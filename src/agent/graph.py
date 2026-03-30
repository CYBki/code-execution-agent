"""Agent builder — LangChain create_agent + Daytona sandbox.

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
    """Build LangChain agent with Daytona backend, skills, and minimal middleware.

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
        make_parse_file_tool(),
        make_execute_tool(backend),
        make_generate_html_tool(session_id=thread_id),
        make_visualization_tool(backend, session_id=thread_id),
        make_download_file_tool(backend, session_id=thread_id),
    ]

    # --- Smart interceptor: rate-limit + pip block + font auto-fix ---
    _seen_parse_files: set[str] = set()
    _execute_count = 0
    _max_execute = _compute_max_execute(user_query, uploaded_files)
    _schema_discovered = False  # Track if first execute did schema discovery
    _total_blocked = 0  # Track total blocked attempts to prevent infinite loops
    _MAX_BLOCKED = 4   # After this many blocks, stop blocking and let code through
    _last_execute_failed = False  # Track if previous execute had error/assertion
    _correction_count = 0  # Track correction loop iterations (max 2)
    _MAX_CORRECTIONS = 2

    def reset_interceptor_state():
        """Reset all interceptor counters for a new conversation turn.

        MUST be called before each agent.stream() to prevent state leaking
        between user messages (closure variables persist in cached agent).
        """
        nonlocal _execute_count, _schema_discovered, _total_blocked
        nonlocal _last_execute_failed, _correction_count
        _execute_count = 0
        _schema_discovered = False
        _total_blocked = 0
        _last_execute_failed = False
        _correction_count = 0
        _seen_parse_files.clear()
        logger.info("[Interceptor] State reset for new turn")

    @wrap_tool_call
    def smart_interceptor(request, handler):
        nonlocal _execute_count, _schema_discovered, _total_blocked
        nonlocal _last_execute_failed, _correction_count
        tc = request.tool_call
        name = tc["name"]
        args = tc.get("args", {})
        tool_call_id = tc.get("id", "")
        _phase = "-"  # Set per-execute below

        # Block duplicate parse_file
        if name == "parse_file":
            filename = args.get("filename", "")
            if filename in _seen_parse_files:
                logger.info("[Tool] BLOCKED duplicate parse_file(%s)", filename)
                return ToolMessage(
                    content=(
                        f"'{filename}' zaten parse edildi — schema sende var. "
                        "Şimdi DOĞRUDAN şunu yap:\n"
                        f"xls = pd.ExcelFile('/home/daytona/{filename}')\n"
                        "for sheet in xls.sheet_names:\n"
                        "    df = pd.read_excel('/home/daytona/{filename}', sheet_name=sheet)\n"
                        "    df.to_csv(f'/home/daytona/temp_{{sheet}}.csv', index=False); del df\n"
                        "Ardından DuckDB ile tüm analizleri ve PDF'i TEK execute'da tamamla."
                    ),
                    tool_call_id=tool_call_id,
                )
            _seen_parse_files.add(filename)

        # Rate-limit + guard execute
        if name == "execute":
            _execute_count += 1
            if _execute_count > _max_execute:
                logger.info("[Tool] BLOCKED execute #%d (limit=%d)", _execute_count, _max_execute)
                return ToolMessage(
                    content=f"⛔ Execute limit reached ({_max_execute}).\n"
                            "YAPMAN GEREKENLER:\n"
                            "1. Kullanıcıya DÜRÜST ol: '⚠️ PDF üretilemedi. Sebep: [gerçek sebep]. "
                            "Tamamlanan analizler: [liste]. Tekrar denemek için oturumu sıfırlayın.'\n"
                            "2. Metin özetinde SAYI KULLANMA — önceki execute'larda gördüğün rakamları hafızadan YAZMA\n"
                            "3. 'Teknik sorun' DEME — gerçek sebebi söyle (kural ihlali, blok, hata)\n"
                            "4. generate_html ile tamamlanmış analiz çıktısını gösterebilirsin (dashboard)\n"
                            "5. Genel bulgular OK ama spesifik sayı ($11.78, %76, 278,329) YASAK",
                    tool_call_id=tool_call_id,
                )

            # Phase tracking: exploration (first 2) → analysis → report (last 2)
            _phase = "exploration" if _execute_count <= 2 else (
                "report" if _execute_count >= _max_execute - 1 else "analysis"
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
                    content="⛔ pip install YASAK. Tüm paketler sandbox'ta PRE-INSTALLED:\n"
                            "pandas, openpyxl, numpy, matplotlib, seaborn, plotly, duckdb, fpdf2, "
                            "scipy, scikit-learn, xlsxwriter, pdfplumber, weasyprint.\n\n"
                            "EĞER 'ModuleNotFoundError: openpyxl' ALIRSAN:\n"
                            "→ Sandbox paketleri henüz yüklenirken sorun oldu.\n"
                            "→ Kullanıcıya DÜRÜST ol: 'Sandbox hazırlığı tamamlanamadı. Lütfen oturumu sıfırlayın.'\n"
                            "→ pip install DENEME — bu kural ihlalidir ve execute hakkını harcarsın.",
                    tool_call_id=tool_call_id,
                )

            # Block network requests (urllib, requests, wget, curl)
            # Fonts are pre-installed at /home/daytona/*.ttf — no download needed
            net_patterns = ["urllib.request", "requests.get", "urlretrieve", "urlopen",
                            "wget", "curl ", "http://", "https://"]
            if any(p in cmd for p in net_patterns) and "cdn.jsdelivr" not in cmd:
                logger.info("[Tool] BLOCKED network request in execute")
                _execute_count -= 1
                return ToolMessage(
                    content="⛔ Sandbox'tan dış ağ isteği YASAK. "
                            "Font dosyaları zaten kurulu: /home/daytona/DejaVuSans.ttf ve DejaVuSans-Bold.ttf. "
                            "İndirme yapma, doğrudan kullan. "
                            "Execute hakkın düşmedi.",
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
                # Show real filenames from parse_file calls
                file_list = "\n".join(f"  - /home/daytona/{fn}" for fn in _seen_parse_files) if _seen_parse_files else ""
                instruction = (
                    f"⛔ Shell command '{detected}' YASAK — ls/find/cat kullanma.\n\n"
                    f"parse_file() zaten çalıştı, schema'yı gördün. Dosya(lar):\n{file_list or '  (parse_file henüz çağrılmadı)'}\n\n"
                    "ŞİMDİ NE YAPMALISIN:\n"
                    "1. ls/cat YAPMA — dosya zaten orada, schema'yı biliyorsun\n"
                    "2. DÜŞÜNCE yaz: 'parse_file'dan gördüğüm kolonlar: [...]. Şimdi pd.read_excel ile okuyacağım.'\n"
                    "3. execute() çağır:\n"
                    "   df = pd.read_excel('/home/daytona/DOSYA_ADI_BURAYA.xlsx')\n"
                    "   print(df.shape)  # doğrulama\n"
                )
                return ToolMessage(content=instruction, tool_call_id=tool_call_id)

            # Block Python filesystem exploration (os.listdir, glob, etc.)
            # NOTE: os.path.exists and os.path.getsize are ALLOWED (Rule 8: output verification)
            fs_patterns = ["os.listdir", "os.scandir", "glob.glob", "pathlib.Path"]
            if any(p in cmd for p in fs_patterns):
                logger.info("[Tool] BLOCKED Python filesystem cmd in execute")
                _execute_count -= 1
                # Show real filenames from parse_file calls
                file_list = "\n".join(f"  - /home/daytona/{fn}" for fn in _seen_parse_files) if _seen_parse_files else ""
                instruction = (
                    f"⛔ Filesystem exploration (os.listdir, glob, pathlib) YASAK.\n\n"
                    f"parse_file() zaten çalıştı, schema'yı gördün. Dosya(lar):\n{file_list or '  (parse_file henüz çağrılmadı)'}\n\n"
                    "ŞİMDİ NE YAPMALISIN:\n"
                    "1. os.listdir/glob YAPMA — dosya yollarını biliyorsun\n"
                    "2. DÜŞÜNCE yaz: 'parse_file'dan kolonları gördüm, şimdi pd.read_excel ile okuyacağım'\n"
                    "3. execute() çağır:\n"
                    "   df = pd.read_excel('/home/daytona/DOSYA_ADI.xlsx')\n"
                    "   print(df.shape)  # doğrulama\n"
                )
                return ToolMessage(content=instruction, tool_call_id=tool_call_id)

            # Track schema discovery (first execute should discover columns)
            if _execute_count == 1:
                has_schema_check = any(k in cmd for k in (
                    "df.columns", ".columns", "df.dtypes", ".dtypes",
                    ".info()", "columns.tolist",
                ))
                if has_schema_check:
                    _schema_discovered = True
                    logger.info("[Tool] execute #1: schema discovery detected")

            # If first execute is NOT schema discovery, warn in response
            if _execute_count == 2 and not _schema_discovered:
                logger.warning("[Tool] execute #2 without prior schema discovery")

            # Block large nrows= in read_excel/read_csv (must read ALL data)
            # Allow nrows<=10 for schema discovery (Rule 1: nrows=5)
            nrows_match = re.search(r'nrows\s*=\s*(\d+)', cmd)
            if nrows_match and "fpdf" not in cmd.lower():
                nrows_val = int(nrows_match.group(1))
                if nrows_val > 10:
                    logger.info("[Tool] BLOCKED nrows=%d sampling in execute #%d", nrows_val, _execute_count)
                    _execute_count -= 1
                    return ToolMessage(
                        content=f"⛔ nrows={nrows_val} YASAK — TÜM veriyi oku. "
                                "Schema keşfi için nrows=5 serbest, ama analiz için tüm veriyi yükle. "
                                "pd.read_excel('/home/daytona/dosya.xlsx') kullan.",
                        tool_call_id=tool_call_id,
                    )
                elif _seen_parse_files:
                    # parse_file already ran — schema exists, block re-check
                    logger.info("[Tool] BLOCKED schema re-check nrows=%d (parse_file already ran)", nrows_val)
                    _execute_count -= 1
                    fname = next(iter(_seen_parse_files), "dosya.xlsx")
                    return ToolMessage(
                        content=(
                            f"⛔ Schema re-check BLOKLANDΙ (nrows={nrows_val}). "
                            "parse_file zaten schema verdi — nrows ile tekrar okuma YAPMA. "
                            "Hemen CSV dönüşümüne geç:\n"
                            f"xls = pd.ExcelFile('/home/daytona/{fname}')\n"
                            "for sheet in xls.sheet_names:\n"
                            f"    df = pd.read_excel('/home/daytona/{fname}', sheet_name=sheet)\n"
                            "    df.to_csv(f'/home/daytona/temp_{{sheet}}.csv', index=False); del df\n"
                            "Execute hakkın düşmedi."
                        ),
                        tool_call_id=tool_call_id,
                    )
                else:
                    logger.info("[Tool] Allowed nrows=%d for schema discovery", nrows_val)

            # Block sampling in analysis (head/sample/slice with large N, islice)
            # Exploration phase: allow .head(200) for data discovery
            # Analysis/report phase: strict limit (top-50 for display only)
            sampling_limit = 200 if _phase == "exploration" else 50
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
                        content=f"⛔ .head({n}) / [:{n}] BLOKLANDI — bu satır sınırını koddan KALDIR. "
                                f"Sadece `df = pd.read_excel(path)` veya `pd.read_csv(path)` kullan (limit yok). "
                                "Dosya okunabilir, openpyxl kurulu, sorun yok — sadece örnekleme satırını sil. "
                                "Execute hakkın düşmedi, aynı kodu head/sample/slice olmadan tekrar gönder.",
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

                # Fix 2c: Replace wrong font paths (/usr/share → /home/daytona)
                cmd = cmd.replace(
                    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                    '/home/daytona/DejaVuSans.ttf'
                )
                cmd = cmd.replace(
                    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                    '/home/daytona/DejaVuSans-Bold.ttf'
                )

                # Fix 3: Inject add_font if DejaVu used but not declared
                if "DejaVu" in cmd and "add_font" not in cmd:
                    font_setup = (
                        "pdf.add_font('DejaVu', '', '/home/daytona/DejaVuSans.ttf', uni=True)\n"
                        "pdf.add_font('DejaVu', 'B', '/home/daytona/DejaVuSans-Bold.ttf', uni=True)\n"
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

                # --- Hardcoded metric variable check (skip if too many blocks) ---
                if _total_blocked >= _MAX_BLOCKED:
                    logger.info("[Tool] Skipping variable assignment check (blocked %d times)", _total_blocked)
                else:
                    # Block hardcoded metric variable assignments in PDF code
                    # Detect: total_revenue = 8832003 (literal number, not from data)
                    metric_keywords = (
                        "revenue", "customer", "order", "vip",
                        "potential", "spend", "profit", "sales",
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
                        logger.info("[Tool] BLOCKED hardcoded metric vars in PDF: %s", examples)
                        _execute_count -= 1
                        _total_blocked += 1
                        return ToolMessage(
                            content=f"⛔ RULE 3 İHLALİ: Metrik değişkenlere hardcoded sayı atanmış: {examples}. "
                                    "Bu değerler veriyi okuyup hesaplanmalı (pd.read_excel → df.sum() vb.). "
                                    "Analiz ve PDF TEK BİR SCRIPT'te olmalı — ayrı execute'a bölme. "
                                    "Veriyi oku → hesapla → validate → PDF üret, hepsi tek script içinde.",
                            tool_call_id=tool_call_id,
                        )

                # pdf.cell() check removed — PDF is now generated via HTML+weasyprint
                # All numbers come from m[key] f-string interpolation in HTML template

        logger.info("[Tool] %s(%s) phase=%s", name,
                    {k: str(v)[:80] for k, v in args.items()},
                    _phase if name == "execute" else "-")
        result = handler(request)

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
                    suffix = (f"\n\n[Execute {_execute_count}/{_max_execute}, kalan: {remaining}]"
                              f" 🔄 DÜZELTME DÖNGÜSÜ {_correction_count}/{_MAX_CORRECTIONS}"
                              f" — DÜŞÜNCE yaz: ne fail etti, neden, nasıl düzelteceksin.")
                else:
                    suffix = (f"\n\n[Execute {_execute_count}/{_max_execute}, kalan: {remaining}]"
                              f" ⛔ DÜZELTME LİMİTİ AŞILDI ({_MAX_CORRECTIONS} deneme)."
                              f" Bu metriği ATLA, kullanıcıya bildir, kalan analizle devam et.")
            else:
                if _last_execute_failed and has_validation_ok:
                    # Correction succeeded
                    _last_execute_failed = False
                    _correction_count = 0
                    suffix = f"\n\n[Execute {_execute_count}/{_max_execute}, kalan: {remaining}] ✅ Düzeltme başarılı."
                else:
                    _last_execute_failed = False
                    suffix = f"\n\n[Execute {_execute_count}/{_max_execute}, kalan: {remaining}]"
                    if remaining <= 2:
                        suffix += " ⚠️ Son execute'larını analiz+PDF tek script olarak kullan."

            # Always append DÜŞÜNCE reminder for ReAct enforcement
            suffix += "\n💭 Sonraki adımdan ÖNCE → DÜŞÜNCE: [ne gözlemledin] → [ne yapacaksın] → [neden]"

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
