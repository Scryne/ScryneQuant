# ScryneQuant

Bu proje Scryne'ın Proje Çalışma Akışı'nı takip eder (bkz. global `~/.claude/CLAUDE.md`, ve
detaylı gerekçeler için ScryneOS vault'unda `🧠 500-Knowledge/Proje-Calisma-Akisi.md`).

## Durum

Şu anki aşama `.claude/state.json` içinde tutulur, `session-start` hook'u her oturum başında
bunu okuyup bağlama enjekte eder — nerede kaldığımızı sormana gerek kalmaz. Bir aşama
bittiğinde `asama` alanını sırayla güncelle: `fikir` → `denetim` → `finalizasyon` → `roadmap`
→ `uygulama` → `tamamlandi`. Aynı anda ScryneOS vault'undaki
`🏰 300-Projects/ScryneQuant.md` index notunu da güncelle.

## Dosyalar

- `docs/Proje-Fikri.md` — ilk fikir (v1, tarihsel)
- `docs/Proje-Fikri-v2.md` — **yürürlükteki vizyon** (2026-09-12, multi-asset platform)
- `docs/Final-Dokuman.md` — nihai kararlar (teknoloji stack, mimari, riskler) — **v2**
- `docs/ROADMAP-RESET.md` — kanonik yol haritası (R0-R12); `docs/Roadmap.md` tarihsel. Her faz "Durum" sütunuyla takip edilir, hook bunu
  otomatik okur
- `DESIGN.md` (proje kökünde) — bu projeye özel frontend kimliği (accent palet, tipografi,
  mood). Google DESIGN.md spec'i (alpha): kesin değerler frontmatter'da, gerekçe Markdown'da.

## Frontend

Taban disiplin global `~/.claude/CLAUDE.md`'deki Dark Glassmorphism kuralları — bunlar sabit
ve her projede aynı. Projeye özel karakteri kökteki `DESIGN.md` belirler; o dosya boşsa veya
yer tutucu içeriyorsa frontend işine başlamadan önce `create-design-md` + `ui-ux-pro-max` ile
doldur. Çelişki olduğunda `DESIGN.md` global varsayılanı ezer.

Araç sırası (yeni arayüz): `DESIGN.md` kontrolü → `frontend-design` + `design-taste` (yön ve
anti-slop) → `baseline-ui` (stack kontratı, sürekli açık) → `shadcn`/`21st` MCP (component) →
`ui-ux-pro-max` (palet/UX) → `frontend-ui-engineering` (production) → `ux-writing` (arayüz
metni) → denetim pasları (`fixing-accessibility`, animasyon varsa
`fixing-motion-performance`, public sayfaysa `fixing-metadata`) → `tailwind-ui-refactor`
(son cila). Mevcut bir arayüzü toparlarken `improve-ui` ile başla. Ayrıntı: global
`~/.claude/CLAUDE.md`.

---

## ScryneQuant'a özel — değişmez kurallar

Bu proje gerçek parayla temas edecek. Aşağıdakiler tercih değil, **kısıt**. Bir görev
bunlardan birini ihlal ediyorsa görev yanlıştır; kural değil.

1. **Strateji I/O yapamaz.** `strategy/` paketi exchange, ağ, dosya sistemi veya
   veritabanına erişemez. (K-003)
2. **Strateji geleceği göremez.** `ctx` t anına kadar keser; t sonrası veri bozulduğunda
   backtest sonucu değişmemelidir. (K-002)
3. **Sinyal risk motorunu atlayamaz.** Execution'a giden tek yol onaylanmış intent'tir.
4. **Zaman UTC epoch ms; bar timestamp'i açılış zamanıdır.** (K-005)
5. **Fill bir sonraki barın açılışındadır**, asla sinyal barının kapanışından. (K-004)
6. **Slippage her zaman aleyhte.** Belirsizlikte kötü yöne yuvarla. (K-007)
7. **Aynı girdi aynı çıktıyı verir.** Determinizm testle korunur. (K-009)
8. **Promotion kapıları kaldırılamaz ve sayısaldır.** Live'a elle toggle ile geçilmez;
   her kapı geçer/kalır döndüren makine kontrolüdür, "sonuçlara bakıp karar ver" değil.
   (K-010, K-018)
9. **Kendi hesabı, kendi parası.** Başkasının parası, sinyal paylaşımı, copy trading
   yasak — hukuki sınır. (K-014)
10. **Engelleyen katman risk motorunun dışında olabilir; izin veren katman olamaz.**
    Bayat veri ve `ok` olmayan bar sinyali eler, ama onay üreten tek yer risk motorudur.
    (K-037)
11. **Kaç hipotez denendiği sayılır.** Kapılar strateji başına; "yeterince çok deneyip
    birini geçirmek" eşiğe dokunmadan kuralı delmektir. Hipotez ön kayıtla deftere
    yazılır, sayı promotion kanıtının parçasıdır. (K-039)
12. **Toparlanma bir geri yükleme değil, yeniden üretimdir.** Diskten okunan durum
    bağımsız bir kaynaktan yeniden üretilip karşılaştırılır; uyuşmazlıkta koşu **durur**,
    tahmin yürütülmez. (K-038)
13. **Evren de geleceği göremez.** `ctx` t anında yalnızca o an listelenmiş ve evren
    kuralını t'ye kadarki veriyle sağlayan enstrümanları gösterir; bugünkü listeden kurulan
    evren hayatta kalma yanlılığıdır (ölçüldü: ayda medyan %18). (K-052, Spike 6)
14. **Enstrüman kimliği ticker değildir**; kanonik kimlik geçerlilik aralığı taşır ve kimlik
    kırılması işaretlenir. (K-052)
15. **Bar olmayan gözlemde kesme `available_time`e göredir**, `event_time`e göre değil;
    bilinmiyorsa gün sonuna yuvarlanır. (K-052)
16. **Otomasyon asimetriktir:** riski azaltan otomatik olabilir, izni artıran (canlıya alma,
    sermaye artırma, limit gevşetme) sayısal kapı + elle onay ister. (K-050)
17. **AI yetkisi sınırlıdır:** semantic/research AI yetkisiz; predictive ML yalnız kapıdan
    sonra; LLM çıktısı backtest içinde hesaplanmaz, dondurulmuş veri kaynağıdır; LLM'in
    eğitim kesimi öncesi dönem için ürettiği türetim `leak_riski` taşır ve kapıdan geçemez.
    (K-049)

Yeni bir mimari karar verildiğinde `docs/Kararlar.md`'ye K-0XX olarak yazılır ve ilgili
commit mesajında referans verilir. Karar silinmez, üzerine yenisi yazılır.

## Dosya haritası

- `docs/Proje-Fikri.md` — Scryne'ın özgün konsept dokümanı (2627 satır, v1). Tarihsel kayıt;
  çelişkide Final-Doküman kazanır.
- `docs/Proje-Fikri-v2.md` — **2026-09-12'de gelen ikinci konsept dokümanı** (multi-asset
  autonomous trading platform). Yürürlükteki vizyon; kapsamı genişletir, v1 çekirdeğini
  geçersiz kılmaz (K-048).
- `docs/Denetim-v2.md` — v2'nin denetimi: dokümanın istediğinin ne kadarı zaten var, ne
  çelişiyor, ne eksik. K-048…K-054'ün kaynağı.
- `docs/spikes/06-coklu-sembol-evren.md` — **çoklu sembol evreni ölçüldü** (K-053): 659 aday,
  delist edilenlerin geçmişi indirilebiliyor, hayatta kalma yanlılığı ayda medyan %18,
  ≈0,86 GB.
- `docs/Denetim.md` — v1 fikir dokümanının denetimi: çelişkiler, eksikler, kapsam kesimleri.
- `docs/Kararlar.md` — **karar günlüğü (K-001…).** "Neden böyle" sorusunun tek adresi.
- `docs/Hipotez-Defteri.jsonl` — **kaç çekiliş yapıldığının kaydı (K-039).** Append-only,
  sürüm kontrolünde. Faz 4'e her dönüşte denenecek hipotez **önce** buraya yazılır
  (`sq lab hipotez-kaydet`); kaydedilmemiş bir hipotez `out_of_sample` aşamasını geçemez.
  Sayı yalnızca kayıt değil, **eşiği belirleyen girdi**: K-044 düzeltmeyi ölçtü, yani
  her yeni hipotez `oos_sharpe` kapısını yükseltiyor. **v2 ile (K-051):** defter tek ve
  global kalır (program başına ikinci defter yok); her araştırma programı ön kayıtlı bir
  **arama bütçesiyle** açılır; hipotez kimliğine evren tanımı, portföy yöntemi ve rejim
  tanımı eklenir.
- `sq lab tekrar-kontrol` (`src/scryne_quant/research/gizli_tekrar.py`) — **gizli tekrar çekiliş dedektörü
  (K-061).** `hipotez-kaydet`ten önce koşturulur; Jev yeni gerekçeyi her önceki kayıtla
  karşılaştırır, ≥0,80 uyarı / 0,50–0,80 incele. Engellemez, sayılmaz, işlem katmanına
  girmez. Soru metni hash'le donmuş: değiştirmek yeni spike ister. `TYPESAFE_API_KEY` gerekir.
- `docs/Faz-4-Donus-4-Coklu-Test.md` — **çoklu test düzeltmesi (K-044).** `oos_sharpe`
  kapısı 0,50 → 1,02. Eşik defterdeki çekiliş sayısına bağlı; defter büyürse
  `sq lab coklu-test` yeniden koşturulup `src/scryne_quant/research/kapilar.py`deki sabit güncellenmeli.
- `docs/Faz-4-Donus-5-Tavan.md` — **tavan testi (K-045).** Maliyet sıfırken bile kapıları
  geçen strateji yok; maliyet duvarı bağlayıcı kısıt değilmiş. Tek sembollü yönlü arama
  **kapandı**. Yeni bir strateji/aile/parametre çekilişi yapılmayacak — istisna, ölçüyle
  gerekçelendirilmiş belirgin biçimde farklı bir bilgi kaynağı. **v2 tam olarak bu
  istisnayı kullanıyor** (K-048): cross-sectional, evren geneli türev ve makro programları
  K-051'in program kaydı + arama bütçesiyle açılır, serbest çekilişle değil.
- `docs/Final-Dokuman.md` — bağlayıcı kapsam, stack, mimari.
- `docs/ROADMAP-RESET.md` — **kanonik yol haritası (2026-09-20, denetim döngüsü kabulü):**
  R0-R12 + 10 paralel iz; hook bunu okur. R0-R4 kapalı (R4: K-093…K-097); sırada R5. `docs/Roadmap.md` — Faz 0-16, **tarihsel**.
- `docs/audit/00-08` — denetim döngüsü (W0-W8 + Executive Summary); `docs/research/
  Threshold-Policy.md` — eşik politikası (ölçülmüş / iştah / `DECISION REQUIRED`).
- `docs/Roadmap.md` — Faz 0-16, her fazın somut bitti kriteri (tarihsel). Faz 0-8 v1 (8'i kapalı),
  Faz 9-16 v2. **Faz 8 sıraya değil tetiklenmeye bağlıdır:** promotion'u geçen ilk strateji
  çıktığında başlar.
- `docs/Faz-8-Hazirlik.md` — **Faz 8 hazırlık (2026-09-20, kod yok, K yok).** Shadow adımı
  (tanım, anahtar-yetkisiyle yapısal "gönderilmez" garantisi, `GolgeAdaptoru`/`GOLGE` durumu
  tasarımı), `config/kademe.json` şeması, drift tanımı (`|paper − live|` işlem başına bps),
  venue hukuki statü kayıt biçimi (**doldurulmadı**), tetik gelince iş sırası. Tetik yok.
- `docs/Faz-11-Dogrulama-Raporu.md` — **Faz 11 ölçümleri (K-058):** K-054'ün dört kapısının
  null kalibrasyonu (PBO'nun 0,5 referansı gerçek ızgarada geçersiz — null medyanı 0,237),
  evren dayanıklılığının yapısal ölçümü, 38 çekilişin yeni kapılardaki durumu (0/38).
- `docs/Arastirma-Programlari.jsonl` — **araştırma programı defteri (K-051/2, K-058).**
  Append-only. Faz 12'de her program `sq lab program-kaydet` ile **önce** buraya açılır;
  `sq lab hipotez-kaydet` artık `--program` istiyor ve bütçe dolunca reddediyor.
- `src/scryne_quant/research/kapilar_v2.py` — K-054'ün dört kapısı ve eşikleri; `butun_kapilar` 11 kapının
  tamamı. Eşikler ızgara şekline bağlı: yeni ızgara biçimi `tools/kalibrasyon_v2_kos.py` ile
  yeniden ölçüm ister.
- `docs/Faz-10-Coklu-Enstruman-Raporu.md` — **Faz 10 ölçümleri (K-057):** tek motor +
  sarmalayıcı (bit düzeyinde eşitlik kanıtı), çok enstrümanlı Decimal referansı, evren
  look-ahead, portföy düzeyi risk limitleri, VaR/CVaR + kapasite, evren kıyası, ölçek/bellek
  (323 sembol × 32.857 bar = 945 MB), ve iki beklenmeyen bulgu (`sq lab dogrula` kırıktı;
  `sonuc_hash` atlama sayacı listesi büyüdükçe kayıyordu).
- `docs/Faz-9-Veri-Platformu-Raporu.md` — **Faz 9 ölçümleri (K-056):** arşivden 735 sembol,
  µs geçişi, checksum, ızgaraya oturmayan barlar, kimlik kırılması eşikleri (12 bar / ln 10),
  PIT evren tablosu ve yeniden ölçülen hayatta kalma yanlılığı (medyan %16,7).
- **Veri sonu sabitleme / geri sarım (K-080).** Veri seti kimliği dosya hash'i + son bar;
  depoyu uzatmak eski kayıtları yeniden üretilemez yapar. `sq data indir|arsiv-indir
  --bitis-gun YYYY-MM-DD` depoyu o güne sabitler (sonrası atılır, uzatmak da geri sarmak da
  aynı komut); `sq lab dogrula --geri-sar [--veri-sonu 'YYYY-MM-DD HH:MM']` reddedilen kaydı
  depoyu kaydın `veri_son_ms`ine kırparak yeniden dener (ana depo değişir; `sq data indir`
  geri getirir). Deney ve defter kayıtları `veri_son_ms` taşır (kimliğe girmez). Kanıt:
  `tests/unit/test_geri_sarim.py`. Gerçek depo: 2026-09-09 10:00 UTC sınırı `e3adb02c…`yi
  bayt düzeyinde geri veriyor; kalan uyuşmazlık K-057/6 hash algoritması (R1(b)).
- **Kayıt yenileme (R1(b)).** `sq lab dogrula` uyuşmazlığı sınıflandırır: `yalniz_sonuc_hash`
  (ekonomik alanlar birebir, K-057/6) ya da `semantik` (kod değişmiş, kayıt tarihsel).
  `sq lab yenile <kayıt>` yalnız birinci sınıfı aynı girdiyle yeni kayda çevirir (etiket eski
  kimlik + sebep; eski kayıt silinmez); semantik/aynı kaydı reddeder. Toplu durum:
  `tools/r1b_kayit_durumu.py` → `runs/deneyler/tekrar-durumu.json` (ana depoya dokunmaz,
  geçici kopyada geri sarar); rapor `docs/research/records/2026-09-20-R1b-kayit-durumu.md`.
- `data/evren/` — arşivden inen çoklu sembol deposu (`.gitignore`'da). Sembol başına
  `1h.parquet` + `1h.kaynak.json` (indirilen her arşiv dosyasının SHA-256'sı); `_evren/`
  altında PIT evren tablosu ve kimlik kataloğu. `data/market/` REST verisiyle **karıştırılmaz**
  (K-056/1).
- `docs/Faz-1-Veri-Raporu.md`, `docs/Faz-4-Laboratuvar-Raporu.md`,
  `docs/Faz-5-Risk-Raporu.md`, `docs/Faz-6-Paper-Raporu.md`,
  `docs/Faz-7-Execution-Raporu.md` — faz sonu ölçüm raporları.
  Sayılar buradan alınır, tahmin edilmez. Faz 6 **kapandı** (K-055): 30 günlük koşu kriteri
  sürekli açık host gerektirdiği için Faz 8 ön koşuluna ve Faz 14'e taşındı.
- `config/risk.json` — yürürlükteki risk limitleri; her limit `olculdu`/`istah` kaynağını
  ve (iştahsa) gözden geçirme koşulunu taşır (K-033). `sq risk limitler` ile okunur.
- `migrations/001_faz5.sql` — operasyonel PostgreSQL şeması. **Uygulanmadı ve bu artık bir
  erteleme değil, bir ölçüm** (K-034, 2026-09-11): kararın kendi üç geri dönüş koşulu
  ölçüldü, üçü de gerçekleşmemiş (tek yazıcı; audit 1.091 satır / eşik 10 M; `runs/`
  3,7 MB / eşik 5 GB; tek sembol). Şema dondurulmuş, `risk/audit.py`'nin SQLite şemasıyla
  hizalı tutuluyor ve testle korunuyor. Faz 8'e taşınan şey karar değil, bir sonraki ölçüm.
- `src/scryne_quant/risk/promotion.py` — **promotion kaydı zincir hash'li ve audit'e bağlı
  (K-082).** Her `gecmis` satırı `onceki_hash`/`satir_hash`/`audit_hash`; `yukle()` fail closed;
  eski kayıt `sq promotion zincirle` ile açıkça göç eder (sessiz uyum yok); `degerlendir`/`onayla`
  `--audit` (`runs/audit.sqlite`, `OlayTuru.PROMOTION`). `paper`/`live` açılışı bütünlük ister,
  `gozlem`/`backtest` bakmaz (K-035). `runs/promotion/sma_kesisim.json` **göç edilmedi**.
- `src/scryne_quant/oms/pozisyon.py` — **pozisyon mutabakatı** (K-046). Değişmez açılış
  çıpası + defter akışı vs borsa bakiyesi; açıklanamayan farkta koşu durur. `sq testnet
  pozisyon` ile okunur. Faz 8'in "açıklanamayan pozisyon farkı: sıfır" kriteri buraya
  bakar.
- `runs/testnet/poz-1.*`, `runs/testnet/lim-1.*` — K-046 ve K-047'nin ölçüm koşuları.
  `.gitignore`'da; sayılar `docs/Faz-7-Execution-Raporu.md` §9'a kopyalandı.
- `runs/testnet/<kosu>.sqlite` + `.json` — Faz 7 execution ölçümlerinin emir defteri ve
  raporu. `sq testnet yuk` ve `sq testnet kesinti` üretir. `.gitignore`'da; sayılar
  `docs/Faz-7-Execution-Raporu.md`'ye kopyalanır.
- `runs/paper/<kosu>.sqlite` — bir paper/gözlem koşusunun **tamamı**: koşu kimliği,
  kontrol noktası, fill defteri, koşu günlüğü ve risk audit'i tek dosyada. Koşuyu
  yedeklemek tek bir dosyayı kopyalamak demek. `.gitignore`'da.
- `src/scryne_quant/backtest/coklu_motor.py` — **çok enstrümanlı event loop (K-057).** Tek
  sembollü `backtest/motor.py` bunun sarmalayıcısıdır; kendi döngüsü yok ve bu statik testle
  korunuyor. Evren `ctx`i `strategy/evren.py`, hedef portföy sözleşmesi `strategy/hedef.py`,
  portföy kurma `strategy/kurma.py`de.
- `src/scryne_quant/backtest/fill.py` — **bid/ask fill + spread bileşeni (K-094, R4 Paket 2).**
  Barlarda `bid_open`+`ask_open` varsa alış `ask×(1+s)`, satış `bid×(1−s)` (K-007 üstüne);
  `Emir.kotasyon_fiyat`/`spread_maliyeti`; `Islem.spread`, `Metrikler.toplam_spread`,
  `Sonuc.takvim` (seanslı takvimde `{id, icerik_hash}`) **yalnız varsa** kayda girer — kripto
  yolu bit-aynı (HEAD kıyası K-094'te). FX Parquet → görünüm adaptörü ve FX kalite bayrağı
  **yok** (R4 kalan).
- `src/scryne_quant/common/finansman.py` — **finansman/rollover (K-095, R4 Paket 3).**
  `Enstruman.finansman_modeli_id` → `config/finansman/<id>.json` (global yok, dosya yoksa hata;
  bugün **dosya yok**, ölçülmüş swap oranı gelince yazılır). Rollover anları takvimden
  (`Takvim.rollover_anlari`), bedel `CokluAdimci._finansman_isle`te bir kez nakitten; kayda
  `finansmanlar`/`Islem.finansman`/`toplam_finansman` yalnız varsa. Finansman seanslı takvim
  ister; nakit yetmezse koşu durur.
- `src/scryne_quant/data/fx_gorunum.py` — **FXCM Parquet → motor adaptörü (K-096, R4 Paket 4).**
  `fx_dogrula` FX kalite bayrağı (sözleşme ihlali hata, bozuk bar `suspect`, takvimli gap),
  `fx_barlar` (orta OHLC, hacim NaN, bid/ask aynen), `fx_hizala`, haftalık üyelik, cfd kimlik
  (`maliyet fxcm-fx`, `finansman fxcm-<pair>` — dosyaları **yok**, uydurulmaz).
  `evren_kosu.fx_kur`; `sq evren backtest` FX tablosunu meta'dan tanır (`--fx-depo`).
  Fixture `tests/fixtures/fx/` gerçek EURUSD 2024 h2-h8 (`tools/fx_fixture_uret.py`).
- `src/scryne_quant/data/fx_kalibrasyon.py` + `sq data fx-kalibre` — **FX maliyet kalibrasyonu
  (K-098, R5 Paket 1).** Kripto `kalibre_et` kalıbı, M1 orta fiyat; spread modele girmez (K-094),
  rollover ±15 dk ayrı raporlu. `config/maliyet/fxcm-<pair>.json` **ölçülmüş** (21 çift, K-100/5; Active Trader koşulu); `config/finansman/fxcm-<pair>.json` **proxy** (`tur=proxy` → gecici, promotion
  engeli; `tools/fx_finansman_proxy_yaz.py`). Rapor `docs/research/records/2026-09-21-R5-fx-kalibrasyon.json`.
- `strategy/kutuphane/evren_esit_agirlik.py:FxEvrenEsitAgirlik` — **hacimsiz FX kıyası (K-099).**
  PIT üyelerinin tamamı eşit ağırlık, 120 bar dengeleme, skor yok, hacim NaN kalır; kripto kıyası
  iki kancayla aynı davranış. `sq evren backtest --strateji fx_evren_esit_agirlik --yeniden-dengele 120`.
- **FX depo 21 çift × 55 hafta (K-100).** `data/fx/` pencere 2023-11-19..2024-12-13; `tools/
  fx_depo_durumu.py` durum tablosu (tam/kısmi/sağlayıcı boşluğu/`bozuk`); `bozuk` = sağlayıcı 200
  ama gövde kullanılamaz (kanıt `.bozuk.bin`, bar yok, evrende `var`). Maliyet **çift başına**
  `config/maliyet/fxcm-<pair>.json` (21, ölçülmüş), finansman proxy 21 dosya (gecici).
- `sq evren backtest` — evren üzerinde çok enstrümanlı koşu. Varsayılan strateji bir
  **kıyastır** (K-030), alfa adayı değil; buradan hipotez üretilmez (K-051).
- `apps/web/` — dashboard SPA (K-036). Token'lar `DESIGN.md`'den üretiliyor
  (`npm run tokens`), elle yazılmıyor.
- `src/scryne_quant/jev/` — **Jev karar katmanı, yalnızca gölge/ölçüm (K-074).** `durum.py`
  kanonik durum (betimleyici, `PENCERE_BAR`=1.200, 4h 1h'den kapanmış kovalarla; byte-identical
  sızıntı testi), `sorular.py` donmuş soru seti (`SORU_SHA256` testli), `istemci.py` tek SDK
  girişi + sır taraması, `karar.py` `JevKarari` (`extra=forbid`; olasılık + marj; fail-closed),
  `defter.py` append-only zincir hash'li SQLite (`runs/jev/<kosu>.sqlite`), `golge.py` gölge
  motoru/koşturucu (ayrı süreç, emir yok), `tekrar.py` replay → dondurma
  (`data/semantik/jev/<turetim_id>/`, her kayıt `leak_riski`), `sonuc.py` ileri sonuç +
  kalibrasyon. Bağımlılık yönü tek ve AST testli (`test_jev_izolasyon.py`): `jev` risk/
  execution/oms'a ulaşamaz; işlem katmanı `jev`/`typesafe` import edemez. **Jev'den `Sinyal`
  üreten fonksiyon yoktur** (K-067 aynen). CLI: `sq jev golge|durdur|durum|degerlendir|tekrar|dondur`.
- `config/jev.json` — model pini, **kesim tarihi `null` (UNKNOWN, K-074/3)**, timeout/retry,
  `yon_marji` 0,20, `bayat_ms`, **sonuç tanımları** (giriş `open[t+1]`, ufuk 1/4/24, MAE/MFE,
  maliyet, isabet, kovalar) — koşudan önce sabit; değiştirmek yeni çekiliş (K-049/2).
- `docs/Jev-Denetim.md` — spec ↔ repo denetimi (Existing/Partial/Missing/Conflicts) ve beş
  bağlayıcı karar. `docs/Jev-Integration-Spec.md` — Scryne'ın spec'i (kaynak, değiştirilmez).
  `docs/spikes/07-jev-durum.md` — 4h eşitliği, Jev tutarlılığı, kesim tarihi araştırması.
- `.github/workflows/test.yml` — minimal CI (K-074/8): `uv run pytest -m "not network"` +
  Jev sızıntı testleri adıyla.
- `DESIGN.md` — arayüz kimliği. Token'lar Faz 6'da dolduruldu ve **normatif**: kesin
  değerler yalnızca frontmatter'da, gerekçe Markdown gövdesinde. Doğrulama:
  `npx --package @google/design.md -c "designmd lint DESIGN.md"`.

## Uyarı

Bu projede "neredeyse doğru" sonuç, yanlış sonuçtan daha tehlikelidir — çünkü fark
edilmez. Bir şeyden emin değilsen tahmin etme; ölç, ya da açık bırakıp Kararlar.md'ye
yaz.
