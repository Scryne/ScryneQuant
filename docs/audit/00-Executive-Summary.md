# 00 — Executive Summary (Denetim Özeti)

**Tarih:** 2026-09-20 · **Baseline:** `1e1a05b` (brief'teki `86d3f4d` bayattı) · **Dalgalar:**
W0-W8 (`docs/audit/`), `docs/research/Threshold-Policy.md`, `docs/ROADMAP-RESET.md`.
**Kod değişikliği:** sıfır. Denetim boyunca koşulan komutlar salt okunur (pytest ×2, ruff,
`sq lab dogrula` ×18, sha256sum, süreç listesi). Uzak hosta bağlanılmadı (K-069).

Etiket sözlüğü: **VERIFIED** kodda görüldü + testi/ölçümü var · **PARTIAL** · **UNKNOWN** ·
**RISK** koşul değişince zarar verir · **BLOCKER** · **DECISION REQUIRED** · **APPROVAL REQUIRED**
· **COMPLIANCE REVIEW REQUIRED**.

---

## Tek paragraf

ScryneQuant, 12 günde 136 commit'le kurulmuş, **çalışan ve olağanüstü iyi belgelenmiş** bir
tek-venue (Binance spot) kripto araştırma + paper/testnet platformu. Deterministik güvenlik
sınırları (strateji izolasyonu, risk-tek-onay, execution kapısı, Jev izolasyonu) **kodla ve
negatif kontrollü AST testleriyle kanıtlı**. Bugünkü sorun altyapı değil: (1) "kayıttan yeniden
üretilebilir" iddiası **bugün kırık** (0/16), (2) araştırma uzayı mevcut eylem uzayında **kapalı**
(52 çekiliş, 0 geçen, maliyet-sıfırda bile) ve brief'in çok varlık evreni için **sıfır** veri/
adaptör/takvim/maliyet var, (3) canlıya giden yolda eksik olan strateji değil üç kod kalemi +
insan kararları. Yeniden yazma gerekmiyor; gereken, tekrar üretilebilirliği onarıp çok varlık
alan modelini mevcut dört tipin (`Enstruman`, `VeriSozlesmesi`, `SembolKurallari`,
`MaliyetModeli`) ayrıştırılmasıyla kurmak.

## Ne gerçekten çalışıyor? (VERIFIED)

- **Sınırlar:** K-003 (strateji I/O yok), K-032 (execution sinyale dokunamaz, HMAC mühür,
  kapıda yeniden doğrulama), K-074 (Jev işlem katmanına ulaşamaz) — hepsi AST testli, CI'da.
- **Risk motoru:** yazılı karar sırası, yalnız aşağı boyutlandırma, portföy kısıtları, kill
  switch (K-008 beş davranış), süreç dışı kill (K-065, raporlu), 55+23+18+17 test.
- **Execution/OMS (testnet):** önce diske yaz sonra gönder, deterministik idempotency, üç
  sınıflı hata (UNKNOWN → yalnız mutabakat), pozisyon mutabakatı; gerçek testnet'te 100/100,
  kesinti senaryoları, K-046/047 ölçümleri.
- **Veri:** Parquet deterministik yazıcı (süreçler arası bayt-aynı), PIT evren (hayatta kalma
  yanlılığı ölçüldü %16,7-18), `available_time` kesmesi, ALFRED vintage, kimlik kırılması.
- **Backtest:** tek motor (tek sembol = özel hâl, statik testli), Decimal bağımsız referans,
  look-ahead testi **hileli stratejiyi yakalıyor**, canlı ≡ backtest 0,0 bps (K-073).
- **Araştırma yönetişimi:** ön kayıtlı defter (52), program bütçesi (10), 500 denemelik
  sızıntısız null, DSR/Bonferroni çapraz kontrol, null-kalibre v2 kapıları, kıyas ayarlanmaz.
- **Operasyon:** toparlanma = yeniden üretim, 15 alarm kodu + Runbook satırı, ntfy, yedek +
  tatbikat, salt okunur pano, SSH-anahtar host.
- **Test/CI:** 1.845 test yeşil (2 koşu), ruff temiz, flaky yok.

## Ne kısmen çalışıyor? (PARTIAL)

- **Paper trading:** altyapı tam, ama promotion kanıtı üreten `paper` modlu koşu **hiç
  yapılmadı**; en uzun koşu 4,3 gün / 5 kesinti / 0 fill; evren kurulumu `gozlem`a sabit.
- **K-001 tek kod yolu:** evren yolunda tam (`CokluAdimci`), tek sembol paper'da döngü ayrı.
- **Execution kapısı** yalnız tek sembol paper yolunda çağrılıyor.
- **İzleme:** izleyen ölürse ikinci bağımsız kanal yok (yalnız "özet gelmedi").
- **Toparlanma:** risk durumu bağımsız kaynaktan doğrulanamıyor (dürüstçe belgelenmiş); açık
  pozisyonla gerçek toparlanma ölçülmedi (25 Eylül).
- **Hipotez defteri:** ön kayıt var, **sonuç/karar alanı yok**; sonuçlar `runs/` (git dışı) +
  anlatısal raporlarda.

## Ne deneysel?

- Jev gölgesi (yön ekseni kapalı; K-076), kurma katmanı (h51/h52: kıyası geçiyor, Sharpe kapısına
  uzak), Hat 1 carry (RESEARCH_CANDIDATE → DATA_BLOCKED, K-079), K-080 taslağı (commit dışı).

## Ne bilinmiyor? (UNKNOWN)

- GitHub Actions gerçek durumu (repo özel, `gh` yok); uzak host anlık durumu (K-069);
  Jev eğitim kesim tarihi (TypeSafe cevap vermedi); brief §15 evreninin **tamamı** (FX/endeks/
  emtia/ETH-SOL/short/perp: hiçbir kanıt yok — "başarısız" değil, "test edilmedi"); yargı
  alanı/API ToS/vergi; Node bağımlılık kullanımı; log'larda sır (test yok).

## Ne güvensiz? (UNSAFE)

**Bugün hiçbir şey canlı parayla temas etmiyor ve edemiyor** — canlı host tanımsız, işlem
anahtarı yok, `PaperMotoru` `live` reddediyor. "UNSAFE" sınıfı **boş**. Koşul değişince
tehlikeli olacaklar (RISK): `AZALTAN_YONLER` yön bazlı (short açılırsa her kontrolü atlar);
risk limitleri BTC'den kalibre, evrene tek eşik; promotion kaydı bütünlük korumasız JSON;
araştırma risk motorsuz; tek global maliyet modeli altcoinlerde iyimser.

## Ne gereksiz?

- `duckdb`, `structlog` bağımlılıkları (0 import; projede logging çerçevesi yok); APScheduler
  (yalnız dokümanda); `tools/pano.py` (K-069 geçici başlatıcı, 25 Eylül sonrası); `runs/` kök
  logları; boş `research/` klasörü; `.claude/state.json`'daki 4.000 karakterlik anlatı.
- **Bekleme olarak gereksiz:** Faz 15'in "spike koşulu" (bekleme değil, yapılmamış iş).

## Ne silinmeli / emekliye ayrılmalı?

Yukarıdaki gereksizler (onayla). **Silinmemeli:** `migrations/001_faz5.sql` (K-034 ölçülmüş
erteleme, testle hizalı), kapalı strateji aileleri kodu (kayıt yeniden üretimi), faz raporları
(tarihsel; arşivlenir, silinmez), `Proje-Fikri.md` v1.

## Ne korunmalı?

17 değişmez kural ve onları koruyan AST testleri; K-001…079 karar günlüğü (tek adres); ön
kayıt + bütçe disiplini; "ölçülemeyen kapı geçilmiş sayılmaz"; kıyas ayarlanmaz; K-050 asimetri;
Runbook; Decimal referans fixture'ları; `VeriSozlesmesi` (brief §17 provenance'ının çoğunu
zaten taşıyor).

## Ürünleşmeyi ne engelliyor? (BLOCKER)

1. **Tekrar üretilebilirlik** (W3 R1-R3): veri kimliği son bara bağlı, depo uzatılınca 52
   çekiliş + 16 kayıt geçersiz; eşik ölçümü bu yüzden durdu; K-080 yarım.
2. **`paper` modlu koşu yolu yok** (evren için).
3. **Execution bağlantısı yok** (paper → `EmirMotoru`) — Faz 8 kodu, APPROVAL.
4. **Çok varlık için sıfır veri/adaptör/takvim/maliyet** — brief'in hedefi için başlangıç
   noktası.
5. **Promotion geçen strateji yok** — bu bir blocker değil, kapının çalıştığının kanıtı;
   ama R12'nin tetiği.
6. **Venue/compliance kaydı boş.**

## Hemen ne yapılabilir? (bugün, hosta dokunmadan)

K-080'i tamamlamak (K + test + REST karşılığı + defterde `veri_sonu`); `sq lab dogrula` CI
adımı; eşik bekçisini defteri sayar hâle getirmek; eşik yeniden ölçümü; bağımlılık temizliği;
doküman etiketleme + 12 çelişkinin kapatılması; `Enstruman`/maliyet/takvim tip tasarımı;
FX/endeks veri kaynağı + lisans spike'ı; defter §19 alanları; `--mod paper` kurulum parametresi;
frontend denetim pasları; Jev yönetişim aracı tasarımı. (ROADMAP-RESET §2 iz listesi.)

## Gerçekten ölçüm gerektiren ne?

Eşik yeniden ölçümü (null, ~2 s); 52 çekilişin risk motorlu yeniden koşusu (K-073); risk
limitlerinin evren-geneli/enstrüman-başı kalibrasyonu (`volatilite_esigi`, ATR çarpanı);
enstrüman başına slippage/spread (her venue için Spike 4/K-021 kalıbı); hayatta kalma
yanlılığı her yeni sınıfta; embargo etkisinin büyüklüğü; `ASGARI_PAPER_GUN` için fill sıklığı;
açık pozisyonlu toparlanma (25 Eylül); shadow emir sıklığı (tetik gelince).

## Gerçekten insan onayı gerektiren ne?

Threshold-Policy §6 kararları (U13-U17, embargo, `asgari_islem`, deney karar durumları, kurma
parametreleri, paper fill koşulu); execution bağlantısı ve evren kapısı; `AZALTAN_YONLER`;
risk limit kalibrasyonunun gevşeten yönü; promotion defteri biçimi; vadeli/kaldıraç/kripto-dışı
venue (K-079, K-014, compliance); veri lisansları; host senkronu (25 Eylül); canlı aktivasyon
(her zaman, K-010).

## Çok varlık stratejisi nedir?

**Yeniden yazma değil, ayrıştırma.** `Enstruman` (kimlik+geçerlilik) → `+asset_class,
instrument_type, takvim, tick/lot/contract`; `MaliyetModeli` global → enstrüman başına (spread
ayrı, finansman/rollover bacağı); ızgara 24/7 → takvim-farkında; `VeriSozlesmesi` → venue/tip
alanı. Her adımda kripto koşusu **bit düzeyinde aynı** kalır (K-057 kalıbı). Sıra: R2 tipler →
R3 **bir** kripto-dışı sınıf için veri (kaynak/lisans insan kararı) → R4 motor → R5 yönetişim.
Spot/vadeli/CFD/ETF **karıştırılmaz**; kaldıraçlı ürün compliance'tan önce açılmaz. Hedef
evren brief §15; ilk sınıf seçimi veri erişilebilirliği + lisans + takvim basitliğiyle
belirlenir, getiriyle değil (brief §20).

## Alfa araştırması stratejisi nedir?

Mevcut eylem uzayında (Binance spot long-only, fiyat/funding/makro/konumlanma) **kapalı kalır**
(K-078); yeniden çekiliş yok. Açılış yalnız **yeni evren + yeni null + yeni eşik** ile, K-051
program kaydı ve bütçesiyle. Aile sırası kanıta göre: (1) **portföy kurma** (tek olumlu yön:
h51/h52) çok varlık evreninde; (2) çok varlık **trend/momentum** (test edilmedi; aile-özel kapı
seti DECISION); (3) cross-asset/relative value; (4) carry — yalnız K-079 dış koşulları
sağlanırsa. Predictive ML ve olay-güdümlü: veri/lisans kararından sonra program olarak.
Jev: sinyal değil yönetişim. Her sonuç, FAIL dahil, `docs/research/records/`'a.

## En erken kullanılabilir ürün nedir?

**Bugün:** araştırma + backtest + Binance canlı veri + gözlem paper + pano + Jev gölge —
çalışıyor. **R1+R8 sonrası (K-069 kapanışı + 2-3 hafta):** yeniden üretilebilir araştırma +
kanıt üreten `paper` koşusu + tek pano = **kullanılabilir tek-varlık araştırma/paper ürünü**,
strateji olmasa da (kıyas, veri kalitesi, risk gözlemi). **R3-R5 sonrası:** aynı ürün ikinci
varlık sınıfıyla, araştırma için.

## Kontrollü canlıdan önce ne kalıyor?

Sırayla: R1 (tekrar üretim) → R8 (`paper` modu, 30 gün + fill koşulu) → R9 (execution
bağlantısı, evren kapısı, testnet'te strateji-güdümlü emirler; APPROVAL) → **promotion geçen
strateji** (tetik; bugün 0/52) → R12: shadow kodu + 14 gün/20 emir (kalibre) + 7 karar +
`Venue-Statu.md` + compliance cevapları + kademe tablosu + işlem anahtarı (IP kısıtlı, ayrı ad)
+ drift ölçümü → **elle onay** (K-010, `sq promotion onayla`) → kademe 1. "Tam otomasyon"
hedef değil; K-050 asimetri kalıcı.

---

**Dalga özetleri:** W0 baseline/stack (Postgres/Redis/Celery/Docker/Sentry yok) · W1 mimari
(canlı emir yolu yok, 7 çok-varlık sınırı) · W2 risk/execution (5 bulgu B1-B5) · W3 araştırma
(0/16 tekrar üretim, R1-R7) · W4 alfa (52 çekiliş 0 PASS, 11 test edilmeyen eksen) · W5 Jev
(5 katman izolasyon) · W6 test/CI (T1-T3) · W7 hazırlık (8 durum, bekleme analizi, compliance)
· W8 borç (D1-D15).
