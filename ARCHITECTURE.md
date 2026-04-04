# Architecture Diagram

> **Last Updated:** 2026-04-04
> **Version:** 1.3 (with persistent kernel + tool output persistence)

## 🎯 End-to-End Flow (60 Second Overview)

```
1. User uploads Excel (45MB, 2 sheets) → Streamlit sidebar
                ↓
2. Skill System detects: .xlsx + ≥40MB → loads skills/xlsx/SKILL.md + large_files.md
                ↓
3. Background Thread: OpenSandbox creates (~5s, packages pre-installed in Docker image)
                ↓
4. User asks: "Aylık satış trendini analiz et, PDF rapor ver"
                ↓
5. Agent (Claude Sonnet 4) starts ReAct loop:
   │
   ├─ parse_file("file.xlsx") → schema + "⚠️ DuckDB kullan" warning
   │  Output: columns, dtypes, 100 rows preview
   │
   ├─ execute #1: Excel → CSV per sheet (DuckDB prep)
   │  Output: "525K rows → temp_sheet1.csv (44.6 MB)"
   │
   ├─ execute #2: DuckDB queries + metrics + WeasyPrint PDF
   │  │  df → m = {'total': ..., 'avg': ...}  ← metric dict
   │  │  html = f"<h3>{m['total']}</h3>"  ← inject metrics
   │  │  weasyprint.HTML(string=html).write_pdf(...)
   │  Output: "✅ PDF: rapor.pdf (21 KB)"
   │
   └─ download_file("rapor.pdf") → ArtifactStore → st.download_button
                ↓
6. Chat history saves: tool inputs + outputs (call_id matching)
                ↓
7. User refreshes page → history re-renders with all tool outputs intact
```

**Key Innovation:** Tool outputs (execute stdout, parse_file schema) persist in chat history via `call_id` matching - not lost after streaming.

## Table of Contents

1. [Quick Summary](#quick-summary) — Tech stack, key features, critical patterns
2. [System Overview](#system-overview) — Component diagram (UI, Skills, Agent, Sandbox)
3. [Data Flow](#data-flow--typical-analysis-request) — Typical analysis request lifecycle
4. [Smart Interceptor](#smart-interceptor--tool-call-control-layer) — Tool call control (block/rate-limit/auto-fix)
5. [Session & Sandbox Lifecycle](#session--sandbox-lifecycle) — Browser open → prewarm → cleanup
6. [Message Persistence](#message-persistence--tool-output-tracking-new) — Tool output tracking (NEW)
7. [Message Deduplication](#message-deduplication-rendered_ids-set) — rendered_ids set (NEW)
8. [Thread-Safe Artifacts](#thread-safe-artifact-passing) — ArtifactStore pattern
9. [Progressive Disclosure](#progressive-disclosure-flow-skill-loading) — Skill loading triggers
10. [Persistent Kernel](#persistent-kernel-data-flow) — Variables survive across executes (UPDATED)
11. [Module Dependencies](#module-dependency-graph) — Import graph
12. [Configuration](#key-configuration) — Model, timeouts, limits, paths
13. [Pre-installed Packages](#pre-installed-packages-sandbox) — Critical vs Optional split (UPDATED)
14. [Recent Updates](#recent-updates-last-10-commits) — Changelog (NEW)
15. [Documentation Index](#documentation-index) — Links to other guides

## Quick Summary

**What:** AI agent that analyzes Excel/CSV/PDF files using Claude Sonnet 4 + LangChain + OpenSandbox sandboxed execution. Generates PDF reports and interactive HTML dashboards via Streamlit.

**Tech Stack:**
- **Frontend:** Streamlit (chat UI + file upload)
- **Agent:** LangChain `create_agent` + Claude Sonnet 4 (ReAct pattern)
- **Execution:** OpenSandbox (persistent CodeInterpreter kernel)
- **Storage:** LangGraph MemorySaver (conversation state per thread_id)
- **Skills:** Progressive disclosure (load based on file type/size/keywords)

**Key Features:**
- 📋 **Tool Output Persistence**: Execute/parse_file outputs saved in chat history (call_id matching)
- 🔒 **Persistent Kernel**: Variables, imports, DataFrames survive across execute() calls
- 🛡️ **Smart Interceptor**: Blocks shell commands, pip install, network requests, sampling
- 🚀 **Fast Startup**: Packages pre-installed in Docker image (~5s sandbox creation)
- 🎯 **Self-Verification**: Agent builds complete HTML strings before generate_html()

**Critical Patterns:**
1. **Persistent Kernel**: Variables (df, m, imports) survive across execute() calls — no pickle needed
2. **DuckDB Pattern**: Files ≥40MB → Excel→CSV→DuckDB (lazy queries)
3. **Metric Dict**: All calculations in SAME execute as PDF/HTML generation
4. **Deduplication**: `rendered_ids` set prevents message replay during streaming
5. **generate_html Exception**: Runs in separate process — pass complete HTML strings

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
│  │ OpenSandbox  │  │  ├─ 📥 Preparing download...  ✓                 │  │
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
│  │       • PPTX: python-pptx + matplotlib charts (optional package)   │  │
│  │       • HTML: Plotly.js/Chart.js dashboard (browser iframe)        │  │
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
│  │         (strips /home/sandbox/ prefix for duplicate detection)    │  │
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
   │ • 100 rows │  │ • Chart.j│  │ • seaborn    │  │   from sbx   │
   │ • dtypes   │  │ • CSS    │  │ • PNG output │  │ • st download│
   │ • file size│  │ • SVG    │  │              │  │   button     │
   │ • sheets   │  │ • tables │  │              │  │              │
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
│            OPENSANDBOX — CodeInterpreter Persistent Kernel               │
│                       (src/sandbox/manager.py)                           │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  SandboxManager                                                    │  │
│  │                                                                    │  │
│  │  Lifecycle:                                                        │  │
│  │  • get_or_create_sandbox() — create new or reuse cached           │  │
│  │  • _create_new_sandbox()   — SandboxSync.create() + CodeInterpreter│  │
│  │  • clean_workspace()       — rm files + reset Python context      │  │
│  │  • stop() + __del__        — cleanup (not guaranteed)             │  │
│  │                                                                    │  │
│  │  OpenSandboxBackend: Wraps SandboxSync + CodeInterpreterSync      │  │
│  │                      Persistent Python context (_py_context)      │  │
│  │                                                                    │  │
│  │  Fast Startup (packages pre-installed in Docker image):           │  │
│  │  ┌──────────────────────────────────────────────────────────────┐  │  │
│  │  │  Image: agentic-sandbox:v1                                   │  │  │
│  │  │  Pre-installed: weasyprint, pandas, openpyxl, duckdb,        │  │  │
│  │  │                 fpdf2, numpy, matplotlib, seaborn, plotly,   │  │  │
│  │  │                 scipy, scikit-learn, xlsxwriter, pdfplumber, │  │  │
│  │  │                 python-pptx                                   │  │  │
│  │  │  Fonts: /home/sandbox/DejaVuSans*.ttf (pre-copied)           │  │  │
│  │  │                                                              │  │  │
│  │  │  Sandbox creation: ~5s (no pip install wait)                 │  │  │
│  │  │  _packages_ready.set() immediately                           │  │  │
│  │  └──────────────────────────────────────────────────────────────┘  │  │
│  │                                                                    │  │
│  │  File Upload:                                                      │  │
│  │  • backend.upload_files([(path, bytes)])                          │  │
│  │  • Uses SandboxSync.files.write_files() (WriteEntry list)         │  │
│  │  • Runs after wait_until_ready(timeout=30)                        │  │
│  │                                                                    │  │
│  │  Sandbox Config:                                                   │  │
│  │  • Home: /home/sandbox                                             │  │
│  │  • Timeout: 2 hours (configurable)                                 │  │
│  │  • Persistent kernel: variables survive across execute() calls    │  │
│  │  • Context reset: clean_workspace() creates new py_context        │  │
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
│          │   │  3. wait_until_ready(30s) — block for sandbox     │
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
               │  ② execute(read + clean) — df persists in kernel   │
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
               │                                                    │
               │  Message Persistence (NEW):                        │
               │  • collected_steps: [{name, input, call_id, output}]│
               │  • Tool call matching: AI msg.tool_calls[].id      │
               │    ↔ Tool msg.tool_call_id → pair output with input│
               │  • Saved to session_state["messages"][]["steps"]   │
               │  • Re-rendered on history with tool outputs        │
               │                                                    │
               │  Deduplication (rendered_ids set):                 │
               │  • Track msg.id in session_state["_rendered_ids"]  │
               │  • Skip messages already rendered (prevents replay)│
               │  • Persists across queries in same session         │
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
│     ├─ SandboxManager() → self._backend = None (lazy init)       │
│     │                                                            │
│     └─ Background Thread (_prewarm):                             │
│        ├─ get_or_create_sandbox(session_id)                      │
│        │   └─ _create_new_sandbox():                             │
│        │       ├─ SandboxSync.create("agentic-sandbox:v1")       │
│        │       ├─ CodeInterpreterSync.create(sandbox)            │
│        │       ├─ codes.create_context(PYTHON) — persistent      │
│        │       └─ OpenSandboxBackend(sandbox, interpreter, ctx)  │
│        │                                                         │
│        └─ _packages_ready.set() immediately                      │
│           (packages pre-installed in Docker image, ~5s total)    │
│                                                                  │
│  atexit.register(mgr.stop) — cleanup on process exit             │
│  Sandbox timeout: 2 hours (configurable)                         │
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

## Message Persistence & Tool Output Tracking (NEW)

**Problem:** Tool outputs (execute, parse_file) were lost after streaming. History showed tool calls but not their results.

**Solution (commits 07c3123, 3ac8e62, ee097d5):**

```
┌─────────────────────────────────────────────────────────────────────┐
│  Streaming Phase (chat.py:318-350)                                  │
│                                                                     │
│  AI Message arrives:                                                │
│  ├─ tool_calls = [{id: "call_abc", name: "execute", args: {...}}]  │
│  ├─ Append to collected_steps:                                     │
│  │   {name: "execute", input: {...}, call_id: "call_abc",          │
│  │    output: None}  ← Initially empty                             │
│  └─ Render tool call UI (collapsible status block)                 │
│                                                                     │
│  Tool Message arrives (later in stream):                            │
│  ├─ tool_call_id = "call_abc"                                      │
│  ├─ content = "Metrics calculated\n✅ Done"                         │
│  ├─ Find matching step by call_id in collected_steps               │
│  └─ step["output"] = content  ← Paired!                            │
│                                                                     │
│  After stream completes:                                            │
│  └─ Save to session_state["messages"][-1]["steps"] with outputs    │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  History Rendering (chat.py:215-229)                                │
│                                                                     │
│  for msg in session_state["messages"]:                              │
│    for step in msg["steps"]:                                        │
│      _render_tool_call(                                             │
│        tool_name=step["name"],                                      │
│        tool_input=step["input"],                                    │
│        tool_output=step.get("output")  ← NOW AVAILABLE             │
│      )                                                              │
│                                                                     │
│  Tool outputs rendered in expanders:                                │
│  • execute → "📤 Execute Output" (collapsed by default)             │
│  • parse_file → "📋 Schema Info" (collapsed by default)             │
│  • Blocked calls filtered out (⛔ markers detected)                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Message Deduplication (rendered_ids Set)

**Problem:** Same message IDs rendered multiple times during streaming (history replay).

**Solution (commit ee097d5):**

```
session_state["_rendered_ids"] = set()  ← Persists across queries

During streaming (_process_stream_chunk):
  msg_id = getattr(msg, "id", None)
  if msg_id and msg_id in rendered_ids:
    continue  ← Skip already rendered
  if msg_id:
    rendered_ids.add(msg_id)  ← Track as rendered

NOTE: collected_steps does NOT use deduplication - we want ALL messages
from current turn for persistence to session_state["messages"].
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
      └── src/sandbox/manager.py         OpenSandbox lifecycle: create/clean/stop + persistent kernel
           ├── opensandbox               OpenSandbox SDK (SandboxSync)
           └── code_interpreter          CodeInterpreterSync (persistent Python context)
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
| sandbox timeout          | 2 hours (7200s)                | manager.py       |
| sandbox home             | `/home/daytona`                | manager.py       |
| font path (regular)      | `/home/sandbox/DejaVuSans.ttf` | prompts.py       |
| font path (bold)         | `/home/sandbox/DejaVuSans-Bold.ttf` | prompts.py  |
| wait_until_ready timeout | 30s                            | chat.py          |
| API keys                 | ANTHROPIC_API_KEY, OPEN_SANDBOX_API_KEY | config.py    |

## Pre-installed Packages (Sandbox)

| Phase    | Packages                                                                          |
|----------|-----------------------------------------------------------------------------------|
| Critical | weasyprint, pandas, openpyxl, xlsxwriter, numpy, matplotlib, seaborn, plotly, scipy, scikit-learn |
| Optional | pdfplumber, duckdb, python-pptx (background thread, after ready signal)           |
| Fonts    | DejaVuSans.ttf, DejaVuSans-Bold.ttf (cp from /usr/share/fonts/truetype/dejavu/)   |

**Note:** python-pptx moved from Critical to Optional (commit af46e37) to prevent timeout - PowerPoint generation is rarely used and slow to install (~15-20s).

## Sandbox Disk Management

Docker container disk space is managed per sandbox. Sandboxes are automatically cleaned up after timeout (2 hours default).

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

## Persistent Kernel Data Flow

**Key Insight:** execute() calls share a **persistent Python kernel** (CodeInterpreter). Variables, imports, and DataFrames survive across calls.

```
Execute #1 (read + clean):         Execute #2 (analyze):
  df = pd.read_excel(path)           # df STILL in memory from Execute #1
  df.dropna(...)                     m = {'total': df['col'].nunique()}
  print(f"✅ {len(df)} rows")        print(f"✅ m: {list(m.keys())}")
     │
     └── df persists in kernel ──▶  Execute #3 (PDF):
                                     # Both df and m STILL available
                                     html = f"<h3>{m['total']:,}</h3>"
                                     weasyprint.HTML(...).write_pdf(...)
```

**No pickle needed** — variables survive across execute() calls automatically.

**DuckDB pattern (≥40MB) simplified:**
```
Execute #1: Excel → CSV + csv_paths dict
  for sheet in sheets:
      df = pd.read_excel(path, sheet_name=sheet)
      df.to_csv(f'/home/sandbox/temp_{sheet}.csv', index=False)
  csv_paths = {'Sheet1': '/home/sandbox/temp_Sheet1.csv', ...}

Execute #2: DuckDB queries
  # csv_paths from Execute #1 STILL available (persistent kernel)
  stats = duckdb.sql(f"SELECT ... FROM read_csv_auto('{csv_paths['Sheet1']}')")
```

## generate_html Isolation (UPDATED - persistent kernel)

**Exception:** `generate_html()` runs in a **separate process** — it CANNOT see Python variables.

**Common Bug:**
```
Execute #1:
  m = {'total_orders': 36969, 'revenue': 17743429.18}
  # m persists in kernel (correct)

Separate tool call:
  generate_html(html_code=f"<h3>{m['total_orders']}</h3>")
  # ❌ WRONG: generate_html() cannot see m (separate process)
  Result: Empty KPI cards
```

**Correct Pattern (enforced by RULE 3):**
```
Single Execute:
  df = pd.read_excel('/home/sandbox/data.xlsx')  # or reuse from earlier execute
  m = {'total': df['amount'].sum(), 'avg': df['amount'].mean()}
  chart_data = df.groupby('month')['revenue'].sum().tolist()

  # Build complete HTML string with all data embedded
  html = f'''
  <h3>{m['total']:,}</h3>  ← Literal value embedded
  <script>const data = {chart_data};</script>  ← Literal array
  '''
  
  # NOW pass complete string to generate_html
  generate_html(html_code=html)
```

**Agent Self-Verification (prompts.py RULE 3):**

Before generate_html():
1. Build complete HTML string inside execute() with all data as literals
2. Pass the complete string to generate_html()
3. Never pass variable references expecting generate_html to resolve them

**Key difference from old pattern:**
- execute() → execute(): Variables DO persist (persistent kernel)
- execute() → generate_html(): Variables DO NOT persist (separate process)

## Recent Updates (Last 10 Commits)

| Commit | Date | Change |
|--------|------|--------|
| 391cf29 | 2026-04-04 | **Persistent Kernel Documentation**: Fixed docs to match OpenSandbox reality (no pickle, variables persist) |
| b0ebf82 | 2026-03-31 | **generate_html Isolation Check**: Added RULE 3 pre-flight for HTML string building |
| af46e37 | 2026-03-31 | **python-pptx → Optional**: Moved from critical to optional packages (prevents timeout) |
| 07c3123 | 2026-03-31 | **Tool Output Persistence**: call_id matching system to persist execute/parse_file outputs |
| ee097d5 | 2026-03-31 | **Deduplication**: rendered_ids set in session_state prevents history replay |
| be1a283 | 2026-03-31 | **Logging Cleanup**: Removed debug logs, kept only meaningful state changes |
| 6bcc8d0 | 2026-03-31 | **Message Dedup Fix**: Prevent duplicate messages in collected_steps |
| a6c426f | 2026-03-30 | **UI Enhancement**: Show execute and parse_file outputs in expanders |

## Documentation Index

| File | İçerik |
|---|---|
| `ARCHITECTURE.md` | **[THIS FILE]** Sistem mimarisi, bileşenler, veri akışı, interceptor kuralları, message persistence, execute isolation |
| `TECHNICAL_GUIDE.md` | Teknik detaylar: persistent kernel patterns, DuckDB stratejileri, skill sistemi, ArtifactStore |
| `CLAUDE.md` | **[START HERE]** Quick start, critical patterns (execute isolation, ReAct loop), common issues, testing workflow |
| `skills/xlsx/SKILL.md` | Excel analiz kuralları, sheet tespiti, pivot format, WeasyPrint PDF, DuckDB stratejileri, **self-check** |
| `skills/xlsx/references/large_files.md` | ≥40MB dosyalar: Excel→CSV→DuckDB, UNION ALL, multi-sheet pattern |
| `skills/xlsx/references/multi_file_joins.md` | Çoklu dosya JOIN pattern |
| `skills/csv/SKILL.md` | CSV analiz kuralları, pickle, DuckDB |
| `skills/pdf/SKILL.md` | PDF okuma, pdfplumber, OCR |
| `skills/visualization/SKILL.md` | Chart selection guide, Plotly.js (interactive), matplotlib (static) |

---

## 🏗️ Architectural Decisions (Why These Choices?)

### 1. ReAct vs Plan-and-Execute

**Decision:** ReAct (Reason → Act → Observe loop)

**Why:**
- Excel analysis requires **adaptive exploration** (multi-sheet detection, schema surprises)
- User queries are often **vague** ("analiz et" → what exactly?)
- ReAct discovers structure incrementally: parse → clean → analyze → adjust
- Plan-and-Execute requires upfront complete plan → fails when schema changes mid-task

**Trade-off:**
- ✅ Handles unexpected data structures (merged cells, multi-sheet, missing columns)
- ❌ More LLM calls (each observation → new reasoning step)

See: [docs/REACT_VS_PLAN_EXECUTE.md](docs/REACT_VS_PLAN_EXECUTE.md)

---

### 2. Smart Interceptor (Block Shell Commands)

**Decision:** Block `ls`, `find`, `cat`, `head`, `glob.glob` in execute()

**Why:**
- Agent doesn't need filesystem exploration → file paths known from `parse_file`
- Prevents wasted execute quota on `ls /home/daytona` (agent already knows file uploaded)
- Prevents infinite loops: `parse_file → ls → cat → parse_file → ...`
- Security: no arbitrary file reading

**Implementation:** `@wrap_tool_call` decorator intercepts before execution

**Trade-off:**
- ✅ Saves 2-3 execute calls per query (ls, find, cat)
- ✅ Circuit breaker: 2 consecutive blocks → force error (stops infinite loops)
- ❌ Agent must trust parse_file schema (can't "verify" with head/cat)

---

### 3. Tool Output Persistence (call_id Matching)

**Decision:** Store tool outputs in session_state["messages"][]["steps"]

**Why:**
- Users expect to see "what did the agent do?" after page refresh
- Execute outputs contain verification logs ("✅ 36,969 orders processed")
- Debugging: "Why did analysis fail?" → check execute output in history
- Transparency: Show schema info, SQL queries, data transformations

**Implementation:**
```python
AI msg.tool_calls[i].id == Tool msg.tool_call_id → pair them
collected_steps[i]["output"] = tool_message.content
```

**Trade-off:**
- ✅ Full traceability in chat history
- ✅ No additional LLM calls (just metadata tracking)
- ❌ +2KB per execute output in session storage (acceptable for 10-20 messages)

---

### 4. DuckDB for Files ≥40MB

**Decision:** Auto-switch to DuckDB when file ≥40MB (progressive disclosure)

**Why:**
- Pandas loads entire file into RAM → MemoryError on 100MB+ files
- DuckDB lazy evaluation → queries run on disk, not memory
- Excel→CSV conversion once → multiple queries without re-reading Excel

**Trade-off:**
- ✅ Handles files up to 500MB+ on limited RAM
- ✅ SQL syntax → complex joins/aggregations more readable
- ❌ Extra step: Excel→CSV conversion (adds 1 execute call)
- ❌ csv_paths dict must be redeclared in every execute (isolation pattern)

---

### 5. Package Pre-warming (Critical vs Optional Split)

**Decision:** Split packages into Critical (blocks ready) vs Optional (background)

**Why:**
- User expects "ready" after 10-15s, not 60s
- 90% of queries use: pandas, weasyprint, openpyxl (fast to install)
- 10% of queries use: duckdb, python-pptx, pdfplumber (slow to install)
- Don't block UI for rarely-used packages

**Implementation:**
- Critical: `pip install weasyprint pandas openpyxl` → verify → set ready flag
- Optional: Background thread installs duckdb/pptx AFTER ready signal

**Trade-off:**
- ✅ First query ready in ~15s instead of ~60s
- ❌ If user immediately asks for PPTX → may hit "module not found" (rare)

---

### 6. Turkish Output, English Prompt

**Decision:** System prompt in English, agent responses in Turkish

**Why:**
- Claude Sonnet 4 reasoning is **stronger in English** (training data distribution)
- Turkish prompt → tool call args in Turkish → breaks schema matching
- Internal reasoning (DÜŞÜNCE blocks) can be Turkish for user transparency

**Example:**
```
DÜŞÜNCE: InvoiceDate kolonunu datetime'a çevirmem lazım...  ← Turkish OK
execute("df['InvoiceDate'] = pd.to_datetime(...)")  ← English code
```

**Trade-off:**
- ✅ Better reasoning quality, fewer hallucinations
- ✅ Tool calls use English schema (matches actual column names)
- ❌ Prompt engineering slightly more complex (language mixing)

---

### 7. Metric Dict Pattern (m = {...})

**Decision:** Always use `m = {'total': ..., 'avg': ...}` dict for reports

**Why:**
- Prevents hardcoded numbers: Agent can't copy "36,969" from previous execute output
- Forces recalculation: `m['total'] = df['col'].sum()` ensures fresh data
- Type safety: dict values are Python types, not strings
- Single source of truth: metric used in PDF and HTML from same calculation

**Enforced by:** prompts.py RULE 3, skills/xlsx/SKILL.md line 133-146

**Trade-off:**
- ✅ Zero hallucination risk (numbers must be calculated)
- ✅ Easy to verify: print(list(m.keys())) before PDF generation
- ❌ Slightly verbose (could use individual variables)

---

### 8. No Filesystem Tools for Agent

**Decision:** Agent has NO access to os.listdir, glob, pathlib

**Why:**
- File paths are deterministic: `/home/sandbox/{uploaded_filename}`
- parse_file already provides schema → no need to "discover" files
- Prevents exploration waste: agent can't wander filesystem

**Blocked patterns:**
```python
import os; os.listdir('/home/daytona')  ← Interceptor blocks
import glob; glob.glob('*.csv')  ← Interceptor blocks
```

**Trade-off:**
- ✅ Faster queries (no wasted execute on ls/find)
- ✅ Security: can't read sandbox config files
- ❌ Agent must trust upload succeeded (can't verify with ls)

---

## 📊 Performance Metrics

| Metric | Value | Note |
|--------|-------|------|
| First query latency | ~35s | Sandbox creation (5s) + package install (15s) + first execute (15s) |
| Subsequent queries | ~8-12s | Reuse sandbox + agent cache, only execute time |
| Memory per session | ~200MB | Agent + checkpointer + session state + sandbox overhead |
| Concurrent users | ~50-100 | Bottleneck: Daytona disk limit (30GB) + API rate limits |
| Execute call budget | 6-10/query | Dynamic: simple queries 6, complex 10 (DuckDB multi-sheet) |

