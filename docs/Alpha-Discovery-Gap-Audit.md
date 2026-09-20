---
proje: ScryneQuant
faz: 16
tur: AUDIT / DESIGN (kod yok, deney yok, çekiliş yok, commit yok)
tarih: 2026-09-20
type: rapor
durum: taslak — Scryne onayı bekliyor
---
# Alpha Discovery Gap Audit

**Soru:** Mevcut alpha family/selector katmanını değiştirmek yerine, gate seviyesine
(`oos_sharpe ≥ 1,04` + 10 kapı + 30 gün paper) ulaşabilecek yeni alpha edge nereden
üretilebilir?

**Kısa cevap:** Fiyat geçmişinden türeyen her şey (yönlü TA, kesitsel sıralama, kıyas-üstü
dışlama, rejim seçimi) ölçülmüş ve kapalı. Açık kalan uzaylar, **bilgi kaynağı** değil
**eylem uzayı** ve **veri sınıfı** değişikliği gerektirenler: (1) short/vadeli bacak — 52
çekilişin 52'si long-only spot ve düşen rejim yapısal olarak kazanılamaz; (2) delta-nötr
carry (funding/basis hasadı) — türev verisi var, ama yalnız *dışlama ölçütü* olarak
denendi, *pozisyon* olarak hiç; (3) takvim/uzlaşma-zamanı mikroyapısı — 1m veri var,
tek bir çapa dışında ölçülmedi; (4) kurma katmanının devamı — genelleşen tek katman, ama
sınırı belli; (5) ikinci varlık sınıfı — veri yok, spike gerekli. Hiçbiri için "edge var"
denmiyor; her biri için önce K-045/K-068 kalıbında **çekiliş harcamayan bir tavan/kaynak
ölçümü** tanımlanıyor.

---

## 1. Kanıt tabanı (yeniden keşif yok)

| Kayıt | Ne ölçtü | Sonuç |
| --- | --- | --- |
| Defter (52) | 38 tek-sembol BTC (6 aile × 1h/4h/1d × tepe/plato + 3 funding) + 14 evren (kesitsel, türev dışlama, makro engel, konumlanma dışlama, kurma) | **0/52** geçen; en iyi 7/11 (h52), OOS Sharpe en iyi 0,363 (h51) |
| K-044 / K-064 / K-071 | çoklu test eşiği | 0,50 → 1,02 → **1,04**; 43 çekilişte gerçek yanlış-pozitif %2,6 |
| K-045 | maliyet-sıfır tavanı, tek sembol | tavan kapının yarısında (0,53 / 0,69); **maliyet duvar değil, sinyal OOS'ta çöküyor** |
| Faz 4 dönüş 1–3 | timeframe, seçim yöntemi, funding | üçü de çürütüldü; 4h maliyet/gürültüyü iyileştirir ama işlem sayısını düşürür |
| Faz 11 | K-054'ün dört kapısı, 38 çekiliş | 0/38; rejim kapısında en iyisi +0,108; `evren_dayanikliligi` tek sembolde ölçülemez |
| Faz 12 (3 program, 10 çekiliş) | kesitsel fiyat, türev dışlama, makro engel | kıyasın gürültü bandından ayrışan yok |
| K-068 | kıyas-üstü tek dışlama katmanı (8 çekiliş) | **aile kapandı**; kaynak farkı tek başına yetmez, sıralama gücü de ölçülmeli (IS'te) |
| Faz 16 kurma (2 çekiliş) | 1/σ ağırlık, turnover bandı | **kurma genelleşiyor** (`oos_is_orani` ✓, `evren_dayanikliligi` ✓), Sharpe 0,36 |
| K-072 | kıyasın kendi ızgarası | kıyas ayarlanamaz; sıfır noktası kuralla; promotion iddiası ızgaranın en iyisini (0,333) geçmeli |
| Faz 16 duyuru (K-067/3) | listeleme/delist olay etkisi | gerçek ama evren dışı küçük sembollerde ve **aşağı** yönde; sabit ufukta −%8,6; program açılmadı |
| M-1 (2026-09-19) | NY öğle saati çapası, BTC 1m | p = 0,385; Lunch ailesi kapalı |
| K-074/075/076 | Jev yönü, 50 sembol yayın sonrası | %49,0 isabet; **Jev bilgi kaynağı değil** |
| K-077 | rejim × aile oracle tavanı | hindsight'la bile 0,60 / en kötü rejim 0,52; selector/filter için headroom yok |

**Yapısal gerçek (K-077 tablosundan):** BTC 1h düşen rejimde 17 aileden **0**'ı pozitif.
Bunun nedeni ailelerin kötülüğü değil, `Sinyal.side ∈ {BUY, SELL}`, `target_exposure ∈
[0, 1]` — **v1 kaldıraçsız spot, açığa satış yok** (`strategy/sinyal.py`, Final-Doküman).
Düşen rejimde tek meşru pozisyon flat. Zamanın ≈%45–50'si yapısal olarak kazanılamaz.

---

## 2. Araştırma uzayı haritası

Kategoriler: **A** test edildi, başarısız · **B** test edildi, yeterli OOS kanıtı yok ·
**C** gerçekten test edilmedi · **D** mevcut sonuçlara göre araştırmaya değer.

| # | Alan | Kat. | İlgili kayıt | Neden açık/kapalı | Veri | Katman | Belirleyici kapı | Sızıntı / çoklu test riski | Müdahale | Öncekilerden bağımsızlık |
| --- | --- | :-: | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Tek sembol yönlü TA (BTC, 1h/4h/1d) | **A** | K-045, Faz 4 dönüş 1–5, Faz 11 | maliyet-sıfır tavan bile geçmedi | var | sinyal | `oos_is_orani`, `asgari_islem` | — | — | — |
| 2 | Funding rate yönlü filtre/eğilim (tek sembol) | **A** | K-042, Faz 4 dönüş 3 | üç hipotez, tek tur, geri dönüşsüz | var | sinyal | `oos_sharpe` | — | — | — |
| 3 | Kesitsel momentum/ters (evren) | **A** | Faz 12 `kesitsel_fiyat` | OOS −0,18…−0,97, durma kuralı işledi | var | seçim | `oos_sharpe` | — | — | — |
| 4 | Kıyas-üstü dışlama: funding, basis, VIX, NFCI, OI, taker | **A** | K-068, Faz 12/16 | 8 çekiliş, aile kapalı; yeniden açılma şartı: IS'te sıralama gücü | var | seçim | `oos_is_orani`, `evren_dayanikliligi` | — | — | — |
| 5 | Rejim seçimi / strateji seçimi / no-trade filtresi (Jev dahil) | **A** | K-077, K-076, K-074 | oracle tavanı 0,60 | var | seçim | `oos_sharpe`, `rejim_kararliligi` | — | — | — |
| 6 | Duyuru/olay (listeleme, delist) — long tarafı | **A** | Faz 16 duyuru ölçümü | etki evren dışında ve aşağı yönde | var (`data/duyuru`) | olay | `asgari_islem`, kapasite | — | — | — |
| 7 | NY seans saati (Lunch) | **A** | M-1 | p = 0,385; kural gereği başka çapa denenmez | var | takvim | — | — | — | — |
| 8 | Kesitsel düşük oynaklık | **B** | Faz 12 `kesitsel_fiyat` (2 çekiliş harcanmadı) | koşmadı; aynı iskelet (seçim katmanı, K-068) | var | seçim | `oos_is_orani` | çoklu test: +2 çekiliş | düşük | düşük — K-068 sınıfı |
| 9 | 4h/1d aileler daha uzun veriyle | **B** | Faz 4 dönüş 1 ("veriyi uzatmanın sorusu") | 11.615 bar yetmedi; arşivde BTC 1h 2017'den var | var (`data/evren/BTCUSDT`) | sinyal | `asgari_islem`, `wf_katman_basari` | aynı aileler = yeni çekiliş sayılır | düşük | düşük — aynı bilgi |
| 10 | Kurma katmanı devamı: korelasyon budaması, portföy oynaklık hedefi | **B/D** | Faz 16 kurma §4, K-068, K-072 | genelleşen tek katman; ama işaret kaynağı kıyas (0,33) — boyutlandırma 3× Sharpe üretmez | var | kurma | `oos_sharpe`, `pbo` (taban 0,277 vs 0,0087) | çoklu test: +2 çekiliş; kıyas ayarlanamaz | orta (`kur()`a korelasyon matrisi) | orta — katman aynı, mekanizma farklı |
| 11 | **Short/vadeli bacak** (düşen rejimde pozisyon) | **C** | `sinyal.py::Yon`, Final-Doküman kapsam, K-008, K-046 | hiç denenmedi — eylem uzayında yok | fiyat var; **execution yok** | eylem uzayı | tümü + yeni: funding ödemesi, likidasyon | K-045: yönlü TA'nın aynası bilgi eklemez — yalnız 12 ile birlikte anlamlı | **yüksek** (venue, risk motoru, mutabakat, kill switch) | yüksek (eylem), düşük (bilgi) |
| 12 | **Delta-nötr carry** (spot long + perp short: funding + basis hasadı) | **C/D** | K-042 (funding *filtre* olarak), Faz 12 türev (*dışlama* olarak), K-045 §4 | pozisyon olarak hiç denenmedi; fiyat yönüne bağlı değil | funding 43 sembol ✓, premium/basis ✓, OI ✓ | carry (yeni aile) | `oos_sharpe`, `max_drawdown`, kapasite, **stres** (funding tersine dönmesi) | düşük look-ahead (ödeme olayı, `available_time` net); çoklu test: 1 program | **yüksek** (11 ile aynı altyapı) | **yüksek** — kaynak *ve* mekanizma farklı |
| 13 | Funding uzlaşma zamanı / takvim mikroyapısı (00/08/16 UTC) | **C** | M-1 kalıbı, K-042 (rate'i test etti, *zamanı* değil) | ölçülmedi; 1m BTC 3,1 yıl var | var (`data/market/BTCUSDT/1m`) | takvim/olay | `asgari_islem` ✓ (günde 3 olay), **maliyet** (30,6 bps gidiş-dönüş) | 96-çapa plasebosu hazır; çekiliş değil | düşük | orta — türev mekaniği, fiyat geçmişi değil |
| 14 | Duyuru/olay — **aşağı** yönü (short ile) | **C** | Faz 16 duyuru §sonuç | etki ölçüldü ama işlem yapılamadı; 11'e bağlı | var | olay | kapasite, `asgari_islem` | seçim yanlılığı kontrolü zaten yapıldı | 11'e bağlı | orta |
| 15 | Alt-saat yönlü (5m/15m) | **C** | Faz 4 dönüş 1 mekanizması | ölçülmedi ama mekanizma ters yönde: maliyet/gürültü 1h'ten kötü | var (1m) | sinyal | maliyet | çoklu test | düşük | düşük |
| 16 | Predictive ML aynı feature'larda | **C** | K-013, K-049/3 | yalnız kapılardan sonra; aynı bilgi, farklı fonksiyon | var | sinyal | `pbo`, `oos_is_orani` | **yüksek** (esnek model = çok çekiliş) | orta | düşük |
| 17 | Haber/metin (Faz 13) | **C** | Roadmap Faz 13, K-049 | veri bütçesi + PIT arşiv spike'ı yok; LLM kesim/leak | **yok** | olay | `leak_riski` mutlak | **yüksek** (kesim, arşiv silinmesi) | yüksek | yüksek |
| 18 | On-chain / opsiyon IV / emir defteri | **C** | — | veri yok; PIT/revizyon sorunu | **yok** | — | — | yüksek (revizyon) | yüksek | yüksek |
| 19 | İkinci varlık sınıfı (US equities/ETF; transkript Grup B NQ) | **C** | K-053, Roadmap Faz 15, program-adaylari/01 Grup B | broker/lisans spike'ı; CME 1m verisi yok | **yok** | — | tümü | Grup B kuralları LLM türetimi (K-049/4) | yüksek | yüksek |
| 20 | Evren kuralı varyantları (likidite katmanı, küçük cap) | **A** | K-072 | kıyas ayarlanamaz | var | kıyas | — | — | — | — |
| 21 | Maker yürütme / maliyet düşürme | **A** | K-045 §3 | tavan maliyetsiz bile geçmedi | — | execution | — | — | — | — |

**Okuma.** A ve B satırlarının ortak paydası: hepsi aynı bilgi kaynağından (fiyat + fiyata
bağlı türevler) **long-only spot** ile edge çıkarmaya çalıştı. Kapanan şey tam olarak bu
kesişim. C satırları iki eksende açılıyor: eylem uzayı (11, 12, 14) ve veri sınıfı (17, 18,
19). Veri sınıfı eksenindekiler bugün ölçülemez (veri yok). Eylem uzayı eksenindekiler
**mevcut veriyle tavanı ölçülebilir** — ve K-045/K-077 kalıbı tam bunu istiyor: önce
tavan, sonra program.

---

## 3. Önerilen araştırma hatları (mevcut kanıtla desteklenen)

Sıra, "önce çekiliş harcamayan ölçüm" ilkesine göre. Hiçbiri bugün açılmıyor; her biri
kendi tavan/kaynak ölçümünün sonucuna bağlı.

### Hat 1 — Delta-nötr carry tavanı (funding + basis hasadı) · #12

- **Neden kapalı değil:** Funding ve basis bu projede yalnız *dışlama ölçütü* olarak
  (long-only kıyasın üstünde) denendi (K-042, Faz 12 türev). Carry'nin kendisi — spot long +
  perp short, fiyat yönünden bağımsız, funding ödemesini toplayan pozisyon — hiç
  koşturulmadı çünkü eylem uzayında short bacak yok. K-045 §4 "gerçekten farklı bir bilgi
  kaynağı" şartını koyuyor; buradaki fark kaynakta değil **getiri mekanizmasında**
  (fiyat tahmini yok). K-068'in ek şartı (IS'te sıralama gücü) kesitsel seçim için; carry
  seçim değil.
- **Mevcut kanıttan öğrenilen:** Funding'in fiyat *yönü* için bilgi değeri yok (K-042, Faz
  12: 0/7). Bu, carry'nin lehine ne de aleyhine kanıt — carry funding'in işaretini tahmin
  etmez, tahsil eder. Türev veri hattı (funding 43 sembol, premium, OI) ve PIT hizalaması
  hazır.
- **Minimum deney (Adım 0, çekiliş değil — K-045 kalıbı):** `data/funding` + `data/turev/
  premium`'dan BTC/ETH ve evren ilk 20 için **maliyetsiz carry endeksi**: her ödeme
  döneminde short-perp'in aldığı/ödediği funding + basis yakınsaması, sıfır maliyet, sıfır
  likidasyon. Yıllık Sharpe, max DD, negatif funding dönemlerinin süresi ve derinliği,
  IS penceresinde (bar 0–55.594; K-068 ek şart). **Önceden yazılan kural:** maliyetsiz
  tavan `oos_sharpe` eşiğinin (1,04) altındaysa hat kapanır, program açılmaz. Üstündeyse
  ikinci adım: gerçek maliyet (iki bacak komisyon, spread, funding ödeme yönü) ve
  likidasyon marjıyla yeniden hesap; hâlâ üstündeyse K-051 programı.
- **Gerekli veri:** var. Eksik: perp emir yürütme, marjin/likidasyon modeli, iki bacaklı
  mutabakat.
- **Başarı/başarısızlık:** Adım 0 tavan ≥ 1,04 **ve** max DD ≤ %25 → devam; değilse
  kapanır. Program aşamasında 11 kapı + `stres`: funding'in 30 gün negatif kaldığı
  senaryo.
- **Yeniden açılması gereken kayıtlar:** Final-Doküman kapsamı (v1 spot, kaldıraçsız,
  açığa satış yok — `Yon`, `target_exposure ≤ 1`); K-008 (kill switch spot semantiği; iki
  bacak kapatma sırası); K-046 (üç taraflı mutabakat → dört: spot + perp + funding
  defteri); K-057 (portföy kurma: nötr pozisyon "hedef ağırlık" değil, çift); K-033
  (risk limitleri: kaldıraç, likidasyon mesafesi, bacak dengesizliği); K-015 (vadeli
  testnet erişimi yeniden ölçülür). K-014 içinde kalır. **Bu bir mimari genişlemedir**;
  Adım 0 hiçbirini gerektirmez.

### Hat 2 — Funding uzlaşma zamanı mikroyapısı · #13

- **Neden kapalı değil:** K-042 funding *oranını* bilgi olarak test etti; ödeme *anının*
  (00/08/16 UTC) fiyat üzerindeki etkisi ölçülmedi. M-1 tek bir çapa (13:00 ET) ölçtü ve
  kural gereği başka çapa seçmeyi yasakladı — ama M-1'in 96-çapa plasebo tablosu bu üç
  saat için de bir okuma içeriyor (17:00 ET = 21:00 UTC yaz → tabloda +1,99; **bu bir
  keşif değil, sonucu görmüş bir okumadır** ve gerekçe olarak kullanılmayacak).
- **Mevcut kanıttan öğrenilen:** M-1 kalıbı çalışıyor: olay tanımı + 96 plasebo + DST
  ayrımı, çekiliş harcamadan p-değeri veriyor. Maliyet 30,6 bps gidiş-dönüş; 1h'te
  ortalama |getiri| bunun altında (Faz 4 dönüş 1) — etki en az bunun 2–3 katı olmalı.
- **Minimum deney (çekiliş değil):** Olay: funding ödeme anı; pencere ±60 dk; ölçüm: ödeme
  öncesi/sonrası ortalama log-getiri, **funding işaretine koşullu** (pozitif funding →
  ödeme öncesi long baskısı hipotezi); plasebo: aynı ölçüm 96 çapada; DST'siz (UTC
  olay). IS penceresi. **Önceden yazılan kural:** koşullu etki (|ortalama| − 30,6 bps)
  ≤ 0 ya da plasebo p > 0,05 → kapanır.
- **Gerekli veri:** BTC 1m (var), funding zamanları (var). Evren için 1m yok — BTC/ETH
  ile sınırlı; ETH 1m indirilmeli (arşiv, K-056).
- **Başarı/başarısızlık:** maliyet sonrası etki > 0 ve p ≤ 0,05 → K-051 programı (1
  çekiliş: uzlaşma-öncesi tek olay stratejisi, long-only mümkün: pozitif funding'de ödeme
  öncesi long). Program aşamasında `asgari_islem` kolay (günde 3), `oos_sharpe` zor.
- **Yeniden açılması gereken kayıtlar:** yok (long-only spot içinde kalabilir). K-045'in
  "belirgin farklı kaynak" şartı: kaynak takvim × türev mekaniği — ölçümle gerekçelenir.

### Hat 3 — Short bacak: düşen rejim eylem uzayı · #11 (+ #14)

- **Neden kapalı değil:** K-077 tablosu düşen rejimde 0/17 pozitif gösteriyor ve bu bir
  *bulgu* değil, *kısıt*: long-only. Zamanın yarısı yapısal olarak flat. K-045 yönlü TA'yı
  kapattı; short'un aynası bilgi eklemez — bu hat **tek başına program adayı değildir**.
  Değeri Hat 1'in altyapısını paylaşmasında ve #14'ü (duyuru aşağı etkisi, ölçülmüş
  −%8,6) işlenebilir kılmasında.
- **Mevcut kanıttan öğrenilen:** Duyuru etkisi aşağı yönde ve evren dışı — short + küçük
  sembol likiditesi = kapasite sorunu; Faz 16 duyuru raporu kapasiteyi ölçmedi.
- **Minimum deney (çekiliş değil):** Hat 1 altyapısı varsa: #14 için maliyetsiz tavan —
  delist/uyarı duyurusu sonrası short, sabit ufuk, IS penceresi, kapasite (ADV oranı)
  dahil. Ayrıca K-077 tablosunun **aynası**: düşen rejimde ailelerin short versiyonunun
  OOS Sharpe'ı — bu bir yeniden koşudur ve **K-039 gereği çekiliş sayılır**; yalnız Hat 1
  açılırsa ve program bütçesinden düşülerek.
- **Gerekli veri:** var. Eksik: Hat 1 ile aynı execution.
- **Başarı/başarısızlık:** #14 tavanı kapasite dahil ≥ 1,04 → programa girer; aynalar
  için ayrı bütçe yok.
- **Yeniden açılması gereken kayıtlar:** Hat 1 ile aynı + K-045 (yönlü aramanın short
  yarısı için açık istisna gerekir; gerekçe "bilgi" değil "eylem uzayı" olduğu için K-045
  §4'ün lafzı yetmez — yeni K-kaydı ister).

### Hat 4 — Kurma katmanı 2: korelasyon budaması + portföy oynaklık hedefi · #10

- **Neden kapalı değil:** K-068 "iskeleti değiştir" dedi; kurma programı iki çekilişte
  `oos_is_orani` ve `evren_dayanikliligi`'ni geçen ilk katmanı buldu; 3. ve 4. çekiliş
  bilerek harcanmadı (§4). Açık kalem.
- **Mevcut kanıttan öğrenilen — sınır:** Kurma, işaret kaynağının Sharpe'ını ölçekler,
  yaratmaz. Kıyas OOS 0,17–0,33; h51 +0,196 kattı. 1,04 için ≈3× gerekir; literatürde
  risk-parity/vol-target'ın eşit ağırlığa göre iyileştirmesi genelde 1,2–1,6×. **Bu hat
  tek başına kapıya ulaşmaz**; değeri Hat 1/2 bir işaret kaynağı bulursa onu kapıya
  taşıyacak çarpan olmasında. `pbo` tabanı 0,277 (eşik 0,0087) — kurma bunu düşürmedi.
- **Minimum deney:** açılmaz; Hat 1 ya da 2'den pozitif işaret kaynağı gelene kadar
  bekler. Gelirse: o kaynağın üstüne 1/σ + korelasyon budaması, 2 çekiliş, kurma
  programının kalan bütçesi.
- **Gerekli veri:** var. Eksik: `kur()`a korelasyon matrisi girişi (küçük kod).
- **Başarı/başarısızlık:** işaret kaynağı S₀ ise kurma sonrası ≥ 1,04 ve `pbo` ≤ 0,0087.
- **Yeniden açılan kayıt:** yok (K-068 yönü içinde).

### Hat 5 — İkinci varlık sınıfı spike'ı (Faz 15) · #19

- **Neden kapalı değil:** K-053 "ölçülmeden açılmaz" diyor, "açılmaz" değil. Kripto
  long-only evreni tükenmiş görünüyor; başka bir varlık sınıfının aynı ailelerle nasıl
  davranacağı bilinmiyor. Transkript Grup B'nin 95 adayı CME NQ/ES 1m istiyor.
- **Mevcut kanıttan öğrenilen:** Hayatta kalma yanlılığı kriptoda ayda %17 (K-056) —
  hisse evreninde PIT üyelik verisi olmadan aynı tuzak. Aileler kriptoda geçemedi; hissede
  geçeceğine dair kanıt **yok**; bu hat "umut" değil "ölçülmemiş" kategorisi.
- **Minimum deney (spike, çekiliş değil):** broker/veri/lisans: PIT üyelikli günlük
  hisse/ETF verisi kaynağı ve maliyeti; CME 1m arşivi var mı, lisansı ne; Türkiye
  yerleşiği için broker erişimi. Çıktı: "veri bütçesi kararı" (Final-Doküman "Bütçeler").
  Veri gelirse ilk ölçüm K-045 kalıbı: mevcut 6 aile, maliyet-sıfır tavan, tek varlık.
- **Gerekli veri:** yok — spike'ın konusu.
- **Başarı/başarısızlık:** spike "PIT veri ≤ bütçe, lisans uygun" demezse kapanır.
- **Yeniden açılan kayıtlar:** K-053 (ölçüm şartı), Roadmap Faz 15 açılma koşulu;
  Final-Doküman bütçe kalemi.

---

## 4. Önerilmeyenler ve neden

- **#8 kesitsel düşük oynaklık, #9 uzun veri, #15 alt-saat, #16 ML:** aynı bilgi kaynağı,
  aynı long-only uzay; K-045/K-068 kapattı; her biri defteri büyütür (eşik yükselir) ve
  önceki ölçümler beklentiyi negatife koyuyor.
- **#17 haber, #18 on-chain/IV/emir defteri:** veri yok; ileriye biriktirmek yıllar
  (Spike 5 dersi); LLM türetimi `leak_riski`.
- **Jev'in herhangi bir rolü:** K-076/K-077. Gölge açık kalır; bu denetim Jev'e iş vermiyor.

## 5. Sıralama gerekçesi

Hat 1 önce: tek başına mevcut veriyle, çekiliş harcamadan, bir hafta içinde "tavan var mı"
sorusuna sayısal cevap verir ve cevap pozitifse mimari genişlemeyi (short/perp) gerekçeler;
negatifse Hat 3 de onunla kapanır. Hat 2 paralel ve ucuz (M-1 betiği kalıbı). Hat 4 bekler.
Hat 5 bir veri/bütçe kararıdır, araştırma değil.

**Bu raporun açtığı şey:** hiçbir program, hiçbir çekiliş. Sonraki adım Scryne kararı:
Hat 1 Adım 0 ve/veya Hat 2 ölçümü için onay (ikisi de `tools/` betiği + rapor; kod
tabanına, motora, kapılara dokunmaz).
