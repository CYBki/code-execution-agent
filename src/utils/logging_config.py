"""Structured JSON logging configuration.

Provides:
- JSONFormatter: outputs each log line as a single JSON object
- SessionContext: thread-local session_id correlation
- setup_logging(): configures root logger with console + file handlers
- get_audit_logger(): returns a dedicated logger for tool call auditing

Log files (under DATA_DIR or logs/):
- logs/app.log        — all application logs (INFO+), JSON format
- logs/app_error.log  — errors only (WARNING+), JSON format
- logs/audit.log      — tool call audit trail, JSON format
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


# --- Thread-local session context ---

class SessionContext:
    """Thread-local storage for session_id correlation.

    Usage:
        SessionContext.set("abc-123")
        logger.info("something")  # → {"session_id": "abc-123", ...}
        SessionContext.clear()
    """
    _local = threading.local()

    @classmethod
    def set(cls, session_id: str):
        cls._local.session_id = session_id

    @classmethod
    def get(cls) -> str:
        return getattr(cls._local, "session_id", "")

    @classmethod
    def clear(cls):
        cls._local.session_id = ""


# --- JSON Formatter ---

class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects.

    Output example:
    {"ts":"2026-04-14T08:52:00.123Z","level":"ERROR","logger":"src.sandbox.manager",
     "msg":"execute failed: timeout","session_id":"abc-123","exc":"Traceback..."}
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Session correlation
        sid = SessionContext.get()
        if sid:
            log_entry["session_id"] = sid

        # Extra fields (e.g. tool_name, action)
        for key in ("tool_name", "action", "blocked", "execute_num", "duration_s"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        # Exception info
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exc"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


# --- Setup functions ---

_LOG_DIR = os.path.join(
    os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data")),
    "..", "logs",
)
_LOG_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "logs")
)


def setup_logging(log_level: int = logging.INFO):
    """Configure root logger with structured JSON handlers.

    Replaces the default basicConfig setup in app.py.

    Handlers:
    - Console (stdout): human-readable format for dev, JSON if LOG_JSON=1
    - app.log: all logs INFO+ in JSON (10MB × 5 rotation)
    - app_error.log: WARNING+ only in JSON (10MB × 5 rotation)
    """
    os.makedirs(_LOG_DIR, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(log_level)

    # Remove any existing handlers (prevents duplicate logs on Streamlit rerun)
    root.handlers.clear()

    json_fmt = JSONFormatter()
    human_fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    # Console handler — human-readable by default, JSON if LOG_JSON=1
    console = logging.StreamHandler()
    console.setLevel(log_level)
    if os.environ.get("LOG_JSON", "").strip() in ("1", "true"):
        console.setFormatter(json_fmt)
    else:
        console.setFormatter(human_fmt)
    root.addHandler(console)

    # File handler: all logs (INFO+) in JSON
    all_handler = RotatingFileHandler(
        os.path.join(_LOG_DIR, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    all_handler.setLevel(logging.INFO)
    all_handler.setFormatter(json_fmt)
    root.addHandler(all_handler)

    # File handler: errors only (WARNING+) in JSON
    err_handler = RotatingFileHandler(
        os.path.join(_LOG_DIR, "app_error.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(json_fmt)
    root.addHandler(err_handler)

    logging.getLogger(__name__).info("Structured logging initialized (log_dir=%s)", _LOG_DIR)


def get_audit_logger() -> logging.Logger:
    """Return a dedicated logger for tool call auditing.

    Writes to logs/audit.log in JSON format. Separate from app.log
    so it can be analyzed independently (grep, jq, log aggregator).
    """
    audit = logging.getLogger("audit")
    if not audit.handlers:
        os.makedirs(_LOG_DIR, exist_ok=True)
        handler = RotatingFileHandler(
            os.path.join(_LOG_DIR, "audit.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(JSONFormatter())
        audit.addHandler(handler)
        audit.setLevel(logging.INFO)
        audit.propagate = False  # Don't duplicate into app.log
    return audit
