#!/usr/bin/env python3
"""Automated skill refinement loop.

Reads failing judge rationales from an eval results JSON, sends them to
Claude to generate SKILL.md fixes, applies the fixes, and reruns eval.

Usage:
    # Run refinement on latest eval results
    python -m tests.eval.refine

    # Run on specific results file
    python -m tests.eval.refine --results tests/eval/results/eval_v4.json

    # Dry run — show proposed fixes without applying
    python -m tests.eval.refine --dry-run

    # Max iterations (default: 3)
    python -m tests.eval.refine --max-iterations 2
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("refine")

SKILLS_DIR = PROJECT_ROOT / "skills"
RESULTS_DIR = PROJECT_ROOT / "tests" / "eval" / "results"


def find_latest_results() -> Path | None:
    """Find the most recent eval results JSON file."""
    if not RESULTS_DIR.exists():
        return None
    results = sorted(RESULTS_DIR.glob("eval_*.json"), reverse=True)
    return results[0] if results else None


def extract_failures(results_path: Path) -> list[dict]:
    """Extract failing evaluators with their rationales from results JSON."""
    with open(results_path) as f:
        data = json.load(f)

    failures = []
    for report in data.get("reports", []):
        scenario = report["scenario"]
        for ev in report.get("evaluators", []):
            if not ev.get("passed", True):
                failures.append({
                    "scenario": scenario,
                    "evaluator": ev["name"],
                    "score": ev.get("score", 0),
                    "reason": ev.get("reason", ""),
                })
    return failures


def identify_relevant_skill(failure: dict) -> Path | None:
    """Map a failure to the most relevant SKILL.md file."""
    scenario = failure["scenario"]
    evaluator = failure["evaluator"]

    # Map scenarios to primary skill files
    scenario_skill_map = {
        "basic_revenue_analysis": "xlsx",
        "full_pdf_report": "xlsx",
        "multisheet_join": "xlsx",
        "multi_turn_followup": "xlsx",
        "category_breakdown": "xlsx",
    }

    # Some evaluators map to specific skills regardless of scenario
    evaluator_skill_map = {
        "report_generated": "pdf",
        "no_hardcoded_metrics": "xlsx",
    }

    skill_name = evaluator_skill_map.get(evaluator) or scenario_skill_map.get(scenario, "xlsx")
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    return skill_path if skill_path.exists() else None


def build_fix_prompt(failures: list[dict], skill_path: Path) -> str:
    """Build the prompt for Claude to fix a SKILL.md based on failures."""
    skill_content = skill_path.read_text()

    failure_descriptions = []
    for f in failures:
        failure_descriptions.append(
            f"- Scenario '{f['scenario']}', evaluator '{f['evaluator']}' "
            f"(score: {f['score']:.0%}): {f['reason']}"
        )

    return f"""You are a skill file editor for an AI data analysis agent.

The agent uses SKILL.md files as part of its system prompt to guide behavior.
Several evaluation scenarios have FAILED. Your job is to fix the SKILL.md
to prevent these failures.

## Current SKILL.md content:
```markdown
{skill_content}
```

## Failures to fix:
{chr(10).join(failure_descriptions)}

## Rules:
1. Only modify the SKILL.md content — do not add new files
2. Keep changes minimal and targeted
3. Add or strengthen instructions that would prevent the specific failures
4. Do NOT remove existing instructions unless they conflict with the fix
5. Preserve the overall structure and formatting
6. The agent uses a PERSISTENT Python kernel — variables survive across execute() calls
7. generate_html() runs in a SEPARATE process — HTML must be passed as a literal string
8. Do NOT add pickle usage

## Output:
Return ONLY the updated SKILL.md content, starting with the YAML frontmatter (---).
No explanations, no code blocks wrapping — just the raw markdown content."""


def call_claude_for_fix(prompt: str) -> str | None:
    """Call Claude API to get the fixed SKILL.md content."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set")
        return None

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except ImportError:
        logger.error("anthropic package not installed. Run: pip install anthropic")
        return None
    except Exception as e:
        logger.error("Claude API call failed: %s", e)
        return None


def apply_fix(skill_path: Path, new_content: str, dry_run: bool = False) -> bool:
    """Apply the fix to the SKILL.md file."""
    old_content = skill_path.read_text()
    if old_content.strip() == new_content.strip():
        logger.info("  No changes needed for %s", skill_path.name)
        return False

    if dry_run:
        logger.info("  [DRY RUN] Would update %s", skill_path)
        # Show diff summary
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        added = len(new_lines) - len(old_lines)
        logger.info("  Lines: %d → %d (%+d)", len(old_lines), len(new_lines), added)
        return False

    # Backup original
    backup_path = skill_path.with_suffix(".md.bak")
    backup_path.write_text(old_content)
    logger.info("  Backup: %s", backup_path)

    # Write new content
    skill_path.write_text(new_content)
    logger.info("  Updated: %s", skill_path)
    return True


def run_eval_subprocess(scenario: str | None = None) -> Path | None:
    """Run eval as a subprocess and return the results file path."""
    cmd = [sys.executable, "-m", "tests.eval.run_eval"]
    if scenario:
        cmd.extend(["--scenario", scenario])

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = str(RESULTS_DIR / f"eval_refine_{ts}.json")
    cmd.extend(["--output", out_path])

    logger.info("  Running eval: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT), timeout=600,
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            logger.error("  Eval failed:\n%s", result.stderr[-500:])
            return None
        return Path(out_path)
    except subprocess.TimeoutExpired:
        logger.error("  Eval timed out (600s)")
        return None


def main():
    parser = argparse.ArgumentParser(description="Automated skill refinement loop")
    parser.add_argument("--results", "-r", help="Eval results JSON to refine from")
    parser.add_argument("--dry-run", action="store_true", help="Show fixes without applying")
    parser.add_argument("--max-iterations", type=int, default=3, help="Max refinement iterations")
    parser.add_argument("--scenario", "-s", help="Only refine for a specific scenario")
    args = parser.parse_args()

    # Find results file
    if args.results:
        results_path = Path(args.results)
    else:
        results_path = find_latest_results()

    if not results_path or not results_path.exists():
        logger.error("No eval results found. Run eval first: python -m tests.eval.run_eval")
        sys.exit(1)

    logger.info("=" * 70)
    logger.info("  SKILL REFINEMENT LOOP")
    logger.info("  Results: %s", results_path)
    logger.info("  Max iterations: %d", args.max_iterations)
    logger.info("=" * 70)

    for iteration in range(1, args.max_iterations + 1):
        logger.info("\n── Iteration %d/%d ──", iteration, args.max_iterations)

        # Extract failures
        failures = extract_failures(results_path)
        if args.scenario:
            failures = [f for f in failures if f["scenario"] == args.scenario]

        if not failures:
            logger.info("  ✅ No failures found — refinement complete!")
            break

        logger.info("  Found %d failures:", len(failures))
        for f in failures:
            logger.info("    ❌ %s / %s: %s", f["scenario"], f["evaluator"], f["reason"][:80])

        # Group failures by skill file
        skill_failures: dict[Path, list[dict]] = {}
        for f in failures:
            skill_path = identify_relevant_skill(f)
            if skill_path:
                skill_failures.setdefault(skill_path, []).append(f)

        # Fix each skill file
        any_changed = False
        for skill_path, skill_fails in skill_failures.items():
            logger.info("\n  Fixing %s (%d failures)...", skill_path.relative_to(PROJECT_ROOT), len(skill_fails))

            prompt = build_fix_prompt(skill_fails, skill_path)
            new_content = call_claude_for_fix(prompt)

            if new_content:
                changed = apply_fix(skill_path, new_content, dry_run=args.dry_run)
                if changed:
                    any_changed = True

        if args.dry_run:
            logger.info("\n  [DRY RUN] No changes applied. Exiting.")
            break

        if not any_changed:
            logger.info("\n  No changes made — stopping refinement loop.")
            break

        # Rerun eval
        logger.info("\n  Rerunning eval after fixes...")
        new_results = run_eval_subprocess(args.scenario)
        if new_results:
            # Compare scores
            with open(results_path) as f:
                old_data = json.load(f)
            with open(new_results) as f:
                new_data = json.load(f)

            old_score = old_data.get("overall_score", 0)
            new_score = new_data.get("overall_score", 0)
            delta = new_score - old_score
            icon = "📈" if delta > 0.01 else "📉" if delta < -0.01 else "➡️"
            logger.info("  %s Score: %.1f%% → %.1f%% (Δ %+.1f%%)",
                        icon, old_score * 100, new_score * 100, delta * 100)

            results_path = new_results  # Use new results for next iteration

            if new_score >= 0.95:
                logger.info("  ✅ Score ≥95%% — refinement complete!")
                break
        else:
            logger.warning("  Eval rerun failed — stopping.")
            break

    logger.info("\n" + "=" * 70)
    logger.info("  REFINEMENT COMPLETE")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
