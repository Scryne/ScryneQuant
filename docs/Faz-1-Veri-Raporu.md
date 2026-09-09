---
proje: ScryneQuant
created: 2026-09-09
type: faz-raporu
faz: 1
status: aktif
---
# Faz 1 — Market data temeli: ne indirildi, ne ölçüldü

Bu dosya Faz 1'in **ölçüm** kaydıdır. Kararların gerekçesi `docs/Kararlar.md`'de
(K-021, K-023, K-024, K-025); burası o kararların dayandığı sayılar.

Ölçüm tarihi: **2026-09-09**. Ham raporlar `data/kalite/` altında (git'e girmez, komutla
yeniden üretilir).

## 1. İndirilen veri

| | 1h (birincil, K-017) | 1m (yardımcı) |
| --- | --- | --- |
| Aralık | 2021-06-28 03:00 → 2026-09-09 09:00 UTC | 2023-08-04 04:17 → 2026-09-09 10:52 UTC |
| Süre | **5,2 yıl** (kriter: ≥5) | **3,1 yıl** (kriter: ≥3) |
| Bar | 45.576 | 1.630.476 |
| Parquet (zstd) | 2,08 MB | 63,61 MB |
| İndirme | 46 çağrı, 14,0 s | 1.631 çağrı, 560,8 s |
| SHA-256 | `e3adb02c2a6a…` | `5a3b33c708a5…` |

**Projeksiyon tuttu mu — süre evet, boyut hayır.** Spike 2 "~1,7 MB + ~43 MB, toplam
~8 dakika" demişti. Gerçek: 2,08 MB + 63,61 MB, 9,6 dakika.

Boyut sapmasının sebebi **şema farkı**, veri farkı değil. İlk tahmin önce "son yılların barı
daha ağırdır" idi; ölçüldü ve **çürüdü** — bar başına boyut aralık boyunca neredeyse sabit:
ilk yıl 40,0 bayt/bar, son yıl 41,6 bayt/bar. Asıl fark şurada: spike'ın ölçtüğü dosya yedi
sütunluydu (`open_time, open, high, low, close, volume, trades`) ve 27 bayt/bar veriyordu;
`BAR_SEMASI` dokuz sütun taşıyor — `quote_volume` (float64) ve `quality_status` (string)
eklendi. Yani ~1,45 katlık büyüme K-006 ve K-023'ün bedeli, hem de bilinerek ödenen bir bedel.

Süre beklentiyle uyumlu ve **ağ sınırlı, rate limit sınırlı değil** — 1.631 çağrı × 2 weight
= 3.262, dakikalık limit 6.000.

## 2. Kalite — Spike 2'nin "veri kusursuz" bulgusu kısmen çürüdü

Spike 2, 3 yıllık 1h ve 1 yıllık 1m veride **sıfır** anomali bulmuştu ve buradan "K-006'nın
bayrakları gerçek veriyle hiç tetiklenmeyecek" sonucu çıkmıştı. **Pencere genişleyince
bulgu değişti.**

| | 1h (5,2 yıl) | 1m (3,1 yıl) |
| --- | --- | --- |
| `ok` | 45.572 (%99,9912) | 1.630.476 (%100) |
| `gap` | 3 | 0 |
| `suspect` | 1 | 0 |
| `duplicate` | 0 | 0 |
| Eksik bar | 7 | 0 |
| Kapsama | %99,9846 | %100 |

**Boşluklar (1h):**

| Aralık (UTC) | Eksik bar |
| --- | --- |
| 2021-08-13 02:00 → 06:00 | 4 |
| 2021-09-29 07:00 → 09:00 | 2 |
| 2023-03-24 13:00 → 14:00 | 1 |

**Tek `suspect` bar — 2023-03-24 12:00 UTC.** Hacim 0, işlem 0, dört fiyat da 28.080,00.
Bir sonraki bar (13:00) ise hiç yok. Yani tek bir olay iki bayrağı birden üretmiş: kesintinin
başındaki bar sıfır hacimle kaydedilmiş, ortasındaki bar hiç kaydedilmemiş, sonrasındaki
(14:00) `gap` işaretli.

**Sonucu:** `gap` ve `suspect` kod yolları ölü kod değilmiş — Spike 2'nin penceresi onları
görecek kadar geniş değilmiş. Bu, spike'ın sonucunu geçersiz kılmıyor ama **genellemesini**
kılıyor: "gerçek veride anomali yok" değil, "3 yıllık pencerede anomali yok" doğruymuş.

Yine de sentetik bozuk fixture'lar yerinde kalıyor ve kalmalı: gerçek veri `duplicate`,
`islemsiz_hacim`, `high_low_ters`, `pozitif_olmayan_fiyat`, `sonlu_olmayan`,
`asiri_hareket` kurallarının hiçbirini hâlâ tetiklemiyor. Onlar yalnızca
`tests/unit/test_dogrulama.py`'de çalışıyor.

## 3. Slippage kalibrasyonu (K-021 kapandı)

Ölçüm: BTC/USDT 1m, tüm aralık, **1.630.475 hareket**, hepsi `ok` bar.

| | p50 | p75 | p90 | p95 | p99 | ort | max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 dk hareket (bps) | 2,566 | **5,300** | 9,325 | 12,870 | 23,426 | 4,050 | 428,98 |
| 1m bar içi salınım (bps) | 4,446 | 8,172 | 13,584 | 18,302 | 32,349 | 6,296 | 643,57 |

**Seçilen: p75 → `slippage_bps = 5,2996`.** Gerekçe K-021'in kapanış bölümünde ve
`config/maliyet.json`'ın `kalibrasyon.gerekce` alanında; özeti: ölçülen 1 dakikalık pencere
gerçek yürütme penceresinden (~1 s) onlarca kat uzun, yani metrik zaten muhafazakâr bir üst
sınır; üstüne yüksek persentil koymak iki muhafazakârlığı çarpar.

**Spike 2'nin sayısı doğrulandı:** 1 yılda p50 = 2,42 / p75 = 5,01; 3,1 yılda
p50 = 2,566 / p75 = 5,300. Bu yakınlık, yöntem tanımının spike'ınkiyle aynı olduğunun kanıtı.

**Gidiş-dönüş maliyeti: 30,60 bps** (2 × [10,0 + 5,2996]). K-017'nin timeframe kararı
20,02 bps'lik komisyon ayağına dayanıyordu; slippage eklendiğinde 1h barın medyan hareketi
(20,85 bps) gidiş-dönüş maliyetinin **altına** düşüyor. Karar değişmiyor — 1m'nin oranı hâlâ
~8 kat daha kötü — ama Faz 4'ün "hiçbiri maliyetlerden sonra anlamlı değil" beklentisi
güçlendi.

## 4. İdempotency kanıtı

Faz 1'in kriteri: aynı indirme komutu iki kez çalıştırıldığında dosya bit düzeyinde aynı.

```
$ sq data indir BTCUSDT 1h --yil 5.2      # ilk
  inen bar : 45,576 (46 çağrı)   sha256: e3adb02c…   değişti: evet
$ sq data indir BTCUSDT 1h --yil 5.2      # ikinci
  inen bar : 0      (3 çağrı)    sha256: e3adb02c…   değişti: HAYIR (idempotent)
```

İkinci çalıştırmanın 3 çağrısı, üç boşluğun yeniden denenmesidir (K-024): borsa boşluğu
sonradan doldurursa veri seti kendiliğinden iyileşsin diye. Çağrı başına 2 weight, yani
maliyeti sıfıra yakın.

Bunun üç ayağı var, üçü de test altında:

1. **Kapanmamış bar yazılmıyor** (K-015/1) — `test_binance_adaptoru.py::TestKapanmamisBar`.
2. **Depo kanonik yazıyor** (K-011) — `test_depo_idempotency.py`, ayrıca ayrı bir süreçte
   `test_depo_surecler_arasi.py`.
3. **Bayrak tam seriden hesaplanıyor** — `test_indirici.py::test_parcali_indirme_butun_indirmeyle_ayni_dosya`.
   Üçüncüsü en az görünen ama en kritik olanı: `gap` bayrağı bir barın **öncekiyle**
   arasındaki mesafeye bakar; sayfa sayfa doğrulansaydı dosya, indirmenin kaç parçaya
   bölündüğüne göre değişirdi.

## 5. Faz 2'ye devreden

- **`suspect` eşiği bir varsayım.** `asiri_hareket_bps = 5.000` (%50), 5,2 yıllık veride
  ölçülen en büyük 1h hareketin (533 bps) ~9 katı. Ölçüye dayanıyor ama ölçülmüş bir eşik
  değil; başka bir sembol eklendiğinde yeniden bakılmalı.
- **Slippage hâlâ bir proxy.** Gerçek dolum fiyatı ancak Faz 7'de testnet'te ölçülebilir.
  O ölçüm bugünkü 5,2996'yı doğrulamalı; sapıyorsa yeni bir karar yazılır.
- **`backfilled` bayrağı hiç üretilmiyor.** Kod yolu var ve test altında, ama Faz 1'de tek
  kaynak REST olduğu için anlamı yok. Faz 6'da birincil akış WebSocket olunca kazanacak.
- **1m verisi backtest'te kullanılmıyor.** İndirildi çünkü K-017 üç sebep saydı: slippage
  kalibrasyonu (bu fazda kullanıldı), Faz 3'ün fill gerçekçiliği, Faz 7'nin emir testleri.
  İkisi hâlâ önümüzde.

## Kaynaklar

- `data/kalite/BTCUSDT-1h.json`, `data/kalite/BTCUSDT-1m.json` — ham kalite raporları
- `config/maliyet.json` — kalibrasyonun tam kaydı
- Komutlar: `sq data indir`, `sq data quality`, `sq data slippage-kalibre`, `sq data maliyet`
