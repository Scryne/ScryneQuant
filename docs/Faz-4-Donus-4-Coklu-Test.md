---
proje: ScryneQuant
faz: 4-donus-4
type: faz-raporu
tarih: 2026-09-11
status: kapandi
---
# Faz 4'e dönüş 4 — Çoklu test: **eşik ölçüldü, 0,50 → 1,02**

K-039'un açık düzeltmesi kapandı (K-044). Bu dönüş yeni bir hipotez **denemedi** — defter
38'de duruyor. Ölçülen şey stratejiler değil, **kapının kendisi**.

Ham kayıt: `runs/deneyler/coklu_test/91d0d4b0ff73-67b1eacf6ad5.json` ·
komut: `sq lab coklu-test --deneme 4000 --seed 0`

## 1. Neden şimdi, neden "ilk geçen strateji çıkınca" değil

K-039 düzeltmeyi *"kapıları geçen ilk strateji çıktığında"* diye ertelemişti. O erteleme
bir çelişki taşıyordu: düzeltmeyi bir geçeni **gördükten sonra** tanımlamak, bu projenin
başka her yerde yasakladığı şeydir — sonucu görüp kuralı ona göre ayarlamak (K-018,
K-042'nin durma kuralı).

Ertelemenin asıl gerekçesi *"o an defterdeki sayı bilinecek"*ti, çünkü çekiliş sayısı
büyümeye devam ettiği sürece düzeltme sabitlenemez. O koşul şimdi sağlandı: K-042 ile
funding kapandı, **bekleyen çekiliş yok**, defter 38'de dondu. Sayının bilindiği ve
hiçbir sonucun görülmediği tek an burası.

## 2. Yöntem — paylaşılan dairesel kaydırma

Sorunun tam hâli: *"31 çekiliş yapsaydım ve hiçbirinin edge'i olmasaydı, en iyisi ne kadar
iyi görünürdü?"*

1. Her çekilişin OOS **sinyal takvimi** çıkarılıyor (bar indeksi → yön, hedef maruziyet).
   Takvim, kayıtlı parametrelerle gerçek stratejiyi koşturarak üretiliyor.
2. Takvim `k` bar dairesel kaydırılıyor. Korunanlar: sinyal sayısı, aralık deseni, hedef
   maruziyet dağılımı — ölçümle doğrulandı, işlem sayısı ve piyasada kalma oranı kaydırma
   altında değişmiyor. Yok edilen tek şey fiyatla hizalanma, yani edge.
3. Kaydırılmış takvim **gerçek backtest motorundan** geçiriliyor. Yaklaşım yok: fill bir
   sonraki barın açılışında (K-004), aynı maliyet modeli, aynı Sharpe formülü.
4. O iterasyonun maksimumu, K-019'un ucuz kapılarını geçen çekilişler arasından alınıyor.

**Kaydırma iterasyon başına paylaşılıyor** — 31'ine de aynı oran uygulanıyor. Bağımsız
kaydırma stratejiler arası korelasyonu koparır, maksimumun dağılımını genişletir ve
düzeltmeyi olduğundan büyük gösterirdi; yani K-039'un reddettiği uydurulmuş çarpanı arka
kapıdan geri getirirdi. Paylaşılan kaydırmada korelasyon veriden geliyor.

**Doğrulama:** `k = 0` ile çalıştırıldığında 31 çekilişin 31'i de kayıtlı OOS Sharpe'ını
**birebir** (fark 0,0) yeniden üretiyor. Null ile gerçek sayı aynı kod yolundan çıkıyor.

## 3. Ölçülen sayılar

31 ölçülebilir çekiliş · 4.000 iterasyon · edge yok:

| Yanlış-pozitif | Düzeltilmiş `oos_sharpe` | %90 bootstrap GA |
| --- | ---: | --- |
| %20 | 0,589 | 0,574 – 0,605 |
| %10 | 0,777 | 0,754 – 0,800 |
| **%5 (seçilen)** | **1,017** | **0,975 – 1,055** |
| %1 | 2,424 | 1,829 – 3,040 |

Null dağılımı: p50 0,234 · p75 0,519 · p90 0,777 · p95 1,017 · p99 2,424

**Eski eşik 0,50'nin gerçek yanlış-pozitif oranı %26,3.** 0,50 hiçbir zaman %5'lik bir kapı
değildi; 31 çekilişte dört denemeden birini şansa geçiren bir kapıydı.

Sınır **1,02** olarak donduruldu. %5 bir iştah kararıdır (K-033), ölçüm değil. %1 ölçüldü
ama seçilmedi: güven aralığı [1,83 – 3,04], 4.000 iterasyonda savunulamayacak kadar geniş.

**Kararlılık:** p95 200 iterasyonda 0,854, 2.000'de 1,021, 4.000'de 1,017 çıktı. İlk
sayıdaki sapma gürültüydü ve tam da bu yüzden güven aralığı zorunlu hâle getirildi —
promotion eşiği olacak bir sayının hata payı, sayının kendisi kadar kayda geçmeli.

## 4. Çapraz kontrol: iki bağımsız yöntem uyuşuyor

| Yöntem | Sonuç | Varsayımı |
| --- | ---: | --- |
| Permütasyon null'ı (ölçülen) | **1,017** | yok — korelasyon veriden |
| Deflated Sharpe (Bailey & López de Prado) | 0,922 | Sharpe'lar normal dağılıyor |
| Bonferroni | 1,300 | **bağımsızlık** — bu veride yanlış |

İlk ikisi %10 içinde uyuşuyor ve tamamen farklı varsayımlar yapıyorlar; bu anlamlı bir
yakınsama. Bonferroni'nin yukarıda kalması K-039'un öngörüsünü doğruluyor: bağımsızlık
varsaymak fazla düzeltiyor ve uydurulmuş bir çarpan üretiyor.

## 5. Asıl bulgu eşik değil

**Projenin en iyi sonucu, saf şans beklentisinin altında.**

- 31 çekilişin gerçek en iyisi: `cok_faktor` 4h/plato, OOS Sharpe **0,4585**
- p-değeri: **0,296** — edge olmasa bile 31 çekiliş yapan biri vakaların yaklaşık üçte
  birinde bu kadar iyi bir sonuç görürdü
- Deflated Sharpe'a göre şans beklentisi 0,92; gözlenen 0,46 — yani sonuç, rastgeleliğin
  **üretmesi beklenenden daha kötü**

31 çekilişin OOS Sharpe dağılımı: ortalama **−0,3148** · sapma 0,4416 · min −1,0328 ·
max +0,4585 · pozitif olan **7/31**.

Bu "aramanın başarısız olduğu" değil, **"aramanın henüz hiçbir şey bulmadığı"**nın
ölçülmüş hâli. Fark korunuyor (K-042/5 ile aynı ayrım).

## 6. Ölçüm sırasında bulunan iki hata

İkisi de sessiz kalabilirdi ve ikisi de artık testle bağlı (`tests/unit/test_coklu_test.py`).

**1. Takvimin tanım kümesi.** Takvim indeksleri motorun gördüğü dilimin tamamı (ısınma
dahil) üzerinde üretiliyor, ölçüm ise dilimin son kısmında. Modül olarak ölçüm uzunluğu
verilince taşan indeksler sarmalanıp **birbirinin üstüne yazdı** — sinyaller sessizce
kayboldu, işlem sayısı düştü, Sharpe gürültüsü patladı. Null, rastgele bir stratejiye
p99'da **4,2 Sharpe** atfetti.

Sayı absürt olduğu için fark edildi. Biraz daha makul olsaydı fark edilmezdi ve K-039'un
düzeltmesi uydurulmuş bir sayıyla kapanırdı. Artık sığmayan indeks **hata**; sessizce mod
almak yok.

**2. Maksimum, uygunluk süzgeci olmadan alınıyordu.** Düzeltildikten sonra bile uçlar
kaldı ve ölçüm sebebi gösterdi: hepsi **az işlemli** çekilişlerdendi (`ema_kesisim` 4h, 14
işlem → null p99 3,03; `cok_faktor` 1h/plato, 98 işlem → null p99 −0,12). 14 işlemle
ölçülen Sharpe'ın örneklem varyansı devasadır.

Ama o çekiliş `asgari_islem ≥ 30` kapısında zaten ölüyor. Onu maksimuma katmak, hiç
geçemeyecek bir kapıdan geçme olasılığını hesaplamaktı — düzeltmeyi kendi kendine şişiren
bir hata.

## 7. Ölçülmeyen ve bu kayıtlı

**Düzeltme yalnızca `oos_sharpe` kapısına uygulandı.** Diğer altı kapı düzeltilmedi çünkü
ölçülmedi: her biri ayrı bir null ister, ve walk-forward ile stres kapıları iterasyon
başına yeniden ölçülemeyecek kadar pahalı. Yani **kapı kümesinin tamamının** yanlış pozitif
oranı hâlâ bilinmiyor.

Uygunluk süzgeci gerçek kapı kümesinden **gevşek** olduğu için ölçülen düzeltme
gerçeğinden **büyük** çıkıyor — yön bilinçli (K-007: belirsizlikte kötü yöne yuvarla).

**1d'nin yedi çekilişi ölçüme giremedi.** Dönüş 1'de walk-forward hiçbir katmanda geçerli
aday bulamamış, araç sayı uydurmak yerine reddetmişti. Sayı üretmemiş bir çekiliş yanlış
pozitif de üretemez, dolayısıyla maksimum istatistiğine giremez — ama defterden silinmez:
denendi, sayılır. **Defter 38, ölçülebilir 31.**

**Dairesel kaydırma bir null modelidir.** Sinyal zamanlamasının fiyattan bağımsız olduğu
bir dünya kuruyor. Stratejinin sinyal **yoğunluğu** rejime bağlıysa, kaydırma o bağı da
koparır ve null'ı bir miktar iyimser yapabilir. Kusur değil ama varsayım, ve yazılı.

## 8. Eşik bir sabit değil, defterin fotoğrafı

`COKLU_TEST_ESIGI = 1,02` **31 çekilişte** geçerli. Defter büyüdükçe gerçek eşik yükselir;
sabit yerinde kalırsa kapı sessizce gevşer ve K-039'un engellemeye çalıştığı şey
düzeltmenin kendi içinden geri gelir.

Bu yüzden `COKLU_TEST_CEKILIS_SAYISI = 31` de koda yazıldı ve testle bağlandı: sayı
değişirse test kırılır ve `sq lab coklu-test` yeniden koşturulmak zorunda kalır.

## 9. Üretilenler

- `research/coklu_test.py` — null kurgusu, `KayitliStrateji` / `BetikStrateji` ölçüm
  aletleri, dairesel kaydırma, Deflated Sharpe çapraz kontrolü, bootstrap güven aralığı.
  Ölçüm aletleri `KUTUPHANE`ye **bilerek kaydedilmedi**: kayıtlı olsalardı bir alet,
  hipotez defterine yazılabilir bir çekiliş hâline gelirdi (K-039).
- `research/kapilar.py` — `COKLU_TEST_ESIGI`, `COKLU_TEST_CEKILIS_SAYISI`; `oos_sharpe`
  sınırı 0,50 → 1,02.
- `research/deney.py` — yeni deney tipi `coklu_test`.
- CLI: `sq lab coklu-test`.
- `tests/unit/test_coklu_test.py` — 41 test.

**1061 → 1102 test yeşil.**

## 10. Sırada ne var

Bu ölçüm bir kapıyı sıkılaştırdı ama **hiçbir stratejiyi geçirmedi** — ve geçirmesi de
beklenmiyordu. Faz 8'in önündeki engel değişmedi ve şimdi daha net ölçülü: kapıları geçen
bir strateji yok, ve en iyi aday şans beklentisinin altında.

Devam edilecekse K-042'nin kuralı hâlâ bağlayıcı: **dördüncü bir parametre denemesi yok,
bilgi kaynağı değişmeli.** Ve artık her yeni çekiliş eşiği de yükseltiyor — bu, aramaya
devam etmenin bedelinin ilk kez sayısal olarak görünür olması demek.
