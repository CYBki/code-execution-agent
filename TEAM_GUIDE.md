# Agentic Analyze — Ekip Teknik Dokümanı

## 1. Proje Nedir?

Excel, CSV ve PDF dosyalarını analiz eden, sonuçları **PDF rapor** veya **interaktif HTML dashboard** olarak sunan bir AI agent uygulaması.

**Kullanıcı deneyimi:**
1. Sol panelden dosya yükle (`.xlsx`, `.csv`, `.pdf`)
2. Türkçe soru sor: *"Müşteri başına sipariş ortalaması nedir? PDF rapor ver."*
3. Agent çalışır → PDF indirme butonu belirir

---

## 2. Teknoloji Stack'i ve Seçim Nedenleri

| Katman | Teknoloji | Neden? |
|---|---|---|
| **UI** | Streamlit | Hızlı prototipleme, dosya upload built-in, `st.download_button` |
| **LLM** | Claude Sonnet 4 (Anthropic) | Uzun context, güçlü kod üretme, Türkçe |
| **Agent framework** | LangChain `create_agent` + LangGraph | ReAct döngüsü, MemorySaver, middleware stack |
| **Kod çalıştırma** | OpenSandbox | İzole ortam + persistent kernel — değişkenler execute'lar arası korunur |
| **Büyük dosya** | DuckDB | 40MB+ Excel'i pandas'a yüklemeden SQL ile sorgular |
| **PDF üretimi** | WeasyPrint | HTML/CSS → PDF, Türkçe karakter sorunu yok |

---

## 3. Sistem Mimarisi — Bileşenler

```
┌─────────────────────────────────────────────┐
│              Streamlit UI (app.py)           │
│   Sidebar: file upload, new chat, model info │
│   Chat: streaming, step persistence, artifacts│
└────────────┬──────────────────┬─────────────┘
             │ dosya + sorgu    │
             ▼                  ▼
┌─────────────────┐   ┌──────────────────────┐
│  Skill System   │   │  Agent (graph.py)     │
│  registry.py    │──▶│  Claude Sonnet 4      │
│  loader.py      │   │  ReAct: max 30 adım   │
└─────────────────┘   │  smart_interceptor    │
                      └─────────┬────────────┘
                                │ tool call
          ┌─────────────────────┼──────────────┐
          ▼         ▼           ▼              ▼
    parse_file   execute   generate_html  download_file
    (LOCAL)     (SANDBOX)   (BROWSER)     (SANDBOX)
                    │
                    ▼
             ArtifactStore
          (thread-safe köprü)
                    │
                    ▼
         st.download_button / iframe
```

---

## 4. Uçtan Uca Veri Akışı

### 4.1 Oturum Açılışı (Prewarm)

```
Tarayıcı açılır → app.py
    ↓
init_session()
    ├── session_id = uuid4()
    ├── SandboxManager() oluşturulur
    └── Background thread (_prewarm):
        ├── get_or_create_sandbox(session_id)
        │   ├── OpenSandbox'ta session_id olan sandbox var mı?
        │   │   ├── VAR  → state kontrol et, STOPPED ise start()
        │   │   └── YOK  → create(TTL=7200s)
        └── _install_packages() (daemon thread):
            ├── Phase 1: DejaVuSans fontlarını /home/sandbox/'a kopyala (~1s)
            ├── Phase 2: Pre-installed paketleri verify (weasyprint, pandas, openpyxl...) (~5s)
            ├── Phase 3: Verify → import weasyprint, pandas, openpyxl
            └── _packages_ready.set()  ← HER ZAMAN finally'de
```

**Neden prewarm?** Kullanıcı ilk sorusunu gönderdiğinde sandbox hazır olsun, 30 saniye bekletmeyelim.

### 4.2 Kullanıcı Dosya Yükler ve Soru Sorar

```
Dosya + sorgu gelir → chat.py render_chat()
    ↓
get_or_build_agent(fingerprint)
    ├── Aynı fingerprint (dosya adı + boyutu) → cached agent döner
    └── Farklı fingerprint → yeni agent build et (skill + prompt derle)
    ↓
wait_until_ready(timeout=120s)  ← paketler hazır mı?
    ↓
upload_files()
    ├── Native API: backend.upload_files([(path, bytes)])
    └── Fallback: chunked base64 (512KB chunk'lar, büyük dosya için)
    ↓
reset_interceptor_state()  ← ZORUNLU, closure counter'larını sıfırla
    ↓
agent.stream(query, stream_mode="updates")
```

### 4.3 Agent ReAct Döngüsü (Küçük Dosya, <40MB)

```
① parse_file("data.xlsx")
   → şema: kolonlar, dtypes, satır sayısı, boyut, sheet'ler
   → execute harcamaz, LOCAL çalışır

② execute("""
   import pandas as pd
   df = pd.read_excel('/home/sandbox/data.xlsx')
   df.dropna(subset=['Customer ID'], inplace=True)
   print(f"✅ Yüklendi: {len(df):,} satır")
   # df bellekte persist eder, pickle gerekmez
   """)
   → veriyi yükle + temizle

③ execute("""
   # df HALA bellekte — persistent kernel sayesinde
   import weasyprint, os
   m = {
       'customers': df['Customer ID'].nunique(),
       'revenue':   (df['Quantity'] * df['Price']).sum(),
   }
   html = f'<html>...<b>{m["customers"]:,}</b>...</html>'
   weasyprint.HTML(string=html).write_pdf('/home/sandbox/rapor.pdf')
   print(f"✅ PDF: {os.path.getsize('/home/sandbox/rapor.pdf')//1024} KB")
   """)
   → df hala mevcut, analiz + PDF TEK execute'da

④ download_file('/home/sandbox/rapor.pdf')
   → sandbox'tan binary oku → ArtifactStore.add_download()
   → UI'da st.download_button belirir
```

### 4.4 Agent ReAct Döngüsü (Büyük Dosya, ≥40MB)

```
① parse_file("large.xlsx")
   → "⚠️ BÜYÜK DOSYA (43.5 MB ≥ 40MB) — DUCKDB STRATEJİSİ ZORUNLU"

② execute("""
   import pandas as pd
   xls = pd.ExcelFile('/home/sandbox/large.xlsx')
   csv_paths = {}
   for sheet in xls.sheet_names:
       df = pd.read_excel('/home/sandbox/large.xlsx', sheet_name=sheet)
       csv_path = f'/home/sandbox/temp_{sheet}.csv'
       df.to_csv(csv_path, index=False)
       csv_paths[sheet] = csv_path
       del df  # RAM serbest bırak
   print(f"✅ CSV'ler hazır: {csv_paths}")
   # csv_paths persistent kernel'da bellekte kalır
   """)
   → her sheet ayrı CSV olarak diske yazılır

③ execute("""
   # csv_paths HALA bellekte — persistent kernel sayesinde
   import duckdb, weasyprint, os
   # Robust kod için path'leri açıkça yazabiliriz:
   # csv_paths = {'Sheet1': '/home/sandbox/temp_Sheet1.csv', ...}

   # UNION ALL ile tüm dönemsel veriler birleştirilir
   union = " UNION ALL ".join(
       f"SELECT *, '{s}' as period FROM read_csv_auto('{p}')"
       for s, p in csv_paths.items()
   )
   stats = duckdb.sql(f"SELECT COUNT(DISTINCT customer_id), SUM(revenue) FROM ({union})").fetchone()
   m = {'customers': int(stats[0]), 'revenue': float(stats[1])}
   # ... HTML + PDF üret
   """)
   → csv_paths hala mevcut, analiz + PDF TEK execute'da
```

**Not:** Persistent kernel ile csv_paths Execute #1'den Execute #2'ye taşınır. Ancak robust kod için path'leri açıkça yazmak iyi pratik (kernel restart durumunda güvenli).

---

## 5. Persistent Kernel — Kritik Tasarım Kararı

```
Agent process (tek process, LLM)
    │
    └── OpenSandbox CodeInterpreter (persistent kernel)
        │
        ├── execute() #1 → df yükle, temizle
        │                   df, imports, değişkenler bellekte KALIR
        ├── execute() #2 → df HALA mevcut → analiz
        │                   m dict hesapla, bellekte KALIR
        └── execute() #3 → df ve m HALA mevcut → PDF üret
```

**Önemli:** `execute()` çağrıları **aynı persistent Python kernel**'da çalışır. Değişkenler, imports, DataFrames execute'lar arası **otomatik korunur** — pickle/disk gerekmez.

**İstisna:** `generate_html()` **ayrı process**'te çalışır, Python değişkenlerini göremez. HTML string'i execute içinde tamamen oluştur, sonra `generate_html()`'e literal olarak geç.

Büyük dosyalar için hala DuckDB stratejisi kullanılır:

| Strateji | Kullanım | Avantaj |
|---|---|---|
| **Persistent Kernel** | <40MB, pandas analizi | Değişkenler persist eder, hızlı |
| **CSV + DuckDB** | ≥40MB | Disk'ten lazy query, bellek patlamaz |

### Base64 Temp File Mekanizması

Agent `python3 -c "..."` formatında kod gönderir. Uzun kodlarda shell quote-escaping bozulur. `execute.py` bunu şöyle çözer:

```
Agent → execute(command="import pandas as pd\n...")
              ↓
        py_code = _extract_python_code(command)
        b64 = base64.b64encode(py_code.encode())
              ↓
        "printf '%s' '<b64>' | base64 -d > /tmp/_run_abc.py"
        "python3 /tmp/_run_abc.py"
        "rm -f /tmp/_run_abc.py"
```

Tek/çift tırnak, özel karakter, Unicode — hepsi güvenle iletilir.

---

## 6. Skill Sistemi — Progressive Disclosure

Her analiz için sistem promptu **dinamik olarak derlenir**. Mantık: küçük dosyalar için küçük prompt (context tasarrufu), büyük/karmaşık dosyalar için zengin prompt.

```
Dosya yüklendi
    ↓
registry.py → detect_required_skills()
    • .xlsx/.xls  → "xlsx" skill
    • .csv/.tsv   → "csv" skill
    • .pdf        → "pdf" skill
    • sorgu içinde "chart/plot/dashboard" → "visualization" skill

detect_reference_files()  (sadece xlsx için)
    • boyut ≥ 40MB → large_files.md eklenir
    • ≥ 2 xlsx dosyası VEYA "join/merge" keyword → multi_file_joins.md eklenir
    ↓
loader.py → compose_system_prompt()
    = BASE_SYSTEM_PROMPT
    + SKILL.md (her xlsx için)
    + large_files.md (gerekirse)
    + multi_file_joins.md (gerekirse)
    + yüklenen dosya listesi
```

**Skill dosyaları** (`skills/` klasörü):
- `xlsx/SKILL.md` — persistent kernel pattern, m dict, WeasyPrint kuralları
- `xlsx/references/large_files.md` — DuckDB pattern, UNION ALL, sheet CSV dönüşümü
- `xlsx/references/multi_file_joins.md` — JOIN pattern, VLOOKUP → SQL
- `csv/SKILL.md` — CSV okuma kuralları
- `pdf/SKILL.md` — pdfplumber, tablo çıkarma
- `visualization/SKILL.md` — chart seçimi, Plotly, matplotlib

---

## 7. Smart Interceptor — Neden Var?

LLM'ler bazen verimli olmayan veya tehlikeli kod üretir. `smart_interceptor`, `@wrap_tool_call` ile her tool çağrısını **agent'tan önce** yakalar.

### 7.1 Blok Kuralları (execute hakkı düşmez)

```python
# Her kural: gerçek mesaja yönlendirme içerir, execute sayacı geri alınır

❌ ls / find / cat / os.listdir / glob
   → "Dosya path biliniyor, parse_file kullan"

❌ pip install / subprocess
   → "Paketler pre-installed: pandas, openpyxl, weasyprint..."

❌ urllib / requests / wget / curl
   → "Sandbox'tan dış ağ erişimi yasak. Fontlar zaten /home/sandbox/'da"

❌ nrows > 10
   → "TÜM veriyi oku — sampling yasak"

❌ nrows ≤ 10 + parse_file zaten çalıştıysa
   → "Schema zaten var, CSV dönüşümüne geç"

❌ Aynı dosya için 2. parse_file
   → "Schema sende var, CSV dönüşüm kodunu ver"

❌ Execute > limit (6 veya 10)
   → "Limit doldu, kullanıcıya dürüst ol"
```

### 7.2 Auto-Fix (execute değiştirilir, çalışır)

```python
# Font fix: Arial/Helvetica sandbox'ta yok
"Arial"     → "DejaVu"
"Helvetica" → "DejaVu"

# add_font inject: DejaVu kullanılıyor ama add_font() unutulmuş
→ pdf.add_page()'dan sonra add_font() satırları eklenir

# class-based FPDF fix: font ordering sorununa yol açar
class PDF(FPDF): ...   →   pdf = FPDF()
```

### 7.3 Dinamik Execute Limiti

```python
def _compute_max_execute(query, files):
    is_complex = any(kw in query for kw in [
        "rfm", "cohort", "cluster", "segment", "pivot",
        "karşılaştır", "korelasyon", "forecast"
    ])
    is_large = total_file_size > 10MB
    return 10 if (is_complex or is_large) else 6
```

### 7.4 Execute Sonrası Bilgi Enjeksiyonu

Her execute sonucuna şunlar eklenir:
- **Kalan execute hakkı:** `[Execute 2/6, kalan: 4]`
- **Hata varsa:** Düzeltme döngüsü başlatılır (max 2 deneme), sonra "bu metriği atla" mesajı
- **Son 2 haksa:** "analiz+PDF tek script olmalı" uyarısı
- **Her adım:** `💭 DÜŞÜNCE: [ne gözlemledin] → [ne yapacaksın] → [neden]` zorlaması

---

## 8. ArtifactStore — Threading Sorunu ve Çözümü

**Problem:** Streamlit'te `st.session_state`, sadece ana Streamlit thread'inden erişilebilir. Agent tool'ları farklı thread'lerde çalışır → `ScriptRunContext` hatası.

**Çözüm:** Global singleton + `threading.Lock`

```
Agent Thread (tool çalışır)       Streamlit Thread (render eder)
        │                                  │
  generate_html(html)                      │
        ↓                                  │
  ArtifactStore.add_html(html)             │
  (Lock ile thread-safe)                   │
                                  ← stream tamamlandı
                                  artifact_store.pop_html()
                                       → components.html() (iframe)

  download_file(path)
        ↓
  ArtifactStore.add_download(name, bytes)
                                  artifact_store.pop_downloads()
                                       → st.download_button()
```

---

## 9. Sandbox Yaşam Döngüsü

```
Durum Makinesi:
CREATING → STARTING → STARTED ← → STOPPED ← → ARCHIVED
                         ↓
                      DESTROYING → DESTROYED

SandboxManager._ensure_started():
  STOPPED/ARCHIVED/RESTORING → start()
  STARTED/STARTING/CREATING  → bekle
  Diğer (ERROR, BUILD_FAILED) → uyar, devam et
```

**TTL sistemi:**
- `auto_delete_interval=7200` → 2 saat idle sandbox otomatik silinir
- `atexit.register(mgr.stop)` → process kapanınca sandbox durdurulur
- "🔄 New Conversation" → eski sandbox stop, yeni SandboxManager, yeni prewarm

**Disk yönetimi:**
Docker container'lar disk kaplar. Kullanılmayan sandbox'ları temizlemek için sistem yöneticisiyle koordinasyon gerekebilir.

**Sandbox disk yapısı:**
```
/home/sandbox/
├── veri.xlsx              ← kullanıcı dosyası (upload ile gelir)
├── temp_Sheet1.csv        ← DuckDB için CSV (≥40MB dosyalar, analiz sonrası silinir)
├── rapor.pdf              ← çıktı
├── DejaVuSans.ttf         ← kalıcı font (Phase 1'de kopyalandı)
└── DejaVuSans-Bold.ttf    ← kalıcı font
```

---

## 10. Agent Cache Mekanizması

Her soruda agent yeniden oluşturulmaz:

```python
# graph.py - get_or_build_agent()
file_fingerprint = tuple(
    (f.name, len(f.getvalue())) for f in uploaded_files
)

cached = st.session_state.get("_agent_cache")
if cached and cached["fingerprint"] == file_fingerprint:
    return cached["agent"], cached["checkpointer"], cached["reset_fn"]
# Farklı fingerprint → yeni agent, yeni skill prompt derlenir
```

**Cache geçersiz olur:**
- Yeni dosya yüklenirse (ad veya boyut değişir)
- "New Conversation" tıklanırsa
- Session sıfırlanırsa

**`reset_interceptor_state()` ZORUNLUdur** — closure içindeki `_execute_count`, `_seen_parse_files` vb. counter'lar agent cache'de yaşar. Yeni soruda sıfırlanmadan kalırsa limitler yanlış hesaplanır.

---

## 11. BASE_SYSTEM_PROMPT Stratejisi

`prompts.py`'deki prompt İngilizce yazılmıştır (token efficiency için). İlk satır: "Always respond to the user in Turkish."

**Neden İngilizce?**
- Token verimliliği: İngilizce ~20-30% daha az token (UTF-8 multi-byte yok)
- Claude'un native dili: instruction following daha güçlü
- Maintenance: kod review, debugging, collaboration kolay
- Agent yanıtları Türkçe (kullanıcıya), system prompt İngilizce (Claude'a)

Prompt 3 kritik davranışı zorlar:

**1. Sayı yasağı (chat mesajında):**
```
❌ "Suzanne Collins 278,329 değerlendirme ile lider"
✅ "En popüler yazar analizi ve başarı faktörleri raporlandı"
Sayısal detaylar PDF'te olsun
```

**2. ReAct döngüsü zorunluluğu:**
```
DÜŞÜNCE: [öncekinden ne öğrendim] → [ne yapacağım ve NEDEN]
  execute(...)
GÖZLEM: [çıktıyı oku]
KARAR: [hedefe ulaştım mı? hayır → ne düzeltmeliyim?]
```

**3. Schema-first zorunluluğu:**
```
İlk araç her zaman parse_file()
Kolon adlarını ASLA tahmin etme
```

---

## 12. Middleware Stack

```python
middleware = [
    create_summarization_middleware(model, backend),  # eski mesajları özetler
    AnthropicPromptCachingMiddleware(),               # Anthropic cache breakpoint'leri
    PatchToolCallsMiddleware(),                        # tool call format normalize
    smart_interceptor,                                 # blok/fix/rate-limit
]
```

**Summarization middleware:** Uzun konuşmalarda context window dolmadan önce eski mesajları özetleyerek bağlamı küçük tutar.

**AnthropicPromptCachingMiddleware:** Aynı sistem promptu tekrar tekrar gönderildiğinde Anthropic cache kullanır → API maliyetini düşürür.

---

## 13. Deployment Notları

### Gereksinimler

```bash
Python 3.12+
ANTHROPIC_API_KEY      # console.anthropic.com
OPEN_SANDBOX_API_KEY   # OpenSandbox backend
```

### Kurulum

```bash
git clone <repo>
cd agentic_analyze_d
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # API key'leri gir
streamlit run app.py
```

### Bağımlılıklar (`pyproject.toml`)

```toml
deepagents          # LangChain create_agent + middleware
langchain-anthropic >= 1.4.0
opensandbox         # OpenSandbox backend
streamlit >= 1.40.0
pandas, openpyxl, duckdb >= 1.1.0
pdfplumber, Pillow, pyyaml
```

### Sık Karşılaşılan Sorunlar

| Sorun | Sebep | Çözüm |
|---|---|---|
| Sandbox başlamıyor | Docker disk/kaynak | Sistem yöneticisiyle iletişim |
| `ModuleNotFoundError: deepagents` | `pip install -e .` yapılmadı | `pip install -e .` çalıştır |
| İlk sorgu ~5-10s bekliyor | Package verification devam ediyor | Normaldir, prewarm tam bitmedi |
| PDF oluşturulmuyor | Arial/Helvetica font | smart_interceptor otomatik düzeltir |

---

## 14. Güvenlik Kararları Özeti

| Karar | Neden? |
|---|---|
| Sandbox izolasyonu (OpenSandbox) | Kullanıcı kodu local process'e zarar veremez |
| `pip install` bloklaması | Paketler pre-installed; LLM kötü niyetli paket kuramaz |
| Ağ isteği bloklaması | Sandbox veri sızdıramaz, dış kaynak çekemez |
| Filesystem keşfi bloklaması | Path zaten biliniyor; LLM sandbox dizinini tarayamaz |
| Execute limit | Sonsuz döngüyü ve maliyet patlamasını önler |
| Hardcoded metrik bloklaması | LLM hallucination'ını PDF'e yansıtmaz |
| Persistent kernel | Değişkenler korunur → kod daha basit, hata riski azalır |

---

*Doküman `src/agent/graph.py`, `src/sandbox/manager.py`, `src/tools/execute.py`, `src/skills/registry.py`, `src/agent/prompts.py`, `ARCHITECTURE.md` ve `TECHNICAL_GUIDE.md` kaynak alınarak derlenmiştir.*
