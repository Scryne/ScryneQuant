---
proje: ScryneQuant
faz: 16
tur: kıyas ölçümü (çekiliş değil)
tarih: 2026-09-18
type: rapor
durum: kapandı — K-072
---
# Faz 16 — Kıyasın kendi parametre uzayı

**Sonuç: kıyas ayarlanamaz.** In-sample'da en iyi olan kıyas parametresi, out-of-sample'da
15 adayın **10.'su** ve Sharpe'ı **negatif** (−0,357). Yani "kıyası en iyi hâline getirip
sıfır noktası yapalım" fikri, projenin 52 çekilişte belgelediği aşırı uydurmanın ta
kendisini üretir. Ayrıca **parametresiz kıyas bugünkü sözleşmede kurulamıyor.**

Ölçüm `tools/faz16_kiyas_olcumu.py`, çıktı `runs/faz16/kiyas-olcumu.json`. **Bu bir çekiliş
değildir:** kıyas bir iddia taşımıyor, sıfır noktasını tanımlıyor (K-030); seçilen bir
parametre yok, ızgaranın tamamı raporlanıyor.

## 1. Neden ölçüldü

`evren_esit_agirlik` kıyası `azami_enstruman = 10`, `yeniden_dengele_bar = 168` ile
koşuyordu. Bu iki sayı **ölçülerek değil varsayılan olarak** seçilmişti ve Faz 12-16'nın on
çekilişinin tamamı bu sıfır noktasına karşı değerlendirildi. `kurma_evren` programı yan
ürün olarak n=5'in OOS Sharpe'ının 0,333, n=10'unkinin 0,167 olduğunu gösterdi — iki kat
fark, ve hiçbiri ölçülmemişti.

## 2. Ölçüm

Aynı evren (`27b7a16ed0ed`, 429 sembol, 79.420 bar), aynı maliyet, `hedef_brut` sabit 0,2.
Kıyasın tavanı tanımı gereği eşit pay (`hedef_brut / n`).

**OOS Sharpe:**

| n \ periyot | 168 (haftalık) | 336 | 720 (aylık) |
| ---: | ---: | ---: | ---: |
| **5** | **+0,3334** | +0,2425 | +0,3068 |
| 10 | +0,1669 | +0,1341 | +0,2809 |
| 20 | −0,2701 | −0,3407 | −0,3029 |
| 30 | −0,4528 | −0,5592 | −0,4129 |
| 39 | −0,5070 | −0,4554 | −0,3565 |

**IS Sharpe:**

| n \ periyot | 168 | 336 | 720 |
| ---: | ---: | ---: | ---: |
| 5 | +0,3496 | +0,3679 | +0,2605 |
| 10 | +0,3389 | +0,3264 | +0,2538 |
| 20 | +0,2483 | +0,2250 | +0,3530 |
| 30 | +0,3130 | +0,2878 | +0,3700 |
| **39** | +0,3484 | +0,3227 | **+0,4923** |

## 3. Kararı veren tek satır

| | |
| --- | --- |
| IS'te en iyi | n=39, periyot 720 · Sharpe **+0,492** |
| Aynı parametrenin OOS'taki sırası | **10 / 15** |
| Aynı parametrenin OOS Sharpe'ı | **−0,357** |
| OOS'ta en iyi | n=5, periyot 168 · Sharpe +0,333 |
| Aynı parametre mi | **hayır** |

In-sample'ın en iyi kıyası, out-of-sample'da para kaybediyor. Kıyası IS'te seçmek,
stratejileri IS'te seçmekle **aynı hatadır** — ve kıyas sıfır noktası olduğu için hatanın
maliyeti daha büyük: yanlış yerde duran bir sıfır noktası, üstündeki bütün ölçümleri
kaydırır.

**IS tablosu düz, OOS tablosu keskin.** IS'te bütün ızgara 0,22-0,49 bandında ve yoğunlukla
ilgili bir yapı yok; OOS'ta n≤10 pozitif, n≥20 kuvvetle negatif. Yani OOS'taki yoğunluk
tercihi bir *özellik* değil, o pencerenin **rejimi** — ve bir rejimi sıfır noktasına
yazmak, onu kalıcı sanmaktır.

## 4. Parametresiz kıyas da kurulamıyor

İlk koşu bir kısıtla düştü ve kısıt gerçek: evren kuralının `ust_n`'i **50**, `hedef_brut`
**0,2**, yani "herkesi eşit taşı" dendiğinde pozisyon başına pay **0,004**. Kurma
katmanının asgari ağırlık tabanı **0,005** ("ekonomik olarak anlamsızı sıfır say",
`VARSAYILAN_ASGARI_AGIRLIK`). Parametresiz kıyas bugünkü sözleşmede **var olamıyor**.

İfade edilebilir azami yoğunluk **39** ve o da OOS'ta −0,36 ile −0,51 arasında. Tabanı
indirmek ya da brütü büyütmek ayrı birer karardır; ikisi de bu raporun kapsamı dışında ve
ikisi de sonuca bakılarak verilemez.

## 5. Sonucun `kurma_evren` programına etkisi

h51'in (`1/σ` ağırlıklandırma) OOS Sharpe'ı **0,363**. Yan yana:

| | OOS Sharpe |
| --- | ---: |
| h51 (1/σ ağırlık, n=10) | 0,363 |
| Kıyas, **hiçbir ayar yok**, n=5/168 | 0,333 |
| Kıyas, kayıtlı sıfır noktası, n=10/168 | 0,167 |

h51 kendi kayıtlı kıyasını iki katından fazla geçiyor — bu doğru ve apples-to-apples
(aynı yoğunluk, aynı takvim, fark yalnızca ağırlıkta: +0,196). **Ama bilinen en iyi basit
kıyasa üstünlüğü %9.** Ve kıyasın kendisi, tek bir keyfî parametreyle +0,333 ile −0,507
arasında geziniyor: h51'in 0,363'ü o bandın içinde.

Bu, h51'in bulgusunu geçersiz kılmıyor — aynı yoğunlukta ağırlıklandırmanın kattığı +0,196
duruyor ve `oos_is_orani`/`evren_dayanikliligi` kapılarını geçmesi hâlâ projede bir ilk.
Ama **"kıyası iki kat geçti" cümlesi, seçilen kıyas yüzünden olduğundan büyük görünüyordu.**

## 6. Karar

K-072: kıyas ayarlanmaz, kuralla sabitlenir; ve promotion iddiası için ikinci ve daha sıkı
bir çizgi tanımlanır (ayrıntı `docs/Kararlar.md`).

## 7. Açık bırakılanlar

- **Yoğunluğun OOS'taki keskin yapısı açıklanmadı.** n=5 ile n=39 arasında OOS'ta 0,84
  Sharpe fark var. Bu bir rejim etkisi mi (o pencerede birkaç büyük isim taşıdı) yoksa
  kalıcı bir kesit özelliği mi — ölçülmedi. Ölçmek bir çekiliştir ve **OOS'a bakılarak
  seçilmiş bir soru** olduğu için, sorulacaksa yeni bir veri penceresinde sorulmalı.
- **Asgari ağırlık tabanı (0,005) ve `hedef_brut` (0,2) ölçülmemiş varsayılanlar.** Bu
  raporun bulduğu kısıt ikisinin kesişiminden doğuyor. İkisi de kıyasın değil risk
  iştahının parçası; gözden geçirilmeleri gerekiyorsa `config/risk.json`'ın K-033 kalıbıyla.
