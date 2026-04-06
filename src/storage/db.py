"""SQLite persistence layer for conversations and messages.

Schema:
- conversations: session_id, user_id, title, created_at, updated_at
- messages: id, session_id, role, content, steps (JSON), created_at
"""

import json
import logging
import sqlite3
import threading

logger = logging.getLogger(__name__)

DB_PATH = "conversations.db"
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call multiple times."""
    with _lock:
        conn = _get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                session_id TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                title      TEXT DEFAULT 'Yeni Konuşma',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT,
                steps      TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES conversations(session_id)
            );

            CREATE TABLE IF NOT EXISTS files (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                filename   TEXT NOT NULL,
                size       INTEGER NOT NULL,
                data       BLOB NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES conversations(session_id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_conversations_user
                ON conversations(user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_files_session
                ON files(session_id);
        """)
        conn.commit()
        conn.close()
    logger.info("DB initialized at %s", DB_PATH)


def create_conversation(session_id: str, user_id: str, title: str = "Yeni Konuşma"):
    """Insert a new conversation row (ignored if session_id already exists)."""
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO conversations (session_id, user_id, title) VALUES (?, ?, ?)",
            (session_id, user_id, title),
        )
        conn.commit()
        conn.close()


def update_conversation_title(session_id: str, title: str):
    """Update conversation title (called after first user message)."""
    with _lock:
        conn = _get_conn()
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = datetime('now') WHERE session_id = ?",
            (title[:80], session_id),
        )
        conn.commit()
        conn.close()


def save_message(session_id: str, role: str, content: str, steps: list | None = None):
    """Append a message to the conversation and bump updated_at."""
    with _lock:
        conn = _get_conn()
        steps_json = None
        if steps:
            try:
                steps_json = json.dumps(steps, default=str, ensure_ascii=False)
            except Exception as e:
                logger.warning("steps serialization failed: %s", e)
        conn.execute(
            "INSERT INTO messages (session_id, role, content, steps) VALUES (?, ?, ?, ?)",
            (session_id, role, content or "", steps_json),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
        conn.close()


def load_messages(session_id: str) -> list[dict]:
    """Return all messages for a conversation in insertion order."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT role, content, steps FROM messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    conn.close()

    messages = []
    for row in rows:
        msg: dict = {"role": row["role"], "content": row["content"] or ""}
        if row["steps"]:
            try:
                msg["steps"] = json.loads(row["steps"])
            except Exception:
                msg["steps"] = []
        msg.setdefault("steps", [])
        msg["artifacts"] = {"html": [], "charts": [], "downloads": []}
        messages.append(msg)
    return messages


def list_conversations(user_id: str, limit: int = 25) -> list[dict]:
    """Return most-recent conversations for a user."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT session_id, title, created_at, updated_at FROM conversations "
        "WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_conversation(session_id: str):
    """Delete a conversation and all its messages."""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()


def save_files(session_id: str, files: list):
    """Save uploaded files (list of MockUploadedFile or UploadedFile) to DB.

    Replaces any previously saved files for this session.
    """
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM files WHERE session_id = ?", (session_id,))
        for f in files:
            try:
                data = f.getvalue() if hasattr(f, "getvalue") else f.read()
                conn.execute(
                    "INSERT INTO files (session_id, filename, size, data) VALUES (?, ?, ?, ?)",
                    (session_id, f.name, len(data), data),
                )
            except Exception as e:
                logger.warning("Failed to save file %s: %s", getattr(f, "name", "?"), e)
        conn.commit()
        conn.close()


def load_files(session_id: str) -> list[dict]:
    """Return saved files for a session as list of dicts with name/size/data."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT filename, size, data FROM files WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    conn.close()
    return [{"name": r["filename"], "size": r["size"], "data": bytes(r["data"])} for r in rows]


def conversation_exists(session_id: str) -> bool:
    """Check whether a conversation already has messages."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT 1 FROM messages WHERE session_id = ? LIMIT 1", (session_id,)
    ).fetchone()
    conn.close()
    return row is not None
