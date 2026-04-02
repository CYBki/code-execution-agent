# OpenSandbox Kurulum Planı - Mevcut Sunucu

**Sunucu:** external-compute  
**Kaynaklar:** 16 vCPU, 31GB RAM, 975GB disk  
**OS:** Ubuntu  
**Tarih:** 1 Nisan 2026

---

## 🎯 Kapasite Özeti

| Kaynak | Değer | Durum |
|--------|-------|-------|
| CPU | 16 vCPU | ✅ Mükemmel (12+ sandbox) |
| RAM | 31GB (26GB available) | ✅ Mükemmel (12 sandbox × 2GB) |
| Disk | 975GB boş | ✅ Fazlasıyla yeterli |
| Mevcut kullanım | 4.5GB RAM | ✅ Düşük, bol boş alan |
| **Kapasite** | **12-15 eşzamanlı kullanıcı** | ✅ Hedef: 10-15 kullanıcı |

**Sonuç:** Bu sunucu OpenSandbox için ideal. Ayrı sunucu kiralamaya gerek yok.

**Maliyet tasarrufu:** $480/ay (Daytona sandbox maliyeti kalkacak, yeni sunucu kiralaması yok)

---

## 📅 Kurulum Adımları

### Faz 1: Hazırlık (1 saat)

#### 1.1. Port Kontrolü

```bash
# Kullanılan portları kontrol et
sudo netstat -tulpn | grep LISTEN | grep -E ":(8080|8501)"

# Çıktı boşsa → Portlar boş, devam edilebilir
# Çıktı varsa → Farklı portlar kullanılacak (8090, 8502 gibi)
```

#### 1.2. Docker Kontrolü

```bash
# Docker kurulu mu?
docker --version

# Kurulu değilse kur
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Test et
docker run hello-world
```

#### 1.3. Gerekli Dizinleri Oluştur

```bash
# Proje dizini
mkdir -p ~/agentic_analyze_d
cd ~/agentic_analyze_d

# Backup dizini
mkdir -p ~/backups/agentic

# Log dizini
sudo mkdir -p /var/log/agentic
sudo chown $USER:$USER /var/log/agentic
```

---

### Faz 2: Custom Sandbox Image (30 dakika)

#### 2.1. Dockerfile Oluştur

```bash
cd ~/agentic_analyze_d

cat > Dockerfile.analysis <<'EOF'
FROM python:3.11-slim

# Font ve sistem bağımlılıkları
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core libpango1.0-0 libcairo2 \
    libgdk-pixbuf2.0-0 libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Python paketleri (tüm analiz bağımlılıkları)
RUN pip install --no-cache-dir \
    pandas==2.2.0 \
    openpyxl==3.1.2 \
    xlsxwriter==3.2.0 \
    numpy==1.26.4 \
    matplotlib==3.8.3 \
    seaborn==0.13.2 \
    plotly==5.19.0 \
    scipy==1.12.0 \
    scikit-learn==1.4.1.post1 \
    weasyprint==61.2 \
    pdfplumber==0.11.0 \
    duckdb==0.10.0 \
    fpdf2==2.7.7 \
    pillow==10.2.0

# DejaVu fontları (WeasyPrint için)
RUN mkdir -p /usr/share/fonts/truetype/dejavu && \
    cp /usr/share/fonts/truetype/dejavu-sans/DejaVuSans.ttf /home/sandbox/ && \
    cp /usr/share/fonts/truetype/dejavu-sans/DejaVuSans-Bold.ttf /home/sandbox/

WORKDIR /home/sandbox
EOF
```

#### 2.2. Image Build Et

```bash
# Build (5-10 dakika sürer)
docker build -t agentic-sandbox:v1 -f Dockerfile.analysis .

# Verify
docker images | grep agentic-sandbox

# Test et
docker run --rm agentic-sandbox:v1 python -c "import pandas, weasyprint, duckdb; print('OK')"
```

---

### Faz 3: OpenSandbox Server (30 dakika)

#### 3.1. Kurulum

```bash
# Python ve pip güncel mi?
python3 --version  # 3.8+ olmalı
pip3 --version

# OpenSandbox server kur
pip3 install opensandbox-server

# Verify
opensandbox-server --version
```

#### 3.2. Config Oluştur

```bash
# Config dosyası oluştur
opensandbox-server init-config ~/.sandbox.toml --example docker

# Config düzenle
nano ~/.sandbox.toml
```

**~/.sandbox.toml içeriği:**

```toml
[runtime]
type = "docker"

[runtime.docker]
# Custom image
default_image = "agentic-sandbox:v1"

# Kaynak limitleri (KONSERVATIF - 31GB RAM için)
default_cpu = "1"              # Her sandbox max 1 vCPU
default_memory = "2Gi"         # Her sandbox max 2GB RAM
default_timeout = "1h"         # 1 saat inaktivitede otomatik sil

# Maksimum sandbox sayısı (ÖNEMLI!)
max_sandboxes = 12             # 12 × 2GB = 24GB max kullanım

# Network izolasyonu (opsiyonel, diğer uygulamalardan izole eder)
# network = "agentic-net"

[server]
host = "0.0.0.0"
port = 8080

[logging]
level = "info"
file = "/var/log/agentic/opensandbox.log"
```

#### 3.3. Test Et

```bash
# Arka planda başlat
opensandbox-server &

# 5 saniye bekle
sleep 5

# Health check
curl http://localhost:8080/health

# Beklenen çıktı: {"status":"ok"}

# Process'i durdur (systemd ile başlatacağız)
pkill opensandbox-server
```

---

### Faz 4: Streamlit App (1 saat)

#### 4.1. Kodu Al

```bash
cd ~/agentic_analyze_d

# Git'ten çek (veya scp/rsync ile transfer et)
git clone <repo-url> .

# Veya mevcut kodu güncelle
git pull origin main
```

#### 4.2. Kod Değişikliklerini Yap

**ÖNEMLİ:** `src/sandbox/manager.py` dosyasını Daytona'dan OpenSandbox'a çevirmeniz gerekiyor.

Bu konuda yardım gerekiyorsa ayrı bir task olarak yapabiliriz.

#### 4.3. Bağımlılıkları Kur

```bash
# Virtual environment (opsiyonel ama önerilir)
python3 -m venv .venv
source .venv/bin/activate

# Paketleri kur
pip install -r requirements.txt

# OpenSandbox SDK'ları ekle
pip install opensandbox opensandbox-code-interpreter
```

#### 4.4. .env Dosyası

```bash
cat > .env <<'EOF'
# Anthropic API
ANTHROPIC_API_KEY=sk-ant-...

# OpenSandbox (local)
OPEN_SANDBOX_API_KEY=local-key-12345
OPEN_SANDBOX_DOMAIN=localhost:8080

# Opsiyonel
LOG_LEVEL=INFO
EOF

# Güvenlik
chmod 600 .env
```

#### 4.5. Test Et

```bash
# Terminal'de başlat
streamlit run app.py --server.port 8501 --server.address 0.0.0.0

# Tarayıcıda aç: http://<sunucu-ip>:8501
# Test dosyası yükle, basit bir soru sor

# Ctrl+C ile durdur
```

---

### Faz 5: Systemd Servisleri (30 dakika)

#### 5.1. OpenSandbox Servisi

```bash
sudo tee /etc/systemd/system/opensandbox.service <<'EOF'
[Unit]
Description=OpenSandbox Server
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu
ExecStart=/home/ubuntu/.local/bin/opensandbox-server
Restart=always
RestartSec=10
StandardOutput=append:/var/log/agentic/opensandbox-stdout.log
StandardError=append:/var/log/agentic/opensandbox-stderr.log

# Kaynak limitleri (güvenlik)
LimitNOFILE=4096
LimitNPROC=512

[Install]
WantedBy=multi-user.target
EOF
```

#### 5.2. Streamlit Servisi

```bash
sudo tee /etc/systemd/system/agentic-streamlit.service <<'EOF'
[Unit]
Description=Agentic Analyze Streamlit App
After=opensandbox.service
Requires=opensandbox.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/agentic_analyze_d
Environment="PATH=/home/ubuntu/agentic_analyze_d/.venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/ubuntu/agentic_analyze_d/.venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=10
StandardOutput=append:/var/log/agentic/streamlit-stdout.log
StandardError=append:/var/log/agentic/streamlit-stderr.log

# Kaynak limitleri
LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
EOF
```

#### 5.3. Servisleri Etkinleştir

```bash
# Reload
sudo systemctl daemon-reload

# Enable (boot'ta otomatik başlat)
sudo systemctl enable opensandbox
sudo systemctl enable agentic-streamlit

# Start
sudo systemctl start opensandbox
sleep 5
sudo systemctl start agentic-streamlit

# Status kontrolü
sudo systemctl status opensandbox
sudo systemctl status agentic-streamlit

# Logları izle
journalctl -u opensandbox -f
journalctl -u agentic-streamlit -f
```

---

### Faz 6: Monitoring ve Cleanup Scriptleri (1 saat)

#### 6.1. Kaynak İzleme Scripti

```bash
sudo tee /usr/local/bin/monitor_agentic.sh <<'EOF'
#!/bin/bash

LOG_TAG="agentic-monitor"

# RAM kullanımı (eşik: %85)
RAM_USAGE=$(free | grep Mem | awk '{print ($3/$2) * 100.0}')
if (( $(echo "$RAM_USAGE > 85" | bc -l) )); then
  echo "ALERT: RAM kullanımı %$RAM_USAGE" | systemd-cat -t $LOG_TAG -p err
  
  # En eski 2 sandbox'ı durdur
  docker ps --filter "label=opensandbox" --format "{{.CreatedAt}}\t{{.ID}}" | \
    sort | head -n 2 | awk '{print $NF}' | xargs -r docker stop
  
  echo "2 sandbox durduruldu (RAM kurtarma)" | systemd-cat -t $LOG_TAG -p warning
fi

# CPU load (16 vCPU için %80 = 12.8 load average)
CPU_LOAD=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | tr -d ',')
if (( $(echo "$CPU_LOAD > 12.8" | bc -l) )); then
  echo "WARNING: CPU load $CPU_LOAD (threshold: 12.8)" | systemd-cat -t $LOG_TAG -p warning
fi

# Disk kullanımı (eşik: %90)
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 90 ]; then
  echo "ALERT: Disk kullanımı %$DISK_USAGE" | systemd-cat -t $LOG_TAG -p err
  docker system prune -f --volumes
fi

# Aktif sandbox sayısı
ACTIVE=$(docker ps --filter "label=opensandbox" --quiet | wc -l)
echo "RAM: $RAM_USAGE% | CPU: $CPU_LOAD | Disk: $DISK_USAGE% | Sandboxes: $ACTIVE" | \
  systemd-cat -t $LOG_TAG -p info
EOF

sudo chmod +x /usr/local/bin/monitor_agentic.sh
```

**Crontab ekle:**

```bash
crontab -e

# Ekle (her 5 dakikada):
*/5 * * * * /usr/local/bin/monitor_agentic.sh
```

#### 6.2. Haftalık Cleanup Scripti

```bash
sudo tee /usr/local/bin/cleanup_agentic.sh <<'EOF'
#!/bin/bash

echo "Cleanup başladı: $(date)" | systemd-cat -t agentic-cleanup

# Docker cleanup
docker system prune -a -f --volumes

# Eski sandbox dosyaları (7 gün+)
find /tmp -name "sandbox-*" -mtime +7 -delete 2>/dev/null
find /home/sandbox -name "*.pkl" -mtime +7 -delete 2>/dev/null
find /home/sandbox -name "*.csv" -mtime +7 -delete 2>/dev/null

# Eski loglar (30 gün+)
find /var/log/agentic -name "*.log" -mtime +30 -delete 2>/dev/null

DISK_FREE=$(df -h / | tail -1 | awk '{print $4}')
echo "Cleanup bitti. Boş disk: $DISK_FREE" | systemd-cat -t agentic-cleanup
EOF

sudo chmod +x /usr/local/bin/cleanup_agentic.sh
```

**Crontab ekle:**

```bash
crontab -e

# Ekle (her Pazar 03:00):
0 3 * * 0 /usr/local/bin/cleanup_agentic.sh
```

#### 6.3. Backup Scripti

```bash
sudo tee /usr/local/bin/backup_agentic.sh <<'EOF'
#!/bin/bash

BACKUP_DIR=~/backups/agentic
DATE=$(date +%Y%m%d)

mkdir -p $BACKUP_DIR

tar -czf $BACKUP_DIR/agentic-$DATE.tar.gz \
  ~/agentic_analyze_d \
  ~/.sandbox.toml \
  /etc/systemd/system/opensandbox.service \
  /etc/systemd/system/agentic-streamlit.service

# 7'den eski yedekleri sil
ls -t $BACKUP_DIR/agentic-*.tar.gz | tail -n +8 | xargs rm -f

echo "Backup: agentic-$DATE.tar.gz" | systemd-cat -t agentic-backup
EOF

sudo chmod +x /usr/local/bin/backup_agentic.sh
```

**Crontab ekle:**

```bash
crontab -e

# Ekle (her gün 02:00):
0 2 * * * /usr/local/bin/backup_agentic.sh
```

---

### Faz 7: Son Kontroller (30 dakika)

#### 7.1. Servis Durumu

```bash
# Servisler çalışıyor mu?
sudo systemctl status opensandbox
sudo systemctl status agentic-streamlit

# Port dinliyor mu?
sudo netstat -tulpn | grep -E ":(8080|8501)"

# Docker container'lar
docker ps -a
```

#### 7.2. Test Senaryosu

1. Tarayıcıda aç: `http://<sunucu-ip>:8501`
2. Excel dosyası yükle
3. Soru sor: "Bu dosyadaki verilerin özetini ver, PDF rapor oluştur"
4. Sandbox oluşturulduğunu kontrol et:
   ```bash
   docker ps --filter "label=opensandbox"
   ```
5. PDF indir
6. 1 saat bekle, sandbox otomatik silinmeli:
   ```bash
   docker ps -a --filter "label=opensandbox"
   ```

#### 7.3. Kaynak İzleme Test

```bash
# Monitoring script'i manuel çalıştır
/usr/local/bin/monitor_agentic.sh

# Logları kontrol et
journalctl -t agentic-monitor --since "10 minutes ago"

# Cleanup script test (dry-run benzeri)
docker system df
```

---

## 📊 Beklenen Performans

| Metrik | Değer |
|--------|-------|
| İlk sandbox başlatma | ~5-10 saniye |
| Execute çalıştırma | 1-3 saniye |
| PDF üretme | 2-5 saniye |
| Eşzamanlı kullanıcı | 12-15 |
| Sandbox TTL | 1 saat (inaktivite) |
| RAM kullanımı (5 kullanıcı) | ~15GB (sistem + 5×2GB sandbox) |
| RAM kullanımı (12 kullanıcı) | ~28GB (sistem + 12×2GB sandbox) |

---

## 🚨 Sorun Giderme

### Sorun 1: OpenSandbox başlamıyor

```bash
# Log kontrolü
journalctl -u opensandbox -n 50

# Manuel başlatma (debug)
opensandbox-server --log-level debug

# Docker çalışıyor mu?
sudo systemctl status docker
```

### Sorun 2: Sandbox oluşturulmuyor

```bash
# Config kontrolü
cat ~/.sandbox.toml

# Docker image var mı?
docker images | grep agentic-sandbox

# Manuel sandbox oluşturma test
docker run --rm agentic-sandbox:v1 python -c "print('OK')"
```

### Sorun 3: RAM tükendi

```bash
# Acil: Tüm sandbox'ları durdur
docker ps --filter "label=opensandbox" -q | xargs docker stop

# RAM kullanımı
free -h
docker stats --no-stream

# Config'de limiti düşür
nano ~/.sandbox.toml
# → max_sandboxes = 8 (12 yerine)
sudo systemctl restart opensandbox
```

### Sorun 4: Port çakışması

```bash
# Kullanılan portlar
sudo netstat -tulpn | grep 8080

# Farklı port kullan
sudo nano /etc/systemd/system/opensandbox.service
# → ExecStart ekle: --port 8090

sudo systemctl daemon-reload
sudo systemctl restart opensandbox

# .env güncelle
nano ~/agentic_analyze_d/.env
# → OPEN_SANDBOX_DOMAIN=localhost:8090
```

---

## ✅ Kurulum Checklist

- [ ] Faz 1: Port ve Docker kontrolü yapıldı
- [ ] Faz 2: Custom image build edildi ve test edildi
- [ ] Faz 3: OpenSandbox server kuruldu, config ayarlandı
- [ ] Faz 4: Streamlit app deploy edildi, .env oluşturuldu
- [ ] Faz 5: Systemd servisleri kuruldu, otomatik başlatma aktif
- [ ] Faz 6: Monitoring, cleanup, backup scriptleri kuruldu, crontab eklendi
- [ ] Faz 7: End-to-end test yapıldı (dosya yükle → analiz → PDF)
- [ ] Faz 7: Kaynak kullanımı izlendi (RAM/CPU/Disk)
- [ ] Faz 7: 1 saat sonra sandbox otomatik silindi mi kontrol edildi

---

## 📞 Sonraki Adımlar

1. **Hemen:** Port kontrolü ve Docker kurulumu (15 dk)
2. **Yarın:** Custom image build ve test (1 saat)
3. **Sonraki gün:** OpenSandbox + Streamlit kurulumu (2 saat)
4. **3. gün:** Monitoring scriptleri + test (2 saat)
5. **1 hafta sonra:** Production'a al (kod migration tamamlandıktan sonra)

**Toplam:** ~6-8 saat net iş (kurulum + test)

---

## 💡 Notlar

- Mevcut sunucu kaynak olarak **fazlasıyla yeterli** (16 vCPU, 31GB RAM)
- Ayrı sunucu kiralamaya **gerek yok**
- **$480/ay tasarruf** (Daytona sandbox maliyeti kalkacak)
- Mevcut uygulamalar ile çakışma riski **düşük** (Docker izolasyonu)
- Monitoring **zorunlu** (kaynak paylaşıldığı için)
- İlk 2 hafta dikkatli izleme, sonra routine

**Sorun çıkarsa:** Rollback planı var (Daytona'ya geri dönülebilir, 1 gün)
