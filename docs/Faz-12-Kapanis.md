---
proje: ScryneQuant
faz: 12
tarih: 2026-09-17
type: rapor
durum: kapandı
---
# Faz 12 — Araştırma programları: kapanış

**Sonuç:** Üç program bütçesi içinde kapandı ve raporlandı, eşik yeniden ölçüldü. **Promotion
kapılarını geçen çekiliş yok.** Defter 38 → 48; K-054'ün 11 kapısına karşı en iyi çekiliş 6/11.

| Program | Bütçe | Harcanan | En iyi OOS Sharpe | En iyi kapı | Rapor |
| --- | ---: | ---: | ---: | ---: | --- |
| `kesitsel_fiyat` | 6 | 4 (durma kuralı) | −0,18 | 4/11 | `Faz-12-Kesitsel-Fiyat-Raporu.md` |
| `turev_evren` | 4 | 4 | 0,26 | 6/11 | `Faz-12-Turev-Evren-Raporu.md` |
| `makro_rejim` | 3 | 2 (motor harcanmadı) | 0,22 | 4/11 | `Faz-12-Makro-Rejim-Raporu.md` |

## Bitti kriteri

| Kriter | Durum |
| --- | --- |
| Her program kendi bütçesi içinde kapanmış | ✅ 4/6, 4/4, 2/3 |
| Her programın sonucu kapılara karşı raporlanmış | ✅ üç rapor |
| Defter büyümesi sonrası `oos_sharpe` eşiği yeniden ölçülmüş | ✅ 41 çekiliş, 1,039 → sabit 1,04 (K-064) |
| Rejim motoru kullanıldıysa yumuşatılmış olasılık testle yasak | — kullanılmadı |

## Ortak bulgu

Evren kıyasının (`evren_esit_agirlik`: PIT üst 50'nin likit ilk N'i, eşit ağırlık) üstüne
konan hiçbir katman — **seçim** (kesitsel sıralama), **dışlama** (funding/basis),
**engel** (makro stres) — kıyasın kendi gürültü bandından ölçülebilir biçimde ayrışmadı.
Kıyas IS 0,34, WF 0,85-0,95; çekilişler IS 0,26-0,88, WF −0,40…0,86, OOS −0,97…0,26.

## Faz boyunca gelen kararlar

- **K-059:** barı biten sembolde pozisyon 48 bar sonra sıfır değer (9 takılı pozisyon ölçüldü,
  4'ü token göçü).
- **K-060:** makro stres engeli: günlük PIT, ertesi gün görünürlük, yalnızca risk azaltan niyet.
- **K-061:** gizli tekrar çekiliş dedektörü (paralel oturum).
- **K-062/K-063:** sürekli açık host; VPS askıda, yerel ikinci bilgisayar.
- **K-064:** null'da sızıntı payı; eşik 1,04.

## Altyapı kazanımları (sonraki programlar için)

Evren değerlendirme hattı (11 kapı, havuzlu koşucu), arşiv funding/premium/makro vintage
verisi ve PIT hizalamaları, kıyas + filtre iskeleti (oran 0'da kıyasla bit düzeyinde aynı),
evren çekilişlerini sayan çoklu test null'ı, bellek bütçesi (süreç başına 6,2 → 4,5 GB).

## Açık kalemler

1. Sızıntı paylı yeni null koşusu + ≈2.000 iterasyon (K-064/4) — sürekli açık hostta.
2. Token göçü eşlemesi (K-059/4) — PIT kaynak gelmeden uydurulmaz.
3. `evren_dayanikliligi` eşiği hâlâ iştah (K-058/2): pozitif Sharpe'lı adaylar 0,17-0,59.
4. Rejim motoru çekilişi (Faz 16'da ayrı program kaydıyla).

**Sırada (K-060 plan kaydı):** Faz 14 — sürekli açık host (ikinci bilgisayar, K-063), süreç
dışı kill switch, alarmlar, çok enstrümanlı paper motoru ve 7/24 ileriye dönük izleme.
