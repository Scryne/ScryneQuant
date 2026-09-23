---
proje: ScryneQuant
faz: 16
tur: DESIGN — üç veri/model spike'ı (B-1, B-3, B-5); ölçüm yok, indirme yok, kod yok, karar yok
tarih: 2026-09-20
type: tasarım
durum: taslak — Scryne onayı bekliyor
---
# Hat 1 — B listesi veri/model spike tasarımı: B-1 perp maliyet · B-3 marjin/likidasyon · B-5 USDT benchmark

**Amaç:** ikinci tavanın DATA BLOCKED üç katmanını ölçülebilir kılmak için hangi verinin,
hangi kapsamda, hangi mekanizmayla gerektiğini ve hangi noktaların **veri kararı** ya da
**K-kaydı** istediğini ayırmak. Hiçbir sayı dışarıdan yazılmadı; "Binance ücreti şu kadar"
türü varsayım yok. Bu doküman veri indirmez, karar açmaz.

Ortak repo denetimi (bu turda doğrulandı):

| Bileşen | Var | Yok |
| --- | --- | --- |
| Arşiv indirici | `exchange/binance_arsiv.py` (`HttpArsiv.listele/indir`, `.CHECKSUM` doğrulama, IPv4), `tools/faz12_premium_indir.py` ve `tools/faz16_metrics_indir.py` aynı kalıpla `futures/um/...` altından iniyor; her dosyanın SHA-256'sı `<S>.kaynak.json`'a yazılıyor (K-009/K-056) | vadeli **klines / markPriceKlines / bookTicker** için araç |
| Vadeli REST | `exchange/turev_rest.py` (`fapi`: `fundingRate`, `fundingInfo`, `premiumIndexKlines`; arşivle bit düzeyi eşitlik ölçülmüş) | `leverageBracket`, `commissionRate`, `exchangeInfo` (vadeli) çağrısı; vadeli yetkili anahtar (K-066: anahtar salt okunur, spot) |
| Maliyet modeli | `config/maliyet.json` + `common/maliyet.py` (taker iki bacak, slippage aleyhte, kalibrasyon bloğu, K-007/K-021), `sq data slippage-kalibre` (1m bar-to-bar p75) | perp alanları |
| Stres | `research/analiz.py::STRES_SENARYOLARI` (slippage 2×/3×, fee 2×) | — |
| FRED hattı | `tools/faz12_makro_indir.py` (ALFRED vintage, yıl parçalı, SHA'lı), `data/makro.py` (PIT kuralı K-060; `SERILER = {vix, nfci}`), 6 seri indirilmiş (VIXCLS, DGS10, T10Y2Y, DTWEXBGS, NFCI, BAMLH0A0HYM2) | **DTB3** |
| Marjin/likidasyon tanımı | — | hiçbir tanım yok; K-008 "futures'a geçilirse yeniden verilmeli"; Final-Doküman v2 "perp ile işlem yok" |

---

## B-1 — Perp komisyon / slippage

### Mevcut durum
- Perp işlem verisi (kline, trade, order book): **yok.** `data/turev/` altında yalnız
  funding, premium index (1h) ve günlük `metrics` (OI, long/short oranları) var.
- Fee schedule: **yok.** Spike 4 yalnız spot VIP 0 ölçtü (`fee_taker_bps` 10,0, BNB
  indirimi yok, maker kullanılmıyor). Vadeli tarifeye dair repoda tek satır yok.
- Tarihsel fee: **yok** ve dış dünyada da arşivlenmiş bir seri olarak yok (tarife
  sayfası anlık; kademe/VIP değişimleri geriye dönük kayıtlı değil).
- 1m perp fiyat / mark / order book: **yok.** Premium index 1h var; premium 1m arşivi
  ve perp 1m `klines` arşivi indirilmedi.
- Spot modelinden **taşınabilenler:** (i) "her iki bacak taker, maker varsayılmaz" kuralı
  (K-007); (ii) slippage kalibrasyon yöntemi — 1m bar-to-bar |Δclose| dağılımının p75'i
  (K-021), aynı araç `--depo` ile perp deposuna çevrilebilir; (iii) `kalibrasyon` bloğu
  şeması (yöntem, persentil, veri SHA, dağılım, tarih, gerekçe); (iv) stres çarpanları;
  (v) "belirsizlikte aleyhte yuvarla" (K-007).

### Eksik veri
1. USDT-M perpetual komisyon tarifesi (taker, maker; VIP 0; BNB indirimi var/yok).
2. Perp 1m `klines` (slippage kalibrasyonu için) — IS penceresi.
3. Perp emir defteri / `bookTicker` (spread) — Spike 4'ün "spread sayılmaz" bulgusu spot
   BTC içindi; perp'te ölçülmedi.

### Gerekli veri ve kaynak
| Veri | Kaynak | Mekanizma | PIT durumu |
| --- | --- | --- | --- |
| Tarife | Binance ücret sayfası (herkese açık) **veya** `GET /fapi/v1/commissionRate` (imzalı; vadeli yetkili anahtar ister — bugün yok, K-066) | Spike 4 kalıbı: tarih + kaynak URL + ekran/yanıt hash'i `docs/arsiv/spikes/` altına; `config/maliyet.json`'a `fee_taker_bps_perp` (+ `fee_maker_bps_perp`, kullanılmaz) | anlık; IS boyunca sabit **varsayımı** açıkça yazılır (tarihsel tarife serisi olmadığı için sapmanın yönü ve büyüklüğü bilinmiyor — belirsizlik beyanı, ölçüm değil) |
| Perp 1m klines | `data.binance.vision` `data/futures/um/monthly/klines/<S>/1m/` (herkese açık; mevcut `HttpArsiv` + `.CHECKSUM`) | `faz12_premium_indir.py` kalıbında yeni araç; `data/turev/klines_1m/` (REST deposuyla karışmaz, K-056/1) | tarihsel, tam |
| bookTicker | `futures/um/daily/bookTicker/<S>/` — arşivde **var olup olmadığı spike'ta listelenir**, burada varsayılmıyor | varsa aynı indirici | tarihsel |

### Minimum veri kapsamı
- Tarife: tek kayıt (bugün), VIP 0, BNB indirimsiz.
- Perp 1m klines: **BTCUSDT + ETHUSDT**, IS (2020-01 → 2025-02); kalibrasyon spot'ta da
  yalnız BTC'de yapıldı (K-021), perp'te iki sembol yeterli ve altcoinlere **taşınmaz**
  (taşımak yeni varsayım). Mertebe: 2 sembol × 62 ay zip.
- bookTicker: varsa aynı iki sembol, örneklem (IS'ten 12 ay).

### Ölçüm formülü için gerekli girdiler
`c_perp_tek_yon = fee_taker_bps_perp + slippage_bps_perp`; pozisyon açılış/kapanış toplam
`= 2·(fee_spot + slip_spot) + 2·(fee_perp + slip_perp)`; amortisman `H` ızgarası; stres
çarpanları `STRES_SENARYOLARI` perp kalemlerine de aynen. Spread perp'te ölçülürse ve
Spike 4 gibi ihmal edilebilir çıkmazsa `slippage_bps_perp`e **eklenmez**, ayrı alan olur
(K-007'nin "spread slippage'ın içinde" cümlesi Spike 4'te zaten çürütülmüştü).

### Karar gereksinimleri
- Tarife kaydı: **karar değil, ölçüm** (spike). Ancak imzalı uçla alınacaksa vadeli
  yetkili anahtar üretimi → K-066 (host sırları) kapsamında **karar**.
- Perp 1m klines indirme: **veri ekleme kararı** (Final-Doküman "Bütçeler"; disk ≈ küçük,
  ama K-056/1 "iki kaynak karışmaz" gereği yeni depo dizini).
- "IS boyunca tarife sabit" varsayımı: ikinci tavan raporunda **açık varsayım**; K-kaydı
  gerektirmez, sınırlama olarak yazılır.

---

## B-3 — Marjin / likidasyon

### Mevcut durum
Repo ve karar kayıtlarında **hiçbir tanım yok:** margin type, maintenance margin, mark
price, likidasyon formülü, kaldıraç. Var olan iki cümle: K-008 ("spot'ta likidasyon yok;
futures'a geçilirse yeniden verilmeli") ve Final-Doküman v2 / K-048 ("kaldıraç, kısa
pozisyon, perp ile işlem: kapsam dışı; perp bilgi kaynağı olarak kalır"). `config/risk.json`
(K-033) kaldıraç/likidasyon limiti taşımıyor. Model **seçilmiyor.**

### Eksik veri
1. Bakım marjin kademe tablosu (`mmr` ve bakım tutarı, sembol × notional kademesi).
2. Mark price serisi (likidasyon mark'a göre tetiklenir; premium index mark değildir).
3. Marjin rejimi kuralları (isolated / cross / portföy marjini; spot teminatın sayılıp
   sayılmadığı; otomatik marjin ekleme; ADL; likidasyon ücreti).
4. Likidasyon formülünün borsa tanımı (repoya yazılmadı; burada da yazılmıyor — formül
   spike'ta borsa dokümanından tarih ve kaynakla kaydedilir).

### Gerekli veri ve kaynak
| Veri | Kaynak | PIT durumu |
| --- | --- | --- |
| `mmr` kademeleri | `GET /fapi/v1/leverageBracket` (imzalı, vadeli anahtar) **veya** Binance "leverage & margin" sayfası | **anlık**; tarihsel kademe değişiklikleri arşivlenmiyor → IS'e uygulanınca "bugünkü kurallar geçmişe" varsayımı, açıkça yazılır |
| Mark price | `data.binance.vision` `futures/um/monthly/markPriceKlines/<S>/1h/` (premiumIndexKlines ile aynı aile; **varlığı spike'ta listelenir**) | tarihsel |
| Marjin rejimi kuralları | Binance vadeli dokümanı | anlık, kural metni |

### Likidasyon modelinin minimum girdileri
Giriş fiyatı, mark price yolu (1h yeterli mi → 1m'de tetiklenen likidasyon 1h'de
görünmez; bu bir **model sınırı**, spike'ta yazılır), `L` (ızgara, seçilmez), `mmr` ve
bakım tutarı (kademe), marjin modu, marjine akan funding (negatif funding **marjinden**
ödenir — funding koşu dağılımı A-1 burada girdi), likidasyon ücreti, otomatik marjin
ekleme kuralı (varsa likidasyon yerine "marjin çağrısı sayacı"). Çıktı: `L` ızgarası ×
sembol için IS'te likidasyon (ya da marjin çağrısı) **sayısı** ve tarihleri; A-5 MFE
dağılımı bunun fiyat tarafıdır.

### Borsa / marjin seçimi neden karar gerektirir
Aynı fiyat yolu, aynı `L`: isolated modda perp bacağı tek başına likide olabilirken
portföy marjininde spot bacağın kazancı teminat sayılır ve likidasyon mesafesi niteliksel
olarak değişir. Yani sayaç "modele" değil **hesap yapısına** bağlı; hesap yapısı bir
operasyon kararıdır (hangi borsa, hangi hesap tipi, spot ve vadeli aynı cüzdanda mı). Bu
karar verilmeden ölçüm iki ayrı senaryo olarak raporlanabilir ama tek sayıya inemez.

### Seçim yapılırsa gereken K-kayıtları
- Kapsam: Final-Doküman v2 "Yok" tablosu + K-048 → perp ile işlem kapsamı (yeni K).
- K-008 → likidasyon-bilinçli kill switch (pozisyonu tutmak artık güvenli değil).
- K-033 → kaldıraç üst sınırı, likidasyon mesafesi alt sınırı, bacak dengesizliği limiti,
  marjin oranı guard'ı — her biri `olculdu/istah` kaynaklı.
- K-046 → iki bacaklı mutabakat (spot + perp pozisyon + funding defteri + marjin bakiyesi).
- K-057 → çift bacaklı hedef sözleşmesi.
- K-066 → vadeli yetkili anahtar (salt okunur bile olsa yeni anahtar).
`L` ızgarasındaki hiçbir değer **önerilmiyor**; ölçüm ızgara verir.

### DATA BLOCKED sınırı
`mmr` tablosu **ve** mark serisi gelmeden likidasyon sayacı üretilmez; ikisi gelince sayaç
`L` ızgarası ve iki marjin senaryosu (isolated / portföy) için deterministiktir. Marjin
rejimi **seçilmeden** tek bir sayı yoktur — ikinci tavanın stres aşaması bu satırı iki
senaryo olarak taşır ya da BLOCKED bırakır.

---

## B-5 — USDT benchmark (fırsat maliyeti)

### Mevcut durum
- FRED hattı **var:** `tools/faz12_makro_indir.py` (ALFRED vintage, yıl parçalı istek, her
  parçanın SHA-256'sı `.kaynak.json`), `data/makro.py` PIT kuralı (K-060: `realtime_start`
  gün çözünürlüğü, değer `d+1` 00:00'dan görünür; hafta sonu/tatil son gözlem; ilk
  vintage öncesi NaN). Anahtar hostta kullanıcı ortam değişkeni (K-066).
- İndirilmiş seriler: VIXCLS, DGS10, T10Y2Y, DTWEXBGS, NFCI, BAMLH0A0HYM2. **DTB3 yok.**
  `makro.SERILER` (program kaydındaki kullanım) yalnız `vix`, `nfci`.
- USDT/stablecoin getiri serisi (Binance Earn, borç verme, DeFi): **yok**; arşivi de yok →
  ölçülemez.

### Gerekli veri
| Alan | Değer |
| --- | --- |
| Seri | FRED/ALFRED `DTB3` — 3-Month Treasury Bill Secondary Market Rate, Discount Basis |
| Frekans | günlük (iş günü), yüzde |
| Aralık | 2019-09 (funding verisinin başı) → bugün; IS için 2020-01 → 2025-02 |
| Kaynak | FRED API (`api.stlouisfed.org`, mevcut anahtar), ALFRED vintage — DTB3 revize edilmez ama hat aynı kalıpla iner |
| Lisans/erişim | FRED verisi kaynak (Fed H.15) atıfla serbest kullanım; anahtar ücretsiz; erişim mevcut hatla doğrulanmış (6 seri indi) |
| Hatta ekleme | `faz12_makro_indir.py::SERILER` demetine `"DTB3"` eklenir → `data/makro/DTB3.parquet` + `.kaynak.json`; `makro.SERILER`'e **eklenmez** (o sözlük program kaydına bağlı, K-051/2) — benchmark araştırma programı değil, tavan girdisi |

### Benchmark formülü (tasarım; hesaplanmadı)
- Günlük benchmark getirisi: `r_bench,d = DTB3_d / 100 / 365` — DTB3 **discount basis**tir;
  yatırım getirisine (bond-equivalent) çevrim spike'ta yazılır ve uygulanır; iki tanım
  arasındaki fark küçük ama sıfır değil, seçim kaydedilir.
- PIT: `d` gününün oranı `d+1`den itibaren (K-060); hafta sonu son gözlem.
- Uygulama tabanı: **toplam sermaye** `N(1 + m + b)` (spot + perp marjini + tampon), yalnız
  spot bacak değil — nakit yatırılmayan sermaye de fırsat maliyeti taşır.
- `r_excess,d = r_cap,d − r_bench,d`; excess Sharpe günlük excess'ten, √365.
- Ayrı satırlar: brüt funding (`r_pos`), maliyet-düzeltilmiş (`r_gross`), fırsat-maliyetli
  (`r_excess`). Karıştırılmaz.
- Sınırlama beyanı: USDT ≠ USD (depeg ve platform riski benchmark'ta yok); benchmark
  "risksiz" değil, "ölçülebilir en yakın nakit getirisi".
- Döngüsellik notu: funding tabanı (`0,0001`/8h) Binance'in kendi faiz bileşenidir;
  benchmark olarak **kullanılmaz** (A-2'de ayrı satır).

### Veri ekleme kararı gerektiren noktalar
- `DTB3` indirme: **veri ekleme kararı** — küçük (tek seri), mevcut hat, ücretsiz; ama
  Final-Doküman "Bütçeler" kalemi ve K-056 kalıbı gereği kayıtla yapılır.
- Discount → bond-equivalent çevrimi: **yöntem kararı**, spike'ta kaynakla yazılır
  (K-kaydı değil).
- Stablecoin getirisi alternatifi: veri yok → **ölçülemez**, karar konusu değil.

---

## Ayrım

### MEVCUT VERİYLE ÖLÇÜLEBİLİR
- B-1: spot bacak maliyeti ve `H` amortismanı (A-6'da yapıldı); stres çarpanlarının perp
  kalemine **nasıl** uygulanacağı (formül hazır, sayı yok).
- B-3: likidasyonun **fiyat tarafı** (A-5 MFE dağılımı) ve marjine akan funding'in koşu
  yapısı (A-1); iki marjin senaryosunun **tanımı**.
- B-5: hiçbir şey — benchmark serisi yok. (Funding tabanı ayrıştırması A-2'de var, benchmark
  değil.)

### VERİ GEREKİYOR
- B-1: USDT-M tarife kaydı (spike); perp 1m klines BTC+ETH IS (arşiv); bookTicker (varsa,
  örneklem).
- B-3: `mmr` kademe tablosu (anlık); mark price 1h arşivi (varlığı listelenecek); marjin
  rejimi kural metni; likidasyon formülü kaynağı.
- B-5: FRED `DTB3` (mevcut hat, tek seri).

### KARAR GEREKİYOR
- Veri ekleme: perp 1m klines deposu (B-1), mark price deposu (B-3), `DTB3` (B-5) —
  Final-Doküman "Bütçeler", K-056 depo ayrımı.
- Anahtar: vadeli uçlar (`commissionRate`, `leverageBracket`) imzalı → vadeli yetkili
  anahtar üretimi, K-066.
- Marjin rejimi / hesap yapısı seçimi (B-3) — operasyon kararı; seçilirse Final-Doküman
  kapsamı, K-008, K-033, K-046, K-057 yeniden açılır. **Bu doküman seçmiyor.**
- `L` seçimi — K-033; **önerilmiyor.**

Bu doküman hiçbir veri indirmedi, karar açmadı, kod yazmadı, ikinci tavanı hesaplamadı.
