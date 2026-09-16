---
proje: ScryneQuant
created: 2026-09-16
type: faz-raporu
faz: 9
status: kapandi
---
# Faz 9 — Veri platformu v2: PIT, evren, enstrüman kimliği

> Ölçümler 2026-09-15/16'da yapıldı. Sayılar bu dosyadan alınır, tahmin edilmez.

## 1. İndirme: 735 sembol, 34.519 dosya, 0 hata

| | Değer |
| --- | ---: |
| İstenen sembol (arşivdeki USDT pariteleri) | 735 |
| Veri inen sembol | 734 |
| Arşivde 1h katmanı olmayan | 1 (`USDSOLDUSDT` — Spike 6 ile aynı) |
| İnen dosya (aylık + günlük zip) | 34.519 |
| Bar | 20.055.412 |
| Disk (parquet, zstd) | 628,1 MB |
| Süre | 4.297 s (71,6 dk), 32 iş parçacığı |
| Hata | 0 |

Depo `data/evren/`, `data/market/` **değil** — gerekçesi §4'te. Her sembolün yanında
`1h.kaynak.json` manifestosu var: indirilen her arşiv dosyasının adı ve SHA-256'sı.

**İdempotency evren ölçeğinde ölçüldü:** ertesi gün aynı komut 735 sembol için **0 dosya**
indirdi, **0 sembolde** dosya değişti (2.124 s, tamamı listeleme ve katman kontrolü).

**Boyut projeksiyonu tuttu.** Spike 6 ≈0,86 GB tahmin etmişti (25.955 sembol-ay); ölçülen
628 MB (34.519 dosya, kaldıraçlı ve stable pariteler dahil). K-011'in 500 MB'lık gözden
geçirme eşiği **dosya başına**dır; en büyük dosya BTCUSDT 1h = 3,7 MB (ETH 3,3 MB, BNB
2,9 MB). Düzen değişmiyor.

## 2. Arşivin dört tuzağı — dördü de ölçüldü

### 2a. Zaman damgası 2025-01'de mikrosaniyeye geçmiş

`BTCUSDT-1h-2024-12` ilk satır `1733011200000` (ms); `BTCUSDT-1h-2025-01` ilk satır
`1735689600000000` (**µs**). Aynı sütun, aynı düzen, 1000 kat fark. Fark edilmezse 2025
sonrası barlar 55.000 yıl ileriye düşer; sıralama ve boşluk hesabı sessizce bozulur.

Kural: birim sayının büyüklüğünden çıkarılır (sınır 10¹⁴), **dosya içinde karışık birim
reddedilir**, µs değeri 1000'e bölünmüyorsa reddedilir. Üçü de testte.

### 2b. Float ayrıştırma REST ile farkı kendi başına üretiyordu

pandas'ın varsayılan hızlı float ayrıştırıcısı 744 satırlık bir ayda **50** `quote_volume`
değerini 2,4e-7 kaydırdı. Veri seti kimliği dosyanın hash'i olduğu için (K-009) bu, aynı
veriye iki farklı kimlik demekti. `float_precision="round_trip"` ile fark sıfır.

### 2c. Arşiv REST'in birebir kopyası değil

BTCUSDT 1h'in REST'le ortak **45.576 barının 4'ünde** değerler farklı:

| Bar (UTC) | Fark |
| --- | --- |
| 2021-12-24 03:00 | hacim %1,8, işlem sayısı 767, kapanış 0,06 |
| 2021-12-24 04:00 | hacim %0,005 |
| 2021-12-27 07:00 | hacim %1,3 |
| 2022-04-13 05:00 | hacim %0,1 |

Hangisinin doğru olduğu **bilinmiyor** ve tahmin edilmedi. Sonuç: iki kaynak karıştırılmıyor.

### 2d. Izgaraya oturmayan barlar: 2018-02 kesintisi

`BTCUSDT-1h-2018-02` içinde 43 bar, açılışı 28 dk 14,789 sn kaymış olarak yazılmış
(2018-02-09 09:28:14.789 → 2018-02-11 03:28:14.789); Binance'in 2018-02-08 kesintisinden
sonraki yeniden başlatma. Aynı desen 6 sembolde, toplam **258 bar**: BCC, BNB, BTC, ETH,
LTC, NEO — hepsi 2018-02 dosyasında, her birinde 43 bar.

Bu barlar **atılıyor**, saate yuvarlanmıyor: 09:28–10:28 aralığının barı 09:00–10:00 barı
değildir, yuvarlamak olmayan bir barı varmış gibi göstermek olurdu (K-024). Atılan aralık
depoda `gap` bayrağı olarak görünür, sayısı manifestoda (`atilan_hizasiz_bar`) ve raporda.
Doğrulama katmanının K-005 kuralı **gevşetilmedi**; arşiv katmanı, tek bir kaymış aralık
yüzünden sembolün tüm geçmişini reddetmemek için bu barları kendisi ayıklar.

## 3. Kimlik kırılması: eşikler ölçüldü

734 sembolün 1h serisinde **3.598 boşluk** var. Boşluğun iki yanındaki fiyat oranı
(`sonraki açılış / önceki kapanış`) ile boşluk uzunluğunun dağılımı:

| eksik bar | \|ln oran\| < 0,1 | 0,1–1 | 1–2,3 | ≥ 2,3 | toplam |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.481 | 1 | 0 | 0 | 1.482 |
| 2–23 | 2.040 | 14 | 6 | 3 | 2.068 |
| 24–167 | 6 | 4 | 1 | 21 | 32 |
| 168–719 | 1 | 3 | 1 | 2 | 7 |
| 720+ | 7 | 1 | 0 | 1 | 9 |

**Dağılımda boş bir bant var:** eksik barı ≥ 12 olan boşluklarda `|ln oran|` 0,99 ile 2,30
arasında **hiçbir vaka yok**. Bandın üstündeki 28 vakanın tamamı bilinen kimlik değişimi:

| Vaka | Boşluk | Oran |
| --- | ---: | ---: |
| `LUNAUSDT` → yeni LUNA | 437 bar | 20.000 |
| `VENUSDT` → VET takası | 2.117 bar | 5,5e-05 |
| `SUNUSDT`, `COCOSUSDT`, `QUICKUSDT` (1:1000) | 96–101 bar | 1000 / 0,001 |
| `DREPUSDT`, `BNXUSDT` (1:100) | 96–149 bar | 100 / 0,01 |
| `BTCSTUSDT`, `STRAXUSDT`, `VIDTUSDT` (1:10) | 96–221 bar | 0,1 |
| Kaldıraçlı token ters bölünmeleri (13 sembol) | 23–24 bar | 17.000–179.000 |

Bandın altındaki en yakın vakalar **gerçek fiyat hareketi**: 2021-05-19 çöküşünde Binance'in
4 barlık kesintisi sırasında kaldıraçlı token'lar `|ln|` 3,02'ye kadar oynadı; kimlik
değişmedi. Bu yüzden:

- `KIRILMA_ASGARI_EKSIK_BAR = 12` — ölçülen yanlış-pozitif bölgesinin (≤4 bar) üç katı.
- `KIRILMA_ASGARI_LOG_ORAN = ln 10 = 2,3026` — boş bandın üst ucu ve en küçük gerçek
  redenominasyon oranı.

Eşikler **1h serileri için** ölçüldü; başka timeframe'de yeniden ölçülmeden kullanılmaz.
`tests/unit/test_kimlik.py` hem değerleri hem iki sınır vakasını (LUNA yakalanıyor,
2021-05-19 yakalanmıyor) kilitliyor.

Sonuç: 734 sembolde **27 kırılma, 24 sembol**; seriler 761 kanonik kimliğe bölündü. Kimlik
biçimi `binance-spot:<ticker>@<segmentin ilk barının UTC tarihi>` ve geriye doğru kararlı:
seriye yeni bar eklemek mevcut kimlikleri değiştirmiyor (testle).

## 4. Neden ayrı depo (`data/evren`)

1. **Hipotez defteri.** `data/market/BTCUSDT/1h.parquet`'in hash'i defterdeki 38 çekilişin
   `veri_sha256`sı (K-039). Arşiv verisini aynı dosyaya yazmak o kimliği değiştirirdi;
   geçmiş ölçümlerin yeniden üretilebilirliği yeni bir kaynağa feda edilmez.
2. **İki kaynak birebir aynı değil** (§2c). Birleştirmek, hangi barın hangi kaynaktan
   geldiğini dosyada görünmez kılardı.

Arşiv BTCUSDT 1h'i 2017-08'den başlıyor; REST dosyası 2021-06'dan. Aynı sembolün iki
kopyası bilinçli.

## 5. PIT evren tablosu

Kural: **M ayının üyeliği yalnızca M−1'in tamamlanmış verisiyle** kurulur — M−1 quote
hacmi (kendi barlarımızdan, `suspect` barlar hariç), enstrümanın M−1'in son gününde hâlâ
işlem görüyor olması, ve **kanonik kimlik** (ticker değil: yeni LUNA, eski LUNA'nın hacmiyle
evrene giremez).

Spike 6'nın parametreleriyle (N=50, aylık quote hacmi ≥ 30 M USDT) ölçülen tablo:

| | Değer |
| --- | ---: |
| Ay | 109 (2017-09 … 2026-09) |
| Satır | 4.464 |
| Üye olmuş kanonik kimlik | 432 |
| Bugün kapanmış olanlar | 99 (%22,9) |
| Aylık "bugün ölü" oranı: medyan / en kötü | **%16,7 / %33,3** |
| Kural kimliği (K-051/4) | `27b7a16ed0ed9725` |
| Tablo hash'i | `b06857c0737217ef…` |

Spike 6 aynı yanlılığı N=50 için medyan %18, en kötü %34 ölçmüştü; bağımsız bir yoldan
(kimlik bölünmesi + ay sonu listelenmişlik kuralı dahil) yeniden ölçüldü ve **tuttu**.

Tablo üretimi deterministik: aynı depo ve aynı kuralla ikinci koşu aynı `tablo_hash`'i
verdi (`b06857c0737217ef…`).

Kırılma sonrası kimliklerden beşi evrene üye oldu: `LUNAUSDT@2022-05-31`,
`BNXUSDT@2023-02-22`, `BTCSTUSDT@2021-03-19`, `COCOSUSDT@2021-01-23`, `SUNUSDT@2021-06-18`.
Kimlik ayrımı olmasaydı bu beş seri, kendilerinden önceki varlığın hacmi ve fiyat geçmişiyle
tek bir seri olarak görünecekti.

**Look-ahead testi yeşil:** M'den sonraki veri bozulduğunda (hacim çarpıtma, sahte kimlik
kırılması, gelecek barların silinmesi) M ve öncesinin üyeliği **bit düzeyinde** değişmiyor
(`tests/unit/test_evren.py::TestLookAhead`).

## 6. PIT gözlem deposu (bar olmayan veri)

`available_time_ms <= t` tek kesme kuralı. `event_time`e göre kesen bir uygulama testte
**kalır**: `kesme_sozlesmesini_dogrula` üç tuzaklı bir fixture'la (açıklanmamış kayıt,
sonradan gelen revizyon, tam t'de açıklanan kayıt) her kesiciyi sınar. Gün çözünürlüklü
available_time UTC gün sonuna yuvarlanır (K-007'nin zaman eksenindeki karşılığı).
Revizyonlar silinmiyor: geçmiş bir t'de görülen değer, sonradan revize edildi diye
değişmiyor (testle).

## 7. Veri sözleşmeleri ve katman tamlığı

Üç kaynağın sözleşmesi yazıldı (`data/sozlesme.py`): şema, cadence, zaman semantiği,
`available_time` kaynağı, tamlık kontrolü, revizyon davranışı, lisans, kanıt.
**Lisans alanı üçünde de "doğrulanmadı"** — Binance kullanım koşulları okunup kaynaklı
kaydedilmedi; tahmin yazılmadı. Bu Faz 9'un kapanmasını engellemiyor ama açık bir kalem.

Katman tamlığı her indirmede otomatik koşuyor: indirilen `1h` katmanının ayları, arşivin
türetilmiş `1mo` katmanıyla karşılaştırılıyor (Spike 6 §4b'nin sessiz boşluğu). Evren
genelinde ölçüldü (734 sembol):

| | Değer |
| --- | ---: |
| İki katmanı tam örtüşen sembol | 115 |
| `1mo`'da ay eksiği olan sembol | 619 |
| `1mo`'da olup `1h`'te olmayan sembol | 1 |
| `1h` katmanında iç boşluğu (aylık dosyası hiç olmayan ay) olan sembol | 9 |

En çok eksik olan aylar `1mo` tarafında: **2026-08 (491 sembol), 2026-07 (484), 2026-03
(441), 2024-03 (371)**. Yani Spike 6'nın tek bir ayda gördüğü boşluk kalıcı ve yaygın:
türetilmiş katman, sembollerin çoğunda son aylarda üretilmiyor. **Evren hacmi bu yüzden
kendi barlarımızdan hesaplanıyor** (K-056/6); `1mo` kullanılsaydı son üç ayın evreni
sessizce boşalırdı.

`1h` katmanındaki 9 iç boşluk 2022-10 … 2023-02 aylarında yoğunlaşıyor; bunlar delist edilip
sonra yeniden listelenen sembollerin arşivde dosyası olmayan aylarıdır — veri kaybı değil,
o aylarda işlem olmaması. Kimlik kırılması taraması (§3) bu boşlukların hepsine ayrıca bakıyor.

## 8. K-034 yeniden ölçümü (Faz 9'un bitti kriteri)

| # | Koşul | Eşik | **Ölçülen (2026-09-16)** | Gerçekleşti mi |
| --- | --- | ---: | ---: | --- |
| 1 | İkinci yazıcı süreç | — | Tek yazıcı; arşiv indirici tek süreç, dosya başına atomik `replace` | **Hayır** |
| 2a | Audit satır sayısı | 10.000.000 | **1.091** (değişmedi) | **Hayır** |
| 2b | `runs/` toplam boyut | 5 GB | **3,8 MB** | **Hayır** |
| 3 | Çok sembollü çalışma | — | **Araştırma tarafında gerçekleşti** (734 sembol, 628 MB parquet); operasyonel state hâlâ tek sembol ve tek koşu | Kısmen |

Koşul 3'ün doğurduğu soru *"operasyonel state'i PostgreSQL'e taşımalı mıyız"*dı. Ölçülen
yazma deseni bunu gerektirmiyor: çoklu sembol verisi **araştırma deposu** (parquet, K-011),
operasyonel state değil; yazıcı tek, transaction yok, eşzamanlılık yok. Karar değişmiyor;
gerekçe artık "henüz gerçekleşmedi" değil, **"gerçekleşti ve ölçüldü, gerektirmedi"**.
