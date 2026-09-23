---
proje: ScryneQuant
faz: 5
created: 2026-09-11
type: faz-raporu
status: kapandi
---
# Faz 5 — Risk Motoru + Promotion: Ölçüm Raporu

**Veri:** BTC/USDT 1h · 45.576 bar · 5,2 yıl (2021-06-28 → 2026-09-09) ·
SHA-256 `e3adb02c2a6a…`
**Maliyet modeli:** `fee_taker_bps = 10,0` · `slippage_bps = 5,2996` (K-021, kalibre)
**Risk limitleri:** kimlik `c3608583bd9f…` (K-033)
**Test:** 756 geçti, 1 atlandı (ağ testi) · ruff temiz

Bu raporun sayıları ölçüldü. Tahmin edilen hiçbir değer yok; ölçülemeyen şeyler
"ölçülemedi" diye yazıldı.

---

## 1. Bitti kriteri

| Kriter | Sonuç |
| --- | --- |
| Risk motoru atlanamıyor (testle kanıtlı) | ✅ üç katman: tip + mühür + import kesme noktası (`test_risk_bypass.py`, 22 test) |
| Her limit için ihlal senaryosu testi var ve doğru davranıyor | ✅ sekiz limit, her biri için ihlal **ve** ihlal-olmayan vaka (`test_risk_limitleri.py`, 57 test) |
| Kill switch'te K-008'in beş davranışı gerçekleşiyor | ✅ her davranış kendi test sınıfında (`test_kill_switch.py`, 26 test) |
| Promotion kapıları uygulanıyor; `dirty` / `data_quality_warning` geçemiyor | ✅ zincir zorlanıyor (`test_promotion.py`, 33 test) + CLI'da uçtan uca doğrulandı |

**Üretilen paketler:** `risk/` (`limitler`, `muhur`, `niyet`, `durum`, `motor`, `audit`,
`promotion`, `kalibrasyon`), `execution/kapi.py`, `migrations/001_faz5.sql`,
CLI: `sq risk {kalibre,limitler,durum,audit,serbest}`,
`sq promotion {durum,degerlendir,onayla}`, `sq backtest --risk`.

**Verilen kararlar:** K-032 (risk onayının üç katmanı), K-033 (limitlerin kaynağı ve
gözden geçirme koşulu).

---

## 2. Limitlerin kalibrasyonu

Üç limit ölçüldü, beşi iştah tercihi olarak işaretlendi (K-033). İştah olanların her biri
bir gözden geçirme koşulu taşıyor; `config/risk.json` onsuz doğrulanmıyor.

### 2.1 Volatilite eşiği — ATR(14)/fiyat dağılımı (45.562 bar)

| p50 | p75 | p90 | p95 | **p99** | p99,5 | p99,9 | max |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| %0,684 | %0,911 | %1,190 | %1,398 | **%2,047** | %2,417 | %3,138 | %3,758 |

Eşik **p99 = %2,0466**, yani tipik volatilitenin 3,0 katı. p95 seçilseydi guard her 20
barda bir devreye girer ve stratejinin kendi kararının yerine geçerdi; p99,9 yılda birkaç
bar demek, yani neredeyse hiç.

### 2.2 Aleyhte hareket çarpanı — "2×ATR" varsayımı çürütüldü

Bir girişin `N` bar içinde gördüğü en kötü aşağı hareket, ATR katı olarak:

| Ufuk | p50 | p75 | **p90** | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 bar | 1,03 | 1,92 | 3,19 | 4,29 | 7,16 | 23,5 |
| 12 bar | 1,45 | 2,71 | 4,49 | 5,96 | 10,13 | 34,2 |
| **24 bar** | **2,07** | 3,97 | **6,39** | 8,65 | 14,65 | 37,9 |
| 48 bar | 3,00 | 5,62 | 9,41 | 12,58 | 22,67 | 62,4 |

**Bulgu:** yaygın "2×ATR stop" kuralı 24 barlık ufukta **medyanı** karşılıyor. 2,0 seçmek
vakaların yarısında gerçek riskin altında kalmak olurdu — K-007'nin açıkça yasakladığı
yöne yuvarlamak. Seçilen değer p90 = **6,3934**.

**Ufuk neden 24 bar:** v1'de borsada duran bir stop emri yok (Faz 7), yani pozisyon strateji
`FLAT` diyene kadar açık kalır. Risk ufku bir stop mesafesi değil **tutma süresi**. Faz 4'ün
altı stratejisinin 2.834 kapanmış işleminde medyan tutma süresi **27 saat** ölçüldü:

| Strateji | medyan | ortalama | p75 | p90 |
| --- | ---: | ---: | ---: | ---: |
| sma_kesisim | 35,0 h | 43,2 h | 54,5 h | 87,0 h |
| ema_kesisim | 34,0 h | 54,0 h | 73,0 h | 133,8 h |
| rsi_donus | 116,5 h | 135,0 h | 181,5 h | 253,5 h |
| donchian | 35,5 h | 49,7 h | 63,0 h | 105,0 h |
| momentum | 44,0 h | 64,5 h | 79,2 h | 144,0 h |
| cok_faktor | 8,0 h | 16,1 h | 26,0 h | 40,0 h |
| **TÜMÜ** | **27,0 h** | 43,9 h | 53,0 h | 105,0 h |

### 2.3 Günlük zarar limiti — tetikleme sıklığıyla seçildi

Günlük getiri dağılımı (1.899 gün):

| p0,1 | p0,5 | p1 | p2,5 | p5 | p10 | min |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| −%14,03 | −%9,31 | −%7,34 | −%5,58 | −%4,04 | −%2,89 | −%15,38 |

%30 maruziyet tavanında aday limitlerin tetikleme sıklığı:

| Limit | Tetiklenen gün | Oran |
| ---: | ---: | ---: |
| %1,5 | 64 / 1.899 | %3,37 |
| **%2,0** | **24 / 1.899** | **%1,26** |
| %2,5 | 14 / 1.899 | %0,74 |
| %3,0 | 7 / 1.899 | %0,37 |

**%2,0 seçildi.** %1,5 normal bir kötü günde devreye girip stratejinin yerine karar verir;
%3,0 neredeyse hiç çalışmaz — varmış gibi görünüp yokmuş gibi davranır.

### 2.4 Ardışık kayıp limiti — Faz 4'ün 564 kayıp serisi

| Eşik | Seri sayısı | Oran |
| ---: | ---: | ---: |
| ≥3 | 277 | %49,1 |
| ≥5 | 144 | %25,5 |
| ≥8 | 57 | %10,1 |
| **≥10** | **33** | **%5,9** |

p95 = 10. Yani 10 "olağan kötü gidiş" değil **olağandışı** tarafta; daha düşük bir limit
stratejinin normal davranışını cooldown'a sokardı (üç ardışık kayıp serilerin yarısında
görülüyor).

### 2.5 İki limitin birlikte davranışı

`islem_basina_risk` tavanı = `islem_basina_risk / (ters_hareket_atr_carpani × ATR/fiyat)`.
Ölçülen çarpanla (6,3934):

| Volatilite | ATR/fiyat | Varsayılan aleyhte hareket | Maruziyet tavanı |
| --- | ---: | ---: | ---: |
| medyan (p50) | %0,684 | %4,37 | **%11,4** |
| p75 | %0,911 | %5,82 | %8,6 |
| p95 | %1,398 | %8,94 | %5,6 |
| p99 (guard sınırı) | %2,047 | %13,08 | %3,8 |

**Bulgu:** pratikte bağlayıcı limit `azami_maruziyet` (%30) değil, `islem_basina_risk`
(%0,5). Tipik volatilitede tavan %11,4 — yani %0,5 risk bütçesi, bu kadar oynak bir
varlıkta %30'luk tavanı hiç göstermiyor. Bu iki sayının birlikte düşünülmemiş sonucu mu,
bilinçli bir tercih mi: **cevap Scryne'ın.** `config/risk.json` bu soruyu
`islem_basina_risk`in gözden geçirme koşuluna yazdı.

---

## 3. Risk motorunun gerçek veride etkisi

Aynı veri, aynı maliyet, aynı stratejiler; tek fark risk motoru. Sol blok risksiz (Faz
3-4'ün tabanı), sağ blok riskli.

| Strateji | Getiri | **R-Getiri** | maxDD | **R-maxDD** | Sharpe | **R-Sharpe** | Maliyet | **R-Maliyet** | R-ort.maruziyet |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| al_tut (kıyas) | +%25,9 | +%7,1 | %25,7 | **%9,4** | 0,38 | 0,31 | 3 | 1 | %8,6 |
| sma_kesisim | −%13,3 | −%4,3 | %22,1 | **%11,9** | −0,34 | −0,18 | 3.104 | 2.065 | %6,5 |
| ema_kesisim | −%8,3 | **+%8,1** | %20,4 | **%7,7** | −0,19 | **+0,37** | 2.501 | 1.689 | %6,5 |
| rsi_donus | −%12,3 | −%10,5 | %18,5 | **%13,4** | −0,28 | −0,62 | 969 | 659 | %4,9 |
| donchian | −%9,2 | −%6,8 | %15,0 | **%9,6** | −0,30 | −0,46 | 1.750 | 1.200 | %3,7 |
| momentum | −%17,6 | −%10,2 | %24,8 | **%13,1** | −0,49 | −0,56 | 2.055 | 1.436 | %5,8 |
| cok_faktor | −%46,0 | −%19,1 | %49,4 | **%20,1** | −1,85 | −1,78 | 4.679 | 1.912 | %1,8 |

*(Getiri ve maliyet sayıları 10.000 USDT başlangıç sermayesi üzerinden; maliyet = komisyon
+ slippage, USDT.)*

**Raporun en önemli satırı kıyas satırı.** Risk motoru **yedi vakanın yedisinde de** düşüşü
azalttı (en çok `cok_faktor`da: %49,4 → %20,1). Ama aynı motor kıyasın getirisini
+%25,9'dan +%7,1'e indirdi. Yani:

> **Risk motoru bir alfa kaynağı değil, bir varyans azaltıcıdır.** Kaybedeni daha az
> kaybettirir, kazananı daha az kazandırır. Altı stratejinin zararının küçülmesi bir
> başarı kanıtı değil — maruziyetin küçülmesinin aritmetik sonucu.

`ema_kesisim`in pozitife dönmesi (−%8,3 → +%8,1, Sharpe −0,19 → +0,37) bu yüzden dikkatle
okunmalı: ortalama %6,5 maruziyetle elde edilmiş bir sayı ve kıyas %8,6 maruziyetle +%7,1
getirdi. Fark, ölçeklemenin gürültüsünün içinde. **Karar mercii K-019'un yedi kapısı,
bu tablo değil.**

### 3.1 Risk kararlarının dökümü

| Strateji | Değerlendirilen | Onay | Red | SAFE_MODE |
| --- | ---: | ---: | --- | --- |
| al_tut | 15 | 1 | volatilite_olculemedi: 14 | — |
| sma_kesisim | 1.087 | 1.082 | cooldown 1, volatilite 4 | — |
| ema_kesisim | 867 | 859 | cooldown 5, volatilite 3 | — |
| rsi_donus | 3.310 | 3.289 | volatilite 21 | — |
| donchian | 2.872 | 2.871 | volatilite 1 | — |
| momentum | 15.576 | 15.472 | cooldown 4, volatilite 100 | — |
| cok_faktor | 31.014 | 27.522 | **safe_mode 3.417**, drawdown 1, cooldown 62, volatilite 12 | **açık** |

**Kill switch gerçek veride bir kez tetiklendi:** `cok_faktor` drawdown limitini (%20) aştı,
SAFE_MODE açıldı ve sonrasındaki 3.417 giriş sinyali reddedildi. Çıkış sinyalleri geçmeye
devam etti (K-008/3). Bu, kill switch'in sentetik bir testte değil **gerçek bir seride**
çalıştığının kanıtı.

---

## 4. Beklenmeyen bulgular

Dördü de testlerin veya ölçümün kendisi sayesinde çıktı; hiçbiri tasarımda öngörülmüş
değildi.

### 4.1 "Execution stratejiyi hiç görmüyor" iddiası yanlıştı — test çürüttü

İlk bypass testi şunu ölçüyordu: `execution/` ve `oms/` paketlerinin import grafiğinde
`strategy.sinyal` **yok**. Test ilk koşuda kırıldı ve haklıydı:

```
scryne_quant.execution.kapi -> scryne_quant.risk.niyet -> scryne_quant.strategy.sinyal
```

`OnayliNiyet` sinyali **içinde taşıyor** — ve bu doğru bir tasarım: audit'in "strateji ne
istedi, risk ne verdi" karşılaştırması ancak ikisi bir aradayken mümkün. Yani geçişli yol
kaçınılmaz. Doğru iddia "o yol yok" değil, **"o yol `risk.niyet`ten geçiyor"**. Test
yeniden yazıldı: `risk.niyet` grafikten çıkarıldığında strateji katmanı ulaşılamaz hâle
geliyor mu — yani `risk.niyet` bir **kesme noktası** mı. Ayrıca kesme testinin kendi testi
eklendi (kesilmemiş grafikte yol gerçekten var mı), yoksa `execution/`i silmek de testi
geçirirdi.

### 4.2 Kayan nokta, sınır testlerini sessizce kırıyordu

"Drawdown tam %20 bir ihlal değil" testi kırıldı: `1 − 8000/10000` = `0,19999999999999996`
ve bu limiti aşmış görünüyor. Karşılaştırmalar çıkarmadan çarpmaya çevrildi
(`son < zirve × (1 − limit)`), böylece tam sayılarla tam sonuç çıkıyor. Aynı düzeltme
günlük zarar limitine de uygulandı. Sınır davranışının bir **tercih** olduğu ve yazılı olmak
zorunda olduğu buradan öğrenildi: bu motorda sınır **dahil** geçer.

### 4.3 `SIFIR_BOYUT` red sebebi ölü koddu

Testler gösterdi ki boyutlandırma tavanı hiçbir zaman tam sıfıra inmiyor (iki çarpan da
pozitif), dolayısıyla `RedSebebi.SIFIR_BOYUT` hiç üretilemez. Bir risk motorunda ölü kod
işe yaramaz değil **tehlikeli**: sayımın kapsadığı sanılan bir durum kapsanmıyor demektir.
`ASGARI_MARUZIYET = 1e-9` eşiği eklendi ve sebep erişilebilir hâle geldi. Borsanın gerçek
minimum emir büyüklüğü bu değil — o Faz 7'nin işi ve sembol başına farklı.

### 4.4 Limitler tavan değil tetikleyici — ve bu iki yerde görünüyor

İki ölçüm aynı dersi verdi:

1. **`azami_maruziyet` %30 iken gerçekleşen maruziyet %30,14 çıktı.** Fill `t+1` açılışında
   o anki özkaynağın %30'u olarak hesaplanıyor; bar kapanışına kadar fiyat yükselirse payı
   %30'un üstüne çıkar. Sürekli yeniden dengeleme yok — her barda hedefe dönmek bir
   *rebalance bandı* kararı ve Faz 5'in kapsamında değil. Test sayıyı değil **mertebeyi**
   sınırlıyor: sapma %10'u aşarsa kırılıyor, çünkü o gün tavan pratikte başka bir sayı demek.
2. **`drawdown_limiti` %20 iken `cok_faktor` %20,1 düştü.** Limit tam tasarlandığı gibi
   çalıştı: aşıldığı anda kill switch'i açtı. Ama zaten olmuş bir düşüşü geri alamaz —
   K-008/2 açık pozisyonları kapatmayı **yasaklıyor**. Yani bir drawdown limiti drawdown'ı
   kapatmaz; yeni risk almayı kapatır.

İkinci bulgu promotion kapısının gerekçesini de düzeltti. Kapı önce "limit devredeyken
aşılmışsa limit çalışmıyor" diyordu — bu çıkarım yanlış. Kapının gerçek gerekçesi: backtest'te
kill switch'e **değen** bir strateji canlıda elle onay bekleyerek duracaktır (K-008/4), ve
böyle bir stratejiyi live adayı saymak zincirin sonunda duran insanı zincirin ortasına
koymak olurdu.

### 4.5 Risk motoru girişi ATR ısınması kadar geciktiriyor

`al_tut` kıyasının 15 değerlendirmesinden 14'ü `volatilite_olculemedi` ile reddedildi:
ATR(14) ilk 14 barda NaN ve **ölçülemeyen guard geçilmiş sayılmıyor**. 45.576 barlık bir
seride 14 bar ihmal edilebilir, ama kural şu: ilk 14 barda işlem yapmak zorunda olan bir
strateji risk motoruyla çalışamaz. NaN'ı sıfır saymak çözüm değil — sıfır ATR guard'ı
geçirir **ve** boyut tavanını sonsuz yapar, yani tek bir eksik ölçüm iki limiti birden
sessizce kaldırır.

---

## 5. Promotion zincirinin bugünkü durumu

Zincir (K-010): `backtest → kalite_kontrol → out_of_sample → risk_incelemesi → paper →
live_adayi → elle_onay → live`

**Hiçbir strateji `out_of_sample` aşamasını geçemiyor** — çünkü K-019'un yedi eşiğini Faz
4'te yedi stratejinin yedisi de geçemedi. Zincir bunu tekrar doğruluyor, gevşetmiyor.

`paper` aşaması **tanım olarak ölçülemez** (Faz 6'nın işi) ve bu yüzden "geçilmemiş"
sayılıyor, "atlanmış" değil. K-019'un cümlesi: *"'Veri yoktu' ile 'kapıdan geçti' aynı şey
değil."*

Uçtan uca doğrulandı: kirli bir working tree'den üretilen sonuç `backtest` aşamasında
durduruldu (`sq promotion degerlendir`), yani Roadmap'in "`dirty` işaretli sonuç kapıdan
geçemiyor" kriteri gerçek bir komutla gösterildi.

---

## 6. PostgreSQL: şema donduruldu, bağlantı Faz 6'da

`migrations/001_faz5.sql` üç tablo taşıyor: `audit`, `risk_durumu`, `promotion` +
`promotion_gecmis`. Hiçbir veritabanına uygulanmadı ve bu bilinçli (K-032, K-011).
`audit` tablosunun kolonları `SqliteDefter` ile **birebir aynı** ve `test_audit.py` ikisinin
ayrışmadığını kontrol ediyor.

İki tasarım kararı SQL tarafında not edildi:

- **Trigger, `RULE` değil.** `DO INSTEAD NOTHING` bir DELETE'i sessizce yutar — işlem
  başarılı görünür, hiçbir şey silinmez, kimse yanlış bir şey yapıldığını öğrenmez. SQLite
  tarafındaki `RAISE(ABORT, ...)` ile aynı davranış isteniyor: işlem **hatayla** düşsün.
- **`risk_durumu` tek satırlık bir tablo ve `safe_mode` orada kalıcı.** Bir çöküşle
  sıfırlanan kill switch, kill switch değildir; aynı gerekçe günlük zarar limiti için de
  geçerli — sıfırlanan bir limit, sürecin her çöküşte kendini affetmesi demek.

---

## 7. Faz 6'ya devredilen

| Konu | Neden Faz 6 |
| --- | --- |
| PostgreSQL bağlantısı | Eşzamanlı yazma ve dayanıklı state ilk kez orada gerekiyor (K-011). Şema hazır. |
| `paper` promotion aşaması | 30 günlük kesintisiz koşu ölçümü Faz 6'nın bitti kriteri |
| K-018/3'ün beşinci eşiği | Paper/backtest drift üst sınırı ölçülebilir hâle gelince K-019'a eklenecek |
| Rebalance bandı kararı | §4.4/1'in ölçtüğü sapma bir limit olarak konuşulacaksa, paper'da gerçek sapma görülmeli |
| `islem_basina_risk` iştahının gözden geçirilmesi | §2.5'in tablosu bu soruyu açtı; cevap Scryne'ın |

---

## 8. Roadmap notunun doğrulanması

Roadmap Faz 5 için bir not yazmamıştı, ama Faz 4'ün notu şunu söylüyordu: *"Faz 5-8 bu
tabloyu değiştirmiyor: sistemin işi cevabı ölçmekti ve ölçtü."*

**Doğrulandı.** Risk motoru altı stratejinin de zararını küçülttü ve düşüşlerini yarıya
indirdi — ama kıyasın getirisini de aynı oranda küçülttü. Hiçbir strateji K-019'un
kapılarını geçmedi. Risk motoru kötü bir stratejiyi iyi yapmıyor; **küçük** yapıyor. Bu,
risk motorundan beklenmesi gereken şeyin tam olarak kendisi.
