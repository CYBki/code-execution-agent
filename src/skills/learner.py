"""Skill learner — detect agent errors, judge output quality, and auto-improve SKILL.md.

Two paths to skill improvement:
1. Error-based: agent code crashed / was blocked → extract errors → generate fix
2. Quality-based: LLM-as-judge scores output < threshold → generate improvement

Both paths converge in auto_learn(), the single entry point called from chat.py.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_EVAL_LOG_PATH = _PROJECT_ROOT / "eval_log.jsonl"

# --- Constants ---
_MAX_ERRORS_PER_SUGGESTION = 5       # max errors sent to suggestion LLM
_MAX_SKILL_CONTENT_CHARS = 3000      # max chars of current SKILL.md sent to LLM
_MAX_TOOL_SUMMARY_STEPS = 5          # last N execute calls shown to judge
_REPEAT_OVERRIDE_THRESHOLD = 3       # failures needed to override skill_issue=False
_EVAL_LOG_LOOKBACK = 20              # how many recent log entries to scan
_MAX_SKILL_FILE_BYTES = 50_000       # ~50KB — refuse to append if SKILL.md exceeds this
_MAX_SUGGESTION_CHARS = 3000         # reject LLM suggestions longer than this
_MIN_SUGGESTION_CHARS = 20           # reject LLM suggestions shorter than this

# Thread safety for ALL file operations (both read and write)
_file_lock = threading.Lock()

# Error keywords that indicate an execute failure
_ERROR_KEYWORDS = (
    "Traceback", "Error:", "Exception:", "AssertionError",
    "KeyError", "ValueError", "TypeError", "NameError",
    "IndexError", "AttributeError", "ModuleNotFoundError",
    "FileNotFoundError", "ZeroDivisionError", "PermissionError",
)

# Interceptor block markers (agent made a bad decision)
_BLOCK_MARKERS = (
    "⛔ BLOCKED",
    "⚠️ HARDCODED DATA DETECTED",
    "🛑 CIRCUIT BREAKER",
)

# Correction loop markers
_CORRECTION_MARKERS = (
    "🔄 CORRECTION",
    "⛔ CORRECTION LIMIT",
)


@dataclass
class ErrorContext:
    """A single error occurrence from the agent's execution."""
    tool_name: str
    tool_input: str  # The command/code that caused the error
    error_output: str  # The error message/traceback
    error_type: str  # "execute_error", "blocked", "correction_loop"


@dataclass
class SkillSuggestion:
    """An LLM-generated suggestion to improve a SKILL.md."""
    skill_name: str
    skill_path: str
    errors: list[ErrorContext]
    suggestion: str  # The actual improvement text from LLM
    current_content: str  # Current SKILL.md content (for diff display)


@dataclass
class JudgeResult:
    """Result of LLM-as-judge output quality evaluation."""
    score: float       # 0.0–1.0
    reason: str        # Why this score was given
    skill_issue: bool  # True if the problem is in SKILL.md, not user error
    skill_name: str    # Which skill was evaluated


@dataclass
class SkillUpdateResult:
    """Outcome of a single skill update attempt."""
    skill_name: str
    action: str  # "skill_updated", "update_failed", "no_suggestion"


def _parse_judge_json(raw: str) -> dict:
    """Extract and parse JSON from LLM judge response.

    Handles common LLM quirks: ```json wrappers, extra text around JSON.
    Falls back to safe defaults if parsing fails.
    """
    # Try to find JSON object in the response
    match = re.search(r'\{[^{}]*"score"[^{}]*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Fallback: try the whole string
    try:
        return json.loads(raw.strip().strip("`").strip())
    except json.JSONDecodeError:
        logger.warning("Failed to parse judge JSON, using defaults. Raw: %s", raw[:200])
        return {"score": 0.5, "reason": "judge_parse_failed", "skill_issue": False}


def extract_errors(collected_steps: list[dict]) -> list[ErrorContext]:
    """Extract error contexts from agent's collected tool call steps.

    Scans execute outputs for: failures, interceptor blocks, correction loops.
    """
    errors: list[ErrorContext] = []

    for step in collected_steps:
        name = step.get("name", "")
        output = step.get("output") or ""
        tool_input = step.get("input", {})

        # Get the command string from execute calls
        cmd = ""
        if name == "execute":
            cmd = tool_input.get("command", "")
        elif name == "parse_file":
            cmd = tool_input.get("filename", "")

        # 1. Execute errors (Traceback, exceptions)
        if name == "execute" and any(kw in output for kw in _ERROR_KEYWORDS):
            # Skip if it's a blocked message (handled separately)
            if not any(m in output for m in _BLOCK_MARKERS):
                errors.append(ErrorContext(
                    tool_name=name,
                    tool_input=cmd[:500],
                    error_output=output[:1000],
                    error_type="execute_error",
                ))

        # 2. Interceptor blocks (agent tried something forbidden)
        if any(m in output for m in _BLOCK_MARKERS):
            errors.append(ErrorContext(
                tool_name=name,
                tool_input=cmd[:500],
                error_output=output[:500],
                error_type="blocked",
            ))

        # 3. Correction loops (agent had to retry)
        if any(m in output for m in _CORRECTION_MARKERS):
            errors.append(ErrorContext(
                tool_name=name,
                tool_input=cmd[:500],
                error_output=output[:500],
                error_type="correction_loop",
            ))

    return errors


def detect_skills_for_errors(
    uploaded_files: list,
    user_query: str,
) -> list[str]:
    """Determine which skills were active for this session.

    Uses the same detection logic as the agent builder.
    """
    from src.skills.registry import detect_required_skills
    return detect_required_skills(uploaded_files or [], user_query)


def _load_skill_content(skill_name: str) -> tuple[str, str] | None:
    """Load SKILL.md content and path for a given skill name.

    Returns (content, path) or None if not found.
    """
    skill_path = Path(f"skills/{skill_name}/SKILL.md")
    if not skill_path.exists():
        return None
    return skill_path.read_text(encoding="utf-8"), str(skill_path)


def generate_skill_suggestion(
    errors: list[ErrorContext],
    skill_name: str,
    user_query: str,
) -> SkillSuggestion | None:
    """Call LLM to generate an improvement suggestion for a SKILL.md.

    Args:
        errors: List of errors from the agent execution.
        skill_name: Which skill to improve (e.g., "xlsx", "csv").
        user_query: The user's original query that triggered the errors.

    Returns:
        SkillSuggestion or None if no suggestion could be generated.
    """
    result = _load_skill_content(skill_name)
    if result is None:
        logger.warning("Skill '%s' not found, skipping suggestion", skill_name)
        return None

    current_content, skill_path = result

    # Build error summary for the LLM
    error_descriptions = []
    for i, err in enumerate(errors[:_MAX_ERRORS_PER_SUGGESTION], 1):
        error_descriptions.append(
            f"Error {i} ({err.error_type}):\n"
            f"  Tool: {err.tool_name}\n"
            f"  Input: {err.tool_input[:200]}\n"
            f"  Output: {err.error_output[:300]}"
        )
    errors_text = "\n\n".join(error_descriptions)

    system_msg = SystemMessage(content="""You are a skill improvement analyst for an AI data analysis agent.

The agent reads SKILL.md files as direct instructions. Your job is to write NEW RULES
that will be appended to the SKILL.md so the agent stops repeating the same mistake.

CRITICAL FORMAT RULES — the agent parses your output as raw markdown instructions:
- Do NOT wrap output in ```markdown``` fences — write raw markdown directly
- Do NOT include "Analysis" or "Why this happened" sections — only write actionable RULES
- Start with a ## heading, then bullet-point rules the agent can follow
- Keep it concise: max 15 lines
- Use imperative language: "Always…", "Never…", "Before doing X, check Y…"
- Only suggest things the agent CAN do (no internet access, no external APIs)
- Focus on the ROOT CAUSE, not symptoms
- If the error is a one-off user mistake (not a pattern), say "NO_SUGGESTION" and nothing else

GOOD example:
## Column Addition Rules
- When user asks for ONE column, add exactly ONE column — no "bonus" extras
- If currency name is ambiguous (e.g. "kron" could be DKK/SEK/NOK), ASK the user which one
- Always verify the column was added: print(df.columns.tolist()) after modification

BAD example (DO NOT do this):
## Analysis
The error occurred because... [WRONG — agent doesn't need explanations]
```markdown
## Rules  [WRONG — fenced markdown is invisible to agent]
```""")

    human_msg = HumanMessage(content=f"""## Current SKILL.md ({skill_name})

```markdown
{current_content[:_MAX_SKILL_CONTENT_CHARS]}
```

## User Query
{user_query}

## Errors During Execution
{errors_text}

## Task
Analyze these errors and suggest a specific improvement to the SKILL.md above.
Output a markdown section that should be APPENDED to the existing SKILL.md to prevent these errors.""")

    try:
        from deepagents._models import resolve_model
        model = resolve_model("anthropic:claude-sonnet-4-20250514")
        response = model.invoke([system_msg, human_msg])
        suggestion_text = response.content.strip()

        # If LLM says no suggestion needed, skip
        if "NO_SUGGESTION" in suggestion_text:
            logger.info("LLM determined no skill improvement needed for '%s'", skill_name)
            return None

        return SkillSuggestion(
            skill_name=skill_name,
            skill_path=skill_path,
            errors=errors,
            suggestion=suggestion_text,
            current_content=current_content,
        )
    except Exception as e:
        logger.error("Failed to generate skill suggestion for '%s': %s", skill_name, e)
        return None


def judge_output(
    user_query: str,
    agent_final_response: str,
    collected_steps: list[dict],
    uploaded_files: list,
) -> JudgeResult | None:
    """Score agent output quality using LLM-as-judge (Haiku for cost efficiency).

    Evaluates whether the agent's response actually satisfies the user's query.
    Returns a JudgeResult with score, reason, and whether the issue is skill-related.

    Args:
        user_query: The user's original query.
        agent_final_response: The agent's final text response to the user.
        collected_steps: All tool calls + outputs from the agent run.
        uploaded_files: Files the user uploaded.

    Returns:
        JudgeResult or None if judge call fails.
    """
    # Determine active skill for attribution
    active_skills = detect_skills_for_errors(uploaded_files, user_query)
    skill_name = active_skills[0] if active_skills else "unknown"

    # Build tool call summary: parse_file (schema context) + last N execute calls
    parse_summary = ""
    tool_summary_parts = []
    for step in collected_steps:
        name = step.get("name", "")
        if name == "parse_file" and not parse_summary:
            out = (step.get("output") or "")[:500]
            parse_summary = f"parse_file → {out}"
    for step in collected_steps[-10:]:
        if step.get("name") == "execute":
            cmd = step.get("input", {}).get("command", "")[:150]
            out = (step.get("output") or "")[:150]
            tool_summary_parts.append(f"execute: {cmd}\n→ {out}")
    parts = ([parse_summary] if parse_summary else []) + tool_summary_parts[-_MAX_TOOL_SUMMARY_STEPS:]
    tool_summary = "\n\n".join(parts) or "(no tool calls)"

    system_msg = SystemMessage(content="""You are a quality judge for an AI data analysis agent.

Score how well the agent's output satisfies the user's query.

Return ONLY a JSON object — no extra text, no markdown fences:
{"score": <float 0.0-1.0>, "reason": "<1-2 sentences>", "skill_issue": <true/false>}

Scoring guide:
- 1.0: Perfect — query fully answered, code output confirms correct result
- 0.8: Good — minor issues but usable
- 0.6: Partial — some parts answered, some missing or wrong
- 0.4: Poor — significant errors or missing analysis
- 0.2: Failed — wrong data, wrong format, or nonsensical output
- 0.0: No output at all

How to judge:
- Compare the user's request to what the code actually produced (look at execute outputs).
- If parse_file output is present, check: did the agent follow the schema info (correct columns, date formats, types)?
- If user asked to add a column → does code output show that column exists?
- If user asked to filter → does code output show reduced row count?
- If user asked for a file → did the agent produce it and confirm its contents?
- If code ran successfully but there's no evidence the output matches the request → lower the score.
- If agent repeatedly ignores parse_file instructions (e.g. wrong date format) → skill_issue=true.

skill_issue = true means the agent's INSTRUCTIONS (SKILL.md) need improvement.
skill_issue = false means it's a one-off error, user ambiguity, or infrastructure issue.""")

    human_msg = HumanMessage(content=f"""## User Query
{user_query}

## Agent Final Response
{agent_final_response[:1500]}

## Tool Calls (parse_file + last execute steps)
{tool_summary}

## Task
Judge the output quality. Return JSON only.""")

    try:
        from deepagents._models import resolve_model
        model = resolve_model("anthropic:claude-haiku-4-5-20251001")
        response = model.invoke([system_msg, human_msg])
        parsed = _parse_judge_json(response.content)

        score = max(0.0, min(1.0, float(parsed.get("score", 0.5))))
        reason = str(parsed.get("reason", "no_reason"))
        skill_issue = bool(parsed.get("skill_issue", False))

        result = JudgeResult(
            score=score,
            reason=reason,
            skill_issue=skill_issue,
            skill_name=skill_name,
        )
        logger.info("[Judge] score=%.2f skill_issue=%s skill=%s reason=%s",
                     score, skill_issue, skill_name, reason[:80])
        return result
    except Exception as e:
        logger.error("[Judge] Failed: %s", e)
        return None


def _append_eval_log(
    judge_result: JudgeResult,
    user_query: str,
    action_taken: str = "none",
    suggestion_text: str = "",
) -> None:
    """Append a judge evaluation record to eval_log.jsonl.

    Each line is a self-contained JSON object for easy grep/analysis.

    Args:
        judge_result: The judge's evaluation result.
        user_query: The user's original query (truncated to 200 chars).
        action_taken: What was done — "none", "skill_updated", "no_suggestion".
        suggestion_text: The actual text appended to SKILL.md (empty if no update).
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": judge_result.score,
        "reason": judge_result.reason,
        "skill_issue": judge_result.skill_issue,
        "skill_name": judge_result.skill_name,
        "action": action_taken,
        "query": user_query[:200],
    }
    if suggestion_text:
        record["suggestion"] = suggestion_text[:_MAX_SUGGESTION_CHARS]
    try:
        with _file_lock:
            with open(_EVAL_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info("[EvalLog] Appended: score=%.2f action=%s", judge_result.score, action_taken)
    except Exception as e:
        logger.error("[EvalLog] Failed to write: %s", e)


def _count_similar_failures(
    skill_name: str,
    threshold: float,
    lookback: int = _EVAL_LOG_LOOKBACK,
) -> int:
    """Count recent low-score entries for the same skill in eval_log.jsonl.

    Scans the last `lookback` log entries and counts how many have
    score < threshold for the given skill, regardless of skill_issue flag.

    Args:
        skill_name: Skill to check (e.g., "xlsx").
        threshold: Score threshold to consider as failure.
        lookback: How many recent entries to scan.

    Returns:
        Number of recent failures for this skill.
    """
    if not _EVAL_LOG_PATH.exists():
        return 0

    try:
        with _file_lock:
            with open(_EVAL_LOG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
    except Exception as e:
        logger.error("[RepeatCheck] Failed to read eval_log: %s", e)
        return 0

    # Scan last N entries
    count = 0
    for line in lines[-lookback:]:
        try:
            record = json.loads(line)
            if record.get("skill_name") == skill_name and record.get("score", 1.0) < threshold:
                count += 1
        except json.JSONDecodeError:
            continue

    return count


def _apply_skill_suggestion_auto(suggestion: SkillSuggestion) -> bool:
    """Apply a skill suggestion directly to SKILL.md without UI interaction.

    Appends the suggestion text to the skill file and clears the loader cache
    so the next agent build picks up the updated instructions.

    Args:
        suggestion: The SkillSuggestion to apply.

    Returns:
        True if successfully applied, False otherwise.
    """
    # Validate suggestion before writing
    text = suggestion.suggestion.strip()
    if len(text) < _MIN_SUGGESTION_CHARS:
        logger.warning("[AutoLearn] Suggestion too short (%d chars), skipping", len(text))
        return False
    if len(text) > _MAX_SUGGESTION_CHARS:
        logger.warning("[AutoLearn] Suggestion too long (%d chars), truncating", len(text))
        text = text[:_MAX_SUGGESTION_CHARS]

    try:
        with _file_lock:
            # Check file size before appending
            skill_path = Path(suggestion.skill_path)
            if skill_path.exists() and skill_path.stat().st_size > _MAX_SKILL_FILE_BYTES:
                logger.warning(
                    "[AutoLearn] SKILL.md too large (%d bytes > %d), skipping update",
                    skill_path.stat().st_size, _MAX_SKILL_FILE_BYTES,
                )
                return False

            with open(suggestion.skill_path, "a", encoding="utf-8") as f:
                f.write("\n\n")
                f.write(text)
                f.write("\n")

        # Clear skill loader cache so the updated skill is loaded next time
        from src.skills.loader import load_skill
        load_skill.cache_clear()

        logger.info("[AutoLearn] Skill updated: %s", suggestion.skill_path)
        return True
    except Exception as e:
        logger.error("[AutoLearn] Failed to update %s: %s", suggestion.skill_path, e)
        return False


def auto_learn(
    user_query: str,
    agent_final_response: str,
    collected_steps: list[dict],
    uploaded_files: list,
    threshold: float = 0.7,
) -> None:
    """Main entry point: judge output quality and auto-improve skills if needed.

    Called from chat.py in a background thread after agent stream completes.
    Combines both error-based and quality-based skill improvement:

    1. Judge output quality with LLM-as-judge (Haiku)
    2. Log every evaluation to eval_log.jsonl
    3. If score < threshold AND skill_issue is True:
       a. Extract code-level errors from tool calls
       b. Add judge's quality failure as an additional error context
       c. Generate SKILL.md improvement suggestion (Sonnet)
       d. Auto-apply the suggestion

    Args:
        user_query: The user's original query.
        agent_final_response: The agent's final text response.
        collected_steps: All tool calls + outputs from the agent run.
        uploaded_files: Files the user uploaded.
        threshold: Quality score below which skill improvement is triggered.
    """
    try:
        # Step 1: Judge output quality
        judge_result = judge_output(
            user_query, agent_final_response, collected_steps, uploaded_files
        )
        if judge_result is None:
            logger.warning("[AutoLearn] Judge returned None, skipping")
            return

        # Step 2: Log evaluation (always, regardless of score)
        action = "none"

        # Step 3: Check if improvement is needed
        # Override skill_issue if the same skill keeps failing (repeat pattern)
        should_improve = judge_result.skill_issue
        if judge_result.score < threshold and not should_improve:
            repeat_count = _count_similar_failures(
                judge_result.skill_name, threshold
            )
            if repeat_count >= _REPEAT_OVERRIDE_THRESHOLD:
                should_improve = True
                logger.info(
                    "[AutoLearn] skill_issue overridden: %d recent failures for '%s'",
                    repeat_count, judge_result.skill_name,
                )

        combined_suggestions = ""

        if judge_result.score < threshold and should_improve:
            logger.info("[AutoLearn] Low score (%.2f < %.2f) + skill improvement needed",
                        judge_result.score, threshold)

            # 3a. Extract code-level errors
            errors = extract_errors(collected_steps)

            # 3b. Add judge's quality assessment as an error context
            errors.append(ErrorContext(
                tool_name="judge",
                tool_input=user_query[:300],
                error_output=f"Quality score: {judge_result.score:.2f}. {judge_result.reason}",
                error_type="quality_failure",
            ))

            # 3c. Generate suggestion for the relevant skill
            active_skills = detect_skills_for_errors(uploaded_files, user_query)
            if not active_skills:
                logger.info("[AutoLearn] No active skills found, cannot improve")
                _append_eval_log(judge_result, user_query, "no_skill")
                return

            skill_results: list[SkillUpdateResult] = []
            applied_suggestions: list[str] = []
            for skill_name in active_skills:
                suggestion = generate_skill_suggestion(errors, skill_name, user_query)
                if suggestion:
                    success = _apply_skill_suggestion_auto(suggestion)
                    outcome = "skill_updated" if success else "update_failed"
                    if success:
                        applied_suggestions.append(suggestion.suggestion.strip())
                else:
                    outcome = "no_suggestion"
                skill_results.append(SkillUpdateResult(skill_name=skill_name, action=outcome))
                logger.info("[AutoLearn] Skill '%s' → %s", skill_name, outcome)

            # Summarise: prefer "skill_updated" > "update_failed" > "no_suggestion"
            priority = {"skill_updated": 0, "update_failed": 1, "no_suggestion": 2}
            skill_results.sort(key=lambda r: priority.get(r.action, 99))
            action = skill_results[0].action if skill_results else "none"
            combined_suggestions = "\n---\n".join(applied_suggestions)

        elif judge_result.score >= threshold:
            logger.info("[AutoLearn] Score %.2f >= %.2f — no improvement needed",
                        judge_result.score, threshold)
        else:
            repeat_count = _count_similar_failures(
                judge_result.skill_name, threshold
            )
            logger.info(
                "[AutoLearn] Score %.2f < %.2f, skill_issue=False, repeat_count=%d (need %d to override)",
                judge_result.score, threshold, repeat_count, _REPEAT_OVERRIDE_THRESHOLD,
            )

        # Step 4: Log with final action
        _append_eval_log(judge_result, user_query, action,
                         suggestion_text=combined_suggestions)

    except Exception as e:
        logger.error("[AutoLearn] Unexpected error: %s", e, exc_info=True)
