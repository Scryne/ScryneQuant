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
| 2 | İndikatör + strateji sözleşmesi | ✅ Tamamlandı | ≥6 indikatör referans değerle doğrulanmış; look-ahead testi ve import-izolasyon testi yeşil |
| 3 | Backtest motoru | ✅ Tamamlandı | Determinizm hash'le kanıtlı; maliyet modeli çalışıyor; bağımsız referans fixture'ıyla birebir uyuşuyor |
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

### Faz 2: İndikatör + strateji sözleşmesi — ✅ kapandı 2026-09-09

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

**Bitti kriteri karşılandı:**

| Kriter | Sonuç |
| --- | --- |
| ≥6 indikatör bağımsız referansla doğrulanmış | ✅ **6 indikatör** (SMA, EMA, RSI, ATR, Bollinger, hacim ortalaması) + `true_range`; referans **TA-Lib 0.7.1**, 4 vaka × 40 sütun `tests/fixtures/indikator_referans.json`'da dondurulmuş (K-026) |
| Look-ahead testi yeşil | ✅ `tests/unit/test_look_ahead.py` — `t` sonrası bozulunca sinyaller bit düzeyinde aynı; 3 bozma × 5 kesme noktası |
| İzolasyon testi yeşil | ✅ `tests/unit/test_izolasyon.py` — geçişli import grafiği, izin listesi (K-027) |

**Üretilen paketler:** `features/` (`indikator.py` saf numpy indikatörler, `motor.py`
bildirimsel özellik motoru, `barlar.py` pandas sınırı), `strategy/` (`baglam.py` = `ctx`,
`sinyal.py` = Pydantic `Sinyal`, `temel.py` = `Strateji` ABC, `kosu.py` ince sürücü,
`kutuphane/sma_kesisim.py` referans strateji), `tools/referans_uret.py`.

**`ctx`'in tasarım kararı:** geleceğe erişim yasaklanmadı, **ifade edilemez** kılındı.
İndeks yönü ters çevrildi — `ctx.bar("close", 1)` bir önceki bar, `geri=-1` ise bir hata
(`GelecekErisimi`), bir seçenek değil. Mutlak indeks verilseydi `t+1` yazmak mümkün,
dolayısıyla er ya da geç kaçınılmaz olurdu. Seri erişimleri kopya döndürür: dilim
döndürmek `.base` üzerinden tüm seriye — yani geleceğe — bir yol bırakırdı.

**Faz 2'nin verdiği kararlar:** K-026 (indikatör konvansiyonu TA-Lib; referans
dondurulmuş; hareketsiz seride RSI için tek bilinçli sapma), K-027 (izolasyon izin
listesiyle zorlanır, geçişli, statik, öz-testli).

**Beklenmeyen bulgular — ikisi de testlerin *kendi* testleri sayesinde çıktı:**

1. **Rastgele bozma tek başına look-ahead'i yakalamıyor.** İlk yazılan negatif kontrol
   (kasten geleceğe bakan `HileliStrateji`) rastgele bozmayla **geçti** — çünkü bir bar
   ileri bakan hile yalnızca kesme noktasındaki tek sinyali etkiler ve rastgele bir
   fiyatın o kararı gerçekten çevirmesi yazı-turadır. Çözüm: iki yönlü **sabit** bozma
   (çok yüksek / çok düşük) eklendi; hangi yöne bakan hile olursa olsun ikisinden biri
   kararı çevirir. Testin gücü artık olasılıksal değil, yapısal.
2. **İzolasyon tarayıcısında iki hata vardı.** Öz-test (sahte pakette `a → ara → socket`
   zinciri) tarayıcının kök paket adını sabit kodladığını ve `__init__.py`'yi yanlış
   modül adına eşlediğini gösterdi. İkisi de düzeltildi; öz-test bedelini ilk gün ödedi.
3. **TA-Lib düz seride RSI olarak `0.0` veriyor** — azami aşırı satım, yani hareketsiz
   bir piyasadan gelen en güçlü alım sinyali. K-026/4 ile bilinçli olarak NaN'a çevrildi.

**Ölçüm:** gerçek BTC/USDT 1h verisinde (45.576 bar) özellik hesabı 0,002 s, strateji
döngüsü 0,26 s (~177.000 bar/s), 1.087 sinyal; iki koşunun sinyal hash'i aynı.

- **Notlar:** İndikatör motoru `research/`e değil `src/scryne_quant/features/`e yazıldı ve
  Faz 4'ün diğer strateji aileleri (breakout, momentum) yeni indikatör isterse **deftere**
  (`features/motor.py:DEFTER`) eklenir; kayıtsız indikatör tanım olarak kabul edilmez.

### Faz 3: Backtest motoru — ✅ kapandı 2026-09-09

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

**Bitti kriteri karşılandı:**

| Kriter | Sonuç |
| --- | --- |
| Determinizm hash'le kanıtlı | ✅ `Sonuc.sonuc_hash` (çıktı) + `config_hash` (girdi); aynı veri+config iki koşuda aynı, farklı config farklı — negatif kontrolüyle birlikte |
| Bağımsız referansla birebir uyuşuyor | ✅ **12 turluk** senaryo, `Decimal` (50 basamak) defter + **kapalı formül** çapraz doğrulaması; motorla bağıl fark <1e-12 (K-029) |
| Referans motordan türetilmemiş | ✅ üretici `scryne_quant`ı import etmiyor — `ast` ile taranıyor, söz değil kısıt |
| Kayıtta commit/dirty/veri hash/config hash/seed/kütüphane sürümleri | ✅ `Sonuc.sozluk()["kimlik"]`, testle sabitlenmiş |
| `ok` olmayan bar oranı kayıtta (K-006) | ✅ sayı, oran ve bayrak başına dağılım; eşiği aşınca `data_quality_warning` |

**Üretilen paketler:** `backtest/` (`fill.py` K-004/K-007 fill ve boyutlandırma, `motor.py`
event loop, `metrikler.py` 29 metrik + işlem defteri, `sonuc.py` K-009 kaydı),
`portfolio/durum.py` (değişmez portföy, spot değişmezleri), `tools/backtest_referans_uret.py`,
CLI: `sq backtest`.

**Faz 3'ün verdiği kararlar:** K-028 (`ok` olmayan barda ne karar ne fill; atlanan sinyal
sayılır), K-029 (referans kapalı formülle çapraz doğrulanır, üretici motoru import edemez).

**Ölçüm — BTC/USDT 1h, 5,2 yıl, 45.576 bar, SMA(20/50), %90 hedef maruziyet:**

| | |
| --- | --- |
| Koşu süresi | 0,35 s |
| İşlem | 543 (165 kazanç / 378 kayıp), win rate %30,4 |
| Toplam getiri | **−%58,61** (CAGR −%15,61) |
| Sharpe / Sortino / Calmar | −0,373 / −0,277 / −0,213 |
| Max drawdown | %73,37 |
| Profit factor | 0,864 |
| Komisyon + slippage | 6.465 + 3.426 = **9.891 USDT** |

**Bu tablonun en önemli satırı sonuncusu.** 10.000 USDT'lik sermayeyle yapılan koşuda
ödenen toplam maliyet 9.891 USDT — yani **başlangıç sermayesinin tamamı kadar.** Strateji
brüt olarak neredeyse başabaş (profit factor 0,864); zararın tamamına yakınını 543 işlemin
maliyeti üretiyor. K-017'nin timeframe kararını veren hareket/maliyet oranı burada somut
sayıya döndü, ve K-007'nin "maliyet varsayımı stratejinin bir parçasıdır, dipnot değil"
cümlesi tam olarak bunu kastediyordu.

Roadmap Faz 4 notu bu sonucu zaten öngörüyordu: **bu bir başarısızlık değil, sistemin
çalıştığının kanıtı.** Maliyetleri gizleyen bir motor aynı stratejiyi kârlı gösterirdi.

**Beklenmeyen bulgular:**

1. **Kendi yazdığım K-004 testi hiçbir şey kanıtlamıyordu.** Fill barının açılışı ile
   kapanışı aynı sayı seçilmişti, dolayısıyla "kapanıştan doldur" mutasyonu testi
   kırmıyordu — mutasyon testi yakaladı. Vaka dört olası fiyatın dördü de farklı olacak
   şekilde yeniden yazıldı. Yeşil ama boş bir test, testsizlikten daha kötüdür: koruma
   sanılır.
2. **CAGR kısa pencerede `OverflowError` fırlatıyordu.** 3 barlık bir koşuda üs 2.922
   oluyor ve `(1,5)**2922` taşıyor. Log uzayına taşındı ve tavana kırpıldı; ayrıca
   `Metrikler.yillik_anlamli` bayrağı eklendi (pencere ≥30 gün mü). Bu, Faz 4'ün kısa
   walk-forward katmanlarında kesin patlardı.
3. **Referans testi üç kasıtlı bozmayı da yakalıyor:** slippage yönü ters (10 test),
   fill kapanışa kaymış (3), tek bacakta komisyon unutulmuş (8).

- **Notlar:** Sonuç kayıtları `runs/` altına yazılıyor (gitignore'da), dosya adı
  `<config_hash>-<sonuc_hash>` — aynı deneyin iki kez çalıştırılması aynı dosyayı üretir.
  `Sonuc.promotion_engelleri` K-010'un Faz 5'te uygulayacağı kapının okuyacağı listeyi
  şimdiden üretiyor; bugün üç engel tanınıyor: `dirty` (K-009), `data_quality_warning`
  (K-006), `gecici_maliyet_modeli` (K-021).

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
