---
proje: ScryneQuant
faz: 4-donus-3
type: faz-raporu
tarih: 2026-09-11
status: kapandi
---
# Faz 4'e dönüş 3 — Funding rate: **çürütüldü**

K-042'nin durma kuralı uygulandı: üç hipotez, tek tur, hiçbiri K-019'un yedi kapısını
geçemedi. **Funding fikri kapandı.** Dördüncü aile denenmeyecek.

Hipotezler ön kayıtla yazıldı (defter 36-38), ölçüm ondan sonra yapıldı. Ham kayıt:
`runs/deneyler/degerlendirme/058f6de87165-34065b334590.json`.

## 1. Kapı tablosu — BTC/USDT 1h, IS 31.422 / OOS 13.672 bar, WF 16 katman

| Strateji | OOS Sharpe | OOS/IS | WF katman | İşlem | Kararlılık | Stres | Sonuç |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **funding_egilim** | **+0,288** | **+0,197** | **0,75** ✓ | 24 ✗ | **0,125** ✓ | **0,068** ✓ | kaldı |
| funding_filtre | −0,094 | −0,112 | 0,438 | 56 ✓ | 0,146 ✓ | 0,129 ✓ | kaldı |
| funding_ters | −0,268 | −0,189 | 0,625 ✓ | 60 ✓ | 0,188 ✓ | 0,166 ✗ | kaldı |
| al_tut (kıyas) | −0,271 | −0,369 | 0,500 | 0 ✗ | 0,000 ✓ | 0,001 ✓ | kaldı |
| donchian | −0,348 | −0,439 | 0,438 | 56 ✓ | 0,188 ✓ | 0,154 ✗ | kaldı |
| ema_kesisim | −0,469 | −0,684 | 0,312 | 44 ✓ | 0,219 ✓ | 0,217 ✗ | kaldı |
| momentum | −0,554 | −0,581 | 0,562 | 58 ✓ | 0,208 ✓ | 0,170 ✗ | kaldı |
| rsi_donus | −0,854 | −1,810 | 0,438 | 112 ✓ | 0,208 ✓ | 0,088 ✓ | kaldı |
| cok_faktor | −0,945 | −3,500 | 0,438 | 91 ✓ | 0,167 ✓ | 0,257 ✗ | kaldı |
| sma_kesisim | −1,030 | −1,510 | 0,438 | 70 ✓ | 0,188 ✓ | 0,249 ✗ | kaldı |

Eşikler değişmedi: `oos_sharpe ≥ 0,5` · `oos_is_orani ≥ 0,5` · `wf_katman_basari ≥ 0,6` ·
`parametre_kararliligi ≤ 0,35` · `asgari_islem ≥ 30` · `max_drawdown ≤ 0,25` ·
`stres_dayanikliligi ≤ 0,15`.

## 2. Projenin ilk pozitif OOS Sharpe'ı — ve neden yetmedi

`funding_egilim`, Faz 4'ten bu yana **OOS Sharpe'ı pozitif çıkan ilk strateji**. Faz 4'te
altı stratejinin altısı, dönüş 1'de 4h'te iki aile hariç hepsi, dönüş 2'de değişen altı
vakanın beşi negatifti. Burada +0,288.

Dahası tek başına bir sayı değil, **tutarlı bir desen**:

| Ölçü | `funding_egilim` | Tüm fiyat aileleri arasında en iyi |
| --- | ---: | ---: |
| OOS Sharpe | **+0,288** | −0,348 (donchian) |
| OOS/IS oranı | **+0,197** | −0,306'dan iyisi yok |
| WF katman başarısı | **0,75** (12/16) | 0,562 (momentum) |
| Parametre kararlılığı | **0,125** | 0,167 (cok_faktor) |
| Stres dayanıklılığı | **0,068** | 0,088 (rsi_donus) |

Yedi kapının **dördünü** geçti ve geçemediği üçünden ikisinde (`oos_sharpe`,
`oos_is_orani`) tüm alanın önündeydi.

**Üç kapıda kaldı:**

1. `oos_sharpe` **0,288 < 0,50** — pozitif ama eşiğin yarısından biraz üstü.
2. `oos_is_orani` **0,197 < 0,50** — IS'teki performansın beşte biri OOS'a taşındı.
3. `asgari_islem` **24 < 30** — ve bu en can alıcısı.

**Üçüncü kapı dönüş 1'in tuzağının aynısı.** Orada timeframe'i uzatmak işlem sayısını
dörde bölmüştü; burada birikimli funding rejim değişimlerini seyrekleştiriyor. Bu bir
teknik ayrıntı değil: **24 işlemle ölçülen bir Sharpe'a güvenilmez.** +0,288'in şans olma
olasılığı, o sayının kendisinden daha belirleyici. Kapı tam olarak bu yüzden var.

## 3. Hipotez 2'nin mekanizması **çalıştı**, ama yetmedi

`funding_filtre` en somut soruyu soruyordu: *kırılımların OOS çöküşünü kalabalıklaşma mı
açıklıyor?* Karşılaştırma doğrudan, çünkü aynı kanal, tek fark filtre:

| Ölçü | donchian | funding_filtre | Fark |
| --- | ---: | ---: | ---: |
| OOS Sharpe | −0,348 | **−0,094** | +0,254 |
| OOS/IS | −0,439 | **−0,112** | +0,327 |
| Stres | 0,154 ✗ | **0,129** ✓ | kapı geçti |
| Kararlılık | 0,188 | **0,146** | iyileşti |
| İşlem | 56 | 56 | **değişmedi** |

**Beş ölçüden dördü iyileşti, işlem sayısı hiç düşmedi.** Yani filtre, elediği kırılımların
yerine başkalarını koymadı — sadece kötülerini eledi. Mekanizma gerçek: kalabalıklaşmış
piyasada tetiklenen kırılımlar, sakin funding ortamındakilerden ölçülebilir biçimde daha
kötü.

Ama **yetmedi**: −0,094 hâlâ negatif. Kalabalıklaşma, OOS çöküşünün bir parçasını açıklıyor,
tamamını değil.

## 4. Ne yapılmıyor ve neden

Bu tablonun karşısında üç cazip hamle var ve **üçü de K-042'nin yasakladığı şey**:

1. *"`funding_egilim`in ızgarasını biraz genişletelim, 30 işleme çıksın."* — Bu, eşiğe
   dokunmadan kapıyı delmektir. İşlem sayısını hedefleyerek parametre seçmek, kapıyı
   sonucu bilerek ayarlamaktır ve K-018'in yasakladığı tam olarak budur.
2. *"`funding_filtre`yi diğer ailelere de uygulayalım."* — Her biri yeni bir çekiliş.
   K-042 "dördüncü aile yok" diyor ve o cümle bugün, sonucu görmeden önce yazıldı.
3. *"4h'te deneyelim, işlem sayısı sorunu çözülür."* — Dönüş 1'de ölçüldü ve orada da
   kapı düşürdü. Ayrıca K-042 "timeframe varyasyonu yok" diyor.

Üçü de aynı hatanın farklı kılıkları: **sonucu gördükten sonra çekiliş sayısına karar
vermek.** Durma kuralının sonucu görmeden yazılmasının tek sebebi buydu.

Defter **38** hipotezde. K-039'un açık düzeltmesi (çoklu test) hâlâ açık.

## 5. Ne ölçüldü, ne ölçülmedi

**Ölçülen:** funding, fiyat geçmişinden türetilemeyen gerçek bir bilgi taşıyor. Üç
stratejinin üçü de OOS metriklerinde bütün fiyat ailelerini geçti; biri pozitif OOS Sharpe
üretti. Bu tesadüf değil, tutarlı bir desen.

**Ölçülmeyen:** bu bilginin **yeterli** olup olmadığı. Eşikleri geçmediği için "işe yaramaz"
denemez; "bu ızgarada, bu tanımlarla, bu veride, kapıları geçecek kadar güçlü değil"
denebilir. Fark önemli — ve farkı korumanın tek yolu, şimdi dördüncü bir çekiliş
yapmamak.

**Kayıt altına alınan asıl sonuç:** Faz 4'ten beri ilk kez bir hipotezin *mekanizması*
ölçülebilir biçimde çalıştı (§3). Önceki üç turda mekanizmalar ya hiç etki göstermedi
(dönüş 2: altı vakanın beşi kötüleşti) ya da kendi ayağına bastı (dönüş 1: işlem sayısı).
Bu, funding'in gelecekte — daha büyük bir veri kümesiyle, farklı bir sembol evreninde, ya
da K-039'un düzeltmesi netleştikten sonra — yeniden sorulmaya değer bir soru olduğunun
kaydı. **Ama bugün kapalı.**

## 6. Üretilenler

- `data/funding.py` — indirici, doğrulama, nedensel bar hizalaması (Spike 5, K-042/4).
- `features/indikator.py` — `persentil_sirasi`, `kumulatif`, `kumulatif_persentil`.
- `strategy/kutuphane/` — `funding_ters`, `funding_filtre`, `funding_egilim`; yeni aile
  `kalabalik`.
- Veri kimliği **strateji başına** hesaplanıyor: funding okumayan bir stratejinin kimliği
  değişmiyor, yoksa `sq lab kapilar` her koşuda dokuz yeni çekiliş üretirdi (K-039).
- `tests/unit/test_look_ahead.py::TestFundingLookAhead` — funding üzerinden sızıntı testi.
  Bu sınıf olmadan funding stratejileri look-ahead testinden **muaf** olurdu.

1023 test yeşil (Faz 7 sonunda 991'di).
