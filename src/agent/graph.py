"""Agent builder — LangChain create_agent + OpenSandbox.

Replaces create_deep_agent to eliminate unnecessary SubAgent, FilesystemMiddleware,
and TodoListMiddleware. Only the middleware we actually need is included.
"""

from __future__ import annotations

import logging
import re

import streamlit as st
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from deepagents._models import resolve_model
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware

from src.agent.prompts import BASE_SYSTEM_PROMPT
from src.sandbox.manager import SandboxManager
from src.skills.loader import compose_system_prompt
from src.skills.registry import detect_required_skills
from src.tools.download_file import make_download_file_tool
from src.tools.execute import make_execute_tool
from src.tools.file_parser import make_parse_file_tool
from src.tools.generate_html import make_generate_html_tool
from src.tools.visualization import make_visualization_tool
from src.utils.logging_config import get_audit_logger

logger = logging.getLogger(__name__)
_audit = get_audit_logger()

REACT_MAX_ITERATIONS = 30

# --- Persistent checkpointer (SqliteSaver or PostgresSaver singleton) ---
_checkpointer = None
_checkpointer_conn = None


def _get_checkpointer():
    """Return a module-level checkpointer (PostgresSaver or SqliteSaver).

    Backend selection:
    - DATABASE_URL env var set → PostgresSaver (production)
    - DATABASE_URL not set     → SqliteSaver with data/checkpoints.db (dev)

    Persistent across agent rebuilds and app restarts.
    """
    global _checkpointer, _checkpointer_conn
    if _checkpointer is None:
        import os
        database_url = os.environ.get("DATABASE_URL", "")

        if database_url.startswith("postgresql"):
            from langgraph.checkpoint.postgres import PostgresSaver
            _checkpointer = PostgresSaver.from_conn_string(database_url)
            _checkpointer.setup()
            logger.info("PostgresSaver initialized (PostgreSQL)")
        else:
            import sqlite3
            _project_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
            _data_dir = os.environ.get("DATA_DIR", os.path.join(_project_root, "data"))
            os.makedirs(_data_dir, exist_ok=True)
            db_path = os.path.join(_data_dir, "checkpoints.db")
            _checkpointer_conn = sqlite3.connect(db_path, check_same_thread=False)
            _checkpointer = SqliteSaver(_checkpointer_conn)
            _checkpointer.setup()
            logger.info("SqliteSaver initialized at %s", db_path)
    return _checkpointer

_COMPLEX_KEYWORDS = (
    "marka", "brand", "segment", "cluster", "skor", "score",
    "cross-sell", "basket", "rfm", "cohort", "trend",
    "karşılaştır", "compare", "korelasyon", "correlation",
    "anomal", "outlier", "forecast", "predict", "classif",
    "regress", "pivot", "stratej", "strateg",
)


def _compute_max_execute(user_query: str, uploaded_files: list | None = None) -> int:
    """Dynamic execute limit: simple=6, complex/large=10."""
    query_lower = (user_query or "").lower()
    is_complex = any(kw in query_lower for kw in _COMPLEX_KEYWORDS)
    total_size = sum(f.size for f in (uploaded_files or []))
    is_large = total_size > 10 * 1024 * 1024  # >10MB
    limit = 10 if (is_complex or is_large) else 6
    logger.info("Dynamic execute limit: %d (complex=%s, large=%s)", limit, is_complex, is_large)
    return limit


def build_agent(
    sandbox_manager: SandboxManager,
    thread_id: str,
    uploaded_files: list | None = None,
    user_query: str = "",
):
    """Build LangChain agent with OpenSandbox backend, skills, and minimal middleware.

    Returns:
        Tuple of (agent, checkpointer).
    """
    backend = sandbox_manager.get_or_create_sandbox(thread_id)

    # Progressive disclosure: compose system prompt with skills
    system_prompt = BASE_SYSTEM_PROMPT
    if uploaded_files:
        from src.sandbox.manager import SANDBOX_HOME
        file_list = "\n".join(
            f"- `{SANDBOX_HOME}/{f.name}` ({f.size:,} bytes)"
            for f in uploaded_files
        )
        system_prompt += (
            f"\n\n## Currently Uploaded Files\n\n"
            f"The user has uploaded the following files to the sandbox:\n{file_list}\n"
            f"These files are ready to use. Do NOT say 'no files uploaded'.\n"
        )

        required_skills = detect_required_skills(uploaded_files, user_query)
        if required_skills:
            system_prompt = compose_system_prompt(
                system_prompt,
                required_skills,
                uploaded_files=uploaded_files,
                user_query=user_query,
            )

    # 5 tools — no extra ls/glob/grep/write_file injected
    tools = [
        make_parse_file_tool(uploaded_files=uploaded_files),  # Pass files to avoid st.session_state in agent thread
        make_execute_tool(backend, session_id=thread_id),
        make_generate_html_tool(session_id=thread_id),
        make_visualization_tool(backend, session_id=thread_id),
        make_download_file_tool(backend, session_id=thread_id),
    ]

    # --- Smart interceptor: rate-limit + pip block + font auto-fix ---
    _seen_parse_files: set[str] = set()
    _execute_count = 0
    _max_execute = _compute_max_execute(user_query, uploaded_files)
    _total_blocked = 0  # Track total blocked attempts to prevent infinite loops
    _MAX_BLOCKED = 4   # After this many blocks, stop blocking and let code through
    _last_execute_failed = False  # Track if previous execute had error/assertion
    _correction_count = 0  # Track correction loop iterations (max 3)
    _MAX_CORRECTIONS = 3
    _consecutive_blocks = 0  # Track consecutive blocks without execute
    _MAX_CONSECUTIVE_BLOCKS = 3  # Circuit breaker: stop after 3 consecutive blocks

    def reset_interceptor_state():
        """Reset all interceptor counters for a new conversation turn.

        MUST be called before each agent.stream() to prevent state leaking
        between user messages (closure variables persist in cached agent).
        """
        nonlocal _execute_count, _total_blocked
        nonlocal _last_execute_failed, _correction_count, _consecutive_blocks
        _execute_count = 0
        _total_blocked = 0
        _last_execute_failed = False
        _correction_count = 0
        _consecutive_blocks = 0
        _seen_parse_files.clear()
        logger.info("[Interceptor] State reset for new turn")

    @wrap_tool_call
    def smart_interceptor(request, handler):
        nonlocal _execute_count, _total_blocked
        nonlocal _last_execute_failed, _correction_count, _consecutive_blocks
        tc = request.tool_call
        name = tc["name"]
        args = tc.get("args", {})
        tool_call_id = tc.get("id", "")

        # Circuit breaker: too many consecutive blocks = infinite loop
        if _consecutive_blocks >= _MAX_CONSECUTIVE_BLOCKS:
            logger.error("[Tool] CIRCUIT BREAKER triggered (%d consecutive blocks)", _consecutive_blocks)
            return ToolMessage(
                content=(
                    f"🛑 CIRCUIT BREAKER: {_consecutive_blocks} consecutive blocks detected.\n\n"
                    "You are in an infinite loop. STOP NOW.\n\n"
                    "Tell user: 'A loop occurred in tool calls. Please start a new conversation.'\n\n"
                    "DO NOT call any more tools. Write a message and STOP."
                ),
                tool_call_id=tool_call_id,
            )

        # Block duplicate parse_file
        if name == "parse_file":
            filename = args.get("filename", "")
            # Normalize path: remove /home/sandbox/ prefix if present
            filename_normalized = filename.replace("/home/sandbox/", "").strip("/")

            if filename_normalized in _seen_parse_files:
                logger.warning("[Tool] BLOCKED duplicate parse_file(%s)", filename)
                _audit.info("tool_blocked", extra={"tool_name": name, "action": "duplicate_parse", "blocked": True})
                _total_blocked += 1
                _consecutive_blocks += 1
                return ToolMessage(
                    content=(
                        f"⛔ BLOCKED: '{filename}' already parsed (block #{_total_blocked}, consecutive #{_consecutive_blocks})\n\n"
                        "NEVER call parse_file again — you already have the schema.\n"
                        "Do NOT use ls/cat/os.listdir — you know the file path.\n\n"
                        "SKIP this step. Go DIRECTLY to execute:\n"
                        f"df = pd.read_excel('/home/sandbox/{filename_normalized}')\n"
                        f"print(f'✅ {{df.shape[0]}} rows, {{df.shape[1]}} columns loaded')\n\n"
                        "Do NOT call parse_file/ls — call EXECUTE now."
                    ),
                    tool_call_id=tool_call_id,
                )
            _seen_parse_files.add(filename_normalized)

        # Rate-limit + guard execute
        if name == "execute":
            _execute_count += 1
            if _execute_count > _max_execute:
                logger.warning("[Tool] BLOCKED execute #%d (limit=%d)", _execute_count, _max_execute)
                _audit.info("tool_blocked", extra={"tool_name": name, "action": "rate_limit", "blocked": True, "execute_num": _execute_count})
                return ToolMessage(
                    content=f"⛔ Execute limit reached ({_max_execute}).\n"
                            "YOU MUST:\n"
                            "1. Be HONEST with user: tell real reason (not 'technical issue')\n"
                            "2. Do NOT use specific numbers from memory in text summary\n"
                            "3. You may show completed analysis with generate_html\n"
                            "4. General findings OK but specific numbers FORBIDDEN in chat",
                    tool_call_id=tool_call_id,
                )

            cmd = args.get("command", "")

            # Block pip install (direct or via subprocess)
            # Catches: pip install, subprocess.run/call/Popen, sys.executable pip
            pip_patterns = ["pip install", "pip3 install", "subprocess.run", "subprocess.call",
                           "subprocess.check_call", "subprocess.Popen", "sys.executable, '-m', 'pip'"]
            if any(p in cmd for p in pip_patterns):
                logger.warning("[Tool] BLOCKED pip/subprocess in execute")
                _audit.info("tool_blocked", extra={"tool_name": name, "action": "pip_install", "blocked": True})
                _execute_count -= 1  # Don't count blocked calls
                return ToolMessage(
                    content="⛔ pip install BLOCKED. All packages are PRE-INSTALLED in sandbox:\n"
                            "pandas, openpyxl, numpy, matplotlib, seaborn, plotly, duckdb, fpdf2, "
                            "scipy, scikit-learn, xlsxwriter, pdfplumber, weasyprint, python-pptx.\n\n"
                            "If you get ModuleNotFoundError: sandbox setup incomplete.\n"
                            "Tell user: 'Sandbox setup failed. Please start a new conversation.'\n"
                            "Execute quota NOT consumed.",
                    tool_call_id=tool_call_id,
                )

            # Detect hardcoded data (SCENARIO-INDEPENDENT, PER-ASSIGNMENT check)
            # Key insight: check each dict/list assignment INDIVIDUALLY for data access,
            # NOT the whole code block. Agent mixes duckdb.sql() + hardcoded m={...}
            # in same execute — global check lets hardcoding slip through.
            import re
            _data_access_ops = (".tolist()", ".values", "groupby", ".reset_index()",
                                ".to_dict(", ".iloc[", ".loc[", "duckdb.sql",
                                ".sum()", ".mean()", ".count()", ".nunique()",
                                ".sort_values(", ".nlargest(", ".nsmallest(",
                                ".apply(", ".agg(", ".pivot", ".fetchone()",
                                ".fetchall()", ".df()",
                                ".idxmax()", ".idxmin()", ".max()", ".min()",
                                ".head(", ".tail(", ".iterrows()", ".itertuples(",
                                "len(", "int(", "float(")

            def _is_hardcoded_assignment(match_text):
                """Check if a specific assignment uses data access ops."""
                return not any(da in match_text for da in _data_access_ops)

            # Find ALL dict assignments with large numbers: var = {...1234...}
            _hc_dicts = [m for m in re.finditer(
                r'\w+\s*=\s*\{[^}]*\b\d{3,}\b[^}]*\}', cmd
            ) if _is_hardcoded_assignment(m.group())]

            # Find ALL list-of-dict assignments: var = [{...1234...}]
            _hc_list_dicts = [m for m in re.finditer(
                r'\w+\s*=\s*\[\s*\{[^\]]*\b\d{3,}\b[^\]]*\]', cmd
            ) if _is_hardcoded_assignment(m.group())]

            # Find ALL list-of-numbers: var = [1234, 5678, 9012]
            _hc_lists = [m for m in re.finditer(
                r'\w+\s*=\s*\[\d{3,}(?:\s*,\s*\d{3,}){2,}[^\]]*\]', cmd
            ) if _is_hardcoded_assignment(m.group())]

            _all_hardcoded = _hc_dicts + _hc_list_dicts + _hc_lists
            if _all_hardcoded:
                examples = [m.group()[:60] for m in _all_hardcoded[:3]]
                examples_str = "\n  ".join(examples)
                logger.warning("[Tool] BLOCKED: %d hardcoded assignments: %s",
                               len(_all_hardcoded), examples)
                _audit.info("tool_blocked", extra={"tool_name": name, "action": "hardcoded_data", "blocked": True})
                _execute_count -= 1  # Don't count
                return ToolMessage(
                    content=f"⚠️ HARDCODED DATA DETECTED ({len(_all_hardcoded)} assignments)\n\n"
                            f"These assignments contain literal numbers without data operations:\n"
                            f"  {examples_str}\n\n"
                            "❌ Numbers must come from kernel variables, NOT copied from output.\n\n"
                            "✅ FIX: Use kernel variables directly:\n"
                            "  labels = df_result['column'].tolist()  # .tolist() from kernel\n"
                            "  values = df_result['metric'].tolist()  # .tolist() from kernel\n"
                            "  kpi = m['key_name']  # m dict from previous step\n\n"
                            "  # For dicts — compute from data:\n"
                            "  m = {'total': df['col'].nunique(), 'revenue': df['rev'].sum()}\n\n"
                            "REMEMBER: ALL variables from previous execute steps persist in kernel.\n"
                            "Rewrite using .tolist()/.values/.sum()/.mean() on kernel variables.\n"
                            "Execute quota NOT consumed.",
                    tool_call_id=tool_call_id,
                )

            # Block network requests (urllib, requests, wget, curl)
            # Fonts are pre-installed in the Docker image
            net_patterns = ["urllib.request", "requests.get", "urlretrieve", "urlopen",
                            "wget", "curl ", "http://", "https://"]
            if any(p in cmd for p in net_patterns) and "cdn.jsdelivr" not in cmd:
                logger.warning("[Tool] BLOCKED network request in execute")
                _audit.info("tool_blocked", extra={"tool_name": name, "action": "network_request", "blocked": True})
                _execute_count -= 1
                return ToolMessage(
                    content="⛔ Network requests BLOCKED from sandbox. "
                            "Fonts are pre-installed in Docker image. "
                            "Execute quota NOT consumed.",
                    tool_call_id=tool_call_id,
                )

            # Block bare shell commands (ls, find, cat, etc.)
            # Check both direct commands and python3 -c wrapped code
            bare_cmd = cmd.strip().split()[0] if cmd.strip() else ""
            shell_cmds = ("ls", "find", "cat", "head", "tail", "wc", "file", "stat")
            is_shell = (
                bare_cmd in shell_cmds
                or any(f"os.system('{sc}" in cmd or f'os.system("{sc}' in cmd for sc in shell_cmds)
                or any(f"os.popen('{sc}" in cmd or f'os.popen("{sc}' in cmd for sc in shell_cmds)
            )
            if is_shell:
                detected = bare_cmd if bare_cmd in shell_cmds else "shell command"
                logger.warning("[Tool] BLOCKED shell cmd '%s' in execute", detected)
                _audit.info("tool_blocked", extra={"tool_name": name, "action": "shell_cmd", "blocked": True})
                _execute_count -= 1
                _consecutive_blocks += 1
                file_list = ", ".join(f"/home/sandbox/{fn}" for fn in _seen_parse_files) if _seen_parse_files else "(parse_file not called yet)"
                return ToolMessage(
                    content=(
                        f"⛔ Shell command '{detected}' BLOCKED (consecutive #{_consecutive_blocks})\n\n"
                        f"Known files: {file_list}\n"
                        "Use pd.read_excel() or pd.read_csv() instead of shell commands.\n"
                        "Execute quota NOT consumed."
                    ),
                    tool_call_id=tool_call_id,
                )

            # Block Python filesystem exploration (os.listdir, glob, etc.)
            # NOTE: os.path.exists and os.path.getsize are ALLOWED (output verification)
            fs_patterns = ["os.listdir", "os.scandir", "glob.glob", "pathlib.Path"]
            if any(p in cmd for p in fs_patterns):
                logger.warning("[Tool] BLOCKED Python filesystem cmd in execute")
                _audit.info("tool_blocked", extra={"tool_name": name, "action": "filesystem_exploration", "blocked": True})
                _execute_count -= 1
                _consecutive_blocks += 1
                file_list = ", ".join(f"/home/sandbox/{fn}" for fn in _seen_parse_files) if _seen_parse_files else "(parse_file not called yet)"
                return ToolMessage(
                    content=(
                        f"⛔ Filesystem exploration BLOCKED (consecutive #{_consecutive_blocks})\n\n"
                        f"Known files: {file_list}\n"
                        "Use pd.read_excel() or pd.read_csv() directly.\n"
                        "Execute quota NOT consumed."
                    ),
                    tool_call_id=tool_call_id,
                )

            # Block large nrows= in read_excel/read_csv (must read ALL data for analysis)
            # Allow nrows<=10 for schema discovery
            nrows_match = re.search(r'nrows\s*=\s*(\d+)', cmd)
            if nrows_match and "fpdf" not in cmd.lower():
                nrows_val = int(nrows_match.group(1))
                if nrows_val > 10:
                    logger.warning("[Tool] BLOCKED nrows=%d sampling in execute #%d", nrows_val, _execute_count)
                    _audit.info("tool_blocked", extra={"tool_name": name, "action": "nrows_sampling", "blocked": True})
                    _execute_count -= 1
                    return ToolMessage(
                        content=f"⛔ nrows={nrows_val} BLOCKED — read ALL data for analysis. "
                                "nrows<=10 is OK for schema discovery, but analysis needs full data. "
                                "Execute quota NOT consumed.",
                        tool_call_id=tool_call_id,
                    )
                else:
                    logger.info("[Tool] Allowed nrows=%d for schema discovery", nrows_val)

            # Block only excessive sampling (>500 rows is likely reading full data via head)
            # Normal display/analysis usage (.head(60), .head(100), .head(200)) is fine
            sampling_limit = 500
            sampling_hits = re.findall(
                r'\.head\((\d+)\)|\.sample\((\d+)\)|\[:(\d+)\]|islice\([^,]+,\s*(\d+)\)', cmd
            )
            for match in sampling_hits:
                vals = [v for v in match if v]
                if not vals:
                    continue
                n = int(vals[0])
                if n > sampling_limit:
                    logger.warning("[Tool] BLOCKED large sampling (%d) in execute #%d", n, _execute_count)
                    _audit.info("tool_blocked", extra={"tool_name": name, "action": "large_sampling", "blocked": True})
                    _execute_count -= 1
                    return ToolMessage(
                        content=f"⛔ .head({n}) / [:{n}] BLOCKED — remove this sampling limit from code. "
                                "Use pd.read_excel(path) or pd.read_csv(path) without limits. "
                                "Execute quota NOT consumed. Resend same code without head/sample/slice.",
                        tool_call_id=tool_call_id,
                    )

            # Auto-fix Arial/Helvetica → DejaVu in PDF code
            is_pdf_code = "fpdf" in cmd.lower() or "FPDF" in cmd
            if is_pdf_code:
                original = cmd

                # Fix 1: Replace class-based FPDF with simple FPDF
                # class PDF(FPDF): ... causes font ordering issues
                if re.search(r'class\s+\w+\(FPDF\)', cmd):
                    # Remove class definition and its methods
                    cmd = re.sub(
                        r'class\s+\w+\(FPDF\):.*?(?=\n\S|\npdf\s*=|\Z)',
                        '',
                        cmd,
                        flags=re.DOTALL
                    )
                    # Replace CustomClass() with FPDF()
                    cmd = re.sub(r'pdf\s*=\s*\w+\(\)', 'pdf = FPDF()', cmd)
                    logger.info("[Tool] Replaced class-based FPDF with simple FPDF")

                # Fix 2: Replace Arial/Helvetica font names
                for bad_font in ("Arial", "Helvetica"):
                    if bad_font in cmd:
                        cmd = cmd.replace(f"'{bad_font}'", "'DejaVu'")
                        cmd = cmd.replace(f'"{bad_font}"', '"DejaVu"')

                # Fix 2b: Replace italic variants (DejaVu has no italic in sandbox)
                # 'I' → '', 'BI' → 'B'  (only for DejaVu/replaced fonts)
                cmd = re.sub(r"(set_font\(['\"]DejaVu['\"],\s*)['\"]I['\"]", r"\1''", cmd)
                cmd = re.sub(r"(set_font\(['\"]DejaVu['\"],\s*)['\"]BI['\"]", r"\1'B'", cmd)

                # Fix 2c: Replace wrong font paths (/usr/share → /home/sandbox)
                cmd = cmd.replace(
                    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                    '/home/sandbox/DejaVuSans.ttf'
                )
                cmd = cmd.replace(
                    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                    '/home/sandbox/DejaVuSans-Bold.ttf'
                )

                # Fix 3: Inject add_font if DejaVu used but not declared
                if "DejaVu" in cmd and "add_font" not in cmd:
                    font_setup = (
                        "pdf.add_font('DejaVu', '', '/home/sandbox/DejaVuSans.ttf', uni=True)\n"
                        "pdf.add_font('DejaVu', 'B', '/home/sandbox/DejaVuSans-Bold.ttf', uni=True)\n"
                    )
                    # Insert after first add_page()
                    cmd = re.sub(
                        r'(pdf\.add_page\(\))',
                        r'\1\n' + font_setup,
                        cmd,
                        count=1
                    )

                if cmd != original:
                    logger.info("[Tool] Auto-fixed fonts in execute #%d", _execute_count)
                    tc["args"]["command"] = cmd

                # pdf.cell() check removed — PDF is now generated via HTML+weasyprint
                # All numbers come from m[key] f-string interpolation in HTML template

            # --- Hardcoded metric variable check (SCENARIO-INDEPENDENT) ---
            # Detects: any_variable = large_number (>=1000) on its own line
            # Regex only matches plain `var = number`, not `var = df['col'].sum()`
            if _total_blocked >= _MAX_BLOCKED:
                logger.info("[Tool] Skipping variable assignment check (blocked %d times)", _total_blocked)
            else:
                # Safe variable patterns: UI/formatting constants + config
                safe_patterns = (
                    # UI/PDF formatting — MUST be fixed constants
                    "font", "size", "spacing", "margin", "width", "height",
                    "padding", "indent", "line_h", "cell_h", "col_w",
                    "page_", "title_", "header_", "row_h",
                    # Display limits & truncation
                    "limit", "top_n", "_to_show", "_displayed", "max_len",
                    "max_name", "truncat", "display_",
                    # Config/counting constants
                    "insight", "strategy", "section", "_num",
                    "_multiplier", "_percent", "growth", "max_", "min_",
                    "_count_", "batch", "chunk", "n_items", "n_rows",
                    # Chart config (not data)
                    "color", "label", "opacity", "border", "radius",
                    # Loop/index vars
                    "idx", "index", "step", "i_", "j_", "k_",
                )
                # Find: var = large_number (≥1000) on its own line
                hardcoded_vars = re.findall(
                    r'^(\w+)\s*=\s*(\d[\d,]*\.?\d*)\s*(?:#.*)?$', cmd, re.MULTILINE
                )
                fabricated = [
                    (var, val) for var, val in hardcoded_vars
                    if not any(sp in var.lower() for sp in safe_patterns)
                    and float(val.replace(',', '')) >= 1000  # Only large numbers are suspicious
                ]
                if fabricated:
                    examples = [f"{v}={n}" for v, n in fabricated[:3]]
                    logger.info("[Tool] BLOCKED hardcoded metric vars: %s", examples)
                    _execute_count -= 1
                    _total_blocked += 1
                    return ToolMessage(
                        content=f"⛔ Hardcoded metrics detected: {examples}.\n"
                                "These values must be COMPUTED from data or taken from kernel variables.\n"
                                "Variables persist in kernel — use variable references directly.\n"
                                "Execute quota NOT consumed.",
                        tool_call_id=tool_call_id,
                    )

        logger.info("[Tool] %s(%s)", name,
                    {k: str(v)[:80] for k, v in args.items()})
        result = handler(request)

        # Reset consecutive blocks on successful execute
        if name == "execute" and isinstance(result, ToolMessage):
            # If execute actually ran (not blocked), reset counter
            if "⛔" not in (result.content or ""):
                _consecutive_blocks = 0
                logger.info("[Tool] execute succeeded, reset consecutive_blocks")

        # Append remaining execute count + correction loop info
        if name == "execute" and isinstance(result, ToolMessage):
            content = result.content or ""
            remaining = _max_execute - _execute_count

            # Detect if this execute failed (error/assertion)
            has_error = any(kw in content for kw in (
                "Error", "Traceback", "AssertionError", "Exception",
                "KeyError", "ValueError", "TypeError", "NameError",
            ))
            has_validation_ok = "✅ Doğrulama OK" in content or "✅ Validation OK" in content

            if has_error:
                _last_execute_failed = True
                if _correction_count < _MAX_CORRECTIONS:
                    _correction_count += 1
                    suffix = (f"\n\n[Execute {_execute_count}/{_max_execute}, remaining: {remaining}]"
                              f" 🔄 CORRECTION {_correction_count}/{_MAX_CORRECTIONS}"
                              f" — THINK: what failed, why, how to fix.")
                else:
                    suffix = (f"\n\n[Execute {_execute_count}/{_max_execute}, remaining: {remaining}]"
                              f" ⛔ CORRECTION LIMIT ({_MAX_CORRECTIONS} attempts)."
                              f" SKIP this metric, inform user, continue with remaining analysis.")
            else:
                if _last_execute_failed and has_validation_ok:
                    _last_execute_failed = False
                    _correction_count = 0
                    suffix = f"\n\n[Execute {_execute_count}/{_max_execute}, remaining: {remaining}] ✅ Correction succeeded."
                else:
                    _last_execute_failed = False
                    suffix = f"\n\n[Execute {_execute_count}/{_max_execute}, remaining: {remaining}]"
                    if remaining <= 2:
                        suffix += " ⚠️ Last executes — combine analysis+PDF in single script."

            # ReAct enforcement: THOUGHT reminder
            suffix += "\n💭 Before next step → THOUGHT: [what you observed] → [what you will do] → [why]"

            result = ToolMessage(
                content=content + suffix,
                tool_call_id=result.tool_call_id,
            )

        logger.info("[Tool] %s done", name)
        _audit.info("tool_completed", extra={"tool_name": name, "action": "completed", "blocked": False, "execute_num": _execute_count if name == "execute" else None})
        return result

    # --- Middleware: only what we need ---
    model = resolve_model("anthropic:claude-sonnet-4-20250514")

    middleware = [
        create_summarization_middleware(model, backend),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
        PatchToolCallsMiddleware(),
        smart_interceptor,
    ]

    checkpointer = _get_checkpointer()

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
        checkpointer=checkpointer,
    )

    # LangGraph counts node transitions, not iterations.
    # Each ReAct step ≈ 2 transitions (agent node + tool node).
    agent = agent.with_config({"recursion_limit": REACT_MAX_ITERATIONS * 2 + 1})
    return agent, checkpointer, reset_interceptor_state


def get_or_build_agent(
    sandbox_manager: SandboxManager,
    thread_id: str,
    uploaded_files: list,
    user_query: str = "",
):
    """Cache agent in session state. Only rebuild when file set changes.

    Returns:
        Tuple of (agent, checkpointer, reset_fn).
        Call reset_fn() before each agent.stream() to reset interceptor counters.
    """
    file_fingerprint = tuple(
        (f.name, len(f.getvalue())) for f in (uploaded_files or [])
    )

    cached = st.session_state.get("_agent_cache")
    if cached and cached["fingerprint"] == file_fingerprint:
        return cached["agent"], cached["checkpointer"], cached["reset_fn"]

    agent, checkpointer, reset_fn = build_agent(
        sandbox_manager, thread_id, uploaded_files, user_query
    )
    st.session_state["_agent_cache"] = {
        "fingerprint": file_fingerprint,
        "agent": agent,
        "checkpointer": checkpointer,
        "reset_fn": reset_fn,
    }
    return agent, checkpointer, reset_fn
