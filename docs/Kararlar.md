---
proje: ScryneQuant
created: 2026-09-08
type: kararlar
status: aktif
---
# ScryneQuant — Karar Günlüğü

Bu dosya **neden** sorusunun cevabını tutar. `docs/Final-Dokuman.md` ne yapılacağını
söyler; burası o kararın hangi alternatifler arasından, hangi gerekçeyle seçildiğini
kaydeder.

Neden ayrı bir dosya: §19 reproducibility bu projede birinci sınıf gereksinim. Altı ay
sonra bir backtest sonucu tartışılırken "fee modelini neden böyle seçtik" sorusunun cevabı
bir yerde yazılı olmak zorunda; yoksa sonuç yeniden üretilemez, sadece tekrar hesaplanır.

**Kural:** karar değiştirilmez, üzerine yeni karar yazılır. Eski karar `Durum: değiştirildi
→ K-0XX` işaretiyle yerinde kalır. Bir karar koda dokunuyorsa ilgili commit mesajında
`K-0XX` referansı geçer.

**Durum etiketleri:** `kabul` (verildi, uygulanacak) · `açık` (spike bekliyor) ·
`değiştirildi` (yerine yenisi geçti)

---

## K-001 — Tek backtest motoru: event-driven

**Durum:** kabul · **Kapatır:** Denetim A1

**Karar:** v1'de tek bir **event-driven** backtest motoru olacak. VectorBT v1 kapsamından
çıkarıldı. Aynı strateji kodu backtest, paper trading ve live'da değişmeden çalışır.

**Gerekçe:** İki motor demek stratejinin fiilen iki kez yazılması ve "iki motor aynı sonucu
veriyor mu" diye sürekli bir doğrulama yükü demek. Bu uyuşmazlık ortaya çıktığında hangi
sonuca güvenileceği belirsizleşir — ki bu, backtest sonucuna güvenmenin tamamen anlamını
yitirmesidir.

Vektörize motorun tek gerçek avantajı hız; bu projenin ölçeğinde o avantaja ihtiyaç yok:
5 yıllık 1h BTC/USDT ≈ 44 bin bar, saf Python döngüsüyle saniyeler mertebesi. 1m'ye
inildiğinde ≈ 2,6 milyon bar, dakikalar mertebesi — parametre taraması için hâlâ kabul
edilebilir.

**Ölçüldü (Spike 2, 2026-09-08):** bu paragraf tahmindi; gerçek sayı daha iyi çıktı. Gerçekçi
bir döngü (dataclass `Signal`, risk kontrolü, equity/drawdown takibi) **1.800.526 bar/s**.
5 yıllık 1h'de **1000 parametrelik tarama 25 saniye**; 1m'de 24,3 dakika. Yani hız, K-017'nin
timeframe kararında bir etken bile olmadı — ve vektörize tarama katmanı ihtiyacı 1h için
görünürde yok. *Faz 3 sonunda gerçek motorla yeniden ölçülmeli.* Hız gerçekten darboğaz olduğunda vektörize bir **tarama** katmanı eklenebilir,
ama o katmanın çıktısı hiçbir zaman "sonuç" sayılmaz; sadece event-driven motorda
doğrulanacak aday parametreleri üretir.

**Alternatif neden reddedildi:** VectorBT + event-driven ikilisi araştırma hızını artırırdı,
ama §9.1'in `on_bar` sözleşmesi vektörize modelde karşılıksız kalıyor ve backtest ile paper
trading arasında ikinci bir kod yolu doğuyor — §45'in ölçmek istediği drift'in kaynağı tam
olarak budur.

---

## K-002 — Stratejiye geleceği gösteren nesne verilmez

**Durum:** kabul · **Kapatır:** Denetim A2

**Karar:** Strateji `on_bar(ctx)` çağrısında ham DataFrame almaz. `ctx` yalnızca **t anına
kadar** kesilmiş, salt-okunur bir görünüm sunar. Geleceğe erişim mümkün olmayacak şekilde
tip düzeyinde engellenir; ihlal denemesi hata fırlatır.

Bu sözleşmenin doğruluğunu kanıtlayan bir test birinci sınıftır ve Faz 2'nin bitti
kriterindedir: veri setinin `t` sonrası tamamı bozulduğunda (NaN veya rastgele değerle
doldurulduğunda) backtest sonucu **bit düzeyinde aynı** kalmalıdır. Değişiyorsa look-ahead
vardır.

**Gerekçe:** Look-ahead bias'ın maliyeti asimetrik: backtest'te sonucu iyileştirir, canlıda
zarara çevirir — yani kendini fark ettirmeyen tek yönlü bir hata. Disipline
bırakılamayacak kadar tehlikeli; yapısal olarak imkânsız kılınmalı. Bu test sonradan
eklenemez, sözleşmenin ilk günü kurulmalıdır.

---

## K-003 — Strateji katmanı I/O yapamaz

**Durum:** kabul · **Kapatır:** Denetim A3

**Karar:** Strateji modülleri exchange istemcisi, ağ, dosya sistemi veya veritabanına
erişemez. Strateji yalnızca `ctx`'ten okur ve bir `Signal` döndürür; başka hiçbir yan
etkisi olamaz.

Zorlama iki katmanlı: (1) mimari — strateji paketi exchange/execution paketlerine bağımlı
olmaz; (2) test — strateji paketinin import grafiği taranır, yasaklı bağımlılık (`ccxt`,
`requests`, `httpx`, `socket`, `open`) bulunursa test kırmızıya döner.

**Gerekçe:** §9.1 bu ayrımı "güvenlik mimarisinin temeli" ilan ediyor ama bir mekanizma
tanımlamıyor. Zorlanmayan mimari kural, kural değil temennidir — ve bu temenninin bozulduğu
gün risk motoru bypass edilmiş olur, yani projenin tek gerçek koruması ortadan kalkar.

---

## K-004 — Bar kapanışı ve fill semantiği

**Durum:** kabul · **Kapatır:** Denetim B1

**Karar:**
- Sinyal yalnızca **kapanmış** bar üzerinde üretilir. Yarım bar ile karar verilmez.
- `t` barında üretilen sinyal **`t+1` barının açılış fiyatından** doldurulur.
- Fill fiyatına slippage her zaman **aleyhte** uygulanır (K-007).
- Bir barın kendi `close` fiyatından doldurma yasaktır.

**Gerekçe:** Sinyalin üretildiği barın kapanış fiyatından doldurmak, karar anında henüz
bilinmeyen bir fiyatı kullanmak demektir — gizli bir look-ahead. Gerçekte bar kapandığı an
emir gönderilir ve bir sonraki fiyat seviyesinde dolar. `t+1` açılışı, gerçekliğe en yakın
ve muhafazakâr olan varsayımdır.

**Sonucu:** Bu kural tek başına backtest getirilerini kâğıt üzerinde düşürür. Bu bir kayıp
değil, kâğıt üzerindeki sahte kazancın kaldırılmasıdır (§4.3 No Fake Alpha).

---

## K-005 — Zaman: UTC, epoch ms, bar timestamp'i açılıştır

**Durum:** kabul · **Kapatır:** Denetim B2

**Karar:** Sistemde hiçbir yerde yerel saat kullanılmaz. Depolamada ve iş mantığında zaman
**UTC epoch milisaniye**. Bir mumun `timestamp` alanı o mumun **açılış** zamanıdır. Yerel
saat (UTC+3) yalnızca arayüzde, gösterim anında uygulanır ve gösterildiği yerde saat dilimi
etiketi zorunludur.

**Gerekçe:** Türkiye UTC+3. Karışık saat dilimi, backtest'te "çalışıyor gibi görünen" ama
canlıda barları kaydıran hatalar üretir; bu hata sınıfı sessizdir çünkü sonuç makul
görünmeye devam eder. Ayrıca §38'deki clock drift kontrolü ancak tek bir zaman referansı
varsa anlamlıdır.

---

## K-006 — Veri kalitesi bayrakları ve backtest'e etkisi

**Durum:** kabul · **Kapatır:** Denetim B3

**Karar:** `quality_status` şu değerleri alır:

| Değer | Anlamı |
| --- | --- |
| `ok` | Doğrulamalardan geçti |
| `gap` | Öncesinde eksik bar var |
| `duplicate` | Aynı timestamp tekrar geldi, tekilleştirildi |
| `suspect` | Aykırı hareket / sıfır hacim / OHLC tutarsızlığı |
| `backfilled` | Sonradan tamamlandı, birincil akıştan gelmedi |

**Backtest kuralı:** `ok` dışındaki barlar **sessizce kullanılmaz**. Backtest, çalıştığı
aralıktaki `ok` olmayan bar sayısını sonuç kaydına yazar; oran bir eşiği aşarsa sonuç
`data_quality_warning` bayrağıyla işaretlenir ve **promotion'a giremez** (K-010).

**Gerekçe:** Veri boşluğunun üzerinden atlayan bir backtest yanlış sonucu sessizce üretir —
en tehlikeli hata sınıfı budur, çünkü hiçbir uyarı vermez. §16.4'ün survivorship bias
endişesinin aynı ailesi.

---

## K-007 — Maliyet modeli: muhafazakâr ve açık

**Durum:** kabul · **Kapatır:** Denetim B4

**Karar:** v1 varsayımları — hepsi konfigürasyondan gelir, kodda gömülü sabit yoktur ve her
backtest sonucuna hangi değerlerle çalıştığı yazılır:

- **Komisyon:** her iki bacakta da **taker** varsayılır. Maker indirimi varsayılmaz.
- **Slippage:** girişte ve çıkışta sabit bps, **her zaman aleyhte** (alışta yukarı, satışta
  aşağı).
- **Spread:** modelin içinde ayrıca sayılmaz; slippage varsayımı spread'i kapsayacak kadar
  yüksek tutulur.
- **Ölçülen değerler (Spike 4, 2026-09-08 — `docs/spikes/04-maliyet-tarifesi.md`):**
  `fee_taker_bps = 10.0` (Binance VIP 0 spot, BNB indirimi varsayılmıyor),
  `slippage_bps = 5.0` **geçici** — Faz 1'de kalibre edilecek (K-021; ilk yöntem K-020 idi,
  ölçüm onu çürüttü). Geçici değerle üretilen hiçbir sonuç promotion'a giremez.

**Spike 4'ün düzelttiği varsayım:** yukarıdaki "slippage varsayımı spread'i kapsayacak kadar
yüksek tutulur" cümlesi yanlış bir modele dayanıyordu. Ölçüm: BTC/USDT spread'i 0,00128 bps,
komisyon 20 bps — komisyon spread'den ~15.600 kat büyük, yani spread bu projede bir maliyet
kalemi değil. K-004'ün `t+1` açılış fill'i göz önüne alındığında `slippage_bps` aslında bir
**fiyat hareketi** proxy'sidir, mikroyapı proxy'si değil. Bkz. K-021.

**Spike 2'nin ayrıca düzelttiği (2026-09-08):** Spike 4 yönü doğru bulmuştu ama ölçülecek
aralığı yanlış seçmişti. `open[t+1] − close[t]` bir bar boyu belirsizlik değil, birkaç
milisaniyedir (ölçüldü: 1h'de vakaların %52,2'sinde iki fiyat birebir aynı). Gerçek pencere
bar kapanışı ile emrin dolması arasıdır. Ayrıntı: K-021.

**Yön kuralı:** belirsizlik olduğunda her zaman aleyhte yuvarla. Backtest gerçeğinden kötü
çıkarsa sürpriz iyi olur; iyi çıkarsa sürpriz para kaybettirir.

**Gerekçe:** §55 slippage'ın hafife alınmasını "yüksek olasılık / yüksek etki" olarak
işaretliyor ve haklı: yüksek frekanslı, çok işlemli stratejilerde maliyet modeli tek başına
kârlı görünen bir stratejiyi zararlıya çevirebilir. Maliyet varsayımı stratejinin bir
parçasıdır, dipnot değil.

---

## K-008 — Kill switch davranışı (spot)

**Durum:** kabul · **Kapatır:** Denetim B5

**Karar:** Kill switch tetiklendiğinde:

1. **Yeni pozisyon girişi durur** — istisnasız.
2. **Açık pozisyonlar piyasadan otomatik kapatılmaz.**
3. **Mevcut çıkış emirleri (stop / take-profit) çalışmaya devam eder.**
4. Sistem `SAFE_MODE`'a geçer; bu durumdan çıkış yalnızca **elle onayla** olur.
5. Tetikleyen sebep, o andaki tüm pozisyon ve emir durumuyla birlikte audit log'a yazılır.

**Gerekçe:** Kill switch çoğunlukla "bir şeyler yanlış" sinyaliyle tetiklenir — bozuk veri,
bağlantı kaybı, beklenmedik state. Böyle bir anda **panik satışı yapmak, sorunu çözmek
değil zararı gerçekleştirmektir**; üstelik sorun kill switch'i tetikleyen şeyse kapatma
emirlerinin doğru gitmesi de garanti değil. Spot piyasada likidasyon riski olmadığı için
pozisyonu tutmak güvenlidir — bu karar futures'a geçilirse **yeniden verilmelidir**
(likidasyon varsa tutmak güvenli değildir).

---

## K-009 — Kirli working tree ile üretilen backtest promotion'a giremez

**Durum:** kabul · **Kapatır:** Denetim B6

**Karar:** Her backtest çalıştırması kayıt altına şunları alır: git commit SHA, working
tree'nin kirli olup olmadığı, veri seti hash'i, config hash'i, rastgelelik seed'i, kütüphane
sürümleri.

Working tree kirliyse çalıştırma **engellenmez** — araştırma sırasında sürekli kirli olur —
ama sonuç `dirty: true` işaretlenir ve **promotion zincirine giremez** (K-010). Live'a aday
olan her sonuç temiz bir ağaçtan üretilmiş olmak zorundadır.

**Gerekçe:** §19 "git commit reference tutulmalı" diyor ama kirli ağaçta o referans yalan
söyler: kaydedilen commit, sonucu üreten kodu tarif etmez. Reproducibility iddiası ancak bu
kural varsa doğrudur.

---

## K-010 — Promotion gate MVP kapsamındadır

**Durum:** kabul · **Kapatır:** Denetim A4

**Karar:** §43'ün promotion zinciri opsiyonel değil, MVP'nin parçası. Bir strateji live'a
elle bir toggle ile alınamaz; şu kapılardan geçmek zorundadır:

```
BACKTEST → KALİTE KONTROL → OUT-OF-SAMPLE → RİSK İNCELEMESİ
        → PAPER → LIVE ADAYI → ELLE ONAY → LIVE
```

Her kapının geçme koşulu makine tarafından kontrol edilir ve sonucu kaydedilir. `dirty`
(K-009) veya `data_quality_warning` (K-006) işaretli hiçbir sonuç kapıdan geçemez. Son
adımdaki elle onay kaldırılamaz.

**Gerekçe:** Bu proje sahibinin beyan ettiği amaç para kazanmak; dokümanın kendi §56'sı ise
bunun en tehlikeli yanılgıyı doğurduğunu yazıyor. İkisi arasındaki gerilim iyi niyetle
çözülmez — sabırsızlanıldığı gün karar veren kişi ile korunması gereken kişi aynı kişidir.
Bu yüzden kapı **sistemde** olmalı: bugünkü Scryne, altı ay sonraki sabırsız Scryne'a karşı
şimdi karar veriyor.

---

## K-011 — Veri saklama: Parquet + DuckDB (tarihsel), PostgreSQL (operasyonel, Faz 5+)

**Durum:** kabul · **Kapatır:** Denetim C1 · **Değiştirir:** Proje-Fikri §7, §30 ·
**Doğrulandı:** Spike 3 (2026-09-08)

**Karar:** İki katmanlı:

- **Tarihsel market data** → sembol/timeframe bazında bölümlenmiş **Parquet** dosyaları,
  sorgu için **DuckDB**. Faz 1-4'ün tamamı bununla çalışır.
- **Operasyonel state** (emir, pozisyon, çalıştırma kaydı, audit log) → **PostgreSQL**,
  Faz 5'te gelir.
- **TimescaleDB v1'de yok.** Redis v1'de yok.

**Gerekçe:** Faz 1-4 boyunca tarihsel veriye yapılan tek şey toplu okuma; bu iş yükü için
sunucu süreci çalıştırmanın hiçbir getirisi yok, sadece operasyonel yük var. Parquet ayrıca
reproducibility'ye birebir uyuyor: dosya içerik hash'i alınabiliyor, kopyalanabiliyor,
sürümlenebiliyor — canlı bir veritabanının durumu için aynısı geçerli değil.

PostgreSQL asıl olarak eşzamanlı yazma, transaction ve dayanıklı state gerektiğinde
(paper/live) anlamlı. O noktada zaten gerekli olacak; şimdi kurmak erken.

**Spike 3'ün doğruladığı ve eklediği (2026-09-08, `docs/spikes/03-parquet-duckdb.md`):**

Seçim ölçümle onaylandı, hiçbir eşik zorlanmadı: 5 yıllık 1m verisi 71 MB, tamamı 0,12 s'de
RAM'e giriyor, en ağır sorgu (1m→1h yeniden örneklem) 87 ms. Karara üç somut değer eklendi:

- **Sıkıştırma `zstd`** — 525k bar için 14,21 MB / 0,190 s yazma / 0,022 s okuma. brotli %17
  daha küçük ama 12 kat yavaş yazıyor; gzip 33 kat. snappy %30 daha büyük, okuma avantajı 3 ms.
- **Sembol/timeframe başına tek dosya** — yıl/ay bölümleme bu ölçekte %18 *daha çok* yer
  kaplıyor (16,73 vs 14,21 MB) ve kazandırdığı 11 ms hissedilmiyor. *Gözden geçirme koşulu:
  tek dosya 500 MB'ı aştığında veya çok sembollü çalışmaya geçildiğinde.*
- **Veri seti hash'i = Parquet dosyasının SHA-256'sı** — aynı DataFrame iki kez yazıldığında
  çıktı **bit düzeyinde aynı** (zstd ve snappy'de doğrulandı). K-009 ayrı bir içerik-hash
  mekanizması gerektirmiyor.

DuckDB'nin native tablo formatı ölçüldü ve **bilerek reddedildi**: %42 daha küçük (8,26 MB) ve
sorgusu 25 kat hızlı (0,6 vs 15,1 ms), ama canlı bir veritabanı durumu hash'lenemez. Bu projede
reproducibility birinci sınıf, 15 milisaniye hiçbir yerde darboğaz değil.

**Faz 1 uygulaması — yazım parametreleri dondurulmuştur.** Dosyanın SHA-256'sı kimlik
olduğuna göre, hash'i etkileyen her şey karar kapsamındadır. `data/depo.py` şunları açıkça
sabitler; değiştirilmesi mevcut tüm dosyaların kimliğini değiştirir:

- **pandas metadata'sı yazılmaz.** `pa.Table.from_pandas` dosyaya pandas sürümünü ve index
  şemasını gömer; pandas güncellenince aynı veri farklı hash verirdi. Bunun yerine açık
  Arrow şemasıyla tablo kuruluyor. (Testle korunuyor: dosyada `pandas_version` geçmemeli.)
- **Sıkıştırma seviyesi, `row_group_size` ve parquet sürümü açıkça veriliyor** — hepsinin
  kütüphane varsayılanı sürümle değişebilir ve dosya düzenini etkiler.
- **Satırlar `open_time`'a göre sıralı ve tekil**; gelen sıra dosyaya sızmaz. Çakışmada
  **son** kayıt tutulur (yeniden indirilen aralık daha güncel veridir).

Kanıt: iki ayrı Python sürecinde yazılan 26.281 barlık gerçek BTC/USDT verisi bit düzeyinde
aynı çıktı (`tests/unit/test_depo_surecler_arasi.py`).

---

## K-012 — Arayüz Faz 6'da başlar; öncesi CLI + notebook

**Durum:** kabul · **Kapatır:** Denetim C2 · **Değiştirir:** Proje-Fikri §28

**Karar:** Web dashboard Faz 6'da (paper trading ile birlikte) başlar. Faz 1-5'in arayüzü
CLI ve Jupyter notebook'tur. İlk sürümde §28'in 10 sayfası değil **4 sayfa** yapılır:
Overview, Strategies, Positions, Logs. Kalan altı sayfa Faz 7+'ya bırakıldı.

**Gerekçe:** Faz 1-4'ün ürettiği şey sonuç tablosu ve grafik — notebook bunun için web
arayüzünden iyi. Dashboard'un asıl gerekçesi "sürekli çalışan bir şeyi izlemek"tir ve o
ihtiyaç ilk kez paper trading'de doğar. Daha erken yazılan her ekran, henüz kararlaşmamış
bir veri modelinin üstüne kurulur ve yeniden yazılır.

---

## K-013 — ML ve LLM v1 kapsamı dışında

**Durum:** kabul · **Kapatır:** Denetim C3 · **Değiştirir:** Proje-Fikri §36, §58

**Karar:** ML katmanı, LLM ve multi-agent research assistant v1 kapsamında **yok**. Bu
alanlar "Gelecek" başlığında birer satır olarak durur. §37'nin gerekçesi aynen kabul edildi
ve kapsam kararına dönüştürüldü.

**Gerekçe:** ML'in bu projede eklediği tek şey overfitting yüzeyini büyütmek olurdu —
projenin en yüksek olasılıklı riski zaten overfitting (§55). Rule-based stratejilerle
sağlam bir araştırma disiplini kurulmadan ML eklemek, ölçemediğin şeyi karmaşıklaştırmak
demek.

---

## K-014 — Yalnızca kendi hesabı, kendi parası

**Durum:** kabul · **Kapatır:** Denetim D (§51 eki)

**Karar:** Sistem yalnızca Scryne'ın kendi borsa hesabında, kendi sermayesiyle çalışır. v1
ve öngörülebilir gelecekte **kesin yasak**: başkasının hesabını yönetmek, sinyal satmak veya
paylaşmak, copy trading, ortak havuz, ücretli erişim, herhangi bir kamuya açık servis.

Bu çizgi teknik değil hukuki: geçildiği anda 7518 sayılı Kanun kapsamında SPK'nın düzenleme
alanına girilir (§51). Bu kapıdan geçmeden önce hukukçu değerlendirmesi zorunludur.

**Gerekçe:** Bu tür projelerde çizgi kazara geçilir — bir arkadaşa "sen de kullan" demekle
başlar. Yasağın yazılı olması, o anın fark edilmesini sağlar.

---

## K-018 — Eğitim fazı kapsam dışı; operatör yargısı yerine makine eşiği

**Durum:** kabul · **Kapatır:** Denetim C4 · **Tarih:** 2026-09-08

**Karar:** Faz 0'ın trading eğitimi kısmı Scryne'ın kararıyla kaldırıldı. Faz 0 yalnızca
teknik doğrulama (spike) fazıdır.

Bunun **zorunlu mimari sonucu**: sistemin hiçbir güvenlik kontrolü operatörün piyasa
bilgisine dayanamaz. Bu yüzden:

1. **K-010'un kapıları sayısal eşiklerle tanımlanır ve makine kontrol eder.** "Sonuçlara
   bak ve karar ver" bir kapı değildir. Her kapı geçer/kalır döndüren bir kontroldür.
2. **Son adımdaki elle onay yerinde kalır** ama artık son savunma değil, son formalitedir.
   Onaydan önceki kapılar geçilmemişse onay ekranı zaten açılmaz.
3. **Eşikler Faz 4 sonunda gerçek veriyle kalibre edilir** ve K-019 olarak yazılır. Adayları:
   OOS/IS Sharpe oranı alt sınırı, max drawdown üst sınırı, minimum işlem sayısı,
   paper-backtest drift üst sınırı, parametre duyarlılığı üst sınırı.
4. **Faz 3'ün doğruluk referansı elle hesaba dayanamaz.** Referans senaryonun beklenen P&L'i
   `tests/fixtures/` altına bağımsız olarak sabitlenir; motorun kendi çıktısından
   türetilemez.

**Gerekçe:** Bir kontrolün etkili olması, onu uygulayan tarafın onu uygulayabilmesine
bağlıdır. Eğitim kapsam dışına alındığına göre, kontrolün ağırlığı insandan sisteme
kaydırılmak zorundaydı — aksi hâlde kapılar kâğıt üzerinde var, pratikte yoktu.

Bu, K-010'u zayıflatmaz; **sertleştirir.** İnsan yargısına bırakılan bir kapı esnetilebilir,
sayısal eşik esnetilemez — değiştirmek için karar günlüğüne yazmak gerekir ve bu iz bırakır.

---

## K-015 — Binance erişimi: coğrafi engel yok, testnet ayakta

**Durum:** kabul · **Kaynak:** Spike 1 · **Tarih:** 2026-09-08 ·
**Rapor:** `docs/spikes/01-binance-erisim.md`

**Karar:** Binance'e Türkiye'den erişim doğrulandı. Faz 1'in indiricisi ve Faz 7'nin testnet
planı bu temele kurulabilir.

**Ölçülen kanıt (2026-09-08, 19:53 UTC, VPN yok):**

- **Coğrafi engel yok.** Kimlik doğrulamalı endpoint'lere anahtarsız istek **400/401**
  (`-1102 signature missing`, `-2014 API-key format invalid`) döndürdü — coğrafi engelin
  imzası olan **451 hiçbir istekte görülmedi**. `/sapi/v1/system/status` →
  `{"status":0,"msg":"normal"}`. İstek Binance'in anahtar doğrulama katmanına ulaşıyor.
- **Gecikme:** altı host, 60/60 başarılı istek, p50 260–360 ms, kuyruk 1,6 s'ye çıkıyor.
- **Rate limit:** beyan 6.000 weight/dk; **ölçülen tüketim klines çağrısı başına sabit 2**
  (`limit` 100 de olsa 1000 de olsa). Teorik tavan 3.000.000 bar/dk. **Rate limit bu proje
  için darboğaz değil.**
- **Spot Testnet ayakta** ve canlıyı takip ediyor: aynı üç saatlik barda fiyat sapması
  **%0,007**. `ccxt.set_sandbox_mode(True)` doğru host'a yöneliyor.
- **Saat farkı:** yerel − sunucu = **−153,2 ms** (güvenli yön).
- **BTCUSDT emir kuralları (Faz 7):** tick 0,01 USDT · step 0,00001 BTC ·
  **minNotional 5,00 USDT** · status TRADING.

**Ölçümden Faz 1/7'ye bağlayıcı geçen kurallar:**

1. **Kapanmamış bar depoya yazılmaz.** REST `klines` her zaman devam eden barı son eleman
   olarak döndürüyor ve o bar çağrılar arasında **değişiyor** (3 saniye arayla iki istekte
   son bar farklı, sondan önceki aynı). Kapanmışlık bayrağı REST'te yok — o bayrak yalnızca
   WebSocket akışında var; tek güvenilir kural `close_time < serverTime`. **Faz 1'in
   idempotency kriteri bu kural olmadan sağlanamaz** — aynı komut iki kez çalıştırıldığında
   dosya farklı çıkar.
2. **Her zaman `limit=1000`** — weight çağrı başına sabit; küçük sayfa istemek saf kayıp.
3. **IPv4'e zorla veya kalıcı session kullan.** Yerel çözümleyici `*.binance.vision` için
   AAAA sorgusunu ~12 saniye sonra düşürüyor; `AF_UNSPEC` varsayılanıyla **her yeni bağlantı
   12 saniye gecikiyor** (ölçüldü: 12.098 ms vs 26,6 ms). Binance'e ait değil, ortama ait —
   ama koda bakarak anlaşılmaz, o yüzden burada yazılı.
4. **Timeout ≥ 5 s ve retry'lı** — ölçülen kuyruk gecikmesi 1,6 s.
5. **Tarihsel indirme `data-api.binance.vision` üzerinden** — p50 277,6 ms, ve emir
   trafiğiyle aynı IP weight havuzunu paylaşmaz.
6. **`load_markets()` önbelleğe alınır** — 3,2 s sürüyor ve 4.619 marketin tamamını çekiyor;
   tek sembolle çalışan bir sistemde her başlatmada ödenmemeli.
7. **Clock-drift kontrolü Faz 7'nin ön koşulu** — fark +1000 ms'i aşarsa imzalı istekler
   sessizce reddedilir.

**Kapanmayan kısım — dürüst sınır:** Bu ölçüm elde API anahtarı olmadan yapıldı. Kanıtlanan:
kimlik doğrulamalı yol Türkiye'den **açık**. Kanıtlanmayan: hesap açma, KYC ve o hesabın
spot işlem yetkisi — bunlar teknik değil idari adımlar, ölçülemezdi. **Testnet anahtarı**
(KYC'siz, GitHub hesabıyla alınır) Faz 7'nin, **canlı hesap + API anahtarı** Faz 8'in ön
koşulu olarak Roadmap'e yazıldı. O noktada bu spike'ın kimlik doğrulama kısmı gerçek
anahtarla **tekrarlanmalıdır**; bugünkü kanıt "yol açık" der, "hesap çalışıyor" demez.

---

## K-017 — Birincil timeframe: 1h

**Durum:** kabul · **Kaynak:** Spike 2 · **Tarih:** 2026-09-08 ·
**Rapor:** `docs/spikes/02-veri-hacmi.md`

**Karar:** **Birincil timeframe 1h.** Strateji, backtest ve promotion 1h barı üzerinde
çalışır. 1m verisi indirilir ve saklanır ama strateji timeframe'i değildir.

**Kararı veren ölçüm — hacim değil, hareket/maliyet oranı.**

Önce elenen gerekçeler: ne depolama, ne indirme, ne hesaplama kısıt çıktı.

| | 1h (5 yıl) | 1m (5 yıl) |
| --- | --- | --- |
| Bar | 43.800 | 2.628.000 |
| Parquet (zstd) | 1,66 MB | 71,04 MB |
| İndirme | 0,26 dk | 12,31 dk |
| RAM | 2,33 MB | 140,35 MB |
| 1000 parametrelik tarama | 0,41 dk | 24,3 dk |

Hepsi rahat. Karar bu yüzden başka bir yerden geldi — **Spike 4'ün ölçtüğü 20,02 bps
gidiş-dönüş maliyetine karşı bir barın tipik hareketi:**

```
Gidiş-dönüş maliyeti        : 20,02 bps   (Spike 4)
Medyan 1 saatlik hareket    : 20,85 bps   -> oran ~1
Medyan 1 dakikalık hareket  :  2,42 bps   -> oran ~1/8
```

**1m barda çalışan bir strateji, tipik bir barın 8 katı büyüklüğünde bir hareketi yakalamak
zorundadır — sadece başabaş kalmak için.** 1h'de bu engel 8,6 kat daha alçak. İkisi de kolay
değil; biri diğerinden ölçülebilir biçimde daha zor.

Bu, "daha çok bar = daha çok fırsat" sezgisinin tersini söylüyor: bar başına hareket
küçülürken bar başına sabit maliyet aynı kalıyor.

**1m verisi neden yine de indirilir:** (1) K-021'in slippage kalibrasyonu — 1h barın
içindeki fiyat yolunu görmenin tek yolu; (2) Faz 3'ün fill gerçekçiliği — bir 1h bar içinde
stop'un tetiklenip tetiklenmediği 1h OHLC'den **tahmindir**, 1m'den **ölçümdür**; (3) Faz
7'nin emir testleri dakika ölçeğinde davranır.

**Faz 1'de indirilecek:** BTC/USDT **1h, 5 yıl** (birincil) + **1m, 3 yıl** (yardımcı).
Ölçülenden projeksiyon: ~1,7 MB + ~43 MB parquet, toplam ~8 dakika.

**Ölçümün yan bulguları — üçü de sonraki fazları bağlıyor:**

- **Veri kusursuz çıktı.** 3 yıllık 1h (26.281 bar) ve 1 yıllık 1m (525.601 bar) verisinde
  **sıfır** eksik bar, sıfır tekrar eden timestamp, sıfır OHLC tutarsızlığı, sıfır
  sıfır-hacimli bar. **Sonucu:** K-006'nın kalite bayrakları gerçek veriyle hiç
  tetiklenmeyecek; o kod yolları **yapay bozuk fixture** ile test edilmek zorunda. Aksi
  hâlde hiç çalıştırılmamış bir güvenlik mekanizmasına güvenmiş oluruz.
- **K-001'in hız tahmini fazla karamsardı.** Gerçekçi bir döngü (dataclass `Signal`, risk
  kontrolü, equity/drawdown takibi, trade listesi) **1.800.526 bar/s** ölçtü; asgari döngü
  5.147.117 bar/s. 1h'de 5 yıllık 1000 parametrelik tarama **25 saniye**. K-001'in
  "vektörize tarama katmanı gerekebilir" ihtiyatı 1h için gereksiz. *Bu sayı Faz 3 sonunda
  gerçek motorla yeniden ölçülmeli — gerçekçi varyant bile bir üst sınır tahminidir.*
- **İndirme ağ sınırlı, rate limit sınırlı değil** — 526 çağrı yalnızca 224 weight harcadı
  (limit 6.000/dk) ve ağ süresi duvar saatinin %99'u. Faz 1'de hız gerekirse kazanç
  paralellikten gelir, kuyruk optimizasyonundan değil.

---

## K-020 — Slippage parametresi veriden kalibre edilir, tahmin edilmez

**Durum:** değiştirildi → K-021 · **Kaynak:** Spike 4 · **Tarih:** 2026-09-08

**Karar:** `slippage_bps` bir tahmin değil, ölçüm olacak. Faz 1'de tarihsel veri geldiğinde
`|open[t+1] − close[t]| / close[t]` dağılımı hesaplanır ve muhafazakâr bir yüzdelik alınır
(medyan değil, 75. persentil ya da daha yukarısı — yön kuralı gereği aleyhte).

Kalibrasyon yapılana kadar geçici değer `5.0 bps`'tir ve bu değerle üretilen sonuçlar
`provisional_cost_model` bayrağı taşır; promotion'a giremez (K-010).

**Gerekçe:** K-004 fill'i `t+1` barının açılışına koyuyor. Sinyal `t` kapanışında üretilip
emir bir sonraki barın açılışında dolduğuna göre, aradaki fiyat farkı bir mikroyapı olayı
değil — 1h timeframe'de saatlerce süren bir belirsizlik penceresi. Spread (ölçüldü:
0,00128 bps) bunun yanında görünmez kalıyor.

Yani bu parametrenin doğru değeri borsanın ücret sayfasından değil **kendi verimizden**
çıkar. Tam olarak ölçebileceğimiz bir şeyi tahmin etmek için hiçbir sebep yok.

**Neden değiştirildi (Spike 2, 2026-09-08):** Yukarıdaki son cümle doğru, ama önerilen
**ölçüm yöntemi yanlıştı.** `|open[t+1] − close[t]|` dağılımı gerçekten ölçüldü ve neredeyse
sıfır çıktı: 1h'de vakaların **%52,2'sinde iki fiyat birebir aynı**, 75. persentil
**0,0014 bps**. Bu yöntem `slippage_bps`'i geçici değerin 3.500'de biri olarak belirlerdi —
yani maliyeti fiilen sıfırlardı.

Sebep: kripto 7/24 kesintisiz işlem görüyor. `open[t+1]`, `close[t]`'in birkaç milisaniye
sonrasıdır; arada piyasa kapanışı yok, boşluk yok. Bu dağılım bir yürütme belirsizliğini
değil, iki komşu işlemin tick farkını ölçüyor. Ayrıntı: `docs/spikes/02-veri-hacmi.md` §4.

Yerine **K-021** geçti.

---

## K-021 — Slippage: yürütme penceresindeki fiyat hareketinden kalibre edilir

**Durum:** açık (Faz 1'de kapanacak) · **Değiştirir:** K-020 · **Kaynak:** Spike 2 ·
**Tarih:** 2026-09-08

**Karar:** `slippage_bps`, K-020'nin öngördüğü `|open[t+1] − close[t]|` dağılımından
**hesaplanmaz** — o dağılım ölçüldü ve neredeyse sıfır çıktı (bkz. K-020'nin düzeltme notu).
Yerine parametre **yürütme penceresindeki fiyat hareketinden** kalibre edilir.

**Yürütme penceresi nedir:** bar kapandığı an ile emrin borsada dolduğu an arasındaki süre.
Spike 1 bunun ağ ayağını ölçtü: p50 ~300 ms, kuyruk 1,6 s; buna emir işleme süresi eklenir.
Yani pencere **saniye altı ile birkaç saniye arası** — K-004'ün ima ettiği "bir bar boyu"
değil.

**Kalibrasyon yöntemi (Faz 1):** Pencere bir dakikadan kısa olduğuna göre, 1 dakikalık fiyat
hareketi dağılımı **muhafazakâr bir üst sınırdır**. Ölçüldü (BTC/USDT, 1 yıl, 525.600 bar):

| | p50 | p75 | p90 | p95 | p99 |
| --- | --- | --- | --- | --- | --- |
| 1 dakikalık hareket (bps) | 2,42 | **5,01** | 8,86 | 12,32 | 22,64 |
| 1m bar içi salınım (bps) | 4,28 | 7,82 | 12,99 | 17,48 | 30,71 |

Yön kuralı (K-007) gereği aleyhte ve muhafazakâr taraf seçilir. Faz 1'de bu dağılım,
kullanılacak veri aralığı üzerinde yeniden hesaplanır ve seçilen persentil **gerekçesiyle
birlikte** kaydedilir.

**Geçici değerin durumu:** `slippage_bps = 5,0` yerinde kalıyor. Ölçüm bunu doğrulamıyor ama
**çürütmüyor da**: 1 dakikalık hareketin 75. persentili 5,01 bps — yani büyüklük mertebesi
tesadüfen doğruydu, türetme yolu yanlıştı. Kalibrasyon tamamlanana kadar bu değerle üretilen
sonuçlar `provisional_cost_model` bayrağı taşır ve promotion'a giremez (K-010).

**Gerekçe:** K-020 doğru soruyu sordu ("tahmin etme, ölç") ama yanlış şeyi ölçmeyi önerdi.
Bu tam olarak projenin uyardığı hata sınıfı: yöntem makul görünüyordu, sonuç makul görünen
bir sayı üretecekti (0,0014 bps — küçük, ama "ölçülmüş"), ve maliyeti fiilen sıfırlayarak
her stratejiyi kârlı gösterecekti. Yanlışlığı ancak dağılıma bakılınca ortaya çıktı — "neredeyse
doğru" olanın fark edilmemesi tam olarak budur.

---

## K-022 — Bağımlılıklar `uv` + `uv.lock` ile kilitlenir

**Durum:** kabul · **Tarih:** 2026-09-08 · **Hizmet ettiği:** K-009

**Karar:** Paket yönetimi `uv`, sürüm kilidi `uv.lock` (commit edilir). Python sürümü
`pyproject.toml`'da `==3.12.*` olarak sabit. Alternatif olan pip + `requirements.txt` +
elle `pip freeze` reddedildi.

**Gerekçe:** K-009 her backtest sonucuna kütüphane sürümlerinin yazılmasını istiyor. Bu,
ancak sürümlerin gerçekten sabit olduğu bir dünyada anlamlı — aksi hâlde kayıt "o gün ne
kuruluysa o" demekten ibaret kalır ve altı ay sonra aynı ortamı kurmak mümkün olmaz.
`pip freeze` doğrudan bağımlılıkları yakalar ama transitive olanlarda kayma bırakır; kilit
dosyası tüm ağacı çözer.

`common/hash.py:ortam_kaydi()` yine de **çalışma anındaki** sürümleri okur, kilit dosyasını
değil: ikisinin ayrışabildiği durumları (elle kurulmuş paket, bozuk ortam) görmenin tek yolu
bu.

**Yan karar:** lint/format `ruff`, ama `docs/` ve `research/` hariç. `docs/Proje-Fikri.md`
tarihsel kayıttır ve içindeki kod blokları olduğu gibi kalmalıdır; `research/` zaten commit
edilmiyor.

---

## Açık kararlar

Faz 0 kapandığında (2026-09-08) durum:

| No | Konu | Durum | Kapanacağı yer |
| --- | --- | --- | --- |
| K-011 | Parquet + DuckDB saklama | ✅ **kabul** | Spike 3 |
| K-015 | Binance erişimi, rate limit, testnet | ✅ **kabul** | Spike 1 |
| K-016 | Fee/slippage'ın kesin sayıları | ✅ **kabul** | Fee: Spike 4. Slippage → K-021 |
| K-017 | Birincil timeframe ve veri hacmi | ✅ **kabul** (1h) | Spike 2 |
| K-019 | Promotion kapılarının sayısal eşikleri | ⏳ açık | Faz 4 sonu |
| K-020 | Slippage kalibrasyonu (ilk yöntem) | ⛔ değiştirildi → K-021 | — |
| K-021 | Slippage'ın yürütme penceresinden kalibrasyonu | ⏳ açık | Faz 1 |
| K-022 | Bağımlılık kilidi (`uv`) | ✅ **kabul** | Faz 1 başlangıcı |

**Faz 0'ın dört spike'ı da kapandı.** Kalan iki açık karar Faz 1 ve Faz 4'e ait; Faz 0'ı
bloke etmiyorlar.

### Faz 0'dan çıkan, karar olmayan ama bağlayıcı gereksinimler

Bunlar ayrı birer K-0XX değil çünkü alternatifi olan tercihler değil — ölçümün dayattığı
kısıtlar. İlgili kararların içinde ayrıntılı, burada tek bakışta:

| # | Gereksinim | Kaynak | Nerede uygulanır |
| --- | --- | --- | --- |
| 1 | Kapanmamış bar depoya yazılmaz (`close_time < serverTime`) | Spike 1 | Faz 1 — idempotency'nin ön koşulu |
| 2 | Klines çağrısı her zaman `limit=1000` | Spike 1 | Faz 1 |
| 3 | IPv4'e zorla veya kalıcı session kullan (aksi hâlde +12 s/bağlantı) | Spike 1 | Faz 1, Faz 7 |
| 4 | Veri seti hash'i = Parquet dosyasının SHA-256'sı | Spike 3 | Faz 1, Faz 3 (K-009) |
| 5 | Kalite bayrakları yapay bozuk fixture ile test edilir | Spike 2 | Faz 1 (K-006) |
| 6 | Testnet API anahtarı alınmış olmalı | Spike 1 | Faz 7 ön koşulu |
| 7 | Canlı hesap + KYC + API anahtarı; Spike 1'in auth kısmı tekrarlanır | Spike 1 | Faz 8 ön koşulu |
