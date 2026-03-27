# Multi-File Join Patterns with DuckDB

This reference is loaded when the user uploads 2+ Excel files or mentions keywords like "join", "merge", "combine", "match", "lookup".

## Workflow: Multiple Excel Files → CSV → DuckDB JOIN

1. Convert each Excel file to CSV
2. Use DuckDB SQL JOINs across CSV files (memory-efficient)
3. Return aggregated result as pandas DataFrame

## Basic Multi-File Join

```python
import pandas as pd
import duckdb

# Step 1: Convert all Excel files to CSV
print("Converting files to CSV...")
pd.read_excel('/home/daytona/sales.xlsx').to_csv('/home/daytona/sales.csv', index=False)
pd.read_excel('/home/daytona/products.xlsx').to_csv('/home/daytona/products.csv', index=False)
print("Conversion complete")

# Step 2: DuckDB JOIN query (memory-efficient)
result = duckdb.sql("""
    SELECT
        s.date,
        p.product_name,
        p.category,
        SUM(s.quantity) as total_sold,
        SUM(s.revenue) as total_revenue
    FROM read_csv_auto('/home/daytona/sales.csv') s
    JOIN read_csv_auto('/home/daytona/products.csv') p
        ON s.product_id = p.product_id
    GROUP BY s.date, p.product_name, p.category
    ORDER BY total_revenue DESC
""").df()

print(result)
```

## Join Types

### INNER JOIN (default — only matching rows)

```python
result = duckdb.sql("""
    SELECT s.*, p.product_name, p.category
    FROM read_csv_auto('/home/daytona/sales.csv') s
    JOIN read_csv_auto('/home/daytona/products.csv') p
        ON s.product_id = p.product_id
""").df()
```

### LEFT JOIN (all rows from left, matching from right)

```python
result = duckdb.sql("""
    SELECT s.*, p.product_name, p.category
    FROM read_csv_auto('/home/daytona/sales.csv') s
    LEFT JOIN read_csv_auto('/home/daytona/products.csv') p
        ON s.product_id = p.product_id
""").df()

# Check for unmatched rows
unmatched = result[result['product_name'].isna()]
if len(unmatched) > 0:
    print(f"Warning: {len(unmatched)} sales rows have no matching product")
```

### FULL OUTER JOIN (all rows from both sides)

```python
result = duckdb.sql("""
    SELECT
        COALESCE(s.product_id, p.product_id) as product_id,
        s.revenue,
        p.product_name
    FROM read_csv_auto('/home/daytona/sales.csv') s
    FULL OUTER JOIN read_csv_auto('/home/daytona/products.csv') p
        ON s.product_id = p.product_id
""").df()
```

## VLOOKUP-Style Patterns via SQL

Excel VLOOKUP is equivalent to LEFT JOIN in SQL:

```python
# Excel: =VLOOKUP(A2, products!A:B, 2, FALSE)
# SQL equivalent:
result = duckdb.sql("""
    SELECT
        s.*,
        p.product_name  -- This is the "looked up" value
    FROM read_csv_auto('/home/daytona/transactions.csv') s
    LEFT JOIN read_csv_auto('/home/daytona/catalog.csv') p
        ON s.product_id = p.product_id
""").df()
```

## Multi-File Conversion Workflow

When dealing with 3+ files:

```python
import pandas as pd
import os

excel_files = [
    '/home/daytona/sales_2023.xlsx',
    '/home/daytona/sales_2024.xlsx',
    '/home/daytona/products.xlsx',
    '/home/daytona/regions.xlsx',
]

csv_files = {}
for excel_path in excel_files:
    csv_path = excel_path.replace('.xlsx', '.csv')
    df = pd.read_excel(excel_path)
    df.to_csv(csv_path, index=False)
    csv_files[os.path.basename(csv_path)] = csv_path
    print(f"  {os.path.basename(excel_path)}: {len(df)} rows")
    del df

print(f"\nConverted {len(csv_files)} files")
```

## Time Series Comparison (Year-over-Year)

```python
import duckdb

# Stack yearly files + compare
result = duckdb.sql("""
    WITH combined AS (
        SELECT *, 2023 as year FROM read_csv_auto('/home/daytona/sales_2023.csv')
        UNION ALL
        SELECT *, 2024 as year FROM read_csv_auto('/home/daytona/sales_2024.csv')
    )
    SELECT
        product_name,
        SUM(CASE WHEN year = 2023 THEN revenue ELSE 0 END) as revenue_2023,
        SUM(CASE WHEN year = 2024 THEN revenue ELSE 0 END) as revenue_2024,
        SUM(CASE WHEN year = 2024 THEN revenue ELSE 0 END) -
        SUM(CASE WHEN year = 2023 THEN revenue ELSE 0 END) as yoy_change
    FROM combined
    GROUP BY product_name
    ORDER BY yoy_change DESC
""").df()

print(result)
```

## Multi-Source Aggregation

Combine revenue from multiple regional files:

```python
result = duckdb.sql("""
    WITH all_regions AS (
        SELECT *, 'North' as region FROM read_csv_auto('/home/daytona/north.csv')
        UNION ALL
        SELECT *, 'South' as region FROM read_csv_auto('/home/daytona/south.csv')
        UNION ALL
        SELECT *, 'East' as region FROM read_csv_auto('/home/daytona/east.csv')
    )
    SELECT
        region,
        product_name,
        SUM(revenue) as total_revenue,
        COUNT(*) as order_count
    FROM all_regions
    GROUP BY region, product_name
    ORDER BY region, total_revenue DESC
""").df()
```

## Pre-Join Validation

Always verify common columns before joining:

```python
import duckdb

# Check column names in both files
cols_sales = duckdb.sql("""
    SELECT column_name FROM (DESCRIBE SELECT * FROM read_csv_auto('/home/daytona/sales.csv'))
""").df()

cols_products = duckdb.sql("""
    SELECT column_name FROM (DESCRIBE SELECT * FROM read_csv_auto('/home/daytona/products.csv'))
""").df()

print("Sales columns:", list(cols_sales['column_name']))
print("Products columns:", list(cols_products['column_name']))

# Find common columns
common = set(cols_sales['column_name']) & set(cols_products['column_name'])
print(f"Common columns (potential join keys): {common}")
```

## Cleanup

Track created CSV files during conversion, then remove them after analysis:

```python
import os

# Use the csv_files dict from conversion step (tracks all created CSVs)
for name, path in csv_files.items():
    if os.path.exists(path):
        os.remove(path)
        print(f"Cleaned: {path}")

# Also clean any temp_ prefixed files from large_files workflow
for f in os.listdir('/home/daytona/'):
    if f.startswith('temp_') and f.endswith('.csv'):
        full = f'/home/daytona/{f}'
        os.remove(full)
        print(f"Cleaned: {full}")
```
