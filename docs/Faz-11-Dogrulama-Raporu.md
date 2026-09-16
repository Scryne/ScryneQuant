---
proje: ScryneQuant
faz: 11
tarih: 2026-09-16
type: rapor
karar: K-058
---
# Faz 11 — Doğrulama v2

Bu faz **strateji aramadı.** K-054'ün dört yeni kapısını kurdu, eşiklerini geçecek adayı
görmeden ölçtü, defterdeki 38 çekilişi bu kapılardan geçirdi, ve araştırma programı kaydını
zorunlu kıldı. Kararlar `docs/Kararlar.md` K-058'de; ham ölçümler `runs/kalibrasyon-v2/` ve
`runs/deneyler/kapilar_v2/`.

## 0. Bitti kriteri tablosu

| Kriter | Sonuç |
| --- | --- |
| Dört kapı hesaplanıyor, her eşik gerekçesiyle sabit | ✅ `pbo` 0,0087 · `parametre_perturbasyonu` 0,0565 · `rejim_kararliligi` 0,685 (üçü edge'siz null'dan, iki ızgarada) · `evren_dayanikliligi` 0,75 (yapısal ölçüm, iştah olarak işaretli) |
| Eşikler bugünkü sonuca göre ayarlanmadı; gevşetmeyi yakalayan test var | ✅ `test_kapilar_v2.py::TestGevsetme` — eşik ölçümün gerisine düşerse, yönü çevrilirse veya null medyanı geçerse kırılıyor |
| Defterdeki 38 çekiliş yeni kapılardan geçirilmiş, raporlanmış | ✅ **0/38** geçti (§4) |
| `leak_riski` taşıyan sonuç kapıdan geçemiyor (testle) | ✅ Bütün sayısal kapılar geçse bile duruyor (`test_program.py::TestLeakRiski`) |
| Program kaydı olmadan araştırma programı koşturulamıyor (testle) | ✅ Defter ve CLI yolunda; bütçe dolunca da duruyor (`test_program.py`, `test_cli.py::TestProgramKaydi`) |

**Test:** 1.441 geçti, 1 atlandı (faz başında 1.351).

## 1. Ne kuruldu

| Modül | İşi |
| --- | --- |
| `research/pbo.py` | CSCV (16 dilim, 12.870 kombinasyon), dilim toplamlarından tam Sharpe |
| `research/perturbasyon.py` | Seçilen noktanın tek-eksen komşularına göre düşüşü |
| `research/rejim.py` | Nedensel, parametresiz rejim bölümlemesi (30 günlük kıyas getirisinin işareti) |
| `research/evren_dayaniklilik.py` | En iyi katkıyı evrenden düşürüp **yeniden koşma** |
| `research/kalibrasyon_v2.py` | Üç istatistiğin paylaşılan-kaydırma null dağılımı |
| `research/kapilar_v2.py` | Dört kapının ölçümü + eşikler + `butun_kapilar` (11 kapı) |
| `research/program.py` | Program defteri, arama bütçesi, `LlmTuretimi` ve `leak_riski` |
| `research/dsr.py` | Deflated Sharpe (raporlanır, kapı değil) |
| CLI | `sq lab program-kaydet / program-kapat / butce / kapilar-v2`; `hipotez-kaydet --program` |
| Araçlar | `tools/kalibrasyon_v2_kos.py`, `tools/evren_dayaniklilik_kalibre.py` |

## 2. Eşiklerin ölçümü

### 2.1 Null kalibrasyonu (`pbo`, `parametre_perturbasyonu`, `rejim_kararliligi`)

K-044'ün yöntemi: ızgaranın her noktasının sinyal takvimi bir kez çıkarıldı, sonra her
iterasyonda **hepsi aynı oranda** dairesel kaydırılıp gerçek motordan geçirildi. Korunan:
sinyal sayısı, aralık deseni, noktalar arası korelasyon. Yok edilen: fiyatla hizalanma.
Her kapı kendi penceresinde (PBO tam, pertürbasyon IS, rejim OOS).

| Kapı | Izgara | Nokta | İterasyon | Null medyanı | %5 sınırı | %90 GA | Süre |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |
| `pbo` (≤) | donchian | 12 | 200 | 0,237 | **0,0087** | 0,006-0,017 | 43 dk |
| `pbo` (≤) | rsi_donus | 32 | 100 | 0,199 | 0,0462 | 0,022-0,060 | 52 dk |
| `perturbasyon` (≤) | donchian | 12 | 200 | 0,246 | 0,0752 | 0,062-0,097 | 18 dk |
| `perturbasyon` (≤) | rsi_donus | 32 | 100 | 0,167 | **0,0565** | 0,048-0,078 | 24 dk |
| `rejim` (≥) | donchian | 12 | 200 | −0,741 | 0,481 | 0,078-0,738 | 8 dk |
| `rejim` (≥) | rsi_donus | 23 | 100 | −0,204 | **0,685** | 0,538-1,176 | 6 dk |

**Kural: iki ızgaradan sıkı olanı** (≤ kapısında düşük, ≥ kapısında yüksek). Eşik ızgara
şekline bağlı çıktı ve bir aday ızgarasını seçerek gevşek eşiğe kaçamamalı (K-007).

Rejim kapısının güven aralıkları geniş: null'ın üst kuyruğu ince. Kayıtlı; çaresi
iterasyonu artırmak, eşiği yuvarlamak değil.

### 2.2 PBO'nun literatür referansı burada eşik olamaz

İlk varsayım "null PBO = 0,5" idi. İki ayrı ölçüm:

- **İid gürültü (12 aday × 4.000 bar, 40 tohum):** ortalama **0,503** — referans ortalamada
  doğru. Ama standart sapma **0,204**, aralık 0,084-0,898: tek bir veri kümesinde ölçülen
  PBO ±0,2 belirsizlik taşıyor.
- **Gerçek ızgara (donchian, kaydırma null'ı):** medyan **0,237**, %90'ı 0,548'in altında.
  Komşu parametreler neredeyse aynı strateji; IS-en iyisi edge olmadan da OOS'ta iyi kalıyor.

Yani 0,5 eşiği edge'siz ızgaraların %90'ından fazlasını geçirirdi. K-044'ün dersinin bu
istatistikteki hâli: referans sayı ölçülmüş eşiğin yerini tutmaz.

### 2.3 `evren_dayanikliligi` — yapısal kalibrasyon

Null bu kapıyı kalibre edemez: edge'i yok eder, oysa kapı yoğunlaşmayı ölçüyor. Evren
kıyası (K-030) farklı yoğunluklarda koşuldu; en iyi katkı evrenden düşürülüp yeniden koşuldu.

**İlk tasarım çürüdü.** Kapı önce mutlak Sharpe düşüşünü okuyordu. 2025-01…2026-08'de
(kıyas Sharpe ≈ −0,5) düşüş 3 enstrümanda 0,035, 20'de 0,000 çıktı — sayı Sharpe'ın
büyüklüğüyle ölçekleniyor; Sharpe 1,5'lik bir strateji aynı yoğunlukta çok daha büyük bir
mutlak düşüş üretirdi. Kapı **orana** geçti ve pozitif Sharpe'lı pencerede yeniden ölçüldü:

| Varyant | Azami enstrüman | Katkı veren | Tam Sharpe | Azaltılmış | **Oran** |
| --- | ---: | ---: | ---: | ---: | ---: |
| eşit | 2 | 0 | +0,743 | — | ölçülemedi |
| eşit | 3 | 4 | +0,674 | +0,584 | 0,867 |
| eşit | 5 | 13 | +0,719 | +0,601 | 0,835 |
| eşit | 10 | 30 | +0,300 | +0,292 | 0,974 |
| eşit | 20 | 58 | +0,204 | +0,208 | 1,021 |
| oynaklık | 3 | 4 | +0,668 | +0,586 | 0,878 |
| oynaklık | 5 | 13 | +0,729 | +0,607 | **0,832** |
| oynaklık | 10 | 30 | +0,309 | +0,301 | 0,976 |
| oynaklık | 20 | 58 | +0,202 | +0,207 | 1,023 |

(2023-01…2026-08, 323 sembol, k=1.) Oran çeşitlendirmeyle monoton yükseliyor; bant
**0,832-1,023**. Eşik **0,75** — bandın altında, "performansın dörtte birinden fazlası tek
bir isme bağlı" çizgisi. Bant içinden bir iştah seçimi ve öyle işaretli.

**Kayda değer sınır:** en yoğun kurulum (N=2) **ölçülemedi** — iki isim her dengelemede
seçili kaldığı için hiç tur kapanmadı ve katkı hesaplanamadı. Kapının en çok ilgilendiği
durum, ölçünün en zor olduğu durum.

## 3. Program kaydı ve `leak_riski`

- `docs/Arastirma-Programlari.jsonl` append-only. Program açılışı gerekçe (≥60 karakter),
  **ölçüyle** kaynak farkı (boş `kaynak_olcumu` reddediliyor), azami çekiliş, durma kuralı
  ve eşik tahmini ister. Aynı adla ikinci açılış reddediliyor (bütçeyi sessizce ikiye
  katlamanın en kolay yolu).
- `sq lab hipotez-kaydet` yeni bir hipotezi program olmadan, kapalı bir programa veya
  bütçesi dolmuş bir programa yazmıyor. Zaten kayıtlı bir hipotez yeni çekiliş değil, bütçe
  düşmüyor.
- Hipotez kimliği `evren`/`portfoy`/`rejim` ile genişledi — yalnızca dolu olduklarında.
  Defterdeki 38 satırın kimliği **değişmedi** (test edildi); aksi hâlde `dogrula()` hiçbirini
  tanımazdı.
- `LlmTuretimi.leak_riski` kapsam başlangıcı eğitim kesiminden önceyse `True`. Dondurulmamış
  (prompt/girdi hash'i olmayan) türetim reddediliyor. `Sonuc.leak_riski` hash'e girmiyor ama
  `promotion_engelleri`ne giriyor; bütün sayısal kapılar geçse bile sonuç duruyor.

## 4. Defterdeki 38 çekiliş, yeni kapılarda

`sq lab kapilar-v2` (kayıt `runs/deneyler/kapilar_v2/301e3750d764-530ecf2a72f1.json`).
**Geçen: 0/38.**

| Kapı | Geçen | Kalan | Ölçülemedi |
| --- | ---: | ---: | ---: |
| `pbo` | 2 | 29 | 7 |
| `parametre_perturbasyonu` | 1 | 29 | 8 |
| `rejim_kararliligi` | 0 | 36 | 2 |
| `evren_dayanikliligi` | 0 | 0 | **38** |

- **`evren_dayanikliligi` 38/38 ölçülemez** ve bu K-054'ün kendi cümlesi: tek sembolde
  geliştirilen hiçbir çekiliş bu kapıyı geçemez. Diğer üç kapı geçilse bile sonuç değişmezdi.
- **Ölçülemeyenler:** tek noktalı ızgaralar (`al_tut`, PBO ve pertürbasyon tanımsız) ve 1d'de
  geçerli aday üretmeyen çekilişler (`sma_kesisim`, `ema_kesisim` 1d).
- **En yakın aday `cok_faktor` 1h/plato:** PBO 0,000 ✓, pertürbasyon 0,044 ✓, en kötü rejim
  Sharpe'ı −1,23 ✗, evren ölçülemez ✗. Faz 4'te de en yakın aday oydu (OOS Sharpe 0,46,
  eşik 1,02). Yeni kapılar eski tabloyu **çevirmedi, teyit etti**.
- **Rejim kapısında hiçbir çekiliş pozitif bölgeye yaklaşmadı:** en iyisi `sma_kesisim` 4h
  (+0,108, eşik 0,685). Stratejilerin çoğu OOS'ta rejimlerden birinde belirgin negatif —
  Faz 4'ün "OOS'ta çöküş" bulgusunun rejim kırılımı.

## 5. Bu fazda düzeltilen üç hata

Hepsi ölçüm sırasında çıktı, hiçbiri sessiz kalmadı:

1. **Rejim penceresi bar cinsindendi.** 720 bar 1h'te 30 gün, 4h'te 120 gün, 1d'de iki yıl
   ediyordu; ilk 38-çekiliş koşusunda 1d'nin OOS penceresi tamamen ısınmada kaldı ve rejim
   **hiç ölçülemedi.** Pencere zamana bağlandı (30 gün → 720/180/30 bar). Eşik 1h'te
   kalibre edildi; zaman sabit tutulduğu için diğer timeframe'lere aynı anlamda uygulanıyor.
2. **Kalibrasyon aracı sonucu yalnızca sonda yazıyordu.** Rejim adımındaki bir dilimleme
   hatası (etiket dizisi ısınmayı kesmiyordu — `rejim.olc` uzunluk uyuşmazlığıyla **durdu**,
   sessizce hizalamadı) iki saatlik PBO/pertürbasyon ölçümünün ham örneğini sildi. Araç
   artık her ölçümden sonra yazıyor; koşu yeniden yapıldı ve sayılar **birebir aynı** çıktı
   (sabit tohum).
3. **`kapilar_v2` deney tipi tanınmıyordu.** 38 çekilişin tamamı hesaplandıktan sonra kayıt
   adımı düştü. Tip eklendi, komut her çekilişten sonra ara kayıt yazıyor, ve uçtan uca bir
   CLI testi eklendi.

## 6. Raporlanan ama kapı olmayanlar

- **DSR** (`research/dsr.py`) — K-044'ün çapraz kontrolü; ham basıklıkla (fazlalık basıklık
  sonucu iyimser yapardı), 30 gözlem altında ve paydası negatifken reddediyor.
- **VaR/CVaR, kapasite** — Faz 10.
- **Olasılık kalibrasyonu — uygulanamaz.** Yalnızca olasılık üreten tahmin modellerinde
  anlamlı; bu projede böyle bir model yok (Faz 13, koşullu). Uygulanamaz diye yazılı,
  sıfır diye değil.

## 7. Açık kalemler

1. Rejim null'ının güven aralığı geniş (rsi_donus 0,54-1,18): iterasyon artırılmalı.
2. `evren_dayanikliligi` eşiği bir iştah; ilk gerçek cross-sectional adayla (Faz 12)
   yeniden ölçülür.
3. Yeni bir ızgara biçimi üç null eşiğinin yeniden ölçümünü ister (K-058 geri dönüş 1).
4. `oos_sharpe` eşiği (K-044) 31 çekilişte ölçülmüştü, defter 38; Faz 12'nin bitti kriteri
   onu zaten yeniden ölçtürüyor.
