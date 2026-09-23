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

- `docs/DURUM.md` — **yürürlükteki durumun tek sayfası** (oturum başında önce bu).
- `docs/ROADMAP-RESET.md` — yol haritası; hook "Durum" sütununu okur. Yürürlükteki hat R17
  (aktif demo bot); ⛔ satırlar donduruldu (K-136).
- `docs/Kararlar.md` — karar günlüğü (K-001…); "neden böyle"nin tek adresi.
- `docs/arsiv/` — tarihsel her şey (fikir v1/v2, final doküman, faz raporları, denetimler,
  eski DURUM). Yalnız geçmişe bakarken açılır.
- `DESIGN.md` (proje kökünde) — frontend kimliği (Google DESIGN.md spec'i: kesin değerler
  frontmatter'da, gerekçe Markdown'da).

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

**Kapsam (K-136):** 1-7, 9, 10, 12, 16 ve 17 aktif demo hat dahil **her kodda** geçerli. 8 ve 11
(promotion kapıları, hipotez sayımı) **gerçek paraya** geçişin kuralıdır; demo hatta araştırma
yine ön kayıtla yapılır (`docs/research/records/*-onkayit.md`, koşudan önce commit).

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

**Yürürlükteki hat — aktif demo bot (K-134…K-136)**
- Kod `src/scryne_quant/aktif/`: `strateji` (saf yön serileri), `risk` (boyut, kaldıraç tavanı,
  günlük/haftalık kayıp freni), `araci` (`KriptoPaper`; `MT5Paper` gerçek fiyat/spread + kur
  çevrimi + swap; `MT5Araci` yalnız demo hesap, Integral'de algoritmik emir kapalı), `dongu`,
  `geriye` (aynı kurallarla backtest), `defter` (işlem, özkaynak, karne).
- CLI `sq aktif geriye|calistir|karne|durdur|baglanti`; ayar `config/aktif.json`; koşular
  `runs/aktif/<hesap>/`; testler `tests/unit/test_aktif.py`.
- Takip ekranı `sq execution pano` → http://127.0.0.1:8790 (`trader/aktif_panosu.py` →
  `/api/aktif`, `apps/web/aktif.html` + `src/aktif/`; derleme `cd apps/web && npm run build`).
- Süreçleri `tools/gosterim_gozetmen.ps1` (zamanlanmış görev `ScryneQuant-Gosterim`, 10 dk) ayakta
  tutar: dört demo hesap + pano. `sq aktif durdur` kalıcı kapatır (`kapali`).
- Araştırma: `tools/aktif_arastirma.py` + ön kayıt/sonuç `docs/research/records/2026-09-23-aktif-donus-*`.

**Dondurulmuş (kod ve testler duruyor, çalışan süreç yok, K-136)**
- Alfa araştırması ve promotion: `research/`, `risk/promotion.py`, `config/esikler.json`,
  `docs/Hipotez-Defteri.jsonl` (append-only), `docs/Arastirma-Programlari.jsonl`, `tools/faz12_*`,
  `tools/pozitif_kontrol*.py`, `docs/research/` (Threshold-Policy, RYPP, kayıtlar).
- Gerçek para yolu: `execution/` (mod makinesi, `canli_kapi.py` tek yetki kaynağı), `trader/yurutucu.py`,
  `exchange/canli.py`, `config/kademe.json|risk*.json|venue_statu.json`, `docs/arsiv/Execution-Runbook.md`.
  BTC gösterim/pilot/R8 koşuları durduruldu.
- Jev (`src/scryne_quant/jev/`, K-074) yalnız gölge; işlem katmanı import edemez (`test_jev_izolasyon.py`).
- Veri depoları `data/evren/` (PIT arşiv), `data/market/`, `data/turev/`, `data/makro/`, `data/fx/`.

**Diğer**
- CI `.github/workflows/test.yml` (ruff + `pytest -m "not network"`). `uv run` kilitlenirse
  `.venv/Scripts/` altından çalıştır (süreçler `sq.exe`'yi tutar).

## Uyarı

Bu projede "neredeyse doğru" sonuç, yanlış sonuçtan daha tehlikelidir — çünkü fark
edilmez. Bir şeyden emin değilsen tahmin etme; ölç, ya da açık bırakıp Kararlar.md'ye
yaz.
