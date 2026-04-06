"""Sidebar UI — file upload widget, file list, new conversation button."""

from __future__ import annotations

import html as html_mod

import streamlit as st

from src.storage.db import delete_conversation, list_conversations, load_files, load_messages, save_files
from src.ui.session import MockUploadedFile, reset_session

FILE_TYPE_ICONS = {
    ".csv": "📊",
    ".tsv": "📊",
    ".xlsx": "📗",
    ".xls": "📗",
    ".xlsm": "📗",
    ".json": "📋",
    ".pdf": "📕",
}


def _get_file_icon(filename: str) -> str:
    """Get emoji icon based on file extension."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return FILE_TYPE_ICONS.get(ext, "📄")


def _format_size(size_bytes: int) -> str:
    """Format file size to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def render_sidebar():
    """Render the sidebar with file upload, file list, and controls."""
    with st.sidebar:
        st.markdown("### 📁 Data Analysis Agent")
        st.caption("Upload files and ask questions about your data")

        st.divider()

        # File upload widget
        uploader_key = st.session_state.get("uploader_key", "file_uploader")
        uploaded = st.file_uploader(
            "Upload files",
            type=["csv", "xlsx", "xls", "xlsm", "json", "pdf", "tsv"],
            accept_multiple_files=True,
            key=uploader_key,
            help="Supported: CSV, Excel, JSON, PDF",
        )

        # Sync uploaded files to session state (upload to sandbox happens in chat.py)
        if uploaded:
            st.session_state["uploaded_files"] = uploaded
            # Save to DB immediately so they survive page refresh
            _sid = st.session_state.get("session_id", "")
            if _sid:
                save_files(_sid, uploaded)

        # Show uploaded file list with download buttons
        files = st.session_state.get("uploaded_files", [])
        if files:
            st.markdown("**Uploaded files:**")
            for i, f in enumerate(files):
                icon = _get_file_icon(f.name)
                size = _format_size(f.size)
                col1, col2 = st.columns([4, 1])
                with col1:
                    safe_name = html_mod.escape(f.name)
                    st.markdown(
                        f'<div class="file-badge">{icon} {safe_name} ({size})</div>',
                        unsafe_allow_html=True,
                    )
                with col2:
                    st.download_button(
                        label="⬇️",
                        data=f.getvalue(),
                        file_name=f.name,
                        key=f"dl_upload_{i}_{f.name}",
                        help=f"{f.name} indir",
                    )

        st.divider()

        # New conversation button
        if st.button("🔄 New Conversation", use_container_width=True):
            reset_session()
            st.rerun()

        # --- Conversation history ---
        user_id = st.session_state.get("user_id", "")
        if user_id:
            conversations = list_conversations(user_id)
            current_sid = st.session_state.get("session_id", "")

            # Filter out empty/current conversations that have no messages yet
            past = [c for c in conversations if c["session_id"] != current_sid]

            if past:
                st.divider()
                st.markdown("**🕓 Geçmiş Konuşmalar**")
                for conv in past:
                    title = conv["title"] or "Yeni Konuşma"
                    updated = conv["updated_at"][:16].replace("T", " ") if conv["updated_at"] else ""
                    col1, col2 = st.columns([5, 1])
                    with col1:
                        label = f"{title[:30]}…" if len(title) > 30 else title
                        if st.button(label, key=f"load_{conv['session_id']}", use_container_width=True,
                                     help=f"{title}\n{updated}"):
                            # Load selected conversation messages
                            msgs = load_messages(conv["session_id"])
                            st.session_state["messages"] = msgs
                            st.session_state["session_id"] = conv["session_id"]
                            st.session_state.pop("_agent_cache", None)
                            st.session_state.pop("_rendered_ids", None)
                            st.session_state.pop("_files_uploaded", None)
                            # Restore files for this conversation
                            saved_files = load_files(conv["session_id"])
                            if saved_files:
                                st.session_state["uploaded_files"] = [
                                    MockUploadedFile(f["name"], f["size"], f["data"])
                                    for f in saved_files
                                ]
                            else:
                                st.session_state["uploaded_files"] = []
                            st.toast(f"✅ Konuşma yüklendi: {title[:40]}", icon="📂")
                            st.rerun()
                    with col2:
                        if st.button("🗑️", key=f"del_{conv['session_id']}",
                                     help="Konuşmayı sil"):
                            delete_conversation(conv["session_id"])
                            st.rerun()

        # Model info
        st.divider()
        st.caption("**Model:** Claude Sonnet 4")
        st.caption("**Sandbox:** OpenSandbox")
