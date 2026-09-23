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

## K-016 — Fee/slippage'ın kesin sayıları

**Durum:** kabul · **Tarih:** 2026-09-08 · **Kapatır:** Spike 4 · **Kaynak:**
`docs/spikes/04-maliyet-tarifesi.md`

Bu karar ayrı bir başlık taşımıyordu; numarası "Açık kararlar" tablosunda ve sekiz kararın
"İlgili" satırında geçtiği için başlık 2026-09-20'de eklendi (içerik yeni değil). Sayıların
kendisi K-007'nin "Ölçülen değerler" bloğunda: `fee_taker_bps = 10.0` (Binance VIP 0 spot,
BNB indirimi varsayılmıyor). Slippage bu kararda kapanmadı → K-020 (çürütüldü) → **K-021**
(5,2996 bps, yürütme penceresinden kalibre). Konfigürasyon biçimi K-025.

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

## K-062 — Sürekli açık host: AB'de bir VPS, paper modda

**Durum:** kabul · **Tarih:** 2026-09-17 · **Karar veren:** Scryne · **Uygular:** K-055,
K-060 plan kaydı · **Açar:** Faz 14

1. **Host bir VPS.** Ev bilgisayarı değil: elektrik, internet ve işletim sistemi
   güncellemesi kesintileri K-055'in ≥30 gün kesintisiz koşu kriterini ölçülemez kılar.
   Araştırma koşuları (bellek yoğun, `data/evren/`) yerel makinede kalır; host yalnızca
   canlı paper motorunu taşır.
2. **Konum AB (örn. Almanya); ABD değil.** Binance ABD IP'lerini engelliyor. Erişim Spike 1
   kalıbıyla host üzerinde yeniden doğrulanır; "yol açık" kanıtı yerel makineden taşınmaz.
3. **Boyut:** 2 vCPU / 4 GB RAM başlangıç. Canlı motor uzun geçmiş taşımaz; ölçülen bellek
   yetmezse büyütülür (ölç, tahmin etme).
4. **Erişim yalnızca SSH anahtarıyla**, parola girişi kapalı. Anahtar yalnızca bu host için
   üretildi (`~/.ssh/scrynequant_vps`), başka hiçbir yerde kullanılmaz.
5. **Mod paper.** Hostta borsa **işlem** anahtarı bulunmaz; Faz 8 tetiklenene kadar gerçek
   emir yolu yok.

## K-063 — Host şimdilik yerel bir Windows makinesi; K-062'nin VPS kararı askıda

**Durum:** kabul · **Tarih:** 2026-09-17 · **Karar veren:** Scryne · **Askıya alır:** K-062/1-4
(VPS) · **Korur:** K-062/5 (paper modda, hostta işlem anahtarı yok)

1. **Host Scryne'ın kendi bilgisayarlarından biri.** Tercih sırası: araştırma koşularının
   yapılmadığı **ikinci bilgisayar** (bellek ve kesinti çakışması yok), olmazsa ana makine.
2. **Bedeli yazılı:** elektrik, internet ve Windows güncellemesi kesintileri K-055'in ≥30 gün
   kesintisiz koşu kriterini zorlaştırır. Kriter gevşetilmez; kesinti olursa sebebi kaydedilir
   ve sayaç yeniden başlar. Toparlanma yolu (K-038) kesintinin iz bırakmadığını zaten ölçüyor.
3. **Asgari hazırlık:** uyku/hazırda bekleme kapalı, Windows Update etkin saatleri ayarlı,
   kablolu ağ tercih edilir; koşu zamanlanmış görevle oturum açılmadan başlar (Faz 6'daki
   `tools/paper-kosu.ps1` kalıbı).
4. **Geri dönüş koşulu:** 30 günlük pencerede iki veya daha fazla kontrol dışı kesinti
   (elektrik/ağ/güncelleme) ölçülürse K-062 (VPS) yeniden açılır.

## K-064 — Çoklu test null'ında sızıntı payı; `oos_sharpe` eşiği 41 çekilişle 1,04

**Durum:** kabul · **Tarih:** 2026-09-17 · **Düzeltir:** K-044'ün kaydırma yöntemi ·
**Kapatır:** Faz 12'nin "defter büyümesi sonrası eşik yeniden ölçülmüş" kriteri ·
**Kaynak:** `research/coklu_test.py`, `research/coklu_test_evren.py`, `tools/faz12_coklu_test.py`,
`runs/faz12/coklu-test-birlesik-500-0.json`, `runs/faz12/coklu-test-sizintisiz-500-0.json`

### Bağlam

K-044 her çekilişin OOS sinyal takvimini `k ∈ [1, L−2]` bar dairesel kaydırıyordu. Faz 12
evren çekilişlerini aynı null'a kattı (sinyal özellikleri kaydırılarak) ve 41 çekiliş ×
500 iterasyonda %5 eşik **1,154** çıktı. Uç değerler tek bir çekilişten geldi:
`kesitsel_guc_haftalik`'in null Sharpe'ı 6,3'e kadar. Sebep: `k = L − m` sinyali `m` bar
**öne** alır; `t`deki karar `t−m`de uygulanır ve strateji henüz gerçekleşmemiş barları
görmüş olur. Kesitsel skorun penceresi 336 bar olduğu için sızıntı bölgesi iterasyonların
%1,4'ü, tam uç değerlerin sıklığı. Aynı kusur K-044'ün tek sembollü null'ında da vardı
(daha küçük ölçekte); yönü eşiği **yükseltmek**, yani tutucu.

### Karar — dört madde

1. **Sızıntı payı:** kaydırma `k ∈ [1, L−2−H]`. `H` tek sembolde stratejinin ısınması,
   evren çekilişinde ısınma + yeniden dengeleme periyodu. Varsayılan `H = 0` K-044'ün
   formülüyle aynı (eski kayıtlar yeniden üretilebilir, testle).
2. **Ölçüm (sonradan dışlama, aynı 500 satır):**

   | Küme | Sızıntılı p95 | Sızıntısız p95 | %90 GA |
   | --- | ---: | ---: | --- |
   | Tek sembollü (31) | 1,072 | 1,039 | 0,975-1,076 |
   | Evren (10) | 0,613 | 0,529 | 0,507-0,545 |
   | **Hepsi (41)** | 1,154 | **1,039** | 0,975-1,076 |

   Evren çekilişleri maksimumu hiç taşımıyor (portföy stratejilerinin null Sharpe'ı dar).
3. **`COKLU_TEST_ESIGI` = 1,04:** K-044'ün 1,021'i (4.000 iterasyon, sızıntılı) ile
   1,039'dan (500 iterasyon, sızıntısız) tutucu olanın yukarı yuvarlanmışı (K-007).
   `COKLU_TEST_CEKILIS_SAYISI` = 41. Hiçbir çekilişin kararı değişmiyor (en iyi OOS Sharpe
   0,26 evren, 0,46 tek sembollü).
4. **Açık kalem:** sızıntı paylı **yeni koşu** (`k` doğrudan daraltılmış aralıktan) ve daha
   çok iterasyon (GA'yı K-044'ün genişliğine indirmek için ≈2.000+). Uzun iş: sürekli açık
   hostta koşturulur (K-063).

## K-065 — Süreç dışı kill switch: işaret → süreç → emirler

**Durum:** kabul · **Tarih:** 2026-09-17 · **Kapatır:** Denetim-v2 A8, Faz 14'ün kill switch
kriteri · **Tamamlar:** K-008 (süreç içi SAFE_MODE), K-043 (durdurma bayrağı) · **Kaynak:**
`src/scryne_quant/live/kill.py`, `sq kill`, `tools/faz14_kill_tatbikati.py`,
`runs/faz14/kill-tatbikati-1789656349736.json`

### Karar — beş madde

1. **Sıra sabit:** (a) SAFE_MODE işareti diske (`<koşu>.safemode`), (b) trader süreci
   `TerminateProcess` ile sonlandırılır, (c) borsadaki açık emirler iptal edilir ve **yeniden
   okunarak** doğrulanır. İşaret ilk: sonraki adımlar başarısız olsa bile yeniden başlatma
   kilitli açılır. Süreç emirlerden önce: tersi iptal ile ölüm arasına yeni emir sokabilirdi.
2. **İşbirliği yok:** süreç `<koşu>.pid` dosyasından bulunur (kilit dosyası Windows'ta tutulurken
   okunamıyor); askıya alınmış süreç de sonlandırılır. İşaret veritabanında değil ayrı dosyada:
   donmuş süreç SQLite yazma kilidini tutuyor olabilir.
3. **Yeniden başlatma SAFE_MODE'da:** `baslat.kur` işareti görürse risk motorunu toparlanmadan
   **sonra** kilitler (önce kilitlemek toparlanmanın yeniden ürettiği kararları ayrıştırırdı).
4. **Çıkış yalnızca elle:** `sq kill kaldir --not` (≥10 karakter, geçmiş dosyasına yazılır) +
   risk motorunda `sq risk serbest` (K-008/4, K-050).
5. **Başarı raporla ölçülür:** `<koşu>.kill.json`; süreç ölmediyse, iptal hata verdiyse ya da
   doğrulamada açık emir kaldıysa kill **başarısız** (çıkış kodu 1).

### Kanıt (gerçek testnet, 2026-09-17)

İki GTC limit alım emri koymuş, sonra `NtSuspendProcess` ile dondurulmuş bir trader. `sq kill
calistir --testnet` ayrı süreçten: 2,97 s, çıkış 0. Bağımsız okuma: önce 2 açık emir → sonra 0;
süreç yaşıyor → ölü; aynı koşu yeniden kurulunca `safe_mode = True`, sebep "süreç dışı kill: …".
Birim testleri sahte borsayla sırayı (iptal anında süreç ölü), başarısız iptalin raporunu ve
işaretin gerekçesiz kaldırılamadığını koruyor.

## K-066 — Host sırları ve dış bildirim kanalı: FRED anahtarı hostta, alarmlar ntfy.sh ile

**Durum:** kabul · **Tarih:** 2026-09-17 · **Onay:** Scryne ("tüm dediğin her şeyi
onaylıyorum") · **Tamamlar:** K-062/5 (hostta borsa işlem anahtarı yok), K-050 · **Kaynak:**
`src/scryne_quant/data/alfred.py`, `src/scryne_quant/cli/izle.py`, `docs/Runbook.md`

### Karar

1. **FRED API anahtarı hostun `.env` dosyasında** (kullanıcı profilinde; yalnız kullanıcı,
   SYSTEM, yöneticiler okuyabilir). Yalnızca herkese açık makro veriyi okur; `evren_makro_nfci`
   koşusunun canlı girdisi için gerekli. Hiçbir çıktıya, loga, kayda yazılmaz (aktarım çıktısız
   yapıldı). **Borsa anahtarı hosta konmadı ve bu karar onu değiştirmez** (K-062/5).
2. **Alarm ve günlük özet ntfy.sh üzerinden telefona.** Konu adı tahmin edilemez rastgele
   dizge, hostun `.env`inde (`SQ_NTFY_KONU`). ntfy'da konuyu bilen herkes okuyabildiği için
   mesajlarda sır, anahtar, gerçek hesap bilgisi **yok**: alarm kodu, koşu adı, gözlem
   koşusunun sanal özkaynağı.
3. **Sessizlik sinyaldir:** 09:00 TR günlük özet gelmediyse host/görev/ağ ayakta değildir.
   Alarm sistemi kendi ölümünü haber veremez.
4. **Bildirim yalnızca gözlem:** alarm koşuyu durdurmaz, limit değiştirmez (K-050).

### Gerekçe

Bildirimsiz alarm, kimsenin bakmadığı bir dosyaya yazılmış alarmdır. ntfy hesap/uygulama anahtarı
istemeyen en basit kanal; bedeli konunun gizliliğe değil tahmin edilemezliğe dayanması — bu
yüzden içerik sınırlandı.

### Ek (2026-09-20, Scryne: "K-066: AÇ") — vadeli **salt okunur** anahtar, iki uç

Hat 1 ikinci tavanının iki girdisi (VIP 0 USDT-M taker fee; C-isolated MMR kademeleri)
anahtarsız hiçbir resmî kaynaktan doğrulanamadı (`docs/Faz-16-Hat1-Fee-MMR-Erisilebilirlik.md`).
Ek kapsam: vadeli hesap için **salt okunur** API anahtarı; yetki yalnız `GET /fapi/v1/
commissionRate` ve `GET /fapi/v1/leverageBracket`; işlem/emir **kapalı**, çekim **kapalı**,
başka uç yok. Anahtar hosta konmaz (K-062/5 aynen); yalnız araştırma makinesinde, hiçbir
çıktıya yazılmaz. Erişim ölçüm kapısı **değildir**: gelen kayıt tarihlidir, PIT sınırı kayıt
anıdır (2020–2025 IS'e uygulanırsa `NON_PIT/leak_risk`, kapı dışı). Araç:
`tools/faz16_vadeli_okuma.py`; kayıt `docs/spikes/08-vadeli-tarife-kademe.md`. Mevcut spot
salt okunur anahtar bu uçlarda `-2015` verdi (yetki yok); yetkili anahtar Scryne'ın eylemi.

## K-067 — Jev'in genişleyen rolü: eleme ve **ileriye dönük** sınıflandırma; sinyal üretimi yok

**Durum:** kabul · **Tarih:** 2026-09-17 · **Onay:** Scryne ("bu jev modelini de aktif olarak
kullanalım") · **Genişletir:** K-061 · **Tabi:** K-049 (AI yetkisi), K-039/K-051 (çekiliş
sayımı) · **Kaynak:** `tools/faz16_duyuru_indir.py`, `research/gizli_tekrar.py`

### Karar — Jev'in izinli üç rolü

1. **Gizli tekrar dedektörü (K-061, yürürlükte).** Hipotez kaydından önce, aynı mekanizmanın
   başka adla tekrar denenip denenmediğini metinden yakalar. Uyarır, engellemez, sayılmaz.
2. **Program öncesi kaynak elemesi.** Yeni bir araştırma programı açılmadan önce, önerilen
   bilgi kaynağının daha önce kapatılmış kaynakların yeniden ifadesi olup olmadığını
   değerlendirir. **Tavsiyedir:** K-045'in istisna şartını Jev değil, sayısal kaynak ölçümü
   karşılar (`tools/faz16_kaynak_olcumu.py`). Jev'in "farklı" demesi bir programı açmaz.
3. **İleriye dönük metin sınıflandırması.** Kamuya açık duyuru/haber metinleri Jev'le tipli
   alanlara çevrilir ve **görüldüğü an** (`available_time`) ile saklanır. Bu kayıt dondurulmuş
   bir veri kaynağıdır (K-049/3): backtest içinde **hesaplanmaz**, yalnızca okunur.

### Sınırlar — ihlali görevi yanlış yapar, kuralı değil

- **Jev sinyal üretmez.** Hiçbir alım/satım niyeti, ağırlık ya da hedef Jev çıktısından
  doğrudan türetilemez; strateji katmanı yalnızca dondurulmuş alanları okur (K-003, K-049/1).
- **Geçmiş dönem için Jev türetimi kapıya giremez.** Modelin eğitim kesimi öncesine ait metni
  bugün sınıflandırmak `leak_riski` taşır (K-049/4). Geçmiş için **kural tabanlı** ayrıştırma
  kullanılır; Jev o kuralların kalitesini ölçmekte kullanılabilir (ölçüm, özellik değil).
- **Sürüm ve soru donar.** Model sürümü ve soru metninin hash'i her kayda yazılır; soru
  değişirse eşikler geçersizdir ve yeniden ölçülür (K-061/3 kalıbı).
- **Çekiliş sayımı değişmez.** Jev'in önerdiği ya da elediği her hipotez, deftere normal
  şekilde kaydedilir ve bütçeden düşer (K-039, K-051).
- **Gecikme ve maliyet ölçülür.** Canlı yolda kullanılacaksa, koşunun bar bütçesine sığdığı
  ölçülür; ölçülmeden canlı koşuya bağlanmaz.

### Gerekçe

Jev metin ve anlam üzerine tipli yargı verir; TypeSafe'in kendi dokümanı zaman serisi tahminini
ve sayısal öngörüyü uygun olmayan kullanım sayıyor. Bu projede eksik olan da tahmin değil,
**yapılandırılmamış bilginin sayıya çevrilmesi**: duyuru, kural değişikliği, erişim genişlemesi.
Jev'i oraya koymak yeni bir bilgi kaynağı açar; sinyal üretimine koymak K-049'un yasakladığı
şeydir ve ölçülemeyen bir kara kutu üretir.


## K-068 — Kıyas-üstü tek dışlama katmanı ailesi kapanıyor; sıradaki program iskeleti değiştirir

**Durum:** kabul · **Tarih:** 2026-09-18 · **Faz:** 16 · **Kapatır:** evren kıyasının üstüne
tek dışlama katmanı ekleyen çekiliş ailesi · **İlgili:** K-042, K-045, K-051, K-054, K-067 ·
**Kanıt:** `docs/Faz-12-Turev-Evren-Raporu.md`, `docs/Faz-12-Makro-Rejim-Raporu.md`,
`docs/Faz-16-Konumlanma-Raporu.md`

**Bağlam.** Faz 12 ve Faz 16'da üç program, sekiz çekiliş, tek bir iskelet: `evren_esit_agirlik`
kıyası (n=10, haftalık, hedef brüt 0,2) + kesitte bir dilimi dışlayan tek katman. Dışlama
ölçütü her seferinde bilerek farklı bir bilgi kaynağından alındı ve her seferinde K-045'in
istisna şartı sayısal olarak karşılandı:

| Program | Çekiliş | Dışlama ölçütü | En iyi OOS Sharpe | Kıyas |
| --- | ---: | --- | ---: | ---: |
| `turev_evren` | 4 | funding birikimi, basis primi, ikisinin kesit sırası | 0,256 | 0,333 / 0,167 |
| `makro_rejim` | 2 | VIX, NFCI stres engeli | 0,216 | 0,167 |
| `konumlanma_evren` | 2 | açık pozisyon birikimi, taker baskısı | 0,087 | 0,167 |

Sekiz çekilişin hiçbiri 11 kapıyı geçmedi (en iyi 6/11). İkisi OOS'ta kıyasın üstüne çıktı
(h44, h46) ama ikisi de kıyasın kendi IS/WF bandının içinde kaldı; hiçbiri ayrışmadı.

**Karar.** Bu iskelete dokuzuncu bir seri bağlanmaz. Yeni bir kaynağın "farklı" olduğunu
gösteren kaynak ölçümü, K-045 istisnasını **artık tek başına karşılamaz**: sekiz ölçüm
bağımsızlığın sıralama gücü anlamına gelmediğini gösterdi. Bundan sonra kıyas-üstü dışlama
öneren bir program kaydı açılabilmesi için, kaynak farkına **ek olarak** önerilen ölçütün
kesitte ileriye dönük getiri sırasıyla ölçülmüş ve sıfırdan ayrışan bir ilişkisi gerekir —
yani kaynak ölçümü fiyata bağımsızlığı değil, sıralama gücünü de raporlar.

**Sıradaki program ne yapmalı.** Kaynağı değil **iskeleti** değiştirmeli: kıyasın seçimini
süzmek yerine, kıyasın yapısı gereği göremediği bir olayı ölçmeli. Yürürlükteki aday, evren
kuralının aylık ızgarasının arasında kalan erişim değişiklikleridir (listeleme, marjin/vadeli
ekleme, delist — `data/duyuru/olaylar.parquet`, K-067/3). Bu bir açılış değil, bir yön; program
K-051'e tabidir ve kendi ön kaydı, bütçesi ve durma kuralıyla açılır.

**Geri dönüş koşulu.** Karar, ölçülmüş bir şeye dayanıyor ve ölçümle geri alınabilir: yukarıdaki
ek şartı (kesitte sıfırdan ayrışan ileriye dönük sıralama gücü) sağlayan bir ölçüt bulunursa,
aile yeniden açılır ve o ölçüt normal bir program kaydıyla denenir.

**Ek şartın sınırı** (aynı gün eklendi, 2026-09-18): yukarıdaki "ileriye dönük sıralama
gücü" ölçümü **yalnızca in-sample penceresinde** (bar 0-55.594, `27b7a16ed0ed` evreninde)
yapılır ve rapor bunu açıkça yazar. Tam örneklemde ölçülürse, program daha açılmadan OOS
görülmüş olur — K-039'un yasakladığı şeyin ta kendisi, üstelik bir kapı kılığında. Ölçüm
yine çekiliş sayılmaz (strateji koşmaz, parametre seçilmez), ama artık "bu araç ileriye
dönük hiçbir getiriye bakmaz" cümlesi yeni kaynak ölçümleri için geçerli değildir; yerine
geçen kural: **ileriye dönük getiriye yalnızca in-sample'da bakılır.**

## K-069 — Faz 14'ün dayanıklılık kriteri 30 günden 8 güne indi; promotion kapısı değişmedi

**Durum:** kabul · **Tarih:** 2026-09-18 · **Onay:** Scryne ("bu 30 gün çok fazla. 1 hafta
yeterli olucaktır", 30 günlük Faz 8 ön koşulu için "tamamen kalksın") · **Değiştirir:** K-055 ·
**İlgili:** K-010, K-018, K-050, K-062, K-063

### Karar

1. **Faz 14'ün bitti kriteri:** "sürekli açık host üzerinde ≥30 gün kesintisiz koşu" →
   **≥8 gün** (host-1: 2026-09-17 → **2026-09-25**). Kesinti olduysa sebebi kayıtlı ve
   giderilmiş şartı **aynen duruyor**.
2. **Faz 8'in 5. ön koşulundaki "30 günlük kesintisiz koşu" kaldırıldı.** "Sürekli açık bir
   host" şartı ve "açık pozisyonla gerçek bir toparlanma en az bir kez görülmüş olmalı"
   şartı duruyor.
3. **`risk/promotion.py:ASGARI_PAPER_GUN = 30.0` DEĞİŞMEDİ** ve bu kararın kapsamı dışıdır.
   Bir stratejinin promotion zincirini geçmesi için hâlâ 30 paper günü gerekir (K-018/3).

### Neden 8, neden 5 değil

Sekiz gün keyfî değil, **bir tam yeniden dengeleme turunu** içine alacak en kısa süre:
evren koşularının periyodu 168 bar (7 gün), ilk dengeleme **2026-09-24**. Salı (22 Eylül,
5 gün) biten bir koşu ana döngünün periyodik işini — hedef portföy kurma, emir üretme,
mutabakat — **bir kez bile çalıştırmamış** olurdu. Ayakta kalmayı ölçen ama çalışmayı
ölçmeyen bir dayanıklılık kriteri, geçen ama boş bir testtir (Faz 2'nin dersi).

### Bu karar canlıya giden yolu açmıyor — nedeni yazılı olsun

Faz 8 ön koşulundan 30 gün kalksa bile, canlıya geçmek için önce promotion gerekir ve
promotion `paper_gun ≥ 30` ister. O 30 paper günü zaten sürekli açık host üzerinde koşar.
Yani **30 günlük kesintisiz host operasyonu, kaldırılan ön koşuldan bağımsız olarak
promotion kapısının içinden geri geliyor.** Kaldırılan şey, aynı şartın ikinci ve ayrı bir
kopyasıydı; K-050'nin "izni artıran karar sayısal kapı ister" kuralını delen bir gevşetme
değil.

### Ne kaybediyoruz, açıkça

- **Ay sınırı kod yolu ölçülmemiş kalıyor.** Evren tablosu ve PIT üyelik ayda bir yenileniyor;
  8 günlük pencere 1 Ekim geçişini içermiyor. Ay başı yolu ilk kez promotion'un 30 paper
  gününde koşacak — yani yine koşacak, ama Faz 14'ün gözetimi altında değil.
- **Uzun vadeli bellek davranışı ölçülmemiş kalıyor.** Süreç başına ≈4,5 GB ölçüldü; yavaş
  bir sızıntı 8 günde görünmeyebilir.
- Bunlar **kayıtlı risktir, kapı değil.** Bir kapıya dönüşmeleri gerekirse K-050/3'ün kademeli
  sermaye tablosunda yazılır.

### Geri dönüş koşulu

8 günlük pencerede bir kesinti olur ve sebebi giderilemezse, kriter sebebin ölçülmesini
gerektiren süreye uzar. Süre kısaltıldığı için değil, **sebep bilinmediği için** uzar.

## K-070 — `agirliklar()` tavanı bir tavan değildi; kırpılan pozisyon kilitleniyor

**Durum:** kabul · **Tarih:** 2026-09-18 · **Faz:** 16 · **İlgili:** K-057, K-051/4 ·
**Kaynak:** `src/scryne_quant/strategy/kurma.py`, `tests/unit/test_evren_kurma.py`

**Bulgu.** `strategy/kurma.py:agirliklar()` tavanı aşan ağırlıkları kırpıp artan bütçeyi
kalanlara dağıtıyor. Kırpılan enstrüman **kilitlenmiyordu**: kırpıldıktan sonra `w == tavan`
olduğu için bir sonraki turda `w > tavan` testine takılmıyor, "serbest" sayılıyor ve yeniden
pay alıyordu. Sonuç, tavanın aşılması ve döngünün yakınsamaması.

Ölçülen (`hedef_brut = 0,2`, `azami_agirlik = 0,05`, oynaklıklar 0,01/0,02/0,03):

| Aday sayısı | Eski çıktı | Tavan aşıldı mı |
| ---: | --- | --- |
| 3 | A 0,05 · B 0,05 · **C 0,10** | evet, **iki katı** |
| 4 | A 0,0520 · B 0,05 · C 0,0520 · D 0,0460 | evet |

Fonksiyonun kendi docstring'i *"Sabit nokta: her turda en az bir enstrüman tavana oturur,
yani en fazla `len(secilen)` tur"* diyordu. Cümle doğruydu, kod onu uygulamıyordu: oturan
enstrüman bir sonraki turda kalkıyordu. Döngü `len(secilen)` turda kesiliyor, dolayısıyla
çıktı salınımın nerede kesildiğine bağlı.

**Düzeltme.** Kırpılan enstrüman `kilitli` maskesine giriyor ve bir daha pay almıyor. Her tur
en az bir enstrüman kilitlendiği için sabit nokta artık garanti.

**Hiçbir kayıtlı sonuç değişmedi ve bu tesadüf değil.** Bugüne kadarki bütün evren koşuları
`esit_agirlik=True` ile yapıldı; orada bütün ağırlıklar eşit ve tavan `hedef_brut /
azami_enstruman`, yani ya hiçbiri tavanı aşar ya da hepsi birden aşar. İkinci durumda hepsi
tavana kırpılır ve dağıtılacak "serbest" enstrüman kalmaz — eski kod da yeni kod da aynı
şeyi verir. Karışık durum (bazıları üstte, bazıları altta) yalnızca oynaklık ayarlı
dağıtımda doğuyor ve o yol hiçbir çekilişte koşmamıştı. 1.617 testin tamamı yeşil, referans
fixture'ları ve determinizm testleri dahil.

**Ders, bu projede daha önce iki kez yazıldı ve üçüncü kez doğrulandı:** hata, o kod yolunu
ilk kez gerçekten çalıştıran test yazıldığında çıktı. `esit_agirlik=False` Faz 10'dan beri
kodda duruyordu, docstring'i vardı, tip kontrolünden geçiyordu ve **hiç koşmamıştı**.
Koşmayan kod, çalıştığı varsayılan koddur.

## K-071 — Çoklu test eşiği 43 çekilişle yeniden ölçüldü; sabit 1,04'te kalıyor

**Durum:** kabul · **Tarih:** 2026-09-18 · **Faz:** 16 · **Kapatır:** K-064/4'ün açık kalemi
(sızıntı paylı **yeni koşu**) · **İlgili:** K-007, K-039, K-044, K-050 · **Kaynak:**
`runs/faz12/coklu-test-birlesik-500-0.json`, `research/kapilar.py`

### Ölçüm

Defterdeki 43 ölçülebilir çekilişin (31 tek sembollü + 12 evren) tamamı, K-064'ün sızıntı
paylı kaydırmasıyla (`k ∈ [1, L−2−H]`) **yeniden koşuldu** — sonradan dışlama yaklaşımıyla
değil. 500 iterasyon, seed 0.

| Yanlış pozitif hedefi | Ölçülen eşik | %90 GA |
| --- | ---: | --- |
| %20 | 0,592 | 0,571-0,643 |
| %10 | 0,745 | 0,697-0,785 |
| **%5** | **0,926** | 0,838-0,967 |
| %1 | 1,178 | 1,099-1,306 |

**Yürürlükteki 1,04'ün gerçek yanlış-pozitif oranı: %2,6.**

### Karar — sabit indirilmiyor

Ölçülen %5 sınırı (0,926) yürürlükteki sabitin altında, yani 1,04 tasarım hedefinden **daha
sıkı** bir kapı. 1,04'ü 0,93'e çekmenin tek gerekçesi "oran tam %5 olsun" olurdu; bu bir
promotion kapısını, sonucu gördükten sonra, stratejilerin geçmesini kolaylaştıran yönde
gevşetmektir (K-007'nin yuvarlama yönü, K-050'nin asimetrisi). Sabit **1,04**'te kalıyor,
`COKLU_TEST_CEKILIS_SAYISI` 41 → **43**.

Eşiğin düşmesi defterin küçülmesinden değil **yöntemin düzelmesinden** geliyor: K-064'ün
sonradan dışlaması aynı 500 satırı koşullayarak sızıntıyı ayıklıyordu, yeni koşu sızıntıyı
hiç üretmiyor ve null daha dar çıkıyor. Defter 41'den 43'e çıktı, yani karşıt yönde bir
etki de var; ikisinin bileşkesi 1,0388 → 0,926.

### Beklenmeyen bulgu: ölçüm aracı defterin yarısını sessizce düşürüyordu

Bu yeniden ölçüm plansızdı. `tools/faz12_coklu_test.py --birlestir` ilk koşturulduğunda
eşiği **0,51** olarak raporladı — kapıya yazılsaydı çıta yarıya inerdi. Sebep: K-064 satır
şemasına `sizinti_bar` alanını ekledi ve iki birleştirme yolu birbirinin tümleyeni oldu:

| Yol | Aldığı satır | O anki sonuç |
| --- | --- | --- |
| `--birlestir` | yalnız `sizinti_bar` **olan** | 12 evren → 0,51 |
| `--sonradan-sizintisiz` | yalnız `sizinti_bar` **olmayan** | 0 satır → çöktü |

Arada, önceki oturumun çöken koşusu (`sinyal özellikleri tanımlı değil`, K-070 commit'inde
düzeltildi) 10 evren satırını yeni şemaya taşımıştı. Sonuç: evren tarafı yeni şemada, tek
sembollü taraf eskisinde ve **hiçbir komut ikisini birleştiremiyor.**

Çıktı hata vermedi: `"defter_sayisi": 50` ve `"olculebilir": 12` yan yana yazdı, aradaki
uçurum hakkında tek kelime etmedi. Bu projenin uyarısının tam olarak tarif ettiği durum —
"neredeyse doğru" bir sayı, fark edilmeden bir kapıya yazılabilirdi.

**Düzeltme:** 31 tek sembollü satır da yeni yöntemle koşuldu; 43 satırın tamamı artık aynı
şemada ve `--birlestir` kümenin tamamını görüyor. `--sonradan-sizintisiz` yolu artık
işlevsiz (besleyeceği eski satır kalmadı); tarihsel kayıt olarak duruyor.

**Açık kalem (K-064/4'ten devralındı):** iterasyon sayısı hâlâ 500; %5 eşiğinin %90 güven
aralığı 0,13 genişliğinde. Daraltmak ≈2.000+ iterasyon ister, o da ≈8 saatlik bir koşu.
Sabit 1,04, aralığın **üstünde** olduğu için bu kalem bugünkü kararı değiştirmiyor.

## K-072 — Kıyas ayarlanmaz: sıfır noktası kuralla sabit, promotion iddiası ikinci çizgiye tabi

**Durum:** kabul · **Tarih:** 2026-09-18 · **Onay:** Scryne · **Faz:** 16 ·
**Denetler:** K-030 · **İlgili:** K-007, K-010, K-018, K-039, K-051 · **Kanıt:**
`docs/Faz-16-Kiyas-Olcumu.md`, `runs/faz16/kiyas-olcumu.json`

### Bağlam

Faz 12-16'nın on çekilişinin tamamı `evren_esit_agirlik` kıyasına karşı değerlendirildi ve
o kıyasın iki parametresi (`azami_enstruman = 10`, `yeniden_dengele_bar = 168`) **ölçülerek
değil varsayılan olarak** seçilmişti. Ölçüldüğünde kıyasın kendi OOS Sharpe'ının ızgara
boyunca **+0,333 ile −0,507** arasında gezindiği çıktı.

### Karar — üç madde

1. **Kıyas ayarlanmaz.** Parametresi IS'te (ya da herhangi bir pencerede) optimize edilip
   sabitlenemez. Ölçüm bunu bir tercih değil, bir **imkânsızlık** olarak gösterdi: IS'te en
   iyi olan kıyas (n=39/720, IS Sharpe +0,492) OOS'ta 15 adayın 10.'su ve Sharpe'ı
   **−0,357**. Kıyası IS'te seçmek, stratejileri IS'te seçmekle aynı hata; kıyas sıfır
   noktası olduğu için maliyeti daha büyük.
2. **Kayıtlı kıyas, çekilişin seçtiği yoğunlukta koşulmaya devam eder.** Bu apples-to-apples
   karşılaştırmadır (aynı evren, aynı yoğunluk, aynı takvim; fark yalnızca çekilişin
   değiştirdiği şeyde) ve **durma kuralının ölçütü budur**. Değişiklik yok.
3. **Promotion iddiası ikinci ve daha sıkı bir çizgiye tabidir.** Bir strateji için "bu,
   hiçbir şey yapmamaktan iyidir" denebilmesi için, kendi kıyasını geçmesi **yetmez**;
   ilan edilmiş kıyas ızgarasının **geriye dönük en iyisini** de geçmelidir. Bugünkü değer:
   **OOS Sharpe 0,333** (n=5, periyot 168). Bu çizgi bir kapı değil, promotion kanıtının
   parçasıdır ve raporlarda ayrı satır olarak görünür.

### Neden 3. madde adil — ve neden tersi adil olmazdı

Geriye dönük en iyi kıyas, önceden bilinemezdi; onu çıta yapmak stratejiye haksızlık gibi
görünür. Ama karar şudur: **gerçek parayı riske atmanın alternatifi, en basit şeyi
yapmaktır** ve o basit şeyin geriye dönük en iyi hâli, "keşke hiçbir şey yapmasaydım"
sorusunun cevabıdır. Çıtayı yükseltmek yanlış pozitif üretemez (K-007'nin yönü, K-050'nin
asimetrisi). Tersi — geçilmesi kolay bir kıyas parametresi seçmek — doğrudan K-018'i deler.

### Ne değişmiyor

Geçmiş on çekilişin sonuçları **yeniden koşulmuyor ve değişmiyor**; yalnızca okunuşuna bir
satır ekleniyor. Hiçbiri 11 kapıyı geçmemişti, dolayısıyla 3. madde hiçbir kararı
çevirmiyor.

### Ölçülmüş yan kısıt: parametresiz kıyas kurulamıyor

Evren kuralının `ust_n`'i 50, `hedef_brut` 0,2; "herkesi eşit taşı" dendiğinde pay 0,004 ve
kurma katmanının asgari ağırlık tabanı 0,005. **Parametresiz kıyas bugünkü sözleşmede var
olamıyor** — ifade edilebilir azami yoğunluk 39. Tabanı indirmek ya da brütü büyütmek ayrı
birer karardır ve **sonuca bakılarak verilemez**; ikisi de risk iştahının parçası (K-033).

### `kurma_evren`e etkisi, açıkça

h51'in OOS Sharpe'ı 0,363; kendi kıyasını (n=10, 0,167) iki katından fazla geçiyor ve bu
doğru. Ama 3. maddenin çizgisi 0,333, yani üstünlük **%9**. Rapordaki "kıyası iki kat
geçti" okunuşu, seçilen kıyas yüzünden olduğundan büyük görünüyordu; düzeltme
`docs/Faz-16-Kiyas-Olcumu.md` §5'te.

## K-073 — Araştırma/canlı risk motoru ve evren kalibrasyonu: karşılaştırılabilirlik uyuşmazlığı

**Durum:** kabul · **Tarih:** 2026-09-18 · **Onay:** Scryne · **Faz:** 14 · **İlgili:**
K-001, K-019, K-021, K-030, K-033, K-035, K-050, K-051, K-057, K-060, K-069, K-072 ·
**Kanıt:** bu kararın "Ölçülenler" bölümü — hepsi 2026-09-18'de, koşu dosyalarının salt
okunur kopyalarından yeniden üretilerek ölçüldü; canlı koşulara dokunulmadı.

### Bulgu

**Araştırma backtest'i risk motorsuz koşuyor, canlı gözlem yolu risk motorunu zorunlu
uyguluyor.** Üç araştırma kurulum noktasının üçü de `CokluBacktest`i `risk=` argümanı
vermeden kuruyor, yani `risk=None`:

| Yol | Kurulum noktası | Risk motoru |
| --- | --- | --- |
| Araştırma — evren backtest'i | `cli/main.py:3281` (`sq evren backtest`) | **yok** (`risk=None`) |
| Araştırma — çekiliş/ızgara | `research/evren_degerlendirme.py:260` | **yok** |
| Araştırma — çoklu test null'ı | `research/coklu_test_evren.py:198` | **yok** |
| Canlı — paper/gözlem | `cli/main.py:2554` → `live/evren_motor.py:84` | **`RiskMotoru(limitler, "1h", mod="gozlem")`** |

`backtest/coklu_motor.py:230` bunu açıkça söylüyor: *"Risk devre dışıysa bu fonksiyon
kimliktir… Faz 1-4'ün risksiz ölçümleri bu yüzden bit düzeyinde korunuyor."* Yani
`risk=None` bir unutma değil, bilinçli bir sözleşme. Kaydedilmemiş olan şey bu sözleşmenin
**sonucu**: dondurulmuş bir hipotez ileriye dönük izlendiğinde (K-060), izlenen şey
hipotezin kendisi değil, onun risk motorlu hâlidir.

**İkinci yarısı: eşik BTC'den kalibre, evren altcoin.** `volatilite_esigi = 0,020466`,
ATR(14)/fiyat dağılımının p99'u; ölçüm **45.562 barlık tek sembollü** seride yapıldı
(2026-09-10, `config/risk.json` → `gerekceler.volatilite_esigi`, `veri_sha256`
`e3adb02c…`, `risk/kalibrasyon.py` `VOLATILITE_PERSENTILI = 99`). Faz 5'te bu doğru
ölçülmüş bir sayıydı — o zaman evren tek semboldü. 50 üyeli altcoin evreninde aynı eşiğin
p99'a denk gelip gelmediği **ölçülmedi**. Guard'ın gerekçesi "olağandışı çalkantıda işlem
yapma" ve "olağandışı"nın tanımı veriden gelmeli (K-021/K-033 kalıbı); eşiğin türetildiği
veri ile uygulandığı veri artık aynı değil.

### Bu bir kod hatası değildir

Her iki kod yolu da kendi sözleşmesine uyuyor, testler yeşil, canlı koşu kendi referansıyla
bit düzeyinde tutuyor (sapma 0,0 bps). Bu bir **kalibrasyon ve karşılaştırılabilirlik
uyuşmazlığıdır**: iki ölçüm aynı adı taşıyor ama aynı aday kümesini taşımıyor. K-070 tipi
bir hata (kodun kendi docstring'ini uygulamaması) burada **yok**; o ayrı bir karardır ve bu
pencereyi etkilemediği aşağıda ölçüldü.

### Ölçülenler (2026-09-18)

1. **Risk katmanının elediği.** `evren-kiyas` koşusu salt okunur kopyadan yeniden üretildi
   (kayıtla bit düzeyinde aynı). Koşunun bugüne kadarki **tek** yeniden dengeleme kararında
   risk motoruna 10 hedef sunuldu, **2'si reddedildi**:

   | Sembol | `atr_oran` | Eşik | Sebep |
   | --- | ---: | ---: | --- |
   | NEARUSDT | 0,023765 | 0,020466 | `volatilite` |
   | ZECUSDT | 0,025989 | 0,020466 | `volatilite` |

   Sonuç: dondurulmuş 10 enstrümanlık hedef kümesi ileriye dönük gözlemde **8 enstrümana**
   düştü; brüt maruziyet hedef 0,20 yerine **0,1676**.

2. **Strateji katmanının elediği — ayrı mekanizma, karıştırılmamalı.**
   `evren-funding-basis` koşusunun `_aday_uyeler` çağrısı yeniden üretimde kayda alındı:
   50 üye → **41 aday**, 9 sembol dışlandı: BABYUSDT, ENAUSDT, MMTUSDT, PENGUUSDT,
   PLUMEUSDT, REUSDT, UNIUSDT, XLMUSDT, XPLUSDT. Bu, kayıtlı hipotezin **kendi tasarımıdır**
   (`dislama_orani = 0,2`) ve doğru çalışıyor; risk motorunun elemesiyle ilgisi yoktur. İki
   eleme aynı cümlede anılırsa hipotezin kendi filtresi bir kusur gibi okunur.

### Karar

1. **Mevcut gözlem penceresinde (2026-09-17 → 2026-09-25, K-069) hiçbir değişiklik
   yapılmaz.** Risk eşiği, aday evren, `hedef_brut`, `azami_agirlik`,
   `yeniden_dengele_bar`, evren üyeliği ve sembol listesi pencere kapanana kadar **olduğu
   gibi kalır**. Koşular durdurulmaz, host master'a senkronlanmaz, parametre değiştirilmez.
   Gerekçe: pencere bir dayanıklılık ölçümüdür; ortasında değişen bir parametre ölçümü ölçüm
   olmaktan çıkarır. (K-043'ün "planlı durdurma kesinti sayılmaz" istisnası bir kod
   güncellemesi içindir, bir deney ayarı için değil.)
2. **Pencerenin okunuşuna bir sınır cümlesi eklenir.** Bu pencere, dondurulmuş adayın değil,
   **adayın risk motorlu hâlinin** ileriye dönük gözlemidir. K-035 zaten gözlem modunun
   promotion kanıtı üretmediğini söylüyor; buraya eklenen, kıyaslanabilirlik sınırının da
   yazılı olması: pencere sonuçları Faz 12'nin kayıtlı ızgara sonuçlarıyla **doğrudan**
   karşılaştırılamaz.
3. **Kalibrasyon sorusu pencere sonrasına, ayrı bir ölçüm olarak bırakılır** (aşağıdaki
   bölüm). Bu ölçüm bir strateji çekilişi **değildir** — strateji koşulmaz, parametre
   seçilmez, ileriye dönük getiriye bakılmaz; yalnızca oynaklık dağılımı ölçülür —
   dolayısıyla Hipotez Defteri'ne çekiliş olarak yazılmaz. Ama eşiği **gevşetmek** (izin
   artıran yön) K-050'ye tabidir: sayısal kapı + elle onay ister ve sonuca bakılarak
   verilemez (K-033). Eşiği **sıkmak** aynı asimetride serbesttir.

### Pencere sonrası araştırma — soru ve ölçülecekler

> **Soru:** `RiskMotoru` volatilite eşiği, araştırma ve canlı gözlem arasında aynı aday
> kümesini koruyacak şekilde evren-geneli nasıl kalibre edilmelidir?

Ölçülecekler (bu kararla **tanımlandı**, uygulanmadı):

1. **Evrenin oynaklık dağılımı.** 50 üyeli gerçek araştırma evreninde ATR(14)/fiyat
   dağılımı; sembol başına ve havuzlanmış, `risk/kalibrasyon.py`nin `PERSENTILLER`
   ızgarasıyla (p50, p75, p90, p95, p99, p99.5, p99.9). Pencere ve evren kural kimliği
   (`27b7a16ed0ed`) rapora yazılır.
2. **BTC eşiğinin evrendeki karşılığı.** `0,020466` bu havuzlanmış dağılımın hangi
   persentiline denk geliyor? Tek sayı yeterli değil: sembol başına persentil de
   raporlanır, çünkü eşik kesitte **sembolleri birbirine karşı** eliyor.
3. **Aday eşiklerin eleme profili.** Evren-geneli p95, p99, p99.5 ve sembol-bazlı (her
   sembolün kendi p99'u) seçenekleri için: her birinin hangi sembolleri, kaç barda, hangi
   aylarda elediği. Sayı değil liste — "kaç tanesini eledi", bir eşiğin zararsız göründüğü
   ama hangi tarafı elediğini gizleyen ölçüdür.
4. **Risk filtresi öncesi/sonrası aday kümesi.** Aynı çekiliş `risk=None` ve
   `risk=RiskMotoru(...)` ile koşulur; her yeniden dengeleme barında hedef kümesi, onaylanan
   küme ve red sebepleri karşılaştırılır. Çıktı: kesişim oranı ve enstrüman bazında fark.
5. **Karar zincirinin aynılaştırılabilirliği.** Araştırma yolunun da risk motorlu koşması
   mümkün mü, mümkünse maliyeti ne: (a) Faz 1-4'ün risksiz referanslarının ve
   `sonuc_hash`lerinin bit düzeyinde korunması şart (K-057); (b) çekiliş sayısına ve ızgara
   koşu süresine etkisi; (c) `kapilar_v2` eşiklerinin yeniden kalibrasyonunu gerektirip
   gerektirmediği — eşikler ızgara şekline bağlı. Cevap "hayır" çıkarsa nedeni ölçüyle
   yazılır ve ikinci en iyi yol (gözlem sonuçlarının risksiz referansla birlikte
   raporlanması) tanımlanır.
6. **Kalibrasyon seçeneklerinin etkisi.** Her aday eşik için turnover, ortalama ve azami
   brüt maruziyet, eşzamanlı enstrüman sayısı dağılımı ve 11 kapının metrikleri. Bu ölçüm
   bir **seçim yapmaz**: eşik seçimi ayrı bir karardır (K-033 + K-050) ve sonuçlara
   bakılarak verilemez.

**Ölçüm önce, karar sonra.** Bu bölüm bir uygulama planı değil, bir ölçüm planıdır; K-073
kapsamında hiçbir eşik, ağırlık ya da maruziyet değeri değiştirilmemiştir.

### Açık kalem 1 — `hedef_brut = 0,2` ölçülmemiş bir varsayılandır

Pencerede ölçülen (2026-09-18, ilk 24 saat): başlangıç özkaynak 10.000, `evren-kiyas`
özkaynağı ≈10.088,81, nominal getiri ≈%0,89, brüt maruziyet ≈0,1676. Bu sayılar **bir
performans değerlendirmesi değildir** ve öyle yorumlanmaz: 24 saat, tek yeniden dengeleme,
gözlem modu.

Kaydedilen tek şey şu: nominal getirinin küçüklüğü stratejinin ölçülmüş bir zayıflığı değil,
`hedef_brut = 0,2` ayarının doğrudan sonucudur — sermayenin ≈%83'ü nakitte duruyor. Ve
`hedef_brut = 0,2` **ölçülmüş bir optimum değildir**; Faz 12 ızgarasından dondurulmuş bir
varsayılandır. K-072 aynı sayıya başka bir yönden değmişti ("brütü büyütmek ayrı bir
karardır ve sonuca bakılarak verilemez"); burada eklenen, sayının **hiç ölçülmemiş**
olduğunun açıkça deftere geçmesi. Ölçülmesi K-033'ün kalıbına tabidir (dağılım + gözden
geçirme koşulu) ve K-050'nin asimetrisine: brütü büyütmek izin artıran yöndür.

**Bu pencerede `hedef_brut` değiştirilmez.** Yatırılan sermaye üzerinden normalize edilmiş
getiri (≈%5,3/gün) yalnızca sermaye kullanımını açıklayan yardımcı bir sayıdır; stratejinin
performansı olarak raporlanmaz ve hiçbir kapıda kullanılmaz.

### Açık kalem 2 — bu pencerede ayırt edici kanıt oluşmadı

2026-09-18 15:00 UTC adımında `evren-funding-basis` ve `evren-makro-nfci` özkaynakları **bit
düzeyinde aynı**: `10088.42804712792`; pozisyonları da aynı. Ölçülen sebepler: (a)
funding/basis dışlaması 9 sembolü eliyor ama hiçbiri kote hacme göre ilk 10'da değil, yani
seçimi değiştirmiyor; (b) NFCI değeri −0,56, stres engeli tetiklenmiyor. `evren-kiyas`ın
küçük farkı ise stratejiden değil, bir saat önce başlamış olmasından (farklı giriş barı).

Bu **"strateji başarısız" demek değildir** ve öyle kaydedilmez. Kaydedilen: *mevcut gözlem
penceresinde bu iki koşu kıyastan ayırt edici kanıt üretmemiştir.* 25 Eylül'de pencere
kapanırken "adayı bir hafta ileriye dönük izledik" cümlesinin yanında bu satır da bulunmalı.

### Açık kalem 3 — RLUSDUSDT

Evren kuralının ürettiği listede bir stablecoin (RLUSDUSDT) var ve mevcut koşuda brüt
maruziyetin ≈1/8'ini tutuyor; yapısı gereği ≈sıfır getiri üretir. Evren kuralının stabil
taban listesinde olmadığı için bu bir **kural kusurudur**, bir piyasa gözlemi değil.
Araştırma tablosu aynı kuralla kurulduğu için **parite doğrudur**: canlı ile backtest aynı
listeyi görüyor.

**Pencere sırasında çıkarılmaz, sembolü değiştirilmez, ağırlığı elle düzeltilmez.** Kuralın
düzeltilmesi pencere sonrası bir program kaydının konusudur; koşu ortasında evreni
değiştirmek, K-052'nin "evren de geleceği göremez" kuralını bugünkü bilgiyle delmek olurdu.

### Yan doğrulama — host 17 commit geride, canlı yol etkilenmiyor (ölçüldü)

Host `3a74ebf`, master `06282e8`: **17 commit**. `src/` altında değişen 14 dosyadan canlı
yolu etkileyebilecek tek aday `strategy/kurma.py` (K-070). Diğer 13'ü eklemeli:
`features/indikator.py` (yeni `log_degisim`), `features/motor.py` (yeni konumlanma DEFTER
kayıtları), `cli/main.py` (yalnızca `lab tekrar-kontrol`), kalanı araştırma modülleri ve
koşan hiçbir konfigürasyonun kullanmadığı iki yeni strateji dosyası. `config/` ve
`migrations/` altında değişiklik **yok**.

K-070'in etkisizliği okunarak değil **ölçülerek** doğrulandı: eski (`3a74ebf`) ve yeni
`agirliklar()` fonksiyonları, koşuların gerçek ayarlarıyla (`hedef_brut = 0,2`,
`azami_agirlik = 0,02`, `esit_agirlik = True`) yan yana koşuldu.

| Vaka | Sonuç |
| --- | --- |
| `esit_agirlik=True`, n = 1…50, her n için 20 rastgele oynaklık dizisi (1.000 vaka) | **0 fark** |
| Koşunun fiili hâli: n = 8 ve n = 10 | aynı; brüt 0,160 / 0,200, azami ağırlık 0,020 = tavan |
| Kontrol: `esit_agirlik=False`, n = 3, tavan 0,05 (K-070'in vakası) | **fark var** — eski: 0,05 / 0,05 / **0,10** (tavanın iki katı), yeni: 0,05 / 0,05 / 0,05 |

Kontrol vakası hatanın gerçekten var olduğunu ve karşılaştırmanın boş geçmediğini
gösteriyor; canlı ayarda 1.000 vakada tek fark yok. **Karar: host güncellenmez, koşular
yeniden başlatılmaz, canlı pencereye dokunulmaz.** Güncelleme pencere kapandıktan sonra,
K-043'ün planlı durdurma yordamıyla yapılır.

## K-074 — Jev karar katmanı yalnızca gölgede ölçülür; K-067 değişmez; kesim tarihi bilinmiyor

**Durum:** kabul · **Tarih:** 2026-09-19 · **Onay:** Scryne (beş bağlayıcı karar, Jev denetimi
sonrası) · **Tabi:** K-067 (Jev sinyal üretmez — **aynen yürürlükte**), K-049 (AI yetkisi,
kesim, dondurma), K-039/K-051 (çekiliş sayımı, program bütçesi), K-045 (tek sembollü yönlü
arama kapalı), K-037 (izin veren katman risk dışında olamaz) · **Kaynak:** `docs/Jev-Denetim.md`
(repository ↔ `docs/Jev-Integration-Spec.md` denetimi), `docs/spikes/07-jev-durum.md`,
`config/jev.json`

**Bağlam.** Spec bir "Jev-style LLM decision layer" istiyor: yön, güven, rejim, kurulum
kalitesi üretsin; risk ve execution'a karışmasın; önce gölgede ölçülsün. Denetim, spec'in
bu projede üç kararla çarpıştığını buldu: K-067 Jev'den sinyal türetmeyi yasaklıyor
(spec'in "Jev only" / "Baseline + Jev" deneyleri); K-049/5 backtest içinde LLM çağrısını
yasaklıyor (spec'in replay'i); K-049/4 kesim öncesi türetimi kapıdan düşürüyor ve Jev'in
kesimi yayınlanmıyor (spec'in tarihsel isabet kanıtı). Bu karar üçünü de spec'i değil
**kararları** koruyarak çözüyor.

### Karar — sekiz madde

1. **Jev'in yönü bir ölçümdür, bir sinyal değil.** İlk ve tek kapsam **gölge**: kapanmış her
   `ok` 1h barda kanonik durum kurulur, Jev'e sorulur, cevap deftere yazılır, **başka hiçbir
   şey olmaz.** Jev çıktısı `Sinyal` üretmez, `Strateji`ye girmez, `PaperMotoru`/
   `EvrenPaperMotoru`'na girmez, `RiskMotoru`'na girmez, execution'a girmez, emir
   oluşturmaz. K-067'nin "ölçüm, özellik değil" istisnası kullanılıyor; K-067'nin kendisi
   **değişmiyor.** Spec'in B (Jev only), C (baseline + Jev onayı) ve D (Jev filtre)
   deneyleri **bu fazın dışındadır**; herhangi birini açmak yeni bir K-kaydı, K-051 program
   kaydı ve K-045 istisnasının sayısal gerekçesini ister.
2. **Yer ve yön.** Kod `src/scryne_quant/jev/` altında yaşar. Bağımlılık yönü tek:
   `data → features → live/pencere → jev`. `strategy`, `backtest`, `features`, `risk`,
   `execution`, `live` paketleri `jev`i ya da `typesafe`i import etmez
   (`test_islem_katmani_dedektoru_import_etmez` zaten zorluyor); `jev` paketi `risk`,
   `execution`, `oms`u import etmez (yeni AST testi). `JevKarari` `extra="forbid"`:
   miktar, fiyat, kaldıraç, stop, borsa eylemi alanı **yok** — `Sinyal`in tip düzeyi
   yasağının ikizi.
3. **Kesim tarihi UNKNOWN.** Spike 7(c): `/v1/models` yalnızca yayın tarihi veriyor
   (`jev-latest` → 2026-09-10T18:38:01Z); hiçbir doküman eğitim kesimi söylemiyor. Yayın
   tarihi kesim yerine **geçmez** (model yayından önce eğitilmiştir). Kural: kesim
   bilinmediği sürece geriye dönük **her** türetim `leak_riski=true` taşır ve hiçbir kapıya
   giremez; dondurulmuş tarihsel replay yalnızca boru hattı / şema / gecikme doğrulamasıdır.
   **İleriye dönük** gölge kararı — bar kapanışından sonra, `bayat_ms` (2 bar) içinde
   üretilen — kesimden bağımsızdır: model o anda gelecekteki fiyatı bilemez. Kayıt bunu
   `ileriye_donuk=true` ve `uretim_ms` ile taşır. TypeSafe'e resmi beyan sorulur; gelene
   kadar `config/jev.json::egitim_kesim_utc = null`, **uydurulmaz.**
4. **Kanonik durum betimleyicidir, hesap kodda.** Spike 7(b): Jev sayısal eşik kıyasında
   yanılıyor (zirveye %1,02 uzakken "%1'den yakın" → 0,86). Bu yüzden Jev'e dizi ya da
   eşik sorusu gitmez; indikatörler, yapı etiketleri, persentiller ve tazelik kodda
   hesaplanır ve etiket olarak gider. 4h bağlam 1h'den yalnızca **kapanmış** kovalarla
   toplanır (Spike 7(a): OHLC + trades Binance 4h ile bit düzeyinde aynı, hacim 1 ulp);
   ikinci akış yok; eksik kova `eksik`, uydurulmaz (K-024). Durum `durum_surumu`,
   `karar_ms` (bar açılışı), `veri_kesimi_ms` (bar kapanışı; funding için kendi
   `funding_time`), `durum_hash` (`nesne_hash`) taşır; aynı girdi aynı hash'i verir ve
   `t` sonrası veri **bozulunca ve silinince** JSON byte düzeyinde değişmez (test; negatif
   kontrol dahil).
5. **Fail-closed, ayrı süreç.** Gölge `sq jev golge` ile **ayrı süreçte** koşar; kendi
   deposu (`runs/jev/<kosu>.sqlite`, zincir hash), kendi timeout/retry'ı, kendi hata
   günlüğü. Timeout, API/kimlik hatası, şema hatası, çözülen model ≠ istenen, bayat durum,
   eksik kritik veri → **karar yok**: kayıt `GECERSIZ` + sebep, **önceki karar yeniden
   kullanılmaz**, ana yola (paper/live) hiçbir yan etki. Jev sürecinin ölmesi trading
   sürecini etkilemez; tersi de.
6. **Yeniden üretilebilirlik.** Model pinli (`jev-1.13.0`; çözülen ≠ istenen → GECERSIZ),
   soru seti `SORU_SHA256` ile donmuş ve testli (K-061 kalıbı), istek/yanıt hash'li. Karar
   `choice` değil **olasılık vektörü + kodda marj** ile etiketlenir (Spike 7(b): eşit
   olasılıkta argmax koşular arasında değişti); marj `config/jev.json`'da ve koşudan önce
   sabit. Her 24 kararda aynı durum ikinci kez sorulup sapma yazılır — izleme, kanıt değil.
7. **Sonuç tanımları önceden sabit** (`config/jev.json::sonuc`): giriş `open[t+1]` (K-004),
   ufuklar 1/4/24 bar, birincil 4; getiri, MAE, MFE, gidiş-dönüş maliyet; yön isabeti
   yalnız long/short kararlarda, flat çekimserliktir; güven kovaları yazılı. Gölge ölçümü
   **çekiliş değildir** (strateji koşmuyor, parametre seçilmiyor — K-068'in notu); soru
   setini, marjı ya da durum alanlarını **sonuca bakıp** değiştirmek yeni bir çekiliştir ve
   hipotez defterine satır ister (K-049/2). Başarısız sonuç silinmez, rapor edilir.
   "8 gün geçti" bir başarı ölçütü değildir; ölçüt bu tanımlardır.
8. **CI minimal.** `.github/workflows/test.yml`: `uv sync` + `uv run pytest` — mevcut takım
   ve Jev testleri (kanonik snapshot, byte-identical sızıntı, negatif sızıntı, şema/
   fail-closed) tek işte. Koruduğu invariant tek cümle: *aynı karar zamanı ve aynı PIT
   koşullarında kanonik durum gelecekten etkilenmez.*

### Neyi vaat etmiyor

- Jev'in isabetli olduğunu değil, isabetinin **ölçülebilir** olduğunu kuruyor.
- Gölge penceresi bittiğinde "Jev çalışıyor/çalışmıyor" ilanı yapılmaz; rapor yalnızca 7.
  maddedeki tanımlarla, örneklem büyüklüğü ve güven aralığıyla yazılır.
- OI, çoklu sembol, haber, makro kapsam dışı (K-051: yeni veri = yeni program).

### Geri dönüş koşulları

- TypeSafe kesim tarihini beyan ederse 3. madde ölçülebilir pencereye çevrilir; beyan
  `config/jev.json`'a kaynağıyla yazılır, önceki `leak_riski=true` kayıtları **yeniden
  etiketlenmez** (üretildikleri günkü bilgiyle kalır).
- Gölge raporu K-045'in istisna şartını sayısal olarak karşılarsa (Jev yönünün fiyat
  özelliklerinden bağımsızlığı **ve** in-sample'da ileriye dönük sıralama gücü, K-068) D
  deneyi için program kaydı açılabilir — yine bu kararın değil, yeni bir kararın konusu.

## K-075 — Yayın tarihi kesimin üst sınırıdır: yayından sonra açılan bar için replay kesimden bağımsızdır

**Durum:** kabul · **Tarih:** 2026-09-19 · **Onay:** Scryne ("beklemek istemiyorum, başka bir
çözüm bul") · **Tabi:** K-074/3 (kesim UNKNOWN, uydurulmaz — **aynen yürürlükte**), K-049/4,
K-067 (Jev sinyal üretmez — aynen) · **Kaynak:** `docs/spikes/07-jev-durum.md` (c),
`config/jev.json::yayin_utc`, `runs/jev/tekrar-yayin-sonrasi-1.sqlite`

**Bağlam.** K-074/3 doğru olarak "yayın tarihi kesim yerine geçmez; yayından önceki hiçbir
pencereyi temizlemez" dedi ve ileriye dönük gölgeyi tek kanıt yolu bıraktı. Bu, kanıtın
yalnız takvim hızında (24 karar/gün) birikmesi demekti. Gözden kaçan şey: aynı önerme
(**kesim ≤ yayın**, `ayarlar.py` bunu zaten zorluyor) yayından **sonraki** barlar için
kesimin ne olduğunu bilmeyi gereksiz kılar. Karar barı `karar_ms ≥ yayın_ms` ise
`karar_ms ≥ yayın ≥ kesim`; hangi kesim olursa olsun t sonrası fiyat eğitimde olamaz.
Bu bir tahmin değil, eşitsizlik.

### Karar

1. `_leak_riski`: kesim bilinmiyorsa `leak_riski = karar_ms < yayın_ms`. Yayından önceki
   bar için hiçbir şey değişmedi (`true`). Kesim biliniyorsa yayın yok sayılır (K-074/3
   aynen). Test: `TestLeakRiski::test_kesim_bilinmiyorsa_yayin_alt_sinirdir`.
2. Yayın sonrası replay (`jev-1.13.0` → 2026-09-10T18:38Z) ileriye dönük gölgeyle **aynı
   kanıt sınıfındadır**; `degerlendir` `kanit: true` verir. Ölçüm tanımları K-074/7'deki
   gibi, değişmedi. Marj 0,20 değişmedi.
3. **İlk ölçüm (aynı gün):** `tekrar-yayin-sonrasi-1`, BTCUSDT 1h, 219 bar
   (2026-09-10 19:00 → 2026-09-19 21:00 UTC), 219/219 geçerli, zincir geçerli, 1 dk 7 s.
   Çekimserlik **%96,3** (211 flat, 4 long, 4 short); sonucu bilinen yönlü 7, isabet **3/7**
   (CI %95 0,16–0,75); al-tut aynı barlarda 126/215. Yönlü net getiri 4 bar: −%0,30
   (maliyet sonrası negatif). Betimleyici (kapı değil): marj 0'a inse bile argmax yalnız
   32/219 yönlü — çekimserlik marjın değil, Jev'in kendi olasılık dağılımının sonucu
   (P_flat medyan 0,71).
4. **Ne değişmiyor:** Jev hâlâ sinyal üretmez; bu ölçüm bir strateji değil, K-045
   istisnasının sayısal ön koşulu. n=7 ile hiçbir şey söylenemez; bu kaydın değeri sonuçta
   değil, **kanıt hızında**: 9 günlük pencere takvimde 9 gün, replay'de 1 dakika.

### Sonraki adım (bu karar açmıyor, yalnız işaret ediyor)

Aynı pencere evrendeki diğer sembollere uygulanırsa yönlü örneklem takvim beklemeden
büyür (K-074 "çoklu sembol kapsam dışı" dediği için ayrı K-kaydı ister; saatler arası
kesitsel korelasyon nedeniyle etkin n sembol sayısıyla doğrusal büyümez — rapor bunu
ölçmek zorunda).

## K-076 — Jev yön ekseni kapandı: 50 sembol, yayın sonrası pencere, isabet %49,0

**Durum:** kabul · **Tarih:** 2026-09-19 · **Onay:** Scryne ("evet aç ve koştur") · **Tabi:**
K-067, K-074 (aynen), K-075 · **Kaynak:** `docs/Faz-16-Jev-Evren-Replay-Raporu.md`,
`runs/jev/evren/`

**Bağlam.** K-074 çoklu sembolü gölge kapsamı dışında bırakmıştı; K-075 yayın sonrası
replay'i gölgeyle aynı kanıt sınıfına aldı. İkisi birleşince BTC'nin 7 yönlü kararı yerine
aynı gün 1.099 yönlü karar ölçülebildi. Bu karar o kapsamı **tek seferlik ölçüm** olarak
açtı; strateji, program ya da çekiliş değil (Jev sinyal üretmiyor, parametre seçilmiyor).

### Karar

1. Ölçüm: PIT 2026-09 ilk 50 sembol × 197 bar, K-074 soru seti/marj/durum **değişmeden**.
   `sq jev tekrar --sembol` eklendi (config'i ezer, başka hiçbir şey değişmez).
2. Sonuç: isabet 539/1.099 = %49,0 (CI 0,46–0,52), net −%0,38/işlem (t ≈ −6,9), brüt
   negatif, kalibrasyon yok, saat-küme etkin n 183'te de %51. **K-045 istisnasının sayısal
   koşulu karşılanmadı. Jev'in yönü bilgi kaynağı değildir.**
3. Sonuçlar: Jev filtre/onay/only deneyleri (spec B/C/D) açılmaz; K-074'ün "geri dönüş
   koşulu" tetiklenmedi. Gölge `golge-1` açık kalır (ileriye dönük doğrulama, bedelsiz).
   Sembol seçimi yapılmadı (en iyi 5 sembol yazı-tura kuyruğunun içinde, rapor §2).
4. Değişmeyen: soru setini, durumu ya da timeframe'i değiştirip yeniden sormak yeni
   çekiliştir; deftere satır ve K-051 programı ister. Bu rapora bakarak yapılmaz.

## K-077 — Rejim-koşullu oracle tavanı yetersiz: Jev B/C/D/E açılmaz; selector/filter için headroom yok

**Durum:** kabul · **Tarih:** 2026-09-20 · **Onay:** Scryne (Faz 0 sonucu kabul) · **Tabi:**
K-045 (tavan), K-054 (kapılar), K-067/K-074/K-076 (Jev, aynen), K-068 (seçim/kurma) ·
**Kaynak:** `docs/Faz-16-Rejim-Tavan-Olcumu.md`, `tools/faz16_rejim_tavan.py`,
`runs/faz16/rejim_tavan.json`, Jev Strategy Discovery denetimi (audit + design, 2026-09-19)

**Bağlam.** Jev Strategy Discovery Engine denetimi "NOT READY" dedi ve tek ön koşul koydu:
Jev'e sorulmadan, deterministik olarak, rejim × aile oracle tavanının kapıyı geçtiği
gösterilsin. Ölçüldü.

### Karar

1. **Tavan yetersiz.** Her rejimde OOS'ta en iyi aileyi hindsight'la seçen, geçiş maliyeti
   ödemeyen oracle: birleşik OOS Sharpe en iyi grupta 0,60 (eşik 1,04); en kötü rejim
   Sharpe'ı en iyi grupta 0,52 (eşik 0,685); no-trade serbestliğiyle 0,59. Gözlenen en yüksek
   tekil rejim Sharpe'ı 0,87 — yaklaşımdan bağımsız üst sınır, eşik altı.
2. **Oracle promotion kanıtı değildir** ve öyle kullanılmayacak: seçim sonucu görerek
   yapıldı (in-sample), rejimler arası geçiş bedava sayıldı, sermaye tek. Bir tavan, kapıyı
   geçseydi bile yalnız "araştırmaya değer" derdi; geçmediği için hiçbir şey demez.
3. **Jev B/C/D/E açılmaz.** Kusursuz seçici bile kapı altındaysa kusurlu (K-076: yön %49)
   seçicinin yakalayacağı alan sıfırdır. Kayıt dili: **"Jev başarısız" değil, "mevcut alpha
   evreni üzerinde selector/filter için yeterli headroom yok."** K-067, K-074 aynen; gölge
   yalnız ileriye dönük doğrulama.
4. **K-045 ile aynı duvar, farklı açı.** K-045 maliyeti sıfırladı, geçen yok; bu ölçüm
   seçimi hindsight'a verdi, geçen yok. BTC 1h düşen rejimde 17 aileden sıfırı pozitif —
   seçim katmanının teorik azami katkısı (≈ +0,2 Sharpe) kapı boşluğunun (0,44) yarısından
   az. K-068 ("seçim genelleşmiyor, kurma genelleşiyor") tavan tarafından da doğrulandı.
5. **Yapılmayan:** backtest, Jev çağrısı, yeni rejim tanımı, çekiliş — defter 52'de, eşik
   değişmedi. Kalan dokuz kapı oracle serisi için hesaplanmadı (bar düzeyi getiri yok);
   belirleyici ikisi düştüğü için gerekmedi.

### Sonraki soru

Seçici değil, kaynak: "gate seviyesine ulaşabilecek yeni alpha edge nereden üretilebilir?"
Önce araştırma uzayı haritalanır (`docs/Alpha-Discovery-Gap-Audit.md`), sonra program
açılır (K-051). Bu karar hiçbir programı açmıyor.

## K-078 — Alpha Discovery Gap Audit ve iki Adım 0 ölçümü: Hat 2 kapandı, Hat 1 ikinci tavana uygun (bilgilendirici)

**Durum:** kabul (bilgilendirici; hiçbir kapsam, kapı ya da karar değişmedi) · **Tarih:**
2026-09-20 · **Onay:** Scryne · **Tabi:** K-045, K-053, K-068, K-077 (aynen); K-008, K-033,
K-046, K-057 (açılmadı) · **Kaynak:** `docs/Alpha-Discovery-Gap-Audit.md`,
`docs/Faz-16-Hat1-Carry-Tavan-Olcumu.md`, `docs/Faz-16-Hat2-Funding-Uzlasma-Olcumu.md`,
`tools/faz16_carry_tavan.py`, `tools/faz16_funding_uzlasma.py`, `runs/faz16/carry_tavan.json`,
`runs/faz16/funding_uzlasma.json`

### Kayıt

1. **Yapısal bulgu (korunur):** defterdeki 52 çekilişin 52'si long-only spot
   (`strategy/sinyal.py::Yon`, `target_exposure ≤ 1`). K-077'nin "düşen rejimde 17 aileden
   0 pozitif" sonucu alpha zayıflığı olarak *değil*, **mevcut eylem uzayının yapısal sınırı**
   olarak okunur. Fiyat geçmişinden türeyen yönlü TA / kesitsel / rejim / seçim / Jev hattı
   kapalıdır ve yeniden açılmaz. Açık uzaylar: eylem uzayı (short/vadeli bacak, delta-nötr
   carry) ve veri sınıfı (haber, on-chain, ikinci varlık sınıfı — veri yok).
2. **Hat 2 (funding uzlaşma anı mikroyapısı): CLOSE.** BTC 1m, IS 2023-08 → 2025-02, 1.688
   olay, önceki ödemenin işaretine koşullu; en iyi bacak +0,9 bps, maliyet 30,6 bps, net
   −29,7 bps; 32 üçlü plaseboda p = 0,156. Çapa/pencere/koşullama değiştirilerek tekrar
   ölçülmez (M-1 kuralı).
3. **Hat 1 (delta-nötr carry, ideal tavan): FURTHER-RESEARCH-ELIGIBLE — ekonomik edge
   değil.** Spot long + perp short, `r_t = funding_t − Δbasis_t`, maliyet/marjin/likidasyon
   sıfır, IS 2020-01 → 2025-02: BTC +%14,2/yıl Sharpe 9,5; havuz (28) +%13,8 / 6,6.
   Sayıların okunuşu: BTC ödemelerinin %42'si Binance faiz tabanı (0,01 %/8h = %10,95/yıl);
   Sharpe carry için yanlış risk ölçüsü (risk kuyrukta); 2022'de ETH 0,66, SOL −%38, BNB
   dört yıl negatif. Tavan yalnız **ikinci tavanın** (gerçekçi maliyet, marjin, fırsat
   maliyeti, stres) gerekçesidir; promotion kanıtı değildir ve öyle kullanılmayacaktır.
4. **Değişmeyen:** defter 52; eşik 1,04; spot kapsamı; K-008/K-033/K-046/K-057; Jev gölge
   yalnız ileriye dönük doğrulama. Program açılmadı; veri satın alma kararı yok.

## K-079 — Hat 1 ikinci tavanı: DATA BLOCKED — eksik katman (perp fee) + eksik sınıf (liquidation threshold); vadeli hesap açılmıyor

**Durum:** kabul (bilgilendirici — Hat 1'in mevcut metodolojik kapanış durumunun kalıcı kaydı;
yeni veri erişimi, yeni kapsam, yeni kapı ya da yeni yetki **açmaz**; yeni kural ve yeni K
bağımlılığı üretmez) · **Tarih:** 2026-09-20 · **Onay:** Scryne · **Tabi:** K-007, K-021,
K-045, K-049/4, K-054, K-058, K-066 (+Ek), K-077, K-078 · **Kaynak:** `docs/Faz-16-Hat1-Kapanis.md`,
`docs/Faz-16-Hat1-Ikinci-Tavan-Kismi-Raporu.md`, `docs/Faz-16-Hat1-Metodoloji-Denetimi.md`,
`docs/Faz-16-Hat1-Fee-MMR-Erisilebilirlik.md`, `docs/spikes/08-vadeli-tarife-kademe.md`

1. **Ölçülen:** ideal carry tavanı (K-078); perp slippage K-021 yöntemiyle BTC 7,11 / ETH
   9,11 bps (config'e yazılmadı); DTB3 benchmark (BEY, K-060 PIT); fee=0 maliyet **üst
   sınırı**; `r_excess` üst sınırı (L×b×H ızgarası, seçim yok); `basabas_fee_perp_bps`
   (**eşik**, gerçek fee değil: BTC L1/b0 H30 8 bps, H365 346 bps); beş stres sınıfı + kısmi
   execution; `stres_bozulma` **alt sınırı** (BTC H30 35,7 pp, H365 10,95 pp — IS yıllık; OOS
   toplam-getiri kapısıyla yalnız mertebe kıyası).
2. **Bloke:** perp taker fee ve MMR kademeleri — resmî sayfalar bot korumalı/JS, FAQ'lar
   oran/kademe vermiyor, imzalı uçlar `-2015`, `apiRestrictions` `enableFutures=false`, UI'da
   seçenek yok (FAQ 360002502072: vadeli hesap açılmadan üretilmiş anahtara verilemez).
   **Scryne: vadeli hesap açılmıyor** — bu, mevcut kararın kaydıdır; gelecekte zorunlu bir
   erişim yolu tanımlamaz. K-066 Ek'in erişim yolu bu anahtarla kapalı. Alternatif uç,
   spot→perp taşıma, güncel MMR'yi geçmişe uygulama, varsayım: yapılmaz.
3. **Sonuç:** `DATA BLOCKED — eksik katman (perp fee) + eksik sınıf (liquidation threshold)`.
   CLOSE/ELIGIBLE verilmedi; `gecici_maliyet_modeli` mutlak engeli; hiçbir sayı promotion
   kanıtı değil. Adım 0 durumu (K-078/3 FURTHER-RESEARCH-ELIGIBLE) eksik katmanla askıda.
4. **PIT:** fee/MMR ne zaman alınırsa alınsın kayıt tarihi PIT sınırıdır; 2020–2025 IS'e
   uygulanırsa `NON_PIT/leak_risk`, kapı dışı. PIT MMR EMPTY, NON_PIT MMR EMPTY.
5. **Kapsam:** BTC+ETH; havuz (2)–(4) yok, genellenmez. B-6 (havuz perp slippage) AÇMA —
   backlog, mevcut karar için gerekli değil. C-portfolio, mark boşluk günleri, DTB3'ün program
   sözlüğüne/host sözleşmesine dahil edilmesi: bağımsız backlog.
6. **Yeniden açılma:** doğrulanabilir taker fee + MMR kademeleri/bakım tutarı + PIT
   kapsamının açıkça belirlenmesi → `tools/faz16_hat1_ikinci_tavan_kismi.py` tam, `C-isolated`
   sayacı kayıt tarihinden ileriye, tasarım §10 kuralı; sonuç yine promotion değil. Bu
   koşullardan biri gerçekten sağlanmadan Hat 1 yeniden açılmaz.
7. **Değişmeyen:** `src/`, config, execution, spot kapsamı, K-008/K-033/K-046/K-057, defter 52,
   eşik 1,04, Jev gölge yalnız doğrulama.

## K-080 — Veri seti kimliği tarihe sabitlenir: `bitis_gun` ile geri sarım, kayıtta `veri_son_ms`

**Durum:** kabul · **Tarih:** 2026-09-20 · **Onay:** Scryne ("A / K-080 ONAY", denetim döngüsü
kapanışı) · **Tabi:** K-009, K-011, K-039, K-057/6 · **Kaynak:** `docs/audit/W3-Research-Backtest.md`
§6, `docs/audit/W6-Testing-CI.md` T3, `tests/unit/test_geri_sarim.py`, `docs/ROADMAP-RESET.md` R1(a)

### Bulgu (W3, 2026-09-20)

Veri seti kimliği dosyanın SHA-256'sı (K-009) ve OOS penceresi veri **sonuna** göreli
(`is_oos(n, …)`). Depo uzatılınca ikisi birden kayar. `data/market/BTCUSDT/1h.parquet`
2026-09-20 01:06'da 2026-09-19'a uzatıldı; sonuç: `sq lab dogrula` 16 tekrar-edilebilir kayıttan
**10'unu** "veri seti değişmiş" ile reddetti (kalan 6'sı K-057/6 hash algoritması değişimi —
ayrı kalem, R1(b)), defterdeki 52 kaydın 9 farklı `veri_sha256`'sının **hiçbiri** depoda
kalmadı, ve eşik yeniden ölçümü (`tools/faz12_coklu_test.py`, 45 çekiliş) `h51`'de "kaydırmasız
koşu kayıttaki OOS `sonuc_hash`'ini üretmedi" ile durdu. "Kayıttan yeniden üretilebilir"
iddiası o an **kanıtlanamıyordu**.

### Ölçülen

Depodaki barlar değişmemişti; yalnız **uzamıştı**. K-011'in deterministik yazıcısı aynı
barlardan aynı dosyayı üretir: bugünkü depo 2026-09-09 10:00 UTC sınırına kırpıldığında
(45.576 bar) 38 tek sembollü çekilişin `veri_sha256`'sı `e3adb02c…` **bayt düzeyinde** geri
geldi (`tests/unit/test_geri_sarim.py` modül başlığı; tarama `--geri-sar --veri-sonu
"2026-09-09 09:00"` ile kayıt yeniden üretildi, aşağıda "Kanıt").

### Karar

1. **Veri sonu sabitlenebilir.** `ArsivIndirici(bitis_gun=)` ve `TarihselIndirici(bitis_gun=)`
   (`sq data arsiv-indir --bitis-gun`, `sq data indir --bitis-gun`, `YYYY-MM-DD` UTC dahil): o
   günden sonraki dosya/bar indirilmez, depoda varsa **atılır**. Uzatmak da geri sarmak da aynı
   komut; arşiv deposunda sabit tarih `1h.kaynak.json::bitis_gun`te durur. Bitiş gününün ayı
   aylık katmandan alınmaz (ayı kesmek günlük katman ister).
2. **Depo kırpılabilir.** `ParquetDepo.kirp(sembol, tf, bitis_ms)`: ağsız geri sarım, aynı
   yazıcı, bayt-aynı; kırpılacak bar yoksa dosyaya dokunmaz; depoyu boşaltacak kırpma hata.
3. **Kayıt geri sarma adresi taşır.** `Deney.kimlik.veri_son_ms` ve `Hipotez.veri_son_ms`
   (defter satırı): verinin son barının açılışı. **Kimliğe girmez** — `veri_sha256` veriyi
   zaten tanımlıyor; bu alan o veriye dönmenin adresi. Eski kayıtlarda yok (`null`), defter
   append-only olduğu için geriye yazılmaz.
4. **`sq lab dogrula --geri-sar`.** Veri hash'i uyuşmazsa depoyu kaydın `veri_son_ms`ine
   (K-080 öncesi kayıt için `--veri-sonu 'YYYY-MM-DD HH:MM'`) kırpar ve hash'i **yeniden**
   karşılaştırır; geri sarım hash'i geri getirmediyse red aynen kalır — kırpma tahmin değil,
   ölçüm. Kırpma depodaki sonraki barları atar (`sq data indir` geri getirir); bu yüzden
   bayrak açık, varsayılan değil.
5. **Kapsam dışı (bilerek):** funding/makro/PIT depoları (ayrı kimlik; `_veri_kimligi`
   bileşik hash'i onlar uzadıysa yine reddeder — doğru davranış); evren tanımı dosyası;
   K-057/6 hash algoritması değişiminden kalan 6 kayıt (R1(b): yenilenir, etiketlenir); risk/
   execution/OMS/Jev katmanları.

### Kanıt

`tests/unit/test_geri_sarim.py` (20 test): depo kırpma bayt-aynı; REST ve arşiv için
"uzat → sabitle" ≡ "baştan sabit" (bayt), sabiti kaldırmak eski dosyayı geri veriyor, geri
sarım ağ kullanmıyor; `sq lab tara` kaydı `veri_son_ms` taşıyor; uzatılmış depoda `dogrula`
reddediyor, `--geri-sar` ile yeniden üretiliyor ve depo hash'i kayda dönüyor; adressiz eski
kayıt reddediliyor, `--veri-sonu` ile sarılıyor; yanlış adres red'i kaldırmıyor; `veri_son_ms`
defter kimliğini değiştirmiyor.

**Gerçek depo (2026-09-20, `data/market` kopyası üzerinde, ana depo dokunulmadı):**
`sq lab dogrula --geri-sar --veri-sonu "2026-09-09 09:00"` dört e3adb-dönemi kayıtta depoyu
45.576 bara kırptı ve **veri hash'i dördünde de geri geldi** (`e3adb02c…`). Çıktı hash'i
dördünde de uyuşmadı; alan alan karşılaştırma (`tekrar.tekrar_uret` çıktısı ↔ kayıt):
- `tarama` ×2 (`4353f031`, `895715401b`): **yalnız** `sonuc_hash` alanları farklı (13 / 37);
  getiri, Sharpe, işlem, drawdown, parametreler birebir — Faz 10 §3'ün K-057/6 bulgusu
  (atlama sayacı listesi), veri sorunu değil.
- `karsilastirma` (`96889713`): 158 fark; `kiyas/in_sample/*` (al-tut) metrikleri değişmiş ve
  kayıtta olmayan yeni alanlar var (`cvar_95`) — kayıt 2026-09-09'dan, kod o günden beri
  metrik ekledi ve kıyas semantiği değişti (K-070/K-072 dönemi). **Kod sürümü** sorunu:
  bugünkü kodla yeniden üretilemez; kaydın `commit`i DIRTY olduğu için eski ağaç da tam
  değil.
- `degerlendirme` (`51c76510`): veri hash'i geri geldi, çıktı uyuşmadı (`karsilastirma` ile
  aynı sınıf — kıyas ve metrik alanları; kayıt 2026-09-09, commit DIRTY).
Sonuç: K-080 **veri kimliği** yarısını kapatıyor; **kod/hash sürümü** yarısı R1(b)'nin işi
ve iki alt sınıfa ayrılıyor: (i) yalnız `sonuc_hash` (K-057/6) — kayıt "hash algoritması
değişti" etiketiyle yenilenir; (ii) metrik/semantik drift — kayıt tarihsel kalır, "bugünkü
kodla yeniden üretilemez, commit DIRTY" etiketi alır. İkisi de sessiz değil, adıyla yazılı.

### Değişmeyen

`sonuc_hash` tanımı, `veri_sha256`'nın anlamı, defterdeki 52 satır, eşik 1,04 (yeniden ölçüm
R1(c)), OOS penceresinin veri sonuna göreli tanımı (**bilinçli**: değiştirmek her kaydı
yeniden üretilemez yapardı; sabit tarih bunu gereksiz kılıyor).

## K-081 — Eşik yeniden ölçümü (45 çekiliş): sabit 1,04 korunur, fotoğraf 45, bekçi defteri sayar, veri ileri sarılır

**Durum:** kabul · **Tarih:** 2026-09-20 · **Onay:** Scryne ("R1(d) kararlarını onaylıyorum", D1–D4)
· **Tabi:** K-039, K-044, K-050, K-064, K-071, K-080 · **Kaynak:**
`docs/research/records/2026-09-20-R1c-esik-yeniden-olcumu.md` (ölçüm),
`docs/research/records/2026-09-20-R1d-karar-maddeleri.md` (maddeler), `docs/research/coklu-test-olcum.json`
(fotoğraf), `runs/faz12/coklu-test-birlesik-500-0.json` (ham, git dışı)

### Ölçüm (değiştirilmedi, yeniden koşulmadı)

`tools/faz12_coklu_test.py --deneme 500 --seed 0`, kod `209ff2a` (temiz), veri sonu
2026-09-14 23:00 UTC (K-080 ile sabitlenmiş `data/evren`), 45 ölçülebilir çekiliş (31 tek
sembollü + 14 evren; defter 52, ölçülemeyen 7'si 1d), 43 çekilişlik önbellek aynen, h51/h52
500/500. Null maksimumu %5 sınırı **1,004** (%90 GA 0,982–1,064); sabit 1,04'ün ölçülen
yanlış-pozitifi **%4,2** (hedef %5). Engel ve A kararı (ölçülemeyen oynaklık = aday değil,
`oynaklik_olculebilir`, h51/h52 hash'leri aynı) R1(c) kaydında.

### Karar

1. **D1 — `COKLU_TEST_CEKILIS_SAYISI = 45`.** R1(c) 45 çekiliş kullandı ve kimlikleri
   defterle birebir; 43 artık ölçüm kapsamını temsil etmiyor. Bu sayı **eşik değil**, eşiğin
   ölçüldüğü defter fotoğrafıdır; testteki ikinci elle-tutulan kopya (`OLCULEN_CEKILIS`)
   kaldırıldı, sabit git'teki fotoğrafla karşılaştırılır.
2. **D2 — `COKLU_TEST_ESIGI = 1.04` korunur.** Gerekçe: R1(c) %5 sınırı ≈ 1,004; GA
   0,982–1,064 mevcut 1,04'ü kapsıyor; mevcut eşikte ölçülen FP ≈ %4,2, hedef %5; 52
   çekilişin hiçbiri ne 1,004'ü ne 1,04'ü aşıyor. Bu nedenle **mevcut politika eşiğinin
   korunması** tercih edildi. 1,004 bir ölçüm değeridir, config/politika eşiği **yapılmadı**;
   1,064 de uygulanmadı. Bu "1,04 matematiksel olarak optimaldir" demek değildir.
3. **D3 — Bekçi defteri sayar.** Kaynak gerçeklik `docs/research/coklu-test-olcum.json`
   (ölçüm aracının `--birlestir` sonunda git'e yazdığı fotoğraf: ölçülen/ölçülemez kimlikler,
   defter satır sayısı ve dosya SHA-256'sı, %5 sınırı) + `docs/Hipotez-Defteri.jsonl`. Testler
   (`test_coklu_test.py::TestEsigiDefteBagla`): sabit = fotoğraf; defter uzunluğu ve hash'i =
   fotoğraf; ölçülen ∪ ölçülemez = defter; ölçülen %5 ≤ sabit (K-050: gevşek kapı olamaz);
   gitignore'daki ham çıktı varsa fotoğrafla uyuşmalı, yoksa **görünür skip**. Defter bir satır
   büyürse CI kırmızı: yeniden ölçüm ya da bilinçli karar. Elle tutulan fotoğraf sabiti yok;
   `COKLU_TEST_DEFTER_SAYISI` ayrı bir sabit olarak **konulmadı** — defter sayısı fotoğraftan.
4. **D4 — Ölçüm kimliği korunur, deploy verisi ileri sarılır.** R1(c) kaydındaki veri sonu
   (2026-09-14 23:00 UTC) değişmez. 50 sembolün 09-18 hâli `runs/yedek/evren50-2026-09-18/`e
   (git dışı, proje içi) taşındı; arşivden `--bitis-gun 2026-09-18` ile yeniden üretim
   **50/50 parquet SHA-256 aynı** (`_arsivden-yeniden-uretim-sha256.txt`) — K-080'in "uzatmak
   da geri sarmak da aynı komut, bayt-aynı" iddiasının gerçek depo kanıtı. Ancak bundan sonra
   `data/evren` (734 sembol) güncel arşiv sonuna uzatıldı: **2026-09-19 23:00 UTC** (482 aktif
   sembol; delist edilenler kendi son barında), 2.410 dosya, 0 hata
   (`runs/yedek/evren-ileri-sarma-2026-09-20.{json,log}`); ölçüm hâline `--bitis-gun 2026-09-14`
   ile dönülür.

### Değişmeyen

`COKLU_TEST_ESIGI` 1,04; defter 52; R1(c) ölçüm artefaktları; strateji/risk/execution kodu.

## K-082 — Promotion kaydı zincir hash'li ve audit'e bağlı; canlı/paper açılışı bütünlük ister

**Durum:** kabul · **Tarih:** 2026-09-20 · **Onay:** Scryne (İz A P1/P2 talimatı) · **Tabi:**
K-008/5, K-010, K-032, K-035, K-038, K-050 · **Kaynak:** `docs/audit/W2-Risk-Execution.md` B4,
`docs/audit/IzA-CI-Kill-Promotion-Denetim.md` §3, `tests/unit/test_promotion_zinciri.py`

### Bulgu

`runs/promotion/<strateji>.json` düz JSON'du: satırlar arası hash yok, `yaz()` dosyayı baştan
yazıyordu; `live/baslat.py` aşamaları buradan okuyup `RiskMotoru`'na veriyor ve `MOD_ESIGI["live"]`
üçüncü adımda buna bakıyordu. `"asama": "live"` yazan biri (ya da bir hata) canlı modda
promotion kapısını geçerdi. `risk/audit.py`de zincir kalıbı ve `OlayTuru.PROMOTION` tanımlıydı
ama promotion olayları audit'e hiç yazılmıyordu.

### Karar

1. **P1 — kayıt zinciri.** `PromotionKaydi.gecmis`in her satırı `onceki_hash` + `satir_hash`
   taşır. Kanonikleştirme `nesne_hash` (sort_keys, ensure_ascii=False, ayırıcısız) — audit ile
   aynı; hash'e giren içerik = satır **eksi** `{onceki_hash, satir_hash, audit_hash}`, artı
   stratejinin adı ve öncekinin hash'i; ilk satırın öncekisi `KOK_HASH` (audit ile ortak sabit).
   `yukle()` zinciri baştan doğrular ve `asama == son geçilen satırın aşaması` ister. Eksik/
   değiştirilmiş/yeniden sıralanmış satır, zincirsiz (K-082 öncesi) biçim, aşama uyuşmazlığı,
   başka stratejiye taşınmış zincir → `PromotionHatasi`, **fail closed**. Sessiz geriye uyum
   **yok**: eski kayıt `sq promotion zincirle <strateji>` ile açıkça göç ettirilir (içerik
   değişmez, hash'ler eklenir, satırlar audit'e `goc=true` ile yazılır).
2. **P2 — audit bağı.** Her promotion satırı (ilerleme, başarısız deneme, elle onay) global
   audit defterine (`runs/audit.sqlite`, `OlayTuru.PROMOTION`, `sembol=""`, `zaman_ms` = satırın
   zamanı) yazılır; audit satırının zincir hash'i promotion satırına `audit_hash` olarak döner,
   audit gövdesi promotion `satir_hash`ini taşır (iki yönlü referans). Sıra: **önce audit, sonra
   dosya** — arada ölen süreç audit'te olan/dosyada olmayan satır bırakır ve bu "kısaltılmış
   dosya" olarak yakalanır; tersi sessiz olurdu. İkinci audit sistemi yok; koşu deposundaki
   audit değil **global** dosya, çünkü promotion koşudan bağımsız.
3. **Fail-closed sınırı moda bağlı** (`live/baslat.py::_promotion_asamalari`). `paper`/`live`
   (`MOD_ESIGI` ≠ `YOK`) promotion'a **dayanır**: her kayıt zincir + audit çapraz doğrulamasından
   geçmeden ve global audit verilmeden koşu **açılmaz**. `gozlem`/`backtest` promotion'a bakmaz
   (K-035): bozuk ya da eski kayıt koşuyu durdurmaz, `PROMOTION_OKUNAMADI` olayı günlüğe düşer,
   aşama `YOK` sayılır (bu modlarda eşik zaten `YOK` — gevşeme yok). Araştırma
   (`RiskMotoru(mod="backtest")`) promotion dosyasına hiç dokunmaz.
4. **Bilinen sınır:** son satırların silinmesi dosya içinden fark edilemez (zincir tutarlı
   kalır); audit çapraz kontrolü yakalar. Dosyanın sahibi audit'i ve dosyayı birlikte baştan
   yazabilir — audit.py'nin kendi sınırıyla aynı: sessiz kurcalama imkânsız, kasıtlı değil.

### Göç

`runs/promotion/sma_kesisim.json` (3 satır, `kalite_kontrol`, 2026-09-10) K-082 öncesi biçimdeydi ve
uygulama commit'inde **yeniden yazılmadı**; göç Scryne'ın kararıyla **2026-09-20'de yapıldı**
(`sq promotion zincirle sma_kesisim`, gerçek `runs/audit.sqlite` ile): SHA `cbd7072c…` →
`05201944…`, satır sayısı 3→3, `zaman_ms/asama/gecti/gerekce/onceki_asama/kanit` birebir, eklenen
yalnız `onceki_hash/satir_hash/audit_hash`; `satir_hash`ler kopya üzerindeki ön doğrulamayla aynı
(`940a5846, 067bf900, e34640bd` — deterministik); audit 1.091 → 1.094 satır (3 `promotion`,
`goc=true`), audit zinciri sağlam; promotion+audit çapraz doğrulama geçti. Göç öncesi dosya ve
audit kopyası `runs/yedek/promotion-goc-2026-09-20/`. Gözlem koşuları (host-1) etkilenmedi.

### Kanıt

`tests/unit/test_promotion_zinciri.py` (28): zincir kuruluşu ve kanoniklik; 8 fail-closed vakası;
audit iki yönlü referans, yalnız yeni satırların eklenmesi, audit'siz/başka-audit/bozuk-audit
redleri, kısaltma; göç (içerik birebir, `goc=true`, ikinci göç red); açılış sınırı (gözlem açılır +
olay, paper bozuk/audit'siz/karşılıksız açılmaz, doğrulanmış açılır, backtest dokunmaz); CLI
`zincirle`/`durum`/`onayla`. Mevcut `test_promotion.py` (34) ve `test_risk_bypass.py` aynen geçiyor.

---

## K-083 — Enstrüman v2: sözleşme alanları kimlikten ayrıştırıldı; U13/U15/U16/U17 çok varlık değişmezleri

**Durum:** kabul · **Tarih:** 2026-09-20 (Paket 1, taslak) → **2026-09-21 kabul** (Decision Memo) ·
**Onay:** Scryne (R2 Paket 1 talimatı; U13/U15/U16/U17 Decision Gate onayı, 2026-09-21) ·
**Tabi:** K-007, K-009, K-039, K-052, K-057/6, K-079, K-080, K-081 · **Kaynak:** `docs/ROADMAP-RESET.md` R2,
`docs/audit/W1-Architecture.md` §6, `docs/research/Threshold-Policy.md` §1 (U13-U17) ve §3,
`tests/unit/test_enstruman_v2.py`, `tests/unit/test_takvim.py`

### Bulgu

`Enstruman` (`data/kimlik.py`) yalnız kimlik taşıyordu: `kanonik_id, venue, sembol, geçerlilik,
bar_sayisi, kirilma_ile_basladi`. Varlık sınıfı, enstrüman tipi, takvim, tick/lot/kontrat, maliyet ve
finansman modeli için alan yoktu (W1 §6). Threshold-Policy §1 beş çok-varlık değişmezini (U13-U17)
`DECISION REQUIRED` olarak listeliyor; hiçbiri K olarak yazılmamıştı.

### Uygulandı ve ölçüldü (bu paket — karar değil, kayıt)

1. `Enstruman`'a sekiz varsayılanlı alan eklendi: `asset_class="kripto"`, `instrument_type="spot"`,
   `takvim_id="24x7"`, `tick_size=None`, `lot_size=None`, `contract_size=None`,
   `maliyet_modeli_id="global"`, `finansman_modeli_id=None`. Varsayılanlar bugün depoda olan **tek**
   gerçeği kodlar (Binance spot kripto, 7/24, `config/maliyet.json`'daki tek model, finansman yok).
   `kimlikleri_kur` yalnız v1 alanlarını doldurur; v2 alanları varsayılanda kalır.
2. `tick_size/lot_size/contract_size` **`None`**: bu katmanda güvenilir kaynak yok (arşiv verisi
   taşımıyor; `SembolKurallari` borsadan canlı okunuyor ve bağlanmadı). Uydurma sayı yazılmadı;
   verilirse pozitif olmak zorunda (`bool` ve 0 reddedilir).
3. `instrument_type` kapalı küme: `("spot", "vadeli", "cfd", "etf")`; başka değer `KimlikHatasi`.
   `asset_class` ayrı eksen ve bugün yalnız `{"kripto"}` — yeni sınıf eklemek koda dokunmak demek
   (bilerek: sınıf "kodda geçiyor" diye desteklenmiş sayılmaz). Tipler kimlik düzeyinde ayrı
   enstrümandır (`spot ≠ vadeli ≠ cfd ≠ etf`, testli); **çalışır değil** — execution/backtest
   desteği yok, bu paket onu iddia etmiyor.
4. **Kanonik kimlik değişmedi:** `<venue>:<ticker>@<tarih>`. Tip/sınıf kimliğe girmiyor.
5. **Serileştirme:** `Enstruman.sozluk()` v1'in 9 anahtarını aynı sırada ve aynı değerle verir
   (altın `nesne_hash` `4cd3052c…`, HEAD `dbe29ba`'da ölçüldü), ardından 8 v2 anahtarı. Gerçek
   katalog (`data/evren/_evren/kimlik-katalogu.json`, 761 kayıt) v2 modeliyle yeniden
   serileştirildi: v1 alt kümesi eski dosyayla **bayt-aynı**, iki üretim bayt-aynı, eklenen
   anahtarlar tam v2 kümesi, 761 kayıtta v2 değerleri aynı varsayılan. Katalog dosyası yeniden
   **yazılmadı** (veri yenileme kapsam dışı); bir sonraki `sq evren tablo` 8 anahtar ekleyecek —
   bu **beklenen şema değişimi**, "eski katalog bayt-aynı kalmalı" diye bir değişmez yok.
6. **Hash sınırı:** v2 alanları `sonuc_hash`, `config_hash`, `tablo_hash`, deney `girdi/cikti_hash`
   ve `_maliyet_govdesi()`'ne girmiyor. Statik: `backtest/sonuc.py`, `research/deney.py`,
   `common/hash.py`, `common/maliyet.py`, `research/tekrar.py` `data/kimlik`i import etmiyor ve
   v2 adlarını anmıyor. Davranışsal: v1 ve v2-açık kimliklerle `evren_tablosu` → `tablo_hash` ve
   `uyelik_matrisi` eşit. `_maliyet_govdesi(yukle("config/maliyet.json"))` kanonik SHA-256
   `fe9f73bb…` ve `MaliyetModeli.sozluk()` `nesne_hash` `5022dec9…` testte sabit — bunlar deney
   `girdi_hash`ine giriyor; değişmesi R1(b) kayıtlarını `semantik`e düşürür.
7. **R1(b) regresyonu:** `tools/r1b_kayit_durumu.py` `--tip monte_carlo|stres|tarama` (9 kayıt)
   değişiklik öncesi/sonrası birebir: `monte_carlo` 1 `ayni`; `stres` 1 `ayni`; `tarama` 3
   `yalniz_sonuc_hash` (fark 13/37/16) + 3 `ayni` (R1(b) yenilenmiş) + 1 `veri_geri_getirilemedi`;
   kayıt başına sınıf, `fark_sayisi` ve fark listesi aynı. `degerlendirme` tipi (10 `semantik`,
   ≈600 s/kayıt) bu ölçüme alınmadı: sınıfı zaten `semantik`, bu paketin değişmezine girmiyor.
   Tam test: 1.930 → 1.980 geçti (+50 = yeni dosya), 1 skip, 3 deselected; `ruff` temiz.

### Uygulandı ve ölçüldü — Paket 2 (2026-09-21)

1. **U13:** `kanonik_kimlik(venue, tip, sembol, tarih)` (`data/kimlik.py`); `kimlikleri_kur(...,
   instrument_type="spot")`; `Enstruman.__post_init__` kimliği alanlardan türetip karşılaştırır
   (tutarsız → `KimlikHatasi`), `VENUE_TIPLERI={"binance-spot": "spot"}` ile venue/tip
   tutarsızlığını reddeder. Spot kodlaması bayt-aynı: gerçek depodan PIT tablosu **yeniden
   üretildi** → `tablo_hash` `b06857c0…` (meta ile aynı), 761 kimlik, v1 katalog alt kümesi
   hash'i ve kimlik listesi öncesi/sonrası aynı; kural kimliği `27b7a16ed0ed…` aynı; 14 evren
   çekilişinin `veri_sha256` girdileri (tablo_hash + kural + pencere + sembol sha) değişmedi.
2. **U15:** `data/takvim.py` — `Takvim(kimlik, surekli, surum, aciklama)`, `KATALOG={"24x7"}`,
   `izgara()` = `np.arange` (eleman-eleman `ortak_izgara` ile aynı, 4 timeframe),
   `beklenen_bar()` = `dogrulama` formülü (boşluklu seride sayı sayıya), `icerik_hash`
   deterministik; seanslı takvim kurucuda reddedilir. Hiçbir çağıran bağlanmadı (R4).
3. **U16:** `depo.py`/`deney.py`/`sonuc.py`/`hash.py`/`izgara.py`/`dogrulama.py`/`metrikler.py`
   `takvim` import etmiyor (AST testi); `ParquetDepo.kirp` imzası `(sembol, timeframe, bitis_ms)`;
   `veri_son_ms` kimliğe girmiyor (`test_geri_sarim`, değişmedi). `_maliyet_govdesi` SHA
   `fe9f73bb…`, `MaliyetModeli.sozluk()` hash `5022dec9…` aynı; R1(b) 9 kayıt (monte_carlo/stres/
   tarama) sınıf + fark listesi birebir.
4. **U17:** `__post_init__`: `vadeli`/`cfd` → `finansman_modeli_id` zorunlu; `spot`/`etf` →
   `contract_size` dolu olamaz; `maliyet_modeli_id="global"` yalnız `binance_spot_kripto`.
   `Enstruman.islem_icin_dogrula()` (fail closed: tick/lot her tipte, contract finansmanlıda) —
   **çağrı noktası bağlanmadı** (paper/live yolu `Enstruman` görmüyor; İz G, K-046 kalıbı).
   `EvrenKurali(venue, instrument_type)`: sözlüğe/kimliğe yalnız Binance spot dışında girer;
   gerçek kural literal testi `27b7a16ed0ed…`; aynı sembollerle vadeli evren farklı kimlik;
   `EvrenKurali(**sozluk)` gidiş-dönüş.
5. Testler: `test_enstruman_v2.py` 71 → 102, `test_takvim.py` 20 (yeni); `test_izgara.py`
   fixture'ı kanonik kimliğe uyarlandı (`binance:AAA:1` biçimi artık geçersiz — davranış değil,
   fixture). Tam suite 2.001 → 2.052 geçti, 1 skip, 3 deselected; ruff temiz.

### Kararlar — KABUL (2026-09-21, Scryne; Decision Memo sonrası)

Kanıt zinciri (U13 kodlamasının belirleyicisi): `kanonik_id` → PIT tablo sütunu → `tablo_hash`
(`data/evren.py`) → `evren_degerlendirme.veri_kimligi` → defterdeki **14 evren çekilişinin**
`veri_sha256`sı (hepsi kural `27b7a16ed0ed…`, 5 farklı veri kimliği). Kodlama değişseydi aynı veri
+ aynı kural yeni hipotez görünür (K-039) ve K-081 bekçisi kırılırdı. `sonuc_hash`/`config_hash`/
deney kimliği/tek-sembol hipotez kimliği `kanonik_id`yi **görmüyor** (ölçüldü, 2026-09-21).

**U13 — kabul.** Kanonik kimlik `(venue, instrument_type, sembol, geçerlilik)`in fonksiyonudur.
Kodlama: `spot` → `<venue>:<TICKER>@<tarih>` (**mevcut, değişmez**); spot dışı →
`<venue>:<tip>:<TICKER>@<tarih>`. Aynı venue + sembol + tarih farklı tiple **farklı `kanonik_id`**
zorunlu (`Enstruman.__post_init__` kimliği alanlardan türetip karşılaştırır; uyumsuz kimlik red).
`kimlikleri_kur()` `instrument_type` alır (varsayılan `spot`). Venue/tip tutarsızlığı reddedilir
(`binance-spot` + `vadeli` → `KimlikHatasi`; bilinen venue'lerin tipi `VENUE_TIPLERI`). Spot dışı
veri ayrı depo kökünde tutulur (`data/evren/` yalnız Binance spot; `data/turev/` zaten ayrı).
Korunanlar: 761 spot kimlik, PIT tablo/`tablo_hash` `b06857c0…`, 14 çekilişin `veri_sha256`sı.

**U14 — bu kararda uygulanmaz.** R2 Paket 3. Enstrüman-başı `MaliyetModeli` ve `_maliyet_govdesi`
değişikliği ayrı K ile (sabit `fe9f73bb…` bilerek değişir, istemeden değil).

**U15 — kabul.** Takvim kod içi, sürümlü ve içerik-hash'li bir katalog soyutlamasıdır
(`data/takvim.py`); minimum arayüz `izgara(baslangic_ms, bitis_ms, timeframe) -> int64[]` ve
`beklenen_bar(ilk_ms, son_ms, timeframe) -> int`. R2 Paket 2'de yalnız `24x7` uygulanır ve mevcut
davranışla **bit-aynı** olmak zorundadır (`np.arange` ızgarası, `dogrulama.beklenen_bar` formülü).
Kripto-dışı gerçek takvim içeriği R3 gerçek veri spike'ı olmadan tanımlanmaz. Sağlayıcı
metadata'sı tek başına kanonik takvim kaynağı değildir. `gap`/kırılma/`bar_yili`/canlı bayatlık
takvime **R4'te** bağlanır; Paket 2 yalnız seam.

**U16 — kabul.** K-080 yürürlüktedir. `veri_son_ms` kimlik **değildir**, geri sarma adresidir
(`deney.py`). Takvim veri sonunu değil beklenen ızgarayı belirler; `ParquetDepo.kirp` bar zamanıyla
keser, takvimsiz kalır. `24x7` dışı takvim ileride deney girdisine `{"takvim": {id, icerik_hash}}`
ile girer — **yalnız `24x7` değilse** (`risk`/`evren` bloğu kalıbı) — böylece mevcut kayıtların
`girdi_hash`/`sonuc_hash`i Paket 2 nedeniyle değişmez (ölçüldü: R1(b) 9 kayıt birebir).

**U17 — kabul.** Binance spot kripto dışı enstrümanlarda alanlar açıkça sağlanır:
`asset_class`, `instrument_type`, `takvim_id`, `maliyet_modeli_id` zorunlu (`global` yasak);
`finansman_modeli_id` `vadeli`/`cfd`de zorunlu, `spot`/`etf`te `None` olabilir; `tick_size`,
`lot_size`, `contract_size`: `None` = **bilinmiyor** — araştırmada izinli, paper/live'da gerekli alan
`None` ise **reddedilir** (`Enstruman.islem_icin_dogrula()`, fail closed); `contract_size` yalnız
`vadeli`/`cfd`de anlamlı, `spot`/`etf`te dolu olması red. Evren kuralı `venue` + `instrument_type`
taşır (sözlüğe/kimliğe **yalnız Binance spot dışında** girer → `27b7a16ed0ed…` korunur; bir evren tek
tip). Yeni `(venue, instrument_type, takvim)` kombinasyonu yeni null kalibrasyonu gerektirir; 1,04
ve `kapilar_v2` sabitleri otomatik taşınmaz (`esikler.json` R5'te sınıf anahtarlı).

**Açık kalan (K değil, TODO) — 2026-09-21'de K-085 ile kapandı:** paper/live kurulum yolunda
`islem_icin_dogrula()` çağrısı — bugün o yol `Enstruman` nesnesi görmüyor (`SembolKurallari` + PIT sembol listesiyle çalışıyor); bağlama İz G
(`--mod paper` kurulumu) paketinde, K-046 kalıbıyla.

### Kanıt

**Paket 2:** `test_enstruman_v2.py` (102: +kanonik kimlik 7 grup, U17 sözleşme 6, evren kuralı 4,
gerçek depo regresyonu 2 — yerelde koşar, CI'da atlanır), `test_takvim.py` (20). **Paket 1:**
`tests/unit/test_enstruman_v2.py` (50): varsayılan/açık/donmuş; tip kümesi (4 geçerli, 6 red, 4 çift
ayrımı, sınıf≠tip); serileştirme A/B/C (sıra, altın hash, tam şema, determinizm, eski⊂yeni);
hash sınırı D (5 modül statik, `tablo_hash`/`uyelik_matrisi` davranışsal, `Sonuc` alanları);
maliyet gövdesi (yürürlükteki dosya SHA, sentetik literal, `tekrar._maliyet` gidiş-dönüş, geçici model).
Mevcut `test_kimlik.py`, `test_evren.py`, `test_izgara.py`, `test_coklu_motor.py` değişmeden geçiyor.

---

## K-084 — Enstrüman-başı maliyet modeli: katalog + çözümleyici; tek-model Binance spot yolu bit-aynı (U14)

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (U14 spike → tasarım A kabulü, R2 Paket 3
talimatı) · **Tabi:** K-007, K-009, K-021, K-057/6, K-083 · **Kaynak:** `docs/audit/W3` R5 (tek global
maliyet 761 sembole uygulanıyor), Threshold-Policy U14, U14 Spike (2026-09-21),
`tests/unit/test_maliyet_katalogu.py`

### Bulgu

`MaliyetModeli` koşu başına **tek** nesneydi (`config/maliyet.json`; BTCUSDT 1m p75 slippage, K-021)
ve evren koşularında her sembole aynen uygulanıyordu. `Enstruman.maliyet_modeli_id` (K-083) yalnız
metadata idi, tüketicisi yoktu. Maliyet üç kimlik zincirine giriyor: deney `girdi["maliyet"]`
(`_maliyet_govdesi`, `girdi_hash`), `Sonuc.maliyet = sozluk()` (`config_hash`, evren kaydı), paper
`KosuKimligi.maliyet` (+ toparlanma eşitliği, K-038). Hipotez/evren çekiliş kimliğinde maliyet yok.

### Karar

1. **Tasarım A — katalog + çözümleyici** (`common/maliyet.py:MaliyetKatalogu`). `global` →
   `config/maliyet.json` (mevcut dosya, aynı şema); diğer kimlikler → `config/maliyet/<id>.json`
   (aynı `MaliyetModeli` şeması). Dosya yok / JSON bozuk / şema uymuyor / kimlik biçimsiz
   (`^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}$`) → `MaliyetHatasi`, **fail closed**; sessiz global
   düşüşü yok. Çözümleme yalnız dosya: ortam, sağlayıcı, ağ yok.
2. **`global` yalnız Binance spot kripto** (K-083/U17 ile tutarlı): `coz("global",
   binance_spot_kripto=False)` hata. Yeni enstrümana yayılmaz.
3. **Kimlik kararlı ad**, içerik hash'i gömülmez; kanonik kanıt kayıttaki gövde
   (`fee, slippage, kalibrasyon` — `kalibrasyon.veri_sha256` dahil). Aynı gövdeli iki kimlik iki
   ayrı modeldir (kayıt `id` ile ayırt eder).
4. **Sahiplik/bağ:** `common/maliyet.py` `Enstruman`ı bilmez (statik testle); `Enstruman →
   maliyet_modeli_id → katalog → model` çözümlemesi `research/evren_kosu.enstruman_maliyetleri`
   (kimlik segmentleri orada). Bir sembolün segmentleri farklı kimlik taşıyamaz. **Hepsi `global`
   ise `None`** döner → motor tek-model yolunda.
5. **Motor:** `CokluBacktest(maliyet, maliyetler=None)`; `emirleri_hazirla(..., maliyetler)`
   sembolün modelini kullanır (yalnız fee/slippage; satış-önce sırası, sembol sırası, nakit tavanı
   maliyetten bağımsız — değişmedi). `maliyetler=None` → bugünkü yol **bit-aynı**; verilmişse
   evrendeki her sembol için model zorunlu (eksik → `CokluBacktestHatasi`).
6. **Kayıt/hash:** `Sonuc.maliyetler` (`{sembol: {id, govde}}`, sembol sıralı; ekleme sırasından
   bağımsız) ve `Sonuc.gecici` **yalnız çok modelde** dolu; `config_hash`e ve `config` bloğuna
   yalnız varsa girer (`risk`/`evren` kalıbı). Tek modelli kaydın `maliyet` bloğu, `config_hash`
   formülü ve `Sonuc` alanları (`gecici=None`) **aynen**. `_maliyet_govdesi` → `maliyet.govde`
   delege (çıktı bayt-aynı, SHA `fe9f73bb…` testli); `tekrar._maliyet` → `govdeden`.
7. **Geçici (K-021):** çok modelde herhangi bir model `gecici` ise koşu geçici →
   `promotion_engelleri` `gecici_maliyet_modeli`. Tek modelde eski okuma (`maliyet["gecici"]`).
8. **Tekrar:** eski `maliyet` bloğu aynen okunur; `maliyetler` bloğu taşıyan kayıt tek sembollü
   tekrar yolunda **uygulanmaz** — blok kurulur (bozuksa `MaliyetHatasi`), sonra `TekrarHatasi`
   ile açıkça reddedilir (sessiz tek modele düşüş yok). Eski kayıtlar dönüştürülmez.
9. **Paper/toparlanma (evren yolu):** başlangıçta `global` katalogdan çözülür (dosya yoksa açılmaz);
   kimlik biçimi aynı (`maliyet` tekil blok); `maliyetler` bloğu varsa toparlanma her kimliği
   katalogdan **yeniden** çözer ve gövdeyi kayıtla karşılaştırır — fark/eksik/bozuk →
   `KurulumUyusmazligi` (sebep `MaliyetHatasi` zincirde; çağıranlar tek tipi yakalıyor). `EvrenPaperMotoru(maliyetler=None)` geçişi. Tek sembollü `PaperMotoru`/
   `runs/paper` sqlite şeması **değişmedi** (tek sembol = tek model). Canlı evren yolu `Enstruman`
   görmediği için (K-083 açık kalan, İz G) çok modelli kimlik bugün yalnız toparlanma tarafında
   doğrulanabilir; üretimi İz G'ye bağlı.
10. **Execution/OMS/risk:** `MaliyetModeli` bağımlılığı yok, değişmedi.
11. **Kapsam dışı:** spread ayrı bileşen (R4), yeni kalibrasyon koşusu (her yeni `(venue, tip, id)`
    kendi `SlippageKalibrasyonu`nu ister; kalibrasyonsuz = geçici = promotion engeli), spot-dışı
    adaptör/veri, `tools/` betikleri (global `yukle()` ile devam).

### Kanıt (2026-09-21)

- `_maliyet_govdesi` SHA `fe9f73bb…`, `MaliyetModeli.sozluk()` `5022dec9…`, katalog dosyası,
  kural kimliği `27b7a16ed0ed…`, PIT `tablo_hash` `b06857c0…`, 14 çekilişin `veri_sha256`sı: SAME.
- `runs/evren/` 5 gerçek kaydın `config_hash`i bugünkü formülle yeniden hesaplandı: 5/5 SAME,
  hiçbirinde `maliyetler` bloğu yok. R1(b) 9 kayıt (monte_carlo/stres/tarama) sınıf + fark listesi
  birebir. `runs/paper/gozlem-1/2.sqlite` `maliyet` bloğu bugünkü `yukle().sozluk()` ile aynı (test).
- `tests/unit/test_maliyet_katalogu.py` (31): çözümleyici (global/dosya/eksik/bozuk×3/spot-dışı
  global/kimlik biçimi×7/deterministik/aynı gövde iki kimlik), enstrüman çözümleme (hepsi global →
  `None` ama fail closed; karışık evren; segment tutarsızlığı), tek model bit-aynı (`config_hash`
  formülü, eski `Sonuc` biçimi, aynı modelin haritası = aynı `sonuc_hash`, sabitler), çok model
  (fill sembol bazında, sıra aynı, ekleme sırası hash'i değiştirmez, eksik sembol red, kayıt
  gidiş-dönüş, tekrar reddi), geçici yayılımı + promotion engeli, paper toparlanma (tek model
  doğrulanır, çok model katalogla, dosya değişince/eksikte fail closed, gerçek gözlem sqlite'ları).
  Tam ağ dışı suite 2.052 → 2.083, 1 skip, 3 deselected; ruff temiz.

---

## K-085 — Canlı evren girişinde enstrüman kimliği katalogdan, işlem sözleşmesi borsadan; U17 fail-closed (İz G)

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne ("R2'de sıradaki gerçek işi belirle ve
ilerle" talimatı; İz G) · **Tabi:** K-038, K-046, K-083/U13-U17, K-084 · **Kaynak:**
`src/scryne_quant/live/evren_enstruman.py`, `tests/unit/test_evren_enstruman.py`

### Bulgu

K-083 ve K-084/9 açık bırakmıştı: canlı evren yolu (`sq paper evren-baslat` → `EvrenKosucu`)
barları REST/akıştan alıyor, `Enstruman` nesnesi görmüyordu; `islem_icin_dogrula()` çağrısız,
`maliyet_modeli_id` canlı kimliğe girmiyordu.

### Karar

1. **Kimlik kaynağı katalogdur, uydurulmaz.** Canlı yol `Enstruman`ı `sq evren tablo`nun PIT
   tablosuyla birlikte ürettiği `kimlik-katalogu.json`dan okur (`katalogu_oku`, tablonun yanında).
   v1 ve v2 kayıtları okunur; bilinmeyen anahtar / tutarsız `kanonik_id` → hata. Tabloda üye olup
   katalogda olmayan sembol → hata (K-083/U13).
2. **Sözleşme borsadan (K-046 kalıbı):** `tick_size`/`lot_size` `SembolKurallari`nden
   (`tick_size`, `step_size`) yazılır; `TRADING` dışı sembol reddedilir; her segment
   `islem_icin_dogrula()`dan geçer. Kısmi sonuç yok — **fail closed** (`EvrenEnstrumanHatasi`).
3. **Doğrulama noktaları:** (a) açılış — en son ayın üyeleri (işlem görebilecek küme); geçmiş
   ayların artık üye olmayan sembolleri ısınma verisidir, borsada kuralı olmayabilir (delist),
   doğrulanmaz; (b) aylık yenileme — `EvrenKosucu.enstruman_dogrulayici` yeni giren üyeliği aynı
   yoldan geçirir; hata → `enstruman_dogrulama_hatasi` olayı + koşu **durur** (K-038); geçince
   `enstruman_dogrulandi` olayı.
4. **Maliyet bağı (K-084):** `enstruman_maliyetleri(katalog, kimlikler)` canlı girişte de çalışır;
   hepsi `global` → `None` → kimlik/kurulum **aynen** (Faz 14 biçimi); çok modelde `maliyetler`
   bloğu kimliğe ve kuruluma girer, toparlanma onu katalogla doğrular (K-084/9).
5. **Değişmeyen:** `EvrenTablosu`, `EvrenPaperMotoru`, `evren_kurulum_kimlikten`, tek sembollü
   `PaperMotoru`, execution/OMS/risk. `ozet()` yalnız sayım (günlüğe), kimliğe girmez.

### Kanıt

`test_evren_enstruman.py` (13): katalog okuma (v1+v2, segment sırası, yol, eksik/bozuk×2, geçersiz
kayıt×2), kurulum (tick/lot her segmente, katalog değişmez, özet; katalog dışı üye, `BREAK`, tick 0 →
U17 reddi; spot zinciri `None`), gerçek katalog (761 kimlik, son ayın 50 üyesi kurulur, `None` —
yerelde), koşucu (yeni üyelik doğrulanır + olay; hata → olay + koşu durur; doğrulayıcı yoksa eski
davranış). Mevcut `test_evren_kosturucu.py`/`test_evren_pano.py`/`test_paper_dongu.py` değişmeden
geçiyor; host-1 gözlem koşuları etkilenmez (kod dokunulmadı, K-069).

---

## K-086 — R2 kapandı: enstrüman & çok varlık alan modeli; R4 sınırı takvim bağlaması R4'te

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne ("push sonrası R2'yi kapat") ·
**Tabi:** K-083, K-084, K-085 · **Kaynak:** `docs/ROADMAP-RESET.md` R2

**Karar.** R2'nin "bitti" kriteri karşılandı: `Enstruman` v2 alanları (K-083 Paket 1), U13 kanonik
kimlik + U15 `24x7` takvim seam'i + U16/U17 sözleşme kuralları (K-083 Paket 2), enstrüman-başı
maliyet kataloğu (K-084), canlı evren girişinde kimlik + U17 fail-closed (K-085); spot/vadeli/
CFD/ETF ayrımı tip düzeyinde testle; U13-U17 K olarak yazılı. Kripto yolu her pakette bit-aynı
ölçüldü (`_maliyet_govdesi` `fe9f73bb…`, PIT `b06857c0…`, kural `27b7a16ed0ed…`, 14 evren
çekilişi, R1(b) 9 kayıt, 5 evren kaydı `config_hash`; ağ dışı suite 2.096).

**R2'den R4'e devredilen (R2'nin değil R4'ün kriteri):** takvim seam'inin `izgara`/`gap`/
kırılma "eksik bar"/`bar_yili`/canlı bayatlığa bağlanması ve bunun motor tarafında bit-aynı
kripto kanıtı; spread ayrı maliyet bileşeni. R3'e bağlı: yeni `(venue, tip, id)` kalibrasyonu ve
kripto-dışı takvim içeriği. Bunlar R2'yi açık tutmaz; R4 satırı zaten bunları sayıyor.

---

## K-087 — R3 ilk kripto-dışı sınıf: FX (HistData M1 → 1h), yalnız araştırma; Dukascopy ve Tiingo elendi

**Durum:** değiştirildi → K-088 (sağlayıcı: HistData yerine FXCM MarketData; sınıf/kapsam/takvim/eşik maddeleri yürürlükte) · **Tarih:** 2026-09-21 · **Onay:** Scryne ("R3'ün ilk işi: kaynak/lisans ve
kripto-dışı veri kapsamı kararı") · **Tabi:** K-005, K-007, K-014, K-021, K-052, K-079, K-080,
K-083/U13-U17, K-084 · **Kaynak:** sağlayıcı sayfaları 2026-09-21'de okundu (aşağıda), Threshold-
Policy §3, `docs/audit/W7` §5, `src/scryne_quant/data/sozlesme.py:histdata-fx-m1`

### Bulgu — kaynak taraması (2026-09-21, sayfalar doğrudan okundu)

| Kaynak | Veri | Lisans/koşul (alıntı) | Sonuç |
| --- | --- | --- | --- |
| **Dukascopy** Historical Data Export | FX/emtia/endeks, tick→aylık, ücretsiz, anahtarsız | Terms of Use: "solely for your own non-commercial use"; "You shall not use … any 'scraper,' 'robot,' 'bot,' … or any other automate device … without the prior express written consent" | **Elendi** — idempotent/checksum'lu indirici bir "automated device"; yazılı izin olmadan K-009 hattı kurulamaz |
| **Tiingo** (ücretsiz Individual) | EOD hisse/ETF 110k sembol, 30+ yıl; intraday yok; 50 istek/saat, 500 sembol/ay; `supported_tickers.zip` | ToS §1.6(a): "you may not write, save, archive, back up, or otherwise retain Tiingo Data in any persistent or durable storage … remove … immediately after the calculation"; §5.3 sistematik derleme yasağı; §7.3 "internal consumption only" | **Elendi** — Parquet depo + `veri_sha256` + K-080 geri sarım kalıcı depolama ister; ToS ile uzlaşmaz |
| **HistData.com** | 66 FX çifti + endeks CFD (SPX/NDX/DAX/…) + XAU/XAG + WTI/BCO; tick ve **M1** (bid); aylık zip; ücretsiz web indirme, toplu/otomatik için FTP tek seferlik 27 USD ("traffic cost", veri satışı değil) | Lisans metni **yok**; tek beyan: "Since it's free data, you'll not get from us any kind of warranty or certification. Use the data at your own will and risk." Yeniden dağıtım/ticari/otomasyon yasağı yazılı değil | **Seçildi** (araştırma). Provenans zayıf: kaynak akışı adsız, bar'lar yalnız bid, zaman damgası EST (UTC−5) yaz saatsiz |
| Stooq | (sayfa boş döndü, değerlendirilemedi) | — | açık |
| FRED/ALFRED | makro (mevcut hat, K-060) | kaynak atıfla serbest | varlık sınıfı değil |

### Karar

1. **İlk kripto-dışı sınıf `fx`**, venue `histdata-fx`, `instrument_type="cfd"` (perakende marjlı
   FX: swap = finansman → U17 `finansman_modeli_id` zorunlu; spot değil — dürüst sınıflama).
   `VARLIK_SINIFLARI = {kripto, fx}`, `VENUE_TIPLERI[histdata-fx] = cfd` (koda dokunma = karar,
   K-083). Endeks/emtia için karar **yok** (`endeks` reddedilir, testli).
2. **Kapsam: yalnız araştırma.** Canlı akış yok (R3 satırı "isteğe bağlı"); K-079 (kaldıraçlı
   ürün hesabı) ve W7 §5 (FX/CFD aracı kurum = lisans + yargı alanı) bu sınıf için canlıya giden
   yolu **kapalı** tutuyor; açılması ayrı K + compliance.
3. **Veri sözleşmesi `histdata-fx-m1`** (`data/sozlesme.py`): şema aynı bar şeması; 1h katmanı
   M1'den türetilir; EST→UTC **sabit +5 saat** (yaz saati yok, kaynak beyanı); fiyatlar bid —
   ask yok → spread R4'te ayrı bileşen, o güne kadar aleyhte varsayım (K-007); `Volume` tanımsız
   → `trades` 0; her zip SHA-256 manifestoya; lisans alanı sağlayıcı beyanını **alıntıyla** taşır,
   ad uydurmaz.
4. **Edinim:** ücretsiz web indirme elle (aylık zip → `data/fx/_gelen/`) **ya da** FTP (27 USD,
   Scryne'ın ödeme kararı). İndirici her iki yolda aynı: dosya-gelen, idempotent, checksum'lu,
   `--bitis-gun` ile veri sonu sabit (K-080). Web formuna otomatik POST **yapılmaz** (yazılı izin
   yok; Dukascopy ile aynı gerekçe).
5. **Takvim:** 5/7 (Pazar ~22:00 UTC açılış, Cuma ~22:00 UTC kapanış) — R3 "takvim doğrulama
   testi" bu veriyle ölçülür ve `data/takvim.py`ye ikinci katalog satırı (`fx-5x24`, içerik-hash'li)
   **ölçümden sonra** girer (K-083/U15: kripto-dışı takvim R3 verisi olmadan tanımlanmaz).
6. **Hayatta kalma yanlılığı:** sabit çift listesi; ölçüm yine yapılır (hangi çiftlerin hangi
   aydan itibaren dosyası var — PIT evren tablosu aynı kalıpla), sonuç raporlanır.
7. **Eşik/kalibrasyon:** yeni `(histdata-fx, cfd, <id>)` → kendi `SlippageKalibrasyonu`
   (M1 bid bar-to-bar, K-021 kalıbı) ve kendi null dağılımı (U17); 1,04 taşınmaz.

### R3 Paket 1 (uygulama sırası)

(a) `data/fx.py`: zip → M1 CSV → UTC 1h Parquet (`data/fx/<PAIR>/1h.parquet` + `1h.kaynak.json`
SHA'lı manifesto), idempotent, `--bitis-gun`; (b) `sq data fx-al` CLI (gelen dizinden);
(c) `sq data quality` FX'te (gap 5/7 farkında değil — R4'e kadar hafta sonu boşlukları
raporlanır, `suspect` değil); (d) takvim ölçümü + `fx-5x24` satırı; (e) PIT evren tablosu (çift
listesi) + hayatta kalma ölçümü; (f) `docs/Faz-R3-FX-Veri-Raporu.md`. Kanıt: `test_fx.py`
(format, EST→UTC, bid, idempotency, checksum, K-080).

---

## K-088 — R3 FX kaynağı FXCM MarketData (doğrudan HTTPS haftalık M1 bid+ask); HistData terk edildi

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne ("FXCM MarketData bulgusunu kabul et")
· **Değiştirir:** K-087'nin sağlayıcı kararı (K-087/1, /3, /4 → bu K; K-087/2, /5-7 kapsam,
takvim, hayatta kalma, eşik maddeleri yürürlükte) · **Tabi:** K-005, K-007, K-009, K-014, K-080,
K-083/U13-U17, K-084 · **Kaynak:** `github.com/fxcm/MarketData` README (2026-09-21 okundu),
gerçek dosya ölçümü (aşağıda), `src/scryne_quant/data/fx.py`, `tests/unit/test_fx.py`

### Neden HistData terk edildi

Ücretsiz indirme yalnız tarayıcı içinde çalışıyor: `POST /get.php` formunun `tk` alanı ham HTML'de
**boş**, sayfa JavaScript'iyle dolduruluyor, dosya gizli iframe'e iniyor; API/örnek dosya/doğrudan
URL yok; toplu erişim yalnız ücretli FTP/Google Drive. Token'ı taklit eden otomatik POST K-087/4'te
zaten yasaktı. Ayrıca veri yalnız bid ve kaynak akışı adsızdı. FTP için ödeme **yapılmadı**.

### FXCM MarketData — ölçüm (2026-09-21, gerçek dosyalar)

- README doğrudan URL kalıbı veriyor: `https://candledata.fxcorporate.com/{m1|H1|D1}/{PAIR}/{yıl}/{hafta}.csv.gz`,
  hesap/anahtar yok; "This is for personal use and abides by our EULA". 21 çift.
- Biçim: başlık `DateTime,BidOpen,BidHigh,BidLow,BidClose,AskOpen,AskHigh,AskLow,AskClose`;
  damga `MM/DD/YYYY HH:MM:SS.000` (03/08/2024 = 8 Mart, Cuma); **volume yok**.
- **Zaman damgası UTC** (varsayılmadı, ölçüldü): kış haftaları Pazar 22:0x açılış / Cuma 21:59
  kapanış (2024 h2, h10, h45; 2023 h51-53), ABD yaz saati haftaları Pazar 21:0x / Cuma 20:59
  (2024 h11 = 10 Mart DST başlangıcı, h12, h30, h31, h44) — NY 17:00 açılışının UTC karşılığı
  tam olarak böyle kayar; yerel/sabit-ofset damga olsaydı kaymazdı.
- Hafta dosyası Pazar→Cuma; satır 7.172–7.188 / 7.200 dakika (tick'siz dakikalar yok); yılbaşı
  haftaları kısa (2023 h52 5.415, h53 5.356).
- **Hafta numarası**: yıl = haftanın **Pazar**ının yılı; `w = %U(Pazar) + (1 if %U(1 Ocak)==0 else 0)`
  — yani 1 Ocak'ı içeren hafta 1 (Pazar'dan başlayan haftalar). Doğrulandı: 2023-12-31 → 2023/53,
  2024-01-07 → 2024/2, 2024-03-03 → 2024/10, 2024-10-27 → 2024/44; 2024/1 ve 2024/53 **404**.
- Kapsam: 2012'den 2026 h35'e kadar 200 döndü (EURUSD).

### Karar

1. Venue **`fxcm-fx`**, `instrument_type="cfd"` (FXCM perakende CFD/marjlı FX; swap = finansman,
   U17), `asset_class="fx"`. `VENUE_TIPLERI[fxcm-fx] = cfd`. `histdata-fx` venue'su ve
   `histdata-fx-m1` sözleşmesi hiç veri taşımadan **kaldırıldı** (K-087 metni tarihsel).
2. Veri sözleşmesi **`fxcm-candledata-m1`**: M1 bid+ask OHLC, volume yok (`trades` üretilmez),
   damga UTC (ölçüm yukarıda), haftalık `.csv.gz`, 5/7 seans (Pazar 21/22:00 UTC → Cuma
   20:59/21:59 UTC, DST'ye göre). Lisans alanı: "personal use / EULA" **alıntıyla**; yeniden
   dağıtım yok; kullanım kendi hesabı/araştırma (K-014). Canlı yok (K-087/2 aynen).
3. **`data/fx.py` (Paket 1(a)):** haftalık dosyalar `data/fx/_gelen/<PAIR>/<yıl>-<w>.csv.gz`e
   indirilir (varsa yeniden indirilmez; 404 manifestoya `yok` yazılır), SHA-256'ları manifestoda;
   M1 → **1h** (bar = saat başı, `open_time` UTC epoch ms, K-005): bid ve ask OHLC ayrı ayrı
   (ilk/maks/min/son), `m1_sayisi`; **mid/tek fiyat üretilmez** — motorun hangi fiyatı kullanacağı
   ve spread bileşeni R4 kararı (K-007 "aleyhte" orada uygulanır). Parquet `data/fx/<PAIR>/1h.parquet`
   deterministik (depo ile aynı yazım parametreleri, pandas metadata'sız), manifesto
   `1h.kaynak.json` (dosya başına sha/satır/ilk/son, `veri_sonu`, `bitis_gun`).
4. **`--bitis-gun` (K-080):** o günden sonraki haftalar indirilmez, depodaki barlar `open_time <
   gün+1 00:00 UTC` ile kırpılır; aynı komut iki kez → bayt-aynı; uzatmak da geri sarmak da aynı
   komut. Kripto yolu (`ParquetDepo`, `data/market`, `data/evren`) **değişmedi**.
5. Takvim (`fx-5x24`), kalite raporu, hayatta kalma ölçümü, kalibrasyon: K-087/5-7 aynen, sonraki
   paketler.

---

## K-089 — `fx-5x24` takvimi: New York 17:00 dönümlü 5/7 seans + yalnız ölçülmüş kapalı dönemler

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (R3 Paket 1(d) talimatı) · **Tabi:**
K-005, K-009, K-083/U15-U16, K-088 · **Kaynak:** `src/scryne_quant/data/takvim.py`,
`docs/Faz-R3-FX-Veri-Raporu.md` §3-4, `tests/unit/test_takvim.py::TestFx5x24`, `test_fx.py::TestFxKalite`

### Ölçüm (FXCM EURUSD m1, 55 hafta: 2023-11-19 22:00 → 2024-12-13 21:00 UTC)

| Soru | Sonuç |
| --- | --- |
| Hafta uzunluğu | 53/55 hafta **120 saat**; hafta içi eksik saat **0** |
| Açılış/kapanış UTC | kış Pazar 22:00 → Cuma 21:00 (son bar); yaz (10 Mart–3 Kasım 2024) 21:00 → 20:00 |
| Rollover | kısa saatlerin (m1<60) 447'sinden 257'si **NY yerel 17:00**; kış/yaz fark etmiyor → dönüm yerel saate bağlı |
| ABD/İngiltere tatilleri | Şükran Günü 2023-11-23, Good Friday 2024-03-29, Easter Monday 04-01, May Day 05-06, Memorial Day 05-27, 4 Temmuz, Labor Day 09-02, Veterans Day 11-11: **kapanış yok** (120/120) |
| Noel 2023 | h52 92/120: kapalı 2023-12-25 01:00 → 2023-12-26 05:00 UTC (NY 24 Aralık 20:00 → 26 Aralık 00:00), 28 saat |
| Yılbaşı 2024 | h53 91/120: kapalı 2024-01-01 00:00 → 2024-01-02 05:00 UTC (NY 31 Aralık 19:00 → 2 Ocak 00:00), 29 saat |
| Sağlayıcı boşluğu (takvim değil) | m1 dosyası yok: 2024 h35 (25-30 Ağu), h51-53, 2025 h2 (21 çift); `H1/EURUSD/2024/52` var — m1 katmanının boşluğu |
| Noel/Yılbaşı 2024 | **ölçülemedi** (m1 h51-53 yok) |

### Karar

1. `data/takvim.py` kataloğuna **`fx-5x24`** (sürüm 1, içerik hash `16bafe19…`): `Seans("America/
   New_York", Pazar 17:00 → Cuma 17:00)`; hafta içi kesintisiz; UTC ızgarası IANA bölgesinden
   türetilir (yaz saati yerel saati sabit, UTC'yi kaydırır — ölçümle aynı). `izgara()` sürekli
   `arange`'i seans maskesiyle keser; `beklenen_bar()` ızgara uzunluğu.
2. **`kapali` yalnız ölçülmüş dönemleri taşır** (Noel 2023, Yılbaşı 2024, kaynağı yazılı);
   `olcum_kapsami` ölçümün UTC aralığı. Kapsam dışı için kapalı dönem **bilinmiyor**, "yok" değil
   (K-083/U15: uydurma tatil yok). ABD/İngiltere tatilleri ölçüldü ve kapalı **değil** — takvime
   girmedi. Takvim yeni ölçümle yalnız `surum`+`kapali` eklenerek büyür (yeni içerik = yeni hash).
3. **`24x7` değişmedi:** `Takvim.sozluk()` seans alanlarını yalnız seanslı takvimde yazar; 24x7
   içerik hash'i R2 ile aynı (testli); kripto kimlik/hash yolları takvimi hâlâ import etmiyor
   (AST testi aynen). Takvim sağlayıcı kapsamıyla **karıştırılmaz**: sağlayıcının dosya
   boşlukları (h35, h51-53) takvimde değil, kalite raporunda `eksik_dosya`.
4. **`sq data quality fx`** takvimi kullanır: haftanın beklenen ızgarası = ilk/son bar arasında
   takvimin açık saydığı saatler; `kapali_saat` ayrı; takvimin kapalı saydığı anda bar varsa
   `takvim_disi_bar` (takvimi yanlışlayan kanıt, sıfır beklenir); `olcum_kapsami` dışı haftalar
   `takvim_olcumu_disinda=True`. Rapor `takvim {kimlik, icerik_hash, surum}` taşır.
5. Doğrulama: takvim + 2 ölçülmüş kapanış, 55 haftalık gerçek depoyu **bar bar açıklıyor**:
   beklenen 6.663 = mevcut 6.543 + 120 (yalnız sağlayıcının h35 dosyası); takvim dışı bar 0;
   kalite raporu 6.543/6.543, eksik 0, `kapali_saat` 57.
6. Kapsam dışı: spread/mid (R4), `izgara`/`gap`/`bar_yili`'nin takvime bağlanması (R4), canlı.

---

## K-090 — FX PIT evreni "dosya-var" kuralı; hayatta kalma ölçümü HEAD kanıtıyla, indirmesiz

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (Paket 1(e) tasarım talimatı; büyük
indirme ve ödeme yok) · **Tabi:** K-051/4, K-052, K-088, K-089 · **Kaynak:**
`src/scryne_quant/data/fx_evren.py`, `tests/unit/test_fx_evren.py`, `docs/Faz-R3-FX-Veri-Raporu.md` §5

### Karar

1. **Kural (`FxEvrenKurali`, içerik hash'li):** çift `w` haftasında üye ⇔ sözleşmede (21 çift,
   `fxcm-candledata-m1`) **ve** o haftanın M1 dosyası sağlayıcıda var. Hacim yok → kripto
   evreninin hacim sıralaması yok; kural adı `dosya-var`. Kalite bazlı eleme (dosya indirilince,
   `fx_kalite`) **ayrı kural adı/sürümü** olur, bu kurala sessizce eklenmez.
2. **PIT anlamı:** haftalık dosya hafta bitince yayımlanır (ölçüldü: ~1-2 hafta); bar `t`nin
   kullanılabilirliği haftanın kapanışından sonradır — `available_time = bar kapanışı`
   sözleşmesiyle (K-052/5) uyumlu; canlı yok (K-087/2).
3. **Kanıt iki kaynaktan ve ayrı:** `_gelen/<PAIR>/kesif-*.json` (HEAD, indirmesiz) ve
   `<PAIR>/1h.kaynak.json` (indirilmiş, sha'lı). Çelişki → hata. Kanıtı olmayan hücre
   **bilinmiyor**; tabloya girmez ("yok" sayılmaz). `kapsam` bunu raporlar (`tam`/`kismi`).
4. **Hayatta kalma yanlılığı (Spike 6 kalıbı):** yalnız **tam kanıtlı** haftalarda (21/21 hücre)
   `|bugünkü liste \ PIT| / |bugünkü liste|`; medyan/azami/sıfır olmayan hafta. Tüm çiftlerde boş
   hafta = `saglayici_boslugu` (evren yok, yanlılık değil). Kısmi kanıtlı hafta ölçüme girmez.
5. **Tam indirme gerekli değil.** PIT tablosu ve hayatta kalma ölçümü **varlık** bilgisine
   dayanır; varlık HEAD ile ölçülür (`sq data fx-kesif --hepsi`): 21 × 770 hafta ≈ 16.170 HEAD,
   veri transferi ≈ 0; tam veri (~1,5 GB) yalnız kalite eleme kuralı ve araştırma (R6) için ve
   o zaman da yalnız kullanılacak pencere/çift altkümesi kadar (`--bas/--bit`).
6. **"2012 h1'de 21/21" varsayım değil, ölçülecek:** tam HEAD matrisi 2011 h50 → bugün; ilk
   hafta 21/21 ise yanlılık o haftadan itibaren 0 çıkar, değilse ölçüm gösterir. Bugünkü kanıt:
   21 çiftte 6 örnek hafta (2011 h10 404; 2012/2013/2017/2020/2026 h10 200) + EURUSD sınır
   taramaları — **kısmi**; mevcut çıktı `kapsam: kismi, ölçülen hafta 0` (uydurma yok).
7. Enstrüman kimliği: `fxcm-fx:cfd:<PAIR>@2012-01-01` tek segment — kimlik kırılması tespiti
   (K-052/4) bar verisi ister; dosya indirilince aynı `kimlikleri_kur` yoluyla ölçülür, şimdi tek
   segment varsayımı **açıkça** kayıtta.

### Uygulama

`data/fx_evren.py`: `FxEvrenKurali`, `kanit_topla`, `pit_tablo` (sütunlar `hafta, pazar,
kanonik_id, sembol, uye, kanit`; deterministik), `tablo_hash`, `hayatta_kalma`, `kapsam`,
`evren_kur` → `data/fx/_evren/<kural>.{parquet,json}`. CLI `sq data fx-evren`, `sq data fx-kesif
--hepsi` (dosya adı aralık taşır, kanıtlar birleşir). Testler (15): kural kimliği/sözleşme dışı,
hafta anahtarı çözümü (2012-1, 2023-53, 2024-1 yok), kanıt birleşme/çelişki, tablo determinizmi,
tekdüze → 0, eksik çift → 1/6 medyan 1/3 azami, sağlayıcı boşluğu, kısmi kanıt, kapsam,
`evren_kur` deterministik, gerçek kanıt → kısmi/ölçüm yok.

---

## K-091 — FXCM hafta numarası düzeltmesi, yıl sınırı alternatif anahtar; FX hayatta kalma ölçümü (21 × 773 hafta)

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (HEAD keşfi onayı) · **Düzeltir:** K-088
ölçüm notundaki hafta numarası kuralı · **Tabi:** K-052, K-088, K-090 · **Kaynak:**
`data/fx.py:hafta_no/hafta_anahtarlari`, `data/fx/_evren/6124cf568498.json` (yerel),
`docs/Faz-R3-FX-Veri-Raporu.md` §5b, `tests/unit/test_fx.py`, `test_fx_evren.py`

### Bulgu

1. **K-088'deki kural yanlıştı.** `%U(Pazar) + (1 if %U(1 Ocak)==0)` 2024 için doğru, 2015/2016/
   2021/2022/2026 için bir hafta kaydırıyordu (h53 "sağlayıcı boşluğu" artefakt). 15 yılın 10.
   dosyasının başlangıç tarihi okunarak ölçüldü: **kayma 1 yalnız 1 Ocak Pazartesi/Salı/Çarşamba
   ise** (2013, 2014, 2018, 2019, 2020, 2024, 2025), aksi hâlde 0. Kanonik anahtar yıl = Pazar'ın yılı.
2. **Sağlayıcı yıl sınırında tutarsız:** 31 Aralık 2017 haftası `2018/1` (2017/53 404), 31 Aralık
   2023 haftası `2023/53` (2024/1 404). `hafta_anahtarlari()` yıl geçiren hafta için `(yıl+1, 1)`
   alternatifini dener; depo/manifesto/kesif anahtarı kanonik kalır, kesif `kaynak_anahtar` yazar.
3. Yanlış anahtarla üretilmiş keşif dosyaları (2011, 2015, 2016, 2017, 2018, 2021, 2022, 2026)
   silinip yeniden tarandı; çelişkiyi `fx_evren` fail-closed yakaladı (2017-53: eski 2018 taraması
   "yok", yeni 2017 taraması "var") — kanıt sessizce düzeltilmedi, kaynak yeniden ölçüldü.

### Ölçüm (HEAD, 21 çift × 773 hafta, 2011-49 → 2026-38; indirme yok, ödeme yok)

| Ölçüm | Sonuç |
| --- | --- |
| Kapsam | **tam** — 21/21 çift, 773 hafta, kısmi kanıtlı hafta 0 |
| İlk üye haftası | **2012 h1 (2012-01-01): 21/21** — varsayım değil, ölçüm; 2011 h49-52 21/21 yok (kaynak öncesi) |
| Son üye haftası | 2026 h37 (2026-09-13); h38 henüz yok |
| Sağlayıcı boşluğu (21/21 yok) | 2011 h49-52; **2025 h29-30** (13-25 Tem 2025); **2026 h18-31** (3 May – 8 Ağu 2026, 14 hafta); 2026 h38 |
| Hayatta kalma | 752 ölçülen hafta; **medyan 0,0**; sıfır olmayan **5 hafta** (%0,66); azami 0,952 |
| Sıfır olmayan haftalar | 2024 h35 (yalnız AUDCAD), h51 (AUDCAD), h52 (AUDCAD, AUDCHF), h53 ve 2025 h2 (AUDCAD, AUDCHF, AUDJPY, AUDNZD) |

**Yorum.** Sözleşme sabit 21 çift olduğundan enstrüman giriş/çıkışı yok; sıfır olmayan 5 hafta
sağlayıcının **kısmi** yayın haftaları (alfabetik ilk çiftler var → yarım kalmış toplu iş izi),
delist değil. Kripto evreniyle kıyas: ayda medyan %16,7-18 (K-056) → FX'te **0**. Kural sonucu:
`dosya-var` kuralı o 5 haftada 1-4 üyeli evren verir; araştırma kuralı bu haftalar için **asgari
üye eşiği** ister (örn. "üye < 21 → evren yok") — bu bir kural sürümü kararıdır (R5/R6, K ile),
burada uygulanmadı. Sağlayıcı boşlukları (2025 h29-30, 2026 h18-31) araştırma penceresinden
adıyla dışlanır; canlı yok.

---

## K-092 — R3 kapandı: kripto-dışı ilk sınıf (FX, FXCM) veri katmanı

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne ("Paket 1(f) ile R3 raporunu kapat")
· **Tabi:** K-087…K-091 · **Kaynak:** `docs/ROADMAP-RESET.md` R3, `docs/Faz-R3-FX-Veri-Raporu.md`

**R3 bitti kriteri, madde madde:** kaynak seçilmiş + lisans kaydı (`fxcm-candledata-m1`,
`VeriSozlesmesi.lisans` alıntılı, K-088) ✅; tarihsel indirici idempotent + checksum + `veri_sonu`
(`data/fx.py`, `--bitis-gun`, manifesto SHA, bayt-aynı ölçüldü, K-088) ✅; takvim doğrulama testi
(`fx-5x24`, gerçek 55 haftayı bar bar açıklıyor, K-089) ✅; hayatta kalma yanlılığı ölçümü
(21 × 773 hafta, medyan 0, K-091) ✅; `sq data quality fx` raporu (K-089) ✅; canlı akış
isteğe bağlıydı, **yok** (K-087/2). Compliance: yalnız araştırma, kendi hesabı (K-014); FX/CFD
canlı yolu kapalı (K-079, W7 §5).

**R3'ten devredilen:** spread/mid modeli ve motorun bid/ask'i tüketmesi (R4); takvimin
`izgara`/`gap`/`bar_yili`/bayatlığa bağlanması (R4); `fx-5x24` `kapali` tablosunun 2023-24
ölçüm kapsamı dışına genişletilmesi (veri indirildikçe, yeni sürüm); asgari üye eşiği kuralı ve
FX null kalibrasyonu (R5/U17); FX slippage/spread kalibrasyonu (K-021 kalıbı, bid/ask); tam veri
indirme yalnız kullanılacak pencere kadar (K-090/5).

---

## K-093 — R4 Paket 1: takvim ızgara/bar_yili/gap/bayatlık hesaplarına bağlandı; 24x7 yolu bit-aynı

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (R4 Paket 1 talimatı) · **Tabi:**
K-057 (kanıt kalıbı), K-083/U15-U16, K-089 · **Kaynak:** `data/takvim.py`, `backtest/metrikler.py`,
`backtest/coklu_motor.py`, `data/dogrulama.py`, `data/kimlik.py`, `data/izgara.py`, `live/akis.py`,
`tests/unit/test_takvim_baglama.py`

### Karar

1. **Tek kaynak:** `data/takvim.Takvim` artık davranış üretiyor — `yillik_bar(timeframe_ms)`
   (sürekli: `YIL_MS / timeframe_ms`, ifade R2 öncesiyle aynı; seanslı: × haftalık açık saat/168 —
   fx-5x24 1h: 6.261,43), `beklenen_bar`, `acik_mi`. `YIL_MS` tanımı takvime taşındı,
   `metrikler.YIL_MS` aynı nesneyi dışa verir.
2. **Bağlanan hesaplar** (hepsi `takvim: Takvim | None = None`, `None` = 24x7 = eski formül):
   `metrikler.bar_yili/hesapla` (`CokluBacktest(takvim=…)` geçirir; kayda **girmez** — seanslı
   takvim `{"takvim": {id, icerik_hash}}` bloğuyla R4'ün sonraki paketinde, yalnız 24x7 değilse);
   `dogrulama.dogrula/rapor_cikar` (`gap` bayrağı ve `beklenen_bar` takvimin iki bar arasında
   beklediği sayıdan — 24x7'de `(Δ // adım) − 1`, aynı bayrak); `kimlik.bosluklar/kirilmalar`
   (`eksik_bar` aynı yoldan; duck-typed, `kimlik` → `takvim` import'u yok); `izgara.ortak_izgara`
   (seanslı takvimde seans dışı damga **reddedilir**, sessizce atılmaz); `live/akis.Tazelik`
   (seanslı takvimde piyasa kapalıyken sessizlik bayat değil; nabız hiç yoksa yine bayat).
3. **FX motor fiyatına/spread'e bağlanmadı** (bu paketin kapsamı dışı; R4 Paket 2).
4. `24x7` içerik hash'i ve `Takvim.sozluk()` R2 ile aynı; kimlik/hash modülleri (`depo`, `deney`,
   `sonuc`, `hash`) takvimi hâlâ import etmiyor (AST testi; `izgara`/`dogrulama`/`metrikler`
   listeden çıktı — bağlanma bu K).

### Bit-aynı kanıtı (K-057 kalıbı)

- **Statik:** 7 fonksiyon `takvim` parametresi alıyor, varsayılan `None`; `YIL_MS` aynı nesne;
  `24x7` sözlüğü 4 anahtar (test).
- **Referans (aynı girdi, `None` vs `takvim("24x7")`):** `CokluBacktest` → `sonuc_hash`,
  `config_hash`, metrikler birebir; `hesapla` sözlüğü birebir; `dogrula` raporu + bayrak dizisi
  birebir (boşluklu seri: 2 gap, 7 eksik, beklenen 300); `kirilmalar` LUNA fixture'ı birebir
  (`eksik_bar` 437); `ortak_izgara` birebir; `Tazelik` aynı kararlar.
- **Gerçek veri:** ağ dışı suite 2.185 (referans fixture testleri değişmeden); R1(b) 9 kayıt
  sınıf + fark listesi birebir; `_maliyet_govdesi` `fe9f73bb…` SAME; PIT tablosu gerçek depodan
  **yeniden üretildi** (kırılma yolu takvim üzerinden) → `tablo_hash b06857c0…`, 761 kimlik,
  kural `27b7a16ed0ed…`, 14 çekiliş girdileri SAME.
- **Seanslı davranış (fx-5x24, beklenen fark):** iki haftalık FX serisinde hafta sonu gap
  değil (24x7: 2 gap/48 eksik → fx: 1 gap/1 eksik, beklenen 240), kırılma boşluğu yalnız hafta
  içi, Cumartesi damgası `IzgaraHatasi`, Cumartesi sessizliği bayat değil / Pazar açılışı bayat.

## K-094 — R4 Paket 2: bid/ask fill + spread ayrı bileşen + kayda seanslı takvim; kripto yolu bit-aynı

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (R4 Paket 2 talimatı) · **Tabi:**
K-004, K-007, K-009, K-057 (kanıt kalıbı), K-083/U16, K-089, K-093 · **Kaynak:** `backtest/fill.py`,
`backtest/defter.py`, `backtest/metrikler.py`, `backtest/sonuc.py`, `backtest/coklu_motor.py`,
`tests/unit/test_fx_fill_spread.py`

### Karar

1. **Fill fiyatı yönün kotasyonundan:** `emir_hazirla_genel(kotasyon=(bid, ask))` verilirse alış
   `ask × (1 + s)`, satış `bid × (1 − s)` — K-007'nin kayması kotasyonun **üstüne** biner, yön
   yine aleyhte. Boyutlandırma ve yön kararı tek fiyattan (`open` = orta) verilir; kotasyon yalnız
   fill fiyatını değiştirir. `bid ≤ orta ≤ ask` ve `bid > 0` zorunlu, aksi `ValueError`.
   `kotasyon=None` (kripto) = bugünkü ifade, bit-aynı.
2. **Spread ayrı bileşen:** `Emir.kotasyon_fiyat` (yönün kotasyonu, kayma öncesi);
   `Emir.spread_maliyeti = |kotasyon − orta| × miktar`, `slippage_maliyeti = |fiyat − kotasyon| ×
   miktar` — iki sayı birbirine karışmaz. `Islem.spread` ve `Metrikler.toplam_spread` **yalnız
   varsa** (`None` = ölçülmedi) sözlüğe girer (`sembol`/`risk`/`maliyetler` kalıbı); kotasyonsuz
   fill `Islem.spread`e dokunmaz — "ölçülmeyen sıfır sayılmaz, eksik sayılır". Fiyata gömülü
   olduğu için `net_pnl`e zaten dahil, yalnız ayrı raporlanır. `_maliyet_govdesi`/`MaliyetModeli`
   değişmedi: spread bir **konfigürasyon** değil, veriden okunan bir **ölçüm**.
3. **Motor kotasyonu barlardan okur:** `bid_open` + `ask_open` sütunları olan sembol `(bid, ask)`
   ile dolar; yalnız biri varsa `CokluBacktestHatasi` (tek fiyata sessiz düşüş yok); ikisi de
   yoksa tek fiyat. Kotasyon yalnız fill barında barı olan sembol için okunur — "son bilinen
   kotasyon" yok. `AdimGirdisi.kotasyon` canlı adımcıya da aynı yoldan gider (K-001: tek gövde).
4. **Kayda takvim bloğu:** `CokluBacktest.takvim_kaydi()` → seanslı takvimde
   `{"id", "icerik_hash"}` (K-083/U16), 24x7 ve `None`da `None`. `Sonuc.takvim` `config_hash`e ve
   `config`e **yalnız varsa** girer; `sonuc_hash`e girmez (girdi, çıktı değil). `sonuc.py` takvimi
   import etmez (K-093/4 AST testi korunur) — blok sözlük olarak gelir.
5. **Kapsam dışı ve bilinçli bırakılan:** FX Parquet'inden `PiyasaGorunumu` kuran adaptör ve FX
   kalite bayrağı (`quality_status`) — `data/fx.py` `ok` üretmiyor, motor `ok` olmayan barda
   doldurmuyor; bu R4'ün sonraki adımı (Paket 3 finansman bacağıyla birlikte ya da ayrı K).
   `research/tekrar.py` `takvim` bloğunu henüz yorumlamıyor (FX kaydı yok). Spread tahmin modeli,
   yeni takvim, alfa, canlı emir yolu yok.

### Bit-aynı kanıtı (K-057 kalıbı)

- **Statik:** `kotasyon`/`kotasyonlar`/`spread_bileseni`/`Emir.kotasyon_fiyat`/`Islem.spread`/
  `Metrikler.toplam_spread`/`Sonuc.takvim` varsayılanları "yok"; kripto kaydında `spread`,
  `toplam_spread`, `takvim` anahtarı yok (test).
- **Referans (HEAD `96933a8` vs bu değişiklik, aynı betik):** `coklu_referans.json` iki senaryo
  `sonuc_hash` `d5a74d90…`/`5a21ba21…`, `config_hash` `25bc4854…`/`f3ffa934…` SAME; maliyet
  kataloğu senaryosu tam kayıt (git/ortam alanları dışında) SHA `0dddec77…` SAME. `takvim=None` vs
  `takvim("24x7")` tam kayıt birebir. `(mid, mid)` kotasyonu tek fiyat yoluyla özkaynak eğrisi,
  işlem satırları ve metrikler sayı sayıya aynı; tek fark `spread: 0.0` anahtarları.
  `test_backtest_referans`/`test_coklu_referans` dokunulmadan geçiyor; `_maliyet_govdesi` SAME.
- **FX (elle doğrulanmış fixture, EURUSD 6 bar, bar bar farklı spread):** `Decimal`(50) referansla
  alış fiyatı `ask[2] × (1 + s)`, satış `bid[4] × (1 − s)`, miktar, komisyon, spread, slippage,
  bitiş özkaynağı ≤ 1e-12; kaymasız modelde fill tam `ask`/`bid`, slippage 0, spread > 0; spread
  sıfırken slippage > 0 (bileşenler bağımsız); K-007: alış > ask > orta, satış < bid < orta.
- **Takvim:** `fx-5x24` bloğu `{"id": "fx-5x24", "icerik_hash": "16bafe19…"}` (K-089 hash'i),
  iki koşuda aynı `config_hash`, takvimsiz koşudan farklı; 24x7/`None` kayda girmiyor.
- **Gerçek veri (R1(b), `tools/r1b_kayit_durumu.py`, ana depoya dokunmadan):** 26 kayıt; 2026-09-20 durumuyla kıyaslanan 23 kaydın sınıfı ve fark listesi birebir (ayni 2, yalniz_sonuc_hash 3, semantik 10, veri_geri_getirilemedi 3, tekrar_edilemez 5); `sq lab yenile` ile üretilmiş 3 yeni tarama kaydı `ayni`.
- **Suite:** ağ dışı 2.205 test yeşil (19 yeni).

## K-095 — R4 Paket 3: FX finansman/rollover bacağı maliyet hattında; finansmansız yol bit-aynı

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (R4 Paket 3 talimatı) · **Tabi:**
K-007, K-009, K-021 (geçici model), K-057 (kanıt kalıbı), K-083/U17, K-084 (katalog kalıbı),
K-089, K-094 · **Kaynak:** `common/finansman.py`, `data/takvim.py`, `portfolio/durum.py`,
`backtest/coklu_motor.py`, `backtest/metrikler.py`, `backtest/sonuc.py`, `research/evren_kosu.py`,
`cli/main.py`, `tests/unit/test_finansman.py`

### Karar

1. **Model = `Enstruman.finansman_modeli_id` → `config/finansman/<id>.json`** (`FinansmanKatalogu`,
   `common/maliyet.MaliyetKatalogu` kalıbı; **global yok**). `FinansmanModeli`: `uzun_gunluk_bps ≥ 0`
   (uzun pozisyon, gün başına, notional bps), `uclu_swap_gunu` (varsayılan 2 = Çarşamba),
   `kaynak` (sağlayıcı/tarih/gerekçe; yoksa `gecici` → `promotion_engelleri`
   `gecici_finansman_modeli`). Kısa bacak alanı **uydurulmadı** (long-only). Eksik/bozuk dosya,
   fazla alan, biçimsiz kimlik → `FinansmanHatasi`; sessiz 0 yok. Bugün depoda ölçülmüş swap oranı
   yok, o yüzden `config/finansman/` altında dosya **yok**: FX koşusu model dosyası yazılana kadar
   fail-closed.
2. **Rollover anları takvimden** (`Takvim.rollover_anlari`, `rollover_gunleri`): seanslı takvimde
   her hafta içi günün yerel seans kapanış saati (fx-5x24: NY 17:00; DST'de UTC 22:00↔21:00 kayar);
   hafta içi = açılış gününden sonraki günden kapanış gününe. `uclu_swap_gunu` 3 gün, diğerleri 1
   (hafta 7). Bar i'ye `(t_i, t_{i+1}]` aralığındaki anlar işler (hafta sonu boşluğunda Cuma
   rollover'ı Cuma'nın son barına; son bar `+adım`). Ölçülmüş kapalı dönemde **atlanmaz** (K-007).
   Sürekli takvimde rollover tanımsız → `TakvimHatasi`; `CokluBacktest(finansmanlar=…)` seanslı
   takvim ister, `None`/24x7 ile reddeder.
3. **Tek kaynak, bir kez:** bedel `CokluAdimci._finansman_isle`te (fill'den sonra, risk/karardan
   önce) `miktar × close[i] × bps × 1e-4 × gün` olarak **nakitten düşülür** (`CokluPortfoy.nakit_dus`)
   ve açık tura `Islem.finansman` + `net_pnl −= bedel` yazılır. Fill, metrik, kayıt yeniden
   hesaplamaz; `Metrikler.toplam_finansman` turların toplamı. Nakit yetmezse `FinansmanHatasi`,
   koşu durur (kaldıraçsız portföyde borç yok, kırpma yok). Finansmanlı sembolün turu **0.0** ile
   başlar (ölçülmüş sıfır); `None` = model yok.
4. **Kayıt:** `Sonuc.finansmanlar` `{sembol: {"id", "govde"}}` `config_hash`e ve `config`e **yalnız
   varsa**; `Islem.finansman`/`Metrikler.toplam_finansman` yalnız varsa; `finansman_gecici` hash
   dışı. `takvim` bloğu (K-094) aynen. `_maliyet_govdesi`/`MaliyetModeli` değişmedi.
5. **Bağ:** `research/evren_kosu.enstruman_finansmanlari` (kimliği `None` olanlar atlanır; hepsi
   `None` → `None`; kimliği olanın dosyası yoksa hata; segmentler farklı kimlik taşıyamaz);
   `sq evren backtest` bunu geçirir — spot evreninde `None`, bit-aynı. Karışık (spot + cfd) evren
   motor tarafından reddedilir (bilerek). Canlı/paper yolu FX bilmiyor (K-087/2), bağlanmadı.

### Bit-aynı kanıtı (K-057 kalıbı)

- **Statik:** `finansmanlar`/`finansman_bileseni`/`Islem.finansman`/`Metrikler.toplam_finansman`/
  `Sonuc.finansmanlar`/`finansman_gecici` varsayılanları "yok"; kripto **ve** finansmansız FX
  kaydında `finansman`, `toplam_finansman`, `finansmanlar`, `gecici_finansman_modeli` yok (test).
- **Referans (HEAD `478cc5d` vs bu değişiklik, aynı betik):** `coklu_referans.json` 2 senaryo
  `sonuc_hash`/`config_hash` SAME; katalog senaryosu tam kayıt `0dddec77…` SAME — ve `96933a8`
  (R4 Paket 1) ile de SAME. Referans fixture testleri dokunulmadan geçiyor; `_maliyet_govdesi` SAME.
- **FX (fixture: EURUSD Pzt-Cum 2024-01-08…12, saatlik, bid/ask, 2,5 bps/gün):** tur 1 (Pzt 02:00 →
  Per 10:00) üç rollover görür (Pzt 1 + Sal 1 + Çar 3 = 5 gün); `Decimal`(50) referans: tur
  bedeli, `net_pnl` farkı ve özkaynak eğrisinin bar bar birikimli bedel kadar ayrışması ≤ 1e-12;
  tur 2 (Per 13:00 → 15:00) rollover görmez: `finansman = 0.0`, `net_pnl` yalnız fiyat/komisyon;
  Çarşamba birim bedeli Salı'nın 3 katı; 0 bps modeli özkaynak eğrisini finansmansızla birebir
  bırakır ama anahtarlar 0.0 ile var. Rollover anları: kış 22:00 / yaz 21:00 UTC, hafta 7 gün,
  hafta sonu boşluğunda Cuma barına.
- **Fail closed (test):** takvimsiz/24x7 + finansman → hata; evrende modeli olmayan sembol → hata;
  %100 pozisyonda rollover → `nakit yetersiz` hata; katalogda dosya yok / negatif bps / fazla alan
  (`kisa_gunluk_bps`) / `../x` → hata; cfd `Enstruman` `finansman_modeli_id=None` zaten kurulamaz.
- **Suite:** ağ dışı 2.227 test yeşil (22 yeni).

## K-096 — R4 Paket 4: gerçek FXCM Parquet → `PiyasaGorunumu` adaptörü, FX kalite bayrağı, `sq` FX akışı

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (R4 Paket 4 talimatı) · **Tabi:**
K-006, K-028, K-057 (kanıt kalıbı), K-083/U13-U17, K-084, K-088, K-089, K-090, K-093, K-094,
K-095 · **Kaynak:** `data/fx_gorunum.py`, `research/evren_kosu.py` (`fx_veri_kur`/`fx_kur`/
`fx_tablo_mu`), `cli/main.py` (`sq evren backtest --fx-depo`), `tools/fx_fixture_uret.py`,
`tests/fixtures/fx/`, `tests/unit/test_fx_gorunum.py`

### Karar

1. **Tek çeviri:** `data/fx_gorunum.py` FXCM 1h deposunu (`data/fx.py`, bid/ask OHLC + `m1_sayisi`)
   motorun bar sözleşmesine çevirir. `open/high/low/close` = alan alan `(bid + ask) / 2`; `volume`/
   `quote_volume` **NaN** (sağlayıcı vermiyor; sıfır "hacim yok" olurdu — kapasite oranı üretilmez,
   hacim isteyen strateji `hazir()` alamaz); `trades` 0; bid/ask OHLC ve `m1_sayisi` **aynen**
   taşınır → fill K-094 ile `ask_open`/`bid_open`dan. `data/fx.py` değişmedi (K-088: kaynağın
   verdiğini taşır, mid/kalite üretmez).
2. **FX kalite bayrağı (`fx_dogrula`):** kripto şemasıyla (`ok`/`gap`/`suspect`), FX kuralları:
   iki yanın OHLC tutarlılığı, çapraz kotasyon (`ask < bid`, K-094 `bid ≤ orta ≤ ask` ister),
   sonlu/pozitif olmayan fiyat, aşırı hareket (orta kapanış; eşik kripto `ASIRI_HAREKET_BPS`
   5.000 = üst sınır, FX için ölçülmüş değil — R5), `m1_sayisi` ∉ 1..60. `gap` = `fx-5x24`
   takviminin beklediği ama olmayan saat (hafta sonu/ölçülmüş kapalı dönem gap değil, K-089).
   **Sözleşme ihlali bayrakla geçiştirilmez:** hizasız damga, tekrar damga, takvim dışı bar, eksik
   sütun, sürekli takvim → `FxGorunumHatasi`. Motor yalnız `ok` barda karar verir ve doldurur
   (K-028/K-006, değişmedi): bozuk fill barı `fill_bari_ok_degil` sayılır, tek fiyata düşülmez.
3. **Izgara ve üyelik:** `ortak_izgara(..., takvim=fx-5x24)` (seans dışı damga hata, K-093);
   olmayan saat `listelenmedi` (`fx_hizala`, uydurma bar yok). Üyelik haftalık PIT tablosundan
   (`fx_evren.pit_tablo`, `hafta_anahtari` = UTC tarihini içeren Pazar-başlı hafta); pencere ay
   bazlı (kripto ile aynı: haftanın Pazar'ı pencere ayında → üye; bar kırpması ay sınırında).
   Depoda barı olmayan üye çift → hata (`AUDCAD: FX deposunda yok ama tabloda üye`), yani 21
   çiftlik gerçek tablo hepsi indirilmeden koşmaz — bilerek, kripto yoluyla aynı.
4. **Kimlik:** tablodaki kanonik kimlik (`fxcm-fx:cfd:<PAIR>@2012-01-01`) tek segment; FX'te
   kırılma tespiti uygulanmadı. `maliyet_modeli_id="fxcm-fx"`, `finansman_modeli_id=
   "fxcm-<pair>"` **referans**: `config/maliyet/fxcm-fx.json` ve `config/finansman/fxcm-<pair>.json`
   yoksa koşu katalogda durur (K-084/K-095; ikisi de bugün **yok**, oran uydurulmadı).
5. **`sq evren backtest`:** tablo meta'sı `fxcm-candledata-m1` kaynağını taşıyorsa (`fx_tablo_mu`)
   görünüm `--fx-depo`dan `fx_kur` ile kurulur, takvim tablonun takvimi olarak motora geçer
   (`Sonuc.takvim` bloğu), maliyet + finansman katalogdan zorunlu. Kripto tablosu için yol
   **değişmedi**. Varsayılan kıyas kote hacim ister → FX'te sinyal üretmez (dürüst sıfır; FX kıyası
   K-030 kapsamında ayrı karar).
6. **Fixture:** `tests/fixtures/fx/` = gerçek EURUSD deposunun 2024 h2-h8 dilimi (839 bar,
   `tools/fx_fixture_uret.py`, `FxDepo` yazımı → bayt-aynı, sha `ced35067…`; manifesto hafta
   sha'ları gerçek depodan kopya) + tek çiftlik PIT tablosu (`8f90232205e9`).

### Kanıt (K-057 kalıbı)

- **Kripto bit-aynı (HEAD `74c2cef` vs değişiklik, aynı betik):** `coklu_referans` 2 senaryo
  `sonuc_hash`/`config_hash` + katalog senaryosu tam kayıt SAME; `96933a8` (Paket 1 öncesi) ile de
  SAME. Kripto `hizala`/`veri_kur`/`dogrula` dokunulmadı; referans fixture testleri aynen.
- **Gerçek dilim kalite:** 839/839 `ok`, 0 gap, 0 suspect, 51 kısa saat (rollover dakikası,
  bilgi); tam 55 haftalık gerçek depo: 6.543 bar, 1 gap (120 saat = 2024 h35 sağlayıcı boşluğu,
  K-089 ile tutarlı), 0 suspect, 0,03 s.
- **Uçtan uca (fixture → `fx_kur` → motor):** tur alış fiyatı Parquet'teki `ask_open[3] × (1+s)`,
  satış `bid_open[61] × (1−s)` (`Decimal` ≤ 1e-12, kaymalı ve kaymasız); spread = gerçek yarım
  spread × miktar iki bacak (≤ 1e-12); iki rollover (Pzt + Sal) `Islem.finansman > 0`; kayıtta
  `takvim` (`16bafe19…`), `maliyetler["EURUSD"].id = fxcm-fx`, `finansmanlar["EURUSD"].id =
  fxcm-eurusd`, `toplam_spread`/`toplam_finansman`; iki koşu aynı hash.
- **Kalite fail-closed:** çapraz kotasyon → `suspect` → motor doldurmaz (`fill_bari_ok_degil` 1,
  işlem 0); beş suspect kuralı tek tek; hafta içi iki saat eksik → 1 gap / 2 eksik; Cumartesi
  damgası, hizasız damga, eksik sütun, 24x7 takvim, tekrar damga → hata.
- **`sq`:** maliyet dosyası yok → `fxcm-fx … dosya yok` ile başlamaz; finansman dosyası yok →
  `fxcm-eurusd` ile başlamaz; geçici kataloglarla koşar: `evren.takvim.id = fx-5x24`, kalite
  839 ok, kıyas 0 işlem, `toplam_finansman`/`toplam_spread` kayıtta.
- **Suite:** ağ dışı 2.248 test yeşil (21 yeni).

## K-097 — R4 kapandı: araştırma motoru genelleştirme (takvim, bid/ask, spread, finansman, FX adaptörü)

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne ("R4'ü kapat; K-096 kanıtlarını kullan,
yeni audit yok") · **Tabi:** K-093…K-096 · **Kaynak:** `docs/ROADMAP-RESET.md` R4/R5

**Paketler:** (1) K-093 takvim → `bar_yili`/gap/kırılma/ızgara/bayatlık, 24x7 bit-aynı ✅;
(2) K-094 bid/ask fill (K-007 üstüne) + spread ayrı bileşen + kayda `takvim` bloğu ✅;
(3) K-095 finansman/rollover (`finansman_modeli_id` → katalog, rollover anları takvimden, bedel bir
kez nakitten, fail-closed) ✅; (4) K-096 FXCM Parquet → `PiyasaGorunumu` adaptörü, FX kalite
bayrağı, `sq evren backtest` FX akışı, gerçek EURUSD fixture uçtan uca ✅.

**R4 bitti kriteri, madde madde (mevcut kanıtlarla):**
- Motor takvim-farkında, seans boşluğu "kırılma" değil → K-093 (fx-5x24 seride hafta sonu gap
  değil: 24x7 2 gap/48 eksik → fx 1 gap/1 eksik; kırılma boşluğu yalnız hafta içi) ✅
- Yıllıklandırma takvimden → K-093 (`Takvim.yillik_bar`, fx-5x24 1h 6.261,43; 24x7 aynı ifade) ✅
- Finansman/rollover bacağı fill'de → K-095 (bedel adım döngüsünde bir kez nakitten + tura;
  FX fixture `Decimal` ≤ 1e-12, 3 rollover/5 gün; kısa tur 0.0; K-096 uçtan uca 2 rollover) ✅
- Kripto koşusu R2 öncesiyle **bit düzeyinde aynı** (referans fixture) → her pakette HEAD ve
  `96933a8` (R4 öncesi) kıyası: `coklu_referans` 2 senaryo + katalog senaryosu tam kayıt SAME;
  R1(b) 23 gerçek kayıt sınıf + fark listesi birebir (K-094); `test_backtest_referans`/
  `test_coklu_referans` dokunulmadan ✅
- Spread ayrı maliyet bileşeni → K-094 (`Emir.spread_maliyeti`, `Islem.spread`, `toplam_spread`
  yalnız varsa; K-096 gerçek yarım spread ≤ 1e-12) ✅

**R4'te kalan — sınıflandırıldı ve taşındı (R4'e geri doldurulmaz):**
1. **R5 kalibrasyon:** ölçülmüş FX maliyet (`config/maliyet/fxcm-fx.json`, K-021 kalıbı,
   bid/ask'ten) ve swap oranları (`config/finansman/fxcm-<pair>.json`, kaynaklı). Bugün ikisi de
   yok; FX koşusu katalogda durur (bilerek).
2. **R5/araştırma:** hacimsiz FX kıyasının tanımı (K-030; varsayılan kıyas kote hacim ister,
   FX'te hacim yok → sinyal üretmez).
3. **Veri kapsamı (R5 ön koşulu, K-090/5):** 21 çiftin tamamı HEAD'de var (K-091) ama yalnız 3'ü
   indirildi; gerçek tablo tüm üyeleri ister (`AUDCAD: FX deposunda yok` ile durur). İndirme
   yalnız kullanılacak pencere kadar.
4. **Araştırma altyapısı (R5/R6):** FX kırılma tespiti (bugün tek segment) ve
   `research/tekrar.py`nin `takvim`/`finansmanlar` bloklarını yorumlaması (FX kaydı tekrarı).

**R5 ilk paket önerisi:** ölçülmüş FX maliyet + finansman — ayrı öneri (Scryne kararı).

## K-098 — R5 Paket 1: ölçülmüş FX maliyet (`fxcm-fx`) ve **proxy** finansman modelleri

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (R5 Paket 1 talimatı) · **Tabi:**
K-007, K-021 (kalibrasyon kalıbı), K-084 (katalog), K-088, K-094, K-095, K-096, K-097 · **Kaynak:**
`data/fx_kalibrasyon.py`, `cli/main.py` (`sq data fx-kalibre`), `tools/fx_finansman_proxy_yaz.py`,
`config/maliyet/fxcm-fx.json`, `config/finansman/fxcm-{eurusd,gbpusd,usdjpy}.json`,
`docs/research/records/2026-09-21-R5-fx-kalibrasyon.json`, `tests/unit/test_fx_kalibrasyon.py`

### Ölçüm (3 çift, ortak pencere 2024 h2-h5 = 2024-01-07..2024-02-02, M1 28,6-28,7k dk/çift)

| | spread p50 / p95 (bps) | rollover ±15 dk p50 (bps), genişleme | slippage p50 / p75 / p95 (bps) |
|---|---|---|---|
| EURUSD | 0,184 / 0,459 | 1,004 (×5,4) | 0,460 / **0,923** / 2,123 |
| GBPUSD | 0,393 / 0,864 | 1,411 (×3,6) | 0,551 / **1,020** / 2,318 |
| USDJPY | 0,474 / 0,944 | 1,627 (×3,4) | 0,708 / **1,355** / 2,917 |

EURUSD tam 55 hafta (390.935 dk): slippage p75 0,849, spread p50 0,185 — ortak pencereyle uyumlu.

### Karar

1. **Slippage kripto kalıbıyla:** `data/kalibrasyon.kalibre_et` (1 dk bar-to-bar kapanış hareketi,
   p75, K-021 gerekçesi aynen) — girdi M1 **orta** fiyat; boşluk/hafta sonu sonrası dakika `gap`,
   iki ucu temiz olmayan hareket atılır. Yeni kalibrasyon sistemi yok; `data/fx_kalibrasyon.py`
   yalnız M1 birleştirme + spread dağılımı + proxy aritmetiği ekler.
2. **Spread modele yazılmaz** (çift sayım yok): K-094 fill bar bar gerçek `bid_open`/`ask_open`dan;
   ölçülen dağılım kanıt/kıyas (rapor). **Rollover penceresi ayrı:** NY 17:00 ±15 dk'da spread p50
   ×3,4-5,4 genişliyor, p95 6-13 bps — tek slippage sayısına gizlenmedi (rapor + gerekçe).
   Sonuç: rollover saatinde fill K-094 ile zaten o genişlemiş spread'i öder.
3. **Venue modeli `fxcm-fx`:** p75 oranı 1,468 < 1,5 (eşik ölçümden **önce** yazıldı,
   `VENUE_ORAN_ESIGI`); değer üç çiftin **en büyük** p75'i (USDJPY 1,355 bps, K-007); üç çiftin
   p75'i `dagilim_bps`te ayrı ayrı kayıtlı. Eşik sınıra yakın; 21 çift indirilince yeniden ölçüm
   ister (oran ≥ 1,5 çıkarsa çift başına dosya, `sq data fx-kalibre --yaz` bunu kendisi yapar).
4. **`fee_taker_bps` = 0,26, 0 DEĞİL.** Kaynak: MarketData README "lowest spreads available
   exclusively on Active Trader accounts" → veri komisyonlu hesabın spread'i; Active Trader UK
   tarifesi "£2.00 per side per 100K … above 50 million" → £2 × GBPUSD(ort. 1,27) / notional:
   EURUSD 0,233, GBPUSD 0,254, USDJPY 0,254 bps → en büyüğü yukarı yuvarlanmış 0,26 (K-007).
   **Koşul:** aylık ≥ 50M hacim + ≥ £25.000 özkaynak; altında standart hesap komisyonsuz ama daha
   geniş spread — bu veride **yok**, ölçülmedi. Model yalnız Active Trader koşulu için geçerli;
   `gerekce` bunu taşır. Kalibrasyon gerçek ölçüm → `gecici=False`.
5. **Finansman proxy:** FXCM rollover oranı yalnız platformda (Roll S/Roll B, 1k lot, bir gün
   önceden; help "Where is rollover shown", "Rollover" — 2026-09-21), **tarihli herkese açık arşiv
   yok**. Bu yüzden `config/finansman/fxcm-<pair>.json` merkez bankası politika faizi farkından
   türetildi ve `tur="proxy"` ile işaretlendi: `FinansmanKaynagi.tur ∈ {broker, proxy}` zorunlu,
   `aralik` zorunlu, `ham_gunluk_bps` (işaretli) kayıtlı; `FinansmanModeli.gecici` = kaynak yok
   **ya da** proxy → `gecici_finansman_modeli` promotion engeli. Türetim K-007 aleyhte: alınan faiz
   aralığın altı, ödenen üstü; broker marjı bilinmiyor → eklenmedi (proxy gerçekten **düşük**
   olabilir, bir sebep daha geçici). Sabit model, zaman serisi yok (ayrı karar).
   - EURUSD: (5,50 − 4,00)/365 → **0,4110** bps/gün, aralık 2023-09-20..2024-06-12
   - GBPUSD: (5,50 − 5,25)/365 → **0,0685** bps/gün, aralık 2023-08-03..2024-08-01
   - USDJPY: ham (−0,10 − 5,25)/365 = **−1,4658** (lehte carry) → **0** — K-095/1
     (`uzun_gunluk_bps ≥ 0`, K-007: lehte carry modellenmez) **korundu**, otomatik sıfırlama değil:
     ham değer dosyada, kural kaynaklı. Aralık 2023-07-27..2024-03-19 (BoJ 19 Mar 2024).
   - Kaynaklar: Fed FOMC (5,25-5,50, 2023-07-27..2024-09-18), ECB deposit 4,00 (2023-09-20..
     2024-06-12), BoE 5,25 (2023-08-03..2024-08-01), BoJ −0,10 (..2024-03-19) — URL'ler dosyada.
6. **Güven seviyesi:** maliyet modeli **ölçülmüş** (Active Trader koşuluyla); finansman **proxy,
   geçici** — gerçek broker oranı (tarihli) gelmeden FX sonucu promotion'a giremez. Motor `aralik`
   denetlemiyor (koşu penceresi aralığın dışına taşarsa sessiz) — R5 açık madde.

### Kanıt

- `sq evren backtest` fixture'da gerçek dosyalarla koşuyor; PlanliHedef tur: fill 1,09497 (ask),
  spread 0,114, slippage 1,355 bps, komisyon 0,26 bps, finansman 0,411 → `promotion_engelleri`
  `gecici_finansman_modeli` (maliyet geçici değil).
- Sentetik M1: rollover penceresi n=30/30, spread ×4, gap sonrası iki hareket atıldı (K-021 kuralı).
- Kripto: `coklu_referans` + katalog senaryosu `96933a8` ile SAME; `_maliyet_govdesi` SAME
  (`MaliyetModeli` şeması değişmedi); ağ dışı 2.257 test (9 yeni).

## K-099 — R5 Paket 2: hacimsiz FX evren kıyası `fx_evren_esit_agirlik` (K-030 çözümü)

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (R5 Paket 2 talimatı) · **Tabi:**
K-030 (kıyas zorunlu, aynı yoldan geçer), K-088 (hacim yok), K-090 (`dosya-var` kuralı), K-094,
K-095, K-096, K-098 · **Kaynak:** `strategy/kutuphane/evren_esit_agirlik.py`
(`FxEvrenEsitAgirlik`), `strategy/kutuphane/__init__.py` (`EVREN_KIYAS`), `tools/fx_fixture_uret.py`
(çoklu çift), `tests/fixtures/fx/{GBPUSD,USDJPY,_evren/27f528fa4aec.*}`, `tests/unit/test_fx_kiyas.py`

### Karar

1. **Tanım (ekonomik):** her yeniden dengeleme anında (`yeniden_dengele_bar`, 1h'te varsayılan
   120 = bir seans haftası) `t`de PIT üyesi (`dosya-var`, haftalık tablo) ve barı `ok` olan **tüm**
   çiftler eşit ağırlıkla tutulur (`hedef_brut` 1,0; `azami_agirlik` 0,30 tavanı → 3 çiftle %90
   brüt, kalan nakit rollover için); üyelikten düşen çift bir sonraki dengelemede kapatılır;
   giriş/çıkış yalnız üyelik + dengeleme periyodundan gelir — fiyat, momentum, hacim yok. Al-tut
   kalıbı: pozisyon pencerenin sonunda açık kalır (K-030 istisnası 2).
2. **Neden hacim gerektirmiyor:** FXCM hacim vermiyor ve FX evren kuralı hacimle sıralamıyor
   (`dosya-var` bir varlık kuralı). Kripto kıyasının sıralaması evren kuralının ölçütünü (30 günlük
   kote hacim) yansıtır; FX kuralında sıralama **yok**, dolayısıyla kıyasta da yok: skor sabit 0,
   tavan bağlarsa sıra `kur` sözleşmesiyle sembol adına düşer. Bu yüzden `azami_enstruman`
   varsayılanı sözleşmedeki çift sayısı (21): tavan bağlamaz, "evrenin tamamı" cümlesi doğru
   kalır. Daha küçük tavan alfabetik alt küme = kıyas değil (parametre kayda giriyor).
   `volume`/`quote_volume` **NaN kalır**, ısınma yalnız ATR (14 + 2 bar).
3. **En küçük değişiklik:** `EvrenEsitAgirlik`e iki kanca (`_hazirlik_ozellikleri`, `_skor`);
   varsayılanlar eski davranışın kendisi (`("atr","kote_hacim")`, kote hacim skoru). `on_bar`ın
   seçim/kurma/dengeleme gövdesi ortak; FX sınıfı yalnız özellik listesi, ısınma, kancalar ve
   varsayılan parametreleri değiştirir. `EVREN_KIYAS`e kayıtlı; kıyas olduğu için hipotez defterine
   girmez (K-030/K-039), alfa değildir.
4. **Kripto kıyası değişmedi:** `sozluk()` (config_hash girdisi) aynı; sentetik 3 sembollü evrende
   (tavan bağlıyor, geç listelenen sembol) HEAD vs değişiklik `sonuc_hash`/`config_hash` iki
   varyantta SAME; kripto referans senaryoları `96933a8` ile SAME.
5. **Promotion engeli aynen:** FX koşusu `gecici_finansman_modeli` taşır (K-098 proxy); bu paket
   kaldırmaz.

### Kanıt (gerçek fixture: EURUSD h2-h8, GBPUSD/USDJPY h2-h5, tablo `27f528fa4aec`, gerçek model dosyaları)

- Kıyas **işlem üretiyor**: 15 fill, üç çift aynı dengeleme barında açılıyor; brüt maruziyet ort.
  > 0,85, azami ≤ 0,92; spread 0,103, slippage 1,239, komisyon 0,238, finansman 7,06 (EURUSD 6,05,
  GBPUSD 1,01, USDJPY 0 — proxy tabanı) — hepsi motor hattından; `gecici_finansman_modeli` duruyor.
- Tek dengeleme (periyot > koşu): çift başına tek alış, fiyat Parquet `ask_open[15] × (1+s)` (`Decimal`
  ≤ 1e-12), notional 3.000 = 0,30 × 10.000, komisyon 0,26 bps.
- PIT çıkışı (sentetik, barı olan çift üyelikten düşer): sonraki dengelemede **tek satış**
  `bid_open × (1−s)` (`Decimal`), geri girmez; %100 yatırımlı hâl rollover'da `FinansmanHatasi`
  (K-095 fail-closed) — kıyas tavanı bu yüzden nakit bırakır.
- Hacim isteyen kripto kıyası FX'te hâlâ 0 sinyal (hacim uydurulmadı).
- `sq evren backtest --strateji fx_evren_esit_agirlik` koşuyor (CLI varsayılan `--yeniden-dengele`
  720; FX için 120 verilir). Ağ dışı 2.264 test (7 yeni).

**Not:** fixture'da GBPUSD/USDJPY h6-h8'de **barı yok** (indirilmedi) → pozisyon son fiyattan
değerlenir (`bayat_degerleme` 720, K-057) ve kapanamaz; bu üyelik çıkışı değil veri yokluğu.
Gerçek koşuda 21 çift pencere kadar indirilir (K-090/5).

## K-100 — R5 Paket 3: FX veri kapsamı tamamlandı — 21 çift × 55 hafta, gerçek kıyas koşuyor

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (R5 Paket 3 talimatı) · **Tabi:**
K-007, K-088, K-089, K-090/5 (pencere kadar indirme), K-091, K-094, K-095, K-096, K-098, K-099 ·
**Kaynak:** `data/fx.py` (`bozuk`), `data/fx_evren.py`, `data/fx_gorunum.py` (kapanış artığı,
çift başına maliyet kimliği), `data/fx_kalibrasyon.py` (`fee_bps` taban USD), `cli/main.py`,
`strategy/kutuphane/evren_esit_agirlik.py` (`HEDEF_BRUT_FX`, `_ayarlar_icin`),
`tools/fx_depo_durumu.py`, `tools/fx_finansman_proxy_yaz.py` (21 çift), `config/maliyet/fxcm-<pair>.json`
(21), `config/finansman/fxcm-<pair>.json` (21), `docs/research/records/2026-09-21-R5-fx-depo-durumu.{json,md}`,
`docs/research/records/2026-09-21-R5-fx-kalibrasyon-21cift.json`

### Kapsam kararı ve depo durumu

1. **Pencere = kullanılacak pencere (K-090/5):** 2023-11-19..2024-12-13 (56 hafta anahtarı, 55 var),
   EURUSD'nin mevcut deposuyla aynı; 2012'ye kadar tam tarihçe **indirilmedi** (≈16k dosya, ~1,5 GB;
   ihtiyaç doğunca aynı komut). Önce 18 eksik çift 4 haftalık pencereyle (2024 h2-h5) doğrulandı,
   sonra `sq data fx-al --hepsi --bas 2023-11-19 --bit 2024-12-13` ile tamamlandı; önbellek/
   checksum/idempotency aynen (EURUSD deposu bayt-aynı `9dee3e07…`). `_gelen` 1.152 dosya, 122 MB.
2. **Durum tablosu (`tools/fx_depo_durumu.py`):** **21 çift `tam`, 0 kısmi, 0 depoda yok.**
   Sağlayıcı boşluğu 20 hafta (2024-35, 20 çift — K-089 ile aynı), **bozuk 4 hafta** (aşağıda),
   kanıt-yok 0. Çift başına 6.417-6.543 bar.
3. **Yeni sınıf `bozuk` (sağlayıcı 200, gövde kullanılamaz):** ölçüldü — AUDCAD 2024-35 (98.361
   baytın 98.219'u NUL), CADCHF 2024-18, NZDCAD ve NZDCHF (yalnız başlık, 74 bayt). 404 (`yok`)
   değil, hata da değil: kanıt `<hafta>.csv.gz.bozuk.bin`, işaret `<hafta>.bozuk`, manifestoda
   `durum: bozuk` + sha + neden; bir daha indirilmez; bar üretmez. Evren kanıtı **`var`**
   (`dosya-var` kuralı yayımla ilgilidir; kesif ile çelişmez); barı olmadığı için üyelik saatleri
   `uyeligi_barlara_kis` ile düşer ve sayılır (`bar_yok_uyelik` 460). Başlık değişikliği bozuk
   dosya değil şema değişikliğidir → hâlâ hata.
4. **Kapanış artığı (`fx_dogrula`):** USDCHF 2024-01-12 22:00 ve NZDUSD 2024-02-02 22:00 (Cuma
   NY 17:00 kapanış anı, `m1_sayisi` 1) K-096'nın "takvim dışı bar = hata" kuralını yanlışladı.
   Karar: seans kapanış anında açılan ve `m1_sayisi ≤ 5` bar **kapanış artığı** — sayılarak atılır
   (`kapanis_artigi` raporda, koşu meta'sında), ızgaraya girmez; başka takvim dışı bar hâlâ hata.
   55 haftada 21 çiftte 18 artık. Ayrıca gerçek veride **çapraz kotasyon** var (AUDNZD 11, GBPJPY 2,
   EURAUD 1, USDCHF 1 bar → `suspect`, fill yok) — K-096 bayrağı işini yapıyor.
5. **Maliyet çift başına (K-098/3'ün kendi kuralı):** 21 çift, 55 hafta yeniden ölçüldü: p75 oranı
   **2,39 ≥ 1,5** (EURGBP 0,643 … AUDJPY 1,536 bps) → `fxcm-fx` venue modeli **kaldırıldı**,
   `config/maliyet/fxcm-<pair>.json` (21, ölçülmüş, gecici değil). Komisyon türetimi düzeltildi:
   £2/100K **taban** → tabanın USD değeri (AUD = EURUSD/EURAUD, CAD/CHF = 1/USDxxx): AUD 0,39, CAD
   0,35, EUR 0,24, GBP 0,20, NZD 0,43, USD 0,26 bps (K-098'in 0,26'sı yalnız USD tabanlı için doğruydu).
   `fx_enstruman.maliyet_modeli_id = "fxcm-<pair>"`. Rollover spread genişlemesi 21 çiftte ≥ ×2.
6. **Finansman proxy 21 çifte:** AUD (RBA 4,35), CAD (BoC 5,00), CHF (SNB 1,75), NZD (RBNZ 5,50)
   eklendi, K-098 türetimi ve `tur=proxy`/`gecici` aynen; lehte carry olan 12 çift 0 (ham kayıtlı).
   Fail-closed korunur: dosyası olmayan çift koşuya giremez (hepsinin var, hepsi geçici).
7. **Kıyas 21 çiftte:** iki ölçülmüş düzeltme — (a) `HEDEF_BRUT_FX = 0,98`: %100 yatırılmış kıyas
   ilk rollover'da K-095 ile duruyordu (AUDCAD bar 138); %2 nakit payı ölçülmüş en yüksek proxy
   bedeline göre (0,411 bps/gün × 365 ≈ %1,5/yıl); (b) `_ayarlar_icin`: barı olmayan (satılamayan)
   açık pozisyonun payı brüt hedeften düşülür — CADCHF'nin bozuk haftasında hedef 0,98 kalan 20
   çifte dağıtılıp %4,7 takılı pozisyona binince nakit sıfırlanıyordu (bar 2775). Kripto kıyasına
   dokunulmadı (kanca kimlik; sentetik evrende HEAD ile SAME).

### Kanıt

- Gerçek koşu `sq evren backtest data/fx/_evren/6124cf568498.parquet --strateji fx_evren_esit_agirlik
  --yeniden-dengele 120 --azami-enstruman 21 --baslangic 2023-11 --bitis 2024-12`: 21 çift, 6.543
  bar, 136.943 üye bar, 1.152 fill, brüt ort. 0,978; spread 1,36, slippage 1,46, komisyon 0,40,
  finansman 27,18 (proxy); getiri −0,29 %, Sharpe −0,06; `config_hash 7fc528c0…`, `sonuc_hash
  33cc0a32…` iki koşuda aynı; `gecici_finansman_modeli` engeli duruyor. Kurulum 0,4 s, koşu 0,6 s.
- Kripto: `coklu_referans` + katalog senaryosu `96933a8` ile SAME; kripto kıyası sentetik evrende
  HEAD ile SAME; ağ dışı 2.268 test (fixture testleri çift başına kimliğe güncellendi).

## K-101 — R5 Paket 4: FXCM tarihli rollover oranı yok — proxy geçici kalır; finansman aralığı motorda denetlenir

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (R5 Paket 4 talimatı) · **Tabi:**
K-095 (semantik değişmedi), K-098/5, K-100/6 · **Kaynak:** `docs/research/records/
2026-09-21-R5-fx-rollover-kaynak.md`, `common/finansman.py` (`aralik_ms`, `gecerli_mi`),
`backtest/coklu_motor.py` (K-101 denetimi), `tests/unit/test_finansman.py`

### Karar

1. **Gerçek kaynak yok (kanıtlı):** FXCM rollover oranını yalnız Trading Station / ForexConnect
   Offers tablosunda (`Roll S`/`Roll B`, `RolloverBuy`/`RolloverSell`, 1k lot, bir gün önceden,
   hesap gerekir) gösteriyor; **tarihli, çift bazlı, herkese açık arşiv yok**. Resmi "FX Rollover
   Calendar" PDF'i (`docs.fxcorporate.com/user-guide/FXCMFXRolloverCalendar.pdf`, Q3 2026) yalnız
   **gün çarpanlarını** (0/1/2/3/4) veriyor, oran değil, yalnız cari çeyrek. MarketData deposunda
   rollover veri seti yok. Üçüncü taraf aggregator'larda FXCM yok. Ayrıntı ve URL/tarihler kayıtta.
2. **Sınıflandırma:** 21/21 çift `tur=proxy`, geçici; broker sınıfında **0** çift, karışım yok.
   Proxy "gerçek finansman" olarak **yeniden etiketlenmedi**; `gecici_finansman_modeli` promotion
   engeli duruyor.
3. **Resmi takvimle doğrulanan:** Çarşamba 3 gün (K-095 `uclu_swap_gunu=2`) ✓. Fark: FXCM tatil
   günü 0 + iki iş günü önce +1; K-095 kapalı dönemde bedeli atlamıyor — haftalık toplam aynı,
   zamanlama ≤ 2 gün. **K-095 semantiği değiştirilmedi** (talimat); resmi takvimi bağlamak ayrı karar
   (tarihsel takvim yayımlanmıyor).
4. **Geçerlilik aralığı motorda (bu paketin küçük parçası):** `FinansmanKaynagi.aralik`
   `YYYY-MM-DD..YYYY-MM-DD` (bitiş hariç, UTC) biçimi zorunlu; `FinansmanModeli.gecerli_mi(ilk, son)`;
   `CokluBacktest.calistir` ölçüm penceresi (ısınma hariç) aralığın dışına taşan sembolde
   **başlamaz** (`FinansmanHatasi`, sembol + kimlik + aralık listesiyle). Kaynaksız model hiçbir
   pencerede geçerli değil (bilinmeyen sıfır değil). Sonuç: K-100'ün 55 haftalık koşusu artık
   reddediliyor; 21 proxy'nin ortak geçerli penceresi 2023-11-19..2024-03-18 (BoJ), `--baslangic
   2023-11 --bitis 2024-02` ile gerçek koşu: 1.721 bar, 315 fill, finansman 7,14, hash
   `7fc528c0…/4f1333bd…`.
5. **Birim/dönüşüm (broker verisi gelirse):** platform değeri 1k lot başına hesap para birimi →
   `bps/gün = roll / (1000 × kur) × 10⁴`; long = `Roll B`, short = `Roll S` (short bacak bugün
   modelde yok, K-095). Kaynak URL + erişim tarihi + dönem + `tur=broker` ile `FinansmanKaynagi`ye.

### Kanıt

- Testler: aralık dışı pencere → `FinansmanHatasi` (K-101), sınır bitiş günü hariç, kaynaksız
  `gecerli_mi` False, ters aralık hata; fixture koşuları 2024 Ocak-Şubat (aralık içi) aynen.
- Kripto: `coklu_referans` `96933a8` ile SAME, kripto kıyası SAME; ağ dışı 2.269 test.

## K-102 — R5 Paket 5: ilk FX alfa araştırması — araştırma hattı FX'e açıldı, `fx_fiyat` programı (3/3) koşuldu ve kapandı

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (R5 Paket 5 talimatı: "altyapı eklemeyi
bırak, ilk FX alpha araştırmasına geç; motorun hipotez çalıştırabildiğini kanıtla, küçük setle başla")
· **Tabi:** K-039, K-045 (istisna, ölçümle), K-051, K-054, K-061, K-099 (kontrol), K-101 (pencere,
mutlak engel) · **Kaynak:** `docs/research/records/2026-09-21-R5-fx-alpha-1.md`,
`research/evren_degerlendirme.py`, `strategy/kutuphane/zaman_serisi.py`, `research/izgaralar.py`
(`FX_CEKILISLERI`), `tools/r5_fx_kos.py`, `tests/unit/test_fx_arastirma.py`

### Karar

1. **Araştırma hattı motor ayarlarını veriden çözer.** `evren_degerlendirme.kosu` her koşuda
   `veri.kimlikler`den çift başına maliyet (K-084) ve finansman (K-095), `veri.meta["takvim"]`den
   takvimi (K-096) çözüp `CokluBacktest`e verir (`motor_ayarlari`). Kripto evreninde üçü `None`
   → Faz 12-16 kayıtları bit-aynı (`test_coklu_referans`, `test_evren_degerlendirme`). **Sebep,
   ölçüldü:** FX verisinde eski `kosu` hata vermeden koşuyordu — kripto komisyonu, 24x7
   yıllıklandırma, sıfır finansman, bid/ask fill'le: "neredeyse doğru". Stres çarpanı da çok
   modelli evrende her çiftin modelini bozar (`maliyet_carpani`).
2. **Sığmayan kapı küçültülmez, "ölçülemedi" olur.** `pencereler(isinma_bar=…)`: depo pencere
   başından geriye gitmiyorsa ısınma verinin başından alınır; walk-forward katmanları veriye
   sığmazsa liste boş döner ve `wf_*` kapıları ölçülemez (`degerlendir` → `olculemedi`). Rejim
   kıyası FX'te `EURUSD`; K-058 eşiği BTC'de kalibre, FX'te **kalibre değil** ve 14 haftalık
   pencerede ölçülemiyor. Kapı eşiklerine dokunulmadı.
3. **Yeni aile `zaman_serisi_trend`** (`_Kesitsel` iskeleti, sıralama yerine `roc > 0` eşiği;
   yükselen yoksa nakit; yalnız uzun — kısa bacak K-095'te yok, sorulmadı). `EVREN_AILELER`e ve
   `coklu_test_evren.SINYAL_OZELLIKLERI`ne (`skor_ham`) kayıtlı; FX null'u **ölçülmedi**.
4. **`fx_fiyat` programı (K-051): bütçe 3, açıldı ve kapandı.** Kaynak farkı ölçümü: FX sepet ×
   BTCUSDT 1h korelasyon −0,006, ortak enstrüman 0, FX çiftleri arası korelasyon medyan +0,076
   (kesit gerçek). Üç çekiliş — `fx_kesitsel_guc` (h53), `fx_kesitsel_ters` (h54),
   `fx_zaman_serisi_trend` (h55) — **koşudan önce** deftere yazıldı (gerekçe + karşı argüman +
   K-061 çıktısı; h53 uyarı 2 / h54 incele 2 kripto aynalarıyla, bilerek; h55 temiz). Izgara 12
   nokta: `pencere` {24, 48, 120, 240} × `azami_enstruman` {3, 5, 10}; 120 bar dengeleme, 0,2 brüt,
   plato. Pencere K-101'in ortak geçerli finansman aralığı (`2023-11..2024-02`, 1.721 bar);
   finansman gevşetilmedi. Kontrol `fx_evren_esit_agirlik` 21 çift / 0,2 brüt, IS-OOS-tam'da
   ayrı ölçüldü.
5. **Sonuç: 0/3 promotion, 1/3 durma-kuralı ölçüsünde kontrolü geçti (h54, +4,0 USD, 11 tur,
   IS negatif).** Hepsinde `asgari_islem` (11-16 < 30), `pbo`, `parametre_perturbasyonu` kaldı;
   `wf_*` ve `rejim` ölçülemedi; `gecici_finansman_modeli` mutlak engel. Sayılar rapor §3'te
   (brüt/net, dört maliyet bileşeni, benchmark farkı, IS/OOS). h54 için **tekrar gereksinimi**
   yazıldı: K-101 dışında geçerli bir finansman aralığı açılınca aynı nokta (240, 10) yeni çekiliş
   harcamadan ikinci bağımsız OOS'ta koşulur; o güne kadar promotion adayı değildir. "Pozitif
   sonuç" otomatik promotion değildir (talimat, K-018).
6. **Açık kalemler (bilerek yapılmadı):** `oos_sharpe` kapısı `yillik_anlamli`yı okumuyor (OOS 21,5
   gün, Sharpe 6 mertebesi anlamsız — h53/h54'te kapı bu yüzden "geçti"); kapı katmanı değişikliği
   ayrı karar. `fx_veri_kur` aylık pencere (K-101 aralığının son 2 haftası kullanılmadı). FX çoklu
   test null'u ölçülmedi; `COKLU_TEST_CEKILIS_SAYISI` 45'te bayat (defter 55). Duman testi
   açıklaması (K-039): yanlış hatla `kesitsel_guc(120,5)` tam pencerede bir kez görüldü (−2,5),
   ızgara ondan önce sabitti — program kaydında yazılı.

### Kanıt

- `tests/unit/test_fx_arastirma.py` (14): FX fixture'ında `kosu` çift başına model/finansman/takvim
  çözüyor ve kayda yazıyor, spread/finansman > 0, `gecici_finansman_modeli` duruyor; stres çarpanı
  çift modellerini ölçekliyor; kripto verisinde üç ayar `None`; `pencereler` ısınma tabanı + boş
  katman; `zaman_serisi_trend` yalnız `roc > 0` (fill barı − 1'de) taşıyor, düşen evrende 0 işlem;
  üç FX çekilişi 12 noktalı/kurulabilir, kayıt ile koşu aynı kimlik; `degerlendir` FX'te 11 kapı,
  `motor.coklu_model=true`, walk-forward `olculemedi`.
- Kripto bit-aynı: `test_coklu_referans`, `test_evren_degerlendirme` (39) değişmeden geçti.
- Gerçek koşu: `tools/r5_fx_kos.py kos` × 3, çekiliş başına ~4 s; OOS hash'leri `a5c33f50fe06` /
  `28c5d102ee06` / `7cca05b02bae`, kontrol OOS `5689acde9405`; seçilen noktanın OOS/IS tekrarı
  kayıtla aynı hash (koşucu aksi hâlde durur).

## K-103 — R6: h54 (`fx_kesitsel_ters` 240/n10) doğrulama turu — iki yeni pencerede OOS negatif, **elendi**

**Durum:** kabul · **Tarih:** 2026-09-21 · **Onay:** Scryne (R6 talimatı: "sadece h54'ü doğrulama
turuna al; parametre arama yok, promotion yok, yeni katman yok") · **Tabi:** K-039 (ölçüt koşudan
önce), K-099 (kontrol), K-101 (aralıklar aynen), K-102 · **Kaynak:**
`docs/research/records/2026-09-21-R6-h54-tekrar.md`, `tools/r6_h54_tekrar.py`,
`research/evren_kosu.py` (`bitis_pazar`, `semboller`), `tests/unit/test_fx_arastirma.py`

### Karar

1. **Pencereler K-101'den türetilir, elle seçilmez.** Bir pencerenin evreni, finansman modeli
   pencerenin sonuna kadar geçerli çiftlerdir (dosyalardan okunur). Elde: W1 21 çift 2023-12-04..
   2024-02-29 (h54'ün kendisi, referans), W2 10 çift 2024-03-01..05-31, W3 4 çift 2024-06-02..07-26
   (haftalık kesim). W3 zayıf: 4 çiftlik kesit, IS bile `yillik_anlamli=False`; yine de koşuldu ve
   öyle etiketlendi. Daha uzun/geniş pencere yok (21 proxy'nin ortak aralığı Mart'ta bitiyor).
2. **Sabit nokta; tek sapma `n`nin oranla ölçeklenmesi** (`round(10/21 × U)`: W2 5, W3 2). n=10'u
   10 çiftte tutmak kontrolün kendisi olurdu. Sinyal (240 bar), dengeleme (120), brüt (0,2), eşit
   ağırlık, seçim payı sabit. Izgara yalnız PBO/pertürbasyon **teşhisi** için koşuldu.
3. **Ölçüt koşudan önce:** yeni pencerede hem IS hem OOS net benchmark farkı > 0 = "aynı yön";
   W2 ve W3'te aynı yön → devam adayı, aksi → elendi. Sharpe ölçüt değil.
4. **Sonuç: elendi.** W2 IS +31,58 USD / **OOS −15,42 USD** (h54 −0,082 % vs kontrol +0,072 %, 5 tur);
   W3 IS +3,15 / **OOS −26,67** (−0,192 % vs +0,075 %, 2 tur). Kalıp: IS'te geçiyor, OOS'ta
   kaybediyor. Kapılar: `asgari_islem` her pencerede kaldı (11/5/2), `pbo` W1 0,428 / W2 0,795
   kaldı, W3 ölçülemedi; pertürbasyon W1 0,475 kaldı, W2/W3 ölçülemedi (IS'te 30 tura ulaşan aday
   yok); wf/rejim ölçülemedi; `gecici_finansman_modeli` mutlak engel. Yeni çekiliş harcanmadı
   (defter 55). h54'ün K-102'deki "tekrar gereksinimi" bu turla **kapandı**: tekrar yapıldı, geçmedi.
5. **Yan bulgu (K-059 görünür):** W2 tam penceresinde NZDCAD'ın sağlayıcı boşluğu haftası (120 bar)
   48 bar sonra sıfır değerlenip `max_drawdown` %4,1 üretti; piyasa kaybı değil, pozisyon çift
   dönünce geri geldi. Politika doğru çalıştı; alt evren koşularında bu kalem raporda taşınmalı.
6. **Kod:** `fx_veri_kur(bitis_pazar=, semboller=)` (araştırma için gerekli, 2 test); koşucu
   `tools/r6_h54_tekrar.py`. Refactor, yeni katman yok.
7. **Defter fotoğrafı yenilendi (K-081 bekçisi):** K-102 defteri 52→55 büyütmüş, fotoğraf
   (`docs/research/coklu-test-olcum.json`) güncellenmemişti — `TestEsigiDefteBagla` kırmızıydı ve
   R5 Paket 5 commit'inde görülmedi (bu paketin düzeltmesi). `tools/faz12_coklu_test.py --deneme 500
   --seed 0 --birlestir` önbellekten yeniden birleştirildi: ölçülebilir 45 aynı, %5 sınırı 1,0039 aynı,
   h53-h55 **ölçülemez** (FX çekilişi kripto null'una girmez; FX null'u açık kalem, K-102/6).

### Kanıt

- W1 koşusu K-102'nin h54 kaydıyla birebir aynı hash (OOS `28c5d102ee06`, kontrol `5689acde9405`);
  IS ızgarasındaki sabit noktanın hash'i tek koşuyla aynı (koşucu `assert`).
- Testler: alt evren meta/hata, tam küme alt evren değil, `bitis_pazar` üst sınırı; FX/araştırma
  testleri geçti.

## K-104 — R6: FX ortalama dönüş ailesi (`fx_ortalama_donus`, h56-h57) — zayıf, aile kapalı; h56 tekrar gereksinimi taşıyor

**Durum:** kabul · **Tarih:** 2026-09-22 · **Onay:** Scryne (R6 talimatı: "yeni aile: yalnız
mean-reversion; 2-3 basit hipotez; küçük parametre seti; zayıfsa aileyi kapat") · **Tabi:** K-039,
K-045 (istisna, ölçümle), K-051, K-061, K-099, K-101, K-102, K-103 · **Kaynak:**
`docs/research/records/2026-09-22-R6-fx-ortalama-donus.md`, `strategy/kutuphane/ortalama_donus.py`,
`research/izgaralar.py` (`FX_DONUS_CEKILISLERI`), `tools/r5_fx_kos.py`, `tests/unit/test_fx_arastirma.py`

### Karar

1. **Aile:** zaman serisi ortalama dönüş, **eşikli** (h54'ün sıralamasından farkı bu): `zaman_serisi_sapma`
   (`(close − sma)/atr14 < −esik`) ve `zaman_serisi_rsi` (`rsi < esik`); eşiği geçen yoksa nakit; yalnız uzun.
   Ortak iskelet `_EsikliDonus`; K-102 motor hattı ve penceresi aynen (aynı IS/OOS barları, aynı kontrol).
2. **Izgara 12 nokta, yoğunluk {2,5} sinyal-seti ölçümünden** (getiri okunmadan: eşiği geçen çift
   ortalama 1,4-4,6, boş hafta %23-85). Eşikler klasik değerler. Program bütçesi 2, kaynak ölçümü kayıtta.
3. **Sonuç:** h56 seçilen (48/1/5): IS +5,84 vs kontrol −10,59 USD; **OOS +22,59 vs +20,76 → +1,82 USD,
   9 tur**; pertürbasyon **1,0** (tek komşu, negatif), pbo 0,482, `asgari_islem` 9, IS'te 12 noktanın 10'u
   geçersiz/negatif, `yillik_anlamli=False`. h57: IS'te hiçbir nokta asgari tura ulaşmadı → seçilemedi,
   **elendi**. Kapılar 0/2. Mutlak engel `gecici_finansman_modeli`.
4. **Aile kapalı, zayıf.** Genişletilmez (durma kuralı). h56 program kuralı gereği **tekrar gereksinimi**
   taşır (K-103 kalıbı: sabit nokta, W2/W3) — ayrı tur, bu pakette koşulmadı; promotion adayı değil.
5. **Yapısal (üç FX programı):** `asgari_islem` (30) haftalık dengeleme × 4,3 haftalık OOS'ta geçilemez;
   sıklaştırmak maliyet (h56 IS'te brütün %55'i), uzatmak finansman modeli ister (K-101). Kapı
   küçültülmedi; FX için pencere sorunu K-101'in çözümüne bağlı.
6. **Defter fotoğrafı** önbellekten yenilendi (57 satır; 45 ölçülebilir, p05 aynı; h53-h57 ölçülemez).

### Kanıt

- Testler: iki sınıf kayıtlı/ızgaralar 12 noktalı ve kurulabilir; fixture'da alınan her sembolde karar
  barında ölçü eşiğin altında; tekdüze yükselen evrende 0 işlem; FX/araştırma testleri geçti.
- K-061: h56 incele 1 (h54 "farklı"), h57 incele 1 (h4 tek sembol RSI "parametre varyasyonu", bilerek).
- Koşu: `tools/r5_fx_kos.py kos` × 2 (~3,5 s); h56 OOS hash `807c7c89cf29`, kontrol `5689acde9405`.

---

## K-105 — R6: FX volatilite/risk-temelli aile (`fx_oynaklik`, h58-h59) — zayıf, aile kapalı; tekrar gereksinimi yok

**Durum:** kabul · **Tarih:** 2026-09-22 · **Onay:** Scryne (R6 talimatı: "volatilite/risk-temelli aile;
en fazla 2-3 basit hipotez; sinyal seçimi ile boyutlandırmayı karıştırma; küçük parametre seti; zayıfsa
kapat") · **Tabi:** K-037, K-039, K-045 (istisna, ölçümle), K-051, K-061, K-099, K-101, K-102, K-104 ·
**Kaynak:** `docs/research/records/2026-09-22-R6-fx-oynaklik.md`, `strategy/kutuphane/oynaklik_filtre.py`,
`research/izgaralar.py` (`FX_OYNAKLIK_CEKILISLERI`), `tools/r5_fx_kos.py`, `tests/unit/test_fx_arastirma.py`,
`runs/fx/oynaklik-kaynak-olcumu.json` (program kaydında)

### Karar

1. **Aile:** oynaklık genişlemesi filtresi — kıyasın (`fx_evren_esit_agirlik`) evreni, eşit ağırlığı, haftalık
   takvimi ve takvim çıpası aynen; `atr(14)/atr(pencere) > esik` olan üye o hafta **nakde** alınır, payı
   kalanlara dağıtılmaz (tavan = filtre öncesi eşit pay; brüt düşer). Seçim yok, boyutlandırma yok; K-037
   engelleyici. İki üye: çift başına (`fx_oynaklik_filtre_cift`) ve evren geneli medyan (`fx_oynaklik_filtre_evren`).
   Eşik sonsuzken kıyasla ekonomik olarak bit-aynı (testle; gerçek IS'te `esik ≥ 1,1` noktaları kıyasın kendisi).
2. **İki eksen çekiliş harcanmadan dışarıda, ölçümle:** ters oynaklık ağırlık (`1/σ`) kapalı tur üretmez
   (üyelik değişimi 0, toz eşiği 0,11 çift/hafta); düşük oynaklık seçimi IS'te en çok 14 tur (asgari 20).
   İkisi de bu pencere ve bu kapıyla **yapısal olarak ölçülemez**; kapı küçültülmedi, çekiliş harcanmadı.
3. **Izgara 12, eşikler ölçülen dağılımdan** (getiri okunmadan): oran q10 0,82-0,89 / q50 ≈ 1 / q90 1,11-1,26
   → esik {0,9; 1,0; 1,1; 1,2}, pencere {48, 120, 240}; ATR 14 eksen değil; yoğunluk ekseni yok. Bütçe 2.
4. **Sonuç:** h58 seçilen (48 / 0,9): IS **+10,20 vs kontrol −10,59** (+20,79 USD); **OOS +4,57 vs +20,76 →
   −16,20 USD**, 12 tur; durma kuralı ölçüsünde geçemedi (4,44 < 6,08); `asgari_islem` 12, pbo 0,278,
   pertürbasyon 0,859 (izole tepe), evren dayanıklılığı 0,64 (USDJPY) kaldı. h59 seçilen (48 / 0,9): IS +1,87
   vs −10,59; **OOS'ta 4/4 dengelemede nakit, 0 tur, 0,00 vs +20,76 → −20,76 USD**. Kapılar 0/2; `yillik_anlamli`
   yok; mutlak engel `gecici_finansman_modeli`. Kalıp: filtre yalnız maruziyet düşürür, kıyasın negatif ayında
   kazanır, pozitif ayında kaybeder (`−β × kıyas`); maliyet bağlayıcı değil (h58 OOS'ta brütün %10'u).
5. **Aile kapalı, zayıf. Tekrar gereksinimi yok** (hiçbiri OOS'ta kontrolü geçmedi). Genişletilmez.
6. **Yapısal (dört FX programı):** `asgari_islem` (30) haftalık dengeleme × 4,3 haftalık OOS'ta geçilemez;
   filtre ailesinde ayrıca eşiğin gövdeden uzak yarısı IS'te tur üretmiyor (etkin ızgara 6/12). K-104/5 aynen.
7. **Defter fotoğrafı** önbellekten yenilendi (59 satır; 45 ölçülebilir, p05 1,0039 aynı; h53-h59 ölçülemez).

### Kanıt

- Testler: iki sınıf kayıtlı, ızgaralar 12 noktalı, kurulabilir, `kiyas=False`; eşik sonsuzken kıyasla
  metrik/işlem/özkaynak/maruziyet eşit (yalnız ısınma atlama sayacı farklı, fixture ısınması kısa); çift
  elenince pay nakitte (maruziyet kıyasın altında, alınan her çiftte karar barında oran ≤ eşik); evren
  filtresi ya hepsi ya hiçbiri (nakde geçilen barda medyan > eşik). FX/araştırma testleri geçti.
- K-061: h58 uyarı 0 / incele 0; h59 uyarı 0 / incele 0 ("benzer mekanizma bulunmadı").
- Koşu: `tools/r5_fx_kos.py kos` × 2 (4,7 s / 4,6 s); h58 OOS hash `b5acf4f53869`, h59 `f9a3de7e72e3`, kontrol
  `5689acde9405` (h53-h57 ile aynı).

---

## K-106 — R6 kapanışı: FX alfa araştırması (h53-h59) sonuç FAIL; mevcut kapsamda doğrulanmış FX alfası yok

**Durum:** kabul · **Tarih:** 2026-09-22 · **Onay:** Scryne ("R6 FX alpha araştırmasını kapat; yeni hipotez,
grid, kod yok; yalnız mevcut kayıtlardan kapanış dokümanı") · **Tabi:** K-045, K-051, K-101, K-102, K-103,
K-104, K-105 · **Kaynak:** `docs/research/records/2026-09-22-R6-kapanis.md`

### Karar

1. **R6 kapandı, sonuç FAIL.** Üç program (`fx_fiyat`, `fx_ortalama_donus`, `fx_oynaklik`; 7/7 çekiliş) ve
   h54 tekrar turu: kapılar 0/7, tekrar eden OOS üstünlüğü 0/7, promotion adayı yok. Program kaydı + bütçe
   kalıbı üç kez uçtan uca işledi; her programın kapanış raporu var.
2. **İddianın kapsamı sınırlı:** 21 FXCM çifti, 1h, K-101 proxy penceresi (2023-11..2024-02; tekrar için
   2024-03..07 alt evrenleri), haftalık dengeleme, yalnız uzun, test edilen yedi mekanizma ve mevcut kapılar.
   "FX'te alfa yok" **denmiyor**.
3. **Kapanış dokümanı** ölçülemeyen kapıları (walk-forward, rejim, FX null), `yillik_anlamli=False`'un
   etkisini (dört "geçti" Sharpe'ı kanıt değil), `asgari_islem`in yapısal kapalılığını, proxy finansman
   engelini ve dönüş koşullarını (ölçülmüş tarihli finansman, ≥1 yıl finansman-geçerli veri, FX null,
   `oos_sharpe`↔`yillik_anlamli`, kısa bacak, rejim kalibrasyonu) tek yerde toplar.
4. **Açık kalan tek kalem:** h56 tekrar gereksinimi (K-104) — koşulmadı; R6 kapanışında takip edilmiyor,
   dönüş koşulları sağlanınca yeni çekiliş harcamadan koşulur.
5. Yeni hipotez/ızgara/kod yok; mevcut sonuçlar değiştirilmedi; defter 59.

---

## K-107 — R7 ön koşul: FX finansman/veri penceresi genişletme **BLOCKED**; promotion'a açık FX günü 0; R7 kripto evreninde yürür

**Durum:** kabul · **Tarih:** 2026-09-22 · **Onay:** Scryne ("R7'nin ilk işi FX finansman/veri penceresini
genişletmek; proxy'yi gerçekmiş gibi kullanma; veri yoksa FAIL/BLOCKED yaz, boşuna altyapı geliştirme") ·
**Tabi:** K-088, K-090/5, K-091, K-098, K-100, K-101, K-106 · **Kaynak:**
`docs/research/records/2026-09-22-R7-fx-finansman-penceresi.md`

### Karar

1. **Hazır olan:** fiyat indirici + arşiv (2012→, 21 çift; indirilen 55 hafta), takvim/rollover anları/kalite/PIT,
   motorda finansman aralık denetimi, çift başına ölçülmüş maliyet. **Eksik olan:** gerçek tarihli finansman
   kaynağı — 21/21 proxy (`gecici`).
2. **Mevcut geçerli pencere (proxy):** 21 çiftin ortak aralığı fiilen 2023-11-19..2024-03-18 (120 gün; kullanılan
   2023-11..2024-02, 1.721 bar); en uzun çift AUDNZD/NZDUSD 269 gün; ≥365 gün **0 çift**; promotion'a açık gün
   **0** (engel pencereye değil kaynağa bağlı, K-101/2).
3. **≥1 yıl:** fiyat için evet (yalnız indirme); finansman için yalnız yeni proxy segmentleriyle — bu yalnız
   araştırma kapılarını ölçülebilir kılar, promotion'a bir gün açmaz → **yapılmadı**. Gerçek tarihli FXCM
   rollover arşivi K-101'de ve bugünkü yeniden taramada **yok**; uydurulmadı.
4. **BLOCKED.** Kilit tek: `config/finansman/fxcm-<pair>.json` içinde `tur=broker`, aralık ≥365 gün, en az bir
   çift. Bilinen tek üretim yolu ileriye dönük (FXCM hesabında günlük `Roll S`/`Roll B` kaydı; geriye doldurmaz;
   hesap gerektirir) — Scryne kararı, başlatılmadı.
5. **R7 FX'i beklemez:** portföy kurma kripto evreninde (gerçek funding, proxy yok) yürür; FX tetik sağlanınca
   sırasıyla fiyat indirme, FX null, `oos_sharpe`↔`yillik_anlamli`, h56 sabit nokta.
6. Kod, proxy, çekiliş, motor değişikliği **yok**.

---

## K-108 — R7(1): kripto evreninde ilk portföy kurma programı (`portfoy_kurma`, h60-h61) — 0/2, aile kapalı

**Durum:** kabul · **Tarih:** 2026-09-22 · **Onay:** Scryne ("R7'yi kripto evreninde başlat; 2-3 basit portföy
mekanizması; IS/OOS; kıyas sabit; PBO/pertürbasyon/işlem kapıları; tek OOS başarısıyla promotion yok; negatifse
kapat") · **Tabi:** K-019, K-033, K-037, K-039, K-044, K-050, K-051/4, K-061, K-070, K-072, K-073, K-079 ·
**Kaynak:** `docs/research/records/2026-09-22-R7-portfoy-kurma-1.md`, `strategy/kutuphane/evren_portfoy.py`,
`strategy/kutuphane/evren_esit_agirlik.py` (`_korelasyon_icin`), `research/izgaralar.py` (`PORTFOY_CEKILISLERI`),
`tools/faz12_evren_kos.py`, `tests/unit/test_evren_portfoy.py`, `runs/faz12/portfoy-kaynak-olcumu.json`

### Karar

1. **Program:** `portfoy_kurma`, bütçe 2, iki mekanizma, ikisi de kıyasın seçimi/sıralaması/takvimi üstüne yalnız
   kurma değişikliği (Faz 16 iskeleti): korelasyon budaması (`kur(korelasyon=)` — Faz 16'da "var olmayan makine";
   kıyas kancası `None` → bit-aynı) ve **yalnız düşüren** oynaklık hedefi (K-050; hedefler ölçülen IS dağılımından,
   getiri okunmadan). Optimizasyon (ERC/min-var) açılmadı. Kripto evreni spot: gerçek funding verisi var ama motorda
   maliyet değil (K-079), sinyal olarak K-068'de kapalı → bu programda **ne maliyet ne sinyal**, uydurulmadı.
2. **h60 korelasyon budaması: elendi.** Seçilen (0,5 / n20) OOS Sharpe −1,11 vs kıyas −0,26, net −893,76 USDT, DD
   31,2 % vs 27,4 %; maruziyet yarıya iniyor (budama dolduramıyor), hayatta kalanlar likiditesi düşük → maliyet ve
   tur artıyor; `oos_is_orani` −1,93. 4/11 kapı. Ön yazılı karşı argüman gerçekleşti.
3. **h61 oynaklık hedefi: elendi, Sharpe-nötr.** Seçilen (0,010 / n5) OOS Sharpe 0,4606 vs kıyas 0,4617; DD, getiri
   ve maruziyet aynı oranda (×0,66) → zaman-değişken kaldıraç düşürmenin mekanik sonucu, σ_t'de zamanlama bilgisi
   yok. 7/11 kapı (`oos_is_orani` 0,845, walk-forward 0,633, evren dayanıklılığı 1,00; pbo 0,042 defter en düşüğü,
   eşik 0,0087; pertürbasyon 0,193; rejim 0,124). Durma kuralı (kıyas ∧ 0,333) geçilmedi → doğrulama adımı yok.
4. **Aile kapalı; yeni portföy kapısı tanımlanmadı.** Faz 16'nın bulgusu ikinci kez ölçüldü: kurma katmanı risk
   profilini değiştirir, risk-ayarlı getiriyi değil. Oynaklık hedefi bir promotion kapısı değil, risk iştahının
   (K-033 `azami_brut_maruziyet`) ifadesi olabilir — ayrı karar, bu pakette verilmedi.
5. **Kod:** iki strateji sınıfı, kıyasta bir kanca (varsayılan `None`, kripto kıyası bit-aynı: `test_evren_kurma`
   bant testi + `test_coklu_referans`), ızgara/program/sinyal özelliği kayıtları, +13 test. Execution/risk/audit
   değişmedi; FX işi yok. Araştırma yolu risk motorsuz (K-073 aynen).
6. **Çoklu test:** h60/h61 null'u ölçüldü (500 deneme, seed 0; 82 + 48 dk), fotoğraf yenilendi: ölçülebilir
   45 → **47**, %5 sınırı 1,0039 aynı, sabit 1,04 korunuyor; `COKLU_TEST_CEKILIS_SAYISI` 45 → 47 (K-081 kuralı:
   sabit yalnız karar kaydıyla güncellenir). Defter 61.

---

## K-109 — R7(2): kripto alfa/sinyal turu — K-068 ön koşulu ölçüldü, tek aday (kesitsel düşük oynaklık, h62) kıyas altı; FAIL

**Durum:** kabul · **Tarih:** 2026-09-22 · **Onay:** Scryne ("R7(2)'de doğrudan kripto alpha/sinyal araştırmasına
geç; 2-3 basit sinyal; 11 kapı; null eşiği değiştirme; tek OOS başarısı promotion değil; zayıfsa kapat") ·
**Tabi:** K-039, K-044, K-045, K-051, K-061, K-068 (geri dönüş koşulu), K-072, K-078 (sınırlı istisna), K-108 ·
**Kaynak:** `docs/research/records/2026-09-22-R7-kesit-oynaklik.md`, `tools/r7_sinyal_gucu.py`,
`runs/faz12/r7-sinyal-gucu.json`, `research/izgaralar.py` (`KESIT_OYNAKLIK_CEKILISLERI`)

### Karar

1. **K-078/1'e sınırlı istisna, K-068 koşuluyla.** K-078/1 fiyat-türevli hattı "yeniden açılmaz" yazmıştı; Scryne'ın
   talimatıyla hat, K-068'in **ölçülebilir** geri dönüş koşulu (yalnız IS'te ileriye dönük sıralama gücü, |t| ≥ 2 ∧
   IS iki yarısında aynı işaret; koşudan önce yazıldı) uygulanarak açıldı. Ölçüm çekiliş değildir; OOS'a bakılmadı.
2. **Ön koşul sonucu:** 11 sinyalden (ts momentum 168-1440, ts ters 24-168, sapma 168/720, hacim şoku, düşük
   oynaklık 14-1440) yalnız **kesitsel düşük oynaklık** geçti (IC +0,11..+0,14, t 6-7,8). Diğerleri açılmadı,
   çekiliş harcanmadı. Program `kesit_oynaklik` (bütçe 2; Faz 12'nin hiç harcanmamış `kesitsel_dusuk_oynaklik`
   ızgarası aynen; yeni kod yok).
3. **h62 (1440 / n5): elendi.** IS Sharpe 0,929 (12/12 pozitif) → OOS 0,287 vs kıyas n10 0,302 (< ikinci çizgi
   0,333); net +603 vs +926 USDT; DD 12,7 % vs 18,8 %; `oos_is_orani` 0,31; `evren_dayanikliligi` 0,22 (XRP çıkınca
   0,06); pbo 0,11; pertürbasyon 0,15; rejim 0,11; **5/11**. Aylık çekiliş durma kuralı gereği harcanmadı (1/2).
   Aile kapalı, tekrar gereksinimi yok.
4. **Ek kural:** IS IC'si K-068 ölçütünü geçen bir sinyal yalnızca **aday**dır; sıralama gücü kıyas-üstü olma
   iddiası taşımaz (h62: t ≈ 7 IC, OOS kıyas altı — IC'nin kaynağı büyük ölçüde yüksek oynaklı isimlerin ortalama
   kaybı). İşaret testinde |t| ≥ 2 veren `roc720` (devam) ve `roc72` (devam) IC ölçütünü geçmedi; kayıt yalnız
   bilgi, açılmaz.
5. **Sonuç (kapsamlı):** mevcut veri (spot, 429 sembol PIT), evren kuralı, pencere ve 11 kapı kapsamında
   fiyat/hacim türevli kesit/ts sinyallerinde doğrulanmış kripto alfası yok; K-078/1'in yapısal okuması
   (eylem uzayı ve veri sınıfı açık, fiyat geçmişi hattı tükenmiş) **pekişti**. Evrensel iddia değil.
6. **Çoklu test:** h62 null'u ölçüldü (500/0, 50 dk), fotoğraf 47 → **48** ölçülebilir, %5 sınırı 1,0039 aynı, sabit
   1,04 değişmedi; `COKLU_TEST_CEKILIS_SAYISI` 48 (K-081 kuralı).

---

## K-110 — R6+R7 kapanış değerlendirmesi: K-078/1 desteklendi; yeni alfa hattı açılmıyor; tek kilit K-079/2

**Durum:** kabul · **Tarih:** 2026-09-22 · **Onay:** Scryne ("R6+R7'yi birlikte değerlendir; elenenleri kayda geç;
K-078/1'i ölç; evrensel sonuç çıkarma; test edilmemiş kaynak envanteri; gerekliyse en az altyapılı hattı öner;
yeni kod/grid/refactor yok") · **Tabi:** K-044, K-045, K-068, K-072, K-077, K-078, K-079, K-106, K-107, K-108,
K-109 · **Kaynak:** `docs/research/records/2026-09-22-R7-kapanis-alfa-envanteri.md`

### Karar

1. **R7 kapandı, sonuç FAIL** (K-107 BLOCKED, K-108 0/2, K-109 0/1). R6 ile birlikte 10 çekiliş, 0 kapı geçen,
   0 tekrar eden kıyas-üstü OOS.
2. **K-078/1 ("fiyat-türevli long-only hat tükenmiş") bugünkü kanıtla desteklendi — kapsam içinde:** 48 ölçülebilir
   çekilişin gerçekleşen OOS Sharpe'ı kendi null dağılımında medyan persentil 0,50 (tek sembollü 31) / 0,45 (evren
   17); null p95'i aşan 0/31 ve 2/17 (şansla beklenen 0,85; ikisi de kıyas-üstü değil); IS'te 11 fiyat/hacim
   sinyalinden 10'u |t| < 2; defter 62'de en iyi OOS 0,46 < null %5 sınırı 1,004 < kapı 1,04. Kapsam: Binance spot
   1h PIT `27b7a16ed0ed` 2019→2025, FXCM 21 çift 2023-11→2024-02, long-only kaldıraçsız, §3'teki aileler, K-054/K-058
   kapıları. **Evrensel iddia değil.**
3. **Tükenen aileler tekrar denenmez** (doküman §3): tek sembol TA, funding yönlü, kesitsel momentum/ters/düşük
   oynaklık, kıyas-üstü dışlama (8 kaynak), rejim/seçici/Jev yönü, kurma katmanı, FX seçim/dönüş/oynaklık, duyuru
   long, funding-anı ve NY çapası mikroyapısı. "Farklı parametre/pencere/eşik" açılış değildir.
4. **Envanter (A-H):** mevcut veriyle hemen ölçülebilen yalnız A (cross-asset/makro→kripto) ve G (opsiyon IV) IS IC
   ön koşulu — ikisi de K-068 sınıfı (kıyas-üstü filtre), **önerilmez**. Mekanizması farklı tek hat B (delta-nötr
   carry; C ona bağlı): veri var, kilit K-079/2 hesap kararı; D/E/F veri sınıfı hatları ileriye toplama/bütçe ister.
5. **Yeni araştırma hattı açılmıyor; kod yok.** Tek uygulanabilir adım Scryne'ın K-079/2 kararı: korunuyorsa
   araştırma programı askıya alınır (defter 62'de donar) ve **R8 paper koşusu kıyasla açılır** (kanıt değil, yol
   testi); açılıyorsa Hat B ikinci tavanı mevcut araçla (`tools/faz16_hat1_ikinci_tavan_kismi.py`) ölçülür,
   K-079/6 kuralıyla.
6. Bu karar hiçbir kapı, eşik, kapsam ya da yetki değiştirmez.

---

## K-111 — Araştırma programı askıda (defter 62); R8 paper/gözlem operasyon koşusu açıldı, kriterleri dondurulmuş

**Durum:** kabul · **Tarih:** 2026-09-22 · **Onay:** Scryne ("K-079/2 korunuyor; R7 kapalı; yeni alfa/hipotez/veri/
çekiliş yok; programı askıya al, defteri 62'de dondur; R8 paper koşusunu aç ama alfa kanıtı olarak sunma;
kriterleri önceden tanımla, sonradan eşik değiştirme") · **Tabi:** K-004, K-007, K-009, K-010, K-021, K-035,
K-037, K-038, K-043, K-050, K-052, K-069, K-079, K-082, K-110 · **Kaynak:**
`docs/research/records/2026-09-22-R8-paper-protokol.md`, `config/r8_kriterler.json` (SHA-256 `2c3d520e8f3fe5d278ac5bc054363f4e0c34b7b7ed2ad726b793469873d4cdf5`)

### Karar

1. **Araştırma programı askıda.** K-079/2 (vadeli hesap açılmıyor) korunuyor; R7 kapalı (K-110). Hipotez defteri
   **62'de donar**: yeni çekiliş, hipotez, aile, veri kaynağı, araştırma hattı açılmaz; elenen aileler yeniden
   açılmaz; kıyas değişmez. Askıdan çıkış yalnız Scryne kararıyla ve K-051 program kaydıyla.
2. **R8 açıldı — amaç operasyon kanıtı, alfa değil.** Koşu `r8-kiyas`: kıyas `evren_esit_agirlik` n=10 haftalık
   0,2 brüt, **gözlem modu** (K-035; `paper` promotion ister ve promotion geçmiş strateji olmadığı için her sinyali
   reddederdi — execution/recovery ölçülemezdi), host-1, **2026-09-25** K-069 kapanışında K-043 planlı durdurma
   yordamıyla (kod senkronu + testler) başlar, **14 gün** (iki dengeleme + 1 Ekim ay sınırı). Pencere içinde hosta
   dokunulmaz; ≥ 1 planlı durdur/başlat açık pozisyonla zorunlu.
3. **Kriterler önceden dondurulmuş** (`config/r8_kriterler.json`, hash yukarıda): 10 alan — veri akışı, PIT evren,
   sinyal/benchmark üretimi, maliyet, risk kapıları, karar/seal, paper execution, idempotency/recovery, audit
   trail, monitoring — her biri mevcut araç (`evren-durum`, `izle kontrol`, `evren-tatbikat`, `evren-sapma`,
   run-içi zincirli risk defteri) ve mevcut eşiklerle (`izleme.ESIKLER`, K-004/007/009/038/043/052/082).
   **10/10 PASS, biri kalırsa FAIL; eşik pencere içinde ve sonrasında değiştirilmez.** Ölçüm dışı: Sharpe, getiri,
   benchmark farkı, promotion, `ASGARI_PAPER_GUN` (30, K-069/3 aynen).
4. **Roadmap R8 satırı düzeltildi:** "kanıt üreten paper" → "operasyon koşusu"; `--mod paper` bayrağı ve
   `ASGARI_PAPER_GUN` fill koşulu R8'den çıktı (biri ölçülemez, öteki promotion'a ait).
5. **Başlangıç noktası kaydedildi** (salt okunur SSH, 2026-09-22 09:00 UTC): `evren-kiyas` adım 884, 8 pozisyon
   (RLUSDUSDT dahil — bilinen kural açığı, koşu ortasında değiştirilmez), 3 kopma (hepsi ≤ 31 s'de bağlandı),
   3 `toparlandi`; `host-1` 4,81 gün, kesinti 5. Sebepler 25 Eylül'de host günlüğünden okunur; K-069 kararı
   burada verilmez.
6. **Kapanış:** pencere sonunda ayrı kayıt (`<tarih>-R8-kapanis.md` + K-112) — ölçülen 10 alan, PASS/FAIL,
   giderme/R9 kararı. Bu paket kod değiştirmez.

## K-113 — `oos_sharpe` kapısı `yillik_anlamli`yı okur; `oos_suresi` ayrı kapı; Threshold-Policy §2 `config/esikler.json`'da kabul

**Durum:** kabul · **Tarih:** 2026-09-22 · **Onay:** Scryne ("R5 artıklarını şimdi kapat; `oos_sharpe` ↔
`yillik_anlamli` semantiğini denetle ve düzelt; kapıyı gevşetme, K-050 asimetrisine uygun sıkılaştır; minimum
geçerli OOS koşulu ile Sharpe anlamlılığı açıkça ayrışsın; Threshold-Policy kabulünü `config/esikler.json` ile
tamamla, eşik değişikliği tuning mekanizmasına dönüşmesin; R8 öncesi bitsin") · **Kapatır:** K-102/7 açık
kalemi, K-106 dönüş koşulu 4, R5 "Threshold-Policy kabul" · **Değiştirir:** K-019 (kapı listesi 7 → 8; iki
kapıya ön koşul) · **Tabi:** K-007, K-010, K-018, K-019, K-044, K-050, K-054, K-081, K-111 · **Kaynak:**
`docs/research/records/2026-09-22-R5-oos-suresi.json` (`tools/r5_oos_suresi_olcum.py`),
`docs/research/records/2026-09-22-R5-oos-kapi-once-sonra.json` (`tools/r5_oos_kapi_once_sonra.py`),
`docs/research/records/2026-09-22-R5-K113-oos-kapisi.md`

### Mevcut semantik (denetim)

- `Metrikler.yillik_anlamli` (Faz 4): ölçülen pencere `bar × timeframe ≥ 30 gün` ise `True`. Docstring'i
  *"Promotion kapıları (K-019) bu bayrağa bakmak zorunda"* diyordu; **hiçbir kapı bakmıyordu.**
- `research/degerlendirme.py` ve `research/evren_degerlendirme.py` `oos_sharpe = metrikler.sharpe` yazıyor,
  `kapilar.degerlendir` bunu doğrudan `≥ 1,04` ile karşılaştırıyordu. Sharpe `mean/std × √(bar/yıl)`: 21,5
  günlük OOS'ta +0,21 % getiri 6,08 ediyor (K-102/7). Kapı bunu "geçti" sayıyordu: R5/R6 kayıtlarında
  h53 (1,09), h54 (6,44), h56 (5,58), h58 (4,44) `oos_sharpe` ✓ görünüyor (`…once-sonra.json`, "önce").
- OOS süresi ile eşik arasında hiçbir bağ yoktu. Oysa 1,04 bir null dağılımından ölçüldü ve o null
  fotoğraftaki 48 çekilişin **kendi OOS pencerelerinde** koşuldu: 13.672 bar 1h (569,67 gün), 3.484 bar 4h
  (580,67 gün), 23.826-23.862 bar evren (992,75-994,25 gün). Sharpe kestiriminin dağılımı OOS kısaldıkça
  genişler; kısa OOS'ta null'un %5 sınırı 1,04'ün **üstündedir**. 1,04'ü 21,5 güne uygulamak kapıyı
  ölçülmemiş biçimde gevşetmekti.
- Promotion'a etkisi **bugüne kadar sıfır**: dört "geçti" çekilişin hepsi başka kapılarda kaldı
  (`asgari_islem`, `pbo`, pertürbasyon, mutlak engel), toplam PASS 0/78 kayıt. Ama zincirin tek savunması
  "başka kapı tutar" olamaz (K-037'nin ruhu): promotion kaydına giden `kapi_sonucu` bu değeri taşıyordu.

### Karar

1. **`oos_sharpe` ve `oos_is_orani` ön koşullu:** `Esik.on_kosul="oos_yillik_anlamli"`. Ön koşul
   **tam olarak `True`** değilse (False, eksik, 1, "True" — hepsi sağlanmadı) kapı `gecti=None`
   (ölçülemedi), değer kayda girer, karar girmez; satıra `on_kosul: {alan, deger}` yazılır. Ölçülemeyen
   kapı geçilmiş sayılmaz (K-019). Ön koşul yalnız `True`'yu `None` yapar; hiçbir yolla `False`'u
   `True` yapamaz (testli).
2. **Yeni kapı `oos_suresi`:** alan `oos_gun` (ölçülen bar × timeframe / gün — `yillik_anlamli` ile aynı
   ölçek, bar-zamanı; seanslı takvimde takvim gününden küçük, bilerek), sınır
   `ASGARI_OOS_GUN = 13.672 × 1h / 24 = 569,666… gün`, yön `≥`. Sınır fotoğraftaki en kısa OOS'un
   **kendisi**; yuvarlanmadı — kalibrasyon kümesinin üyeleri tanım gereği geçmeli. (Ölçüldü: 570'e
   yuvarlama 1h tek sembollü 31 çekilişin tamamını `oos_suresi`de bırakıyordu; sınır bir kestirim değil,
   kayıtlı bir bar sayısı.) Daha uzun OOS'ta 1,04 tutucudur (K-007 yönünde), daha kısasında kapı
   ölçülemez. Fotoğraf değişince `tools/r5_oos_suresi_olcum.py` yeniden koşulur;
   `test_esikler.py` sabiti kayıtla ve fotoğrafla eşit tutar.
3. **İki koşul ayrı ve ikisi de gerekli:** (1) yıllıklandırma yorumlanabilir mi (30 gün, ön koşul) —
   (2) eşik bu uzunlukta ölçülmüş mü (569,67 gün, kapı). 30 ≤ OOS < 569,67 günde Sharpe okunur ama
   kapı kalır; ≥ 569,67'de eski mantık birebir (1,04, `≥`).
4. **Ölçüm katmanı** iki alanı üretir: `oos_yillik_anlamli` (`Metrikler.yillik_anlamli` aynen) ve
   `oos_gun` (`kapilar.oos_suresi_gun(ozkaynak.size, timeframe_ms)`), tek sembollü ve evren yolunda
   aynı. `oos_sharpe` sayısı **silinmez** (rapor/DSR/çoklu test aynen okur). `Metrikler`e dokunulmadı:
   backtest çıktısı ve `sonuc_hash` bit-aynı.
5. **Threshold-Policy §2 kabulü = `config/esikler.json`** (SHA-256 `040219d6232aca5d132b2b541fb60b08b015d8834dc27bab6266d32b86f58b4b`). Kayıt, ayar değil: kod
   dosyayı **okumaz** (statik testli); 12 kapı + 3 girdi (`asgari_yillik_pencere_gun` 30,
   `coklu_test_cekilis_sayisi` 48, `yanlis_pozitif` 0,05) her biri `kaynak` ∈ {olculdu, istah,
   null-kalibre, politika}, `karar` (Kararlar.md'de başlık olarak var olmak zorunda), ölçülmüşse
   `kayit` + `olcum_tarihi`, iştahsa `gozden_gecirme`. Bir eşiği değiştirmek = kod + JSON + yeni K
   aynı anda; biri eksikse `test_esikler.py` kırmızı. Tuning'e kapalı olmasının mekanizması bu:
   JSON tek başına hiçbir davranışı değiştiremez, kod tek başına testi geçemez.
   **DECISION REQUIRED kalemleri (Threshold-Policy §2/§5/§6) dosyaya girmedi:** karar verilmemiş sayı
   eşik değildir; liste olduğu yerde açık kalır, Scryne'ın kararını bekler.
6. **Kapsam dışı (bilerek):** `rejim_kararliligi` (30 günlük rejim pencereleri, kendi null'u),
   `wf_sharpe` (kapı değil), `parametre_kararliligi` — hiçbirine dokunulmadı; `oos_sharpe` eşiğinin
   sayısı (1,04) ve fotoğrafı değişmedi. Yeni hipotez/çekiliş/koşu yok; defter 62 (K-111).

### Önce / sonra (yalnız mevcut kayıtlardan, yeni koşu yok — `…once-sonra.json`)

| | önce | sonra |
| --- | --- | --- |
| Kayıt | 78 (7 FX · 17 evren · 54 tek sembollü satır) | 78 |
| `oos_sharpe` ✓ | **4** — h53 1,09 / h54 6,44 / h56 5,58 / h58 4,44, hepsi OOS 21,5 gün | **0** (dördü `—` ölçülemedi, `on_kosul.deger=False`) |
| `oos_suresi` | yok | 6 FX kaydı ✗, 72 kripto kaydı ✓ (569,67-994,25 gün) |
| Toplam PASS | 0 | 0 |
| Gevşeyen kapı (herhangi bir kayıtta `✗/—` → `✓`) | — | **0** |

K-102/7'nin vakası: OOS 516 bar / 21,5 gün, kontrol Sharpe 6,08 → önce `oos_sharpe` ✓, sonra
`oos_sharpe` `—` + `oos_is_orani` `—` + `oos_suresi` ✗ (`test_kapilar.TestOosSuresiVeSharpeAnlamliligi`).

### R8'e etkisi

**Sıfır.** Değişen paketler `research/` (kapilar, kapilar_v2, degerlendirme, evren_degerlendirme) ve
`tools/`; `paper/`, `risk/`, `execution/`, `oms/`, `backtest/`, `strategy/` hiçbir `research` modülünü
import etmiyor (doğrulandı), `Metrikler`/`Sonuc` değişmedi. R8 gözlem koşusu kapı değerlendirmesi
yapmıyor (K-111/3 ölçüm dışı: Sharpe, promotion). 25 Eylül kod senkronu bu commit'i taşır; R8
penceresinde `research/` dahil hiçbir şey değişmez.

### Değişmez (yeni)

> Yıllıklandırılmış bir OOS metriği, yıllıklandırmanın anlamlı olmadığı pencerede kapı kararı
> üretemez; null-kalibre bir eşik, kalibre edildiği en kısa OOS'tan kısa pencerede okunamaz. İkisi
> de "ölçülemedi"dir, "geçti" değil.

## K-114 — Execution altyapısı (R9 teknik kısmı) tetikten bağımsız kodlandı; canlı aktivasyonun kapıları değişmedi

**Durum:** kabul · **Tarih:** 2026-09-22 · **Onay:** Scryne ("Live trading'e giden bütün teknik yolu şimdi
mümkün olduğunca tamamla … gerçek para ile işlem gönderen yolu gizlice etkinleştirme, approval/risk
gate/promotion bypass etme, R8 PASS varsayma; bunların dışındaki execution altyapısını tamamlamak için
tekrar izin isteme") · **Değiştirir:** Faz-8-Hazirlik §0 "tetik gelmeden kod yazılmaz" ve §5/4'ün
zamanlaması (kod şimdi; aktivasyon yine tetikli) · **Kapatır:** Faz-8-Hazirlik §6/7 (canlı modül + AST
sınırı) · **Tabi:** K-004, K-007, K-008, K-009, K-010, K-032, K-035, K-037, K-038, K-041, K-046, K-047,
K-050, K-065, K-082, K-111 · **Açık bırakır:** Faz-8-Hazirlik §6/1-6 (`config/kademe.json` `kararlar`,
`DECISION REQUIRED`)

### Karar

1. **Mod durum makinesi** (`execution/mod.py`): `DISABLED → PAPER → SHADOW → TESTNET →
   LIVE_PENDING_APPROVAL → LIVE`. Yukarı yalnızca bir adım ve hedef modun kontrol listesi geçerse;
   aşağı her zaman, onaysız (K-050). `LIVE` yalnızca `canli_onayla` ile — onu yalnızca
   `sq execution onayla` (TTY, rapor hash'inin ilk 8 karakteri elle, ≥20 karakter not) çağırır, AST
   testli. Kayıt zincir hash'li + audit'e bağlı (`OlayTuru.EXECUTION`); kırık zincir DISABLED okunur.
2. **Live gate** (`execution/canli_kapi.py`): kontrol listesi — mod kaydı, R8 sözleşme hash'i, risk
   config, paper/testnet/shadow koşu kanıtları, **strateji promotion `LIVE`** (K-010, K-082 audit
   çapraz kontrolü), **R8 PASS kaydı** (`config/operasyon_dogrulama.json`, K-112; önceden varsayılmaz),
   kademe tablosu (risk sermayesi + Kademe 1 sermayesi + onay), açık kararlar kapalı, venue statüsü
   `AÇIK`, canlı host kill tatbikatı, HEAD'de yeşil test kaydı, açık SAFE_MODE/halt/UNKNOWN yok, işlem
   anahtarının `apiRestrictions`ı (spot işlem açık; çekim/transfer/margin/futures kapalı; IP kısıtlı),
   canlı bağlantı. Ölçülemeyen kontrol geçmiş sayılmaz. **Eşik icat edilmedi:** her sayı mevcut bir
   karardan ya da `config/kademe.json`da `DECISION REQUIRED`/`null` olarak Scryne'dan.
3. **`CanliYetki`** (`exchange/yetki.py`): mühürlü, süreç başına rastgele anahtarla imzalı belirteç;
   yalnızca `canli_yetki_ver` üretir (AST testli) ve yalnızca mod LIVE + kapı **şimdi** geçiyor + rapor
   hash'i onay satırındaki hash'le aynıysa. Diske yazılmaz; her canlı başlangıçta yeniden türetilir.
   Onaydan sonra karar değiştiren bir şey (kod commit'i, strateji aşaması, kademe, anahtar yetkisi…)
   değişirse yeniden onay gerekir.
4. **Canlı host yalnızca `exchange/canli.py`de** ve oraya yalnızca `cli/execution.py`,
   `trader/kurulum.py`, `execution/canli_kapi.py` ulaşır; `backtest/research/strategy/live/risk/oms/data/
   features/portfolio/jev` ulaşamaz (AST). `BinanceImzaliAdaptoru` testnet dışında **yetkisiz
   kurulamaz**; `salt_okunur` (shadow) taşımada yalnız GET, `yalniz_iptal` (acil iptal) GET+DELETE —
   ikisi de emir açamaz. İşlem anahtarı `.env`de dursa bile yetki olmadan okunmaz.
5. **Shadow dört katmanlı** (Faz-8-Hazirlik §1.2-1.3 aynen): anahtar yetkisi (işlem kapalı, açılışta
   `apiRestrictions`) → taşıma GET-only → `GolgeAdaptoru` yazmaları reddeder → `EmirMotoru` `VALIDATED →
   GOLGE` (yeni nihai durum; `SUBMITTED`a uğramaz). Risk modu `shadow` eklendi: `MOD_ESIGI["shadow"] =
   LIVE_ADAYI` (§1.3/1). Diğer modların eşlemesi değişmedi.
6. **Execution hattı** (`execution/hat.py`): onaylı niyet → engelleyici güvenlik (DISABLED, halt,
   UNKNOWN, açık emir, aynı bar ikinci emir, SAFE_MODE, bayat karar, **borsa ölçümlü** günlük zarar/
   drawdown → SAFE_MODE) → miktar (tavanlar yalnızca aşağı: `azami_maruziyet`, `azami_brut_maruziyet`,
   nakit; canlıda sermaye = kademe) → `EmirMotoru` → emir + pozisyon mutabakatı (uyuşmazlık/yetim emir
   → halt). Onay üretmez, büyütmez (K-037). Paper, shadow, testnet, live **aynı kod**; fark adaptör.
7. **Paper borsa** (`exchange/paper_adaptoru.py`): `EmirAdaptoru`nun simüle karşı tarafı, kalıcı
   (SQLite). Market emri **sonraki barın açılışında** dolar (K-004), slippage aleyhte (K-007),
   komisyon `config/maliyet.json`dan; duplicate kimlik `-2010`. Böylece paper, Faz 7'nin emir yolunu
   (defter, mutabakat, pozisyon mutabakatı) uçtan uca sınıyor.
8. **Yürütücü** (`trader/yurutucu.py`): kapanmış bar → (paper fill) → mutabakat → risk durumu →
   strateji → risk motoru → hat. Tek sembol. Son kapanmış bar `AKIS`, geç gelen `BACKFILL` ve karar
   üretmez (K-028). Kalıcı durum + kimlik (K-009); yeniden başlatma yeniden üretimdir (test: kesintili
   koşu = kesintisiz koşu, bit düzeyinde).
9. **İmzalı adaptör sertleştirmesi:** 429'da `Retry-After` kadar bekleyip okumayı yeniden dener; 418
   yasaktır, denenmez; `X-MBX-USED-WEIGHT-1M`/`ORDER-COUNT-10S` başlıkları okunur ve sınırın %80'inde
   yazma **gönderilmez** (`FAILED`, yeniden denenebilir). `SembolKurallari`na `minQty/maxQty/
   MARKET_LOT_SIZE/maxNotional` (tavanlar kırpmaz, reddeder).
10. **R8 sözleşme hash'i satır sonundan bağımsız okunur.** Bulgu: `config/r8_kriterler.json` K-111'den
    beri **değişmedi**, ama K-111'in hash'i (`2c3d520e…`) CRLF biçiminin; git LF saklıyor ve LF biçimin
    hash'i `9519524c…`. Kontrol satır sonlarını CRLF'e normalize edip hash'ler; içerikteki her değişiklik
    yine yakalanır. R8 kapanışında (K-112) hash doğrulanırken aynı normalizasyon kullanılmalı.

### R8 ve K-111'e etkisi

**R8: sıfır davranış değişikliği.** R8 yolu (`live/evren_*`, `EvrenPaperMotoru`, gözlem modu)
değiştirilmedi; yeni paketler (`trader/`, `execution/hat|mod|canli_kapi`, `exchange/paper_adaptoru|golge|
canli|yetki`) R8 yolundan import edilmiyor. `risk/`deki değişiklikler eklemedir (`MODLAR`'a `shadow`,
`MOD_ESIGI`'ne `shadow`, `OlayTuru.EXECUTION`); `gozlem` eşlemesi ve risk kararları aynen. 25 Eylül kod
senkronu bu commit'i taşır; K-043 yordamındaki test adımı yeşil takımı görür. **K-111: sıfır.** Yeni
hipotez/çekiliş/aile/veri kaynağı yok; defter 62. Doğrulama koşuları (`sma_kesisim` paper/shadow)
`gozlem` risk modunda altyapı ölçümüdür (K-035): promotion kanıtı değil, defter kaydı değil.

### Bugün LIVE'ı engelleyen (makine listesi `sq execution preflight --hedef LIVE_PENDING_APPROVAL`)

Promotion'u geçmiş strateji yok (K-078/1, K-110, K-111); R8 kapanmadı (K-112); risk sermayesi, Kademe 1
sermayesi ve onayı, shadow ölçütü, kademe artış oranı, drift kuralı, venue statüsü — Scryne kararları;
işlem anahtarı yok (bilerek, K-062/5: elle onaydan sonra üretilir); canlı host kill tatbikatı ve
§1.5 kapısını geçen `shadow` risk modlu shadow koşusu (promotion `LIVE_ADAYI` gerektirir) yok.

### Değişmez (yeni)

> Gerçek parayla emir gönderebilen tek nesne, bütün kontrolleri **o an** geçen bir kapının ve bir
> insanın onayının birlikte ürettiği, diske yazılmayan bir yetkidir. Kod bu yetkiyi üretemez, taşıyamaz,
> tahmin edemez.

### K-114 eki — adversarial denetim (2026-09-22)

Denetim (`docs/research/records/2026-09-22-K114-execution-denetim.md`) execution katmanında **dört HIGH**
fail-open buldu ve kapattı (`c255e94`): (1) tek canlı koşu kilidi yoktu — iki canlı süreç kademe
tavanını katlayabilirdi; (2) mutabakat *yapılamadığında* artıran emirler gidiyordu; (3) mod düşürme
çalışan süreci etkilemiyordu; (4) kill adaptörü kurulamazsa işaret ve süreç sonlandırma da yapılmıyordu.
Ek olarak: `SUBMITTED`+borsada dolmuş emir artık ACK üzerinden çözülür (önceden halt); bayatlık gönderim
anında ölçülür; LIVE onayı global audit'le, kanıt dosyaları koşu audit'iyle doğrulanır; onay API
anahtarına (`createTime`) ve yetki host'a bağlı; boyut tabanı ≤ sermaye. Karar değişmedi: canlı aktivasyon
kapıları aynı; hiçbir eşik değişmedi; hiçbir kullanıcı kararı doldurulmadı. Yeni değişmez:

> Mutabakat yapılamamış bir hesap üzerinde, bir kilitle tekil kılınmamış bir canlı süreçte ya da sistem
> modunun artık izin vermediği bir anda riski artıran emir gönderilmez.

## K-115 — Mikro canlı pilot: promotion'suz, kodda sabit tavanlı (100 USDT sermaye / 10 USDT kayıp) gerçek para kademesi

**Durum:** kabul · **Tarih:** 2026-09-22 · **Onay:** Scryne ("artık bir şeyleri beklemek istemiyorum. bir
an önce kullanmak istiyorum … ne gerekiyor ise en iyi ve en profesyonel bir şekilde yap"; yol: "en iyi
şekilde sen karar ver"; shadow: "ben direkt live olarak kullanmak istiyorum"; sermaye: "100 USDT, 10 USDT
kayıpta dur"; venue: "bilmiyorum, araştır") · **Değiştirir:** değişmez kural 8'in (K-010, K-018)
kapsamı — promotion kapıları **Kademe ≥ 2** için aynen, Kademe 1 bundan sonra *pilot*tur; Faz-8-Hazirlik
§2.1 kademe numaraları (micro-live 1 → 2) · **Kapatır:** Faz-8-Hazirlik §6/3 risk sermayesi, §6/6 venue
statüsü (pilot için) · **Tabi:** K-004, K-007, K-008, K-010, K-014, K-035, K-037, K-046, K-050, K-065,
K-111, K-114 · **Açık bırakır:** §6/1-2 shadow, §6/4 kademe artışı, §6/5 drift (Kademe 2 için)

### Bağlam (ölçülen)

- 62 hipotez, 0 promotion (K-078/1, K-110); araştırma askıda (K-111). K-114 canlı yolu kodladı ama live
  gate'in ilk kontrolü `strateji_onayi` — bugün geçen strateji yok, yani canlı kapı süresiz kapalı.
- Hesap (2026-09-22, salt okunur anahtar): `canTrade=true`, SPOT, bakiye 0, komisyon %0,10.
  `BTCUSDT` `minNotional` 5 USDT, step 1e-5.
- Risk limitleri (`config/risk.json`, değişmedi) boyutu sermayenin yüzdesi olarak kurar: tipik
  oynaklıkta `islem_basina_risk` bağlar ve pozisyon ≈ sermayenin %11,4'ü (p75 %8,6, p90 %6,6).
  **10 USDT sermayede pozisyon ≈ 1 USDT < 5 USDT minNotional → hiç emir verilemez.** 100 USDT'de
  ≈ 6,6-11,4 USDT — minNotional'ın üstünde (p90 oynaklığa kadar).

### Karar

1. **Pilot, promotion kanıtı değil ve alfa iddiası değil.** Amaç gerçek parayla execution, mutabakat ve
   paper↔live farkını ölçmek. Strateji `sma_kesisim` (BTCUSDT 1h; promotion aşaması `kalite_kontrol`,
   K-045'e göre tek sembollü yönlü arama kapalı) — **beklenen getiri ≈ −maliyet.** Paper/testnet'te uçtan
   uca koşan tek sembollü yol bu olduğu için seçildi.
2. **Tavanlar kodda sabit** (`execution/canli_kapi.py`): `PILOT_AZAMI_SERMAYE_USDT = 100`,
   `PILOT_AZAMI_KAYIP_USDT = 10`, `PILOT_HESAP_CARPANI = 1,5`. `config/kademe.json` bunların altında
   kalabilir, üstüne çıkamaz; yükseltmek kod + `tests/unit/test_pilot.py` + yeni K (K-050/2).
3. **Pilot live gate'i** (aktif kademede `"pilot": true`): `strateji_onayi`, `operasyon_r8`,
   `shadow_live_kaniti` yerine `pilot_siniri` (sermaye/kayıp tavanları, strateji verilmiş) ve
   `pilot_hesap_degeri` (salt okunur anahtarla canlı hesabın toplam USDT değeri **sermaye − azami kayıp ≤
   toplam ≤ sermaye × 1,5**; fiyatı ölçülemeyen varlık → kapalı). Geri kalan her kontrol aynen: paper ve
   testnet kanıtı, kademe + onay, pilot kararları (`risk_sermayesi`, `venue_statusu`,
   `canli_modul_sinir`), venue `AÇIK`, canlı host kill tatbikatı, HEAD'de yeşil test kaydı, açık
   SAFE_MODE/halt/UNKNOWN yok, işlem anahtarı yetkisi (spot açık; çekim/transfer/margin/futures kapalı;
   **IP kısıtlı**), canlı bağlantı. Açılış yine `sq execution onayla` (TTY, hash) — K-010'un "elle toggle
   yok, insan onayı var" zinciri değişmedi; değişen, onayın girdisinin promotion değil sabit tavan olması.
4. **Risk modu `pilot`** (`MOD_ESIGI["pilot"] = YOK`): K-035'in `gozlem` kalıbı — promotion istemez,
   promotion dışındaki **her** risk limiti tam uygulanır, ve `Kanit.paper_mod` yalnız `paper` kabul
   ettiği için pilot koşusu promotion kanıtı **üretemez**. Pilot kademe yalnız `pilot`, pilot olmayan
   kademe yalnız `live` risk moduyla kurulur (`trader/kurulum.py`).
5. **Mutlak kayıp tavanı** (`GuvenlikLimitleri.azami_kayip_usdt`, execution hattı, engelleyen katman —
   K-037): özkaynak (defter + borsa fiyatı) ≤ sermaye − 10 USDT → SAFE_MODE, artıran emir yok, azaltan
   geçer (K-008/3). Tavan zirveye değil sermayeye göredir ve özkaynak altında kaldıkça işaret kaldırılsa
   da her barda yeniden konur: bu sermayeyle koşu bir daha risk artırmaz. Açık pozisyon kendiliğinden
   kapatılmaz (K-008/2, spot). Risk motorunun %20 drawdown ve %2 günlük zarar frenleri de aynen durur.
6. **Venue kaydı** `config/venue_statu.json`: binance.com SPK KVHS listesinde yok (Binance Turkey AŞ
   var); 7518 sayılı Kanun rejiminin yükümlülüğü hizmet sağlayıcıya; bireysel kullanımı yasaklayan hüküm
   bulunmadı; Binance "Türkiye'den erişilebilir kalır" (2024-07-02); hesap API'den `canTrade=true`.
   Bilinmeyenler (vergi, madde numaraları, sözleşme tüzel kişiliği) kayıtta açık. Hukuki görüş değil;
   `AÇIK` sonucunu Scryne canlı onayla birlikte sahiplenir. Gözden geçirme ≤ 90 gün.
7. **Shadow adımı pilot için atlandı** (Scryne kararı). Karşılığı: kayıp tavanı + hesap tavanı + 5 USDT
   minNotional düzeyinde emirler. Kademe 2 (promotion sonrası micro-live) için shadow ölçütü ve
   §6/1-2 `DECISION REQUIRED` olarak duruyor.

### R8 ve K-111'e etkisi

**R8: sıfır.** `live/evren_*` yoluna dokunulmadı; `risk/`deki değişiklik ekleme (`MODLAR`/`MOD_ESIGI`'ne
`pilot`). Pilot bu makinede koşar; host-1'e dokunmaz (K-069 penceresi). **K-111: sıfır.** Yeni hipotez/
çekiliş yok; pilot koşusu defter kaydı ve promotion kanıtı değildir.

### Değişmez (yeni)

> Promotion'u geçmemiş bir stratejiyle gerçek paraya dokunan tek yol, kodda sabit bir sermaye ve kayıp
> tavanının içinde, bir insanın o anki kapı raporunu onaylamasıyla açılan pilottur; pilot hiçbir
> promotion kanıtı üretmez ve tavanını kendisi büyütemez.

---

## K-116 — 2026-09-23 denetimi: pilot kapısı kademenin strateji + sembolüne bağlandı; funding carry'nin güncel düzeyi ölçüldü (Hat B ekonomik tabanı çöktü)

**Durum:** kabul · **Tarih:** 2026-09-23 · **Onay:** Scryne ("projemin tamamını baştan sona denetleyip,
test edip … hatalı, eksik, iyileştirilmesi gereken yerleri profesyonel bir şekilde yap") · **Tabi:**
K-010, K-050, K-079, K-110, K-111, K-114, K-115 · **Kaynak:** `tests/unit/test_pilot.py`,
`docs/research/records/2026-09-23-funding-carry-guncel.md`, `tools/funding_guncel.py`

### Bulgu 1 — pilot onayı kademede yazılı strateji ve sembole bağlı değildi

`config/kademe.json` pilot kademesi `strateji: sma_kesisim`, `sembol: BTCUSDT` taşıyor (K-115/1), ama
`pilot_siniri` yalnız "strateji verildi mi" diye bakıyordu ve kapı raporunda sembol yoktu: `sq execution
onayla --strateji <herhangi>` ve `sq execution calistir --mod live --sembol <herhangi>` pilot tavanları
içinde başka bir strateji/sembolle canlı koşu açabiliyordu. Tavanlar (100/10 USDT, hesap ≤ 150) yine
bağlıydı; delinen şey onayın **neye** verildiğiydi.

**Düzeltme (yalnız sıkılaştırır, K-050):** `pilot_siniri` kademe stratejisi ≠ istenen strateji ya da kademe
sembolü boşsa kalır; kapı raporu `sembol` alanını taşır ve **hash'e girer** (sembol değişirse onay geçersiz);
`trader/kurulum.py` pilot kademede koşu sembolünü rapordakine eşitler, değilse `KurulumHatasi`. Testler:
`test_pilot_siniri_kademe_strateji_ve_sembolune_bagli`, `test_pilot_raporu_sembolu_tasir_ve_hash_sembole_bagli`,
`test_kurulum_pilot_baska_sembolde_kurulmaz`. Parametreler (`-p`) bağlanmadı: pilot tavanları içinde kalır ve
Kademe ≥ 2 zaten promotion ister — ama bir sonraki kademede parametre bağının kapıya girmesi açık kalem.

### Bulgu 2 — Hat B (carry) tabanı çöktü

Son 12 ay funding: BTC %3,37, ETH %2,38, SOL −%1,83, XRP %0,11 (notional'a oranla, maliyetsiz; IS tavanı
BTC %14,2). Sermaye verimi ≈ yarı → BTC ≈ %1,7-2,5/yıl < DTB3 %3,97. K-110'un "tek kilit K-079/2" dediği
hat bugün vadeli hesap açılsa da risksiz getirinin altında. **K-079/2 sorusu bugünkü piyasada ekonomik
olarak anlamsız**; yeniden açılma işareti: son 90 gün BTC funding ≥ %8/yıl (`tools/funding_guncel.py`,
bugün %6,53 — toparlanıyor, işaretin altında). Bu işaret bir karar değil, K-079/2'yi yeniden sormanın zamanı.

### Değişmeyen

Kapılar, eşikler, defter 62, K-111 askısı, pilot tavanları, R8 kriterleri. Kod değişikliği yalnız pilot
bağında (sıkılaştırma).

---

## K-117 — Pozitif kontrol: kapı sisteminin gücü ölçüldü, iyi stratejiyi de reddediyor; stres parametre hatası düzeltildi

**Durum:** kabul (ölçüm + hata düzeltmesi; eşik/kapı tanımı **değişmedi**) · **Tarih:** 2026-09-23 · **Onay:**
Scryne ("bu kadar hipotez denenip hiç kapıdan geçen olmaması garip değil mi? bir yerlerde hata mı yapıyoruz?
… her şeyin gerçekten doğru ve sağlam olduğuna inanmanı istemiyorum") · **Tabi:** K-019, K-039, K-044, K-050,
K-054, K-058, K-081, K-110, K-113 · **Kaynak:** `docs/research/records/2026-09-23-pozitif-kontrol.md`,
`tools/pozitif_kontrol.py`, `tests/unit/test_degerlendirme_stres.py`

### Ölçülen

1. **Motor doğru:** bağımsız vektörel hesapla getiri/Sharpe 4/4 senaryoda eşit (±%4).
2. **Kapıların gücü o güne kadar hiç ölçülmemişti.** Bilinen üstünlüklü kahin (gerçek motor, maliyet, bölme,
   K-019 + K-113): %65 isabetli günlük (OOS Sharpe medyanı 2,06) **0/20**; haftalık ufukta her p'de **0/20**.
   Null (p = 0,50) 0/60 — yanlış pozitif tarafı sağlam.
3. **Yapısal kusurlar:** (a) `stres_dayanikliligi` tüm dönem yüzde puan farkını ölçüyor; işlem sayısı, süre ve
   stratejinin kendi getirisiyle büyüyor, güçlü günlük stratejilerin %100'ünü eliyor. (b) `asgari_islem` 30 +
   walk-forward eğitimde ≥ 20 işlem: tutma süresi ≳ 1 hafta olan her strateji üç kapıda "ölçülemedi". (c)
   `evren_dayanikliligi` tek sembolde tanım gereği ölçülemiyor. (d) Kapılar ayrı ayrı %5'e kalibre, birlikte
   uygulanınca güç sıfıra yakın.
4. **0/62 bu yüzden "alfa yok" kanıtı değildi — ama 62 çekiliş yine de zayıf:** en iyi OOS Sharpe 0,46, null
   persentil medyanı 0,50 (K-110); kahin ölçeğinde isabet ≤ %55 düzeyi. Düzeltilmiş kapılar bu çekilişleri
   geçirmezdi (hepsi `oos_sharpe` 1,04'ün altında). Asıl kayıp: yavaş aileler hiç ölçülemedi.

### Karar

1. **Hata düzeltildi:** tek sembollü `research/degerlendirme.degerlendir` stresi seçilen parametrelerle koşuyor
   (önce `sinif()`, varsayılan). Seçilen yoksa stres ölçülmez, kapı kalır. Evren yolu zaten doğruydu.
2. **Her yeni ya da değişen kapı iki yönlü doğrulanır:** yanlış pozitif (null kalibrasyonu) **ve** güç
   (`tools/pozitif_kontrol.py`). Tek yönlü kalibrasyon K-117'den sonra kabul edilmez.
3. **DECISION REQUIRED (Scryne, K-050: gevşetme yönü elle onay + yeni K):**
   - `stres_dayanikliligi`: pp farkı yerine stres senaryosunda risk-ayarlı ölçü (öneri: `hepsi_2x` OOS Sharpe
     ≥ 0,5 × temel OOS Sharpe ve `hepsi_2x` OOS getirisi > 0).
   - `asgari_islem` + walk-forward asgari işlemi: işlem sayısı yerine bağımsız karar dönemi / zaman-farkında
     tanım (Threshold-Policy'de zaten DECISION REQUIRED).
   - Birleşik kapı sisteminin hedef gücü (öneri: OOS Sharpe ≈ 1,5 düzeyindeki üstünlükte ≥ %50 geçiş).
   Bu kalemlerin hiçbiri bu kararla uygulanmadı.
4. Eşikler, defter (62), K-111 askısı ve promotion değişmedi.

---

## K-118 — Sistematik denetim (bilinen-cevaplı sınama): execution yolunda cooldown hiç çalışmıyordu; look-ahead kapsamı kayıttan; K-054'ün üç kapısının gücü sıfıra yakın

**Durum:** kabul · **Tarih:** 2026-09-23 · **Onay:** Scryne ("projenin tamamını dikkatli bir şekilde denetle …
projede vereceğin tüm kararları en iyi şekilde nasıl olacak ise o yönde kararlar ver") · **Tabi:** K-002, K-008,
K-033, K-054, K-058, K-114, K-115, K-117 · **Kaynak:** `tools/pozitif_kontrol_tam.py`,
`runs/pozitif_kontrol/tam.json`, `tests/unit/test_look_ahead_genel.py`, `tests/unit/test_trader_yurutucu.py`

### Yöntem

K-117'nin kök nedeni "ölçüm aletleri tek yönde doğrulanmış" olduğu için denetim her ölçüm/karar bileşenini
**cevabı bilinen girdiyle** sınar: bağımsız yeniden hesap, negatif kontrol (üstünlük yok → geçmemeli), pozitif
kontrol (bilinen üstünlük → geçmeli).

### Bulgular

1. **Execution yolunda (paper/testnet/canlı/pilot, `trader/yurutucu.py`) ardışık kayıp → cooldown limiti hiç
   çalışmıyordu.** `RiskMotoru.islem_kapandi` yalnız backtest defterinden çağrılıyordu; K-114 yürütücüsü
   çağırmıyordu. `config/risk.json` `ardisik_kayip_limiti` 10 / `cooldown_bar` 24 gerçek parada ölü limitti
   (K-115'in "her risk limiti tam uygulanır" cümlesi bu limit için yanlıştı). **Düzeltildi:**
   `yurutucu.kapanan_turlar` (pozisyon minNotional altına inen satışla kapanan tur; taban-varlık komisyonu
   miktardan, kote komisyonu nakitten, kırıntı değeri dahil), `_turlari_isle` her barda yeni turları bildirir,
   `islenen_tur` `yurutucu.json`'da kalıcı (yeniden başlatmada çift sayım yok). Testler: tur hesabı, cooldown'ın
   paper yolunda emri gerçekten reddetmesi, kesintili koşunun kesintisizle aynı sayacı vermesi. R8 evren paper
   yolu (`CokluAdimci` → `backtest/defter.py`) etkilenmemişti.
2. **Look-ahead kapsamı elle seçilmişti** (`sma_kesisim` + 3 funding stratejisi + 11 gösterge). Göstergeler
   koşu başında tüm seride önceden hesaplandığı için listede olmayan nedensel-olmayan bir gösterge `ctx`
   kesmesine rağmen sızardı. `test_look_ahead_genel.py` listeyi kayıttan (`motor.DEFTER`, `KUTUPHANE`,
   `KIYAS`) kurar: her gösterge × 3 bozma, her strateji × 3 bozma + "sinyal var" kontrolü. **Sonuç: hepsi
   temiz** — sızıntı yok; koruma artık otomatik.
3. **K-054 kapılarının gücü (tam hat, gerçek kütüphane stratejileri ve ızgaraları, gömülü rejim-trendli sentetik
   seri, m ∈ {0, 3, 5} × 4 tohum × 3 strateji):**

   | Kapı | m=0 medyan | m=5 medyan | Eşik | m=5 geçen |
   | --- | ---: | ---: | ---: | ---: |
   | `parametre_perturbasyonu` | 0,155 | 0,146 | ≤ 0,0565 | 2/12 (m=0: 2/12) |
   | `pbo` | 0,173 | 0,097 | ≤ 0,0087 | 0/12 |
   | `rejim_kararliligi` | −1,23 | −1,19 | ≥ 0,685 | 0/12 |
   | `oos_sharpe` | −0,75 | 0,38 | ≥ 1,04 | 5/12 |

   Pertürbasyon ve rejim üstünlüğü yokluğundan **ayırt etmiyor**; PBO kısmen ayırt ediyor ama eşik ulaşılamaz.
   Eşikler null'ın %5 kuyruğundan seçilmiş, gücü ölçülmemiş (K-117'nin aynı hatası). m=5'te 12 kapıyı geçen
   0/36; K-019'u geçen 1/12.
4. **Doğrulanan (hata yok):** tek sembollü motor bağımsız hesapla eşit (K-117); çok enstrümanlı motorun Decimal
   referans testi mevcut; çoklu-test null'u kavramsal olarak aile-bazında doğru (p = 0,50 kahin 0/60).

### Karar

1. Bulgu 1 ve 2'nin düzeltmeleri uygulandı (yalnız sıkılaştırır: ölü limit canlandı, test kapsamı genişledi).
2. K-054'ün `pbo`, `parametre_perturbasyonu`, `rejim_kararliligi` kapıları ve K-019'un `stres_dayanikliligi`,
   `asgari_islem` tanımları **yeniden tasarlanacak** (K-119); tasarım yalnız cevabı bilinen veride (kahin +
   sentetik) doğrulanır, dondurulur, **sonra** gerçek hipotezlere uygulanır — sonuca bakıp kapı ayarlamanın
   önü böyle kesilir.

---

## K-119 — Promotion kapıları iki yönlü doğrulamayla yeniden tanımlandı; tek sembollü araştırma 9 yıllık arşiv verisini kullanır

**Durum:** kabul · **Tarih:** 2026-09-23 · **Onay:** Scryne ("projede vereceğin tüm kararları en iyi şekilde nasıl
olacak ise o yönde kararlar ver") · **Değiştirir:** K-019 `stres_dayanikliligi` tanımı; K-054/K-058 `pbo` ve
`parametre_perturbasyonu` ölçüsü ve eşiği; `tarama` walk-forward asgari işlemi · **Tabi:** K-007, K-010, K-018,
K-039, K-044, K-050, K-054, K-058, K-081, K-113, K-117, K-118 · **Kaynak:**
`docs/research/records/2026-09-23-kapi-yeniden-tasarim.md`, `tools/pozitif_kontrol.py`,
`tools/pozitif_kontrol_tam.py`, `tools/pozitif_kontrol_evren.py`

### Bağlam

K-117/K-118 ölçtü: eşikler yalnız null'ın %5 kuyruğundan seçilmişti ve gücü hiç ölçülmemişti. Sonuç olarak
gerçek bir üstünlüğün 12 kapıyı geçme olasılığı fiilen sıfırdı: %65 isabetli kahin 0/20, güçlü gömülü trend 0/36.
0/62'nin bir kısmı "alfa yok" değil, "alet göremez"di. Kapı gevşetmek K-050'ye göre gerekçeli ve elle onaylı olmalı;
onay Scryne'ın açık yetkisiyle burada veriliyor. Gerekçe, sonuca bakıp eşik oynatma değil: her tanım **cevabı bilinen**
veride (kahin + sentetik) doğrulandı, gerçek hipotezlere bakılmadan donduruldu. Gerçek defterde sonuç değişmedi
(0/38).

### Karar

1. **`stres_dayanikliligi`:** alan `stres_sharpe_orani` ≥ 0,5 (OOS'ta en kötü maliyet senaryosu Sharpe / temel OOS
   Sharpe; seçilen parametreyle). Eski tüm dönem yüzde puan farkı yalnız rapor (`stres_bozulma`).
2. **`pbo`:** alan `pbo_zarar_olasiligi` ≤ 0,05 (CSCV içinde IS-en iyisinin OOS'ta zarar etme olasılığı). Sıralama
   PBO'su yalnız rapor.
3. **`parametre_perturbasyonu`:** alan `perturbasyon_koruma` ≥ 0,80 (komşu medyanı / seçilen, IS). Aralığa bölünen
   düşüş yalnız rapor.
4. **Walk-forward asgari işlem** pencereye göre: `tarama.asgari_islem_pencere` (yılda 6 tur). IS taraması (20) ve
   OOS `asgari_islem` kapısı (30) değişmedi.
5. **Değişmeyen kapılar:** `oos_sharpe` 1,04, `oos_suresi`, `oos_is_orani`, `wf_katman_basari`,
   `parametre_kararliligi`, `asgari_islem`, `max_drawdown`, `rejim_kararliligi`, `evren_dayanikliligi`. Rejim ve
   evren kapılarının evren yolunda gücü ölçüldü (güçlü trendde 6/6, trendsizde rejim 0/6).
6. **Tek sembollü araştırma verisi:** yeni hipotezler `data/evren/<sembol>/1h` (arşiv, 2017-08→) üzerinde; OOS 1,57
   → 2,72 yıl. Veri kimliği hipotez kimliğinin parçası (K-009); eski kayıtlar kendi verileriyle tarihsel kalır.
7. **Kalıcı kural:** yeni ya da değişen her kapı iki yönlü doğrulanır: yanlış pozitif (null / üstünlüksüz örnek)
   **ve** güç (pozitif kontrol). `test_kapilar_v2.py` eşiği iki ölçüme bağlar (pozitif kontrolün uç değeri geçer,
   null medyanı geçmez).
8. **Promotion, 12 kapının tamamını ister** (K-118 `ZORUNLU_KAPILAR`); tek sembollü strateji `evren_dayanikliligi`
   yüzünden hâlâ promotion alamaz (K-054). Gerçek bir aday evren yolundan gelir.

### Açık

Çoklu test eşiği 1,04, 1,57 yıllık OOS'ta kalibre edildi. 9 yıllık seride yeniden ölçülmeli; uzun OOS'ta null daha
dar olacağı için mevcut değer tutucu yönde kalır (K-050 yönü).

---

## K-120 — Araştırma askısı (K-111) kalkıyor; `kripto_zs_trend` programı açılıyor (bütçe 2)

**Durum:** kabul · **Tarih:** 2026-09-23 · **Onay:** Scryne ("bu stratejiyi bulmanı istiyorum … projede vereceğin
tüm kararları en iyi şekilde nasıl olacak ise o yönde kararlar ver") · **Değiştirir:** K-111/1 (askı) · **Tabi:**
K-039, K-044, K-045, K-051, K-068, K-072, K-110, K-117, K-118, K-119

### Gerekçe

K-111 askıyı "62 çekiliş, 0 geçen, hat tükendi" kanıtına dayandırmıştı. K-117/K-118 o kanıtın kapı tarafını
geçersiz kıldı: kapılar gerçek üstünlüğü de geçiremiyordu. Yavaş (haftalık+) stratejiler ise yapısal olarak hiç
ölçülemiyordu. 62 çekilişin **OOS sonuçları** gerçek ölçümdür ve geçerliliğini korur (K-110: null persentili 0,50);
tükenen aileler yeniden açılmaz. Açılan tek şey defterde **hiç çekilmemiş**, önceden ölçülemeyen bölgedeki en iyi
gerekçeli aile.

### Program `kripto_zs_trend`

- **Mekanizma:** zaman serisi (mutlak) trend. Kripto PIT evreninde (`27b7a16ed0ed`) her haftalık dengelemede kendi
  `pencere` barlık getirisi pozitif olan üyelerden en güçlü N tanesi eşit ağırlıkla taşınır; yükselen yoksa portföy
  nakde döner (`ZamanSerisiTrend`, kod değişmedi).
- **Kaynak farkı (K-045):** kesitsel momentum (h39-h42) üyeleri birbirine göre sıralar ve hep N isim taşır. Zaman
  serisi trend, düşen piyasada nakde çekilerek **piyasa zamanlaması** yapar; bu bileşen kesitsel IC'de görünmez.
  Kripto evreninde hiç çekilmedi (yalnız FX'te, kısa pencereyle: h53).
- **Kaynak ölçümü (yalnız IS, OOS'a bakılmadı):** R7 işaret testi `roc720 > 0` üyeleri +0,87 pp/hafta (t 2,07,
  iki yarı aynı işaret; 336: t 0,68; 1440: t −1,04). Haftalık zamanlama, IS sonu 2023-12-24: BTC 4 hafta t 2,64,
  ETH 8 hafta t 2,09, ADA 4 hafta t 2,14, BNB 2 hafta t 1,95; XRP, LTC yok. **Orta düzey kanıt;** tek pencere ve
  majörler taşıyor.
- **Karşı argüman (sonucu görmeden):**
  1. OOS (2024-01→2026-09) 2024 boğasını ve 2025-26 düşüşünü içeriyor. Trend takipçisi dönüş noktalarında
     testere yer.
  2. Kesitsel momentum aynı evrende kıyasın altında kaldı. Zamanlama bileşeni kıyasın düşüşünü azaltabilir ama
     Sharpe'ı 1,04'e taşımayabilir (K-108'in "risk profilini değiştirir, risk-ayarlı getiriyi değil" bulgusu).
  3. Altcoin'lerde IS zamanlama kanıtı yok.
- **Izgara:** pencere {336, 720, 1440, 2160} × n {5, 10, 20}, `hedef_brut` 0,2. 12 nokta; K-119 kapılarının
  doğrulandığı biçim.
- **Çekilişler ve durma kuralı:**
  1. `zs_trend_haftalik` (dengeleme 168).
  2. `zs_trend_aylik` (720) yalnız haftalık çekiliş OOS'ta kıyası (n = 10 sabit, K-072) geçerse koşulur. Bu bir
     takvim tekrarıdır, genişletme değil. Geçmezse program kapanır, aylık harcanmaz.
- **Kapılar:** K-119'un 12 kapısı aynen. Tek OOS başarısı promotion değildir. Geçerse sıradaki adımlar
  paper/shadow ve embargo sonrası yeni veridir.
- **Bütçe:** 2 çekiliş. Defter 62 → en çok 64. Çoklu test fotoğrafı program sonunda yeniden ölçülür (K-044); eşik
  bu karar içinde değiştirilmez.

---

## K-121 — `kripto_zs_trend` kapandı (1/2): h63 elendi; koşu commit'siz ağaçtan yapıldı (süreç hatası)

**Durum:** kabul · **Tarih:** 2026-09-23 · **Tabi:** K-009, K-044, K-072, K-110, K-119, K-120 · **Kaynak:**
`runs/faz12/zs_trend_haftalik.json`, `docs/Arastirma-Programlari.jsonl` (kapanış satırı)

### Ölçülen

h63 `zs_trend_haftalik` (plato seçimi): IS Sharpe 0,967; **OOS Sharpe −0,535** vs kıyas (n = 10) 0,302; OOS getiri
−%17,9, azami düşüş %29,2, 711 tur (994 gün); walk-forward 32 katman Sharpe 0,74, %62,5 pozitif; `pbo_zarar` 0,201,
`perturbasyon_koruma` 0,611, en kötü rejim −0,63. K-119'un 12 kapısından 8'i kalıyor. Önceden yazılan karşı argüman
(1) gerçekleşti: 2024 boğası ve 2025-26 düşüşü dönüş noktalarında testere. IS'teki zamanlama kanıtı (BTC 4 hafta
t 2,64) OOS'ta risk-ayarlı getiriye dönüşmedi.

### Karar

1. **Elendi; program kapandı.** Durma kuralı gereği `zs_trend_aylik` harcanmaz. Zaman serisi trend (kripto evreni,
   haftalık) tükenen aileler listesine eklendi (`docs/DURUM.md` §2).
2. **Süreç hatası:** koşu K-120 değişiklikleri commit edilmeden başlatıldı; kayıt `dirty` mutlak engelini taşıyor
   (K-009). Ekonomik sonuç etkilenmedi (kod değişikliği yalnız ızgara tanımıydı, sonradan commit `88c2a3d`), ama kayıt
   promotion kanıtı olamaz. Kural hatırlatması `.claude/CLAUDE.md` haritasına yazıldı: **evren çekilişinden önce
   commit.**
3. Çoklu test fotoğrafı 63'e yeniden ölçülüyor (K-044). h63'ün OOS düşüşü %29 > %25 olduğu için null uygunluğunu
   geçmez; eşiği yükseltmesi beklenmez.

**Ek (2026-09-23):** fotoğraf yeniden ölçüldü (`tools/faz12_coklu_test.py --deneme 500 --seed 0`): 63 çekiliş, 49
ölçülebilir (31 tek sembollü + 18 evren); %5 sınırı 1,0039 (önce de 1,004), %90 GA 0,982–1,063; mevcut eşik 1,04'ün
yanlış pozitifi 0,042. `COKLU_TEST_CEKILIS_SAYISI` 48 → 49; eşik değişmedi. `oos_suresi` kaydı yeniden üretildi
(asgari 569,67 gün aynı).

---

## K-122 — Gerçek para iki hükme bağlandı (sistem hazır + strateji hazır); 14 günlük gösterim dönemi

**Durum:** kabul · **Tarih:** 2026-09-23 · **Onay:** Scryne ("her şey hazır olduğundan emin olmadan hesaba gerçek
para ile açmam. önce projenin tamamen bitmesini istiyorum … gerçekten projenin çalıştığını görmeden … para atmam";
koşu yeri: "bu bilgisayar") · **Tabi:** K-008, K-010, K-028, K-035, K-038, K-046, K-065, K-111, K-114, K-115, K-119

### Karar

1. **Gerçek para iki ayrı, makine kontrollü hükme bağlı** (`sq execution hazirlik`, `execution/hazirlik.py`):
   - **Sistem hazır:** HEAD'de yeşil test kaydı; `gosterim-testnet` (sanal para, gerçek borsa emri) ve
     `gosterim-shadow` (gerçek hesap, salt okunur) koşularının her biri ≥ 14 gün, süreç yaşıyor, veri ≤ 2 bar
     geride, halt/SAFE_MODE/UNKNOWN yok, pozisyon mutabakatı temiz, testnet ≥ 4 dolan emir / shadow ≥ 4 GOLGE ve
     0 gönderilmiş emir, kaçırılan karar ≤ %2, saat sıçraması 0, ≥ 1 yeniden başlatma; canlı host kill
     tatbikatı; R8 PASS (K-112).
   - **Strateji hazır:** en az bir strateji promotion zincirinde `live_adayi` ya da ötesinde (12 kapı + risk
     incelemesi + paper).
   Pilot (K-115) de dahil gerçek para, Scryne'ın kararıyla **ikisi birden** sağlanmadan konmaz. Eşikler gösterim
   başlamadan yazıldı; dönem içinde değiştirilmez.
2. **Gösterim koşuları oturumdan bağımsız:** `tools/gosterim_gozetmen.ps1` (yalnız başlatır; öldürmez, SAFE_MODE
   kaldırmaz, mod yükseltmez; `runs/gosterim/DURDUR` ile durur), Windows zamanlanmış görevi `ScryneQuant-Gosterim`
   (oturum açılışı + 10 dakikada bir). Eski `testnet-surekli-1` planlı durduruldu (aynı testnet hesabı/sembolünde
   iki koşu pozisyon mutabakatını bozardı; hiç emir vermemişti).
3. **Gösterim öncesi bulunan ve düzeltilen:**
   - `testnet-surekli-1` 10 saatte 107 döngüde veri ucuna 5 denemede ulaşamadı. Public adaptör artık ağ hatasında
     yedek uca geçer (`YEDEK_HOSTLAR`: data-api → api → api-gcp; aynı veri). Hız sınırı hatası uç değiştirmez
     (ccxt'de `NetworkError` alt sınıfı; testle bulundu).
   - Kesinti yüzünden karar üretilmeyen bar sessizdi: `Sayac.kacirilan_karar` + zamanlı `hatalar.jsonl`.
   - `live.kill.pid_oku` bozuk pid dosyasında `TypeError` ile çöküyor. `live/` R8 için dondurulmuş olduğundan
     (K-111, bekçi testi) orada düzeltilmedi; hazırlık raporu hatayı yakalar ve "süreç çalışmıyor" der. R8
     kapanışından sonra `live/`de düzeltilecek.

---

## K-123 — Vadeli (long/short) tavanı yalnız IS'te ölçüldü: short bacak değer katmıyor; K-079/2 veriyle desteklendi

**Durum:** kabul · **Tarih:** 2026-09-23 · **Onay:** Scryne (K-122 planı: "vadeli tavan ölçümü, hesap açmadan") ·
**Tabi:** K-039, K-079, K-110, K-116, K-120, K-121 · **Kaynak:** `tools/vadeli_tavan.py`, `runs/vadeli_tavan.json`

### Ölçüm (çekiliş değil; OOS'a bakılmadı; karar kuralı ölçümden önce aracın başına yazıldı)

12 sembol (funding geçmişi olanlar), ortak haftalık takvim, sinyal = kendi `pencere` getirisinin işareti; long bacak
spot, short bacak perp (gerçek funding alınır/ödenir), taraf başı 15,3 bps (perp ücreti public'in 2 katı). IS
2019-09 → 2023-12-24 (222 hafta):

| Pencere | Long-only Sharpe | Long/short Sharpe | Short bacak pozitif yıl (2020-23) |
| --- | ---: | ---: | --- |
| 336 | 1,50 | 1,09 | 2020, 2022 |
| 720 | 1,56 | 1,42 | 2021 (+0,02), 2022 |
| 1440 | 0,93 | 0,33 | 2022 |
| 2160 | 0,98 | 0,36 | 2022 |

Kural (1)+(2) 0/4 pencere (≥ 3 gerekli); kural (3) short bacak dört pencere ortalamasında yalnız 2022'de pozitif
(≥ 3 yıl gerekli). **Vadeli hesap gerekçesi: YOK.** Short bacak yalnız 2022 ayısında kazanıyor; boğa ve yatay
yıllarda trendin tersine dönüşlerinde kaybettiriyor ve long-only'nin risk-ayarlı getirisini her pencerede düşürüyor.

İlk koşuda araç hatası yakalandı ve düzeltildi: sembol başına ayrı karar takvimi tarihleri hizalamıyordu (1.815
"hafta", %100 düşüş). Sonuç ortak takvimle yeniden ölçüldü.

### Karar

1. K-079/2 (vadeli hesap açılmıyor) artık yalnız bir tercih değil, **ölçümle destekleniyor**; short mimarisi
   (çift bacak, marjin, likidasyon, perp emir yolu) yazılmaz.
2. Not (tarafsız, sonuç değil): 12 majörde yalnız-long zaman serisi trendin IS Sharpe'ı 1,5 mertebesinde; h63 (429
   sembollük evren) OOS'ta −0,54'tü. Bu IS sayısı bir hipotez **değildir**. OOS'a bakılmadı, bakılmayacak; majör
   evreniyle bir çekiliş ancak K-051 program kaydı ve ön kayıtla açılabilir (h63'le aynı aile → K-110/K-121 gereği
   tükenen aile listesinde; yeniden açmak yeni gerekçe ister).

---

## K-124 — Evren değerlendirmesinde yıllıklandırma takvimi yok sayıyordu (düzeltildi); hisse/sektör trendinin IS ön ölçümü

**Durum:** kabul · **Tarih:** 2026-09-23 · **Onay:** Scryne ("abonelik almak istemiyorum, başka yolu yok mu") ·
**Tabi:** K-089, K-093, K-102, K-119, K-122 · **Kaynak:** `tests/unit/test_evren_degerlendirme.py`,
`docs/research/records/2026-09-23-hisse-etf-yol-secimi.md`

1. **Hata (düzeltildi):** `evren_degerlendirme.degerlendir` `yil_bar`ı `bar_yili(timeframe)` ile, yani takvimsiz (24x7)
   hesaplıyordu. Seanslı veride (FX) rejim kapısının Sharpe'ı ve PBO performans bozulması √(8.766/6.261) ≈ %18
   şişik çıkıyordu. Motor metrikleri takvimi zaten kullanıyordu. Artık `motor_ayarlari(veri).takvim`'den geliyor;
   kripto (takvim yok) bit-aynı. h53-h59 FX çekilişlerinin hükmü değişmez (hepsi `oos_sharpe`'ta ve rejimde kaldı).
2. **Ücretsiz veri kaynağı:** Kenneth French veri kütüphanesi (Dartmouth; CRSP'den): ABD piyasası + 12 sektör, günlük
   toplam getiri 1926-07 → 2026-07, risksiz faiz dahil; otomasyona açık (zip). EODHD free plan yalnız 1 yıl
   (ölçüldü: "Data is limited by one year"); Stooq bot korumalı; Scryne abonelik istemiyor. Sınırlar: yalnız
   getiri (bar yok → dolum ertesi gün kapanışı, K-004'ten tutucu); sektör portföyü ≠ ETF; 1952 öncesi cumartesi
   seansı var (seri 1952-07'den başlar; yıllık işlem günü 1953-2025 ortalaması **251,68**).
3. **IS ön ölçümü (çekiliş değil; 1952-07 → 2004-05, OOS'a bakılmadı):** Sharpe (risksiz üstü): piyasa al-tut
   0,49; piyasa trend 0,46-0,59; 12 sektör al-tut 0,56; **12 sektör trend 0,64-0,73**. Trend al-tut'a göre ~0,1-0,17
   Sharpe ekliyor; promotion eşiği 1,04'ün çok altında. Kripto (K-110/K-121), FX (K-106) ve carry/vadeli (K-116,
   K-123) sonuçlarıyla tutarlı: halka açık fiyat verisiyle bireysel ölçekte maliyet sonrası güçlü üstünlük
   görülmüyor; belgelenmiş en iyi yöntem (trend) riski iyileştiriyor, getiriyi değil.
4. Hedef tanımı (alfa mı, riski yönetilen yatırım mı) Scryne'ın kararına sunuldu; bu karar verilmeden hisse veri
   hattı yazılmaz.

---

## K-125 — Hedef yeniden tanımı: "riski yönetilen sistematik yatırım"; Risk Yönetimli Promotion Protokolü (RYPP)

**Durum:** kabul (protokol; strateji yok) · **Tarih:** 2026-09-23 · **Onay:** Scryne (B fazı talimatı: "yüksek
getirili alfa makinesi yerine riski yönetilen sistematik yatırım botu … eski promotion kapıları gevşetilmeyecek; ayrı,
önceden tanımlanmış, OOS doğrulanabilir protokol") · **Tabi:** K-010, K-030, K-039, K-044, K-051, K-052, K-072, K-110,
K-117…K-124 · **Kaynak:** `docs/research/Risk-Yonetimli-Protokol.md`, `src/scryne_quant/research/risk_protokolu.py`,
`tests/unit/test_risk_protokolu.py`

### Ana tez

ScryneQuant'ın amacı piyasayı sürekli yenmek değil: önceden tanımlanmış risk kurallarıyla piyasaya sistematik
maruziyet sağlamak, büyük düşüşlerde riski azaltmayı hedeflemek ve bunu ölçülebilir, denetlenebilir, otomatik bir
yürütme sistemi olarak yapmak. Bilimsel sınır: "piyasada alfa yok" iddia edilmez. İddia yalnızca şudur: mevcut veri,
hipotezler, test kapsamı ve doğrulama protokolü altında promotion edilebilir, tekrarlanabilir bir alfa kanıtı
bulunmadı (K-110, K-121, K-123, K-124).

### Denetim bulguları (B fazı öncesi)

| ID | Dosya | Bulgu | Önem | Düzeltme |
| --- | --- | --- | --- | --- |
| B-1 | `backtest/metrikler.py` (`hesapla`) | Sortino'nun aşağı yönlü sapması yalnız negatif gözlemlerle ortalanıyor (standart: tüm gözlemler) → Sortino ≈ √(N_neg/N) kadar düşük | Düşük (hiçbir kapı/karar kullanmıyor) | Eski alan `sonuc_hash`e girdiği için **değiştirilmedi** (bütün kayıtların yeniden üretimi kırılırdı); RYPP standart tanımı kullanır (`sortino_standart`), fark testle belgelendi |
| B-2 | `tests/unit/test_metrikler.py` | Sortino testi yalnız sıralamayı ("Sortino > Sharpe") ölçüyor; yanlış formül yeşil kalıyordu | Düşük | Formülü sabitleyen test RYPP'de |
| B-3 | kripto evren OOS (`27b7a16ed0ed`, bar 55.678→) | 18 çekiliş aynı OOS'a baktı; penceredeki 2025-26 düşüşü biliniyor → risk-off tasarımı için hindsight avantajı | **Yüksek** (yeni hedef için) | P3 plasebo (aynı maruziyet bütçesi, rastgele zaman) + bağımsız veride (French, 2004-05 sonrası, bakılmamış) ek doğrulama zorunlu |
| B-4 | kıyaslar (`al_tut`, `evren_esit_agirlik`) | brüt 0,2; nakit getirisi 0 | Orta (yeni hedef için) | RYPP kıyası stratejinin brüt tavanında; nakit 0 her iki tarafta (tutucu, belgelendi) |
| B-5 | `research/kapilar.py` `max_drawdown` ≤ 0,25 | 0,2 brütlü stratejiler için kalibre; tam maruziyetli dağılımda anlamsız | Orta | Alfa yolunda aynen; RYPP göreli düşüş kullanır |
| B-6 | `docs/ROADMAP-RESET.md` | K-116…K-124 ve hedef değişikliği yoktu | Orta (doküman) | Güncellendi (R13-R15) |
| B-7 | K-123 | 12 sembol bugünkü listeden (hayatta kalma) | Düşük (yalnız fizibilite; K-123'te yazılı) | RYPP evreni PIT kural zorunlu |

Kanıtla kontrol edilip sorun bulunmayanlar: azami düşüş hesabı; IS/OOS/walk-forward bölmesi; look-ahead (kayıttan
otomatik test, K-118); delist ele alınışı (`SIFIRA_YAZ_BAR` + testler); PIT evren hayatta kalma testleri; çoklu test
FWER'i (K-121 eki, yanlış pozitif 0,042); maliyet/kayma ve K-004 dolumu (bağımsız hesapla, K-117); canlı/paper/shadow/
testnet ayrımı (K-114/K-122).

### Karar

1. **Hedef yeniden tanımlandı**; alfa yolu (12 kapı, K-119) **değişmeden** durur. RYPP ayrı bir promotion yoludur:
   kıyas (§1), P1-P3/S1/R1-R3/B koşulları, PASS/FAIL/INCONCLUSIVE, plasebo, aile içi Bonferroni, dondurma →
   doğrulama → promotion ayrımı (`docs/research/Risk-Yonetimli-Protokol.md`). Bütün eşikler **tasarım kararı**
   olarak işaretli, sonuç görülmeden yazıldı; sonuca göre değiştirilemez (değişiklik yeni K + iki yönlü test).
2. **Kendini kandırma korumaları testle sabit:** yalnız maruziyet düşürmek FAIL; rastgele zamanlama FAIL; tek olay
   FAIL; 2x maliyette çöken FAIL; kısa OOS / tek epizot / eksik kanıt INCONCLUSIVE; aile büyüdükçe eşik sıkılaşır.
3. **Sıra (A→B→C→D→E):** A (sistem gösterimi + R8) sürüyor. B = bu protokol. C (kripto strateji) ancak RYPP promotion
   zincirine bağlandıktan sonra açılır. Promotion'a/canlıya hiçbir şey A ve R8 kapanmadan girmez. Gerçek para
   yalnız K-122'nin iki hükmü ve Scryne'ın açık onayıyla.
4. **Açık (bir sonraki adım):** RYPP'nin promotion zincirine bağlanması (`Kanit` için protokol türü; RYPP yolunda
   `ZORUNLU_KAPILAR` yerine RYPP koşul listesi) ve bağımsız veri (French) yükleyicisi. İkisi de strateji değil.

## K-126 — RYPP promotion zincirine bağlandı: protokol türü `Kanit`te, alfa yolu değişmedi; B-3 yoksa PASS yok (INCONCLUSIVE)

**Durum:** kabul (altyapı; strateji yok, eşik değişikliği yok) · **Tarih:** 2026-09-23 · **Onay:** Scryne (K-126 talimatı:
"yalnızca RYPP'nin mevcut promotion zincirine güvenli ve deterministik biçimde bağlanması") · **Tabi:** K-010, K-035,
K-039, K-082, K-118, K-119, K-122, K-125 · **Kaynak:** `src/scryne_quant/risk/promotion.py`,
`src/scryne_quant/cli/main.py` (`sq promotion degerlendir --protokol/--rypp/--bagimsiz`),
`tests/unit/test_promotion_rypp.py`

### Mimari bulgu: `ZORUNLU_KAPILAR` protokole özgü, sistem değişmezleri başka aşamalarda

Zincir (`backtest → kalite_kontrol → out_of_sample → risk_incelemesi → paper → live_adayi → elle_onay → live`) incelendi.
`ZORUNLU_KAPILAR` yalnız `_out_of_sample`da okunuyor ve içeriği alfa protokolünün ekonomik/istatistiksel ölçütü
(OOS Sharpe ≥ 1,04, PBO, WF, parametre kararlılığı, mutlak `max_drawdown` ≤ 0,25 — K-125/B-5'e göre tam maruziyetli
dağılımda anlamsız). Yani **protokole özgü**. Gerçek sistem değişmezleri başka yerde ve protokolden bağımsız:

| Değişmez | Nerede | RYPP'de |
| --- | --- | --- |
| Yeniden üretilebilirlik, temiz ağaç, sonuç/config/commit kimliği (K-009) | `backtest` | aynen |
| Veri kalitesi, maliyet modeli, `data_quality_warning` (K-006/K-021) | `kalite_kontrol` | aynen |
| Çekiliş sayımı (K-039) | `out_of_sample` ön şartı (`hipotez_sirasi`) | aynen (iki yolda da) |
| Kanıt tamlığı (K-118) | `out_of_sample` | alfa: 12 kapı; RYPP: 13 koşul (`RYPP_KOSULLARI`) |
| Risk motoru altında düşüş, kill switch'e değmemek (K-008) | `risk_incelemesi` | aynen |
| 30 gün kesintisiz paper, yalnız `paper` modu (K-035) | `paper`, `Kanit.__post_init__` | aynen |
| Elle onay makinece verilemez (K-010) | `elle_onay` | aynen |
| Zincir hash'i + audit bağı (K-082) | `PromotionKaydi` | aynen; protokol satırın içinde |
| Look-ahead | kod düzeyi, `test_look_ahead_genel.py` (K-118) | kanıt başına değil, değişmedi |

### Karar

1. **`Kanit.protokol`** (`Protokol.ALFA` | `Protokol.RYPP`), varsayılan `alfa`: K-126 öncesi davranışın aynısı ve en katı
   yol; varsayılan hiçbir ölçümü dolu göstermez. Yalnız `out_of_sample`ın ölçütünü seçer; diğer aşamalar ortak.
2. **Karışma yasak (kurulurken, K-035/2 kalıbı):** alfa kanıtı `rypp_sonucu`/`bagimsiz_dogrulama` taşıyamaz; RYPP kanıtı
   `kapi_sonucu` taşıyamaz; RYPP gövdesi alfa `kapi_sonucu`na konursa 12 kapı eksik → `False`. `out_of_sample`ı bir
   protokolle geçen strateji sonraki aşamalarda (ve `elle_onayla`da) ötekinin kanıtıyla ilerletilemez
   (`PromotionKaydi.protokol`, geçmişten türer; K-126 öncesi satır = alfa).
3. **Hüküm satırlardan türer, raporlanan `durum`dan değil** (`rypp_hukmu`): yeterlilik satırı yok/geçmedi → INCONCLUSIVE;
   nokta koşulu **kaldı** → FAIL; ölçülmemiş nokta koşulu → INCONCLUSIVE; bootstrap yok/geçmedi → INCONCLUSIVE; hepsi →
   PASS. Yalnız `gecti is True` geçer (`1`, `"true"`, `None` geçmez). Türetilen ≠ raporlanan, bilinmeyen/çift satır,
   `esikler` yok ya da K-125 değerlerinden farklı (`RYPP_ESIKLER`, gevşetilmiş kodla üretilmiş kanıt) → `PromotionHatasi`.
   PASS/FAIL/INCONCLUSIVE → `AsamaSonucu.gecti` True/False/**None** ("ölçülemedi"; zincirin mevcut üç değeri).
4. **B-3 → INCONCLUSIVE, FAIL değil.** Bağımsız doğrulama yoksa RYPP PASS üretemez. FAIL seçilmedi çünkü FAIL "ölçüldü ve
   kaldı" demek ve K-125 §5.3'e göre yeni araştırma döngüsü/hipotez açtırır; burada donmuş aday yanlışlanmadı, kanıt eksik.
   INCONCLUSIVE'in K-125 tanımı ("eşik gevşemez, daha fazla veri beklenir") B-3'ün durumunun kendisi. Ayrıntı:
   - kimliksiz (`veri_sha256` yok) bağımsız veri → INCONCLUSIVE; ana OOS ile aynı `veri_sha256` → kanıt hatası;
   - bağımsız veride FAIL → FAIL (üç değerli VE: bir FAIL her şeye baskın, sonra INCONCLUSIVE);
   - K-125 §5 "PASS için bağımsız veride en az FAIL olmamalı" **yorumu**: bağımsız veride yeterlilik satırlarının ve
     bütün nokta koşullarının ölçülüp geçmesi şart; tolere edilen tek belirsizlik bootstrap'tır. Aksi hâlde kısa bir seri
     (yeterlilik INCONCLUSIVE) ya da P3'ü hiç koşmamak (ölçülmemiş koşul → INCONCLUSIVE) "FAIL değil" sayılıp B-3'ü boşa
     düşürürdü. Bu bir **sıkılaştırma yorumu**, eşik değişikliği değil; ikinci açığı özellik testi yakaladı (ilk sürüm
     yalnız yeterliliği arıyordu).
5. **Kanıt izi:** her satırın `kanit` özetinde `protokol`; RYPP satırında `rypp_durum`, `rypp_hash`, `bagimsiz_durum`,
   `bagimsiz_veri_sha256`, `bagimsiz_hash` (tam gövdelerin `nesne_hash`i). Hepsi satır hash'ine ve audit'e girer; hash
   sözleşmesi (`satir_hashi`, `HASH_DISI`) değişmedi, eski satırlar olduğu gibi doğrulanır.
6. **CLI:** `sq promotion degerlendir <strateji> --protokol rypp --rypp <RyppSonucu.sozluk JSON> --bagimsiz <aynı + veri_sha256>
   --sonuc <kayıt>`. `--protokol alfa` + `--rypp` ya da `--protokol rypp` + `--kapilar` → hata. RYPP koşusunu dosyaya
   yazan üretici komut henüz yok (C fazının işi).

### Alfa regresyonu

16 alfa kanıt varyantında (tam, boş, dirty, DQ, kapı yok/eksik/kalan, üst `gecti` doğru satır yanlış, hipotez yok, risk
yok/aşım, paper yok/kısa/kesinti) aşama aşama `(asama, gecti, gerekce)` ve eski kanıt alanları K-126 öncesiyle **byte
aynı**; `runs/promotion/sma_kesisim.json` üzerinde `sq promotion durum --json` çıktısı aynı. Alfa satırına eklenen tek
alan `"protokol": "alfa"` (yeni satırların içeriği, dolayısıyla hash'i, bu bir alan kadar farklı; karar aynı).

### Sınırlar (açık)

- `aile_sayisi` (P3'ün Bonferroni k'sı) RYPP gövdesinde yapısal alan değil; promotion defterden doğrulayamıyor (yalnız P3
  satırının açıklamasında). Kayıt ve üretici komut yazılırken yapısal alana alınmalı.
- B-3 bağımsız veri yolu (French, 2004-05 sonrası) **yok**; bu yüzden şu an hiçbir RYPP kanıtı PASS olamaz — tasarım gereği.
- B fazı kapanmadı: RYPP entegre, ama bağımsız doğrulama veri yolu, metodolojinin yeniden denetimi ve B kararı eksik.
  **C fazı açılmaz.**

---

## K-127 — B-3 bağımsız doğrulama kuralı açık karar oldu; P3'ün k'sı kanıta donduruldu; French verisi kilitlendi ama PIT değil (promotion'a kapalı)

**Durum:** kabul (altyapı + metodoloji; strateji yok, eşik değeri değişikliği yok) · **Tarih:** 2026-09-23 · **Onay:**
Scryne (K-127 talimatı: "RYPP'yi PASS ettirmek değil; PASS'ın ancak yeniden üretilebilir, bağımsız ve metodolojik olarak
kilitli kanıtla mümkün olmasını sağlamak") · **Tabi:** K-039, K-052, K-124, K-125, K-126 · **Kaynak:**
`src/scryne_quant/risk/promotion.py`, `src/scryne_quant/research/risk_protokolu.py`, `src/scryne_quant/research/hipotez.py`,
`src/scryne_quant/data/french.py`, `config/bagimsiz_veri.json`, `tests/unit/test_promotion_rypp.py`,
`tests/unit/test_bagimsiz_veri.py`, `docs/research/records/2026-09-23-B3-bagimsiz-veri.md`

### 1. K-125 §5 "Ek doğrulama" cümlesi ve K-126 kodu: doğal yorum değil, yeni karar

Kayıtlı metin (`Risk-Yonetimli-Protokol.md` §5, 4. maddeden sonraki paragraf; değiştirilmedi):

> **Ek doğrulama (kirlenme nedeniyle zorunlu):** kripto OOS'u (B-3) tek başına yeterli sayılmaz. Aynı donmuş kural, bu
> projede OOS'una hiç bakılmamış bağımsız bir veride de raporlanır: ABD piyasası/sektörleri, French verisi, **2004-05
> sonrası** (K-124'te yalnız öncesi ölçüldü). Bu veri promotion kararına INCONCLUSIVE/FAIL girdisi olarak girer: PASS için
> bağımsız veride en az FAIL olmamalı.

Son cümle harfiyen okunursa bağımsız sonucun **herhangi bir** INCONCLUSIVE'i (kısa seri, plasebo yok, stres yok) PASS'a
izin verir. K-126 kodu daha sıkı: yeterlilik satırlarının ve 8 nokta koşulunun hepsi ölçülüp geçmiş olmalı; tolere edilen
tek belirsizlik bootstrap. Bu, metnin doğal yorumu **değil**; "zorunlu" kelimesinden ve INCONCLUSIVE'in K-125 tanımından
("kanıt karar vermeye yetmiyor") türetilmiş bir **sıkılaştırma kararı**. Sessiz kalmaması için burada açıkça karar olarak
yazılıyor:

- **Kural (K-127/1):** Bağımsız doğrulama ancak veri yeterliliği (`oos_suresi`, `kiyas_epizot`, `plasebo_var`,
  `stres_var`) ve bütün nokta koşulları (P1, P2a, P2b, P3, S1, R1, R2, R3) ölçülüp geçtiyse "yapıldı ve FAIL değil"
  sayılır. Bağımsız veride FAIL → FAIL. Yok, kimliksiz, yeterliliği sağlanmamış ya da ölçülmemiş nokta koşullu → yapılmamış →
  INCONCLUSIVE. Yalnız bootstrap belirsizliği → izin (K-125 §5'in "FAIL değil" hükmü).
- **Neden:** Harfi yorumla çok kısa bir seri ya da P3'ü hiç koşmamak B-3'ü boşa düşürür. B-3'ün tek amacı kirlenmiş
  kripto OOS'unu bağımsız kanıtla dengelemek.
- **Eşik değeri değişmedi**, kabul kuralı sıkılaştı. Bu yüzden K düzeyinde. Karar hiçbir RYPP sonucu yokken verildi
  (defterde RYPP çekilişi 0). Test iki yönlü: pozitif (yalnız bootstrap belirsiz → PASS korunur) ve negatif (yetersiz veya
  ölçülmemiş → PASS yok); `test_K127_bagimsiz_dogrulama_karar_tablosu`.
- K-126/4'teki "yorum" ifadesinin yerine bu karar geçer. K-126 metni değiştirilmedi (append-only).

### 2. P3'ün k'sı: anlamı, kaynağı, kanıttaki yeri

**Anlam (K-125 §4, `RyppGirdisi.aile_sayisi`):** RYPP ailesi içi Bonferroni. k, **değerlendirme anında** hipotez defterindeki
RYPP çekilişlerinin birikimli sayısı (adayın kendi satırı dahil). Aşağıdakilerden hiçbiri değil:
- küresel K-039 sayısı (63; o ayrı sürüyor),
- araştırma programı sayısı,
- "başarılı aile" sayısı (sonuca bakan her tanım yasak).

**Bulunan açıklar:**
- Defterde RYPP satırını işaretleyen bir alan yoktu; k defterden sayılamıyordu.
- `aile_sayisi` varsayılanı 1'di.
- `max(1, k)`, k=0'ı sessizce düzeltiyordu.
- Kanıtta k yapısal alan değildi; yalnız açıklama metninde geçiyordu.
- Promotion k'yı doğrulayamıyordu.

**Karar (K-127/2):**
- `Hipotez.protokol` (`""` = alfa, `rypp`). Doluysa kimliğe girer. Boşken girmez: 63 eski satırın kimliği aynı
  (`test_gercek_defterin_kimlikleri_degismedi`). `sq lab hipotez-kaydet --protokol rypp`.
- `HipotezDefteri.rypp_aile_sayisi(satir)`: ilk `satir` satırdaki RYPP satırları. Defter append-only olduğu için aynı önek
  her zaman aynı k'yı verir (replay). Kısalmış defter → hata.
- `RyppGirdisi.aile_sayisi` zorunlu (varsayılan yok), `int` ≥ 1. `bool`, `float` ve `str` → `ProtokolHatasi`.
  `aile_defter_satir` k'nın sayıldığı defter öneki.
- `RyppSonucu.aile = {sayi, defter_satir, persentil}` ve P3 satırında `persentil`: araştırmanın gerçekten kullandığı
  1 − α/k. Tam gövde `rypp_hash` ile satır hash'ine ve audit'e girer.
- Promotion (`rypp_ailesi`, `Kanit._aile_tutarliligi`): k tip-katı ≥ 1, `defter_satir` ≥ k, `aile.persentil` = P3 satırının
  `persentil`i = 1 − α/k. Bağımsız doğrulamanın k'sı ana kanıtınkiyle aynı. Aday k sayıldığında defterde kayıtlı olmalı
  (`hipotez_sirasi` ≤ `defter_satir`).
- `Kanit.rypp_aile_sayisi`: CLI'ın defter önekinden **yeniden** saydığı k. Kanıttakiyle farklı → kanıt kurulmaz; yok →
  `out_of_sample` ölçülemedi. Akış: araştırma k'yı sayar → kanıta donar → promotion yeniden sayıp eşitliği ister;
  promotion k seçemez.
- Bugünkü gerçek defterde RYPP çekilişi 0. k=1 iddia eden her kanıt promotion'da reddedilir (test).

### 3. B-3 veri seti: seçim ölçütleri (sonuca bakılmadan)

Ölçütler:
1. K-125 §5'te önceden adı konmuş ihtiyaç.
2. Farklı varlık sınıfı; kripto evreniyle ortak enstrüman yok.
3. Ücretsiz ve otomasyona açık (K-124: abonelik yok).
4. CRSP tabanlı, uzun seri.
5. Projede kullanılmamış pencere.

Pencere K-124'ün IS'inin (1952-07 → 2004-05) hemen sonrası: **2004-06-01 → 2026-07-31** (dosyanın son günü). Pencere
K-124/K-125 metninden alındı, sonuca bakılarak seçilmedi. Set: 12 sektörün değer ağırlıklı günlük getirisi + Mkt-RF + RF.
EW, SMB ve HML dışarıda: EW küçük hisse ağırlıklı ve yatırılabilirliği düşük; SMB/HML gereksiz.

### 4. B-3 veri seti: kimlik ve PIT denetimi (ayrıntı `records/2026-09-23-B3-bagimsiz-veri.md`)

- **Kimlik (dondurulmuş, `config/bagimsiz_veri.json` + test sabitleri):**
  - `dataset_id` `french_12ind_vw_gunluk_202607`, vintage "202607 CRSP (CIZ)", 5.577 işlem günü.
  - zip SHA-256 `ff4f0b6c…` / `1916d331…`, CSV SHA-256 `20b066c1…` / `b324d858…`.
  - Kanonik veri SHA-256 `2448dddc19747d1138675c461b214279e27beda8a4e2867e43ff51be1c21dbc1`. Kaynak ondalık metinleri,
    float'a bağlı değil. İki kez yükleme aynı hash; tek hücre değişince hash değişir.
  - `yukle` her okumada zip/CSV hash'ini, üye adını, şemayı, pencereyi, satır sayısını, ilk günü ve kanonik hash'i yeniden
    hesaplar. `indir` farklı vintage'ı kilitli dosyanın yerine yazmaz.
- **Bağımsızlık:** Hipotez defterinin 63 satırında bu verinin ya da kaynak dosyaların kimliği yok
  (`sq data bagimsiz-dogrula`). Defterde French/ABD hisse çekilişi yok. Kayıt dışı tek kullanım K-124'ün IS ölçümü;
  kodu repoda değil, "OOS'a bakılmadı" ifadesi yalnız karar metnine dayanıyor.
- **PIT:**
  - Değer zamanı uygun: t'nin getirisi t kapanışında bilinir.
  - Üyelik zamanı kaynağa göre uygun: hisse, t yılı Haziran sonunda o anki SIC ile atanır. Bileşen verisi yok, bağımsız
    doğrulanamadı.
  - Hayatta kalma: CRSP evreni. Delist getirisi kaynak sayfada açık yazmıyor.
  - **Revizyon uygun değil.** Kaynak: *"We reconstruct the full history of returns each month … Historical returns can
    change"*. As-published vintage geçmişi yok; Wayback'te 9 anlık görüntü var. Ölçüm (yalnız hücre farkı, 2004-06 sonrası,
    VW):

    | Eski vintage | Değişen hücre | ≥10 bp | Azami fark |
    | --- | --- | --- | --- |
    | 201611 | %58,3 | %2,50 | 1,19 yp |
    | 202202 | %31,6 | %1,54 | 3,44 yp |
    | 202406 | %32,2 | %1,50 | 3,44 yp |
    | 202601 | %0,25 | %0 | 0,02 yp |

    2025-01'deki FIZ→CIZ geçişi bütün geçmişi yeniden üretti.
- **Hüküm (K-127/4):** Veri **PIT değil** (revize edilmiş tek vintage). K-052/15 (`available_time`) ve NFCI'da vintage
  kullanma emsali gereği set `promotion_uygun: false`. `sq promotion degerlendir --bagimsiz` yalnız kaydı
  `promotion_uygun: true` olan bir setle birebir eşleşen (`dataset_id` + `veri_sha256`) kanıtı kabul eder.
  `promotion_uygun` yalnız yeni bir K ile değişir.
- Revizyonun doğası (düzeltme ve metodoloji değişikliği) gelecek getiri bilgisi taşıdığını göstermiyor. Büyüklüğü de
  küçük: hücrelerin %1,5-2,5'i ≥ 10 bp. Yani risk büyük olasılıkla sızıntı değil gürültü. Yine de bu bir **ölçüm değil
  argüman**; uygunluk Scryne'ın kararına bırakıldı.

### 5. Kilit

Pencere, kaynak, şema ya da hash değişirse `test_manifest_dondurulmus…` ve `yukle` kırılır. Yeni vintage, pencere ya da set
yeni K ve yeni doğrulama döngüsü ister. Bağımsız veri üzerinde **strateji koşulmadı, getiri istatistiği hesaplanmadı**.

### 6. Ek bulgular (açık)

- **Bonferroni birikimli k:** Her çekiliş kendi değerlendirme anındaki k'yı kullanırsa ailenin toplam yanlış pozitifi α·H_n
  ile sınırlıdır (H_n harmonik sayı; n=10'da ≈ 2,9α), α ile değil. Bu, K-125 §4'ün tanımı; değiştirilmedi. Kesin aile
  kontrolü (ör. önceden sabit aile bütçesi) ayrı bir K ister.
- **CLI `hipotez_sirasi` doldurmuyor:** `sq promotion degerlendir` kanıtında `hipotez_sirasi` hep `None`; iki protokolde de
  CLI'dan `out_of_sample` ölçülemedi kalır (fail closed, K-126 öncesinden). C'den önce kapatılmalı.
- **"Aynı donmuş kural" eşlemesi tanımsız:** Kripto evren kuralının ABD sektörlerine (günlük, 12 portföy, hisse maliyeti,
  epizot eşiği 0,10) nasıl uygulanacağı hipotez kaydında, kripto OOS'undan **önce** donmalı.
- **Makro rejim çekilişleri** (VIX/NFCI, 2017+) ABD stres zamanlamasını dolaylı olarak kripto filtresi olarak gördü; ABD
  hisse getirisine bakılmadı. Zayıf örtüşme, kayıtta.

### Sonuç

- K-125 §5'in yorumu ve k açıkları kapandı.
- B-3 veri **hattı** kuruldu ve test edildi (kimlik, kilit, bağımsızlık, replay).
- B-3 veri **seti** PIT revizyon koşulunu karşılamıyor. Bu yüzden B-3 bağımsız doğrulama yolu PASS için **hazır değil**;
  RYPP bugün de PASS üretemez.
- R13 (B) açık kalıyor, C açılmıyor.
- Açık karar: revize edilmiş French verisinin koşullu kabulü (ör. aynı donmuş kuralın iki farklı vintage'da aynı hükmü
  vermesi şartı; 201611 FIZ görüntüsü 2004-06 → 2016-11'i kapsar) ya da PIT vintage'lı başka bir veri seti.

---

## K-128 — B fazı kararı: French vintage dayanıklılığı şartıyla kabul; P3'ün k'sı program bütçesi; CLI hipotez sırası; B kapandı

**Durum:** kabul · **Tarih:** 2026-09-23 · **Onay:** Scryne ("tamam onaylıyorum ve her şeyi sana bırakıyorum … geçilmesi
gereken adımları biraz düşür") · **Tabi:** K-051, K-125, K-126, K-127 · **Kaynak:** `risk/promotion.py`
(`vintage_hukmu`, `rypp_ailesi`), `research/risk_protokolu.py`, `data/french.py`, `config/bagimsiz_veri.json`,
`cli/main.py` (`--bagimsiz-vintage`, `--hipotez`, `_program_butcesi`), `tests/unit/test_promotion_rypp.py`,
`tests/unit/test_bagimsiz_veri.py`

### 1. B-3: French verisi vintage dayanıklılığı şartıyla kabul

K-127 French 202607'nin PIT olmadığını ölçtü: her ay revize ediliyor, hücrelerin %1,5-2,5'i ≥ 10 bp değişiyor. PIT
vintage'lı ücretsiz bir ABD hisse verisi yok (abonelik yok, K-124). Revizyonun doğası da düzeltme; getiri bilgisi
taşımıyor. Bu yüzden revizyon riski bir argümanla geçiştirilmiyor, **test edilen bir şarta** çevriliyor:

- **İkinci vintage:** `french_12ind_vw_gunluk_201705`. Wayback görüntüsü 2017-07-09; sektör ve faktör dosyası aynı
  CRSP 201705 sürümünde. Pencere 2004-06-01 → 2017-05-31, 3.273 gün, kanonik `10256f91…`. 202607'ye göre hücrelerin
  %2,46'sı ≥ 10 bp farklı: gerçekten başka bir revizyon.
- **Kural (`vintage_hukmu`):**

  | Birincil | Vintage eşi | Sonuç |
  | --- | --- | --- |
  | geçti | geçti | PASS'a izin |
  | FAIL | FAIL | FAIL |
  | FAIL | geçti (ya da tersi) | INCONCLUSIVE (revizyona duyarlı) |
  | FAIL | yapılmadı | FAIL |
  | diğer | diğer | INCONCLUSIVE |

  İki gövde aynı veride olamaz ve aynı k'yı taşımalı.
- **Kayıt:** Birincil set `promotion_uygun: true`, `rol: birincil`, `vintage_eslesi`. İkinci set yalnız `rol:
  ikinci_vintage` olarak; tek başına bağımsız doğrulama sayılmaz.
- **CLI:** `--bagimsiz` birincil rolde, `--bagimsiz-vintage` onun eşi olmak zorunda.

### 2. P3'ün k'sı: program bütçesi (K-125 §4 ve K-127/2'nin yerine)

K-127'nin birikimli sayımı (her çekiliş kendi anındaki k ile) aile hatasını α ile değil α·H(n) ile sınırlıyordu.
Yeni tanım: **k = adayın RYPP araştırma programının açılışta yazılan bütçesi** (`azami_cekilis`, K-051).

- Önceden sabit, sonuçtan bağımsız. Programın bütün çekilişleri aynı k'yı kullanır; bütçe aşılamaz. Böylece aile
  içi Bonferroni tam kontrol sağlar.
- `aile = {sayi, program, persentil}`. Promotion (CLI `_program_butcesi`) açılış satırını okur ve kanıttaki k ile
  eşitliğini ister. Kapanmış program da okunur; iki kez açılmış program hata verir.
- `HipotezDefteri.rypp_aile_sayisi` (defter öneki sayımı) kaldırıldı. `Hipotez.protokol` kalıyor: RYPP adayı onunla
  tanınır.

### 3. CLI `hipotez_sirasi` (açık K-126'dan beri)

`sq promotion degerlendir --hipotez <kimlik>` defterdeki satırı bulur ve `hipotez_sirasi`/`hipotez_toplami`ni doldurur.
Satır adayın stratejisine ait olmalı. RYPP'de ayrıca `protokol: rypp` taşımalı ve kanıttaki k'nın programında olmalı.
Önceden CLI bu alanı hiç doldurmuyordu; `out_of_sample` CLI'dan iki protokolde de hep ölçülemedi kalıyordu.

### 4. "Aynı donmuş kural" eşleme sözleşmesi (bağımsız veride)

RYPP hipotezi **kripto OOS'una bakılmadan önce** şunları dondurur (`gerekce`/ızgara kaydında). B-3 değerlendirmesi
yalnız bu eşlemeyle yapılır:

| Konu | Eşleme |
| --- | --- |
| Enstrümanlar | 12 VW sektör portföyü, hepsi her zaman listeli (evren kuralı gerekmez) |
| Zaman | Karar gün kapanışı, dolum ertesi gün (K-004). Kripto parametreleri **takvim süresi** olarak taşınır (ör. 30 gün → 21 işlem günü), bar sayısı olarak değil |
| Kıyas | 12 sektör eşit ağırlık, stratejinin brüt tavanında, aynı dengeleme takvimi (K-125 §1) |
| Maliyet | Taraf başı 5 bps (ETF komisyon + spread); S1 stresi 2x |
| Epizot eşiği | 0,10 (K-125, hisse endeksi) |
| Nakit getirisi | İki tarafta 0 (RF verilmez, K-125 tutucu yön) |

Bu tasarım kararı sonuç görülmeden yazıldı.

### 5. B fazı kararı

B'nin kapanış şartları:
- RYPP entegre (K-126).
- Metodoloji açıkları kapandı (K-127/1, K-128/2-3).
- Bağımsız veri yolu, kimliği ve vintage kilidi hazır (K-127/K-128).
- Testler yeşil.
- Bu karar.

**R13 kapandı.** C (R14) açılabilir: tek RYPP programı, küçük bütçe, ön kayıt. Hiçbir aday henüz yok.

---

## K-129 — Mikro pilot K-122'nin "strateji hazır" ve R8 şartından ayrıldı; 7 günlük gösterim yeter

**Durum:** kabul · **Tarih:** 2026-09-23 · **Onay:** Scryne ("artık elimde çalışan bir trade bot'umun olmasını istiyorum.
eğer gerekliyse geçilmesi gereken adımları biraz düşür") · **Tabi:** K-010, K-050, K-115, K-116, K-122 · **Kaynak:**
`execution/hazirlik.py` (`PILOT_GOSTERIM_GUN`, `pilot_hazir`), `execution/canli_kapi.py` (`pilot_gosterim_kontrolu`),
`cli/execution.py` (`hazirlik`), `tests/unit/test_hazirlik.py`, `tests/unit/test_pilot.py`

K-122'de Scryne'ın kuralı "iki hüküm birden olmadan gerçek para yok, pilot dahil" idi. Kod düzeyinde pilotun canlı
kapısı (K-115) R8 ve promotion istemiyordu; şart yalnız karar metnindeydi. Karar:

1. **Mikro pilot (Kademe 1: 100 USDT sermaye, 10 USDT kayıpta SAFE_MODE; tavanlar kodda sabit) için** "strateji hazır"
   (promotion), R8 ve 14 günlük gösterim şartları **kalkar**.
2. **Yerine** üç şart gelir; hepsi `sq execution hazirlik` altında "MİKRO PİLOT" hükmü olarak görünür:
   - HEAD'de yeşil test takımı.
   - Testnet + shadow gösterimi **7 gün** aynı ölçütlerle temiz: kaçırılan karar ≤ %2, dolan emir/GOLGE ≥ 4,
     yeniden başlatma tatbikatı, mutabakat temiz.
   - Kill tatbikatı.

   Gösterim şartı **pilot canlı kapısına da eklendi** (`pilot_gosterim`). Bu, K-115 kapısını K-122'nin kaldırılan
   kısmına göre bir tık **sıkılaştırır**.
3. **Değişmeyenler:**
   - Koddaki pilot tavanları.
   - Risk motoru, kill switch, SAFE_MODE.
   - İşlem anahtarı yetki denetimi (çekim/transfer/margin/futures kapalı, IP kısıtlı).
   - Hesap değeri bandı [90, 150] USDT.
   - `sq execution onayla` ile elle onay (K-010).
   - Tavanı büyütmek kod + test + yeni K ister.
   - **Kademe ≥ 2 (sermaye büyütme) K-122'nin iki hükmünü aynen ister.**
4. **Beklenti (dürüst):** Pilot stratejisi `sma_kesisim` ve alfa iddiası taşımıyor (K-115). Amaç gerçek parayla
   execution, mutabakat ve kayma ölçümü. Bekleneni küçük bir maliyet kaybı, kazanç değil. Kayıp 10 USDT'de durur.
   Pilotun stratejisi C fazından çıkan bir RYPP adayıyla değiştirilebilir; bu yeni kademe kaydı ve onay ister.
5. **Takvim:** Gösterim 2026-09-23'te başladı. En erken pilot yaklaşık 2026-09-30.

   Scryne'dan gerekenler:
   - Binance'ta işlem yetkili, IP kısıtlı, çekimsiz bir API anahtarı.
   - Hesapta ~100 USDT.
   - `sq execution preflight --hedef live --ag` geçtikten sonra `sq execution onayla`.

---

## K-130 — C fazı açıldı: `kripto_risk_kapisi` programı (bütçe 1), tek aday `evren_risk_kapisi`, RYPP ön kaydı

**Durum:** kabul (ön kayıt; OOS'a bakılmadı) · **Tarih:** 2026-09-23 · **Onay:** Scryne ("nasıl devam etmemiz
gerekiyor ise o şekilde devam et", K-128'de B kapandı) · **Tabi:** K-039, K-051, K-072, K-121, K-125, K-128 ·
**Kaynak:** `src/scryne_quant/strategy/kutuphane/evren_risk_kapisi.py`, `src/scryne_quant/research/rypp_kosu.py`,
`tools/rypp_kos.py`, `tests/unit/test_evren_risk_kapisi.py`, `tests/unit/test_rypp_kosu.py`

### Aday (dondurulmuş, ızgara yok)

| Alan | Değer |
| --- | --- |
| Kıyas | `evren_esit_agirlik`: PIT evren `27b7a16ed0ed`, hacimde ilk 10, eşit ağırlık, 168 barda (haftalık) dengeleme, brüt 1,0, aynı maliyet modeli |
| Aday | Kıyasın kendisi + rejim kapısı: `BTCUSDT` kapanışı 2.400 barlık (100 gün) SMA'nın üstündeyse risk açık, değilse bütün pozisyonlar kapanır ve nakitte beklenir |
| Kontrol | Her 24 barda bir (günde bir); karar bar kapanışında, dolum sonraki bar açılışında (K-004) |
| Bilinmeyen rejim | Risk kapalı (tutucu) |
| Parametre seçimi | Yalnız IS: rejim penceresi 50/100/200 gün, önceden yazılı kuralla 100 gün (aşağıda) |

### Protokol

- **Program:** `kripto_risk_kapisi`, bütçe **1**. Bu yüzden k = 1 ve P3 persentili 0,95 (K-128/2).
- **Doğrulama:** RYPP. Kripto OOS'u, `pencereler` ile öteki evren çekilişleriyle aynı %30 kesim.
  Bağımsız doğrulama K-128/4 eşlemesiyle yapılır:
  - French 202607 (2004-06 → 2026-07).
  - French 201705 (2004-06 → 2017-05).
  - Rejim sinyali piyasa endeksi (Mkt-RF + RF) > 69 işlem günü SMA (100 takvim günü).
  - Günde bir kontrol, 5 günde bir dengeleme, taraf başı 5 bps, gecikme 2 gün.
- **Koşu:** `tools/rypp_kos.py kos`. Bir kez yapılır; temiz ağaç ve kayıtlı hipotez şart. FAIL ya da INCONCLUSIVE'de
  aynı OOS'ta tuning yapılmaz, program kapanır.
- **Plasebo:** Adayın zamanlama takvimi (`g_t`: risk açık mı) kıyasın bar getirisine uygulanır ve dairesel
  kaydırılır. Aday kıyastan yalnız zamanlamayla ayrıldığı için doğru sıfır noktası budur.

### IS ölçümü (yalnız in-sample; OOS'a bakılmadı)

Pencere 2018-03-08 → 2023-12-30 (bar 4.802-55.678). Isınma ızgaranın en büyük ısınması, varyantlar aynı barlarda.
Kayıt: `runs/rypp/kripto_risk_kapisi/is_izgara.json` ve `is_olcum.json`, commit `a01658c6`, temiz ağaç.

| | Azami düşüş | CAGR | MAR | Düşüş azaltımı | Rejim değişimi |
| --- | --- | --- | --- | --- | --- |
| Kıyas (brüt 1,0) | %89,9 | −%7,9 | −0,09 | — | — |
| Aday, 50 gün | %69,8 | %50,6 | 0,73 | %22,4 ✗ | 108 |
| **Aday, 100 gün (seçilen)** | **%59,1** | **%59,9** | **1,01** | **%34,3 ✓** | 60 |
| Aday, 200 gün | %71,8 | %39,4 | 0,55 | %20,2 ✗ | 36 |

**Seçim kuralı (ölçümden önce yazılı):** IS düşüş azaltımı ≥ %25 (P1 eşiği) olanlar arasında en yüksek IS MAR; hiçbiri
geçmezse program açılmazdı. Seçilen **100 gün (2.400 bar)**. İlk koşuda literatür standardı 200 gündü ve IS'te P1'i
geçemedi (%20); bu yüzden OOS'a sokulmadı, ızgaraya genişletildi. Izgaranın tamamı hipotez kimliğinde. Not: ilk
ızgara koşusu commit'siz ağaçtaydı ve IS penceresi seçilen adayın ısınmasına bağlıydı; iki sorun düzeltildi ve
temiz koşu ilk ölçümle birebir aynı çıktı.

### Önceden yazılan karşı argümanlar

1. **Testere riski.** h63 (üye başına trend) OOS'ta 2024 boğası ve 2025-26 düşüşünün dönüşlerinde testereye yakalandı
   (K-121). 100 günlük tek piyasa kapısı daha yavaştır ama aynı dönüşlerde geç çıkıp geç girebilir. Bu durumda P3 ya da
   P2 kalır.
2. **Hindsight.** Kripto OOS'undaki düşüş biliniyor (B-3). Pencere yalnız IS'te seçildi.
   Plasebo ve iki vintage bağımsız veri bu avantajı dengelemek için var.
3. **Maruziyet düşürme.** Aday nakitte kaldıkça düşüşü kendiliğinden azaltır. P1 bu yüzden tek başına kanıt değil;
   asıl kapı P3'tür.
4. **Brüt 1,0.** Araştırma motoru risk motorunu koşmaz (K-073). Canlıda drawdown limiti (0,20) ve maruziyet tavanı
   (0,30/enstrüman) ayrıca bağlar. PASS gelse bile `risk_incelemesi` bunu ölçer.
5. **Parametre duyarlılığı.** IS ızgarası monoton değil: komşu pencereler (50 ve 200 gün) P1'i geçemiyor. Sonuç
   pencereye duyarlı olabilir. RYPP'nin R1 (başlangıç tarihi) ve R2 (alt dönem) koşulları ile bağımsız veri bunu
   kısmen sınar. Canlıya geçmeden önce ayrıca not edilmeli.

---

## K-131 — h64 `evren_risk_kapisi` RYPP FAIL; `kripto_risk_kapisi` programı kapandı; kripto P3 takvim hatası düzeltildi

**Durum:** kabul (sonuç kaydı) · **Tarih:** 2026-09-23 · **Tabi:** K-125, K-128, K-130 · **Kaynak:**
`runs/rypp/kripto_risk_kapisi/{ozet,ana,bagimsiz,vintage,ana_tani_k131}.json`, `runs/promotion/evren_risk_kapisi.json`

### Sonuç (tek sefer, ön kayıttan sonra, temiz ağaç `e8924bf`)

**Kripto OOS** (2023-12-30 → 2026-09-19, 2,72 yıl, 23.861 bar; kıyasta 3 epizot):

| | Toplam getiri | CAGR | Azami düşüş | MAR | Sharpe |
| --- | --- | --- | --- | --- | --- |
| Kıyas (ilk 10, eşit ağırlık, brüt 1,0) | −%31,2 | −%12,8 | %75,7 | −0,17 | 0,17 |
| Aday (BTC 100g kapısı) | −%16,6 | −%6,4 | %59,8 | −0,11 | 0,16 |
| Aday, 2x maliyet | −%23,7 | −%9,5 | %61,0 | −0,16 | 0,10 |

- **Kalan koşullar:**
  - P1 düşüş azaltımı 0,21 (< 0,25).
  - R3: yalnız 1 epizotta iyileşme (< 2).
  - P3: düzeltilmiş tanıda gerçek MAR −0,06, plasebonun %95 persentili 0,64. Zamanlama şanstan iyi değil.
- **Geçen koşullar:** P2a, P2b, S1, R1, R2.
- Aday kıyastan daha az kaybetti, ama bunu zamanlamayla değil maruziyeti yaklaşık %56'ya indirerek yaptı. K-125'in
  tam olarak ayırt etmek için tasarlandığı durum bu.

**Bağımsız veri (K-128/4 eşlemesi):**

| Veri | Aday CAGR / düşüş / MAR | Kıyas CAGR / düşüş / MAR | Hüküm |
| --- | --- | --- | --- |
| French 202607 (2004-09 → 2026-07) | %6,0 / %24,1 / 0,25 | %10,8 / %54,1 / 0,20 | FAIL (R1 başlangıç tarihi) |
| French 201705 (2004-09 → 2017-05) | %4,8 / %24,0 / 0,20 | %9,4 / %54,0 / 0,18 | FAIL (P3, S1, R1) |

İki vintage da FAIL olduğu için birleşik sonuç FAIL. ABD'de kapı düşüşü yarıya indiriyor ve 202607'de plaseboyu da
geçiyor. Ama sonuç başlangıç tarihine bağlı; eski vintage'da plaseboyu geçemiyor.

**Hüküm: RYPP FAIL** (üç yolun üçünde). Promotion zincirinde `out_of_sample` = FAIL olarak kayıtlı: zincir K-126/K-128
kanıt yolunu CLI'dan uçtan uca ilk kez gerçek kanıtla çalıştırdı; program bütçesi k = 1 doğrulandı, hipotez sırası 64.

### Kripto P3 hatası (K-131/1)

`rypp_kosu.kripto_girdi`, motorun zaten kesir olan brüt maruziyetini bir kez daha özkaynağa bölüyordu. Takvim hep 0
çıktı ve `ana.json`'daki P3 anlamsız hesaplandı.

- **Birim testi neden yakalamadı:** Test de aynı yanlış varsayımla (tutar cinsinden maruziyet) yazılmıştı.
- **Düzeltme:** Kesir okunuyor. İki bekçi eklendi: maruziyet > 1,5 ise hata; işlem varken takvim boşsa hata.
- **Hükme etkisi yok:** P1 ve R3 motorun gerçek özkaynağından hesaplanıyor ve ikisi de kaldı. Düzeltilmiş P3 aynı
  deterministik OOS koşularıyla tanı olarak kaydedildi (`ana_tani_k131.json`); o da kaldı. Kanonik kanıt `ana.json`,
  hüküm değişmez.
- **Ders:** Yeni bir hesap yolunun birim testi motorun gerçek çıktısıyla (en az bir kez) sınanmalı; sentetik girdi
  yazarın varsayımını tekrarlar. Bu, projenin "bilinen cevapla denetim" kuralının bir uygulaması.

### Durma kuralı

Bütçe 1/1 harcandı ve program kapandı. Aynı OOS'ta pencere, sembol ya da brüt ayarı yapılmaz. Yeni bir RYPP adayı yeni
bir program ve yeni bir IS araştırması ister.

**Öğrenilen:**
1. Kripto alt coin sepetinde tek piyasa trend kapısı, maruziyet düşürmenin ötesinde zamanlama değeri üretmedi.
2. ABD sektörlerinde aynı kural düşüşü belirgin azaltıyor, ama sağlamlık (başlangıç tarihi, vintage) yetmiyor.

---

## K-132 — Hedef: sabit risk bütçeli sistematik yatırım; ilk ürün `sabit_oran` (%50 BTC, ±5 puan bant); pilot bu kurala bağlandı

**Durum:** kabul · **Tarih:** 2026-09-23 · **Onay:** Scryne ("tamam ikinci yolla devam edelim"; önerilen varsayılanlar: hedef
%50 BTC / %50 USDT, bant ±5 puan) · **Tabi:** K-014, K-037, K-050, K-115, K-122, K-125, K-129, K-131 · **Kaynak:**
`strategy/kutuphane/sabit_oran.py`, `config/risk_profilleri.json`, `config/risk_yatirim.json`, `risk/limitler.py`
(`profil_yolu`), `trader/kurulum.py`, `execution/canli_kapi.py` (`risk_config_kontrolu`), `config/kademe.json`,
`tools/gosterim_gozetmen.ps1`, `tests/unit/test_sabit_oran.py`, `tests/unit/test_execution_cli.py`

### Gerekçe

- **Arama tükendi.** 64 çekiliş (63 alfa + 1 RYPP) hiçbir zamanlama ya da seçim becerisini şanstan ayırt edemedi
  (K-110, K-131).
- **Riski azaltan tek ölçülmüş etken maruziyet.** K-131'de aday düşüşü maruziyeti azaltarak düşürdü, plaseboyu geçemedi.
  Maruziyet bir beceri değil bir kuraldır ve bir bot kuralı kusursuz uygular.
- **Hedefin netleşmesi.** K-125'in hedefi ("riski yönetilen sistematik yatırım") sabit risk bütçeli yatırım olarak
  netleşiyor. Alfa ve RYPP yolları aynen durur ve yeni bir aday çıkarsa kullanılır.

### Karar

1. **Ürün (`sabit_oran`):**
   - Portföyün `hedef` kesri (0,5) BTC'de, gerisi USDT'de.
   - Maruziyet [0,45, 0,55] dışına çıkarsa hedefe dön; altındaysa `BUY`, üstündeyse `SELL`, mutlak hedef 0,5.
   - Pozisyon yoksa `BUY`.
   - Yön tahmini yok, indikatör yok, ısınma yok. Durum `ctx.pozisyon`dan okunur.
   - Alfa ailesi değil: ayrı kayıt `YATIRIM`, hipotez defterine girmez.
   - Look-ahead otomatik testine girdi (`test_look_ahead_genel.py`).
2. **Risk profili (K-037/K-050 uyumlu):**
   - Eşleme `config/risk_profilleri.json`'da, stratejinin kodunda değil; bir strateji kendine gevşek limit seçemez.
   - `config/risk_yatirim.json` genel profilden **yalnız iki alanda** ayrılır:
     - `azami_maruziyet` 0,30 → 0,50.
     - `islem_basina_risk` 0,005 → 0,05. ATR stop boyutlandırması stopsuz bir yatırımda %50 hedefi ~%11'e indirirdi.
   - Değişmeyenler: drawdown 0,20 (kill), günlük zarar %2, volatilite eşiği %2,05, cooldown.
   - Bekçi test: başka bir alan değişirse kırılır.
   - Canlı kapının `risk_config` kanıtı kullanılacak profilin limit kimliğidir; profil değişirse onay düşer.
   - Genel `risk.json` ve araştırma yolu değişmedi.
3. **Promotion ölçütü (yatırım ürünü):**
   - Plasebo aranmaz, çünkü ürün zamanlama iddiası taşımaz.
   - Aranan kanıt operasyoneldir:
     - Risk sınırları hiç aşılmadı.
     - Dengeleme yalnız bant dışında ve doğru yönde çalıştı.
     - Mutabakat temiz.
     - Maliyet modelle uyumlu.
   - **Pilot (Kademe 1, K-115/K-129) promotion istemez.** Sermaye büyütme (Kademe ≥ 2) için bu operasyonel ölçütün
     sayısal kapısı ve promotion zincirindeki karşılığı (üçüncü protokol) ayrı bir K ile yazılır. O yazılana kadar
     Kademe ≥ 2 kapalıdır.
4. **Pilot:**
   - `config/kademe.json` Kademe 1 stratejisi `sma_kesisim` → `sabit_oran`, sembol BTCUSDT.
   - Tavanlar kodda aynen: sermaye 100, kayıp 10 USDT.
   - Açılış `sq execution onayla` ile elle.
5. **Gösterim:**
   - Mevcut `gosterim-testnet` ve `gosterim-shadow` (`sma_kesisim`) altyapı kanıtı olarak devam eder, 7 günlük saatleri
     sıfırlanmaz. Sık emir ürettikleri için emir akışını daha iyi sınarlar.
   - Gözetmene `urun-testnet` eklendi: `sabit_oran`, testnet, 100 USDT. Ürünü gerçek borsa akışında gösterir.

### Risk karakteri (geçmiş, kapı değil; beklenti hiç değil)

BTC 1h arşivi 2017-08-17 → 2026-09-19, 100 USDT, ölçülmüş maliyet modeli (taraf başı 10 + 5,3 bps):

| | Toplam getiri | Yıllık | Azami düşüş | Dengeleme | Maliyet |
| --- | --- | --- | --- | --- | --- |
| **sabit_oran (%50, ±5)** | +%647 | %24,8 | **%56,2** | 100 | 2,66 USDT |
| %50 al-tut (dengelemesiz, kayar) | +%892 | %28,8 | %72,6 | 1 | 0,08 |
| %100 BTC tut | +%1.783 | %38,2 | %83,9 | 1 | 0,15 |

**Okuma:**
- Getiri tamamen BTC'nin geçmişteki yükselişinden geliyor ve geleceğe dair bir şey söylemez.
- Ürünün yaptığı, düşüşü tam BTC'ye göre sınırlamak (%84 yerine %56). Bunun bedeli yükselişte daha az kazanmak.
- **%56 da derin bir düşüş.**
- **Pilotta:** 10 USDT kayıp tavanı, BTC yaklaşık %20 düşünce tetiklenir (%50 maruziyette hesabın %10'u) ve bot
  SAFE_MODE'a geçer; çıkış elle yapılır. Bu pilot için doğru davranış.
- **Sermaye büyütülürse:** Kullanıcı bu derinlikte düşüşü kabul etmeli ya da hedef kesri düşürülmeli. Bu, o gün
  verilecek ayrı bir karar.

### Bilinen sınırlar

- Dengeleme emri 100 USDT'de ~5-6 USDT'dir, Binance'in asgari tutarının (5 USDT) hemen üstünde. Altına düşen emir
  borsaya gitmeden reddedilir; bir sonraki barda yeniden denenir.
- Çıkış (`SELL`) risk motorunda engellenmez, alım (`BUY`) günlük zarar ve volatilite kontrollerinden geçer. Sert bir
  düşüş gününde "düşüşte alım" ertesi güne kayabilir.

## K-133 — Bot takip ekranı (`/api/bot` + `apps/web/bot.html`) ve yürütücünün `egri.jsonl` izi

**Durum:** kabul · **Tarih:** 2026-09-23 · **Onay:** Scryne ("siteyi şöyle bişey yap ben buradan güzelce takip
edeyim") · **Tabi:** K-036, K-043, K-114, K-129, K-132 · **Kaynak:** `trader/bot_panosu.py`, `trader/pano.py`,
`trader/yurutucu.py` (`_egri_ekle`), `apps/web/bot.html`, `apps/web/src/bot/`, `DESIGN.md` (`bot-*` token'ları),
`tests/unit/test_bot_panosu.py`

### Gerekçe

- K-114 panosu on bölümlü bir denetim ekranı: her şeyi gösterir, "bot şu an ne yapıyor, param ne durumda" sorusunu
  tek bakışta cevaplamaz. Scryne botu günlük takip edeceği bir ekran istedi.
- Hesap değerinin zaman içindeki seyri diskte yoktu (yalnız son `durum.json`). Grafik için bir iz gerekiyordu.

### Karar

1. **İz (`egri.jsonl`):** yürütücü her işlenen barda `{bar_ms, ozkaynak, maruziyet, fiyat}` satırı ekler.
   - Yalnız okuma içindir; karar yolu, toparlanma ve mutabakat onu okumaz (K-038'in "yeniden üretim" iddiası
     değişmez).
   - Yazılamazsa koşu durmaz, hata `hatalar.jsonl`e düşer.
   - Aynı bar yeniden yazılırsa (toparlanma) okuyucu sonuncusunu alır.
2. **Uç (`GET /api/bot`):** koşu özetleri, seçili koşunun hesabı, eğrisi, son 40 emri, risk durumu, sabit oranın bant
   tetikleri (P = x·c / (q·(1 − x))), pilot tavanları, hazırlık kontrolü, sistem sürümü.
   - Salt okuma (K-036/K-043): emir, onay, durdurma ucu yok; SQLite `mode=ro` açılır; test dosya yazılmadığını ölçer.
   - Acil durdurma ekranda bir düğme değil, kopyalanan bir komuttur (`sq execution kill`).
3. **Sayfa:** `sq execution pano` kökte derlenmiş `apps/web/dist/bot.html`i verir; derleme yoksa klasik pano.
   Klasik pano `/klasik`te her zaman durur.
4. **Görsel kimlik:** `DESIGN.md` `bot-*` token'ları. Kâr/marka nane yeşili, zarar mercan, risk ayrı tek bir kehribar;
   ekranda glassmorphism yok (yalnız yapışkan üst çubukta statik blur).

### Bilinen sınırlar

- K-133'ten önce başlamış koşular yeniden başlatılana kadar `egri.jsonl` yazmaz; grafik o ana kadar boş kalır.
- Pano sunucusu çalışırken derlenen yeni sayfa bir sonraki yüklemede görünür; `/api/bot` değişiklikleri sunucunun
  yeniden başlatılmasını ister.
