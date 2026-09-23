# Kaldıraçlı vadeli trend / kırılım — ön kayıt (K-140)

Tarih: 2026-09-23 (UTC). Koşudan önce commit'lenir; sonuç `2026-09-23-kaldirac-trend-sonuc.json`.
Scryne'ın getirdiği tarif: kırılımda 10-20x long/short, iz süren stop, SuperTrend, Bollinger patlaması,
%1-2 keskin stop. Bu kayıt onu tanımıyla test eder; parametreler yaygın standart değerlerdir, aranmaz.

## Veri

BTC, ETH, SOL, XRP, BNB, DOGE. Fiyat: `data/evren/<sembol>/1h` (spot, perp'e vekil; premium ihmal),
funding: `data/turev/funding/` (long pozitif oranda öder, short alır). Dönem 2020-01-01 → 2026-08-31.
**IS 2020-2023, OOS 2024-2026.**

## Stratejiler (karar grafik kapanışında, giriş sonraki 1 saatlik bar açılışında)

- **S1 Donchian (Turtle 2):** kapanış > 55 bar tepesi → long; < 55 bar dibi → short. Çıkış: giriş sonrası uç
  noktadan 3 × ATR(20) iz süren stop (saatlik barla denetlenir) ya da ters 20 bar kanalı kırılımı.
- **S2 SuperTrend (ATR 10, çarpan 3):** yön değişince ters çevir (hep piyasada).
- **S3 Bollinger (20, 2σ):** kapanış üst bandın üstü → long, alt bandın altı → short. Çıkış: kapanış orta
  bandı (SMA 20) ters yönde geçince.
- Zaman dilimi: **4h** ve **1d**. Her stratejide **%2 keskin stop** (girişten %2 aleyhte fiyat) açık/kapalı.
  → 3 × 2 × 2 = **12 yapılandırma**.

## Kaldıraç ve likidasyon

Sermaye 6 sembole eşit bölünür (izole). Pozisyon notional'ı = kaldıraç × dilim özkaynağı. Kaldıraç ∈
{1, 2, 3, 5, 10, 20}. **Likidasyon:** işlem içinde girişten aleyhte en büyük hareket (saatlik yüksek/düşük)
≥ 1/kaldıraç − %0,5 ise dilim o işlemde **tamamen** kaybedilir (yeniden fonlama yok). Maliyet taraf başı
taker 5 + kayma 2 bps (notional üzerinden), funding notional üzerinden.

## Seçim ve ölçüt

- Seçim (yalnız IS): 12 × 6 = 72 (yapılandırma, kaldıraç) içinde **IS sonu özkaynağı en yüksek** olan (Scryne'ın
  "maksimum kazanç" hedefi).
- Demo ölçütü (K-138 demo kademesi): seçilenin OOS'ta maliyet sonrası toplam getirisi > 0.
- Rapor: her yapılandırma × kaldıraç için IS/OOS toplam, yıllık, azami düşüş (işlem içi en kötü nokta dahil),
  likidasyon sayısı.
