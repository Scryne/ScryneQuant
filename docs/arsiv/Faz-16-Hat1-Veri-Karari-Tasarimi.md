---
proje: ScryneQuant
faz: 16
tur: DESIGN + uygulama kaydı — üç veri ekleme kararı; A ve B uygulandı, C bekliyor (bkz. son bölüm)
tarih: 2026-09-20
type: tasarım
durum: A ve B uygulandı; C kararları verildi (iki senaryo, PIT/NON_PIT ayrı satır) ve mark verisi indirildi; mmr yok (2026-09-20)
---
# Hat 1 — Veri ekleme kararları: DTB3 · perp 1m klines · mark price

Bu doküman üç veri kararını **tanımlar**; kararı Scryne verdi (A → B → C, 2026-09-20), uygulama kaydı son bölümde. Kaynak: `docs/Faz-16-Hat1-B-Veri-Spike-
Tasarimi.md` (commit `64616a9`). Ortak kural: K-056/1 (REST deposu ile arşiv deposu
karışmaz; her arşiv dosyasının SHA-256'sı `.kaynak.json`'da), K-009 (kirli veri kanıt
değil), Final-Doküman "Bütçeler" (veri ekleme kalemi). Hiçbir kararda getiri sayısı yok.

## Karar A — DTB3 (B-5 benchmark)

| | |
| --- | --- |
| Neden gerekli | Fırsat-maliyetli aşama (ikinci tavan §9/3) benchmark'sız DATA BLOCKED; repoda nakit getirisine yakın tek ölçülebilir seri adayı bu. |
| Açtığı ölçüm | `r_excess = r_cap − r_bench`, excess Sharpe; ikinci tavanın 3. aşaması. |
| Kaynak | FRED/ALFRED `DTB3` (3-Month Treasury Bill, Secondary Market, Discount Basis; günlük, yüzde; Fed H.15). Erişim: mevcut anahtar (`.env` / host kullanıcı ortamı, K-066); 6 seri aynı hatla inmiş. |
| Mekanizma | `tools/faz12_makro_indir.py::SERILER` demetine `"DTB3"` — **tek satır**; araç yıl-parçalı ALFRED isteği atar (`realtime_start/end` yıl bazında), her parçanın SHA-256'sı ve parametreleri `data/makro/DTB3.kaynak.json`'a, seri `DTB3.parquet`'e (`date, realtime_start, realtime_end, value`). |
| PIT | `data/makro.py` K-060 kuralı aynen: `d` gününün değeri `d+1` 00:00'dan görünür; hafta sonu/tatil son gözlem; ilk vintage öncesi NaN. DTB3 revize edilmeyen seri — vintage tek, kural yine uygulanır. |
| Kapsam | 2019-09 → bugün (funding verisinin başı); ikinci tavanda yalnız IS (→ 2025-02-16). |
| Kullanım sınırı | Yalnız B-5 benchmark; `makro.SERILER` (program kaydına bağlı sözlük, K-051/2) **değişmez** — DTB3 bir araştırma programının girdisi değil, tavan girdisi. |
| Yöntem notu (karar değil) | Discount basis → yatırım getirisi çevrimi spike'ta kaynağıyla yazılır; formül bu dokümanda yok. |
| Depo etkisi | ≈ 0,2 MB (mevcut 6 seri toplam 972 KB). Bütçe kalemi: sıfıra yakın. |
| Karar tipi | **Veri ekleme kararı**, küçük. Kapsam/kod/kapı değişikliği yok; K-kaydı gerekmez, "Bütçeler"e bir satır. |

## Karar B — Perp 1m klines (B-1 slippage)

| | |
| --- | --- |
| Neden gerekli | Perp bacağı slippage'ı K-021 yöntemiyle (1m bar-to-bar \|Δclose\| p75) kalibre edilmeden maliyet-düzeltilmiş aşama (§9/2) perp kalemini taşıyamaz; spot slippage'ı perp'e taşımak yeni varsayım olur. |
| Açtığı ölçüm | `slippage_bps_perp` kalibrasyonu (`sq data slippage-kalibre --depo <perp>` kalıbı) → B-1 perp tek yön maliyeti → ikinci tavan 2. aşaması (tarife kaydıyla birlikte). |
| Kaynak | `data.binance.vision` `data/futures/um/monthly/klines/<S>/1m/<S>-1m-YYYY-MM.zip` + `.CHECKSUM` (herkese açık). Kapsam ve dosya adı deseni spike'ta `HttpArsiv.listele` ile doğrulanır; burada varsayılmadı. |
| Format | Binance kline CSV: `open_time, open, high, low, close, volume, close_time, quote_volume, trades, taker_buy_base, taker_buy_quote, ignore` (spot ile aynı şema; `arsiv_indirici` ayrıştırıcısı yeniden kullanılabilir — spike'ta doğrulanır). Depo şeması `data/market` ile aynı sütunlar + `quality_status` (K-006/K-024 bayrakları aynen). |
| Mekanizma | `faz12_premium_indir.py` kalıbında yeni araç; hedef `data/turev/klines_1m/<S>.parquet` + `<S>.kaynak.json` (zip SHA'ları). REST deposuna yazılmaz (K-056/1). |
| Sembol / timeframe | **BTCUSDT, ETHUSDT — yalnız 1m**, IS (2020-01 → 2025-02). Altcoin yok (kalibrasyon taşınmaz, B tasarımı §B-1). |
| Depo etkisi | Repo ölçüsüyle: spot BTC 1m 1,63 M satır = 66,7 MB parquet (3,1 yıl); perp 62 ay ≈ 2,7 M satır ≈ 110 MB/sembol → **≈ 220 MB** parquet, zip geçici. `data/evren` 0,86 GB ile kıyaslandığında orta. |
| Karar tipi | **Veri ekleme kararı** (yeni depo dizini, K-056 ayrımı) + Bütçeler satırı. Kapsam değişikliği değil (perp hâlâ bilgi kaynağı; bu veri **işlem** için değil, maliyet kalibrasyonu için). K-kaydı gerekmez; K-056 kalıbı yeter. |
| Bağımlılık | Tek başına yetmez: tarife kaydı (spike, ölçüm) olmadan `c_perp` tamamlanmaz. Tarife için imzalı uç kullanılacaksa vadeli anahtar → K-066 kararı; herkese açık sayfa kullanılırsa karar yok. |

## Karar C — Mark price (B-3 likidasyon fiyat yolu)

| | |
| --- | --- |
| Neden gerekli | Likidasyon mark price'a göre tetiklenir; repodaki premium index mark değildir. A-5 MFE spot `high`'dan hesaplandı — fiyat tarafının yaklaşımı, mark değil. |
| Açtığı ölçüm | Likidasyon/marjin çağrısı **sayacı** (ikinci tavan 4. aşaması, "likidasyon eşiğine yaklaşma" senaryosu) — **ancak** `mmr` tablosu ve marjin rejimi tanımıyla birlikte; tek başına yalnız "mark − spot" farkının dağılımını ölçer. |
| Kaynak | `data.binance.vision` `data/futures/um/monthly/markPriceKlines/<S>/1h/` (premiumIndexKlines ile aynı aile). **Varlığı ve kapsamı spike'ta listelenir**; burada varsayılmadı. 1m mark de aynı ağaçta olabilir — 1h'de görünmeyen likidasyon (B tasarımı model sınırı) için gerekip gerekmediği ölçüm tasarımında karara bağlanır; ilk kapsam 1h. |
| Sembol / timeframe | BTCUSDT, ETHUSDT — 1h, IS. |
| Mekanizma | `faz12_premium_indir.py`'nin doğrudan kopyası (önek değişir); hedef `data/turev/mark/<S>.parquet` + `.kaynak.json`. |
| Depo etkisi | Premium 1h BTC 2,4 MB → mark 1h 2 sembol **≈ 5 MB**. |
| Karar tipi | **Veri ekleme kararı**, küçük. |
| **Ayrı kararlar (bu veriyle karışmaz)** | (1) Marjin rejimi / hesap yapısı (isolated vs portföy marjini; spot teminat sayılır mı) — operasyon kararı; seçilmeden sayaç tek sayıya inmez, iki senaryo olarak raporlanır. (2) `mmr` kademe tablosu — anlık kayıt (spike); **geçmiş `mmr` değerleri arşivlenmediği için bugünkü tablo geçmişe uygulanamaz**: IS'e uygulanırsa sonuç "bugünkü kurallar 2020–2025 fiyat yoluna" varsayımı taşır ve rapor bunu **açık sınır** olarak yazar; PIT değildir, kapıya giremez (K-049/4 ruhu: geriye dönük türetim `leak_riski` benzeri işaretle). (3) `L` seçimi — K-033; ızgara verilir. |

## Özet: hangi karar neyi açar

| Karar | Boyut | Açtığı aşama | Tek başına yeter mi |
| --- | --- | --- | --- |
| A DTB3 | ≈ 0,2 MB, tek satır kod | §9/3 fırsat maliyeti | evet (yöntem notuyla) |
| B perp 1m | ≈ 220 MB, yeni araç + depo | §9/2 perp slippage | hayır — tarife kaydı (spike) da gerekir |
| C mark 1h | ≈ 5 MB, araç kopyası + depo | §9/4 likidasyon **fiyat yolu** | hayır — `mmr` (anlık, sınırlı) + marjin rejimi **kararı** gerekir |

Üçü de kapsam genişletmez: perp hâlâ bilgi kaynağı, işlem aracı değil (Final-Doküman v2).
Hiçbiri K-008/K-033/K-046/K-057'yi açmaz. Bu doküman hiçbirini vermedi; indirme yok.


---

## Uygulama kaydı (2026-09-20)

Scryne kararı: A → B → C sırası; A **tamamlandı**, B **slippage tamamlandı + fee DATA BLOCKED**, C **kararlar verildi + mark verisi doğrulandı; `mmr` yok**.

### A — DTB3: UYGULANDI

| | |
| --- | --- |
| Komut | `uv run python tools/faz12_makro_indir.py --ek` (yeni `--ek` bayrağı: yalnız `EK_SERILER = ("DTB3",)` iner; program serilerinin dosyalarına ve `_ozet.json`a **dokunmaz**) |
| Kaynak | `https://api.stlouisfed.org/fred/series/observations`, `series_id=DTB3`, ALFRED vintage, yıl-parçalı `realtime_start/end` (2017 → 2026), 10 parça |
| Kapsam | gözlem 2017-01-02 → 2026-09-17, 2.534 gözlem, 14.262 vintage satırı, 2.409 vintage tarihi; `vintage_olmayan_yillar: []` |
| Pin | `data/makro/DTB3.kaynak.json` (10 parça SHA-256, ilk parça `77f899ba0bee599c…`); `DTB3.parquet` SHA-256 `f24e48f08af6274d11486154accd26235d50969c116a0f2dbdf50c3e10752bd0` (dizin `.gitignore`'da; hash'ler buraya kopyalandı) |
| PIT | `data/makro.pit_gunluk` (K-060) aynen; IS 2020-01-01 → 2025-02-16'da NaN gün **0** |
| Boyut | +≈0,15 MB (`data/makro` 972 KB → 1,1 MB) |
| Açtığı ölçüm | `tools/faz16_hat1_b5_benchmark.py` → `runs/faz16/hat1_b5_benchmark.json`: benchmark BEY (birincil, `365·d/(360−91·d)`, kaynak Hazine/TreasuryDirect çevrimi) ve discount (ikincil); IS ortalaması BEY %2,60 / disc %2,53 (2020 0,37 · 2021 0,05 · 2022 2,05 · 2023 5,20 · 2024 5,11 · 2025 4,32); `r_excess` ve excess Sharpe **L×b ızgarası**, sembol + havuz; tutarlılık BTC günlük Sharpe = Adım 0 (9,477, eşit). İçerik hash'i iki koşuda aynı (`60993fa3…`). **İdeal − benchmark**; maliyet katmanı yok, ikinci tavan değil, karar yok. |

**Ayrı karar (Scryne, 2026-09-20: "şimdilik program kaydına dokunma"):**

> *Faz 16 DTB3 benchmark serisi, Faz 12'nin program serileri sözlüğüne (`makro.SERILER`) ve
> host `ScryneQuant-EvrenNFCI` açılış sözleşmesine dahil edilecek mi?*

Bu bir uygulama hatası değil, entegrasyon kararıdır ve **açık**. Verilene kadar:
`makro.SERILER` değiştirilmez, host görevi değiştirilmez, Faz 12 koşularının hash/kimlik
sözleşmesi bozulmaz; DTB3 `EK_SERILER + --ek` ile ayrı tutulur. Gerekçe: `makro.SERILER` (i) `bar_alanlari` üzerinden her `--makro` evren koşusunun alanlarını
ve koşu kimliğine giren dosya hash'lerini belirliyor (K-051/2: program kaydına bağlı; DTB3
eklenirse Faz 12 `makro_rejim` koşuları yeniden üretilemez), (ii) `live/evren_motor.py`
`ScryneQuant-EvrenNFCI` görevinin açılışta kurduğu seriler — hostta `DTB3.parquet` yoksa
yeniden başlatmada fail-closed durur (K-069 penceresi). Benchmark bir tavan girdisidir,
program alanı değil; tasarım §A'daki "girmez" satırı korundu. Eklenmesi isteniyorsa ayrı
karar: program kaydı güncellemesi + host senkronu.

### B — Perp 1m klines: UYGULANDI (slippage); tarife ÖLÇÜLEMEDİ

| | |
| --- | --- |
| Komut | `uv run python tools/faz16_perp_klines_indir.py` (yeni araç; `HttpArsiv` + `checksum_dogrula` + `dogrula` + `ParquetDepo`, src değişmedi) |
| Kaynak | `data.binance.vision` `data/futures/um/monthly/klines/{BTCUSDT,ETHUSDT}/1m/`, aylık zip + `.CHECKSUM`; **listeleme sonucu:** kapsam 2020-01 → 2025-02 filtresinde 62 ay/sembol |
| Format | spot ile aynı 12 sütun; **62 dosyanın 38'i başlık satırı taşıyor** (spot'ta yok) — atıldı, sayısı kaynak kaydında; `open_time` ms |
| Kapsam | sembol başına 2.715.840 bar, 2020-01-01 00:00 → 2025-02-28 23:59 UTC, boşluk 0, kapsama 1,0; `suspect` (sıfır hacim) BTC 351 / ETH 284 (K-006 bayrağı, doldurulmadı). Son ay dosyası IS bitişinden (02-16 18:00) sonrasını da içerir; **kesme ölçümde** |
| Pin | `data/turev/klines_1m/<S>/1m.kaynak.json` (62 zip SHA-256; ilk: `b4e13ea1…`); parquet SHA-256 BTC `db5f7a5a881eaef5a56ad1d916e00ef70b87884b7dd2c0742537cf3f70b28113`, ETH `f6622def36428418d6ac2a6bd1e770580eaf0d31828f58e9f92030eda5e2bcc3` |
| Depo | `data/turev/klines_1m/` (yeni; K-056/1 ayrı), 184 MB (tahmin 220) |
| Açtığı ölçüm | `tools/faz16_hat1_b1_perp_slippage.py` → `runs/faz16/hat1_b1_perp_slippage.json` (`kalibre_et`, p75, config'e **yazılmadı**): perp IS p75 **BTC 7,11 / ETH 9,11 bps**; örtüşme 2023-08 → 2025-02: perp BTC 5,83 / ETH 7,04, aynı pencerede spot BTC 5,67 (yürürlükteki spot config 5,30 = 2023-08 → 2026-09 penceresi, değişmedi). İçerik hash'i iki koşuda aynı (`087f4862…`). Seçim yok; iki pencere de raporlandı. |
| **Tarife** | **DATA BLOCKED — Scryne kararı (2026-09-20): şimdilik açılmaz.** Gerekçe: `c_perp` için gerekli gerçek ücret girdisi mevcut yöntemle doğrulanamıyor; herkese açık kaynak yalnız varsayımsal örnek içeriyor; imzalı erişim (`commissionRate`/`leverageBracket`) K-066 kapsamında ayrı bir güvenlik/erişim kararı. Bu karar verilene kadar: varsayımsal tablo kullanılmaz, BNB indirimi modele girmez, vadeli anahtar oluşturulmaz/kullanılmaz, K-066 açılmaz; fee bileşeni DATA BLOCKED, `c_perp` tamamlanmamış, config'e perp slippage yazılmaz, canlı/işlem davranışına etki yok. Ayrıntı: Herkese açık `binance.com/en/fee/futureFee` JS ile üretiliyor, HTML'de tablo yok ("No records found", giriş ister). Destek makalesi (360033544231) yalnız *varsayımsal* örnek veriyor (0,02 %/0,05 % — "assumed", **kullanılmadı**) ve BNB ile ödemede %10 indirim cümlesi (kaydedildi, varsayılmadı). İmzalı `GET /fapi/v1/commissionRate` vadeli yetkili anahtar ister; mevcut anahtar salt okunur spot (K-066) — sınır ihlal edilmedi, denenmedi. Sonuç: `c_perp_tek_yon` tamamlanamıyor; ikinci tavan 2. aşaması **hâlâ blocked** (slippage hazır, fee yok). |

### C — Mark price: iki karar verildi (Scryne, 2026-09-20), veri indirildi

**C-1 — Ölçüm rejimi: iki ayrı senaryo, tek rejim seçilmedi.**

| Senaryo | Varsayım | Uygunluk koşulu | Çıktı |
| --- | --- | --- | --- |
| `C-isolated` | perp bacağı yalnız kendi marjiniyle (`m·N` + tampon `b·N`) ayakta; spot bacağın değeri/kazancı teminat **sayılmaz**; funding marjine akar (negatif funding marjinden düşer) | her hesapta mevcut; ek şart yok | `L` ızgarası × sembol: marjin oranı < `mmr + tampon` sayısı ve tarihleri; likidasyon sayısı |
| `C-portfolio` | spot bacak teminat sayılır (portföy marjini / çapraz teminat); likidasyon iki bacağın toplam öz kaynağına bakar | hesap tipi/venue uygunluğu, asgari bakiye, teminat kesinti oranları (haircut) — **repoda yok**, kural kaydı ister | aynı ızgara; teminat haircut'ı parametre olarak ayrı satır |

Anlamı: ikisinin gerçek kullanımda eşdeğer olduğu **değil**, ölçümün marjin rejimine
duyarlılığının görünür kılınması. Hangisinin resmi kapı/rejim olacağı **ayrı ve açık** karar.

**C-2 — Tarihsel `mmr` / PIT: (c) ayrı satır / ayrı senaryo.**

| Sınıf | Tanım | Kullanım |
| --- | --- | --- |
| `PIT` | `mmr` tablosunun kaydedildiği andan **ileriye** dönük ölçüm (kayıt tarihi + kaynak + hash) | kapıya girebilir (K-054 çerçevesinde, program açılırsa) |
| `NON_PIT` (`leak_risk`) | bugünkü tablo 2020–2025 IS fiyat yoluna uygulanır | **resmi kapıya girmez**, doğrulanmış tarihsel sonuç gibi sunulmaz, yalnız duyarlılık/araştırma satırı; raporda her satır bu etiketi taşır |

MMR'nin tarihsel PIT arşivi olmadığı dönem bugünkü tabloyla "gerçek tarihsel veri" gibi
kapatılmaz. **MMR kararı (Scryne, 2026-09-20): iki sınıf da boş kalır.** Durum:

| Sınıf | Durum |
| --- | --- |
| PIT MMR | **EMPTY / veri yok** |
| NON_PIT · leak_risk MMR | **EMPTY / veri yok** |

K-066 kapalı olduğu sürece: imzalı `leverageBracket`/`commissionRate` denenmez, vadeli anahtar
istenmez/oluşturulmaz, public JS sayfasından MMR kazınıp tarihsel veri gibi kaydedilmez,
bugünkü tablo 2020–2025 IS'e uygulanmaz. Public sayfa yalnız erişilebilirlik/format keşfi
için incelenebilir; ölçüm girdisi üretmez. Tablo bir gün kaydedilirse kayıt tarihi PIT
sınırıdır, öncesi tamamen NON_PIT.

**Mark ≠ MMR:** mark serisi PIT'tir, indirildi ve doğrulandı; blocker yalnız MMR ve marjin
kurallarıdır. Sayaç üretimini bloke eden girdiler (varsayım üretilmez): MMR · bakım
marjı/likidasyon ücreti · otomatik marjin kuralları · portföy haircut + hesap uygunluğu.

**Açık küçük karar (backlog):** mark'taki tam-gün boşluklarının günlük arşivden
(`futures/um/daily/markPriceKlines`) doldurulması — açılmadı; mevcut seri doğrulamasıyla
ilerlenir, boşluk günü ölçümde "ölçülemez".

**Durum:** mark yolu ✅ · spot yolu ✅ · MMR ❌ · marjin/likidasyon girdileri ❌ →
stres/likidasyon sayacı **kapalı**. Sonraki aşama kod değil: eksik girdilerden hangisinin
metodolojik olarak gerçekten gerekli olduğunun belirlenmesi.

**İndirilen veri:** mark price 1h, BTC+ETH, 2020-01 → 2025-02, `tools/faz16_mark_indir.py`,
`data/turev/mark/<S>.parquet` + `.kaynak.json` (62 zip SHA); parquet SHA BTC `991e4ac5…`,
ETH `f9beee15…`; iki koşuda eşit; kapsama 0,9958 / 0,9989 (arşiv tarafı tam-gün boşlukları,
doldurulmadı); suspect 0. Doğrulama raporu: `docs/arsiv/Faz-16-Hat1-C-Veri-Dogrulama.md`.
Stres tavanı ve likidasyon sayacı **açılmadı** (`mmr` yok).

Tasarım gereği C'nin verisi (mark 1h) indirilmeden önce iki sınır çözülmeli; ikisi de
**Scryne kararı**, burada verilmedi:

1. **Ölçüm rejimi: isolated mı, portföy marjini mi?** Isolated: perp bacağı yalnız kendi
   marjiniyle ayakta, spot kazancı sayılmaz → likidasyon mesafesi `1/L − mmr` mertebesinde,
   A-5 MFE dağılımıyla (BTC 30 g p99 %108) `L ≥ 2`'de IS'te tekrarlayan likidasyon
   beklenir — bu bir tahmin değil, ölçülecek şey. Portföy marjini: spot teminat sayılır,
   likidasyon niteliksel olarak uzaklaşır, ama hesap tipi/venue şartları (uygunluk, asgari
   bakiye) operasyoneldir. Öneri yapılmıyor; ikisi de ayrı senaryo olarak ölçülebilir,
   **hangisinin "ölçüm rejimi" sayılacağı** karar.
2. **Geçmiş `mmr` PIT değil — hangi dönem/sınır?** Kademe tablosu yalnız anlık; 2020–2025'e
   uygulanırsa "bugünkü kurallar geçmiş fiyat yoluna" varsayımı. Seçenekler (karar):
   (a) sayaç yalnız **ileriye dönük** üretilir (tablo kaydedildiği günden itibaren, gölge
   gibi) — PIT temiz, örneklem takvim hızında; (b) IS'e uygulanır, `leak_riski` benzeri
   bayrakla, kapıya giremez, yalnız mertebe bilgisi; (c) ikisi birden, ayrı satır.
   Tablo kaydı için imzalı `leverageBracket` (anahtar, K-066) ya da herkese açık sayfa
   (JS riski, tarife sayfasında görüldü).

Bu iki karar verilmeden mark price indirilmedi, `mmr` tablosu kaydedilmedi, likidasyon
sayısı üretilmedi.

### K-066 eki uygulaması (2026-09-20)

Scryne K-066'yı iki salt okunur uç için açtı (`Kararlar.md` K-066 Ek). Deneme: mevcut spot
salt-okunur anahtar `commissionRate`/`leverageBracket` uçlarında **`-2015`** — vadeli okuma
yetkisi yok. Yetkili anahtar üretimi Scryne'ın eylemi; araç hazır
(`tools/faz16_vadeli_okuma.py`). Kaydedilen: likidasyon ücreti BTC/ETH `0.012500`
(`exchangeInfo`, 07:07:59 UTC, SHA `926d6672…`, PIT = kayıt anı). Formül: metin kısmı
provenance ile kayıtlı, görsel aktarılmadı. Durum: **A fee blocked · B MMR kademeleri blocked
(likidasyon ücreti ✓, formül metni ✓ kısmen) · PIT MMR EMPTY · NON_PIT MMR EMPTY**.
Ayrıntı: `docs/arsiv/spikes/08-vadeli-tarife-kademe.md`, `docs/arsiv/Faz-16-Hat1-Metodoloji-Denetimi.md`,
`docs/arsiv/Faz-16-Hat1-Fee-MMR-Erisilebilirlik.md`.

**Ek doğrulama (2026-09-20):** `apiRestrictions` → `enableReading=true`, **`enableFutures=false`**,
`enableSpotAndMarginTrading=false`, `enablePortfolioMarginTrading=false` (SHA `9fe27fdd…`).
UI'da "Enable Futures" seçeneği yok; resmî FAQ 360002502072: vadeli hesap açılmadan üretilmiş
anahtara Futures yetkisi verilemez. K-066 ekinin erişim yolu bu anahtarla **kapalı**; yeniden
değerlendirme `docs/arsiv/spikes/08-vadeli-tarife-kademe.md` §1b — karar Scryne'ın (vadeli hesap
açma = hesap/operasyon kararı; sonrasında yeni salt-okunur anahtar). Fee ve MMR kademeleri
blocked kalır.

**Karar (Scryne, 2026-09-20): vadeli hesap açılmıyor.** K-066 erişim yolu bu anahtarla
doğrulanmış şekilde **kapalı** kabul edildi; vadeli hesap açıp yeni anahtar üretmek araştırma
kapsamının zorunlu adımı değil. Kalıcı durum: fee / `commissionRate` **BLOCKED** · MMR
kademeleri / `leverageBracket` **BLOCKED** · PIT MMR **EMPTY** · NON_PIT MMR **EMPTY** ·
likidasyon-eşiği stres sınıfı **CLOSED / hesaplanamaz** · beş stres sınıfı hesaplamaya hazır ·
execution maliyeti **PARTIAL** (fee eksikliği açıkça korunur). Bundan sonra alternatif uç,
spot→perp taşıma, güncel MMR'yi geçmişe uygulama ya da başka varsayımla bu iki blokaj
aşılmaya çalışılmaz. Uygulama: `docs/arsiv/Faz-16-Hat1-Ikinci-Tavan-Kismi-Raporu.md` (tasarım §9
"eksik sınıf"), `tools/faz16_hat1_ikinci_tavan_kismi.py`.

**B-6 kararı (Scryne, 2026-09-20): AÇMA.** 26 sembol / ≈2,4 GB perp 1m slippage verisi mevcut
kararları değiştirmiyor; backlog'da bağımsız veri kararı olarak kalır. İndirme, hesaplama,
kapsam genişletme yok. Havuz için ikinci tavan (2)–(4) DATA BLOCKED; BTC+ETH sonuçları havuza
genellenmez. Sonraki adım: yeni veri değil, mevcut Hat 1 çıktısının metodolojik kapanışı.
