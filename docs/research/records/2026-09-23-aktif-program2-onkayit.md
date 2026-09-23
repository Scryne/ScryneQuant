# Aktif demo — Program 2: literatürde belgelenmiş etkiler, ön kayıt (K-137)

Tarih: 2026-09-23 (UTC). **Koşudan önce commit'lenir.** Sonuç
`docs/research/records/2026-09-23-aktif-program2-sonuc.json`. Aşağıdaki tanımlar, maliyetler, testler ve
karar kuralı sonuç görüldükten sonra değiştirilmez; değişiklik yeni ön kayıt ister.

## Neden yeni program

Program 1 (K-136) teknik gösterge parametresi taradı; OOS'ta kaldı. Profesyonel yol: ekonomik
gerekçesi olan ve hakemli literatürde belgelenmiş etkileri **literatürdeki tanımıyla, parametre
aramadan** test etmek. Parametre aranmadığı için tüm örneklem test örneklemidir; çoklu test yalnız
hipotez sayısı üzerinden düzeltilir (Holm).

## Hipotezler (k = 4)

Zamanlar New York saatiyle (DST dahil, `America/New_York`). MT5 sunucu saati sabit UTC+3 (ölçüldü:
S&P günlük arası yaz 00:00, kış 01:00 sunucu saati = 17:00 ET). Bar zamanı açılış; karar bar
kapanışında, pozisyon sonraki barın açılışından itibaren (K-004).

- **A1 — Gece getirisi** (Cliff, Cooper & Gulen 2008; Lou, Polk & Skouras 2019): ABD hisse endeksi
  getirisinin büyük kısmı seans dışında oluşur. Kural: her işlem günü **16:00 ET'de long gir, 09:00
  ET'de çık** (hafta sonu Cuma 16:00 → Pazartesi 09:00 dahil). Semboller S&P, NASDAQ, DJI.
- **A2 — Gün içi momentum** (Gao, Han, Li & Zhou 2018, JFE): günün ilk getirisi son getiriyi
  öngörür. Kural: sinyal = önceki gün 16:00 ET → bugün 10:00 ET getirisi; **15:00-16:00 ET barında
  sinyalin işaretiyle pozisyon** (long ya da short). Semboller S&P, NASDAQ, DJI.
- **A3 — Ay dönümü** (Ariel 1987; Lakonishok & Smidt 1988; McConnell & Xu 2008): Kural: ayın son
  işlem gününün kapanışında long gir, yeni ayın **3. işlem gününün kapanışında** çık. Günlük bar
  (MT5 D1; kapanış ≈ 17:00 ET). Semboller S&P, NASDAQ, DJI.
- **B1 — Zaman serisi momentumu** (Moskowitz, Ooi & Pedersen 2012; Hurst, Ooi & Pedersen 2017):
  Kural: her sembolde işaret = son 252 işlem günü getirisinin işareti; boyut = yıllık %10 hedef
  oynaklık / 60 günlük gerçekleşen oynaklık, sembol başına kaldıraç ≤ 3; **haftalık** yeniden
  dengeleme (haftanın ilk işlem günü açılışı). Semboller `mt5-demo`nun 11'i, günlük bar.

Kripto bu programda yok: eski programlar kripto zaman serisi trendini (h63) ve seans çapası etkisini
(M-1) zaten test edip kaldı; tekrar denemek K-039 kuralını deler.

## Veri

- MT5 Integral demo terminali: A1, A2 için H1 (gerçek saatlik veri 2021-03'ten beri; öncesi günlük
  bar kılığında → **2021-04-01 öncesi dışlanır**); A3, B1 için D1 (endeksler 2014-08, altın 2001-12,
  pariteler 1990). Koşu anında çekilir ve sonuç dosyasına dönem + bar sayısı yazılır.
- **Bağımsız referans (yalnız A1, A3):** Yahoo Finance günlük SPY (1993→), QQQ (1999→), DIA (1998→);
  A1 için gece getirisi = açılış / önceki kapanış (temettü ex-tarihinde temettü geri eklenir).
  Referans etkinin **var olup olmadığını** uzun geçmişte gösterir; karar MT5 sonucuna göredir.

## Maliyet (K-007: kötü yöne)

Taraf başı: ölçülen spread'in yarısı (2026-09-23) + 0,5 bps komisyon (doğrulanmadı) + 0,5 bps ek kayma.
S&P 1,0 · NASDAQ 0,8 · DJI 1,1 bps; pariteler/altın kendi spread'lerinden. B1'de gecelik swap bugünkü
oranlarla bütün geçmişe uygulanır (geçmiş swap bilinmiyor; yaklaşıklık sonuçta işaretlenir).
Referans (Yahoo) testleri maliyetsizdir (yalnız etkinin varlığı).

## Test

- Her hipotez için günlük **net** getiri serisi; semboller eşit ağırlıklı (A: her endeks 1/3 notional ×
  1 kaldıraç; B1: hedef oynaklık ağırlıkları / 11).
- İstatistik: günlük ortalama net getiri > 0, Newey-West (5 gecikme) t, tek yönlü p.
- **Çoklu test:** Holm-Bonferroni, k = 4, aile α = 0,05.

## Karar kuralı (hepsi birden → PASS)

1. Holm düzeltmesinden sonra anlamlı.
2. Örneklemin iki yarısında da net ortalama > 0.
3. A hipotezlerinde 3 endeksin en az 2'si tek başına net pozitif; B1'de sembollerin en az yarısı.

**PASS** → hipotez tam bu tanımla yeni bir demo hesap olur (mevcut hesaplar değişmez). **FAIL** → yazılır,
demoya eklenmez. Güç notu: A1/A2'nin saatlik örneklemi ~5,5 yıl (~1.380 gün); günlük oynaklık ~%1 iken
günde ~2 bps'lik bir etki t ≈ 1'de kalır. FAIL "etki yok" değil, "bu örneklemle gösterilemedi" de olabilir;
Yahoo referansı bu ayrımı yorumlamak için raporlanır, kararı değiştirmez.
