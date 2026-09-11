---
proje: ScryneQuant
faz: 7
type: faz-raporu
tarih: 2026-09-11
status: kapandi
---
# Faz 7 — Execution sandbox (Binance Spot Testnet)

Bu dosyadaki her sayı ölçüldü. Ham çıktılar `runs/testnet/` altında
(`faz7-100.json`, `faz7-kesinti.json`); `.gitignore`'da olduğu için sayılar buraya
kopyalandı, ama üreten komutlar yazılı ve tekrar çalıştırılabilir.

## Bitti kriteri

| Kriter | Sonuç | Kanıt |
| --- | --- | --- |
| Aynı intent iki kez → tek emir | ✅ **iki katman**, ikisi de gerçek borsaya karşı ölçüldü | `faz7-100.json` · `test_mutabakat.py::TestDuplicate` |
| Süreç gönderim ortasında ölünce state uyuşuyor | ✅ **iki vakanın ikisi de** doğru çözüldü | `faz7-kesinti.json` · `sq testnet kesinti` |
| Testnet'te ≥100 emir, elle müdahalesiz | ✅ **100/100 FILLED**, hata 0 | `faz7-100.json` · `sq testnet yuk` |
| Uyuşmazlıkta halt | ✅ `Uyusmazlik` fırlıyor, koşu duruyor | `test_mutabakat.py::TestHalt` |

Ön koşul (Faz 0'dan): testnet API anahtarı alındı; clock-drift kontrolü çalışıyor —
aşağıda.

## 1. Yük koşusu — 100 emir

`sq testnet yuk faz7-100 --emir 100 --mutabakat-her 25`

| Ölçüm | Değer |
| --- | --- |
| Gönderilen | 100 |
| `FILLED` | **100** |
| `REJECTED` / `FAILED` / `UNKNOWN` | 0 / 0 / 0 |
| Elle müdahale gerektiren hata | **0** |
| Ara mutabakat | 5 kez, hepsi temiz |
| Risk motoru reddi | 0 |
| Süre | 2 dk 4 sn (10:57:11 → 10:59:15 UTC) |
| Saat sapması (koşu sonu) | −2.535 ms |
| `-1021` (timestamp) hatası | **0** |

Emirler BUY/FLAT dönüşümlü, emir başına ≤10 USDT: net pozisyon sıfıra yakın kaldı, ölçüm
testnet bakiyesini tüketmedi.

**Sinyaller gerçek risk motorundan geçti** (`RiskMotoru.degerlendir`, mod `gozlem`) —
değişmez kural 3 bu ölçümde de geçerli. Gözlem modu seçildi çünkü promotion kapılarını
geçmiş strateji yok; `paper` modu her sinyali `PROMOTION_YOK` ile reddeder ve kriter **boş
yere** geçerdi (K-035, Faz 6'da aynı sorunun aynı çözümü). **Bu koşunun hiçbir kaydı
promotion kanıtı değildir.**

## 2. Duplicate koruması — gerçek borsaya karşı

Koşunun sonunda ilk niyet **bilerek** ikinci kez gönderildi.

| Katman | Ölçülen |
| --- | --- |
| Defter (yerel) | Kimlik tanındı, istek borsaya **hiç gitmedi** — fiyat sorgusu bile yapılmadı |
| Deterministik kimlik (borsa) | Defter silinip yeniden kurulduğunda borsa `-2010` ile reddetti (birim test) |

İkinci katmanın birincinin yedeği olması ölçülmüş bir özellik, varsayım değil: defter
dosyası silinse, elle bozulsa veya başka bir makineden koşulsa bile kimlik aynı içerikten
türediği için borsa tarafındaki koruma ayakta kalıyor.

## 3. Kesinti + mutabakat — Faz 7'nin en zor kriteri

`sq testnet kesinti faz7-kesinti`

İstek **gerçekten gönderildi**, yanıt yutuldu, defter kapatıldı (süreç ölümünün diskteki
izi), sonra yeni bir defter nesnesi diskten kuruldu ve mutabakat çalıştı.

| Vaka | Borsada emir | Kesintiden sonra | Mutabakattan sonra | Beklenen |
| --- | --- | --- | --- | --- |
| Yanıt kayboldu, emir **oluştu** | var | `UNKNOWN` | **`FILLED`** | `FILLED` ✅ |
| Yanıt kayboldu, emir **oluşmadı** | yok | `UNKNOWN` | **`FAILED`** | `FAILED` ✅ |

İki satır birlikte okunmalı. Çağıran açısından bu iki durum **ayırt edilemez** — ikisinde de
görülen şey aynı `ReadTimeout`. Buna rağmen iki farklı doğru sonuca varıldı, çünkü mutabakat
cevabı tahminden değil borsadan alıyor. `UNKNOWN`u "herhalde olmadı" sayıp yeniden göndermek
birinci satırda duplicate emir üretirdi.

## 4. Saat — ölçüm ve çözüm

İlk ölçüm yanlıştı ve düzeltmesi kayda değer: IPv4 zorlanmadan ölçüldüğü için K-015/3'teki
AAAA fallback ilk isteği geciktirdi ve −8,9 s'lik uç değerler üretti. IPv4 zorlanmış ölçüm
(host başına 9 örnek, ısınma isteği hariç):

| Host | Medyan | Min | Max | Yayılım | RTT medyan |
| --- | ---: | ---: | ---: | ---: | ---: |
| testnet.binance.vision | −2.661 ms | −2.897 | −2.650 | 247 ms | 304 ms |
| data-api.binance.vision | −2.624 ms | −2.655 | −2.609 | 46 ms | 313 ms |

İki host aynı → sapma sunucuda değil, **yerel makinede**, ve kararlı. Spike 1'in ölçtüğü
−153 ms artık geçerli değil.

**`w32tm` ile düzeltmek reddedildi**: sorunu çözmez, erteler. `timestamp` artık borsanın
saatinden türüyor ve `time.monotonic()` çıpasına bağlı — sistem saati değişse bile imza
geçerli kalıyor. 100 emirlik koşuda tek bir `-1021` görülmedi, oysa yerel saat koşu boyunca
2,5 saniye gerideydi. Ayrıntı: K-041/2.

## 5. Gerçek koşunun bulduğu iki hata

Birim testlerin tamamı yeşilken (988 test) gerçek testnet iki hata gösterdi:

1. **`FLAT` borsaya olduğu gibi gidiyordu** → `Invalid side`, 2/4 emir reddedildi.
2. **Defter istenen miktarı yazıyordu, gönderilebileni değil.** `FILLED` bir emrin `kalan`ı
   sıfır değildi — tamamen dolmuş ama defterde bakiyesi olan bir emir.

İkisinin de sebebi aynı: **sahte borsa gerçeğinden hoşgörülüydü.** `SahteBorsa` yönü hiç
doğrulamıyor ve miktarı olduğu gibi dolduruyordu. Bir sahte, gerçeğin reddettiğini kabul
ediyorsa ona karşı yeşil olan test bir şey kanıtlamaz. Sahte borsa artık yön ve lot adımı
kontrolü yapıyor; her iki hata için regresyon testi var
(`test_mutabakat.py::TestGercekKosudanCikanlar`).

İkinci hata bu projenin "neredeyse doğru" dediği sınıfın ders kitabı örneği: çökme yok,
hata yok, test yeşil — ve pozisyon hesabında her emirde biraz büyüyen sessiz bir fark.

## 6. Üretilen paketler

- `exchange/hatalar.py` — hata hiyerarşisi (`BelirsizSonuc`, `GonderilemediHatasi`,
  `BorsaReddetti`, `SaatSapmasi`). `temel.py`den ayrı çünkü emir yolunda pandas yasak.
- `exchange/kurallar.py` — `SembolKurallari` + lot/notional uydurma (aşağı yuvarlama, K-007).
- `exchange/emir_adaptoru.py` — emir tarafı sözleşme, durum ve yön eşlemeleri.
- `exchange/imzali.py` — imzalı Binance istemcisi, saat senkronu, hata sınıflandırması.
- `execution/motor.py` — gönderim sırası ve sonuç sınıflandırması.
- `oms/mutabakat.py` — §25 mutabakatı ve halt.
- CLI: `sq testnet {durum, yuk, kesinti, mutabakat}`.

**991 test yeşil** (Faz 6 sonunda 942'ydi).

## 7. Bu faz neyi ölçmedi

- **Pozisyon mutabakatı.** Koşu başındaki bakiyenin bağımsız kaydı yok; Faz 8'in
  *"açıklanamayan pozisyon farkı: sıfır"* kriteri onu kuracak (K-041/3).
- **PostgreSQL şeması.** K-034 ile Faz 7'ye ertelenmişti; Faz 7'de de tek yazıcı var, yani
  şemanın gerekçesi olan eşzamanlı yazma hâlâ doğmadı. `migrations/001_faz5.sql` dondurulmuş
  kalıyor ve `oms/defter.py` ile birlikte SQLite üzerinde çalışılıyor. Karar Faz 8'e taşındı.
- **Limit emri ve iptal.** Faz 7 market emriyle çalıştı; `CANCELED` yolu state machine'de
  tanımlı ama gerçek borsaya karşı hiç yürütülmedi. Limit emri gerektiğinde ölçülecek.
- **Uzun süreli dayanıklılık.** 100 emir 2 dakikada gönderildi; günlerce süren bir emir
  akışının davranışı (bağlantı yaşlanması, anahtar rotasyonu) ölçülmedi.

## 8. Faz 7'nin verdiği karar

**K-041** — ağ hatası üç sınıfa ayrılır; imzanın zamanı borsadan gelir; mutabakat
çözebildiğini çözer, çözemediğinde durur.
