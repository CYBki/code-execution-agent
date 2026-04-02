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
   → generate_html(dashboard)
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
- **Large combinations**: Product pair analysis → filter popular items first:
  `popular = df.groupby('col').size().pipe(lambda s: s[s > 50].index)`

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

### SELF-CHECK: Before generate_html() (MANDATORY)

⚠️ **`generate_html()` runs in a SEPARATE process — it cannot access Python variables.**
You must build the complete HTML string inside execute() and pass it as a literal to generate_html().

**Variables persist across execute() calls (persistent kernel):**
- m dict computed in execute #1 → available in execute #2+ ✅
- df loaded in execute #1 → available in execute #2+ ✅

**But generate_html() is NOT an execute — it's a separate tool:**
- generate_html(html_code=html) → html must be a complete string, not a variable reference

**Correct pattern:**
```python
# Execute: build HTML string using persisted variables (df, m already in kernel)
m = {'total_orders': df['Invoice'].nunique(), ...}  # df from previous execute
monthly_data = df.groupby('month')['revenue'].sum().tolist()

html = f'''
<h3>{m['total_orders']:,}</h3>
<script>const data = {monthly_data};</script>
'''
generate_html(html_code=html)  # Pass literal string — OK
```

**If user reports empty dashboard/PDF:**
1. Recognize: "generate_html() cannot access Python variables directly"
2. Build complete HTML string with data embedded inside execute()
3. Then pass the string to generate_html()

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
