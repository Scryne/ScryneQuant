# ScryneQuant

Kripto spot piyasasında trading hipotezlerini veri üzerinde araştıran, deterministik olarak
backtest eden, risk kurallarıyla sınırlandıran, paper trading ile doğrulayan ve ancak
yapısal kapılardan geçtikten sonra kontrollü biçimde otomatik uygulayan tek kişilik quant
araştırma ve execution platformu.

**Durum:** Roadmap hazır, uygulama başlamadı. Sıradaki adım: Faz 0.

## Bu proje ne değil

Bir "para kazanan bot" değil. Ürünün asıl çıktısı bir strateji değil, **bir stratejiye
güvenilip güvenilemeyeceğini ölçen altyapıdır.** Başarı net PnL ile ölçülmez; sistemin
kaç kötü stratejiyi elediğiyle ölçülür.

## Nereden başlanır

| Soru | Dosya |
| --- | --- |
| Proje ne yapacak? | [`docs/Final-Dokuman.md`](docs/Final-Dokuman.md) — **bağlayıcı** |
| Neden böyle karar verildi? | [`docs/Kararlar.md`](docs/Kararlar.md) |
| Sırada ne var? | [`docs/Roadmap.md`](docs/Roadmap.md) |
| Özgün fikir neydi? | [`docs/Proje-Fikri.md`](docs/Proje-Fikri.md) |
| Fikirde ne düzeltildi? | [`docs/Denetim.md`](docs/Denetim.md) |
| Arayüz nasıl görünecek? | [`DESIGN.md`](DESIGN.md) |

## Değişmez kurallar

Strateji I/O yapamaz · Strateji geleceği göremez · Sinyal risk motorunu atlayamaz · Zaman
UTC · Fill bir sonraki barın açılışında · Slippage her zaman aleyhte · Aynı girdi aynı
çıktı · Promotion kapıları kaldırılamaz · Kendi hesabı, kendi parası.

Gerekçeler: `docs/Kararlar.md`.

## Uyarı

Bu yazılım kişisel araştırma amaçlıdır. Yatırım tavsiyesi değildir, kâr garantisi vermez ve
gerçek para kaybettirebilir. Yalnızca sahibinin kendi hesabında, kendi sermayesiyle
çalışır; başkası adına işlem, sinyal paylaşımı veya ücretli erişim kapsam dışıdır ve
hukuki sınır sayılır (bkz. K-014).
