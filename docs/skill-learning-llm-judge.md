# Skill Learning — LLM-as-Judge Sistemi

> **Branch:** skill-learning-judge  
> **Tarih:** Nisan 2026  
> **Durum:** Implement edildi, lokal test geçti

---

## 1. Bu Branch'te Ne Yaptık (Adım Adım)

### Adım 1: `learner.py` — Temel Altyapı (önceki branch'ten miras)
Zaten var olan yapı:
- `ErrorContext` dataclass — agent'ın çalışma hatalarını temsil eder
- `SkillSuggestion` dataclass — LLM'in ürettiği SKILL.md iyileştirme önerisi
- `extract_errors()` — agent tool call çıktılarından hata çıkarır (Traceback, BLOCKED, correction loop)
- `generate_skill_suggestion()` — Sonnet ile hata analizi yapıp SKILL.md iyileştirme önerisi üretir
- `detect_skills_for_errors()` — hangi skill'in aktif olduğunu tespit eder

### Adım 2: `learner.py` — LLM-as-Judge Eklendi
Yeni fonksiyonlar:
- **`JudgeResult`** dataclass — score (0.0–1.0), reason, skill_issue, skill_name
- **`_parse_judge_json()`** — LLM'in JSON çıktısını robust şekilde parse eder (markdown fence, extra text, garbage → fallback)
- **`judge_output()`** — Claude Haiku ile agent çıktısını puanlar. Girdi: kullanıcı sorgusu + agent yanıtı + son 5 execute çıktısı

### Adım 3: `learner.py` — Eval Log Sistemi
- **`_append_eval_log()`** — Her değerlendirmeyi `eval_log.jsonl`'e yazar (timestamp, score, reason, skill_issue, skill_name, action, query, suggestion)
- `skill_updated` olan kayıtlarda `suggestion` alanı da kaydedilir
- Append-only JSONL formatı — kolay grep/analiz
- `_file_lock` ile thread-safe yazma

### Adım 4: `learner.py` — Otomatik SKILL.md Güncelleme
- **`_apply_skill_suggestion_auto()`** — UI olmadan doğrudan SKILL.md'ye yazar
  - Suggestion doğrulama: min 20 char, max 3000 char, aksi halde reject/truncate
  - Dosya boyutu kontrolü: SKILL.md > 50KB ise yazma reddedilir
  - `_file_lock` ile thread-safe yazma
  - Yazma sonrası `load_skill.cache_clear()` ile cache temizleme

### Adım 5: `learner.py` — Tekrar Sayacı (Repeat Override)
- **`_count_similar_failures()`** — `eval_log.jsonl`'den son 20 kaydı tarar, aynı skill için düşük skorlu kayıt sayar
- **Override mantığı:** Judge `skill_issue=False` dese bile, aynı skill 3+ kez düşük skor aldıysa `skill_issue` override edilir → SKILL.md güncellenir
- `_file_lock` ile thread-safe okuma

### Adım 6: `learner.py` — `auto_learn()` Tek Giriş Noktası
Tüm mantığı birleştiren ana fonksiyon:
1. Judge çağır (Haiku)
2. Her zaman logla
3. Skor < 0.7 VE (skill_issue=True VEYA repeat_count ≥ 3) ise:
   - Hata çıkar + judge reason'ı error context olarak ekle
   - Sonnet ile suggestion üret
   - SKILL.md'ye otomatik uygula
4. **`SkillUpdateResult`** ile her skill sonucu ayrı takip edilir (son skill öncekini ezmez)

### Adım 7: `chat.py` — UI Entegrasyonu
- **Silindi:** `_run_skill_learning()` — eski UI-based öneri gösterme
- **Silindi:** `_apply_skill_suggestion()` — eski kullanıcı onaylı yazma
- **Eklendi:** `auto_learn()` çağrısı `threading.Thread(daemon=True)` ile — UI'yı bloklamaz, arka planda çalışır

### Adım 8: SKILL.md Güncellemeleri
- **xlsx/SKILL.md** ve **csv/SKILL.md** — "Output file summary (MANDATORY)" kuralı eklendi
  - Agent çıktı dosyası ürettikten sonra kolonları, shape'i, sample satırları yazdırır
  - Format serbest — sabit marker yok
  - Judge bu çıktıyı görerek daha isabetli puanlama yapar

### Adım 9: `.gitignore`
- `eval_log.jsonl` eklendi

### Adım 10: Judge'a parse_file Görünürlüğü
- `judge_output()` artık sadece `execute` değil, `parse_file` çıktısını da judge'a gönderiyor
- Judge, schema bilgisini (kolonlar, tarih formatları, veri tipleri) görerek agent'ın bu talimatlara uyup uymadığını değerlendirebilir
- Agent parse_file talimatlarını tekrar tekrar yok sayarsa → `skill_issue=true` → SKILL.md güncellenir

### Adım 11: Suggestion Prompt Düzeltmesi
- LLM'in ürettiği öneriler ` ```markdown ` fence içinde geliyordu → agent bunu kod bloğu olarak görüp talimat olarak okumuyordu
- "Analysis" bölümleri gereksiz gürültüydü → agent post-mortem raporu okumuyor
- Prompt güncellendi: "raw markdown yaz, fence kullanma, analysis yazma, sadece kural yaz"
- Good/bad örnek eklendi prompt'a
- "Agent'in yapamayacagi seyleri önerme" kuralı eklendi (internet erişimi yok)

### Adım 12: Eval Log'a Suggestion İçeriği Kaydı
- `_append_eval_log()` fonksiyonuna `suggestion_text` parametresi eklendi
- `action: "skill_updated"` olan kayıtlarda artık `"suggestion"` alanı da var
- SKILL.md'ye ne yazıldığı dosyayı açmadan `eval_log.jsonl`'den görülebilir
- `action: "none"` olan kayıtlarda alan eklenmez — log şişmez

### Adım 13: Güvenlik ve Sağlamlık Düzeltmeleri
- **`_file_lock`** — tüm dosya okuma/yazma operasyonları tek lock altında (race condition koruması)
- **Named constants** — 8 sabit dosya başında tanımlı (`_MAX_SKILL_FILE_BYTES`, `_REPEAT_OVERRIDE_THRESHOLD`, vb.)
- **Suggestion validation** — LLM çıktısı uzunluk kontrolünden geçer
- **SKILL.md boyut limiti** — 50KB üstü dosyalara yazma reddedilir

---

## 2. Metodoloji

### Felsefe: "Hatadan Öğrenme Döngüsü"

```
Kullanıcı sorgusu
      ↓
  Agent çalışır (sandbox'ta kod yazar + çalıştırır)
      ↓
  Agent yanıt verir
      ↓
  ──────────────────────── arka plan thread ────────────────────────
  │                                                                │
  │  1. Haiku judge: "Bu çıktı kullanıcının isteğini karşılıyor   │
  │     mı? Kod çıktısı beklenenle uyuşuyor mu?"                  │
  │                                                                │
  │  2. eval_log.jsonl'e yaz (her zaman)                           │
  │                                                                │
  │  3. Skor < 0.7?                                                │
  │     ├─ skill_issue=True → Sonnet ile öneri üret → SKILL.md'ye │
  │     │  otomatik yaz                                            │
  │     ├─ skill_issue=False, repeat < 3 → sadece logla            │
  │     └─ skill_issue=False, repeat ≥ 3 → override → SKILL.md'ye │
  │        otomatik yaz                                            │
  │                                                                │
  ──────────────────────────────────────────────────────────────────
```

### İki İyileştirme Yolu

| Yol | Tetikleyici | LLM | Çıktı |
|-----|-------------|-----|-------|
| **Error-based** | Kod hata verdi (Traceback, BLOCKED) | Sonnet | SKILL.md kuralı |
| **Quality-based** | Judge düşük skor verdi | Haiku (judge) + Sonnet (fix) | SKILL.md kuralı |

### Neden İki Ayrı Model?

- **Haiku (judge):** Ucuz, hızlı. Her sorgudan sonra çalışır → maliyet kritik. ~$0.001/sorgu
- **Sonnet (suggestion):** Akıllı, detaylı. Sadece iyileştirme gerektiğinde çalışır → nadir. ~$0.01/çağrı

---

## 3. Mimari Şema

```
┌─────────────────────────────────────────────────────────────────┐
│                        chat.py (Streamlit UI)                   │
│                                                                 │
│  Kullanıcı sorgusu → Agent stream → Yanıt göster               │
│                                          │                      │
│                                    ┌─────┴──────┐              │
│                                    │ threading   │              │
│                                    │ .Thread()   │              │
│                                    │ daemon=True │              │
│                                    └─────┬──────┘              │
└──────────────────────────────────────────┼──────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     learner.py — auto_learn()                   │
│                                                                 │
│  ┌──────────────────┐    ┌───────────────────┐                 │
│  │  judge_output()   │    │ _parse_judge_json()│                 │
│  │  (Haiku ~$0.001)  │───▶│ robust JSON parse │                 │
│  └────────┬─────────┘    └───────────────────┘                 │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────┐                                          │
│  │ _append_eval_log()│──────▶ eval_log.jsonl                   │
│  │  (her zaman)      │       (append-only JSONL)               │
│  └────────┬─────────┘                                          │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────────────────────────────┐                  │
│  │           Karar Ağacı                     │                  │
│  │                                           │                  │
│  │  score ≥ 0.7?  ──▶ DONE (no action)      │                  │
│  │                                           │                  │
│  │  score < 0.7 + skill_issue=True?          │                  │
│  │    ──▶ extract_errors()                   │                  │
│  │    ──▶ generate_skill_suggestion() [Sonnet]│                  │
│  │    ──▶ _apply_skill_suggestion_auto()     │                  │
│  │                                           │                  │
│  │  score < 0.7 + skill_issue=False?         │                  │
│  │    ──▶ _count_similar_failures()          │                  │
│  │    ──▶ repeat ≥ 3? OVERRIDE → fix         │                  │
│  │    ──▶ repeat < 3? sadece logla           │                  │
│  └──────────────────────────────────────────┘                  │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────┐                                          │
│  │ SKILL.md güncelle │──────▶ skills/{name}/SKILL.md           │
│  │ + cache_clear()   │       (append, max 50KB)                │
│  └──────────────────┘                                          │
└─────────────────────────────────────────────────────────────────┘

Veri Akışı:

  eval_log.jsonl                    SKILL.md
  ┌─────────────┐                 ┌──────────────────┐
  │ {score: 0.7} │                 │ # Excel Expertise │
  │ {score: 0.4} │  ◀── repeat ──▶│ ## Rules          │
  │ {score: 0.3} │    counter      │ ## New Rule ← LLM│
  │ ...          │                 │ ...               │
  └─────────────┘                 └──────────────────┘

Thread Safety:

  _file_lock (threading.Lock)
       │
       ├── eval_log.jsonl okuma
       ├── eval_log.jsonl yazma
       ├── SKILL.md boyut kontrolü
       └── SKILL.md yazma
```

---

## 4. Dosya Değişiklikleri Özeti

| Dosya | Değişiklik |
|-------|------------|
| `src/skills/learner.py` | **Yeni dosya.** `JudgeResult`, `SkillUpdateResult`, `judge_output()`, `_parse_judge_json()`, `_append_eval_log()`, `_count_similar_failures()`, `_apply_skill_suggestion_auto()`, `auto_learn()` |
| `src/ui/chat.py` | Silinen: `_run_skill_learning()`, `_apply_skill_suggestion()`. Yeni: `auto_learn()` background thread çağrısı |
| `src/agent/graph.py` | `MemorySaver` → `SqliteSaver` (persistent checkpointer) |
| `skills/xlsx/SKILL.md` | Yeni: "Output file summary (MANDATORY)", "Column Addition Rules", "File Handling Rules", "Currency Addition Verification Rules" |
| `skills/csv/SKILL.md` | Yeni: "Output file summary (MANDATORY)" kuralı |
| `requirements.txt` | Yeni: `langgraph-checkpoint-sqlite==3.0.3` |
| `.gitignore` | Yeni: `eval_log.jsonl`, `checkpoints.db*` |
| `docs/skill-learning-llm-judge.md` | Bu doküman |

---

## 5. Ne Beklememiz Gerekiyor

### Kısa Vadede (İlk 50 Sorgu)

- **eval_log.jsonl dolmaya başlar** — her sorgu bir kayıt
- **Ortalama skor 0.6–0.8 arası** olacak (ilk kullanımlarda agent SKILL.md kurallarını tam okumayabilir)
- **1-2 otomatik SKILL.md güncellemesi** olacak — genellikle tekrarlayan hatalar için
- **Judge maliyeti:** ~$0.05 (50 × $0.001 Haiku çağrısı)

### Orta Vadede (50–200 Sorgu)

- **SKILL.md dosyaları zenginleşir** — agent'ın sık yaptığı hatalar için kurallar eklenir
- **Ortalama skor yükselir** (0.7–0.9) — çünkü agent güncellenmiş SKILL.md'yi okuyarak daha az hata yapar
- **Repeat override tetiklenir** — judge "skill sorunu değil" dese bile aynı hata 3+ kez olduysa SKILL.md güncellenir
- **SKILL.md boyutu artabilir** — 50KB limitine dikkat, gerekirse manuel temizlik

### Uzun Vadede (200+ Sorgu)

- **Self-improving loop oturur** — agent hatalarından otomatik öğrenir
- **eval_log.jsonl analiz edilebilir** — skor trendleri, hangi skill'ler sorunlu, hangi sorgu tipleri başarısız
- **SKILL.md kalitesi stabilize olur** — yeni kurallar azalır, mevcut kurallar yeterli olur

### Bilinen Limitasyonlar

| Limitasyon | Açıklama | Olası Çözüm |
|------------|----------|-------------|
| **Judge dosya içeriği görmez** | Agent'ın ürettiği Excel/CSV dosyasının gerçek içeriğini görmez, sadece kod çıktısını (stdout) görür | SKILL.md kuralı: "çıktı dosyasının özetini yazdır" — agent print ederse judge görür |
| **SKILL.md sadece büyür** | Otomatik temizlik/silme yok, sadece append | Manuel periyodik gözden geçirme veya gelecekte prune mekanizması |
| **Tek kullanıcı optimize** | Tüm kullanıcılar aynı SKILL.md'yi etkiler | Kullanıcı bazlı skill override (gelecek) |
| **Judge hallucination** | Haiku bazen yanlış skor verebilir | Threshold (0.7) ve repeat (3) tampon görevi görür |
| **Sonnet suggestion kalitesi** | LLM'in önerisi her zaman doğru olmayabilir | Min/max char kontrolü + SKILL.md boyut limiti |

### Maliyet Tahmini

| Bileşen | Sıklık | Birim Maliyet | Aylık (200 sorgu) |
|---------|--------|---------------|-------------------|
| Haiku (judge) | Her sorgu | ~$0.001 | ~$0.20 |
| Sonnet (suggestion) | ~%10 sorgu | ~$0.01 | ~$0.20 |
| **Toplam** | | | **~$0.40/ay** |

---

## 6. Hızlı Referans — Sabitleri Nerede Değiştirebilirim?

Tüm ayarlanabilir sabitler `src/skills/learner.py` dosya başında:

```python
_MAX_ERRORS_PER_SUGGESTION = 5       # suggestion LLM'e gönderilen max hata sayısı
_MAX_SKILL_CONTENT_CHARS = 3000      # suggestion LLM'e gönderilen mevcut SKILL.md uzunluğu
_MAX_TOOL_SUMMARY_STEPS = 5          # judge'a gönderilen son execute sayısı
_REPEAT_OVERRIDE_THRESHOLD = 3       # override için gereken tekrar sayısı
_EVAL_LOG_LOOKBACK = 20              # tekrar sayacının taradığı son kayıt sayısı
_MAX_SKILL_FILE_BYTES = 50_000       # SKILL.md max boyutu (byte)
_MAX_SUGGESTION_CHARS = 3000         # LLM suggestion max uzunluğu
_MIN_SUGGESTION_CHARS = 20           # LLM suggestion min uzunluğu
```

Threshold değiştirmek için `auto_learn()` çağrısındaki `threshold=0.7` parametresini ayarlayın.
