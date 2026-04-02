# ReAct vs Plan-and-Execute Pattern Değerlendirmesi

**Tarih:** 2026-03-31
**Proje:** Agentic Analyze
**Mevcut Pattern:** ReAct (LangChain `create_agent`)

---

## Executive Summary

**Karar: ReAct pattern'de kalınmalı.**

Plan-and-Execute'a geçiş, bu projenin spesifik gereksinimlerine (multi-turn conversations, dynamic file size handling, execute isolation) uygun değil. Mevcut ReAct implementasyonu, smart interceptor ile optimize edilmiş durumda ve temel sorunlar çözülmüş.

---

## 1. Mevcut Durum: ReAct Pattern

### 1.1 Nasıl Çalışıyor?

```
User Query → Agent (LLM)
    ↓
DÜŞÜNCE: "parse_file ile schema öğrenmeliyim"
    ↓
Tool Call: parse_file(file)
    ↓
GÖZLEM: [columns, dtypes, preview]
    ↓
DÜŞÜNCE: "Şimdi veriyi okuyup temizlemeliyim"
    ↓
Tool Call: execute(pd.read_excel + clean + to_pickle)
    ↓
GÖZLEM: [401,604 satır, ✅ Doğrulama OK]
    ↓
DÜŞÜNCE: "Analiz yapıp PDF oluşturmalıyım"
    ↓
Tool Call: execute(read_pickle + analysis + weasyprint PDF)
    ↓
GÖZLEM: [✅ PDF: 127 KB]
    ↓
KARAR: "PDF hazır, kullanıcıya sun"
    ↓
Tool Call: download_file('/home/daytona/rapor.pdf')
```

**Özet:** Her adım sonrası LLM değerlendirme yapar, dinamik kararlar alır.

### 1.2 ReAct'in Avantajları (Bu Projede)

| Avantaj | Açıklama | Önem |
|---|---|---|
| **Dynamic error recovery** | Execute fail olursa LLM sorunu analiz eder, düzeltir | 🔴 Critical |
| **Multi-turn independence** | Her soru bağımsız ReAct loop başlatır, pickle scope narrowing önlenir | 🔴 Critical |
| **Adaptive strategy** | parse_file sonrası file_size_mb görülünce 40MB+ → CSV strategy | 🟡 Important |
| **Granular control** | Her tool call smart_interceptor'dan geçer, blocklar anında apply | 🟡 Important |
| **Natural conversation** | Turkish prompt'lar ile DÜŞÜNCE → GÖZLEM akışı | 🟢 Nice-to-have |

### 1.3 ReAct'in Dezavantajları (Mevcut Sorunlar)

| Sorun | Açıklama | Çözüm Durumu |
|---|---|---|
| **Tool chaining** | parse_file → ls → parse_file döngüleri | ✅ ÇÖZÜLDÜ (circuit breaker) |
| **Execute quota waste** | Schema re-check, unnecessary sampling | ✅ ÇÖZÜLDÜ (interceptor blocks) |
| **Infinite loops** | Bazı pattern'ler sonsuz döngüye girebilir | ✅ ÇÖZÜLDÜ (MAX_CONSECUTIVE_BLOCKS=2) |
| **Correction limits** | Max 2 correction → sonra pes ediyor | ⚠️ Kısmi (business constraint) |
| **LLM call cost** | Her adımda reasoning token consume | ⚠️ Acceptable (prompt caching helps) |

**Not:** Kritik sorunlar smart_interceptor ile çözülmüş durumda.

---

## 2. Alternatif: Plan-and-Execute Pattern

### 2.1 Nasıl Çalışır?

```
User Query → Planner Agent (LLM)
    ↓
PLAN:
  Step 1: parse_file(file) → get schema
  Step 2: execute(read + clean + pickle)
  Step 3: execute(analysis + validate)
  Step 4: execute(pickle + PDF generation)
  Step 5: download_file(pdf)
    ↓
Executor Agent (Sequential)
    ├─ Step 1 → OK
    ├─ Step 2 → OK
    ├─ Step 3 → FAIL → Replanner (optional)
    ├─ Step 3 (revised) → OK
    ├─ Step 4 → OK
    └─ Step 5 → OK
```

**Özet:** Tüm adımlar önceden planlanır, sonra sırayla execute edilir.

### 2.2 Plan-and-Execute'un Avantajları

| Avantaj | Açıklama | Bu Projede Etkisi |
|---|---|---|
| **Proactive planning** | Tüm adımlar görülür, optimal path seçilir | 🟢 Marginal (ReAct de iyi planlıyor) |
| **Fewer LLM calls** | Planning + execution, her step arası LLM yok | 🟢 Prompt caching ile fark az |
| **Tool chaining önlenir** | Plan zaten sequential, döngü riski düşük | ⚠️ ReAct'te de interceptor ile çözülmüş |
| **Predictable flow** | Debug kolay, step sequence belli | 🟢 Nice-to-have |

### 2.3 Plan-and-Execute'un Dezavantajları (Bu Projede CRİTİCAL)

| Dezavantaj | Açıklama | Etki |
|---|---|---|
| **Multi-turn cache loss** | Her soru için yeni plan → agent rebuild → fingerprint change | 🔴 Critical |
| **Dynamic adaptation zor** | parse_file sonrası 40MB+ görülse bile plan değiştiremez | 🔴 Critical |
| **Execute isolation** | Plan execute #1'de değişken tanımlar, #2'de kullanır diyor → FAIL | 🔴 Critical |
| **Error recovery rigid** | Step fail → replan → costly + context loss | 🟡 Important |
| **Sandbox lifecycle** | Planlama sırasında sandbox hazır mı bilinmez (ModuleNotFoundError riski) | 🟡 Important |
| **Turkish reasoning** | Planning prompt da Turkish olmalı (2 dilde reasoning overhead) | 🟢 Minor |

---

## 3. Kritik Faktör Analizi

### 3.1 Multi-Turn Conversations (🔴 BLOCKER)

**Gerçek kullanım senaryosu:**

```
Turn 1: "Müşteri sayısı nedir? PDF ver"
  → ReAct: parse → clean → analyze → PDF
  → Agent cached by (file_name, file_size)

Turn 2: "Aylık trend grafiği göster, HTML dashboard"
  → ReAct: aynı cached agent, yeni ReAct loop
  → pd.read_excel() FRESH data (scope narrowing önlendi)

Turn 3: "VIP müşterileri filtrele, Excel dosyası ver"
  → ReAct: yine aynı agent, bağımsız loop
```

**Plan-and-Execute ile:**

```
Turn 1: "Müşteri sayısı nedir?"
  → Planner: Plan üret
  → Executor: Plan execute et

Turn 2: "Aylık trend grafiği"
  → Planner: Yeni plan ÜRETMELİ (previous plan scope narrowed)
  → Agent cache'i yenilemeli mi? (fingerprint change)
  → Turn 1'in pickle'ı kullansa scope narrowing problemi
  → Fresh Excel okusa execution overhead
```

**Sonuç:** Multi-turn için ReAct daha uygun. Her turn bağımsız loop, cache korunur.

### 3.2 Dynamic File Strategy (40MB Threshold)

**ReAct flow:**

```
parse_file(file) → GÖZLEM: "file_size_mb: 65.2"
    ↓
DÜŞÜNCE: "40MB üzeri → CSV + DuckDB kullanmalıyım"
    ↓
execute(Excel → CSV dönüşümü)
    ↓
execute(DuckDB query)
```

**Plan-and-Execute flow:**

```
Planner: "User query + file metadata" → Plan üret
  Problem: File size planlama sırasında bilinmez
  (parse_file sonrası öğrenilir)

Çözüm 1: parse_file → replan
  → Extra planning cost, overhead

Çözüm 2: Her zaman worst-case plan (CSV strategy)
  → Küçük dosyalar için suboptimal
```

**Sonuç:** ReAct'te adaptive strategy doğal, Plan-and-Execute'da costly.

### 3.3 Execute Isolation Pattern

**Teknik gerçek:**

Her `execute()` ayrı Python subprocess → değişkenler persist etmez.

**ReAct handling:**

```python
# Execute 1 (agent aware: sonraki execute'da değişken yok)
df.to_pickle('/home/daytona/clean.pkl')

# Execute 2 (agent pickle'dan okuyacağını biliyor)
df = pd.read_pickle('/home/daytona/clean.pkl')
```

**Plan-and-Execute risk:**

```
Plan:
  Step 2: execute(df = pd.read_excel(...); df_clean = df.dropna())
  Step 3: execute(m = calculate_metrics(df_clean))
                                         ^^^^^^^^^^^
                                         NameError: df_clean not defined
```

**Neden?** Planner, execute isolation'ı modellemiyor. ReAct'te her execute sonrası LLM gözlem yapıyor, bir sonraki execute'u buna göre şekillendiriyor.

**Çözüm:** Plan-and-Execute'da execute isolation'ı prompt'a inject etmek gerekir:

```
RULE: Each execute is isolated. Pass data via:
- Pickle: df.to_pickle('/home/daytona/X.pkl') → pd.read_pickle()
- CSV: df.to_csv('/home/daytona/X.csv') → duckdb.read_csv_auto()
```

Ama bu ReAct'te zaten mevcut ve doğal flow'da öğreniliyor.

---

## 4. Smart Interceptor Analizi

Mevcut ReAct implementasyonunda **smart_interceptor** katmanı, tool call'ları execute edilmeden önce filtreler/düzeltir:

### 4.1 Interceptor'un Blokladığı Pattern'ler

| Pattern | Sebep | Etki |
|---|---|---|
| `ls`, `find`, `cat`, `os.listdir` | parse_file zaten schema verdi | Execute quota korunur |
| `pip install`, `subprocess` | Paketler pre-installed | Security + quota |
| `urllib`, `requests`, `wget` | Network yasak | Security |
| `nrows > 10` | Sampling yasak | Data fabrication önlenir |
| Duplicate `parse_file` | Schema zaten var | ⛔ + circuit breaker |
| `pd.read_pickle()` in execute #1-2 | Multi-turn scope narrowing | 🔴 Critical fix |

### 4.2 Interceptor'un Auto-Fix'lediği Pattern'ler

| Pattern | Fix | Sebep |
|---|---|---|
| `Arial` / `Helvetica` fonts | → `DejaVu` | Sandbox'ta sadece DejaVu var |
| Missing `add_font()` | Inject font registration | Turkish chars için gerekli |
| Hardcoded metric variables | Block | Data fabrication riski |

### 4.3 Circuit Breaker Mekanizması

```python
_consecutive_blocks = 0
_MAX_CONSECUTIVE_BLOCKS = 2

if _consecutive_blocks >= 2:
    return ToolMessage("🛑 CIRCUIT BREAKER: Sonsuz döngü...")
```

**Etki:** parse_file → ls → parse_file → ls döngüsü 2. adımda kesilir.

**Plan-and-Execute'da:** Circuit breaker gerekir mi? Muhtemelen hayır (plan sequential), ama planner yanlış plan üretirse aynı sorun olabilir.

---

## 5. Cost-Benefit Analizi

### 5.1 Geçiş Maliyeti

| Görev | Efor | Risk |
|---|---|---|
| LangChain Plan-and-Execute adapter | 2-3 gün | Medium |
| Execute isolation handling in planner | 1 gün | High (test coverage gerekli) |
| Multi-turn plan caching strategy | 2 gün | High (fingerprint logic değişir) |
| Dynamic file strategy in planning | 1 gün | Medium |
| Interceptor refactor (plan-aware) | 1 gün | Medium |
| Turkish planning prompts | 1 gün | Low |
| Regression testing | 2 gün | High (end-to-end scenarios) |
| **TOTAL** | **10-12 gün** | **High** |

### 5.2 Beklenen Faydalar

| Fayda | Gerçekçi mi? | Açıklama |
|---|---|---|
| Execute quota azalır | ❌ Hayır | ReAct zaten 6-10 execute, optimal |
| Tool chaining ortadan kalkar | ⚠️ Kısmen | Interceptor zaten hallediyor |
| LLM call cost azalır | ⚠️ Kısmen | Prompt caching var, fark ~%10-15 |
| Debugging kolaylaşır | ✅ Evet | Plan görünürlüğü iyi |
| **Net fayda** | **Düşük** | Mevcut sorunlar zaten çözülmüş |

### 5.3 Riskler

| Risk | Olasılık | Etki |
|---|---|---|
| Multi-turn performance düşer | Yüksek | Agent cache loss → yavaşlar |
| Dynamic adaptation bozulur | Yüksek | 40MB+ dosyalar fail olabilir |
| Execute isolation bugs | Orta | Test coverage artırılmalı |
| Regression bugs | Orta | Mevcut flow değişir |

---

## 6. Karar Matrisi

| Kriter | ReAct (Mevcut) | Plan-and-Execute | Ağırlık | Sonuç |
|---|---|---|---|---|
| Multi-turn support | ✅ Excellent | ❌ Poor | 🔴 x3 | **ReAct +9** |
| Dynamic adaptation | ✅ Good | ⚠️ Medium | 🔴 x3 | **ReAct +3** |
| Error recovery | ✅ Good | ⚠️ Medium | 🟡 x2 | **ReAct +2** |
| Execute isolation | ✅ Handled | ⚠️ Risky | 🔴 x3 | **ReAct +3** |
| Cost efficiency | ⚠️ Medium | ✅ Good | 🟢 x1 | **P&E +1** |
| Debugging | ⚠️ Medium | ✅ Good | 🟢 x1 | **P&E +1** |
| Implementation cost | ✅ Zero | ❌ High | 🟡 x2 | **ReAct +4** |
| **TOTAL** | | | | **ReAct +21** |

**Skor:** ReAct wins decisively.

---

## 7. Öneri: ReAct Optimization Roadmap

Plan-and-Execute'a geçmek yerine, mevcut ReAct'i optimize et:

### 7.1 Short-term (Hemen Uygulanabilir)

- [x] ✅ Circuit breaker (YAPILMIŞ)
- [x] ✅ Multi-turn scope narrowing prevention (YAPILMIŞ)
- [x] ✅ Hardcoded metric blocking (YAPILMIŞ)
- [ ] 📝 Correction loop visibility: Execute output'a correction attempt count ekle
- [ ] 📝 Planning hint injection: DÜŞÜNCE bloğuna "remaining execute budget" reminder

### 7.2 Medium-term (1-2 Hafta)

- [ ] 🔄 ReAct step tracing: Her DÜŞÜNCE → KARAR arasını log'la (debugging için)
- [ ] 🔄 Execute quota dynamic adjustment: Basit sorgular için 4'e düşür (6 yerine)
- [ ] 🔄 Parallel tool calls: parse_file + sandbox_status aynı anda çağrılabilir

### 7.3 Long-term (Future)

- [ ] 💡 Hybrid approach: İlk turn'de "skeleton plan" oluştur (3-4 high-level step), ReAct ile execute et
- [ ] 💡 Self-reflection: Execute fail olduysa, agent "ne yanlış gitti?" analysis yapsın (1 extra LLM call)

---

## 8. Karşılaştırmalı Senaryo: Gerçek Kullanım

### Senaryo: 50MB Excel, Multi-Sheet, Multi-Turn

**User:**
> Turn 1: "Bu dosyayı analiz et, genel istatistikleri ver"

**ReAct Flow:**

```
parse_file → schema + "file_size_mb: 52.3, sheets: ['2019', '2020', '2021']"
    ↓ (LLM adaptive decision)
DÜŞÜNCE: "40MB+ → CSV strategy, multi-sheet → UNION ALL"
    ↓
execute(Excel → CSV per sheet, ~10s)
execute(DuckDB UNION ALL, stats, ~3s)
    ↓
Output: "3 dönem, 1.2M satır, 450K müşteri"
```

**Plan-and-Execute Flow:**

```
Planner: (file metadata yok) → Assume pandas strategy
Plan:
  1. parse_file
  2. execute(pd.read_excel)  ← MemoryError (52MB)
  3. (blocked)
    ↓
Replanner: (parse_file output gördü) → Revise plan
Plan:
  1. execute(Excel → CSV)
  2. execute(DuckDB)
    ↓
Executor: Run revised plan
```

**Fark:** ReAct 2 execute, Plan-and-Execute 3 (1 fail + replan).

---

**User:**
> Turn 2: "2020 yılı için aylık trend grafiği çiz, HTML dashboard"

**ReAct Flow:**

```
(agent cached, new ReAct loop)
DÜŞÜNCE: "CSV'ler var, 2020 sheet'i filter, monthly group"
    ↓
execute(DuckDB query WHERE period='2020', GROUP BY month)
generate_html(Chart.js dashboard)
```

**Plan-and-Execute Flow:**

```
Planner: (previous plan'ı biliyor mu?)
  Seçenek A: Previous plan'dan devam → Scope narrowed (sadece 2020)
  Seçenek B: Fresh plan → CSV'leri yeniden read (overhead)
    ↓
Executor: Run
```

**Sorun:** Plan-and-Execute'da multi-turn state management belirsiz.

---

## 9. Sonuç ve Karar

### Karar: **ReAct pattern'de kal**

### Gerekçeler:

1. **Multi-turn conversations** projenin core use case'i → Plan-and-Execute uygun değil
2. **Dynamic file strategy** (40MB threshold) ReAct'te doğal, P&E'de costly replan gerektirir
3. **Execute isolation** ReAct'te observation-driven handling, P&E'de plan'a inject etmek zor
4. **Smart interceptor** mevcut sorunları zaten çözmüş (infinite loops, tool chaining)
5. **Implementation cost** (10-12 gün) vs **expected benefit** (düşük) orantısız
6. **Risk:** Multi-turn performance degradation, dynamic adaptation bugs

### Alternatif Yaklaşımlar:

**Hybrid (Future):**
- İlk turn'de "skeleton plan" üret (3-4 high-level step)
- ReAct loop içinde skeleton'ı reference et
- Plan deviate etse bile ReAct flexibility devrede

**Self-Reflection:**
- Execute fail → agent "why did it fail?" analysis
- 1 extra LLM call ama correction success rate artar

---

## 10. Kaynaklar

- **Mevcut kod:** [src/agent/graph.py](../src/agent/graph.py) (ReAct + interceptor)
- **Prompt:** [src/agent/prompts.py](../src/agent/prompts.py) (ReAct DÜŞÜNCE → GÖZLEM rules)
- **Multi-turn fix:** [git commit 53ca33d](https://github.com/.../commits/53ca33d) (scope narrowing prevention)
- **LangChain Docs:** [Plan-and-Execute](https://python.langchain.com/docs/how_to/plan_and_execute/)

---

## Revision History

| Date | Author | Change |
|---|---|---|
| 2026-03-31 | Claude Sonnet 4.5 | Initial analysis |
