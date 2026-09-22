# R7 ön koşul — FX finansman/veri penceresini genişletme: **BLOCKED** (K-107)

Tarih: 2026-09-22 (UTC). Yeni kod, yeni çekiliş, yeni proxy yok. Kaynaklar: K-088/K-090/K-091 (FXCM arşiv
derinliği), K-098/K-100 (proxy finansman, `config/finansman/`), K-101 (rollover kaynağı araştırması,
`2026-09-21-R5-fx-rollover-kaynak.md`), `tools/fx_depo_durumu.py`, bugünkü kısa yeniden tarama (§3).

## 1. Ne hazır (repo ve R3-R5 kayıtlarından)

| Parça | Durum | Kanıt |
|---|---|---|
| Fiyat verisi indirici (FXCM MarketData, haftalık M1 bid/ask → 1h Parquet, checksum, `--bitis-gun`) | **hazır** | K-088/K-090, `sq data fx-al` |
| Fiyat arşivi derinliği | **2012 h1 → 2026 h37**, 21 çift, HEAD ile ölçüldü; indirilen kısım 55 hafta (2023-11-19..2024-12-13) | K-091, `tools/fx_depo_durumu.py` |
| Takvim (`fx-5x24`), rollover anları, kalite bayrağı, PIT evren | **hazır** | K-089, K-095, K-096 |
| Motorda finansman geçerlilik denetimi (`FinansmanKaynagi.aralik`, aralık dışı → koşu başlamaz) | **hazır** | K-101 |
| Çift başına ölçülmüş maliyet (spread/slippage/komisyon) | **hazır, ölçülmüş** (`tur` broker verisi) | K-100/5 |
| Finansman (rollover) modeli | **21/21 proxy, `gecici`** — merkez bankası politika faizi farkı, broker oranı değil | K-098, K-100, K-101 |
| Gerçek tarihli FXCM rollover arşivi | **yok** | K-101 (7 resmi kaynak tarandı), §3 |

Yani veri tarafında eksik olan tek şey **indirme** (mekanik, hazır); finansman tarafında eksik olan şey
**kaynak** (yok).

## 2. Mevcut geçerli finansman penceresi (proxy, `config/finansman/fxcm-<pair>.json` `aralik`)

Proxy aralığı, iki merkez bankası faizinin de sabit kaldığı dönem; faiz değişince aralık biter.

| | Aralık | Gün |
|---|---|---|
| 21 çiftin ortak aralığı | 2023-11-08..2024-03-19 (BoJ 03-19, SNB 03-21) | 132; fiyat verisi 2023-11-19'da başladığı için **fiilen 2023-11-19..2024-03-18 = 120 gün**; aylık çözünürlükte kullanılan 2023-11..2024-02 = 1.721 bar |
| Çift başına en uzun (veri ile kesişimi) | AUDNZD, NZDUSD: 2023-11-19..2024-08-14 | **269** |
| ≥ 365 gün finansman-geçerli çift | — | **0** |
| Promotion'a açık (proxy olmayan) gün | — | **0** (K-101/2: `gecici_finansman_modeli` mutlak engel, pencereden bağımsız) |

Aralıklar `2026-09-21-R6-h54-tekrar.md` §1'de çiftlere göre listelenmişti (JPY 03-19, CHF 03-21,
CAD-çapraz 06-05, EUR-çapraz 06-12, GBP-NZD/USD 08-01, AUDNZD/NZDUSD 08-14).

## 3. Gerçek tarihli broker finansmanı: bugünkü kısa yeniden tarama

K-101'in bulgusu değişmedi. 2026-09-22'de iki ek arama: (a) "historical forex rollover swap rates archive
by date" — Dukascopy/TraderMade yalnız fiyat verisi; ForexBenchmark üçüncü taraf, FXCM listede yok,
doğruluk garantisi yok (K-101'de elenmişti); FOREX.com/Trading.com kendi cari oranlarını yayımlıyor
(FOREX.com sayfası 403 verdi, tarihli arşiv iddiası doğrulanamadı; başka broker, bizim veri FXCM).
(b) "FXCM historical rollover rates by date" — yalnız Trading Station'da "bir gün önceden" cari değer
(`Roll S`/`Roll B`, 1k lot), takvim PDF yalnız gün çarpanı; arşiv yok.

**Sonuç: FXCM için tarihli, çift bazlı, uzun/kısa rollover arşivi yok → `tur=broker` finansman
üretilemez.** Uydurulmadı; proxy promotion-ready yapılmadı.

## 4. ≥ 1 yıl mümkün mü?

| Katman | ≥ 1 yıl | Nasıl | Promotion'a etkisi |
|---|---|---|---|
| Fiyat (bid/ask 1h, takvim, kalite, PIT) | **evet** | mevcut indirici, 2012'ye kadar; yalnız indirme + `fx_depo_durumu` | yok (fiyat zaten yeterli) |
| Finansman, proxy | teknik olarak evet: faiz değişimlerini parça parça izleyen **yeni proxy segmentleri** (`tools/fx_finansman_proxy_yaz.py` kalıbı) | ölçülmüş oran değil; `tur=proxy`, `gecici` kalır | **sıfır** — engel pencereye değil kaynağa bağlı |
| Finansman, gerçek tarihli | **hayır** (kaynak yok) | — | tek kilit bu |

Proxy segmentleriyle pencere uzatmak yalnız **araştırma** kapılarını (walk-forward, rejim,
`yillik_anlamli`, ekonomik `asgari_islem`) ölçülebilir kılar; promotion'a bir gün bile açmaz. R6 kapalı
ve yeni çekiliş yokken bu altyapı bugün bir şey satın almıyor → **yapılmadı** (talimat: boşuna altyapı
geliştirme).

## 5. Eksik olan gerçek veri (tam tanım, gelirse doğrudan `FinansmanKaynagi`ye oturur)

Çift × tarih (rollover günü, NY 17:00) × yön (uzun/kısa) × oran; birim 1k lot başına kote para birimi
ya da bps/gün (dönüşüm K-101'de yazılı: `bps = roll / (1000 × kur_quote→hesap) × 10⁴`); Çarşamba 3 gün
ve tatil (0 / +1) uygulanmış hâliyle; fiyat penceresini (en az 2023-11-19..2024-12-13, tercihen ≥ 1 yıl
kesintisiz) kapsayan; kaynağı ve erişim tarihi kayıtlı. Bugün bunu üretebilecek bilinen tek yol
**ileriye dönük**: bir FXCM (demo/gerçek) hesabında Trading Station'ın günlük `Roll S`/`Roll B`
değerlerini her gün kaydetmek — geriye doldurmaz; ≥ 1 yıl için ≥ 1 yıl bekler; hesap gerektirir. Bu bir
Scryne kararı (hesap açma, kayıt süreci), bu pakette **yapılmadı**.

## 6. Karar ve R7'de uygulanabilir sonraki adım

- **FX finansman penceresi genişletme: BLOCKED** (gerçek veri yok). Proxy pencere 120 gün (ortak) /
  269 gün (en uzun çift), promotion penceresi 0 gün. Kayıt K-107.
- **R7 FX'i beklemez.** R7 (portföy kurma) kripto evreninde tam kapsamlı yürür: funding gerçek ve
  ölçülü (K-042), proxy yok, promotion yolu açık; roadmap zaten "R5 yöntem yoluyla, aday olmadan da
  kurulabilir" diyor. FX, R7'de yalnız "finansman `tur=broker` olduğu gün" koşuluyla girer.
- FX'e dönüş tetikleyicisi tek ve sayısal: **`config/finansman/fxcm-<pair>.json` içinde `tur=broker`,
  aralık ≥ 365 gün, en az bir çift.** O gün: (1) fiyat verisini aynı aralığa indir, (2) FX null'unu ölç
  (K-102/6), (3) `oos_sharpe`↔`yillik_anlamli` kararını ver, (4) h56 sabit noktasını yeni çekiliş
  harcamadan koştur (K-104/K-106). Bunlar bugün başlatılmadı.
