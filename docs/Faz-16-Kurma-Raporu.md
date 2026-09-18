---
proje: ScryneQuant
faz: 16
program: kurma_evren
tarih: 2026-09-18
type: rapor
durum: kapandı — 2/4, kalan bütçe harcanmadı
---
# Faz 16 — `kurma_evren` programı raporu

**Sonuç:** Program 4 çekilişlik bütçenin 2'siyle kapandı. Hiçbir çekiliş 11 kapıyı geçmedi,
ama **ikisi de projede bugüne kadar hiçbir çekilişin geçemediği iki kapıyı geçti** ve
birincisi kıyasın OOS Sharpe'ını iki katından fazla aştı. Kalan iki çekiliş §4'teki
gerekçeyle harcanmadı.

Program kaydı `docs/Arastirma-Programlari.jsonl` (kimlik `ccaa63c6fe6dbdf3`), hipotezler
51-52 `docs/Hipotez-Defteri.jsonl`, taslak `docs/Faz-16-Kurma-Program-Taslagi.md`. Ham
sonuçlar `runs/faz12/kurma_oynaklik.json`, `runs/faz12/kurma_turnover.json`.

## 1. Kurulum

| | |
| --- | --- |
| İskelet | `evren_esit_agirlik` kıyası; **seçim, sıralama ve dengeleme takvimi aynen** — değişen tek şey `KurmaAyarlari` |
| Evren | PIT tablo `27b7a16ed0ed`, 429 sembol, 79.420 bar |
| Bölme | IS bar 0-55.594, OOS 55.594-79.420; WF 29 katman |
| Kıyas | Her çekilişte **seçilen yoğunlukla** koşuldu (türev programı kalıbı): fark yalnızca kurmadan gelsin |
| Değerleme | K-059 (48 bar) |
| Kapılar | `research/kapilar_v2.butun_kapilar` (11 kapı); `oos_sharpe` sınırı 1,04 (K-071, 43 çekilişle doğrulandı) |
| Kod | `348b1892` ve `11e5f09b`, **temiz ağaç** (konumlanma koşularının aksine) |

## 2. Sonuçlar

| Hipotez | Çekiliş | Seçilen | IS Sharpe | OOS Sharpe | Kıyas OOS | OOS getiri | OOS MaxDD | OOS işlem | WF Sharpe | Geçen kapı |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 51 | `kurma_oynaklik` | çarpan 10,0 · n=10 | 0,646 | **0,363** | 0,167 | +%10,1 | **%13,8** | 116 | 0,771 | **6/11** |
| 52 | `kurma_turnover` | bant 0,02 · n=5 | 0,428 | 0,280 | **0,333** | +%7,8 | %20,6 | 47 | 0,884 | **7/11** |
| — | kıyas n=10 | — | — | 0,167 | — | +%3,8 | %20,0 | 108 | — | — |
| — | kıyas n=5 | — | — | 0,333 | — | +%10,3 | %20,9 | 47 | — | — |

### 2.1 Kapılar

| Kapı | Sınır | 51 oynaklık | 52 turnover |
| --- | --- | ---: | ---: |
| `oos_sharpe` | ≥ 1,04 | 0,363 ✗ | 0,280 ✗ |
| `oos_is_orani` | ≥ 0,5 | **0,562 ✓** | **0,654 ✓** |
| `wf_katman_basari` | ≥ 0,6 | 0,586 ✗ | **0,621 ✓** |
| `parametre_kararliligi` | ≤ 0,35 | 0,103 ✓ | 0,121 ✓ |
| `asgari_islem` | ≥ 30 | 116 ✓ | 47 ✓ |
| `max_drawdown` | ≤ 0,25 | 0,138 ✓ | 0,206 ✓ |
| `stres_dayanikliligi` | ≤ 0,15 | 0,086 ✓ | 0,040 ✓ |
| `pbo` | ≤ 0,0087 | 0,277 ✗ | 0,201 ✗ |
| `parametre_perturbasyonu` | ≤ 0,0565 | 0,375 ✗ | 0,331 ✗ |
| `rejim_kararliligi` | ≥ 0,685 | 0,220 ✗ | 0,210 ✗ |
| `evren_dayanikliligi` | ≥ 0,75 | **0,820 ✓** | **1,109 ✓** |

## 3. Okuma

### 3.1 Asıl bulgu: kurma katmanı genelleşiyor, seçim katmanı genelleşmiyor

Bu, iki çekilişin ortak imzası ve programın gerçek çıktısı:

| Kapı | Ne ölçüyor | Seçim çekilişleri (8 adet) | Kurma çekilişleri (2 adet) |
| --- | --- | --- | --- |
| `oos_is_orani` | IS başarısının ne kadarı dışarıda kaldı | **hiçbiri geçmedi** (0,18-0,38) | **ikisi de geçti** (0,56 · 0,65) |
| `evren_dayanikliligi` | Evren tanımı değişince sonuç ayakta mı | **hiçbiri geçmedi** (−0,20 ile 0,59) | **ikisi de geçti** (0,82 · 1,11) |
| `rejim_kararliligi` | En kötü rejimde ne oluyor | hepsinde **negatif** | ikisinde de **pozitif** (0,22 · 0,21) |

Faz 12 ve 16'nın sekiz seçim çekilişinde bu üç ölçü istisnasız kötüydü: in-sample başarı
dışarıda kayboluyor, evren tanımı değişince işaret dönüyor, kötü rejimde sonuç negatif.
Kurma çekilişlerinde üçü de tersine döndü. Sebep mekanizmadan okunabiliyor: **kurma bir
tahmin yapmıyor.** `1/σ` ağırlıklandırma hangi sembolün yükseleceğini iddia etmez, aynı
seçimi farklı risk katkılarıyla taşır — dolayısıyla genelleşmesi için bir tahmin gücünün
var olması gerekmiyor.

`evren_dayanikliligi`nin 52'de **1,109** çıkması bunun en net hâli: alternatif evren
tanımlarında sonuç bozulmuyor, **iyileşiyor**.

### 3.2 Ama Sharpe kapısı geçilmiyor ve ona yaklaşılmıyor da

51'in OOS Sharpe'ı 0,363, kapı 1,04. Bu bir kıl payı değil, üç kat. `pbo` 0,277 (sınır
0,0087) ve `parametre_perturbasyonu` 0,375 (sınır 0,0565) ise mertebe farkıyla uzak.
Genelleşmek başka şey, **çoklu test düzeltmesinden sonra ayakta kalmak** başka şey.

### 3.3 Oynaklık ağırlıklandırma riski düşürüyor, getiriyi de artırıyor

51, kıyasla aynı isimleri, aynı takvimde, neredeyse aynı işlem sayısıyla (116 vs 108)
taşıyor. Fark yalnızca ağırlıklarda:

| | kıyas n=10 | 51 oynaklık |
| --- | ---: | ---: |
| OOS getiri | +%3,8 | **+%10,1** |
| OOS max drawdown | %20,0 | **%13,8** |
| OOS Sharpe | 0,167 | **0,363** |

Drawdown **düşerken** getirinin artması, bunun bir kaldıraç etkisi olmadığını söylüyor —
`hedef_brut` iki koşuda da 0,2. Seçilen nokta `çarpan = 10`, yani **fiilen tavansız saf
1/σ**: ızgaranın en az parametreli noktası. Kazananın ızgaranın kenarındaki en yalın ayar
olması, "ayarlanmış" bir sonuç olmadığının lehine bir işaret.

**Aleyhine olan işaret de yazılı:** `plato_orani` 0,167 ve perturbasyon düşüşü %37,5 —
komşu ızgara noktası performansın üçte birinden fazlasını kaybediyor. Bunun bir kısmı
yapısal: çarpan 10'un komşusu 2,0 ve ikisi arasında tavan bağlamaya başlıyor, yani komşu
gerçekten farklı bir rejim. Bu gerekçeyle `parametre_perturbasyonu` eşiğini gevşetmek,
sonucu gördükten sonra kapıya dokunmak olurdu; dokunulmadı.

### 3.4 Turnover bandı çalışmadı ve önsel beklenti tutturdu

52, kıyasın altında kaldı (0,280 vs 0,333). Hipotez kaydında sonucu görmeden yazılan karşı
argüman aynen gerçekleşti: kıyasın OOS'taki toplam maliyeti 104,76 USDT (%1,05), yani
bandın kazanabileceği üst sınır zaten küçüktü.

Ölçülen şey daha da net: seçilen bant (0,02, eşit payın yarısı) **işlem sayısını hiç
düşürmedi** — kıyasla aynı 47 işlem. Bant, dengeleme *sayısını* azaltmadı; sürüklenmiş
ağırlıkları sıfırlamayıp taşıdığı için maruziyeti değiştirdi ve sonuç kötüleşti. Yani bant
maliyet tasarrufu üretmeden pozisyon profilini bozdu.

**Null sınırı, kayıtlı:** bandın hiçbir tahmini olmadığı için çoklu test null'ında
kaydırılacak doğal bir sinyal yok; sıralama ölçütü (`kote_hacim`) kaydırıldı ve null'da
bant da çalıştığı için null dağılımı sıfır çevresinde değil, kaydırılmış kıyasın Sharpe'ı
çevresinde toplanıyor. **Bu çekiliş için ölçülen düzeltme muhafazakâr değildir.** Sonucu
değiştirmiyor (zaten kıyasın altında) ama kayda geçiyor.

### 3.5 Kıyasın kendi yoğunluğu ölçülmemiş bir kaldıraçmış

Yan bulgu, çekiliş harcanmadan çıktı: kıyas n=5'te OOS Sharpe **0,333**, n=10'da **0,167**.
İki kat fark, ve bu sayı bugüne kadarki bütün karşılaştırmaların sıfır noktasıydı. Faz
12-16'nın sekiz seçim çekilişi n=10'luk kıyasa karşı ölçüldü; n=5'lik kıyas onların
çoğunu **zaten geçiyor**.

Bu bir çekiliş sonucu değil, bir gözlem — ve üzerine bir şey kurmak yeni bir program kaydı
ister (§4/2).

## 4. Kalan iki çekiliş neden harcanmadı

Durma kuralı **tetiklenmedi**: kural ilk iki çekilişin kıyası geçmemesine bağlıydı ve 51
geçti. Bütçe de doluydu (2/4). Yine de 3 ve 4 harcanmıyor, `makro_rejim` programının
kalıbıyla (K-051: **bütçe tavandır, zorunluluk değil; harcamamak yanlış pozitif
üretemez**):

1. **Korelasyon budaması (3):** programın en parametreli çekilişi ve `kur()`a bir korelasyon
   matrisi beslemeyi gerektiriyor — henüz var olmayan bir makine. Üstelik taban `pbo`'da
   0,277 ile 0,0087'nin 30 katı uzakta; kıyasın üstüne konan bir budama katmanının bunu
   mertebe değiştirecek kadar taşıması beklenmiyor ve bu beklenti K-068'in sekiz çekilişte
   ölçtüğü desenle aynı.
2. **Konsantrasyon (4):** sorduğu soruyu veri **zaten cevapladı**. Yoğunluk ekseni
   ({5, 10, 20}) iki çekilişin de ızgarasının içindeydi ve kıyas iki farklı yoğunlukta
   koşuldu (§3.5). Ayrı bir çekiliş harcamak, cevabı alınmış bir soruyu ikinci kez sorup
   defteri büyütmek — yani bütün gelecek çekilişlerin çıtasını bedelsiz yükseltmek olurdu.

**Durma kuralının lafzı belirsizdi ve buna yaslanılmadı.** Kural "ilk iki çekiliş kıyası
geçmezse" diyor; "ikisi de geçmezse" mi "biri geçmezse" mi olduğunu ayırmıyor (türev
programı "ikisi de" yazmıştı). Program, kuralın okunuşundan **bağımsız** gerekçelerle
kapatılıyor. Sonraki program kayıtlarında durma kuralı bu belirsizliği taşımamalı.

## 5. Beklenmeyen bulgular

1. **`agirliklar()`de tavan bir tavan değildi (K-070).** Tavana kırpılan pozisyon
   kilitlenmiyor, sonraki turda yeniden pay alıp tavanı aşıyordu; 3 adaylı bir vakada
   tavanın iki katına çıktığı ölçüldü. Hata, `esit_agirlik=False` kod yolu **ilk kez
   gerçekten çalıştırıldığında** çıktı — o yol Faz 10'dan beri kodda duruyor, docstring'i
   var ve hiç koşmamıştı. Hiçbir kayıtlı sonuç değişmedi (gerekçe K-070'te).
2. **Çoklu test eşiği ölçülürken araç defterin yarısını sessizce düşürdü (K-071).**
   `--birlestir` eşiği 0,51 olarak raporladı; kapıya yazılsaydı çıta yarıya inerdi. Sebep
   K-064'ün eklediği `sizinti_bar` alanının iki birleştirme yolunu birbirinin tümleyeni
   yapması. 43 çekilişin tamamı yeniden koşuldu; ölçülen %5 sınırı 0,926, yürürlükteki
   1,04'ün gerçek yanlış-pozitifi %2,6. Sabit **indirilmedi**.
3. **Sentetik test fixture'ı oynaklık dağılımı üretmiyordu.** `bar_uret` bütün tohumlarda
   aynı mutlak oynaklığı veriyor; dört tavan çarpanı da aynı `sonuc_hash`i üretti, yani
   eksen ölü görünüyordu. Gerçek evrende eksen canlı (n=20, çarpan=10'da ağırlıklar
   0,0050-0,0073 bandına yayılıyor). Fixture'ın getirileri sembol başına ölçeklendi.
4. **Kapalı konumun kıyasa dönme testi iki çekilişte iki farklı biçimde tutuyor.**
   `turnover_bandi = 0` bit düzeyinde aynı (kod yolu aynı); `azami_agirlik_carpani = 1`
   ağırlık eşitliği düzeyinde aynı (kod yolu farklı: önce paylar, sonra kırpma, sonra
   artanın dağıtımı — son bitler tutmuyor). İlk taslak ikisi için de bit eşitliği iddia
   ediyordu; iddia ölçülene göre düzeltildi.

## 6. Bu program ne bıraktı

- **Kurma katmanı, seçim katmanının geçemediği genelleşme kapılarını geçiyor.** Bu, K-068
  sonrası "iskeleti değiştir" yönergesinin ilk olumlu sinyali — ama Sharpe kapısına üç kat
  uzak.
- **Kıyasın yoğunluğu ölçülmemiş bir kaldıraçtı** ve n=5, n=10'un iki katı Sharpe veriyor.
  Bütün geçmiş karşılaştırmaların sıfır noktası bu yüzden tartışmaya açık.
- Defter 50 → **52**. Sonraki programın açılışında `oos_sharpe` eşiği yeniden ölçülmeli
  (K-044): `tools/faz12_coklu_test.py --deneme 500 --seed 0`.
