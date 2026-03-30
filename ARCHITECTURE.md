# Architecture Diagram

## System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         STREAMLIT UI (app.py)                            │
│  ┌──────────────┐  ┌──────────────────────────────────────────────────┐  │
│  │   Sidebar     │  │              Chat Interface                      │  │
│  │              │  │                                                  │  │
│  │ 📁 File Upload│  │  User: "Bu veriyi analiz et..."                 │  │
│  │ satis.xlsx   │  │                                                  │  │
│  │              │  │  🤖 Agent:                                       │  │
│  │ [🔄 New Chat]│  │  ├─ 📄 Parsing file...        ✓                 │  │
│  │              │  │  ├─ 🐍 Running code...        ✓                 │  │
│  │ Model: Claude│  │  ├─ 🌐 Generating HTML...     ✓                 │  │
│  │ Sandbox:     │  │  ├─ 🐍 Creating PDF...       ✓                 │  │
│  │   Daytona    │  │  ├─ 📥 Preparing download...  ✓                 │  │
│  └──────────────┘  │  └─ 💬 Streaming response...                    │  │
│                     │                                                  │  │
│                     │  [📊 HTML Dashboard — interactive iframe]        │  │
│                     │  [📥 rapor.pdf indir]                            │  │
│                     └──────────────────────────────────────────────────┘  │
└────────────┬────────────────────────────┬────────────────────────────────┘
             │ file upload                │ user query
             ▼                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     SKILL SYSTEM (src/skills/)                            │
│                                                                          │
│  ┌─────────────────────┐    ┌────────────────────────────────────────┐   │
│  │  registry.py         │    │  loader.py                             │   │
│  │                     │    │                                        │   │
│  │ detect_required_    │───▶│ load_skill("xlsx")                     │   │
│  │   skills()          │    │   → SKILL.md                           │   │
│  │                     │    │                                        │   │
│  │ detect_reference_   │───▶│ load_reference()                       │   │
│  │   files()           │    │   → large_files.md                     │   │
│  │                     │    │   → multi_file_joins.md                │   │
│  │ Triggers:           │    │                                        │   │
│  │  • file extension   │    │ compose_system_prompt()                 │   │
│  │  • file size (≥40MB)│    │   = base + skills + references         │   │
│  │  • keywords         │    │                                        │   │
│  │  • file count (≥2)  │    └────────────────────────────────────────┘   │
│  └─────────────────────┘                                                 │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │ composed system prompt
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│       LangChain create_agent + LangGraph MemorySaver (src/agent/)       │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  graph.py — build_agent() / get_or_build_agent() [session cache]   │  │
│  │                                                                    │  │
│  │  Claude Sonnet 4 ◄── English System Prompt (prompts.py)            │  │
│  │       │               (user responses in Turkish)                  │  │
│  │       │               + uploaded file paths                        │  │
│  │       │               + progressive skill content                  │  │
│  │       │                                                            │  │
│  │       │  ReAct Loop: Think → Act → Observe → Think → ...           │  │
│  │       │  Max iterations: 30 (recursion_limit=61)                   │  │
│  │       │                                                            │  │
│  │       ├──▶ Tool: parse_file             (custom, LOCAL)            │  │
│  │       ├──▶ Tool: execute                (built-in, DAYTONA)        │  │
│  │       ├──▶ Tool: generate_html          (custom, BROWSER iframe)   │  │
│  │       ├──▶ Tool: create_visualization   (custom, DAYTONA PNG)      │  │
│  │       └──▶ Tool: download_file          (custom, DAYTONA → browser)│  │
│  │                                                                    │  │
│  │       Output formats (single or multi-format):                     │  │
│  │       • PDF: weasyprint (HTML→PDF, Turkish chars)                  │  │
│  │       • PPTX: python-pptx + matplotlib charts (downloadable)       │  │
│  │       • HTML: Chart.js interactive dashboard (browser iframe)      │  │
│  │       • Excel: openpyxl/xlsxwriter (editable data)                 │  │
│  │       User can request: single format OR multi-format combo        │  │
│  │                                                                    │  │
│  │  ┌─── BLOCKED by smart_interceptor (returns ToolMessage) ───────┐  │  │
│  │  │  ls, find, cat, head, tail (shell cmds in execute)           │  │  │
│  │  │  subprocess / pip install / network requests                 │  │  │
│  │  │  nrows>10 sampling / nrows≤10 after parse_file (schema ok)   │  │  │
│  │  │  No filesystem tools injected (manual tool set only)         │  │  │
│  │  └──────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────── MIDDLEWARE STACK (manually configured) ───────────────┐  │
│  │  ① SummarizationMiddleware       (condenses old messages)           │  │
│  │  ② AnthropicPromptCachingMiddleware  (cache breakpoints)            │  │
│  │  ③ PatchToolCallsMiddleware                                         │  │
│  │  ④ smart_interceptor (@wrap_tool_call)                              │  │
│  │       • BLOCKS: shell cmds (ls/find/cat/head/tail) in execute      │  │
│  │       • BLOCKS: subprocess / pip install in execute                │  │
│  │       • BLOCKS: network requests (urllib/requests/wget/curl)       │  │
│  │       • BLOCKS: nrows>10 in read_excel/read_csv (sampling)        │  │
│  │       • BLOCKS: nrows≤10 schema re-check after parse_file ran     │  │
│  │         → redirects agent to CSV conversion immediately            │  │
│  │       • BLOCKS: duplicate parse_file (path normalized) → CSV code │  │
│  │         (strips /home/daytona/ prefix for duplicate detection)    │  │
│  │       • BLOCKS: execute > 6 simple / 10 complex (dynamic limit)   │  │
│  │       • CIRCUIT BREAKER: stops after 2 consecutive blocks to      │  │
│  │         prevent infinite loops (parse_file→ls→parse_file→...)     │  │
│  │       • AUTO-FIX: Arial/Helvetica → DejaVu fonts in PDF code      │  │
│  │       • AUTO-FIX: Injects add_font() if missing in FPDF code      │  │
│  │       • LOGS: all tool calls with truncated args                   │  │
│  │                                                                     │  │
│  │  NOTE: No auto-injected tools (unlike create_deep_agent).           │  │
│  │  Only the 5 explicit tools above are available.                     │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────── CHECKPOINTER ─────────────────────────────────────────┐  │
│  │  MemorySaver — conversation state persisted per thread_id           │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└──────────┬──────────────┬──────────────┬───────────────┬─────────────────┘
           │              │              │               │
           ▼              ▼              ▼               ▼
   ┌────────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────────┐
   │ parse_file │  │gen_html  │  │create_viz    │  │download_file │
   │ (LOCAL)    │  │(BROWSER) │  │(DAYTONA)     │  │(DAYTONA)     │
   │ CUSTOM     │  │ CUSTOM   │  │ CUSTOM       │  │ CUSTOM       │
   │            │  │          │  │              │  │              │
   │ • headers  │  │ • Plotly │  │ • matplotlib │  │ • read file  │
   │ • 100 rows │  │ • D3.js  │  │ • seaborn    │  │   from sbx   │
   │ • dtypes   │  │ • CSS    │  │ • PNG output │  │ • st download│
   │ • file size│  │ • tables │  │              │  │   button     │
   │ • sheets   │  │ • Chart.j│  │              │  │              │
   └─────┬──────┘  └─────┬────┘  └──────┬───────┘  └──────┬───────┘
         │               │              │                  │
         │               ▼              │                  │
         │  ┌─────────────────────┐     │                  │
         │  │  ArtifactStore      │◄────┘                  │
         │  │  (thread-safe       │◄────────────────────────┘
         │  │   global singleton) │
         │  │                     │
         │  │  • add_html()       │──▶ pop_html()     → components.html()
         │  │  • add_chart()      │──▶ pop_charts()   → st.image()
         │  │  • add_download()   │──▶ pop_downloads()→ st.download_button()
         │  └─────────────────────┘
         │  (src/tools/artifact_store.py)
         │
         ▼
   st.session_state["uploaded_files"]  (reads file bytes directly)

┌──────────────────────────────────────────────────────────────────────────┐
│              DAYTONA SANDBOX — LangChain-Daytona backend                 │
│                       (src/sandbox/manager.py)                           │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  SandboxManager                                                    │  │
│  │                                                                    │  │
│  │  Lifecycle:                                                        │  │
│  │  • _find_existing(thread_id)   — list by label, skip DESTROYED     │  │
│  │  • get_or_create_sandbox()     — find or create + _ensure_started  │  │
│  │  • _ensure_started()           — handle STOPPED/ARCHIVED states    │  │
│  │  • stop() + atexit cleanup     — graceful shutdown                 │  │
│  │                                                                    │  │
│  │  DaytonaSandbox (shared): timeout=180s, same instance for agent   │  │
│  │                            AND _install_packages (ensures pkgs     │  │
│  │                            are visible to agent code)             │  │
│  │                                                                    │  │
│  │  Background Package Install (_install_packages in daemon thread):  │  │
│  │  ┌──────────────────────────────────────────────────────────────┐  │  │
│  │  │  Phase 1 (FONTS):     cp /usr/share/fonts/truetype/dejavu/  │  │  │
│  │  │                       → /home/daytona/DejaVuSans*.ttf       │  │  │
│  │  │  Phase 2 (PACKAGES):  fpdf2, pandas, openpyxl, xlsxwriter,  │  │  │
│  │  │                       numpy, matplotlib, seaborn, plotly,   │  │  │
│  │  │                       pdfplumber, duckdb, scipy, scikit-learn│  │  │
│  │  │  Phase 3 (VERIFY):    python3 -c 'import fpdf, pandas,      │  │  │
│  │  │                       openpyxl; print("VERIFY_OK")'          │  │  │
│  │  │                                                              │  │  │
│  │  │  Strategy: ONE package per pip install + exit code check     │  │  │
│  │  │  Total install time: ~35s                                    │  │  │
│  │  │  _packages_ready.set() in finally block (always fires)      │  │  │
│  │  └──────────────────────────────────────────────────────────────┘  │  │
│  │                                                                    │  │
│  │  File Upload:                                                      │  │
│  │  • Native: backend.upload_files([(path, bytes)])  (best for large) │  │
│  │  • Fallback: chunked base64+execute (512KB chunks)                │  │
│  │  • Runs after wait_until_ready(timeout=120)                        │  │
│  │                                                                    │  │
│  │  Sandbox Config:                                                   │  │
│  │  • Home: /home/daytona                                             │  │
│  │  • Labels: {"thread_id": session_id}                               │  │
│  │  • auto_delete_interval: 3600s (1 hour TTL)                        │  │
│  │  • Pre-downloaded fonts at /home/daytona/DejaVuSans*.ttf           │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

## Data Flow — Typical Analysis Request

```
┌─────────┐    ┌──────────────┐    ┌───────────────────────┐
│  User   │───▶│  Streamlit   │───▶│  init_session()       │
│ opens   │    │  app.py      │    │  • session_id = uuid  │
│ browser │    │              │    │  • SandboxManager()   │
└─────────┘    └──────────────┘    │  • prewarm thread:   │
                                   │    get_or_create_sbx  │
                                   │    _install_packages  │
                                   └───────────────────────┘

┌──────────┐   ┌──────────────────────────────────────────────────┐
│  User    │   │  chat.py — render_chat()                          │
│ uploads  │──▶│                                                   │
│ file +   │   │  1. Store in session_state["uploaded_files"]      │
│ query    │   │  2. get_or_build_agent() [cached by fingerprint]  │
│          │   │  3. wait_until_ready(120s) — block for packages   │
│          │   │  4. upload_files() — base64 push to sandbox       │
└──────────┘   │  5. agent.stream(query) with stream_mode=updates  │
               └───────────────────────┬──────────────────────────┘
                                       │
                                       ▼
               ┌────────────────────────────────────────────────────┐
               │  Agent ReAct Loop (LangGraph + Claude Sonnet 4)    │
               │                                                    │
               │  Ideal flow — small file (<40MB):                  │
               │  ① parse_file → schema + file_size_mb              │
               │  ② execute(clean + pickle)                         │
               │  ③ execute(analysis + m dict + WeasyPrint PDF)     │
               │  ④ download_file(pdf_path)                         │
               │                                                    │
               │  Ideal flow — large file (≥40MB, DuckDB):          │
               │  ① parse_file → schema + ⚠️ DuckDB warning         │
               │  ② execute(Excel→CSV: sheet auto-detect,           │
               │             csv_paths dict for all sheets)          │
               │  ③ execute(DuckDB queries + m dict +               │
               │             WeasyPrint PDF) ← ONE execute           │
               │  ④ download_file(pdf_path)                         │
               │                                                    │
               │  Multi-sheet: same cols→UNION ALL,                 │
               │  related→JOIN, independent→separate queries        │
               │                                                    │
               │  Guardrails (smart_interceptor):                   │
               │  • parse_file: 1 per file, dup→CSV conv code       │
               │  • execute: max 6 simple / 10 complex              │
               │  • ls/glob/grep/find: always blocked               │
               │  • nrows≤10 after parse_file: blocked              │
               │  • nrows>10: always blocked (use full data)        │
               │  • pip/subprocess/network: always blocked          │
               │  • Arial/Helvetica: auto-replaced with DejaVu      │
               └────────────────────────┬───────────────────────────┘
                                        │
                                        ▼
               ┌────────────────────────────────────────────────────┐
               │  chat.py — Post-stream rendering                   │
               │                                                    │
               │  • artifact_store.pop_html()      → iframe render  │
               │  • artifact_store.pop_charts()    → st.image()     │
               │  • artifact_store.pop_downloads() → download btn   │
               │  • collected_steps saved to message history         │
               │  • Re-rendered on page rerun (persistent steps)    │
               └────────────────────────────────────────────────────┘
```

## Smart Interceptor — Tool Call Control Layer

```
                    ┌────────────────────────┐
                    │  Agent calls a tool     │
                    │  (any tool_use block)   │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │  smart_interceptor     │
                    │  (@wrap_tool_call)     │
                    └───────────┬────────────┘
                                │
              ┌─────────────────┼──────────────────┐
              │                 │                   │
              ▼                 ▼                   ▼
     ┌─────────────┐  ┌─────────────────┐  ┌──────────────────┐
     │ BLOCK?      │  │ RATE-LIMIT?     │  │ AUTO-FIX?        │
     │             │  │                 │  │                  │
     │ ls/find/cat │  │ execute>6/10    │  │ FPDF + Arial     │
     │ glob        │  │ → ToolMessage:  │  │ → replace with   │
     │ subprocess  │  │   "limit       │  │   DejaVu font    │
     │ pip install │  │    reached"     │  │                  │
     │ network req │  │                 │  │ FPDF + no        │
     │ nrows>10    │  │ dup parse_file  │  │ add_font()       │
     │ nrows≤10    │  │ (path norm'd)   │  │ → inject         │
     │ after parse │  │ → CSV conv      │  │   add_font()     │
     │             │  │   instructions  │  │                  │
     │ Circuit     │  │                 │  │                  │
     │ breaker:    │  │ 2+ consecutive  │  │                  │
     │ 2 consec.   │  │ blocks → STOP   │  │                  │
     │ blocks      │  │ → force error   │  │                  │
     └──────┬──────┘  └────────┬────────┘  └────────┬─────────┘
            │                  │                     │
            ▼                  ▼                     ▼
     ┌─────────────┐  ┌─────────────────┐  ┌──────────────────┐
     │Return       │  │ Return          │  │ Modify tc args   │
     │ ToolMessage │  │ ToolMessage     │  │ then call        │
     │ (no execute)│  │ (no execute)    │  │ handler(request) │
     └─────────────┘  └─────────────────┘  └──────────────────┘
```

## Session & Sandbox Lifecycle

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser Tab Opens                                                │
│                                                                  │
│  app.py → init_session()                                         │
│     │                                                            │
│     ├─ session_state defaults: messages=[], uploaded_files=[]     │
│     ├─ session_id = uuid4()                                      │
│     ├─ SandboxManager() → self._client = Daytona()               │
│     │                                                            │
│     └─ Background Thread (_prewarm):                             │
│        ├─ get_or_create_sandbox(session_id)                      │
│        │   ├─ _find_existing(thread_id) → list by label          │
│        │   ├─ OR create(labels={"thread_id":...}, TTL=3600s)     │
│        │   ├─ _ensure_started() → handle STOPPED/ARCHIVED        │
│        │   └─ self._backend = DaytonaSandbox(timeout=180)        │
│        │                                                         │
│        └─ _install_packages (daemon thread):                     │
│           ├─ Phase 1: DejaVuSans fonts + system deps (~3s)       │
│           ├─ Phase 2: check installed packages, pip missing only │
│           │   • Critical (blocks ready): weasyprint, pandas,     │
│           │     openpyxl, xlsxwriter, numpy, matplotlib,         │
│           │     seaborn, plotly, scipy, scikit-learn, python-pptx│
│           │   • Optional (background): pdfplumber, duckdb        │
│           ├─ Phase 3: verify critical imports (must succeed)     │
│           └─ _packages_ready.set() [only if verification OK]     │
│                                                                  │
│  atexit.register(mgr.stop) — cleanup on process exit             │
│  Daytona auto_delete_interval=3600 — orphan TTL cleanup          │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  User clicks "🔄 New Conversation"                                │
│                                                                  │
│  reset_session():                                                │
│     • messages = [], uploaded_files = [], step_history = []       │
│     • session_id = new uuid4()                                   │
│     • _agent_cache + _files_uploaded cleared                     │
│     • Old sandbox stopped, new SandboxManager created            │
│     • sandbox_prewarm_done cleared (triggers re-prewarm)         │
└──────────────────────────────────────────────────────────────────┘
```

## Thread-Safe Artifact Passing

```
┌────────────────────┐           ┌────────────────────────────────┐
│  Agent Thread       │           │  Streamlit UI Thread            │
│  (tool execution)  │           │  (rendering)                    │
│                    │           │                                 │
│  generate_html()   │───add───▶│                                 │
│  create_viz()      │───add───▶│  ArtifactStore (global singleton│
│  download_file()   │───add───▶│  with threading.Lock)           │
│                    │           │                                 │
│  ❌ st.session_state│           │  After stream completes:        │
│     NOT accessible │           │  pop_html() → components.html() │
│     from agent     │           │  pop_charts() → st.image()      │
│     thread         │           │  pop_downloads() → download_btn │
└────────────────────┘           └────────────────────────────────┘

Why ArtifactStore exists:
  st.session_state raises ScriptRunContext error when accessed from
  non-Streamlit threads. Tools run in agent thread pools, so they
  cannot write to session_state. ArtifactStore bridges this gap.
```

## Progressive Disclosure Flow (Skill Loading)

```
                    ┌──────────────┐
                    │ User Uploads │
                    │    File(s)   │
                    └──────┬───────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ Detect File Type│
                  │ & File Size     │
                  └────────┬────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ .xlsx    │ │ .pdf     │ │ .csv     │
        │ .xls     │ │          │ │ .tsv     │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             ▼            ▼            ▼
      ┌─────────────┐ ┌────────┐ ┌────────┐
      │xlsx/SKILL.md│ │pdf/    │ │csv/    │
      │  ALWAYS     │ │SKILL.md│ │SKILL.md│
      └──────┬──────┘ └────────┘ └────────┘
             │
             ▼
    ┌─────────────────┐
    │ File Size Check  │
    │ + Keyword Check  │
    │ + File Count     │
    └────────┬────────┘
             │
     ┌───────┴────────┬─────────────────┐
     │                │                 │
     ▼                ▼                 ▼
┌─────────┐   ┌────────────┐   ┌──────────────┐
│< 40 MB  │   │ ≥ 40 MB    │   │ ≥ 2 Excel    │
│ OR no   │   │ OR keyword │   │ files OR     │
│ trigger │   │ "duckdb"   │   │ keyword      │
│         │   │ "large     │   │ "join/merge" │
│         │   │  file" etc │   │              │
└────┬────┘   └─────┬──────┘   └──────┬───────┘
     │              │                 │
     ▼              ▼                 ▼
┌─────────┐  ┌──────────────┐  ┌─────────────────┐
│ No refs │  │ + large_     │  │ + multi_file_    │
│ loaded  │  │   files.md   │  │   joins.md       │
│         │  │              │  │                  │
│ Prompt: │  │ Prompt:      │  │ Prompt:          │
│ base +  │  │ base + skill │  │ base + skill     │
│ skill   │  │ + large ref  │  │ + joins ref      │
└─────────┘  └──────────────┘  └─────────────────┘
```

## Skill Directory Structure

```
skills/
├── xlsx/
│   ├── SKILL.md                   (always loaded for .xlsx/.xls/.xlsm)
│   └── references/                (loaded on-demand via progressive disclosure)
│       ├── large_files.md         (DuckDB patterns, lazy queries)
│       └── multi_file_joins.md    (JOIN patterns, VLOOKUP via SQL)
│
├── pdf/
│   └── SKILL.md                   (pdfplumber, pypdf, OCR)
│
├── csv/
│   └── SKILL.md                   (pandas + DuckDB basics)
│
└── visualization/
    └── SKILL.md                   (chart selection, Plotly, matplotlib)
```

## Module Dependency Graph

```
app.py
 ├── src/utils/config.py             get_secret: st.secrets → os.getenv → ValueError
 ├── src/ui/session.py               init_session + prewarm thread + atexit cleanup
 ├── src/ui/styles.py                CUSTOM_CSS + TOOL_ICONS/LABELS + get_tool_icon/label
 ├── src/ui/components.py            render_sidebar: file upload + new chat + model info
 └── src/ui/chat.py                  render_chat: streaming + step persistence + artifacts
      │
      ├── src/agent/graph.py         build_agent + get_or_build_agent (cached by fingerprint)
      │    ├── langchain.agents          create_agent + manual middleware stack
      │    ├── src/agent/prompts.py      BASE_SYSTEM_PROMPT (English, user responses Turkish)
      │    ├── src/skills/registry.py    detect_required_skills + detect_reference_files
      │    ├── src/skills/loader.py      load_skill + load_reference + compose_system_prompt
      │    └── langchain-anthropic       Claude Sonnet 4 (claude-sonnet-4-20250514)
      │
      ├── src/tools/file_parser.py       LOCAL: parse csv/excel/json/pdf → schema summary
      ├── src/tools/generate_html.py     BROWSER: HTML + inject_height_script → ArtifactStore
      ├── src/tools/visualization.py     DAYTONA: matplotlib/seaborn → PNG → ArtifactStore
      ├── src/tools/download_file.py     DAYTONA: download_files() → ArtifactStore
      ├── src/tools/artifact_store.py    Thread-safe global store (Lock + lists)
      │
      └── src/sandbox/manager.py         Daytona lifecycle: create/find/start/stop + TTL
           ├── daytona                   Daytona SDK (Daytona, CreateSandboxFromSnapshotParams)
           └── langchain-daytona         DaytonaSandbox (Deep Agents native backend)
```

## Key Configuration

| Parameter                | Value                          | Location         |
|--------------------------|--------------------------------|------------------|
| Model                    | `claude-sonnet-4-20250514`     | graph.py         |
| large file threshold     | 40MB (DuckDB trigger)          | registry.py      |
| REACT_MAX_ITERATIONS     | 30                             | graph.py         |
| recursion_limit          | 61 (30×2+1)                    | graph.py         |
| execute timeout (agent)  | 180s                           | manager.py       |
| execute timeout (install)| 60s                            | manager.py       |
| max execute calls        | 6 simple / 10 complex (dynamic)| graph.py         |
| sandbox TTL              | 3600s                          | manager.py       |
| sandbox home             | `/home/daytona`                | manager.py       |
| font path (regular)      | `/home/daytona/DejaVuSans.ttf` | prompts.py       |
| font path (bold)         | `/home/daytona/DejaVuSans-Bold.ttf` | prompts.py  |
| wait_until_ready timeout | 120s                           | chat.py          |
| API keys                 | ANTHROPIC_API_KEY, DAYTONA_API_KEY | config.py    |

## Pre-installed Packages (Sandbox)

| Phase    | Packages                                                                          |
|----------|-----------------------------------------------------------------------------------|
| Critical | weasyprint, pandas, openpyxl, xlsxwriter, numpy, matplotlib, seaborn, plotly, scipy, scikit-learn |
| Optional | pdfplumber, duckdb (background thread, after ready signal)                        |
| Fonts    | DejaVuSans.ttf, DejaVuSans-Bold.ttf (cp from /usr/share/fonts/truetype/dejavu/)   |

## Sandbox Disk Management

Daytona has a 30GiB total disk limit across all sandboxes. Stopped sandboxes still consume disk.

```python
# Manual cleanup — delete all stopped sandboxes
from daytona import Daytona, SandboxState
d = Daytona()
result = d.list()
sandboxes = result.items if hasattr(result, 'items') else list(result)
for s in sandboxes:
    if getattr(s, 'state', None) == SandboxState.STOPPED:
        d.delete(s)
```

`auto_delete_interval=3600` in `CreateSandboxFromSnapshotParams` handles idle TTL,
but manually calling `d.delete()` is needed when disk limit is hit.

## Execute-to-Execute Data Flow (Pickle Pattern)

```
Execute 1 (clean + save):          Execute 2 (analyze + PDF):
  df = pd.read_excel(path)           df = pd.read_pickle('/home/daytona/clean.pkl')
  df.dropna(...)                     m = { 'total': df['col'].nunique() }
  df.to_pickle('/home/daytona/       html = f"...{m['total']}..."
    clean.pkl')                      weasyprint.HTML(...).write_pdf(...)
  del df  ← RAM freed               ← SAME process, no hardcoding
     │
     └── /home/daytona/clean.pkl ──▶ persists on Daytona disk

For DuckDB (≥40MB): CSV replaces pickle
  Execute 1: df.to_csv('/home/daytona/temp_sheet.csv'); del df
  Execute 2: duckdb.sql("SELECT ... FROM read_csv_auto('...csv')")

## Documentation Index

| File | İçerik |
|---|---|
| `ARCHITECTURE.md` | Sistem mimarisi, bileşenler, veri akışı, interceptor kuralları |
| `TECHNICAL_GUIDE.md` | Teknik detaylar: pickle/CSV pattern, execute izolasyonu, skill sistemi, ArtifactStore, disk yönetimi |
| `skills/xlsx/SKILL.md` | Excel analiz kuralları, sheet tespiti, pivot format, WeasyPrint PDF, DuckDB stratejileri |
| `skills/xlsx/references/large_files.md` | ≥40MB dosyalar: Excel→CSV→DuckDB, UNION ALL, multi-sheet pattern |
| `skills/xlsx/references/multi_file_joins.md` | Çoklu dosya JOIN pattern |
| `skills/csv/SKILL.md` | CSV analiz kuralları, pickle, DuckDB |
| `skills/pdf/SKILL.md` | PDF okuma, pdfplumber, OCR |

