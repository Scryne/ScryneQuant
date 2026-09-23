# İz A — CI yeniden üretim · Windows kill · Promotion zinciri: mevcut durum denetimi

**Tarih:** 2026-09-20 · **Baseline:** `363fbb8` · **Kod değişikliği:** yok (yalnız bu doküman)
**Kapsam:** ROADMAP-RESET İz A'nın üç bağımsız alt işi. Bu doküman yalnız **mevcut durumu** ve
**uygulanabilir alt adımları** kaydeder; hiçbir alt adım başlatılmadı. Promotion zinciri
**APPROVAL** ister ve tasarım aşamasında kalır.

---

## 0. Mevcut CI (`.github/workflows/test.yml`, VERIFIED)

Tek iş `pytest`, `ubuntu-latest`, 20 dk: `uv sync --frozen --group dev` → `ruff check src tests
tools` → `pytest -m "not network" -p no:cacheprovider` → Jev sızıntı testleri ayrıca adıyla.
Matris yok, Windows yok, artefakt/rapor yok, `-rs` yok (skip'ler özet satırında görünür ama
adıyla listelenmez). Uzak durum bu makineden **UNKNOWN** (özel repo, `gh`/token yok).

## 1. CI'da yeniden üretim (reproducibility)

### Bugün ne var

| Katman | Durum | Kanıt |
| --- | --- | --- |
| Sentetik uçtan uca: `sq lab tara` → kayıt → depo uzat → `dogrula` red → `--geri-sar` → yeniden üretim; `yenile`; sınıf raporu | **CI'da koşuyor** (unit suite içinde) | `tests/unit/test_geri_sarim.py` (26 test), `tmp_path` + `bar_uret` (deterministik, repo içi) |
| Bağımsız Decimal referansları | CI'da koşuyor | `tests/fixtures/{backtest,coklu}_referans.json` |
| Gerçek kayıtların yeniden üretimi (`runs/deneyler/*`) | **CI'da yok** — `runs/` gitignore | R1(b): 2 aynı, 3 yenilendi, 13 tarihsel |
| Çoklu test bekçisi | CI'da koşuyor (K-081 D3): fotoğraf + defter; ham çıktı yoksa **görünür skip** | `test_coklu_test.py::TestEsigiDefteBagla` |
| Workflow'da adıyla bir "reproducibility" adımı | **yok** — takımın içinde kayboluyor (Jev sızıntı adımı için yapılan şey burada yapılmamış) | `test.yml` |

### Boşluk (W3 0/16'nın sessizce tekrar etmesini ne engeller?)

W3'ün 0/16'sı **gerçek** kayıtların gerçek depoyla uyuşmamasıydı; CI o depoya ve kayıtlara
erişemez ve erişmemeli (`runs/`, `data/` git dışı). CI'nın kanıtlayabileceği şey
**mekanizmanın** çalıştığıdır (sentetik zincir) ve bunun **adıyla** görünür olmasıdır. Gerçek
kayıtların durumu yerel bir ölçümdür (`tools/r1b_kayit_durumu.py`); onun çıktısı git'e giren
küçük bir fotoğraf olabilir (K-081 D3 kalıbı) ve CI o fotoğrafın **kayıtlarla tutarlı** olduğunu
denetleyebilir — ama kayıtları yeniden koşturamaz.

### Uygulanabilir alt adımlar (A1, onay gerektirmez: CI yaml + test kodu)

- **A1.1** `test.yml`e adıyla adım: `reproducibility (kayıt→dogrula→geri-sar, sentetik)` →
  `pytest tests/unit/test_geri_sarim.py tests/unit/test_backtest_referans.py
  tests/unit/test_coklu_referans.py tests/unit/test_coklu_test.py -rs`. Amaç: düştüğünde günlükte
  "reproducibility" satırı görünsün (Jev adımıyla aynı gerekçe).
- **A1.2** Tüm takım için `-rs` (skip'ler adıyla): "sessiz başarı yok" ilkesinin görünür hâli.
- **A1.3** Gerçek kayıt durumu fotoğrafı: `tools/r1b_kayit_durumu.py` çıktısının özeti
  (`docs/research/kayit-durumu.json`: kayıt kimliği → sınıf, tarih, kod commit'i) git'e girer;
  `sq lab dogrula` tipi bir test **CI'da** her `runs/deneyler` kaydı için değil, fotoğraftaki her
  kimliğin `docs/`taki defterle tutarlılığını (yenilenen kayıtların eski→yeni zinciri, tarihsel
  etiketler) denetler. Kayıt yeniden koşturulmaz. **Karar:** fotoğrafın biçimi; küçük.
- **A1.4** (isteğe bağlı, ölçüm ister) `test_geri_sarim`'in 4 CLI testinin süresi (~20 s) CI
  bütçesinde; ayrı iş gerekmiyor.

**Kalan risk:** gerçek kayıtların bozulması yine yerelde fark edilir (A1.3 fotoğrafı eskiyebilir);
bunu "fotoğraf tarihi > N gün" uyarısıyla değil, her kayıt yenileme/ölçümde fotoğrafı yazan
araçla kapatmak gerekir (K-081 D3 kalıbı).

## 2. Windows kill-switch CI/kanıtı

### Bugün ne var

| Öğe | Durum | Kanıt |
| --- | --- | --- |
| `live/kill.py` süreç adımı Windows API (`kernel32 OpenProcess/TerminateProcess`); POSIX dalı `os.kill(pid, 9)` — **hiç test edilmiyor** (`# pragma: no cover`) | VERIFIED | `kill.py:136-160` |
| `tests/unit/test_kill_sureci.py` (10 test) **modül düzeyinde** `skipif(sys.platform != "win32")` | VERIFIED | satır 21 |
| 10 testin **2'si** gerçek süreç ister (`donmus_trader`: `subprocess.Popen` + `NtSuspendProcess` ile askıya alınmış Python; kill → `TerminateProcess` → rapor) | VERIFIED | `test_askidaki_surec_sonlandirilir_*`, `test_kilit_serbest_kalir` |
| Kalan **8'i** dosya/işaret/rapor/başlatma davranışı (`tmp_path`, `.safemode`, `.kill.json`, `baslat.kur` SAFE_MODE'da açılış) — Windows'a bağlı **değil**, ama modül işaretinden dolayı Linux'ta koşmuyor | VERIFIED | test gövdeleri |
| CI'da `test_kill_sureci.py` durumu | `ubuntu-latest` → **10 skip**; özet satırında "10 skipped" görünür, adıyla görünmez | `test.yml` |
| Yerelde (Windows) | 10/10 geçiyor (W6, bu oturumun tam koşuları) | `pytest-r1d.log` |
| Tatbikat aracı | `tools/faz14_kill_tatbikati.py` (K-065) — CI dışı, elle | — |

### Uygulanabilir alt adımlar (A2, onay gerektirmez: test işaretleri + CI yaml; `kill.py` **değişmez**)

- **A2.1** Modül düzeyindeki `skipif`i yalnız iki süreç testine (ve `donmus_trader` fixture'ına)
  indir; 8 dosya-temelli test Linux CI'da da koşsun. Mock yok: aynı gerçek dosya/işaret/rapor
  davranışı.
- **A2.2** `test.yml`e ikinci iş: `kill-switch (windows)` → `runs-on: windows-latest`, yalnız
  `uv sync --frozen --group dev` + `pytest tests/unit/test_kill_sureci.py -rs -p no:cacheprovider`.
  Gerçek `subprocess` + `NtSuspendProcess` + `TerminateProcess`; mock yok. `timeout-minutes: 15`.
- **A2.3** Linux işinde skip'ler adıyla görünsün (`-rs`, A1.2 ile aynı) ve Windows işinin
  "0 skipped" olması beklenir: skip = başarı değil.
- **A2.4 (ölçüm, kod değil)** Windows işinin süresi ve `uv sync`in Windows'ta lock'la kurulumu
  (ccxt/pyarrow wheel'leri) — ilk koşuda ölçülür; CI sonucu bu makineden görünmediği için
  **Scryne'ın `gh run list`/Actions sekmesinden** doğrulaması gerekir.

**Kalan risk:** POSIX dalı (`os.kill`) hâlâ testsiz — host Windows olduğu için kabul edilebilir,
ama "Linux'ta kill çalışır" iddiası **yok**. A2 bunu değiştirmez; not düşülür.

## 3. Promotion kaydı zincir hash'i — **APPROVAL REQUIRED**, yalnız tasarım

### Bugün ne var

| Öğe | Durum | Kanıt |
| --- | --- | --- |
| Kayıt biçimi | `runs/promotion/<strateji>.json`: `{asama, canliya_yetkili, eksik_asamalar, gecmis:[{asama, gecti, gerekce, kanit{commit, dirty, config_hash, sonuc_hash, veri_sha256, risk_*…}, onceki_asama, zaman_ms, zaman_utc}]}` — düz JSON, `sort_keys`, üzerine yazılır | `promotion.py:496-500`, `runs/promotion/sma_kesisim.json` |
| Bütünlük | **yok**: satırlar arası hash yok, dosya imzası yok, append-only tetikleyici yok; `yaz()` tüm dosyayı yeniden yazar | `promotion.py` |
| Canlı okuma yolu | `live/baslat.py:194` `asamalar = {strateji: asama}` ← `PromotionDefteri(promotion_kok).hepsi()` → `RiskMotoru(asamalar=…)` → `MOD_ESIGI["live"] = Asama.LIVE` (3. adım) | `baslat.py`, `promotion.py:96-101`, `risk/motor.py:317` |
| Yani | `runs/promotion/x.json`'da `"asama": "live"` yazan biri (ya da hata) `mod="live"` koşuda promotion kapısını geçer. Bugün canlı emir yolu **olmadığı** için etkisi sıfır (W2 B1); Faz 8'de sıfır olmaz | W2 B4 |
| Hazır kalıp | `risk/audit.py`: `onceki_hash` zinciri, `icerik_hash = nesne_hash(içerik + önceki)`, `ZINCIR_BASI` sabiti, SQLite `UPDATE/DELETE` tetikleyicileri, `dogrula()`; `OlayTuru.PROMOTION` **zaten tanımlı** ama promotion olayları audit'e **yazılmıyor** | `audit.py:62-66,90-115,153-160`; `grep OlayTuru.PROMOTION` → yalnız tanım |
| Testler | `test_promotion.py` (34): sıra, dirty, kanıt; bütünlük testi yok | — |

### Tasarım seçenekleri (karar Scryne'ın)

| | Tasarım | Artı | Eksi / soru |
| --- | --- | --- | --- |
| P1 | **`gecmis` içi zincir:** her aşama kaydı `onceki_hash` + `satir_hash` (audit kalıbı, `nesne_hash`); `PromotionKaydi.yukle()` zinciri doğrular, kırıksa `PromotionHatasi`; `baslat.kur` (live/paper) kırık zincirde **açılmaz** | En küçük değişiklik; JSON kalır; `yaz()` üstüne yazsa da geçmiş zincir sabit | Dosyanın tamamı yeniden yazılabilir (sahip yazabilir — audit.py de aynı sınırı kabul ediyor: "sessiz kurcalamayı" engeller, kasıtlıyı değil); `asama` alanı ile `gecmis`in son satırı **tutarlı** olmalı (ayrı kontrol) |
| P2 | **Audit defterine yansıtma:** her `ilerlet`/`elle_onayla` ayrıca `OlayTuru.PROMOTION` olarak `runs/audit.sqlite`'a (zincir + tetikleyici) yazılır; canlı açılışta JSON'daki aşama audit'teki son promotion olayıyla **çapraz** doğrulanır | Var olan, testli, silinemez defter; ikinci bağımsız kaynak (K-038 "yeniden üretim" ruhu) | İki kaynak senkronu; `sq promotion onayla` CLI'sının audit dosyasına yazması (bugün yalnız JSON'a); koşu deposundaki audit ile global `runs/audit.sqlite` ayrımı |
| P3 | **HMAC imza** (mühür kalıbı, `risk/muhur.py`) süreç anahtarıyla | — | Süreç başına rastgele anahtar restart'ta kaybolur: promotion kaydı süreçler arası yaşar → uygun değil (istemci kimliği için de aynı sebeple mühür dışarıda bırakılmıştı) |

**Öneri (karar değil):** P1 + P2 birlikte — P1 dosyayı kendi içinde tutarlı yapar, P2 bağımsız
ikinci kaynağı verir; canlı açılış ikisini de ister. Ön koşullar ve onay noktaları:

1. **APPROVAL:** `risk/promotion.py` ve `live/baslat.py` değişiyor (K-010 zinciri, canlı açılış
   yolu) — brief §6 üretim-kritik.
2. **Karar:** mevcut `runs/promotion/sma_kesisim.json` (2 satır, `kalite_kontrol`) — zincirsiz
   eski kayıt: **yeniden üretilir** mi (aynı kanıtla, `gecmis` zincirli), yoksa "zincir başlangıcı
   öncesi" etiketiyle mi okunur? (Öneri: yeniden üretim; kayıt küçük, kanıt hash'leri elde.)
3. **Karar:** kırık zincirde davranış — `paper`/`gozlem` modunda da açılış reddedilsin mi, yalnız
   `live`da mı? (Öneri: her modda reddet; K-038 "uyuşmazlıkta durur".)
4. **Karar:** P2'de hangi audit dosyası — koşu deposu (`runs/paper/<koşu>.sqlite`) mı, global
   `runs/audit.sqlite` mi? Promotion koşudan bağımsız → global; ama global dosyanın tek yazıcı
   kilidi yok (`live/kilit.py` koşu başına).
5. Testler: zincir doğrulama (bozuk satır, eksik satır, `asama` ↔ son satır uyuşmazlığı, yeniden
   sıralama), canlı açılışın reddi, CLI `onayla`'nın zinciri uzatması; mevcut 34 test aynen.
6. K-082 kaydı; `docs/arsiv/Faz-8-Hazirlik.md` §1.6'ya (live geçiş) bağ.

**Bu turda yapılmayan:** hiçbir kod. Onay gelene kadar P1/P2/P3 uygulanmaz.

## 4. Sıra önerisi

A2 (küçük, bağımsız, mock'suz) → A1 (yaml + fotoğraf biçimi kararı A1.3) → P (onay sonrası).
A1 ve A2 aynı `test.yml` dosyasına dokunur; iki ayrı commit, çakışma yok.
