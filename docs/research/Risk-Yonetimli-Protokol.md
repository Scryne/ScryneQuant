---
proje: ScryneQuant
tarih: 2026-09-23
karar: K-125
type: protokol
---
# Risk Yönetimli Promotion Protokolü (RYPP)

Kod: `src/scryne_quant/research/risk_protokolu.py` · Testler: `tests/unit/test_risk_protokolu.py` ·
Karar: K-125. Alfa yolunun 12 kapısı (K-119) **aynen** durur; RYPP ayrı bir yoldur ve alfa yolunu
gevşetmez.

**Soru:** Risk kontrollü sistematik maruziyet sağlayan bir strateji, önceden tanımlanmış kıyasa göre
azami düşüşü anlamlı biçimde azaltırken kabul edilebilir bir getiri/risk profili sağlıyor mu? Bunu
zamanlamayla mı yapıyor, yoksa yalnızca daha az maruziyet taşıyarak ya da şansla mı?

## 1. Kıyas (benchmark)

Stratejinin **en yüksek brüt maruziyetinde**, aynı **önceden tanımlanmış PIT evrende**, aynı dengeleme
takviminde ve aynı maliyet modeliyle pasif eşit ağırlık. Kripto için mevcut kıyas iskeleti
`evren_esit_agirlik` (K-030/K-072), `hedef_brut` stratejinin tavanına eşitlenir.

- **Temsil ettiği:** stratejinin açıp kapattığı pasif piyasa maruziyeti.
- **Dönem:** stratejiyle birebir aynı OOS barları (hizasız seri hata).
- **Maliyet:** aynı model; kıyasın dengeleme maliyeti de düşülür.
- **Nakit getirisi:** her iki tarafta 0 (motorla aynı). Tutucu yön: nakitte bekleyen stratejinin
  aleyhine.

Kıyas sonuç görüldükten sonra değiştirilemez; her hipotez kaydı kıyası adıyla taşır.

## 2. Birincil ve ikincil ölçüler

| Kod | Koşul | Eşik | Statü |
| --- | --- | --- | --- |
| P1 | Düşüş azaltımı `1 − MDD_S/MDD_K` | ≥ 0,25 | tasarım |
| P2a | Getiri korunumu: `CAGR_S ≥ 0,5·CAGR_K` (kıyas pozitifse), aksi hâlde `CAGR_S ≥ CAGR_K` | 0,5 | tasarım |
| P2b | Verimlilik: `MAR_S ≥ MAR_K` (MAR = CAGR / azami düşüş) | — | tasarım |
| P3 | **Plasebo:** gerçek takvimin MAR'ı > kaydırılmış takvimlerin (1 − α/k) persentili | α = 0,05 | kalibrasyon |
| S1 | 2x maliyette `MAR_S ≥ MAR_K` | — | tasarım |
| R1 | Başlangıç tarihi: ilk yarıdan 8 başlangıcın ≥ %70'inde P1 ve P2b | 0,70 | tasarım |
| R2 | Alt dönem: iki yarıda da `MDD_S ≤ MDD_K` | — | tasarım |
| R3 | Tek olay: kıyasın ≥ 2 epizodunda strateji düşüşü ≤ 0,9 × kıyasınki | 2 epizot | tasarım |
| B | Blok bootstrap (eşleşik, durağan, ortalama blok ≈ 1 ay, 1.000): düşüş azaltımı %5 persentili > 0 **ve** P(MAR_S > MAR_K) ≥ 0,80 | 0,80 | tasarım |

İkincil ve raporlanan ölçüler (kapı değil, kayıtta zorunlu): toplam getiri, CAGR, yıllık oynaklık,
Sharpe, **standart** Sortino, en uzun düşüş süresi, devir, toplam maliyet. Eski `Metrikler.sortino`
standart dışıdır (K-125/B-1) ve RYPP'de kullanılmaz.

"Düşüş %50 azaldı" tek başına PASS değildir. Sabit %50 maruziyet taşıyan strateji P1'i geçer ama
P3'te kalır (testle sabit: `test_yalniz_maruziyet_dusurmek_fail_plasebo_ayirt_eder`).

## 3. Plasebo (rastgele zamanlama) kontrolü

Stratejinin **kendi** ağırlık takvimi (T × N) zamanda dairesel kaydırılır. k, [0,05·T, 0,95·T]
aralığından düzgün çekilir ve bütün enstrümanlara aynı k uygulanır. Korunanlar:

- işlem sayısı (sarma noktası ±2),
- tutma süreleri,
- ortalama maruziyet ve risk bütçesi,
- maliyet yapısı,
- evren ve dönem.

Bozulan tek şey fiyatla hizalanma. Gerçek takvim ve plasebo **aynı doğrusal modelle**
değerlendirilir (elma-elma). P1/P2 ise motorun gerçek özkaynağından ölçülür.

**Neden bu kadar merkezi (K-125/B-3):** kripto evreninin OOS penceresine 18 çekiliş baktı ve
penceredeki 2025-26 düşüşü biliniyor. Bu yüzden "düşüşte nakde geç" tasarımı o pencerede kendiliğinden
iyi görünür. Plasebo aynı maruziyet bütçesini rastgele zamanda harcadığı için bu hindsight avantajını
nötralize eder: yalnız **zamanlama** ödüllendirilir.

## 4. Çoklu test

- Küresel defter (K-039) aynen: her RYPP hipotezi önce kaydedilir ve sayılır.
- RYPP ailesi içinde Bonferroni: plasebo persentili 1 − 0,05/k; k, defterdeki RYPP çekilişlerinin
  **birikimli** sayısıdır (azalmaz).
- Parametre ızgarası ve seçim yöntemi (plato/tepe) hipotez kimliğinin parçasıdır. "En iyi geçmiş
  sonucu seçtik" promotion kanıtı değildir: seçim IS'te yapılır, RYPP yalnız donmuş aday üzerinde
  OOS'ta koşar.

## 5. Araştırma → Dondurma → Doğrulama → Promotion

1. **Araştırma (IS):** aileler, filtreler, evrenler, parametreler serbestçe denenir. OOS'a bakılmaz.
2. **Dondurma:** parametreler, evren tanımı (PIT kural kimliği), timeframe, giriş/çıkış, risk
   kuralları ve kıyas hipotez kaydına yazılır (K-051 program + K-039 defter). Kayıttan önce commit
   (K-121).
3. **Doğrulama (OOS, bir kez):** donmuş aday RYPP'den geçer. FAIL ya da INCONCLUSIVE'de aynı OOS'a
   bakarak "biraz daha tuning" yapılmaz. Yeni bir araştırma döngüsü açılır ve yeni hipotez sayılır.
4. **Promotion:** PASS gerekli ama yeterli değil. Ardından K-122 zinciri gelir: paper/shadow
   gösterimi ve sistem hazır.

**K-127 notu (metin değiştirilmedi):** Yukarıdaki "en az FAIL olmamalı" cümlesi K-127/1 ile açık karara bağlandı:
bağımsız doğrulama ancak veri yeterliliği ve bütün nokta koşulları ölçülüp geçtiyse "yapıldı ve FAIL değil" sayılır;
tolere edilen tek belirsizlik bootstrap. Bağımsız veri kayıtlı ve `promotion_uygun` bir set olmalı
(`config/bagimsiz_veri.json`); French 202607 seti PIT değil (revizyon) ve bugün uygun değil. §4'teki k,
değerlendirme anındaki defter önekinden sayılıp kanıta donar; promotion yeniden sayar (K-127/2).

**Zincire bağlantı (K-126):** `sq promotion degerlendir --protokol rypp --rypp … --bagimsiz …`.
RYPP yalnız `out_of_sample` aşamasının ölçütünü değiştirir; temiz ağaç, veri kalitesi, K-039 sayımı,
risk incelemesi, paper ve elle onay alfa yoluyla ortaktır. Bağımsız doğrulama yoksa sonuç
INCONCLUSIVE'dir (FAIL değil: aday yanlışlanmadı, kanıt eksik); bağımsız veride yeterlilik ve bütün
nokta koşulları ölçülüp geçmiş olmalı, tolere edilen tek belirsizlik bootstrap'tır.

**Ek doğrulama (kirlenme nedeniyle zorunlu):** kripto OOS'u (B-3) tek başına yeterli sayılmaz.
Aynı donmuş kural, bu projede OOS'una hiç bakılmamış bağımsız bir veride de raporlanır: ABD
piyasası/sektörleri, French verisi, **2004-05 sonrası** (K-124'te yalnız öncesi ölçüldü). Bu veri
promotion kararına INCONCLUSIVE/FAIL girdisi olarak girer: PASS için bağımsız veride en az FAIL
olmamalı.

## 6. Üç sonuç

- **PASS:** veri yeterli, bütün nokta koşulları ve bootstrap geçti.
- **FAIL:** veri yeterli ve en az bir nokta koşulu kaldı.
- **INCONCLUSIVE:** kanıt karar vermeye yetmiyor. Sebepler: OOS < 2 yıl, kıyasta < 2 epizot
  (kripto ≥ %20, hisse ≥ %10), plasebo < 100, stres koşusu yok ya da nokta koşulları geçtiği hâlde
  bootstrap güven aralığı yetersiz. **Eşik gevşetilmez**; daha fazla veri beklenir.

## 7. Evren ve yanlılıklar

- **Evren önceden ve PIT:** kural (ör. "o ay hacimde ilk N") yazılır; sonradan başarılı coin seçilmez.
  "BTC geçti → kripto geçti" çıkarımı yapılmaz; evren sonucu raporlanır, sembol kırılımı ikincildir.
- **Delist ve listeleme:** PIT tablo `27b7a16ed0ed` (K-052/K-056), veri kesilen pozisyon 48 barda
  sıfıra yazılır (`SIFIRA_YAZ_BAR`, testli).
- **Look-ahead:** her gösterge ve strateji otomatik testte (`test_look_ahead_genel.py`, K-118).
- **Maliyet:** ölçülmüş kripto modeli (taraf başı 10 + 5,3 bps) ve S1'de iki katı.

## 8. Jev'in yeri (yetki sınırlı, K-049/K-074)

Deterministik strateji → risk motoru → **Jev güvenlik vetosu** (yalnız engeller: duyuru/delist/
olağan dışı olay metni) → execution. Jev yön tahmini yapmaz ve izin üretemez (K-037). Veto katmanı
K-074 izolasyonunu değiştirdiği için ayrı bir K ister ve C/D fazında ele alınır.

## 9. Sınırlar

RYPP canlı uygulanabilirliği, kapasiteyi ve vergiyi ölçmez. İstatistiksel anlamlılık ekonomik
faydayla aynı şey değildir: PASS "önceden tanımlı koşullar sağlandı" demektir, gelecekte düşüşü
azaltacağının garantisi değildir.
