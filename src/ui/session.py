"""Session state initialization — sandbox pre-warm, atexit cleanup."""

import atexit
import logging
import threading
import uuid

import streamlit as st

from src.sandbox.manager import SandboxManager
from src.tools.artifact_store import release_store

logger = logging.getLogger(__name__)


def init_session():
    """Initialize Streamlit session state with all required keys.

    - Creates SandboxManager and pre-warms Daytona sandbox in background thread
    - Registers atexit cleanup for sandbox stop
    - Sets up unique session_id for thread-based sandbox + checkpointer
    """
    # Core state
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("uploaded_files", [])
    st.session_state.setdefault("step_history", [])

    # Pending artifacts from tool calls (consumed by chat renderer)
    st.session_state.setdefault("pending_html", [])
    st.session_state.setdefault("pending_charts", [])

    # Generate unique session/thread ID for Daytona sandbox + checkpointer
    st.session_state.setdefault("session_id", str(uuid.uuid4()))

    # Default HTML render height (Risk #3 fallback)
    st.session_state.setdefault("html_render_height", 600)

    # Create sandbox manager (once per session)
    if "sandbox_manager" not in st.session_state:
        st.session_state["sandbox_manager"] = SandboxManager()

    # Pre-warm Daytona sandbox in background thread (Risk #2)
    if "sandbox_prewarm_done" not in st.session_state:
        st.session_state["sandbox_prewarm_done"] = True  # Set immediately to prevent re-entry

        # Capture values before spawning thread to avoid ScriptRunContext warning
        _mgr = st.session_state.get("sandbox_manager")
        _thread_id = st.session_state.get("session_id")

        def _prewarm(mgr, thread_id):
            try:
                if mgr and thread_id:
                    mgr.get_or_create_sandbox(thread_id)
                    logger.info("Sandbox pre-warm complete for %s", thread_id)
            except Exception as e:
                logger.warning("Sandbox pre-warm failed: %s", e)
                st.session_state["sandbox_prewarm_error"] = str(e)

        threading.Thread(
            target=_prewarm, args=(_mgr, _thread_id), daemon=True
        ).start()

    # Register atexit cleanup to stop sandbox on session end
    # Primary cleanup: Daytona auto_delete_interval=3600
    # atexit is best-effort only — not guaranteed in Streamlit
    if "sandbox_cleanup_registered" not in st.session_state:
        st.session_state["sandbox_cleanup_registered"] = True
        mgr = st.session_state.get("sandbox_manager")
        if mgr:
            atexit.register(mgr.stop)


def reset_session():
    """Reset conversation state for a new chat.

    REUSES the existing sandbox (packages stay installed) — only cleans user files.
    This avoids 2-4 min pip install on every new conversation.
    """
    # Release artifact store for old session
    old_session_id = st.session_state.get("session_id", "")
    if old_session_id:
        release_store(old_session_id)

    st.session_state["messages"] = []
    st.session_state["step_history"] = []
    st.session_state["uploaded_files"] = []
    st.session_state["pending_html"] = []
    st.session_state["pending_charts"] = []
    # Generate new session ID for fresh conversation thread
    st.session_state["session_id"] = str(uuid.uuid4())
    # Reset file uploader widget key so it clears
    st.session_state["uploader_key"] = str(uuid.uuid4())
    # Clear agent cache so it rebuilds with new session context
    st.session_state.pop("_agent_cache", None)
    # Clear file upload fingerprint so files are re-uploaded
    st.session_state.pop("_files_uploaded", None)
    st.session_state.pop("sandbox_prewarm_error", None)

    # REUSE sandbox — clean workspace files but keep packages installed
    mgr = st.session_state.get("sandbox_manager")
    if mgr:
        mgr.clean_workspace()
        logger.info("Session reset: sandbox reused, workspace cleaned")
