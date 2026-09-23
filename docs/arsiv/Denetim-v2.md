---
proje: ScryneQuant
created: 2026-09-12
type: denetim
surum: 2
status: tamamlandi
---
# ScryneQuant — Denetim Raporu v2

`docs/arsiv/Proje-Fikri-v2.md` (docx'in tam metni, 33 bölüm) baştan sona okundu. Bu denetim
v1'inkinden farklı bir soruya cevap veriyor. v1 denetlendiğinde ortada kod yoktu; bugün 47
karar, 1143 test, 9 fazın 7'si kapalı, 38 kayıtlı hipotez ve 30 günlük bir gözlem koşusu var.
Soru *"bu doküman ne istiyor"* değil: **istediğinin ne kadarı zaten var, ne kadarı mevcut
kararlarla çelişiyor, ne eksik.**

**Kısa sonuç.** Doküman v1'in felsefesini değiştirmiyor, **kapsamını** değiştiriyor. Altı
tasarım ilkesinin altısı da (evidence-first, point-in-time, cost-aware, search-aware, risk
veto, progressive activation) bu projede zaten **kural ve testle zorlanıyor**. Değişen
şunlar: tek sembol → çok enstrüman ve çok varlık sınıfı; fiyat → fiyat + türev + makro +
haber; kural tabanlı → kural + yetkisi sınırlı ML; tek strateji → portföy.

**En önemli bulgu.** Dokümanın MVP tanımındaki (§25) 12 maddenin 9'u karşılanmış, 3'ü kısmi.
"En az üç farklı alpha ailesi" maddesi de karşılanmış, üçü de **kaldı** (trend/momentum, mean
reversion, türev/funding; K-044, K-045). Yani dokümanın MVP'si yapılacak iş değil, büyük
ölçüde **yapılmış ve ölçülmüş** iş. Yeni iş MVP'nin ötesinde: yeni bilgi kaynakları, çok
enstrümanlı araştırma çekirdeği ve ikinci varlık sınıfı.

Bulgular beş grupta: **(0) eşleme**: doküman ne istiyor, projede ne var; **(A) mimari
çatlaklar**: karar gerektirir; **(B) eksik tanımlar**: yazılmazsa sessiz hataya dönüşür;
**(C) kapsam**: kesilmezse proje bitmez; **(D) hukuki.**

---

## 0. Eşleme

Durum: ✅ var ve testle zorlanıyor · 🟡 kısmi · ❌ yok.

### 0.1 MVP (§25)

| Madde | Projede | Durum |
| --- | --- | --- |
| Bir piyasa sınıfı + mümkünse ikinci veri kaynağı | Kripto spot (Binance) + perpetual funding geçmişi (K-042) | ✅ |
| Historical + real-time ingestion | Faz 1 indirici (idempotent) + Faz 6 WebSocket akışı | ✅ |
| Canonical instrument and timestamp model | Zaman: K-005 (UTC epoch ms, bar açılışı). Enstrüman: yalnızca Binance spot filtreleri (`SembolKurallari`); enstrüman kimliği = ticker | 🟡 |
| Cost-aware backtest engine | Faz 3; K-004, K-007, K-021 | ✅ |
| En az üç farklı alpha ailesi | Trend/momentum (4 strateji), mean reversion, türev (funding, 3 hipotez), çok faktörlü. **Hepsi kaldı** | ✅ ölçüldü |
| Point-in-time data guard | Bar için yapısal (K-002 `ctx`, look-ahead testi). Bar olmayan veri için genel bir *available_time* modeli yok | 🟡 |
| Walk-forward validation | 16 katman; `wf_katman_basari` kapısı | ✅ |
| Risk engine ve pre-trade checks | Faz 5; üç katmanlı bypass koruması (K-032) | ✅ |
| Paper execution simulator | Faz 6; backtest ile aynı fill yolu (K-001) | ✅ |
| Full audit trail | Zincir hash'li, append-only audit (SQLite, K-034) | ✅ |
| PnL/exposure/slippage dashboard | PnL ve maruziyet var. Slippage fill'lere uygulanıyor ama "gerçekleşen vs model" metriği yok | 🟡 |
| Kill switch | K-008 + SAFE_MODE; elle çıkış | ✅ |

### 0.2 Doğrulama kapıları (§15.1) ↔ K-019

| # | Dokümandaki kapı | Projede | Durum |
| --- | --- | --- | --- |
| 1 | Naive backtest sanity | Bağımsız referans, kapalı formül (K-029) | ✅ |
| 2 | No-leak audit | Look-ahead testi, iki yönlü sabit bozma (K-002). Revizyonlu veri henüz yok | ✅ bar · ❌ revizyon |
| 3 | Cost stress (base/adverse/severe) | `stres_dayanikliligi`: temel, 2×, 3× slippage, 2× fee | ✅ |
| 4 | Out-of-sample | `oos_sharpe` (K-044: 1,02), `oos_is_orani` | ✅ |
| 5 | Walk-forward | `wf_katman_basari` | ✅ |
| 6 | Parameter stability | `parametre_kararliligi` katmanlar arası seçim değişkenliğini ölçüyor. Dokümanın tanımı başka: *komşu parametrede performans çöküyor mu* (pertürbasyon) | 🟡 |
| 7 | Regime stability | Yok | ❌ |
| 8 | Universe robustness | Yok, ve tek sembolde **yapısal olarak ölçülemez** | ❌ |
| 9 | Search-aware correction | Hipotez defteri + ön kayıt (K-039), ölçülmüş düzeltme (K-044) | ✅ |
| 10 | Forward paper test | Promotion `paper` aşaması; altyapı Faz 6 | ✅ altyapı |
| 11 | Micro-live | Faz 8 | ⏳ |
| 12 | Graduated capital allocation | Sayısal kural yok; Faz 8 notu *"sermaye artırma kararı fazın çıktısına bakılarak verilir"* diyor. Bu bir insan yargısı ve K-018 ile çelişiyor | ❌ |

### 0.3 Diğer bölümler

| Bölüm | Projede | Durum |
| --- | --- | --- |
| §13 Risk limitleri | Var: maruziyet, işlem başı risk, günlük zarar, drawdown, ardışık kayıp, cooldown, volatilite guard, bayat veri (K-037), duplicate emir (K-040), SAFE_MODE. Yok: haftalık zarar, varlık sınıfı/sektör/korelasyon/konsantrasyon, kaldıraç, spread/likidite, slippage anomalisi, venue sağlığı, olay kısıtı, model güveni, emir oranı | 🟡 |
| §14 Execution | Market ✅, limit + iptal ✅ (K-047), stop ❌, kısmi dolum 🟡 (state machine var, gerçekte ölçülmedi), tek venue adaptörü ✅, idempotency/retry ✅ (K-040/041), mutabakat ✅ (K-046), market impact ❌, emir bölme ❌, gecikme ölçümü 🟡 | 🟡 |
| §16 Metrikler | 29 metrik (Sharpe, Sortino, Calmar, MDD, PF, win rate…). Yok: VaR/CVaR, kapasite (ADV oranı), kalibrasyon, PBO. DSR yalnızca K-044'te çapraz kontrol | 🟡 |
| §17 Veri kalitesi | Freshness, completeness, validity, continuity, timestamp ✅ (K-006, K-024). Cross-source ❌. Corporate actions: kripto karşılığı (yeniden adlandırma, redenominasyon) ❌. Revision: ilgili veri henüz yok | 🟡 |
| §18 Depolama | Canonical zone = Parquet (K-011), operasyonel DB = SQLite (K-034), araştırma = `runs/`. **Ham değişmez bölge yok**: ham yanıt değil, ayrıştırılmış bar saklanıyor. Cache ve object storage yok (ihtiyaç ölçülmedi) | 🟡 |
| §19 Stack | Python, FastAPI, pandas/numpy, Git ✅. PostgreSQL: K-034'ün ölçülmüş koşullarına bağlı. Redis, object storage, message bus, Docker: K-011 ile dışarıda. ML kütüphaneleri: K-013 ile dışarıda. CI/CD ❌ | 🟡 |
| §19 Feature Service (online/offline parity) | K-001'in tek kod yolu parity'yi **inşa gereği** sağlıyor: backtest = paper = live. Ayrı bir feature store gerekmiyor | ✅ |
| §20 Observability | Trading ve risk ✅ (dashboard), veri 🟡 (bayatlık), sistem 🟡, model ❌, olay/alarm ❌ (kesinti sebebi kaydediliyor ama alarm yok) | 🟡 |
| §21 Güvenlik | Sırlar git dışında ✅ (`.env` gitignore'da). Okuma/işlem anahtarı ayrımı ❌, IP allowlist ❌, çekim yetkisi kapalı anahtar ❌, **alpha servisinden bağımsız kill switch** 🟡 | 🟡 |
| §23 Broker/venue | Adaptör arayüzü + Binance ✅. Broker (IBKR/Alpaca) ❌ | 🟡 |
| §27 Üç bütçe | Yok | ❌ |
| §29 Kod yapısı | Modüler monolit, sert paket sınırları, import grafiği testle korunuyor (K-003, K-027, K-032) | farklı, bkz. A7 |
| §30 Günlük operasyon döngüsü | Parçaları var (bayatlık, mutabakat), döngü olarak yok | ❌ |

### 0.4 Fazlar (§24) ↔ Roadmap

| Doküman | Projede | Durum |
| --- | --- | --- |
| 0 Temeller | Faz 0 (spike'lar). Dokümanın çıkış kriteri *"kavramların anlaşılması"*: **K-018'in kaldırdığı kısım bu** | ✅ (K-018 geçerli, bkz. A10) |
| 1 Research/Data Foundation | Faz 1 | ✅ bar · ❌ PIT genel model |
| 2 Backtest Engine | Faz 2 + 3 | ✅ tek enstrüman |
| 3 Alpha Research | Faz 4 + dönüş 1-5 | ✅ 3 aile kaldı |
| 4 Validation Framework | Faz 4 + K-039/K-044 | 🟡 (kapı 6-8, 12) |
| 5 Paper Trading | Faz 6 | 🔄 30 gün |
| 6 Execution & Risk | Faz 5 + 7 | ✅ |
| 7 Micro-Live | Faz 8 | ⏳ strateji yok |
| 8 Production Hardening | yok | ❌ |
| 9 Multi-Asset Expansion | yok | ❌ |
| 10 Continuous Research | yok | ❌ |

---

## A. Mimari çatlaklar

### A1. "Otomatik olarak canlıya taşıyan" ile K-010'un elle onayı çelişiyor

§1 *"yalnızca doğrulama kapılarından geçen stratejileri otomatik olarak canlı piyasaya
taşıyabilen"* diyor. K-010 ise zincirin son adımını elle onay olarak sabitliyor ve bu onay
kaldırılamaz. Doküman kendi içinde de ikiye bölünmüş: §3 "human override", §21 "human
approval for destructive configuration changes" diyor.

Çözüm iki yönü ayırmakta. **Risk azaltan** her şey (reddetmek, SAFE_MODE, maruziyet
küçültmek, koşuyu durdurmak) otomatik olabilir ve öyle olmalı. **İzin artıran** her şey
(canlıya almak, sermaye artırmak, limit gevşetmek, yeni enstrüman açmak) önce makine
kapısından, sonra elle onaydan geçer. Bu yeni bir ilke değil. K-037'nin *"engelleyen katman
risk motorunun dışında olabilir, izin veren olamaz"* ilkesi yetki düzeyine taşınıyor.
"Autonomous" sözcüğü operasyonu tarif ediyor; yetkiyi değil.

**Karar gerekli** → K-050

### A2. ML/LLM kapsama giriyor, K-013 dışarıda tutuyor. Doküman en tehlikeli sızıntıyı adlandırmıyor

§8 ve §11, ML/LLM'i yetki tablosuyla birlikte kapsama alıyor. Tablonun kendisi doğru ve
sıkı: semantic AI ve research AI yetkisiz, predictive ML yalnızca doğrulama kapısından
sonra. K-013'ün gerekçesi (*"ML overfitting yüzeyini büyütür"*) hâlâ doğru. Ama artık
ölçülmüş bir karşılığı var: K-039/K-044 her çekilişi sayıyor ve eşiği yükseltiyor. Yani ML
artık **fiyatlanabiliyor**.

Dokümanın adlandırmadığı risk şu: **bir LLM'in eğitim verisi, geçmişteki bir t anı için
gelecektir.** 2023 haberini okuyan 2026 modeli o haberden sonra ne olduğunu biliyor. Bu
nedenle LLM'den türetilen bir özellik, K-002'nin `ctx` sözleşmesini kodda hiçbir satır
çiğnemeden delebilir. Look-ahead testi bunu yakalayamaz, çünkü sızıntı veride değil
modelin ağırlıklarında. [7]'nin "leakage-safe" uyarısının somut hâli bu.

İkinci sorun determinizm. LLM çıktısı sürüme ve örneklemeye bağlı, dolayısıyla K-009'un
*"aynı girdi aynı çıktı"* kuralını kendiliğinden sağlamaz.

**Karar gerekli** → K-049

### A3. Arama yapılacak aile sayısı K-044'ün aritmetiğiyle çarpışıyor

Doküman 3-5 alpha ailesi (§32), dokuz aday aile (§4) ve "continuous research" (Faz 10)
istiyor. K-044 ise ölçtü: 31 çekilişte %5'lik `oos_sharpe` sınırı 1,02 ve **her yeni
çekiliş bu sınırı yükseltiyor.** K-045 de bu yüzden yeni bir büyük arama programı açmadı.
Kısıtlı bir istisna bıraktı: *"ölçüyle gerekçelendirilmiş, belirgin biçimde farklı bir
bilgi kaynağı."*

Dokümanın yeni aileleri (cross-sectional, makro, olay, haber) tam olarak bu istisnanın
tanımına giriyor. Ama istisna tek başına bir süreç değil. Her yeni program sayacı
büyütecek ve kendi geçmek zorunda olduğu duvarı yükseltecek. Bu önceden hesaba
katılmazsa program, bulduğu şeyi geçiremeyeceğini sonunda öğrenir.

İki kaçış yolu var ve ikisi de yasak olmalı:

- Defteri program başına ayırmak. *"Kripto cross-sectional ayrı defter, makro ayrı defter"*
  demek, sonunda hepsinin arasından en iyisini seçen kişi için sayacı sıfırlamaktır.
- Programın sonunda kaç çekiliş yapılacağına karar vermek. Bu, K-042'nin durma kuralının
  yasakladığı şeydir.

**Karar gerekli** → K-051

### A4. Çok enstrüman ve portföy, tek enstrümanlı motorun sözleşmesini aşıyor

`backtest/motor.py` kendini *"tek sembol, tek strateji, spot, uzun-yönlü"* diye tanımlıyor
ve bu bilinçli bir v1 kapsamı. Cross-sectional aile, evren boyunca eşzamanlı bir `ctx` ve
sinyal yerine **hedef portföy** üreten bir sözleşme istiyor (§12). Bu genişleme üç
değişmez kuralı birden sınıyor:

- **K-001 (tek kod yolu):** Çok enstrümanlı motor ikinci bir motor olamaz. Tek enstrüman
  onun özel hâli olmalı ve Faz 3'ün referans testleri o özel hâlde bit düzeyinde aynı
  kalmalı.
- **K-002 (gelecek ifade edilemez):** Evrenin **kendisi** zamana bağlı. t anında listelenmemiş
  bir sembol `ctx`te görünürse, bu da bir look-ahead'dir (hayatta kalma yanlılığı). `ctx`
  yalnızca t'ye kadarki barları değil, t'deki evren üyeliğini de kesmek zorunda.
- **K-003 (strateji I/O yapamaz):** Evren seçimi (hacme göre ilk N) bir veri sorgusu gibi
  görünüyor. Stratejinin içinde olamaz; `ctx`e hazır gelir.

**Karar gerekli** (ilke şimdi, tasarım Faz 10'da) → K-052

### A5. Rejim motoru kendi başına bir sızıntı kaynağı

§9 rejimi *"olasılıksal"* ve *"koşullu ağırlık üreten"* bir katman olarak tarif ediyor. Doğru
tarif, ama iki tuzağı var:

1. **Yumuşatılmış olasılık geleceği görür.** HMM benzeri modellerin standart çıktısı
   (smoothed) t anındaki rejimi tüm serinin ışığında verir. Geriye dönük rejim etiketiyle
   yapılan her backtest bu yüzden kusursuz görünür. Yalnızca **filtrelenmiş** (t'ye kadarki
   veriyle hesaplanan) olasılık kullanılabilir. Rejim modeli de walk-forward'ın her
   katmanında yalnızca eğitim penceresinde kurulmalıdır.
2. **Koşullu ağırlık bir maruziyet kararıdır.** "BUY/SELL üretmez" doğru, ama "bu ailenin
   bu rejimde risk bütçesi yarıya insin" sermayeyi hareket ettirir. Rejim motoru bu yüzden
   strateji/portföy tarafında yaşar ve risk motorunun onayından geçer. İzin veren bir
   katman olamaz (K-037). Engelleyen olabilir: *"stres rejiminde yeni giriş yok"* serbest.

Rejim tanımının kendisi (kaç rejim, hangi model) de bir **çekiliştir** ve deftere girer.

→ K-052'ye bağlayıcı kısıt olarak girer; tasarım Faz 12'de.

### A6. Depolama önerisi ölçülmüş bir kararla çelişiyor. Ama koşulluymuş gibi okunmalı

§18-19 MVP için PostgreSQL + Redis + object storage + message bus + Docker öneriyor. K-011
ve K-034 bunları ölçerek dışarıda tuttu. K-034'ün üç geri dönüş koşulu 2026-09-11'de
ölçüldü ve hiçbiri gerçekleşmemişti. Dokümanın kendi cümlesi de koşullu: *"yeterli
**olabilir**"*, *"ihtiyaçlar ortaya çıktığında"*.

Çözüm bir çelişkiyi çözmek değil, zamanlamayı doğru okumak. **K-034'ün 3. koşulu (çok
sembollü çalışma) bu vizyonla gerçekleşecek** ve K-011'in dosya düzeni koşulu da (*"çok
sembollü çalışmaya geçildiğinde"*). İkisi de Faz 9'un başında yeniden ölçülür. Ölçüm
çıkmadan servis eklenmez.

→ K-052

### A7. Dokümanın kod yapısı (§29) mikroservis düzeni; proje modüler monolit

`services/ingestion`, `services/risk`… gibi bir düzen **süreç sınırı** ima ediyor. Bu
projenin güvenlik garantileri ise **import sınırlarına** dayanıyor: K-003, K-027 ve K-032'nin
kesme noktası testi. Bu garantiler bir paketin içinde statik olarak kanıtlanıyor. Servislere
bölmek onları ağ protokolüne taşır ve kanıtlanabilir olmaktan çıkarır. Doküman §29'u
"örnek" diye veriyor. Bileşen tablosu (§19) mevcut paketlere birebir eşleniyor (bkz.
Final-Doküman).

→ K-052

### A8. Kill switch alpha servisinden bağımsız değil

§21: *"Kill switch must work independently of the alpha service."* Bugünkü kill switch
(SAFE_MODE) risk motorunun içinde, yani trader sürecinin içinde. Süreç kilitlenirse (sonsuz
döngü, takılan ağ çağrısı) kill switch de onunla birlikte kilitlenir. K-043'ün bayrak dosyası
bir **istek**, zorlama değil: onu da aynı süreç okuyor.

Paper'da bu kabul edilebilir, çünkü para yok. Canlıda değil. Faz 8'den önce süreç dışından
çalışan bir yol gerekiyor: borsadaki açık emirleri doğrudan iptal eden, trader sürecini
sonlandıran ve yeniden başlamayı SAFE_MODE'a kilitleyen bağımsız bir komut.

→ Faz 8 ön koşulu (Roadmap)

### A9. Kaldıraçlı enstrüman K-008'in temelini kaldırır

§5 "crypto spot/perpetuals" diyor, §13 *"exposure'ın azaltılması"* diyor. K-008/2 kill
switch'te pozisyonu **kapatmıyor**, çünkü *"spot piyasada likidasyon riski olmadığı için
pozisyonu tutmak güvenlidir — bu karar futures'a geçilirse yeniden verilmelidir."* Perpetual
ile işlem yapmak bu gerekçeyi ortadan kaldırır: likidasyon varken tutmak güvenli değildir.

Perpetual **bilgi kaynağı** olarak zaten kullanılıyor (K-042) ve öyle kalabilir. **İşlem
aracı** olarak açılması, likidasyon-bilinçli bir kill switch kararı ve kaldıraç limiti
olmadan yapılamaz.

→ K-048 kapsamında: kaldıraçlı işlem açılmıyor

### A10. Dokümanın Faz 0 çıkış kriteri K-018'in kaldırdığı şey

Doküman Faz 0'ın çıkış kriterini *"market, risk, execution ve veri kavramlarının
anlaşılması"* olarak koyuyor. Bu, Scryne'ın 2026-09-08'de kaldırdığı eğitim fazının
kendisi. K-018 bu kaldırmanın zorunlu sonucunu yazmıştı: hiçbir güvenlik kontrolü
operatörün piyasa bilgisine dayanamaz, her kapı sayısaldır.

Yeni doküman K-018'i geri çevirmiyor, bu kriteri bir fazın içeriği olarak tekrarlıyor. K-018
geçerli kalıyor. Dokümanın aynı ilkeyi başka yerde güçlendirdiğine dikkat: §15.1'in 12
kapısı, K-018'in *"sonuçlara bak ve karar ver bir kapı değildir"* cümlesinin genişletilmiş
hâli.

---

## B. Eksik tanımlar

### B1. PIT gözlem modelinde `ctx` hangi zamana göre keser?

§7.2 beş alan sayıyor (event_time, available_time, ingested_time, effective_from,
effective_to) ama **hangisinin kesme zamanı olduğunu** söylemiyor. Cevap `available_time`.
Bir makro verinin event_time'ı "Mart enflasyonu", available_time'ı açıklandığı an. Kesmeyi
event_time'a göre yapmak, açıklanmamış veriyi kullanmaktır.

İkinci boşluk: available_time **bilinmediğinde** ne olur? ALFRED vintage'ları gün
çözünürlüğünde veriyor, saat vermiyor. K-007'nin ilkesi burada da geçerli olmalı:
belirsizlikte kötü yöne. Gün çözünürlüğündeki veri o günün sonunda (UTC 23:59:59.999)
kullanılabilir sayılır, günün başında değil.

### B2. Hayatta kalma yanlılığı: evren üyeliği de bir zaman serisi

§28 riski adlandırıyor, karşılığını (*"historical universe / delisted data"*) koyuyor, ama
verinin **var olup olmadığını** sormuyor. Kripto için ölçüldü (Spike 6): delist edilmiş
paritelerin geçmişi Binance'in açık arşivinde duruyor. Evren her ay yalnızca o ay listelenmiş
ve likit olan sembollerden, **yalnızca geçmiş veriyle** kurulmalı.

### B3. Kriptonun "corporate action"ı: yeniden adlandırma ve redenominasyon

§17 "corporate actions: split/dividend" diyor ve bunu hisse senedi olayı olarak düşünüyor.
Kriptonun karşılığı başka: LUNA → LUNC (aynı ticker'da **başka bir varlık**), BCC → BCH,
token swap'lar, redenominasyon (1000SHIB tipi). **Enstrüman kimliği ticker olamaz.** Aksi
hâlde iki farklı varlığın geçmişi aynı seride birleşir ve arada imkânsız bir getiri
görünür.

### B4. Evren seçimi, portföy yöntemi ve rejim tanımı birer çekiliştir

K-039 bir hipotezi (strateji, timeframe, veri hash'i, ızgara, seçim yöntemi) beşlisi olarak
tanımlıyor. Çok enstrümanlı dünyada üç yeni serbestlik derecesi doğuyor ve üçü de *"aynı
veriye yeni soru sormanın bir biçimi"*:

- evren tanımı (ilk 30 mu, ilk 100 mü; hacim eşiği)
- portföy kurma yöntemi (eşit ağırlık, oynaklık ayarlı, optimizasyon, turnover cezası)
- rejim tanımı

Kimliğe girmezlerse bedava çekiliş olurlar. K-039'un Faz 4'e dönüş 2'de seçim yöntemi için
yaşadığı düzeltmenin aynısı.

### B5. LLM çıktısı bir hesaplama değil, bir veri kaynağıdır

A2'nin determinizm tarafı: LLM çıktısı backtest içinde **hesaplanamaz**. Bir kez üretilir,
ham değişmez bölgeye (model kimliği, prompt hash'i, girdi hash'i, üretim zamanıyla) yazılır
ve backtest dondurulmuş çıktıyı okur. Veri seti hash'i o dosyanın hash'idir (K-009).

### B6. "Graduated capital allocation" sayısal değil

§15.1/12 *"ancak tüm kapılar geçilirse sermaye artırılır"* diyor, kapıların ne olduğunu
söylemiyor. Bugünkü roadmap'te de Faz 8 notu insan yargısına bırakıyor. K-018 gereği bu
sayısal olmak zorunda. Sayılar ancak Faz 8'in ilk koşusunda kalibre edilebilir, ama
**biçim** şimdi yazılabilir: kademe, asgari canlı süre ve drift üst sınırı. → K-050

### B7. Üç bütçe (§27) rakamsız

Araştırma, veri/altyapı ve risk sermayesi ayrı tutulacak. Rakamlar yok. Risk sermayesi Faz
8'in boyutunu, veri bütçesi hangi programların açılabileceğini belirliyor. Ücretli veri
gerektiren haber arşivi, US equity SIP ve opsiyon yüzeyi bu bütçeye bağlı. Bu sayılar
yalnızca Scryne'dan gelebilir. → açık, Final-Doküman

### B8. "Shadow" aşaması tanımsız

§3: *"Paper → shadow → micro-live → controlled live."* Projede `paper` (canlı veri, simüle
fill) ve `gozlem` (promotion'sız paper, K-035) var; shadow yok. Doğal tanımı şu: **canlı
modun tamamı, emir gönderimi hariç.** Gerçek hesabın bakiyesi okunur, emir kurulur,
doğrulanır ve deftere "gönderilmedi" diye yazılır. Paper'ın ölçemediği şeyi ölçer: gerçek
bakiye, gerçek sembol kuralları, karar→emir gecikmesi. → Faz 8'in ilk adımı

### B9. Olay takvimi kısıtı bir engelleyici katmandır

§13 "news/event emergency restrictions" diyor. Kriptoda da planlı yüksek etkili olaylar var
(FOMC, CPI). *"Olaydan ±N dakika yeni giriş yok"* bir **engelleyici** katmandır ve K-037
gereği risk motorunun dışında olabilir. N bir parametre ve iştah değil ölçüm olmalı
(K-033). Faz 12'de.

### B10. Günlük döngünün "gün"ü

§30 bir gün sonu varsayıyor; kripto 7/24. K-005 gereği gün sınırı UTC 00:00'dır. "End-of-day
snapshot" o anda alınır.

---

## C. Kapsam

Doküman 9 alpha ailesi × 6 varlık sınıfı × haber/NLP × ML × opsiyon istiyor. Tek kişilik bir
proje için bu kesilmezse bitmez. Dokümanın kendisi de sıralı açılım öneriyor (§32).

| # | Kalem | Karar | Gerekçe |
| --- | --- | --- | --- |
| C1 | HFT, market making, co-location, alfa olarak mikro yapı | **Dışarıda** | Doküman da ilk hedef saymıyor (§4). Mikro yapı yalnızca execution kalitesi için |
| C2 | Opsiyon | **Ertelendi** (ikinci varlık sınıfından sonra) | Vol yüzeyi verisi ücretli; risk modeli başka bir iş |
| C3 | Borsa İstanbul | **Ertelendi** | Doküman da *"canlı erişim uygunluğu doğrulanınca"* diyor |
| C4 | FX, kripto dışı futures | **Ertelendi** | İkinci varlık sınıfı oturduktan sonra |
| C5 | Haber/NLP | **Makro ve türev programlarından sonra**, spike ile | Geçmişe dönük, doğru ilk-yayın zamanlı haber arşivi ücretli. Ücretsiz akışların geçmişi yok, yalnızca ileriye biriktirilebilir |
| C6 | Alternatif veri | **Dışarıda** | Doküman da *"yalnızca kanıtlanırsa"* diyor |
| C7 | Redis, message bus, object storage, Docker, K8s | **Koşullu** (K-034 kalıbı) | Ölçülmüş ihtiyaç doğunca |
| C8 | ML | **Kural tabanlı aileler yeni veri kaynaklarında ölçüldükten sonra**; scikit-learn/GBM; PyTorch yok | K-049 |
| C9 | Çoklu kripto venue | **Ertelendi** | Doküman da *"ilk sistem güvenilir hâle geldikten sonra"* diyor |
| C10 | `apps/control-plane`, `apps/research-ui` | **Yok.** Dashboard (K-036) tek UI, yazma işlemleri CLI'da | Salt okunur dashboard bir güvenlik özelliği (K-043'ün gerekçesi) |
| C11 | Kaldıraç ve kısa pozisyon | **Açılmıyor** | A9; K-008 yeniden verilmeden olmaz |

---

## D. Hukuki

- **D1.** K-014 (kendi hesabı, kendi parası) aynen geçerli ve doküman §22 aynı çizgiyi
  çiziyor.
- **D2.** SPK'nın 2025 düzenlemesi (III-35/B.1, B.2) **hizmet sağlayıcıyı** düzenliyor.
  Proje K-014 içinde kaldıkça hizmet sağlayıcı değil. Ama kullanılan venue'nun Türkiye
  yerleşiği bir kullanıcıya hizmet verme statüsü bu düzenlemeden etkilenebilir. K-015 teknik
  erişimi ölçtü (451 yok), **hukuki erişimi** ölçmedi. → Faz 8 ön koşulu: kaynaklı
  doğrulama.
- **D3.** İkinci varlık sınıfı için Türkiye yerleşiğinin broker hesabı açabilmesi (Alpaca/IBKR)
  ve veri lisansı kapsamı doğrulanmadı. → Faz 14'ün spike'ı.
- **D4.** Haber içeriği lisanslıdır; saklama ve türetme hakları kaynağa göre değişir. Data
  contract'ın `licensing` alanı dolmadan kaynak kullanılmaz (§17).

---

## E. Kaynaklar hakkında

Dokümanın 17 kaynağı bağımsız olarak doğrulanmadı. Hiçbir karar tek başına bu kaynaklardan
birine dayanmıyor. [7]'nin savunduğu *search-aware* değerlendirme bu projede zaten kendi
ölçümüyle uygulanıyor (K-039, K-044). [4]/[5]'in PBO ve DSR'si doğrulama kapıları v2'nin
adayları (K-054). Bu projede literatür bir yöntem önerisi olarak kullanılır; eşik ölçümle
belirlenir.

---

## Sonuç: verilmesi gereken kararlar

| No | Konu | Kapatır |
| --- | --- | --- |
| K-048 | Vizyon v2: platform, v1 çekirdek olarak korunur; kapsam ve kesimler | 0, A9, A10, C |
| K-049 | AI/ML yetki sınırları; LLM eğitim-verisi sızıntısı; LLM çıktısı veri kaynağıdır | A2, B5 |
| K-050 | Otomasyon asimetrisi: risk azaltan otomatik, izin artıran kapı + onay; kademeli sermaye | A1, B6, B8 |
| K-051 | Tek, global hipotez defteri; program başına ön kayıtlı arama bütçesi | A3, B4 |
| K-052 | Mimari: modüler monolit korunur; tek kod yolu çok enstrümana genişler; PIT gözlem modeli; servisler koşullu | A4-A7, B1-B3 |
| K-053 | İlk genişleme kripto içinde (çoklu sembol + türev + makro); ikinci varlık sınıfı spike ile | §5, §23, Spike 6 |
| K-054 | Doğrulama kapıları v2: dört yeni kapı, eşikleri açık; eskiler gevşemez | 0.2 |
