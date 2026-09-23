# Funding carry — ön kayıt (K-139)

Tarih: 2026-09-23 (UTC). Koşudan önce commit'lenir; sonuç `2026-09-23-carry-sonuc.json`.
Tek tanım, parametre araması yok. Kural K-138 demo kademesi: sonuç iyi çıkarsa demoya girer;
gerçek para ayrı karar.

## Mekanizma

Spot'ta long + USDT-M perp'te aynı notional short → fiyat yönü nötr. Funding pozitifken short
taraf her funding anında `notional × oran` alır. Getiri = funding − premium değişimi − maliyet.

## Veri (projede, PIT)

`data/turev/funding/` (funding olayları, `calc_time`), `data/turev/premium/` (1h premium index),
`data/evren/<sembol>/1h` (spot fiyat, hacim; listeden çıkanlar dahil). 2020-01 → 2026-08.

## Kural (günlük karar, 00:00 UTC)

- **Uygunluk:** spot'ta son 30 günün medyan günlük işlem hacmi ≥ 20 milyon USDT; en az 30 günlük funding
  geçmişi; o gün premium ve spot verisi var.
- **Sinyal:** son 3 günün funding oranlarının ortalaması, yıllığa çevrilmiş.
- **Giriş:** yıllık ≥ %20 ve boş yer varsa (en yüksek funding önce). **Çıkış:** yıllık < %5 ya da uygunluk
  kaybı. En fazla 8 pozisyon.
- **Boyut:** her pozisyon notional'ı = girişteki özkaynak / (1,5 × 8). 1,5: spot tam + perp teminatı %50
  (2x); cüzdanlar arası günlük dengeleme varsayılır.
- **Maliyet (taraf başı, iki bacak):** spot 10 + perp 5 + kayma 2 × 2 = 19 bps; giriş ve çıkışta.
- **Tasfiye vekili:** gün içinde spot yüksek fiyatı son günlük dengelemeye göre ≥ %45 yükselirse perp
  bacağı tasfiye sayılır: pozisyon kapanır, notional'ın %6'sı kayıp yazılır.

## Rapor

Yıllık getiri (yıl yıl), kârlı hafta oranı, en kötü hafta, azami düşüş, haftalık işlem, ortalama pozisyon;
kâr kaynağı ayrımı (funding / premium / maliyet); tasfiye sayısı. 2020-2023 ve 2024-2026 ayrı.

## Demoya giriş ölçütü (K-138 demo kademesi)

2024-2026 döneminde maliyet sonrası yıllık getiri > 0 ve azami düşüş < %10.
