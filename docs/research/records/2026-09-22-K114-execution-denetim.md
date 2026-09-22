# K-114 denetimi — execution katmanı adversarial audit

Tarih: 2026-09-22 (UTC). Tür: güvenlik denetimi. Gerçek para yok, canlı emir yok, LIVE açılmadı,
gerçek credential gerektiren test yok (testnet ve sahte taşıma hariç). Kod: `f127920` (denetim öncesi)
→ `c255e94` (düzeltmeler). Testler: `tests/unit/test_execution_adversarial.py`,
`tests/unit/test_live_gate_blokerleri.py`, `tests/unit/test_execution_cli.py`.

## 1. Zincir (koddan)

| Geçiş | Modül / çağrı | Arıza davranışı |
| --- | --- | --- |
| Piyasa verisi | `trader/yurutucu.RestBarKaynagi` → `exchange/binance.BinanceAdaptoru.klines` (yalnız kapanmış bar) | hata → `baglanti_hatasi`, bar yok → karar yok |
| Sinyal | `Yurutucu._karar` → `strategy.on_bar(ctx)`; yalnız son kapanmış bar `AKIS` (K-006/K-028) | `BACKFILL` bar karar üretmez |
| Portföy | `ExecutionHatti.hesap` (sermaye + defter akışı) | borsa okunamazsa `Engel.BAGLANTI` |
| Risk | `RiskMotoru.degerlendir` → `OnayliNiyet` (mühürlü) / `Red` | ölçülemeyen guard = red |
| Execution kapısı | `ExecutionHatti.uygula` (11 engel, `hat.py` tablosu) | yalnız engeller/küçültür |
| Niyet → emir | `EmirMotoru.gonder` (kimlik deterministik, SUBMITTED ağdan önce) | `Gonderilemedi`→FAILED, `Reddetti`→REJECTED, `Belirsiz`→UNKNOWN |
| Adaptör | `PaperBorsa` / `GolgeAdaptoru` / testnet / canlı `BinanceImzaliAdaptoru` (yetki + host) | yazma yetkisiz kurulumda taşımada reddedilir |
| Fill | paper: sonraki bar açılışı; borsa: yanıt `fills` | — |
| Mutabakat | `mutabakat_yap` (başlangıç / her bar / kapanış, aynı fonksiyon) | uyuşmazlık → halt; yapılamadı → artıran emir yok |
| Portföy durumu | `durum.json`, `rapor.json` (+ audit hash) | — |

## 2. Bulgular ve durum

| ID | Önem | Bulgu | Düzeltme | Durum |
| --- | --- | --- | --- | --- |
| AUD-01 | HIGH | Tek canlı koşu kilidi yoktu: iki ayrı canlı süreç her biri kademe sermayesiyle, toplam maruziyet kademenin katı | `Yurutucu.kilitle`: koşu kilidi + global `canli` kilidi | düzeltildi, testli |
| AUD-02 | HIGH | Mutabakat **koşamadığında** (borsa/bozuk yanıt) artıran emirler gidiyordu | `mutabakat_tamam` bayrağı, `Engel.MUTABAKAT`; başlangıçta `False` | düzeltildi, testli |
| AUD-03 | HIGH | `sq execution indir` çalışan süreci etkilemiyordu (runbook acil durum yolu olarak gösteriyordu) | `mod_tavani` her artıran emirde; okunamazsa DISABLED; LIVE tavansız çalışmaz | düzeltildi, testli |
| AUD-04 | HIGH | Kill adaptörü kurulamazsa (anahtar/dosya) komut tamamen patlıyordu: işaret ve süreç sonlandırma yapılmıyordu | adaptör hatası yakalanır, işaret + süreç her durumda, rapor başarısız | düzeltildi, testli |
| AUD-05 | MEDIUM | `SUBMITTED` + borsada FILLED (yanıt yazılmadan ölüm) → halt; modülün kendi tablosuyla çelişki (fail-closed yönünde) | önce ACK sonra borsanın durumu | düzeltildi, testli |
| AUD-06 | MEDIUM | Bayat karar kontrolü yürütücüden totolojik çağrılıyordu (`son_kapali_bar_ms=bar.open_time`) | gönderim anında borsa saatinden | düzeltildi, testli |
| AUD-07 | MEDIUM | LIVE onayı yalnız mod dosyasına dayanıyordu; zinciri yeniden hesaplanmış sahte onay satırı yetki üretebilirdi | onay satırı global audit'le iki yönlü doğrulanır; audit yoksa kapalı | düzeltildi, testli |
| AUD-08 | MEDIUM | Kanıt dosyaları (rapor/kill) düz JSON, elle düzenlenebilir | hash'leri koşu audit zincirinde; çapasız kanıt sayılmaz | düzeltildi, testli |
| AUD-09 | MEDIUM | Onay belirli bir API anahtarına bağlı değildi | anahtar kontrolü kanıtı `createTime` taşır | düzeltildi, testli |
| AUD-10 | MEDIUM | Yetki host'a bağlı değildi (başka host'a anahtar gönderilebilirdi) | yetki host alanı + adaptörde eşitlik; serileştirilemez | düzeltildi, testli |
| AUD-11 | LOW | Kâr birikince emir boyutu sermaye/kademe tavanını aşabiliyordu (docstring aksini söylüyordu) | boyut tabanı ≤ sermaye | düzeltildi, testli |
| AUD-12 | LOW | Hat kayıp izleyicisi yalnız emir denemesinde güncelleniyordu | her bar | düzeltildi |
| AUD-13 | LOW | Paper: aynı bar yeniden işlenirse emir kendi karar barının açılışından dolabiliyordu | `transactTime` kuralı; her bardan sonra durum yazımı | düzeltildi, testli |
| AUD-14 | LOW | Halt'lı / SAFE_MODE'lu koşuyu kapatmanın yolu yoktu (live gate kalıcı kapalı) | `sq execution kosu-kapat` (koşu bir daha başlamaz) | düzeltildi, testli |
| AUD-15 | LOW | `safe-kaldir` audit'e yazmıyordu | audit olayı | düzeltildi |
| AUD-16 | LOW | Salt okunur / yalnız-iptal adaptör host'a bağlı değil (yalnız `canli.py` kurar) | — | açık, kasıtlı kod gerektirir |
| AUD-17 | LOW | Bayat `kosu.pid` başka bir süreci işaret edebilir (Faz 14 `live/kill` ile ortak) | — | açık |
| AUD-18 | INFO | Uzun süre açık kalan emir için otomatik iptal/alarm yok; yeni emir `ACIK_EMIR` ile bloklu (fail-closed) | — | açık |
| AUD-19 | INFO | R8 kapanış doğrulaması için kod yok; hash CRLF normalize edilmeli (`r8_kriter_sha256`) | — | açık, K-112'de uygulanmalı |

## 3. Değişmeyenler

R8 yolu (`src/scryne_quant/live`) ve `config/r8_kriterler.json` K-111'den (`dd66452`) beri git diff'te
değişmedi (testli). R8 çalışma zamanı modüllerinin import kapanışı yeni execution paketlerine ulaşmıyor
(testli; CLI kabuğu `cli/main.py` hepsini kaydeder ama çalıştırmaz). Execution/trader/exchange
`research`i import etmiyor, promotion/hipotez yazan çağrı yapmıyor (AST testli). Defter 62.

## 4. Sırlar

`.env` `.gitignore`'da ve git geçmişinde hiç yok. `.env`deki 5 değer için tarama: git geçmişi (tüm
commit'ler), HEAD'deki izli dosyalar, `runs/` altındaki bütün dosyalar, oturumun test/log çıktıları — 0
eşleşme. Hata mesajları ve adaptör `repr`i anahtar/sır taşımıyor (testli). Pano yalnız `durum.json`,
mod kaydı, preflight ve audit okur; bu dosyalarda sır alanı yok (testli).
