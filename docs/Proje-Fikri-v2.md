---
proje: ScryneQuant
created: 2026-09-12
type: proje-fikri
surum: 2
status: denetlendi
kaynak: Multi_Asset_Autonomous_Trading_Platform_Proje_Fikir_Dokumani.docx
---

> **Not (2026-09-12):** Bu dosya Scryne'ın 2026-09-12'de getirdiği ikinci konsept
> dokümanının (`.docx`) tam metnidir; içeriği değiştirilmemiş, yalnızca Markdown'a
> çevrilmiştir (tablolar ve kod bloğu yeniden kuruldu). Aynı gün gelen `.md` sürümü bu
> metnin kısaltılmış bir özetidir; çelişirlerse bu dosya (docx) esas alınır.
>
> Projenin **ikinci vizyonu** budur ve birincinin (`docs/Proje-Fikri.md`) yerini alır;
> ama v1 üzerine kurulan altyapı ve kararlar geçerliliğini korur. Denetimi
> `docs/Denetim-v2.md`, sonucunda verilen kararlar `docs/Kararlar.md` (K-048…),
> bağlayıcı hâli `docs/Final-Dokuman.md`. **Çelişki durumunda Final-Doküman geçerlidir.**

# MULTI-ASSET AUTONOMOUS TRADING PLATFORM

**Nihai Profesyonel Proje Fikir Dokümanı**
Araştırma, ürün vizyonu, sistem mimarisi, doğrulama metodolojisi ve fazlandırma

**Belge durumu:** Tasarım temel şartnamesi / proje başlangıç spesifikasyonu
**Tarih:** 12 Eylül 2026
**Kapsam notu:** Bu doküman yatırım veya finansal danışmanlık değildir. Amaç, otomatik işlem
araştırma ve yazılım sistemi için teknik/ürün tasarımını tanımlamaktır.

## 1. Yönetici Özeti

Projenin amacı, farklı finansal piyasalardan sürekli ve zaman bakımından doğru veriler
toplayan; haber, ekonomik olay, şirket/varlık bilgisi, türev piyasa verileri ve piyasa
mikro-yapısını ortak bir veri katmanında birleştiren; piyasa rejimini belirleyen; birden çok
bağımsız alpha hipotezini test eden; portföy ve risk kararlarını execution maliyetleriyle
birlikte değerlendiren ve yalnızca doğrulama kapılarından geçen stratejileri otomatik olarak
canlı piyasaya taşıyabilen profesyonel bir algorithmic trading platformu kurmaktır.

Ana hedef kârlılıktır; ancak sistem "garantili para makinesi" olarak tasarlanmayacaktır.
CFTC, AI kullanan trading botlarının geleceği veya ani piyasa değişimlerini güvenilir
biçimde öngöremeyeceğini ve olağanüstü/garantili getiri iddialarının kırmızı bayrak olduğunu
açıkça vurgulamaktadır.[1] Bu nedenle projedeki "kârlı" hedefi, işlem maliyetlerinden sonra,
out-of-sample/forward testlerde ve canlı küçük sermaye döneminde istatistiksel olarak
savunulabilir pozitif beklenen değer göstermeyi ifade eder.

En önemli stratejik karar: "tüm piyasaları tek modelle trade etmek" hedeflenmeyecektir.
Bunun yerine evrensel bir trading çekirdeği; piyasa-özgü veri adapterları, alpha aileleri,
execution modelleri ve risk kuralları ile genişletilecektir. Böylece aynı platform hisse
senedi, ETF, kripto, FX, futures, emtia ve ilerleyen aşamada opsiyon gibi farklı piyasalara
genişleyebilir; fakat her piyasanın mikro-yapısı ve maliyet gerçekliği ayrı modellenir.

## 2. Projenin Vizyonu

Ürün vizyonu: "Piyasayı izleyen bir bot" değil, piyasa verisini araştırılabilir bilgiye
dönüştüren, hipotezleri sistematik biçimde sınayan ve sermayeyi korumayı birinci sınıf
yazılım kabiliyeti olarak ele alan bir **Autonomous Trading Research & Execution Platform**.

Sistem beş ana soruya cevap verecektir: (1) Şu anda piyasada ne oluyor? (2) Bunun neden
olabileceğine dair hangi ölçülebilir hipotezler var? (3) Bu hipotez geçmişte benzer
koşullarda çalıştı mı? (4) Bugün, maliyet ve riskler dahil edildiğinde beklenen değer nedir?
(5) İşlem yapılacaksa hangi araçta, hangi büyüklükte ve hangi execution yöntemiyle
yapılmalıdır?

## 3. Tasarım İlkeleri

- **Strategy-first değil, evidence-first:** Her alpha iddiası ölçülebilir hipotez olarak
  kayıt altına alınacaktır.
- **No guaranteed profit:** Hiçbir model veya LLM "kâr garantisi" olarak kabul
  edilmeyecektir.[1]
- **Point-in-time correctness:** Geleceğin bilgisi geçmişe sızmayacaktır. Data release
  time, revision ve availability ayrı tutulacaktır.
- **Cost-aware research:** Komisyon, spread, slippage, borrow/funding, market impact ve
  latency varsayımları backtestin parçasıdır.
- **Search-aware validation:** Kaç hipotezin, parametrenin ve modelin denendiği
  kaydedilecek; selection luck ve backtest overfitting ölçülecektir.[4][5][7]
- **Risk can veto:** Risk Engine, alpha modelinden bağımsız son söz sahibi olacaktır.
- **Execution is part of the strategy:** Sinyalin kârlı olması ile emrin kârlı uygulanması
  ayrı problemlerdir.
- **Human override + kill switch:** Canlı sistemde manuel durdurma, exposure azaltma ve
  güvenli moda geçiş zorunludur.
- **Immutable auditability:** Her veri, feature, model, karar ve emir geriye dönük
  açıklanabilir olmalıdır.
- **Progressive activation:** Paper → shadow → micro-live → controlled live. Doğrudan tam
  sermaye geçişi yoktur.

## 4. Para Kazanma Tezi

Platformun doğrudan amacı "fiyat tahmini" yapmak değil; belirli koşullarda piyasaların
verimsizliklerinden doğan pozitif beklenen değeri maliyetlerin üzerinde yakalamaktır. Bu
nedenle proje tek bir strateji yerine alpha aileleri araştıracaktır.

| Alpha ailesi | Temel hipotez | Uygun piyasa örnekleri | Ana risk |
| --- | --- | --- | --- |
| Trend / momentum | Fiyat hareketi ve risk primi belirli rejimlerde devam edebilir. | Equities, futures, crypto, FX | Reversal / regime shift |
| Mean reversion | Aşırı kısa/orta vadeli sapmalar belirli koşullarda geri dönebilir. | Liquid equities, ETFs, futures, crypto | Structural break |
| Cross-sectional | Varlıklar arası göreli performans ölçülebilir şekilde ayrışabilir. | Equities, crypto baskets, futures | Crowding / correlation breakdown |
| Event-driven | Planlı veya sürpriz olaylar kısa/orta vadeli fiyat reaksiyonu yaratabilir. | Equities, macro futures, FX | Latency / interpretation error |
| News/NLP | Bilgi şoku ve beklenti farkı fiyat keşfine katkı verebilir. | Equities, FX, crypto | Source latency / false novelty |
| Derivatives | Funding, basis, volatility surface ve positioning fiyatlama davranışı hakkında sinyal sağlayabilir. | Crypto, futures, options | Crowding / liquidity |
| Cross-asset / macro | Rates, USD, volatility, commodities ve risk assets arasındaki ilişkiler rejime göre değişir. | Multi-asset | Correlation instability |
| Market microstructure | Order book/flow özellikleri kısa vadeli execution veya prediction avantajı sağlayabilir. | Highly liquid venues | Fees, latency, capacity |
| Statistical / ML | Feature set belirli bir hedef değişkenin koşullu dağılımını tahmin edebilir. | Asset-specific | Leakage / overfit |

İlk sürüm için önerilen ticari/araştırma yaklaşımı: orta frekanslı ve maliyetlere dayanıklı
sistematik stratejiler. HFT/mikrosaniye rekabeti ilk hedef değildir; çünkü altyapı, veri,
co-location ve execution maliyeti gereksinimi farklı bir iş haline gelir. Bu platformun amacı
önce güvenilir araştırma ve pozitif edge bulma kabiliyeti kazanmaktır.

## 5. Multi-Asset Piyasa Stratejisi

"Tüm piyasalar" hedefi platformun kapsamını ifade eder; ilk gün canlı trade evrenini değil.
Varlık sınıfları farklı market hours, contract size, tick size, settlement, margin, funding,
borrow, expiry, liquidity ve fee yapılarına sahiptir. Borsa İstanbul Pay Piyasası örneğinde
elektronik alım-satım fiyat ve zaman önceliğiyle otomatik gerçekleşirken; NYSE gerçek
zamanlı ürünleri farklı derinlik ve quote/trade veri akışları sunar; kripto borsalarında ise
sürekli 7/24 akış ve WebSocket operasyonları görülür.[11][12][13][17]

| Katman | Başlangıç durumu | İleri aşama |
| --- | --- | --- |
| US equities / ETFs | Birincil research/live aday | Universe expansion, sector/market-neutral |
| Crypto spot/perpetuals | Research + controlled live aday | Multi-venue, funding/basis, hedging |
| FX | Macro + execution research | Multi-broker/venue |
| Futures | Index/commodity/rates research | Cross-asset futures portfolio |
| Options | Volatility research | Options execution; daha ileri risk modeli |
| Borsa İstanbul | Ayrı adapter ve mevzuat incelemesi | Canlı erişim uygunluğu doğrulanınca |

Öneri: İlk canlı piyasayı "en kolay" olduğu için değil, araştırma/uygulama maliyetlerinin ve
veri kalitesinin proje sermayesine uygun olduğu için seçmek. US equities/ETFs ile crypto
arasında teknik fizibilite yüksektir; ancak canlı erişim, veri lisansları ve Türkiye'deki
düzenleyici durum ayrıca doğrulanmalıdır.[15][16][17]

## 6. Sistem Mimarisi — Genel

Önerilen akış: Sources → Ingestion → Canonical Data → Feature/Feature Store → Market
Intelligence → Alpha Research/Models → Signal Ensemble → Portfolio Construction → Risk
Engine → Execution Engine → Venue/Broker → Post-Trade Analytics → Monitoring → Research
Feedback.

Bu akışın yanında yatay çalışan Research Registry, Model Registry, Experiment Tracking, Data
Quality, Audit Log, Secrets Management ve Incident Management katmanları bulunur.

## 7. Veri Platformu

Veri platformu projenin gerçek "temeli"dir. Kötü veri üzerine gelişmiş model koymak, iyi
görünümlü ama sahte edge üretme riskini artırır. Sistem her veri parçası için kaynak, alınma
zamanı, event time, revision, quality state ve availability timestamp tutmalıdır.

### 7.1 Veri sınıfları

- **Market price:** trades, OHLCV, quotes, bid/ask, spread, depth, auctions.
- **Derivatives:** open interest, funding, basis, futures curves, implied volatility, skew,
  options Greeks ve surface.
- **Fundamental:** financial statements, filings, earnings, dividends, corporate actions,
  analyst/consensus where licensed.
- **Macro:** inflation, rates, employment, GDP, PMI, yield curves, central-bank decisions,
  economic calendars.
- **News/events:** articles, press releases, regulatory announcements, geopolitical/event
  markers, source metadata.
- **Alternative data:** on-chain, satellite-like or proprietary datasets yalnızca lisans,
  latency, stability ve predictive value kanıtlanırsa.
- **Operational data:** fills, order acknowledgements, latency, rejected orders, venue
  health, API status.

### 7.2 Point-in-time veri tasarımı

Her gözlem için en az "event_time", "available_time", "ingested_time", "effective_from",
"effective_to" mantığı bulunmalıdır. Makro verilerde revisions kritik olduğu için historical
backtestte o tarihte piyasaya gerçekten açık olan değer kullanılmalıdır. FRED/ALFRED ve ECB
Data Portal gibi kaynaklar tarihsel ve programatik ekonomik veri erişimi sağlar.[8][9] SEC
EDGAR da şirket dosyalamalarını programatik erişime açan altyapılara sahiptir.[10]

## 8. News & Event Intelligence

Haber katmanı basit sentiment score olmamalıdır. Hedef, ham metni piyasanın işleyebileceği
yapılandırılmış olaylara dönüştürmektir.

| Aşama | Çıktı |
| --- | --- |
| Source ingestion | Kaynak, yayıncı, URL, timestamp, dil, içerik hash |
| Entity resolution | Şirket, ülke, merkez bankası, emtia, token, endeks ve ilgili varlıklar |
| Event extraction | Ne oldu? Kim yaptı? Ne zaman? |
| Novelty | Bu bilgi gerçekten yeni mi? Aynı olay daha önce yayınlandı mı? |
| Expectation / surprise | Piyasa beklentisi ile gerçekleşen olay arasındaki fark |
| Impact graph | Doğrudan ve dolaylı etkilenmesi muhtemel varlıklar |
| Historical analogue | Benzer olayların geçmiş piyasa reaksiyonları |
| Confidence | Model/source güveni, kaynak kalitesi, disagreement |
| Market response | Event sonrası gerçekleşen price/volume/volatility response |
| Signal contribution | Alpha modeline girdi; doğrudan emir değil |

LLM burada güçlü bir parsing/semantic layer olabilir; ancak LLM çıktısı tek başına trade
authority olmamalıdır. 2026 tarihli bir çalışmada LLM-driven strategy discovery için
leakage-safe ve search-aware değerlendirme gereği özellikle vurgulanıyor; çok sayıda aday
üretip "en iyi" sonucu seçmek, değerlendirme mekanizmasına search bias ekleyebilir.[7]

## 9. Market Regime Engine

Sistem önce piyasanın hangi durumda olduğunu tahmin etmelidir. Örnek durumlar: trend, range,
high-volatility, low-volatility, stress, risk-on, risk-off, liquidity deterioration,
event-driven, macro-transition.

Regime modeli doğrudan "BUY/SELL" üretmez. Bunun yerine hangi alpha ailesinin aktif
olabileceğine dair koşullu ağırlıklar üretir. Böylece aynı alpha, farklı rejimlerde farklı
risk bütçesi alabilir.

## 10. Feature & Signal Layer

Feature katmanı teknik indikatör yığını olmamalıdır. Feature'lar ekonomik anlam, istatistiksel
stabilite, latency ve maliyet açısından değerlendirilmelidir.

- **Price/return features:** momentum, reversal, trend strength, gaps.
- **Volatility:** realized, implied, term structure, volatility-of-volatility.
- **Liquidity:** spread, depth, turnover, volume shock, market impact proxies.
- **Positioning:** funding, open interest, options positioning, when available.
- **Macro:** rates, spreads, curve shape, dollar, inflation/growth surprises.
- **Cross-sectional:** ranks, dispersion, breadth, factor exposures.
- **Event:** novelty, surprise, sentiment/context, event category, source confidence.
- **Context:** session, calendar, market hours, holidays, earnings windows.
- **Market state:** regime probabilities and uncertainty.

## 11. AI / ML Mimarisi

AI, sistemin merkezinde bulunabilir fakat tek karar vericisi olmamalıdır. Üç farklı AI
katmanı önerilir: semantic AI, predictive ML ve research AI.

| AI katmanı | Görev | Üretim otoritesi |
| --- | --- | --- |
| Semantic AI | News/event/entity extraction, classification, summarization | Hayır — structured evidence üretir |
| Predictive ML | Return/volatility/regime/liquidity probability models | Evet — yalnız validation gate sonrası |
| Research AI | Hypothesis generation, code scaffolding, experiment analysis | Hayır — research assistant |
| LLM explanation | Trade rationale and incident summaries | Hayır — audit/explanation only |

ML kullanımında önce ekonomik teori/hipotez, sonra feature set, sonra model gelmelidir. Lopez
de Prado'nun yaklaşımı da stratejinin teorik gerekçesini merkeze alıp ML'yi teori keşfi ve
out-of-sample predictability için tamamlayıcı araç olarak konumlandırır.[6]

## 12. Portfolio Construction

Sinyaller doğrudan emir değildir. Birden fazla alpha sinyalinin portföy içindeki etkisi;
expected return, uncertainty, volatility, correlation, liquidity, turnover, cost ve risk
budget ile birlikte optimize edilmelidir.

| Karar değişkeni | Öneri |
| --- | --- |
| Position size | Volatility- ve risk-budget-aware |
| Gross exposure | Piyasa/rejim bağımlı limit |
| Net exposure | Strategy-specific |
| Correlation | Aynı ekonomik riskin tekrarını azalt |
| Turnover | Cost-aware penalty |
| Liquidity | Position cap ve impact constraint |
| Concentration | Asset/sector/factor/venue limitleri |
| Cash | Aktif bir risk pozisyonu olarak ele al |

## 13. Risk Engine — Son Söz Sahibi

Risk Engine alpha modelinden bağımsız olmalı ve emir göndermeden önce veto edebilmelidir.
Kurumsal algorithmic trading çerçevelerinde pre-trade controls, threshold/limitler,
erroneous-order prevention, testing, monitoring ve business continuity merkezi
gereksinimlerdir.[2][3]

- Max position / notional limit
- Max portfolio gross/net exposure
- Max sector/factor/currency/asset-class exposure
- Max leverage
- Daily loss / weekly loss / drawdown circuit breaker
- Stale data rejection
- Spread and liquidity gate
- Slippage anomaly gate
- API/venue health gate
- News/event emergency restrictions
- Kill switch and manual reset
- Model confidence / uncertainty threshold
- Order rate and duplicate-order protection
- Portfolio concentration and correlation controls

Canlı üretimde risk limitinin tetiklenmesi strategy process'inin otomatik olarak kapanması,
exposure'ın azaltılması ve yeniden başlatma için manuel/ek güvenlik adımı gibi kontrollere
bağlanabilir; gerçek finansal kurumlarda benzer pre-trade lockdown ve aggregate exposure
monitoring yaklaşımları kullanılır.[2]

## 14. Execution Engine

Execution katmanı "broker API wrapper" değildir. Sinyalden gerçek fill'e kadar olan bütün
süreç burada modellenmelidir.

| Konu | Tasarım |
| --- | --- |
| Order types | Market, limit, stop ve venue desteklediği gelişmiş türler |
| Sizing | Partial fills, minimum lot, tick/step constraints |
| Routing | Venue/broker seçimi; tek venue ile başlayan adapter tasarımı |
| Cost model | Fee + spread + slippage + estimated impact |
| Scheduling | Gerekirse order slicing / time schedule |
| Reliability | Retry, idempotency, reconnect, acknowledgement state machine |
| Reconciliation | Broker state ile local state sürekli eşleştirme |
| Latency | Decision-to-order, order-to-ack, ack-to-fill ölçümü |

NYSE ve diğer borsaların gerçek zamanlı veri ürünlerinde depth of book, top of book, trades
ve auction imbalance gibi farklı akışlar bulunması execution kalitesinin veri altyapısıyla
doğrudan ilişkili olduğunu gösterir.[11] Kripto tarafında da WebSocket bağlantılarının süre,
ping/pong, mesaj oranı ve stream limitleri gibi operasyonel kısıtları vardır; Binance'in
güncel dokümantasyonu bu sınırları açıkça tanımlar.[13]

## 15. Research & Backtest Laboratory

Bu proje için research platformu canlı trading motoru kadar önemlidir. Her deney
reproducible olmalıdır.

- Dataset versioning
- Feature versioning
- Strategy/version hash
- Parameter set
- Training/validation/test windows
- Candidate count / search budget
- Cost assumptions
- Execution assumptions
- Random seeds
- Environment/container version
- Benchmark definition
- Out-of-sample results
- Walk-forward results
- Paper-trading results
- Live shadow results

### 15.1 Validation gates

1. **Naive backtest sanity:** strategy gerçekten kodlandığı gibi davranıyor mu?
2. **No-leak audit:** future data veya revised values geçmişe sızıyor mu?
3. **Cost stress:** base, adverse ve severe transaction-cost senaryoları.
4. **Out-of-sample test:** modelin optimize edilmediği veri.
5. **Walk-forward evaluation:** rolling train/validate/test.
6. **Parameter stability:** yakın parametrelerde performansın çöküp çökmediği.
7. **Regime stability:** yalnız tek bull/bear döneminde çalışıyor mu?
8. **Universe robustness:** yalnız birkaç sembole bağımlı mı?
9. **Search-aware correction:** kaç aday denendi ve selection luck ne kadar?
10. **Forward paper test:** gerçek zamanlı, parasız execution davranışı.
11. **Micro-live test:** küçük sermaye ile gerçek fill ve maliyet.
12. **Graduated capital allocation:** ancak tüm kapılar geçilirse sermaye artırılır.

Backtest overfitting literatürü, yüksek simüle performansın çok sayıda alternatif
yapı/parametre denenmesinden sonra kolayca ortaya çıkabileceğini ve bu performansın
out-of-sample çökebileceğini gösteriyor.[4][5] 2026 tarihli yeni LLM araştırması da aday
strateji sayısının ve arama sürecinin doğrudan kayıt altına alınmasının önemini
vurguluyor.[7]

## 16. Performance Metrics

Tek başına CAGR veya Sharpe yeterli değildir. Sistem her stratejiyi net ve brüt performansla
birlikte raporlamalıdır.

| Kategori | Metrikler |
| --- | --- |
| Return | Cumulative return, CAGR/annualized return, excess return |
| Risk | Max drawdown, volatility, downside deviation, VaR/CVaR where appropriate |
| Risk-adjusted | Sharpe, Sortino, Calmar |
| Trade quality | Win rate, payoff ratio, profit factor, expectancy |
| Execution | Slippage, fill ratio, reject rate, latency, market impact proxy |
| Capacity | Turnover, average daily volume fraction, liquidity stress |
| Robustness | Parameter sensitivity, regime stability, OOS degradation |
| Calibration | Probability calibration for predictive models |
| Search | Candidate count, selection percentile, PBO/DSR-type diagnostics |

## 17. Data Quality & Provenance

Her veri kaynağı bir Data Contract ile tanımlanmalıdır: schema, cadence, timestamp
semantics, delivery SLA, completeness, latency, revision behavior, licensing, retention,
recovery behavior.

| State | Örnek kontrol |
| --- | --- |
| Freshness | Son veri beklenen gecikme içinde mi? |
| Completeness | Beklenen event/bar sayısı geldi mi? |
| Validity | Fiyat/volume negatif veya imkânsız mı? |
| Continuity | Gap veya duplicate var mı? |
| Cross-source | Farklı kaynaklar makul ölçüde uyuşuyor mu? |
| Timestamp | Event time / arrival time ayrımı doğru mu? |
| Corporate actions | Split/dividend sonrası seri doğru mu? |
| Revision | Makro/fundamental data revision geçmişi korunuyor mu? |

## 18. Storage & Data Architecture

Önerilen yapı hot data, warm research data ve cold archive katmanlarından oluşur.

- **Raw immutable zone:** Kaynağın ham cevabı, checksum ve acquisition metadata ile.
- **Canonical zone:** Normalize edilmiş ortak şema.
- **Feature zone:** Feature definitions ve computed values.
- **Research lake/warehouse:** Large-scale backtests ve analytics.
- **Operational DB:** Orders, positions, risk state, configuration.
- **Cache:** Low-latency current state and feature snapshots.
- **Object storage:** Model artifacts, datasets, reports, logs.

Tek veritabanını her şey için kullanmak yerine workload'a göre ayrıştırma önerilir. MVP'de
PostgreSQL + object storage + Redis benzeri bir yapı yeterli olabilir; yüksek hacim ve
tick-level data ihtiyaçları ortaya çıktığında columnar/time-series lakehouse yaklaşımına
geçilebilir.

## 19. Teknoloji Mimarisi

Önerilen başlangıç stack'i: Python 3.12+, FastAPI/HTTP services, PostgreSQL, Redis, object
storage (S3-compatible), message bus/streaming layer, Pandas/Polars/NumPy, scikit-learn +
gradient boosting ailesi, PyTorch yalnız kanıtlanan ihtiyaca göre, Docker, Git, CI/CD ve
güçlü observability.

Araştırma ve production kodu aynı notebook ortamına bağlanmamalı. Research package, backtest
engine ve live execution package net sınırlarla ayrılmalıdır.

| Bileşen | Sorumluluk |
| --- | --- |
| Data Gateway | Vendor/exchange-specific ingestion |
| Normalizer | Canonical instruments, timestamps, units |
| Feature Service | Online/offline feature parity |
| Research Engine | Experiments, backtests, validation |
| Model Registry | Model/version/metadata |
| Signal Engine | Strategy signal computation |
| Portfolio Engine | Position targets |
| Risk Engine | Pre-trade and portfolio veto |
| Execution Engine | Orders/fills/reconciliation |
| Monitoring | Health, PnL, risk, drift, latency |
| Control Plane | Configs, feature flags, kill switch |
| Audit Store | Immutable decision/order trails |

## 20. Observability & Operations

Trading sisteminde "application is healthy" yeterli değildir. Üç ayrı gözlem boyutu gerekir:
system health, trading health ve model health.

- **System:** CPU/RAM, event-loop lag, queue lag, service uptime, DB latency.
- **Data:** freshness, completeness, source outage, schema drift.
- **Trading:** PnL, exposure, order rejection, fill ratio, slippage, latency.
- **Model:** drift, calibration, feature distribution shift, prediction error.
- **Risk:** current drawdown, limit utilization, stress loss, kill-switch status.
- **Incident:** automatic alert, runbook, acknowledgement, recovery evidence.

## 21. Security

- API keys and broker credentials never in source code or Git.
- Separate read-only market-data credentials from trade-capable credentials where possible.
- Production secrets in secret manager/environment injection.
- Least-privilege network rules.
- IP allowlists where provider supports them.
- Exchange withdrawal permission disabled for trading keys whenever unnecessary.
- All privileged actions auditable.
- Human approval for destructive configuration changes.
- Kill switch must work independently of the alpha service.

## 22. Regülasyon ve Operasyonel Sınırlar

Bu proje kişisel araştırma ve kendi hesabında otomasyon olarak başlayabilir; ancak başkasının
parasını yönetmek, yatırım tavsiyesi vermek, sinyal satmak, emir iletimi/portföy yönetimi
hizmeti vermek veya düzenlenmiş bir finansal işletme kurmak farklı hukuki yükümlülükler
doğurabilir. Bu doküman hukuki görüş değildir ve canlı ticari kullanım öncesinde Türkiye ve
ilgili yabancı piyasaların güncel mevzuatı uzman hukukçu ile doğrulanmalıdır.

Türkiye'de kripto varlık hizmet sağlayıcılar 6362 sayılı Kanun değişiklikleri sonrasında
SPK'nın düzenleme ve denetim kapsamına alınmış; III-35/B.1 ve III-35/B.2 sayılı tebliğler 13
Mart 2025'te yürürlüğe girmiştir.[16] Bu, "borsa API'siyle kişisel trade botu kullanmak" ile
"kripto varlık hizmeti sunan işletme" arasındaki hukuki ayrımın dikkatle ele alınması
gerektiğini gösterir.

AB tarafında ESMA'nın MiFID II Article 17 çerçevesi algorithmic trading için sistem
dayanıklılığı, kapasite, trading thresholds/limits, erroneous order prevention,
test/monitoring ve business continuity gibi kontrolleri öne çıkarıyor.[2] Şubat 2026 tarihli
ESMA supervisory briefing'i de pre-trade controls, governance, testing, outsourcing ve AI
kaynaklı yeni riskleri ayrıca ele alıyor.[3]

## 23. Broker / Venue Stratejisi

Tek bir broker veya exchange API'sine doğrudan bağımlı bir sistem tasarlanmamalı. Bunun
yerine Adapter Interface kullanılmalıdır. Böylece execution ve data katmanları
değiştirilebilir.

| Aday | Güçlü taraf | Sınırlama / not |
| --- | --- | --- |
| IBKR | Çok varlık sınıfı, trading + account + market data API ekosistemi.[14] | Market data subscription/line ve venue izinleri ürün bazlıdır. |
| Alpaca | Stocks/ETFs/options/crypto data ve trading API; paper trading kolay.[15] | Kapsam ve gerçek veri lisansları plan ve piyasa bazında ayrılır. |
| Direct exchange APIs | En doğrudan veri/execution | Her piyasa için ayrı entegrasyon, üyelik ve lisans yükü. |
| Crypto venues | 7/24 ve API/WebSocket erişimi yaygın | Venue-specific limitler, liquidation/funding ve operasyonel riskler. |

MVP için bir broker + bir crypto venue yeterlidir. Adapter mimarisi ilk günden hazırlanır;
ikinci venue, ilk sistem güvenilir hale geldikten sonra eklenir.

## 24. Proje Fazları

| Faz | Odak | Çıkış kriteri |
| --- | --- | --- |
| 0 | Finansal piyasa ve sistem temelleri | Market, risk, execution ve veri kavramlarının anlaşılması |
| 1 | Research/Data Foundation | Point-in-time dataset + reproducible research |
| 2 | Backtest Engine | Cost-aware, leak-resistant simulator |
| 3 | Alpha Research | En az birkaç farklı alpha ailesinde hipotez testleri |
| 4 | Validation Framework | OOS, walk-forward, search-aware gates |
| 5 | Paper Trading | Real-time data + simulated orders + reconciliation |
| 6 | Execution & Risk | Pre-trade risk + order state machine + kill switch |
| 7 | Micro-Live | Çok küçük sermaye ile gerçek execution |
| 8 | Production Hardening | Monitoring, recovery, security, audit |
| 9 | Multi-Asset Expansion | Yeni asset adapters + cross-asset portfolio |
| 10 | Continuous Research | Yeni alpha, model, venue ve data kaynakları |

## 25. MVP Tanımı

MVP, "para kazanan bot" değil; üretim kalitesinde araştırma ve kontrollü paper trading
çekirdeğidir. Aşağıdakiler MVP kapsamına alınmalıdır:

- Bir piyasa sınıfı + mümkünse ikinci veri kaynağı.
- Historical + real-time ingestion.
- Canonical instrument and timestamp model.
- Cost-aware backtest engine.
- En az üç farklı alpha ailesi.
- Point-in-time data guard.
- Walk-forward validation.
- Risk engine ve pre-trade checks.
- Paper execution simulator.
- Full audit trail.
- PnL/exposure/slippage dashboard.
- Kill switch.

MVP'nin başarı ölçütü "pozitif backtest" değil; sistemin araştırma sonucunu güvenilir
biçimde üretebilmesi, replay edebilmesi ve paper/live state'i tutarlı şekilde
yönetebilmesidir.

## 26. Başarı / Başarısızlık Kriterleri

### 26.1 Başarı

- Net-of-cost OOS performans pozitif ve istikrarlı.
- Performans tek bir zaman dilimine veya birkaç asset'e aşırı bağımlı değil.
- Parametre perturbation performansı tamamen çökertmiyor.
- Forward/paper sonuçları backtest ile aynı karakteri gösteriyor.
- Gerçek execution maliyeti model varsayımlarından makul aralıkta sapıyor.
- Risk limitleri sistem tarafından güvenilir şekilde uygulanıyor.
- Her canlı karar tam audit edilebiliyor.

### 26.2 Başarısızlık

- Edge sadece backtestte var.
- Net-of-cost performans sıfıra yaklaşıyor/negatif.
- OOS performans çöküyor.
- Performans tek parametre noktasında "iğne" gibi.
- News/LLM sinyalleri narrative üretip sayısal edge üretmiyor.
- Execution slippage edge'i siliyor.
- Risk modelinin farklı rejimlerde koruma sağlamadığı görülüyor.
- Veya sistem veri/operasyon açısından güvenilir değil.

## 27. Maliyet ve Sermaye Gerçeği

Proje maliyetini sadece sunucu faturası olarak düşünmemek gerekir. Veri lisansları, gerçek
zamanlı market data, options/derivatives feeds, historical tick data, broker/venue fees,
slippage, borrow, cloud/storage ve operasyon maliyetleri toplam ekonomik modelin parçasıdır.
Örneğin Alpaca'nın güncel market-data dokümanı ücretsiz planda ABD hisse verisinin IEX ile
sınırlı olduğunu ve daha geniş US equity/options kapsamı için ücretli plan sunduğunu
gösteriyor; bu, "API var" ile "kurumsal kalitede tüm piyasa verisi var" arasındaki farkın
somut bir örneğidir.[15] NYSE de tam depth/order-by-order tarihsel ve gerçek zamanlı
feed'leri ayrı ürünler halinde sunmaktadır.[11][12]

Bu nedenle finansal modelde üç ayrı bütçe tutulmalıdır: (1) research budget, (2)
data/infra budget, (3) risk capital. Trading capital asla model geliştirme veya veri
maliyetlerini görünmez biçimde karşılıyor kabul edilmemelidir.

## 28. En Büyük Teknik Riskler ve Karşılıkları

| Risk | Neden tehlikeli | Karşılık |
| --- | --- | --- |
| Look-ahead bias | Gelecek bilgi yanlışlıkla geçmişte görünür | Availability timestamp + point-in-time datasets |
| Backtest overfit | Tesadüfi optimum strateji | Search registry + OOS + walk-forward + PBO/robustness |
| Data snooping | Çok fazla hipotez arasından en iyiyi seçmek | Trial accounting + pre-registration where possible |
| Survivorship bias | Yalnız hayatta kalan varlıkları test etmek | Historical universe / delisted data |
| Corporate action error | Yanlış adjusted series | Corporate-action aware canonical data |
| Transaction cost underestimation | Kağıt üzerindeki edge silinir | Realistic spread/slippage/impact scenarios |
| Regime shift | Geçmiş ilişki bozulur | Regime engine + degradation monitoring |
| Execution failure | Pozisyon beklenenden farklı oluşur | Order state machine + reconciliation |
| Model drift | Predictive relation zamanla kaybolur | Drift monitoring + retraining gates |
| Operational outage | Sistem yanlış/eksik trade yapabilir | Kill switch + circuit breakers + recovery runbook |
| Security/API key leak | Doğrudan finansal zarar | Secrets isolation + least privilege |

## 29. Proje Dosya ve Kod Yapısı

Uzun vadeli bakım için araştırma, canlı trading ve veri altyapısı ayrılmalıdır. Örnek:

```
project/
├── apps/
│   ├── control-plane/
│   ├── monitoring/
│   └── research-ui/
├── services/
│   ├── ingestion/
│   ├── normalization/
│   ├── features/
│   ├── signals/
│   ├── portfolio/
│   ├── risk/
│   ├── execution/
│   └── reconciliation/
├── research/
│   ├── datasets/
│   ├── hypotheses/
│   ├── experiments/
│   ├── backtests/
│   └── reports/
├── models/
│   ├── registry/
│   └── artifacts/
├── data-contracts/
├── configs/
├── infra/
├── tests/
├── docs/
└── scripts/
```

## 30. Günlük Operasyon Döngüsü

1. Data health check
2. Venue health check
3. Macro/news event calendar refresh
4. Regime update
5. Signal generation
6. Portfolio target calculation
7. Risk approval/rejection
8. Execution
9. Fill reconciliation
10. Post-trade cost analysis
11. Model/feature monitoring
12. End-of-day research snapshot and audit archive

## 31. Nihai Ürün Tanımı

Bu projenin nihai ürünü "bir strateji dosyası" değildir. Ürün; veri toplama, veri doğrulama,
araştırma, strateji, portföy, risk, execution, gözlemleme ve sürekli değerlendirmeyi tek bir
yaşam döngüsünde birleştiren bir trading platformudur.

En doğru zihinsel model şöyledir:

```
WORLD / MARKETS
      ↓
DATA → INFORMATION → FEATURES → MARKET STATE
      ↓
HYPOTHESES → ALPHA MODELS → ENSEMBLE
      ↓
PORTFOLIO → RISK → EXECUTION
      ↓
ORDERS → FILLS → P&L → DIAGNOSTICS
      ↓
RESEARCH FEEDBACK → NEW HYPOTHESES
```

Burada "AI" sadece model katmanı değildir; sistemin bilgi çıkarma, araştırma ve analiz
kapasitesini artırır. Ancak sermaye hareketini tek başına yöneten kontrol katmanı değildir.
Nihai karar zincirinin güvenilirliği, model zekâsından daha değerlidir.

## 32. Sonuç ve Önerilen Nihai Yol

Araştırma sonucunda önerilen proje, "her piyasada çalışan tek bir süper model" değildir.
Önerilen sistem; universal data/feature/research/risk/execution omurgası üzerine
asset-specific alpha ve venue adapterları kuran, search-aware ve cost-aware doğrulama yapan,
riskin alphanın üzerinde veto yetkisine sahip olduğu, paper-to-micro-live geçişi zorunlu
kılan bir multi-asset autonomous trading platformudur.

İlk teknik hedef canlı para kazanmak değil, "kârlı olma ihtimali olan bir edge'i yanlış
pozitiflerden ayırabilecek makineyi" kurmaktır. Ancak bu makine kurulduktan sonra canlı
sermayenin hangi stratejilere aktarılacağı bilimsel kanıtla belirlenebilir. Bu yaklaşım,
özellikle backtest overfitting ve AI hype nedeniyle oluşan yanlış güven riskini
azaltır.[1][4][5][7]

Önerilen ilk uygulama sırası: Data/Research Foundation → Cost-aware Backtest → Validation
Framework → 3–5 Alpha ailesi araştırması → Paper Trading → Risk/Execution hardening →
Micro-live → Multi-asset expansion. Bu sıralama, sistemi gereksiz karmaşıklığa boğmadan
gerçek bir quant platformuna dönüştürmek için en düşük riskli yol olarak
değerlendirilmiştir.

## 33. Kaynaklar

1. CFTC. *Customer Advisory: AI Won't Turn Trading Bots into Money Machines.* 2024. https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/AITradingBots.html
2. ESMA. *Article 17 Algorithmic trading — MiFID II.* current. https://www.esma.europa.eu/publications-and-data/interactive-single-rulebook/mifid-ii/article-17-algorithmic-trading
3. ESMA. *ESMA issues a supervisory briefing on algorithmic trading.* 2026-02-26. https://www.esma.europa.eu/press-news/esma-news/esma-issues-supervisory-briefing-algorithmic-trading
4. Bailey et al. *The Probability of Backtest Overfitting.* 2017. https://scholarworks.wmich.edu/math_pubs/42/
5. Bailey et al. *Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample Performance.* 2014. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659
6. Lopez de Prado. *Machine Learning for Asset Managers (Chapter 1).* 2020. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3558728
7. Gençay. *What survives honest evaluation? Leakage-safe, search-aware assessment of LLM-driven trading strategy discovery.* 2026-08-27. https://arxiv.org/abs/2608.27734
8. Fed St. Louis. *FRED API Overview.* current. https://fred.stlouisfed.org/docs/api/fred/overview.html
9. ECB. *ECB Data Portal API — Data.* current. https://data.ecb.europa.eu/help/api/data
10. SEC. *EDGAR API Development Toolkit / data resources.* current. https://api.edgarfiling.sec.gov/
11. NYSE. *NYSE Real-Time Market Data.* current. https://www.nyse.com/market-data/real-time
12. NYSE. *NYSE Historical Market Data.* current. https://www.nyse.com/market-data/historical
13. Binance. *Websocket Market Streams — Coin Futures.* 2026-09-07. https://developers.binance.com/en/docs/products/derivatives-trading-coin-futures/websocket-market-streams/Connect
14. IBKR. *IBKR API.* current. https://www.interactivebrokers.com/campus/ibkr-api-page/
15. Alpaca. *About Market Data API.* current. https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api
16. SPK. *Kripto Varlık Hizmet Sağlayıcılarına İlişkin İki Tebliğ Yayımlandı.* 2025-03-13. https://spk.gov.tr/duyurular/basin-duyurulari/2025/kripto-varlik-hizmet-saglayicilarina-iliskin-iki-teblig-yayimlandi
17. Borsa İstanbul. *Pay Piyasası.* current. https://borsaistanbul.com/piyasalar/pay-piyasasi
