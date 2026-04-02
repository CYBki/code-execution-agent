"""Rule-based MLflow scorers wrapping existing evaluators.

Each scorer receives a trace and returns Feedback. These wrap the existing
evaluators from tests/eval/evaluators.py so they work with mlflow.genai.evaluate().
"""

from __future__ import annotations

import logging
from typing import Any

from mlflow.entities import Feedback
from mlflow.genai.scorers import scorer

from tests.eval.evaluators import (
    eval_completeness,
    eval_execute_efficiency,
    eval_no_hardcoded_metrics,
    eval_no_pickle,
    eval_no_shell_exploration,
    eval_persistent_kernel,
    eval_report_generated,
    eval_validation_present,
)

logger = logging.getLogger(__name__)


def _extract_tool_calls(trace) -> list[dict]:
    """Extract tool calls from an MLflow trace into evaluator-compatible format."""
    tool_calls = []
    if trace is None:
        return tool_calls

    for span in trace.search_spans(span_type="TOOL"):
        name = span.name or ""
        inputs = span.inputs or {}
        output = ""
        if span.outputs:
            output = str(span.outputs) if not isinstance(span.outputs, str) else span.outputs
        tool_calls.append({
            "name": name,
            "input": inputs,
            "output": output,
        })
    return tool_calls


def _extract_response(trace) -> str:
    """Extract the final agent response text from an MLflow trace."""
    if trace is None:
        return ""
    # Look for the last agent span with text output
    for span in reversed(trace.search_spans(span_type="AGENT")):
        if span.outputs and isinstance(span.outputs, str):
            return span.outputs
    # Fallback: root span output
    if trace.info and trace.info.root_span_id:
        root = trace.get_span(trace.info.root_span_id)
        if root and root.outputs:
            return str(root.outputs)
    return ""


# ---------------------------------------------------------------------------
# Wrapped scorers
# ---------------------------------------------------------------------------

@scorer(name="no_pickle")
def no_pickle_scorer(trace) -> Feedback:
    """Agent must never use pickle in execute commands."""
    tool_calls = _extract_tool_calls(trace)
    result = eval_no_pickle(tool_calls, _extract_response(trace))
    return Feedback(
        value="yes" if result.passed else "no",
        rationale=result.reason,
        source={"name": "no_pickle", "score": result.score},
    )


@scorer(name="persistent_kernel")
def persistent_kernel_scorer(trace) -> Feedback:
    """No redundant re-reads of data files."""
    tool_calls = _extract_tool_calls(trace)
    # Count turns from trace (each user message = 1 turn)
    num_turns = max(1, len(trace.search_spans(span_type="AGENT")))
    result = eval_persistent_kernel(tool_calls, _extract_response(trace), num_turns=num_turns)
    return Feedback(
        value="yes" if result.passed else "no",
        rationale=result.reason,
        source={"name": "persistent_kernel", "score": result.score},
    )


@scorer(name="no_hardcoded_metrics")
def no_hardcoded_metrics_scorer(trace) -> Feedback:
    """Report code should not contain hardcoded large numbers."""
    tool_calls = _extract_tool_calls(trace)
    result = eval_no_hardcoded_metrics(tool_calls, _extract_response(trace))
    return Feedback(
        value="yes" if result.passed else "no",
        rationale=result.reason,
        source={"name": "no_hardcoded_metrics", "score": result.score},
    )


@scorer(name="validation_present")
def validation_present_scorer(trace) -> Feedback:
    """At least one execute should contain a validation checkpoint."""
    tool_calls = _extract_tool_calls(trace)
    result = eval_validation_present(tool_calls, _extract_response(trace))
    return Feedback(
        value="yes" if result.passed else "no",
        rationale=result.reason,
        source={"name": "validation_present", "score": result.score},
    )


@scorer(name="no_shell_exploration")
def no_shell_exploration_scorer(trace) -> Feedback:
    """Agent should not waste executes on ls/cat/os.listdir."""
    tool_calls = _extract_tool_calls(trace)
    result = eval_no_shell_exploration(tool_calls, _extract_response(trace))
    return Feedback(
        value="yes" if result.passed else "no",
        rationale=result.reason,
        source={"name": "no_shell_exploration", "score": result.score},
    )


@scorer(name="report_generated")
def report_generated_scorer(trace) -> Feedback:
    """For report scenarios: download_file should be called with a PDF."""
    tool_calls = _extract_tool_calls(trace)
    result = eval_report_generated(tool_calls, _extract_response(trace))
    return Feedback(
        value="yes" if result.passed else "no",
        rationale=result.reason,
        source={"name": "report_generated", "score": result.score},
    )


@scorer(name="execute_efficiency")
def execute_efficiency_scorer(trace) -> Feedback:
    """Agent should complete within the execute budget."""
    tool_calls = _extract_tool_calls(trace)
    result = eval_execute_efficiency(tool_calls, _extract_response(trace))
    return Feedback(
        value="yes" if result.passed else "no",
        rationale=result.reason,
        source={"name": "execute_efficiency", "score": result.score},
    )


@scorer(name="completeness")
def completeness_scorer(trace) -> Feedback:
    """Final response should address the user query."""
    tool_calls = _extract_tool_calls(trace)
    response = _extract_response(trace)
    result = eval_completeness(tool_calls, response)
    return Feedback(
        value="yes" if result.passed else "no",
        rationale=result.reason,
        source={"name": "completeness", "score": result.score},
    )


# All rule-based scorers for easy import
ALL_RULE_SCORERS = [
    no_pickle_scorer,
    persistent_kernel_scorer,
    no_hardcoded_metrics_scorer,
    validation_present_scorer,
    no_shell_exploration_scorer,
    report_generated_scorer,
    execute_efficiency_scorer,
    completeness_scorer,
]

DEFAULT_RULE_SCORERS = [
    no_pickle_scorer,
    persistent_kernel_scorer,
    no_shell_exploration_scorer,
    execute_efficiency_scorer,
    completeness_scorer,
]
