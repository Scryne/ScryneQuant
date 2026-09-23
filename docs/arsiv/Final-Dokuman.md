---
proje: ScryneQuant
created: 2026-09-08
guncellendi: 2026-09-12
surum: 2
type: final-dokuman
status: aktif
---
# ScryneQuant — Final Doküman (v2)

> Bu dosya **bağlayıcı** olandır. `docs/arsiv/Proje-Fikri.md` (v1) ve `docs/arsiv/Proje-Fikri-v2.md`
> ile çeliştiği her yerde bu dosya geçerlidir. Kararların gerekçeleri `docs/Kararlar.md`'de,
> denetim bulguları `docs/arsiv/Denetim.md` (v1) ve `docs/arsiv/Denetim-v2.md`'de.
>
> **v2 (2026-09-12, K-048):** kapsam genişledi, çekirdek değişmedi. v1'in bütün kararları,
> testleri ve değişmez kuralları yürürlükte. Aşağıda "v1" diye işaretli olan her şey
> **kapanmış ve ölçülmüş** iştir, geçersiz kılınmış değil.

## Özet

ScryneQuant, birden fazla bilgi kaynağından (fiyat, türev, makro, olay) beslenen trading
hipotezlerini veri üzerinde araştıran, deterministik biçimde backtest eden, arama sayısını
sayarak düzelten, risk kurallarıyla sınırlandıran, paper trading ile doğrulayan ve ancak
yapısal kapılardan geçtikten sonra kontrollü biçimde otomatik uygulayan, tek kişilik ve tek
hesaplık bir **quant araştırma ve execution platformudur.**

Ürünün asıl çıktısı bir strateji değil, **bir stratejiye güvenilip güvenilemeyeceğini ölçen
altyapıdır.** Bu cümle v1'den beri aynı ve v2 onu değiştirmiyor — genişlettiği şey, güvenin
ölçüleceği bilgi kaynaklarının sayısı ve enstrüman evreninin genişliği.

## v1 neydi, ne oldu

> BTC/USDT spot verisini güvenilir biçimde toplayabilen, birkaç rule-based stratejiyi
> deterministik olarak backtest edebilen, işlem maliyeti ve slippage hesaplayabilen, risk
> kurallarını uygulayabilen ve aynı stratejileri gerçek zamanlı veri üzerinde paper trading
> ile çalıştırabilen bir platformun ilk üretilebilir sürümü.

**Kuruldu ve ölçtü.** Faz 0-7 kapandı (Faz 6'nın 30 günlük koşu kriteri K-055 ile Faz 8/14'e taşındı). Ölçtüğü
sonuç olumsuz ve bu bir başarısızlık değil: 38 hipotez denendi, hiçbiri promotion kapılarını
geçmedi; en iyi sonuç şans beklentisinin altında çıktı (K-044); maliyet sıfır kabul edilse
bile geçen olmadı (K-045). Tek sembollü yönlü arama bu ölçümle kapandı.

**v2 tam olarak buradan başlıyor:** altyapı çalışıyor ve "burada bir şey yok" diyebiliyor.
Eksik olan şey altyapı değil, **bakılan yerin darlığı**.

## v2'nin tanımı

Çok enstrümanlı (önce kripto evreni), çok bilgi kaynaklı (fiyat + türev + makro + olay),
point-in-time doğru, portföy kuran, arama sayısını fiyatlayan ve ikinci bir varlık sınıfına
açılabilir bir araştırma + execution platformu. Live trading yine **ardından** gelir ve
promotion kapılarından (K-010, K-019, K-054) geçmek zorundadır.

---

## Teknoloji Stack

| Katman | Seçim | Gerekçe |
| --- | --- | --- |
| Dil | Python 3.12 | Araştırma ekosistemi ve exchange kütüphaneleri burada |
| Veri işleme | pandas, numpy, pyarrow | Standart; Parquet için pyarrow zaten gerekli. **Polars alınmadı**: ölçülmüş bir darboğaz yok |
| Tarihsel veri | **Parquet** (zstd, deterministik yazıcı) | K-011. Spike 6 çok sembolde yeniden ölçtü: toplam ≈0,86 GB, en büyük dosya 2 MB — düzen değişmiyor. K-011'in öngördüğü DuckDB sorgu katmanı **hiç kullanılmadı** (bütün okuma pandas/pyarrow) ve R1(f) ile bağımlılıktan çıkarıldı (2026-09-20) |
| Operasyonel state | **SQLite (WAL)** | K-034. Çok sembollü çalışma 3. geri dönüş koşulunu tetikliyor → **Faz 9'da yeniden ölçülecek**, otomatik geçiş yok (K-052/6) |
| Backtest | **Kendi event-driven motorumuz** | K-001 — backtest = paper = live, tek kod yolu. Çok enstrümanlı motor ikinci motor değil, genişlemesidir (K-052/2) |
| Exchange | **CCXT** + Binance spot adapter | Adapter arkasında; venue değiştirilebilir kalsın (doküman §23) |
| Doğrulama | **Pydantic v2** | Sinyal / config / veri sözleşmelerinde tip garantisi |
| Zamanlama | **Windows Task Scheduler** (`tools/*.ps1`, S4U, çökmede yeniden başlatma) + koşturucu döngüleri | Celery/Redis/Temporal yok — K-011. APScheduler hiç kullanılmadı (W0 denetimi, 2026-09-20) |
| API | **FastAPI**, trader sürecinin içinde, **salt-okunur** | Yazma ucu yok (K-036, K-043); kill switch süreç dışından gelir (Faz 14) |
| Frontend | **Vite + React + TypeScript + Tailwind** | K-012, K-036 |
| Grafik | **lightweight-charts** | Mum ve equity curve |
| Log | **SQLite olay/audit tabloları** (zincir hash'li, append-only) + `typer.echo`/`.log` yönlendirmesi; logging çerçevesi yok | Prometheus/Grafana/Sentry yok; izleme Faz 14'te ölçülmüş ihtiyaca göre. structlog hiç kullanılmadı, R1(f) ile çıkarıldı |
| Test | **pytest** | Determinizm ve look-ahead testleri birinci sınıf |
| Paket yönetimi | **uv** + `uv.lock` | K-022 — K-009'un ortam kaydının kaynağı |
| Lint/format | **ruff** | `docs/` ve `research/` hariç |
| ML (Faz 13+, koşullu) | scikit-learn + gradient boosting | K-049. **PyTorch yok**; derin öğrenmenin bu veri ölçeğinde gerekçesi ölçülmedi |

**Koşullu olanlar (K-034 kalıbı — koşul gerçekleşince karar *yeniden verilir*, otomatik
kabul edilmez):** PostgreSQL, Redis, object storage, message bus, Docker, CI.

**Bilerek yok:** VectorBT (K-001), TimescaleDB, Kubernetes, mikroservis mimarisi (K-052/1),
ayrı feature store (K-001'in tek kod yolu online/offline parity'yi zaten veriyor).

---

## Mimari

Doküman v2 §6'nın akışı, v1'in hattının genişletilmiş hâli:

```
Kaynaklar → Ingestion/Doğrulama → Kanonik Veri (PIT) → Feature/Evren
        → Rejim → Strateji (Sinyal Niyeti) → Portföy Kurma
        → Risk Motoru (Onaylı Niyet) → OMS → Execution → Venue
        → Fill/PnL → Post-trade → Araştırma geri beslemesi
```

**Modüler monolith** (K-052/1). Doküman §19'un bileşenleri paketlere şöyle eşleniyor:

| Doküman bileşeni (§19) | Paket |
| --- | --- |
| Data Gateway | `exchange/`, `data/indirici.py` |
| Normalizer | `data/semalar.py`, `data/dogrulama.py`, (Faz 9: `instruments/`) |
| Feature Service | `features/` — online/offline parity K-001'den gelir |
| Research Engine | `research/` |
| Model Registry | (Faz 13, koşullu) |
| Signal Engine | `strategy/` |
| Portfolio Engine | `portfolio/` (Faz 10'da portföy kurma buraya) |
| Risk Engine | `risk/` |
| Execution Engine | `execution/`, `oms/` |
| Monitoring | `live/api.py` + `apps/web/` (Faz 14'te genişler) |
| Control Plane | `cli/`, `config/` |
| Audit Store | `risk/audit.py` |

```
scryne-quant/
├── src/scryne_quant/
│   ├── common/      # tipler, zaman (K-005), config, hash
│   ├── data/        # indirme, doğrulama, kalite (K-006), Parquet deposu, PIT gözlem (Faz 9)
│   ├── features/    # indikatörler, feature engine
│   ├── strategy/    # Strategy ABC, ctx (K-002), stratejiler
│   ├── backtest/    # event loop, fill (K-004), maliyet (K-007), metrikler
│   ├── risk/        # limitler, sizing, kill switch (K-008), promotion
│   ├── portfolio/   # pozisyon/exposure state; portföy kurma (Faz 10)
│   ├── oms/         # emir state machine, idempotency, mutabakat
│   ├── execution/   # execution engine + adapter arayüzü
│   ├── exchange/    # CCXT/Binance (strateji buraya erişemez — K-003)
│   ├── research/    # deney kaydı, kapılar, çoklu test, hipotez defteri
│   ├── live/        # canlı akış, paper/gözlem, toparlanma, API
│   └── cli/         # tek arayüz (K-012)
├── apps/web/        # dashboard SPA (K-036)
├── research/        # notebooks, spikes (git'e girmez)
├── tests/
└── docs/
```

### Değişmez mimari kurallar

Tercih değil, testle zorlanan kısıtlar. 1-6 v1'den, 7-10 v2'nin eklediği:

1. **Strateji I/O yapamaz.** `strategy/` paketi `exchange/`, `execution/`, ağ veya dosya
   sistemine erişemez. İmport grafiği testle taranır. (K-003, K-027)
2. **Strateji geleceği göremez.** `ctx` yalnızca t anına kadar keser. (K-002)
3. **Sinyal risk motorunu atlayamaz.** Execution'a giden tek yol onaylanmış niyettir. (K-032)
4. **Zaman UTC'dir; bar timestamp'i açılış zamanıdır.** (K-005)
5. **Fill bir sonraki barın açılışındadır.** (K-004)
6. **Aynı girdi aynı çıktıyı verir.** (K-009)
7. **Evren de geleceği göremez.** `ctx` t anında yalnızca o an listelenmiş ve evren kuralını
   t'ye kadarki veriyle sağlayan enstrümanları gösterir. (K-052/3, Spike 6)
8. **Enstrüman kimliği ticker değildir.** Kanonik kimlik geçerlilik aralığı taşır; kimlik
   kırılması işaretlenir. (K-052/4)
9. **Bar olmayan gözlemde kesme `available_time`e göredir**, `event_time`e göre değil;
   bilinmiyorsa gün sonuna yuvarlanır. (K-052/5)
10. **Otomasyon asimetriktir:** riski azaltan otomatik, izni artıran kapı + elle onay.
    (K-050)

### Strateji sözleşmesi

```
Strategy.on_bar(ctx) -> Signal | None            # tek enstrüman (v1)
Strategy.on_bar(ctx) -> HedefPortfoy | None      # evren (Faz 10)
```

`ctx`: t anına kadar kesilmiş salt-okunur görünüm + evren üyeliği + pozisyon durumu +
parametreler. Çıktı bir **emir değil niyettir**; exchange'e giden yol yoktur. Tek enstrüman,
evren sözleşmesinin özel hâlidir (K-052/2).

---

## Kapsam (v2)

**Var (kapalı ve ölçülmüş — v1):** kripto spot tek sembol veri temeli, indikatör/feature
motoru, 6 rule-based strateji + funding aileleri, deterministik backtest, maliyet modeli,
walk-forward/OOS, deney kaydı, risk motoru + 8 limit + kill switch, promotion kapıları,
çoklu test düzeltmesi, hipotez defteri, paper/gözlem koşusu, 4 sayfalık dashboard, audit,
testnet execution + emir/pozisyon mutabakatı, limit emri ve iptal.

**Var (v2'de açılıyor, roadmap sırasıyla):**

- Çoklu sembol kripto evreni, hayatta kalma yanlılığı olmadan (Spike 6, K-053)
- Kanonik enstrüman kimliği + PIT gözlem modeli + veri sözleşmeleri (Faz 9)
- Çok enstrümanlı motor + portföy kurma (Faz 10)
- Dört yeni doğrulama kapısı + PBO/DSR/kapasite metrikleri (Faz 11, K-054)
- Araştırma programları: cross-sectional, evren geneli türev, makro (Faz 12, K-051)
- Rejim motoru — filtrelenmiş, engelleyici, çekiliş sayılır (Faz 12, K-052)
- Haber/olay zekâsı ve ML — **koşullu**, bütçe ve kaynak spike'ına bağlı (Faz 13, K-049)
- Üretim sertleştirme: bağımsız kill switch, izleme, runbook, dayanıklılık (Faz 14)
- İkinci varlık sınıfı: US equities/ETF, spike'tan sonra (Faz 15, K-053)

**Yok (v2 dışı, gerekçesi K-048'de):** HFT, market making, mikro yapı alfası, **kaldıraç ve
kısa pozisyon**, perpetual ile işlem (bilgi kaynağı olarak kalır), opsiyon, BIST, alternatif
veri, çoklu kripto venue, mikroservisler, ML'de derin öğrenme.

**Mutlak yasak (hukuki, K-014):** başkasının parası, sinyal satışı/paylaşımı, copy trading,
ücretli erişim, kamuya açık servis.

---

## Araştırma programları ve arama bütçesi

v2'nin merkezinde bir aritmetik var: **her yeni hipotez promotion kapısını yükseltiyor**
(K-044: 31 çekilişte `oos_sharpe` sınırı 1,02). Bu yüzden yeni bilgi kaynakları serbestçe
denenmiyor; **program** olarak açılıyor (K-051):

1. Program kaydı deftere yazılır: gerekçe + kaynağın neden belirgin biçimde farklı olduğu
   (ölçüyle) + **azami çekiliş sayısı** + durma kuralı.
2. Bütçe dahil edildiğinde eşiğin nereye çıkacağının tahmini kaydedilir (kapı değil, uyarı).
3. Program biter, `sq lab coklu-test` yeniden koşar, gerçek eşik ölçülür.
4. Bütçe aşılmaz; aşmak yeni bir program kaydı ve yeni bir gerekçe ister.

Hipotez kimliği: (strateji, timeframe, veri hash'i, ızgara, seçim yöntemi, **evren tanımı**,
**portföy yöntemi**, **rejim tanımı**).

---

## Doğrulama kapıları

**Yürürlükte (K-019, gevşetilmez):** `oos_sharpe` ≥ 1,02 (K-044), `oos_is_orani` ≥ 0,50,
`wf_katman_basari` ≥ 0,60, `parametre_kararliligi` ≤ 0,35, `asgari_islem` ≥ 30,
`max_drawdown` ≤ 0,25, `stres_dayanikliligi` ≤ 0,15.

**Ekleniyor (K-054, eşikleri Faz 11'de kalibre edilecek):** `rejim_kararliligi`,
`evren_dayanikliligi`, `parametre_perturbasyonu`, `pbo`.

**Mutlak engeller:** `dirty` (K-009), `data_quality_warning` (K-006),
`gecici_maliyet_modeli` (K-021), **`leak_riski`** (K-049).

**Ölçülemeyen kapı geçilmiş sayılmaz.**

---

## Riskler ve doğrulamalar

| Risk (doküman §28) | Savunma | Nerede |
| --- | --- | --- |
| Look-ahead bias | `ctx` sözleşmesi + bozulmuş-gelecek testi | K-002, Faz 2 |
| …evren üzerinden | PIT evren üyeliği + listeleme bozma testi | K-052/3, Faz 9-10 |
| …LLM eğitim verisi üzerinden | Kesim tarihi kuralı + `leak_riski` engeli | K-049/4 |
| Backtest overfit | Walk-forward, OOS, kapılar, PBO | K-010, K-019, K-054 |
| Data snooping | Hipotez defteri, ön kayıt, ölçülmüş düzeltme, arama bütçesi | K-039, K-044, K-051 |
| Survivorship bias | Delist dahil evren; ölçülen büyüklük: ayda medyan %18 | Spike 6, K-052/3 |
| Corporate action / kimlik | Kanonik kimlik + kırılma tespiti (LUNAUSDT vakası) | K-052/4, Faz 9 |
| Maliyetin hafife alınması | Kalibre slippage + stres senaryoları + tavan testi | K-007, K-021, K-045 |
| Regime shift | Rejim motoru + bozulma izleme | Faz 12, Faz 14 |
| Execution failure | Emir state machine + mutabakat + halt | K-040, K-041, K-046 |
| Model drift | Drift izleme + yeniden eğitim kapıları | Faz 13-14 (ML açılırsa) |
| Operasyonel kesinti | Kill switch + devre kesiciler + toparlanma | K-008, K-038, Faz 14 |
| API anahtarı sızıntısı | Sır ayrımı, en az yetki, çekim kapalı, IP allowlist | Faz 14, Faz 8 ön koşulu |
| Sabırsızlık / erken live | Promotion kapıları + kaldırılamaz elle onay + kademeli sermaye | K-010, K-050 |
| Regülasyon | Kendi hesabı / kendi parası + venue statüsü doğrulaması | K-014, Faz 8 ön koşulu |

---

## Bütçeler (doküman §27) — **açık**

Üç bütçe ayrı tutulur ve trading sermayesi diğer ikisini görünmez biçimde karşılamaz:

| Bütçe | Durum | Neyi belirler |
| --- | --- | --- |
| Araştırma | **açık** | Zaman; program sayısı |
| Veri / altyapı | **açık** | Faz 13 (haber arşivi) ve Faz 15 (US equity verisi) açılabilir mi |
| Risk sermayesi | **açık** | Faz 8'in ilk kademesinin büyüklüğü (K-050/3) |

Bu sayılar yalnızca Scryne'dan gelebilir. Gelene kadar Faz 13 ve 15 **açılmaz**; Faz 8 ise
zaten promotion'u geçen bir strateji bekliyor.

---

## Başarı ölçütü

Bu proje **net PnL ile ölçülmez.** v2 başarılı sayılır eğer:

1. Bir hipotez fikirden ölçülmüş sonuca kadar tek bir komutla götürülebiliyorsa,
2. Aynı backtest altı ay sonra bit düzeyinde yeniden üretilebiliyorsa,
3. Bir strateji promotion kapılarını elle müdahale olmadan geçemiyorsa,
4. Paper trading 30 gün kesintisiz çalışıp restart sonrası state'i doğru toparlıyorsa,
5. Bir araştırma programı **kaç çekiliş yaptığını ve bunun eşiğe ne yaptığını** baştan
   biliyorsa,
6. Ve **kötü stratejilerin çoğu bu sistem tarafından eleniyorsa.**

Altıncısı asıl olandır. Bir quant altyapısının değeri kazandırdığı işlemlerde değil,
**yaptırmadığı işlemlerde** ölçülür. v1 bunu 38 hipotezde yaptı; v2'nin işi aynı şeyi daha
geniş bir evrende, daha fazla bilgi kaynağıyla ve sayacı bozmadan yapmak.
