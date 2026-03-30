# Technical Guide — Agentic Analyze

Bu doküman sistemin iç çalışma mekanizmalarını açıklar: veri aktarımı, büyük dosya işleme, PDF üretimi, interceptor kuralları, skill sistemi ve sandbox yaşam döngüsü.

---

## 1. Execute İzolasyonu — Neden Her Execute Ayrı?

Her `execute()` çağrısı Daytona sandbox'ta bağımsız bir Python subprocess açar:

```
Agent (LLM, tek process)
  │
  ├── execute() çağrısı #1 ──▶  python3 /tmp/_run_abc.py  (PID 1234, biter, ölür)
  ├── execute() çağrısı #2 ──▶  python3 /tmp/_run_def.py  (PID 5678, biter, ölür)
  └── execute() çağrısı #3 ──▶  python3 /tmp/_run_ghi.py  (PID 9012, biter, ölür)
```

**Sonuç:** Execute #1'de tanımlanan `df` değişkeni Execute #2'de yoktur.
Execute'lar arası veri aktarımı için **disk** kullanılır.

---

## 2. Pickle Pattern — Küçük/Orta Dosyalar (<40MB)

Pandas DataFrame'ini execute'lar arası taşımanın en hızlı yolu:

```python
# Execute 1: Temizle + Kaydet
import pandas as pd

df = pd.read_excel('/home/daytona/data.xlsx')
df.dropna(subset=['Customer ID'], inplace=True)
df['InvoiceDate'] = pd.to_datetime(df['InvoiceDate'])
df.to_pickle('/home/daytona/clean_data.pkl')
del df  # RAM'i serbest bırak
print(f"Kaydedildi: {pd.read_pickle('/home/daytona/clean_data.pkl').shape}")
```

```python
# Execute 2: Oku + Analiz Et + PDF
import pandas as pd

df = pd.read_pickle('/home/daytona/clean_data.pkl')

m = {
    'total_customers': df['Customer ID'].nunique(),
    'total_revenue':   (df['Quantity'] * df['Price']).sum(),
    'avg_orders':      df.groupby('Customer ID')['Invoice'].nunique().mean(),
}

# HTML + WeasyPrint PDF tek execute içinde
html = f"""<html>...<b>{m['total_customers']:,}</b>...</html>"""
import weasyprint
weasyprint.HTML(string=html).write_pdf('/home/daytona/rapor.pdf')
print(f"PDF: {__import__('os').path.getsize('/home/daytona/rapor.pdf')//1024} KB")
```

### Pickle vs CSV Karşılaştırması

| | Pickle | CSV |
|---|---|---|
| Okuma hızı | ~5x daha hızlı | Yavaş (parse gerekir) |
| Veri tipleri | datetime, category korunur | Hepsi string olur |
| DuckDB uyumu | ❌ DuckDB okuyamaz | ✅ `read_csv_auto()` |
| Kullanım | <40MB, pandas analizi | ≥40MB, DuckDB analizi |

---

## 3. Büyük Dosya Pattern — Excel → CSV → DuckDB (≥40MB)

40MB üzeri dosyalar için pandas direkt yükleme bellek sorununa yol açar.
Strateji: Excel → CSV dönüşümü (pandas ile), sonra DuckDB lazy query.

### Adım 1: Multi-Sheet CSV Dönüşümü

```python
# Execute 1: Tüm sheet'leri CSV'ye çevir
import pandas as pd
import os
import re
import unicodedata

def safe_filename(name):
    """Sheet adını dosya sistemi için güvenli hale getirir."""
    tr_map = str.maketrans('ıİçşüğ', 'iIcsug')
    name = name.translate(tr_map)
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_name = nfkd.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', '_', ascii_name.lower()).strip('_')

file_path = '/home/daytona/data.xlsx'

# Sheet tespiti — ASLA pd.read_excel(path) ile direkt okuma yapma
xls = pd.ExcelFile(file_path)
sheet_names = xls.sheet_names
print(f"Sheet sayısı: {len(sheet_names)} → {sheet_names}")

csv_paths = {}  # {sheet_name: csv_path}
for sheet in sheet_names:
    df = pd.read_excel(file_path, sheet_name=sheet)
    safe_name = safe_filename(sheet)
    csv_path = f'/home/daytona/temp_{safe_name}.csv'
    df.to_csv(csv_path, index=False)
    csv_paths[sheet] = csv_path
    print(f"  '{sheet}': {len(df):,} satır → {csv_path}")
    del df  # Her sheet sonrası RAM temizle

print(f"✅ csv_paths = {csv_paths}")
```

### Adım 2: DuckDB ile Analiz + PDF

```python
# Execute 2: DuckDB sorguları + m dict + PDF — HEPSİ TEK EXECUTE'DA
import duckdb
import weasyprint
import os
from datetime import datetime

# csv_paths'i yeniden tanımla (execute izolasyonu nedeniyle)
csv_paths = {
    'Year 2009-2010': '/home/daytona/temp_year_2009_2010.csv',
    'Year 2010-2011': '/home/daytona/temp_year_2010_2011.csv',
}

# UNION ALL — aynı kolonlu dönemsel sheet'ler
union_query = " UNION ALL ".join(
    f"SELECT *, '{sheet}' as period FROM read_csv_auto('{path}')"
    for sheet, path in csv_paths.items()
)

# Tüm metrikler tek seferde hesaplanır
stats = duckdb.sql(f"""
    WITH data AS ({union_query})
    SELECT
        COUNT(DISTINCT "Customer ID") as unique_customers,
        COUNT(DISTINCT Invoice)        as unique_invoices,
        SUM(Quantity * Price)          as total_revenue
    FROM data
    WHERE "Customer ID" IS NOT NULL
""").fetchone()

m = {
    'unique_customers': int(stats[0]),
    'unique_invoices':  int(stats[1]),
    'total_revenue':    float(stats[2]),
    'analysis_date':    datetime.now().strftime('%d.%m.%Y'),
}

# PDF — m dict referanslarıyla, hardcode yok
html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>body{{font-family:Arial;margin:40px}}</style></head><body>
<h1>Analiz Raporu</h1>
<p>Benzersiz Müşteri: <b>{m['unique_customers']:,}</b></p>
<p>Toplam Gelir: <b>${m['total_revenue']:,.2f}</b></p>
</body></html>"""

pdf_path = '/home/daytona/rapor.pdf'
weasyprint.HTML(string=html).write_pdf(pdf_path)
print(f"✅ PDF: {os.path.getsize(pdf_path)//1024} KB")

# Temp dosyaları temizle
for path in csv_paths.values():
    os.remove(path)
```

---

## 4. Multi-Sheet DuckDB Analiz Stratejileri

### Strateji 1: UNION ALL — Aynı Kolonlu Sheet'ler

**Ne zaman:** Dönemsel veriler (Ocak/Şubat, 2009-2010/2010-2011)

```python
union_query = " UNION ALL ".join(
    f"SELECT *, '{sheet}' as sheet_name FROM read_csv_auto('{path}')"
    for sheet, path in csv_paths.items()
)
result = duckdb.sql(f"SELECT COUNT(*) FROM ({union_query})").fetchone()
```

### Strateji 2: JOIN — İlişkili Sheet'ler

**Ne zaman:** Orders + Customers gibi yabancı anahtar ilişkisi olan tablolar

```python
result = duckdb.sql(f"""
    SELECT s.Invoice, s.Quantity * s.Price as revenue, m.Country
    FROM read_csv_auto('{csv_paths["Siparisler"]}') s
    JOIN read_csv_auto('{csv_paths["Musteriler"]}') m
        ON s."Customer ID" = m."Customer ID"
""").df()
```

### Strateji 3: Bağımsız Sorgular

**Ne zaman:** Her sheet farklı konu (Finansal + Operasyonel)

```python
for sheet, csv_path in csv_paths.items():
    summary = duckdb.sql(f"""
        SELECT COUNT(*) as rows, COUNT(DISTINCT id) as unique_ids
        FROM read_csv_auto('{csv_path}')
    """).fetchone()
    print(f"{sheet}: {summary[0]:,} satır")
```

**Schema tespiti için:**
- Aynı kolonlar mı? → UNION ALL
- Ortak anahtar kolon var mı? → JOIN
- Hiçbiri? → Bağımsız sorgular

---

## 5. PDF Üretimi — WeasyPrint

`fpdf2` yerine `weasyprint` tercih edilir çünkü:
- HTML/CSS desteği — tablo, renk, düzen çok daha kolay
- Türkçe karakter desteği (`<meta charset="UTF-8">` ile)
- f-string ile dinamik içerik yerleştirme

```python
import weasyprint
import os

html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<style>
  body     {{ font-family: Arial, sans-serif; margin: 40px; font-size: 13px; }}
  h1       {{ color: #1a365d; border-bottom: 3px solid #3182ce; }}
  h2       {{ color: #2c5282; border-left: 4px solid #3182ce; padding-left: 12px; }}
  .metric  {{ background: #ebf8ff; padding: 12px; margin: 8px 0; border-radius: 4px; }}
  .value   {{ font-weight: bold; color: #c53030; font-size: 15px; }}
  table    {{ width: 100%; border-collapse: collapse; }}
  th       {{ background: #2b6cb0; color: white; padding: 10px; }}
  td       {{ padding: 8px; border-bottom: 1px solid #e2e8f0; }}
  .insight {{ background: #f0fff4; border-left: 4px solid #38a169; padding: 12px; }}
</style>
</head><body>
<h1>Rapor Başlığı</h1>
<div class="metric">
  Müşteri Sayısı: <span class="value">{m['unique_customers']:,}</span>
</div>
</body></html>"""

# Dosyaya yaz ve PDF'e dönüştür
html_path = '/home/daytona/temp_report.html'
pdf_path  = '/home/daytona/rapor.pdf'

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

weasyprint.HTML(filename=html_path).write_pdf(pdf_path)

assert os.path.exists(pdf_path), "PDF oluşturulamadı"
print(f"✅ PDF: {os.path.getsize(pdf_path)//1024} KB")
os.remove(html_path)  # Temp temizle
```

**Önemli kurallar:**
- Tüm metrik hesaplamaları ve PDF üretimi **aynı execute** içinde olmalı
- `m = {...}` dict'i hesaplamadan HTML template'e yazmayın
- Hardcoded sayı **yasak** — her zaman `{m['key']}` kullanın

---

## 6. Sandbox Dosya Sistemi

```
/home/daytona/              ← Kalıcı sandbox disk (execute'lar arası yaşar)
├── data.xlsx               ← Kullanıcının yüklediği dosya
├── clean_data.pkl          ← Pickle (geçici, analiz sonrası silinebilir)
├── temp_sheet1.csv         ← DuckDB için CSV (analiz sonrası silinmeli)
├── temp_sheet2.csv         ← DuckDB için CSV
├── rapor.pdf               ← Çıktı PDF
├── DejaVuSans.ttf          ← Font (kalıcı, sandbox kurulumunda kopyalanır)
└── DejaVuSans-Bold.ttf     ← Font (kalıcı)

/tmp/                       ← Geçici (execute'lar arası yaşamaz)
└── _run_abc123.py          ← execute.py'nin oluşturduğu temp script
```

**Dosya yolu kuralı:** Her zaman tam path kullan — `'/home/daytona/dosya.csv'`

---

## 7. Smart Interceptor Kuralları

`graph.py`'deki `smart_interceptor` her tool çağrısını filtreler:

### Blok Kuralları (execute hakkı düşmez)

| Kural | Tetikleyen Pattern | Sebep |
|---|---|---|
| Shell komutları | `ls`, `find`, `cat`, `head`, `tail` | Dosya path zaten biliniyor |
| Filesystem | `os.listdir`, `os.scandir`, `glob.glob` | Parse_file schema verdi |
| pip install | `pip install` veya `subprocess` | Paketler pre-installed |
| Ağ isteği | `urllib`, `requests`, `wget`, `curl` | Sandbox dışarıya çıkamaz |
| nrows > 10 | `nrows=100`, `nrows=1000` | Tüm veri okunmalı |
| Schema re-check | `nrows=5`, `nrows=10` + parse_file çalıştıysa | Schema zaten var |
| Duplicate parse_file | Aynı dosya ikinci kez (path normalized) | Gereksiz |
| Execute limiti | 6. veya 10. execute'dan sonra | Bütçe aşıldı |
| **Circuit breaker** | **2 ardışık blok** | **Sonsuz döngü önleme** |

**Path Normalization:** Duplicate parse_file tespitinde `/home/daytona/file.xlsx` ve `file.xlsx` aynı kabul edilir (prefix strip).

**Circuit Breaker:** Agent 2 kez üst üste bloklanırsa (örn: parse_file→ls→parse_file) üçüncü tool çağrısı STOP mesajı döner, zorunlu hata.

### Auto-Fix Kuralları (execute değiştirilir, çalışır)

| Kural | Tetikleyen | Düzeltme |
|---|---|---|
| Font fix | `Arial`, `Helvetica` in PDF kod | `DejaVuSans` ile değiştir |
| add_font inject | FPDF kodu ama `add_font()` yok | `add_font()` satırı ekle |

### Execute Limiti

```python
# Sorgu karmaşıklığına göre dinamik limit
_compute_max_execute(query):
    if "pdf" veya "rapor" in query:   → 6
    if "detaylı" veya "karşılaştır":  → 8
    if "istatistik" veya "analiz":    → 10
```

---

## 8. Dosya Boyutu Karar Ağacı

```
parse_file() çalışır
       │
       ▼
  file_size_mb?
       │
   ┌───┴───┐
  <40MB  ≥40MB
   │       │
   ▼       ▼
pandas  DuckDB
   │       │
   ▼       ▼
pickle  CSV dönüşümü
   │       │
   ▼       ▼
analiz  UNION ALL / JOIN / bağımsız
   │       │
   └───┬───┘
       ▼
  m = { hesaplanmış metrikler }
       │
       ▼
  HTML f-string
       │
       ▼
  WeasyPrint PDF
```

---

## 9. Sık Karşılaşılan Hatalar ve Çözümleri

### Hata: `row['date_col'][:10]` datetime'da çalışmıyor

```python
# ❌ Yanlış — datetime objede slice olmaz
first_date = row['InvoiceDate'][:10]

# ✅ Doğru
first_date = pd.to_datetime(row['InvoiceDate']).strftime('%Y-%m-%d')

# ✅ DuckDB'den direkt string olarak al (daha güvenli)
duckdb.sql("SELECT CAST(MIN(InvoiceDate) AS VARCHAR)[:10] as first_order ...")
```

### Hata: Hardcoded sayılar PDF'de

```python
# ❌ Yanlış — önceki execute'dan kopyalanmış
m = {'customers': 5942, 'revenue': 16648292.39}

# ✅ Doğru — aynı execute'da hesapla
stats = duckdb.sql("SELECT COUNT(DISTINCT customer_id), SUM(revenue) FROM ...").fetchone()
m = {'customers': int(stats[0]), 'revenue': float(stats[1])}
```

### Hata: İkinci execute'da `csv_paths` bulunamıyor

```python
# ❌ Yanlış — Execute 1'de tanımlı, Execute 2'de yok
# KeyError: csv_paths

# ✅ Doğru — Execute 2'de yeniden tanımla (sabit path'lerden)
csv_paths = {
    'Sheet1': '/home/daytona/temp_sheet1.csv',
    'Sheet2': '/home/daytona/temp_sheet2.csv',
}
```

### Hata: Failed to resolve container IP

**Sebep:** Daytona sandbox container'ı geçici olarak network'ten düştü (DNS resolution hatası).

**Çözüm:** `execute.py` otomatik retry yapar (max 3 deneme, 1s delay). Eğer 3 denemede de başarısız olursa:

```python
# Kullanıcıya gösterilen mesaj:
"⚠️ Sandbox bağlantı hatası - container IP çözümlenemedi.
Lütfen 'Yeni Konuşma' ile oturumu sıfırlayın."
```

**Kod:** [src/tools/execute.py](src/tools/execute.py) lines 96-120 - Connection retry logic with exponential backoff.

### Hata: 40MB dosya hâlâ pandas ile okunuyor

```python
# parse_file çıktısını kontrol et:
# "⚠️ BÜYÜK DOSYA (43.5 MB ≥ 40MB) — DUCKDB STRATEJİSİ ZORUNLU"
# Bu mesajı görünce direkt CSV dönüşümüne geç

# ❌ Yanlış
df = pd.read_excel('/home/daytona/large.xlsx')  # MemoryError riski

# ✅ Doğru
xls = pd.ExcelFile('/home/daytona/large.xlsx')
for sheet in xls.sheet_names:
    df = pd.read_excel('/home/daytona/large.xlsx', sheet_name=sheet)
    df.to_csv(f'/home/daytona/temp_{sheet}.csv', index=False)
    del df
```

---

## 10. execute.py — Base64 Temp File Mekanizması

Agent `python3 -c "..."` şeklinde kod gönderir. Uzun kodlarda shell quote-escaping bozulur.
Çözüm: `execute.py` kodu base64'e çevirip temp dosyaya yazar:

```
Agent → execute(command="python3 -c 'import pandas...'")
              │
              ▼ (execute.py içinde)
         base64.b64encode(py_code)
              │
              ▼
         printf '%s' '<b64>' | base64 -d > /tmp/_run_abc123.py
         python3 /tmp/_run_abc123.py
         rm -f /tmp/_run_abc123.py
```

**Sonuç:** Tek tırnak, çift tırnak, özel karakter — hepsi güvenle iletilir.
Interceptor `cmd = args.get("command", "")` ile orijinal string'i görür (base64'ten önce).

---

## 11. Skill Sistemi — Prompt Progressive Disclosure

Her analiz isteğinde sistem prompt dinamik olarak derlenir:

```
Dosya yüklendi (.xlsx, 43.5 MB)
       │
       ▼
registry.py → detect_required_skills()
  • extension ".xlsx"  → skills/xlsx/SKILL.md  (ZORUNLU)
  • size 43.5MB ≥ 40MB → skills/xlsx/references/large_files.md  (EKLENİR)
  • keyword "duckdb"   → skills/xlsx/references/large_files.md  (EKLENİR)
  • ≥2 dosya + "join"  → skills/xlsx/references/multi_file_joins.md (EKLENİR)
       │
       ▼
loader.py → compose_system_prompt()
  = BASE_SYSTEM_PROMPT
  + xlsx/SKILL.md          (her xlsx'te)
  + large_files.md         (≥40MB veya keyword)
  + multi_file_joins.md    (≥2 dosya veya keyword)
```

**Kural dosyaları:**

| Dosya | İçerik | Ne zaman yüklenir |
|---|---|---|
| `xlsx/SKILL.md` | Sheet tespiti, analiz kuralları, m dict, PDF | Her xlsx/xls |
| `xlsx/references/large_files.md` | DuckDB pattern, multi-sheet CSV, UNION ALL | ≥40MB |
| `xlsx/references/multi_file_joins.md` | JOIN pattern, VLOOKUP karşılıkları | ≥2 dosya |
| `csv/SKILL.md` | CSV okuma, pickle, DuckDB | Her csv/tsv |
| `pdf/SKILL.md` | pdfplumber, OCR, tablo çıkarma | Her pdf |

---

## 12. Agent Cache — get_or_build_agent()

Agent her mesajda yeniden oluşturulmaz — **fingerprint** ile cache'lenir:

```python
# graph.py
fingerprint = (
    model_name,
    tuple(f.name for f in uploaded_files),
    tuple(f.size for f in uploaded_files),
)
# Aynı fingerprint → cached agent döner
# Yeni dosya veya farklı model → yeni agent build edilir
```

**Cache geçersiz olur:**
- Yeni dosya yüklenirse (name veya size değişir)
- "🔄 New Conversation" tıklanırsa (`reset_session()` → `_agent_cache.clear()`)
- Session sıfırlanırsa (sandbox değişir)

---

## 13. Sandbox Paket Kurulumu — Race Condition Çözümü

Sandbox oluşturulunca paketler background thread'de kurulur.
Agent hemen başlarsa paketler hazır olmayabilir → `threading.Event` ile beklenir:

```
Browser açılır
    │
    ▼
init_session() → SandboxManager()
    │
    ├── Background thread (_prewarm):
    │   ├── get_or_create_sandbox()
    │   └── _install_packages() (daemon thread):
    │       ├── Phase 1: DejaVuSans fontları kopyala (~1s)
    │       ├── Phase 2: Critical pkgs (weasyprint, pandas, openpyxl...) (~30s)
    │       ├── Phase 3: Optional pkgs (duckdb, pdfplumber) — ayrı thread
    │       └── _packages_ready.set()  ← her zaman, finally bloğunda
    │
    └── Kullanıcı sorgu gönderir
            │
            ▼
        chat.py → wait_until_ready(timeout=120s)  ← burada bekler
            │
            ▼ (paketler hazır)
        upload_files()
            │
            ▼
        agent.stream(query)
```

**Critical vs Optional ayrımı:**
- **Critical** (sync): weasyprint, pandas, openpyxl, numpy, matplotlib, seaborn, plotly, scipy, scikit-learn
- **Optional** (async background): duckdb, pdfplumber — ready sinyalinden SONRA kurulur

---

## 14. ArtifactStore — Thread-Safe UI Köprüsü

Agent thread'i `st.session_state`'e erişemez (ScriptRunContext hatası).
`ArtifactStore` bu sorunu bir global singleton + Lock ile çözer:

```
Agent Thread (tool call)          Streamlit UI Thread
        │                                │
  generate_html(html_str)                │
        │                                │
        ▼                                │
  ArtifactStore.add_html(html_str)       │
  (threading.Lock ile)                   │
        │                         Stream tamamlandı
        │                                │
        │                                ▼
        │                    artifact_store.pop_html()
        │                         → components.html()
        │                         → iframe gösterilir
        │
  create_visualization(fig)
        │
        ▼
  ArtifactStore.add_chart(png_bytes)
                                    artifact_store.pop_charts()
                                         → st.image()

  download_file(path)
        │
        ▼
  ArtifactStore.add_download(name, bytes)
                                    artifact_store.pop_downloads()
                                         → st.download_button()
```

---

## 15. Sandbox Disk Yönetimi

Daytona 30GiB disk limiti var. Stopped sandbox'lar disk kaplar.

```python
# Tüm stopped sandbox'ları sil
from daytona import Daytona, SandboxState

d = Daytona()
result = d.list()
sandboxes = result.items if hasattr(result, 'items') else list(result)

for s in sandboxes:
    state = getattr(s, 'state', None)
    print(f"{s.id[:8]}... {state}")
    if state == SandboxState.STOPPED:
        d.delete(s)
        print(f"  → Silindi")
```

**`auto_delete_interval=3600`** (`manager.py`): Sandbox 1 saat idle kalırsa otomatik silinir.
Ama stopped (manuel durdurulmuş) sandbox'lar bu TTL'den etkilenmez — `d.delete()` gerekir.

**Disk harcayan dosyalar:**
- Excel dosyaları: 40-100MB
- CSV temp dosyaları: Excel ile benzer boyut (analiz sonrası silinmeli)
- Pickle: genellikle <10MB
- PDF: 50-500KB

```python
# Analiz bittikten sonra temp dosyaları temizle
import os
temp_files = [
    '/home/daytona/temp_sheet1.csv',
    '/home/daytona/temp_sheet2.csv',
    '/home/daytona/clean_data.pkl',
    '/home/daytona/report_temp.html',
]
for f in temp_files:
    if os.path.exists(f):
        os.remove(f)
```
