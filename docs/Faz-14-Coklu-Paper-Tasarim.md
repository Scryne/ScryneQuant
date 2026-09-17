---
proje: ScryneQuant
faz: 14
tarih: 2026-09-17
type: tasarım
durum: taslak — uygulanmadı
---
# Faz 14 — Çok enstrümanlı paper motoru: tasarım

**Amaç (K-060 plan kaydı):** evren kıyasını ve Faz 12'nin en yakın adaylarını **dondurulmuş**
hâlde, canlı veriyle, 7/24 ileriye dönük izlemek. Bugünkü paper motoru (`live/motor.py`) tek
sembollü; bu doküman onun çok enstrümanlı karşılığını tasarlar. Gerçek emir yok, mod `gozlem`
(K-035: promotion kanıtı üretmez; ölçülen şey ileriye dönük davranış).

## 1. Değişmez: tek kod yolu (K-001, K-057)

Backtest'te tek sembollü motor çok enstrümanlının sarmalayıcısı. Canlıda aynı ilke:

- `CokluBacktest.calistir`ın döngü gövdesi bir **`adim(i, durum)`** fonksiyonuna ayrılır
  (fill → değerleme → risk bar işle → karar → bekleyen). Backtest bu adımı döngüde çağırır,
  canlı motor her kapanmış ızgara barında bir kez çağırır.
- **Kabul testi:** (a) bütün mevcut backtest referansları ve `sonuc_hash`ler bit düzeyinde
  aynı; (b) geçmiş barları canlı motora **tek tek** beslemek (replay) aynı özkaynak eğrisini ve
  aynı işlemleri üretir. (b) geçmezse canlı motor yazılmaz.

## 2. Veri

| Parça | Kaynak | Kural |
| --- | --- | --- |
| Bar akışı | Binance combined WebSocket (`<sym>@kline_1h`), üyeler ∪ açık pozisyonlar | Tek sembollü akışın (`exchange/akis.py`) sözleşmesi: nabız, bayatlık, kopmada REST ile tamamlama |
| Pencere | Sembol başına `BarPenceresi` (1.000 bar) | Aynı doğrulama (`data/dogrulama.py`); ızgaraya hizalama `data/izgara.hizala` |
| Evren üyeliği | Ay başında REST: bütün USDT spot adaylarının M−1 1h barları → `EvrenKurali` (üst 50) | Backtest tablosuyla **aynı** kural ve kimlik (`27b7a16ed0ed`); ay içinde sabit (K-052/3) |
| Kimlik | Ay başında kırılma kontrolü (`data/kimlik.kirilmalar`) | Kırılma varsa sembol o ay aday değil, olay kaydı |

**Izgara barının kapanışı:** `t` barı, üyelerin `t` barları geldiğinde **ya da** kapanıştan
`T_bekle` (öneri: 120 s) sonra işlenir. O ana kadar barı gelmeyen sembol o barda **mevcut
değil** sayılır: yeni kalite bayrağı yok, mevcut tanım yeterli (karar yok, fill yok, K-028).
Sonradan gelen bar pencereye girer ama geçmiş kararı değiştirmez ve `GEC_BAR` olayı olarak
kaydedilir. Bu, canlının backtest'ten **bilinçli** tek farkı ve ölçülür (§6).

## 3. Durum, toparlanma, kilit

- Koşu başına tek SQLite (K-034): kimlik, kontrol noktası (portföy + risk durumu + bekleyen
  hedef özeti), fill defteri, olaylar, audit.
- Toparlanma **yeniden üretim** (K-038): portföy fill defterinden, bekleyen hedef stratejiden
  yeniden üretilip kayıtlı özetle karşılaştırılır; ayrışmada koşu durur.
- Kilit, pid dosyası, durdurma bayrağı, SAFE_MODE işareti: tek sembollü koşuyla aynı modüller
  (`live/kilit.py`, `live/kill.py`, `live/durdurma.py`).

## 4. Stratejiler ve süreçler

- **Süreç başına tek strateji**, veri akışı süreç içinde. Birden çok dondurulmuş strateji ayrı
  zamanlanmış görevlerle koşar (bellek: süreç başına 50 × 1.000 bar ≈ 5 MB + özellikler; host
  16 GB). Paylaşımlı akış ileride optimizasyon, başlangıçta değil.
- **Aşama 1:** `evren_esit_agirlik` (n=10, haftalık, `hedef_brut` 0,2) — ek veri yok.
- **Aşama 2:** Faz 12 adayları (`evren_funding_basis` #46, `evren_makro_nfci` #48) — canlı
  funding/premium (REST, 8 s/1 s periyot) ve makro (ALFRED, günlük; FRED anahtarı hostta).
  Parametreler kayıttan dondurulur, değiştirilmez.

## 5. Risk ve kill

Risk motorunun portföy yolu (`RiskMotoru.portfoy_degerlendir`) canlıda zorunlu; `gozlem` modu
promotion dışındaki bütün limitleri uygular. Süreç dışı kill (K-065) aynen çalışır: gözlemde
borsa emri olmadığı için adımlar işaret + süreç.

## 6. Ölçüm (kabul)

1. Replay eşitliği (§1b) — bit düzeyinde.
2. Canlı-backtest sapması: her gün sonu, o günün canlı barlarıyla aynı motor backtest olarak
   koşulur; özkaynak farkı ve `GEC_BAR` olayı sayısı raporlanır. Sıfırdan farklı sapmanın her
   biri bir sebebe bağlanmalı (geç bar, kopma).
3. 30 gün kesintisiz (K-055), dayanıklılık sayacı `host-1` ile zaten işliyor.

## 6b. Ay dönümü: evren tablosunun yenilenmesi (2026-09-17)

Koşu kendi tablosunu okur (`runs/paper/<kosu>.evren.parquet`, araştırma tablosunun kopyası).
Ay dönünce yeni ayın satırı bu dosyaya eklenmeli:

- `sq paper evren-tablo-yenile <tablo> --indir` (`live/evren_yenileme.py`) — **aynı kural**
  (meta'daki `kural` yeniden kurulur, `kural_kimlik` tutmalı) ve **aynı `tablo_kur`** ile.
  İdempotent; hostta günlük görev. **Ölçüldü:** Ağustos'ta biten bir kopyadan Eylül'e uzatılan
  tablo, araştırma tablosunun hash'ini **bit düzeyinde** verdi (`b06857c0…`, 735 sembol, 18 sn).
- **M−1 tamam mı:** `tablo_kur` yalnızca takvime bakıyor ve `ay_sonu_tolerans_saat=24` son
  günün eksikliğini yutabilir. BTCUSDT'nin M−1 son saati depoda yoksa yazılmaz (çıkış 3).
- **Geçmiş değişmez:** eski ayların sembol listesi yenide aynı değilse yazılmaz.
- Koşu kimliği tablo hash'ini değil `evren_kural_kimlik`i taşır: yenileme hash'i değiştirir,
  koşuyu değil. Her ayın listesi hash'iyle depoya ayrıca yazılır; aynı aya **farklı liste**
  gelirse motor durur, aynı liste farklı hash'le gelirse ilk kayıt kalır.
- Yeni ay tabloda yokken koşu bilinen son ayın listesiyle devam eder ve `uyelik_gecikmesi`
  yazar. **Bilinen sapma:** arşivin son gün dosyası ertesi gün yayımlandığı için canlı üyelik
  backtest'ten ≈1-2 gün geç döner; backtest aynı günlerde yeni listeyi kullanır. Sapma olay
  kaydından günü gününe okunur.
- **Yeni üyenin geçmişi:** backtest'te bir sembolün üye olmadan önceki barları veride var;
  canlıda hiç izlenmemiş sembolün yok. Yeni liste eklenince bu semboller için
  `isinma_bar + 48` bar REST'ten doldurulur (`yeni_uye_gecmisi` olayı), şimdiki adımla
  kaydedilir: toparlanma aynısını üretir (testli). Abonelik sonraki adımda yeniden kurulur.

## 7. Aşamalar ve tahmin

| Aşama | İş | Tahmin |
| --- | --- | --- |
| A | `adim` ayrıştırması + referans hash'leri + replay testi | 1 gün |
| B | Çok sembollü akış + pencere + ızgara barı kapanışı (sahte akışla testli) | 1-2 gün |
| C | Canlı evren üyeliği (ay başı REST) + kimlik kontrolü | 1 gün |
| D | Çok enstrümanlı depo/kontrol noktası/toparlanma + kilit/kill entegrasyonu | 1-2 gün |
| E | CLI (`sq paper evren-baslat`), zamanlanmış görev, hostta kıyas koşusu | 0,5 gün |
| F | Aşama 2 adayları: canlı funding/premium/makro | 2 gün |

Toplam ≈ 7-9 çalışma günü. Kıyasın canlı koşusu E sonunda başlar.
