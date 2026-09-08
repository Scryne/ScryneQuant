---
proje: ScryneQuant
created: 2026-09-08
type: spike-raporu
spike: 2
kapatir: K-017
status: tamamlandi
---
# Spike 2 — Veri hacmi, indirme süresi ve birincil timeframe

**Tarih:** 2026-09-08, 19:56–20:03 UTC · **Sembol:** BTCUSDT
**Kaynak:** `data-api.binance.vision`, `GET /api/v3/klines`, `limit=1000`, sayfalı
**Yöntem:** `research/spikes/spike2_veri_hacmi.py`, `spike2b_dongu_hizi.py`
**Ham çıktı:** `research/spikes/out/spike2.json`, `spike2b.json`, `spike2c.json`,
`gap_dagilimi.json`, `hareket_dagilimi.json`

## 1. Ne bilinmiyordu?

K-017 açıktı: birincil timeframe 1h mı 1m mi. Bu karar veri hacmini, indirme süresini,
depolama tasarımını ve Faz 4'ün parametre taraması bütçesini belirliyor. Masa başında
verilemezdi çünkü üç bilinmeyeni vardı: veri ne kadar yer kaplıyor, indirmek ne kadar
sürüyor, ve motor bu hacmi ne hızda geziyor.

K-001 "1h saniyeler, 1m dakikalar mertebesi" diyordu — bu bir tahmindi, ölçüm değil.

---

## 2. Ne ölçüldü?

### 2.1 İndirme — gerçek sayılar

| | **1h / 3 yıl** | **1m / 1 yıl** |
| --- | --- | --- |
| Aralık (UTC) | 2023-09-09 19:00 → 2026-09-08 19:00 | 2025-09-08 19:00 → 2026-09-08 19:00 |
| Bar sayısı | **26.281** | **525.601** |
| İstek sayısı | 27 | 526 |
| Duvar saati | **9,42 s** | **147,68 s** |
| Ağ süresi | 9,40 s | 146,85 s |
| Harcanan weight | 52 | 224 |
| Bar/saniye | 2.789 | **3.559** |

**Rate limit hiç zorlanmadı.** 526 çağrılık indirme 224 weight harcadı; dakikalık limit 6.000.
Yani indirme **tamamen ağ gecikmesiyle sınırlı** (ağ süresi duvar saatinin %99'u), rate
limitle değil. Faz 1'in indiricisi karmaşık bir kuyruğa ihtiyaç duymuyor.

### 2.2 Veri kalitesi — her iki timeframe de kusursuz

| Kontrol | 1h / 3 yıl | 1m / 1 yıl |
| --- | --- | --- |
| Beklenen bar | 26.281 | 525.601 |
| Gelen bar | 26.281 | 525.601 |
| **Eksik bar** | **0** | **0** |
| Tekrar eden timestamp | 0 | 0 |
| Boşluk olayı | 0 | 0 |
| OHLC tutarsızlığı | 0 | 0 |
| Sıfır hacimli bar | 0 | 0 |

BTC/USDT'nin bu aralıkta **tek bar boşluğu yok.** K-006'nın kalite bayrakları yine de
gereklidir — ama bu sembol/aralık için `ok` dışı bar üretmeyecekleri şimdiden biliniyor. Bu,
kalite mekanizmasının kendisini test etmek için **yapay bozuk veri gerekeceği** anlamına
gelir; gerçek veriden `gap` örneği çıkmayacak.

### 2.3 Boyut

| Format | 1h / 3 yıl | 1m / 1 yıl |
| --- | --- | --- |
| Ham JSON (ağdan gelen) | 4,51 MB | 85,22 MB |
| CSV | 1,69 MB | 32,02 MB |
| **Parquet + zstd** | **0,997 MB** | **14,21 MB** |
| pandas bellek (deep) | 1,40 MB | 28,07 MB |

### 2.4 Beş yıllık projeksiyon (ölçülen bar-başına değerlerden türetildi)

| | 1h | 1m |
| --- | --- | --- |
| Bar | 43.800 | 2.628.000 |
| Parquet (zstd) | **1,66 MB** | **71,04 MB** |
| İndirme | 0,26 dk | **12,31 dk** |
| RAM (pandas) | 2,33 MB | 140,35 MB |

**Ne hacim ne süre bir kısıt.** 5 yıllık 1m verisi 71 MB ve 12 dakikada iniyor. Depolama
veya indirme, timeframe kararının belirleyicisi değil.

### 2.5 Motor hızı — K-001'in tahmini ölçüldü

Gerçek BTC/USDT verisi üzerinde saf Python `on_bar` döngüsü. İki varyant ölçüldü çünkü tek
sayı yanıltıcı olurdu:

| Varyant | Bar/saniye |
| --- | --- |
| **Asgari** (dizi erişimi, int sinyal, basit pozisyon) | 5.147.117 |
| **Gerçekçi** (dataclass `Signal` nesnesi, risk kontrolü, equity/drawdown takibi, trade listesi) | **1.800.526** |

Gerçekçi varyantın projeksiyonu:

| Senaryo | Tek koşu | 100 parametre | 1000 parametre |
| --- | --- | --- | --- |
| 1h, 5 yıl (43.800 bar) | 0,024 s | 2,4 s | **0,41 dk** |
| 1m, 5 yıl (2.628.000 bar) | 1,46 s | 2,4 dk | **24,3 dk** |

İndikatör hesabı ayrı ölçüldü: 525k bar üzerinde iki SMA, vektörize, **0,020 s** — döngünün
yanında ihmal edilebilir.

**K-001'in tahmini fazla karamsardı.** 1m'de 1000 parametrelik bir tarama 24 dakika; "dakikalar
mertebesi" doğru ama sonucu şu: **hesaplama maliyeti de timeframe kararının belirleyicisi
değil.** Her iki timeframe de rahatça çalışıyor.

*Uyarı: bu sayılar tek stratejinin, tek sembolün, tek işlemcide ölçümüdür. Faz 3'ün gerçek
motoru daha fazlasını yapacak (emir defteri simülasyonu, çoklu pozisyon, metrik toplama);
gerçekçi varyant bir **taban** değil **üst sınır** tahminidir. Faz 3 sonunda yeniden ölçülmeli.*

### 2.6 Kararı veren ölçüm: hareket / maliyet oranı

Hacim ve hız kısıt olmadığına göre karar başka bir yerden gelmek zorundaydı. Spike 4 gidiş-dönüş
maliyetini **20,02 bps** olarak ölçmüştü. Buna karşı bir barın tipik hareketi:

| | Ortalama | p50 | p75 | p95 | p99 |
| --- | --- | --- | --- | --- | --- |
| **1 dakikalık hareket** (bps) | 3,84 | **2,42** | 5,01 | 12,32 | 22,64 |
| **1 saatlik hareket** (bps) | 32,30 | **20,85** | 40,81 | 100,45 | 187,29 |

Bu tablodaki tek satır kararı veriyor:

```
Gidiş-dönüş maliyeti          : 20,02 bps   (Spike 4, ölçüldü)
Medyan 1 dakikalık hareket    :  2,42 bps   -> maliyetin 1/8'i
Medyan 1 saatlik hareket      : 20,85 bps   -> maliyetle aynı mertebede
```

**1m barda çalışan bir strateji, tipik bir barın 8 katı büyüklüğünde bir hareketi
yakalamak zorundadır — sadece başabaş kalmak için.** 1h barda bu oran ~1. İkisi de kolay
değil, ama 1m'nin engeli **8,6 kat** daha yüksek.

Bu, "1m daha çok veri, daha çok fırsat" sezgisinin tam tersini söylüyor: daha çok bar, bar
başına daha küçük hareket ve **bar başına aynı sabit maliyet** demek.

---

## 3. Karar ne oldu?

**K-017 kapandı → `kabul`. Birincil timeframe: 1h.**

Gerekçe hacim veya hız değil — ikisi de kısıt çıkmadı. Gerekçe **ölçülen hareket/maliyet
oranı**: 1h barın medyan hareketi gidiş-dönüş maliyetiyle aynı mertebede (20,85 vs 20,02 bps),
1m barınki maliyetin sekizde biri (2,42 bps).

**1m verisi yine de indirilir ve saklanır**, ama strateji timeframe'i olarak değil. Üç işi var:

1. **Slippage/execution kalibrasyonu** (K-020 → K-021) — 1h bar içindeki fiyat yolunu
   görmenin tek yolu.
2. **Faz 3'ün fill gerçekçiliği** — bir 1h barın içinde stop'un tetiklenip tetiklenmediği
   yalnızca 1m ile bilinebilir. 1h OHLC'den "high stop'a değdi mi" diye bakmak bir
   tahmindir; 1m ile ölçümdür.
3. **Faz 7'nin emir testleri** — testnet execution'ı dakika ölçeğinde davranır.

Faz 1'de indirilecek: **BTC/USDT 1h, 5 yıl** (birincil) + **1m, 3 yıl** (yardımcı).
Ölçülen değerlerden projeksiyon: ~1,7 MB + ~43 MB parquet, toplam ~8 dakika indirme.

### Faz 1'e bağlayıcı geçen ölçüm sonuçları

1. **İndirme ağ sınırlı, rate limit sınırlı değil** — 526 çağrı / 224 weight / 6.000 limit.
   Paralel indirme eklenirse asıl kazanç oradan gelir, kuyruk optimizasyonundan değil.
2. **Kalite mekanizmasını test etmek için yapay bozuk veri gerekiyor** — 3 yıllık 1h ve
   1 yıllık 1m verisinde tek bir `gap`/`duplicate`/`suspect` bar yok. K-006'nın kod yolları
   gerçek veriyle hiç tetiklenmeyecek; fixture ile test edilmeli.
3. **Hesaplama bütçesi Faz 4'ü kısıtlamıyor** — 1h'de 1000 parametrelik tarama 25 saniye.
   K-001'in "vektörize tarama katmanı gerekebilir" ihtiyatı 1h için gereksiz.

---

## 4. Beklenmeyen bulgu — K-020'nin yöntemi yanlış

K-020, `slippage_bps`'in `|open[t+1] − close[t]| / close[t]` dağılımından kalibre edilmesini
öngörüyordu. **Bu dağılım ölçüldü ve yöntemin yanlış olduğu ortaya çıktı.**

| | n | Tam sıfır oranı | Ortalama | p50 | p75 | p95 | p99 | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1h | 26.280 | **%52,20** | 0,0022 | 0,0000 | 0,0014 | 0,0026 | 0,0205 | 1,61 |
| 1m | 525.600 | **%51,84** | 0,0024 | 0,0000 | 0,0013 | 0,0016 | 0,0379 | 17,17 |

(bps cinsinden)

K-020'nin önerdiği "muhafazakâr 75. persentil" **0,0014 bps** verirdi — geçici değer olan
5,0 bps'in **3.500'de biri.**

**Neden yanlış:** kripto piyasası 7/24 kesintisiz. `open[t+1]`, `close[t]`'in birkaç
milisaniye sonrasıdır — arada piyasa kapanışı yok, boşluk yok. Ölçüm bunu doğruluyor: vakaların
**yarısında iki fiyat birebir aynı.** Bu dağılım bir yürütme belirsizliği değil, iki komşu
işlemin tick farkını ölçüyor.

Spike 4 "slippage bir spread proxy'si değil, fiyat hareketi proxy'sidir" diyerek doğru
yöne dönmüştü; ama ölçtüğü aralığı yanlış seçti. K-004'ün `t+1` açılış fill'i **saatlerce
süren bir belirsizlik penceresi değil** — veri düzeyinde neredeyse anlık.

**Gerçek belirsizlik penceresi** bar kapanışı ile emrin borsada dolması arasındaki süredir:
Spike 1'de ölçülen ağ gecikmesi (p50 ~300 ms, kuyruk 1,6 s) artı emir işleme. Bu pencerede
fiyatın ne kadar oynadığı ise ölçüldü — 1 dakikalık hareket dağılımı (§2.6) bunun
**muhafazakâr üst sınırı**, çünkü gerçek pencere bir dakikadan kısa:

```
1 dakikalık hareket   p50 = 2,42 bps   p75 = 5,01 bps   p95 = 12,32 bps
1m bar içi salınım    p50 = 4,28 bps   p75 = 7,82 bps   p95 = 17,48 bps
```

Geçici `slippage_bps = 5,0` değeri, tesadüfen 1 dakikalık hareketin 75. persentiline
(5,01 bps) denk geliyor — yani **büyüklük mertebesi doğruydu, türetme yolu yanlıştı.**

Bu bulgu **K-021** olarak kaydedildi; K-020 `değiştirildi` durumuna geçti.

## Kaynaklar

- `research/spikes/spike2_veri_hacmi.py`, `spike2b_dongu_hizi.py` (atılacak kod)
- `research/spikes/out/spike2.json`, `spike2b.json`, `spike2c.json`
- `research/spikes/out/gap_dagilimi.json`, `hareket_dagilimi.json`
- Ölçüm aralığı: 2026-09-08T19:56Z – 20:03Z
