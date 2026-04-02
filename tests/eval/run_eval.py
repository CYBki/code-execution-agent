#!/usr/bin/env python3
"""Run agent evaluation scenarios and produce a score report.

Usage:
    # Run all scenarios (classic mode)
    python -m tests.eval.run_eval

    # Run with MLflow scorers + LLM judges
    python -m tests.eval.run_eval --mlflow

    # Run specific scenario
    python -m tests.eval.run_eval --scenario basic_revenue_analysis

    # Generate fixtures only
    python -m tests.eval.run_eval --generate-fixtures

    # Compare two runs (A/B)
    python -m tests.eval.run_eval --compare results_v1.json results_v2.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from tests.eval.evaluators import ALL_EVALUATORS, DEFAULT_EVALUATORS, EvalResult
from tests.eval.runner import ScenarioResult, run_scenario
from tests.eval.scenarios import SCENARIOS

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RESULTS_DIR = PROJECT_ROOT / "tests" / "eval" / "results"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("eval")


def generate_fixtures():
    """Generate fixture xlsx files."""
    from tests.eval.fixtures.generate import (
        generate_sales_fixture,
        generate_multisheet_fixture,
    )
    generate_sales_fixture()
    generate_multisheet_fixture()


def score_scenario(result: ScenarioResult, scenario: dict) -> dict:
    """Run evaluators on a scenario result and return score report."""
    evaluator_names = scenario.get("evaluators", DEFAULT_EVALUATORS)
    tool_calls = result.all_tool_calls
    response = result.final_response

    scores = []
    for eval_name in evaluator_names:
        eval_fn = ALL_EVALUATORS.get(eval_name)
        if not eval_fn:
            logger.warning("Unknown evaluator: %s", eval_name)
            continue

        # Special kwargs for certain evaluators
        kwargs = {}
        if eval_name == "completeness":
            kwargs["expected_keywords"] = scenario.get("expected_keywords")
        if eval_name == "persistent_kernel":
            kwargs["num_turns"] = len(result.turns)

        try:
            eval_result: EvalResult = eval_fn(tool_calls, response, **kwargs)
        except Exception as e:
            eval_result = EvalResult(eval_name, False, 0.0, f"Evaluator error: {e}")

        scores.append({
            "name": eval_result.name,
            "passed": eval_result.passed,
            "score": eval_result.score,
            "reason": eval_result.reason,
        })

    total_score = sum(s["score"] for s in scores) / len(scores) if scores else 0
    passed_count = sum(1 for s in scores if s["passed"])

    return {
        "scenario": result.name,
        "total_score": round(total_score, 3),
        "passed": f"{passed_count}/{len(scores)}",
        "duration_s": round(result.total_duration_s, 1),
        "turns": len(result.turns),
        "tool_calls": len(tool_calls),
        "evaluators": scores,
    }


def print_report(reports: list[dict]):
    """Print a formatted evaluation report to stdout."""
    print("\n" + "=" * 70)
    print("  AGENT EVALUATION REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    total_score = 0
    total_passed = 0
    total_evals = 0

    for report in reports:
        name = report["scenario"]
        score = report["total_score"]
        passed = report["passed"]
        duration = report["duration_s"]
        total_score += score
        p, t = passed.split("/")
        total_passed += int(p)
        total_evals += int(t)

        status = "✅" if score >= 0.8 else "⚠️" if score >= 0.5 else "❌"
        print(f"\n  {status} {name}")
        print(f"     Score: {score:.1%}  |  Passed: {passed}  |  Time: {duration:.1f}s")

        for ev in report["evaluators"]:
            icon = "✅" if ev["passed"] else "❌"
            print(f"       {icon} {ev['name']}: {ev['score']:.0%} — {ev['reason']}")

    avg_score = total_score / len(reports) if reports else 0
    print(f"\n{'─' * 70}")
    print(f"  OVERALL: {avg_score:.1%}  |  {total_passed}/{total_evals} evaluators passed")
    print(f"{'─' * 70}\n")

    return avg_score


def compare_reports(file_a: str, file_b: str):
    """Compare two saved evaluation result files (A/B testing)."""
    with open(file_a) as f:
        results_a = json.load(f)
    with open(file_b) as f:
        results_b = json.load(f)

    print("\n" + "=" * 70)
    print("  A/B COMPARISON")
    print(f"  A: {file_a}")
    print(f"  B: {file_b}")
    print("=" * 70)

    # Index by scenario name
    a_map = {r["scenario"]: r for r in results_a["reports"]}
    b_map = {r["scenario"]: r for r in results_b["reports"]}

    all_scenarios = sorted(set(a_map) | set(b_map))
    for name in all_scenarios:
        a = a_map.get(name, {})
        b = b_map.get(name, {})
        a_score = a.get("total_score", 0)
        b_score = b.get("total_score", 0)
        delta = b_score - a_score
        icon = "📈" if delta > 0.05 else "📉" if delta < -0.05 else "➡️"

        print(f"\n  {icon} {name}")
        print(f"     A: {a_score:.1%}  →  B: {b_score:.1%}  (Δ {delta:+.1%})")

        # Per-evaluator diff
        a_evals = {e["name"]: e for e in a.get("evaluators", [])}
        b_evals = {e["name"]: e for e in b.get("evaluators", [])}
        for eval_name in sorted(set(a_evals) | set(b_evals)):
            ae = a_evals.get(eval_name, {})
            be = b_evals.get(eval_name, {})
            a_s = ae.get("score", 0)
            b_s = be.get("score", 0)
            if abs(b_s - a_s) > 0.01:
                d = b_s - a_s
                print(f"       {eval_name}: {a_s:.0%} → {b_s:.0%} (Δ {d:+.0%})")

    a_avg = results_a.get("overall_score", 0)
    b_avg = results_b.get("overall_score", 0)
    delta = b_avg - a_avg
    icon = "📈" if delta > 0.05 else "📉" if delta < -0.05 else "➡️"
    print(f"\n{'─' * 70}")
    print(f"  {icon} OVERALL: A={a_avg:.1%}  →  B={b_avg:.1%}  (Δ {delta:+.1%})")
    print(f"{'─' * 70}\n")


def _format_tool_log(result: "ScenarioResult") -> str:
    """Format tool calls into a readable log for LLM judges."""
    lines = []
    for i, tc in enumerate(result.all_tool_calls, 1):
        tc_input = tc["input"] if isinstance(tc, dict) else tc.input
        tc_output = tc["output"] if isinstance(tc, dict) else tc.output
        tc_name = tc["name"] if isinstance(tc, dict) else tc.name
        cmd_preview = str(tc_input.get("command", tc_input.get("filename", "")))[:200]
        out_preview = tc_output[:300] if tc_output else ""
        lines.append(f"[{i}] {tc_name}({cmd_preview})")
        if out_preview:
            lines.append(f"    → {out_preview}")
    return "\n".join(lines)


def run_mlflow_eval(scenario_results: list[tuple["ScenarioResult", dict]], scenarios: list[dict]):
    """Run MLflow LLM judges on scenario results.

    Instead of reading traces back from MLflow store, passes tool call logs
    directly as inputs/outputs to evaluate(). Rule-based scorers already
    run in classic mode — this only adds LLM judge analysis.
    """
    try:
        import mlflow
        import pandas as pd
        from tests.eval.scorers.llm_judges import (
            DEFAULT_LLM_JUDGES, report_quality, appropriate_strategy,
        )
    except ImportError:
        logger.error("MLflow not installed. Run: pip install 'mlflow[genai]'")
        return

    print("\n" + "=" * 70)
    print("  MLFLOW LLM JUDGES")
    print("=" * 70)

    scenario_map = {s["name"]: s for s in scenarios}

    for result, report in scenario_results:
        name = report["scenario"]
        scenario = scenario_map.get(name, {})
        expect_report = scenario.get("expect_report", False)

        # Select judges
        judges = list(DEFAULT_LLM_JUDGES)
        if expect_report:
            judges.append(report_quality)
        if "join" in name or "large" in name:
            judges.append(appropriate_strategy)

        # Build evaluation data: inputs=dict, outputs=str
        tool_log = _format_tool_log(result)
        eval_data = pd.DataFrame([{
            "inputs": {"query": scenario.get("queries", [""])[0]},
            "outputs": f"## Tool Call Log:\n{tool_log}\n\n## Agent Response:\n{result.final_response}",
        }])

        print(f"\n  📊 {name} ({len(judges)} judges)")
        try:
            eval_result = mlflow.genai.evaluate(
                data=eval_data,
                scorers=judges,
            )
            # Print results from metrics
            if hasattr(eval_result, 'metrics'):
                for key, val in eval_result.metrics.items():
                    if '/mean' in key:
                        judge_name = key.replace('/mean', '')
                        icon = "✅" if val == 1.0 else "⚠️" if val >= 0.5 else "❌"
                        print(f"    {icon} {judge_name}: {val:.0%}")

            # Print per-row rationale
            if hasattr(eval_result, 'tables') and 'eval_results' in eval_result.tables:
                eval_df = eval_result.tables['eval_results']
                for _, row in eval_df.iterrows():
                    for col in eval_df.columns:
                        if col.endswith('/rationale'):
                            judge_name = col.replace('/rationale', '')
                            rationale = row[col]
                            if rationale:
                                print(f"    💬 {judge_name}: {str(rationale)[:150]}")
        except Exception as e:
            logger.warning("  MLflow evaluate failed for '%s': %s", name, e)


def main():
    parser = argparse.ArgumentParser(description="Agent evaluation runner")
    parser.add_argument("--scenario", "-s", help="Run specific scenario by name")
    parser.add_argument("--generate-fixtures", action="store_true",
                        help="Generate fixture files only")
    parser.add_argument("--compare", nargs=2, metavar=("FILE_A", "FILE_B"),
                        help="Compare two result files (A/B test)")
    parser.add_argument("--output", "-o", help="Save results to JSON file")
    parser.add_argument("--mlflow", action="store_true",
                        help="Enable MLflow LLM judges (requires mlflow[genai])")
    args = parser.parse_args()

    if args.generate_fixtures:
        generate_fixtures()
        return

    if args.compare:
        compare_reports(args.compare[0], args.compare[1])
        return

    # Ensure fixtures exist
    if not (FIXTURES_DIR / "sales_50.xlsx").exists():
        logger.info("Generating fixtures...")
        generate_fixtures()

    # Filter scenarios
    scenarios = SCENARIOS
    if args.scenario:
        scenarios = [s for s in SCENARIOS if s["name"] == args.scenario]
        if not scenarios:
            logger.error("Scenario '%s' not found. Available: %s",
                         args.scenario, [s["name"] for s in SCENARIOS])
            sys.exit(1)

    # Run scenarios with shared sandbox (faster — reuses container)
    from src.sandbox.manager import SandboxManager
    sandbox_manager = SandboxManager()

    reports = []
    scenario_results = []  # (ScenarioResult, report) pairs for MLflow
    try:
        for scenario in scenarios:
            result = run_scenario(scenario, str(FIXTURES_DIR), sandbox_manager)
            report = score_scenario(result, scenario)
            reports.append(report)
            scenario_results.append((result, report))
    finally:
        sandbox_manager.stop()

    overall = print_report(reports)

    # Run MLflow LLM judges if requested
    if args.mlflow:
        run_mlflow_eval(scenario_results, scenarios)

    # Save results
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "overall_score": round(overall, 3),
        "reports": reports,
    }

    if args.output:
        out_path = args.output
    else:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = str(RESULTS_DIR / f"eval_{ts}.json")

    with open(out_path, "w") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    logger.info("Results saved to %s", out_path)


if __name__ == "__main__":
    main()
