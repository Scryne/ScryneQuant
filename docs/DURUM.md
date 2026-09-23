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

- **Yer: ikinci bilgisayar (host, 192.168.1.4), K-138.** Takip: **http://192.168.1.4:8790** (ev ağından).
  Ana makinede bot çalışmaz. Karne hostta: `sq aktif karne --hesap <ad>`.
- Ek demo hesaplar (K-138, doğrulanmamış aday): `mt5-gece` (16:00→09:00 ET), `mt5-aydonumu` (ay sonu → 3. gün).
- Hostta MT5 terminali Integral demo hesabı **50545513**'e bağlı (yalnız fiyat kaynağı); terminal ve Windows
  oturumu açık kalmalı.
- Kayıp freni: gün başına göre %3, hafta başına göre %8 düşüşte her şey kapanır.
- Gözetmen hostta `ScryneQuant-Aktif` (oturumda, 10 dk) altı hesabı ve panoyu ayakta tutar; MT5 terminali
  açık kalmalı. Kalıcı durdurma `sq aktif durdur --hesap <ad>`.
- Integral demo sunucusu algoritmik emri kapalı tutuyor (retcode 10026). Açılırsa `mt5-demo`
  `araci: "mt5"` yapılır ve emirler demo hesaba gider.

## Ölçülen (dürüst tablo)

- **Geriye bakış (K-134, K-135):** 15 strateji × zaman dilimi denemesinin hepsi maliyet sonrası
  negatif. Trend aileleri maliyetsiz de negatif; dönüş ailesinin brüt kârı var, maliyet yiyor.
- **Ön kayıtlı dönüş araştırması (K-136):** 36 aday × 2 piyasa; IS'te seçilen aday OOS'ta **kaldı**
  (kripto −%8,6, MT5 −%3,9). OOS'ta pozitif aday kripto 7/36, MT5 8/36; medyan −%9. Yeni demo
  hesap eklenmedi.
- **Program 2 (K-137, literatür etkileri, Holm k=4):** gece getirisi, gün içi momentum, ay dönümü,
  zaman serisi momentumu → 0/4 PASS. Gece ve ay dönümü etkileri 30 yıllık bağımsız veride gerçek
  (SPY gece +4 bps/gün, t 6); Integral CFD'sinde gece etkisini maliyet (≈ 2,8 bps/gün) sıfırlıyor, ay
  dönümü tutarlı ama 12 yılda istatistiksel eşiği geçmiyor.
- Eski alfa araştırması (64 çekiliş) aynı sonucu vermişti: maliyet sonrası üstünlük yok.
- Yani çalışan demolar **kazanç beklentisiyle değil ölçmek için** çalışıyor; demo karnesi geriye
  bakıştan farklı çıkarsa o ayrı bir bulgu olur.

## Açık işler

1. Dört hesabın ilk haftalık karnesi (2026-09-28 sonrası): demo ↔ geriye bakış tutarlı mı?
2. Integral'den algoritmik işlem izni (Scryne) → gerçek demo emirleri; CFD komisyonu ölçülür.
3. Integral CFD'nin gerçek maliyeti (komisyon + kayma) ölçülürse A1/A3 aynı tanımla yeni ön kayıtla
   yeniden değerlendirilir (K-137). Yeni fikirler de ancak **yeni ön kayıtla**.

## Dondurulmuş

Alfa/promotion/RYPP araştırması, BTC gösterim-pilot-R8 hattı, Jev gölgesi (K-136). Kod ve testler
duruyor; süreç yok. Ayrıntı `.claude/CLAUDE.md` "Dosya haritası".
