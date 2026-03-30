# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An AI agent that analyzes Excel, CSV, and PDF files using Claude Sonnet 4 + LangChain + Daytona sandboxed execution. The agent generates PDF reports and interactive HTML dashboards through a Streamlit interface.

**Tech Stack:** LangChain `create_agent`, Anthropic Claude, Daytona sandbox, Streamlit, DuckDB (large files), WeasyPrint (PDF generation)

## Development Commands

```bash
# Setup
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .

# Configure API keys (.env file)
ANTHROPIC_API_KEY=sk-ant-...
DAYTONA_API_KEY=dtn_...

# Run application
streamlit run app.py

# The app runs at http://localhost:8501
# First query takes ~30s while sandbox installs packages in background
```

## Critical Architecture Concepts

### 1. Execute Isolation Pattern

**Key insight:** Each `execute()` tool call runs in a separate Python subprocess on Daytona sandbox. Variables from Execute #1 don't exist in Execute #2.

**Data transfer between executes:**
- **Small files (<40MB):** Use pickle
  ```python
  # Execute 1
  df.to_pickle('/home/daytona/clean.pkl')

  # Execute 2
  df = pd.read_pickle('/home/daytona/clean.pkl')
  ```
- **Large files (≥40MB):** Use CSV → DuckDB
  ```python
  # Execute 1: Excel → CSV per sheet
  for sheet in xls.sheet_names:
      df = pd.read_excel(path, sheet_name=sheet)
      df.to_csv(f'/home/daytona/temp_{sheet}.csv', index=False)
      del df

  # Execute 2: DuckDB queries (csv_paths dict must be redeclared)
  csv_paths = {'Sheet1': '/home/daytona/temp_Sheet1.csv', ...}
  stats = duckdb.sql(f"SELECT ... FROM read_csv_auto('{csv_paths['Sheet1']}')")
  ```

All sandbox files live at `/home/daytona/`. Font files `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf` are pre-installed there.

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

Skill files contain domain-specific rules (pickle pattern, DuckDB strategy, WeasyPrint format, etc.).

### 4. Sandbox Lifecycle

**Pre-warming** ([src/sandbox/manager.py](src/sandbox/manager.py)):
- Browser opens → `init_session()` spawns background thread
- Background thread: create/find sandbox → install packages (weasyprint, pandas, openpyxl, duckdb, etc.) → signal ready
- User uploads file → `wait_until_ready(timeout=120s)` blocks until packages installed
- Sandbox TTL: 3600s idle → auto-deleted

**Package installation happens once per sandbox**, not per query.

**Cleanup stopped sandboxes** (Daytona has 30GiB disk limit):
```bash
# Interactive mode (shows summary, asks confirmation)
python cleanup_sandboxes.py

# Auto-confirm mode (for automation)
python cleanup_sandboxes.py --yes
```
The script deletes stopped/archived/error sandboxes to free disk space.

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
| [src/sandbox/manager.py](src/sandbox/manager.py) | Daytona lifecycle, package pre-warming, file upload |
| [src/skills/registry.py](src/skills/registry.py) | Skill triggers (file size, extension, keywords) |
| [src/skills/loader.py](src/skills/loader.py) | Dynamic prompt composition |
| [src/tools/file_parser.py](src/tools/file_parser.py) | Schema extraction (doesn't consume execute quota) |
| [src/tools/execute.py](src/tools/execute.py) | Code execution via Daytona, base64 temp file pattern |
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

weasyprint.HTML(string=html).write_pdf('/home/daytona/rapor.pdf')
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
| Sandbox won't start | Daytona disk limit (30GiB) | Run `python cleanup_sandboxes.py --yes` |
| `ModuleNotFoundError: deepagents` | Not installed | Run `pip install -e .` |
| First query takes ~30s | Package installation running | Normal, prewarm not complete |
| `KeyError: csv_paths` in Execute #2 | Execute isolation | Redeclare `csv_paths = {...}` in Execute #2 |
| Hardcoded numbers in PDF | Wrong pattern | Use `m = {...}` dict, calculate in same execute |
| `MemoryError` on 40MB+ file | Using pandas instead of DuckDB | Check parse_file output for "BÜYÜK DOSYA" warning |

## Testing Workflow

1. Place test file (e.g., `data.xlsx`) anywhere accessible
2. Run `streamlit run app.py`
3. Upload file via sidebar
4. Ask question in Turkish: *"Müşteri başına ortalama sipariş sayısı nedir? PDF rapor ver."*
5. Agent workflow appears in chat (parse → clean → analyze → PDF)
6. Download button appears when complete

## Additional Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — system diagrams, data flow, component interactions
- [TECHNICAL_GUIDE.md](TECHNICAL_GUIDE.md) — pickle vs CSV patterns, DuckDB strategies, interceptor rules
- [TEAM_GUIDE.md](TEAM_GUIDE.md) — onboarding guide, security decisions, deployment notes
- [skills/xlsx/SKILL.md](skills/xlsx/SKILL.md) — Excel analysis rules, sheet detection, PDF format
- [skills/xlsx/references/large_files.md](skills/xlsx/references/large_files.md) — DuckDB patterns for ≥40MB files
- [skills/xlsx/references/multi_file_joins.md](skills/xlsx/references/multi_file_joins.md) — Multi-file JOIN patterns

## Security Constraints

- **Sandbox isolation:** User code cannot harm local environment
- **No pip install:** All packages pre-installed, prevents malicious package injection
- **No network access:** Sandbox cannot exfiltrate data or fetch external resources
- **No filesystem exploration:** File paths are known upfront via parse_file
- **Execute limits:** Dynamic cap (6-10) prevents infinite loops and cost overruns
- **No hardcoded metrics:** Prevents LLM hallucinations in PDF reports
