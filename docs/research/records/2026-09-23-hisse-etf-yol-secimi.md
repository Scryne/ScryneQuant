---
proje: ScryneQuant
tarih: 2026-09-23
tur: kaynak/erişim araştırması (kod yok, çekiliş yok)
type: rapor
---
# Hisse/ETF endeks trendi: broker ve veri kaynağı seçimi

**Neden bu yol:** kriptoda üç aday yol kapandı (yalnız-long fiyat, carry, long/short; K-110, K-116,
K-123). Yalnız-long trend takibinin en uzun ve en çok belgelenmiş kanıtı hisse, tahvil ve emtia
endekslerinde; ETF verisiyle 20 yıla yakın geçmiş var, bu da OOS'u uzatıyor ve kapıların gücünü
artırıyor (K-119).

## 1. Broker (Türkiye'de oturan bireysel hesap, API ile otomatik emir)

| Seçenek | Türkiye'den erişim | API | Notlar |
| --- | --- | --- | --- |
| **Interactive Brokers (IBKR Pro)** | Evet (bağımsız rehberler 2026 itibarıyla uygun gösteriyor) | TWS/IB Gateway API, Client Portal Web API; **paper hesap** var | API ve paper erişimi için canlı IBKR Pro hesabının **açık ve fonlanmış** olması gerekiyor. Asgari tutarla ilgili kaynaklar çelişkili: "asgari yatırım yok" (QuantConnect) ve "özel bağlantılar için 10.000 USD ön yatırım" (arama özeti). **Hesap açılışında doğrulanmalı.** IBKR sayfaları bu makineden 403 veriyor. |
| Alpaca | Doğrudan bireysel hesap belirsiz; Türkiye'de Global Menkul Değerler ortaklığıyla (B2B) | REST API, ücretsiz paper | Bireysel uygunluk için destek e-postası gerekiyor; sayfada liste yok. |
| Türk aracı kurumlar (OYAK, İnfo, QNB, Garanti BBVA…) | Evet | Yurt dışı işlemde genel API yok; algoritmik işlem çoğunlukla BIST içi | Otomatik emir yolu için uygun değil. |

**Öneri:** IBKR. Tek gerçek seçenek bu, ama fonlama şartı senin K-122 kuralınla çakışıyor ("hazır olmadan para yok").
Çözüm sırası: araştırma ve backtest broker'sız yapılır (§2 verisiyle); broker hesabı ancak araştırma bir
aday çıkarırsa açılır. O zaman bile ilk adım **paper** hesaptır: fonlama gerçek emir değildir, gösterim
dönemi (K-122) paper'da koşar.

## 2. Tarihsel veri (araştırma için; otomasyona açık, lisansı depolamaya izin veren)

| Kaynak | Durum | Karar |
| --- | --- | --- |
| Stooq | Sembol başı CSV ucu artık JavaScript bot koruması arkasında (2026-09-23 ölçüldü: HTML döndü) | **Elendi** (otomasyon kapalı; HistData/Dukascopy kuralı) |
| Alpha Vantage | Ücretsiz katman son 100 gün; tam geçmiş `outputsize=full` yalnız ücretli (49,99 USD/ay) | Pahalı ve gereksiz |
| **EODHD** (EOD All World) | 19,99 €/ay, kişisel kullanım; abonelik süresince yerel depolama serbest, bitişten sonra 1 ay içinde silinmeli; REST API | **Önerilen** — araştırma için 1 ay yeter |
| Norgate Data | Hayatta kalma yanlılığından arındırılmış (delist dahil), Windows uygulaması + Python paketi; 21 günlük deneme yalnız 2 yıl veri | Hisse seçim stratejisi için ideal; ETF trendi için gereksiz |
| AQR TSMOM veri seti (ücretsiz, aylık faktör getirisi) | Bu makineden `aqr.com` çözülemiyor (DNS zaman aşımı) | Ön kontrol olarak faydalı ama şart değil |

**Depolama kuralıyla uyum (K-009):** EODHD verisi abonelik bitince silinmeli. Deney kayıtları veri hash'ini taşır;
yeniden üretim abonelik sürerken yapılır, ya da gerektiğinde yeniden indirilir (aynı bayt → aynı hash kontrolü).
Tiingo'nun kalıcı depolama yasağı gibi bu da K-088 kalıbında kayda geçer.

## 3. Gerçekçi beklenti (sonucu görmeden)

- Yalnız-long ETF trend takibinin literatürdeki ana faydası **düşüş azaltma**. Getiri çoğu dönemde al-tut
  düzeyinde ya da biraz altında. Risk-ayarlı getiri iyileşmesi orta düzeyde.
- `oos_sharpe` eşiği (1,04) kripto null'unda, 1,6-2,7 yıllık OOS'ta kalibre edildi. ETF'lerde OOS çok daha uzun
  olacak (~6 yıl) ve eşik o verinin kendi null'unda **yeniden ölçülmeli**: uzun OOS'ta null dar, eşik düşük çıkar.
  Bu bir gevşetme değil, doğru istatistik (K-044 yöntemi).
- Dürüst olasılık: klasik ETF trendi kapıları geçemeyebilir. Geçemezse de sonuç doğrudur; bu yol "garanti kazanç"
  değil, doğru ölçülmüş bir deneme.

## 4. Gerekli geliştirme (broker'sız, araştırma aşaması)

1. EODHD → `data/etf/` yükleyicisi (K-060/K-088 kalıbı: ham dosya SHA-256, PIT, kalite bayrağı).
2. ABD seans takvimi (R4 takvim altyapısı var: `common/takvim`), günlük bar; temettü/bölünme düzeltmesi.
3. Maliyet modeli: IBKR hisse başı komisyon + kayma (tutucu; public tarifeden, ×2 stres).
4. `ZamanSerisiTrend` ETF evreninde (kod var); kıyas: eşit ağırlık al-tut.
5. ETF null'uyla çoklu test eşiği; program kaydı (K-051) ve ön kayıtlı hipotez.

Kaynaklar: [BrokerChooser — Türkiye algo broker](https://brokerchooser.com/best-brokers/best-brokers-for-algo-trading-in-turkey),
[TradersUnion — IBKR Türkiye](https://tradersunion.com/brokers/forex/view/interactive_brokers/is-regulated-in-turkey/),
[IBKR paper hesap](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/),
[IBKR Web API](https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-trading/),
[QuantConnect — IBKR gereksinimleri](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/interactive-brokers),
[Alpaca ülkeler](https://alpaca.markets/support/countries-alpaca-is-available),
[Alpaca–GMD](https://www.fintechfutures.com/partnerships/brokerage-platform-alpaca-plots-asian-expansion-with-sbi-partnership),
[EODHD fiyatlar](https://eodhd.com/pricing), [EODHD şartlar](https://eodhd.com/financial-apis/terms-conditions),
[Alpha Vantage belgeleri](https://www.alphavantage.co/documentation/), [Norgate](https://norgatedata.com/),
[AQR TSMOM veri seti](https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Factors-Monthly).
