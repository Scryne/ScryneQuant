# R3 — FX veri katmanı raporu (FXCM MarketData, K-088)

**Durum:** **kapandı 2026-09-21 (K-092)**; Paket 1(a)-(f) ölçümleri. Sayılar gerçek dosyalardan, tahmin
yok. Veri `data/fx/` (gitignore; lisans "personal use" — fixture olarak dağıtılmaz).

## 1. Kaynak ve kapsam (Paket 1(b))

| Ölçüm | Sonuç | Yöntem |
| --- | --- | --- |
| Çift sayısı | **21** (README listesi, `data/fx.FXCM_CIFTLER`, kapalı küme) | README okundu |
| Tarihsel başlangıç | **2012 h1** (2012-01-01 Pazar) — 2011 h50-53 **404**, 21 çiftin tamamında 2011 h10 404 / 2012 h10 200 | HEAD |
| Güncellik | 2026 h37 (6-11 Eylül) **var**, h38-39 404 → yayın gecikmesi ≈ 1-2 hafta | HEAD, 2026-09-21 |
| Dosya/hafta | Pazar → Cuma; 7.172–7.188 M1 satır (2024); yılbaşı haftaları kısa | 11 gerçek hafta |
| Hafta anahtarı | `%U(Pazar) + kayma`, kayma 1 yalnız 1 Ocak Pzt/Sal/Çar (K-091; K-088'deki kural yanlıştı); yıl sınırında sağlayıcı tutarsız → alternatif `(yıl+1, 1)` | 15 yılın 10. dosyası + 2017/2023 sınırı |

Tam evren (21 × ~770 hafta ≈ 16.000 dosya × ~95 KB ≈ 1,5 GB) **indirilmedi** (talimat: örnekle
sına). Tam HEAD taraması (770 istek) sunucunun bağlantıyı düşürmesiyle 187 dk sonra kesildi;
`https_var_mi`/`https_indirici` artık tek oturum + üstel yeniden deneme (4). Derinlik kanıtı sınır
taramalarıyla alındı (`_gelen/EURUSD/kesif*.json`).

## 2. Depo (Paket 1(a)) — gerçek örnek

| Çift | Aralık | Hafta | 1h bar | SHA-256 (ilk 12) |
| --- | --- | --- | --- | --- |
| EURUSD | 2024-01-07 22:00 → 2024-03-22 20:00 UTC | 11 | 1.320 | `b6f762aeaebd` |
| GBPUSD | 2024-01-07 22:00 → 2024-02-02 21:00 UTC | 4 | 480 | `872bf17bcb53` |
| USDJPY | 2024-01-07 22:00 → 2024-02-02 21:00 UTC | 4 | 480 | `588889c9cd8b` |

İdempotency: EURUSD 4 hafta iki koşu bayt-aynı (`c2ca19685465`); `--bitis-gun 2024-01-24` → 314 bar
(`64262c09e55e`), uzatınca yine `c2ca19685465` (K-080).

## 3. Kalite (Paket 1(c)) — `sq data quality fx EURUSD`

| Ölçüm | Sonuç |
| --- | --- |
| Dosya | 11/11 hafta var; eksik dosya 0; kapsam dışı 0 |
| Bar | 1.320 mevcut / 1.320 beklenen; **eksik saat 0** (hafta içi) |
| Hafta uzunluğu | **120 saat** × 11 (Pazar açılış → Cuma kapanış, 5 × 24) |
| Açılış saati (UTC) | 22:00 × 9 (kış), **21:00 × 2** (h11 = 10 Mart ABD yaz saati, h12) |
| Kapanış saati (UTC) | 21:00 × 9, 20:00 × 2 |
| Kısa saat (`m1_sayisi < 60`) | 78; dağılım 22:00 → **44**, 21:00 → 12, 23:00 → 10, diğer ≤ 4 |

Yorum: kısa saatlerin 22:00 UTC'de (DST haftalarında 21:00) yığılması NY 17:00 günlük rollover
duraklamasının izi — bar var, dakika eksik; gap değil. Hafta sonu (Cuma 21/20:00 → Pazar 22/21:00)
beklenen ızgaranın dışında; rapor bunu gap saymıyor, eksik **dosya** ile eksik **bar**ı ayırıyor.

## 4. `fx-5x24` takvimi için kanıt (Paket 1(d) girdisi)

- Seans: Pazar 22:00 UTC → Cuma 22:00 UTC (kış); ABD yaz saatinde **bir saat erken** (21:00 → 21:00).
  Yani takvim UTC'de sabit değil, **NY 17:00'ye bağlı** (5/7, `America/New_York` 17:00 dönüm).
- Hafta içi kesintisiz 24 saat (120/120 bar, 11/11 hafta); günlük rollover saatinde bar kısa ama var.
- Sonuç: `fx-5x24` içeriği = "NY 17:00 (yerel) Pazar açılış → Cuma kapanış, hafta içi sürekli";
  `izgara()` UTC saat başlarını NY yerel saate göre keser. Bu, tatil/kısa gün (Noel, Yılbaşı —
  2023 h52/53'te 5.415/5.356 satır) için **tatil tablosu** ister → R3 Paket 1(d)'de yıl sonu haftaları
  ayrıca ölçülmeden takvim yazılmaz (K-083/U15).

## 4b. Paket 1(d) ölçümü ve `fx-5x24` (K-089)

55 hafta (2023-11-19 → 2024-12-13): 53 hafta 120/120; Noel 2023 (h52) 28 saat kapalı
(2023-12-25 01:00 → 12-26 05:00 UTC), Yılbaşı 2024 (h53) 29 saat kapalı (2024-01-01 00:00 →
01-02 05:00 UTC); Şükran Günü, Good Friday, Easter Monday, May Day, Memorial Day, 4 Temmuz, Labor
Day, Veterans Day haftaları **120/120** (kapanış yok). Kısa saatlerin NY yerel dağılımı: 17:00 →
257/447 (rollover). Sağlayıcı m1 boşlukları: 2024 h35, h51-53, 2025 h2 (21 çiftte; `H1` katmanında
2024/52 var) — Noel/Yılbaşı 2024 ölçülemedi. Takvim + 2 ölçülmüş kapanış gerçek depoyu bar bar
açıklıyor: beklenen 6.663 = 6.543 + 120 (h35 dosyası); takvim dışı bar 0.

## 5. PIT evren ve hayatta kalma — tasarım (Paket 1(e), K-090)

Kural `dosya-var` (kimlik `6124cf568498…`, 21 çift): üyelik = o haftanın M1 dosyası sağlayıcıda var.
Kanıt kaynağı HEAD keşfi (`kesif-*.json`) + indirilmiş manifestolar; kanıtsız hücre bilinmiyor.
Bugünkü kanıt: EURUSD 80 hafta (2011 h50 → 2026 h39; 69 var), GBPUSD/USDJPY 4'er hafta → `kapsam:
kismi`, **ölçülen hafta 0** (21/21 kanıtlı hafta yok). Tam ölçüm için gereken **minimum kapsam**:
21 çift × 770 hafta HEAD (≈16.170 istek, veri indirmesiz, curl hızıyla ≈ 80 dk; sunucu uzun
oturumu düşürdüğü için yıl yıl `--bas/--bit` parçalarıyla). Tam veri indirme (≈1,5 GB) hayatta
kalma ölçümü için **gerekmez**; kalite bazlı eleme ve R6 araştırması için, kullanılacak pencere
kadar. "2012 h1'de 21/21" varsayılmıyor: matris ölçecek (örnek kanıt: 21 çiftte 2012 h10 200,
2011 h10 404).

## 5b. PIT / hayatta kalma — ölçüm (K-091, 2026-09-21)

HEAD ile 21 çift × 773 hafta (2011-49 → 2026-38), indirme ve ödeme yok; kanıt `kesif-*.json` +
manifestolar (`fx_evren` fail-closed birleştirdi; 2017/2018 sınırındaki eski/yeni çelişkiyi yakaladı,
yeniden tarandı). Sonuç `data/fx/_evren/6124cf568498.json` (tablo `10703833134d`, 16.233 satır):

| Ölçüm | Sonuç |
| --- | --- |
| Kapsam | tam (21/21, 773 hafta, kısmi kanıt 0) |
| 2012 h1 | **21/21 üye** (ölçüldü); 2011 h49-52 hiçbiri yok |
| Son üye haftası | 2026 h37 (13 Eylül) |
| Sağlayıcı boşluğu (21/21 yok) | 2011 h49-52 · 2025 h29-30 · 2026 h18-31 (14 hafta) · 2026 h38 |
| Hayatta kalma | 752 hafta ölçüldü; medyan **0,0**; sıfır olmayan 5 hafta (%0,66); azami 0,952 |
| Sıfır olmayan haftalar | 2024 h35 (AUDCAD), h51 (AUDCAD), h52 (AUDCAD, AUDCHF), h53 + 2025 h2 (AUD× 4) — kısmi yayın, delist değil |

Kripto ile kıyas: aylık medyan %16,7-18 (K-056) → FX sabit sözleşmede **0**. Araştırma kuralı için
asgari üye eşiği (kısmi yayın haftaları) R5/R6 kararı.

## 6. R3 kapanışı (K-092)

Bitiş kriteri: kaynak+lisans ✅ (K-088) · indirici idempotent/checksum/`veri_sonu` ✅ (K-088) ·
takvim testi ✅ (K-089) · hayatta kalma ölçümü ✅ (K-091) · `sq data quality fx` ✅ (K-089) · canlı
akış isteğe bağlı, yok. Devredilen: spread/mid ve bid/ask tüketimi, takvim bağlama, `kapali` tablosu
genişletme, asgari üye eşiği, FX kalibrasyonu (R4/R5).

## 7. Açık

- Hayatta kalma yanlılığı (1e): 21 çift sabit; PIT tablosu "hangi çiftin hangi haftadan itibaren
  dosyası var" ile kurulacak (2012 h1'de 21/21 var → sıfır beklenir, ölçülecek).
- Spread/mid (R4), kalibrasyon (K-021 kalıbı bid/ask ile), canlı akış yok (K-087/2).
- Noel/Yılbaşı 2024 ve diğer yıllar: m1 kapsamı genişleyince `kapali` yeni sürümle ölçülüp eklenir.
