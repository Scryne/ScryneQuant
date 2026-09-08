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
| 0 | Trading temeli + spike'lar | ⏳ Bekliyor | 12 kavramın vault notu + elle hesaplanmış örnek işlem + 3 spike raporu (K-015/016/017 kapandı) |
| 1 | Market data temeli | ⏳ Bekliyor | BTC/USDT ≥3 yıl indirilmiş, kalite raporu üretiliyor, indirme idempotent |
| 2 | İndikatör + strateji sözleşmesi | ⏳ Bekliyor | ≥6 indikatör referans değerle doğrulanmış; look-ahead testi ve import-izolasyon testi yeşil |
| 3 | Backtest motoru | ⏳ Bekliyor | Determinizm hash'le kanıtlı; maliyet modeli çalışıyor; elle hesaplanmış senaryoyla birebir uyuşuyor |
| 4 | Strateji laboratuvarı | ⏳ Bekliyor | 5 strateji ailesi; walk-forward + OOS; her sonuç reproduce edilebilir kayıtla |
| 5 | Risk motoru + promotion | ⏳ Bekliyor | Risk bypass edilemiyor (testle); kill switch çalışıyor; promotion kapıları uygulanıyor |
| 6 | Paper trading + dashboard | ⏳ Bekliyor | 30 gün kesintisiz; restart sonrası state doğru; 4 sayfalık dashboard ayakta |
| 7 | Execution sandbox (testnet) | ⏳ Bekliyor | Duplicate order üretilemiyor; reconciliation çalışıyor; testnet'te ≥100 emir hatasız |
| 8 | Kontrollü live | ⏳ Bekliyor | Promotion'u geçmiş ≥1 strateji, minimum sermaye, backtest-paper-live drift ölçülüyor |

---

## Faz Detayları

### Faz 0: Trading temeli + spike'lar

Bu faz **yazılım fazı değil.** Amacı, Proje-Fikri §53'ün dediği gibi, sistemi yanlış
modellememek. Atlanabilir görünen ama atlanırsa Faz 3'te sessiz hata olarak geri dönen tek
faz budur.

- **İşler:**
  - 12 kavramın her biri için ScryneOS vault'unda `🧠 500-Knowledge/` altına kısa not:
    candle, order türleri, long/short, spot vs futures, fee (maker/taker), spread, slippage,
    volatilite, drawdown, position sizing, risk/ödül, likidite.
  - **Elle bir işlem hesabı:** giriş, çıkış, taker fee iki bacakta, slippage dahil net P&L.
    Kalemle. Bu sayı Faz 3'te motorun doğruluğunun referansı olacak.
  - **Spike 1 (K-015):** CCXT ile Binance'e gerçek istek. Türkiye'den erişim, kimlik
    gereksinimi, rate limit, Spot Testnet'in güncel durumu. Çıktı: kısa rapor.
  - **Spike 2 (K-017):** BTC/USDT 1h ve 1m için 1 yıllık veri indirilip ölçülür — süre,
    dosya boyutu, bar sayısı. Birincil timeframe kararı buradan çıkar.
  - **Spike 3 (K-011):** ölçülen hacim Parquet'e yazılıp DuckDB ile sorgulanır; seçim
    doğrulanır ya da değiştirilir.
  - **Spike 4 (K-016):** Binance'in güncel spot komisyon tarifesi ve gerçekleşen spread
    gözlemi → K-007'nin sayıları doldurulur.
- **Bitti Kriteri:** 12 not yazılmış; elle P&L hesabı yapılmış; dört spike raporu
  `docs/spikes/` altında; K-015, K-016, K-017 `Kararlar.md`de `kabul` durumuna geçmiş.
- **Notlar:** Spike kodu atılacak koddur, `research/spikes/` altında yaşar ve production
  paketine taşınmaz.

### Faz 1: Market data temeli

- **İşler:** Exchange adapter arayüzü + Binance implementasyonu; tarihsel indirici
  (sayfalama, rate limit, kaldığı yerden devam); doğrulama (eksik bar, tekrar eden
  timestamp, OHLC tutarlılığı, sıfır hacim); kalite bayrakları (K-006); Parquet deposu
  (K-011); kalite raporu; CLI komutları.
- **Bitti Kriteri:**
  - BTC/USDT için ≥3 yıllık veri indirilmiş ve saklanmış.
  - `data quality` komutu boşluk/tekrar/şüpheli bar raporu üretiyor.
  - Aynı indirme komutu iki kez çalıştırıldığında dosya içeriği bit düzeyinde aynı
    (idempotent).
  - Tüm timestamp'ler UTC epoch ms, bar açılış zamanı (K-005) — test ile kanıtlı.
- **Notlar:**

### Faz 2: İndikatör + strateji sözleşmesi

Projenin en kritik fazı. Buradaki iki test (look-ahead, izolasyon) sonradan eklenemez.

- **İşler:** İndikatör motoru (SMA, EMA, RSI, ATR, Bollinger, hacim ortalaması — §8'den);
  `Strategy` ABC ve `ctx` sözleşmesi (K-002); `Signal` modeli (Pydantic); ilk strateji
  (SMA crossover) referans olarak.
- **Bitti Kriteri:**
  - Her indikatör bağımsız bir referans kaynağıyla (elle hesap veya bilinen kütüphane)
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
  - **Doğruluk:** elle hesaplanmış ≥10 işlemlik bir senaryo ile motorun çıktısı kuruşuna
    kadar uyuşuyor (Faz 0'daki elle hesap bunun temeli).
  - Her sonuç kaydında commit SHA, dirty bayrağı, veri hash'i, config hash'i, seed,
    kütüphane sürümleri var.
  - `ok` olmayan bar oranı sonuç kaydına yazılıyor (K-006).
- **Notlar:**

### Faz 4: Strateji laboratuvarı

Amaç kâr bulmak değil — strateji ailelerini bilimsel olarak karşılaştırmayı öğrenmek.

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
- **Notlar:** Testnet periyodik olarak sıfırlanabilir; testler buna dayanıklı yazılmalı.

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
- **Notlar:** Sermaye artırma kararı bu fazın çıktısına bakılarak verilir; fazın içinde
  değil. Drift beklenenden büyükse sermaye artmaz, Faz 3-4'e geri dönülür.
