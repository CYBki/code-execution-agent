# 🛠️ CODE_WALKTHROUGH_TR.md — Projeyi Sıfırdan, Satır Satır Yazıyoruz

> **Bu doküman nedir?** Projeyi sanki sıfırdan yazıyormuşsun gibi, **her satırı** açıklıyor.
> Sadece "ne yapıyor" değil — **neden bu şekilde yazdık**, alternatifler neydi, hangi
> tuzaklara düştük ve neden bu çözümü seçtik — hepsini anlatıyor.
>
> 🔗 linklerine tıkla → GitHub'da kodu gör → açıklamayı oku → sonraki adıma geç.

**Repo:** [CYBki/code-execution-agent](https://github.com/CYBki/code-execution-agent)

---

## İçindekiler

| # | Bölüm | Ne Yazıyoruz? |
|---|-------|---------------|
| 1 | [Konfigürasyon](#bölüm-1-konfigürasyon) | API anahtarı çözümleme — neden tek fonksiyon? |
| 2 | [Logging](#bölüm-2-logging-altyapısı) | JSON loglar — neden yapılandırılmış? |
| 3 | [Veritabanı](#bölüm-3-veritabanı-katmanı) | Çift backend — neden ikisi birden? |
| 4 | [Sandbox](#bölüm-4-sandbox-yöneticisi) | Kalıcı kernel — neden pickle değil? |
| 5 | [Artifact Store](#bölüm-5-artifact-store) | Thread güvenliği — neden Lock? |
| 6 | [Araçlar](#bölüm-6-araçlar-tools) | Factory pattern — neden closure? |
| 7 | [Skill Sistemi](#bölüm-7-skill-sistemi) | Progressive disclosure — neden dinamik prompt? |
| 8 | [Sistem Prompt'u](#bölüm-8-sistem-promptu) | 696 satır kural — neden bu kadar çok? |
| 9 | [Ajan Beyni](#bölüm-9-ajan-beyni) | Smart interceptor — neden 12 kural? |
| 10 | [UI](#bölüm-10-kullanıcı-arayüzü) | Streaming — neden chunk chunk? |
| 11 | [Giriş Noktası](#bölüm-11-giriş-noktası) | app.py — neden bu sıralama? |
| 12 | [Uçtan Uca](#bölüm-12-uçtan-uca-akış) | Tam senaryo — her adımda ne oluyor? |
| 13 | [Bellek Yönetimi](#bölüm-13-bellek-yönetimi--15-koruma-katmanı) | 15 koruma katmanı — sandbox, sunucu, disk |
| 14 | [Sohbet Hafızası](#bölüm-14-sohbet-hafızası-conversation-memory--agent-nasıl-hatırlıyor) | 3 hafıza katmanı — checkpointer, kernel, DB |

---

## Bölüm 1: Konfigürasyon

Projeye başlarken ilk soru: API anahtarlarını nasıl yöneteceğiz?

### 1.1 Problem

İki farklı ortamımız var:
- **Lokal geliştirme:** `.env` dosyasında `ANTHROPIC_API_KEY=sk-ant-...`
- **Streamlit Cloud (production):** Dashboard'dan girilen `secrets.toml`

Eğer her yerde `os.getenv("ANTHROPIC_API_KEY")` kullansak, Streamlit Cloud'da çalışmaz
çünkü orada anahtarlar `st.secrets` içinde. Tersi de geçerli — `st.secrets` lokal'de
dosya bulamayınca hata fırlatır.

### 1.2 Çözüm: Tek Fonksiyon, İki Kaynak

🔗 [**src/utils/config.py** — Tam dosya (23 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/utils/config.py)

```python
import os
import streamlit as st


def get_secret(key: str) -> str:
    """Resolve a secret value with priority: st.secrets → os.environ → raise.

    Streamlit Cloud → st.secrets (from secrets.toml or dashboard)
    Local dev       → .env (loaded via python-dotenv)
    """
```

**Satır satır:**

```python
    try:
        return st.secrets[key]                    # ← İLK BURAYA BAK
    except (KeyError, FileNotFoundError):         # ← İki farklı hata yakalıyoruz
```

`st.secrets[key]` iki şekilde başarısız olabilir:
- `KeyError`: `secrets.toml` var ama bu anahtar yok
- `FileNotFoundError`: `secrets.toml` dosyası hiç yok (lokal geliştirme)

İkisini de yakalıyoruz çünkü lokal'de `.secrets` klasörü bile olmayabilir.

```python
        value = os.getenv(key)                    # ← İKİNCİ ŞANS: ortam değişkeni
        if not value:
            raise ValueError(                     # ← HİÇBİR YERDE YOK → HATA
                f"'{key}' not found. "
                f"Add it to .env file or Streamlit secrets."
            )
        return value
```

> 💡 **Neden `ValueError` ve `KeyError` değil?** `ValueError` daha açıklayıcı bir mesaj
> taşıyabiliyor. Kullanıcıya "nereye eklemen lazım" diyebiliyoruz. `KeyError` sadece
> anahtarı gösterirdi.

> 💡 **Alternatif neydi?** Her dosyada `if os.getenv(): ... elif st.secrets: ...` yazabilirdik.
> Ama bu 10+ yerde tekrar ederdi. Tek fonksiyon → tek sorumluluk → tek değişiklik noktası.
> Yarın üçüncü bir kaynak eklensek (AWS Secrets Manager gibi), sadece bu fonksiyonu değiştiririz.

---

## Bölüm 2: Logging Altyapısı

Production'da bir şey patlayınca tek silahın loglar. "Bir hata oldu" yazan log işe
yaramaz — hangi kullanıcı, hangi oturum, hangi araç, ne zaman?

### 2.1 `SessionContext` — Thread-Local Oturum Takibi

🔗 [**src/utils/logging_config.py:25-45** — SessionContext](https://github.com/CYBki/code-execution-agent/blob/main/src/utils/logging_config.py#L25-L45)

```python
class SessionContext:
    """Thread-local storage for session_id correlation."""
    _local = threading.local()
```

**Neden `threading.local()`?** Streamlit her kullanıcı için ayrı thread çalıştırıyor.
Global bir değişken kullansak, Kullanıcı A'nın session_id'si Kullanıcı B'nin loglarına
karışır. `threading.local()` her thread'e özel depolama sağlıyor — thread A `session_id = "abc"`
yazarsa, thread B bunu görmez.

```python
    @classmethod
    def set(cls, session_id: str):
        cls._local.session_id = session_id    # ← Bu thread'e özel

    @classmethod
    def get(cls) -> str:
        return getattr(cls._local, "session_id", "")  # ← Yoksa boş string
```

**Neden `getattr` ile default?** İlk log yazıldığında henüz `set()` çağrılmamış olabilir.
`cls._local.session_id` direkt erişsek `AttributeError` alırız. `getattr(..., "")` ile
güvenli erişim sağlıyoruz.

```python
    @classmethod
    def clear(cls):
        cls._local.session_id = ""            # ← Oturum bitince temizle
```

### 2.2 `JSONFormatter` — Her Log Satırı Bir JSON

🔗 [**src/utils/logging_config.py:50-81** — JSONFormatter](https://github.com/CYBki/code-execution-agent/blob/main/src/utils/logging_config.py#L50-L81)

```python
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
```

**Neden UTC?** Sunucu Türkiye'de, geliştirici Almanya'da, kullanıcı ABD'de olabilir.
Herkes kendi saat diliminde log okursa karışır. UTC tek standart — herkese göre
dönüştürülebilir.

**Neden `record.created` ve `datetime.now()` değil?** `record.created` logun gerçek
oluşturulma anını veriyor (Python'un log sistemi bunu otomatik tutuyor). `datetime.now()`
ise format anını verir — arada milisaniyelik fark olabilir, sıralama bozulur.

```python
            "level": record.levelname,
            "logger": record.name,               # ← "src.sandbox.manager" gibi
            "msg": record.getMessage(),
        }
```

**Neden `record.name`?** Bu, logu yazan modülün tam adı. `logger = logging.getLogger(__name__)`
dediğimizde `__name__` otomatik olarak `src.sandbox.manager` gibi olur. Hangi dosyadan
geldiğini hemen görürsün.

```python
        # Session correlation
        sid = SessionContext.get()
        if sid:
            log_entry["session_id"] = sid         # ← Hangi kullanıcının logu?
```

`SessionContext`'ten session_id'yi alıyoruz. Yoksa eklemiyoruz — gereksiz `"session_id": ""`
JSON'ı şişirmesin.

```python
        # Extra fields (audit logları için)
        for key in ("tool_name", "action", "blocked", "execute_num", "duration_s"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val
```

**Neden bu özel alanlar?** Audit loglarında `_audit.info("tool_blocked", extra={"tool_name": "execute", "action": "pip_install", "blocked": True})`
şeklinde ek bilgi gönderiyoruz. Formatter bunları JSON'a ekliyor. Böylece log satırından
doğrudan "hangi araç engellendi, neden engellendi, kaçıncı execute'du" bilgisini çekebilirsin.

```python
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exc"] = self.formatException(record.exc_info)
```

Hata varsa stack trace'i de JSON'a ekle. `jq` ile filtreleme yapabilirsin:
`cat app.log | jq 'select(.exc != null)'` → sadece hatalı logları göster.

```python
        return json.dumps(log_entry, ensure_ascii=False, default=str)
```

**Neden `ensure_ascii=False`?** Türkçe karakterler ("ö", "ü", "ş") ASCII'de yok.
`ensure_ascii=True` olsa `\u00f6` gibi escape'ler yazılır — okunmaz. `False` ile
doğrudan UTF-8 yazılır.

**Neden `default=str`?** Bazen log'a `datetime` veya `Path` nesnesi düşebilir. `json.dumps`
bunları serialize edemez. `default=str` ile "en kötü ihtimalle string'e çevir" diyoruz.

### 2.3 `setup_logging()` — Üç Katmanlı Log Sistemi

🔗 [**src/utils/logging_config.py:95-147** — setup_logging](https://github.com/CYBki/code-execution-agent/blob/main/src/utils/logging_config.py#L95-L147)

```python
def setup_logging(log_level: int = logging.INFO):
    os.makedirs(_LOG_DIR, exist_ok=True)       # ← logs/ dizini yoksa oluştur

    root = logging.getLogger()
    root.setLevel(log_level)

    root.handlers.clear()                       # ← KRİTİK!
```

**Neden `handlers.clear()`?** Streamlit her sayfayı yeniden çalıştırıyor (rerun).
`clear()` yapmazsak her rerun'da yeni handler eklenir → aynı log 2x, 3x, 10x tekrar
yazar. Bu çok yaygın bir Streamlit tuzağı.

```python
    # Console handler — geliştirici dostu
    console = logging.StreamHandler()
    if os.environ.get("LOG_JSON", "").strip() in ("1", "true"):
        console.setFormatter(json_fmt)          # ← Production: JSON
    else:
        console.setFormatter(human_fmt)         # ← Dev: "2026-04-14 [sandbox] INFO: ..."
```

**Neden iki format?** Geliştirme sırasında JSON okumak zor. İnsan-okunur format daha hızlı
debug sağlıyor. Production'da ise Grafana/ELK gibi araçlar JSON bekliyor.

```python
    # File handler: tüm loglar (10MB × 5 rotasyon)
    all_handler = RotatingFileHandler(
        os.path.join(_LOG_DIR, "app.log"),
        maxBytes=10 * 1024 * 1024,             # ← 10MB olunca yeni dosyaya geç
        backupCount=5,                          # ← En fazla 5 eski dosya tut
        encoding="utf-8",
    )
```

**Neden `RotatingFileHandler`?** Sıradan `FileHandler` dosyayı sonsuza kadar büyütür.
24 saat sonra 2GB log dosyası olabilir — disk dolar. Rotation ile en fazla
10MB × 6 = 60MB disk kullanımı garanti.

**Neden `backupCount=5`?** 5 yedek = son ~60MB log. Hata araştırması için yeterli,
disk israfı yok. Daha fazla gerekirse log aggregator (ELK, Grafana Loki) kullan.

```python
    # Sadece hatalar (WARNING+)
    err_handler = RotatingFileHandler(
        os.path.join(_LOG_DIR, "app_error.log"),
        ...
    )
    err_handler.setLevel(logging.WARNING)
```

**Neden ayrı hata dosyası?** `app.log` her şeyi içeriyor (INFO, WARNING, ERROR).
Sadece hataları görmek istediğinde 100,000 satırlık dosyada `grep` yapmak yerine
doğrudan `app_error.log`'a bak — çok daha hızlı.

### 2.4 `get_audit_logger()` — Araç Denetim İzi

🔗 [**src/utils/logging_config.py:150-169** — Audit logger](https://github.com/CYBki/code-execution-agent/blob/main/src/utils/logging_config.py#L150-L169)

```python
def get_audit_logger() -> logging.Logger:
    audit = logging.getLogger("audit")
    if not audit.handlers:                      # ← İlk çağrıda kur, sonra yeniden kurma
        ...
        audit.propagate = False                 # ← KRİTİK!
    return audit
```

**Neden `propagate = False`?** Python'da loggerlar ağaç yapısında. `"audit"` logger'ı
logladığında, parent olan root logger'a da gider → `app.log`'a da yazılır. Biz bunu
istemiyoruz — audit logları ayrı dosyada kalmalı. `propagate = False` ile parent'a
iletmeyi kapatıyoruz.

**Neden ayrı audit log?** `app.log`'da uygulama logları + audit logları karışır.
Audit analizi yapmak istediğinde:
```bash
cat audit.log | jq 'select(.blocked == true)' | wc -l   # Kaç araç engellendi?
cat audit.log | jq 'select(.tool_name == "execute")' | wc -l  # Kaç execute çağrıldı?
```

`app.log`'dan bunu yapmak çok zor çünkü arada binlerce unrelated log var.

---

## Bölüm 3: Veritabanı Katmanı

Kullanıcı sayfayı yenilediğinde konuşma geçmişi kaybolmasın. Dosyalar kaybolmasın.
Bunun için veritabanına ihtiyacımız var.

### 3.1 Çift Backend: SQLite + PostgreSQL

🔗 [**src/storage/db.py:54-84** — Bağlantı yönetimi](https://github.com/CYBki/code-execution-agent/blob/main/src/storage/db.py#L54-L84)

```python
def _get_conn():
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgresql"):
        import psycopg2
        return psycopg2.connect(database_url)
    else:
        return sqlite3.connect(DB_PATH, check_same_thread=False)
```

**Neden `check_same_thread=False`?** SQLite normalde "ben sadece beni oluşturan thread'den
erişilebilirim" diyor. Ama Streamlit'te birden fazla thread var (UI thread, ajan thread,
ön-ısıtma thread). `check_same_thread=False` ile bu kısıtlamayı kaldırıyoruz.

**Bu tehlikeli değil mi?** Evet, SQLite aynı anda iki write yapılırsa kilitlenebilir.
Ama bizim kullanım senaryomuzda her oturum genellikle tek bir ajan çalıştırıyor — eşzamanlı
write nadir. Production'da PostgreSQL kullanılması tam da bu yüzden öneriliyor.

```python
def _ph(n: int = 1) -> str:
    """Placeholder: %s (PostgreSQL) veya ? (SQLite)"""
    return ", ".join(["%s"] * n) if _is_pg() else ", ".join(["?"] * n)
```

**Neden bu yardımcı fonksiyon?** SQL'de parametre placeholder'ları veritabanına göre değişiyor:
- SQLite: `INSERT INTO t VALUES (?, ?, ?)`
- PostgreSQL: `INSERT INTO t VALUES (%s, %s, %s)`

Her SQL sorgusunda `if _is_pg(): "%s" else "?"` yazmak yerine `_ph(3)` diyoruz. DRY prensibi.

```python
def _now_expr() -> str:
    return "NOW()" if _is_pg() else "datetime('now')"
```

Aynı mantık — `NOW()` PostgreSQL'e özel, SQLite `datetime('now')` kullanıyor.

> 💡 **Neden ORM (SQLAlchemy) kullanmadık?** Bu proje için overkill. 3 tablo, ~10 sorgu var.
> SQLAlchemy eklemek: dependency artışı, migration sistemi, session yönetimi... Basit SQL
> yeterli. "En basit çözüm en iyi çözümdür" — YAGNI prensibi.

### 3.2 Şema Tasarımı

🔗 [**src/storage/db.py:96-170** — init_db ve tablo tanımları](https://github.com/CYBki/code-execution-agent/blob/main/src/storage/db.py#L96-L170)

```sql
-- conversations tablosu
CREATE TABLE IF NOT EXISTS conversations (
    session_id TEXT PRIMARY KEY,     -- UUID, her oturumun benzersiz kimliği
    user_id    TEXT NOT NULL,        -- Kullanıcı kimliği (query param'dan)
    title      TEXT DEFAULT '',      -- İlk mesajın ilk 80 karakteri
    created_at ...,
    updated_at ...
);
```

**Neden `session_id` PK ve auto-increment değil?** UUID'yi Python tarafında üretiyoruz
(`str(uuid4())`). Bunu URL'de, log'da, sandbox'ta kullanıyoruz. Auto-increment integer
olsa bu ID'yi her yerde taşımak zorunda kalırdık ve DB'ye gitmeden ID üretemezdik.

```sql
-- messages tablosu
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,        -- "user" veya "assistant"
    content    TEXT DEFAULT '',
    steps      TEXT DEFAULT '[]',    -- JSON: araç çağrıları
    created_at ...
);
```

**Neden `steps` JSON olarak?** Ajan her turda farklı sayıda araç çağırıyor (2-8 arası).
Her araç çağrısının adı, girdisi, çıktısı var. Bunu normalize etseydik:
- `tool_calls` tablosu, `tool_inputs` tablosu, `tool_outputs` tablosu...
- JOIN'ler, karmaşık sorgular, performans sorunları

JSON ile tek kolonda saklıyoruz. Okurken `json.loads()` ile parse ediyoruz. Basit, hızlı,
yeterli.

```sql
-- files tablosu
CREATE TABLE IF NOT EXISTS files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    filename   TEXT NOT NULL,
    size       INTEGER DEFAULT 0,
    file_data  BLOB,               -- ← Dosyanın kendisi!
    created_at ...
);
```

**Neden BLOB?** Alternatifler:
1. **Dosya sistemi:** Dosyayı disk'e yaz, yolunu DB'ye kaydet → Sunucu değiştiğinde dosyalar kaybolur
2. **S3/Object storage:** Ölçeklenebilir ama ekstra servis → karmaşıklık artışı
3. **BLOB:** Dosya DB'nin içinde → yedekleme tek komut, taşıma basit

Dosyalar genellikle 1-20MB. SQLite bu boyutları rahat taşıyor. 100MB+ dosyalar için
S3'e geçmek gerekir ama şu an overkill.

### 3.3 CRUD Operasyonları — Detaylı

🔗 [**src/storage/db.py:173-355** — Tüm CRUD fonksiyonları](https://github.com/CYBki/code-execution-agent/blob/main/src/storage/db.py#L173-L355)

**`save_message()` içindeki önemli detay:**

```python
def save_message(session_id, role, content, steps=None):
    steps_json = json.dumps(steps or [], ensure_ascii=False, default=str)
    # ...
    cur.execute(f"""
        INSERT INTO messages (session_id, role, content, steps, created_at)
        VALUES ({_ph(5)})
    """, (session_id, role, content, steps_json, ...))
```

**Neden `ensure_ascii=False`?** Aynı mantık — Türkçe karakterler korunmalı.
**Neden `default=str`?** `steps` içinde `bytes` veya `datetime` nesnesi olabilir (araç çıktıları).
Normal `json.dumps` bunları serialize edemez — `default=str` ile string'e çevrilir.

**`save_files()` — dosya boyutu kontrolü:**

```python
def save_files(session_id, files):
    for f in files:
        f.seek(0)
        data = f.getvalue()         # ← Tüm dosyayı belleğe oku
        # ... INSERT INTO files ... (data as BLOB)
```

**Neden `f.seek(0)`?** Streamlit'in `UploadedFile` nesnesi bir stream. Daha önce okunmuşsa
cursor sonda kalır — tekrar okumak için başa sar. Bu `seek(0)` olmazsa boş bytes alırsın.
Bu çok yaygın bir bug kaynağı.

---

## Bölüm 4: Sandbox Yöneticisi

Burası projenin kalbi. Tüm kullanıcı kodu izole bir Docker container içinde çalışıyor.

### 4.1 Temel Kavram: Kalıcı Kernel (Persistent Kernel)

🔗 [**src/sandbox/manager.py:1-50** — Sabitler ve yardımcılar](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L1-L50)

```python
SANDBOX_HOME = "/home/sandbox"
```

Tüm dosyaların yaşadığı dizin. Neden `/home/sandbox/` ve `/tmp/` değil? Docker image'da
bu dizin WORKDIR olarak ayarlanmış. Kullanıcı dosyaları, fontlar, üretilen raporlar
hep burada. Tutarlı bir konum — ajan her zaman dosyanın nerede olduğunu biliyor.

```python
_PYFILE_RE = re.compile(
    r"printf '%s' '([A-Za-z0-9+/=\s]+)' \| base64 -d > (/tmp/_run_[a-f0-9]+\.py)"
)
```

**Bu regex ne yapıyor?** `execute.py` Python kodunu şu formata çeviriyor:
```bash
printf '%s' 'aW1wb3J0IH...' | base64 -d > /tmp/_run_a1b2c3d4.py && python3 /tmp/_run_a1b2c3d4.py
```

Bu regex o kalıbı tanıyıp base64 kısmını (`group(1)`) ve dosya yolunu (`group(2)`) çıkarıyor.
Eşleşirse → Python kodu, kalıcı kernel'da çalıştır. Eşleşmezse → shell komutu.

**Neden bu ayrım önemli?** Kalıcı kernel'da çalışan Python kodundaki değişkenler
sonraki çağrılarda da yaşıyor. Shell komutu olarak çalışsa her seferinde yeni process
başlar — değişkenler kaybolur.

```python
class _ExecuteResult:
    def __init__(self, output: str, exit_code: int = 0):
        self.output = output
        self.exit_code = exit_code
```

**Neden bu wrapper sınıf?** Proje önce Daytona sandbox kullanıyordu. OpenSandbox'a geçince
mevcut araçları (execute.py, download_file.py) değiştirmemek için aynı arayüzü sağlayan
wrapper sınıflar yazdık. `result.output` ve `result.exit_code` her iki backend'de de çalışıyor.
Adapter pattern — mevcut kodu kırmadan backend değiştirme.

### 4.2 `OpenSandboxBackend` — Asıl İşi Yapan Sınıf

🔗 [**src/sandbox/manager.py:52-189** — OpenSandboxBackend](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L52-L189)

```python
class OpenSandboxBackend:
    def __init__(self, sandbox, interpreter, py_context):
        self._sandbox = sandbox            # Docker container yönetimi
        self._interpreter = interpreter    # CodeInterpreter API
        self._py_context = py_context      # KALICI KERNEL BAĞLAMI
```

**Üç farklı nesne — neden?**
- `sandbox`: Container'ın kendisi (dosya sistemi, shell komutları)
- `interpreter`: CodeInterpreter servisi (Python çalıştırma API'si)
- `py_context`: Belirli bir Python oturumu (değişkenler burada yaşıyor)

Analoji: `sandbox` = bilgisayar, `interpreter` = Python kurulumu, `py_context` = açık
bir Python REPL penceresi. REPL'de `x = 5` yazarsın, sonra `print(x)` yazarsın → 5 gelir.
İşte `py_context` o REPL.

#### `execute()` metodu — satır satır

🔗 [**src/sandbox/manager.py:96-155** — execute](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L96-L155)

```python
    def execute(self, command: str, timeout: int = 180) -> _ExecuteResult:
        try:
            m = _PYFILE_RE.search(command)    # ← Python kodu mu kontrol et
            if m:
                b64 = m.group(1).strip()
                py_code = base64.b64decode(b64).decode()   # ← Base64'ten çöz
```

**Neden `search` ve `match` değil?** `match` sadece string'in başında arar. Ama komut
`printf '%s' '...' | base64 -d > ...` ile başlıyor — öncesinde boşluk veya başka
karakterler olabilir. `search` string'in herhangi bir yerinde eşleşme arar.

```python
                pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = pool.submit(
                    self._interpreter.codes.run,
                    py_code, context=self._py_context,
                )
                try:
                    result = future.result(timeout=timeout)    # ← 180 saniye bekle
```

**Neden `ThreadPoolExecutor` ile sarmalıyoruz?** `codes.run()` senkron bir çağrı ve
kendi timeout mekanizması yok. Büyük bir dosya işlemi sonsuz süre takılabilir.
`future.result(timeout=180)` ile "180 saniye içinde bitmezse TimeoutError fırlat" diyoruz.

**Neden `max_workers=1`?** Aynı kernel bağlamında aynı anda iki kod çalıştıramazsın
(race condition). Tek worker yeterli.

```python
                except concurrent.futures.TimeoutError:
                    future.cancel()
                    pool.shutdown(wait=False)       # ← wait=True YAPMA!
```

**Neden `wait=False`?** `pool.shutdown(wait=True)` takılan thread'in bitmesini bekler —
ama thread zaten timeout oldu, bitmeyecek! `wait=False` ile pool'u bırakıyoruz.
Thread arka planda ölecek.

Yorumda da yazıyor: "Do NOT use 'with' block — pool.__exit__ calls shutdown(wait=True)
which blocks until the hung thread finishes." `with` kullanırsan sonsuz bekleme.

```python
                    self._reset_context()           # ← Takılan kernel'ı kurtarma
                    return _ExecuteResult(
                        output=f"Error: Code execution timed out after {timeout}s...",
                        exit_code=1,
                    )
```

Timeout sonrası eski kernel bağlamı "meşgul" durumda kalıyor. Yeni bir bağlam oluşturuyoruz.

```python
                else:
                    pool.shutdown(wait=False)        # ← Başarılıysa da beklemeden kapat

                output = result.text or ""
                if result.error:
                    err_msg = getattr(result.error, "value", str(result.error))
                    output = output + (f"\n{err_msg}" if output else err_msg)
                exit_code = 1 if result.error else 0
```

**Neden `getattr(result.error, "value", str(result.error))`?** `result.error` bazen
string, bazen bir hata nesnesi (`.value` alanı olan). İkisini de ele almak için
`getattr` ile güvenli erişim.

```python
            # Shell command path
            opts = RunCommandOpts(timeout=timedelta(seconds=timeout))
            result = self._sandbox.commands.run(command, opts=opts)
```

Python kodu değilse (regex eşleşmezse), doğrudan shell komutu olarak çalıştır.
`rm -f /tmp/...`, `echo CLEAN_OK` gibi komutlar buradan geçiyor.

#### `_reset_context()` — Takılan Kernel'ı Kurtarma

🔗 [**src/sandbox/manager.py:75-94** — _reset_context](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L75-L94)

```python
    def _reset_context(self):
        try:
            old_id = getattr(self._py_context, "id", None)
            if old_id:
                try:
                    self._interpreter.codes.delete_context(old_id)
                except Exception:
                    pass    # ← Silme başarısız olabilir — sorun değil
```

**Neden `try/except pass`?** Takılı bağlam "session is busy" durumunda. Silme isteği
de timeout olabilir veya reddedilebilir. Ama zaten yeni bağlam oluşturacağız — eski
silinmese bile sorun yok, garbage collection halleder.

```python
            self._py_context = self._interpreter.codes.create_context(
                SupportedLanguage.PYTHON
            )
```

Yeni, temiz bir Python oturumu. Eski değişkenler kayboldu ama en azından takılma
sona erdi.

#### `upload_files()` ve `download_files()`

🔗 [**src/sandbox/manager.py:157-189** — Upload/Download](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L157-L189)

```python
    def upload_files(self, files: list) -> list:
        class _Ok:
            error = None
        class _Err:
            def __init__(self, msg):
                self.error = msg
```

**Neden bu iç sınıflar?** Eski Daytona backend'inin döndüğü sonuç formatını taklit
ediyorlar. `_Ok` = başarılı yükleme, `_Err` = başarısız. Mevcut kodda `if resp.error:`
kontrolü var — bu iç sınıflar o kontrolü çalışır tutyor.

```python
        entries = []
        for path, data in files:
            if isinstance(data, str):
                data = data.encode()              # ← String'i bytes'a çevir
            entries.append(WriteEntry(path=path, data=data))
        self._sandbox.files.write_files(entries)
```

**Neden `isinstance(data, str)` kontrolü?** Bazen veri string olarak geliyor (metin
dosyaları), bazen bytes (Excel, PDF). `write_files` bytes bekliyor — string gelirse
encode ediyoruz.

### 4.3 `SandboxManager` — Yaşam Döngüsü

🔗 [**src/sandbox/manager.py:192-346** — SandboxManager](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L192-L346)

```python
class SandboxManager:
    def __init__(self):
        self._backend: OpenSandboxBackend | None = None
        self._sandbox: SandboxSync | None = None
        self._interpreter: CodeInterpreterSync | None = None
        self._py_context = None
        self._packages_ready = threading.Event()    # ← Senkronizasyon
        self._create_lock = threading.Lock()         # ← Yarış koşulu koruması
```

**Neden `threading.Event()`?** Sandbox oluşturma arka plan thread'inde (~5 saniye).
Ana thread "sandbox hazır mı?" diye sormak istiyor. `Event` tam bunu sağlıyor:
- Arka plan thread'i: `self._packages_ready.set()` → "hazırım!"
- Ana thread: `self._packages_ready.wait(timeout=30)` → "30 saniye bekle, hazır olmazsa devam et"

**Neden `threading.Lock()`?** İki thread aynı anda `get_or_create_sandbox()` çağırabilir
(Streamlit rerun + ön-ısıtma thread). Lock olmadan iki sandbox oluşturulabilir — kaynak
israfı ve bug.

#### `_create_new_sandbox()` — Sandbox Doğum Anı

🔗 [**src/sandbox/manager.py:222-269** — _create_new_sandbox](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L222-L269)

```python
    def _create_new_sandbox(self, thread_id: str) -> OpenSandboxBackend:
        sandbox = SandboxSync.create(
            "agentic-sandbox:v1",                    # ← Özel Docker image
            entrypoint=["/opt/opensandbox/code-interpreter.sh"],
            env={"PYTHON_VERSION": "3.11"},
            timeout=timedelta(hours=2),              # ← 2 saat ömür
        )
```

**Neden `"agentic-sandbox:v1"`?** Bu özel bir Docker image. İçinde tüm Python paketleri
(pandas, matplotlib, duckdb, weasyprint, vb.) önceden kurulu. Normal bir Python image
kullansak her sandbox'ta `pip install` gerekir — 35 saniye bekleme.
Önceden kurulu image ile sandbox 3-5 saniyede hazır.

**Neden `timeout=timedelta(hours=2)`?** Kullanıcı oturumu 2 saatten uzun sürmemeli.
2 saat sonra sandbox otomatik silinir — zombi container'lar birikmiyor.

```python
        interpreter = CodeInterpreterSync.create(sandbox)
        py_context = interpreter.codes.create_context(SupportedLanguage.PYTHON)
```

**İki adımlı oluşturma — neden?**
1. `CodeInterpreterSync.create(sandbox)` → Sandbox'taki CodeInterpreter servisine bağlan
2. `create_context(PYTHON)` → Yeni bir Python REPL oturumu başlat

Tek adımda yapılamıyor çünkü bir sandbox'ta birden fazla dil bağlamı olabilir (Python,
JavaScript, vb.). Biz sadece Python kullanıyoruz ama API genel.

```python
        # publish_html() helper'ı kernel'a enjekte et
        _INIT_CODE = (
            "def publish_html(html_str):\n"
            "    \"\"\"Write HTML dashboard to file for automatic rendering in the UI.\"\"\"\n"
            "    with open('/home/sandbox/__dashboard__.html', 'w', encoding='utf-8') as f:\n"
            "        f.write(html_str)\n"
            "    print('__PUBLISH_HTML__')\n"
        )
        interpreter.codes.run(_INIT_CODE, context=py_context)
```

**Neden bu fonksiyonu kernel'a enjekte ediyoruz?** Ajan dashboard oluşturduğunda HTML'i
doğrudan Streamlit'e gönderemez (farklı thread, farklı process). Ama kernel'daki bir
fonksiyon HTML'i dosyaya yazabilir ve stdout'a marker basabilir. `execute.py` bu marker'ı
yakalayıp HTML'i artifact store'a yönlendiriyor.

**Akış:**
1. Ajan: `publish_html("<div>Dashboard</div>")`
2. Kernel: HTML'i `/home/sandbox/__dashboard__.html`'e yaz
3. Kernel: stdout'a `__PUBLISH_HTML__` bas
4. `execute.py`: Marker'ı yakala → dosyayı oku → `ArtifactStore.add_html()` → dosyayı sil
5. Stream bitince: `store.pop_html()` → `components.html()` → iframe'de göster

```python
        self._packages_ready.set()     # ← "Hazırım!" sinyali
```

#### `clean_workspace()` — Yeni Konuşma için Sıfırlama

🔗 [**src/sandbox/manager.py:296-324** — clean_workspace](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L296-L324)

```python
    def clean_workspace(self):
        # 1. Dosyaları temizle
        self._backend.execute(
            f"rm -rf {SANDBOX_HOME}/* 2>/dev/null; "
            "rm -rf /tmp/_run_*.py 2>/dev/null; "
            "echo CLEAN_OK"
        )
```

**Neden `2>/dev/null`?** Dosya yoksa `rm` hata basar — ama bu normal, beklenen durum.
Hata çıktısını `/dev/null`'a yönlendirerek log'u kirletmiyoruz.

**Neden `echo CLEAN_OK`?** Temizlik başarılı mı kontrol etmek için. Çıktıda `CLEAN_OK`
varsa her şey temiz.

```python
        # 2. Kernel bağlamını sıfırla
        if self._interpreter is not None:
            try:
                self._interpreter.codes.delete_context(self._py_context.id)
            except Exception:
                pass
            self._py_context = self._interpreter.codes.create_context(
                SupportedLanguage.PYTHON
            )
            self._backend._py_context = self._py_context
```

**Neden kernel'ı sıfırlıyoruz?** Önceki konuşmadaki `df`, `m`, `plt` gibi değişkenler
hâlâ bellekte. Yeni konuşmada eski verilerle karışmamalı. Bağlamı silip yenisini
oluşturarak temiz bir başlangıç sağlıyoruz.

**Neden `self._backend._py_context = self._py_context`?** Backend nesnesi eski bağlama
referans tutuyor. Yeni bağlamı backend'e de iletmemiz lazım — yoksa backend eski (silinmiş)
bağlama kod göndermeye çalışır.

> 💡 **Container'ı neden öldürmüyoruz?** Yeni container = ~5 saniye bekleme. Bağlam
> sıfırlama = ~0.1 saniye. 50x daha hızlı. "Yeni Konuşma" butonuna basan kullanıcı
> 5 saniye beklemek istemez.

---

## Bölüm 5: Artifact Store

Şimdi kritik bir mimari sorun: **Ajan araçları thread pool'da çalışıyor, UI ana thread'de.
Nasıl konuşacaklar?**

### 5.1 Problem Detayı

```
Ana Thread (Streamlit):          Ajan Thread (LangChain):
  render_chat()                    execute() → PDF üret
  st.download_button(???)         download_file() → PDF bytes'ı var
                                  → st.session_state["downloads"] = ???
                                    ↑ PATLAMA! Thread-safe değil!
```

Streamlit'in `st.session_state`'i thread-safe değil. Ajan thread'inden erişirsen:
- En iyi ihtimal: Veri yarışı, bazen çalışır bazen çalışmaz
- En kötü ihtimal: Deadlock, uygulama donar

### 5.2 Çözüm: Lock Korumalı Global Store

🔗 [**src/tools/artifact_store.py** — Tam dosya (89 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/artifact_store.py)

```python
class ArtifactStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._pending_downloads: list[dict[str, Any]] = []
        self._pending_charts: list[dict[str, Any]] = []
        self._pending_html: list[str] = []
```

**Neden `threading.Lock()`?** Aynı anda iki thread (execute + generate_html aynı anda
çağrılabilir) listeye yazmaya çalışırsa veri bozulur. Lock ile "aynı anda sadece bir
thread yazabilir" garantisi sağlıyoruz.

```python
    def add_download(self, file_bytes: bytes, filename: str, path: str = "") -> None:
        with self._lock:
            # Dedup: aynı dosya adı zaten varsa ekleme
            if any(d["filename"] == filename for d in self._pending_downloads):
                return
            self._pending_downloads.append({
                "bytes": file_bytes,
                "filename": filename,
                "path": path,
            })
```

**Neden dedup kontrolü?** Ajan bazen aynı dosyayı iki kez indirmeye çalışıyor (retry
sonrası veya correction loop'ta). İki aynı download butonu göstermek kötü UX.

**Neden `with self._lock`?** `with` sözdizimi otomatik olarak lock'u alır ve blok
bittiğinde (hata olsa bile) serbest bırakır. Manuel `self._lock.acquire()` /
`self._lock.release()` kullansak, hata durumunda lock asla serbest kalmaz → deadlock.

```python
    def pop_downloads(self) -> list[dict[str, Any]]:
        with self._lock:
            items = self._pending_downloads[:]     # ← Kopya al
            self._pending_downloads.clear()         # ← Orijinali temizle
            return items
```

**Neden kopyalayıp temizliyoruz?** Bu "consume" pattern'i. Ana thread artifact'ları
alıp render ettikten sonra store'da kalmamalı — yoksa sayfa yenilendiğinde aynı
download butonları tekrar gösterilir.

**Neden `[:]` ile kopya?** `items = self._pending_downloads` desek referans kopyalanır.
Sonra `clear()` çağırdığımızda `items` da boşalır çünkü aynı listeyi gösteriyorlar.
`[:]` yeni bir liste oluşturur.

### 5.3 Per-Session Store — Neden Global Ama Session-Scoped?

🔗 [**src/tools/artifact_store.py:73-89** — Global yönetim](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/artifact_store.py#L73-L89)

```python
_stores: dict[str, ArtifactStore] = {}     # session_id → store
_stores_lock = threading.Lock()

def get_store(session_id: str) -> ArtifactStore:
    with _stores_lock:
        if session_id not in _stores:
            _stores[session_id] = ArtifactStore()
        return _stores[session_id]
```

**Neden modül seviyesinde global?** Araçlar factory fonksiyonlarla oluşturuluyor.
Factory fonksiyon `session_id`'yi closure'da tutuyor. Araç çağrıldığında
`get_store(session_id)` ile kendi oturumunun store'una erişiyor.

**Neden `_stores_lock`?** `_stores` dict'ine aynı anda iki thread yeni session
eklemeye çalışabilir. `dict` Python'da thread-safe değil (CPython'da GIL var ama
güvenilmez). Lock ile güvence altına alıyoruz.

```python
def release_store(session_id: str) -> None:
    with _stores_lock:
        _stores.pop(session_id, None)     # ← Varsa sil, yoksa hata verme
```

**Neden `pop(key, None)` ve `del` değil?** `del _stores[key]` key yoksa `KeyError` fırlatır.
`pop(key, None)` key yoksa sessizce `None` döner. `release_store` birden fazla kez
çağrılabilir (reset_session sırasında) — hata vermemeli.

---

## Bölüm 6: Araçlar (Tools)

5 araç var. Hepsi **factory pattern** kullanıyor. Neden?

### 6.0 Factory Pattern — Neden?

```python
# Alternatif 1: Global değişken (KÖTÜ)
_backend = None

@tool
def execute(command: str) -> str:
    return _backend.execute(command)      # ← Global'e bağımlı — test edilemez

# Alternatif 2: Parametre (KÖTÜ)
@tool
def execute(command: str, backend: OpenSandboxBackend) -> str:
    return backend.execute(command)       # ← LangChain backend'i nereden bilecek?
```

LangChain `@tool` fonksiyonlarını çağırırken sadece tool_call'daki parametreleri
geçiriyor. `backend` veya `session_id` gibi altyapı parametrelerini geçiremez.

```python
# Alternatif 3: Factory + Closure (DOĞRU)
def make_execute_tool(backend, session_id):
    @tool
    def execute(command: str) -> str:
        return backend.execute(command)   # ← backend closure'da yakalanmış
    return execute
```

Factory fonksiyon `backend`'i closure'da yakalıyor. Döndürdüğü `execute` fonksiyonu
LangChain'in beklediği imzaya sahip (`command: str`) ama içeride `backend`'e erişebiliyor.

> 💡 **Closure nedir?** İç fonksiyon, dış fonksiyonun değişkenlerine erişebilir — dış
> fonksiyon bitse bile. `make_execute_tool` return ettikten sonra `backend` değişkeni
> hâlâ `execute` fonksiyonunun "hafızasında" yaşıyor. Python'da fonksiyonlar
> `__closure__` attribute'unda bu referansları tutuyor.

### 6.1 `parse_file` — Yerel Dosya Şeması Çıkarma

🔗 [**src/tools/file_parser.py** — Tam dosya (327 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/file_parser.py)

**Neden bu araç sandbox'a GİTMİYOR?**

Sandbox'ta `pd.read_excel()` çalıştırmak:
1. Python kodunu base64'e çevir
2. Sandbox'a gönder
3. Container'da dosyayı oku
4. Sonucu geri gönder
→ ~2-3 saniye

Lokal'de aynı dosya zaten bellekte (Streamlit upload):
1. `pd.read_excel(io.BytesIO(file_bytes))`
→ ~0.1 saniye

20x daha hızlı. Ve execute kotasını tüketmiyor.

#### Factory fonksiyon — closure detayı

🔗 [**src/tools/file_parser.py:237-327** — make_parse_file_tool](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/file_parser.py#L237-L327)

```python
def make_parse_file_tool(uploaded_files: list | None = None):
    _files = uploaded_files if uploaded_files is not None else st.session_state.get("uploaded_files", [])
```

**Neden `uploaded_files` parametresi var?** Ajan araçları thread pool'da çalışıyor.
`st.session_state` ana thread'e ait — ajan thread'inden erişmek tehlikeli.
Bu yüzden factory çağrılırken dosya listesini closure'a yakalıyoruz.

**`if uploaded_files is not None` — neden `is not None` ve `if uploaded_files` değil?**
Boş liste `[]` falsy'dir. `if uploaded_files:` boş listeyi `None` gibi değerlendirir.
Ama boş liste geçerli bir değer — "dosya yok" demek. `None` ise "parametreyi vermedim,
fallback kullan" demek. İkisini ayırt etmek lazım.

```python
    @tool
    def parse_file(filename: str) -> str:
        uploaded_files = _files    # ← Closure'dan al, st.session_state'e DOKUNMA

        target = None
        for f in uploaded_files:
            if f.name == filename:
                target = f
                break
```

**Neden lineer arama?** Dosya sayısı genellikle 1-5. `dict` veya `set` kullanmak
gereksiz karmaşıklık. "Premature optimization is the root of all evil."

```python
        if target is None:
            available = [f.name for f in uploaded_files] if uploaded_files else []
            return f"File '{filename}' not found. Available files: {available}"
```

**Neden mevcut dosyaları gösteriyoruz?** Ajan bazen dosya adını yanlış hatırlıyor.
"sales.xlsx" yerine "Sales.xlsx" veya "data.xlsx" diyebiliyor. Mevcut dosya listesini
göstererek kendini düzeltmesini sağlıyoruz.

#### Excel tarih formatı tespiti — neden bu kadar detaylı?

🔗 [**src/tools/file_parser.py:38-172** — Excel parsing ve tarih tespiti](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/file_parser.py#L38-L172)

```python
def _excel_numfmt_to_strftime(number_format: str) -> str:
    if not number_format or number_format == 'General':
        return '%Y-%m-%d'

    nf = number_format.lower().strip()
    nf = nf.split(' hh')[0].split(' h:')[0].strip()   # ← Saat kısmını kes
```

**Neden saat kısmını kesiyoruz?** Excel'de `DD/MM/YYYY HH:MM:SS` formatı yaygın. Ama
biz raporda sadece tarihi göstermek istiyoruz. Saat kısmını kaldırıp sadece tarih
formatını çıkarıyoruz.

```python
    mappings = [
        ('mm/dd/yyyy', '%m/%d/%Y'),      # ABD formatı
        ('dd/mm/yyyy', '%d/%m/%Y'),      # Avrupa formatı
        ('yyyy-mm-dd', '%Y-%m-%d'),      # ISO formatı
        ('dd.mm.yyyy', '%d.%m.%Y'),      # Almanya/Türkiye formatı
        ...
    ]
```

**Neden bu kadar çok format?** Her ülke farklı tarih formatı kullanıyor. `01/02/2024`:
- ABD'de: 2 Ocak 2024
- Avrupa'da: 1 Şubat 2024

Yanlış format = yanlış analiz. Ajan Excel'in kendi formatını bilirse doğru yorumlar.

```python
def _parse_excel(file_bytes, filename):
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
```

**Neden `read_only=True`?** Dosyayı değiştirmeyeceğiz, sadece format bilgisini okuyacağız.
`read_only=True` bellek kullanımını %60-70 azaltır — büyük dosyalar için kritik.

**Neden `data_only=True`?** Excel formülleri var: `=SUM(A1:A100)`. `data_only=True` ile
formül yerine hesaplanmış değeri alıyoruz. Ajan formül stringi değil, gerçek sayıyı görmeli.

```python
    for col in df.columns:
        dtype = str(df[col].dtype)
        if dtype in ('datetime64[ns]', 'datetime64[us]'):
            col_idx = list(df.columns).index(col)
            ws = wb[sheet]
            for row in ws.iter_rows(min_row=2, max_row=6, min_col=col_idx+1, max_col=col_idx+1):
                for cell in row:
                    if cell.number_format and cell.number_format != 'General':
                        py_fmt = _excel_numfmt_to_strftime(cell.number_format)
```

**Neden 2-6. satırları kontrol ediyoruz?** 1. satır başlık. 2-6. satırlar veri satırları.
İlk birkaç hücrenin formatı tüm kolonu temsil eder. Tüm satırları kontrol etmek gereksiz.

#### Parse sonrası yönlendirme

🔗 [**src/tools/file_parser.py:281-322** — Yönlendirme mesajları](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/file_parser.py#L281-L322)

```python
    output += "✅ PARSE BAŞARILI. SONRAKI ADIM:\n\n"
    output += "❌ YAPMA: ls, cat, os.listdir, parse_file tekrar çağırma\n"
    output += "✅ YAP:\n"
    output += f"1. DÜŞÜNCE yaz: 'Schema alındı. Dosya /home/sandbox/{filename}...'\n"
    output += "2. execute() çağır:\n"
    output += f"   df = pd.read_excel('/home/sandbox/{filename}')\n"
```

**Neden bu kadar açık yönlendirme?** Claude bazen `parse_file`'dan sonra `ls` veya tekrar
`parse_file` çağırıyor. Çıktının sonuna "BUNU YAPMA, BUNU YAP" yazarak bu davranışı
%90+ azaltıyoruz. LLM'ler son gördükleri metne göre hareket etmeye meyilli (recency bias)
— çıktının sonuna koyduğumuz talimat en etkili yerde.

```python
    if size_mb >= 40:
        output += "⚠️ BÜYÜK DOSYA — DUCKDB STRATEJİSİ ZORUNLU..."
```

**Neden 40MB eşiği?** Deneysel: 40MB altında pandas hızlı çalışıyor (~2-5 saniye).
40MB üstünde pandas bellek tüketimi kritik seviyeye çıkıyor (dosya boyutunun ~3-5x'i
RAM kullanır). DuckDB lazy evaluation ile sadece gerekli kısmı okur — 40MB dosyada bile
100MB altında RAM kullanır.

### 6.2 `execute` — Kod Çalıştırma

🔗 [**src/tools/execute.py** — Tam dosya (165 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/execute.py)

#### Python kodu tespiti — iki katmanlı

🔗 [**src/tools/execute.py:19-51** — Kod tespiti](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/execute.py#L19-L51)

```python
_PY_INLINE_RE = re.compile(
    r"""^python3?\s+-c\s+(['"])(.*)\1\s*$""",
    re.DOTALL,
)
```

**Regex açıklaması:**
- `^python3?` → "python" veya "python3" ile başla
- `\s+-c\s+` → `-c` flag'i (inline kod)
- `(['"])` → Açılış tırnağını yakala (group 1)
- `(.*)` → Kod içeriğini yakala (group 2)
- `\1` → Aynı tırnakla kapat (backreference)
- `re.DOTALL` → `.` karakteri `\n`'i de eşleştirsin (çok satırlı kod)

```python
def _unescape_shell(code: str, quote_char: str) -> str:
    if quote_char == '"':
        code = code.replace('\\"', '"').replace('\\\\', '\\')
    return code
```

**Neden unescape?** Shell'de çift tırnak içinde `\"` ve `\\` escape edilir.
Python kodunda `print("hello")` yazılırsa shell'e `print(\"hello\")` olarak geçer.
Biz geri çeviriyoruz. Tek tırnak içinde escape yok — olduğu gibi bırak.

```python
def _extract_python_code(command: str) -> str | None:
    m = _PY_INLINE_RE.match(command.strip())
    if m:
        return _unescape_shell(m.group(2), m.group(1))

    # Fallback: python3 -c prefix'i var ama regex eşleşmedi
    for prefix in ("python3 -c ", "python -c "):
        if command.strip().startswith(prefix):
            code = command.strip()[len(prefix):]
            ...
            return code if len(code) > 10 else None
    return None
```

**Neden fallback?** Regex bazen eşleşmiyor — tırnak dengesizliği, escape sorunları.
Fallback basit string kesme ile kodu çıkarıyor. `len(code) > 10` kontrolü yanlış
pozitifları önlüyor — 10 karakterden kısa "kod" muhtemelen kod değil.

#### İkinci katman — ham Python kodu tespiti

🔗 [**src/tools/execute.py:80-90** — Raw Python detection](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/execute.py#L80-L90)

```python
            if not py_code:
                stripped = command.strip()
                _PY_STARTS = ("import ", "from ", "print(", "def ", "class ",
                              "# ", "try:", "with ", "for ", "if ", "df ", "df=",
                              "pdf ", "pdf=", "result ", "result=",
                              "pd.", "np.", "plt.", "total_", "assert ", ...)
                if any(stripped.startswith(p) for p in _PY_STARTS):
                    py_code = stripped
```

**Neden bu?** Ajan bazen `python3 -c` prefix'i olmadan doğrudan Python kodu gönderiyor:
```python
df = pd.read_excel('/home/sandbox/data.xlsx')
print(df.shape)
```

Bu shell komutu olarak çalıştırılırsa `df: command not found` hatası alırsın.
`_PY_STARTS` listesi ile "bu Python kodu" diyip yönlendiriyoruz.

**Neden `"df "` ve `"df="` ayrı?** `df = pd.read_excel(...)` (boşluklu) ve
`df=pd.read_excel(...)` (boşluksuz) ikisi de geçerli Python. İkisini de yakalıyoruz.

#### Base64 kodlama — kritik mekanizma

🔗 [**src/tools/execute.py:92-97** — Base64 encoding](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/execute.py#L92-L97)

```python
            if py_code:
                b64 = base64.b64encode(py_code.encode()).decode()
                tmp_path = f"/tmp/_run_{uuid.uuid4().hex[:8]}.py"
                shell_cmd = f"printf '%s' '{b64}' | base64 -d > {tmp_path} && python3 {tmp_path} && rm -f {tmp_path}"
```

**Neden base64?** Python kodu şunları içerebilir:
- Tek tırnak: `print('hello')`
- Çift tırnak: `df["column"]`
- Dolar işareti: `f"${total}"`
- Yeni satır: `\n`
- Backslash: `\\n`

Bunların hepsi shell'i bozar. Base64'e çevirince sadece `A-Z`, `a-z`, `0-9`, `+`, `/`, `=`
kalır — shell-safe.

**Neden `uuid.uuid4().hex[:8]`?** Benzersiz dosya adı. Eşzamanlı çalıştırmalarda
çakışma olmasın. 8 hex karakter = 4.3 milyar kombinasyon — yeterli.

**Neden `&& rm -f {tmp_path}`?** Geçici dosyayı temizle. Birikmesini önle.
`-f` flag'i: dosya yoksa hata verme.

#### publish_html() otomatik tespiti

🔗 [**src/tools/execute.py:142-158** — HTML marker tespiti](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/execute.py#L142-L158)

```python
_HTML_MARKER = "__PUBLISH_HTML__"
_HTML_PATH = "/home/sandbox/__dashboard__.html"

# ... execute sonrası:
            if output and _HTML_MARKER in output:
                try:
                    html_result = backend.execute(f"cat {_HTML_PATH}")
                    html_content = getattr(html_result, "output", "")
                    if html_content and html_content.strip():
                        from src.tools.generate_html import inject_height_script
                        from src.tools.artifact_store import get_store
                        get_store(session_id).add_html(inject_height_script(html_content))
                        backend.execute(f"rm -f {_HTML_PATH}")
```

**Tam akış:**
1. Kernel'da `publish_html(html)` çağrılır → dosyaya yazar + marker basar
2. `execute.py` çıktıda `__PUBLISH_HTML__` görür
3. `cat` ile dosyayı okur
4. Height script enjekte eder (iframe yüksekliği için)
5. Artifact store'a ekler
6. Geçici dosyayı siler
7. Marker'ı çıktıdan temizler
8. "✅ HTML dashboard rendered successfully." ekler

**Neden marker-based ve doğrudan değil?** Kernel'ın stdout'u string. İçinde hem
normal print çıktıları hem de HTML olabilir. Marker ile "bu satırdan sonra HTML var"
demek yerine "HTML'i dosyaya yazdım, bak" diyoruz. Dosya-tabanlı yaklaşım HTML'i
stdout'tan ayırıyor.

### 6.3 `generate_html` — HTML İframe Render

🔗 [**src/tools/generate_html.py** — Tam dosya (57 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/generate_html.py)

```python
HEIGHT_SCRIPT = """
<script>
  function _reportHeight() {
    const h = document.body.scrollHeight;
    window.parent.postMessage({type: 'streamlit:setFrameHeight', height: h}, '*');
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _reportHeight);
  } else {
    _reportHeight();
  }
</script>
"""
```

**Neden bu script?** Streamlit'in `components.html()` iframe kullanıyor. İframe
sabit yükseklikte — içerik uzunsa kesilir, kısaysa boşluk kalır. Bu script
`postMessage` ile Streamlit'e "benim gerçek yüksekliğim X piksel" diyor.
Streamlit iframe'i otomatik ayarlıyor.

**Neden `readyState` kontrolü?** Script DOM yüklenmeden önce çalışırsa `body.scrollHeight`
yanlış değer verir (0 veya kısmi). `DOMContentLoaded` event'ini bekleyerek doğru
yüksekliği garantiliyoruz. Script geç enjekte edildiyse DOM zaten hazır — hemen çalış.

### 6.4 `download_file` — Dosya İndirme

🔗 [**src/tools/download_file.py** — Tam dosya (110 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/download_file.py)

```python
    ALLOWED_PREFIX = SANDBOX_HOME + "/"
    if not file_path.startswith(ALLOWED_PREFIX):
        return f"❌ Only files under {ALLOWED_PREFIX} can be downloaded."
```

**Güvenlik kontrolü — neden?** Ajan hallüsinasyon yapıp `/etc/passwd` veya
`/root/.ssh/id_rsa` indirmeye çalışabilir. Path prefix kontrolü bunu önlüyor.
Sadece `/home/sandbox/` altı indirilebilir.

#### Excel tarih temizleme — detaylı açıklama

🔗 [**src/tools/download_file.py:17-62** — _clean_excel_dates](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/download_file.py#L17-L62)

```python
def _clean_excel_dates(content: bytes) -> bytes:
    wb = load_workbook(io.BytesIO(content))
    for ws in wb.worksheets:
        for col in ws.iter_cols(min_row=2, max_row=ws.max_row):
            cells_with_dates = [c for c in col if isinstance(c.value, datetime)]
            if not cells_with_dates:
                continue

            all_midnight = all(
                c.value.hour == 0 and c.value.minute == 0 and c.value.second == 0
                for c in cells_with_dates
            )
            if all_midnight:
                for c in cells_with_dates:
                    c.value = c.value.date()         # datetime → date
                    c.number_format = 'YYYY-MM-DD'
```

**Sorun ne?** pandas `datetime64` tipini Excel'e yazarken `2024-01-15 00:00:00` olarak
yazar. Kullanıcı Excel'de "00:00:00" görünce "bu ne?" diye soruyor.

**Çözüm mantığı:** TÜM değerler gece yarısıysa (saat/dakika/saniye = 0), bu kolon
aslında sadece tarih — saat kısmı anlamsız. `datetime → date` çevrimi yapıp format'ı
`YYYY-MM-DD` olarak ayarlıyoruz.

**Neden tüm değerler kontrol?** Eğer bazı hücreler `14:30:00` gibiyse, bu kolon
gerçekten datetime — saat bilgisi önemli. O zaman dokunmuyoruz.

### 6.5 `create_visualization` — Statik Grafikler

🔗 [**src/tools/visualization.py** — Tam dosya (60 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/visualization.py)

```python
    wrapped_code = code + "\nimport matplotlib; matplotlib.pyplot.close('all')"
```

**Neden `plt.close('all')` ekliyoruz?** matplotlib figürleri bellekte kalır. 10 grafik
oluşturursan 10 figür birikir. Sandbox'ın sınırlı belleğinde bu sorun yaratır.
Her grafik sonrası temizlik.

```python
    responses = backend.download_files([f"{SANDBOX_HOME}/chart.png"])
    resp = responses[0] if responses else None
    if resp and resp.content and not resp.error:
        get_store(session_id).add_chart(resp.content, code)
```

**Neden `code`'u da saklıyoruz?** UI'da "Show code" butonu var — kullanıcı grafiğin
altında nasıl üretildiğini görebilir. Eğitim amaçlı.

---

## Bölüm 7: Skill Sistemi

### 7.1 Problem: One-Size-Fits-All Prompt

Tüm kuralları her zaman sisteme prompt'una koysak:
- Excel kuralları (~500 satır)
- CSV kuralları (~200 satır)
- PDF kuralları (~150 satır)
- DuckDB kuralları (~300 satır)
- Çoklu dosya JOIN kuralları (~200 satır)
- Görselleştirme kuralları (~150 satır)

= ~1,500 satır ekstra prompt. Claude'un context window'u sınırlı. Bu kadar kural:
1. Token maliyetini artırır
2. Ajanın odağını dağıtır — Excel analizi yaparken PDF kurallarını okuması gereksiz
3. Çelişkili kurallar kafa karıştırır

### 7.2 Çözüm: Progressive Disclosure

🔗 [**src/skills/registry.py** — Tam dosya (117 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/skills/registry.py)

```python
SKILL_TRIGGERS: dict[str, dict] = {
    "xlsx": {
        "extensions": [".xlsx", ".xls", ".xlsm"],    # ← Dosya uzantısı tetikleme
        "keywords": ["excel", "spreadsheet"],         # ← Anahtar kelime tetikleme
        "skill_path": "skills/xlsx/SKILL.md",
        "references": {
            "large_files": {
                "path": "skills/xlsx/references/large_files.md",
                "triggers": {
                    "file_size_mb": 40,               # ← Boyut tetikleme
                    "keywords": ["duckdb", "million rows", "out of memory"],
                },
            },
            "multi_file_joins": {
                "path": "skills/xlsx/references/multi_file_joins.md",
                "triggers": {
                    "min_files": 2,                   # ← Dosya sayısı tetikleme
                    "keywords": ["join", "merge"],
                },
            },
        },
    },
```

**4 tetikleme mekanizması:**
1. **Dosya uzantısı:** `.xlsx` → xlsx skill
2. **Anahtar kelime:** "dashboard" → visualization skill
3. **Dosya boyutu:** ≥40MB → large_files referansı
4. **Dosya sayısı:** 2+ Excel → multi_file_joins referansı

```python
def detect_required_skills(uploaded_files, user_query=""):
    required_skills: set[str] = set()        # ← set: duplicate önle

    for file in uploaded_files:
        ext = "." + file.name.rsplit(".", 1)[-1].lower()
        for skill_name, config in SKILL_TRIGGERS.items():
            if ext in config["extensions"]:
                required_skills.add(skill_name)
```

**Neden `rsplit(".", 1)`?** `file.name = "data.v2.xlsx"`. `split(".")` → `["data", "v2", "xlsx"]`.
`rsplit(".", 1)` → `["data.v2", "xlsx"]`. Sağdan bölerek son uzantıyı doğru alıyoruz.

```python
    if user_query:
        query_lower = user_query.lower()
        for skill_name, config in SKILL_TRIGGERS.items():
            if skill_name not in required_skills:      # ← Zaten varsa ekleme
                if any(kw in query_lower for kw in config["keywords"]):
                    required_skills.add(skill_name)
```

**Neden `skill_name not in required_skills` kontrolü?** Dosya uzantısı zaten xlsx skill'i
tetiklediyse, sorguda "excel" kelimesi geçse bile tekrar eklemeye çalışmaya gerek yok.

### 7.3 Loader — Prompt Derleme

🔗 [**src/skills/loader.py** — Tam dosya (86 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/skills/loader.py)

```python
@lru_cache(maxsize=32)
def load_skill(skill_name: str) -> dict | None:
    skill_path = Path(f"skills/{skill_name}/SKILL.md")
```

**Neden `lru_cache`?** Aynı skill dosyası her sorguda yeniden okunmasın. Dosya disk'ten
okunuyor — cache'le ~0.001ms, cache'siz ~5ms. 32 farklı skill cache'leniyor (şu an 4
var, gelecekte artabilir).

```python
    content = skill_path.read_text(encoding="utf-8")
    if content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        if end != -1:
            frontmatter = yaml.safe_load(content[4:end])    # ← YAML metadata
            instructions = content[end + 5:]                 # ← Markdown kurallar
```

**YAML frontmatter nedir?** Jekyll/Hugo gibi statik site oluşturuculardan ödünç alınmış
bir kalıp. Dosyanın başında `---` ile çevrili YAML metadata, sonra Markdown içerik:

```yaml
---
name: Excel Analysis
description: Rules for analyzing Excel files
---
# Excel Analiz Kuralları
1. Önce parse_file çağır
...
```

```python
def compose_system_prompt(base_prompt, active_skills, uploaded_files=None, user_query=""):
    prompt_parts = [base_prompt]

    for skill_name in active_skills:
        skill = load_skill(skill_name)
        prompt_parts.append(f"# {skill['name']} Expertise\n\n{skill['instructions']}")

        # Progressive disclosure: sadece tetiklenen referansları yükle
        ref_paths = detect_reference_files(skill_name, uploaded_files, user_query)
        for ref_path in ref_paths:
            ref_content = load_reference(ref_path)
            prompt_parts.append(f"## {ref_name} (Reference)\n\n{ref_content}")

    return "\n\n".join(prompt_parts)
```

**Sonuç:** Prompt boyutu duruma göre değişiyor:

| Senaryo | Prompt boyutu |
|---------|--------------|
| Küçük Excel | ~base + 500 satır |
| 50MB Excel | ~base + 800 satır (+DuckDB) |
| 2 Excel + "merge" | ~base + 900 satır (+JOIN) |
| Sadece "dashboard" | ~base + 150 satır |

---

## Bölüm 8: Sistem Prompt'u

🔗 [**src/agent/prompts.py** — Tam dosya (696 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/prompts.py)

696 satır. Neden bu kadar uzun? Çünkü LLM'ler kuralları "unutuyor" — aynı kuralı farklı
açılardan, farklı örneklerle tekrar etmek uyumluluğu artırıyor.

### 8.1 Sayı Yasağı — Neden?

🔗 [**src/agent/prompts.py:34-42** — Chat message rules](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/prompts.py#L34-L42)

```
- NEVER use numbers, ratios, percentages in text summaries
- ✅ OK: "Analysis complete, Excel ready."
- ❌ FORBIDDEN: "Suzanne Collins leads with 278,329 reviews..."
```

**Neden sayı yasağı?** Claude bazen hallüsinasyon yapıyor — önceki çıktıdaki sayıları
yanlış hatırlıyor veya uydurma sayılar yazıyor. Raporda (PDF/Excel) sayılar gerçek
hesaplamadan geliyor. Ama sohbet mesajında ajan "hatırlayarak" yazıyor — ve bu
güvenilmez.

Çözüm radikal: **Sohbette sayı yazma, noktası.** Sayılar sadece dosyalarda olsun.

### 8.2 Hardcoded Veri Yasağı — En Kritik Kural

🔗 [**src/agent/prompts.py:198-269** — RULE 3.5](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/prompts.py#L198-L269)

Bu kural 70 satır. Neden bu kadar uzun? Çünkü bu en yaygın hata:

1. Ajan Execute #3'te: `print(m)` → `{'total_customers': 5863, ...}`
2. Ajan Execute #4'te: `m = {'total_customers': 5863}` ← **KOPYALADI!**

Sorun: Ajan sayıyı çıktıdan kopyaladı. Eğer veri değişirse (yeni satır eklendi,
filtre değişti), bu sayı yanlış olur ama ajan farketmez.

Çözüm:
1. **Prompt'ta yasak** (RULE 3.5): "ASLA literal sayı yazma"
2. **Prompt'ta değer yazdırma yasağı** (RULE 3.6): `print(m)` YASAK, `print(list(m.keys()))` yaz
3. **Interceptor'da tespit** (graph.py): Regex ile hardcoded sayıları yakala

Üç katmanlı savunma — çünkü tek katman yetmiyor.

### 8.3 Kernel Güveni — Neden Bu Kadar Vurgulanıyor?

🔗 [**src/agent/prompts.py:245-269** — Kernel confidence](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/prompts.py#L245-L269)

```
✅ TRUST — These variables persist forever within the session:
- DataFrame df from Execute #1 → available in Execute #5, #6, #7, even #10
- Dict m from Execute #3 → available in Execute #7 (dashboard step)
```

Claude bazen "emin olamıyorum, tekrar hesaplayayım" diye veriyi tekrar okuyor.
Bu execute kotasını boşa harcıyor. Prompt'ta "GÜVEN, değişkenler yaşıyor" diye
tekrar tekrar söylüyoruz.

---

## Bölüm 9: Ajan Beyni

🔗 [**src/agent/graph.py** — Tam dosya (629 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py)

### 9.1 Dinamik Execute Limiti

🔗 [**src/agent/graph.py:75-92** — _compute_max_execute](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L75-L92)

```python
_COMPLEX_KEYWORDS = (
    "rfm", "cohort", "trend", "korelasyon", "forecast", "predict",
    "segment", "cluster", "cross-sell", "basket", ...
)

def _compute_max_execute(user_query, uploaded_files):
    is_complex = any(kw in query_lower for kw in _COMPLEX_KEYWORDS)
    is_large = total_size > 10 * 1024 * 1024
    return 10 if (is_complex or is_large) else 6
```

**Neden dinamik?** Basit sorular ("bu dosyayı özetle") 3-4 execute'da biter. Karmaşık
analizler ("RFM segmentasyonu yap, her segment için dashboard") 8-10 execute ister.
Sabit limit 6 olsa karmaşık analizler yarım kalır. Sabit limit 10 olsa basit sorularda
maliyet artar (ajan gereksiz execute yapar).

**Neden 10MB eşiği?** Büyük dosyalar daha çok adım gerektirir: CSV'ye çevirme, DuckDB
sorguları, chunk processing. 10MB üstü dosyalarda ekstra execute hakkı veriyoruz.

### 9.2 Smart Interceptor — Detaylı

🔗 [**src/agent/graph.py:140-572** — Smart interceptor](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L140-L572)

#### Closure değişkenleri — neden closure?

```python
    _seen_parse_files: set[str] = set()
    _execute_count = 0
    _max_execute = _compute_max_execute(user_query, uploaded_files)
    _total_blocked = 0
    _consecutive_blocks = 0
```

**Neden instance variable değil?** Interceptor bir `@wrap_tool_call` dekoratörü ile
sarmalanmış fonksiyon. LangChain middleware sistemi fonksiyon bekliyor, sınıf değil.
Closure değişkenleri fonksiyonun "özel belleği" oluyor.

#### `reset_interceptor_state()` — Neden kritik?

🔗 [**src/agent/graph.py:152-166** — Reset](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L152-L166)

```python
    def reset_interceptor_state():
        nonlocal _execute_count, _total_blocked, _last_execute_failed, ...
        _execute_count = 0
        _total_blocked = 0
        _consecutive_blocks = 0
        _seen_parse_files.clear()
```

**Senaryo:** Kullanıcı ilk mesajda 5 execute kullanıyor. İkinci mesaj gönderdiğinde
`_execute_count` hâlâ 5. Limit 6 ise sadece 1 hakkı kalır — YANLIŞ!

`reset_fn()` her yeni mesajdan önce çağrılarak sayaçlar sıfırlanıyor. Bu çağrı
`chat.py`'de yapılıyor (satır 610).

**Neden `nonlocal`?** Python'da iç fonksiyon dış fonksiyonun değişkenlerini okuyabilir ama
**yazamaz** (UnboundLocalError). `nonlocal` ile "bu değişken dış scope'ta, yazma izni ver"
diyoruz.

#### Kural 1: Circuit Breaker

🔗 [**src/agent/graph.py:178-188** — Circuit breaker](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L178-L188)

```python
        if _consecutive_blocks >= _MAX_CONSECUTIVE_BLOCKS:  # 3
            return ToolMessage(
                content="🛑 CIRCUIT BREAKER: ... You are in an infinite loop. STOP NOW.",
                tool_call_id=tool_call_id,
            )
```

**Senaryo:** Ajan `ls` çağırıyor → engelleniyor → `os.listdir` çağırıyor → engelleniyor
→ `glob.glob` çağırıyor → engelleniyor → sonsuz döngü!

3 ardışık engelleme sonrası "SONSUZ DÖNGÜDESÍN, DUR" mesajı. Ajan başka araç çağıramaz.

**Neden `_consecutive_blocks` ve `_total_blocked` ayrı?** `_consecutive_blocks` ardışık
engellemeyi sayar — başarılı bir execute sıfırlar. `_total_blocked` toplam engellemeyi
sayar — hiç sıfırlanmaz. İkisi farklı senaryolarda kullanılıyor.

#### Kural 5: Hardcoded Veri Tespiti — en karmaşık kural

🔗 [**src/agent/graph.py:251-308** — Hardcoded data detection](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L251-L308)

```python
            _data_access_ops = (".tolist()", ".values", "groupby", ".sum()",
                                ".mean()", ".count()", ".nunique()", "duckdb.sql",
                                "len(", "int(", "float(", ...)
```

Bu liste "gerçek veri erişim operasyonları". Bunlardan biri kodda varsa → sayılar
gerçek veriden geliyor. Yoksa → hardcoded.

```python
            def _is_hardcoded_assignment(match_text):
                return not any(da in match_text for da in _data_access_ops)
```

**Örnek:**
- `m = {'total': df['ID'].nunique()}` → `.nunique()` var → OK
- `m = {'total': 5863}` → hiçbir data_access_op yok → ENGELLE

```python
            # Dict assignments: var = {...1234...}
            _hc_dicts = [m for m in re.finditer(
                r'\w+\s*=\s*\{[^}]*\b\d{3,}\b[^}]*\}', cmd
            ) if _is_hardcoded_assignment(m.group())]
```

**Regex açıklaması:**
- `\w+` → değişken adı
- `\s*=\s*` → atama
- `\{[^}]*` → açılış süslü parantez + içerik
- `\b\d{3,}\b` → 3+ basamaklı sayı (word boundary ile)
- `[^}]*\}` → kapanış süslü parantez

**Neden `\d{3,}` (3+ basamak)?** Küçük sayılar genellikle sabit:
`{'top_n': 5}` → UI parametresi, OK. `{'total': 5863}` → muhtemelen hardcoded metrik.

#### Kural 11: Font Otomatik Düzeltme

🔗 [**src/agent/graph.py:410-469** — Font auto-fix](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L410-L469)

```python
            is_pdf_code = "fpdf" in cmd.lower() or "FPDF" in cmd
            if is_pdf_code:
                for bad_font in ("Arial", "Helvetica"):
                    if bad_font in cmd:
                        cmd = cmd.replace(f"'{bad_font}'", "'DejaVu'")
```

**Neden otomatik düzeltme?** Claude "Arial" fontu kullanmayı seviyor — yaygın ve tanıdık.
Ama sandbox'ta Arial yok (lisans sorunu). DejaVu fontları yüklü. Her seferinde hata
verip ajanı düzeltmeye zorlamak yerine otomatik değiştiriyoruz — execute kotası harcanmıyor.

```python
                if "DejaVu" in cmd and "add_font" not in cmd:
                    font_setup = (
                        "pdf.add_font('DejaVu', '', '/home/sandbox/DejaVuSans.ttf', uni=True)\n"
                        "pdf.add_font('DejaVu', 'B', '/home/sandbox/DejaVuSans-Bold.ttf', uni=True)\n"
                    )
                    cmd = re.sub(r'(pdf\.add_page\(\))', r'\1\n' + font_setup, cmd, count=1)
```

**Neden `add_page()` sonrasına enjekte?** FPDF'de font ekleme `add_page()` sonrası
yapılmalı. Regex ile `add_page()` satırını bulup hemen sonrasına font kurulumunu ekliyoruz.
`count=1` → sadece ilk eşleşmede (birden fazla `add_page` olabilir).

#### Execute sonrası bilgi ekleme

🔗 [**src/agent/graph.py:528-568** — Post-execute metadata](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L528-L568)

```python
        if name == "execute" and isinstance(result, ToolMessage):
            remaining = _max_execute - _execute_count

            has_error = any(kw in content for kw in (
                "Error", "Traceback", "AssertionError", ...
            ))

            if has_error:
                _correction_count += 1
                if _correction_count < _MAX_CORRECTIONS:
                    suffix = f"🔄 CORRECTION {_correction_count}/3 — THINK: what failed"
                else:
                    suffix = f"⛔ CORRECTION LIMIT. SKIP this, inform user."
```

**Neden correction loop limiti?** Ajan bazen aynı hatayı 10 kez düzeltmeye çalışır —
her seferinde execute kotası harcanır. 3 deneme sonrası "bırak, kullanıcıya söyle" diyoruz.

```python
            if remaining <= 2:
                suffix += " ⚠️ Last executes — combine analysis+PDF in single script."
```

**Neden son 2'de uyarı?** Ajan genellikle analiz ve PDF üretimini ayrı execute'larda
yapıyor. Ama kota azaldığında birleştirmeli — yoksa analiz yapıp PDF üretemez.

### 9.3 Middleware Zinciri

🔗 [**src/agent/graph.py:574-597** — Middleware ve ajan oluşturma](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L574-L597)

```python
    middleware = [
        create_summarization_middleware(model, backend),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
        PatchToolCallsMiddleware(),
        smart_interceptor,
    ]
```

**Sıralama önemli — aşağıdan yukarıya çalışır:**
1. İstek gelir → `smart_interceptor` (en altta, ilk çalışan)
2. → `PatchToolCallsMiddleware` (araç çağrısı format düzeltmeleri)
3. → `AnthropicPromptCachingMiddleware` (tekrar eden prompt'ları cache'le — maliyet ↓)
4. → `create_summarization_middleware` (uzun konuşmaları özetle — context window)

```python
    agent = agent.with_config({"recursion_limit": REACT_MAX_ITERATIONS * 2 + 1})
```

**Neden `* 2 + 1`?** LangGraph'ta her ReAct adımı = 2 node transition (ajan node + araç node).
30 iterasyon = 60 transition. `+1` güvenlik marjı.

### 9.4 Ajan Önbellekleme

🔗 [**src/agent/graph.py:600-629** — get_or_build_agent](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L600-L629)

```python
    file_fingerprint = tuple(
        (f.name, len(f.getvalue())) for f in (uploaded_files or [])
    )
    cached = st.session_state.get("_agent_cache")
    if cached and cached["fingerprint"] == file_fingerprint:
        return cached["agent"], cached["checkpointer"], cached["reset_fn"]
```

**Neden fingerprint?** Aynı dosyalarla çalışıyorsak ajanı yeniden oluşturmaya gerek yok
(skill'ler değişmedi, araçlar aynı). `(dosya_adı, dosya_boyutu)` tuple'ı yeterli bir
fingerprint — dosya içeriğini hash'lemek gereksiz yavaş olur.

**Neden boyut kontrol?** Aynı isimle farklı içerik yüklenebilir. Boyut değiştiyse
muhtemelen farklı dosya — ajanı yeniden oluştur.

---

## Bölüm 10: Kullanıcı Arayüzü

### 10.1 Oturum Yönetimi

🔗 [**src/ui/session.py** — Tam dosya (154 satır)](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/session.py)

```python
class MockUploadedFile:
    def __init__(self, name, size, data):
        self.name = name
        self.size = size
        self._data = data if isinstance(data, bytes) else data.encode()

    def getvalue(self):
        return self._data

    def seek(self, pos):
        pass    # ← Gerçek seek yok — tüm veri bellekte
```

**Neden bu sınıf?** Geçmiş konuşmaya dönerken dosyalar DB'den yükleniyor (BLOB).
Ama kodun geri kalanı Streamlit'in `UploadedFile` arayüzünü bekliyor: `.name`,
`.size`, `.getvalue()`, `.seek()`. `MockUploadedFile` bu arayüzü taklit ediyor.

**Neden `seek()` boş?** DB'den yüklenen dosya zaten tamamen bellekte. `BytesIO` gibi
stream pozisyonu yok. `getvalue()` her zaman tüm veriyi döndürüyor. `seek(0)` çağrıları
(file_parser.py'deki gibi) sessizce göz ardı ediliyor — zararı yok.

#### Ön-ısıtma mekanizması

🔗 [**src/ui/session.py:86-104** — Pre-warming thread](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/session.py#L86-L104)

```python
    if "sandbox_manager" not in st.session_state:
        st.session_state["sandbox_manager"] = SandboxManager()

    def _pre_warm():
        try:
            sandbox_manager.get_or_create_sandbox(session_id)
        except Exception as e:
            logger.error("Pre-warm failed: %s", e)

    t = threading.Thread(target=_pre_warm, daemon=True, name="sandbox-prewarm")
    t.start()
```

**Neden daemon thread?** `daemon=True` → ana program kapanırsa bu thread de kapanır.
Zombie thread bırakmaz. Ön-ısıtma kritik değil — başarısız olursa kullanıcı soru
sorduğunda tekrar denenir.

**Neden arka planda?** Sandbox oluşturma ~5 saniye. Bu 5 saniyeyi kullanıcının
dosya yüklemesi veya düşünmesi sırasında harcıyoruz. Soru sorduğunda sandbox hazır.

### 10.2 Chat — Stream İşleme

🔗 [**src/ui/chat.py:494-721** — render_chat](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L494-L721)

```python
    # Interceptor sayaçlarını sıfırla — KRİTİK!
    reset_fn()

    # Stream başlat
    for chunk in agent.stream(
        {"messages": [{"role": "user", "content": user_query}]},
        config={"configurable": {"thread_id": session_id}},
        stream_mode="updates",
    ):
        _process_stream_chunk(chunk, rendered_ids, exec_manager)
```

**Neden `stream_mode="updates"`?** Alternatifler:
- `"values"`: Her adımda tüm mesaj geçmişini döner → büyük payload, yavaş
- `"updates"`: Sadece değişen kısmı döner → küçük payload, hızlı

Biz sadece yeni eklenen mesajları görmek istiyoruz. "updates" tam bunu veriyor.

```python
    # Stream bittikten sonra artifact'ları topla
    _store = get_store(session_id)
    collected_html = _store.pop_html()
    collected_charts = _store.pop_charts()
    collected_downloads = _store.pop_downloads()

    _render_artifacts(collected_html, collected_charts, collected_downloads)
```

**Neden stream sonrası?** Stream sırasında render etsek, mesaj sırası bozulabilir.
Önce tüm stream'i işle (araç çağrıları, execute sonuçları, final yanıt), sonra
artifact'ları göster. Tutarlı sıralama.

#### Engellenen mesajları gizleme

🔗 [**src/ui/chat.py:476-481** — Block filtering](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L476-L481)

```python
                _blocked_markers = ("⛔", "BLOCKED", "already parsed", ...)
                if any(m in tool_content for m in _blocked_markers):
                    logger.debug("Interceptor block (hidden from UI): %s", ...)
                    continue    # ← Kullanıcıya GÖSTERME
```

**Neden gizliyoruz?** Kullanıcı "⛔ Shell command 'ls' BLOCKED" görmek istemez. Bu
internal mekanizma — ajan kuralları öğrenme sürecinde. Kullanıcı temiz bir arayüz
görüyor, ajan ise engelleme mesajını alıp davranışını düzeltiyor.

#### ExecuteStatusManager — Canlı Durum

🔗 [**src/ui/chat.py:97-240** — ExecuteStatusManager](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L97-L240)

```python
class ExecuteStatusManager:
    def __init__(self):
        self._placeholder = None          # st.empty() — canlı güncelleme
        self._step_count = 0
        self._steps_buffer = []           # Tüm adımları tut (yeniden render için)
        self._start_time = None
```

**Neden `st.empty()`?** Streamlit'te bir kez render ettiğin element değiştirilemez...
`st.empty()` hariç. `empty()` bir placeholder oluşturur — her `_render_current_state()`
çağrısında içeriğini tamamen değiştiriyoruz. Böylece "Step 1/3 çalışıyor..." →
"Step 2/3 çalışıyor..." → "✅ Complete (3 steps)" animasyonu sağlıyoruz.

**Neden `_steps_buffer`?** Her güncelleme tüm UI'ı yeniden çiziyor (Streamlit'in
modeli böyle). Buffer'da tüm adımları tutuyoruz ki her render'da geçmiş adımlar da
gösterilsin.

```python
    def add_execute_call(self, tool_call_id, code):
        step_name = _detect_step_name(code)       # ← Koddan adım ismi tahmin et
        self._current_step_name = step_name
        self._steps_buffer.append({
            'num': self._step_count,
            'code': code,
            'step_name': step_name,
            'start_time': time.time(),             # ← Süre ölçümü başlat
        })
        self._render_current_state("running")
```

#### Adım ismi tespiti — öncelik sistemi

🔗 [**src/ui/chat.py:23-94** — _detect_step_name](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L23-L94)

```python
    _DETECTORS = [
        (100, "📑 Generating PDF Report",    'weasyprint' in code_lower),
        (95,  "🎞️ Creating Presentation",   'pptx' in code_lower),
        (85,  "🦆 Running Database Query",   'duckdb' in code_lower),
        (70,  "📄 Loading & Cleaning Data",  'read_excel' in code and 'dropna' in code),
        (65,  "📄 Loading Data",             'read_excel' in code_lower),
        (60,  "📊 Analyzing Data",           'groupby' in code_lower),
        ...
    ]

    for priority, label, matched in _DETECTORS:
        if matched and priority > best_priority:
            best_priority = priority
            best_label = label
```

**Neden öncelik sistemi?** Aynı kod bloğunda `read_excel` + `weasyprint` olabilir
(veri oku + PDF üret). İkisi de eşleşir ama PDF üretimi daha "önemli" — kullanıcıya
"📑 Generating PDF Report" gösterilmeli. Öncelik sistemi en spesifik operasyonu seçiyor.

---

## Bölüm 11: Giriş Noktası

🔗 [**app.py** — Tam dosya (58 satır)](https://github.com/CYBki/code-execution-agent/blob/main/app.py)

```python
from src.utils.logging_config import setup_logging
setup_logging()                              # 1. İLK: Log sistemi
```

**Neden ilk?** Bundan sonraki her şey loglanabilir. Hata olursa yakalarız.

```python
from dotenv import load_dotenv
load_dotenv()                                # 2. .env dosyasını yükle
```

**Neden logging'den sonra?** `load_dotenv()` başarısız olursa log'a yazmak istiyoruz.

```python
st.set_page_config(page_title="Data Analysis Agent", layout="wide")
```

**Neden `layout="wide"`?** Dashboard'lar ve grafikler geniş alan istiyor. Dar layout'ta
kesilir.

```python
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
```

**Neden `unsafe_allow_html`?** Streamlit güvenlik nedeniyle HTML/CSS'i engelliyor.
Biz özel stiller (koyu kenar çubuğu, dönen spinner, renk kodlu durumlar) istiyoruz —
kendi CSS'imizi enjekte ediyoruz.

```python
try:
    get_secret("ANTHROPIC_API_KEY")
    get_secret("OPEN_SANDBOX_API_KEY")
except ValueError as e:
    st.error(str(e))
    st.stop()                                # ← Anahtar yoksa DURMA
```

**Neden `st.stop()`?** API anahtarı olmadan hiçbir şey çalışmaz. Ajanı oluşturamayız,
sandbox'a bağlanamayız. Kullanıcıya hata gösterip durmak en dürüst yaklaşım.

```python
init_db()                                    # 5. Tabloları oluştur
init_session()                               # 6. Oturum + sandbox ön-ısıtma
render_sidebar()                             # 7. Sol panel
render_chat()                                # 8. Sohbet alanı
```

**Sıralama neden önemli?** `init_db()` → `init_session()` çünkü session DB'ye
konuşma kaydediyor. `init_session()` → `render_chat()` çünkü chat sandbox'un
hazır olmasını bekliyor. `render_sidebar()` → `render_chat()` çünkü dosya yükleme
sidebar'da yapılıyor, chat dosyaları okuyor.

---

## Bölüm 12: Uçtan Uca Akış

Tüm bileşenleri birleştirip tek bir senaryoyu takip edelim:

**Senaryo:** Kullanıcı `sales.xlsx` yüklüyor, "Analiz et, PDF ver" diyor.

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. app.py çalışır                                                    │
│    setup_logging() → JSON log sistemi kuruldu                        │
│    load_dotenv() → .env'den ANTHROPIC_API_KEY okundu                 │
│    get_secret() → API anahtarları doğrulandı                         │
│    init_db() → SQLite tabloları oluşturuldu (yoksa)                  │
│    init_session() → session_id=uuid üretildi                         │
│      └─ daemon thread: SandboxManager._create_new_sandbox()          │
│           └─ SandboxSync.create("agentic-sandbox:v1") → ~5s          │
│           └─ CodeInterpreter + py_context oluşturuldu                │
│           └─ publish_html() kernel'a enjekte edildi                   │
│           └─ _packages_ready.set() → hazır sinyali                   │
│    render_sidebar() → dosya yükleme widget'ı gösterildi              │
│    render_chat() → boş sohbet ekranı                                 │
│                                                                      │
│ 2. Kullanıcı sales.xlsx yüklüyor                                     │
│    st.file_uploader → uploaded_files = [sales.xlsx]                   │
│    save_files() → BLOB olarak SQLite'a kaydedildi                    │
│                                                                      │
│ 3. Kullanıcı "Analiz et, PDF ver" yazıyor                           │
│    render_chat():                                                    │
│      a) save_message(session_id, "user", "Analiz et, PDF ver")       │
│      b) get_or_build_agent():                                        │
│         - detect_required_skills([sales.xlsx]) → ["xlsx"]            │
│         - load_skill("xlsx") → SKILL.md kuralları                    │
│         - compose_system_prompt(BASE + xlsx skill) → ~1000 satır     │
│         - make_parse_file_tool(files) → closure'da dosyalar          │
│         - make_execute_tool(backend) → closure'da backend            │
│         - ... 5 araç oluşturuldu                                     │
│         - smart_interceptor oluşturuldu (6 execute hakkı)            │
│         - create_agent(model, tools, prompt, middleware)              │
│      c) sandbox_manager.wait_until_ready() → ön-ısıtma bitmişti ✓   │
│      d) sandbox_manager.upload_files([sales.xlsx])                   │
│         → /home/sandbox/sales.xlsx (sandbox'ta)                      │
│      e) reset_fn() → interceptor sayaçları sıfırlandı               │
│                                                                      │
│ 4. Ajan çalışıyor (ReAct döngüsü)                                   │
│                                                                      │
│    Adım 1: parse_file("sales.xlsx")                                  │
│      → interceptor: _seen_parse_files.add("sales.xlsx")              │
│      → file_parser.py: pd.read_excel(BytesIO(file_bytes))           │
│        → Kolon tipleri, tarih formatları, satır sayısı çıkarıldı     │
│      → Çıktı: "4 kolon, 50000 satır, InvoiceDate: DD.MM.YYYY"       │
│      → Çıktı sonu: "✅ PARSE BAŞARILI. Sonraki: execute(read_excel)" │
│                                                                      │
│    Adım 2: execute("df = pd.read_excel(...); df.dropna(...)")        │
│      → interceptor:                                                  │
│        ✓ Circuit breaker: _consecutive_blocks=0 < 3                  │
│        ✓ Duplicate parse: "execute" değil                            │
│        ✓ Rate limit: _execute_count=1 ≤ 6                            │
│        ✓ Pip install: yok                                            │
│        ✓ Hardcoded data: pd.read_excel var → data_access_op          │
│        ✓ Network: yok                                                │
│        ✓ Shell cmd: "import" ile başlıyor → Python                   │
│        → GEÇIR                                                       │
│      → execute.py:                                                   │
│        1. _extract_python_code() → None (python3 -c yok)            │
│        2. "import" ile başlıyor → py_code = command                  │
│        3. base64 encode → printf/base64 -d kalıbı oluştur           │
│      → manager.py:                                                   │
│        1. _PYFILE_RE eşleşti → base64 decode                        │
│        2. codes.run(py_code, context=py_context)                     │
│        3. df bellekte, 48500 satır                                   │
│      → Çıktı: "✅ 48500 satır" + "[Execute 1/6, remaining: 5]"      │
│      → interceptor: _consecutive_blocks = 0 (başarılı)              │
│                                                                      │
│    Adım 3: execute("m = {'total': len(df), ...}")                    │
│      → interceptor: hardcoded check                                  │
│        "len(df)" var → data_access_op → GEÇIR                       │
│      → Kernel'da m dict hesaplandı                                   │
│      → Çıktı: "✅ m: 5 keys: ['total', 'avg', ...]"                 │
│      → "[Execute 2/6, remaining: 4]"                                 │
│                                                                      │
│    Adım 4: execute("html = f'...{m[\"total\"]:,}...'; weasyprint")   │
│      → interceptor: weasyprint var, sayılar f-string'de → GEÇIR     │
│      → PDF üretildi: /home/sandbox/rapor.pdf (148 KB)                │
│      → "[Execute 3/6, remaining: 3]"                                 │
│                                                                      │
│    Adım 5: download_file("/home/sandbox/rapor.pdf")                  │
│      → Path kontrolü: /home/sandbox/ ✓                               │
│      → backend.download_files() → PDF bytes                         │
│      → _clean_excel_dates: PDF, skip                                 │
│      → ArtifactStore.add_download(pdf_bytes, "rapor.pdf")            │
│      → "✅ rapor.pdf ready (148 KB)"                                 │
│                                                                      │
│    Final: Ajan yanıtı: "Analiz tamamlandı, PDF rapor hazır."        │
│                                                                      │
│ 5. UI sonuçları gösteriyor                                           │
│    exec_manager.finalize() → "✅ Complete (3 steps, 8.2s)"           │
│    store.pop_downloads() → [{rapor.pdf}]                             │
│    st.download_button("📥 rapor.pdf indir")                          │
│    save_message(session_id, "assistant", ..., steps=[...])           │
│    auto_learn() → daemon thread: kalite analizi                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Engelleme Senaryosu — Detaylı

Ya ajan `ls` çalıştırmaya çalışırsa?

```
Ajan: execute("ls /home/sandbox/")
  → interceptor:
    1. bare_cmd = "ls" (ilk kelime)
    2. "ls" in shell_cmds → EVET
    3. _execute_count -= 1 (hakkı geri ver — haksız ceza olmasın)
    4. _consecutive_blocks += 1 (şu an 1)
    5. ToolMessage döndür:
       "⛔ Shell command 'ls' BLOCKED
        Known files: /home/sandbox/sales.xlsx
        Use pd.read_excel() instead."
  → UI: Bu mesaj GÖSTERİLMEZ (_blocked_markers tespiti)
  → Ajan bu mesajı GÖRÜR ve davranışını düzeltir

Ajan (düzeltme): execute("df = pd.read_excel('/home/sandbox/sales.xlsx')")
  → interceptor: Python kodu, data_access_op var → GEÇIR
  → _consecutive_blocks = 0 (sıfırla — başarılı execute)
  → Kod çalışır, df bellekte
```

---

## Bölüm 13: Bellek Yönetimi — Projenin "Görünmez" Savunma Katmanı

Bu proje **üç farklı bellek alanı** yönetiyor ve her birinin taşma riski farklı:

```
┌─────────────────────────────────────────────────────────────┐
│  1. Streamlit Sunucu (Ana Süreç)                            │
│     └─ session_state, artifact_store, DB bağlantıları       │
│                                                             │
│  2. Sandbox Container (Docker, izole)                       │
│     └─ Python kernel, DataFrame'ler, matplotlib figürleri   │
│                                                             │
│  3. Disk (Log dosyaları, geçici dosyalar, DB)               │
│     └─ RotatingFileHandler, sandbox /home/sandbox/ dosyaları│
└─────────────────────────────────────────────────────────────┘
```

Her alan için ayrı ayrı bakalım hangi mekanizmalar var, neden o şekilde yapılmış ve alternatifleri neydi.

---

### 13.1 Sandbox Container Belleği — En Tehlikeli Alan

Sandbox, kullanıcının kodunun çalıştığı yer. Bellek taşması en çok burada olur çünkü
kullanıcının analiz ettiği dosya boyutunu kontrol edemiyoruz.

#### 13.1.1 pandas Bellek Çarpanı ve DuckDB Stratejisi

🔗 [file_parser.py:315-321](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/file_parser.py#L315-L321)

```python
output += (
    f"\n\n⚠️ BÜYÜK DOSYA ({size_mb:.1f} MB ≥ 40MB) — DUCKDB STRATEJİSİ ZORUNLU. "
    "pandas ile pd.read_excel() KULLANMA (çok yavaş/bellek sorunu). "
    "Doğru strateji: "
    "① df = pd.read_excel(path) ile CSV'ye çevir: df.to_csv('/home/sandbox/temp.csv', index=False); del df "  # ← del df KRİTİK!
    "② duckdb.sql(\"SELECT ... FROM read_csv_auto('/home/sandbox/temp.csv')\").df() "
    "Threshold: file_size_mb >= 40 → DuckDB, < 40 → pandas."
)
```

**Problem:** pandas bir Excel dosyasını okurken, dosya boyutunun **3-5 katı** RAM kullanır.

Neden 3-5x? Çünkü:
1. Dosya disk'ten okunur → RAM'e yüklenir (1x)
2. Her sütun Python nesnelerine dönüştürülür (her hücre ayrı Python object) (1.5-2x)
3. String sütunlar her hücre için ayrı str nesnesi oluşturur (1-2x ek)
4. Index oluşturulur (0.1-0.5x ek)

**Somut örnek:** 40MB Excel → pandas ~120-200MB RAM kullanır. Container limiti 2GB.
Aynı anda 2 dosya açılırsa → 400MB. Birkaç `groupby()` + `merge()` → kolayca 1GB aşılır.

**Neden DuckDB?** DuckDB "lazy evaluation" kullanır — tüm dosyayı RAM'e yüklemez, SQL sorgusuna
göre sadece gerekli sütunları ve satırları okur. 40MB dosya → ~5-10MB RAM.

**`del df` neden kritik?**
```python
# Yanlış (bellekte iki kopya):
df = pd.read_excel(path)           # ~120MB RAM
df.to_csv('/home/sandbox/temp.csv') # disk'e yaz
# df hâlâ bellekte! DuckDB sorguları ek 10MB daha kullanacak → toplam ~130MB

# Doğru:
df = pd.read_excel(path)           # ~120MB RAM
df.to_csv('/home/sandbox/temp.csv') # disk'e yaz
del df                              # ~120MB serbest bırakıldı ← KRİTİK!
# Artık DuckDB sadece ~10MB kullanır → toplam ~10MB
```

`del df` olmadan, Python garbage collector DataFrame'i **hemen** toplamaz çünkü referans
sayısı 0'a düşmemiş olabilir (eğer başka bir değişkende referans varsa). `del` ile açıkça
"artık bunu kullanmayacağım" diyorsun.

**💡 Neden 40MB eşiği?**
- 40MB × 3x = 120MB → container'ın 2GB limitinin %6'sı → güvenli
- 40MB × 5x = 200MB → hâlâ %10 → güvenli ama üstü riskli
- 80MB × 5x = 400MB → %20 → birkaç analiz adımıyla 1GB aşılabilir
- 40MB, "pandas güvenli" ile "pandas riskli" arasındaki sınır

**Alternatif neden elendi?**
- `chunksize` parametresi (pandas): Her chunk'ı işleyip atabilirsin ama kodun 3x daha karmaşık
- `modin` veya `vaex`: Ek bağımlılık, sandbox image'ına eklemek gerekir
- Sadece `gc.collect()`: `del` kadar etkili değil ve zamanlaması belirsiz

---

#### 13.1.2 `read_only=True` — openpyxl Bellek Tasarrufu

🔗 [file_parser.py:107](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/file_parser.py#L107)

```python
wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
#                                          ^^^^^^^^^^^^^^  ^^^^^^^^^^^^^
#                                          %60-70 az RAM   formül yerine sonuç
```

**Problem:** openpyxl varsayılanda tüm hücre nesnelerini (Cell objects) oluşturur —
her birinin style, font, border bilgisi var. 10.000 satır × 20 sütun = 200.000 Cell nesnesi.

**`read_only=True` ne yapar?**
- Cell nesnelerini "lazy" oluşturur — iterasyon sırasında, talep edildikçe
- Style bilgisini yüklemez (bize zaten sadece `number_format` lazım)
- Bellek kullanımını **%60-70** azaltır

**`data_only=True` ne yapar?**
- `=SUM(A1:A10)` gibi formülleri yüklemez, sadece hesaplanmış değerleri okur
- Formül ağacı belleğe yüklenmez → ek tasarruf

**Neden `read_only=True` her yerde kullanılmıyor?**
- `download_file.py`'de **kullanılamaz** çünkü orada hücre değerlerini **değiştiriyoruz**
  (datetime → date dönüşümü). `read_only=True` ile yazma işlemi yapılamaz.

---

#### 13.1.3 matplotlib Figür Birikimi — `plt.close('all')`

🔗 [visualization.py:34](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/visualization.py#L34)

```python
wrapped_code = code + "\nimport matplotlib; matplotlib.pyplot.close('all')"
```

**Problem:** matplotlib her `plt.figure()` veya `plt.subplots()` çağrısında bellekte bir Figure
nesnesi oluşturur ve **otomatik silmez**. Bir analiz oturumunda 10 grafik çizilirse:

```
Figür 1: ~5MB  → toplam: 5MB
Figür 2: ~5MB  → toplam: 10MB
Figür 3: ~5MB  → toplam: 15MB
...
Figür 10: ~5MB → toplam: 50MB  ← hepsi hâlâ bellekte!
```

Her figür, pixel buffer + axis nesneleri + text rendering cache tutar.
Yüksek DPI (150) ile bu değerler daha da artar.

**Neden kullanıcının kodu yerine biz ekliyoruz?**
Ajan her zaman `plt.close()` yazmayı hatırlamayabilir — LLM'ler bu tür "temizlik" kodunu
sıklıkla unutur. Biz kodu **sarmallayarak** (wrap) garanti altına alıyoruz.

**Neden `plt.close('all')` ve `plt.close()` değil?**
- `plt.close()` → sadece **aktif** figürü kapatır
- `plt.close('all')` → **tüm** figürleri kapatır
- Kullanıcı birden fazla figür açıp sadece birine `plt.savefig()` yapmış olabilir →
  diğerleri hâlâ açık → `'all'` ile hepsini temizle

**Neden `del fig` yeterli değil?**
matplotlib, figürleri kendi iç `Gcf` (global current figure) manager'ında da tutar.
`del fig` referansı kaldırır ama `Gcf`'teki referans kalır → garbage collector toplamaz.
`plt.close()` hem `Gcf`'ten çıkarır hem figürü destroy eder.

---

#### 13.1.4 Kernel Timeout ve Bellek Kurtarma — `_reset_context()`

🔗 [manager.py:75-94](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L75-L94)

```python
def _reset_context(self):
    try:
        old_id = getattr(self._py_context, "id", None)
        if old_id:
            try:
                self._interpreter.codes.delete_context(old_id)  # ← Eski context'in TÜM değişkenlerini sil
            except Exception:
                pass  # Takılı olabilir — sorun değil
        self._py_context = self._interpreter.codes.create_context(  # ← Temiz kernel
            SupportedLanguage.PYTHON
        )
    except Exception as e:
        logger.error("Failed to reset kernel context: %s", e)
```

**Bu neden bellek yönetimi?** Timeout olan bir kodun bellekte tuttuğu her şeyi temizler.

**Senaryo:** Kullanıcı 200MB'lık bir DataFrame üzerinde karmaşık bir `groupby().apply()`
çalıştırdı → 180 saniye timeout oldu → `_reset_context()` çağrıldı.

Eğer `_reset_context()` yapılmazsa:
- Eski context'teki 200MB DataFrame **hâlâ bellekte** (eski kernel reference tutuyor)
- Yeni context oluşturulsa bile eski Python nesneleri serbest kalmaz
- Sonraki execute'lar ek bellek kullanır → birikir → OOM (Out of Memory)

`delete_context()` eski kernel'ın **tüm Python namespace'ini** temizler — `df`, `m`, `results`
gibi tüm değişkenler garbage collector'a iade edilir.

---

#### 13.1.5 Yeni Konuşma = Temiz Bellek — `clean_workspace()`

🔗 [manager.py:296-324](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L296-L324)

```python
def clean_workspace(self):
    # 1. Dosya temizliği
    self._backend.execute(
        f"rm -rf {SANDBOX_HOME}/* 2>/dev/null; "      # ← Disk'teki dosyaları sil
        "rm -rf /tmp/_run_*.py 2>/dev/null; "           # ← Geçici Python dosyalarını sil
        "echo CLEAN_OK"
    )
    # 2. Kernel temizliği
    if self._interpreter is not None:
        self._interpreter.codes.delete_context(self._py_context.id)  # ← ESKİ kernel sil (TÜM değişkenler)
        self._py_context = self._interpreter.codes.create_context(    # ← YENİ kernel oluştur
            SupportedLanguage.PYTHON
        )
```

**İki aşamalı temizlik:**
1. **Disk:** `/home/sandbox/` altındaki tüm dosyalar (Excel, CSV, PDF, PNG) silinir
2. **Bellek:** Eski Python kernel context'i tamamen yok edilir → tüm DataFrame'ler, değişkenler serbest

**Neden container'ı yeniden oluşturmuyoruz?**
Container oluşturma ~5 saniye sürer. Kernel context reset ~100ms sürer.
Container'ı **yeniden kullanıp** sadece bellek ve dosyaları temizlemek 50x daha hızlı.

**💡 Neden bu tasarım önemli?**
Kullanıcı "Yeni Konuşma" butonuna basınca, önceki analizin 500MB'lık DataFrame'i
bellekten tamamen temizlenir. Yeni analiz **temiz** bir bellekle başlar.
Container restart gerekmeden aynı container'da sıfır bellek yüküyle devam edilir.

---

#### 13.1.6 Container Yaşam Sonu — `stop()` ve `__del__`

🔗 [manager.py:326-346](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L326-L346)

```python
def stop(self):
    if self._sandbox is not None:
        try:
            self._sandbox.kill()     # ← Container process'ini öldür
            self._sandbox.close()    # ← API bağlantısını kapat
        except Exception:
            pass
        finally:
            self._sandbox = None     # ← Referansları None yap
            self._backend = None     # ← Python GC bu nesneleri toplar
            self._interpreter = None
            self._py_context = None
            self._packages_ready = threading.Event()

def __del__(self):
    # Best-effort — Python GC garanti etmiyor
    try:
        self.stop()
    except Exception:
        pass
```

**4 katmanlı referans temizliği:**
1. `kill()` → Docker container'ın process'ini öldürür → container'ın RAM'i OS'a geri döner
2. `close()` → HTTP/WebSocket bağlantısını kapatır → socket belleği serbest
3. `= None` → Python referanslarını kaldırır → GC nesneleri toplar
4. `threading.Event()` → Eski Event nesnesini değiştirir → GC eski Event'i toplar

**Neden `__del__` güvenilir değil?**
Python `__del__`'i garbage collector çalıştığında çağırır — ama **ne zaman** çalışacağı
garanti değil. Döngüsel referanslar varsa hiç çağrılmayabilir. Bu yüzden `atexit` handler
(session.py'de) esas temizlik mekanizması — `__del__` sadece "ihtimale karşı" yedek.

---

### 13.2 Execute Çıktı Belleği — LLM Context Koruması

#### 13.2.1 `MAX_OUTPUT = 50_000` — Çıktı Kırpma

🔗 [execute.py:134-136](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/execute.py#L134-L136)

```python
MAX_OUTPUT = 50_000
if output and len(output) > MAX_OUTPUT:
    output = output[:MAX_OUTPUT] + f"\n... [truncated, {len(output)} total chars]"
```

**Problem:** `print(df)` yazıldığında 50.000 satırlık DataFrame tüm çıktıyı yazar.
Bu çıktı:
1. Sandbox → Streamlit sunucusuna aktarılır (ağ belleği)
2. LangChain ToolMessage'a yazılır (Python string belleği)
3. Claude API'ye gönderilir (API payload belleği)
4. Claude'un context window'unda yer kaplar (token belleği)

50.000 satır × ortalama 100 karakter = 5MB string. Bu:
- Claude'un context window'unu gereksiz doldurur → sonraki adımlarda "context too long" hatası
- API maliyetini artırır (token başına ücret)
- Streamlit'in belleğinde gereksiz büyük string tutar

**Neden 50.000 karakter?**
- 50K karakter ≈ 12-15K token → Claude'un 200K context window'unun ~%7'si
- Yeterince büyük: normal `print(df.describe())`, hata mesajları, birkaç sayfa çıktı rahatça sığar
- Yeterince küçük: tüm DataFrame dump'ı engellenir
- Kırpıldığında `[truncated, 847293 total chars]` bilgisi verir → ajan durumun farkında olur

**Alternatif neden elendi?**
- Kırpmama → context overflow, maliyet patlaması
- Daha küçük limit (10K) → meşru çıktıları da kırpar (uzun hata mesajları, `df.describe()` çıktıları)
- `print()` engellemek → kullanıcı kodunu kısıtlayamazsın, ajan print'e ihtiyaç duyuyor

---

#### 13.2.2 Log Çıktısı Kırpma — 300 Karakter Preview

🔗 [execute.py:126-128](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/execute.py#L126-L128)

```python
out_preview = (output or "")[:300].replace("\n", "\\n")
logger.info("execute output (exit=%s): %s", exit_code, out_preview)
```

**Log dosyasına** tüm çıktıyı yazmıyoruz — sadece ilk 300 karakter.

**Neden?** Log dosyası `RotatingFileHandler` ile 10MB limit var (aşağıda detay). Eğer
her execute çıktısını tam yazarsak, tek bir 5MB çıktı log dosyasının yarısını doldurur.
300 karakter, debug için yeterli — "ne çalıştı ve sonucu ne oldu" anlaşılır.

---

### 13.3 Dosya İndirme Belleği — `MAX_DOWNLOAD_MB = 50`

🔗 [download_file.py:89-91](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/download_file.py#L89-L91)

```python
MAX_DOWNLOAD_MB = 50
if len(resp.content) > MAX_DOWNLOAD_MB * 1024 * 1024:
    return f"❌ File too large ({len(resp.content) // 1024 // 1024}MB). Max {MAX_DOWNLOAD_MB}MB."
```

**Problem:** Sandbox'tan indirilen dosya Streamlit sunucusunun belleğine yüklenir
(`resp.content` → `artifact_store.add_download()` → `st.download_button()`).
50MB'lık bir dosya, sunucu tarafında 50MB RAM kullanır.

**Neden 50MB?**
- PDF rapor: genellikle 1-5MB → rahatça geçer
- Excel çıktısı: genellikle 5-20MB → rahatça geçer
- Dev CSV dump: 100MB+ olabilir → engellenmeli (kullanıcı DuckDB ile filtrelesin)

**💡 İlişkili bellek akışı:**
```
Sandbox RAM → download_files() → resp.content (sunucu RAM)
→ _clean_excel_dates() (eğer Excel ise, ek kopya)
→ artifact_store.add_download() (sunucu RAM'de tutuluyor)
→ st.download_button() (kullanıcı indirir)
→ pop_downloads() (artifact_store'dan temizlenir)
```

Her aşamada geçici bir kopya oluşabilir. 50MB dosya için en kötü durum:
~150MB sunucu RAM (resp.content + Excel cleaning buffer + artifact store).
Bu yüzden limit var.

---

#### 13.3.1 `wb.close()` — Workbook Bellek Temizliği

🔗 [download_file.py:55-58](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/download_file.py#L55-L58) | 
🔗 [file_parser.py:164](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/file_parser.py#L164)

```python
# download_file.py — her iki path'de de close
if modified:
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()        # ← Değişiklik yapıldıysa: kaydet, sonra kapat
    return buf.getvalue()

wb.close()            # ← Değişiklik yoksa: direkt kapat
return content

# file_parser.py
wb.close()            # ← Schema okuma bitti, workbook'u kapat
```

**Neden açıkça `close()` çağırıyoruz?**
openpyxl Workbook nesnesi, özellikle `read_only=False` modunda, dahili XML parser cache'leri
ve hücre nesneleri tutar. `close()` çağırmadan fonksiyondan çıkarsak, bu nesneler garbage
collector'ın insafına kalır — ve Python'da GC zamanlaması belirsizdir.

`close()` şunları yapar:
- XML parser'ları kapatır (libxml2 C belleği serbest)
- Worksheet cache'lerini temizler
- `read_only` modda lazy iterator'ları kapatır (dosya handle serbest)

---

### 13.4 Streamlit Sunucu Belleği

#### 13.4.1 ArtifactStore Pop Pattern — Tüket ve Temizle

🔗 [artifact_store.py:42-55](https://github.com/CYBki/code-execution-agent/blob/main/src/tools/artifact_store.py#L42-L55)

```python
def pop_html(self) -> Optional[str]:
    with self._lock:
        items = self._html_items[:]  # ← Kopyala
        self._html_items.clear()      # ← Orijinali temizle
    return items[-1] if items else None

def pop_downloads(self) -> List[dict]:
    with self._lock:
        items = self._downloads[:]   # ← Kopyala
        self._downloads.clear()       # ← Orijinali temizle
    return items
```

**Bu neden bellek yönetimi?**
Her `generate_html()` çağrısı HTML string'i artifact store'a ekler. Her `download_file()`
çağrısı dosya içeriğini (bytes) ekler.

Eğer `pop` yerine `get` kullansak (temizlemeden okusak):
- 5 dashboard HTML'i × 100KB = 500KB birikir
- 3 dosya indirme × 10MB = 30MB birikir
- Oturum boyunca hiç temizlenmez → bellek sürekli büyür

`pop` pattern'i **tüket ve temizle** prensibiyle çalışır:
1. UI thread artifact'ı alır (`pop`)
2. Artifact listesi temizlenir (`clear`)
3. UI thread artifact'ı render eder
4. Render bittikten sonra UI thread'in kendi referansı da scope dışına çıkar → GC toplar

**Neden `clear()` ve `del` değil?**
`clear()` listeyi boşaltır ama liste nesnesi aynı kalır — yeni öğeler eklenebilir.
`del self._html_items` → listeyi yok eder → sonraki `add_html()` çağrısı `AttributeError` verir.

---

#### 13.4.2 `lru_cache(maxsize=32)` — Skill Dosyası Cache Sınırı

🔗 [loader.py:14-15](https://github.com/CYBki/code-execution-agent/blob/main/src/skills/loader.py#L14-L15)

```python
@lru_cache(maxsize=32)
def load_skill(skill_path: str) -> Optional[str]:
```

**Neden `maxsize=32` ve sınırsız değil?**
- Projede ~10 skill/referans dosyası var → 32 fazlasıyla yeterli
- Her dosya ~5-30KB → 32 × 30KB = ~1MB maximum cache
- `maxsize=None` (sınırsız) kullansak ve bir bug yüzünden farklı path'ler üretilse
  (örneğin timestamp'li path) → cache sonsuz büyür → bellek sızıntısı
- `maxsize=32` bunu önler: 33. dosya eklenince en eski atılır (LRU eviction)

---

### 13.5 Disk Bellek Yönetimi — RotatingFileHandler

🔗 [logging_config.py:126-130](https://github.com/CYBki/code-execution-agent/blob/main/src/utils/logging_config.py#L126-L130)

```python
all_handler = RotatingFileHandler(
    os.path.join(_LOG_DIR, "app.log"),
    maxBytes=10 * 1024 * 1024,    # ← 10MB
    backupCount=5,                 # ← En fazla 5 yedek
    encoding="utf-8",
)
```

**Her üç log dosyası için aynı ayar:** `app.log`, `app_error.log`, `audit.log`

**Nasıl çalışır?**
```
app.log → 10MB dolduğunda:
  app.log → app.log.1 (yeniden adlandır)
  yeni boş app.log oluştur
  app.log.1 → app.log.2 ... app.log.5
  app.log.5 → silinir (6. yedek tutulmaz)
```

**Toplam disk kullanımı:** 3 dosya × (10MB aktif + 5 × 10MB yedek) = 3 × 60MB = **180MB maximum**

**Neden bu önemli?**
Production'da disk dolması sunucuyu çökertir. RotatingFileHandler olmadan:
- Yoğun kullanımda günde 50-100MB log üretilebilir
- 1 hafta → 700MB, 1 ay → 3GB
- Disk dolarsa: veritabanı yazamaz, sandbox dosya oluşturamaz, Streamlit çöker

---

### 13.6 ThreadPoolExecutor Bellek — `shutdown(wait=False)`

🔗 [manager.py:114-137](https://github.com/CYBki/code-execution-agent/blob/main/src/sandbox/manager.py#L114-L137)

```python
pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
future = pool.submit(self._interpreter.codes.run, py_code, context=self._py_context)
try:
    result = future.result(timeout=timeout)
except concurrent.futures.TimeoutError:
    future.cancel()
    pool.shutdown(wait=False)    # ← ZORUNLU: wait=True olursa sonsuza kadar bekler
    self._reset_context()
    return _ExecuteResult(output=f"Error: timed out...", exit_code=1)
else:
    pool.shutdown(wait=False)    # ← Başarılı durumda da pool'u temizle
```

**Bellek açısından:**
- `ThreadPoolExecutor` bir thread + iş kuyruğu tutar → ~1MB overhead
- Her `execute()` çağrısında yeni pool oluşturulur → eski pool temizlenmeli
- `shutdown(wait=False)` → pool kaynakları serbest bırakılır, beklemeden
- `shutdown(wait=True)` → takılmış thread bitene kadar bekle → **sonsuz bekleme!**
- `with` bloğu kullanılmaz çünkü `__exit__` → `shutdown(wait=True)` çağırır → aynı sorun

**Neden her çağrıda yeni pool?**
Aynı pool'u yeniden kullanmak mantıklı görünür ama:
- Timeout olan bir thread pool'da takılı kalır (`max_workers=1`)
- Sonraki submit, takılı thread bitmeden çalışamaz
- Yeni pool → her zaman temiz thread → garanti çalışma

---

### 13.7 Sandbox TTL — Uzun Vadeli Bellek Kontrolü

Sandbox container'ları varsayılan **2 saat TTL** ile oluşturulur. 2 saat boyunca hiç
kullanılmazsa OpenSandbox API otomatik olarak container'ı siler.

**Neden önemli?**
- Kullanıcı tarayıcı sekmesini kapatırsa, Streamlit `on_session_end` her zaman çalışmaz
- Orphan container → Docker'da 2GB RAM ayırılmış durur → sunucu belleği boşa harcanır
- TTL sayesinde en kötü 2 saat sonra otomatik temizlik → bellek geri kazanılır

**Tüm bellek koruma katmanları özet:**

```
┌────────────────────────────────────────────────────────────────────────┐
│  KATMAN                     │ MEKANİZMA            │ NE KORUYOR?      │
├────────────────────────────────────────────────────────────────────────┤
│  1. Dosya boyutu tespiti    │ ≥40MB → DuckDB       │ pandas OOM       │
│  2. del df                  │ CSV sonrası serbest   │ Çift kopya       │
│  3. read_only=True          │ openpyxl lazy load    │ Schema belleği   │
│  4. plt.close('all')        │ Figür temizliği       │ matplotlib leak  │
│  5. _reset_context()        │ Timeout sonrası reset │ Takılı kernel    │
│  6. clean_workspace()       │ Yeni konuşma temizliği│ Eski veri        │
│  7. stop() + __del__        │ Container sonlandırma │ Orphan container │
│  8. MAX_OUTPUT=50K          │ Çıktı kırpma          │ LLM context      │
│  9. MAX_DOWNLOAD_MB=50      │ İndirme limiti        │ Sunucu RAM       │
│ 10. wb.close()              │ Workbook temizliği    │ XML parser cache │
│ 11. pop pattern             │ Tüket ve temizle      │ Artifact birikimi│
│ 12. lru_cache(32)           │ Sınırlı cache         │ Skill cache leak │
│ 13. RotatingFileHandler     │ 10MB × 5 yedek        │ Disk dolması     │
│ 14. shutdown(wait=False)    │ Pool temizliği         │ Thread belleği   │
│ 15. Sandbox TTL             │ 2 saat otomatik silme │ Zombie container │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Bölüm 14: Sohbet Hafızası (Conversation Memory) — Agent Nasıl Hatırlıyor?

Bu bölüm projenin en çok merak edilen ama en az görünen katmanı: **Agent önceki soruları
nasıl hatırlıyor? Yeni dosya ekleyince ne oluyor? Eski konuşmaya dönünce ne değişiyor?**

Sistem **üç bağımsız hafıza katmanı** kullanıyor ve her birinin kapsamı, ömrü ve sınırları farklı:

```
┌────────────────────────────────────────────────────────────────────────────┐
│  HAFIZA KATMANI        │ NE HATIRLAR?           │ NE ZAMAN SİLİNİR?       │
├────────────────────────────────────────────────────────────────────────────┤
│  1. LangGraph           │ Tüm mesaj geçmişi      │ "Yeni Konuşma" →        │
│     Checkpointer        │ (user + AI + tool       │  yeni thread_id →       │
│                         │  mesajları)              │  eski geçmiş erişilmez  │
│                         │                         │                         │
│  2. Sandbox Kernel      │ Python değişkenleri     │ "Yeni Konuşma" →        │
│     (Kalıcı Kernel)     │ (df, m, imports)        │  clean_workspace()      │
│                         │                         │                         │
│  3. Veritabanı          │ Mesajlar + dosyalar     │ Kullanıcı silene kadar  │
│     (SQLite/PostgreSQL) │ (kalıcı depolama)       │  SONSUZA KADAR kalır    │
└────────────────────────────────────────────────────────────────────────────┘
```

---

### 14.1 Katman 1: LangGraph Checkpointer — Ajanın "Kısa Süreli Hafızası"

🔗 [graph.py:44-73](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L44-L73)

```python
_checkpointer = None

def _get_checkpointer():
    global _checkpointer
    if _checkpointer is None:
        database_url = os.environ.get("DATABASE_URL", "")
        if database_url.startswith("postgresql"):
            _checkpointer = PostgresSaver.from_conn_string(database_url)
        else:
            db_path = os.path.join(_data_dir, "checkpoints.db")
            _checkpointer_conn = sqlite3.connect(db_path, check_same_thread=False)
            _checkpointer = SqliteSaver(_checkpointer_conn)
        _checkpointer.setup()
    return _checkpointer
```

**Bu ne yapar?** LangGraph'ın `checkpointer`'ı, bir konuşma thread'indeki **tüm mesajları**
(HumanMessage, AIMessage, ToolMessage) kalıcı bir depoda saklar.

**Nasıl çalışır — adım adım:**

```
Kullanıcı: "Bu veriyi analiz et"
  ↓
agent.stream(
    {"messages": [{"role": "user", "content": "Bu veriyi analiz et"}]},
    config={"configurable": {"thread_id": session_id}},  ← BU KRİTİK!
)
  ↓
1. Checkpointer, bu thread_id için DAHA ÖNCE kaydedilmiş tüm mesajları yükler
2. Claude şunları görür:
   [system_prompt] + [önceki tüm mesajlar] + [yeni kullanıcı mesajı]
3. Claude yanıt verir
4. Yanıt (AIMessage + ToolMessage'lar) checkpointer'a kaydedilir
```

🔗 [chat.py:624-627](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L624-L627)

```python
for chunk in agent.stream(
    {"messages": [{"role": "user", "content": user_query}]},
    config={"configurable": {"thread_id": session_id}},  # ← thread_id = session_id
    stream_mode="updates",
):
```

**💡 Neden `thread_id` bu kadar önemli?**

`thread_id` = konuşmanın kimlik numarası. Aynı `thread_id` ile yapılan her `agent.stream()`
çağrısı, o konuşmanın **tüm geçmişini** Claude'a gösterir.

```
thread_id = "abc-123"

Turn 1: User: "Veriyi yükle"        → Checkpointer'a kaydedildi
        AI: parse_file → execute    → Checkpointer'a kaydedildi
        
Turn 2: User: "Müşteri analizi yap" → Checkpointer "abc-123" için TÜM Turn 1'i yükler
        Claude GÖRÜR: [Turn 1 user + AI + tool mesajları] + [Turn 2 user mesajı]
        Claude HATIRLAR: "Önceki turda df yükledim, hâlâ bellekte"
```

**Checkpointer olmasaydı ne olurdu?**
Claude her turda sadece yeni mesajı görürdü — önceki analizi, hangi dosyayı yüklediğini,
hangi değişkenleri tanımladığını hatırlamazdı. Her seferinde "parse_file → read_excel"
döngüsüne girerdi.

---

#### 14.1.1 Summarization Middleware — Uzun Konuşmaları Kırpmak

🔗 [graph.py:578](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L578)

```python
middleware = [
    create_summarization_middleware(model, backend),  # ← İLK middleware
    AnthropicPromptCachingMiddleware(...),
    PatchToolCallsMiddleware(),
    smart_interceptor,
]
```

**Problem:** 10 turlu bir konuşmada, her turda ~5 tool mesajı varsa = 50+ mesaj.
Her mesajın içinde kod çıktısı var (bazen 50K karakter). Toplamda yüz binlerce token olabilir
— Claude'un 200K context window'unu aşar.

**Çözüm:** `create_summarization_middleware` eski mesajları **özetler**:
- Konuşma uzadıkça, eski turların detaylı tool çıktıları kaldırılır
- Yerine kısa bir özet konur: "Turn 1'de df yüklendi, 48500 satır, 8 sütun"
- Claude hâlâ "ne olduğunu" bilir ama detaylı çıktıları görmez

**Bu neden ilk middleware?**
Summarization, Claude'a gönderilecek mesaj listesini **daraltır**. Diğer middleware'ler
(prompt caching, smart interceptor) daraltılmış listeyle çalışır → daha az token → daha
az maliyet.

**💡 Neden sadece eski mesajları özetliyoruz?**
Son 2-3 turundaki mesajlar tam bırakılır — çünkü Claude'un en son ne yaptığını detaylı
bilmesi gerekir (hata düzeltme, devam etme). Eski turlar özetlenir — "ne olduğunu bilmesi
yeter, detaylı kodu görmesine gerek yok."

---

### 14.2 Katman 2: Sandbox Kernel — Ajanın "Veri Hafızası"

Bu katman önceki bölümlerde detaylı anlatıldı (Bölüm 4), ama sohbet hafızası bağlamında
tekrar bakalım:

```python
# Turn 1 — execute #1:
df = pd.read_excel('/home/sandbox/sales.xlsx')
m = {'total': df['Revenue'].sum()}

# Turn 2 — kullanıcı yeni soru soruyor:
# df VE m HÂLÂ kernel'da! Tekrar yüklemeye gerek yok.
monthly = df.groupby(df['Date'].dt.month)['Revenue'].sum()
```

**Kernel hafızası vs Checkpointer hafızası:**

| Özellik | Checkpointer | Kernel |
|---------|-------------|--------|
| Ne saklar? | Mesaj metinleri (user/AI/tool) | Python değişkenleri (df, m, imports) |
| Nerede? | SQLite/PostgreSQL dosyası | Sandbox container RAM |
| Claude görür mü? | EVET — tüm mesaj geçmişi | HAYIR — sadece çalıştırdığı koddan bilir |
| Sayfa yenilenince? | ✅ Kalır (disk'te) | ✅ Kalır (container hâlâ çalışıyor) |
| "Yeni Konuşma"da? | ❌ Yeni thread_id → eski geçmiş erişilmez | ❌ clean_workspace() → kernel sıfırlanır |
| Eski konuşma yüklenince? | ✅ Eski thread_id → geçmiş geri gelir | ❌ Kernel sıfırlanmış — df yok |

**Kritik senaryo — eski konuşma yükleme:**

```
1. Kullanıcı konuşma A'da analiz yaptı (df bellekte, checkpointer'da 5 mesaj)
2. "Yeni Konuşma" → konuşma B başladı (kernel temizlendi, yeni thread_id)
3. Kullanıcı kenar çubuğundan konuşma A'yı tekrar yükledi:
   - session_id → konuşma A'nın ID'si (checkpointer eski mesajları gösterir ✅)
   - AMA kernel sıfırlanmış → df YOK! ❌
   - Claude eski mesajlardan "df yükledim" diyor → "df hâlâ bellekte" sanıyor
   - İlk execute'da "NameError: df is not defined" alır
   - Claude hatayı görür → "Ah, df yok, tekrar yüklemem lazım" → re-read
```

**💡 Bu neden önemli?** Kernel hafızası **geçici** (session-scoped), checkpointer hafızası
**kalıcı** (disk'te). İkisi arasındaki bu asimetri, eski konuşma yüklemelerinde bazen
ilk execute'un başarısız olmasına neden olur — ama ajanın hata düzeltme mekanizması
(correction loop, max 3 deneme) bunu otomatik halleder.

---

### 14.3 Katman 3: Veritabanı — Kalıcı Sohbet Arşivi

🔗 [db.py:199-222](https://github.com/CYBki/code-execution-agent/blob/main/src/storage/db.py#L199-L222)

```python
def save_message(session_id, role, content, steps=None):
    steps_json = json.dumps(steps, default=str, ensure_ascii=False) if steps else None
    cur.execute(
        "INSERT INTO messages (session_id, role, content, steps) VALUES (?, ?, ?, ?)",
        (session_id, role, content or "", steps_json),
    )
    # updated_at da güncellenir → kenar çubuğunda sıralama
```

**Her mesaj iki yere kaydedilir:**

```
Kullanıcı mesajı:
  1. st.session_state["messages"].append({...})     ← UI render için (RAM)
  2. save_message(session_id, "user", query)         ← DB'ye kalıcı kayıt (disk)

Ajan yanıtı:
  1. st.session_state["messages"].append({           ← UI render için (RAM)
       "role": "assistant",
       "content": full_response,
       "steps": collected_steps,          ← tool çağrıları + çıktıları
       "artifacts": {html, charts, downloads},  ← binary veriler (sadece RAM'de)
   })
  2. save_message(session_id, "assistant",           ← DB'ye kalıcı kayıt (disk)
       full_response, steps=collected_steps)
     # NOT: artifacts DB'ye KAYDEDILMEZ (binary, çok büyük)
```

🔗 [chat.py:549-558](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L549-L558)

```python
# Kullanıcı mesajı kaydı
st.session_state["messages"].append({"role": "user", "content": user_query})
save_message(_sid, "user", user_query)
if len(st.session_state["messages"]) == 1:
    update_conversation_title(_sid, user_query[:80])  # ← İlk mesaj = konuşma başlığı
```

**💡 Neden başlık ilk mesajdan alınıyor?**
Kenar çubuğundaki "Geçmiş Konuşmalar" listesinde kullanıcı konuşmaları ayırt edebilsin diye.
İlk mesaj genellikle niyeti en iyi özetler: "Bu veriyi analiz et" veya "Müşteri segmentasyonu yap".

---

### 14.4 Kullanıcı Yeni Dosya Eklediğinde Ne Olur?

Bu en karmaşık senaryo. Adım adım:

🔗 [chat.py:593-606](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L593-L606)

```python
# 1. Dosya parmak izi kontrolü
uploaded_fingerprint = tuple(f.name for f in uploaded_files) if uploaded_files else ()
if uploaded_files and uploaded_fingerprint != st.session_state.get("_files_uploaded"):
    # Parmak izi değişti → yeni dosya var!
    sandbox_manager.upload_files(uploaded_files)              # 2. Sandbox'a yükle
    st.session_state["_files_uploaded"] = uploaded_fingerprint # 3. Parmak izini güncelle
    save_files(_sid, uploaded_files)                          # 4. DB'ye kaydet
```

🔗 [graph.py:600-629](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L600-L629)

```python
def get_or_build_agent(sandbox_manager, thread_id, uploaded_files, user_query=""):
    file_fingerprint = tuple(
        (f.name, len(f.getvalue())) for f in (uploaded_files or [])
    )
    cached = st.session_state.get("_agent_cache")
    if cached and cached["fingerprint"] == file_fingerprint:
        return cached["agent"], cached["checkpointer"], cached["reset_fn"]
    
    # Parmak izi farklı → ajan YENİDEN oluşturulur
    agent, checkpointer, reset_fn = build_agent(...)
    st.session_state["_agent_cache"] = {
        "fingerprint": file_fingerprint,
        "agent": agent, ...
    }
```

**Tam akış:**

```
Kullanıcı sales.xlsx ile konuşma yapıyor (Turn 1-3 tamamlandı, df bellekte)
  ↓
Kullanıcı kenar çubuğundan customers.csv ekliyor
  ↓
Sonraki soru sorulduğunda:

1. uploaded_fingerprint değişti:
   ("sales.xlsx",) → ("sales.xlsx", "customers.csv")

2. İKİ dosya birden sandbox'a yüklenir (upload_files)
   (sales.xlsx zaten var ama üzerine yazılır — idempotent)

3. file_fingerprint değişti → ajan cache'i geçersiz
   → build_agent() tekrar çağrılır

4. Yeni ajan oluşturulurken:
   a. System prompt YENİDEN oluşturulur:
      "Uploaded Files:
       - /home/sandbox/sales.xlsx (2,400,000 bytes)
       - /home/sandbox/customers.csv (150,000 bytes)"    ← YENİ dosya da var!
   
   b. Skill tespiti YENİDEN çalışır:
      - sales.xlsx → xlsx skill
      - customers.csv → csv skill
      - 2 dosya → multi_file_joins.md referansı da yüklenir!   ← OTOMATİK!
   
   c. Yeni araçlar oluşturulur (parse_file artık 2 dosya biliyor)

5. AMA: thread_id AYNI → checkpointer eski mesajları yükler
   → Claude önceki 3 turn'ü hatırlıyor
   → Claude "sales.xlsx'i zaten analiz ettim, şimdi customers.csv de var" diyor

6. AMA: Kernel de AYNI → df hâlâ bellekte!
   → Claude "df varsa yeniden yükleme" kuralına uyar
   → Sadece yeni dosya için parse_file + execute yapar
```

**💡 Neden ajan yeniden oluşturuluyor ama konuşma sıfırlanmıyor?**

Ajan yeniden oluşturma = yeni system prompt + yeni araçlar + yeni skill'ler.
Bu ZORUNLU çünkü yeni dosyanın tipi farklı skill'ler gerektirebilir.

Ama checkpointer thread_id aynı kaldığı için konuşma geçmişi **korunur**.
Kernel de aynı container'da çalışmaya devam ettiği için değişkenler de **korunur**.

**Sonuç:** Kullanıcı açısından sorunsuz bir deneyim — yeni dosya ekledi, ajan hem eski
analizi hatırlıyor hem yeni dosyayı tanıyor.

---

### 14.5 Interceptor State Reset — Turn Bazlı Hafıza

🔗 [graph.py:152-166](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L152-L166)

```python
def reset_interceptor_state():
    nonlocal _execute_count, _total_blocked
    nonlocal _last_execute_failed, _correction_count, _consecutive_blocks
    _execute_count = 0           # ← Execute sayacı sıfırla
    _total_blocked = 0           # ← Engellenen çağrı sayacı sıfırla
    _last_execute_failed = False # ← Hata durumu sıfırla
    _correction_count = 0        # ← Düzeltme döngüsü sıfırla
    _consecutive_blocks = 0      # ← Ardışık engel sayacı sıfırla
    _seen_parse_files.clear()    # ← Görülen parse_file dosyaları sıfırla
```

🔗 [chat.py:608-610](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L608-L610)

```python
# Her yeni kullanıcı mesajından ÖNCE çağrılır
reset_fn()  # ← interceptor state sıfırla
```

**Bu neden gerekli?** Interceptor'ın sayaçları closure'da tutuluyor ve ajan cache'lendiğinden
aynı closure yeni turda da kullanılır. Sıfırlamazsak:

```
Turn 1: 6 execute kullandı → _execute_count = 6
Turn 2: reset_fn() çağrılmazsa → _execute_count hâlâ 6!
  → İlk execute'da "Execute limit reached" hatası → ajan hiç kod çalıştıramaz!
```

**Ama `_seen_parse_files` neden temizleniyor?**
Aynı dosyayı farklı turda tekrar parse etmek gerekebilir — kullanıcı "dosyanın şemasını
tekrar göster" diyebilir. Turn bazlı sıfırlama buna izin verir.

**💡 Neyi sıfırlıyoruz, neyi koruyoruz?**
- ✅ Sıfırlanan (turn-scoped): execute sayacı, blok sayacı, hata durumu
- ❌ Sıfırlanmayan (session-scoped): kernel değişkenleri, checkpointer mesajları, dosyalar

---

### 14.6 Geçmiş Konuşma Yükleme — Tam Akış

🔗 [components.py:113-132](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/components.py#L113-L132)

```python
if st.button(label, key=f"load_{conv['session_id']}"):
    # 1. DB'den mesajları yükle
    msgs = load_messages(conv["session_id"])
    st.session_state["messages"] = msgs            # ← UI geçmişi geri geldi

    # 2. session_id'yi eski konuşmanınki yap
    st.session_state["session_id"] = conv["session_id"]  # ← Checkpointer thread_id

    # 3. Ajan cache'ini temizle (yeni dosyalarla yeniden oluşturulacak)
    st.session_state.pop("_agent_cache", None)
    st.session_state.pop("_rendered_ids", None)
    st.session_state.pop("_files_uploaded", None)

    # 4. Dosyaları DB'den geri yükle
    saved_files = load_files(conv["session_id"])
    if saved_files:
        st.session_state["uploaded_files"] = [
            MockUploadedFile(f["name"], f["size"], f["data"]) for f in saved_files
        ]
```

**Yüklenen ve yüklenmeyen:**

```
✅ Geri gelen:
  - Mesaj geçmişi (UI + checkpointer)    → Kullanıcı eski konuşmayı görür
  - Dosyalar (DB'den)                     → Sidebar'da dosyalar gözükür
  - Checkpointer thread_id               → Claude eski mesajları hatırlar

❌ Geri gelmeyen:
  - Kernel değişkenleri (df, m, imports)  → Container sıfırlanmış veya farklı oturum
  - Artifact'lar (HTML, chart, download)  → DB'ye kaydedilmiyor (binary, çok büyük)
  - Interceptor state                     → Zaten her turn'de sıfırlanıyor
```

**Sonuç:** Eski konuşmaya dönüp yeni soru sorduğunda, Claude mesaj geçmişinden "df yüklemiştim"
bilir ama kernel'da df yoktur. İlk execute'da hata alır, düzeltme döngüsüyle veriyi tekrar
yükler. Kullanıcı açısından 1 execute "kaybedilir" ama akış devam eder.

---

### 14.7 "Yeni Konuşma" — Tam Sıfırlama

🔗 [session.py:116-154](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/session.py#L116-L154)

```python
def reset_session():
    # 1. Artifact store temizliği
    release_store(old_session_id)
    
    # 2. UI state sıfırlama
    st.session_state["messages"] = []            # ← Mesaj geçmişi silindi
    st.session_state["uploaded_files"] = []       # ← Dosyalar silindi
    
    # 3. YENİ session_id → YENİ checkpointer thread
    new_session_id = str(uuid.uuid4())
    st.session_state["session_id"] = new_session_id
    
    # 4. DB'de yeni konuşma oluştur
    create_conversation(session_id=new_session_id, user_id=user_id)
    
    # 5. Ajan cache'ini temizle → yeni dosyalarla yeniden oluşturulacak
    st.session_state.pop("_agent_cache", None)
    
    # 6. Sandbox: dosyaları sil + kernel sıfırla (container KALIR)
    mgr.clean_workspace()
```

**Sıfırlanan her şey:**

| Bileşen | Sıfırlama Yöntemi | Sonuç |
|---------|-------------------|-------|
| Mesaj geçmişi (UI) | `messages = []` | Ekran temiz |
| Checkpointer geçmişi | Yeni `session_id` | Claude sıfırdan başlar |
| Kernel değişkenleri | `clean_workspace()` | df, m, imports yok |
| Sandbox dosyaları | `rm -rf /home/sandbox/*` | Disk temiz |
| Ajan cache | `pop("_agent_cache")` | Yeni skill'lerle oluşturulacak |
| Artifact store | `release_store()` | HTML/chart/download temiz |

**Sıfırlanmayan:**
- Docker container (hâlâ çalışıyor — 5 saniye tasarruf)
- Pre-installed paketler (pandas, duckdb, weasyprint — hâlâ kurulu)
- DB'deki eski konuşmalar (kenar çubuğunda hâlâ görünür)

---

### 14.8 Prompt Caching — Maliyet Hafızası

🔗 [graph.py:579](https://github.com/CYBki/code-execution-agent/blob/main/src/agent/graph.py#L579)

```python
AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
```

**Bu conversation memory değil ama ilişkili:** Anthropic'in prompt caching özelliği,
aynı system prompt'u tekrar gönderdiğinde token'ları cache'den okur → **%90 daha ucuz**.

```
Turn 1: system_prompt (696 satır) → Claude'a gönderilir → Anthropic cache'e alır
Turn 2: Aynı system_prompt → cache'den okunur → %90 indirim
Turn 3: Aynı → cache → %90 indirim
...
```

**Neden `unsupported_model_behavior="ignore"`?**
Bazı modeller prompt caching desteklemez. `"ignore"` → hata fırlatmadan devam et.
`"error"` → model cache desteklemezse uygulamayı çökertir.

---

### 14.9 Hafıza Akış Diyagramı — Her Senaryo

```
┌──────────────────────────────────────────────────────────────────────┐
│ SENARYO 1: Aynı konuşmada ardışık sorular                          │
│                                                                     │
│ Turn 1: "Veriyi yükle"                                              │
│   Checkpointer: [user1, ai1, tool1]     ← kaydedildi               │
│   Kernel: df = 48500 satır              ← bellekte                  │
│   DB: user1 + assistant1 mesajları      ← kaydedildi                │
│                                                                     │
│ Turn 2: "Müşteri analizi yap"                                      │
│   Claude görür: [Turn1 mesajları] + [Turn2 user mesajı]             │
│   Claude bilir: "df zaten bellekte, tekrar yükleme"                 │
│   Kernel: df hâlâ var → direkt groupby yapabilir                    │
│   reset_fn(): execute_count=0 (yeni kota)                           │
│                                                                     │
│ Turn 3: "PDF rapor üret"                                            │
│   Claude görür: [Turn1 + Turn2 mesajları] + [Turn3 user]            │
│   Claude bilir: "df ve m hâlâ bellekte"                             │
│   Kernel: df + m var → direkt weasyprint ile PDF                    │
├──────────────────────────────────────────────────────────────────────┤
│ SENARYO 2: Yeni dosya eklendi (aynı konuşma)                       │
│                                                                     │
│ Turn 1-3: sales.xlsx ile analiz (yukarıdaki gibi)                   │
│                                                                     │
│ Kullanıcı: customers.csv ekliyor (sidebar'dan)                      │
│   → file_fingerprint değişti → ajan YENİDEN oluşturulur             │
│   → Yeni system prompt: 2 dosya + multi_file_joins skill'i          │
│   → Checkpointer thread_id AYNI → eski mesajlar korunur             │
│   → Kernel AYNI → df hâlâ bellekte                                  │
│                                                                     │
│ Turn 4: "İki dosyayı birleştir"                                     │
│   Claude: Turn 1-3 geçmişini görür + yeni dosya bilgisini           │
│   Kernel: df (sales) var + customers.csv sandbox'ta                  │
│   → parse_file(customers.csv) + df2 = read_csv() + merge            │
├──────────────────────────────────────────────────────────────────────┤
│ SENARYO 3: "Yeni Konuşma" butonuna basıldı                         │
│                                                                     │
│ reset_session() →                                                    │
│   Checkpointer: yeni thread_id → eski mesajlar ERİŞİLEMEZ          │
│   Kernel: clean_workspace() → df, m, imports YOK                    │
│   UI: messages = [] → ekran temiz                                   │
│   Container: AYNI → paketler hâlâ kurulu (hızlı başlangıç)         │
│   DB: eski konuşma DURUYOR → kenar çubuğundan geri yüklenebilir    │
├──────────────────────────────────────────────────────────────────────┤
│ SENARYO 4: Eski konuşma kenar çubuğundan yüklendi                  │
│                                                                     │
│ load_messages(old_session_id) →                                      │
│   UI: eski mesajlar gösterilir ✅                                    │
│   Checkpointer: old_session_id → eski thread geçmişi yüklenir ✅    │
│   Dosyalar: DB'den MockUploadedFile olarak geri yüklenir ✅          │
│   Kernel: SIFIRLANMIŞ → df YOK ❌                                   │
│   Artifacts: DB'ye kaydedilmemiş → HTML/chart/download YOK ❌        │
│                                                                     │
│ İlk soru sorulduğunda:                                              │
│   Claude: "df var sanıyorum" → execute → NameError!                 │
│   Claude: "Ah, kernel sıfırlanmış" → re-read → devam eder           │
│   1 execute "kaybedilir" ama akış otomatik düzelir                  │
└──────────────────────────────────────────────────────────────────────┘
```

---

### 14.10 Rendered IDs — Mesaj Tekrarı Önleme

🔗 [chat.py:619-621](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L619-L621)

```python
if "_rendered_ids" not in st.session_state:
    st.session_state["_rendered_ids"] = set()
rendered_ids = st.session_state["_rendered_ids"]
```

🔗 [chat.py:427-431](https://github.com/CYBki/code-execution-agent/blob/main/src/ui/chat.py#L427-L431)

```python
msg_id = getattr(msg, "id", None)
if msg_id and msg_id in rendered_ids:
    continue  # ← Bu mesaj zaten render edildi, ATLA
if msg_id:
    rendered_ids.add(msg_id)
```

**Problem:** LangGraph stream'i, checkpointer'dan önceki mesajları da döndürebilir.
Turn 2'de stream başlayınca, Turn 1'in mesajları da "updates" olarak gelebilir.

**Çözüm:** Her render edilen mesajın `id`'si `_rendered_ids` set'ine eklenir.
Aynı `id` tekrar geldiğinde atlanır → kullanıcı aynı mesajı iki kez görmez.

**Neden `set` ve `list` değil?**
`set`'te arama O(1), `list`'te O(n). 50 mesajlık bir konuşmada her chunk için
50 kez kontrol gerekir → `set` çok daha hızlı.

---

## Son Söz

Bu dokümanı okuduysan artık her satırın ne yaptığını VE neden o şekilde yazıldığını
biliyorsun. Önemli tasarım kararları:

1. **Kalıcı kernel** — pickle yerine CodeInterpreter bağlamı → basitlik + performans
2. **Factory + closure** — LangChain araç arayüzüyle backend referansı birleştirme
3. **Artifact store** — thread güvenli köprü: Lock + pop/push pattern
4. **Progressive disclosure** — ihtiyaca göre prompt derleme → token tasarrufu
5. **Smart interceptor** — 12 kural, 3 katmanlı hardcoded veri savunması
6. **Base64 kodlama** — shell escaping sorunlarını ortadan kaldırma
7. **Ön-ısıtma** — kullanıcı beklemeden sandbox hazırlığı
8. **Çift backend** — SQLite (dev) + PostgreSQL (prod) aynı kodla
9. **publish_html marker** — kernel → dosya → marker → artifact store → iframe
10. **Circuit breaker** — sonsuz döngü tespiti ve durdurma
11. **15 katmanlı bellek yönetimi** — sandbox, sunucu, disk, thread belleği koruması
12. **3 katmanlı sohbet hafızası** — checkpointer + kernel + DB, her biri farklı ömür ve kapsam

Her karar bir problemi çözüyor. Alternatifler denenip elenmiş. Bu doküman o sürecin
kaydı.

İyi kodlamalar! 🚀
