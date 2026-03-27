"""Thread-safe artifact store for passing data from agent tools to Streamlit UI.

Tools run in agent thread pools where st.session_state is not accessible.
This module provides a per-session thread-safe store that tools write to and
the UI thread reads from.
"""

from __future__ import annotations

import threading
from typing import Any


class ArtifactStore:
    """Thread-safe store for pending artifacts (charts, downloads, HTML)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pending_downloads: list[dict[str, Any]] = []
        self._pending_charts: list[dict[str, Any]] = []
        self._pending_html: list[str] = []

    def add_download(self, file_bytes: bytes, filename: str, path: str = "") -> None:
        with self._lock:
            # Dedup: skip if same filename already pending
            if any(d["filename"] == filename for d in self._pending_downloads):
                return
            self._pending_downloads.append({
                "bytes": file_bytes,
                "filename": filename,
                "path": path,
            })

    def add_chart(self, chart_bytes: bytes | None, code: str = "") -> None:
        if chart_bytes is None:
            return
        with self._lock:
            self._pending_charts.append({
                "bytes": chart_bytes,
                "code": code,
            })

    def pop_downloads(self) -> list[dict[str, Any]]:
        with self._lock:
            items = self._pending_downloads[:]
            self._pending_downloads.clear()
            return items

    def pop_charts(self) -> list[dict[str, Any]]:
        with self._lock:
            items = self._pending_charts[:]
            self._pending_charts.clear()
            return items

    def add_html(self, html: str) -> None:
        with self._lock:
            self._pending_html.append(html)

    def pop_html(self) -> list[str]:
        with self._lock:
            items = self._pending_html[:]
            self._pending_html.clear()
            return items

    def clear_all(self) -> None:
        """Clear all pending artifacts (used by reset_session)."""
        with self._lock:
            self._pending_downloads.clear()
            self._pending_charts.clear()
            self._pending_html.clear()


# --- Per-session store management ---
_stores: dict[str, ArtifactStore] = {}
_stores_lock = threading.Lock()


def get_store(session_id: str) -> ArtifactStore:
    """Get or create an ArtifactStore for the given session."""
    with _stores_lock:
        if session_id not in _stores:
            _stores[session_id] = ArtifactStore()
        return _stores[session_id]


def release_store(session_id: str) -> None:
    """Remove a session's store (call on session reset)."""
    with _stores_lock:
        _stores.pop(session_id, None)
