"""Chat interface — streaming agent responses with Claude-style step timeline."""

from __future__ import annotations

import logging
import time

import streamlit as st
import streamlit.components.v1 as components
from langgraph.errors import GraphRecursionError
from langgraph.types import Overwrite

logger = logging.getLogger(__name__)

from src.agent.graph import get_or_build_agent
from src.tools.artifact_store import get_store
from src.ui.styles import get_tool_icon, get_tool_label


def _detect_step_name(code: str) -> str:
    """Detect step name from code content using priority-weighted scoring.

    When a single execute block does multiple things (e.g. analysis + PDF),
    the highest-priority detected operation wins.
    """
    code_lower = code.lower()

    # (priority, label, detector)  — higher priority wins
    _DETECTORS: list[tuple[int, str, bool]] = [
        # --- Artifact generation (highest priority — final output) ---
        (100, "📑 Generating PDF Report",
         'weasyprint' in code_lower or 'write_pdf' in code_lower
         or ('html' in code_lower and '.pdf' in code_lower)),

        (95, "🎞️ Creating Presentation",
         'pptx' in code_lower or 'Presentation' in code),

        # --- Dashboard data prep (JSON for generate_html) ---
        (90, "🎯 Preparing Dashboard Data",
         'json' in code_lower
         and any(x in code_lower for x in ['value_counts', 'groupby', 'chart', 'dashboard', 'kpi'])),

        # --- DuckDB (before generic analysis — more specific) ---
        (85, "🦆 Running Database Query",
         'duckdb' in code_lower or 'read_csv_auto' in code_lower),

        # --- Visualization ---
        (80, "📈 Creating Visualization",
         any(x in code_lower for x in ['matplotlib', 'plt.savefig', 'plt.show', 'plotly', 'seaborn', 'sns.'])),

        # --- Data loading + cleaning combo (very common first execute) ---
        (70, "📄 Loading & Cleaning Data",
         any(x in code_lower for x in ['read_excel', 'read_csv', 'read_parquet'])
         and any(x in code_lower for x in ['dropna', 'fillna', 'to_datetime', 'drop_duplicates'])),

        # --- Data loading only ---
        (65, "📄 Loading Data",
         any(x in code_lower for x in ['read_excel', 'read_csv', 'read_parquet'])),

        # --- Statistical analysis ---
        (60, "📊 Analyzing Data",
         any(x in code_lower for x in ['groupby', '.agg(', 'pivot_table', 'describe()', '.corr('])),

        # --- Data cleaning only ---
        (50, "🧹 Cleaning Data",
         any(x in code_lower for x in ['dropna', 'fillna', 'drop_duplicates', 'astype(', 'replace('])),

        # --- Date processing (only if to_datetime is explicit, not just an import) ---
        (45, "📅 Processing Dates",
         'to_datetime' in code_lower or 'dt.month' in code_lower or 'dt.year' in code_lower
         or 'resample(' in code_lower),

        # --- Schema discovery ---
        (40, "🔍 Exploring Schema",
         any(x in code_lower for x in ['.dtypes', '.info()', '.columns'])
         and 'read_' not in code_lower),

        # --- Excel writing ---
        (55, "💾 Saving Excel Output",
         'to_excel' in code_lower or 'excelwriter' in code_lower),
    ]

    best_priority = -1
    best_label = "⚙️ Processing"

    for priority, label, matched in _DETECTORS:
        if matched and priority > best_priority:
            best_priority = priority
            best_label = label

    return best_label


class ExecuteStatusManager:
    """Manages a single consolidated st.status() container for all execute tool calls with real-time updates."""

    def __init__(self):
        self._placeholder = None     # st.empty() placeholder for live updates
        self._step_count = 0         # Number of execute steps so far
        self._pending_call_ids = set()  # tool_call IDs waiting for results
        self._has_error = False      # Whether any step had an error
        self._steps_buffer = []      # Buffer of all steps for re-rendering
        self._current_step_name = "⚙️ Code Execution"  # Current step's detected name
        self._start_time = None      # Overall execution start time
        self._total_time = 0         # Total execution time in seconds

    @property
    def is_active(self) -> bool:
        """Whether the consolidated container is currently open."""
        return self._placeholder is not None

    def _render_current_state(self, state: str):
        """Re-render the entire status container with current buffer."""
        if self._placeholder is None:
            return

        # Determine label and spinner HTML based on state
        if state == "running":
            spinner_html = '<span class="rotating-spinner">⟳</span>'
            label_text = f"{self._current_step_name} (Step {self._step_count}/~{self._step_count + 2})"
            state_class = "status-running"
        else:
            # Completed state - no spinner
            icon = "❌" if self._has_error else "✅"
            spinner_html = icon
            time_str = f", {self._total_time:.1f}s" if self._total_time > 0 else ""
            label_text = f"Code Execution Complete ({self._step_count} steps{time_str})"
            state_class = "status-error" if self._has_error else "status-complete"

        # Use custom HTML for the header with rotating spinner
        with self._placeholder.container():
            # Render custom status header
            st.markdown(f"""
            <div class="execute-status-container {state_class}">
                <div class="execute-status-header">
                    {spinner_html} {label_text}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Render collapsible details with st.expander
            with st.expander("📋 View execution details", expanded=False):
                for step_data in self._steps_buffer:
                    step_name = step_data.get('step_name', 'Code Execution')
                    duration = step_data.get('duration', 0)
                    duration_str = f"  ({duration:.1f}s)" if duration > 0 else ""

                    st.markdown(f"**Step {step_data['num']} · {step_name}**{duration_str}")
                    st.code(step_data['code'], language="python")

                    if step_data.get('output'):
                        output = step_data['output']
                        is_error = step_data.get('is_error', False)
                        output_label = f"📤 Output" + (" ❌" if is_error else "")

                        with st.expander(output_label, expanded=is_error):
                            if is_error:
                                st.error(output[:2000])
                            else:
                                st.text(output[:2000])

    def add_execute_call(self, tool_call_id: str, code: str):
        """Called when an AI message contains an execute tool_call."""
        self._step_count += 1
        self._pending_call_ids.add(tool_call_id)

        # Detect step name from code
        step_name = _detect_step_name(code)
        self._current_step_name = step_name

        if self._placeholder is None:
            # First execute call - create placeholder
            self._placeholder = st.empty()
            self._start_time = time.time()

        # Add step to buffer with detected name and start time
        self._steps_buffer.append({
            'num': self._step_count,
            'code': code,
            'tool_call_id': tool_call_id,
            'output': None,
            'is_error': False,
            'step_name': step_name,
            'start_time': time.time(),
            'duration': 0,
        })

        # Re-render with running state
        self._render_current_state("running")

    def add_execute_result(self, tool_call_id: str, content: str):
        """Called when a tool message with execute result arrives."""
        self._pending_call_ids.discard(tool_call_id)

        if self._placeholder is None:
            return

        is_error = "error" in content.lower() or "traceback" in content.lower()
        if is_error:
            self._has_error = True

        # Find step in buffer and add output with duration
        for step_data in self._steps_buffer:
            if step_data['tool_call_id'] == tool_call_id:
                step_data['output'] = content
                step_data['is_error'] = is_error
                # Calculate duration
                if step_data.get('start_time'):
                    step_data['duration'] = time.time() - step_data['start_time']
                break

        # Re-render with running state (more steps may come)
        self._render_current_state("running")

    def finalize(self):
        """Close the container and switch to complete state."""
        if self._placeholder is None:
            return

        # Calculate total time
        if self._start_time:
            self._total_time = time.time() - self._start_time

        # Final render — if last step succeeded, agent corrected any earlier errors
        last_step_error = self._steps_buffer[-1].get('is_error', False) if self._steps_buffer else False
        final_state = "error" if last_step_error else "complete"
        self._render_current_state(final_state)

        # Reset for potential future use
        self._placeholder = None
        self._step_count = 0
        self._pending_call_ids.clear()
        self._has_error = False
        self._steps_buffer = []
        self._start_time = None
        self._total_time = 0


def _safe_extract_messages(node_output) -> list:
    """Safely extract messages from a stream node output.

    Handles: dict with 'messages' key, Overwrite wrappers, non-iterable values.
    """
    if isinstance(node_output, Overwrite):
        node_output = node_output.value

    if isinstance(node_output, dict):
        messages = node_output.get("messages", [])
    else:
        return []

    # messages itself might be an Overwrite
    if isinstance(messages, Overwrite):
        messages = messages.value

    if not isinstance(messages, (list, tuple)):
        return [messages] if messages else []

    return list(messages)


def _render_execute_history(execute_steps: list[dict]):
    """Render a consolidated block for execute steps from history."""
    n = len(execute_steps)
    # Check last step only — if agent corrected earlier errors, final result is success
    last_output = execute_steps[-1].get("output", "") if execute_steps else ""
    last_step_error = last_output and ("error" in last_output.lower() or "traceback" in last_output.lower())
    icon = "❌" if last_step_error else "✅"
    step_word = "steps" if n != 1 else "step"
    state_class = "status-error" if last_step_error else "status-complete"

    # Render custom status header for history
    st.markdown(f"""
    <div class="execute-status-container {state_class}">
        <div class="execute-status-header">
            {icon} Code Execution Complete ({n} {step_word})
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Render collapsible details
    with st.expander("📋 View execution details", expanded=False):
        for i, step in enumerate(execute_steps, 1):
            code = step["input"].get("command", "") or step["input"].get("code", "")

            # Detect step name from code
            step_name = _detect_step_name(code) if code else "Code Execution"

            if code:
                st.markdown(f"**Step {i} · {step_name}**")
                st.code(code, language="python")

            output = step.get("output")
            if output:
                # Skip blocked messages
                _blocked_markers = ("⛔", "BLOCKED", "already parsed", "not needed",
                                    "Execute limit reached", "Shell command")
                if any(m in output for m in _blocked_markers):
                    continue

                is_error = "error" in output.lower() or "traceback" in output.lower()
                with st.expander(f"📤 Output" + (" ❌" if is_error else ""), expanded=is_error):
                    if is_error:
                        st.error(output[:2000])
                    else:
                        st.text(output[:2000])


def _render_tool_call(tool_name: str, tool_input: dict, tool_output: str | None = None):
    """Render a single tool call as a Claude-style collapsible block."""
    icon = get_tool_icon(tool_name)
    label = get_tool_label(tool_name)

    with st.status(f"{icon} {label}", state="complete"):
        # Show tool input
        if tool_name in ("execute", "create_visualization"):
            code = tool_input.get("command", "") or tool_input.get("code", "")
            if code:
                st.code(code, language="python")
        elif tool_name == "generate_html":
            html_code = tool_input.get("html_code", "")
            if html_code:
                with st.expander("Show HTML"):
                    st.code(html_code[:2000], language="html")
        elif tool_name == "parse_file":
            filename = tool_input.get("filename", "")
            st.markdown(f"**File:** `{filename}`")
        elif tool_name == "download_file":
            file_path = tool_input.get("file_path", "")
            st.markdown(f"**Preparing download:** `{file_path}`")
        else:
            # Generic tool input display
            if tool_input:
                st.json(tool_input)

        # Show tool output (with expander for execute/parse_file)
        if tool_output:
            # Skip blocked messages (they're shown as warnings in stream)
            _blocked_markers = ("⛔", "BLOCKED", "already parsed", "not needed",
                                "Execute limit reached", "Shell command")
            if any(m in tool_output for m in _blocked_markers):
                return  # Don't show blocked output in history

            # Show execute output in expander
            if tool_name == "execute":
                with st.expander("📤 Execute Output", expanded=False):
                    if "error" in tool_output.lower() or "traceback" in tool_output.lower():
                        st.error(tool_output[:2000])
                    else:
                        st.text(tool_output[:2000])

            # Show parse_file output in expander
            elif tool_name == "parse_file":
                with st.expander("📋 Schema Info", expanded=False):
                    st.text(tool_output[:2000])

            # Other tool outputs (fallback)
            else:
                if "error" in tool_output.lower():
                    st.error(tool_output[:1000])
                else:
                    st.text(tool_output[:2000])


def _get_mime(filename: str) -> str:
    """Get MIME type from filename extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
        "png": "image/png",
        "json": "application/json",
        "txt": "text/plain",
    }.get(ext, "application/octet-stream")


def _render_artifacts(html_list, charts_list, downloads_list, key_prefix=""):
    """Render artifacts (HTML, charts, downloads) in the Streamlit UI."""
    for i, html in enumerate(html_list):
        height = st.session_state.get("html_render_height", 600)
        components.html(html, height=height, scrolling=True)

    for i, chart in enumerate(charts_list):
        chart_bytes = chart.get("bytes")
        code = chart.get("code", "")
        if chart_bytes:
            st.image(chart_bytes, use_container_width=True)
            if code:
                with st.expander("Show code"):
                    st.code(code, language="python")

    for i, dl in enumerate(downloads_list):
        file_bytes = dl.get("bytes")
        filename = dl.get("filename", "file")
        if file_bytes:
            st.download_button(
                label=f"📥 {filename} indir",
                data=file_bytes,
                file_name=filename,
                mime=_get_mime(filename),
                key=f"dl_{key_prefix}{filename}_{i}",
            )


def _process_stream_chunk(chunk, rendered_ids: set, exec_manager: ExecuteStatusManager):
    """Process a single stream chunk and render appropriate UI elements.

    Args:
        chunk: Stream chunk from LangGraph
        rendered_ids: Set of message IDs already rendered (prevents history replay)
        exec_manager: Manager for consolidated execute status container
    """
    if not isinstance(chunk, dict):
        return
    for node_name, node_output in chunk.items():
        if node_name == "__end__":
            continue

        messages = _safe_extract_messages(node_output)
        for msg in messages:
            # Dedup: Skip messages already rendered (prevents old turns from replaying)
            msg_id = getattr(msg, "id", None)
            if msg_id and msg_id in rendered_ids:
                continue
            if msg_id:
                rendered_ids.add(msg_id)

            msg_type = getattr(msg, "type", None)

            # AI message — stream text content
            if msg_type == "ai":
                content = getattr(msg, "content", "")
                tool_calls = getattr(msg, "tool_calls", [])

                # Render thinking/reasoning if present
                thinking = getattr(msg, "additional_kwargs", {}).get("thinking", "")
                if thinking:
                    with st.expander("💭 Thinking...", expanded=False):
                        st.markdown(thinking)

                # Render tool calls
                for tc in tool_calls:
                    tool_name = tc.get("name", "unknown")
                    tool_input = tc.get("args", {})
                    tool_call_id = tc.get("id")

                    if tool_name == "execute":
                        # Route execute calls to consolidated manager
                        code = tool_input.get("command", "") or tool_input.get("code", "")
                        if code and tool_call_id:
                            exec_manager.add_execute_call(tool_call_id, code)
                    else:
                        # Non-execute tool: finalize any open execute container first
                        exec_manager.finalize()
                        _render_tool_call(tool_name=tool_name, tool_input=tool_input)

                # Render text content (final answer)
                if content and not tool_calls:
                    # Finalize execute container before showing final answer
                    exec_manager.finalize()
                    st.markdown(content)

            # Tool message — tool output
            elif msg_type == "tool":
                tool_name = getattr(msg, "name", "")
                tool_content = getattr(msg, "content", "") or ""
                tool_call_id = getattr(msg, "tool_call_id", None)

                # Blocked tool calls: agent already gets feedback via ToolMessage.
                # Don't show internal interceptor messages to the user.
                _blocked_markers = ("⛔", "BLOCKED", "already parsed", "not needed",
                                    "Execute limit reached", "Shell command")
                if any(m in tool_content for m in _blocked_markers):
                    logger.debug("Interceptor block (hidden from UI): %s", tool_content[:200])
                    continue

                # Route execute results to consolidated manager
                if tool_name == "execute" and tool_content and tool_call_id:
                    exec_manager.add_execute_result(tool_call_id, tool_content)

                # parse_file output (schema info)
                elif tool_name == "parse_file" and tool_content:
                    with st.expander("📋 Schema Info", expanded=False):
                        st.text(tool_content[:2000])

                # Artifacts are collected and rendered after stream completes


def render_chat():
    """Render the chat interface with message history and streaming responses."""
    # Display message history
    messages = st.session_state.get("messages", [])
    logger.info(f"[UI] Rendering {len(messages)} messages from history")
    for i, msg in enumerate(messages):
        role = msg["role"]
        content = msg["content"]

        with st.chat_message(role):
            # Re-render stored tool call steps (consolidating consecutive execute steps)
            steps = msg.get("steps", [])
            execute_buffer = []

            for step in steps:
                if step["name"] == "execute":
                    # Buffer execute steps for consolidation
                    execute_buffer.append(step)
                else:
                    # Flush any accumulated execute steps
                    if execute_buffer:
                        _render_execute_history(execute_buffer)
                        execute_buffer = []
                    # Render non-execute step individually
                    _render_tool_call(
                        tool_name=step["name"],
                        tool_input=step["input"],
                        tool_output=step.get("output"),
                    )

            # Flush remaining execute steps
            if execute_buffer:
                _render_execute_history(execute_buffer)

            if content:
                st.markdown(content)

            # Re-render stored artifacts (including downloads)
            artifacts = msg.get("artifacts", {})
            _render_artifacts(
                artifacts.get("html", []),
                artifacts.get("charts", []),
                artifacts.get("downloads", []),
                key_prefix=f"hist_{i}_",
            )

    # Chat input
    user_query = st.chat_input("Ask a question about your data...")
    if not user_query:
        return

    # Display user message
    with st.chat_message("user"):
        st.markdown(user_query)

    # Store user message
    st.session_state["messages"].append({"role": "user", "content": user_query})
    logger.info(f"[UI] Saved user message to history. Total messages: {len(st.session_state['messages'])}")

    # Get sandbox manager and session ID
    sandbox_manager = st.session_state.get("sandbox_manager")
    session_id = st.session_state.get("session_id", "default")
    uploaded_files = st.session_state.get("uploaded_files", [])

    if not sandbox_manager:
        st.error("Sandbox manager not initialized. Please refresh the page.")
        return

    # Build or retrieve cached agent
    try:
        agent, checkpointer, reset_fn = get_or_build_agent(
            sandbox_manager, session_id, uploaded_files, user_query
        )
    except Exception as e:
        logger.error("Agent build failed: %s", e, exc_info=True)
        st.error(f"Agent oluşturulamadı: {e}")
        return

    # Block until OpenSandbox is ready (prevents race condition)
    # Timeout is generous for first-ever sandbox (pip install), fast for reuse
    with st.spinner("⏳ Sandbox hazırlanıyor..."):
        ready = sandbox_manager.wait_until_ready(timeout=180)
        if not ready:
            # STOP - cannot continue without packages
            st.error("❌ Sandbox hazırlığı tamamlanamadı (180s timeout).\n\n"
                     "**Sebep:** Paketler yüklenemedi veya sandbox yanıt vermiyor.\n\n"
                     "**Çözüm:** 'Yeni Konuşma' ile oturumu sıfırlayın.")
            return
    # Upload files to sandbox (once per file set, after sandbox is ready)
    uploaded_fingerprint = tuple(f.name for f in uploaded_files) if uploaded_files else ()
    if uploaded_files and uploaded_fingerprint != st.session_state.get("_files_uploaded"):
        try:
            sandbox_manager.upload_files(uploaded_files)
            st.session_state["_files_uploaded"] = uploaded_fingerprint
            logger.info("Uploaded %d files to sandbox", len(uploaded_files))
        except Exception as e:
            logger.error("Failed to upload files to sandbox: %s", e, exc_info=True)
            st.warning(f"⚠️ Dosya yüklenemedi: {e}")
            return

    # Reset interceptor counters for new conversation turn
    # (prevents _execute_count leak from previous user messages)
    reset_fn()

    # Stream agent response
    with st.chat_message("assistant"):
        full_response = ""
        collected_steps = []  # Persist tool call steps for history
        exec_manager = ExecuteStatusManager()  # Consolidated execute container manager

        # Track rendered message IDs (persist across queries in same session)
        if "_rendered_ids" not in st.session_state:
            st.session_state["_rendered_ids"] = set()
        rendered_ids = st.session_state["_rendered_ids"]

        try:
            for chunk in agent.stream(
                {"messages": [{"role": "user", "content": user_query}]},
                config={"configurable": {"thread_id": session_id}},
                stream_mode="updates",
            ):
                _process_stream_chunk(chunk, rendered_ids, exec_manager)

                # Collect tool calls + outputs for message history
                # NOTE: No dedup here - we want ALL messages from current turn for persistence
                if not isinstance(chunk, dict):
                    continue
                for _node_name, node_output in chunk.items():
                    for msg in _safe_extract_messages(node_output):
                        msg_type = getattr(msg, "type", None)

                        # AI message: collect tool calls (inputs)
                        if msg_type == "ai":
                            for tc in getattr(msg, "tool_calls", []):
                                collected_steps.append({
                                    "name": tc.get("name", "unknown"),
                                    "input": tc.get("args", {}),
                                    "call_id": tc.get("id"),  # For matching with tool output
                                    "output": None,  # Will be filled by tool message
                                })
                            content = getattr(msg, "content", "")
                            if content and not getattr(msg, "tool_calls", []):
                                full_response += content

                        # Tool message: collect tool output and match with tool call
                        elif msg_type == "tool":
                            tool_call_id = getattr(msg, "tool_call_id", None)
                            tool_content = getattr(msg, "content", "") or ""

                            # Find matching tool call in collected_steps and add output
                            if tool_call_id:
                                for step in collected_steps:
                                    if step.get("call_id") == tool_call_id:
                                        step["output"] = tool_content
                                        break

            # Finalize any open execute container after stream completes
            exec_manager.finalize()

        except GraphRecursionError:
            exec_manager.finalize()  # Close execute container before showing error
            st.warning(
                "⚠️ Agent maksimum adım sayısına ulaştı (30 iterasyon). "
                "Soruyu daha spesifik sormayı dene veya daha küçük bir veri seti yükle."
            )
            full_response = (
                "Analiz tamamlanamadı — maksimum adım sayısına ulaşıldı. "
                "Lütfen soruyu daraltmayı deneyin."
            )
        except Exception as e:
            exec_manager.finalize()  # Close execute container before showing error
            st.error(f"Agent hatası: {e}")
            full_response = f"Bir hata oluştu: {e}"

        # Collect all artifacts that accumulated during streaming
        _store = get_store(session_id)
        collected_html = _store.pop_html()
        collected_charts = _store.pop_charts()
        collected_downloads = _store.pop_downloads()

        # Render them now (after stream is done, so they persist)
        _render_artifacts(collected_html, collected_charts, collected_downloads, key_prefix="new_")

    # Store assistant message with steps + artifacts
    st.session_state["messages"].append({
        "role": "assistant",
        "content": full_response,
        "steps": collected_steps,
        "artifacts": {
            "html": collected_html,
            "charts": collected_charts,
            "downloads": collected_downloads,
        },
    })
    logger.info(f"[UI] Saved assistant message to history. Total messages: {len(st.session_state['messages'])}, Steps: {len(collected_steps)}")
