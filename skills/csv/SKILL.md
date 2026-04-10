---
name: csv
description: "Use when working with .csv, .tsv files, comma-separated data, tab-separated data, large CSV files, or when user mentions DuckDB or lazy SQL queries"
---

# CSV Processing Expertise

You are an expert at working with CSV/TSV files efficiently.

## Analysis Workflow

```
1. DISCOVERY  → parse_file(file)  ← does NOT consume execute budget, always FIRST STEP
2. CLEANING   → execute(read + clean + print summary)
3. ANALYSIS   → execute(df already in memory — analysis + validation)
4. REPORT     → execute(metrics dict + weasyprint PDF) → execute(publish_html(dashboard)) → download_file
```

## Persistent Kernel — Variables Are Preserved

The Python kernel is persistent: `df`, variables, and imports are preserved across execute calls.

```python
# Execute 1: Read + clean
df = pd.read_csv('/home/sandbox/data.csv')
df = df.dropna(subset=['key_col'])
print(f'✅ Loaded: {len(df):,} rows')

# Execute 2+: df already in memory
print(f'df still here: {len(df):,} rows')
```

## Process Rules

- Process ALL data — `.head(1000)` or `nrows=50000` FORBIDDEN (except `nrows=5` for schema)
- For every critical metric: `assert not pd.isna(x) and x > 0` + print
- Validation at the END of analysis execute: `print('✅ Validation OK')`
- Use try/except inside the script — do NOT use a separate execute

### Output file summary (MANDATORY)
After creating any output file, read it back and print its columns, shape, and a few sample rows.
Format is free — the goal is to confirm the output matches the user's request before delivering.
If the summary shows a mismatch (wrong columns, wrong row count, unexpected values), fix it before delivering.

## Basic CSV Reading

```python
import pandas as pd

# Standard CSV
df = pd.read_csv('/home/sandbox/data.csv')
print(f"Shape: {df.shape}")
print(df.head())

# TSV (tab-separated)
df = pd.read_csv('/home/sandbox/data.tsv', sep='\t')

# Custom separator
df = pd.read_csv('/home/sandbox/data.txt', sep='|')

# Handle encoding issues
df = pd.read_csv('/home/sandbox/data.csv', encoding='utf-8-sig')  # BOM-aware
df = pd.read_csv('/home/sandbox/data.csv', encoding='latin-1')    # Western European
```

## File Size Detection

```python
import os

file_path = '/home/sandbox/data.csv'
file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
print(f"File size: {file_size_mb:.1f} MB")

if file_size_mb < 50:
    print("Strategy: Direct pandas load")
    df = pd.read_csv(file_path)
else:
    print("Strategy: DuckDB lazy queries (no full memory load)")
```

## DuckDB for Large CSV Files (>50MB)

```python
import duckdb

# DuckDB reads CSV lazily — no full memory load
result = duckdb.sql("""
    SELECT
        category,
        COUNT(*) as count,
        SUM(revenue) as total_revenue,
        AVG(revenue) as avg_revenue
    FROM read_csv_auto('/home/sandbox/data.csv')
    GROUP BY category
    ORDER BY total_revenue DESC
""").df()

print(result)
```

### Quick Row Count

```python
import duckdb

count = duckdb.sql("""
    SELECT COUNT(*) FROM read_csv_auto('/home/sandbox/data.csv')
""").fetchone()[0]
print(f"Total rows: {count:,}")
```

### Sample Data

```python
import duckdb

sample = duckdb.sql("""
    SELECT * FROM read_csv_auto('/home/sandbox/data.csv') LIMIT 100
""").df()
print(sample.dtypes)
print(sample.head())
```

## Common CSV Options

```python
import pandas as pd

# Skip rows, custom header
df = pd.read_csv('/home/sandbox/data.csv', skiprows=3, header=0)

# No header — assign column names
df = pd.read_csv('/home/sandbox/data.csv', header=None, names=['A', 'B', 'C'])

# Parse dates during read
df = pd.read_csv('/home/sandbox/data.csv', parse_dates=['date', 'created_at'])

# Force column types
df = pd.read_csv('/home/sandbox/data.csv', dtype={'zip_code': str, 'id': str})

# Handle missing values
df = pd.read_csv('/home/sandbox/data.csv', na_values=['N/A', 'null', '-', ''])

# Only read specific columns
df = pd.read_csv('/home/sandbox/data.csv', usecols=['name', 'revenue', 'date'])

# Read first N rows only (for preview)
df = pd.read_csv('/home/sandbox/data.csv', nrows=1000)
```

## Writing CSV

```python
# Standard write
df.to_csv('/home/sandbox/output.csv', index=False)

# Custom separator
df.to_csv('/home/sandbox/output.tsv', sep='\t', index=False)

# Excel-compatible (BOM for UTF-8)
df.to_csv('/home/sandbox/output.csv', index=False, encoding='utf-8-sig')
```

## Common Pitfalls

- [ ] **Encoding**: Try `utf-8`, `utf-8-sig`, `latin-1`, `cp1252` if garbled text appears
- [ ] **Separator detection**: Check if file uses `,`, `\t`, `;`, or `|` as delimiter
- [ ] **Quoting**: Use `quoting=csv.QUOTE_ALL` if fields contain the separator character
- [ ] **Large files**: Always check `os.path.getsize()` first — use DuckDB if >50MB
- [ ] **Mixed types**: Use `dtype=str` to prevent pandas from guessing wrong types
- [ ] **Leading zeros**: Read ID/zip columns as `dtype=str` to preserve leading zeros
