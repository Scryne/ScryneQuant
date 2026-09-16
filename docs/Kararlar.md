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

**Durum:** kabul (Faz 1'de kapatıldı, 2026-09-09) · **Değiştirir:** K-020 · **Kaynak:** Spike 2 +
Faz 1 kalibrasyonu · **Tarih:** 2026-09-08, kapanış 2026-09-09

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

**Faz 1 kalibrasyonu — 2026-09-09, karar kapandı.**

Ölçüm `sq data slippage-kalibre` ile, kullanılacak veri aralığının tamamı üzerinde yapıldı:
BTC/USDT 1m, 2023-08-04 → 2026-09-09, **1.630.475 hareket**, hepsi `ok` bar
(veri hash'i `5a3b33c7…`).

| | p50 | p75 | p90 | p95 | p99 | ort | max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 dk hareket (bps) | 2,566 | **5,300** | 9,325 | 12,870 | 23,426 | 4,050 | 428,98 |
| 1m bar içi salınım (bps) | 4,446 | 8,172 | 13,584 | 18,302 | 32,349 | 6,296 | 643,57 |

**Seçilen: p75 → `slippage_bps = 5,2996`.** Geçici 5,0 değeri kaldırıldı,
`provisional_cost_model` bayrağı düştü.

**Persentil neden p75 — kaydedilen gerekçe:** ölçülen büyüklük 1 dakikalık hareket, ama
gerçek yürütme penceresi (bar kapanışı → emrin dolması; Spike 1: p50 ~300 ms, kuyruk 1,6 s)
bundan onlarca kat kısa. Yani **metrik zaten muhafazakâr bir üst sınır**: rastgele yürüyüşte
hareket ~√t ile büyüdüğünden 60 s ölçmek 1 s'lik pencereyi ~7,7 kat abartır. Üstüne p95/p99
koymak iki muhafazakârlığı çarpar ve her stratejiyi **gerçek olmayan bir sebeple** zararlı
gösterir — bu da bir hata türüdür, sadece diğer yöne doğru. Medyan ise K-007'nin
"belirsizlikte aleyhte yuvarla" kuralını çiğner. p75 tek ve bilinçli bir emniyet payıdır.
Tam dağılım `config/maliyet.json`'a yazıldı; persentil kararı yeniden ölçüm gerektirmeden
değiştirilebilir (K-025).

**Spike 2'nin sayısı doğrulandı.** 1 yıllık veride ölçülen p50 = 2,42 / p75 = 5,01 bps;
3,1 yıllık veride p50 = 2,566 / p75 = 5,300. Yöntem tanımının spike'ınkiyle aynı olduğunun
kanıtı bu yakınlık — farklı bir büyüklük ölçülüyor olsaydı sayılar bu kadar örtüşmezdi.

**Kalan dürüst sınır:** bu hâlâ bir **proxy**. Gerçek slippage ancak Faz 7'de, testnet'te
gönderilen emirlerin fiili dolum fiyatlarıyla ölçülebilir. O ölçüm geldiğinde buradaki sayı
doğrulanmalı; sapıyorsa yeni bir karar yazılır. Bugünkü kanıt "muhafazakâr bir üst sınır"
der, "gerçekleşen slippage budur" demez.

**Gidiş-dönüş maliyeti artık:** 2 × (10,0 + 5,2996) = **30,60 bps.** K-017'nin timeframe
kararı 20,02 bps'lik komisyon ayağına dayanıyordu; slippage eklendiğinde 1h barın medyan
hareketi (20,85 bps) gidiş-dönüş maliyetinin **altına** düşüyor. Karar değişmiyor — 1m'nin
oranı hâlâ 8 kat daha kötü — ama Faz 4'ün "hiçbiri maliyetlerden sonra anlamlı değil"
beklentisi bu sayıyla daha da olası hale geldi.

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

## K-023 — Tarihsel klines ccxt'nin ham ucundan alınır, `fetch_ohlcv`'den değil

**Durum:** kabul · **Tarih:** 2026-09-09 · **Faz:** 1 · **Değiştirir:** Final-Doküman'ın
"CCXT yerinde kalıyor" notunun bir ayrıntısını

**Karar:** Binance adaptörü tarihsel barları `exchange.publicGetKlines(...)` ile, yani
ccxt'nin **ham** Binance ucundan çeker. `fetch_ohlcv` kullanılmaz. ccxt transport katmanı
olarak yerinde kalır: kalıcı `requests.Session`, rate limiter, hata sınıfları hep ondan.

**Gerekçe:** `fetch_ohlcv`'nin normalize ettiği satır altı alandır —
`[timestamp, open, high, low, close, volume]`. `BAR_SEMASI` bunların yanında
`quote_volume` ve `trades` alanlarını **zorunlu** tutuyor. İkisi de gerçekten kullanılıyor:

- `trades` ile `volume`'ün ayrışması (`islemsiz_hacim`) veri bozulmasının imzasıdır —
  K-006'nın `suspect` kurallarından biri buna bakar.
- `quote_volume` §8'in hacim ortalaması indikatörünün doğal girdisi; `volume × fiyat`
  olarak yeniden türetmek, bar içindeki fiyat yolunu ortalama sayarak sessiz bir hata
  ekler.

Alternatif üçtü: (a) şemadan iki alanı atmak, (b) `fetch_ohlcv` kullanıp alanları ayrı bir
çağrıyla tamamlamak, (c) ccxt'yi tamamen bırakıp doğrudan `requests` kullanmak. (a) zaten
commit edilmiş bir şemayı kalite kontrolünü zayıflatmak için değiştirirdi; (b) her bar için
iki kaynak demek — hangisi doğru sorusu ortaya çıkar; (c) ccxt'nin rate limiter'ını ve Faz
7'nin ihtiyaç duyacağı imzalama katmanını elle yeniden yazmak olurdu.

**Sonucu:** adaptör Binance'in 12 alanlı kline dizisinin sıralamasına bağımlı hale geldi.
Bu bağımlılık `_KLINE_ALANLARI` sözlüğünde tek bir yerde yazılı ve
`test_binance_adaptoru.py::TestKlineDonusumu::test_alan_eslesmesi` onu sabitliyor —
alanlar karışırsa test kırmızı yanar, sessiz yanlış veri değil.

---

## K-024 — Kalite bayrağı tekildir; boşluk sentetik barla doldurulmaz

**Durum:** kabul · **Tarih:** 2026-09-09 · **Faz:** 1 · **Detaylandırır:** K-006

K-006 bayrakların **ne olduğunu** söylüyor; bu karar birden fazlası aynı anda geçerliyken
ne olacağını ve bayrağın veriye nasıl dokunacağını söylüyor.

**Karar 1 — bayrak tekildir, öncelik sırası şudur:**

```
suspect > gap > duplicate > backfilled > ok
```

Gerekçe: `suspect` barın **içeriğinin** yanlış olabileceğini söyler; en ağırı budur.
`gap` seriyi ilgilendirir, bar içeriğini değil. `duplicate` yalnızca barın **gelişini**
ilgilendirir — tekilleştirme onu zaten çözdü. `backfilled` bir köken bilgisidir, kusur
değil. Öncelik yalnızca raporlamayı etkiler; backtest için ayrım her hâlükârda ikilidir:
`ok` ya da değil.

**Karar 2 — boşluk bayrağı boşluktan *sonraki* bara konur, eksik barlar için satır
üretilmez.** Sentetik bir bar yazmak, olmayan bir fiyatı varmış gibi göstermektir; bu
projenin "neredeyse doğru sonuç yanlış sonuçtan tehlikelidir" uyarısının tam hedefi.
Boşluğun gerçeği bayrakta ve kalite raporunda durur, veride durmaz.

Yan faydası: K-021'in slippage kalibrasyonu yalnızca `ok` barları kullandığından,
boşluğun iki yakasını birbirine bağlayan sahte hareketler bu kuralla **kendiliğinden**
düşer. Bayrağın önceki değil sonraki bara konmasının sebeplerinden biri budur.

**Karar 3 — ızgaraya hizasız timestamp bayrak değil, hatadır.** `open_time % timeframe`
sıfır değilse `DogrulamaHatasi` fırlatılır. Hizasızlık tek bir barın kusuru değil, serinin
yanlış hizalanmış olmasıdır (K-005). `suspect` deyip devam etmek, yanlış bir zaman eksenini
"biraz şüpheli veri" diye kaydetmek olurdu.

**Karar 4 — depo-yeni çakışması `duplicate` üretmez.** `duplicate`, borsanın aynı
timestamp'i iki kez göndermesini kaydeder. Kendi depomuzu yeni bir indirmeyle birleştirmek
bir borsa anomalisi değil, olağan işleyiştir; ayrılmazsa örtüşen her yeniden indirme
yüzlerce barı yanlış bayraklar ve `ok` oranı sebepsiz düşer. Çakışma indiricide çözülür
(yeni veri kazanır), doğrulamaya yalnızca **tek bir paketin içindeki** tekrarlar ulaşır.

**Ölçüm — bu kararı Faz 1 verisi doğruladı.** Spike 2, 3 yıllık veride hiçbir kalite
bayrağı tetikleyememişti. Faz 1'in 5,2 yıllık indirmesinde (45.576 bar) **3 boşluk (7 eksik
bar) ve 1 `suspect` bar** çıktı; en açıklayıcısı 2023-03-24: 12:00 UTC barı sıfır hacimli
ve dört fiyatı da aynı, 13:00 barı ise hiç yok. Yani bayraklar ölü kod değilmiş — sadece
Spike 2'nin penceresi onları görecek kadar geniş değilmiş.

---

## K-025 — Maliyet parametreleri `config/maliyet.json`'da yaşar; kalibre edilmemiş model kendini işaretler

**Durum:** kabul · **Tarih:** 2026-09-09 · **Faz:** 1 · **Hizmet ettiği:** K-007, K-021

**Karar:** `fee_taker_bps` ve `slippage_bps` tek bir dosyada, `config/maliyet.json`'da
tutulur; kodda gömülü maliyet sabiti yoktur. Dosya yoksa sistem varsayılana **düşmez**,
hata verir. Model bir `kalibrasyon` bloğu taşımıyorsa `gecici` sayılır ve bu bayrak sonuç
kaydına geçer; geçici modelle üretilen sonuç promotion'a giremez (K-010, K-021).

**Kalibrasyon bloğu yalnızca sayıyı değil, sayının kanıtını taşır:** yöntemin formülü,
persentil, ölçümün yapıldığı sembol/timeframe/aralık, **veri setinin SHA-256'sı**, tam
persentil dağılımı, tarih ve serbest metin gerekçe. `sq data slippage-kalibre --yaz`
komutu `--gerekce` olmadan çalışmayı reddeder.

**Gerekçe:** K-007 maliyet varsayımının "stratejinin bir parçası, dipnot değil" olduğunu
söylüyor. Bir sayının stratejinin parçası olması, altı ay sonra "bu 5,01 nereden geldi"
sorusunun cevabının bulunabilmesi demek. K-020'nin başına gelen tam olarak buydu: makul
görünen bir yöntem, makul görünen bir sayı üretecekti ve yanlışlığı ancak dağılıma
bakılınca ortaya çıktı. Dağılımı sayının yanına yazmak, o kontrolü mümkün kılan şey.

**Neden JSON, TOML değil:** bu dosyayı kalibrasyon komutu **yazıyor**. `tomllib` yalnızca
okur; TOML yazmak yeni bir bağımlılık ya da elle yazılmış bir serileştirici gerektirirdi —
ikisi de, içeriği bir backtest sonucunun kimliğine giren bir dosya için kötü takas.
`json.dumps(sort_keys=True)` byte düzeyinde kararlı bir dosya verir; K-009'un istediği de bu.

---

## K-026 — İndikatör konvansiyonu TA-Lib'dir; referans dondurulur, sapma tektir ve kayıtlıdır

**Durum:** kabul · **Tarih:** 2026-09-09 · **Faz:** 2 · **Hizmet ettiği:** Faz 2 bitti
kriteri ("her indikatör bağımsız bir referansla doğrulanmış")

**Karar 1 — konvansiyon TA-Lib'in konvansiyonudur.** Bir indikatörün "doğru" değeri tek
değil: EMA ilk n değerin SMA'sıyla mı yoksa ilk değerle mi tohumlanır, Bollinger
popülasyon mu örneklem sapması kullanır, RSI'ın ilk değeri hangi indekstedir — hepsi
seçimdir. Seçilenler **varsayılmadı, ölçüldü** (TA-Lib 0.7.1):

| İndikatör | İlk geçerli indeks | Konvansiyon |
| --- | --- | --- |
| `sma(n)` | `n-1` | Kayan pencere ortalaması |
| `ema(n)` | `n-1` | Tohum = ilk `n` değerin SMA'sı; α = 2/(n+1) |
| `rsi(n)` | `n` | Wilder yumuşatması; tohum = ilk `n` farkın basit ortalaması |
| `atr(n)` | `n` | Wilder; TR indeks 1'den başlar (önceki kapanış gerekir) |
| `bollinger(n,k)` | `n-1` | SMA ± k × **popülasyon** sapması (ddof=0) |
| `hacim_sma(n)` | `n-1` | `sma`, hacim serisi üzerinde |

Neden TA-Lib: grafik platformlarının yaygın olarak izlediği konvansiyon bu, dolayısıyla
canlıda bir grafikle karşılaştırma yapıldığında sayılar tutar. `ta`/`pandas-ta` gibi
kütüphaneler EMA ve RSI'ı ilk değerden tohumluyor — ısınma bölgesinde farklı sayı, ve o
farkın nereden geldiği altı ay sonra hatırlanmaz.

**Karar 2 — referans dondurulur, TA-Lib bağımlılık olmaz.** TA-Lib native bir kütüphanedir;
her makinede kurulu olmasını şart koşmak, testleri çalıştırmayı zorlaştırır. Bunun yerine
çıktısı `tests/fixtures/indikator_referans.json` içine bir kez yazıldı; testler o dosyaya
bakıyor. Üretici `tools/referans_uret.py`, `uv run --with ta-lib python tools/referans_uret.py`
ile elle çalıştırılır.

Fixture **hem girdiyi hem beklenen çıktıyı** taşıyor. Yalnızca çıktıyı saklamak, girdiyi
üreten test yardımcısı bir gün değiştiğinde referansı sessizce yanlış hale getirirdi — bu
projede en pahalı hata sınıfı tam olarak bu.

**Karar 3 — tolerans kayan nokta içindir, konvansiyon için değil.** Karşılaştırma bağıl
1e-11 toleransla yapılır (ölçülen en büyük fark 3,1e-12: TA-Lib yürüyen toplam, numpy
pencere başına toplam kullanıyor). Ama **NaN maskeleri birebir eşit olmak zorunda**: "ilk
geçerli değer hangi indekste" bir konvansiyon sorusudur ve yaklaşık cevabı yoktur. Bir
tohumlama veya ddof farkı bu toleransın kat kat üstünde sapma üretir ve testi kırar.

**Karar 4 — tek bilinçli sapma: hareketsiz seride RSI.** Pencere boyunca fiyat hiç
kımıldamadıysa (kazanç = kayıp = 0) TA-Lib `0.0` döndürür; biz **NaN** döndürüyoruz.

Gerekçe: 0, RSI ölçeğinde azami aşırı satımdır. Yani hiç hareket etmeyen bir piyasa, bir
mean-reversion stratejisine üretilebilecek **en güçlü alım sinyalini** verirdi. Bu sayı
yanlış değil, *tehlikeli*: "neredeyse doğru" sınıfından. Hareket yoksa RSI tanımsızdır ve
NaN ile yapılan her karşılaştırma False olduğu için hiçbir eşik tetiklenmez.

Bu senaryo teorik değil: 2023-03-24 12:00 UTC barı (K-024'ün ölçümü) tam olarak sıfır
hacimli ve dört fiyatı aynı. Kesinti uzasaydı pencerenin tamamı düz olabilirdi.

Sapma üç yerde birden kayıtlı: `features/indikator.py:rsi` docstring'i,
`tools/referans_uret.py` başlığı, ve `test_indikator.py::test_hareketsiz_seride_rsi_tanimsiz`
— o test ayrıca referanstaki TA-Lib değerinin hâlâ `0.0` olduğunu doğruluyor, yani üst
kaynak davranışı değişirse haberimiz olur.

---

## K-027 — Strateji izolasyonu izin listesiyle zorlanır, yasak listesiyle değil

**Durum:** kabul · **Tarih:** 2026-09-09 · **Faz:** 2 · **Detaylandırır:** K-003

K-003 mekanizmayı "import grafiği taranır, yasaklı bağımlılık (`ccxt`, `requests`, `httpx`,
`socket`, `open`) bulunursa test kırmızıya döner" diye tarif ediyor. Bu karar o taramanın
nasıl yapıldığını sabitliyor, çünkü tarifin doğrudan uygulanışı yeterince güçlü değil.

**Karar 1 — izin listesi.** Yasak listesi her zaman eksiktir: `aiohttp`, `urllib3`,
`smtplib`, `paramiko`, `pyarrow`, henüz var olmayan bir kütüphane... Listeye eklemeyi
unutmak sessizce kuralı deler. İzin listesinde unutmanın yönü güvenli tarafa düşer:
listede olmayan reddedilir, eklemek bilinçli ve gözden geçirilebilir bir diff olur.
K-003'ün saydığı beş isim ayrıca kendi testinde açıkça kontrol ediliyor — kararın metni
testte görünür kalsın diye.

**Karar 2 — tarama geçişlidir.** Yüzeysel bir tarama `strategy → common.hash`'i temiz
sayardı; oysa `common.hash` `subprocess` çağırıyor. Bir adım derine bakmayan izolasyon
testi tam da engellemesi gereken şeyi kaçırır. Test bulduğu ihlalin **yolunu** basar
(`strategy.temel → common.hash → subprocess`), çünkü "yasaklı bağımlılık var" tek başına
teşhis değil.

**Karar 3 — tarama statiktir (`ast`).** Modülleri import edip `sys.modules`'a bakmak, yan
etkileri çalıştırmak demek olurdu — ve yan etki tam olarak aradığımız şey.

**Karar 4 — pandas strateji katmanına giremez.** pandas dosya okuyabilir
(`read_parquet`, `read_csv`), yani K-003'ün kapattığı I/O yüzeyini dolaylı yoldan geri
açar. Bu yüzden `features/` paketi ikiye bölündü: `indikator.py` ve `motor.py` yalnızca
numpy kullanır ve stratejiye açıktır; DataFrame ↔ dizi dönüşümü `barlar.py`'de yaşar ve
izin listesinde **yoktur**. Aynı gerekçeyle `common/zaman.py` açık, `common/hash.py`
(subprocess) kapalıdır.

**Karar 5 — tarayıcının kendisi test edilir.** `TestTaramaninKendisi` sahte bir paket
üzerinde `a → ara → socket` zinciri kurup tarayıcının onu bulduğunu doğruluyor. Bu öz-test
yazılırken tarayıcıda iki gerçek hata çıktı (kök paket adı sabit kodlanmıştı, `__init__.py`
yanlış modül adına eşleniyordu) — yani öz-test bedelini ilk gün ödedi. Hiçbir zaman
kırmızıya dönemeyen bir izolasyon testi, güvenlik değil tiyatrodur.

---

## K-028 — `ok` olmayan barda ne karar verilir ne fill yapılır

**Durum:** kabul · **Tarih:** 2026-09-09 · **Faz:** 3 · **Detaylandırır:** K-006

K-006 "`ok` dışındaki barlar backtest'te **sessizce kullanılmaz**" diyor ve oranın sonuç
kaydına yazılmasını istiyor. Bu karar cümlenin uygulama karşılığını sabitliyor.

**Karar 1 — `ok` olmayan bar hem karar hem fill dışıdır.** Motor o barda `on_bar`
çağırmaz ve bekleyen bir sinyali o barın açılışından doldurmaz.

Gerekçe: bir `suspect` barın açılış fiyatı, tanımı gereği güvenilmez. O fiyattan
doldurmak, gerçek olmayan bir fiyattan **gerçek bir P&L** üretmek olurdu — ve o P&L
sonuçta bir sayı olarak görünür, uyarı olarak değil. Karar tarafında da aynısı geçerli:
şüpheli bir kapanışa bakarak verilen karar, şüpheli bir karardır.

**Karar 2 — kural bayrağa göre değişmez, tekdüzedir.** `gap`, `duplicate`, `suspect`,
`backfilled` — dördü de aynı muameleyi görür. Bayrak başına farklı kural yazmak (örneğin
"`gap` barında fill yapılabilir çünkü fiyatı kendi başına geçerlidir") daha ince olurdu ama
dört ayrı kod yolu üretirdi ve her biri ayrı ayrı test edilmek zorunda kalırdı. Ölçülen
gerçek bu inceliği gereksiz kılıyor: BTC/USDT 1h, 5,2 yıl, 45.576 barda `ok` olmayan bar
sayısı **4** (%0,0088). Kazanç sıfıra yakın, karmaşıklık maliyeti gerçek.

**Karar 3 — atlanan sinyal sayılır ve kayda yazılır.** K-006'nın "sessizce kullanılmaz"
kuralının simetriği: sinyal sessizce **atılmaz** da. `AtlamaSebebi` enum'u beş sebep
tanımlıyor (`sonraki_bar_yok`, `fill_bari_ok_degil`, `hedef_zaten_tutturulmus`,
`nakit_yok`, `pozisyon_yok`) ve sonuç kaydında sıfır olanlar dahil hepsi görünür — yokluk
da bir bilgi.

**Karar 4 — özkaynak `ok` olmayan barda da işaretlenir.** Pozisyon o barda da elde
duruyor; equity eğrisinde delik bırakmak, olmayan bir "işlem yapılmadı" hâli uydurmak
olurdu. Bilinen sınır: şüpheli bir kapanış o barda yapay bir drawdown sivrisi üretebilir.
Alternatifi (bir önceki `ok` kapanıştan işaretlemek) veri uydurmak olurdu — K-024'ün
"boşluk sentetik barla doldurulmaz" kuralının aynısı.

**Bilinen sınır — indikatörler `ok` olmayan barı yine de görür.** İndikatörler tüm seri
üzerinde hesaplanıyor, yani bir `suspect` barın fiyatı sonraki 20 barın SMA'sını
kirletiyor. Bunu düzeltmek boşluk-farkında indikatörler gerektirirdi; K-024 zaten sentetik
bar üretmeyi reddetmişti. Ölçülen etki (4 bar / 45.576) bu borcu şimdilik kabul edilebilir
kılıyor. Faz 4'te çok daha kirli bir veri setiyle çalışılırsa bu karar yeniden açılmalı.

---

## K-029 — Backtest referansı kapalı formülle çapraz doğrulanır; üretici motoru import edemez

**Durum:** kabul · **Tarih:** 2026-09-09 · **Faz:** 3 · **Hizmet ettiği:** Faz 3 bitti
kriteri, K-009

Faz 3'ün kriteri açık: referans senaryonun beklenen P&L'i "motordan **bağımsız** olarak
hesaplanmış" olmalı, çünkü "motorun kendi çıktısından türetilirse test hiçbir şey
kanıtlamaz". Bu karar o bağımsızlığın nasıl sağlandığını ve **nereye kadar gerçek olduğunu**
sabitliyor.

**Karar 1 — üretici projeyi import edemez.** `tools/backtest_referans_uret.py`
`scryne_quant`ın hiçbir modülünü import etmez; bunu bir test statik olarak (`ast`) tarar
(K-027'nin tarayıcısının aynı fikri). Söz değil, kısıt.

**Karar 2 — sayısal bağımsızlık: `Decimal` (50 basamak) karşısında `float64`.** Aynı kayan
nokta hatasını iki tarafta birden yapmak mümkün değil. Tolerans 1e-11 bağıl — 10.000
USDT'de kuruşun milyonda biri.

**Karar 3 — asıl kanıt cebirsel.** Referans senaryo A'nın her turu "tüm nakitle gir,
tamamen çık" biçiminde; böyle bir turun sonucu döngü çalıştırmadan yazılabilir:

```
C_son / C_ilk = (o_çıkış / o_giriş) × (1−s)(1−f) / [(1+s)(1+f)]
```

Bu formül K-004 (fill `t+1` açılışında) ve K-007'nin (slippage aleyhte, iki bacakta taker
komisyonu) metninden cebirle çıkarıldı — ne motorun kodundan ne referans defterinden.
Üretici, defter sonucunu bu formülle karşılaştırmadan dosya yazmayı reddeder; ölçülen
uyum 1,9e-49 bağıl fark. Testler ayrıca formülü fixture'ın defterini hiç kullanmadan
**doğrudan motora karşı** da kuruyor — yani defter ile motor aynı anda aynı hatayı yapsa
bile test kırılır.

**Karar 4 — bağımsızlığın sınırı açıkça yazılır.** Senaryo B (kısmi maruziyet) kapalı
formüle uymaz; orada yalnızca Decimal defteri var ve kanıt gücü daha zayıf. Bu bilinçli bir
kabul, gizlenmiş bir varsayım değil — hem üreticinin hem testin docstring'inde yazılı.

**Ölçülen etki:** referans testi üç kasıtlı bozmayı da yakaladı — slippage yönünü ters
çevirmek (10 test kırmızı), fill'i kapanışa kaydırmak (3), tek bacakta komisyonu unutmak
(8). Kırılamayan bir doğruluk testi, doğruluk kanıtı değildir.

---

## K-019 — Promotion kapılarının sayısal eşikleri

**Durum:** kabul · **Tarih:** 2026-09-09 · **Faz:** 4 · **Kapatır:** K-010'un ve K-018/3'ün
açık bıraktığı sayılar · **Rapor:** `docs/Faz-4-Laboratuvar-Raporu.md`

K-018 şunu şart koşmuştu: *"K-010'un kapıları sayısal eşiklerle tanımlanır ve makine
kontrol eder. 'Sonuçlara bak ve karar ver' bir kapı değildir."* Eşikler Faz 4 sonunda
gerçek veriyle kalibre edilecekti. Bu karar o eşikleri sabitliyor.

**Karar — yedi kapı, hepsi sayısal:**

| Kapı | Eşik | Gerekçe |
| --- | --- | --- |
| `oos_sharpe` | ≥ 0,50 | Al-tut kıyasının in-sample Sharpe'ı 0,70 ölçüldü. Kıyasın belirgin altında kalan bir strateji, sermayeyi piyasada tutmak yerine sistemde tutmak için gerekçe üretemez. 0,50 kıyası geçmeyi şart koşmuyor ama sıfıra yakın Sharpe'ları eliyor. |
| `oos_is_orani` | ≥ 0,50 | Overfitting'in en doğrudan ölçüsü. Faz 4'te altı stratejinin **altısında da** negatif çıktı (−0,09 … −4,15). "IS performansının en az yarısı korunmuş olmalı." |
| `wf_katman_basari` | ≥ 0,60 | Walk-forward katmanlarının kaçı pozitif. Bileşik getiri tek bir şanslı katmandan gelebilir. Ölçülen: 7-10/16, yani yazı-tura. |
| `parametre_kararliligi` | ≤ 0,35 | Katmanlar arası benzersiz parametre değeri oranı. Ölçülen 0,15-0,25. Üstü, "canlıda hangi parametreyle çalıştıracağız" sorusunun cevapsız olması demek. |
| `asgari_islem` | ≥ 30 | 30 işlemde win rate'in standart hatası ~%9. Tarama eşiği 20'ydi (aday elemek için); promotion daha yüksek kanıt ister. |
| `max_drawdown` | ≤ 0,25 | Kıyas %25,7 düştü. Varlığın kendisinden derin düşen aktif yönetim değer katmıyor. Eşik gerçekleşen değere değil kıyasa dayanıyor — çünkü Monte Carlo gerçekleşen düşüşün şanslı bir sıralama olabileceğini gösterdi. |
| `stres_dayanikliligi` | ≤ 0,15 | Temel senaryodan en kötü stres senaryosuna getiri farkı (yüzde puan). Maliyet kalibrasyonu (K-021) bir tahmindir; slippage iki katına çıkınca çöken strateji, kalibrasyonun doğruluğuna bahis oynamaktır. |

Bunlara ek olarak **üç mutlak engel** sayısal sonuçtan bağımsız olarak kapıyı kapatır:
`dirty` (K-009), `data_quality_warning` (K-006), `gecici_maliyet_modeli` (K-021).

**Ölçülemeyen kapı geçilmiş sayılmaz.** "Veri yoktu" ile "kapıdan geçti" aynı şey değil;
ikisini karıştırmak kapıyı sessizce kaldırmak olurdu.

**Eşikler bugünkü sonuca göre ayarlanmadı — ayarlansaydı kapı kaldırılmış olurdu.** Faz
4'te ölçülen **yedi stratejinin yedisi de kaldı** (kıyas dahil) ve bu doğru sonuçtur.
`tests/unit/test_kapilar.py::test_faz4_olcumlerinden_hicbiri_gecmiyor` gevşetmeyi yakalar:
eşikleri indiren biri testi kırar ve karar günlüğüne gerekçe yazmak zorunda kalır. K-018'in
"sayısal eşik esnetilemez, değiştirmek iz bırakır" cümlesinin mekanizması budur.

**Kapsam sınırı:** K-018/3 beşinci bir aday saymıştı — paper/backtest drift üst sınırı. O
ölçüm Faz 6'da (paper trading) mümkün olacak; kapı listesine o zaman eklenecek.

**Faz 4 eşikleri belirledi, Faz 5 uygular.** `research/kapilar.py` bir sonucun kapılardan
geçip geçmediğini **söyler**; sinyalin execution'a ulaşmasını engelleyen mekanizma risk
motorunun işi.

---

## K-030 — Her karşılaştırmada al-tut kıyası bulunur

**Durum:** kabul · **Tarih:** 2026-09-09 · **Faz:** 4

**Karar:** Strateji karşılaştırmalarına `al_tut` (buy & hold) kıyası **otomatik** eklenir;
istenmesine bırakılmaz. Kıyas `KUTUPHANE`de değil ayrı bir `KIYAS` sözlüğünde durur ve
beş aileden sayılmaz.

**Gerekçe:** Bir stratejinin "%15 kazandı" cümlesi tek başına hiçbir şey söylemez. Aynı
dönemde varlık %39 yükseldiyse o strateji para kazandırmadı, **kaybettirdi** — sermayeyi
piyasada tutmak yerine sistemde tuttu ve farkı fırsat maliyeti olarak ödetti.

Bu teorik bir endişe değil, Faz 4'ün ana bulgusu: walk-forward'da `donchian` +%14,4 ile en
iyi strateji görünüyordu; kıyas **+%39,0** getirdi ve Sharpe'ı (0,86) hepsinden yüksekti.
Kıyas tabloda olmasaydı o satır "donchian çalışıyor" diye okunurdu.

**Kıyasın adil olması için diğer stratejilerle aynı yoldan geçer:** aynı `ctx` sözleşmesi,
aynı fill kuralı (K-004), aynı komisyon ve slippage (K-007), aynı hedef maruziyet.
`close[-1]/close[0]` hesaplamak daha kolay olurdu ama maliyetsiz ve fill'siz bir kıyas
stratejileri haksız yere kötü gösterirdi.

**İki istisna kayıtlı:** (1) kıyasın ızgarası tek noktalıdır — kıyas sabit bir çizgi
olmalı, ayarlanan bir rakip değil. (2) asgari işlem şartı kıyasa uygulanmaz: al-tut
pozisyonu pencerenin sonunda açık bırakır, yani kapanmış tur sayısı sıfırdır. Şart
parametre seçimi için var; kıyasta seçilecek bir şey yok. İkisi de ölçülerek öğrenildi —
şart ilk denemede kıyası tablodan sildi.

---

## K-031 — Strateji, sinyalinin kabul edildiğini varsayamaz

**Durum:** kabul · **Tarih:** 2026-09-09 · **Faz:** 4 · **Detaylandırır:** K-002, K-003

**Karar:** Bir strateji kendi içinde durum tutabilir, ama o durum **sinyalin kabul
edildiği varsayımına dayanamaz.** "Girdim, artık sinyal üretmeyeceğim" biçiminde bir bayrak
yasaktır; pozisyon durumu `ctx.pozisyon`dan okunur.

**Gerekçe — ölçülen hata:** `al_tut` kıyasının ilk hâli bir `_girildi` bayrağı tutuyordu.
Walk-forward katmanında bayrak **ısınma barında** kalktı; o barda üretilen sinyal ölçüm
penceresine girmediği için atıldı (K-028'in `isinma_penceresi` yolu); strateji bir daha hiç
sinyal üretmedi. Kıyas çizgisi karşılaştırma tablosunda **%0,0 getiri** olarak göründü —
çökme yok, uyarı yok, sadece sessizce yanlış bir sayı.

**Bu hata sınıfı Faz 5'te büyüyecek.** Bugün sinyali yutan tek yol ısınma penceresi ve
`ok` olmayan bar (K-028). Risk motoru devreye girdiğinde (Faz 5) sinyaller **rutin olarak**
reddedilecek: exposure limiti, günlük zarar limiti, cooldown, kill switch. Durumunu
sinyalin kabulüne bağlayan her strateji o gün sessizce bozulur.

**Sonucu:** `Sinyal.target_exposure`ın mutlak hedef olması (delta değil) bu kuralın ön
koşuluydu — ve şimdi gerekçesi somutlaştı. Mutlak hedef, kaçırılan bir sinyalden sonra
kendini bir sonraki barda düzeltir; delta düzeltemez.

---

## K-032 — Risk onayı bir tip, bir mühür ve bir kesme noktasıdır

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 5 · **Uygular:** K-008, K-010, §9.1/3

**Karar:** "Sinyal risk motorunu atlayamaz" kuralı üç katmanda birlikte zorlanır; hiçbiri
tek başına yeterli sayılmaz.

1. **Tip:** `execution/kapi.py` yalnızca `OnayliNiyet` kabul eder. `Sinyal`, `Red`, sözlük
   veya taklit bir sınıf `MuhurGecersiz` ile reddedilir — `isinstance` ile, yalnızca
   annotation'a güvenilmez.
2. **Mühür:** `OnayliNiyet` içeriğinin HMAC'iyle mühürlenir; anahtar süreç başına üretilir
   ve bir closure hücresinde yaşar. Mühürsüz bir örnek **kurulamaz**, onay sonrası
   değiştirilmiş bir örnek kapıda yakalanır. Mühür hiçbir hash'e, kayda veya audit
   satırına girmez (rastgele olduğu için determinizmi kırardı — K-009).
3. **Kesme noktası (asıl zorlama):** `execution/` ve `oms/` paketlerinden strateji
   katmanına giden **her** import yolu `risk.niyet`ten geçmek zorunda.
   `tests/unit/test_risk_bypass.py` bunu `ast` ile ölçüyor: `risk.niyet` grafikten
   çıkarıldığında strateji katmanı ulaşılamaz hâle gelmiyorsa test kırılır.

**Üçüncü katmanın neden asıl zorlama olduğu.** İlk tasarım "execution strateji katmanına
hiç ulaşmıyor" diye ölçüyordu ve **test bunu çürüttü**: `OnayliNiyet` sinyali içinde
taşıdığı için `execution → risk.niyet → strategy.sinyal` yolu kaçınılmaz. O yolu kesmek
değil, **nereden geçtiğini** zorlamak doğru iddia. Sinyalin niyetin içinde taşınması ayrıca
gerekli: audit'in "strateji ne istedi, risk ne verdi" karşılaştırması ikisi bir aradayken
mümkün.

**Mührün sınırı açıkça belgelenmiştir ve test edilmiştir**
(`test_muhur_kasitli_asilabilir`). Python'da bir sınıfın dışarıdan kurulmasını imkânsız
kılmanın yolu yok; closure hücresindeki anahtara ulaşmak mümkün. Mührün işi kazara atlamayı
ve onay-sonrası değişikliği kapatmak, kasıtlı atlamayı **görünür** kılmak. Ne vaat ettiğini
dürüst tutmayan bir güvenlik katmanı, olmayan bir garanti satar.

**Risk motoru aşağı çeker, yukarı asla.** `OnayliNiyet.__post_init__` onaylı maruziyetin
`[0, sinyalin hedefi]` aralığında olmasını zorunlu kılar. Mühür içeriğe bağlı olduğu için
bu kural onay anıyla sınırlı kalmaz, niyetin ömrü boyunca sürer.

**Azaltan niyetler hiçbir engele tabi değildir.** `SELL` ve `FLAT` — SAFE_MODE, cooldown,
günlük zarar limiti, volatilite guard'ı ve promotion kapısının hepsinin önünde geçer ve
boyutlandırmadan da muaftır. Bir çıkışı engellemek riski azaltmaz, artırır; K-008/3'ün
"mevcut çıkış emirleri çalışmaya devam eder" maddesi bu kuralın özel hâli. Ters sırada,
kill switch tetiklenen bir sistemde strateji pozisyonundan çıkamaz hâle gelir — yani kill
switch riski dondurmak yerine kilitler.

**Audit append-only ve zincirlenmiştir.** `Defter` protokolü `sil`/`guncelle` tanımlamaz;
SQLite tarafında UPDATE ve DELETE tetikleyiciyle **hata** fırlatır (sessizce yutulmaz). Her
satır kendinden öncekinin hash'ini taşır: kurcalamayı engellemez ama **sessiz** kurcalamayı
imkânsız kılar.

**PostgreSQL Faz 6'da bağlanır, şeması Faz 5'te donar.** K-011 PostgreSQL'i "eşzamanlı
yazma, transaction ve dayanıklı state gerektiğinde" diye gerekçelendiriyor; Faz 5'te o
ihtiyacın hiçbiri yok (tek süreç, tek yazıcı, canlı emir yok) ve ayakta bir veritabanı
gerektiren test takımı fazın kendi kriterine hiçbir şey katmazdı. Ama yazım **yeri**
değişecekse yazım **biçimi** şimdi sabitlenmeli: `migrations/001_faz5.sql` `SqliteDefter`
ile aynı kolonları taşıyor ve `tests/unit/test_audit.py` ikisinin ayrışmadığını kontrol
ediyor. Faz 6 bir şema tasarımıyla değil bir bağlantı dizgisiyle başlıyor.

**Risk motoru backtest'te opsiyoneldir, execution'da değil.** `Backtest(..., risk=None)`
varsayılanı Faz 1-4'ün ölçümlerini yeniden üretilebilir tutuyor (`sq lab dogrula` buna
dayanıyor) ve risk özeti `sonuc_hash`'e yalnızca **varsa** giriyor — `"risk": None` yazmak
eski her kaydın hash'ini değiştirirdi. Bu "risk atlanabilir" demek değil: backtest bir
simülasyondur, borsaya giden kapı değil. Paper/live modunda motor zorunlu ve promotion
zinciri risksiz koşulmuş bir sonucu `risk_incelemesi` aşamasında **ölçülemedi** sayar.

---

## K-033 — Risk limitlerinin her biri kaynağını ve gözden geçirme koşulunu taşır

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 5 · **Rapor:**
`docs/Faz-5-Risk-Raporu.md`

**Karar:** Sekiz limitin her biri `config/risk.json`da bir `Gerekce` ile birlikte yaşar ve
gerekçe iki kaynaktan birini beyan eder:

- **`olculdu`** — sayı gerçek veriden çıktı. Tam persentil dağılımı kayıtta durur, yani
  persentil kararı yeniden ölçmeden değiştirilebilir (K-021'in kurduğu kalıp).
  `veri_sha256` zorunludur.
- **`istah`** — sayı bir risk iştahı tercihi, ölçüm değil. **`gozden_gecirme` koşulu
  zorunludur**: "ne zaman yeniden düşüneceğiz" sorusu cevapsız kalan bir tercih, hak
  ettiği için değil kimse dokunmadığı için kalıcı olur.

Gerekçesi olmayan bir limit **tanımlanamaz** (Pydantic doğrulaması reddeder), ve üç limit
(`volatilite_esigi`, `ters_hareket_atr_carpani`, `gunluk_zarar_limiti`) `istah` olarak
işaretlenemez. İştahı ölçüm gibi göstermek en tehlikelisi olurdu: ölçülmüş görünen bir
tercih tartışılamaz hâle gelir.

**Yürürlükteki değerler (BTC/USDT 1h, 45.576 bar, veri `e3adb02c2a6a`, limit kimliği
`c3608583bd9f`):**

| Limit | Değer | Kaynak | Dayanak |
| --- | ---: | --- | --- |
| `azami_maruziyet` | %30 | iştah | Proje-Fikri §11. Gözden geçirme: Faz 8 |
| `islem_basina_risk` | %0,5 | iştah | Proje-Fikri §42. Gözden geçirme: Faz 5 raporundaki maruziyet tablosu |
| `ters_hareket_atr_carpani` | 6,3934× | **ölçüldü** | 24 barlık ufukta aleyhte hareketin p90'ı (45.538 örnek) |
| `gunluk_zarar_limiti` | %2,0 | **ölçüldü** | 1.899 günde 24 kez (%1,26) tetikliyor |
| `drawdown_limiti` | %20 | iştah | K-019'un `max_drawdown` kapısı (%25) altında kalmak zorunda |
| `ardisik_kayip_limiti` | 10 | iştah | Faz 4'ün 564 kayıp serisinde p95 = 10 |
| `cooldown_bar` | 24 | iştah | 1h'de bir gün ≈ bir pozisyon ömrü (medyan tutma 27 saat) |
| `volatilite_esigi` | %2,0466 | **ölçüldü** | ATR(14)/fiyat p99 (45.562 bar) |

**"2×ATR" varsayımı ölçümle çürütüldü.** Yaygın kural stop mesafesini 2×ATR alır. Bu
veride 24 barlık ufukta aleyhte hareketin **medyanı** 2,07 ATR — yani 2,0 seçmek vakaların
yarısında gerçek riskin altında kalmak olurdu. K-007'nin "belirsizlikte kötü yöne yuvarla"
kuralı p90'ı (6,39) dayatıyor. Risk ufkunun tutma süresi olmasının sebebi v1'de borsada
duran bir stop emri olmaması (Faz 7): pozisyon strateji `FLAT` diyene kadar açık kalır.

**Drawdown limiti ile promotion kapısı arasındaki ilişki koda gömülüdür.** `limitler.py`
`drawdown_limiti >= 0,25` ise konfigürasyonu reddeder: fren kapıdan **önce** devreye
girmek zorunda, yoksa canlıda bugün promote etmeyeceğimiz bir düşüşe izin verilmiş olur.
Sayı iki yerde yaşıyor (`risk/` `research/`i import etmiyor — canlı karar yolu araştırma
koduna bağlanmamalı) ve ayrışmaması testle korunuyor.

**Drawdown limiti bir tavan değil, bir tetikleyicidir.** Aşıldığında kill switch'i açar ve
yeni girişi durdurur; zaten olmuş bir düşüşü geri **alamaz**, çünkü K-008/2 açık
pozisyonları kapatmayı açıkça yasaklıyor. Ölçüldü: `cok_faktor` risk altında %20,1 düştü,
limit %20,0 — limit tam tasarlandığı gibi çalıştı ve yine de aşıldı. Aynı sınıf bir ayrım
`azami_maruziyet`te de var: tavan **hedef** maruziyet üzerindedir, gerçekleşen üzerinde
değil (ölçüldü: %30 tavanda gerçekleşen %30,14, fill sonrası fiyat hareketi).

---

## K-034 — Operasyonel state SQLite (WAL); PostgreSQL Faz 7'ye ertelendi

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 6 · **Tadil eder:** K-011,
Final-Doküman "Teknoloji Stack" satırı *Operasyonel state → PostgreSQL (Faz 5+)*

**Karar:** Faz 6'nın operasyonel state'i (paper koşu durumu, portföy, risk durumu, audit
log) **SQLite**'ta, WAL modunda yaşar. PostgreSQL Faz 7'ye (execution sandbox) ertelendi.
`migrations/001_faz5.sql` olduğu yerde ve dondurulmuş kalır; `risk/audit.py`'nin şemayla
kolon hizası testi (`tests/unit/test_audit.py`) sürüyor.

**Gerekçe — K-011'in kendi ölçütüne göre:** K-011 PostgreSQL'i *"eşzamanlı yazma,
transaction ve dayanıklı state gerektiğinde"* diye gerekçelendirmişti. Faz 6'nın mimarisi
o üç ihtiyaçtan yalnızca ikisini doğuruyor:

- **Eşzamanlı yazma yok.** FastAPI paper trading sürecinin *içinde* çalışıyor (K-036);
  yazan tek şey trader döngüsü, dashboard yalnızca okuyor. Tek yazıcı + çok okuyucu tam
  olarak SQLite WAL'ın tasarım noktası.
- **Transaction ve dayanıklılık gerekiyor** ve SQLite ikisini de veriyor: WAL +
  `synchronous = FULL` ile commit'lenmiş bir satır süreç çökmesinde de işletim sistemi
  çökmesinde de kalır.

Geriye tek bir gerçek argüman kalıyordu — "nasıl olsa gerekecek, şimdi kur". Onu Faz 6'nın
**bitti kriteri** çürütüyor: *"30 gün kesintisiz çalışma (kesinti olduysa sebebi kayıtlı ve
giderilmiş)."* Bu kriteri ölçen koşunun yanına, ayakta kalması gereken ikinci bir servis
(Docker konteyneri — bu makinede yerel `psql` yok) koymak, ölçülen şeyi ölçüm aracının
kendisiyle kirletir. 30 günü bölen şey konteynerin yeniden başlaması olursa, o kesinti
paper trading altyapısı hakkında hiçbir şey söylemez ama kriteri düşürür.

**Ne zaman geri dönülür (gözden geçirme koşulu, K-033'ün kalıbı):** aşağıdakilerden biri
gerçekleştiğinde PostgreSQL kararı yeniden verilir — ertelenmiş karar, iptal edilmiş karar
değildir.

1. İkinci bir yazıcı süreç doğduğunda (Faz 7'nin execution/reconciliation döngüsü trader
   döngüsünden ayrı bir süreçse).
2. Audit tablosu 10 milyon satırı aştığında veya `runs/` toplamı 5 GB'ı geçtiğinde.
3. Çok sembollü çalışmaya geçildiğinde.

**Bedeli açıkça:** SQLite'ta `JSONB` yok (`govde`/`durum` TEXT olarak JSON tutuluyor,
zaten öyleydi), `BIGSERIAL` yerine `INTEGER PRIMARY KEY`, ve append-only kuralı Postgres'in
`RULE`'ları yerine trigger + `RAISE(ABORT)` ile zorlanıyor. Şema ikizliği testle korunduğu
için göç, bir bağlantı dizgisi ve bir toplu kopyalama olarak kalır.

### Gözden geçirme ölçümü — 2026-09-11 (Faz 7'ye dönüş)

Bu karar Faz 5'ten Faz 6'ya, Faz 6'dan Faz 7'ye, Faz 7'den Faz 8'e taşındı. Üçüncü
taşımada sorulması gereken soru *"yine erteleyelim mi"* değil, **koşullar gerçekleşti
mi** — çünkü koşullar zaten yukarıda yazılı ve ölçülebilir. Ölçüldüler:

| # | Koşul | Eşik | **Ölçülen** | Gerçekleşti mi |
| --- | --- | ---: | ---: | --- |
| 1 | İkinci yazıcı süreç | — | Tek yazıcı (`live/kilit.py` zorluyor); `sq testnet` komutları kendi dosyalarına yazan ayrı koşular | **Hayır** |
| 2a | Audit satır sayısı | 10.000.000 | **1.091** | **Hayır** (‰0,1) |
| 2b | `runs/` toplam boyut | 5 GB | **3,7 MB** | **Hayır** (‰0,7) |
| 3 | Çok sembollü çalışma | — | Tek sembol; çok sembollü arama K-045 ile kapandı | **Hayır** |

**Üçü de uzak, ve ikisi *uzaklaşıyor*.** K-045 tek sembollü aramayı kapattığı için koşul
3 kendiliğinden gerçekleşmiyor; Faz 8'in planlanan mimarisi (tek strateji, tek sembol, tek
koşturucu) koşul 1'i de doğurmuyor. Koşul 2'nin eşiklerine bugünkü hızla ulaşmak, audit
tarafında dört buçuk basamak büyüme ister.

**Karar değişmiyor ve bu artık bir erteleme değil.** Aradaki fark K-039'un ayrımıyla aynı:
erteleme, ölçülebilir bir şeyi ölçmemektir; bu ise ölçülmüş ve **koşulların
gerçekleşmediği** görülmüştür. Faz 8'e taşınan şey karar değil, **bir sonraki ölçüm**.

`migrations/001_faz5.sql` dondurulmuş kalıyor ve `tests/unit/test_audit.py`'nin kolon
hizası testi sürüyor — göç yolu açık tutuluyor, ama açık tutmak ile kullanmak farklı
şeyler.

### Gözden geçirme ölçümü — 2026-09-16 (Faz 9, K-052/6'nın istediği ölçüm)

Koşul 3 (**çok sembollü çalışma**) araştırma tarafında gerçekleşti: 734 sembol, 20,06 milyon
bar, 628 MB (K-056). K-052/6 bu durumda kararın *yeniden verilmesini* istiyordu; verildi.

| # | Koşul | Eşik | **Ölçülen** | Gerçekleşti mi |
| --- | --- | ---: | ---: | --- |
| 1 | İkinci yazıcı süreç | — | Tek yazıcı; arşiv indirici tek süreç, dosya başına atomik `replace` | **Hayır** |
| 2a | Audit satır sayısı | 10.000.000 | **1.091** (değişmedi) | **Hayır** |
| 2b | `runs/` toplam boyut | 5 GB | **3,8 MB** | **Hayır** |
| 3 | Çok sembollü çalışma | — | **Evet, araştırma deposunda** (628 MB parquet); operasyonel state tek sembol, tek koşu | **Kısmen** |

**Karar yine değişmiyor, ama gerekçe değişiyor.** Koşul 3'ün sorusu *"operasyonel state
PostgreSQL'e taşınmalı mı"*ydı; ölçülen yazma deseni gerektirmiyor: çoklu sembol verisi
**araştırma deposudur** (parquet + DuckDB, K-011), operasyonel state değil — transaction yok,
eşzamanlı yazıcı yok, tek süreç dosya yazıyor. Yani koşul gerçekleşti, ölçüldü ve
**gerektirmediği görüldü**. Bir sonraki tetikleyici koşul 1 veya 2'dir; koşul 3 kapanmıştır.

---

## K-035 — Gözlem modu: promotion geçmemiş strateji canlı veride koşabilir, ama kanıt üretemez

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 6 · **İlgili:** K-010, K-018, K-019,
K-032

**Sorun:** `MOD_ESIGI["paper"] = Asama.RISK_INCELEMESI`, yani paper modunda bir stratejinin
sinyali ancak `out_of_sample` kapısını geçtiyse risk motorundan geçer. Faz 4'te ölçülen
**yedi stratejinin yedisi de kaldı** (K-019) ve Faz 5 eşikleri gevşetmedi. Bugün başlatılan
bir paper koşusunda risk motoru her sinyali `PROMOTION_YOK` ile reddeder. Faz 6'nın dört
bitti kriterinden biri — *"süreç öldürülüp yeniden başlatıldığında pozisyon ve emir state'i
doğru toparlanıyor"* — hiç pozisyon açılmadığı için **boş yere** geçer. Bu, bu projenin
açıkça kaçındığı hata sınıfı: ölçülmemiş bir şeyin ölçülmüş görünmesi.

**Reddedilen çözüm:** `MOD_ESIGI["paper"]` eşiğini indirmek. K-018 *"sayısal eşik
esnetilemez"* diyor ve K-019 bunun mekanizmasını
(`test_faz4_olcumlerinden_hicbiri_gecmiyor`) kurmuş. Kriteri ölçülebilir kılmak için
kapıyı indirmek, kriteri ölçmenin sebebini yok eder.

**Karar:** Dördüncü bir çalışma modu eklendi: `gozlem`. `MOD_ESIGI["gozlem"] = Asama.YOK`.

1. **Risk motorunun promotion kapısı dışındaki her limiti tam olarak uygulanır** —
   SAFE_MODE, drawdown, günlük zarar, cooldown, volatilite guard, boyutlandırma. Gözlem
   modu risk motorunu gevşetmez; yalnızca *"bu strateji canlıya aday mı"* sorusunu sormaz.
2. **Gözlem koşusunun ürettiği hiçbir kayıt promotion kanıtı olamaz.** Koşu kaydı `mod`
   alanını taşır ve promotion kanıtı üretimi `mod != "paper"` olan bir koşuyu **reddeder** —
   atlamaz, hata verir. Zorlaması `tests/unit/test_gozlem_modu.py`'de: gözlem koşusundan
   promotion ilerletmeye çalışan test `PromotionHatasi` bekler.
3. **Gerçek para yolu kapalıdır.** `gozlem` `MODLAR` içinde ama gerçek borsa bağlantısı
   yalnızca `paper` ve `live` modlarında kurulur; gözlem her zaman simüle fill kullanır
   (`backtest/fill.py`, yani K-004 ve K-007 aynen geçerli).

**Gerekçe:** Faz 6'nın ölçtüğü şey stratejinin kârı değil, **altyapının 30 gün ayakta
kalması ve doğru toparlanması**. O ölçüm için gereken tek şey pozisyon açan bir sinyal
akışı; sinyalin canlıya aday olup olmaması ölçümle ilgisiz. İki soruyu tek kapıya bağlamak
(K-010'un promotion kapısı) doğruydu — ama o kapı *sermayeyi* koruyor, *test kapsamını*
değil. Gözlem modu ikisini ayırıyor: sermaye yolu kapalı kalır, kapsam açılır.

**Ne kaybediyoruz, açıkça:** Gözlem koşusu 30 gün sürse bile K-018/3'ün beşinci eşik
adayını (paper/backtest drift üst sınırı) **kalibre etmeye yetmez** — o ölçüm promotion'a
girecek bir strateji üzerinde yapılmalı, çünkü drift'in büyüklüğü stratejiye bağlıdır.
Gözlem koşusundan çıkacak olan şey drift ölçüm **yönteminin** çalıştığının kanıtı; sayının
kendisi değil.

---

## K-036 — Dashboard: Vite + React SPA, FastAPI tarafından servis edilir

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 6 · **Tadil eder:** Final-Doküman
"Teknoloji Stack" satırı *Frontend → Next.js + TypeScript + Tailwind + shadcn/ui* ·
**İlgili:** K-012

**Karar:** Faz 6'nın 4 sayfalık dashboard'u **Vite + React + TypeScript + Tailwind +
shadcn/ui** ile yazılır, `apps/web/` altında yaşar, statik build'i **FastAPI servis eder**.
Next.js kullanılmıyor. Diğer stack seçimleri (TypeScript, Tailwind, shadcn/ui,
lightweight-charts) **aynen korunuyor** — değişen tek şey uygulama çatısı.

**Gerekçe:** Next.js'in ScryneQuant'a verecek üç şeyi var — SSR/SSG, dosya-tabanlı
yönlendirme, ve API route'ları — ve üçü de bu üründe karşılıksız:

- **SSR'ın getirisi sıfır.** Tek kullanıcı, localhost, ve ekrandaki her sayı canlı
  (SSE ile geliyor). Sunucuda render edilen bir sayfa, ilk boyamadan sonra hemen bayatlar.
  İlk-boyama gecikmesi bir SEO veya mobil-3G problemi; burada ikisi de yok.
- **API route'ları çakışıyor.** API zaten FastAPI'de ve orada olmak zorunda: risk durumu,
  portföy ve audit **trader sürecinin belleğinde** yaşıyor. İkinci bir API katmanı, o
  belleğe erişmek için trader'a HTTP atan bir proxy'den ibaret olurdu.
- **Süreç sayısı Faz 6'nın bitti kriterine giriyor.** *"30 gün kesintisiz"* ölçülen şey;
  ayakta kalması gereken her ek süreç o ölçümün paydası. Statik build tek bir dizin, tek
  bir `StaticFiles` mount'u, ve düşecek ikinci bir servis yok. (Aynı gerekçe K-034'te de
  belirleyiciydi.)

**Bedeli açıkça:** Çok kullanıcılı, kimlik doğrulamalı, SEO'lu bir web ürününe dönülürse bu
karar yeniden verilmelidir. K-014 (*yalnızca kendi hesabı, kendi parası*) o dönüşü hukuki
olarak zaten kapatıyor — yani bu bedel, v1 kapsamı içinde ödenmiyor.

**Gözden geçirme koşulu:** §28'in kalan altı sayfası açıldığında (Faz 7+) yönlendirme
yükü ölçülür; `react-router` yetmezse karar yeniden değerlendirilir.

---

## K-037 — Sinyali engelleyen katman risk motorunun dışında olabilir; izin veren katman olamaz

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 6 · **İlgili:** K-028, K-032, K-008/3,
§24

**Sorun:** Faz 6 iki yeni engel getiriyor ve ikisi de risk motorunun dışında yaşıyor:

1. **Bayat veri** (§24): akıştan uzun süre mesaj gelmediyse yeni pozisyon açılmaz.
2. **`ok` olmayan bar** (K-028): kopma sonrası REST'ten tamamlanan bar `backfilled`dır,
   o barda ne karar verilir ne fill yapılır.

İkisi de "sinyal risk motorunu atlayamaz" kuralıyla (§9.1/3) ilk bakışta gerilimde: bir
sinyal risk motoruna hiç ulaşmadan eleniyor.

**Karar — asimetri açıkça yazılıyor:**

- Bir sinyali **engelleyen** katman risk motorunun dışında olabilir. Engelleme riski
  artırmaz; en kötü ihtimalle bir fırsat kaçar ve o kayıp sayılabilir (`AtlamaSebebi`).
- Bir sinyale **izin veren** katman yalnızca risk motorudur. `OnayliNiyet`in tek üreticisi
  risk motoru olmaya devam eder (K-032) ve execution kapısı başka hiçbir şey kabul etmez.

**Gerekçe:** §9.1/3'ün koruduğu şey "her sinyal risk motorunu görsün" değil, **"borsaya
giden yolda risk motorundan geçmemiş hiçbir şey olmasın"**. Bu ikisi aynı şey değil ve
farkı önemli: birincisini şart koşmak, bozuk veriyle beslenen bir kararı risk motoruna
sokmak demek olurdu — yani guard'ı, korumaya çalıştığı şeyin **içine** taşımak. Risk
motorunun deterministik ve I/O'suz kalması (K-002/K-003 kalıbı) bu ayrımın ön koşulu:
motor duvar saatine bakmıyor ve bakmamalı, dolayısıyla "veri kaç saniyeliktı" sorusunu
cevaplayamaz.

**Bayat veri guard'ının iki ayrıntısı, ikisi de bilinçli:**

1. **Azaltan niyetler engellenmez.** Bayat veride `SELL`/`FLAT` geçer. Bu, K-008/3'ün
   ("kill switch'te mevcut çıkışlar çalışmaya devam eder") ve risk motorunun sıfırıncı
   adımının aynı kuralı: bir çıkışı engellemek riski azaltmaz, artırır. Bayatlığı bir
   çıkış engeline çevirmek, bağlantı sorununu pozisyon kilidine dönüştürürdü.
2. **Bayatlık, gelen barın nabzından *önce* ölçülür.** Barın kendisi de bir mesajdır;
   nabzı önce işlersek akış her bar geldiğinde taze görünür ve guard 1h timeframe'de hiç
   tetiklenmez. Ölçülmek istenen şey "bu bar gelene kadar ne kadar sessizlik vardı" —
   çünkü o sessizlikte kaçırılmış bar olabilir.

**Bunun ön koşulu bir sözleşme:** koşturucu **her** akış mesajında `nabiz()` çağırmak
zorunda, yalnızca kapanmış barlarda değil. Çağırmazsa guard sürekli açık kalır. Bu bir
güvenlik açığı değil (yanlış yön güvenli yöndür) ama guard'ı işe yaramaz hâle getirir, ve
işe yaramaz bir guard er ya da geç kapatılır.

**Kayıt:** Engellenen her sinyal sayılıyor (`AtlamaSebebi.VERI_BAYAT`,
`AtlamaSebebi.FILL_BARI_OK_DEGIL`) ve bayatlığa giriş/çıkış koşu günlüğüne yazılıyor.
Sessizce elenen sinyal yok — K-024'ün ("bayrak tekildir, boşluk uydurulmaz") ve Faz 3'ün
`AtlamaSebebi` kalıbının devamı.

**Bayat veri kesinti sayılmaz.** Faz 6'nın *"30 gün kesintisiz"* kriterinin sayacı
(`KESINTI_OLAYLARI`) bayatlığı içermiyor: bayat veri koşuyu bölmez, yalnızca yeni girişi
durdurur. Kesinti sayılanlar kopma, hata ve toparlanma ayrışması.

---

## K-038 — Toparlanma bir geri yükleme değil, yeniden üretimdir

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 6 · **İlgili:** K-009, K-032, K-034 ·
**Kanıt:** `tests/unit/test_toparlanma.py`

**Karar:** Süreç yeniden başladığında diskten okunan durum **olduğu gibi kabul edilmez**;
bağımsız bir kaynaktan yeniden üretilip karşılaştırılır. Uyuşmazlıkta koşu **durur**
(`ToparlanmaAyrismasi`), tahmin yürütülmez.

| Diskten okunan | Bağımsız kaynak | Uyuşmazsa |
| --- | --- | --- |
| Portföy (nakit, miktar, ort. maliyet) | `fill` defterinin baştan uygulanması | durur |
| Bekleyen kararın özeti | Strateji + risk motorunun barı yeniden karara bağlaması | durur |
| Risk durumu | **yok** — türetilecek bağımsız kaynağı yok | — |

**Neden karar saklanmıyor da yeniden üretiliyor:** `OnayliNiyet` mühürlü ve mühür süreç
başına rastgele (K-032). Serileştirilmiş bir onay yeniden başlayan süreçte doğrulanamaz;
onu yeniden mühürlemek ise "onayın tek üreticisi risk motorudur" garantisini kırardı —
diskteki bir JSON'u değiştiren herkes onay üretebilir hâle gelirdi. Bu yüzden kayda giren
şey onay değil **özet**tir ve tek işi karşılaştırılmaktır.

**Kontrol noktasının yeri bu kararın sonucudur.** Durum satırı bir barın fill'i ve risk
güncellemesi yapıldıktan **sonra, kararı verilmeden önce** yazılır. Karar sonrası
yazılsaydı yeniden üretim yanlış başlangıç noktasından yapılırdı: karar adımı risk
durumunu değiştirebiliyor (drawdown limiti aşıldığında `kill()`), ve SAFE_MODE açıkken
yeniden üretilen karar `Red(DRAWDOWN)` yerine `Red(SAFE_MODE)` verirdi — yani sistem kendi
kendine ayrışma ilan ederdi.

**Bayatlık kontrol noktasının parçası.** Toparlanan süreç henüz hiç nabız almamıştır;
bayatlığı yeniden ölçse her kararı bayat yoldan üretirdi. Kararın girdisi olan bayatlık
değeri bu yüzden kayda giriyor (K-037/2 ile birlikte okunmalı).

**Üçüncü satır bilerek boş ve bu bir eksiklik olarak kayıtlı.** Risk durumunun bağımsız
bir ikinci kaynağı yok — equity eğrisinin tamamını saklamadan yeniden hesaplanamaz. Onu
"doğrulandı" diye raporlamak, doğrulanmamış bir şeyi doğrulanmış göstermek olurdu.
Korunması yazım tarafında: atomik yazım + `synchronous=FULL` (K-034).

**Ölçüm yöntemi de bir karar:** toparlanmanın testi "okunan alanlar kayıtlıyla eşit mi"
diye bakmıyor — o, kaydı kaydın kendisiyle doğrulamak olurdu. Bunun yerine **iki koşu**
karşılaştırılıyor: 60 barı kesintisiz işleyen koşu ile 30 barda öldürülüp yeniden
başlatılan koşunun portföyü, risk durumu ve fill defteri birebir aynı olmak zorunda.
Kesinti hiçbir iz bırakmamalı.

**Yan etki, açıkça:** Yeniden üretim audit'e o bar için **ikinci** bir karar satırı yazar.
Bu bilinçli — karar gerçekten yeniden verildi — ve koşu günlüğündeki `toparlandi` olayı
sebebini açıklıyor. Alternatifi, risk kararını audit'e yazmadan veren bir kod yolu açmak
olurdu; o kapı bir kez aralandığında kapanmaz.

---

## K-039 — Kaç hipotez denendiği sayılır ve ön kayıt zorunludur

**Durum:** kabul · **Düzeltme K-044 ile kapandı (2026-09-11).** · **Tarih:** 2026-09-11 · **Faz:** 6 · **Tamamlar:**
K-010, K-018, K-019 · **Kanıt:** `tests/unit/test_hipotez.py`,
`tests/unit/test_promotion.py::TestHipotezSayisi`

**Sorun — promotion zincirinin en sessiz başarısızlık yolu.** K-019'un yedi kapısı
strateji **başına** çalışıyor ve hiçbiri *"bu kaçıncı denemeydi"* sorusunu sormuyor. Faz
4'te yedi hipotez denendi ve yedisi de kaldı; bu doğru sonuçtu. Ama elli tane daha
denenirse, kapılara **hiç dokunmadan**, birinin şans eseri geçme olasılığı ciddi biçimde
yükselir.

Yani K-018'in *"sayısal eşik esnetilemez, değiştirmek iz bırakır"* kuralı, **eşiğe el
sürmeden** delinebiliyordu: yeterince çok deneyerek. Hiçbir kural çiğnenmez, hiçbir test
kırılmaz, `test_faz4_olcumlerinden_hicbiri_gecmiyor` yeşil kalır — ve sonunda "kapıları
geçen bir strateji" ortaya çıkar. O stratejinin kaçıncı deneme olduğu kayıtlı değilse,
geçtiği kapının ne anlama geldiği de bilinmiyor demektir.

Bu, K-010'un korumaya çalıştığı sabırsızlığın en kılık değiştirmiş hâli: kapıyı zorlamak
yerine kapıya yeterince çok kez gitmek.

**Karar — üç parça:**

1. **Hipotez defteri** (`docs/Hipotez-Defteri.jsonl`, `research/hipotez.py`). Bir hipotez
   = (strateji, timeframe, veri hash'i, parametre ızgarası, **parametre seçim yöntemi**).
   Aynı beşlisi ikinci kez yeni bir çekiliş **değil**; ızgarayı genişletmek veya seçim
   kuralını değiştirmek **yeni bir çekiliştir** ve sayılır.

   *Seçim yöntemi kimliğe Faz 4'e dönüş 2'de eklendi:* kimliğin dışında bırakmak, "argmax
   dene, olmadı platoyu dene, olmadı şunu dene" zincirini **bedava çekiliş** yapardı —
   aynı ızgara, aynı veri, ama her seferinde yeni bir tahmin. Aynı veriye yeni bir soru
   sormanın her biçimi sayılmak zorunda.
2. **Ön kayıt zorunlu.** Hipotez sonucu görülmeden önce yazılır ve bir **gerekçe** taşır
   (≥20 karakter, zorunlu). Sonradan yazılan bir hipotez "zaten bunu bekliyordum" demenin
   kaydıdır, kanıt değil. Gerekçesiz bir hipotez, ızgarayı genişletmenin kibar adıdır.
3. **Sayı promotion kanıtının parçası.** `Kanit.hipotez_sirasi` yoksa `out_of_sample`
   aşaması **ölçülemedi** sayılır — "kaldı" değil, ölçülemedi. Bu, K-019'un *"ölçülemeyen
   kapı geçilmiş sayılmaz"* kuralının aynısı. Geçen bir stratejinin kaydı "47. hipotez
   (defterde toplam 120)" diye okunur.

**Bilerek yapılmayan: eşiği düzeltmek.** Bonferroni benzeri bir düzeltme çekici ama buraya
yanlış oturur — stratejiler bağımsız değil (aynı veri, örtüşen sinyaller, aynı rejim), yani
düzeltme çarpanı bilinmiyor. Uydurulan bir çarpan, olmayan bir kesinlik iddia eder ve bu
projede en pahalı hata sınıfı tam olarak budur. Deflated Sharpe (Bailey & López de Prado)
gibi yöntemler var ama varsayımları tartışmalı ve bu veri üzerinde **ölçülmedi**.

**Bu yüzden karar "açık düzeltme" ile veriliyor** — K-019'un eşikleri Faz 4'ün ölçümüne
kadar nasıl açık bırakıldıysa aynı kalıpta. Düzeltme, kapıları geçen **ilk** strateji
çıktığında verilir; o an defterdeki sayı bilinecek ve düzeltmenin büyüklüğü somut bir
soruya dönüşecek. Şimdiden bir sayı seçmek, ölçülmemiş bir şeye sayı vermek olurdu.

**Defterin yeri bir karar.** `runs/` altında olması doğal görünüyordu ama yanlış: `runs/`
`.gitignore`'da ve **iz bırakmadan silinebilen bir defter, defter değildir.** Sayacı
sıfırlamak, bu kararın engellemeye çalıştığı şeyi bir `rm` ile yapmak olurdu. Defter
`docs/` altında, sürüm kontrolünde, karar günlüğünün yanında duruyor — tuttuğu şey bir
çalışma çıktısı değil, bir araştırma kaydı. Biçim JSONL: bir hipotez eklemek diff'te tek
bir satır.

**Faz 4'ün yedi hipotezi geriye dönük kaydedildi** ve kayıtları bunu açıkça söylüyor.
Geriye dönük kayıt ön kayıt sayılmaz ve o yedi hipotez ön-kayıt kanıtı olarak
kullanılamaz — ama **sayılmak zorundalar**: kaydedilmemiş bir çekiliş, sayacı olduğundan
küçük gösterir ve bu kararın tam olarak engellemek istediği şeyi yapar.

**Zorlama laboratuvarda, yalnızca kapıda değil — ve bu bir düzeltme.** Kararın ilk hâlinde
defteri yalnızca promotion kapısı kontrol ediyordu. Yanlıştı: **çekiliş laboratuvarda
yapılıyor.** `sq lab karsilastir` yedi aileyi koşturup sonuçlarını gösterebiliyor, defter
bundan habersiz kalıyordu — ve bu gerçekten oldu (`docs/Faz-4-Donus-1-Timeframe.md`, "Süreç
hatası"). Artık `sq lab` komutlarının hepsi defteri zorluyor; kaydedilmemiş bir strateji
**koşturulamıyor**.

Kaçış kapısı bilerek yok. "Sadece bakıyorum" diye koşturulan bir strateji de bir
çekiliştir; bakmak bedavaysa, yeterince bakan biri kapıyı delmiş olur.

**Pratik sonuç:** Faz 4'e her dönüşte, denenecek hipotez önce `sq lab hipotez-kaydet` ile
gerekçesiyle yazılır. Defter `sq lab hipotezler` ile okunur.

---

## K-040 — Emir kimliği içerikten türer; yazım gönderimden önce; `UNKNOWN` yeniden gönderilmez

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 7 · **İlgili:** §33, §25, K-032,
K-038 · **Kanıt:** `tests/unit/test_oms.py`

Faz 7'nin bitti kriterlerinden biri: *"Aynı intent iki kez gönderildiğinde tek emir
oluşuyor (duplicate order üretilemiyor)."* Bu karar o cümlenin üç mekanizmasını sabitliyor.
Üçü de yapısal — hiçbiri bir dikkate bağlı değil.

### 1. Emir kimliği onaylı niyetin **içeriğinden** türetilir

İstemci emir kimliği (`newClientOrderId`) rastgele üretilmiyor, sayaçtan gelmiyor: onaylı
niyetin içeriğinin hash'i. Aynı niyet → aynı kimlik → borsa ikincisini reddeder.

**Mühür kimliğe girmiyor** ve bu ayrıntı belirleyici: mühür süreç başına rastgele (K-032).
Girseydi, süreç yeniden başladığında aynı niyet farklı bir kimlik üretir ve koruma **tam da
en çok gerektiği anda** — restart sonrasında — çökerdi. Testi bunu ölçüyor: mühür anahtarı
döndürülüp aynı içerik yeniden mühürleniyor, kimlik değişmiyor.

Kimlik 34 karakter (`sq` + 32 altıgen). Binance sınırı 36; 128 bit, çarpışma bu ölçekte
anlamsız.

### 2. İki katman, ikisi de gerekli

| Katman | Neyi engelliyor |
| --- | --- |
| Emir defteri (yerel) | Aynı niyetin ikinci kez **gönderilmesini** |
| Deterministik kimlik (borsa) | Defterin kaçırdığı bir gönderimin **emir olmasını** |

Yalnızca borsa tarafına güvenmek yetmez: o reddi görebilmek için isteği **göndermiş** olman
gerekir, ve gönderimin kendisi risk — yanıt kaybolursa emrin oluşup oluşmadığını bilemezsin.
Defter bu riski hiç almamayı sağlıyor. Borsa tarafı ise defterin yedeği: dosya kaybolsa,
elle silinse veya başka bir makineden koşulsa bile koruma ayakta.

Defterde `istemci_kimligi` **birincil anahtar**, otomatik bir sayı değil. "Tek emir" iddiası
bir veritabanı kısıtı olarak yaşıyor; otoartan bir anahtarla aynı kimlikten iki satır mümkün
olurdu ve iddia bir koda bağlı kalırdı.

### 3. `SUBMITTED` diske ağ çağrısından **önce** yazılır

Ters sırada, gönderim ile yazım arasında ölen bir süreç **yetim emir** bırakırdı: borsada
var olan ama sistemin hiç bilmediği bir emir. Onu bulmanın tek yolu borsayı sorgulamak
olurdu ki sistem aramayı bile bilmezdi.

Bu sırayla en kötü durum, hiç gönderilmemiş bir emrin kaydı — ve reconciliation onu borsaya
sorup bulamayınca kapatır. **İki hatadan bilinen olanı seçiliyor.** Faz 6'nın kontrol
noktası kararının (K-038) aynı mantığı: kaydı erken yazmak, kaydı geç yazmaktan güvenli.

### 4. `UNKNOWN` bir başarısızlık değil, bir bilinmezliktir

Gönderim yapıldı ama yanıt kaybolduysa (zaman aşımı, bağlantı koptu, süreç öldü) emir
borsada olabilir de olmayabilir de.

- `FAILED` = gönderim **hiç yapılamadı**, yani borsada emir olmadığı **biliniyor**.
  Yeniden gönderilebilir.
- `UNKNOWN` = gönderildi, sonuç bilinmiyor. **Yeniden gönderilemez.**

`UNKNOWN`u `FAILED` sayıp yeniden denemek, duplicate emir üretmenin en kısa yoludur. State
machine'de `UNKNOWN → SUBMITTED` diye bir geçiş **yok**: yeniden göndermek kod düzeyinde
imkânsız. Çıkışın tek yolu borsayı **sorgulamak** (§25 reconciliation); varsayım yok.

`UNKNOWN` bu yüzden "açık emir" kümesinde — reconciliation onu sormak zorunda. Bilinmezlik,
yokluk değil.

### 5. Emir silinemez, kimlik değiştirilemez

İkisi de veritabanı tetikleyicisi. Bir emri silmek, reconciliation'ın karşılaştıracağı iki
taraftan birini yok etmek demek; kimliği değiştirmek ise o emri başka bir emre dönüştürmek.
Durum güncellemesi serbest ama geçilen yol `gecmis` sütununda birikiyor — "bu emir hangi
yoldan buraya geldi" bir uyuşmazlık araştırmasının ilk sorusu.

---

## K-041 — Ağ hatası üç sınıfa ayrılır; imzanın zamanı borsadan gelir

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 7 · **Tamamlar:** K-040 · **İlgili:**
K-015, K-032, K-038 · **Kanıt:** `tests/unit/test_imzali.py`,
`tests/unit/test_mutabakat.py`, `runs/testnet/faz7-100.json`,
`runs/testnet/faz7-kesinti.json`

K-040 duplicate korumasının üç mekanizmasını sabitledi ama bir soruyu açık bıraktı: bir
gönderim başarısız olduğunda **hangi** duruma geçilir? Bu karar o eşlemeyi ve onu mümkün
kılan iki alt kararı yazıyor.

### 1. Bir ağ hatası üç ayrı şey söyleyebilir ve ayrımı **adaptör** yapar

| Hata | Anlamı | Emir durumu | Yeniden gönderim |
| --- | --- | --- | --- |
| `GonderilemediHatasi` | İstek bayta hiç dökülmedi (ConnectTimeout, DNS) | `FAILED` | serbest |
| `BorsaReddetti` | Borsa açıkça reddetti (4xx + hata kodu) | `REJECTED` | sebep giderilmeden hayır |
| `BelirsizSonuc` | Yanıt kayboldu (ReadTimeout, kopan bağlantı, **5xx**) | `UNKNOWN` | **asla** |
| `SaatSapmasi` | `-1021`; emir oluşmadı ama sebep saat | `FAILED` + koşu durur | saat düzelmeden hayır |

**5xx'in `BelirsizSonuc` olması Binance'in kendi sözleşmesinden geliyor**, bizim ihtiyatımızdan
değil: 503/504 açıkça "yürütme durumu bilinmiyor" demek. 4xx ile 5xx'i aynı kovaya koymak,
oluşmuş bir emri oluşmamış saymaktır.

**Ayrım neden çağırana bırakılamaz.** İsteğin bayta dökülüp dökülmediğini yalnızca transport
bilir. Çağırana bırakılsaydı her çağıranın aynı doğru kararı vermesi gerekirdi — ve bir kez
unutulan yerde duplicate emir doğardı.

**Bu yüzden ccxt kullanılmadı.** Faz 1'in okuma adaptörü ccxt'yi transport olarak kullanıyor
ve bu doğru bir karardı. Emir tarafında aynı tercih yanlış olurdu: ccxt `NetworkError`
altında "gitmedi" ile "bilmiyorum"u **aynı sınıfa** koyuyor. Silinen ayrım duplicate emrin
ta kendisi. Emir yolu ham `requests` istisnalarına bakıyor.

### 2. İmzalı isteğin `timestamp`i yerel saatten değil, borsadan türer

Ölçüm (2026-09-11, IPv4 zorlanmış, host başına 9 örnek): yerel saat borsadan **2.640 ms
geride**, yayılım 46-247 ms, iki farklı host aynı değeri veriyor — yani sapma sunucuda değil
**yerel makinede** ve kararlı.

`recvWindow=5000` ile bu bugün çalışır. Ama saat kaymaya devam eder ve eşiği geçtiği gün
imzalı istekler `-1021` ile **sessizce** reddedilir; sebep emir mantığında aranır.

**İşletim sistemi saatini düzeltmek (`w32tm`) reddedildi** — sorunu çözmüyor, erteliyor.
Bunun yerine fark açılışta bir kez ölçülüp `time.monotonic()` çıpasına bağlanıyor ve
periyodik tazeleniyor. Sistem saati değişse bile (elle, NTP sıçraması) `monotonic`
etkilenmez, yani imza geçerli kalır. Sapmanın kendisi bir **sağlık göstergesi** olarak
raporlanıyor (`sq testnet durum`), gizlenmiyor.

İki senkron arasında farkın kendisi 2.000 ms'den çok değişirse `SaatSapmasi` fırlıyor: o
aralıkta üretilmiş imzalar güvenilmez ve bunu sessizce yeni değere geçerek örtmek, geçersiz
bir pencereyi görünmez yapardı.

**İmzalanan metin, gönderilen metin olmak zorunda.** Sorgu dizesi elle kurulup URL'ye
gömülüyor; `requests`in `params=` yolu kullanılmıyor. İki ayrı kodlayıcının bugün aynı
çıktıyı vermesi bir varsayımdır, ve ayrıştıkları gün hata `-1022` (geçersiz imza) olarak
görünür — sebebi kodlamada aranmaz.

### 3. Mutabakat çözebildiğini çözer, çözemediğinde **durur**

Sınır bilgiye dayalı, keyfi değil: defterin *"bilmiyorum"* dediği yerde (`SUBMITTED`,
`UNKNOWN`) borsa otoritedir ve cevabı yazılır. Defterin *"biliyorum"* dediği yerde
(`ACKNOWLEDGED`) borsa başka bir şey söylüyorsa ortada çelişki vardır ve çözmenin tek
dürüst yolu durmaktır (K-038'in kuralı).

Borsada açık ama defterde olmayan bir emir de durdurur: sistemin üretmediği ya da kaydını
kaybettiği bir emir, ikisinde de defter borsadaki maruziyeti eksik biliyor demektir.

**Pozisyon mutabakatı bilerek yapılmıyor.** Bakiye farkını emirlerden türetmek, koşu
başındaki bakiyenin bağımsız bir kaydını gerektirir; o kayıt yokken yapılan karşılaştırma
"borsa ne diyorsa o" demenin süslü hâli olur. Faz 8'in *"açıklanamayan pozisyon farkı:
sıfır"* kriteri o kaydı kurar. K-039'un "ölçülemedi ≠ kaldı" ayrımı burada da geçerli.

### Ölçülen (2026-09-11, Binance Spot Testnet)

| Kriter | Sonuç |
| --- | --- |
| 100 emir, elle müdahalesiz | **100/100 FILLED**, hata 0, belirsiz 0, süre 2 dk 4 sn |
| Ara mutabakat | 5 kez, hepsi temiz |
| Duplicate (gerçek borsa) | aynı niyet ikinci kez → **ağa hiç çıkmadı** |
| Kesinti: emir oluştu, yanıt kayboldu | `UNKNOWN` → mutabakat → **`FILLED`** |
| Kesinti: emir oluşmadı, yanıt kayboldu | `UNKNOWN` → mutabakat → **`FAILED`** |
| Saat sapması (koşu boyunca) | −2.535 ms; hiçbir `-1021` yok |

Son iki satır birlikte okunmalı: çağıran açısından **ayırt edilemez** iki durumdan iki farklı
doğru sonuca varıldı. Mutabakatın tahmin yürütmediğinin kanıtı bu — cevabı borsadan alıyor.

### İlk gerçek koşunun bulduğu iki hata

Birim testlerin tamamı yeşilken gerçek testnet iki hata gösterdi, ve ikisinin de sebebi
aynı: **sahte borsa gerçeğinden hoşgörülüydü.**

1. **`FLAT` borsaya olduğu gibi gönderiliyordu** → `Invalid side`. `FLAT` bizim
   sözlüğümüzde var (tam çıkış), Binance'te yok. Çeviri artık sözleşmenin kenarında
   (`borsa_yonu`); defterde yön `FLAT` olarak kalıyor çünkü "tamamen kapat" ile "azalt"
   farklı kararlardır ve audit'in ikisini ayırt etmesi gerekir.
2. **Defter istenen miktarı yazıyordu, gönderilebileni değil.** Lot adımına yuvarlama
   farkı küçük görünüyor ama sonucu şu: `FILLED` bir emrin `kalan`ı sıfır değil — tamamen
   dolmuş ama defterde hâlâ bakiyesi olan bir emir, ve pozisyon hesabında sessizce biriken
   bir fark. Tam olarak bu projenin "neredeyse doğru" dediği hata sınıfı.

Ders kayda geçiyor: **bir sahte, gerçeğin reddettiğini kabul ediyorsa ona karşı yeşil olan
test bir şey kanıtlamaz.** `SahteBorsa` artık yön ve lot adımı kontrolü yapıyor.

---

## K-042 — Funding rate bir bilgi kaynağı olarak eklenir; üç hipotez, tek tur, geri dönüşsüz

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 4'e dönüş 3 · **Tamamlar:** K-039 ·
**İlgili:** K-002, K-016, K-025, K-030 · **Kanıt:** `docs/spikes/05-funding-verisi.md`

**Bağlam.** Faz 4 yedi hipotezi çürüttü, dönüş 1 (timeframe) ve dönüş 2 (parametre seçim
yöntemi) de çürüdü. Üçü de **aynı kavanozdan** çekilişti: aynı veri, aynı fiyat geçmişi,
yeni bir tahmin. K-039'un uyarısı tam olarak buna: yeterince çok çekmek, eşiğe dokunmadan
kuralı delmektir. Bu yüzden dördüncü bir parametre denemesi **yapılmıyor**; devam edilecekse
bilgi kaynağı değişmeli.

### 1. Neden funding rate, neden çoklu sembol değil

**Çoklu sembol + göreli güç reddedildi**: mimariyi kırıyor. Kapsam (v1) *"tek sembol
(BTC/USDT)"* diyor; çoklu sembol portföy katmanı, sembol-arası korelasyon ve portföy düzeyi
risk limitleri demek — Faz 5'in risk motorunu yeniden açmak. Büyük bir iş, ve başarısızlık
olasılığı bu işi haklı çıkaracak kadar düşük değil.

**Funding rate mimariye dokunmuyor**: BTC/USDT spot'ta tek pozisyon, tek sembol. Değişen tek
şey stratejinin gördüğü bilgi — fiyat geçmişi yerine türev piyasasının **konumlanması**. Bu
OHLCV'den türetilemeyen bir büyüklük, yani gerçekten yeni bir soru.

**Spike 5 hipotez uzayını kendisi daralttı.** Dört aday kaynak ölçüldü, üçü elendi:
`openInterestHist`, `globalLongShortAccountRatio` ve `takerlongshortRatio` Binance'te
yalnızca **~31 gün** saklanıyor. Walk-forward kurulamaz. Geriye tek kanal kaldı: funding
rate, 7,01 yıl, 8 saatte bir, sıfır boşluk.

### 2. Funding bir maliyet değil, bir bilgidir

Sistem **spot** işlem yapıyor; spot'ta funding ödenmez. Maliyet modeline (K-016, K-021,
K-025) dokunulmuyor. Funding yalnızca özellik olarak girer. Bu ayrım yazılı olmalı çünkü
sezgiye ters: funding kelimesi bir ödemeyi çağrıştırıyor ve bir gün biri onu maliyet modeline
eklemeye kalkarsa, o değişiklik backtest sonuçlarını sessizce bozardı.

### 3. Eşikler mutlak değil, persentil olmalı

Ölçülen medyan funding **+0,0096% / 8 saat** — kalıcı pozitif. Mutlak bir eşik ("funding > 0")
neredeyse her zaman doğru olur ve hiçbir şey ayırt etmez. Eşikler kayan pencere persentili
olarak tanımlanıyor. Bu bir optimizasyon tercihi değil, verinin tanımından çıkan bir kısıt.

### 4. Hizalama nedensel olmak zorunda

`fundingTime` ödemenin **gerçekleştiği** an. `t` barı yalnızca `fundingTime <= t` olan
kayıtları görebilir. 8 saatlik bir seriyi 1h barlara yaymak, dikkat edilmezse gelecekten
bilgi sızdırır — K-002'nin kapattığı hata sınıfı. Hizalama geriye dönük (`merge_asof`
backward) yapılıyor ve look-ahead testi bu alanı da kapsıyor. Funding kaydı yoksa alan
`NaN` kalır, **uydurulmaz** (K-024).

### 5. Durma kuralı — sonucu görmeden yazıldı

**Üç hipotez, tek tur.** Ön kayıtla yazılır, ölçülür, biter.

| # | Hipotez | Soru |
| --- | --- | --- |
| 1 | `funding_ters` | Kalabalıklaşma tersine mi çalışıyor? |
| 2 | `funding_filtre` | Kalabalıklaşma, mevcut ailelerin OOS çöküşünü açıklıyor mu? |
| 3 | `funding_egilim` | Birikimli funding bir rejim göstergesi mi? |

Üçü de BTC/USDT **1h**, tek parametre ızgarası, seçim yöntemi **`tepe`**.

**Hiçbiri K-019'un yedi kapısını geçemezse funding fikri kapanır.** Dördüncü aile yok,
ikinci seçim yöntemi yok, timeframe varyasyonu yok, ızgara genişletmesi yok. Bunlardan
herhangi biri yapılırsa **ayrıca sayılır** ve bu kararın ihlalidir.

**"Yaklaşırsa devam" kuralı bilerek reddedildi.** Cazip görünüyor — yedi kapının beşini geçen
bir aileden birkaç varyasyon daha çekmek. Ama o, sonucu gördükten sonra çekiliş sayısına karar
vermektir; yani durma kuralının olmaması. K-039'un engellemeye çalıştığı şeyin tam olarak
kibar hâli.

Defter 35'ten **38**'e çıkıyor. K-039'un açık düzeltmesi (çoklu test) hâlâ açık ve ilk geçen
strateji çıktığında verilecek — o an defterdeki sayı 38 olacak.

### 6. Bu karar neyi vaat etmiyor

Baz oran düşük. Faz 4 ve iki dönüş, aktif yönetimin bu veride al-tut'u yenemediğini ölçtü;
funding'in bunu değiştireceğine dair bir kanıt **yok** — olsaydı hipoteze gerek kalmazdı.
Üçüncü bir çürütme beklenen sonuçtur ve başarısızlık değildir: sistemin işi cevabı ölçmek,
istenen cevabı üretmek değil.

### 7. SONUÇ (2026-09-11, aynı gün): **çürütüldü, kural uygulandı**

Üç hipotez ön kayıtla yazıldı (defter 36-38), ölçüldü, üçü de kapılarda kaldı. **Funding
fikri kapandı.** Ayrıntı: `docs/Faz-4-Donus-3-Funding.md`.

Sonuç beklenen yöndeydi ama tablo Faz 4'ten beri görülmemiş bir şey içeriyor:
`funding_egilim` projenin **ilk pozitif OOS Sharpe**'ını üretti (+0,288) ve yedi kapının
dördünü geçti; `funding_filtre`nin mekanizması ölçülebilir biçimde çalıştı — donchian'ın OOS
Sharpe'ını −0,348'den −0,094'e taşıdı, işlem sayısını hiç düşürmeden.

**Buna rağmen dördüncü bir çekiliş yapılmıyor** — ve bu kararın bütün değeri burada. Izgarayı
genişletip `funding_egilim`i 24 işlemden 30'a çıkarmak, eşiğe dokunmadan kapıyı delmek
olurdu. Durma kuralı tam olarak bu anı öngörerek, sonucu görmeden yazıldı.

Funding'in "işe yaramadığı" **ölçülmedi**; ölçülen, bu ızgarada ve bu veride kapıları
geçecek kadar güçlü olmadığı. Fark korunuyor.

## K-043 — Planlı duruş kesinti değildir; onu ayıran şey bir bayrak dosyasıdır

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 6 · **Tamamlar:** K-034, K-038 ·
**İlgili:** K-009, K-037 · **Kanıt:** `tests/unit/test_durdurma.py`

**Bağlam.** Faz 6'nın kriteri *"30 gün kesintisiz çalışma (kesinti olduysa sebebi kayıtlı
ve giderilmiş)"*. Koşu bir Windows zamanlanmış görevinin altında yaşıyor ve düzgün kapanış
`SIGINT`/`SIGTERM`e bağlıydı. O yol orada **ulaşılamaz**: sinyali gönderecek bir terminal
yok ve başka bir sürecin konsol grubuna `CTRL_BREAK` yollanamıyor. Geriye tek seçenek sert
kill kalıyordu — ve sistem onu, kendi kuralı gereği, `temiz_kapanmadi` olarak kaydediyor.

Sonucu şuydu: **kodu düzeltmek için yapılan her yeniden başlatma kriterin kendisini
kırıyordu.** Kriter altyapının beklenmedik şekilde düşüp düşmediğini ölçmek istiyor; o
hâliyle ölçtüğü şey makinenin 30 gün hiç dokunulmamış olmasıydı. İkisi aynı şey değil ve
farkı kapatmak eşiği gevşetmek olmazdı — ölçülen büyüklüğü düzeltmek olurdu.

### 1. Ayrım niyette, mekanizmada değil

Bir duruş iki sorudan biriyle ayrılır: **kim istedi?** Süreç kendi kapanış yolundan
çıktıysa ve sebebini yazabildiyse bu bir `durdu`dur. Yazamadan öldüyse `temiz_kapanmadi`dır
ve sebebi "bilinmiyor" kalır. Kesinti sayan ikincisidir; birincisi zaten K-038'in
kanıtladığı yolu (yeniden üretim) izleyerek geri geliyor.

`KESINTI_OLAYLARI` değişmedi ve değişmemeliydi: `DURDU` zaten o kümede değildi. Eksik olan
şey kural değil, **kuralın kullanılabilir bir kapısının olmaması**ydı.

### 2. Bayrak dosyası, HTTP ucu değil

Dashboard salt okunur ve öyle kalmalı (`tests/unit/test_api.py`). Koşuyu durduran bir uç
koymak, arayüzü ölçümün üstünde bir yetkiye çıkarırdı — K-036'nın *"arayüz asla ölçümün
önüne geçmez"* çizgisinin tersi. Bayrak dosyası ise kilidin (`live/kilit.py`) zaten kurduğu
kalıbı izliyor: koşunun yanında yaşayan, işletim sistemi düzeyinde, ağ yüzeyi olmayan bir iz.

Sebep **isteyen tarafından** yazılıyor (`sq paper durdur --sebep`), çünkü onu bilen tek
taraf o. Süreç kendi kapanışına "bilinmiyor" yazmak zorunda kalmıyor.

### 3. Bayrağın varlığı niyettir, içeriği değil

Bozuk ya da yarım yazılmış bir bayrak **yine de istek sayılıyor**; yalnızca sebebi
"bilinmiyor" oluyor. Tersi — ayrıştırılamayan dosyayı yok saymak — durdurma yeteneğini bir
JSON ayrıntısına bağlardı. Durdurulamayan bir koşu, kaydı eksik bir koşudan kötüdür.

Bayrak hem başlangıçta hem kapanışta siliniyor: kalan bir bayrak, bir sonraki koşuyu
başlar başlamaz durdururdu.

### 4. Bu karar neyi vaat etmiyor

Planlı duruş kesinti sayılmıyor ama **bedava** da değil: duruş boyunca gelen barlar akıştan
alınmıyor, toparlanmada REST'ten `backfilled` olarak geliyor ve K-028 gereği o barların
açılışında fill iddia edilmiyor. Yani uzun bir planlı duruş, kesinti sayacını değil **ölçüm
yoğunluğunu** düşürür. 30 günün kapanışında bu ayrım rapora yazılacak: kaç bar `ok`, kaç bar
`backfilled` geldi.

---

## K-044 — Çoklu test düzeltmesi ölçüldü: eşik `0,50` → `1,02`

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 4'e dönüş 4 · **Kapatır:** K-039'un
açık düzeltmesi · **Değiştirir:** K-019 (`oos_sharpe` sınırı) · **İlgili:** K-018, K-033,
K-007 · **Kanıt:** `docs/Faz-4-Donus-4-Coklu-Test.md`, `tests/unit/test_coklu_test.py`,
`runs/deneyler/coklu_test/`

**Bağlam.** K-039 çekilişleri saymayı getirdi ama düzeltmeyi **açık bıraktı** ve sebebini
yazdı: *"stratejiler bağımsız değil (aynı veri, örtüşen sinyaller, aynı rejim), yani
düzeltme çarpanı bilinmiyor. Uydurulan bir çarpan, olmayan bir kesinlik iddia eder."*
Düzeltmenin *"kapıları geçen ilk strateji çıktığında"* verileceği söylenmişti.

**O erteleme artık savunulamaz ve sebebi ertelemenin kendisinde.** Düzeltmeyi geçen bir
stratejiyi **gördükten sonra** tanımlamak, bu projenin başka her yerde yasakladığı şeydir:
sonucu görüp kuralı ona göre ayarlamak (K-018, K-042'nin durma kuralı). Ertelemenin
gerekçesi *"o an defterdeki sayı bilinecek"*ti — ve o an **şimdi**: K-042 ile funding
kapandı, bekleyen çekiliş yok, defter 38'de dondu. Sayının bilindiği ve hiçbir sonucun
görülmediği tek an bu.

### 1. Çarpan uydurulmadı, ölçüldü

Yöntem `research/coklu_test.py`de, özeti: defterdeki her çekilişin OOS **sinyal takvimi**
çıkarılıyor, dairesel kaydırılıyor ve **gerçek backtest motorundan** geçiriliyor. Kaydırma
işlem sayısını, tutma süresini ve piyasada kalma oranını koruyor; yok ettiği tek şey
fiyatla hizalanma — yani edge.

**Kaydırma iterasyon başına paylaşılıyor.** Bağımsız kaydırma kolay olurdu ve yanlış
olurdu: stratejiler arası korelasyonu koparır, maksimumun dağılımını genişletir ve
düzeltmeyi olduğundan büyük gösterirdi — K-039'un reddettiği uydurulmuş çarpanı arka
kapıdan geri getirmek. Paylaşılan kaydırmada korelasyon ne ise o kalıyor; çarpan verinin
kendi yapısından geliyor.

**Maksimum, K-019'un ucuz kapılarını geçen çekilişler arasından alınıyor** (`asgari_islem`,
`max_drawdown`). Bu bir hatanın düzeltmesi: ilk ölçümde maksimum 31'inin hepsinden
alınıyordu ve null, rastgele bir stratejiye p99'da 4,2 Sharpe atfediyordu. Sebep ölçümle
bulundu — uçların tamamı **az işlemli** çekilişlerdendi (14 işlemle ölçülen Sharpe'ın
örneklem varyansı devasadır). Ama o çekiliş `asgari_islem ≥ 30` kapısında zaten ölüyor;
onu maksimuma katmak, hiç geçemeyecek bir kapıdan geçme olasılığını hesaplamaktı.

### 2. Ölçülen sayılar

31 ölçülebilir çekiliş, 4.000 iterasyon, edge yok:

| Yanlış-pozitif | Düzeltilmiş `oos_sharpe` | %90 GA |
| --- | ---: | --- |
| %20 | 0,589 | 0,574 – 0,605 |
| %10 | 0,777 | 0,754 – 0,800 |
| **%5 (seçilen)** | **1,017** | **0,975 – 1,055** |
| %1 | 2,424 | 1,829 – 3,040 |

**Eski eşik 0,50'nin gerçek yanlış-pozitif oranı %26,3.** Yani 0,50 hiçbir zaman %5'lik bir
kapı değildi; 31 çekilişte dört denemeden birini şansa geçiren bir kapıydı. Eşik
esnetilmemişti — eksik kalibre edilmişti, ve farkı yalnızca çekiliş sayısı ortaya
çıkarabilirdi.

**Sınır `1,02` olarak donduruluyor** (ölçülen 1,017, GA içinde kalan en yakın iki
basamak). %5 bir **iştah** kararıdır (K-033), ölçüm değil: Scryne seçti, gerekçesi
"bilimsel yayın standardı ve K-019'un mevcut eşikleriyle aynı ruhta". %1 ölçüldü ama
seçilmedi — güven aralığı [1,83-3,04] o sayıyı 4.000 iterasyonda savunulamaz kılıyor.

### 3. İki bağımsız yöntem birbirini doğruluyor

| Yöntem | Sonuç | Varsayımı |
| --- | ---: | --- |
| Permütasyon null'ı (ölçülen) | **1,017** | yok — korelasyon veriden geliyor |
| Deflated Sharpe (Bailey & López de Prado) | 0,922 | denemelerin Sharpe'ları normal dağılıyor |
| Bonferroni | 1,300 | **bağımsızlık** — bu veride yanlış |

İlk ikisi %10 içinde uyuşuyor; ikisi tamamen farklı varsayımlar yaptığı için bu anlamlı
bir yakınsama. Bonferroni'nin yukarıda kalması K-039'un öngörüsünü doğruluyor: bağımsızlık
varsaymak fazla düzeltiyor.

### 4. Asıl bulgu eşik değil

**Projenin en iyi sonucu, saf şans beklentisinin altında.** 31 çekilişin gerçek en iyisi
`cok_faktor` 4h/plato ile 0,4585; p-değeri **0,296**. Yani hiçbir stratejinin edge'i
olmasa bile, 31 çekiliş yapan biri vakaların yaklaşık üçte birinde bu kadar iyi bir sonuç
görürdü. Deflated Sharpe daha da keskin: şans beklentisi 0,92, gerçek en iyi 0,46 — yani
gözlenen sonuç, rastgeleliğin **üretmesi beklenenden daha kötü**.

31 çekilişin OOS Sharpe dağılımı: ortalama −0,31, sapma 0,44, yalnızca 7'si pozitif.

Bu, "aramanın başarısız olduğu" değil, **"aramanın henüz hiçbir şey bulmadığı"**nın
ölçülmüş hâlidir. Fark önemli ve korunuyor (K-042/5 ile aynı ayrım).

### 5. Eşik bir sabit değil, defterin fotoğrafı

`COKLU_TEST_ESIGI = 1,02` **31 çekilişte** geçerli. Defter büyüdükçe gerçek eşik yükselir;
sabit yerinde kalırsa kapı sessizce gevşer ve K-039'un engellemeye çalıştığı şey
düzeltmenin kendi içinden geri gelir.

Bu yüzden `COKLU_TEST_CEKILIS_SAYISI = 31` de koda yazıldı ve testle bağlandı: sayı
değişirse test kırılır ve `sq lab coklu-test` yeniden koşturulmak zorunda kalır. Sabiti
elle büyütmek, ölçülmemiş bir sayıya ölçülmüş süsü vermektir.

### 6. Bu karar neyi vaat etmiyor

**Düzeltme yalnızca `oos_sharpe` kapısına uygulandı.** Diğer altı kapı (`oos_is_orani`,
`wf_katman_basari`, `parametre_kararliligi`, `asgari_islem`, `max_drawdown`,
`stres_dayanikliligi`) düzeltilmedi çünkü ölçülmedi: her biri için ayrı bir null gerekir ve
walk-forward ile stres kapıları iterasyon başına yeniden ölçülemeyecek kadar pahalı
(tek bir tam değerlendirme dakikalar sürüyor). Yani **kapı kümesinin tamamının** yanlış
pozitif oranı hâlâ bilinmiyor; bilinen, en çok konuşulan kapının oranı.

Yön bilinçli olarak muhafazakâr: uygunluk süzgeci gerçek kapı kümesinden **gevşek**
olduğu için ölçülen düzeltme gerçeğinden **büyük** çıkıyor (K-007, belirsizlikte kötü
yöne yuvarla).

**Ve 1d'nin yedi çekilişi ölçüme giremedi.** Faz 4'e dönüş 1'de walk-forward hiçbir
katmanda geçerli aday bulamamış, araç sayı uydurmak yerine reddetmişti. Sayı üretmemiş bir
çekiliş yanlış pozitif de üretemez, dolayısıyla maksimum istatistiğine giremez — ama
defterden de silinmez: denendi, sayılır. Defter 38, ölçülebilir 31.

---

## K-045 — Maliyet duvarı bağlayıcı kısıt değil; tek sembollü yönlü arama kapanıyor

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 4'e dönüş 5 · **Kapatır:** tek sembollü
yönlü strateji araması · **İlgili:** K-016, K-021, K-039, K-042, K-044 · **Kanıt:**
`docs/Faz-4-Donus-5-Tavan.md`

**Bağlam.** K-044 çoklu test düzeltmesini ölçtükten sonra ortada şu tablo vardı: 38 hipotez
denendi, hiçbiri geçmedi, ve en iyi sonuç şans beklentisinin altındaydı. Doğal bir itiraz
duruldu: **38 çekilişin 38'i de sinyal tarafındaydı; maliyet tarafına hiç bakılmadı.**
Gidiş-dönüş maliyet %0,306 (10 bps komisyon + 5,3 bps slippage, iki yön) ve bu her
stratejinin aşması gereken bir duvar. Maker yürütmeyle yarıya inebilirdi.

Bu itiraz ciddiydi ve test edilmeden reddedilemezdi.

### 1. Haftalarca yürütme modeli yazmak yerine tavan ölçüldü

Maker yürütme modeli kurmak (doluluk olasılığı, dolmama yolu, testnet ölçümü) haftalar
alırdı. Onun yerine **üst sınır** ölçüldü: maliyet **sıfır** kabul edilip aynı çekilişler
yeniden koşturuldu.

Sıfır maliyet fiziksel olarak imkânsızdır ve amaç tam olarak budur — hiçbir yürütme
iyileştirmesi bu sonuçları geçemez. Tavan tabandan alçaksa, aradaki her şey boştur.

**Bu bir hipotez çekilişi değildir ve K-039'a girmez.** Strateji seçilmiyor, parametre
aranmıyor, yeni bir soru sorulmuyor; sorulan tek şey *"tavan kapıdan yüksek mi"*. Bir üst
sınır ölçümü, bir bahis değil.

### 2. Sonuç: tavan kapının yarısında

| | En iyi strateji | OOS Sharpe | Kapı | Geçen |
| --- | --- | ---: | ---: | --- |
| 1h, maliyet 0x | `funding_filtre` | 0,526 | 1,02 | **hiçbiri** |
| 4h, maliyet 0x | `ema_kesisim` (19 işlem) | 0,691 | 1,02 | **hiçbiri** |
| 1h, maliyet 0,25x | `funding_egilim` | 0,433 | 1,02 | **hiçbiri** |

**İki olası itiraz önden kapatıldı:**

*"Kapıyı K-044 ile yükselttin, tabii geçen olmaz."* — Eski, düzeltilmemiş 0,50 kapısına
göre de geçen yok. `funding_filtre` 0,526 ile Sharpe kapısını geçiyor ama `oos_is_orani`
ve `wf_katman_basari`'da kalıyor; `ema_kesisim` 4h 0,691 ile geçiyor ama 19 işlemle
`asgari_islem`'de kalıyor. Kapılar bir **konjonksiyon**dur ve tek kapı yeterli değildir.

*"Kapı gerçek maliyetle ölçüldü, sıfır maliyetli sonuçla karşılaştırmak haksız."* — Tersi
doğru: sıfır maliyette null stratejiler de maliyet ödemez, yani düzeltilmiş kapı 1,02'nin
**üstüne** çıkardı. Test stratejiler lehine cömert ve sonuç yine de olumsuz.

### 3. Kararın kendisi

**Maliyet duvarı bağlayıcı kısıt değilmiş.** Yürütmeyi iyileştirmek — maker emirler, BNB
indirimi, VIP kademe — ölçülen tavanı kapıya yaklaştırmıyor. Dolayısıyla:

1. **Maker yürütme modeli yazılmayacak.** Gerekçesi ortadan kalktı.
2. **Tek sembollü yönlü strateji araması kapanıyor.** BTC/USDT üzerinde klasik teknik
   göstergelerle yönlü tahmin, bu veri ve bu kapılarla tükendi — ve tükendiği ölçüldü,
   tahmin edilmedi.

### 4. Neden yeni bir arama programı da açılmıyor

Çoklu sembol (cross-sectional) cazip ve gerçekten farklı bir bilgi kaynağı. Yine de
açılmıyor, ve gerekçe K-044'ün kendisinden geliyor: **her yeni çekiliş kapıyı yükseltiyor.**
31 çekilişte %5 sınırı 1,02; 60 çekilişte daha yüksek olacak. Büyük bir yeni arama
programı, bulduğu şeyi geçirmek için kendi diktiği duvarı aşmak zorunda kalır.

Yeni bir kaynak ancak **marjinal değil belirgin** biçimde daha iyiyse açılmalı. Çoklu
sembolün böyle olduğuna dair elimizde ölçüm yok — yalnızca literatür var, ve bu proje
literatürle değil ölçümle karar veriyor.

### 5. Bu bir başarısızlık kaydı değil, bir ölçüm kaydı

Sistem yanlış çalışmadı. Tam tersine: **doğru çalıştığı için "burada bir şey yok"
diyebildi.** 1102 test, look-ahead koruması, deterministik backtest, atlatılamayan risk
motoru ve çoklu test düzeltmesi — bunların toplam işlevi, olmayan bir edge'i var
göstermemekti. O işlevi yerine getirdiler.

Ölçülen alternatif maliyeti somut: `ema_kesisim` ile canlıya geçilseydi OOS beklentisi
**−%4,2**'ydi. Aramanın durdurulması bir kayıp değil, o kaybın önlenmesidir.

### 6. Ne korunuyor, ne kapanıyor

**Kapanan:** tek sembollü yönlü strateji araması, maker yürütme çalışması, dördüncü bir
parametre/aile çekilişi.

**Korunan:** altyapının tamamı. Faz 6'nın 30 günlük koşusu devam ediyor (altyapı kanıtı,
bedeli yok). Piyasa koşulları değişirse — funding rejimi dönerse, komisyon yapısı
değişirse, yeni bir veri kaynağı erişilebilir olursa — aynı altyapı **saatler içinde**
yeniden ölçüm yapabilir. `sq lab kapilar`, `sq lab coklu-test` ve hipotez defteri
yerinde duruyor.

**Kapanmayan tek şey Faz 8'dir ve kapanamaz:** promotion'u geçen strateji olmadığı için
kontrollü live hiç başlamadı. Bu bir borç değil, kapının çalıştığının kanıtı (K-010).

---

## K-046 — Pozisyon mutabakatı üç taraflıdır; çıpa tazelenemez, komisyon tahmin edilemez

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 7'ye dönüş (Faz 8 hazırlığı) ·
**Kapatır:** Faz 7 §7'nin "pozisyon mutabakatı ölçülmedi" maddesi · **İlgili:** K-038,
K-040, K-041 · **Kanıt:** `tests/unit/test_pozisyon.py`, `runs/testnet/poz-1.json`

**Bağlam.** Faz 7 emir mutabakatını kurdu ve pozisyon tarafını bilerek açık bıraktı.
Gerekçesi `oms/mutabakat.py`de yazılıydı ve hâlâ doğru:

> *"Bakiye farkını emirlerden türetmek, koşunun başındaki bakiyenin bağımsız bir kaydını
> gerektirir; o kayıt yoksa yapılan karşılaştırma 'borsa ne diyorsa o' demenin süslü hâli
> olur."*

Faz 8'in bitti kriterlerinden biri *"açıklanamayan pozisyon farkı: sıfır"* diyor. O kriter
ölçülebilir olmadan Faz 8 başlayamaz — ve ölçülebilir kılan şey, eksik olan o kayıt.

### 1. Üç taraf, iki taraf değil

| Taraf | Nereden | Değişmez mi |
| --- | --- | --- |
| **Çıpa** — açılış bakiyesi | Borsadan, ilk emirden önce | **Evet** |
| **Akış** — defterin fill'leri | Bizim kaydımız | Hayır, koşuyla büyür |
| **Gerçek** — bugünkü bakiye | Borsadan, şimdi | — |

`çıpa + akış` bizim **iddiamız**, `gerçek` borsanın beyanı. İki taraflı bir karşılaştırma
(defterin emirleri ↔ borsanın emirleri) zaten var ve başka bir soru soruyor: *"emirler ne
durumda"*. Bu üçüncü taraf yeni bir soru soruyor: *"hesap, defterin söylediği yerde mi"*.
İkisi ayrı olmak zorunda, çünkü **bütün emirlerini doğru bilen bir defter bile** dışarıdan
gelen bir yatırmayı, elle yapılmış bir işlemi ya da başka bir sürecin emrini göremez. Para
o yollardan da hareket eder.

### 2. Çıpanın değişmezliği, ölçümün tamamı

Açılış kaydı yazılıp bırakılıyor: `oms/defter.py`de iki SQLite tetiği hem `UPDATE` hem
`DELETE` reddediyor, ve `acilis_yaz` deftere emir girmişse yazmayı da reddediyor.

Bu bir titizlik değil, mekanizmanın kendisi. Çıpa yazılabilir olsaydı, açıklanamayan bir
farkla karşılaşan herkesin elinde *"çıpayı tazele"* düğmesi olurdu; fark araştırılmak
yerine sıfırlanır ve kriter her koşuda kendiliğinden geçerdi. **Bir kapıyı elle
açılabilir yapmak, o kapıyı kaldırmaktır** (K-010'un aynı mantığı).

Çıpanın ilk emirden **önce** atılması da aynı sebepten zorunlu: emirler varken atılan bir
çıpa o emirlerin etkisini içine alır, akış onları bir kez daha sayar, ve fark tam olarak
o emirler kadar çıkar.

### 3. Komisyon bir muhasebe büyüklüğüdür ve tahmin edilemez

Binance komisyonu **alınan varlıktan** keser. 0,001 BTC'lik bir alımda hesaba 0,001 BTC
girmez, 0,000999 girer. Komisyonu hesaba katmayan bir "beklenen bakiye" her alımda ~%0,1
yanılır — ve bu, bu projenin *"neredeyse doğru"* dediği sınıfın ta kendisi: çökme yok,
hata yok, sadece emir sayısıyla birlikte büyüyen sessiz bir fark.

O yüzden komisyon defterde iki sütun: **rakam** ve **nereden geldiği**. Kaynak boşken
komisyon "sıfır" değil **"bilinmiyor"** demektir, ve ikisi diskte bile ayrı tutuluyor.

**Bilinmeyen komisyon varken beklenen bakiye hesaplanmıyor, tahmin edilmiyor.**
`%0,1 varsaydım` diyen bir satır yazmak yerine mutabakat *"ölçülemedi"* diyor ve koşu
duruyor. `oms/pozisyon.py`de `VARSAYILAN_ORAN` diye bir sabit bilerek yok.

Komisyonun iki kaynağı var ve biri diğerinin yedeği: `POST /api/v3/order` yanıtının
`fills` dizisi (normal yol, ek ağ çağrısı yok) ve `/api/v3/myTrades` (yanıtı kaybolmuş —
`UNKNOWN → FILLED`e çözülmüş — emirlerin **tek** kaynağı, çünkü `GET /api/v3/order`
komisyon taşımaz). İlk ölçüm **üzerine yazılmaz**: ikinci bir kaynağın farklı bir sayı
söylemesi sessizce kabul edilecek bir şey değil.

### 4. Bakiye `serbest` değil `toplam`

`EmirAdaptoru.bakiye()` artık `dict[str, float]` değil `dict[str, Varlik]` döndürüyor
(serbest + kilitli). Değişiklik bilerek **kırıcı**: eski hâli yalnızca `free` okuyordu,
yani açık bir limit emri hesabın bir kısmını görünmez yapıyordu ve pozisyon mutabakatı
her açık emirde haksız yere dururdu. Faz 7 yalnızca market emri kullandığı için bu vaka o
fazda hiç doğmadı — limit yolu açılırken doğuyor (K-047).

Tipi değiştirmek her çağıranı yeniden okumaya zorlar; alanın anlamını sessizce
genişletmek ise okunmamış bir çağıranda "neredeyse doğru" bir bakiye bırakırdı.

### 5. Tolerans türetildi, seçilmedi

`tolerans = max(1e-8, (brüt_ciro + |çıpa|) × 1e-9)`

İki taraf da kayan nokta taşıyor, o yüzden tolerans sıfır olamaz. **Brüt ciroyla**
ölçekleniyor, net pozisyonla değil: hata her işlemde birikir, net bakiyede değil. `1e-9`
oranı `float` epsilon'unun ~10 milyon katı (asla yanlış alarm vermez) ama bir lot adımının
(1e-5) on binde biri — yani gerçekleşebilecek en küçük gerçek farkı bile yutamaz. Test
ikisini de ölçüyor: bir lot adımlık fark **yakalanıyor**, 1e-13'lük gürültü **yakalanmıyor**.

### 6. Ölçüm: gerçek testnet'e karşı, iki yönde

`runs/testnet/poz-1` — 20 emir (10 alım/10 satım), gözlem modu:

| Varlık | Çıpa | Defter akışı | Beklenen | Borsada | Fark | Tolerans |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC | 1,00048 | 0,0 | 1,00048 | 1,00048 | **0,0** | 1,0e-8 |
| USDT | 9963,0282472 | −0,000012 | 9963,0282352 | 9963,0282352 | **0,0** | 1,01e-5 |

Ama temiz geçmek tek başına bir şey kanıtlamaz — ölçünün **bozulduğunda bozulduğu** da
gösterilmeli. Defterin bilmediği bir emir (doğrudan adaptörden, `EmirMotoru`'na
uğramadan, 0,0002 BTC market alımı) gönderildi ve mutabakat **durdu**:

```
AÇIKLANAMAYAN FARK — BTC : fark +0,0002000000 (tolerans 0,0000000100)
AÇIKLANAMAYAN FARK — USDT: fark −15,4368020000 (tolerans 0,0000101482)
```

Sayılar kuruşuna kadar tutuyor: 0,0002 × 77.184,01 = 15,43680. Çıkış kodu 1.

Market emri anında dolduğu için **açık emir listesinde hiç görünmedi**; yani bu farkı
emir mutabakatı yakalayamazdı. Pozisyon mutabakatının kendi başına gerekli olduğunun
kanıtı bu vaka.

### 7. Ölçülemeyen: komisyonun kendisi

**Testnet komisyon kesmiyor** — ölçüldü, varsayılmadı: `/api/v3/myTrades` yanıtında
`commission: '0.00000000'`, `commissionAsset: 'USDT'`. Yani yukarıdaki temiz sonuç,
komisyon yolu **hiç çalışmadan** da aynı çıkardı.

Bu kayda geçiyor çünkü tam olarak Faz 7'nin dersinin tekrarı, yönü değişmiş hâliyle:
*"bir sahte, gerçeğin reddettiğini kabul ediyorsa ona karşı yeşil olan test bir şey
kanıtlamaz."* Burada **testnet** sahtenin rolünde: gerçek hesabın keseceği bedeli
kesmiyor. Komisyon mantığı birim testlerde ölçülüyor (`SahteBorsa` %0,1 kesiyor ve
bakiyeye yansıtıyor) ama gerçeğe karşı ölçülmesi Faz 8'e kalıyor — ve Faz 8'in ilk
pozisyon mutabakatı, o yolun ilk gerçek sınavı olacak.


## Açık kararlar

Faz 0 kapandığında (2026-09-08) durum:

| No | Konu | Durum | Kapanacağı yer |
| --- | --- | --- | --- |
| K-011 | Parquet + DuckDB saklama | ✅ **kabul** | Spike 3 |
| K-015 | Binance erişimi, rate limit, testnet | ✅ **kabul** | Spike 1 |
| K-016 | Fee/slippage'ın kesin sayıları | ✅ **kabul** | Fee: Spike 4. Slippage → K-021 |
| K-017 | Birincil timeframe ve veri hacmi | ✅ **kabul** (1h) | Spike 2 |
| K-019 | Promotion kapılarının sayısal eşikleri | ✅ **kabul** | Faz 4, kapandı 2026-09-09 |
| K-020 | Slippage kalibrasyonu (ilk yöntem) | ⛔ değiştirildi → K-021 | — |
| K-021 | Slippage'ın yürütme penceresinden kalibrasyonu | ✅ **kabul** (5,2996 bps) | Faz 1, kapandı 2026-09-09 |
| K-022 | Bağımlılık kilidi (`uv`) | ✅ **kabul** | Faz 1 başlangıcı |
| K-023 | Klines ccxt'nin ham ucundan alınır | ✅ **kabul** | Faz 1 |
| K-024 | Bayrak tekildir; boşluk uydurulmaz | ✅ **kabul** | Faz 1 |
| K-025 | Maliyet konfigürasyonu ve geçici model bayrağı | ✅ **kabul** | Faz 1 |
| K-026 | İndikatör konvansiyonu TA-Lib; referans dondurulmuş | ✅ **kabul** | Faz 2 |
| K-027 | Strateji izolasyonu izin listesiyle zorlanır | ✅ **kabul** | Faz 2 |
| K-028 | `ok` olmayan barda karar da fill de yok | ✅ **kabul** | Faz 3 |
| K-029 | Backtest referansı kapalı formülle çapraz doğrulanır | ✅ **kabul** | Faz 3 |
| K-030 | Her karşılaştırmada al-tut kıyası bulunur | ✅ **kabul** | Faz 4 |
| K-031 | Strateji sinyalinin kabul edildiğini varsayamaz | ✅ **kabul** | Faz 4 |
| K-032 | Risk onayı bir tip, bir mühür ve bir kesme noktası | ✅ **kabul** | Faz 5 |
| K-033 | Her risk limiti kaynağını ve gözden geçirme koşulunu taşır | ✅ **kabul** | Faz 5 |
| K-034 | Operasyonel state SQLite (WAL); Postgres'in koşulları ölçüldü, doğmadı | ✅ **kabul** | Faz 6, ölçüldü 2026-09-11 |
| K-035 | Gözlem modu: kanıt üretmeyen canlı koşu | ✅ **kabul** | Faz 6 |
| K-036 | Dashboard Vite+React SPA, FastAPI servis eder | ✅ **kabul** | Faz 6 |
| K-037 | Engelleyen katman risk motorunun dışında olabilir, izin veren olamaz | ✅ **kabul** | Faz 6 |
| K-038 | Toparlanma bir geri yükleme değil, yeniden üretimdir | ✅ **kabul** | Faz 6 |
| K-039 | Kaç hipotez denendiği sayılır; ön kayıt zorunlu | ✅ **kabul** (düzeltme açık) | Faz 6 |
| K-040 | Emir kimliği içerikten türer; yazım gönderimden önce; UNKNOWN yeniden gönderilmez | ✅ **kabul** | Faz 7 |
| K-041 | Ağ hatası üç sınıfa ayrılır; imzanın zamanı borsadan gelir | ✅ **kabul** | Faz 7 |
| K-042 | Funding bir bilgi kaynağıdır; üç hipotez, tek tur, geri dönüşsüz | ✅ **kabul** | Faz 4'e dönüş 3 |
| K-043 | Planlı duruş kesinti değildir; ayıran şey bir bayrak dosyasıdır | ✅ **kabul** | Faz 6 |
| K-044 | Çoklu test düzeltmesi ölçüldü: `oos_sharpe` 0,50 → 1,02 | ✅ **kabul** | Faz 4'e dönüş 4 |
| K-045 | Maliyet duvarı bağlayıcı değil; tek sembollü yönlü arama kapandı | ✅ **kabul** | Faz 4'e dönüş 5 |
| K-046 | Pozisyon mutabakatı üç taraflı; çıpa tazelenemez, komisyon tahmin edilemez | ✅ **kabul** | Faz 7'ye dönüş |
| K-047 | İptalde de maruziyetin var olduğu varsayılır; fiyat kimliğe girmez | ✅ **kabul** | Faz 7'ye dönüş |

**Faz 0'ın dört spike'ı da kapandı; Faz 1 kendi üç kararını (K-023/024/025) verdi ve
K-021'i kapattı; Faz 2 K-026/027'yi, Faz 3 K-028/029'u, Faz 4 K-030/031'i, Faz 5
K-032/033'ü, Faz 6 K-034…039'u, Faz 7 K-040/041'i, Faz 4'e dönüşler K-042/043/044'ü
ekledi.**

**Açık karar kalmadı; geriye *tek* açık sayı kaldı** (aşağıda) — ve o da ölçülemiyor,
ertelenmiş değil. Projenin son açık kararı olan **K-019** (promotion kapılarının sayısal
eşikleri) Faz 4 sonunda gerçek veriyle kalibre edilip kapandı; K-039'un açık düzeltmesi
K-044 ile ölçülüp kapandı. Bundan sonraki kararlar yeni fazların kendi soruları olacak.

**K-039'un düzeltmesi kapandı (K-044, 2026-09-11).** Ölçüldü: 31 ölçülebilir çekilişte
%5 yanlış-pozitif sınırı **1,02** (eski eşik 0,50'nin gerçek oranı %26,3). Erteleme
gerekçesi *"kapıları geçen ilk strateji çıktığında"*ydı; o erteleme terk edildi çünkü
düzeltmeyi bir geçeni **gördükten sonra** tanımlamak, projenin başka her yerde yasakladığı
şeydir. Ölçüm, funding kapandıktan ve defter donduktan sonra — hiçbir sonuç görülmeden —
yapıldı.

**K-018/3'ün beşinci eşik adayı (paper/backtest drift üst sınırı) hâlâ ölçülmemiş.** Faz
6'da ölçülebilir hâle gelecekti; K-035 bunun neden **hâlâ mümkün olmadığını** kaydediyor:
drift'in büyüklüğü stratejiye bağlı, ve promotion'a girecek bir strateji henüz yok. Gözlem
koşusu ölçüm **yönteminin** çalıştığını gösterir, eşiğin sayısını vermez. Eşik, kapıları
geçen ilk stratejinin paper koşusunda kalibre edilecek.

**Bu sayının açık kalması bir erteleme değil, bir engeldir ve ikisi farklı.** K-039'un
düzeltmesi ertelenmişti — ölçülebilirdi, ölçülmemişti, ve K-044 onu ölçtü. Drift eşiği ise
**bugün ölçülemez**: ölçmek için promotion kapılarını geçmiş bir stratejinin gerçek `paper`
koşusu gerekiyor ve öyle bir strateji yok (K-044 bunu sayıyla da gösterdi — en iyi aday
şans beklentisinin altında). Bir sayı uydurmak yerine açık bırakmak, bu projede tercih
değil kural.

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

---

## K-047 — İptalde de aynı ilke: maruziyetin var olduğunu varsay

**Durum:** kabul · **Tarih:** 2026-09-11 · **Faz:** 7'ye dönüş (Faz 8 hazırlığı) ·
**Kapatır:** Faz 7 §7'nin "limit emri ve iptal ölçülmedi" maddesi · **İlgili:** K-007,
K-040, K-041, K-046 · **Kanıt:** `tests/unit/test_limit_iptal.py`,
`runs/testnet/lim-1.json`

**Bağlam.** Faz 7 market emriyle çalıştı ve iptal yolunu açık bıraktı: *"`CANCELED` yolu
state machine'de tanımlı ama gerçek borsaya karşı hiç yürütülmedi."* Tanımlı ama hiç
yürütülmemiş bir yol, **çalıştığı sanılan** bir yoldur — ve bu projede en pahalı hata
sınıfı orada yaşar.

### 1. Asimetri değil, tek bir ilkenin iki yüzü

Gönderimde kayıt ağ çağrısından **önce** yazılıyor (K-040); iptalde yanıt doğrulandıktan
**sonra**. İlk bakışta çelişkili görünüyor. Değil:

| | Kayıt ne zaman | Belirsizlikte varsayılan |
| --- | --- | --- |
| Gönderim | Ağ çağrısından **önce** (`SUBMITTED`) | Emir **olmuş olabilir** |
| İptal | Yanıt doğrulandıktan **sonra** (`CANCELED`) | Emir **hâlâ duruyor olabilir** |

İkisi de aynı yöne yanılıyor: **maruziyet vardır.** Gönderimde erken yazmak, olmuş bir
emri kaçırmamak için; iptalde geç yazmak, duran bir emri kapanmış saymamak için.

Tersi — doğrulanmamış bir iptali `CANCELED` yazmak — duran bir maruziyeti kapanmış
gösterir. Sistem "pozisyonum yok" sanıp yeni emir gönderir ve maruziyet **ikiye
katlanır**. Yanlış tarafa yanılmanın bedeli, bu projede geri alınamaz olan taraftadır.

Bunun doğrudan sonucu: `BelirsizSonuc` alan bir iptal defteri **hiç değiştirmiyor**.
Emir `ACKNOWLEDGED` kalıyor ve çıkış yolu mutabakat — `UNKNOWN`dan çıkışın tek yolunun
sorgulama olmasıyla aynı disiplin.

### 2. "İptal edilecek emir yok" bir başarısızlık değil

Borsa `-2011` döndürdüğünde ortada iptal edilecek bir şey yoktur: emir bu arada dolmuş,
süresi geçmiş ya da zaten iptal edilmiştir. Bunu hata sayıp yeniden iptal denemek, hiçbir
şeyi çözmez. Doğru tepki **sorgulamak** ve gerçek durumu deftere yazmak.

Bu, iptal ile fill'in yarıştığı andır ve yarışı fill kazanmıştır. Ölçülmesi gereken şey
yarışın kendisi değil, **yarışı kaybeden iptalin ne yaptığı**.

### 3. Fiyat yuvarlaması yön bağımlı — miktarınkiyle aynı ilkeden (K-007)

| Yön | Yuvarlama | Sonuç |
| --- | --- | --- |
| BUY | **aşağı** | İstenenden yüksek fiyat teklif edilmez |
| SELL | **yukarı** | İstenenden düşük fiyata satılmaz |

Emir istenenden **saldırgan olamaz**. Bedeli dolmama ihtimali ve bu bilinçli: dolmayan
bir emir **görünür** — defterde durur, iptal edilebilir, raporda sayılır. Bir tick kötüye
yuvarlanmış bir fill ise **sessizdir**: emir dolar, kayıt temiz görünür, fark yalnızca
uzun vadeli maliyet hesabında ortaya çıkar. Gürültülü hata, sessiz hataya yeğdir.

Fiyat tick'e **deftere yazılmadan önce** uyduruluyor: borsaya giden fiyat ile defterdeki
fiyat aynı olmalı, yoksa *"hangi fiyattan emir verdim"* sorusunun iki cevabı olur.

### 4. Fiyat kimliğe girmiyor — ve bu bir güvenlik kararı

`istemci_kimligi` yalnızca onaylı niyetin içeriğinden türüyor. Tür (`MARKET`/`LIMIT`) ve
limit fiyatı **kimliğe katılmıyor**, yani aynı niyet bir kez market bir kez limit olarak
gönderilse ikincisi reddediliyor.

Alternatifi — fiyatı kimliğe katmak — yeniden fiyatlamayı mümkün kılardı: dolmayan bir
limit emrini iptal edip biraz daha yukarıdan tekrar koymak. Ve tam orada execution
katmanı **kendi başına maruziyet kararı üretmeye** başlardı: "market denedim olmadı,
limit de deneyeyim". Değişmez kural 3 bunu yasaklıyor. Bir niyet, bir emir; dolmayan bir
limit iptal edilir ve **yeni bir risk kararı** yeni bir niyet üretir.

`GTC` seçilmesi de bununla ilgili: `IOC`/`FOK` dolmama hâlinde emri kendiliğinden kapatır
ve iptal yolunu hiç sınamaz — oysa ölçülmesi gereken tam olarak o yol.

### 5. Ölçüm: gerçek testnet, dört vaka

`runs/testnet/lim-1` (fiyat 77.207,08):

| Vaka | Sonuç |
| --- | --- |
| `acik_limit` | `ACKNOWLEDGED` · limit 61.765,66 · **9,8825 USDT kilitlendi** · açık emir listesinde |
| `iptal` | `CANCELED` · kilit **0,0**'a çözüldü · açık emir listesinden çıktı |
| `marketable` | `FILLED` · limit 77.979,15 · gerçekleşen **77.218,01** (limitten iyi) |
| `nihai_iptal` | Dolmuş emir · **ağa hiç çıkılmadı** · durum `FILLED` kaldı |

Koşu sonunda pozisyon mutabakatı: BTC ve USDT farkı **tam sıfır**. Yani limit yolunun
bakiyeyi `serbest`/`kilitli` arasında gezdirmesi, `toplam` üzerinden yapılan mutabakatı
bozmuyor — K-046'nın `Varlik` kararının ilk gerçek sınavı ve geçti.

### 6. Bu değişiklik Faz 7'de ölçülemezdi

Faz 7'nin `bakiye()`si yalnızca `free` okuyordu ve o fazda bu hiç sorun çıkarmadı, çünkü
market emri para kilitlemez. Limit yolu açılınca aynı kod **her açık emirde koşuyu
durduracaktı** — haksız yere, çünkü kilitli para da hesabın parasıdır.

Kayda değer olan şu: bu, sessiz değil **gürültülü** bir kırılma olurdu. Faz 7'nin dersi
("bir sahte, gerçeğin reddettiğini kabul ediyorsa ona karşı yeşil olan test bir şey
kanıtlamaz") burada da geçerli, o yüzden `SahteBorsa` artık gerçek bir muhasebe tutuyor:
açık limit emri parayı `serbest`ten `kilitli`ye taşıyor, iptal geri alıyor, komisyon
alınan varlıktan kesiliyor.

### 7. Ölçülmeyen, kayıtlı

- **Kısmi dolum.** `PARTIALLY_FILLED → CANCELED` geçişi state machine'de tanımlı ve birim
  testi var, ama gerçek borsaya karşı yürütülmedi: testnet'te 10 USDT'lik bir emri kısmi
  doldurtmak güvenilir biçimde tetiklenemiyor. Faz 8'in emir büyüklükleri de küçük
  olacağı için orada da doğal olarak doğmayabilir.
- **Uzun süre açık kalan emir.** Ölçümdeki emir saniyeler içinde iptal edildi; günlerce
  açık kalan bir emrin davranışı (borsa tarafında süre aşımı, sunucu bakımı) ölçülmedi.

---

## K-048 — Vizyon v2: kapsam genişliyor, v1 çekirdeği duruyor

**Durum:** kabul · **Tarih:** 2026-09-12 · **Kaynak:** `docs/Proje-Fikri-v2.md` ·
**Denetim:** `docs/Denetim-v2.md` · **Tadil eder:** Final-Doküman "Kapsam (v1)" ·
**İlgili:** K-008, K-013, K-014, K-045

**Karar.** Projenin hedefi *"kripto spot, tek sembol araştırma ve execution platformu"*ndan
*"multi-asset autonomous trading research & execution platform"*a genişler. Genişleme
**kümülatiftir**: v1'in kararları, testleri ve değişmez kuralları yürürlükte kalır. Hiçbir
karar "eski sürüm" gerekçesiyle kaldırılmaz; değişen bir kararın yerine yenisi yazılır.

**Kapsama giren (aşamalı, roadmap sırasıyla):** çok enstrümanlı araştırma çekirdeği; yeni
bilgi kaynakları (cross-sectional, türev, makro, olay takvimi, haber); portföy kurma; rejim
motoru; yetkisi sınırlı ML/LLM (K-049); üretim sertleştirme; ikinci varlık sınıfı (K-053).

**Kapsama girmeyen, gerekçesiyle:**

| Dışarıda | Gerekçe |
| --- | --- |
| HFT, market making, alfa olarak mikro yapı | Doküman da ilk hedef saymıyor (§4); altyapı ve maliyet başka bir iş. Mikro yapı yalnızca execution kalitesi için |
| **Kaldıraç, kısa pozisyon, perpetual ile işlem** | K-008'in tüm gerekçesi *"spot'ta likidasyon yok, pozisyonu tutmak güvenli"*. Likidasyon varken tutmak güvenli değil. Perpetual **bilgi kaynağı** olarak kalır (K-042), işlem aracı olmaz — açılması likidasyon-bilinçli yeni bir kill switch kararı ister |
| Opsiyon | Vol yüzeyi verisi ücretli; risk modeli ayrı bir iş |
| Borsa İstanbul | Doküman da *"canlı erişim uygunluğu doğrulanınca"* diyor |
| Alternatif veri | Doküman da *"yalnızca kanıtlanırsa"* diyor |
| Başkasının parası, sinyal paylaşımı, ücretli erişim | K-014 — hukuki sınır, tartışmaya açık değil |

**Neden şimdi ve neden bu bir yeniden başlatma değil.** K-045 tek sembollü yönlü aramayı
kapatırken tek bir kapı bırakmıştı: *"ölçüyle gerekçelendirilmiş, belirgin biçimde farklı bir
bilgi kaynağı."* Yeni dokümanın getirdiği şey tam olarak bu — fiyat geçmişinin dışında dört
kaynak. Ama "belirgin biçimde farklı" iddiası program başına ölçülür, peşinen kabul edilmez
(K-051).

Denetim-v2'nin ölçtüğü şey de bunu destekliyor: dokümanın MVP tanımındaki 12 maddenin 9'u
zaten karşılanmış, üç alpha ailesi zaten test edilmiş ve üçü de kalmış. Yani değişen temel
değil, **kapsam**.

**Dokümanın Faz 0'ı (kavramların anlaşılması) alınmıyor:** K-018 o fazı kaldırdı ve zorunlu
sonucunu yazdı — hiçbir güvenlik kontrolü operatörün piyasa bilgisine dayanamaz. K-018
yürürlükte.

---

## K-049 — AI/ML yetki sınırları; LLM'in eğitim verisi bir look-ahead kaynağıdır

**Durum:** kabul · **Tarih:** 2026-09-12 · **Değiştirir:** K-013 · **İlgili:** K-002, K-009,
K-039, K-044, K-051 · **Kaynak:** Proje-Fikri-v2 §8, §11; Denetim-v2 A2, B5

**Karar — beş madde:**

1. **Yetki tablosu bağlayıcıdır.** Semantic AI (haber/olay/varlık çıkarımı) **yetkisizdir**,
   yapılandırılmış kanıt üretir. Predictive ML yalnızca doğrulama kapılarından sonra üretim
   yetkisi alır. Research AI (hipotez üretimi, kod iskeleti, deney analizi) **yetkisizdir**.
   LLM açıklaması yalnızca audit metnidir ve hiçbir karara girmez.
2. **ML bir strateji gibi kapılardan geçer ve ayrıcalığı yoktur.** Her model ailesi, özellik
   kümesi ve hiperparametre seçimi **birer çekiliştir** (K-039, K-051). "Model denedim,
   tutmadı, başkasını denedim" zinciri tam olarak K-039'un saydığı şeydir.
3. **Sıra değişmez:** önce ekonomik hipotez, sonra özellik, sonra model. Kural tabanlı aileler
   yeni bilgi kaynaklarında ölçülmeden ML programı açılmaz.
4. **LLM'in eğitim verisi geçmiş için gelecektir.** 2023 haberini okuyan 2026 modeli o
   haberden sonra ne olduğunu biliyor; bu sızıntı **veride değil ağırlıklarda** olduğu için
   K-002'nin look-ahead testi onu yakalayamaz — kodda tek satır kural çiğnenmez. Kural:
   - Geçmişe dönük LLM türetimi yalnızca modelin **eğitim kesim tarihinden sonraki** dönem
     için kanıt sayılır.
   - Kesim öncesi dönem için üretilmiş türetim `leak_riski` bayrağı taşır ve bu bayrak
     promotion'un **mutlak engelidir** (`dirty`, `data_quality_warning`,
     `gecici_maliyet_modeli` ile aynı sınıf).
   - Bu yüzden LLM kullanan bir program, kullanacağı modelin kesim tarihini **önceden**
     kaydeder; ölçülebilir pencere o tarihten sonrasıdır.
5. **LLM çıktısı bir hesaplama değil, bir veri kaynağıdır.** Backtest içinde canlı LLM
   çağrısı **yasak**: çıktı sürüme ve örneklemeye bağlı olduğu için K-009'un *"aynı girdi aynı
   çıktı"* kuralını sağlamaz. Çıktı bir kez üretilir; ham değişmez bölgeye model kimliği,
   prompt hash'i, girdi hash'i ve üretim zamanıyla yazılır; backtest **dondurulmuş dosyayı**
   okur ve veri seti hash'i o dosyanın SHA-256'sıdır.

**K-013 neden değişiyor.** K-013'ün gerekçesi *"ML overfitting yüzeyini büyütür; önce sağlam
bir araştırma disiplini"* idi ve doğruydu. O disiplin kuruldu **ve fiyatlandı**: K-044 her
çekilişin kapıyı yükselttiğini ölçtü. ML artık bedava bir deneme değil, sayacı büyüten ve
kendi duvarını yükselten bir program. K-013 kaldırılmıyor; **ödeme planına bağlanıyor.**

---

## K-050 — Otomasyon asimetriktir: riski azaltan otomatik, izni artıran kapı + onay

**Durum:** kabul · **Tarih:** 2026-09-12 · **İlgili:** K-008, K-010, K-018, K-037, K-046 ·
**Kaynak:** Proje-Fikri-v2 §1 ile §3/§21'in gerilimi; Denetim-v2 A1, B6

**Karar:**

1. **Riski azaltan her eylem otomatik olabilir ve olmalıdır:** sinyali reddetmek, SAFE_MODE'a
   geçmek, maruziyeti küçültmek, koşuyu durdurmak, uyuşmazlıkta halt etmek.
2. **İzni artıran hiçbir eylem otomatik olamaz:** canlıya alma, sermaye artırma, limit
   gevşetme, yeni enstrüman/venue açma, kapı eşiği değiştirme. Sırası değişmez: **sayısal
   kapı → elle onay.** K-010'un son adımı yerinde kalır.
3. **Kademeli sermaye sayısal bir kuraldır**, insan yargısı değil (K-018). Biçimi şimdi
   sabitleniyor, sayıları Faz 8'in ilk koşusunda kalibre edilecek. Bir kademe şunları ister:
   (a) asgari kesintisiz canlı gün, (b) o kademede ölçülmüş `|paper − live|` drift üst sınırı,
   (c) açıklanamayan pozisyon farkı **sıfır** (K-046), (d) elle onay. Kademe atlanamaz.
   İhlalde sermaye bir kademe **otomatik iner** — 1. madde gereği, çünkü inmek riski azaltır.

**"Autonomous" sözcüğünün anlamı burada sabitleniyor:** operasyon otonomdur, **yetki
değildir.** Bu yeni bir ilke değil; K-037'nin *"engelleyen katman risk motorunun dışında
olabilir, izin veren olamaz"* kuralının yetki düzeyine taşınmış hâli.

---

## K-051 — Defter tektir; her araştırma programı ön kayıtlı arama bütçesiyle açılır

**Durum:** kabul · **Tarih:** 2026-09-12 · **Tamamlar:** K-039, K-042, K-044, K-045 ·
**Kaynak:** Denetim-v2 A3, B4

**Sorun.** v2 dört yeni bilgi kaynağı ve "continuous research" istiyor. K-044 ise ölçtü: 31
çekilişte %5'lik `oos_sharpe` sınırı 1,02 — ve **her yeni çekiliş bu sınırı yükseltiyor.**
Bir araştırma programı, bulduğu şeyi geçiremeyeceği bir duvarı kendisi örebilir ve bunu
ancak sonunda öğrenir.

**Karar:**

1. **Defter tek ve globaldir.** Varlık sınıfı, veri kaynağı veya program başına ikinci bir
   defter açılmaz. Gerekçe basit: seçim en sonunda hepsinin arasından yapılıyor. Defteri
   bölmek, seçimi yapan kişi için sayacı sıfırlamaktır.
2. **Program kaydı ön koşuldur.** Bir araştırma programı açılırken deftere yazılır: gerekçe;
   bilgi kaynağının **neden belirgin biçimde farklı olduğu** (K-045'in istisna şartı, iddiayla
   değil ölçüyle); planlanan **azami çekiliş sayısı** (arama bütçesi); ve durma kuralı (K-042
   kalıbı). Bütçe aşılamaz — aşmak yeni bir program kaydı ve yeni bir gerekçe ister.
3. **Duvar önceden tahmin edilir.** Program başlamadan, bütçe dahil edildiğinde eşiğin nereye
   çıkacağının mertebe tahmini (DSR / Bonferroni) kaydedilir. Bu tahmin **kapı değildir**;
   kapı bitiminde `sq lab coklu-test` ile ölçülür (K-044). Amacı, programın kendi dikeceği
   duvarı baştan görmesi.
4. **Hipotez kimliği genişler.** K-039'un beşlisine üç alan ekleniyor: **evren tanımı**,
   **portföy kurma yöntemi**, **rejim tanımı**. Üçü de "aynı veriye yeni bir soru sormanın"
   biçimleri; kimliğin dışında kalırlarsa bedava çekiliş olurlar — Faz 4'e dönüş 2'de seçim
   yöntemi için yaşanan düzeltmenin aynısı.

**Bu karar büyümeyi yasaklamıyor; fiyatını önceden görünür kılıyor.**

---

## K-052 — Tek kod yolu çok enstrümana genişler; monolit korunur; servisler ölçüme bağlı

**Durum:** kabul · **Tarih:** 2026-09-12 · **Tamamlar:** K-001, K-002, K-003, K-005, K-007,
K-011, K-027, K-032, K-034, K-037 · **Kaynak:** Proje-Fikri-v2 §6, §7.2, §9, §18, §19, §29;
Denetim-v2 A4-A7, B1-B3; Spike 6

**Karar — altı madde:**

1. **Modüler monolit korunur.** Dokümanın §29 servis düzeni alınmıyor. Bu projenin güvenlik
   garantileri **import sınırlarında statik olarak kanıtlanıyor** (K-003 izolasyon, K-027 izin
   listesi, K-032 kesme noktası). Servislere bölmek bu kanıtı ağ protokolüne taşır ve
   kanıtlanabilir olmaktan çıkarır. §19'un bileşen tablosu mevcut paketlere eşleniyor (tablo:
   Final-Doküman).
2. **Çok enstrümanlı motor ikinci bir motor değildir** (K-001). Tek enstrüman onun **özel
   hâlidir**; Faz 3'ün bağımsız referans testleri o özel hâlde **bit düzeyinde** aynı sonucu
   vermek zorundadır. Aksi hâlde `backtest = paper = live` iddiası ikiye bölünür ve K-001'in
   bütün gerekçesi düşer.
3. **Evren üyeliği point-in-time bir zaman serisidir.** `ctx` t anında yalnızca o an
   listelenmiş ve evren kuralını **yalnızca t'ye kadarki veriyle** sağlayan enstrümanları
   gösterir. Bugünkü listeden kurulan bir evren, Spike 6'nın ölçtüğü gibi her ayın likit
   isimlerinin medyan %18'ini — sonradan başarısız olanları — atar. Evren seçimi stratejinin
   içinde yapılamaz (K-003); `ctx`e hazır gelir.
4. **Enstrüman kimliği ticker değildir.** Kanonik kimlik geçerlilik aralığı taşır. Uzun bir
   boşluk + imkânsız bir fiyat oranı **kimlik kırılması şüphesi** olarak işaretlenir. Ölçülmüş
   vaka: `LUNAUSDT` 73 ay kesintisiz görünüyor, ama 2022-05-13 kapanışı 0,00005 ve 17 gün
   sonraki açılış 1,00 — aynı ticker altında iki farklı varlık, 20.000 katlık sahte bir getiri
   (Spike 6 §4a).
5. **PIT gözlem modeli.** Bar olmayan her gözlem `event_time`, `available_time`,
   `ingested_time`, `effective_from/to` ve revizyon geçmişi taşır. **`ctx` `available_time`e
   göre keser** — `event_time`e göre kesmek, açıklanmamış veriyi kullanmaktır. Available_time
   yalnızca gün çözünürlüğünde biliniyorsa **gün sonuna** (UTC 23:59:59.999) yuvarlanır:
   K-007'nin *"belirsizlikte aleyhte"* ilkesinin zaman eksenindeki karşılığı.
6. **Servisler koşulludur.** PostgreSQL, Redis, object storage, message bus, Docker: K-034'ün
   kalıbı geçerli. Çok sembollü çalışma K-034'ün 3. koşulunu **gerçekleştiriyor** — ama bir
   koşulun gerçekleşmesi kararın *yeniden verilmesi* demektir, otomatik kabul değil. Ölçüm Faz
   9'da, gerçek yazma deseni belli olduğunda yapılır. K-011'in dosya düzeni Spike 6'da ölçüldü
   ve **değişmiyor**: toplam ≈0,86 GB, en büyük dosya 2 MB (eşik 500 MB).

**Rejim motorunun bağlayıcı kısıtları** (tasarımı Faz 12, kuralı bugün):

- Yalnızca **filtrelenmiş** (t'ye kadarki veriyle hesaplanan) olasılık kullanılır.
  Yumuşatılmış (smoothed) rejim etiketi tüm serinin ışığında üretilir ve backtest'i kusursuz
  gösterir — bu bir look-ahead'dir.
- Rejim modeli walk-forward'ın her katmanında **yalnızca eğitim penceresinde** kurulur.
- Rejim **engelleyici** olabilir ("stres rejiminde yeni giriş yok"), **izin verici** olamaz
  (K-037).
- Rejim tanımı bir çekiliştir (K-051/4).

---

## K-053 — İlk genişleme kripto içinde; ikinci varlık sınıfı ölçülmeden açılmaz

**Durum:** kabul · **Tarih:** 2026-09-12 · **Kaynak:** Spike 6
(`docs/spikes/06-coklu-sembol-evren.md`) · **İlgili:** K-015, K-042, K-048

**Karar.** v2'nin ilk araştırma programları **Binance kripto** üzerinde kurulur: çoklu sembol
(cross-sectional), türev (evren geneli funding/basis), makro (ücretsiz PIT kaynakları).
İkinci varlık sınıfı (US equities/ETF; broker olarak Alpaca veya IBKR) **kendi spike'ından
sonra** açılır — ölçülecekler: Türkiye yerleşiğinin hesap uygunluğu, veri lisansının kapsamı
ve maliyeti, PIT corporate action verisi, gerçek komisyon tarifesi.

**Gerekçe dokümanın kendi ölçütü.** §5 diyor ki: ilk piyasa *"en kolay olduğu için değil,
araştırma/uygulama maliyetleri ve veri kalitesi proje sermayesine uygun olduğu için"*
seçilmeli. Kriptoda bu ölçüldü:

- Veri maliyeti **sıfır** ve kapsam ölçüldü: 659 aday sembol, hayatta kalma yanlılığı olmadan,
  ≈0,86 GB, ≈8 dakikada indirilebilir (Spike 6).
- Altyapının tamamı bu venue'ye karşı çalışıyor ve ölçüldü: indirici, doğrulama, backtest,
  risk motoru, execution, mutabakat, testnet'te 100/100 emir.
- US equities tarafında ücretsiz veri planı IEX ile sınırlı (doküman §27), hesap uygunluğu ve
  lisans kapsamı **doğrulanmadı** (Denetim-v2 D3).

**Bu bir "kripto daha iyi piyasa" kararı değil, bir sıra kararı:** ölçülmüş yoldan başlanıyor,
ölçülmemiş olan spike'a bırakılıyor. Dokümanın §5 tablosu US equities'i "birincil aday"
diyor ve sıra tersine çevrilebilir — ama ancak spike'ın sayıları geldikten sonra, araştırma
sonuçları görüldükten sonra değil.

---

## K-054 — Doğrulama kapıları v2: dört yeni kapı, eşikleri açık

**Durum:** kabul (eşikler **açık**) · **Tarih:** 2026-09-12 · **Tamamlar:** K-019, K-044 ·
**Kaynak:** Proje-Fikri-v2 §15.1, §16; Denetim-v2 §0.2

**Karar.** K-019'un yedi kapısı yürürlükte ve **gevşetilmiyor**. Dokümanın 12 kapılık
listesiyle karşılaştırıldığında dördü eksik; ekleniyor. Eşikleri **açık** ve ilgili ölçüm
yapılmadan sayı yazılmıyor — K-019'un kendi kalıbı (*"eşikler Faz 4 sonunda gerçek veriyle
kalibre edilir"*).

| Yeni kapı | Ne ölçer | Nerede kalibre edilir |
| --- | --- | --- |
| `rejim_kararliligi` | Performansın rejimler arası dağılımı; tek bir boğa/ayı dönemine bağımlılık | Faz 11 (rejim tanımı Faz 12) |
| `evren_dayanikliligi` | Sonuç kaç enstrümana bağlı; en iyi k enstrüman çıkarıldığında geriye ne kalıyor | Faz 11 |
| `parametre_perturbasyonu` | Komşu parametrede performans çöküyor mu (§15.1/6). Mevcut `parametre_kararliligi` **başka bir şey** ölçüyor: katmanlar arası seçim değişkenliği | Faz 11 |
| `pbo` | Backtest overfitting olasılığı (CSCV) | Faz 11 |

**Mutlak engel listesine `leak_riski` ekleniyor** (K-049/4): eğitim kesimi öncesi dönem için
üretilmiş LLM türetimi taşıyan hiçbir sonuç kapıdan geçemez.

**Raporlanan ama kapı olmayan metrikler genişliyor** (§16): VaR/CVaR, kapasite (ADV oranı),
olasılık kalibrasyonu, Deflated Sharpe. Kapı olmamalarının sebebi K-019'unkiyle aynı: eşiği
ölçülmemiş bir sayı kapı değildir.

**"Ölçülemeyen kapı geçilmiş sayılmaz"** yeni kapılar için de geçerli ve bir sonucu var:
`evren_dayanikliligi` tek bir sembolde **ölçülemez** — aynı kuralların evrenin geri kalanına
uygulanmasıyla ölçülür. Yani tek sembolde geliştirilen bir strateji de artık evrene karşı
sınanmak zorunda. Bu bilinçli: K-045 tek sembollü yönlü aramayı zaten kapatmıştı.

---

## K-055 — Faz 6 kapanır; 30 günlük kesintisizlik sürekli açık bir host ister ve oraya taşınır

**Durum:** kabul · **Tarih:** 2026-09-15 · **Faz:** 6 · **Tamamlar:** K-035, K-043 ·
**İlgili:** K-010, K-018, K-038 · **Kaynak:** Scryne'ın kararı; `runs/paper/gozlem-2.sqlite`

**Bağlam.** Faz 6'nın dört bitti kriterinden üçü 2026-09-11'de testle karşılanmıştı;
dördüncüsü *"30 gün kesintisiz çalışma"* `gozlem-2` koşusuna bağlıydı. Scryne kriteri
gereksiz buldu ve bir olgu bildirdi: **bilgisayar iş bitince kapatılıyor.** Koşunun kaydı bunu
doğruluyor.

| Ölçüm (`gozlem-2`, 2026-09-11 12:21 → 2026-09-15 19:24 UTC) | Değer |
| --- | --- |
| Çalışma | 4,29 gün |
| Kesinti | 5 = 4 `temiz_kapanmadi` (sebep "bilinmiyor"; makinenin kapatılmasıyla uyumlu) + 1 `kopma` |
| Gerçek WebSocket kopması | 1, 18 s'de `yeniden_baglandi`, resync 0 bar |
| Toparlanma | 4 başarılı (`toparlandi`), ayrışma 0 |
| Fill | 0 |
| Kapanış | `sq paper durdur` → `durdu` (kesinti sayılmadı); zamanlanmış görev kaldırıldı |

**Karar — dört madde:**

1. **Faz 6 kapanır; 30 günlük kriter gevşetilmez, taşınır.** Bu makinede kriter altyapının
   beklenmedik şekilde düşüp düşmediğini değil, bir masaüstünün 30 gün açık kalıp
   kalmadığını ölçüyor. K-043 aynı ayrımı planlı yeniden başlatma için yapmıştı; buradaki
   fark, günlük kapanışın bir bayrakla "planlı" sayılması **da** yanlış olurdu: canlı bir
   koşu o saatlerde gerçekten kapalıdır. Doğru cevap kriteri düzeltmek değil, onu ölçülebilir
   olduğu yere taşımak.
2. **Promotion kapısı değişmiyor.** `risk/promotion.py::ASGARI_PAPER_GUN = 30` yerinde. Faz
   6'nın gözlem koşusu K-035 gereği zaten promotion kanıtı **olamazdı**; promotion'un `paper`
   aşamasının 30 günü, kapıları geçen ilk stratejinin gerçek paper koşusunda ölçülür.
3. **Borç iki yere bağlanır.** (a) **Faz 8 ön koşulu 5:** sürekli açık bir host ve üzerinde
   30 gün kesintisiz koşu; açık pozisyonla gerçek bir toparlanma en az bir kez görülmüş.
   (b) **Faz 14 bitti kriteri:** uzun süreli dayanıklılık (Faz 7'nin açık kalemiyle
   birleşir).
4. **Ne kaybedildi, açıkça:** toparlanmanın **açık pozisyonla** canlıda sınanması (0 fill;
   yol yalnızca `tests/unit/test_toparlanma.py`'de kanıtlı); günlerce süren bağlantının
   yaşlanması; uzun koşuda bellek/dosya büyümesi. Üçü de Faz 8'den önce ölçülmek zorunda ve
   yukarıdaki iki madde bunu zorluyor.

**Faz sırası:** Faz 9 bu karardan bağımsızdır (strateji ve canlı koşu içermez), bekleme yok.

---

## K-056 — Arşiv ikinci veri kaynağıdır ve karıştırılmaz; kimlik ölçüyle bölünür; evren PIT'tir

**Durum:** kabul · **Tarih:** 2026-09-16 · **Faz:** 9 · **Uygular:** K-052/3, K-052/4,
K-052/5, K-051/4 · **İlgili:** K-005, K-006, K-009, K-011, K-024, K-039 ·
**Kanıt:** `docs/Faz-9-Veri-Platformu-Raporu.md`

**Bağlam.** Çoklu sembol evreni REST'ten kurulamaz: delist edilmiş sembollerin geçmişi orada
yok, arşivde var (Spike 6). Arşiv kullanılınca dört şey ölçüldü ve dördü de karar gerektirdi.

**Karar — altı madde:**

1. **Arşiv (`data.binance.vision`) ikinci bir veri kaynağıdır ve REST ile karıştırılmaz.**
   Evren `data/evren/` altında yaşar, `data/market/` REST'ten kalır. İki sebep: (a) REST
   dosyalarının hash'i hipotez defterindeki 38 çekilişin `veri_sha256`sı (K-039); (b) iki
   kaynak birebir aynı değil — BTCUSDT 1h'in ortak 45.576 barının **4'ünde** hacim, işlem
   sayısı veya kapanış farklı. Hangisinin doğru olduğu bilinmiyor ve **tahmin edilmiyor**;
   bir seri tek kaynaktan kurulur.
2. **Arşiv dosyası doğrulanmadan kabul edilmez.** Her zip'in `.CHECKSUM` dosyasıyla SHA-256'sı
   karşılaştırılır; checksum'ı olmayan veya tutmayan dosya reddedilir ve o sembol için hiçbir
   şey yazılmaz. İndirilen her dosyanın adı ve hash'i parquet'in yanındaki manifestoda durur:
   "kaldığı yerden devam"ın ölçüsü bar değil, **dosya**.
3. **İki ayrıştırma kuralı sabitlenir.** (a) `open_time` birimi 2025-01'de ms'den µs'e geçti;
   birim büyüklükten çıkarılır, dosya içinde karışık birim ve 1000'e bölünmeyen µs
   **reddedilir**. (b) CSV `float_precision="round_trip"` ile okunur: varsayılan ayrıştırıcı
   744 satırlık bir ayda 50 değeri 2,4e-7 kaydırıyordu ve veri seti kimliği dosyanın
   hash'idir (K-009).
4. **Izgaraya oturmayan bar atılır, yuvarlanmaz, ve sayılır.** 2018-02 kesintisinden sonra 6
   sembolde toplam 258 bar 28 dk kaymış açılışla yazılmış. Yuvarlamak, 09:28–10:28 barını
   09:00–10:00 barı gibi göstermek olurdu (K-024). Doğrulama katmanının K-005 kuralı
   gevşetilmiyor; ayıklama arşiv katmanında yapılır, atılan sayı manifestoda ve raporda.
5. **Kimlik kırılması eşikleri ölçüldü** (K-052/4'ün "uzun boşluk + imkânsız oran" kuralına
   sayı): `eksik_bar >= 12` **ve** `|ln(sonraki açılış / önceki kapanış)| >= ln 10`. 3.598
   boşluğun dağılımında 0,99–2,30 arası **boş**; üstündeki 28 vakanın tamamı bilinen kimlik
   değişimi (LUNA, VEN→VET, 1:1000/1:100/1:10 redenominasyonlar, kaldıraçlı token ters
   bölünmeleri), altındaki en yakın vakalar 2021-05-19 çöküşündeki gerçek fiyat hareketi.
   Kanonik kimlik `binance-spot:<ticker>@<segmentin ilk barının UTC tarihi>`. **Şüphede
   bölünür:** yanlış pozitif bilgi kaybettirir, yanlış negatif olmayan bir getiriyi seriye
   gömer. Eşikler 1h için ölçüldü; başka timeframe'de yeniden ölçülür.
6. **Evren tablosu PIT'tir ve evren kuralı bir çekiliştir.** M ayının üyeliği yalnızca M−1'in
   tamamlanmış verisiyle kurulur; hacim kendi barlarımızdan (arşivin `1mo` özet katmanından
   değil — o katman 2026-03'ten beri eksik) ve `suspect` barlar hariç hesaplanır; enstrüman
   M−1'in son gününde işlem görüyor olmalıdır. Kuralın her alanı `EvrenKurali.kimlik`
   hash'ine girer ve hipotez kimliğinin `evren` alanıdır (K-051/4).

**Ölçülen yanlılık, ikinci kez ve bağımsız yoldan:** N=50, hacim ≥ 30 M USDT kuralıyla kurulan
evrende bir ayın üyelerinin **medyan %16,7'si** (en kötü ay %33,3) bugün kapanmış. Spike 6
aynı büyüklüğü %18 / %34 ölçmüştü. Bugünkü listeden kurulan bir evren bu isimleri atardı.

**Açık kalem:** üç veri kaynağının da lisans alanı **"doğrulanmadı"**. Binance kullanım
koşulları okunup kaynaklı kaydedilmedi; tahmin yazılmadı. Faz 9'u bloke etmiyor, ikinci
varlık sınıfı (K-053, Faz 15) için bloke edici hâle gelir.

---

## K-057 — Çok enstrümanlı motor tek motordur; portföy kurma öneri, risk onaydır

**Durum:** kabul · **Tarih:** 2026-09-16 · **Uygular:** K-001, K-052/2, K-052/3, K-037,
K-030 · **Tamamlar:** K-009, K-019, K-054 · **Kaynak:** Faz 10,
`docs/Faz-10-Coklu-Enstruman-Raporu.md`

### Karar — yedi madde

1. **Tek motor var, sarmalayıcısı var.** `backtest/motor.py` kendi event loop'unu
   **taşımıyor**: tek sembollü koşu, tek elemanlı bir evren + `TekEnstruman` sarmalayıcısıyla
   `backtest/coklu_motor.py`ye gidiyor. K-052/2 *"çok enstrümanlı motor ikinci bir motor
   değildir"* diyor; iki motorun "aynı sonucu verdiğini" test etmek bu cümlenin zayıf
   hâlidir — iki motor bir gün ayrışabilir, tek kod yolu ayrışamaz. Ayrışmayı
   `test_coklu_motor.py::test_tek_motor_kalmadi` statik olarak engelliyor.

2. **Hedef portföy, ağırlık sözlüğü değil `Sinyal` demetidir.** `HedefPortfoy` sembole göre
   sıralı, sembolleri benzersiz, tek bir barın zamanını taşıyan bir `Sinyal` demetidir.
   Ağırlık sözlüğü seçilseydi `side`, `confidence` ve `reason` kaybolur ve *"azaltan niyete
   engel konmaz"* (K-008/3) kuralı çok enstrümanlı yolda **uygulanamaz** hâle gelirdi: hangi
   hedefin bir çıkış olduğu ancak mevcut pozisyona bakılarak tahmin edilebilirdi. Sıralama
   zorunlu, çünkü emir sırası kayan nokta toplamını etkiliyor (K-009).
   **Bahsedilmeyen sembol "kapat" demek değildir** — `Sinyal` sözleşmesindeki kuralın portföy
   hâli.

3. **Portföy düzeyi risk yalnızca aşağı çeker (K-037).** İki yeni limit: `azami_brut_maruziyet`
   ve `azami_enstruman`. Sıra sabit: önce sinyal düzeyindeki 0-8 adımı, **sonra** portföy
   tavanları. Ters sırada, sinyal düzeyinde reddedilecek bir hedef brüt bütçeden yer kapar ve
   geçecek bir hedefi sessizce kısardı. Tavanlar azaltan niyetlere uygulanmaz ve mevcut
   maruziyetin **altına zorlamaz**: bir tavanın satış emri üretmesi, stratejinin istemediği
   bir çıkışı risk motorunun yazması olurdu. İkinci bir mühür yok — onay hâlâ `OnayliNiyet`
   düzeyinde ve sembol başına; `PortfoyKarari` yalnızca onları bir arada taşıyor.

4. **Portföy kurma `strategy/` altındadır ve bir öneridir.** Saf hesap olduğu için K-003'ün
   izolasyon testinin kapsamında; `portfolio/` altında olsaydı o testi genişletmek ya da
   kapsam dışı bırakmak gerekirdi. Ürettiği ağırlıklar bir onay **değildir**; kurmadaki bir
   sayıyı gevşetmek canlıda hiçbir kapıyı açmaz. Yöntemin her ayarı `KurmaAyarlari.sozluk()`e,
   oradan hipotez kimliğine girer — yöntem bir çekiliştir (K-051/4).
   §12'nin *cost-aware turnover penalty*'si **bant** olarak uygulanıyor, ceza katsayısı olarak
   değil: bandın birimi ağırlık ve sayısı doğrudan maliyet modelinden türetilebilir, ceza
   katsayısı ise stratejiden stratejiye değişen skor ölçeğine bağlı olurdu.

5. **Barı olmayan enstrüman: ne karar, ne fill, ne tahmin.** Bir sembolün `t`de barı yoksa o
   sembolde karar verilmez ve doldurulmaz (K-028'in uzantısı). Açık bir pozisyon bu sebeple
   kapatılamıyorsa **son bilinen fiyattan** değerlenir ve `bayat_degerleme` sayacı artar.
   Sıfıra yazmak olmayan bir zararı, portföyden atmak olmayan bir kârı gerçekleştirmek olurdu.
   Ölçüldü: 2025-01…2026-08 penceresinde (205 sembol) bu durum **hiç** oluşmadı; sayacın
   kendisi Faz 12'nin ölçeceği şey.

6. **`sonuc_hash` sıfır atlama sayaçlarına karşı dayanıklı hâle getirildi.** `atlama_sayimi`
   kaydın okunabilirliği için sıfır sayaçları da yazıyor, ama o liste `AtlamaSebebi` enum'unun
   **bugünkü** hâlinden türüyordu: yeni bir atlama sebebi eklemek, o sebebi hiç üretmemiş eski
   koşuların hash'ini de değiştiriyordu. **Ölçüldü ve zaten olmuş:** Faz 4'ün tarama kayıtları,
   Faz 5/6'da eklenen `risk_reddetti` ve `veri_bayat` yüzünden Faz 10'dan **önce** yeniden
   üretilemez hâldeydi — üstelik her ekonomik değer (getiri, Sharpe, işlem sayısı, drawdown,
   profit factor) birebir aynıyken. Bundan sonra hash'e yalnızca sıfır olmayan sayaçlar giriyor.
   Aynı gerekçeyle `Sonuc.evren` ve `Islem.sembol` yalnızca çok enstrümanlı koşuda yazılıyor:
   tek sembollü bir koşuda sembol zaten `veri.sembol`de ve evren diye bir şey yok.

7. **Evren kıyası bir kıyastır, aile değil (K-030).** Tek sembolde kıyas `al_tut`; evrende
   *"o ay listelenmiş likit isimleri, hiçbir seçim yapmadan taşısaydım ne olurdu"*. Hipotez
   defterine çekiliş olarak **girmez** ve K-045'in "yeni çekiliş yok" kuralının kapsamında
   değildir — Faz 4'ün `al_tut`u da değildi. Sıralaması evren kuralının kendi ölçütüyle aynı
   büyüklükten (30 günlük ortalama kote hacim) geliyor; skoru sabit bırakmak, tavan
   bağladığında kıyası evrenin **alfabetik** ilk N'ini taşıyan keyfi bir alt kümeye çevirirdi.
   Ölçüldü: 205 sembollü pencerede tavan gerçekten bağlıyor ve kapasite oranı alfabetik
   seçimde 0,167%, hacim sıralamasında 0,0038% — 44 kat fark.

### Gerekçe: neden sarmalayıcı, neden "bit düzeyinde"

K-052/2 kriteri şuydu: *"Faz 3'ün bağımsız referans fixture'ı yeni motorda bit düzeyinde aynı
sonucu veriyor — bu kriter düşerse K-001 düşer."* Eşitliğin **nereden** geldiği önemli:

- Boyutlandırma tek fonksiyondan (`fill.emir_hazirla_genel`); tek ve çok sembollü yollar onu
  çağırıyor.
- Defter aritmetiği tek yerden (`portfolio.durum.Pozisyon.al/sat`); `Portfoy` ve `CokluPortfoy`
  aynı iki metodu çağırıyor.
- Tur muhasebesi tek kalıpta (`backtest.defter`), sembol başına.
- Portföy düzeyi tavanları varsayılan değerlerinde (1,0 ve 1000) tek sembollü koşuda bağlamaz.

Yani aynı sayılar aynı sırada toplanıyor. Doğrulandı: Faz 3'ün 12 turluk ve kısmi maruziyetli
iki senaryosu, tek elemanlı bir evrende Decimal referansla 1e-12 bağıl tolerans içinde aynı; ve
gerçek 5,2 yıllık veride 12 noktalık bir parametre taramasının **bütün** ekonomik değerleri
değişmedi.

### Kapsam dışı bırakılanlar ve sebepleri

- **Tam risk paritesi / optimizasyon.** Ağırlık `w_i ∝ 1/σ_i`; korelasyon **budama**
  aşamasında ele alınıyor, ağırlıkta değil. Optimizasyon aynı veriye daha çok soru sormaktır
  ve ayrı bir çekiliş olarak kaydedilmelidir.
- **Bağlayıcı portföy limit sayıları.** `azami_brut_maruziyet = 1,0` ve
  `azami_enstruman = 1000` bugün **bağlamıyor** ve bağlamaması bilinçli: Faz 10 yöntemi
  *kurar*, iştahı ölçmez. Sayılar Faz 12'de, turnover ve kapasitenin gerçek maliyeti
  ölçüldüğünde yazılır. Bugünden bir sayı yazmak, ölçülmemiş bir kapı olurdu (K-019).
- **VaR/CVaR ve kapasite kapı değil.** K-054'ün kalıbı: raporlanır, eşiği ölçülmediği için
  kapı değildir.
- **Evren `ctx`inde sıra bilgisi yok.** Strateji sıralamayı kendi ölçüsüyle yapar; evren
  tablosunun `sira` sütununu `ctx`e koymak, kuralın seçim ölçütünü stratejiye ücretsiz bir
  sinyal olarak vermek olurdu.

### Geri dönüş koşulları

Bu karar şu üç durumda yeniden açılır:

1. **Bellek.** Ölçüldü: 323 sembol × 32.857 bar = 945 MB dizi (2023-01…2026-08). Bir pencere
   4 GB'ı aşarsa ortak ızgara yerine akış (chunked) kurulumu ölçülür — bugün gereksiz.
2. **`bayat_degerleme` sıfırdan büyük çıkarsa**, delist edilmiş pozisyonun değerlemesi bir
   iştah kararına dönüşür ve K-033'ün gerekçe disiplinine girer.
3. **Portföy tavanlarından biri gerçekten bağlarsa**, o sayı iştah olmaktan çıkıp ölçülmüş
   olmak zorunda kalır.

---

## K-058 — Doğrulama v2: dört kapının eşiği null'dan, program kaydı zorunlu, `leak_riski` mutlak

**Durum:** kabul · **Tarih:** 2026-09-16 · **Kapatır:** K-054'ün açık eşikleri ·
**Uygular:** K-051/2-4, K-049/4 · **Tamamlar:** K-019, K-044 · **Kaynak:** Faz 11,
`docs/Faz-11-Dogrulama-Raporu.md`, ham ölçümler `runs/kalibrasyon-v2/`

### Karar — altı madde

1. **Üç kapının eşiği edge'siz dünyadan ölçülür (K-044'ün yöntemi).** `pbo`,
   `parametre_perturbasyonu` ve `rejim_kararliligi` için ızgaranın her noktasının sinyal
   takvimi bir kez çıkarılıp **paylaşılan** dairesel kaydırmayla edge'siz bir dünyada
   yeniden koşuldu; eşik o dağılımın %5 kuyruğu. İki ızgarada ölçüldü (`donchian` 12
   nokta / 200 iterasyon, `rsi_donus` 32 nokta / 100 iterasyon) ve **sıkı olanı**
   alındı: eşik ızgara şekline bağlı çıktı ve bir aday ızgarasını seçerek gevşek eşiğe
   kaçamamalı (K-007).

   | Kapı | Yön | donchian | rsi_donus | Eşik |
   | --- | --- | ---: | ---: | ---: |
   | `pbo` | ≤ | 0,0087 | 0,0462 | **0,0087** |
   | `parametre_perturbasyonu` | ≤ | 0,0752 | 0,0565 | **0,0565** |
   | `rejim_kararliligi` | ≥ | 0,481 | 0,685 | **0,685** |

2. **`evren_dayanikliligi` null'dan kalibre edilemez ve yapısal olarak kalibre edilir.**
   Null edge'i yok eder; bu kapı yoğunlaşmayı ölçer. Evren kıyası 2023-01…2026-08'de 3-20
   enstrümanla koşuldu; en iyi katkı çıkarıldığında Sharpe oranı **0,832-1,023** bandında
   kaldı. Eşik **0,75** — bandın altında, bir **iştah** seçimi ve öyle işaretli. Kapı mutlak
   düşüşü değil **oranı** okur: ilk tasarımda mutlak düşüş vardı ve kalibrasyon onun Sharpe
   büyüklüğüyle ölçeklendiğini gösterdi. Oran `Sharpe ≤ 0` iken ve tek sembolde
   **ölçülemez**; ölçülemeyen kapı geçilmiş sayılmaz.

3. **PBO'nun literatür referansı (0,5) bu projede eşik olamaz — ölçüldü.** İid gürültüde
   ortalama gerçekten 0,503 (40 tohum), ama tek ölçüm ±0,20 sapıyor (aralık 0,08-0,90).
   Gerçek ızgarada null'ın **medyanı 0,237** (donchian): komşu parametreler neredeyse aynı
   strateji olduğu için IS-en iyisi edge olmadan da OOS'ta iyi kalıyor. 0,5 eşiği
   edge'siz ızgaraların %90'ından fazlasını geçirirdi.

4. **Program kaydı olmadan hipotez yazılamaz (K-051/2).** `sq lab hipotez-kaydet` artık
   `--program` ister; program `docs/Arastirma-Programlari.jsonl`de açık ve bütçesi dolmamış
   olmalı. Kayıt gerekçe, **ölçüyle** kaynak farkı, azami çekiliş, durma kuralı ve eşik
   tahmini taşır; biri eksikse program açılmaz. Faz 4'ün 38 çekilişi program öncesi olarak
   kalır ve öyle sayılır.

5. **Hipotez kimliği K-051/4'le genişler — ama yalnızca dolu alanlarla.** `evren`,
   `portfoy`, `rejim` kimliğe girer; boşsa girmez, çünkü koşulsuz eklemek defterdeki 38
   satırın kimliğini değiştirir ve `dogrula()` hiçbirini tanımaz. `program` kimliğe
   **girmez**: aynı soruyu iki program altında sormak yeni bir soru değildir.

6. **`leak_riski` mutlak engeldir ve beyana dayanır (K-049/4).** `LlmTuretimi` model
   kimliği, eğitim kesimi, kapsadığı dönem, prompt ve girdi hash'i taşır; kapsam kesimden
   önceye uzanıyorsa `leak_riski`. `Sonuc.leak_riski` hash'e girmez (provenans, `dirty` gibi)
   ama `promotion_engelleri`ne girer. Bütün sayısal kapılar geçse bile sonuç geçemez.

### Raporlanan ama kapı olmayanlar

DSR (`research/dsr.py`, ham basıklıkla — fazlalık basıklık sonucu iyimser yapardı),
VaR/CVaR ve kapasite (Faz 10). **Olasılık kalibrasyonu uygulanamaz**: yalnızca olasılık
üreten tahmin modellerinde anlamlı ve bu projede henüz böyle bir model yok (Faz 13, koşullu).

### Geri dönüş koşulları

1. Yeni bir **ızgara biçimi** (nokta sayısı veya eksen sayısı belirgin farklı) → üç null
   eşiği o ızgarada yeniden ölçülür (`tools/kalibrasyon_v2_kos.py`).
2. İlk gerçek cross-sectional aday (Faz 12) → `evren_dayanikliligi` o adayla yeniden
   ölçülür; iştah sayısı ölçülmüş bir sayıya dönüşür.
3. `rejim_kararliligi`nin güven aralığı geniş (0,54-1,18) → iterasyon artırılarak daraltılır;
   eşik yuvarlanmaz.

### Ek: rejim penceresi zamana bağlı

Rejim etiketinin penceresi **30 gündür**, bar sayısı değil (1h/4h/1d → 720/180/30 bar). İlk
uygulamada sabit 720 bardı; 1d'de iki yıl ederek OOS penceresini tamamen ısınmada bıraktı ve
rejim hiç ölçülemedi. Eşik 1h'te kalibre edildi; zaman sabit tutulduğu için diğer
timeframe'lerde aynı soruyu soruyor.

### Sonuç: 38 çekiliş

**0/38** geçti. `evren_dayanikliligi` tek sembolde 38/38 ölçülemez; diğer üç kapıda en iyi
aday `cok_faktor` 1h/plato (PBO ✓, pertürbasyon ✓, rejim ✗) — Faz 4'ün de en yakın adayı.

## K-059 — Barı biten sembolde kalan pozisyon: 48 bar sonra sıfır değer; token göçü kimlik sorunudur

**Durum:** kabul · **Tarih:** 2026-09-16 · **Tamamlar:** K-057 (motorun "son bilinen fiyat"
kuralı), K-007, K-052/4 · **Kaynak:** Faz 12, `docs/Faz-12-Kesitsel-Fiyat-Raporu.md` §4,
`tools/faz12_bayat_olcumu.py` → `runs/faz12/bayat-olcumu.json`

### Bağlam

K-057 motoru barı olmayan sembolde pozisyonu son bilinen fiyattan değerliyor ve sayacı
(`bayat_degerleme`) Faz 12'nin ölçmesine bırakmıştı. `kesitsel_fiyat`'ın OOS'unda sayaç
13.101-58.254 çıktı. Ölçüm (kayıtlı `sonuc_hash`ler bit düzeyinde yeniden üretilerek):

- **9 takılı pozisyon**, hepsi barı pencere sonundan önce biten sembolde, 693-18.837 bar.
  Strateji onlardan **çıkamıyor**: barı olmayan sembol `ctx.gorunur()` dışında, hedef
  üretilemiyor, fill de yok.
- Sonda özkaynağın %1,0-8,3'ü takılı değer. Bir örnekte (BNX) son fiyat girişin 1,7 katı.
- İki sınır: son fiyat (a) ve son bardan itibaren sıfır (b). OOS Sharpe a → b: −0,510 →
  −0,630 · −0,177 → −0,198 · −0,922 → −1,047 · −0,967 → −1,082. Kıyasta takılı pozisyon 0.
- Takılanlardan en az dördü delist değil **token göçü** (MATIC→POL 2024-09, RNDR→RENDER
  2024-07, EOS rebrand 2025-05, BNX 2025-03): değer yeni ticker altında sürüyor, veride iki
  ayrı sembol.
- Evrendeki barsız aralıklar iki ayrık küme: **7-26 bar** (bakım; 2018-06-26 on dört sembolde
  10 bar) ve **96-7.466 bar** (durdurma, göç, delist; FTT 7.466, CVC 3.700). Arada gözlem yok.

### Karar — dört madde

1. **`CokluBacktest(sifira_yaz_bar=N)`:** art arda N bar barı gelmeyen pozisyon **sıfır**
   değerlenir; bar geri gelirse piyasa fiyatına döner. Karar `t`ye kadarki barlardan
   verilir (look-ahead yok, testle), yalnızca kötü yöne işler (K-007). Varsayılan `None`:
   eski davranış ve eski `sonuc_hash`ler değişmez; açıkken `evren.sifira_yazma` kaydına
   yazılır.
2. **Araştırma hattı N = 48 kullanır** (`evren_degerlendirme.SIFIRA_YAZ_BAR`). İki ölçülen
   kümenin arasından; bakım boşluğunu sıfıra yazmaz, delist/göçü iki günde yazar.
3. **`kesitsel_fiyat` yeniden değerlendirilmez.** Her iki sınırda da dört çekiliş kıyasın
   altında ve PBO/pertürbasyon kapıları bu değerlemeden bağımsız kalıyor; kapanış sağlam.
   Hipotez 39-42 bu kararın öncesinde (N = None) koşuldu ve öyle kayıtlı.
4. **Token göçü bir kimlik sorunudur, değerleme sorunu değil** (K-052/4'ün tersi yönü:
   aynı varlık, iki ticker). Bugün bağlanmıyor; sıfıra yazma göçte **kötümser** bir
   yanlılık bırakıyor ve bu bilinçli (K-007). Göç eşlemesi PIT bir kaynaktan (duyuru
   tarihi + dönüşüm oranı) gelmeden uydurulmaz.

### Geri dönüş koşulları

1. Göç eşleme verisi PIT bulunursa: göçte pozisyon yeni kimliğe taşınır, N yalnız delistte
   uygulanır.
2. Delist duyuru tarihleri PIT bulunursa: duyurudan sonra zorunlu çıkış modellenir ve
   sıfıra yazma yalnızca kaçırılan çıkışlar için kalır.
3. Bir çekiliş kapıları geçer ve takılı değer payı özkaynağın %1'ini aşarsa: sonuç N'ye
   duyarlılıkla (N = 24 / 96) yeniden raporlanır.

## K-060 — Makro stres engeli: günlük PIT, ertesi gün görünürlük, stres rejiminde yalnızca risk azaltan niyet

**Durum:** kabul · **Tarih:** 2026-09-16 · **Uygular:** K-037, K-052/5, K-052/15, K-050 ·
**Kaynak:** Faz 12 `makro_rejim` programı, `src/scryne_quant/data/makro.py`,
`src/scryne_quant/strategy/kutuphane/evren_makro.py`

### Karar — dört madde

1. **PIT:** ALFRED vintage satırı `d` gününde görülebilir ⇔ `realtime_start ≤ d ≤ realtime_end`;
   `d` gününün değeri o gün görülebilen en geç gözlem tarihli satırınki. Saat bilgisi yok:
   değer gün sonunda bilinir ve **`d+1` 00:00 barından itibaren** görünür (testle).
2. **Persentil günlük seride, yükleyicide, önceden sabit pencerelerle** (30/90/180/365 gün).
   Bar başına kayan persentil çekiliş başına günler sürerdi; gün içinde değer sabit olduğu
   için sonuç aynı. Izgara bu kümenin dışına çıkamaz.
3. **Stres rejiminde** kıyasın hedefi normal kurulur; yalnızca hedefi 0 olan (çıkış) ve
   elde olan sembolde hedefi mevcut ağırlığı aşmayan niyetler geçer. Yeni isim ve büyütme
   silinir; silinen niyet satış değildir ("bahsedilmeyen sembol olduğu gibi kalır"). Bu,
   K-050'nin asimetrisinin strateji içindeki hâli: engel yalnızca riski artıranı durdurur.
4. **Makro bilgisi yoksa stres yok sayılır.** Bilgi yokluğu engelleme gerekçesi değil
   (funding filtresiyle aynı kural). Makro bilgisi olmadan strateji kıyasla bit düzeyinde
   aynı (testle).

### Plan kaydı (Scryne onayı, 2026-09-16)

Faz 12 makro programıyla kapanır; ardından **Faz 14 öne alınır**: sürekli açık host, süreç
dışı kill switch, alarmlar ve paper modda 7/24 koşu. Bu koşuda kıyas ve en yakın adaylar
dondurulmuş hâlde **ileriye dönük** izlenir (30-60 gün). Gerçek sermaye yalnızca promotion
kapılarını geçen stratejiyle (K-010, K-018); kapılar gevşetilmez.

---

## K-061 — Gizli tekrar çekiliş dedektörü: TypeSafe (Jev) araştırma aracı, uyarır engellemez

**Durum:** kabul · **Tarih:** 2026-09-16 · **Uygular:** K-039, K-051 · **Sınırı:** K-049 ·
**Kaynak:** `src/scryne_quant/research/gizli_tekrar.py`, `sq lab tekrar-kontrol`,
`tests/unit/test_gizli_tekrar.py`

**Boşluk.** K-039 kimliği sayıyor, K-051 bütçeyi. İkisi de aynı mekanizmanın başka adla,
başka programda, başka kapsamda yeniden denenmesini görmez; bunu görmek gerekçe metnini
anlamayı gerektiriyor, hash ya da kural yetmiyor.

### Karar — dört madde

1. **Soru ve eşik.** Yeni kayıt × her önceki kayıt için tek Choice (`ayni_mekanizma` /
   `parametre_varyasyonu` / `farkli`), `jev-1.13.0`, hepsi paralel (48 karşılaştırmaya kadar
   tek istek). Kod `ilgili = P(ayni) + P(param)` toplar: **≥ 0,80 uyarı, 0,50–0,80 incele**.
   Soru metni `SORU_SHA256` ile dondurulmuş; metni değiştirmek eşiği geçersiz kılar ve yeni
   spike + yeni K-kaydı ister.
2. **Yetkisi yok.** Kaydı engellemez, defteri değiştirmez, çekiliş sayılmaz, alım-satım
   kararına ya da özelliğe girmez (K-049/1). Karar Scryne'ındır. Piyasa hakkında bir şey
   söylemediği için look-ahead taşımaz; K-049/4'ün kesim tarihi ve K-049/5'in dondurulmuş
   veri kaynağı kuralları uygulanmaz. İşlem katmanının (`strategy`, `backtest`, `features`,
   `risk`, `execution`, `live`) modülü ya da SDK'yı import etmediği testle korunuyor.
3. **Sürüm sabit.** Çözülen model `jev-1.13.0` değilse komut durur. Sürüm API'den kalkarsa
   eşikler yeni sürümde yeniden ölçülür. Her koşunun istek hash'leri ve cevapları
   `runs/gizli_tekrar/` altına yazılır (`.gitignore`'da; iz, kanıt değil).
4. **Anahtar yalnız yerel ortamda** (`TYPESAFE_API_KEY`); komut dışında hiçbir yol SDK'yı
   yüklemez.

### Ölçüm (spike, 2026-09-16, 48 kayıtlı defter)

| Yeni → önceki | ilgili | Jev |
|---|---|---|
| 43 evren_funding_kesit → 37 funding_filtre / 36 / 38 | 0,98 / 0,95 / 0,91 | aynı mekanizma |
| 43 → kalan 39 kayıt | ≤ 0,17 (medyan 0,02) | farklı |
| 40 kesitsel_guc aylık → 39 haftalık | 1,00 | parametre varyasyonu |
| 48 NFCI → 47 VIX | 0,04 | farklı |
| Sentetik gizli tekrar (38'in adı, "funding" kelimesi ve K-042 referansı silinmiş, evrene taşınmış), 3 koşu | 38: 0,93–0,97 · 44: 0,87–0,94 · 36: 0,84–0,89 · 37: 0,81–0,82 | aynı mekanizma |
| Aynı sentetik → 46 / 43 (akraba) | 0,58–0,66 | sınırda |
| Aynı sentetik → 18 rsi_donus (mekanizmasız idari gerekçe) | 0,40–0,51 | **yanlış alarm** |

Koşular arası oynama sınırda ±0,1; net kararlarda ±0,03. İstek başına ≈50k girdi token'ı
(≈ $0,002). Bu makinede ilk bağlantı DNS yüzünden ~12 sn; `--sira 43` uçtan uca 15 sn ve
spike'ı tekrarladı (0,98 / 0,96 / 0,93).

### Açık

- ~~**Aynı nedensel iddia, farklı veri serisi** (VIX stres engeli ↔ NFCI stres engeli)
  bugünkü tanımda `farkli`.~~ **Kapandı (Scryne, 2026-09-16): `farkli` kalıyor.** Aynı
  program içinde önceden kaydedilmiş proxy varyasyonları zaten ayrı çekiliş olarak sayılıyor
  (K-039, K-051 bütçesi); dedektörün yakalaması gereken şey kayıt dışı kalan başka adlı
  tekrar. Soru metni ve eşikler değişmiyor.
- Mekanizma içermeyen idari gerekçeler (hipotez 1-7, 18-21) incele bandına gürültü düşürüyor.
