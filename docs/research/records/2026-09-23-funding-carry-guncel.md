---
proje: ScryneQuant
tarih: 2026-09-23
karar: K-116
tur: ölçüm (çekiliş değil, strateji değil, defter satırı değil)
type: rapor
---
# Funding carry'nin güncel düzeyi — Hat B'nin ekonomik tabanı çöktü

**Sonuç:** K-110'un "mekanizması farklı tek hat" dediği delta-nötr carry'nin (spot long + perp
short) ham gelir kaynağı, yani funding, son 12 ayda BTC'de **yıllık %3,4**, ETH'de **%2,4**,
SOL'da **−%1,8**, XRP'de **%0,1** (notional'a oranla, maliyetsiz). IS tavanının (2020→2025-02,
BTC %14,2 / ETH %17,1) dörtte biri. Negatif ödeme payı %8'den %24-48'e çıktı.

## Ölçüm

`uv run python tools/funding_guncel.py` — yerel `data/funding/<sembol>.parquet` (son ödeme
2026-09-19). Yıllık = dönem toplamı / gün × 365.

| Sembol | 2024 %/yıl | 2025 %/yıl | 2026 %/yıl | Son 12 ay % | Son 12 ay neg. payı |
| --- | ---: | ---: | ---: | ---: | ---: |
| BTCUSDT | 11,92 | 5,13 | 2,89 | **3,37** | 0,237 |
| ETHUSDT | 12,96 | 4,93 | 1,74 | **2,38** | 0,274 |
| SOLUSDT | 13,62 | 0,35 | −1,37 | **−1,83** | 0,480 |
| XRPUSDT | 14,19 | 3,53 | −0,52 | **0,11** | 0,460 |
| DOGEUSDT | 14,00 | 4,34 | 2,78 | **2,84** | 0,332 |
| LTCUSDT | 14,39 | 5,55 | 2,84 | **3,03** | 0,312 |

## Okuma

1. **Bu da bir tavandır.** Basis M2M, komisyon (giriş/çıkış ≈ 61 bps), marjin ve likidasyon
   yok. Sermaye verimi ≈ yarı (spot + perp teminatı): BTC'de sermayeye oranla ≈ %1,7-2,5/yıl.
   Risksiz alternatif bunun üstünde: DTB3 2026-09-17'de %3,97 (`data/makro/DTB3.parquet`).
2. **Tabanın kaynağı değişti.** IS'te BTC ödemelerinin %42'si faiz tabanında (0,01 %/8s,
   %10,95/yıl) idi; bugünkü %3,4 tabanın altında — premium bileşeni sık sık −0,04 %'ün altında, yani
   perp talebi spotun altında. Taban "sabit faiz" değil, premium ≥ −0,04 % koşuluna bağlı.
3. **K-079/2 kararının bugünkü fiyatı:** vadeli hesap açılsa da güncel funding'le carry,
   risksiz alternatifin altında. Hat B'nin ikinci tavanını bugün koşmak (fee/MMR gelse bile)
   önceden bilinen bir sonuca harcanan iş olur. Yeniden açılma işareti: son 90 günlük BTC
   funding ≥ %8/yıl (risksiz + maliyet + likidasyon payı) — `tools/funding_guncel.py` ile
   ölçülür (`son90g_yillik_pct`). **Bugün: BTC %6,53, ETH %4,28, SOL %2,89** — son 12 aya göre
   toparlanma var, işaretin altında. Sermayeye oranla BTC ≈ %3,3-4,4 ≈ DTB3; üstünlük yok.

## Değişmeyen

Defter 62, K-111 askısı, kapılar, eşikler, promotion. Bu ölçüm hiçbir şey açmaz.
