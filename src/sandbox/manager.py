"""OpenSandbox lifecycle manager — per-conversation sandbox with persistent kernel.

Key differences from Daytona:
- Uses SandboxSync + CodeInterpreterSync: fully blocking, no asyncio needed
- Packages are pre-installed in Docker image (no ~35s pip install wait)
- CodeInterpreter persistent Python context: variables survive across execute()
  calls within a session — pickle no longer needed for data transfer
- Sandbox creation is ~3-5s instead of ~35s
"""

import base64
import concurrent.futures
import logging
import re
import threading
from datetime import timedelta

from opensandbox.sync.sandbox import SandboxSync
from opensandbox.models import WriteEntry
from opensandbox.models.execd import RunCommandOpts
from code_interpreter.sync.code_interpreter import CodeInterpreterSync
from code_interpreter.models.code import SupportedLanguage

# OpenSandbox working directory (matches Dockerfile WORKDIR)
SANDBOX_HOME = "/home/sandbox"

logger = logging.getLogger(__name__)

# Detects the base64+tempfile pattern that execute.py generates for Python code:
# printf '%s' 'BASE64' | base64 -d > /tmp/_run_XXXXXX.py && python3 /tmp/_run_XXXXXX.py ...
_PYFILE_RE = re.compile(
    r"printf '%s' '([A-Za-z0-9+/=\s]+)' \| base64 -d > (/tmp/_run_[a-f0-9]+\.py)"
)


class _ExecuteResult:
    """Mimics DaytonaSandbox execute result — keeps execute.py interface unchanged."""

    def __init__(self, output: str, exit_code: int = 0):
        self.output = output
        self.exit_code = exit_code


class _DownloadResult:
    """Mimics DaytonaSandbox download result — keeps download_file.py interface unchanged."""

    def __init__(self, content: bytes, error: str | None = None):
        self.content = content
        self.error = error


class OpenSandboxBackend:
    """Synchronous OpenSandbox backend compatible with existing tool interfaces.

    Provides the same .execute() / .upload_files() / .download_files() interface
    as DaytonaSandbox so execute.py, download_file.py, visualization.py work
    without logic changes.

    Persistent kernel: Python code detected via _PYFILE_RE runs through the
    CodeInterpreter context — variables/imports survive across execute() calls
    within the same session, so pickle is no longer needed.
    Shell commands (rm, echo, etc.) run via sandbox.commands.run().
    """

    def __init__(
        self,
        sandbox: SandboxSync,
        interpreter: CodeInterpreterSync,
        py_context,
    ):
        self._sandbox = sandbox
        self._interpreter = interpreter
        self._py_context = py_context  # Persistent Python execution context

    def _reset_context(self):
        """Destroy the current (hung) Python context and create a fresh one.

        Called after a timeout — the old context is stuck in "session is busy"
        state because codes.run() is still blocking in a background thread.
        A new context gives subsequent execute() calls a clean kernel.
        """
        try:
            old_id = getattr(self._py_context, "id", None)
            if old_id:
                try:
                    self._interpreter.codes.delete_context(old_id)
                except Exception:
                    pass  # May fail if context is stuck — that's OK
            self._py_context = self._interpreter.codes.create_context(
                SupportedLanguage.PYTHON
            )
            logger.info("Kernel context reset after timeout (new: %s)", self._py_context.id)
        except Exception as e:
            logger.error("Failed to reset kernel context: %s", e)

    def execute(self, command: str, timeout: int = 180) -> _ExecuteResult:
        """Execute a command in the sandbox.

        Python code (detected via base64+tempfile pattern) runs in the persistent
        CodeInterpreter context for stateful execution.
        Shell commands run directly via sandbox.commands.run().
        """
        try:
            m = _PYFILE_RE.search(command)
            if m:
                # Python code path: decode base64 → run in persistent kernel context
                b64 = m.group(1).strip()
                py_code = base64.b64decode(b64).decode()

                # Wrap codes.run() with timeout — codes.run() has no built-in
                # timeout and can hang forever on large file operations.
                # NOTE: Do NOT use 'with' block — pool.__exit__ calls
                # shutdown(wait=True) which blocks until the hung thread finishes.
                pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = pool.submit(
                    self._interpreter.codes.run,
                    py_code, context=self._py_context,
                )
                try:
                    result = future.result(timeout=timeout)
                except concurrent.futures.TimeoutError:
                    future.cancel()
                    pool.shutdown(wait=False)
                    logger.error("codes.run() timed out after %ds", timeout)
                    # Reset kernel context — the old context is stuck with the
                    # hung execution ("session is busy"). Create a fresh one so
                    # subsequent execute() calls work normally.
                    self._reset_context()
                    return _ExecuteResult(
                        output=f"Error: Code execution timed out after {timeout}s. "
                               "The operation is too slow — try chunked/streaming reads "
                               "or use DuckDB to query the file directly without loading "
                               "it entirely into memory.",
                        exit_code=1,
                    )
                else:
                    pool.shutdown(wait=False)

                output = result.text or ""
                if result.error:
                    err_msg = getattr(result.error, "value", str(result.error))
                    output = output + (f"\n{err_msg}" if output else err_msg)
                exit_code = 1 if result.error else 0
                return _ExecuteResult(output=output.strip(), exit_code=exit_code)

            # Shell command path: run directly
            opts = RunCommandOpts(timeout=timedelta(seconds=timeout))
            result = self._sandbox.commands.run(command, opts=opts)
            output = result.text or ""
            exit_code = getattr(result, "exit_code", 0) or 0
            return _ExecuteResult(output=output.strip(), exit_code=exit_code)

        except Exception as e:
            logger.error("execute failed: %s", e)
            return _ExecuteResult(output=f"Error: {e}", exit_code=1)

    def upload_files(self, files: list) -> list:
        """Upload files to sandbox. files: [(path, bytes), ...]"""

        class _Ok:
            error = None

        class _Err:
            def __init__(self, msg):
                self.error = msg

        try:
            entries = []
            for path, data in files:
                if isinstance(data, str):
                    data = data.encode()
                entries.append(WriteEntry(path=path, data=data))
            self._sandbox.files.write_files(entries)
            return [_Ok()]
        except Exception as e:
            logger.error("upload_files failed: %s", e)
            return [_Err(str(e))]

    def download_files(self, paths: list) -> list:
        """Download files from sandbox. Returns list of _DownloadResult."""
        results = []
        for path in paths:
            try:
                content = self._sandbox.files.read_bytes(path)
                results.append(_DownloadResult(content=content))
            except Exception as e:
                logger.error("download %s failed: %s", path, e)
                results.append(_DownloadResult(content=b"", error=str(e)))
        return results


class SandboxManager:
    """Manages a single OpenSandbox per conversation thread.

    Key improvements over Daytona:
    - SandboxSync: fully blocking API, no asyncio complexity
    - Packages pre-installed in Docker image → ready in ~5s (not ~35s)
    - Persistent CodeInterpreter context → no pickle needed between execute() calls
    - Sandbox reused across conversations (clean_workspace clears files only)
    """

    def __init__(self):
        self._backend: OpenSandboxBackend | None = None
        self._sandbox: SandboxSync | None = None
        self._interpreter: CodeInterpreterSync | None = None
        self._py_context = None
        self._packages_ready = threading.Event()
        self._create_lock = threading.Lock()

    def get_or_create_sandbox(self, thread_id: str) -> OpenSandboxBackend:
        """Get existing backend or create new sandbox with CodeInterpreter kernel.

        Returns immediately with cached backend if already created.
        First call creates sandbox + persistent Python context (~5s).
        """
        with self._create_lock:
            if self._backend is not None:
                logger.info("Reusing existing OpenSandbox backend")
                return self._backend
            return self._create_new_sandbox(thread_id)

    def _create_new_sandbox(self, thread_id: str) -> OpenSandboxBackend:
        """Create sandbox container + CodeInterpreter + persistent Python context."""
        try:
            logger.info("Creating OpenSandbox sandbox (image: agentic-sandbox:v1)")
            sandbox = SandboxSync.create(
                "agentic-sandbox:v1",
                entrypoint=["/opt/opensandbox/code-interpreter.sh"],
                env={"PYTHON_VERSION": "3.11"},
                timeout=timedelta(hours=2),
            )
            self._sandbox = sandbox
            logger.info("Sandbox created (%s), initializing CodeInterpreter...", sandbox.id)

            # Create CodeInterpreter wrapping the sandbox
            interpreter = CodeInterpreterSync.create(sandbox)
            self._interpreter = interpreter

            # Create persistent Python execution context (variables survive across calls)
            py_context = interpreter.codes.create_context(SupportedLanguage.PYTHON)
            self._py_context = py_context
            logger.info("Persistent Python context created: %s", py_context.id)

            self._backend = OpenSandboxBackend(sandbox, interpreter, py_context)

            # Pre-inject publish_html() helper into the persistent kernel
            _INIT_CODE = (
                "def publish_html(html_str):\n"
                "    \"\"\"Write HTML dashboard to file for automatic rendering in the UI.\"\"\"\n"
                "    with open('/home/sandbox/__dashboard__.html', 'w', encoding='utf-8') as f:\n"
                "        f.write(html_str)\n"
                "    print('__PUBLISH_HTML__')\n"
            )
            try:
                interpreter.codes.run(_INIT_CODE, context=py_context)
                logger.info("publish_html() injected into persistent kernel")
            except Exception as e:
                logger.warning("Failed to inject publish_html(): %s", e)

            # Packages are pre-installed in image — signal ready immediately
            self._packages_ready.set()
            logger.info("Sandbox ready (packages pre-installed, persistent kernel active)")

            return self._backend

        except Exception as e:
            logger.error("Failed to create sandbox: %s", e, exc_info=True)
            self._packages_ready.set()  # Fail-fast: don't block UI forever
            raise ConnectionError(f"OpenSandbox unreachable: {e}") from e

    def wait_until_ready(self, timeout: float = 30) -> bool:
        """Block until sandbox is ready. Much faster than Daytona (no pip install)."""
        return self._packages_ready.wait(timeout=timeout)

    def upload_files(self, files: list):
        """Upload user files to sandbox /home/sandbox/."""
        self.wait_until_ready()
        if self._backend is None:
            logger.error("Cannot upload files: no sandbox backend")
            return
        logger.info("Uploading %d file(s) to sandbox", len(files))
        for f in files:
            dst = f"{SANDBOX_HOME}/{f.name}"
            data = f.getvalue()
            size_mb = len(data) / (1024 * 1024)
            try:
                responses = self._backend.upload_files([(dst, data)])
                resp = responses[0] if responses else None
                err = getattr(resp, "error", None) if resp else "no response"
                if err:
                    raise RuntimeError(f"Upload error: {err}")
                logger.info("Uploaded %s (%.1f MB)", f.name, size_mb)
            except Exception as e:
                logger.error("Failed to upload %s: %s", f.name, e)

    def clean_workspace(self):
        """Remove user files from sandbox for new conversation.

        Reuses the same sandbox container + kernel — no restart needed.
        The Python context is reset so variables from previous session don't leak.
        """
        if self._backend is None:
            return
        try:
            # Clean filesystem
            self._backend.execute(
                f"rm -rf {SANDBOX_HOME}/* 2>/dev/null; "
                "rm -rf /tmp/_run_*.py 2>/dev/null; "
                "echo CLEAN_OK"
            )
            # Reset Python kernel context for fresh session
            if self._interpreter is not None:
                try:
                    self._interpreter.codes.delete_context(self._py_context.id)
                except Exception:
                    pass
                self._py_context = self._interpreter.codes.create_context(
                    SupportedLanguage.PYTHON
                )
                self._backend._py_context = self._py_context
                logger.info("Python kernel context reset for new session")
            logger.info("Workspace cleaned")
        except Exception as e:
            logger.warning("Workspace cleanup failed: %s", e)

    def stop(self):
        """Stop sandbox container. Safe to call multiple times."""
        if self._sandbox is not None:
            try:
                self._sandbox.kill()
                self._sandbox.close()
            except Exception:
                pass
            finally:
                self._sandbox = None
                self._backend = None
                self._interpreter = None
                self._py_context = None
                self._packages_ready = threading.Event()

    def __del__(self):
        # Best-effort only — not guaranteed. Primary cleanup via atexit in session.py.
        try:
            self.stop()
        except Exception:
            pass
