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

Yeni bir mimari karar verildiğinde `docs/Kararlar.md`'ye K-0XX olarak yazılır ve ilgili
commit mesajında referans verilir. Karar silinmez, üzerine yenisi yazılır.

## Dosya haritası

- `docs/Proje-Fikri.md` — Scryne'ın özgün konsept dokümanı (2627 satır). Tarihsel kayıt;
  çelişkide Final-Doküman kazanır.
- `docs/Denetim.md` — fikir dokümanının denetimi: çelişkiler, eksikler, kapsam kesimleri.
- `docs/Kararlar.md` — **karar günlüğü (K-001…).** "Neden böyle" sorusunun tek adresi.
- `docs/Final-Dokuman.md` — bağlayıcı kapsam, stack, mimari.
- `docs/Roadmap.md` — Faz 0-8, her fazın somut bitti kriteri.
- `docs/Faz-1-Veri-Raporu.md`, `docs/Faz-4-Laboratuvar-Raporu.md`,
  `docs/Faz-5-Risk-Raporu.md` — faz sonu ölçüm raporları. Sayılar buradan alınır, tahmin
  edilmez.
- `config/risk.json` — yürürlükteki risk limitleri; her limit `olculdu`/`istah` kaynağını
  ve (iştahsa) gözden geçirme koşulunu taşır (K-033). `sq risk limitler` ile okunur.
- `migrations/001_faz5.sql` — operasyonel PostgreSQL şeması. **Henüz uygulanmadı**; Faz
  6'da bağlanacak (K-011, K-032). `risk/audit.py`'nin SQLite şemasıyla hizalı tutuluyor.
- `DESIGN.md` — arayüz kimliği. Token'lar Faz 6'da doldurulacak, karar katmanı şimdiden
  bağlayıcı.

## Uyarı

Bu projede "neredeyse doğru" sonuç, yanlış sonuçtan daha tehlikelidir — çünkü fark
edilmez. Bir şeyden emin değilsen tahmin etme; ölç, ya da açık bırakıp Kararlar.md'ye
yaz.
