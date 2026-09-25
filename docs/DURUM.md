---
proje: ScryneQuant
guncellendi: 2026-09-25
type: durum
---
# ScryneQuant — şu anki gerçek

> **⛔ DONDURULDU (2026-09-25).** Scryne projeye dönmeyecek; iş TradeBot'ta (`Projeler/TradeBot`, sıfırdan).
> Host'taki dört demo bot `sq aktif durdur` ile durduruldu, `ScryneQuant-Aktif` görevi devre dışı, pano 8790
> kapalı. Aşağısı dondurulduğu andaki durumdur.

Tek sayfa. "Neden böyle" için `docs/Kararlar.md` (K-141), geçmiş için `docs/arsiv/`.

## Hedef (K-141)

Maliyet sonrası kâr eden bot. Eski kararların törensel kısmı bırakıldı; ölçüm hijyeni (gelecek görmezlik,
sonraki bar dolumu, aleyhte maliyet, PIT evren) kalıyor. **Şu an yalnız demo; gerçek para Scryne'ın API anahtarı
ve açık onayıyla.**

## Çekirdek strateji

`cekirdek`: BTC + ETH spot, kaldıraçsız. Ağırlık = (0,4/2) / 30 günlük oynaklık × SMA100/200 filtresi, brüt ≤ %100,
günde bir karar (UTC 00:05). Backtest 2018-26: yıllık **+%29**, Sharpe 1,1, en kötü düşüş **−%30** (BTC tutmak
−%81). Her alt dönem pozitif (2018-19 +%16, 2020-22 +%40, 2023-26 +%29). Kriptonun yükselişine düşüş korumalı
maruziyettir; gerçekçi beklenti yıllık %10-25.

## Çalışan demo hesaplar (host 192.168.1.4, pano http://192.168.1.4:8790)

| Hesap | Ne | Backtest |
|---|---|---|
| `cekirdek` | yukarıdaki | +%29/yıl, DD −%30 (2018-26) |
| `kripto-carry` | funding carry, yön nötr | +%6,6/yıl, DD −%0,7 (2020-26) |
| `vadeli-bollinger-3x` | 6 perp günlük kırılım, 3x | +%26/+%57 yıllık, DD −%42 (2020-26) |
| `vadeli-donchian-2x` | 6 perp günlük kırılım, 2x | +%11/+%22 yıllık, DD −%15 |

Kapatılan (maliyet sonrası negatif): 15 dk kripto trend/kırılım/dönüş, MT5 RSI, gece, ay dönümü (K-141).
Host güncelleme `tools/host_guncelle.ps1 [-BotlariYenile]`; kalıcı durdurma `sq aktif durdur --hesap <ad>`.

## Ölçülen (özet)

- Sık işlem (15m/1h, 15 strateji, 36 aday dönüş ızgarası, literatür etkileri): hepsi maliyet sonrası negatif.
- Geniş evrenli alt coin trendi: oynaklık ayarlı BTC tutmanın altında (K-141).
- İşe yarayan: günlük/haftalık ufukta BTC/ETH trend filtresi + oynaklık hedefi; funding carry.

## Sıradaki

1. `cekirdek` demo ↔ backtest tutarlılığı (ilk karar günleri emir/fiyat kontrolü).
2. Gerçek para için Scryne'dan: Binance hesabı + yalnız spot işlem izinli, çekme kapalı, IP kısıtlı API anahtarı
   + başlangıç tutarı. Sonra `cekirdek` için gerçek emir aracı (spot, kaldıraçsız) ve küçük tutarla başlangıç.
3. Boştaki USDT'nin faiz getirisi (Binance Simple Earn) — backtest'te sayılmadı, ek getiri.
