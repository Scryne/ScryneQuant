---
proje: ScryneQuant
faz: 12
program: turev_evren
tarih: 2026-09-16
type: rapor
durum: kapandı — bütçe doldu
---
# Faz 12 — `turev_evren` programı raporu

**Sonuç:** Program **bütçesi dolarak kapandı**: 4 çekilişin 4'ü harcandı. 11 kapının
tamamını geçen çekiliş yok, en iyisi 6/11. İki çekiliş OOS'ta filtresiz kıyası geçti.
Ama kıyasın kendisi aynı IS/WF bandında duruyor, dolayısıyla funding veya basis
dışlamasının evren kıyasına ölçülebilir bir katkısı yok.

Program kaydı `docs/Arastirma-Programlari.jsonl`, kaynak ölçüsü
`docs/arsiv/Faz-12-Program-Taslaklari.md` §1.2. Ham sonuçlar `runs/faz12/<çekiliş>.json`,
kıyas bağlamı `runs/faz12/turev-kiyas-baglam.json` (`.gitignore`'da; sayılar buradan
kopyalandı).

## 1. Kurulum

| | |
| --- | --- |
| Evren | PIT üst 50 (`27b7a16ed0ed`), 429 sembol, 79.420 1h bar; pencereler kesitsel programla aynı |
| Tasarım | `evren_esit_agirlik` kıyası + tek bir dışlama adımı; dışlama oranı 0 iken kıyasla bit düzeyinde aynı |
| Sabit | spot, long-only, `hedef_brut` 0,2, eşit ağırlık, haftalık dengeleme, seçim `plato` |
| Değerleme | K-059: 48 bar barı gelmeyen pozisyon sıfır (bu programda OOS'ta tetiklenmedi, `bayat_degerleme` 0) |
| Funding | arşiv (`data/turev/funding/`), `calc_time <= open_time`, 8 saatlik eşdeğer, 24 saat bayatlık; 380/429 sembol, OOS üye-bar kapsamı %90,6 |
| Basis | premium index 1h kapanışı (`data/turev/premium/`), tam zaman eşleşmesi; 379/380 perp, OOS kapsamı %89,6 |
| Kod | 43-44 `fcf9bbc`, 45-46 `ab3c5de`, temiz ağaç; seri koşu (`--isci 1`), 32-38 dk/çekiliş |

## 2. Sonuçlar

| Hipotez | Çekiliş (skor) | Seçilen | IS Sharpe | OOS Sharpe | Kıyas OOS | OOS getiri | WF Sharpe | Geçen kapı |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 43 | son funding oranı | q=0,3, n=5 | 0,438 | 0,184 | 0,333 (n=5) | +%4,5 | 0,811 | 5/11 |
| 44 | W saatte ödenen funding | W=720, q=0,1 | 0,353 | **0,221** | 0,167 | +%5,9 | 0,804 | 5/11 |
| 45 | W saatlik ortalama basis | W=720, q=0,2 | 0,369 | 0,129 | 0,167 | +%2,3 | 0,861 | 5/11 |
| 46 | funding + basis sıra ortalaması | W=720, q=0,2 | 0,390 | **0,256** | 0,167 | +%7,4 | 0,839 | 6/11 |

### 2.1 Kıyasın kendisi (K-030, çekiliş değil)

| Kıyas | IS Sharpe | OOS Sharpe | OOS getiri | WF Sharpe | WF pozitif katman |
| --- | ---: | ---: | ---: | ---: | ---: |
| n=5, haftalık | 0,350 | 0,333 | +%10,3 | 0,952 | 19/32 |
| n=10, haftalık | 0,339 | 0,167 | +%3,8 | 0,848 | 19/32 |

### 2.2 Kapılar

| Kapı | Sınır | 43 | 44 | 45 | 46 |
| --- | --- | ---: | ---: | ---: | ---: |
| `oos_sharpe` | ≥ 1,02 | 0,184 ✗ | 0,221 ✗ | 0,129 ✗ | 0,256 ✗ |
| `oos_is_orani` | ≥ 0,5 | 0,421 ✗ | 0,626 ✓ | 0,350 ✗ | 0,657 ✓ |
| `wf_katman_basari` | ≥ 0,6 | 0,621 ✓ | 0,586 ✗ | 0,621 ✓ | 0,621 ✓ |
| `parametre_kararliligi` | ≤ 0,35 | 0,121 ✓ | 0,121 ✓ | 0,121 ✓ | 0,121 ✓ |
| `asgari_islem` | ≥ 30 | 141 ✓ | 121 ✓ | 162 ✓ | 158 ✓ |
| `max_drawdown` | ≤ 0,25 | 0,231 ✓ | 0,198 ✓ | 0,221 ✓ | 0,194 ✓ |
| `stres_dayanikliligi` | ≤ 0,15 | 0,118 ✓ | 0,048 ✓ | 0,053 ✓ | 0,056 ✓ |
| `pbo` | ≤ 0,0087 | 0,054 ✗ | 0,571 ✗ | 0,441 ✗ | 0,413 ✗ |
| `parametre_perturbasyonu` | ≤ 0,0565 | 0,656 ✗ | 0,471 ✗ | 0,205 ✗ | 0,627 ✗ |
| `rejim_kararliligi` | ≥ 0,685 | 0,009 ✗ | 0,110 ✗ | −0,127 ✗ | 0,085 ✗ |
| `evren_dayanikliligi` | ≥ 0,75 | 0,305 ✗ | 0,502 ✗ | −0,437 ✗ | 0,174 ✗ |

## 3. Okuma

1. **Filtre kıyasa bir şey katmıyor.** IS'te çekilişler 0,35-0,44, kıyas 0,34-0,35; WF'de
   çekilişler 0,80-0,86, kıyas 0,85-0,95. OOS'ta ikisi kıyasın 0,05-0,09 üstünde (44, 46),
   ikisi altında (43, 45). Dört çekiliş, her biri 12 noktalık ızgarada seçilmiş hâliyle,
   kıyasın gürültü bandından ayrışmıyor.
2. **Kıyası geçen iki çekiliş seçimden geliyor.** PBO 0,57 ve 0,41: CSCV'de IS'in en iyisi
   OOS'ta medyanın altında kalma olasılığı null medyanının (0,237, K-058) iki katına
   yakın. Pertürbasyon düşüşü 0,47 ve 0,63: seçilen noktanın komşuları çok daha kötü.
3. **Sonuç birkaç isme bağlı.** Evren dayanıklılığı −0,44…0,50: en çok katkı veren tek
   sembol çıkarıldığında Sharpe yarıya iniyor ya da (45'te) işaret değiştiriyor.
4. **Rejim kararlılığı dördünde de sıfıra yakın ya da negatif.** Kıyasın beta taşıması
   (long-only) kötü rejimi olduğu gibi aktarıyor; dışlama onu azaltmıyor.
5. **Kaynak ölçüsüyle birlikte:** taslak §1.2 funding'in kesitte BTC'den bağımsız bir bilgi
   taşıdığını ve fiyat momentumunun yeniden adlandırılmış hâli olmadığını gösterdi. Bu
   program o bilginin **dışlama filtresi** olarak kıyasa değer katmadığını gösterdi. K-042'nin
   tek sembollü sonucu evren kesitinde tekrar etti.

## 4. Kayıt notları

- **Durma kuralı tetiklenmedi, bu yüzden basis çekilişleri harcandı.** Kural "(1) ve (2)
  kıyası geçmezse (3)-(4) harcanmaz" diyordu; 44 geçti. Sonuca bakıp durmak K-018'in
  yasakladığı elle karar olurdu. Maliyeti: defter 2 çekiliş daha büyüdü.
- **Basis çekilişleri 43-44 görüldükten sonra kaydedildi.** Izgaraları
  `turev_funding_birikim`in birebir aynası; sonuca bakılarak seçilmiş parametre yok
  (`research/izgaralar.py`, testle). Üç basis/birleşik çekilişin de W=720 seçmesi bu
  aynalamanın sonucu değil, IS taramasının sonucu.
- **İndiricide iki yanlış eşik** (`tools/faz12_premium_indir.py`): |premium| > 0,5 ve ≥ 1
  "veri hatası" sayılmıştı; ikisi de gerçek piyasa içeriğiydi (2021-05-19 çöküşü; LEVER'in
  delist sonrası 120 saat donuk endeksi). Değer filtresi kaldırıldı, yalnızca sonlu olmayan
  değer reddediliyor.

## 5. Açık kalemler

1. **`oos_sharpe` eşiği** (K-044): defter 38 → 46 (kesitsel 4 + türev 4). Faz 12'nin bitti
   kriteri, makro programından sonra `sq lab coklu-test` ile yeniden ölçüm istiyor.
2. **Çok enstrümanlı null** (K-058 geri dönüş 1): hâlâ ölçülmedi. Kapı sınırına en yakın çekiliş
   bile `pbo`da sınırın 6 katında (43: 0,054); bu programın sonucunu etkilemiyor.
3. **`evren_dayanikliligi` eşiği** (K-058 geri dönüş 2): ilk pozitif Sharpe'lı gerçek adaylar
   0,17-0,50 verdi, hepsi 0,75'in altında. Eşik iştah olarak kalıyor. Yeniden ölçmek için
   diğer kapıları geçen bir aday gerekiyor.
