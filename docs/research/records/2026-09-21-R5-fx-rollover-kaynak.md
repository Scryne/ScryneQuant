# FX rollover/swap oranı — gerçek broker kaynağı araştırması (R5 Paket 4, K-101)

Erişim tarihi: 2026-09-21 (UTC). Amaç: K-098/K-100'deki 21 `proxy + geçici` finansman modelini
FXCM'nin **tarihli, çift bazlı** rollover oranıyla değiştirmek. Sonuç: **böyle bir kaynak yok**;
proxy'ler geçici kalır, promotion engeli (`gecici_finansman_modeli`) korunur.

## Taranan resmi kaynaklar

| Kaynak | Ne veriyor | Tarihli oran? |
|---|---|---|
| `fxcm.com/markets/help/rollover-where-is-rollover-shown/` (+ `/uk/`, `/au/`) | Rollover **yalnız Trading Station**'da: Simple Dealing Rates → `Roll S` / `Roll B`, **1k lot** başına, "every effort is made to display rollover rates one day before they are posted to your account". | Hayır — yalnız yarınki değer, platform içi, hesap gerekir. |
| `fxcm.com/ca/help/c/trading/execution-rollover/rollover/` | Tanım: 5pm EST'de açık pozisyona rollover; oran "multiple liquidity providers"dan. | Hayır. |
| `fxcm.com/markets/help/fx-trading-forex-product-guide/` | Genel tanım; Çarşamba 3 gün, tatilde 0 + iki iş günü önce ek gün. | Hayır. |
| **`docs.fxcorporate.com/user-guide/FXCMFXRolloverCalendar.pdf`** (FX Rollover Calendar, Q3 2026, 4 sayfa) | Tarih × çift **gün çarpanı** tablosu (0/1/2/3/4): Çarşamba 3, Cmt/Paz 0, tatilde 0 ve iki iş günü önce +1. 46 çift (bizim 21 dahil). | **Oran yok**, yalnız gün sayısı; yalnız cari çeyrek. |
| `github.com/fxcm/MarketData` README | Candle (m1/H1/D1), tick (e-posta), order flow, sentiment. | Rollover veri seti **yok**. |
| `github.com/fxcm/ForexConnectAPI` README | "get rollover" örneği (`FC-examples-master.zip`): Offers tablosu `RolloverBuy`/`RolloverSell`, **cari** değer, hesap girişi gerekir. | Hayır (canlı tablo, arşiv yok). |
| `fxcm-api.readthedocs.io` (REST) | 404. | — |

## Üçüncü taraf (resmi değil, kullanılmadı)

- `forexbenchmark.com/brokers/swaps/` — tarihli swap karşılaştırması, 39+ broker; **FXCM listede yok**;
  "There is no guarantee for the correctness of the data shown". Kaynak değil.
- FOREX.com, Trading.com vb. kendi oranlarını yayımlıyor — başka broker, bizim veri FXCM'nin.

## Sınıflandırma (21 çift)

| Sınıf | Çift | Dönem |
|---|---|---|
| Gerçek broker oranı (`tur=broker`) | **0** | — |
| Proxy, geçici (`tur=proxy`, merkez bankası politika faizi farkı, K-098/K-100) | **21** | çift başına aralık `config/finansman/fxcm-<pair>.json`; hepsinin ortak geçerli penceresi **2023-11-19..2024-03-18** (BoJ 2024-03-19'da değişti) |

Karışım yok: hiçbir çiftte broker verisi olmadığı için "bazı dönem broker, bazı dönem proxy"
durumu oluşmadı; oluşursa `tur` alanı çift × dönem düzeyinde ayrılır (K-098/5).

## Resmi takvimden doğrulanan/öğrenilen

- **Çarşamba 3 gün** — `FinansmanModeli.uclu_swap_gunu = 2` (K-095) resmi takvimle uyumlu.
- **Tatil kuralı** — FXCM: tatil günü 0, iki iş günü önce +1 (ör. 2026-09-03 Per 2, 2026-09-04 Cum
  0: ABD İşçi Bayramı). K-095 kapalı dönemde bedeli **atlamıyor** (aynı günde 1); haftalık toplam
  gün aynı, zamanlama ≤ 2 gün farklı. K-095 semantiği bu pakette **değiştirilmedi**; fark kayda
  alındı, resmi takvimi (yalnız cari çeyrek yayımlanıyor, tarihsel yok) motora bağlamak ayrı karar.
- **Birim** — platformda 1k lot başına para birimi; bizim model notional bps/gün (`uzun_gunluk_bps`).
  Dönüşüm (broker verisi gelirse): `bps = roll_para_birimi / (1000 × kur_quote→hesap) × 10⁴`.

## Bu paketle gelen mekanizma (K-101)

- `FinansmanKaynagi.aralik` biçimi zorunlu (`YYYY-MM-DD..YYYY-MM-DD`, bitiş hariç, UTC);
  `FinansmanModeli.gecerli_mi(ilk_ms, son_ms)`; `CokluBacktest.calistir` ölçüm penceresi aralığın
  dışına taşan sembolde **başlamaz** (`FinansmanHatasi`, K-101). Kaynaksız model hiçbir pencerede
  geçerli değil.
- Sonuç: K-100'ün 55 haftalık gerçek koşusu artık **reddediliyor** (21 çift aralık dışı); geçerli
  pencere `--baslangic 2023-11 --bitis 2024-02`: 1.721 bar, 36.048 üye bar, 315 fill, finansman
  7,14, `config_hash 7fc528c0…`, `sonuc_hash 4f1333bd…`; engel `gecici_finansman_modeli` duruyor.
