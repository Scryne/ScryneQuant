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

- `docs/Proje-Fikri.md` — ilk fikir
- `docs/Final-Dokuman.md` — nihai kararlar (teknoloji stack, mimari, riskler)
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

Yeni bir mimari karar verildiğinde `docs/Kararlar.md`'ye K-0XX olarak yazılır ve ilgili
commit mesajında referans verilir. Karar silinmez, üzerine yenisi yazılır.

## Dosya haritası

- `docs/Proje-Fikri.md` — Scryne'ın özgün konsept dokümanı (2627 satır). Tarihsel kayıt;
  çelişkide Final-Doküman kazanır.
- `docs/Denetim.md` — fikir dokümanının denetimi: çelişkiler, eksikler, kapsam kesimleri.
- `docs/Kararlar.md` — **karar günlüğü (K-001…).** "Neden böyle" sorusunun tek adresi.
- `docs/Hipotez-Defteri.jsonl` — **kaç çekiliş yapıldığının kaydı (K-039).** Append-only,
  sürüm kontrolünde. Faz 4'e her dönüşte denenecek hipotez **önce** buraya yazılır
  (`sq lab hipotez-kaydet`); kaydedilmemiş bir hipotez `out_of_sample` aşamasını geçemez.
  Sayı yalnızca kayıt değil, **eşiği belirleyen girdi**: K-044 düzeltmeyi ölçtü, yani
  her yeni hipotez `oos_sharpe` kapısını yükseltiyor.
- `docs/Faz-4-Donus-4-Coklu-Test.md` — **çoklu test düzeltmesi (K-044).** `oos_sharpe`
  kapısı 0,50 → 1,02. Eşik defterdeki çekiliş sayısına bağlı; defter büyürse
  `sq lab coklu-test` yeniden koşturulup `research/kapilar.py`deki sabit güncellenmeli.
- `docs/Faz-4-Donus-5-Tavan.md` — **tavan testi (K-045).** Maliyet sıfırken bile kapıları
  geçen strateji yok; maliyet duvarı bağlayıcı kısıt değilmiş. Tek sembollü yönlü arama
  **kapandı**. Yeni bir strateji/aile/parametre çekilişi yapılmayacak — istisna, ölçüyle
  gerekçelendirilmiş belirgin biçimde farklı bir bilgi kaynağı.
- `docs/Final-Dokuman.md` — bağlayıcı kapsam, stack, mimari.
- `docs/Roadmap.md` — Faz 0-8, her fazın somut bitti kriteri.
- `docs/Faz-1-Veri-Raporu.md`, `docs/Faz-4-Laboratuvar-Raporu.md`,
  `docs/Faz-5-Risk-Raporu.md`, `docs/Faz-6-Paper-Raporu.md`,
  `docs/Faz-7-Execution-Raporu.md` — faz sonu ölçüm raporları.
  Sayılar buradan alınır, tahmin edilmez. Faz 6 raporu **açık**: fazın 30 günlük kriteri
  duvar saati istiyor, koşu bitince o dosyaya yazılacak.
- `config/risk.json` — yürürlükteki risk limitleri; her limit `olculdu`/`istah` kaynağını
  ve (iştahsa) gözden geçirme koşulunu taşır (K-033). `sq risk limitler` ile okunur.
- `migrations/001_faz5.sql` — operasyonel PostgreSQL şeması. **Uygulanmadı; Faz 7'de de
  ertelendi, karar Faz 8'e taşındı** (K-034): Faz 6 ve Faz 7'nin mimarisinde tek yazıcı var,
  PostgreSQL'in gerekçesi olan eşzamanlı yazma doğmuyor. Şema dondurulmuş, `risk/audit.py`'nin SQLite şemasıyla hizalı
  tutuluyor ve testle korunuyor.
- `runs/testnet/<kosu>.sqlite` + `.json` — Faz 7 execution ölçümlerinin emir defteri ve
  raporu. `sq testnet yuk` ve `sq testnet kesinti` üretir. `.gitignore`'da; sayılar
  `docs/Faz-7-Execution-Raporu.md`'ye kopyalanır.
- `runs/paper/<kosu>.sqlite` — bir paper/gözlem koşusunun **tamamı**: koşu kimliği,
  kontrol noktası, fill defteri, koşu günlüğü ve risk audit'i tek dosyada. Koşuyu
  yedeklemek tek bir dosyayı kopyalamak demek. `.gitignore`'da.
- `apps/web/` — dashboard SPA (K-036). Token'lar `DESIGN.md`'den üretiliyor
  (`npm run tokens`), elle yazılmıyor.
- `DESIGN.md` — arayüz kimliği. Token'lar Faz 6'da dolduruldu ve **normatif**: kesin
  değerler yalnızca frontmatter'da, gerekçe Markdown gövdesinde. Doğrulama:
  `npx --package @google/design.md -c "designmd lint DESIGN.md"`.

## Uyarı

Bu projede "neredeyse doğru" sonuç, yanlış sonuçtan daha tehlikelidir — çünkü fark
edilmez. Bir şeyden emin değilsen tahmin etme; ölç, ya da açık bırakıp Kararlar.md'ye
yaz.
