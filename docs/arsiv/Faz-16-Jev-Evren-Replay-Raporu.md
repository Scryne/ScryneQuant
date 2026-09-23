---
proje: ScryneQuant
faz: 16
tur: ölçüm (çekiliş değil — Jev sinyal üretmez, K-067)
tarih: 2026-09-19
type: rapor
durum: kapandı — K-076
---
# Faz 16 — Jev'in yönü, yayın sonrası temiz pencerede 50 sembol

**Sonuç: Jev'in yön kararı yazı-turadan ayırt edilemiyor ve maliyet sonrası kesin zarar
ediyor.** 9.850 karar, 1.099 yönlü; isabet **%49,0** (CI %95 46,1–52,0); 4 barlık net
getiri **−%0,38** / işlem (SE 0,056 → t ≈ −6,9); brüt bile negatif (−%0,08). Güven
kalibrasyonu yok. Jev'in ileriye dönük yön isabeti K-045 istisnasının sayısal koşulunu
karşılamıyor; **Jev yön ekseni kapandı.**

## 1. Kurulum (K-075 + K-076)

| | |
| --- | --- |
| Pencere | 2026-09-10 19:00 → 2026-09-18 23:00 UTC — model yayınından (`jev-1.13.0`, 2026-09-10 18:38Z) sonraki her bar; `leak_riski=false` (K-075: kesim ≤ yayın ≤ bar) |
| Evren | PIT tablosu `27b7a16ed0ed`, ay 2026-09, sıra 1–50 (önceki ay kote hacmi; K-052) — bugünün listesi değil |
| Veri | `data/evren/<sembol>/1h.parquet` arşivden 2026-09-18'e uzatıldı (`sq data arsiv-indir`, SHA'lar `1h.kaynak.json`); funding 43 sembolde (7'sinde vadeli yok → durumda `eksik`, uydurulmadı) |
| Soru seti / marj / durum | K-074 ile aynı: `SORU_SHA256 e6f91afb…`, marj 0,20, `durum_surumu` 1. **Hiçbir şey ayarlanmadı.** |
| Koşu | `sq jev tekrar --sembol X --depo data/evren --son-n-bar 197`, 50 defter `runs/jev/evren/<sembol>.sqlite`, 4 paralel, 13 dk, 0 hata, 50/50 zincir geçerli |
| Değerlendirme | `tools/faz16_jev_evren_degerlendir.py` — `jev/sonuc.py` ile aynı tanımlar (giriş `open[t+1]`, ufuk 4, gidiş-dönüş 30,6 bps), havuz + saat-küme |

## 2. Sonuçlar

| Ölçüm | Değer |
| --- | ---: |
| Karar / geçerli | 9.850 / 9.850 |
| Çekimserlik | **%88,6** (sembol medyanı %90,9; BTC %98,5) |
| Yön dağılımı | flat 8.732 · short 835 · long 283 |
| Yönlü, sonucu bilinen | **1.099** |
| Yön isabeti (4 bar) | **539 / 1.099 = %49,0** (Wilson %95: 0,461–0,520) |
| Saat-küme (aynı saat tek gözlem) | 183 saat, %51,4 (CI 0,44–0,59); aynı saatte medyan 5 sembol yön alıyor, %86'sı aynı yönde → semboller bağımsız değil, etkin n ≈ 183 |
| Al-tut aynı barlarda | 4.932 / 9.650 = %51,1 |
| Net getiri / işlem, 4 bar | **−%0,383** (SE 0,056) |
| Brüt getiri / işlem, 4 bar | −%0,077 |
| Net, 1 bar / 24 bar | −%0,370 / −%1,36 |
| Long ayrı / short ayrı | %47,2 (n 265) / %49,6 (n 834) |
| Güven kovaları isabet | 0–0,4: %46 · 0,4–0,5: %53 · 0,5–0,6: %46 · 0,6–0,7: %44 · 0,7–1: %54 — monoton değil |

**Sembol başına:** n ≥ 10 olan 30 sembolde isabet medyanı %44,7, aralık %9–%73. Beş sembol
%60'ın üstünde (ENA, UNI, ALLO, BICO, PENGU); 30 yazı-tura sembolde beklenen **en iyi** oran
%71 (simülasyon, seed 0) — yani en iyiler dağılımın kuyruğu, keşif değil. Bunlardan birini
seçmek K-039'un saydığı çekiliştir ve yapılmadı.

## 3. Okuma

- Jev'in çıktısı yönsüz değil: 1.099 kez yön verdi ve %76'sı short'tu (pencere düşüş
  ağırlıklı: rejim etiketi 3.896 `trend_asagi`). Ama short'lar da %49,6.
- Brüt bile negatif olduğu için sorun maliyet değil; marj değil (K-075 raporu: marj 0'da da
  aynı dağılım); örneklem değil (CI 0,50'yi içeriyor, üst sınır 0,52).
- Bu ölçüm Jev'in **bu durum betimlemesiyle, bu soru setiyle, 1h'de** yön bilmediğini
  gösteriyor. Başka bir durum/soru/timeframe yeni bir çekiliştir (K-074/7) ve K-045'in
  "ölçüyle gerekçelendirilmiş farklı bilgi kaynağı" şartına Jev'in kendisi artık aday değil.
- K-074'ün "Jev sinyal üretmez" kararı değişmedi; bu rapor o kararı test etmedi, doğruladı.
- Gölge koşusu `golge-1` hostta açık kalıyor: bedeli sıfıra yakın, ileriye dönük doğrulama
  bedava. Sonuç bu raporu çürütürse (CI'ın tamamı 0,50 üstünde) yeniden açılır.

Ham: `runs/jev/evren/_degerlendirme.json` (sembol başına tam tablo), 50 defter, `kos.log`.
