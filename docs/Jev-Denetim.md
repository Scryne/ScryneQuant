# Jev Integration Audit — repository ↔ `docs/Jev-Integration-Spec.md`

> **Tarih:** 2026-09-19 · **Kapsam:** Spec §64 Phase 1 (repository audit) + Phase 2 (gap
> analysis) · **Kod değişikliği:** yok · **Test tabanı:** 1.441 test yeşil (`uv run pytest`)
> · **Bağlayıcı kararlar:** K-002, K-003, K-009, K-037, K-039, K-045, K-049, K-051, K-061,
> K-067, K-068

Bu doküman iki soruya cevap verir: (1) spec'in istediği her şeyin ne kadarı zaten var,
(2) Jev'i mevcut mimariye **en az duplication ve en az riskle nereden** bağlamalıyız.

---

## Repository Audit

### Mimari (bugünkü akış)

```
Binance (WS + REST)                  Arşiv (data.binance.vision)      ALFRED (FRED vintage)
   │ exchange/akis.py                    │ exchange/binance_arsiv.py       │ data/alfred.py
   ▼                                     ▼                                 ▼
data/dogrulama.py  ──►  KaliteDurumu (ok/gap/duplicate/suspect/backfilled)  (K-006)
   │                                     │
   ▼                                     ▼
data/depo.py (Parquet, zstd, SHA-256 = veri kimliği, K-009)   data/pit.py (available_time ≤ t)
   │  data/market/BTCUSDT/{1m,1h,4h,1d}  data/evren/<sembol>/1h   data/funding, data/turev, data/makro
   ▼
features/barlar.py (tek pandas kullanıcısı) ──► features/motor.py (bildirimsel defter, nedensel, numpy)
   │
   ▼
strategy/baglam.py  Baglam(t'de kesik, ters indeks, K-002)  ──►  Strateji.on_bar(ctx) → Sinyal | None
   │                                                              (I/O yok: test_izolasyon.py, K-003)
   ▼
risk/motor.py  RiskMotoru.degerlendir → OnayliNiyet (HMAC mühür) | Red      (K-032, K-037)
   │  limitler: config/risk.json (kaynak + gözden geçirme koşulu, K-033)
   ▼
execution/kapi.py gonder(OnayliNiyet)  ── yalnızca mühürlü niyet; Sinyal tipini tanımaz (AST testi)
   │
   ▼
oms/ (emir state machine, idempotent kimlik K-040, mutabakat K-046/47) ──► exchange/imzali.py (testnet)

Tek döngü: backtest/coklu_motor.CokluAdimci.adim  (fill@next open K-004 → risk durumu → karar → değerleme)
   ├─ backtest/motor.Backtest      (tek sembol = sarmalayıcı, bit düzeyinde aynı, K-057)
   ├─ live/motor.PaperMotoru       (tek sembol paper/gözlem; BarPenceresi + aynı dogrula)
   └─ live/evren_motor.EvrenPaperMotoru (Faz 14; host'ta koşuyor, gerçek emir yok)

Kayıt: runs/paper/*.sqlite (koşu+kontrol noktası+fill+olay+audit tek dosya) · risk/audit.py
(append-only, zincir hash, UPDATE/DELETE tetikleyicili) · runs/deneyler/*.json (Deney: girdi/çıktı
hash, tekrar.py ile yeniden üretim) · docs/Hipotez-Defteri.jsonl (52 çekiliş, K-039) ·
docs/Arastirma-Programlari.jsonl (10 kayıt, K-051; LlmTuretimi + leak_riski alanı hazır)
```

### Existing

| Alan | Nerede | Not |
| --- | --- | --- |
| Zaman disiplini | `common/zaman.py` | UTC epoch ms, bar ts = açılış (K-005), `bar_kapandi_mi` (serverTime'a göre). Tek dönüşüm noktası. |
| Market data modeli | `data/semalar.py` | 9 sütunlu dondurulmuş Arrow şeması + `quality_status`. Dosya SHA-256 = veri kimliği. |
| Veri kaynakları | `data/market` (BTCUSDT 1m/1h/4h/1d, 1h: 45.576 bar 2021-06-28→2026-09-09), `data/funding` (REST, `fundingTime ≤ t` nedensel hizalama, `barlara_hizala`), `data/turev/{funding,premium,metrics}` (arşiv; metrics = OI adedi, taker, L/S oranı, 5 dk, `available_time = create_time+5dk`), `data/makro` (ALFRED vintage, gün sonuna yuvarlanan `available_time`), `data/duyuru` | Canlı: `exchange/akis.py` ham WS (kapanmışlık bayrağı var) + REST resync; `exchange/turev_rest.py` funding+premium (arşivle bit düzeyinde aynı ölçüldü). |
| PIT / `available_time` kesmesi | `data/pit.py::kes`, `kesme_sozlesmesini_dogrula` | Her kesici uygulamayı tuzaklı fixture'la sınayan sözleşme testi. |
| Veri doğrulama | `data/dogrulama.py::dogrula` | Backtest ve canlı **aynı** fonksiyon (`live/pencere.py` her barda yeniden doğrular). |
| Feature/indicator sistemi | `features/motor.py` `DEFTER` + `features/indikator.py` | sma, ema, rsi, atr, true_range, bollinger, roc, en_yuksek/en_dusuk, hacim_sma, persentil, kumulatif, log_degisim; funding/basis/makro/konumlanma girdileri. Hepsi nedensel, `test_indikator.py` geleceği bozarak ölçüyor. TA-Lib konvansiyonu, referans dondurulmuş (K-026). |
| Strateji/sinyal sözleşmesi | `strategy/temel.py`, `strategy/baglam.py`, `strategy/sinyal.py` | `Sinyal` frozen pydantic, `extra="forbid"` (fiyat/miktar/emir tipi sızamaz), `reason` kod deseni, `confidence` alanı var. `Baglam` negatif indeksi hata yapar. |
| Backtest | `backtest/coklu_motor.py` (`CokluAdimci` tek döngü), `backtest/motor.py` (sarmalayıcı), `fill.py`, `defter.py`, `metrikler.py`, `sonuc.py` | Fill sonraki açılış (K-004), maliyet `common/maliyet.py` (`config/maliyet.json`, aleyhte K-007), `ok` olmayan barda karar/fill yok (K-028), bağımsız kapalı-formül referansla çapraz doğrulama (K-029), `sonuc_hash`. |
| Risk motoru | `risk/motor.py`, `niyet.py`, `muhur.py`, `limitler.py`, `durum.py`, `promotion.py` | 8 adımlı sabit karar sırası; azaltan niyet engellenmez; SAFE_MODE; drawdown/günlük zarar/cooldown/volatilite guard; boyutlandırma yalnız aşağı çeker; portföy düzeyi tavanlar. Limitlerin her biri `kaynak`/`gozden_gecirme` taşır. |
| Execution + OMS | `execution/kapi.py`, `execution/motor.py`, `oms/*` | Tek kapı, yalnız `OnayliNiyet`; `test_risk_bypass.py` AST ile `execution/`+`oms/`'un `strategy.sinyal`e ulaşmadığını zorluyor. |
| Kill switch | `risk/motor.kill` (süreç içi), `live/kill.py` (süreç dışı, K-065) | Riski azaltan otomatik, izni artıran elle (K-050). |
| Config | `config/risk.json`, `config/maliyet.json` | Genel bir config framework'ü yok; JSON + gerekçe alanı kalıbı. |
| Secrets | `SQ_BINANCE_TESTNET_*` env, `.env` gitignore'da, `.env.example` yalnız adlar, `tools/faz14_anahtar_denetimi.py` | `TYPESAFE_API_KEY` SDK'nın kendi env okumasıyla; kod anahtara dokunmuyor (`gizli_tekrar.py`). |
| Persistence | SQLite WAL (`live/depo.py`, `live/evren_depo.py`), Parquet, JSONL defterler | K-034: PostgreSQL ertelendi, ölçüldü. |
| Logging / audit | `risk/audit.py` (`Defter` protokolü: `SqliteDefter`, `JsonlDefter`, `BellekDefteri`; zincir hash; `dogrula()`), `live/depo.KosuOlayi` olay günlüğü, `live/izleme.py` alarm + `docs/Runbook.md` | `structlog` bağımlılık listesinde ama **kullanılmıyor**. |
| Test altyapısı | 1.441 test, `tests/conftest.py::bar_uret`, `test_look_ahead.py` (rastgele + yukarı + aşağı bozma, negatif kontrol), `test_izolasyon.py` (izin listesi), `test_risk_bypass.py`, `test_gizli_tekrar.py::test_islem_katmani_dedektoru_import_etmez` (**`typesafe` importu strategy/backtest/features/risk/execution/live'da yasak**) | CI **yok** (`.github/` yok; remote GitHub var). |
| Deney / araştırma | `research/deney.py` (tarif + hash + `tekrar.py` yeniden üretim), `hipotez.py` (ön kayıt, K-039), `program.py` (bütçe + `LlmTuretimi.leak_riski`, K-051/K-049), `bolme.py`, `walkforward.py`, `karsilastirma.py` (al-tut kıyası zorunlu K-030), `kapilar.py`/`kapilar_v2.py` (11 sayısal kapı), `coklu_test.py`, `rejim.py` (parametresiz nedensel rejim bölümlemesi), `dsr.py`, `pbo.py` | Faz 4-16 raporları `docs/` altında; sayılar oradan alınır. |
| **Mevcut Jev kullanımı** | `research/gizli_tekrar.py` (K-061), `tools/faz16_duyuru_jev_dogrula.py` (K-067/3), `cli/main.py::_typesafe_istemci` | Model pini `jev-1.13.0`, çözülen model ≠ istenen → durur; soru metni `SORU_SHA256` ile donmuş ve testli; istek/yanıt `runs/gizli_tekrar/`'a dondurulur; `Istemci` Protocol'ü testte sahteyle değiştiriliyor. **Bu üç kalıp (pin, soru hash'i, dondurma) Jev adaptörünün tamamıdır; yeniden yazılmaz, taşınır.** |

### Partial

| Gereksinim | Ne var | Ne eksik |
| --- | --- | --- |
| Canonical market state | `PiyasaGorunumu` + `Baglam` stratejinin kanonik görünümü: deterministik, t'de kesik, salt okunur. | Serileştirilebilir/hash'lenebilir **anlık görüntü** yok; `state_version` kavramı yok; çok timeframe'li tek nesne yok. |
| State hashing | `common/hash.nesne_hash` (sort_keys, kanonik JSON), `dosya_hash`. | Snapshot'a uygulanmış hâli yok. |
| Timestamp discipline (karar vs kesim) | `Sinyal.timestamp` = karar barının açılışı; fill sonraki bar; `available_time` kesmesi bar-dışı veride. | `decision_timestamp` ≠ `data_cutoff` ayrımı tek nesnede taşınmıyor (bugün ikisi de "barın açılışı"na eşit varsayılıyor — bar için doğru, funding/OI için kesim ayrıca yazılmalı). |
| Multi-timeframe | 4h ve 1d Parquet tarihsel olarak var (`data/market`). | Canlı akış tek timeframe (`BarAkisi(sembol, timeframe)`); 4h bağlam ya ikinci akış ya da 1h'den **yalnızca kapanmış** 4h barları toplayarak üretilmeli (spec §7: kapanmamış mum gelecek OHLC taşımamalı). 1h→4h toplamanın Binance 4h dosyasıyla eşitliği ölçülmeli (spike). |
| Technical / market structure | RSI, EMA, SMA, ATR, Bollinger, ROC, N-bar en yüksek/en düşük var. | MACD, VWAP, swing high/low, destek/direnç, "yapı" etiketleri (HH/HL) yok. Eklenecekse `DEFTER`e nedensel + referans testli girer (K-026 kalıbı). |
| Derivatives | Funding: canlı REST + arşiv, nedensel hizalama, bayatlık kuralı. Basis (premium) aynı. OI/taker/L-S: **arşiv** (5 dk, `available_time` tanımlı). | Canlı OI toplayıcısı yok; arşiv dosyası T+1 iner (canlıda t anında erişilebilir değil), Binance `openInterestHist` ~30 gün tutuyor (Spike 5). Spec §9: zaman damgası sorunlu kaynak kullanılmaz → OI MVP dışı, ayrı deney. |
| Leakage testi | Bozulmuş-gelecek testi sinyal dizisi için var (3 bozma + negatif kontrol); funding için var. | Spec'in istediği **snapshot byte-identical** testi (t sonrası **silme** dahil) kanonik state için yok. Kalıp hazır, nesne yok. |
| Replay | Backtest tarihsel seride bar bar koşuyor; `Deney`/`tekrar.py` deneyi yeniden üretiyor. | "Tarihsel state → Jev → dondurulmuş karar dosyası" akışı yok. |
| Experiment tracking | `Deney` (tip, girdi/çıktı hash, git durumu, ortam), hipotez defteri, program defteri, `LlmTuretimi` (model, kesim, prompt_hash, girdi_hash, leak_riski). | `LlmTuretimi` hiçbir boru hattında üretilmiyor; `Deney.TIPLER`de Jev tipi yok. |
| Structured model output | Jev zaten tipli döner (Choice/Noul/Score + olasılık + confidence); `gizli_tekrar` şema kontrolü (model, kategori) yapıyor. | Karar şeması (`JevKarari`) ve "şema geçmezse GEÇERSİZ" politikası yok. |
| Failure-closed | Risk: ölçülemeyen guard geçilmiş sayılmaz; bayat veri → giriş yok; `ok` olmayan bar → karar yok; toparlanma ayrışması → dur. `gizli_tekrar`: model uyuşmazlığı → hata. | Jev'e özgü hata sınıflandırması (timeout / API / auth / şema / bayat state / hash uyuşmazlığı) ve "son kararı yeniden kullanma" yasağı kodlanmamış. SDK `RetryPolicy` + `timeout` destekliyor, projede yapılandırılmamış. |
| Shadow mode | `gozlem` modu (K-035): promotion'suz strateji canlı veride koşar, kanıt üretemez. Host'ta evren gözlem koşuları çalışıyor. | Strateji için var; **karar katmanı gözlemcisi** yok. |
| Paper mode | `PaperMotoru` / `EvrenPaperMotoru` + risk zorunlu + execution kapısı. | Jev'in paper'a girmesi = Jev'den türeyen bir strateji; bugün K-067 bunu yasaklıyor (bkz. Conflicts). |
| Audit logging | `risk/audit.py` append-only zincir. | Olay türleri risk'e özel (`OlayTuru`); Jev kararı için ya yeni tür ya ayrı tablo. Zincir-hash kalıbı yeniden kullanılır. |
| Outcome linkage | `Islem.net_pnl` (maliyet düşülmüş), `rejim.etiketle` (t−1'e kadar), `tools/faz16_kaynak_olcumu.py` ileri getiri (yalnız IS, K-068). | Karar × {1h,4h,24h getiri, MAE, MFE} birleştiricisi yok; `Islem`'de MAE/MFE yok. |
| Kalibrasyon | `risk/kalibrasyon.py` risk limit kalibrasyonu (olasılık kalibrasyonu değil). | Brier / ECE / kova tablosu yok. |
| Telemetri | `live/izleme.py` dört boyut + alarm + runbook kodları. | Jev sayaçları (istek/başarı/timeout/şema hatası, gecikme p50/p95/p99, yön/güven dağılımı) yok. |
| Config (provider/model) | `MODEL` sabiti modülde (K-061/3 bilinçli). | `config/jev.json` yok. |

### Missing

- `jev/` karar katmanı: kanonik durum kurucu, dondurulmuş soru seti, adaptör, `JevKarari`, karar defteri.
- Gölge gözlemci süreci (bar kapanışı → durum → Jev → kayıt; emir yok).
- Tarihsel replay üreticisi (dondurulmuş türetim dosyası + manifest, K-049/5).
- Snapshot byte-identical sızıntı testi (bozma + silme) ve CI (`.github/workflows` yok).
- Karar → sonuç bağlama, yön isabeti, kalibrasyon, çekimserlik, gecikme raporları.
- Prompt/istek kaydında sır tarayıcısı (state'e `SQ_`/`TYPESAFE` değeri sızmadığını kontrol eden test).
- Jev'e özgü K-kaydı (yetki sınırı, kesim varsayımı, K-067'nin "ölçüm ≠ sinyal" ayrımı).

### Conflicts

| # | Spec | Repo kararı | Sonuç |
| --- | --- | --- | --- |
| C1 | §45 Exp. B "Jev Only", Exp. C "Baseline + Jev confirmation": Jev yönü işleme dönüşür | **K-067:** "Jev sinyal üretmez. Hiçbir alım/satım niyeti… Jev çıktısından doğrudan türetilemez"; K-049/1 semantic AI yetkisiz | Gölge modda yön **ölçülür** (K-067'nin "ölçüm, özellik değil" istisnası). Exp. D (Jev **filtre**) K-067/3 kalıbına uyar: dondurulmuş alanı strateji okur, funding_filtre gibi. **B ve C yeni bir K-kaydı (K-074) ile K-067 değiştirilmeden açılamaz.** Karar Scryne'ın. |
| C2 | §64 Phase 7 replay: "historical data → state → Jev → decision" | **K-049/5:** backtest içinde canlı LLM çağrısı yasak; çıktı bir kez üretilip dondurulur, backtest dosyayı okur, veri seti hash'i = dosya SHA-256 | Replay = **tek seferlik dondurma üreticisi**; backtest/değerlendirme yalnızca dondurulmuş Parquet'i okur. Mimari böyle kurulur. |
| C3 | §8, §39, §43 tarihsel replay üzerinden isabet/kalibrasyon kanıtı | **K-049/4:** LLM eğitim kesimi öncesi türetim `leak_riski` taşır, **mutlak engel**. TypeSafe Jev'in kesim tarihini yayınlamıyor; proje varsayımı = sürüm çıkış tarihi (`jev-1.13.0` → 2026-09-10, `/v1/models` `release_date`; `TypeSafe.md` notu) | 2026-09-10 öncesi **her** replay `leak_riski=true`: boru hattı/gecikme/şema doğrulaması için kullanılır, isabet sayıları **kanıt değildir**. Gerçek ölçüm penceresi = ileriye dönük gölge koşusu. Spec'in beklediği "geçmişte ölç, sonra canlıya" sırası bu projede **"canlıda gölgede ölç"** olur. |
| C4 | §20/§24 `key_factors` serbest metin listesi; §19 `temperature`, `max_tokens`; §50 seed | Jev metin üretmez (System One: Choice/Noul/Score); API'de temperature/seed yok; tutarlılık ölçüldü ±0,01–0,03 (bit-deterministik değil) | `key_factors` = önceden tanımlı **Noul faktörler** (kod tanımlar, Jev evet/hayır olasılığı verir). Config: `model, timeout, retry`; örnekleme parametresi yok. Reproducibility tanımı: aynı `durum_hash + soru_sha256 + model` → cevap **sapması ölçülür ve kaydedilir**, bit eşitliği iddia edilmez. |
| C5 | §7 Jev'e OHLCV dizileri + göstergeler | Jev jaggedness dokümanı: sayma/aritmetik/sayısal yakınlık/tarih sıralaması **güvenilmez**; `TypeSafe.md` ölçümü: aritmetik yanlış. K-067 gerekçesi: zaman serisi tahmini uygun kullanım değil | Sayısal hesap **kodda** (indikatör, yapı etiketi, persentil); Jev'e **betimleyici** state gider ("1h kapanış EMA20 üstünde", "RSI aşırı alım bandı", "funding 90. persentil"). Ham dizi gönderilmez. |
| C6 | §20 `direction: LONG/SHORT/FLAT` | v1 spot, `Yon` = BUY/SELL/FLAT, açığa satış yok | Karar şemasında SHORT **ölçüm etiketi** olarak kalır (isabet ölçülebilir); herhangi bir sinyal eşlemesi long/flat. |
| C7 | §2 "Decision Gate" Jev ile risk arasında | **K-037:** engelleyen katman risk dışında olabilir, izin veren olamaz | Kapı yalnızca **eler** (güven eşiği, bayatlık, çekimser). Onay üreten tek yer risk motoru kalır. |
| C8 | §47 experiment registry (yeni) | K-039/K-051: **tek** defter, program başına bütçe; K-049/2: her soru seti/eşik bir çekiliş | Ayrı registry yok. Prompt sürümü/eşik değişimi = yeni hipotez satırı; `Deney.TIPLER`e `jev_golge`/`jev_tekrar` eklenir. Gölge **ölçümü** çekiliş değildir (strateji koşmuyor, parametre seçilmiyor — K-068 notu); **sonuç tanımları ve eşikler koşudan önce yazılır** (§35). |
| C9 | §68 BTCUSDT tek sembol, yönlü karar | **K-045:** tek sembollü yönlü arama kapandı; istisna: ölçüyle gerekçelendirilmiş farklı bilgi kaynağı. **K-068:** kaynak farkı tek başına yetmez, IS'te ileriye dönük sıralama gücü gerekir | Gölge ölçümü bir strateji koşturmadığı için K-045'e girmez. B/C/D'den herhangi biri **program kaydı** ister; K-045 istisnası için `kaynak_olcumu` gölge penceresinden gelir (Jev yönü ↔ fiyat özelliklerinden bağımsızlık + IS'te ileri getiri ilişkisi). |
| C10 | §63 `data/ features/ decision/ logging/ backtest/ experiments/` klasörleri | Hepsinin karşılığı var (`data`, `features`, `risk/audit`, `backtest`, `research`) | Yalnızca `jev/` (spec'teki `decision/jev`) yeni. Diğerlerine dokunulmaz. |
| C11 | §15 "test CI'a bağlanmalı" | CI yok | GitHub remote var → minimal `.github/workflows/test.yml` (`uv sync` + `uv run pytest`) eklenir; Jev dışı ama spec'in açık isteği — onay ister. |

---

## Proposed Architecture

**Bağlama noktası (cevap):** Jev, mevcut karar zincirine **girmez**; onun **yanında** koşan,
aynı bar penceresini ve aynı özellik hesabını okuyan bir **gözlemci**dir. Trading yoluna
(`strategy → risk → execution`) tek satır eklenmez. Mevcut test
(`test_islem_katmani_dedektoru_import_etmez`) bunu zaten zorluyor: `typesafe` importu o altı
pakette yasak; yön `jev → live/features/data`, asla tersi.

```
                     ┌──────────── mevcut, dokunulmaz ────────────┐
Binance WS ─► exchange/akis ─► live/pencere.BarPenceresi ─► (PaperMotoru: strateji→risk→execution)
                                        │  aynı diziler, aynı dogrula()
                                        ▼
                     ┌──────────── yeni: src/scryne_quant/jev/ ────────────┐
                     │ durum.py    kanonik durum (saf, numpy, t'de kesik)  │
                     │ sorular.py  donmuş soru seti (SORU_SHA256 = prompt) │
                     │ istemci.py  TypeSafe adaptörü (pin, timeout, retry) │
                     │ karar.py    JevKarari (frozen, extra=forbid)         │
                     │ defter.py   append-only karar deposu (zincir hash)   │
                     │ golge.py    canlı gözlemci (emir yok)                │
                     │ tekrar.py   tarihsel dondurma üreticisi (K-049/5)    │
                     │ sonuc.py    karar × ileri sonuç, kalibrasyon, gecikme│
                     └──────────────────────────────────────────────────────┘
                                        │
                     runs/jev/<kosu>.sqlite  (gölge kararları, zincir hash)
                     data/semantik/jev/<turetim_id>/kararlar.parquet + manifest.json  (dondurulmuş)
```

Bileşen kararları:

1. **`jev/durum.py` — `kanonik_durum(diziler_1h, i, *, funding, surum) -> dict`.** Girdi
   `features/barlar.bar_dizileri` çıktısı (backtest ve canlı için **aynı** diziler); 4h
   bağlam 1h'den yalnızca **kapanmış** 4h barları toplayarak üretilir (kapanmamış 4h mum
   yok). İndikatörler `features/motor.hesapla` ile (mevcut defter; MACD/swing gerekirse
   deftere nedensel + referans testli eklenir). Çıktı: `{"surum": 1, "sembol", "karar_ms"
   (bar açılışı), "veri_kesimi_ms" (barın kapanışı; funding için kendi `funding_time`),
   "timeframes": {"1h": {...}, "4h": {...}}, "teknik": {...betimleyici...}, "yapi": {...},
   "turev": {"funding": {...} | "eksik"}, "kalite": {...}}`. Sayılar yuvarlanmış float ya da
   etiket; NaN → `"eksik"`, bayat → `"bayat"` (spec §56: 0 asla "yok" demek değil).
   `durum_hash = nesne_hash(durum)`. Numpy dışında import yok (strateji izolasyon kalıbı).
2. **`jev/sorular.py` — soru seti sabit ve hash'li.** `yon` (Choice: long/short/flat),
   `rejim` (Choice: trend/aralik/yuksek_vol/dusuk_vol/belirsiz), `kurulum` (Score: dusuk/orta/
   yuksek), `cekimser` (Noul), önceden tanımlı `faktor_*` Noul'ları. `SORU_SHA256` = spec'in
   `prompt_version`ı; değişimi = yeni çekiliş (hipotez satırı). Model `jev-1.13.0` pinli;
   çözülen ≠ istenen → karar GEÇERSİZ.
3. **`jev/istemci.py`** — `gizli_tekrar.Istemci` Protocol'ünün genişletilmiş hâli; `timeout`,
   `RetryPolicy(max_retries)` config'ten; hata sınıfları → `KararDurumu` enum
   (`GECERLI`, `TIMEOUT`, `API_HATASI`, `KIMLIK_HATASI`, `SEMA_HATASI`, `MODEL_UYUMSUZ`,
   `BAYAT_DURUM`, `EKSIK_VERI`). Geçersiz her durumda **karar yok** ve **önceki karar
   yeniden kullanılmaz** (testle). Anahtar koda girmez; state'e sır sızmadığı testle taranır.
4. **`jev/karar.py` — `JevKarari`** frozen pydantic, `extra="forbid"`; alanlar spec §33 + `durum`
   (KararDurumu) + ham cevaplar (`answers` sözlüğü; SDK ham metin döndürmez). **Miktar, fiyat,
   kaldıraç, stop alanı yok** — `Sinyal`in tip-düzeyi yasağıyla aynı.
5. **`jev/defter.py`** — `risk/audit.py`'nin zincir-hash + UPDATE/DELETE tetikleyici kalıbı,
   `jev_karar` tablosu; `runs/jev/<kosu>.sqlite`. Dondurulmuş replay ayrıca Parquet + manifest
   (`LlmTuretimi.sozluk()` alanları: model, `egitim_kesim_ms` + kaynağı ("varsayım: sürüm
   çıkışı"), kapsam, `prompt_hash=SORU_SHA256`, `girdi_hash`, `leak_riski`).
6. **`jev/golge.py`** — `exchange/akis.BinanceBarAkisi` + `live/pencere.BarPenceresi` +
   `turev_rest.funding`; her kapanmış `ok` barda durum → Jev → defter. `PaperMotoru`
   kullanılmaz, execution import edilmez (AST testi). Ayrı süreç: `sq jev golge`. Kesinti/
   toparlanma: girdi saklanır, durum yeniden üretilir (K-038 kalıbı); durum hash'i uyuşmazsa
   koşu durur.
7. **`jev/tekrar.py`** — `data/market` (veya `data/evren`) 1h + `data/funding` üzerinde aynı
   `kanonik_durum`; çıktı dondurulmuş dosya. **Backtest bu modülü çağırmaz.** Kesim öncesi
   kapsam otomatik `leak_riski=true`.
8. **`jev/sonuc.py`** — dondurulmuş/gölge kararları bar serisiyle birleştirir: ileri getiri
   (1h/4h/24h), MAE/MFE (high/low'dan), maliyet sonrası (`MaliyetModeli` ile round-trip),
   kıyas stratejisinin aynı bardaki sinyali (`strategy/kosu.sinyalleri_uret`, kayıtlı kıyas
   K-030/K-072), yön isabeti, çekimserlik oranı, güven kovaları + Brier + ECE, rejim başına
   (`research/rejim.etiketle`), gecikme p50/p95/p99. Sonuç tanımları **koşudan önce**
   `config/jev.json`'a yazılır (§35).
9. **Config `config/jev.json`** — `model`, `egitim_kesim` {tarih, kaynak}, `timeout_s`,
   `max_retries`, `guven_esigi` (ayarlanabilir, kapı değil), `durum_surumu`,
   `sonuc_ufuklari`, `bayat_ms`. Gerekçe alanı kalıbı `risk.json` ile aynı.
10. **CLI** — `cli/jev.py` (yeni Typer app; `testnet.py`/`kill.py` kalıbı), `main.py`'ye tek
    satır `app.add_typer(jev_app)`. Komutlar: `golge`, `tekrar`, `degerlendir`, `durum`.
11. **Karar günlüğü** — K-074: Jev karar katmanının yetki sınırı (yalnız gölge/ölçüm), kesim
    varsayımı ve kaynağı, K-067'ye açık ek ("yön ölçümü ≠ sinyal"), B/C deneylerinin açılma
    şartı (program kaydı + K-045 istisnası + K-067 değişikliği).

**Yetki sınırı, kodla:** `JevKarari`'ndan `Sinyal` üreten hiçbir fonksiyon bu fazda
yazılmaz. Exp. D açılırsa bile yol dondurulmuş Parquet → `features/barlar.EK_SAYISAL` kalıbı
(funding gibi bar çerçevesine sütun) → strateji `ctx.ozellik("jev_rejim")` okur → kural
sinyal üretir → risk → execution. Jev hiçbir noktada risk/execution ile konuşmaz.

---

## Implementation Plan

Her phase: implement → test → inspect → verify → document. Test geçmeden sonraki phase yok.

| Phase | İş | Bitti kriteri |
| --- | --- | --- |
| 1 | Repository audit | **Bu doküman.** |
| 2 | Gap analysis | **Bu doküman** (Conflicts tablosu). |
| 3 | Tasarım + K-074 + `config/jev.json` + spike'lar: (a) 1h→4h toplama ≡ Binance 4h dosyası mı, (b) betimleyici state örneğinde Jev cevap/gecikme/tutarlılık (5 tekrar), (c) `/v1/models` `release_date` kaydı | K-074 yazılı; config'te kesim tarihi ve kaynağı; spike sayıları `docs/spikes/07-jev-durum.md`'de. Toplama eşit değilse 4h akışı ayrı alınır. |
| 4 | `jev/durum.py` kanonik durum | Aynı diziler + aynı `i` → aynı `durum_hash` (10 tekrar); NaN/bayat → `eksik`/`bayat` etiketi; numpy dışı import yok (izolasyon testi kalıbı). |
| 5 | Zaman + sızıntı koruması | `test_jev_sizinti.py`: t sonrası **bozma** (3 bozma) ve **silme** → JSON byte-identical; negatif kontrol (kasıtlı sızdıran kurucu yakalanıyor); funding için `funding_time > kapanış` görünmüyor; `karar_ms`/`veri_kesimi_ms` doğrulanıyor. CI workflow eklenir ve bu test orada koşar. |
| 6 | `jev/sorular.py` + `istemci.py` + `karar.py` | Sahte istemciyle: şema dışı cevap → `SEMA_HATASI`; timeout → `TIMEOUT`; model uyuşmazlığı → `MODEL_UYUMSUZ`; hiçbir hata durumunda önceki karar taşınmıyor; `JevKarari` miktar/fiyat alanı reddediyor; state'te sır yok. `SORU_SHA256` sabitlenmiş ve testli. |
| 7 | `jev/defter.py` | Append-only, zincir `dogrula()`, UPDATE/DELETE tetikleyici; kayıt spec §33 alanlarının tamamını taşıyor; `durum_hash` ile durum yeniden bulunabiliyor. |
| 8 | `jev/tekrar.py` tarihsel dondurma | BTCUSDT 1h son N bar (örneklem, maliyet ölçülü) → Parquet + manifest, `leak_riski=true` (kesim öncesi); aynı girdiyle ikinci koşu: `durum_hash` %100 eşit, cevap sapması ölçülüp raporlanmış. Backtest bu dosyayı **okumuyor** (henüz tüketici yok). |
| 9 | `jev/golge.py` + `sq jev golge` | Host'ta ayrı süreç, `ok` bar başına bir karar, emir yok (AST: `jev/` `execution`/`oms`/`risk` import etmez); kesinti sonrası yeniden üretim; `sq jev durum` sayaçlar (istek/başarı/timeout/şema, gecikme p50/p95/p99, yön/güven/çekimser dağılımı). ≥ 8 gün (K-069 kalıbı) veri. |
| 10 | Baseline comparison (`jev/sonuc.py`, `sq jev degerlendir`) | Gölge penceresi + dondurulmuş örneklem üzerinde: yön isabeti, kalibrasyon (kova/Brier/ECE), çekimserlik, rejim başına, maliyet sonrası, kıyas (`al_tut` + kayıtlı kıyas) ile aynı bar karşılaştırması. **Negatif sonuç aynen kaydedilir**, `runs/jev/` + `docs/Jev-Golge-Raporu.md`. Exp. A vs D **dondurulmuş alan + program kaydı** ile; B/C yalnızca K-074 izin verirse. |
| 11 | Paper | Yalnızca program kaydı (K-051) + Jev-türevli strateji K-074 ile izinliyse; `PaperMotoru` değişmez, strateji `EK_SAYISAL` alanını okur. Bu görev kapsamında **başlatılmaz**, koşul yazılır. |
| 12 | Kontrollü live | Faz 8 kapıları (K-010/K-019/K-054, 11 kapı) + K-050 elle onay. Bu görev kapsamı dışı; hiçbir kısayol yazılmaz. |

---

## Risks

1. **Kesim tarihi varsayımı yanlışsa** (Jev daha eski/yeni veriyle eğitildiyse) `leak_riski`
   sınırı kayar. Tarih uydurulmaz; TypeSafe'ten resmi beyan istenir, gelene kadar varsayım
   "sürüm çıkışı" ve kaynak alanı bunu söyler.
2. **Jev sürümü kalkarsa** (`jev-1.12` kalktı) gölge koşusu durur; yeni sürüm = yeni deney.
   Koşu sürüm uyuşmazlığında GEÇERSİZ üretir, sessizce geçmez.
3. **Betimleyici state tasarımı bir çekiliştir** (K-049/2): hangi alanların gireceği koşudan
   önce donar. Sonuca bakıp alan eklemek yeni hipotez satırı ister. Kodda yakalanamaz, defterle
   korunur.
4. **Kısa gölge penceresi**: 8 günde 1h'te ~190 karar; kalibrasyon kovaları seyrek kalır.
   Rapor bunu güven aralığıyla yazar; "çalışıyor/çalışmıyor" ilanı yapılmaz (§65).
5. **1h→4h toplama Binance 4h ile eşit çıkmazsa** (Binance 4h ızgarası UTC 00/04/…; 1h
   toplamı kural olarak aynı olmalı) ikinci akış gerekir; spike ölçer.
6. **Gecikme**: `TypeSafe.md` ölçümü 0,26–0,7 s, ilk bağlantı ~12 s (DNS). 1h barda bütçe
   bol; yine de ölçülüp kaydedilir (K-067 "gecikme ölçülmeden canlı yola bağlanmaz").
7. **Host kaynakları**: evren koşusu süreç başına ≈4,5 GB (bellek notu). Gölge süreci tek
   sembol, küçük; yine de ayrı süreç olarak ölçülür.
8. **K-067 ile gerilim**: yön sorusu "ölçüm" olarak meşru, "özellik" olarak değil. Sınır
   K-074'te yazılı olmazsa ileride sessizce kayar.
9. **CI ekleme** Jev dışı bir dosya; kapsam politikası (§15) ile spec'in açık isteği (§15
   "CI'a bağlanmalı") çelişiyor — onay ister.
10. **Prompt injection yüzeyi yok** (state tamamen koddan üretilir, dış metin yok) — ama
    ileride duyuru/haber alanı eklenirse bu değişir; o gün ayrı değerlendirilir.

---

## Files Expected To Change

**Yeni**

- `src/scryne_quant/jev/__init__.py`, `durum.py`, `sorular.py`, `istemci.py`, `karar.py`,
  `defter.py`, `golge.py`, `tekrar.py`, `sonuc.py`
- `src/scryne_quant/cli/jev.py`
- `config/jev.json`
- `tests/unit/test_jev_durum.py`, `test_jev_sizinti.py`, `test_jev_karar.py`,
  `test_jev_defter.py`, `test_jev_golge.py`, `test_jev_tekrar.py`, `test_jev_sonuc.py`,
  `test_jev_izolasyon.py` (AST: `jev/` → `execution`/`oms`/`risk` yok; `strategy`/`backtest`/
  `live`/`risk`/`execution`/`features` → `jev` yok)
- `docs/Jev-Denetim.md` (bu dosya), `docs/spikes/07-jev-durum.md`, `docs/Jev-Golge-Raporu.md`
  (Phase 10)
- `.github/workflows/test.yml` (onaya bağlı)

**Değişen (asgari)**

- `src/scryne_quant/cli/main.py` — tek satır: `app.add_typer(jev_app)`; mevcut
  `_typesafe_istemci` fabrikası `jev/istemci.py`'ye taşınırsa `tekrar-kontrol` oradan okur
  (davranış değişmez, test korur).
- `src/scryne_quant/research/deney.py` — `TIPLER`e `jev_tekrar`, `jev_golge`.
- `src/scryne_quant/features/motor.py` + `indikator.py` — **yalnızca** durum kurucunun
  ihtiyaç duyduğu ve mevcut defterde olmayan indikatör (MACD, swing) eklenirse; nedensel +
  referans testi + `test_indikator.py` bozma testi şart (K-026). Aksi hâlde dokunulmaz.
- `docs/Kararlar.md` — K-074. `docs/Roadmap.md` — Faz 16 turu satırı (program açılırsa).
  `.claude/CLAUDE.md` dosya haritası — `jev/` satırı. `docs/Runbook.md` — gölge alarm kodu
  (varsa).
- `.gitignore` — `runs/jev/` zaten `runs/` altında; `data/semantik/` zaten `/data/` altında.
  Değişiklik gerekmiyor.

**Dokunulmayan** (bilerek): `strategy/`, `backtest/`, `risk/`, `execution/`, `oms/`,
`live/motor.py`, `live/evren_motor.py`, `exchange/`, `config/risk.json`, `config/maliyet.json`,
`research/gizli_tekrar.py`.

---

## Açık sorular — **cevaplandı (Scryne, 2026-09-19) → K-074**

| # | Karar |
| --- | --- |
| 1 | Yalnızca ölçüm; K-067 değişmez; B/C/D bu fazın dışında |
| 2 | 2026-09-10 **kabul edilmedi**; kesim UNKNOWN, kanıt Spike 7(c); geriye dönük türetim `leak_riski=true` |
| 3 | Minimal CI: mevcut takım + Jev snapshot/sızıntı/negatif/şema testleri |
| 4 | OI MVP dışı |
| 5 | Mevcut host, ayrı süreç/ledger/timeout, fail-closed |

Sorular (tarihsel kayıt):

1. **K-074 kapsamı:** Jev yönü yalnızca ölçüm mü (önerim), yoksa K-067 değiştirilip Exp. B/C
   için Jev-türevli strateji yolu açılsın mı?
2. **Kesim tarihi:** "sürüm çıkışı = 2026-09-10" varsayımı kabul mü; TypeSafe'e resmi beyan
   sorulsun mu?
3. **CI:** GitHub Actions workflow eklensin mi (Jev dışı dosya)?
4. **OI:** MVP dışı (canlı toplayıcı yok, arşiv T+1) — kabul mü, yoksa `openInterestHist`
   toplayıcısı ayrı bir iş olarak açılsın mı?
5. **Gölge host'u:** mevcut host'ta (192.168.1.4) ayrı süreç olarak mı, yerelde mi?
