---
proje: ScryneQuant
faz: 16
program: konumlanma_evren
tarih: 2026-09-18
type: rapor
durum: kapandı — 2/4, durma kuralı işledi
---
# Faz 16 — `konumlanma_evren` programı raporu

**Sonuç:** Program 4 çekilişlik bütçenin 2'siyle kapandı. Önceden yazılmış durma kuralı
işledi: ilk iki çekiliş OOS'ta filtresiz evren kıyasının Sharpe'ını geçemedi, 3. ve 4.
çekiliş (`evren_buyuk_hesap`, `evren_oi_taker`) **harcanmadı**. Hiçbir çekiliş 11 kapıyı
geçmedi.

Program kaydı ve kapanışı `docs/Arastirma-Programlari.jsonl`; hipotezler 49-50
`docs/Hipotez-Defteri.jsonl`; taslak `docs/Faz-16-Konumlanma-Program-Taslagi.md`. Ham
sonuçlar `runs/faz12/konumlanma_oi.json`, `runs/faz12/konumlanma_taker.json`.

## 1. Kurulum

| | |
| --- | --- |
| İskelet | `evren_esit_agirlik` kıyası (n=10, haftalık dengeleme, `hedef_brut` 0,2) + tek dışlama katmanı |
| Evren | PIT tablo `27b7a16ed0ed` (kural kimliği), 429 sembol, 79.420 bar, 3.231.546 üye-bar |
| Ek veri | `data/turev/metrics` — `data.binance.vision futures/um/daily/metrics`, 5 dk ızgara; günlük değer = 23:55 gözlemi, `available_time = create_time + 5 dk` (K-052/15) |
| Izgara | `pencere` ∈ {24, 72, 168, 720} saat × `dislama_orani` ∈ {0,1, 0,2, 0,3} — 12 nokta, iki çekilişte birebir aynı |
| Seçim | plato merkezi (`secim: plato`), ölçüt Sharpe |
| Bölme | IS 0-55.594 bar, OOS 55.594-79.420 bar; WF 28 katman (8.766 eğitim / 2.190 test) |
| Değerleme | K-059 (48 bar sıfıra yaz) |
| Kod | `c9c7f8c`, çalışma ağacı **kirli** (aşağıda §5/1) |
| Süre | 867 s + 898 s |

Kıyasın OOS'taki kendi sayıları (aynı pencere, aynı maliyet): Sharpe **0,1669**, getiri
+%3,75, max drawdown %20,04, 108 işlem, `sonuc_hash` `be28cd90…`.

## 2. Sonuçlar

| Hipotez | Çekiliş | Ölçülen | Seçilen | IS Sharpe | OOS Sharpe | Kıyas OOS | OOS getiri | OOS MaxDD | OOS işlem | WF Sharpe | Geçen kapı |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 49 | `evren_oi_birikim` | Açık pozisyon artışı (sözleşme adedi, log) | 720 s, %10 | 0,302 | **0,087** | 0,167 | +%0,60 | %19,2 | 228 | 0,744 | 5/11 |
| 50 | `evren_taker_baski` | Taker long/short hacim oranı ortalaması | 168 s, %20 | 0,317 | **0,056** | 0,167 | −%0,77 | %22,7 | 175 | 0,688 | 4/11 |
| — | kıyas (n=10) | — | — | — | 0,167 | — | +%3,75 | %20,0 | 108 | — | — |

### 2.1 Kapılar (`research/kapilar_v2.py`, `butun_kapilar`)

| Kapı | Sınır | 49 `oi_birikim` | 50 `taker_baski` |
| --- | --- | ---: | ---: |
| `oos_sharpe` | ≥ 1,04 | 0,087 ✗ | 0,056 ✗ |
| `oos_is_orani` | ≥ 0,5 | 0,287 ✗ | 0,175 ✗ |
| `wf_katman_basari` | ≥ 0,6 | 0,571 ✗ | 0,571 ✗ |
| `parametre_kararliligi` | ≤ 0,35 | 0,125 ✓ | 0,125 ✓ |
| `asgari_islem` | ≥ 30 | 228 ✓ | 175 ✓ |
| `max_drawdown` | ≤ 0,25 | 0,192 ✓ | 0,227 ✓ |
| `stres_dayanikliligi` | ≤ 0,15 | 0,054 ✓ | 0,050 ✓ |
| `pbo` | ≤ 0,0087 | 0,393 ✗ | 0,392 ✗ |
| `parametre_perturbasyonu` | ≤ 0,0565 | 0,027 ✓ | 0,694 ✗ |
| `rejim_kararliligi` | ≥ 0,685 | −0,168 ✗ | −0,108 ✗ |
| `evren_dayanikliligi` | ≥ 0,75 | −0,183 ✗ | −0,205 ✗ |

**Defter kaydındaki sayı düzeltilir.** `docs/Arastirma-Programlari.jsonl`'daki kapanış
satırı "ikisinde de 4 kapı geçti" diyor; ölçüm 49 için **5/11**, 50 için 4/11. Defter
append-only olduğu için satır düzeltilmiyor, düzeltme burada kayıtlı. Fark sonucu
değiştirmiyor (ikisi de kaldı), ama "neredeyse doğru sayı" bu projede kayda geçmez.

## 3. Okuma

1. **Bilgi farklı, sıralama gücü yok.** Program açılışının K-045 istisnasını karşılayan
   kaynak ölçümü (`runs/faz16/kaynak-olcumu-konumlanma.json`) bu serilerin fiyattan ve
   funding'den bağımsız olduğunu gösteriyordu: açık pozisyon değişiminin günlük getiriyle
   açıklanamayan payı medyan 0,892, funding ile 0,972, taker akışı 0,986. Aynı ölçüm
   **kesit sırası** tarafında zaten sıfıra yakın bir şey söylüyordu: açık pozisyon değişimi
   ↔ 7 günlük getiri sırası −0,012, taker ↔ 7 günlük getiri −0,003. Sonuç o ön ölçümle
   tutarlı çıktı. **Bağımsızlık bir ön şarttır, bir vaat değil.**
2. **Katman kıyastan ayrışmıyor.** İki çekilişin de IS Sharpe'ı kıyasın bandında
   (0,30-0,32), OOS'ta kıyasın **altında**, WF'de kıyasın (0,85) altında. Dışlama işlem
   sayısını 108'den 175-228'e çıkarıyor, yani maliyeti artırıyor ve karşılığında getiri
   getirmiyor: 49'un OOS getirisi +%0,60 (kıyas +%3,75), 50'ninki negatif.
3. **Faz 12 ile aynı desen.** `turev_evren` (4 çekiliş) ve `makro_rejim` (2 çekiliş) de
   aynı iskeleti kullandı ve aynı yere düştü. Sekiz çekilişte de şekil aynı: kıyasın üstüne
   konan tek dışlama katmanı, kıyasın gürültü bandından çıkmıyor. Bu artık tek tek
   çekilişlerin sonucu değil, **ailenin** sonucu — §4.
4. **`parametre_perturbasyonu` 50'de 0,694.** Izgara komşusuna geçince performansın %69'u
   gidiyor; seçilen nokta bir plato değil, bir tepe. 49'da aynı ölçü 0,027. İki çekiliş
   aynı ızgarada, aynı iskelette, aynı seçim yöntemiyle koştu — fark ölçülen seride.
5. **Evren dayanıklılığı ikisinde de negatif** (−0,18 / −0,20): evren tanımı değişince
   sonucun işareti dönüyor. Bu, K-054'ün tam olarak yakalamak için konduğu şey.

## 4. Karar: kıyas-üstü dışlama katmanı ailesi kapandı

Bu rapor yeni bir çekiliş önermiyor. Öneri, **aileyi kapatmak**: aynı iskelete (evren eşit
ağırlık kıyası + tek dışlama) yeni bir seri bağlamak, K-045'in kapattığı tek sembollü yönlü
aramanın çoklu enstrüman sürümüdür — 8 çekiliş, 0 geçiş, her seferinde aynı gerekçeyle
("bu sefer bilgi farklı"). Bilgi gerçekten her seferinde farklıydı; sonuç değişmedi.

Bir sonraki programın **iskeleti** farklı olmalı, kaynağı değil: kıyasın seçimini süzmek
yerine kıyasın kendisinin göremediği bir olayı ölçen bir yapı. Yürürlükteki aday, ikinci
hatta zaten çalışan duyuru/olay yolu (K-067/3): evren kuralının aylık ızgarasının arasında
kalan erişim değişiklikleri (listeleme, marjin/vadeli ekleme, delist). Bu ailenin kapanışı
K-068 olarak deftere yazıldı.

## 5. Beklenmeyen bulgular

1. **İki koşu da kirli ağaçta yapıldı** (`git.dirty: true`, `c9c7f8c` + çalışma ağacı). Her
   iki sonuç kaydı da `mutlak_engeller: ["dirty"]` taşıyor. Promotion açısından sonucu
   değiştirmiyor (ikisi de kapılarda zaten kaldı) ama kirli ağaçta koşan bir çekilişin
   **geçseydi** promotion'a giremeyeceğini hatırlatıyor: koşu öncesi commit, tercih değil
   ön koşul. Bu koşulardaki kirlilik `tools/faz12_coklu_test.py`'nin konumlanma desteği ve
   `strateji_izgarasi` düzeltmesiydi — ikisi de koşunun gerektirdiği, koşuyu bozmayan
   değişiklikler; yine de sırası yanlıştı.
2. **`sq lab tekrar-kontrol` evren stratejilerinde kırıktı.** K-061'in dedektörü ızgarayı
   `izgaralar.izgara()` ile arıyordu; o fonksiyon yalnızca tek sembollü defteri biliyor,
   evren çekilişlerinin ızgarası çekiliş adına bağlı. Hipotez 49 kaydedilmeden önce
   `IzgaraYok` veriyordu. `strateji_izgarasi()` eklendi: önce tek sembollü defter, sonra
   evren/türev/makro/konumlanma çekiliş defterleri. Kontrol sonra koştu (jev-1.13.0, 48
   kayıtla karşılaştırma: uyarı 0, incele 0).
3. **Kapı eşiği bu program için bayat değildi.** Program açılışında `oos_sharpe` eşiği 41
   ölçülebilir çekilişle yeniden ölçülmüştü (p95 = 1,0388 → 1,04, K-064). İki yeni çekiliş
   defteri 50'ye çıkardı; eşik sonraki programın açılışında yeniden ölçülecek (K-044).
