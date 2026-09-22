# R7(2) — kripto alfa/sinyal araştırması: K-068 ön koşulu + `kesit_oynaklik` programı (h62, K-109)

Tarih: 2026-09-22 (UTC). Koşucu: `tools/faz12_evren_kos.py`; ön koşul ölçümü `tools/r7_sinyal_gucu.py`.
Evren/pencere R7(1) ile aynı: kripto PIT `27b7a16ed0ed`, 429 sembol, 79.540 bar, spot, ölçülmüş maliyet
(proxy yok), IS 0-55.678 / OOS 55.678-79.540 (23.862 bar ≈ 2,7 yıl, `yillik_anlamli` evet), WF 32 katman,
K-059; kıyas `evren_esit_agirlik` **n=10 sabit** (Faz 12 kesitsel kalıbı, K-072 "kıyas ayarlanmaz"),
haftalık, 0,2 brüt; ikinci çizgi 0,333 (K-072). Funding ne maliyet ne sinyal (spot, K-079). FX işi yok.

**Bağlam:** K-078/1 fiyat-türevli yönlü/kesitsel/rejim/seçim hattını "kapalı, yeniden açılmaz" yazmıştı;
Scryne'ın R7(2) talimatıyla ve K-068'in **ölçülebilir geri dönüş koşulu** uygulanarak sınırlı yeniden açılış:
program yalnız IS'te ölçülmüş ileriye dönük sıralama gücü sıfırdan ayrışan sinyal için açılır.

## 1. K-068 ön koşulu: 11 aday sinyalin IS sıralama gücü (çekiliş değil; OOS'a bakılmadı)

`tools/r7_sinyal_gucu.py`: 292 haftalık dengeleme anında (bar 1.442..55.510) kıyasın aday kümesinde
(ort. üye ≈ 37) sinyal ↔ 168 bar ileri log getiri Spearman IC; t = ort/(sd/√n); IS iki yarısı.
**Ölçüt (koşudan önce yazıldı):** IC için |t| ≥ 2,0 ∧ iki yarıda aynı işaret → aday.

| Sinyal | IC ort | t | pozitif hafta | yarı 1 / yarı 2 | Aday |
|---|---|---|---|---|---|
| ts momentum `roc` 168 / 336 / 720 / 1440 | +0,009 / +0,015 / +0,030 / −0,018 | +0,59 / +0,98 / **+1,94** / −1,10 | 0,50-0,53 | 720: +0,066 / −0,006 | hayır |
| ts ters `−roc` 24 / 72 / 168 | −0,023 / −0,027 / −0,009 | −1,57 / −1,86 / −0,59 | 0,46-0,50 | 72: −0,048 / −0,006 | hayır |
| sapma `−(close−sma)/atr` 168 / 720 | −0,029 / −0,019 | −1,93 / −1,28 | 0,47-0,49 | işaret döndü | hayır |
| hacim şoku `hacim24/hacim720` | +0,014 | +0,98 | 0,51 | +0,037 / −0,009 | hayır |
| **düşük oynaklık `−atr(p)/close`** p 14 / 168 / 336 / 720 / 1440 | **+0,127 / +0,140 / +0,139 / +0,140 / +0,109** | **+7,76 / +7,56 / +7,32 / +7,37 / +5,95** | 0,62-0,68 | +0,13 / +0,15 (hepsi aynı işaret) | **evet** |

İşaret testleri (bilgi amaçlı, ölçüt değil): `roc720 > 0` üyeleri ≤ 0 üyelerinden +0,87 pp/hafta ileri
(t 2,07); `roc72 < 0` üyeleri ≥ 0 üyelerinden −1,44 pp (t −3,30, yani 72 saatlik **devam**). IC ölçütünü
geçmedikleri için program açılmadı; kayıt K-109/4'te.

Tek aday: kesitsel düşük oynaklık. Faz 12'nin `kesitsel_dusuk_oynaklik` çekilişleri hiç harcanmamıştı
(program güç+ters ile 4/4 kapandı; defterde 0 kayıt). Izgara Faz 12 tanımının **aynısı**; yeni eksen, yeni
strateji kodu yok. K-061: uyarı 0 / incele 0.

## 2. Program `kesit_oynaklik` (bütçe 2; h62 haftalık; aylık yalnız haftalık kıyası geçerse)

| | h62 `r7_dusuk_oynaklik_haftalik` (`kesitsel_dusuk_oynaklik`) |
|---|---|
| Mekanizma | her haftalık dengelemede `atr(pencere)/close` en **düşük** N isim eşit ağırlık (kıyasla aynı evren/takvim/kurma; tek fark skor) |
| Izgara | pencere {168, 336, 720, 1440} × n {5, 10, 20} (12) |
| **Seçilen (plato)** | pencere 1440, n 5 (plato oranı 0,08; 12/12 geçerli, IS Sharpe 0,50-0,93 hepsi pozitif) |
| IS Sharpe / getiri | 0,929 / +148,6 % (237 tur) |
| **OOS net / brüt USDT** | **+603,35** (+6,0 %) / +681,00 |
| OOS maliyet kom / slip = toplam | 50,75 / 26,90 = **77,65** (brütün %11) |
| OOS turnover / tur / ort. maruziyet | 5,08 / 46 / 0,188 |
| OOS Sharpe / max DD / CAGR | **0,287** / **12,7 %** / +2,2 % |
| **Kıyas n=10** net / Sharpe / DD / CAGR | +925,79 (+9,3 %) / **0,302** / 18,8 % / +3,3 % (maliyet 107,68, turnover 7,04, 108 tur, maruziyet 0,194) |
| **Benchmark farkı** net / Sharpe | **−322,44 USDT / −0,015**; ikinci çizgi 0,333'ün de altında |
| Durma kuralı | **geçemedi** → aylık çekiliş harcanmadı |
| Funding / finansman | 0 / yok (spot) |

### Kapılar (11; eşikler aynen, `oos_sharpe` 1,04)

| Kapı | Sınır | h62 |
|---|---|---|
| `oos_sharpe` | ≥ 1,04 | 0,287 ✗ |
| `oos_is_orani` | ≥ 0,5 | **0,309 ✗** (IS 0,93 → OOS 0,29) |
| `wf_katman_basari` | ≥ 0,6 | 0,613 ✓ (31 katman, WF Sharpe 0,87) |
| `parametre_kararliligi` | ≤ 0,35 | 0,097 ✓ |
| `asgari_islem` | ≥ 30 | 46 ✓ |
| `max_drawdown` | ≤ 0,25 | 0,127 ✓ |
| `stres_dayanikliligi` | ≤ 0,15 | 0,114 ✓ |
| `pbo` | ≤ 0,0087 | 0,110 ✗ |
| `parametre_perturbasyonu` | ≤ 0,0565 | 0,151 ✗ |
| `rejim_kararliligi` | ≥ 0,685 | 0,113 ✗ (`yukselen`) |
| `evren_dayanikliligi` | ≥ 0,75 | **0,221 ✗** (XRP çıkınca OOS Sharpe 0,287 → 0,063) |
| **Geçen** | | **5/11**; mutlak engel `dirty` (çalışma ağacı) |

## 3. Okuma

1. **Sıralama gücü gerçek, sonuç kıyas altı.** IS'te IC +0,14 (t ≈ 7) ve 12/12 ızgara noktası pozitif; ama
   OOS'ta kıyasın 322 USDT altında, Sharpe 0,287 < 0,302 < 0,333. Düşük oynaklı N ismi taşımak riski düşürüyor
   (DD 12,7 % vs 18,8 %, maliyet −28 %) ve getiriyi aynı ölçüde düşürüyor — h61'in (oynaklık hedefi) kesit-içi
   hâli aynı yere çıktı: **oynaklık bilgisi risk profilini değiştiriyor, risk-ayarlı getiriyi değil.**
2. **OOS tek isme bağlı:** evren dayanıklılığı 0,22 — XRP çıkarılınca Sharpe 0,29 → 0,06. n=5 düşük oynaklık
   sepeti fiilen BTC/ETH/BNB/XRP/… sabit bir büyük-cap sepeti; OOS getirisinin çoğu XRP'nin 2024 sonu
   hareketi. `oos_is_orani` 0,31: IS üstünlüğü OOS'a taşınmadı — K-068'in sekiz seçim çekilişinde gördüğü
   imza dokuzuncu kez.
3. **K-068 ek şartı, tek başına yetmedi.** IS'te ölçülen sıralama gücü (IC) OOS'ta kıyas-üstü sonuca
   dönüşmedi; IC'nin kaynağı büyük ölçüde "yüksek oynaklı altcoin'ler ortalamada kaybeder" (kıyastan az
   kaybetmek ≠ kıyası geçmek). Bundan sonra bir kaynak ölçümünün IC'si yalnız "aday" der; kıyas-üstü olma
   iddiasını taşımaz (K-109/4).
4. Ön yazılı karşı argümanların üçü de gerçekleşti (mutlak getiri düşük; büyük-cap sepet, rejim kapısı
   0,11; genelleşme kapıları kaldı).

## 4. Karar

- **h62 elendi.** Kıyası ve ikinci çizgiyi geçmedi; 5/11 kapı. Aylık çekiliş durma kuralı gereği
  **harcanmadı** (bütçe 1/2). **Aile (`kesit_oynaklik`) kapalı.** Tekrar gereksinimi **yok**.
- Diğer 10 sinyal K-068 ölçütünü sağlamadığı için program açılmadı, çekiliş harcanmadı.
- R7(2) kripto alfa/sinyal turu bu pakette **FAIL**: ölçülen 11 fiyat/hacim sinyalinden biri ön koşulu geçti,
  o da OOS'ta kıyasın altında kaldı. Mevcut veri, evren ve kapılar kapsamında doğrulanmış kripto kesit/ts
  sinyali yok (evrensel iddia değil).
- Kod: `tools/r7_sinyal_gucu.py` (ölçüm aracı, scipy yok), `izgaralar.KESIT_OYNAKLIK_CEKILISLERI` (Faz 12
  ızgarasının aynısı, yeni program adıyla), `faz12_evren_kos.PROGRAM_AYARI`. Strateji/motor/kapı/execution/
  risk/audit değişmedi. Ölçüm `runs/faz12/r7-sinyal-gucu.json` (program kaydında da).
- Koşu: 879 s (3 işçi); OOS hash `a3ddeeb9339e`, kıyas `9652afef865d`; git `050c6c84` dirty.

## 5. Çoklu test fotoğrafı (K-044)

h62 null'u ölçüldü (2.989 s; kaydırılan `skor_ham`, K-064 sızıntı payı). Birleşik: **ölçülebilir 48** (31 tek
sembollü + 17 evren; FX ölçülemez), defter 62, **%5 sınırı 1,0039** (değişmedi), GA %5 bandı 0,98-1,06,
yürürlükteki sabit **1,04** korunuyor (gerçek yanlış pozitifi %4,2). `COKLU_TEST_CEKILIS_SAYISI` 47 → 48
(K-081 kuralı).
