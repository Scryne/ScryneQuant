---
proje: ScryneQuant
created: 2026-09-08
type: proje-fikri
status: denetlendi
---

> **Not (2026-09-12):** Bu doküman **v1**'dir. 2026-09-12'de gelen ikinci konsept dokümanı
> (`docs/Proje-Fikri-v2.md`) projenin yürürlükteki vizyonudur ve kapsamı genişletir (K-048);
> bu dosya tarihsel kayıt olarak durur. Çelişkide sıra: Final-Doküman > Proje-Fikri-v2 >
> Proje-Fikri.
>
> **Not (2026-09-08):** Bu dosya Scryne'ın yazdığı özgün konsept dokümanının tamamıdır,
> içeriği değiştirilmemiştir. Denetim aşamasında bulunan çelişkiler ve eksikler
> `docs/Denetim.md` dosyasında; bunların sonucunda verilen nihai kararlar
> `docs/Final-Dokuman.md` ve `docs/Kararlar.md` dosyalarındadır. **Çelişki durumunda
> Final-Doküman geçerlidir**; bu dosya tarihsel kayıt ve gerekçe kaynağı olarak durur.

# SCRYNE QUANT
## Algorithmic Trading Research, Backtesting, Risk & Automated Execution Platform

**Belge türü:** Proje Fikri / Ürün Vizyonu / Teknik Konsept Dokümanı  
**Durum:** Concept / Pre-Development  
**Versiyon:** 1.0  
**Tarih:** 8 Eylül 2026  
**Ana yaklaşım:** Research-first, risk-first, execution-safe  
**İlk hedef pazar:** Crypto spot piyasaları; daha sonra genişletilebilir mimari  
**İlk çalışma modu:** Backtest → Paper Trading → Kontrollü Live Trading

---

## 1. Yönetici Özeti

Scryne Quant, piyasaları otomatik olarak analiz eden ve belirli bir stratejiye göre işlem kararları üretebilen klasik bir “trading bot”tan daha büyük bir sistem olarak tasarlanacaktır.

Projenin temel fikri şudur:

> **Bir yatırım/trading fikrini veri üzerinde araştırabilen, geçmişte test edebilen, gerçek zamanlı olarak izleyebilen, risk kurallarıyla sınırlandırabilen ve ancak güvenlik kapılarından geçtikten sonra otomatik emir gönderebilen modüler bir algoritmik trading platformu oluşturmak.**

Sistem tek bir stratejiye bağlı olmayacaktır. Bunun yerine veri toplama, veri doğrulama, feature/indicator üretimi, strateji çalıştırma, sinyal üretimi, portföy yönetimi, risk kontrolü, emir yürütme, gözlemleme ve sonuç analizi birbirinden ayrılmış modüller olarak tasarlanacaktır.

Bu yaklaşımın önemli sonucu şudur: Projenin amacı “her zaman para kazanan bir bot” üretmek değildir. Böyle bir garanti teknik veya bilimsel olarak gerçekçi değildir. Amaç; **hipotezleri sistematik biçimde test edebilen, başarısız stratejileri eleyecek kadar katı, gerçek hayattaki işlem maliyetlerini hesaba katacak kadar gerçekçi ve yanlış bir emir gönderildiğinde zararı sınırlayacak kadar güvenli bir quant altyapısı kurmaktır.**

İlk sürümde sistem crypto spot piyasasına odaklanacak ve gerçek para kullanmadan başlayacaktır. Stratejiler önce tarihsel veri üzerinde backtest edilecek, daha sonra gerçek zamanlı market verisi ile paper trading ortamında sınanacak ve ancak belirlenmiş kalite/güvenlik kriterlerini sağlayan stratejiler kontrollü live execution aşamasına geçirilecektir.

Binance gibi borsalar resmi test/demo ortamları sağlarken CCXT, birden fazla crypto exchange API'sini ortak bir arayüz üzerinden kullanmayı kolaylaştırmaktadır. Bu nedenle ilk sürümde exchange bağımlılığının bir abstraction katmanı arkasında tutulması planlanmaktadır. [Binance Testnet](https://www.binance.com/en/support/faq/detail/ab78f9a1b8824cf0a106b4229c76496d), [CCXT](https://docs.ccxt.com/docs/manual)

Sistem sadece execution katmanı olarak değil, aynı zamanda bir **quant research laboratory** olarak ele alınacaktır. Kullanıcı farklı stratejileri, parametreleri, zaman dilimlerini, varlıkları ve risk ayarlarını deneyebilecek; sonuçları karşılaştırabilecek; backtest ile paper/live sonuçlarını yan yana inceleyebilecektir.

---

# 2. Projenin Temel Fikri

## 2.1 Problem

Bir kişi trading öğrenmeye başladığında çoğu zaman şu sırayı izler:

```text
Bir indikatör öğrenir
        ↓
Al-sat kuralı yazar
        ↓
Bir script oluşturur
        ↓
Borsaya bağlar
        ↓
Gerçek parayla dener
```

Bu yaklaşım tehlikelidir çünkü aradaki bilimsel ve operasyonel katmanları atlar.

Gerçek bir trading sisteminde şu sorular cevaplanmalıdır:

- Veri güvenilir mi?
- Veride eksik veya bozuk dönem var mı?
- Strateji geçmişte gerçekten çalıştı mı?
- Çalışması sadece belirli parametrelerden mi kaynaklanıyor?
- Strateji başka bir dönem veya başka bir varlıkta da çalışıyor mu?
- Komisyonlar hesaba katıldığında sonuç ne oluyor?
- Slippage hesaba katıldığında ne oluyor?
- İşlem sayısı değiştiğinde sonuç stabil kalıyor mu?
- En kötü kayıp dönemi ne kadar?
- Sermayenin ne kadarı aynı anda risk altında?
- Borsaya emir gönderilmezse veya yanlış gönderilirse sistem ne yapacak?
- Market data akışı kesilirse bot yeni işlem açabilecek mi?
- Uygulama yeniden başlatıldığında açık pozisyonların durumunu nasıl toparlayacak?
- Backtest sonuçları ile canlı sonuçlar arasındaki fark nasıl ölçülecek?

Scryne Quant tam olarak bu boşluğu çözmek için tasarlanacaktır.

---

## 2.2 Çözüm

Sistem aşağıdaki ana pipeline üzerine kurulacaktır:

```text
                    ┌──────────────────────┐
                    │   MARKET DATA        │
                    │ Exchange / Feeds     │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ DATA INGESTION       │
                    │ Validation / Quality │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ HISTORICAL DATA      │
                    │ Time-series Storage  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ FEATURE ENGINE       │
                    │ Indicators / Factors │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ STRATEGY ENGINE      │
                    │ Rules / Models       │
                    └──────────┬───────────┘
                               │
                         Signal Intent
                               │
                               ▼
                    ┌──────────────────────┐
                    │ RISK ENGINE          │
                    │ Limits / Sizing      │
                    └──────────┬───────────┘
                               │
                        Approved Intent
                               │
                               ▼
                    ┌──────────────────────┐
                    │ PORTFOLIO / OMS       │
                    │ Position State       │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ EXECUTION ENGINE     │
                    │ Order Management     │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ EXCHANGE ADAPTERS    │
                    │ Binance / Others     │
                    └──────────┬───────────┘
                               │
                               ▼
                       REAL MARKET

Monitoring / Metrics / Audit / Alerts observe every layer.
```

Bu mimari, gerçek algoritmik trading sistemlerinde görülen veri, strateji, risk, execution ve monitoring ayrımını temel alır. AB'de MiFID II kapsamında algoritmik trading yapan yatırım firmaları için de dayanıklılık, işlem eşikleri/limitleri, hatalı emir önleme, test ve izleme gibi kontroller öne çıkarılmaktadır. Scryne Quant başlangıçta kişisel araştırma projesi olsa da mimari olarak bu prensiplerden ilham alacaktır. [ESMA Article 17](https://www.esma.europa.eu/publications-and-data/interactive-single-rulebook/mifid-ii/article-17-algorithmic-trading), [ESMA 2026 Supervisory Briefing](https://www.esma.europa.eu/sites/default/files/2026-02/ESMA74-1505669079-10311_Supervisory_Briefing_on_Algorithmic_Trading_in_the_EU.pdf)

---

# 3. Vizyon

## 3.1 Uzun Vadeli Vizyon

Scryne Quant'ın uzun vadeli vizyonu:

> **Kişisel veya küçük ekip ölçeğinde kullanılabilecek, profesyonel quant research disiplinini erişilebilir hale getiren, stratejiden execution'a kadar tam yaşam döngüsünü yöneten bir algoritmik trading platformu olmak.**

Bu vizyon yalnızca “trade açan bot” üretmekten farklıdır.

Platformun odağı şu yaşam döngüsü olacaktır:

```text
Idea
 ↓
Hypothesis
 ↓
Data
 ↓
Feature
 ↓
Strategy
 ↓
Backtest
 ↓
Validation
 ↓
Paper Trading
 ↓
Risk Approval
 ↓
Live Execution
 ↓
Monitoring
 ↓
Post-Trade Analysis
 ↓
Research Feedback
 ↓
Strategy Revision
```

Böylece sistem kendisini sürekli olarak “araştırma → deneme → ölçüm → geri bildirim” döngüsü içinde geliştiren bir quant laboratuvarına dönüşecektir.

---

# 4. Projenin Felsefesi

## 4.1 Research First

İlk prensip:

> **Gerçek parayı riske atmadan önce hipotezi kanıtlamaya çalış.**

Bir strateji doğrudan live'a çıkmayacaktır.

Minimum pipeline:

```text
Research
  ↓
Backtest
  ↓
Out-of-sample Validation
  ↓
Stress Test
  ↓
Paper Trading
  ↓
Operational Validation
  ↓
Controlled Live
```

---

## 4.2 Risk First

Botun başarısı yalnızca “ne kadar kazandı?” ile ölçülmeyecektir.

Ölçüm kümesinin içerisinde en azından:

- Total return
- Annualized return
- Volatility
- Sharpe ratio
- Sortino ratio
- Maximum drawdown
- Calmar ratio
- Win rate
- Profit factor
- Average trade
- Expectancy
- Exposure
- Turnover
- Fees paid
- Slippage impact
- Consecutive losses
- Recovery time
- Tail loss

bulunacaktır.

Ana fikir:

> Yüksek getiri, yüksek kalite anlamına gelmez.

---

## 4.3 No Fake Alpha

Backtest sonucu “iyi görünüyor” diye strateji başarılı kabul edilmeyecektir.

Sistem özellikle şu riskleri görünür hale getirecektir:

- Look-ahead bias
- Survivorship bias
- Data leakage
- Overfitting
- Parameter mining
- Unrealistic fills
- Ignored fees
- Ignored slippage
- Unrealistic latency
- Incomplete market data
- Regime dependence

Backtest motoru mümkün olduğunca gerçek piyasa koşullarını simüle etmeye çalışacaktır.

---

## 4.4 Kill Switch First-Class Citizen

Sistem yalnızca işlem açmayı değil, gerektiğinde **işlem yapmayı tamamen durdurmayı** da temel özellik olarak görecektir.

Örneğin:

```text
Unexpected drawdown
        ↓
Risk Engine Alert
        ↓
Trading Halt
        ↓
Open orders cancel (policy-dependent)
        ↓
System enters SAFE MODE
        ↓
Operator review
```

---

# 5. Hedef Kullanım Senaryosu

Scryne Quant'ın ana kullanıcı senaryosu tek bir kişinin bir trading fikrini alıp sistematik biçimde test etmesidir.

Örnek:

> “Bitcoin'de kısa vadeli trend takip eden bir strateji oluşturmak istiyorum.”

Kullanıcı:

```text
Asset: BTC/USDT
Timeframe: 15m
Strategy: EMA crossover
Fast EMA: 20
Slow EMA: 50
Risk per trade: 0.5%
Fee assumption: configurable
Slippage assumption: configurable
```

Sistem:

```text
Historical Data
      ↓
Feature Calculation
      ↓
Strategy Evaluation
      ↓
Trade Simulation
      ↓
Risk Model
      ↓
Metrics
```

çıktısı üretir:

```text
Return:              +XX%
Max Drawdown:        -YY%
Sharpe:               X.XX
Profit Factor:        X.XX
Trades:               NNNN
Fees:                 $$$
Slippage Cost:        $$$
Worst Month:          -ZZ%
```

Sonrasında kullanıcı aynı stratejiyi paper trading'e geçirebilir.

---

# 6. Ürünün Modülleri

## 6.1 Data Layer

Sistemin temelidir.

Toplanabilecek ilk veri seti:

### Market Data

- OHLCV
- Tick data
- Trades
- Order book snapshots
- Spread
- Volume
- Funding rate (futures genişlemesinde)
- Open interest (kaynağa göre)

### Meta Data

- Symbol
- Exchange
- Market type
- Tick size
- Lot size
- Min notional
- Trading status
- Fee schedule

### Data Quality

Her veri kaydı için kalite kontrolleri yapılmalıdır:

```text
Timestamp continuity
Price validity
Volume validity
Duplicate detection
Outlier detection
Missing candles
Unexpected gaps
Exchange status
```

Data ingestion katmanı veriyi sadece almakla kalmayacak; alınan verinin kalitesini de değerlendirecektir.

---

# 7. Historical Data Architecture

Zaman serisi verilerinin yüksek insert/query hacmi nedeniyle PostgreSQL tabanlı bir yapı ve ihtiyaç halinde TimescaleDB yaklaşımı değerlendirilecektir. TimescaleDB hypertable yaklaşımı, zaman bazlı veriyi otomatik olarak chunk'lara ayırarak zaman serisi sorgularını optimize etmek üzere tasarlanmıştır. [Timescale Hypertables](https://docs.timescale.com/use-timescale/latest/hypertables/)

Örnek veri modeli:

```text
market_candles
--------------
id
exchange
symbol
timeframe
timestamp
open
high
low
close
volume
source
quality_status
created_at
```

İleride:

```text
trades
order_book_snapshots
funding_rates
open_interest
market_metadata
```

tabloları eklenebilir.

---

# 8. Feature / Indicator Engine

Stratejilerin ham fiyat üzerinden çalışması zorunlu değildir.

Feature Engine aşağıdaki türlerde değişkenler üretebilir:

### Trend

- SMA
- EMA
- WMA
- MACD
- ADX

### Momentum

- RSI
- Stochastic
- ROC

### Volatility

- ATR
- Rolling standard deviation
- Bollinger Bands

### Volume

- OBV
- VWAP
- Volume delta (veri yapısına göre)

### Market structure

- High/low breaks
- Range
- Support/resistance proxies
- Volatility regime

İleride:

- Cross-asset factors
- Market breadth
- Funding features
- On-chain features
- Sentiment features
- News/event features

eklenebilir.

Önemli mimari kural:

> Feature üretimi strateji koduna gömülmemelidir.

Bunun yerine:

```text
Market Data
     ↓
Feature Engine
     ↓
Feature Set
     ↓
Strategy
```

yapısı kullanılmalıdır.

---

# 9. Strategy Engine

Strategy Engine platformun “alpha research” katmanıdır.

İlk başta AI kullanılmasına gerek yoktur.

Önerilen ilk strateji aileleri:

### Trend Following

Örneğin hareketli ortalama bazlı trend takibi.

### Mean Reversion

Aşırı sapma sonrası ortalamaya dönüş varsayımı.

### Breakout

Belirli fiyat seviyelerinin kırılması üzerine kurulu strateji.

### Momentum

Yakın dönem fiyat hareketinin devam edeceği hipotezi.

### Multi-factor

Birden fazla sinyalin birlikte değerlendirilmesi.

---

## 9.1 Strategy Contract

Her stratejinin ortak bir arayüzü olmalıdır.

Kavramsal olarak:

```python
class Strategy:
    def initialize(self, context):
        ...

    def on_bar(self, data, context):
        ...

    def on_tick(self, data, context):
        ...

    def generate_signal(self, data, context):
        ...
```

Ancak stratejinin doğrudan exchange API çağırmasına izin verilmemelidir.

Doğru ayrım:

```text
Strategy
   ↓
Intent / Signal
   ↓
Risk Engine
   ↓
Execution Engine
```

Yanlış ayrım:

```text
Strategy
   ↓
API
   ↓
BUY NOW
```

Bu ayrım projenin güvenlik mimarisinin temelidir.

---

# 10. Signal Model

Strateji doğrudan “emir” yerine bir trading intent üretmelidir.

Örneğin:

```json
{
  "symbol": "BTC/USDT",
  "side": "BUY",
  "confidence": 0.72,
  "reason": "EMA_FAST_CROSSED_ABOVE_EMA_SLOW",
  "target_exposure": 0.20,
  "timestamp": "..."
}
```

Bu sinyal risk motorundan geçmeden execution'a ulaşmamalıdır.

---

# 11. Risk Engine

Risk Engine sistemin en kritik modüllerinden biridir.

Temel sorusu:

> “Bu sinyal teknik olarak doğru olsa bile bunu şimdi ve bu büyüklükte gerçekleştirmek güvenli mi?”

### Risk kontrolleri

#### Position sizing

Örneğin:

```text
Portfolio = $10,000
Max trade risk = 0.5%
Maximum loss budget = $50
```

#### Maximum exposure

```text
BTC exposure <= 30%
Single asset exposure <= X%
```

#### Daily loss limit

```text
Daily PnL < -X%
→ trading halt
```

#### Maximum drawdown guard

```text
Equity drawdown > threshold
→ reduce risk / halt
```

#### Consecutive-loss guard

```text
N consecutive losses
→ strategy cooldown
```

#### Volatility guard

Aşırı volatilite sırasında pozisyon boyutunu azaltma veya işlem yapmama.

#### Liquidity guard

Spread veya order-book koşulları kötüleştiğinde emirleri reddetme.

---

# 12. Portfolio Engine

Portfolio Engine sistemin gerçek durumunu takip eder.

Tutulması gereken kavramlar:

- Cash balance
- Asset balance
- Open positions
- Average entry price
- Unrealized PnL
- Realized PnL
- Exposure
- Leverage (ileride)
- Margin (ileride)
- Fees
- Funding costs (futures genişlemesinde)

Portfolio state tek kaynaktan yönetilmelidir.

---

# 13. Order Management System (OMS)

OMS, stratejinin “al” demesi ile borsada gerçekten gerçekleşen emir arasındaki durumu yönetir.

Örneğin:

```text
Signal
 ↓
Order Intent
 ↓
Risk Approved
 ↓
Order Created
 ↓
Submitted
 ↓
Partially Filled
 ↓
Filled
```

Bunun yanında:

```text
Rejected
Canceled
Expired
Failed
Unknown
```

durumları da açıkça yönetilmelidir.

---

# 14. Execution Engine

Execution Engine trading kararını gerçek emir operasyonuna çevirir.

İlk sürümde:

- Market order
- Limit order
- Cancel order
- Replace order

yeterli olabilir.

İleride:

- TWAP
- VWAP
- Passive execution
- Smart order routing
- Multi-venue execution

gibi sistemler düşünülebilir.

CCXT, farklı crypto exchange API'lerini ortaklaştıran bir katman olarak ilk prototip için güçlü bir adaydır; resmi dokümantasyon 100'den fazla exchange için unified API sunduğunu ve Python dahil birden fazla dili desteklediğini belirtiyor. Bununla birlikte tüm exchange davranışları tamamen aynı değildir; kritik operasyonlarda exchange-specific adapter ve doğrulamalar yine gerekli olacaktır. [CCXT Documentation](https://docs.ccxt.com/docs/manual)

---

# 15. Backtesting Engine

Projenin kalbi backtesting motorudur.

Backtest sadece:

```text
close fiyatı → sinyal → para kazan
```

değildir.

Gerçekçi bir engine:

```text
Historical Market State
        ↓
Strategy
        ↓
Signal
        ↓
Risk
        ↓
Position Sizing
        ↓
Order Simulation
        ↓
Fees
        ↓
Slippage
        ↓
Portfolio Update
        ↓
Metrics
```

oluşturmalıdır.

---

## 15.1 Backtest Türleri

### Basic Backtest

Hızlı araştırma için.

### Event-driven Backtest

Emir, fill, order state gibi olayları simüle eder.

### Walk-forward Backtest

Bir dönemde optimize, sonraki dönemde test yaklaşımı.

### Monte Carlo Analysis

Trade sıralaması ve dağılımına duyarlılığı incelemek için.

### Stress Testing

Aşırı volatilite, spread genişlemesi ve yüksek slippage gibi koşulları simüle eder.

VectorBT, pandas/NumPy tabanlı hızlı backtesting ve çok sayıda strateji/configuration kombinasyonunu taramaya yönelik bir quantitative analysis yaklaşımı sunmaktadır; bu nedenle araştırma katmanında değerlendirilebilir. [VectorBT](https://vectorbt.dev/)

---

# 16. Backtesting'de En Kritik İstatistiksel Riskler

## 16.1 Look-ahead Bias

Stratejinin karar verdiği anda henüz bilinmeyen bilgiyi yanlışlıkla kullanması.

Örneğin:

```text
Bugünkü candle'ın kapanışına göre
bugünkü candle'da işlem açmak
```

yanlış simülasyon olabilir; çünkü kararın hangi zaman anında verildiği açıkça modellenmelidir.

---

## 16.2 Overfitting

Bir stratejinin geçmiş veri üzerindeki parametrelere aşırı uyarlanması.

Örneğin:

```text
EMA Fast = 17
EMA Slow = 63
RSI = 41
Stop = 2.37%
Take Profit = 4.82%
```

kombinasyonunun “mükemmel” görünmesi tek başına anlamlı değildir.

Daha önemli soru:

> Aynı davranış veri dışında da sürüyor mu?

Bu nedenle sistem parameter search sonuçlarını tek başına başarı olarak göstermemelidir.

---

## 16.3 Data Leakage

Model veya stratejinin test döneminden bilgi sızdırması.

Özellikle ML aşamasında kritik hale gelir.

---

## 16.4 Survivorship Bias

Yalnızca bugün hayatta kalan varlıkların geçmişte de sürekli mevcutmuş gibi değerlendirilmesi.

---

## 16.5 Unrealistic Fill Assumption

Her emrin teorik fiyattan anında tamamen gerçekleştiğini varsaymak.

Canlı piyasa bunu garanti etmez.

---

# 17. Performans Ölçüm Sistemi

Dashboard yalnızca “% ROI” göstermemelidir.

### Core metrics

```text
Total Return
CAGR / Annualized Return
Maximum Drawdown
Sharpe Ratio
Sortino Ratio
Calmar Ratio
Volatility
Profit Factor
Win Rate
Average Win
Average Loss
Expectancy
Turnover
Total Fees
Estimated Slippage
```

### Trade metrics

```text
Trades
Long Trades
Short Trades
Average Holding Time
Best Trade
Worst Trade
Consecutive Wins
Consecutive Losses
```

### Risk metrics

```text
Gross Exposure
Net Exposure
Peak Exposure
Drawdown Duration
Time to Recovery
Tail Loss
```

---

# 18. Research Lab

Platformun en değerli özelliklerinden biri araştırma ortamı olacaktır.

Kullanıcı:

```text
Strategy A
Strategy B
Strategy C
```

ve farklı:

```text
Timeframes
Assets
Parameters
Risk Profiles
```

kombinasyonlarını karşılaştırabilir.

### Experiment kaydı

Her deney şu bilgileri saklamalıdır:

```text
Experiment ID
Strategy Version
Code Commit / Revision
Dataset Version
Date Range
Universe
Timeframe
Parameters
Fee Model
Slippage Model
Execution Model
Risk Configuration
Random Seed (if applicable)
Metrics
Artifacts
Notes
```

Bu özellik çok önemlidir çünkü birkaç hafta sonra:

> “Bu sonucu hangi kodla, hangi veriyle, hangi parametreyle elde etmiştim?”

sorusu ortaya çıkacaktır.

---

# 19. Reproducibility

Bir backtest tekrar çalıştırıldığında mümkün olduğunca aynı sonucu üretebilmelidir.

Bu nedenle:

- Dataset versioning
- Strategy versioning
- Config versioning
- Seed management
- Run metadata
- Git commit reference

tutulmalıdır.

---

# 20. Paper Trading

Paper trading, gerçek market data ile sanal portföy üzerinde işlem yapma aşamasıdır.

```text
REAL MARKET DATA
       ↓
 REAL STRATEGY
       ↓
 REAL RISK ENGINE
       ↓
 SIMULATED EXECUTION
       ↓
 VIRTUAL PORTFOLIO
```

Ama paper trading'i gerçek trading'in birebir kopyası sanmak doğru değildir.

Bu yüzden platform:

- backtest result
- paper result
- live result

üçünü ayrı göstermelidir.

---

# 21. Live Trading

Live trading projenin ilk değil, son aşamasıdır.

## Live execution gate

Bir strateji canlıya geçmeden önce örneğin şu kriterlerden geçebilir:

```text
[ ] Backtest completed
[ ] Out-of-sample completed
[ ] Stress test completed
[ ] Risk limits configured
[ ] Paper trading observation completed
[ ] No unresolved execution bugs
[ ] Monitoring active
[ ] Kill switch verified
[ ] Exchange API permissions verified
[ ] Position reconciliation verified
```

Bu liste stratejiyi otomatik olarak “kârlı” ilan etmez. Sadece sistemin operasyona hazır olup olmadığını değerlendirir.

---

# 22. Exchange Integration ve API Güvenliği

Gerçek para kullanan bir API entegrasyonu güvenlik açısından kritik olacaktır.

Temel kurallar:

- API key source code içine yazılmayacak.
- Secret değerleri düz metin loglanmayacak.
- Production secrets environment veya secrets manager üzerinden yönetilecek.
- Withdrawal/transfer yetkisi gereksizse kapalı tutulacak.
- Minimum yetki prensibi uygulanacak.
- Mümkünse IP restriction kullanılacak.
- API errors ve nonce/timestamp problemleri yönetilecek.
- Rate-limit takibi yapılacak.
- Duplicate order riskine karşı idempotency yaklaşımı kullanılacak.

Binance, API anahtarlarının dış uygulamalardan hesap/işlem verisine erişebilmesi ve trading yapabilmesi nedeniyle bunların korunmasını özellikle vurgulamaktadır. Test ortamı için de ayrı Spot Testnet ve Futures Demo ortamları sunulmaktadır. [Binance API](https://www.binance.com/en-TR/binance-api), [Binance API Keys](https://www.binance.com/en/support/faq/detail/360002502072), [Binance Testnet](https://www.binance.com/en/support/faq/detail/ab78f9a1b8824cf0a106b4229c76496d)

---

# 23. Kill Switch ve Safe Mode

Sistemde iki farklı güvenlik mekanizması bulunmalıdır.

## Automatic Kill Switch

Sistem tarafından tetiklenir.

Örnek:

```text
Daily Loss > Limit
API behavior abnormal
Position mismatch
Data feed stale
Execution errors spike
Unexpected spread
System clock issue
```

→ trading halt

## Manual Kill Switch

Operatör tek hareketle:

```text
HALT ALL TRADING
```

yapabilmelidir.

Acil durumda dashboard üzerinden veya CLI/ops endpoint üzerinden gerçekleştirilebilmesi planlanabilir.

---

# 24. Data Feed Failure Strategy

Trading sistemlerinde “veri gelmiyor” durumu normal bir edge case değil, tasarım gereksinimidir.

Örneğin:

```text
Last market update: 37 seconds ago
Expected update: < 5 sec
```

sistem bunu fark etmelidir.

Sonuç:

```text
DATA_STALE
```

→ yeni işlem açma.

Aynı şekilde exchange WebSocket bağlantısı kesilirse reconnect mekanizması devreye girmeli, ancak reconnect sonrası durum mutlaka resync edilmelidir.

---

# 25. Position Reconciliation

En kritik operasyonel konulardan biri internal state ile exchange state arasındaki farktır.

Örneğin sistem:

```text
Internal position = 0.25 BTC
```

diyor olabilir.

Exchange:

```text
Actual position = 0.20 BTC
```

ise sistem güvenli durumda değildir.

Bu durumda:

```text
STATE_MISMATCH
       ↓
TRADING HALT
       ↓
RECONCILIATION
```

uygulanmalıdır.

---

# 26. Monitoring

Dashboard üç ana boyutta gözlemleme sağlamalıdır.

## Trading observability

```text
PnL
Positions
Orders
Fills
Exposure
Drawdown
Strategy state
```

## System observability

```text
CPU
Memory
Latency
WebSocket health
API errors
Queue depth
Database health
```

## Risk observability

```text
Risk limit usage
Daily loss
Max drawdown
Exposure limits
Strategy status
Kill switch status
```

---

# 27. Audit Log

Trading sistemi üzerinde gerçekleşen kritik tüm işlemler audit log'a yazılmalıdır.

Örnek:

```text
2026-09-08 18:22:01
STRATEGY_SIGNAL
BTC/USDT BUY

2026-09-08 18:22:01
RISK_APPROVED
risk=0.42%

2026-09-08 18:22:02
ORDER_SUBMITTED
exchange_order_id=...

2026-09-08 18:22:03
ORDER_FILLED
price=...

2026-09-08 18:22:03
POSITION_UPDATED
```

Bu loglar sonradan:

- debugging
- post-trade analysis
- incident investigation
- strategy analysis

için kullanılacaktır.

---

# 28. Frontend / Dashboard Konsepti

Ürünün frontend'i basit bir “trading terminal clone” olmayacaktır.

Odak:

> **Research + Risk + Execution Visibility**

olacaktır.

## Ana sayfalar

### 1. Overview

```text
Portfolio Value
Daily PnL
Current Drawdown
Open Positions
Active Strategies
System Health
Risk Status
```

### 2. Markets

```text
Symbol
Price
24h Change
Volume
Spread
Trend
Volatility
```

### 3. Strategies

Her stratejinin:

```text
Status
Version
Return
Drawdown
Sharpe
Trades
Paper/Live state
```

görülebilir.

### 4. Backtests

Backtest oluşturma ve sonuç karşılaştırma ekranı.

### 5. Experiments

Araştırma geçmişi ve reproducibility.

### 6. Portfolio

Pozisyonlar ve exposure.

### 7. Orders

OMS ekranı.

### 8. Risk

Risk limitlerinin merkezi.

### 9. System Health

Operasyonel gözlemleme.

### 10. Logs

Audit + system events.

---

# 29. Dashboard Tasarım Dili

Projenin arayüzü:

- Profesyonel
- Yoğun veri kullanımına uygun
- Minimal
- Modern
- Dark-first
- Gereksiz animasyondan uzak
- Rakamları öne çıkaran
- Risk durumlarını açıkça gösteren

olmalıdır.

Özellikle finansal uygulamalarda “çok güzel chart” yerine doğru bilgi hiyerarşisi önemlidir.

Ana tasarım prensibi:

```text
Signal → Decision → Risk → Execution → Outcome
```

kullanıcının tek ekranda takip edebileceği bir zihinsel model yaratmaktır.

---

# 30. Önerilen Teknik Mimari

## Backend

```text
Python
FastAPI
Pydantic
asyncio
```

## Research

```text
NumPy
pandas
VectorBT
Jupyter (research only)
```

## Data

```text
PostgreSQL
TimescaleDB (opsiyonel / değerlendirilecek)
Redis
```

## Exchange

```text
CCXT
Exchange-specific adapters
WebSocket clients
```

## Async / Jobs

İlk sürüm için:

```text
Celery + Redis
```

veya daha gelişmiş orchestration ihtiyaçlarında:

```text
Temporal
```

değerlendirilebilir.

## Frontend

```text
Next.js
TypeScript
Tailwind CSS
shadcn/ui
Recharts / lightweight charting solution
```

## Observability

```text
Structured logging
Prometheus
Grafana
Sentry
OpenTelemetry (ileride)
```

## Deployment

İlk sürüm:

```text
Docker Compose
```

Sonraki aşama:

```text
VPS / Cloud VM
```

Daha ileri aşamada:

```text
Kubernetes / managed services
```

ancak başlangıçta gereksiz operasyonel karmaşıklık oluşturmamak için kullanılmamalıdır.

---

# 31. Önerilen Monorepo Yapısı

```text
scryne-quant/
│
├── apps/
│   ├── web/
│   └── api/
│
├── packages/
│   ├── strategies/
│   ├── indicators/
│   ├── backtest/
│   ├── risk/
│   ├── execution/
│   ├── portfolio/
│   ├── exchange/
│   ├── data/
│   └── common/
│
├── research/
│   ├── notebooks/
│   ├── experiments/
│   └── datasets/
│
├── infrastructure/
│   ├── docker/
│   ├── monitoring/
│   └── migrations/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── backtest/
│   ├── execution/
│   └── risk/
│
├── docs/
│
└── README.md
```

---

# 32. Servis / Modül Ayrımı

İlk sürümde mikroservis mimarisine hemen geçmek yerine modüler monolith yaklaşımı daha sağlıklı olabilir.

Kavramsal yapı:

```text
API
 │
 ├── Data Service
 ├── Research Service
 ├── Strategy Service
 ├── Backtest Service
 ├── Risk Service
 ├── Portfolio Service
 ├── Order Service
 └── Monitoring Service
```

İhtiyaç oluştuğunda yüksek yük alan parçalar ayrı servislere bölünebilir.

Örneğin:

```text
Data Ingestion → worker
Backtests → worker pool
Live Execution → isolated service
```

Özellikle live execution'ın araştırma workload'undan izole edilmesi güvenlik açısından önemlidir.

---

# 33. State Machine Tasarımı

Strategy ve order state'leri açık state machine ile modellenmelidir.

## Strategy lifecycle

```text
DRAFT
 ↓
RESEARCH
 ↓
BACKTESTED
 ↓
VALIDATED
 ↓
PAPER
 ↓
APPROVED
 ↓
LIVE
 ↓
PAUSED / HALTED
 ↓
RETIRED
```

## Order lifecycle

```text
CREATED
 ↓
VALIDATED
 ↓
SUBMITTED
 ↓
ACKNOWLEDGED
 ↓
PARTIALLY_FILLED
 ↓
FILLED
```

Alternatif branch:

```text
REJECTED
CANCELED
EXPIRED
FAILED
UNKNOWN
```

---

# 34. API Konsepti

Örnek endpointler:

```text
GET    /markets
GET    /markets/{symbol}
GET    /candles

GET    /strategies
POST   /strategies
GET    /strategies/{id}
PATCH  /strategies/{id}

POST   /backtests
GET    /backtests/{id}
GET    /backtests/{id}/trades
GET    /backtests/{id}/metrics

GET    /portfolio
GET    /positions
GET    /orders

GET    /risk/status
POST   /risk/halt
POST   /risk/resume

GET    /system/health
GET    /logs
```

Live trading endpointleri özellikle internal/private erişim ve güçlü authorization arkasında olmalıdır.

---

# 35. Database Entity Konsepti

Ana entity'ler:

```text
User
Exchange
Market
Candle
Trade
OrderBookSnapshot
Strategy
StrategyVersion
BacktestRun
Experiment
Portfolio
Position
Order
Fill
RiskLimit
RiskEvent
SystemEvent
AuditLog
```

Özellikle:

```text
Strategy
  └── StrategyVersion
        └── BacktestRun
              └── Experiment
```

ilişkisi korunmalıdır.

---

# 36. ML / AI Katmanı

AI başlangıçta sistemin merkezine konulmayacaktır.

Önerilen yol:

```text
Phase 1
Rule-based strategies

Phase 2
Statistical features

Phase 3
Factor models

Phase 4
ML prediction experiments

Phase 5
Ensemble / regime models
```

AI kullanım alanları:

- Regime classification
- Volatility forecasting
- Return distribution modeling
- Anomaly detection
- Trade filtering
- Feature ranking
- News/sentiment enrichment

Ama kritik ilke:

> AI modeli doğrudan “BUY/SELL” üretse bile Risk Engine'i bypass edemez.

---

# 37. Neden İlk Sürümde LLM Kullanılmamalı?

LLM'ler trading sisteminin deterministik core'u için doğru başlangıç noktası değildir.

Bunun yerine LLM:

- araştırma asistanı
- experiment summary
- log explanation
- strategy documentation
- natural language query

gibi yan katmanlarda kullanılabilir.

Örneğin:

> “Son 30 paper trade içinde stratejinin en kötü performans gösterdiği volatilite rejimini bul.”

LLM bunu analiz katmanında özetleyebilir.

Ama:

```text
LLM → BUY BTC → Exchange
```

şeklinde doğrudan kontrol verilmemelidir.

---

# 38. Güvenlik Modeli

Trading botta security sadece API key korumak değildir.

Tehdit modeli:

### Credential compromise

API key sızması.

### Accidental order

Bug nedeniyle yanlış miktarda emir.

### Duplicate order

Retry mekanizması nedeniyle aynı emrin iki kez gönderilmesi.

### State desync

Botun internal state'inin exchange ile uyuşmaması.

### Stale market data

Botun güncel olmayan veriyle işlem yapması.

### Clock drift

Timestamp/signature problemleri.

### Dependency compromise

Supply-chain saldırıları.

### Operator error

Yanlış configuration.

### Data poisoning

İleride ML katmanında bozuk/zararlı veri.

---

# 39. Güvenlik Önlemleri

Minimum:

```text
Secrets Manager / environment secrets
Least privilege API permissions
No withdrawal permission by default
IP restrictions where available
Rate-limit protection
Idempotent order handling
Strict input validation
Configuration schema validation
Immutable audit logs
Emergency kill switch
Position reconciliation
Health checks
Dependency pinning
Automated security scanning
```

---

# 40. Test Stratejisi

Trading software'da test sadece unit test değildir.

## Unit Tests

- Indicator calculations
- Risk calculations
- Position sizing
- PnL
- Fee calculations
- State transitions

## Integration Tests

- Exchange adapter
- Database
- WebSocket
- Redis
- Order lifecycle

## Simulation Tests

- Market crash
- Data gap
- API timeout
- Partial fill
- Duplicate event
- Restart during open position

## Backtest Regression Tests

Bir stratejinin veya engine değişikliğinin geçmiş sonuçları istemeden değiştirmesini yakalamak için golden datasets kullanılabilir.

## Chaos / Failure Tests

İleride:

```text
kill worker
kill websocket
restart API
network failure
DB failure
```

sonrasında sistemin güvenli biçimde toparlanıp toparlanmadığı test edilmelidir.

---

# 41. CI/CD

Her commit'te:

```text
Lint
Type checking
Unit tests
Integration subset
Security scan
Build
```

çalıştırılabilir.

Production deployment öncesi:

```text
Full test suite
Migration validation
Config validation
Paper environment smoke test
```

gerekmelidir.

Live trading deploy'u ayrıca manuel approval gerektirebilir.

---

# 42. Strateji Registry

Her strateji merkezi bir registry'de tanımlanabilir.

Örnek:

```yaml
strategy:
  id: ema-crossover-v1
  asset_class: crypto_spot
  timeframe: 15m
  status: paper
  parameters:
    fast_ema: 20
    slow_ema: 50
  risk:
    max_position: 0.20
    risk_per_trade: 0.005
```

Bu yapı sayesinde trading engine kodundan configuration ayrılabilir.

---

# 43. Strategy Promotion System

Stratejilerin live'a alınması manuel bir “toggle” olmamalıdır.

Örneğin:

```text
BACKTEST
   ↓
QUALITY CHECK
   ↓
OUT-OF-SAMPLE
   ↓
RISK REVIEW
   ↓
PAPER
   ↓
LIVE CANDIDATE
   ↓
MANUAL APPROVAL
   ↓
LIVE
```

Böyle bir promotion sistemi projenin en güçlü profesyonel özelliklerinden biri olabilir.

---

# 44. Strategy Health Score

İleride her strateji için tek bir “sağlık” görünümü üretilebilir.

Ancak bu bir “kârlılık puanı” olmamalıdır.

Örneğin:

```text
Research Quality      82/100
Risk Stability        91/100
Execution Stability   88/100
Out-of-Sample         76/100
Paper/Backtest Gap    63/100
```

Bu skorlar açıklanabilir olmalı, gizemli AI puanı olmamalıdır.

---

# 45. Backtest–Paper–Live Drift

Sistemin önemli araştırma özelliklerinden biri sonuçlar arasındaki farkı ölçmek olacaktır.

Örneğin:

```text
Backtest Return:      +24%
Paper Return:         +18%
Live Return:           +9%
```

Sistem “live kötü” demek yerine farkın olası nedenlerini araştırmalıdır:

```text
Fee drift
Slippage drift
Fill rate
Market regime
Latency
Signal frequency
Liquidity
```

Bu özellik sistemi sıradan botlardan ayırabilecek önemli bir research capability'dir.

---

# 46. Trading Journal

Otomatik işlemler için bile journal tutulabilir.

Her trade için:

```text
Why signal generated?
What was market regime?
What risk limits applied?
What was expected?
What actually happened?
```

kaydedilebilir.

İleride insan tarafından girilen notlar da eklenebilir.

---

# 47. Research Notebook Entegrasyonu

Quant research için Jupyter notebook veya Python research environment kullanılabilir.

Ama notebook'lar production execution ile karıştırılmamalıdır.

```text
Research Environment
        ↓
Validated Strategy Artifact
        ↓
Production Strategy Registry
```

şeklinde promotion yapılmalıdır.

---

# 48. Veri Saklama Politikası

Veri türüne göre:

```text
Raw data
Processed data
Features
Backtest artifacts
Trade logs
```

ayrı tutulmalıdır.

Raw data mümkün olduğunca değiştirilemez olarak saklanmalı; düzeltme gerektiğinde yeni dataset version oluşturulmalıdır.

---

# 49. Performans / Ölçeklenebilirlik

İlk aşamada ultra-low-latency/HFT hedeflenmeyecektir.

Bu çok önemli bir kapsam kararıdır.

Scryne Quant'ın ilk versiyonu:

```text
Research / Swing / Intraday automation
```

gibi daha uzun zaman ufuklarında çalışabilecek şekilde tasarlanacaktır.

HFT:

```text
Microsecond latency
Colocation
Kernel bypass
Custom network stack
FPGA
```

gibi bambaşka mühendislik gerektirir ve bu projenin başlangıç kapsamı değildir.

---

# 50. Neden Crypto ile Başlamak Mantıklı?

İlk MVP için crypto tercih edilmesinin teknik gerekçeleri:

- 24/7 piyasa yapısı
- Çok sayıda API erişimi
- Test/demo ortamlarının bulunabilmesi
- Programatik veri erişiminin yaygın olması
- Küçük bir prototip için erişilebilir operasyon

Ancak bu tercih “crypto daha kolay para kazanılan bir piyasa” anlamına gelmez.

Riskleri yüksektir ve exchange/varlık bazlı operasyonel riskler ciddi olabilir.

İlk aşamada **spot** piyasa önerilir; futures, leverage ve liquidation mekanikleri daha sonra eklenmelidir.

---

# 51. Türkiye Açısından Düzenleyici Kapsam

Bu proje kişisel kullanım amacıyla geliştirilen bir yazılım/ar-Ge projesi olarak başlayabilir; fakat proje ileride başkaları adına işlem yapma, müşteri fonu/varlıkları yönetme, saklama, yatırım hizmeti sunma, platform işletme veya ticari bir servis haline gelme noktasına gelirse düzenleyici kapsam ciddi biçimde değişebilir.

Türkiye'de 7518 sayılı Kanun ile kripto varlık hizmet sağlayıcıları Sermaye Piyasası Kurulu'nun düzenleme ve denetim kapsamına alınmış; 13 Mart 2025 tarihinde ilgili kuruluş ve faaliyet esaslarına ilişkin ikincil düzenlemeler yayımlanmıştır. SPK, bu düzenlemelerin iç kontrol, risk yönetimi, bilgi sistemleri, teknolojik altyapı, kayıt sistemleri, hizmetler, saklama ve sermaye yeterliliği gibi alanları kapsadığını açıklamaktadır. SPK'nın güncel “Faaliyette Bulunanlar Listesi” de listenin tek başına yetkilendirme anlamına gelmediği uyarısını içermektedir. [SPK – 2025 Düzenlemeleri](https://spk.gov.tr/duyurular/basin-duyurulari/2025/kripto-varlik-hizmet-saglayicilarina-iliskin-iki-tebli%C4%9F-yayimlandi), [SPK – 2024 Duyurusu](https://spk.gov.tr/duyurular/basin-duyurulari/2024/kripto-varlik-hizmet-saglayicilara-iliskin-duyuru_02072024), [SPK – Faaliyette Bulunanlar Listesi](https://spk.gov.tr/kurumlar/kripto-varlik-hizmet-saglayicilar/faaliyette-bulunanlar-listesi)

Bu nedenle proje dokümanı **hukuki tavsiye değildir**. Ürün başkalarına sunulmadan, müşteri fonları veya yatırım kararlarıyla ilgili hizmet verilmeden önce Türkiye'deki güncel mevzuat ve gerektiğinde uzman hukukçu değerlendirmesi yapılmalıdır.

---

# 52. Ürün Kapsamı ve Non-Goals

## MVP'de yapılacaklar

```text
Crypto spot
Market data ingestion
Historical storage
Indicator engine
Rule-based strategies
Backtesting
Performance metrics
Paper trading
Portfolio tracking
Risk engine
Basic execution adapter
Dashboard
Logging
Alerts
```

## MVP'de yapılmayacaklar

```text
HFT
Leverage
Futures
Options
Cross-exchange arbitrage
Market making
Fully autonomous AI trader
Copy trading
Customer accounts
Custody
Social trading
Public investment service
```

Bunların tamamı gelecekte değerlendirilebilir ancak MVP'nin başarısını tehlikeye atacak kadar erken eklenmemelidir.

---

# 53. Aşamalı Geliştirme Yol Haritası

## Phase 0 — Trading Education

Önce öğrenilecekler:

```text
Markets
Candles
Orders
Long/Short
Spot/Futures
Fees
Spread
Slippage
Volatility
Drawdown
Position sizing
Risk
```

Amaç yazılım geliştirmek değil, sistemi yanlış modellememektir.

---

## Phase 1 — Market Data Foundation

```text
Exchange connection
Historical downloader
WebSocket consumer
Database schema
Data validation
Data quality reports
```

Çıktı:

> Güvenilir ve sorgulanabilir market dataset'i.

---

## Phase 2 — Research Toolkit

```text
Indicators
Feature engine
Strategy API
Research notebooks
Experiment registry
```

---

## Phase 3 — Backtesting Engine

```text
Signal simulator
Order simulator
Fee model
Slippage model
Portfolio model
Metrics
Equity curve
Trade list
```

---

## Phase 4 — Strategy Laboratory

İlk stratejiler:

```text
SMA crossover
EMA crossover
RSI mean reversion
Breakout
Momentum
```

Amaç kâr bulmak değil:

> farklı strategy family'lerini bilimsel olarak karşılaştırmayı öğrenmek.

---

## Phase 5 — Risk Engine

```text
Position sizing
Exposure limits
Daily loss limit
Drawdown limit
Kill switch
Cooldown
Volatility guard
```

---

## Phase 6 — Paper Trading

```text
Realtime market data
Live signals
Simulated orders
Position tracking
Real-time risk checks
```

---

## Phase 7 — Execution Sandbox

Resmi test/demo ortamı.

Örneğin Binance Spot Testnet kullanılabilir. Güncel Binance dokümantasyonu Spot Testnet ve Futures Demo ortamlarının test için kullanılabildiğini ve test ağındaki varlıkların gerçek varlık olmadığını belirtmektedir. Testnet ayrıca periyodik olarak sıfırlanabilir. [Binance Testnet](https://www.binance.com/en/support/faq/detail/ab78f9a1b8824cf0a106b4229c76496d)

---

## Phase 8 — Controlled Live

Minimum sermaye ile, çok düşük risk limitleriyle, tek veya çok az sayıda markette kontrollü execution.

Bu aşamada amaç para kazanmak değil:

> **backtest → paper → live arasındaki gerçek operasyon farkını ölçmek.**

---

# 54. Başarı Kriterleri

Proje başarısı yalnızca net PnL ile değerlendirilmeyecektir.

## Engineering success

```text
No duplicate orders
No unreconciled positions
Safe restart
Reliable market ingestion
Deterministic backtests
Full audit trail
Automated tests
```

## Research success

```text
Reproducible experiments
No look-ahead bias
Realistic transaction costs
Out-of-sample support
Stress tests
Strategy versioning
```

## Operational success

```text
Stable paper trading
Correct order lifecycle
Accurate PnL
Correct risk enforcement
Working kill switch
```

## Financial success

Financial performance ancak tüm diğer katmanlardan sonra değerlendirilmelidir.

---

# 55. Risk Register

| Risk | Etki | Olasılık | Önlem |
|---|---:|---:|---|
| Overfitting | Çok yüksek | Yüksek | OOS, walk-forward, stress test |
| Data leakage | Çok yüksek | Orta | Time-aware pipeline, validation |
| API key leak | Çok yüksek | Düşük/Orta | Secret manager, least privilege |
| Duplicate order | Çok yüksek | Orta | Idempotency, order state machine |
| State mismatch | Çok yüksek | Orta | Reconciliation + halt |
| Market data outage | Yüksek | Orta | Stale-data guard |
| Slippage underestimation | Yüksek | Yüksek | Conservative execution model |
| Exchange outage | Yüksek | Orta | Safe mode, retry/reconcile |
| Software bug | Çok yüksek | Orta | Tests, sandbox, staged rollout |
| Poor strategy | Yüksek | Yüksek | Research gates |
| Regime change | Yüksek | Yüksek | Monitoring, walk-forward |
| Regulatory scope expansion | Çok yüksek | Düşük/Orta | Legal review before commercialization |

---

# 56. En Tehlikeli Yanılgılar

## “Backtest'te çok kazandı, demek ki çalışıyor.”

Hayır.

Backtest araştırma kanıtıdır; geleceğe dair garanti değildir.

## “Win rate %70, yani iyi.”

Tek başına hiçbir şey ifade etmez.

%70 win rate olan bir sistem tek büyük kayıpla zarar edebilir.

## “AI eklersek daha iyi olur.”

Kanıtlanmamış stratejinin üzerine AI koymak sorunu çözmez.

## “Bot 24/7 çalışacak, o zaman daha çok kazanır.”

Daha fazla işlem fırsatı aynı zamanda daha fazla hata ve transaction cost anlamına gelebilir.

## “Leverage daha hızlı büyütür.”

Leverage aynı zamanda kayıpları da büyütür ve liquidation riskini devreye sokar. Bu nedenle ilk sürümde kapsam dışıdır.

---

# 57. Projenin Benzersizliği

Scryne Quant'ın güçlü tarafı tek başına “trading bot” olması değildir.

Fark yaratan yaklaşım:

```text
Research
+ Reproducibility
+ Backtesting
+ Risk Engine
+ Execution Safety
+ Observability
+ Strategy Lifecycle
```

birlikteliğidir.

Klasik basit bot:

```text
indicator → buy/sell → exchange
```

Scryne Quant:

```text
idea
 ↓
research
 ↓
data
 ↓
strategy
 ↓
backtest
 ↓
validation
 ↓
risk
 ↓
paper
 ↓
execution
 ↓
monitoring
 ↓
feedback
```

olacaktır.

---

# 58. Gelecekte Eklenebilecek Özellikler

MVP sonrası:

### Multi-exchange

Birden fazla borsaya bağlanma.

### Cross-market research

BTC, ETH, altcoin basket vb.

### Futures

Ancak ciddi risk modeli sonrası.

### Portfolio optimization

Birden fazla stratejinin birlikte yönetimi.

### Regime detection

Market koşullarına göre strateji seçimi.

### ML pipeline

Feature → train → validate → deploy.

### Alternative data

News, sentiment, on-chain data.

### Strategy ensemble

Birden fazla model/strateji birlikte.

### Smart execution

Spread ve liquidity-aware order routing.

### Multi-agent research assistant

LLM destekli research workflow.

---

# 59. Uzun Vadeli Mimari Vizyon

Son haline geldiğinde platform aşağıdaki ekosisteme evrilebilir:

```text
                         SCRYNE QUANT
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
     RESEARCH             EXECUTION           MONITORING
          │                   │                   │
          ▼                   ▼                   ▼
     DATA LAB            ORDER SYSTEM       RISK CENTER
          │                   │                   │
          └──────────────┬────┴────┬──────────────┘
                         │         │
                         ▼         ▼
                    PORTFOLIO   AUDIT
                         │
                         ▼
                  PERFORMANCE
                         │
                         ▼
                     FEEDBACK
                         │
                         └────────→ RESEARCH
```

Bu mimari sayesinde sistem sadece işlem yapan bir script olmaktan çıkıp bir **algorithmic trading operating environment** haline gelebilir.

---

# 60. Nihai Proje Tanımı

## Tek cümlelik tanım

> **Scryne Quant, trading stratejilerini veri üzerinde araştırmak, backtest etmek, risk açısından değerlendirmek, paper trading ile doğrulamak ve kontrollü biçimde otomatik olarak uygulamak için geliştirilen modüler bir algorithmic trading research ve execution platformudur.**

## Daha kapsamlı tanım

Scryne Quant; market data ingestion, historical time-series storage, feature engineering, strategy development, backtesting, out-of-sample validation, risk management, portfolio management, order management, exchange execution, paper trading, live trading, experiment tracking, monitoring ve audit yeteneklerini tek bir mimaride birleştiren araştırma-öncelikli bir quant trading platformu olacaktır.

Sistem herhangi bir stratejiyi “kârlı” kabul etmek yerine stratejinin hangi koşullarda, hangi veri üzerinde, hangi maliyet varsayımlarıyla ve hangi risk altında çalıştığını ölçmeye odaklanacaktır. Bu nedenle platformun ana ürünü yalnızca trading algoritması değil; **algoritmanın güvenilirliğini araştırmak için gereken altyapının tamamıdır.**

---

# 61. Projenin İlk Somut Hedefi

İlk hedef doğrudan para kazandıran bir bot yazmak değildir.

İlk somut hedef:

> **BTC/USDT spot verisini güvenilir biçimde toplayabilen, en az birkaç rule-based stratejiyi deterministik biçimde backtest edebilen, transaction cost ve slippage hesaplayabilen, risk kurallarını uygulayabilen ve aynı stratejileri gerçek zamanlı market data üzerinde paper trading ile çalıştırabilen bir quant platformunun ilk üretilebilir sürümünü oluşturmak.**

Bu hedef tamamlandığında:

```text
Data ✅
Strategy ✅
Backtest ✅
Risk ✅
Paper Trading ✅
Monitoring ✅
```

seviyesine ulaşılmış olacaktır.

Live trading bunun ardından gelecektir.

---

# 62. İlk MVP Sonunda Ortaya Çıkması Beklenen Sistem

```text
                ┌───────────────────────┐
                │      WEB DASHBOARD    │
                └────────────┬──────────┘
                             │
                       REST / WS API
                             │
                ┌────────────▼──────────┐
                │      CORE PLATFORM    │
                │                       │
                │ Strategy              │
                │ Backtest              │
                │ Risk                  │
                │ Portfolio             │
                │ OMS                   │
                │ Execution             │
                └───────────┬───────────┘
                            │
                 ┌──────────┴───────────┐
                 │                      │
                 ▼                      ▼
        ┌─────────────────┐    ┌─────────────────┐
        │ PostgreSQL / TS │    │ Redis / Workers │
        └─────────────────┘    └─────────────────┘
                 │
                 ▼
        ┌─────────────────┐
        │ Exchange Adapter│
        └────────┬────────┘
                 │
                 ▼
             Exchange
```

---

# 63. Sonuç

Scryne Quant'ın ana fikri basitçe “otomatik al-sat yapan bir bot” değildir.

Proje, bir trading fikrinin ortaya çıkışından gerçek piyasa uygulamasına kadar tüm yaşam döngüsünü sistematik hale getirmeyi amaçlamaktadır.

Bunun merkezinde üç ana fikir bulunur:

### 1. Araştır

Bir stratejiyi önce veri ile sorgula.

### 2. Ölç

Getiriden çok risk, maliyet, stabilite ve out-of-sample davranışını incele.

### 3. Koru

Hiçbir strateji risk motorunu, güvenlik kontrollerini ve kill switch'i aşamasın.

Bu yaklaşım sayesinde proje hem güçlü bir software engineering çalışması hem de ciddi bir quant/trading öğrenme altyapısı haline gelebilir.

En önemli hedef “ilk günden para kazanmak” değil, **finansal bir sistemi bilimsel olarak test edebilecek, hataları görünür kılacak ve gerçek para ile temas ettiğinde güvenli davranacak bir platform inşa etmektir.**

---

# 64. Kaynaklar ve Teknik Referanslar

1. **CCXT Documentation** — Unified exchange API ve exchange entegrasyonları.  
   https://docs.ccxt.com/docs/manual

2. **VectorBT Documentation** — Quantitative analysis ve hızlı backtesting.  
   https://vectorbt.dev/

3. **TimescaleDB Documentation — Hypertables** — Time-series storage/partitioning yaklaşımı.  
   https://docs.timescale.com/use-timescale/latest/hypertables/

4. **Binance — Spot Testnet / Futures Demo** — Test ve demo ortamları.  
   https://www.binance.com/en/support/faq/detail/ab78f9a1b8824cf0a106b4229c76496d

5. **Binance — API** — API kullanımına ilişkin resmi bilgiler.  
   https://www.binance.com/en-TR/binance-api

6. **Binance — API Keys** — API anahtarları ve izinler.  
   https://www.binance.com/en/support/faq/detail/360002502072

7. **ESMA — MiFID II Article 17: Algorithmic Trading** — Risk kontrolleri, limitler, resilience, testing ve monitoring ilkeleri.  
   https://www.esma.europa.eu/publications-and-data/interactive-single-rulebook/mifid-ii/article-17-algorithmic-trading

8. **ESMA — Supervisory Briefing on Algorithmic Trading in the EU (26 Feb 2026)** — Algorithmic trading supervision, governance, testing ve outsourcing konularında güncel yaklaşım.  
   https://www.esma.europa.eu/sites/default/files/2026-02/ESMA74-1505669079-10311_Supervisory_Briefing_on_Algorithmic_Trading_in_the_EU.pdf

9. **SPK — Kripto Varlık Hizmet Sağlayıcılarına İlişkin İki Tebliğ (13 Mar 2025)** — Türkiye'deki kripto varlık hizmet sağlayıcılarına ilişkin ikincil düzenlemeler.  
   https://spk.gov.tr/duyurular/basin-duyurulari/2025/kripto-varlik-hizmet-saglayicilarina-iliskin-iki-tebliğ-yayimlandi

10. **SPK — 7518 Sayılı Kanun Kapsamında Duyuru (2 Jul 2024)** — Kripto varlık hizmet sağlayıcıların SPK düzenleme/denetim kapsamına alınması.  
    https://spk.gov.tr/duyurular/basin-duyurulari/2024/kripto-varlik-hizmet-saglayicilara-iliskin-duyuru_02072024

---

# 65. Disclaimer

Bu doküman bir proje tasarımı ve teknik konsept dokümanıdır; yatırım tavsiyesi, finansal tavsiye veya kârlılık garantisi değildir.

Trading stratejileri geçmiş performanstan gelecekteki getiriyi garanti etmez. Gerçek para ile işlem yapan sistemlerde sermaye kaybı, teknik arıza, exchange riski, likidite riski, operasyonel risk ve düzenleyici risk bulunur.

Gerçek para ile live execution'a geçişten önce teknik testler, kontrollü paper trading, güvenlik doğrulaması ve gerekli durumlarda bağımsız hukuki/finansal değerlendirme yapılmalıdır.
