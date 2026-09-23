# R6 + R7 kapanış değerlendirmesi ve alfa kaynağı envanteri (K-110)

Tarih: 2026-09-22 (UTC). Tür: karar dokümanı — yeni ölçüm yalnız mevcut kayıtlardan türetildi
(defter 62, null önbelleği 48, program kapanış raporları); çekiliş yok, strateji kodu yok. Kaynaklar:
K-045, K-068, K-072, K-077, K-078, K-079, `docs/arsiv/Alpha-Discovery-Gap-Audit.md` (2026-09-20), K-102…K-109,
`runs/faz12/coklu-test/*.json`, `runs/faz12/r7-sinyal-gucu.json`.

## 1. Karar özeti

- **Yeni alfa araştırma hattı bugün açılmıyor.** R6 (FX, 7 çekiliş) ve R7 (kripto, 3 çekiliş) K-078'in
  2026-09-20'de önerdiği beş hattan test edilebilir olanların hepsini kapattı; kalanlar veri/eylem-uzayı
  kararıyla bloke (K-079, K-107). Mevcut veriyle, altyapı değişmeden, **getiri mekanizması farklı** bir
  hat kalmadı.
- **K-078/1'in "hat tükenmiş" okuması bugünkü kanıtla desteklendi** (§4): 48 ölçülebilir çekilişin
  gerçekleşen OOS Sharpe'ı kendi null dağılımının **medyan persentili 0,45-0,50**; null p95'i aşan
  2/17 (şansla beklenen 0,85); IS'te 11 fiyat/hacim sinyalinden 10'unun sıralama gücü |t| < 2.
- **Sınır:** bu sonuç mevcut veri (Binance spot 1h, PIT evren `27b7a16ed0ed`, 429 sembol, 2019→2025;
  FXCM 21 çift 2023-11→2024-02), long-only spot eylem uzayı, fiyat/türev/makro/konumlanma/kurma
  sinyal aileleri ve 11 kapı (`oos_sharpe` 1,04) **kapsamındadır**. "Kriptoda alfa yok" iddiası değildir.
- **Tek uygulanabilir sonraki adım:** Scryne kararı — K-079'un tek kilidi (vadeli hesap → doğrulanabilir
  perp fee + MMR). "Evet" ise Hat 1 (delta-nötr carry) ikinci tavanı mevcut araçla ölçülür; "hayır" ise
  araştırma programı **askıya alınır** ve R8 (paper, kıyasla) açılır — kanıt üretmez, yolu test eder.

## 2. R6 + R7 ortak bulguları (sayılarla)

| | R6 FX (h53-h59) | R7 kripto (h60-h62) |
|---|---|---|
| Çekiliş / kapı geçen | 7 / **0** | 3 / **0** |
| OOS'ta kıyası geçen | 2 (h54 +4,0 USD, h56 +1,8 USD; ikisi de ≤ 11 tur) | 0 (h61 −0,001 Sharpe, h62 −0,015) |
| Tekrar/doğrulama | h54 W2/W3'te negatif → elendi; h56 tekrarı koşulmadı | yok |
| En iyi kapı sayısı | 5/11 (h53, h56) | 7/11 (h61) |
| Ortak kalıp | IS'te kıyasın negatif ayında kazanan, OOS'ta pozitif ayında kaybeden (`−β × kıyas`) | risk profilini değiştiren, risk-ayarlı getiriyi değiştirmeyen (h61 ×0,66 ölçek; h62 DD ↓ getiri ↓) |
| Yapısal kısıt | `asgari_islem` 30 haftalık × 4,3 hafta OOS'ta geçilemez; `yillik_anlamli=False`; proxy finansman mutlak engel | seçim aileleri `oos_is_orani`/`evren_dayanikliligi`'ni kaybediyor (h62: 0,31 / 0,22, XRP) |

Üç bulgu iki varlık sınıfında aynı: **(1)** oynaklık/risk bilgisi (filtre, hedef, kesit) maruziyeti
düşürür, Sharpe'ı artırmaz; **(2)** fiyat sinyalinden seçim IS'te görünen üstünlüğü OOS'a taşımaz;
**(3)** tek OOS başarısı tekrarda tutmaz (h54) ya da tek isme/tek haftaya bağlıdır (h56, h62).

## 3. Tükenen araştırma aileleri — neden tekrar denenmemeli

| Aile | Kayıt | Sonuç | Tekrar denenmeme gerekçesi |
|---|---|---|---|
| Tek sembol yönlü TA (BTC 1h/4h/1d, 6 aile) | K-045, h1-h38 | 0/38; maliyet-sıfır tavan bile kapının yarısı | maliyet duvar değil; sinyal OOS'ta çöküyor; null persentili medyan 0,50 (§4) |
| Funding yönlü filtre/eğilim (tek sembol) | K-042 | 0/3 | funding fiyat yönü için bilgi taşımıyor |
| Kesitsel momentum / ters / **düşük oynaklık** | Faz 12, K-109 (h62) | 0/5; düşük oynaklık IC t≈7 ama OOS kıyas altı | IC'si olan tek sinyal de kıyası geçmedi; K-109/4: IC yalnız "aday" der |
| Kıyas-üstü dışlama (funding, basis, VIX, NFCI, OI, taker) | K-068 | 0/8; aile kapalı | 8 farklı kaynak, aynı iskelet, aynı sonuç; yeniden açılma şartı (IS IC) h62'de sağlandı ve yine yetmedi |
| Rejim / seçici / Jev yönü | K-076, K-077 | oracle tavanı 0,60 | hindsight'la bile kapı altı |
| Kurma katmanı (1/σ, turnover, korelasyon budaması, oynaklık hedefi) | K-070/072, K-108 | genelleşir, Sharpe üretmez (0,36 en iyi) | kaldıraç/ölçekleme; işaret kaynağı olmadan kapıya taşıyacak bir şey yok |
| FX fiyat seçimi / ortalama dönüş / oynaklık filtresi | K-102…K-105 | 0/7 | mekanizma yön bilgisi taşımıyor; proxy finansman promotion'u zaten kapatıyor |
| Duyuru/olay (long) | Faz 16 duyuru | etki aşağı yönde, evren dışı | long-only'de işlenemez |
| Funding uzlaşma anı mikroyapısı (BTC 1m) | K-078/2 | net −29,7 bps, p 0,156 | M-1 kuralı: çapa/pencere değiştirilerek tekrar ölçülmez |
| NY seans çapası | M-1 | p 0,385 | aynı |

Bunların hiçbiri "biraz farklı parametre/pencere/eşik" ile açılmaz: her yeni çekiliş `oos_sharpe`
eşiğini yükseltir (K-044) ve önceki ölçümler beklentiyi sıfırın altına koyuyor.

## 4. K-078/1 ölçümü: hat gerçekten tükenmiş mi?

Üç bağımsız ölçü, hepsi mevcut kayıtlardan:

1. **Gerçek OOS Sharpe vs kendi null'u** (`runs/faz12/coklu-test/`, 500 kaydırma, seed 0, 48 çekiliş):
   gerçekleşen OOS Sharpe'ın kendi null dağılımındaki persentili — tek sembollü 31: medyan **0,50**,
   p95'i aşan **0/31**; evren 17: medyan **0,45**, p95'i aşan **2/17** (`kesitsel_dusuk_oynaklik` 0,986 —
   ama kıyas altı; `evren_funding_basis` 0,968 — kıyas bandı içinde, K-068). %5 düzeyinde şansla beklenen
   0,85; gözlenen 2; ayrışma yok. Yani 48 çekilişin sonuç dağılımı, **aynı iskeletin rastgele zamanlanmış
   hâlinin dağılımından ayırt edilemiyor.**
2. **IS sıralama gücü** (`tools/r7_sinyal_gucu.py`, K-109): 11 fiyat/hacim sinyalinden 10'u |t| < 2 —
   OOS çöküşü değil, IS'te bile kesit bilgisi yok. Tek istisna (düşük oynaklık, t≈7) bir risk primi:
   kıyastan az kaybettiriyor, kıyası geçmiyor.
3. **Defter geneli:** 62 çekiliş, 11 kapıyı geçen 0; en iyi OOS Sharpe 0,46 (h61, kıyasa eşit) /
   0,36 (h51); kapı 1,04; null %5 sınırı 1,004 — en iyi gerçek sonuç, null'un %5 sınırının da altında.

**Sonuç:** K-078/1 destekleniyor — kapsam içinde. Kapsam: Binance spot USDT, 1h, PIT `27b7a16ed0ed`
üst-50 hacim evreni, 2019→2025 (IS 0-55.678 / OOS 23.862 bar); FXCM 21 çift 2023-11→2024-02;
long-only, kaldıraçsız, `hedef_brut` 0,2; sinyal aileleri §3; kapılar K-054/K-058 eşikleri. Bu kapsamın
dışı (short/perp eylem uzayı, on-chain/haber/emir defteri veri sınıfları, başka venue/varlık) ölçülmedi.

## 5. Henüz gerçekten test edilmemiş alfa kaynakları — envanter

| # | Kaynak | Bugün ne var | Test edildi mi | Mevcut sistemde kullanılabilir mi | Yeni sağlayıcı / depo / PIT | Araştırma maliyeti | Sızıntı riski | Gerçek hipoteze alan |
|---|---|---|---|---|---|---|---|---|
| A | **Cross-asset / göreli güç** (FX 21 çift, makro DTB3/DGS10/T10Y2Y/VIX/NFCI/HY spread/DTWEXBGS → kripto) | FX 1h 55 hafta (2012→ indirilebilir, fiyat için finansman gerekmez); makro günlük PIT (K-060) | Kısmen: VIX/NFCI **dışlama** olarak (h47/h48, kıyas bandı); FX→kripto hiç | Evet — `evren_kosu` ek veri kancaları (makro yolu var); FX'i özellik olarak hizalamak küçük iş | Yok (makro PIT `available_time` ertesi gün; FX seans takvimi ↔ 7/24 hizası tanımlanmalı) | Düşük: önce IS IC ölçümü (`r7_sinyal_gucu` kalıbı, 1 gün) | Düşük-orta (makro yayın gecikmesi K-060'da çözülü; FX kapanış saati hizası dikkat) | **Dar:** mekanizma yine kıyas-üstü filtre/seçim (K-068 sınıfı, 9 kez kaldı); makro engel zaten denendi. Yalnız IC ön koşulunu geçerse tek çekiliş |
| B | **Türev — carry pozisyonu** (spot long + perp short: funding + basis hasadı) | funding 761 dosya (43+ sembol), premium/basis 367 MB, mark, OI/taker/L-S metrics 3,3 GB — hepsi PIT | Sinyal olarak evet (0/7, kapalı); **pozisyon olarak hayır**; ideal tavan ölçüldü (K-078/3: BTC Sharpe 9,5 maliyetsiz), ikinci tavan **DATA BLOCKED** (K-079) | **Hayır** — `Yon ∈ {BUY, SELL, FLAT}`, `target_exposure ≤ 1`, spot; iki bacak execution, marjin/likidasyon, 4 taraflı mutabakat yok | Veri var; eksik olan veri değil **katman**: perp taker fee kademesi + MMR (bot korumalı, vadeli hesap ister — Scryne: açılmıyor) | Orta: ikinci tavan aracı yazılı (`tools/faz16_hat1_ikinci_tavan_kismi.py`), fee/MMR gelince koşar; program aşaması **mimari genişleme** (K-008, K-033, K-046, K-057) | Düşük (ödeme olayı, `available_time` net); fee/MMR PIT sınırı kayıt tarihi (K-079/4) | **Geniş:** fiyat yönünden bağımsız tek mekanizma; ama kilit K-079 |
| C | **Türev — short/vadeli yönlü** (düşen rejim, duyuru aşağı etkisi −%8,6) | fiyat var | Hayır (eylem uzayında yok) | Hayır (B ile aynı altyapı) | B ile aynı | B'ye bağlı | orta | Yönlü TA'nın aynası bilgi eklemez (K-045); yalnız olay-short anlamlı; B'siz açılmaz |
| D | **Emir defteri / mikroyapı** | Emir defteri **yok**; 1m yalnız BTC/ETH (turev `klines_1m`), BTC spot 1m; K-021 slippage ölçümü | Kısmen: funding anı (K-078/2 kapalı), NY çapası (M-1 kapalı); derinlik/imbalance hiç | Hayır — motor 1h bar; 1m yol tek sembol; derinlik şeması yok | **Evet:** websocket derinlik anlık görüntüsü ileriye dönük toplanır (geriye yok); depo + PIT yeni | Yüksek: ≥ 6-12 ay toplama, sonra 1m maliyet modeli (K-021: 1m'de 5,3 bps iyimser; gidiş-dönüş 30,6 bps) | Düşük (borsa zaman damgası), ama kapasite/maliyet bağlayıcı | Orta: mekanizma farklı (akış), ama uzun ufuklu portföyle kesişmiyor; ayrı sistem demek |
| E | **On-chain** (aktif adres, borsa rezervi, stablecoin arzı, madenci akışı) | **Yok** | Hayır | Hayır | **Evet:** sağlayıcı (Glassnode ücretli; ücretsiz BTC düzeyi mempool/blockchain.com) + günlük PIT depo; "as-of" arşiv yok → geçmiş revizyon riski ölçülemez | Orta-yüksek: veri bütçesi kararı + K-060 kalıbı yükleyici; kapsam çoğunlukla BTC/ETH | **Orta-yüksek:** sağlayıcı geçmişi revize eder; `available_time` sağlayıcı yayın gecikmesi bilinmiyor | Dar: yine kıyas-üstü filtre/rejim (K-068 sınıfı); BTC-tek sembol yolu K-045 ile kapalı |
| F | **Alternatif veri** — haber/metin, sosyal, LLM türetimi | Duyuru arşivi var (`data/duyuru`, K-067); haber PIT arşivi **yok**; Jev gölge | Duyuru: evet (long'da işlenemez); haber: hayır; Jev yön: kapalı (K-076, %49) | Duyuru yolu var (`olaylar.parquet`) | Haber için PIT arşivi + lisans (Faz 13 koşulu); LLM türetimi `leak_riski` (K-049/4) | Yüksek (arşiv geriye yok, ileri biriktirme yıllar) | **Yüksek** (kesim tarihi, arşiv silinmesi) | Dar bugün; olay-short C'ye bağlı |
| G | **Diğer yapısal:** Deribit opsiyon IV/DVOL (2021→, borsa zaman damgalı, public API) | Yok (indirilmedi) | Hayır | Sinyal olarak K-060 kalıbıyla evet (BTC/ETH) | Yeni sağlayıcı (public), günlük PIT kolay | Düşük-orta (yükleyici + IC ölçümü) | Düşük | Dar: rejim/risk sinyali → VIX ile aynı sınıf (h47 kıyas bandı); IC ön koşulu şart |
| H | **İkinci varlık sınıfı** (hisse/ETF/vadeli) | Yok; FX yapıldı (R3-R6): 0/7 + finansman BLOCKED | FX evet | Motor takvim-farkında (R4) | Broker/lisans/PIT üyelik spike'ı (K-053) | Yüksek (veri bütçesi) | Orta (PIT üyelik) | Bilinmiyor; FX deneyimi: aynı aileler aynı sonucu verdi |

**Okuma.** Mevcut veriyle **hemen** ölçülebilen tek şey A ve G'nin IS IC ön koşulu (ucuz, çekiliş değil);
ama ikisi de K-068 sınıfına (kıyas-üstü filtre, long-only) girer ve bu sınıf 9 çekilişte + h62'de
kapandı — IC geçse bile h62 örneği "IC ≠ kıyas-üstü" dedi. **Getiri mekanizması gerçekten farklı** olan
tek hat B (carry) ve ona bağlı C; ikisinin de kilidi veri değil, **K-079'daki hesap kararı**. D/E/F veri
sınıfı hatları ileriye dönük toplama ister (aylar-yıllar) ve sonunda yine A sınıfı bir kullanım bulur.

## 6. Mevcut mimariye uygunluk tablosu

| Hat | Motor (1h, PIT, takvim) | Sinyal sözleşmesi (`Yon`, `target_exposure ≤ 1`) | Kurma/risk (K-033, K-057) | Execution/OMS (K-008, K-046) | Veri katmanı | Değişiklik boyutu |
|---|---|---|---|---|---|---|
| A cross-asset filtre | uyumlu (makro yolu var) | uyumlu | uyumlu | uyumlu | FX→özellik hizası küçük | **küçük** (1 yükleyici kancası + IC aracı) |
| B carry | uyumlu (mark/funding/premium hizalı) | **kırılır** (çift bacak, nötr pozisyon) | **genişler** (kaldıraç, likidasyon mesafesi, bacak dengesi) | **genişler** (perp venue, 4 taraflı mutabakat, kill switch sırası) | var; fee/MMR eksik | **büyük** (mimari, K-008/033/046/057 yeniden açılır) |
| C short/olay | uyumlu | kırılır | genişler | genişler | var | büyük (B ile aynı) |
| D mikroyapı | **uyumsuz** (1m motor yolu tek sembol) | uyumlu | uyumlu | uyumsuz (maliyet modeli 1m) | yok, ileriye toplama | büyük |
| E on-chain | uyumlu (K-060 günlük PIT kalıbı) | uyumlu | uyumlu | uyumlu | yok, sağlayıcı + bütçe | orta |
| F haber/LLM | uyumlu | uyumlu | uyumlu | uyumlu | yok, PIT arşiv | orta-büyük |
| G opsiyon IV | uyumlu (K-060 kalıbı) | uyumlu | uyumlu | uyumlu | public, küçük yükleyici | küçük-orta |
| H ikinci sınıf | uyumlu (R4) | uyumlu | uyumlu | venue adaptörü | yok, spike | büyük |

## 7. Önerilen sonraki araştırma hattı

**Yok — bugün hiçbir hat açılmıyor.** Gerekçe: küçük değişiklikle başlayabilen hatlar (A, G) mekanizma
olarak tükenmiş sınıftadır (§4, §5); mekanizması farklı olan hat (B) altyapı değil **karar** kilitli
(K-079/2: vadeli hesap açılmıyor) ve o karar bu dokümanın yetkisinde değil. Kilit açılmadan B'ye
altyapı yazmak "boşuna altyapı" (K-107 ilkesi); kilit kapalıyken A/G'ye çekiliş harcamak defteri
büyütüp eşiği yükseltmekten başka şey yapmaz.

**Koşullu öneri (yalnız Scryne "K-079 kilidi açılsın" derse):** Hat B, en az altyapıyla —
1. `tools/faz16_hat1_ikinci_tavan_kismi.py`'yi doğrulanabilir taker fee + MMR ile tam koştur (araç var,
   kod yok); kural K-079/6: tavan ≥ 1,04 ∧ DD ≤ %25 değilse hat kapanır, program açılmaz.
2. Geçerse K-051 programı (bütçe 1-2) — ama önce K-008/K-033/K-046/K-057'nin çift-bacak için yeniden
   yazılması ayrı karar paketi (R9'a bağlı; bu bir R7 işi değil).

## 8. Gerekli ön koşullar (hangi hat için)

| Ön koşul | Hat | Kim / nasıl | Durum |
|---|---|---|---|
| Vadeli hesap → perp taker fee kademesi + MMR (doğrulanabilir, PIT kayıt tarihi) | B, C | Scryne kararı (K-079/2 tersine) | **kapalı** |
| FX/makro → kripto IS IC ölçümü (K-068 ek şartı) | A | `r7_sinyal_gucu` kalıbı, 1 gün, çekiliş değil | yapılabilir; **önerilmiyor** (K-068 sınıfı) |
| Deribit IV yükleyici + IC | G | K-060 kalıbı, 1-2 gün | yapılabilir; önerilmiyor (aynı sınıf) |
| Emir defteri ileriye toplama | D | websocket kayıt, ≥ 6 ay | başlatılmadı; ayrı sistem |
| On-chain sağlayıcı + veri bütçesi | E | Scryne kararı (Final-Doküman bütçe) | yok |
| Haber PIT arşivi + lisans | F | Faz 13 koşulu | yok |
| Gerçek tarihli FX finansman | H (FX) | K-107 | BLOCKED |

## 9. Tek uygulanabilir sonraki adım

**Scryne'a tek soru:** K-079/2 kararı (vadeli hesap açılmıyor) korunuyor mu?
- **Korunuyorsa:** araştırma programı **askıya alınır** (yeni çekiliş yok, defter 62'de donar), R7 kapanır,
  **R8 paper koşusu kıyasla açılır** (roadmap R8: "aday olmasa bile kıyasla — kanıt üretmez ama yol test
  edilir"): `--mod paper`, `ASGARI_PAPER_GUN` fill koşulu kararı, açık pozisyonlu toparlanma ölçümü
  (25 Eylül penceresi). Bu, alfa değil operasyon kanıtı üretir ve K-050 asimetrisini bozmaz.
- **Açılıyorsa:** Hat B ikinci tavanı mevcut araçla ölçülür (§7/1); sonuç ne olursa olsun yazılır.

Bu doküman hiçbir program, çekiliş ya da kod açmaz. Kod değişikliği yok.
