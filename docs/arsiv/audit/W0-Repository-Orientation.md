# W0 — Repository Orientation (Depo Yönlendirmesi)

**Tarih:** 2026-09-20 · **Dalga:** 0 / 8 · **Kod değişikliği:** yok (yalnız bu doküman)
**Yöntem:** her satır bir komut çıktısına veya dosyaya dayanır; brief'te "bildirilen" her bilgi
repoya karşı doğrulandı. Doğrulanamayan şey `UNKNOWN` olarak bırakıldı.

---

## 1. Git durumu (VERIFIED)

| Alan | Değer |
| --- | --- |
| Uzak | `https://github.com/Scryne/ScryneQuant.git` (origin) |
| Dal | `master` (tek dal, PR akışı yok) |
| HEAD | `1e1a05badc62464891fdc3a4e0d9e7eb829dff5a` — "durum: state.json — Faz 8 hazırlık, denetim, eşik yeniden ölçümü başlatıldı (45 çekiliş), origin senkron" (2026-09-20 12:47 +03) |
| origin/master | aynı commit (`git rev-list --left-right --count master...origin/master` → `0 0`) |
| Tarih aralığı | 136 commit, `f4678fc` 2026-09-08 → `1e1a05b` 2026-09-20 (12 gün) |
| Çalışma ağacı | **temiz değil:** `M src/scryne_quant/data/arsiv_indirici.py` (+56/−2) ve izlenmeyen `.claude/sync-health.json` |

**Brief'teki "reported baseline `86d3f4d`" bayat.** `86d3f4d` HEAD'in 3 commit gerisinde
(sonrasında `53196a5` Faz 8 hazırlık dokümanı, `ae59fd2` denetim düzeltmeleri, `1e1a05b`
state). Bu denetimin baseline'ı **`1e1a05b`**'dir.

**Commit edilmemiş değişiklik (`arsiv_indirici.py`):** `bitis_gun` parametresi — depoyu bir
tarihe sabitleme/geri sarma. Docstring **K-080**'e atıf yapıyor ama `docs/Kararlar.md`'de
son karar **K-079** (K-080 yok). Yani yarım kalmış bir iş: kod var, karar kaydı ve testi yok.
Gerekçe docstring'de: depoyu 4 gün uzatmak 52 çekilişin `sonuc_hash`'ini bozdu (OOS penceresi
veri sonuna bağlı). Bu, **tekrar üretilebilirlik açısından W3'te incelenecek gerçek bir bulgu**
(veri seti kimliği "son bar" ile değişiyor). Bu dalgada dokunulmadı.

## 2. Teknoloji stack — brief vs repo

Brief'in "bilinen bağlam" listesi büyük ölçüde **yanlış**. Repo kaynak alınır.

| Brief iddiası | Repo gerçeği | Kanıt |
| --- | --- | --- |
| Python 3.12 | ✅ `==3.12.*`, `.venv` 3.12.10 | `pyproject.toml`, `.python-version` |
| FastAPI | ✅ var, **salt okunur**, trader sürecinin içinde | `pyproject`, `live/api.py`, Final-Doküman §Stack |
| PostgreSQL 16 + pgvector | ❌ **yok.** Operasyonel state SQLite (WAL); `migrations/001_faz5.sql` var ama **uygulanmadı ve donduruldu** (K-034) | `grep psycopg/sqlalchemy/pgvector` → 0 sonuç |
| Redis 7 | ❌ yok | grep → 0 |
| Celery 5.4 | ❌ yok ("Celery/Redis/Temporal yok — K-011") | grep → 0 |
| Docker Compose | ❌ yok; `Dockerfile`/`compose*` yok. Host dağıtımı Windows Scheduled Task + PowerShell (`tools/*.ps1`) | `ls`, `tools/evren-gorev-kur.ps1` |
| Structlog | ✅ | `pyproject` |
| Sentry | ❌ yok ("Prometheus/Grafana/Sentry yok") | grep → 0 |
| GitHub Actions | ✅ tek workflow | `.github/workflows/test.yml` |
| Jev research/shadow | ✅ `src/scryne_quant/jev/` (2.720 satır), TypeSafe SDK | tree |

**Doküman-içi çelişki:** `docs/arsiv/Final-Dokuman.md` §Stack "Zamanlama: **APScheduler** (tek proses)"
diyor; `apscheduler` ne `pyproject`te ne `uv.lock`ta ne kodda var. Gerçek zamanlama: Windows
Task Scheduler (`Register-ScheduledTask`) + koşturucu döngüleri. → **W8 teknik borç: doküman
yanlış.** Aynı tabloda "ML: scikit-learn (Faz 13+, koşullu)" — kodda `sklearn` yok, koşullu
olduğu için tutarlı.

**Gerçek bağımlılıklar (`pyproject.toml`, 13 runtime + 3 dev; `uv.lock` 65 paket):**
`aiohttp, ccxt, duckdb, fastapi, numpy, pandas (3.x), pyarrow, pydantic v2, structlog, typer,
typesafe-sdk, uvicorn` · dev: `httpx, pytest, ruff`. Frontend (`apps/web/package.json`):
React 19, Vite 7, TypeScript 5.9, Tailwind 4, `lightweight-charts` 5, react-router 7.

**Dış servisler (koddan):** Binance spot REST/WS + `data.binance.vision` arşivi
(`exchange/`), Binance testnet (K-015), Binance futures REST yalnız **veri** (`turev_rest.py`),
FRED/ALFRED (`data/alfred.py`), ntfy.sh (alarm), TypeSafe API (Jev). **Başka borsa/broker yok.**
Brief'in FX/endeks/emtia evreni için **hiçbir veri kaynağı ya da adaptör repoda yok** — bu W1/R2'de
ele alınacak, şimdiden bilinmeli.

**Sırlar:** `.env` git dışı, `.env.example` beş anahtar ailesini adlandırıyor (testnet işlem;
canlı **salt okunur**; Faz 8 işlem anahtarı **üretilmemiş**; FRED; ntfy; TypeSafe hostun ortam
değişkeninde). Ortam değişkenlerini okuyan modüller: `cli/main.py`, `data/alfred.py`,
`data/kimlik.py`, `exchange/emir_adaptoru.py`, `exchange/imzali.py`, `jev/istemci.py`. W2'de
her biri okunacak.

## 3. Depo yapısı (VERIFIED)

```
ScryneQuant/
├── src/scryne_quant/        38.816 satır Python, 15 paket (aşağıda)
├── tests/unit/              89 test dosyası, 22.067 satır; fixtures/ 3 referans JSON
├── tools/                   47 betik: faz12_*/faz14_*/faz16_* ölçüm betikleri (donmuş), *.ps1 host operasyonu
├── apps/web/                Dashboard SPA (React/Vite/Tailwind); dist/ commit dışı
├── config/                  risk.json · maliyet.json · jev.json
├── migrations/001_faz5.sql  PostgreSQL şeması — uygulanmamış, dondurulmuş (K-034)
├── docs/                    55 dosya (aşağıda) + spikes/ (8 spike + README) + program-adaylari/
├── data/                    git dışı: market 67M · evren 639M · turev 3,9G · funding/makro/duyuru/semantik
├── runs/                    git dışı: 101M — audit.sqlite, deneyler, evren, faz12/14/16, jev, paper, testnet
├── research/                boş (yalnız spikes/); gerçek araştırma kodu src/scryne_quant/research/
├── .claude/                 CLAUDE.md, state.json, hooks (session-start/end), settings
├── .github/workflows/test.yml
├── DESIGN.md · README.md · pyproject.toml · uv.lock · .env.example · .env (git dışı)
```

**Not:** `.claude/CLAUDE.md` `research/kapilar.py`, `research/gizli_tekrar.py` yollarına atıf
yapıyor; gerçek yer `src/scryne_quant/research/`. Kök `research/` klasörü boş. → W8.

### 3.1 Paketler (satır sayısı ile)

| Paket | Satır | Sorumluluk (ilk bakış — W1 doğrular) |
| --- | ---: | --- |
| `research/` | 6.695 | Hipotez defteri, walk-forward, kapılar v1/v2, PBO, DSR, çoklu test, program/bütçe, gizli tekrar dedektörü |
| `live/` | 6.256 | Paper/gözlem koşturucu, evren koşturucu, toparlanma, izleme, kill, pano, API |
| `cli/` | 5.332 | `sq` Typer uygulaması: `data / lab / risk / promotion / paper / evren / testnet / kill / izle / jev` (≈55 komut) |
| `data/` | 3.493 | Parquet depo, arşiv indirici, PIT evren, kimlik, funding, makro, konumlanma, doğrulama |
| `risk/` | 2.797 | Risk motoru, limitler, niyet (intent), promotion, audit (zincir hash), mühür |
| `jev/` | 2.720 | Jev gölge katmanı: durum, sorular, istemci, karar, defter, gölge, tekrar, sonuç |
| `exchange/` | 2.378 | CCXT/Binance adaptörü, akış (WS), imzalı istekler, emir adaptörü, türev REST, arşiv |
| `backtest/` | 1.866 | Çok enstrümanlı event loop (`coklu_motor`), tek sembol sarmalayıcı, fill, defter, metrikler |
| `oms/` | 1.627 | Emir, defter, mutabakat, pozisyon (K-046) |
| `strategy/` | 1.539 | Sözleşme, bağlam (`ctx`), sinyal, evren/hedef/kurma; `kutuphane/` 16 strateji |
| `features/` | 647 | Bar/indikatör motoru |
| `execution/` | 567 | Execution motoru + kapı |
| `portfolio/` | 336 | Portföy durumu |
| `common/` | 329 | hash, maliyet, zaman |

### 3.2 Dokümantasyon alanları

- **Bağlayıcı:** `Final-Dokuman.md` (v2, 280 satır), `Kararlar.md` (K-001…K-079, 3.915 satır),
  `Roadmap.md` (Faz 0-16, 1.000 satır), `.claude/CLAUDE.md` (17 değişmez kural).
- **Vizyon/denetim:** `Proje-Fikri.md` (v1), `Proje-Fikri-v2.md`, `Denetim.md`, `Denetim-v2.md`.
- **Defterler (append-only, versiyonlu):** `Hipotez-Defteri.jsonl` (**52 kayıt**),
  `Arastirma-Programlari.jsonl` (**10 kayıt**).
- **Faz raporları:** Faz 1 / 4 (+5 dönüş) / 5 / 6 / 7 / 8-hazırlık / 9 / 10 / 11 / 12 (×5) /
  14 (×2) / 16 (×18) — **~35 anlatısal faz dokümanı.** Brief §28'in "düzinelerce benzer faz
  dokümanı" uyarısı burada gerçek.
- **Jev:** `Jev-Integration-Spec.md` (kaynak), `Jev-Denetim.md`, `Jev-Golge-Raporu.md`.
- **Operasyon:** `Runbook.md` (106 satır; host `192.168.1.4`, portlar 8787/8788).
- **Araştırma kapanışı:** `Alpha-Discovery-Gap-Audit.md` (K-078), `Faz-16-Hat1-Kapanis.md` (K-079).
- **Mevcut audit dokümanı yok:** `docs/arsiv/audit/` bu dalgada açıldı.

## 4. CI (VERIFIED yapı, UNKNOWN uzak durum)

Tek workflow `.github/workflows/test.yml`: push(master)/PR → `uv sync --frozen` → `ruff check
src tests tools` → `pytest -m "not network"` → Jev sızıntı testleri ayrıca adıyla. Matris,
önbellek, dağıtım, coverage yok (K-074/8 bilinçli dar kapsam). **Uzak CI durumu: `UNKNOWN`** —
`gh` bu makinede kurulu değil, GitHub'a sorulmadı. Yerel eşdeğeri §6'da.

## 5. Roadmap durumu (`docs/arsiv/Roadmap.md` tablosundan — W7 doğrular)

| Faz | Durum (dokümanda) |
| --- | --- |
| 0-7 | ✅ (Faz 6'nın 30 günlük kriteri K-055 ile Faz 8/14'e taşındı) |
| 8 Kontrollü live | ⏳ tetik: promotion geçen ≥1 strateji — **0/52** |
| 9-12 | ✅ (PIT veri, çoklu motor, doğrulama v2, araştırma programları) |
| 13 Haber/olay + ML | ⏳ koşullu |
| 14 Üretim sertleştirme | 🔄 K-069 8 günlük pencere, host-1 2026-09-17 → 09-25 |
| 15 İkinci varlık sınıfı (US equities/ETF) | ⏳ koşul: broker/lisans spike'ı |
| 16 Sürekli araştırma | 🔄 "kapanmaz"; 5 program açılıp kapandı, açık program yok |

`.claude/state.json` (`asama: uygulama`) bununla tutarlı ve ek olarak: "sistem çalışan ve
kanıtlanmış bir araştırma + paper/testnet platformu; darboğaz altyapı değil, promotion kapısını
geçen stratejinin bulunmaması." Bu iddia W2/W3/W7'de doğrulanacak, şimdilik **PARTIAL**.

## 6. Yerel doğrulama (bu oturumda koşuldu — VERIFIED)

- `pytest -m "not network" -p no:cacheprovider -q -x` → **çıkış kodu 0, 1.845 test seçildi
  (1.848 toplandı, 3 `network` deselect)**; yalnız starlette deprecation uyarısı.
  state.json'daki "1.847 test yeşil" sayısı ±2 farkla tutarlı.
- Ruff koşulmadı (W6'da).

## 7. Çalışma-anı gözlemleri (bu makine, 2026-09-20 ~15:00)

- Çalışan süreçler: `sq jev …` (gölge-3), `tools/pano.py --port 8788` ve `--port 8790` —
  **her biri iki kez** (biri `.venv\Scripts\python.exe`, biri sistem Python 3.12). Aynı porta
  iki süreç mi yoksa ebeveyn/çocuk çifti mi → `UNKNOWN`, W6/W8'de bakılacak. Bu dalgada hiçbir
  süreç durdurulmadı (hafıza notu: `uv run` kilidi).
- **Eşik yeniden ölçümü (state.json: "başlatıldı, ~2 saat"):** `runs/faz12/coklu-test-500-45.log`
  12:46'da yazılmış **tek satır** (`tek sembollü: ölçülebilir 31, atlanan 21`), süreç listede
  yok, hedef dosya `coklu-test-birlesik-500-0.json` hâlâ 2026-09-18 tarihli. **Ölçüm
  tamamlanmamış ve büyük olasılıkla ölmüş.** → state.json'daki "(c) BAŞLATILDI" kalemi
  gerçeği yansıtmıyor; yeniden koşturulması gerekir (`--deneme 500 --seed 0` ile, aksi
  önbelleği bozar). **INSUFFICIENT EVIDENCE**; W3'te ele alınacak.
- Uzak host `192.168.1.4` bu oturumda **sorgulanmadı** (K-069 penceresi; state.json "bilerek 41
  commit geride" diyor). Durumu `UNKNOWN`.

## 8. İlk bilinmeyenler ve bir sonraki dalgaya taşınanlar

| # | Soru | Dalga |
| --- | --- | --- |
| U1 | K-080 taslağı (`bitis_gun`): veri seti kimliği son bara bağlı → 52 çekiliş yeniden üretilemez. Ne kadar ciddi? | W3 |
| U2 | Eşik yeniden ölçümü öldü mü; `oos_sharpe` 1,04 sabiti 45 çekilişle hâlâ geçerli mi? | W3 |
| U3 | Final-Doküman §Stack'teki APScheduler ve diğer doküman/kod uyuşmazlıkları | W8 |
| U4 | Brief'in FX/endeks/emtia evreni için sıfır adaptör/veri; instrument model bugün Binance'e ne kadar bağlı? (`data/kimlik.py`, `data/sozlesme.py`) | W1 |
| U5 | GitHub Actions gerçek durumu (yeşil mi?) | W6 |
| U6 | Uzak host durumu ve K-069 penceresinin gerçekten neyi koruduğu | W7 |
| U7 | ~35 faz dokümanı: hangileri bağlayıcı, hangileri tarihsel | W8 |
| U8 | Çift pano süreçleri | W6/W8 |

## 9. Bu dalgada yapılmayanlar

Kod değişmedi; commit edilmemiş `arsiv_indirici.py` diff'ine dokunulmadı; hiçbir süreç
durdurulmadı; uzak hosta bağlanılmadı; risk/execution kodu okunmadı (W2).

**Sonraki dalga:** W1 — Architecture (uçtan uca modül haritası + bağımlılık grafiği).
