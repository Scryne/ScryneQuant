---
proje: ScryneQuant
faz: 16
tur: kaynak ölçümü (çekiliş değil)
tarih: 2026-09-18
type: rapor
durum: program açılmadı
---
# Faz 16 — Duyuru/olay kaynağının ölçümü

**Sonuç: program açılmıyor.** Duyuru verisi gerçek ve istatistiksel olarak sağlam bir etki
taşıyor, ama etki bu projenin **işlem yapamayacağı** yerde: evren dışındaki küçük
sembollerde ve **aşağı** yönde. Kıyasın yapısal kör noktası ölçüldü ve ilk bakışta kârlı
göründü (+%7,9); seçim yanlılığı kontrolü aynı duyuruları sabit ufukta **−%8,6**'ya
çevirdi. Kör pencere bir fırsat değil, bir kayıp bölgesi.

Ölçüm `tools/faz16_duyuru_olcum.py`, çıktı `runs/faz16/kaynak-olcumu-duyuru.json`.
**Bu bir çekiliş değildir** (K-039): strateji koşmadı, parametre seçilmedi, kapı
hesaplanmadı, defter büyümedi. İleriye dönük getiriye yalnızca in-sample penceresinde
bakıldı (bar 0-55.594, IS bitişi **2023-12-20 14:00 UTC**) — K-068'in ek şart maddesi.

## 1. Veri

| | |
| --- | --- |
| Kaynak | Binance duyuru arşivi (`tools/faz16_duyuru_indir.py`, `..._govde_indir.py`) |
| Duyuru | 10.380 (2017-08 → 2026-09), gövdesi inen 2.690 |
| Olay satırı | 8.276; 9 olay tipi; kotesi boş 43 |
| Ayrıştırma | Kural tabanlı (K-049/4: geçmiş dönem için LLM türetimi kapıya giremez) |
| Jev doğrulaması (K-067/3) | n=80, jev-1.13.0: olay uyumu **0,738**, yön uyumu **0,825** |
| Evren | PIT tablo `27b7a16ed0ed`, 429 sembol, 79.580 bar |
| Kesişim | 8.276 olay satırının **1.124**'ü evrende bir zamanlar yer almış bir pariteye ait |

**PIT durumu.** `yayin_ms` Binance'in kendi yayın zamanı — nokta-zamanda doğru alan budur.
`ilk_gorulen_ms` arşivden indirme anıdır (medyan 1.240 gün sonra) ve **kullanılamaz**.
Yıl dağılımı 2017'den bugüne sürekli (270 → 1.696/yıl), yani arşivde büyük bir silinme
izi yok; yine de "silinmiş duyuru" ihtimali ölçülemedi ve açık bırakılıyor.

## 2. Kıyasın kör noktası — ne kadar büyük

Kıyasın evreni ayda bir yenilenir, ölçüt önceki ayın hacmidir. Bir sembol ayın ortasında
listelendiğinde kıyas bunu ay başına kadar görmez.

| Ölçü | n | Medyan | p25 | p75 |
| --- | ---: | ---: | ---: | ---: |
| Duyurudan evrene girişe kadar (gün) | 755 | **32,6** | 17,7 | 174,2 |
| Duyurudan evrenden çıkışa kadar (gün) | 4 | 305,3 | 155,8 | 544,8 |

Kör pencere gerçek ve küçük değil: medyan bir ay, çeyrekte altı aydan uzun.

## 3. Kör pencerede getiri var mı — ve yanlılık kontrolü

| Ölçüm | n | Göreli medyan | Pozitif oran | İşaret p |
| --- | ---: | ---: | ---: | ---: |
| Duyurudan **evrene girişe** kadar (değişken ufuk) | 308 | **+%7,88** | 0,568 | 0,017 |
| Aynı duyurular, **sabit 30 gün**, sonradan girenler | 308 | **−%8,56** | 0,412 | 0,002 |
| Aynı duyurular, sabit 30 gün, **hiç girmeyenler** | 45 | −%6,61 | 0,400 | 0,180 |

(Göreli = sembolün log getirisi − aynı pencerede evren üyelerinin medyan log getirisi.)

**Birinci satır bir ölçüm hatasıdır, bulgu değil.** Pencere, sembolün evrene girdiği ayda
biter; evrene giriş ölçütü hacimdir ve hacim sıçraması fiyat sıçramasıyla gelir. Yani
pencerenin **bitiş noktası sonuca göre seçilmiş** oluyor. Aynı duyuruları sabit 30 günlük
ufukta ölçünce işaret dönüyor: +%7,88 → −%8,56. Fark (%16,4) yanlılığın kendisidir.

Bu, bu projenin uyarı cümlesinin somut hâli: "neredeyse doğru" sonuç fark edilmez. İlk
koşuda bu satır tek başına dursaydı, bir program açılması için yeterince ikna ediciydi.

**İkinci bir ölçüm hatası ilk koşuda yakalandı ve düzeltildi:** olay anında evren üyesi
olmayan semboller eleniyordu. Listeleme duyurusunda sembol **tanım gereği** henüz üye
değildir; üyelik şartı, ölçülmek istenen kör bölgeyi siliyordu (`spot_listeleme` n=9'a
düşmüştü). Araç artık iki kolu ayrı raporluyor.

## 4. Olay çalışması (IS, göreli log getiri medyanı)

| Olay | Kol | n | h24 | h72 | h168 | h720 | En düşük p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `vadeli_listeleme` | üye değil | 118 | −%2,5 | −%5,1 | −%7,1 | **−%17,6** | **0,00023** |
| `vadeli_listeleme` | üye | 45-46 | −%0,2 | +%0,2 | −%0,5 | −%4,4 | 0,456 |
| `marjin_ekleme` | üye değil | 216 | −%1,1 | −%2,1 | −%0,9 | −%3,4 | 0,021 |
| `marjin_ekleme` | üye | 44 | −%0,9 | −%1,5 | −%3,4 | +%3,4 | 0,132 |
| `marjin_kaldirma` | üye değil | 27-34 | −%2,0 | −%0,9 | −%3,1 | −%1,3 | 0,016 |
| `spot_listeleme` | üye değil | 19 | +%1,6 | −%1,7 | +%2,8 | −%13,5 | n<30 |
| `delist` | üye değil | 4 | −%14,2 | −%37,3 | −%49,4 | — | n<30 |

Bu dosyada 56 karşılaştırma var; tek bir p-değeri kapı değildir. En güçlü hücre
(`vadeli_listeleme`, üye değil, h720) Bonferroni'yi de geçiyor: 2,3·10⁻⁴ × 56 = **0,013**.

## 5. Okuma — ve neden program açılmıyor

1. **Etki gerçek ve tutarlı:** vadeli listeleme duyurusu, evren dışındaki semboller için bir
   ay boyunca kıyasa göre **−%17,6** medyan; pozitif oran 0,331 (n=118). Dört ufkun dördü
   de aynı yönde ve büyüyor. Marjin ekleme ve marjin kaldırma da aynı işarette. Anlatı
   makul: erişim genişlemesi duyurusu, beklentinin fiyatlandığı yerde gelir ve sonrasını
   satar.
2. **Ama üye kolunda kaybolan bir etki bu.** Aynı olay, evren üyesi sembollerde h720'de
   −%4,4 ve p=0,456 — yani kıyasın **tuttuğu** isimlerde ölçülebilir bir şey yok. Kıyasın
   seçimini iyileştirecek bir dışlama buradan çıkmaz; K-068'in kapattığı desenin tekrarı
   olurdu, üstelik daha zayıf sayılarla.
3. **Etkinin yaşadığı yerde işlem yapılamıyor.** İşaret aşağı yönde, portföy modeli
   **açığa satış ve kaldıraç tanımıyor** — `portfolio/durum.py` bunu bir tercih değil
   değişmez olarak zorluyor ("miktar negatif olamaz", "nakit negatif olamaz"). Long-only
   bir portföyde aşağı yönlü bir sinyal ancak dışlama olarak kullanılır ve dışlanacak
   isimler zaten portföyde değil.
4. **Evreni genişletmek bu bulguyu kurtarmaz, sorunu taşır.** Etki `asgari_quote_hacim`
   30 M USDT'nin altındaki isimlerde; evreni oraya açmak kapasite ve maliyet varsayımlarını
   (K-021, K-007) yeniden ölçmeyi gerektirir ve etkinin yönü yine satış tarafındadır.

**Karar:** duyuru kaynağı üzerine program açılmıyor. Ölçüm dört çekilişlik bir bütçeyi
harcamadan bu cevabı verdi — kaynak ölçümünün varlık sebebi tam olarak bu.

## 6. Açık bırakılanlar

- **Silinmiş duyuru ihtimali ölçülmedi.** Yıl dağılımı düzgün ama arşivin bugünkü hâli
  geçmişteki hâli midir, bilinmiyor. Bir gün duyuru üzerine bir şey kurulursa bu önce
  ölçülür.
- **`etkili_ms` olayların %41,7'sinde var.** Duyuru metninde işlem başlangıç saati yazmayan
  %58,3 için `yayin_ms` kullanıldı; bu, etkinin gerçekte olduğundan **erken** ölçülmesi
  anlamına gelebilir (muhafazakâr yön değil — K-007'nin tersi). Program açılsaydı bu ilk
  kapatılacak şeydi.
- **Jev'in yakaladığı ama kuralın kaçırdığı duyurular.** Olay uyumu 0,738; kalan %26'nın
  içinde başka olay tipleri olabilir. Kural tabanlı ayrıştırma geçmiş dönem için zorunlu
  (K-049/4), dolayısıyla bu bir tavan.
