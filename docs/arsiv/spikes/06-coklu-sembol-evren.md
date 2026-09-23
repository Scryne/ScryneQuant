---
proje: ScryneQuant
spike: 6
type: spike-raporu
tarih: 2026-09-12
status: kapandi
---
# Spike 6 — Çoklu sembol evreni: hayatta kalma yanlılığı olmadan kurulabilir mi?

**Soru:** Vizyon v2'nin ilk genişlemesi (K-053) kripto içinde çoklu sembol. Delist edilmiş
semboller dahil, her ay yalnızca o ay var olan sembollerden kurulan bir evren Binance'in
**ücretsiz** verisinden kurulabiliyor mu? Kurulamazsa her çoklu sembol backtest'i hayatta
kalma yanlılığı taşır ve cross-sectional ailenin tamamı ölçülemez olur.

**Neden spike:** Proje çalışma akışının 3. adımı: bilinmeyen bir veri kaynağı finalize
edilmeden önce ölçülür. Denetim-v2'nin B2 ve B3 bulguları bu cevaba bağlı. K-011'in dosya
düzeni ve K-034'ün 3. geri dönüş koşulu da *"çok sembollü çalışmaya geçildiğinde"* yeniden
ölçülecekti. Hacim projeksiyonu bu ölçümün girdisi.

**Bu spike sinyal gücü ölçmedi ve bilerek ölçmedi.** Getiri ya da sinyal ile hiçbir ilişkiye
bakılmadı; bakmak K-039'un saydığı bir çekiliş olurdu. Ölçülen tek şey verinin kendisi:
kapsam, süreklilik, hacim, boyut. Hipotez defterine kayıt yok.

**Ölçüm:** 2026-09-11T21:33:50Z · 475 s · `research/spikes/spike6_evren.py` ·
ham çıktı `research/spikes/out/spike6_evren.json`. Kaynaklar: `data.binance.vision` S3
listesi (aylık klines arşivi), `data-api.binance.vision/api/v3/exchangeInfo`, arşivin `1mo`
katmanındaki 25.349 aylık dosya (hatalı: 0).

## 1. Kapsam: delist edilmiş sembollerin geçmişi duruyor

| | Sayı |
| --- | ---: |
| Arşivdeki spot sembol | 3.710 |
| USDT paritesi | 735 |
| − kaldıraçlı token (`UP`/`DOWN`/`BULL`/`BEAR`) | 52 |
| − stablecoin/fiat taban (USDC, FDUSD, EUR, TRY…) | 24 |
| **Aday evren** | **659** |
| Bugün `TRADING` | 467 |
| Bugün `BREAK` (delist/askıda) veya exchangeInfo'da yok | 192 |
| **…bunlardan 1h geçmişi indirilebilen** | **191** |

192 ölü sembolün 191'inin tarihsel 1h barları arşivde duruyor. Tek istisna
(`USDSOLDUSDT`) arşivde 1h katmanı hiç olmayan bir sembol. Örnekler gerçekten indirildi:
`SRMUSDT` (2020-08 → 2022-11, 28 ay) ve `BCCUSDT` (2017-11 → 2018-11, 13 ay). İkisi de
bugün `BREAK`, ikisinin de dosyası açılıp satırları sayıldı.

**Sonuç: evet, ücretsiz veriden hayatta kalma yanlılığı olmayan bir evren kurulabilir.**

## 2. Yanlılığın büyüklüğü: her ayın likit evreninin ~beşte biri bugün yok

Evren PIT kuruldu: **M ayının evreni, M−1 ayının quote hacmine göre ilk N sembol.** Seçimde M
ayına ya da sonrasına ait hiçbir bilgi kullanılmadı. Soru: o evrenlere girmiş sembollerin
kaçı bugün `TRADING` değil?

| N | Evrene hiç girmiş sembol | Bugün ölü | Oran | Ay başına bugün-ölü oranı (medyan / en kötü) |
| ---: | ---: | ---: | ---: | --- |
| 30 | 302 | 72 | %23,8 | %14,3 / %33,3 |
| **50** | **412** | **104** | **%25,2** | **%18,0 / %34,0** |
| 100 | 540 | 169 | %31,3 | %22,6 / %44,0 |

Bugünkü listeden kurulan bir evren, her ayın likit isimlerinin **medyan %18'ini** atar, en
kötü ayda %34'ünü. Atılanlar rastgele değil: sonradan **başarısız olanlar**. Rakam bir
yuvarlama hatası değil; ders kitabındaki yanlılık, sayısıyla. Çoklu sembol çalışmasında
evren üyeliği bu yüzden bir zaman serisi olmak zorunda (K-052).

## 3. Evrenin zaman içindeki büyüklüğü: anlamlı pencere 2020-2021'den başlıyor

| Ay | Listelenmiş (aday) | Likit (önceki ay quote hacmi ≥ 30 M USDT ≈ 1 M/gün) |
| --- | ---: | ---: |
| 2018-01 | 6 | 6 |
| 2019-01 | 22 | 18 |
| 2020-01 | 85 | 35 |
| 2021-01 | 186 | 124 |
| 2022-01 | 309 | 297 |
| 2023-01 | 317 | 206 |
| 2024-01 | 361 | 338 |
| 2025-01 | 387 | 384 |
| 2026-01 | 431 | 266 |

2020 öncesinde evren 35 ismin altında; cross-sectional bir sıralama o dönemde istatistiksel
olarak zayıf. **Kullanılabilir pencere ≈ 2020-2026 (~6 yıl)**, 2021'den sonra ≥100 likit
isim. Bu, Faz 4'ün 5,2 yıllık tek sembol penceresiyle aynı mertebede. Cross-sectional aile
daha uzun bir geçmiş kazandırmıyor, genişlik kazandırıyor.

## 4. İki veri sözleşmesi bulgusu: ikisi de "neredeyse doğru" sınıfından

### 4a. Ticker bir enstrüman kimliği değil

`LUNAUSDT` arşivde 73 ay kesintisiz görünüyor (2020-08 → 2026-08) ve bugün `TRADING`. Günlük
satırlar başka bir şey söylüyor:

| Tarih | Açılış | Kapanış |
| --- | ---: | ---: |
| 2022-05-12 | 1,0782 | 0,00032 |
| 2022-05-13 | 0,00032 | **0,00005** |
| *(17 gün satır yok)* | | |
| 2022-05-31 | **1,00** | 8,87 |

Aynı ticker altında **iki farklı varlık** var: Terra Classic ve 2022-05-31'de listelenen yeni
LUNA. Seriyi olduğu gibi okuyan bir motor boşluğun iki yanını birleştirir ve **20.000 katlık**
(açılış/önceki kapanış) bir getiri görür. K-006 boşluğu işaretlerdi. Ama boşluk sonrası ilk
barın `ok` olması, kimlik değişikliğini **yakalamaz**: bayrak eksik barı işaretler,
değişen varlığı değil.

Sonuç: enstrüman kimliği `(venue, ticker)` değil, **geçerlilik aralığı taşıyan kanonik bir
kimlik** olmalı. Uzun bir boşluk artı imkânsız bir fiyat oranı, kimlik kırılması şüphesi
olarak yakalanmalı (Faz 9).

### 4b. Arşivin katmanları birbiriyle tutarlı değil

| Ay | `1mo` katmanında sembol | `1h` katmanında sembol |
| --- | ---: | ---: |
| 2026-02 | 447 | 447 |
| 2026-03 | **7** | 448 |
| 2026-04 | 249 | 450 |
| 2026-05 | 233 | 435 |
| 2026-06 | 228 | 446 |
| 2026-07 | **0** | 484 |
| 2026-08 | **0** | 491 |

Türetilmiş `1mo` katmanı 2026-03'ten beri eksik; `1h` tam. Hacim ölçümü bu yüzden 2026-02'ye
kadar güvenilir (yukarıdaki tablolar o aralıkta). Ders K-023'ün dersinin aynısı: kaynağın
türetilmiş bir katmanına güvenmek sessiz bir boşluk bırakır. **Evren hacmi bizim sakladığımız
barlardan hesaplanır, arşivin özet katmanından değil.** Data contract her katman için ayrı
bir tamlık kontrolü taşır.

## 5. Boyut: K-011 bozulmuyor, K-034'ün 3. koşulu gerçekleşiyor

| | |
| --- | --- |
| 1h sembol-ay (aday evren) | 25.955 |
| Bar (≈ 730/ay) | ≈ 18,9 milyon |
| Parquet tahmini (Faz 1'in ölçtüğü yoğunluk: 2,08 MB / 45.576 bar ≈ 45,6 B/bar) | **≈ 0,86 GB** |
| Arşiv zip medyanı (1h, 1 sembol-ay) | 31 KB → indirme ≈ 0,8 GB |
| İndirme süresi projeksiyonu (bu spike'ta 25.349 dosya ≈ 440 s, 32 iş parçacığı) | ≈ 8 dk |

Sembol başına tek dosya kalırsa en büyüğü BTC'ninki (2 MB) ve K-011'in 500 MB gözden geçirme
eşiğinin çok altında. Toplam 0,86 GB, DuckDB'nin tek süreçte rahatça taradığı büyüklük.
**K-011'in dosya düzeni değişmiyor.**

**K-034'ün 3. geri dönüş koşulu (çok sembollü çalışma) bu genişlemeyle gerçekleşiyor.** Ama
koşul PostgreSQL'i **otomatik** getirmiyor; kararın yeniden verilmesini getiriyor. O ölçüm,
çok sembollü operasyonel state'in gerçek yazma deseni belli olduğunda Faz 9'da yapılır.

## 6. Karar

- **K-053:** İlk genişleme kripto içinde yapılır. Hayatta kalma yanlılığı olmayan çoklu
  sembol evreni ücretsiz veriden kurulabilir.
- **K-052'ye bağlayıcı kısıtlar:** evren üyeliği PIT bir zaman serisidir; enstrüman kimliği
  ticker değildir; hacim kendi barlarımızdan hesaplanır.
- **Faz 9'un kapsamına girenler:** kanonik enstrüman kimliği + kimlik kırılması tespiti,
  PIT evren tablosu, katman başına tamlık kontrolü, K-034 yeniden ölçümü.
