# W1 — Architecture (Mimari Denetimi)

**Tarih:** 2026-09-20 · **Baseline:** `1e1a05b` (+ `423c28d` W0 dokümanı) · **Kod değişikliği:** yok
**Yöntem:** bağımlılık grafiği `src/scryne_quant` üzerinde AST ile çıkarıldı (import ifadeleri,
dinamik import yok); sorumluluklar modül docstring'lerinden ve giriş noktalarından okundu; iddialar
kodla çapraz kontrol edildi. Test kapsamı burada yalnız "hangi modül bir testten import ediliyor"
düzeyinde; "test neyi kanıtlıyor" W6'nın işi. Etiketler: **VERIFIED / PARTIAL / UNKNOWN / RISK**.

---

## 1. Paket bağımlılık grafiği (VERIFIED, AST)

Ok yönü "A → B: A, B'yi import eder". Sayı = import ifadesi adedi.

```
                 ┌──────────────────────────── cli (5.332 sl) ────────────────────────────┐
                 │  data 14 · exchange 12 · jev 13 · live 21 · research 16 · risk 9 · …   │
                 └───────┬──────────┬──────────┬──────────┬──────────┬────────────────────┘
                         ▼          ▼          ▼          ▼          ▼
   ┌── research ──┐  ┌── live ──────────────────────┐  ┌── jev ─────────────┐
   │ backtest 16  │  │ backtest 6 · risk 12         │  │ common 12 · data 1 │
   │ strategy 22  │  │ strategy 8 · data 11         │  │ exchange 1 · feat 1│
   │ data 6       │  │ exchange 3 · execution 1     │  │ live 2 (Bar tipi)  │
   └──────┬───────┘  │ portfolio 2 · features 1     │  └────────────────────┘
          │          └──────┬───────────────┬───────┘
          ▼                 ▼               ▼
   ┌── backtest ──┐   ┌── execution ──┐  ┌── exchange ──────────┐
   │ strategy 8   │   │ exchange 3    │  │ live 2 (Bar/Kaynak)  │
   │ risk 4       │   │ oms 2         │  │ data 2 · oms 1       │
   │ portfolio 3  │   │ risk 2        │  │ common 3             │
   │ data 1 feat 1│   └───────┬───────┘  └──────────────────────┘
   └──────┬───────┘           ▼
          ▼             ┌── oms ────┐
   ┌── risk ───┐        │ exchange 2│
   │ strategy 4│        │ risk 1    │
   │ features 1│        └───────────┘
   └─────┬─────┘
         ▼
   ┌── strategy ──┐        ┌── data ──────────┐
   │ features 18  │        │ exchange 4       │
   └─────┬────────┘        │ strategy 1 (enum)│
         ▼                 └──────────────────┘
   ┌── features ──┐  ┌── portfolio ──┐  ┌── common ──┐
   │ data 1 (şema)│  │ strategy 1    │  │ (yaprak)   │
   └──────────────┘  └───────────────┘  └────────────┘
```

**Kural doğrulamaları (import düzeyi):**

| Kural | Durum | Kanıt |
| --- | --- | --- |
| K-003 Strateji I/O yapamaz | **VERIFIED** | `strategy/*` yalnız `features` (+ kendi içi) import ediyor; `data/exchange/live/risk` yok. `tests/unit/test_izolasyon.py` AST ile koruyor |
| K-032 Execution sinyale dokunamaz | **VERIFIED** | `execution/` ve `oms/` geçişli grafikte `strategy.sinyal` yok; `execution/kapi.py` yalnız `risk.niyet` (mühür doğrulama). `test_risk_bypass.py` AST ile koruyor |
| K-074 Jev işlem katmanına ulaşamaz | **VERIFIED** | `jev/*` → `common, data.depo, exchange.akis, features, live.akis/pencere`; `risk/execution/oms/strategy` **yok**. `test_jev_izolasyon.py` |
| Risk araştırmaya bağlı değil | **VERIFIED** | `risk/` → `common, features, strategy`; `research` yok. Eşik `PROMOTION_DRAWDOWN_KAPISI=0.25` `risk/limitler.py`de **kopya**, `test_risk_limitleri.py` eşitliği koruyor |

**Katman tersinmeleri (bilerek, belgelenmiş):** `exchange.akis → live.akis` (`Bar`, `Kaynak`,
`AkisHatasi`, `BarAkisi` protokolü tüketici tarafında tanımlı, `live/baslat.py` docstring'i gerekçeyi
veriyor). `data.izgara → strategy.evren` (tek bir sentinel `LISTELENMEDI`). Her ikisi de mimari
sorun değil ama isimlendirme yanıltıyor: "live" paketi bir sözleşme paketi gibi davranıyor → W8.

**`cli/` tanrı-modül:** 5.332 satır, 10 alt-uygulama, ~55 komut; her paketi import ediyor ve
`tools/faz*_*.py` betikleri gibi ölçüm mantığı taşıyor (`cli/testnet.py` `EmirMotoru`'nun **tek**
üretim-dışı çağırıcısı). Kabul edilebilir ama test edilebilirliği düşük → §6.

## 2. Üretim akışı (Market Data → … → Monitoring)

```
 Binance WS/REST ──► exchange/akis.py (BinanceBarAkisi)        [tek sembol, Faz 6]
                 ──► exchange/coklu_akis.py (birleşik WS)      [çok sembol, Faz 14]
                          │  Bar(kaynak=LIVE|REST_RESYNC|BACKFILL, kalite bayrakları K-006)
                          ▼
 live/akis.py  Tazelik (bayat-veri guard, K-028)  ─── engelleyen katman, izin vermez (K-037)
                          ▼
 live/pencere.py BarPenceresi (kayan pencere)  ·  live/izgara_toplayici.py ("t barı hazır" kararı)
                          ▼
 features/motor.py  (bildirimsel indikatör → numpy; nedensel, NaN-ısınmalı)
                          ▼
 strategy/baglam.py ctx (t'ye kesik)  →  strategy/temel.py  on_bar(ctx) → Sinyal | None
 strategy/evren.py  EvrenCtx (PIT üyelik)  →  PortfoyStratejisi → HedefPortfoy
                          ▼
 strategy/kurma.py  (skor → hedef ağırlık; yalnız evren yolu)
                          ▼
 risk/motor.py  RiskMotoru (limitler config/risk.json, durum, promotion zinciri)
        └─► risk/niyet.py  OnayliNiyet + risk/muhur.py HMAC mühür  |  Red → risk/audit.py (zincir hash SQLite)
                          ▼
 execution/kapi.py gonder(niyet)  ─ mührü YENİDEN doğrular, KabulKaydi döndürür ─ **borsaya gitmez**
                          ▼
 ┌─ paper/gözlem: live/motor.py PaperMotoru → backtest/fill.py (t+1 açılış, aleyhte slippage)
 │                → backtest/defter.py → portfolio/durum.py → live/depo.py (SQLite, tek dosya)
 ├─ evren paper:  live/evren_motor.py → backtest/coklu_motor.py CokluAdimci (AYNI motor)
 │                → live/evren_depo.py (SQLite)
 └─ testnet:      cli/testnet.py → execution/motor.py EmirMotoru → oms/defter.py (idempotency)
                  → exchange/emir_adaptoru.py → exchange/imzali.py (yalnız TESTNET_HOST)
                  → oms/mutabakat.py · oms/pozisyon.py (uyuşmazlıkta koşu durur)
                          ▼
 live/izleme.py (4 boyut + alarm) → live/api.py (FastAPI, **yalnız GET**, süreç içi)
 live/evren_pano.py (ayrı salt okunur süreç) → apps/web (React) · ntfy.sh alarm
 live/kill.py (süreç dışı kill switch, Faz 14) · live/toparlanma.py (yeniden üretim, K-038)
```

### 2.1 Bulgu: canlı emir yolu **yok** (VERIFIED, tasarım gereği)

`EmirMotoru`'nu üretimde çağıran tek yer `cli/testnet.py` (4 ölçüm komutu). `PaperMotoru` ve
`EvrenPaperMotoru`, `execution/kapi.gonder`e kadar gider; `gonder` mührü doğrulayıp
`KabulKaydi` döndürür, ardından **simüle fill** üretilir. `exchange/imzali.py` canlı host'u
bilerek tanımlamıyor (`#: Canlı host bilerek burada tanımlı değil`). Yani:

- "Sinyal → risk → execution" sözleşmesi uçtan uca **var ve testli**;
- "execution → gerçek borsa emri" bağlantısı **PaperMotoru/EvrenPaperMotoru için mevcut değil**,
  yalnız testnet ölçüm CLI'sında var.

Faz 8 açıldığında yapılacak iş bir "toggle" değil, `PaperMotoru`'nun fill adımını
`EmirMotoru`'na bağlayan **yeni kod** + shadow adımı (`docs/Faz-8-Hazirlik.md`). Bu, W7 için
"Restricted Live = BLOCKED (kod yok)" anlamına gelir. Olumlu tarafı: kazara canlıya gitmek
yapısal olarak imkânsız (anahtar da yok, `.env.example` §Faz 8).

### 2.2 Bulgu: iki canlı motor, tek backtest çekirdeği (PARTIAL)

| Motor | Döngü | Fill/defter | Risk | Depo |
| --- | --- | --- | --- | --- |
| `live/motor.py PaperMotoru` (tek sembol, Faz 6) | **kendi** döngüsü | `backtest.fill.emir_hazirla` + `backtest.defter.uygula` (paylaşılan primitifler) | `RiskMotoru` | `live/depo.py` |
| `live/evren_motor.py EvrenPaperMotoru` (çok sembol, Faz 14) | `CokluAdimci` (backtest motorunun adım nesnesi) | `coklu_motor` içinden | `RiskMotoru` | `live/evren_depo.py` |
| `backtest/motor.py Backtest` (tek sembol) | `CokluBacktest` sarmalayıcısı (K-057, statik testli) | `coklu_motor` | `RiskMotoru` | `runs/deneyler` JSON |

K-001'in "backtest = paper = live, tek kod yolu" iddiası **evren yolunda tam** (aynı `CokluAdimci`),
**tek sembol paper yolunda kısmi** (primitifler paylaşılıyor, döngü ayrı). `live/evren_sapma.py`
"canlı koşu girdileri baştan bilseydi" karşılaştırmasıyla bunu ölçüyor (Faz 14) — ölçüm sonucu
W7'de okunacak. Tek sembollü `PaperMotoru`'nun `EvrenPaperMotoru`'nun özel hâli olup olmadığı
**açık soru**; iki depo şeması (`live/depo.py` vs `live/evren_depo.py`) ve iki toparlanma yolu
var → W8 çift soyutlama adayı.

## 3. Araştırma akışı (Historical Data → Research → Backtest → Validation → Registry)

```
 data.binance.vision ──► exchange/binance_arsiv.py ──► data/arsiv_indirici.py (plan, checksum, manifesto, idempotent)
 Binance REST         ──► data/indirici.py (sayfalama, devam)
                                   ▼
 data/depo.py ParquetDepo  (sembol/timeframe başına tek zstd Parquet; SHA-256 = veri kimliği K-009)
 data/dogrulama.py (kalite bayrakları K-006) · data/semalar.py
 data/kimlik.py Enstruman(kanonik_id, venue, sembol, [başlangıç,bitiş), kırılma)  (K-052/4)
 data/evren.py PIT aylık üyelik tablosu (K-052/3)  ·  data/pit.py available_time kesmesi (K-052/5)
 data/funding.py · data/makro.py (ALFRED vintage) · data/konumlanma.py · data/sozlesme.py (kaynak sözleşmesi)
                                   ▼
 data/izgara.py  ortak bar ızgarası + PIT üyelik matrisi  →  research/evren_kosu.py
                                   ▼
 backtest/coklu_motor.py CokluBacktest  (risk motoru dahil; fill t+1; maliyet MaliyetModeli)
 backtest/sonuc.py Sonuc (veri hash + config hash + ortam kaydı → sonuc_hash)
                                   ▼
 research/bolme.py (IS/OOS, walk-forward) · research/tarama.py (ızgara) · research/walkforward.py
 research/degerlendirme.py (K-019 kapıları) · research/evren_degerlendirme.py (11 kapı)
 research/kapilar.py (v1 eşikler; COKLU_TEST_ESIGI=1.04, CEKILIS=43) · research/kapilar_v2.py (K-054)
 research/pbo.py (CSCV) · research/dsr.py · research/rejim.py · research/evren_dayaniklilik.py
 research/coklu_test.py / coklu_test_evren.py (çoklu test düzeltmesi, null dağılım)
 research/perturbasyon.py · research/analiz.py (Monte Carlo/stres) · research/karsilastirma.py
                                   ▼
 research/hipotez.py  → docs/Hipotez-Defteri.jsonl (52, append-only, ön kayıt K-039)
 research/program.py  → docs/Arastirma-Programlari.jsonl (10, arama bütçesi K-051)
 research/gizli_tekrar.py (Jev ile benzerlik uyarısı, K-061; engellemez)
 research/deney.py / tekrar.py  → runs/deneyler/*.json (yeniden üretim)
```

**Bulgu (RISK, W3'e):** `sonuc_hash` sembol dosyalarının SHA-256'sını ve OOS penceresi veri
sonunu taşıdığı için depoyu uzatmak geçmiş çekilişleri yeniden üretilemez yapıyor — K-080
taslağının gerekçesi (W0 U1). Veri seti kimliği "içerik" değil "içerik + son bar"; bu, çoklu
varlıkta (farklı kaynakların farklı bitişleri) daha da kırılgan olur.

**Bulgu (RISK, W3'e):** `research/kapilar.py` `COKLU_TEST_CEKILIS_SAYISI = 43`, defter 52
kayıt (45 ölçülebilir). Eşik bayat; bekçi test sabit dosyayı okuduğu için yakalamıyor (state.json
kendisi bunu söylüyor).

## 4. Jev akışı (VERIFIED, yalnız gölge)

```
 exchange/akis.py BinanceBarAkisi ──► jev/golge.py (kapanmış 1h bar → live/pencere.py)
                                          ▼
 jev/durum.py  kanonik durum (betimleyici, t'de kesik, PENCERE_BAR=1200, 4h 1h'den; byte-identical sızıntı testi)
 jev/sorular.py  donmuş 4 soru (SORU_SHA256)  →  jev/istemci.py (TypeSafe SDK, tek istemci, sır taraması)
                                          ▼
 jev/karar.py JevKarari (extra=forbid, olasılık+marj, fail-closed)  →  jev/defter.py (SQLite zincir hash, runs/jev/)
 jev/tekrar.py replay → data/semantik/jev/<turetim_id>/ (dondurulmuş, her kayıt leak_riski)
 jev/sonuc.py ileri sonuç (open[t+1], ufuk 1/4/24) + kalibrasyon  ←  config/jev.json
```

- `jev/` → `risk/execution/oms/strategy` **import yok**; `Sinyal` üreten fonksiyon yok (K-067).
- Dış bağımlılık: `typesafe_sdk` (yalnız `jev/istemci.py` ve `cli/jev.py`).
- Zaman sınırı: kesim tarihi `null` (UNKNOWN, K-074/3) — W5.

## 5. Modül tablosu

Sütunlar: sorumluluk · girdi → çıktı · kalıcılık · doğrudan test · durum. "Doğrudan test" = bir
test dosyası modülü import ediyor (AST/regex); **dolaylı kapsam sayılmadı** (örn. `kutuphane/*`
stratejileri `test_strateji.py`/`test_laboratuvar.py` kayıt defterinden geçiyor).

| Paket / modül | Sorumluluk | Girdi → Çıktı | Kalıcılık | Test | Durum |
| --- | --- | --- | --- | --- | --- |
| `common/zaman, hash, maliyet` | UTC ms; SHA-256/config/ortam; `MaliyetModeli` | — | `config/maliyet.json` | ✅ | VERIFIED |
| `data/depo` | Parquet depo, idempotent yazım | DataFrame ↔ `data/market|evren/*.parquet` | Parquet+zstd | ✅ | VERIFIED |
| `data/arsiv_indirici` | arşivden çok sembol, checksum, manifesto | Binance arşiv → depo + `1h.kaynak.json` | Parquet/JSON | ✅ | VERIFIED (+K-080 taslağı commit dışı) |
| `data/indirici` | REST tarihsel indirici | REST → depo | Parquet | ✅ | VERIFIED |
| `data/dogrulama, semalar` | kalite bayrakları, bar şeması | DF → bayraklar | — | ✅ | VERIFIED |
| `data/kimlik` | kanonik enstrüman + kırılma | DF → `Enstruman[]` | `_evren/` JSON | ✅ | VERIFIED — **yalnız `VENUE_BINANCE_SPOT`** |
| `data/evren, pit` | PIT üyelik, `available_time` kesmesi | depo → aylık tablo | Parquet | ✅ | VERIFIED |
| `data/izgara` | ortak ızgara + üyelik matrisi | çok DF → numpy | — | ✅ | VERIFIED — **sürekli 24/7 ızgara varsayımı** |
| `data/funding, makro, alfred, konumlanma, sozlesme` | türev/makro/konumlanma katmanları, kaynak sözleşmesi | REST/ALFRED → PIT depo | Parquet/JSON | funding/makro/konumlanma ✅, alfred ❌, sozlesme ✅ | PARTIAL |
| `data/kalibrasyon` | slippage kalibrasyonu (K-021) | 1m barlar → bps | `config/maliyet.json` | ✅ | VERIFIED — BTCUSDT'ye özgü |
| `features/*` | nedensel indikatörler, özellik motoru | numpy → numpy | — | ✅ | VERIFIED |
| `strategy/baglam, temel, sinyal` | `ctx`, `Strateji`, `Sinyal` sözleşmeleri | ctx → Sinyal | — | ✅ | VERIFIED |
| `strategy/evren, hedef, kurma` | evren ctx, `HedefPortfoy`, ağırlık kurma | ctx → HedefPortfoy | — | ✅ | VERIFIED |
| `strategy/kutuphane/*` (16) | 6 aile + evren kıyas/dışlama/kurma | — | — | dolaylı | VERIFIED (kayıt defteri testi) |
| `backtest/coklu_motor` | çok enstrümanlı event loop (**tek motor**) | ızgara + strateji + risk → Sonuc | `runs/deneyler` JSON | ✅ | VERIFIED |
| `backtest/motor` | tek sembol sarmalayıcı (kendi döngüsü yok, statik test) | — | — | ✅ | VERIFIED |
| `backtest/fill, defter, metrikler, sonuc` | t+1 fill, defter, metrikler, `sonuc_hash` | — | JSON | fill/metrikler ✅, defter/sonuc dolaylı | VERIFIED |
| `risk/motor, niyet, muhur, durum, limitler` | onayın tek üretildiği yer; HMAC mühür; limitler | Sinyal/HedefPortfoy → OnayliNiyet/Red | `config/risk.json`, `runs/audit.sqlite` | ✅ (bypass, limit, portföy) | VERIFIED |
| `risk/promotion` | zincir: backtest→…→elle onay→live | kayıt → aşama | SQLite | ✅ | VERIFIED — LIVE aşamasına ulaşan kayıt yok |
| `risk/audit` | silinemez zincir-hash defter | karar → satır | SQLite | ✅ | VERIFIED |
| `risk/kalibrasyon` | limitlerin veriden kalibrasyonu | barlar → öneri | — | dolaylı | PARTIAL |
| `execution/kapi` | mühür yeniden doğrulama, `KabulKaydi` | OnayliNiyet → KabulKaydi | — | ✅ | VERIFIED — **borsaya gitmez** |
| `execution/motor` | `EmirMotoru`: niyet → emir, belirsizlik, iptal | niyet → GonderimSonucu | `oms/defter` SQLite | ✅ | VERIFIED — yalnız `cli/testnet` çağırıyor |
| `oms/emir, defter, mutabakat, pozisyon` | state machine, idempotency, mutabakat (durdurucu) | — | SQLite | ✅ | VERIFIED (testnet ölçümleriyle) |
| `exchange/temel, binance, kurallar, hatalar` | adaptör sözleşmesi, Binance spot, sembol kuralları | — | — | ✅ | VERIFIED — tek venue |
| `exchange/akis, coklu_akis` | WS + REST resync | WS → Bar | — | ✅ | VERIFIED |
| `exchange/imzali, emir_adaptoru` | imzalı istemci (yalnız testnet host) | emir → BorsaEmri | — | ✅ | VERIFIED — canlı host tanımsız |
| `exchange/binance_arsiv, turev_rest` | arşiv listesi/indirme; futures **veri** REST | — | — | arşiv ✅, turev_rest ❌ | PARTIAL |
| `live/akis, pencere, izgara_toplayici` | Bar sözleşmesi, tazelik, pencere, ızgara toplayıcı | — | — | ✅ | VERIFIED |
| `live/motor` `PaperMotoru` | tek sembol paper/gözlem döngüsü; `live` modunu reddediyor | Bar → karar → simüle fill | `live/depo` SQLite | ✅ | VERIFIED |
| `live/evren_motor, evren_kosturucu, evren_kurulum, evren_depo` | çok sembol paper (CokluAdimci) | — | SQLite | ✅ (kurulum dolaylı) | VERIFIED |
| `live/kosturucu, baslat, kilit, durdurma, toparlanma` | döngü, kurulum, tek yazıcı kilidi, düzgün durdurma, yeniden üretim | — | bayrak dosyası, SQLite | ✅ | VERIFIED |
| `live/kill` + `cli/kill` | süreç dışı kill switch (K-065) | — | — | ✅ (`test_kill_*`) | VERIFIED |
| `live/izleme, api, evren_pano` | 4 boyut + alarm; salt okunur FastAPI (10 GET); pano | — | — | ✅ | VERIFIED |
| `live/canli_evren, evren_yenileme, evren_sapma` | canlı PIT üyelik, aylık yenileme, canlı-backtest sapması | — | Parquet/JSON | ✅ | VERIFIED |
| `jev/*` (9) | gölge karar katmanı | Bar → JevKarari → defter | SQLite, `data/semantik` | ✅ (istemci sahte anahtarla) | VERIFIED — yalnız gölge |
| `research/*` (24) | §3 | — | `runs/`, `docs/*.jsonl` | çoğu ✅; `degerlendirme, kalibrasyon_v2, tekrar` doğrudan ❌ | PARTIAL |
| `cli/*` (5) | `sq` — 10 alt uygulama | — | — | `main` ✅ (3 dosya); `jev, kill, testnet, izle` doğrudan ❌ | PARTIAL |
| `portfolio/durum` | nakit/pozisyon/ort. maliyet | — | — | ✅ | VERIFIED |
| `apps/web` | React SPA, `live/api` tüketicisi; `tokens.css` DESIGN.md'den | — | — | yok | UNKNOWN (bu dalgada açılmadı) |

## 6. Çok varlıklı hedefe karşı mimari sınırlar (U4 cevabı)

Brief §15-17'nin istediği "instrument registry + multi-asset data layer" bugün **yok**; mevcut
soyutlamalar Binance spot'a şu noktalarda bağlı (hepsi VERIFIED, dosya:satır):

| Sınır | Nerede | Etki |
| --- | --- | --- |
| Enstrüman modeli | `data/kimlik.py:115` `Enstruman(kanonik_id, venue, sembol, geçerlilik, bar_sayisi, kırılma)` — `venue` var, ama `asset_class, instrument_type, tick/lot, calendar, fee/spread/financing modeli` **yok**; `venue` varsayılanı `VENUE_BINANCE_SPOT` | Registry sıfırdan değil, bu tipin genişlemesi olabilir; ama kimlik ≠ sözleşme ayrımı yapılmalı |
| Emir kuralları | `exchange/kurallar.py:46` `SembolKurallari(tick_size, step_size, min_notional, durum, taban, kote)` — Binance `exchangeInfo` biçimi | Lot/kontrat büyüklüğü, kaldıraç, marj yok |
| Maliyet modeli | `common/maliyet.py:55` **tek global** `MaliyetModeli(fee_taker_bps, slippage_bps)`; `config/maliyet.json` BTCUSDT 1m'den kalibre; `coklu_motor.py:79` motora **tek** nesne olarak giriyor — sembol başına maliyet yok | Çok varlıkta yanlış: FX spread, endeks CFD financing, futures rollover modellenemez. **Bu, "Slippage her zaman aleyhte" kuralının çok varlıkta uygulanabilmesi için ilk kırılması gereken yer** |
| Zaman ızgarası | `data/izgara.py:55` `adim = timeframe_ms(timeframe)` — sürekli, boşluksuz 24/7 ızgara; kimlik kırılması "eksik bar" ile tespit ediliyor (`kimlik.py:141`) | Seans/takvimli piyasalarda her hafta sonu "kırılma" sayılır; takvim soyutlaması yok |
| Veri kaynağı sözleşmesi | `data/sozlesme.py:28` `VeriSozlesmesi(ad, kaynak, şema, cadence, zaman semantiği, available_time, tamlık, revizyon, lisans, kanıt)` — **iyi bir başlangıç**, brief §17'nin provenance alanlarının çoğu var | Genişletilebilir; venue/instrument_type eksik |
| Adaptör | `exchange/temel.py` sözleşmesi + tek uygulama `BinanceAdaptoru`; futures yalnız veri (`turev_rest.py`) | İkinci venue eklemek sözleşmenin yeterliliğini ilk kez test eder |
| Funding/finansman | `data/funding.py` Binance perp funding'e özgü; motorda finansman/rollover bacağı yok (K-079 "eksik katman perp fee" bunu zaten kaydediyor) | Carry/basis ailesi ve CFD/futures için gerekli |

**Yorum (öneri, karar değil):** Registry işi `Enstruman` + `VeriSozlesmesi` + `SembolKurallari` +
`MaliyetModeli` dörtlüsünün **ayrıştırılıp** sembol başına bağlanmasıdır; sıfırdan model yazmak
mevcut kimlik/kırılma/PIT işini çöpe atar. Roadmap R2/R3'te bu dört dosya başlangıç noktası.

## 7. Kalıcılık haritası (VERIFIED)

| Depo | Biçim | Yazan | Git |
| --- | --- | --- | --- |
| `data/market/<S>/<tf>.parquet` (REST), `data/evren/<S>/1h.parquet` + `1h.kaynak.json` (arşiv) | Parquet+zstd, JSON | `data/depo`, `arsiv_indirici` | hayır |
| `data/evren/_evren/` PIT tablo + kimlik kataloğu | Parquet/JSON | `data/evren`, `data/kimlik` | hayır |
| `data/funding, makro, turev (3,9 GB), konumlanma, duyuru, semantik/jev` | Parquet/JSON | ilgili `data/*`, `jev/tekrar` | hayır |
| `runs/audit.sqlite` | SQLite WAL, zincir hash | `risk/audit` | hayır |
| `runs/paper/<koşu>.sqlite`, `runs/evren/…` | SQLite (kimlik+kontrol noktası+fill+olay+audit tek dosya) | `live/depo`, `live/evren_depo` | hayır |
| `runs/testnet/*.sqlite/json` | SQLite | `oms/defter`, `cli/testnet` | hayır |
| `runs/jev/<koşu>.sqlite` | SQLite zincir hash | `jev/defter` | hayır |
| `runs/deneyler, faz12, faz16, kalibrasyon-v2, promotion` | JSON | `research/deney`, `tools/*` | hayır |
| `docs/Hipotez-Defteri.jsonl`, `docs/Arastirma-Programlari.jsonl` | JSONL append-only | `research/hipotez`, `research/program` | **evet** |
| `config/risk.json, maliyet.json, jev.json` | JSON | elle / `sq risk kalibre` / `sq data slippage-kalibre` | evet |
| `migrations/001_faz5.sql` | SQL | — | evet, **uygulanmamış** |

Tek yazıcı ilkesi: `live/kilit.py` koşu dosyası başına kilit. Çok süreçli erişim (paper + pano +
Jev aynı makinede) salt okunur süreçlerle çözülmüş.

## 8. Hata modları (mimariden görünen; W2/W7 derinleştirir)

| Mod | Ele alınış | Kanıt |
| --- | --- | --- |
| Bayat veri / `ok` olmayan bar | eler, fill iddia etmez (K-028, K-037) | `live/akis.py Tazelik`, `live/baslat.py` docstring |
| WS kopması | REST resync (`REST_RESYNC` kaynağı) | `exchange/akis.py`, K-069 kesinti kaydı |
| Süreç ölümü | yeniden üretim + karşılaştırma, uyuşmazlıkta **durur** (K-038) | `live/toparlanma.py` |
| Aynı koşuya iki süreç | kilit | `live/kilit.py` |
| Mühür kırılması | `execution/kapi.gonder` reddeder | `risk/muhur.py` |
| Defter ≠ borsa | koşu durur | `oms/mutabakat.py`, `oms/pozisyon.py` |
| Duplicate emir | idempotency anahtarı | `oms/emir.py` |
| Saat kayması | `SaatEngeli` | `execution/motor.py:91` |
| Kill | süreç dışı bayrak/komut | `live/kill.py`, `cli/kill.py` |
| Sır sızıntısı | Jev istemci taraması; `.env` git dışı | `jev/istemci.py` |
| **Eksik:** canlı emir yolu, çok venue, takvim | — | §2.1, §6 |

## 9. Dokümantasyon durumu

Her modülün K-referanslı docstring'i var (istisnasız); mimari **koddan okunabilir**. Buna karşılık
`docs/Final-Dokuman.md` §Mimari 280 satırlık özet, ve §Stack'te en az bir yanlış (APScheduler,
W0). Kalıcı bir `docs/architecture/` dokümanı yok; bu W1 raporu onun ilk taslağı sayılabilir.
`requests`/`urllib3` doğrudan kullanılıyor (`cli`, `data`, `exchange`) ama `pyproject`te
bildirilmemiş (ccxt'nin geçişli bağımlılığı) — `aiohttp` için yazılan gerekçe bunlara da uygulanmalı
→ W8.

## 10. Sonraki dalgaya taşınanlar

| # | Soru | Dalga |
| --- | --- | --- |
| A1 | `PaperMotoru` ile `EvrenPaperMotoru` gerçekten aynı fill/risk semantiğini mi veriyor? `evren_sapma` sonucu ne? | W2, W7 |
| A2 | `execution/kapi.gonder` sonrası fill: mühür doğrulanan niyet ile fill'e giden niyet aynı nesne mi (araya kod giriyor mu)? | W2 |
| A3 | Tek global `MaliyetModeli`nin çok sembollü backtest'te (323 sembol) uygulanması: her sembole BTCUSDT slippage'ı — bu, Faz 10-16 sonuçlarını hangi yönde saptırır? | W3 |
| A4 | `sonuc_hash` ↔ veri sonu bağımlılığı (K-080 taslağı) | W3 |
| A5 | `COKLU_TEST_CEKILIS_SAYISI=43` bayatlığı | W3 |
| A6 | Jev kesim tarihi UNKNOWN'un pratik sonucu | W5 |
| A7 | Doğrudan testi olmayan `cli/{jev,kill,testnet,izle}`, `exchange/turev_rest`, `data/alfred`, `research/{degerlendirme,kalibrasyon_v2,tekrar}` — dolaylı kapsam var mı? | W6 |
| A8 | Çift depo/toparlanma yolu (`live/depo` vs `live/evren_depo`) birleştirilebilir mi? | W8 |

**Sonraki dalga:** W2 — Trading Engine + Risk + Execution (risk/execution kodu okunacak, değiştirilmeyecek).
