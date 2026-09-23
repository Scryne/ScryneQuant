---
proje: ScryneQuant
faz: 12
program: makro_rejim
tarih: 2026-09-17
type: rapor
durum: kapandı — 2/3, rejim motoru harcanmadı
---
# Faz 12 — `makro_rejim` programı raporu

**Sonuç:** Program 3 çekilişlik bütçenin 2'siyle kapandı. İki makro stres engelinin hiçbiri
kapıları geçmedi; ikisi de 4/11. NFCI engeli OOS'ta kıyasın üstünde çıktı, VIX engeli
altında. Walk-forward'da ikisi de kıyasın gerisinde. Rejim motoru çekilişi **harcanmadı**;
gerekçe §4'te.

Program kaydı `docs/Arastirma-Programlari.jsonl`, karar K-060. Ham sonuçlar
`runs/faz12/makro_vix.json`, `makro_nfci.json`.

## 1. Kurulum

| | |
| --- | --- |
| İskelet | `evren_esit_agirlik` kıyası (n=10, haftalık, `hedef_brut` 0,2) + stres engeli |
| Engel (K-060) | Stres rejiminde yeni isim ve büyütme silinir; çıkış ve azaltma serbest. Makro bilgisi yoksa kıyasla bit düzeyinde aynı |
| Veri | ALFRED vintage'ları (`data/makro/`), günlük PIT. `d` gününün değeri `d+1` 00:00 barından itibaren görünür |
| Izgara | pencere {30, 90, 180, 365} gün × eşik {0,7, 0,8, 0,9} |
| Stres payı | eşik 0,8'de zamanın %17-32'si |
| Değerleme | K-059 (48 bar) |
| Kod | 47 `244a584` (paralel oturumun K-061 commit'i koşu sürerken geldi; bu koşunun kodunu değiştirmedi), 48 `28509a6`; temiz ağaç, seri koşu |

## 2. Sonuçlar

| Hipotez | Seri | Seçilen | IS Sharpe | OOS Sharpe | Kıyas OOS | OOS getiri | OOS MaxDD | WF Sharpe | Geçen kapı |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 47 | VIX | 30 g, eşik 0,7 | 0,486 | 0,165 | 0,167 | +%3,6 | %18,1 | 0,669 | 4/11 |
| 48 | NFCI | 365 g, eşik 0,7 | 0,578 | **0,216** | 0,167 | +%5,6 | %19,2 | 0,690 | 4/11 |
| — | kıyas (n=10) | — | 0,339 | 0,167 | — | +%3,8 | %20,0 | 0,848 | — |

### 2.1 Kapılar

| Kapı | Sınır | 47 VIX | 48 NFCI |
| --- | --- | ---: | ---: |
| `oos_sharpe` | ≥ 1,02 | 0,165 ✗ | 0,216 ✗ |
| `oos_is_orani` | ≥ 0,5 | 0,339 ✗ | 0,375 ✗ |
| `wf_katman_basari` | ≥ 0,6 | 0,536 ✗ | 0,519 ✗ |
| `parametre_kararliligi` | ≤ 0,35 | 0,125 ✓ | 0,130 ✓ |
| `asgari_islem` | ≥ 30 | 87 ✓ | 96 ✓ |
| `max_drawdown` | ≤ 0,25 | 0,181 ✓ | 0,192 ✓ |
| `stres_dayanikliligi` | ≤ 0,15 | 0,038 ✓ | 0,038 ✓ |
| `pbo` | ≤ 0,0087 | 0,160 ✗ | 0,151 ✗ |
| `parametre_perturbasyonu` | ≤ 0,0565 | 0,602 ✗ | 0,375 ✗ |
| `rejim_kararliligi` | ≥ 0,685 | −0,106 ✗ | 0,080 ✗ |
| `evren_dayanikliligi` | ≥ 0,75 | 0,413 ✗ | 0,586 ✗ |

## 3. Okuma

1. **Engel düşüşü biraz azaltıyor, getiriyi de aynı ölçüde kesiyor.** OOS max drawdown
   %18-19, kıyasta %20. Buna karşılık walk-forward Sharpe 0,67-0,69, kıyasta 0,85: uzun
   dönemde engel, kaçırdığı toparlanmalarla ödüyor.
2. **IS'te iyi, OOS'ta kıyas bandında.** IS Sharpe kıyasın 0,15-0,24 üstünde; OOS'ta farkı
   −0,002 / +0,05. Pertürbasyon (0,38-0,60) ve PBO (0,15-0,16) seçimin tepe noktası
   olduğunu söylüyor.
3. **Rejim kararlılığı sıfıra yakın.** Makro engel, amaçladığı şeyi (kötü rejimi yumuşatmak)
   OOS'ta göstermiyor.
4. **Üç Faz 12 programının ortak sonucu:** evren kıyasının üstüne konan seçim (kesitsel),
   dışlama (türev) ve engel (makro) katmanlarının hiçbiri, kıyasın kendi gürültü bandından
   ölçülebilir biçimde ayrışmıyor.

## 4. Rejim motoru çekilişi neden harcanmadı

Durma kuralı "VIX ve NFCI kıyası geçmezse motor harcanmaz" diyordu; NFCI geçtiği için kural
**tetiklenmedi**. `turev_evren`de aynı durumda kalan çekilişler harcanmıştı. Burada
harcanmadı, çünkü:

- **Bütçe bir tavandır (K-051/2), zorunluluk değil.** Aramayı genişletmek yanlış pozitif
  üretebilir; daraltmak üretemez. "Sonuca bakıp karar verme" yasağı (K-018) izin veren
  yöndeki kararlar için; araştırmayı kısmak yanlış pozitif oranını yalnızca düşürür.
- **İki basit filtre kıyasın gürültü bandında.** Motor aynı bilgiyi (makro seriler) daha çok
  parametreyle işleyecekti: durum sayısı, girdi seti, eğitim penceresi. Programın en
  parametreli çekilişi.
- **Maliyet:** filtrelenmiş olasılık, katman başına eğitim ve yumuşatılmış olasılık yasağının
  testi yaklaşık bir günlük iş. Scryne'ın onayladığı plan (K-060) Faz 12'den sonra Faz 14'ü,
  yani sistemin 7/24 çalışmasını öne alıyor.

Motor Faz 16'da ayrı bir program kaydıyla açılabilir.

## 5. Açık kalemler

1. **`oos_sharpe` eşiği:** defter 48. Evren çekilişlerini de sayan null
   (`research/coklu_test_evren.py`, `tools/faz12_coklu_test.py`) Faz 12'nin kapanışında
   koşturulur.
2. Faz 11'in `evren_dayanikliligi` eşiği hâlâ iştah olarak duruyor. Pozitif Sharpe'lı
   adayların değerleri 0,41 ve 0,59 çıktı, ikisi de kapı sınırının (0,75) altında.
