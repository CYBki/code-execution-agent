# Agentic Analyze

Excel, CSV ve PDF dosyalarını analiz eden, otomatik PDF rapor üreten AI agent.

**Stack:** LangChain `create_agent` + Anthropic Claude + OpenSandbox + Streamlit

---

## Ön Koşullar

- Python 3.12+
- [Anthropic API Key](https://console.anthropic.com/)
- OpenSandbox — kod çalıştırma sandbox ortamı

---

## Kurulum

```bash
# 1. Repoyu klonla
git clone https://github.com/SKYMOD-Team/code-execution-agent.git
cd code-execution-agent

# 2. Sanal ortam oluştur
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Bağımlılıkları yükle
pip install -e .

# 4. API anahtarlarını ayarla
cp .env.example .env
# .env dosyasını aç ve anahtarları gir:
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPEN_SANDBOX_API_KEY=...
#   OPEN_SANDBOX_DOMAIN=...
```

---

## Çalıştırma

```bash
streamlit run app.py
```

Tarayıcıda `http://localhost:8501` açılır.

---

## Kullanım

1. Sol panelden dosya yükle (`.xlsx`, `.csv`, `.pdf`)
2. Soru yaz: *"Müşteri başına ortalama sipariş sayısı nedir? PDF rapor ver."*
3. Agent analiz yapar ve PDF indirme butonu çıkar

---

## Nasıl Çalışır?

```
Dosya yüklenir
    ↓
Skill sistemi devreye girer (xlsx/csv/pdf/visualization)
    ↓
parse_file → schema + boyut bilgisi
    ↓
< 40MB → pandas + pickle      ≥ 40MB → Excel→CSV + DuckDB
    ↓
Analiz + m dict + WeasyPrint PDF → tek execute'da
    ↓
download_file → kullanıcıya PDF
```

Detaylar için:
- `ARCHITECTURE.md` — sistem mimarisi
- `TECHNICAL_GUIDE.md` — teknik detaylar (pickle, DuckDB, execute izolasyonu)

---

## Temel Kurallar

| Kural | Açıklama |
|---|---|
| **Query-Faithful Scope** | Sorguya sadık kal — kullanıcı istemediği sürece veriyi kısma, filtre ekleme |
| **Data Fabrication** | Hesaplanamayan sayıyı rapora koyma |
| **Process ALL Data** | `head(1000)`, `nrows=5000` gibi kısayollar yasak |
| **ReAct Loop** | Her adımda THOUGHT → EXECUTE → OBSERVE → DECIDE |

---

## Proje Yapısı

```
agentic_analyze_d/
├── app.py                          # Streamlit UI girişi
├── src/
│   ├── agent/
│   │   ├── graph.py                # Agent kurulumu + smart_interceptor
│   │   └── prompts.py              # Temel sistem prompt + kurallar
│   ├── tools/
│   │   ├── execute.py              # OpenSandbox execute (base64 pattern)
│   │   ├── file_parser.py          # parse_file tool
│   │   ├── generate_html.py        # HTML dashboard tool
│   │   ├── download_file.py        # PDF download tool
│   │   └── artifact_store.py       # Thread-safe UI köprüsü
│   ├── sandbox/
│   │   └── manager.py              # OpenSandbox yaşam döngüsü
│   └── skills/
│       ├── registry.py             # Skill tetikleyiciler (40MB eşiği vb.)
│       └── loader.py               # Sistem prompt derleyici
├── skills/
│   ├── xlsx/
│   │   ├── SKILL.md                # Excel kuralları, pivot format, WeasyPrint
│   │   └── references/
│   │       ├── large_files.md      # ≥40MB DuckDB pattern
│   │       └── multi_file_joins.md # Çoklu dosya JOIN
│   ├── csv/SKILL.md                # CSV/TSV kuralları, DuckDB pattern
│   ├── pdf/SKILL.md                # PDF parsing kuralları
│   └── visualization/SKILL.md      # Grafik ve görselleştirme kuralları
├── pyproject.toml                  # Bağımlılıklar
├── ARCHITECTURE.md                 # Sistem mimarisi
└── TECHNICAL_GUIDE.md              # Teknik rehber
```

---

## Ortam Değişkenleri

| Değişken | Açıklama |
|---|---|
| `ANTHROPIC_API_KEY` | Claude modeline erişim |
| `OPEN_SANDBOX_API_KEY` | OpenSandbox API anahtarı |
| `OPEN_SANDBOX_DOMAIN` | OpenSandbox sunucu adresi |

---

## Sorun Giderme

**Sandbox başlamıyor:**
OpenSandbox API key ve domain ayarlarını kontrol et.
```bash
curl http://$OPEN_SANDBOX_DOMAIN/health
```

**`ModuleNotFoundError: deepagents`:**
```bash
pip install -e .
```

**WeasyPrint PDF oluşturulmuyor:**
Sandbox içinde otomatik kurulur. İlk sorgu ~30 saniye paket kurulumu için bekler.
