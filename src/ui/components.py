"""Sidebar UI — file upload widget, file list, new conversation button."""

from __future__ import annotations

import html as html_mod

import streamlit as st

from src.ui.session import reset_session

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

        # Show uploaded file list
        files = st.session_state.get("uploaded_files", [])
        if files:
            st.markdown("**Uploaded files:**")
            for f in files:
                icon = _get_file_icon(f.name)
                size = _format_size(f.size)
                safe_name = html_mod.escape(f.name)
                st.markdown(
                    f'<div class="file-badge">{icon} {safe_name} ({size})</div>',
                    unsafe_allow_html=True,
                )

        st.divider()

        # New conversation button
        if st.button("🔄 New Conversation", use_container_width=True):
            reset_session()
            st.rerun()

        # Model info
        st.divider()
        st.caption("**Model:** Claude Sonnet 4")
        st.caption("**Sandbox:** OpenSandbox")
