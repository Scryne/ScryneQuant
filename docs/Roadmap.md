---
proje: ScryneQuant
created: 2026-09-08
type: roadmap
status: aktif
---
# ScryneQuant — Roadmap

Durum sütunu session-start hook'u tarafından otomatik okunur — format bozulmasın:
⏳ Bekliyor / 🔄 Devam Ediyor / ✅ Tamamlandı.

Bu roadmap `docs/Proje-Fikri.md` §61'in ilk somut hedefi üzerine kuruldu, §60'ın kapsamlı
tanımı üzerine değil. Fazlar §53'ün Phase 0-8'ini takip eder; farklar `docs/Kararlar.md`de.

**Faz geçiş kuralı:** bir faz, bitti kriterinin **tamamı** karşılanmadan kapanmaz. "Neredeyse
bitti" diye geçilen faz, sonraki fazın üstüne borç bırakır — ve bu projede o borç sessiz
yanlış sonuç olarak geri döner.

| Faz | Adı | Durum | Bitti Kriteri |
| --- | --- | --- | --- |
| 0 | Teknik doğrulama (spike'lar) | ✅ Tamamlandı | Dört spike raporu `docs/spikes/` altında; K-011/015/016/017 `kabul` durumuna geçmiş |
| 1 | Market data temeli | ✅ Tamamlandı | BTC/USDT 1h ≥5 yıl + 1m ≥3 yıl indirilmiş, kalite raporu üretiliyor, indirme idempotent, slippage kalibre |
| 2 | İndikatör + strateji sözleşmesi | ⏳ Bekliyor | ≥6 indikatör referans değerle doğrulanmış; look-ahead testi ve import-izolasyon testi yeşil |
| 3 | Backtest motoru | ⏳ Bekliyor | Determinizm hash'le kanıtlı; maliyet modeli çalışıyor; bağımsız referans fixture'ıyla birebir uyuşuyor |
| 4 | Strateji laboratuvarı | ⏳ Bekliyor | 5 strateji ailesi; walk-forward + OOS; her sonuç reproduce edilebilir kayıtla |
| 5 | Risk motoru + promotion | ⏳ Bekliyor | Risk bypass edilemiyor (testle); kill switch çalışıyor; promotion kapıları uygulanıyor |
| 6 | Paper trading + dashboard | ⏳ Bekliyor | 30 gün kesintisiz; restart sonrası state doğru; 4 sayfalık dashboard ayakta |
| 7 | Execution sandbox (testnet) | ⏳ Bekliyor | Duplicate order üretilemiyor; reconciliation çalışıyor; testnet'te ≥100 emir hatasız |
| 8 | Kontrollü live | ⏳ Bekliyor | Promotion'u geçmiş ≥1 strateji, minimum sermaye, backtest-paper-live drift ölçülüyor |

---

## Faz Detayları

### Faz 0: Teknik doğrulama (spike'lar) — ✅ kapandı 2026-09-08

Kod yazılan bir faz değil, **ölçüm yapılan** faz. Dört bilinmeyen de kapandı.

| Spike | Kapattığı karar | Sonuç | Rapor |
| --- | --- | --- | --- |
| 1 | K-015 | Coğrafi engel yok; rate limit darboğaz değil; testnet ayakta | `docs/spikes/01-binance-erisim.md` |
| 2 | K-017 | **Birincil timeframe 1h** | `docs/spikes/02-veri-hacmi.md` |
| 3 | K-011 | Parquet+zstd + DuckDB doğrulandı, değişiklik yok | `docs/spikes/03-parquet-duckdb.md` |
| 4 | K-016 | `fee_taker_bps = 10.0`; slippage → K-021 | `docs/spikes/04-maliyet-tarifesi.md` |

**Bitti kriteri karşılandı:** dört rapor da yerinde ve her biri gerçek ölçülmüş sayı içeriyor;
K-011, K-015, K-016, K-017 `kabul` durumunda; K-007'nin komisyon sayısı doğrulanmış değerle
dolu.

**Kapsam dışı bırakılan:** Faz 0'ın trading eğitimi kısmı K-018 ile kaldırıldı.

**Faz 0'ın ürettiği ve sonraki fazları bağlayan sonuçlar** — ayrıntısı `docs/Kararlar.md`
sonundaki "Faz 0'dan çıkan gereksinimler" tablosunda:

1. Kapanmamış bar depoya yazılmaz — **Faz 1 idempotency'sinin ön koşulu**.
2. Klines çağrısı her zaman `limit=1000`.
3. IPv4'e zorla veya kalıcı session kullan (aksi hâlde bağlantı başına +12 s).
4. Veri seti hash'i = Parquet dosyasının SHA-256'sı (yazım bit düzeyinde deterministik).
5. Kalite bayrakları yapay bozuk fixture ile test edilir — gerçek veride tek bozuk bar yok.
6. Testnet API anahtarı **Faz 7'nin**, canlı hesap + KYC + anahtar **Faz 8'in** ön koşulu.

**Bir karar düzeltildi:** K-020'nin slippage kalibrasyon yöntemi ölçümle çürütüldü, yerine
K-021 geçti. Ayrıntı: `docs/spikes/02-veri-hacmi.md` §4.

**Notlar:** Spike kodu atılacak koddur, `research/spikes/` altında yaşar (gitignore'da) ve
production paketine taşınmaz. Ham ölçüm çıktıları `research/spikes/out/` altında.

### Faz 1: Market data temeli — ✅ kapandı 2026-09-09

- **Kapsam (Faz 0'ın ölçümüyle netleşti):** BTC/USDT **1h, 5 yıl** (birincil, K-017) +
  **1m, 3 yıl** (yardımcı: slippage kalibrasyonu, fill gerçekçiliği, Faz 7). Projeksiyon:
  ~1,7 MB + ~43 MB parquet, ~8 dakika indirme.
- **İşler:** Exchange adapter arayüzü + Binance implementasyonu; tarihsel indirici
  (sayfalama, rate limit, kaldığı yerden devam); doğrulama (eksik bar, tekrar eden
  timestamp, OHLC tutarlılığı, sıfır hacim); kalite bayrakları (K-006); Parquet deposu
  (zstd, sembol/timeframe başına tek dosya — K-011); kalite raporu; CLI komutları;
  **slippage kalibrasyonu (K-021)**.
- **Faz 0'dan gelen bağlayıcı kurallar:** kapanmamış bar yazılmaz (`close_time <
  serverTime`); `limit=1000`; IPv4/kalıcı session; timeout ≥ 5 s + retry; indirme
  `data-api.binance.vision` üzerinden; `load_markets()` önbellekli.
- **Bitti Kriteri:**
  - BTC/USDT 1h için ≥5 yıllık, 1m için ≥3 yıllık veri indirilmiş ve saklanmış.
  - `data quality` komutu boşluk/tekrar/şüpheli bar raporu üretiyor.
  - Aynı indirme komutu iki kez çalıştırıldığında dosya içeriği bit düzeyinde aynı
    (idempotent). **Ön koşul:** kapanmamış bar yazılmıyor — Spike 1 bu barın çağrılar
    arasında değiştiğini ölçtü, atılmazsa idempotency imkânsız.
  - Tüm timestamp'ler UTC epoch ms, bar açılış zamanı (K-005) — test ile kanıtlı.
  - **`slippage_bps` kalibre edilmiş** (K-021): yürütme penceresindeki fiyat hareketi
    dağılımı kullanılacak veri aralığı üzerinde hesaplanmış, muhafazakâr persentil
    **gerekçesiyle birlikte** kaydedilmiş; geçici 5.0 değeri kaldırılmış.
  - **Kalite bayrakları yapay bozuk fixture ile test edilmiş** (K-006): Spike 2 gerçek
    veride tek bozuk bar bulamadı; `gap`/`duplicate`/`suspect` kod yolları aksi hâlde hiç
    çalıştırılmamış olur.
- **Notlar:** Faz 0'ın ölçtüğü indirme hızı (~3.500 bar/s, ağ sınırlı) bu fazın süre
  beklentisidir; rate limit zorlanmayacak.

**Bitti kriteri karşılandı — ölçümlerin tamamı `docs/Faz-1-Veri-Raporu.md`'de:**

| Kriter | Sonuç |
| --- | --- |
| 1h ≥5 yıl | ✅ 5,2 yıl · 45.576 bar · 2,08 MB |
| 1m ≥3 yıl | ✅ 3,1 yıl · 1.630.476 bar · 63,61 MB |
| `data quality` raporu | ✅ boşluk/tekrar/şüpheli bar raporu üretiyor (`sq data quality`) |
| İdempotent indirme | ✅ ikinci çalıştırma 0 bar indiriyor, sha256 aynı |
| UTC epoch ms, bar açılışı (K-005) | ✅ testle kanıtlı; hizasız timestamp hata veriyor |
| `slippage_bps` kalibre (K-021) | ✅ **5,2996 bps** (p75), gerekçesiyle kaydedildi; geçici 5,0 kalktı |
| Kalite bayrakları bozuk fixture ile test edilmiş (K-006) | ✅ `tests/unit/test_dogrulama.py` — her kural için ayrı vaka |

**Faz 1'in verdiği kararlar:** K-023 (klines ccxt'nin ham ucundan), K-024 (bayrak tekildir,
boşluk uydurulmaz), K-025 (maliyet konfigürasyonu ve geçici model bayrağı). K-021 kapandı.

**Beklenmeyen bulgu:** Spike 2 "gerçek veride anomali yok" demişti; 3 yıl yerine 5,2 yıla
bakılınca **3 boşluk (7 eksik bar) ve 1 `suspect` bar** çıktı — 2023-03-24'teki Binance
kesintisi. Bayraklar ölü kod değilmiş, spike'ın penceresi dardı. Ayrıntı: Faz 1 raporu §2.

**Üretilen paketler:** `exchange/` (adaptör sözleşmesi + Binance), `data/` (indirici,
doğrulama, kalibrasyon, depo), `common/maliyet.py`, `cli/` (`sq data indir|quality|ls|
slippage-kalibre|maliyet`, `sq bilgi`).

### Faz 2: İndikatör + strateji sözleşmesi

Projenin en kritik fazı. Buradaki iki test (look-ahead, izolasyon) sonradan eklenemez.

- **İşler:** İndikatör motoru (SMA, EMA, RSI, ATR, Bollinger, hacim ortalaması — §8'den);
  `Strategy` ABC ve `ctx` sözleşmesi (K-002); `Signal` modeli (Pydantic); ilk strateji
  (SMA crossover) referans olarak.
- **Bitti Kriteri:**
  - Her indikatör bağımsız bir referansla (bilinen kütüphane veya sabitlenmiş fixture)
    karşılaştırılıp doğrulanmış.
  - **Look-ahead testi yeşil:** `t` sonrası veri bozulduğunda backtest çıktısı bit düzeyinde
    değişmiyor (K-002).
  - **İzolasyon testi yeşil:** `strategy/` paketinin import grafiğinde yasaklı bağımlılık
    yok (K-003).
- **Notlar:**

### Faz 3: Backtest motoru

- **İşler:** Event loop; fill modeli (K-004); maliyet modeli (K-007); portföy simülasyonu;
  metrikler (§17: getiri, Sharpe, max drawdown, win rate, profit factor, işlem sayısı,
  ortalama tutma süresi); equity curve; trade listesi; çalıştırma kaydı (K-009).
- **Bitti Kriteri:**
  - **Determinizm:** aynı veri + config + seed ile iki çalıştırmanın sonuç hash'i aynı.
  - **Doğruluk:** ≥10 işlemlik bir referans senaryonun beklenen P&L'i motordan bağımsız
    olarak hesaplanıp `tests/fixtures/` altına sabitlenmiş, ve motorun çıktısı bu değerle
    kuruşuna kadar uyuşuyor. Referans motorun kendi çıktısından türetilemez — türetilirse
    test hiçbir şey kanıtlamaz.
  - Her sonuç kaydında commit SHA, dirty bayrağı, veri hash'i, config hash'i, seed,
    kütüphane sürümleri var.
  - `ok` olmayan bar oranı sonuç kaydına yazılıyor (K-006).
- **Notlar:**

### Faz 4: Strateji laboratuvarı

Amaç kâr bulmak değil — strateji ailelerini aynı veri ve aynı maliyet varsayımlarıyla
bilimsel olarak karşılaştırmak.

- **İşler:** 5 strateji ailesi (SMA/EMA crossover, RSI mean reversion, breakout, momentum,
  multi-factor); parametre taraması; walk-forward; out-of-sample ayrımı; Monte Carlo;
  deney kaydı ve karşılaştırma; stres testi (§15.1).
- **Bitti Kriteri:**
  - 5 aile de aynı veri ve aynı maliyet varsayımlarıyla çalıştırılmış, sonuçlar yan yana.
  - Her strateji için in-sample / out-of-sample sonuçları ayrı raporlanıyor.
  - Walk-forward çalışıyor ve parametre kararlılığı görülebiliyor.
  - Herhangi bir deney, kaydından yeniden üretilebiliyor (kanıt: rastgele seçilen bir deney
    yeniden çalıştırılıp hash'i doğrulanır).
- **Notlar:** Bu fazın çıktısı büyük ihtimalle "hiçbiri maliyetlerden sonra anlamlı değil"
  olacaktır. **Bu bir başarısızlık değil, sistemin çalıştığının kanıtıdır.**

### Faz 5: Risk motoru + promotion

- **İşler:** Position sizing; exposure limiti; günlük zarar limiti; drawdown limiti;
  cooldown; volatilite guard; kill switch (K-008); SAFE_MODE; promotion kapıları (K-010);
  PostgreSQL şeması ve audit log.
- **Bitti Kriteri:**
  - Risk motoru atlanamıyor — bir sinyalin risk onayı olmadan execution'a ulaşamayacağı
    testle kanıtlı.
  - Her limit için ihlal senaryosu testi var ve doğru davranıyor.
  - Kill switch tetiklendiğinde K-008'deki beş davranışın hepsi gerçekleşiyor.
  - Promotion kapıları uygulanıyor; `dirty` veya `data_quality_warning` işaretli sonuç
    kapıdan geçemiyor.
- **Notlar:**

### Faz 6: Paper trading + dashboard

- **İşler:** WebSocket ile gerçek zamanlı veri; stale-data guard (§24); canlı sinyal
  üretimi; simüle emir ve pozisyon takibi; gerçek zamanlı risk kontrolü; FastAPI; 4 sayfalık
  dashboard (Overview, Strategies, Positions, Logs) — K-012; DESIGN.md'nin token'ları bu
  fazda doldurulur.
- **Bitti Kriteri:**
  - 30 gün kesintisiz çalışma (kesinti olduysa sebebi kayıtlı ve giderilmiş).
  - Süreç öldürülüp yeniden başlatıldığında pozisyon ve emir state'i doğru toparlanıyor.
  - Veri akışı kesildiğinde yeni pozisyon açılmıyor (stale-data guard testi).
  - Dashboard'un 4 sayfası çalışıyor ve risk durumu ilk bakışta görülüyor.
- **Notlar:** Frontend'e başlamadan önce global `~/.claude/CLAUDE.md`'deki araç sırası
  izlenir ve `DESIGN.md` doldurulur.

### Faz 7: Execution sandbox (Binance Spot Testnet)

- **İşler:** Emir state machine (§33); idempotency key; retry ve timeout politikası;
  reconciliation (§25); execution engine; gerçek adapter üzerinden testnet emirleri.
- **Bitti Kriteri:**
  - Aynı intent iki kez gönderildiğinde tek emir oluşuyor (duplicate order üretilemiyor).
  - Süreç emir gönderiminin ortasında öldürüldüğünde, yeniden başlayınca borsadaki gerçek
    durumla local state uyuşuyor (reconciliation).
  - Testnet'te ≥100 emir, elle müdahale gerektiren hata olmadan tamamlanmış.
  - Uyuşmazlık tespit edildiğinde sistem işlem yapmayı durduruyor (halt), tahmin yürütmüyor.
- **Ön koşul (Faz 0'dan):** `testnet.binance.vision` üzerinden **testnet API anahtarı
  alınmış** olmalı (GitHub hesabıyla, KYC gerektirmez). Ayrıca clock-drift kontrolü
  çalışıyor olmalı — fark +1000 ms'i aşarsa imzalı istekler sessizce reddedilir (Spike 1'de
  ölçülen: −153 ms).
- **Notlar:** Testnet periyodik olarak sıfırlanabilir; testler buna dayanıklı yazılmalı.
  Spike 1'de testnet'in canlı fiyatı %0,007 sapmayla takip ettiği ölçüldü — execution
  testleri için gerçekçi.

### Faz 8: Kontrollü live

Bu faz **para kazanma fazı değildir.** Amacı §45'in ölçtüğü şeyi ölçmek: backtest, paper ve
live arasındaki gerçek operasyon farkı.

- **İşler:** Minimum sermaye; en sıkı risk limitleri; tek sembol; tek strateji; drift ölçümü;
  günlük gözden geçirme.
- **Bitti Kriteri:**
  - Promotion zincirinin tamamını geçmiş ≥1 strateji live'da.
  - En az 30 gün çalışmış ve backtest/paper/live sonuçları arasındaki fark ölçülüp
    raporlanmış.
  - Kill switch canlıda en az bir kez **kasıtlı olarak** test edilmiş ve doğru davranmış.
  - Uzlaşmazlık, duplicate emir veya açıklanamayan pozisyon farkı sayısı: **sıfır.**
- **Ön koşul (Faz 0'dan):** Canlı Binance hesabı açılmış, KYC tamamlanmış, spot işlem
  yetkili API anahtarı üretilmiş olmalı. **Spike 1'in kimlik doğrulama kısmı bu gerçek
  anahtarla tekrarlanır** — bugünkü kanıt "yol açık" der, "hesap çalışıyor" demez.
- **Notlar:** Sermaye artırma kararı bu fazın çıktısına bakılarak verilir; fazın içinde
  değil. Drift beklenenden büyükse sermaye artmaz, Faz 3-4'e geri dönülür.
