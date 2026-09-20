# W2 — Trading Engine + Risk + Execution

**Tarih:** 2026-09-20 · **Baseline:** `1e1a05b` · **Kod değişikliği:** yok (risk/execution koduna
dokunulmadı; brief §6 sınırı) · **Okunan:** `risk/{motor,niyet,limitler,promotion,muhur}`,
`execution/{kapi,motor}`, `oms/{emir,mutabakat,pozisyon}`, `exchange/imzali`, `live/{motor,
toparlanma,kill,izgara_toplayici,evren_kosturucu,evren_kurulum}`, `backtest/fill`,
`config/risk.json`, `runs/promotion/*.json`, Faz 5/7 raporları, K-073.

Etiketler: **VERIFIED** (kodda görüldü + testi var) · **PARTIAL** · **UNKNOWN** · **RISK**
(bugün zarar vermiyor, koşullar değişince verir) · **BLOCKER** (canlıya geçişi engeller).
Brief §13 checklist'i başlık olarak kullanıldı.

---

## 0. Özet

Risk/execution katmanı bu projenin **en olgun** parçası: karar sırası yazılı ve testli, onay
tek yerden çıkıyor ve HMAC mühürle taşınıyor, execution kapısı mührü yeniden doğruluyor,
emir motoru "önce yaz sonra gönder" + deterministik idempotency anahtarı + üç sınıflı hata
ile gerçek testnet'e karşı ölçülmüş (100/100, kesinti senaryoları). Toparlanma **yeniden üretim**.
Kill switch süreç dışı ve raporlu.

Buna karşılık dört yapısal nokta var, hiçbiri "hata" değil ama üçü canlıya geçişten önce
kapanmak zorunda:

| # | Bulgu | Sınıf |
| --- | --- | --- |
| B1 | Paper/evren motorlarından borsaya giden emir yolu **yok**; `EmirMotoru` yalnız `cli/testnet` | BLOCKER (Faz 8 için, bilerek) |
| B2 | **Araştırma backtest'leri risk motorsuz** (`risk=None`), canlı evren risk motorlu (K-073) → 52 çekilişin kapı sonuçları risk katmanı olmadan üretildi | RISK (W3'te sayısal etkisi) |
| B3 | Risk limitleri BTCUSDT 1h'den kalibre (`volatilite_esigi` = BTC ATR/fiyat p99) ve **evren-geneli tek eşik** olarak uygulanıyor | RISK (çok varlıkta yanlış) |
| B4 | Promotion kaydı düz, bütünlük korumasız JSON (`runs/promotion/*.json`, git dışı); `live` modu bu dosyayı okuyarak açılır | RISK (canlıdan önce) |
| B5 | `AZALTAN_YONLER = {SELL, FLAT}` sinyal **yönünden** türüyor, pozisyondan değil — long-only spotta doğru; short/perp eylem uzayında **her kontrolü atlayan** bir yol olur | RISK (eylem uzayı genişlerse) |

## 1. Sinyal → Risk → Onay

| Kontrol | Durum | Kanıt |
| --- | --- | --- |
| Onay tek yerden çıkar (`RiskMotoru.degerlendir` / `portfoy_degerlendir`) | VERIFIED | `risk/motor.py:262,415`; `test_risk_bypass.py` (18) tip + mühür + import kesme |
| Karar sırası sabit: azaltan → ölçüm geçerli → SAFE_MODE → promotion → drawdown(kill) → günlük zarar → cooldown → volatilite → boyut | VERIFIED | `risk/motor.py:280-413`, docstring sırayı gerekçelendiriyor |
| Boyutlandırma yalnız **aşağı** (iki tavan: `azami_maruziyet`, `islem_basina_risk / (ATR×çarpan)`) | VERIFIED | `motor.py:540-568`; `test_risk_limitleri.py` (55) |
| Portföy düzeyi: brüt maruziyet yalnız artıranları kısar, mevcut pozisyonu zorla satmaz; enstrüman sayısı yalnız yeni girişleri eler | VERIFIED | `motor.py:470-538`; `test_risk_portfoy.py` (17) |
| Kayan nokta sınır davranışı (çarpmayla karşılaştırma, sınır dahil) | VERIFIED | `motor.py:320-330` |
| Mühür: süreç başına rastgele HMAC, hash'lere girmez, `kapi.gonder` ve `istemci_kimligi` yeniden doğrular | VERIFIED | `risk/muhur.py`, `execution/kapi.py:54`, `oms/emir.py:235` |
| Drawdown yalnız **sinyal geldiğinde** kontrol ediliyor (`bar_isle` yalnız durum günceller) | PARTIAL | `motor.py:185-192` gerekçeli (audit "hangi sinyal sırasında" istiyor). Sonuç: sinyalsiz uzun drawdown'da KILL olayı ve alarm **gecikir**; giriş zaten olmadığı için maruziyet artmaz. Canlıda izleme alarmıyla (`live/izleme`) telafi ediliyor mu → W7 |
| Risk durumu (zirve, gün başı, ardışık kayıp, cooldown, SAFE_MODE) toparlanmada **bağımsız kaynaktan doğrulanamıyor** | PARTIAL | `live/toparlanma.py` başlığı bunu açıkça yazıyor; yazım atomik + `synchronous=FULL` |
| Volatilite guard "ölçülemeyen = geçilmemiş" | VERIFIED | `motor.py:388-392` |
| **B5** azaltan niyet = `side ∈ {SELL, FLAT}`; pozisyon var mı bakılmıyor | RISK | `risk/niyet.py:78`; spot fill katmanı `POZISYON_YOK` ile satışı atlıyor (`backtest/fill.py:225`) — bugün güvenli, short açıldığında değil |
| **B3** limitler tek sembolden kalibre, evren geneline uygulanıyor | RISK | `config/risk.json` `veri_sha256` = BTCUSDT; K-073 "Ölçülenler" risk katmanının evrende neyi elediğini ölçmüş, kalibrasyon pencere sonrasına bırakılmış |
| Limit değişikliği izni artıran yönde kapı + elle onay ister | VERIFIED (kural) / UNKNOWN (zorlama) | K-050; `sq risk limitler` yalnız okur; `yaz()` var — hangi komut çağırıyor ve elle onay nasıl kanıtlanıyor → W7 |

## 2. Portföy kurma ve boyutlandırma

- Tek sembol: `Sinyal.target_exposure` → risk tavanları → `hedef_maruziyet`. VERIFIED.
- Evren: `HedefPortfoy` (strateji) → `strategy/kurma.py` ağırlık → `portfoy_degerlendir` her
  sembol için 0-8 adım + portföy kısıtları → `PortfoyKarari`. VERIFIED (`test_risk_portfoy`).
- **Araştırma yolunda risk motoru yok (B2).** `CokluBacktest(risk=None)` üç araştırma kurulum
  noktasında (K-073 tablosu). Yani Faz 10-16'nın bütün evren çekilişleri **risk katmanı
  olmadan** ölçüldü; canlı gözlem koşuları (`evren_kurulum.py:79`, `mod="gozlem"`) risk
  motorlu. K-073 bunu "kod hatası değil, karşılaştırılabilirlik uyuşmazlığı" diye kaydetmiş ve
  pencere sonrasına bırakmış. W3 için soru: risk motorlu backtest'te 52 çekilişin kapı durumu
  değişir mi? (K-073 §Ölçülenler: risk katmanı `evren-kiyas`ta bir şeyler eliyor — sayı orada.)
- `hedef_brut 0.2`, `azami_agirlik`, asgari ağırlık `0.005` — ölçülmemiş varsayılanlar
  (state.json K-072 açık kalemi). UNKNOWN → Threshold-Policy'e `DECISION REQUIRED`.

## 3. Emir oluşturma, doğrulama, gönderim (testnet yolu)

| Kontrol | Durum | Kanıt |
| --- | --- | --- |
| Sıra: kimlik→defter sor→kurallara uydur→CREATED/VALIDATED→**SUBMITTED diske**→gönder→sonuç | VERIFIED | `execution/motor.py` başlık + `gonder` (168-253); `test_oms.py` (28) |
| İdempotency anahtarı: niyet içeriğinden deterministik (mühür hariç), restart'ta aynı | VERIFIED | `oms/emir.py:220-245`; testnet'te gerçek borsa `-2010` ikinci katman (Faz 7 §2) |
| Duplicate: aynı niyet ikinci kez → ağ çağrısı **yok** | VERIFIED | Faz 7 §2, `test_mutabakat::TestDuplicate` |
| Sembol kuralları (tick/step/minNotional), deftere **gönderilebilir** miktar yazılır | VERIFIED | `exchange/kurallar.py`, `motor.py:305` |
| Hata sınıfları: `GonderilemediHatasi→FAILED`, `BorsaReddetti→REJECTED`, `BelirsizSonuc→UNKNOWN` (yalnız mutabakat, asla yeniden gönderim), `SaatSapmasi→FAILED + koşu durur` | VERIFIED | `motor.py` tablo; Faz 7 §3 iki `ReadTimeout` senaryosu gerçek borsaya karşı |
| Yazma isteklerinde yeniden deneme **yok** | VERIFIED | `imzali.py:88,268` |
| İptal: kayıt yanıt **sonrası**; `-2011` → sorgula | VERIFIED | K-047, `test_limit_iptal.py` (19) |
| Kısmi dolum: `PARTIALLY_FILLED` state machine'de, iptal edilebilir, dolan kısım defterde | VERIFIED (birim) / PARTIAL (gerçek) | `oms/emir.py:120-204`; testnet yük koşusu 100/100 FILLED — kısmi dolum **gerçekte gözlenmedi** |
| Rate limit: 418/429 → `BorsaReddetti` (geri çekilme yok, yazma yolunda doğru); okumalar ccxt `enableRateLimit` | VERIFIED | `imzali.py:349`, `binance.py:106` |
| Saat: `recvWindow=5000`, imza zamanı borsadan, `-1021`'de dur | VERIFIED | Faz 7 §4; `test_imzali.py` (23) |
| Canlı host tanımsız; yalnız `TESTNET_HOST` | VERIFIED | `imzali.py:67-69` |
| **B1** paper/evren → `EmirMotoru` bağlantısı yok | BLOCKER (Faz 8) | W1 §2.1; `EmirMotoru(` çağrıları yalnız `cli/testnet.py` |
| Execution kapısı evren yolunda **çağrılmıyor** (yalnız `PaperMotoru._karar_ver`) | PARTIAL | `grep execution_gonder` → `live/motor.py:49` tek; `coklu_motor` `portfoy_degerlendir` sonrası doğrudan fill. Faz 8'de evren yolu da kapıdan geçmeli |

## 4. Mutabakat ve pozisyon

| Kontrol | Durum | Kanıt |
| --- | --- | --- |
| Emir mutabakatı: defter vs borsa, uyuşmazlıkta `Uyusmazlik` → halt | VERIFIED | `oms/mutabakat.py:130-165`; Faz 7 §1 (5 ara mutabakat temiz) |
| Pozisyon mutabakatı: değişmez açılış çıpası + defter akışı vs borsa bakiyesi; açıklanamayan fark → durur | VERIFIED | `oms/pozisyon.py:223-286` (K-046); Faz 7 §9.1 EmirMotoru dışından gönderilen market emri yakalandı |
| Komisyon (BNB/varlık) açıklaması | VERIFIED | `oms/emir.py:70`, `komisyon_yaz` |
| Gerçeğe karşı **açık pozisyonla** toparlanma | UNKNOWN | Faz 8 ön koşulu 5; state.json "25 Eylül senkron restart'ında ölçülebilir" |
| Uzun süreli dayanıklılık (günler) testnet'te | UNKNOWN | Faz 7 §7 "açık" |

## 5. Bayat/eksik veri, zaman

| Kontrol | Durum | Kanıt |
| --- | --- | --- |
| Tek sembol: `Tazelik` barın nabzından **önce** ölçülür; bayatsa yeni giriş yok, azaltan geçer | VERIFIED | `live/motor.py:250-260,387-390`; `test_canli_akis.py` (27) |
| `ok` olmayan bar (BACKFILL/REST_RESYNC) → fill iddiası yok, karar yok | VERIFIED | `motor.py:270-280` (K-028) |
| Aynı barın revizyonu → `MotorHatasi` (duplicate kararın Faz 6 hâli) | VERIFIED | `motor.py:264-268` |
| Evren: eksik sembol `bekleme_ms`(120 s) sonra "mevcut değil"; geç bar kararı değiştirmez, sayılır; sıra korunur | VERIFIED | `live/izgara_toplayici.py` başlık; `test_izgara_toplayici.py` (8) |
| Evren: **tüm akışın** ölmesi (hiç bar yok) | PARTIAL | Toplayıcı hiç `t` teslim etmez → karar yok; alarm `live/izleme` (K-069 kaydı 4× WS CLOSED) — kesinti sonrası yeniden bağlanma ölçümü var, "sessiz ölüm" eşiği W7 |
| Zaman: UTC ms, bar = açılış, `t+1` açılışta fill; risk motoru duvar saatine bakmaz | VERIFIED | `common/zaman.py`, `backtest/fill.py`, `motor.py` başlık |
| Isınma barları `BACKFILL` → geçmişte fill imkânsız | VERIFIED | `live/baslat.py` başlık |

## 6. Restart / toparlanma / kill

| Kontrol | Durum | Kanıt |
| --- | --- | --- |
| Toparlanma = yeniden üretim + karşılaştırma; portföy fill defterinden, bekleyen karar strateji+risk'ten yeniden türetilir; ayrışmada durur | VERIFIED | `live/toparlanma.py:113-160`; `test_toparlanma.py` (22) |
| Tek yazıcı kilidi + pid dosyası | VERIFIED | `live/kilit.py`, `kill.py:70-93` |
| Süreç dışı kill: `.safemode` işareti → `TerminateProcess` → açık emir iptali + doğrulama → `.kill.json` raporu; restart SAFE_MODE'da açılır; kaldırma elle+gerekçe | VERIFIED | `live/kill.py`; `test_kill_sureci.py` (10), `test_kill_switch.py` (23); tatbikat `tools/faz14_kill_tatbikati.py` (K-065) |
| Kill **Windows'a bağlı** (`ctypes.WinDLL("kernel32")`, POSIX dalı `os.kill(pid, 9)`) | PARTIAL | `kill.py:142,158`; host Windows — taşınabilirlik notu, hata değil |
| SAFE_MODE'dan kod içinden çıkış yok (statik test) | VERIFIED | `motor.py:238` docstring, `test_kill_switch.py` |
| Düzgün durdurma bayrağı (`*.dur`) | VERIFIED | `live/durdurma.py` |

## 7. Sırlar ve ortam ayrımı

| Kontrol | Durum | Kanıt |
| --- | --- | --- |
| Testnet anahtarı ayrı adla (`SQ_BINANCE_TESTNET_*`), ortam → `.env` sırası; canlı işlem anahtarı (`SQ_BINANCE_API_*`) **tanımlı değil, üretilmemiş** | VERIFIED | `imzali.py:75-76,124-153`; `.env` yerelde: testnet ✓, FRED ✓, `BINANCE_API_KEY` (salt okunur) ✓, `SQ_BINANCE_API_KEY` ✗ (yalnız ad kontrolü yapıldı, değer okunmadı) |
| Salt okunur canlı anahtarın yetkileri ölçülür (`apiRestrictions`: çekim/transfer kapalı; işlem yetkisi raporlanır) | VERIFIED (araç) / UNKNOWN (son çıktı) | `tools/faz14_anahtar_denetimi.py`; Spike 8 "enableSpotAndMarginTrading=false" — çıktı dosyası bu dalgada açılmadı |
| `.env` git dışı, `.gitignore` çift kapsam; `*.key/*.pem/secrets/` | VERIFIED | `.gitignore` |
| Jev istemcisi hata metinlerinden 6 anahtar adını temizler | VERIFIED | `jev/istemci.py:31-41` |
| Anahtar hiçbir loga/rapora yazılmaz | PARTIAL | Kod niyeti açık; log denetimi (structlog çıktıları) yapılmadı → W6/W7 |
| Paper/gözlem/live izolasyonu: `PaperMotoru` `live` reddeder; `RiskMotoru.mod == kimlik.mod` zorunlu; `MOD_ESIGI["live"]=LIVE` | VERIFIED | `live/motor.py:162-172`, `promotion.py:96-101`, `test_gozlem_modu.py` (13) |
| Evren canlı koşuları **`gozlem`** modunda sabit (`evren_kurulum.py:79`) → promotion kanıtı üretmez (K-035) | VERIFIED — sonuç: çok sembollü bir aday için `paper` modu koşusu **henüz mümkün değil** (kurulum modu parametreli değil) | W7'ye |
| **B4** promotion kaydı düz JSON, hash/zincir yok, git dışı; `elle_onayla` yalnız ≥10 karakter not ister | RISK | `runs/promotion/sma_kesisim.json`; `promotion.py` içinde `hash/hmac/zincir` yok; `risk/audit.py` zincir hash'li iken bu defter değil |

## 8. Checklist özeti (brief §13)

| Alan | Madde | Sonuç |
| --- | --- | --- |
| Data | timestamp bütünlüğü · eksik · duplicate · bayat · kötü tick · seans · timezone · takvim | ✅ ✅ ✅ ✅ ✅(kalite bayrakları) · **yok (24/7)** · ✅ UTC · **yok** |
| Execution | spread · slippage · gecikme · kısmi · red · duplicate · retry · idempotency · mutabakat | spread **modellenmiyor** (tek `slippage_bps`) · ✅ · ✅(saat) · birim · ✅ · ✅ · ✅(yalnız okuma) · ✅ · ✅ |
| Risk | max pozisyon · maruziyet · kaldıraç · drawdown · günlük zarar · konsantrasyon · korelasyon · acil durdurma | ✅ · ✅ · **yok (spot, ≤1.0)** · ✅ · ✅ · ✅(sayı, bağlamıyor) · **yok** · ✅ |
| Ops | API hatası · borsa kesintisi · rate limit · restart · state recovery · sır sızıntısı · saat kayması · izleme hatası | ✅ · ✅(WS→REST) · ✅ · ✅ · ✅ · ✅ · ✅ · PARTIAL (W7) |

## 9. Testlerin kanıtladığı (W6 derinleştirir)

- `test_risk_bypass` (18): `OnayliNiyet` mühürsüz kurulamaz; `execution/oms` geçişli grafikte
  `strategy.sinyal` yok; sahte mühür `kapi.gonder`da düşer.
- `test_risk_limitleri` (55): sekiz limit × ihlal/ihlal-olmayan; `risk.json` ↔ `kapilar.py`
  drawdown tutarlılığı.
- `test_kill_switch` (23) + `test_kill_sureci` (10): K-008'in beş davranışı; süreç dışı kill'in
  üç adımı ve raporu; `serbest_birak` kod içinden çağrılmıyor (statik).
- `test_promotion` (34): sıra atlanamaz; `dirty`/`data_quality_warning` geçemez;
  `ASGARI_PAPER_GUN=30`.
- `test_mutabakat` (26), `test_pozisyon` (20), `test_oms` (28), `test_limit_iptal` (19),
  `test_imzali` (23): §3-4.
- `test_toparlanma` (22), `test_paper_dongu` (19), `test_canli_akis` (27): §5-6.
- Gerçek borsaya karşı: Faz 7 `faz7-100.json`, kesinti senaryoları, K-046/K-047 koşuları
  (`runs/testnet/`, git dışı; sayılar raporda).

## 10. Canlıya geçiş öncesi (Faz 8) bu dalgadan çıkan zorunlu kalemler

Hiçbiri bu denetimde yapılmadı; hepsi **APPROVAL REQUIRED** (brief §6).

1. B1: paper/evren motorlarını `EmirMotoru`'na bağlayan kod + shadow (`GolgeAdaptoru`) — tasarım
   `docs/Faz-8-Hazirlik.md`'de var, kod yok.
2. Evren yolunun `execution/kapi.gonder`dan geçmesi (§3 son satır).
3. B4: promotion defterine bütünlük (zincir hash ya da imza) — `risk/audit.py` kalıbı hazır.
4. B5: `AZALTAN_YONLER` kararının pozisyon bilgisine bağlanması, eylem uzayı genişlemeden önce.
5. B2/B3: araştırma yolunun risk motorlu koşulması ve limitlerin evren-geneli kalibrasyonu
   (K-073 pencere sonrası ölçümü) — bu, W3'ün ilk sorusu.
6. Evren kurulumunun `paper` modunu desteklemesi (bugün `gozlem` sabit).
7. Canlı işlem anahtarı, IP kısıtı, venue hukuki statü kaydı (`Faz-8-Hazirlik.md` §1.6, §5) —
   COMPLIANCE REVIEW REQUIRED.

**Sonraki dalga:** W3 — Backtest / Research (B2'nin sayısal etkisi, `sonuc_hash`↔veri sonu,
eşik bayatlığı, tek global maliyet modeli).
