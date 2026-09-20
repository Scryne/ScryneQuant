# W4 — Alpha Baseline (Mevcut Alfa Durumu)

**Tarih:** 2026-09-20 · **Baseline:** `1e1a05b` · **Kod değişikliği:** yok
**Kaynaklar:** `docs/Hipotez-Defteri.jsonl` (52 kayıt, doğrudan okundu), Faz 4 raporu + 5 dönüş,
Faz 11 §4, Faz 12 (×3 program raporu), Faz 16 (konumlanma, kurma, kıyas, rejim tavanı, duyuru,
M-1, Hat 1, Hat 2), `Alpha-Discovery-Gap-Audit.md`, K-042/044/045/068/071/072/076/077/078/079,
`runs/faz12/coklu-test-birlesik-500-0.json`. Sayılar raporlardan **kopyalandı**, yeniden
hesaplanmadı; W3 §6'daki tekrar üretilebilirlik bulgusu bu sayıların "bugün yeniden üretilemez"
olduğunu söylüyor — raporun kendisi kanıt, koşu değil.

Karar durumları brief §19: **PASS / FAIL / INCONCLUSIVE / DATA_BLOCKED / INVALIDATED /
RESEARCH_CANDIDATE**. Ek etiket **BENCHMARK** (çekiliş değil, kıyas) ve **MEASUREMENT** (çekiliş
sayılmayan tavan/ölçüm).

---

## 0. Özet

- **52 ön kayıtlı çekiliş, 0 PASS.** 38 tek sembol (BTCUSDT), 14 evren (Binance spot altcoin).
- Tek sembol yönlü TA: **maliyet sıfırken bile** kapı geçilmedi (K-045) → aile **kapalı**.
- Evren: seçim katmanı (kesitsel, dışlama) kıyası geçemedi; **kurma katmanı** (h51/h52) kıyası
  geçti ve 11 kapının 6-7'sini aldı ama `oos_sharpe` 0,36 vs eşik 1,04.
- Çekiliş sayılmayan altı ölçüm (tavan, rejim oracle, duyuru, NY saati, Hat 1, Hat 2) araştırma
  uzayının hangi köşelerinin **kapalı**, hangisinin **DATA_BLOCKED** olduğunu söylüyor.
- Bütün kanıt **Binance spot, long-only, 1h/4h/1d, fiyat+funding+makro+konumlanma**. Brief §15
  evreninin hiçbir kısmı test edilmedi (FX/endeks/emtia/ETH-SOL tek sembol/short/perp).

## 1. Çekiliş bazlı tablo (52)

Kısaltmalar: OOS = out-of-sample Sharpe; K = geçen kapı / toplam (v1 7 kapı; Faz 11+ 11 kapı);
kıyas = `al_tut` (tek sembol) ya da `evren_esit_agirlik` (evren). Eşik `oos_sharpe`: Faz 4'te
0,50 (K-019), K-044 sonrası 1,02, K-064/071 sonrası **1,04**.

### 1.1 Tek sembol BTCUSDT, 1h, tepe seçimi (h01-h07) — Faz 4

| h | Strateji | IS | OOS | K | Karar | Not |
| --- | --- | ---: | ---: | --- | --- | --- |
| 01 | al_tut | 0,70 | −0,39 | — | BENCHMARK | |
| 02 | sma_kesisim | +0,62 | **−1,03** | ✗ | FAIL | 70 işlem |
| 03 | ema_kesisim | +0,65 | −0,46 | ✗ | FAIL | |
| 04 | rsi_donus | +0,45 | −0,85 | ✗ | FAIL | |
| 05 | donchian | +0,75 | −0,35 | ✗ | FAIL | WF bileşik +0,61 (10/16 katman) — en dayanıklı |
| 06 | momentum | +0,91 | −0,08 | ✗ | FAIL | |
| 07 | cok_faktor | +0,23 | −0,95 | ✗ | FAIL | |

Geriye dönük kayıt (defterden önce); ön kayıt kanıtı değil, sayıma dahil. Altı ailenin altısı
OOS'ta negatif; IS→OOS bozulma 8,8-25,5 puan.

### 1.2 Timeframe dönüşü: 4h/1d, tepe (h08-h21) — Dönüş 1

| h | Strateji | tf | OOS | K | Karar | Not |
| --- | --- | --- | ---: | --- | --- | --- |
| 08 | sma_kesisim | 4h | **+0,39** | ✗ | FAIL | 18 işlem < asgari; kıyas −0,33 iken pozitif |
| 09 | ema_kesisim | 4h | +0,32 | ✗ | FAIL | 14 işlem |
| 10 | donchian | 4h | −0,33 | ✗ | FAIL | |
| 11 | momentum | 4h | −0,18 | ✗ | FAIL | |
| 12 | al_tut | 4h | −0,33 | — | BENCHMARK | |
| 13-16 | sma/ema/donchian/momentum | 1d | — | ✗ | FAIL/INCONCLUSIVE | 1d'de geçerli aday üretmeyenler var (Faz 11: sma/ema 1d ölçülemez) |
| 17 | al_tut | 1d | — | — | BENCHMARK | |
| 18-21 | rsi_donus, cok_faktor | 4h/1d | 4h: −0,45 / +0,17 | ✗ | FAIL | geriye dönük kayıt |

Ders (rapor): timeframe büyütmek OOS'u pozitife çevirdi ama işlem sayısını kapının altına
düşürdü — "mekanizma kendi ayağına bastı". Aile çürütüldü, eşik oynatılmadı.

### 1.3 Seçim dönüşü: plato (h22-h35) — Dönüş 2

| h | Strateji | tf | OOS/IS (tepe→plato) | Karar |
| --- | --- | --- | --- | --- |
| 22-28 | 6 aile + al_tut | 1h | 4 aynı nokta, 2 kötüleşti (ema −0,70→−1,20; momentum −0,09→−0,45), cok_faktor −4,15→−58,6 (artefakt) | FAIL |
| 29-35 | 6 aile + al_tut | 4h | 3 aynı, 2 kötüleşti (rsi, momentum), **cok_faktor 0,15→0,42 iyileşti** | FAIL |

Ders: plato seçimi tepeden sistematik olarak daha iyi değil; seçim yöntemi çürütüldü.

### 1.4 Funding aileleri (h36-h38) — Dönüş 3, K-042

| h | Strateji | OOS | OOS/IS | WF | İşlem | Karar | Not |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| 36 | funding_ters | −0,27 | −0,19 | 0,63 ✓ | 60 | FAIL | stres ✗ |
| 37 | funding_filtre | −0,09 | −0,11 | 0,44 | 56 | FAIL | |
| 38 | funding_egilim | **+0,29** | +0,20 | **0,75 ✓** | **24 ✗** | FAIL | Faz 4'ten beri ilk pozitif OOS; asgari işlem kapısında kaldı; ızgara genişletme bilerek reddedildi (eşiğe dokunmadan kural delme) |

### 1.5 Evren programları (h39-h52) — Faz 12/16, 11 kapı, eşik 1,04

| h | Program | Çekiliş | IS | OOS | Kıyas OOS | K | Karar |
| --- | --- | --- | ---: | ---: | ---: | --- | --- |
| 39 | kesitsel_fiyat | güç haftalık p=336 n=5 | 0,88 | **−0,51** | 0,17 | 2/11 | FAIL |
| 40 | kesitsel_fiyat | güç aylık p=168 n=20 | 0,66 | −0,18 | 0,28 | 4/11 | FAIL |
| 41 | kesitsel_fiyat | ters haftalık | 0,26 | −0,92 | 0,17 | 3/11 | FAIL |
| 42 | kesitsel_fiyat | ters aylık | 0,41 | −0,97 | 0,28 | 3/11 | FAIL — durma kuralı, 2/6 bütçe iade |
| 43 | turev_evren | son funding dışlama q=0,3 | 0,44 | 0,18 | 0,33 | 5/11 | FAIL (kıyas altı) |
| 44 | turev_evren | 720s funding birikimi | 0,35 | 0,22 | 0,17 | 5/11 | FAIL |
| 45 | turev_evren | basis ortalaması | 0,37 | 0,13 | 0,17 | 5/11 | FAIL |
| 46 | turev_evren | funding+basis sıra ort. | 0,39 | **0,26** | 0,17 | 6/11 | FAIL |
| 47 | makro_rejim | VIX 30g eşik 0,7 | 0,49 | 0,17 | 0,17 | 4/11 | FAIL (=kıyas) |
| 48 | makro_rejim | NFCI 365g | 0,58 | 0,22 | 0,17 | 4/11 | FAIL — 3. çekiliş harcanmadı |
| 49 | konumlanma_evren | OI birikimi | 0,30 | 0,09 | 0,17 | 5/11 | FAIL (kıyas altı) → **K-068 aile kapandı** |
| 50 | konumlanma_evren | taker baskısı | 0,32 | 0,06 | 0,17 | 4/11 | FAIL |
| 51 | kurma_evren | 1/σ ağırlık ×10 n=10 | 0,65 | **0,36** | 0,17 | **6/11** | FAIL — kıyası 2×, MaxDD %13,8 vs %20; Sharpe kapısına 3× uzak |
| 52 | kurma_evren | turnover bandı 0,02 n=5 | 0,43 | 0,28 | 0,33 | **7/11** | FAIL — kıyas altı ama genelleşme kapılarını geçti |

Kıyas (`evren_esit_agirlik`, n=10): OOS 0,167, MaxDD %20,0, ayarlanmaz (K-072).

## 2. Çekiliş sayılmayan ölçümler (K-045 kalıbı: strateji koşulmaz ya da tavan)

| Ölçüm | Ne soruldu | Sonuç | Durum | Kaynak |
| --- | --- | --- | --- | --- |
| Maliyet-sıfır tavan | Komisyon+slippage 0 olsa kapı geçilir mi? | Hayır: en iyi ema 4h 0,69 (19 işlem), momentum −0,92 | **INVALIDATED (aile)** — maliyet bağlayıcı kısıt değil | Dönüş 5, K-045 |
| Rejim×aile oracle tavanı | Her rejimde kusursuz aile seçici olsa? | tavan 0,60 < 1,04 | **INVALIDATED** — selector/filter için headroom yok; Jev B/C/D/E açılmaz | Faz-16-Rejim-Tavan, K-077 |
| Duyuru kaynağı (Binance listeleme/delist) | Duyuru sonrası getiri işlem yapılabilir mi? | Etki gerçek ama evren dışı küçük sembollerde ve **aşağı** yönde; seçim yanlılığı kontrolü +%7,9 → −%8,6 | **FAIL (program açılmadı)** | Faz-16-Duyuru-Kaynak-Olcumu |
| M-1 NY saati çapası | 13:00 ET süpürme-dönüş yapısı var mı? | p=0,385 | **FAIL** — Lunch ailesi çekiliş harcanmadan kapandı | Faz-16-M1-NY-Saati |
| Hat 2: funding uzlaşma anı mikroyapısı | ±60 dk pencerede koşullu getiri | net −29,7 bps, 32 plasebo p=0,156 | **FAIL (CLOSE)** | Hat2 raporu, K-078 |
| Hat 1: delta-nötr carry ideal tavanı | spot long + perp short, yalnız funding+basis, maliyet 0 | BTC +%14,2/yıl Sharpe 9,5; havuz(28) +%13,8 / 6,6 | **RESEARCH_CANDIDATE → DATA_BLOCKED** (K-079: perp fee katmanı + liquidation threshold eksik; vadeli hesap açılmıyor — Scryne kararı) | Hat1 raporları, K-078/079 |
| Jev yön ekseni | Jev'in yön yargısı bilgi kaynağı mı? | 50 sembol × 197 bar, isabet %49,0, net −%0,38/işlem | **FAIL** — kapalı | K-076, Jev-Golge-Raporu |
| Jev evren replay | Jev seçim/filtre olarak? | oracle tavanı altında | **FAIL** | Faz-16-Jev-Evren-Replay, K-077 |
| Evren dayanıklılığı (yapısal) | Sonuç kaç enstrümana bağlı? | tek sembol çekilişleri 38/38 ölçülemez | **INVALIDATED (tek sembol → evren kapısı)** | Faz 11 §4 |

## 3. Ne test edildi / ne edilmedi

### Test edildi (kanıtlı)
- BTCUSDT spot, 1h/4h/1d, long-only: kesişim (SMA/EMA), ortalama dönüş (RSI), kırılım
  (Donchian), momentum, çok faktör; tepe ve plato seçimi; funding filtre/eğilim/ters.
- Binance spot altcoin evreni (PIT, 109 ay, ~323-734 sembol): kesitsel momentum/ters
  (haftalık/aylık), funding/basis dışlama, VIX/NFCI stres engeli, OI/taker dışlama, 1/σ kurma,
  turnover bandı.
- Ölçümler: maliyet tavanı, rejim oracle, duyuru, NY saati, funding uzlaşma anı, carry tavanı,
  Jev yön/seçim.

### Test edilmedi (kanıt yok — "başarısız" değil, "bilinmiyor")
| Eksen | Neden yok | Brief §15/18 karşılığı |
| --- | --- | --- |
| **Short / perp eylem uzayı** | Final-Doküman v1 spot kaldıraçsız; K-079 vadeli hesap açılmıyor | Hat 3 önerisi; §18 #11 funding/basis |
| **ETH, SOL tek sembol yönlü** | tek sembol araması BTC'de kapandı (K-045), başka sembole taşınmadı | §15 Crypto |
| **FX, endeks, emtia, ETF** | veri kaynağı/adaptör yok (W1 §6) | §15 tamamı |
| **Makro/cross-asset özellik** (DXY, VIX, faiz) | VIX/NFCI yalnız evren engeli olarak; cross-asset ilişki yok | §18 #9, #15 |
| **Trend following (uzun ufuk, ATR-stop)** | Donchian/momentum 1h-1d yönlü sınandı; klasik çok-varlık trend (aylar) sınanmadı | §18 #1 |
| **Volatilite stratejileri** (vol hedefleme dışında) | h51 1/σ kurma sınandı; vol-breakout/vol-risk-premium yok | §18 #5 |
| **Relative value / pairs / cross-asset** | yok | §18 #8, #9 |
| **Hacim/akış mikroyapı** (1m-15m) | 1m veri var (3 yıl), yalnız slippage kalibrasyonunda kullanıldı | §18 #12, #13 |
| **Olay-güdümlü (haber/on-chain)** | Faz 13 koşullu, veri kararı yok; duyuru kaynağı elendi | §18 #14 |
| **Predictive ML** | K-049: yalnız kapıdan sonra | — |
| **Portföy (çok strateji/çok varlık)** | tek geçen aday yok → portföy aşaması hiç açılmadı | §21 |

## 4. Geçerlilik kapsamı

| İddia | Geçerli olduğu yer | Genelleşir mi | Not |
| --- | --- | --- | --- |
| "Klasik TA tek sembolde OOS'ta çöküyor" | BTCUSDT 2021-05→2026-09, 1h/4h/1d | **Hayır** (tek enstrüman, tek rejim dizisi) | Literatürle uyumlu ama bu repo yalnız BTC'yi ölçtü |
| "Maliyet bağlayıcı değil" | aynı | Hayır — illikit varlıkta maliyet bağlayıcı olabilir | tek global maliyet (W3 R5) |
| "Kıyas-üstü tek dışlama katmanı işe yaramıyor" (K-068) | Binance spot evreni, 6 dışlama | Yöntemsel olarak taşınabilir hipotez, sonuç değil | |
| "Kurma katmanı seçim katmanından daha çok geçiyor" | h51/h52 | RESEARCH_CANDIDATE yönü; başka evrende yeniden çekiliş ister | K-072 açık kalemi: OOS yoğunluk yapısı açıklanmadı |
| "Carry tavanı yüksek" | BTC/havuz perp, maliyet 0, likidasyon yok | Hayır; ideal tavan | DATA_BLOCKED |
| "Jev yön bilgisi yok" | Jev modeli, kripto, yayın sonrası pencere | Jev için evet, varlık için ilgisiz | K-076 |
| "0/52 → kapı çalışıyor" | doğru okuma | evet | README bunu böyle yazıyor ✓ |
| Eşik 1,04 | **bu deftere** (43 çekiliş) bağlı | Hayır — yeni evren/program yeni null ister | W3 R2 bayat |

## 5. Kanıt kalitesi notları

- **Tekrar üretim:** hiçbir çekiliş bugünkü depo/kodla yeniden üretilemiyor (W3 §6). Sayılar
  raporlardan; rapor ile koşu arasındaki bağ `sonuc_hash` ve o hash'ler bugün doğrulanamaz.
- **Risk motoru:** araştırma çekilişleri risk motorsuz (K-073). Sonuç "0/52" bundan etkilenmez
  (risk motoru yalnız eler), ama "h51 6/11" gibi ara sonuçlar risk motorlu koşuda değişebilir.
- **Ön kayıt:** h01-h07 ve h18-h21 geriye dönük (11/52); kayıt bunu açıkça söylüyor.
- **Maliyet:** evren çekilişlerinde altcoinlere BTC slippage'ı; kıyasa görelilik korunuyor,
  mutlak Sharpe iyimser olabilir.
- **Rejim:** tek dönem (2021-05 → 2026-09; 1h veri 5,2 yıl). Rejim kapısı OOS içinde 30
  günlük pencerelerle; çok yıllık rejim çeşitliliği (2018 ayı, 2020 mart) 1h veride **yok**
  (1m/1h 2021'den; 1d ise 1936 bar).

## 6. Roadmap'e giden cümleler

1. Mevcut eylem uzayında (Binance spot long-only, fiyat/funding/makro/konumlanma) araştırma
   **kapalı** (K-078). Yeniden açılma koşulu belirgin biçimde farklı bilgi kaynağı ya da eylem
   uzayı.
2. Açık iki eksen (short/perp; ikinci varlık sınıfı/veri sınıfı) **araştırma değil karar**
   konusu: veri/hesap/lisans kararı verilmeden çekiliş yapılamaz.
3. Tek RESEARCH_CANDIDATE (Hat 1 carry) DATA_BLOCKED; tek olumlu yönlü sinyal (kurma katmanı
   h51/h52) kıyası geçiyor ama Sharpe kapısına uzak — **portföy kurma araştırması** (brief
   §21) çok varlıklı evrende doğal devam noktası.
4. Yeni evren = yeni null = yeni eşik; 1,04 taşınmaz.
5. Brief §15 evreninin tamamı **UNKNOWN**; ilk iş alfa değil, o evren için veri + registry +
   maliyet modeli (W1 §6, W3 R5).

**Sonraki dalga:** W5 — Jev.
