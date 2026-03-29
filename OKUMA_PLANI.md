# Agentic Analyze — Sıfırdan Anlama Okuma Planı

Bu plan, projeyi katman katman anlamak için dosyaları hangi sırayla okuyacağını ve her tasarım kararının neden yapıldığını açıklar.

---

## Aşama 0 — Ne inşa edildi? (5 dk)

### 1. `README.md`
**Ne:** Projenin tek cümlelik özeti + kurulum + nasıl çalışır şeması.  
**Neden önce:** "Excel/CSV/PDF yükle → soru sor → PDF rapor al" akışını kafana oturtmadan kod okusan kaybolursun.  
**Özellikle bak:** "Nasıl Çalışır?" bölümündeki ASCII şeması (40MB eşiği, pickle vs DuckDB kararı).

---

## Aşama 1 — Büyük resim: mimari ve teknik kararlar (30 dk)

### 2. `ARCHITECTURE.md`
**Ne:** Tüm sistemin ASCII diyagramı — UI'dan sandbox'a kadar her katman.  
**Neden:** Kod okumadan önce hangi parçanın neyle konuştuğunu bilmek gerekiyor.  
**Özellikle bak:**
- **Smart Interceptor diyagramı** — ajanın araç çağrılarına kural koyan katman (BLOCK / RATE-LIMIT / AUTO-FIX üçlüsü)
- **ArtifactStore diyagramı** — *neden* session_state kullanılamıyor; agent thread'i neden ayrı
- **Progressive Disclosure Flow** — 40MB eşiğinde neden farklı strateji

### 3. `TECHNICAL_GUIDE.md`
**Ne:** "Neden böyle yaptık?" sorusunun cevabı — 15 teknik bölüm.  
**Neden:** Pickle vs CSV, WeasyPrint vs fpdf2, DuckDB ne zaman, race condition çözümü — bunlar kod okurken "bu neden böyle?" diye soracağın sorular.  
**Kritik bölümler:**
- **§1 Execute İzolasyonu** — her execute() ayrı Python process, değişkenler yaşamıyor → pickle zorunlu
- **§2 Pickle Pattern** — execute'lar arası veri taşımanın en hızlı yolu
- **§3 Büyük Dosya Pattern** — Excel→CSV→DuckDB neden ve nasıl
- **§5 WeasyPrint** — fpdf2 yerine neden HTML+CSS tabanlı PDF
- **§13 Race Condition** — sandbox hazır olmadan agent başlarsa ne olur → `threading.Event`
- **§14 ArtifactStore** — Streamlit `ScriptRunContext` hatası neden oluşur, çözümü

---

## Aşama 2 — Giriş noktası ve UI katmanı (20 dk)

### 4. `app.py`
**Ne:** Streamlit uygulamasının tüm giriş noktası — 57 satır.  
**Neden:** Uygulamanın boot sırasını görmek için. API key doğrulama → `init_session()` → UI render sırası.  
**Dikkat:** `init_session()` sandbox'ı arka planda başlatır — kullanıcı henüz soru sormadan bile.

### 5. `src/ui/session.py`
**Ne:** Session başlatma + sandbox prewarm + atexit cleanup.  
**Neden:** "Neden sayfa açılınca sandbox hemen başlıyor?" sorusunun cevabı burada.

### 6. `src/ui/chat.py`
**Ne:** Streaming yanıt render'ı, step geçmişi, artifact popup.  
**Neden:** `agent.stream()` ile gelen chunk'ların nasıl ekrana bastığını ve `ArtifactStore`'dan HTML/PDF'in nasıl çekildiğini görmek için.

---

## Aşama 3 — Ajan çekirdeği (30 dk)

### 7. `src/agent/prompts.py`
**Ne:** `BASE_SYSTEM_PROMPT` — ajanın tüm davranış kuralları (191 satır).  
**Neden:** Ajanın ne yapıp yapamayacağını belirleyen tek metin. KURAL 1 (veri uydurma yasak), KURAL 2 (ReAct döngüsü), KURAL 3 (schema-first) burada.  
**Önemli kararlar:**
- Sayı içeren chat mesajı yasak → sayısal detay PDF'e
- `fpdf2` değil `weasyprint` referansı — neden HTML tercih edildi

### 8. `src/agent/graph.py`
**Ne:** `build_agent()` + `smart_interceptor` — projenin en karmaşık dosyası (529 satır).  
**Neden:** Tüm kontrol mantığı burada: araç çağrısı filtreleme, execute sayacı, font auto-fix, hardcoded metrik tespiti.  
**Özellikle bak:**
- `smart_interceptor` closure'ı — neden `nonlocal` ile durum tutuyor
- `reset_interceptor_state()` — agent cache'lendiği için her `stream()` öncesi sıfırlanmak zorunda
- `get_or_build_agent()` — fingerprint (dosya adı + boyutu) ile cache → yeni dosya = yeni agent
- `_compute_max_execute()` — basit sorgu=6, karmaşık/büyük=10 dinamik limit

---

## Aşama 4 — Sandbox yönetimi (15 dk)

### 9. `src/sandbox/manager.py`
**Ne:** Daytona sandbox yaşam döngüsü — oluştur, başlat, paket kur, dosya yükle, durdur.  
**Neden:** "Sandbox neden ilk sorguda yavaş?" sorusunun cevabı burada.  
**Kritik kararlar:**
- **`threading.Event` (_packages_ready)** — race condition: paketler kurulmadan query giderse hata
- **Native upload → fallback chunked base64** — büyük dosyalar için güvenilirlik
- **`auto_delete_interval=3600`** — orphan sandbox'ları otomatik temizle (30GB disk limiti)
- **Critical vs Optional paket ayrımı** — weasyprint/pandas kritik, duckdb/pdfplumber opsiyonel → farklı öncelik

---

## Aşama 5 — Araçlar (20 dk)

### 10. `src/tools/artifact_store.py`
**Ne:** Thread-safe global singleton — agent thread'den UI thread'e HTML/PNG/PDF köprüsü.  
**Neden önce:** Diğer tool'ların neden `st.session_state` yazmadığını anlamak için.

### 11. `src/tools/execute.py`
**Ne:** Daytona sandbox'ta Python kodu çalıştır + base64 temp file mekanizması.  
**Neden:** Shell quote-escaping sorunu neden base64 encode ile çözüldü → interceptor bu ham kodu görüyor.

### 12. `src/tools/file_parser.py`
**Ne:** `parse_file` tool — Excel/CSV/PDF schema'sını LOCAL'de çıkar (execute harcamaz).  
**Neden:** Agent execute bütçesini schema keşfine harcamasın diye ayrı, LOCAL bir tool.

### 13. `src/tools/download_file.py` + `generate_html.py` + `visualization.py`
**Ne:** Sandbox'tan dosya indir, HTML dashboard render, PNG grafik üret.  
**Hepsi** `ArtifactStore`'a yazar, UI thread okuyor.

---

## Aşama 6 — Skill sistemi (15 dk)

### 14. `src/skills/registry.py`
**Ne:** Hangi dosya tipinde hangi skill yüklenir — extension + boyut + keyword trigger'ları.  
**Neden:** Sistem prompt'u her zaman maksimum tutmak yerine dinamik yükleme → context window tasarrufu.

### 15. `src/skills/loader.py`
**Ne:** Skill MD dosyalarını okuyup base prompt'a ekler.

### 16. `skills/xlsx/SKILL.md`
**Ne:** Agent'a Excel için kural seti — sheet tespiti, pickle pattern, analiz kuralları, PDF kalıbı.  
**Neden en sona:** Bunu okuyunca "agent bu kodu nereden öğreniyor?" sorusu netleşiyor.

### 17. `skills/xlsx/references/large_files.md` + `multi_file_joins.md`
**Ne:** Sadece gerekince yüklenen ek referanslar — DuckDB pattern, multi-file JOIN.

---

## Tasarım Kararları Özeti

| Karar | Neden |
|---|---|
| **Daytona sandbox** | Agent'ın ürettiği Python kodu izole çalışsın, host sistem etkilenmesin |
| **execute izolasyonu** | Her execute ayrı process → değişkenler ölüyor → pickle ile taşı |
| **40MB eşiği (DuckDB)** | pandas.read_excel() büyük dosyada MemoryError → DuckDB lazy query |
| **WeasyPrint > fpdf2** | HTML/CSS ile tablo+renk+Türkçe çok daha kolay; fpdf2 font sorunları |
| **ArtifactStore** | `st.session_state` agent thread'inden erişilemiyor (ScriptRunContext hatası) |
| **Smart Interceptor** | LLM davranışını kod+prompt yerine teknik katmanda garantile |
| **Progressive disclosure** | Her analiz için 800 satır prompt yerine dosya tipine göre 500-800 satır |
| **Agent fingerprint cache** | Dosya değişmediyse aynı agent'ı kullan; her mesajda rebuild etme |
| **create_agent > create_deep_agent** | SubAgent, FilesystemMiddleware, TodoListMiddleware gereksizdi → minimal middleware |
| **threading.Event (packages_ready)** | Sandbox hazır olmadan query gelirse paket bulunamaz → senkronizasyon |
| **Critical vs Optional paketler** | weasyprint/pandas her sorgu için kritik; duckdb/pdfplumber sadece büyük dosyada |
