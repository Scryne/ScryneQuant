---
proje: ScryneQuant
created: 2026-09-08
type: final-dokuman
status: aktif
---
# ScryneQuant — Final Doküman

> Bu dosya **bağlayıcı** olandır. `docs/Proje-Fikri.md` ile çeliştiği her yerde bu dosya
> geçerlidir. Kararların gerekçeleri `docs/Kararlar.md`'de, denetim bulguları
> `docs/Denetim.md`'de.

## Özet

ScryneQuant, kripto spot piyasasında trading hipotezlerini veri üzerinde araştırmak,
deterministik biçimde backtest etmek, risk kurallarıyla sınırlandırmak, paper trading ile
doğrulamak ve ancak yapısal kapılardan geçtikten sonra kontrollü biçimde otomatik uygulamak
için geliştirilen, tek kişilik ve tek hesaplık bir quant araştırma ve execution
platformudur. Ürünün asıl çıktısı bir strateji değil, **bir stratejiye güvenilip
güvenilemeyeceğini ölçen altyapıdır.**

## v1'in tanımı (§61'den)

> BTC/USDT spot verisini güvenilir biçimde toplayabilen, birkaç rule-based stratejiyi
> deterministik olarak backtest edebilen, işlem maliyeti ve slippage hesaplayabilen, risk
> kurallarını uygulayabilen ve aynı stratejileri gerçek zamanlı veri üzerinde paper trading
> ile çalıştırabilen bir platformun ilk üretilebilir sürümü.

Live trading bunun **ardından** gelir ve promotion kapılarından (K-010) geçmek zorundadır.

---

## Teknoloji Stack

| Katman | Seçim | Gerekçe |
| --- | --- | --- |
| Dil | Python 3.12 | Araştırma ekosistemi (pandas, numpy) ve exchange kütüphaneleri burada |
| Veri işleme | pandas, numpy, pyarrow | Standart; ayrıca Parquet için pyarrow zaten gerekli |
| Tarihsel veri | **Parquet dosyaları + DuckDB** | K-011 — sunucu süreci yok, hash'lenebilir, sürümlenebilir |
| Operasyonel state | **PostgreSQL** (Faz 5+) | Emir/pozisyon/audit için transaction ve dayanıklılık gerekli |
| Backtest | **Kendi event-driven motorumuz** | K-001 — backtest = paper = live, tek kod yolu |
| Exchange | **CCXT** + Binance spot adapter | Adapter arkasında; borsa değiştirilebilir kalsın |
| Doğrulama | **Pydantic v2** | Signal / config / veri sözleşmelerinde tip garantisi |
| Zamanlama | **APScheduler** (tek proses) | Celery/Redis/Temporal v1'de yok — K-011 |
| API | **FastAPI** (Faz 6+) | Dashboard'la birlikte gelir, öncesinde gerekmez |
| Frontend | **Next.js + TypeScript + Tailwind + shadcn/ui** (Faz 6+) | K-012 |
| Grafik | **lightweight-charts** | Mum ve equity curve'ün ikisini de yapar; tek kütüphane |
| Log | **structlog** (JSON) + Postgres audit tablosu | Prometheus/Grafana/Sentry v1'de yok |
| Test | **pytest** | Determinizm ve look-ahead testleri birinci sınıf |
| Paket yönetimi | **uv** + `uv.lock` | Kilitli sürümler; K-009'un ortam kaydının kaynağı |
| Lint/format | **ruff** | `docs/` ve `research/` hariç |
| Notebook | Jupyter (yalnızca araştırma) | Notebook'tan production koduna içe aktarma yok, tersi var |

**v1'de bilerek yok:** VectorBT, TimescaleDB, Redis, Celery, Temporal, Docker, Prometheus,
Grafana, Sentry, Kubernetes, ML/LLM katmanı. Gerekçeler: K-001, K-011, K-013.

---

## Mimari

Veri akışı, Proje-Fikri §2.2'deki hattı korur:

```
Market Data → Ingestion/Validation → Historical Store → Feature Engine
           → Strategy (Signal Intent) → Risk Engine (Approved Intent)
           → Portfolio/OMS → Execution → Exchange Adapter
```

**Modüler monolith** (§32 kabul edildi). Tek Python paketi, içeride sert modül sınırları:

```
scryne-quant/
├── src/scryne_quant/
│   ├── common/        # tipler, zaman (K-005), config, hash yardımcıları
│   ├── data/          # indirme, doğrulama, kalite bayrakları (K-006), Parquet deposu
│   ├── features/      # indikatörler, feature engine
│   ├── strategy/      # Strategy ABC, ctx sözleşmesi (K-002), stratejiler
│   ├── backtest/      # event loop, fill modeli (K-004), maliyet modeli (K-007), metrikler
│   ├── risk/          # limitler, sizing, kill switch (K-008)
│   ├── portfolio/     # pozisyon ve exposure state
│   ├── oms/           # emir state machine, idempotency
│   ├── execution/     # execution engine + exchange adapter arayüzü
│   ├── exchange/      # CCXT/Binance adapter (strategy buraya erişemez — K-003)
│   ├── research/      # deney kaydı, promotion kapıları (K-010)
│   └── cli/           # Faz 1-5'in tek arayüzü (K-012)
├── apps/web/          # Faz 6'da açılır
├── research/          # notebooks, experiments, datasets (git'e girmez)
├── tests/
└── docs/
```

### Değişmez mimari kurallar

Bunlar tercih değil, testle zorlanan kısıtlardır:

1. **Strateji I/O yapamaz.** `strategy/` paketi `exchange/`, `execution/`, ağ veya dosya
   sistemine erişemez. Import grafiği testle taranır. (K-003)
2. **Strateji geleceği göremez.** `ctx` yalnızca t anına kadar keser; t sonrası veri
   bozulduğunda sonuç değişmemelidir. (K-002)
3. **Sinyal risk motorunu atlayamaz.** Execution'a giden tek yol Risk Engine'in
   onayladığı intent'tir. Strateji "emir" değil "niyet" üretir. (§9.1, §10)
4. **Zaman UTC'dir.** Bar timestamp'i açılış zamanıdır. (K-005)
5. **Fill bir sonraki barın açılışındadır.** (K-004)
6. **Aynı girdi aynı çıktıyı verir.** Aynı veri + config + seed = bit düzeyinde aynı sonuç.

### Strateji sözleşmesi

```
Strategy.on_bar(ctx) -> Signal | None
```

`ctx`: t anına kadar kesilmiş salt-okunur görünüm + pozisyon durumu + parametreler.
`Signal`: `{symbol, side, target_exposure, confidence, reason, timestamp}` — emir değil
niyet (§10). Exchange'e giden yol yoktur.

---

## Kapsam (v1)

**Var:**
- Kripto **spot**, tek borsa (Binance), başlangıçta tek sembol (BTC/USDT)
- Tarihsel veri indirme, doğrulama, kalite raporu
- İndikatör/feature motoru
- Rule-based strateji ailesi: SMA/EMA crossover, RSI mean reversion, breakout, momentum
- Deterministik event-driven backtest; fee + slippage modeli
- Performans metrikleri, equity curve, trade listesi
- Walk-forward ve out-of-sample doğrulama
- Deney kaydı ve reproducibility (K-009)
- Risk motoru: sizing, exposure limiti, günlük zarar limiti, drawdown limiti, kill switch
- Promotion kapıları (K-010)
- Paper trading (gerçek zamanlı veri, simüle emir)
- 4 sayfalık dashboard (K-012)
- Audit log

**Yok (v1 dışı):** HFT, kaldıraç, futures, opsiyon, borsalar arası arbitraj, market making,
çoklu borsa, ML/LLM, copy trading, müşteri hesabı, saklama, kamuya açık servis.

**Mutlak yasak (hukuki):** başkasının parası, sinyal satışı/paylaşımı, ücretli erişim.
(K-014)

---

## Riskler ve Doğrulamalar

| Risk | Savunma | Nerede |
| --- | --- | --- |
| Look-ahead bias | ctx sözleşmesi + bozulmuş-gelecek testi | K-002, Faz 2 |
| Overfitting | Walk-forward, OOS, promotion kapıları | K-010, Faz 4 |
| Gerçekçi olmayan fill | t+1 açılış + aleyhte slippage | K-004, K-007 |
| Veri boşluğu | Kalite bayrakları + backtest engeli | K-006 |
| Reproduce edilemezlik | Commit + hash + seed kaydı, dirty engeli | K-009 |
| Duplicate order | Idempotency key + emir state machine | Faz 7 |
| State desync | Reconciliation + halt | Faz 7 |
| Risk motoru bypass | Import grafiği testi | K-003 |
| Sabırsızlık / erken live | Promotion kapıları, kaldırılamaz elle onay | K-010 |
| Saat kayması | UTC-only + clock drift kontrolü | K-005 |
| Regülasyon | Kendi hesabı / kendi parası kuralı | K-014 |

**Faz 0'da doğrulandı (2026-09-08).** Dört spike da kapandı; raporlar `docs/spikes/`
altında, gerekçeler `docs/Kararlar.md`'de:

| Bilinmeyen | Sonuç |
| --- | --- |
| Binance erişimi ve testnet (K-015) | Coğrafi engel yok; rate limit darboğaz değil; testnet ayakta |
| Fee/slippage (K-016) | `fee_taker_bps = 10.0` ölçüldü; slippage Faz 1'e devredildi (K-021) |
| Veri hacmi ve birincil timeframe (K-017) | **1h** — 5 yıl = 1,66 MB, 1000 parametrelik tarama 25 sn |
| Saklama (K-011) | Parquet+zstd + DuckDB doğrulandı; parquet yazımı bit düzeyinde deterministik |

**Faz 0'ın stack'e getirdiği düzeltmeler:**

- **CCXT yerinde kalıyor**, iki ayarla: `load_markets()` önbelleğe alınır (3,2 s sürüyor,
  4.619 marketin tamamını çekiyor) ve kapanmışlık kontrolü `open_time + timeframe` üzerinden
  bizde hesaplanır. *Faz 1 düzeltmesi (K-023):* tarihsel barlar `fetch_ohlcv` ile değil,
  ccxt'nin ham `publicGetKlines` ucuyla çekiliyor — `fetch_ohlcv` `quote_volume` ve `trades`
  alanlarını düşürüyor, ikisi de `BAR_SEMASI`'nda zorunlu.
- **Kapanmamış bar depoya yazılmaz.** REST her zaman devam eden barı son eleman olarak
  döndürüyor ve o bar çağrılar arasında değişiyor — atılmazsa Faz 1'in idempotency
  kriteri sağlanamaz.
- **Veri seti hash'i = Parquet dosyasının SHA-256'sı** (K-009 için ayrı bir mekanizma
  gerekmiyor).
- **Bağımlılıklar `uv` + `uv.lock` ile kilitli** — K-009'un istediği kütüphane sürümü
  kaydının tek doğruluk kaynağı.

---

## Başarı ölçütü

Bu proje **net PnL ile ölçülmez.** v1 başarılı sayılır eğer:

1. Bir hipotez fikirden ölçülmüş sonuca kadar tek bir komutla götürülebiliyorsa,
2. Aynı backtest altı ay sonra bit düzeyinde yeniden üretilebiliyorsa,
3. Bir strateji promotion kapılarını elle müdahale olmadan geçemiyorsa,
4. Paper trading 30 gün kesintisiz çalışıp restart sonrası state'i doğru toparlıyorsa,
5. Ve **kötü stratejilerin çoğu bu sistem tarafından eleniyorsa.**

Beşincisi asıl olandır. Bir quant altyapısının değeri kazandırdığı işlemlerde değil,
**yaptırmadığı işlemlerde** ölçülür.
