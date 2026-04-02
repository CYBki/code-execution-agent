# OpenSandbox Management Rehberi

**Hızlı referans:** Günlük işler ve ölçeklendirme

---

## ⚠️ Daytona'nın Mevcut Sorunları (Neden Geçiş Düşünüyoruz?)

### Yaşanan Gerçek Bug'lar

| Sorun | Ne Oluyor? | Kullanıcı Etkisi | Root Cause |
|-------|-----------|-------------------|------------|
| **openpyxl kaybolması** | "Yeni Konuşma" sonrası paket bulunamıyor | Kullanıcı 3 dk bekliyor + manuel reset | Daytona sandbox restart'ta paketleri kaybediyor |
| **"File not found" hatası** | Dosya yüklendi ama agent bulamıyor | "Dosyanızı tekrar yükleyin" hatası | Agent thread'inde Daytona API erişim sorunu |
| **180s timeout** | Paket kurulumu başarısız olunca sessizce bekliyor | Kullanıcı 3 dakika boş yere bekliyor | Hata durumunda fail-fast mekanizması yoktu |
| **State kaybolması** | `df` değişkeni ikinci execute'da kayboluyor | Agent her seferinde dosyayı tekrar okuyor | Daytona her execute'u ayrı process'te çalıştırıyor |

### State Kaybolması — En Büyük Yapısal Sorun

Daytona'da her `execute()` çağrısı **ayrı bir process** başlatır:

```
# Daytona davranışı (şu anki):
Execute 1: df = pd.read_excel("dosya.xlsx")     → df var ✅
Execute 2: print(df.describe())                   → NameError: df is not defined ❌
bunu pickle ile çözuyoruz ama kernel cok daha iyi bir cozum
                                                    (yeni process, df kayboldu!)

# Agent'ın workaround'u:
Execute 2: df = pd.read_excel("dosya.xlsx")       → dosyayı TEKRAR okuyor (gereksiz) 

           print(df.describe())                    → çalışıyor ama yavaş 
```

**OpenSandbox CodeInterpreter'da bu sorun yok:**

```
# OpenSandbox davranışı (geçiş sonrası):
Execute 1: df = pd.read_excel("dosya.xlsx")     → df var ✅
Execute 2: print(df.describe())                   → df hala var ✅ (aynı kernel!)
```

Bu fark şu anlama geliyor:
- **Daha az API çağrısı** → Claude maliyeti düşer
- **Daha hızlı analiz** → dosya tekrar tekrar okunmaz
- **Daha az hata** → pickle/state kaybı sorunu kalmaz

### Daytona Resmi Production Uyarısı

Daytona'nın kendi OSS Deployment dokümanı:

> **"This setup is still in development and is not safe to use in production"**
> — https://www.daytona.io/docs/en/oss-deployment/

Self-hosted Daytona production'da kullanılamaz. Production istiyorsan → Cloud'a para öde veya enterprise lisans al.

### Lisans Kısıtlaması

| | Daytona | OpenSandbox |
|---|---|---|
| **Lisans** | AGPL-3.0 | Apache-2.0 |
| **Kodu değiştirirsen** | Açık kaynak paylaşmak **zorundasın** | Zorunluluk **yok** |
| **Ticari kullanım** | Kısıtlı | Tamamen serbest |

---

## 🔄 Cloud vs Self-Host Karşılaştırması

| | Daytona Cloud (Şu An) | OpenSandbox Self-Host (Geçiş) |
|---|---|---|
| **Haftalık yönetim işi** | 0 dk | 15-20 dk |
| **Maliyet** | ~$630/ay | ~$150/ay (sadece Claude API) |
| **openpyxl sorunu** | ❌ Yaşıyoruz | ✅ CodeInterpreter ile kalkıyor |
| **State kaybolması** | ❌ Her execute'da kaybolur | ✅ Kernel state korunur |
| **Pickle gerekli mi?** | ❌ Evet | ✅ Hayır |
| **Ölçekleme** | Otomatik (para öde) | Manuel (bu doküman) |
| **Risk** | Düşük (managed) | Orta (4 aylık proje) |
| **Geri dönüş** | — | 5 dk (env variable değiştir) |

**Tasarruf:** $480/ay = $5,760/yıl

---

## 🔧 Kod Değişikliği Etkisi (Sandbox Değiştirilirse)

| Dosya | Ne Değişir? | Satır | Zorluk |
|-------|------------|-------|--------|
| `src/sandbox/manager.py` | Daytona SDK → OpenSandbox SDK (tamamen yeniden yazılır) | ~350 | Yüksek |
| `src/tools/execute.py` | Subprocess → CodeInterpreter kernel | ~50 | Orta |
| `src/tools/download_file.py` | Dosya indirme API değişikliği | ~20 | Düşük |
| `src/tools/visualization.py` | Grafik oluşturma API değişikliği | ~20 | Düşük |
| Prompt dosyaları | Pickle instruction kaldırılır | ~30 | Düşük |
| **TOPLAM** | | **~470 satır** | |

**Not:** Geri dönüş çok kolay — `manager.py`'de import'u değiştir + env variable güncelle = 5 dakika.

---

## 🛡️ Geri Dönüş Planı (OpenSandbox Sorun Çıkarırsa)

```
OpenSandbox sorun çıkardı!
  │
  ├─ Küçük sorun (bug, timeout) → GitHub issue aç, workaround uygula
  │
  └─ Büyük sorun (çalışmıyor, veri kaybı)
      │
      ├─ .env dosyasını değiştir:
      │    SANDBOX_PROVIDER=daytona        # ← tek satır
      │    DAYTONA_API_KEY=xxx
      │
      ├─ Streamlit restart:
      │    sudo systemctl restart agentic-streamlit
      │
      └─ Daytona Cloud'a geri döndü ✅ (5 dakika)
```

**Koşul:** Manager.py'de her iki backend'i de destekleyen bir abstraction layer yazılır (1 günlük ek iş).

---

## 💡 OpenSandbox Nasıl Çalışır?

### Sürekli Çalışan Servisler

```
┌─────────────────────────────────────┐
│ Sunucu (Sürekli Açık)              │
│                                     │
│  ✅ Docker Engine (her zaman)      │
│  ✅ OpenSandbox Server (her zaman) │ ← Port 8080, API bekler
│  ✅ Streamlit App (her zaman)      │ ← Port 8501, kullanıcı UI
│                                     │
│  RAM: ~1GB (sabit)                 │
└─────────────────────────────────────┘
```

**Bu servisler reboot'tan sonra bile otomatik başlar** (systemd ile).

---

### Geçici Çalışan Sandbox'lar

```
Kullanıcı A: Excel yükledi → "Analiz et" dedi
  → OpenSandbox: Docker container başlat (sandbox-user-a)
  → RAM: +2GB
  → Execute komutları çalıştır
  → Kullanıcı 1 saat pasif → Otomatik sil
  → RAM: -2GB (geri kazanıldı)

Kullanıcı B: Aynı anda başka dosya analiz ediyor
  → Başka bir container (sandbox-user-b)
  → RAM: +2GB (toplam 4GB sandbox)
```

**Sandbox'lar geçici:** Kullanıcı aktifken açık, pasifse (1 saat) otomatik kapanır.

---

### RAM Kullanımı Örneği

| Durum | RAM Kullanımı |
|-------|---------------|
| **Gece 03:00 (hiç kullanıcı yok)** | ~5.5GB (sistem + mevcut uygulamalar + servisler) |
| **Sabah 10:00 (5 kullanıcı aktif)** | ~15.5GB (5.5GB + 5×2GB sandbox) |
| **Öğlen 13:00 (12 kullanıcı aktif)** | ~29.5GB (5.5GB + 12×2GB sandbox) |
| **Akşam 19:00 (2 kullanıcı aktif)** | ~9.5GB (5.5GB + 2×2GB sandbox) |

**Sandbox'lar dinamik:** Kullanıcı sayısına göre açılır/kapanır, RAM esnek.

---

### Timeout Mekanizması

```bash
# Config: ~/.sandbox.toml
default_timeout = "1h"  # 1 saat inaktivite → otomatik sil

# Örnek akış:
10:00 → Kullanıcı execute çalıştırdı (sandbox açık)
10:15 → Kullanıcı PDF indirdi (sandbox hala açık)
10:20 → Kullanıcı tarayıcı kapattı (sandbox açık ama pasif)
11:20 → 1 saat geçti → Sandbox otomatik silindi ✅
```

**Neden timeout?** RAM'i boşa harcamamak için. Kullanıcı çıktı ama sandbox açık kaldıysa, 1 saat sonra sil.

---

### Maliyet Etkisi

**Daytona (Şu An):**
```
Sandbox'lar sürekli çalışıyor gibi faturalandırılıyor
→ 10 kullanıcı × 24 saat × 30 gün × $0.067/saat = $480/ay
```

**OpenSandbox (Self-Hosted):**
```
Sandbox'lar sadece aktifken RAM kullanır
→ RAM zaten var (mevcut sunucu)
→ Ek maliyet: $0
```

**Bu yüzden OpenSandbox ucuz.** 🎯

---

## 🔧 Haftalık Management (15-20 Dakika)

### Pazartesi Sabahı Kontrol

```bash
# SSH ile bağlan
ssh ubuntu@sunucu-ip

# Servisler çalışıyor mu? (2 dakika)
systemctl status opensandbox
systemctl status agentic-streamlit

# Kaynaklar nasıl? (3 dakika)
free -h                           # RAM kullanımı
df -h                             # Disk kullanımı
docker ps --filter "label=opensandbox" | wc -l  # Aktif sandbox sayısı

# Hata var mı? (10 dakika)
journalctl -t agentic-monitor --since "7 days ago" -p err
journalctl -u opensandbox --since "7 days ago" | grep -i error

# Her şey OK ise çık
exit
```

**Toplam:** 15 dakika

---

## ⚙️ Otomatik Çalışanlar (Elle Bir Şey Yapmayacaksınız)

### 1. Her 5 Dakika: Kaynak İzleme

```bash
# /usr/local/bin/monitor_agentic.sh (otomatik)
# → RAM %85+ → En eski 2 sandbox'ı durdur
# → CPU load yüksek → Uyarı logla
# → Disk %90+ → Docker cleanup
```

**Nerede izlenir:**
```bash
journalctl -t agentic-monitor -f  # Canlı izleme
```

---

### 2. Her Pazar 03:00: Cleanup

```bash
# /usr/local/bin/cleanup_agentic.sh (otomatik)
# → Unused Docker containers sil
# → Eski sandbox dosyaları sil (7 gün+)
# → Eski loglar sil (30 gün+)
```

---

### 3. Her Gün 02:00: Backup

```bash
# /usr/local/bin/backup_agentic.sh (otomatik)
# → Kod + config yedekle
# → Son 7 günü sakla
```

---

## 🚨 Acil Durum (Yılda 1-2 Kez)

### Senaryo 1: Sistem Yavaşladı

```bash
# 1. RAM kontrol (1 dakika)
free -h
# RAM %90+ ise:

# 2. Sandbox'ları durdur (1 dakika)
docker ps --filter "label=opensandbox" -q | head -n 5 | xargs docker stop

# 3. Servisleri restart (1 dakika)
sudo systemctl restart opensandbox
```

**Toplam:** 3 dakika

---

### Senaryo 2: Servis Çöktü

```bash
# 1. Durumu kontrol (30 saniye)
systemctl status opensandbox

# 2. Restart (30 saniye)
sudo systemctl restart opensandbox
sudo systemctl restart agentic-streamlit

# 3. Logları kontrol (2 dakika)
journalctl -u opensandbox -n 50
```

**Toplam:** 3 dakika

---

### Senaryo 3: Disk Doldu

```bash
# 1. Hemen cleanup (2 dakika)
docker system prune -a -f --volumes
find /tmp -name "sandbox-*" -mtime +1 -delete

# 2. Disk kontrol (30 saniye)
df -h

# 3. Yetmezse eski dosyaları sil (2 dakika)
find /var/log -name "*.log" -mtime +7 -delete
```

**Toplam:** 5 dakika

---

## 📈 Ölçeklendirme

### Senaryo 1: Kullanıcı 10 → 20 (RAM Yeterli)

**Adım:** Config ayarla (5 dakika)

```bash
ssh ubuntu@sunucu-ip

# Config düzenle
nano ~/.sandbox.toml
# Değiştir:
# max_sandboxes = 12  →  max_sandboxes = 18
# default_memory = "2Gi"  →  default_memory = "1.5Gi"

# Restart
sudo systemctl restart opensandbox

# Test
docker ps --filter "label=opensandbox"
```

**Downtime:** 10 saniye  
**Maliyet:** $0

---

### Senaryo 2: Kullanıcı 20 → 30 (RAM Yetersiz)

#### Yerli Sunucu:

**Adım 1:** Yeni sunucu kirala (1-2 gün)

```
1. 64GB RAM sunucu kirala
2. Backup'tan geri yükle:
   scp backup.tar.gz yeni-sunucu:~
   ssh yeni-sunucu
   tar -xzf backup.tar.gz
   # Servisleri başlat
3. DNS değiştir (sunucu IP'si)
4. Test et
5. Eski sunucuyu kapat
```

**Downtime:** 2-4 saat  
**Maliyet:** $150/ay → $240/ay

---

#### AWS:

**Adım 1:** Instance type değiştir (10 dakika)

```
AWS Console:
1. EC2 → Instances → Select instance
2. Instance State → Stop
3. Actions → Instance Settings → Change Instance Type
4. t3.2xlarge → m5.4xlarge (64GB RAM)
5. Instance State → Start
6. Test: http://<public-ip>:8501
```

**Downtime:** 5-10 dakika  
**Maliyet:** $180/ay → $490/ay (on-demand) veya $110/ay → $300/ay (reserved)

---

### Senaryo 3: Kullanıcı 30 → 50+ (Multi-Instance)

#### Yerli Sunucu:

**Adım 1:** İkinci sunucu + Load Balancer (2-3 gün)

```
1. İkinci sunucu kirala (aynı spec)
2. Her ikisine OpenSandbox kur
3. Nginx load balancer kur:
   upstream backend {
     server sunucu1:8501;
     server sunucu2:8501;
   }
4. Redis kur (shared session)
5. Test et
```

**Downtime:** 1-2 saat (load balancer kurulumu)  
**Maliyet:** $150/ay → $300-350/ay (2 sunucu)

---

#### AWS:

**Adım 1:** Application Load Balancer (1-2 gün)

```
AWS Console:
1. EC2 → AMI → Create image (mevcut instance'tan)
2. EC2 → Launch instance (AMI'dan)
3. Load Balancer → Create ALB
4. Target Group → 2 instance ekle
5. ElastiCache → Redis (shared session)
6. Test et
```

**Downtime:** 0 (zero downtime deployment)  
**Maliyet:** $180/ay → $440/ay (2 instance + ALB + Redis)

---

## 📊 Ölçeklendirme Karşılaştırması

| Kullanıcı | Yerli Sunucu | AWS | Süre | Downtime |
|-----------|--------------|-----|------|----------|
| **10 → 20** | Config değiştir | Config değiştir | 5 dk | 10 saniye |
| **20 → 30** | Yeni sunucu kirala | Instance type değiştir | 1-2 gün vs 10 dk | 2-4 saat vs 5-10 dk |
| **30 → 50** | İkinci sunucu + LB | ALB + AMI | 2-3 gün vs 1-2 gün | 1-2 saat vs 0 |

**Kritik fark:** AWS ölçeklendirmesi çok daha hızlı (özellikle 20-30 kullanıcı arası).

---

## ☸️ Kubernetes Ne Zaman Gerekir?

| | Docker (Tek Sunucu) | Kubernetes (Sunucu Kümesi) |
|---|---|---|
| **Kullanıcı sayısı** | 1-50 | 50+ |
| **Sunucu sayısı** | 1 | 2-10+ |
| **Ölçekleme** | Manuel (sen yaparsın) | Otomatik (yük artınca yeni sunucu ekler) |
| **Kurulum zorluğu** | Kolay (3 komut) | Zor (1-2 hafta) |
| **AWS karşılığı** | EC2 + Docker | EKS (managed Kubernetes) |
| **Bize şu an gerekli mi?** | ✅ **Evet, bu yeterli** | ❌ Şu an gereksiz |

**Özet:** EC2 + Docker ile başlıyoruz. 50+ kullanıcıya ulaşırsak AWS EKS'e geçiş düşünülür.

OpenSandbox her iki runtime'ı da destekliyor:
- `opensandbox-server` → Docker backend (şu an)
- `kubernetes/` dizini → Kubernetes backend (ileride)

---

## 🎯 Ne Zaman Ölçeklendirme Gerekir?

### Proaktif Sinyaller (Aksiyon Al)

```bash
# RAM kullanımı sürekli %75+ ise
free -h | grep Mem | awk '{print ($3/$2) * 100}'

# Sandbox queue uzuyorsa (5+ bekleyen sandbox)
journalctl -t agentic-monitor --since "1 day ago" | grep "max_sandboxes"

# Kullanıcı şikayeti ("yavaş çalışıyor")
# → Hemen kaynak kontrol yap
```

**Kural:** RAM %75+ → 1 hafta içinde ölçeklendir (reaktif değil, proaktif)

---

## 💾 Backup ve Kurtarma

### Manuel Backup (Gerekirse)

```bash
# Anlık backup al (5 dakika)
ssh ubuntu@sunucu-ip
sudo tar -czf /tmp/backup-$(date +%Y%m%d).tar.gz \
  ~/agentic_analyze_d \
  ~/.sandbox.toml \
  /etc/systemd/system/opensandbox.service \
  /etc/systemd/system/agentic-streamlit.service

# İndir
scp ubuntu@sunucu-ip:/tmp/backup-*.tar.gz ~/backups/
```

---

### Sunucu Çökerse Kurtarma

#### Yerli Sunucu:

```bash
# Yeni sunucu kirala (4-8 saat)
1. Ubuntu sunucu hazırla
2. Backup yükle: scp backup.tar.gz sunucu:~
3. Dosyaları geri çıkar: tar -xzf backup.tar.gz
4. Docker + OpenSandbox kur (KURULUM_PLANI_MEVCUT_SUNUCU.md)
5. Servisleri başlat
6. DNS güncelle (yeni IP)
```

**Süre:** 4-8 saat

---

#### AWS:

```bash
# Snapshot'tan kurtarma (10 dakika)
AWS Console:
1. EC2 → AMI → Son snapshot seç
2. Launch instance
3. Elastic IP → Yeni instance'a ata (DNS değişikliği yok)
4. Test: http://<elastic-ip>:8501
```

**Süre:** 10 dakika

---

## 📞 Monitoring Dashboard (Opsiyonel)

### Basit Dashboard (htop)

```bash
# SSH ile bağlan, canlı izle
ssh ubuntu@sunucu-ip
htop

# Veya uzaktan:
watch -n 5 "ssh ubuntu@sunucu-ip 'free -h && df -h'"
```

---

### CloudWatch Dashboard (Sadece AWS)

```
AWS Console → CloudWatch → Dashboards:
1. CPU Utilization (grafik)
2. Memory Usage (grafik)
3. Disk Usage (grafik)
4. Active Sandboxes (custom metric)

→ Tek ekranda her şeyi görürsünüz
```

---

## ✅ Checklist (Aylık)

```
□ Disk kullanımı %80'in altında mı?
□ RAM kullanımı %75'in altında mı?
□ Backup'lar düzenli alınıyor mu? (ls ~/backups/)
□ Monitoring scriptleri çalışıyor mu? (journalctl -t agentic-monitor)
□ Docker image güncel mi? (docker images | grep agentic-sandbox)
□ Sunucu paketleri güncel mi? (sudo apt update && sudo apt list --upgradable)
```

**Toplam:** 10 dakika/ay

---

## 🎯 Özet

### Management:
- **Haftalık:** 15-20 dk (SSH + log kontrol)
- **Otomatik:** RAM/CPU izleme, cleanup, backup
- **Acil durum:** 3-5 dk (restart/cleanup)

### Ölçeklendirme:
- **10 → 20 kullanıcı:** 5 dk (config değiştir)
- **20 → 30 kullanıcı:**
  - Yerli: 1-2 gün, 2-4 saat downtime
  - AWS: 10 dk, 5-10 dk downtime
- **30 → 50 kullanıcı:**
  - Yerli: 2-3 gün, 1-2 saat downtime
  - AWS: 1-2 gün, 0 downtime

### Kritik Fark:
- Management: Yerli ve AWS aynı (15-20 dk/hafta)
- Ölçeklendirme: AWS çok daha hızlı (özellikle 20+ kullanıcı)

---
## Kaynaklar

- OpenSandbox GitHub: https://github.com/alibaba/OpenSandbox
- Python SDK: https://github.com/alibaba/OpenSandbox/tree/main/sdks/sandbox/python
- Code Interpreter SDK: https://github.com/alibaba/OpenSandbox/tree/main/sdks/code-interpreter/python
- LangGraph entegrasyon örneği: https://github.com/alibaba/OpenSandbox/tree/main/examples/langgraph
- Lisans: Apache-2.0