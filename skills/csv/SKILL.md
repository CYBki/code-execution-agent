---
name: csv
description: "Use when working with .csv, .tsv files, comma-separated data, tab-separated data, large CSV files, or when user mentions DuckDB or lazy SQL queries"
---

# CSV Processing Expertise

You are an expert at working with CSV/TSV files efficiently.

## Analiz İş Akışı

```
1. KEŞİF    → parse_file(dosya)  ← execute HARCAMAZ, her zaman İLK ADIM
2. TEMİZLEME → execute(oku + temizle + df.to_pickle('/home/daytona/clean_data.pkl'))
3. ANALİZ   → execute(pd.read_pickle + analiz + doğrulama)
4. RAPOR    → execute(pickle + metrics dict + weasyprint PDF) → generate_html → download_file
```

## Pickle İş Akışı

CSV'yi her execute'da tekrar okuma — ilk execute'da pickle'a kaydet:

```python
# Execute 1: Oku + kaydet
df = pd.read_csv('/home/daytona/data.csv')
df.to_pickle('/home/daytona/clean_data.pkl')
print(f'✅ Kaydedildi: {len(df):,} satır')

# Execute 2+: Pickle'dan oku (10x daha hızlı)
df = pd.read_pickle('/home/daytona/clean_data.pkl')
```

## Süreç Kuralları

- Tüm veriyi işle — `.head(1000)` veya `nrows=50000` YASAK (schema için `nrows=5` hariç)
- Her kritik metrik için: `assert not pd.isna(x) and x > 0` + print
- Doğrulama analiz execute'unun SONUNA: `print('✅ Doğrulama OK')`
- Script içinde try/except — ayrı execute YAPMA

## Basic CSV Reading

```python
import pandas as pd

# Standard CSV
df = pd.read_csv('/home/daytona/data.csv')
print(f"Shape: {df.shape}")
print(df.head())

# TSV (tab-separated)
df = pd.read_csv('/home/daytona/data.tsv', sep='\t')

# Custom separator
df = pd.read_csv('/home/daytona/data.txt', sep='|')

# Handle encoding issues
df = pd.read_csv('/home/daytona/data.csv', encoding='utf-8-sig')  # BOM-aware
df = pd.read_csv('/home/daytona/data.csv', encoding='latin-1')    # Western European
```

## File Size Detection

```python
import os

file_path = '/home/daytona/data.csv'
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
    FROM read_csv_auto('/home/daytona/data.csv')
    GROUP BY category
    ORDER BY total_revenue DESC
""").df()

print(result)
```

### Quick Row Count

```python
import duckdb

count = duckdb.sql("""
    SELECT COUNT(*) FROM read_csv_auto('/home/daytona/data.csv')
""").fetchone()[0]
print(f"Total rows: {count:,}")
```

### Sample Data

```python
import duckdb

sample = duckdb.sql("""
    SELECT * FROM read_csv_auto('/home/daytona/data.csv') LIMIT 100
""").df()
print(sample.dtypes)
print(sample.head())
```

## Common CSV Options

```python
import pandas as pd

# Skip rows, custom header
df = pd.read_csv('/home/daytona/data.csv', skiprows=3, header=0)

# No header — assign column names
df = pd.read_csv('/home/daytona/data.csv', header=None, names=['A', 'B', 'C'])

# Parse dates during read
df = pd.read_csv('/home/daytona/data.csv', parse_dates=['date', 'created_at'])

# Force column types
df = pd.read_csv('/home/daytona/data.csv', dtype={'zip_code': str, 'id': str})

# Handle missing values
df = pd.read_csv('/home/daytona/data.csv', na_values=['N/A', 'null', '-', ''])

# Only read specific columns
df = pd.read_csv('/home/daytona/data.csv', usecols=['name', 'revenue', 'date'])

# Read first N rows only (for preview)
df = pd.read_csv('/home/daytona/data.csv', nrows=1000)
```

## Writing CSV

```python
# Standard write
df.to_csv('/home/daytona/output.csv', index=False)

# Custom separator
df.to_csv('/home/daytona/output.tsv', sep='\t', index=False)

# Excel-compatible (BOM for UTF-8)
df.to_csv('/home/daytona/output.csv', index=False, encoding='utf-8-sig')
```

## Common Pitfalls

- [ ] **Encoding**: Try `utf-8`, `utf-8-sig`, `latin-1`, `cp1252` if garbled text appears
- [ ] **Separator detection**: Check if file uses `,`, `\t`, `;`, or `|` as delimiter
- [ ] **Quoting**: Use `quoting=csv.QUOTE_ALL` if fields contain the separator character
- [ ] **Large files**: Always check `os.path.getsize()` first — use DuckDB if >50MB
- [ ] **Mixed types**: Use `dtype=str` to prevent pandas from guessing wrong types
- [ ] **Leading zeros**: Read ID/zip columns as `dtype=str` to preserve leading zeros
