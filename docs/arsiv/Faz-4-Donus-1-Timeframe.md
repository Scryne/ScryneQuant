---
proje: ScryneQuant
created: 2026-09-11
type: deney-raporu
faz: 4
tur: 1
status: kapandi
---
# Faz 4'e dönüş 1 — Timeframe hipotezi

> **Sonuç: hipotez çürütüldü, ama boş çürütülmedi.** Mekanizmanın öngörülen etkisi
> ölçüldü ve gerçek; yalnızca kendi ayağına bastı. Hiçbir strateji K-019'un kapılarını
> geçmiyor ve eşikler değiştirilmedi.

## Hipotez (sonuç görülmeden yazıldı)

Faz 4'te altı stratejinin **altısının da** out-of-sample'da negatif çıkmasının sebebi
stratejilerin kendisi değil, **1h timeframe'inin maliyet/gürültü oranı** olabilir.

Mekanizma somut: tur başına maliyet sabit (K-021: gidiş-dönüş 30,6 bps) ama bar başına
fiyat hareketi timeframe uzadıkça büyür. Yani aynı sinyal mantığı daha uzun ufukta daha az
işleme, daha büyük harekete ve dolayısıyla daha düşük maliyet/getiri oranına denk gelir.

**Beklenti:** trend takibi ailelerinde (kesişim, kırılım, momentum) OOS Sharpe'ın 1h'e göre
yükselmesi. Ortalama dönüşte beklenmiyor — o yüzden ilk turda kaydedilmedi.

**Önceden belirlenen başarısızlık koşulu:** K-019'un yedi kapısı değişmez. Geçemezse sonuç
"timeframe hipotezi bu veride çalışmadı" olarak kaydedilir ve ızgara genişletilmez.

**Ön kayıt:** hipotezler 8-17 (`docs/Hipotez-Defteri.jsonl`), K-039 uyarınca koşudan önce.

## Veri

Yeniden örnekleme değil, **borsanın kendi toplamı** indirildi — aynı test edilmiş
doğrulama yolundan geçsin diye (K-006, K-023).

| Timeframe | Bar | Aralık | Kalite | SHA-256 |
| --- | ---: | --- | --- | --- |
| 4h | 11.615 | 2021-05-24 → 2026-09-11 | ok %100, boşluk 0 | `c4ed6bcb4e77` |
| 1d | 1.936 | 2021-05-24 → 2026-09-10 | ok %100, boşluk 0 | `fa957f260f1d` |

Slippage kalibrasyonu (K-021, 5,2996 bps) **aynen geçerli**: yürütme penceresindeki fiyat
hareketinden türetildi (bar kapanışı → emrin dolması, ~300 ms) ve bar süresinden bağımsız.

## Ölçüm 1 — IS/OOS (%70/%30), 4h

```
strateji     aile              plato  IS-shp  OOS-shp  OOS/IS  OOS-get  OOS-DD  işlem
sma_kesisim  kesisim            0.07    1.10     0.39    0.35     2.9%    7.5%     18
ema_kesisim  kesisim            0.13    1.00     0.32    0.32     2.3%    7.0%     14
rsi_donus    ortalama_donus     0.13    0.63    -0.45   -0.72    -6.2%   12.2%      4
donchian     kirilim            0.17    1.08    -0.33   -0.31    -3.2%    8.9%     37
momentum     momentum           0.14    0.85    -0.18   -0.21    -1.9%    9.7%     25
cok_faktor   cok_faktor         0.11    1.13     0.17    0.15     1.1%    7.1%     25
al_tut       kiyas              1.00    0.72    -0.33   -0.46    -4.4%   12.9%      0
```

**Mekanizma çalıştı.** 1h'te altı stratejinin altısı da OOS'ta negatifti; 4h'te iki kesişim
ailesi **pozitife döndü** (+0,39 ve +0,32) ve bunu kıyasın **negatif** olduğu (−0,33) bir
pencerede yaptı. Yani bu, varlığın yükselmesinden gelen bir kazanç değil.

Bu, hipotezin öngördüğü yön. Ama yeterli değil.

## Ölçüm 2 — K-019 kapıları, 4h (WF: 16 katman, 1 yıl eğitim / 3 ay test)

Walk-forward pencereleri **bar değil süre** olarak çevrildi (2190/547 bar = 1 yıl / 3 ay),
Faz 4'ün penceresiyle aynı takvim aralığı kalsın diye.

```
strateji      oos_sharp oos_is_or wf_katman parametre asgari_is max_drawd stres_day  SONUÇ
sma_kesisim           ✗         ✗         ✓         ✓         ✗         ✓         ✓  kaldı
ema_kesisim           ✗         ✗         ✗         ✓         ✗         ✓         ✓  kaldı
rsi_donus             ✗         ✗         ✓         ✓         ✗         ✓         ✓  kaldı
donchian              ✗         ✗         ✗         ✓         ✓         ✓         ✓  kaldı
momentum              ✗         ✗         ✗         ✓         ✗         ✓         ✓  kaldı
cok_faktor            ✗         ✗         ✗         ✓         ✗         ✓         ✗  kaldı
al_tut                ✗         ✗         ✗         ✓         ✗         ✓         ✓  kaldı
```

**Kapılardan geçen strateji yok.**

## Asıl bulgu: mekanizma kendi ayağına bastı

Hipotezin öngördüğü şey oldu — ama öngörülmeyen bir bedelle.

| | 1h | 4h |
| --- | --- | --- |
| `sma_kesisim` OOS Sharpe | negatif | **+0,39** |
| `sma_kesisim` işlem sayısı | ✓ (≥30) | **18 (✗)** |
| `ema_kesisim` işlem sayısı | ✓ | **14 (✗)** |

**Timeframe'i uzatmak maliyet/gürültü oranını iyileştirdi ve aynı anda istatistiksel gücü
yok etti.** Aynı 5,3 yıllık veri, 4 kat az bar, 4 kat az işlem. `asgari_islem ≥ 30` kapısı
tam da bunu yakalamak için var: 18 işlemle kurulan bir iddia, Sharpe pozitif olsa bile
gürültüden ayırt edilemez.

Yani iki kapı birbirini dengeliyor ve bu bir kusur değil, tasarım: bir tarafı iyileştirmek
için diğerini feda eden bir değişiklik, kapıların toplamından geçemiyor.

## 1d: ölçüm yapılamadı ve bu da bir ölçüm

`sq lab kapilar -t 1d` walk-forward'ı **tamamlayamadı**:

```
hata: WalkForwardHatasi: hiçbir katmanda geçerli aday bulunamadı —
      ızgara veya asgari işlem şartı gözden geçirilmeli
```

1.936 günlük bar üzerinde 365 barlık bir eğitim penceresi, tarama şartını (≥20 işlem)
sağlayan tek bir parametre noktası bile üretmiyor. IS/OOS tablosunda da kesişim aileleri ve
donchian "geçerli aday yok" dedi.

**Araç sayı uydurmak yerine reddetti** ve doğru olan buydu. 1d bu veri uzunluğunda
istatistiksel güç tabanının altında: 5,3 yıl günlük veriyle trend takibi sınanamaz. Bunu
aşmanın yolu eşiği indirmek değil, **daha uzun veri** — ve BTC'nin 2017 öncesi verisi bugün
işlem gördüğü piyasa değil.

## Ne öğrendik, ne öğrenmedik

**Öğrendik:**

1. Maliyet/gürültü mekanizması **gerçek ve ölçülebilir**: 1h → 4h geçişi kesişim
   ailelerinin OOS Sharpe'ını negatiften +0,3-0,4 bandına taşıdı.
2. Ama tek başına yetmiyor: 0,50 eşiğine ulaşmıyor ve işlem sayısını eşiğin altına düşürüyor.
3. 1d bu veri setiyle **sınanamaz** — güç tabanının altında.
4. Walk-forward yine tek bölmeden farklı konuştu (`al_tut` WF-Sharpe 0,85 ama OOS −0,33).
   Faz 4 §9.4'ün bulgusu tekrarlandı: tek bir OOS testine güvenilmez.

**Öğrenmedik:** 4h'in daha uzun veriyle ne yapacağını. 11.615 bar, kapıların istediği
kanıtı üretmeye yakın ama yetmiyor. Bu, ızgarayı genişletmenin değil, **veriyi
uzatmanın** sorusu — ve o ayrı bir hipotez, ayrı bir çekiliş.

## Süreç hatası ve düzeltmesi

`sq lab karsilastir` tasarımı gereği yedi ailenin **hepsini** koşturuyor (K-030 kıyası
zorunlu kılıyor). Ben yalnızca beşini kaydetmiştim; `rsi_donus` ve `cok_faktor` için 4h/1d
sonuçları **ön kayıt olmadan görüldü**.

İkisi geriye dönük kaydedildi (hipotez 18-21) ve kayıtları bunu açıkça söylüyor: ön kayıt
sayılmazlar ve o iki ailenin 4h/1d sonuçları ön-kayıt kanıtı olarak kullanılamaz. Ama
sayılmak zorundalar — kaydedilmemiş bir çekiliş sayacı olduğundan küçük gösterir.

**Asıl kusur araçtaydı:** K-039'un ilk hâlinde defteri yalnızca promotion kapısı kontrol
ediyordu, oysa çekiliş laboratuvarda yapılıyor. `sq lab` komutlarının hepsi artık defteri
zorluyor ve kaydedilmemiş bir strateji **koşturulamıyor**. Kaçış kapısı bilerek yok:
"sadece bakıyorum" diye koşturulan bir strateji de bir çekiliştir.

## Defterin durumu

**21 hipotez** (7 Faz 4 + 10 ön kayıtlı + 4 geriye dönük). Kapıları geçen ilk strateji
çıktığında bu sayı K-039'un düzeltme kararının girdisi olacak.

## Sırada ne var

Bu turun sonucu ızgarayı genişletmeyi **dışlıyor** (önceden yazılmış başarısızlık koşulu).
Açık kalan iki yön — ikisi de yeni hipotez, yeni çekiliş:

1. **Daha uzun veri, 4h.** 2017-2021 arası BTC verisiyle 4h'in bar sayısını iki katına
   çıkarmak. Bedeli: o dönemin piyasası bugünkünden yapısal olarak farklı (likidite, vade
   ürünleri, kurumsal katılım) — yani eklenen veri "daha çok aynı şey" değil.
2. **Yeni strateji ailesi.** Volatilite rejimi, ortalama dönüş bandı gibi denenmemiş
   fikirler. Daha büyük tasarım işi ve §8/§9'a geri dönmeyi gerektirir.
