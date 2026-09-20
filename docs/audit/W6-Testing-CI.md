# W6 — Test / CI / Determinizm

**Tarih:** 2026-09-20 · **Baseline:** `1e1a05b` · **Kod değişikliği:** yok
**Koşulan:** `pytest -m "not network"` (iki kez: W0'da `-x`, burada `--durations=15`),
`ruff check src tests tools`, GitHub API sorgusu (anonim → 404, repo özel), süreç ağacı
(`Win32_Process` ParentProcessId). **Okunan:** 89 test dosyasının adları/sınıfları, seçilmiş
suite'lerin gövdeleri (`test_izolasyon`, `test_risk_bypass`, `test_look_ahead`,
`test_coklu_test::TestEsikBayatligi`, `test_kill_sureci`, `test_jev_izolasyon`, referans suite'leri),
`.github/workflows/test.yml`, `pyproject.toml [tool.pytest]`, `tools/*referans_uret.py`.

Brief §10'un kuralı uygulandı: ham test sayısı kalite ölçüsü değil; her önemli suite için
"**bu test gerçekte neyi kanıtlıyor?**" soruldu.

---

## 0. Özet

| Ölçü | Değer |
| --- | --- |
| Toplanan / seçilen test | 1.848 / 1.845 (3 `network` deselect) |
| Sonuç (yerel, Windows, Python 3.12.10) | **hepsi geçti**, çıkış 0; yalnız starlette deprecation uyarısı |
| Ruff (`src tests tools`) | **temiz** |
| Test kodu | 89 dosya, 22.067 satır (src 38.816 → oran 0,57) |
| Doğrudan testi olmayan src modülü | 25 (W1 §5; çoğu strateji kütüphanesi dolaylı kapsanıyor) |
| Property-based (hypothesis) | **yok** — rastgele girdiler `default_rng(sabit)` ile, 25 dosyada |
| E2E/CLI | `CliRunner` 4 dosya (`test_cli` 36 test), `tmp_path` 70 dosya |
| Flaky | bu oturumda **gözlenmedi** (2 tam koşu aynı sonuç); seed'ler sabit; duvar saati testlerde parametre |
| GitHub Actions uzak durumu | **UNKNOWN** — repo özel, `gh` kurulu değil, anonim API 404. Yerel eşdeğeri yeşil |

**Üç yapısal bulgu:**

| # | Bulgu | Sınıf |
| --- | --- | --- |
| T1 | **Kill switch süreç testleri CI'da koşmuyor:** `test_kill_sureci.py` `skipif(sys.platform != "win32")` (10 test), CI `ubuntu-latest` | RISK — K-065 kriterinin CI kanıtı yok; yalnız yerel Windows |
| T2 | **Eşik bayatlığı bekçisi bekçi değil:** `test_defter_olculen_cekilis_sayisini_gecmedi` gitignore'daki ölçüm çıktısını okuyor (yoksa sessiz geçer); defteri saymıyor. Bugün defter 45 ölçülebilir, sabit 43, test yeşil | RISK — test kendi docstring'inde bunu itiraf ediyor |
| T3 | **Tekrar üretilebilirlik testi yok:** K-009'un "kayıttan yeniden üretim" iddiası (`sq lab dogrula`) hiçbir testte/CI adımında koşmuyor; W3'te 0/16 bulundu | RISK |

## 1. CI yapılandırması (VERIFIED)

`.github/workflows/test.yml` — tek iş, `ubuntu-latest`, 20 dk timeout:
`uv sync --frozen --group dev` → `ruff check src tests tools` → `pytest -m "not network"
-p no:cacheprovider` → `test_jev_durum.py + test_jev_izolasyon.py` ayrıca adıyla.

| Özellik | Durum |
| --- | --- |
| Lock'lu kurulum (`--frozen`) | ✅ K-009 ortam kaydıyla tutarlı |
| Matris (OS/Python) | yok — **T1'in sebebi**: Windows'a bağlı kill testleri hiç koşmuyor |
| Coverage | yok |
| Önbellek | yok (bilinçli) |
| Ağ testleri | dışarıda (bilinçli, doğru) |
| Dal koruması / PR zorunluluğu | UNKNOWN (tek dal `master`, doğrudan push) |
| Uzak koşu kanıtı | UNKNOWN |

Öneri (karar değil): `windows-latest` ikinci iş **yalnız** `test_kill_sureci.py` için; ya da
`os.kill` POSIX dalı için Linux'ta koşan ayrı bir test. Her ikisi de kod değişikliği ister
(kill = üretim-kritik, brief §6 → APPROVAL REQUIRED).

## 2. Suite'ler — ne kanıtlıyor?

### 2.1 Mimari sınırlar (statik, AST)

| Suite | n | Kanıtladığı | Kanıtlamadığı |
| --- | ---: | --- | --- |
| `test_izolasyon` | 11 | `strategy/` geçişli grafikte `exchange/data/execution`, `pandas/pyarrow`, `common.hash`, `features.barlar` **yok**; yasaklı çağrı adları (open, requests, sqlite…) yok; **testin testi**: sahte ihlal yakalanıyor | Dinamik import / `importlib` / monkeypatch (üretimde kullanılmıyor) |
| `test_risk_bypass` | 18 | `execution/oms` → `strategy.sinyal` yok; kesme noktası gerçekten yolun üstünde; ham `Sinyal`, `Red`, taklit nesne, sahte sınıf, elle kurulan niyet, uydurma/başka niyetin mührü **kapıda düşer**; onay sonrası değişiklik yakalanır; risk yukarı çekemez | Mühür anahtarının bellekten okunması (tehdit modeli dışı: tek süreç, tek kullanıcı) |
| `test_jev_izolasyon` | 5 | `jev` → risk/execution/oms/imzali/emir_adaptoru geçişli yok; işlem katmanı jev/typesafe import etmez; typesafe yalnız istemci; negatif kontrol | — |
| `test_coklu_motor::test_tek_motor_kalmadi` | 1 | `backtest/motor.py`de kendi döngüsü yok (K-057) | — |
| `test_kill_switch` (statik kısım) | — | `serbest_birak` `risk/` içinden çağrılmıyor | — |

**Değerlendirme:** Bu katman projenin en değerli test varlığı. Üçü de "negatif kontrol" içeriyor
(test kendi tarama mekanizmasının çalıştığını gösteriyor) — brief'in "test neyi kanıtlıyor"
sorusuna kodun kendisi cevap veriyor.

### 2.2 Sızıntı / determinizm

| Suite | n | Kanıtladığı | Sınır |
| --- | ---: | --- | --- |
| `test_look_ahead` | ~25 | Gelecek 3 biçimde bozulunca sinyaller **bit düzeyinde** aynı, her kesme noktasında, hemen sonraki bar dahil; funding geleceği de; **hileli strateji yakalanıyor, rastgele bozma tek başına yetersiz** (kalibre negatif kontrol); aynı girdi aynı çıktı | Tek sembol + funding; evren look-ahead ayrı (`test_evren`) |
| `test_evren` | 12 | Delist edilen geçmişte kalır (hayatta kalma yanlılığı yok); ay içinde listelenen o ay üye değil; kırılma sonrası yeni kimlik eski hacmi devralmaz; mart sonrası bozulma mart'ı değiştirmez | Ölçüm (%18) ayrı, spike |
| `test_pit` | 15 | `available_time` kesicisi geçer, `event_time` kesicisi **reddedilir**; revizyon öncesi/sonrası görünüm; gün sonuna yuvarlama | — |
| `test_jev_durum` | 30 | Kanonik JSON byte-identical (10 tekrar); gelecek bar/funding bozma+silme → aynı; pencere dışı geçmiş etkisiz; NaN/numpy tipi yok | Jev'in cevabı deterministik değil (ölçülüyor, test edilmiyor — doğru) |
| `test_depo_idempotency` + `test_depo_surecler_arasi` | 22 | Aynı veri → aynı **bayt** (satır/sütun sırası, dtype, pandas metadata etkisiz); iki ayrı süreçte aynı bayt; parçalı = bütün indirme | K-011 deterministik yazıcı — K-080 geri sarma bunun üstüne kurulacak |
| `test_backtest_referans` / `test_coklu_referans` | 25+25 | **Bağımsız Decimal referans** (üretici motoru import etmiyor, kapalı form defterle doğrulanmış) ile fill/tur/equity bar bar aynı; sermaye muhasebesi tutarlı; hiçbir hedef atlanmadı | Referans senaryo küçük (fixture); gerçek 5 yıllık koşu "iki koşu aynı hash" ile ayrıca (Faz 10) |
| `test_coklu_motor::TestKayitDayanikliligi` | 2 | Sıfır atlama sayacı hash'i değiştirmiyor, sıfır olmayan değiştiriyor (K-057/6) | Eski kayıtları geri getirmiyor (W3 R1) |
| **`sq lab dogrula` / tekrar üretim** | **0** | — | **T3:** kayıttan yeniden üretim hiçbir testte yok |

### 2.3 Risk / promotion

| Suite | n | Kanıtladığı |
| --- | ---: | --- |
| `test_risk_limitleri` | 55 | 8 limit × ihlal / ihlal-olmayan; `risk.json` ↔ `kapilar.py` drawdown tutarlılığı; dosya yoksa varsayılana düşmez |
| `test_risk_portfoy` | 17 | Brüt maruziyet yalnız artıranları kısar, zorla satmaz; enstrüman sayısı yalnız yeni girişleri eler; güven sırası |
| `test_kill_switch` | 23 | K-008'in beş davranışı (giriş durur, pozisyon kapatılmaz, çıkış devam, SAFE_MODE elle, audit) |
| `test_promotion` | 34 | Sıra atlanamaz; dirty/data_quality geçemez; `ASGARI_PAPER_GUN`; elle onay yalnız `live_adayi`nda |
| `test_gozlem_modu` | 13 | Gözlem modu promotion kanıtı üretmez, diğer limitler tam |
| `test_kapilar` / `test_kapilar_v2` | 15+ | Her eşiğin gerekçesi var; ölçülemeyen geçilmiş sayılmaz; yön semantiği |
| `test_coklu_test` | 45 | Dairesel kaydırma sinyal sayısını korur; takvim dışı bar sinyal üretmez; **T2** bekçisi |
| `test_hipotez` / `test_program` | 18+23 | Kimlik içerikten türer (gerekçe/ızgara sırası etkisiz); aynı hipotez yeni çekiliş değil; append-only; program kaydı olmadan çekiliş yazılamaz; bütçe |

### 2.4 Execution / OMS (testnet yolu)

| Suite | n | Kanıtladığı |
| --- | ---: | --- |
| `test_oms` | 28 | State machine geçişleri; idempotency anahtarı mühürden bağımsız, restart'ta aynı; deftere gönderilebilir miktar |
| `test_mutabakat` | 26 | Duplicate → ağ çağrısı yok; UNKNOWN → yalnız mutabakat; uyuşmazlık → halt; **gerçek koşudan çıkan iki hata** regresyon olarak |
| `test_pozisyon` | 20 | Açılış çıpası; komisyon açıklaması; açıklanamayan fark → durur; çıpa yoksa hata |
| `test_limit_iptal` | 19 | İptal kaydı yanıt sonrası; `-2011` → sorgula |
| `test_imzali` | 23 | İmza, recvWindow, hata sınıflandırma, yazma isteğinde retry yok, `.env` gölgeleme sırası |
| `test_binance_adaptoru::TestGercekBinance` | 3 (`network`) | Gerçek REST — CI dışı |

### 2.5 Canlı döngü / toparlanma / kill

| Suite | n | Kanıtladığı |
| --- | ---: | --- |
| `test_paper_dongu` | 19 | `backtest`/`live` modu reddedilir; risk modu = koşu modu; fill t+1 açılış, aleyhte; aynı bar iki kez işlenemez; backfill barında fill yok |
| `test_canli_akis` | 27 | Tazelik/nabız sırası; REST resync; kalite bayrakları |
| `test_toparlanma` | 22 | Portföy fill defterinden **yeniden üretilip** aynı; açık pozisyon/bekleyen kararla kesilse de aynı; bekleyen karar yeniden türetilip doğrulanıyor; toparlanma kesinti sayılmıyor |
| `test_kill_sureci` | 10 | Askıdaki süreç sonlandırılır, emirler iptal, işaret yazılır; iptal başarısızsa kill başarısız; kaldırmak gerekçe ister; işaret varsa SAFE_MODE'da açılır — **yalnız Windows (T1)** |
| `test_evren_kosturucu` / `test_izgara_toplayici` / `test_evren_motor` / `test_evren_sapma` | 5/8/… | Izgara barı hazırlık kuralı; geç bar kararı değiştirmez; canlı vs "girdileri baştan bilseydi" sapması |
| `test_api` | 19 | Salt okunur uçların alanları; gözlem koşusu "kanıt üretmez" der |

### 2.6 Veri

`test_indirici`, `test_arsiv_indirici`, `test_dogrulama`, `test_izgara`, `test_kimlik`,
`test_sozlesme`, `test_funding`, `test_kalibrasyon`: sayfalama/devam, checksum/manifesto,
kalite bayrakları, ızgara hizası, kimlik kırılması eşikleri, sözleşme tamlığı. `test_arsiv_indirici`
K-080 taslağını (`bitis_gun`) **kapsamıyor** (commit dışı kod, test yok — W0).

## 3. Eksik kapsam (brief §10 "missing coverage")

| Alan | Durum | Not |
| --- | --- | --- |
| Kayıttan yeniden üretim (`sq lab dogrula`) | **yok** (T3) | En az bir fixture'lı kayıt CI'da yeniden üretilmeli |
| Kill switch süreç adımı CI'da | **yok** (T1) | |
| Eşik ↔ defter bağı | zayıf (T2) | Bekçi defteri saymalı (değerlendirme kaydı olan hipotezler) |
| `cli/{jev,kill,testnet,izle}` | doğrudan test yok | `sq kill` = üretim-kritik komut; `test_kill_sureci` modülü test ediyor, CLI sarmalayıcısını değil |
| `exchange/turev_rest`, `data/alfred` | test yok | veri katmanı, ağ; sahte istemciyle test edilebilir |
| `research/{degerlendirme,kalibrasyon_v2,tekrar}` | doğrudan test yok | `tekrar` = T3 ile aynı |
| Uzun süreli dayanıklılık (günler) | test değil, ölçüm (K-069 penceresi) | doğru sınıflandırma |
| Property-based | yok | fill/metrik/hash için değerli olurdu; öneri |
| Gerçek dashboard (React) | test yok | W7 |
| Log'larda sır | test yok | `jev/istemci` temizliyor; genel log denetimi yok |

## 4. Determinizm envanteri

| İddia | Test | Durum |
| --- | --- | --- |
| Aynı girdi → aynı sinyal (K-009) | `test_look_ahead::test_ayni_girdi_ayni_cikti` | VERIFIED |
| Aynı veri → aynı Parquet baytı, süreçler arası | `test_depo_*` | VERIFIED |
| Backtest ≡ bağımsız Decimal referans | `test_*_referans` | VERIFIED |
| Tek sembol ≡ çok sembol özel hâli (bit) | `test_coklu_motor` | VERIFIED |
| Canlı ≡ backtest (aynı girdi) | `test_evren_sapma` + K-073 ölçümü (0,0 bps) | VERIFIED |
| Kanonik Jev durumu byte-identical | `test_jev_durum` | VERIFIED |
| Toparlanma yeniden üretimi | `test_toparlanma` | VERIFIED |
| Kayıttan aylar sonra yeniden üretim | — | **KANITLANAMIYOR** (W3 §6) |
| Risk motoru duvar saatine bakmaz | docstring + `PiyasaOlcumu.bar_ms` | VERIFIED (okuma) |

## 5. Süre / performans

`--durations=15` çıktısı (yerel, Windows):

| Süre | Test |
| ---: | --- |
| 13,3 s | `test_pbo::TestSinirlar::test_null_ortalamasi_yarim_ama_tek_olcum_gurultulu` |
| 11,1 s | `test_evren_motor::test_bar_bar_motor_tam_backtestle_ayni[kesitsel]` |
| 7,1 s | `test_evren_motor::test_makro_motoru_arastirma_yoluyla_ayni` |
| 6,0 s | `test_evren_motor::test_sapma_geciksiz_kosuda_sifir_gec_barda_sebebine_baglanir` |
| 5,2 s | `test_evren_motor::test_turev_toparlanma_ve_sapma` |
| 4,5 s | `test_evren_motor::test_dogrulama_onbellegi_bit_esit` |
| 4,1 s | `test_evren_motor::test_turev_motoru_arastirma_yoluyla_ayni` |
| 4,1 s | `test_evren_motor::test_toparlanma_ayni_yolu_yeniden_uretir_ve_devam_eder` |
| 4,0 s | `test_pbo::TestYon::test_overfit_senaryosu_yuksek_pbo` |
| 2,8 s | `test_evren_motor::test_bar_bar_motor_tam_backtestle_ayni[kiyas]` |
| ≤1,4 s | geri kalan 1.835 test |

Toplam ≈5 dk (yerel). Yavaş 10'un 8'i `test_evren_motor` (canlı evren motoru ≡ araştırma yolu,
bit düzeyinde) — bunlar en değerli entegrasyon testleri; hızlandırmak için fixture küçültmek
değil, işaretleyip (`slow`) ayrı iş olarak koşturmak uygun. CI 20 dk timeout içinde rahat.

## 6. U8 kapanışı — çift pano süreçleri

`Win32_Process` ParentProcessId: `.venv\Scripts\python.exe` (venv başlatıcısı) → gerçek
`Python312\python.exe` çocuk. Aynı port için **iki değil bir** sunucu; başlatıcı/çocuk çifti.
Sorun yok.

## 7. Sonraki dalgalara

| # | Kalem | Nereye |
| --- | --- | --- |
| T1 | Kill süreç testleri için Windows CI işi | ROADMAP R1 (APPROVAL: kill = üretim-kritik ama değişen şey CI yaml) |
| T2 | Eşik bekçisinin defteri sayması | R1 |
| T3 | Yeniden üretim testi + CI adımı | R1 (K-080 ile birlikte) |
| — | `test_arsiv_indirici`ye `bitis_gun` | K-080 tamamlanırken |
| — | GitHub Actions gerçek durumu | `gh auth login` sonrası `gh run list` — insan adımı |

**Sonraki dalga:** W7 — Operations / Product Readiness.
