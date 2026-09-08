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
edilebilir. Hız gerçekten darboğaz olduğunda vektörize bir **tarama** katmanı eklenebilir,
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
- **Kesin sayılar Faz 0 spike'ında Binance'in güncel ücret tarifesi ölçülerek doldurulur**
  ve tahmin edilen değil, doğrulanmış değer kullanılır.

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

**Durum:** kabul · **Kapatır:** Denetim C1 · **Değiştirir:** Proje-Fikri §7, §30

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

**Ne zaman gözden geçirilir:** veri hacmi Faz 0 spike'ında ölçüldüğünde (Denetim E), ve
tek dosya boyutu ya da sorgu süresi rahatsız edici hale geldiğinde.

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

## Açık kararlar (spike bekliyor)

| No | Konu | Kapanacağı yer |
| --- | --- | --- |
| K-015 | Binance erişimi ve testnet'in güncel durumu | Faz 0 spike |
| K-016 | Fee/slippage'ın kesin sayıları | Faz 0 spike (K-007'yi tamamlar) |
| K-017 | Birincil timeframe (1h mi 1m mi) ve veri hacmi | Faz 0 spike |
| K-019 | Promotion kapılarının sayısal eşikleri (K-018'in devamı) | Faz 4 sonu |
