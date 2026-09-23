---
proje: ScryneQuant
faz: 16
tur: DESIGN (ölçüm yok, kod yok, çekiliş yok, karar açılmadı)
tarih: 2026-09-20
type: tasarım
durum: taslak — Scryne onayı bekliyor
---
# Hat 1 — İkinci tavan tasarımı: ideal carry tavanının gerçekçi koşullarda ne kadarı kalıyor?

**Soru:** Adım 0'ın ideal tavanı (BTC +%14,2/yıl, havuz Sharpe 6,6; K-078) gerçekçi
işlem maliyeti, marjin, fırsat maliyeti ve stres altında 1,04'ün üstünde kalıyor mu?

**Bu doküman ne değil:** ölçüm değil (hiçbir sayı üretilmedi), strateji değil, program
kaydı değil, kapsam değişikliği değil. Adım 0'daki 9,5 / 8,8 Sharpe **ekonomik edge olarak
okunmaz**; bu tasarım o sayının hangi katmanlarda ve neden eriyeceğini ölçülebilir kılar.

---

## 0. Repo denetimi — ikinci tavanın dayanabileceği ve dayanamayacağı şeyler

| Katman | Repoda var | Repoda yok | Çelişki |
| --- | --- | --- | --- |
| Funding | `data/funding.py` (ödeme olayı, `funding_time`/`funding_rate`, `BAYAT_MS`, `barlara_hizala`), 43 sembol IS+OOS | — | yok |
| Basis | `data/funding.py::evren_premium_dizisi` (premium index 1h `close`, NaN doldurulmaz), `data/turev/premium/` 484 sembol | mark price serisi (premium index ≠ mark; fark küçük ama ölçülmedi) | yok |
| Spot maliyet | K-007: her iki bacak **taker**, `fee_taker_bps` 10,0 (Spike 4, VIP 0, BNB indirimi yok); `slippage_bps` 5,30 (K-021, 1m fiyat hareketi proxy'si, p75); spread sayılmaz (Spike 4: 0,00128 bps) | — | yok |
| **Vadeli maliyet** | — | USDT-M taker/maker tarifesi, vadeli slippage kalibrasyonu, spread | Spike 4 yalnız spot ölçtü |
| Stres çerçevesi | `research/analiz.py::STRES_SENARYOLARI` (slippage 2×/3×, fee 2×, hepsi 2×; gerekçe K-021 dağılımı p95/p99); `stres_bozulma` kapısı ≤ 0,15 | funding/basis/likidasyon/erişim senaryosu | yok — genişletilir, değiştirilmez |
| Risk limitleri | `config/risk.json` (K-033): brüt maruziyet 1,0, tek enstrüman 0,3, DD 0,20, günlük zarar 0,02; her limit kaynaklı | kaldıraç, likidasyon mesafesi, bacak dengesizliği, marjin oranı | K-033 spot için yazıldı |
| Kill switch | K-008: pozisyon otomatik kapatılmaz — "spot'ta likidasyon yok, tutmak güvenli"; **"futures'a geçilirse yeniden verilmelidir"** | likidasyon-bilinçli davranış | **K-008 açıkça vadeli için geçersiz** |
| Mutabakat | K-046: üç taraflı (çıpa + defter + borsa bakiyesi), spot | ikinci bacak (perp pozisyon + funding defteri) | K-046 tek bacak |
| Portföy | K-057: `hedef.py` ağırlık ∈ [0,1], tek bacak | çift (spot + perp) hedef | K-057 tek bacak |
| Kapsam | Final-Doküman v2 §"Yok": **"kaldıraç ve kısa pozisyon, perpetual ile işlem (bilgi kaynağı olarak kalır)"**; K-048 tablosu aynı | — | **carry pozisyonu kapsam dışı** |
| K-045 | istisna: "ölçüyle gerekçelendirilmiş, belirgin biçimde farklı bilgi kaynağı" | — | carry yeni *bilgi* değil, yeni *getiri mekanizması*; K-045 lafzı bunu kapsamıyor → program açılırken yeni K-kaydı ister |
| K-053 | ilk genişleme kripto içinde | — | yok (carry kripto içi) |
| Türev metrikleri | `data/turev/metrics/` (OI, long/short oranları, 5 dk, 2020-09→) | — | yok; stres tanımında girdi olabilir |
| USDT getiri kıyası | — | hiçbir seri yok; FRED anahtarı hostta (K-066), `data/makro/` DGS10/T10Y2Y/NFCI/HY/DTWEX var, **DTB3 yok** | yok |
| Borsa kesintisi | Faz 6 `gozlem-2`: 1 gerçek WS kopması 18 s; Faz 14 host kesinti sayacı | borsa çapında kesinti/erişim kaybı/iflas tarihçesi | ölçülemez |

**Sonuç:** ikinci tavanın funding, basis, stres çerçevesi ve spot maliyet katmanları
repoya dayanıyor; vadeli maliyet, marjin, likidasyon ve USDT kıyası katmanları **veri ya da
karar** istiyor. Tasarım bu ayrımı her katmanda işaretler.

---

## 1. Funding katmanı

- Tanım **aynen**: `funding_rate_t` ödeme olayı; pozitif oran long'un short'a ödediği tutar.
  `r_funding,t = funding_rate_t` (short perp alır).
- **Ayrıştırma (raporlanır, tanımı değiştirmez):** taban bileşeni `0,0001` (Binance faiz
  bileşeni, `clamp(faiz − premium, ±0,05 %)`) ve talep bileşeni `funding_rate_t − 0,0001`.
  Adım 0 BTC'de tabanın payı %77. İkinci tavan iki bileşeni ayrı raporlar çünkü taban bir
  **borsa parametresidir** (§8 senaryo sınıfı), talep bileşeni piyasa.
- **Pozitif/negatif dönem yapısı:** ödeme dizisi ardışık aynı-işaretli **koşulara**
  bölünür; her koşu için başlangıç, uzunluk (ödeme), toplam ödeme, o koşudaki Δbasis.
  Rapor: sembol × yıl için negatif koşu sayısı, en uzun negatif koşu, en derin kümülatif
  negatif funding, negatif koşuların toplam süre payı. Bunlar §8'in "funding uzun süre
  negatif" senaryosunun **tarihsel parametre kaynağıdır** — parametre seçilmez, dağılım
  yazılır.
- Havuz: eşit ağırlık, o gün verisi olan semboller (Adım 0 ile aynı); PIT ilk 50 ve
  yalnız perp'i olanlar. Seçim yanlılığı notu: "perp'i olan ilk 50" bugünkü liste değil,
  2026-09 PIT tablosu — ama IS boyunca üyelik değişmiş sembollerin funding'i "o dönemde
  evrende miydi" kontrolü yapılmadı; ikinci tavanda PIT üyelik tablosuyla (`_evren/`)
  kesişim **raporlanır** (A).

## 2. Basis / premium katmanı

- Tanım **aynen**: `basis_t` = ödeme anında kapanan 1h premium barının `close`'u
  (`evren_premium_dizisi`); `r_basis,t = −(basis_t − basis_{t−1})`; NaN doldurulmaz,
  eşleşmeyen ödeme düşer (sayısı raporlanır).
- Yeni basis tanımı yok. Mark price serisi repoda olmadığı için "mark ≠ premium index"
  farkı **ölçülemez**; sınırlama olarak yazılır.
- Basis M2M'in gerçek maliyeti dengeleme sıklığında ortaya çıkar (§3); bu katman yalnız
  aleyhte basis hareketinin dağılımını (§8) üretir: pencere w ∈ {1, 7, 30} gün için en kötü
  kümülatif Δbasis, yıl bazında.

## 3. İşlem maliyeti katmanı

Pozisyon dört yürütmeden oluşur: spot alış (açılış), perp satış (açılış), perp alış
(kapanış), spot satış (kapanış). Ayrıca dengeleme: bacaklar arası notional farkı eşik
`δ`yi aşınca küçük bacak düzeltilir.

| Kalem | Kaynak | Durum |
| --- | --- | --- |
| Spot komisyon | K-007 `fee_taker_bps` = 10,0, iki yönde | **A** |
| Spot slippage | K-021 `slippage_bps` = 5,30 (BTC 1m p75); diğer semboller için kalibre edilmedi | A (BTC), B (diğerleri: `sq data slippage-kalibre` sembol başına) |
| **Perp komisyon** | repoda yok — Binance USDT-M tarifesi (VIP 0, maker/taker) | **B**: Spike 4 kalıbıyla tarife kaydı (`docs/arsiv/spikes/`), `config/maliyet.json`'a `fee_taker_bps_perp` alanı — **sayı bu dokümanda yazılmıyor** |
| Perp slippage | repoda yok; premium index 1h'den kalibre edilemez (1m perp kline yok) | **B**: perp 1m kline arşivi (`data.binance.vision futures/um`) — yeni veri **kararı**, bu dokümanda verilmiyor |
| Spread | Spike 4: spot'ta sayılmaz; perp için ölçülmedi | B (perp emir defteri yok) |
| Dengeleme sıklığı | tasarım parametresi `δ` — seçilmez; ızgara {%1, %2, %5} **duyarlılık** olarak raporlanır, tek değer seçilirse çekiliştir | A (δ verilince hesap deterministik: Δbasis ve fiyat yolundan bacak sapması) |
| Dönem başına maliyet | açılış+kapanış tek seferlik: `2·(fee_spot + slip_spot) + 2·(fee_perp + slip_perp)`; tutma süresi `H` gün → yıllık amortisman `/ (H/365)`; `H` parametre, ızgara {30, 90, 365} raporlanır | A (perp kalemleri gelince) |

**Maliyet-düzeltilmiş getiri:** `r_net,t = r_funding,t + r_basis,t − c_dengeleme,t`,
toplam kümülatiften açılış/kapanış maliyeti düşülür. Stres çarpanları §8.

Çelişki notu: K-007 "her iki bacak taker" kuralı perp bacağına da uygulanır; maker
varsayımı yapılmaz (K-045 §3 maker çalışmasını kapatmıştı — o karar spot yürütme
iyileştirmesi içindi, burada "varsayma" kuralı olarak taşınır).

## 4. Marjin katmanı

- Pozisyon tanımı **aynen**: eşit notional `N` spot long + `N` perp short.
- **Sermaye kullanımı:** spot bacak `N` (tam ödeme). Perp bacak başlangıç marjini
  `m·N`, `m = 1/L`; `L` **kaldıraç, tasarım parametresi — seçilmez.** Ölçüm `L ∈ {1, 2, 3,
  5}` için tablo üretir; tek `L` seçmek ayrı bir karardır (K-033'e yeni limit).
- **İki getiri ayrı raporlanır:**
  - pozisyon getirisi: `r_pos = PnL / N` (Adım 0 böyle),
  - **sermaye getirisi:** `r_cap = PnL / (N + m·N + b·N)`; `b` = likidasyon tamponu
    (§5) — parametre.
  Sharpe kaldıraçtan bağımsız olduğu için `r_cap` esas olarak **getiri düzeyini**
  (fırsat maliyeti kıyası §7 için) değiştirir; DD ve likidasyon mesafesi ise `L`ye bağlıdır.
- **Marjin tipi** (isolated / cross / portföy marjini; spot BTC'nin perp teminatı sayılıp
  sayılmayacağı) — borsa kuralı, repoda yok → **C** (karar) ve **B** (kural kaydı).
  Tasarım her ikisini ayrı senaryo olarak tutar: (i) ayrı hesaplar, spot teminat
  **sayılmaz** (muhafazakâr, K-007 ruhu); (ii) portföy marjini (teminat sayılır). Varsayılan
  raporlama (i); (ii) yalnız kural kaydı gelirse.
- **Bacak dengesizliği:** fiyat `p` yükselince spot bacak `N·(p/p₀)`, perp bacak
  `−N·(p/p₀)`: notional dengesi korunur ama perp marjin oranı düşer (§5). Basis değişimi
  iki bacağın değerini farklı hareket ettirir; `δ` eşiği §3.

## 5. Likidasyon katmanı

- **Normal PnL ile ayrım:** §1–4 pozisyonun sürekli PnL'ini verir; likidasyon, perp
  bacağının **tek taraflı ve kalıcı** kapanmasıdır — sonrasında pozisyon delta-nötr değil,
  long spot'tur ve carry biter. Ölçümde likidasyon bir PnL kalemi değil, **olay sayacıdır**:
  "bu `L` ve tamponla IS'te kaç kez likide olurdu".
- Short perp likidasyon koşulu (isolated): marjin oranı bakım marjin oranının (`mmr`)
  altına düştüğünde; yaklaşık likidasyon fiyatı `p_liq ≈ p₀ · (1 + 1/L − mmr)`. Fiyat
  yolu `p` **mark price**; repoda mark serisi yok, 1h `close` + premium yaklaşımı yapılabilir
  ama bu **yaklaşık model uydurma** olur.
- **Bağlı olduğu kurallar:** Binance USDT-M kademeli bakım marjin tablosu (sembol ve
  notional kademesine göre `mmr`), isolated/cross, otomatik marjin ekleme, ADL. Hiçbiri
  repoda yok.
- **Durum: DATA BLOCKED.** Likidasyon **sayacı** ancak (a) `mmr` kademe tablosu kaydedilir
  (Spike kalıbı, `docs/arsiv/spikes/`, tarih + kaynak URL), (b) mark ≈ close·(1+premium)
  yaklaşımının hatası ölçülür ya da mark kline arşivi eklenir (veri kararı) — ikisi de
  gelene kadar üretilmez.
- **Bugün ölçülebilen tek girdi (A):** 1h `high`'dan, tutma penceresi içinde girişe göre
  **azami yukarı hareket** dağılımı (`MFE` benzeri; `jev/sonuc.py` ile aynı tanım) — sembol ×
  yıl. Bu, `L` seçilmeden "hangi `L`de kaç kez `1/L − mmr` aşılırdı" tablosunun fiyat
  tarafıdır; `mmr` gelince tablo tamamlanır.
- Stres modeli (§8) burada yalnız **tasarlanır**: likidasyon eşiğine yaklaşma = marjin
  oranının `mmr + tampon` altına inme sayısı; tampon parametre.

## 6. Borsa / karşı taraf riski

- Keyfi Sharpe cezası **yok.** Risk, önceden tanımlı **senaryo sınıfları** olarak tutulur;
  her senaryo pozisyona uygulanır ve sonucu ayrı satırda raporlanır.
- Sınıflar: (a) erişim kaybı `D` gün (pozisyon açık, dengeleme yok, funding birikir, çıkış
  yok); (b) tek bacak erişim kaybı (spot erişilir, perp erişilmez → delta açılır); (c)
  borsa parametre değişikliği (faiz bileşeni `0,0001` → `0`; funding aralığı 8h → 4h);
  (d) borsa iflası/çekim durması (sermayenin `x` payı kaybı).
- **Parametre kaynakları:** (a)–(b) için repoda yalnız kendi kesintilerimiz var (`gozlem-2`
  WS kopması 18 s; Faz 14 kesinti sayacı) — bunlar bağlantı, borsa değil; borsa çapında
  kesinti tarihçesi repoda **yok → ölçülemez**, `D` parametre olarak açık bırakılır ve
  sonuç `D ∈ {1, 3, 7}` gün için **duyarlılık** olarak verilir. (c) deterministik ve
  ölçülebilir (funding dizisinden taban çıkarılır) — **A**. (d) tarihsel veri yok (borsa
  iflası dağılımı) → **ölçülemez**; `x` seçilmez; rapor "x için başabaş yıl" tablosu verir
  (kaç yıllık net carry `x`'i telafi eder) — bu bir ceza değil, bir dönüşüm.

## 7. USDT alternatif getirisi (fırsat maliyeti)

- **Amaç:** carry'nin brüt funding getirisi ile "aynı USDT'yi risksize yakın bir yere
  koymak" arasındaki farkı ayrı tutmak. İki satır: `r_gross` (§3 sonrası) ve
  `r_excess = r_gross − r_benchmark`.
- **Benchmark adayları ve durumları:**
  1. Binance funding faiz bileşeni tabanı (`0,0001`/8h = %10,95/yıl): repoda **var**, ama
     carry'nin kendi bileşeni — benchmark olarak döngüseldir; yalnız "talep bileşeni tek
     başına" satırı olarak raporlanır (A).
  2. ABD 3 aylık hazine bonosu (FRED `DTB3`), günlük, IS 2020–2025: repoda **yok**;
     mevcut FRED hattıyla (`data/makro/`, K-060 PIT kuralı: ertesi gün görünürlük) indirilebilir
     — **B, veri ekleme kararı** (bu doküman vermiyor). USDT ≠ USD (depeg riski) notu düşülür.
  3. Binance Earn / stablecoin borç verme oranı tarihçesi: arşiv yok → **ölçülemez**.
  4. DeFi stablecoin oranları (Aave USDT): repoda yok, on-chain veri kararı → dışarıda.
- **Tasarım kararı (onaya tabi):** benchmark = `DTB3` (2); yoksa fırsat maliyeti satırı
  **DATA BLOCKED** kalır ve ikinci tavan yalnız maliyet-düzeltilmiş aşamaya kadar
  raporlanır. Dışarıdan sayı yazılmaz.
- Sermaye tabanı §4'teki `r_cap`; fırsat maliyeti sermayenin tamamına (`N(1+m+b)`) uygulanır,
  yalnız spot bacağa değil.

## 8. Stres senaryoları — sınıflar ve parametre kaynakları (parametre seçilmedi)

| Sınıf | Uygulama | Parametre kaynağı | Durum |
| --- | --- | --- | --- |
| Funding uzun süre negatif | IS'teki gerçek negatif koşular (§1) + sentetik: en uzun koşu ×k / en derin koşu ×k | tarihsel koşu dağılımı (A); `k` ızgara {1, 2} duyarlılık | A |
| Basis aleyhte hareket | w-gün en kötü kümülatif Δbasis (§2), dengeleme maliyetiyle | premium verisi | A |
| Yüksek volatilite | 1h realize vol üst dilimindeki günler alt-örneği; o günlerde Δbasis, MFE, dengeleme sayısı | `research/rejim.py` **kullanılmaz** (rejim tanımı yok); dilim = IS vol persentili, parametre değil sıralama | A (persentil eşiği ızgara {90, 95, 99} duyarlılık) |
| Likidasyon eşiğine yaklaşma | marjin oranı < `mmr + tampon` sayısı, `L` ızgarası | `mmr` tablosu (B), mark yaklaşımı (B) | **DATA BLOCKED** |
| Execution maliyeti yükselmesi | `STRES_SENARYOLARI` çarpanları aynen (slippage 2×/3×, fee 2×, hepsi 2×) perp kalemlerine de | `research/analiz.py` (K-021 gerekçesi) | A (perp kalemi gelince) |
| Borsa parametre değişikliği | taban `0,0001 → 0`; aralık 8h→4h (ödeme sayısı 1,5×, oran aynı) | funding dizisi | A |
| Erişim kaybı / karşı taraf | §6 (a)–(d) | ölçülemez; `D`, `x` ızgara | duyarlılık |

Senaryoların **hiçbiri** Sharpe'a çarpan olarak girmez; her biri ayrı satırda "bu senaryoda
yıllık net getiri / DD / ilgili sayaç" verir. Mevcut `stres_bozulma` kapısı (temel − en kötü
senaryo getiri farkı ≤ 0,15) **aynen** uygulanır; senaryo kümesi genişler, kapı değişmez.

## 9. Ölçüm sırası — tek sayı değil, dört aşama

```
(1) İdeal tavan            Adım 0 — maliyet 0, marjin 0, likidasyon 0     [ölçüldü]
        ↓  −açılış/kapanış/dengeleme maliyeti, taker, stres çarpanı yok
(2) Maliyet-düzeltilmiş    r_gross; H ve δ ızgarası; L ızgarası ile r_cap
        ↓  −benchmark (DTB3 ya da DATA BLOCKED)
(3) Fırsat-maliyetli       r_excess; Sharpe yalnız excess üstünden
        ↓  senaryolar tek tek
(4) Stres tavanı           her sınıf ayrı satır; stres_bozulma; likidasyon sayacı (blocked)
```

**Neden ayrı:** (1)→(2) farkı yürütmenin payını, (2)→(3) sermayenin payını, (3)→(4)
kuyruğun payını gösterir. Tek sayıda birleştirilirse hangi katmanın öldürdüğü görünmez
ve K-045'in "duvar neredeydi" sorusu cevapsız kalır. Ayrıca (3) DATA BLOCKED kalabilir;
o zaman (2) ve (4) yine raporlanır ve karar "eksik katman" ile verilir.

## 10. Başarı / kapanış kuralı (önceden yazılır, 1,04 değişmez)

| Aşama (3) sonucu — havuz **ve** BTC tek başına | Karar |
| --- | --- |
| excess Sharpe < 1,04 **veya** `r_excess` yıllık ≤ 0 | **CLOSE** |
| excess Sharpe ≥ 1,04 ve DD ≤ %25 ve `stres_bozulma` ≤ 0,15 (ölçülebilen senaryolarda) | **ELIGIBLE** — sonraki adım program kaydı + mimari karar; **promotion kanıtı değil** |
| (3) benchmark yok ya da (4) likidasyon sayacı blocked | **DATA BLOCKED** — (2) raporlanır, karar verilmez |

Sharpe'ın carry için kuyruğu görmediği (K-078/3) bu kuralda kabul: ELIGIBLE, "riskli değil"
demez; "bir sonraki ölçüm bedelini hak ediyor" der. İkinci tavan da hindsight içerir
(IS'te her zaman açık pozisyon, `L`/`δ`/`H` ızgarasının en iyisi raporlanmaz, tablo
verilir).

---

## A) Mevcut veriyle doğrudan ölçülebilecekler

1. Funding koşu yapısı (pozitif/negatif koşular, uzunluk, derinlik) sembol × yıl (§1).
2. Taban/talep bileşeni ayrıştırması; "taban 0" senaryosu; "aralık 4h" senaryosu (§1, §8).
3. Basis aleyhte hareket dağılımı w ∈ {1, 7, 30} gün (§2).
4. Yüksek vol alt-örneği (1h realize vol persentili; rejim tanımı değil) ve o günlerde
   Δbasis/MFE (§8).
5. Fiyat tarafı likidasyon girdisi: tutma penceresi içinde azami yukarı hareket (1h `high`)
   dağılımı (§5) — `mmr` olmadan sayaç üretmez.
6. Spot bacak maliyeti (K-007/K-021) ve dengeleme maliyeti `δ` ızgarasıyla (§3, perp
   kalemi hariç).
7. PIT üyelik kesişimi (sembol o dönemde evrende miydi) — seçim yanlılığı notu (§1).
8. `r_cap` tablosu `L` ızgarası için, likidasyon **hariç** (§4).

## B) Veri / model gerektirenler (karar bu dokümanda verilmiyor)

1. Binance USDT-M komisyon tarifesi kaydı (Spike 4 kalıbı) → `fee_taker_bps_perp`.
2. Perp 1m kline arşivi → perp slippage kalibrasyonu (`sq data slippage-kalibre` kalıbı).
3. Bakım marjin kademe tablosu (`mmr`) kaydı + marjin tipi kuralları → likidasyon sayacı.
4. Mark price serisi ya da mark ≈ close·(1+premium) yaklaşımının hata ölçümü.
5. FRED `DTB3` (mevcut FRED hattı, K-060 PIT kuralı) → fırsat maliyeti benchmark'ı.
6. Diğer semboller için spot slippage kalibrasyonu (1m verisi yalnız BTC'de).
7. Borsa çapında kesinti/erişim kaybı tarihçesi → yok; `D` parametre kalır.

## C) Karar kaydı açılmadan yapılamayacaklar

1. **Tek bir `L` (kaldıraç) seçmek** — K-033'e yeni limit; ölçüm ızgara verir, seçmez.
2. **Marjin tipi** (isolated/cross/portföy marjini; spot teminat sayılır mı).
3. **Carry pozisyonunun kapsama girmesi** — Final-Doküman v2 "Yok" tablosu ve K-048:
   kaldıraç/kısa pozisyon/perp ile işlem kapsam dışı; K-045 istisnasının lafzı ("bilgi
   kaynağı") carry'yi kapsamıyor → yeni K-kaydı.
4. **K-008** — vadeli için kill switch davranışı yeniden ("tutmak güvenli" varsayımı
   likidasyonla geçersiz).
5. **K-046** — iki bacaklı mutabakat (spot + perp + funding defteri).
6. **K-057** — çift bacaklı hedef sözleşmesi (`hedef.py` ağırlık ∈ [0,1] tek bacak).
7. **K-033** — kaldıraç, likidasyon mesafesi, bacak dengesizliği limitleri.
8. **Program kaydı (K-051)** — ikinci tavan ELIGIBLE derse; bütçe, durma kuralı, eşik
   tahmini.
9. Yeni veri ekleme kararları (B-2, B-4, B-5) — Final-Doküman "Bütçeler" kalemi.

Hiçbiri bu dokümanla açılmadı. Sonraki adım: A listesinin ölçümü için onay (tek betik,
`tools/`, ölçüm; B-1/B-3/B-5 kayıtları ayrı spike kararı; C listesi ancak ELIGIBLE sonrası).
