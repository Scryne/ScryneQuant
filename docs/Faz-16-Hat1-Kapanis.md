---
proje: ScryneQuant
faz: 16
tur: metodolojik kapanış raporu — Hat 1 (delta-nötr carry ikinci tavanı)
tarih: 2026-09-20
type: rapor
durum: DATA BLOCKED — eksik katman (perp fee) + eksik sınıf (liquidation threshold); hat yeniden açılma koşuluyla askıda
---
# Hat 1 — Metodolojik kapanış

Bu rapor yeni hesap çalıştırmaz, veri indirmez, sayı değiştirmez; mevcut kayıtları tek
yerde bağlar. Karar hükmü içermez (CLOSE/ELIGIBLE/performans/gate yok). Yeni K açmaz.

## 1. Amaç ve kapsam

**Soru:** Adım 0'ın ideal delta-nötr carry tavanı (spot long + perp short; `r_t = funding_t −
Δbasis_t`; maliyet/marjin/likidasyon sıfır) gerçekçi ekonomik koşullarda ne kadar kalıyor?
İkinci tavan dört katmanı ayrı ölçmek için kuruldu (`Faz-16-Hat1-Ikinci-Tavan-Tasarimi.md`
§9): **(1) ideal → (2) maliyet-düzeltilmiş (spot + perp yürütme) → (3) fırsat-maliyetli
(USDT nakit getirisi) → (4) stres (yedi senaryo sınıfı)**; kapanış kuralı §10 (1,04 eşiği
değişmeden; ELIGIBLE ≠ promotion).

**BTC+ETH ile havuz neden ayrı:** perp slippage kalibrasyonu (K-021 yöntemi) sembol başına
1m perp veri ister; veri kararı B yalnız BTC+ETH için açıldı (≈184 MB), 26 sembol için B-6
açılmadı (≈2,4 GB, "mevcut kararları değiştirmiyor"). Bu yüzden (2)–(4) yalnız BTC+ETH'de;
28'lik havuz için yalnız (1). BTC+ETH sonuçları havuza **genellenmez**: A-7 PIT kesişimi
havuzun 6 sembolünün IS'in yarısında evrende olmadığını, A-2 talep bileşeninin 9/28 sembolde
negatif olduğunu ölçtü — havuz BTC/ETH'nin ölçeklenmiş kopyası değil.

## 2. Tamamlanan ölçümler (tümü deterministik, iki koşuda içerik hash'i eşit)

| Ölçüm | Kayıt | Sonuç (değiştirilmedi) | Statü |
| --- | --- | --- | --- |
| (1) İdeal tavan | `Faz-16-Hat1-Carry-Tavan-Olcumu.md`, K-078 | BTC +14,2 %/y S 9,5; ETH +17,1 / 8,8; havuz(28) +13,8 / 6,6 | tavan; ekonomik edge değil |
| A listesi (8 girdi) | `Faz-16-Hat1-A-Olcumu.md` | funding koşuları, taban/talep (BTC talep +2,84, 4/7 yıl negatif), basis aleyhte, yüksek-vol, MFE, spot maliyet, PIT kesişimi, `r_cap` ızgarası | girdi |
| Perp slippage (K-021 aynen) | `hat1_b1_perp_slippage.json`, Spike 8 | IS p75 BTC **7,11** / ETH **9,11** bps; örtüşme penceresinde perp 5,83 vs spot 5,67 | ölçüldü; config'e yazılmadı |
| DTB3 benchmark | `hat1_b5_benchmark.json`, veri kararı A | BEY IS ort. %2,60 (2020 0,37 → 2023 5,20); K-060 PIT | ölçüldü |
| (2) `r_gross_ust_sinir_fee0` | `Faz-16-Hat1-Ikinci-Tavan-Kismi-Raporu.md` | BTC H30/90/365: 8,74 / 12,38 / 13,75 %/y; ETH 12,44 / 15,54 / 16,71; açılış+kapanış 44,8 / 38,2 bps (fee_perp = 0) | **üst sınır**, kapı dışı (`gecici_maliyet_modeli`) |
| (3) `r_excess` | aynı | BTC H90 L1/b0 3,59 %/y, excess S 4,59; L5/b0 7,71 / 6,04; ETH 5,17/5,14 → 10,35/6,27 | üst sınır |
| `basabas_fee_perp_bps` | aynı | BTC L1/b0: H30 **8**, H90 68, H365 346 (H30 b=m **−3**); ETH 21 / 102 / 471 | **eşik**, gerçek fee değil |
| (4) Stres — beş sınıf | aynı | funding negatif ×k, basis aleyhte w, yüksek-vol (koşullu), borsa taban 0 (BTC H365 **2,80**), erişim kaybı D | ölçüldü; parametre ızgara |
| Execution sınıfı | aynı | `slippage_2x/3x` tam; `fee_2x/hepsi_2x` **KISMİ** (yalnız spot fee) | kısmi |
| `stres_bozulma` | aynı | BTC H30 35,7 pp (erişim kaybı D1) · H365 10,95 pp (taban 0); ETH 28,7 / 10,95 | **alt sınır** (eksik sınıf); IS yıllık, OOS toplam-getiri kapısıyla yalnız mertebe kıyası |

## 3. Blokaj matrisi

| Blokaj | Eksik veri | Neden gerekli | Erişim sonucu (2026-09-20) | Karar / K | Gate'e etkisi | Yeniden açılma koşulu |
| --- | --- | --- | --- | --- | --- | --- |
| **Perp taker fee → BLOCKED** | VIP 0 USDT-M taker (bps), tarihli, doğrulanabilir | `c_perp = fee + slip`; (2)'nin bir terimi; (3) ve execution stresi ona bağlı; spot→perp taşıma yeni varsayım (K-020 hatası) | fee sayfası ve Leverage&Margin `curl` **202**/JS; FAQ'lar oran vermiyor; `commissionRate` **401 −2015**; `apiRestrictions`: **`enableFutures=false`**; UI'da seçenek yok (FAQ 360002502072: hesap açılmadan üretilmiş anahtara verilemez) | K-007 (taker, kalibre), K-021, K-066 Ek (yalnız iki uç), Scryne: **vadeli hesap açılmıyor** | `MUTLAK_ENGELLER::gecici_maliyet_modeli` — hiçbir sonuç kapıya giremez | doğrulanabilir taker fee kaydı (imzalı yanıt + hash **veya** hash'lenebilir resmî sayfa) |
| **MMR kademeleri → BLOCKED** | `maintMarginRatio`, `cum`/bakım tutarı, notional sınırları, tarihli | C-isolated likidasyon sayacının eşiği; MMR ≥ 0 sınırı dışında değer yok | `leverageBracket` **401 −2015**; sayfa 202; FAQ tablo görsel; `exchangeInfo.maintMarginPercent` resmî dokümanda **"ignore"** → kullanılmaz | K-066 Ek, C-1/C-2, Scryne: iki sınıf EMPTY | likidasyon senaryosu tanımsız → `stres_bozulma` alt sınır | kademe kaydı + kayıt tarihi (PIT sınırı) |
| **Liquidation-threshold stress → CLOSED** | MMR (üstteki) + bakım tutarı + likidasyon ücreti (✓ `0.012500`, hash'li) + formül (metin ✓, görsel ✗) | 4. aşamanın yedinci sınıfı; `C-isolated`/`C-portfolio` | mark 1h ✓ (kapsama 0,996/0,999, suspect 0); MMR ✗ | C-1 iki senaryo, C-2 ayrı satır, NON_PIT açılmadı | sınıf boş; bozulma yalnız artabilir | MMR gelince: `C-isolated` kayıt tarihinden ileriye PIT satır; IS için yalnız NON_PIT/leak_risk (kapı dışı) |
| **B-6 havuz perp slippage → BACKLOG** | 26 sembol perp 1m (≈2,4 GB) | havuz için (2)–(4) | açılmadı (Scryne: mevcut kararları değiştirmiyor) | veri kararı, K-056 depo ayrımı | havuz sonucu yalnız ideal; **mevcut karar için gerekli değil** | "havuz geneli perp maliyet" sorusu ayrıca sorulursa bağımsız karar |
| C-portfolio (haircut, uygunluk) → BACKLOG | teminat haircut oranları, hesap tipi şartı | portföy marjini sayısı | repoda yok; açılmadı | C-1 | band olarak kalır | kural metni kaydı + hesap kararı |
| Mark boşluk günleri (günlük arşiv) → BACKLOG | 5+2 tam gün | boşluk günü "ölçülemez" | açılmadı | veri kararı C notu | ihmal | küçük bağımsız karar |

## 4. PIT / NON_PIT sınırı

Fee ve MMR **ne zaman elde edilirse edilsin**, kayıt tarihi PIT sınırıdır. 2026-09-20 ya da
sonrasında alınan bir kademe tablosu 2020–2025 IS'e uygulanırsa sonuç `NON_PIT/leak_risk`
sınıfına girer: resmi kapıya giremez (K-058 `leak_riski` mutlak engel; K-049/4 geriye dönük
türetim), doğrulanmış tarihsel sonuç gibi sunulamaz, yalnız duyarlılık satırı olabilir.
Bugün PIT MMR **EMPTY**, NON_PIT MMR **EMPTY**; hiçbir güncel değer geçmişe yayılmadı. Mark
serisi PIT'tir (arşiv); PIT sorunu yalnız fee/MMR/marjin kurallarındadır. Likidasyon ücreti
`0.012500` kaydının PIT sınırı 2026-09-20 07:07:59 UTC; öncesi bilinmiyor.

## 5. Ne ölçülmedi

- **Gerçek `c_perp`** (fee bilinmiyor) → gerçek `r_gross`, gerçek `r_excess`, gerçek
  `fee_2x`/`hepsi_2x`.
- **Gerçek likidasyon sayacı** — `C-isolated` ve `C-portfolio`; marjin çağrısı sayısı; MMR
  alt sınır/başabaş ara ölçümleri de **çalıştırılmadı** (tanımlı, hesaplanmadı).
- **Havuz geneli perp slippage ve (2)–(4)** — 26 sembol.
- Mark'tan MFE'nin yeniden hesabı ve mark'la basis M2M (tanımlı, çalıştırılmadı).
- Ödeme aralığı 8h→4h senaryosu (oran yeniden ölçeklemesi tanımsız; atlandı, not).
- Tasarım §10 kararı (uygulanamaz).

## 6. Sonuç

**`DATA BLOCKED — eksik katman (perp fee) + eksik sınıf (liquidation threshold)`.**

CLOSE değil, ELIGIBLE değil; hiçbir performans ya da gate hükmü yok. Üretilen bütün sayılar
üst sınır (fee=0), eşik (başabaş fee) ya da alt sınır (`stres_bozulma`) niteliğindedir ve
kapı dışıdır. Adım 0'daki FURTHER-RESEARCH-ELIGIBLE durumu (K-078/3) bu raporla **ne
yükseltildi ne düşürüldü**: ikinci tavan tamamlanamadığı için o durum "eksik katmanla
askıda" olarak kalır.

## 7. Yeniden açılma koşulları

| Koşul | Sağlanınca çalıştırılacak |
| --- | --- |
| Doğrulanabilir VIP 0 USDT-M taker fee (tarihli, hash'li, resmî) | `config/maliyet.json`'a `fee_taker_bps_perp` (kalibrasyon bloğuyla; **karar**) → `faz16_hat1_ikinci_tavan_kismi.py` fee ile yeniden: gerçek (2), (3), execution `fee_2x/hepsi_2x` tam; `basabas_fee_perp_bps` ile karşılaştırma; §10 kuralı (fee tek eksikse "eksik sınıf: likidasyon" notuyla) |
| MMR kademeleri + bakım tutarı (tarihli) + formül görselinin aktarımı | `C-isolated` likidasyon sayacı **yalnız kayıt tarihinden ileriye** (PIT satır; gölge gibi biriktirilir); IS için isteğe bağlı NON_PIT satırı, kapı dışı; `stres_bozulma` yedinci sınıfla |
| PIT kapsamının açıkça belirlenmesi (kayıt tarihi, hangi satır PIT) | yukarıdaki iki ölçümün etiketleri; program kaydı (K-051) ancak PIT satır kapıyı geçerse |
| (İsteğe bağlı) B-6 | havuz (2)–(4) |

Üçü birden sağlanırsa ikinci tavan **tam** hesaplanır ve §10 kuralı uygulanır; sonuç yine
promotion kanıtı değildir (tasarım §10).

## 8. Faz 16 sürekli araştırma defteri — Hat 1'in bıraktıkları

**Veri (hepsi `.kaynak.json` + SHA pinli, `data/` gitignore, hash'ler raporlarda):**
`data/makro/DTB3` (ALFRED vintage, 2017→, K-060 PIT) · `data/turev/klines_1m/{BTC,ETH}USDT`
(perp 1m, 2020-01→2025-02, checksum'lu, kapsama 1,0) · `data/turev/mark/{BTC,ETH}USDT` (mark 1h,
2020-01→2025-02, kapsama 0,996/0,999) · `data/turev/kurallar/` (exchangeInfo snapshot —
likidasyon ücreti; `apiRestrictions` kaydı; `-2015` denemeleri) · funding 43 sembol (2026-09-19
yenilendi) · premium/basis 759 sembol (mevcut).

**Araçlar (`tools/`):** `faz16_carry_tavan.py` (ideal) · `faz16_hat1_a_olcum.py` (8 girdi) ·
`faz16_perp_klines_indir.py`, `faz16_mark_indir.py` (arşiv indirici kalıbı, başlık satırı
toleranslı) · `faz16_hat1_b1_perp_slippage.py` (K-021 aynen, config'e yazmaz) ·
`faz12_makro_indir.py --ek` (program serilerine dokunmadan ek seri) · `faz16_hat1_b5_benchmark.py`
(BEY/discount, L×b ızgarası) · `faz16_vadeli_okuma.py` (iki salt okunur uç, anahtar
çıktısız) · `faz16_hat1_ikinci_tavan_kismi.py` (eksik sınıf yaklaşımı). Hepsi deterministik,
içerik hash'li, karar vermez.

**Metodoloji:** tavan → gerçekçi → fırsat maliyeti → stres sırası ve neden ayrı tutulduğu
(tasarım §9); "eksik katman/sınıf" raporlama kalıbı; başabaş girdi (fee, MMR) yaklaşımı;
PIT/NON_PIT ayrımının veri değil **kural** kaynaklı girdilere uygulanması; `makro.SERILER`
program sözlüğü ile tavan girdilerinin ayrılması (açık entegrasyon kararı).

**Bilinen blokajlar:** perp fee ve MMR kademeleri yalnız vadeli-yetkili anahtarla
(hesap açılmadan verilemez — Scryne: açılmıyor); resmî web sayfaları bot korumalı.

**Bağımsız backlog'lar:** B-6 (havuz perp 1m slippage) · C-portfolio (haircut/uygunluk) ·
mark boşluk günleri (günlük arşiv) · DTB3'ün program sözlüğüne/host sözleşmesine dahil
edilip edilmeyeceği · formül görselinin aktarımı.

**B-6 neden açılmadı:** havuz (2)–(4) BTC/ETH'nin ölçeklenmişi değil ama fee ve MMR olmadan
havuz için de aynı iki blokaj geçerli; ≈2,4 GB veri mevcut DATA BLOCKED kararını değiştirmez.
"Havuz geneli perp maliyet" sorusu ayrıca sorulursa bağımsız karar.

Değişmeyen: `src/`, config, execution, K kayıtları, defter (52), eşik 1,04, Jev (gölge yalnız
doğrulama), spot kapsamı.
