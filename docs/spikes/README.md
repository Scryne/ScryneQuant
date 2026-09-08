# Spike Raporları

Faz 0'ın çıktısı buraya yazılır. Bir spike'ın amacı kod üretmek değil, **bir bilinmeyeni
ölçüp kapatmaktır.** Spike kodu atılacak koddur ve `research/spikes/` altında yaşar
(git'e girmez); buraya yalnızca **rapor** düşer.

Her rapor şu üç soruyu cevaplar:

1. **Ne bilinmiyordu?** — hangi karar bu ölçüm olmadan verilemiyordu (K-0XX referansı).
2. **Ne ölçüldü?** — gerçek sayılar, tarih, koşullar. Tahmin değil, gözlem.
3. **Karar ne oldu?** — `docs/Kararlar.md`'deki hangi karar kapandı veya değişti.

Beklenen raporlar:

| Dosya | Kapatır | Konu |
| --- | --- | --- |
| `01-binance-erisim.md` | K-015 | Türkiye'den erişim, KYC, rate limit, Spot Testnet durumu |
| `02-veri-hacmi.md` | K-017 | 1h ve 1m veri boyutu, indirme süresi, birincil timeframe |
| `03-parquet-duckdb.md` | K-011 | Saklama formatı ve sorgu performansı doğrulaması |
| `04-maliyet-tarifesi.md` | K-016 | Güncel komisyon tarifesi ve gözlenen spread |

**Kural:** bir spike "çalıştı gibi göründü" ile kapanmaz. Sayı yoksa rapor yok, rapor yoksa
karar kapanmaz, karar kapanmadan Faz 1 mimarisi dondurulmaz.
