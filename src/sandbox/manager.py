"""Daytona sandbox lifecycle manager — per-conversation sandbox with TTL cleanup."""

import base64
import logging
import threading

from daytona import (
    Daytona,
    CreateSandboxFromSnapshotParams,
    DaytonaError,
    DaytonaTimeoutError,
    SandboxState,
)
from langchain_daytona import DaytonaSandbox

# Daytona sandbox home directory (not /home/user)
SANDBOX_HOME = "/home/daytona"

logger = logging.getLogger(__name__)


class SandboxManager:
    """Manages a single Daytona sandbox per conversation thread.

    Features:
    - Per-thread sandbox labeled by thread_id (list + create)
    - threading.Event for race-condition-safe package installation
    - auto_delete_interval TTL for orphan cleanup
    - Split exception handling: not-found vs network errors
    """

    def __init__(self):
        self._client = Daytona()
        self._sandbox = None
        self._backend: DaytonaSandbox | None = None
        self._packages_ready = threading.Event()
        self._create_lock = threading.Lock()

    def _find_existing(self, thread_id: str):
        """Find an existing sandbox for this thread, or return None."""
        result = self._client.list(labels={"thread_id": thread_id})
        sandboxes = result.items if hasattr(result, 'items') else list(result)
        # Skip destroyed/error sandboxes
        usable = [
            s for s in sandboxes
            if getattr(s, 'state', None) not in (
                SandboxState.DESTROYED, SandboxState.DESTROYING,
                SandboxState.ERROR, SandboxState.BUILD_FAILED,
            )
        ]
        if len(usable) > 1:
            logger.warning("Multiple sandboxes for thread %s, stopping orphans", thread_id)
            for s in usable[1:]:
                try:
                    self._client.stop(s)
                except Exception:
                    pass
        return usable[0] if usable else None

    def _ensure_started(self):
        """Start the sandbox if it's not already running."""
        state = getattr(self._sandbox, 'state', None)
        if state in (SandboxState.STOPPED, SandboxState.ARCHIVED, SandboxState.RESTORING):
            logger.info("Sandbox state is %s, starting...", state)
            self._client.start(self._sandbox)
            logger.info("Sandbox started.")
        elif state and state not in (SandboxState.STARTED, SandboxState.STARTING, SandboxState.CREATING):
            logger.warning("Sandbox in unexpected state: %s", state)

    def get_or_create_sandbox(self, thread_id: str) -> DaytonaSandbox:
        """Get existing sandbox for thread or create new one with TTL.

        Creates sandbox and starts background package installation.
        Call wait_until_ready() before using the sandbox for user queries.
        """
        with self._create_lock:
            return self._get_or_create_sandbox_locked(thread_id)

    def _get_or_create_sandbox_locked(self, thread_id: str) -> DaytonaSandbox:
        # Validate cached backend is still alive
        if self._backend is not None and self._sandbox is not None:
            state = getattr(self._sandbox, 'state', None)
            if state in (SandboxState.STOPPED, SandboxState.STOPPING,
                         SandboxState.DESTROYED, SandboxState.DESTROYING,
                         SandboxState.ERROR, SandboxState.BUILD_FAILED):
                logger.warning("Cached sandbox in bad state %s, invalidating", state)
                self._backend = None
                self._sandbox = None
                self._packages_ready = threading.Event()
            else:
                # REUSE existing sandbox regardless of thread_id
                logger.info("Reusing cached sandbox %s (ignoring new thread_id for UX)", self._sandbox.id)
                return self._backend
        if self._backend is not None:
            return self._backend

        # Try to find ANY existing sandbox (not by thread_id)
        # This allows "Yeni Konuşma" to reuse sandbox without waiting for package install
        try:
            result = self._client.list(labels={})
            sandboxes = result.items if hasattr(result, 'items') else list(result)
            usable = [
                s for s in sandboxes
                if getattr(s, 'state', None) not in (
                    SandboxState.DESTROYED, SandboxState.DESTROYING,
                    SandboxState.ERROR, SandboxState.BUILD_FAILED,
                    SandboxState.STOPPED, SandboxState.ARCHIVED,  # Also skip stopped
                )
            ]
            if usable:
                # Reuse first available sandbox
                existing = usable[0]
                logger.info("Reusing existing sandbox %s (thread-agnostic for UX)", existing.id)
                self._sandbox = existing
                self._ensure_started()

                # Create backend and immediately signal ready (packages already installed)
                self._backend = DaytonaSandbox(sandbox=self._sandbox, timeout=180)
                self._packages_ready.set()  # Packages already there, no need to wait
                logger.info("Reused sandbox ready immediately (packages pre-installed)")
                return self._backend
            else:
                # No usable sandbox, create new one (packages will be installed)
                logger.info("Creating new sandbox (no usable sandbox found)")
                params = CreateSandboxFromSnapshotParams(
                    labels={"thread_id": thread_id},
                    auto_delete_interval=3600,
                )
                self._sandbox = self._client.create(params)
                self._ensure_started()
                logger.info("New sandbox created: %s", self._sandbox.id)
        except (ConnectionError, TimeoutError, DaytonaTimeoutError) as e:
            logger.error("Daytona API error: %s", e)
            raise ConnectionError(
                f"Daytona unreachable, cannot create sandbox: {e}"
            ) from e
        except Exception as e:
            # Generic error (e.g., list() failed) - fallback to creating new sandbox
            logger.warning("Failed to list sandboxes: %s, creating new", e)
            params = CreateSandboxFromSnapshotParams(
                labels={"thread_id": thread_id},
                auto_delete_interval=3600,
            )
            self._sandbox = self._client.create(params)
            self._ensure_started()
            logger.info("New sandbox created (fallback): %s", self._sandbox.id)

        self._backend = DaytonaSandbox(sandbox=self._sandbox, timeout=180)

        # Install packages in background thread (fast return, packages ready later)
        threading.Thread(
            target=self._install_packages, daemon=True
        ).start()

        return self._backend

    def _install_packages(self):
        """Pre-install data analysis packages and fonts. Sets ready flag when done.

        Strategy: Check which packages are already installed (fast), only pip
        install missing ones. This avoids 180s timeouts on already-installed pkgs.
        """
        be = self._backend
        if be is None:
            logger.error("_install_packages: no backend, skipping")
            self._packages_ready.set()
            return

        try:
            logger.info("_install_packages thread started")

            # Phase 1: Fonts + weasyprint system deps (instant if already installed)
            be.execute(
                "cp /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf /home/daytona/ 2>/dev/null; "
                "cp /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf /home/daytona/ 2>/dev/null; "
                "apt-get install -y -qq --no-install-recommends "
                "libpango1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi8 "
                "libxml2 libxslt1.1 fonts-dejavu-core 2>/dev/null || true; "
                "echo FONTS_DONE"
            )
            logger.info("Fonts and system deps done")

            # Phase 2: Check packages — split into CRITICAL (must be ready) and OPTIONAL (background)
            # Critical: needed for every analysis (fast to install, ~10s)
            # Optional: heavy wheels used rarely (duckdb, pdfplumber)
            critical_pkgs = {
                "weasyprint": "weasyprint", "pandas": "pandas", "openpyxl": "openpyxl",
                "xlsxwriter": "xlsxwriter", "numpy": "numpy",
                "matplotlib": "matplotlib", "seaborn": "seaborn",
                "plotly": "plotly", "scipy": "scipy", "scikit-learn": "sklearn",
                "python-pptx": "pptx",  # PowerPoint generation (moved to critical)
            }
            optional_pkgs = {
                "pdfplumber": "pdfplumber",
                "duckdb": "duckdb",
            }
            all_pkgs = {**critical_pkgs, **optional_pkgs}

            check_lines = []
            for pkg, imp in all_pkgs.items():
                check_lines.append(
                    f"try:\n    import {imp}\n    print('{pkg}:OK')\n"
                    f"except Exception:\n    print('{pkg}:MISS')"
                )
            check_script = "\n".join(check_lines)
            b64 = base64.b64encode(check_script.encode()).decode()
            r = be.execute(
                f"printf '%s' '{b64}' | base64 -d > /tmp/_pkgcheck.py && python3 /tmp/_pkgcheck.py 2>&1"
            )
            check_out = getattr(r, 'output', '') or ''
            logger.info("Package check: %s", check_out.replace('\n', ', ')[:200])

            missing_critical = []
            missing_optional = []
            for line in check_out.splitlines():
                for pkg in critical_pkgs:
                    if line.strip() == f"{pkg}:MISS":
                        missing_critical.append(pkg)
                for pkg in optional_pkgs:
                    if line.strip() == f"{pkg}:MISS":
                        missing_optional.append(pkg)

            # Install critical packages synchronously (blocks ready signal)
            if missing_critical:
                for i in range(0, len(missing_critical), 4):
                    batch = missing_critical[i:i + 4]
                    pkg_list = " ".join(batch)
                    logger.info("Installing critical batch: %s", pkg_list)
                    try:
                        r = be.execute(
                            f"pip install -q --timeout 120 {pkg_list} 2>&1",
                            timeout=150,
                        )
                        exit_code = getattr(r, 'exit_code', None)
                        if exit_code and exit_code != 0:
                            logger.warning("critical batch exit=%s: %s",
                                           exit_code, getattr(r, 'output', '')[:200])
                        else:
                            logger.info("critical batch OK: %s", pkg_list)
                    except Exception as e:
                        logger.warning("critical batch failed: %s", e)
            else:
                logger.info("All critical packages already installed")

            # Optional packages install in background AFTER ready signal
            if missing_optional:
                def _install_optional(pkgs):
                    pkg_list = " ".join(pkgs)
                    logger.info("Background: installing optional packages: %s", pkg_list)
                    try:
                        r = be.execute(
                            f"pip install -q --timeout 300 {pkg_list} 2>&1",
                            timeout=360,
                        )
                        exit_code = getattr(r, 'exit_code', None)
                        logger.info("Optional packages done (exit=%s)", exit_code)
                    except Exception as e:
                        logger.warning("Optional install failed: %s", e)
                threading.Thread(
                    target=_install_optional, args=(missing_optional,), daemon=True
                ).start()

            # Phase 3: Verify critical packages
            verify = be.execute(
                "python3 -c 'import weasyprint, pandas, openpyxl, pptx; print(\"VERIFY_OK\")' 2>&1"
            )
            v_out = getattr(verify, 'output', '') or ''
            if "VERIFY_OK" in v_out:
                logger.info("Critical packages verified OK")
                self._packages_ready.set()
                logger.info("_packages_ready event SET (verified)")
            else:
                logger.error("Package verification FAILED: %s", v_out[:200])
                # Don't set ready flag if verification fails
                # Agent will get timeout warning from wait_until_ready()

        except Exception as e:
            logger.error("Package installation FAILED: %s", e, exc_info=True)
            # Don't set ready flag on exception — let wait_until_ready() timeout

    def wait_until_ready(self, timeout: float = 360) -> bool:
        """Block until packages are installed. Returns False on timeout."""
        return self._packages_ready.wait(timeout=timeout)

    def upload_files(self, files: list):
        """Upload user files to Daytona sandbox.

        Strategy: Use native upload_files API first (handles large files).
        Falls back to chunked base64+execute for resilience.
        """
        self.wait_until_ready()
        if self._backend is None:
            logger.error("Cannot upload files: no sandbox backend")
            return
        logger.info("Starting upload of %d files", len(files))
        for f in files:
            dst = f"{SANDBOX_HOME}/{f.name}"
            data = f.getvalue()
            size_mb = len(data) / (1024 * 1024)

            # Try native API first (best for large files)
            try:
                responses = self._backend.upload_files([(dst, data)])
                resp = responses[0] if responses else None
                err = getattr(resp, 'error', None) if resp else 'no response'
                if err:
                    raise RuntimeError(f"Native upload error: {err}")
                logger.info("Uploaded %s (%.1f MB) via native API", f.name, size_mb)
                continue
            except Exception as e:
                logger.warning("Native upload failed for %s: %s, trying chunked", f.name, e)

            # Fallback: chunked base64 (works for any size)
            try:
                self._upload_chunked(dst, data)
                logger.info("Uploaded %s (%.1f MB) via chunked base64", f.name, size_mb)
            except Exception as e:
                logger.error("Failed to upload %s: %s", f.name, e)

    def _upload_chunked(self, dst: str, data: bytes, chunk_size: int = 512_000):
        """Upload file via chunked base64+execute (fallback for large files)."""
        b64 = base64.b64encode(data).decode()
        # First chunk: create file (overwrite)
        for i in range(0, len(b64), chunk_size):
            chunk = b64[i:i + chunk_size]
            op = ">" if i == 0 else ">>"
            cmd = f"printf '%s' '{chunk}' {op} /tmp/_upload.b64"
            self._backend.execute(cmd)
        # Decode and move to destination
        self._backend.execute(f"base64 -d /tmp/_upload.b64 > '{dst}' && rm /tmp/_upload.b64")
        # Verify
        r = self._backend.execute(f"wc -c < '{dst}'")
        remote_size = int(r.output.strip()) if r.output.strip().isdigit() else 0
        if remote_size != len(data):
            raise RuntimeError(f"Size mismatch: local={len(data)}, remote={remote_size}")

    def clean_workspace(self):
        """Remove user files from sandbox, keep packages and fonts intact.

        Enables sandbox reuse between conversations without re-installing packages.
        """
        if self._backend is None:
            return
        try:
            # Remove everything in /home/daytona/ EXCEPT font files
            self._backend.execute(
                "cd /home/daytona && "
                "find . -maxdepth 1 -type f ! -name '*.ttf' -delete 2>/dev/null; "
                "rm -rf /tmp/_run_*.py /tmp/_pkgcheck.py /tmp/_upload.b64 2>/dev/null; "
                "echo CLEAN_OK"
            )
            logger.info("Workspace cleaned (packages preserved)")
        except Exception as e:
            logger.warning("Workspace cleanup failed: %s", e)

    def stop(self):
        """Stop sandbox. Safe to call multiple times."""
        if self._sandbox is not None:
            try:
                self._client.stop(self._sandbox)
            except Exception:
                pass
            finally:
                self._sandbox = None
                self._backend = None
                self._packages_ready = threading.Event()

    def __del__(self):
        # Best-effort only — not guaranteed. Primary cleanup via atexit.
        try:
            self.stop()
        except Exception:
            pass
