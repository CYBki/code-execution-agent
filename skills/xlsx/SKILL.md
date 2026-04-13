---
name: xlsx
description: "Use when working with .xlsx, .xls, Excel files, spreadsheets, workbooks, or when user mentions formulas, cells, sheets, pivot tables, financial data, merged cells, or named ranges"
---

# Excel/XLSX Expertise

You are an expert Excel analyst. Follow these instructions precisely when working with Excel files.

## Analysis Workflow (ReAct Loop)

No fixed phase order — adapt to the user's query. Typical sequence:

```
1. DISCOVERY
   THOUGHT: "File uploaded, I need to understand its structure. NOT ls/os.listdir — use parse_file."
   → parse_file(file)   ← does NOT consume execute budget, always FIRST STEP
   OBSERVATION: [columns, types, preview, row count]
   DECISION: Schema seen → clean.

2. CLEANING
   THOUGHT: [Which columns needed, null status, type conversions]
   → execute(read + clean + print summary)
   OBSERVATION: [row count, cleaning summary, ✅ Validation OK]
   DECISION: Clean? Yes → analyze. No → CORRECTION LOOP.

3. ANALYSIS (df already in memory — no re-read from Excel)
   THOUGHT: [What is the user asking, which calculations needed]
   → execute(use df + analysis + validation block)
   OBSERVATION: [results + ✅ Validation OK]
   DECISION: Validation passed? Yes → move to report. No → CORRECTION LOOP.

4. REPORT (analysis + PDF in single script)
   THOUGHT: [Which metrics to include in report]
   → execute(compute from df + metrics dict + weasyprint PDF + validate)
   → execute(build HTML dashboard with real data + publish_html(html))
   → download_file(PDF)
   → Give user a SHORT summary (general findings — do NOT repeat specific numbers)
```

## Persistent Kernel — Variables Are Preserved

The Python kernel is persistent: `df`, variables, and imports are preserved across execute calls.

```python
# Execute 1: Read + clean (df stays in memory)
df = pd.read_excel('/home/sandbox/data.xlsx')
df = df.dropna(subset=['key_col'])
df['Date'] = pd.to_datetime(df['Date'])
print(f'✅ Loaded and cleaned: {len(df):,} rows')

# Execute 2+: df already in memory
print(f'df still here: {len(df):,} rows')
```

## Analysis Strategy

1. **Read the schema** → which columns exist, what are their types?
2. **What does the user want?** → analyze the query
3. **Which analyses are possible?** → decide based on available columns
4. **Skip impossible analyses** → if a column is missing, skip that analysis and inform the user

## Common Mistakes

- **Average calculation**: Row-level average or group average? Decide by context.
  Order value → `df.groupby('order_id')['amount'].sum().mean()` ✅  Row-level mean ❌
- **Negative values**: Don't delete — first understand. Refund? Debit? Distinguish gross/net.
- **Unique counting**: Use `.nunique()`, not `len()` or `count()`.
- **Large combinations (BLOCK: top-N scope reduction)**: Market basket, co-occurrence, pair analysis → include ALL items. SCOPE CHECK before writing code.
  ```python
  # ❌ BLOCK — these patterns are FORBIDDEN:
  popular_items = df['item'].value_counts().head(50).index  # arbitrary top-N
  df_filtered = df[df['item'].isin(popular_items)]           # shrinks analysis scope
  # SQL: LIMIT 50 to select items for analysis                # same problem in SQL

  # ✅ CORRECT — pandas + mlxtend (all items, statistical filter):
  from mlxtend.frequent_patterns import apriori, association_rules
  basket = df.groupby(['Invoice', 'StockCode'])['Quantity'].sum().unstack(fill_value=0)
  basket = (basket > 0)  # binary encoding
  frequent = apriori(basket, min_support=0.005, use_colnames=True, low_memory=True)
  rules = association_rules(frequent, metric='lift', min_threshold=1.5)

  # ✅ CORRECT — DuckDB (all items, HAVING filters result not input):
  # Self-join on ALL items, then filter by min co-occurrence count
  SELECT a.StockCode as item_a, b.StockCode as item_b, COUNT(*) as together
  FROM clean a JOIN clean b ON a.Invoice = b.Invoice AND a.StockCode < b.StockCode
  GROUP BY 1, 2
  HAVING COUNT(*) >= 20  -- statistical threshold on OUTPUT, not input scope
  ```

## Analysis Quality

### Validate Results
If you extracted categorical values, check the top 10 — do they truly represent that category?
```python
print(df['extracted_col'].value_counts().head(10))
# If output is nonsensical, fix the algorithm — don't include in report
```
If unknown/fallback ratio exceeds 20%: expand the algorithm.

### Score/Index — Normalize
```python
# ❌ WRONG: score = col_a * 0.4 + col_b * 0.4  (different scales → meaningless)
# ✅ CORRECT:
df['norm_a'] = (df['a'] - df['a'].min()) / (df['a'].max() - df['a'].min())
df['norm_b'] = (df['b'] - df['b'].min()) / (df['b'].max() - df['b'].min())
df['score'] = df['norm_a'] * 0.5 + df['norm_b'] * 0.5
```

### Derive Recommendations from Data
Every recommendation MUST contain CONCRETE numbers — generic statements FORBIDDEN.
- ❌ "Increase the budget"
- ✅ "Group A avg value is 127 but performance is 8.3 — a 20% increase still keeps it in the top segment"

### Disclose Analysis Limitations
At the end of the report: what assumptions were made, which cleaning steps may affect results.

## Process Rules

### Process ALL data
`.head(1000)`, `[:5000]`, `nrows=50000`, `nrows=5` → **FORBIDDEN**.
`parse_file` already provides the schema — don't re-read with `nrows`.
For display: `.head(10)`, `.most_common(20)` are fine.

**Scope reduction FORBIDDEN** — never limit analysis to top-N items/products/categories:
- ❌ `df[df['item'].isin(top_products.head(50))]` → misses real associations
- ❌ `LIMIT 25` in SQL for analysis data (OK only for display/preview)
- ✅ Use `min_support`, `min_count`, or `idf` thresholds — let statistics decide what's significant

### Validation (do it INSIDE the execute code)
Don't waste a separate execute — append to the END of analysis code:
```python
# === VALIDATION ===
assert len(df) > 0, 'DataFrame is empty!'
assert metric > 0, f'Metric is negative/zero: {metric}'
print(f'Nulls: {df.isnull().sum().sum()}')
print('✅ Validation OK')
```
If you don't see "✅ Validation OK" → do NOT include in report, fix first.

### Show formulas
For every derived metric, print its components:
`print(f'AOV = {total:,.0f} / {order_count:,} = {aov:.2f}')`

### Error handling
Catch with try/except inside the script — do NOT use a separate execute.
If execute was blocked: read the error message, fix only the problematic part.

### File validation
```python
assert os.path.exists(output_path), f'File not created: {output_path}'
print(f'OK: {output_path} ({os.path.getsize(output_path)/1024:.1f} KB)')
```

### Output file summary (MANDATORY)
After creating any output file, read it back and print its columns, shape, and a few sample rows.
Format is free — the goal is to confirm the output matches the user's request before delivering.
If the summary shows a mismatch (wrong columns, wrong row count, unexpected values), fix it before delivering.

### Metric computation and PDF must be in the same execute
NEVER hardcode numbers from previous execute output as `m = {'total': 1234, ...}`.
Every metric MUST be **computed in code** — df is already in memory.
```python
# ❌ WRONG — hardcoded numbers copied from previous execute output:
m = {'total_customers': 4383, 'total_revenue': 8348208.57}

# ✅ CORRECT — compute in the same execute (df in memory):
m = {
    'total_customers': df['Customer ID'].nunique(),
    'total_revenue': (df['Quantity'] * df['Price']).sum(),
}
```
Analysis and PDF generation MUST be completed in a **single execute**.

### Dashboard Generation — USE publish_html() INSIDE execute()

`publish_html(html_string)` is pre-loaded in the persistent kernel.
Call it inside your execute() code to render dashboards with **direct variable access**.

**Variables persist across ALL execute() calls (persistent kernel):**
- m dict computed in execute #3 → available in execute #7 (dashboard step) ✅
- segment_summary from execute #3 → available in dashboard step ✅
- country_analysis from execute #5 → available in dashboard step ✅
- hourly_pattern from execute #4 → available in dashboard step ✅
- Even across separate tool-call rounds — kernel NEVER resets

**⛔ ABSOLUTE BAN — Never create new dicts/lists with literal numbers (ANY domain):**
```python
# ❌ ANY of these patterns are FORBIDDEN — regardless of data domain
any_metrics = {'key1': 5863, 'key2': 17588623}  # HARDCODED!
any_data = [{'name': 'X', 'value': 508}]  # HARDCODED!
any_series = [890000, 1200000, 950000]  # FABRICATED!
```

**✅ CORRECT — Reference kernel variables directly (works for ANY data):**
```python
# Dashboard step — df_result, m, summary_df etc. from previous execute
# Step 1: Extract from kernel using DataFrame operations
labels = df_result['category_col'].tolist()  # ✅ .tolist()
values = df_result['metric_col'].tolist()  # ✅ .tolist()
kpi = m['some_key']  # ✅ dict reference

# Step 2: Embed in HTML
parts = []
parts.append(f'<div class="kpi">{kpi:,}</div>')
parts.append(f'<script>const labels={labels};const data={values};</script>')
publish_html('\\n'.join(parts))  # ✅ Real data, auto-rendered
```

**SELF-CHECK:** If you're about to write ANY number literal → STOP → that variable is in the kernel → use `.tolist()` or `m['key']`.

**RULE:** For any dashboard that uses analysis results → ALWAYS use `publish_html()` inside `execute()`.
Use kernel variables directly. Only use `generate_html()` for purely static HTML with zero data dependency.

## Quick Start

### Reading Excel Files — Always Check Sheet Count First

⚠️ **Do NOT use `pd.read_excel(path)` directly** — it only reads the first sheet.
Always check the sheet list first:

```python
import pandas as pd

file_path = '/home/sandbox/data.xlsx'
xls = pd.ExcelFile(file_path)
sheet_names = xls.sheet_names
print(f"Sheet count: {len(sheet_names)} → {sheet_names}")

if len(sheet_names) == 1:
    # Single sheet — read directly
    df = pd.read_excel(file_path)
    print(f"Single sheet: {df.shape}")
else:
    # Multiple sheets — load all into dict
    all_sheets = pd.read_excel(file_path, sheet_name=None)
    for name, sheet_df in all_sheets.items():
        print(f"  '{name}': {sheet_df.shape[0]:,} rows x {sheet_df.shape[1]} cols")
        print(f"    Columns: {list(sheet_df.columns)}")
```

**Multi-sheet analysis strategies (pandas, <40MB):**
```python
# Same columns (periodic: Jan/Feb/Mar) → concatenate
df_combined = pd.concat(
    [sheet_df.assign(sheet=name) for name, sheet_df in all_sheets.items()],
    ignore_index=True
)
print(f"Combined: {len(df_combined):,} rows")

# Different topics (Orders + Customers) → merge
df_orders = all_sheets['Orders']
df_customers = all_sheets['Customers']
df_merged = df_orders.merge(df_customers, on='Customer ID', how='left')

# Independent sheets → separate analysis
for name, sheet_df in all_sheets.items():
    print(f"{name}: {sheet_df.describe()}")
```

### File Size Detection — ALWAYS DO THIS FIRST

```python
import os

file_path = '/home/sandbox/data.xlsx'
file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
print(f"File size: {file_size_mb:.1f} MB")

if file_size_mb < 40:
    print("Strategy: Direct pandas load")
    # Use sheet detection pattern from above
elif file_size_mb < 500:
    print("Strategy: Convert to CSV + DuckDB lazy queries")
    # See large file handling below
else:
    print("Strategy: Chunked processing needed")
    # See large file handling below
```

**Size-based strategy selection:**

| File Size | Rows (approx) | Strategy | Expected Time |
|-----------|---------------|----------|---------------|
| < 40 MB | < 100k | Direct pandas + sheet detection | 5-10 sec |
| 40-200 MB | 100k-500k | Excel → CSV → DuckDB | 20-40 sec |
| 200-500 MB | 500k-1M | DuckDB lazy queries | 40-90 sec |
| > 500 MB | > 1M | Chunked + DuckDB | 2-5 min |

> **For large files ≥40MB, see: references/large_files.md**
> **For multi-file joins, see: references/multi_file_joins.md**

## Multi-Sheet Handling

→ See **Quick Start → Reading Excel Files** section for sheet detection and analysis strategies.

**Summary:**
- Always start with `pd.ExcelFile(path).sheet_names`
- Single sheet: `pd.read_excel(path)` ✔️
- Multiple sheets: `pd.read_excel(path, sheet_name=None)` → dict
- Same columns → `pd.concat(... assign(sheet=name))`
- Different topics → `merge(on='common_column')`
- ≥40MB → CSV conversion + DuckDB (see references/large_files.md)

## Report-Style Excel Format Issues (Header-Offset)

Auto-generated Excel reports (Logo, VMS, SAP, Netsis, etc.) often have metadata in the first few rows.
Actual column headers start at row 3-5.

**Don't confuse** with real pivot tables (pd.pivot_table output) — that's a different issue:
```
Row 1: "Material Stock Report - 01.03.2025"   ← report title (meta)
Row 2: "Period: Jan-Mar 2025"                 ← meta info
Row 3: "Prepared by: Accounting"              ← meta info
Row 4: (empty)
Row 5: material_code | material_name | qty    ← REAL header
Row 6: 10001         | Screw M6      | 500   ← data start
```

In auto-generated Excel reports (Logo, VMS, SAP, etc.) the first row is usually NOT the real data header.
After checking the `parse_file` schema, verify column names:

**Suspicious cases — check after `parse_file`:**
- Column name `Unnamed: 0`, `Unnamed: 1` → header row is at wrong position
- Column name looks like a label (`Report:`, `Date:`, `Period:`) → there's a title row above, `skiprows` needed
- First 1-3 rows are empty or metadata → skip with `skiprows=N`

```python
# Detect: which row has the real column names?
df_check = pd.read_excel(file_path, nrows=10, header=None)
for i, row in df_check.iterrows():
    non_null = row.dropna()
    print(f"Row {i}: {list(non_null.values)[:6]}")
# → Find which row contains actual column names
```

```python
# Case 1: First row is report title, 2nd row is column names
df = pd.read_excel(file_path, skiprows=1)

# Case 2: First N rows are metadata
df = pd.read_excel(file_path, header=2)  # 3rd row (0-indexed) is column header

# Case 3: No column names at all → define manually
df = pd.read_excel(file_path, header=None,
                   names=['material_code', 'material_name', 'quantity', 'unit'])

# Case 4: Column names correct but extra sub-header row exists (pivot)
df = pd.read_excel(file_path, skiprows=1)
df = df.dropna(how='all')          # Drop completely empty rows
df = df[df.iloc[:, 0].notna()]     # Drop rows where first column is empty
```

**If column names are still broken:**
```python
# Fix existing column names
df.columns = df.columns.str.strip()               # Remove leading/trailing whitespace
df.columns = df.columns.str.replace('\n', ' ')    # Remove newline characters
df = df.rename(columns={
    'Material\nCode': 'material_code',
    'Unnamed: 2':     'quantity',
})
```

## PDF Report Generation — WeasyPrint

Always use `weasyprint` for PDF (`fpdf2` has issues with Turkish/Unicode characters).
**Metric computation and PDF generation must be in the same execute.**

```python
import weasyprint
import os

# m dict — df already in memory (persistent kernel) — hardcoding FORBIDDEN
m = {
    'total':        int(df['ID'].nunique()),
    'revenue':      float((df['Qty'] * df['Price']).sum()),
    'analysis_date': __import__('datetime').datetime.now().strftime('%d.%m.%Y'),
}

html = f'''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<style>
  body    {{ font-family: Arial, sans-serif; margin: 40px; font-size: 13px; }}
  h1      {{ color: #1a365d; border-bottom: 3px solid #3182ce; }}
  h2      {{ color: #2c5282; border-left: 4px solid #3182ce; padding-left: 12px; }}
  .metric {{ background: #ebf8ff; padding: 12px; margin: 8px 0; border-radius: 4px; }}
  .value  {{ font-weight: bold; color: #c53030; font-size: 15px; }}
  table   {{ width: 100%; border-collapse: collapse; }}
  th      {{ background: #2b6cb0; color: white; padding: 10px; }}
  td      {{ padding: 8px; border-bottom: 1px solid #e2e8f0; }}
  .insight{{ background: #f0fff4; border-left: 4px solid #38a169; padding: 12px; }}
</style></head><body>
<h1>Analysis Report</h1>
<p><strong>Date:</strong> {m["analysis_date"]}</p>
<div class="metric">Total: <span class="value">{m["total"]:,}</span></div>
<div class="metric">Revenue: <span class="value">${m["revenue"]:,.2f}</span></div>
</body></html>'''

html_path = '/home/sandbox/temp_report.html'
pdf_path  = '/home/sandbox/rapor.pdf'
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

weasyprint.HTML(filename=html_path).write_pdf(pdf_path)
assert os.path.exists(pdf_path), f'PDF creation failed'
print(f'✅ PDF: {os.path.getsize(pdf_path)//1024} KB')
os.remove(html_path)
```

**Table loop (DataFrame → HTML table):**
```python
rows_html = ''
for _, row in top_df.iterrows():
    rows_html += f'<tr><td>{row["id"]}</td><td>{row["value"]:,.2f}</td></tr>\n'

html_table = f'''<table>
<tr><th>ID</th><th>Value</th></tr>
{rows_html}
</table>'''
```

**Date formatting — `[:10]` does NOT work on datetime objects:**
```python
# ❌ Wrong
date_str = row['InvoiceDate'][:10]

# ✅ Correct
date_str = pd.to_datetime(row['InvoiceDate']).strftime('%Y-%m-%d')

# ✅ Pull as string directly from DuckDB (safer)
# SELECT CAST(MIN(InvoiceDate) AS VARCHAR)[:10] as first_order
```

## Merged Cells Handling

Excel merged cells appear as NaN in non-first rows. Always forward-fill:

```python
df = pd.read_excel('/home/sandbox/data.xlsx')

# Forward fill merged cell values
df = df.ffill()

# Or fill specific columns only
df['Category'] = df['Category'].ffill()
```

### Detecting Merged Cells with openpyxl

```python
from openpyxl import load_workbook

wb = load_workbook('/home/sandbox/data.xlsx')
ws = wb.active

# List all merged cell ranges
for merged_range in ws.merged_cells.ranges:
    print(f"Merged: {merged_range}")
```

## Data Type Handling

```python
# Force column types during read
df = pd.read_excel('/home/sandbox/data.xlsx', dtype={
    'ID': str,           # Prevent leading zero loss
    'ZipCode': str,      # Keep as text
    'Amount': float,
})

# Date parsing
df = pd.read_excel('/home/sandbox/data.xlsx', parse_dates=['Date', 'Created'])

# Handle mixed types
df['Price'] = pd.to_numeric(df['Price'], errors='coerce')  # Non-numeric → NaN
```

## Date Filtering — NEVER Guess Format

`parse_file` output includes `date_columns` with detected format and samples from the actual Excel data.

**RULE:** Use the EXACT format from `date_columns` — never assume or convert to a different format.

```python
# parse_file output example:
# 'date_columns': {'Tarih': {'format': '%m/%d/%Y', 'samples': ['04/29/2025', '04/22/2025']}}

# Step 1: Read with detected format
fmt = '%m/%d/%Y'  # ← from parse_file date_columns
df['Tarih'] = pd.to_datetime(df['Tarih'], format=fmt)

# Step 2: User provides date in SAME format as Excel
user_date = pd.to_datetime(user_input, format=fmt)

# Step 3: Filter
filtered = df[df['Tarih'] < user_date]
```

**Step 4: Display and save — strftime for SCREEN ONLY, datetime for EXCEL:**
```python
# FOR SCREEN OUTPUT (print) — use strftime to show original format:
display_df = filtered.copy()
display_df['Tarih'] = display_df['Tarih'].dt.strftime(fmt)
print(display_df)  # ALL columns, dates in original Excel format

# FOR EXCEL OUTPUT (to_excel) — keep datetime, NEVER strftime:
# ❌ WRONG — converts to string, Excel shows '12/01/2026 with apostrophe
filtered['Tarih'] = filtered['Tarih'].dt.strftime(fmt)
filtered.to_excel('output.xlsx')

# ✅ CORRECT — dates stay as datetime, Excel formats them properly
filtered.to_excel('output.xlsx')  # Tarih column stays datetime
```

**CRITICAL:**
- If `date_columns` says `%m/%d/%Y` → use `%m/%d/%Y` for reading, filtering AND displaying
- If `date_columns` says `%d.%m.%Y` → use `%d.%m.%Y` for reading, filtering AND displaying
- NEVER show dates in pandas default `YYYY-MM-DD HH:MM:SS` format — always use `strftime(fmt)` for output
- NEVER convert Excel dates to a different format than what `parse_file` detected
- If user enters date in a different format than Excel, ask user to use the Excel format

## Common Analysis Patterns

### Exploratory Data Analysis (EDA)

```python
import pandas as pd

df = pd.read_excel('/home/sandbox/data.xlsx')

# Overview
print(f"Shape: {df.shape}")
print(f"\nColumn types:\n{df.dtypes}")
print(f"\nNull counts:\n{df.isnull().sum()}")
print(f"\nBasic stats:\n{df.describe()}")

# Unique values per column
for col in df.columns:
    n_unique = df[col].nunique()
    print(f"{col}: {n_unique} unique values")
    if n_unique <= 10:
        print(f"  Values: {df[col].value_counts().to_dict()}")
```

### Group-By Aggregation

```python
# Sales by category
summary = df.groupby('Category').agg(
    total_revenue=('Revenue', 'sum'),
    avg_revenue=('Revenue', 'mean'),
    count=('Revenue', 'count'),
).sort_values('total_revenue', ascending=False)

print(summary)
```

### Pivot Tables

```python
pivot = pd.pivot_table(
    df,
    values='Revenue',
    index='Category',
    columns='Quarter',
    aggfunc='sum',
    fill_value=0,
    margins=True  # Add row/column totals
)
print(pivot)
```

### Time Series Analysis

```python
# Ensure date column is datetime
df['Date'] = pd.to_datetime(df['Date'])

# Monthly aggregation
monthly = df.set_index('Date').resample('M').agg({
    'Revenue': 'sum',
    'Quantity': 'sum',
    'OrderID': 'count'
}).rename(columns={'OrderID': 'order_count'})

print(monthly)
```

## Color Coding Standards (Financial Models)

When creating or reading financial Excel files, follow these color conventions:

| Color | RGB | Use |
|-------|-----|-----|
| **Blue text** | (0, 0, 255) | Hardcoded inputs / assumptions |
| **Black text** | (0, 0, 0) | Formulas and calculations |
| **Green text** | (0, 128, 0) | Links within the workbook |
| **Red text** | (255, 0, 0) | Links to external workbooks |

```python
from openpyxl.styles import Font

# Apply color coding
ws['B5'].font = Font(color='0000FF')  # Blue = input
ws['C5'].font = Font(color='000000')  # Black = formula
```

## Formula Construction Rules

When the agent creates or modifies Excel formulas:

1. **Place assumptions in separate cells** — never hardcode numbers in formulas
2. **Use cell references**: `=B5*(1+$B$6)` NOT `=B5*1.05`
3. **Test formulas on 2-3 cells** before applying to full range
4. **Use absolute references** (`$B$6`) for fixed parameters
5. **Check for errors** after formula application

### Zero Formula Error Requirement

Every output workbook MUST have zero formula errors. Check for:

```python
from openpyxl import load_workbook

wb = load_workbook('/home/sandbox/output.xlsx')
ws = wb.active

error_types = ['#REF!', '#DIV/0!', '#VALUE!', '#NAME?', '#NULL!', '#N/A', '#NUM!']
errors_found = []

for row in ws.iter_rows():
    for cell in row:
        if cell.value in error_types:
            errors_found.append(f"{cell.coordinate}: {cell.value}")

if errors_found:
    print(f"ERRORS FOUND ({len(errors_found)}):")
    for e in errors_found:
        print(f"  {e}")
else:
    print("✅ Zero formula errors — all clear")
```

## Writing Excel Output

### Basic Write

```python
# Write single sheet
df.to_excel('/home/sandbox/output.xlsx', index=False, sheet_name='Results')

# Write multiple sheets
with pd.ExcelWriter('/home/sandbox/output.xlsx', engine='openpyxl') as writer:
    sales_df.to_excel(writer, sheet_name='Sales', index=False)
    summary_df.to_excel(writer, sheet_name='Summary', index=False)
```

### Styled Output with openpyxl

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows

wb = Workbook()
ws = wb.active
ws.title = "Analysis Results"

# Write header
headers = list(df.columns)
header_font = Font(bold=True, color='FFFFFF')
header_fill = PatternFill(start_color='2F5496', end_color='2F5496', fill_type='solid')

for col_idx, header in enumerate(headers, 1):
    cell = ws.cell(row=1, column=col_idx, value=header)
    cell.font = header_font
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal='center')

# Write data rows
for row_idx, row in enumerate(dataframe_to_rows(df, index=False, header=False), 2):
    for col_idx, value in enumerate(row, 1):
        ws.cell(row=row_idx, column=col_idx, value=value)

# Auto-adjust column widths
for col in ws.columns:
    max_length = max(len(str(cell.value or '')) for cell in col)
    ws.column_dimensions[col[0].column_letter].width = min(max_length + 2, 50)

wb.save('/home/sandbox/output.xlsx')
print("✅ Styled Excel file saved")
```

## Named Ranges

```python
from openpyxl import load_workbook

wb = load_workbook('/home/sandbox/data.xlsx')

# List all named ranges
for name, defn in wb.defined_names.items():
    print(f"{name}: {defn.attr_text}")

# Read data from named range
from openpyxl.utils import range_boundaries
for title, coord in wb.defined_names['SalesData'].destinations:
    ws = wb[title]
    min_col, min_row, max_col, max_row = range_boundaries(coord)
    data = []
    for row in ws.iter_rows(min_row=min_row, max_row=max_row,
                             min_col=min_col, max_col=max_col, values_only=True):
        data.append(row)
```

## Common Pitfalls Checklist

Before finalizing any Excel analysis, verify:

- [ ] **Column mapping**: DataFrame column index 64 = Excel column BL (not BK). Use `openpyxl.utils.get_column_letter()` for conversion
- [ ] **Row offset**: DataFrame row 5 = Excel row 6 (Excel is 1-indexed, header is row 1)
- [ ] **NaN handling**: Use `pd.notna(value)` or `.fillna()` — never compare with `==`
- [ ] **Division by zero**: Check denominator before using `/` operator
- [ ] **File size check**: Always check `os.path.getsize()` before loading. Use DuckDB if ≥40MB
- [ ] **Sheet name verification**: Always check `pd.ExcelFile().sheet_names` before reading specific sheets
- [ ] **Leading zeros**: Phone numbers, ZIP codes, IDs — read as `dtype=str`
- [ ] **Date formats**: Verify `parse_dates=[]` or `pd.to_datetime()` after reading
- [ ] **Encoding**: For CSV exports from Excel, try `encoding='utf-8-sig'` if BOM issues
- [ ] **Merged cells**: Forward-fill with `df.ffill()` after reading

## Financial Modeling Best Practices

When building financial models in Excel:

1. **Separate inputs from calculations** — inputs on dedicated sheet/section with blue font
2. **One formula per row/column** — avoid mixing formulas in the same range
3. **No circular references** — always check with `wb.calculation.calcMode`
4. **Version control** — save timestamped copies before major changes
5. **Documentation** — add a "Notes" sheet explaining assumptions
6. **Sensitivity analysis** — create data tables for key assumptions
7. **Check totals** — verify sum of parts equals total at each level

### Common Financial Formulas

```python
# Compound growth
future_value = present_value * (1 + rate) ** periods

# CAGR
cagr = (end_value / start_value) ** (1 / years) - 1

# NPV (pure Python — np.npv removed in NumPy 1.24)
npv = sum(cf / (1 + discount_rate) ** i for i, cf in enumerate(cash_flows))

# IRR (scipy optimize — np.irr removed in NumPy 1.24)
from scipy.optimize import brentq
irr = brentq(lambda r: sum(cf / (1 + r) ** i for i, cf in enumerate(cash_flows)), -0.5, 10.0)
```


## Column Addition Rules
- When user asks for ONE column, add exactly ONE column — no "bonus" extras
- If currency name is ambiguous (e.g. "kron" could be DKK/SEK/NOK), ASK the user which one before adding
- Never add multiple currency pairs when only one was requested
- Always verify the column was added: `print(df.columns.tolist())` after modification

## File Handling Rules
- Always verify the exact filename the user references — "12gun" ≠ "11gun"
- If multiple similar files exist, explicitly confirm which file to use before proceeding
- When user says "buna ekle" (add to this), they mean the file they just mentioned — not a different one
- One clear action per response — never repeat previous responses in the current answer
- If you made an error, acknowledge briefly and move forward with the correct action


## Currency Addition Verification Rules

- When adding currency exchange rate columns, ALWAYS execute a verification step after the addition
- After adding any new column, print `df.columns.tolist()` to show the column was actually created
- For currency conversions, print `df[['original_currency_col', 'new_exchange_rate_col']].head()` to prove values exist
- When user requests currency data like "japon yeni tl kuru", add the JPY/TRY exchange rate column AND show sample values
- Never claim a column was added without executing code that proves it exists in the dataframe
- Always end currency addition tasks by showing the updated dataframe structure and sample data


## Code Execution Display Rules
- Always include `print()` statements to show filtering results: `print(f"After filtering: {len(filtered_df):,} rows")`
- When adding calculated columns, immediately display the new column: `print(df[['original_col1', 'original_col2', 'new_column']].head())`
- For datetime calculations, show sample values to verify correctness: `print(df[['timestamp1', 'timestamp2', 'calculated_hours']].head(3))`
- Never claim completion without showing the actual filtered data and new column values in the output
- End each filtering/calculation step with a validation print showing row counts and sample data


## Data Validation Rules
- After reading Excel files, ALWAYS verify data diversity: check `df['column'].value_counts()` to ensure values aren't suspiciously uniform
- When filtering data (e.g., "values > 5"), ALWAYS show the filtered results with `print(filtered_df)` or `print(filtered_df.head(10))` to prove the filter worked
- Before claiming "all X have value Y", verify with `df['column'].nunique()` and `df['column'].describe()` to check for data loading issues
- When adding categorical columns based on numeric ranges, validate the new column distribution with `df['new_column'].value_counts()`
- If all values in a numeric column are identical, investigate potential parsing errors before proceeding with analysis


## Data Filtering and Column Addition Validation

- Always show the actual filtered results after applying conditions — use `print(filtered_df.head())` or `print(filtered_df[['key_columns']].head())`
- After adding new columns, immediately validate with `print(df[['new_column_name']].value_counts())` to show the distribution
- When filtering data, print the count: `print(f"Found {len(filtered_df):,} rows matching criteria")`
- For categorical column additions, show sample rows: `print(df[['original_col', 'new_col']].head(10))`
- Never claim completion without showing execute output — always provide concrete evidence of the work done


## Date Filtering Rules
- When user requests specific YEAR filtering, ALWAYS check if that year EXISTS in the dataset first
- Before applying date filters, print the actual date range: `print(f"Date range in data: {df['date_col'].min()} to {df['date_col'].max()}")`
- If requested year is NOT found, inform user immediately: "No data found for [year]. Available years: [list]"
- Never silently apply filters that return zero results without explaining why


## Excel Output Generation Rules

- When user asks for Excel output ("excel çıktısı", "Excel file", "export to Excel"), ALWAYS execute code that creates an actual .xlsx file
- Use `df.to_excel('/home/sandbox/output.xlsx', index=False)` to create the file
- After creating Excel file, ALWAYS call `download_file('output.xlsx')` to make it available
- Verify file creation with `os.path.exists('/home/sandbox/output.xlsx')` before claiming success
- Never claim Excel file is "ready for download" without actually executing file creation code
- Include sheet naming when appropriate: `df.to_excel(path, sheet_name='Data', index=False)`


## Turkish Language Query Handling
- When user writes in Turkish, respond in Turkish and clarify what they want before proceeding
- "tm excel ciktisini da ver" means "also give me the tm excel output" - ask what specific data/analysis they want exported
- Never claim to create files without actually executing the code and showing the file was created
- Always use download_file() to deliver Excel files to user, don't just mention creating them
- After creating Excel output, verify file exists and show first few rows: `print(f"✅ Excel file created: {filename}, {len(df)} rows")`


## Multi-Sheet Excel Requirements
- Always check if file has multiple sheets: `xl = pd.ExcelFile(filepath)` then `print(xl.sheet_names)`
- When user mentions a specific sheet name (e.g. "Marmara sayfasında"), read THAT sheet: `pd.read_excel(filepath, sheet_name='Marmara')`
- For "all sheets" operations, iterate through ALL sheets: `for sheet in xl.sheet_names:`
- Never assume single sheet structure when user mentions sheet names or "all sheets"
- Before filtering or adding columns, verify the column exists in target sheet(s)
- When adding columns to multiple sheets, apply the operation to each sheet individually


## Vague Query Handling Rules

- When user says "I uploaded a new file" or similar without specific requests, ALWAYS ask what they want to analyze before starting any work
- Before using parse_file(), confirm the user wants file analysis — don't assume
- If query lacks analytical intent (just mentions upload), respond: "I see you uploaded a file. What would you like me to analyze or calculate from it?"
- Never start discovery phase for pure upload notifications without analytical requests


## Ambiguous Query Handling
- When user input is unclear, ambiguous, or just "yes/no" responses, STOP and ask for clarification
- Never assume what the user wants — ask specific questions about their data analysis needs
- Before starting any analysis workflow, verify the user has provided a clear, actionable request
- If query is in another language or seems incomplete, respond: "I need more details about what analysis you'd like me to perform on your data"


## Network Error Recovery Rules

- When getting "Network connectivity error: [Errno 111] Connection refused", STOP trying to execute the same code repeatedly
- Network errors are environment issues, not code issues — DO NOT enter correction loops
- If execute fails with network error, immediately inform user: "I'm experiencing connectivity issues that prevent code execution. Please try again in a moment."
- Never waste execute budget on identical retries when the error is clearly environmental
- Before any execute attempt, use parse_file() first to verify file access without consuming execute budget


## Network Error Recovery Rules

- When execute() fails with "Network connectivity error" or "Connection refused", STOP trying execute() immediately
- Instead, use parse_file() first to understand the file structure — this tool works without network
- After parse_file() succeeds, try execute() again with simpler code blocks
- If execute() still fails after parse_file(), inform user that analysis cannot proceed due to system limitations
- Never retry the same failing execute() command multiple times — each retry wastes limited execution budget


## Network Error Recovery Rules
- When network connectivity errors occur, NEVER retry the same code immediately
- If pandas.read_excel() fails with network error, the file is already uploaded — use parse_file() tool instead
- Always start with parse_file() to read uploaded files, not pd.read_excel() directly
- If execute() fails with "Connection refused", switch to parse_file() for file reading
- After parse_file() succeeds, use the returned dataframe directly in subsequent execute() calls


## Network Error Prevention Rules

- NEVER use `os.path.exists()` or `os.path.getsize()` on the first step — these cause network connectivity errors
- ALWAYS start with `parse_file(filename)` to check file existence and get schema — this is the ONLY safe way to verify files
- If parse_file fails, the file doesn't exist — inform user immediately, don't attempt execute() 
- Before any execute() call, ensure you have successfully run parse_file() first
- When network errors occur, do NOT retry the same code — switch to parse_file() instead


## Network Error Recovery Rules
- When getting "Connection refused" or network errors, STOP trying to read Excel files directly
- Network errors mean pandas.read_excel() is blocked — use alternative approach immediately
- On network error: try `import openpyxl; wb = openpyxl.load_workbook(file_path)` as fallback
- If openpyxl also fails, inform user that Excel file access is currently blocked
- Never retry the same failing pandas.read_excel() command multiple times
- Always check for file existence with `os.path.exists(file_path)` before attempting any Excel operations
- When file access fails, explain the technical limitation rather than consuming all execute attempts


## Query Filtering Rules
- When filtering produces zero results, ALWAYS inform the user that no rows match the criteria
- NEVER substitute alternative filters without explicit user permission
- Before changing filter conditions, ask: "No rows match [original criteria]. Would you like me to adjust the filters?"
- When user requests specific conditions (e.g., Quantity > 10 AND Category = 'Giyim'), apply exactly those conditions
- If no results found, show the actual data ranges: "Found Quantity range: X-Y, Categories available: [list]"
- Only proceed with column additions/calculations AFTER addressing the filtering results


## Excel Library Dependencies

- Always import required Excel libraries at the start: `import pandas as pd` and `import openpyxl`
- If xlrd error occurs, use `engine='openpyxl'` parameter: `pd.read_excel(file, engine='openpyxl')`
- For Excel output, use `df.to_excel('output.xlsx', index=False, engine='openpyxl')`
- Never assume xlrd is available — openpyxl handles both .xlsx reading and writing
- Test the Excel read immediately after import to catch engine issues early


## Data Validation Before Processing Rules

- Before filtering data, ALWAYS check if the filter criteria exist: `df['column'].unique()` or `df['column'].value_counts()`
- If filter values don't exist (e.g., no "Nike" brand, no >20% discount), INFORM user immediately with available options
- Never silently skip filtering tasks — always attempt the filter and report results even if empty
- When no records match criteria, show user what values ARE available: "No Nike found. Available brands: [list]"
- Complete ALL user requests even if intermediate steps yield empty results
- If filtering returns 0 rows, still proceed with remaining tasks (adding columns, Excel output) on original data


## Excel Query Execution Rules
- When user requests filtering by specific values (e.g., "Store_ID is S001"), attempt the filter immediately — do not ask clarifying questions about format
- If the exact column name doesn't exist, try common variations (Store_ID, StoreID, store_id) before asking questions
- When user asks for Excel output, always end with `df.to_excel()` and `download_file()` — never stop at analysis only
- For date column operations (extracting year, month), use `pd.to_datetime()` first, then `.dt.year` or `.dt.month`
- Complete the full workflow: filter → add columns → export Excel file — do not pause for clarification on straightforward requests


## Column Existence Verification Rules

- Before filtering on ANY column, always verify it exists: `print(df.columns.tolist())` 
- If a requested filter column is missing, inform user immediately — do NOT skip the filter silently
- When applying multiple filters, check ALL required columns exist before starting any filtering operations
- Always apply ALL requested filters in sequence — never skip filters even if one seems redundant


## Data Filtering and Output Rules
- Before filtering by ANY value, check what values actually exist: print(df['column_name'].unique()) or df['column_name'].value_counts()
- If user requests filtering by a value that doesn't exist, inform user of available options and ask for clarification
- When user asks for "Excel output" at the end, ALWAYS save the final filtered DataFrame to Excel using df.to_excel()
- Always validate filters work before proceeding: print(f"Filtered to {len(filtered_df)} rows") after each filter
- If filtering results in 0 rows, stop and inform user that no records match their criteria


## User Requirement Adherence Rules
- When user specifies multiple filter conditions with "AND" logic, apply ALL conditions even if some return zero results
- NEVER skip or modify user-specified filter criteria — if Quantity > 20 yields no rows, report this explicitly but still attempt remaining filters
- If a filter condition produces empty results, inform user about the actual data range: "No rows found with Quantity > 20. Data range: [min-max]"
- Complete ALL requested tasks in sequence, even when earlier filters reduce the dataset
- When adding categorical columns, use the EXACT column name requested by user (preserve language/format)


## Column Name Precision Rules
- When user specifies an EXACT column name (e.g. "Şirket kodu"), use that EXACT name — never substitute with similar columns
- Before filtering, always verify the column exists: `print(df.columns.tolist())` and `print(df['exact_column_name'].unique()[:10])`
- If the exact column doesn't exist, inform user and ask which available column to use instead
- Never assume "Şirket tanım" equals "Şirket kodu" — these are different fields with different values


## Network Error Recovery Rules

- When encountering "peer closed connection" or "Connection refused" errors, NEVER retry the same code
- If Excel file creation fails with network errors, switch to CSV output immediately: `df.to_csv(filename, index=False)`
- For multiple sheets requirement after network failure, create separate CSV files: `df_2009.to_csv('year_2009.csv')` and `df_2010.to_csv('year_2010.csv')`
- Always test file operations with simple `print("Test")` first if previous network errors occurred
- When Excel output specifically requested but fails, inform user that CSV alternative is provided due to system limitations


## Excel Sheet Modification Verification Rules

- After filtering rows from a sheet, ALWAYS print the before/after row counts: `print(f"Sheet '{sheet_name}': {old_count} → {new_count} rows after filtering")`
- After adding columns to a sheet, ALWAYS verify the column was added: `print(f"Added column to '{sheet_name}': {list(df.columns)}")`
- When modifying Excel files, ALWAYS save the result and confirm file creation: `df.to_excel('output.xlsx'); print("✅ Excel file saved successfully")`
- For multi-sheet operations, process each sheet separately and report completion status for each one
- Before claiming task completion, validate that ALL requested modifications were actually performed by printing evidence


## Multi-Sheet Excel Analysis Rules

- When user mentions specific sheet names, ALWAYS verify those sheets exist using `xl.sheet_names` before proceeding
- If user asks to filter by column values that seem redundant (e.g., MARKA="NAOS" in sheet named "NAOS"), confirm the logic with user before executing
- For conditional column additions, use `np.where()` or `pd.cut()` for clean categorization logic
- When adding status columns, always validate the new column was created: `print(df['new_column'].value_counts())`
- Before filtering data, check if the filter column exists: `if 'MARKA' in df.columns:` then proceed
- If requested filter returns empty results, inform user and show available values: `df['column'].unique()`


## DuckDB Timeout Prevention Rules

- When Excel files are large (>100MB or >500k rows), NEVER use DuckDB for full sheet reads — it causes 180s timeouts
- For multi-sheet operations: read ONE sheet at a time with pandas `pd.read_excel(file, sheet_name='specific_sheet')`
- Apply filters IMMEDIATELY after reading each sheet to reduce memory usage: `df = df[df['Country'] == 'United Kingdom']`
- Add calculated columns BEFORE any complex operations: `df['Total_Revenue'] = df['Quantity'] * df['Price']`
- If pandas read also times out, use `chunksize` parameter or process sheets separately
- Never attempt to read multiple large sheets simultaneously in one execute block


## Large File Performance Rules
- Before processing Excel sheets with >100k rows, use DuckDB directly on CSV files — never load entire datasets into pandas DataFrames
- For multi-sheet Excel operations on large files: process each sheet separately using DuckDB, write results to temporary CSV files, then combine into final Excel using pandas in chunks
- Always check row count first: if any sheet >50k rows, switch to streaming/chunked approach immediately
- When creating Excel output from large data: use `chunksize=10000` parameter in pandas operations to avoid memory/timeout issues
- Never attempt full DataFrame operations (groupby, merge, calculations) on datasets >100k rows without chunking strategy
