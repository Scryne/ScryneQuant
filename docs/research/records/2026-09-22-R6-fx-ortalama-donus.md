# R6 — FX ortalama dönüş ailesi: `fx_ortalama_donus` programı (K-104)

Tarih: 2026-09-22 (UTC). Koşucu: `tools/r5_fx_kos.py` (K-102 hattı; kayıtlar `runs/fx/`, gitignore).
Motor aynen: ask/bid fill, spread, çift başına slippage/komisyon (K-100), proxy finansman (K-098),
`fx-5x24`. Pencere K-101 ortak aralığı: 2023-11-19..2024-02-29, 1.721 bar; ısınma 242; **IS 963 /
OOS 516 bar (21,5 gün) — h53-h55 ile aynı barlar, aynı kontrol sayıları** (veri kimliği `44d51a1d9b85`).
Kontrol `fx_evren_esit_agirlik` 21 çift / 0,2 brüt / 120 bar. Sermaye 10.000 USD.

## 1. Hipotezler (koşudan önce kayıtlı: h56, h57; program bütçesi 2/2)

| Defter | Çekiliş | Aday koşulu (haftalık dengelemede) | Izgara (12) | K-061 |
|---|---|---|---|---|
| **h56** | `fx_zaman_serisi_sapma` | `z = (close − sma(pencere)) / atr(14) < −esik`; en derin sapma önce, en fazla N; yoksa nakit | pencere {48,120,240} × esik {1,2} × n {2,5} | incele 1 (h54, "farklı") |
| **h57** | `fx_zaman_serisi_rsi` | Wilder `rsi(pencere) < esik`; en düşük önce, en fazla N; yoksa nakit | pencere {14,24,48} × esik {30,40} × n {2,5} | incele 1 (h4 tek sembol rsi, "parametre varyasyonu" — bilerek) |

h54'ten (sıralama, elendi K-103) farkı: eşik. Yoğunluk ekseni {2,5} **getiri okunmadan**, sinyal-seti
ölçümünden: W1'de 13 dengeleme anında eşiği geçen çift ortalama 1,4-4,6, haftaların %23-85'i boş
(`runs/fx/donus-kaynak-olcumu.json`; program kaydında). Yalnız uzun. Plato seçimi.

## 2. Sonuçlar

| | h56 `zaman_serisi_sapma` | h57 `zaman_serisi_rsi` |
|---|---|---|
| **Seçilen (plato)** | pencere 48, esik 1,0 ATR, n 5 | **seçilemedi** — IS'te 12 noktanın hiçbiri asgari tura (20) ulaşmadı (3-16 tur) |
| IS net / brüt USD | **+5,84** (+0,058 %) / +13,07 | — (en iyi nokta 24/30/2: +0,146 %, 5 tur) |
| IS maliyet kom/slip/spread/fin = toplam | 0,68 / 2,32 / 3,79 / 0,44 = **7,22** (brütün %55'i) | — |
| IS tur / fill | 23 / 59 | — |
| IS kontrol → **fark** | −10,59 → **+16,43 USD** (+0,164 pp) | — |
| OOS net / brüt USD | **+22,59** (+0,226 %) / +23,95 | — (OOS koşulmadı: seçilen nokta yok) |
| OOS maliyet | 0,20 / 0,70 / 0,21 / 0,25 = **1,37** | — |
| OOS tur / fill | **9 / 20** | — |
| OOS kontrol → **fark** | +20,76 → **+1,82 USD** (+0,018 pp) | kontrol +20,76; h57 ölçülemedi → geçemedi |
| OOS `yillik_anlamli` | **hayır** (Sharpe 5,58 kanıt değil) | — |
| Max DD IS / OOS | 0,48 % / 0,11 % | — |

IS taraması h56: 12 noktanın yalnız 2'si geçerli (≥20 tur): (48,1,5) +0,058 % ve (120,1,5) −0,057 %;
n=2 noktalarının hepsi negatif (−0,15..−0,37 %), 9-12 tur. Plato oranı 0,50.

## 3. Kapılar (mevcut eşikler; ölçülemeyen küçültülmedi)

| Kapı | h56 | h57 |
|---|---|---|
| `asgari_islem` (≥30) | **9 → kaldı** | ölçülemedi |
| `pbo` (≤0,0087) | **0,482 → kaldı** | 0,305 → kaldı (tam pencerede 12 nokta) |
| `parametre_perturbasyonu` (≤0,0565) | **1,00 → kaldı** (tek komşu, medyanı negatif: seçilen nokta izole tepe) | ölçülemedi |
| `oos_sharpe` / `oos_is_orani` | 5,58 / 16,1 "geçti" — `yillik_anlamli=False`, kanıt değil (K-102/6) | ölçülemedi |
| `max_drawdown`, stres | geçti (stres bozulma 0,001) | ölçülemedi |
| `evren_dayanikliligi` | 0,82 geçti (USDCHF çıkınca Sharpe 5,58 → 4,58; katkı USDCHF 9,1, CADCHF 6,2 — OOS getirisinin çoğu iki CHF çiftinden) | ölçülemedi |
| walk-forward, rejim | ölçülemedi (pencere sığmıyor) | ölçülemedi |
| Mutlak engel | `gecici_finansman_modeli` | — |

## 4. Tekrar gereksinimi ve aile kararı

- **h56:** durma kuralı ölçüsünde OOS'ta kontrolü geçti — **+1,82 USD, 9 tur, izole tepe (pertürbasyon
  1,0), IS'te 12 noktanın 10'u geçersiz/negatif.** Program kuralı gereği **tekrar gereksinimi** yazıldı:
  K-103 kalıbında sabit nokta (48 / 1 ATR / n oranla) W2 (10 çift, 2024-03..05) ve W3 (4 çift,
  2024-06..07) — ayrı tur, bu pakette koşulmadı. Promotion adayı **değil**.
- **h57:** elendi — hiçbir ızgara noktası asgari tura ulaşmıyor; RSI eşiği 1h FX'te haftalık dengelemede
  fiilen sinyal üretmiyor (48/30 hiç tetiklemedi, önceden yazılmıştı).
- **Aile kararı: kapalı, zayıf.** İki çekilişten biri seçilemedi, öteki 1,8 USD / 9 turla geçti.
  Program bütçesi 2/2 doldu; eşik, pencere, yoğunluk, ölçü genişletilmez (durma kuralı). Ailenin
  tek açık ucu h56'nın tekrar turu; o tur elerse aile tamamen kapanır.

Yapısal not (üç FX programında ortak): haftalık dengeleme × 4,3 haftalık OOS = ≤ 4 karar, 5-10
pozisyonla 5-16 tur; `asgari_islem` (30) bu pencerede **hiçbir** çekilişin geçemeyeceği bir kapı.
Sıklaştırmak maliyeti büyütür (h56 IS'te maliyet brütün %55'i), uzatmak finansman modeli ister (K-101).

## 5. Defter

- `docs/Arastirma-Programlari.jsonl`: `fx_ortalama_donus` açıldı (bütçe 2, kaynak ölçümü) ve kapandı.
- `docs/Hipotez-Defteri.jsonl`: h56, h57 (57 satır). Çoklu test fotoğrafı önbellekten yeniden
  birleştirildi: 45 ölçülebilir aynı, %5 sınırı aynı, h53-h57 ölçülemez (FX null'u yok, K-102/6).
- Kod: `strategy/kutuphane/ortalama_donus.py` (iki sınıf, ortak iskelet), `izgaralar.FX_DONUS_CEKILISLERI`,
  `coklu_test_evren.SINYAL_OZELLIKLERI` (+2), `tools/r5_fx_kos.py` çok programlı (ısınma tabanı 242).
  Testler +4. Yeni katman yok.
