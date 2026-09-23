# W7 — Operations / Product Readiness

**Tarih:** 2026-09-20 · **Baseline:** `1e1a05b` · **Kod değişikliği:** yok · **Uzak hosta bağlanılmadı**
(K-069 penceresi 2026-09-25'e kadar açık; state.json "sync/deploy/restart yapılmaz" diyor —
salt okunur `ssh` bile bu dalgada yapılmadı, host durumu son yazılı kayıttan alındı).
**Okunan:** `docs/arsiv/Runbook.md`, `Faz-14-Host-Kurulum.md`, `Faz-6-Paper-Raporu.md`,
`Faz-7-Execution-Raporu.md`, `Faz-8-Hazirlik.md` (§0, §6), K-055/062/065/066/069/073,
`live/izleme.py` eşik tablosu (Runbook kopyası), `runs/paper/*` (yerel), `apps/web/src`,
`.env.example`, `tools/*.ps1` adları, W1-W6 bulguları.

Durum etiketleri (brief §11): **READY / PARTIAL / BLOCKED / UNSAFE / UNKNOWN**. "READY" =
bugün kullanılabilir ve kanıtı var; "BLOCKED" = eksik bir şey var ve ne olduğu biliniyor;
"UNSAFE" = kullanılırsa zarar verir.

---

## 0. Durum matrisi

| Durum | Sonuç | Bir cümlelik kanıt |
| --- | --- | --- |
| **Research** | **READY** (metodoloji) / **BLOCKED** (tekrar üretim) | Kapılar, defter, program bütçesi, null dağılımı çalışıyor; **ama** bugün hiçbir kayıt yeniden üretilemiyor ve eşik ölçümü duruyor (W3 R1-R3). Yeni bir program açmak K-051'e göre mümkün, kapı bayat (43→45) |
| **Backtest** | **READY** | Tek/çok enstrümanlı motor, Decimal referans, look-ahead/PIT testleri; 5,2 yıl 1h BTC + 109 ay evren; risk motorsuz (K-073) — **araştırma için READY, canlı kıyas için PARTIAL** |
| **Live Data** | **READY** (Binance spot) | WS + REST resync, kalite bayrakları, bayat guard, çok sembollü birleşik akış, PIT üyelik yenileme, ALFRED makro; K-069 penceresinde 4× WS CLOSED yeniden bağlandı. **Yalnız tek venue** |
| **Paper Trading** | **PARTIAL** | Motor, toparlanma, kill, izleme, alarm, yedek/tatbikat, pano hepsi var ve testli. **Ama:** en uzun kesintisiz koşu 4,29 gün / 5 kesinti / **0 fill** (`gozlem-2`); host-1 3 gün (09-17→); hepsi `gozlem` modu → **promotion kanıtı üreten (`paper` modlu) tek bir koşu hiç yapılmadı**; evren koşuları `gozlem`a sabit (W2) |
| **Testnet** | **READY** (ölçüm aracı olarak) / **BLOCKED** (strateji yolu) | 100/100 emir, duplicate, kesinti, pozisyon mutabakatı, limit/iptal gerçek testnet'e karşı ölçüldü (Faz 7). **Ama** testnet'e giden tek yol `cli/testnet` ölçüm komutları; paper motoru testnet'e emir **gönderemiyor** (W1 §2.1) |
| **Production-like Dry Run (shadow)** | **BLOCKED** | Tanım ve tasarım yazılı (`Faz-8-Hazirlik.md` §1), kod yok, K yok, 7 açık karar (§6). Tetik: promotion geçen strateji (0/52) |
| **Restricted Live** | **BLOCKED** (kod + anahtar + venue + strateji) | Canlı host tanımsız (`imzali.py:69`), işlem anahtarı üretilmemiş, `PaperMotoru` `live` reddediyor, venue hukuki kaydı boş (`Faz-8-Hazirlik.md` §3 "doldurulmadı"), promotion geçen strateji yok. **UNSAFE değil**: kazara canlıya gitmek yapısal olarak imkânsız |
| **Full Automation** | **BLOCKED** (tasarım gereği) | K-050 asimetri: izni artıran her adım kapı + elle onay. "Tam otomasyon" bu projenin hedefi değil; hedef "kontrollü otomasyon". Roadmap'te yeniden adlandırılmalı |

## 1. Operasyon envanteri (VERIFIED, yazılı kayıttan)

### 1.1 Host (`192.168.1.4`, Windows, ev ağı)

| Öğe | Durum | Kaynak |
| --- | --- | --- |
| Erişim | SSH yalnız anahtar, LocalSubnet, parola kapalı; uyku kapalı; Update saatleri | Faz-14-Host-Kurulum §1 |
| Görevler (Task Scheduler, S4U, çökmede 1 dk'da yeniden) | `ScryneQuant-Paper` (host-1, ema_kesisim, gözlem, 8787) · `-Evren` (evren-kiyas) · `-EvrenFB` · `-EvrenNFCI` · `-Pano` (8788) · `-Izleme` (15 dk) · `-EvrenTablo` (aylık) · `-EvrenSapma` · yedek 05:30 · Jev `golge-1` | Runbook, `tools/evren-gorev-kur.ps1`, state.json |
| Host kodu | **bilerek 41 commit geride** (`3a74ebf`), pencere sonuna kadar | Roadmap Faz 14 satırı |
| Anahtarlar hostta | `BINANCE_API_KEY` salt okunur (çekim/transfer/işlem kapalı — Spike 8, `faz14_anahtar_denetimi`), `FRED_API_KEY`, `SQ_NTFY_KONU`; `TYPESAFE_API_KEY` kullanıcı ortamında; **işlem anahtarı yok** | `.env.example`, K-062/5, K-066 |
| Bildirim | ntfy.sh: alarm aç/kapa + 09:00 TR günlük özet; özet gelmezse host/ağ ölü demek | Runbook, K-066 |
| Yedek | günlük, koşu başına son 7; `sq paper evren-tatbikat` yeniden üretip karşılaştırır | Runbook |
| Panolar | 8787 (koşunun kendi süreci) ve 8788 (salt okunur ayrı süreç); yalnız SSH tüneliyle | Runbook |

### 1.2 İzleme (dört boyut, 15 alarm kodu, her biri Runbook satırı)

Sistem: `SUREC_YOK, DISK_AZ, BELLEK_AZ` · Veri: `SON_BAR_GECIKTI (≥2 s), EKSIK_ADIM, KOPMA
(>5/24 s), UYELIK_GECIKMESI, TABLO_YENILEME_HATASI` · Trading: `SAFE_MODE, DUSUS (%5/%10),
BRUT_ASIMI (1,5×), KOSU_HATASI` · Model: `SAPMA (>50 bps), SEBEPSIZ_SAPMA, SAPMA_OLCUMU_YOK`.

Alarm **yalnız gözlem** (K-050): durdurmaz, limit değiştirmez. Eşikler `izleme.ESIKLER` tek
yerde, testle korunur (her kodun tabloda satırı olmalı). **Değerlendirme:** brief §13 "monitoring
failure" için tek kapsama `SAPMA_OLCUMU_YOK` (36 s) ve günlük özetin gelmemesi — izlemenin
kendisinin ölmesi (`ScryneQuant-Izleme` görevi) insan tarafından "özet gelmedi" ile fark edilir;
ikinci bağımsız kanal yok → PARTIAL.

### 1.3 Kill switch (K-065)

Süreç dışı, üç adım (işaret → TerminateProcess → açık emir iptali + doğrulama), raporlu; tatbikat
`tools/faz14_kill_tatbikati.py`; restart SAFE_MODE'da açılır; kaldırma elle+gerekçe. **CI kanıtı
yok** (W6 T1). Windows'a bağlı.

### 1.4 Toparlanma

Yeniden üretim (K-038); tatbikat aracı var; **açık pozisyonla gerçek toparlanma henüz
ölçülmedi** (Faz 8 ön koşulu 5; 25 Eylül senkron restart'ında ölçülecek — state.json). Yerelde
testli (`test_toparlanma::test_acik_pozisyonla_kesilse_de_ayni`).

### 1.5 Dashboard (`apps/web`, React 19 / Vite 7 / Tailwind 4)

- Koşu panosu (8787): `Genel, Gunluk, Pozisyon, Strateji` — 4 sayfa (Faz 6 kriteri ✅,
  `test_api` 19 test + "uçtan uca canlı doğrulama").
- Gözlem panosu (8788): `Kosular, Kosu, Ozkaynak, Servisler, Jev, JevOzet` — çok koşu, işlem
  defteri yeniden üretimli (O(N²), 797 adımda ≈8 s), Jev defteri görüntüleme.
- `dist/` bu makinede 2026-09-20 12:25'te build edilmiş; `tokens.css` DESIGN.md'den.
- **Frontend testi yok**; erişilebilirlik/performans denetimi yapılmamış (global CLAUDE.md
  `fixing-accessibility`/`fixing-motion-performance` pasları) → W8/ROADMAP R11.
- API salt okunur (10 GET). Kill/durdur/onay pano'dan **yapılamaz** — doğru (K-043).

### 1.6 Sırlar ve ortam

W2 §7: testnet/salt-okunur/işlem anahtarları ayrı adlarla; işlem anahtarı üretilmemiş; `.env`
git dışı; Jev istemcisi sır temizliyor. Eksik: log çıktılarında sır taraması testi (W6).

## 2. "Şimdi kullanılabilir ürün" (brief §25)

**Bugün gerçekten kullanılabilir olan:** araştırma + backtest + canlı veri + gözlem modlu paper
+ pano + Jev gölgesi. Bu, "Research + Paper Trading" MVP'sinin **altyapı** kısmı ve çalışıyor.

**Kullanılabilir olmayan:** promotion kanıtı üreten `paper` modlu koşu (hiç yapılmadı; evren için
kurulum `gozlem`a sabit), shadow, live.

**Ürün olarak eksik olan şey strateji değil, üç somut kalem:**

1. `paper` modlu koşu **yolu** (evren kurulumunda mod parametresi + 30 günlük promotion
   penceresinin operasyonu). Bugün K-069 ile host 8 gün dayanıklılık ölçüyor ama o koşu
   promotion'a **sayılmıyor** (gözlem). Bir aday çıktığında 30 gün sıfırdan başlar.
2. Tekrar üretilebilirlik (W3) — "kanıt" iddiasının temeli.
3. Çok varlık: veri + registry + maliyet (W1 §6) — brief'in hedefi için sıfır noktası.

## 3. Bekleme dönemleri (brief §24 soruları)

| Bekleme | İstatistiksel olarak gerekli mi? | Hangi kararı besliyor | Paralel iş mümkün mü | Kısaltılabilir mi | En erken aksiyon noktası |
| --- | --- | --- | --- | --- | --- |
| **K-069 8 gün (→ 25 Eylül)** host dayanıklılığı | Kısmen: dayanıklılık ölçümü "kaç kesinti, toparlandı mı" — istatistik değil, gözlem. 8 gün Scryne'ın kararı (30'dan indi) | Faz 14 kapanışı; host senkronu; açık pozisyonlu toparlanma ölçümü | **Evet, tamamen.** Yalnız host'a dokunulmaz. Yerelde K-080, testler, registry, veri katmanı, roadmap — hepsi serbest | Zaten kısaltıldı; daha da kısaltmak "kesintisiz" kelimesini anlamsızlaştırır | 25 Eylül: senkron restart = pozisyonlu toparlanma ölçümü (iki kuş) |
| **`ASGARI_PAPER_GUN = 30`** promotion | **Evet** — ileriye dönük kanıt; K-069 bilerek dokunmadı | live_adayi aşaması | Evet: strateji yokken bu saat **çalışmıyor bile**; aday çıkınca başlar | Politika (Threshold-Policy `DECISION REQUIRED`); sinyal sıklığına göre "gün" yerine "işlem sayısı ∧ gün" daha doğru olabilir | Aday çıktığında |
| **Eşik yeniden ölçümü (~2 s)** | Evet (null dağılım) | yeni program açmadan önce kapı | Evet | Hayır (500 deneme × seed sabit, önbellek) | K-080 tamamlanınca hemen |
| **Shadow 14 gün / 20 emir** (Faz 8 §6/2, iştah) | Belirsiz — emir sıklığı ölçülmeden sayı iştah | live kademe 1 | Evet | İlk shadow'da ölçülüp kalibre edilir | Tetik gelince |
| **Jev gölge penceresi** | Evet (ileriye dönük tek kanıt sınıfı) | Jev yeniden açılma (K-074 geri dönüş) | Evet, bedelsiz | Hayır | Sürekli, karar noktası yok |
| **Faz 15 "broker/lisans spike'ı"** | Hayır — bu bir bekleme değil, yapılmamış iş | ikinci varlık sınıfı | Evet | — | **Hemen** (ROADMAP R2/R3) |

**Sonuç:** Bugün projeyi durduran tek "bekleme" yok. K-069 yalnız hosta dokunmayı kısıtlıyor;
diğer her şey paralel. "Process paralysis" hissi bekleme dönemlerinden değil, **araştırma
uzayının kapanmış olmasından** (K-078) ve çok varlık altyapısının henüz başlamamış olmasından
geliyor.

## 4. Üretim güvenlik kapıları (brief §27) — bugünkü doluluk

| Kapı | Durum | Eksik |
| --- | --- | --- |
| Security | PARTIAL | SSH/anahtar/ağ sertleştirme var; işlem anahtarı IP kısıtı tasarımı var, anahtar yok; log sır taraması testi yok |
| Data integrity | PARTIAL | Kalite bayrakları, checksum, PIT ✓; **tekrar üretim kırık** (W3) |
| Risk | READY (spot, BTC kalibre) / PARTIAL (evren) | B2/B3/B5 (W2) |
| Execution | PARTIAL | Testnet yolu ✓; paper→execution bağlantısı yok (B1) |
| Reconciliation | READY (testnet ölçümlü) | Gerçek hesapla ilk sınav Faz 8 |
| Monitoring | PARTIAL | İkinci bağımsız kanal yok |
| Recovery | PARTIAL | Açık pozisyonlu gerçek toparlanma ölçülmedi |
| Secrets | READY (ayrım) / PARTIAL (denetim) | — |
| Venue | **BLOCKED** | `Venue-Statu.md` açılmadı; hukuki statü yok |
| Compliance | **COMPLIANCE REVIEW REQUIRED** | §5 |
| Strategy validation | **BLOCKED** | 0/52 |
| Operational procedures | READY (Runbook 15 alarm + Jev + yedek) | Faz 8 runbook satırları (drift, kademe) yok |

Canlı aktivasyon **insan kararı** kalır (K-010 elle onay, K-050) — repo bunu zaten zorluyor.

## 5. Uyum / hukuk (brief §26) — COMPLIANCE REVIEW REQUIRED

Bu bölüm hukuki sonuç **üretmez**; repoda ne var, ne yok onu kaydeder.

| Konu | Repoda olan | Durum |
| --- | --- | --- |
| Yargı alanı | Belirtilmemiş (kayıtlar TR saatine göre, host Türkiye'de olabilir) | **UNKNOWN** |
| Enstrüman tipi | Spot kripto (kaldıraçsız); vadeli hesap **açılmıyor** (K-079, Scryne kararı) | VERIFIED |
| Broker/borsa | Binance spot (canlı salt okunur anahtar), Binance testnet; Faz 15 "broker/lisans spike'ı" yapılmadı | PARTIAL |
| Hesap/KYC | Testnet KYC'siz; canlı hesap için Faz 8 ön koşulu "gerçek hesap + KYC" (`imzali.py:69`) | UNKNOWN |
| API şartları / otomatik işlem kısıtları | Binance API ToS'a atıf yok; `Faz-8-Hazirlik.md` §3.2 sorular listesi var, cevap yok | **REVIEW REQUIRED** |
| Vergi/raporlama | Yok | REVIEW REQUIRED |
| Lisans (başkası adına işlem) | K-014: yalnız kendi hesabı/parası; sinyal paylaşımı, copy trading yasak — **hukuki sınır olarak yazılı** | VERIFIED (kapsam) |
| Veri lisansı / yeniden dağıtım | `VeriSozlesmesi.lisans` alanı var (Binance arşivi, FRED); FX/endeks/emtia kaynakları için **hiçbir şey yok** | PARTIAL / R3'te |
| Brief §15 evreni (FX/CFD/endeks) | CFD/FX aracı kurum seçimi = lisans + yargı alanı sorusu; ürün tipi (spot/vadeli/CFD/ETF) ayrımı brief'in de istediği gibi registry'de zorunlu | REVIEW REQUIRED — **kod işi değil, karar** |

## 6. Sonraki dalgalara / roadmap'e

| # | Kalem | Nereye |
| --- | --- | --- |
| P1 | `paper` modlu koşu yolu (evren kurulumunda mod parametresi; tek sembol için zaten var) | R8 |
| P2 | Shadow kodu + 7 karar | R12 (tetikle) |
| P3 | Venue-Statu + compliance soruları | R12, insan |
| P4 | İzleme için ikinci bağımsız kanal (izleyen ölürse) | R1/R11 |
| P5 | Açık pozisyonlu gerçek toparlanma ölçümü | 25 Eylül |
| P6 | Frontend denetim pasları | R11 |
| P7 | "Full automation" hedefinin "kontrollü otomasyon" olarak yeniden adlandırılması | ROADMAP-RESET |

**Sonraki dalga:** W8 — Technical Debt + Documentation.
