---
proje: ScryneQuant
guncellendi: 2026-09-23
type: durum
---
# ScryneQuant — şu anki gerçek

Tek sayfa, **yürürlükteki** durum. "Neden böyle" için `docs/Kararlar.md`, sayılar için
`docs/research/records/` ve faz raporları. Bu sayfa ile başka bir doküman çelişirse bu sayfa ve
en yeni K kazanır; eski doküman tarihsel kayıttır.

## 1. Doğrulanmış olanlar (cevabı bilinen girdiyle, K-117/K-118)

| Bileşen | Nasıl doğrulandı |
| --- | --- |
| Tek sembollü backtest motoru | Bağımsız vektörel hesapla getiri/Sharpe 4/4 eşit (±%4) |
| Çok enstrümanlı motor | Bağımsız Decimal referans testi (`test_coklu_referans.py`) |
| Look-ahead | Her kayıtlı gösterge + her kütüphane stratejisi, 3 bozma (`test_look_ahead_genel.py`) |
| IS/OOS/walk-forward bölmesi | Kronolojik, örtüşmesiz, ısınma yalnız geriye |
| Çoklu test null'u (`oos_sharpe` 1,04) | Üstünlüksüz kahin 0/60 |
| Promotion kapıları (K-119) | Null 0/60 + gerçek defter 0/38; güçlü sentetik evren 5/6; %65 kahin 17-20/20 |
| Canlı emir katmanı (`exchange/imzali.py`) | Yazmada yeniden deneme yok, belirsiz sonuç sorgulanmadan tekrarlanmaz |
| Risk motoru → execution | Cooldown artık canlı yolda da çalışıyor (K-118) |

## 2. Strateji durumu

- **Promotion'u geçen strateji: yok.** Defter 63 çekiliş.
- 62 çekilişin OOS sonuçları gerçek ölçümdür: null persentili medyan 0,50 (K-110), en iyi OOS
  Sharpe 0,46. Eski kapıların güçsüzlüğü (K-117) bu sonuçları değiştirmiyor.
- h63 (kripto evren zaman serisi trend, K-120): OOS Sharpe −0,54 vs kıyas 0,30 → elendi.
- **Tükenen aileler** (tekrar denenmez): tek sembol TA, funding yönlü, kesitsel
  momentum/ters/düşük oynaklık, kıyas-üstü dışlama, rejim/Jev yönü, kurma katmanı, FX
  seçim/dönüş/oynaklık, zaman serisi trend (kripto evreni) — `docs/research/records/2026-09-22-R7-kapanis-alfa-envanteri.md` §3.
- **Carry (Hat B):** funding son 12 ay BTC %3,4/yıl; bugün risksiz getirinin altında
  (`tools/funding_guncel.py`, işaret: son 90 gün ≥ %8).
- **Açık kaynaklar:** on-chain, emir defteri, haber (ileriye toplama ister); envanter §5.

## 3. Kapılar (12, K-119)

`oos_suresi`, `oos_sharpe` ≥ 1,04 (çoklu test), `oos_is_orani` ≥ 0,5, `wf_katman_basari` ≥ 0,6,
`parametre_kararliligi` ≤ 0,35, `asgari_islem` ≥ 30, `max_drawdown` ≤ 0,25,
`stres_dayanikliligi` (OOS Sharpe oranı) ≥ 0,5, `pbo` (CSCV zarar olasılığı) ≤ 0,05,
`parametre_perturbasyonu` (komşu koruma) ≥ 0,80, `rejim_kararliligi` ≥ 0,685,
`evren_dayanikliligi` ≥ 0,75. Kayıt `config/esikler.json`; promotion 12'sinin tamamını ister.
Tek sembollü strateji `evren_dayanikliligi` yüzünden promotion alamaz — aday evren yolundan gelir.
Yeni/değişen kapı **iki yönlü** doğrulanır (null + `tools/pozitif_kontrol*.py`).

## 4. Canlı / operasyon

- **Gerçek para kuralı (K-122):** `sq execution hazirlik` iki hüküm verir — **sistem hazır**
  (14 günlük testnet + shadow gösterimi, kill tatbikatı, R8 PASS, HEAD'de yeşil testler) ve
  **strateji hazır** (promotion `live_adayi`). Scryne'ın kararı: ikisi birden olmadan gerçek para
  yok (pilot dahil).
- **Gösterim dönemi (2026-09-23 →):** `gosterim-testnet` (sanal para, gerçek borsa emri) ve
  `gosterim-shadow` (gerçek hesap, salt okunur) bu bilgisayarda; `tools/gosterim_gozetmen.ps1` +
  zamanlanmış görev `ScryneQuant-Gosterim` (10 dk) ayakta tutar; durdurmak `runs/gosterim/DURDUR`.
  Shadow bekliyor: `BINANCE_API_KEY` işlem yetkili (salt okunur olmalı) — Scryne Binance'te
  "Enable Spot & Margin Trading"i kapatınca gözetmen kendiliğinden başlatır.
- **Mikro pilot (K-115/K-116):** 100 USDT, 10 USDT kayıpta SAFE_MODE, `sma_kesisim` BTCUSDT 1h,
  alfa iddiası yok; K-122 hükümleri sağlanmadan açılmaz. Yordam `docs/Execution-Runbook.md` §4.3.
- **R8:** `r8-kiyas` gözlem koşusu, host-1, 2026-09-25 başlar, 14 gün, kriterler dondurulmuş
  (`config/r8_kriterler.json`). Operasyon kanıtı, alfa değil.
- Kademe ≥ 2 (gerçek sermaye büyütme) promotion ister; tavan büyütmek kod + test + yeni K.

## 5. Jev

Yön tahmini %49 (K-074…077): işlem kararına bağlanmaz. Yürürlükteki rolü araştırma yönetişimi
(gizli tekrar dedektörü, K-061). Değerlendirilecek: duyuru/delist metni → yalnız **engelleyen**
katman (K-037 izin verir; K-074 izolasyonu yeni K ister).

## 6. Açık işler

1. Çoklu test fotoğrafı 63 çekilişe güncellendi (49 ölçülebilir; %5 sınırı 1,0039, mevcut 1,04'ün
   yanlış pozitifi 0,042). `oos_sharpe` eşiği 9 yıllık tek sembollü OOS için ayrıca kalibre edilmedi
   (uzun OOS'ta tutucu yönde).
2. `asgari_islem` 30 aylık stratejileri dışarıda bırakıyor (bilinçli; null bu çekilişlerde kalibre değil).
3. Maliyet modeli tutucu (taraf başı 10 + 5,3 bps); pilotun gerçek fill'leriyle yeniden kalibre edilir.
