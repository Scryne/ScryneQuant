---
proje: ScryneQuant
faz: 10
tarih: 2026-09-16
type: rapor
karar: K-057
---
# Faz 10 — Çok enstrümanlı araştırma çekirdeği

Bu faz **strateji aramadı.** Ölçülen şey çekirdeğin kendisi: tek enstrümanın çok
enstrümanlının özel hâli olmaya devam edip etmediği, evrenin geleceğini görmenin
engellenip engellenmediği, ve portföy kurma katmanının bir onay katmanına dönüşüp
dönüşmediği. Kararlar `docs/Kararlar.md` K-057'de.

## 0. Bitti kriteri tablosu

| Kriter | Sonuç |
| --- | --- |
| Tek enstrüman özel hâl: Faz 3 referansı bit düzeyinde aynı | ✅ İki senaryo da Decimal referansla **1e-12 bağıl tolerans** içinde; ayrıca gerçek 5,2 yıllık veride 12 noktalık tarama sonucunun **tüm** ekonomik değerleri değişmedi (§3) |
| Çok enstrümanlı bağımsız referans: ≥2 enstrüman, ≥10 işlem | ✅ `tests/fixtures/coklu_referans.json` — senaryo C **12 tur / 2 enstrüman**, kapalı formülle çapraz doğrulandı (azami bağıl fark **4,39e-49**); senaryo D eşzamanlı dengeleme, 4 barda satış+alım birlikte |
| Üretici `scryne_quant`ı import etmiyor (K-029) | ✅ `ast` taramasıyla zorlanıyor |
| Evren look-ahead testi yeşil | ✅ Fiyat **ve** üyelik geleceği bozuluyor + bir sembol tamamen delist ediliyor; 5 kesme noktasında bit düzeyinde aynı. Negatif kontrol (evrenin geleceğine kasten bakan strateji) yakalanıyor |
| Determinizm: aynı veri + config → aynı `sonuc_hash` | ✅ Birim testte ve gerçek evren koşusunda (`062dac2f87a80bf5`, iki koşu) |
| Risk motoru çok enstrümanlı hedefi onaylıyor/reddediyor | ✅ İki yeni portföy limiti; `test_risk_portfoy.py` 17 vaka |
| `test_risk_bypass.py` hâlâ yeşil | ✅ Değişmedi; ayrıca motor yolunda promotion'suz stratejinin fill üretemediği ölçüldü |
| Portföy kurma **izin veren** katman değil | ✅ Kurmanın %80'lik önerisi risk motorunun %30 tavanında kesiliyor (`test_risk_portfoy.py::TestKurmaIzinVeremez`) |

**Test:** 1.351 geçti, 1 atlandı (faz başında 1.229) — 122 yeni test.

## 1. Ne kuruldu

| Katman | Modül | İşi |
| --- | --- | --- |
| Sözleşme | `strategy/hedef.py` | `HedefPortfoy` — sembole göre sıralı `Sinyal` demeti |
| Sözleşme | `strategy/evren.py` | `EvrenGorunumu` / `EvrenBaglam` — `t` anında üyelik + kesilmiş enstrüman görünümü |
| Sözleşme | `strategy/temel.py` | `PortfoyStratejisi` + `TekEnstruman` sarmalayıcısı |
| Kurma | `strategy/kurma.py` | Oynaklık ayarlı boyut, korelasyon budaması, konsantrasyon, turnover bandı |
| Defter | `portfolio/durum.py` | `Pozisyon` (paylaşılan aritmetik) + `CokluPortfoy` |
| Motor | `backtest/coklu_motor.py` | Event loop; `backtest/motor.py` artık **sarmalayıcı** |
| Fill | `backtest/fill.py` | `emir_hazirla_genel` (tek çekirdek) + `emirleri_hazirla` (önce satış) |
| Risk | `risk/motor.py` | `portfoy_degerlendir` + iki portföy limiti |
| Metrik | `backtest/metrikler.py` | VaR/CVaR (%95, %99) + kapasite (ADV oranı) |
| Veri | `data/izgara.py` | Ortak ızgara, `listelenmedi` doldurma, PIT üyelik matrisi |
| Koşu | `research/evren_kosu.py` | Tablo → ızgara → üyelik → görünüm |
| Kıyas | `strategy/kutuphane/evren_esit_agirlik.py` | Evren kıyası (K-030) — **aile değil** |
| CLI | `sq evren backtest` | Evren üzerinde koşu |

## 2. Çok enstrümanlı bağımsız referans

Faz 3'ün kalıbı aynen tekrarlandı ve bir madde eklendi.

| Katman | Ne kanıtlıyor |
| --- | --- |
| Sayısal | Referans `Decimal` (prec=50), motor `float64`. Aynı kayan nokta hatasını iki tarafta birden yapmak mümkün değil |
| Cebirsel | Senaryo C kapalı formülle doğrulandı. **Formül Faz 3'ünkiyle birebir aynı metin** — ve bu kanıtın kendisi: iki enstrüman arasında dönüşümlü işlem yapmak, tek enstrümanla işlem yapmaktan farklı bir aritmetik gerektirmiyor |
| Yapısal | Senaryo D aynı barda satış+alım içeriyor; sıralama kuralı (önce satış, tek özkaynak anlık görüntüsü, nakit tavanı) `coklu_motor.py`nin **docstring'inden** yazıldı, kodundan değil |

Senaryo D'nin kanıt gücü daha zayıf ve bu bilinçli bir kabul: kapalı formül orada geçerli
değil. Üretici, senaryonun gerçekten karışık bar ürettiğini **sayarak** kaydediyor
(`ayni_barda_satis_ve_alim: 4`); sıfır çıksaydı dosya yazılmıyor.

## 3. Beklenmeyen bulgu: `sonuc_hash` zaten kaymıştı

Faz 10'un motoru bit düzeyinde aynı çıktı ama **kayıt hash'i değişti.** Sebep arandığında
çıkan şey Faz 10 değildi:

- `sq lab dogrula` komutu, kayıttaki strateji adını `kayit["girdi"]["strateji"]` diye
  okuyordu; oysa `deney.kaydet` onu **üst düzeye** yazıyor. Yani komut **her** kayıtta
  `KeyError` veriyordu ve Faz 4'ün *"herhangi bir deney kaydından yeniden üretilebiliyor"*
  kriterinin kanıtı çalıştırılamıyordu. Düzeltildi; `stres`, `monte_carlo` ve `karsilastirma`
  kayıtları artık birebir yeniden üretiliyor.
- Düzeltildikten sonra `tarama` kaydı yine uyuşmadı — **Faz 10 öncesi ağaçta da**
  (`073f7f6867ab9bf1` vs kayıt `58bceaed0fe1d6a7`). Alan alan karşılaştırıldığında
  **getiri, Sharpe, işlem sayısı, drawdown, profit factor: hepsi birebir aynı.** Değişen tek
  şey `sonuc_hash`ti.
- Sebep: `atlama_sayimi` sıfır sayaçları da yazıyor ve o liste `AtlamaSebebi` enum'unun
  **bugünkü** hâlinden türüyor. Faz 5 `risk_reddetti`, Faz 6 `veri_bayat` ekledi; ikisi de o
  koşularda hiç tetiklenmemişken hash'i değiştirdi.

**Düzeltme (K-057/6):** `sonuc_hash`e artık yalnızca **sıfır olmayan** atlama sayaçları
giriyor. Kayıt okunabilirliği için sıfırlar yazılmaya devam ediyor. Geçmiş kayıtlar geri
gelmiyor (eski hash tam listeyle hesaplanmıştı) ama bundan sonra bir atlama sebebi eklemek
eski koşuları yeniden üretilemez yapmıyor. Test: `test_coklu_motor.py::TestKayitDayanikliligi`
— sıfır sayaç hash'i değiştirmiyor, sıfır olmayan değiştiriyor.

Bu bulgu fazın kriterlerinden biri değildi; aranan şey değil, sebebi aranırken çıkan şeydi.

## 4. Evren look-ahead: ikinci biçim

`test_look_ahead.py` fiyat geleceğini ölçüyor. Faz 10 ikinci biçimi ekledi: **hayatta kalma
geleceği.** Ölçüm iki eksende birden bozuyor ve `t`ye kadarki kararların bit düzeyinde aynı
kalmasını istiyor:

| Bozma | Ne taklit ediyor |
| --- | --- |
| `t` sonrası fiyatlar rastgele | Klasik look-ahead |
| `t` sonrası üyelik tersine çevriliyor | Evren kuralının geleceğini görmek |
| Bir sembol `t` sonrasında tamamen siliniyor | Bugünkü listeden evren kurmak (hayatta kalma yanlılığı) |

Üçü de, ikisi birlikte de yeşil; üyelik bozması ayrıca **5 farklı kesme noktasında**
(bar 30, 80, 150, 220, 298) tekrarlanıyor. **Testin testi:** kasten `uyelik[i+1]`e bakan bir
strateji yazıldı ve test onu yakaladı. Ayrıca evren **geçmişi** değiştiğinde kararların
değiştiği de kontrol ediliyor — aksi hâlde dört testin dördü, evreni hiç okumayan bir
stratejiyle de yeşil olurdu.

## 5. Gerçek evrende ölçümler

`sq evren backtest`, `data/evren/_evren/27b7a16ed0ed.parquet` (N=50, hacim ≥ 30 M USDT,
109 ay). **Aşağıdaki sayılar bir strateji sonucu değil, kıyas ve makine ölçümüdür.**

### 5.1 Ölçek, süre, bellek

| Pencere | Sembol | Bar | Üye bar | Dizi belleği | Kurulum | Koşu |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025-01…2026-08 | 205 | 15.314 | 759.255 | 279 MB | 4,5 s | 2,1 s |
| 2023-01…2026-08 | 323 | 32.857 | 1.637.047 | 945 MB | 12,3 s | 6,9 s |
| 2021-01…2026-08 | 410 | — | — | — | (koşulmadı) | — |

Ölçek doğrusal: bellek ≈ sembol × bar × 80 B. 410 sembollü tam geçmiş ~3-4 GB eder; bu
K-057'nin birinci geri dönüş koşulu (4 GB) ile aynı mertebede, yani akış kurulumu **henüz
gerekmiyor ama uzak da değil.**

### 5.2 Evren kıyası (K-030) — alfa değil, sıfır noktası

| Pencere | Varyant | Getiri | Sharpe | MaxDD | İşlem | Turnover | Maliyet |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025-01…2026-08 | eşit ağırlık | −%55,66 | −0,490 | %68,06 | 27 | 5,2× | 79 |
| 2025-01…2026-08 | oynaklık ayarlı | −%42,13 | −0,384 | %61,09 | 27 | 7,0× | 107 |
| 2023-01…2026-08 | eşit ağırlık | −%3,91 | +0,300 | %66,87 | 70 | 21,4× | 328 |
| 2023-01…2026-08 | oynaklık ayarlı | **+%41,11** | **+0,447** | %57,53 | 70 | 29,0× | 443 |

İki varyantın farkı **yalnızca boyutlandırmadan** geliyor: aynı evren, aynı seçim, aynı
yeniden dengeleme takvimi. Oynaklık ayarlı boyut her iki pencerede de hem getiriyi hem
Sharpe'ı iyileştirdi ve düşüşü azalttı — **ama turnover'ı da artırdı** (5,2→7,0 ve
21,4→29,0; ikisi de yaklaşık +%35).
Bu bir alfa bulgusu değil; portföy kurma yönteminin bir şey yaptığının ve maliyetinin
ölçülebildiğinin kanıtı. Yöntemin bir çekiliş olarak değerlendirilmesi Faz 11'in kapılarıyla,
bir program kaydı altında (K-051) yapılır.

### 5.3 Yeni metrikler gerçekten ölçülüyor

| Metrik | 2023-01…2026-08 (eşit) |
| --- | ---: |
| VaR %95 (bar) | %0,989 |
| CVaR %95 (bar) | %1,679 |
| Kapasite, azami fill / 30 günlük ADV | %0,0082 |
| Kapasite, ortalama | %0,0006 |
| `bayat_degerleme` | 0 |

**Kapasite ölçüsü sıralamanın yanlış olduğunu yakaladı.** İlk uygulamada kıyasın skoru sabit
bırakılmıştı ve tavan bağladığında sıra sembol adına düşüyordu — yani kıyas, evrenin
**alfabetik** ilk 10'unu taşıyordu. Azami kapasite oranı %0,167 çıktı. Sıralama evren
kuralının kendi ölçütüne (30 günlük ortalama kote hacim) bağlandığında aynı sayı **%0,0038**
oldu: **44 kat.** Ölçüm olmasaydı fark görünmezdi; getiri tablosu her iki hâlde de
"makul" görünüyordu.

Bu, `kote_hacim_sma` indikatörünün deftere eklenme sebebi: baz varlık hacmi
cross-sectional bir sıralamada karşılaştırılamaz (1 BTC ile 1 DOGE aynı sayı değildir).

`bayat_degerleme = 0`: bu pencerede pozisyon taşınan hiçbir enstrüman ortadan kaybolmadı.
Sayaç boş görünüyor ama ölü kod değil — birim testi (`test_coklu_motor.py`) yapay bir delist
ile kod yolunu çalıştırıyor. Faz 2'nin dersi: gerçek veride tetiklenmeyen bir kod yolu,
sentetik bozuk veriyle test edilmezse hiç test edilmemiş olur.

## 6. Portföy düzeyi risk

İki yeni limit, ikisi de `istah` kaynaklı ve **bugün bağlamıyor**:

| Limit | Değer | Gözden geçirme |
| --- | ---: | --- |
| `azami_brut_maruziyet` | 1,0 | Faz 12 — cross-sectional programın kapasite/korelasyon ölçümüyle |
| `azami_enstruman` | 1000 | Faz 12 — turnover ve ADV oranı ölçümüyle |

Bağlamamaları bilinçli: Faz 10 yöntemi *kurar*, iştahı ölçmez. Bugünden bir sayı yazmak,
ölçülmemiş bir kapı olurdu (K-019) — ve tek sembollü koşuların bit düzeyinde yeniden
üretilebilirliğinin ön koşulu da bu.

Davranış testle sabitlendi:

- Tavan **aşağı çeker, yukarı asla**; bol bütçe hedefleri büyütmez.
- Azaltan niyetlere uygulanmaz (brüt maruziyeti düşüren emri brüt tavanla engellemek,
  limitin amacının tersi).
- Mevcut maruziyetin **altına zorlamaz**: bir tavan satış emri üretmez.
- Bahsedilmeyen açık pozisyonlar da bütçeyi tüketir.
- Enstrüman sayısı tavanı yalnızca **yeni** girişleri eler; mevcut pozisyonlara ve çıkışlara
  dokunmaz. Eleme sırası stratejinin kendi `confidence`ına, eşitlikte sembol adına göre.
- Sinyal düzeyinde reddedilen bir hedef brüt bütçeden yer kaplamaz.

## 7. Açık kalemler (Faz 11/12'ye taşınanlar)

1. **Portföy limitlerinin sayıları.** İkisi de iştah ve ikisi de bağlamıyor; ölçüm Faz 12.
2. **Turnover bandı.** Varsayılan 0. Bandın sayısı gidiş-dönüş maliyetinden türetilebilir;
   ölçüm Faz 12.
3. **Korelasyon matrisi.** `sec()` destekliyor ama hiçbir kıyas kullanmıyor — nedensel bir
   korelasyon tahmincisi (rolling, PIT) Faz 12'nin işi. Bugün eksik çift **1,0** kabul
   ediliyor: ölçülemeyen guard geçilmiş sayılmaz.
4. **Bellek.** 4 GB eşiğine yaklaşıldığında akış kurulumu ölçülür (K-057 geri dönüş 1).
5. **`sq lab dogrula` ve `coklu_test`.** `coklu_test` kayıtları kaydından yeniden
   üretilemiyor ve artık bunu **adıyla** söylüyor (`TEKRAR_EDILEBILIR` listesi): girdisi bar
   verisi değil, append-only defterin kendisi. Defteri sürümlemek ayrı bir karar.
6. **Faz 4 kayıtlarının yeniden üretimi.** Ekonomik değerler aynı, hash'ler eski listeyle
   hesaplandığı için uyuşmuyor. Kayıtları yenilemek `sq lab tara` ile mümkün; Faz 11'de
   defter yeniden koşturulurken birlikte yapılır.
