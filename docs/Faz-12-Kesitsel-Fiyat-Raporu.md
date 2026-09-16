---
proje: ScryneQuant
faz: 12
program: kesitsel_fiyat
tarih: 2026-09-16
type: rapor
durum: kapandı — durma kuralı
---
# Faz 12 — `kesitsel_fiyat` programı raporu

**Sonuç:** Program **durma kuralıyla kapandı**. Bütçe 6 çekilişti, 4'ü harcandı. İlk iki
ailenin dört çekilişinin hiçbiri OOS'ta kıyasın Sharpe'ını geçmedi ve 11 kapının tamamını
geçen çekiliş olmadı (en iyisi 4/11). Düşük oynaklık ailesinin iki çekilişi **harcanmadı**.

Program kaydı ve kaynak ölçüsü: `docs/Arastirma-Programlari.jsonl`,
`docs/Faz-12-Program-Taslaklari.md`. Ham sonuçlar: `runs/faz12/<çekiliş>.json`
(`.gitignore`'da; sayılar buradan kopyalandı).

## 1. Kurulum

| | |
| --- | --- |
| Evren | PIT üst 50 (`27b7a16ed0ed`), 429 sembol, 79.420 1h bar (2017-08 … 2026-09) |
| Pencereler | IS bar 0-55.594 · OOS 55.594-79.420 · WF 32 katman (eğitim 8.766 / test 2.190) |
| Sabit | spot, long-only, `hedef_brut` 0,2, eşit ağırlık, seçim `plato` |
| Izgara | her çekiliş 12 nokta: 4 pencere × `azami_enstruman` {5, 10, 20} |
| Kıyas | `evren_esit_agirlik`, aynı OOS, aynı dengeleme sıklığı, yoğunluk 10, `hedef_brut` 0,2 |
| Kod | `504a87d` (39: `f1a19de`), temiz ağaç; `tools/faz12_evren_kos.py` |

## 2. Sonuçlar

| Hipotez | Çekiliş | Seçilen | IS Sharpe | OOS Sharpe | Kıyas OOS | OOS getiri | OOS MaxDD | WF Sharpe | Geçen kapı |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 39 | güç, haftalık | p=336, n=5 | 0,875 | **−0,510** | 0,167 | −%26,6 | %36,8 | 0,451 | 2/11 |
| 40 | güç, aylık | p=168, n=20 | 0,662 | **−0,177** | 0,281 | −%10,4 | %24,7 | 0,331 | 4/11 |
| 41 | ters, haftalık | p=24, n=20 | 0,260 | **−0,922** | 0,167 | −%36,1 | %40,6 | −0,402 | 3/11 |
| 42 | ters, aylık | p=72, n=10 | 0,408 | **−0,967** | 0,281 | −%36,7 | %47,3 | 0,228 | 3/11 |

### 2.1 Kapılar (K-058: 7 + 4)

| Kapı | Sınır | 39 | 40 | 41 | 42 |
| --- | --- | ---: | ---: | ---: | ---: |
| `oos_sharpe` | ≥ 1,02 | −0,510 ✗ | −0,177 ✗ | −0,922 ✗ | −0,967 ✗ |
| `oos_is_orani` | ≥ 0,5 | −0,583 ✗ | −0,267 ✗ | −3,546 ✗ | −2,371 ✗ |
| `wf_katman_basari` | ≥ 0,6 | 0,562 ✗ | 0,516 ✗ | 0,375 ✗ | 0,419 ✗ |
| `parametre_kararliligi` | ≤ 0,35 | 0,109 ✓ | 0,113 ✓ | 0,109 ✓ | 0,113 ✓ |
| `asgari_islem` | ≥ 30 | 435 ✓ | 420 ✓ | 1.756 ✓ | 274 ✓ |
| `max_drawdown` | ≤ 0,25 | 0,368 ✗ | 0,247 ✓ | 0,406 ✗ | 0,473 ✗ |
| `stres_dayanikliligi` | ≤ 0,15 | 0,332 ✗ | 0,058 ✓ | 0,108 ✓ | 0,045 ✓ |
| `pbo` | ≤ 0,0087 | 0,153 ✗ | 0,273 ✗ | 0,042 ✗ | 0,472 ✗ |
| `parametre_perturbasyonu` | ≤ 0,0565 | 0,371 ✗ | 0,397 ✗ | 0,358 ✗ | 0,276 ✗ |
| `rejim_kararliligi` | ≥ 0,685 | −0,691 ✗ | −0,261 ✗ | −1,251 ✗ | −1,383 ✗ |
| `evren_dayanikliligi` | ≥ 0,75 | ölçülemedi | ölçülemedi | ölçülemedi | ölçülemedi |

Evren dayanıklılığının oranı yalnızca pozitif OOS Sharpe'ta tanımlı; dördü de negatif.
Ölçülemeyen kapı geçilmiş sayılmaz (K-019).

## 3. Okuma

1. **Faz 4'ün deseni kesitte tekrar etti.** Göreli güçte IS Sharpe pozitif ve anlamlı
   (0,66-0,88), OOS negatif. PBO (0,15 / 0,27) ve pertürbasyon (0,37 / 0,40) bunun
   seçimden geldiğini söylüyor: ızgaranın IS'teki en iyi bölgesi OOS'ta taşınmıyor.
2. **Ters dönüş hiçbir pencerede işe yaramadı.** IS Sharpe zaten düşük (0,26 / 0,41),
   haftalık hâlin walk-forward'ı bile negatif. Kısa vadeli ters dönüş bu evrende ve bu
   maliyetle bir edge değil.
3. **Maliyet duvarı sebep değil.** Aylık dengeleme devri 31 → 9-10 kata, stres bozulmasını
   0,33 → 0,06'ya düşürdü; OOS Sharpe yine negatif. K-045'in tek sembollü bulgusuyla aynı.
4. **Kıyas pozitifken seçim negatif.** Aynı OOS'ta evrenin likit ilk 10'unu tutmak +0,17 /
   +0,28 verdi. Long-only'nin beta taşıması (taslak §3) sonucu açıklamıyor: seçim, aynı
   betayı taşıyan kıyasın **altında** kaldı.
5. **Kaynak farklıydı, değerli değildi.** Taslak §1 ölçüsü kesitin BTC serisinden farklı bilgi
   taşıdığını gösterdi; bu program o bilginin fiyat sıralamasıyla paraya çevrilemediğini
   gösterdi. Önden yazılan uyarı buydu.

## 4. Açık kalemler

1. **`bayat_degerleme` sıfır değil.** OOS'ta 13.101 (39), 18.837 (40), 58.254 (41), 23.532
   (42) pozisyon-bar: seçilen sembol delist edilmiş, pozisyon son bilinen fiyattan
   değerleniyor (`backtest/coklu_motor.py`, Faz 10'un 2023 sonrası penceresinde 0'dı). Ters dönüş
   ailesi geride kalanı seçtiği için en yüksek. **Etkinin yönü ölçülmedi:** son fiyat
   delist öncesi çöküşü içerebilir de, sermayeyi dondurup volatiliteyi düşürebilir de.
   Kapanış kararını değiştirmiyor (PBO ve pertürbasyon kapıları bundan bağımsız, OOS
   Sharpe'lar kıyasın 0,5-1,2 altında) ama bir sonraki evren programı başlamadan önce
   ölçülmeli.

   **Ölçüldü → K-059.** 9 takılı pozisyon (4'ü token göçü: MATIC, RNDR, EOS, BNX); sonda
   özkaynağın %1,0-8,3'ü. Sıfır değer alt sınırında OOS Sharpe −0,630 / −0,198 / −1,047 /
   −1,082; kıyasta takılı pozisyon yok. Kapanış sağlam. Sonraki programlar 48 bar sonra
   sıfır değerleme politikasıyla koşar.
2. **`evren_dayanikliligi` eşiği yeniden ölçülemedi** (K-058 geri dönüş 2): pozitif Sharpe'lı
   gerçek aday çıkmadı. İştah olarak kalıyor.
3. **Çok enstrümanlı null** (K-058 geri dönüş 1) ölçülmedi; hiçbir çekiliş kapı sınırına
   yaklaşmadığı için bu programın sonucunu etkilemiyor.
4. **`oos_sharpe` eşiği** (K-044): defter 38 → 42. Faz 12'nin bitti kriteri üç program
   bittikten sonra `sq lab coklu-test` ile yeniden ölçüm istiyor.

## 5. Koşu olayları (sonuç üretilmeden duranlar)

| Olay | Sebep | Düzeltme |
| --- | --- | --- |
| Ön kayıt dışı bakış | Süre ölçümü aday stratejiyle yapıldı | Taslak §6, hipotez 39 gerekçesi |
| 39 ilk koşu | 205 üye bar barı olmayan saatte (2018-06-26, BCCUSDT delisti) | `f1a19de`, taslak §7 |
| 40 iki kez, 42 bir kez öldürüldü | Bellek: süreç başına 6,2 GB × 5 süreç; ayrıca makinede başka bir servis ≈11,7 GB commit | `f967203`, `504a87d` (4,5 GB/süreç); 42 seri koşuldu |

Üçünde de sonuç dosyası yazılmadı. `504a87d` sonrası hipotez 39'un OOS `sonuc_hash`'i ve veri
kimliği bit düzeyinde yeniden üretildi.
