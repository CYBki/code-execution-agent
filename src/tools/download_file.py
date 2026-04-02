"""Download file tool — fetch a file from OpenSandbox and offer as Streamlit download."""

from __future__ import annotations

import logging
import os

from langchain_core.tools import tool
from src.sandbox.manager import OpenSandboxBackend, SANDBOX_HOME

from src.tools.artifact_store import get_store

logger = logging.getLogger(__name__)


def make_download_file_tool(backend: OpenSandboxBackend, session_id: str = ""):
    """Factory: create the download_file tool bound to an OpenSandbox backend."""

    @tool
    def download_file(file_path: str) -> str:
        """Make a file from the sandbox available for the user to download.

        Use this AFTER generating a file (PDF report, Excel output, CSV export, etc.)
        in the sandbox. The file will appear as a download button in the chat.

        Args:
            file_path: Absolute path to the file in the sandbox, e.g. '/home/sandbox/report.pdf'
        """
        ALLOWED_PREFIX = SANDBOX_HOME + "/"
        if not file_path.startswith(ALLOWED_PREFIX):
            return f"❌ Only files under {ALLOWED_PREFIX} can be downloaded."

        filename = os.path.basename(file_path)

        try:
            responses = backend.download_files([file_path])
            resp = responses[0] if responses and len(responses) > 0 else None

            if resp and resp.content and not getattr(resp, "error", None):
                MAX_DOWNLOAD_MB = 50
                if len(resp.content) > MAX_DOWNLOAD_MB * 1024 * 1024:
                    return f"❌ File too large ({len(resp.content) // 1024 // 1024}MB). Max {MAX_DOWNLOAD_MB}MB."
                # Thread-safe per-session store — no st.session_state access from agent thread
                get_store(session_id).add_download(resp.content, filename, file_path)
                size_kb = len(resp.content) / 1024
                logger.info("File ready for download: %s (%.1f KB)", filename, size_kb)
                return f"✅ '{filename}' ready for download ({size_kb:.1f} KB)."
            else:
                error_info = getattr(resp, "error", "no response") if resp else "no response"
                return f"❌ Could not download '{file_path}': {error_info}"
        except Exception as e:
            logger.error("Failed to download %s: %s", file_path, e, exc_info=True)
            return f"❌ Error downloading '{file_path}': {e}"

    return download_file
