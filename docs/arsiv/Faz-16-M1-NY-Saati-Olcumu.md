---
proje: ScryneQuant
faz: 16
tur: gerekçe ölçüsü (çekiliş değil)
tarih: 2026-09-19
type: rapor
durum: kapandı — Lunch ailesi çekiliş harcanmadan kapandı
---
# Faz 16 — M-1 "NY saati çapası": Lunch ailesinin gerekçe ölçüsü

**Sonuç: BTC'de 13:00 ET (NY öğle) çapasına bağlı bir süpürme-dönüş yapısı ölçülemedi.**
Program adayı 01'in (`docs/arsiv/program-adaylari/01-transkript-desenleri/README.md` §4) önceden
yazılmış karar kuralı iki testten birini geçemedi; Lunch ailesi (KAANERMI-LUNCH-01-h1,
02-h1, 11-h1) **program kaydına giremez** ve kural gereği çapa, pencere ya da ufuk
değiştirilerek **tekrar ölçülmez**.

## Kurulum

Tanım README §4'te 2026-09-15'te sonuç görülmeden yazıldı; `tools/faz16_m1_ny_saati.py` onu
olduğu gibi hesaplar. Parametre seçimi yok. Veri `data/market/BTCUSDT/1m.parquet`
(SHA-256 `5a3b33c7…`, 1.630.476 `ok` bar, 2023-08-04 → 2026-09-09 UTC). Olay: hafta içi ET günü,
[a−60, a) aralığının low/high'ı, [a, a+30) içinde ilk süpürme + geri kapanış, y = 60 dk ileri
log-getiri (süpürme yönüne göre işaretli), gün başına ilk olay. S(a) = ortalama / SE.

## Sonuç

| Test | Ölçüm | Kural | Sonuç |
| --- | --- | --- | --- |
| 1 — saat plasebosu | S(13:00 ET) = **0,49** (n = 430); 96 çapa içinde sıra **37**; p = **0,385** | p ≤ 0,05 | ✗ |
| 2 — yaz saati ayrımı (kış, 544.500 bar) | S(18:00 UTC = 13:00 ET) = −0,07 (n = 138) vs S(17:00 UTC) = −0,57 (n = 133) | NY saati > UTC saati | ✓ (ikisi de negatif; fark 0,5 SE — anlamsız) |

96 çapanın S dağılımı: medyan 0,28, min −2,01, max 2,96 (15:15 ET). 96 bağımsız sıfır
hipotezinde beklenen azami ≈ 2,5; 2,96 bir keşif değil, en büyük plasebo. Kural bu çapaya
geçişi yasaklıyor — geçmek K-039'un tam olarak saydığı çekiliştir.

## Okuma

- Kaynak videoların iddiası ("NY öğle saatinde likidite süpürmesi sonra dönüş") NQ üzerine
  anlatılıyor; BTC'de aynı saat 95 rastgele çapadan ayırt edilemiyor. Bu, iddianın NQ'da da
  yanlış olduğunu **söylemez** — o veri bu projede yok (Grup B, K-053).
- Grup A'nın kalan yedi adayı (fib, FVG, inside bar, günlük süpürme, OB, volatilite) saat
  eksenine dayanmaz; K-051/2'nin istediği "belirgin farklı bilgi kaynağı" ölçüsü onlar için
  hâlâ yok. Aynı BTC fiyat geçmişinden türeyen desenler K-045 kapsamındadır.
- Çekiliş harcanmadı: defter 52'de kaldı, `oos_sharpe` eşiği değişmedi.

Ham çıktı: `runs/faz16/m1_ny_saati.json` (96 çapanın tamamı).
