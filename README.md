# ScryneQuant

Birden fazla bilgi kaynağından (fiyat, türev, makro, olay) beslenen trading hipotezlerini
veri üzerinde araştıran, deterministik olarak backtest eden, arama sayısını sayarak
düzelten, risk kurallarıyla sınırlandıran, paper trading ile doğrulayan ve ancak yapısal
kapılardan geçtikten sonra kontrollü biçimde otomatik uygulayan tek kişilik quant araştırma
ve execution platformu.

**Durum (2026-09-20):** kanonik yol haritası **`docs/ROADMAP-RESET.md`** (R0-R12; Faz 0-16
tablosu `docs/Roadmap.md`'de tarihsel). R0 denetim döngüsü kapandı (`docs/audit/`); R1
stabilizasyon (a)-(f) kapandı — K-080 veri sonu sabitleme, K-081 eşik yeniden ölçümü (45
çekiliş, `oos_sharpe` 1,04 korundu), K-082 promotion zinciri + audit — (g) doküman senkronu
bu güncellemeyle. **52 çekilişin hiçbiri kapıyı geçmedi**; bu kapının çalıştığının kanıtı.
Mevcut eylem uzayında (long-only spot) araştırma kapalı (K-078); Hat 1 veri engelli (K-079).
Host-1 K-069 penceresi (2026-09-17 → 09-25) sürüyor; canlı (R12) tetik bekliyor, hazırlık
`docs/Faz-8-Hazirlik.md`.

**2026-09-12 — vizyon v2 (K-048):** kapsam *multi-asset autonomous trading research &
execution platform*'a genişledi. Çekirdek değişmedi; genişleyen şey bilgi kaynakları ve
enstrüman evreni: PIT veri platformu ve hayatta kalma yanlılığı olmayan evren (Faz 9), çok
enstrümanlı tek motor (Faz 10), dört yeni doğrulama kapısı (Faz 11), ön kayıtlı arama
bütçeli araştırma programları (Faz 12). Jev (TypeSafe) karar katmanı yalnızca gölgede
(K-074); yön ekseni ölçülüp kapandı (K-076).

## Kurulum ve ilk komutlar

```bash
uv sync                                      # bağımlılıklar (K-022)
uv run pytest -q                             # tüm testler
uv run sq data indir BTCUSDT 1h --yil 5.2    # tarihsel veri (idempotent)
uv run sq data quality BTCUSDT 1h            # kalite raporu (K-006)
uv run sq data maliyet                       # yürürlükteki maliyet modeli (K-007)
```

### Paper / gözlem koşusu (Faz 6)

```bash
cd apps/web && npm install && npm run build && cd ../..   # dashboard build'i (bir kez)
uv run sq paper baslat gozlem-1 --strateji ema_kesisim    # koşuyu başlat + dashboard
uv run sq paper durum gozlem-1                            # süreç kapalıyken durum
uv run sq paper olaylar gozlem-1                          # koşu günlüğü, kesinti sebepleri
```

Dashboard `http://127.0.0.1:8787`. Aynı koşu adıyla yeniden başlatmak **yeni koşu
açmaz**: kayıtlı durumdan toparlanır — ve toparlanma bir geri yükleme değil, state'in
yeniden üretilebildiğinin kanıtıdır (K-038). Konfigürasyon koşunun kimliğinin parçası ve
değişmez (K-009); farklı bir konfigürasyon için yeni bir koşu adı verilir.

**`--mod gozlem` promotion zincirini atlar ama kanıt üretmez** (K-035): o koşunun günleri
`paper` aşamasına sayılmaz. Risk motorunun diğer limitleri tam olarak uygulanır.

Veri `data/market/<SEMBOL>/<timeframe>.parquet` altında yaşar ve git'e girmez; dosyanın
SHA-256'sı veri setinin kimliğidir (K-009).

## Bu proje ne değil

Bir "para kazanan bot" değil. Ürünün asıl çıktısı bir strateji değil, **bir stratejiye
güvenilip güvenilemeyeceğini ölçen altyapıdır.** Başarı net PnL ile ölçülmez; sistemin
kaç kötü stratejiyi elediğiyle ölçülür.

## Nereden başlanır

| Soru | Dosya |
| --- | --- |
| Proje ne yapacak? | [`docs/Final-Dokuman.md`](docs/Final-Dokuman.md) — **bağlayıcı (v2)** |
| Neden böyle karar verildi? | [`docs/Kararlar.md`](docs/Kararlar.md) — K-001…K-079 |
| Yeni vizyon ne? | [`docs/Proje-Fikri-v2.md`](docs/Proje-Fikri-v2.md) · denetimi [`docs/Denetim-v2.md`](docs/Denetim-v2.md) |
| Çoklu sembol evreni kurulabilir mi? | [`docs/spikes/06-coklu-sembol-evren.md`](docs/spikes/06-coklu-sembol-evren.md) — evet, ölçüldü |
| Timeframe denendi mi? | [`docs/Faz-4-Donus-1-Timeframe.md`](docs/Faz-4-Donus-1-Timeframe.md) — çürütüldü |
| Seçim yöntemi denendi mi? | [`docs/Faz-4-Donus-2-Secim.md`](docs/Faz-4-Donus-2-Secim.md) — çürütüldü |
| Kaç hipotez denendi? | [`docs/Hipotez-Defteri.jsonl`](docs/Hipotez-Defteri.jsonl) — `sq lab hipotezler` |
| Sırada ne var? | [`docs/Roadmap.md`](docs/Roadmap.md) |
| Özgün fikir neydi? | [`docs/Proje-Fikri.md`](docs/Proje-Fikri.md) |
| Fikirde ne düzeltildi? | [`docs/Denetim.md`](docs/Denetim.md) |
| Arayüz nasıl görünecek? | [`DESIGN.md`](DESIGN.md) |
| Veri katmanı ne buldu? | [`docs/Faz-1-Veri-Raporu.md`](docs/Faz-1-Veri-Raporu.md) |
| Laboratuvar ne ölçtü? | [`docs/Faz-4-Laboratuvar-Raporu.md`](docs/Faz-4-Laboratuvar-Raporu.md) |
| Risk motoru ne yaptı? | [`docs/Faz-5-Risk-Raporu.md`](docs/Faz-5-Risk-Raporu.md) |
| Canlı taraf nerede? | [`docs/Faz-6-Paper-Raporu.md`](docs/Faz-6-Paper-Raporu.md) · [`docs/Faz-7-Execution-Raporu.md`](docs/Faz-7-Execution-Raporu.md) · host operasyonu [`docs/Runbook.md`](docs/Runbook.md) |
| Canlıya nasıl geçilir? | [`docs/Faz-8-Hazirlik.md`](docs/Faz-8-Hazirlik.md) — shadow, kademe, venue; tetik yok |
| Araştırma nerede kapandı? | [`docs/Alpha-Discovery-Gap-Audit.md`](docs/Alpha-Discovery-Gap-Audit.md) (K-078) · [`docs/Faz-16-Hat1-Kapanis.md`](docs/Faz-16-Hat1-Kapanis.md) (K-079) |
| Jev ne yapıyor? | [`docs/Jev-Denetim.md`](docs/Jev-Denetim.md) · [`docs/Jev-Golge-Raporu.md`](docs/Jev-Golge-Raporu.md) — yalnız gölge (K-074) |

## Değişmez kurallar

Strateji I/O yapamaz · Strateji geleceği göremez · Sinyal risk motorunu atlayamaz · Zaman
UTC · Fill bir sonraki barın açılışında · Slippage her zaman aleyhte · Aynı girdi aynı
çıktı · Promotion kapıları kaldırılamaz · Kendi hesabı, kendi parası · Engelleyen katman
risk motorunun dışında olabilir, izin veren olamaz · Toparlanma bir geri yükleme değil,
yeniden üretimdir · Kaç hipotez denendiği sayılır · **Evren de geleceği göremez** ·
**Enstrüman kimliği ticker değildir** · **Kesme `available_time`e göredir** · **Otomasyon
asimetriktir: riski azaltan otomatik, izni artıran kapı + onay** · **AI yetkisi sınırlıdır.**

Gerekçeler: `docs/Kararlar.md`.

## Uyarı

Bu yazılım kişisel araştırma amaçlıdır. Yatırım tavsiyesi değildir, kâr garantisi vermez ve
gerçek para kaybettirebilir. Yalnızca sahibinin kendi hesabında, kendi sermayesiyle
çalışır; başkası adına işlem, sinyal paylaşımı veya ücretli erişim kapsam dışıdır ve
hukuki sınır sayılır (bkz. K-014).
