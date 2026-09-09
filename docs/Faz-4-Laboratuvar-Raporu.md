---
proje: ScryneQuant
created: 2026-09-09
type: faz-raporu
faz: 4
status: kapandi
---
# Faz 4 — Strateji Laboratuvarı Raporu

**Ölçüm tarihi:** 2026-09-09 · **Veri:** BTC/USDT 1h, 45.576 bar (5,2 yıl),
`sha256 = e3adb02c2a6a1639…` · **Maliyet:** `fee_taker_bps = 10,0`,
`slippage_bps = 5,2996` (K-021 kalibrasyonu) · **Sermaye:** 10.000 USDT ·
**Hedef maruziyet:** tüm stratejilerde sabit %20

> Bu fazın amacı kâr bulmak değildi. Roadmap'in kendi notu: *"Bu fazın çıktısı büyük
> ihtimalle 'hiçbiri maliyetlerden sonra anlamlı değil' olacaktır. Bu bir başarısızlık
> değil, sistemin çalıştığının kanıtıdır."* Ölçüm bu beklentiyi doğruladı.

---

## 1. Tek cümlelik sonuç

**Beş strateji ailesinin hiçbiri, maliyetlerden sonra al-tut kıyasını geçemedi; altısının
da in-sample başarısı out-of-sample'da tamamen kayboldu; K-019 kapılarından geçen strateji
yok.**

---

## 2. Kurulan laboratuvar

| Bileşen | Modül | Ne yapıyor |
| --- | --- | --- |
| Bölme | `research/bolme.py` | Kronolojik IS/OOS ve walk-forward pencereleri; ısınma geriye taşır, ileriye asla |
| Tarama | `research/tarama.py` | Izgara taraması, seçim ölçütü, asgari işlem şartı, plato/duyarlılık ölçümü |
| Walk-forward | `research/walkforward.py` | Katman katman optimize-test, sermaye taşımalı bileşik OOS, parametre kararlılığı |
| Monte Carlo | `research/analiz.py` | İşlem sırası karıştırma, düşüş dağılımı |
| Stres | `research/analiz.py` | Maliyet varsayımlarını 2×/3× bozma (§15.1) |
| Karşılaştırma | `research/karsilastirma.py` | Beş aile + kıyas, aynı veri/maliyet/sermaye |
| Kapılar | `research/kapilar.py` | K-019 eşikleri, geçer/kalır |
| Deney kaydı | `research/deney.py`, `tekrar.py` | Kaydından yeniden üretim (K-009) |

**Strateji ailesi (5) + kıyas (1):** kesişim (`sma_kesisim`, `ema_kesisim`), ortalamaya
dönüş (`rsi_donus`), kırılım (`donchian`), momentum (`momentum`), çok faktörlü
(`cok_faktor`); kıyas `al_tut`.

**Izgaralar bilerek küçük** (12-36 nokta): 1.000 kombinasyon denemek, gürültünün en şanslı
örneğini "en iyi parametre" diye sunmanın en kestirme yolu (§16.2).

---

## 3. In-sample / out-of-sample (%70 / %30 kronolojik bölme)

IS 31.702 bar, OOS 13.672 bar. Parametre **yalnızca IS'te** seçildi, OOS'ta hiç
optimizasyon yapılmadı.

| Strateji | Aile | Plato | IS Sharpe | OOS Sharpe | OOS/IS | OOS getiri | OOS maxDD | İşlem |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sma_kesisim | kesişim | 0,27 | **+0,62** | **−1,03** | −1,67 | −9,2 % | 12,4 % | 70 |
| ema_kesisim | kesişim | 0,27 | **+0,65** | **−0,46** | −0,70 | −4,1 % | 9,5 % | 44 |
| rsi_donus | ortalama dönüş | 0,09 | **+0,45** | **−0,85** | −1,89 | −10,0 % | 12,6 % | 112 |
| donchian | kırılım | 0,08 | **+0,75** | **−0,35** | −0,46 | −2,8 % | 6,6 % | 56 |
| momentum | momentum | 0,19 | **+0,91** | **−0,08** | −0,09 | −1,2 % | 12,2 % | 22 |
| cok_faktor | çok faktör | 0,14 | **+0,23** | **−0,95** | −4,15 | −8,3 % | 11,9 % | 91 |
| *al_tut* | *kıyas* | 1,00 | *+0,70* | *−0,27* | *−0,39* | *−3,7 %* | *13,2 %* | *0* |

**Okunuşu:** altı stratejinin **altısında da** IS Sharpe pozitif, OOS Sharpe negatif.
OOS/IS oranı hepsinde negatif. Bu, ders kitabı overfitting tablosudur: in-sample başarı
gürültünün ezberlenmesiydi.

**Plato oranı düşük (0,08-0,27):** en iyi parametrenin komşuları belirgin biçimde daha
kötü, yani seçilen nokta bir plato değil dar bir tepe — gürültü tepesi olduğunun ikinci
işareti.

**Kıyas da negatif (−%3,7):** OOS penceresinde BTC'nin kendisi düştü. Yani "stratejiler
kaybetti" cümlesi tek başına yeterli değil; asıl soru kıyasa göre nerede durdukları. Altı
stratejiden yalnızca ikisi (momentum −%1,2, donchian −%2,8) kıyastan daha az kaybetti,
dördü daha çok.

---

## 4. Walk-forward (16 katman, 1 yıl eğitim / 3 ay test, kaydırmalı)

Her katmanda ızgara yeniden tarandı, seçilen parametre **sonraki** dönemde kullanıldı.
Sermaye katmanlar arasında taşındı.

| Strateji | Bileşik OOS Sharpe | Bileşik getiri | maxDD | İşlem | Pozitif katman | Kararsızlık |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **al_tut (kıyas)** | **+0,86** | **+39,0 %** | 13,1 % | 0 | 8/16 | 0,00 |
| donchian | +0,61 | +14,4 % | 10,5 % | 155 | 10/16 | 0,19 |
| sma_kesisim | +0,53 | +14,7 % | 12,8 % | 197 | 8/16 | 0,25 |
| rsi_donus | +0,27 | +7,1 % | 10,2 % | 181 | 7/16 | 0,21 |
| momentum | +0,18 | +3,7 % | 17,3 % | 148 | 9/16 | 0,21 |
| ema_kesisim | −0,03 | −1,7 % | 14,0 % | 171 | 9/16 | 0,25 |
| cok_faktor | −0,12 | −4,1 % | 14,6 % | 287 | 8/16 | 0,15 |

**Bu tablonun en önemli satırı ilki.** Walk-forward'da bazı stratejiler pozitife dönüyor
(donchian +%14,4, sma_kesisim +%14,7) ve tek başına bakıldığında umut verici görünüyor.
Ama **hiçbir şey yapmayan kıyas +%39,0 getirdi ve Sharpe'ı hepsinden yüksek.** Aktif
yönetim bu veride sermayeyi piyasada tutmaktan daha iyisini yapmadı; yaptığı tek şey
155-287 işlemin maliyetini ödemek oldu.

**Kıyas neden IS/OOS'ta negatif ama walk-forward'da pozitif:** ikisi farklı pencereleri
ölçüyor. IS/OOS'un OOS'u serinin son %30'u (düşen dönem); walk-forward ısınmadan sonraki
neredeyse tüm seriyi kapsıyor. Bu bir çelişki değil, "sonuç pencereye bağlı"nın somut
örneği — ve tam olarak bu yüzden tek bir bölmeye bakıp karar verilmiyor.

**Pozitif katman oranı 7-10/16 (≈ %50):** bileşik getiri yazı-turadan ayırt edilemiyor.

**Parametre kararsızlığı 0,15-0,25:** prosedür 16 katmanda her parametre için 2-4 farklı
değer seçiyor. Yani "canlıda hangi parametreyle çalıştıracağız" sorusunun cevabı yok.
Kıyasın kararsızlığı 0,00 — seçilecek bir şeyi olmadığı için.

---

## 5. Monte Carlo (2.000 deneme, işlem sırası karıştırma)

| Strateji | Gerçekleşen maxDD | Karıştırılmış maxDD p95 | Gerçekleşenden kötü çıkan oran |
| --- | ---: | ---: | ---: |
| sma_kesisim | 77,0 % | 86,0 % | 46,8 % |
| ema_kesisim | — | 84,0 % | 65,7 % |
| rsi_donus | — | 71,0 % | **85,8 %** |
| donchian | — | 76,9 % | **85,2 %** |
| momentum | — | 89,0 % | 46,3 % |
| cok_faktor | — | 97,5 % | 7,3 % |

**Okunuşu:** `rsi_donus` ve `donchian` için gerçekleşen düşüş, olası sıralamaların
yalnızca %15'inden daha derindi — yani **geçmişteki düşüş şanslı bir sıralamaydı**.
"Geçmişte %10 düştü" cümlesi "en fazla %10 düşer" demek değil; aynı işlemler başka sırada
gelseydi vakaların %85'inde daha derin düşülürdü.

Ters yönde `cok_faktor`: gerçekleşen düşüş olası sıralamaların %93'ünden daha kötü — bu
sefer geçmiş şanssızdı.

**Bu testin sınırı kayıtlı:** işlemlerin bağımsız olduğunu varsayar. Trend takip eden bir
stratejide ardışık kazançlar ilişkilidir; karıştırmak o ilişkiyi siler. Yani kötü haber
verdiğinde inanılır, iyi haber verdiğinde tek başına yeterli değildir.

---

## 6. Stres testi (§15.1)

Maliyet varsayımları bozuldu: slippage 2×/3×, komisyon 2×, ikisi birden 2×.

| Strateji | Bozulma (yüzde puan) |
| --- | ---: |
| rsi_donus | 8,8 |
| donchian | 15,3 |
| momentum | 16,8 |
| ema_kesisim | 21,3 |
| sma_kesisim | 24,5 |
| cok_faktor | 25,5 |
| *al_tut* | *0,0* |

Kıyasın bozulması sıfır: tek işlem yapıyor, maliyet varsayımı onu ilgilendirmiyor. Aktif
stratejilerin 8,8-25,5 puanlık bozulması, sonuçlarının K-021 kalibrasyonunun **doğruluğuna
bahis** olduğunu gösteriyor. Kalibrasyon p75 persentiliyle yapılmıştı; p95'te slippage
2,4 kat, p99'da 4,4 kat yüksek.

---

## 7. K-019 — promotion kapıları ve sonuç

Kapılar `research/kapilar.py`'de, gerekçeleriyle birlikte. `sq lab kapilar` bunu koşturur.

| Kapı | Eşik | Neden bu sayı |
| --- | --- | --- |
| `oos_sharpe` | ≥ 0,50 | Kıyasın IS Sharpe'ı 0,70 ölçüldü; kıyasın çok altında kalan bir strateji sermayeyi sistemde tutmak için gerekçe üretemez |
| `oos_is_orani` | ≥ 0,50 | IS başarısının en az yarısı korunmuş olmalı; Faz 4'te altı stratejide de bu oran **negatif** |
| `wf_katman_basari` | ≥ 0,60 | 16 katmanın en az 10'unda pozitif; ölçülen 7-10 (yazı-tura) |
| `parametre_kararliligi` | ≤ 0,35 | Ölçülen 0,15-0,25; 0,35 üstü "her dönem başka bir şey seçiliyor" demek |
| `asgari_islem` | ≥ 30 | 30 işlemde win rate standart hatası ~%9; daha azıyla iddia kurulamaz |
| `max_drawdown` | ≤ 0,25 | Kıyas %25,7 düştü; varlığın kendisinden derin düşen aktif yönetim değer katmıyor |
| `stres_dayanikliligi` | ≤ 0,15 | Maliyet iki katına çıkınca çöken strateji, kalibrasyona bahis oynamaktır |

**Sonuç: 7 stratejinin 7'si de kaldı.**

```
strateji      oos_shp oos/is  wf_kat  param  islem  maxDD  stres    SONUÇ
sma_kesisim      ✗      ✗       ✗       ✓      ✓      ✓      ✗      kaldı
ema_kesisim      ✗      ✗       ✗       ✓      ✓      ✓      ✗      kaldı
rsi_donus        ✗      ✗       ✗       ✓      ✓      ✓      ✓      kaldı
donchian         ✗      ✗       ✓       ✓      ✓      ✓      ✗      kaldı
momentum         ✗      ✗       ✗       ✓      ✗      ✓      ✗      kaldı
cok_faktor       ✗      ✗       ✗       ✓      ✓      ✓      ✗      kaldı
al_tut (kıyas)   ✗      ✗       ✗       ✓      ✗      ✓      ✓      kaldı
```

**Eşikler bugünkü sonuca göre ayarlanmadı.** Ayarlansaydı kapı kaldırılmış olurdu — K-010'un
tam olarak uyardığı şey. `tests/unit/test_kapilar.py::test_faz4_olcumlerinden_hicbiri_gecmiyor`
bu gevşemeyi yakalar: birisi eşikleri indirirse test kırmızıya döner ve karar günlüğüne
gerekçe yazmaya zorlar.

---

## 8. Yeniden üretilebilirlik (bitti kriteri)

Beş deney tipi de (`tarama`, `walk_forward`, `monte_carlo`, `stres`, `karsilastirma`,
`degerlendirme`) kaydından yeniden üretilip çıktı hash'i doğrulandı:

```
sq lab dogrula runs/deneyler/tarama/4353f031df00-58bceaed0fe1.json
  → yeniden üretildi: aynı (58bceaed0fe1d6a7)
sq lab dogrula runs/deneyler/monte_carlo/53c71be5cc56-9314ed8ee8fd.json
  → yeniden üretildi: aynı (9314ed8ee8fdf05d)
sq lab dogrula runs/deneyler/stres/e8270eb6d6e4-249d47f444dd.json
  → yeniden üretildi: aynı (249d47f444dd0dfa)
sq lab dogrula runs/deneyler/karsilastirma/96889713358a-5e62e0b9b6cf.json
  → yeniden üretildi: aynı (5e62e0b9b6cf3f69)
```

Tekrar mekanizmasının kritik kuralı: **kayıt tek doğruluk kaynağıdır.** Tekrar,
`config/maliyet.json`ın bugünkü hâline bakmaz, bugünkü ızgarayı kullanmaz, varsayılana
düşmez. Bunların herhangi biri yapılsaydı "aynı çıktı" iddiası kendi kendini doğrulayan bir
totoloji olurdu. Ayrıca veri SHA-256'sı eşleşmezse tekrar **reddedilir**.

---

## 9. Beklenmeyen bulgular

1. **Kıyas ölçütünün tek sinyali ısınma penceresinde yutuldu.** `al_tut`un ilk hâli bir
   `_girildi` bayrağı tutuyordu; walk-forward katmanında bayrak ısınma barında kalkıyor, o
   barda üretilen sinyal ölçüm penceresine girmediği için atılıyor, ve strateji bir daha
   hiç sinyal üretmiyordu. Kıyas çizgisi tabloda **%0,0 getiri** olarak göründü —
   çökmeden, uyarı vermeden.

   **Genel ders (K-031):** kendi durumunu tutan bir strateji, sinyalinin *kabul edildiğini*
   varsayamaz. Faz 5'te risk motoru sinyalleri reddedecek ve aynı hata sınıfı geri gelecek.
   Durum `ctx.pozisyon`dan okunur.

2. **Sentetik test verisi momentum eşikleri için fazla sakin.** `conftest.bar_uret` bar
   başına ~%0,08 oynaklık üretiyor; gerçek BTC/USDT 1h bunun ~10 katı. `momentum`
   varsayılan %2 eşiğiyle sentetik seride **tek sinyal üretmedi** ve "strateji bozuk" gibi
   göründü. Laboratuvar testleri için ayrı, gerçekçi oynaklıkta bir üreteç eklendi.

3. **Kıyas asgari işlem şartına takıldı.** Al-tut bir kez alıp tutar, yani kapanmış tur
   sayısı sıfırdır. Tarama şartı (≥20 işlem) ona uygulanınca karşılaştırmanın referans
   çizgisi tablodan silindi. Şart parametre seçimi içindir; kıyasta seçilecek bir şey yok.

4. **Walk-forward, tek bölmenin tersini söyledi.** IS/OOS'ta altı stratejinin altısı da
   negatifken, walk-forward'da dördü pozitife döndü. Aynı veri, farklı pencere. Bu, tek bir
   OOS testine güvenmemek için somut gerekçe — ve kıyas eklenmemiş olsaydı bu tablo
   "donchian çalışıyor" diye okunabilirdi.

---

## 10. Faz 5'e devreden

- **Kapıların zorlanması.** Bu faz eşikleri belirledi ve `degerlendir()` fonksiyonunu
  yazdı; sinyalin execution'a ulaşmasını engelleyen mekanizma Faz 5'in risk motorunda.
- **K-031'in ikinci yarısı.** Risk motoru sinyalleri reddedecek; strateji katmanının
  "sinyalim kabul edildi" varsayımı yapmadığı testle korunmalı.
- **`confidence` alanı.** Yalnızca `cok_faktor` anlamlı dolduruyor (oy oranı); risk
  motorunun pozisyon büyüklüğünde bu alanı kullanması Faz 5 kararı.
- **Açık soru:** bu veri setinde (tek sembol, 1h, 5,2 yıl) hiçbir aile çalışmadı. Faz 5-8
  bunun *yanlış strateji* mi yoksa *yanlış soru* mu olduğunu değiştirmiyor — sistemin işi
  cevabı ölçmekti ve ölçtü. Sermaye artırma veya live'a geçme kararı bu tabloya bakılarak
  verilmez.
