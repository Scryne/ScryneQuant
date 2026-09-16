---
proje: ScryneQuant
faz: 12
tarih: 2026-09-16
type: plan
durum: taslak — program defterine henüz yazılmadı
---
# Faz 12 — Program taslakları ve kaynak ölçüleri

Bu doküman **program kaydı değil.** `docs/Arastirma-Programlari.jsonl` append-only; oraya
yazılan bütçe geri alınamaz ve her çekiliş global defterin eşiğini yükseltir (K-044,
K-051/1). Bütçe bir **iştah** kararı (K-033 kalıbı) — onay Scryne'da. Aşağıdakiler onaya
sunulan taslaklar ve onları taşıyan ölçüler.

Hiçbir çekiliş yapılmadı. Defter **38**, ölçülebilir **31**, `oos_sharpe` eşiği **1,02**.

## 1. Kaynak ölçüleri (K-051/2, K-045 istisnası)

Araç: `tools/faz12_kaynak_olcumu.py` → `runs/faz12/kaynak-olcumu.json`. **İleriye dönük
hiçbir getiriye bakılmadı** — bütün istatistikler eşzamanlı veya geriye dönük; hiçbir kural
sınanmadı (Spike 5'in kalıbı). Bu ölçüler kaynağın **farklı** olduğunu gösterir, **değerli**
olduğunu değil.

### 1.1 Kesitsel fiyat (PIT evren, üst 50, 99 ay, 429 sembol)

| Ölçü | p25 | Medyan | p75 |
| --- | ---: | ---: | ---: |
| Üye günlük getirisinin BTC ile **açıklanamayan** varyans payı (1−R², sembol-ay, n=4.254) | 0,378 | **0,552** | 0,748 |
| Kesitin ilk temel bileşen payı (ay, n=98) | 0,533 | **0,638** | 0,712 |
| Günlük kesit sapması (gün, n=2.998) | %2,73 | **%3,57** | %4,75 |
| BTC günlük getiri sapması (zaman serisi) | | %3,53 | |

Okuma: tipik bir üyenin günlük hareketinin **yarısından fazlası** K-045'in kapattığı
kaynakta (BTC serisi) görünmüyor. Ortak faktör güçlü (%64) — kesitsel bir sıralamanın
çalışabileceği alan kalan ~%36 — ama günlük kesit dağılımı BTC'nin kendi günlük
oynaklığı kadar geniş.

### 1.2 Evren geneli funding

Veri: `tools/faz12_funding_indir.py`, arşiv `futures/um/monthly/fundingRate`, her zip
`.CHECKSUM` ile doğrulandı → `data/turev/funding/` (26 MB, REST deposundan ayrı, K-056/1).
Evrene girmiş 429 sembolün **380**'inin perp'i var; üye-ay kapsamı **%93,5**. 49 sembol
eşleşmedi (çoğu `1000PEPE` tipi çarpanlı sözleşme veya perp'i olmayan spot) — eşleme
uydurulmadı.

| Ölçü | p25 | Medyan | p75 |
| --- | ---: | ---: | ---: |
| Üye günlük funding'inin BTC funding'iyle **açıklanamayan** payı (1−R², n=3.338) | 0,617 | **0,853** | 0,965 |
| Günlük funding kesit sapması (n=2.417) | %0,037 | **%0,060** | %0,114 |
| BTC günlük funding sapması (zaman serisi) | | %0,058 | |
| Funding sırası ↔ geriye dönük 7 günlük getiri sırası (Spearman, gün) | −0,131 | **+0,012** | +0,158 |

Okuma: üyelerin funding'i K-042'nin kapattığı BTC funding'inden büyük ölçüde bağımsız ve
kesitteki funding farkı BTC'nin kendi funding oynaklığı kadar. Funding sırası fiyat
momentum sırasıyla medyanda ilişkisiz — yani türev kanalı §1.1'in kesitsel fiyat kanalının
yeniden adlandırılmış hâli değil.

**Sınır:** funding uzun dönemler taban değerde (%0,01/8 s) sabit kalıyor; neredeyse sabit
bir serinin R²'si doğal olarak düşük çıkar ve 1−R² bağımsızlığı bir miktar **abartır**.
Kesit sapması ve sıra korelasyonu bu etkiden bağımsız ölçüler.

### 1.3 Basis ve makro

- **Basis:** arşivde `premiumIndexKlines` 1h, 2020-01'den beri (ETHUSDT'de 80 ay
  doğrulandı). Henüz indirilmedi; türev programının ikinci kanalı.
- **Makro:** ALFRED vintage'ları FRED API anahtarı ister (Roadmap Faz 12 notu). Anahtar
  gelmeden makro programının kaynak ölçüsü yapılamaz ve program açılamaz.

## 2. Duvar: bütçe → tahmini `oos_sharpe` eşiği (K-051/3)

`σ = 0,4416` (31 çekilişin OOS Sharpe sapması). DSR = Bailey & López de Prado beklenen
maksimum; "ölçek" sütunu DSR'ı N=31'de ölçülen permütasyon/DSR oranıyla (1,017/0,922 =
1,103) çarpar. **Tahmin, kapı değil** — kapı program bitiminde `sq lab coklu-test` ile
ölçülür.

| Ek çekiliş | Ölçülebilir N | DSR | DSR × ölçek | Bonferroni |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 31 | 0,922 | 1,017 | 1,301 |
| 5 | 36 | 0,948 | 1,047 | 1,321 |
| 10 | 41 | 0,971 | 1,072 | 1,338 |
| 15 | 46 | 0,991 | 1,094 | 1,354 |
| 20 | 51 | 1,009 | 1,113 | 1,367 |
| 30 | 61 | 1,038 | 1,146 | 1,391 |
| 60 | 91 | 1,103 | 1,217 | 1,441 |

**İki uyarı:**
1. Duvar logaritmik büyüyor; asıl maliyet N değil **σ**. Kesitsel/türev çekilişlerinin OOS
   Sharpe dağılımı tek sembollü 31'inkinden geniş çıkarsa duvar tablodan hızlı yükselir.
2. Faz 4'ün en iyisi 0,46'ydı. Duvarın 1,02'den 1,10'a çıkması, hiçbir şey bulunamamış bir
   dünyada pratik farkı değiştirmiyor; bir şey bulunmuş bir dünyada değiştiriyor.

## 3. Program taslakları

Ortak kısıtlar (değişmez): spot, **long-only**, kaldıraç yok (K-057); evren PIT
(K-052/3); kıyas `evren_esit_agirlik` (K-030) ve kıyas bir çekiliş değil; her çekiliş 11
kapının tamamına karşı (K-058) ve `evren_dayanikliligi` ilk gerçek adayla yeniden ölçülür
(K-058 geri dönüş 2).

**Long-only'nin sonucu önden yazılmalı:** spot'ta kesitsel sıralama bir long-short faktör
değil, "evrenin hangi dilimini tut" seçimidir ve piyasa betasını taşır. OOS Sharpe mutlak
ölçülüyor; 2025-01…2026-08 penceresinde kıyasın kendisi −0,49. Faktörün göreli edge'i
beta tarafından örtülebilir ve bu, kapıların **bilinçli** hâli.

### 3.1 `kesitsel_fiyat` — önerilen bütçe **6**

- **Gerekçe:** K-045 tek sembollü yönlü aramayı kapattı; kesit, BTC serisinin göremediği
  varyansın medyan %55'ini taşıyor (§1.1).
- **Aileler (her biri bir çekiliş = bir ızgara):** (1) orta vadeli göreli güç (trailing
  getiri sırası); (2) kısa vadeli ters dönüş; (3) düşük oynaklık dilimi. Her aile iki
  yeniden dengeleme sıklığında (haftalık, aylık) → 6.
- **"Değer" ailesi alınmadı:** kriptoda PIT temel veri yok; fiyattan türetilen bir "değer"
  proxy'si göreli gücün yeniden adlandırılmış hâli olur ve bedava çekiliş sayılırdı.
- **Durma kuralı:** Bütçe biter veya ilk iki ailenin dört çekilişinin hiçbiri OOS'ta
  kıyasın Sharpe'ını geçmezse program kapanır; kalan çekilişler harcanmaz, aile/parametre
  genişletilmez.

### 3.2 `turev_evren` — önerilen bütçe **4**

- **Gerekçe:** K-042 funding'i tek sembolde kapattı; `funding_filtre` mekanizması (aşırı
  pozitif funding = kaldıraçla finanse edilmiş kırılganlık) evren kesitinde tekrar ediyor mu.
  Kaynak ölçüsü §1.2.
- **Çekilişler:** (1) funding kesit filtresi — kıyas evreninden en yüksek funding dilimini
  dışla; (2) birikimli funding sırası; (3) basis (premium index) kesit filtresi;
  (4) funding + basis birleşik.
- **Durma kuralı:** Bütçe biter veya (1) ile (2) OOS'ta filtresiz kıyası geçmezse (3)-(4)
  harcanmaz.

### 3.3 `makro_rejim` — önerilen bütçe **3**, **anahtar gelene kadar açılmaz**

- Kaynak: ALFRED vintage (FRED anahtarı), ECB. Kullanım **yalnızca engelleyici** (K-037,
  K-052): "risk-iştahı düşük rejimde yeni giriş yok".
- Rejim motoru (Roadmap 12d) bu programın altyapısı: filtrelenmiş olasılık, katman başına
  eğitim, yumuşatılmış olasılığın kullanılmadığını kanıtlayan test. Rejim **tanımı** bir
  çekiliştir (K-051/4) ve bu bütçeden düşer.

### 3.4 Program adayı 01 (transkript desenleri) — **Faz 12'ye alınmaması önerilir**

İleriye dönük değerlendirme penceresi 2026-09-15'te başladı; `asgari_islem ≥ 30` birçok
kural için aylar-yıllar ister. Bugün açılırsa bütçesi Faz 12'nin duvarına **şimdiden**
eklenir ama sonucu Faz 12 içinde ölçülemez. Faz 16'ya bırakılır; dondurulmuş hâli değişmez.

## 4. Toplam

Önerilen: 6 + 4 + 3 = **13** çekiliş → ölçülebilir N ≈ 44 → tahmini eşik ≈ **1,08**
(DSR × ölçek), Bonferroni 1,35.

## 5. Onay bekleyenler (Scryne)

1. Bütçeler (6 / 4 / 3) — veya başka bir dağılım.
2. FRED API anahtarı (makro programının ön koşulu).
3. Program adayı 01'in Faz 16'ya bırakılması.

## 6. Ön kayıt dışında görülen bir OOS sonucu (2026-09-16) — kayıt

Hat süresini ölçmek için koşturulan duman testinde **kayıtsız bir koşu yapıldı ve sonucu
görüldü:** `kesitsel_guc(pencere=720, azami_enstruman=10, yeniden_dengele_bar=168)`, tam
evren (429 sembol, 79.420 bar), `pencereler()`in OOS'u (bar 55.594-79.420):
**Sharpe −0,407, 534 işlem**, 9,1 s. K-039'a göre bu bir bakıştır ve saklanmaz.

Sonuç: `kesitsel_fiyat`'ın haftalık göreli güç çekilişinin ızgarası bu nokta **görülmüş**
olarak kurulur; kaydının gerekçesine bu bölüm yazılır. Süre ölçümü için bundan sonra
yalnızca kıyas (`evren_esit_agirlik`) veya sentetik veri kullanılır.
