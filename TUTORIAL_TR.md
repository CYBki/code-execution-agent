# 🎓 Code Execution Agent — Sıfırdan Ustaya Türkçe Tutorial

> **Bu belge seni bu projenin her köşesini anlayacak seviyeye getirecek, adım adım, kod kod.**
> Bir arkadaşınla kahve içerken sohbet eder gibi yazıldı. Teknik terimler açıklanacak, tasarım kararları sorgulanacak.

---

## 📑 İçindekiler

- [Adım 0: Projeye Genel Bakış](#adım-0-projeye-genel-bakış)
- [Adım 1: Uygulama Nasıl Başlıyor?](#adım-1-uygulama-nasıl-başlıyor-apppy)
- [Adım 2: Oturum Yönetimi](#adım-2-oturum-yönetimi-srcuisessionpy)
- [Adım 3: Sandbox Sistemi](#adım-3-sandbox-sistemi-srcsandboxmanagerpy)
- [Adım 4: Skill Sistemi](#adım-4-skill-sistemi-progressive-disclosure)
- [Adım 5: Araçlar (Tools)](#adım-5-araçlar-tools--ajanın-elleri)
- [Adım 6: Ajanın Beyni](#adım-6-ajanın-beyni-srcagentgraphpy)
- [Adım 7: Sistem Prompt'u](#adım-7-sistem-promptu-srcagentpromptspy)
- [Adım 8: Kullanıcı Arayüzü](#adım-8-kullanıcı-arayüzü-ui)
- [Adım 9: Veritabanı](#adım-9-veritabanı-srcstoragedbpy)
- [Adım 10: Tüm Akış Birlikte](#adım-10-tüm-akış-birlikte-end-to-end)
- [Bonus: Projeyi Geliştirmek İstersen](#bonus-projeyi-geliştirmek-i̇stersen)
- [Adım 11: Production'a Hazırlık — Deployment Rehberi](#adım-11-productiona-hazırlık--deployment-rehberi)
- [Adım 12: İzleme ve Operasyonlar](#adım-12-i̇zleme-ve-operasyonlar-monitoring--ops)
- [Adım 13: Güvenlik Sertleştirme](#adım-13-güvenlik-sertleştirme)
- [Adım 14: Yedekleme ve Felaket Kurtarma](#adım-14-yedekleme-ve-felaket-kurtarma)
- [Adım 15: Sorun Giderme Runbook'u](#adım-15-sorun-giderme-runbooku)
- [Adım 16: Ölçeklendirme ve Kapasite Planlaması](#adım-16-ölçeklendirme-ve-kapasite-planlaması)

---

## Adım 0: Projeye Genel Bakış

### Bu Proje Ne Yapıyor?

Bir kullanıcı düşün: elinde karmaşık bir Excel dosyası var, binlerce satır veri. Normal yol ne? Excel'i aç, pivot table yap, grafik çiz, Word'e yapıştır… Saatler sürer.

Bu proje, o işi **AI'a yaptırıyor.** Kullanıcı dosyasını yükler, Türkçe bir soru sorar — "Müşteri başına ortalama sipariş nedir? PDF rapor ver." — ve birkaç saniye içinde:

1. Veri okunur ve temizlenir
2. Analiz yapılır
3. PDF rapor üretilir (WeasyPrint ile)
4. İnteraktif HTML dashboard oluşturulur (Chart.js ile)
5. Kullanıcıya indirme butonu sunulur

Hepsi **izole bir Docker container** içinde çalışır — kullanıcının kodu senin bilgisayarına zarar veremez.

### Teknoloji Yığını

```
┌─────────────────────────────────────────────────────────┐
│                    Kullanıcı (Tarayıcı)                 │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP
┌─────────────────────▼───────────────────────────────────┐
│              Streamlit UI (app.py)                       │
│  ┌──────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ Sidebar  │ │   Chat UI    │ │   Artifact Render    │ │
│  │(upload)  │ │  (stream)    │ │ (HTML/PDF/chart)     │ │
│  └──────────┘ └──────┬───────┘ └──────────────────────┘ │
└──────────────────────┼──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│            LangChain / LangGraph Agent                   │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Smart Interceptor (güvenlik + otomatik düzeltme)  │  │
│  └────────────────────────┬───────────────────────────┘  │
│  ┌──────────┐ ┌───────────▼──┐ ┌────────────┐           │
│  │parse_file│ │   execute    │ │generate_html│           │
│  │(yerel)   │ │ (sandbox'a)  │ │ (artifact)  │           │
│  └──────────┘ └───────┬──────┘ └────────────┘           │
└───────────────────────┼─────────────────────────────────┘
                        │ API
┌───────────────────────▼─────────────────────────────────┐
│           OpenSandbox (Docker Container)                  │
│  ┌─────────────────────────────────────────────────────┐ │
│  │     CodeInterpreter (Kalıcı Python Kernel)          │ │
│  │  ┌─────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐  │ │
│  │  │ pandas  │ │ duckdb │ │weasyprint│ │matplotlib│  │ │
│  │  └─────────┘ └────────┘ └──────────┘ └──────────┘  │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

| Katman | Teknoloji | Rol |
|--------|----------|-----|
| **UI** | Streamlit | Web arayüzü, dosya yükleme, chat |
| **Ajan** | LangChain `create_agent` + Claude Sonnet 4 | Karar verme, ReAct döngüsü |
| **Güvenlik** | Smart Interceptor | Her tool çağrısını denetleme |
| **Sandbox** | OpenSandbox (Docker) | İzole Python çalıştırma |
| **Veri İşleme** | pandas, DuckDB | Veri analizi |
| **Raporlama** | WeasyPrint, Chart.js, matplotlib | PDF + dashboard |
| **Veritabanı** | SQLite / PostgreSQL | Konuşma geçmişi |

### Proje Dizin Yapısı

```
code-execution-agent/
├── app.py                          # 🚀 Giriş noktası — her şey buradan başlar
├── cleanup_sandboxes.py            # 🧹 Duran sandbox container'ları temizler
│
├── src/
│   ├── agent/
│   │   ├── graph.py                # 🧠 Ajanın beyni: build_agent + smart_interceptor
│   │   └── prompts.py              # 📜 Sistem prompt'u: kurallar, ReAct şablonu
│   │
│   ├── sandbox/
│   │   └── manager.py              # 📦 OpenSandbox yaşam döngüsü, kalıcı kernel
│   │
│   ├── skills/
│   │   ├── registry.py             # 🎯 Skill tetikleyiciler (dosya tipi, boyut)
│   │   ├── loader.py               # 📚 Skill dosyalarını yükle, prompt derle
│   │   └── learner.py              # 🤖 Otomatik skill iyileştirme (LLM-as-judge)
│   │
│   ├── tools/
│   │   ├── execute.py              # ⚡ Sandbox'ta kod çalıştır
│   │   ├── file_parser.py          # 📋 Yerel dosya şeması çıkar (sandbox'a gitmez)
│   │   ├── generate_html.py        # 🌐 HTML dashboard render
│   │   ├── visualization.py        # 📊 matplotlib/seaborn PNG grafikler
│   │   ├── download_file.py        # 📥 Sandbox'tan dosya indir
│   │   └── artifact_store.py       # 🔗 Thread-safe köprü (ajan ↔ UI)
│   │
│   ├── ui/
│   │   ├── chat.py                 # 💬 Chat arayüzü, ajan stream, artifact render
│   │   ├── components.py           # 📁 Sidebar: dosya yükleme, konuşma geçmişi
│   │   ├── session.py              # 🔑 Oturum yönetimi, sandbox ön-ısıtma
│   │   └── styles.py               # 🎨 CSS stilleri, araç ikonları
│   │
│   ├── storage/
│   │   └── db.py                   # 💾 SQLite/PostgreSQL — konuşma kaydetme
│   │
│   └── utils/
│       ├── config.py               # ⚙️ API key çözümleme
│       └── logging_config.py       # 📝 JSON log formatı, audit trail
│
├── skills/                         # 📖 Skill dosyaları (ajan talimatları)
│   ├── xlsx/
│   │   ├── SKILL.md                # Excel analiz kuralları
│   │   └── references/
│   │       ├── large_files.md      # ≥40MB DuckDB stratejisi
│   │       └── multi_file_joins.md # Çoklu dosya JOIN
│   ├── csv/SKILL.md                # CSV/TSV kuralları
│   ├── pdf/SKILL.md                # PDF parsing kuralları
│   └── visualization/SKILL.md      # Grafik kuralları
│
├── pyproject.toml                  # Bağımlılıklar
├── CLAUDE.md                       # AI asistanlar için proje rehberi
└── README.md                       # Kurulum ve kullanım
```

> 💡 **Neden böyle?**
> Proje katmanlı mimari (layered architecture) kullanıyor. Her katman sadece altındaki katmanla konuşuyor:
> UI → Agent → Tools → Sandbox. Bu sayede bir katmanı değiştirdiğinde diğerleri etkilenmez.

---

## Adım 1: Uygulama Nasıl Başlıyor? (`app.py`)

`app.py` projenin **giriş noktası** — Streamlit uygulaması buradan başlıyor. Sadece 58 satır, ama çok şey yapıyor. Satır satır inceleyelim:

```python
"""Streamlit entry point — Data Analysis Agent with LangChain + OpenSandbox."""

import os

from dotenv import load_dotenv
```

İlk iş: `.env` dosyasından ortam değişkenlerini yükle. Bu dosyada API anahtarların var:
- `ANTHROPIC_API_KEY` — Claude modeline erişim
- `OPEN_SANDBOX_API_KEY` — OpenSandbox'a erişim
- `OPEN_SANDBOX_DOMAIN` — OpenSandbox sunucu adresi

```python
from src.utils.logging_config import setup_logging

setup_logging()
```

Yapılandırılmış JSON loglama başlatılıyor. Loglar üç yere yazılır:
1. **Konsol** — geliştirme sırasında görürsün
2. **`logs/app.log`** — tüm loglar (INFO+)
3. **`logs/app_error.log`** — sadece hatalar (WARNING+)

Her log satırı bir JSON nesnesi: timestamp, level, logger adı, session_id (korelasyon için), ve mesaj.

```python
import streamlit as st

load_dotenv()

st.set_page_config(
    page_title="Data Analysis Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
```

Streamlit sayfa yapılandırması. `layout="wide"` dashboard'ların geniş görünmesi için.

```python
from src.ui.styles import CUSTOM_CSS
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
```

Özel CSS enjeksiyonu. `styles.py`'deki CSS, Claude-benzeri karanlık kod blokları, araç kartları, animasyonlu yükleme göstergeleri ekliyor. `unsafe_allow_html=True` olmadan Streamlit ham HTML'i göstermez.

```python
from src.utils.config import get_secret

try:
    get_secret("ANTHROPIC_API_KEY")
except ValueError:
    st.error("⚠️ ANTHROPIC_API_KEY bulunamadı. .env dosyasına ekleyin.")
    st.stop()
```

API anahtarı doğrulaması. `get_secret()` fonksiyonu iki yere bakar:
1. `st.secrets` — Streamlit Cloud'da çalışırken
2. `os.environ` — yerel geliştirmede (`.env`'den yüklenen)

Bulamazsa hata gösterir ve `st.stop()` ile uygulamayı durdurur. Sandbox anahtarı burada kontrol edilmez — sandbox oluşturulurken kontrol edilir.

```python
from src.storage.db import init_db
init_db()
```

Veritabanı tablolarını oluşturur (yoksa). SQLite veya PostgreSQL — `DATABASE_URL` ortam değişkenine bağlı.

```python
from src.ui.session import init_session
init_session()
```

Bu satır **çok kritik**. Oturum durumunu başlatıyor ve arka planda sandbox container'ını oluşturuyor. Detayları Adım 2'de göreceğiz.

```python
from src.ui.components import render_sidebar
render_sidebar()
```

Sol paneli çizer: dosya yükleme widget'ı, yüklenen dosya listesi, "Yeni Konuşma" butonu, konuşma geçmişi.

```python
from src.ui.chat import render_chat
render_chat()
```

Ana sohbet arayüzünü çizer: mesaj geçmişi, kullanıcı girdisi, ajan stream'i, artifact render.

> 🔑 **Anahtar kavram: Streamlit Çalışma Modeli**
> Streamlit "top-to-bottom" çalışır. Kullanıcı bir butona her tıkladığında veya mesaj yazdığında, **tüm script baştan çalışır**. Bu yüzden `st.session_state` çok önemli — sayfalar arası durumu korumak için kullanılıyor.

> 🧪 **Kendin dene:**
> `app.py`'nin ilk satırına `import time; time.sleep(2)` ekle ve sayfayı yenile. 2 saniye bekleyecek — çünkü Streamlit her seferinde tüm script'i çalıştırıyor.

### Başlatma Sırası (Özet)

```
1. setup_logging()        → JSON loglar yapılandır
2. load_dotenv()          → .env'den API anahtarlarını yükle
3. st.set_page_config()   → Sayfa başlığı, layout
4. CUSTOM_CSS inject      → Özel stiller
5. get_secret() validate  → ANTHROPIC_API_KEY kontrol
6. init_db()              → SQLite/PostgreSQL tablolar
7. init_session()         → Session state + sandbox ön-ısıtma 🔥
8. render_sidebar()       → Sol panel UI
9. render_chat()          → Ana chat UI
```

---

## Adım 2: Oturum Yönetimi (`src/ui/session.py`)

### Session State Nedir?

Streamlit'te her sayfa yenilemesinde Python değişkenleri sıfırlanır. Ama chat geçmişini, yüklenen dosyaları, sandbox bağlantısını kaybetmek istemezsin. İşte `st.session_state` bunun için var — tarayıcı sekmesi açık olduğu sürece yaşayan bir sözlük.

### `init_session()` — Oturumun Kalbi

```python
def init_session():
    """Initialize Streamlit session state with all required keys."""
    if "initialized" in st.session_state:
        return  # Zaten başlatılmış, tekrar yapma
```

İlk satır: tekrar çalıştırmayı önlüyor. Streamlit her interaksiyonda tüm script'i çalıştırdığından, bu kontrol olmadan her tıklamada yeni sandbox oluşturulurdu.

```python
    # Core state
    st.session_state.setdefault("messages", [])           # Chat geçmişi
    st.session_state.setdefault("session_id", str(uuid4()))  # Benzersiz oturum ID
    st.session_state.setdefault("user_id", "default_user")
    st.session_state.setdefault("uploaded_files", [])     # Yüklenen dosyalar
```

`setdefault()` kullanımı önemli — sadece anahtar yoksa değer atar. Bu sayede mevcut değerleri ezmez.

### Sandbox Ön-Isıtma (Pre-warming)

İşte burada büyü başlıyor:

```python
    if "sandbox_manager" not in st.session_state:
        st.session_state["sandbox_manager"] = SandboxManager()

    if "sandbox_prewarm_done" not in st.session_state:
        st.session_state["sandbox_prewarm_done"] = True

        _mgr = st.session_state["sandbox_manager"]
        _thread_id = st.session_state["session_id"]

        def _prewarm(mgr, thread_id):
            try:
                mgr.get_backend(thread_id)
            except Exception as e:
                logger.error("Sandbox pre-warm failed: %s", e)

        threading.Thread(
            target=_prewarm, args=(_mgr, _thread_id), daemon=True
        ).start()
```

> 💡 **Neden böyle?**
> Sandbox oluşturmak ~5 saniye sürüyor (Docker container başlatma). Kullanıcı daha soru sormadan, **arka plan thread'inde** sandbox'ı hazırlıyoruz. Kullanıcı ilk sorusunu yazdığında sandbox zaten hazır. Buna **pre-warming** (ön-ısıtma) deniyor.
>
> Düşün ki bir restoranda fırını müşteri sipariş vermeden önce ısıtıyorsun. Sipariş gelince hemen pişirmeye başlıyorsun.

`daemon=True` detayı: ana program kapanınca bu thread de otomatik kapanır — zombie thread oluşmaz.

### MockUploadedFile — Veritabanından Dosya Yükleme

```python
class MockUploadedFile:
    """Simulates a Streamlit UploadedFile for files loaded from DB."""
    def __init__(self, name: str, size: int, data: bytes):
        self.name = name
        self.size = size
        self._data = data

    def getvalue(self) -> bytes:
        return self._data

    def read(self) -> bytes:
        return self._data

    def seek(self, pos: int):
        pass  # No-op: getvalue() always returns full content
```

> 💡 **Neden böyle?**
> Kullanıcı geçmiş bir konuşmaya geri dönünce, dosyaları veritabanından yüklüyoruz. Ama kodun geri kalanı Streamlit'in `UploadedFile` nesnesini bekliyor. `MockUploadedFile` aynı arayüzü (interface) taklit ediyor — `name`, `size`, `getvalue()`, `read()`, `seek()`. Kodun geri kalanı farkı anlamıyor.
>
> Bu bir **duck typing** örneği: "Ördek gibi yürüyorsa ve ördek gibi vaklıyorsa, o bir ördektir."

### `reset_session()` — Temiz Başlangıç

```python
def reset_session():
    """Reset all session state for a new conversation."""
    for key in list(st.session_state.keys()):
        if key not in ("user_id",):
            del st.session_state[key]
```

"Yeni Konuşma" butonuna basınca çağrılır. `user_id` hariç her şeyi siler — yeni oturum ID, yeni sandbox, temiz chat geçmişi.

> 🧪 **Kendin dene:**
> Uygulamayı çalıştır, bir dosya yükle, soru sor. Sonra "Yeni Konuşma"ya bas. Dosya ve chat geçmişi sıfırlanır ama önceki konuşma sol panelde "Geçmiş Konuşmalar" altında görünür.

---

## Adım 3: Sandbox Sistemi (`src/sandbox/manager.py`)

### OpenSandbox Nedir?

**OpenSandbox**, Docker container içinde çalışan izole bir Python ortamı. Kullanıcının kodu senin bilgisayarında değil, ayrı bir container'da çalışır. Bu sayede:

- 🛡️ **Güvenlik:** Zararlı kod sisteme zarar veremez
- 📦 **İzolasyon:** Her oturum kendi container'ında çalışır
- 🔄 **Tekrarlanabilirlik:** Aynı paketler, aynı ortam

Bir analoji: Sandbox bir **laboratuvar eldiveni kutusu** (glove box) gibi. İçinde ne yaparsan yap, dışarıyı etkilemez.

### SandboxManager vs OpenSandboxBackend

Bu iki sınıf farklı sorumluluklar taşıyor:

| Sınıf | Rol | Analoji |
|-------|-----|---------|
| `SandboxManager` | Container yaşam döngüsü yönetimi | **Otopark yöneticisi** — arabaları park ettirir |
| `OpenSandboxBackend` | Kod çalıştırma, dosya yükleme/indirme | **Arabanın kendisi** — seni A'dan B'ye götürür |

### Container Oluşturma

```python
def _create_new_sandbox(self, thread_id: str) -> OpenSandboxBackend:
    """Create sandbox container + CodeInterpreter + persistent Python context."""
    sandbox = SandboxSync.create(
        "agentic-sandbox:v1",                          # Docker image adı
        entrypoint=["/opt/opensandbox/code-interpreter.sh"],
        env={"PYTHON_VERSION": "3.11"},
        timeout=timedelta(hours=2),                     # 2 saat sonra otomatik silinir
    )
```

Birkaç kritik detay:
- **`agentic-sandbox:v1`** — özel bir Docker image. pandas, duckdb, weasyprint, matplotlib gibi paketler **önceden kurulu**. Her sorgu için pip install yapmaya gerek yok.
- **`timeout=timedelta(hours=2)`** — 2 saat boyunca kullanılmazsa container silinir. Kaynak tasarrufu.
- **`entrypoint`** — CodeInterpreter shell script'i, Python kernel'ı başlatıyor.

### 🔑 Kalıcı Kernel (Persistent Kernel) — En Önemli Kavram

```python
    interpreter = sandbox.code_interpreter
    py_context = interpreter.codes.create_context(SupportedLanguage.PYTHON)
    self._py_context = py_context
```

**Bu üç satır projenin en kritik tasarım kararını temsil ediyor.**

`py_context` bir **kalıcı Python oturumu**. Normal bir script çalıştırıp kapattığında değişkenler kaybolur. Ama burada:

```python
# Execute çağrısı #1:
df = pd.read_excel('/home/sandbox/data.xlsx')
df = df.dropna(subset=['CustomerID'])
print(f"✅ {len(df):,} satır yüklendi")

# Execute çağrısı #2 (ayrı bir tool call, ama AYNI kernel):
# df HÂLÂ bellekte! Tekrar okumaya gerek yok.
summary = df.groupby('Category')['Revenue'].sum()
print(summary)

# Execute çağrısı #3:
# Hem df hem summary hâlâ burada!
m = {'total': len(df), 'top': summary.idxmax()}
```

> 💡 **Neden böyle?**
> Alternatif ne olurdu? Her execute çağrısında veriyi yeniden okumak. 100MB'lık bir Excel dosyasını 6 kez okumak hem yavaş hem gereksiz.
>
> Jupyter notebook kullandıysan aynı mantık: bir hücrede `df = ...` yazarsın, sonraki hücrelerde `df` hâlâ orada.

**İSTİSNA:** `generate_html()` aracı **ayrı bir process'te** çalışır — Python değişkenlerini göremez. HTML string'ini `execute()` içinde oluşturup literal olarak `generate_html()`'e geçirmen gerekir.

### `execute()` Metodunun İç Çalışması

```python
def execute(self, command: str) -> ExecuteResult:
    """Run code in the persistent Python kernel."""
```

Bu metot gelen komutu analiz eder:

```python
    py_code = self._extract_python_code(command)
    if py_code:
        # Python kodu tespit edildi → base64 kodla → CodeInterpreter'a gönder
        b64 = base64.b64encode(py_code.encode()).decode()
        tmp_path = f"/tmp/_run_{uuid.uuid4().hex[:8]}.py"
        shell_cmd = (
            f"printf '%s' '{b64}' | base64 -d > {tmp_path} "
            f"&& python3 {tmp_path} && rm -f {tmp_path}"
        )
    else:
        shell_cmd = command
```

> 💡 **Neden base64?**
> Python kodu içinde tek tırnak, çift tırnak, yeni satırlar, özel karakterler olabilir. Bunları doğrudan shell komutuna yazmak kabus. Base64 kodlama tüm bu sorunları çözer:
> 1. Kodu base64'e çevir (güvenli ASCII)
> 2. Geçici dosyaya yaz
> 3. Python ile çalıştır
> 4. Geçici dosyayı sil

### `publish_html()` Helper Enjeksiyonu

```python
def _inject_publish_html(self) -> None:
    """Inject publish_html() helper into sandbox kernel."""
    code = """
import json as _json, pathlib as _pathlib

def publish_html(html_str: str) -> None:
    p = _pathlib.Path('/home/sandbox/.artifacts')
    p.mkdir(exist_ok=True)
    idx = len(list(p.glob('artifact_*.html')))
    out = p / f'artifact_{idx}.html'
    out.write_text(html_str, encoding='utf-8')
    print(f'✅ HTML artifact: {out.name}')
"""
```

Bu fonksiyon sandbox kernel'ına **önceden enjekte** ediliyor. Ajan kodunda `publish_html(html_string)` çağırdığında, HTML dosyası sandbox'un disk'ine yazılıyor. Ardından ana uygulama bu dosyayı okuyup iframe içinde render ediyor.

> 🔑 **Anahtar kavram: Factory Pattern**
> Sandbox aracılığıyla hem `execute()`, hem `download_file()`, hem `create_visualization()` çalışıyor. Hepsi aynı `backend` nesnesini paylaşıyor. Bu nedenle her araç bir **factory fonksiyonu** ile oluşturuluyor:
> ```python
> execute_tool = make_execute_tool(backend, session_id)
> download_tool = make_download_file_tool(backend, session_id)
> ```
> Factory pattern sayesinde backend referansı closure ile yakalanıyor ve her araç aynı sandbox'a erişiyor.

### Dosya Yükleme

```python
def upload_files(self, files) -> None:
    """Upload files to the sandbox /home/sandbox/ directory."""
    for f in files:
        f.seek(0)
        self._backend.upload_file(f.getvalue(), f"/home/sandbox/{f.name}")
```

Yüklenen dosyalar sandbox'un `/home/sandbox/` dizinine kopyalanır. Bu yol sabittir — ajan her zaman dosyaları burada arar.

> 🧪 **Kendin dene:**
> Bir Excel dosyası yükle. Logları izle (`logs/app.log`). `"Creating OpenSandbox sandbox"` ve `"Persistent Python context created"` mesajlarını göreceksin.

---

## Adım 4: Skill Sistemi (Progressive Disclosure)

### Progressive Disclosure Nedir?

Bir öğretmenin her derste tüm ders kitabını okutmamasını düşün. Sadece o gün işlenecek konuyu verir. Skill sistemi de aynı mantıkla çalışıyor:

- Kullanıcı `.xlsx` yükledi → Excel kurallarını ver
- Dosya 40MB'dan büyük → DuckDB stratejisini de ver
- İki dosya yüklendi → Multi-file JOIN kurallarını da ver
- Sadece `.csv` yükledi → CSV kurallarını ver, Excel kurallarını verme

Bu yaklaşıma **progressive disclosure** deniyor. Ajana gereksiz bilgi vermek onu yavaşlatır ve hata yapma ihtimalini artırır.

### Registry — Skill Tetikleyiciler (`src/skills/registry.py`)

```python
SKILL_TRIGGERS: list[SkillTrigger] = [
    SkillTrigger(
        name="xlsx",
        extensions=[".xlsx", ".xls", ".xlsm"],
        keywords=["excel", "spreadsheet", "workbook", "çalışma kitabı"],
    ),
    SkillTrigger(
        name="csv",
        extensions=[".csv", ".tsv"],
        keywords=["csv", "comma separated", "tab separated"],
    ),
    SkillTrigger(
        name="pdf",
        extensions=[".pdf"],
        keywords=["pdf", "document"],
    ),
    SkillTrigger(
        name="visualization",
        extensions=[],
        keywords=["chart", "plot", "graph", "grafik", "görsel", "dashboard"],
    ),
]
```

Her `SkillTrigger` iki koşuldan birini kontrol eder:
1. **Dosya uzantısı:** Yüklenen dosyanın uzantısı eşleşiyor mu?
2. **Anahtar kelime:** Kullanıcının sorgusu bu kelimeleri içeriyor mu?

```python
def detect_required_skills(uploaded_files: list, user_query: str = "") -> list[str]:
    """Detect which skills should be loaded based on files + query."""
    active = set()
    extensions = {os.path.splitext(f.name)[1].lower() for f in uploaded_files}
    query_lower = user_query.lower()

    for trigger in SKILL_TRIGGERS:
        # Uzantı eşleşmesi
        if any(ext in extensions for ext in trigger.extensions):
            active.add(trigger.name)
        # Anahtar kelime eşleşmesi
        if any(kw in query_lower for kw in trigger.keywords):
            active.add(trigger.name)

    return sorted(active) or ["xlsx"]  # Varsayılan: xlsx
```

### Reference Dosyaları — Koşullu Yükleme

```python
REFERENCE_TRIGGERS: list[ReferenceTrigger] = [
    ReferenceTrigger(
        skill="xlsx",
        path="skills/xlsx/references/large_files.md",
        condition=lambda files, query: (
            any(f.size >= 40 * 1024 * 1024 for f in files)  # ≥40MB
            or any(kw in query.lower() for kw in ["duckdb", "büyük dosya", "large file"])
        ),
    ),
    ReferenceTrigger(
        skill="xlsx",
        path="skills/xlsx/references/multi_file_joins.md",
        condition=lambda files, query: (
            len(files) >= 2
            or any(kw in query.lower() for kw in ["join", "merge", "birleştir", "eşleştir"])
        ),
    ),
]
```

Reference dosyaları **koşullu** yüklenir:
- `large_files.md` → sadece dosya ≥40MB olduğunda veya "duckdb" kelimesi geçtiğinde
- `multi_file_joins.md` → sadece 2+ dosya yüklendiğinde veya "join"/"birleştir" kelimesi geçtiğinde

> 💡 **Neden böyle?**
> Claude'un context window'u sınırlı (200K token). Her sorguya 1000 satırlık DuckDB rehberini göndermek israf olur. Sadece gerektiğinde yükliyoruz — hem token tasarrufu, hem odaklanmış talimat.

### Loader — Prompt Derleme (`src/skills/loader.py`)

```python
@lru_cache(maxsize=32)
def load_skill(skill_name: str) -> dict | None:
    """Load a SKILL.md file and parse its YAML frontmatter + instructions."""
    skill_path = Path(f"skills/{skill_name}/SKILL.md")
    content = skill_path.read_text(encoding="utf-8")
    # YAML frontmatter'ı ayır: ---\nname: xlsx\n---
    if content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        frontmatter = yaml.safe_load(content[4:end])
        instructions = content[end + 5:]
    else:
        frontmatter, instructions = {}, content
    return {"name": ..., "instructions": instructions, ...}
```

`@lru_cache(maxsize=32)` — aynı skill dosyasını tekrar tekrar diskten okumak yerine bellekte tutuyor. İlk okumadan sonra hızlı.

```python
def compose_system_prompt(base_prompt, active_skills, uploaded_files, user_query):
    """Build system prompt with dynamically loaded skills + reference files."""
    prompt_parts = [base_prompt]

    for skill_name in active_skills:
        skill = load_skill(skill_name)
        prompt_parts.append(f"# {skill['name']} Expertise\n\n{skill['instructions']}")

        # Progressive disclosure: referans dosyalarını koşullu yükle
        ref_paths = detect_reference_files(skill_name, uploaded_files, user_query)
        for ref_path in ref_paths:
            ref_content = load_reference(ref_path)
            prompt_parts.append(f"## {ref_name} (Reference)\n\n{ref_content}")

    return "\n\n".join(prompt_parts)
```

**Sonuç prompt şu formatta birleşir:**

```
[Base System Prompt — ReAct kuralları, genel talimatlar]

# xlsx Expertise
[SKILL.md içeriği — Excel analiz kuralları]

## Large Files (Reference)          ← sadece ≥40MB dosya varsa
[large_files.md içeriği]

## Multi File Joins (Reference)     ← sadece 2+ dosya varsa
[multi_file_joins.md içeriği]
```

### Learner — Otomatik Skill İyileştirme (`src/skills/learner.py`)

Bu dosya projenin en ilginç parçalarından biri. Ajan hata yaptığında **otomatik olarak öğreniyor**:

```
Ajan hata yapıyor
    ↓
LLM-as-judge çıktıyı puanlıyor (Haiku, maliyet düşük)
    ↓
Puan < 0.7 ve skill_issue = true?
    ↓ Evet
Hataları çıkar → Sonnet'e gönder → SKILL.md iyileştirme önerisi al
    ↓
Öneriyi SKILL.md'ye otomatik ekle
    ↓
Sonraki soruda ajan bu kuralı da görecek
```

```python
def auto_learn(user_query, agent_final_response, collected_steps, uploaded_files, threshold=0.7):
    # 1. Çıktıyı puanla
    judge_result = judge_output(user_query, agent_final_response, collected_steps, uploaded_files)

    # 2. Düşük puan + skill sorunu?
    if judge_result.score < threshold and judge_result.skill_issue:
        # 3. Hataları çıkar
        errors = extract_errors(collected_steps)

        # 4. İyileştirme önerisi üret
        suggestion = generate_skill_suggestion(errors, skill_name, user_query)

        # 5. SKILL.md'ye ekle
        _apply_skill_suggestion_auto(suggestion)
```

Bu `auto_learn` fonksiyonu **arka plan thread'inde** çalışır — kullanıcıyı bekletmez:

```python
# chat.py'den:
threading.Thread(
    target=auto_learn,
    kwargs={...},
    daemon=True,
    name="auto_learn",
).start()
```

> 💡 **Neden böyle?**
> Ajan aynı hatayı tekrar tekrar yapıyorsa, bir insanın gelip SKILL.md'yi düzeltmesini beklemek yerine, sistem kendini düzeltiyor. Ama güvenlik önlemleri var:
> - `_MAX_SKILL_FILE_BYTES = 50_000` — SKILL.md 50KB'ı geçerse ekleme yapmaz
> - `_MAX_SUGGESTION_CHARS = 3000` — çok uzun öneriler kesilir
> - `_MIN_SUGGESTION_CHARS = 20` — çok kısa öneriler reddedilir
> - `_REPEAT_OVERRIDE_THRESHOLD = 3` — aynı hata 3 kez tekrarlanırsa zorunlu güncelleme

---

## Adım 5: Araçlar (Tools) — Ajanın Elleri

Ajan tek başına hiçbir şey yapamaz. Düşünür, karar verir, ama **işi araçlar yapar**. Tıpkı bir cerrahın ellerini (araçları) kullanması gibi.

### Araç Genel Bakış

| Araç | Dosya | Ne yapar | Sandbox'a gider mi? |
|------|-------|----------|---------------------|
| `parse_file` | `file_parser.py` | Dosya şemasını çıkarır | ❌ Yerel |
| `execute` | `execute.py` | Python kodu çalıştırır | ✅ Sandbox |
| `generate_html` | `generate_html.py` | HTML dashboard render | ❌ Yerel (iframe) |
| `create_visualization` | `visualization.py` | matplotlib/seaborn PNG | ✅ Sandbox |
| `download_file` | `download_file.py` | Dosya indirme butonu | ✅ Sandbox |

### 1. `parse_file` — Şema Keşfi

```python
@tool
def parse_file(filename: str) -> str:
    """Parse an uploaded file and return its schema summary."""
    # Dosya uzantısına göre parser seç
    ext = os.path.splitext(filename)[1].lower()
    parser = PARSERS.get(ext)  # {".csv": _parse_csv, ".xlsx": _parse_excel, ...}

    target.seek(0)
    data = target.getvalue()
    result = parser(data, filename)
```

**Kritik detay:** Bu araç **sandbox'a gitmez**. Dosya Streamlit'in belleğinde zaten var — yerel olarak parse eder. Bu yüzden `execute` kotasını tüketmez ve çok hızlıdır.

Excel parser'ı özellikle akıllı:

```python
def _parse_excel(file_bytes, filename):
    # openpyxl ile hücre formatlarını oku
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)

    for col in df.columns:
        if dtype in ('datetime64[ns]',):
            # Excel'in hücre format string'ini Python strftime'a çevir
            py_fmt = _excel_numfmt_to_strftime(cell.number_format)
            # Örnek: 'mm/dd/yyyy' → '%m/%d/%Y'
```

Parse sonrası çıktıya eklenen mesaj, ajanı **doğru yola yönlendirir**:

```
✅ PARSE BAŞARILI. SONRAKI ADIM:
❌ YAPMA: ls, cat, os.listdir, parse_file tekrar çağırma
✅ YAP:
1. DÜŞÜNCE yaz: 'Schema alındı. Dosya /home/sandbox/data.xlsx...'
2. execute() çağır:
   df = pd.read_excel('/home/sandbox/data.xlsx')
```

> 💡 **Neden böyle?**
> LLM'ler bazen `ls` veya `os.listdir()` çağırarak dosya sistemi keşfi yapmak ister. Ama sandbox'ta buna gerek yok — dosya yolları zaten biliniyor. Parse çıktısındaki talimat, ajanı gereksiz adımlardan uzak tutarak execute kotasını koruyor.

### 2. `execute` — Kod Çalıştırma

```python
def make_execute_tool(backend: OpenSandboxBackend, session_id: str = ""):
    @tool
    def execute(command: str) -> str:
        """Run Python code or shell command in the sandbox."""
        result = backend.execute(command)
        output = result.output

        # publish_html() çağrısını tespit et → artifact'e ekle
        if "✅ HTML artifact:" in output:
            _collect_html_artifacts(backend, session_id)

        return output
    return execute
```

`execute` aracı sandbox'taki kalıcı kernel'da kod çalıştırır. Önceki execute'larda tanımlanan değişkenler, import'lar ve DataFrame'ler hâlâ bellekte.

**`publish_html()` tespiti:** Kod içinde `publish_html()` çağrıldıysa (çıktıda `"✅ HTML artifact:"` mesajı), sandbox'tan HTML dosyalarını indirip ArtifactStore'a ekler.

**Retry mekanizması:**
```python
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                result = backend.execute(command)
                break
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                return f"Error after {max_retries + 1} attempts: {e}"
```

Ağ hataları veya geçici sorunlarda otomatik yeniden deneme.

### 3. `generate_html` — HTML Dashboard

```python
def make_generate_html_tool(session_id: str = ""):
    @tool
    def generate_html(html_code: str) -> str:
        """Render HTML/CSS/JS in the browser as an interactive artifact."""
        injected = inject_height_script(html_code)
        get_store(session_id).add_html(injected)
        return "HTML rendered successfully in browser iframe."
    return generate_html
```

Bu araç sandbox'a **gitmez**. HTML string'ini doğrudan ArtifactStore'a ekler. Streamlit tarafında `st.components.html()` ile iframe içinde gösterilir.

**Height script enjeksiyonu:**
```javascript
function _reportHeight() {
    const h = document.body.scrollHeight;
    window.parent.postMessage({type: 'streamlit:setFrameHeight', height: h}, '*');
}
```

Bu script iframe'in yüksekliğini içeriğe göre ayarlıyor — kaydırma çubuğu oluşmaz.

> ⚠️ **Önemli fark: `generate_html` vs `publish_html`**
>
> | | `generate_html` | `publish_html` |
> |---|---|---|
> | Nerede çalışır | Ajan thread'inde (yerel) | Sandbox kernel'ında |
> | Değişkenlere erişir mi? | ❌ Hayır | ✅ Evet (kernel değişkenleri) |
> | Ne zaman kullan | Statik HTML, veri bağımsız | Analiz verisiyle dashboard |
> | Örnek | Boş şablon, bilgi sayfası | `m['total']` içeren grafik |

### 4. `create_visualization` — Statik Grafikler

```python
@tool
def create_visualization(code: str) -> str:
    """Generate a static chart (PNG) by running matplotlib/seaborn code in the sandbox."""
    wrapped_code = code + "\nimport matplotlib; matplotlib.pyplot.close('all')"
    exec_result = backend.execute(wrapped_code)

    # /home/sandbox/chart.png dosyasını indir
    responses = backend.download_files([f"{SANDBOX_HOME}/chart.png"])
    get_store(session_id).add_chart(resp.content, code)
```

Sandbox'ta matplotlib/seaborn kodu çalıştırıp PNG çıktıyı indirir. `plt.close('all')` otomatik ekleniyor — bellek sızıntısını önler.

### 5. `download_file` — Dosya İndirme

```python
@tool
def download_file(file_path: str) -> str:
    """Make a file from the sandbox available for the user to download."""
    ALLOWED_PREFIX = SANDBOX_HOME + "/"
    if not file_path.startswith(ALLOWED_PREFIX):
        return f"❌ Only files under {ALLOWED_PREFIX} can be downloaded."

    responses = backend.download_files([file_path])
    # Excel dosyalarında tarih temizliği
    if filename.lower().endswith(('.xlsx', '.xlsm')):
        file_content = _clean_excel_dates(file_content)

    get_store(session_id).add_download(file_content, filename, file_path)
```

İki özel özellik:
1. **Güvenlik:** Sadece `/home/sandbox/` altındaki dosyalar indirilebilir
2. **Excel tarih temizliği:** `_clean_excel_dates()` — datetime sütunlarında tüm değerler gece yarısıysa (`00:00:00`), sadece tarihe çevirir. Excel'de `2024-01-15 00:00:00` yerine `2024-01-15` görünür

### 6. `artifact_store` — Thread-Safe Köprü

```python
class ArtifactStore:
    """Thread-safe storage for artifacts produced by agent tools."""
    def __init__(self):
        self._html: list[str] = []
        self._charts: list[tuple[bytes, str]] = []
        self._downloads: list[tuple[bytes, str, str]] = []
        self._lock = threading.Lock()

    def add_html(self, html: str):
        with self._lock:
            self._html.append(html)

    def pop_html(self) -> list[str]:
        with self._lock:
            items = self._html.copy()
            self._html.clear()
            return items
```

> 💡 **Neden böyle?**
> LangChain ajanı **ayrı bir thread'de** çalışır. Streamlit UI ise **ana thread'de**. İkisi arasında veri aktarmak için `st.session_state` kullanamazsın — thread-safe değil.
>
> `ArtifactStore` bir **global singleton** olarak çalışır:
> ```
> Ajan thread:                     Streamlit thread:
>   execute() → publish_html()
>     ↓
>   ArtifactStore.add_html()       (stream bittikten sonra)
>                                      ↓
>                                  store.pop_html()
>                                      → st.components.html()
> ```
>
> `threading.Lock()` aynı anda iki thread'in listeyi değiştirmesini engeller.

```python
# Global singleton — session_id ile izole
_stores: dict[str, ArtifactStore] = {}
_global_lock = threading.Lock()

def get_store(session_id: str = "") -> ArtifactStore:
    with _global_lock:
        if session_id not in _stores:
            _stores[session_id] = ArtifactStore()
        return _stores[session_id]
```

Her oturum kendi ArtifactStore'una sahip — farklı kullanıcıların artifact'leri karışmaz.

---

## Adım 6: Ajanın Beyni (`src/agent/graph.py`)

Bu dosya projenin **en karmaşık** ve **en önemli** dosyası. 629 satır. Ajanın nasıl kurulduğunu, güvenlik katmanını ve karar mekanizmasını tanımlıyor.

### `build_agent()` — Ajanı İnşa Etmek

```python
def build_agent(sandbox_manager, thread_id, uploaded_files, user_query=""):
    backend = sandbox_manager.get_backend(thread_id)
    session_id = thread_id

    # 1. Araçları oluştur (factory pattern)
    parse_tool = make_parse_file_tool(uploaded_files)
    execute_tool = make_execute_tool(backend, session_id)
    html_tool = make_generate_html_tool(session_id)
    viz_tool = make_visualization_tool(backend, session_id)
    download_tool = make_download_file_tool(backend, session_id)
    tools = [parse_tool, execute_tool, html_tool, viz_tool, download_tool]

    # 2. Skill sistemini çalıştır → prompt derle
    active_skills = detect_required_skills(uploaded_files, user_query)
    system_prompt = compose_system_prompt(
        BASE_SYSTEM_PROMPT, active_skills, uploaded_files, user_query
    )

    # 3. Smart interceptor oluştur (closure ile)
    # ... (aşağıda detaylı)

    # 4. Middleware yığınını kur
    model = resolve_model("anthropic:claude-sonnet-4-20250514")
    middleware = [
        create_summarization_middleware(model, backend),
        AnthropicPromptCachingMiddleware(...),
        PatchToolCallsMiddleware(),
        smart_interceptor,
    ]

    # 5. Ajanı oluştur
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
        checkpointer=checkpointer,
    )

    # 6. Recursion limitini ayarla
    agent = agent.with_config({"recursion_limit": REACT_MAX_ITERATIONS * 2 + 1})
    return agent, checkpointer, reset_interceptor_state
```

### Smart Interceptor — Güvenlik Kalkanı

Smart interceptor, ajanın yaptığı **her tool çağrısını** çalıştırılmadan önce kontrol eden bir middleware. Bir güvenlik görevlisi gibi: "Bu çağrıyı geçirebilir miyim?"

```python
def smart_interceptor(request):
    name = request.tool_calls[0]["name"]
    args = request.tool_calls[0]["args"]
    tool_call_id = request.tool_calls[0]["id"]
```

#### Kural 1: Execute Limiti

```python
    # Dinamik limit: basit sorular → 6, karmaşık → 10
    if name == "execute":
        _execute_count += 1
        if _execute_count > _max_execute:
            return ToolMessage(
                content=f"⛔ Execute limit reached ({_max_execute}). "
                        "Summarize findings and respond to user.",
                tool_call_id=tool_call_id,
            )
```

> 💡 **Neden limit var?**
> LLM'ler bazen sonsuz döngüye girebilir — küçük bir hatayı düzeltmeye çalışırken aynı kodu tekrar tekrar çalıştırır. Limit bunu önler ve maliyeti kontrol altında tutar.

#### Kural 2: Shell Komutları Engelleme

```python
    shell_patterns = [
        r'\bls\b', r'\bfind\b', r'\bcat\b', r'\bhead\b', r'\btail\b',
        r'\bos\.listdir\b', r'\bglob\.glob\b', r'\bos\.walk\b',
    ]
    if name == "execute" and any(re.search(p, cmd) for p in shell_patterns):
        return ToolMessage(
            content="⛔ Shell/filesystem commands BLOCKED. "
                    "File paths are known from parse_file. Use pd.read_excel() directly.",
            tool_call_id=tool_call_id,
        )
```

Ajan `ls`, `find`, `cat` gibi komutlar çalıştırmaya çalışırsa **engellenir**. Dosya yolları `parse_file()`'dan zaten biliniyor — gereksiz dosya sistemi keşfi execute kotasını israf eder.

#### Kural 3: Ağ Erişimi Engelleme

```python
    network_patterns = [
        r'\burllib\b', r'\brequests\b', r'\bwget\b', r'\bcurl\b',
        r'\bhttpx\b', r'\baiohttp\b',
    ]
    if any(re.search(p, cmd) for p in network_patterns):
        return ToolMessage(content="⛔ Network access BLOCKED.", ...)
```

Sandbox'tan dışarıya ağ erişimi engellidir — veri sızıntısını önler.

#### Kural 4: `pip install` Engelleme

```python
    if "pip install" in cmd or "pip3 install" in cmd or "subprocess" in cmd:
        return ToolMessage(
            content="⛔ Package installation BLOCKED. All packages are pre-installed.",
            ...
        )
```

Zararlı paket kurulumunu önler. İhtiyaç duyulan her şey Docker image'da önceden kurulu.

#### Kural 5: Tekrar `parse_file` Engelleme

```python
    if name == "parse_file" and _parse_done:
        return ToolMessage(
            content="⛔ parse_file already called. Use execute() to work with the data.",
            ...
        )
```

#### Kural 6: Circuit Breaker (Devre Kesici)

```python
    _MAX_CONSECUTIVE_BLOCKS = 3
    if name == "execute":
        if _consecutive_blocks >= _MAX_CONSECUTIVE_BLOCKS:
            return ToolMessage(
                content="🛑 CIRCUIT BREAKER: 3 consecutive blocks. "
                        "STOP trying execute. Inform user of the issue.",
                ...
            )
```

Ajan art arda 3 kez engellendiyse, aynı hatayı yapmaya devam etmek yerine kullanıcıya bilgi vermesi isteniyor.

#### Kural 7: Büyük Sampling Engelleme

```python
    sampling_limit = 500
    # .head(1000), .sample(2000), [:5000] gibi kalıpları tespit et
    if n > sampling_limit:
        return ToolMessage(
            content=f"⛔ .head({n}) BLOCKED — remove sampling limit. "
                    "Use pd.read_excel(path) without limits.",
            ...
        )
```

> 💡 **Neden böyle?**
> `.head(1000)` veya `nrows=5000` kullanmak verinin bir kısmını atlıyor. Bu projede **tüm veri** işlenmelidir — aksi halde analiz sonuçları yanlış olur.

#### Kural 8: Font Otomatik Düzeltme (Auto-fix)

```python
    if is_pdf_code:
        # Arial/Helvetica → DejaVu
        for bad_font in ("Arial", "Helvetica"):
            cmd = cmd.replace(f"'{bad_font}'", "'DejaVu'")

        # DejaVu font tanımı yoksa enjekte et
        if "DejaVu" in cmd and "add_font" not in cmd:
            font_setup = (
                "pdf.add_font('DejaVu', '', '/home/sandbox/DejaVuSans.ttf', uni=True)\n"
                "pdf.add_font('DejaVu', 'B', '/home/sandbox/DejaVuSans-Bold.ttf', uni=True)\n"
            )
            cmd = re.sub(r'(pdf\.add_page\(\))', r'\1\n' + font_setup, cmd, count=1)
```

Bu bir **engelleme değil, düzeltme**. LLM sık sık "Arial" fontu kullanır, ama sandbox'ta Arial yok. Interceptor otomatik olarak DejaVu'ya çeviriyor.

#### Kural 9: Hardcoded Metrik Tespiti

```python
    # var = 1234567 gibi sabit değerler tespit et
    hardcoded_vars = re.findall(
        r'^(\w+)\s*=\s*(\d[\d,]*\.?\d*)\s*(?:#.*)?$', cmd, re.MULTILINE
    )
    fabricated = [
        (var, val) for var, val in hardcoded_vars
        if not any(sp in var.lower() for sp in safe_patterns)
        and float(val.replace(',', '')) >= 1000
    ]
    if fabricated:
        return ToolMessage(
            content=f"⛔ Hardcoded metrics detected: {examples}.\n"
                    "These values must be COMPUTED from data.",
            ...
        )
```

> 💡 **Neden böyle?**
> LLM'ler bazen **halüsinasyon** yapar — gerçek veriden hesaplamak yerine, önceki çıktıdan gördüğü sayıları kopyalar. `m = {'total': 4383, 'revenue': 8348208.57}` gibi hardcoded değerler **veri uydurma**dır. Bu kural bunu engelliyor.
>
> `safe_patterns` listesi font_size, margin, padding gibi UI sabitlerine izin veriyor.

#### Execute Sonrası Suffix Ekleme

Her başarılı execute'dan sonra, ajana kalan kota ve bir sonraki adım için talimat eklenir:

```python
    suffix = f"\n\n[Execute {_execute_count}/{_max_execute}, remaining: {remaining}]"
    if remaining <= 2:
        suffix += " ⚠️ Last executes — combine analysis+PDF in single script."
    suffix += "\n💭 Before next step → THOUGHT: [what you observed] → [what you will do] → [why]"
```

Bu suffix ReAct döngüsünü teşvik ediyor — ajan her execute'dan sonra düşünmeye zorlanıyor.

### Ajan Önbellekleme (Agent Caching)

```python
def get_or_build_agent(sandbox_manager, thread_id, uploaded_files, user_query=""):
    file_fingerprint = tuple(
        (f.name, len(f.getvalue())) for f in (uploaded_files or [])
    )

    cached = st.session_state.get("_agent_cache")
    if cached and cached["fingerprint"] == file_fingerprint:
        return cached["agent"], cached["checkpointer"], cached["reset_fn"]

    # Fingerprint değişti → yeni ajan oluştur
    agent, checkpointer, reset_fn = build_agent(...)
    st.session_state["_agent_cache"] = {
        "fingerprint": file_fingerprint,
        "agent": agent, ...
    }
```

**Fingerprint** = dosya adları + boyutları. Aynı dosyalar yüklüyse ajanı yeniden oluşturmaya gerek yok — skill derleme ve model yapılandırma atlanır.

> 🔑 **Anahtar kavram: `reset_interceptor_state()`**
> Her yeni kullanıcı mesajından önce `reset_fn()` çağrılır. Bu, interceptor'ın closure'daki sayaçlarını sıfırlar:
> - `_execute_count = 0`
> - `_consecutive_blocks = 0`
> - `_correction_count = 0`
>
> Bu olmadan, önceki mesajın execute sayısı yeni mesaja taşınırdı.

---

## Adım 7: Sistem Prompt'u (`src/agent/prompts.py`)

Sistem prompt'u, ajanın **anayasası**. 700 satır uzunluğunda ve ajanın davranışını tamamen şekillendiriyor.

### ReAct Döngüsü

```
DÜŞÜNCE → EYLEM → GÖZLEM → KARAR → DÜŞÜNCE → ...
```

ReAct (Reasoning + Acting) bir LLM ajan kalıbıdır. Ajan her adımda:

1. **DÜŞÜNCE (THOUGHT):** "Kullanıcı müşteri başına geliri soruyor. Veriyi okumam gerekiyor."
2. **EYLEM (ACTION):** `execute(df = pd.read_excel(...))`
3. **GÖZLEM (OBSERVATION):** "12.453 satır yüklendi, Customer ID ve Revenue sütunları var."
4. **KARAR (DECISION):** "Veri temiz, şimdi gruplandırma yapabilirim."

> 💡 **Neden ReAct?**
> Alternatif olan "Plan-and-Execute" kalıbında ajan önce tam bir plan yapar, sonra sırayla uygular. Ama veri analizi **keşif amaçlı** — veriyi görene kadar ne yapacağını bilemezsin. ReAct her adımda gözlemleme ve yön değiştirme imkânı veriyor.

### Temel Kurallar

#### 1. Türkçe Yanıt Zorunluluğu

Prompt Türkçe yazılmış ve ajan Türkçe yanıt vermek zorunda. Ama kod ve teknik terimler İngilizce kalabilir.

#### 2. Schema-First Yaklaşımı

```
HER ZAMAN parse_file() ile başla. Veriyi okumadan önce yapısını öğren.
```

Neden? 100MB'lık bir dosyayı okuyup sütun adlarının yanlış olduğunu fark etmek israf. Önce şema bilgisini al, sonra doğru okuma stratejisini belirle.

#### 3. Kernel Güveni (Kernel Trust)

```
KURAL: Kernel'daki değişkenlere GÜVEN. df, m, summary_df gibi
önceki execute'larda oluşturulan değişkenler HÂLÂ bellekte.
Tekrar okuma, tekrar hesaplama YASAK.
```

Bu kural kalıcı kernel'ın gücünü kullanıyor. `df` bir kez yüklendiyse, sonraki tüm execute'larda kullanılabilir.

#### 4. Hardcoded Veri Yasağı

```
⛔ YASAK: m = {'total': 4383, 'revenue': 8348208.57}
✅ DOĞRU: m = {'total': df['ID'].nunique(), 'revenue': (df['Qty'] * df['Price']).sum()}
```

> 💡 **Neden bu kadar önemli?**
> LLM bir önceki execute çıktısında "Toplam: 4.383 müşteri" gördüğünde, PDF üretirken bu sayıyı kopyalamak ister. Ama ya veri temizliği sonrası sayı değiştiyse? Ya da LLM yanlış hatırlıyorsa?
>
> Her metrik **mutlaka koddan hesaplanmalı** — bu garantinin tek yolu.

#### 5. WeasyPrint PDF Formatı

Prompt'ta PDF üretimi için WeasyPrint kullanılması zorunlu tutulmuş. fpdf2 yerine WeasyPrint tercih edilmesinin nedeni: **Türkçe karakter desteği**. HTML + CSS ile PDF üretmek, font sorunlarını ortadan kaldırıyor.

```python
# Prompt'taki PDF şablonu:
html = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>body {{ font-family: Arial, sans-serif; margin: 40px; }}</style>
</head><body>
<h1>Rapor</h1>
<div class="metric">Toplam: <span class="value">{m["total"]:,}</span></div>
</body></html>'''

weasyprint.HTML(string=html).write_pdf('/home/sandbox/rapor.pdf')
```

#### 6. HTML Dashboard — Chart.js

İnteraktif dashboardlar için Chart.js kullanılıyor. Prompt'ta detaylı HTML/CSS/JS şablonları var — KPI kartları, bar chart, line chart.

**Önemli kural:** Dashboard `execute()` içinde `publish_html()` ile oluşturulmalı — `generate_html()` ile değil. Çünkü `publish_html()` kernel değişkenlerine erişebilir, `generate_html()` erişemez.

---

## Adım 8: Kullanıcı Arayüzü (UI)

### `render_chat()` — Ana Akış (`src/ui/chat.py`)

Bu fonksiyon 200+ satır ve tüm sohbet mantığını barındırıyor. Adım adım:

#### 1. Mesaj Geçmişini Göster

```python
messages = st.session_state.get("messages", [])
for i, msg in enumerate(messages):
    with st.chat_message(role):
        # Tool çağrı adımlarını göster
        for step in steps:
            if step["name"] == "execute":
                execute_buffer.append(step)  # Execute'ları birleştir
            else:
                _render_tool_call(tool_name=step["name"], ...)
        # Mesaj içeriğini göster
        if content:
            st.markdown(content)
        # Artifact'leri yeniden render et
        _render_artifacts(html, charts, downloads)
```

Execute çağrıları **konsolide** ediliyor — 6 ayrı execute yerine tek bir genişletilebilir kutu.

#### 2. Kullanıcı Girdisi

```python
user_query = st.chat_input("Ask a question about your data...")
if not user_query:
    return  # Mesaj yoksa hiçbir şey yapma
```

#### 3. Ajan Oluşturma ve Sandbox Bekleme

```python
agent, checkpointer, reset_fn = get_or_build_agent(
    sandbox_manager, session_id, uploaded_files, user_query
)

with st.spinner("⏳ Sandbox hazırlanıyor..."):
    ready = sandbox_manager.wait_until_ready(timeout=180)
```

Pre-warming sayesinde genellikle bekleme olmaz. Ama ilk kez sandbox oluşturuluyorsa 180 saniyeye kadar bekler.

#### 4. Dosyaları Sandbox'a Yükle

```python
if uploaded_files and uploaded_fingerprint != st.session_state.get("_files_uploaded"):
    sandbox_manager.upload_files(uploaded_files)
    st.session_state["_files_uploaded"] = uploaded_fingerprint
```

Fingerprint karşılaştırması sayesinde aynı dosyalar tekrar yüklenmez.

#### 5. Interceptor Sıfırlama

```python
reset_fn()  # _execute_count = 0, _consecutive_blocks = 0, ...
```

#### 6. Ajan Stream'i

```python
with st.chat_message("assistant"):
    for chunk in agent.stream(
        {"messages": [{"role": "user", "content": user_query}]},
        config={"configurable": {"thread_id": session_id}},
        stream_mode="updates",
    ):
        _process_stream_chunk(chunk, rendered_ids, exec_manager)
```

`stream_mode="updates"` sayesinde her LangGraph node çıktısı gerçek zamanlı olarak gelir. `_process_stream_chunk` bu chunk'ları render eder:

- **AI mesajı + tool call:** Tool kartı göster (ikon, isim, girdi)
- **Tool mesajı (çıktı):** Çıktıyı kartta göster (hata varsa kırmızı)
- **AI mesajı (son yanıt):** Markdown olarak göster

#### 7. Artifact Render

```python
# Stream bittikten sonra artifact'leri topla
_store = get_store(session_id)
collected_html = _store.pop_html()
collected_charts = _store.pop_charts()
collected_downloads = _store.pop_downloads()

_render_artifacts(collected_html, collected_charts, collected_downloads)
```

Artifact'ler stream bittikten sonra render edilir — stream sırasında render etmek Streamlit'in güncelleme mekanizmasıyla çakışır.

#### 8. Auto Learn

```python
threading.Thread(
    target=auto_learn,
    kwargs={
        "user_query": user_query,
        "agent_final_response": full_response,
        "collected_steps": collected_steps,
        "uploaded_files": uploaded_files,
    },
    daemon=True,
).start()
```

Arka planda çıktı kalitesini değerlendirir ve gerekirse SKILL.md'yi günceller.

### ExecuteStatusManager — Gerçek Zamanlı Durum

```python
class ExecuteStatusManager:
    """Manages a single consolidated container for execute steps."""
```

Birden fazla execute çağrısı olduğunda, her birini ayrı göstermek yerine tek bir kutu içinde gösteriyor:

```
🐍 Running code...
  ├── ✅ Execute 1/6 — Data loaded
  ├── ✅ Execute 2/6 — Analysis complete
  ├── 🔄 Execute 3/6 — Generating PDF...
  └── ⏳ Execute 4-6 pending
```

### Sidebar — `components.py`

```python
def render_sidebar():
    with st.sidebar:
        # 1. Dosya yükleme widget'ı
        uploaded = st.file_uploader(
            "Upload files",
            type=["csv", "xlsx", "xls", "xlsm", "json", "pdf", "tsv"],
            accept_multiple_files=True,
        )

        # 2. Yüklenen dosya listesi (ikon + boyut + indirme butonu)
        for f in files:
            icon = _get_file_icon(f.name)  # .xlsx → 📗, .csv → 📊
            size = _format_size(f.size)     # 1234567 → "1.2 MB"

        # 3. "Yeni Konuşma" butonu
        if st.button("🔄 New Conversation"):
            reset_session()
            st.rerun()

        # 4. Konuşma geçmişi
        conversations = list_conversations(user_id)
        for conv in past:
            if st.button(label):
                msgs = load_messages(conv["session_id"])
                st.session_state["messages"] = msgs
```

### CSS Stilleri — `styles.py`

413 satır CSS. Önemli öğeler:

- **Tool kartları:** Rounded border, ikon header, koyu çıktı kutusu
- **Execute animasyonu:** `pulse-glow` — mavi nokta nabız gibi atıyor
- **Sidebar:** Koyu arka plan (`#1e293b`), açık metin renkleri
- **Dosya rozeti:** Mavi arka plan, küçük font, ikon + boyut
- **Hata stili:** Kırmızı kenarlık, pembe arka plan

```css
.exec-active-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #0ea5e9;
    animation: pulse-glow 1.5s ease-in-out infinite;
}
```

### Araç İkonları

```python
TOOL_ICONS = {
    "parse_file": "📄",
    "execute": "🐍",
    "generate_html": "🌐",
    "create_visualization": "📊",
    "download_file": "📥",
}
```

---

## Adım 9: Veritabanı (`src/storage/db.py`)

### Veritabanı Seçimi

```python
DATABASE_URL = os.environ.get("DATABASE_URL", "")

if DATABASE_URL:
    # PostgreSQL — production ortamı
    _engine = create_engine(DATABASE_URL)
else:
    # SQLite — yerel geliştirme
    db_path = os.path.join(DATA_DIR, "conversations.db")
    _engine = create_engine(f"sqlite:///{db_path}")
```

`DATABASE_URL` varsa PostgreSQL, yoksa SQLite. Geliştirme sırasında SQLite yeterli.

### Tablo Yapısı

```sql
-- Konuşmalar
CREATE TABLE conversations (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    title       TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Mesajlar
CREATE TABLE messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,           -- 'user' veya 'assistant'
    content     TEXT DEFAULT '',
    steps       TEXT DEFAULT '[]',       -- JSON: tool çağrıları
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dosyalar
CREATE TABLE files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    name        TEXT NOT NULL,
    size        INTEGER NOT NULL,
    data        BLOB NOT NULL,          -- Dosya içeriği (binary)
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Temel İşlemler

```python
def save_message(session_id, role, content, steps=None):
    """Mesajı veritabanına kaydet."""
    # steps JSON olarak saklanıyor: [{"name": "execute", "input": {...}, "output": "..."}]

def load_messages(session_id) -> list[dict]:
    """Bir konuşmanın tüm mesajlarını yükle."""

def save_files(session_id, uploaded_files):
    """Yüklenen dosyaları veritabanına kaydet (binary BLOB)."""

def load_files(session_id) -> list[dict]:
    """Bir konuşmanın dosyalarını yükle → MockUploadedFile ile sarmal."""

def delete_conversation(session_id):
    """Konuşmayı ve ilişkili mesaj/dosyaları sil."""

def list_conversations(user_id) -> list[dict]:
    """Kullanıcının tüm konuşmalarını listele (son güncellenen önce)."""
```

> 💡 **Neden dosyalar da DB'de?**
> Dosyalar BLOB olarak veritabanında saklanıyor. Alternatif: dosya sisteminde saklamak. Ama DB'de saklamanın avantajı: konuşma silinince dosyalar da otomatik silinir, ve konuşma yüklenirken dosyalar da birlikte gelir. Tek kaynak (single source of truth).

> 🧪 **Kendin dene:**
> Uygulamayı çalıştır, bir dosya yükleyip soru sor. Sonra `data/conversations.db` dosyasını bir SQLite istemcisiyle aç:
> ```bash
> sqlite3 data/conversations.db
> .tables
> SELECT session_id, title FROM conversations;
> SELECT role, substr(content, 1, 50) FROM messages WHERE session_id='...';
> ```

---

## Adım 10: Tüm Akış Birlikte (End-to-End)

Şimdi her şeyi birleştirelim. Kullanıcı bir Excel dosyası yükleyip "Bu veriyi analiz et, PDF rapor ver" dediğinde **tam olarak ne oluyor?**

### Senaryo

1. Kullanıcı tarayıcıyı açıyor: `http://localhost:8501`
2. `sales_data.xlsx` dosyasını yüklüyor (25MB, tek sayfa, 50.000 satır)
3. Chat'e yazıyor: *"Müşteri başına ortalama sipariş tutarını hesapla. PDF rapor ver."*

### Akış

```
Zaman   Bileşen            Ne Oluyor
──────  ─────────────────  ────────────────────────────────────────
t=0     app.py              Sayfa yükleniyor, init_session() çalışıyor
t=0.1   session.py          Sandbox ön-ısıtma thread'i başlatılıyor
t=0.5   manager.py          Docker container oluşturuluyor (arka plan)
t=3     manager.py          ✅ Sandbox hazır, CodeInterpreter kernel oluşturuldu
t=5     components.py       Kullanıcı sales_data.xlsx'i sürükleyip bırakıyor
t=5.1   session_state       uploaded_files = [sales_data.xlsx]
t=8     chat.py             Kullanıcı mesajını yazıyor ve Enter'a basıyor
│
│  ┌─── render_chat() başlıyor ───────────────────────────────────
│  │
t=8.1   graph.py            get_or_build_agent() → yeni ajan oluştur
t=8.2   registry.py         detect_required_skills() → ["xlsx"]
t=8.3   loader.py           compose_system_prompt():
│  │                          BASE_PROMPT + xlsx/SKILL.md
│  │                          (25MB < 40MB, large_files.md yüklenmedi)
t=8.5   graph.py            build_agent() → araçlar + interceptor + middleware
t=8.6   manager.py          wait_until_ready() → zaten hazır ✅
t=8.7   manager.py          upload_files() → sales_data.xlsx → /home/sandbox/
t=8.8   graph.py            reset_interceptor_state() → sayaçlar sıfırlandı
│  │
│  │  ┌─── agent.stream() başlıyor ──────────────────────────────
│  │  │
t=9     Claude Sonnet       DÜŞÜNCE: "Dosya yüklendi, şemasını öğrenmeliyim."
t=9.1   Claude              EYLEM: parse_file("sales_data.xlsx")
t=9.2   interceptor         ✅ parse_file izinli (ilk çağrı)
t=9.3   file_parser.py      Yerel parse: 50.000 satır, sütunlar: [OrderID, CustomerID,
│  │  │                      Date, Product, Quantity, Price]
t=9.5   Claude              GÖZLEM: Schema alındı. 50K satır. Tarih formatı: %m/%d/%Y
t=9.6   Claude              KARAR: "Pandas ile okuyabilirim (25MB < 40MB)"
│  │  │
t=10    Claude              DÜŞÜNCE: "Veriyi okuyup temizlemeliyim."
t=10.1  Claude              EYLEM: execute("""
│  │  │                        import pandas as pd
│  │  │                        df = pd.read_excel('/home/sandbox/sales_data.xlsx')
│  │  │                        df = df.dropna(subset=['CustomerID'])
│  │  │                        df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%Y')
│  │  │                        print(f'✅ {len(df):,} satır yüklendi')
│  │  │                      """)
t=10.2  interceptor         ✅ execute #1 izinli, shell/network kalıbı yok
t=10.3  sandbox             Python çalıştır → "✅ 48.721 satır yüklendi"
t=10.5  interceptor         Suffix ekle: "[Execute 1/8, remaining: 7]"
│  │  │
t=11    Claude              GÖZLEM: 48.721 satır temiz veri.
t=11.1  Claude              DÜŞÜNCE: "Müşteri başına sipariş tutarını hesaplamalıyım."
t=11.2  Claude              EYLEM: execute("""
│  │  │                        # df kernel'da hâlâ var!
│  │  │                        df['OrderTotal'] = df['Quantity'] * df['Price']
│  │  │                        customer_stats = df.groupby('CustomerID')['OrderTotal'].agg(
│  │  │                            ['sum', 'count', 'mean']
│  │  │                        )
│  │  │                        m = {
│  │  │                            'total_customers': df['CustomerID'].nunique(),
│  │  │                            'avg_order': customer_stats['mean'].mean(),
│  │  │                            'total_revenue': df['OrderTotal'].sum(),
│  │  │                        }
│  │  │                        print(f'Metriklerin key listesi: {list(m.keys())}')
│  │  │                        print('✅ Doğrulama OK')
│  │  │                      """)
t=11.3  interceptor         ✅ execute #2 izinli, hardcoded metrik yok
t=11.5  sandbox             → "Metriklerin key listesi: ['total_customers', 'avg_order', ...]"
│  │  │
t=12    Claude              GÖZLEM: Metrikler hesaplandı. ✅ Doğrulama OK.
t=12.1  Claude              DÜŞÜNCE: "PDF rapor oluşturmalıyım. m dict ve df kernel'da."
t=12.2  Claude              EYLEM: execute("""
│  │  │                        import weasyprint, os
│  │  │                        html = f'''<!DOCTYPE html>...
│  │  │                          <div>Müşteri Sayısı: {m['total_customers']:,}</div>
│  │  │                          <div>Ortalama Sipariş: {m['avg_order']:,.2f}</div>
│  │  │                        ...'''
│  │  │                        weasyprint.HTML(string=html).write_pdf('/home/sandbox/rapor.pdf')
│  │  │                        assert os.path.exists('/home/sandbox/rapor.pdf')
│  │  │                        print(f'✅ PDF: {os.path.getsize(...)} KB')
│  │  │                      """)
t=12.3  interceptor         ✅ execute #3 izinli
t=12.5  sandbox             → "✅ PDF: 28 KB"
│  │  │
t=13    Claude              EYLEM: download_file('/home/sandbox/rapor.pdf')
t=13.1  download_file.py    Sandbox'tan PDF indir → ArtifactStore'a ekle
│  │  │
t=14    Claude              EYLEM: execute("""  # Dashboard oluştur
│  │  │                        # m ve customer_stats hâlâ kernel'da!
│  │  │                        labels = customer_stats.index[:10].tolist()
│  │  │                        values = customer_stats['sum'][:10].tolist()
│  │  │                        html = f'''<html>...Chart.js...
│  │  │                          const labels = {labels};
│  │  │                          const data = {values};
│  │  │                        ...'''
│  │  │                        publish_html(html)
│  │  │                      """)
t=14.1  interceptor         ✅ execute #4 izinli
t=14.3  sandbox             → "✅ HTML artifact: artifact_0.html"
t=14.4  execute.py          publish_html tespiti → artifact dosyasını indir
│  │  │                      → ArtifactStore.add_html()
│  │  │
t=15    Claude              Son yanıt: "Analiz tamamlandı. Müşteri verileriniz
│  │  │                      incelendi ve PDF rapor hazırlandı..."
│  │  │
│  │  └─── agent.stream() bitti ──────────────────────────────────
│  │
t=15.1  chat.py             exec_manager.finalize() → execute kutusunu kapat
t=15.2  artifact_store      pop_html() → HTML dashboard
│  │                        pop_downloads() → PDF dosyası
t=15.3  chat.py             st.components.html(dashboard)  → iframe render
│  │                        st.download_button("rapor.pdf") → indirme butonu
t=15.5  db.py               save_message() → asistan yanıtını kaydet
t=15.6  learner.py          auto_learn() başlat (arka plan thread)
│  │
│  └─── render_chat() bitti ──────────────────────────────────────
│
t=16    Kullanıcı           PDF'i indiriyor, dashboard'u inceliyor ✨
```

### Sequence Diagram (ASCII)

```
Kullanıcı    Streamlit UI    Agent(Claude)    Interceptor    Sandbox
    │              │               │               │            │
    │──upload──────▶│               │               │            │
    │              │──prewarm──────────────────────────────────▶│
    │              │               │               │      create container
    │              │               │               │            │
    │──"analiz et"─▶│               │               │            │
    │              │──build_agent──▶│               │            │
    │              │  (skills,tools)│               │            │
    │              │──upload_files──────────────────────────────▶│
    │              │──reset_fn()───────────────────▶│            │
    │              │──stream()─────▶│               │            │
    │              │               │               │            │
    │              │               │──parse_file──▶│──check──▶  │
    │              │               │◀──schema───── │            │
    │              │               │               │            │
    │              │               │──execute #1──▶│──check──▶  │
    │              │               │               │──run──────▶│
    │              │◀──status──────│◀──output──────│◀───────────│
    │              │               │               │            │
    │              │               │──execute #2──▶│──check──▶  │
    │              │               │               │──run──────▶│
    │              │◀──status──────│◀──output──────│◀───────────│
    │              │               │               │            │
    │              │               │──execute #3──▶│──check──▶  │
    │              │               │  (PDF üretim) │──run──────▶│
    │              │◀──status──────│◀──output──────│◀───────────│
    │              │               │               │            │
    │              │               │──download_file─────────────▶│
    │              │◀──artifact────│◀──PDF bytes───│◀───────────│
    │              │               │               │            │
    │              │               │──execute #4──▶│──check──▶  │
    │              │               │  (dashboard)  │──run──────▶│
    │              │◀──artifact────│◀──HTML────────│◀───────────│
    │              │               │               │            │
    │              │◀──son yanıt───│               │            │
    │              │               │               │            │
    │◀──render─────│  (iframe + download button)   │            │
    │              │──auto_learn (arka plan)───────▶│            │
    │              │               │               │            │
```

---

## Bonus: Projeyi Geliştirmek İstersen

### 1. Yeni Skill Ekleme

Diyelim ki `.parquet` dosyalarını da desteklemek istiyorsun.

**Adım 1:** `skills/parquet/SKILL.md` oluştur:

```markdown
---
name: parquet
description: "Use when working with .parquet files, Apache Parquet format, columnar storage"
---

# Parquet Processing Expertise

## Reading Parquet Files
\```python
import pandas as pd
df = pd.read_parquet('/home/sandbox/data.parquet')
print(f"Shape: {df.shape}")
\```

## DuckDB with Parquet (Large Files)
\```python
import duckdb
result = duckdb.sql("""
    SELECT * FROM read_parquet('/home/sandbox/data.parquet')
""").df()
\```
```

**Adım 2:** `src/skills/registry.py`'ye trigger ekle:

```python
SkillTrigger(
    name="parquet",
    extensions=[".parquet"],
    keywords=["parquet", "columnar"],
),
```

**Adım 3:** `src/tools/file_parser.py`'ye parser ekle:

```python
def _parse_parquet(file_bytes: bytes, filename: str) -> dict[str, Any]:
    import pandas as pd
    df = pd.read_parquet(io.BytesIO(file_bytes))
    return {
        "type": "parquet",
        "filename": filename,
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "total_rows": len(df),
        "preview": df.head(10).to_string(),
    }

PARSERS[".parquet"] = _parse_parquet
```

**Adım 4:** `src/ui/components.py`'de dosya tipi ekle:

```python
FILE_TYPE_ICONS[".parquet"] = "🔶"
# Ve file_uploader'ın type listesine "parquet" ekle
```

### 2. Yeni Araç Ekleme

Diyelim ki bir `export_to_google_sheets` aracı eklemek istiyorsun.

**Adım 1:** `src/tools/google_sheets.py` oluştur:

```python
from langchain_core.tools import tool

def make_google_sheets_tool(session_id: str = ""):
    @tool
    def export_to_google_sheets(data_json: str, sheet_name: str) -> str:
        """Export analysis results to Google Sheets."""
        # ... Google Sheets API entegrasyonu
        return f"✅ Data exported to Google Sheets: {sheet_name}"
    return export_to_google_sheets
```

**Adım 2:** `src/agent/graph.py`'de `build_agent()` fonksiyonuna ekle:

```python
sheets_tool = make_google_sheets_tool(session_id)
tools = [parse_tool, execute_tool, html_tool, viz_tool, download_tool, sheets_tool]
```

**Adım 3:** `src/ui/styles.py`'de ikon ve etiket ekle:

```python
TOOL_ICONS["export_to_google_sheets"] = "📊"
TOOL_LABELS["export_to_google_sheets"] = "Exporting to Google Sheets"
```

### 3. Yeni Interceptor Kuralı Ekleme

Diyelim ki `time.sleep()` çağrılarını engellemek istiyorsun (sandbox'ı meşgul etmeyi önlemek için).

`src/agent/graph.py`'deki `smart_interceptor` fonksiyonuna ekle:

```python
    # Block time.sleep() calls
    if name == "execute" and "time.sleep" in cmd:
        _execute_count -= 1  # Kotadan düşme
        return ToolMessage(
            content="⛔ time.sleep() BLOCKED — sandbox resources are limited. "
                    "Remove sleep calls and use direct execution.",
            tool_call_id=tool_call_id,
        )
```

**Nereye ekleyeceğini** bilmek önemli: `if name == "execute":` bloğunun içinde, ama `handler(request)` çağrısından **önce**. Çünkü interceptor'ın amacı çalıştırmadan önce kontrol etmek.

**Test:** Ajan `time.sleep(10)` çağırmaya çalıştığında engellenir ve kota tüketilmez.

---

## Adım 11: Production'a Hazırlık — Deployment Rehberi

Bu bölüm, projeyi geliştirme ortamından **production ortamına** taşıyacak ekibin ihtiyaç duyduğu her şeyi kapsar.

### Docker Mimarisi

Production ortamında **4 Docker container** çalışıyor:

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Host                               │
│                                                              │
│  ┌──────────────────┐    ┌──────────────────────────────┐   │
│  │  agentic-app     │    │  opensandbox-server           │   │
│  │  (Streamlit)     │───▶│  (Sandbox yöneticisi)         │   │
│  │  Port: 8501      │    │  Port: 8080                   │   │
│  │  network: host    │    │  network: host                │   │
│  └──────────────────┘    └──────────┬───────────────────┘   │
│                                      │ Docker API            │
│  ┌──────────────────┐    ┌──────────▼───────────────────┐   │
│  │  postgres         │    │  agentic-sandbox:v1          │   │
│  │  (Veritabanı)     │    │  (Kullanıcı kodu çalışır)    │   │
│  │  Port: 5432       │    │  CPU: 1, RAM: 2GB            │   │
│  └──────────────────┘    │  max: 12 eşzamanlı            │   │
│                           └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Neden `network_mode: host`?**
OpenSandbox sunucusu, Docker API ile sandbox container'ları oluşturur. Bu container'lar dinamik portlar alır. `host` ağ modu sayesinde hem Streamlit hem de OpenSandbox aynı ağda — port yönlendirmesine gerek kalmaz.

### Container'lar Detaylı

#### 1. `sandbox-image` — Analiz Ortamı Image'ı

```dockerfile
# Dockerfile.analysis
FROM opensandbox/code-interpreter:v1.0.2

# Paketler önceden kurulu — runtime'da pip install yok
RUN /opt/python/versions/cpython-3.11.14.../bin/python3 -m pip install \
    pandas==2.2.3 \
    openpyxl==3.1.5 \
    matplotlib==3.9.4 \
    weasyprint==62.3 \
    duckdb==1.1.3 \
    ...
```

Bu container **çalışmaz** (`entrypoint: ["true"]`). Sadece image'ı build edip tag'ler (`agentic-sandbox:v1`). OpenSandbox sunucusu bu image'dan sandbox container'lar türetir.

> 💡 **Neden paketler image'da?**
> Her sandbox oluşturulduğunda pip install yapmak ~30 saniye sürer. Image'a bake edince ilk sorgu ~5 saniyeye düşer.

#### 2. `opensandbox-server` — Sandbox Yöneticisi

```dockerfile
# docker/Dockerfile.server
FROM python:3.12-slim
RUN pip install opensandbox-server
ENTRYPOINT ["opensandbox-server"]
```

Yapılandırması `docker/sandbox.toml`'da:

```toml
[server]
host = "127.0.0.1"
port = 8080
api_key = "local-sandbox-key-2024"      # ⚠️ Production'da değiştir!
max_sandbox_timeout_seconds = 86400     # 24 saat max TTL

[docker]
default_image = "agentic-sandbox:v1"
default_cpu = "1"                        # Her sandbox'a 1 CPU
default_memory = "2Gi"                   # Her sandbox'a 2GB RAM
max_sandboxes = 12                       # Eşzamanlı max 12 sandbox
```

Docker socket mount'u zorunlu — OpenSandbox kendi container'larını oluşturmak için Docker API'ye erişir:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

#### 3. `postgres` — Veritabanı

```yaml
postgres:
  image: postgres:16-alpine
  environment:
    POSTGRES_DB: agentic
    POSTGRES_USER: agentic
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-agentic-local-dev}
  volumes:
    - pgdata:/var/lib/postgresql/data    # Kalıcı veri
```

#### 4. `app` — Streamlit Uygulaması

```yaml
app:
  build:
    context: .
    dockerfile: Dockerfile
  env_file: .env
  environment:
    - OPEN_SANDBOX_DOMAIN=127.0.0.1:8080
    - DATABASE_URL=postgresql://agentic:${POSTGRES_PASSWORD}@127.0.0.1:5432/agentic
  volumes:
    - ./logs:/app/logs    # Log dosyaları host'a yazılır
    - ./data:/app/data    # SQLite fallback verisi
```

**Sağlık kontrolü (healthcheck):**
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1
```

Streamlit'in dahili sağlık endpoint'i. Load balancer veya orchestrator bu URL'i kontrol eder.

### Adım Adım Deployment

#### Ön Koşullar

| Gereksinim | Minimum | Önerilen |
|------------|---------|----------|
| **CPU** | 4 çekirdek | 8 çekirdek |
| **RAM** | 8 GB | 16 GB |
| **Disk** | 20 GB | 50 GB (SSD) |
| **Docker** | 24.0+ | En güncel |
| **Docker Compose** | 2.20+ | En güncel |
| **İşletim Sistemi** | Ubuntu 22.04+ | Ubuntu 24.04 LTS |

**RAM hesabı:**
- Streamlit app: ~500MB
- OpenSandbox server: ~200MB
- PostgreSQL: ~200MB
- Her sandbox container: ~2GB × max 12 = 24GB (tam kapasitede)
- Gerçekte: ortalama 2-4 eşzamanlı sandbox → 4-8GB

#### 1. Sunucuyu Hazırla

```bash
# Docker kurulumu (Ubuntu)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Çıkış yap ve tekrar gir (grup değişikliği aktif olsun)

# Docker Compose (v2 plugin olarak gelir)
docker compose version  # 2.20+ olmalı
```

#### 2. Projeyi Klonla

```bash
git clone https://github.com/CYBki/code-execution-agent.git
cd code-execution-agent
```

#### 3. Ortam Değişkenlerini Ayarla

```bash
cp .env.example .env
```

`.env` dosyasını düzenle:

```bash
# ⚠️ ZORUNLU: Anthropic API anahtarı
ANTHROPIC_API_KEY=sk-ant-api03-GERCEK-ANAHTAR-BURAYA

# ⚠️ ZORUNLU: OpenSandbox API anahtarı (sandbox.toml ile aynı olmalı!)
OPEN_SANDBOX_API_KEY=GUCLU-RASTGELE-ANAHTAR-URET

# OpenSandbox sunucu adresi
OPEN_SANDBOX_DOMAIN=localhost:8080

# ⚠️ ZORUNLU: PostgreSQL şifresi (production'da güçlü şifre kullan)
POSTGRES_PASSWORD=GUCLU-SIFRE-BURAYA
```

**API anahtarı eşleştirmesi kritik:**
`OPEN_SANDBOX_API_KEY` değeri ile `docker/sandbox.toml` içindeki `api_key` değeri **aynı olmalı**. Eşleşmezse Streamlit sandbox'a bağlanamaz.

```bash
# sandbox.toml'u da güncelle:
sed -i 's/local-sandbox-key-2024/GUCLU-RASTGELE-ANAHTAR-URET/' docker/sandbox.toml
```

#### 4. Build ve Başlat

```bash
# Tüm image'ları build et (ilk sefer ~5-10 dakika)
docker compose build

# Başlat (arka planda)
docker compose up -d

# Logları izle
docker compose logs -f app
```

#### 5. Doğrulama

```bash
# 1. Tüm container'lar çalışıyor mu?
docker compose ps
# Beklenen: 4 container, hepsi "running" veya "healthy"

# 2. Streamlit sağlık kontrolü
curl -f http://localhost:8501/_stcore/health
# Beklenen: {"status":"ok"}

# 3. OpenSandbox sağlık kontrolü
curl -f http://localhost:8080/health
# Beklenen: 200 OK

# 4. PostgreSQL bağlantısı
docker compose exec postgres pg_isready -U agentic
# Beklenen: "accepting connections"

# 5. Sandbox oluşturma testi
curl -X POST http://localhost:8080/v1/sandboxes \
  -H "OPEN-SANDBOX-API-KEY: $OPEN_SANDBOX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"image":"agentic-sandbox:v1"}'
# Beklenen: JSON response with sandbox ID
```

### Reverse Proxy (Nginx) Yapılandırması

Production'da Streamlit'i doğrudan internete açma. Nginx ile:
- HTTPS (SSL/TLS)
- Rate limiting
- WebSocket proxy (Streamlit gerektiriyor)

```nginx
# /etc/nginx/sites-available/agentic-analyze
upstream streamlit {
    server 127.0.0.1:8501;
}

server {
    listen 443 ssl http2;
    server_name analiz.sirketim.com;

    ssl_certificate     /etc/letsencrypt/live/analiz.sirketim.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/analiz.sirketim.com/privkey.pem;

    # Dosya yükleme limiti (varsayılan 1MB çok düşük)
    client_max_body_size 200M;

    # Rate limiting — IP başına dakikada 60 istek
    limit_req_zone $binary_remote_addr zone=app:10m rate=60r/m;
    limit_req zone=app burst=20 nodelay;

    location / {
        proxy_pass http://streamlit;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket desteği (Streamlit ZORUNLU)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Uzun süreli bağlantılar (analiz zaman alabilir)
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # Statik dosyalar (Streamlit içsel)
    location /_stcore/ {
        proxy_pass http://streamlit;
    }
}

# HTTP → HTTPS yönlendirme
server {
    listen 80;
    server_name analiz.sirketim.com;
    return 301 https://$server_name$request_uri;
}
```

```bash
# Nginx'i etkinleştir
sudo ln -s /etc/nginx/sites-available/agentic-analyze /etc/nginx/sites-enabled/
sudo nginx -t  # Yapılandırmayı kontrol et
sudo systemctl reload nginx

# SSL sertifikası (Let's Encrypt)
sudo certbot --nginx -d analiz.sirketim.com
```

> ⚠️ **Önemli:** `proxy_read_timeout 300s` ayarı kritik. Büyük dosya analizleri 30+ saniye sürebilir. Varsayılan 60 saniyelik timeout, uzun analizlerde bağlantıyı koparır.

---

## Adım 12: İzleme ve Operasyonlar (Monitoring & Ops)

### Log Yapısı

Proje yapılandırılmış JSON loglar üretiyor — log toplama araçlarıyla (ELK, Grafana Loki, Datadog) kolayca entegre olur.

```
logs/
├── app.log          # Tüm loglar (INFO+), JSON formatı, 10MB × 5 rotasyon
├── app_error.log    # Sadece hatalar (WARNING+), JSON formatı
└── audit.log        # Araç çağrı denetim izi (tool call audit trail)
```

**Log format örneği (`app.log`):**
```json
{
  "ts": "2026-04-14T08:52:00.123Z",
  "level": "INFO",
  "logger": "src.agent.graph",
  "msg": "Tool call: execute #3",
  "session_id": "abc-123",
  "tool_name": "execute",
  "execute_num": 3,
  "duration_s": 2.4
}
```

**Audit log örneği (`audit.log`):**
```json
{
  "ts": "2026-04-14T08:52:01.456Z",
  "level": "INFO",
  "logger": "audit",
  "msg": "tool_blocked",
  "tool_name": "execute",
  "action": "hardcoded_metrics",
  "blocked": true,
  "session_id": "abc-123"
}
```

`session_id` ile bir oturumun tüm loglarını filtreleyebilirsin:
```bash
# Belirli bir oturumun tüm loglarını göster
cat logs/app.log | jq 'select(.session_id == "abc-123")'

# Son 1 saatteki engellenen tool çağrılarını say
cat logs/audit.log | jq 'select(.blocked == true)' | wc -l

# Hata oranını izle
cat logs/app_error.log | jq -r '.level' | sort | uniq -c
```

### Console vs JSON Log Seçimi

```bash
# Geliştirmede: okunabilir konsol formatı (varsayılan)
streamlit run app.py

# Production'da: JSON konsol çıktısı (log toplama için)
LOG_JSON=1 streamlit run app.py
```

### Sağlık Kontrolü (Health Check) Endpoint'leri

| Servis | Endpoint | Kontrol |
|--------|----------|---------|
| Streamlit | `http://localhost:8501/_stcore/health` | `{"status":"ok"}` |
| OpenSandbox | `http://localhost:8080/health` | 200 OK |
| PostgreSQL | `pg_isready -U agentic` | "accepting connections" |

**Uptime monitoring script'i:**
```bash
#!/bin/bash
# /opt/scripts/health_check.sh — cron ile 5 dakikada bir çalıştır

check() {
    local name=$1 url=$2
    if ! curl -sf --max-time 5 "$url" > /dev/null 2>&1; then
        echo "[$(date -Iseconds)] ALERT: $name is DOWN" >> /var/log/agentic_health.log
        # Opsiyonel: Slack/email bildirimi
        # curl -X POST "https://hooks.slack.com/..." -d "{\"text\":\"⚠️ $name DOWN\"}"
    fi
}

check "Streamlit"   "http://localhost:8501/_stcore/health"
check "OpenSandbox" "http://localhost:8080/health"
```

```bash
# Cron'a ekle: her 5 dakikada bir
echo "*/5 * * * * /opt/scripts/health_check.sh" | crontab -
```

### Sandbox İzleme ve Temizlik

Sandbox container'ları birikebilir. `cleanup_sandboxes.py` script'i duran container'ları temizler:

```bash
# Durumu kontrol et
python cleanup_sandboxes.py

# Çıktı örneği:
# Found 5 total sandboxes:
# ────────────────────────────
#   [KEEP]   ID: abc123... | State: running  | Thread: session-xyz
#   [DELETE] ID: def456... | State: stopped  | Thread: session-old
#   [DELETE] ID: ghi789... | State: error    | Thread: session-err
#
# Summary:
#   Active:  1
#   Stopped: 2
# Will delete 2 stopped sandbox(es).

# Otomatik onay ile çalıştır (cron için)
python cleanup_sandboxes.py --yes
```

**Cron ile otomatik temizlik:**
```bash
# Her saat başı duran sandbox'ları temizle
0 * * * * cd /path/to/code-execution-agent && /path/to/.venv/bin/python cleanup_sandboxes.py --yes >> /var/log/sandbox_cleanup.log 2>&1
```

**Sandbox kaynak limitleri (`sandbox.toml`):**

| Parametre | Değer | Açıklama |
|-----------|-------|----------|
| `default_cpu` | `"1"` | Her sandbox'a 1 CPU çekirdek |
| `default_memory` | `"2Gi"` | Her sandbox'a 2GB RAM |
| `max_sandboxes` | `12` | Eşzamanlı max sandbox sayısı |
| `max_sandbox_timeout_seconds` | `86400` | Sandbox max yaşam süresi (24 saat) |

> 💡 **Kapasite hesabı:**
> 12 sandbox × 2GB = 24GB RAM (tam kapasitede). Ama genellikle 2-4 eşzamanlı kullanıcı olur → 4-8GB. Sunucu RAM'ini buna göre planla.

### Kritik İzleme Metrikleri

| Metrik | Nereden | Alarm Eşiği |
|--------|---------|-------------|
| Sandbox oluşturma süresi | `app.log` → `"Creating OpenSandbox"` | > 15 saniye |
| Execute süresi | `audit.log` → `duration_s` | > 60 saniye |
| Engellenen tool çağrı oranı | `audit.log` → `blocked: true` | > %30 |
| Hata oranı | `app_error.log` satır sayısı | > 10/saat |
| Aktif sandbox sayısı | `cleanup_sandboxes.py` çıktısı | > 10 (12 limitine yaklaşıyor) |
| Disk kullanımı | `docker system df` | > %80 |
| PostgreSQL bağlantı sayısı | `pg_stat_activity` | > 50 |

---

## Adım 13: Güvenlik Sertleştirme

### Mevcut Güvenlik Katmanları

Proje zaten birçok güvenlik önlemi içeriyor:

```
┌──────────────────────────────────────────────┐
│              Güvenlik Katmanları              │
├──────────────────────────────────────────────┤
│ 1. Smart Interceptor                         │
│    ├── Shell komutu engelleme                │
│    ├── Ağ erişimi engelleme                  │
│    ├── pip install engelleme                 │
│    ├── Dosya sistemi keşfi engelleme         │
│    └── Execute limiti (6-10)                 │
│                                              │
│ 2. Docker İzolasyonu                         │
│    ├── Ayrı container (her oturum)           │
│    ├── CPU/RAM limiti (1 CPU, 2GB)           │
│    ├── 2 saat TTL (otomatik temizlik)        │
│    └── bridge ağ modu (sandbox'lar arası)    │
│                                              │
│ 3. Uygulama Seviyesi                         │
│    ├── API key doğrulama                     │
│    ├── Dosya yolu kısıtlaması (/home/sandbox)│
│    ├── Dosya boyutu limiti (50MB download)    │
│    └── XSRF koruması (Streamlit)             │
└──────────────────────────────────────────────┘
```

### Production İçin Ek Önlemler

#### 1. API Anahtarı Güvenliği

```bash
# ❌ YAPMA: .env dosyasına düz metin
ANTHROPIC_API_KEY=sk-ant-GERCEK-ANAHTAR

# ✅ YAP: Secret manager kullan
# AWS Secrets Manager, HashiCorp Vault, veya Docker secrets
```

**Docker secrets ile:**
```yaml
# docker-compose.yml'e ekle:
secrets:
  anthropic_key:
    file: ./secrets/anthropic_key.txt
  sandbox_key:
    file: ./secrets/sandbox_key.txt

services:
  app:
    secrets:
      - anthropic_key
      - sandbox_key
    environment:
      - ANTHROPIC_API_KEY_FILE=/run/secrets/anthropic_key
```

#### 2. OpenSandbox API Anahtarını Değiştir

```bash
# Güçlü rastgele anahtar üret
openssl rand -base64 32
# Örnek çıktı: aB3dF7gH9jK2mN4pQ6rS8tU0vW1xY3zA

# Bu değeri hem .env hem sandbox.toml'a yaz
```

> ⚠️ **Kritik:** Varsayılan `local-sandbox-key-2024` değerini **kesinlikle** değiştir. Bu değer GitHub'da açık — herkes bilir.

#### 3. Ağ Güvenliği

```bash
# OpenSandbox portunu dışarıya açma (sadece localhost'tan erişilebilir)
# sandbox.toml zaten host = "127.0.0.1" kullanıyor ✅

# PostgreSQL portunu dışarıya açma
# docker-compose.yml'den ports bölümünü kaldır (sadece internal erişim)
```

**Firewall kuralları (ufw):**
```bash
# Sadece gerekli portları aç
sudo ufw allow 443/tcp     # HTTPS (Nginx)
sudo ufw allow 80/tcp      # HTTP → HTTPS redirect
sudo ufw allow 22/tcp      # SSH
sudo ufw enable

# 8501 ve 8080 portlarını AÇMA — Nginx üzerinden erişilecek
```

#### 4. Dosya Yükleme Güvenliği

Streamlit'in `file_uploader`'ı dosya tiplerini sınırlıyor:
```python
type=["csv", "xlsx", "xls", "xlsm", "json", "pdf", "tsv"]
```

Ek olarak Nginx'te `client_max_body_size 200M;` ile dosya boyutunu sınırla.

#### 5. Non-root Kullanıcı

Dockerfile zaten non-root kullanıcı oluşturuyor:
```dockerfile
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser
USER appuser
```

Bu, container içinden host'a sızma riskini azaltır.

---

## Adım 14: Yedekleme ve Felaket Kurtarma

### PostgreSQL Yedekleme

```bash
#!/bin/bash
# /opt/scripts/backup_db.sh

BACKUP_DIR="/backups/postgres"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR"

# Yedek al
docker compose exec -T postgres \
    pg_dump -U agentic -Fc agentic \
    > "$BACKUP_DIR/agentic_${TIMESTAMP}.dump"

# Boyutu kontrol et (boş yedek = sorun var)
if [ ! -s "$BACKUP_DIR/agentic_${TIMESTAMP}.dump" ]; then
    echo "ALERT: Empty backup file!" >> /var/log/backup.log
    exit 1
fi

echo "[${TIMESTAMP}] Backup created: $(du -h "$BACKUP_DIR/agentic_${TIMESTAMP}.dump" | cut -f1)" \
    >> /var/log/backup.log

# Eski yedekleri temizle
find "$BACKUP_DIR" -name "*.dump" -mtime +${RETENTION_DAYS} -delete
```

```bash
# Cron: Her gece 03:00'te yedek al
0 3 * * * /opt/scripts/backup_db.sh
```

### Yedekten Geri Yükleme

```bash
# 1. Mevcut veritabanını durdur
docker compose stop app

# 2. Geri yükle
docker compose exec -T postgres \
    pg_restore -U agentic -d agentic --clean --if-exists \
    < /backups/postgres/agentic_20260414_030000.dump

# 3. Uygulamayı başlat
docker compose start app
```

### Log Yedekleme

Log dosyaları `RotatingFileHandler` ile 10MB × 5 dosya olarak rotasyon yapıyor. Ama production'da uzun süreli saklama için:

```bash
# Logları günlük olarak sıkıştırıp arşivle
0 4 * * * tar -czf /backups/logs/logs_$(date +\%Y\%m\%d).tar.gz /path/to/code-execution-agent/logs/
# 90 günden eski arşivleri sil
0 5 * * * find /backups/logs/ -name "*.tar.gz" -mtime +90 -delete
```

### Tam Sunucu Kurtarma Planı

Sunucu tamamen çökerse:

```
1. Yeni sunucu kur (aynı OS)
2. Docker + Docker Compose kur
3. Projeyi klonla
4. .env dosyasını geri yükle (secret manager'dan)
5. docker compose build && docker compose up -d
6. PostgreSQL yedekten geri yükle
7. Nginx + SSL yapılandırmasını geri yükle
8. Health check'leri doğrula
```

**Tahmini kurtarma süresi:** ~30-45 dakika (hazırlıklıysan)

---

## Adım 15: Sorun Giderme Runbook'u

### Sık Karşılaşılan Sorunlar ve Çözümleri

#### 🔴 Sorun: "Sandbox başlamıyor"

**Belirtiler:** Kullanıcı soru sorduğunda "Sandbox hazırlanıyor..." spinner'ı 180 saniye dönüyor ve timeout oluyor.

**Tanı:**
```bash
# 1. OpenSandbox sunucusu çalışıyor mu?
curl http://localhost:8080/health

# 2. Docker daemon çalışıyor mu?
docker ps

# 3. Disk alanı var mı?
docker system df
df -h

# 4. Sandbox image mevcut mu?
docker images | grep agentic-sandbox

# 5. Max sandbox limitine ulaşıldı mı?
python cleanup_sandboxes.py
```

**Çözümler:**
```bash
# Disk alanı yetersizse:
docker system prune -f           # Kullanılmayan image/container temizle
docker volume prune -f           # Kullanılmayan volume'ları temizle

# Sandbox image yoksa:
docker compose build sandbox-image

# Duran sandbox'lar biriktiyse:
python cleanup_sandboxes.py --yes

# OpenSandbox sunucusu yanıt vermiyorsa:
docker compose restart opensandbox-server
```

#### 🔴 Sorun: "MemoryError" veya sandbox yavaşlıyor

**Belirtiler:** Büyük dosya analizinde (>40MB) sandbox bellek hatası veriyor.

**Tanı:**
```bash
# Sandbox container'ın bellek kullanımını kontrol et
docker stats --no-stream | grep sandbox
```

**Çözümler:**
- `sandbox.toml`'da `default_memory` değerini artır: `"2Gi"` → `"4Gi"`
- Skill sisteminin ≥40MB dosyalar için DuckDB stratejisini önerdiğini doğrula
- `logs/app.log`'da `"BÜYÜK DOSYA"` uyarısını ara

#### 🔴 Sorun: Claude API timeout / rate limit

**Belirtiler:** `anthropic.APITimeoutError` veya `429 Rate Limit Exceeded`

**Tanı:**
```bash
cat logs/app_error.log | jq 'select(.msg | contains("anthropic"))' | tail -5
```

**Çözümler:**
- Rate limit: Anthropic planını yükselt veya istekler arası bekleme ekle
- Timeout: Büyük system prompt'u küçült (gereksiz skill'ler yüklenmiyor mu kontrol et)
- API anahtarının geçerli olduğunu doğrula: `curl -s https://api.anthropic.com/v1/messages -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" -d '{}' | jq .`

#### 🟡 Sorun: PDF'te Türkçe karakterler bozuk

**Belirtiler:** PDF'te `ş`, `ğ`, `ü`, `ı`, `ö`, `ç` yerine `?` veya boş karakterler.

**Çözüm:** Smart interceptor zaten Arial → DejaVu dönüşümü yapıyor. Eğer yine sorun varsa:
```bash
# Sandbox image'da fontlar var mı kontrol et
docker run --rm agentic-sandbox:v1 ls /home/sandbox/DejaVu*.ttf
# Beklenen: DejaVuSans.ttf DejaVuSans-Bold.ttf
```

#### 🟡 Sorun: Konuşma geçmişi kayboluyor

**Belirtiler:** Sayfa yenilenince eski konuşmalar görünmüyor.

**Tanı:**
```bash
# PostgreSQL bağlantısı var mı?
docker compose exec postgres pg_isready -U agentic

# Konuşma verisi var mı?
docker compose exec postgres psql -U agentic -c "SELECT COUNT(*) FROM conversations;"
```

**Çözüm:**
- `DATABASE_URL` ortam değişkeninin doğru ayarlandığını kontrol et
- PostgreSQL container'ının çalıştığını doğrula
- Volume mount'un doğru olduğunu kontrol et (veri kaybını önler)

#### 🟢 Sorun: İlk sorgu yavaş

**Beklenen davranış:** İlk sorgu ~5 saniye (sandbox oluşturma). Sonrakiler ~1-2 saniye.

Eğer ilk sorgu >15 saniye sürüyorsa:
```bash
# Pre-warming çalışıyor mu?
cat logs/app.log | jq 'select(.msg | contains("pre-warm"))'

# Docker image pull yapılıyor mu? (ilk build sonrası olmaz)
docker images | grep agentic-sandbox
```

### Acil Durum Prosedürleri

#### Tam Yeniden Başlatma

```bash
docker compose down          # Tüm container'ları durdur
docker compose up -d         # Yeniden başlat
docker compose logs -f       # Logları izle, hata var mı?
```

#### Belirli Servisi Yeniden Başlat

```bash
docker compose restart app                # Sadece Streamlit
docker compose restart opensandbox-server # Sadece sandbox yöneticisi
docker compose restart postgres           # Sadece veritabanı (dikkat: bağlantılar kesilir)
```

#### Container Loglarını İncele

```bash
docker compose logs --tail=50 app                # Son 50 satır
docker compose logs --since="1h" opensandbox-server  # Son 1 saat
docker compose logs -f postgres 2>&1 | grep ERROR    # Gerçek zamanlı hata filtresi
```

---

## Adım 16: Ölçeklendirme ve Kapasite Planlaması

### Mevcut Limitler

| Parametre | Mevcut Değer | Darboğaz |
|-----------|-------------|----------|
| Eşzamanlı sandbox | 12 | `max_sandboxes` (sandbox.toml) |
| Sandbox RAM | 2GB | `default_memory` (sandbox.toml) |
| Dosya yükleme | 200MB | Streamlit + Nginx limiti |
| Execute kotası | 6-10 / sorgu | Smart interceptor |
| Sandbox TTL | 2 saat | `timeout` (manager.py) |
| Log rotasyonu | 10MB × 5 | `RotatingFileHandler` |

### Eşzamanlı Kullanıcı Tahmini

```
Max sandbox sayısı / Ortalama sandbox kullanım süresi = Eşzamanlı kullanıcı

12 sandbox / ortalama 5 dakika = ~144 sorgu/saat (pikte)
12 sandbox / ortalama 2 dakika = ~360 sorgu/saat (kısa sorgular)
```

**Gerçekçi senaryo:** 5-10 eşzamanlı kullanıcı rahat desteklenir.

### Yatay Ölçekleme (Birden Fazla Sunucu)

Mevcut mimari **tek sunucu** için tasarlanmış. Yatay ölçekleme için:

```
                    ┌────────────┐
                    │ Load       │
                    │ Balancer   │
                    └─────┬──────┘
                 ┌────────┼────────┐
          ┌──────▼──┐  ┌──▼──────┐  ┌──────▼──┐
          │Sunucu 1 │  │Sunucu 2 │  │Sunucu 3 │
          │App+Sandx│  │App+Sandx│  │App+Sandx│
          └────┬────┘  └────┬────┘  └────┬────┘
               └────────────┼────────────┘
                     ┌──────▼──────┐
                     │ PostgreSQL  │
                     │ (paylaşımlı)│
                     └─────────────┘
```

**Gereksinimler:**
1. PostgreSQL → ayrı sunucuda veya managed service (AWS RDS, Cloud SQL)
2. Session sticky'liği → load balancer'da session affinity (sandbox oturumla bağlı)
3. Her sunucu kendi OpenSandbox instance'ını çalıştırır

### Dikey Ölçekleme (Mevcut Sunucuyu Güçlendir)

Daha basit yaklaşım:

```bash
# sandbox.toml'da limitleri artır:
[docker]
default_cpu = "2"        # 1 → 2 CPU
default_memory = "4Gi"   # 2GB → 4GB
max_sandboxes = 24       # 12 → 24

# Sunucu: 16 CPU, 64GB RAM önerilir (24 sandbox × ~3GB)
```

### Maliyet Tahmini

| Kalem | Aylık Tahmin |
|-------|-------------|
| Anthropic API (Claude Sonnet 4) | ~$50-200 (kullanıma bağlı) |
| Sunucu (8 CPU, 32GB RAM) | ~$100-200 (AWS/Hetzner) |
| Disk (50GB SSD) | ~$5-10 |
| **Toplam** | **~$155-410/ay** |

**Claude API maliyet azaltma:**
- Prompt caching middleware zaten etkin — aynı system prompt tekrar gönderildiğinde %90 ucuz
- Execute limiti (6-10) aşırı API çağrısını önlüyor
- Agent caching — aynı dosyalar için ajan yeniden oluşturulmuyor

---

## Adım 17: Bellek Yönetimi — Sessiz Ama Kritik Savunma

Bu proje üç farklı bellek alanını yönetiyor. Her birinde taşma riski var ve her biri için farklı mekanizmalar devreye giriyor.

### 🔑 Üç Bellek Alanı

```
┌───────────────────────────────────────────────────────────────┐
│  1. Sandbox Container (Docker)                                │
│     → Python kernel, DataFrame'ler, matplotlib figürleri      │
│     → En tehlikeli alan: kullanıcı dosya boyutunu kontrol      │
│       edemiyoruz                                              │
│                                                               │
│  2. Streamlit Sunucu (Ana süreç)                              │
│     → session_state, artifact_store, DB bağlantıları          │
│     → İndirilen dosyalar geçici olarak burada tutuluyor       │
│                                                               │
│  3. Disk                                                      │
│     → Log dosyaları, sandbox geçici dosyaları, veritabanı     │
│     → Disk dolması = her şey çöker                            │
└───────────────────────────────────────────────────────────────┘
```

### Alan 1: Sandbox Container Belleği

#### pandas Bellek Çarpanı ve DuckDB

pandas bir Excel dosyası okurken, dosya boyutunun **3-5 katı** RAM kullanır:

| Dosya Boyutu | pandas RAM Kullanımı | Container Limiti (2GB) |
|-------------|---------------------|----------------------|
| 10MB        | ~30-50MB            | %2 — güvenli |
| 40MB        | ~120-200MB          | %10 — sınırda |
| 80MB        | ~240-400MB          | %20 — riskli |
| 200MB       | ~600MB-1GB          | %50 — çökme riski |

**Neden 3-5x?** Her hücre ayrı Python nesnesi olur (string, int, datetime). 10.000 satır × 20 sütun = 200.000 Python nesnesi, her biri ~100-500 byte overhead.

Bu yüzden `parse_file()` dosya boyutunu kontrol eder ve ≥40MB'de uyarı verir:

```python
# file_parser.py — büyük dosya tespiti
if size_mb >= 40:
    output += "⚠️ BÜYÜK DOSYA — DUCKDB STRATEJİSİ ZORUNLU"
```

**DuckDB farkı:** pandas tüm dosyayı RAM'e yükler, DuckDB sadece sorguya gereken sütunları/satırları okur:

```python
# Yanlış — 40MB dosya → ~150MB RAM:
df = pd.read_excel(path)
result = df.groupby('City')['Revenue'].sum()

# Doğru — 40MB dosya → ~10MB RAM:
df = pd.read_excel(path)
df.to_csv('/home/sandbox/temp.csv', index=False)
del df  # ← 150MB serbest bırakıldı!
result = duckdb.sql("SELECT City, SUM(Revenue) FROM read_csv_auto('temp.csv') GROUP BY City").df()
```

> 💡 **`del df` neden kritik?** CSV'ye yazdıktan sonra DataFrame'e artık ihtiyacın yok. `del` olmadan pandas bellekte tutmaya devam eder — DuckDB'nin kullanacağı belleğe ek olarak. İki kopya yerine sıfır kopya.

#### `read_only=True` — openpyxl Bellek Tasarrufu

```python
# file_parser.py — schema okurken
wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
```

`read_only=True` bellek kullanımını **%60-70** azaltır:
- Hücre nesnelerini lazy oluşturur (talep edildikçe)
- Style/font/border bilgisi yüklenmez
- Bize sadece `number_format` lazım — geri kalan gereksiz

> 💡 `download_file.py`'de `read_only=True` **kullanılamaz** çünkü orada hücre değerlerini değiştiriyoruz (datetime → date dönüşümü).

#### `plt.close('all')` — Grafik Bellek Sızıntısını Önleme

```python
# visualization.py — her grafik kodunun sonuna otomatik eklenir
wrapped_code = code + "\nimport matplotlib; matplotlib.pyplot.close('all')"
```

matplotlib figürleri bellekte kalır ve **otomatik silinmez**. 10 grafik × ~5MB = 50MB birikir.

**Neden biz ekliyoruz, ajan yazmıyor?** LLM'ler temizlik kodunu sıklıkla unutur. Kodu sarmalayarak garanti altına alıyoruz — ajan farkında bile olmadan bellek temizleniyor.

**Neden `plt.close('all')` ve sadece `plt.close()` değil?**
- `plt.close()` → sadece aktif figürü kapatır
- `plt.close('all')` → **tüm** figürleri kapatır (kapanmamış eski figürler dahil)

#### Kernel Reset — Timeout Sonrası Bellek Kurtarma

```python
# manager.py — timeout olduğunda
def _reset_context(self):
    self._interpreter.codes.delete_context(old_id)  # Eski kernel'ın TÜM değişkenlerini sil
    self._py_context = self._interpreter.codes.create_context(SupportedLanguage.PYTHON)
```

Timeout olan bir kodun bellekte tuttuğu **her şeyi** temizler. 200MB'lık DataFrame timeout olduysa, `delete_context()` ile tüm namespace serbest bırakılır.

#### `clean_workspace()` — Yeni Konuşma = Temiz Bellek

```python
# manager.py — "Yeni Konuşma" butonunda
def clean_workspace(self):
    self._backend.execute("rm -rf /home/sandbox/* 2>/dev/null")      # Disk temizliği
    self._interpreter.codes.delete_context(self._py_context.id)       # Bellek temizliği
    self._py_context = self._interpreter.codes.create_context(...)    # Temiz kernel
```

Önceki analizin 500MB DataFrame'i tamamen temizlenir. Container **yeniden oluşturulmaz** (5 saniye tasarruf) — sadece bellek ve dosyalar sıfırlanır.

### Alan 2: Streamlit Sunucu Belleği

#### Execute Çıktı Kırpma — `MAX_OUTPUT = 50_000`

```python
# execute.py
MAX_OUTPUT = 50_000
if output and len(output) > MAX_OUTPUT:
    output = output[:MAX_OUTPUT] + f"\n... [truncated, {len(output)} total chars]"
```

`print(df)` ile 50.000 satırlık DataFrame yazdırılırsa = 5MB string.
Bu string → LangChain ToolMessage → Claude API → context window.

50K karakter limiti:
- Yeterince büyük: `df.describe()`, hata mesajları, normal çıktılar sığar
- Yeterince küçük: tüm DataFrame dump'ı engellenir
- Claude'un context window'unu korur (200K token'ın ~%7'si)

#### Dosya İndirme Limiti — `MAX_DOWNLOAD_MB = 50`

```python
# download_file.py
MAX_DOWNLOAD_MB = 50
if len(resp.content) > MAX_DOWNLOAD_MB * 1024 * 1024:
    return f"❌ File too large"
```

İndirilen dosya sunucu RAM'ine yüklenir. 50MB limit olmadan, 200MB CSV dump sunucuyu zorlayabilir.

#### ArtifactStore Pop Pattern — Tüket ve Temizle

```python
# artifact_store.py
def pop_html(self):
    with self._lock:
        items = self._html_items[:]   # Kopyala
        self._html_items.clear()       # Orijinali temizle → bellek serbest
    return items[-1] if items else None
```

Her `generate_html()` çağrısı HTML string'i biriktirir. `pop` pattern'i ile:
1. UI thread artifact'ı alır
2. Store temizlenir → bellek serbest
3. Eğer `get` (temizlemeden okuma) kullansak → oturum boyunca birikir

#### Skill Cache Sınırı — `lru_cache(maxsize=32)`

```python
# loader.py
@lru_cache(maxsize=32)
def load_skill(skill_path: str) -> Optional[str]:
```

~10 skill dosyası var → 32 fazlasıyla yeter. `maxsize=None` (sınırsız) kullansak ve bir bug farklı path'ler üretse → cache sonsuz büyür. `maxsize=32` bunu önler.

### Alan 3: Disk Bellek Yönetimi

#### RotatingFileHandler — Log Dosyası Rotasyonu

```python
# logging_config.py — her 3 log dosyası için aynı ayar
RotatingFileHandler(
    "app.log",
    maxBytes=10 * 1024 * 1024,    # 10MB
    backupCount=5,                 # En fazla 5 yedek
)
```

Nasıl çalışır: `app.log` 10MB dolunca → `app.log.1` → `app.log.2` → ... → `app.log.5` silinir.

**Toplam disk:** 3 dosya × (10MB + 5×10MB) = **180MB maximum** → disk dolması önlenir.

### Alan 4: Thread ve Process Belleği

#### `shutdown(wait=False)` — ThreadPoolExecutor Temizliği

```python
# manager.py — her execute() çağrısında
pool = ThreadPoolExecutor(max_workers=1)
future = pool.submit(...)
try:
    result = future.result(timeout=180)
except TimeoutError:
    pool.shutdown(wait=False)   # ← wait=True olursa SONSUZ BEKLEMEye girer!
    self._reset_context()
```

Her execute'da yeni pool oluşturulur (~1MB). `shutdown(wait=False)` ile hemen temizlenir. `wait=True` kullanılırsa, takılmış thread bitene kadar bekler — ama thread zaten timeout olmuş, bitmeyecek!

#### `wb.close()` — Workbook Kapatma

```python
# download_file.py ve file_parser.py'de
wb.close()  # XML parser cache'leri + hücre nesneleri serbest bırakılır
```

openpyxl Workbook kapatılmazsa, dahili XML parser cache'leri ve hücre referansları garbage collector'ın zamanlamasına kalır.

### Sandbox TTL — Zombie Container Önleme

Sandbox'lar **2 saat TTL** ile oluşturulur. Kullanıcı tarayıcı sekmesini kapatırsa ve Streamlit cleanup çalışmazsa, 2 saat sonra OpenSandbox API container'ı otomatik siler → 2GB RAM geri kazanılır.

### 📊 Bellek Koruma Katmanları Özet Tablosu

| # | Katman | Mekanizma | Ne Koruyor? |
|---|--------|-----------|-------------|
| 1 | Dosya boyutu tespiti | ≥40MB → DuckDB | pandas OOM |
| 2 | `del df` | CSV sonrası serbest bırak | Çift kopya |
| 3 | `read_only=True` | openpyxl lazy load | Schema okuma belleği |
| 4 | `plt.close('all')` | Figür sarmalama | matplotlib leak |
| 5 | `_reset_context()` | Timeout sonrası kernel reset | Takılı kernel belleği |
| 6 | `clean_workspace()` | Yeni konuşma temizliği | Eski veri |
| 7 | `stop()` + `__del__` | Container sonlandırma | Orphan container |
| 8 | `MAX_OUTPUT=50K` | Çıktı kırpma | LLM context + sunucu RAM |
| 9 | `MAX_DOWNLOAD_MB=50` | İndirme limiti | Sunucu RAM |
| 10 | `wb.close()` | Workbook kapatma | XML parser cache |
| 11 | Pop pattern | Tüket ve temizle | Artifact birikimi |
| 12 | `lru_cache(32)` | Sınırlı cache | Skill cache leak |
| 13 | RotatingFileHandler | 10MB × 5 yedek | Disk dolması |
| 14 | `shutdown(wait=False)` | Pool temizliği | Thread belleği |
| 15 | Sandbox TTL | 2 saat auto-delete | Zombie container |

> 🧪 **Kendin dene:** `docker stats` komutuyla sandbox container'ın bellek kullanımını izle. Büyük bir dosya yükle, analiz yap, sonra "Yeni Konuşma"ya bas — bellek kullanımının düştüğünü göreceksin.

---

## Adım 18: Sohbet Hafızası (Conversation Memory) — Agent Nasıl Hatırlıyor?

Agent'a bir soru sordun, cevapladı. Sonra ikinci soruyu sordun — önceki soruyu ve cevabını **hatırlıyor**. Peki bu nasıl çalışıyor? Yeni dosya eklersen ne oluyor? Eski konuşmaya geri dönersen?

### 🔑 Üç Hafıza Katmanı

Sistem üç **bağımsız** hafıza katmanı kullanıyor. Her birinin ömrü ve kapsamı farklı:

```
┌────────────────────────────────────────────────────────────────────────────┐
│  KATMAN                  │ NE HATIRLAR?             │ NE ZAMAN SİLİNİR?   │
├────────────────────────────────────────────────────────────────────────────┤
│  1. LangGraph            │ Tüm mesaj geçmişi        │ "Yeni Konuşma" →     │
│     Checkpointer         │ (user + AI + tool)        │  yeni thread_id      │
│                          │                           │                      │
│  2. Sandbox Kernel       │ Python değişkenleri       │ "Yeni Konuşma" →     │
│     (Kalıcı Kernel)      │ (df, m, imports)          │  clean_workspace()   │
│                          │                           │                      │
│  3. Veritabanı           │ Mesajlar + dosyalar       │ Kullanıcı silene     │
│     (SQLite/PostgreSQL)  │ (kalıcı arşiv)            │  kadar KALIR         │
└────────────────────────────────────────────────────────────────────────────┘
```

### Katman 1: LangGraph Checkpointer — "Agent Ne Konuştuğunu Hatırlıyor"

Bu, ajanın **konuşma hafızası**. Her mesaj (kullanıcı sorusu, ajan yanıtı, tool çıktıları) bir `thread_id` altında disk'e kaydedilir.

```python
# graph.py — checkpointer oluşturma
def _get_checkpointer():
    if database_url.startswith("postgresql"):
        return PostgresSaver.from_conn_string(database_url)  # Production
    else:
        return SqliteSaver(sqlite3.connect("data/checkpoints.db"))  # Development
```

**Nasıl çalışır?**

```
Turn 1: "Veriyi analiz et"
  → agent.stream(..., config={"thread_id": "abc-123"})
  → Claude yanıt verir, tüm mesajlar checkpointer'a kaydedilir

Turn 2: "Müşteri segmentasyonu yap"  
  → agent.stream(..., config={"thread_id": "abc-123"})  ← AYNI thread_id!
  → Checkpointer Turn 1'in TÜM mesajlarını yükler
  → Claude GÖRÜR: [Turn 1 mesajları] + [Turn 2 sorusu]
  → Claude HATIRLAR: "df'yi önceki turda yükledim, bellekte"
```

**`thread_id` = `session_id`:** Her konuşma benzersiz bir `session_id` alıyor. Bu ID hem checkpointer'a hem sandbox'a veriliyor — böylece hafızalar aynı konuşmayı takip ediyor.

> 💡 **Checkpointer olmasaydı?** Claude her turda sadece yeni mesajı görürdü. Önceki analizi, hangi dosyayı yüklediğini hatırlamazdı. Her seferinde sıfırdan başlardı.

#### Summarization Middleware — Uzun Konuşmaları Yönetmek

10 turlu bir konuşma = 50+ mesaj. Her mesajda kod çıktıları var. Toplamda yüz binlerce token → Claude'un context window'unu aşar.

```python
# graph.py — middleware zincirindeki İLK middleware
middleware = [
    create_summarization_middleware(model, backend),  # ← Eski mesajları özetler
    AnthropicPromptCachingMiddleware(...),
    PatchToolCallsMiddleware(),
    smart_interceptor,
]
```

Eski turların detaylı tool çıktıları kaldırılır, yerine kısa özet konur. Son 2-3 turn tam bırakılır (Claude'un ne yaptığını detaylı bilmesi gerekiyor).

### Katman 2: Sandbox Kernel — "Agent Veriyi Hatırlıyor"

Bu, kalıcı kernel kavramı — daha önce Adım 3'te detaylı anlattık. Ama hafıza bağlamında farklarını görelim:

| Özellik | Checkpointer | Kernel |
|---------|-------------|--------|
| Ne saklar? | Mesaj metinleri | Python değişkenleri (df, m) |
| Nerede? | Disk (SQLite/PostgreSQL) | Container RAM |
| Claude görür mü? | EVET | HAYIR (sadece koddan bilir) |
| Sayfa yenilenince? | ✅ Kalır | ✅ Kalır (container çalışıyor) |
| "Yeni Konuşma"da? | ❌ Yeni thread | ❌ Kernel sıfırlanır |
| Eski konuşma yüklenince? | ✅ Geçmiş geri gelir | ❌ df YOK! |

> 💡 **Kritik fark:** Eski konuşmaya döndüğünde, Claude mesaj geçmişinden "df yükledim" bilir ama kernel'da df yoktur. İlk execute'da `NameError` alır → düzeltme döngüsüyle otomatik tekrar yükler.

### Katman 3: Veritabanı — Kalıcı Arşiv

```python
# chat.py — her mesaj iki yere kaydedilir
st.session_state["messages"].append({"role": "user", "content": query})  # RAM (UI)
save_message(session_id, "user", query)                                    # Disk (DB)
```

DB'deki mesajlar **sonsuza kadar** kalır. Kenar çubuğundan eski konuşmaları yükleyebilirsin:

```python
# components.py — eski konuşma yükleme
msgs = load_messages(conv["session_id"])       # DB'den mesajları yükle
st.session_state["messages"] = msgs             # UI'a koy
st.session_state["session_id"] = conv["session_id"]  # Checkpointer thread_id'yi ayarla
saved_files = load_files(conv["session_id"])   # Dosyaları da geri yükle
```

### 4 Farklı Senaryo — Ne Zaman Ne Olur?

#### Senaryo 1: Aynı konuşmada ardışık sorular ✅

```
Turn 1: "Veriyi yükle" → df bellekte, mesajlar checkpointer'da
Turn 2: "Analiz yap"   → Claude Turn 1'i hatırlıyor, df hâlâ bellekte
Turn 3: "PDF yap"      → Claude Turn 1-2'yi hatırlıyor, df + m bellekte
```

**Her şey çalışıyor** — en sorunsuz senaryo.

#### Senaryo 2: Yeni dosya eklendi (aynı konuşma) ✅

```
Turn 1-3: sales.xlsx ile analiz
Kullanıcı: customers.csv ekliyor (sidebar'dan)
Turn 4: "İki dosyayı birleştir"
```

Ne olur:
1. `file_fingerprint` değişti → **ajan yeniden oluşturulur** (yeni system prompt, yeni skill'ler)
2. Ama `thread_id` AYNI → **checkpointer eski mesajları korur**
3. Kernel de AYNI → **df hâlâ bellekte**
4. Yeni skill'ler yüklendi (multi_file_joins.md — 2 dosya olduğu için otomatik)
5. Claude: "sales.xlsx'i daha önce analiz ettim, şimdi customers.csv de var, birleştireyim"

> 💡 **Ajan neden yeniden oluşturuluyor?** Yeni dosya farklı tip olabilir (CSV vs Excel) → farklı skill'ler gerekir. System prompt'a yeni dosya bilgisi eklenmeli. Ama konuşma sıfırlanmaz.

#### Senaryo 3: "Yeni Konuşma" butonuna basıldı 🔄

```python
reset_session():
    st.session_state["messages"] = []           # UI temiz
    st.session_state["session_id"] = yeni_uuid  # Yeni checkpointer thread
    st.session_state.pop("_agent_cache")        # Ajan yeniden oluşturulacak
    mgr.clean_workspace()                        # Kernel + dosyalar sıfırlandı
```

**Her şey sıfırlanır** — ama eski konuşma DB'de kalır (kenar çubuğundan geri dönülebilir).

#### Senaryo 4: Eski konuşma kenar çubuğundan yüklendi ⚠️

```
Geri gelen: Mesajlar ✅, dosyalar ✅, checkpointer geçmişi ✅
Geri gelmeyen: Kernel değişkenleri ❌, artifact'lar (HTML/chart) ❌
```

İlk soru sorulduğunda:
1. Claude: "df var sanıyorum" → execute → `NameError: df is not defined`
2. Claude: "Kernel sıfırlanmış" → `df = pd.read_excel(...)` → devam
3. 1 execute "kaybedilir" ama akış otomatik düzelir (correction loop)

### Interceptor State Reset — Turn Bazlı Sıfırlama

```python
# graph.py — her yeni soru ÖNCE çağrılır
def reset_interceptor_state():
    _execute_count = 0       # Yeni kota
    _total_blocked = 0       # Blok sayacı sıfır
    _consecutive_blocks = 0  # Ardışık blok sayacı sıfır
    _seen_parse_files.clear() # Parse geçmişi temiz
```

Bu neden gerekli? Ajan cache'lendiğinden interceptor'ın closure değişkenleri iki turn arasında yaşar. Turn 1'de 6 execute kullandıysan ve sıfırlamazsan, Turn 2'de ilk execute'da "limit reached" hatası alırsın.

**Neyi sıfırlıyoruz, neyi koruyoruz?**
- ✅ **Sıfırlanan:** execute sayacı, blok sayacı, parse geçmişi (turn-scoped)
- ❌ **Korunan:** kernel değişkenleri, checkpointer mesajları, dosyalar (session-scoped)

### Prompt Caching — Maliyet Hafızası

```python
AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore")
```

Aynı system prompt tekrar gönderildiğinde Anthropic cache'den okur → **%90 daha ucuz**. Konuşma hafızası değil ama her turn'de system prompt'u yeniden göndermek yerine cache'den okumak büyük maliyet tasarrufu.

### Mesaj Tekrarı Önleme — `_rendered_ids`

```python
# chat.py — stream sırasında
if msg_id and msg_id in rendered_ids:
    continue  # Bu mesaj zaten gösterildi, ATLA
rendered_ids.add(msg_id)
```

LangGraph stream'i, checkpointer'dan önceki mesajları da döndürebilir. `_rendered_ids` set'i ile aynı mesajın iki kez render edilmesi önlenir.

### 📊 Hafıza Özet Tablosu

| Eylem | Checkpointer | Kernel | DB | UI |
|-------|-------------|--------|-----|-----|
| Aynı konuşmada yeni soru | Eski mesajlar + yeni | Değişkenler duruyor | Yeni mesaj eklenir | Tüm mesajlar görünür |
| Yeni dosya ekleme | Korunur (aynı thread) | Korunur (aynı container) | Dosya kaydedilir | Ajan yeniden oluşturulur |
| "Yeni Konuşma" | Yeni thread (sıfır) | Sıfırlanır | Yeni conversation | Ekran temiz |
| Eski konuşma yükleme | Eski thread geri | ⚠️ df YOK | Mesajlar + dosyalar yüklenir | Eski mesajlar görünür |
| Sayfa yenileme (F5) | Kalır (disk'te) | Kalır (container çalışıyor) | Kalır | session_state'den geri yüklenir |

> 🧪 **Kendin dene:** Bir dosya yükle, 3 soru sor. Sonra "Yeni Konuşma"ya bas, başka bir dosya yükle. Kenar çubuğundan eski konuşmaya dön — mesajların geri geldiğini ama ilk execute'da df'nin tekrar yüklendiğini gözlemle.

---

## 🎓 Sonuç

Bu tutorial boyunca şunları öğrendin:

**Geliştirici olarak (Adım 0-10 + Bonus):**
1. **Projenin ne yaptığını** ve teknoloji yığınını
2. **app.py'den** uygulamanın nasıl başladığını
3. **Session state** ile Streamlit'te durumun nasıl korunduğunu
4. **Sandbox sisteminin** Docker ile nasıl izolasyon sağladığını
5. **Kalıcı kernel** kavramını ve neden devrim niteliğinde olduğunu
6. **Skill sisteminin** progressive disclosure ile nasıl çalıştığını
7. **Araçların** factory pattern ile nasıl oluşturulduğunu
8. **Smart interceptor'ın** güvenlik ve kalite nasıl sağladığını
9. **Sistem prompt'unun** ajanın davranışını nasıl şekillendirdiğini
10. **UI katmanının** stream, artifact ve geçmiş yönetimini
11. **Veritabanının** konuşma ve dosya persistansını
12. **Tüm akışın** uçtan uca nasıl çalıştığını

**Production ekibi olarak (Adım 11-18):**
13. **Docker mimarisi** — 4 container, nasıl bağlantılı, neden host network
14. **Adım adım deployment** — sunucu hazırlama, build, doğrulama
15. **Nginx reverse proxy** — HTTPS, WebSocket, rate limiting
16. **İzleme** — JSON loglar, health check, sandbox temizlik, kritik metrikler
17. **Güvenlik sertleştirme** — API key yönetimi, firewall, non-root container
18. **Yedekleme** — PostgreSQL dump, log arşivleme, felaket kurtarma planı
19. **Sorun giderme** — 6 yaygın sorun ve çözüm prosedürleri
20. **Ölçeklendirme** — kapasite hesabı, dikey/yatay ölçekleme, maliyet tahmini
21. **Bellek yönetimi** — 15 koruma katmanı: sandbox, sunucu, disk, thread belleği
22. **Sohbet hafızası** — 3 katmanlı hafıza: checkpointer, kernel, DB + 4 senaryo

Bu proje, modern AI mühendisliğinin birçok ileri kalıbını bir araya getiriyor:
- **ReAct ajanlar** (düşün → yap → gözlemle)
- **Sandbox izolasyonu** (güvenli kod çalıştırma)
- **Progressive disclosure** (bilgi yükünü azalt)
- **LLM-as-judge** (otomatik kalite değerlendirme)
- **Self-improving skills** (otomatik öğrenme)

Artık sadece **kullanıcı** değil, hem **geliştirici** hem **DevOps mühendisi** olarak bu projeye katkı sağlayabilirsin. 🚀

---

> 📝 **Bu belge** CYBki/code-execution-agent deposu için hazırlanmıştır.
> Her adım, gerçek kaynak koduna dayanarak yazılmıştır.
