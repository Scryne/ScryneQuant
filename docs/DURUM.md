---
proje: ScryneQuant
guncellendi: 2026-09-23
type: durum
---
# ScryneQuant — şu anki gerçek

Tek sayfa. "Neden böyle" için `docs/Kararlar.md` (K-134…K-136), geçmiş için `docs/arsiv/`
(2026-09-23 öncesi DURUM dahil).

## Hedef

Çok varlıkta (kripto, EURUSD ve diğer pariteler, altın, S&P, Nasdaq, Dow) sık işlem yapan bot.
**Şu an yalnız demo; gerçek para yok.** Gerçek paraya geçiş yeni K + önceden yazılmış sayısal
ölçüt + elle onay ister. TR'de kaldıraçlı FX/CFD gerçek parası SPK kuralıyla ≥ 50.000 TL teminat
ve en fazla 1:10 kaldıraç.

## Çalışan

| Hesap | Piyasa | Strateji | Aracı |
|---|---|---|---|
| `kripto-trend` | 10 büyük coin, 15 dk, yalnız alış | EMA 20/50 trend | Binance fiyatı, simüle dolum |
| `kripto-kirilim` | aynı | 20 bar kırılım | aynı |
| `kripto-donus` | aynı | RSI 3 ortalamaya dönüş | aynı |
| `mt5-demo` | EURUSD, GBPUSD, USDCHF, USDJPY, AUDUSD, NZDUSD, USDCAD, XAUUSD, S&P, NASDAQ, DJI · 1 saat · alış + açığa satış | RSI 3 ortalamaya dönüş | Integral MT5 demo fiyatı/spread'i, simüle dolum, kur çevrimi, gecelik swap |

- Takip: http://127.0.0.1:8790 (`sq execution pano`). Karne: `sq aktif karne --hesap <ad>`.
- Kayıp freni: gün başına göre %3, hafta başına göre %8 düşüşte her şey kapanır.
- Gözetmen (`ScryneQuant-Gosterim`, 10 dk) dört hesabı ve panoyu ayakta tutar; MT5 terminali açık
  kalmalı. Kalıcı durdurma `sq aktif durdur --hesap <ad>`.
- Integral demo sunucusu algoritmik emri kapalı tutuyor (retcode 10026). Açılırsa `mt5-demo`
  `araci: "mt5"` yapılır ve emirler demo hesaba gider.

## Ölçülen (dürüst tablo)

- **Geriye bakış (K-134, K-135):** 15 strateji × zaman dilimi denemesinin hepsi maliyet sonrası
  negatif. Trend aileleri maliyetsiz de negatif; dönüş ailesinin brüt kârı var, maliyet yiyor.
- **Ön kayıtlı dönüş araştırması (K-136):** 36 aday × 2 piyasa; IS'te seçilen aday OOS'ta **kaldı**
  (kripto −%8,6, MT5 −%3,9). OOS'ta pozitif aday kripto 7/36, MT5 8/36; medyan −%9. Yeni demo
  hesap eklenmedi.
- Eski alfa araştırması (64 çekiliş) aynı sonucu vermişti: maliyet sonrası üstünlük yok.
- Yani çalışan demolar **kazanç beklentisiyle değil ölçmek için** çalışıyor; demo karnesi geriye
  bakıştan farklı çıkarsa o ayrı bir bulgu olur.

## Açık işler

1. Dört hesabın ilk haftalık karnesi (2026-09-28 sonrası): demo ↔ geriye bakış tutarlı mı?
2. Integral'den algoritmik işlem izni (Scryne) → gerçek demo emirleri; CFD komisyonu ölçülür.
3. Maliyeti düşüren yeni fikirler (limit emir, daha seçici giriş) ancak **yeni ön kayıtla**.

## Dondurulmuş

Alfa/promotion/RYPP araştırması, BTC gösterim-pilot-R8 hattı, Jev gölgesi (K-136). Kod ve testler
duruyor; süreç yok. Ayrıntı `.claude/CLAUDE.md` "Dosya haritası".
