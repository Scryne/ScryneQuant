# R1(d) — Karar maddeleri D1–D4 (KARAR VERİLDİ → K-081)

**Tarih:** 2026-09-20 · **Durum:** Scryne onayladı (D1 onay, D2 koru, D3 onay, D4 ölçüm kimliğini
koru + deploy verisini ileri sar); uygulama bu dokümanın sonundaki bölümde. Aşağıdaki madde
metinleri karar öncesi hâliyle bırakıldı (kayıt). · **Girdi:** `2026-09-20-R1c-esik-yeniden-olcumu.md` (ölçüm), K-044/064/071
(önceki ölçümler), K-050 (asimetri), K-039 (sayım), K-080 (veri sonu)
· **Doğrulanan durum:** `HEAD == origin/master == e5ff3e9`, çalışma ağacı temiz; CI **UNKNOWN**
(repo özel, bu makinede `gh`/token yok — `gh auth login && gh run list -L 3` insan adımı).

Her madde: **ölçümün söylediği** (veri) → **karar** (insan) → **onay sonrası değişiklik**.

---

## D1 — Çekiliş sayısı: `COKLU_TEST_CEKILIS_SAYISI` 43 → 45

**Kanıt (R1(c) gerçekten 45 çekiliş kullandı; defterde 52 kayıt):**

| Kaynak | Değer |
| --- | --- |
| `docs/Hipotez-Defteri.jsonl` (git, `11e5f09`) | **52** satır |
| `runs/faz12/coklu-test/*.json` (çekiliş başına null önbelleği) | **45** dosya; kimlikleri defterin 45 satırıyla birebir eşleşiyor |
| Ölçülemeyen 7 | h13–h17, h20, h21 — **hepsi 1d**: geçerli aday üretmeyen çekilişler (Faz 11 §4 notu); önbellekte dosyası yok |
| `coklu-test-birlesik-500-0.json` | `defter_sayisi 52 · olculebilir 45 · tek_sembollu 31 · evren 14 · null.cekilis_sayisi 45` |
| `research/kapilar.py:76` | `COKLU_TEST_CEKILIS_SAYISI = 43` (K-071 fotoğrafı) |
| `tests/unit/test_coklu_test.py:371` | `OLCULEN_CEKILIS = 43` |

**Ayrım:** `COKLU_TEST_CEKILIS_SAYISI` ve `OLCULEN_CEKILIS` **eşik değildir**; "eşik hangi
defter hâlinde ölçüldü" fotoğrafıdır (kapilar.py yorumu: "ölçülebilir çekiliş sayısı değişirse
yeniden ölçülür, elle büyütülmez"). Yeniden ölçüm **yapıldı**; sabiti 45'e çekmek fotoğrafı
güncellemektir, kapıyı değil. Bu değişiklik `COKLU_TEST_ESIGI`nin değerine dokunmaz.

**Onay gerektiren:** evet (K-071 kalıbı: sabit yalnız ölçümle birlikte değişir; ölçüm var, karar
kaydıyla birlikte yazılır).

**Onay sonrası:** `kapilar.py` 43→45 + yorum satırına R1(c) kaydı; `test_coklu_test.py`
`OLCULEN_CEKILIS` 43→45 ve geçmiş notu ("31 → 41 → 43 → 45"). Etki: yerelde kırmızı olan
`test_defter_olculen_cekilis_sayisini_gecmedi` yeşile döner.

## D2 — Eşik: `COKLU_TEST_ESIGI = 1.04`

**Ölçümün söylediği (veri, yorum değil):**

| | K-044 (31) | K-064 (41) | K-071 (43) | **R1(c) (45)** |
| --- | ---: | ---: | ---: | ---: |
| %5 sınırı | 1,021 | 1,039 | 0,926 | **1,004** |
| %90 GA | 0,975–1,055 | 0,975–1,076 | 0,838–0,967 | **0,982–1,064** |
| Sabit 1,04'ün gerçek FP'si | — | — | %2,6 | **%4,2** |

- 45 çekilişte null maksimumunun %95'i **1,004**; GA **1,04'ü kapsıyor** (0,982–1,064) — yani
  "1,04 ölçümden istatistiksel olarak farklı" denemez.
- Sabit 1,04, tasarım hedefi %5'e karşı **%4,2** yanlış-pozitif veriyor: hedeften biraz sıkı.
- Sağ kuyruğu tek çekiliş (h52, turnover bandı, n=5) taşıyor; iki çekilişin eklenmesi sınırı
  0,926 → 1,004 taşıdı (+0,078). Sonraki çekilişler sınırı 1,04'ün **üstüne** taşıyabilir.
- 52 çekilişin hiçbiri ne 1,004'ü ne 1,04'ü geçiyor (en iyi OOS 0,459 tek sembol / 0,363
  evren); bugünkü sonuçlar için iki sayı arasında **pratik fark yok**.

**Politika kararı (insan):** üç yol, hiçbiri ölçümden otomatik çıkmaz:

| Seçenek | Ne | K-050/K-007 okuması |
| --- | --- | --- |
| (a) 1,04 kalır | Sabit ölçümün üstünde; gevşetme yok, sıkılaştırma gerekmiyor | K-071 ile aynı kalıp; "tam %5 olsun" gerekçesi gevşetme sayılır |
| (b) 1,004 | Ölçülen %5 sınırına indir | **İzni artıran yön** (K-050): sayısal kapı + elle onay + yazılı gerekçe ister; pratik etkisi bugün sıfır |
| (c) 1,064 | GA üst sınırına çıkar | Sıkılaştırma (belirsizlikte aleyhte); sonraki çekilişlerde yeniden ölçüm yine gerekir |

**Bu dokümanın yaptığı:** hiçbiri. `config/esikler.json` **yok** (R5'te açılacak), politika
dosyasına ve `kapilar.py`ye **yazılmadı**; `1,004` hiçbir yere "onaylı" olarak girmedi.

**Onay sonrası (hangisi seçilirse):** K-081 karar kaydı (`Kararlar.md`; K-071 biçimi: ölçüm,
seçilen sabit, gerekçe, GA, FP); `kapilar.py` `oos_sharpe` gerekçe metnine R1(c) satırı
(sabit değişmese bile ölçüm geçmişi güncellenir); (b) ya da (c) seçilirse
`COKLU_TEST_ESIGI` değişir ve `test_kapi_olculen_degeri_tasiyor` + `risk.json` tutarlılık
testi koşulur.

## D3 — Bekçi: JSON yerine defter

**Mevcut mekanizma ve neden 45 > 43'ü yakaladı:** `test_defter_olculen_cekilis_sayisini_gecmedi`
`runs/faz12/coklu-test-birlesik-500-0.json` (gitignore) dosyasını okuyor ve `olculebilir <=
COKLU_TEST_CEKILIS_SAYISI` diyor. R1(c) o dosyayı yeniden yazdığı (45) için test **yerelde**
kırmızı — bekçi çalıştı. Ama iki zaaf, testin kendi docstring'inde yazılı: dosya yoksa test
**sessizce geçer** (CI'da hep yok) ve "ölçülebilir" sayısı defterden değil ölçüm çıktısından
geliyor — ölçüm koşturulmadan defter büyürse (W0'daki durum: 52 satır, sabit 43, dosya 09-18)
bekçi **hiçbir şey görmez**.

**Hedef:** `COKLU_TEST_DEFTER_SAYISI = 52` (`kapilar.py`, ölçümün defter fotoğrafı) ve test
`len(HipotezDefteri().tumu()) == COKLU_TEST_DEFTER_SAYISI` — defter git'te (`docs/`), yani
**CI'da da görünür**. Yeni bir hipotez satırı (ölçülebilir olsun olmasın) testi kırar: ya
yeniden ölçüm ya da bilinçli sabit güncellemesi. Ölçülemez bir hipotezin bile yeniden ölçüm
istemesi kasıtlı sertlik (K-039: her kayıt bir çekiliş adayı) — gevşek seçenek (yalnız
değerlendirme kaydı olanları saymak) `runs/`a bağımlı olduğu için CI'da yine sessiz kalırdı.

**Onay gerektiren:** evet (test disiplinini sertleştiriyor; her `hipotez-kaydet` sonrası
`sq lab coklu-test`/`faz12_coklu_test` zorunlu hâle gelir — bu bir süreç kararı).

**Onay sonrası:** `kapilar.py` `COKLU_TEST_DEFTER_SAYISI: Final = 52`; `test_coklu_test.py`
yeni test + mevcut JSON testinin "dosya yoksa sessiz geç" dalı **kalır** ama artık tek bekçi
değildir; `hipotez-kaydet` çıktısına "defter büyüdü: eşik yeniden ölçülmeli" uyarısı (isteğe
bağlı). Threshold-Policy §2 "çoklu test" satırına bekçi tanımı.

## D4 — Veri sonu: `data/evren` 2026-09-14 23:00 UTC

**Durum:** 734 sembolün 684'ü zaten 09-14'te bitiyordu; 09-19'da uzatılmış 50 sembol
`sq data arsiv-indir <50> --bitis-gun 2026-09-14` ile **ağsız** geri sarıldı (0 dosya indi;
`1h.kaynak.json::bitis_gun = "2026-09-14"`). Bu hâlde h51/h52 kayıtlı hash'leri **aynen**
yeniden üretildi (R1(c) §3) ve 45 çekilişlik ölçüm bu hâlde yapıldı.

**Korunan kanıt:** 50 sembolün 09-18 hâli `scratchpad/evren50-yedek/` (58 MB, parquet +
kaynak.json); geri sarım raporu `scratchpad/evren50-geri-sarim.json`; K-080'in ileri sarma yolu
`sq data arsiv-indir <semboller>` (bitis_gun'suz; günlük Eylül dosyaları yeniden iner) ya da
yedekten kopya. **İleri sarma yapılmadı** ve karar olmadan yapılmayacak.

**Onay gerektiren:** ileri sarma tarihi/zamanı. Seçenekler: (a) sabit kalır — yeni program
açılana kadar ihtiyaç yok, kayıtlarla aynı hâl; (b) yedekten 09-18'e — Jev evren replay
(K-076) hâli; ölçüm hâline K-080 ile dönülebilir; (c) önce bir sembolde arşivden uzatma ≡ yedek
(bayt) doğrulaması, sonra sabit (K-080'in "uzatmak da aynı komut" iddiasının gerçek depo
kanıtı; ~1 dk, ağ).

**Not:** scratch dizini oturuma bağlı; yedek kalıcı olacaksa `runs/yedek/evren50-2026-09-18/`
gibi git dışı ama proje içi bir yere taşınmalı (D4 ile birlikte karar).

---

## Onay sonrası uygulanacaklar (özet, sırayla)

1. **K-081** karar kaydı: D1 + D2 (seçilen yol) + D3 + D4 tek kayıtta; kaynak R1(c) dokümanı.
2. `research/kapilar.py`: `COKLU_TEST_CEKILIS_SAYISI = 45`, `COKLU_TEST_DEFTER_SAYISI = 52`,
   `oos_sharpe` gerekçesine R1(c) satırı; `COKLU_TEST_ESIGI` **yalnız D2 (b)/(c) seçildiyse**.
3. `tests/unit/test_coklu_test.py`: `OLCULEN_CEKILIS = 45`, defter sayısı testi.
4. `docs/research/Threshold-Policy.md` §2 `oos_sharpe` satırı: "bayat" → R1(c) ölçümü + karar.
5. `docs/ROADMAP-RESET.md` R1(c) ✅.
6. D4 (c) seçildiyse doğrulama koşusu; yedek kalıcı yere.
7. Tam takım + ruff; commit; push (ayrı onay).

Bu listeden hiçbiri bu commit'te yapılmadı.


---

## Uygulama (2026-09-20, K-081)

| Madde | Karar | Yapılan |
| --- | --- | --- |
| D1 | 43 → 45 | `research/kapilar.py` `COKLU_TEST_CEKILIS_SAYISI = 45` (+ yorumda R1(c)); testteki `OLCULEN_CEKILIS` kopyası kaldırıldı, sabit git'teki fotoğrafla karşılaştırılıyor |
| D2 | 1,04 **korunur** | `COKLU_TEST_ESIGI` değişmedi; 1,004 hiçbir config/politika dosyasına eşik olarak yazılmadı; gerekçe K-081/2 |
| D3 | bekçi defteri sayar | `research/coklu_test_fotograf.py` (fotoğraf yaz/oku/kur, tutarsızlıkta hata); `tools/faz12_coklu_test.py --birlestir` sonunda fotoğrafı yazar; bugünkü fotoğraf mevcut ham çıktıdan üretildi (**ham dosya değiştirilmedi**): `docs/research/coklu-test-olcum.json`; `test_coklu_test.py::TestEsigiDefteBagla` 9 test (sabit=fotoğraf, defter uzunluk+SHA, kimlik birebir, %5 ≤ sabit, ham çıktı varsa uyum / yoksa görünür skip, kapı=sabit, >0,5, gerekçe); `test_coklu_test_fotograf.py` 6 test (negatifler) |
| D4 | kimliği koru, veriyi ileri sar | R1(c) kaydı değişmedi. Yedek → `runs/yedek/evren50-2026-09-18/` (50 sembol parquet+kaynak.json, `_sha256.txt`, geri sarım raporu). Kanıt: scratch kopyada `arsiv-indir <50> --bitis-gun 2026-09-18` (200 günlük dosya indi) → **50/50 SHA-256 yedekle aynı** (`_arsivden-yeniden-uretim-sha256.txt`, `_arsivden-yeniden-uretim-raporu.json`). Sonra `data/evren` 734 sembol güncel arşiv sonuna uzatıldı: **2026-09-19 23:00 UTC** (482 aktif sembol), 2.410 dosya, 0 hata, 3.341 s (`runs/yedek/evren-ileri-sarma-2026-09-20.{json,log}`). Ölçüm hâli `--bitis-gun 2026-09-14` ile geri gelir |
