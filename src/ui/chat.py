"""Chat interface — streaming agent responses with Claude-style step timeline."""

from __future__ import annotations

import logging

import streamlit as st
import streamlit.components.v1 as components
from langgraph.errors import GraphRecursionError
from langgraph.types import Overwrite

logger = logging.getLogger(__name__)

from src.agent.graph import get_or_build_agent
from src.tools.artifact_store import get_store
from src.ui.styles import get_tool_icon, get_tool_label


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

        # Show tool output
        if tool_output:
            if "error" in str(tool_output).lower():
                st.error(str(tool_output)[:1000])
            else:
                st.text(str(tool_output)[:2000])


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


def _process_stream_chunk(chunk, rendered_ids: set):
    """Process a single stream chunk and render appropriate UI elements.

    Args:
        chunk: Stream chunk from LangGraph
        rendered_ids: Set of message IDs already rendered (prevents history replay)
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

            # DEBUG: Log message ID info
            logger.info(f"[UI] Processing message: type={getattr(msg, 'type', None)}, id={msg_id}, already_seen={msg_id in rendered_ids if msg_id else 'N/A'}")

            if msg_id and msg_id in rendered_ids:
                logger.info(f"[UI] SKIPPED duplicate message ID: {msg_id}")
                continue
            if msg_id:
                rendered_ids.add(msg_id)
                logger.info(f"[UI] Added message ID to rendered set: {msg_id}")

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
                    _render_tool_call(
                        tool_name=tc.get("name", "unknown"),
                        tool_input=tc.get("args", {}),
                    )

                # Render text content (final answer)
                if content and not tool_calls:
                    st.markdown(content)

            # Tool message — tool output
            elif msg_type == "tool":
                tool_name = getattr(msg, "name", "")
                tool_content = getattr(msg, "content", "") or ""

                # Show blocked tool calls as warnings in the UI
                _blocked_markers = ("⛔", "BLOCKED", "already parsed", "not needed",
                                    "Execute limit reached", "Shell command")
                if any(m in tool_content for m in _blocked_markers):
                    st.warning(f"🚫 Bloklandı: {tool_content[:200]}")
                    continue

                # Show successful execute output (for debugging/verification)
                if tool_name == "execute" and tool_content:
                    with st.expander("📤 Execute Output", expanded=False):
                        if "error" in tool_content.lower() or "traceback" in tool_content.lower():
                            st.error(tool_content[:2000])
                        else:
                            st.text(tool_content[:2000])

                # parse_file output (schema info)
                elif tool_name == "parse_file" and tool_content:
                    with st.expander("📋 Schema Info", expanded=False):
                        st.text(tool_content[:2000])

                # Artifacts are collected and rendered after stream completes


def render_chat():
    """Render the chat interface with message history and streaming responses."""
    # Display message history
    for i, msg in enumerate(st.session_state.get("messages", [])):
        role = msg["role"]
        content = msg["content"]

        with st.chat_message(role):
            # Re-render stored tool call steps
            for step in msg.get("steps", []):
                _render_tool_call(
                    tool_name=step["name"],
                    tool_input=step["input"],
                )

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

    # Block until Daytona sandbox packages are installed (prevents race condition)
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
                _process_stream_chunk(chunk, rendered_ids)

                # Collect tool calls + text for message history (skip already-seen messages)
                if not isinstance(chunk, dict):
                    continue
                for _node_name, node_output in chunk.items():
                    for msg in _safe_extract_messages(node_output):
                        # Skip messages already rendered (same dedup logic as _process_stream_chunk)
                        msg_id = getattr(msg, "id", None)
                        if msg_id and msg_id in rendered_ids:
                            continue  # Already processed in _process_stream_chunk

                        if getattr(msg, "type", None) == "ai":
                            for tc in getattr(msg, "tool_calls", []):
                                collected_steps.append({
                                    "name": tc.get("name", "unknown"),
                                    "input": tc.get("args", {}),
                                })
                            content = getattr(msg, "content", "")
                            if content and not getattr(msg, "tool_calls", []):
                                full_response += content

        except GraphRecursionError:
            st.warning(
                "⚠️ Agent maksimum adım sayısına ulaştı (30 iterasyon). "
                "Soruyu daha spesifik sormayı dene veya daha küçük bir veri seti yükle."
            )
            full_response = (
                "Analiz tamamlanamadı — maksimum adım sayısına ulaşıldı. "
                "Lütfen soruyu daraltmayı deneyin."
            )
        except Exception as e:
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
