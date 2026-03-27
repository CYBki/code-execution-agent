"""Execute tool — run shell commands in the Daytona sandbox.

Handles the common python3 -c "..." pattern by writing code to a temp file
first, avoiding shell quote-escaping issues that corrupt Python code.
"""

from __future__ import annotations

import base64
import logging
import re
import uuid

from langchain_core.tools import tool
from langchain_daytona import DaytonaSandbox

logger = logging.getLogger(__name__)

# Matches: python3 -c "..." or python3 -c '...'
_PY_INLINE_RE = re.compile(
    r"""^python3?\s+-c\s+(['"])(.*)\1\s*$""",
    re.DOTALL,
)


def _unescape_shell(code: str, quote_char: str) -> str:
    """Unescape shell escape sequences based on the outer quote type."""
    if quote_char == '"':
        # In double-quoted shell strings: \" → " and \\ → \
        code = code.replace('\\"', '"').replace('\\\\', '\\')
    # Single-quoted shell strings have no escapes (everything is literal)
    return code


def _extract_python_code(command: str) -> str | None:
    """Extract Python code from a python3 -c '...' command, or None."""
    m = _PY_INLINE_RE.match(command.strip())
    if m:
        quote_char = m.group(1)
        return _unescape_shell(m.group(2), quote_char)
    # Fallback: starts with python3 -c and rest is the code
    for prefix in ("python3 -c ", "python -c "):
        if command.strip().startswith(prefix):
            code = command.strip()[len(prefix):]
            # Strip outer quotes if present
            if code.startswith('"') and code.endswith('"'):
                code = _unescape_shell(code[1:-1], '"')
            elif code.startswith("'") and code.endswith("'"):
                code = code[1:-1]
            return code if len(code) > 10 else None
    return None


def make_execute_tool(backend: DaytonaSandbox):
    """Factory: create the execute tool bound to a Daytona backend."""

    @tool
    def execute(command: str) -> str:
        """Execute a shell command inside the Daytona sandbox.

        Use this to run Python scripts for data analysis, PDF generation, etc.
        The sandbox has pre-installed packages: pandas, openpyxl, numpy,
        matplotlib, seaborn, pdfplumber, duckdb, fpdf2, scipy, scikit-learn,
        plotly, xlsxwriter.

        Example:
            execute("python3 -c 'import pandas as pd; print(pd.__version__)'")

        Args:
            command: Shell command string to execute in the sandbox.
        """
        try:
            # Detect python3 -c "..." and route through temp file
            py_code = _extract_python_code(command)

            # Also detect raw Python code sent WITHOUT python3 -c prefix
            if not py_code:
                stripped = command.strip()
                _PY_STARTS = ("import ", "from ", "print(", "def ", "class ",
                              "# ", "try:", "with ", "for ", "if ", "df ", "df=",
                              "pdf ", "pdf=", "result ", "result=",
                              "pd.", "np.", "plt.", "total_", "assert ", "raise ",
                              "while ", "open(", "json.", "con ", "con=")
                if any(stripped.startswith(p) for p in _PY_STARTS):
                    py_code = stripped
                    logger.info("Auto-detected raw Python code (no python3 -c prefix)")

            if py_code:
                b64 = base64.b64encode(py_code.encode()).decode()
                tmp_path = f"/tmp/_run_{uuid.uuid4().hex[:8]}.py"
                shell_cmd = f"printf '%s' '{b64}' | base64 -d > {tmp_path} && python3 {tmp_path} && rm -f {tmp_path}"
            else:
                shell_cmd = command

            result = backend.execute(shell_cmd)
            output = getattr(result, "output", str(result)) if result else ""
            exit_code = getattr(result, "exit_code", None)

            # Log output for debugging (truncated)
            out_preview = (output or "")[:300].replace("\n", "\\n")
            logger.info("execute output (exit=%s): %s", exit_code, out_preview)

            MAX_OUTPUT = 50_000
            if output and len(output) > MAX_OUTPUT:
                output = output[:MAX_OUTPUT] + f"\n... [truncated, {len(output)} total chars]"

            if exit_code is None:
                logger.warning("execute: exit_code is None, cannot determine success")
            elif exit_code != 0:
                return f"Exit code: {exit_code}\n{output}"
            return output or "(no output)"
        except Exception as e:
            logger.error("Execute failed: %s", e)
            return f"Error: {e}"

    return execute
