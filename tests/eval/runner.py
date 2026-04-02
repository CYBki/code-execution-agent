"""Headless agent runner — runs scenarios without Streamlit.

Creates a real SandboxManager, builds the agent via build_agent(),
streams responses, and collects all tool calls + outputs for evaluation.

MLflow integration: if mlflow is installed, enables LangChain autolog
for automatic trace collection. Traces are stored locally (file-based).
"""

from __future__ import annotations

import io
import logging
import os
import signal
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field

from langgraph.errors import GraphRecursionError
from langgraph.types import Overwrite

logger = logging.getLogger(__name__)

# MLflow autolog is intentionally DISABLED during agent execution
# because it interferes with LangChain streaming and causes hangs.
# LLM judges run as a separate post-processing step in run_eval.py.


@dataclass
class ToolCall:
    name: str
    input: dict
    output: str = ""


@dataclass
class TurnResult:
    query: str
    response: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    error: str | None = None
    duration_s: float = 0.0


@dataclass
class ScenarioResult:
    name: str
    turns: list[TurnResult] = field(default_factory=list)
    total_duration_s: float = 0.0

    @property
    def all_tool_calls(self) -> list[dict]:
        """Flat list of all tool calls across turns (evaluator-compatible format)."""
        result = []
        for turn in self.turns:
            for tc in turn.tool_calls:
                result.append({
                    "name": tc.name,
                    "input": tc.input,
                    "output": tc.output,
                })
        return result

    @property
    def final_response(self) -> str:
        """Last turn's response text."""
        return self.turns[-1].response if self.turns else ""


class MockUploadedFile:
    """Mimics Streamlit UploadedFile interface for build_agent()."""

    def __init__(self, filepath: str):
        self.name = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            self._data = f.read()
        self.size = len(self._data)

    def getvalue(self) -> bytes:
        return self._data

    def read(self) -> bytes:
        return self._data

    def seek(self, pos: int):
        pass


def _extract_messages(node_output) -> list:
    """Extract messages from stream node output (handles Overwrite wrappers)."""
    if isinstance(node_output, Overwrite):
        node_output = node_output.value
    if isinstance(node_output, dict):
        messages = node_output.get("messages", [])
    else:
        return []
    if isinstance(messages, Overwrite):
        messages = messages.value
    if not isinstance(messages, (list, tuple)):
        return [messages] if messages else []
    return list(messages)


# Default timeout per scenario (seconds)
SCENARIO_TIMEOUT = int(os.environ.get("EVAL_SCENARIO_TIMEOUT", "180"))


def run_scenario(
    scenario: dict,
    fixtures_dir: str,
    sandbox_manager=None,
    timeout: int = SCENARIO_TIMEOUT,
) -> ScenarioResult:
    """Run a single evaluation scenario with timeout.

    Args:
        scenario: Scenario definition dict (from scenarios.py)
        fixtures_dir: Path to fixtures directory
        sandbox_manager: Optional pre-created SandboxManager (reused across scenarios)
        timeout: Max seconds per scenario (default 180s)

    Returns:
        ScenarioResult with all turns, tool calls, and timing.
    """
    from src.sandbox.manager import SandboxManager
    from src.agent.graph import build_agent

    name = scenario["name"]
    fixture_path = os.path.join(fixtures_dir, scenario["fixture"])
    queries = scenario["queries"]

    logger.info("═══ Scenario: %s (timeout=%ds) ═══", name, timeout)
    logger.info("Fixture: %s, Queries: %d", scenario["fixture"], len(queries))

    # Setup sandbox
    own_sandbox = sandbox_manager is None
    if own_sandbox:
        sandbox_manager = SandboxManager()

    result = ScenarioResult(name=name)
    t0 = time.time()

    def _run_inner():
        """Inner function that runs inside a thread with timeout."""
        # Create mock uploaded file
        mock_file = MockUploadedFile(fixture_path)
        uploaded_files = [mock_file]
        thread_id = f"eval_{name}_{int(time.time())}"

        # Build agent (no Streamlit dependency)
        agent, checkpointer, reset_fn = build_agent(
            sandbox_manager, thread_id, uploaded_files, queries[0]
        )

        # Upload fixture to sandbox
        sandbox_manager.wait_until_ready(timeout=60)
        sandbox_manager.upload_files(uploaded_files)
        logger.info("Fixture uploaded to sandbox")

        # Run each query turn
        for qi, query in enumerate(queries):
            turn_result = _run_turn(agent, reset_fn, query, thread_id, qi)
            result.turns.append(turn_result)
            logger.info(
                "Turn %d/%d: %d tool calls, %.1fs, response=%d chars",
                qi + 1, len(queries), len(turn_result.tool_calls),
                turn_result.duration_s, len(turn_result.response),
            )

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_inner)
            future.result(timeout=timeout)
    except FuturesTimeout:
        logger.error("Scenario %s TIMED OUT after %ds", name, timeout)
        result.turns.append(TurnResult(
            query=queries[0] if queries else "",
            error=f"Timeout after {timeout}s",
        ))
    except Exception as e:
        logger.error("Scenario %s failed: %s", name, e, exc_info=True)
        result.turns.append(TurnResult(
            query=queries[0] if queries else "",
            error=str(e),
        ))
    finally:
        result.total_duration_s = time.time() - t0
        # Clean workspace for next scenario (keep sandbox alive)
        if sandbox_manager:
            try:
                sandbox_manager.clean_workspace()
            except Exception:
                pass

        # Only stop if we created it
        if own_sandbox and sandbox_manager:
            sandbox_manager.stop()

    return result


def _run_turn(agent, reset_fn, query: str, thread_id: str, turn_idx: int) -> TurnResult:
    """Run a single conversation turn and collect tool calls + response."""
    reset_fn()
    turn = TurnResult(query=query)
    t0 = time.time()

    # Collect tool calls by ID for matching inputs to outputs
    pending_calls: dict[str, ToolCall] = {}

    try:
        for chunk in agent.stream(
            {"messages": [{"role": "user", "content": query}]},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode="updates",
        ):
            if not isinstance(chunk, dict):
                continue

            for _node_name, node_output in chunk.items():
                if _node_name == "__end__":
                    continue

                for msg in _extract_messages(node_output):
                    msg_type = getattr(msg, "type", None)

                    if msg_type == "ai":
                        # Collect tool call inputs
                        for tc in getattr(msg, "tool_calls", []):
                            call = ToolCall(
                                name=tc.get("name", "unknown"),
                                input=tc.get("args", {}),
                            )
                            call_id = tc.get("id")
                            if call_id:
                                pending_calls[call_id] = call
                            turn.tool_calls.append(call)

                        # Collect final text response
                        content = getattr(msg, "content", "")
                        if content and not getattr(msg, "tool_calls", []):
                            turn.response += content

                    elif msg_type == "tool":
                        # Match tool output to its call
                        tool_call_id = getattr(msg, "tool_call_id", None)
                        tool_content = getattr(msg, "content", "") or ""
                        if tool_call_id and tool_call_id in pending_calls:
                            pending_calls[tool_call_id].output = tool_content

    except GraphRecursionError:
        turn.error = "GraphRecursionError: max iterations reached"
        turn.response += "\n[EVAL: Agent hit recursion limit]"
    except Exception as e:
        turn.error = str(e)
        turn.response += f"\n[EVAL: Error - {e}]"

    turn.duration_s = time.time() - t0
    return turn
