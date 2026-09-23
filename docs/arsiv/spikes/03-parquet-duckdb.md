---
proje: ScryneQuant
created: 2026-09-08
type: spike-raporu
spike: 3
kapatir: K-011
status: tamamlandi
---
# Spike 3 — Parquet + DuckDB doğrulaması

**Tarih:** 2026-09-08, 20:05 UTC
**Veri:** Spike 2'nin indirdiği gerçek BTC/USDT verisi — 1m 525.601 bar, 1h 26.281 bar
**Sürümler:** DuckDB 1.5.5, PyArrow 25.0.1, pandas 3.0.5, Python 3.12.10
**Yöntem:** `research/spikes/spike3_parquet_duckdb.py` · Ham çıktı: `research/spikes/out/spike3.json`

## 1. Ne bilinmiyordu?

K-011 Parquet + DuckDB'yi seçmişti ama seçim **masa başında** yapılmıştı; kararın kendisi
"veri hacmi Faz 0 spike'ında ölçüldüğünde gözden geçirilir" notunu taşıyordu. Dört soru
açıktı:

1. Hangi sıkıştırma? (boyut / yazma / okuma dengesi)
2. Tek dosya mı, bölümlenmiş mi?
3. DuckDB'nin sorgu süresi kabul edilebilir mi?
4. **Parquet yazımı bit düzeyinde tekrarlanabilir mi?** — K-009 veri seti hash'i istiyor;
   dosya her yazımda farklı bayt üretiyorsa dosya hash'i kullanılamaz.

---

## 2. Ne ölçüldü?

### 2.1 Sıkıştırma (1m, 525.601 bar)

| Codec | Boyut | Yazma | Okuma (p50) |
| --- | --- | --- | --- |
| none | 26,076 MB | 0,129 s | 0,0195 s |
| snappy | 18,475 MB | 0,158 s | 0,0190 s |
| gzip | 12,557 MB | **6,275 s** | 0,0305 s |
| **zstd** | **14,208 MB** | **0,190 s** | **0,0224 s** |
| brotli | **11,817 MB** | 2,314 s | 0,0368 s |
| *(CSV, karşılaştırma)* | *32,021 MB* | — | *0,2667 s* |

**zstd seçildi.** brotli %17 daha küçük ama yazması **12 kat**, okuması %64 daha yavaş.
gzip'in yazması **33 kat** yavaş. snappy'nin okuma avantajı ölçülemeyecek kadar küçük
(%15, yani 3 ms) ama %30 daha büyük. zstd bu üç eksende de dengeli tek nokta.

CSV'yi referans olarak bırakmak gerekiyor: **Parquet+zstd, CSV'den 2,25 kat küçük ve
12 kat hızlı okunuyor.**

### 2.2 Yazma tekrarlanabilirliği (K-009'un ön koşulu)

Aynı DataFrame, 1,1 saniye arayla iki kez yazıldı ve dosyaların SHA-256'sı karşılaştırıldı:

| Codec | Bayt düzeyinde eşit mi? | SHA-256 (ilk 16) |
| --- | --- | --- |
| zstd | **evet** | `62e4b98222e074f7` / `62e4b98222e074f7` |
| snappy | **evet** | `304f65a300c7f01d` / `304f65a300c7f01d` |

**PyArrow'un Parquet çıktısı deterministik** — dosyaya yazma zamanı veya rastgele bir kimlik
gömülmüyor.

**Sonucu:** K-009'un istediği "veri seti hash'i" doğrudan **dosyanın SHA-256'sı** olabilir.
Ayrı bir içerik hash'i mekanizması gerekmiyor — ki bu, dosya kopyalanınca/taşınınca da aynı
kalan basit ve doğrulanabilir bir kimlik demek.

Yedek yol da ölçüldü: Arrow buffer'larından türetilen içerik hash'i 525k bar için **0,018 s**
sürüyor ve parquet'ten geri okununca aynı değeri veriyor. Dosya hash'i bir gün yetmezse
(ör. bölümlenmiş depoya geçilirse) bu yol açık.

### 2.3 Bölümleme

| | Boyut | Dosya sayısı | Yazma |
| --- | --- | --- | --- |
| Tek dosya | **14,208 MB** | 1 | — |
| yıl/ay bölümlü | 16,730 MB | 13 | 0,089 s |

Bölümleme bu ölçekte **%18 daha çok yer kaplıyor** (her dosya kendi sözlüğünü ve
metadata'sını taşıyor).

### 2.4 DuckDB sorgu süreleri (parquet üzerinde, tabloya yüklemeden)

| Sorgu | p50 | Sonuç |
| --- | --- | --- |
| `COUNT(*)` tam tarama | **0,0006 s** | 1 satır |
| `min/max(open_time)` | 0,0007 s | 1 satır |
| Tek gün aralığı (tek dosya) | 0,0151 s | 1 satır |
| Tek gün aralığı (bölümlü) | **0,0042 s** | 1 satır |
| Bölüm atlamalı (`yil=2026 AND ay=3`) | 0,0029 s | 1 satır |
| **1m → 1h yeniden örneklem (OHLCV)** | **0,0870 s** | 8.761 satır |
| Boşluk tespiti (`lag` ile ardışık fark) | 0,0313 s | 1 satır |
| Tüm sütunları pandas'a getir | 0,3474 s | 525.601 satır |

`COUNT(*)` ve `min/max` bir milisaniyenin altında çünkü DuckDB bunları Parquet'in kendi
metadata'sından okuyor, veriyi hiç açmıyor.

Bölümleme aralık sorgusunu **3,6 kat** hızlandırıyor (15,1 → 4,2 ms) — ama ikisi de 20
milisaniyenin altında. Bu fark hiçbir yerde hissedilmez.

**1m → 1h yeniden örneklem 87 milisaniye.** Bu önemli: 1m verisinden 1h barlarını üretmek
pratikte bedava, yani her iki timeframe'i ayrı ayrı saklamak zorunlu değil (yine de
saklanacak — indirme de bedava ve iki kaynağın birbirini doğrulaması bir kalite kontrolü).

### 2.5 DuckDB native tablo vs Parquet

| | Boyut | Tek gün sorgusu (p50) |
| --- | --- | --- |
| Parquet + zstd | 14,208 MB | 0,0151 s |
| DuckDB native `.duckdb` | **8,262 MB** | **0,0006 s** |

Native tablo %42 daha küçük ve sorgusu **25 kat** hızlı (oluşturma maliyeti 0,142 s).

**Yine de Parquet seçiliyor** — ve gerekçe performans değil, K-009: bir `.duckdb` dosyası
canlı bir veritabanı durumudur; Parquet dosyası içeriği hash'lenebilen, kopyalanabilen,
sürümlenebilen bir yapıdır (§2.2'de deterministikliği kanıtlandı). 15 milisaniye ile
0,6 milisaniye arasındaki fark bu projede hiçbir yerde darboğaz değil; reproducibility ise
birinci sınıf gereksinim.

### 2.6 Faz 3'ün gerçek iş yükü: motora veri yükleme

| İşlem | p50 |
| --- | --- |
| `pandas.read_parquet` (1m, 1 yıl) | 0,0236 s |
| DuckDB → Arrow | **0,0128 s** |
| pandas → numpy (`to_numpy`) | 0,0004 s |
| RAM ayak izi (pandas, deep) | 28,07 MB |

### 2.7 Beş yıllık 1m projeksiyonu (ölçülenden türetildi)

| | Değer |
| --- | --- |
| Bar | 2.628.000 |
| Parquet (zstd) | **71,0 MB** |
| RAM (pandas) | 140,3 MB |
| Tam yükleme | **0,12 s** |

---

## 3. Karar ne oldu?

**K-011 kapandı → `kabul`, değişiklik yok.** Parquet + DuckDB seçimi ölçümle doğrulandı;
gözden geçirme notu ("hacim ölçüldüğünde tekrar bak") kapatıldı. Hiçbir eşik zorlanmadı:
5 yıllık 1m verisi 71 MB, tamamı 0,12 saniyede RAM'e giriyor, en ağır sorgu 87 milisaniye.
PostgreSQL'in Faz 5'e ertelenmesi doğrulandı — Faz 1-4'ün veri erişimi için sunucu süreci
çalıştırmanın hiçbir getirisi yok.

Karara eklenen, ölçümden gelen üç somut nokta:

1. **Sıkıştırma: `zstd`.** Ölçülen dengeye göre — brotli/gzip'in boyut kazancı, yazma
   süresindeki 12–33 katlık kaybı karşılamıyor.
2. **Düzen: sembol/timeframe başına tek dosya.** Bölümleme bu ölçekte %18 daha çok yer
   kaplıyor ve kazandırdığı 11 milisaniye hiçbir yerde hissedilmiyor. Karmaşıklık
   karşılıksız. *Gözden geçirme koşulu: tek dosya 500 MB'ı aştığında veya çok sembollü
   çalışmaya geçildiğinde yıl bazlı bölümleme yeniden değerlendirilir.*
3. **Veri seti hash'i = Parquet dosyasının SHA-256'sı.** Yazımın bit düzeyinde
   tekrarlanabilir olduğu ölçüldü; K-009 ayrı bir içerik-hash mekanizması gerektirmiyor.

## Kaynaklar

- `research/spikes/spike3_parquet_duckdb.py` (atılacak kod, commit edilmiyor)
- `research/spikes/out/spike3.json`
- Ölçüm zamanı: 2026-09-08T20:05Z
