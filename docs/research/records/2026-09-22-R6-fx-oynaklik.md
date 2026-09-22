# R6 — FX volatilite/risk-temelli aile: `fx_oynaklik` programı (K-105)

Tarih: 2026-09-22 (UTC). Koşucu: `tools/r5_fx_kos.py` (K-102 hattı; kayıtlar `runs/fx/`, gitignore).
Motor aynen: ask/bid fill, spread, çift başına slippage/komisyon (K-100), proxy finansman (K-098,
`gecici` → promotion engeli), `fx-5x24`. Pencere K-101 ortak aralığı: 2023-11-19..2024-02-29, 1.721 bar;
ısınma 242; **IS 963 / OOS 516 bar (21,5 gün) — h53-h59 aynı barlar, aynı kontrol sayıları** (veri
kimliği `44d51a1d9b85`). Kontrol `fx_evren_esit_agirlik` 21 çift / 0,2 brüt / 120 bar. Sermaye 10.000 USD.

## 1. Sorulan soru ve mekanizma ayrımı

Önceki üç FX programı (K-102, K-103, K-104) **fiyat sinyalinden seçim** yaptı. Bu program seçim
yapmaz ve boyutlandırmaz: kıyasın evrenini, eşit ağırlığını, haftalık takvimini ve takvim çıpasını aynen
alır; tek eklediği, gerçekleşen oynaklığı kendi tabanına göre genişlemiş üyeyi o hafta **nakde**
almaktır. Ölçü `atr(14)/atr(pencere)`; elenen payın yerine kimse geçmez (tavan = filtre öncesi eşit
pay), brüt maruziyet düşer. K-037: engelleyici katman, izin vermez. Eşik sonsuzken kıyasla ekonomik
olarak bit-aynı (fixture testi; gerçek IS'te de `esik ≥ 1,1` noktaları kıyasla metrik/işlem/özkaynak/
maruziyet düzeyinde aynı, yalnız ısınma bölgesi atlama sayacı farklı).

**Üç eksen ölçüldü, ikisi çekiliş harcanmadan dışarıda kaldı** (`runs/fx/oynaklik-kaynak-olcumu.json`,
getiri okunmadan, program kaydında):

| Eksen | Mekanizma | Kapalı tur tahmini (IS, 9 dengeleme) | Karar |
|---|---|---|---|
| Ters oynaklık ağırlık (`1/σ`, 21 çift) | boyutlandırma | üyelik değişimi 0; yalnız toz eşiği (0,11 çift/hafta) | **yapısal olarak ölçülemez** — `asgari_islem` (IS 20) hiçbir noktada; kapı küçültülmez |
| Düşük oynaklık seçimi (`kesitsel_dusuk_oynaklik`, N∈{3,5,10}) | seçim | 3-14 (küme yapışkan, haftalık değişim %38-100 ama 1-2 çift) | **yapısal olarak ölçülemez** — 12 noktanın hiçbiri 20'ye ulaşmıyor (h57 kalıbı); çekiliş harcanmadı |
| Oynaklık genişlemesi filtresi (çift / evren) | maruziyet düşürme | eşik 0,9-1,0'da 16-28; 1,1'de 7-17; 1,2'de 0-9 | **ölçüldü** (h58, h59) |

Oran dağılımı (IS üye-hafta, n=174): q10 0,82-0,89 · q50 ≈ 1,00 · q90 1,11-1,26 → eşik {0,9; 1,0; 1,1; 1,2}
dağılımın gövdesinden; 1,25+ ölü sütun olurdu (K-104'teki rsi48<30 gibi). Pencere {48, 120, 240}; ATR 14
eksen değil (kıyas/risk motoru ölçüsü). Yoğunluk ekseni yok (evrenin tamamı, K-099). Izgara 12 nokta.

## 2. Hipotezler (koşudan önce kayıtlı: h58, h59; bütçe 2/2; K-061 her ikisinde uyarı 0 / incele 0)

| Defter | Çekiliş | Karar (haftalık dengelemede) | Sonucu görmeden yazılan karşı argüman |
|---|---|---|---|
| **h58** | `fx_oynaklik_filtre_cift` | çift başına `atr14/atr(p) > esik` → o çift o hafta nakit | oynaklık genişlemesi yön bilgisi taşımaz; nakde çıkmak yalnız finansman/spread tasarrufu kadar kazandırır, giriş-çıkış maliyeti öder; 0,9 evrenin %70-80'ini nakde alır |
| **h59** | `fx_oynaklik_filtre_evren` | üyelerin **medyan** oranı `> esik` → **hepsi** nakit | IS 9 / OOS 4 karar; tetik 0,9'da 7/9, 1,0'da 3-4/9, ≥1,1'de 0-2/9; tek haftanın şansı; h58'in kaba hâli |

## 3. Sonuçlar

| | h58 `filtre_cift` | h59 `filtre_evren` |
|---|---|---|
| **Seçilen (plato)** | pencere 48, esik 0,9 | pencere 48, esik 0,9 |
| IS geçerli nokta (≥20 tur) | 6/12 (esik ≥ 1,1 tur üretmiyor: 0-16) | 6/12 (esik ≥ 1,1 → 0 tur, kıyasın kendisi) |
| IS geçerli noktalarda getiri | 2 pozitif (+0,102 %, +0,006 %), 4 negatif | 1 pozitif (+0,019 %), 5 negatif (−0,002..−0,145 %) |
| Plato oranı | 0,17 | 0,17 |
| IS net / brüt USD | **+10,20** (+0,102 %) / +12,09 | **+1,87** (+0,019 %) / +3,53 |
| IS maliyet kom/slip/spread/fin = toplam | 0,16 / 0,60 / 0,97 / 0,16 = **1,89** (brütün %16) | 0,12 / 0,44 / 1,01 / 0,10 = **1,67** (brütün %47) |
| IS tur / fill | 28 / 63 | 21 / 42 |
| IS kontrol → **fark** | −10,59 (brüt −9,40, maliyet 1,19) → **+20,79 USD** | −10,59 → **+12,45 USD** |
| OOS net / brüt USD | **+4,57** (+0,046 %) / +5,05 | **0,00** — 4 dengelemenin 4'ünde rejim tetiklendi, tamamı nakit |
| OOS maliyet | 0,07 / 0,26 / 0,06 / 0,08 = **0,48** (brütün %10) | 0 |
| OOS tur / fill | **12 / 26** | **0 / 0** |
| OOS kontrol → **fark** | +20,76 (brüt +21,53, maliyet 0,77) → **−16,20 USD** (−0,162 pp) | +20,76 → **−20,76 USD** |
| Durma kuralı (OOS Sharpe > kıyas 6,08) | 4,44 → **geçemedi** | 0,00 → **geçemedi** |
| OOS `yillik_anlamli` | hayır (Sharpe kanıt değil) | hayır |
| Max DD IS / OOS | 0,096 % / 0,017 % | 0,045 % / 0 |

Kalıp iki çekilişte aynı: **IS'te kıyasın negatif ayında maruziyeti düşürmek kazandırdı (+20,8 / +12,5
USD), OOS'ta kıyasın pozitif ayında aynı düşürme kaybettirdi (−16,2 / −20,8 USD).** Filtre yön bilgisi
taşımıyor; katkısı `−β × kıyas`. Maliyet bağlayıcı değil: h58 OOS'ta maliyet brütün %10'u, fark maliyetin
34 katı. h59'un seçilen noktası OOS'un tamamında nakitte kaldı — 4 karardan 4'ü "çık"; ölçülen şey bir
haftanın değil, bir ayın rejim etiketi.

## 4. Kapılar (mevcut eşikler; ölçülemeyen küçültülmedi)

| Kapı | h58 | h59 |
|---|---|---|
| `asgari_islem` (≥30) | **12 → kaldı** | 0 → kaldı |
| `pbo` (≤0,0087) | **0,278 → kaldı** | 0,683 → kaldı |
| `parametre_perturbasyonu` (≤0,0565) | **0,859 → kaldı** (2 komşu, medyanı −0,73: izole tepe) | 0,638 → kaldı |
| `oos_sharpe` / `oos_is_orani` | 4,44 / 1,83 "geçti" — `yillik_anlamli=False`, kanıt değil (K-102/6) | 0 / 0 → kaldı |
| `evren_dayanikliligi` (≥0,80) | **0,64 → kaldı** (USDJPY çıkınca 4,44 → 2,85; katkı USDJPY 1,40, GBPJPY 0,92, NZDCHF 0,87) | ölçülemedi (OOS'ta pozisyon yok) |
| `max_drawdown`, stres | geçti (stres bozulma 0,0002) | geçti (0,0001) |
| walk-forward, rejim | ölçülemedi (pencere sığmıyor) | ölçülemedi |
| Mutlak engel | `gecici_finansman_modeli` | `gecici_finansman_modeli` |

Kapılar 0/2. Promotion adayı yok.

## 5. Tekrar gereksinimi ve aile kararı

- **h58: elendi.** OOS'ta kontrolün 16,20 USD altında; durma kuralı ölçüsünde geçemedi. Tekrar gereksinimi
  **yok** (program kuralı: yalnız OOS'ta kontrolü geçen çekiliş tekrar turu alır).
- **h59: elendi.** OOS'ta hiç pozisyon almadı; kontrolün 20,76 USD altında. Tekrar gereksinimi **yok**.
- **Aile kararı: kapalı, zayıf.** Bütçe 2/2 doldu; eşik, pencere, ölçü genişletilmez. Ters oynaklık
  ağırlık ve düşük oynaklık seçimi bu pencerede yapısal olarak ölçülemez ve öyle kaydedildi — "ölçülmedi"
  değil, "bu pencere ve bu kapıyla ölçülemez". Aile içinde açık uç yok.

Yapısal not (dört FX programında ortak, K-104/5'i pekiştirir): haftalık dengeleme × 4,3 haftalık OOS'ta
`asgari_islem` (30) hiçbir çekilişte geçilemiyor; oynaklık filtresinde ek olarak eşiğin dağılımın
gövdesinden uzaklaşan yarısı (≥1,1) IS'te bile tur üretmiyor → 12 noktalık ızgaranın etkin boyutu 6.
Bu pencerede FX'te ölçülebilir olan yalnızca "kıyasa göre işaret"; kapılar K-101'in çözümüne bağlı.

## 6. Defter ve kod

- `docs/Arastirma-Programlari.jsonl`: `fx_oynaklik` açıldı (bütçe 2, kaynak ölçümü: oran dağılımı, dışlama
  oranları, kapalı tur tahminleri, yapısal olarak ölçülemeyen iki eksen) ve kapandı.
- `docs/Hipotez-Defteri.jsonl`: h58, h59 (59 satır). Çoklu test fotoğrafı önbellekten yeniden birleştirildi
  (`--birlestir`): 45 ölçülebilir aynı, %5 sınırı 1,0039 aynı, h53-h59 ölçülemez (FX null'u yok, K-102/6).
- Kod: `strategy/kutuphane/oynaklik_filtre.py` (`FxOynaklikFiltreCift`, `FxEvrenOynaklikFiltre`; ortak
  iskelet `FxEvrenEsitAgirlik` üstüne `_aday_uyeler` + dinamik tavan + takvim çıpası), `izgaralar.
  FX_OYNAKLIK_CEKILISLERI`, `coklu_test_evren.SINYAL_OZELLIKLERI` (+2), `tools/r5_fx_kos.py`
  (`PROGRAM_PORTFOY`: bu program `EVREN_ESIT`). Testler +5 (`TestOynaklikFiltre`). Yeni veri/execution/
  audit katmanı yok, refactor yok.
- Koşu: `tools/r5_fx_kos.py kos` × 2 (4,7 s / 4,6 s, git `ed0b6942` dirty); h58 OOS hash `b5acf4f53869`,
  h59 OOS `f9a3de7e72e3`, kontrol OOS `5689acde9405` (h53-h57 ile aynı), kontrol IS `965ced69ff4f`.
