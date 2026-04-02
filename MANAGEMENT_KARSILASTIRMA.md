# Sandbox Management Karşılaştırması

**Soru:** Sandbox'ı kendimiz mi yönetelim (on-prem), cloud mu kullanalım?

---

## 🔧 1. Günlük Management: Ne Yapacaksınız?

### On-Prem (OpenSandbox - Mevcut Sunucu)

**Haftalık Rutin (15-20 dakika):**

```bash
# Pazartesi sabahı (5 dakika)
ssh ubuntu@external-compute
systemctl status opensandbox agentic-streamlit  # Servisler ayakta mı?
docker ps --filter "label=opensandbox"          # Kaç sandbox aktif?
free -h                                          # RAM durumu
df -h                                            # Disk doldu mu?

# Logları kontrol et (10 dakika)
journalctl -t agentic-monitor --since "7 days ago" -p err  # Hata var mı?
journalctl -u opensandbox -n 50                             # OpenSandbox loglari

# Eğer sorun varsa (5 dakika)
docker system prune -f     # Cleanup
systemctl restart opensandbox
```

**Otomatik Çalışanlar (elle bir şey yapmayacaksınız):**
- Her 5 dakika: RAM/CPU/disk kontrol (script)
- Her Pazar 03:00: Docker cleanup (cron)
- Her gün 02:00: Backup (cron)
- RAM %85+ olursa: En eski 2 sandbox'ı otomatik durdur

**Acil Durum (yılda 1-2 kez, 30-60 dakika):**
- Sunucu çöktü → SSH ile gir, servisleri restart et
- Disk doldu → Cleanup script çalıştır
- Çok yavaş → Sandbox limitini düşür (config)

---

### Cloud (Daytona - Şu An)

**Haftalık Rutin (10 dakika):**

```python
# Pazartesi sabahı (5 dakika)
python cleanup_sandboxes.py  # Stopped sandbox'ları temizle

# Daytona dashboard'a gir (5 dakika)
# → Sandbox sayısı
# → Maliyet ($480/ay civarı olmalı)
# → Hata logları var mı?
```

**Otomatik Çalışanlar:**
- Her şey (Daytona hallediyor)
- Sandbox lifecycle, timeout, cleanup → otomatik

**Acil Durum:**
- Disk limiti doldu (30GB) → `cleanup_sandboxes.py` çalıştır
- Daytona servisi down → Bekle (sizin kontrolünüzde değil)

---

### Karşılaştırma

| Görev | On-Prem | Cloud (Daytona) |
|-------|---------|-----------------|
| **Haftalık kontrol** | 15-20 dk | 10 dk |
| **Otomatik işler** | Cron scriptler (kurmanız lazım) | Hepsi hazır |
| **Acil durum müdahale** | SSH → restart (30-60 dk) | Yok (Daytona'nın sorunu) |
| **Sunucu down** | Sizin sorumluluğunuz | Daytona'nın sorumluluğu |
| **Ölçeklendirme** | Config düzenle veya sunucu büyüt | Otomatik (Daytona halleder) |
| **Maliyet** | $150/ay (Claude API) | $630/ay |

**Fark:** Haftada 5-10 dakika daha fazla iş (on-prem) ama ayda $480 tasarruf.

---

## 🚀 2. Ölçeklendirme: Kullanıcı Artarsa Ne Olur?

### Senaryo: 10 kullanıcı → 25 kullanıcıya çıktı

#### On-Prem (OpenSandbox)

**Adım 1:** Config değiştir (5 dakika)

```toml
# ~/.sandbox.toml
max_sandboxes = 12  →  max_sandboxes = 20
default_memory = "2Gi"  →  default_memory = "1.5Gi"
```

```bash
sudo systemctl restart opensandbox
```

**Adım 2:** Yetmezse, sunucuyu büyüt (1-2 gün)
- 31GB RAM → 64GB RAM sunucu kirala
- Kod/config aynı, sadece sunucu değişir

**Maliyet:**
- 31GB sunucu: $150/ay
- 64GB sunucu: $240/ay

---

#### Cloud (Daytona)

**Yapmanız gereken:** Hiçbir şey (otomatik ölçeklenir)

**Maliyet:**
- 10 kullanıcı: $630/ay
- 25 kullanıcı: $1,500/ay ($0.067/saat × 25 user × 24 saat × 30 gün)

---

### Senaryo: 25 kullanıcı → 50 kullanıcıya çıktı

#### On-Prem

**Çözüm 1:** Tek sunucu büyüt
- 64GB → 128GB RAM sunucu
- Maliyet: $400-500/ay

**Çözüm 2:** İkinci sunucu ekle + Load balancer
- 2 sunucu × $150 = $300/ay
- Nginx load balancer (1 gün kurulum)

---

#### Cloud (Daytona)

**Yapmanız gereken:** Hiçbir şey

**Maliyet:**
- 50 kullanıcı: $3,000/ay

---

### Karşılaştırma

| Kullanıcı Sayısı | On-Prem (Aylık) | Cloud (Aylık) | Fark |
|------------------|-----------------|---------------|------|
| 10 | $150 | $630 | -$480 |
| 25 | $240 | $1,500 | -$1,260 |
| 50 | $400 | $3,000 | -$2,600 |

**On-prem:** Manuel ölçeklendirme (1-2 gün iş) ama çok daha ucuz  
**Cloud:** Otomatik ölçeklendirme ama çok pahalı

---

## 🐛 3. Hatalar: "Bir Sürü İş Var" Senaryosu

### Tipik Sorunlar ve Çözümleri

#### Sorun 1: Sandbox oluşturulmuyor

**On-Prem:**
```bash
# Teşhis (2 dakika)
journalctl -u opensandbox -n 50

# Çözüm 1: Restart (30 saniye)
sudo systemctl restart opensandbox

# Çözüm 2: Docker image problemi (5 dakika)
docker pull agentic-sandbox:v1
docker images | grep agentic-sandbox

# Çözüm 3: Config hatası (5 dakika)
nano ~/.sandbox.toml  # max_sandboxes çok yüksek mi?
```

**Cloud (Daytona):**
```python
# Çözüm yok (Daytona'nın sorunu)
# Ticket açarsınız, beklersiniz
```

---

#### Sorun 2: RAM tükendi, sistem yavaşladı

**On-Prem:**
```bash
# Acil müdahale (1 dakika)
docker ps --filter "label=opensandbox" -q | xargs docker stop

# Config düşür (2 dakika)
nano ~/.sandbox.toml
# → max_sandboxes = 8 (12 yerine)
sudo systemctl restart opensandbox
```

**Cloud (Daytona):**
```python
# Cleanup script çalıştır
python cleanup_sandboxes.py

# Disk limitine takıldıysanız, Daytona'ya ticket açın
```

---

#### Sorun 3: Disk doldu

**On-Prem:**
```bash
# Hemen cleanup (2 dakika)
docker system prune -a -f --volumes
find /tmp -name "sandbox-*" -delete

# Disk bittiyse sunucu büyüt (1 gün)
```

**Cloud (Daytona):**
```python
# 30GB limit var, cleanup script çalıştır
python cleanup_sandboxes.py

# Limit aşılırsa → Daytona'ya ticket
```

---

#### Sorun 4: Execute timeout (30 saniye geçiyor)

**On-Prem:**
```bash
# Config artır (2 dakika)
nano ~/.sandbox.toml
# → default_timeout = "2h" (1h yerine)
sudo systemctl restart opensandbox
```

**Cloud (Daytona):**
```python
# Kod tarafında timeout ayarı (değişken)
sandbox.execute(..., timeout=120)
```

---

### Karşılaştırma

| Sorun | On-Prem Çözüm Süresi | Cloud Çözüm Süresi |
|-------|----------------------|--------------------|
| Sandbox oluşturulmuyor | 2-10 dakika (kendiniz) | Bilinmiyor (Daytona) |
| RAM tükendi | 1-3 dakika (acil müdahale) | 5 dakika (cleanup script) |
| Disk doldu | 2 dakika (prune) | 5 dakika (cleanup script) |
| Config değişikliği | 2-5 dakika | Kod değişikliği (deploy gerekir) |

**On-prem:** Sorunları kendiniz çözersiniz (hızlı)  
**Cloud:** Bazı sorunlarda eliniz kolunuz bağlı (Daytona'ya bağımlısınız)

---

## 📦 4. Sandbox "Kapalı Kutu" mu? (Sizin Endişeniz)

### OpenSandbox Gerçekten Kapalı Kutu mu?

**Evet ama yarım:**

✅ **Kapalı kutu olanlar (dokunmayın):**
- Sandbox lifecycle (oluşturma, silme, timeout)
- Docker container yönetimi
- Execute komutlarını izole etme
- Dosya transfer (upload/download)

❌ **Sizin yönetmeniz gerekenler:**
- Docker engine (kurulum, upgrade)
- Sunucu kaynakları (RAM/CPU izleme)
- Disk temizliği (Docker prune)
- Config ayarları (max_sandboxes, timeout vs.)
- Servis restart (crash olursa)

**Yani:** Sandbox logic kapalı kutu, ama altyapı sizin sorumluluğunuzda.

---

### Daytona Gerçekten Kapalı Kutu mu?

**Evet, tam kapalı kutu:**

✅ **Daytona halleder:**
- Sandbox lifecycle
- Sunucu kaynakları
- Disk yönetimi
- Otomatik ölçeklendirme
- Servis uptime

❌ **Sizin yapmanız gereken:**
- Cleanup script çalıştırma (30GB disk limiti için)
- Maliyet izleme

**Yani:** Neredeyse her şey Daytona'nın sorumluluğunda.

---

### Karşılaştırma

| | OpenSandbox (On-Prem) | Daytona (Cloud) |
|---|---|---|
| **Sandbox logic** | ✅ Kapalı kutu | ✅ Kapalı kutu |
| **Sunucu yönetimi** | ❌ Sizin | ✅ Daytona |
| **Disk yönetimi** | ❌ Sizin | ✅ Daytona (ama 30GB limit) |
| **Ölçeklendirme** | ❌ Manuel | ✅ Otomatik |
| **Hata müdahalesi** | ❌ Sizin | ✅ Daytona (ticket) |
| **Maliyet kontrolü** | ✅ Sabit ($150) | ❌ Değişken ($630+) |

**OpenSandbox:** Yarı kapalı kutu (sandbox kapalı, altyapı sizin)  
**Daytona:** Tam kapalı kutu (her şey Daytona, ama pahalı)

---

## 💻 5. Kod Değişikliği: Neden/Ne Kadar Değişiyor?

### Neden Değişiyor?

**Sebep:** Daytona ve OpenSandbox **farklı API'ler** kullanıyor.

**Daytona API:**
```python
from daytona_sdk import Daytona

client = Daytona(api_key="...")
workspace = client.create()
workspace.upload_file(path)
result = workspace.execute(code)
workspace.download_file(path)
```

**OpenSandbox API:**
```python
from opensandbox import Sandbox

sandbox = Sandbox.create()
sandbox.files.write(path, content)
result = sandbox.run_code(code)
file = sandbox.files.read(path)
```

Mantık aynı ama **fonksiyon isimleri, parametreler farklı**.

---

### Ne Kadar Değişiyor?

| Dosya | Değişiklik Tipi | Satır | Neden |
|-------|-----------------|-------|-------|
| **src/sandbox/manager.py** | Tamamen yeniden yaz | ~350 | API tamamen farklı |
| **src/tools/download_file.py** | Fonksiyon isimleri değiş | ~20 | `workspace.download()` → `sandbox.files.read()` |
| **src/agent/prompts.py** | Pickle talimatları kaldır | ~15 | Execute isolation kalktı |
| **src/skills/**/*.md** | Döküman güncelle | ~10 | Pickle pattern artık yok |
| **requirements.txt** | Paket değiştir | 2 | `daytona-sdk` → `opensandbox` |

**Toplam:** ~400 satır

---

### Değişmeyen Kısımlar (Önemli!)

✅ **Bunlar aynı kalacak:**
- `src/agent/graph.py` → Agent logic
- `src/tools/execute.py` → Execute tool interface
- `src/tools/artifact_store.py` → Artifact geçişi
- `src/ui/chat.py` → Streamlit UI
- `app.py` → Ana uygulama
- Skill sistemi → Dinamik prompt loading

**Yani:** Sadece sandbox ile konuşan katman değişiyor, geri kalanı aynı.

---

### Kod Değişikliği Örneği

#### Önce (Daytona):

```python
# src/sandbox/manager.py
from daytona_sdk import Daytona

class SandboxManager:
    def __init__(self):
        self.client = Daytona(api_key=os.getenv("DAYTONA_API_KEY"))
    
    def create_sandbox(self):
        workspace = self.client.create_workspace()
        return workspace
    
    def execute_code(self, workspace, code):
        result = workspace.process.create(cmd=f"python -c '{code}'")
        return result.stdout
```

#### Sonra (OpenSandbox):

```python
# src/sandbox/manager.py
from opensandbox import Sandbox

class SandboxManager:
    def __init__(self):
        self.api_key = os.getenv("OPEN_SANDBOX_API_KEY")
    
    def create_sandbox(self):
        sandbox = Sandbox.create(image="agentic-sandbox:v1")
        return sandbox
    
    def execute_code(self, sandbox, code):
        result = sandbox.run_code(code, language="python")
        return result.text
```

**Fark:** API fonksiyonları değişiyor ama mantık aynı (sandbox oluştur → kod çalıştır → sonuç al).

---

### Değişiklik Nedenleri (Detaylı)

#### 1. manager.py (350 satır)

**Neden:**
- Sandbox oluşturma API'si farklı
- Dosya upload/download farklı
- Execute farklı
- Lifecycle management farklı

**Örnek:**
```python
# Daytona
workspace.upload_file(local_path, remote_path)

# OpenSandbox
sandbox.files.write(remote_path, open(local_path).read())
```

---

#### 2. prompts.py (15 satır)

**Neden:** Execute isolation kalktı

**Daytona (subprocess model):**
```
Execute #1: df = pd.read_excel()
           df.to_pickle('data.pkl')  ← Bellekten kaybet, diske yaz

Execute #2: df = pd.read_pickle('data.pkl')  ← Diskten oku
           df.describe()
```

**OpenSandbox (persistent kernel):**
```
Execute #1: df = pd.read_excel()  ← Bellekte kalır

Execute #2: df.describe()  ← Aynı bellekten devam
```

**Prompt değişikliği:**
```diff
- Her execute'den sonra önemli değişkenleri pickle ile kaydet.
- Sonraki execute'de pickle'dan yükle.
+ Değişkenler bellekte kalır, pickle gereksiz.
```

---

#### 3. download_file.py (20 satır)

**Neden:** Dosya okuma API'si farklı

```python
# Daytona
content = workspace.download_file(path)

# OpenSandbox
content = sandbox.files.read_file(path)
```

---

### Rollback (Geri Dönüş) Planı

**Eğer OpenSandbox çalışmazsa:**

1. Git branch'e geri dön (5 dakika)
   ```bash
   git checkout main
   git branch -D opensandbox-migration
   ```

2. Daytona .env'i geri koy (1 dakika)
   ```bash
   cp .env.backup .env
   ```

3. Restart (1 dakika)
   ```bash
   streamlit run app.py
   ```

**Toplam rollback:** 10 dakika

**Kayıp:** 1 haftalık iş (ama risk düşük, test ortamında doğrulama yapılırsa)

---

## 🎯 Özet: Hangi Durumda Ne Seçmeli?

### On-Prem (OpenSandbox) Seçin Eğer:

✅ Haftalık 15-20 dakika management yapabilirsiniz  
✅ Maliyet öncelikli ($480/ay tasarruf)  
✅ Sunucu yönetimi biliyorsunuz (SSH, Docker, systemd)  
✅ Acil durum müdahale edebilirsiniz (30-60 dk)  
✅ 10-25 kullanıcı hedef (sabit büyüme)  

**Özet:** Biraz daha iş ama çok daha ucuz

---

### Cloud (Daytona) Seçin Eğer:

✅ Sıfır management istiyorsunuz  
✅ Maliyet ikinci planda ($630/ay tolere edilir)  
✅ Sunucu yönetimi bilmiyorsunuz  
✅ Otomatik ölçeklendirme lazım (50+ kullanıcı)  
✅ Acil durum müdahalesi istemiyorsunuz  

**Özet:** Çok kolay ama çok pahalı

---

### Bizim Durumumuz İçin Öneri:

**✅ OpenSandbox (On-Prem)**

**Neden:**
1. Mevcut sunucu var, yeterli kaynak (16 vCPU, 31GB RAM)
2. Hedef 10-15 kullanıcı (otomatik ölçeklendirme gereksiz)
3. Teknik ekip var (management yapabilir)
4. $480/ay tasarruf (yılda $5,760)
5. Haftalık 15-20 dakika iş tolere edilebilir

**İlk 6 ay test edin:**
- Management gerçekten 15-20 dakika mı?
- Sorun çok mu çıkıyor?
- Kullanıcı sayısı artıyor mu?

**6 ay sonra:**
- Her şey yolundaysa → Devam
- Çok iş çıkarıyorsa → Cloud'a dönün (ama pahalı)
- Kullanıcı 30+'a çıktıysa → Sunucu büyütün veya cloud

---

## 📞 Final Karar

**Soru:** OpenSandbox (on-prem) mi, Daytona (cloud) mu?

**Cevap:** **OpenSandbox (on-prem)**

**Gerekçe:**
- Haftalık 10 dakika daha fazla iş
- Ama ayda $480 tasarruf
- Mevcut sunucu yeterli
- Teknik ekip management yapabilir
- İlk 6 ay test et, değerlendirmeli

**Sonraki adım:** `KURULUM_PLANI_MEVCUT_SUNUCU.md` ile başlayın.
