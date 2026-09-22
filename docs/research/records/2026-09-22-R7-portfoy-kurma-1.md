# R7 — kripto evreninde ilk portföy kurma programı: `portfoy_kurma` (h60-h61, K-108)

Tarih: 2026-09-22 (UTC). Koşucu: `tools/faz12_evren_kos.py` (Faz 12/16 hattı; kayıtlar `runs/faz12/`,
gitignore). Evren: kripto PIT tablo `27b7a16ed0ed`, 429 sembol, **79.540 bar** (Faz 16'da 79.420 — depo
120 bar uzamış, K-080; veri kimliği `1b1ded91fbec`, h51/h52'ninkinden farklı); spot, ölçülmüş maliyet
(`config/maliyet` global, proxy yok); IS 0-55.678 / OOS 55.678-79.540 (23.862 bar ≈ 2,7 yıl, `yillik_anlamli`
**evet**); WF 32 katman; K-059 değerleme. Kıyas `evren_esit_agirlik` **seçilen yoğunlukta** (Faz 16 kalıbı),
haftalık (168), 0,2 brüt. 10.000 USDT. Araştırma yolu risk motorsuz (K-073, değişmedi).

**Funding:** kripto evreni spot; gerçek funding verisi (`data/turev/funding`) K-042/K-068'de sinyal olarak
ölçülüp kapandı, motorda maliyet değil (K-079 perp katmanı yok). Bu programda funding **ne maliyet ne sinyal**;
uydurulmadı. FX'e ait iş yok.

## 1. Mekanizmalar (koşudan önce kayıtlı: h60, h61; bütçe 2/2; K-061 ikisinde uyarı 0 / incele 0)

İskelet `kurma_evren` (Faz 16) ile aynı: **seçim, sıralama (30 günlük kote hacim) ve dengeleme takvimi kıyasla
aynen**, değişen yalnız kurma. Kapalı konum ızgarada yok ve kıyasla bit-aynı (testle).

| Defter | Çekiliş | Mekanizma | Izgara (12) |
|---|---|---|---|
| **h60** | `portfoy_korelasyon` (`evren_korelasyon_budama`) | `kur(korelasyon=)`: `sec` sırayla giderken tutulan bir isimle 720 barlık log-getiri `\|ρ\| > tavan` olan aday atlanır, sıradaki alır; ölçülemeyen çift 1,0 (budanır, K-019). Yeni kanca `EvrenEsitAgirlik._korelasyon_icin` (kıyas `None`, bit-aynı) | tavan {0,5; 0,6; 0,7; 0,8} × n {5,10,20}; pencere 720 sabit |
| **h61** | `portfoy_oynaklik_hedefi` (`evren_oynaklik_hedefi`) | uygun üyelerin `atr14/close` medyanı σ_t > hedef ise brüt `0,2 × hedef/σ_t`; **yalnız düşürür** (K-050) | hedef {0,010; 0,0125; 0,015; 0,020} × n {5,10,20} — hedefler ölçülen IS dağılımından (q10 0,0099 / q25 0,0123 / q50 0,0165 / q75 0,0205; `runs/faz12/portfoy-kaynak-olcumu.json`, getiri okunmadan) |

Optimizasyon (ERC / min-var) açılmadı: `kurma.py` onu ayrı çekiliş sayıyor; iki kapalı-formlu mekanizma yeterli.

## 2. Sonuçlar (OOS, 10.000 USDT; kıyas seçilen yoğunlukta)

| | h60 korelasyon budaması | h61 oynaklık hedefi |
|---|---|---|
| **Seçilen (plato)** | tavan 0,5, n 20 (plato oranı 0,08) | hedef 0,010, n 5 (plato 0,17) |
| IS Sharpe | 0,577 (12/12 geçerli, 0,20-0,58) | 0,545 (12/12 geçerli, 0,01-0,55) |
| **OOS net / brüt USDT** | **−2.166,59** (−21,7 %) / −2.047,73 | **+1.007,02** (+10,1 %) / +1.109,83 |
| OOS maliyet kom / slip = toplam | 77,69 / 41,17 = **118,85** | 67,20 / 35,61 = **102,81** |
| OOS turnover / tur | 7,77 / 350 | 6,72 / 43 |
| OOS ort. / azami maruziyet | 0,102 / 0,238 | 0,128 / 0,251 |
| OOS Sharpe / max DD / CAGR | **−1,113** / **31,2 %** / −8,6 % | **0,461** / **14,1 %** / +3,6 % |
| **Kıyas (aynı n)** net / Sharpe / DD / maruziyet | −1.272,83 (−12,7 %) / −0,263 / 27,4 % / 0,193 | +1.562,40 (+15,6 %) / 0,462 / 20,2 % / 0,194 |
| Kıyas maliyet / turnover / tur | 111,83 / 7,31 / 260 | 94,87 / 6,20 / 43 |
| **Benchmark farkı** net / Sharpe | **−893,76 USDT / −0,850** | **−555,38 USDT / −0,001** |
| Durma kuralı (OOS Sharpe > kıyas ∧ > 0,333) | −1,113 → **geçemedi** | 0,4606 vs 0,4617 → **geçemedi** (0,333'ü geçiyor, kıyası geçmiyor) |

Funding: 0 (spot). Finansman: yok.

## 3. Kapılar (`kapilar_v2.butun_kapilar`, 11 kapı; eşikler aynen)

| Kapı | Sınır | h60 | h61 |
|---|---|---|---|
| `oos_sharpe` | ≥ 1,04 (K-071) | −1,113 ✗ | 0,461 ✗ |
| `oos_is_orani` | ≥ 0,5 | −1,93 ✗ | **0,845 ✓** |
| `wf_katman_basari` | ≥ 0,6 | **0,625 ✓** | **0,633 ✓** |
| `parametre_kararliligi` | ≤ 0,35 | 0,109 ✓ | 0,117 ✓ |
| `asgari_islem` | ≥ 30 | 350 ✓ | 43 ✓ |
| `max_drawdown` | ≤ 0,25 | 0,312 ✗ | 0,141 ✓ |
| `stres_dayanikliligi` | ≤ 0,15 | 0,039 ✓ | 0,048 ✓ |
| `pbo` | ≤ 0,0087 | 0,285 ✗ | **0,042 ✗** (defterdeki en düşük; h51 0,277, h52 0,201) |
| `parametre_perturbasyonu` | ≤ 0,0565 | 0,650 ✗ | 0,193 ✗ |
| `rejim_kararliligi` | ≥ 0,685 | −1,372 ✗ (`yukselen`) | 0,124 ✗ (`dusen`) |
| `evren_dayanikliligi` | ≥ 0,75 | ölçülemedi (tam Sharpe negatif; BTC çıkınca −1,19) | **1,001 ✓** (NEIRO çıkınca 0,461 → 0,461) |
| **Geçen** | | **4/11** | **7/11** |
| Mutlak engel | | `dirty` (çalışma ağacı; koşu deterministik) | `dirty` |

## 4. Okuma

1. **h60 korelasyon budaması: elendi, mekanizma tersine çalıştı.** Tavan 0,5 / n 20'de budama ortalama
   maruziyeti kıyasın yarısına indirdi (0,102 vs 0,193: "sıradaki alır" dolduramıyor, ~37 uygun üyenin
   çoğu BTC betasıyla birbirine bağlı) ama DD **arttı** (31 % vs 27 %) ve net kıyasın 894 USDT altında.
   Hayatta kalan isimler düşük korelasyonlu = idiyosenkratik/likiditesi düşük olanlar: yarı maruziyetle
   kıyastan **daha çok** komisyon (77,7 vs 73,1) ve tur (350 vs 260). Sonucu görmeden yazılan karşı argüman
   ("0,5 listeyi derinlere iter, maliyet artışı kazancı yener") gerçekleşti, üstüne DD de bozuldu.
   `oos_is_orani` −1,93: IS'te en iyi görünen nokta OOS'ta en kötü — seçim etkisinin klasik imzası.
2. **h61 oynaklık hedefi: Sharpe-nötr, elendi.** OOS Sharpe 0,4606 vs kıyas 0,4617; DD 20,2 % → 14,1 %,
   getiri 15,6 % → 10,1 %, maruziyet 0,194 → 0,128 — hepsi **aynı oranda** (≈ ×0,66). Bu, zaman-değişken
   bir kaldıraç düşürmenin mekanik sonucu: Sharpe kaldıraçtan bağımsız kalıyor, yani σ_t'nin **zamanlama
   bilgisi yok**. R6 FX'te aynı sınıfın ayrık hâli (h58/h59) IS'te kazanıp OOS'ta kaybetmişti; burada
   kaybetmiyor ama kazanmıyor da. 7/11 kapı ve pbo 0,042 (defter rekoru) mekanizmanın **istikrarını**
   ölçüyor, üstünlüğünü değil — kıyasın ölçekli kopyası da istikrarlıdır. Promotion adayı değil;
   durma kuralına göre tekrar/doğrulama adımı **yok** (kıyası geçmedi).
3. **Faz 16 bulgusu aynen duruyor:** kurma çekilişleri genelleşme kapılarını (h61: `oos_is_orani`,
   `evren_dayanikliligi`, walk-forward) geçiyor, Sharpe/PBO/pertürbasyon kapılarını geçmiyor. Bu paket
   ikinci kez ölçtü: kurma katmanı **risk profilini** değiştiriyor, **risk-ayarlı getiriyi** değil.
4. **Yan gözlem (çekiliş değil):** kıyasın kendisi bu OOS'ta n=5'te +0,46, n=20'de −0,26 Sharpe —
   yoğunluk ekseni K-072'nin ölçtüğü gibi bir kaldıraç; K-072 ikinci çizgisi (0,333) yürürlükte.

## 5. Karar

- **h60 elendi. h61 elendi. Aile (`portfoy_kurma`) kapalı**; bütçe 2/2 doldu, üçüncü çekiliş yok.
- Tekrar/doğrulama gereksinimi **yok**: hiçbiri kıyası geçmedi; tek OOS başarısı da yok.
- R7'nin "portföy düzeyi kapılar" kalemi için ölçülen şey: oynaklık hedefi DD'yi maruziyetle orantılı
  düşürüyor (risk aracı olarak öngörülebilir), Sharpe'a katkısı sıfır → bir promotion kapısı değil, olsa
  olsa risk motorunun mevcut `azami_brut_maruziyet` iştahının bir ifadesi (K-033). Yeni kapı **tanımlanmadı**.
- Kod: `strategy/kutuphane/evren_portfoy.py` (iki sınıf), `evren_esit_agirlik._korelasyon_icin` kancası
  (kıyas `None`, bit-aynı: `test_evren_kurma` bant testi + `test_coklu_referans`), `izgaralar.
  PORTFOY_CEKILISLERI`, `coklu_test_evren.SINYAL_OZELLIKLERI` (+2; budama için sıralama ölçüsü kaydırma
  **yaklaşımı**, turnover bandıyla aynı sınır), `tools/faz12_evren_kos.py` `PROGRAM_AYARI`. Testler +13
  (`tests/unit/test_evren_portfoy.py`). Execution/risk/audit değişmedi.
- Koşu: 1.282 s / 940 s (3 işçi); OOS hash h60 `a4d69c6b3bc6` (kıyas n20 `5fac9aaa19ec`), h61
  `6b62b42301f8` (kıyas n5 `2a3d31aca01f`); git `a9982f60` dirty.
- Çoklu test: h60/h61 null'u `tools/faz12_coklu_test.py --deneme 500 --seed 0 --yalniz evren` ile
  ölçüldü ve fotoğraf yenilendi (§6).

## 6. Çoklu test fotoğrafı (K-044, `tools/faz12_coklu_test.py --deneme 500 --seed 0`)

h60/h61 null'u ölçüldü (4.939 s + 2.907 s; kaydırılan `kote_hacim` / `atr`, K-064 sızıntı payı). Birleşik:
**ölçülebilir 47** (31 tek sembollü + 16 evren; h53-h59 FX ölçülemez), defter 61, **%5 sınırı 1,0039**
(değişmedi), GA %5 bandı 0,98-1,06, yürürlükteki sabit **1,04** korunuyor (gerçek yanlış pozitifi %4,2).
Fotoğraf `docs/research/coklu-test-olcum.json`; `TestEsigiDefteBagla` yeşil.
