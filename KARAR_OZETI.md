# OpenSandbox Geçiş Kararı - Özet

**Tarih:** 1 Nisan 2026  
**Karar:** Daytona Cloud → OpenSandbox (mevcut sunucuya kurulum)

---

## 🎯 Nihai Kararlar

### 1. Sandbox Çözümü: OpenSandbox (Self-Hosted)

**Karar:** Daytona yerine OpenSandbox kullanılacak.

**Neden:**
- Maliyet %76 düşüyor ($630/ay → $150/ay)
- Execute isolation kalkar (pickle pattern gereksiz, kod basitleşir)
- Veri kontrolü elimizde (KVKK uyumlu)
- Açık kaynak (Apache-2.0), vendor lock-in yok

**Alternatifler değerlendirme:**
- ❌ Daytona'da kalmak → Pahalı ($480/ay sandbox maliyeti)
- ❌ AWS/Azure managed sandbox → Uygun çözüm yok
- ✅ OpenSandbox → En uygun (maliyet + kontrol)

---

### 2. Sunucu Seçimi: Mevcut Sunucu (external-compute)

**Karar:** Yeni sunucu kiralamak yerine mevcut sunucuya kurulacak.

**Neden:**
- Kaynaklar fazlasıyla yeterli:
  - 16 vCPU → 12-15 sandbox için ideal
  - 31GB RAM (26GB available) → 12×2GB sandbox + sistem
  - 975GB disk → Bol bol yeterli
  - Mevcut kullanım düşük (4.5GB RAM)
- Ek maliyet yok ($0 vs $120-150/ay yeni sunucu)
- Aynı network'te, latency avantajı

**Alternatifler değerlendirme:**
- ❌ Yeni sunucu kirala (Hetzner/AWS) → Gereksiz maliyet (+$120-150/ay)
- ❌ Cloud managed service → Uygun yok ve pahalı
- ✅ Mevcut sunucu → En ekonomik, yeterli kaynak

---

### 3. Hedef Kapasite: 12-15 Eşzamanlı Kullanıcı

**Karar:** Konservatif kaynak tahsisi (2GB RAM/sandbox, max 12 sandbox).

**Neden:**
- İlk hedef 10-15 kullanıcı → Mevcut kaynaklar yeterli
- Konservatif başla, izle, sonra optimize et
- Güvenlik payı (7GB RAM kalan → mevcut uygulamalar + buffer)

**Config:**
```
max_sandboxes = 12
default_memory = "2Gi"
default_cpu = "1"
```

---

### 4. Kurulum Stratejisi: Aynı Sunucuya + Docker İzolasyonu

**Karar:** Mevcut uygulamalarla birlikte çalışacak, Docker izolasyonu kullanılacak.

**Neden:**
- Kritik production uygulaması yok (risk düşük)
- Docker resource limits çakışma önler
- Monitoring ile erken uyarı (RAM %85+, CPU load >12.8)
- Acil durum otomatik müdahale (en eski sandbox'ları durdur)

**Risk azaltma:**
- Kaynak limitleri (max_sandboxes, RAM/CPU per sandbox)
- Monitoring scriptleri (her 5 dakika)
- Cleanup otomasyonu (haftalık)
- Backup otomasyonu (günlük)

---

## 💰 Maliyet Analizi

| | Daytona (Şu An) | OpenSandbox (Karar) | Fark |
|---|---|---|---|
| Sandbox | $480/ay | $0 | -$480 |
| Sunucu | - | $0 (mevcut) | $0 |
| Claude API | $150/ay | $150/ay | $0 |
| **TOPLAM** | **$630/ay** | **$150/ay** | **-$480/ay** |
| **Yıllık** | **$7,560** | **$1,800** | **-$5,760** |

**Tasarruf:** %76 düşüş (ayda $480, yılda $5,760)

---

## ⚙️ Teknik Detaylar

### Sunucu Kaynakları (external-compute)

```
CPU:     16 vCPU (Intel Xeon Icelake)    ✅ Yeterli
RAM:     31GB total, 26GB available      ✅ Yeterli
Disk:    975GB boş                       ✅ Fazlasıyla yeterli
OS:      Ubuntu                          ✅ İdeal
Mevcut:  4.5GB RAM kullanımda            ✅ Bol boş alan
```

### Kapasite Hesabı

```
Toplam RAM:                 31GB
- Mevcut uygulamalar:       4.5GB
- Sistem rezervi:           2GB
- Docker + OpenSandbox:     0.5GB
─────────────────────────────────
OpenSandbox için kalan:     24GB

Sandbox ayırımı:            12 sandbox × 2GB = 24GB
Kullanıcı kapasitesi:       12-15 eşzamanlı
```

### Kod Değişikliği

| Dosya | Değişiklik | Satır |
|-------|------------|-------|
| src/sandbox/manager.py | Tamamen yeniden (Daytona → OpenSandbox) | ~350 |
| src/tools/download_file.py | API değişikliği | ~20 |
| src/agent/prompts.py | Pickle talimatları kaldır | ~15 |
| src/skills/**/*.md | Pickle referansları güncelle | ~10 |
| requirements.txt | Paket değişikliği | 2 |
| **TOPLAM** | | **~400 satır** |

**Süre:** ~1 hafta (1 developer, full-time)

---

## 📅 Kurulum Süreci

### Faz 1: Altyapı Kurulumu (1 gün)

- [ ] Docker kurulumu
- [ ] Custom sandbox image build
- [ ] OpenSandbox server kurulum
- [ ] Config ayarları
- [ ] Systemd servisleri
- [ ] Monitoring scriptleri
- [ ] Cleanup/backup otomasyonu

### Faz 2: Kod Değişikliği (1 hafta)

- [ ] manager.py yeniden yaz
- [ ] Test ve doğrulama
- [ ] Prompt/skill güncelleme

### Faz 3: Test (2-3 gün)

- [ ] Sandbox oluşturma/silme test
- [ ] Dosya yükleme test
- [ ] Analiz ve PDF üretme test
- [ ] Kaynak kullanımı izleme
- [ ] Edge case testleri

**Toplam:** ~2 hafta (altyapı 1 gün + kod 1 hafta + test 2-3 gün)

---

## ⚠️ Risk ve Azaltma

### Risk 1: Mevcut Uygulamalarla Çakışma

**Olasılık:** Düşük  
**Etki:** Orta  
**Azaltma:**
- Docker resource limits (max_sandboxes, CPU, RAM)
- Monitoring (RAM %85+ → otomatik sandbox durdur)
- Acil durum: `docker ps | xargs docker stop`

### Risk 2: Kaynak Tükenmesi

**Olasılık:** Düşük  
**Etki:** Yüksek  
**Azaltma:**
- Konservatif başlangıç (12 sandbox max)
- Otomatik cleanup (haftalık Docker prune)
- Monitoring alarmları
- İlk 3 ay dikkatli izleme

### Risk 3: Kod Değişikliği Sorunları

**Olasılık:** Orta  
**Etki:** Yüksek  
**Azaltma:**
- Test ortamında önce doğrula
- Rollback planı (Daytona kodu korunur)
- Adım adım migration (önce sandbox, sonra prompt)

---

## ✅ Başarı Kriterleri

### Kurulum Başarılı Sayılır Eğer:

1. ✅ Sandbox 10 saniye içinde oluşuyor
2. ✅ Execute komutları 1-3 saniyede çalışıyor
3. ✅ PDF rapor 5 saniyede üretiliyor
4. ✅ 1 saat inaktivitede sandbox otomatik siliniyor
5. ✅ RAM kullanımı %80'in altında (12 kullanıcıda)
6. ✅ Mevcut uygulamalarda yavaşlama yok
7. ✅ 3 gün boyunca crash yok

### İlk 3 Ay Hedefleri:

- 10-15 kullanıcı rahat çalışıyor
- Haftalık management 15-20 dakika
- Downtime <1%
- Kullanıcı şikayeti yok

---

## 🔄 6 Ay Sonra Değerlendirme

### Eğer Her Şey Yolundaysa:

- ✅ Devam et (mevcut setup)
- Belki aggressive config'e geç (15-20 kullanıcı)

### Eğer Kullanıcı 20+'a Çıkarsa:

- Sunucu RAM'ini artır (31GB → 64GB)
- Veya ayrı sunucu ekle (load balancer)

### Eğer Kullanıcı 50+'a Çıkarsa:

- Multi-instance setup (Kubernetes)
- AWS/cloud'a migrate et (otomatik ölçeklendirme)

---

## 📞 Sonraki Adım

**Hemen:** Kurulum başlasın mı?

**Evet ise:**
1. Teknik ekip `KURULUM_PLANI_MEVCUT_SUNUCU.md` dosyasını takip etsin
2. Önce altyapı kur (1 gün)
3. Kod değişikliği paralel başlasın (1 hafta)

**Hayır ise:**
6 ay daha Daytona ile devam, maliyeti tolere et.

---

## 🎯 Özet (Tek Cümle)

**Mevcut sunucu kaynak olarak yeterli, OpenSandbox'a geçerek ayda $480 tasarruf edeceğiz, kurulum 2 hafta sürer, 12-15 kullanıcıya hizmet verebilir.**
