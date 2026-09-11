# ScryneQuant

Birden fazla bilgi kaynağından (fiyat, türev, makro, olay) beslenen trading hipotezlerini
veri üzerinde araştıran, deterministik olarak backtest eden, arama sayısını sayarak
düzelten, risk kurallarıyla sınırlandıran, paper trading ile doğrulayan ve ancak yapısal
kapılardan geçtikten sonra kontrollü biçimde otomatik uygulayan tek kişilik quant araştırma
ve execution platformu.

**Durum:** Faz 0-5 ve 7 kapandı; Faz 6'nın 30 günlük gözlem koşusu sürüyor (`gozlem-2`,
2026-09-11 → ≈2026-10-11). Faz 8 (kontrollü live) promotion'u geçen bir strateji bekliyor —
38 hipotezin hiçbiri geçmedi (K-044, K-045) ve bu kapının çalıştığının kanıtı.

**2026-09-12 — vizyon v2 (K-048):** kapsam *multi-asset autonomous trading research &
execution platform*'a genişledi. Çekirdek değişmedi; genişleyen şey bilgi kaynakları ve
enstrüman evreni. Sıradaki iş **Faz 9**: PIT veri platformu, hayatta kalma yanlılığı olmayan
çoklu sembol evreni ve kanonik enstrüman kimliği (Spike 6 ölçtü: 659 aday sembol, ≈0,86 GB,
bugünkü listeden kurulan bir evren her ayın likit isimlerinin medyan %18'ini atıyor).

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
| Neden böyle karar verildi? | [`docs/Kararlar.md`](docs/Kararlar.md) — K-001…K-054 |
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
| Canlı taraf nerede? | [`docs/Faz-6-Paper-Raporu.md`](docs/Faz-6-Paper-Raporu.md) — **açık** |

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
