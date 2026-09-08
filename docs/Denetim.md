---
proje: ScryneQuant
created: 2026-09-08
type: denetim
status: tamamlandi
---
# ScryneQuant — Denetim Raporu

`docs/Proje-Fikri.md` (2627 satır, 65 bölüm) baştan sona okundu. Doküman olağanüstü
kapsamlı ve felsefesi doğru: research-first, risk-first, "backtest kanıttır, garanti
değil". Aşağıdakiler dokümanın zayıflığı değil, **karara bağlanmamış açıkları** — bunlar
kod yazılmadan kapatılmazsa her biri sonradan pahalıya patlar.

Bulgular üç grupta: **(A) mimari çatlaklar** — karar gerektirir; **(B) eksik tanımlar** —
yazılmazsa sessiz hataya dönüşür; **(C) kapsam** — kesilmezse proje bitmez.

---

## A. Mimari çatlaklar

### A1. İki backtest mimarisi aynı anda isteniyor — bunlar uyumsuz

§30 araştırma stack'inde **VectorBT** (vektörize; tüm seriyi tek seferde işler) öneriliyor.
§15.1 ise **event-driven backtest** istiyor. §9.1'deki strateji sözleşmesi
(`on_bar` / `on_tick`) event-driven dünyaya ait ve VectorBT ile çalışmaz. §20 paper trading
ve §14 execution engine de event-driven varsayıyor.

Bu, dokümanın en büyük kapatılmamış çatlağı. İki motor tutulursa strateji fiilen iki kere
yazılır ve "iki motor aynı sonucu veriyor mu" diye üçüncü bir doğrulama yükü doğar; bu
uyuşmazlık quant projelerinin klasik ölüm sebebidir.

**Karar gerekli:** tek motor mu, iki motor mu? → K-001

### A2. Look-ahead bias risk olarak listelenmiş ama yapısal olarak engellenmemiş

§16.1 look-ahead bias'ı "çok yüksek etkili risk" diye doğru teşhis ediyor; önlem olarak
"time-aware pipeline" diyor. Ama §9.1'deki sözleşme stratejiye `data` veriyor — bu bir
DataFrame ise strateji `data.iloc[-1]` yerine `data.iloc[t+1]` yazabilir ve hiçbir şey onu
durdurmaz. Backtest muhteşem sonuç verir, canlıda çöker.

Look-ahead bir disiplin meselesi değil, **tip meselesi** olmalı: stratejiye geleceği
gösteren bir nesne verilmemeli. Bu sonradan eklenebilecek bir şey değil; strateji
sözleşmesinin ilk gününde doğru kurulmalı.

**Karar gerekli:** strateji sözleşmesinin veri erişim modeli → K-002

### A3. Risk motorunun bypass edilemezliği iddia edilmiş, garanti edilmemiş

§9.1 "strateji doğrudan exchange API çağıramaz" diyor ve bunu güvenlik mimarisinin temeli
ilan ediyor — doğru. Ama bunu sağlayan bir mekanizma tanımlanmamış. Bir strateji modülü
`import ccxt` yazarsa hiçbir şey engellemiyor.

Bu, risk register'daki "duplicate order / accidental order" maddelerinin asıl savunma
hattı. Test edilebilir bir kural olmalı.

**Karar gerekli:** izolasyonun nasıl zorlanacağı → K-003

### A4. Promotion sistemi "ileride olabilir" diye yazılmış — oysa asıl koruma bu

§43 backtest→…→live promotion zincirini "projenin en güçlü profesyonel özelliklerinden biri
**olabilir**" diyerek opsiyonel bırakıyor. Ama §56'da listelenen en tehlikeli yanılgıya
("backtest'te kazandı, demek ki çalışıyor") karşı tek yapısal savunma bu. Opsiyonel
bırakılırsa, sabırsızlanıldığı gün elle bir toggle açılır.

**Karar:** promotion gate MVP kapsamındadır, opsiyonel değildir. → K-010

---

## B. Eksik tanımlar

### B1. Bar kapanışı ve fill semantiği hiç tanımlanmamış

Dokümanda hiçbir yerde şu yazmıyor: bir 1h mumunda sinyal **mum kapandığında** mı üretilir,
ve emir **o mumun kapanışından** mı yoksa **bir sonraki mumun açılışından** mı doldurulur?

Bu tek karar backtest sonuçlarını yüzde yüzler mertebesinde değiştirir. Kapanış fiyatından
doldurmak, o fiyatı sinyal üretilirken bilmek demektir — yani gizli bir look-ahead. §16.5
"unrealistic fill assumption"ı risk olarak sayıyor ama fill kuralını yazmıyor.

**Karar gerekli** → K-004

### B2. Zaman dilimi ve timestamp semantiği yok

§7'deki `market_candles` şemasında `timestamp` alanı var ama tz bilgisi ve semantiği yok:
bu mumun **açılış** zamanı mı, kapanış zamanı mı? §38 "clock drift"i güvenlik riski olarak
listeliyor ama temel kuralı koymuyor.

Türkiye UTC+3. Bu yazılmazsa bir yerde 3 saatlik kayma çıkar — ve bu tür hatalar backtest'te
"çalışıyor gibi" görünür. → K-005

### B3. `quality_status` alanı var, değerleri ve etkisi yok

§7 şemasında `quality_status` sütunu tanımlı ama hangi değerleri alacağı ve **backtest'in
bu alana ne yapacağı** yazılmamış. Bir veri boşluğunun üzerinden atlayan backtest sessizce
yanlış sonuç üretir. → K-006

### B4. Fee ve slippage modeli sayısız

§16.5 ve §55 slippage'ın hafife alınmasını "yüksek olasılık, yüksek etki" diye
işaretliyor ama hiçbir sayı vermiyor. Taker fee kaç bps? Slippage sabit mi, spread'in oranı
mı, hacme göre mi? Muhafazakârlık yönü nedir? → K-007

### B5. Kill switch'in davranışı tanımsız

§23 kill switch'i birinci sınıf vatandaş ilan ediyor ama tetiklendiğinde ne olacağı
yazılmamış. Üç farklı davranış mümkün ve yanlışını seçmek doğrudan zarar demek: yeni giriş
durur mu, açık pozisyonlar piyasadan kapatılır mı, yoksa dokunulmadan mı bırakılır? → K-008

### B6. Reproducibility listesi doğru ama uygulanabilir kural yok

§19 "git commit reference tutulmalı" diyor. Ama kirli bir working tree ile çalıştırılan
backtest, commit referansı kaydedilse bile yeniden üretilemez — kaydedilen commit o kodu
tarif etmiyor. → K-009

### B7. Başarı kriterleri ölçülemez

§54 "No duplicate orders", "Safe restart", "Research success" gibi ifadeler kullanıyor ama
eşik vermiyor. Ölçülemeyen kriter, kriter değildir — "bitti" kararını duyguya bırakır.
Roadmap'te her fazın bitti kriteri somut çıktıya bağlandı.

---

## C. Kapsam

### C1. Doküman tek kişinin birkaç yılını tarif ediyor

MVP listesi (§52) 14 kalem görünüyor, ama §26 monitoring, §27 audit log, §28'in 10 sayfalık
dashboard'u, §40'ın 5 test kategorisi ve §41 CI/CD de MVP'nin içindeymiş gibi okunuyor.
Önerilen operasyonel yığın — Prometheus + Grafana + Sentry + Celery + Redis + Temporal +
Docker Compose + Next.js + FastAPI + PostgreSQL + TimescaleDB — kurulup ayakta tutulması
başlı başına bir iş. Bu yük araştırma zamanını yer, ki projenin asıl değeri orada.

Kesim yapıldı: K-011, K-012, K-013.

### C2. Frontend çok erken konumlanmış

§28 on sayfalık bir dashboard tarif ediyor. Ama Faz 1-4 boyunca (veri, indikatör, backtest,
strateji laboratuvarı) gerçekten ihtiyaç duyulan arayüz bir web dashboard'u değil; notebook
ve CLI. Web dashboard asıl olarak **sürekli çalışan bir şey izlenmeye başladığında**
(paper trading) gerekli olur. Öncesinde yazılan her ekran, henüz şekli belli olmayan bir
veri modelinin üzerine kurulur ve yeniden yazılır. → K-012

### C3. ML/LLM katmanı v1 kapsamını kirletiyor

§37 "ilk sürümde LLM kullanılmamalı" diyerek doğru kararı zaten vermiş. Ama §36 (ML
katmanı) ve §58 (multi-agent research assistant) dokümanda hâlâ geniş yer kaplıyor ve
kapsamı bulanıklaştırıyor. Bunlar "Gelecek" başlığına indirildi. → K-013

### C4. Phase 0 kapsam dışı bırakıldı

§53'ün Phase 0'ı bir trading eğitimi fazı tanımlıyor ("Amaç yazılım geliştirmek değil,
sistemi yanlış modellememektir").

**Bu faz 2026-09-08'de Scryne'ın kararıyla kapsam dışına alındı** — eğitim yapılmayacak.
Faz 0 yalnızca teknik doğrulama (spike'lar) fazı olarak duruyor.

Kararın mimari sonucu K-018'de: operatör yargısına dayanan kontroller makineye devredildi,
promotion kapıları eşiği yazılı ve otomatik kontrol edilir hale getirildi.

---

## D. Dokümanın doğru yaptıkları — korunacak, sulandırılmayacak

Denetim sadece hata aramak değil. Aşağıdakiler nadir bulunan doğrular:

- **§4.3 No Fake Alpha** ve §56'daki yanılgı listesi. Çoğu kişisel trading projesi tam
  buradan ölür.
- **§9.1 Strategy → Intent → Risk → Execution ayrımı.** Mimarinin belkemiği.
- **§10 Signal Model** — stratejinin "emir" değil "niyet" üretmesi.
- **§25 Position Reconciliation** ve §38'deki state desync teşhisi. Amatör projelerin
  neredeyse hepsinde yok.
- **§51 Regülasyon farkındalığı.** Buna tek operasyonel kural eklendi: sistem yalnızca
  kendi hesabında, kendi parasıyla çalışır. → K-014
- **§61'in ilk somut hedefi.** Roadmap doğrudan bunun üzerine kuruldu; §60'ın kapsamlı
  tanımı üzerine değil.

---

## E. Kapatılamayan açıklar — spike gerektirir

Aşağıdakiler masa başında karara bağlanamaz, ölçüm ister. Faz 0'a alındı:

| Konu | Neden bilinmiyor | Nasıl kapanır |
| --- | --- | --- |
| Binance API erişimi | Türkiye'den erişim, KYC durumu, rate limit ve Spot Testnet'in güncel hâli doğrulanmadı | Gerçek istek atan küçük bir spike |
| Veri hacmi ve indirme maliyeti | 3-5 yıllık 1h ve 1m verinin gerçek boyutu ve indirme süresi tahminî | Bir sembol indirilip ölçülür |
| Saklama formatı performansı | Parquet + DuckDB seçimi ölçülmeden yapıldı (K-011) | Ölçülen hacim üzerinde sorgu süresi testi |

**Bu üçü kapanmadan Faz 1 mimarisi dondurulmaz.**
