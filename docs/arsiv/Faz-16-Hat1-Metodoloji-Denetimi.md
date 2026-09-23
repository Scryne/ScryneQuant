---
proje: ScryneQuant
faz: 16
tur: metodoloji denetimi (kısa) — perp fee ve MMR gerçekten zorunlu mu?
tarih: 2026-09-20
type: denetim
durum: bulgular; karar Scryne'ın
---
# Hat 1 — Metodoloji denetimi: perp fee ve MMR eksikliği neyi kilitliyor?

Kapsam: yalnız mevcut dokümanlar (`Ikinci-Tavan-Tasarimi` §3/§5/§8/§9/§10, `A-Olcumu`,
`B-Veri-Spike`, `Veri-Karari`, `C-Veri-Dogrulama`), mevcut K hükümleri (K-007, K-021,
K-045, K-049/4, K-054, K-058, K-066) ve mevcut ölçüm tanımları. Veri, anahtar, kod,
config, hesap, varsayımsal değer: **yok.**

Üç şey birbirinden ayrı tutulur: **(H)** hesaplanabilirlik · **(E)** ekonomik anlam ·
**(K)** resmi ikinci tavan / stres kapısına girebilme. Bir satırın (H)'si "evet" olması
(K)'sını "evet" yapmaz.

---

## 1. Perp fee

**İkinci tavanda nereye giriyor.** Tasarım §3: `c_perp_tek_yon = fee_perp + slip_perp`;
açılış+kapanış toplamı `2·(fee_spot + slip_spot) + 2·(fee_perp + slip_perp)`, `H` gün
tutmada yıllık amortisman `× 365/H`; dengeleme terimi A-6'da ihmal edilebilir ölçüldü
(δ=%1 aşımı IS'in %0,02'si). Yani fee, `r_gross`'a **tek bir toplamsal sabit** olarak girer
ve `r_gross` üzerinden 3. aşamayı (`r_excess`) ve 4. aşamayı (stres çarpanları `fee_2x`,
`hepsi_2x` — `STRES_SENARYOLARI`) besler.

**Zorunlu mu?**
- (H) Tam `r_gross`: **evet, zorunlu.** Formülün bir terimi boş; boş terimle "gerçekçi
  maliyet-düzeltilmiş" sayı tanım gereği üretilemez.
- (H) Ara ölçüm: **mümkün.** Fee ≥ 0 olduğundan `r_gross(fee=0)` gerçek `r_gross`un **üst
  sınırıdır** — K-045'in tavan mantığı: "maliyetsiz bile geçmiyorsa hiçbir ücret geçiremez".
  İkinci, daha güçlü ara ölçüm: **başabaş perp fee** — `H` ızgarasında `r_excess` Sharpe'ını
  tam 1,04'e indiren `fee_perp` değeri (bps). Bu bir varsayım değil, bilinmeyeni bir eşiğe
  çeviren türetimdir: "gerçek ücret bu bps'in altındaysa 2./3. aşama kapının üstünde kalır".
- (E) Ara ölçümün ekonomik anlamı sınırlı: üst sınır "en iyi hâl"dir; başabaş fee ise
  ancak gerçek ücretle karşılaştırılınca anlam kazanır — o karşılaştırma yapılamıyor.
- (K) **Giremez.** İki bağımsız kural: (i) `research/kapilar.py::MUTLAK_ENGELLER` içinde
  `gecici_maliyet_modeli` — kalibre edilmemiş/eksik maliyet parametresiyle üretilen sonuç
  promotion'a giremez (K-007: "geçici değerle üretilen hiçbir sonuç promotion'a giremez");
  fee alanı yokken model **geçicidir**. (ii) Tavan/üst sınır zaten kapı kanıtı değildir
  (K-045/1, K-077/2).

**Adı ne olmalı.** `r_gross_ust_sinir_fee0` (perp-fee'siz maliyet tavanı) ve
`basabas_fee_perp_bps` (H başına). İkisi de raporda "ARA — kapı dışı, `gecici_maliyet_modeli`"
etiketiyle; `oos_sharpe`, `stres_dayanikliligi` ve promotion zincirine **girmez**.

**Spot fee/slippage'ı perp'e taşımak neden yeni varsayım.**
1. Farklı piyasa ve tarife: Spike 4 yalnız **spot VIP 0** ölçtü (`fee_taker_bps` 10,0); USDT-M
   ayrı tarife, repoda ölçümü yok. Bir ölçümü başka bir piyasaya kopyalamak ölçüm değil
   varsayımdır — K-020'nin hatası tam buydu ve K-021 onu "veriden kalibre edilir, tahmin
   edilmez" ile değiştirdi.
2. Ölçülmüş fark: aynı pencerede (2023-08 → 2025-02) perp BTC slippage p75 **5,83** vs spot
   **5,67** bps; IS tamamında perp **7,11 / 9,11** (BTC/ETH). Eşit değil; yönü "perp daha
   pahalı". Spot değerini taşımak ölçülmüş farkı silerdi ve K-007'nin "belirsizlikte
   aleyhte yuvarla" kuralını çiğnerdi.
3. `config/maliyet.json` şeması her parametreye kaynak/kalibrasyon bloğu istiyor; kaynağı
   "spot'tan kopya" olan bir perp alanı şemanın amacına aykırı.
Varsayımsal ücret tablosu (destek makalesindeki "assumed" örnek) hesapta **kullanılmaz**.

**A. Tam ikinci tavanı açmak için gerçekten gerekli minimum bilgi (fee):**
tek bir tarihli kayıt — işlem yapılacak hesap kademesinde (VIP 0) USDT-M **taker** ücreti
(bps), doğrulanabilir kaynaktan (imzalı `commissionRate` yanıtı ya da hash'lenmiş resmî
sayfa), `config/maliyet.json`'a `fee_taker_bps_perp` + kalibrasyon bloğu (tarih, kaynak,
hash). Gerekmeyenler: maker ücreti (K-007 taker kuralı), BNB indirimi (varsayılmaz),
tarihsel tarife serisi (yok; "IS boyunca sabit" açık sınırlama olarak yazılır), emir
defteri (Spike 4 spread'i ihmal etti; perp'te ölçülmediyse sınırlama satırı).

---

## 2. MMR (bakım marjin oranı)

**Metodolojide nereye giriyor.** Tasarım §5: likidasyon = perp bacağının marjin oranının
`mmr + tampon` altına inmesi; short perp için yaklaşık `p_liq ≈ p₀·(1 + 1/L − mmr)`
(borsa formülü kaydedilmedi; bu tasarımdaki mertebe ifadesi). Çıktı bir **olay sayacı**,
PnL kalemi değil; 4. aşamanın yalnız **bir** senaryo sınıfını ("likidasyon eşiğine
yaklaşma") besler. Diğer altı stres sınıfı (funding negatif, basis aleyhte, yüksek vol,
execution ×, borsa parametresi, erişim kaybı) MMR istemez.

**Zorunlu mu?**
- (H) Tam sayaç: **evet, zorunlu.** Eşik MMR'nin kendisi; `L` ızgarası eşiğin yalnız
  öbür terimi.
- (H) Ara ölçüm: **mümkün, üç biçimde**, hiçbiri MMR değeri varsaymaz:
  1. **Alt sınır sayacı:** MMR ≥ 0 tanım gereği ⇒ likidasyon rallisi ≤ `1/L`. Mark yolunda
     tutma penceresi içinde `1/L`'i aşan ralli sayısı, gerçek likidasyon sayısının **alt
     sınırıdır** (gerçek eşik daha yakın). `L` ızgarası, sembol, yıl; seçim yok.
  2. **Marjin payı yolu:** `L` verildiğinde marjin oranı = `(m + funding birikimi − ralli)`
     yolu — A-1 (funding→marjin) + mark ralli; MMR olmadan "eşik" yok ama **dağılım** var:
     her `L` için IS'te marjin oranının p1/p5/min'i.
  3. **Gerekli tolerans (başabaş MMR):** her `L` için, IS'te hiç likidasyon olmaması için
     MMR'nin en fazla ne olabileceği (= `1/L − azami ralli`). Bilinmeyeni eşiğe çevirir;
     gerçek MMR ile karşılaştırma yapılamıyor.
- (E) 1 ve 3 anlamlı sınırlar; 2 betimleyici. Üçü de "likidasyon riski küçüktür" cümlesi
  kuramaz; yalnız "en az şu kadar" ve "şu toleransı ister" der.
- (K) **Giremez.** `stres_bozulma` (≤ 0,15) tanımlı bir senaryoda gerçekleşen bozulmayı
  ölçer; alt sınır/tolerans bir senaryo değil, sınırdır. Ayrıca kapıya girecek satır PIT
  olmak zorunda (K-058: `leak_riski` mutlak engel).

**Mark tek başına neyi destekler.** Mark−spot farkı (ölçüldü: medyan −0,02 %, uç 2,2–2,4 %);
A-5 MFE'nin mark sürümü; yukarıdaki üç ara ölçüm; basis M2M'in mark'la yeniden hesabı.
Desteklemediği: sayaç, marjin çağrısı sayısı, likidasyon ücreti/ADL etkisi.

**Bugünkü MMR'yi geçmişe uygulamak neden NON_PIT / leak_risk.** Kademe tabloları borsa
tarafından değiştirilir ve **değişiklikler geçmiş oynaklık olaylarına tepkidir**; 2020–2025
yoluna bugünkü tabloyu uygulamak (i) o gün elde olmayan bilgiyi kullanır (K-049/4: geriye
dönük türetim, kesim sonrası bilgi), (ii) tabloyu o dönemin kendisi şekillendirdiği için
seçim yanlılığı taşır. K-058 `leak_riski`yi mutlak engel yaptı; bu satır o bayrağı taşır.

**PIT ile NON_PIT arasındaki kapı farkı.**

| | PIT MMR (kayıt tarihinden ileriye) | NON_PIT MMR (bugünkü tablo → IS) |
| --- | --- | --- |
| Sayaç hesaplanır mı (H) | evet | evet |
| Ekonomik anlam (E) | evet, örneklem takvim hızında | duyarlılık; "o dönemde olurdu" iddiası **yok** |
| `stres_bozulma` senaryosu olabilir mi (K) | evet (program açılırsa, K-054 çerçevesi) | **hayır** — `leak_riski` mutlak engel |
| Raporda etiket | `PIT` | `NON_PIT · leak_risk · kapı dışı` |
| Bugünkü içerik | EMPTY | EMPTY |

**İzole vs portföy marjininde MMR'nin rolü.**
- `C-isolated`: MMR **doğrudan eşik**; tek bilinmeyen. Alt sınır/tolerans ara ölçümleri
  tamamen tanımlı (mark + `L` + A-1).
- `C-portfolio`: MMR gerekli ama **yetersiz**; eşik toplam öz kaynağa (spot teminat ×
  (1 − haircut)) bakar. Haircut ve uygunluk olmadan: haircut ∈ [0, 1] aralığının iki ucu
  sınır verir — haircut 1 ⇒ `C-isolated` (üst sınır: portföy likidasyonu izole olandan fazla
  olamaz), haircut 0 ⇒ spot tamamen sayılır (alt sınır: rally yalnız basis M2M kadar
  eritir, likidasyon pratikte basis olayı). Aradaki tek sayı **haircut olmadan ölçülemez**;
  uygunluk ikili (hesap uygun değilse senaryo boş). Yani `C-portfolio` için bugün
  üretilebilen tek şey "C-isolated'dan az, basis-tetiklemeli senaryodan çok" bandı.

**B. Stres/likidasyon kapısını açmak için gerçekten gerekli minimum bilgi seti (MMR):**
1. `C-isolated` için: BTC/ETH USDT-M kademe tablosu (notional kademesi → MMR ve bakım
   tutarı) **kayıt tarihiyle**, likidasyon ücreti oranı, borsa likidasyon formülünün
   metni (kaynak + tarih) — üçü tek spike kaydı; artı **PIT kuralı**: sayaç yalnız kayıt
   tarihinden ileriye kapıya girer, IS satırı `NON_PIT`. Otomatik marjin ekleme kuralı
   *yalnız* "marjin çağrısı" sayacı istenirse gerekir; likidasyon sayacı için gereksiz
   (tampon `b` ızgarası zaten var).
2. `C-portfolio` için ek: teminat haircut oranları ve hesap uygunluk şartı (kural metni,
   tarih). Bunlar olmadan portföy senaryosu **band** olarak kalır, sayı olmaz.
3. Gerekmeyen: 1m mark (1h'de görünmeyen likidasyon bir model sınırıdır, açık yazılır;
   sayaç için zorunlu değil), tarihsel MMR arşivi (yok; PIT kuralı bunun yerine geçer),
   ADL (kapı kapsamı dışı).

---

## 3. Sonuç matrisi

| Girdi | Statü | Kilitlediği aşama | Girdi olmadan üretilebilen çıktı | Resmi kapıya girebilir mi? |
| --- | --- | --- | --- | --- |
| Perp taker fee (VIP 0, tarihli) | **ZORUNLU GİRDİ** | 2 (tam `r_gross`), 3 (`r_excess`), 4 (`fee_2x`/`hepsi_2x`) | `r_gross_ust_sinir_fee0`, `basabas_fee_perp_bps` (H ızgarası) | **hayır** — `gecici_maliyet_modeli` mutlak engel; tavan |
| Perp slippage (K-021) | **ARA ÖLÇÜMÜ MÜMKÜN KILAR** — ölçüldü | — | üst sınır ve başabaş fee ancak bununla hesaplanır | ölçüldü; kapıya fee ile birlikte girer |
| Perp maker fee | **ÖLÇÜM İÇİN GEREKSİZ** | — | — | — (K-007 taker kuralı) |
| Tarihsel tarife serisi | **ÖLÇÜM İÇİN GEREKSİZ** (yok; sınırlama satırı) | — | "IS boyunca sabit" beyanı | — |
| Perp emir defteri / spread | **TERCİH / İYİLEŞTİRME** | — | sınırlama satırı (Spike 4 spot'ta ihmal etti) | — |
| MMR kademe tablosu (tarihli) | **ZORUNLU GİRDİ** (`C-isolated` sayacı) | 4 (yalnız "likidasyon eşiğine yaklaşma" sınıfı) | alt sınır sayacı (MMR=0 sınırı), marjin payı dağılımı, başabaş MMR | **hayır** girdi olmadan; girdiyle yalnız **PIT** satır |
| Bakım tutarı + likidasyon ücreti | **ZORUNLU GİRDİ** (sayacın tam tanımı) | 4 (aynı sınıf) | MMR'siz alt sınır zaten bunları içermez; küçük ama gerekli | MMR ile birlikte |
| Otomatik marjin ekleme kuralı | **TERCİH / İYİLEŞTİRME** | — (yalnız "marjin çağrısı" sayacı) | likidasyon sayacı `b` ızgarasıyla tanımlı | — |
| Mark price 1h | **ARA ÖLÇÜMÜ MÜMKÜN KILAR** — indirildi | — | mark−spot, mark-MFE, alt sınır sayacı | PIT; sayaç MMR bekler |
| Mark 1m | **ÖLÇÜM İÇİN GEREKSİZ** (model sınırı olarak yazılır) | — | — | — |
| Mark boşluk günleri (günlük arşiv) | **TERCİH / İYİLEŞTİRME** | — | boşluk günü "ölçülemez" | — |
| Portföy haircut oranları | **ZORUNLU GİRDİ** (`C-portfolio` sayısı) | 4 (`C-portfolio` satırı) | band: [basis-tetiklemeli, `C-isolated`] | hayır |
| Hesap uygunluk şartı | **ZORUNLU GİRDİ** (`C-portfolio` varlığı) | 4 (`C-portfolio` satırı) | uygun değilse senaryo boş | — |
| USDT benchmark (DTB3) | **ZORUNLU GİRDİ** — sağlandı | 3 | — | girdi PIT; `r_excess` fee'yi bekler |
| Tarihsel MMR arşivi | **ÖLÇÜM İÇİN GEREKSİZ** (yok; PIT kuralı yerine geçer) | — | NON_PIT satırı asla kapıya girmez | hayır |

**Okuma.** Fee tek bir sayıdır ve üç aşamayı birden kilitler; MMR bir tablodur ve 4.
aşamanın yalnız bir senaryo sınıfını kilitler — diğer altı stres sınıfı bugün
hesaplanabilir. Bu asimetri bir öneri değil, tanımların sonucu.

## 4. Değişiklik yok

Veri, anahtar, K-066, yeni K, config, `src/`, stres/likidasyon hesabı, varsayımsal değer:
hiçbiri. Kararlar Scryne'ın.
