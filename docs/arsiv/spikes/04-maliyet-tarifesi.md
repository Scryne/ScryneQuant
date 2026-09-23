---
proje: ScryneQuant
created: 2026-09-08
type: spike-raporu
spike: 4
kapatir: K-016, K-007 (sayilar)
status: tamamlandi
---
# Spike 4 — Maliyet tarifesi ve spread

**Tarih:** 2026-09-08 · **Yöntem:** Binance resmî ücret sayfası + `api.binance.com`
public `bookTicker` endpoint'ine üç ardışık istek (kurulum yok, tek HTTPS GET).

## 1. Ne bilinmiyordu?

K-007 maliyet modelini "muhafazakâr ve açık" diye tanımladı ama sayı vermedi. Taker
komisyonu kaç bps, slippage varsayımı ne olmalı — ikisi de tahminliydi.

## 2. Ne ölçüldü?

### Komisyon (Binance spot, VIP 0)

| Kalem | Değer |
| --- | --- |
| Maker | **0.100%** (10 bps) |
| Taker | **0.100%** (10 bps) |
| BNB ile ödeme indirimi | %25 → 0.075% |

**Karar:** BNB indirimi **varsayılmaz** (K-007'nin muhafazakârlık kuralı). Model her iki
bacakta da taker kabul eder: **gidiş-dönüş 20 bps.**

### Spread (BTC/USDT, top-of-book)

Üç ardışık ölçüm, ~2 saniye arayla:

| Ölçüm | Mid | Spread | bps | Üst seviye derinliği (bid / ask) |
| --- | --- | --- | --- | --- |
| 1 | 78.347,52 | 0,01 USDT | 0,00128 | 195.171$ / 182.672$ |
| 2 | 78.340,90 | 0,01 USDT | 0,00128 | 359.293$ / 83.626$ |
| 3 | 78.340,90 | 0,01 USDT | 0,00128 | 353.126$ / 58.712$ |

Spread her ölçümde **tek tick** (0,01 USDT) — yani piyasanın verebileceği minimum.

### Başabaş noktası

10.000₺ (~250$) büyüklüğünde, taker/taker bir gidiş-dönüş için:

```
Komisyon        : 0,50$  (20 bps)
Yarım spread    : ~0,00064 bps  → ihmal edilebilir
BAŞABAŞ         : fiyatın %0,2002 yükselmesi gerekiyor
```

## 3. Karar ne oldu?

### Bulgu A — Spread bu projede maliyet kalemi değil

BTC/USDT'nin spread'i 0,00128 bps; komisyon 20 bps. **Komisyon spread'den ~15.600 kat
büyük.** Ayrıca üst seviye derinliği 60.000–360.000$ arasında; 250$'lık bir emir tek
seviyeyi bile tüketmiyor, yani market impact de sıfıra yakın.

Sonuç: K-007'nin "slippage varsayımı spread'i kapsayacak kadar yüksek tutulur" cümlesi
**yanlış bir modele dayanıyordu.** Bu büyüklükte ve bu sembolde slippage'ın kaynağı spread
değil.

### Bulgu B — Bizim fill modelimizde "slippage" aslında fiyat hareketidir

K-004 fill'i **`t+1` barının açılışına** koyuyor. Yani sinyal `t` barı kapanınca üretiliyor,
emir bir sonraki barın açılışında doluyor. Aradaki fark mikroyapı değil, **fiyatın o süre
boyunca hareket etmesi.** 1h timeframe'de bu, saatlerce süren bir belirsizlik penceresi —
mikrosaniyelik spread'in yanında devasa.

Yani K-007'nin `slippage_bps` parametresi bir spread proxy'si değil, **execution
belirsizliği proxy'si.**

**Bunun somut sonucu:** bu parametre tahmin edilerek değil, **tarihsel veriden ölçülerek**
konmalı. Faz 1'de veri geldiğinde `|open[t+1] − close[t]| / close[t]` dağılımına bakılır ve
muhafazakâr bir yüzdelik (ör. medyan yerine 75. persentil) alınır. Bu bir Faz 1 işi olarak
kaydedildi → **K-020**.

> **Düzeltme (Spike 2, aynı gün):** bu paragrafın yönü doğru, **aralığı yanlış.** Kripto
> 7/24 kesintisiz işlem gördüğü için `open[t+1]`, `close[t]`'in birkaç milisaniye
> sonrasıdır — "saatlerce süren belirsizlik penceresi" değil. Ölçüm: 1h'de vakaların
> %52,2'sinde iki fiyat **birebir aynı**, 75. persentil 0,0014 bps. Gerçek pencere bar
> kapanışı ile emrin borsada dolması arasıdır (~300 ms). K-020 → **K-021**.

### K-007'ye giren kesin değerler (v1 başlangıcı)

```
fee_maker_bps      : 10.0     (kullanılmıyor; model taker varsayıyor)
fee_taker_bps      : 10.0     ← ölçüldü, BNB indirimi yok
slippage_bps       : GEÇİCİ 5.0 — Faz 1'de kalibre edilecek (K-021)
bnb_discount       : false    (muhafazakârlık kuralı)
```

`slippage_bps` bilerek geçici. Faz 1 bitene kadar bu değerle üretilen hiçbir sonuç
promotion'a giremez.

### Bulgu C — "Çok işlem yapan strateji" matematiği

Başabaş %0,2002. Yani:

| İşlem sıklığı | Yıllık maliyet (bileşiksiz) |
| --- | --- |
| Günde 10 | **~%501** |
| Günde 1 | ~%50 |
| Haftada 1 | ~%10 |

Bir stratejinin günde 10 işlem yapması, yılda %500'ün üzerinde brüt getiri üretmesi
gerektiği anlamına gelir — sadece başabaş kalmak için. Bu, Faz 4'te işlem sıklığının neden
birinci sınıf bir metrik olduğunu tek başına açıklıyor.

## 4. Kapanmayan kısım — *sonradan kapandı (2026-09-08, aynı gün)*

- ~~**K-016 kısmen açık.**~~ **Kapandı.** Komisyon tarifesi burada kapandı; `slippage_bps`
  Faz 1'e devredildi. **Ancak bu raporun önerdiği kalibrasyon yöntemi (K-020) Spike 2'de
  ölçülüp çürütüldü** — `|open[t+1] − close[t]|` dağılımı neredeyse sıfır çıktı (1h'de
  vakaların %52,2'sinde iki fiyat birebir aynı). Yerine K-021 geçti: yürütme penceresindeki
  fiyat hareketi. Ayrıntı: `02-veri-hacmi.md` §4.
- ~~**K-015'e kısmi kanıt.**~~ **Kapandı** — Spike 1 (`01-binance-erisim.md`) kimlik
  doğrulamalı endpoint'leri, rate limit'in gerçek tüketimini ve Spot Testnet'i ölçtü.
  Hesap açma/KYC ise ölçülemez (idari adım); Faz 7/8'in ön koşulu olarak Roadmap'e yazıldı.

## Kaynaklar

- [Binance — Fee Schedule](https://www.binance.com/en/fee/schedule)
- `GET https://api.binance.com/api/v3/ticker/bookTicker?symbol=BTCUSDT` — 2026-09-08,
  üç ardışık ölçüm
