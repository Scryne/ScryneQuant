---
proje: ScryneQuant
tur: denetim (kod değişikliği yok)
tarama_tarihi: 2026-09-20 (gist)
denetim_tarihi: 2026-09-23
kaynak: https://gist.github.com/drillan/6916b16e8ea31a8ec36c8f59d6483150
commit: 23862bf (denetim anındaki HEAD)
type: rapor
---
# Jev Trading Ecosystem Audit

> Bu rapor bir **mimari öğrenme** denetimidir. Hiçbir dış projenin Jev ile trading'de işe yaradığını
> iddia etmez, ima etmez. Dış repoların hiçbirinde Jev kararlarının ileriye dönük isabetine dair
> doğrulanmış bir ölçüm bulunmadı (§8). ScryneQuant'ın kendi ölçümü (K-076: 50 sembol, isabet %49,0,
> CI 0,46–0,52) Jev'in yönünün bu projenin durum/soru/timeframe kurulumunda bilgi taşımadığını
> gösteriyor; bu rapor o sonucu değiştirecek bir kanıt bulmadı.

## 1. Executive Summary

1. **Hiçbir dış proje A (gerçek çalışan, operasyon kanıtlı) sınıfında değil.** 13 repo kaynak koduyla
   incelendi: 6'sı B (çalışan prototip), 4'ü C (backtest/simülasyon), 3'ü D (demo/kavramsal). Canlı
   gerçek para iddiası tek projede var (`aowang-ai/jev-trade`, "real fills"): **UNVERIFIED**.
2. **Dış projelerin hiçbiri Jev kararlarının sonucunu güven aralığıyla ölçmüş değil.** Kalibrasyon
   altyapısı olanlar (buberlo, jev_stock, Jev Lab) ya sentetik veride ya da eğitim kesimi bilinmeyen
   tarihsel dönemde çalışıyor. Bu kümede Jev'in yönünü **yayın sonrası temiz pencerede, maliyetle,
   CI ile** ölçen tek kayıt ScryneQuant'ın K-076'sı.
3. **Tekrarlayan sağlam desen**: *deterministik özellik/durum → Jev yargısı → kodda policy → modelden
   bağımsız hard risk veto → execution*. buberlo bunu ilke olarak yazıyor ("Jev should not own the
   trading system"). ScryneQuant bunu **zaten** uyguluyor ve bir adım öteye gidiyor: Jev işlem yolunda
   hiç yok (K-067, K-074/1; AST testli izolasyon).
4. **İki ayrışma çizgisi var:** (a) Jev'i **sinyal üreticisi** olarak kullananlar (jarrodwatts,
   jev-trade, market-reflex, jev-fund) — ScryneQuant kararlarıyla çelişiyor; (b) Jev'i **giriş
   kapısı / veto** olarak kullananlar (QuantDinger, moomoo, Paperline) — mimari olarak K-037'nin
   "engelleyen katman" tanımına uyuyor ama **K-074/1 (spec D açılmaz) ve K-077 (filtre için headroom
   yok) ile çelişiyor.**
5. **En keskin güvenlik farkı hata davranışı:** QuantDinger'ın Jev kapısı **fail-open** (Jev hatası
   ya da düşük güven → LLM → ikisi de yoksa emir **geçer**; `docs/trading/LIVE_TRADING_SAFETY.md`
   bunu bilinçli tercih olarak yazıyor). moomoo aynı işte **fail-closed** (taze inceleme yoksa bekle).
   ScryneQuant fail-closed (K-074/5, K-114 denetimi).
6. **Jev'e boyut/kaldıraç yetkisi veren bir proje var** (`jev-trade`: Jev kaldıraç kademesini seçer;
   kaynak kodunda pozisyon tavanı bulunamadı). ScryneQuant'ta `JevKarari` tipinde bu alanlar yok.
7. **Doğrudan alınabilecek tek desen (ADOPT):** soru/veri hash'iyle anahtarlanmış sabit örnek seti
   üzerinde **model sürümü değişiminde otomatik yeniden skorlama** (Jev Lab `npm run check`). Mimari
   değil, yönetişim/ölçüm deseni; R10 kapsamına düşüyor.
8. **Araştırılmaya değer tek desen (INVESTIGATE):** *blind replay* — sembol, borsa ve tarihi gizleyip
   fiyatı 100'e rebase ederek modelin hatırlama katkısını ölçmek (Jev Lab `--blind`). `leak_riski`
   kuralını **kaldırmaz**; yalnızca teşhis aracı olabilir.
9. **Current phase impact: NONE.** Bulguların hiçbiri R5/R8/R9 ya da K-115 pilotunun yönünü
   değiştirmiyor (§14).

## 2. Scope & Method

**Kaynak:** gist (2026-09-20 taraması, 17 giriş + 1 yorum eki). Her repo **kaynak kodundan**
doğrulandı: sığ klon (`git clone --depth 1`, denetim anındaki son commit), README iddiaları koddaki
dosyalarla karşılaştırıldı (Jev çağrısı, soru seti, risk kodu, test varlığı). GitHub CLI yoktu;
yıldız/istatistik kullanılmadı (sıralama yasak).

| Repo | Son commit (klon) | Kod incelemesi | Kanıt sınıfı |
| --- | --- | --- | --- |
| jarrodwatts/jev-trader | 2026-09-16 | `src/model.ts`, `src/trader.ts`, `src/config.ts` | **B** |
| aowang-ai/jev-trade | 2026-09-21 | `src/model.ts`, `src/plan.ts`, `src/trader.ts`, `test/` (14 dosya) | **B** (canlı fill iddiası UNVERIFIED) |
| OpenByteInc/QuantDinger (Jev bileşeni) | 2026-09-21 | `backend_api_python/app/services/ai_decision_filter.py` (746 satır), testi (513), `LIVE_TRADING_SAFETY.md` | **B** (Jev kapısı için) |
| buberlo/jev-trader | 2026-09-20 | `judgment/battery.py`, `policy/engine.py`, `risk/limits.py`, `loop/engine.py`, `calibration/metrics.py`, `feeds/` | **C** (yalnız sentetik feed; PLAN.md Faz 0) |
| zzsong1023/jev-market-reflex | 2026-09-19 | `src/jev.ts`, `src/paper.ts`, `tests/` | **B** (canlı Kraken verisi, paper; 21 çağrılık tek koşu) |
| rnjsxodyd90 "Paperline" | 2026-09-19 | `jev-trading-bot` **404**; aynı sahibin `jev-trading-bot-fork-backup` reposu: `src/risk.ts`, `src/model.ts`, testler | **B** (paper-only; orijinal repo UNVERIFIED) |
| maxlibin/moomoo-jev-trader | 2026-09-20 | `ai_analysis.py` (`gate_decision`), `executor.py`, `run_live.py`, `tests/` | **B** (gist'te "boş" idi; artık 41 dosya) |
| UditJain2622004/Jev-Trading | 2026-09-19 | `scripts/jev_sol_backtest*.py` (18 deney a–r), `data/jev_backtest*/` | **C** |
| sosopop/jev_stock | 2026-09-17 | `jev_hk_predict.py`, `backtest_first_day.py`, README | **C** |
| IslamBaraka90/jev-…-use-cases ("Jev Lab") | 2026-09-20 | README (backtest lab, `--blind`, benchmark), `results/` biçimi | **C** |
| Gamma-Software/jev-signals-lab | 2026-09-19 | `server.js`, README | **D** |
| beto11-gif/jev-trading-backend | 2026-09-18 | `src/services/jev/analyzer.ts` (`DisabledJevAnalyzer`) | **D** (Jev kapalı) |
| erboland/jev-fund | 2026-09-23 | README, `src/app/api/decide` | **D** (varsayılan mock; Jev yoksa mock'a düşer) |
| Pastorkid/jevTradingBoth, hifizz/jev-finance-benchmark | — | boş repo (commit yok) | — |
| simonmesmith/jev-banking77-experiment, adilmoujahid/jev-banking77-demo, kyotofin/tax-doc-classifier | — | **kapsam dışı**: trading değil, metin sınıflandırma | NOT RELEVANT |

**Kanıt sınıfları:** A — kod + test + gerçek/paper operasyon kanıtı; B — çalışan kod, operasyon
kanıtı sınırlı; C — yalnız backtest/simülasyon; D — demo/kavramsal. **Kanıt sınıfı trading başarısı
hakkında değildir**; B bile "Jev işe yarıyor" demek değildir.

**ScryneQuant tarafı** (dosya/commit referanslı): `src/scryne_quant/jev/` (9 modül), `config/jev.json`,
`docs/arsiv/Jev-Denetim.md`, `docs/arsiv/Jev-Golge-Raporu.md`, `docs/arsiv/Faz-16-Jev-Evren-Replay-Raporu.md`,
`docs/Kararlar.md` K-049, K-061, K-067, K-074…K-077, K-111, K-114, K-115; risk/execution:
`risk/motor.py`, `execution/hat.py`, `execution/canli_kapi.py`, `trader/`.

## 3. External Project Matrix

### 3.1 Proje başına şablon (özet)

| Proje | Jev girdisi (state) | Jev çıktısı | Jev'in rolü | Jev sonrası deterministik sınır | Karar sıklığı | Güvenlik |
| --- | --- | --- | --- | --- | --- | --- |
| jarrodwatts/jev-trader | Kitap ilk 5 seviye, derinlik bantları, `returnsBps`, `recentMids` dizisi (string), taker akışı, `allowed` | `direction` buy/sell + olasılık | **Sinyal üretici** (her blok) | Pozisyon tavanı (`MAX_POSITION_MON`) yalnız tarafı değiştirir; geç kalınan blokta `hold` | Her Monad bloğu (~300 ms) | Tavan, dry-run; test yok |
| aowang-ai/jev-trade | Yukarıdaki + pozisyon (yön, boyut, giriş, kaldıraç, likidasyon mesafesi), 1m indikatörler, mark/oracle/funding/OI | `bias` long/short, `intent` open/close/hold, **`leverage` kademesi** | **Sinyal + boyut/kaldıraç seçici** | Kaldıraç kademeye yuvarlanır; açılış post-only, kapanış IOC; **kaynakta pozisyon tavanı bulunamadı** (grep) | `TICK_MS` 2 s, 5 ayrı sleeve | Testnet varsayılanı; testler + CI |
| QuantDinger | Emir isteği (sembol, miktar, fiyat, kaldıraç, strateji, `signal_reason`) + çok-timeframe `context` | 6 Choice: data_quality, signal_alignment, market_regime, risk_check, execution_quality, entry_decision | **Giriş öncesi kapı (yalnız veto)** | `allowed = pass ∧ risk≠block ∧ exec≠block ∧ ¬(conflict∧adverse)`; güven < `min_confidence` (0,55) → hata | Her giriş emri; çıkışlar filtrelenmez | **Fail-open**: Jev hata/düşük güven → LLM → yoksa emir geçer |
| buberlo/jev-trader | "<400 token" dense snapshot (iddia; doğrulanmadı): mid, microprice, spread, imbalance, vol, envanter, drawdown | 6 atomik yargı: regime, direction, toxic_flow, liquidity_stressed, quote_environment (Score), inventory_pressure (Score) | **Yargı sağlayıcı; policy kodda** | `compose_action` eşikleri kodda; `RiskEngine` OK<REDUCE_ONLY<HOLD<KILL; latency/API hatası/bayat veri veto | Her blok (sentetik) | Kill switch; Jev yoksa deterministik yedek yargı |
| jev-market-reflex | Kraken BTC/ETH/SOL sınırlı özellikler; **3 sembol tek istekte** | Sembol başına BUY/SELL/HOLD | **Sinyal üretici** | Güven < 0,55 → HOLD; boyut güven bandına göre $100/250/500; sembol başı tavan; bayat veri → duraklat | Döngü başına | Paper-only, cüzdan yok |
| Paperline (fork-backup) | jev-trader state'i | direction + olasılık | **Sinyal üretici + güven kapısı** | `MIN_CONFIDENCE` 0,65; kilitlenen oturum zararı $5; model çağrı bütçesi 300; spread/bayat kitap/zaman aşımı | ≥10 blokta bir | Canlıyı başlangıçta reddeder |
| moomoo-jev-trader | Deterministik 7 faktörlü kurulum + 1m OHLCV + benchmark | direction, entry_quality, stop-first risk | **Giriş kapısı, `shadow` varsayılan / `enforce`** | Kurulum kodda; boyut/stop/hedef/günlük limit kodda; `gate_decision`: inceleme **aynı muma** ait ve taze değilse bekle | 5 s | Kill switch; SIMULATE varsayılanı; fail-closed |
| UditJain/Jev-Trading | SOL 1m, **10 kazanan + 10 kaybeden örnek işlem** state'te | take/skip + "looks_like" | **İşlem filtresi** | Sabit TP/SL | Tarihsel replay | 7 günlük veride 18 deney, sayım yok |
| jev_stock | Hedef hisse + HSI + HSTECH 30 seans OHLCV/indikatör, haftalık/aylık bağlam | up/flat/down (eşikli) | **Sınıflandırıcı (tahmin)** | Etiket tanımı kodda; skor Brier | Günlük | Finansal veri tarihsel backtest'ten bilinçli olarak çıkarılmış |
| Jev Lab | 90 mum + isteğe bağlı 10 indikatör; `--blind` | long/short/n.a., stop, hedef, tutma süresi | **Sinyal + plan (backtest)** | Simülatör K-004 benzeri (sonraki gün açılışı), 5 bps/taraf | Kesme noktası başına | Kayıtlı mod; soru/veri hash'li benchmark |
| jev-signals-lab | Tek snapshot | 12 bağımsız olasılık | **Yargı sağlayıcı** | Kodda BUY kuralı (5 eşik) | İstek başına | Paper-only; offline demo etiketli |
| jev-fund | Tek isim, günlük Yahoo | buy/sell/hold | **Sinyal üretici** | Paper boyutlandırma | ~4 s | **Jev yoksa mock'a düşer** |
| beto11 backend | — | — | Yok (devre dışı) | — | — | "Uydurma sinyal yok" ilkesi |

### 3.2 ScryneQuant ile karşılaştırma

| Alan | ScryneQuant | External Project Pattern | Kanıt | ScryneQuant Açısından |
| --- | --- | --- | --- | --- |
| Jev role | Yalnız ölçüm: gölge yön/rejim/kurulum/çekimser kaydı (K-074/1); araştırma yönetişimi (gizli tekrar, K-061); Jev `Sinyal` üretmez (K-067) | Çoğunlukta sinyal üretici; bir grup giriş kapısı; biri yargı sağlayıcı + kod policy | Kod (B/C/D) | different design |
| State design | Kodla hesaplanmış betimleyici etiketler, dizi yok, sayısal kıyas sorulmaz; 1h + kapanmış 4h + funding; `PENCERE_BAR` 1.200; ≈2.059 girdi token (`Jev-Golge-Raporu` §2.2) | İkiye ayrılıyor: ham kitap/tape + fiyat dizisi (jarrodwatts, jev-trade) vs. kompakt kod-hesaplı durum (buberlo, jev_stock) | Kod | already covered |
| Decision frequency | Kapanmış her `ok` 1h bar; `bayat_ms` 2 bar | 300 ms–5 s (mikroyapı) ya da günlük | Kod | different design |
| Policy layer | Jev için yok (tüketici yok); strateji → risk motoru → hat | buberlo/signals-lab/QuantDinger: eşikler kodda | Kod | not applicable |
| Risk veto | Risk motoru tek onay kaynağı (K-037); hat engelleri; azaltan geçer (K-008/3); pilot kayıp tavanı (K-115) | buberlo/Paperline/moomoo: modelden bağımsız veto; jev-trade'de tavan yok | Kod | already covered |
| Execution boundary | Jev → risk/execution/oms **import edemez** (AST, `test_jev_izolasyon.py`); canlı host yalnız 3 modül (`test_canli_izolasyon.py`) | Çoğunda Jev kararı doğrudan emre dönüşüyor | Kod | different design |
| Shadow mode | Ayrı süreç, emir yolu yapısal olarak yok (`golge.py`); execution'da ayrıca SHADOW modu (K-114) | moomoo: `shadow`/`enforce` bayrağı, shadow varsayılan | Kod | already covered |
| Calibration | `sonuc.py`: giriş `open[t+1]`, 1/4/24 bar, MAE/MFE, maliyet, Wilson CI, Brier, ECE, kovalar; tanımlar koşudan önce sabit (`config/jev.json::sonuc`) | buberlo: triple log + Brier/log-loss/ECE/Platt (sentetik); jev_stock: Brier; Jev Lab: ECE | Kod; dışarıda gerçek-veri sonucu yok | already covered |
| Multi-symbol | K-076: 50 PIT sembol, sembol başına ayrı çağrı, saat-küme etkin n; deterministik kesit sinyalleri K-109'da test edildi (momentum/ters/sapma/hacim \|t\|<2) | market-reflex: 3 sembol tek istekte; jev-trade: 5 izole sleeve; jev_stock: endekse göreli | Kod | different design |
| Portfolio context | Jev'e verilmez (Jev'in işlem rolü yok) | jev-trade pozisyon/likidasyon, QuantDinger portföy/drawdown, buberlo envanter | Kod | not applicable |
| Failure handling | Fail-closed: hata = "karar yok" (≠ flat), önceki karar taşınmaz, hata kodu kayıtta (`karar.py`) | QuantDinger fail-open; jev-fund mock'a düşer; buberlo deterministik yedek; moomoo/Paperline fail-closed | Kod | already covered |
| Human approval | Canlı yalnız TTY onayıyla (K-010, K-114, K-115); Jev canlıya hiç bağlanmaz | Hiçbir dış projede canlı geçiş için insan onayı yok (yalnız env bayrakları) | Kod | already covered |
| Evaluation | Ön kayıtlı sonuç tanımları, kıyas (`al_tut`), yayın sonrası temiz pencere (K-075), çekiliş sayımı (K-039) | Tek koşu gecikme tabloları, simüle P&L, sentetik kalibrasyon; bir projede aynı 7 günde 18 deney | Kod | already covered |

## 4. Architecture Patterns

**P-A · Katmanlı zincir (tekrarlayan, sağlam).**

```text
market → deterministik özellik/durum → Jev yargısı → kodda policy → hard risk veto → execution
```

buberlo (README: "Code calculates the state. Jev interprets the state. Code applies policy."), moomoo
("Jev does not size positions, place orders, or manage exits"), Paperline, QuantDinger ve signals-lab
bu zinciri kuruyor. Kanıt seviyesi mimari (B/C); hiçbiri zincirin getiri etkisini ölçmedi.

**P-B · Doğrudan zincir (sinyal üretici).**

```text
market (kitap/tape/dizi) → Jev → emir
```

jarrodwatts, jev-trade, market-reflex, jev-fund, Jev Lab. Deterministik kod yalnızca tavan/format
işi yapıyor. jev-trade'de Jev kaldıracı da seçiyor.

**ScryneQuant'ın konumu:** P-A'nın ilk iki halkası (durum + Jev yargısı) var; üçüncü halkadan
sonrası **bilerek yok** — Jev çıktısının tüketicisi defterdir (K-074/1). Bu, P-A'nın daha kısıtlı bir
hali değil, ayrı bir tasarım: Jev bir ölçüm aracıdır.

## 5. Jev Role Patterns

| Rol | Projeler | ScryneQuant |
| --- | --- | --- |
| Sinyal üretici (yön → emir) | jarrodwatts, jev-trade, market-reflex, Paperline, jev-fund, Jev Lab | Yasak (K-067); yön ölçüldü ve kapandı (K-076) |
| Boyut/kaldıraç seçici | jev-trade | Tipte yok (`JevKarari` `extra=forbid`, K-074/2) |
| Giriş kapısı / veto | QuantDinger, moomoo, Paperline (güven kapısı) | Açılmadı (K-074/1 spec D; K-077 headroom yok) |
| Yargı sağlayıcı (policy kodda) | buberlo, signals-lab | Kısmen: yargılar var, policy yok (tüketici yok) |
| Sınıflandırıcı / tahmin | jev_stock | Gölge yönü aynı biçimde ölçülüyor (4 bar ufuk) |
| İşlem filtresi (örnek işlemlerle) | UditJain | Yok; K-039 sayımı dışı deney kalıbı |
| Risk değerlendirici (data/execution kalitesi) | QuantDinger | Kodda (Tazelik, sembol kuralları, K-074/4) |
| Araştırma yönetişimi | — | **Yalnız ScryneQuant**: gizli tekrar dedektörü (K-061), kaynak elemesi (K-067/2) |

## 6. State/Input Patterns

- **Ham kitap/tape + dizi** (jarrodwatts `recentMids` string'i, 5 seviye kitap, son işlemler):
  sayısal kıyası modele bırakıyor. ScryneQuant Spike 7 bunun riskini ölçtü (zirveye %1,02 uzakken
  "%1'den yakın" → 0,86) ve K-074/4 ile dışladı.
- **Kompakt kod-hesaplı durum** (buberlo "<400 token", jev_stock tablo tabanlı, ScryneQuant
  etiketler): hesap kodda, yorum Jev'de. ScryneQuant'ın durumu daha büyük (≈2.059 token) ama
  token maliyeti karar başına ≈ $0,00009 ve 1h bütçesinde gecikme p95 403 ms — boyut burada bağlayıcı
  kısıt değil.
- **Etkiler (sorulan beş eksen):**
  - *Leakage*: kompakt durum sızıntıyı önlemez; önleyen şey `t`de kesmedir. ScryneQuant bunu bozma/
    silme testleriyle ölçüyor (negatif kontrol dahil). Dış projelerde bu tür bir test görülmedi;
    jev_stock yalnızca hizalama/kesme kuralı yazıyor. Tarihsel replay'lerde (UditJain hariç — o
    yayın sonrası 7 gün) eğitim kesimi sorunu ele alınmamış; yalnızca Jev Lab `--blind` ile kısmi
    bir önlem deniyor.
  - *Reproducibility*: ScryneQuant `durum_hash` + `SORU_SHA256` (model dahil) + zincir hash'li defter;
    Jev Lab soru/veri hash'li benchmark. Diğerlerinde soru metni sürümlenmiyor.
  - *Latency/token*: mikroyapı projelerinde bağlayıcı (300 ms blok); ScryneQuant'ta değil.
  - *Decision consistency*: ScryneQuant aynı durumu 24 kararda bir ikinci kez soruyor ve sapmayı
    kaydediyor (replay'de medyan 0,03). Dış projelerde tutarlılık ölçümü görülmedi.
- **Few-shot örnek işlemler** (UditJain: 10 kazanan + 10 kaybeden): durumun içine etiketli geçmiş
  koymak; aynı 7 günlük veride 18 varyant. Seçim yanlılığı riski yüksek.

## 7. Risk & Execution Boundaries

**Hard veto var mı?**

| Proje | "Jev BUY → risk NO → emir yok" | Nasıl |
| --- | --- | --- |
| buberlo | Evet | `RiskEngine.check` her emirden önce; öncelik OK<REDUCE_ONLY<HOLD<KILL; drawdown/günlük zarar/API hatası → KILL; pozisyon > tavan → REDUCE_ONLY; bayat veri/gecikme → HOLD |
| Paperline | Evet | Güven/spread/bayat kitap/zaman aşımı kapıları; kilitlenen oturum zararı ve çağrı bütçesi |
| moomoo | Evet | Deterministik kurulum + risk motoru; Jev yalnızca `enforce`'ta ek veto |
| market-reflex | Kısmen | Güven < 0,55 → HOLD; sembol başı tavan |
| QuantDinger | Jev'in kendisi bir veto; ama **Jev yoksa veto da yok** (fail-open) | `ai_decision_filter.py` satır 214–250 |
| jarrodwatts | Zayıf | Tavan yalnız tarafı zorlar ("capped") |
| jev-trade | **Kaynakta bulunamadı** | Pozisyon/notional tavanı yok; Jev kaldıraç seçiyor |

**ScryneQuant karşılığı:** onay üreten tek yer risk motoru (K-037); execution hattı engeller/küçültür
(halt, UNKNOWN, SAFE_MODE, bayat karar, mutabakat, mod tavanı; K-114); pilot kayıp tavanı kalıcı
(K-115). Jev bu zincirin **hiçbir** halkasına ulaşamaz.

**Çelişki notu — "Jev giriş kapısı":** QuantDinger/moomoo deseni yalnızca **engeller** (izin vermez);
bu K-037/K-050'nin asimetrisiyle mimari olarak uyumlu. **Ama bu external pattern mevcut ScryneQuant
kararıyla çelişiyor:** K-074/1 spec D'yi (Jev filtre) açmıyor; K-077 kusursuz bir seçicinin bile kapı
altında kaldığını ölçtü ("filtre için headroom yok"); K-076 Jev'in yönünü %49 ölçtü. Dış tarafta bu
kapıların değer kattığına dair ölçüm **yok** (kanıt: kod var, sonuç yok). ScryneQuant tarafında kanıt
ölçülmüş (K-076/K-077). Karar değişmez; yeniden açmak yeni K + K-051 program kaydı + K-045 sayısal
gerekçesi ister ve bugün filtrelenecek promoted bir strateji zaten yok.

## 8. Evaluation & Calibration

| Proje | Ne ölçülüyor | Veri | Sonuç raporlanıyor mu |
| --- | --- | --- | --- |
| buberlo | (state, decision, outcome) üçlüsü; Brier, log loss, ECE, reliability, Platt | **Sentetik** feed | Hayır (Faz 0) |
| jev_stock | Günlük yön isabeti + çok sınıflı Brier | Tarihsel HK hisseleri — eğitim kesimi öncesi olabilir; README kendisi "retrospective model calls can also benefit from information…" diye uyarıyor | Örnek rapor; CI yok |
| Jev Lab | Benchmark: isabet + aralık, kurala göre lift, ECE; backtest P&L | Tarihsel Yahoo günlük (2 yıl) | Evet; kesim sorunu `--blind` ile kısmen ele alınıyor |
| market-reflex | Gecikme/hata sayımı | 21 çağrı, tek koşu | Yalnız operasyonel; README "not evidence that Jev predicts" diyor |
| moomoo | `jev_reviews.jsonl` sonradan sonuç analizi için | Canlı/simüle | Analiz yok |
| UditJain | Filtreli/filtresiz P&L | SOL 1m, 7 gün (yayın sonrası), 18 deney | `summary.json`; çoklu test düzeltmesi yok |
| **ScryneQuant** | Ön kayıtlı: 1/4/24 bar getiri, MAE/MFE, maliyet sonrası, yön isabeti + Wilson CI, `al_tut` kıyası, Brier/ECE/kovalar, rejim başına, tutarlılık, gecikme, `ileriye_donuk` | Gölge (ileriye dönük) + yayın sonrası 50 sembol replay | **Evet: K-076** — isabet 539/1.099 = %49,0 (CI 0,461–0,520), net −%0,383/işlem (t≈−6,9), kalibrasyon monoton değil |

**Drift:** hiçbir dış projede Jev kararlarının zaman içindeki kaymasını izleyen bir mekanizma yok.
ScryneQuant'ta tutarlılık sorgusu (aynı durum, ikinci soru) + model pini var; **model sürümü
değiştiğinde otomatik yeniden skorlama yok** → §10.

## 9. ScryneQuant Gap Analysis

- **Zaten mevcut (dış desenlerin karşılığı var):** katmanlı mimari ve deterministik durum, atomik soru
  seti, shadow, tazelik, fail-closed, model-bağımsız veto, kilitli kayıp tavanı, kalibrasyon
  ölçütleri, "olasılık ≠ isabet" disiplini, insan onayı. → §13
- **Farklı tasarım (eksik değil):** Jev'in işlem yolunda olmaması; 1h karar frekansı; Jev'e
  portföy/pozisyon verilmemesi; çoklu sembolün tek çağrıda değil sembol başına sorulması (K-076
  bağımsızlık/etkin n analizi bunu gerektirdi).
- **Kısmen eksik:** model sürümü değişiminde sabit bir örnek seti üzerinde otomatik regresyon kontrolü
  (bugün K-061/3 "sürüm kalkarsa yeniden ölç" diyor, ama bunu yapan komut/araç yok). → §10
- **Ölçülmemiş:** eğitim kesimi bilinmediği için tarihsel replay'in ne kadarının hatırlamadan geldiği
  (K-074/3 bunu `leak_riski=true` ile kapatıyor; ölçmüyor). → §11

## 10. ADOPT

**ADOPT-1 · Soru/veri hash'iyle anahtarlanmış sabit örnek seti + model sürümü regresyon kontrolü**

```text
Observation:
Jev Lab her kaydı (model, tarih, veri hash'i, soru hash'i) ile anahtarlıyor; iki koşu yalnız her iki
hash eşleşirse kıyaslanıyor; `npm run check` beyan edilen kapıyı kaçıran ya da aynı testte başlık
metriği 3 puandan fazla düşen koşuda başarısız oluyor. Amaç: aynı testi bir sonraki model sürümünde
koşup neyin değiştiğini görmek.

Evidence:
IslamBaraka90/jev-typesafe-real-financial-use-cases README "Running the suite again" (adım 1–3);
kanıt sınıfı C (yöntem deseni; trading sonucu değil).

Current ScryneQuant state:
Hash tarafı var: `SORU_SHA256` model pinini içeriyor (`jev/sorular.py`), gizli tekrar dedektörünün
soru hash'i testle donmuş (`research/gizli_tekrar.py`), eşikler 2026-09-16 spike'ında ölçüldü
(K-061/1). Eksik olan: `jev-1.13.0` API'den kalktığında (K-061/3, global CLAUDE.md "eski Jev sürümleri
API'den kalkıyor") eşiklerin ve gölge soru setinin yeni sürümde **aynı sabit örneklerle** otomatik
yeniden ölçülmesi.

Potential implication:
R10 (Jev araştırma asistanı / yönetişim) açıldığında, dedektörün bilinen-benzer/bilinen-farklı
örnek seti ve gölge replay örneklemi (`data/semantik/jev/997a12f1390f/`) sürüm değişimi için bir
regresyon kapısına dönüşebilir. İşlem katmanına dokunmaz; K-049/K-067 içinde kalır.

Risk:
Örnek setinin sonuca bakılarak genişletilmesi eşik ayarlamasına dönüşebilir (K-049/2). Set ve
eşikler önceden dondurulmalı; yeni sürümde "geçti" demek yeni bir K ister, otomatik kabul değil.

Recommendation:
ADOPT — R10 kapsamında, R10'un tetiği (R5) geldiğinde; bu turda kod yok.
```

## 11. INVESTIGATE

**INVESTIGATE-1 · Blind replay (sembol/borsa/tarih gizleme + fiyat rebase)**

```text
Observation:
Jev Lab `--blind`: "hides the symbol, exchange and dates and rebases prices so the first close shown
is 100, so decisions can't rely on what the model may remember about an instrument's history."

Evidence:
README satır 135; kanıt sınıfı C. Blind ile blind-olmayan koşuların farkına dair bir sonuç
raporlanmış değil (UNVERIFIED etkinlik).

Current ScryneQuant state:
K-074/3: kesim bilinmediği sürece geriye dönük her türetim `leak_riski=true` ve kapı dışı. K-075:
yayın sonrası barlar temiz. Durum zaten fiyat dizisi değil etiket gönderiyor, ama sembol adı
(`BTCUSDT`) ve bağlam soru metninde var (`_ORTAK`).

Potential implication:
Aynı tarihsel barlar için blind ve açık durumla iki replay → farkın dağılımı modelin hatırlama
katkısının bir **alt sınır** teşhisi olabilir. Bu `leak_riski` kuralını kaldırmaz: fiyat yolu
örüntüsü de hatırlanabilir; gizleme bunu ölçmez.

Risk:
Soru metnini/durumu değiştirmek K-074/7 ve K-076/4'e göre yeni çekiliştir; K-111 araştırmayı askıya
aldı. Teşhis, sinyal aramaya dönüşürse K-039/K-051 ihlali olur.

Recommendation:
INVESTIGATE — yalnızca araştırma askısı (K-111) kalktığında ve bir K-051 programı altında, sızıntı
teşhisi olarak; kapı kanıtı olarak asla.
```

## 12. REJECT

Her biri kaynak koduyla doğrulandı; hepsi "bu projede şimdi" için REJECT, desenin genel değeri
hakkında hüküm değildir.

| # | Desen | Görüldüğü yer | Neden REJECT (kanıt) |
| --- | --- | --- | --- |
| R-1 | Ham kitap/tape + fiyat dizisiyle **her blokta yön sinyali** | jarrodwatts `src/model.ts`, jev-trade, market-reflex, jev-fund | **Çelişki:** K-067 (Jev sinyal üretmez), K-074/1; ölçüm: K-076 yön %49,0; Spike 7 sayısal kıyas hatası (K-074/4). Dış tarafta isabet ölçümü yok |
| R-2 | **Jev'in kaldıraç/boyut seçmesi** | jev-trade `jevQuestions` → `leverage` choice, `parseLeverage` | **Çelişki:** `JevKarari`'nda boyut/kaldıraç alanı yok (K-074/2); K-050 izni artıran otomasyon yasağı; kaynakta pozisyon tavanı bulunamadı |
| R-3 | **Jev giriş kapısı (veto-only) işlem yolunda** | QuantDinger, moomoo `enforce`, Paperline | **Çelişki:** K-074/1 (spec D açılmaz), K-077 (headroom yok), K-076. Mimari olarak K-037'ye uygun; kanıt bugün aleyhte. Promoted strateji ortaya çıkarsa yeniden değerlendirme yeni K + K-051 + K-045 gerekçesiyle |
| R-4 | **Fail-open AI kapısı** / Jev → LLM → izin zinciri | QuantDinger `ai_decision_filter.py` 214–250, `LIVE_TRADING_SAFETY.md` | **Çelişki:** K-074/5 fail-closed; K-114 denetimi execution'daki fail-open davranışları kapattı. Düşük güven bile hataya dönüşüp izne gidiyor |
| R-5 | Jev yokken **mock/heuristik ikamesi** | jev-fund ("falls back to mock"), buberlo deterministik yedek yargı | Ölçüm bütünlüğü: ScryneQuant'ta hata "karar yok"tur ve çekimserlikten ayrı sayılır (`karar.py`); ikame, gölge istatistiğini kirletir |
| R-6 | **Veri/execution kalitesini Jev'e yargılatmak** | QuantDinger `data_quality`, `execution_quality`, `risk_check` | K-074/4: hesaplanabilir olan kodda (Tazelik, `SembolKurallari`, risk motoru); modelin "stale" yargısı ölçülebilir bir kontrolün yerine geçmez (K-019 "ölçülemeyen geçmiş sayılmaz") |
| R-7 | **Jev güveniyle boyut ölçekleme** | market-reflex ($100/250/500 güven bandı), buberlo (düşük güven → küçült) | K-076: güven kovaları isabetle monoton değil; K-074/2 boyut alanı yok. Kalibre olmayan güvenle boyutlamak ölçülmemiş bir kapıdır |
| R-8 | **Jev ile çoklu sembol göreli güç sıralaması / seçim** | market-reflex (3 sembol tek istek), signals-lab `relative strength` sorusu | K-067 (sinyal), K-045 (aynı fiyat bilgisi yeni kaynak değil); K-109 deterministik kesit sinyalleri \|t\|<2; K-077 seçici headroom yok |
| R-9 | **Etiketli örnek işlemleri state'e koyup aynı veride çok sayıda varyant denemek** | UditJain (10+10 örnek, 18 deney a–r, 7 gün) | K-039 (çekiliş sayımı), K-044 (çoklu test düzeltmesi); sayılmayan varyantlar seçim yanlılığı üretir |

## 13. Already Covered

| # | Desen | Dış kaynak | ScryneQuant kanıtı |
| --- | --- | --- | --- |
| C-1 | Deterministik durum → Jev yargısı → kod (policy/risk) | buberlo, moomoo, Paperline | `jev/durum.py` (K-074/4); risk motoru tek onay (K-037); Jev izolasyonu AST (`test_jev_izolasyon.py`) |
| C-2 | Kompakt, kodla hesaplanmış betimleyici durum; sayısal kıyas modele sorulmaz | buberlo, jev_stock | `durum.py` etiketleri; `sorular.py` "sayıları karşılaştırma" talimatı; Spike 7 |
| C-3 | Atomik soru bataryası, tek çağrı, kodda birleştirme | buberlo (6), QuantDinger (6), signals-lab (12) | `sorular.py` 4 soru (Choice/Score/Noul), `SORU_SHA256` donmuş |
| C-4 | Shadow varsayılan, enforce ayrı; incelemelerin journal'ı | moomoo | `jev/golge.py` ayrı süreç, emir yolu yok; zincir hash'li defter `runs/jev/<kosu>.sqlite`; execution SHADOW modu (K-114) |
| C-5 | Karar tazeliği mum kimliğine + azami yaşa bağlı; bayatsa bekle | moomoo `gate_decision`, buberlo blok son tarihi, Paperline `MAX_DECISION_MS` | `karar_ms`, `bayat_ms` 2 bar, `ileriye_donuk`, `BAYAT_DURUM` (`karar.py`, `config/jev.json`); execution'da bayat karar engeli (`hat.py` #9) |
| C-6 | Modelden bağımsız hard veto; öncelik sırası; azaltan geçer | buberlo `RiskEngine`, Paperline, moomoo | `risk/motor.py` 0–8 adım; `execution/hat.py` engel tablosu; K-008/3 |
| C-7 | Kilitlenen (latched) oturum zararı | Paperline `MAX_SESSION_LOSS_USD` | K-115 `azami_kayip_usdt` → SAFE_MODE, her barda yeniden konur (`hat.py`) |
| C-8 | (state, decision, outcome) + Brier/ECE/reliability | buberlo, jev_stock, Jev Lab | `jev/sonuc.py`; tanımlar önceden `config/jev.json::sonuc`; K-076'da uygulandı |
| C-9 | "Olasılık ≠ isabet; güven kalibre değildir" disiplini | jev_stock, market-reflex README | `sonuc.py` docstring (spec §21), yön = olasılık + marj kodda (`karar.py`) |
| C-10 | Canlıya geçişte açık insan onayı | — (dış projelerde yok) | K-010, K-114 `sq execution onayla` (TTY, hash), K-115 |

**NOT RELEVANT (4):**

| # | Desen | Neden |
| --- | --- | --- |
| N-1 | Platt ile Jev olasılıklarını yeniden kalibre edip policy eşiğine bağlamak (buberlo) | Jev çıktısının karar tüketicisi yok (K-074/1); K-076'da kalibre edilecek monoton ilişki yok |
| N-2 | Jev'e pozisyon/portföy/envanter state'i vermek (jev-trade, QuantDinger, buberlo) | Jev'in işlem rolü yok; ölçümü stratejinin durumuna bağlamak gölgeyi kirletir |
| N-3 | Blok başına post-only market making, A-S fiyatlama (jarrodwatts, jev-trade, buberlo) | Farklı venue/frekans (300 ms DEX/perp); ScryneQuant 1h spot, taker, emir defteri verisi yok (R7 envanteri D) |
| N-4 | Model çağrı bütçesi latch'i (Paperline `MAX_MODEL_CALLS`) | Gölge saatte 1 çağrı, ≈ $0,00009/karar; maliyet bağlayıcı değil |

## 14. Implications for Current Phase

**Mevcut fazı değiştirmeyi gerektirmiyor.**

- **R5** (yönetişim, `DECISION REQUIRED` kalemleri): etkisi yok. ADOPT-1 R10'a düşüyor, R10'un ön koşulu
  R5 (ROADMAP-RESET).
- **R8** (operasyon koşusu, gözlem modu, Jev içermiyor): etkisi yok.
- **R9 / K-115 pilot** (execution, Jev içermiyor): etkisi yok. Dış projelerdeki en güçlü güvenlik
  dersleri (fail-closed, model-bağımsız veto, kilitli kayıp tavanı, tazelik) zaten uygulanmış.
- **K-111 araştırma askısı:** INVESTIGATE-1 yalnızca askı kalkınca bir program adayı; askıyı
  kaldıracak bir kanıt değil.
- **K-067/K-074/K-076/K-077:** hiçbir dış proje bunları çürütecek bir ölçüm sunmuyor (dış tarafta
  ileriye dönük isabet ölçümü yok).

## 15. Open Questions

1. **Jev eğitim kesimi** hâlâ UNKNOWN (`config/jev.json::egitim_kesim_utc = null`); hiçbir dış proje
   bunu çözmüş değil. TypeSafe'in resmi beyanı gelmedi.
2. **`golge-1` sonuçları:** gölge 2026-09-19'da hostta başladı; ≥8 günlük pencere 2026-09-27 civarı
   doluyor. K-074/7 tablosu henüz doldurulmadı. Bu denetim host'a dokunmadı (K-069).
3. **jev-trade canlı fill iddiası** (jev-trade.com): UNVERIFIED — kod var, gerçek işlem kaydı
   incelenmedi.
4. **QuantDinger Jev kapısının üretimde ne sıklıkla fail-open'a düştüğü:** kod davranışı belli,
   operasyonel sıklık bilinmiyor.
5. **buberlo "<400 token" iddiası** ve canlı Jev modunda Faz 1 kabul kriterleri: UNVERIFIED (PLAN.md
   Faz 1 işaretsiz).
6. **Paperline'ın orijinal reposu** (`rnjsxodyd90/jev-trading-bot`) 404; incelenen içerik aynı
   sahibin `jev-trading-bot-fork-backup` reposu.
7. **K-077'nin koşulu:** "headroom yok" sonucu promoted strateji olmadığı için bağlayıcı. Bir gün
   promotion'u geçen bir strateji çıkarsa, veto-only Jev kapısının (R-3) yeniden sorulması gerekip
   gerekmediği açık — ama bu, o gün yeni bir K ile açılır.
8. **Blind replay'in** hatırlama katkısını ne kadar ölçebildiği: dış tarafta sonuç yok (INVESTIGATE-1).

## 16. Sources

- Gist: https://gist.github.com/drillan/6916b16e8ea31a8ec36c8f59d6483150
- https://github.com/jarrodwatts/jev-trader
- https://github.com/aowang-ai/jev-trade · canlı masa (doğrulanmadı): https://www.jev-trade.com/
- https://github.com/OpenByteInc/QuantDinger (`backend_api_python/app/services/ai_decision_filter.py`,
  `docs/trading/LIVE_TRADING_SAFETY.md`)
- https://github.com/buberlo/jev-trader
- https://github.com/zzsong1023/jev-market-reflex
- https://github.com/rnjsxodyd90/jev-trading-bot (404) → https://github.com/rnjsxodyd90/jev-trading-bot-fork-backup
- https://github.com/maxlibin/moomoo-jev-trader
- https://github.com/UditJain2622004/Jev-Trading
- https://github.com/sosopop/jev_stock
- https://github.com/IslamBaraka90/jev-typesafe-real-financial-use-cases
- https://github.com/Gamma-Software/jev-signals-lab
- https://github.com/beto11-gif/jev-trading-backend
- https://github.com/erboland/jev-fund
- https://github.com/Pastorkid/jevTradingBoth, https://github.com/hifizz/jev-finance-benchmark (boş)
- Kapsam dışı (trading değil): simonmesmith/jev-banking77-experiment, adilmoujahid/jev-banking77-demo,
  kyotofin/tax-doc-classifier

---

## Son karar

### Q1 — Mimaride gerçekten yeni bir pattern bulundu mu?

**Hayır, mimari düzeyde değil.** Tekrarlayan sağlam desen (deterministik durum → Jev yargısı → kodda
policy → hard veto → execution) ScryneQuant'ta zaten var; ScryneQuant Jev'i işlem yolundan tamamen
çıkararak daha dar bir tasarım kullanıyor. Yeni olan iki şey **yöntem** düzeyinde: model sürümü
regresyon kontrolü (ADOPT-1) ve blind replay (INVESTIGATE-1).

### Q2 — Bu desenler mimariyi nasıl etkiler?

Mimariyi değiştirmezler. ADOPT-1 R10'un yönetişim araçlarına (gizli tekrar dedektörü eşikleri, gölge
soru seti) bir sürüm-değişimi kapısı ekler; işlem katmanına dokunmaz, K-049/K-067 içinde kalır.
INVESTIGATE-1 yalnızca sızıntı teşhisi olabilir ve `leak_riski` kuralını kaldırmaz.

### Q3 — Mevcut fazın yönünü değiştirecek kadar güçlü kanıt var mı?

**Hayır.** 13 dış projenin hiçbiri A sınıfında değil; hiçbiri Jev kararlarının ileriye dönük
isabetini güven aralığıyla ölçmüyor. ScryneQuant'ın kendi ölçümü (K-076, K-077) aleyhte ve daha güçlü
kanıt sınıfında (ön kayıtlı, yayın sonrası, maliyetli, CI'lı).

### Q4 — Bir sonraki araştırma adımını değiştirmesi gereken bulgu var mı?

**Hayır.** Araştırma K-111 ile askıda; bir sonraki adım R5 kararları ve R8 kapanışı (K-112). R10
açıldığında ADOPT-1 kapsamına alınabilir; INVESTIGATE-1 yalnızca askı kalkarsa ve bir K-051
programı altında.

```text
Current phase impact:
NONE
```

**Gerekçe:** Bulguların 10'u zaten uygulanmış, 9'u mevcut kararlarla (K-067, K-074, K-076, K-077,
K-039, K-050, K-114) çelişiyor ve dış tarafta onları destekleyecek ölçüm yok, 4'ü bağlam dışı; tek
ADOPT ve tek INVESTIGATE mevcut fazın değil, R10 ve askı sonrası araştırmanın konusu.
