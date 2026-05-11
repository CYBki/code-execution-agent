# Agentic Analyze

AI-powered data analysis agent that turns Excel, CSV, and PDF files into insights, visualizations, and professional PDF reports — all through natural language conversation.

Upload a 1M+ row spreadsheet, ask a question in plain language, and get a complete analysis with charts and a downloadable PDF report in seconds.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/LLM-Claude_(Anthropic)-blueviolet?logo=anthropic" />
  <img src="https://img.shields.io/badge/Sandbox-OpenSandbox-orange" />
  <img src="https://img.shields.io/badge/UI-Streamlit-red?logo=streamlit" />
</p>

---

## What Is This?

Agentic Analyze is an **autonomous data analysis agent**. It doesn't just answer questions — it writes and executes real Python code inside a secure sandbox to analyze your data end-to-end.

### Key Capabilities

- **Excel / CSV / PDF analysis** — Upload `.xlsx`, `.csv`, `.xls`, `.pdf` files and ask questions in natural language
- **1M+ row support** — Small files use pandas; large files (≥40 MB) automatically switch to **DuckDB** for blazing-fast SQL-based analysis with minimal memory usage
- **Secure code execution** — All code runs inside an isolated **OpenSandbox** Docker container. Your host system is never exposed
- **PDF report generation** — Produces professional PDF reports with tables, charts, and summaries via WeasyPrint
- **Interactive HTML dashboards** — Generates Plotly/Matplotlib visualizations rendered directly in the UI
- **Persistent kernel** — Variables and DataFrames survive across multiple code executions within a session — no redundant re-reads
- **Skill system** — Modular prompt engineering: specialized skills for Excel, CSV, PDF, and visualization are automatically activated based on file type and query content
- **Multi-file joins** — Upload multiple files and the agent can JOIN/merge them automatically

### How It Works

```
User uploads file(s) + asks a question
        ↓
Skill system activates (xlsx / csv / pdf / visualization)
        ↓
parse_file → schema, column types, row count, preview
        ↓
  < 40 MB  →  pandas (in-memory)
  ≥ 40 MB  →  Excel → CSV conversion + DuckDB (SQL)
        ↓
Agent writes & executes analysis code (ReAct loop)
        ↓
Results + charts + PDF report → delivered to user
```

---

## Quick Start (Docker — Recommended)

The fastest way to get everything running. Docker Compose builds the sandbox image, starts the OpenSandbox server, PostgreSQL, and the Streamlit app in one command.

### Prerequisites

- **Docker** & **Docker Compose** v2+
- **Anthropic API Key** — [get one here](https://console.anthropic.com/)

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/SKYMOD-Team/code-execution-agent.git
cd code-execution-agent

# 2. Configure environment
cp .env.example .env
# Edit .env and set your Anthropic API key:
#   ANTHROPIC_API_KEY=sk-ant-api03-...

# 3. Build & start all services
docker compose up -d --build
# First run takes ~5-10 min (builds the 10 GB analysis sandbox image)

# 4. Check that everything is healthy
docker compose ps
# All services should show "healthy" or "Up"
```

Open **http://localhost:8501** in your browser. Done.

### What Docker Compose Starts

| Service | Description | Port |
|---|---|---|
| **sandbox-image** | Builds `agentic-sandbox:v1` — pre-baked Python environment with pandas, DuckDB, matplotlib, WeasyPrint, etc. | — |
| **opensandbox-server** | Manages sandbox container lifecycles | `8080` |
| **postgres** | Conversation & file storage | `5432` |
| **app** | Streamlit web UI | `8501` |

---

## Manual Setup (Without Docker)

For development or environments where Docker is not available for the app itself. You still need Docker for OpenSandbox.

### Prerequisites

- Python 3.12+
- Docker (for OpenSandbox sandbox containers)
- [OpenSandbox server](https://github.com/nicholasgriffintn/OpenSandbox) installed and running
- [Anthropic API Key](https://console.anthropic.com/)

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/SKYMOD-Team/code-execution-agent.git
cd code-execution-agent

# 2. Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -e .

# 4. Build the sandbox image (required — contains all analysis packages)
docker build -f Dockerfile.analysis -t agentic-sandbox:v1 .

# 5. Start OpenSandbox server (if not already running)
opensandbox-server   # listens on 127.0.0.1:8080

# 6. Configure environment
cp .env.example .env
# Edit .env:
#   ANTHROPIC_API_KEY=sk-ant-api03-...
#   OPEN_SANDBOX_API_KEY=local-sandbox-key-2024
#   OPEN_SANDBOX_DOMAIN=localhost:8080

# 7. Run the app
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

---

## Usage

1. **Upload files** — Drag & drop `.xlsx`, `.csv`, `.xls`, or `.pdf` files in the sidebar
2. **Ask a question** — Examples:
   - *"Summarize this dataset and create a PDF report"*
   - *"What are the top 10 customers by revenue? Show a bar chart"*
   - *"Compare sales across regions with a pivot table"*
   - *"Join these two files on customer_id and find mismatches"*
3. **Get results** — The agent analyzes, generates charts, and provides downloadable PDF/HTML reports

### Large File Handling

Files under 40 MB are loaded with **pandas** for fast in-memory analysis. Files ≥40 MB (including 1M+ row spreadsheets) are automatically converted to CSV and queried with **DuckDB** — an embedded analytical SQL engine that can process millions of rows without loading everything into memory.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic Claude API key |
| `OPEN_SANDBOX_API_KEY` | ✅ | OpenSandbox API key (default: `local-sandbox-key-2024`) |
| `OPEN_SANDBOX_DOMAIN` | ✅ | OpenSandbox server address (default: `localhost:8080`) |
| `POSTGRES_PASSWORD` | — | PostgreSQL password (Docker only, default: `agentic-local-dev`) |
| `DATABASE_URL` | — | PostgreSQL connection string (omit for SQLite fallback) |

---

## Project Structure

```
├── app.py                          # Streamlit entry point
├── src/
│   ├── agent/
│   │   ├── graph.py                # Agent setup, tools, smart interceptor
│   │   └── prompts.py              # System prompt + analysis rules
│   ├── tools/
│   │   ├── execute.py              # Sandbox code execution (base64 pattern)
│   │   ├── file_parser.py          # parse_file — schema + preview extraction
│   │   ├── generate_html.py        # Interactive HTML dashboard generation
│   │   ├── download_file.py        # PDF/file download from sandbox
│   │   └── artifact_store.py       # Thread-safe artifact bridge to UI
│   ├── sandbox/
│   │   └── manager.py              # OpenSandbox lifecycle (create, reuse, cleanup)
│   ├── skills/
│   │   ├── registry.py             # Skill triggers (file type, size thresholds)
│   │   └── loader.py               # Dynamic system prompt composer
│   └── ui/
│       ├── chat.py                 # Chat interface + message rendering
│       ├── session.py              # Session state + sandbox pre-warming
│       └── components.py           # Sidebar, file uploader, controls
├── skills/
│   ├── xlsx/SKILL.md               # Excel analysis rules, pivot, WeasyPrint PDF
│   ├── csv/SKILL.md                # CSV/TSV rules, DuckDB patterns
│   ├── pdf/SKILL.md                # PDF text extraction rules
│   └── visualization/SKILL.md      # Chart & dashboard rules
├── docker-compose.yml              # Full-stack deployment
├── Dockerfile                      # App container image
├── Dockerfile.analysis             # Sandbox image (pandas, DuckDB, WeasyPrint, etc.)
└── pyproject.toml                  # Python dependencies
```

---

## Architecture

```
┌─────────────┐     ┌────────────────────┐     ┌──────────────────────────┐
│  Streamlit   │────▶│  LangChain Agent   │────▶│  OpenSandbox Server      │
│  (UI)        │◀────│  (Claude + Tools)  │◀────│  (container lifecycle)   │
└─────────────┘     └────────────────────┘     └──────────┬───────────────┘
                                                          │
                                               ┌──────────▼───────────────┐
                                               │  agentic-sandbox:v1      │
                                               │  (isolated container)    │
                                               │                          │
                                               │  pandas · DuckDB         │
                                               │  matplotlib · plotly     │
                                               │  WeasyPrint · openpyxl   │
                                               │  scikit-learn · scipy    │
                                               └──────────────────────────┘
```

- **Streamlit UI** — File upload, chat interface, artifact rendering
- **LangChain Agent** — ReAct loop with Claude, 5 tools (parse_file, execute, generate_html, visualization, download_file)
- **OpenSandbox** — Creates isolated Docker containers per session for secure code execution
- **Sandbox Image** — Pre-baked with 15+ analysis packages so there's zero install wait at runtime

---

## Troubleshooting

**Sandbox won't start / "OpenSandbox unreachable":**
```bash
# Check if OpenSandbox server is running
curl http://127.0.0.1:8080/health
# Should return: {"status":"healthy"}

# Check if sandbox image exists
docker images agentic-sandbox:v1
# If missing, rebuild: docker compose build sandbox-image
```

**Port conflict on 8080 or 8501:**
```bash
# Find what's using the port
ss -tlnp | grep 8080
# Kill the process or change the port in .env / docker-compose.yml
```

**Large file analysis is slow:**
Files ≥40 MB use DuckDB automatically. If you're hitting memory limits, the agent will suggest chunked processing. Ensure the sandbox container has at least 2 GB of available memory.

---

## License

MIT
