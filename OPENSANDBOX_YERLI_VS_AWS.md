# OpenSandbox: Yerli Sunucu vs AWS

**Soru:** OpenSandbox'ı yerli sunucuya mı, AWS'ye mi kuralım?

---

## 🖥️ Yerli Sunucu (Mevcut external-compute)

### Management (Günlük İşler)

**Haftalık Rutin (15-20 dakika):**
```bash
# Pazartesi sabahı kontrol
ssh ubuntu@external-compute
systemctl status opensandbox agentic-streamlit
free -h
df -h
journalctl -t agentic-monitor --since "7 days ago" -p err
```

**Otomatik Çalışanlar:**
- Her 5 dk: RAM/CPU/disk izleme (cron)
- Her Pazar 03:00: Docker cleanup (cron)
- Her gün 02:00: Backup (cron)

**Acil Durum (yılda 1-2 kez):**
- Sunucu çöktü → SSH ile gir, restart (30-60 dk)
- Disk doldu → Cleanup script (5 dk)
- RAM tükendi → Sandbox'ları durdur (2 dk)

**Yedekleme:**
- Manuel: Script çalıştır, tar.gz dosyasını indir
- Sunucu çökerse: Yeniden kurulum (4-8 saat)

---

### Ölçeklendirme

#### Senaryo 1: 10 → 20 kullanıcı

**Adım:** Config değiştir (5 dakika)
```bash
nano ~/.sandbox.toml
# max_sandboxes = 12 → 18
# default_memory = "2Gi" → "1.5Gi"
sudo systemctl restart opensandbox
```

**Maliyet:** $0 (aynı sunucu yeterli)

---

#### Senaryo 2: 20 → 30+ kullanıcı (RAM yetersiz)

**Seçenek A:** Sunucu upgrade (1-2 gün)
```
1. Yeni sunucu kirala (64GB RAM)
2. Backup'tan geri yükle
3. Servisleri başlat
4. Test et
5. Eski sunucuyu kapat
```

**Downtime:** 2-4 saat  
**Maliyet:** $150/ay → $240/ay

**Seçenek B:** İkinci sunucu ekle (2-3 gün)
```
1. İkinci sunucu kirala
2. Nginx load balancer kur
3. Redis session store ekle (shared state için)
4. Her iki sunucuya OpenSandbox kur
5. Test et
```

**Downtime:** 1-2 saat (load balancer kurulumu)  
**Maliyet:** $150/ay → $300/ay (2 sunucu)

---

#### Senaryo 3: 50+ kullanıcı

**Çözüm:** Multi-instance + load balancer (zorunlu)

**Süre:** 1 hafta (manuel kurulum)  
**Maliyet:** 3-4 sunucu × $150 = $450-600/ay

---

### Artıları/Eksileri

| | Yerli Sunucu |
|---|---|
| **Maliyet** | ✅ En ucuz ($150/ay) |
| **Management** | ⚠️ Manuel (haftalık 15-20 dk) |
| **Ölçeklendirme** | ❌ Manuel (1-3 gün iş) |
| **Downtime** | ⚠️ 2-4 saat (upgrade sırasında) |
| **Yedekleme** | ❌ Manuel (script çalıştır) |
| **Acil durum** | ❌ Kendiniz müdahale (30-60 dk) |
| **Kontrol** | ✅ Tam kontrol (her şey sizde) |

---

## ☁️ AWS (EC2 + OpenSandbox)

### Management (Günlük İşler)

**Haftalık Rutin (15-20 dakika):**
```bash
# Aynı komutlar
ssh ubuntu@<ec2-ip>
systemctl status opensandbox agentic-streamlit
free -h
df -h

# EK: AWS CloudWatch logları
# AWS Console → CloudWatch → Logs → agentic-monitor
```

**Otomatik Çalışanlar:**
- Her 5 dk: RAM/CPU/disk izleme (cron)
- Her Pazar 03:00: Docker cleanup (cron)
- Her gün 02:00: Backup (otomatik AMI snapshot)

**Acil Durum:**
- Sunucu çöktü → Snapshot'tan yeni instance (10 dk)
- Disk doldu → EBS volume büyüt (5 dk)
- RAM tükendi → Instance type değiştir (5 dk)

**Yedekleme:**
- Otomatik: AMI snapshot (günlük, AWS hallediyor)
- Sunucu çökerse: Snapshot'tan yeni instance (10 dk)

---

### Ölçeklendirme

#### Senaryo 1: 10 → 20 kullanıcı

**Adım:** Config değiştir (5 dakika)
```bash
nano ~/.sandbox.toml
# max_sandboxes = 12 → 18
sudo systemctl restart opensandbox
```

**Maliyet:** $0 (aynı instance yeterli)

---

#### Senaryo 2: 20 → 30+ kullanıcı (RAM yetersiz)

**Adım:** Instance type değiştir (10 dakika)
```
AWS Console:
1. Stop instance
2. Actions → Instance Settings → Change Instance Type
3. t3.2xlarge → m5.4xlarge (64GB RAM)
4. Start instance
```

**Downtime:** 5-10 dakika  
**Maliyet:** $180/ay → $490/ay

**Alternatif:** Reserved instance 1 yıl = $300/ay (ucuz)

---

#### Senaryo 3: 50+ kullanıcı

**Seçenek A:** Tek instance büyüt
```
m5.4xlarge → m5.8xlarge (128GB RAM)
```

**Downtime:** 5-10 dakika  
**Maliyet:** $980/ay (on-demand)

**Seçenek B:** Multi-instance + Load Balancer (1-2 gün)
```
1. Application Load Balancer oluştur (AWS Console)
2. İkinci EC2 instance başlat (AMI'dan)
3. Target Group ekle
4. Redis ElastiCache kur (session store)
5. Test et
```

**Downtime:** 0 (zero downtime deployment)  
**Maliyet:** 2 × $180 + $50 (ALB) + $30 (Redis) = $440/ay

**Seçenek C:** Auto Scaling + EKS (Kubernetes)
```
AWS EKS kullan (managed Kubernetes)
Auto scaling rules:
- CPU %70 → +1 instance
- CPU %30 → -1 instance
```

**Kurulum:** 1 hafta (Kubernetes bilgisi gerekir)  
**Maliyet:** $220/ay (EKS) + değişken instance ($200-800/ay)

---

### Artıları/Eksileri

| | AWS |
|---|---|
| **Maliyet** | ⚠️ Orta-Yüksek ($180-490/ay) |
| **Management** | ⚠️ Manuel (haftalık 15-20 dk, yerli ile aynı) |
| **Ölçeklendirme** | ✅ Çok hızlı (5-10 dk, instance type değiştir) |
| **Downtime** | ✅ Minimal (5-10 dk) |
| **Yedekleme** | ✅ Otomatik (AMI snapshot) |
| **Acil durum** | ✅ Snapshot'tan 10 dk'da kurtarma |
| **Kontrol** | ⚠️ AWS'ye bağımlısınız |

---

## 📊 Karşılaştırma Tablosu

### Management (Günlük Operasyon)

| Görev | Yerli Sunucu | AWS |
|-------|--------------|-----|
| Haftalık kontrol | 15-20 dk | 15-20 dk (aynı) |
| Otomatik scriptler | Kendiniz kurun | Kendiniz kurun (aynı) |
| Yedekleme | Manuel (cron) | Otomatik (AMI) ✅ |
| Sunucu çökerse | Yeniden kurulum (4-8 saat) | Snapshot'tan 10 dk ✅ |
| Disk dolunca | Cleanup (5 dk) | EBS büyüt (5 dk) ✅ |

**Fark:** AWS'de acil durum kurtarma çok daha hızlı (snapshot sayesinde)

---

### Ölçeklendirme

| Senaryo | Yerli Sunucu | AWS |
|---------|--------------|-----|
| **10 → 20 kullanıcı** | Config değiştir (5 dk) | Config değiştir (5 dk) |
| **20 → 30 kullanıcı** | Yeni sunucu (1-2 gün, 2-4 saat downtime) | Instance type değiştir (10 dk, 5-10 dk downtime) ✅ |
| **30 → 50 kullanıcı** | İkinci sunucu + LB (2-3 gün) | ALB + ikinci instance (1-2 gün, 0 downtime) ✅ |
| **50+ kullanıcı** | Manuel multi-instance (1 hafta) | Auto scaling/EKS (1 hafta, otomatik) ✅ |

**Fark:** AWS'de ölçeklendirme çok daha hızlı ve kolay

---

### Maliyet (10-50 Kullanıcı)

| Kullanıcı | Yerli Sunucu | AWS On-Demand | AWS Reserved (1 yıl) |
|-----------|--------------|---------------|----------------------|
| **10** | $150/ay (31GB) | $180/ay (t3.2xlarge) | $110/ay |
| **20** | $150/ay (aynı) | $180/ay (aynı) | $110/ay |
| **30** | $240/ay (64GB) | $490/ay (m5.4xlarge) | $300/ay |
| **50** | $450/ay (3 sunucu) | $440/ay (2 instance + ALB + Redis) | $280/ay |

**Fark:**
- 10-20 kullanıcı → Yerli en ucuz
- 30+ kullanıcı → AWS reserved competitive
- 50+ kullanıcı → Neredeyse aynı maliyet

---

### Acil Durum Senaryoları

| Senaryo | Yerli Sunucu | AWS |
|---------|--------------|-----|
| Sunucu çöktü | 4-8 saat (yeniden kur) | 10 dk (snapshot) ✅ |
| Disk doldu | 5 dk (cleanup) | 5 dk (EBS büyüt) |
| RAM yetersiz | 1-2 gün (upgrade) | 10 dk (instance type) ✅ |
| Network sorunu | Sağlayıcıya ticket | AWS'ye ticket (genelde daha hızlı) |
| Güvenlik açığı | Manuel patch | AWS'nin infradan sorumlu ✅ |

**Fark:** AWS'de disaster recovery çok daha hızlı

---

## 🎯 Hangi Durumda Hangisi?

### Yerli Sunucu Seçin Eğer:

✅ Bütçe kısıtlı ($150/ay vs $180-490/ay)  
✅ Sabit kullanıcı sayısı (10-20, ani büyüme yok)  
✅ Downtime tolere edilir (2-4 saat upgrade sırasında)  
✅ Manuel ölçeklendirme yapabilirsiniz (1-2 gün iş)  
✅ Veri lokasyonu kritik (Türkiye'de kalmalı)  

**Özet:** En ucuz, ama disaster recovery yavaş

---

### AWS Seçin Eğer:

✅ Hızlı ölçeklendirme gerekiyor (10 → 50 kullanıcı 6 ay içinde)  
✅ Downtime kritik (5-10 dk max)  
✅ Disaster recovery önemli (10 dk'da kurtarma)  
✅ Otomatik yedekleme istiyorsunuz (AMI snapshot)  
✅ Gelecekte auto scaling/K8s planı var  

**Özet:** Daha pahalı, ama disaster recovery ve ölçeklendirme çok hızlı

---

## 💡 Bizim Durumumuz İçin Öneri

### Şimdilik: Yerli Sunucu (Mevcut external-compute)

**Neden:**
1. Kaynak zaten var (16 vCPU, 31GB RAM)
2. Hedef 10-15 kullanıcı (sabit)
3. Bütçe hassasiyeti var ($480/ay tasarruf önemli)
4. Downtime 2-4 saat tolere edilir
5. Ani büyüme beklenmiyor

**Maliyet:** $150/ay (sadece Claude API)

---

### 6 Ay Sonra Değerlendirin

**Eğer bunlar olursa AWS'e geçin:**

❌ Kullanıcı 30+'a çıktı (hızlı büyüme)  
❌ Downtime problem oldu (kullanıcı şikayeti)  
❌ Manuel ölçeklendirme çok iş çıkarıyor  
❌ Disaster recovery gerekti (sunucu çöktü, 4 saat downtime)  

**AWS'ye geçiş:** 1-2 gün (AMI export → EC2 import)

---

### Hibrit Strateji (En Akıllıcası)

```
Faz 1 (İlk 6 ay):
  Yerli sunucu → Test et, kullanım ölçümle
  Maliyet: $150/ay

Faz 2 (Büyüme varsa):
  AWS'e migrate → Reserved instance al
  Maliyet: $110-300/ay (1 yıl reserved)

Faz 3 (50+ kullanıcı):
  AWS Auto Scaling → EKS
  Maliyet: $400-800/ay (ama hacim karşılıyor)
```

**Başarı metriği:** 6 ayda kullanıcı 2x olursa → AWS'e geç

---

## 📋 Özet (Tek Tablo)

| | Yerli Sunucu | AWS |
|---|---|---|
| **Kurulum** | 1 gün | 1-2 gün (VPC, IAM vs.) |
| **Management** | 15-20 dk/hafta | 15-20 dk/hafta (aynı) |
| **Yedekleme** | Manuel (cron) | Otomatik (AMI) ✅ |
| **Ölçeklendirme** | 1-2 gün (manuel) | 10 dk (instance type) ✅ |
| **Disaster recovery** | 4-8 saat | 10 dk ✅ |
| **Downtime** | 2-4 saat (upgrade) | 5-10 dk ✅ |
| **Maliyet (10 user)** | $150/ay ✅ | $180/ay (on-demand) |
| **Maliyet (30 user)** | $240/ay ✅ | $300/ay (reserved) |
| **Maliyet (50 user)** | $450/ay | $440/ay (benzer) |

---

## 🎯 Final Karar

**Soru:** Yerli sunucu mu, AWS mi?

**Cevap:** **Yerli sunucu (şimdilik)**

**Gerekçe:**
- Mevcut sunucu yeterli (16 vCPU, 31GB)
- Hedef 10-15 kullanıcı (sabit)
- En ucuz ($150/ay)
- Downtime tolere edilir
- 6 ay test et, sonra değerlendir

**AWS'e ne zaman geçilir:**
- Kullanıcı 30+'a çıkarsa
- Downtime problem olursa
- Hızlı ölçeklendirme gerekirse

**Sonraki adım:** Yerli sunucuya kur, 6 ay ölç, karar ver.
