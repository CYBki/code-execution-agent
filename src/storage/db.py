"""Persistence layer for conversations and messages (SQLite / PostgreSQL).

Backend selection:
- DATABASE_URL env var set → PostgreSQL (production)
- DATABASE_URL not set     → SQLite fallback (local dev)

Schema:
- conversations: session_id, user_id, title, created_at, updated_at
- messages: id, session_id, role, content, steps (JSON), created_at
- files: id, session_id, filename, size, file_path, created_at
"""

import json
import logging
import os
import shutil
import sqlite3
import threading

logger = logging.getLogger(__name__)

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_APP_DIR, "..", ".."))
_DATA_DIR = os.environ.get("DATA_DIR", os.path.join(_PROJECT_ROOT, "data"))

DATABASE_URL = os.environ.get("DATABASE_URL", "")
DB_PATH = os.environ.get("DB_PATH", os.path.join(_DATA_DIR, "conversations.db"))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(_DATA_DIR, "uploads"))

_USE_PG = DATABASE_URL.startswith("postgresql")

if not _USE_PG:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

_lock = threading.Lock()

# --- Connection pool (PostgreSQL) / factory (SQLite) ---

_pg_pool = None


def _init_pg_pool():
    """Initialize a thread-safe PostgreSQL connection pool (lazy, once)."""
    global _pg_pool
    if _pg_pool is not None:
        return
    import psycopg2
    from psycopg2 import pool as pg_pool
    _pg_pool = pg_pool.ThreadedConnectionPool(minconn=2, maxconn=10, dsn=DATABASE_URL)
    logger.info("PostgreSQL connection pool initialized")


def _get_conn():
    """Return a DB connection (PostgreSQL or SQLite)."""
    if _USE_PG:
        _init_pg_pool()
        conn = _pg_pool.getconn()
        conn.autocommit = False
        return conn
    else:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn


def _release_conn(conn):
    """Return a PostgreSQL connection to the pool, or close SQLite."""
    if _USE_PG:
        _pg_pool.putconn(conn)
    else:
        conn.close()


def _ph(n: int = 1) -> str:
    """Return placeholder(s) for parameterized queries: %s for PG, ? for SQLite."""
    p = "%s" if _USE_PG else "?"
    return ", ".join([p] * n)


def _now_expr() -> str:
    """SQL expression for current timestamp."""
    return "NOW()" if _USE_PG else "datetime('now')"


def _dict_row(row, keys: list[str]) -> dict:
    """Convert a row (dict-like or tuple) to a dict with given keys."""
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):
        return dict(row)
    return dict(zip(keys, row))


def init_db():
    """Create tables if they don't exist. Safe to call multiple times."""
    with _lock:
        conn = _get_conn()
        cur = conn.cursor()

        if _USE_PG:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    session_id TEXT PRIMARY KEY,
                    user_id    TEXT NOT NULL,
                    title      TEXT DEFAULT 'Yeni Konuşma',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id         SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES conversations(session_id),
                    role       TEXT NOT NULL,
                    content    TEXT,
                    steps      TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id         SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES conversations(session_id),
                    filename   TEXT NOT NULL,
                    size       INTEGER NOT NULL,
                    file_path  TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            # Replace single-column indexes with composite (session_id, id)
            # so that ORDER BY id is satisfied by the index scan itself.
            cur.execute("DROP INDEX IF EXISTS idx_messages_session")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_ordered ON messages(session_id, id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, updated_at DESC)")
            cur.execute("DROP INDEX IF EXISTS idx_files_session")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_files_session_ordered ON files(session_id, id)")
        else:
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
                    file_path  TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (session_id) REFERENCES conversations(session_id)
                );
                DROP INDEX IF EXISTS idx_messages_session;
                CREATE INDEX IF NOT EXISTS idx_messages_session_ordered ON messages(session_id, id);
                CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, updated_at DESC);
                DROP INDEX IF EXISTS idx_files_session;
                CREATE INDEX IF NOT EXISTS idx_files_session_ordered ON files(session_id, id);
            """)

        conn.commit()
        _release_conn(conn)
    backend = "PostgreSQL" if _USE_PG else f"SQLite ({DB_PATH})"
    logger.info("DB initialized — backend: %s", backend)


def create_conversation(session_id: str, user_id: str, title: str = "Yeni Konuşma"):
    """Insert a new conversation row (ignored if session_id already exists)."""
    ph = _ph(3)
    if _USE_PG:
        sql = f"INSERT INTO conversations (session_id, user_id, title) VALUES ({ph}) ON CONFLICT (session_id) DO NOTHING"
    else:
        sql = f"INSERT OR IGNORE INTO conversations (session_id, user_id, title) VALUES ({ph})"
    with _lock:
        conn = _get_conn()
        conn.cursor().execute(sql, (session_id, user_id, title))
        conn.commit()
        _release_conn(conn)


def update_conversation_title(session_id: str, title: str):
    """Update conversation title (called after first user message)."""
    ph = _ph()
    now = _now_expr()
    sql = f"UPDATE conversations SET title = {ph}, updated_at = {now} WHERE session_id = {ph}"
    with _lock:
        conn = _get_conn()
        conn.cursor().execute(sql, (title[:80], session_id))
        conn.commit()
        _release_conn(conn)


def save_message(session_id: str, role: str, content: str, steps: list | None = None):
    """Append a message to the conversation and bump updated_at."""
    ph4 = _ph(4)
    ph1 = _ph()
    now = _now_expr()
    with _lock:
        conn = _get_conn()
        cur = conn.cursor()
        steps_json = None
        if steps:
            try:
                steps_json = json.dumps(steps, default=str, ensure_ascii=False)
            except Exception as e:
                logger.warning("steps serialization failed: %s", e)
        cur.execute(
            f"INSERT INTO messages (session_id, role, content, steps) VALUES ({ph4})",
            (session_id, role, content or "", steps_json),
        )
        cur.execute(
            f"UPDATE conversations SET updated_at = {now} WHERE session_id = {ph1}",
            (session_id,),
        )
        conn.commit()
        _release_conn(conn)


def load_messages(session_id: str) -> list[dict]:
    """Return all messages for a conversation in insertion order."""
    ph = _ph()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        f"SELECT role, content, steps FROM messages WHERE session_id = {ph} ORDER BY id",
        (session_id,),
    )
    rows = cur.fetchall()
    _release_conn(conn)

    messages = []
    for row in rows:
        r = _dict_row(row, ["role", "content", "steps"])
        msg: dict = {"role": r["role"], "content": r["content"] or ""}
        if r["steps"]:
            try:
                msg["steps"] = json.loads(r["steps"])
            except Exception:
                msg["steps"] = []
        msg.setdefault("steps", [])
        msg["artifacts"] = {"html": [], "charts": [], "downloads": []}
        messages.append(msg)
    return messages


def list_conversations(user_id: str, limit: int = 25) -> list[dict]:
    """Return most-recent conversations for a user."""
    ph = _ph(2)
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        f"SELECT session_id, title, created_at, updated_at FROM conversations "
        f"WHERE user_id = {_ph()} ORDER BY updated_at DESC LIMIT {_ph()}",
        (user_id, limit),
    )
    rows = cur.fetchall()
    _release_conn(conn)
    keys = ["session_id", "title", "created_at", "updated_at"]
    return [_dict_row(r, keys) for r in rows]


def delete_conversation(session_id: str):
    """Delete a conversation, all its messages, and uploaded files from disk."""
    # Remove files from disk
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    if os.path.isdir(session_dir):
        shutil.rmtree(session_dir, ignore_errors=True)

    ph = _ph()
    with _lock:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM files WHERE session_id = {ph}", (session_id,))
        cur.execute(f"DELETE FROM messages WHERE session_id = {ph}", (session_id,))
        cur.execute(f"DELETE FROM conversations WHERE session_id = {ph}", (session_id,))
        conn.commit()
        _release_conn(conn)


def save_files(session_id: str, files: list):
    """Save uploaded files to disk and record metadata in DB.

    Replaces any previously saved files for this session.
    Files are stored under UPLOAD_DIR/<session_id>/<filename>.
    """
    session_dir = os.path.join(UPLOAD_DIR, session_id)

    # Remove old files from disk
    if os.path.isdir(session_dir):
        shutil.rmtree(session_dir, ignore_errors=True)
    os.makedirs(session_dir, exist_ok=True)

    ph1 = _ph()
    ph4 = _ph(4)
    with _lock:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM files WHERE session_id = {ph1}", (session_id,))
        for f in files:
            try:
                data = f.getvalue() if hasattr(f, "getvalue") else f.read()
                file_path = os.path.join(session_dir, f.name)
                with open(file_path, "wb") as fp:
                    fp.write(data)
                cur.execute(
                    f"INSERT INTO files (session_id, filename, size, file_path) VALUES ({ph4})",
                    (session_id, f.name, len(data), file_path),
                )
            except Exception as e:
                logger.warning("Failed to save file %s: %s", getattr(f, "name", "?"), e)
        conn.commit()
        _release_conn(conn)


def load_files(session_id: str) -> list[dict]:
    """Return saved files for a session as list of dicts with name/size/data."""
    ph = _ph()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        f"SELECT filename, size, file_path FROM files WHERE session_id = {ph} ORDER BY id",
        (session_id,),
    )
    rows = cur.fetchall()
    _release_conn(conn)

    results = []
    for row in rows:
        r = _dict_row(row, ["filename", "size", "file_path"])
        try:
            with open(r["file_path"], "rb") as fp:
                data = fp.read()
            results.append({"name": r["filename"], "size": r["size"], "data": data})
        except FileNotFoundError:
            logger.warning("File not found on disk: %s", r["file_path"])
        except Exception as e:
            logger.warning("Failed to load file %s: %s", r["filename"], e)
    return results


def conversation_exists(session_id: str) -> bool:
    """Check whether a conversation already has messages."""
    ph = _ph()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT 1 FROM messages WHERE session_id = {ph} LIMIT 1", (session_id,))
    row = cur.fetchone()
    _release_conn(conn)
    return row is not None
