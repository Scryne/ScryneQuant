---
proje: ScryneQuant
tarih: 2026-09-23
karar: K-119
tur: ölçüm + kapı yeniden tanımı (iki yönlü doğrulama; çekiliş değil, defter satırı değil)
type: rapor
---
# Promotion kapılarının yeniden tasarımı — iki yönlü doğrulama

**Sonuç.** 12 kapının 4'ünün tanımı değişti (`stres_dayanikliligi`, `pbo`,
`parametre_perturbasyonu`, walk-forward asgari işlemi). Hiçbir kapı kaldırılmadı (değişmez kural
8). Tek sembollü araştırma artık 9 yıllık arşiv verisini kullanabiliyor. Yeni sistem üç koşulu
birlikte sağlıyor:

- **Yanlış pozitif yok:** üstünlüksüz kahin 0/60, trendsiz sentetik 0/n, gerçek defter 0/38.
- **Güç üstünlükle artıyor:** tek sembollü kahinde %58 → %60 → %65 isabette geçiş kabaca
  %5-55 → %35-75 → %85-100; evren sentetiğinde güçlü trendde 12 kapının tamamı geçiliyor.
- **Önce ölçülemeyen bölge açıldı:** haftalık ufuklu kahin 0/20'den 17/20'ye çıktı.

Eski sistemde gerçek üstünlüğün 12 kapıyı geçme olasılığı fiilen sıfırdı (K-117, K-118).

## Neden

K-117 ve K-118 şunu ölçtü:

- Kapıların gücü hiç ölçülmemişti. Eşikler null'ın %5 kuyruğundan seçilmişti (tek yönlü
  kalibrasyon).
- Bu yüzden dört kapı gerçek üstünlüğü ya yokluğundan ayırt etmiyordu ya da yapısal olarak
  eliyordu.
- K-058'de yalnızca null kalibrasyonu (yanlış pozitif tarafı) ölçülmüştü; güç (yanlış negatif
  tarafı) hiç ölçülmemişti.

## Yöntem

Her aday tanım **cevabı bilinen** üç kaynakta ölçüldü:

| Kaynak | Araç | Üstünlük | Ne sınar |
| --- | --- | --- | --- |
| Kahin (tek sembol, gerçek BTC 2017-08→) | `tools/pozitif_kontrol.py --depo data/evren` | p ∈ {0,50…0,65} × ufuk {24, 72, 168} × 20 tohum | K-019 + K-113, gerçek piyasa |
| Tek sembol sentetik (gerçek kütüphane + ızgaralar) | `tools/pozitif_kontrol_tam.py` | rejim trendi m ∈ {0, 3, 5} × 6 tohum | 12 kapı, ızgaraya bağlı kapılar |
| Evren sentetik (`ZamanSerisiTrend`, 10 sembol) | `tools/pozitif_kontrol_evren.py` | m ∈ {0, 3, 5} × 6 tohum | 12 kapı, promotion'a giden gerçek yol |
| Gerçek defter (38 tek sembollü çekiliş) | `sq lab kapilar-v2` | null'dan ayırt edilemez (K-110) | gerçek veride yanlış pozitif |

## Değişen tanımlar

| Kapı | Eski | Yeni | Gerekçe |
| --- | --- | --- | --- |
| `stres_dayanikliligi` | tüm dönem getiri farkı (yüzde puan) ≤ 0,15; **varsayılan** parametreyle | OOS'ta en kötü maliyet senaryosu Sharpe / temel OOS Sharpe ≥ 0,5; **seçilen** parametreyle | eski ölçü işlem sayısı, süre ve stratejinin kendi getirisiyle büyüyordu: %65 kahin 0/20 |
| `pbo` | sıralama PBO'su ≤ 0,0087 | CSCV zarar olasılığı ≤ 0,05 | sıralama PBO'su gerçek üstünlükte de 0,01-0,82 |
| `parametre_perturbasyonu` | (seçilen − komşu medyanı) / ızgara aralığı ≤ 0,0565 | komşu medyanı / seçilen ≥ 0,80 | eski ölçü sağlam platoyu cezalandırıyordu; m=5 ile m=0 arasında fark yoktu |
| walk-forward asgari işlem | sabit 20 | yılda 6 tur × pencere yılı (1 yıllık eğitimde 6) | haftalık strateji "geçerli aday yok"a düşüyordu |

Değişmeyenler: `oos_sharpe` 1,04 (çoklu test), `oos_suresi`, `oos_is_orani`, `wf_katman_basari`,
`parametre_kararliligi`, `asgari_islem` 30, `max_drawdown`, `rejim_kararliligi` 0,685,
`evren_dayanikliligi` 0,75. Rejim ve evren kapıları evren yolunda gücü **olan** kapılar: güçlü
trendde 6/6 ve 6/6, trendsizde rejim 0/6.

## Ölçümler

### Evren sentetik (promotion'a giden yol)

| Ölçü | m ≥ 3 (12) | m = 0 (6) | Eşik |
| --- | --- | --- | --- |
| `pbo_zarar_olasiligi` | 0,000–0,007 | 0,002–0,458, medyan 0,143 | ≤ 0,05 |
| `perturbasyon_koruma` | 0,855–1,021 | 0,266–0,856, medyan 0,650 | ≥ 0,80 |
| eski `pbo` | 0,010–0,822 | 0,098–0,890 | ≤ 0,0087 |
| eski `perturbasyon_dusus` | −0,051–0,682 | 0,283–0,643 | ≤ 0,0565 |

12 kapının tamamını geçen (yeni tanımlarla): m = 5 → 5/6, m = 3 → 2/6, m = 0 → 0/6.

### Kahin (gerçek BTC, 9 yıl, K-019 + K-113 yeni kurallarla; 20 tohumda geçen)

| p | 24 saat | 72 saat | 168 saat |
| --- | ---: | ---: | ---: |
| 0,50 | 0 | 0 | 0 |
| 0,54 | 0 | 1 | 2 |
| 0,56 | 0 | 3 | 5 |
| 0,58 | 1 | 11 | 7 |
| 0,60 | 7 | 15 | 10 |
| 0,65 | 19 | 20 | 17 |

Aynı veri eski kurallarla: her hücre 0/20 (stres her koşulda, haftalıkta walk-forward). Günlük
ufukta yeni stres kapısının bağlaması bilinçli: günde birkaç tur yapan strateji maliyet iki
katına çıkınca Sharpe'ının yarısından fazlasını gerçekten kaybediyor.

### Gerçek defter (38 tek sembollü çekiliş)

`pbo_zarar_olasiligi` ≤ 0,05: 2/31 · `perturbasyon_koruma` ≥ 0,80: 8/30 · ikisi birden: 1
(`funding_ters` 1h, OOS Sharpe −0,27 → `oos_sharpe`'ta kalır). 12 kapıyı geçen: **0**. Yeni
tanımlar gerçek veride gevşeklik açmıyor; yanlış pozitif kontrolünü yine çoklu testle düzeltilmiş
`oos_sharpe` yapıyor, bu iki kapı sağlamlık teşhisi olarak ek eleme sağlıyor.

### Tek sembol sentetik

Aşağıda, koşu bitince.

## Veri

`data/evren/BTCUSDT/1h` 2017-08-17'den başlıyor (79.530 bar, 28 `gap` + 4 `suspect` işaretli);
tek sembollü araştırma `data/market` (2021-06→, 45.828 bar) kullanıyordu. 9 yıllık seride OOS
%30 = 2,72 yıl (önce 1,57): Sharpe'ın standart hatası ≈ 0,8'den ≈ 0,6'ya iniyor. Kahin
tablosunda "stres hariç" geçiş %60 günlükte 10/20'den 18/20'ye çıktı; bu yalnız veri uzunluğunun
etkisi.

## Açık

- `asgari_islem` 30 (OOS) aylık stratejileri hâlâ dışarıda bırakıyor (2,72 yılda ≈ 16 tur).
  Bilinçli: 30'un altındaki OOS'ta null Sharpe dağılımı çok geniş (K-044 notu), `oos_sharpe`
  1,04 o çekilişler için kalibre değil.
- Çoklu test eşiği (1,04) 45.828 barlık OOS'ta kalibre edildi. 9 yıllık seride yeni null ölçümü
  gerekir; uzun OOS'ta null daha dar olacağı için 1,04 **tutucu** yönde kalır.
