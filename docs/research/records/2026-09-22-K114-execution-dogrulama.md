# K-114 — execution yolu uçtan uca doğrulama (paper, shadow, testnet, kill)

Tarih: 2026-09-22 (UTC). Tür: operasyon ölçümü — **alfa, strateji ya da promotion kanıtı değildir.**
Bütün koşular `gozlem` risk modunda (K-035), strateji mevcut kütüphaneden `sma_kesisim` (yeni hipotez,
çekiliş, aile yok; defter 62, K-111). Kod: `c0931a2`…`d08dd0f`. Koşu dosyaları `runs/execution/`
(`.gitignore`); sayılar buraya kopyalandı.

| Koşu | Mod / veri | Ölçülen | Sonuç |
| --- | --- | --- | --- |
| `paper-tekrar-1` | PAPER, yerel depo BTCUSDT 1h, 2.000 bar tekrar (300 ısınma) | 50 sinyal → 50 risk onayı → 49 emir, 49 FILLED; emir + pozisyon mutabakatı her barda temiz; kurallar canlı `exchangeInfo`dan | `gecti` |
| `paper-canli-1m` | PAPER, public canlı 1m barlar, 45 dk | 45 bar, 7 sinyal → 7 emir, 7 FILLED (sonraki barın açılışı + aleyhte slippage); pozisyon farkı 0 | `gecti` |
| `shadow-canli-1m` | SHADOW, canlı hesap salt okunur, 40 dk | `apiRestrictions`: `enableSpotAndMarginTrading=false`, çekim/transfer/margin/futures kapalı; 40 bar, 5 sinyal → 3 `GOLGE` (2 çıkış sinyali "hedefte": shadow pozisyon açmaz); **gönderilen emir 0**; kural reddi 0; pozisyon farkı 0; saat sıçraması 0 | `gecti` |
| `shadow-kill-tatbikat` | SHADOW, canlı host kill tatbikatı | Yaşayan süreç (pid 2092) `TerminateProcess` ile sonlandırıldı, rapor 1.231 ms; canlı hesapta açık emir 0; yeniden başlatma hat + risk motoru SAFE_MODE'da açıldı, plansız kesinti 1 sayıldı, SAFE_MODE'da GOLGE üretilmedi | kill `basarili` (koşu raporu `gecti=false`, beklenen) |
| `testnet-canli-1m` | TESTNET (Binance Spot Testnet), canlı 1m barlar | BUY 0,00231 @ 86.546,22 → FLAT 0,00231 @ 86.482,16, ikisi FILLED; kapanış mutabakatı emir uyuşmazlığı 0, pozisyon farkı BTC 0 / USDT 0 | `gecti` |

Mod geçişleri (`runs/execution/mod.json`, zincirli + audit): DISABLED → PAPER (18:33:56) → SHADOW
(18:34:55) → TESTNET (19:15:23). Test kaydı: 2.401 geçti, 0 kalan @ `d08dd0f`.

**LIVE_PENDING_APPROVAL kapısı (19:23, `--ag`): KAPALI.** Geçen: mod kaydı, R8 sözleşmesi
(`2c3d520e…`, CRLF normalize), risk config, paper kanıtı, kill tatbikatı, testler, canlı bağlantı.
Kalan: testnet kanıtı (o an koşu sürüyordu; şimdi var), `shadow` risk modlu shadow kanıtı, strateji
promotion `LIVE`, R8 kapanışı (K-112), kademe/risk sermayesi, açık kararlar (Faz-8-Hazirlik §6), venue
statüsü, kritik hata (tatbikatların bıraktığı SAFE_MODE işaretleri — bilerek bırakıldı, kaldırmak
`sq execution safe-kaldir`), işlem anahtarı yetkisi (anahtar yok, bilerek).

Gözlem: testnet komisyon kesmiyor (Faz 7 §7 aynen); canlı komisyon ilk kez Kademe 1'de ölçülür.
