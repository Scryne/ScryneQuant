---
proje: ScryneQuant
faz: 16
tur: ölçüm (ikinci tavan girdileri; karar yok, seçim yok, çekiliş yok)
tarih: 2026-09-20
type: rapor
durum: tamamlandı — ikinci tavan HESAPLANMADI
---
# Hat 1 — İkinci tavan A listesi ölçümü (8 kalem)

**Ne yapıldı:** `docs/arsiv/Faz-16-Hat1-Ikinci-Tavan-Tasarimi.md` §A'daki sekiz girdi, oradaki
tanımlarla, yalnız depodaki veriden çıkarıldı. **Ne yapılmadı:** ikinci tavan hesabı,
CLOSE/ELIGIBLE, H/δ/L seçimi, perp maliyeti, USDT benchmark, likidasyon modeli, marjin
tipi, stres parametresi, strateji, backtest, Jev. Betik: `tools/faz16_hat1_a_olcum.py`;
çıktı: `runs/faz16/hat1_a_olcum.json` (28 sembolün tamamı, yıl kırılımları).

## 1. Veri ve pencere

| Kaynak | Yol | Sürüm / hash |
| --- | --- | --- |
| Funding | `data/funding/<s>.parquet` (43 sembol, REST, 2026-09-19) | BTC `900484f2…`; her sembolün SHA-256'sı JSON `veri.semboller` |
| Premium (basis) | `data/turev/premium/<s>.parquet` (arşiv `premiumIndexKlines`, aylık zip SHA'ları `.kaynak.json`) | BTC `c61452ad…` |
| Spot 1h barlar | `data/evren/<s>/1h.parquet` (arşiv, K-056) | BTC `3e692b23…`, IS 65.604 bar |
| PIT evren tablosu | `data/evren/_evren/27b7a16ed0ed.parquet` (aylık, sıra ≤ 50, K-052) | `9389b5cb…` |
| Maliyet modeli | `config/maliyet.json` (K-007, K-021) | `9f96ef10…` |
| Risk limitleri | `config/risk.json` (K-033; `volatilite_esigi` + dağılım) | `814ac6c3…` |
| Adım 0 çıktısı | `runs/faz16/carry_tavan.json` (`r_pos` kaynağı) | `1798422c…` |

**Pencere:** in-sample, her serinin başı → **2025-02-16 18:00 UTC** (BTC tek-sembol OOS
başlangıcı, `research/bolme.is_oos`), dahil değil. **Semboller:** Adım 0'ın 28'i.
**Tekrar üretilebilirlik:** betik deterministik, harici çağrı yok; iki ardışık koşuda
`uretim_utc` hariç içerik hash'i **aynı**: `icerik_sha256 = 671c2bc9dc5b71a4…`. Koşu ≈ 8 s.

## 2. Kalem tanımları, yöntem, sonuç

### 1 — Funding koşu yapısı

Tanım: `data/funding.py` ödeme olayı; ardışık aynı-işaretli ödemeler bir **koşu**.
Raporlanan: koşu sayısı, negatif koşuların zaman payı, en uzun / en derin negatif koşular,
yıl kırılımı.

| Sembol | Neg. zaman payı | En uzun neg. koşu | Kümülatif | En derin neg. koşu |
| --- | ---: | --- | ---: | --- |
| BTC | 0,13 | **8,0 gün** (2020-03-12, 24 ödeme) | −1,04 % | aynı |
| ETH | 0,11 | **8,3 gün** (2022-09-08, 25 ödeme) | −1,35 % | aynı |
| TRX | 0,31 | **34,3 gün** (2022-06-10, 103 ödeme) | −6,27 % | aynı |
| WLD | 0,24 | 34,3 gün (2023-09-17) | −2,26 % | — |
| BCH | 0,32 | 30,0 gün (2024-04-14) | −1,80 % | — |
| 28 sembol medyan | — | 7,5 gün | — | — |

BTC yıl kırılımı (neg. ödeme payı / en uzun neg. koşu, ödeme): 2019 0,18/9 · 2020 0,14/24 ·
2021 0,07/9 · **2022 0,22/10** · 2023 0,10/7 · 2024 0,08/18 · 2025 0,05/1. ETH 2022:
**0,34/25**. Uzun negatif dönemler BTC/ETH'de 8 günü aşmıyor; üç altcoinde bir ayı aşıyor.
Bunlar §8 "funding uzun süre negatif" senaryosunun **tarihsel parametre dağılımıdır**;
parametre seçilmedi.

### 2 — Taban / talep ayrışması

Tanım: taban = sembolün funding serisinin **modu** (veriden; 8h sembollerde 0,0001, 4h'te
0,00005 — PENGU'da ölçüldü); talep = oran − taban. Yıllık = ortalama × ödeme/yıl (ödeme
aralığı serinin medyanından).

| Sembol | Taban payı | Taban %/yıl | Talep %/yıl | Toplam %/yıl | Talep < 0 ödeme payı |
| --- | ---: | ---: | ---: | ---: | ---: |
| BTC | 42,3 % | 10,95 | **+2,84** | 13,79 | 0,40 |
| ETH | 41,6 % | 10,95 | +6,04 | 16,99 | 0,37 |
| 28 sembol medyan | 47,3 % | — | +2,9 | — | — |
| Talep negatif sembol | — | — | **9 / 28** | — | — |

BTC talep bileşeni yıl bazında: 2019 −3,5 · 2020 +6,2 · 2021 **+19,7** · 2022 −6,8 ·
2023 −3,1 · 2024 +1,0 · 2025 −3,8. **Okuma (ölçüm, yorum değil):** taban çıkarıldığında
BTC'de talep bileşeni yedi yılın dördünde negatif; toplamın pozitifliği tabandan geliyor.
"Taban 0" senaryosu (§8 borsa parametresi) BTC'de +2,84 %/yıl bırakır.

### 3 — Basis aleyhte hareket dağılımı

Tanım: `evren_premium_dizisi` (premium 1h `close`); short perp için aleyhte yön basis
**artışı**; `w`-gün değişimi `basis_{t+w} − basis_t`, her saat için; pencere w ∈ {1, 7, 30}.

| Sembol | Basis p1 / p50 / p99 | 1g p99 / max | 7g p99 / max | 30g p99 / max | 7g > %1 payı |
| --- | --- | --- | --- | --- | ---: |
| BTC | −0,093 / −0,027 / 0,184 % | 0,122 / **2,94** % | 0,150 / 2,93 % | 0,177 / 2,90 % | 0,02 % |
| ETH | −0,100 / −0,017 / 0,232 % | 0,152 / 2,31 % | 0,175 / 2,36 % | 0,205 / 2,36 % | 0,01 % |
| 28 sembol medyan | — | — | p99 0,216 / max 2,33 % | — | — |
| Kuyruk | — | — | max **25,4 %** (BCH) | — | — |

Yıl kırılımı BTC (7g p99 / max, %): 2020 0,21/2,01 · **2021 0,17/2,93** · 2022 0,08/0,55 ·
2023 0,12/0,77 · 2024 0,11/0,31 · 2025 0,08/0,19. En kötü olaylar 2020-03 (kriz) ve
2021-04/05 (boğa tepesi) — kuyruk iki yönlü olay ekseninde, düzeyde küçük. Yeni stres
parametresi seçilmedi; dağılım §8 girdisidir.

### 4 — Yüksek-volatilite alt örneği

Tanım: `risk/kalibrasyon.volatilite_olc` — ATR(14)/close, 1h; eşikler `config/risk.json`
kaydından: p90 0,0119, p95 0,0140, **p99 = `volatilite_esigi` 0,0205** — üçü de **BTC'de
kalibre** ve öyle uygulandı (sembol başına yeniden kalibrasyon = yeni seçim, yapılmadı).
Bir gün, bir barı eşiği aşıyorsa "yüksek-vol günü". Yeni rejim tanımı yok.

| Sembol / eşik | Bar payı | YV gün | Δbasis ort / p99 (YV) | Funding gün. ort (YV / diğer) | MFE-24 gün. max p90 (YV / diğer) |
| --- | ---: | ---: | --- | --- | --- |
| BTC p99 | 7,2 % | 298 | +0,013 % / 0,457 % | 0,063 % / 0,036 % | **18,0 % / 7,6 %** |
| BTC p95 | 17,8 % | 742 | −0,003 % / 0,154 % | 0,058 % / 0,033 % | 14,8 % / 6,7 % |
| ETH p99 | 11,5 % | 498 | −0,008 % / 0,389 % | 0,083 % / 0,041 % | 19,2 % / 9,2 % |

Yüksek-vol günlerinde funding **daha yüksek**, basis günlük değişimi kuyrukta 3× daha
geniş, 24 saatlik azami yukarı hareket 2,4× daha büyük. Ölçüm; koşul değil.

### 5 — MFE fiyat girdisi

Tanım: `jev/sonuc.py` — giriş `open[i+1]` (K-004), pencere `w` bar, `max(high[i+1..i+w]) /
giriş − 1`; her bar giriş sayılır (örtüşen pencereler); boşluklu pencere düşer. Short perp
için likidasyon yönü. **Yalnız ölçüm girdisi:** ileri bakar, hiçbir seçim/filtre üretmez;
`mmr` (B-3) gelmeden likidasyon sayacına çevrilemez.

| Sembol | 1 gün p50 / p90 / p99 | 7 gün p99 | 30 gün p99 / max | 90 gün p99 / max |
| --- | --- | ---: | --- | --- |
| BTC | 1,7 / 5,9 / 14,2 % | 35,7 % | **107,6 % / 216 %** | 384 % / 509 % |
| ETH | 2,2 / 7,4 / 16,7 % | 44,4 % | 107,5 % / 148 % | 194 % / 275 % |
| 28 sembol medyan (30 g p99) | — | — | 174 % | — |
| En yüksek (30 g p99) | — | — | 655 % (DOGE) | — |

BTC 30 gün p99 yıl bazında: 2017 186 % · 2018 48 % · 2019 80 % · 2020 61 % · 2021 49 % ·
2022 43 % · 2023 44 % · 2024 60 % · 2025 20 %. Pencere 2017'den başlıyor (spot arşivi);
funding/premium 2020'den — MFE tablosu fiyat tarihinin tamamını kapsıyor ve JSON'da yıl
kırılımıyla duruyor, kesişim ikinci tavanda seçilir (tasarım kararı, burada değil).
**DATA BLOCKED:** ONDO (IS'te spot 1h bar yok), TRUMP 30 gün penceresi (30 günden kısa seri).

### 6 — Spot maliyet + dengeleme

Tanım: `config/maliyet.json` aynen — taker 10,0 bps iki yön (K-007); slippage 5,30 bps
**yalnız BTC'de** kalibre (K-021; diğer sembollerde tek yön = fee, eksik işaretli).
Açılış+kapanış spot gidiş-dönüş; `H` gün tutmada yıllık amortisman = gd × 365/H. Perp
kalemi **yok** (B-1, B-2). Dengeleme: eşit **miktar** hedge'inde bacak notional farkı =
|basis|; δ aşım payı ve düzeltme maliyeti = |basis| × spot tek yön.

| | BTC | ETH |
| --- | ---: | ---: |
| Spot gidiş-dönüş | 30,6 bps | 20,0 bps (slippage kalibre değil) |
| Amortisman H=30 / 90 / 365 g (%/yıl) | 3,72 / 1,24 / 0,31 | 2,43 / 0,81 / 0,20 |
| İdeal `r_pos` − spot amortisman, H=30 / 90 / 365 (%/yıl) | 10,47 / 12,96 / 13,89 | 14,66 / 16,28 / 16,89 |
| δ = %1 aşım payı (bar) | 0,02 % (9 bar) | 0,01 % (6 bar) |
| δ = %2 / %5 aşım | 4 bar / 0 | 1 bar / 0 |
| 28 sembol δ=%1 aşım payı medyan / max | 0,02 % / 0,29 % | |

**Okuma:** eşit-miktar hedge'de notional dengesizliği basis'in kendisidir ve %1'i IS'in
%0,02'sinde aşar — δ-dengeleme maliyeti bu tanımla ihmal edilebilir. Gerçek dengeleme
ihtiyacı **marjin oranından** (perp bacağı, §5/likidasyon) doğar; o katman DATA BLOCKED.
Bu tablo ızgaradır, hiçbir H seçilmedi.

### 7 — PIT kesişimi

Tanım: PIT aylık tablo `27b7a16ed0ed` (K-052; ay, sıra ≤ 50). Her IS ayı (funding
verisinin olduğu aylar) için sembol o ay evrende miydi.

| Sembol | IS ay | PIT üye ay | Pay |
| --- | ---: | ---: | ---: |
| BTC / ETH / XRP / BNB / ADA / LINK / LTC | 64–66 | tamamı | **1,00** |
| SOL 0,94 · TRX 0,97 · SUI 0,95 · FET 0,92 · ENA 0,91 · WLD 0,90 · DOGE 0,89 · AVAX 0,89 | | | |
| **Pay < 0,5:** ZEC 0,36 · XLM 0,42 · ACE 0,13 · PYTH 0,06 · **BICO 0,00 · ONDO 0,00** | | | |

**Okuma:** Adım 0 havuzu 2026-09 listesiydi; 28 sembolün 6'sı IS'in yarısından azında
evrendeydi, ikisi hiç. Havuz sonucu **hayatta kalma yanlılığı** taşıyor (K-056 ölçtü: ayda
medyan %17). İkinci tavanda "o ay PIT üyesi olan semboller" havuzu ayrı satır olmalı —
seçim değil, PIT kuralının uygulanması.

### 8 — `r_cap` ızgarası

Tanım: `r_cap = r_pos / (1 + m + b)`, `m = 1/L`, `L ∈ {1, 2, 3, 5}`, `b ∈ {0, m}`; `r_pos` Adım
0 ideal yıllık pozisyon getirisi. Sharpe kaldıraçtan bağımsız; yalnız **düzey** değişir.
Likidasyon **hariç** (DATA BLOCKED). GRID — hiçbir hücre seçilmedi.

| `r_cap` %/yıl | L=1, b=0 | L=1, b=m | L=2, b=0 | L=2, b=m | L=3, b=0 | L=3, b=m | L=5, b=0 | L=5, b=m |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Sermaye çarpanı | 2,00 | 3,00 | 1,50 | 2,00 | 1,33 | 1,67 | 1,20 | 1,40 |
| BTC (`r_pos` 14,20) | 7,10 | 4,73 | 9,46 | 7,10 | 10,65 | 8,52 | 11,83 | 10,14 |
| ETH (`r_pos` 17,09) | 8,55 | 5,70 | 11,39 | 8,55 | 12,82 | 10,26 | 14,24 | 12,21 |

Pozisyon getirisi ≠ sermaye getirisi: `L=1` (kaldıraçsız perp) ve tamponsuz halde bile
sermaye getirisi pozisyon getirisinin yarısı. `L` arttıkça düzey artar, likidasyon mesafesi
(kalem 5 girdisi + `mmr`) azalır — o değiş tokuş burada **ölçülemez**.

## 3. Veri kapsamı ve eksikler

- 28 sembol; 22 sembol (stablecoin, tokenize hisse, çarpanlı sözleşmeler, premium arşivi
  olmayanlar) Adım 0'da olduğu gibi dışarıda.
- Kalem 4/5: ONDO spot 1h IS'te yok; TRUMP 30/90 gün pencereleri seri kısa.
- Kalem 6: slippage yalnız BTC (K-021); diğer 27 sembolde tek yön = fee.
- Kalem 5 penceresi spot arşivinin başından (2017) — funding/premium 2020'den.
- Kalem 4 eşikleri BTC kalibreli; altcoinlerde "bar payı" bu yüzden yüksek (ETH p90'da %42,5).

## 4. Listeler

### A — İkinci tavan hesabına doğrudan girebilecek ölçümler
1. Funding koşu dağılımı (sembol × yıl; en uzun/en derin negatif koşular) → §8 "funding
   negatif" senaryosunun tarihsel parametre kaynağı.
2. Taban/talep ayrışması ve "taban 0" senaryosu yıllık değerleri.
3. Basis aleyhte değişim dağılımı (1/7/30 g; p50/p90/p99/max; yıl) → §8 "basis aleyhte".
4. Yüksek-vol alt örneğinde Δbasis/funding/MFE-24 (üç eşik) → §8 "yüksek vol".
5. MFE dağılımı (1/7/30/90 g; yıl) → likidasyon sayacının **fiyat tarafı**.
6. Spot gidiş-dönüş amortismanı `H` ızgarası; δ-dengeleme aşım payları (ihmal edilebilir).
7. PIT üyelik payları → PIT-tutarlı havuz satırı.
8. `r_cap` ızgarası (`L`, `b`) → sermaye getirisi düzeyi.

### B — Hâlâ veri/model isteyen noktalar
1. Perp komisyon tarifesi (USDT-M, VIP 0, taker) — Spike kaydı.
2. Perp slippage — perp 1m kline arşivi (veri ekleme kararı).
3. Bakım marjin kademe tablosu (`mmr`) ve marjin tipi kuralları — likidasyon sayacı için.
4. Mark price serisi ya da mark ≈ close·(1+premium) hata ölçümü.
5. USDT fırsat maliyeti benchmark'ı (FRED `DTB3`; mevcut FRED hattı, veri ekleme kararı).
6. Diğer 27 sembolde spot slippage kalibrasyonu (1m verisi yok).
7. Borsa çapında kesinti tarihçesi — yok; `D` parametre kalır.

### C — Karar kaydı gerektiren noktalar
1. `L` seçimi (K-033'e kaldıraç limiti) — bu rapor ızgara verdi, seçmedi.
2. Marjin tipi (isolated / cross / portföy marjini; spot teminat sayılır mı).
3. Carry pozisyonunun kapsama alınması — Final-Doküman v2 "Yok" tablosu, K-048; K-045
   istisna lafzı (bilgi kaynağı ≠ getiri mekanizması) → yeni K-kaydı.
4. K-008 (vadeli kill switch), K-046 (iki bacaklı mutabakat), K-057 (çift bacak hedef),
   K-033 (kaldıraç/likidasyon/bacak limitleri) — **dokunulmadı**, ikinci tavan ELIGIBLE derse.
5. K-051 program kaydı — ikinci tavan sonrası.
6. B-2, B-4, B-5 veri ekleme kararları (Final-Doküman "Bütçeler").

Bu rapor hiçbirini açmadı; ikinci tavan hesaplanmadı.
