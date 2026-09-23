# Aktif demo — ortalamaya dönüş araştırması: ön kayıt (K-136)

Tarih: 2026-09-23 (UTC). Bu dosya **koşudan önce** commit'lenir; sonuçlar ayrı kayıtta
(`2026-09-23-aktif-donus-sonuc.json`) yazılır. Aşağıdaki ızgara, seçim kuralı ve geçme ölçütü
sonuç görüldükten sonra değiştirilmez.

## Neden bu aile

K-134/K-135 geriye bakışlarında maliyetsiz kârlı tek aile `rsi_donus` oldu (kripto 15m +%23,
MT5 1h +%61). İki hesapta da maliyet bu kârı yedi. Soru: daha seçici giriş (daha az işlem) ve
daha uzun zaman dilimi, brüt üstünlüğü maliyet sonrası pozitife taşıyor mu? Bu seçim o
geriye bakışlara **bakılarak** yapıldı; kanıt değeri bu yüzden yalnız OOS'tan gelir.

## Veri ve bölme

- **Kripto:** `config/aktif.json` `kripto-donus` sembolleri (10 büyük USDT paritesi; bugünkü
  listeden seçildi → hayatta kalma yanlılığı, iyimser yönde). Binance public 1h/4h, son 730 gün.
  Maliyet taraf başı 10 + 5 bps. Yalnız long (spot).
- **MT5:** `config/aktif.json` `mt5-demo` 11 sembolü, Integral demo terminal geçmişi, 1h/4h,
  son 730 gün (terminal ne verirse). Maliyet taraf başı 0,5 + 1,0 bps + bugünkü swap oranları.
  Long ve short.
- **Bölme:** her seride zamanın ilk %70'i IS, son %30'u OOS. OOS seçimden sonra **bir kez**
  okunur.
- Risk ayarı: hesapların `config/aktif.json` risk değerleri (kripto 0,3/1,0; MT5 2/6).

## Izgara (her piyasa için 36 aday)

`rsi_donus`: `n ∈ {2, 3, 5}` × `alt ∈ {5, 10, 15}` (`ust = 100 − alt`, `cikis = 50`) ×
`trend ∈ {100, 200}` × zaman dilimi `∈ {1h, 4h}`.

## Seçim kuralı (yalnız IS)

1. Aday IS'te haftada **≥ 5 işlem** yapmalı (Scryne'ın "sık işlem" hedefi).
2. Kalanlar arasında **IS haftalık Sharpe** en yüksek olan seçilir. Eşitlikte daha az işlem.
3. Hiçbir aday 1. şartı sağlamazsa o piyasa için seçim yok.

## Geçme ölçütü (seçilen aday, OOS, maliyet sonrası)

Hepsi birden: toplam getiri > 0 **ve** haftalık Sharpe ≥ 0,5 **ve** kârlı hafta oranı ≥ %50.

- **Geçerse:** aday yeni bir demo hesap olarak eklenir (mevcutlar değişmez).
- **Kalırsa:** yazılır; demoya eklenmez. OOS'a bakıp ızgarayı genişletmek bu kaydın dışındadır ve
  yeni ön kayıt ister.

Rapor ayrıca bütün adayların OOS dağılımını verir (seçimin şans olup olmadığını görmek için);
bu dağılım seçim için kullanılmaz.
