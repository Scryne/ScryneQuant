---
proje: ScryneQuant
faz: 16
tur: veri doğrulama raporu (veri kararı C — mark price 1h); ölçüm/stres/likidasyon yok
tarih: 2026-09-20
type: rapor
durum: veri indirildi ve doğrulandı; mmr yok; stres tavanı açılmadı
---
# Hat 1 — C veri doğrulama: mark price 1h (BTC + ETH, IS)

**Ne yapıldı:** C-1 (iki senaryo: `C-isolated`, `C-portfolio`) ve C-2 (PIT / `NON_PIT`
ayrı satır) kararları `docs/arsiv/Faz-16-Hat1-Veri-Karari-Tasarimi.md`'ye işlendi; mark price 1h
BTCUSDT + ETHUSDT, 2020-01 → 2025-02 arşivden indirildi, checksum'landı, pin'lendi,
kapsam/boşluk/suspect kontrolünden geçirildi, iki koşuda parquet SHA'sı eşit.
**Ne yapılmadı:** `mmr` tablosu kaydı (K-066 kapalı, herkese açık sayfa JS riski),
likidasyon sayısı, stres tavanı, canlı/işlem/config değişikliği, yeni K, K kapsamı değişikliği.

## 1. Kaynak ve mekanizma

| | |
| --- | --- |
| Araç | `tools/faz16_mark_indir.py` (`tools/faz12_premium_indir.py` kalıbı; `HttpArsiv` + `checksum_dogrula`; src değişmedi) |
| Kaynak | `data.binance.vision` `data/futures/um/monthly/markPriceKlines/<S>/1h/<S>-1h-YYYY-MM.zip` + `.CHECKSUM` — listeleme sonucu kapsam filtresinde 62 ay/sembol |
| Format | kline düzeni (12 sütun); `open, high, low, close` mark; 62 dosyanın **35'i başlık satırı** taşıyor (premium'da da aynı), atıldı ve sayıldı |
| Depo | `data/turev/mark/<S>.parquet` + `<S>.kaynak.json` — REST (`data/market`) ve spot arşivi (`data/evren`) ile karışmaz (K-056/1); `.gitignore` kapsamı değişmedi, hash'ler buraya kopyalandı |
| Pin | zip başına SHA-256 `.kaynak.json`'da (BTC 2020-01: `0c53176e…`, ETH 2020-01: `f513b4f3…`); parquet SHA-256 **BTC `991e4ac51810c82a1dcc00abdb41ef63bdc8502a4b0c53bf58a949513b517bd0`**, **ETH `f9beee1539887783e98434bf3abde4546b6a8bcde113a18fab6f964044ecdf4c`** |
| Tekrarlanabilirlik | iki ardışık koşu, iki sembolde parquet SHA **eşit** |
| Boyut | 2 × ≈1,1 MB |

## 2. Kapsam, boşluk, suspect

| | BTCUSDT | ETHUSDT |
| --- | ---: | ---: |
| İlk / son bar | 2020-01-01 00:00 / 2025-02-28 23:00 UTC | aynı |
| Satır | 45.072 | 45.216 |
| Beklenen (saatlik ızgara) | 45.264 | 45.264 |
| Eksik bar / kapsama | **192 / 0,9958** | **48 / 0,9989** |
| Boşluk sayısı | 5 | 2 |
| Tekrar / hizasız atılan | 0 / 0 | 0 / 0 |
| Sonlu olmayan ya da ≤ 0 mark | 0 (hata koşulu; tetiklenmedi) | 0 |
| Spot 1h ile eşleşen bar | 45.041 | 45.185 |
| \|mark/spot − 1\| > %5 (`suspect`) | **0** | **0** |
| mark/spot − 1: p1 / p50 / p99 / max\| \| | −0,082 % / −0,021 % / +0,167 % / 2,23 % | −0,095 % / −0,019 % / +0,210 % / 2,42 % |

**Boşluklar (arşiv tarafı, tam günler; doldurulmadı, K-024):**

| Sembol | Sonrası (UTC) | Eksik bar | Premium index arşivinde aynı boşluk? |
| --- | --- | ---: | --- |
| BTC | 2021-06-30 23:00 | 24 (2021-07-01) | evet |
| BTC | 2021-07-23 23:00 | 96 (07-24 → 07-27) | evet |
| BTC | 2022-07-30 23:00 | 24 (2022-07-31) | **hayır** (yalnız mark) |
| BTC, ETH | 2022-10-01 23:00 | 24 (2022-10-02) | evet |
| BTC, ETH | 2023-02-23 23:00 | 24 (2023-02-24) | evet |

Boşluklar aylık arşivin eksik günleri; günlük arşiv (`futures/um/daily/markPriceKlines`)
bu günleri içeriyor olabilir — **indirilmedi**; doldurma kararı **açılmadı**, backlog'da
açık küçük veri kararı olarak kayıtlı (`Veri-Karari-Tasarimi.md`).
Likidasyon ölçümünde boşluk günü "ölçülemez" sayılır, interpolasyon yapılmaz.

**IS kesmesi:** son ay dosyası 2025-02-28'e kadar; IS bitişi 2025-02-16 18:00 UTC. Kesme
ölçümde (veride değil), A/B ile aynı kural.

## 3. Mark ≠ spot, mark ≠ premium — ölçülen fark

Mark/spot oranının medyanı −0,02 %, p99 +0,17…0,21 %, azami mutlak 2,2–2,4 %. Yani
A-5'teki MFE (spot `high`) likidasyon yolu için **yaklaşık** — tipik saatte 0,1 %'in
altında, uç saatlerde 2 %'ye kadar sapıyor. Bu, `mmr` geldiğinde sayacın neden spot'tan
değil mark'tan hesaplanacağının ölçülmüş gerekçesi.

## 4. `mmr` — PIT / NON_PIT durumu (C-2)

| Sınıf | Bugünkü içerik |
| --- | --- |
| `PIT` (kayıt tarihinden ileriye) | **EMPTY / veri yok** (Scryne kararı: K-066 kapalıyken toplanmaz) |
| `NON_PIT` / `leak_risk` (bugünkü tablo → IS) | **EMPTY / veri yok** |

`mmr` kademe tablosu bu turda toplanmadı: imzalı `GET /fapi/v1/leverageBracket` vadeli
anahtar ister (K-066 kapalı — Scryne kararı); herkese açık sayfa tarife sayfasında görülen
JS riskini taşıyor ve denenmedi. Tablo kaydedildiği gün kayıt tarihi PIT sınırı olur;
öncesi tamamen `NON_PIT`. Mark price serisi kendisi PIT'tir (arşiv, ödeme/oluşma anı
belli); PIT sorunu yalnız `mmr` ve marjin kurallarındadır.

## 5. C senaryoları için hazır olan / olmayan

| Girdi | `C-isolated` | `C-portfolio` |
| --- | --- | --- |
| Mark price yolu (1h) | ✅ bu veri | ✅ bu veri |
| Spot fiyat yolu (teminat değeri) | — (sayılmaz) | ✅ `data/evren` 1h |
| Funding → marjin akışı | ✅ A-1 koşu yapısı | ✅ |
| `L` ızgarası | ✅ (seçim yok) | ✅ |
| `mmr` kademeleri | ❌ | ❌ |
| Bakım tutarı / likidasyon ücreti / otomatik marjin ekleme kuralı | ❌ | ❌ |
| Teminat haircut oranları | — | ❌ (repoda yok) |
| Hesap tipi uygunluk şartı | — | ❌ (operasyonel) |

İkisi de `mmr` olmadan sayaç üretmez. Mark verisinin bugün açtığı tek ölçüm: mark−spot
farkı (§3) ve mark yolundan MFE'nin yeniden hesabı (A-5'in mark sürümü) — ikisi de
likidasyon sayısı değil.

## 6. Değişen dosyalar (commit edilmedi)

- `tools/faz16_mark_indir.py` (yeni)
- `docs/arsiv/Faz-16-Hat1-Veri-Karari-Tasarimi.md` (C-1/C-2 kararları ve C kaydı)
- `docs/arsiv/Faz-16-Hat1-C-Veri-Dogrulama.md` (bu rapor)
- `data/turev/mark/` (gitignore; hash'ler §1)

`src/`, `config/`, execution/live, Jev, kapılar, K kayıtları: değişmedi.
