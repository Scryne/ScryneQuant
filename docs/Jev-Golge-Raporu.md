# Jev gölge programı — kurulum, boru hattı doğrulaması ve ölçüm planı

> **Tarih:** 2026-09-19 · **Karar:** K-074 · **Durum:** boru hattı doğrulandı; ileriye dönük
> gölge koşusu **başladı, sonuç yok** · **Kanıt sınıfı:** aşağıdaki hiçbir sayı Jev'in
> isabetine dair kanıt değildir (replay `leak_riski=true`; gölge penceresi henüz boş)

Bu rapor iki bölümden oluşur. Birincisi bugün ölçülenler: boru hattının çalıştığı, deterministik
olduğu, gelecekten etkilenmediği ve fail-closed olduğu. İkincisi gölge penceresi kapandığında
doldurulacak tablo — sütunları **şimdi**, sonucu görmeden yazılıyor (spec §35, K-074/7).

## 1. Ne kuruldu

| Katman | Modül | Ne yapar | Ne yapmaz |
| --- | --- | --- | --- |
| Kanonik durum | `jev/durum.py` | 1h karar barı + 1h'den toplanmış kapanmış 4h + funding; betimleyici etiketler; `PENCERE_BAR`=1.200 sabit pencere; `durum_hash` | Diziyi Jev'e göndermez; sayısal eşik sormaz; `t` sonrasını okumaz |
| Soru seti | `jev/sorular.py` | 4 soru: `yon` (long/short/flat), `rejim`, `kurulum` (Score), `cekimser` (Noul); `SORU_SHA256 = e6f91afb…` testle donmuş | Faktör Noul'u yok (koddan etiket); sayısal kıyas yok |
| Adaptör | `jev/istemci.py` | Tek SDK girişi; timeout 20 s; 2 deneme; hata sınıflandırma; sır tarama/temizleme | Varsayılan cevap üretmez; anahtara dokunmaz |
| Karar | `jev/karar.py` | `JevKarari` frozen, `extra=forbid`; yön = olasılık vektörü + marj 0,20; `ileriye_donuk`/`leak_riski` | Miktar/fiyat/kaldıraç/stop alanı **tipte yok**; `Sinyal` üretmez |
| Defter | `jev/defter.py` | `runs/jev/<kosu>.sqlite`: koşu kimliği, karar + kanonik durum (bytes) + ham yanıt, olaylar; zincir hash; UPDATE/DELETE tetikleyicileri | Silme/güncelleme; sır |
| Gölge | `jev/golge.py` | `BinanceBarAkisi` + `BarPenceresi` (paper'ın akışı ve doğrulaması); her `ok` barda durum → Jev → defter; 24 kararda bir tutarlılık sorgusu | `PaperMotoru`/`RiskMotoru`/execution ile bağ (AST testli) |
| Replay | `jev/tekrar.py` | Tarihsel barlar → aynı kurucu → Jev → defter → Parquet + manifest (`data/semantik/jev/<id>/`) | Backtest içinde çağrılmaz (K-049/5); isabet kanıtı |
| Sonuç | `jev/sonuc.py` | `open[t+1]` giriş; 1/4/24 bar getiri, MAE, MFE, gidiş-dönüş maliyet; yön isabeti + Wilson CI; `al_tut` kıyası; güven kovaları, Brier, ECE; rejim başına | Yorum |
| CLI | `cli/jev.py` | `sq jev golge / durdur / durum / degerlendir / tekrar / dondur` | — |

Testler: `tests/unit/test_jev_*.py` — 7 dosya, 202 test (durum 51, izolasyon 20, karar/istemci
72, defter 15, tekrar 12, gölge 15, sonuç 17). Tam takım: **1.834 geçti**, 1 atlandı, 3 ağ
testi CI'da dışarıda. CI: `.github/workflows/test.yml` (push'ta doğrulanacak; repoya henüz
push edilmedi).

## 2. Bugün ölçülenler (boru hattı; kanıt değil)

### 2.1 Sızıntı ve determinizm (test)

- Aynı diziler + aynı bar → kanonik JSON **byte düzeyinde** aynı (10 tekrar), hash =
  SHA-256(JSON).
- `t` sonrası **rastgele / uçtan uca yukarı / uçtan uca aşağı bozma** ve **silme** → JSON aynı
  (4 kesme noktası × 4 bozma). Hemen sonraki tek barın bozulması → aynı. Gelecek funding
  bozulması ve silinmesi → aynı; `funding_time ≤ karar_ms` sınırı dahil, +1 ms hariç.
- **Negatif kontrol:** bir sonraki barın kapanışını duruma sokan kasıtlı sızdıran kurucu,
  bozma ve silme testlerinde **yakalandı**.
- Pencere dışı geçmiş (1.200 bardan öncesi) durumu değiştirmiyor → replay (tam seri) ile canlı
  (sınırlı pencere) aynı hash; gölge ve replay aynı 25 bar için **hash eşit** (test) ve gerçek
  veride 48/48 bar (aşağıda).
- 4h kova yalnızca kapanmışsa ve 4 barı `ok`/`backfilled` ise girer; `gap`/`suspect` kovayı
  düşürür, uydurulmaz.

### 2.2 Gerçek veri, gerçek Jev: 48 barlık replay, iki bağımsız koşu

`sq jev tekrar --kosu tekrar-orneklem-{a,b} --son-n-bar 48` (BTCUSDT 1h, 2026-09-02 08:00 →
2026-09-09 09:00 UTC; girdi `1h.parquet` SHA-256 `e3adb02c…`, funding `747a8253…`).

| Ölçüm | Değer |
| --- | ---: |
| Durum hash eşitliği (A vs B) | **48 / 48** |
| Geçerli karar | 48 / 48 (hata 0) |
| Yön etiketi aynı (A vs B) | 48 / 48 |
| `yon` olasılık sapması medyan / p95 / max | 0,030 / 0,097 / 0,130 |
| `rejim` olasılık sapması medyan / p95 / max | 0,040 / 0,080 / 0,130 |
| `kurulum` skor sapması medyan / p95 / max | 0,050 / 0,150 / 0,240 |
| `cekimser` sapması medyan / p95 / max | 0,015 / 0,047 / 0,070 |
| Gecikme p50 / p95 (ilk bağlantı hariç) | 295 / 403 ms (ilk çağrı ≈ 7 s, DNS) |
| Girdi token / karar | 2.059 (≈ $0,00009) |
| Yön dağılımı (A) | **flat 48** (marj 0,20 ile hiçbir barda long/short) |
| Rejim dağılımı (A) | trend_asagi 27 · belirsiz 20 · trend_yukari 1 |
| `yon_guven` medyan · `cekimser` medyan | 0,53 · 0,53 |
| Dondurma | `data/semantik/jev/997a12f1390f/` (manifest `leak_riski: true`) |
| Değerlendirme | `kanit: false`; `cekimserlik_orani 1,0`; `yonlu 0`; `al_tut` 4h isabeti 23/44 (CI 0,38–0,66) |

**Okuma (yorum değil, tespit):** bu 48 barda Jev marj kuralıyla **hiç yön vermedi**. Bu bir
sonuç, ayarlanacak bir şey değil: marj koşudan önce sabitlendi (K-074/6). Gölge penceresinde
çekimserlik oranı 1,0'a yakın kalırsa raporun ilk satırı bu olur ve "yön isabeti" satırı
`n=0` ile boş kalır — o da geçerli bir araştırma sonucudur (spec §46). Marjı düşürerek yön
üretmek yeni bir çekiliştir ve hipotez defterine satır ister.

### 2.3 Gölge kurulumu (gerçek Binance)

`sq jev golge --kosu golge-kuru-deneme --kuru`: pencere 1.248 bar (depo + REST, hepsi
`backfilled`, son 2026-09-19 16:00 UTC), funding 360 ödeme, boşluk 0. Canlı koşu
`golge-deneme-1` 17:23 UTC'de başlatıldı. **İlk canlı karar** (17:00 barı, kapanış 18:00 UTC):
`gecerli`, `ileriye_donuk=true`, `leak_riski=false`, yön `flat` (P long 0,32 / flat 0,39 /
short 0,29; güven 0,08), rejim `trend_yukari`, kurulum 1,9, çekimser 0,38; üretim kapanıştan
10 s sonra; gecikme 13,1 s (ilk bağlantı DNS — bunun üzerine CLI'a başlangıçta bağlantı ısıtma
eklendi, sonraki barlar ≈0,3 s beklenir); durum hash'i zincirde, funding `guncel` (85. persentil).
Bu koşu **kirli ağaçta** (`git.dirty: true`) başladı: boru hattı denemesidir; ≥8 günlük asıl
gölge koşusu commit sonrası temiz ağaçta `golge-1` adıyla açılır.

## 3. Gölge penceresi bittiğinde doldurulacak tablo (sütunlar şimdi sabit)

Pencere: ≥ 8 gün (K-069 kalıbı; ≈ 190 karar). **"8 gün geçti" bir ölçüt değildir**; ölçütler
aşağıdaki satırlardır ve her biri örneklem büyüklüğü + Wilson %95 aralığıyla yazılır.

| Ölçüt | Tanım (`config/jev.json::sonuc`) | Kıyas |
| --- | --- | --- |
| Hata oranı | `durum_kodu ≠ gecerli` / toplam; kod başına sayım | — (≤ %5 beklenir; aşarsa önce altyapı) |
| Çekimserlik oranı | `yon = flat` / geçerli | — |
| Yön isabeti (4 bar) | long ∧ getiri>0 ∨ short ∧ getiri<0, yalnız yönlü kararlar | `al_tut` aynı barlarda (her zaman long) |
| Net getiri / karar (4 bar) | yön × getiri − gidiş-dönüş maliyet (`config/maliyet.json`) | `al_tut` brüt |
| MAE / MFE (4 bar) | `min(low)/giriş − 1`, `max(high)/giriş − 1` | — |
| Kalibrasyon | `yon_guven` kovaları (0–0,2–0,4–0,5–0,6–0,7–0,8–0,9–1,0) vs isabet; Brier; ECE | Güven ≠ olasılık hipotezi |
| Rejim başına | isabet, net getiri, `al_tut` | — |
| Tutarlılık | 24 kararda bir ikinci sorgu: olasılık sapması | replay'de ölçülen ±0,03 medyan |
| Gecikme | p50 / p95 / p99 | bar bütçesi 1 saat |
| `ileriye_donuk` | tüm geçerli kararlar `true` olmalı (bayat üretim = geçersiz) | — |

**Sonuç ne olursa olsun yazılır.** Negatif sonuç (isabet ≤ kıyas, çekimserlik 1,0, hata
oranı yüksek) silinmez, bir sonraki adımı belirler. Pozitif görünen bir sonuç "Jev çalışıyor"
demek değildir: B/C/D deneylerinin herhangi biri için program kaydı (K-051), K-045 istisnasının
sayısal gerekçesi ve yeni bir K-kaydı gerekir (K-074/1).

## 4. Açık kalemler

1. **Kesim tarihi UNKNOWN** — TypeSafe'e resmi beyan sorulacak (Scryne). Gelene kadar replay
   kanıt değil; gölge kesimden bağımsız.
2. **CI push edilmedi** — workflow dosyası yerelde; ilk push'ta doğrulanır.
3. **Çekimserlik 1,0 riski** — replay örnekleminde yön hiç çıkmadı; gölge de öyle çıkarsa
   "yön isabeti" ölçülemez. Bu durumda marj değil, soru **değişmez**; sonuç yazılır.
4. **OI yok** (karar 4); **haber/makro/çoklu sembol yok** (kapsam). Her biri ayrı program.
