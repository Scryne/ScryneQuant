# Threshold Policy — Eşik Politikası

**Sürüm:** 0.1 (taslak, 2026-09-20, denetim döngüsü çıktısı) · **Durum:** `DECISION REQUIRED`
kalemleri Scryne'ın kararına kadar bağlayıcı değildir; ölçülmüş kalemler zaten koddadır.
**Kural (brief §14):** bu doküman **sayı uydurmaz**. Her satır ya repodaki mevcut değeri ve
kaynağını (ölçüm / iştah) taşır, ya da `DECISION REQUIRED` + aday aralık + gerekçe. Aday
aralıklar öneri niteliğindedir; "önerildi" ≠ "kabul edildi".

**Kaynak sınıfları (K-033 kalıbı):** `olculdu` (veriden, `veri_sha256` ile), `istah` (risk
iştahı, gözden geçirme koşuluyla), `null-kalibre` (null dağılımdan, çekiliş sayısına bağlı),
`politika` (metodolojik seçim), `DECISION REQUIRED`.

**Makine-okunurluk:** politika kabul edildiğinde her satır `config/esikler.json`'a
(`{ad, deger, kaynak, kapsam, gerekce, olcum_tarihi, veri_sha256, gozden_gecirme}`) taşınır ve
`research/kapilar*.py`, `risk/limitler.py`, `risk/promotion.py` sabitleri o dosyadan okur ya da
testle ona eşit tutulur (bugün `risk.json` ↔ `kapilar.py` için yapılan gibi). Bu bir R5 işi.

---

## 1. Evrensel mühendislik değişmezleri (asset/strateji bağımsız; eşik değil, **kural**)

Bunlar sayı değil, ihlali "görev yanlıştır" demek olan kurallar. Repo: `.claude/CLAUDE.md` 17 madde.

| # | Değişmez | Kaynak | Test |
| --- | --- | --- | --- |
| U1 | Strateji I/O yapamaz | K-003 | `test_izolasyon` (AST) |
| U2 | `ctx` t'de kesik; gelecek bozulunca sonuç değişmez | K-002 | `test_look_ahead` (negatif kontrollü) |
| U3 | Fill `t+1` açılış; slippage aleyhte; belirsizlikte kötü yöne | K-004, K-007 | `test_paper_dongu`, `test_backtest_referans` |
| U4 | Zaman UTC epoch ms; bar = açılış; bar olmayan gözlem `available_time`e göre | K-005, K-052/5 | `test_zaman`, `test_pit` |
| U5 | Onay yalnız risk motorundan; engelleyen katman dışarıda olabilir, izin veren olamaz | K-032, K-037 | `test_risk_bypass` |
| U6 | Aynı girdi → aynı çıktı; **kayıt yeniden üretilebilir** | K-009 | ilk yarı ✅, ikinci yarı **testsiz** (W6 T3) |
| U7 | Evren de geleceği göremez (PIT üyelik); kimlik ≠ ticker | K-052 | `test_evren`, `test_kimlik` |
| U8 | Kaç hipotez denendiği sayılır; kapı eşiği sayıya bağlı | K-039, K-044 | `test_hipotez`, `test_program`, bekçi (**zayıf**, W6 T2) |
| U9 | Toparlanma = yeniden üretim; uyuşmazlıkta durur | K-038 | `test_toparlanma` |
| U10 | Otomasyon asimetrik: izni artıran = kapı + elle onay | K-050 | `test_promotion`, `serbest_birak` statik |
| U11 | AI yetkisiz; LLM çıktısı backtest'te hesaplanmaz, dondurulur; kesim öncesi = `leak_riski` | K-049, K-074 | `test_jev_izolasyon`, `test_jev_durum` |
| U12 | Kendi hesabı, kendi parası | K-014 | — (hukuki sınır) |

**Çok varlıkta eklenmesi gereken (DECISION REQUIRED, kural düzeyinde):**

| # | Aday değişmez | Gerekçe |
| --- | --- | --- |
| U13 | Enstrüman = `(venue, instrument_type, sembol, geçerlilik)`; spot/vadeli/CFD/ETF/endeks verisi **karıştırılmaz** | Brief §15-16; bugün `Enstruman.venue` var, `instrument_type` yok (W1 §6) |
| U14 | Maliyet modeli enstrüman başına; global maliyet **reddedilir** | W3 R5 — tek global `MaliyetModeli` BTC'den kalibre |
| U15 | Takvim/seans enstrüman özelliği; "eksik bar" takvime göre tanımlanır | W1 §6 (24/7 ızgara varsayımı) |
| U16 | Veri seti kimliği = içerik hash **+ bitiş tarihi**; kayıt `veri_sonu` taşır | W3 R3 (K-080 taslağı) |
| U17 | Yeni evren/varlık sınıfı = yeni null dağılım = yeni `oos_sharpe` eşiği; eşik taşınmaz | W4 §4 |

## 2. Araştırma metodolojisi gereksinimleri (varlık bağımsız)

| Eşik | Mevcut değer | Kaynak | Durum / Öneri |
| --- | --- | --- | --- |
| OOS oranı | 0,30 (izin 0,10-0,50) | `bolme.py` politika | politika; **DECISION REQUIRED**: çok varlıkta sabit oran mı, sabit süre mi (FX'te 5/7 takvim → aynı oran farklı gün sayısı) |
| Walk-forward pencere | 1 yıl eğitim / 3 ay test (süre olarak, Dönüş 1) | politika | kabul edilebilir; **süre** cinsinden kalmalı (bar değil) — Faz 11 §5/1 dersi |
| Purge / embargo | **yok** | — | **DECISION REQUIRED.** Aday: embargo = tutma süresi p95 (BTC 1h'te ~24-48 bar); alternatif: sıfır ve "etki ihmal edilebilir" ölçümü. Gerekçe: IS sonu açık pozisyon OOS'a taşıyor (W3 R6) |
| Ölçülemeyen kapı = geçilmemiş | kural | K-019 | politika, değişmez |
| Ön kayıt zorunlu; program bütçesi | zorunlu; bütçe program başına | K-039, K-051 | politika, değişmez |
| Çoklu test düzeltmesi yöntemi | sızıntısız dairesel kaydırma, 500 deneme, seed 0, %5 yanlış-pozitif hedefi | K-044/064/071 | politika; `deneme=500` **DECISION REQUIRED** (GA genişliği 0,84-0,97 → yeterli mi?) |
| `oos_sharpe` (tek sembol + evren, Binance spot) | **1,04** | null-kalibre; **45 çekiliş** (K-081, 2026-09-20): %5 sınırı 1,004, GA 0,982–1,064, sabitin FP'si %4,2 — sabit **korundu** (politika kararı, GA sabiti kapsıyor) | Bekçi: `docs/research/coklu-test-olcum.json` + defter (CI'da); defter büyürse yeniden ölçüm zorunlu. Yeni evren için U17 |
| `oos_is_orani` ≥ 0,5 | 0,5 | politika (K-019) | kabul; gerekçesi "OOS IS'in yarısını korumalı" — ölçülmemiş |
| `wf_katman_basari` ≥ 0,6 | 0,6 | politika | kabul; **DECISION REQUIRED**: katman sayısına bağlı binom eşiği daha doğru (16 katmanda 0,6 = 10/16; 4 katmanda 3/4) |
| `parametre_kararliligi` ≤ 0,35 | 0,35 | politika | kabul; pertürbasyon v2 (0,0565) null-kalibre olduğu için bu v1 kapısı **gereksiz olabilir** — DECISION: birini emekliye ayır |
| `asgari_islem` ≥ 30 | 30 | politika | **DECISION REQUIRED**: timeframe'e göre sabit sayı adil değil (4h'te 18 işlem 5 yılda "az" mı?). Aday: yıl başına asgari işlem ya da "≥30 ∧ ≥N/yıl" |
| `max_drawdown` ≤ 0,25 | 0,25 | istah (K-019) | risk `drawdown_limiti` 0,20 ile testle bağlı; kabul |
| `stres_dayanikliligi` ≤ 0,15 | 0,15 | politika | kabul |
| `pbo` ≤ 0,0087 | 0,0087 | null-kalibre (Faz 11; 0,5 referansı geçersiz) | ızgara biçimine bağlı; yeni ızgara → `kalibrasyon_v2_kos.py` |
| `parametre_perturbasyonu` ≤ 0,0565 | 0,0565 | null-kalibre | aynı |
| `rejim_kararliligi` ≥ 0,685 | 0,685 | null-kalibre (30 gün pencere) | aynı; rejim tanımı varlık sınıfına göre yeniden (bkz. §3) |
| `evren_dayanikliligi` ≥ 0,75 | 0,75 | politika (K-054) | tek sembolde ölçülemez (doğru); çok varlıkta "kaç enstrümana bağlı" aynı soru |
| DSR / Bonferroni | rapor, kapı değil | K-044 | kabul |
| Kıyas ayarlanmaz | kural | K-072 | değişmez; her varlık sınıfı için **kıyas tanımı** DECISION (§3) |
| Deney kararı durumları | yok | — | **DECISION REQUIRED**: PASS/FAIL/INCONCLUSIVE/DATA_BLOCKED/INVALIDATED/RESEARCH_CANDIDATE defterde alan olsun (brief §19; W3 R7) |
| Deney sözleşmesi zorunlu alanlar | kısmi | — | brief §19 listesi; R5 |

## 3. Varlık sınıfına özgü gereksinimler

Bugün **yalnız kripto spot** için değer var. Diğer sütunlar tamamen `DECISION REQUIRED` — ve
çoğu karar **veri ölçülmeden verilemez** (K-021/K-033 kalıbı: önce dağılım, sonra persentil).

| Gereksinim | Kripto spot (Binance) | FX | Endeks (vadeli/CFD/ETF) | Emtia | Kaynak |
| --- | --- | --- | --- | --- | --- |
| Takvim | 24/7, bar = saat | 5/7, Pazar 22:00 UTC açılış, seans yok/rollover 17:00 NY | Borsa saatleri + vadeli uzatılmış seans; tatiller | Ürün başına | **DECISION**: takvim kaynağı (exchange_calendars? elle?) — R2 |
| Yıllıklandırma | 365,25 × 24 / tf | işlem saati/yıl ölçülmeli | aynı | aynı | U-not: `metrikler.py` sabit 365,25 → varlık takviminden |
| Komisyon | taker 10 bps/bacak (Spike 4) | spread içinde; komisyon broker'a bağlı | komisyon + borsa ücreti | aynı | **ölçüm** her venue için (Spike 4 kalıbı) |
| Slippage | 5,30 bps (BTCUSDT 1m p75, K-021) | **ölçülmeli** (tick verisi ya da 1m) | ölçülmeli | ölçülmeli | persentil politikası p75 (K-021 gerekçesi) — DECISION: aynı persentil mi |
| Spread | slippage içinde | **ayrı modellenmeli** (FX'te ana maliyet) | ayrı | ayrı | U14 |
| Finansman | yok (spot) / funding (perp, veri var, model yok — K-079) | swap/rollover günlük | CFD: gecelik finansman; vadeli: rollover | aynı | **DECISION + kod** (R2/R4) |
| Kaldıraç | 1,0 (spot) | broker marjı | marj | marj | K-079: vadeli hesap açılmıyor — kaldıraçlı ürün **karar konusu**, önce U12/K-014 ve compliance |
| Likidite / kapasite | ADV oranı (Faz 10) | ADV yok — spread/derinlik | hacim | hacim | ölçüm |
| Rejim tanımı | oynaklık pencereleri (Faz 11) | ? | ? | ? | DECISION: sınıf başına rejim değişkeni |
| Kıyas | `evren_esit_agirlik` / `al_tut` | ? (long USD? carry? sıfır?) | endeks al-tut | ? | **DECISION REQUIRED** — FX'te "al-tut" tanımsız |
| Hayatta kalma yanlılığı | ayda %16,7-18 (ölçüldü) | çift listesi stabil; broker kaldırabilir | endeks kompozisyonu değişir | kontrat serisi | ölçüm sınıf başına |
| Veri lisansı | Binance arşivi (açık) / FRED | **kaynak seçilmedi** | seçilmedi | seçilmedi | R3 + compliance |
| Enstrüman tipi ayrımı | spot ✓ | spot FX vs CFD | ETF ≠ vadeli ≠ endeks verisi | vadeli ≠ ETF | U13 |

## 4. Strateji ailesine özgü gereksinimler

| Aile | Mevcut durum | Ek gereksinim | Durum |
| --- | --- | --- | --- |
| Tek sembol yönlü TA (kesişim, RSI, Donchian, momentum, çok faktör) | **kapalı** (K-045, Binance spot BTC) | Başka varlıkta açılırsa: aynı 7+4 kapı; `asgari_islem` §2 kararı | yeni varlık = yeni çekiliş |
| Funding/basis (carry) | DATA_BLOCKED (K-079) | Perp fee katmanı + likidasyon modeli + iki bacak execution; max DD ≤ %25 tavan koşulu (Hat 1 tanımı) | dış koşul |
| Kesitsel (evren) | kapalı (kıyas altı) | `evren_dayanikliligi`, kıyas-üstü; **turnover ve kapasite** bağlayıcı (K-072 açık kalemi: `asgari_agirlik 0,005`, `hedef_brut 0,2`, `azami_agirlik 0,30` **ölçülmemiş varsayılan**) | **DECISION REQUIRED** (kurma parametreleri) |
| Kurma katmanı (1/σ, turnover bandı) | RESEARCH_CANDIDATE yönü (h51/h52) | Portföy düzeyi kapılar: korelasyon budaması, oynaklık hedefi (Hat 4) — **kapı tanımı yok** | R7 |
| Rejim/seçici | kapalı (K-077 tavan 0,60) | Yeniden açma: oracle tavanı ≥ eşik | ölçüm |
| Trend (uzun ufuk, çok varlık) | **test edilmedi** | Klasik trend için: tutma süresi aylar → `asgari_islem` 30 beş yılda karşılanmaz; embargo ≈ tutma süresi; walk-forward 1 yıl eğitim yetersiz olabilir | **DECISION REQUIRED** aile-özel kapı seti |
| Mikroyapı (1m-15m) | test edilmedi (1m veri var) | Slippage modeli 1m'de 5,3 bps **çok iyimser** (K-021 ölçümü 1m bar-to-bar); tick/derinlik gerekir | DECISION: aile açılmadan önce maliyet ölçümü |
| Olay-güdümlü | duyuru kaynağı elendi; haber yok | `available_time` kesmesi; kaynak lisansı | Faz 13 koşulu |
| Predictive ML | yok | K-049/3: yalnız kapıdan sonra; kesim/leak kuralı | değişmez |

## 5. Operasyonel dağıtım gereksinimleri

| Eşik | Mevcut | Kaynak | Durum / Öneri |
| --- | --- | --- | --- |
| `ASGARI_PAPER_GUN` | 30 | politika (K-010; K-069 dokunmadı) | **DECISION REQUIRED**: "≥30 gün ∧ ≥N fill" (N aile-özel; 0 fill'li 30 gün kanıt değil — `gozlem-2` 4,3 günde 0 fill) |
| Faz 14 dayanıklılık | ≥8 gün (K-069) | istah | kabul; ölçüm 25 Eylül |
| Shadow süresi / emir | 14 gün / 20 emir | istah (Faz-8-Hazirlik §6/2) | ilk shadow'da kalibre |
| Drift üst sınırı | kademe 1 ilk 30 gün `|d_i|` p95 | K-050/3 | ölçümle |
| Kademe artış | ×2 | istah | DECISION |
| Risk sermayesi | — | yalnız Scryne | DECISION |
| Bayat veri | 60 s (tek sembol `azami_veri_yasi`), 120 s (evren `bekleme_ms`) | politika | çok varlıkta seans kapanışı "bayat" değil → takvim-farkında tanım (U15) |
| `SON_BAR_GECIKTI` | ≥2 saat | politika | aynı |
| `DUSUS` alarm | %5 / %10 | politika | kabul |
| `SAPMA` | 50 bps | politika | kabul; Faz 8'de `|paper − live|` ile aynı ölçek |
| `KOPMA` | >5 / 24 s | politika | venue'ye göre |
| Risk limitleri (`risk.json`) | 10 kalem; 3 `olculdu` (BTC), 7 `istah` | K-033 | **evren-geneli / varlık-sınıfı kalibrasyonu** (W2 B3, K-073 pencere sonrası) — `volatilite_esigi` ve `ters_hareket_atr_carpani` **enstrüman başına** olmalı |
| `azami_brut_maruziyet` 1,0 / `azami_enstruman` 1000 | bağlamayan | istah | kaldıraçlı ürün açılırsa **bağlayıcı sayı** DECISION |
| Kill/SAFE_MODE kaldırma | elle + ≥10 karakter gerekçe | K-008/4 | kabul; **DECISION**: ikinci onay/tekrar bekleme süresi? |
| Promotion kaydı bütünlüğü | yok (W2 B4) | — | zincir hash — R1 |

## 6. Karar listesi (özet)

Scryne'ın vermesi gereken kararlar, önem sırasıyla. Hiçbiri bu dokümanda verilmedi.

1. **U13-U17** çok varlık değişmezleri (kural düzeyi; roadmap R2/R3'ün kabul kriteri).
2. Embargo politikası (§2).
3. `asgari_islem` ve `wf_katman_basari` timeframe/katman-farkında tanım (§2).
4. Deney karar durumları + sözleşme alanları defterde (§2).
5. Kurma parametreleri (`hedef_brut`, `azami_agirlik`, `asgari_agirlik`) ölçüm planı (§4).
6. `ASGARI_PAPER_GUN` fill koşulu (§5).
7. Varlık sınıfı başına: takvim kaynağı, kıyas tanımı, veri kaynağı/lisansı, kaldıraç (§3) —
   **ölçüm ve compliance'tan sonra**.
8. Kademe/sermaye/drift (§5) — tetik gelince.

Bu dokümanın kabulü = `config/esikler.json` + test (R5). Kabulden önce mevcut sabitler
yürürlükte kalır.
