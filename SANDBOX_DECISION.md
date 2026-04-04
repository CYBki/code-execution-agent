# Sandbox Stratejisi — Karar Dokümanı

> **📋 Status: TAMAMLANDI**  
> **Karar:** OpenSandbox seçildi ve projeye entegre edildi (Nisan 2026).  
> **Sonuç:** Persistent CodeInterpreter kernel ile değişkenler execute'lar arası korunur, pickle ihtiyacı ortadan kalktı.  
> Bu doküman tarihsel referans amaçlıdır.

**Tarih:** 1 Nisan 2026  
**Amaç:** Agentic Analyze projesini kullanıcılara açarken hangi sandbox altyapısını kullanacağımıza karar vermek.

---

## 1. Mevcut Durum

Şu an **Daytona Cloud** kullanıyoruz. Her kullanıcı oturumu için izole bir Docker container oluşturuluyor. Agent bu container'da Python kodu çalıştırıyor.

**Daytona'ya bağımlı kod:**

| Dosya | Satır | Bağımlılık Seviyesi |
|---|---|---|
| `src/sandbox/manager.py` | 398 | **Tamamen Daytona-specific** — lifecycle, SDK, package install |
| `src/tools/execute.py` | 117 | `backend.execute(cmd)` — generic interface |
| `src/tools/visualization.py` | ~80 | `backend.execute(cmd)` — generic interface |
| `src/tools/download_file.py` | ~60 | `backend.download_files()` — küçük adaptasyon gerekir |

**Kritik bulgu:** Tool'lar `backend.execute(cmd) → output` arayüzünü kullanıyor. Bu interface'i sağlayan herhangi bir backend takılabilir. `graph.py`, `prompts.py`, `app.py`, skill sistemi **hiç değişmez.**

---

## 2. Seçenekler

### Seçenek A — Daytona Self-Hosted (On-Prem)

Daytona open source. Docker Compose ile kendi sunucumuza kurulabilir.

```bash
git clone https://github.com/daytonaio/daytona
docker compose -f docker/docker-compose.yaml up -d
```

**İçinde gelen servisler:** API server, Runner, SSH Gateway, PostgreSQL, Redis, MinIO, Docker Registry, Proxy, Jaeger.

| | Detay |
|---|---|
| **Kod değişikliği** | 0 satır — aynı SDK, sadece env variable değişir |
| **Kurulum süresi** | 1 gün |
| **Maliyet** | Sabit sunucu ücreti (AWS t3.xlarge ~$120/ay) |
| **Ölçekleme** | Manuel — sunucu kapasitesi kadar |
| **Güvenlik** | Docker container izolasyonu |

**Limitasyonlar:**
- Docker Compose tek sunucuda çalışır — horizontal scaling yok
- 50+ eşzamanlı kullanıcıda sunucu yetersiz kalabilir (her sandbox ~512MB RAM)
- Kubernetes'e geçiş gerekebilir (Daytona destekliyor ama ek DevOps yükü)
- Sunucu bakımı, güncelleme, monitoring sizin sorumluluğunuz
- Docker izolasyonu microVM'e göre daha zayıf (kernel paylaşılır)
- Sandbox resource limitleri DinD ortamda tam çalışmıyor (Daytona docs notu)

**Kaynak:** https://www.daytona.io/docs/en/oss-deployment/

---

### Seçenek B — Daytona Cloud (Mevcut)

Şu anki model. Daytona'nın managed cloud'u.

| | Detay |
|---|---|
| **Kod değişikliği** | 0 satır |
| **Kurulum süresi** | Zaten hazır |
| **Maliyet** | ~$0.067/saat per sandbox + $200 ücretsiz kredi |
| **Ölçekleme** | Otomatik |
| **Güvenlik** | Daytona managed Docker |

**Maliyet projeksiyonu:**

| Kullanıcı | Günlük (8 saat) | Aylık (22 iş günü) |
|---|---|---|
| 10 eşzamanlı | ~$5.36 | ~$118 |
| 25 eşzamanlı | ~$13.40 | ~$295 |
| 50 eşzamanlı | ~$26.80 | ~$590 |

**Limitasyonlar:**
- Fatura kontrolü zor — kullanıcı sandbox'u açık bırakırsa maliyet artar (TTL=3600s ile hafifletilmiş)
- Vendor lock-in — Daytona kapanırsa veya fiyat artırırsa alternatife geçiş gerekir
- Veri Daytona sunucularında işlenir — regülasyon/compliance sorunu olabilir
- Default resource limitleri düşük, artırmak için Daytona ile iletişim gerekir
- $200 kredi bitince otomatik faturalandırma başlar

**Kaynak:** https://betterstack.com/community/comparisons/best-sandbox-runners/

---

### Seçenek C — AWS ECS Fargate

Her kullanıcı için izole Fargate task.

| | Detay |
|---|---|
| **Kod değişikliği** | ~400 satır (manager.py tamamen yeniden) |
| **Kurulum süresi** | 2-3 hafta |
| **Maliyet** | ~$0.04/saat (vCPU) + $0.004/saat (GB RAM) |
| **Ölçekleme** | Otomatik (ECS auto-scaling) |
| **Güvenlik** | Container + VPC + IAM |

**Limitasyonlar:**
- Cold start 30-60 saniye (Daytona: 90ms) — kullanıcı ilk soruda bekler
- ECS task definition, IAM role, VPC, security group kurulumu karmaşık
- Package pre-install için custom Docker image build pipeline gerekir
- `backend.execute()` interface'ini ECS Exec API üzerinden implemente etmek gerekir
- ECS Exec SSM agent gerektirir — her container'da kurulu olmalı
- Fargate'te disk 20GB ephemeral — büyük dosyalar için EFS mount gerekir
- DevOps bilgisi yüksek seviyede gerekli

---

### Seçenek D — Cloudflare Sandboxes

| | Detay |
|---|---|
| **Kod değişikliği** | ~400 satır (manager.py tamamen yeniden) |
| **Kurulum süresi** | 1 hafta |
| **Maliyet** | $0.00002/vCPU-second (~$0.072/saat) + Workers $5/ay |
| **Ölçekleme** | Otomatik (global CDN) |
| **Güvenlik** | Per-VM Linux container |

**Limitasyonlar:**
- **Beta aşamasında** — production'da beklenmedik sorunlar çıkabilir
- 10 dakika inaktivite → container sıfırlanır, state kaybolur
- GPU desteği yok
- BYOC (Bring Your Own Cloud) yok
- pip install süresi her yeni container'da tekrarlanır (pre-built image desteği sınırlı)
- Python SDK henüz olgun değil
- Türkiye'den latency testi yapılmadı

**Kaynak:** https://betterstack.com/community/comparisons/best-sandbox-runners/

---

### Seçenek E — Microsandbox (Open Source, Self-Hosted)

| | Detay |
|---|---|
| **Kod değişikliği** | ~400 satır + Python wrapper yazılmalı |
| **Kurulum süresi** | 1-2 hafta |
| **Maliyet** | Sabit sunucu ücreti |
| **Ölçekleme** | Manuel |
| **Güvenlik** | **microVM** (en güçlü izolasyon) |

**Limitasyonlar:**
- **Beta aşamasında** — breaking change riski yüksek
- Python SDK yok — TypeScript ve Rust SDK var, Python wrapper yazman gerekir
- KVM gerekli — AWS'de bare metal instance veya nested virt destekli VM lazım (daha pahalı)
- Topluluk küçük, dokümantasyon sınırlı
- Production referansı yok
- Long-running session yönetimi test edilmedi

**Kaynak:** https://github.com/microsandbox/microsandbox

---

## 3. Karşılaştırma Matrisi

| Kriter | A. Daytona Self-Host | B. Daytona Cloud | C. AWS Fargate | D. Cloudflare | E. Microsandbox |
|---|---|---|---|---|---|
| Kod değişikliği | **0 satır** | **0 satır** | ~400 satır | ~400 satır | ~400+ satır |
| Hazır olma | **1 gün** | **Zaten hazır** | 2-3 hafta | 1 hafta | 1-2 hafta |
| Cold start | 90ms | 90ms | 30-60s | ~200ms | <100ms |
| Maliyet kontrolü | **Sabit** | Değişken | Değişken | Değişken | **Sabit** |
| Ölçekleme | Manuel | Otomatik | Otomatik | Otomatik | Manuel |
| İzolasyon | Docker | Docker | Container+VPC | Container | **microVM** |
| Olgunluk | Stable | Stable | Stable | Beta | Beta |
| DevOps yükü | Orta | **Düşük** | Yüksek | Düşük | Orta |
| Vendor lock-in | Düşük (OSS) | **Yüksek** | Orta (AWS) | Orta | **Yok** |
| Veri lokasyonu | **Sizin sunucu** | Daytona DC | AWS region | Cloudflare edge | **Sizin sunucu** |

---

## 4. Mevcut Cloud Kaynaklarınızla Eşleştirme

| Cloud | En Uygun Seçenek | Nasıl? |
|---|---|---|
| **AWS** | Seçenek A (Daytona Self-Host) | EC2 t3.xlarge + Docker Compose |
| **Azure** | Seçenek A (Daytona Self-Host) | Azure VM D4s_v3 + Docker Compose |
| **Google Cloud** | Seçenek A (Daytona Self-Host) | Compute Engine e2-standard-4 + Docker Compose |
| **Cloudflare** | Seçenek D (Cloudflare Sandboxes) | Beta — test et, production'a alma |
| **Yerli Cloud** | Seçenek A (Daytona Self-Host) | Linux VM + Docker Compose |

---

## 5. Öneri — Aşamalı Yaklaşım

### Faz 1 — Hemen (bu hafta)
**Daytona Self-Hosted** kur. Kod değişikliği sıfır, 1 günde hazır.
AWS/Azure/GCP/yerli cloud — herhangi birinde Linux VM aç, Docker Compose çalıştır.

```bash
# Env variable değişikliği — tek değişiklik bu
DAYTONA_BASE_URL=https://your-server:3000
DAYTONA_API_KEY=your-self-hosted-key
```

### Faz 2 — Kullanıcı sayısı 25'i geçince
Sunucu boyutunu artır veya Kubernetes'e geç. Daytona K8s deployment destekliyor.

### Faz 3 — 100+ kullanıcı veya maliyet optimizasyonu gerekince
`manager.py`'yi abstract interface'e çevir → AWS Fargate veya olgunlaşmış Microsandbox'a geç (~450 satır değişiklik).

---

## 6. Karar İçin Sorulması Gereken 3 Soru

1. **Veri lokasyonu:** Müşteri verileri Daytona Cloud'da işlenebilir mi, yoksa on-prem zorunlu mu?
2. **Eşzamanlı kullanıcı tahmini:** İlk 3 ayda kaç kişi aynı anda kullanacak?
3. **DevOps kapasitesi:** Docker Compose sunucusu yönetecek biri var mı?

**Bu 3 sorunun cevabına göre:**
- Veri hassas + DevOps var → **Seçenek A (Daytona Self-Hosted)**
- Veri hassas değil + hız önemli → **Seçenek B (Daytona Cloud)**
- AWS zaten aktif + DevOps güçlü → **Seçenek C (AWS Fargate)**

---

## Kaynaklar

- Daytona OSS Deployment: https://www.daytona.io/docs/en/oss-deployment/
- Daytona GitHub: https://github.com/daytonaio/daytona
- Sandbox Runners Karşılaştırması: https://betterstack.com/community/comparisons/best-sandbox-runners/
- Microsandbox GitHub: https://github.com/microsandbox/microsandbox
- AWS ECS Fargate: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/
