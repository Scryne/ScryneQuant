---
proje: ScryneQuant
tarih: 2026-09-23
karar: K-117
tur: ölçüm (kapıların istatistiksel gücü; çekiliş değil, defter satırı değil)
type: rapor
---
# Pozitif kontrol — kapılar gerçek bir üstünlüğü geçirebiliyor mu?

**Sonuç: Hayır, büyük ölçüde geçiremiyor.** 62 çekilişin 0'ı geçti. Kapıların gücü o güne
kadar hiç ölçülmemişti; yalnız yanlış pozitif oranı (null kalibrasyonu) ölçülmüştü. Bu ölçüm
gücü ölçtü. Gerçek motorla, gerçek maliyetle, gerçek bölmeyle ve K-019 + K-113 kapılarıyla
koşulan **%65 isabetli günlük kahin** (OOS Sharpe medyanı **2,06**) 20 tohumun **0'ında**
geçti. Haftalık ufukta hiçbir üstünlük düzeyi geçemiyor. Motorun kendisi doğru: bağımsız
numpy hesabıyla getiri ve Sharpe 4/4 senaryoda eşit (±%4).

Bu ölçüm 62 çekilişin aslında iyi olduğunu **göstermez**. En iyi OOS Sharpe'ları 0,46,
null persentil medyanı 0,50 (K-110); bu, isabeti ≤ %55 olan bir kahinin düzeyi. Gösterdiği
şey başka: **kapı sistemi iyi bir stratejiyi de reddediyordu**, yani 0/62 tek başına "alfa
yok" kanıtı değildi. Ayrıca yavaş (haftalık+) stratejiler yapısal olarak ölçülemediği için
arama bu bölgeye hiç bakamadı.

## Yöntem

`tools/pozitif_kontrol.py` (ölçüm aleti; `KUTUPHANE`de yok, K-039). Kahin her `ufuk` barda
karar verir. Sonraki `ufuk` barın (t+1 açılışı → t+1+ufuk açılışı) getiri işaretini `p`
olasılıkla doğru bilir. Yukarı derse 0,2 long, aşağı derse FLAT: kütüphaneyle aynı eylem
uzayı ve maruziyet. BTCUSDT 1h, 45.828 bar (2021-06 → 2026-09), `config/maliyet.json` (10 +
5,3 bps). `research/degerlendirme.degerlendir`in tek noktalı kopyası kullanıldı: aynı IS/OOS
(%30), aynı walk-forward (8.766 / 2.190), stres, `kapilar.degerlendir`; ek olarak K-054
rejim kapısı. Izgara: p ∈ {0,50 … 0,65} × ufuk ∈ {24, 72, 168} × 20 tohum = 420 değerlendirme.
Ham sonuç `runs/pozitif_kontrol/izgara.json`.

**Motor doğrulaması:** aynı sinyal, motorsuz vektörel hesap (open→open, değişimde maruziyet ×
(fee+slippage)): p0,60/24 +0,694 vs motor +0,690 (Sharpe 1,37 / 1,37); p0,50/24 −0,173 /
−0,172; p0,60/168 +0,357 / +0,361; p0,55/72 +0,390 / +0,375.

## Sonuç (20 tohumda geçen sayısı)

| p | ufuk | OOS Sh medyan | IS Sh medyan | K-019+K-113 | stres hariç | stres hariç + rejim | En sık kalan |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 0,50 | 24 | −0,62 | −0,15 | 0 | 0 | 0 | oos_sharpe 20 |
| 0,50 | 72 | 0,01 | 0,29 | 0 | 0 | 0 | oos_sharpe 20 |
| 0,50 | 168 | 0,16 | 0,53 | 0 | 0 | 0 | wf/kararlılık/asgari_islem 20 |
| 0,54 | 72 | 0,36 | 0,73 | 1 | 1 | 1 | oos_sharpe 19 |
| 0,56 | 72 | 0,48 | 0,94 | 3 | 3 | 3 | oos_sharpe 17 |
| 0,58 | 24 | 0,88 | 1,33 | 0 | 4 | 2 | stres 20 |
| 0,58 | 72 | 0,63 | 1,15 | 3 | 5 | 3 | oos_sharpe 15 |
| 0,60 | 24 | 1,11 | 1,65 | **0** | 10 | 9 | stres 20 |
| 0,60 | 72 | 0,79 | 1,40 | 1 | 7 | 5 | oos_sharpe 13, stres 10 |
| 0,60 | 168 | 0,74 | 1,35 | **0** | 0 | 0 | wf/kararlılık/asgari_islem 20 |
| 0,65 | 24 | **2,06** | 2,60 | **0** | **19** | **19** | stres 20 |
| 0,65 | 72 | 1,33 | 1,99 | **0** | 15 | 12 | stres 20 |
| 0,65 | 168 | 1,11 | 1,87 | **0** | 0 | 0 | wf/kararlılık/asgari_islem 20 |

Null satırları (p = 0,50) 0/60: yanlış pozitif kontrolü çalışıyor.

## Bulgular

1. **`stres_dayanikliligi` iyi stratejiyi cezalandırıyor.** Ölçtüğü şey, *tüm dönemde*
   (≈ 5,2 yıl) temel getiri − en kötü senaryo getirisi, yüzde puan olarak (≤ 15). Bu fark işlem
   sayısıyla, dönem uzunluğuyla ve **stratejinin kendi getirisiyle** (bileşik) büyür. %60
   günlük kahin 2x maliyette hâlâ +%26 kazanıyor ama 43 puan kaybettiği için kalıyor. Kapının
   gerekçesi ("2x maliyette çöken strateji") ile ölçtüğü şey farklı. Kaynağı `politika`,
   ölçülmemiş (Threshold-Policy).
2. **Yavaş stratejiler yapısal olarak ölçülemiyor.** Haftalık ufukta walk-forward her 1 yıllık
   eğitimde ≥ 20 işlem istiyor (`tarama.ASGARI_ISLEM`), OOS ≥ 30 istiyor (569 günde). Yılda
   ~13 turluk bir strateji üstünlüğü ne olursa olsun 3 kapıda "ölçülemedi" ile kalıyor.
   Faz 11'deki 1d `sma_kesisim`/`ema_kesisim` "geçerli aday yok" sonuçları da bu. Kriptoda en
   çok belgelenmiş aile (yavaş trend) aranamadı.
3. **`oos_sharpe` ≥ 1,04'ün gücü düşük.** OOS 1,57 yıl ve düşen piyasa (BTC −%15,5, al-tut
   Sharpe −0,25). Güçlü bir kahin (%60/24, OOS medyan 1,11) kapıyı yalnız 10/20'de geçiyor.
   Bu bir hata değil, verinin sınırı: 1,57 yılda Sharpe'ın standart hatası ≈ 0,8.
4. **Kapılar yığılıyor.** Her kapı ayrı ayrı %5 yanlış pozitife kalibre, üstüne `oos_sharpe`
   48 çekiliş için düzeltilmiş. Birlikte uygulanınca sistemin yanlış pozitif oranı %5'in çok
   altında, gücü ise sıfıra yakın. Kalibrasyon tek yönlü yapıldı.
5. **Hata (düzeltildi, K-117):** tek sembollü `degerlendirme` stresi `sinif()`, yani varsayılan
   parametrelerle koşuyordu; evren yolu seçileni koşuyordu. 38 tek sembollü çekilişin stres
   ölçümü başka bir parametre setine aitti (hepsi `oos_sharpe`'ta zaten kaldığı için sonuç
   değişmiyor).
6. **`evren_dayanikliligi` tek sembolde tanım gereği ölçülemez** (Faz 11: 38/38). Tek sembollü
   hiçbir strateji 12 kapıyı geçemez. Bu bir tasarım kararı, ama kayıtta "0/38" olarak
   sonuç gibi duruyor.

## Ne değişmedi / ne açık

Eşikler ve kapı tanımları **değişmedi.** Kapı tanımını değiştirmek K-050'ye göre yeni K, elle
onay ve bu araçla **iki yönlü** doğrulama ister: gücü pozitif kontrolle, yanlış pozitifi null
kalibrasyonuyla. Öneriler K-117'de `DECISION REQUIRED` olarak duruyor.
