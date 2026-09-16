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
- `docs/Roadmap.md` — fazlı yol haritası; her faz "Durum" sütunuyla takip edilir, hook bunu
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
- `docs/Faz-4-Donus-4-Coklu-Test.md` — **çoklu test düzeltmesi (K-044).** `oos_sharpe`
  kapısı 0,50 → 1,02. Eşik defterdeki çekiliş sayısına bağlı; defter büyürse
  `sq lab coklu-test` yeniden koşturulup `research/kapilar.py`deki sabit güncellenmeli.
- `docs/Faz-4-Donus-5-Tavan.md` — **tavan testi (K-045).** Maliyet sıfırken bile kapıları
  geçen strateji yok; maliyet duvarı bağlayıcı kısıt değilmiş. Tek sembollü yönlü arama
  **kapandı**. Yeni bir strateji/aile/parametre çekilişi yapılmayacak — istisna, ölçüyle
  gerekçelendirilmiş belirgin biçimde farklı bir bilgi kaynağı. **v2 tam olarak bu
  istisnayı kullanıyor** (K-048): cross-sectional, evren geneli türev ve makro programları
  K-051'in program kaydı + arama bütçesiyle açılır, serbest çekilişle değil.
- `docs/Final-Dokuman.md` — bağlayıcı kapsam, stack, mimari.
- `docs/Roadmap.md` — Faz 0-16, her fazın somut bitti kriteri. Faz 0-8 v1 (8'i kapalı),
  Faz 9-16 v2. **Faz 8 sıraya değil tetiklenmeye bağlıdır:** promotion'u geçen ilk strateji
  çıktığında başlar.
- `docs/Faz-11-Dogrulama-Raporu.md` — **Faz 11 ölçümleri (K-058):** K-054'ün dört kapısının
  null kalibrasyonu (PBO'nun 0,5 referansı gerçek ızgarada geçersiz — null medyanı 0,237),
  evren dayanıklılığının yapısal ölçümü, 38 çekilişin yeni kapılardaki durumu (0/38).
- `docs/Arastirma-Programlari.jsonl` — **araştırma programı defteri (K-051/2, K-058).**
  Append-only. Faz 12'de her program `sq lab program-kaydet` ile **önce** buraya açılır;
  `sq lab hipotez-kaydet` artık `--program` istiyor ve bütçe dolunca reddediyor.
- `research/kapilar_v2.py` — K-054'ün dört kapısı ve eşikleri; `butun_kapilar` 11 kapının
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
- `sq evren backtest` — evren üzerinde çok enstrümanlı koşu. Varsayılan strateji bir
  **kıyastır** (K-030), alfa adayı değil; buradan hipotez üretilmez (K-051).
- `apps/web/` — dashboard SPA (K-036). Token'lar `DESIGN.md`'den üretiliyor
  (`npm run tokens`), elle yazılmıyor.
- `DESIGN.md` — arayüz kimliği. Token'lar Faz 6'da dolduruldu ve **normatif**: kesin
  değerler yalnızca frontmatter'da, gerekçe Markdown gövdesinde. Doğrulama:
  `npx --package @google/design.md -c "designmd lint DESIGN.md"`.

## Uyarı

Bu projede "neredeyse doğru" sonuç, yanlış sonuçtan daha tehlikelidir — çünkü fark
edilmez. Bir şeyden emin değilsen tahmin etme; ölç, ya da açık bırakıp Kararlar.md'ye
yaz.
