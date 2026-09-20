# R1(c) — `oos_sharpe` eşiğinin 45 çekilişle yeniden ölçümü (2026-09-20)

**Amaç (ROADMAP-RESET R1(c)):** defter 43 → 45 ölçülebilir çekilişe büyüdü (h51, h52; Faz 16
`kurma_evren`); K-044/064/071'in null dağılımı yeniden koşuldu. **Bu doküman ölçümü ve
engeli kaydeder; eşik kararı vermez** (R1(d), Scryne). `research/kapilar.py` sabitleri
(`COKLU_TEST_ESIGI = 1.04`, `COKLU_TEST_CEKILIS_SAYISI = 43`) **değiştirilmedi**.

## 1. Kimlik

| Alan | Değer |
| --- | --- |
| Komut | `tools/faz12_coklu_test.py --deneme 500 --seed 0` |
| Kod | `209ff2a` (temiz ağaç; `git.dirty=false` sonuç dosyasında) |
| Veri | `data/evren` (734 sembol), **veri sonu 2026-09-14 23:00 UTC** (K-080: 50 sembol `--bitis-gun 2026-09-14` ile geri sarıldı, 684'ü zaten oradaydı); PIT tablo `27b7a16ed0ed` (`tablo_hash b06857c0…`) |
| h51/h52 veri kimliği | `a06553c923aa…` (defter satırı `veri_sha256`; `runs/faz12/kurma_*.json`) |
| Çekiliş | 45 ölçülebilir (31 tek sembollü + 14 evren), defter 52 (7 ölçülemez: tek noktalı ızgara / 1d geçersiz aday) |
| Null | dairesel kaydırma, sızıntı payı (`sizinti_bar` h51/h52: 890), 500 deneme, seed 0, her çekiliş **aynı oran dizisi** |
| Önbellek | 43 çekilişlik `runs/faz12/coklu-test/*.json` **yeniden kullanıldı** (dokunulmadı); yalnız h51/h52 hesaplandı |
| Sonuç dosyası | `runs/faz12/coklu-test-birlesik-500-0.json` (`uretildi 2026-09-20 17:36:57 UTC`); log `runs/faz12/coklu-test-500-45-r1c-2.log` |
| Süre | h51 ≈ 51 dk, h52 ≈ 47 dk (≈6 s/deneme) |

## 2. Engel ve A kararı

**Engel (ilk koşu, `coklu-test-500-45-r1c.log`):** h51'in (`evren_oynaklik_agirlik`, 1/σ)
null'u 141. denemede `KurmaHatasi: REDUSDT: oynaklık pozitif ve sonlu olmalı, verilen 0.0`
ile düştü. Dairesel kaydırma bir sembole ATR=0 pencere düşürdü; `Aday.__post_init__`
(`strategy/kurma.py`) bunu hata sayıyor, `evren_esit_agirlik.on_bar` sembolü ayıklamıyordu.
Gerçek veride bu dal hiç tetiklenmemişti. Tek sembol bütün evren adımını düşürüyordu.

**Seçenekler ve karar (Scryne, A):**

| | Ne | Neden reddedildi / kabul edildi |
| --- | --- | --- |
| A | Strateji katmanı ölçülemeyen (0/NaN/inf) oynaklıklı sembolü `Aday` kurmadan **aday dışı** bırakır; `Aday` sözleşmesi değişmez; null'a istisna yok | **Kabul.** Risk motorunun volatilite guard'ıyla aynı semantik ("ölçülemeyen = geçilmemiş"); canlıda 14 düz barlı tek bir illikit sembolün `EvrenPaperMotoru`'nu durdurmasını da engeller. Null ve gerçek koşu **aynı** kodu görür |
| B | Null üreticisi hatalı denemeyi atlar | Red: atlanan denemeler maksimum dağılımını düşürür → eşik **gevşer** (K-007'nin tersi); yeniden kaydırma 43'lük önbellekle "aynı oran dizisi" ilkesini bozar |
| C | Eşik 43/1,04'te bayat kalır | Red: kapının sınıfı bilinmez |

**Neden bu bir manipülasyon değil:** değişiklik null üreticisinde değil stratejide; gerçek
tarihsel koşuda dal tetiklenmediği için h51/h52'nin kayıtlı OOS `sonuc_hash`'i **aynı kaldı**
(§3, hash ile kanıt); değişiklik yalnız gerçek veride hiç oluşmayan bir durumun (sıfır
oynaklık) davranışını "çök" yerine "aday değil" yapıyor; `tests/unit/test_oynaklik_olculebilir.py`
bozuk sembolün geçerli adayların metrik/işlemlerini **bit düzeyinde** değiştirmediğini ölçüyor.
Etkisi null'da: kaydırılmış evrende oynaklığı sıfırlanan sembol o barda aday olmuyor —
gerçek stratejinin canlıda yapacağı şeyin aynısı.

## 3. Regresyon kanıtı (kod değişikliği tarihsel ölçümü değiştirmedi)

Sabitlenmiş depoda, yeni kodla (`209ff2a` öncesi çalışma ağacı, aynı içerik), null'dan **önce**:

| Çekiliş | Strateji | Kayıtlı OOS `sonuc_hash` | Yeni | OOS Sharpe |
| --- | --- | --- | --- | ---: |
| h51 `501049cf9901` | `evren_oynaklik_agirlik` | `94758822a9474b8c` | `94758822a9474b8c` **AYNI** | 0,3635 |
| h52 `3a077f36ea0b` | `evren_turnover_bandi` | `b33ae8a6d4261db9` | `b33ae8a6d4261db9` **AYNI** | 0,2799 |

Araç da aynı kontrolü null'dan önce yapar ve geçmezse durur (ilk koşuda geçmişti; düşen şey
null'un 141. denemesiydi). İkinci koşuda 500/500 deneme her iki çekilişte tanımlı null
prosedürüyle tamamlandı (`satirlar` 500/500; h51'de 349/500 uygun, h52'de 500/500 uygun).

## 4. Null dağılımı (45 çekilişin maksimumu, sızıntı paylı)

| | p50 | p75 | p90 | **p95** | p99 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Uygunluk filtreli (kapı) | 0,597 | 0,751 | 0,936 | **1,004** | 1,198 |
| Ham (filtresiz) | 0,715 | 0,955 | 1,197 | 1,366 | 1,565 |

Düzeltilmiş eşikler: %20 → 0,795 · %10 → 0,936 · **%5 → 1,004 (%90 GA 0,982–1,064)** · %1 → 1,198.
Uygun oran 0,551. Gerçek en iyi çekiliş: `cok_faktor` 0,4585, null p = 0,82 (43'te 0,42).

Çekiliş bazında (h51/h52 null'ları): h51 medyan 0,120 / p95 0,404 / max 0,606; h52 medyan
0,543 / **p95 0,946 / max 1,197** — maksimum dağılımının sağ kuyruğunu h52 (turnover bandı, 47
işlem, n=5) taşıyor.

## 5. Eski eşikle fark

| | K-071 (43 çekiliş, 2026-09-18) | R1(c) (45 çekiliş, 2026-09-20) |
| --- | ---: | ---: |
| %5 sınırı | 0,926 (GA 0,838–0,967) | **1,004** (GA 0,982–1,064) |
| Sabit 1,04'ün gerçek yanlış-pozitif oranı | %2,6 | **%4,2** |
| Sabit | 1,04 | 1,04 (değişmedi) |

İki çekiliş %5 sınırını 0,08 yukarı taşıdı (h52'nin kuyruğu). Ölçülen sınır hâlâ 1,04'ün
**altında**: K-050 asimetrisine göre sabit gevşetilmez; sıkılaştırma gerekmiyor (ölçüm < sabit).
Sabitin tasarım hedefi (%5) ile gerçek FP (%4,2) artık çok yakın — bir sonraki iki çekiliş
sabiti aşabilir.

## 6. İnsan onayı bekleyen (R1(d))

1. `COKLU_TEST_CEKILIS_SAYISI` 43 → **45** (ölçümün fotoğrafı; eşik değil) ve
   `tests/unit/test_coklu_test.py::OLCULEN_CEKILIS` 43 → 45. Bugün bekçi testi yerelde
   **kırmızı** (`test_defter_olculen_cekilis_sayisini_gecmedi`: 45 > 43) — bekçi çalışıyor;
   CI'da (dosya yok) sessiz. Sabit güncellenmeden takım yerelde tam yeşil değil.
2. `COKLU_TEST_ESIGI` **1,04 kalır mı** (K-050: ölçüm 1,004 < 1,04 → gevşetme yok) — karar
   yazılı olmalı (K-071 kalıbı: "sabit indirilmedi").
3. Bekçinin gitignore'daki JSON yerine **defteri** sayması (W6 T2): `COKLU_TEST_DEFTER_SAYISI`
   (=52) sabiti + ledger uzunluğu testi — R1(c)'nin kalan alt maddesi, sayı kararıyla birlikte.
4. `data/evren` deposu 2026-09-14'te **sabit** duruyor (50 sembolün 09-15→09-18 barları
   scratch yedekte, `sq data arsiv-indir <50> ` ile de geri gelir). İleri sarma kararı.

## 7. Değişen dosyalar

`src/scryne_quant/strategy/kurma.py` (`oynaklik_olculebilir`, başlık), `strategy/kutuphane/
evren_esit_agirlik.py`, `strategy/kutuphane/kesitsel.py`, `tests/unit/test_oynaklik_olculebilir.py`
(18 test) — commit `209ff2a`. Bu doküman ve ROADMAP satırı — sonraki commit. Tam takım
1.889 yeşil (rc=0, `209ff2a`), ruff temiz; ölçüm sonrası yerelde 1 kırmızı (§6/1, bilinçli).
