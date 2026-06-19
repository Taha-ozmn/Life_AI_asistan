# Life+ Studio (Life_AI_asistan)

Yapay zekâ destekli kişisel sağlık asistanı: diyet ve fitness sohbeti, kalori/hedef planlama, günlük takip (su, adım, beslenme, antrenman) ve BMI analizi. Veriler tarayıcı oturumuna bağlı olarak SQLite’da saklanır.

**Canlı repo:** [github.com/Taha-ozmn/Life_AI_asistan](https://github.com/Taha-ozmn/Life_AI_asistan)

---

## Özellikler

- **AI asistan** — Beslenme, egzersiz ve tarif sorularına Türkçe yanıt
- **Kalori hesapla** — Sohbette `kalori hesapla` yazarak adım adım günlük kalori planı
- **Hedef planla** — Sohbette `hedef planla` yazarak hedef kilo ve aktiviteye göre plan
- **Günlük takip** — Su, adım, ruh hâli, öğün notları, antrenman kaydı
- **BMI & analiz** — Boy/kilo ile BMI hesabı ve AI yorumu
- **Sohbet arşivi** — Geçmiş konuşmalar cihazda kalıcı olarak saklanır
- **PWA** — Ana ekrana eklenebilir, çevrimdışı sayfa desteği

---

## Gereksinimler

- **Python 3.10+** (önerilir)
- Bir yapay zekâ API anahtarı:
  - [Google AI Studio](https://aistudio.google.com/apikey) (Gemini) — varsayılan
  - [Groq](https://console.groq.com/keys) — hızlı, ücretsiz katman
  - [OpenAI](https://platform.openai.com/account/api-keys)

---

## Kurulum

### 1. Repoyu klonlayın

```bash
git clone https://github.com/Taha-ozmn/Life_AI_asistan.git
cd Life_AI_asistan
```

### 2. Sanal ortam oluşturun (önerilir)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 3. Bağımlılıkları yükleyin

```bash
pip install -r requirements.txt
```

### 4. Ortam değişkenlerini ayarlayın

```bash
cp .env.example .env
```

`.env` dosyasını düzenleyin. En azından şunları doldurun:

```env
FLASK_SECRET_KEY=uzun-rastgele-gizli-metin
AI_PROVIDER=gemini
GEMINI_API_KEY=AIza...gercek-anahtariniz
```

Gizli anahtar üretmek için:

```bash
openssl rand -hex 32
```

> **Önemli:** `.env` dosyası Git’e yüklenmez. Gerçek API anahtarlarınızı yalnızca `.env` içinde tutun.

---

## Çalıştırma

```bash
python3 app.py
```

Tarayıcıda açın: **http://127.0.0.1:8000**

Sağlık kontrolü: **http://127.0.0.1:8000/health** — `ai_configured: true` ise API anahtarı doğru yüklenmiştir.

`.env` dosyasını değiştirdikten sonra sunucuyu durdurup (`Ctrl+C`) yeniden başlatın.

---

## Yapay zekâ sağlayıcıları

| Sağlayıcı | `.env` ayarı | Anahtar |
|-----------|--------------|---------|
| **Gemini** (varsayılan) | `AI_PROVIDER=gemini` | `GEMINI_API_KEY=AIza...` |
| **Groq** | `AI_PROVIDER=groq` | `GROQ_API_KEY=gsk_...` |
| **OpenAI** | `AI_PROVIDER=openai` | `OPENAI_API_KEY=sk-...` |

Örnek Groq yapılandırması:

```env
AI_PROVIDER=groq
GROQ_API_KEY=gsk-buraya-groq-anahtari
AI_MODEL=llama-3.1-8b-instant
```

Örnek OpenAI yapılandırması:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-buraya-openai-anahtari
AI_MODEL=gpt-4.1-mini
```

İsteğe bağlı ayarlar (`.env.example` içinde açıklamalı):

- `AI_MODEL` — Kullanılacak model
- `AI_MAX_OUTPUT_TOKENS` — Yanıt uzunluğu (512 varsayılan; uzun tarifler için artırın)
- `AI_TEMPERATURE` — Yanıt çeşitliliği (0.35 varsayılan)
- `NUTRICOACH_DB` — SQLite veritabanı yolu (varsayılan: `instance/nutricoach.db`)

---

## Testler

```bash
pytest
```

---

## Proje yapısı

```
Life_AI_asistan/
├── app.py              # Flask uygulaması ve API uçları
├── store.py            # SQLite (sohbetler, günlük takip)
├── requirements.txt    # Python bağımlılıkları
├── .env.example        # Ortam değişkenleri şablonu
├── templates/
│   └── index.html      # Ana arayüz
├── static/
│   ├── script.js       # İstemci mantığı
│   ├── style.css       # Stiller
│   ├── sw.js           # Service worker (PWA)
│   └── manifest.webmanifest
└── tests/
    └── test_app.py     # Birim testleri
```

---

## Kullanım ipuçları

- Sohbette **“kalori hesapla”** yazın → yaş, kilo, boy sorulur → günlük kalori ve örnek öğün planı
- Sohbette **“hedef planla”** yazın → hedef kilo ve aktivite seviyesine göre plan
- **Günlük takip** sekmesinden su, adım, beslenme ve antrenman kaydedin; AI haftalık/günlük özet üretebilir
- **BMI & analiz** sekmesinden boy/kilo girerek BMI hesaplayın

---

## Lisans

Bu proje eğitim ve kişisel kullanım amaçlıdır. Tıbbi tavsiye yerine geçmez; sağlık kararları için uzmanınıza danışın.
