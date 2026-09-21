# R3 — FX veri katmanı raporu (FXCM MarketData, K-088)

**Durum:** yaşayan rapor; Paket 1(a)-(c) ölçümleri (2026-09-21). Sayılar gerçek dosyalardan, tahmin
yok. Veri `data/fx/` (gitignore; lisans "personal use" — fixture olarak dağıtılmaz).

## 1. Kaynak ve kapsam (Paket 1(b))

| Ölçüm | Sonuç | Yöntem |
| --- | --- | --- |
| Çift sayısı | **21** (README listesi, `data/fx.FXCM_CIFTLER`, kapalı küme) | README okundu |
| Tarihsel başlangıç | **2012 h1** (2012-01-01 Pazar) — 2011 h50-53 **404**, 21 çiftin tamamında 2011 h10 404 / 2012 h10 200 | HEAD |
| Güncellik | 2026 h37 (6-11 Eylül) **var**, h38-39 404 → yayın gecikmesi ≈ 1-2 hafta | HEAD, 2026-09-21 |
| Dosya/hafta | Pazar → Cuma; 7.172–7.188 M1 satır (2024); yılbaşı haftaları kısa | 11 gerçek hafta |
| Hafta anahtarı | `%U(Pazar) + 1` (yıl Pazar'la başlamıyorsa); 2024/1 ve 2024/53 404 | ölçüm + `hafta_no` testi |

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

## 5. Açık

- Hayatta kalma yanlılığı (1e): 21 çift sabit; PIT tablosu "hangi çiftin hangi haftadan itibaren
  dosyası var" ile kurulacak (2012 h1'de 21/21 var → sıfır beklenir, ölçülecek).
- Spread/mid (R4), kalibrasyon (K-021 kalıbı bid/ask ile), canlı akış yok (K-087/2).
