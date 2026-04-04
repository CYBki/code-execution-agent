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
from langgraph.checkpoint.memory import MemorySaver

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

logger = logging.getLogger(__name__)

REACT_MAX_ITERATIONS = 30

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
                logger.info("[Tool] BLOCKED duplicate parse_file(%s)", filename)
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
                logger.info("[Tool] BLOCKED execute #%d (limit=%d)", _execute_count, _max_execute)
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
                logger.info("[Tool] BLOCKED pip/subprocess in execute")
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

            # Detect hardcoded chart/dashboard data (integrity check)
            # Catches: list/dict assignments that look like fake data
            import re
            hardcoded_patterns = [
                r"(top_\w+_data|hourly_distribution|monthly_data|chart_data|product_names|category_labels|customer_names)\s*=\s*\[(?:['\"]\[\w\s\]+['\"],?\s*){3,}\]",  # ['Product A', 'Product B', ...]
                r"(top_\w+_revenue|sales_data|revenue_data|amounts|values|totals)\s*=\s*\[\d+,?\s*\d+,?\s*\d+",  # [100000, 80000, 60000]
                # Dict literals with metric-like keys (dashboard_metrics = {...})
                r"(dashboard_metrics|dashboard_data|kpi_data|metrics_dict)\s*=\s*\{",
                # List-of-dict literals for chart data (segment_data = [{...}])
                r"(segment_data|category_data|country_data|hourly_data|daily_data|monthly_data|product_data)\s*=\s*\[",
            ]
            if any(re.search(pattern, cmd, re.IGNORECASE) for pattern in hardcoded_patterns):
                # Check if it's really hardcoded (not .tolist(), .reset_index(), from analysis)
                data_access = (".tolist()", ".values", "groupby", ".reset_index()",
                               ".to_dict(", ".iloc[", ".loc[", "duckdb.sql")
                if not any(da in cmd for da in data_access):
                    logger.warning("[Tool] WARNING: Potential hardcoded dashboard data detected")
                    _execute_count -= 1  # Don't count
                    return ToolMessage(
                        content="⚠️ HARDCODED DASHBOARD DATA DETECTED\n\n"
                                "You are creating variables with literal numbers like:\n"
                                "  dashboard_metrics = {'total_customers': 5863, ...}  ❌\n"
                                "  segment_data = [{'name': 'X', 'customers': 508}]  ❌\n"
                                "  hourly_data = [{'hour': 6, 'revenue': 890000}]  ❌\n\n"
                                "❌ This is HARDCODED/FABRICATED DATA. Dashboard will be WRONG.\n\n"
                                "✅ USE KERNEL VARIABLES from previous execute steps:\n"
                                "  seg = segment_summary.reset_index()\n"
                                "  seg_names = seg['customer_segment'].tolist()\n"
                                "  seg_revs = seg['toplam_ciro'].tolist()\n"
                                "  # m dict, country_analysis, hourly_pattern — all in kernel\n\n"
                                "REMEMBER: Variables persist in kernel across ALL execute calls.\n"
                                "Access them directly — NEVER copy numbers from output.\n\n"
                                "Rewrite using kernel variables. Execute quota NOT consumed.",
                        tool_call_id=tool_call_id,
                    )

            # Block network requests (urllib, requests, wget, curl)
            # Fonts are pre-installed in the Docker image
            net_patterns = ["urllib.request", "requests.get", "urlretrieve", "urlopen",
                            "wget", "curl ", "http://", "https://"]
            if any(p in cmd for p in net_patterns) and "cdn.jsdelivr" not in cmd:
                logger.info("[Tool] BLOCKED network request in execute")
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
                logger.info("[Tool] BLOCKED shell cmd '%s' in execute", detected)
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
                logger.info("[Tool] BLOCKED Python filesystem cmd in execute")
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
                    logger.info("[Tool] BLOCKED nrows=%d sampling in execute #%d", nrows_val, _execute_count)
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
                    logger.info("[Tool] BLOCKED large sampling (%d) in execute #%d", n, _execute_count)
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

            # --- Hardcoded metric variable check (runs for ALL execute, not just PDF) ---
            if _total_blocked >= _MAX_BLOCKED:
                logger.info("[Tool] Skipping variable assignment check (blocked %d times)", _total_blocked)
            else:
                # Block hardcoded metric variable assignments
                # Detect: total_revenue = 8832003 (literal number, not from data)
                metric_keywords = (
                    "revenue", "customer", "order", "vip",
                    "potential", "spend", "profit", "sales",
                    "ciro", "musteri", "siparis",
                )
                # Safe variable patterns: UI/formatting constants + config
                safe_patterns = (
                    # UI/PDF formatting — MUST be fixed constants (Rule 3 Clarification)
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
                )
                hardcoded_vars = re.findall(
                    r'^(\w+)\s*=\s*(\d[\d,]*\.?\d*)\s*(?:#.*)?$', cmd, re.MULTILINE
                )
                fabricated = [
                    (var, val) for var, val in hardcoded_vars
                    if any(kw in var.lower() for kw in metric_keywords)
                    and not any(sp in var.lower() for sp in safe_patterns)
                    and float(val.replace(',', '')) > 100  # config constants are small
                ]
                if fabricated:
                    examples = [f"{v}={n}" for v, n in fabricated[:3]]
                    logger.info("[Tool] BLOCKED hardcoded metric vars: %s", examples)
                    _execute_count -= 1
                    _total_blocked += 1
                    return ToolMessage(
                        content=f"⛔ Hardcoded metrics detected: {examples}. "
                                "These values must be COMPUTED from data or taken from kernel variables. "
                                "Variables persist in kernel — use m['total_revenue'], segment_summary, etc. "
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
        return result

    # --- Middleware: only what we need ---
    model = resolve_model("anthropic:claude-sonnet-4-20250514")

    middleware = [
        create_summarization_middleware(model, backend),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
        PatchToolCallsMiddleware(),
        smart_interceptor,
    ]

    # MemorySaver: in-process only, lost on restart.
    # For production: replace with SqliteSaver or PostgresSaver.
    checkpointer = MemorySaver()

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
