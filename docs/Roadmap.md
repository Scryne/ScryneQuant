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

**v2 eki (2026-09-12, K-048).** `docs/Proje-Fikri-v2.md` kapsamı genişletti; roadmap
**numaralandırma değiştirmeden** genişledi: Faz 0-8 olduğu yerde duruyor (kararlar, raporlar
ve commit'ler onlara referans veriyor), v2'nin işleri Faz 9-16 olarak eklendi. Dokümanın
kendi faz numaralarıyla eşleme `docs/Denetim-v2.md` §0.4'te.

**Faz geçiş kuralı:** bir faz, bitti kriterinin **tamamı** karşılanmadan kapanmaz. "Neredeyse
bitti" diye geçilen faz, sonraki fazın üstüne borç bırakır — ve bu projede o borç sessiz
yanlış sonuç olarak geri döner.

| Faz | Adı | Durum | Bitti Kriteri |
| --- | --- | --- | --- |
| 0 | Teknik doğrulama (spike'lar) | ✅ Tamamlandı | Dört spike raporu `docs/spikes/` altında; K-011/015/016/017 `kabul` durumuna geçmiş |
| 1 | Market data temeli | ✅ Tamamlandı | BTC/USDT 1h ≥5 yıl + 1m ≥3 yıl indirilmiş, kalite raporu üretiliyor, indirme idempotent, slippage kalibre |
| 2 | İndikatör + strateji sözleşmesi | ✅ Tamamlandı | ≥6 indikatör referans değerle doğrulanmış; look-ahead testi ve import-izolasyon testi yeşil |
| 3 | Backtest motoru | ✅ Tamamlandı | Determinizm hash'le kanıtlı; maliyet modeli çalışıyor; bağımsız referans fixture'ıyla birebir uyuşuyor |
| 4 | Strateji laboratuvarı | ✅ Tamamlandı | 5 strateji ailesi; walk-forward + OOS; her sonuç reproduce edilebilir kayıtla |
| 5 | Risk motoru + promotion | ✅ Tamamlandı | Risk bypass edilemiyor (testle); kill switch çalışıyor; promotion kapıları uygulanıyor |
| 6 | Paper trading + dashboard | ✅ Tamamlandı | Restart sonrası state doğru; bayat veri guard'ı; 4 sayfalık dashboard ayakta (30 günlük koşu kriteri K-055 ile Faz 8/14'e taşındı) |
| 7 | Execution sandbox (testnet) | ✅ Tamamlandı | Duplicate order üretilemiyor; reconciliation çalışıyor; testnet'te ≥100 emir hatasız |
| 8 | Kontrollü live (tetiklemeli) | ⏳ Bekliyor | Promotion'u geçmiş ≥1 strateji, minimum sermaye, backtest-paper-live drift ölçülüyor |
| 9 | Veri platformu v2 (PIT + evren + kimlik) | ✅ Tamamlandı | Delist dahil çoklu sembol indirilmiş; PIT evren tablosu üretiliyor; kimlik kırılması yakalanıyor; `available_time` kesmesi testli |
| 10 | Çok enstrümanlı araştırma çekirdeği | ⏳ Bekliyor | Tek enstrüman özel hâlde bit düzeyinde aynı; çok enstrümanlı bağımsız referans tutuyor; evren look-ahead testi yeşil |
| 11 | Doğrulama v2 | ⏳ Bekliyor | Dört yeni kapı hesaplanıyor, eşikleri gerekçeyle sabit; mevcut 38 çekiliş yeni kapılardan geçirilmiş |
| 12 | Araştırma programları (cross-sectional, türev, makro) | ⏳ Bekliyor | Her program bütçesi içinde kapanmış, raporlanmış; defter büyümesi sonrası eşik yeniden ölçülmüş |
| 13 | Haber/olay zekâsı + ML (koşullu) | ⏳ Bekliyor | Açılma koşulu: veri bütçesi kararı + kaynak spike'ı. Açılırsa: LLM kesim tarihi kayıtlı, `leak_riski` uygulanıyor |
| 14 | Üretim sertleştirme | ⏳ Bekliyor | Süreç dışı kill switch testnet'te kanıtlı; dört gözlem boyutu ayakta; her alarmın runbook'u var; toparlanma tatbikatı yapılmış |
| 15 | İkinci varlık sınıfı (US equities/ETF) | ⏳ Bekliyor | Açılma koşulu: broker/lisans spike'ı. Açılırsa: aynı kod yolu ikinci varlık sınıfında paper koşuyor |
| 16 | Sürekli araştırma | ⏳ Bekliyor | Kapanmaz; her tur bir program kaydı ve bir rapor bırakır |

**Faz 8 sıraya değil tetiklenmeye bağlıdır.** Promotion zincirini geçen ilk strateji
çıktığında başlar — hangi fazda olunursa olunsun. Ön koşulları (süreç dışı kill switch,
hukuki doğrulama, canlı hesap/KYC, shadow adımı, kademeli sermaye tablosu) Faz 8
bölümünde.

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

### Faz 4: Strateji laboratuvarı — ✅ kapandı 2026-09-09

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

**Bitti kriteri karşılandı — ayrıntılı ölçümler `docs/Faz-4-Laboratuvar-Raporu.md`'de:**

| Kriter | Sonuç |
| --- | --- |
| 5 aile aynı veri ve aynı maliyetle, sonuçlar yan yana | ✅ `sq lab karsilastir` — 5 aile (6 strateji) + al-tut kıyası, aynı dosya/SHA-256/maliyet/sermaye |
| Her strateji için IS / OOS ayrı raporlanıyor | ✅ kronolojik %70/%30 bölme; parametre yalnızca IS'te seçiliyor |
| Walk-forward çalışıyor, parametre kararlılığı görülebiliyor | ✅ 16 katman (1 yıl eğitim / 3 ay test); `parametre_kararliligi()` katman başına seçilen değerleri, benzersiz sayısını ve değişim katsayısını raporluyor |
| Herhangi bir deney kaydından yeniden üretilebiliyor | ✅ `sq lab dogrula` — beş deney tipi de yeniden üretilip çıktı hash'i doğrulandı |

**Üretilen paketler:** `research/` (`bolme`, `tarama`, `walkforward`, `analiz`,
`karsilastirma`, `izgaralar`, `kapilar`, `degerlendirme`, `deney`, `tekrar`),
`strategy/kutuphane/` (5 aile + al-tut kıyası), 3 yeni indikatör (`en_yuksek`, `en_dusuk`,
`roc` — TA-Lib'e karşı doğrulandı, K-026), CLI: `sq lab {stratejiler,tara,walkforward,
montecarlo,stres,karsilastir,kapilar,deneyler,dogrula}`.

**Faz 4'ün verdiği kararlar:** **K-019 kapandı** (promotion kapılarının yedi sayısal
eşiği — projenin son açık kararıydı), K-030 (her karşılaştırmada al-tut kıyası bulunur),
K-031 (strateji sinyalinin kabul edildiğini varsayamaz).

**Ölçüm — BTC/USDT 1h, 45.576 bar, 5,2 yıl:**

| Strateji | IS Sharpe | OOS Sharpe | OOS/IS | WF bileşik getiri | WF Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: |
| **al_tut (kıyas)** | +0,70 | −0,27 | −0,39 | **+39,0 %** | **+0,86** |
| donchian | +0,75 | −0,35 | −0,46 | +14,4 % | +0,61 |
| sma_kesisim | +0,62 | −1,03 | −1,67 | +14,7 % | +0,53 |
| rsi_donus | +0,45 | −0,85 | −1,89 | +7,1 % | +0,27 |
| momentum | +0,91 | −0,08 | −0,09 | +3,7 % | +0,18 |
| ema_kesisim | +0,65 | −0,46 | −0,70 | −1,7 % | −0,03 |
| cok_faktor | +0,23 | −0,95 | −4,15 | −4,1 % | −0,12 |

**Roadmap'in bu faz için yazdığı not doğrulandı.** Altı stratejinin **altısında da**
in-sample Sharpe pozitif, out-of-sample Sharpe negatif — ders kitabı overfitting tablosu.
Walk-forward'da dördü pozitife dönüyor ama **hiçbir şey yapmayan al-tut kıyası hepsini
geçiyor** (+%39,0 / Sharpe 0,86). Aktif yönetimin bu veride yaptığı tek şey 155-287 işlemin
maliyetini ödemek oldu.

**K-019 kapıları uygulandı: 7 stratejinin 7'si de kaldı** (`sq lab kapilar`). Eşikler
bugünkü sonuca göre gevşetilmedi; gevşetilseydi kapı kaldırılmış olurdu.

**Beklenmeyen bulgular:**

1. **Kıyasın tek sinyali ısınma penceresinde yutuldu.** `al_tut`un `_girildi` bayrağı
   ısınma barında kalkıyor, o barın sinyali ölçüm penceresine girmediği için atılıyor, ve
   strateji bir daha hiç sinyal üretmiyordu. Kıyas tabloda **%0,0 getiri** olarak göründü —
   çökme yok, uyarı yok. K-031 bu hata sınıfını kapatıyor ve Faz 5'te risk motoru sinyal
   reddetmeye başlayınca çok daha sık karşılaşılacaktı.
2. **Walk-forward, tek bölmenin tersini söyledi.** IS/OOS'ta altısı da negatifken
   walk-forward'da dördü pozitif. Aynı veri, farklı pencere — tek bir OOS testine
   güvenmemek için somut gerekçe.
3. **Monte Carlo: bazı stratejilerin geçmiş düşüşü şanslıydı.** `rsi_donus` ve `donchian`
   için gerçekleşen düşüş, olası sıralamaların yalnızca %15'inden derindi. "Geçmişte %10
   düştü" cümlesi "en fazla %10 düşer" demek değil.
4. **Sentetik test verisi momentum eşikleri için fazla sakin.** `bar_uret` bar başına
   ~%0,08 oynaklık üretiyor, gerçek BTC 1h bunun ~10 katı; `momentum` sentetik seride tek
   sinyal üretmedi ve bozuk görünüyordu.

- **Notlar:** Bu fazın çıktısı büyük ihtimalle "hiçbiri maliyetlerden sonra anlamlı değil"
  olacaktır. **Bu bir başarısızlık değil, sistemin çalıştığının kanıtıdır.** — *Ölçüldü,
  öyle çıktı.* Faz 5-8 bu tabloyu değiştirmiyor: sistemin işi cevabı ölçmekti ve ölçtü.
  Sermaye artırma veya live'a geçme kararı bu tabloya bakılarak verilmez.

**Faz 4'e dönüş 1 (2026-09-11): timeframe hipotezi — çürütüldü.** Roadmap'in geri besleme
kuralı gereği burada kayıtlı. 4h ve 1d indirildi, hipotezler önceden kaydedildi (K-039).
Mekanizma **çalıştı**: 1h'te altı stratejinin altısı da OOS'ta negatifken 4h'te iki kesişim
ailesi pozitife döndü (+0,39 / +0,32), üstelik kıyasın negatif olduğu bir pencerede. Ama
yetmedi ve **kendi ayağına bastı**: timeframe'i uzatmak işlem sayısını 4 kat düşürdü, yani
`asgari_islem ≥ 30` kapısı düştü. 1d ise walk-forward'ı hiç tamamlayamadı — 1.936 bar
istatistiksel güç tabanının altında. Kapılardan geçen yok, eşikler değişmedi. Ayrıntı:
`docs/Faz-4-Donus-1-Timeframe.md`.

**Faz 4'e dönüş 2 (2026-09-11): parametre seçim yöntemi — çürütüldü.** Dönüş 1'in
bulgusu üzerine: `oos_is_orani` her stratejide, her timeframe'de düşüyordu, yani sorun aile
seçiminde değil **parametre seçiminde** olabilirdi. `en_iyi` saf argmax ve bir platonun
tepesi tanımı gereği o platonun gürültü en çok lehe çalışan noktasıdır. Plato **merkezi**
seçimi eklendi (`tarama.plato_merkezi`) ve ön kayıtla koşturuldu (hipotez 22-35). Sonuç:
değişen altı vakanın **beşinde kötüleşti**, birinde iyileşti. Hipotez çürüdü; önceden
yazılmış koşul gereği üçüncü bir seçim yöntemi denenmiyor. En yakına gelen `cok_faktor`
4h/plato (OOS Sharpe 0,46 · eşik 0,50) ama üç kapıda daha düşüyor — ve 35 çekilişten biri.
Ayrıntı: `docs/Faz-4-Donus-2-Secim.md`.

**Faz 4'e dönüş 3 (2026-09-11): funding rate — çürütüldü.** İlk kez **farklı bir bilgi
kaynağı** denendi: fiyat geçmişi değil, türev piyasasının konumlanması. Spike 5 dört adayı
ölçtü ve üçünü eledi (open interest, long/short oranı, taker hacmi — Binance'te ~31 gün
saklanıyor, walk-forward kurulamaz); geriye funding rate kaldı (7,01 yıl, sıfır boşluk).
Üç hipotez ön kayıtla yazıldı (defter 36-38), üçü de kapılarda kaldı ve **K-042'nin durma
kuralı gereği funding fikri kapandı** — dördüncü aile yok.

Ama tablo Faz 4'ten beri görülmemiş bir şey içeriyor: `funding_egilim` projenin **ilk
pozitif OOS Sharpe**'ını üretti (**+0,288**; önceki en iyi −0,348) ve yedi kapının dördünü
geçti. Üç kapıda kaldı, en belirleyicisi `asgari_islem` **24 < 30** — dönüş 1'in tuzağının
aynısı: 24 işlemle ölçülen bir Sharpe'a güvenilmez.

`funding_filtre`nin mekanizması **ölçülebilir biçimde çalıştı**: aynı donchian kanalına tek
bir funding koşulu eklemek OOS Sharpe'ı −0,348'den −0,094'e, OOS/IS oranını −0,439'dan
−0,112'ye taşıdı, stres kapısını geçirdi — ve **işlem sayısını hiç düşürmedi** (56 → 56).
Yani filtre elediği kırılımların yerine başkasını koymadı, sadece kötülerini eledi.
Kalabalıklaşma, OOS çöküşünün bir parçasını açıklıyor; tamamını değil.

**Izgara genişletilmedi, dördüncü aile denenmedi, 4h tekrarlanmadı.** Üçü de cazipti ve üçü
de K-042'nin sonucu görmeden yasakladığı şeydi: çekiliş sayısına sonucu gördükten sonra
karar vermek. Ayrıntı: `docs/Faz-4-Donus-3-Funding.md`.

**Faz 4'e dönüş 4 (2026-09-11): çoklu test düzeltmesi — K-039'un açık maddesi kapandı.**
Bu dönüş yeni bir hipotez **denemedi**; ölçülen şey kapının kendisiydi. Defterdeki 31
ölçülebilir çekiliş, edge'i olmayan bir dünyada yeniden koşturuldu (sinyal takvimi dairesel
kaydırılıp gerçek motordan geçirildi; kaydırma iterasyon başına paylaşıldı ki stratejiler
arası korelasyon bozulmasın).

Sonuç: **`oos_sharpe` kapısı 0,50 → 1,02** (K-044). Eski eşiğin gerçek yanlış-pozitif oranı
**%26,3**'tü — yani 0,50 hiçbir zaman %5'lik bir kapı değildi. Bağımsız çapraz kontrol
(Deflated Sharpe) 0,92 veriyor, Bonferroni 1,30 — ikisinin arasında kalması beklenen yerde.

**Asıl bulgu eşik değil:** projenin en iyi sonucu (`cok_faktor` 4h/plato, OOS Sharpe 0,4585)
**şans beklentisinin altında**; p-değeri 0,296. 31 çekilişin Sharpe dağılımı ortalama −0,31,
yalnızca 7'si pozitif. Ayrıntı: `docs/Faz-4-Donus-4-Coklu-Test.md`.

**Eşik bir sabit değil, defterin fotoğrafı:** 31 çekilişte geçerli, defter büyürse yeniden
ölçülmeli. `COKLU_TEST_CEKILIS_SAYISI` testle bağlı, sayı değişirse test kırılıyor.

**Faz 4'e dönüş 5 (2026-09-11): tavan testi — arama kapandı (K-045).** "38 çekilişin
hepsi sinyal tarafındaydı, maliyet tarafına bakılmadı" itirazı test edildi. Maker yürütme
modeli yazmak yerine **üst sınır** ölçüldü: maliyet sıfır kabul edilip çekilişler yeniden
koşturuldu.

Sonuç: maliyet sıfırken bile geçen yok. 1h'te en iyi 0,526, 4h'te 0,691; kapı 1,02.
Maliyeti tamamen silmek Sharpe'a yalnızca +0,24 katıyor. Eski 0,50 kapısına göre de geçen
yok (kapılar bir konjonksiyon; tek kapı yetmiyor).

**Maliyet duvarı bağlayıcı kısıt değilmiş.** Tek sembollü yönlü strateji araması kapandı;
maker yürütme çalışması iptal. Funding carry de ölçüldü ve sıkışmış (son 1 yıl %3,40 brüt,
maliyet sonrası ~%2,8) — önerilmiyor. Ayrıntı: `docs/Faz-4-Donus-5-Tavan.md`.

### Faz 5: Risk motoru + promotion — ✅ kapandı 2026-09-11

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

**Bitti kriteri karşılandı — ayrıntılı ölçümler `docs/Faz-5-Risk-Raporu.md`'de:**

| Kriter | Sonuç |
| --- | --- |
| Risk motoru atlanamıyor (testle kanıtlı) | ✅ **üç katman**: tip (kapı yalnızca `OnayliNiyet` alır), mühür (içeriğin HMAC'i), ve asıl zorlama olan **import kesme noktası** — `execution/`+`oms/`den strateji katmanına giden her yol `risk.niyet`ten geçiyor (`test_risk_bypass.py`) |
| Her limit için ihlal senaryosu | ✅ sekiz limitin her biri için ihlal **ve** ihlal-olmayan vaka + sınır vakası (`test_risk_limitleri.py`) |
| Kill switch'te K-008'in beş davranışı | ✅ her davranış kendi test sınıfında; "pozisyon kapatılmaz" maddesi `risk/` paketinin portföyü hiç import etmediğiyle **yapısal** olarak kanıtlı (`test_kill_switch.py`) |
| `dirty` / `data_quality_warning` kapıdan geçemiyor | ✅ `test_promotion.py` + `sq promotion degerlendir` ile uçtan uca gösterildi |

**Üretilen paketler:** `risk/` (`limitler`, `muhur`, `niyet`, `durum`, `motor`, `audit`,
`promotion`, `kalibrasyon`), `execution/kapi.py`, `migrations/001_faz5.sql`, CLI:
`sq risk {kalibre,limitler,durum,audit,serbest}`, `sq promotion {durum,degerlendir,onayla}`,
`sq backtest --risk`.

**Faz 5'in verdiği kararlar:** K-032 (risk onayı bir tip, bir mühür ve bir kesme
noktasıdır), K-033 (her risk limiti kaynağını — `olculdu`/`istah` — ve gözden geçirme
koşulunu taşır).

**Ölçüm — BTC/USDT 1h, 45.576 bar; aynı veri, aynı maliyet, tek fark risk motoru:**

| Strateji | Getiri → R-Getiri | maxDD → R-maxDD | Sharpe → R-Sharpe | R-ort.maruziyet |
| --- | ---: | ---: | ---: | ---: |
| **al_tut (kıyas)** | +%25,9 → **+%7,1** | %25,7 → **%9,4** | 0,38 → 0,31 | %8,6 |
| sma_kesisim | −%13,3 → −%4,3 | %22,1 → %11,9 | −0,34 → −0,18 | %6,5 |
| ema_kesisim | −%8,3 → **+%8,1** | %20,4 → %7,7 | −0,19 → **+0,37** | %6,5 |
| rsi_donus | −%12,3 → −%10,5 | %18,5 → %13,4 | −0,28 → −0,62 | %4,9 |
| donchian | −%9,2 → −%6,8 | %15,0 → %9,6 | −0,30 → −0,46 | %3,7 |
| momentum | −%17,6 → −%10,2 | %24,8 → %13,1 | −0,49 → −0,56 | %5,8 |
| cok_faktor | −%46,0 → −%19,1 | %49,4 → **%20,1** | −1,85 → −1,78 | %1,8 |

**Tablonun en önemli satırı kıyas satırı.** Risk motoru yedi vakanın yedisinde de düşüşü
azalttı, ama kıyasın getirisini de +%25,9'dan +%7,1'e indirdi. Yani risk motoru bir alfa
kaynağı değil **varyans azaltıcı**: kaybedeni daha az kaybettirir, kazananı daha az
kazandırır. Altı stratejinin zararının küçülmesi bir başarı kanıtı değil, maruziyetin
küçülmesinin aritmetik sonucu.

**Kill switch gerçek veride bir kez tetiklendi:** `cok_faktor` drawdown limitini (%20) aştı,
SAFE_MODE açıldı, sonrasındaki **3.417 giriş sinyali** reddedildi ve çıkış sinyalleri
geçmeye devam etti (K-008/3).

**Limitlerin kalibrasyonu (K-033):** üç limit ölçüldü, beşi iştah olarak işaretlendi ve her
biri bir gözden geçirme koşulu taşıyor. En dikkat çekici ölçüm: yaygın **"2×ATR" stop
varsayımı bu veride riski hafife alıyor** — 24 barlık ufukta aleyhte hareketin medyanı 2,07
ATR, p90'ı 6,39 ATR. 2,0 seçmek vakaların yarısında gerçek riskin altında kalmak olurdu
(K-007).

**Beklenmeyen bulgular:**

1. **"Execution stratejiyi hiç görmüyor" iddiası yanlıştı ve testi kendi kırdı.**
   `OnayliNiyet` sinyali içinde taşıdığı için `execution → risk.niyet → strategy.sinyal`
   yolu kaçınılmaz — ve doğru: audit'in "strateji ne istedi, risk ne verdi"
   karşılaştırması ikisi bir aradayken mümkün. Doğru iddia "o yol yok" değil, **"o yol
   `risk.niyet`ten geçiyor"**. Test bir kesme-noktası testine çevrildi, ayrıca kesme
   testinin kendi testi eklendi (yoksa `execution/`i silmek de geçirirdi).
2. **Kayan nokta sınır testlerini sessizce kırıyordu.** `1 − 8000/10000` =
   0,19999999999999996, yani "tam %20 düşüş" limiti aşmış görünüyor. Karşılaştırmalar
   çıkarmadan çarpmaya çevrildi (`son < zirve × (1 − limit)`).
3. **`SIFIR_BOYUT` red sebebi ölü koddu.** Boyutlandırma tavanı hiçbir zaman tam sıfıra
   inmiyor; sebep hiç üretilemezdi. Risk motorunda ölü kod işe yaramaz değil **tehlikeli**:
   sayımın kapsadığı sanılan bir durum kapsanmıyor demektir.
4. **Limitler tavan değil tetikleyici, ve bu iki yerde ölçüldü.** `azami_maruziyet` %30
   iken gerçekleşen maruziyet %30,14 (fill sonrası fiyat hareketi; sürekli yeniden
   dengeleme yok). `drawdown_limiti` %20 iken `cok_faktor` %20,1 düştü — limit tam
   tasarlandığı gibi çalıştı ama zaten olmuş bir düşüşü geri alamaz, çünkü K-008/2 açık
   pozisyon kapatmayı yasaklıyor. Bu bulgu promotion kapısının **gerekçesini de düzeltti**.
5. **Risk motoru girişi ATR ısınması kadar geciktiriyor.** `al_tut`un 15
   değerlendirmesinden 14'ü `volatilite_olculemedi` ile reddedildi: ATR(14) ilk 14 barda
   NaN ve ölçülemeyen guard geçilmiş sayılmıyor. NaN'ı sıfır saymak iki limiti birden
   sessizce kaldırırdı.

- **Notlar:** PostgreSQL **bağlanmadı**, şeması donduruldu (`migrations/001_faz5.sql`);
  K-011 gerekçesi gereği eşzamanlı yazma ilk kez Faz 6'da gerekiyor. Audit bugün SQLite'a
  yazıyor ve iki şemanın kolonları testle hizalı tutuluyor. Risk motoru backtest'te
  **opsiyonel** (`--risk`): Faz 1-4'ün ölçümleri yeniden üretilebilir kalmalı ve risk
  özeti `sonuc_hash`'e yalnızca varsa giriyor. Promotion zincirinde hiçbir strateji
  `out_of_sample` aşamasını geçemiyor — K-019'un eşikleri gevşetilmedi.

### Faz 6: Paper trading + dashboard — ✅ kapandı (2026-09-15, K-055)

- **İşler:** WebSocket ile gerçek zamanlı veri; stale-data guard (§24); canlı sinyal
  üretimi; simüle emir ve pozisyon takibi; gerçek zamanlı risk kontrolü; FastAPI; 4 sayfalık
  dashboard (Overview, Strategies, Positions, Logs) — K-012; DESIGN.md'nin token'ları bu
  fazda doldurulur.
- **Bitti Kriteri:**
  - ~~30 gün kesintisiz çalışma (kesinti olduysa sebebi kayıtlı ve giderilmiş).~~ **K-055 ile
    bu fazdan çıkarıldı** — Faz 8 ön koşuluna ve Faz 14'e taşındı (aşağıda).
  - Süreç öldürülüp yeniden başlatıldığında pozisyon ve emir state'i doğru toparlanıyor.
  - Veri akışı kesildiğinde yeni pozisyon açılmıyor (stale-data guard testi).
  - Dashboard'un 4 sayfası çalışıyor ve risk durumu ilk bakışta görülüyor.
- **Notlar:** Frontend'e başlamadan önce global `~/.claude/CLAUDE.md`'deki araç sırası
  izlenir ve `DESIGN.md` doldurulur.

**Durum — kalan üç kriterin üçü de karşılandı, faz kapandı (2026-09-15). Ayrıntı
`docs/Faz-6-Paper-Raporu.md`'de:**

| Kriter | Sonuç |
| --- | --- |
| 30 gün kesintisiz çalışma | ↪ **taşındı (K-055)** — `gozlem-2` 4,29 gün koştu, 5 kesinti: 4 `temiz_kapanmadi` (makine her gün kapatılıyor) + 1 gerçek WebSocket kopması (18 s'de giderildi); 0 fill. 2026-09-15 19:24 UTC'de `sq paper durdur` ile düzgün kapatıldı, zamanlanmış görev kaldırıldı. Kriter bu makinede altyapıyı değil masaüstünün açık kalmasını ölçüyordu |
| Restart sonrası state doğru toparlanıyor | ✅ toparlanma bir geri yükleme değil **yeniden üretim** (K-038); 60 barı kesintisiz işleyen koşu ile 30 barda öldürülüp yeniden başlatılan koşu birebir aynı sonucu veriyor |
| Veri akışı kesilince yeni pozisyon açılmıyor | ✅ bayat-veri guard'ı (§24, K-037); azaltan niyetler geçiyor |
| 4 sayfalık dashboard, risk ilk bakışta | ✅ Genel/Strateji/Pozisyon/Günlük; risk şeridi her sayfada aynı yerde ve boşken de görünür |

**Faz neden kriter karşılanmadan değil, kriter taşınarak kapandı (K-055).** Gözlem koşusu
K-035 gereği promotion kanıtı **olamaz**; promotion'un `paper` aşaması kodda ayrıca
`ASGARI_PAPER_GUN = 30` ile zorlanıyor ve o kapı **değişmedi**. Faz 6'nın 30 günü yalnızca
altyapı dayanıklılığını ölçüyordu, ve bu ölçüm her gün kapatılan bir masaüstünde anlamlı
değil. Borç kayıtlı ve iki yere bağlandı: Faz 8 ön koşulu (5. madde) ve Faz 14 bitti kriteri.

**Faz 6'nın en önemli bulgusu kriterle ilgili değil, kargoyla:** hiçbir strateji promotion
kapılarını geçmediği için (`MOD_ESIGI["paper"] = RISK_INCELEMESI`, K-019'da yedi
stratejinin yedisi de kaldı) paper modunda risk motoru her sinyali `PROMOTION_YOK` ile
reddederdi — yani hiç pozisyon açılmaz ve restart kriteri **boş yere** geçerdi. Eşik
indirilmedi; K-035 ile **gözlem modu** eklendi: promotion dışındaki her limit tam olarak
uygulanıyor, ama o koşunun ürettiği hiçbir kayıt promotion kanıtı **olamıyor** (kanıt
nesnesi kurulmadan reddediliyor).

**Bunun bedeli kayıtlı:** K-018/3'ün beşinci eşik adayı (paper/backtest drift üst sınırı)
Faz 6'da ölçülecekti, **ölçülemedi** — drift'in büyüklüğü stratejiye bağlı. O sayı,
kapıları geçen ilk stratejinin gerçek `paper` koşusunda kalibre edilecek.

**Koşu başladıktan sonraki denetim (2026-09-11):** altyapı baştan sona denetlendi; koşunun
kendisinde arıza yok, ama 30 günü etkileyen altı sorun bulundu ve giderildi — `exchange/akis.py`
hiç test edilmemişti, `YENIDEN_BAGLANDI` olayı hiç yazılmıyordu, bayatlık yoklaması sessizce
ölebiliyordu, düzgün durdurmanın kapısı yoktu (K-043), backoff yanlış ölçüte bakıyordu ve
kapanışta bağlantılar kapatılmıyordu. Ayrıntı `docs/Faz-6-Paper-Raporu.md`. Testler 1023 → 1061.

**Faz 6'nın verdiği kararlar:** K-034 (operasyonel state SQLite/WAL, PostgreSQL Faz 7'ye
ertelendi), K-035 (gözlem modu), K-036 (dashboard Vite+React SPA, FastAPI servis eder),
K-037 (engelleyen katman risk motorunun dışında olabilir, izin veren olamaz), K-038
(toparlanma bir geri yükleme değil yeniden üretimdir).

**Üretilen paketler:** `live/` (akış, pencere, depo, motor, toparlanma, koşturucu, API,
kurulum), `exchange/akis.py` (Binance WebSocket + resync), `live/kilit.py` (tek-yazıcı kilidi), `backtest/defter.py` (Faz 3'ten
taşındı — K-001), `apps/web/` (Vite SPA), CLI `sq paper {baslat,durum,durdur,olaylar}`.
881 test yeşil (Faz 5 sonunda 757'ydi).

### Faz 7: Execution sandbox (Binance Spot Testnet) — ✅ kapandı 2026-09-11

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

**Bitti kriteri karşılandı — ölçümlerin tamamı `docs/Faz-7-Execution-Raporu.md`'de:**

| Kriter | Sonuç |
| --- | --- |
| Duplicate order üretilemiyor | ✅ **iki katman**: defter aynı kimliği tanıyınca istek borsaya hiç gitmiyor (fiyat sorgusu bile yapılmıyor); defter silinse bile kimlik içerikten türediği için borsa `-2010` ile reddediyor |
| Reconciliation (süreç ortada ölünce) | ✅ **iki vakanın ikisi de** gerçek testnet'e karşı doğru çözüldü: emir oluştuysa `UNKNOWN → FILLED`, oluşmadıysa `UNKNOWN → FAILED` |
| Testnet'te ≥100 emir | ✅ **100/100 FILLED**, elle müdahale gerektiren hata 0, süre 2 dk 4 sn, 5 ara mutabakat temiz |
| Uyuşmazlıkta halt | ✅ borsa kabul ettiği emri tanımıyorsa, defterde olmayan açık emir varsa, ya da borsanın durumu state machine'de ulaşılamazsa koşu duruyor |

Faz 4'e dönüş 1 ve 2 çürüdükten sonra Faz 7'ye geçildi ve bu bir yön kararıydı:
**Faz 7 promotion geçmiş bir strateji gerektirmiyor.** Emir mantığı, idempotency ve
reconciliation kendi başına doğrulanabilir; strateji arayışının azalan verimi altyapıyı
bloke etmemeli. Ölçüm bunu doğruladı — dört kriter de strateji olmadan kapandı.

Duplicate koruması **üç yapısal mekanizma** (K-040): kimlik onaylı niyetin içeriğinden
türüyor (mühür dahil değil, yoksa restart'ta çökerdi), defterde birincil anahtar, ve state
machine'de `UNKNOWN → SUBMITTED` geçişi **yok**. `UNKNOWN` bir başarısızlık değil bir
bilinmezlik: `FAILED` sayıp yeniden denemek duplicate üretmenin en kısa yolu.

`SUBMITTED` diske ağ çağrısından **önce** yazılıyor — yetim emir bırakmamak için; en kötü
durum hiç gönderilmemiş bir emrin kaydı ve reconciliation onu kapatır. K-038'in aynı
mantığı: kaydı erken yazmak geç yazmaktan güvenli.

**Saat sorunu ölçüldü ve kodla çözüldü.** Yerel saat borsadan **2.640 ms geride** (kararlı,
iki host aynı); Spike 1'in −153 ms'i artık geçerli değil. İşletim sistemi saatini düzeltmek
reddedildi — sorunu ertelerdi. `timestamp` artık borsanın saatinden türüyor ve
`time.monotonic()` çıpasına bağlı, yani sistem saati değişse bile imza geçerli kalıyor.
100 emirlik koşuda tek bir `-1021` görülmedi. Ayrıntı: K-041/2.

**Beklenmeyen bulgu — sahte borsa gerçeğinden hoşgörülüymüş.** 988 birim testin tamamı
yeşilken ilk gerçek testnet koşusu iki hata gösterdi: `FLAT` borsaya olduğu gibi
gönderiliyordu (`Invalid side`), ve defter istenen miktarı yazıyordu, gönderilebileni
değil — yani `FILLED` bir emrin `kalan`ı sıfır değildi. İkincisi tam olarak bu projenin
"neredeyse doğru" dediği sınıf: çökme yok, hata yok, test yeşil, ve pozisyon hesabında her
emirde biraz büyüyen sessiz bir fark. Ders: **bir sahte, gerçeğin reddettiğini kabul
ediyorsa ona karşı yeşil olan test bir şey kanıtlamaz.** `SahteBorsa` artık yön ve lot
adımı doğruluyor; iki hata için de regresyon testi var.

**Bu fazın ölçmediği şeyler** (raporun §7'si): pozisyon mutabakatı, limit emri ve iptal
yolu, uzun süreli dayanıklılık. **K-034 yine ertelendi:** Faz 7'de de tek yazıcı var,
PostgreSQL'in gerekçesi olan eşzamanlı yazma doğmadı; şema dondurulmuş kalıyor.

**Faz 7'ye dönüş (2026-09-11): dört eksikten ikisi kapandı.** Faz 4'e dönüş 5'ten sonra
(K-045) Faz 8'in önündeki engel bir iş kalemi değil bir bulgu — promotion'u geçen strateji
yok. Bu arada **stratejiden bağımsız** ölçülebilen iki borç kapatıldı; ikisi de Faz 8'in ön
koşulu ve ikisi de strateji beklemiyordu:

| Eksik | Durum |
| --- | --- |
| Pozisyon mutabakatı | ✅ **K-046** — değişmez çıpa + defter akışı vs borsa bakiyesi. `runs/testnet/poz-1`: fark tam sıfır; defterin bilmediği 0,0002 BTC'lik bir emir gönderilince **durdu** (−15,4368 USDT, çıkış kodu 1) |
| Limit emri ve iptal | ✅ **K-047** — dört vaka gerçek testnet'te: açık limit para kilitliyor, iptal kilidi çözüyor, marketable limit limitten iyi fiyattan doluyor, dolmuş emrin iptali ağa hiç çıkmıyor |
| PostgreSQL şeması (K-034) | ✅ **ölçüldü** — üç geri dönüş koşulunun üçü de uzak: tek yazıcı, audit 1.091 satır (eşik 10 M), `runs/` 3,7 MB (eşik 5 GB), tek sembol. Erteleme değil, ölçüm |
| Uzun süreli dayanıklılık | ⏳ açık, Faz 8 |

**İki iş birbirini buldu:** Faz 7'nin `bakiye()`si yalnızca `free` okuyordu ve market
emriyle bu hiç sorun çıkarmamıştı; limit yolu açılınca aynı kod **her açık emirde**
pozisyon mutabakatını haksız yere durduracaktı. Ayrı yapılsalardı ikincisi birincinin
üzerine sessiz bir arıza bırakırdı.

**Kayıtlı ölçülemezlik: testnet komisyon kesmiyor** (`commission: '0.00000000'`). Pozisyon
mutabakatının temiz sonucu, komisyon yolu hiç çalışmadan da aynı çıkardı. Komisyon mantığı
birim testlerde ölçülüyor; gerçeğe karşı ilk sınavı Faz 8. Testler 1103 → 1143.

**Üretilen paketler:** `exchange/` (`hatalar`, `kurallar`, `emir_adaptoru`, `imzali`),
`execution/motor.py`, `oms/mutabakat.py`, CLI `sq testnet {durum,yuk,kesinti,mutabakat}`.
**991 test yeşil** (Faz 6 sonunda 942'ydi).

**Faz 7'nin verdiği karar:** K-041 (ağ hatası üç sınıfa ayrılır; imzanın zamanı borsadan
gelir; mutabakat çözemediğinde durur).

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

**v2'nin eklediği ön koşullar (2026-09-12):**

1. **Süreç dışı kill switch çalışıyor olmalı** (Denetim-v2 A8). Bugünkü kill switch risk
   motorunun, yani trader sürecinin içinde; süreç kilitlenirse kill switch de kilitlenir.
   Paper'da bunun bedeli yok, canlıda var. Faz 14'ün ilk kalemi, ama Faz 8 ondan **önce**
   tetiklenirse bu tek kalem yine de önce yapılır.
2. **Shadow adımı** (doküman §3: paper → shadow → micro-live). Canlı modun tamamı, emir
   gönderimi hariç: gerçek bakiye okunur, emir kurulur, doğrulanır, deftere "gönderilmedi"
   yazılır. Paper'ın ölçemediğini ölçer — gerçek bakiye, gerçek sembol kuralları,
   karar→emir gecikmesi.
3. **Kademeli sermaye tablosu** (K-050/3): her kademe için asgari kesintisiz canlı gün,
   `|paper − live|` drift üst sınırı, açıklanamayan pozisyon farkı sıfır (K-046) ve elle
   onay. Kademe atlanamaz; ihlalde sermaye **otomatik** bir kademe iner.
4. **Venue'nun hukuki statüsü doğrulanmış olmalı** (Denetim-v2 D2): K-015 teknik erişimi
   ölçtü (451 yok), hukuki erişimi ölçmedi. SPK'nın 2025 düzenlemesi sonrası kullanılan
   borsanın Türkiye yerleşiğine hizmet statüsü kaynaklı olarak kaydedilir. Proje K-014
   içinde kaldığı sürece hizmet sağlayıcı değildir; doğrulanan şey venue'nun durumu.
5. **Sürekli açık bir host ve üzerinde 30 günlük kesintisiz koşu** (K-055, Faz 6'dan
   taşındı). Canlı koşu her gün kapatılan bir masaüstünde yaşayamaz. Promotion'un `paper`
   aşaması (`ASGARI_PAPER_GUN = 30`) zaten bu host üzerinde koşulur; kesinti olursa sebebi
   koşu günlüğünde kayıtlı ve giderilmiş olmalı. Açık pozisyonla gerçek bir toparlanma en az
   bir kez bu koşuda görülmüş olmalı (Faz 6'da 0 fill ile sınanamadı).

- **Notlar:** Sermaye artırma kararı bu fazın çıktısına bakılarak verilir; fazın içinde
  değil, ve artık K-050/3'ün sayısal kuralıyla. Drift beklenenden büyükse sermaye artmaz,
  Faz 3-4'e (v2'de Faz 10-12'ye) geri dönülür.

---

# v2 — Faz 9-16

Bu bölüm `docs/Proje-Fikri-v2.md` ve `docs/Denetim-v2.md` üzerine kuruldu; kararları K-048…
K-054. Faz geçiş kuralı aynen geçerli: bir faz, bitti kriterinin **tamamı** karşılanmadan
kapanmaz.

**Sıra neden bu.** Dokümanın kendi önerisi (§32): *Data/Research Foundation → Cost-aware
Backtest → Validation Framework → alpha aileleri → Paper → Risk/Execution → Micro-live →
Multi-asset.* Bizde backtest, paper, risk ve execution zaten kapalı; sıranın v2'ye düşen
kısmı **veri → çekirdek → doğrulama → araştırma**. Doğrulama araştırmadan **önce** geliyor ve
bu bilinçli: kapıları sonuçları gördükten sonra tanımlamak, bu projenin her yerde yasakladığı
şey.

### Faz 9: Veri platformu v2 — PIT, evren, enstrüman kimliği — ✅ kapandı (2026-09-16, K-056)

- **İşler:** Kanonik enstrüman kimliği (geçerlilik aralıklı) ve kimlik kırılması tespiti;
  çoklu sembol indirici (delist edilenler dahil, `data.binance.vision` arşivinden); PIT evren
  tablosu (aylık üyelik + likidite kuralı, **kendi barlarımızdan** hesaplanan hacimle);
  kaynak başına **veri sözleşmesi** (şema, cadence, timestamp semantiği, tamlık, revizyon,
  lisans) ve katman başına tamlık kontrolü; bar olmayan gözlemler için PIT deposu
  (`event_time`/`available_time`/`ingested_time`/`effective_from|to`); K-034 ve K-011'in
  yeniden ölçümü.
- **Girdi:** Spike 6 (`docs/spikes/06-coklu-sembol-evren.md`) — 659 aday sembol, ≈0,86 GB,
  ≈8 dk indirme, ölçülmüş hayatta kalma yanlılığı (ayda medyan %18).
- **Bitti Kriteri:**
  - Aday evrenin 1h geçmişi indirilmiş (delist edilenler dahil), indirme **idempotent**, her
    dosyanın SHA-256'sı kayıtlı.
  - `sq data evren` PIT evren tablosu üretiyor: bir ayın üyeliği yalnızca o aya kadarki
    veriyle hesaplanıyor. **Testle kanıtlı:** gelecekteki veri bozulduğunda geçmiş üyelik bit
    düzeyinde değişmiyor.
  - **Kimlik kırılması yakalanıyor:** `LUNAUSDT` 2022-05 vakası (kapanış 0,00005 → 17 gün
    boşluk → açılış 1,00) fixture olarak testte, seri iki kimliğe bölünüyor.
  - Bar olmayan bir gözlem `available_time`e göre kesiliyor; `event_time`e göre kesen bir
    uygulama testle **reddediliyor**. Gün çözünürlüklü kaynak gün sonuna yuvarlanıyor.
  - Her veri kaynağının sözleşme dosyası var ve tamlık kontrolü otomatik koşuyor; arşivin
    `1mo` katmanındaki eksiklik (Spike 6 §4b) bu kontrolle yakalanıyor.
  - **K-034 yeniden ölçüldü** ve sonuç (geçiş veya kalma) karar günlüğüne yazıldı.
- **Notlar:** Bu faz strateji içermez ve içermemeli. Veri katmanı yanlışsa üstündeki her ölçüm
  yanlış olur — ve bu projede yanlış ölçüm, ölçüm yokluğundan tehlikelidir.

**Durum — altı kriterin altısı karşılandı. Ölçümler `docs/Faz-9-Veri-Platformu-Raporu.md`de:**

| Kriter | Sonuç |
| --- | --- |
| Aday evrenin 1h geçmişi inmiş, idempotent, her dosyanın SHA-256'sı kayıtlı | ✅ 735 sembol istendi, 734'ünde veri (arşivde 1h'i olmayan tek sembol `USDSOLDUSDT`), 34.519 dosya, 20.055.412 bar, 628 MB, 0 hata. İkinci koşu 0 dosya indiriyor; hash'ler sembol başına `1h.kaynak.json` manifestosunda |
| `sq data evren` PIT tablo üretiyor; gelecek veri bozulduğunda geçmiş üyelik bit düzeyinde değişmiyor | ✅ 109 ay, 4.464 satır; look-ahead testi `test_evren.py::TestLookAhead` (hacim çarpıtma + sahte kırılma + gelecek barları silme) |
| Kimlik kırılması yakalanıyor; `LUNAUSDT` 2022-05 fixture olarak testte, seri iki kimliğe bölünüyor | ✅ Eşikler **ölçüldü** (12 bar, ln 10); 734 sembolde 27 kırılma / 24 sembol; LUNA fixture'ı gerçek arşiv satırlarından (`test_kimlik.py`) |
| Bar olmayan gözlem `available_time`e göre kesiliyor; `event_time` kesicisi reddediliyor; gün çözünürlüğü gün sonuna yuvarlanıyor | ✅ `data/pit.py` + `kesme_sozlesmesini_dogrula`; yanlış kesiciler testte kalıyor (`test_pit.py`) |
| Her kaynağın sözleşme dosyası var; tamlık kontrolü otomatik koşuyor; `1mo` katmanındaki eksiklik yakalanıyor | ✅ `data/sozlesme.py` (3 kaynak); katman kontrolü `sq data arsiv-indir` içinde otomatik ve arşivde `1mo`'nun eksik aylarını (2024-03, 2026-03, 2026-07…) yakalıyor. **Açık kalem:** üç sözleşmede de lisans "doğrulanmadı" |
| K-034 yeniden ölçüldü ve sonuç karar günlüğüne yazıldı | ✅ Koşul 3 (çok sembollü çalışma) gerçekleşti, ölçüldü, PostgreSQL'i **gerektirmedi** (K-034 gözden geçirme bloğu, 2026-09-16) |

**Fazın sürprizi kriterlerde değil, arşivin kendisindeydi:** zaman damgası 2025-01'de
mikrosaniyeye geçmiş, pandas'ın varsayılan float ayrıştırıcısı değerleri kaydırıyor, arşiv
REST'ten 45.576 barın 4'ünde farklı, ve 2018-02 kesintisinden sonra 6 sembolde 258 bar
ızgaraya oturmuyor. Dördü de K-056'ya bağlandı.

### Faz 10: Çok enstrümanlı araştırma çekirdeği

- **İşler:** Evren `ctx`i (t anında üyelik + her enstrümanın kesilmiş görünümü); hedef portföy
  sözleşmesi; portföy kurma (oynaklık ayarlı boyut, korelasyon ve konsantrasyon limitleri,
  turnover cezası, nakit bir pozisyondur); çok enstrümanlı backtest motoru; metrik genişlemesi
  (kapasite/ADV oranı, VaR/CVaR); risk motorunun portföy düzeyi.
- **Bitti Kriteri:**
  - **Tek enstrüman özel hâldir:** Faz 3'ün bağımsız referans fixture'ı yeni motorda **bit
    düzeyinde** aynı sonucu veriyor. (K-052/2 — bu kriter düşerse K-001 düşer.)
  - **Çok enstrümanlı bağımsız referans:** ≥2 enstrüman, ≥10 işlem içeren senaryonun beklenen
    P&L'i motordan bağımsız hesaplanıp `tests/fixtures/` altına sabitlenmiş; motorun çıktısı
    birebir uyuşuyor. Üretici `scryne_quant`ı import etmiyor (K-029).
  - **Evren look-ahead testi yeşil:** t sonrası fiyat **ve** t sonrası listeleme/delist bilgisi
    bozulduğunda sonuç bit düzeyinde değişmiyor.
  - Determinizm: aynı veri + config iki koşuda aynı `sonuc_hash`.
  - Risk motoru çok enstrümanlı hedef portföyü onaylıyor/reddediyor; bypass testi
    (`test_risk_bypass.py`) hâlâ yeşil; portföy kurma **izin veren** bir katman değil.
- **Notlar:** Portföy kurma yöntemi bir **çekiliştir** (K-051/4) — bu fazda yöntem *kurulur*,
  strateji aranmaz.

### Faz 11: Doğrulama v2

- **İşler:** K-054'ün dört kapısı (`rejim_kararliligi`, `evren_dayanikliligi`,
  `parametre_perturbasyonu`, `pbo`); PBO'nun CSCV uygulaması; DSR, kapasite ve kalibrasyonun
  raporlanması; `leak_riski` mutlak engeli; program kaydı ve arama bütçesi komutları
  (`sq lab program-kaydet`, `sq lab bütçe`).
- **Bitti Kriteri:**
  - Dört kapı da hesaplanıyor ve her eşik **gerekçesiyle** sabitlenmiş (K-019 kalıbı: sayı
    nereden geliyor, hangi ölçüme dayanıyor).
  - Eşikler bugünkü sonuçlara göre ayarlanmadı: gevşetmeyi yakalayan bir test var
    (`test_faz4_olcumlerinden_hicbiri_gecmiyor`in kardeşi).
  - Defterdeki mevcut 38 çekiliş yeni kapılardan da geçirilmiş ve sonuç raporlanmış — geçen
    olsa da olmasa da.
  - `leak_riski` taşıyan bir sonuç kapıdan geçemiyor (testle).
  - **Program kaydı olmadan bir araştırma programı koşturulamıyor** (K-051/2, testle).
- **Notlar:** Bu fazda strateji aranmaz. Kapıyı, geçecek adayı görmeden tanımlamak K-044'ün
  dersi.

### Faz 12: Araştırma programları — cross-sectional, türev, makro

- **Ön koşul:** Faz 9-11 kapalı. Her program için K-051'in program kaydı: gerekçe, kaynağın
  neden belirgin biçimde farklı olduğu (ölçüyle — K-045'in istisnası), azami çekiliş sayısı,
  durma kuralı, eşik tahmini.
- **İşler:** (a) **Cross-sectional**: evren içi göreli güç/değer/oynaklık sıralamaları;
  (b) **Türev**: evren geneli funding/basis — tek sembolde ölçülen mekanizma
  (`funding_filtre`, K-042) evrende tekrar ediyor mu; (c) **Makro**: ücretsiz PIT kaynakları
  (ALFRED vintage, ECB) ile rejim/risk-iştahı bağlamı; (d) **Rejim motoru**: filtrelenmiş
  olasılık, katman başına eğitim, engelleyici kullanım (K-052).
- **Bitti Kriteri:**
  - Her program **kendi bütçesi içinde** kapanmış; bütçe aşımı yok.
  - Her programın sonucu kapılara karşı raporlanmış (`docs/Faz-12-*`), geçen olmasa da.
  - Defter büyümesi sonrası `sq lab coklu-test` yeniden koşmuş ve `oos_sharpe` eşiği
    güncellenmiş (K-044); `COKLU_TEST_CEKILIS_SAYISI` testi buna bağlı.
  - Rejim motoru kullanıldıysa: yumuşatılmış olasılık kullanılmadığı testle kanıtlı.
- **Notlar:** Bu fazın çıktısı "kârlı strateji" olmayabilir ve bu bir başarısızlık değildir —
  Faz 4'ün dersi aynen geçerli. Sistemin işi cevabı ölçmek.
- **FRED API anahtarı** (ücretsiz, kayıt gerektirir) makro programının ön koşulu; Scryne'dan.

### Faz 13: Haber/olay zekâsı + ML — **koşullu**

- **Açılma koşulu (ikisi de gerekli):** (1) veri/altyapı bütçesi kararı (Final-Doküman
  "Bütçeler" — bugün açık); (2) kaynak spike'ı: geçmişe dönük, **ilk yayın zamanı doğru** ve
  lisansı kullanıma uygun bir haber arşivi var mı, maliyeti ne. Ücretsiz akışların geçmişi
  yoktur; ileriye biriktirmek yıllar alır ve bu fazın sorusunu cevaplamaz (Spike 5'in dersi).
- **İşler (açılırsa):** Kaynak → varlık → olay → yenilik → sürpriz → etki grafiği zinciri
  (doküman §8); semantic AI **yetkisiz** (K-049/1); predictive ML yalnızca kapılardan sonra;
  LLM çıktısı dondurulmuş veri kaynağı (K-049/5).
- **Bitti Kriteri (açılırsa):** LLM eğitim kesim tarihi önceden kayıtlı ve ölçüm penceresi o
  tarihten sonrası; kesim öncesi türetim `leak_riski` taşıyor ve kapıdan geçemiyor; her LLM
  çıktısı model kimliği + prompt hash + girdi hash ile dondurulmuş ve backtest yalnızca
  dondurulmuş dosyayı okuyor; ML modelleri hipotez defterinde çekiliş olarak sayılıyor.

### Faz 14: Üretim sertleştirme

- **İşler:** **Süreç dışı kill switch** (borsadaki açık emirleri iptal eden, trader sürecini
  sonlandıran, yeniden başlamayı SAFE_MODE'a kilitleyen bağımsız komut — Denetim-v2 A8);
  izleme dört boyutta (sistem, veri, trading, model) + risk; alarm ve **runbook**; günlük
  operasyon döngüsü ve gün sonu (UTC 00:00) anlık görüntüsü; yedek ve **geri yükleme
  tatbikatı** (K-038: geri yükleme değil yeniden üretim); sır yönetimi (okuma/işlem anahtarı
  ayrımı, çekim yetkisi kapalı, IP allowlist); uzun süreli dayanıklılık (Faz 7'nin açık
  kalemi); CI.
- **Bitti Kriteri:**
  - Kill switch, trader süreci **askıdayken** (yapay olarak dondurulmuş) çalışıyor ve
    testnet'te kanıtlanmış: açık emirler iptal edilmiş, süreç durmuş, yeniden başlatma
    SAFE_MODE'da açılmış.
  - Dört gözlem boyutu dashboard'da görünüyor ve her alarmın bir runbook satırı var.
  - Toparlanma tatbikatı: koşu dosyası yedekten geri getirilip state **yeniden üretiliyor** ve
    karşılaştırma temiz.
  - Anahtar ayrımı ve çekim yetkisinin kapalı olduğu ekran görüntüsü/çıktıyla kayıtlı.
  - **Uzun süreli dayanıklılık** (K-055; Faz 6'nın 30 günü + Faz 7'nin açık kalemi): sürekli
    açık host üzerinde ≥30 gün kesintisiz koşu, kesinti olduysa sebebi kayıtlı ve giderilmiş.

### Faz 15: İkinci varlık sınıfı (US equities / ETF) — **koşullu**

- **Açılma koşulu:** Broker/lisans spike'ı (K-053): Türkiye yerleşiğinin hesap uygunluğu,
  veri lisansının kapsamı ve maliyeti (ücretsiz plan IEX ile sınırlı — doküman §27), PIT
  corporate action verisi, gerçek komisyon tarifesi. Veri/altyapı bütçesi kararı.
- **İşler (açılırsa):** Broker adaptörü (Alpaca veya IBKR); seans/takvim/tatil modeli; tick ve
  lot kuralları; corporate action bilinçli kanonik seri; varlık sınıfına özel maliyet modeli;
  cross-asset portföy.
- **Bitti Kriteri (açılırsa):** Aynı kod yolu (K-001) ikinci varlık sınıfında paper koşuyor;
  corporate action fixture'ı (split/temettü) testte; seans dışı sinyal üretilmiyor; maliyet
  modeli o piyasa için ayrıca kalibre edilmiş (K-021 kalıbı).

### Faz 16: Sürekli araştırma

- **Kapanmaz.** Her tur şunu bırakır: bir program kaydı (gerekçe + bütçe), bir ölçüm raporu ve
  gerekirse bir karar. Piyasa koşulu değişimleri (funding rejimi, komisyon yapısı, yeni veri
  kaynağı) bu turların tetikleyicisidir.
- **Kural:** Tur açmak K-051'e tabidir. "Sadece bakıyorum" diye koşturulan bir strateji de bir
  çekiliştir.
