"""Custom evaluators for the data analysis agent.

Each evaluator inspects the collected tool calls and agent response
from a single scenario run, returning a score dict:
  {"name": str, "pass": bool, "score": float, "reason": str}

Evaluators target known failure patterns observed in production.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class EvalResult:
    name: str
    passed: bool
    score: float  # 0.0–1.0
    reason: str


# ---------------------------------------------------------------------------
# 1. No pickle usage
# ---------------------------------------------------------------------------
def eval_no_pickle(tool_calls: list[dict], response: str) -> EvalResult:
    """Agent must never use pickle in execute commands."""
    pickle_patterns = ("to_pickle", "read_pickle", ".pkl", "import pickle")
    violations = []
    for tc in tool_calls:
        if tc["name"] != "execute":
            continue
        cmd = tc.get("input", {}).get("command", "")
        for pat in pickle_patterns:
            if pat in cmd:
                violations.append(f"execute used '{pat}'")
    if violations:
        return EvalResult("no_pickle", False, 0.0, "; ".join(violations[:3]))
    return EvalResult("no_pickle", True, 1.0, "No pickle usage detected")


# ---------------------------------------------------------------------------
# 2. Persistent kernel — no redundant re-reads
# ---------------------------------------------------------------------------
def eval_persistent_kernel(tool_calls: list[dict], response: str,
                           num_turns: int = 1) -> EvalResult:
    """After first read_excel/read_csv per turn, subsequent executes should NOT re-read.

    Multi-turn allowance: 1 read per turn is acceptable (kernel context resets).
    Within a single turn, re-reading is wasteful.
    """
    read_patterns = ("pd.read_excel", "pd.read_csv", "read_excel(", "read_csv(")
    read_count = 0
    for tc in tool_calls:
        if tc["name"] != "execute":
            continue
        cmd = tc.get("input", {}).get("command", "")
        if any(p in cmd for p in read_patterns):
            read_count += 1

    # Allow 1 read per turn (kernel resets between turns)
    expected_max = max(1, num_turns)
    if read_count <= expected_max:
        return EvalResult("persistent_kernel", True, 1.0,
                          f"Data read {read_count} time(s) — optimal (budget: {expected_max})")
    # Excess reads: penalize proportionally
    excess = read_count - expected_max
    score = max(0.0, 1.0 - excess * 0.3)
    return EvalResult("persistent_kernel", excess <= 1, score,
                      f"Data re-read {read_count} times (expected ≤{expected_max})")


# ---------------------------------------------------------------------------
# 3. No hardcoded metrics in report code
# ---------------------------------------------------------------------------
def eval_no_hardcoded_metrics(tool_calls: list[dict], response: str) -> EvalResult:
    """Report/PDF execute should not contain hardcoded large numbers."""
    metric_keywords = (
        "revenue", "customer", "order", "total", "amount",
        "profit", "sales", "spend", "count",
    )
    safe_patterns = (
        "font", "size", "margin", "width", "height", "padding",
        "line_h", "cell_h", "col_w", "page_", "header_", "row_h",
        "limit", "top_n", "max_len", "display_", "n_rows",
    )
    violations = []
    for tc in tool_calls:
        if tc["name"] != "execute":
            continue
        cmd = tc.get("input", {}).get("command", "")
        # Only check executes that look like report/PDF generation
        if "weasyprint" not in cmd and "html" not in cmd.lower() and "pdf" not in cmd.lower():
            continue
        hardcoded = re.findall(r'^(\w+)\s*=\s*(\d[\d,]*\.?\d*)\s*(?:#.*)?$', cmd, re.MULTILINE)
        for var, val in hardcoded:
            if (any(kw in var.lower() for kw in metric_keywords)
                    and not any(sp in var.lower() for sp in safe_patterns)
                    and float(val.replace(',', '')) > 100):
                violations.append(f"{var}={val}")

    if violations:
        return EvalResult("no_hardcoded_metrics", False, 0.0,
                          f"Hardcoded metrics: {violations[:3]}")
    return EvalResult("no_hardcoded_metrics", True, 1.0, "All metrics computed from data")


# ---------------------------------------------------------------------------
# 3b. Dashboard data integrity — no hardcoded chart arrays
# ---------------------------------------------------------------------------
def eval_dashboard_integrity(tool_calls: list[dict], response: str) -> EvalResult:
    """Dashboard/HTML executes must use .tolist() from DataFrames, not hardcoded arrays."""
    chart_var_patterns = (
        r"(top_\w+_data|hourly_distribution|sales_data|revenue_data|product_names|category_labels)",
    )
    violations = []

    for tc in tool_calls:
        if tc["name"] != "execute":
            continue
        cmd = tc.get("input", {}).get("command", "")

        # Only check executes that generate dashboards/HTML
        if "html" not in cmd.lower() and "chart" not in cmd.lower() and "dashboard" not in cmd.lower():
            continue

        # Check for hardcoded arrays: variable = ['string', 'string', ...] or [num, num, ...]
        # Pattern: chart_var = [...] with 3+ items, without .tolist() or .values
        for pattern in chart_var_patterns:
            # Match: top_products_data = ['Product A', 'Product B', 'Product C', ...]
            string_array = re.search(
                pattern + r"\s*=\s*\[(?:['\"][\w\s]+['\"],?\s*){3,}\]",
                cmd,
                re.IGNORECASE
            )
            # Match: revenue_data = [100000, 80000, 60000, ...]
            number_array = re.search(
                pattern + r"\s*=\s*\[\d+(?:,?\s*\d+){2,}\]",
                cmd,
                re.IGNORECASE
            )

            if string_array or number_array:
                match = string_array or number_array
                # Allow if it's from .tolist() or .values
                if ".tolist()" not in cmd[:match.start()] and ".values" not in cmd[:match.start()]:
                    var_name = match.group(1) if match else "unknown"
                    violations.append(f"{var_name} = [...] without .tolist()")

    if violations:
        return EvalResult("dashboard_integrity", False, 0.0,
                          f"Hardcoded chart data (fake): {violations[:2]}")
    return EvalResult("dashboard_integrity", True, 1.0,
                      "All chart data from real analysis (.tolist())")


# ---------------------------------------------------------------------------
# 4. Validation present in analysis execute
# ---------------------------------------------------------------------------
def eval_validation_present(tool_calls: list[dict], response: str) -> EvalResult:
    """At least one execute output should contain '✅ Doğrulama OK' or assertion."""
    for tc in tool_calls:
        if tc["name"] != "execute":
            continue
        output = tc.get("output", "")
        if "✅ Doğrulama OK" in output or "✅ Validation OK" in output:
            return EvalResult("validation_present", True, 1.0, "Validation checkpoint found")
        cmd = tc.get("input", {}).get("command", "")
        if "assert " in cmd and "Doğrulama" in cmd:
            return EvalResult("validation_present", True, 0.8,
                              "Assertion in code but no OK output captured")
    return EvalResult("validation_present", False, 0.0,
                      "No validation checkpoint found in any execute")


# ---------------------------------------------------------------------------
# 5. No shell exploration (ls, cat, os.listdir)
# ---------------------------------------------------------------------------
def eval_no_shell_exploration(tool_calls: list[dict], response: str) -> EvalResult:
    """Agent should not waste executes on ls/cat/os.listdir."""
    shell_patterns = ("os.listdir", "os.scandir", "glob.glob", "pathlib.Path")
    violations = []
    for tc in tool_calls:
        if tc["name"] != "execute":
            continue
        cmd = tc.get("input", {}).get("command", "")
        bare_cmd = cmd.strip().split()[0] if cmd.strip() else ""
        if bare_cmd in ("ls", "find", "cat", "head", "tail", "wc"):
            violations.append(f"shell: {bare_cmd}")
        for pat in shell_patterns:
            if pat in cmd:
                violations.append(f"python: {pat}")
    if violations:
        return EvalResult("no_shell_exploration", False, 0.0, "; ".join(violations[:3]))
    return EvalResult("no_shell_exploration", True, 1.0, "No filesystem exploration")


# ---------------------------------------------------------------------------
# 6. PDF/report generated (for report scenarios)
# ---------------------------------------------------------------------------
def eval_report_generated(tool_calls: list[dict], response: str) -> EvalResult:
    """For report scenarios: download_file should be called with a PDF."""
    for tc in tool_calls:
        if tc["name"] == "download_file":
            path = tc.get("input", {}).get("file_path", "")
            if path.endswith(".pdf"):
                return EvalResult("report_generated", True, 1.0,
                                  f"PDF generated: {path}")
    # Check if generate_html was at least called (dashboard without PDF)
    for tc in tool_calls:
        if tc["name"] == "generate_html":
            return EvalResult("report_generated", True, 0.7,
                              "HTML dashboard generated but no PDF download")
    return EvalResult("report_generated", False, 0.0,
                      "No PDF or HTML artifact produced")


# ---------------------------------------------------------------------------
# 7. Execute efficiency — stays within budget
# ---------------------------------------------------------------------------
def eval_execute_efficiency(tool_calls: list[dict], response: str,
                            max_expected: int = 6) -> EvalResult:
    """Agent should complete within the execute budget."""
    execute_count = sum(1 for tc in tool_calls if tc["name"] == "execute")
    blocked_count = sum(
        1 for tc in tool_calls
        if tc["name"] == "execute" and "⛔" in tc.get("output", "")
    )
    actual = execute_count - blocked_count

    if actual <= max_expected:
        return EvalResult("execute_efficiency", True, 1.0,
                          f"{actual} executes used (budget: {max_expected})")
    score = max(0.0, 1.0 - (actual - max_expected) * 0.2)
    return EvalResult("execute_efficiency", actual <= max_expected + 2, score,
                      f"{actual} executes used (budget: {max_expected}, {blocked_count} blocked)")


# ---------------------------------------------------------------------------
# 8. Conversation completeness — final response addresses the query
# ---------------------------------------------------------------------------
def eval_completeness(tool_calls: list[dict], response: str,
                      expected_keywords: list[str] | None = None) -> EvalResult:
    """Final response should contain expected keywords/concepts."""
    if not expected_keywords:
        # Basic check: response should not be empty or an error
        if not response or "hata" in response.lower() or "error" in response.lower():
            return EvalResult("completeness", False, 0.0,
                              "Response is empty or contains error")
        return EvalResult("completeness", True, 0.8,
                          "Response present (no keyword check)")

    # Search both response AND tool call outputs for keywords
    all_text = response.lower()
    for tc in tool_calls:
        out = tc.get("output", "") if isinstance(tc, dict) else getattr(tc, "output", "")
        all_text += " " + out.lower()

    found = [kw for kw in expected_keywords if kw.lower() in all_text]
    ratio = len(found) / len(expected_keywords) if expected_keywords else 1.0
    passed = ratio >= 0.5  # At least half the keywords present
    missing = [kw for kw in expected_keywords if kw.lower() not in all_text]
    reason = (f"Found {len(found)}/{len(expected_keywords)} keywords"
              + (f", missing: {missing[:3]}" if missing else ""))
    return EvalResult("completeness", passed, ratio, reason)


# ---------------------------------------------------------------------------
# Registry — maps evaluator names to functions
# ---------------------------------------------------------------------------
ALL_EVALUATORS = {
    "no_pickle": eval_no_pickle,
    "persistent_kernel": eval_persistent_kernel,
    "no_hardcoded_metrics": eval_no_hardcoded_metrics,
    "dashboard_integrity": eval_dashboard_integrity,
    "validation_present": eval_validation_present,
    "no_shell_exploration": eval_no_shell_exploration,
    "report_generated": eval_report_generated,
    "execute_efficiency": eval_execute_efficiency,
    "completeness": eval_completeness,
}

# Default set for most scenarios (report_generated only for report scenarios)
DEFAULT_EVALUATORS = [
    "no_pickle",
    "persistent_kernel",
    "no_hardcoded_metrics",
    "dashboard_integrity",
    "validation_present",
    "no_shell_exploration",
    "execute_efficiency",
    "completeness",
]
