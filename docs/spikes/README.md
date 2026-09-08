# Spike Raporları

Faz 0'ın çıktısı buraya yazılır. Bir spike'ın amacı kod üretmek değil, **bir bilinmeyeni
ölçüp kapatmaktır.** Spike kodu atılacak koddur ve `research/spikes/` altında yaşar
(git'e girmez); buraya yalnızca **rapor** düşer.

Her rapor şu üç soruyu cevaplar:

1. **Ne bilinmiyordu?** — hangi karar bu ölçüm olmadan verilemiyordu (K-0XX referansı).
2. **Ne ölçüldü?** — gerçek sayılar, tarih, koşullar. Tahmin değil, gözlem.
3. **Karar ne oldu?** — `docs/Kararlar.md`'deki hangi karar kapandı veya değişti.

Raporlar — **dördü de tamamlandı (2026-09-08):**

| Dosya | Kapatır | Sonuç |
| --- | --- | --- |
| `01-binance-erisim.md` | K-015 ✅ | Coğrafi engel yok; rate limit darboğaz değil (klines = sabit 2 weight); testnet ayakta ve canlıyı %0,007 sapmayla takip ediyor |
| `02-veri-hacmi.md` | K-017 ✅ | **Birincil timeframe 1h** — kararı hacim değil, hareket/maliyet oranı verdi (20,85 vs 2,42 bps medyan hareket, 20,02 bps maliyet) |
| `03-parquet-duckdb.md` | K-011 ✅ | Parquet+zstd + DuckDB doğrulandı; parquet yazımı bit düzeyinde deterministik → veri seti hash'i = dosya SHA-256 |
| `04-maliyet-tarifesi.md` | K-016 ✅ | `fee_taker_bps = 10.0`; slippage Faz 1'e devredildi (K-020 → **K-021**) |

**Ham ölçüm çıktıları:** `research/spikes/out/` (JSON, gitignore'da — raporlardaki sayılar
oradan geliyor).

**Kural:** bir spike "çalıştı gibi göründü" ile kapanmaz. Sayı yoksa rapor yok, rapor yoksa
karar kapanmaz, karar kapanmadan Faz 1 mimarisi dondurulmaz.
