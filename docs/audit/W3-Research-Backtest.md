# W3 — Research / Backtest Audit

**Tarih:** 2026-09-20 · **Baseline:** `1e1a05b` · **Kod değişikliği:** yok. Bu dalgada üç
komut koşuldu (hepsi salt okunur araştırma araçları): `sq lab dogrula` 18 kayıt üzerinde;
`sha256sum` depo dosyaları; defter/JSON okuma.
**Okunan:** `strategy/baglam`, `research/{bolme,kapilar,kapilar_v2,coklu_test*,pbo,dsr,
hipotez,program,tekrar}`, `backtest/{fill,metrikler,sonuc,coklu_motor}`, `common/maliyet`,
`tests/unit/test_look_ahead.py`, `docs/Hipotez-Defteri.jsonl` (52), `runs/faz12/coklu-test-*`,
`runs/deneyler/*`, Faz 4/10/11 raporları, K-044/057/064/071/073/079.

---

## 0. Özet

Metodoloji **güçlü** (look-ahead negatif kontrollü test, t+1 fill, PIT evren, ön kayıtlı defter,
çoklu test null dağılımı, PBO/DSR, null-kalibre v2 kapıları). **Tekrar üretilebilirlik bugün
kırık**: kayıtlı 16 tekrar-edilebilir deneyin **0'ı** bugünkü depo/kodla yeniden üretilebiliyor,
eşik yeniden ölçümü aynı sebeple durdu. Kapılar 52 çekilişin tamamını eledi; bu sonuç **risk
motorsuz** backtest'lerden geldi (B2) ve maliyet modeli tek sembolden kalibre (A3).

| # | Bulgu | Sınıf |
| --- | --- | --- |
| R1 | Kayıtlı deneylerin **0/16**'sı yeniden üretilebiliyor: 1h kayıtları depo uzatıldığı için (`veri seti değişmiş`), 4h/1d kayıtları `sonuc_hash` algoritması değiştiği için (K-057/6, bilinen, "Faz 11'de yenilenecek" denmiş, **yenilenmemiş**) | **RISK** (K-009 iddiası bugün kanıtlanamıyor) |
| R2 | Eşik yeniden ölçümü (45 çekiliş) `h51` kaydının OOS `sonuc_hash`'ini üretemediği için **durdu** (`runs/faz12/coklu-test-500-45.err.log`); `COKLU_TEST_CEKILIS_SAYISI=43` bayat | **RISK** |
| R3 | Veri seti kimliği "içerik + son bar": depoyu uzatmak geçmiş kayıtları geçersiz kılıyor; REST deposu (`data/market`) geri sarılamaz (`--yil 5.2` şimdiye göreli), arşiv deposu K-080 taslağıyla sarılabilir | **RISK** (yapısal) |
| R4 | Araştırma backtest'leri `risk=None` (K-073); 52 çekilişin kapı sonuçları risk katmanı olmadan | PARTIAL |
| R5 | Tek global maliyet: `fee 10 bps + slippage 5,30 bps` (BTCUSDT 1m p75), 323 sembollü evrene aynı; spread ayrı modellenmiyor | PARTIAL |
| R6 | Walk-forward'da **purge/embargo yok**: test penceresi eğitim bitişinde hemen başlıyor; medyan tutma 27 saat | PARTIAL |
| R7 | Hipotez defteri **ön kayıt** taşıyor, **sonuç/karar** taşımıyor (brief §19 sözleşmesinin yarısı); sonuçlar `runs/` (git dışı) ve faz raporlarında | PARTIAL |

## 1. Look-ahead / sızıntı / zaman hizası — VERIFIED

| Kontrol | Kanıt |
| --- | --- |
| `ctx` `i`'de kesik; negatif `geri` hata; diziler salt okunur; seri kopya döner | `strategy/baglam.py:140-275`, `test_look_ahead.py::TestErisimSozlesmesi` |
| Gelecek bozulunca sinyaller **bit düzeyinde** aynı, her kesme noktasında; hemen sonraki bar dahil | `TestBozulmusGelecek` (3 bozma × t) |
| **Negatif kontrol:** hile yapan strateji en az bir bozmayla yakalanıyor; rastgele bozma tek başına yetersiz | `TestNegatifKontrol` — testin testi var |
| Funding look-ahead: gelecek funding bozulunca aynı | `TestFundingLookAhead` |
| Evren look-ahead (hayatta kalma): PIT üyelik, `available_time` kesmesi | Faz 10 §4, `test_evren.py`, `test_pit.py`; Spike 6 ölçümü ayda medyan %18 (Faz 9 yeniden: %16,7) |
| Jev durumu byte-identical sızıntı testi | `test_jev_durum.py` (CI'da adıyla) |
| Bar = açılış zamanı, UTC ms; fill `t+1` açılış; slippage aleyhte | `common/zaman.py`, `backtest/fill.py:125-137` |
| Makro: ALFRED vintage (revizyon yok); bilinmeyen `available_time` gün sonuna | `data/makro.py`, `data/pit.py` (K-052/5) |

## 2. Train/test, walk-forward, seçim

| Kontrol | Durum | Kanıt |
| --- | --- | --- |
| IS/OOS kronolojik, OOS oranı sınırlı aralıkta, ısınma ayrı | VERIFIED | `research/bolme.py:105-132` |
| Walk-forward rolling/anchored; katman örtüşmesi hata | VERIFIED | `bolme.py:85-100,134-196` |
| **Purge/embargo** | **YOK** | Test `egitim_bitis`te başlıyor; IS sonunda açık pozisyon/etiket OOS'a taşar. Etki 1h'de küçük (tutma ~24 bar / test penceresi binlerce bar) ama sıfır değil → Threshold-Policy `DECISION REQUIRED` (embargo = tutma süresi p95?) |
| Seçim ölçütü kayıtlı (`secim: tepe|plato`), pertürbasyon testi | VERIFIED | `research/tarama.py`, `perturbasyon.py`; defterde 52 kayıtta `secim` alanı |
| Parametre ızgarası defterde | VERIFIED | `izgara` alanı her kayıtta |
| Gizli tekrar (aynı fikrin yeni adla) | PARTIAL | `research/gizli_tekrar.py` Jev'le benzerlik uyarısı (K-061); engellemez |

## 3. Çoklu test, kapılar, eşikler

| Kontrol | Durum | Kanıt |
| --- | --- | --- |
| Çekiliş sayısı ön kayıtla sayılıyor; program başına bütçe; bütçe dolunca red | VERIFIED | `research/hipotez.py`, `program.py`; 52 kayıt / 10 program kaydı |
| Null dağılımı: sızıntısız kaydırma, 500 deneme, seed 0 | VERIFIED (kod+kayıt) | `coklu_test.py`, `coklu_test_evren.py`; `runs/faz12/coklu-test-birlesik-500-0.json` (2026-09-18, 43 ölçülebilir, %5 sınırı 0,926 ± GA 0,838-0,967) |
| `oos_sharpe` kapısı 1,04 (43 çekiliş; gerçek yanlış-pozitif %2,6, bilerek gevşetilmedi) | VERIFIED — **bayat** | `kapilar.py:70-76`; bugün 45 ölçülebilir, yeniden ölçüm **R2** ile durdu |
| DSR ve Bonferroni çapraz kontrol (0,92 / 1,30) | VERIFIED | `kapilar.py` gerekçe, `research/dsr.py` |
| v2 kapıları null-kalibre: PBO 0,0087 · pertürbasyon 0,0565 · rejim 0,685 · evren dayanıklılığı 0,75 | VERIFIED | `kapilar_v2.py:168-173`; Faz 11 raporu (PBO'nun 0,5 referansı ızgarada geçersiz, null medyanı 0,237) |
| "Ölçülemeyen kapı geçilmiş sayılmaz" | VERIFIED | `kapilar.py Esik.gecti` |
| Sonuç: 0/52 geçti; en iyi 7/11 (h52), en iyi OOS Sharpe 0,363 (h51) | VERIFIED (rapor) | `Alpha-Discovery-Gap-Audit.md:32`; en iyi tek sembol OOS 0,459 (`cok_faktor`, null p=0,416) |
| Eşiklerin kaynağı: ölçülmüş mü, politika mı | karışık | Ölçülmüş: 1,04, v2 dördü, `gunluk_zarar`, ATR çarpanı, volatilite eşiği. **İştah/politika:** `max_drawdown 0,25`, OOS oranı 0,30, `ASGARI_PAPER_GUN 30`, `asgari_islem`, `hedef_brut 0,2`, `azami_agirlik`, asgari ağırlık 0,005 → Threshold-Policy'e |

**R4 (K-073):** Tüm araştırma backtest'leri risk motorsuz. K-073'ün tek ölçümü: `evren-kiyas`ın
tek yeniden dengelemesinde 10 hedeften **2'si** `volatilite` ile reddedildi (NEAR, ZEC; eşik
BTC p99'u). Etki yönü belirsiz: risk motoru hem kaybettiren hem kazandıran pozisyonları eler.
52 çekilişin risk motorlu yeniden koşusu **yapılmadı**; bu, eşik yeniden ölçümüyle aynı
engele (R1/R2) takılır.

## 4. Maliyet modeli

| Bileşen | Durum | Kanıt |
| --- | --- | --- |
| Komisyon: taker 10 bps/bacak (Spike 4) | VERIFIED | `config/maliyet.json` |
| Slippage: 5,30 bps/bacak, BTCUSDT 1m bar-to-bar p75, gerekçesi yazılı (60 s ölçüm 1 s pencereyi ~7,7× abartır → p75 seçildi) | VERIFIED | `config/maliyet.json kalibrasyon` |
| **Spread** | modellenmiyor ayrıca (slippage içinde sayılıyor) | `common/maliyet.py:55` |
| **Sembol başına maliyet** | **yok** — tek `MaliyetModeli` motora giriyor; 323 sembollü evrende illikit altcoinlere BTC slippage'ı | `coklu_motor.py:79` (A3) |
| Kapasite: ADV oranı, `kapasite_oranlari` | VERIFIED | `coklu_motor.py:151-175`, Faz 10 §VaR/kapasite |
| Funding: spot long-only'de maliyet değil, **veri** (funding aileleri sinyal olarak kullandı); perp carry için "eksik katman perp fee + liquidation" | VERIFIED (K-079 DATA BLOCKED) | `data/funding.py`, K-079 |
| Finansman/rollover/seans | **yok** (kripto spot varsayımı) | W1 §6 |
| Kısmi dolum / gecikme | yok: `t+1` açılışta tam dolum; gecikme bar ölçeğinde (1h) ihmal | `backtest/fill.py` |
| Maliyet-sıfır tavan testi (K-045): maliyet sıfırken bile kapı geçilmiyor | VERIFIED | `Faz-4-Donus-5-Tavan.md` |

**A3 yorumu (ölçüm değil):** tek global slippage altcoinlerde maliyeti **düşük** gösterir
(K-007 yönünün tersi), ama K-045 maliyet-sıfırda bile geçen strateji olmadığını ölçtüğü için
mevcut "0/52" sonucu bundan etkilenmez. Etki, gelecekte bir aday geçtiğinde ortaya çıkar; o
gün sembol başına maliyet zorunlu.

## 5. PnL, metrikler

| Kontrol | Durum | Kanıt |
| --- | --- | --- |
| Yıllıklandırma takvimle (365,25×24 / tf), 252 değil; ddof=1 | VERIFIED | `metrikler.py:3-30,368-389` |
| Sharpe = ort/σ × √(bar/yıl), risksiz 0; bar bazlı getiri (sıfır-getirili düz barlar dahil) | VERIFIED (konvansiyon) | 1h'de √8766 ≈ 93,6; düz dönemler σ'yı düşürür — kıyaslar tutarlı olduğu sürece sorun değil, **varlık sınıfları arası kıyasta** takvim farkı (FX 5/7) hesaba katılmalı |
| Sortino, drawdown, VaR/CVaR, profit factor | VERIFIED | `metrikler.py:263-310` |
| Decimal bağımsız referans (tek ve çok enstrüman) fixture'ları | VERIFIED | `tests/fixtures/{backtest,coklu}_referans.json`, `test_backtest_referans.py`, `test_coklu_referans.py` |
| Kıyas ayarlanmaz (K-072) | VERIFIED | `strategy/kutuphane/evren_esit_agirlik.py` |

## 6. Tekrar üretilebilirlik — R1/R2/R3 (bu oturumda ölçüldü)

`sq lab dogrula` 18 kayıt (`runs/deneyler/{degerlendirme,karsilastirma,tarama,kapilar_v2}`):

| Sonuç | Adet | Sebep |
| --- | ---: | --- |
| `veri seti değişmiş` (1h) | 10 | `data/market/BTCUSDT/1h.parquet` 2026-09-20 01:06'da yeniden yazılmış; eldeki SHA `851b947d…`, kayıtlar `e3adb02c…`/`c32b5bd0…` |
| `YENİDEN ÜRETİLEMEDİ: uyuşmuyor` (4h/1d, veri aynı) | 6 | `sonuc_hash` algoritması K-057/6'da değişti; Faz 10 §7/6 "Faz 11'de yenilenir" — **yapılmadı** (kayıtlar hâlâ 2026-09-11). Ekonomik değerlerin aynı olduğu Faz 10'da alan alan gösterilmiş; bugün kanıt **hash değil, o rapor** |
| `bu deney tipi yeniden üretilemiyor` (kapilar_v2) | 2 | tasarım gereği (girdisi defter) |

Defterdeki 52 kaydın `veri_sha256`'sı 9 farklı hash; **hiçbiri** bugün depoda yok
(`data/market` ve `data/evren` BTCUSDT dosyaları 2026-09-20'de yeniden yazıldı). Eşik yeniden
ölçümü `h51`'de "kaydırmasız koşu kayıttaki OOS sonuc_hash'ini üretmedi — ölçüm durdu" ile
düştü (`coklu-test-500-45.err.log`); state.json bunu "başlatıldı" diye taşıyor.

**Kök sebep (R3):** `Sonuc.veri.sha256` dosyanın tamamı; OOS penceresi `is_oos(n,…)` ile
**veri sonuna göreli**. Depo büyüyünce hem hash hem pencere kayar. Commit dışı K-080 taslağı
(`arsiv_indirici.py bitis_gun`) arşiv deposunu tarihe sabitliyor — doğru yön, ama:
(a) `data/market` REST deposu için karşılığı yok; (b) K kaydı ve testi yok; (c) kayıtların
"hangi veri sonuyla" koşulduğu defterde yok (yalnız hash var) → geri sarmak için tarih
başka yerden bulunmalı.

**Ne kanıtlanmış, ne kanıtlanmamış:** K-009 (aynı girdi → aynı çıktı) birim testte ve aynı
oturumda iki koşuda **kanıtlı**. "Kayıttan, aylar sonra yeniden üretilebilir" iddiası bugün
**kanıtlanamıyor**. Bu ikisi farklı iddialar; README/Roadmap ikincisini de ✅ gösteriyor.

## 7. Hipotez defteri sözleşmesi (brief §19 ile karşılaştırma)

| Alan | Defterde | Nerede |
| --- | --- | --- |
| hypothesis_id, family/strateji, timeframe, ızgara, seçim, gerekçe, veri hash, zaman | ✅ | `Hipotez-Defteri.jsonl` |
| evren tanımı, portföy yöntemi, rejim, program | ✅ (h39+; K-051) | aynı |
| instrument_set, data_source, dataset_version (tarih), fee/spread/slippage/finansman modeli, IS/OOS dönemleri, walk-forward config, budget | ❌ kayıtta yok (dolaylı: `config_hash` deney kaydında) | `runs/deneyler` (git dışı) |
| results, failure_modes, **decision** (PASS/FAIL/INCONCLUSIVE/DATA_BLOCKED/INVALIDATED) | ❌ | faz raporları (anlatısal), `Alpha-Discovery-Gap-Audit.md` tablosu |

İlk 7 kayıt **geriye dönük** (Faz 4 defterden önce; kayıt bunu açıkça söylüyor, ön kayıt
sayılmıyor). Sonuç tablosunu tek yerde tutan makine-okunur bir kayıt yok → ROADMAP-RESET'te
"deney sözleşmesi" kalemi.

## 8. BTC'ye özgü vs genelleşebilir sonuçlar (brief §8)

| Sonuç | Kapsam | Genelleşir mi |
| --- | --- | --- |
| Tek sembol yönlü TA (6 aile × 3 tf) maliyet-sıfırda bile geçmiyor (K-045) | **yalnız BTCUSDT spot** | Hayır — bir sembol, bir venue, bir eylem uzayı (long-only). Başka varlıkta ayrı çekiliş |
| Funding filtre/eğilim/ters (3) | BTCUSDT perp funding + spot fiyat | Hayır |
| Kesitsel momentum/ters, dışlama katmanları, kurma (14) | Binance spot altcoin evreni (109 ay, ~323-734 sembol) | Kısmen — kesitsel *yöntem* genel, *sonuç* kripto-spot'a özgü |
| Kıyas-üstü tek dışlama katmanı kapalı (K-068) | evren | yöntemsel ders genel |
| Rejim×aile oracle tavanı 0,60 < 1,04 (K-077) | BTC + evren | eşik 1,04 bu deftere bağlı; başka evrende tavan yeniden ölçülür |
| Jev yön ekseni %49,0 isabet (K-076) | 50 sembol, yayın sonrası pencere | Jev için genel sinyal, varlık için değil |
| Hayatta kalma yanlılığı ayda %16,7-18 | Binance spot | FX/endekste farklı ama sıfır değil (delist/kompozisyon) |
| Metodoloji (kapılar, null, PIT, ön kayıt) | — | **Evet** — asıl taşınabilir varlık bu |

**Sonuç:** "ScryneQuant'ta alfa yok" ifadesi **yanlış**; doğru ifade "Binance spot long-only
eylem uzayında, fiyat/funding/makro/konumlanma bilgi kaynaklarıyla, 52 ön kayıtlı çekilişte
1,04 eşiğini geçen yok". Brief §15'in evreni bu kanıtla **kapsanmıyor**.

## 9. Sonraki dalgalara / roadmap'e taşınanlar

| # | Kalem | Nereye |
| --- | --- | --- |
| R1-R3 | Veri seti kimliğinin tarihe sabitlenmesi (K-080'in tamamlanması: REST deposu + K kaydı + test + defterde `veri_sonu`), kayıtların yenilenmesi, eşik yeniden ölçümü | ROADMAP R1 (stabilizasyon) — **ilk iş** |
| R4 | 52 çekilişin risk motorlu yeniden koşusu (K-073 pencere sonrası) | R1/R5 |
| R5 | Sembol/enstrüman başına maliyet modeli | R2 (registry) |
| R6 | Embargo politikası | Threshold-Policy `DECISION REQUIRED` |
| R7 | Deney sözleşmesi + karar durumu tek dosyada | R5 (governance) |
| — | Sharpe yıllıklandırması varlık sınıfı takvimine bağlanmalı | R2/R4 |

**Sonraki dalga:** W4 — Alpha Baseline (brief §8 çıktısı `W4-Alpha-Baseline.md`; §8 burada büyük
ölçüde cevaplandı, W4 çekiliş-bazlı tabloyu üretir).
