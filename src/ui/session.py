"""Session state initialization — sandbox pre-warm, atexit cleanup."""

import atexit
import logging
import threading
import uuid

import streamlit as st

from src.sandbox.manager import SandboxManager
from src.storage.db import create_conversation, load_files, load_messages, save_message
from src.tools.artifact_store import release_store


class MockUploadedFile:
    """Mimics Streamlit's UploadedFile interface for DB-restored files."""

    def __init__(self, name: str, size: int, data: bytes):
        self.name = name
        self.size = size
        self._data = data

    def getvalue(self) -> bytes:
        return self._data

    def read(self) -> bytes:
        return self._data

logger = logging.getLogger(__name__)


def init_session():
    """Initialize Streamlit session state with all required keys.

    - Creates SandboxManager and pre-warms OpenSandbox in background thread
    - Registers atexit cleanup for sandbox stop
    - Sets up unique session_id for thread-based sandbox + checkpointer
    """
    # --- User identification via URL query param (persists across F5) ---
    if "user_id" not in st.session_state:
        uid = st.query_params.get("uid", "")
        if not uid:
            uid = str(uuid.uuid4())
            st.query_params["uid"] = uid
        st.session_state["user_id"] = uid

    # Core state
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("uploaded_files", [])
    st.session_state.setdefault("step_history", [])

    # Pending artifacts from tool calls (consumed by chat renderer)
    st.session_state.setdefault("pending_html", [])
    st.session_state.setdefault("pending_charts", [])

    # Generate unique session/thread ID for OpenSandbox + checkpointer
    st.session_state.setdefault("session_id", str(uuid.uuid4()))

    # Register conversation in DB (idempotent — INSERT OR IGNORE)
    if "db_conversation_created" not in st.session_state:
        st.session_state["db_conversation_created"] = True
        create_conversation(
            session_id=st.session_state["session_id"],
            user_id=st.session_state["user_id"],
        )

    # Restore uploaded files from DB if session state is empty
    if not st.session_state.get("uploaded_files"):
        _sid = st.session_state.get("session_id", "")
        if _sid:
            saved = load_files(_sid)
            if saved:
                st.session_state["uploaded_files"] = [
                    MockUploadedFile(f["name"], f["size"], f["data"]) for f in saved
                ]
                logger.info("Restored %d file(s) from DB for session %s", len(saved), _sid)

    # Default HTML render height (Risk #3 fallback)
    st.session_state.setdefault("html_render_height", 600)

    # Create sandbox manager (once per session)
    if "sandbox_manager" not in st.session_state:
        st.session_state["sandbox_manager"] = SandboxManager()

    # Pre-warm OpenSandbox in background thread (Risk #2)
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
    # Primary cleanup: OpenSandbox sandbox timeout=2h
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
    new_session_id = str(uuid.uuid4())
    st.session_state["session_id"] = new_session_id

    # Register fresh conversation in DB
    user_id = st.session_state.get("user_id", "unknown")
    create_conversation(session_id=new_session_id, user_id=user_id)
    st.session_state["db_conversation_created"] = True
    # Reset file uploader widget key so it clears
    st.session_state["uploader_key"] = str(uuid.uuid4())
    # Clear agent cache so it rebuilds with new session context
    st.session_state.pop("_agent_cache", None)
    # Clear file upload fingerprint so files are re-uploaded
    st.session_state.pop("_files_uploaded", None)
    st.session_state.pop("sandbox_prewarm_error", None)
    # Clear rendered message IDs so history doesn't replay
    st.session_state.pop("_rendered_ids", None)

    # REUSE sandbox — clean workspace files but keep packages installed
    mgr = st.session_state.get("sandbox_manager")
    if mgr:
        mgr.clean_workspace()
        logger.info("Session reset: sandbox reused, workspace cleaned")
