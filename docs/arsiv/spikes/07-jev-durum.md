---
proje: ScryneQuant
spike: 7
type: spike-raporu
tarih: 2026-09-19
status: kapandi
---
# Spike 7 — Jev karar katmanı: 4h bağlam, betimleyici durum, kesim tarihi

**Soru (üç parça):** (a) 4h bağlam 1h barlardan yalnızca kapanmış kovaları toplayarak
üretilirse Binance'in kendi 4h dosyasıyla aynı çıkıyor mu, yoksa ikinci bir akış mı gerekir?
(b) Kodla hesaplanmış **betimleyici** bir 1h+4h+funding özetine Jev ne kadar tutarlı cevap
veriyor; gecikme ve token maliyeti ne? (c) Jev'in yayın ve eğitim kesim tarihi
doğrulanabiliyor mu (K-049/4)?

**Bu spike isabet ölçmedi ve bilerek ölçmedi.** Hiçbir cevap ileri getiriyle
karşılaştırılmadı; bakmak K-039'un saydığı bir çekiliş olurdu. Ölçülen şey boru hattının
kendisi: eşitlik, sapma, gecikme, token, tarih kanıtı. Hipotez defterine kayıt yok.

**Ölçüm:** 2026-09-19 · `research/spikes/spike7_jev_durum.py` · ham çıktı
`runs/spike7/sonuc.json` (ikisi de `.gitignore`'da) · model `jev-1.13.0` · SDK
`typesafe-sdk 0.6.0` · veri `data/market/BTCUSDT/{1h,4h}.parquet`, `data/funding/BTCUSDT.parquet`.

## (a) 1h → 4h toplama Binance 4h ile bit düzeyinde aynı (OHLC + trades)

45.576 1h bar → 11.397 4h kova; 11.390'ı tam (4/4 bar). Binance 4h dosyasındaki aynı
`open_time`'lı 11.390 barla karşılaştırma:

| Alan | Bit-eşit | Eşit olmayan | Azami göreli fark |
| --- | --- | ---: | ---: |
| open, high, low, close | **evet** | 0 | 0 |
| trades | **evet** | 0 | 0 |
| volume | hayır | 2.000 | 2,2 × 10⁻¹⁶ |
| quote_volume | hayır | 1.973 | 2,2 × 10⁻¹⁶ |

Hacim farkı toplama sırasından gelen tek ulp (float64 ε = 2,2 × 10⁻¹⁶); Binance dört barı
başka sırayla topluyor. Fiyat ve işlem sayısı birebir.

Tam olmayan 7 kova: seri başı (2021-06-28 00:00, 1 bar), seri sonu (2026-09-09 08:00,
2 bar) ve 1h serisindeki 3 `gap` + 1 `suspect` barın düştüğü 5 kova. Binance 4h dosyası bu
kovaları "ok" barlarla dolduruyor — yani **Binance 4h'te 1h'de görünmeyen veri var**; 1h
serisindeki boşluk 4h'te kapanmış gibi görünüyor. Toplama yaklaşımı bu barları `eksik`
işaretliyor, uydurmuyor (K-024).

**Karar:** 4h bağlam 1h'den toplanır; ikinci akış **yok**. Tek kaynak, tek doğrulama
(`data/dogrulama.dogrula`), sızıntı testi tek seride. Kovaya giren 1h barlardan biri `ok`
değilse ya da 4 bar yoksa o 4h barı durumda `eksik`tir. Hacim betimleyici alanlara
yuvarlanarak girdiğinden ulp farkının durum hash'ine etkisi yok; hacim şu an durumda
kullanılmıyor.

## (b) Betimleyici durum: tutarlı ama sınırda kararsız; sayısal karşılaştırma güvenilmez

Durum ≈ 900 karakter, 1.886 girdi token'ı (≈ $0,00008/karar). Bloklar: `1h`, `4h_kapanmis`
(her biri EMA sıralaması, RSI + bant, ATR% + volatilite bandı, Bollinger konumu, ROC,
20-bar zirve/dip uzaklığı, yapı etiketi), `funding` (oran, 90 gün persentili, bant, tazelik).
Bütün sayılar kodda hesaplanıp yuvarlandı; Jev'e dizi gitmedi. Aynı bar için iki kurulumda
`durum_hash` eşit.

**Gecikme:** ilk çağrı 12,9 s (DNS, bilinen; `TypeSafe.md`), sonrakiler medyan **0,31–0,36 s**.
1h bar bütçesi içinde fazlasıyla; istemci süreç boyunca açık tutulacak.

**Tutarlılık** (aynı durum, aynı sorular, 3–5 tekrar, üç farklı bar):

| Bar | `yon` seçimleri | P aralığı | güven | `rejim` | `kurulum` skor aralığı | Noul aralığı |
| --- | --- | ---: | --- | --- | ---: | ---: |
| 2026-09-09 09:00 | flat, **long**, flat, flat, flat | 0,07 | 0,22–0,25 | 4× trend_yukari, 1× belirsiz | 0,13 | ≤ 0,06 |
| 2026-05-07 10:00 | 3× flat | 0,01 | 0,81–0,83 | 3× belirsiz | 0,05 | 0,02 |
| 2025-04-27 10:00 | 3× flat | 0,03 | 0,76–0,77 | 1× trend_yukari, 2× belirsiz | 0,08 | 0,01 |

Sapma `TypeSafe.md`'nin ölçtüğü bandın içinde (±0,01–0,09). İlk barda P(flat)=P(long)≈0,45
olduğu için **argmax koşular arasında değişiyor**; yani `choice` alanı tek başına kararlı bir
karar değil. Kalıcı olan olasılık vektörü.

**Sayısal karşılaştırma yanlış:** `f_kirilim_yakin` ("zirveye ya da dibe %1'den yakın mı")
sorusuna, zirve 1,02 % / dip 1,39 % uzaktayken Jev 0,86–0,87 "evet" dedi. Jaggedness
dokümanının söylediği şey (sayısal yakınlık, eşik kıyası güvenilmez) burada göründü.

**Kararlar:**
1. Karar alanı `choice` değil **olasılık vektörü + kodda eşik**: `yon` = argmax **yalnızca**
   P(argmax) − P(ikinci) ≥ önceden yazılı bir marj ise, aksi hâlde `flat`; marj
   `config/jev.json`'da ve gölge koşusundan önce sabit. Ham olasılıklar her kayıtta durur.
2. **Sayısal eşik gerektiren hiçbir soru Jev'e sorulmaz.** "Faktörler" iki sınıfa ayrılır:
   kodda hesaplanan etiketler (durumun parçası, deterministik) ve Jev'in yalnızca etiket
   birleşimini yargıladığı sorular (`yon`, `rejim`, `kurulum`, `cekimser`). Spec'teki
   `key_factors` bu projede birincisidir; Jev'in "faktör" Noul'ları yalnızca etiketleri
   okuyarak cevaplanabilecek biçimde yazılır ya da hiç sorulmaz.
3. Tutarlılık **kayıt altına alınır**: gölge koşusu her N. kararda aynı durumu ikinci kez
   sorup sapmayı yazar (kanıt değil, izleme).

## (c) Kesim tarihi: **UNKNOWN** — doğrulanabilir tek tarih yayın tarihi

Aranan yerler (2026-09-19): `GET /v1/models` (ham ve SDK), `docs.typesafe.ai/models.md`,
`model-jaggedness/jev-1.13.md`, `introduction.md`, `introduction/machine-learning-primer.md`,
`concepts/state.md`, `legal.md`, `sdk/python/changelog.md`, `llms.txt` indeksi.

| Tarih | Kaynak | Kanıt |
| --- | --- | --- |
| **Yayın:** `jev-latest` → 2026-09-10T18:38:01Z, `jev-preview` → 2026-09-10T18:39:06Z | `GET https://api.typesafe.ai/v1/models` `release_date` | `runs/spike7/` ve bu rapor; `/v1/models` yalnızca iki takma adı listeliyor, `jev-1.13.0` satırı yok (istekte pinlenince kabul ediliyor ve yanıtta `model="jev-1.13.0"` dönüyor) |
| **Eğitim kesimi:** — | hiçbir dokümanda yok | `models.md`: "Jev is not trained on customer requests or responses" — kesim değil, veri politikası |
| **Kullanılabilirlik:** ≥ 2026-09-16 (bu projede ilk çağrı, K-061) | `runs/gizli_tekrar/` | kayıt var |

**Karar:** `config/jev.json`'da `egitim_kesim_utc: null`, `kaynak: "dogrulanmadi"`, yayın
tarihi ayrı alanda kanıtıyla. Kesim bilinmediği sürece **geriye dönük her türetim**
`leak_riski=true` (K-049/4: bilinmeyen kesim, kesim öncesi demektir). Yayın tarihi kesim
**yerine geçmez**: bir model yayınlanmadan önce eğitilmiştir, yani gerçek kesim yayından
öncedir ve yayın tarihi hiçbir pencereyi temizlemez. İleriye dönük gölge kararları (bar
kapandıktan sonra, bar ömrü içinde üretilen) tanım gereği kesimden bağımsızdır: model o
anda gelecekteki fiyatı bilemez; kayıt `ileriye_donuk=true` ve `uretim_ms` ile bunu taşır.
TypeSafe'e (hello@typesafe.ai) resmi kesim beyanı sorulur; gelene kadar alan `null` kalır,
**uydurulmaz**.

## Neyi vaat etmiyor

- Jev'in yönü **isabetli** olduğunu söylemiyor; hiç ölçülmedi.
- Soru seti taslaktır; Phase 6'da dondurulup hash'lenir. Taslaktaki `f_kirilim_yakin`
  kaldırılacak (2. karar).
- 4h eşitliği yalnızca BTCUSDT'de ve yalnızca tam kovalarda ölçüldü; başka sembolde
  yeniden ölçülmeden genellenmez.
