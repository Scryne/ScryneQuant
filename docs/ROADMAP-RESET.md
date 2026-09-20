# ROADMAP-RESET — Denetim sonrası yol haritası

**Tarih:** 2026-09-20 · **Girdi:** `docs/audit/W0-W8` + `00-Executive-Summary.md`,
`docs/research/Threshold-Policy.md` · **Durum:** taslak, Scryne onayı bekliyor.
**Bu doküman `docs/Roadmap.md`'nin yerine geçmez, önüne geçer:** kabul edildiğinde Faz 0-16
tablosu "tarihsel" olarak Roadmap.md'de kalır, aktif takip bu dosyadaki R-fazları ve
izler üzerinden yapılır; `session-start` hook'u buradaki durum sütununu okur (⏳ / 🔄 / ✅ / ⛔).

**İlke:** brief §33 — `AUDIT → DECIDE → BUILD → TEST → MEASURE → VALIDATE → USE`. Her R-fazı
somut "bitti" kriteri taşır; hiçbir faz "sonuçlara bakıp karar verilir" ile kapanmaz.
Bekleme tek bir izi durdurur, projeyi durdurmaz.

---

## 0. Denetimin roadmap'e söylediği beş şey

1. Altyapı (veri, backtest, risk, paper, testnet, kill, toparlanma, Jev gölge) **çalışıyor ve
   kanıtlı**; darboğaz altyapı değil (W7). Yeniden yazma **yok**.
2. **Tekrar üretilebilirlik bugün kırık** (W3): 0/16 kayıt, eşik ölçümü durmuş, K-080 yarım.
   Bu, "kanıt" iddiasının temeli — **her şeyden önce** gelir.
3. Araştırma uzayı mevcut eylem uzayında **kapalı** (K-078); açık iki eksen (short/perp, yeni
   varlık sınıfı) araştırma değil **karar + veri** işi. Yeni çekiliş yapmak için önce evren
   kurmak gerekiyor.
4. Brief §15 çok varlık hedefi için repo'da **sıfır** adaptör/veri/takvim/maliyet var; ama
   `Enstruman`, `VeriSozlesmesi`, `SembolKurallari`, `MaliyetModeli` dörtlüsü doğru başlangıç
   (W1 §6). Registry sıfırdan değil, ayrıştırmayla kurulur.
5. Canlıya giden yolda eksik olan strateji **değil**, üç kod kalemi + insan kararları: paper
   modlu koşu yolu, execution bağlantısı + shadow, venue/compliance (W7).

## 1. Makro fazlar

| R | Ad | Durum | Bitti kriteri (sayısal / makine kontrolü) | Ön koşul |
| --- | --- | --- | --- | --- |
| R0 | Denetim / doğruluk baseline | ✅ | `docs/audit/00-08` + Threshold-Policy + bu doküman commit'te (`2ce43d3`+) | — |
| R1 | **Stabilizasyon** | 🔄 | (a) ✅ K-080 (2026-09-20): `bitis_gun` arşiv + REST, `ParquetDepo.kirp`, `sq lab dogrula --geri-sar`, kayıt/defterde `veri_son_ms`, 20 test; veri kimliği geri geliyor, kalan uyuşmazlık kod/hash sürümü → (b); (b) ✅ (2026-09-20) 18 tekrar-edilebilir kayıt sınıflandırıldı (`tekrar-durumu.json`, `docs/research/records/2026-09-20-R1b-kayit-durumu.md`): 2 aynı, 3 yalnız-hash → `sq lab yenile` ile yenilendi ve doğrulanıyor, 10 semantik + 3 veri → adıyla tarihsel; `dogrula` sınıfı raporluyor; (c) ✅ (K-081, 2026-09-20) ölçüm 45 çekiliş, 500/500, %5 sınırı 1,004 (GA 0,982–1,064), sabit 1,04 **korundu** (FP %4,2), `COKLU_TEST_CEKILIS_SAYISI=45`, bekçi git'teki fotoğraf + defteri sayıyor (`coklu-test-olcum.json`); engel A kararıyla çözüldü (`209ff2a`), h51/h52 hash'leri aynı; `data/evren` yedeklendi (arşiv≡yedek 50/50 bayt) ve 2026-09-19 23:00 UTC'ye uzatıldı; (d) CI'da yeniden üretim adımı + Windows kill işi; (e) promotion kaydı zincir hash; (f) `duckdb/structlog` çıkarılmış, `requests` eklenmiş; (g) doküman çelişkileri (W8 §4) kapatılmış, faz dokümanları etiketli, state.json `not` ≤500 karakter | R0 |
| R2 | **Enstrüman & çok varlık alan modeli** | ⏳ | `Enstruman`'a `asset_class, instrument_type, takvim, tick/lot/contract, maliyet_modeli_id, finansman_modeli_id` ayrıştırılmış; enstrüman başına `MaliyetModeli`; takvim soyutlaması (24/7 kripto **bit düzeyinde aynı** sonuç — K-057 kalıbı statik+referans testi); U13-U17 K olarak yazılmış; spot/vadeli/CFD/ETF ayrımı tip düzeyinde zorlanıyor (testle) | R1(a,b) |
| R3 | **Çok varlık veri katmanı** | ⏳ | En az **bir** kripto-dışı sınıf için: kaynak seçilmiş + lisans kaydı (`VeriSozlesmesi.lisans`), tarihsel indirici (idempotent, checksum, `veri_sonu`), takvim doğrulama testi, hayatta kalma yanlılığı ölçümü, `sq data quality` raporu; canlı akış **isteğe bağlı** (paper için gerekir, araştırma için gerekmez) | R2, compliance (veri lisansı) |
| R4 | **Araştırma motoru genelleştirme** | ⏳ | Motor takvim-farkında (seans boşluğu "kırılma" değil); yıllıklandırma takvimden; finansman/rollover bacağı fill'de; kripto koşusu R2'den önceki sonuçla **bit düzeyinde aynı** (referans fixture); spread ayrı maliyet bileşeni | R2 |
| R5 | **Doğrulama / araştırma yönetişimi** | ⏳ | Threshold-Policy kabul → `config/esikler.json` + eşitlik testleri; defterde `karar` (PASS/FAIL/…) ve §19 alanları; embargo kararı uygulanmış; risk motorlu araştırma yolu (K-073 kapanışı: 52 çekiliş risk motoruyla yeniden koşulmuş, fark raporlanmış); yeni evren için null kalibrasyon aracı tek komut | R1(c), R4 |
| R6 | **Çok varlık alfa keşfi** | ⏳ | Program kaydı + bütçe ile açılır (K-051); ilk program **kıyas + null** kurulmadan çekiliş yok; her programın kapanış raporu `docs/research/records/`; sonuç ne olursa olsun yazılır | R3, R5 |
| R7 | **Portföy kurma** | ⏳ | Korelasyon budaması, oynaklık hedefi, risk bütçeleme kapıları tanımlı (Threshold-Policy §4); h51/h52 kurma katmanı çok varlık evreninde yeniden çekiliş; portföy düzeyi kapasite/turnover ölçümü | R6 (≥1 RESEARCH_CANDIDATE) ya da R5 (yöntem, aday olmadan da kurulabilir) |
| R8 | **Paper trading (kanıt üreten)** | ⏳ | Evren kurulumu `--mod paper`; `ASGARI_PAPER_GUN` fill koşulu kararı; ilk `paper` modlu koşu **açılmış** (aday olmasa bile kıyasla — kanıt üretmez ama yol test edilir); açık pozisyonlu toparlanma gerçekte ölçülmüş (25 Eylül) | R1, K-069 kapanışı |
| R9 | **Testnet / broker execution** | ⏳ | `EvrenPaperMotoru`/`PaperMotoru` → `execution/kapi` → `EmirMotoru` bağlantısı (**APPROVAL**), evren yolu kapıdan geçiyor; testnet'te strateji-güdümlü ≥N emir; ikinci venue için adaptör sözleşmesi sınavı (`exchange/temel.py` yeterli mi) | R8, APPROVAL |
| R10 | **Jev araştırma asistanı (yönetişim)** | ⏳ | Jev **sinyal değil**; roller: gizli tekrar (var), deney sözleşmesi doğrulama, gerekçe-rapor tutarlılığı, program kapanış özet kontrolü — hepsi K-049 içinde; gölge açık kalır; yeniden açma yalnız K-074 geri dönüş koşulu | R5 |
| R11 | **Ürün / dashboard** | ⏳ | Tek pano (8787/8788 birleşimi ya da açık ayrım); çok varlık görünümü; a11y/motion/metadata pasları; frontend test; izleme için ikinci bağımsız kanal | R1, R2 |
| R12 | **Kontrollü üretim hazırlığı** | ⛔ tetikli | Tetik: promotion geçen ≥1 strateji **ve** R9. İş: shadow kodu (`Faz-8-Hazirlik.md` §1.3), 7 karar K olarak, `Venue-Statu.md`, compliance soruları cevaplı, kademe tablosu, drift ölçümü. Canlı aktivasyon = elle onay (K-010) | R8, R9, insan |

**Eski fazlarla eşleme:** Faz 8 → R12 · Faz 13 (haber/ML) → R6 içinde program olarak, ayrı
faz değil · Faz 14 → 25 Eylül'de kapanır, kalanı R8/R11 · Faz 15 (ikinci varlık sınıfı) → R2+R3
(artık "koşullu" değil, ana hat) · Faz 16 → R6 (program kaydı kalıbı aynen).

## 2. Paralel izler

Her iz bağımsız ilerler; "girdi" başka izin çıktısıysa belirtildi. Kabul kriteri = ilgili R
fazının satırı. **APPROVAL** = brief §6 (üretim-kritik kod, Scryne onayı).

| İz | Kapsam | Girdi | Çıktı | Bağımsız (bugün başlar) | Engelli | Onay |
| --- | --- | --- | --- | --- | --- | --- |
| **A — Çekirdek stabilite** | R1 | W3/W6/W8 bulguları | yeniden üretilebilir kayıtlar, güncel eşik, CI | K-080 tamamlama, `dogrula` testi, bekçi düzeltme, bağımlılık temizliği, doküman etiketleme | — | Kill CI işi (yaml) düşük risk; promotion zincir hash → **APPROVAL** (K-010 defteri) |
| **B — Çok varlık modeli** | R2 | W1 §6 | `Enstruman` v2, takvim, enstrüman-başı maliyet | Tip tasarımı + kripto için bit-aynı kanıt | R3 kaynak kararı (takvim gerçek veriyle sınanır) | — |
| **C — Veri** | R3 | B tipleri; **kaynak/lisans kararı (insan)** | ilk kripto-dışı depo | Kaynak araştırması (spike: hangi FX/endeks verisi, lisans, `available_time`), takvim kütüphanesi spike'ı | İndirici, kaynak seçilmeden | Veri lisansı → COMPLIANCE |
| **D — Araştırma motoru** | R4 | B | takvim-farkında motor, finansman bacağı | Yıllıklandırma/finansman tasarımı; referans fixture genişletme | Gerçek sınama R3 verisiyle | — |
| **E — Doğrulama** | R5 | Threshold-Policy kararları | `esikler.json`, defter §19 alanları, risk motorlu yeniden koşu | Defter şeması, `karar` alanı, embargo uygulaması, null aracı | Kararlar (Scryne) | Eşik değişimi gevşetme yönündeyse K-050 |
| **F — Alfa araştırması** | R6-R7 | C+E | program raporları | **Hiçbir şey** — çekiliş yok (K-078). Yalnız: program taslağı yazmak (`program-adaylari` kalıbı), kıyas tanımı | Evren yok | Program kaydı = K-051 |
| **G — Risk / execution** | R8-R9 | W2 B1-B5 | paper modu, execution bağlantısı, `AZALTAN_YONLER` pozisyon-farkında, limit kalibrasyonu | Tasarım + testler (sahte adaptörle); `--mod paper` parametresi (kurulum, risk değil) | K-069 (25 Eylül'e kadar hosta dokunma); execution bağlantısı | **APPROVAL** (execution, risk limitleri, AZALTAN) |
| **H — Dashboard** | R11 | — | tek pano, a11y | Frontend denetim pasları, test altyapısı | Çok varlık görünümü B'ye bağlı | — |
| **I — Jev** | R10 | E | yönetişim araçları | Deney sözleşmesi doğrulama tasarımı (TypeSafe cookbook + spike `ts.py`) | — | K-049 içinde kalmalı; yeni soru = yeni çekiliş değil (strateji koşmuyor) ama kayıt |
| **J — Operasyon / dokümantasyon** | R1, R12 | W7/W8 | `docs/` yapısı, Runbook güncel, compliance soru listesi, 25 Eylül kapanışı | Doküman taşıma/etiketleme, Kararlar indeksi, state.json sadeleştirme, compliance soruları | Host senkronu 25 Eylül | Host'a dokunma: K-069 |

**Bugün (2026-09-20) başlayabilen işler, öncelik sırasıyla:** A (K-080), J (doküman), B (tip
tasarımı), C (kaynak spike'ı), E (defter şeması), G (tasarım + `--mod paper`), H (denetim
pasları), I (tasarım). **Bekleyen:** yalnız hosta dokunan işler (25 Eylül) ve R12 (tetik).

## 3. Bekleme politikası (brief §24 — W7 §3'ün kararı)

| Bekleme | Karar | Gerekçe |
| --- | --- | --- |
| K-069 (→25 Eylül) | **kalır**, yalnız hostu kilitler | dayanıklılık ölçümü; diğer izler serbest |
| `ASGARI_PAPER_GUN 30` | **kalır**, fill koşulu eklenir (E) | istatistiksel; K-069 bilerek dokunmadı |
| Eşik yeniden ölçümü | **beklenmez, yapılır** (A) | ölmüş, yeniden koşturulur |
| Faz 15 "spike" koşulu | **kaldırılır** — bekleme değil iş | R2/R3 ana hat |
| Faz 13 "veri bütçesi kararı" | **karar istenir** (Scryne), faz değil program | R6 |
| Shadow 14 gün/20 emir | tetik gelince kalibre | iştah |
| Jev gölge | sürekli, karar noktası yok | bedelsiz |

## 4. En erken kullanılabilir ürün (brief §25)

**Bugün:** araştırma + backtest + canlı veri (Binance) + gözlem paper + pano + Jev gölge —
"Research + Paper" MVP'sinin altyapısı **çalışıyor**. Kullanıcı deneyimi olarak eksik olan:
tek pano, `paper` modu, çok varlık.

**R1 + R8 sonunda (hedef: K-069 kapanışı + 2-3 hafta):** yeniden üretilebilir araştırma + kanıt
üreten paper koşusu + tek pano = **kullanılabilir tek-varlık (kripto) araştırma/paper ürünü**.
Strateji olmadan da kullanılır: kıyas koşusu, veri kalitesi, risk gözlemi.

**R3 + R4 + R5 sonunda:** aynı ürün ikinci varlık sınıfıyla, araştırma için (canlı akış şart değil).

**R6-R7:** ilk çok varlık programı. Sonuç FAIL olabilir — ürün yine kullanılır.

**R12:** yalnız tetikle.

## 5. Onay gerektiren işler (brief §6, §27)

| İş | Neden | Kim |
| --- | --- | --- |
| Paper/evren motoru → `EmirMotoru` bağlantısı; evren yolu execution kapısı | live/order path | Scryne |
| `AZALTAN_YONLER` pozisyon-farkında | risk kararı | Scryne |
| Risk limitlerinin evren-geneli / enstrüman-başı kalibrasyonu (gevşetme yönü) | K-050 | Scryne, ölçümle |
| Promotion defteri zincir hash (biçim değişikliği) | K-010 defteri | Scryne |
| Eşik değişiklikleri (Threshold-Policy §6) | K-018 | Scryne |
| Vadeli/kaldıraçlı ürün, kripto-dışı venue | K-079, K-014, compliance | Scryne + hukuki inceleme |
| Kill switch CI/portability değişikliği | K-065 kodu | Scryne (düşük risk) |
| Host senkronu | K-069 | 25 Eylül sonrası |

## 6. Bu roadmap'in "bitti" sayılması

- Her R satırının durum sütunu makine-okunur; `session-start` hook'u aktif satırı gösterir.
- Her R kapanışında bu dosya güncellenir, `docs/Kararlar.md`'ye K yazılır (roadmap kararı).
- R6+ programları `Arastirma-Programlari.jsonl`'a K-051 ile açılır; bu dosya program listesi tutmaz.
- **İlk uygulama birimi (A):** K-080'in tamamlanması — commit dışı diff'in K kaydı + test +
  REST deposu karşılığı. Gerekçe: her diğer kanıtın önkoşulu.
