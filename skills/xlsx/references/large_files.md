# Large Excel File Handling (>40MB)

This reference is loaded when the user uploads a large Excel file (>40MB) or mentions keywords like "large file", "million rows", "out of memory", "duckdb".

⚠️ **Eşik: 40MB.** `file_size_mb >= 40` ise DuckDB stratejisi kullan. `< 40` ise pandas yeterli.

## Strategy: Excel → CSV → DuckDB

DuckDB cannot read `.xlsx` files directly. The workflow is:
1. Convert Excel to CSV using pandas (one-time cost)
2. Use DuckDB `read_csv_auto()` for lazy SQL queries (no full memory load)
3. Only the final aggregated result is loaded to pandas

### Step 1: File Size Detection

```python
import os

file_path = '/home/daytona/data.xlsx'
file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
print(f"File size: {file_size_mb:.1f} MB")

if file_size_mb < 40:
    strategy = "pandas"
elif file_size_mb < 500:
    strategy = "duckdb"
else:
    strategy = "chunked"

print(f"Strategy: {strategy}")
```

### Step 2: Excel → CSV Conversion (Tek veya Çok Sayfalı — OTOMATİK)

⚠️ **ASLA `pd.read_excel(path)` ile direkt okuma** — bu sadece ilk sheet'i alır.
Her zaman sheet sayısını önce kontrol et:

```python
import pandas as pd
import os
import re
import unicodedata

def safe_filename(name):
    tr_map = str.maketrans('ıİ', 'iI')
    name = name.translate(tr_map)
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_name = nfkd.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', '_', ascii_name.lower()).strip('_')

file_path = '/home/daytona/data.xlsx'
xls = pd.ExcelFile(file_path)
sheet_names = xls.sheet_names
print(f"Sheet sayısı: {len(sheet_names)} → {sheet_names}")

csv_paths = {}  # sheet_name → csv_path eşlemesi
for sheet in sheet_names:
    df = pd.read_excel(file_path, sheet_name=sheet)
    safe_name = safe_filename(sheet)
    csv_path = f'/home/daytona/temp_{safe_name}.csv'
    df.to_csv(csv_path, index=False)
    csv_paths[sheet] = csv_path
    print(f"  '{sheet}': {len(df):,} satır → {csv_path}")
    del df

print(f"✅ Dönüşüm tamamlandı: {csv_paths}")
```

### Step 3: Çok Sayfalı DuckDB Analizi

Sheet schema'larını karşılaştırarak strateji seç:

**Aynı kolonlar (dönemsel sheet'ler: Ocak/Şubat/Mart) → UNION ALL:**
```python
import duckdb

# Tüm sheet'leri birleştir, kaynak sheet'i de ekle
union_query = " UNION ALL ".join(
    f"SELECT *, '{sheet}' as sheet_name FROM read_csv_auto('{path}')"
    for sheet, path in csv_paths.items()
)
all_data = duckdb.sql(union_query).df()
print(f"Birleşik veri: {len(all_data):,} satır, {all_data['sheet_name'].nunique()} sheet")
```

**Farklı kolonlar, ilişkili sheet'ler (Siparisler + Musteriler) → JOIN:**
```python
result = duckdb.sql(f"""
    SELECT s.Invoice, s.Quantity * s.Price as revenue, m.Country
    FROM read_csv_auto('{csv_paths["Siparisler"]}') s
    JOIN read_csv_auto('{csv_paths["Musteriler"]}') m
        ON s.\"Customer ID\" = m.\"Customer ID\"
""").df()
```

**Bağımsız sheet'ler (her biri ayrı konu) → ayrı sorgular:**
```python
for sheet, csv_path in csv_paths.items():
    summary = duckdb.sql(f"""
        SELECT COUNT(*) as rows FROM read_csv_auto('{csv_path}')
    """).fetchone()
    print(f"  {sheet}: {summary[0]:,} satır")
```

### Step 4: DuckDB Lazy Queries

```python
import duckdb

# Basic aggregation — DuckDB reads CSV lazily (no full memory load)
result = duckdb.sql("""
    SELECT
        product_name,
        SUM(quantity) as total_quantity,
        SUM(revenue) as total_revenue,
        AVG(revenue) as avg_revenue,
        COUNT(*) as row_count
    FROM read_csv_auto('/home/daytona/temp_data.csv')
    GROUP BY product_name
    ORDER BY total_revenue DESC
    LIMIT 20
""").df()

print(result)
```

## Common DuckDB Query Patterns

### Filtering

```python
result = duckdb.sql("""
    SELECT *
    FROM read_csv_auto('/home/daytona/temp_data.csv')
    WHERE revenue > 1000
      AND date >= '2024-01-01'
    ORDER BY revenue DESC
    LIMIT 100
""").df()
```

### Group-By with Multiple Aggregates

```python
result = duckdb.sql("""
    SELECT
        category,
        region,
        COUNT(*) as order_count,
        SUM(revenue) as total_revenue,
        AVG(revenue) as avg_revenue,
        MIN(revenue) as min_revenue,
        MAX(revenue) as max_revenue
    FROM read_csv_auto('/home/daytona/temp_data.csv')
    GROUP BY category, region
    ORDER BY total_revenue DESC
""").df()
```

### Window Functions

```python
result = duckdb.sql("""
    SELECT
        product_name,
        date,
        revenue,
        SUM(revenue) OVER (PARTITION BY product_name ORDER BY date) as cumulative_revenue,
        ROW_NUMBER() OVER (PARTITION BY product_name ORDER BY revenue DESC) as rank
    FROM read_csv_auto('/home/daytona/temp_data.csv')
""").df()
```

### Date-Based Aggregation

```python
result = duckdb.sql("""
    SELECT
        DATE_TRUNC('month', CAST(date AS DATE)) as month,
        SUM(revenue) as monthly_revenue,
        COUNT(*) as order_count
    FROM read_csv_auto('/home/daytona/temp_data.csv')
    GROUP BY 1
    ORDER BY 1
""").df()
```

### Percentile and Distribution

```python
result = duckdb.sql("""
    SELECT
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY revenue) as p25,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY revenue) as median,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY revenue) as p75,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY revenue) as p95,
        AVG(revenue) as mean,
        STDDEV(revenue) as std_dev
    FROM read_csv_auto('/home/daytona/temp_data.csv')
""").df()
```

### Top-N per Group

```python
result = duckdb.sql("""
    WITH ranked AS (
        SELECT
            category,
            product_name,
            SUM(revenue) as total_revenue,
            ROW_NUMBER() OVER (PARTITION BY category ORDER BY SUM(revenue) DESC) as rn
        FROM read_csv_auto('/home/daytona/temp_data.csv')
        GROUP BY category, product_name
    )
    SELECT category, product_name, total_revenue
    FROM ranked
    WHERE rn <= 5
    ORDER BY category, total_revenue DESC
""").df()
```

## Chunked Processing for Very Large Files (>500MB)

When even DuckDB conversion is too large for a single `pd.read_excel()` (>500MB):

```python
import pandas as pd
import duckdb

file_path = '/home/daytona/huge.xlsx'
chunk_size = 50000  # rows per chunk
csv_path = '/home/daytona/temp_chunked.csv'

# Read and write in chunks
header_written = False
for chunk in pd.read_excel(file_path, chunksize=chunk_size):
    chunk.to_csv(csv_path, mode='a', index=False, header=not header_written)
    header_written = True
    print(f"  Processed {chunk_size} rows...")

print("Conversion complete. Running DuckDB query...")

result = duckdb.sql(f"""
    SELECT
        category,
        SUM(revenue) as total_revenue,
        COUNT(*) as count
    FROM read_csv_auto('{csv_path}')
    GROUP BY category
    ORDER BY total_revenue DESC
""").df()

print(result)
```

## Performance Targets

| Rows | File Size | Strategy | Expected Time | Memory Usage |
|------|-----------|----------|---------------|--------------|
| 100k | ~40 MB | DuckDB | 10-20 sec | ~200 MB |
| 500k | ~200 MB | DuckDB | 20-40 sec | ~200 MB |
| 1M | ~400 MB | DuckDB | 40-90 sec | ~300 MB |
| 5M | ~2 GB | Chunked + DuckDB | 3-8 min | ~500 MB |

Key insight: DuckDB's `read_csv_auto()` uses **lazy loading** — it doesn't load the full file into memory. Only the result set is materialized.

## Memory-Efficient Patterns

### DO: Use DuckDB for Aggregation

```python
# GOOD — only result loaded to memory
result = duckdb.sql("""
    SELECT category, SUM(revenue)
    FROM read_csv_auto('/home/daytona/temp.csv')
    GROUP BY category
""").df()  # Small result: ~100 rows
```

### DON'T: Load Full DataFrame

```python
# BAD — loads 1M+ rows into memory
df = pd.read_excel('/home/daytona/huge.xlsx')  # 10GB memory!
result = df.groupby('category')['revenue'].sum()
```

### DO: Sample for Exploration

```python
# Quick look at data structure
sample = duckdb.sql("""
    SELECT * FROM read_csv_auto('/home/daytona/temp.csv') LIMIT 100
""").df()
print(sample.dtypes)
print(sample.head())
```

### DO: Count Before Full Query

```python
# Check row count first
count = duckdb.sql("""
    SELECT COUNT(*) as total_rows
    FROM read_csv_auto('/home/daytona/temp.csv')
""").fetchone()[0]
print(f"Total rows: {count:,}")
```

## Süreç Kuralları

### Metrik hesaplama ve PDF aynı execute'da olmalı

DuckDB workflow'unda execute sayısını minimize et. Önceki execute çıktısından sayı **KOPYALAMA**:

```python
# ❌ YANLIŞ — execute 5 çıktısından alınan hardcoded sayılar:
m = {'total_customers': 4383, 'total_revenue': 8348208.57, 'uk_avg': 1744.37}

# ✅ DOĞRU — PDF execute'unda DuckDB sorgularını yeniden çalıştır:
general = duckdb.sql("""
    SELECT COUNT(DISTINCT customer_id), SUM(revenue)
    FROM read_csv_auto('/home/daytona/temp_data.csv')
""").fetchone()
m = {'total_customers': int(general[0]), 'total_revenue': float(general[1])}
```

**Optimal execute yapısı (DuckDB):**
```
Execute 1: file size check + nrows=5 schema
Execute 2: Excel → CSV dönüşümü
Execute 3: DuckDB tüm analizler + m dict + HTML + WeasyPrint PDF
```
Analiz sorguları ve PDF üretimi **tek bir execute** içinde tamamlanmalı.

## Cleanup

After analysis, remove temporary CSV files:

```python
import os
for f in ['/home/daytona/temp_data.csv', '/home/daytona/temp_chunked.csv']:
    if os.path.exists(f):
        os.remove(f)
        print(f"Cleaned up: {f}")
```
