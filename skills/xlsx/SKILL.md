---
name: xlsx
description: "Use when working with .xlsx, .xls, Excel files, spreadsheets, workbooks, or when user mentions formulas, cells, sheets, pivot tables, financial data, merged cells, or named ranges"
---

# Excel/XLSX Expertise

You are an expert Excel analyst. Follow these instructions precisely when working with Excel files.

## Analiz İş Akışı (ReAct Döngüsü)

Sabit faz sırası yok — kullanıcı sorgusuna göre adapte et. Tipik sıra:

```
1. KEŞİF
   DÜŞÜNCE: "Dosya yüklendi, yapısını anlamalıyım. ls/os.listdir DEĞİL, parse_file."
   → parse_file(dosya)   ← execute HARCAMAZ, her zaman İLK ADIM
   GÖZLEM: [kolonlar, tipler, preview, satır sayısı]
   KARAR: Schema gördüm → temizle + pickle'a kaydet.

2. TEMİZLEME + PICKLE
   DÜŞÜNCE: [Hangi kolonlar lazım, null durumu, tip dönüşümleri]
   → execute(oku + temizle + df.to_pickle('/home/daytona/clean_data.pkl'))
   GÖZLEM: [satır sayısı, temizleme özeti, ✅ Doğrulama OK]
   KARAR: Temiz mi? Evet → analiz. Hayır → DÜZELTME DÖNGÜSÜ.

3. ANALİZ (pickle'dan oku — Excel'den tekrar okuma)
   DÜŞÜNCE: [Kullanıcı ne soruyor, hangi hesaplamalar gerekli]
   → execute(pd.read_pickle + analiz + doğrulama bloğu)
   GÖZLEM: [sonuçlar + ✅ Doğrulama OK]
   KARAR: Doğrulama geçti mi? Evet → rapora geç. Hayır → DÜZELTME DÖNGÜSÜ.

4. RAPOR (analiz + PDF tek script)
   DÜŞÜNCE: [Hangi metrikleri rapora koyacağım]
   → execute(pickle'dan oku + metrics dict + weasyprint PDF + doğrula)
   → generate_html(dashboard)
   → download_file(PDF)
   → Kullanıcıya KISA özet (genel bulgular — spesifik sayı/oran KULLANMA)
```

## Pickle İş Akışı

Excel/CSV dosyalarını her execute'da tekrar okuma — çok yavaş. İlk execute'da kaydet:

```python
# Execute 1: Oku + temizle + kaydet
df = pd.read_excel('/home/daytona/dosya.xlsx')
df = df.dropna(subset=['key_col'])
df['Date'] = pd.to_datetime(df['Date'])
df.to_pickle('/home/daytona/clean_data.pkl')
print(f'✅ Kaydedildi: {len(df):,} satır')

# Execute 2+: Pickle'dan oku (10x daha hızlı)
df = pd.read_pickle('/home/daytona/clean_data.pkl')
```

## Analiz Stratejisi

1. **Schema'yı oku** → hangi kolonlar var, tipleri ne?
2. **Kullanıcı ne istiyor?** → sorguyu analiz et
3. **Hangi analizler mümkün?** → mevcut kolonlara göre karar ver
4. **Yapılamayan analizi atla** → eksik kolon varsa o analizi yapma, kullanıcıya bildir

## Yaygın Hatalar

- **Ortalama hesabı**: Satır ortalaması mı, grup ortalaması mı? Bağlama göre karar ver.
  Sipariş değeri → `df.groupby('order_id')['amount'].sum().mean()` ✅  Satır bazlı mean ❌
- **Negatif değerler**: Silme — önce anla. İade mi? Borç mu? Brüt/net ayrımı yap.
- **Unique sayma**: `.nunique()` kullan, `len()` veya `count()` değil.
- **Büyük kombinasyonlar**: Ürün çifti analizi → önce popüler öğeleri filtrele:
  `popular = df.groupby('col').size().pipe(lambda s: s[s > 50].index)`

## Analiz Kalitesi

### Sonuçları Doğrula
Kategorik değer çıkardıysan en sık 10 sonuca bak — gerçekten o kategoriyi temsil ediyor mu?
```python
print(df['extracted_col'].value_counts().head(10))
# Anlamsız çıktı varsa algoritmayı düzelt, rapora koyma
```
Bilinmeyen/fallback oranı %20'yi aşıyorsa: algoritmayı genişlet.

### Skor/Index — Normalize Et
```python
# ❌ YANLIŞ: score = col_a * 0.4 + col_b * 0.4  (ölçekler farklı → anlamsız)
# ✅ DOĞRU:
df['norm_a'] = (df['a'] - df['a'].min()) / (df['a'].max() - df['a'].min())
df['norm_b'] = (df['b'] - df['b'].min()) / (df['b'].max() - df['b'].min())
df['score'] = df['norm_a'] * 0.5 + df['norm_b'] * 0.5
```

### Önerileri Veriden Türet
Her öneri SOMUT sayı içermeli — generic cümle YASAK.
- ❌ "Bütçeyi artırın"
- ✅ "A grubu ort. değer 127 ama performans 8.3 — %20 artışla hala üst segmentte kalır"

### Analiz Sınırlarını Bildir
Raporun sonunda: hangi varsayımlar yapıldı, hangi temizleme adımları sonuçları etkileyebilir.

## Süreç Kuralları

### Tüm veriyi işle
`.head(1000)`, `[:5000]`, `nrows=50000`, `nrows=5` → **YASAK**.
`parse_file` schema'yı zaten veriyor — `nrows` ile tekrar okuma yapma.
Sonuç gösteriminde `.head(10)`, `.most_common(20)` serbest.

### Doğrulama (execute kodunun İÇİNDE yap)
Ayrı execute harcama — analiz kodunun SONUNA ekle:
```python
# === DOĞRULAMA ===
assert len(df) > 0, 'DataFrame boş!'
assert metric > 0, f'Metrik negatif/sıfır: {metric}'
print(f'Null: {df.isnull().sum().sum()}')
print('✅ Doğrulama OK')
```
"✅ Doğrulama OK" görmezsen → rapora KOYMA, önce düzelt.

### Formülleri göster
Her türetilmiş metrik için bileşenleri print et:
`print(f'AOV = {toplam:,.0f} / {siparis_sayisi:,} = {aov:.2f}')`

### Hata yönetimi
Script içinde try/except ile yakala — ayrı execute YAPMA.
Execute bloklandıysa: hata mesajını oku, sadece sorunlu kısmı değiştir.

### Dosya doğrulama
```python
assert os.path.exists(output_path), f'File not created: {output_path}'
print(f'OK: {output_path} ({os.path.getsize(output_path)/1024:.1f} KB)')
```

### Metrik hesaplama ve PDF aynı execute'da olmalı
Önceki execute'dan gelen sayıları `m = {'total': 1234, ...}` şeklinde ASLA elle yazma.
Her metrik, **kodla hesaplanmalı** — pickle veya CSV'den okuyarak.
```python
# ❌ YANLIŞ — önceki execute çıktısından kopyalanan hardcoded sayılar:
m = {'total_customers': 4383, 'total_revenue': 8348208.57}

# ✅ DOĞRU — aynı execute içinde hesapla:
df = pd.read_pickle('/home/daytona/clean_data.pkl')
m = {
    'total_customers': df['Customer ID'].nunique(),
    'total_revenue': (df['Quantity'] * df['Price']).sum(),
}
```
Analiz pickle'dan, tablo verileri ve PDF üretimi **tek bir execute** içinde tamamlanmalı.

### SELF-CHECK: Artifact Generation Öncesi Kontrol (MANDATORY)

⚠️ **Before EVERY `generate_html()` or WeasyPrint PDF call, verify variable scope:**

```
DUSUNCE: [Pre-flight check before artifact generation]
[ ] m dict bu execute'da hesaplandi mi? (Onceki execute'da ise UNDEFINED)
[ ] Chart data arrays (monthly_labels, revenues, etc.) bu scope'da mi?
[ ] DataFrame'ler (top_products, top_customers) bu execute'da mi?
[ ] Hepsi OK ise -> artifact generation yap
[ ] Herhangi biri eksikse -> hesaplamayi bu execute'a tasi
```

**Real example of the bug:**
```
# Execute #4
m = {'total_orders': 36969, ...}  # Calculated here
print('Metrics ready')

# Execute #5 (WRONG - NEW subprocess!)
html = f"<h3>{m['total_orders']}</h3>"  # m undefined -> empty KPI cards
generate_html(html_code=html)
```

**Fixed version:**
```
# CORRECT: Single execute - calculation + HTML together
df = pd.read_pickle('/home/daytona/clean.pkl')
m = {'total_orders': df['Invoice'].nunique(), ...}
monthly_data = df.groupby('month')['revenue'].sum().tolist()

html = f'''
<h3>{m['total_orders']:,}</h3>  <!-- m is defined -->
<script>const data = {monthly_data};</script>  <!-- monthly_data defined -->
'''
generate_html(html_code=html)
```

**If user reports empty dashboard/PDF:**
1. Immediately recognize: "Execute isolation violation"
2. Regenerate with single execute pattern
3. DO NOT wait for user to explain — catch this yourself

## Quick Start

### Reading Excel Files — Önce Sheet Sayısını Kontrol Et

⚠️ **`pd.read_excel(path)` direkt KULLANMA** — sadece ilk sheet'i alır.
Her zaman önce sheet listesini kontrol et:

```python
import pandas as pd

file_path = '/home/daytona/data.xlsx'
xls = pd.ExcelFile(file_path)
sheet_names = xls.sheet_names
print(f"Sheet sayısı: {len(sheet_names)} → {sheet_names}")

if len(sheet_names) == 1:
    # Tek sayfa — direkt oku
    df = pd.read_excel(file_path)
    print(f"Tek sheet: {df.shape}")
else:
    # Çok sayfa — tüm sheet'leri dict'e yükle
    all_sheets = pd.read_excel(file_path, sheet_name=None)
    for name, sheet_df in all_sheets.items():
        print(f"  '{name}': {sheet_df.shape[0]:,} satır x {sheet_df.shape[1]} kolon")
        print(f"    Kolonlar: {list(sheet_df.columns)}")
```

**Çok sayfalı analiz stratejileri (pandas, <40MB):**
```python
# Aynı kolonlar (dönemsel: Ocak/Şubat/Mart) → birleştir
df_combined = pd.concat(
    [sheet_df.assign(sheet=name) for name, sheet_df in all_sheets.items()],
    ignore_index=True
)
print(f"Birleşik: {len(df_combined):,} satır")

# Farklı konular (Siparisler + Musteriler) → merge
df_orders = all_sheets['Siparisler']
df_customers = all_sheets['Musteriler']
df_merged = df_orders.merge(df_customers, on='Customer ID', how='left')

# Bağımsız sheet'ler → ayrı analiz
for name, sheet_df in all_sheets.items():
    print(f"{name}: {sheet_df.describe()}")
```

### File Size Detection — ALWAYS DO THIS FIRST

```python
import os

file_path = '/home/daytona/data.xlsx'
file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
print(f"File size: {file_size_mb:.1f} MB")

if file_size_mb < 40:
    print("Strategy: Direct pandas load")
    # Sheet detection yukarıdaki pattern ile yap
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

→ Bkz. **Quick Start → Reading Excel Files** bölümü: sheet tespiti ve analiz stratejileri orada.

**Özet:**
- Her zaman `pd.ExcelFile(path).sheet_names` ile başla
- Tek sheet: `pd.read_excel(path)` ✔️
- Çok sheet: `pd.read_excel(path, sheet_name=None)` → dict
- Aynı kolonlar → `pd.concat(... assign(sheet=name))`
- Farklı konular → `merge(on='ortak_kolon')`
- ≥40MB → CSV dönüşümü + DuckDB (bkz. references/large_files.md)

## Rapor Başlıklı Excel Format Sorunları (Header-Offset)

Otomatik üretilen Excel raporlarında (Logo, VMS, SAP, Netsis vb.) ilk birkaç satır rapor meta bilgisi içerir.
Gerçek kolon başlıkları 3-5. satırda başlar.

**Gerçek pivot tablo** (pd.pivot_table çıktısı) ile karıştırma — bu farklı bir sorundur:
```
Satır 1: "Malzeme Stok Raporu - 01.03.2025"   ← rapor adı (meta)
Satır 2: "Dönem: Ocak-Mart 2025"               ← meta bilgi
Satır 3: "Hazırlayan: Muhasebe"                ← meta bilgi
Satır 4: (boş)
Satır 5: malzeme_kodu | malzeme_adi | miktar   ← GERÇEK başlık
Satır 6: 10001        | Vida M6     | 500       ← veri başlangıcı
```

Otomatik üretilen Excel raporlarında (Logo, VMS, SAP vb.) ilk satır genellikle gerçek veri başlığı değildir.
`parse_file` schema'sına baktıktan sonra kolon adlarını kontrol et:

**Şüpheli durumlar — `parse_file` sonrası kontrol et:**
- Kolon adı `Unnamed: 0`, `Unnamed: 1` → başlık satırı yanlış satırda
- Kolon adı `Rapor:`, `Tarih:`, `Dönem:` gibi bir etiket → üst başlık satırı var, `skiprows` gerekli
- İlk 1-3 satır boş veya meta bilgisi → `skiprows=N` ile atla

```python
# Tespit: hangi satırda gerçek kolon adları var?
df_check = pd.read_excel(file_path, nrows=10, header=None)
for i, row in df_check.iterrows():
    non_null = row.dropna()
    print(f"Satır {i}: {list(non_null.values)[:6]}")
# → Kolon adlarının (malzeme_kodu, miktar vb.) hangi satırda göründüğünü bul
```

```python
# Durum 1: İlk satır rapor başlığı, 2. satır kolon adları
df = pd.read_excel(file_path, skiprows=1)

# Durum 2: İlk N satır meta bilgi
df = pd.read_excel(file_path, header=2)  # 3. satır (0-indexed) kolon adı

# Durum 3: Kolon adı hiç yok → manuel tanımla
df = pd.read_excel(file_path, header=None,
                   names=['malzeme_kodu', 'malzeme_adi', 'miktar', 'birim'])

# Durum 4: Kolon adları doğru ama fazladan alt başlık satırı var (pivot)
df = pd.read_excel(file_path, skiprows=1)
df = df.dropna(how='all')          # Tamamen boş satırları at
df = df[df.iloc[:, 0].notna()]     # İlk kolon boş olan satırları at
```

**Kolon adları hâlâ bozuksa:**
```python
# Mevcut kolon adlarını düzelt
df.columns = df.columns.str.strip()               # Baştaki/sondaki boşlukları temizle
df.columns = df.columns.str.replace('\n', ' ')    # Satır sonu karakterleri
df = df.rename(columns={
    'Malzeme\nKodu': 'malzeme_kodu',
    'Unnamed: 2':    'miktar',
})
```

## PDF Rapor Üretimi — WeasyPrint

PDF için her zaman `weasyprint` kullan (`fpdf2` değil — Türkçe karakter sorunları).
**Metrik hesaplama ve PDF üretimi aynı execute'da olmalı.**

```python
import weasyprint
import os

# m dict — pickle veya DuckDB'den hesapla (hardcode YASAK)
df = pd.read_pickle('/home/daytona/clean_data.pkl')
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
<h1>Analiz Raporu</h1>
<p><strong>Tarih:</strong> {m["analysis_date"]}</p>
<div class="metric">Toplam: <span class="value">{m["total"]:,}</span></div>
<div class="metric">Gelir: <span class="value">${m["revenue"]:,.2f}</span></div>
</body></html>'''

html_path = '/home/daytona/temp_report.html'
pdf_path  = '/home/daytona/rapor.pdf'
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

weasyprint.HTML(filename=html_path).write_pdf(pdf_path)
assert os.path.exists(pdf_path), f'PDF oluşturulamadı'
print(f'✅ PDF: {os.path.getsize(pdf_path)//1024} KB')
os.remove(html_path)
```

**Tablo döngüsü (DataFrame → HTML tablo):**
```python
rows_html = ''
for _, row in top_df.iterrows():
    rows_html += f'<tr><td>{row["id"]}</td><td>{row["value"]:,.2f}</td></tr>\n'

html_table = f'''<table>
<tr><th>ID</th><th>Değer</th></tr>
{rows_html}
</table>'''
```

**Tarih formatlama — datetime objesinde `[:10]` ÇALIŞMAZ:**
```python
# ❌ Hatalı
date_str = row['InvoiceDate'][:10]

# ✅ Doğru
date_str = pd.to_datetime(row['InvoiceDate']).strftime('%Y-%m-%d')

# ✅ DuckDB'den direkt string olarak çek (daha güvenli)
# SELECT CAST(MIN(InvoiceDate) AS VARCHAR)[:10] as first_order
```

## Merged Cells Handling

Excel merged cells appear as NaN in non-first rows. Always forward-fill:

```python
df = pd.read_excel('/home/daytona/data.xlsx')

# Forward fill merged cell values
df = df.ffill()

# Or fill specific columns only
df['Category'] = df['Category'].ffill()
```

### Detecting Merged Cells with openpyxl

```python
from openpyxl import load_workbook

wb = load_workbook('/home/daytona/data.xlsx')
ws = wb.active

# List all merged cell ranges
for merged_range in ws.merged_cells.ranges:
    print(f"Merged: {merged_range}")
```

## Data Type Handling

```python
# Force column types during read
df = pd.read_excel('/home/daytona/data.xlsx', dtype={
    'ID': str,           # Prevent leading zero loss
    'ZipCode': str,      # Keep as text
    'Amount': float,
})

# Date parsing
df = pd.read_excel('/home/daytona/data.xlsx', parse_dates=['Date', 'Created'])

# Handle mixed types
df['Price'] = pd.to_numeric(df['Price'], errors='coerce')  # Non-numeric → NaN
```

## Common Analysis Patterns

### Exploratory Data Analysis (EDA)

```python
import pandas as pd

df = pd.read_excel('/home/daytona/data.xlsx')

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

wb = load_workbook('/home/daytona/output.xlsx')
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
df.to_excel('/home/daytona/output.xlsx', index=False, sheet_name='Results')

# Write multiple sheets
with pd.ExcelWriter('/home/daytona/output.xlsx', engine='openpyxl') as writer:
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

wb.save('/home/daytona/output.xlsx')
print("✅ Styled Excel file saved")
```

## Named Ranges

```python
from openpyxl import load_workbook

wb = load_workbook('/home/daytona/data.xlsx')

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
