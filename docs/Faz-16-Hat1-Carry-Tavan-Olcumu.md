---
proje: ScryneQuant
faz: 16
tur: tavan ölçümü (çekiliş değil, Jev yok, backtest yok, execution yok)
tarih: 2026-09-20
type: rapor
durum: FURTHER-RESEARCH-ELIGIBLE — strateji değil, promotion kanıtı değil
---
# Hat 1 / Adım 0 — Delta-nötr carry'nin maliyetsiz in-sample tavanı

**Sonuç: FURTHER-RESEARCH-ELIGIBLE.** Spot long + perp short pozisyonunun yalnız funding +
basis verisinden hesaplanan, maliyeti ve likidasyonu sıfır sayan in-sample tavanı BTC'de
**yıllık +%14,2, Sharpe 9,5**; ETH +%17,1 / 8,8; 28 sembollük eşit ağırlıklı havuz
**+%13,8 / 6,6**, max DD %4,3. 1,04 eşiğinin çok üstünde. **Bu bir tavandır**: hiçbir
maliyet, marjin, likidasyon, borsa riski, kapasite ve zamanlama içermez; stres kapısı
tanımlı değil. "Carry çalışıyor" sonucu **çıkarılmaz**; çıkarılan tek şey, bu hattın
sonraki adımının (gerçek maliyet + marjin + stres tanımı) gerekçelendirildiğidir.

## 1. Tanımlar — repodan, uydurulmadı

| Terim | Repo tanımı | Kaynak |
| --- | --- | --- |
| funding | Ödeme olayı: `funding_time`, `funding_rate`; pozitif oran long'un short'a ödediği tutar | `data/funding.py`, K-042 |
| basis | Premium index 1h klines `close`'u (perp − endeks, oran) — "perp primi (vadeli talep)" | `data/funding.py::evren_premium_dizisi`, `strategy/kutuphane/evren_funding.py`, `data/turev/premium/` |
| carry | Repoda pozisyon tanımı **yok**. Bu ölçümde: eşit notional spot long + perp short (Gap Audit Hat 1) | `docs/Alpha-Discovery-Gap-Audit.md` |

## 2. Formül ve varsayımlar

Ödeme dönemi `t` için notional'a oranla getiri:

```
r_t = funding_rate_t − (basis_t − basis_{t−1})
```

Short perp funding'i alır (oran pozitifse), basis düşerse kazanır; spot bacak fiyat yönünü
nötrler. `basis_t` = ödeme anında kapanan 1h premium barının `close`'u; eşleşmeyen ödeme
düşürülür (BTC'de 367/5.960, çoğu premium arşivinin başladığı 2020-01 öncesi). Dönemler
UTC güne toplanır (funding aralığı sembole göre 8h/4h olabilir); Sharpe = ort/σ·√365.
Basis terimi teleskopiktir (BTC'de yıllık −0,00007) ama M2M varyansı gerçektir.

**İdeal varsayımlar — hepsi tavanı yukarı iter:** komisyon/spread/slippage 0; marjin faizi
0; likidasyon yok; notional tam eşit ve sürekli dengeli; funding tam alınır; premium index =
mark basis; borsa/karşı taraf riski 0; kapasite sınırsız; giriş/çıkış zamanlaması yok
(pozisyon pencere boyunca açık).

## 3. Veri ve pencere

| | |
| --- | --- |
| Funding | `data/funding/<sembol>.parquet` (REST, `data/funding.py::indir`, 2026-09-19 yenilendi); BTC SHA-256 `900484f2…`, 5.960 IS ödemesi |
| Premium | `data/turev/premium/<sembol>.parquet` (Binance arşivi `premiumIndexKlines`, aylık zip SHA'ları `.kaynak.json`'da); BTC SHA-256 raporda (`runs/faz16/carry_tavan.json::semboller.*.veri`) |
| Pencere | **In-sample:** ilk ödeme (BTC 2020-01-01) → **2025-02-16 18:00 UTC** (BTC tek-sembol kuralının OOS başlangıcı, `research/bolme.is_oos`, 45.576 barlık dosya). OOS okunmadı. |
| Semboller | BTC, ETH + PIT 2026-09 ilk 50; funding **ve** premium'u olan 28'i ölçüldü, 22'si atlandı (vadeli yok / premium arşivi yok: stablecoin, tokenize hisse, PEPE→1000PEPE vb.) |
| Betik | `tools/faz16_carry_tavan.py` → `runs/faz16/carry_tavan.json` |

## 4. Sonuçlar (maliyet öncesi tavan)

| Sembol | Gün | Toplam Sharpe | Funding Sharpe | Funding %/yıl | Basis vol %/yıl | Max DD | Neg. ödeme payı | En uzun neg. seri |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BTCUSDT | 1.871 | **9,48** | 11,51 | 14,2 | 0,85 | 1,5 % | 0,12 | 24 (8 gün) |
| ETHUSDT | 1.871 | 8,80 | 10,76 | 17,1 | 1,05 | 1,9 % | 0,11 | 25 |
| LTCUSDT | 1.862 | 8,20 | 10,35 | 18,1 | 1,3 | 0,9 % | 0,10 | 18 |
| XRPUSDT | 1.865 | 7,33 | 9,00 | 18,6 | 1,5 | 2,5 % | 0,14 | 28 |
| DOGEUSDT | 1.679 | 5,52 | 8,00 | 15,4 | 1,9 | 2,6 % | 0,14 | 14 |
| AVAXUSDT | 1.605 | 3,29 | 3,96 | 9,5 | 1,4 | 6,6 % | 0,25 | 48 |
| BCHUSDT | 1.871 | 2,48 | 3,85 | 7,9 | 2,3 | 20,7 % | 0,32 | 90 |
| TRXUSDT | 1.856 | 2,18 | 2,60 | 5,6 | 1,3 | 21,7 % | 0,31 | 103 |
| SOLUSDT | 1.614 | **0,03** | 0,04 | 0,4 | 10,7 | 52,9 % | 0,24 | 53 |
| BNBUSDT | 1.830 | **−0,05** | −0,08 | −0,2 | 1,5 | 30,1 % | 0,28 | 46 |
| ENAUSDT | 321 | **−8,82** | −11,70 | −29,2 | 2,4 | 25,8 % | 0,49 | 37 |
| **Havuz (28, eşit ağırlık)** | — | **6,55** | — | 13,8 | — | **4,3 %** | — | — |

Tam tablo (28 sembol) `runs/faz16/carry_tavan.json`. Eşiği (1,04) geçen: 25/28; geçmeyen
SOL, BNB, ENA. Kısa geçmişli semboller (PENGU 61 gün, TRUMP 30 gün) tabloda var ama
anlamsız — 30 günden kısa seride Sharpe hesaplanmıyor, 61 gün de bir yıl değil.

### Yıl bazında (BTC / ETH funding, %/yıl; Sharpe toplam)

| Yıl | BTC funding | BTC Sharpe | BTC neg. payı | ETH funding | ETH Sharpe | ETH neg. payı |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2020 | 17,2 | 9,2 | 0,14 | 27,3 | 11,9 | 0,03 |
| 2021 | 30,9 | 13,9 | 0,07 | 37,7 | 12,6 | 0,04 |
| **2022** | **4,1** | 6,3 | 0,22 | **0,8** | **0,66** | 0,34 |
| 2023 | 7,9 | 8,5 | 0,10 | 8,3 | 10,5 | 0,09 |
| 2024 | 11,9 | 14,6 | 0,08 | 13,0 | 15,4 | 0,04 |
| 2025 (47 g) | 7,2 | 18,3 | 0,05 | 7,0 | 13,9 | 0,10 |

SOL 2022: **−%38,0**; BNB 2022–2025 dört yıl negatif. Carry sembole ve yıla göre işaret
değiştiriyor; "havuz Sharpe 6,6" BTC/ETH/LTC/XRP ağırlıklı bir ortalamadır.

### Bileşen ayrıştırması — tavanın yapısı

BTC'de IS ödemelerinin **%42,3'ü tam olarak 0,0100 %** (Binance'in faiz bileşeni tabanı:
`clamp(faiz − premium, ±0,05 %)`, faiz 0,03 %/gün); medyan ödeme = taban. Taban tek başına
**%10,95/yıl** eder. Yani BTC tavanının 14,2 puanının ≈11'i sabit faiz bileşeni, ≈3'ü
premium'a bağlı talep bileşenidir. Bu, tavanı "alfa" değil, **borsanın fiyatladığı bir
faiz**e yaklaştırır: taban, premium −0,04 %'ün altına inmedikçe ödenir; borsa faiz
parametresini değiştirirse taban da değişir (ölçülemez, ilan edilir).

## 5. 1,04 karşılaştırması ve karar kuralı

| | Değer | Eşik | |
| --- | ---: | ---: | :-: |
| Havuz toplam Sharpe (tavan) | 6,55 | ≥ 1,04 | ✓ |
| BTC toplam Sharpe (tavan) | 9,48 | ≥ 1,04 | ✓ |
| Havuz max DD (tavan) | 4,3 % | ≤ 25 % | ✓ |
| Stres kapısı | **tanımsız** | — | — |

Önceden yazılan kural (Gap Audit Hat 1): tavan < 1,04 → CLOSE; ≥ 1,04 ve DD ≤ %25 →
FURTHER-RESEARCH-ELIGIBLE. **Sonuç: FURTHER-RESEARCH-ELIGIBLE.**

## 6. Sınırlamalar — bu sayı neden bir kanıt değil

1. **Sharpe burada yanlış risk ölçüsü.** Günlük varyans küçük çünkü funding neredeyse
   sabit; gerçek risk kuyrukta: perp bacağının likidasyonu (spot ve vadeli ayrı hesap ve
   teminat), borsa/karşı taraf, funding'in uzun süre negatife dönmesi. Bunların hiçbiri
   günlük σ'da görünmez. Kapı sistemi bunu `stres` kapısında ölçer; **stres tanımı yok**.
2. **Pozitif funding rejimine bağımlılık.** IS 2020–2025 iki boğa içeriyor; 2022'de ETH
   Sharpe 0,66, SOL −%38, BNB dört yıl negatif. BTC/ETH'de bile en uzun negatif seri 8 gün.
   Havuz sonucu, sembol seçiminin (PIT ilk 50, likit) ve BTC/ETH ağırlığının eseri.
3. **Tabanın yapısı.** Getirinin ≈%77'si (BTC) faiz bileşeni tabanıdır — borsa parametresi,
   piyasa sinyali değil. Bu, USDT'nin kendi getiri alternatifleriyle (borç verme, stablecoin
   faizi) karşılaştırılmadan "edge" sayılamaz; o karşılaştırma yapılmadı.
4. **Kapasite ve sermaye verimi ölçülmedi.** Notional'ın tamamı yatırım sayıldı; gerçekte
   spot + perp marjini iki kat sermaye bağlar, getiri oranı yaklaşık yarıya iner.
5. **Maliyet ayrı tutuldu** (istendiği gibi). Mertebe: giriş/çıkış 2 bacak × 30,6 bps ≈
   61 bps tek seferlik, yıllık 14 puanın %4'ü — belirleyici değil; belirleyici olan
   dengeleme sıklığı (basis M2M'i dengelemek her seferinde maliyet) ve marjin faizi.
6. **Eşleşmeyen ödemeler** (BTC 367) düşürüldü; 2020 öncesi funding verisi premium'suz.
7. **Zamanlama yok.** Bu tavan "her zaman açık" pozisyonun tavanıdır; funding işaretine
   göre açıp kapamak bir stratejidir, bir çekiliştir, burada yapılmadı.

## 7. Bu ölçümün açmadığı şeyler

Program yok, defter satırı yok, strateji yok, execution yok. K-008/K-033/K-046/K-057 ve
Final-Doküman spot kapsamı **açılmadı**. Bir sonraki adım (yalnız onayla): stres tanımı
(funding 30/90 gün negatif senaryosu; %X rallide perp marjin çağrısı), gerçek maliyet +
marjin modeli, sermaye verimi ve USDT alternatif getiri kıyası ile **ikinci tavan**; o da
geçerse K-051 programı ve mimari genişleme kararı.
