---
proje: ScryneQuant
created: 2026-09-11
type: deney-raporu
faz: 4
tur: 2
status: kapandi
---
# Faz 4'e dönüş 2 — Parametre seçim yöntemi

> **Sonuç: hipotez çürütüldü.** Plato merkezi seçimi `oos_is_orani`'nı iyileştirmedi;
> değişen altı vakanın **beşinde kötüleştirdi**. Önceden yazılmış başarısızlık koşulu
> gereği üçüncü bir seçim yöntemi denenmiyor.

## Hipotez (sonuç görülmeden yazıldı)

Faz 4 ve dönüş 1'de ölçülen desen tek istisnasızdı: **`oos_is_orani` her stratejide, her
timeframe'de düştü.** O kapı overfitting dedektörü; hepsinin aynı kapıda düşmesi sorunun
aile seçiminde değil **parametre seçiminde** olabileceğini söylüyordu.

**Mekanizma:** `en_iyi` saf argmax. Bir platonun tepesi, tanımı gereği, o platonun gürültü
en çok lehe çalışan noktasıdır — yani seçilen nokta sistematik olarak iyimserdir ve o
iyimserlik out-of-sample'da geri alınır. Bölgenin merkezi böyle bir yanlılık taşımaz:
komşularının hepsi de iyi olduğu için seçim tek bir şanslı örneğe dayanmaz.

**Beklenti:** `oos_is_orani`'nın yükselmesi. IS Sharpe'ın **düşmesi** de bekleniyordu —
tepeyi bırakıyoruz — ve bu beklenen bir bedel, başarısızlık değil.

**Önceden belirlenen başarısızlık koşulu:** K-019'un yedi kapısı değişmez. `oos_is_orani`
yükselmezse hipotez çürür ve **üçüncü bir seçim yöntemi denenmez** — denenirse ayrıca
sayılır.

**Ön kayıt:** hipotezler 22-35 (`docs/Hipotez-Defteri.jsonl`), koşudan önce.

## Uygulama

`TaramaSonucu.plato_merkezi()`: plato kümesindeki (en iyinin %10 yakınındaki geçerli
adaylar) her parametrenin **ızgaradaki sırası** alınır, sıraların medyanı hesaplanır, o
medyana en yakın aday seçilir. Ham değer değil sıra kullanılıyor — `pencere` 7-21 ile `ust`
60-80 aynı ölçekte değil ve ham mesafe büyük sayılı parametreyi baskın yapardı. Eşitlikte
skoru yüksek olan kazanır.

**Seçim yöntemi hipotez kimliğinin parçası oldu (K-039).** Kimliğin dışında bırakmak,
"argmax dene, olmadı platoyu dene, olmadı şunu dene" zincirini **bedava çekiliş** yapardı.
Defter 21 kaydı bu alanla göç ettirildi; çekilişlerin kendisi değişmedi, yalnızca kimliğin
kodlanışı.

## Ölçüm: `oos_is_orani`, tepe → plato

Eşik ≥ 0,50. **Yalnızca değişen vakalar anlamlı** — plato kümesi tek adaydan oluştuğunda
plato merkezi tepenin kendisidir.

### 1h

| strateji | tepe | plato | |
| --- | ---: | ---: | --- |
| sma_kesisim | −1,67 | −1,67 | aynı nokta |
| ema_kesisim | −0,70 | **−1,20** | ✗ kötüleşti |
| rsi_donus | −1,89 | −1,89 | aynı nokta |
| donchian | −0,46 | −0,46 | aynı nokta |
| momentum | −0,09 | **−0,45** | ✗ kötüleşti |
| cok_faktor | −4,15 | **−58,56** | ✗ (aşağıda: ölçüm artefaktı) |
| al_tut | −0,39 | −0,39 | tek noktalı ızgara |

### 4h

| strateji | tepe | plato | |
| --- | ---: | ---: | --- |
| sma_kesisim | 0,35 | 0,35 | aynı nokta |
| ema_kesisim | 0,32 | 0,32 | aynı nokta |
| rsi_donus | −0,72 | **−0,97** | ✗ kötüleşti |
| donchian | −0,31 | −0,31 | aynı nokta |
| momentum | −0,21 | **−1,02** | ✗ kötüleşti |
| cok_faktor | 0,15 | **0,42** | ✓ **iyileşti** |
| al_tut | −0,46 | −0,46 | tek noktalı ızgara |

**Altı değişimden beşi kötüleşti, biri iyileşti.** Hipotez çürüdü.

**`cok_faktor` 1h'teki −58,56 bir ölçüm artefaktı**, gerçek bir 14 kat kötüleşme değil:
oran `oos_sharpe / is_sharpe` ve IS Sharpe sıfıra çok yakın pozitif bir sayıya düştüğünde
oran patlıyor. İşaret doğru (kötüleşti), büyüklük anlamsız. Bunu "14 kat kötüleşti" diye
okumak yanlış olurdu.

## Kapı sonucu

**Hiçbir strateji, hiçbir timeframe'de, hiçbir seçim yöntemiyle geçmiyor.** Eşikler
değişmedi.

En yakına gelen: **`cok_faktor`, 4h, plato** — OOS Sharpe **0,46** (eşik 0,50).
Şimdiye kadarki en yüksek değer. Ama:

- `oos_is_orani` 0,42 (eşik 0,50) ✗
- `asgari_islem` ✗
- `stres_dayanikliligi` %15,7 (eşik %15) ✗

Ve en önemlisi: **bu 35 çekilişten biri.** "Neredeyse geçti" diye okumak, K-039'un tam
olarak engellemek için var olduğu hatadır. Tek bir yakın değer, 35 denemenin içinde
beklenen bir şeydir.

## Deneyin kendi sınırı

Plato kümeleri **küçüktü**: 12-36 adaylık ızgaralarda 1-7 aday. Ölçülen dağılım:

```
strateji      tf   geçerli aday   plato kümesi   tepe ≠ plato?
sma_kesisim   1h             15              4   hayır
ema_kesisim   1h             15              4   evet
rsi_donus     1h             32              3   hayır
donchian      1h             12              1   hayır
momentum      1h             36              7   evet
cok_faktor    1h             36              5   evet
sma_kesisim   4h             15              1   hayır
ema_kesisim   4h             15              2   hayır
rsi_donus     4h             23              3   evet
donchian      4h             12              2   hayır
momentum      4h             36              5   evet
cok_faktor    4h             36              4   evet
```

14 vakanın 6'sında seçim farklı bir nokta verdi; 8'inde plato merkezi tepenin kendisiydi.

**Dolayısıyla doğru sonuç dar:** *bu ızgara yoğunluğunda* plato seçimi yardım etmiyor ve
sıklıkla zarar veriyor. İki adaylık bir "plato"nun merkezi, tepeden anlamlı biçimde farklı
bir bilgi taşımaz. Izgarayı sıklaştırmak bu deneyi güçlendirir — ama o **ayrı bir hipotez
ve ayrı bir çekiliştir**, ve bu turun önceden yazılmış başarısızlık koşulu onu bu tur
içinde yapmayı dışlıyor.

## Ne öğrendik

1. **Hipotez yanlıştı ve yanlışlığı bilgi taşıyor.** IS yüzeyindeki "plato", bu veride ve
   bu ızgara yoğunluğunda, genelleme bilgisi **taşımıyor**. Tepenin komşuluğu tepeden daha
   güvenilir değil — yani IS yüzeyi bu ölçekte büyük ölçüde gürültü.
2. **`oos_is_orani`nın evrensel düşüşü seçim yönteminden gelmiyor.** Seçim kuralını
   değiştirmek onu düzeltmedi. Geriye iki açıklama kalıyor ve ikisi de bu turda test
   edilmedi: ya ızgaralar çok kaba, ya da bu strateji ailelerinin bu varlıkta yakaladığı
   şey in-sample'a özgü.
3. **Bir negatif sonuç, 14 çekilişe mal oldu** — ve defter bunu sayıyor. Kapıları geçen
   ilk strateji çıktığında bu sayı K-039'un düzeltme kararının girdisi olacak.

## Defterin durumu

**35 hipotez.** 7 (Faz 4, geriye dönük) + 10 (dönüş 1, ön kayıtlı) + 4 (dönüş 1, geriye
dönük) + 14 (dönüş 2, ön kayıtlı).

## Sırada ne var

Bu turun başarısızlık koşulu **üçüncü bir seçim yöntemini dışlıyor**. Açık kalan yönler,
hepsi yeni çekiliş:

1. **Daha yoğun ızgara.** Dönüş 2'nin ölçtüğü sınırı doğrudan hedefler: plato kavramı
   ancak yeterince nokta varsa anlamlı. Ucuz ama çekiliş sayısını hızla büyütür — ve
   K-039'un düzeltmesi hâlâ açık.
2. **Daha uzun veri, 4h.** Dönüş 1'in `asgari_islem` engelini hedefler.
3. **Yeni strateji ailesi.** §8/§9'a geri dönüş; en pahalı, en dürüst.

**Dördüncü bir seçenek de var ve kaydedilmeli:** durmak. 35 çekiliş sonunda hiçbir şeyin
geçmemesi bir başarısızlık değil, **bir ölçüm** — projenin başarı ölçütü zaten "kaç kötü
stratejiyi elediği" (Final-Doküman §Başarı ölçütü). Faz 6'nın gözlem koşusu 30 gün boyunca
altyapıyı ölçmeye devam ediyor ve Faz 7 (execution sandbox) promotion geçmiş bir strateji
**gerektirmiyor** — testnet'te emir mantığı kendi başına doğrulanabilir.
