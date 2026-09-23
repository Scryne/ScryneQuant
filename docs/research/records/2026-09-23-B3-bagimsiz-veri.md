---
proje: ScryneQuant
tarih: 2026-09-23
karar: K-127
type: kayit
---
# B-3 bağımsız doğrulama veri seti: kaynak, kimlik, PIT ve bağımsızlık denetimi

**Kapsam:** yalnızca veri hattı. Strateji koşulmadı, bağımsız pencerede getiri istatistiği hesaplanmadı. Revizyon
ölçümünde yalnızca vintage'lar arası hücre farkları sayıldı.

## Kaynak

- **Sağlayıcı:** Kenneth R. French Data Library (Dartmouth Tuck),
  `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/`.
- **Dosyalar:**
  - `12_Industry_Portfolios_Daily_CSV.zip`: VW ve EW bölümleri; 12 sektör NoDur…Other.
  - `F-F_Research_Data_Factors_daily_CSV.zip`: Mkt-RF, SMB, HML, RF.
- **Vintage:** dosya başlığında "created using the 202607 CRSP database". HTTP Last-Modified 2026-09-04. İndirme 2026-09-23.
- **Aralık ve sıklık:** 1926-07-01 → 2026-07-31, işlem günü, 26.296 satır. Yüzde getiri. Eksik değer kodu -99.99/-999
  (doğrulama penceresinde yok; yükleyici reddeder).
- **Yapım (kaynak sayfası):**
  - "We assign each NYSE, AMEX, and NASDAQ stock to an industry portfolio at the end of June of year t based on its
    four-digit SIC code at that time."
  - "We use Compustat SIC codes for the fiscal year ending in calendar year t-1. Whenever Compustat SIC codes are not
    available, we use CRSP SIC codes for June of year t."
- **Revizyon politikası (kaynak):**
  - "We reconstruct the full history of returns each month when we update the portfolios. (Historical returns can change,
    for example, if CRSP revises its database.)"
  - FIZ biçimi 2024-12'de bitti; 2025-01'den beri CIZ kullanılıyor.
- **Lisans:** "Copyright Eugene F. Fama and Kenneth R. French"; ücretsiz erişim, açık lisans yazılı değil. Ham dosyalar
  repoya girmez (`data/` gitignore); kimlik manifestte tutulur.

## Kimlik (`config/bagimsiz_veri.json`)

| Alan | Değer |
| --- | --- |
| dataset_id | `french_12ind_vw_gunluk_202607` |
| period_start / period_end | 2004-06-01 / 2026-07-31 (5.577 işlem günü) |
| sektör zip / CSV | `ff4f0b6c4bd6…` / `20b066c1fcd8…` |
| faktör zip / CSV | `1916d331c2c5…` / `b324d858f6ba…` |
| kanonik veri_sha256 | `2448dddc19747d1138675c461b214279e27beda8a4e2867e43ff51be1c21dbc1` |

**Kanonik temsil:** `tarih,NoDur,…,Other,Mkt-RF,RF`, kaynak ondalık metinleri, LF, UTF-8.

**Yeniden üretim:** `sq data bagimsiz-dogrula` kimliği sıfırdan hesaplar. İki kez çalıştırıldı, aynı hash.

## PIT denetimi

| Konu | Durum |
| --- | --- |
| Değer zamanı / look-ahead | Uygun: t getirisi t kapanışında bilinir; `zaman_ms` = gün açılışı (K-005), dolum t+1 (K-004) |
| Üyelik zamanı | Kaynağa göre uygun (yıllık, Haziran sonu, o anki SIC); bileşen verisi yok, doğrulanamadı |
| Hayatta kalma | CRSP evreni (delist dahil); delist getirisi kaynak sayfada açık değil |
| Revizyon | **Uygun değil:** her ay bütün geçmiş yeniden üretiliyor; as-published vintage geçmişi yok |

**Revizyon ölçümü:** Wayback görüntüleri 202607 ile karşılaştırıldı. Kapsam: VW, 12 sektör, 2004-06-01 → eskinin sonu.

| Eski vintage | Ortak gün | Değişen hücre | ≥10 bp | ≥100 bp | Azami (yp) |
| --- | --- | --- | --- | --- | --- |
| 201611 (FIZ) | 3.149 | %58,27 | %2,50 | %0,003 | 1,19 |
| 202202 (FIZ) | 4.468 | %31,59 | %1,54 | %0,004 | 3,44 |
| 202406 (FIZ) | 5.054 | %32,18 | %1,50 | %0,003 | 3,44 |
| 202601 (CIZ) | 5.452 | %0,25 | %0 | %0 | 0,02 |

Hiçbir vintage'da eksik ya da fazla gün yok. Wayback'te toplam 9 anlık görüntü var (2015-11 → 2026-03). Ölçülen görüntüler
yerelde `data/bagimsiz/french/vintage/` altında.

**Hüküm:** PIT değil (revize edilmiş tek vintage) → `promotion_uygun: false` (K-127/4).

## Bağımsızlık kanıtı

- Hipotez defteri (63 satır): bu verinin kanonik hash'i ve kaynak dosya hash'leri hiçbir satırda yok. French/ABD hisse
  çekilişi yok.
- Programlar (22 satır): hisse/sektör programı yok.
- Kayıt dışı kullanım yalnız K-124 IS ölçümü: 1952-07 → 2004-05, kodu repoda değil.
- **Sınır:** Defter yalnız kayıtlı çekilişleri gösterir. 2008, 2020 ve 2022 düşüşleri genel bilgi; proje bağımsızlığı
  insan bilgisinden bağımsızlık demek değil. P3 plasebosu bu hindsight'ı kısmen nötralize eder.
