"""LLM-based judges for semantic trace analysis.

These judges use Claude to analyze agent traces and evaluate behavioral
quality that rule-based scorers cannot assess.

Requires: ANTHROPIC_API_KEY in environment.
"""

from __future__ import annotations

import logging
import os

from mlflow.genai.scorers import Guidelines

logger = logging.getLogger(__name__)

# Model for LLM judges — uses Anthropic Claude
_JUDGE_MODEL = os.environ.get(
    "MLFLOW_JUDGE_MODEL", "anthropic:/claude-sonnet-4-20250514"
)


# ---------------------------------------------------------------------------
# Judge 1: Correct workflow sequence
# ---------------------------------------------------------------------------
correct_workflow_sequence = Guidelines(
    name="correct_workflow_sequence",
    guidelines=(
        "Analyze the agent trace and determine if it followed the correct workflow sequence:\n"
        "1. parse_file() should be called FIRST (once per file) for schema discovery\n"
        "2. Then execute() with pd.read_excel/pd.read_csv to load data\n"
        "3. Then execute() for analysis/computation\n"
        "4. Then artifact generation (generate_html, download_file, or execute with weasyprint)\n\n"
        "The agent should NOT:\n"
        "- Call parse_file more than once for the same file\n"
        "- Use ls/cat/os.listdir before or after parse_file\n"
        "- Skip parse_file and guess column names\n"
        "- Generate artifacts before completing analysis\n\n"
        "Return 'yes' if the workflow sequence is correct, 'no' if steps are out of order "
        "or critical steps are missing."
    ),
    model=_JUDGE_MODEL,
)


# ---------------------------------------------------------------------------
# Judge 2: No unnecessary data re-reads
# ---------------------------------------------------------------------------
no_unnecessary_reread = Guidelines(
    name="no_unnecessary_reread",
    guidelines=(
        "Analyze the agent trace and determine if the agent correctly uses the persistent kernel.\n\n"
        "The Python kernel is PERSISTENT: variables (df, imports, computed dicts) survive across "
        "execute() calls. After loading data once with pd.read_excel(), the DataFrame should be "
        "reused in subsequent execute() calls without re-reading from disk.\n\n"
        "ACCEPTABLE re-reads:\n"
        "- First read of a new file\n"
        "- Re-read after a new user question IF the previous turn's df was filtered/modified\n"
        "- Excel→CSV conversion for DuckDB (large files)\n\n"
        "WASTEFUL re-reads:\n"
        "- Reading the same file in consecutive execute() calls within one turn\n"
        "- Re-reading data just to compute a different metric\n"
        "- Re-reading after adding a computed column (no rows lost)\n\n"
        "Return 'yes' if the agent uses the persistent kernel efficiently, 'no' if it "
        "wastefully re-reads data."
    ),
    model=_JUDGE_MODEL,
)


# ---------------------------------------------------------------------------
# Judge 3: Appropriate strategy for file size
# ---------------------------------------------------------------------------
appropriate_strategy = Guidelines(
    name="appropriate_strategy",
    guidelines=(
        "Analyze the agent trace and determine if the agent chose the right analysis strategy "
        "based on the data size.\n\n"
        "RULES:\n"
        "- Small files (<40MB): pandas is appropriate (pd.read_excel → df operations)\n"
        "- Large files (>=40MB): Should use DuckDB strategy (Excel→CSV→DuckDB SQL)\n"
        "- Very large files (>=500MB): Should use chunked reading\n\n"
        "Also check:\n"
        "- Multi-sheet Excel files: agent should check sheet_names first\n"
        "- Agent should not load ALL data into memory if only aggregation is needed (large files)\n\n"
        "If the file is small and pandas is used, return 'yes'.\n"
        "If the file is large and DuckDB is not used, return 'no'.\n"
        "If you cannot determine file size from the trace, return 'yes' (assume small)."
    ),
    model=_JUDGE_MODEL,
)


# ---------------------------------------------------------------------------
# Judge 4: Report/artifact quality
# ---------------------------------------------------------------------------
report_quality = Guidelines(
    name="report_quality",
    guidelines=(
        "Analyze the agent trace and determine if the generated report/dashboard is well-formed.\n\n"
        "The agent can produce reports in TWO ways (both are valid):\n"
        "A) HTML dashboard via generate_html() — check for proper KPI cards and charts\n"
        "B) PDF via weasyprint inside execute() — check that PDF was created and downloaded\n\n"
        "Check for:\n"
        "1. Were metrics computed from the actual data (df), not hardcoded?\n"
        "2. Was the artifact actually produced? (PDF file created OR HTML generated)\n"
        "3. Was the artifact offered for download (download_file called for PDF)?\n"
        "4. Did the execute output confirm success (e.g., '✅ PDF rapor', file size shown)?\n\n"
        "Return 'yes' if:\n"
        "- A PDF was generated via weasyprint AND downloaded, OR\n"
        "- An HTML dashboard was generated via generate_html()\n"
        "- AND metrics were computed from data, not hardcoded\n\n"
        "Return 'no' only if:\n"
        "- No report/artifact was generated at all\n"
        "- Report generation failed with errors\n"
        "- Metrics are clearly hardcoded (magic numbers not derived from df)\n\n"
        "If the scenario doesn't require a report, return 'yes'."
    ),
    model=_JUDGE_MODEL,
)


# All LLM judges for easy import
ALL_LLM_JUDGES = [
    correct_workflow_sequence,
    no_unnecessary_reread,
    appropriate_strategy,
    report_quality,
]

# Default subset (skip report_quality for non-report scenarios)
DEFAULT_LLM_JUDGES = [
    correct_workflow_sequence,
    no_unnecessary_reread,
]
