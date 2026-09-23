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
- `docs/DURUM.md` — **yürürlükteki durumun tek sayfası** (oturum başında önce bu)
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
   (K-010, K-018) **Tek istisna K-115 mikro canlı pilot:** promotion'suz Kademe 1, kodda
   sabit tavan (`canli_kapi.PILOT_*`: 100 USDT sermaye, 10 USDT kayıp), yine elle onay;
   promotion kanıtı üretmez. Tavanı büyütmek kod + test + yeni K; Kademe ≥ 2 promotion ister.
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

**Önce `docs/DURUM.md` oku** — yürürlükteki durumun tek sayfası (doğrulanmış bileşenler, strateji
durumu, 12 kapı, canlı/pilot, Jev, açık işler). Çelişkide DURUM.md ve en yeni K kazanır; faz
raporları ve eski kayıtlar tarihseldir. Aşağıdaki liste yalnız **nereye bakılacağı**dır.

**Karar ve sayım**
- `docs/Kararlar.md` — karar günlüğü (K-001…); "neden böyle"nin tek adresi.
- `docs/Hipotez-Defteri.jsonl` — çekiliş sayısı (K-039), append-only; her hipotez **önce**
  kaydedilir. `docs/Arastirma-Programlari.jsonl` — program + arama bütçesi (K-051); açma/kapama
  `sq lab program-kaydet|program-kapat`. Kayıttan önce `sq lab tekrar-kontrol` (Jev, K-061).
- Evren çekilişi: `tools/faz12_evren_kos.py kaydet|kos|durum` (programlar `PROGRAM_AYARI`,
  ızgaralar `research/izgaralar.py`). **Koşudan önce commit** (yoksa kayıt `dirty` taşır).
- Defter büyüyünce çoklu test fotoğrafı (`docs/research/coklu-test-olcum.json`) yeniden ölçülür:
  `tools/faz12_coklu_test.py --deneme 500 --seed 0` (bekçi `test_coklu_test.py` kırmızı kalır).

**Kapılar ve ölçüm aletleri**
- `research/kapilar.py` (K-019 + K-113), `research/kapilar_v2.py` (K-054; `butun_kapilar` 12);
  eşik kaydı `config/esikler.json` (kod okumaz; `test_esikler.py` kod ↔ JSON ↔ K bağlar).
- `tools/pozitif_kontrol.py` (kahin, gerçek veri), `tools/pozitif_kontrol_tam.py` (tek sembol
  sentetik), `tools/pozitif_kontrol_evren.py` (evren sentetik) — kapı **gücü** (K-117…K-119).
- `research/degerlendirme.py` (tek sembol), `research/evren_degerlendirme.py` (evren);
  motorlar `backtest/motor.py` → `backtest/coklu_motor.py` (tek döngü, K-057).
- `risk/promotion.py` — zincir hash'li promotion; `Kanit.protokol` alfa → `ZORUNLU_KAPILAR` (12, K-118),
  rypp → `RYPP_KOSULLARI` (13) + B-3 bağımsız doğrulama (K-126); diğer aşamalar iki yolda ortak.
  P3 k'sı = RYPP programının açılış bütçesi; kanıta donar, CLI program defterinden okur (K-128).
  `sq promotion degerlendir --hipotez <kimlik>` K-039 sırasını doldurur.
- B-3 bağımsız veri: `data/french.py` + `config/bagimsiz_veri.json` (dondurulmuş kimlik, rol, vintage eşi);
  `sq data bagimsiz-dogrula [dataset]`. French 202607 + 201705 vintage eşi (K-128).
- Mikro pilot hükmü: `sq execution hazirlik` → MİKRO PİLOT (K-129: testler + 7 gün gösterim + kill).
- **Hedef K-125:** riski yönetilen sistematik yatırım. Promotion protokolü `docs/research/Risk-Yonetimli-Protokol.md`
  + `research/risk_protokolu.py` (PASS/FAIL/INCONCLUSIVE, plasebo = kendi takviminin kaydırılmışı). Alfa yolu aynen durur.

**Veri**
- `data/evren/` arşiv deposu (2017-08→, PIT tablo `_evren/27b7a16ed0ed.parquet`); `data/market/`
  REST deposu (2021-06→), karıştırılmaz (K-056/1). Yeni tek sembollü hipotezler `data/evren`
  kullanır (K-119/6). Veri sonu sabitleme/geri sarım: `--bitis-gun`, `sq lab dogrula --geri-sar` (K-080).
- Türev/makro/FX depoları `data/turev/`, `data/makro/`, `data/fx/` (FX finansmanı proxy → promotion
  engeli, K-101/K-107). Carry takibi `tools/funding_guncel.py`.

**Canlı yol**
- `docs/Execution-Runbook.md` — nasıl çalıştırılır (§4.3 pilot). Mod makinesi `execution/mod.py`,
  live gate `execution/canli_kapi.py` (`CanliYetki`'yi üreten tek yer), hat `execution/hat.py`,
  yürütücü `trader/yurutucu.py`, canlı host `exchange/canli.py` (import sınırı testli).
- `config/kademe.json` (pilot Kademe 1: strateji + sembol bağlı), `config/risk.json`,
  `config/venue_statu.json`. R8 protokolü `docs/research/records/2026-09-22-R8-paper-protokol.md`.

**Jev**
- `src/scryne_quant/jev/` — yalnız gölge/ölçüm (K-074); işlem katmanı `jev`/`typesafe` import
  edemez (`test_jev_izolasyon.py`); Jev'den `Sinyal` üreten fonksiyon yok. `config/jev.json`.

**Diğer**
- `.github/workflows/test.yml` CI (ruff + `pytest -m "not network"`). `apps/web/` pano;
  `DESIGN.md` normatif token'lar (`npx --package @google/design.md -c "designmd lint DESIGN.md"`).
- Tarihsel: `docs/Proje-Fikri*.md`, `docs/Denetim*.md`, `docs/Roadmap.md`, `docs/Faz-*.md`,
  `docs/audit/`, `docs/spikes/`.

## Uyarı

Bu projede "neredeyse doğru" sonuç, yanlış sonuçtan daha tehlikelidir — çünkü fark
edilmez. Bir şeyden emin değilsen tahmin etme; ölç, ya da açık bırakıp Kararlar.md'ye
yaz.
