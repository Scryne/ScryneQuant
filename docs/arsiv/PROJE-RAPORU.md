---
proje: ScryneQuant
tarih: 2026-09-23
type: rapor
kapsam: projenin başından (2026-09-08) bu güne kadar her şey
---
# ScryneQuant — Proje Raporu

**Tarih:** 2026-09-23 · **HEAD:** K-129 sonrası · **Test takımı:** 2.947 geçen, 1 atlanan ·
**Kod:** 177 kaynak dosyası (~51.700 satır), 129 test dosyası (~32.900 satır) · **Commit:** 221+ ·
**Karar kaydı:** 128 karar (K-001…K-129; K-112 R8 kapanışına ayrılmış)

Bu rapor projenin tamamını tek yerde anlatır: ne olduğunu, nasıl kurulduğunu, ne denendiğini, hangi kararların
neden verildiğini, bugün nerede durduğunu ve sırada ne olduğunu. Ayrıntının kanonik kaynağı `docs/Kararlar.md`
(neden), `docs/DURUM.md` (bugün) ve `docs/ROADMAP-RESET.md` (plan). Bu rapor onların yerine geçmez, özetler.

---

## 0. Bir sayfada

- **Ne:** Tek kişilik, tek hesaplık bir kripto trading araştırma + otomatik işlem platformu. Asıl çıktısı "para kazanan
  strateji" değil, **bir stratejiye güvenilip güvenilemeyeceğini ölçen altyapı**.
- **Altyapı çalışıyor ve kanıtlı:**
  - Veri, backtest, risk motoru, paper/testnet/shadow, kill switch, toparlanma, promotion zinciri ve audit kurulu.
  - Her biri cevabı bilinen girdiyle sınandı.
  - 2.947 otomatik test var.
- **Strateji tarafı: promotion'u geçen strateji yok.**
  - 63 hipotez denendi: tek sembol TA, funding, kesitsel, makro, portföy kurma, FX, zaman serisi trend.
  - Sonuçlar şans dağılımından ayırt edilemedi. En iyi OOS Sharpe 0,46, kapı 1,04.
  - Bu bir "alfa yok" iddiası değil. Denenen veri ve hipotez kapsamında kanıt çıkmadı.
- **Hedef değişti (K-125):**
  - Eski hedef: "piyasayı yenen alfa makinesi".
  - Yeni hedef: "riski yönetilen sistematik yatırım". Piyasaya kurallı maruziyet sağlamak ve büyük düşüşlerde riski
    azaltmak.
  - Bunun için ayrı ve katı bir promotion protokolü yazıldı (RYPP). B fazı olarak zincire bağlandı ve kapandı
    (K-126…K-128).
- **Canlı:**
  - Bot 2026-09-23'ten beri gerçek borsada iki koşuda çalışıyor. Testnet'te sanal parayla gerçek emir veriyor,
    shadow'da gerçek hesabı salt okuyor.
  - **Mikro pilot** (100 USDT, 10 USDT kayıpta otomatik durma) 7 günlük temiz gösterimden sonra açılabilir:
    en erken **~2026-09-30** (K-129).
  - Pilotun alfa iddiası yok. Amacı gerçek parayla emir, mutabakat ve kaymayı ölçmek.
- **Sırada:** C fazı. Kriptoda tek, ön kayıtlı, risk yönetimli bir trend adayı RYPP'den geçirilecek.

---

## 1. Proje nedir, hedef nasıl değişti

### 1.1 Başlangıç (v1, 2026-09-08)

BTC/USDT spot verisini güvenilir toplayan, kural tabanlı stratejileri deterministik backtest eden, maliyeti ve kaymayı
hesaplayan, risk kurallarını uygulayan ve aynı stratejiyi paper trading'de koşturan bir platform. Faz 0-7 kuruldu.

**Sonuç:** 38 hipotez denendi, hiçbiri kapıları geçmedi. Maliyet sıfır varsayılsa bile geçmedi (K-045). Tek sembollü
yönlü arama kapandı.

### 1.2 Vizyon v2 (2026-09-12, K-048)

- Çok enstrüman: kripto evreni, hayatta kalma yanlılığı olmadan.
- Çok bilgi kaynağı: fiyat, türev, makro, olay.
- Point-in-time doğru veri, portföy kurma, arama sayısını fiyatlayan program sistemi.
- İkinci varlık sınıfına açılabilirlik.
- Çekirdek ve değişmez kurallar aynen kaldı.

### 1.3 Denetim ve yeniden planlama (2026-09-20, ROADMAP-RESET)

W0-W8 denetim belgeleri beş şey söyledi:
1. Altyapı çalışıyor, darboğaz o değil.
2. Tekrar üretilebilirlik kırık, önce o düzelmeli.
3. Araştırma uzayı mevcut eylem uzayında kapalı.
4. Çok varlık için model sıfırdan değil, ayrıştırmayla kurulur.
5. Canlıya giden yolda eksik olan strateji değil, üç kod kalemi ve insan kararları.

Faz 0-16 tarihsel kaldı. Aktif plan R0-R15 fazları oldu.

### 1.4 Hedef yeniden tanımı (2026-09-23, K-125)

- **Yeni amaç:** piyasayı sürekli yenmek değil. Önceden tanımlı risk kurallarıyla sistematik maruziyet sağlamak, büyük
  düşüşlerde riski azaltmak, bunu ölçülebilir ve otomatik yapmak.
- **Faz sırası:**
  - A: sistem gösterimi + R8.
  - B: RYPP.
  - C: kripto strateji.
  - D: paper/shadow strateji gösterimi.
  - E: gerçek para.
- Alfa yolu (12 kapı) aynen duruyor. Yeni yol onun yerine geçmez, yanına eklenir.

### 1.5 "Çalışan bot" önceliği (2026-09-23, K-128/K-129)

Scryne'ın kararı: "artık elimde çalışan bir trade bot'umun olmasını istiyorum … adımları biraz düşür". Buna göre:
- B fazı tek kararla kapatıldı.
- Mikro pilot promotion, R8 ve 14 gün şartından ayrıldı.
- Para güvenliği (tavanlar, risk motoru, elle onay) ve istatistik eşikleri gevşetilmedi.

---

## 2. Zaman çizelgesi

| Tarih | Olay | Karar |
| --- | --- | --- |
| 2026-09-08 | Proje kuruldu: fikir, denetim, final doküman, roadmap; temel mimari kararlar | K-001…K-018 |
| 2026-09-08→10 | Veri katmanı, maliyet kalibrasyonu, indikatörler, backtest motoru, strateji izolasyonu | K-020…K-029 |
| 2026-09-10→11 | Promotion kapıları, risk motoru, al-tut kıyası, operasyonel state, gözlem modu, dashboard | K-019, K-030…K-038 |
| 2026-09-11 | Hipotez defteri + ön kayıt; emir kimliği ve ağ hatası sınıfları | K-039…K-041 |
| 2026-09-11→12 | Funding programı; çoklu test eşiği 1,02; tek sembol yönlü arama kapandı | K-042…K-047 |
| 2026-09-12 | Vizyon v2 | K-048…K-054 |
| 2026-09-13→16 | Çok enstrümanlı motor, PIT evren arşivi, makro stres engeli, Jev, host, kill switch | K-055…K-066 |
| 2026-09-16→19 | Evren programları (kesitsel, türev, makro, konumlanma, kurma) → hepsi kapandı | K-067…K-077 |
| 2026-09-20 | Denetim, ROADMAP-RESET; alfa keşif boşluğu denetimi; veri kimliği tarihe sabitlendi | K-078…K-082 |
| 2026-09-20→21 | R2 enstrüman modeli, R3 FX veri katmanı, R4 motor genelleştirme | K-083…K-097 |
| 2026-09-21→22 | R5 FX maliyet/kıyas, R6 FX alfa araştırması (FAIL), R7 portföy kurma (FAIL) | K-098…K-110 |
| 2026-09-22 | Araştırma askıya alındı; R8 operasyon koşusu tasarlandı; execution altyapısı; mikro pilot tanımı | K-111, K-113…K-115 |
| 2026-09-23 | Denetim ve pozitif kontrol: kapılar iyi stratejiyi de reddediyordu → yeniden tasarlandı | K-116…K-119 |
| 2026-09-23 | Zaman serisi trend (h63) elendi; gerçek para iki hükme bağlandı; gösterim başladı | K-120…K-122 |
| 2026-09-23 | Vadeli long/short tavanı; hisse/sektör IS ölçümü; hedef değişti (RYPP) | K-123…K-125 |
| 2026-09-23 | RYPP zincire bağlandı; B-3 veri yolu; B kapandı; pilot 7 güne bağlandı | K-126…K-129 |
| 2026-09-25 | R8 gözlem koşusu başlıyor (host-1, 14 gün) | K-111 |
| ~2026-09-30 | Mikro pilot en erken açılış | K-129 |

---

## 3. Mimari ve teknoloji

### 3.1 Stack

| Katman | Seçim | Not |
| --- | --- | --- |
| Dil | Python 3.12 | `uv` + `uv.lock` ile kilitli (K-022) |
| Veri işleme | pandas, numpy, pyarrow | Polars alınmadı (ölçülmüş darboğaz yok) |
| Tarihsel veri | Parquet (zstd, deterministik) | Dosya hash'i veri kimliği (K-009, K-011) |
| Operasyonel state | SQLite (WAL) | K-034; PostgreSQL ölçüme bağlı |
| Backtest | Kendi event-driven motoru | Backtest = paper = live, tek kod yolu (K-001, K-057) |
| Borsa | CCXT + Binance spot adaptörü | Strateji borsaya erişemez (K-003) |
| Doğrulama | Pydantic v2 | Sinyal/config/veri sözleşmeleri |
| Zamanlama | Windows Task Scheduler (`tools/*.ps1`) | Celery/Redis yok |
| API / pano | FastAPI (salt okunur) + Vite/React/TS/Tailwind | K-036; `apps/web/` |
| Audit | SQLite, zincir hash'li, append-only | `risk/audit.py` |
| Test / lint | pytest, ruff | CI: GitHub Actions (`pytest -m "not network"`) |
| AI | TypeSafe (Jev), yalnız gölge/ölçüm | İşlem katmanı import edemez (K-074) |

### 3.2 Akış

```
Kaynaklar → Ingestion/Doğrulama → Kanonik Veri (PIT) → Feature/Evren → Rejim
  → Strateji (Sinyal niyeti) → Portföy Kurma → Risk Motoru (Onaylı niyet)
  → OMS → Execution → Venue → Fill/PnL → Post-trade → Araştırma geri beslemesi
```

Modüler monolit (K-052). Paketler: `common` (zaman, hash), `data` (indirme, kalite, PIT, FX, French), `features`,
`strategy` (20 kütüphane stratejisi), `backtest`, `risk` (limitler, promotion, audit), `portfolio`, `oms`,
`execution` (mod makinesi, live gate, hat, hazırlık), `exchange` (imzalı canlı emir), `research` (kapılar, çoklu
test, defter, RYPP), `live` (paper/gözlem, toparlanma, API), `trader`, `jev`, `cli` (`sq` komutu).

### 3.3 Değişmez kurallar (17)

Tercih değil, testle korunan kısıtlar. Bir görev bunları ihlal ediyorsa görev yanlıştır.

1. Strateji I/O yapamaz (K-003).
2. Strateji geleceği göremez (K-002).
3. Sinyal risk motorunu atlayamaz.
4. Zaman UTC epoch ms; bar zamanı açılıştır (K-005).
5. Dolum bir sonraki barın açılışındadır (K-004).
6. Kayma her zaman aleyhte (K-007).
7. Aynı girdi aynı çıktıyı verir (K-009).
8. Promotion kapıları kaldırılamaz ve sayısaldır. Tek istisna K-115 mikro pilotu (K-010, K-018).
9. Kendi hesabı, kendi parası (K-014).
10. Engelleyen katman risk motorunun dışında olabilir, izin veren olamaz (K-037).
11. Kaç hipotez denendiği sayılır (K-039).
12. Toparlanma geri yükleme değil, yeniden üretimdir (K-038).
13. Evren de geleceği göremez (K-052).
14. Enstrüman kimliği ticker değildir (K-052).
15. Bar olmayan gözlemde kesme `available_time`'a göredir (K-052).
16. Otomasyon asimetriktir: riski azaltan otomatik, izni artıran kapı + elle onay (K-050).
17. AI yetkisi sınırlıdır (K-049).

---

## 4. Veri

| Depo | İçerik | Not |
| --- | --- | --- |
| `data/market/` | Binance spot REST, 2021-06→ | İlk kaynak; karıştırılmaz (K-056) |
| `data/evren/` | Binance arşivi 2017-08→, PIT evren tablosu `27b7a16ed0ed` (429 sembol, delist dahil) | Hayatta kalma yanlılığı ölçüldü: ayda medyan %18 (Spike 6). Yeni tek sembollü hipotezler burayı kullanır (K-119) |
| `data/turev/`, `data/funding/` | Funding, premium/basis, mark, OI/taker metrikleri | PIT; yönlü sinyal olarak denendi, kapandı |
| `data/makro/` | FRED/ALFRED vintage'lı: VIX, NFCI, DGS10, DTB3, HY spread, dolar endeksi | PIT (NFCI gözlemlerinin %99,6'sı revize → vintage şart) |
| `data/fx/` | FXCM M1 bid/ask, 21 çift | Yalnız araştırma; finansman proxy olduğu için promotion'a kapalı (K-101/K-107) |
| `data/duyuru/` | Borsa duyuruları | Delist/olay araştırması; long-only'de işlenemedi |
| `data/bagimsiz/` | French ABD 12 sektör + piyasa, günlük; iki vintage | B-3 bağımsız doğrulama (K-127/K-128). Kanonik kimlik `2448dddc…` (2004-06→2026-07) ve `10256f91…` (2004-06→2017-05) |

- **Kalite:** Her bar kalite bayrağı taşır. `ok` olmayan barda karar verilmez, dolum yapılmaz (K-024, K-028).
  Boşluk sentetik barla doldurulmaz.
- **Kimlik:** Veri seti SHA-256'sı hipotez kimliğinin parçası. `bitis_gun` ile tarihe sabitlenir ve geri sarılabilir
  (K-080).

---

## 5. Araştırma ve doğrulama sistemi

Bu projenin kalbi. Amaç, "yeterince deneyip birini geçirme" yolunu kapatmak.

### 5.1 Hipotez defteri ve programlar

- **`docs/Hipotez-Defteri.jsonl`** (K-039) append-only. Her hipotez sonuçtan **önce** kaydedilir. Kimlik: strateji,
  timeframe, veri hash'i, ızgara, seçim yöntemi, evren, portföy, rejim ve (K-127'den beri) protokol. Bugün 63 satır.
- **Araştırma programları** (K-051, `docs/Arastirma-Programlari.jsonl`): gerekçe, ölçülmüş kaynak farkı, azami
  çekiliş bütçesi ve durma kuralı önceden yazılır. Bütçe aşılamaz.
- **Gizli tekrar dedektörü** (Jev, K-061): benzer hipotezi uyarır, engellemez.

### 5.2 Çoklu test düzeltmesi

Her yeni çekiliş kapıyı yükseltir. `oos_sharpe` eşiği şöyle ölçüldü:
- K-044: 31 çekilişte 1,02.
- K-064/K-071/K-081: 41-45 çekilişte 1,04, sabit.
- 63 çekilişte %5 sınırı 1,0039; mevcut 1,04'ün yanlış pozitifi 0,042.

### 5.3 Alfa yolu: 12 kapı (K-019 → K-054 → K-119)

| Kapı | Eşik |
| --- | --- |
| `oos_suresi` | asgari OOS süresi |
| `oos_sharpe` | ≥ 1,04 (çoklu test) |
| `oos_is_orani` | ≥ 0,5 |
| `wf_katman_basari` | ≥ 0,6 |
| `parametre_kararliligi` | ≤ 0,35 |
| `asgari_islem` | ≥ 30 |
| `max_drawdown` | ≤ 0,25 |
| `stres_dayanikliligi` | OOS stres Sharpe oranı ≥ 0,5 |
| `pbo` | CSCV zarar olasılığı ≤ 0,05 |
| `parametre_perturbasyonu` | komşu koruma ≥ 0,80 |
| `rejim_kararliligi` | ≥ 0,685 |
| `evren_dayanikliligi` | ≥ 0,75 |

Mutlak engeller: `dirty`, `data_quality_warning`, `gecici_maliyet_modeli`, `leak_riski`.

**Kritik ders (K-117 → K-119):** 2026-09-23'teki pozitif kontrol gösterdi ki eski kapılar yalnız yanlış pozitife göre
ayarlanmıştı ve **gerçek bir üstünlüğü de geçirmiyordu**:
- %65 isabetli "kahin" strateji 0/20 geçti.
- Güçlü gömülü trend 0/36 geçti.

Kapılar cevabı bilinen veride iki yönlü (null + güç) yeniden tanımlandı:
- Null testinde 0/60 geçti.
- Güçlü sentetik evrende 5/6 geçti.
- %65 kahin 17-20/20 geçti.

Kalıcı kural: yeni ya da değişen her kapı iki yönlü doğrulanır. Gerçek defterde sonuç değişmedi.

### 5.4 Risk yönetimli yol: RYPP (K-125 → K-128)

**Soru:** Strateji düşüşü anlamlı azaltıp kabul edilebilir getiriyi koruyor mu? Bunu zamanlamayla mı yapıyor, yoksa
yalnız daha az risk alarak ya da şansla mı?

| Kod | Koşul |
| --- | --- |
| P1 | Düşüş azaltımı ≥ %25 (kıyasa göre) |
| P2a / P2b | CAGR ≥ kıyasın yarısı; MAR (CAGR/düşüş) ≥ kıyasınki |
| **P3** | **Plasebo:** stratejinin kendi maruziyet takvimi zamanda kaydırılır (aynı işlem sayısı, süre, maruziyet, maliyet). Gerçek takvim plasebonun (1 − 0,05/k) persentilini geçmeli |
| S1 | 2x maliyette MAR korunur |
| R1 / R2 / R3 | Başlangıç tarihi, alt dönemler, tek olaya bağımlı olmama |
| B | Eşleşik blok bootstrap: düşüş azaltımı %5 persentili > 0 ve P(MAR üstün) ≥ 0,80 |

**Üç sonuç:** PASS / FAIL / INCONCLUSIVE. Eksik kanıt PASS değildir, yetersiz veri FAIL değildir.

Kilitler:
- **Kanıt:** Hüküm raporlanan durumdan değil satırlardan yeniden türetilir. Tutarsız, eşiği farklı ya da eksik kanıt
  kurulmaz (K-126).
- **B-3 (kirlenme):** Kripto OOS'una 18 çekiliş baktı. Bu yüzden aynı donmuş kural bu projede hiç bakılmamış bir veride
  de test edilir: French ABD sektörleri, 2004-06 sonrası. Veri revize edildiği için (PIT değil) iki vintage'da da
  FAIL olmamalı (K-127/K-128).
- **k (çoklu test):** RYPP programının açılışta yazılan bütçesi. Promotion k'yı seçemez (K-128).
- **Alfa yolu byte-aynı kaldı.** Protokoller karışamaz: alfa kanıtı RYPP yoluna, RYPP kanıtı alfa yoluna geçemez.

### 5.5 Promotion zinciri

```
backtest → kalite_kontrol → out_of_sample → risk_incelemesi → paper (30 gün) → live_adayi → elle_onay → live
```

- Adım adım ilerler, atlanamaz.
- Ölçülemeyen aşama geçilmiş sayılmaz.
- Elle onay makinece verilemez ve gerekçe ister.
- Her satır zincir hash'li ve audit'e bağlı (K-082).
- `out_of_sample` ölçütünü protokol seçer (alfa / RYPP); diğer aşamalar ortak (K-126).

---

## 6. Strateji sonuçları: 63 çekiliş

| Program / dönem | Çekiliş | Sonuç | Özet |
| --- | --- | --- | --- |
| Program öncesi (tek sembol BTC, 6 aile + funding) | 38 | 0 geçti | Maliyet sıfırken bile kapının yarısı; sinyal OOS'ta çöküyor (K-044, K-045) |
| `kesitsel_fiyat` | 4 | 0 | Kesitsel momentum/ters kıyası geçmedi |
| `turev_evren` | 4 | 0 | Funding/basis/OI dışlama katmanı, kıyas bandı |
| `makro_rejim` | 2 | 0 | VIX/NFCI stres engeli (h47/h48), kıyas bandı |
| `konumlanma_evren` | 2 | 0 | Aile kapandı (K-068) |
| `kurma_evren` | 2 | 0 | 1/σ, oynaklık hedefi: genelleşir, Sharpe üretmez |
| `fx_fiyat`, `fx_ortalama_donus`, `fx_oynaklik` | 7 | 0 | FX alfası yok; tekrar turunda OOS negatif (K-102…K-106) |
| `portfoy_kurma` | 2 | 0 | Korelasyon budaması, turnover (K-108) |
| `kesit_oynaklik` | 1 | 0 | Düşük oynaklık IC t≈7 ama kıyas altı (K-109) |
| `kripto_zs_trend` | 1 | 0 | h63: OOS Sharpe −0,54, kıyas 0,30; 2024-26 dönüşlerinde testere (K-121) |

**Toplu okuma (K-110, R7 kapanış envanteri):**
- 48 ölçülebilir çekilişin gerçekleşen OOS Sharpe'ı, kendi rastgele zamanlanmış null dağılımının **medyan
  persentili 0,45-0,50**. Yani şanstan ayırt edilemiyor.
- IS'te 11 fiyat/hacim sinyalinden 10'unda sıralama gücü yok.
- En iyi OOS Sharpe 0,46; null'un %5 sınırının da altında.

**Tekrar tekrar görülen üç bulgu:**
1. Oynaklık/risk bilgisi maruziyeti düşürür, Sharpe'ı artırmaz.
2. Fiyat sinyalinden seçim, IS'teki üstünlüğü OOS'a taşımaz.
3. Tek OOS başarısı tekrarda tutmaz.

**Tükenen aileler (tekrar denenmez):** tek sembol TA, funding yönlü, kesitsel momentum/ters/düşük oynaklık, kıyas-üstü
dışlama, rejim/Jev yönü, kurma katmanı, FX, kripto evreninde zaman serisi trend.

**Diğer ölçümler:**
- **Vadeli long/short (K-123):** Short bacak IS'te her pencerede risk-ayarlı getiriyi düşürüyor; vadeli hesap
  gerekçesi yok.
- **Carry (K-116):** BTC funding son 12 ayda %3,4/yıl, risksiz faizin altında.
- **Hisse/sektör trendi (K-124, yalnız IS):** Trend, al-tut'a 0,1-0,17 Sharpe ekliyor; riski iyileştiriyor, getiriyi
  değil. Bu bulgu K-125'teki hedef değişikliğini besledi.

---

## 7. Risk, execution ve canlı yol

### 7.1 Risk motoru (`config/risk.json`)

- **Limitler:** işlem başı risk, günlük zarar limiti, drawdown limiti (0,20), ardışık kayıp (10) ve cooldown (24 bar),
  azami maruziyet (0,30), brüt maruziyet, volatilite eşiği, ters hareket (ATR).
- Her limit kaynağını ve gözden geçirme koşulunu taşır (K-033).
- Onay bir tip ve mühürdür; execution'a giden tek yol onaylı niyettir (K-032).

### 7.2 Kill switch ve toparlanma

- Spot kill switch: yeni girişi durdurur, açık pozisyonu zorla kapatmaz (K-008).
- Çıkış yalnız elle ve gerekçeyle (`sq risk serbest`).
- Süreç dışı kill: işaret → süreç → emirler (K-065). Tatbikat yapıldı ve geçti.
- Toparlanma diskten okunanı bağımsız kaynaktan yeniden üretir; uyuşmazlıkta koşu durur (K-038).

### 7.3 Emir güvenliği

- Emir kimliği içerikten türer, gönderimden önce yazılır. `UNKNOWN` emir yeniden gönderilmez (K-040).
- Ağ hataları üç sınıfa ayrılır (K-041).
- Mutabakat üç taraflıdır (K-046). İptalde maruziyetin var olduğu varsayılır (K-047).
- Canlı emir katmanı yazmada yeniden denemez (K-117 denetimi).
- K-118 denetimi: cooldown canlı yolda hiç çalışmıyordu, düzeltildi.

### 7.4 Modlar ve live gate

- **Mod makinesi (`execution/mod.py`):** DISABLED → PAPER → SHADOW → TESTNET → LIVE_PENDING_APPROVAL → LIVE. Her geçiş
  kapı raporu ister.
- **Live gate (`execution/canli_kapi.py`):** `CanliYetki` üreten tek yer.
- **İşlem anahtarı:** spot işlem açık; çekim/transfer/margin/futures kapalı; IP kısıtlı olmak zorunda.

### 7.5 Gerçek para kuralları

| Kademe | Ne istiyor |
| --- | --- |
| **Mikro pilot (Kademe 1)** | K-115/K-116/K-129. Sermaye ≤ 100 USDT, kayıp ≤ 10 USDT (kodda sabit). Strateji `sma_kesisim` BTCUSDT 1h, alfa iddiası yok. Şartlar: yeşil testler + testnet/shadow gösterimi 7 gün temiz + kill tatbikatı + işlem anahtarı denetimi + hesap değeri 90-150 USDT + `sq execution onayla` (elle) |
| **Sermaye büyütme (Kademe ≥ 2)** | K-122 aynen: sistem hazır (14 gün gösterim + R8 PASS + kill + testler) **ve** strateji hazır (promotion `live_adayi`) |

### 7.6 Operasyon

- **Gösterim (2026-09-23 →):**
  - `gosterim-testnet`: sanal para, gerçek borsa emri.
  - `gosterim-shadow`: gerçek hesap, salt okunur.
  - Gözetmen `tools/gosterim_gozetmen.ps1` ve zamanlanmış görev 10 dakikada bir.
  - Durdurmak için: `runs/gosterim/DURDUR`.
- **R8 (K-111):** `r8-kiyas` gözlem koşusu, host-1, 2026-09-25'ten itibaren 14 gün. Kriterler dondurulmuş
  (`config/r8_kriterler.json`). Operasyon kanıtı üretir, alfa değil.
- **Host:** Yerel Windows makinesi (K-063; VPS kararı askıda).
- **Alarm kanalı:** ntfy.sh (K-066).

---

## 8. Jev (TypeSafe)

- **Rolü:** Metnin ne dediği konusunda güçlü, dünyanın ne yapacağı konusunda değil.
- **Yön tahmini ölçüldü (K-074…K-077):**
  - 50 sembol, yayın sonrası pencere, isabet %49,0.
  - Rejim-koşullu oracle tavanı bile yetersiz.
  - İşlem kararına bağlanmaz.
- **Yürürlükteki rolü:** araştırma yönetişimi (gizli tekrar dedektörü) ve gölge ölçüm.
- **İzolasyon:** İşlem katmanı `jev`/`typesafe` import edemez (test). Jev'den sinyal üreten fonksiyon yok.
- **Değerlendirilecek:** duyuru/delist metni için yalnız **engelleyen** bir güvenlik vetosu. Ayrı bir K ister.

---

## 9. Karar kataloğu (K-001…K-129)

Her satır kararın özüdür. Ayrıntı, gerekçe ve ölçümler `docs/Kararlar.md`'de.

### 9.1 Temel mimari ve kurallar (2026-09-08)

| K | Karar |
| --- | --- |
| K-001 | Tek backtest motoru, event-driven (backtest = paper = live) |
| K-002 | Stratejiye geleceği gösteren nesne verilmez |
| K-003 | Strateji katmanı I/O yapamaz |
| K-004 | Fill bir sonraki bar açılışında |
| K-005 | Zaman UTC epoch ms; bar zamanı açılış |
| K-006 | Veri kalitesi bayrakları backtest'i etkiler |
| K-007 | Maliyet modeli muhafazakâr ve açık; kayma hep aleyhte |
| K-008 | Kill switch (spot): yeni girişi durdurur, pozisyonu zorla kapatmaz, çıkış elle |
| K-009 | Kirli ağaçtan üretilen backtest promotion'a giremez |
| K-010 | Promotion kapısı MVP kapsamında; elle onay kaldırılamaz |
| K-011 | Parquet (tarihsel) + SQLite/PostgreSQL (operasyonel) |
| K-012 | Arayüz Faz 6'da; öncesi CLI |
| K-013 | ML ve LLM v1 kapsamı dışında |
| K-014 | Yalnız kendi hesabı, kendi parası (hukuki sınır) |
| K-015 | Binance erişimi: coğrafi engel yok, testnet ayakta |
| K-016 | Fee/slippage kesin sayıları |
| K-017 | Birincil timeframe 1h |
| K-018 | Operatör yargısı yerine makine eşiği |

### 9.2 Veri, maliyet, motor (2026-09-08→10)

| K | Karar |
| --- | --- |
| K-020 / K-021 | Kayma veriden kalibre edilir, yürütme penceresindeki fiyat hareketinden |
| K-022 | `uv` + `uv.lock` |
| K-023 | Tarihsel klines ccxt ham ucundan |
| K-024 | Kalite bayrağı tekil; boşluk sentetik barla doldurulmaz |
| K-025 | Maliyet `config/maliyet.json`'da; kalibre edilmemiş model kendini işaretler |
| K-026 | İndikatör konvansiyonu TA-Lib; referans dondurulur |
| K-027 | Strateji izolasyonu izin listesiyle |
| K-028 | `ok` olmayan barda karar ve dolum yok |
| K-029 | Backtest referansı kapalı formülle çapraz doğrulanır |

### 9.3 Kapılar, risk, operasyon temeli (2026-09-10→11)

| K | Karar |
| --- | --- |
| K-019 | Promotion kapılarının sayısal eşikleri |
| K-030 | Her karşılaştırmada al-tut kıyası |
| K-031 | Strateji sinyalinin kabul edildiğini varsayamaz |
| K-032 | Risk onayı bir tip, mühür ve kesme noktası |
| K-033 | Her risk limiti kaynağını ve gözden geçirme koşulunu taşır |
| K-034 | Operasyonel state SQLite (WAL) |
| K-035 | Gözlem modu: canlı veride koşar ama kanıt üretemez |
| K-036 | Dashboard: Vite + React SPA, FastAPI servis eder |
| K-037 | Engelleyen katman risk motoru dışında olabilir; izin veren olamaz |
| K-038 | Toparlanma yeniden üretimdir |
| K-039 | Hipotez sayılır, ön kayıt zorunlu |
| K-040 / K-041 | Emir kimliği içerikten; ağ hatası üç sınıf; imza zamanı borsadan |
| K-043 | Planlı duruş kesinti değildir (bayrak dosyası) |
| K-046 / K-047 | Üç taraflı pozisyon mutabakatı; iptalde maruziyet var sayılır |

### 9.4 İlk araştırma sonuçları (2026-09-11→12)

| K | Karar |
| --- | --- |
| K-042 | Funding bilgi kaynağı olarak: üç hipotez, tek tur |
| K-044 | Çoklu test ölçüldü: eşik 0,50 → 1,02 |
| K-045 | Maliyet duvarı bağlayıcı değil; tek sembollü yönlü arama kapandı |

### 9.5 Vizyon v2 ve çok enstrüman (2026-09-12→16)

| K | Karar |
| --- | --- |
| K-048 | Vizyon v2: kapsam genişler, çekirdek durur |
| K-049 | AI/ML yetki sınırları; LLM eğitim verisi look-ahead kaynağı (`leak_riski`) |
| K-050 | Otomasyon asimetrik |
| K-051 | Tek defter; her program ön kayıtlı bütçeyle |
| K-052 | Tek kod yolu çok enstrümana genişler; monolit korunur |
| K-053 | İlk genişleme kripto içinde |
| K-054 | Doğrulama kapıları v2: dört yeni kapı |
| K-055 | Faz 6 kapanır; 30 günlük koşu sürekli host ister |
| K-056 | Arşiv ikinci veri kaynağı, karıştırılmaz; evren PIT |
| K-057 | Çok enstrümanlı motor tek motor; kurma öneri, risk onay |
| K-058 | Kapı v2 eşikleri null'dan; program kaydı zorunlu; `leak_riski` mutlak |
| K-059 | Barı biten sembolde pozisyon 48 bar sonra sıfır değer |
| K-060 | Makro stres engeli: günlük PIT, ertesi gün görünürlük |
| K-061 | Gizli tekrar dedektörü (Jev), uyarır, engellemez |
| K-062 / K-063 | Sürekli host: VPS kararı askıda, şimdilik yerel Windows |
| K-064 | Çoklu test null'ında sızıntı payı; eşik 41 çekilişle 1,04 |
| K-065 | Süreç dışı kill switch |
| K-066 | Host sırları; alarmlar ntfy.sh |

### 9.6 Evren programları ve Jev (2026-09-16→19)

| K | Karar |
| --- | --- |
| K-067 | Jev rolü: eleme ve ileriye dönük sınıflandırma; sinyal yok |
| K-068 | Kıyas-üstü tek dışlama ailesi kapandı |
| K-069 | Faz 14 dayanıklılık kriteri 30 → 8 gün; promotion kapısı değişmedi |
| K-070 | `agirliklar()` tavanı düzeltildi; kırpılan pozisyon kilitlenir |
| K-071 | Eşik 43 çekilişle ölçüldü; 1,04'te kalır |
| K-072 | Kıyas ayarlanmaz; sıfır noktası kuralla sabit |
| K-073 | Araştırma/canlı risk motoru karşılaştırılabilirlik uyuşmazlığı |
| K-074…K-077 | Jev yalnız gölgede; yayın tarihi kesim üst sınırı; yön isabeti %49; oracle tavanı yetersiz → Jev karar katmanı açılmaz |

### 9.7 Denetim ve yeniden yapılanma (2026-09-20→21)

| K | Karar |
| --- | --- |
| K-078 | Alfa keşif boşluğu denetimi: bir hat kapandı, bir hat bilgilendirici |
| K-079 | Carry ikinci tavanı veri eksikliğiyle bloke; vadeli hesap açılmıyor |
| K-080 | Veri kimliği tarihe sabitlenir (`bitis_gun`, geri sarım) |
| K-081 | Eşik 45 çekilişle ölçüldü; 1,04 korunur |
| K-082 | Promotion kaydı zincir hash'li ve audit'e bağlı |
| K-083…K-086 | Enstrüman v2 modeli; enstrüman başı maliyet; canlı evren kimliği; R2 kapandı |
| K-087…K-092 | FX veri katmanı (FXCM), fx-5x24 takvimi, PIT FX evreni; R3 kapandı |
| K-093…K-097 | Motor genelleştirme: takvim, bid/ask dolum, spread, finansman, FX adaptörü; kripto yolu bit-aynı; R4 kapandı |

### 9.8 FX ve portföy araştırması (2026-09-21→22)

| K | Karar |
| --- | --- |
| K-098…K-101 | FX maliyet modeli, hacimsiz FX kıyası, veri kapsamı; tarihli rollover yok, proxy geçici |
| K-102…K-106 | FX alfa araştırması: fiyat, ortalama dönüş, oynaklık → 0/7; R6 FAIL |
| K-107 | FX finansman penceresi genişletme bloke; R7 kripto evreninde |
| K-108 / K-109 | Portföy kurma 0/2; kesitsel düşük oynaklık kıyas altı |
| K-110 | R6+R7 kapanışı: hat tükenmiş okuması desteklendi; yeni alfa hattı açılmıyor |

### 9.9 Operasyon ve canlıya hazırlık (2026-09-22)

| K | Karar |
| --- | --- |
| K-111 | Araştırma askıda; R8 gözlem koşusu kriterleri dondurulmuş |
| K-112 | (Ayrılmış: R8 kapanışı, PASS/FAIL) |
| K-113 | `oos_sharpe` yıllıklandırılmış anlamlılığı okur; `oos_suresi` ayrı kapı; eşik kaydı `config/esikler.json` |
| K-114 | Execution altyapısı kodlandı; canlı kapılar değişmedi |
| K-115 | Mikro canlı pilot: promotion'suz, kodda sabit tavan (100 / 10 USDT) |

### 9.10 Denetim, kapı yeniden tasarımı, hedef değişikliği (2026-09-23)

| K | Karar |
| --- | --- |
| K-116 | Pilot kapısı kademenin strateji + sembolüne bağlandı; carry'nin ekonomik tabanı çöktü |
| K-117 | Pozitif kontrol: kapılar iyi stratejiyi de reddediyordu |
| K-118 | Sistematik denetim: canlı yolda cooldown çalışmıyordu; look-ahead testi kayıttan; 12 kapının tamamı zorunlu |
| K-119 | Kapılar iki yönlü doğrulamayla yeniden tanımlandı; tek sembol araştırması 9 yıllık arşivde |
| K-120 / K-121 | Araştırma askısı kalktı; `kripto_zs_trend` açıldı; h63 elendi (commit'siz koşu süreç hatası kayda geçti) |
| K-122 | Gerçek para iki hükme bağlandı (sistem + strateji); 14 günlük gösterim |
| K-123 | Vadeli long/short tavanı: short bacak değer katmıyor |
| K-124 | Evren değerlendirmesi yıllıklandırma hatası (FX'te %18 şişikti) düzeltildi; hisse/sektör trendi IS ön ölçümü |
| K-125 | Hedef: riski yönetilen sistematik yatırım; RYPP |
| K-126 | RYPP promotion zincirine bağlandı; protokol türü; alfa yolu byte-aynı |
| K-127 | B-3 kuralı açık karar; P3'ün k'sı kanıta donuk; French verisi kilitli ama PIT değil |
| K-128 | B kapandı: French vintage dayanıklılığı şartıyla; k = program bütçesi; CLI hipotez sırası; eşleme sözleşmesi |
| K-129 | Mikro pilot 7 günlük gösterimle; R8 ve promotion şartı yalnız sermaye büyütmede |

---

## 10. Bugünkü durum (2026-09-23)

| Alan | Durum |
| --- | --- |
| Kod ve testler | Temiz ağaç; 2.947 test yeşil ve HEAD için kaydedildi (`sq execution test-kaydet`) |
| Roadmap | R0-R4, R6, R7, R13 ✅; R5, R8, R9 🔄; R10, R11, R14, R15 ⏳; R12 tetikli |
| Promotion | Hiçbir strateji `out_of_sample`ı geçmedi; `sma_kesisim` kalite_kontrol'de |
| Gösterim | Testnet + shadow 2026-09-23 07:31/07:38 UTC'den beri çalışıyor |
| Pilot hazırlığı | Canlı kapıda 15 kontrolün 12'si geçiyor. Kalanlar: 7 gün gösterim, işlem anahtarı, hesap değeri/bağlantı (ağ yoklaması) |
| R8 | 2026-09-25 başlıyor, 14 gün |
| C fazı | İlk program (h64 `evren_risk_kapisi`) RYPP FAIL, kapandı (K-130/K-131) — ek bölüm 14 |

---

## 11. Riskler ve bilinen sınırlar

1. **Strateji kanıtı yok.** Pilot para kazandırmak için değil, ölçmek için. Beklenen sonuç küçük bir maliyet kaybı;
   tavanı 10 USDT.
2. **Kripto OOS'u kirli (B-3).** 18 çekiliş aynı OOS'a baktı; 2025-26 düşüşü biliniyor. Plasebo ve bağımsız veri bunu
   dengelemek için var.
3. **Bağımsız veri PIT değil.** French verisi her ay revize ediliyor. İki vintage şartı revizyon riskini test ediyor,
   ama as-published tarih yok.
4. **Hindsight.** 2008, 2020 ve 2022 herkesin bildiği olaylar. Proje bağımsızlığı insan bilgisinden bağımsızlık
   demek değil.
5. **Maliyet modeli tutucu.** Taraf başı 10 + 5,3 bps. Pilotun gerçek dolumlarıyla yeniden kalibre edilecek.
6. **Gösterimin ilk saatleri.** 6 bardan 1'i kaçırıldı (sınır %2, bar sayısı arttıkça seyrelmeli). Yeniden başlatma
   tatbikatı henüz yapılmadı.
7. **Tek host.** Yerel Windows makinesi; kapanırsa koşular durur. Toparlanma var ama VPS kararı askıda.
8. **Kapsam sınırı.** Ölçülmeyenler: short/perp eylem uzayı, on-chain, emir defteri, haber arşivi, başka venue ve
   varlıklar. Sonuç "denenen kapsamda alfa bulunmadı" demektir.

---

## 12. Sıradaki adımlar

| # | Adım | Kim | Ne zaman |
| --- | --- | --- | --- |
| 1 | Gösterimi izle; yeniden başlatma tatbikatını yap; kaçırılan bar oranı %2'nin altına insin | Claude | 7. güne kadar |
| 2 | **Pilot için hazırlık:** Binance'ta işlem yetkili, çekimsiz, IP kısıtlı API anahtarı; hesaba ~100 USDT | **Scryne** | 30 Eylül'den önce |
| 3 | `sq execution hazirlik` → MİKRO PİLOT HAZIR; `sq execution preflight --hedef live --ag`; `sq execution onayla` | Scryne (onay) | ~30 Eylül |
| 4 | **C fazı:** tek ön kayıtlı RYPP programı (küçük bütçe), IS'te tasarım, dondurma, commit, OOS + iki vintage bağımsız doğrulama, tek sefer | Claude | Paralel |
| 5 | R8 kapanışı (K-112) | Claude | ~9 Ekim |
| 6 | C'den PASS çıkarsa: pilot stratejisini değiştirme kararı; sonra D (paper/shadow strateji gösterimi) | Claude + Scryne onayı | C sonrası |
| 7 | Sermaye büyütme: yalnız sistem + strateji hükümleriyle ve elle onayla | Scryne | D sonrası |

---

## 13. Nerede ne var

| Konu | Yer |
| --- | --- |
| Bugünkü durum | `docs/DURUM.md` |
| Kararlar | `docs/Kararlar.md` |
| Yol haritası | `docs/ROADMAP-RESET.md` (`docs/arsiv/Roadmap.md` tarihsel) |
| Nihai doküman / vizyon | `docs/arsiv/Final-Dokuman.md`, `docs/arsiv/Proje-Fikri-v2.md` |
| Hipotez defteri / programlar | `docs/Hipotez-Defteri.jsonl`, `docs/Arastirma-Programlari.jsonl` |
| RYPP | `docs/research/Risk-Yonetimli-Protokol.md`, `src/scryne_quant/research/risk_protokolu.py` |
| Kapılar | `src/scryne_quant/research/kapilar.py`, `kapilar_v2.py`, `config/esikler.json` |
| Promotion | `src/scryne_quant/risk/promotion.py`, `sq promotion …` |
| Canlı yol | `docs/arsiv/Execution-Runbook.md`, `execution/mod.py`, `execution/canli_kapi.py`, `execution/hazirlik.py` |
| Kademe / risk / venue | `config/kademe.json`, `config/risk.json`, `config/venue_statu.json` |
| Bağımsız veri | `src/scryne_quant/data/french.py`, `config/bagimsiz_veri.json`, `sq data bagimsiz-dogrula` |
| Ölçüm kayıtları | `docs/research/records/` |
| Tarihsel denetimler | `docs/arsiv/audit/`, `docs/Denetim*.md`, `docs/Faz-*.md`, `docs/arsiv/spikes/` |

---

## 14. Ek (aynı gün): C fazının ilk sonucu — K-130 / K-131

- **Aday (`evren_risk_kapisi`):** Kripto evren kıyası (hacimde ilk 10, eşit ağırlık, haftalık, brüt 1,0). BTC 100
  günlük ortalamasının altına inince nakde geçiyor. Pencere IS'te 50/100/200 gün arasından önceden yazılı kuralla
  seçildi; 200 gün IS'te P1'i geçemediği için OOS'a sokulmadı.
- **Ön kayıt:** Program `kripto_risk_kapisi` (bütçe 1, k = 1) ve hipotez 64 commit'lendi, sonra OOS tek sefer koşuldu.
- **Kripto OOS (2,7 yıl):**
  - Aday −%16,6, azami düşüş %59,8. Kıyas −%31,2, azami düşüş %75,7.
  - Düşüş %21 azaldı; eşik %25.
  - Zamanlama rastgele takvimden iyi değil: gerçek MAR −0,06, plasebonun %95 persentili 0,64.
  - Kazanç maruziyet düşürmekten geliyor, zamanlamadan değil.
- **Bağımsız veri (ABD sektörleri):**
  - Düşüş yarıya iniyor: %24 karşı %54.
  - 202607 vintage'ında sonuç başlangıç tarihine duyarlı.
  - 201705 vintage'ında plasebo ve 2x maliyet kalıyor.
- **Hüküm:** RYPP FAIL. Program kapandı, tuning yok.
- **Süreç ve hata:**
  - Promotion zinciri ilk kez gerçek RYPP kanıtıyla uçtan uca çalıştı ve FAIL'i kaydetti.
  - Kripto P3 hesabında bir birim hatası bulundu ve düzeltildi. Hükmü değiştirmiyor, ders kayıtta.
- **Pilot:** Bu sonuç mikro pilotu etkilemiyor; pilot `sma_kesisim` ile ~2026-09-30'da açılabilir.

---

## 15. Ek (aynı gün): Ürün kararı — K-132

- **Hedef:** Sabit risk bütçeli sistematik yatırım. Bot piyasayı tahmin etmiyor; kuralı disiplinle uyguluyor ve kaybı
  kodda sınırlıyor.
- **Ürün (`sabit_oran`):** Hesabın %50'si BTC, %50'si USDT. Oran %45-%55 dışına çıkınca yeniden dengeleniyor.
- **Risk profili:**
  - Ürüne özel ve config'den eşleniyor.
  - Genel profilden yalnız iki alanda farklı: maruziyet tavanı 0,5, işlem başı risk 0,05.
  - Diğer bütün limitler aynen; bir bekçi test bunu koruyor.
- **Geçmiş (2017-2026, beklenti değil):**
  - +%647, yıllık %24,8, azami düşüş %56.
  - Karşılaştırma: tam BTC +%1.783, azami düşüş %84.
- **Pilot:**
  - 100 USDT, 10 USDT kayıp tavanı; tavan yaklaşık %20'lik bir BTC düşüşünde tetiklenir.
  - Strateji `sabit_oran`.
  - Ürün `urun-testnet` koşusunda testnet'te gösteriliyor.
  - Açılış için işlem yetkili anahtar, hesapta ~100 USDT ve `sq execution onayla` gerekiyor.
- **Sermaye büyütme:** Operasyonel promotion ölçütü ayrı bir K ile yazılana kadar kapalı.
