"""Aktif çok varlıklı demo bot. (K-134)

Scryne'ın asıl hedefi: çok varlıkta (kripto, EURUSD, US500, NAS100) gün içinde sık işlem.
Bu paket o hedefin **demo** hattıdır; gerçek para yolu yok (`execution/` ve promotion
zinciri ayrı ve dokunulmadı).

Parçalar:
- `strateji` — saf fonksiyonlar: kapanmış barlar → her bar için yön serisi {-1, 0, +1}.
  I/O yok, gelecek yok (K-002/K-003); canlı ve backtest **aynı** fonksiyonu çağırır.
- `risk` — boyut (ATR'ye göre), kaldıraç tavanları, günlük/haftalık kayıp freni.
- `araci` — `KriptoPaper` (Binance public fiyat, simüle dolum) ve `MT5Araci` (yalnız demo hesap).
- `defter` — işlem ve özkaynak kaydı, haftalık karne.
- `dongu` — bar kapanışında tek tur; `geriye` — aynı kurallarla backtest.

Korunan çekirdek kurallar: zaman UTC epoch ms, bar zamanı açılış (K-005); karar kapanmış
barla, dolum sonraki barın açılışında/anlık fiyatta (K-004); kayma her zaman aleyhte (K-007);
kayıp freni riski yalnız azaltır (K-050).
"""
