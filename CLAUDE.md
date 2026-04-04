# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An AI agent that analyzes Excel, CSV, and PDF files using Claude Sonnet 4 + LangChain + OpenSandbox sandboxed execution. The agent generates PDF reports and interactive HTML dashboards through a Streamlit interface.

**Tech Stack:** LangChain `create_agent`, Anthropic Claude, OpenSandbox (persistent CodeInterpreter kernel), Streamlit, DuckDB (large files), WeasyPrint (PDF generation)

## Development Commands

```bash
# Setup
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .

# Configure API keys (.env file)
ANTHROPIC_API_KEY=sk-ant-...
OPEN_SANDBOX_API_KEY=local-sandbox-key-2024

# Run application
streamlit run app.py

# The app runs at http://localhost:8501
# First query is fast (~5s) — packages pre-installed in Docker image
```

## Critical Architecture Concepts

### 1. Persistent Kernel Pattern

**Key insight:** `execute()` calls share a **persistent Python kernel** (OpenSandbox CodeInterpreter). Variables, imports, and DataFrames survive across calls within a session.

**No pickle/serialization needed — variables persist:**
```python
# Execute #1: Read + clean (df stays in memory)
df = pd.read_excel('/home/sandbox/data.xlsx')
df = df.dropna(subset=['CustomerID'])
df['Date'] = pd.to_datetime(df['Date'])
print(f"✅ Loaded: {len(df):,} rows")

# Execute #2: df is STILL in memory (no re-read needed)
m = {
    'total_customers': df['CustomerID'].nunique(),
    'total_revenue': (df['Quantity'] * df['Price']).sum(),
}
print(f"✅ Metrics computed: {len(m)} keys: {list(m.keys())}")  # Print KEYS only, NOT values!

# Execute #3: Both df and m are STILL available
html = f"""<h3>Customers: {m['total_customers']:,}</h3>"""
weasyprint.HTML(string=html).write_pdf('/home/sandbox/report.pdf')
```

**Exception:** `generate_html()` runs in a **separate process** — it cannot see Python variables. You must build the complete HTML string inside `execute()` and pass it as a literal string to `generate_html()`.

**Large files (≥40MB):** DuckDB pattern is still valid and simplified:
```python
# Execute #1: Excel → CSV per sheet
for sheet in xls.sheet_names:
    df = pd.read_excel(path, sheet_name=sheet)
    df.to_csv(f'/home/sandbox/temp_{sheet}.csv', index=False)
    del df
csv_paths = {'Sheet1': '/home/sandbox/temp_Sheet1.csv', ...}

# Execute #2: DuckDB queries (csv_paths from Execute #1 still available)
stats = duckdb.sql(f"SELECT ... FROM read_csv_auto('{csv_paths['Sheet1']}')")
# No need to redeclare csv_paths — persistent kernel!
```

All sandbox files live at `/home/sandbox/`. Font files `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf` are pre-installed there.

### 2. Smart Interceptor Layer

Located in [src/agent/graph.py](src/agent/graph.py), the `smart_interceptor` intercepts every tool call before execution.

**Blocked patterns (returns ToolMessage, doesn't consume execute quota):**
- Shell commands: `ls`, `find`, `cat`, `head`, `tail`, `os.listdir`, `glob.glob`
- Network: `urllib`, `requests`, `wget`, `curl`
- Package install: `pip install`, `subprocess`
- Sampling: `nrows > 10` or schema re-checks after `parse_file` already ran
- Duplicate `parse_file` calls
- Execute limit exceeded (dynamic: 6-10 based on query complexity)

**Auto-fixes (modifies code, then executes):**
- Arial/Helvetica → DejaVu font replacement
- Missing `add_font()` injection for FPDF code

**Critical:** Always call `reset_interceptor_state()` before `agent.stream()` to clear closure counters (see [src/ui/chat.py:162](src/ui/chat.py)).

### 3. Skill System (Progressive Disclosure)

System prompts are **dynamically composed** based on file type, size, and keywords:

```
File uploaded → registry.py detects triggers → loader.py composes prompt
```

**Triggers** ([src/skills/registry.py](src/skills/registry.py)):
- `.xlsx` extension → always load `skills/xlsx/SKILL.md`
- `≥40MB` or keyword "duckdb" → add `skills/xlsx/references/large_files.md`
- `≥2 files` or keyword "join/merge" → add `skills/xlsx/references/multi_file_joins.md`

Skill files contain domain-specific rules (persistent kernel pattern, DuckDB strategy, WeasyPrint format, etc.).

### 4. Sandbox Lifecycle

**Pre-warming** ([src/sandbox/manager.py](src/sandbox/manager.py)):
- Browser opens → `init_session()` spawns background thread
- Background thread: create sandbox (~5s, packages pre-installed in Docker image) → signal ready
- User uploads file → `wait_until_ready(timeout=30s)` blocks until sandbox ready
- Sandbox TTL: 2 hours (configurable) → auto-deleted

**Packages are pre-installed in Docker image**, not per query. First query is fast.

### 5. Agent Caching

Agents are cached by fingerprint: `(model_name, file_names_tuple, file_sizes_tuple)`. Same files → reuse agent (skip skill recompilation). New file or "New Conversation" → rebuild agent.

Cache location: `st.session_state["_agent_cache"]`

### 6. Thread-Safe Artifact Passing

Agent tools run in separate threads from Streamlit UI. Cannot access `st.session_state` directly.

**Solution:** `ArtifactStore` global singleton ([src/tools/artifact_store.py](src/tools/artifact_store.py))

```
Agent thread:                  Streamlit thread:
  generate_html(html_str)
    ↓
  ArtifactStore.add_html()     (after stream completes)
                                   ↓
                               artifact_store.pop_html()
                                   → components.html()
```

## Key Files & Their Roles

| File | Purpose |
|------|---------|
| [app.py](app.py) | Entry point, validates API keys, renders UI |
| [src/agent/graph.py](src/agent/graph.py) | Agent construction, smart_interceptor, middleware stack |
| [src/agent/prompts.py](src/agent/prompts.py) | Base system prompt (Turkish, ReAct workflow, schema-first rules) |
| [src/sandbox/manager.py](src/sandbox/manager.py) | OpenSandbox lifecycle, CodeInterpreter persistent kernel, file upload |
| [src/skills/registry.py](src/skills/registry.py) | Skill triggers (file size, extension, keywords) |
| [src/skills/loader.py](src/skills/loader.py) | Dynamic prompt composition |
| [src/tools/file_parser.py](src/tools/file_parser.py) | Schema extraction (doesn't consume execute quota) |
| [src/tools/execute.py](src/tools/execute.py) | Code execution via OpenSandbox CodeInterpreter, persistent kernel |
| [src/tools/artifact_store.py](src/tools/artifact_store.py) | Thread-safe bridge to Streamlit UI |
| [src/ui/chat.py](src/ui/chat.py) | Chat rendering, streaming, agent invocation |
| [src/ui/session.py](src/ui/session.py) | Session init, sandbox pre-warming thread |

## Important Patterns

### PDF Generation with WeasyPrint

Use WeasyPrint (not fpdf2) for HTML/CSS → PDF with proper Turkish character support:

```python
html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>body {{ font-family: Arial, sans-serif; margin: 40px; }}</style>
</head><body>
<h1>Rapor</h1>
<p>Müşteri Sayısı: <b>{m['customers']:,}</b></p>
</body></html>"""

weasyprint.HTML(string=html).write_pdf('/home/sandbox/rapor.pdf')
```

**Critical:** All metric calculations and PDF generation must happen in **same execute** block. Never hardcode numbers — always use `m = {...}` dict pattern.

### Multi-Sheet Excel Analysis

**Schema detection first:**
```python
xls = pd.ExcelFile(path)
sheet_names = xls.sheet_names
# NEVER: df = pd.read_excel(path)  ← loads first sheet only
```

**Strategy selection:**
- Same columns → `UNION ALL` in DuckDB
- Related tables → `JOIN` in DuckDB
- Independent data → separate queries

### Base System Prompt Constraints

The [src/agent/prompts.py](src/agent/prompts.py) enforces:
1. **No numbers in chat responses** — details go in PDF only
2. **ReAct loop mandatory** — DÜŞÜNCE → execute → GÖZLEM → KARAR
3. **Schema-first** — always `parse_file()` before reading data
4. **Verification blocks** — every execute must include assertion checks

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Sandbox won't start | Docker disk space | Check Docker disk usage with `docker system df` |
| `ModuleNotFoundError: deepagents` | Not installed | Run `pip install -e .` |
| `ModuleNotFoundError` in sandbox | Package missing from Docker image | Sandbox image needs rebuild (contact dev team) |
| Hardcoded numbers in PDF | Wrong pattern | Use `m = {...}` dict, calculate in same execute |
| `MemoryError` on 40MB+ file | Using pandas instead of DuckDB | Check parse_file output for "BÜYÜK DOSYA" warning |
| Empty KPI cards in dashboard | Variables not passed to generate_html | Build complete HTML string in execute(), pass literal string |

## Testing Workflow

1. Place test file (e.g., `data.xlsx`) anywhere accessible
2. Run `streamlit run app.py`
3. Upload file via sidebar
4. Ask question in Turkish: *"Müşteri başına ortalama sipariş sayısı nedir? PDF rapor ver."*
5. Agent workflow appears in chat (parse → clean → analyze → PDF)
6. Download button appears when complete

## Additional Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — system diagrams, data flow, component interactions
- [TECHNICAL_GUIDE.md](TECHNICAL_GUIDE.md) — persistent kernel patterns, DuckDB strategies, interceptor rules
- [TEAM_GUIDE.md](TEAM_GUIDE.md) — onboarding guide, security decisions, deployment notes
- [skills/xlsx/SKILL.md](skills/xlsx/SKILL.md) — Excel analysis rules, sheet detection, PDF format
- [skills/xlsx/references/large_files.md](skills/xlsx/references/large_files.md) — DuckDB patterns for ≥40MB files
- [skills/xlsx/references/multi_file_joins.md](skills/xlsx/references/multi_file_joins.md) — Multi-file JOIN patterns
- [docs/REACT_VS_PLAN_EXECUTE.md](docs/REACT_VS_PLAN_EXECUTE.md) — ReAct vs Plan-and-Execute pattern evaluation (why ReAct is better for this project)
- [docs/PATTERN_COMPARISON_SUMMARY.md](docs/PATTERN_COMPARISON_SUMMARY.md) — Quick comparison table and decision summary

## Security Constraints

- **Sandbox isolation:** User code cannot harm local environment
- **No pip install:** All packages pre-installed, prevents malicious package injection
- **No network access:** Sandbox cannot exfiltrate data or fetch external resources
- **No filesystem exploration:** File paths are known upfront via parse_file
- **Execute limits:** Dynamic cap (6-10) prevents infinite loops and cost overruns
- **No hardcoded metrics:** Prevents LLM hallucinations in PDF reports
