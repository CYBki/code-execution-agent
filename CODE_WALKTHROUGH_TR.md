# 🛠️ CODE_WALKTHROUGH_TR.md — Projeyi Sıfırdan Yazıyoruz

> **Bu doküman nedir?** Projeyi sanki sıfırdan, adım adım yazıyormuşsun gibi anlatıyor.
> Her bölümde açıklamayı oku, sonra 🔗 linkine tıkla ve GitHub'da ilgili kodu gör.
> Okumaya devam et, sonraki linke tıkla — böylece projeyi baştan sona "yazmış" olursun.

**Repo:** [CYBki/code-execution-agent](https://github.com/CYBki/code-execution-agent)

---

## İçindekiler

| # | Bölüm | Ne Yazıyoruz? |
|---|-------|---------------|
| 0 | [Proje İskeleti](#bölüm-0-proje-i̇skeleti) | Dizin yapısı, bağımlılıklar |
| 1 | [Konfigürasyon](#bölüm-1-konfigürasyon--api-anahtarları) | API anahtarı çözümleme |
| 2 | [Logging Altyapısı](#bölüm-2-logging-altyapısı) | JSON loglar, audit trail |
| 3 | [Veritabanı Katmanı](#bölüm-3-veritabanı-katmanı) | SQLite/PostgreSQL, şema |
| 4 | [Sandbox Yöneticisi](#bölüm-4-sandbox-yöneticisi) | Docker container, kalıcı kernel |
| 5 | [Artifact Store](#bölüm-5-artifact-store) | Thread-safe veri köprüsü |
| 6 | [Araçlar (Tools)](#bölüm-6-araçlar-tools) | parse_file, execute, generate_html, download_file, visualization |
| 7 | [Skill Sistemi](#bölüm-7-skill-sistemi) | Progressive disclosure, tetikleme |
| 8 | [Sistem Prompt'u](#bölüm-8-sistem-promptu) | ReAct döngüsü, kurallar |
| 9 | [Ajan Beyni](#bölüm-9-ajan-beyni--agentgraphpy) | build_agent, smart interceptor |
| 10 | [Kullanıcı Arayüzü](#bölüm-10-kullanıcı-arayüzü) | Streamlit UI, streaming |
| 11 | [Giriş Noktası](#bölüm-11-giriş-noktası--apppy) | Her şeyi birleştiriyoruz |
| 12 | [Uçtan Uca Akış](#bölüm-12-uçtan-uca-akış) | Tam senaryo |

---

## Bölüm 0: Proje İskeleti

Bir projeye başlarken ilk yapacağın şey dizin yapısını kurmak. İşte bu projenin iskeleti:

```
code-execution-agent/
├── app.py                          ← Giriş noktası (Streamlit)
├── pyproject.toml                  ← Bağımlılıklar
├── src/
│   ├── utils/
│   │   ├── config.py               ← API anahtarı çözümleme
│   │   └── logging_config.py       ← JSON log sistemi
│   ├── storage/
│   │   └── db.py                   ← Veritabanı (SQLite/PostgreSQL)
│   ├── sandbox/
│   │   └── manager.py              ← Docker sandbox yaşam döngüsü
│   ├── tools/
│   │   ├── artifact_store.py       ← Thread-safe veri köprüsü
│   │   ├── file_parser.py          ← Dosya şeması çıkarma
│   │   ├── execute.py              ← Kod çalıştırma
│   │   ├── generate_html.py        ← HTML dashboard render
│   │   ├── download_file.py        ← Dosya indirme
│   │   └── visualization.py        ← Grafik üretimi
│   ├── skills/
│   │   ├── registry.py             ← Skill tetikleme kuralları
│   │   └── loader.py               ← Prompt derleme
│   ├── agent/
│   │   ├── prompts.py              ← Sistem prompt'u (696 satır!)
│   │   └── graph.py                ← Ajan oluşturucu + smart interceptor
│   └── ui/
│       ├── session.py              ← Oturum yönetimi
│       ├── components.py           ← Kenar çubuğu
│       ├── styles.py               ← CSS stilleri
│       └── chat.py                 ← Sohbet arayüzü + streaming
└── skills/
    ├── xlsx/SKILL.md               ← Excel analiz kuralları
    ├── csv/SKILL.md                ← CSV analiz kuralları
    ├── pdf/SKILL.md                ← PDF analiz kuralları
    └── visualization/SKILL.md      ← Görselleştirme kuralları
```

> 💡 **Neden bu sırayla yazıyoruz?** Bağımlılık ağacını takip ediyoruz: altta yatan
> katmanları (config, logging, DB) önce yaz, sonra sandbox, sonra araçlar, sonra ajan,
> en son UI. Her katman yalnızca altındakilere bağımlı.

---

## Bölüm 1: Konfigürasyon — API Anahtarları

Her projenin ilk ihtiyacı: API anahtarlarını güvenli şekilde okumak. Biz bunu tek bir
fonksiyonla çözüyoruz.

### 1.1 `get_secret()` — Tek Fonksiyon, İki Kaynak

🔗 [**src/utils/config.py** — Tam dosya (23 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/utils/config.py)

```python
def get_secret(key: str) -> str:
    """Resolve a secret value with priority: st.secrets → os.environ → raise."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        value = os.getenv(key)
        if not value:
            raise ValueError(f"'{key}' not found...")
        return value
```

**Mantık basit:** Önce Streamlit Cloud'un `st.secrets` deposuna bak (production).
Bulamazsan `os.environ`'a düş (lokal geliştirme — `.env` dosyasından yüklenir).
İkisinde de yoksa hata fırlat.

> 💡 **Neden böyle?** Streamlit Cloud'da `secrets.toml` kullanılır. Lokal'de `.env`
> dosyası. Tek fonksiyon ikisini de destekliyor — kod tarafı hangi ortamda
> çalıştığını bilmek zorunda değil.

---

## Bölüm 2: Logging Altyapısı

Production'da "bir şey çalışmıyor" dediğinde tek silahın loglar. Biz JSON formatında
yapılandırılmış loglar yazıyoruz.

### 2.1 `SessionContext` — Oturum Korelasyonu

🔗 [**src/utils/logging_config.py:25-45** — SessionContext sınıfı](https://github.com/CYBki/code-execution-agent/blob/main/src/utils/logging_config.py#L25-L45)

```python
class SessionContext:
    """Thread-local storage for session_id correlation."""
    _local = threading.local()

    @classmethod
    def set(cls, session_id: str):
        cls._local.session_id = session_id
```

Her kullanıcı oturumunun bir `session_id`'si var. Bu sınıf o ID'yi thread-local
değişkende tutuyor. Log yazıldığında otomatik olarak ekleniyor — böylece hangi logun
hangi kullanıcıya ait olduğunu hemen görürsün.

### 2.2 `JSONFormatter` — Yapılandırılmış Log Çıktısı

🔗 [**src/utils/logging_config.py:50-81** — JSONFormatter sınıfı](https://github.com/CYBki/code-execution-agent/blob/main/src/utils/logging_config.py#L50-L81)

Her log satırı şöyle bir JSON objesi oluyor:

```json
{"ts":"2026-04-14T08:52:00.123Z","level":"ERROR","logger":"src.sandbox.manager",
 "msg":"execute failed: timeout","session_id":"abc-123"}
```

Formatter `SessionContext`'ten `session_id`'yi alıp her loga ekliyor. Ayrıca
`tool_name`, `action`, `blocked`, `duration_s` gibi ek alanları da destekliyor —
bunlar audit logları için kritik.

### 2.3 `setup_logging()` — Üç Katmanlı Log Sistemi

🔗 [**src/utils/logging_config.py:95-147** — setup_logging fonksiyonu](https://github.com/CYBki/code-execution-agent/blob/main/src/utils/logging_config.py#L95-L147)

Üç handler var:

| Handler | Dosya | Seviye | Format |
|---------|-------|--------|--------|
| Console | stdout | INFO+ | İnsan-okunur (geliştirme) |
| app.log | `logs/app.log` | INFO+ | JSON (10MB × 5 rotasyon) |
| app_error.log | `logs/app_error.log` | WARNING+ | JSON (10MB × 5 rotasyon) |

### 2.4 `get_audit_logger()` — Araç Denetim İzi

🔗 [**src/utils/logging_config.py:150-169** — Audit logger](https://github.com/CYBki/code-execution-agent/blob/main/src/utils/logging_config.py#L150-L169)

Her araç çağrısı (execute, parse_file, vb.) ayrı bir `audit.log` dosyasına yazılıyor.
`propagate = False` ayarı sayesinde audit logları `app.log`'a düşmüyor — bağımsız
analiz yapabilirsin.

> 💡 **Neden ayrı audit log?** Bir kullanıcının kaç execute çağrısı yaptığını,
> hangilerinin engellendiğini görmek istediğinde `app.log`'u grep'lemek yerine
> doğrudan `audit.log`'a bakarsın. `jq` ile anında analiz yapabilirsin.

---

## Bölüm 3: Veritabanı Katmanı

Kullanıcı sayfayı yenilediğinde konuşma geçmişi kaybolmasın diye bir veritabanına
ihtiyacımız var.

### 3.1 Çift Backend Desteği

🔗 [**src/storage/db.py:54-84** — Bağlantı ve yardımcı fonksiyonlar](https://github.com/CYBki/code-execution-agent/blob/main/src/storage/db.py#L54-L84)

```python
def _get_conn():
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgresql"):
        import psycopg2
        return psycopg2.connect(database_url)
    else:
        return sqlite3.connect(DB_PATH, check_same_thread=False)
```

`DATABASE_URL` varsa PostgreSQL, yoksa SQLite. İki veritabanının SQL farklılıklarını
iki küçük fonksiyon hallediyor:

```python
def _ph(n: int = 1) -> str:
    """Placeholder: %s (PostgreSQL) veya ? (SQLite)"""
    return ", ".join(["%s"] * n) if _is_pg() else ", ".join(["?"] * n)

def _now_expr() -> str:
    """Şimdiki zaman: NOW() (PG) veya datetime('now') (SQLite)"""
    return "NOW()" if _is_pg() else "datetime('now')"
```

> 💡 **Neden ikisi birden?** Lokal geliştirmede SQLite yeterli — sıfır kurulum.
> Production'da PostgreSQL — çok kullanıcılı, yedeklenebilir, ölçeklenebilir.
> Aynı kod ikisinde de çalışıyor.

### 3.2 Veritabanı Şeması

🔗 [**src/storage/db.py:96-170** — init_db() ve tablo tanımları](https://github.com/CYBki/code-execution-agent/blob/main/src/storage/db.py#L96-L170)

Üç tablo:

```
conversations          messages               files
├── session_id (PK)    ├── id (PK)            ├── id (PK)
├── user_id            ├── session_id (FK)    ├── session_id (FK)
├── title              ├── role               ├── filename
├── created_at         ├── content            ├── size
└── updated_at         ├── steps (JSON)       ├── file_data (BLOB)
                       └── created_at         └── created_at
```

`steps` kolonu JSON olarak saklanıyor — ajan hangi araçları çağırdı, ne girdi verdi,
ne çıktı aldı. Bu sayede geçmiş konuşmayı yüklerken araç çağrılarını da geri
gösterebiliyoruz.

### 3.3 CRUD Operasyonları

🔗 [**src/storage/db.py:173-355** — save/load/delete fonksiyonları](https://github.com/CYBki/code-execution-agent/blob/main/src/storage/db.py#L173-L355)

Temel fonksiyonlar:

| Fonksiyon | Ne yapıyor? |
|-----------|-------------|
| `create_conversation()` | Yeni konuşma oluştur |
| `save_message()` | Mesajı kaydet (steps JSON olarak) |
| `load_messages()` | Konuşma geçmişini yükle |
| `save_files()` | Yüklenen dosyaları DB'ye kaydet (BLOB) |
| `load_files()` | Dosyaları DB'den geri yükle |
| `delete_conversation()` | Konuşma + mesajlar + dosyaları sil |
| `list_conversations()` | Kullanıcının tüm konuşmalarını listele |

> 🔑 **Anahtar kavram:** Dosyalar BLOB olarak veritabanında saklanıyor. Bu sayede
> kullanıcı sayfayı yenilediğinde veya geçmiş konuşmaya döndüğünde dosyalar hâlâ mevcut.

---

## Bölüm 4: Sandbox Yöneticisi

Burası projenin kalbi. Kullanıcının kodu nerede çalışıyor? İzole bir Docker container
içinde. Bu bölümde o container'ı yönetiyoruz.

### 4.1 Sabitler ve Yardımcı Sınıflar

🔗 [**src/sandbox/manager.py:1-50** — Import'lar, sabitler, regex, result sınıfları](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L1-L50)

```python
SANDBOX_HOME = "/home/sandbox"
```

Tüm dosyalar bu dizinde yaşıyor. Fontlar, kullanıcı dosyaları, üretilen raporlar —
hepsi `/home/sandbox/` altında.

İki önemli sabit daha:

```python
_PYFILE_RE = re.compile(
    r"printf '%s' '([A-Za-z0-9+/=\s]+)' \| base64 -d > (/tmp/_run_[a-f0-9]+\.py)"
)
```

Bu regex, `execute.py`'nin ürettiği base64-kodlanmış Python dosya kalıbını tanıyor.
Eşleşirse → Python kodu, persistent kernel'da çalıştır. Eşleşmezse → shell komutu,
doğrudan `commands.run()` ile çalıştır.

`_ExecuteResult` ve `_DownloadResult` sınıfları eski arayüzle uyumluluğu sağlıyor —
araçlar (execute.py, download_file.py) bu sınıfların `.output` ve `.content`
alanlarını kullanıyor.

### 4.2 `OpenSandboxBackend` — Kalıcı Kernel

🔗 [**src/sandbox/manager.py:52-189** — OpenSandboxBackend sınıfı](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L52-L189)

Bu sınıf projenin en kritik konseptini barındırıyor: **kalıcı kernel (persistent kernel)**.

```python
class OpenSandboxBackend:
    def __init__(self, sandbox, interpreter, py_context):
        self._sandbox = sandbox
        self._interpreter = interpreter
        self._py_context = py_context  # Kalıcı Python çalıştırma bağlamı
```

`py_context` bir CodeInterpreter bağlamı. Bu bağlamda çalıştırdığın her Python kodu
aynı bellek alanını paylaşıyor. Yani:

```python
# Execute #1: df artık bellekte
df = pd.read_excel('/home/sandbox/data.xlsx')

# Execute #2: df HÂLÂ bellekte — tekrar okumaya gerek YOK
result = df.groupby('Category')['Revenue'].sum()
```

> 🔑 **Anahtar kavram: Kalıcı Kernel.** Değişkenler, import'lar, DataFrame'ler —
> hepsi `execute()` çağrıları arasında hayatta kalır. Pickle/serialization'a gerek yok.
> Bu, projenin performansını dramatik şekilde artırıyor.

### 4.3 `execute()` — Python mu, Shell mi?

🔗 [**src/sandbox/manager.py:96-155** — execute metodu](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L96-L155)

`execute()` metodunun karar ağacı:

```
Gelen komut → _PYFILE_RE regex'i eşleşiyor mu?
  ├─ EVET → base64 decode → codes.run(py_code, context=py_context)  [kalıcı kernel]
  └─ HAYIR → sandbox.commands.run(command)                          [shell komutu]
```

Python kodu kalıcı kernel'da çalışıyor (değişkenler yaşar), shell komutları ise
doğrudan container'da çalışıyor (rm, echo, cat gibi).

**Timeout mekanizması:**

```python
pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
future = pool.submit(self._interpreter.codes.run, py_code, context=self._py_context)
try:
    result = future.result(timeout=timeout)  # 180 saniye
except concurrent.futures.TimeoutError:
    self._reset_context()  # Takılan kernel'ı sıfırla
```

`codes.run()` kendi içinde timeout desteklemiyor. Biz `ThreadPoolExecutor` ile
sarmalayıp dışarıdan timeout veriyoruz. Timeout olursa `_reset_context()` yeni bir
kernel bağlamı oluşturuyor — takılan bağlamı silip temiz bir başlangıç yapıyor.

### 4.4 `_reset_context()` — Takılan Kernel'ı Kurtarma

🔗 [**src/sandbox/manager.py:75-94** — _reset_context metodu](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L75-L94)

```python
def _reset_context(self):
    old_id = getattr(self._py_context, "id", None)
    if old_id:
        try:
            self._interpreter.codes.delete_context(old_id)
        except Exception:
            pass  # Takılı bağlam silinmeyebilir — sorun değil
    self._py_context = self._interpreter.codes.create_context(SupportedLanguage.PYTHON)
```

Eski bağlamı sil (başarısız olabilir, sorun değil), yenisini oluştur. Sonraki
`execute()` çağrıları bu temiz bağlamda çalışacak.

### 4.5 `SandboxManager` — Yaşam Döngüsü Yönetimi

🔗 [**src/sandbox/manager.py:192-346** — SandboxManager sınıfı](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L192-L346)

Bu sınıf sandbox'un tüm yaşam döngüsünü yönetiyor:

**Oluşturma:**

🔗 [**src/sandbox/manager.py:222-269** — _create_new_sandbox](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L222-L269)

```python
sandbox = SandboxSync.create(
    "agentic-sandbox:v1",                              # Docker image
    entrypoint=["/opt/opensandbox/code-interpreter.sh"], # CodeInterpreter başlat
    env={"PYTHON_VERSION": "3.11"},
    timeout=timedelta(hours=2),                         # 2 saat TTL
)
interpreter = CodeInterpreterSync.create(sandbox)
py_context = interpreter.codes.create_context(SupportedLanguage.PYTHON)
```

Sandbox oluşturulduktan sonra `publish_html()` helper'ı kernel'a enjekte ediliyor:

🔗 [**src/sandbox/manager.py:247-258** — publish_html enjeksiyonu](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L247-L258)

```python
_INIT_CODE = (
    "def publish_html(html_str):\n"
    "    with open('/home/sandbox/__dashboard__.html', 'w', encoding='utf-8') as f:\n"
    "        f.write(html_str)\n"
    "    print('__PUBLISH_HTML__')\n"
)
interpreter.codes.run(_INIT_CODE, context=py_context)
```

Bu fonksiyon kernel'ın içinde yaşıyor. Ajan `publish_html(html)` çağırdığında HTML
dosyaya yazılıyor ve `__PUBLISH_HTML__` marker'ı basılıyor. `execute.py` bu marker'ı
yakalayıp HTML'i artifact store'a yönlendiriyor.

**Temizleme (Yeni Konuşma):**

🔗 [**src/sandbox/manager.py:296-324** — clean_workspace](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L296-L324)

```python
def clean_workspace(self):
    # Dosyaları temizle
    self._backend.execute("rm -rf /home/sandbox/* 2>/dev/null; ...")
    # Kernel bağlamını sıfırla (değişkenler sıfırlanır)
    self._interpreter.codes.delete_context(self._py_context.id)
    self._py_context = self._interpreter.codes.create_context(SupportedLanguage.PYTHON)
```

Container'ı öldürmüyoruz — sadece dosyaları siliyor ve kernel bağlamını sıfırlıyoruz.
Yeni container oluşturmak ~5 saniye, bağlam sıfırlamak ~0.1 saniye. Büyük fark.

> 💡 **Neden container'ı yeniden oluşturmuyoruz?** Sandbox oluşturma ~5 saniye sürüyor.
> "Yeni Konuşma" tıklamasında 5 saniye beklemek kötü UX. Bunun yerine aynı container'ı
> tutup sadece dosyaları ve kernel'ı sıfırlıyoruz — çok daha hızlı.

---

## Bölüm 5: Artifact Store

Şimdi kritik bir sorunumuz var: Ajan araçları (execute, generate_html, vb.)
**thread pool** içinde çalışıyor. Ama Streamlit UI **ana thread'de**. Bu iki thread
nasıl konuşacak?

### 5.1 Problem: Thread Güvenliği

Streamlit'in `st.session_state`'i thread-safe değil. Ajan thread'inden
`st.session_state["downloads"].append(...)` yapamazsın — race condition olur.

### 5.2 Çözüm: `ArtifactStore`

🔗 [**src/tools/artifact_store.py** — Tam dosya (89 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/artifact_store.py)

```python
class ArtifactStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._pending_downloads: list[dict] = []
        self._pending_charts: list[dict] = []
        self._pending_html: list[str] = []

    def add_download(self, file_bytes, filename, path=""):
        with self._lock:
            if any(d["filename"] == filename for d in self._pending_downloads):
                return  # Dedup: aynı dosya zaten beklemede
            self._pending_downloads.append({...})

    def pop_downloads(self):
        with self._lock:
            items = self._pending_downloads[:]
            self._pending_downloads.clear()
            return items
```

**Akış:**

```
Ajan thread'i:                    Streamlit thread'i:
  execute() → PDF üret
  download_file()
    → ArtifactStore.add_download()
                                  (stream bittikten sonra)
                                    → store.pop_downloads()
                                    → st.download_button() render et
```

### 5.3 Per-Session Store Yönetimi

🔗 [**src/tools/artifact_store.py:73-89** — Global store yönetimi](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/artifact_store.py#L73-L89)

```python
_stores: dict[str, ArtifactStore] = {}
_stores_lock = threading.Lock()

def get_store(session_id: str) -> ArtifactStore:
    with _stores_lock:
        if session_id not in _stores:
            _stores[session_id] = ArtifactStore()
        return _stores[session_id]
```

Her oturumun kendi store'u var. `_stores_lock` ile store oluşturma da thread-safe.
Oturum sıfırlandığında `release_store()` ile temizleniyor.

> 💡 **Neden global singleton?** Ajan araçları factory fonksiyonlarla oluşturuluyor.
> Her aracın `session_id`'si var. `get_store(session_id)` ile kendi oturumunun
> store'una erişiyor. Streamlit tarafı da aynı `session_id` ile erişiyor. İkisi
> aynı nesneye ulaşıyor ama `threading.Lock` sayesinde race condition yok.

---

## Bölüm 6: Araçlar (Tools)

Ajan dünyayla araçları aracılığıyla etkileşiyor. 5 araç var, hepsi **factory pattern**
ile oluşturuluyor.

> 🔑 **Factory Pattern neden?** Her araç bir `backend` referansına ve `session_id`'ye
> ihtiyaç duyuyor. Factory fonksiyon bu değerleri closure'da yakalıyor. Böylece
> LangChain aracı çağırdığında sadece `execute(command="...")` diyor — backend
> referansı otomatik olarak orada.

### 6.1 `parse_file` — Dosya Şeması Çıkarma

🔗 [**src/tools/file_parser.py** — Tam dosya (327 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/file_parser.py)

Bu araç **sandbox'a gitmiyor**. Dosyayı doğrudan Python'da (sunucu tarafında)
ayrıştırıyor. Neden? Hız. Sandbox round-trip ~2 saniye, lokal ayrıştırma ~0.1 saniye.

**Factory fonksiyon:**

🔗 [**src/tools/file_parser.py:237-327** — make_parse_file_tool](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/file_parser.py#L237-L327)

```python
def make_parse_file_tool(uploaded_files: list | None = None):
    _files = uploaded_files  # Closure'da yakala

    @tool
    def parse_file(filename: str) -> str:
        uploaded_files = _files  # Thread-safe: st.session_state'e dokunma
        # ... dosyayı bul, parse et, sonuç döndür
    return parse_file
```

**Dosya türü algılama:**

🔗 [**src/tools/file_parser.py:226-234** — PARSERS sözlüğü](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/file_parser.py#L226-L234)

```python
PARSERS = {
    ".csv": _parse_csv,
    ".tsv": _parse_tsv,
    ".xlsx": _parse_excel,
    ".xls": _parse_excel,
    ".xlsm": _parse_excel,
    ".json": _parse_json,
    ".pdf": _parse_pdf,
}
```

Her parser kendi dosya türüne özel bilgi döndürüyor:
- **Excel:** Sheet listesi, her sheet'in kolonları, veri tipleri, tarih formatları
- **CSV:** Kolon tipleri, satır sayısı, önizleme
- **PDF:** Sayfa sayısı, tablo sayısı, metin önizlemesi

**Excel tarih formatı tespiti — akıllı dokunuş:**

🔗 [**src/tools/file_parser.py:38-72** — _excel_numfmt_to_strftime](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/file_parser.py#L38-L72)

Excel'de tarihler sayı olarak saklanır ama "görüntüleme formatı" farklı olabilir
(MM/DD/YYYY vs DD.MM.YYYY). Biz openpyxl ile hücrenin `number_format`'ını okuyoruz
ve Python'un `strftime` formatına çeviriyoruz. Ajan bu bilgiyle tarihleri doğru
formatta gösteriyor.

**Büyük dosya uyarısı:**

🔗 [**src/tools/file_parser.py:314-322** — DuckDB uyarısı](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/file_parser.py#L314-L322)

```python
if size_mb >= 40:
    output += "⚠️ BÜYÜK DOSYA — DUCKDB STRATEJİSİ ZORUNLU..."
```

40MB üstü dosyalar için pandas yerine DuckDB kullanılması gerektiğini ajana bildiriyor.

### 6.2 `execute` — Kod Çalıştırma

🔗 [**src/tools/execute.py** — Tam dosya (165 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/execute.py)

Bu araç ajanın "elleri" — analiz kodu çalıştırıyor, PDF üretiyor, dashboard
oluşturuyor.

**Python kodu tespiti — iki yol:**

🔗 [**src/tools/execute.py:35-51** — _extract_python_code](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/execute.py#L35-L51)

```python
# Yol 1: python3 -c "..." kalıbı
_PY_INLINE_RE = re.compile(r"""^python3?\s+-c\s+(['"])(.*)\1\s*$""", re.DOTALL)

# Yol 2: Ham Python kodu (python3 -c prefix'i olmadan)
_PY_STARTS = ("import ", "from ", "print(", "def ", "df ", "pd.", "np.", ...)
```

Ajan bazen `python3 -c "..."` yazıyor, bazen doğrudan Python kodu gönderiyor.
İkisini de yakalıyoruz.

**Base64 kodlama — neden?**

🔗 [**src/tools/execute.py:92-97** — Base64 kodlama](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/execute.py#L92-L97)

```python
if py_code:
    b64 = base64.b64encode(py_code.encode()).decode()
    tmp_path = f"/tmp/_run_{uuid.uuid4().hex[:8]}.py"
    shell_cmd = f"printf '%s' '{b64}' | base64 -d > {tmp_path} && python3 {tmp_path}"
```

Python kodu tırnak, parantez, yeni satır gibi shell'i bozan karakterler içerebilir.
Base64'e çevirip dosyaya yazıyoruz — shell escaping sorunları tamamen ortadan kalkıyor.

**Retry mekanizması:**

🔗 [**src/tools/execute.py:99-124** — Bağlantı retry](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/execute.py#L99-L124)

Container IP çözümleme bazen başarısız olabiliyor. 2 deneme hakkı var, araya 1 saniye
bekleme koyuluyor.

**`publish_html()` otomatik tespiti:**

🔗 [**src/tools/execute.py:142-158** — Publish HTML algılama](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/execute.py#L142-L158)

```python
if output and _HTML_MARKER in output:  # "__PUBLISH_HTML__"
    html_result = backend.execute(f"cat {_HTML_PATH}")
    get_store(session_id).add_html(inject_height_script(html_content))
    backend.execute(f"rm -f {_HTML_PATH}")
```

Ajan kodu içinde `publish_html(html)` çağırdığında:
1. HTML dosyaya yazılır (`/home/sandbox/__dashboard__.html`)
2. `__PUBLISH_HTML__` marker'ı stdout'a basılır
3. `execute.py` bu marker'ı yakalar
4. HTML'i dosyadan okur, height script enjekte eder, artifact store'a koyar
5. Geçici dosyayı siler

### 6.3 `generate_html` — HTML Dashboard Render

🔗 [**src/tools/generate_html.py** — Tam dosya (57 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/generate_html.py)

Bu araç doğrudan HTML alıp artifact store'a koyuyor.

**Height script enjeksiyonu:**

🔗 [**src/tools/generate_html.py:9-31** — HEIGHT_SCRIPT ve inject](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/generate_html.py#L9-L31)

```python
HEIGHT_SCRIPT = """
<script>
  function _reportHeight() {
    const h = document.body.scrollHeight;
    window.parent.postMessage({type: 'streamlit:setFrameHeight', height: h}, '*');
  }
  ...
</script>
"""
```

Streamlit'in `components.html()` iframe kullanıyor. İçerik yüklendikten sonra
iframe'in yüksekliğini otomatik ayarlamak gerekiyor — bu script tam bunu yapıyor.
`postMessage` ile Streamlit'e "benim yüksekliğim X piksel" diyor.

**Factory fonksiyon:**

🔗 [**src/tools/generate_html.py:34-57** — make_generate_html_tool](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/generate_html.py#L34-L57)

```python
def make_generate_html_tool(session_id: str = ""):
    @tool
    def generate_html(html_code: str) -> str:
        injected = inject_height_script(html_code)
        get_store(session_id).add_html(injected)
        return "HTML rendered successfully in browser iframe."
    return generate_html
```

### 6.4 `download_file` — Dosya İndirme

🔗 [**src/tools/download_file.py** — Tam dosya (110 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/download_file.py)

**Güvenlik kontrolü:**

🔗 [**src/tools/download_file.py:78-80** — Path güvenliği](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/download_file.py#L78-L80)

```python
ALLOWED_PREFIX = SANDBOX_HOME + "/"
if not file_path.startswith(ALLOWED_PREFIX):
    return f"❌ Only files under {ALLOWED_PREFIX} can be downloaded."
```

Sadece `/home/sandbox/` altındaki dosyalar indirilebilir. Ajan `/etc/passwd` gibi
sistem dosyalarına erişemez.

**Excel tarih temizleme — kullanıcı dostu dokunuş:**

🔗 [**src/tools/download_file.py:17-62** — _clean_excel_dates](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/download_file.py#L17-L62)

```python
def _clean_excel_dates(content: bytes) -> bytes:
    # Tüm değerler gece yarısı (00:00:00) ise → sadece tarih göster
    if all_midnight:
        for c in cells_with_dates:
            c.value = c.value.date()        # datetime → date
            c.number_format = 'YYYY-MM-DD'
```

pandas DateTime'ları Excel'e yazarken otomatik olarak `2024-01-15 00:00:00` şeklinde
yazıyor. Ama kullanıcı sadece `2024-01-15` görmek istiyor. Bu fonksiyon indirme
sırasında otomatik temizlik yapıyor.

### 6.5 `create_visualization` — Statik Grafikler

🔗 [**src/tools/visualization.py** — Tam dosya (60 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/visualization.py)

```python
def make_visualization_tool(backend, session_id):
    @tool
    def create_visualization(code: str) -> str:
        wrapped_code = code + "\nimport matplotlib; matplotlib.pyplot.close('all')"
        exec_result = backend.execute(wrapped_code)
        responses = backend.download_files([f"{SANDBOX_HOME}/chart.png"])
        get_store(session_id).add_chart(resp.content, code)
```

Matplotlib kodu sandbox'ta çalıştırılıyor → `chart.png` üretiliyor → indirilip
artifact store'a konuluyor → UI'da gösteriliyor.

`plt.close('all')` her zaman ekleniyor — bellek sızıntısını önlemek için.

> 💡 **`generate_html` vs `create_visualization`:** İnteraktif dashboard istiyorsan
> (Chart.js, Plotly.js) → `generate_html`. Statik PNG grafik istiyorsan (matplotlib,
> seaborn) → `create_visualization`. İkisi farklı kullanım senaryoları için var.

---

## Bölüm 7: Skill Sistemi

Şimdi ilginç bir sorun var: Her dosya türü için farklı kurallar lazım. Excel
dosyasıyla PDF dosyası aynı şekilde analiz edilmez. Ama tüm kuralları her zaman
sistem prompt'una eklemek prompt'u gereksiz şişirir.

Çözüm: **Progressive Disclosure** — ihtiyaç duyulduğunda yükle.

### 7.1 Skill Kayıt Defteri (Registry)

🔗 [**src/skills/registry.py** — Tam dosya (117 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/skills/registry.py)

**Tetikleme kuralları:**

🔗 [**src/skills/registry.py:6-51** — SKILL_TRIGGERS](https://github.com/CYBki/code-execution-agent/blob/main/src/skills/registry.py#L6-L51)

```python
SKILL_TRIGGERS = {
    "xlsx": {
        "extensions": [".xlsx", ".xls", ".xlsm"],
        "keywords": ["excel", "spreadsheet", "workbook"],
        "skill_path": "skills/xlsx/SKILL.md",
        "references": {
            "large_files": {
                "path": "skills/xlsx/references/large_files.md",
                "triggers": {
                    "file_size_mb": 40,          # 40MB üstü → DuckDB kuralları
                    "keywords": ["duckdb", "million rows", ...],
                },
            },
            "multi_file_joins": {
                "path": "skills/xlsx/references/multi_file_joins.md",
                "triggers": {
                    "min_files": 2,              # 2+ dosya → JOIN kuralları
                    "keywords": ["join", "merge", ...],
                },
            },
        },
    },
    "csv": { ... },
    "pdf": { ... },
    "visualization": {
        "extensions": [],                        # Uzantı yok — sadece keyword
        "keywords": ["chart", "dashboard", ...],
    },
}
```

**Algılama fonksiyonları:**

🔗 [**src/skills/registry.py:54-74** — detect_required_skills](https://github.com/CYBki/code-execution-agent/blob/main/src/skills/registry.py#L54-L74)

```python
def detect_required_skills(uploaded_files, user_query=""):
    # 1. Dosya uzantılarını kontrol et
    for file in uploaded_files:
        ext = "." + file.name.rsplit(".", 1)[-1].lower()
        for skill_name, config in SKILL_TRIGGERS.items():
            if ext in config["extensions"]:
                required_skills.add(skill_name)
    # 2. Kullanıcı sorgusundaki anahtar kelimeleri kontrol et
    if user_query:
        for skill_name, config in SKILL_TRIGGERS.items():
            if any(kw in query_lower for kw in config["keywords"]):
                required_skills.add(skill_name)
```

🔗 [**src/skills/registry.py:77-117** — detect_reference_files](https://github.com/CYBki/code-execution-agent/blob/main/src/skills/registry.py#L77-L117)

Bu fonksiyon referans dosyalarını kontrol ediyor:
- Dosya boyutu ≥ 40MB → `large_files.md` yükle
- 2+ Excel dosyası → `multi_file_joins.md` yükle
- Sorguda "duckdb" geçiyor → `large_files.md` yükle

### 7.2 Skill Yükleyici (Loader)

🔗 [**src/skills/loader.py** — Tam dosya (86 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/skills/loader.py)

**SKILL.md dosyalarını yükleme:**

🔗 [**src/skills/loader.py:14-37** — load_skill](https://github.com/CYBki/code-execution-agent/blob/main/src/skills/loader.py#L14-L37)

```python
@lru_cache(maxsize=32)  # Aynı skill'i tekrar tekrar okumamak için cache
def load_skill(skill_name: str) -> dict | None:
    skill_path = Path(f"skills/{skill_name}/SKILL.md")
    content = skill_path.read_text(encoding="utf-8")
    # YAML frontmatter varsa ayrıştır
    if content.startswith("---\n"):
        frontmatter = yaml.safe_load(...)
        instructions = content[end + 5:]
```

SKILL.md dosyaları YAML başlık + Markdown içerik formatında:

```yaml
---
name: Excel Analysis
description: Rules for Excel file analysis
---
# Excel Analiz Kuralları
1. Önce parse_file ile şemayı al
2. Tarih kolonlarını tespit et
...
```

**Prompt derleme:**

🔗 [**src/skills/loader.py:49-86** — compose_system_prompt](https://github.com/CYBki/code-execution-agent/blob/main/src/skills/loader.py#L49-L86)

```python
def compose_system_prompt(base_prompt, active_skills, uploaded_files=None, user_query=""):
    prompt_parts = [base_prompt]
    for skill_name in active_skills:
        skill = load_skill(skill_name)
        prompt_parts.append(f"# {skill['name']} Expertise\n\n{skill['instructions']}")

        # Progressive disclosure: referans dosyalarını tetiklenenleri yükle
        ref_paths = detect_reference_files(skill_name, uploaded_files, user_query)
        for ref_path in ref_paths:
            ref_content = load_reference(ref_path)
            prompt_parts.append(f"## {ref_name} (Reference)\n\n{ref_content}")

    return "\n\n".join(prompt_parts)
```

**Sonuç: Dinamik prompt boyutu**

| Senaryo | Prompt boyutu |
|---------|--------------|
| Küçük Excel dosyası | ~500 satır (base + xlsx skill) |
| 50MB Excel dosyası | ~800 satır (+ large_files referansı) |
| 2 Excel + "merge" sorgusu | ~900 satır (+ multi_file_joins referansı) |
| Sadece "dashboard" sorgusu | ~400 satır (base + visualization skill) |

> 💡 **Neden progressive disclosure?** Claude'un context window'u sınırlı.
> Her zaman tüm kuralları yüklemek yerine, sadece gerekli olanları yüklemek
> daha az token tüketir ve ajanın odaklanmasını sağlar.

---

## Bölüm 8: Sistem Prompt'u

696 satırlık devasa bir prompt. Ajanın tüm davranışlarını bu belirliyor.

### 8.1 Temel Kurallar

🔗 [**src/agent/prompts.py:1-50** — Giriş ve çıktı formatı kuralları](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/prompts.py#L1-L50)

```python
BASE_SYSTEM_PROMPT = """You are a senior data analysis agent.
Always respond to the user in Turkish.

⚠️ OUTPUT FORMAT RULE (CRITICAL):
- "Give Excel output" → ONLY execute(save Excel) + download_file
- "Give PDF report" → ONLY execute(HTML→PDF weasyprint) + download_file
...

⚠️ CHAT MESSAGE RULES:
- NEVER use numbers, ratios, percentages in text summaries
- Numbers belong in output files — chat message BRIEF (1-2 sentences)
```

İlk kural: **Türkçe yanıt zorunlu.** İkinci kural: **Sayıları sohbet mesajında
kullanma** — sadece dosyalarda olsun. Neden? Ajan bazen hallüsinasyon yapıp yanlış
sayılar yazabiliyor. Dosyada gerçek hesaplama sonuçları var, sohbette ise sadece
"Analiz tamamlandı, rapor hazır" yeterli.

### 8.2 Veri Fabrikasyonu Yasağı

🔗 [**src/agent/prompts.py:44-50** — RULE 1: DATA FABRICATION](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/prompts.py#L44-L50)

```
## RULE 1: DATA FABRICATION
- If data can't be loaded: STOP, report error
- If column missing: STOP, show available columns
- NEVER put a number in report that can't be calculated
```

### 8.3 ReAct Döngüsü

🔗 [**src/agent/prompts.py:61-113** — RULE 2: ReAct Loop](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/prompts.py#L61-L113)

```
THOUGHT: [Ne gözlemledim] → [Ne yapacağım] → [Neden]
  SCOPE CHECK: Kodumda kullanıcının istemediği filtre var mı?
  execute(...)
OBSERVATION: [Çıktıyı oku]
DECISION: [Hedefe ulaştım mı? Hayır → ne düzeltmeliyim?]
```

Ajan her araç çağrısından önce DÜŞÜNCE yazmalı, sonra çıktıyı gözlemleyip karar
vermeli. Bu yapı halüsinasyonları azaltıyor — ajan "düşünmeden" ardışık araç
çağıramıyor.

### 8.4 Kalıcı Kernel Güveni

🔗 [**src/agent/prompts.py:117-269** — RULE 3: Persistent Kernel](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/prompts.py#L117-L269)

Bu prompt'un en uzun ve en kritik bölümü. Ajana tekrar tekrar anlatıyor:

1. **Değişkenler yaşar** — `df` Execute #1'de oluşturuldu, Execute #5'te hâlâ orada
2. **generate_html() ayrı process** — Python değişkenlerini göremez, HTML string geçir
3. **ASLA hardcoded veri yazma** — `m = {'total': 5863}` YASAK, `m['total']` kullan
4. **Değerleri yazdırma** — `print(m)` YASAK, `print(list(m.keys()))` kullan

> 💡 **Neden bu kadar tekrar?** Claude bazen "öğrendiğini unutuyor" — uzun konuşmalarda
> daha önceki kuralları es geçebiliyor. Aynı kuralı farklı açılardan, örneklerle,
> DO/DON'T formatında tekrar etmek uyumluluğu artırıyor.

### 8.5 PDF ve Dashboard Şablonları

🔗 [**src/agent/prompts.py:441-696** — Teknik referans ve şablonlar](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/prompts.py#L441-L696)

Bu bölüm ajana PDF (WeasyPrint), PPTX (python-pptx + matplotlib) ve HTML dashboard
(Chart.js) üretimi için şablonlar veriyor. Ajan bu şablonları kopyalayıp
değiştiriyor — sıfırdan yazmak zorunda kalmıyor.

---

## Bölüm 9: Ajan Beyni — `agent/graph.py`

629 satırlık bu dosya projenin en karmaşık parçası. Burada ajanı oluşturuyor,
araçları bağlıyor ve **smart interceptor** ile her araç çağrısını denetliyoruz.

### 9.1 Checkpointer — Konuşma Hafızası

🔗 [**src/agent/graph.py:39-73** — _get_checkpointer](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L39-L73)

```python
def _get_checkpointer():
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver
        _checkpointer = PostgresSaver.from_conn_string(database_url)
    else:
        _checkpointer = SqliteSaver(sqlite3.connect(db_path, check_same_thread=False))
```

LangGraph her adımda (her araç çağrısı, her ajan yanıtı) durumu kaydediyor.
Sayfa yenilendiğinde veya hata oluştuğunda son noktadan devam edebiliyor.

### 9.2 Dinamik Execute Limiti

🔗 [**src/agent/graph.py:75-92** — _compute_max_execute](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L75-L92)

```python
_COMPLEX_KEYWORDS = ("rfm", "cohort", "trend", "korelasyon", "forecast", ...)

def _compute_max_execute(user_query, uploaded_files):
    is_complex = any(kw in query_lower for kw in _COMPLEX_KEYWORDS)
    is_large = total_size > 10 * 1024 * 1024  # >10MB
    return 10 if (is_complex or is_large) else 6
```

Basit sorular için 6 execute hakkı, karmaşık analizler veya büyük dosyalar için 10.
Bu maliyet kontrolü sağlıyor — sonsuz döngüye giren ajan API'yi tüketemiyor.

### 9.3 `build_agent()` — Her Şeyi Birleştirme

🔗 [**src/agent/graph.py:95-597** — build_agent fonksiyonu](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L95-L597)

Bu fonksiyon büyük ama mantığı adım adım:

**Adım 1: Backend al**

```python
backend = sandbox_manager.get_or_create_sandbox(thread_id)
```

**Adım 2: Sistem prompt'unu derle**

🔗 [**src/agent/graph.py:108-129** — Prompt derleme](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L108-L129)

```python
system_prompt = BASE_SYSTEM_PROMPT
if uploaded_files:
    # Dosya listesini prompt'a ekle
    system_prompt += f"\n\n## Currently Uploaded Files\n{file_list}\n"
    # Skill tespiti ve yükleme
    required_skills = detect_required_skills(uploaded_files, user_query)
    system_prompt = compose_system_prompt(system_prompt, required_skills, ...)
```

**Adım 3: 5 aracı oluştur**

🔗 [**src/agent/graph.py:131-138** — Araç oluşturma](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L131-L138)

```python
tools = [
    make_parse_file_tool(uploaded_files=uploaded_files),
    make_execute_tool(backend, session_id=thread_id),
    make_generate_html_tool(session_id=thread_id),
    make_visualization_tool(backend, session_id=thread_id),
    make_download_file_tool(backend, session_id=thread_id),
]
```

**Adım 4: Smart interceptor oluştur** (aşağıda detaylı)

**Adım 5: Middleware zinciri ve ajan oluşturma**

🔗 [**src/agent/graph.py:574-597** — Middleware ve ajan](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L574-L597)

```python
middleware = [
    create_summarization_middleware(model, backend),   # Uzun konuşmaları özetle
    AnthropicPromptCachingMiddleware(...),              # Prompt caching (maliyet ↓)
    PatchToolCallsMiddleware(),                         # Araç çağrısı düzeltmeleri
    smart_interceptor,                                  # Bizim güvenlik katmanımız
]

agent = create_agent(
    model=model, tools=tools,
    system_prompt=system_prompt,
    middleware=middleware,
    checkpointer=checkpointer,
)
agent = agent.with_config({"recursion_limit": REACT_MAX_ITERATIONS * 2 + 1})
```

### 9.4 Smart Interceptor — Güvenlik Kalkanı

🔗 [**src/agent/graph.py:140-572** — Smart interceptor tamamı](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L140-L572)

Bu, projenin en kritik güvenlik mekanizması. Her araç çağrısı çalıştırılmadan önce
interceptor'dan geçiyor.

**Durum değişkenleri (closure'da yaşar):**

🔗 [**src/agent/graph.py:141-150** — Durum değişkenleri](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L141-L150)

```python
_seen_parse_files: set[str] = set()      # Hangi dosyalar zaten parse edildi
_execute_count = 0                        # Kaç execute yapıldı
_max_execute = _compute_max_execute(...)  # Maks execute hakkı (6 veya 10)
_total_blocked = 0                        # Toplam engelleme sayısı
_MAX_BLOCKED = 4                          # 4 engellemeden sonra geçir
_consecutive_blocks = 0                   # Ardışık engelleme (circuit breaker)
_MAX_CONSECUTIVE_BLOCKS = 3              # 3 ardışık → sonsuz döngü tespiti
```

**`reset_interceptor_state()`:**

🔗 [**src/agent/graph.py:152-166** — Reset fonksiyonu](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L152-L166)

Her yeni kullanıcı mesajından önce çağrılmalı. Neden? Closure değişkenleri
cached ajan'da yaşıyor — önceki mesajdan kalan sayaçlar sıfırlanmadan yeni
mesajda yanlış davranış olur.

**Interceptor kuralları — tam liste:**

🔗 [**src/agent/graph.py:168-572** — smart_interceptor fonksiyonu](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L168-L572)

| # | Kural | Satırlar | Ne yapıyor? |
|---|-------|----------|-------------|
| 1 | **Circuit Breaker** | [178-188](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L178-L188) | 3 ardışık engelleme → "Sonsuz döngüdesin, DUR" |
| 2 | **Duplicate parse_file** | [190-213](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L190-L213) | Aynı dosyayı tekrar parse etmeye çalışırsa engelle |
| 3 | **Execute rate limit** | [216-229](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L216-L229) | Limiti aşarsa (6 veya 10) engelle |
| 4 | **pip install engeli** | [233-249](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L233-L249) | Paket yüklemeye çalışırsa engelle (güvenlik) |
| 5 | **Hardcoded veri tespiti** | [251-308](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L251-L308) | `m = {'total': 5863}` gibi literal sayılar tespit et |
| 6 | **Network engeli** | [310-323](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L310-L323) | `requests.get`, `urllib` vb. engelle |
| 7 | **Shell komutu engeli** | [325-349](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L325-L349) | `ls`, `cat`, `find` vb. engelle |
| 8 | **Dosya sistemi engeli** | [351-368](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L351-L368) | `os.listdir`, `glob.glob` vb. engelle |
| 9 | **nrows sampling engeli** | [370-384](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L370-L384) | `nrows > 10` engelle (tam veri oku) |
| 10 | **Büyük sampling engeli** | [388-408](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L388-L408) | `.head(500)` üstü engelle |
| 11 | **Font otomatik düzeltme** | [410-469](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L410-L469) | Arial → DejaVu, font yolu düzeltme |
| 12 | **Hardcoded değişken tespiti** | [471-515](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L471-L515) | `revenue = 17588623` gibi satırları tespit et |

Bir kuralı detaylı inceleyelim — **Hardcoded veri tespiti (Kural 5):**

🔗 [**src/agent/graph.py:251-308** — Hardcoded data detection](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L251-L308)

```python
# Her atama AYRI AYRI kontrol et (tek regex değil!)
_hc_dicts = [m for m in re.finditer(
    r'\w+\s*=\s*\{[^}]*\b\d{3,}\b[^}]*\}', cmd
) if _is_hardcoded_assignment(m.group())]

def _is_hardcoded_assignment(match_text):
    """Bu atamada veri erişim operasyonu var mı?"""
    return not any(da in match_text for da in _data_access_ops)
```

Mantık: `m = {'total': df['col'].sum()}` → OK (`.sum()` var, veriden geliyor).
`m = {'total': 5863}` → ENGELLE (literal sayı, veriden gelmiyor).

`_data_access_ops` listesinde `.tolist()`, `.values`, `groupby`, `duckdb.sql`,
`.sum()`, `.mean()` gibi ~30 operasyon var. Bunlardan biri bile varsa → gerçek veri.
Yoksa → hardcoded.

**Execute sonrası bilgi ekleme:**

🔗 [**src/agent/graph.py:528-568** — Execute sonrası suffix](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L528-L568)

Her execute sonucunun sonuna ekleniyor:

```
[Execute 3/6, remaining: 3] 💭 Before next step → THOUGHT: ...
```

Son 2 execute hakkında: `⚠️ Last executes — combine analysis+PDF in single script.`

Hata varsa: `🔄 CORRECTION 1/3 — THINK: what failed, why, how to fix.`

### 9.5 Ajan Önbellekleme

🔗 [**src/agent/graph.py:600-629** — get_or_build_agent](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L600-L629)

```python
def get_or_build_agent(sandbox_manager, thread_id, uploaded_files, user_query):
    file_fingerprint = tuple(
        (f.name, len(f.getvalue())) for f in (uploaded_files or [])
    )
    cached = st.session_state.get("_agent_cache")
    if cached and cached["fingerprint"] == file_fingerprint:
        return cached["agent"], cached["checkpointer"], cached["reset_fn"]
    # Yoksa yeniden oluştur
    agent, checkpointer, reset_fn = build_agent(...)
    st.session_state["_agent_cache"] = {"fingerprint": file_fingerprint, ...}
```

Dosya seti aynıysa ajanı yeniden oluşturmaya gerek yok. Fingerprint = (dosya_adı,
dosya_boyutu) tuple'ı. Yeni dosya yüklenirse veya farklı boyutta dosya gelirse
ajan yeniden oluşturulur (skill'ler değişmiş olabilir).

---

## Bölüm 10: Kullanıcı Arayüzü

Artık altyapımız hazır. Şimdi kullanıcının gördüğü ekranı oluşturuyoruz.

### 10.1 Oturum Yönetimi

🔗 [**src/ui/session.py** — Tam dosya (154 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/session.py)

**`MockUploadedFile` — DB'den geri yükleme:**

🔗 [**src/ui/session.py:15-28** — MockUploadedFile sınıfı](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/session.py#L15-L28)

Kullanıcı geçmiş konuşmaya döndüğünde dosyalar DB'den yükleniyor. Ama Streamlit'in
`UploadedFile` arayüzünü taklit etmemiz lazım — `name`, `size`, `getvalue()`,
`seek()` metotları olmalı. `MockUploadedFile` tam bunu yapıyor.

**`init_session()` — Ön-ısıtma:**

🔗 [**src/ui/session.py:32-113** — init_session fonksiyonu](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/session.py#L32-L113)

```python
def init_session():
    # 1. Session state varsayılanlarını ayarla
    defaults = {"messages": [], "session_id": str(uuid4()), ...}

    # 2. SandboxManager oluştur
    if "sandbox_manager" not in st.session_state:
        st.session_state["sandbox_manager"] = SandboxManager()

    # 3. Arka plan thread'inde sandbox'u ön-ısıt
    def _pre_warm():
        sandbox_manager.get_or_create_sandbox(session_id)
    t = threading.Thread(target=_pre_warm, daemon=True)
    t.start()

    # 4. atexit ile temizlik kaydı
    atexit.register(sandbox_manager.stop)
```

> 💡 **Neden ön-ısıtma?** Sandbox oluşturma ~5 saniye sürüyor. Kullanıcı sayfayı
> açtığında hemen sandbox oluşturmaya başlıyoruz. Kullanıcı dosya yükleyip soru
> sorduğunda sandbox zaten hazır — bekleme yok.

**`reset_session()` — Yeni Konuşma:**

🔗 [**src/ui/session.py:116-154** — reset_session fonksiyonu](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/session.py#L116-L154)

Tüm session state temizleniyor, ajan cache silinyor, sandbox workspace
temizleniyor. Ama sandbox container'ı ÖLDÜRÜLMÜYOR — sadece dosyalar ve kernel
sıfırlanıyor.

### 10.2 CSS Stilleri

🔗 [**src/ui/styles.py** — Tam dosya (413 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/styles.py)

Claude-benzeri görünüm: koyu kenar çubuğu, araç kartları, dönen spinner animasyonu,
renk kodlu durum göstergeleri.

**Araç ikonları:**

🔗 [**src/ui/styles.py:377-413** — TOOL_ICONS ve fonksiyonlar](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/styles.py#L377-L413)

```python
TOOL_ICONS = {
    "parse_file": "📄",
    "execute": "🐍",
    "generate_html": "🌐",
    "create_visualization": "📊",
    "download_file": "📥",
}
```

### 10.3 Kenar Çubuğu

🔗 [**src/ui/components.py** — Tam dosya (142 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/components.py)

**Dosya yükleme:**

🔗 [**src/ui/components.py:39-86** — render_sidebar](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/components.py#L39-L86)

```python
uploaded = st.file_uploader(
    "Upload files",
    type=["csv", "xlsx", "xls", "xlsm", "json", "pdf", "tsv"],
    accept_multiple_files=True,
)
if uploaded:
    st.session_state["uploaded_files"] = uploaded
    save_files(_sid, uploaded)  # DB'ye hemen kaydet
```

**Geçmiş konuşmalar:**

🔗 [**src/ui/components.py:95-137** — Konuşma geçmişi](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/components.py#L95-L137)

Kullanıcının `user_id`'sine göre tüm konuşmalar listeleniyor. Tıklandığında
mesajlar DB'den yükleniyor, dosyalar `MockUploadedFile` olarak geri oluşturuluyor.

### 10.4 Sohbet Arayüzü — En Karmaşık UI Parçası

🔗 [**src/ui/chat.py** — Tam dosya (721 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py)

**Adım ismi tespiti — akıllı etiketleme:**

🔗 [**src/ui/chat.py:23-94** — _detect_step_name](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L23-L94)

Her execute çağrısının koduna bakıp ne yaptığını tahmin ediyor:

```python
_DETECTORS = [
    (100, "📑 Generating PDF Report",    'weasyprint' in code_lower),
    (95,  "🎞️ Creating Presentation",   'pptx' in code_lower),
    (85,  "🦆 Running Database Query",   'duckdb' in code_lower),
    (70,  "📄 Loading & Cleaning Data",  'read_excel' in code and 'dropna' in code),
    (60,  "📊 Analyzing Data",           'groupby' in code_lower),
    ...
]
```

Öncelik sistemi: Aynı kod bloğunda hem `read_excel` hem `weasyprint` varsa,
`weasyprint` daha yüksek önceliğe sahip → "📑 Generating PDF Report" gösterilir.

**`ExecuteStatusManager` — Canlı Durum Gösterimi:**

🔗 [**src/ui/chat.py:97-240** — ExecuteStatusManager sınıfı](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L97-L240)

Bu sınıf birden fazla execute çağrısını tek bir konsolide container'da gösteriyor:

```
⟳ 📊 Analyzing Data (Step 3/~5)
  ├─ Step 1 · 📄 Loading Data ✅ (1.2s)
  ├─ Step 2 · 🧹 Cleaning Data ✅ (0.8s)
  └─ Step 3 · 📊 Analyzing Data ⟳ (çalışıyor...)
```

Dönen spinner animasyonu, adım sayacı, süre takibi — hepsi burada.

**`render_chat()` — Ana Akış:**

🔗 [**src/ui/chat.py:494-721** — render_chat fonksiyonu](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L494-L721)

Bu fonksiyon her şeyi birleştiriyor. Adım adım:

1. **Mesaj geçmişini göster** (satır 497-538)
2. **Kullanıcı girdisi al** (satır 541-558)
3. **Ajanı al veya oluştur** (satır 573-580)
4. **Sandbox hazır olana kadar bekle** (satır 582-591)
5. **Dosyaları sandbox'a yükle** (satır 593-606)
6. **Interceptor sayaçlarını sıfırla** (satır 608-610)
7. **Ajan stream'ini başlat** (satır 612-665)
8. **Artifact'ları render et** (satır 682-689)
9. **Mesajı kaydet** (satır 691-707)
10. **Otomatik öğrenme başlat** (satır 709-721)

**Önemli satır — interceptor reset:**

🔗 [**src/ui/chat.py:608-610** — reset_fn() çağrısı](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L608-L610)

```python
reset_fn()  # ← BU ÇAĞRI KRİTİK
```

Bu çağrı olmazsa önceki mesajdaki execute sayacı sıfırlanmaz. İlk mesajda 5 execute
yapıldıysa, ikinci mesajda sadece 1 hakkın kalır — yanlış davranış.

**Stream chunk işleme:**

🔗 [**src/ui/chat.py:410-491** — _process_stream_chunk](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L410-L491)

LangGraph `stream_mode="updates"` ile chunk chunk veri gönderiyor. Her chunk:
- **AI message + tool_calls** → execute ise `exec_manager`'a yönlendir, değilse
  doğrudan render et
- **AI message + content** → final yanıt, markdown olarak göster
- **Tool message** → engellenmişse gizle, execute sonucuysa manager'a ver

**Engellenen mesajları gizleme:**

🔗 [**src/ui/chat.py:476-481** — Blocked message filtering](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L476-L481)

```python
_blocked_markers = ("⛔", "BLOCKED", "already parsed", ...)
if any(m in tool_content for m in _blocked_markers):
    continue  # Kullanıcıya gösterme — sadece ajan görüyor
```

Smart interceptor'ın engel mesajları kullanıcıyı ilgilendirmiyor. Ajan bu mesajları
görüp davranışını düzeltiyor, ama kullanıcı temiz bir arayüz görüyor.

**Otomatik öğrenme (auto_learn):**

🔗 [**src/ui/chat.py:709-721** — Auto learn thread](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L709-L721)

```python
threading.Thread(
    target=auto_learn,
    kwargs={"user_query": user_query, "agent_final_response": full_response, ...},
    daemon=True,
).start()
```

Her konuşma bittiğinde arka planda analiz yapılıyor: Ajan iyi mi yaptı? Skill
kuralları güncellenmeli mi? Bu daemon thread olarak çalışıyor — UI'ı bloklamıyor.

---

## Bölüm 11: Giriş Noktası — `app.py`

🔗 [**app.py** — Tam dosya (58 satır)](https://github.com/CYBki/code-execution-agent/blob/main/app.py)

Şimdi her şeyi birleştiriyoruz. Bu dosya sadece 58 satır ama her satır bir katmanı
başlatıyor:

```python
# 1. Logging başlat
setup_logging()

# 2. .env dosyasını yükle (lokal geliştirme için)
load_dotenv()

# 3. Streamlit sayfa ayarları
st.set_page_config(page_title="Data Analysis Agent", layout="wide")

# 4. CSS stillerini uygula
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# 5. API anahtarlarını doğrula
try:
    get_secret("ANTHROPIC_API_KEY")
    get_secret("OPEN_SANDBOX_API_KEY")
except ValueError as e:
    st.error(str(e))
    st.stop()

# 6. Veritabanını başlat (tabloları oluştur)
init_db()

# 7. Oturumu başlat (sandbox ön-ısıtma dahil)
init_session()

# 8. UI render
render_sidebar()
render_chat()
```

> 💡 **Sıralama önemli!** `setup_logging()` en başta — hata olursa log'a düşsün.
> `load_dotenv()` API anahtarlarından önce — `.env` yüklensin ki anahtarlar bulunabilsin.
> `init_session()` → `render_chat()`'ten önce — sandbox hazırlanmaya başlasın.

---

## Bölüm 12: Uçtan Uca Akış

Tüm parçalar yerli yerinde. Şimdi bir senaryoyu baştan sona takip edelim:

**Senaryo:** Kullanıcı `sales.xlsx` dosyasını yüklüyor ve "Bu veriyi analiz et, PDF rapor ver" diyor.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. SAYFA AÇILIYOR                                                          │
│                                                                             │
│  app.py:                                                                    │
│    setup_logging()     → JSON log sistemi hazır                            │
│    load_dotenv()       → .env'den API anahtarları                          │
│    get_secret(...)     → ANTHROPIC_API_KEY + OPEN_SANDBOX_API_KEY doğrula  │
│    init_db()           → SQLite tabloları oluştur                          │
│    init_session()      → session_id üret, sandbox oluşturmaya BAŞLA       │
│                          (daemon thread ile — arka planda ~5 saniye)        │
│    render_sidebar()    → Dosya yükleme widget'ı göster                    │
│    render_chat()       → Boş sohbet ekranı                                │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. DOSYA YÜKLENİYOR (kullanıcı sales.xlsx'i sürükle-bırak yapıyor)       │
│                                                                             │
│  components.py → render_sidebar():                                         │
│    st.file_uploader(...) → uploaded dosyayı yakala                         │
│    st.session_state["uploaded_files"] = [sales.xlsx]                       │
│    save_files(session_id, uploaded) → BLOB olarak DB'ye kaydet            │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. SORU SORULUYOR ("Bu veriyi analiz et, PDF rapor ver")                  │
│                                                                             │
│  chat.py → render_chat():                                                  │
│    a) user_query = st.chat_input(...)                                      │
│    b) save_message(session_id, "user", user_query)                         │
│    c) get_or_build_agent() →                                               │
│       - detect_required_skills([sales.xlsx]) → ["xlsx"]                    │
│       - compose_system_prompt(BASE + xlsx skill)                           │
│       - make_parse_file_tool, make_execute_tool, ...                       │
│       - smart_interceptor oluştur                                          │
│    d) sandbox_manager.wait_until_ready() → sandbox ön-ısıtma tamamlandı   │
│    e) sandbox_manager.upload_files([sales.xlsx]) → /home/sandbox/sales.xlsx│
│    f) reset_fn() → interceptor sayaçlarını sıfırla                        │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. AJAN ÇALIŞIYOR (ReAct döngüsü)                                        │
│                                                                             │
│  Turn 1: parse_file("sales.xlsx")                                          │
│    → file_parser.py: Excel şemasını çıkar (lokal, sandbox'a gitmez)       │
│    → Sonuç: "4 kolon, 50,000 satır, tarih formatı: DD.MM.YYYY"           │
│    → interceptor: _seen_parse_files.add("sales.xlsx")                     │
│                                                                             │
│  Turn 2: execute("df = pd.read_excel(...); df.dropna(...)")                │
│    → interceptor: _execute_count=1, limit=6 → GEÇIR                       │
│    → execute.py: Python kodu tespit → base64 → kernel'da çalıştır         │
│    → manager.py: codes.run(py_code, context=py_context)                    │
│    → Sonuç: "✅ 48,500 satır yüklendi" + "[Execute 1/6, remaining: 5]"   │
│                                                                             │
│  Turn 3: execute("m = {'total': len(df), 'avg': df['Revenue'].mean()}")   │
│    → interceptor: Hardcoded check → .mean() var → OK, GEÇIR              │
│    → Sonuç: "✅ m dict computed: 5 keys: ['total', 'avg', ...]"           │
│                                                                             │
│  Turn 4: execute("html = f'...{m[\"total\"]:,}...'; weasyprint → PDF")    │
│    → interceptor: _execute_count=3, limit=6 → GEÇIR                       │
│    → PDF oluşturuldu: /home/sandbox/rapor.pdf (148 KB)                    │
│                                                                             │
│  Turn 5: download_file("/home/sandbox/rapor.pdf")                          │
│    → download_file.py: Sandbox'tan indir → _clean_excel_dates (PDF, skip) │
│    → ArtifactStore.add_download(pdf_bytes, "rapor.pdf")                   │
│                                                                             │
│  Final: Ajan yanıtı: "Analiz tamamlandı, PDF rapor hazır."               │
│    (Sayı yok — kural gereği)                                               │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 5. SONUÇ RENDER EDİLİYOR                                                  │
│                                                                             │
│  chat.py:                                                                  │
│    exec_manager.finalize() → "✅ Code Execution Complete (3 steps, 8.2s)" │
│    store.pop_downloads() → [{bytes: ..., filename: "rapor.pdf"}]          │
│    st.download_button("📥 rapor.pdf indir", data=pdf_bytes)               │
│    save_message(session_id, "assistant", response, steps=[...])           │
│    auto_learn() → arka plan thread'i ile kalite analizi                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Engelleme Senaryosu

Ya ajan `ls` komutu çalıştırmaya çalışırsa?

```
  Ajan: execute("ls /home/sandbox/")
    → interceptor: bare_cmd = "ls" → shell_cmds'de var → ENGELLE
    → ToolMessage: "⛔ Shell command 'ls' BLOCKED. Known files: /home/sandbox/sales.xlsx"
    → _consecutive_blocks += 1
    → UI'da gösterilmez (blocked marker tespiti)

  Ajan (öğreniyor): execute("df = pd.read_excel('/home/sandbox/sales.xlsx')")
    → interceptor: Python kodu → GEÇIR
    → _consecutive_blocks = 0  (başarılı execute → sıfırla)
```

### Hardcoded Veri Senaryosu

Ya ajan önceki çıktıdan sayıları kopyalarsa?

```
  Ajan: execute("m = {'total_customers': 5863, 'total_revenue': 17588623}")
    → interceptor: regex buldu → _is_hardcoded_assignment()
    → .sum(), .mean(), .tolist() YOK → HARDCODED!
    → ToolMessage: "⚠️ HARDCODED DATA DETECTED. Use kernel variables directly."
    → _execute_count -= 1  (hakkını geri ver — haksız ceza olmasın)

  Ajan (düzeltiyor): execute("m = {'total': df['ID'].nunique(), 'rev': df['Rev'].sum()}")
    → interceptor: .nunique() ve .sum() var → OK, GEÇIR
```

---

## Son Söz

Bu dokümanı okuduysan, projenin her satırını anlamış olmalısın. Sıralama kasıtlıydı:

1. **Temel altyapı** (config, logging, DB) — bağımsız, basit
2. **Sandbox** — projenin kalbi, kalıcı kernel
3. **Araçlar** — ajanın elleri, factory pattern
4. **Skill sistemi** — dinamik prompt, progressive disclosure
5. **Sistem prompt'u** — ajanın beyni, kurallar
6. **Smart interceptor** — güvenlik kalkanı, 12 kural
7. **UI** — kullanıcının gördüğü ekran, streaming
8. **app.py** — her şeyi birleştiren 58 satır

Her bölümde 🔗 linklerine tıklayıp GitHub'da gerçek kodu gördün. Açıklamayı okudun,
kodu gördün, sonraki açıklamaya geçtin — projeyi adım adım "yazdın."

Projeye katkı sağlamak istersen, bu akışı takip et:
1. **Yeni araç mı?** → `src/tools/` altına factory fonksiyon yaz, `graph.py`'de tools listesine ekle
2. **Yeni skill mi?** → `skills/` altına SKILL.md yaz, `registry.py`'de trigger ekle
3. **Yeni interceptor kuralı mı?** → `graph.py`'deki `smart_interceptor`'a yeni blok ekle
4. **UI değişikliği mi?** → `chat.py` veya `components.py`'de düzenle

İyi kodlamalar! 🚀
