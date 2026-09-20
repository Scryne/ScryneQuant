# W8 — Technical Debt + Documentation

**Tarih:** 2026-09-20 · **Baseline:** `1e1a05b` · **Kod değişikliği:** yok
**Yöntem:** bağımlılık kullanımı (`grep import` × pyproject), yönetilmeyen public tanım taraması
(AST + referans sayımı, src/tests/tools), `TODO/FIXME/HACK` taraması, doküman iddiası ↔ kod
çapraz kontrolü (W0-W7 bulguları toplandı), `docs/` envanteri (55 dosya, 996 KB),
`runs/` kök dizini, `.claude/state.json`.

Etiket: **BORÇ** (düzeltilmeli), **TARİHSEL** (olduğu gibi kalmalı, etiketlenmeli),
**TEMİZ** (sorun yok).

---

## 0. Özet

Kod tarafı **şaşırtıcı derecede temiz**: ruff sıfır, ölü kod yok denecek kadar az (8 küçük
yardımcı), TODO/HACK yok, geçici kırpıntı yok. Borç **doküman ve süreç** tarafında birikmiş:
üç stack iddiası kodda yok, dört yerde tutulan durum metni birbirinden kayıyor, 35 anlatısal
faz dokümanı "bağlayıcı mı tarihsel mi" etiketi taşımıyor, iki paralel canlı motor/depo
soyutlaması var, ve K-080 gibi yarım kalmış işler commit dışında duruyor.

| # | Borç | Sınıf | Etki |
| --- | --- | --- | --- |
| D1 | **Bildirilen ama kullanılmayan stack:** `duckdb` (pyproject'te, 0 import), `structlog` (pyproject'te, 0 import; projede **hiç logging çerçevesi yok**), APScheduler (Final-Doküman'da, hiçbir yerde yok) | BORÇ (doküman + pyproject) | Yanıltıcı; brief'in yanlış "known context"inin muhtemel kaynağı |
| D2 | **Bildirilmeyen ama kullanılan:** `requests`/`urllib3` (cli/data/exchange doğrudan import; ccxt'nin geçişli bağımlılığı) | BORÇ (pyproject) | `aiohttp` için yazılan gerekçe aynen geçerli |
| D3 | **Durum dört yerde:** README "Durum" paragrafı, `Roadmap.md` tablo, `.claude/state.json` `not` (4.000+ karakter serbest metin), vault index notu — ve session-end hook'u bunları LLM ile senkronluyor. Bugün: state.json "eşik yeniden ölçümü başlatıldı" der, ölçüm ölmüş (W0/W3) | BORÇ (süreç) | Tek doğruluk kaynağı yok; W0'da ilk yakalanan tutarsızlık buradan |
| D4 | **Yarım iş commit dışı:** `arsiv_indirici.py bitis_gun` (K-080 atıflı, K yok, test yok) + izlenmeyen `.claude/sync-health.json` | BORÇ | W3 R3'ün çözümü yarı yolda |
| D5 | **İki canlı motor / iki depo / iki toparlanma / iki koşturucu:** `PaperMotoru`+`KosuDeposu`+`toparlanma`+`Kosturucu` (tek sembol, Faz 6) ↔ `EvrenPaperMotoru`+`EvrenKosuDeposu`+evren toparlanma+`EvrenKosturucu` (Faz 14). Evren yolu backtest çekirdeğini paylaşıyor, tek sembol yolu kendi döngüsüne sahip | BORÇ (soyutlama) | Faz 8'de execution bağlantısı **iki kez** yazılmak zorunda; test yükü çift |
| D6 | **Eşik/sayı kopyaları:** `PROMOTION_DRAWDOWN_KAPISI` (risk ↔ research, testle eşit tutuluyor — kabul edilebilir); `COKLU_TEST_CEKILIS_SAYISI=43` (kod) ↔ `OLCULEN_CEKILIS=43` (test) ↔ defter 45 (bekçi yok, W6 T2) | BORÇ | |
| D7 | `.claude/CLAUDE.md` yolları yanlış (`research/kapilar.py` → `src/scryne_quant/research/`); kök `research/` boş klasör (yalnız `spikes/`), pyproject'te hâlâ ruff-exclude | BORÇ (küçük) | Yeni oturumda yanlış yönlendirme |
| D8 | **`cli/main.py` 3.500 satırlık tanrı-modül** (55 komut, 10 alt uygulama tek dosyada; `izle/jev/kill/testnet` ayrılmış, geri kalanı değil) | BORÇ (yapı) | Doğrudan testi düşük (W6) |
| D9 | `migrations/001_faz5.sql`: uygulanmamış PostgreSQL şeması, K-034 ile dondurulmuş, `risk/audit.py` SQLite şemasıyla hizalı tutuluyor ve **testle korunuyor** | TARİHSEL (bilinçli) | Bakım maliyeti sıfır değil; K-034 geri dönüş koşulları ölçülmüş |
| D10 | **35 anlatısal faz dokümanı** etiketsiz; hangisi bağlayıcı belli değil | BORÇ (doküman) | Brief §28 |
| D11 | `runs/` kökünde 16 başıboş log/JSON (`faz16-*.log`, `faz4_rapor.json`, `pano-test.log`, `temiz.json`, iki hash-adlı JSON) | BORÇ (küçük, git dışı) | |
| D12 | `tools/faz16_*.py` per-file ruff-ignore ile donmuş; `tools/faz12_*`, `faz14_*` de aynı kaderde ama ignore'da değil | TARİHSEL | Ölçüm betikleri raporlarla birlikte donuyor — kabul edilebilir, ama `tools/` bir "ölçüm arşivi" hâline geliyor; ayrı klasör (`tools/olcum/` ya da `docs/olcum/`) düşünülebilir |
| D13 | `docs/program-adaylari/01-transkript-desenleri/` — dondurulmuş taslak, program değil; Faz 11/12 engelleri artık yok ama klasör güncellenmemiş | TARİHSEL / karar bekliyor | |
| D14 | Frontend: test yok, a11y/motion/metadata pasları yapılmamış (global CLAUDE.md sırası), `DESIGN.md` lint durumu bilinmiyor | BORÇ (R11) | |
| D15 | `data/evren/_evren/27b7a16ed0ed.json` `git.dirty: true` ile üretilmiş evren tanımı | BORÇ (provenance) | Evren kimliği kirli ağaçtan; K-009 ortam kaydı bu durumu yakalıyor ama engellemiyor |

## 1. Bağımlılıklar

| Paket | pyproject | Kod | Sonuç |
| --- | --- | --- | --- |
| `duckdb` | ✅ | ❌ (yalnız `common/hash.py` ortam kaydı listesinde ad olarak) | **kullanılmayan bağımlılık**; K-011 "sorgu için DuckDB" — hiçbir sorgu DuckDB'yle yapılmıyor, hepsi pandas |
| `structlog` | ✅ | ❌ | kullanılmıyor; **`logging` de yok** (0 `getLogger`). Çıktı `typer.echo`/`print` + `.log`'a yönlendirme + SQLite olay tabloları. Bu bir tasarım olabilir (olay = veri) ama Final-Doküman "structlog (JSON)" diyor |
| `requests`, `urllib3` | ❌ | ✅ (imzali, binance_arsiv, alfred, cli…) | geçişli bağımlılığa güvenme |
| `httpx` (dev) | ✅ | dolaylı (TestClient) | TEMİZ, gerekçesi yazılı |
| `aiohttp` | ✅ gerekçeli | ✅ | TEMİZ — D2 için şablon |
| `typesafe-sdk` | ✅ | ✅ (2 dosya, lazy import) | TEMİZ |
| `uvicorn`, `fastapi`, `typer`, `pydantic`, `pyarrow`, `pandas`, `numpy`, `ccxt` | ✅ | ✅ | TEMİZ |
| `apscheduler` | ❌ | ❌ | yalnız dokümanda |
| Node: `react-router-dom`, `lightweight-charts`, `clsx`, `tailwind-merge` | — | bu dalgada doğrulanmadı | UNKNOWN |

## 2. Ölü kod / geçici çözümler

- AST taraması: 657 public üst-düzey tanım; modül dışından hiç referans almayan **8** (CLI komut
  fonksiyonları decorator'la kayıtlı, sayılmadı): `exchange/binance_arsiv.{ay_oneki,gun_oneki}`,
  `portfolio/durum.fiyat_sozlugu`, `research/kapilar_v2.KapiV2Hatasi`, `research/rejim.olcum_alanlari`,
  `research/tarama.olcut_{sharpe,calmar,getiri,profit_factor}` (muhtemelen modül içi sözlükte).
  **Önemsiz.**
- `TODO/FIXME/HACK/XXX`: **0**. "geçici" geçen 56 yer: geçici dosya/atomik yazım ve "geçici model"
  kavramı — hack değil.
- `strategy/kutuphane/` 16 strateji: 6 aile + 3 funding + 7 evren; hepsi defterde çekilişle
  eşleşiyor, hiçbiri "denenmemiş" değil. **Kapalı ailelerin kodu duruyor** (K-045/K-068) —
  silinmesi değil, `kapali=True` gibi bir etiketle kayıt defterinde işaretlenmesi düşünülebilir.

## 3. Doküman envanteri ve sınıflandırma önerisi (brief §28)

| Sınıf | Dosyalar | Önerilen yer |
| --- | --- | --- |
| **Bağlayıcı (canlı)** | `Final-Dokuman.md` (v2), `Kararlar.md` (K-001…079, 249 KB), `Roadmap.md` (→ `ROADMAP-RESET.md` ile değişecek), `Runbook.md`, `Faz-8-Hazirlik.md`, `Hipotez-Defteri.jsonl`, `Arastirma-Programlari.jsonl`, `Jev-Integration-Spec.md` (kaynak), `.claude/CLAUDE.md`, kök `DESIGN.md`, `README.md` | `docs/decisions/` (Kararlar), `docs/operations/` (Runbook, Faz-8-Hazirlik), `docs/research/` (defterler), `docs/roadmap/` |
| **Tarihsel — faz raporları (23)** | Faz-1, Faz-4 (+5 dönüş), Faz-5, Faz-6, Faz-7, Faz-9, Faz-10, Faz-11, Faz-12 (×5), Faz-14 (×2), Faz-16 (×18 → aşağıda) | `docs/archive/faz/` ya da yerinde `> **Tarihsel** — sayılar K-0XX'e taşındı` başlığı |
| **Tarihsel — vizyon/denetim** | `Proje-Fikri.md` (v1), `Proje-Fikri-v2.md`, `Denetim.md`, `Denetim-v2.md`, `Jev-Denetim.md`, `Jev-Golge-Raporu.md`, `Alpha-Discovery-Gap-Audit.md` | `docs/archive/` — Gap Audit **canlı** kalabilir (K-078 kaynağı) |
| **Spike'lar (8)** | `docs/spikes/01-08` + README | `docs/research/spikes/` |
| **Denetim (bu döngü)** | `docs/audit/W0-W8` + `00-Executive-Summary.md` | `docs/audit/` |
| **Taslak** | `docs/program-adaylari/01-…` | karar: sil / `docs/research/adaylar/` |

**Faz 16'nın 18 dokümanı** (Hat1 ×8, Hat2, Duyuru, Kıyas, Konumlanma ×2, Kurma ×2, M-1, Rejim,
Jev-Evren-Replay, Kapanış): her biri bir ölçümün raporu, sayıları K-068/072/073/076/077/078/079'a
taşınmış. Tek bir `docs/research/records/2026-09-faz16.md` indeksi + arşiv yeterli.

**Kararlar.md 249 KB, 79 karar, tek dosya.** Okunabilirliği düşüyor; "Değiştirir:" zinciri
yalnız 4 kararda açık. Öneri: dosya bölünmez (tek adres değeri), ama başa **karar indeksi
tablosu** (K, başlık, durum, değiştiren) eklenir ve her K'ya `Durum: kabul | değiştirildi (K-0YY)`
alanı zorunlu olur. Brief'in `docs/decisions/` yapısı bu tek dosyayla sağlanabilir.

## 4. Doküman ↔ kod çelişkileri (W0-W7'den toplandı)

| # | Doküman | Kod | Kaynak dalga |
| --- | --- | --- | --- |
| 1 | Final-Doküman §Stack: APScheduler, structlog, DuckDB | yok / yok / yok | W0, W8 |
| 2 | Final-Doküman §Stack "Koşullu: Docker, CI" | CI **var** (K-074/8) | W0 |
| 3 | `.claude/CLAUDE.md`: `research/kapilar.py`, `research/gizli_tekrar.py` | `src/scryne_quant/research/…` | W0 |
| 4 | README/Roadmap: Faz 4 "her sonuç reproduce edilebilir kayıtla" ✅ | bugün 0/16 (W3) — iddia "o gün" doğruydu, "bugün" değil | W3 |
| 5 | state.json: "eşik yeniden ölçümü başlatıldı (45)" | ölçüm h51'de düştü | W0/W3 |
| 6 | Roadmap Faz 11 bitti kriteri: "mevcut 38 çekiliş yeni kapılardan geçirilmiş" | doğru; ama Faz 10 §7/6 "Faz 4 kayıtları Faz 11'de yenilenir" **yapılmadı** | W3 |
| 7 | Roadmap Faz 16 "kapanmaz; her tur bir program kaydı bırakır" | 5 program kapandı, açık program yok, araştırma uzayı K-078 ile **kapalı** → Faz 16 fiilen kapalı | W4/W7 |
| 8 | Roadmap Faz 13/15 "koşullu" | koşullar (veri bütçesi kararı, broker/lisans spike'ı) **hiç ele alınmadı** — terk edilmiş değil, başlanmamış | W7 |
| 9 | K-011 "PostgreSQL (operasyonel, Faz 5+)" | K-034 ile dondu; K-011 başlığı güncellenmedi (üstüne yazma kuralı gereği normal, ama okuyucu K-034'ü bilmeli) | W0 |
| 10 | Runbook: `evren-kiyas` pano 8788 | doğru | — |
| 11 | Jev-Denetim C11 "CI yok" | artık var (K-074/8) — tarihsel doküman, doğru | — |
| 12 | Final-Doküman §Stack "Log: structlog + SQLite audit" | SQLite audit ✓, structlog ✗ | W8 |

## 5. Yinelenen soyutlamalar (D5 ayrıntı)

| Tek sembol (Faz 6) | Evren (Faz 14) | Paylaşılan | Fark |
| --- | --- | --- | --- |
| `live/motor.py PaperMotoru` (482 sl) | `live/evren_motor.py EvrenPaperMotoru` | `backtest.fill/defter`, `RiskMotoru`, `BarPenceresi`, `execution.kapi` (yalnız tek sembol) | Evren `CokluAdimci` kullanıyor (tek kod yolu ✓); tek sembol kendi döngüsü |
| `live/depo.py KosuDeposu` | `live/evren_depo.py EvrenKosuDeposu` | SQLite kalıbı | ayrı şema |
| `live/toparlanma.py` | `evren_motor` içi toparlanma | K-038 ilkesi | ayrı kod |
| `live/kosturucu.py` | `live/evren_kosturucu.py` | kilit, kill, durdurma | ayrı döngü |
| `live/api.py` (8787) | `live/evren_pano.py` (8788) + `tools/pano.py` | — | iki pano, ikisi de salt okunur; `tools/pano.py` K-069 için geçici başlatıcı ("pencere kapanınca gerekmez") — **silinme adayı 25 Eylül sonrası** |
| `sq paper baslat` | `sq paper evren-baslat` | — | |

Öneri (karar değil): tek sembol = evrenin n=1 özel hâli olarak `EvrenPaperMotoru`'na
katlanabilir mi? `backtest/motor.py` için bu K-057'de yapıldı ve statik testle korunuyor;
`live/` için aynı iş Faz 8 öncesi yapılırsa execution bağlantısı bir kez yazılır. Risk: `host-1`
ve `gozlem-2` kayıtları eski şemada — göç değil, "eski koşular eski okuyucuyla okunur" yeterli.

## 6. Süreç borcu

- **D3 durum senkronu:** session-end hook'u `claude -p` ile state.json'u güncelliyor; bu, üretilen
  metnin kaynağını LLM yapıyor. W0'daki "başlatıldı" hatası bunun örneği. Öneri: state.json
  `not` alanı ≤ 500 karakter ve yalnız **işaretçi** (hangi doküman, hangi K); anlatı Roadmap'te.
- **Tek dal, doğrudan push, PR yok:** tek kişilik proje için normal; ama CI sonucu görülmeden
  push'lar birikiyor (uzak durum UNKNOWN). `gh auth` + dal koruması küçük bir adım.
- **Commit dışı iş:** D4. "Her uygulama birimi commit'lenir" (brief §29) — K-080 bunun tersi.
- **Kirli ağaçtan üretilmiş kimlikler:** D15; `git.dirty` kayda giriyor, üretimi engellemiyor.
  Evren/deney kimliği için "dirty ağaçta üretim reddedilir" ya da en azından uyarı düşünülebilir.

## 7. Silinebilir / emekliye ayrılabilir (öneri, onay ister)

| Öğe | Gerekçe | Ne zaman |
| --- | --- | --- |
| `duckdb`, `structlog` pyproject satırları | kullanılmıyor | hemen (`uv.lock` değişir → K-009 ortam kaydı; yeni kayıtlar farklı hash — kabul edilebilir) |
| `tools/pano.py` | K-069 geçici başlatıcı, `sq paper pano` asıl yol | 25 Eylül sonrası |
| `runs/` kök log/JSON'ları | başıboş | hemen (git dışı) |
| kök `research/` klasörü + ruff exclude | boş | hemen |
| `docs/program-adaylari/` | dondurulmuş taslak, engelleri kalktı | karar: ya program kaydına çevrilir ya arşive |
| `migrations/001_faz5.sql` | **silinmez** (K-034 ölçülmüş erteleme) | — |
| Kapalı strateji aileleri kodu | **silinmez** (defter/kayıt yeniden üretimi için gerekli) | etiketlenir |

## 8. Belgelenmemiş davranışlar (koddan görüldü, dokümanda yok)

1. Evren canlı koşuları `gozlem` moduna sabit (`evren_kurulum.py:79`) — Runbook/Roadmap
   söylemiyor (W2).
2. Drawdown kontrolü yalnız sinyal anında (`risk/motor.py:185`) — docstring'de var, Runbook'ta
   yok (W2).
3. Execution kapısı yalnız tek sembol paper yolunda çağrılıyor (W2).
4. Veri seti kimliği son bara bağlı; depoyu uzatmak kayıtları bozar — K-080 taslağı dışında
   hiçbir dokümanda yok (W3).
5. `.env` yükleme sırası: ortam → `.env` (imzali), doğrudan `.env` parse (alfred) — iki farklı yol.
6. `AZALTAN_YONLER` yön bazlı (W2 B5).
7. Kill switch Windows'a bağlı (W6 T1).
8. Projede logging çerçevesi yok; "log" = SQLite olay tablosu + stdout yönlendirme (D1).

**Sonraki adım:** `docs/audit/00-Executive-Summary.md`, `docs/research/Threshold-Policy.md`,
`docs/ROADMAP-RESET.md`.
