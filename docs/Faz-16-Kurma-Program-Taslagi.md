---
durum: onaylandı
tarih: 2026-09-18
karar: Scryne onayladı (2026-09-18)
---

# Faz 16 — Program taslağı: portföy kurma (`kurma_evren`)

Bu bir **program kaydı taslağıdır** (K-051/2). Onaylanırsa `sq lab program-kaydet` ile
deftere açılır; açılmadan hiçbir çekiliş koşmaz (K-039).

## 1. Soru

Aynı seçim, farklı **kurma**: portföyün nasıl kurulduğu — ağırlıklandırma, korelasyon
budaması, turnover bandı, konsantrasyon — kıyasın risk-ayarlı getirisini iyileştirir mi?

## 2. Neden bu program K-068'in kapattığı desenin tekrarı değil

Defterdeki 50 çekilişin **50'si de seçimi değiştirdi.** Tek sembollü aramada (K-045) hangi
barda girileceği, evren programlarında (K-068) hangi sembolün dışlanacağı soruldu. Kurma
katmanına bugüne kadar **tek bir çekiliş harcanmadı**; kıyas `esit_agirlik=True`,
`korelasyon_tavani=None`, `turnover_bandi=0.0` ile koşuyor ve bu üç değer ölçülerek değil,
varsayılan olarak seçilmiş.

Farkın mekanizması da başka: **kurma bir tahmin yapmıyor.** Oynaklık ayarlı boyutlandırma,
"hangi sembol yükselecek" demiyor; aynı seçimi farklı risk katkılarıyla taşıyor. Sekiz
çekilişin gösterdiği şey "bu veride kesitsel tahmin gücü yok"tu; kurma katmanı tahmin gücü
gerektirmiyor, dolayısıyla o bulgu bu soruyu kapatmıyor.

`strategy/kurma.py` bunu zaten yazıyor: *"Varsayılan 0: Faz 10 yöntemi **kurar**, sayıyı
ölçmez. Bağlayıcı bir bant Faz 12'de, turnover'ın gerçek maliyeti ölçüldüğünde yazılır."*
Faz 12 bunu yapmadı. Bu program o açık kalemi kapatıyor.

## 3. Karşı argüman — kayda geçsin

**K-045 maliyet duvarının bağlayıcı kısıt olmadığını ölçtü:** maliyet sıfıra indirildiğinde
bile kapıları geçen strateji çıkmadı. Turnover bandının yaptığı şey maliyeti düşürmektir.
Dolayısıyla 2. çekilişin (turnover bandı) önsel beklentisi **düşük** ve bu, sonucu görmeden
yazılıyor. Bandın asıl değeri başka bir yerde olabilir — gürültüye tepki veren yeniden
dengelemeleri elemek — ama bu ayrı bir iddia ve ölçüm onu ayırt edemez.

Aynı şekilde: kıyasın OOS'ta 108 işlemi var ve komisyon+slippage toplamı 105 USDT
(10.000 USDT sermayede **%1,05**). Turnover tarafında kazanılabilecek üst sınır budur.
**Tavan ölçüldü, bandın alabileceği pay bunun bir kesri.**

## 4. Çekilişler (bütçe 4)

Hepsi kıyasla **aynı evreni, aynı seçimi, aynı dengeleme takvimini** kullanır; değişen tek
şey `KurmaAyarlari`. Değişken sıfır/kapalı konumdayken sonuç kıyasla **bit düzeyinde aynı**
olmalı (testle zorlanır — funding ailesinde aynı disiplin uygulandı).

| # | Ad | Değişen | Soru | Kod durumu |
| --- | --- | --- | --- | --- |
| 1 | `evren_oynaklik_agirlik` | `esit_agirlik=False` | Oynaklık ayarlı boyut, eşit ağırlığı geçer mi | **Hazır** (`EvrenEsitAgirlik(esit_agirlik=...)`) |
| 2 | `evren_turnover_bandi` | `turnover_bandi` | Gidiş-dönüş maliyetinden küçük dengelemeleri elemek | Parametre stratejiye açılacak |
| 3 | `evren_korelasyon_budama` | `korelasyon_tavani` | Aynı riski iki kez almamak Sharpe'ı artırır mı | Parametre + korelasyon penceresi açılacak |
| 4 | `evren_konsantrasyon` | `azami_enstruman`, `azami_agirlik` | Kaç isim taşımak ve tek isim tavanı | **Hazır** |

**Izgaralar — uygulama sırasında düzeltildi** (her çekiliş 12 nokta, türev/konumlanma
programlarıyla aynı biçim; K-058'in `pbo` eşiği o biçimde kalibre edildi):

1. `kurma_oynaklik`: `azami_agirlik_carpani` ∈ {1,25, 1,5, 2,0, 10,0} × `azami_enstruman`
   ∈ {5, 10, 20}
2. `kurma_turnover`: `turnover_bandi` ∈ {0,0025, 0,005, 0,01, 0,02} × `azami_enstruman`
   ∈ {5, 10, 20}

Sabitler kıyasla aynı: `yeniden_dengele_bar` = 168, `hedef_brut` = 0,2, evren `27b7a16ed0ed`.

**Taslakta yazdığım üç şey yanlıştı; ölçülünce düzeldi:**

1. **`azami_agirlik` mutlak bir eksen olamaz.** `hedef_brut = 0,2` ve 10 isimde eşit pay
   0,02; 0,15 ya da 0,30 gibi bir tavan hiçbir zaman bağlamaz, yani ızgaranın o ekseni ölü
   olurdu ve dört nokta birbirinin kopyası çıkardı — olmayan bir plato. Eksen **eşit payın
   çarpanı** olarak yeniden yazıldı; her yoğunlukta aynı soruyu sorar.
2. **ATR penceresi eksen yapılamaz.** Kıyasın docstring'i `ATR_PENCERESI = 14`'ün risk
   motorunun penceresiyle aynı olmasının bilinçli olduğunu yazıyor. Eksen yapmak o kararı
   sonuca bakarak bozmak olurdu; sabit kaldı.
3. **`yeniden_dengele_bar` ve `hedef_brut` tek değerli olmak zorunda.** Koşucu
   (`tools/faz12_evren_kos.py`) kıyası bu iki alandan kuruyor ve çok değerli olurlarsa
   kıyas kurulamaz. Dengeleme sıklığı ayrı bir çekiliş konusu, bu ikisinin ekseni değil.

Korelasyon budaması ve tavan çekilişleri (3 ve 4) **kodlanmadı**: durma kuralı gereği ilk
iki çekiliş kıyası geçmezse harcanmayacaklar, ve korelasyon budaması `kur()`a bir korelasyon
matrisi beslemeyi gerektiriyor — henüz kimsenin hesaplamadığı bir şey. Gerekirse yazılır.

## 5. Durma kuralı

İlk **iki** çekiliş (`evren_oynaklik_agirlik`, `evren_turnover_bandi`) OOS'ta filtresiz
kıyasın Sharpe'ını geçmezse 3 ve 4 **harcanmaz**, program kapanır. Izgara, pencere kümesi
ya da eşikler sonuçlara bakarak genişletilmez.

Ek durma kuralı (bu programa özel): bir çekilişte değişken sıfır/kapalı konumdayken kıyasla
bit düzeyinde eşitlik **bozulursa**, koşu durur ve sebep bulunmadan devam edilmez (K-038
kalıbı). Kurma katmanındaki sessiz bir fark, bütün sonuçları karşılaştırılamaz yapar.

## 6. Eşik ve sayım

- Defter bu programın açılışında **50 kayıt**. `oos_sharpe` kapısı program açılmadan **önce**
  `tools/faz12_coklu_test.py --deneme 500 --seed 0` ile yeniden ölçülür (K-044); bugünkü
  değer 1,04 ve 41 ölçülebilir çekilişle kalibre edilmişti.
- Bu programın her çekilişi defteri büyütür ve çıtayı yükseltir.
- Her hipotez kaydından önce `sq lab tekrar-kontrol` (K-061) koşar.

## 7. Ölçüm sözleşmesi

- Kurma yönteminin **her alanı** `yontem_kimligi`ne girer ve hipotez kaydının parçasıdır
  (K-051/4). "Eşit ağırlık yerine oynaklık ayarlı deneyelim" cümlesi yeni bir sorudur.
- `azami_agirlik` ve `hedef_brut` stratejinin iştahıdır, risk limitinin kopyası değil; ikisi
  çeliştiğinde risk motoru kazanır (K-037). Buradaki hiçbir sayı canlıda bir kapı açmaz.
- Oynaklık paydası ATR/fiyat; sıfır oynaklıkta aday elenir, uydurulmaz.
- Korelasyon matrisi yoksa budama **yapılmaz** (bilginin yokluğu, ilişkisizlik değildir).

## 8. Uygulamada çıkan iki açık kalem

1. **`evren_turnover_bandi`in null'ı yaklaşık.** Çoklu test null'ı (K-044) çekilişin
   **iddiasını taşıyan** özelliği kaydırır. Turnover bandının hiçbir tahmini yok — bant bir
   şey öngörmez, ağırlık değişimini bastırır. Kaydırılacak doğal bir sinyal olmadığı için
   sıralama ölçüsü (`kote_hacim`) kaydırılıyor; null'da bant da çalıştığı için null dağılımı
   sıfır çevresinde değil, kaydırılmış kıyasın Sharpe'ı çevresinde toplanıyor. **O çekiliş
   için ölçülen düzeltme muhafazakâr değildir** ve rapor bunu yazacak.
2. **`agirliklar()`de bir hata bulundu (K-070).** Tavana kırpılan pozisyon kilitlenmiyordu ve
   sonraki turda yeniden pay alıp tavanı aşıyordu; 3 adaylı bir vakada tavanın iki katına
   çıktığı ölçüldü. Bu programın ilk çekilişi o kod yolunu ilk kez gerçekten çalıştırdığı
   için ortaya çıktı. Düzeltildi; hiçbir kayıtlı sonuç değişmedi (gerekçe K-070'te).

## 9. Jev'in bu programdaki yeri

Yalnızca kayıt öncesi gizli tekrar kontrolü (K-061). Kurma sayısal bir katman; Jev metin
yargısı verir, buraya girmez.
