---
proje: ScryneQuant
spike: 5
type: spike-raporu
tarih: 2026-09-11
status: kapandi
---
# Spike 5 — Türev piyasası verisi: erişim ve kapsam

**Soru:** Faz 4'e dönüş 3 için "fiyat dışı bilgi kaynağı" aday gösterildi. Binance'in türev
veri uçlarına Türkiye'den erişilebiliyor mu, ve o veriler 5,2 yıllık backtest penceremizi
kaplıyor mu?

**Neden spike:** Proje çalışma akışının 3. adımı — bilinmeyen bir veri kaynağı finalize
edilmeden önce ölçülür. Spike 1 **spot** erişimini doğrulamıştı; `fapi.binance.com` ayrı bir
host ve hiç ölçülmemişti. Daha önemlisi kapsam: bir kaynağın var olması, backtest edilebilir
olması demek değil.

**Bu spike sinyal gücü ölçmedi ve bilerek ölçmedi.** Funding ile getiri arasındaki ilişkiye
bakmak, K-039'un saydığı bir çekiliş olurdu — ve ön kayıt yapılmadan bakılan bir ilişki,
sonradan "zaten bunu bekliyordum" demenin kaydıdır. Ölçülen tek şey verinin **kendisi**.

## 1. Erişim — engel yok

| Uç | HTTP | Gecikme |
| --- | --- | --- |
| `fapi.binance.com/fapi/v1/ping` | 200 | 716 ms (ilk, TLS dahil) |
| `dapi.binance.com/dapi/v1/ping` | 200 | 982 ms (ilk, TLS dahil) |
| `fapi/v1/fundingRate` | 200 | 288 ms |
| `futures/data/openInterestHist` | 200 | 284 ms |
| `futures/data/globalLongShortAccountRatio` | 200 | 284 ms |

451 hiçbir istekte görülmedi. Spike 1'in spot için ölçtüğü sonuç türev uçları için de
geçerli: coğrafi engel yok, gecikme spot ile aynı bantta.

## 2. Kapsam — **dört adaydan üçü elendi**

Asıl bulgu burada ve erişimle ilgili değil:

| Kaynak | Kapsam | Granülerlik | Karar |
| --- | --- | --- | --- |
| **fundingRate** | **7,01 yıl** (2019-09-10 → 2026-09-11) | 8 saat | ✅ kullanılabilir |
| openInterestHist | ~31 gün | 1 saat | ❌ elendi |
| globalLongShortAccountRatio | ~31 gün | 1 saat | ❌ elendi |
| takerlongshortRatio | ~31 gün | 1 saat | ❌ elendi |

`futures/data/*` uçları Binance'te **30 günlük** saklama penceresine tabi. 500 kayıtlık ilk
sayfa 20,8 gün, `endTime` ile geriye istenen ikinci sayfa yalnızca 244 kayıt daha verdi ve
orada bitti.

**31 günle walk-forward kurulamaz.** Faz 4'ün bölme yapısı yıllar istiyor; Faz 4'e dönüş 1
zaten 1d'yi *1.936 bar istatistiksel güç tabanının altında* diye elemişti — 744 saatlik
kayıt onun da çok altında. İleriye dönük biriktirmek teorik bir seçenek ama anlamlı bir
pencereye ulaşmak yıllar sürer; bu fazın sorusunu cevaplamaz.

Yani "türev piyasası konumlanması" fikri **tek bir kanala** indi: funding rate. Bu, hipotez
uzayını daraltan bir bulgu ve kayda değer — dört ayrı fikir sanılan şey, ölçülünce bir tane
çıktı.

## 3. Funding verisinin kalitesi — temiz

Tüm geçmiş çekildi (sayfalama, `startTime` ileri yönlü):

| Ölçüm | Değer |
| --- | --- |
| Kayıt | **7.675** |
| Aralık | 2019-09-10 08:00 → 2026-09-11 08:00 UTC |
| Periyot | medyan 8,0 saat · min 8,00 · max 8,0 |
| **8 saat dışı kayıt** | **0 (%0,00)** |
| NaN / boş | 0 |
| Sıfır oran | 0 |
| Oran aralığı | −0,003000 … +0,003000 (±%0,3 tavanı) |
| Medyan oran | **+0,000096** (8 saatte %0,0096) |

Boşluk yok, tekrar yok, tavan dışına taşma yok. Faz 1'in 1h verisinde bulunan 3 boşluk /
1 `suspect` bar gibi bir anomali burada **yok** — ama bu "hiç olmaz" demek değil, Spike 2'nin
dersi tam olarak buydu (dar pencerede anomali görünmez). Doğrulama katmanı yine de yazılacak.

**Kapsam kontrolü:** 1h veri seti 2021-06-28 03:00 → 2026-09-09 09:00 (45.576 bar). Funding
o pencerenin **21 ay öncesinden** başlıyor. Isınma penceresi için de fazlasıyla yer var.

## 4. Ölçümden çıkan bağlayıcı notlar

1. **Funding bir maliyet değil, bir bilgidir.** Sistem BTC/USDT **spot** işlem yapıyor; spot'ta
   funding ödenmez. Yani maliyet modeline (K-016, K-021, K-025) dokunulmaz. Funding yalnızca
   özellik olarak girer.
2. **Medyan funding pozitif** (+%0,0096 / 8 saat). Kalıcı long eğilimi, bilinen bir olgu.
   Bu bir sinyal iddiası değil, verinin tanımı — ve eşik seçiminin merkezi sıfır olamayacağı
   anlamına geliyor: mutlak eşik yerine **persentil** kullanılmalı, yoksa "pozitif funding"
   koşulu neredeyse her zaman doğru olur.
3. **Hizalama look-ahead riski taşıyor.** `fundingTime` ödemenin **gerçekleştiği** an. `t`
   anındaki bir bar yalnızca `fundingTime <= t` olan kayıtları görebilir. 8 saatlik veriyi
   1h barlara yaymak, dikkat edilmezse gelecekten bilgi sızdırır — K-002'nin tam olarak
   kapattığı hata sınıfı, ve look-ahead testi bunu yakalamalı.
4. **Yeni bir kalite bayrağı gerekir mi:** funding kaydı eksikse o bardaki özellik
   `None` olmalı, uydurulmamalı (K-024'ün "bayrak tekildir, boşluk uydurulmaz" kuralı).

## 5. Sonuç

Erişim açık, funding verisi backtest için **yeterli ve temiz**. Diğer üç kaynak
kullanılamaz. Faz 4'e dönüş 3'ün hipotez uzayı bu bulguyla daralıyor ve ön kayıt buna göre
yazılacak.

**Bu spike hiçbir hipotezi test etmedi.** Bir sonraki adım ön kayıt (K-039), ölçüm ondan
sonra.
