# OpenSandbox Kurulum ve Geçiş Rehberi

**Tarih:** 1 Nisan 2026  
**Amaç:** Daytona Cloud'dan OpenSandbox'a (self-hosted) geçiş planı.

---

## 🎯 Hızlı Özet (Executive Summary)

| Konu | Durum |
|------|-------|
| **Geçiş nedeni** | Maliyet optimizasyonu (Daytona $630/ay → OpenSandbox $270/ay) |
| **Geçiş süresi** | ~1 hafta (kod değişikliği) + 1 gün (kurulum) |
| **Kod değişikliği** | ~400 satır (manager.py, prompts.py, skill dosyaları) |
| **Mevcut sunucuya kurulabilir mi?** | ✅ Evet (8+ vCPU, 32GB+ RAM gerekli) |
| **Yeni sunucu gerekli mi?** | ⚠️ Opsiyonel (kaynaklar yeterliyse aynı sunucuya kurulabilir) |
| **Management effort** | Haftalık 15-20 dk (monitoring + cleanup) |
| **Risk seviyesi** | Orta (test ortamında doğrulama önerilir) |
| **Geri dönüş planı** | Mevcut Daytona kodu korunur (rollback 1 gün) |

### Maliyet Karşılaştırması (10 Kullanıcı)

| | Daytona (Şu An) | OpenSandbox (Mevcut Sunucu - SEÇILDI ✅) |
|---|---|---|
| Sandbox | $480/ay | **$0** |
| Sunucu | - | **$0** (mevcut external-compute) |
| Claude API | $150/ay | $150/ay |
| **TOPLAM** | **$630/ay** | **$150/ay** |
| **Tasarruf** | - | **$480/ay (%76 düşüş)** |

### Kritik Karar Noktaları

1. **Sunucu durumu: ✅ KARAR VERİLDİ**
   - Mevcut sunucu (external-compute) kullanılacak
   - Kaynaklar: 16 vCPU, 31GB RAM, 975GB disk
   - Kapasite: 12-15 eşzamanlı kullanıcı
   - **Tasarruf: $480/ay**

2. **Kurulum stratejisi:**
   - Aynı sunucuya kurulum (Docker izolasyonu ile)
   - Kaynak limitleri: 12 sandbox max, 2GB RAM/sandbox
   - Monitoring zorunlu (otomatik scriptler)
   - Haftalık cleanup (otomatik)

3. **Beklenen kullanıcı sayısı:**
   - Hedef: 10-15 kullanıcı
   - Mevcut kaynaklar yeterli
   - 20+ kullanıcıya çıkarsa → Değerlendirme gerekir

**Sonraki adım:** KURULUM_PLANI_MEVCUT_SUNUCU.md dosyasındaki adımları takip edin.

---

## Ne Yapıyoruz?

Şu an kullanıcı dosyalarını analiz eden Python kodları **Daytona Cloud** sunucularında çalışıyor. Bunu kendi sunucumuza taşıyoruz.

| | Eski (Daytona Cloud) | Yeni (OpenSandbox) |
|---|---|---|
| Kod nerede çalışıyor? | Daytona'nın sunucusu | **Bizim sunucumuz** |
| Sandbox maliyeti | $0.067/saat per kullanıcı | **$0** (açık kaynak) |
| Veri nerede? | Daytona datacenter | **Bizim sunucumuzda** |
| Lisans | AGPL-3.0 | **Apache-2.0** (kısıtlama yok) |
| Pickle gerekli mi? | Evet (her execute bağımsız) | **Hayır** (CodeInterpreter kernel) |

---

## Sunucuya Ne Kurulacak?

Tek sunucuda 3 bileşen çalışacak:

```
Sunucu (8 vCPU, 32GB RAM, 100GB SSD, Ubuntu 22.04)
│
├── Docker Engine         → Sandbox container'larını çalıştırır
├── OpenSandbox Server    → Sandbox lifecycle yönetimi (port 8080)
└── Streamlit App         → Kullanıcı arayüzü + AI Agent (port 8501)
```

---

## Port Çakışması Kontrolü

**Mevcut sunucuya kuruluyorsa önce kontrol edin:**

```bash
# Kullanılan portları listeleyin
sudo netstat -tulpn | grep LISTEN
# veya
sudo ss -tulpn | grep LISTEN

# OpenSandbox default portları:
# - 8080 (OpenSandbox Server)
# - 8501 (Streamlit App)
```

**Eğer çakışma varsa farklı portlar kullanın:**

```bash
# OpenSandbox farklı portta başlatma
opensandbox-server --port 8090

# Streamlit farklı portta başlatma
streamlit run app.py --server.port 8502

# .env dosyasını güncelle
OPEN_SANDBOX_DOMAIN="localhost:8090"
```

---

## Kurulum Adımları

### 1. Docker Kur

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

### 2. Custom Sandbox Image Build Et

Tüm Python paketlerimiz bu image'da önceden kurulu olacak:

```dockerfile
# Dockerfile.analysis
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core libpango1.0-0 libcairo2 \
    libgdk-pixbuf2.0-0 libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    pandas openpyxl xlsxwriter numpy \
    matplotlib seaborn plotly scipy scikit-learn \
    weasyprint pdfplumber duckdb fpdf2

WORKDIR /home/sandbox
```

```bash
docker build -t agentic-sandbox:v1 -f Dockerfile.analysis .
```

### 3. OpenSandbox Server Kur

```bash
pip install opensandbox-server
opensandbox-server init-config ~/.sandbox.toml --example docker
```

Config ayarları (`~/.sandbox.toml`):

```toml
[runtime]
type = "docker"

[runtime.docker]
default_image = "agentic-sandbox:v1"
default_cpu = "2"              # Her sandbox max 2 vCPU
default_memory = "4Gi"         # Her sandbox max 4GB RAM (tek sunucuysa 2Gi yapın)
default_timeout = "1h"         # 1 saat inaktivitede otomatik sil
max_sandboxes = 12             # Maksimum eşzamanlı sandbox sayısı (opsiyonel)
```

**MEVCUT SUNUCU İÇİN ÖNERİLEN (external-compute: 16 vCPU, 31GB RAM):**

```toml
[runtime.docker]
default_image = "agentic-sandbox:v1"
default_cpu = "1"              # Her sandbox max 1 vCPU (16 sandbox kapasitesi)
default_memory = "2Gi"         # Her sandbox max 2GB RAM
default_timeout = "1h"         # 1 saat inaktivitede otomatik sil
max_sandboxes = 12             # Toplam 24GB RAM kullanımı (12 × 2GB)
                               # Kalan 7GB → sistem + mevcut uygulamalar (4.5GB)
```

Bu ayarlar **12-15 eşzamanlı kullanıcı** için yeterli ve güvenli.

```bash
opensandbox-server   # → http://localhost:8080
```

### 4. Projeyi Deploy Et

```bash
git clone <repo-url> ~/agentic_analyze_d
cd ~/agentic_analyze_d
pip install -r requirements.txt
pip install opensandbox opensandbox-code-interpreter

export ANTHROPIC_API_KEY="sk-ant-..."
export OPEN_SANDBOX_API_KEY="local-key"
export OPEN_SANDBOX_DOMAIN="localhost:8080"

streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

### 5. Systemd ile Otomatik Başlatma

Sunucu restart olduğunda servisler otomatik ayağa kalkar:

```ini
# /etc/systemd/system/opensandbox.service
[Unit]
Description=OpenSandbox Server
After=docker.service
[Service]
ExecStart=/usr/local/bin/opensandbox-server
Restart=always
User=deploy
[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/streamlit.service
[Unit]
Description=Agentic Analyze
After=opensandbox.service
[Service]
WorkingDirectory=/home/deploy/agentic_analyze_d
ExecStart=/usr/local/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0
Restart=always
User=deploy
[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable opensandbox streamlit
sudo systemctl start opensandbox streamlit
```

---

## Kullanıcı Akışı

```
Kullanıcı → tarayıcıda sunucu:8501 açar
  → Excel yükler
  → "Analiz et" der
  → Agent (Claude) düşünür, execute çağrısı yapar
  → OpenSandbox Server → Docker container başlatır
  → Container'da CodeInterpreter kernel çalışır
  → Excel okunur, analiz yapılır, PDF üretilir
  → Sonuç kullanıcıya döner
  → 1 saat inaktivite → container otomatik silinir
```

---

## Sandbox Timeout ve İnaktivite

Sandbox **sürekli çalışmaz**. Kullanıcı aktifken açılır, işi bitince kapanır.

### Sürekli Çalışan ve Geçici Bileşenler

| Bileşen | Sürekli mi? | RAM |
|---|---|---|
| Docker Engine | Evet — her zaman çalışır | ~100MB |
| OpenSandbox Server | Evet — istekleri bekler | ~50MB |
| Streamlit App | Evet — UI sunar | ~200MB |
| **Sandbox container** | **Hayır** — sadece kullanıcı aktifken | ~2-4GB per kullanıcı |

### Sandbox Silinince Ne Olur?

| | Sandbox aktifken | Sandbox silindikten sonra |
|---|---|---|
| Bellekteki değişkenler (df, result vs.) | Var | Silinir |
| Container içindeki dosyalar (*.pkl, *.pdf) | Var | Silinir |
| Kullanıcının yüklediği orijinal dosya | Streamlit session'da | **Kalır** |
| Agent ürettiği sonuç (PDF, HTML, grafik) | ArtifactStore'da | **Kalır** |
| Chat geçmişi | MemorySaver'da | **Kalır** |

Sonuçlar sandbox silinmeden önce `download_file` tool ile dışarı çekilir. Kullanıcı PDF'i zaten almış olur.

### Timeout Ayarı

Config'de:
```toml
default_timeout = "1h"   # 1 saat inaktivitede sandbox silinir
```

Kod içinde:
```python
# Timeout ile
sandbox = SandboxSync.create("agentic-sandbox:v1", timeout=timedelta(hours=2))

# Timeout'suz (manuel kill gerekir)
sandbox = SandboxSync.create("agentic-sandbox:v1")

# Süre uzatma
sandbox.renew(timedelta(minutes=30))
```

### Ne Zaman Timeout Gerekir?

| Durum | Timeout | Neden |
|---|---|---|
| 5+ kullanıcı aynı sunucuyu paylaşıyor | Gerekir (1-2 saat) | RAM'i geri kazanmak için |
| 1-2 kişi kullanıyor, sunucu güçlü | Gerekmez | RAM yeterli, sandbox açık kalsın |
| Demo/test ortamı | Gerekmez | Tek kullanıcı |

Timeout bir güvenlik ağıdır — tarayıcı kapatan ama `kill()` tetiklenmeyen durumlar için orphan sandbox'ları temizler.

---

## Kaynak Monitoring ve Cleanup

**ÖNEMLI:** Mevcut sunucuya kuruluyorsa monitoring zorunludur!

### 1. Kaynak İzleme Scripti

```bash
# /root/monitor_agentic_resources.sh oluştur
cat > /root/monitor_agentic_resources.sh <<'EOF'
#!/bin/bash

LOG_TAG="agentic-monitor"

# RAM kullanımı %85 üstü mü?
RAM_USAGE=$(free | grep Mem | awk '{print ($3/$2) * 100.0}')
if (( $(echo "$RAM_USAGE > 85" | bc -l) )); then
  echo "ALERT: RAM kullanımı %$RAM_USAGE" | systemd-cat -t $LOG_TAG -p err
  
  # En eski 2 sandbox'ı durdur (acil durum)
  docker ps --filter "label=opensandbox" --format "{{.CreatedAt}}\t{{.ID}}" | \
    sort | head -n 2 | awk '{print $NF}' | xargs -r docker stop
  
  echo "2 sandbox durduruldu (RAM %$RAM_USAGE)" | systemd-cat -t $LOG_TAG -p warning
fi

# CPU load average (16 vCPU için %80 = 12.8 load)
CPU_CORES=$(nproc)  # 16
CPU_THRESHOLD=$(echo "$CPU_CORES * 0.8" | bc)  # 12.8
CPU_LOAD=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | tr -d ',')

if (( $(echo "$CPU_LOAD > $CPU_THRESHOLD" | bc -l) )); then
  echo "WARNING: CPU load $CPU_LOAD (threshold: $CPU_THRESHOLD)" | systemd-cat -t $LOG_TAG -p warning
fi

# Disk kullanımı %90 üstü mü?
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 90 ]; then
  echo "ALERT: Disk kullanımı %$DISK_USAGE" | systemd-cat -t $LOG_TAG -p err
  
  # Docker cleanup çalıştır
  docker system prune -f --volumes
  echo "Docker cleanup yapıldı (disk %$DISK_USAGE)" | systemd-cat -t $LOG_TAG -p warning
fi

# Aktif sandbox sayısı
ACTIVE_SANDBOXES=$(docker ps --filter "label=opensandbox" --quiet | wc -l)
echo "Durum: RAM %$RAM_USAGE | CPU $CPU_LOAD | Disk %$DISK_USAGE% | Sandboxes: $ACTIVE_SANDBOXES" | \
  systemd-cat -t $LOG_TAG -p info
EOF

chmod +x /root/monitor_agentic_resources.sh
```

**Crontab'a ekle (her 5 dakikada çalışır):**

```bash
crontab -e

# Ekle:
*/5 * * * * /root/monitor_agentic_resources.sh
```

**Logları izleme:**

```bash
# Gerçek zamanlı izleme
journalctl -t agentic-monitor -f

# Son 24 saat
journalctl -t agentic-monitor --since "24 hours ago"

# Sadece hataları göster
journalctl -t agentic-monitor -p err --since "7 days ago"
```

### 2. Haftalık Cleanup Scripti

```bash
# /root/cleanup_agentic.sh oluştur
cat > /root/cleanup_agentic.sh <<'EOF'
#!/bin/bash

echo "Agentic cleanup başladı: $(date)" | systemd-cat -t agentic-cleanup

# Docker cleanup (unused containers, images, volumes)
docker system prune -a -f --volumes

# Eski sandbox dosyalarını sil (7 günden eski)
find /tmp -name "sandbox-*" -mtime +7 -delete 2>/dev/null
find /home/daytona -name "*.pkl" -mtime +7 -delete 2>/dev/null
find /home/daytona -name "*.csv" -mtime +7 -delete 2>/dev/null

# OpenSandbox log rotation (30 günden eski)
find /var/log -name "*opensandbox*" -mtime +30 -delete 2>/dev/null

DISK_FREED=$(df -h / | tail -1 | awk '{print $4}')
echo "Cleanup tamamlandı. Boş disk: $DISK_FREED" | systemd-cat -t agentic-cleanup
EOF

chmod +x /root/cleanup_agentic.sh
```

**Crontab'a ekle (her Pazar 03:00):**

```bash
crontab -e

# Ekle:
0 3 * * 0 /root/cleanup_agentic.sh
```

### 3. Manuel Müdahale Komutları

**Acil durum (çok yüksek kaynak kullanımı):**

```bash
# TÜM sandbox'ları durdur
docker ps --filter "label=opensandbox" -q | xargs docker stop

# Servisleri yeniden başlat
sudo systemctl restart opensandbox
sudo systemctl restart streamlit

# Agresif cleanup
docker system prune -a -f --volumes
```

**Durum kontrolü:**

```bash
# Aktif sandbox'ları listele
docker ps --filter "label=opensandbox" --format "table {{.ID}}\t{{.CreatedAt}}\t{{.Status}}\t{{.Names}}"

# Kaynak kullanımı
docker stats --no-stream --filter "label=opensandbox"

# Sunucu kaynakları
htop  # veya top
```

---

## Kodda Ne Değişecek?

| Dosya | Değişiklik | Efor |
|---|---|---|
| `src/sandbox/manager.py` | Tamamen yeniden yazılır (Daytona → OpenSandbox SDK) | ~350 satır |
| `src/tools/download_file.py` | `sandbox.files.read_file()` kullanılır | ~20 satır |
| `src/agent/prompts.py` | Pickle talimatları kaldırılır | ~15 satır |
| `src/skills/*.md` | Pickle referansları güncellenir | ~10 satır |
| `requirements.txt` | `daytona` çıkar, `opensandbox` eklenir | 2 satır |

**Değişmeyen dosyalar:** `graph.py`, `app.py`, `file_parser.py`, `execute.py` interface'i, `generate_html.py`, skill sistemi.

**Toplam değişiklik:** ~400 satır | **Süre:** ~1 hafta (1 developer)

---

## Pickle Neden Kalkıyor?

**Eski (Daytona):** Her `execute()` ayrı subprocess → değişkenler ölür → pickle ile diske yazıp oku.

**Yeni (OpenSandbox CodeInterpreter):** Canlı Python kernel → değişkenler bellekte kalır → pickle gereksiz.

```
Eski: execute("df = read_excel(...)") → execute("pickle.load(...)") → execute("pickle.load(...)")
Yeni: execute("df = read_excel(...)") → execute("df.describe()")    → execute("pdf oluştur")
```

Fayda: Daha az execute çağrısı, daha az hata, daha hızlı analiz.

---

## Mevcut Sunucu Özellikleri (external-compute)

| Özellik | Değer | Durum |
|---------|-------|-------|
| **CPU** | 16 vCPU (Intel Xeon Icelake) | ✅ 10-25 kullanıcı için ideal |
| **RAM** | 31GB (26GB available) | ✅ 12-15 sandbox için yeterli |
| **Disk** | 975GB boş | ✅ Fazlasıyla yeterli |
| **OS** | Ubuntu | ✅ Docker desteği mükemmel |
| **Mevcut kullanım** | 4.5GB RAM, düşük CPU | ✅ Bol boş kaynak |

**Sonuç:** Bu sunucu 12-15 eşzamanlı kullanıcıya rahatlıkla hizmet verebilir. Yeni sunucu kiralamaya gerek yok.

**Referans (Gelecek İçin):**
- 25-50 kullanıcı → 16 vCPU, 64GB RAM gerekir (sunucu upgrade)
- 50+ kullanıcı → Multi-instance setup (load balancer + ikinci sunucu)

---

## ✅ KARAR: Mevcut Sunucuya Kurulacak

### Mevcut Sunucu Kaynakları (external-compute)

| Kaynak | Değer | Durum |
|--------|-------|-------|
| **CPU** | 16 vCPU (Intel Xeon Icelake) | ✅ Mükemmel |
| **RAM** | 31GB total, 26GB available | ✅ Mükemmel |
| **Disk** | 975GB boş (993GB total) | ✅ Fazlasıyla yeterli |
| **OS** | Ubuntu | ✅ İdeal |
| **Mevcut kullanım** | 4.5GB RAM | ✅ Düşük, bol boş alan |

### Kapasite Hesabı (Mevcut Sunucu)

```
Toplam RAM:                    31GB
- Mevcut uygulamalar:          4.5GB
- Sistem rezervi:              2GB
- Docker + OpenSandbox:        0.5GB
────────────────────────────────────
OpenSandbox için kalan:        24GB

Her sandbox:                   2GB RAM + 1 vCPU
Maksimum eşzamanlı sandbox:    12 sandbox (24GB ÷ 2GB)
Kullanıcı kapasitesi:          12-15 eşzamanlı kullanıcı
```

**CPU bottleneck yok:** 16 vCPU → her sandbox 1 vCPU = 16 sandbox rahat çalışır

**Sonuç:** ✅ Aynı sunucuya kurulabilir. Ayrı sunucu kiralamaya gerek yok.

### Maliyet Etkisi

| Senaryo | Maliyet |
|---------|---------|
| Daytona Cloud (şu an) | $630/ay |
| OpenSandbox (mevcut sunucu) | $150/ay (sadece Claude API) |
| **Tasarruf** | **$480/ay** |

### Aynı Sunucuya Kurmanın Artıları/Eksileri

| | Bu Sunucu | Ayrı Sunucu |
|---|---|---|
| **Maliyet** | ✅ $0 (mevcut sunucu) | ❌ +$120-150/ay |
| **Kaynaklar** | ✅ Fazlasıyla yeterli (16 vCPU, 31GB) | Gereksiz |
| **İzolasyon** | ⚠️ Kaynak paylaşımı (düşük risk) | ✅ Tam izole |
| **Yönetim** | ⚠️ Monitoring gerekli | ✅ Bağımsız |
| **Ölçeklendirme** | ⚠️ 15 kullanıcı max | ✅ Bağımsız büyüyebilir |

**Karar:** Mevcut sunucu ideal. Kaynak limitleri ve monitoring kurulacak.


### Gelecekte Ölçeklendirme (20+ Kullanıcı Olursa)

Eğer 6-12 ay içinde kullanıcı sayısı 20+'a çıkarsa, seçenekler:

| Seçenek | Ne Zaman | Maliyet | Süre |
|---------|----------|---------|------|
| **Mevcut sunucuyu büyüt** | Kaynaklar yetersiz kalırsa | Sunucu bağımlı | 1-2 gün (downtime) |
| **Ayrı sunucu ekle (load balancer)** | 25+ kullanıcı | +$120-150/ay | 2-3 gün |
| **AWS/cloud'a migrate** | 50+ kullanıcı, otomatik ölçeklendirme gerekirse | $400-600/ay | 1 hafta |

**Şimdilik:** Mevcut sunucu yeterli. 6 ay sonra yeniden değerlendirin.

### Mevcut Sunucu Kapasitesi (external-compute)

| Kaynak Profili | Eşzamanlı Kullanıcı | Not |
|----------------|---------------------|-----|
| **Konservatif (önerilen)** | 12-15 kullanıcı | 2GB RAM/sandbox, güvenli |
| **Agresif** | 15-20 kullanıcı | 1.5GB RAM/sandbox, sıkı izleme gerekir |
| **Maksimum teorik** | 24 kullanıcı | 1GB RAM/sandbox, önerilmez |

**Gerçek kullanım:** Tüm kullanıcılar aynı anda execute çalıştırmaz. Bir kısmı sonuçlara bakar, bir kısmı chat yazar. Konservatif başlayın (12 sandbox max), ihtiyaç görürseniz artırın.

**İlk 3 ay:** Monitoring ile gerçek kullanımı ölçün, sonra optimize edin.

---

## Karar Özeti (Teknik Ekip İçin)

### Karar Durumu: ✅ KESİNLEŞTİ

```
Mevcut Sunucu: external-compute
  │
  ├─ Kaynaklar: 16 vCPU, 31GB RAM, 975GB disk ✅
  ├─ Mevcut kullanım: 4.5GB RAM (düşük) ✅
  ├─ Kritik uygulamalar: Yok ✅
  │
  └─ KARAR: ✅ Aynı sunucuya kurulacak
      │
      ├─ Maliyet: $0 (sunucu), $150/ay (Claude API)
      ├─ Tasarruf: $480/ay (Daytona'dan)
      ├─ Kapasite: 12-15 eşzamanlı kullanıcı
      ├─ Kurulum: 1 gün (altyapı) + 1 hafta (kod)
      └─ Management: Haftalık 15-20 dk

Sonraki Adım → KURULUM_PLANI_MEVCUT_SUNUCU.md
```

### Seçilen Kurulum Stratejisi

| Kriter | Değer |
|--------|-------|
| **Sunucu** | Mevcut (external-compute) |
| **Hedef kullanıcı** | 10-15 eşzamanlı |
| **Kaynaklar** | 16 vCPU, 31GB RAM (yeterli) |
| **Maliyet** | $0 (sunucu), $150/ay (Claude API) |
| **Tasarruf** | $480/ay (Daytona'dan) |
| **Kurulum süresi** | ~1 gün (altyapı) + 1 hafta (kod) |
| **Risk** | Düşük (Docker izolasyonu, monitoring) |
| **Management** | Haftalık 15-20 dk (otomatik scriptler) |

### Checklist (Kurulum Öncesi)

**Mevcut sunucu (external-compute) için:**

- [x] Kaynaklar yeterli (16 vCPU, 31GB RAM) ✅
- [ ] Root/sudo erişimi test edildi
- [x] Ubuntu işletim sistemi ✅
- [ ] Docker kurulu mu kontrol edildi
- [ ] Port 8080 ve 8501 boş mu kontrol edildi
- [x] Kritik production uygulamaları yok ✅
- [ ] Monitoring kurulumu onaylandı (haftalık 15 dk)
- [ ] Backup stratejisi onaylandı
- [ ] Teknik ekip kurulum dökümanını inceledi

### İlk Adım (Kuruluma Başlama)

Detaylı adım adım kurulum için: **KURULUM_PLANI_MEVCUT_SUNUCU.md** dosyasına bakın.

**Hızlı başlangıç:**

```bash
# SSH ile bağlan
ssh ubuntu@external-compute

# Port kontrolü (8080 ve 8501 boş mu?)
sudo netstat -tulpn | grep -E ":(8080|8501)"

# Docker var mı?
docker --version
# Yoksa: curl -fsSL https://get.docker.com | sh

# Kurulum dökümanını takip et
# → KURULUM_PLANI_MEVCUT_SUNUCU.md
```

---

## Geçiş Takvimi

| İş |
|---|
| Sunucu hazırla, Docker kur, custom image build et, OpenSandbox test et |
| `manager.py` yeniden yaz (OpenSandbox SDK ile) |
| Prompt'lardan pickle talimatlarını kaldır, skill dosyalarını güncelle |
| Entegrasyon testi — dosya yükle, analiz yap, PDF indir |
| Edge case'ler, hata yönetimi, TTL testi, production deploy |

---

## Kaynaklar

- OpenSandbox GitHub: https://github.com/alibaba/OpenSandbox
- Python SDK: https://github.com/alibaba/OpenSandbox/tree/main/sdks/sandbox/python
- Code Interpreter SDK: https://github.com/alibaba/OpenSandbox/tree/main/sdks/code-interpreter/python
- LangGraph entegrasyon örneği: https://github.com/alibaba/OpenSandbox/tree/main/examples/langgraph
- Lisans: Apache-2.0
