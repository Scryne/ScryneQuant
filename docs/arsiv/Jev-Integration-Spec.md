# ScryneQuant — Jev Integration Specification

> **Document Type:** Engineering / Research Architecture Specification
> **Project:** ScryneQuant
> **Status:** Proposed
> **Version:** 2.0.0
> **Scope:** Jev-style LLM decision layer integration
> **Primary Goal:** Measure whether Jev adds reproducible, statistically defensible value to ScryneQuant without giving the LLM uncontrolled trading authority.

---

# 1. Document Purpose

Bu dokümanın amacı, ScryneQuant içerisine **Jev tarzı bir LLM karar katmanının** nasıl güvenli, ölçülebilir, yeniden üretilebilir ve denetlenebilir şekilde entegre edileceğini tanımlamaktır.

Bu doküman doğrudan bir AI coding agent'a verilebilir.

Agent'ın görevi yalnızca kod yazmak değildir.

Agent:

1. mevcut repository'yi incelemeli,
2. mevcut mimariyi anlamalı,
3. mevcut veri ve backtest altyapısını yeniden kullanmalı,
4. Jev entegrasyonunu minimum gerekli değişiklikle kurmalı,
5. leakage ve reproducibility testleri yazmalı,
6. Jev kararlarını kalıcı olarak kaydetmeli,
7. baseline ile karşılaştırmalı,
8. negatif sonuçları da raporlamalı,
9. Jev'in gerçekten katkı sağlayıp sağlamadığını ölçmeli.

## Temel ilke

> **Jev yeni olduğu için sisteme eklenmez. Jev'in ölçülebilir ve tekrarlanabilir bir katkı sağladığı gösterilebilirse sisteme eklenir.**

Jev bir:

* araştırma katmanı,
* karar destek katmanı,
* sinyal / rejim değerlendirme katmanı

olarak ele alınmalıdır.

Jev başlangıçta:

* risk motorunun,
* position sizing'in,
* stop-loss'un,
* execution'ın,
* circuit breaker'ların

otoritesi değildir.

---

# 2. Kritik Mimari Prensip

Sistem aşağıdaki ayrımı korumalıdır:

```text
Market Data
     │
     ▼
Data Validation
     │
     ▼
Feature / State Builder
     │
     ▼
Canonical Market State
     │
     ▼
Jev State Builder
     │
     ▼
Jev Decision Engine
     │
     ▼
Typed Decision
     │
     ▼
Decision Gate
     │
     ▼
Deterministic Risk Engine
     │
     ▼
Execution Engine
```

Audit/logging sistemi bu zincirin tamamını gözlemlemelidir.

```text
                    ┌─────────────────────┐
                    │    Audit / Ledger    │
                    │                     │
                    │ state               │
                    │ state hash          │
                    │ prompt/request      │
                    │ raw response        │
                    │ parsed decision     │
                    │ risk decision       │
                    │ execution            │
                    │ outcome              │
                    └─────────────────────┘
```

## Kesin sınır

Jev:

```text
direction
confidence
regime
setup quality
horizon
analytical factors
```

gibi karar desteği üretir.

Jev doğrudan:

```text
BUY 0.43 BTC
SELL 2.1 ETH
use 7x leverage
risk 3%
set stop at X
```

gibi emir veya bağımsız risk kararı veremez.

---

# 3. Mevcut Repository Önceliği

Agent entegrasyona başlamadan önce repository'yi denetlemelidir.

## Zorunlu audit

Aşağıdakiler bulunmalı:

* mevcut data collectors
* canonical market data modelleri
* feature hesaplama sistemi
* strategy interface'leri
* signal interface'leri
* backtest engine
* execution engine
* risk engine
* configuration sistemi
* secrets yönetimi
* persistence / database
* logging
* test altyapısı
* mevcut experiment kayıtları
* mevcut state / run metadata sistemi

## Önemli

Agent mevcut mimariyi anlamadan yeni:

```text
data/
features/
execution/
logging/
```

klasörleri yaratmamalıdır.

Eğer repository'de aynı sorunu çözen abstraction zaten varsa yeniden yazmak yerine mevcut abstraction kullanılmalıdır.

Amaç:

> **minimum duplication + maksimum mevcut altyapı kullanımı**

---

# 4. Entegrasyon Modları

Jev entegrasyonu aşağıdaki modlara sahip olmalıdır:

```text
DISABLED
SHADOW
PAPER
LIVE
```

## DISABLED

Jev hiçbir karar üretmez.

## SHADOW

Jev gerçek market state'i görür ve karar üretir.

Fakat:

```text
order = 0
```

Jev kararları yalnızca kaydedilir.

Bu ilk entegrasyon modu olmalıdır.

## PAPER

Jev kararları gerçek execution yerine simulated execution'a gönderilir.

Gerçek piyasa verisi kullanılabilir.

## LIVE

Jev kararlarının gerçek execution pipeline'ına girmesine izin verilir.

Bu mod varsayılan olmamalıdır.

LIVE için ayrıca:

* insan onayı,
* risk limitleri,
* kill switch,
* veri tazeliği kontrolü,
* model/schema doğrulaması,
* failure handling

zorunludur.

---

# 5. Veri Katmanı

Jev'in kalitesi doğrudan kendisine verilen context'in kalitesine bağlıdır.

Bu nedenle Jev entegrasyonunun ilk problemi LLM değil, **market state üretimidir.**

---

# 6. Canonical Market State

Jev'e doğrudan dağınık API response'ları gönderilmemelidir.

Önce deterministic bir:

```text
CanonicalMarketState
```

üretilmelidir.

Bu state:

* timestamped,
* versioned,
* deterministic,
* serializable,
* hashable,
* reproducible

olmalıdır.

Örnek:

```json
{
  "symbol": "BTCUSDT",
  "decision_timestamp": "2026-01-01T12:00:00Z",
  "timeframes": {},
  "technical": {},
  "structure": {},
  "derivatives": {},
  "cross_market": {},
  "macro": {},
  "onchain": {},
  "sentiment": {}
}
```

Gerçek schema repository'nin mevcut modellerine göre belirlenmelidir.

---

# 7. Veri Grupları

İkinci dokümandaki kapsam genişletmesi korunmalıdır; ancak bütün kaynaklar ilk aşamada zorunlu değildir.

## 7.1 Price / Technical

Desteklenebilen zaman dilimleri:

```text
1m
5m
15m
1h
4h
1d
```

Alanlar:

* OHLCV
* RSI
* MACD
* EMA
* SMA gerekiyorsa
* ATR
* VWAP
* support / resistance
* swing highs
* swing lows
* market structure
* volatility
* volume structure

Önemli:

Bir timeframe'deki kapanmamış candle, gelecekteki OHLC bilgisini içermemelidir.

---

# 8. Multi-Timeframe Context

Jev'e yalnızca tek timeframe verilmemelidir.

Örneğin:

```text
1h → execution context
4h → intermediate structure
1d → higher timeframe regime
```

şeklinde context oluşturulabilir.

Ancak timeframe'lerin anlamı deney protokolünde açıkça tanımlanmalıdır.

Örneğin:

```text
decision timeframe = 1h
higher timeframe = 4h + 1d
```

gibi.

Agent timeframe eklemeden önce bunun:

* mevcut data availability,
* backtest cost,
* sample size,
* latency

üzerindeki etkisini kontrol etmelidir.

---

# 9. Derivatives Context

Mümkün olduğunda:

* funding rate
* open interest
* futures basis
* long/short ratio
* taker buy/sell flow
* liquidation data

kullanılabilir.

Ancak veri kaynağında timestamp problemi varsa veri kullanılmamalıdır.

Özellikle:

```text
scrape_time != market_observation_time
```

olabilir.

Bu iki zaman birbirine karıştırılmamalıdır.

---

# 10. Cross-Market / On-Chain

İleri aşamada:

* ETH/BTC
* futures basis
* stablecoin supply
* stablecoin supply change
* hashrate
* block fees
* diğer cross-asset relationships

eklenebilir.

Bunlar MVP'nin zorunlu parçası değildir.

Her yeni veri grubu ayrı experiment olarak değerlendirilmelidir.

---

# 11. Macro

İleri aşamada:

* Fed funds rate
* 2Y yield
* 10Y yield
* 2s10s spread
* DXY
* Fed balance sheet

gibi macro context eklenebilir.

Macro verilerde kritik problem:

> Verinin ekonomik olarak gözlemlendiği tarih ile piyasaya gerçekten erişilebilir hâle geldiği tarih aynı olmayabilir.

Bu nedenle mümkünse:

```text
observed_at
published_at
available_at
```

ayrı tutulmalıdır.

Backtest yalnızca karar zamanında gerçekten erişilebilir olan bilgiyi kullanmalıdır.

---

# 12. News / Sentiment

Kullanılabilecek alanlar:

* haber başlıkları
* Fear & Greed
* Wikipedia attention
* sentiment metrics

Ancak:

```text
article published_at
```

esas alınmalıdır.

Scrape zamanı:

```text
scraped_at
```

haber yayın zamanı yerine kullanılamaz.

Gelecekte yayınlanmış bir haber geçmiş karara kesinlikle gösterilemez.

Timestamp'i doğrulanamayan haber:

```text
EXCLUDE
```

edilmelidir.

---

# 13. Zaman Disiplini — ZORUNLU

Her market observation en az:

```text
observed_at
```

taşımalıdır.

Kaynak destekliyorsa ayrıca:

```text
published_at
available_at
ingested_at
```

saklanmalıdır.

Karar zamanı:

```text
t
```

ise yalnızca:

```text
available_at <= t
```

olan bilgi kullanılabilir.

Basit durumda:

```text
observed_at <= t
```

kuralı uygulanır.

---

# 14. Look-Ahead Leakage

Kesinlikle yasaktır.

Aşağıdakiler leakage örneğidir:

* kapanmamış candle'ın gelecekteki high/low değerini kullanmak
* gelecekteki funding bilgisini kullanmak
* haberin daha sonra yayınlanan versiyonunu geçmişe koymak
* future macro revision kullanmak
* gelecekte oluşacak support/resistance bilgisini geçmiş snapshot'a dahil etmek
* future OHLC ile normalize edilmiş feature kullanmak
* backtest sırasında tüm dataset üzerinde fit edilmiş scaler kullanmak

---

# 15. Leakage Testi

Agent aşağıdaki testi yazmalıdır:

```text
test_no_lookahead_leakage:

1. t zamanı seç.
2. t anındaki canonical snapshot'ı üret.
3. snapshot_A olarak serialize et.
4. t sonrasındaki tüm verileri sil / görünmez yap.
5. aynı t için snapshot_B üret.
6. snapshot_A == snapshot_B kontrol et.
```

Tercihen:

```text
byte-identical
```

olmalıdır.

Bu test CI'a bağlanmalıdır.

---

# 16. Decision Timestamp

Her Jev kararı:

```text
decision_timestamp
```

taşımalıdır.

Ayrıca:

```text
data_cutoff
```

bulunmalıdır.

Örneğin:

```json
{
  "decision_timestamp": "...",
  "data_cutoff": "..."
}
```

Bu iki kavram birbirine otomatik olarak eşit varsayılmamalıdır.

---

# 17. Snapshot Hash

Canonical state deterministic biçimde serialize edildikten sonra hash üretilmelidir.

Örneğin:

```text
SHA-256(canonical_state)
```

sonucu:

```text
state_hash
```

olarak kaydedilir.

Amaç:

Aynı decision tekrar üretildiğinde gerçekten aynı input'un kullanılıp kullanılmadığını kontrol edebilmektir.

---

# 18. Jev Decision Engine

Decision Engine şu görevleri yapmalıdır:

1. canonical state'i almak
2. Jev input schema'sını oluşturmak
3. versioned prompt oluşturmak
4. modeli çağırmak
5. response'u validate etmek
6. typed decision'a çevirmek
7. karar metadata'sını oluşturmak
8. audit log'a kaydetmek

---

# 19. Model Provider Abstraction

Provider/model adı kodun içine gelişigüzel hardcode edilmemelidir.

Repository'nin config sistemine göre:

```text
provider
model
temperature
max_tokens
timeout
retry_policy
```

yönetilebilir olmalıdır.

Jev'in gerçekten hangi API/provider üzerinden kullanılacağı repository auditinden sonra belirlenmelidir.

---

# 20. Structured Output

Jev'den serbest metin yerine yapılandırılmış çıktı alınmalıdır.

Örnek:

```json
{
  "direction": "LONG | SHORT | FLAT",
  "confidence": 0.0,
  "horizon": "1h",
  "regime": "TREND | RANGE | HIGH_VOL | LOW_VOL | UNKNOWN",
  "setup_quality": "LOW | MEDIUM | HIGH",
  "key_factors": [
    "factor 1",
    "factor 2"
  ],
  "abstain": false
}
```

Gerçek enum'lar repository'deki domain modeline göre tanımlanmalıdır.

---

# 21. Confidence

`confidence`:

```text
0.0 → 1.0
```

aralığında tutulabilir.

Ancak:

> **confidence otomatik olarak gerçek olasılık değildir.**

Örneğin:

```text
confidence = 0.80
```

ifadesi:

```text
%80 kesin kazanır
```

şeklinde yorumlanamaz.

Bunun gerçekten olasılık anlamına gelip gelmediği ayrıca calibration experiment ile test edilmelidir.

---

# 22. Confidence Threshold

İkinci dokümanda örnek olarak:

```text
confidence < 0.55 → no trade
```

öneriliyor.

Bu değer ScryneQuant'ta **hardcoded gerçek olarak alınmamalıdır.**

Threshold:

* experiment,
* validation dataset,
* calibration,
* transaction cost,
* false-positive / false-negative trade-off

üzerinden belirlenmelidir.

Başlangıçta:

```text
threshold = configurable
```

olmalıdır.

---

# 23. Abstention

Jev yalnızca:

```text
LONG
SHORT
```

demeye zorlanmamalıdır.

Ayrıca:

```text
ABSTAIN
```

veya:

```text
NO_TRADE
```

üretebilmelidir.

Özellikle:

* context eksikse
* market regime belirsizse
* data stale ise
* confidence düşükse
* contradictory signals varsa

abstention geçerli bir sonuçtur.

---

# 24. Key Factors

Jev kısa açıklayıcı factor listesi döndürebilir:

```json
{
  "key_factors": [
    "4h trend structure bullish",
    "funding elevated",
    "OI increasing while price consolidates"
  ]
}
```

Bu alan:

* audit,
* debugging,
* post-analysis

için kullanılabilir.

Bu alan modelin gizli Chain-of-Thought'u değildir.

Tam reasoning / CoT istenmemelidir.

---

# 25. Risk Authority Separation

Bu mimarinin en önemli kurallarından biridir.

Jev:

```text
direction
confidence
regime
setup quality
```

üretir.

Risk Engine:

```text
position size
maximum exposure
stop distance
daily risk
drawdown protection
leverage limits
```

üretir.

Execution Engine:

```text
order type
quantity
price
exchange interaction
fill handling
```

üretir.

Böylece:

```text
LLM → intelligence
Risk Engine → risk
Execution Engine → execution
```

ayrımı korunur.

---

# 26. Stop-Loss

İkinci dokümandaki ATR yaklaşımı araştırılabilir:

```text
stop_distance = ATR(14) × multiplier
```

Ancak multiplier'ın Jev tarafından doğrudan belirlenmesi zorunlu değildir.

Öncelikli mimari:

```text
Jev
 ↓
direction / context
 ↓
Risk Engine
 ↓
ATR-based deterministic stop
```

şeklindedir.

Eğer ileride Jev'in stop önerisinin ek değer sağlayıp sağlamadığı test edilmek istenirse bu ayrı bir experiment olmalıdır.

Jev'in önerdiği değer doğrudan uygulanmamalıdır.

---

# 27. Position Sizing

Sizing deterministik olmalıdır.

Örneğin:

```text
base_risk
×
validated confidence scaling
×
risk constraints
```

gibi bir mekanizma kullanılabilir.

Fakat:

```text
LLM → "hesabın %8'ini kullan"
```

kabul edilmemelidir.

Hard limits:

```text
max_position_size
max_account_exposure
max_trade_risk
max_daily_loss
max_drawdown
```

Jev'den bağımsız uygulanmalıdır.

---

# 28. Execution Layer

Execution Engine LLM'den tamamen bağımsız olmalıdır.

Görevleri:

* order validation
* quantity calculation
* price calculation
* stop placement
* take profit
* trailing logic
* fill handling
* retry
* exchange errors
* position reconciliation

olabilir.

---

# 29. Exit Logic

İlk sürümde exit logic deterministic olmalıdır.

Araştırılabilecek mekanizmalar:

* ATR stop
* trailing stop
* time-based exit
* fixed R exits
* regime change exit
* confidence deterioration

Ancak bunların her biri ayrı deney olarak ölçülmelidir.

Jev'in art arda:

```text
FLAT
NO_TRADE
```

dönmesi otomatik olarak pozisyon kapatma sebebi yapılmamalıdır.

Bu davranış ayrıca test edilmelidir.

---

# 30. Circuit Breakers

Minimum olarak:

```text
daily loss limit
maximum drawdown limit
maximum position exposure
maximum order value
consecutive loss protection
API failure protection
stale data protection
model failure protection
```

olmalıdır.

Bir circuit breaker tetiklenirse:

```text
NO NEW TRADE
```

varsayılan davranıştır.

---

# 31. Failure Policy

Aşağıdaki durumlarda Jev kararı geçerli kabul edilmemelidir:

* API timeout
* provider error
* malformed JSON
* schema validation failure
* authentication error
* stale market state
* missing required feature
* invalid timestamp
* unknown model version
* state hash mismatch
* decision timestamp mismatch

Varsayılan:

```text
FAIL CLOSED
```

olmalıdır.

Yani:

> Hata varsa son Jev kararını tekrar kullanarak yeni işlem açma.

---

# 32. Retry Policy

Retry deterministik ve sınırlı olmalıdır.

Örneğin:

```text
max_retries = configurable
timeout = configurable
```

Retry sonrasında hâlâ hata varsa:

```text
NO_TRADE
```

---

# 33. Decision Record

Her Jev kararı kalıcı olarak kaydedilmelidir.

Minimum:

```json
{
  "decision_id": "...",
  "symbol": "BTCUSDT",
  "decision_timestamp": "...",
  "data_cutoff": "...",
  "state_version": "...",
  "state_hash": "...",
  "prompt_version": "...",
  "model_provider": "...",
  "model_version": "...",
  "direction": "...",
  "confidence": 0.0,
  "regime": "...",
  "setup_quality": "...",
  "latency_ms": 0,
  "status": "VALID"
}
```

---

# 34. Prompt Audit

Mümkün ve güvenli olduğu sürece:

* prompt version
* input state hash
* request metadata
* raw model response
* parsed response

saklanmalıdır.

Ancak:

* API key
* secret
* private credential

kesinlikle loglanmamalıdır.

Prompt logging içinde secret leakage kontrolü yapılmalıdır.

---

# 35. State + Decision + Outcome Linkage

Araştırma için üç şey birbirine bağlanmalıdır:

```text
STATE
  ↓
JEV DECISION
  ↓
FUTURE OUTCOME
```

Örneğin:

```text
decision at t
→ return after 1h
→ return after 4h
→ return after 24h
→ max adverse excursion
→ max favorable excursion
→ realized PnL
```

gibi sonuçlar daha sonra hesaplanabilir.

Outcome tanımları deney başlamadan önce belirlenmelidir.

---

# 36. Future Outcome Leakage

Outcome hesaplanırken gelecek verinin decision input'una geri sızması yasaktır.

Örneğin:

```text
decision_time = t
outcome = return(t → t+4h)
```

olabilir.

Ama `t+4h` bilgisi decision state'e kesinlikle giremez.

---

# 37. Trade Timing

Karar:

```text
candle t
```

üzerinde üretiliyorsa execution:

```text
candle t+1
```

başlangıcında veya tanımlı execution timestamp'inde gerçekleşmelidir.

Aynı candle'ın gelecekteki fiyatından işlem yapılmış gibi backtest yapılmamalıdır.

---

# 38. Backtest Architecture

Backtest ve canlı pipeline mümkün olduğunca aynı state builder'ı kullanmalıdır.

Yanlış:

```text
BacktestFeatureBuilder
LiveFeatureBuilder
```

ve iki farklı hesaplama mantığı.

Doğru:

```text
CanonicalStateBuilder
       │
 ┌─────┴─────┐
 ▼           ▼
Backtest     Live
```

Bu, sessiz leakage ve implementation drift riskini azaltır.

---

# 39. Walk-Forward Testing

Canlıya geçmeden önce:

```text
train / validation / test
```

veya uygun walk-forward yapısı kullanılmalıdır.

Örnek:

```text
[train][validation][test]
       →
   [train][validation][test]
              →
          ...
```

Jev promptu, threshold'u veya feature setini gelecekteki sonuçları gördükten sonra aynı test dönemine göre tekrar tekrar optimize etmek yasaktır.

---

# 40. Dry Run

Dry-run:

```text
real market data
+
real Jev decision
+
real feature pipeline
+
simulated execution
```

şeklinde çalışmalıdır.

Gerçek emir gönderilmez.

Bu modda:

* latency
* decision distribution
* signal frequency
* confidence
* theoretical fills
* slippage
* missed trades
* risk behavior

ölçülmelidir.

---

# 41. Transaction Costs

Backtest:

```text
fees
slippage
spread
latency
```

gibi maliyetleri mümkün olduğunca gerçekçi şekilde içermelidir.

Özellikle:

> Direction doğru olsa bile execution maliyeti nedeniyle strateji zarar edebilir.

Bu nedenle yalnızca:

```text
direction accuracy
```

ölçmek yeterli değildir.

---

# 42. Ölçülecek Metrikler

Minimum:

```text
total return
max drawdown
Sharpe
Sortino
win rate
average R multiple
profit factor
trade count
average trade
fees
slippage
latency
```

Ayrıca:

```text
MAE
MFE
holding time
signal frequency
abstention rate
```

ölçülebilir.

---

# 43. Jev Evaluation

Jev ayrı ayrı değerlendirilmeli:

### A. Directional accuracy

Jev yönü ne kadar doğru tahmin ediyor?

### B. Economic value

Bu doğruluk gerçekten PnL'e dönüşüyor mu?

### C. Calibration

Confidence ile gerçekleşen başarı arasında ilişki var mı?

### D. Regime dependence

Jev hangi market regime'lerinde farklı davranıyor?

### E. Incremental value

Mevcut baseline'ın üzerine gerçekten katkı sağlıyor mu?

---

# 44. Calibration

Confidence bucket'ları oluşturulabilir:

```text
0.50–0.55
0.55–0.60
0.60–0.65
...
0.90–0.95
0.95–1.00
```

Her bucket için:

```text
predicted confidence
vs
realized success
```

karşılaştırılabilir.

İleri aşamada:

```text
Brier score
calibration curve
ECE
```

gibi metrikler değerlendirilebilir.

---

# 45. Deney Matrisi

Jev tek başına test edilmemelidir.

Minimum:

## Experiment A — Baseline

```text
Existing ScryneQuant
```

## Experiment B — Jev Only

```text
Jev
```

## Experiment C — Baseline + Jev

```text
Baseline signal
+
Jev confirmation
```

## Experiment D — Jev as Filter

```text
Existing strategy
      +
Jev regime / risk filter
```

## Experiment E — Feature Ablation

```text
price only
price + technical
price + derivatives
price + derivatives + macro
price + derivatives + sentiment
...
```

Amaç:

> Jev gerçekten hangi bilgi grubundan fayda sağlıyor?

sorusunu araştırmaktır.

---

# 46. Negative Results

Agent:

* başarısız deneyleri silmemeli,
* kötü sonuçları gizlememeli,
* sadece başarılı run'ları raporlamamalı,
* benchmark'ı Jev lehine değiştirmemeli,
* test dönemini sonuçlara göre seçmemeli.

Başarısız sonuç:

```text
VALID RESEARCH RESULT
```

olarak saklanmalıdır.

---

# 47. Multiple Testing

Çok sayıda:

* prompt,
* threshold,
* feature,
* timeframe,
* symbol,
* model,
* exit rule

denemek tesadüfi başarı ihtimalini artırır.

Bu nedenle experiment registry tutulmalıdır.

Her experiment:

```text
experiment_id
hypothesis
dataset
period
features
prompt_version
model
parameters
metrics
result
```

ile kayıt altına alınmalıdır.

---

# 48. Prompt Versioning

Prompt değişiklikleri versiyonlanmalıdır.

Örneğin:

```text
prompt_v1
prompt_v2
prompt_v3
```

Aynı test:

```text
prompt_v1
```

ile çalıştırıldıysa daha sonra sonuçların hangi prompttan geldiği kesin olarak bilinmelidir.

---

# 49. Model Versioning

Aynı şekilde:

```text
provider
model
model_version
```

kaydedilmelidir.

Model değiştiğinde:

```text
aynı strateji
```

olarak kabul edilmemelidir.

Yeni model:

```text
new experiment
```

sayılmalıdır.

---

# 50. Reproducibility

Aynı:

```text
market state
model
prompt
configuration
```

ile mümkün olduğunca aynı karar tekrar üretilebilmelidir.

LLM deterministik değilse:

* seed destekleniyorsa seed,
* temperature,
* model version,
* request metadata,
* state hash

saklanmalıdır.

Amaç:

> Kararın neden ve hangi input ile üretildiğini sonradan yeniden inceleyebilmek.

---

# 51. Observability

Jev için minimum telemetry:

```text
request_count
success_count
failure_count
timeout_count
schema_error_count
average_latency
p50_latency
p95_latency
p99_latency
direction_distribution
confidence_distribution
abstention_rate
state_build_failures
stale_state_count
```

olmalıdır.

---

# 52. Jev Drift

Zaman içerisinde Jev'in davranışı değişebilir.

İzlenmesi gerekenler:

```text
direction distribution
confidence distribution
trade frequency
abstention rate
regime distribution
PnL contribution
latency
```

Model/provider değiştiğinde drift analizi yapılmalıdır.

---

# 53. Data Drift

Market data dağılımı da değişebilir.

Örneğin:

```text
volatility
volume
funding
OI
spread
correlation
```

dağılımları geçmiş dönemlerden farklılaşabilir.

Jev'in başarısı regime'e bağlıysa bu özellikle önemlidir.

---

# 54. Jev State Builder

Önerilen mantıksal yapı:

```text
Raw Market Data
      ↓
Validation
      ↓
Normalization
      ↓
Feature Engine
      ↓
Canonical State
      ↓
Jev State Builder
      ↓
Structured LLM Input
```

Jev'e doğrudan raw exchange response gönderilmemelidir.

---

# 55. State Builder Determinism

Aynı input dataset + aynı cutoff:

```text
→ aynı canonical state
```

üretmelidir.

Randomness varsa açıkça kontrol edilmelidir.

---

# 56. Eksik Veri

Bir feature yoksa:

```text
null
```

veya tanımlı bir missing state kullanılabilir.

Ancak:

```text
0
```

değerini otomatik olarak "veri yok" anlamında kullanmak tehlikelidir.

Jev'e:

```text
missing
unavailable
stale
```

durumları açıkça ifade edilmelidir.

---

# 57. Stale Data

Her veri kaynağı için freshness policy tanımlanmalıdır.

Örneğin:

```text
price → very short TTL
funding → source-specific TTL
macro → longer TTL
news → publication-based
```

Gerçek TTL'ler deney ve veri kaynağına göre belirlenmelidir.

Stale critical input:

```text
NO_TRADE
```

üretebilir.

---

# 58. Security

Agent:

* API key'leri source code'a yazmamalı,
* prompt loglarına secret koymamalı,
* `.env` dosyalarını commit etmemeli,
* production credentials'ı testlerde kullanmamalı,
* Jev'e exchange credentials göndermemeli.

Jev'in exchange account'a doğrudan erişimi olmamalıdır.

---

# 59. Binance / Exchange Ayrımı

Jev'in:

```text
exchange API
```

ile doğrudan konuşması gerekmemelidir.

Doğru:

```text
Exchange
   ↓
ScryneQuant Data Layer
   ↓
Canonical State
   ↓
Jev
```

Yanlış:

```text
Jev
 ↓
Binance API
 ↓
ORDER
```

---

# 60. Shadow Mode İlkesi

İlk gerçek entegrasyon:

```text
SHADOW
```

olmalıdır.

Örneğin:

```text
Market state
    ↓
Existing strategy
    ↓
Jev
    ↓
record only
```

Jev'in kararları mevcut botun davranışını değiştirmemelidir.

Bu aşamada şu sorular cevaplanır:

* Jev kaç karar üretiyor?
* Direction distribution nasıl?
* Confidence nasıl dağılıyor?
* Latency kabul edilebilir mi?
* Context oluşturma stabil mi?
* Leakage testi geçiyor mu?
* Schema hatası oluyor mu?
* Baseline ile Jev arasında nasıl bir ilişki var?

---

# 61. Paper Trading

Shadow sonuçları yeterli teknik güvence sağladıktan sonra:

```text
PAPER
```

moduna geçilebilir.

Paper mode gerçek execution davranışını simüle etmelidir.

Özellikle:

```text
spread
slippage
fees
latency
partial fill
```

gibi durumlar mümkün olduğunca hesaba katılmalıdır.

---

# 62. Live Gate

LIVE'e geçiş yalnızca:

```text
tests pass
+
leakage tests pass
+
reproducibility verified
+
paper run completed
+
risk limits active
+
kill switch tested
+
execution reconciliation tested
+
experiment evidence reviewed
```

şartları sağlandıktan sonra değerlendirilebilir.

Jev'in yalnızca birkaç başarılı trade üretmiş olması LIVE için yeterli kanıt değildir.

---

# 63. Önerilen Modül Yapısı

Repository auditinden sonra mevcut yapıya adapte edilmelidir.

Mantıksal olarak:

```text
data/
    collectors/
    validation/

features/
    indicators/
    market_structure/
    snapshot/

decision/
    jev/
        client
        prompt
        schema
        parser
        state_builder

risk/
    sizing
    stops
    limits
    circuit_breaker

execution/
    orders
    fills
    reconciliation

logging/
    decisions
    outcomes
    audit

backtest/
    replay
    walk_forward
    evaluation

experiments/
    registry
    reports
```

Gerçek klasör isimleri repository mimarisine göre değişebilir.

---

# 64. Agent Implementation Workflow

Agent aşağıdaki sırayı takip etmelidir.

## Phase 1 — Repository Audit

Kod değiştirme.

Şunları çıkar:

* mevcut architecture
* data sources
* existing feature system
* strategy flow
* risk flow
* execution flow
* persistence
* test structure

Çıktı:

```text
Jev Integration Audit
```

---

## Phase 2 — Integration Design

Kod değiştirmeden:

```text
existing flow
+
proposed Jev flow
```

çıkarılmalıdır.

Mevcut abstraction'lar yeniden kullanılmalıdır.

---

## Phase 3 — Canonical State

Önce:

```text
CanonicalMarketState
```

üretilmelidir.

Henüz LIVE Jev execution yapılmamalıdır.

---

## Phase 4 — Leakage Protection

Yaz:

```text
timestamp validation
cutoff validation
future-data exclusion
byte-identical snapshot test
```

---

## Phase 5 — Jev Adapter

Yaz:

```text
Jev client
request builder
schema validator
parser
timeout
retry
failure handling
```

---

## Phase 6 — Shadow Logging

Her Jev decision:

```text
state
state hash
prompt version
model
decision
confidence
latency
```

ile kaydedilmelidir.

---

## Phase 7 — Replay

Geçmiş market state'lerinden Jev replay sistemi kurulmalıdır.

Aynı pipeline:

```text
historical data
→ state
→ Jev
→ decision
```

üretmelidir.

---

## Phase 8 — Evaluation

Şunlar karşılaştırılmalıdır:

```text
Baseline
Jev
Baseline + Jev
```

---

## Phase 9 — Ablation

Veri grupları tek tek eklenerek test edilmelidir:

```text
price
→ technical
→ derivatives
→ cross-market
→ macro
→ sentiment
```

---

## Phase 10 — Paper

Gerçek veri + gerçek Jev + simulated execution.

---

## Phase 11 — Controlled Live

Yalnızca açıkça tanımlanmış risk limitleri altında.

---

# 65. Agent'ın Kesinlikle Yapmaması Gerekenler

Agent:

* Jev'i doğrudan Binance order API'sine bağlamamalı.
* LLM'e position size authority vermemeli.
* LLM'e leverage authority vermemeli.
* Risk limitlerini LLM'e bırakamamalı.
* Gelecek veriyi feature'a dahil etmemeli.
* Gelecek sonuçları görerek prompt optimize etmemeli.
* Başarısız experimentleri silmemeli.
* Baseline'ı Jev lehine değiştirmemeli.
* Sonuç iyi görünmesi için test dönemini seçmemeli.
* Hardcoded secret kullanmamalı.
* Schema validation olmadan response'u execution'a göndermemeli.
* API hatasında son kararı tekrar kullanarak işlem açmamalı.
* Eksik timestamp'i varsayımla doldurmamalı.
* Jev'in confidence değerini otomatik olarak gerçek probability kabul etmemeli.
* Birkaç başarılı işlemden sonra Jev'in "çalıştığını" ilan etmemeli.

---

# 66. Acceptance Criteria — Technical

Entegrasyon tamamlandı sayılmadan önce:

* [ ] Repository audit tamamlandı.
* [ ] Existing abstractions yeniden kullanıldı.
* [ ] Canonical state oluşturuluyor.
* [ ] State deterministic.
* [ ] State versioned.
* [ ] State hash üretiliyor.
* [ ] Timestamp validation mevcut.
* [ ] Look-ahead testleri mevcut.
* [ ] Future-data deletion sonrası snapshot byte-identical.
* [ ] CI leakage testini çalıştırıyor.
* [ ] Jev response schema validated.
* [ ] Timeout handling mevcut.
* [ ] Retry policy mevcut.
* [ ] Failure → no trade.
* [ ] Jev doğrudan execution yapamıyor.
* [ ] Risk Engine Jev'den bağımsız.
* [ ] Circuit breakers mevcut.
* [ ] Audit log mevcut.
* [ ] Model version kaydediliyor.
* [ ] Prompt version kaydediliyor.
* [ ] Decision ID mevcut.
* [ ] Outcome linkage mevcut.
* [ ] Historical replay mevcut.
* [ ] Walk-forward evaluation mevcut.
* [ ] Dry-run mevcut.
* [ ] Transaction costs hesaba katılıyor.

---

# 67. Acceptance Criteria — Research

Canlıya geçmeden önce:

* [ ] Baseline tanımlı.
* [ ] Jev-only experiment tanımlı.
* [ ] Baseline + Jev experiment tanımlı.
* [ ] Jev-as-filter experiment tanımlı.
* [ ] Confidence calibration ölçülebiliyor.
* [ ] Signal frequency ölçülebiliyor.
* [ ] Abstention ölçülebiliyor.
* [ ] Regime bazlı sonuçlar görülebiliyor.
* [ ] Transaction costs dahil.
* [ ] Negative results korunuyor.
* [ ] Experiment registry mevcut.
* [ ] Multiple testing etkisi dikkate alınıyor.
* [ ] Replay reproducibility doğrulanıyor.

---

# 68. Minimum Viable Jev Integration

İlk sürümde her şeyi eklemek zorunlu değildir.

Önerilen başlangıç:

```text
BTCUSDT
1h
4h
OHLCV
technical indicators
market structure
funding
open interest
```

ve:

```text
SHADOW MODE
```

İlk hedef:

> Jev'in güvenilir şekilde state okuyup yapılandırılmış karar üretmesi ve bu kararların geçmişte/gerçekte ölçülebilir şekilde kaydedilmesi.

Macro, on-chain, news ve geniş cross-sectional universe daha sonra eklenebilir.

---

# 69. Genişletme Sırası

Önerilen araştırma sırası:

```text
Stage 1
Price + Technical
        ↓
Stage 2
Market Structure
        ↓
Stage 3
Derivatives
        ↓
Stage 4
Multi-Symbol / Cross-Sectional
        ↓
Stage 5
Macro
        ↓
Stage 6
On-chain
        ↓
Stage 7
News / Sentiment
```

Her stage:

```text
new data
→ new experiment
→ compare
→ document
```

şeklinde ilerlemelidir.

---

# 70. Neden Bu Sıra?

Daha fazla veri otomatik olarak daha iyi model anlamına gelmez.

Yeni veri:

* noise,
* latency,
* missingness,
* timestamp complexity,
* overfitting,
* multiple testing

getirebilir.

Bu nedenle:

> Her yeni feature grubunun incremental value'su ölçülmelidir.

---

# 71. Nihai Sistem

Uzun vadede hedeflenen sistem:

```text
                 ┌─────────────────────┐
                 │     Market Data     │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Data Validation     │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Feature Engine      │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Canonical State     │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Jev Decision Layer  │
                 │                     │
                 │ direction           │
                 │ confidence          │
                 │ regime              │
                 │ setup quality       │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Decision Gate       │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Deterministic Risk  │
                 │ Engine              │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Execution Engine    │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Exchange            │
                 └─────────────────────┘
```

Ve bütün zincir:

```text
                    ┌──────────────────┐
                    │ Audit / Research │
                    │ Ledger           │
                    └──────────────────┘
```

tarafından kayıt altına alınmalıdır.

---

# 72. Nihai Tasarım İlkeleri

ScryneQuant + Jev entegrasyonunun temel prensipleri:

### 1. Intelligence ≠ Risk

Jev analiz yapar.

Risk Engine riski kontrol eder.

### 2. Risk ≠ Execution

Risk Engine izin verilen işlemi tanımlar.

Execution Engine emri gerçekleştirir.

### 3. Prediction ≠ Profit

Doğru yön tahmini tek başına kârlılık kanıtı değildir.

### 4. Confidence ≠ Probability

Confidence calibration yapılmadan probability olarak yorumlanamaz.

### 5. More Data ≠ Better Strategy

Her yeni veri incremental value açısından test edilmelidir.

### 6. Backtest ≠ Proof

Backtest yalnızca belirli bir tarihsel örnek üzerindeki performanstır.

### 7. New Model ≠ New Alpha

Jev'in yeni olması tek başına alpha ürettiği anlamına gelmez.

### 8. Failure ≠ Bug

Jev'in bazı deneylerde başarısız olması değerli bir araştırma sonucudur.

### 9. Reproducibility > Impression

Sonuç tekrar üretilemiyorsa güvenilir araştırma sonucu değildir.

### 10. Safety First

LLM hiçbir zaman:

```text
risk limit
position size
leverage
exchange authority
```

üzerinde sınırsız yetkiye sahip olmamalıdır.

---

# 73. Agent'a Son Talimat

Bu dokümanı uygularken:

> **Önce repository'yi incele, sonra değiştir.**

Kod yazmadan önce mevcut mimariyi çıkar.

Her değişiklik:

```text
implement
→ test
→ verify
→ document
```

döngüsünden geçsin.

Jev entegrasyonunu mevcut sistemin üzerine kontrolsüz bir ikinci bot olarak kurma.

Mevcut ScryneQuant mimarisiyle bütünleşen:

```text
State
→ Decision
→ Risk
→ Execution
→ Outcome
```

zinciri oluştur.

Her aşamada:

* determinism,
* timestamp correctness,
* leakage resistance,
* provenance,
* reproducibility,
* testability,
* risk isolation

korunmalıdır.

Sonuç ne olursa olsun raporla.

Jev başarılı olursa neden başarılı olduğunu ölç.

Jev başarısız olursa neden başarısız olduğunu ölç.

**Amaç Jev'i başarılı göstermek değil; Jev'in ScryneQuant'a gerçekten ölçülebilir bir katkı sağlayıp sağlamadığını bulmaktır.**
