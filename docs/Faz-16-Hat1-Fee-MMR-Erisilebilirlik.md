---
proje: ScryneQuant
faz: 16
tur: erişilebilirlik / doğrulanabilirlik raporu — minimum perp fee ve minimum C-isolated MMR girdileri
tarih: 2026-09-20
type: rapor
durum: fee DATA BLOCKED (K-066 kararı gerekli); MMR kısmen (likidasyon ücreti + formül metni doğrulandı; kademeler K-066 kararı gerekli)
---
# Hat 1 — Perp fee ve C-isolated MMR: minimum girdiler erişilebilir mi, doğrulanabilir mi?

Kapsam (Scryne kararı, 2026-09-20): **A** VIP 0 USDT-M taker fee, tarihli, resmî kaynak →
`fee_taker_bps_perp`; **B** C-isolated için tarihli MMR kademeleri, bakım tutarı, likidasyon
ücreti, resmî likidasyon formülü metni, kayıt tarihi + PIT sınırı. Açılmayan: maker, BNB,
tarihsel tarife, emir defteri, C-portfolio, NON_PIT MMR. Yapılmayan: varsayımsal değer,
spot→perp taşıma, imzalı uç, anahtar, K-066 açma, config/`src`, stres/likidasyon hesabı.

Deneme günü/saati: **2026-09-20 ≈ 07:00–07:10 UTC.** Erişim yolu: bu makine (IPv4),
`curl` (User-Agent tarayıcı) ve `WebFetch`.

## 1. Erişim denemeleri

| Kaynak | Yol | Sonuç |
| --- | --- | --- |
| `binance.com/en/fee/futureFee` (resmî ücret sayfası) | `curl` | **HTTP 202, 0 bayt** (bot koruması / JS) |
| aynı sayfa | `WebFetch` | içerik yok — "No records found", giriş ister |
| `binance.com/en/futures/trading-rules/perpetual/leverage-margin` (Leverage & Margin) | `curl` | **HTTP 202, 0 bayt** |
| FAQ 360033544231 "Futures Fee Structure & Fee Calculations" | `WebFetch` | gövde var; **rakam yok**, yalnız "assumed" örnek (0,02 % / 0,05 %) — **kullanılmadı**; BNB %10 indirim cümlesi |
| FAQ 98488a51… "What Fees are Generated…" (güncelleme 2026-01-05) | `WebFetch` | gövde var; **rakam yok**; "Insurance Clearance Fee" tanımı, oran Trading Rules sayfasına atıf |
| FAQ b3c689c1… "How to Calculate Liquidation Price of USDⓈ-M" (yayın 2020-06-11, güncelleme **2025-12-31**) | `WebFetch` | gövde var; **formül görsel**, değişken tanımları metin (WB, TMM₁, UPNL₁, cumB/L/S, Side₁, Position₁, EP₁, MMRB/L/S); "Maintenance Margin = Notional × MMR − Maintenance Amount" metin |
| FAQ 360033162192 "Leverage and Margin of USDⓈ-M" (güncelleme **2026-03-27**) | `WebFetch` | gövde var; kademe tablosu **görsel/yok**; "For the latest updates, please refer to the Leverage & Margin page"; "0,5 %'in altındaki bakım marjı ayarlamaları duyurusuz yapılabilir" |
| `GET /fapi/v1/exchangeInfo?symbol=BTCUSDT` (herkese açık) | `curl` | **HTTP 200, 1.123.073 bayt**, SHA-256 `926d6672eee3f19e…` (ham JSON scratchpad'de, repoya yazılmadı) |
| `GET /fapi/v1/leverageBracket` | `curl` (anahtarsız) | **401 −2014** — imzalı (dokümanda `USER_DATA`) |
| `GET /fapi/v1/commissionRate` | `curl` (anahtarsız) | **401 −2014** — imzalı (`USER_DATA`) |
| API dokümanı: Exchange Information | `WebFetch` | `maintMarginPercent`, `requiredMarginPercent` → **"ignore"**; `liquidationFee` → "liquidation fee rate" |
| API dokümanı: Notional and Leverage Brackets | `WebFetch` | `USER_DATA`; alanlar: `bracket, initialLeverage, notionalCap, notionalFloor, maintMarginRatio, cum` ("Auxiliary number for quick calculation" = bakım tutarı) |

## 2. A — Perp taker fee: **DATA BLOCKED, K-066 kararı gerçekten gerekli**

| Gereken | Erişilebilir mi | Doğrulanabilir mi |
| --- | --- | --- |
| VIP 0 USDT-M taker fee, tarihli, resmî | **hayır** — tek resmî sayısal kaynak (fee sayfası) JS/bot korumalı; FAQ'lar yöntem anlatıyor, oran vermiyor; blog/square yazıları resmî tarife değil, kullanılmadı | — |
| İmzalı `commissionRate` | hesaba özgü, **kesin** (o hesabın gerçek oranı) | evet (imzalı yanıt + hash) — ama vadeli yetkili anahtar ister |

**Bulgu:** metodoloji denetiminin "minimum bilgi" tanımı (tek tarihli, doğrulanabilir taker
oranı) bu ortamda **anahtarsız karşılanamıyor**. Dolayısıyla K-066 bir "belki" değil,
`c_perp`'in tek yolu: **vadeli, salt okunur, yalnız `commissionRate` (ve isteniyorsa
`leverageBracket`) için** bir anahtar — işlem/çekim yetkisi olmadan. Bu kararı ben
vermiyorum; gerekçe budur. Karar gelene kadar: `c_perp` DATA BLOCKED; ara ölçümler
`r_gross_ust_sinir_fee0` ve `basabas_fee_perp_bps` tanımlı (metodoloji denetimi §1),
**hesaplanmadı** (bu rapor erişilebilirlik raporu), hesaplanırsa "ARA — kapı dışı,
`gecici_maliyet_modeli`" etiketiyle.

## 3. B — C-isolated MMR minimum seti: **kısmen erişilebilir**

| Girdi | Kaynak | Erişilebilir | Doğrulanabilir | Durum |
| --- | --- | --- | --- | --- |
| Likidasyon ücreti (BTC/ETH) | `exchangeInfo.symbols[].liquidationFee` | **evet, anahtarsız** — BTCUSDT `0.012500`, ETHUSDT `0.012500` (2026-09-20 07:07 UTC, JSON SHA `926d6672…`) | evet (ham JSON hash'li; yeniden çekilebilir) | **PIT kaydı yapılabilir** — kayıt tarihi 2026-09-20; öncesi bilinmiyor |
| Resmî likidasyon formülü metni | FAQ b3c689c1… (güncelleme 2025-12-31) | evet — formül **görsel**, değişken tanımları ve "Notional × MMR − Maintenance Amount" cümlesi metin | kısmen — görsel formülün metne dökümü insan aktarımı ister; sayfa hash'lenemedi (`curl` 202) | **kaydedilebilir**, "görselden aktarıldı" notuyla |
| MMR kademeleri + bakım tutarı (`maintMarginRatio`, `cum`) | `leverageBracket` (`USER_DATA`) **veya** Leverage & Margin sayfası | **hayır** anahtarsız — uç imzalı; sayfa 202/JS; FAQ'daki tablo görsel/yok | imzalı yanıt hash'lenebilir | **DATA BLOCKED, K-066 kararı gerekli** |
| `exchangeInfo.maintMarginPercent` (2,5 %) / `requiredMarginPercent` (5 %) | herkese açık | evet | **resmî dokümanda "ignore"** | **kullanılmaz** — kademe yerine geçmez |
| Kayıt tarihi + PIT sınırı | — | — | — | kademe kaydedildiği gün = PIT sınırı; bugün **PIT MMR EMPTY, NON_PIT MMR EMPTY** (değişmedi) |
| Otomatik marjin ekleme, ADL | — | — | — | gereksiz / kapsam dışı (metodoloji denetimi) |

**Bulgu:** likidasyon ücreti ve formül metni anahtarsız, tarihli ve (ücret için) hash'li
elde edilebilir; **kademe tablosu edilemez**. C-isolated sayacının eşiği kademe tablosudur;
dolayısıyla sayaç hâlâ **kapalı** ve MMR için de aynı K-066 kararı belirleyici. Kademe
tablosu gelmeden likidasyon ücreti tek başına hiçbir ölçüm açmaz (ücret, likidasyon
**olayının** maliyetidir; olay sayısı yok).

## 4. Stres sınıfları envanteri — mevcut veriyle tanımlı olanlar (hesaplanmadı)

Metodoloji denetimi asimetrisi: **MMR eksikliği tüm stres ölçümlerini değil, MMR'ye bağımlı
likidasyon-eşiği sınıfını bloke eder.**

| Sınıf (tasarım §8) | Girdi | Mevcut veriyle tanımlı mı | Eksik |
| --- | --- | --- | --- |
| Funding uzun süre negatif | A-1 koşu dağılımı (sembol × yıl), funding serisi | **evet** — gerçek koşular; `k` ızgarası duyarlılık | — |
| Basis aleyhte hareket | A-3 w-gün dağılımı; mark ile yeniden hesap mümkün | **evet** | — |
| Yüksek volatilite | A-4 (ATR/close, `config/risk.json` eşikleri) | **evet** (eşik BTC kalibreli, açık) | — |
| Execution maliyeti yükselmesi | `STRES_SENARYOLARI` × (spot fee ✓, spot slip ✓, perp slip ✓, **perp fee ✗**) | **kısmen** — `slippage_2x/3x` tanımlı; `fee_2x`, `hepsi_2x` perp fee'siz eksik | perp fee (A) |
| Borsa parametre değişikliği | A-2 taban ayrıştırması ("taban 0"), ödeme aralığı 8h→4h | **evet** | — |
| Erişim kaybı / karşı taraf | `D`, `x` ızgarası — tarihsel kaynak yok | **duyarlılık olarak tanımlı**, parametre kaynağı yok | ölçülemez (bilinen) |
| Likidasyon eşiğine yaklaşma (`C-isolated`) | mark ✓, `L` ızgarası ✓, funding→marjin ✓, **MMR kademeleri ✗**, likidasyon ücreti ✓ (bugün), formül ✓ (metin) | **hayır** — eşik yok | MMR kademeleri (K-066) |
| `C-portfolio` | + haircut, uygunluk | hayır | backlog (açılmadı) |

Yedi sınıfın **beşi** bugün tam tanımlı, biri kısmen (execution: fee), biri kapalı
(likidasyon: MMR). Hiçbiri hesaplanmadı; `stres_bozulma` üretilmedi; kapı kararı yok.

## 5. Sonuç

- **Fee:** resmî sayısal kaynak anahtarsız erişilemez → `c_perp` DATA BLOCKED sürüyor;
  **K-066 gerçek karar konusu** (vadeli, salt okunur, `commissionRate` — işlem yetkisi yok).
- **MMR (C-isolated):** likidasyon ücreti (PIT kaydı yapılabilir) ve formül metni erişilebilir;
  **kademe tablosu değil** → sayaç kapalı; aynı K-066 kararı (`leverageBracket`, salt okunur).
- **PIT / NON_PIT:** ikisi de EMPTY; NON_PIT açılmadı; bugünkü hiçbir değer IS'e uygulanmadı.
- **Ara ölçümler** (`r_gross_ust_sinir_fee0`, `basabas_fee_perp_bps`, MMR alt sınır/başabaş):
  tanımlı, hesaplanmadı, kapı dışı.
- Değişiklik: yok (`src/`, config, execution, K kayıtları, veri deposu; ham `exchangeInfo`
  scratchpad'de, repoya alınmadı).

Karar Scryne'ın: K-066 kapsamında vadeli salt-okunur anahtar açılsın mı (iki uç birden:
`commissionRate` + `leverageBracket`)? Açılmazsa fee ve MMR bloke kalır; stres tavanı
"eksik sınıf" ile raporlanabilir (tasarım §9: (2) ve (4) yine raporlanır, karar "eksik
katman" ile verilir).
