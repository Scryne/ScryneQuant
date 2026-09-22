# R8 — paper/gözlem operasyon koşusu: protokol ve önceden sabitlenmiş kriterler (K-111)

Tarih: 2026-09-22 (UTC). Tür: protokol — bu doküman koşuyu **tanımlar ve kriterleri dondurur**; sonuç
yazmaz. Kriterlerin makine-okunur hâli `config/r8_kriterler.json` (SHA-256 `2c3d520e8f3fe5d2…`); K-111
bu hash'i taşır, pencere içinde ve sonrasında değiştirilmez.

## 0. R8 ne değildir

Alfa kanıtı, strateji doğrulaması, promotion kanıtı **değildir**. Araştırma programı K-110 ile askıda,
defter 62'de donmuş; benchmark değişmez; yeni mekanizma, yeni hipotez, yeniden açılan aile yok.
R8'in tek sorusu: *"Mevcut ScryneQuant sistemi gerçek operasyon koşullarında kontrollü ve denetlenebilir
biçimde çalışıyor mu?"* Cevap PASS/FAIL'dir ve hiçbir strateji hakkında bir şey söylemez.

## 1. Mod: `gozlem`, `paper` değil — neden

Roadmap R8 satırı "`--mod paper` evren kurulumu" diyordu. `paper` modu promotion zinciri ister
(K-010; `MOD_ESIGI["paper"] = RISK_INCELEMESI`). Promotion geçmiş strateji yok → paper modunda her sinyal
`PROMOTION_YOK` ile reddedilir; execution, fill, recovery, audit ölçülemez — K-035'in tarif ettiği "boş
geçen kriter". K-035 `gozlem` modunu tam bu ölçüm için kurdu: promotion kapısı dışındaki **bütün** risk
limitleri aynen, simüle fill (K-004/K-007), gerçek emir yok, kanıt üretmez. R8 gözlem modunda koşar;
`--mod paper` bayrağı eklenmez (ölçeceği tek şey reddin kendisi olurdu; o da `risk_kapilari` alanında
`mod=gozlem` kaydıyla zaten sorulmuyor). Roadmap satırı buna göre düzeltildi.

## 2. Koşu tanımı

| | |
|---|---|
| Ad | `r8-kiyas` |
| Host | host-1 (192.168.1.4), `ScryneQuant-Evren` görevi kalıbı (`tools/evren-kosu.ps1`), S4U, çökmede 1 dk yeniden başlatma |
| Komut | `sq paper evren-baslat r8-kiyas --evren-tablo runs/paper/r8-kiyas.evren.parquet --strateji evren_esit_agirlik -p yeniden_dengele_bar=168 -p azami_enstruman=10 -p azami_agirlik=0.02 -p hedef_brut=0.2` |
| Strateji | kıyas (K-030), n=10 haftalık — `evren-kiyas` ile birebir; aday değil |
| Sermaye | 10.000 USDT (simüle) |
| Görevler | mevcut set aynen (`tools/servisler.ps1`): İzleme 15 dk, Yedek 05:30, EvrenTablo 06:15, EvrenSapma 06:45, Özet 09:00, Pano 8788 |
| Başlangıç | **2026-09-25**, K-069 penceresi kapandıktan sonra, K-043 planlı durdurma yordamıyla: bundle → `uv sync --frozen` → testler → görevler. Pencere içinde hosta dokunulmaz (K-069). |
| Pencere | **14 gün** (2026-09-25 → 2026-10-09): iki haftalık dengeleme + **1 Ekim ay sınırı** (K-069'un "ölçülmemiş kaldı" dediği kod yolu) |
| Zorunlu tatbikat | pencere içinde ≥ 1 planlı durdur/başlat (açık pozisyonla) — K-043 bayrağıyla, kesinti sayılmaz; günlük `evren-tatbikat` |

Neden yeni koşu, `evren-kiyas` devam değil: host master'ın gerisinde (`3a74ebf`; 17+ commit), K-069
penceresi kapanınca K-043 ile senkronlanacak; R8 senkronlu kodla, kimliği pencere başında sabitlenmiş
temiz bir koşuda ölçülmeli. `evren-kiyas`/`host-1` Faz 14 kayıtları olarak durur, silinmez.

## 3. Ölçülen 10 alan ve önceden sabitlenmiş kriterler

Eşikler yeni değil: `live/izleme.ESIKLER`, K-004/K-007/K-009/K-021/K-035/K-037/K-038/K-043/K-052/K-082.

| Alan | Ölçüm (mevcut araç) | PASS kuralı |
|---|---|---|
| Veri akışı | `evren-durum`, `izle kontrol` | SON_BAR_GECIKTI kritik 0; KOPMA ≤ 5/24 s; her kopmada `yeniden_baglandi` |
| PIT evren | EvrenTablo yenileme logu, tablo hash | 1 Ekim geçişi: yeni ay üyeliği yazıldı ya da UYELIK_GECIKMESI kayıtlı; geçmiş ay listesi değişmedi |
| Sinyal/benchmark | koşu adımları | ≥ 2 dengeleme hedef üretti; üye sayısı 10 ya da eksikler risk/uygunluk sebebiyle kayıtlı |
| Maliyet | fill defteri vs `config/maliyet` | her fill'de komisyon+slippage > 0, model bps ile tutarlı (1e-9), yön aleyhte (K-007) |
| Risk kapıları | run-içi risk defteri, `safe_mode` | ≥ 1 risk reddi kayıtlı ve execution'a ulaşmadı; SAFE_MODE varsa sebebi audit'te; `mod=gozlem` kimlikte |
| Karar/seal | `kimlik_oku`, `config_hash` | kimlik değişmedi; `kod_degisti` yalnız planlı duruşta; kimlik değişikliğiyle başlatma reddedildi (K-009) |
| Paper execution | fill defteri + adımlar | fill = sinyal barının **sonraki** açılışı (K-004); gerçek emir 0; hedef−fill farkı yalnız red/nakit ile açıklanır |
| Idempotency/recovery | `evren-tatbikat`, planlı durdur/başlat | ≥ 1 yeniden başlatma sonrası `toparlandi`; tatbikat `gecti=true` (bit-aynı özkaynak, canlıyla aynı); ayrışmada koşu **durdu** |
| Audit trail | run-içi zincir hash'li risk defteri (`sq risk audit --audit runs/paper/r8-kiyas.sqlite`) | zincir kırık satır 0; her fill/karar için satır; sayılar depo ile tutarlı |
| Monitoring | İzleme (15 dk), ntfy, günlük özet | kritik alarm 0 ya da her biri runbook koduyla 24 s içinde kapatıldı; SEBEPSIZ_SAPMA 0; SAPMA > 50 bps varsa sebebi kayıtlı |

**Sonuç kuralı:** 10/10 → **PASS** (operasyon kanıtı). Biri kalırsa **FAIL**; kalan alan(lar) K-112'de,
eşik değişmez, koşu tekrarı ancak giderme sonrası yeni koşu adıyla. Ölçüm dışı: Sharpe, getiri, benchmark
farkı, promotion, `ASGARI_PAPER_GUN` (30, K-069/3).

## 4. Başlangıç noktası (2026-09-22 09:00 UTC, salt okunur SSH; hosta dokunulmadı)

Mevcut Faz 14 koşuları — R8 değil, ama R8'in "ne bekleniyor" ölçeği:

| Koşu | Durum |
|---|---|
| `evren-kiyas` (kıyas n=10, gözlem, 17 Eylül'den) | adım 884, son bar 2026-09-22 08:00, özkaynak 10.251,72, brüt 0,181, 8 işlem, 8 pozisyon (BNB BTC DOGE ETH **RLUSD** SOL SUI XRP), SAFE_MODE hayır; 16 olay: kopma 3 (her biri ≤ 31 s'de `yeniden_baglandi`), `toparlandi` ×3 (21 Eyl 11:48 ve 20:30, 22 Eyl 06:51) + `bosluk_tamamlandi` (8, 7 bar) |
| `host-1` (ema_kesisim, tek sembol, gözlem) | çalışma 4,81 gün, **kesinti 5**, fill 1, son bar 08:00 |
| Host kodu | `3a74ebf` (master `e816b7e`'nin gerisinde) |

Okuma (karar değil, K-069 25 Eylül'de kapanır): üç `toparlandi` ve `kesinti 5`, pencere içinde en az üç
yeniden başlatma olduğunu söylüyor; sebep host günlüğünde (25 Eylül'de okunur). Toparlanma ve boşluk
tamamlama **çalışmış** (K-038 yolu), RLUSDUSDT stablecoin evrende (bilinen kural açığı, koşu ortasında
değiştirilmez). Bunlar R8'in `idempotency_recovery` ve `pit_evren` alanlarında tam olarak ölçeceği şeyler.

## 5. Kapanış

Pencere sonunda (2026-10-09 sonrası) `docs/research/records/<tarih>-R8-kapanis.md` + **K-112**: 10 alan
ölçülmüş değerlerle, PASS/FAIL, kalan alanların giderme planı, R9 (execution bağlantısı, APPROVAL)
için sonraki karar. Sonuç ne olursa olsun yazılır; eşik değişmez.

Bu paket kod değiştirmez; koşu 25 Eylül'de açılır.
