---
proje: ScryneQuant
faz: 4-donus-5
type: faz-raporu
tarih: 2026-09-11
status: kapandi
---
# Faz 4'e dönüş 5 — Tavan testi: **maliyet duvarı bağlayıcı kısıt değilmiş**

Tek sembollü yönlü strateji araması kapandı (K-045). Bu dönüş de yeni bir hipotez
**denemedi** — defter 38'de duruyor. Ölçülen şey stratejiler değil, **ulaşılabilir olanın
üst sınırı**.

## 1. Cevaplanan itiraz

K-044'ten sonra ortada şu tablo vardı: 38 hipotez, hiçbiri geçmedi, en iyi sonuç şans
beklentisinin altında. Ciddi bir itiraz duruldu:

> *"38 çekilişin 38'i de sinyal tarafındaydı. Maliyet tarafına hiç bakılmadı. Gidiş-dönüş
> %0,306 ödüyoruz ve bu her stratejinin aşması gereken bir duvar. Maker yürütmeyle yarıya
> inebilir."*

İtiraz haklıydı ve test edilmeden reddedilemezdi.

## 2. Haftalar yerine saatler: tavanı ölç

Maker yürütme modeli kurmak — doluluk olasılığı, dolmama yolu, testnet ölçümü — haftalar
alırdı. Onun yerine **üst sınır** ölçüldü: maliyet **sıfır** kabul edilip aynı çekilişler
yeniden koşturuldu.

Sıfır maliyet fiziksel olarak imkânsızdır ve amaç tam olarak budur: hiçbir yürütme
iyileştirmesi bu sonuçları geçemez. **Tavan kapıdan alçaksa, aradaki her şey boştur.**

Bu bir hipotez çekilişi değil ve K-039'a girmiyor: strateji seçilmiyor, parametre
aranmıyor, yeni bir soru sorulmuyor. Sorulan tek şey *"tavan kapıdan yüksek mi"*.

## 3. Duyarlılık eğrisi — 1h

| Maliyet | Gidiş-dönüş | En iyi strateji | OOS Sharpe | Geçen |
| --- | ---: | --- | ---: | --- |
| Gerçek (1,00x) | %0,306 | `funding_egilim` | 0,288 | hiçbiri |
| Yarı (0,50x) | %0,153 | `funding_egilim` | 0,384 | hiçbiri |
| Çeyrek (0,25x) | %0,077 | `funding_egilim` | 0,433 | hiçbiri |
| **Sıfır (0,00x)** | **%0,000** | `funding_filtre` | **0,526** | **hiçbiri** |

**Maliyeti tamamen silmek Sharpe'a +0,24 katıyor.** Kapı 1,02. Maliyet bu uçurumun yarısını
bile kapatmıyor.

Gerçekçi bir maker senaryosu 0,25x–0,50x arasındadır (BNB indirimi + spread kazanmak).
Orada bile en iyi sonuç 0,43.

## 4. 4h — aynı sonuç

Maliyet sıfır, tüm kayıtlı stratejiler:

| Strateji | OOS Sharpe | OOS getiri | İşlem | Kalan kapılar |
| --- | ---: | ---: | ---: | --- |
| `ema_kesisim` | 0,691 | +%5,2 | 19 | oos_sharpe, wf_katman_basari, **asgari_islem** |
| `sma_kesisim` | 0,529 | +%4,1 | 18 | oos_sharpe, oos_is_orani, wf_katman_basari |
| `rsi_donus` | 0,240 | +%1,9 | 81 | oos_sharpe, oos_is_orani, wf_katman_basari |
| `cok_faktor` | −0,014 | −%0,2 | 238 | oos_sharpe, oos_is_orani |
| `donchian` | −0,084 | −%1,0 | 37 | oos_sharpe, oos_is_orani, wf_katman_basari |
| `al_tut` | −0,328 | −%4,4 | 0 | oos_sharpe, oos_is_orani, wf_katman_basari |
| `momentum` | −0,922 | −%8,0 | 75 | oos_sharpe, oos_is_orani, wf_katman_basari |

## 5. İki itiraz önden kapatıldı

**"Kapıyı K-044 ile yükselttin, tabii geçen olmaz."**

Eski, düzeltilmemiş **0,50** kapısına göre de geçen yok:

- `funding_filtre` (1h, 0x): 0,526 ile Sharpe kapısını geçiyor → `oos_is_orani` ve
  `wf_katman_basari`'da kalıyor.
- `ema_kesisim` (4h, 0x): 0,691 ile geçiyor → 19 işlemle `asgari_islem`'de kalıyor.

Kapılar bir **konjonksiyon**dur. Tek kapıyı geçmek promotion değildir ve hiçbir zaman
olmadı (K-019).

**"Kapı gerçek maliyetle ölçüldü; sıfır maliyetli sonuçla karşılaştırmak haksız."**

Tersi doğru. Sıfır maliyette **null stratejiler de** maliyet ödemez, yani K-044'ün
düzeltilmiş kapısı 1,02'nin **üstüne** çıkardı. Test stratejiler lehine cömert ve sonuç
yine de olumsuz. Yönü yanlış olan bir cömertlik değil bu — sonucu güçlendiriyor.

## 6. Karar

**Maliyet duvarı bağlayıcı kısıt değilmiş.** Dolayısıyla:

1. **Maker yürütme modeli yazılmayacak** — gerekçesi ortadan kalktı.
2. **Tek sembollü yönlü strateji araması kapanıyor** (K-045). BTC/USDT üzerinde klasik
   teknik göstergelerle yönlü tahmin, bu veri ve bu kapılarla tükendi; ve tükendiği
   **ölçüldü**, tahmin edilmedi.

**Yeni bir arama programı da açılmıyor** ve gerekçesi K-044'ün kendisi: her yeni çekiliş
kapıyı yükseltiyor. 31 çekilişte %5 sınırı 1,02; 60 çekilişte daha yüksek olacak. Büyük
bir yeni arama programı, bulduğunu geçirmek için kendi diktiği duvarı aşmak zorunda kalır.
Yeni bir kaynak ancak **marjinal değil belirgin** biçimde daha iyiyse açılmalı.

## 7. Ek ölçüm: funding carry de kapalı

Yönlü tahmin dışında tek yapısal (tahmin gerektirmeyen) aday funding carry'ydi — spot al +
perpetual short, fiyat yönünden bağımsız. Kendi 7 yıllık verimizle ölçüldü:

| Pencere | Yıllık brüt | Negatif ödeme oranı |
| --- | ---: | ---: |
| 7 yıl | %12,29 | 14,3% |
| 3 yıl | %7,65 | 14,7% |
| 2 yıl | %5,35 | 16,8% |
| **Son 1 yıl** | **%3,40** | **23,8%** |

Edge **sıkışmış**. Son 1 yıl oranıyla, iki bacaklı giriş-çıkış maliyeti düşüldükten sonra
net ~%2,8; ayda bir yeniden dengeleme gerekirse **negatif**. Mevduat faizinin altında,
üstüne borsa riski ve short bacağın likidasyon riski.

**Önerilmiyor.** Ama ölçüm kayıtlı: funding rejimi dönerse (7 yıllık ortalama %12,3 idi)
bu hesap saatler içinde tekrarlanabilir.

## 8. Bu bir başarısızlık kaydı değil

Sistem yanlış çalışmadı — **doğru çalıştığı için "burada bir şey yok" diyebildi.** 1102
test, look-ahead koruması, deterministik backtest, atlatılamayan risk motoru, çoklu test
düzeltmesi: bunların toplam işlevi, olmayan bir edge'i var göstermemekti.

Ölçülen alternatif maliyet somut: `ema_kesisim` ile canlıya geçilseydi OOS beklentisi
**−%4,2**'ydi. Aramanın durdurulması bir kayıp değil, o kaybın önlenmesi.

## 9. Ne korunuyor

**Kapanan:** tek sembollü yönlü arama, maker yürütme çalışması, dördüncü bir
parametre/aile çekilişi, funding carry.

**Korunan:** altyapının tamamı. Faz 6'nın 30 günlük koşusu devam ediyor — bedeli yok ve
altyapının ayakta kaldığının kanıtı olacak. Piyasa koşulları değişirse (funding rejimi
döner, komisyon yapısı değişir, yeni veri kaynağı erişilebilir olur) aynı altyapı
**saatler içinde** yeniden ölçüm yapabilir: `sq lab kapilar`, `sq lab coklu-test`,
hipotez defteri ve 38 çekilişlik geçmiş yerinde duruyor.

**Faz 8 kapanmıyor ve kapanamaz:** promotion'u geçen strateji olmadığı için kontrollü live
hiç başlamadı. Bu bir borç değil, kapının çalıştığının kanıtı (K-010).
