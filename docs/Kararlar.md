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

**Faz 0'ın dört spike'ı da kapandı; Faz 1 kendi üç kararını (K-023/024/025) verdi ve
K-021'i kapattı; Faz 2 K-026/027'yi, Faz 3 K-028/029'u, Faz 4 K-030/031'i, Faz 5
K-032/033'ü ekledi.**

**Açık karar kalmadı.** Projenin son açık kararı olan **K-019** (promotion kapılarının
sayısal eşikleri) Faz 4 sonunda gerçek veriyle kalibre edilip kapandı. Bundan sonraki
kararlar yeni fazların kendi soruları olacak; K-018/3'ün beşinci eşik adayı
(paper/backtest drift üst sınırı) Faz 6'da ölçülebilir hâle gelince K-019'a eklenecek.

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
