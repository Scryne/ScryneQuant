---
proje: ScryneQuant
created: 2026-09-08
type: spike-raporu
spike: 1
kapatir: K-015
status: tamamlandi
---
# Spike 1 — Binance erişimi, rate limit ve Spot Testnet

**Tarih:** 2026-09-08, 19:53 UTC · **Konum:** Türkiye (ev bağlantısı, VPN yok)
**Yöntem:** `research/spikes/spike1_binance_erisim.py` — Python 3.12.10, `requests` 2.34.2,
`ccxt` 4.5.78. Ham çıktı: `research/spikes/out/spike1.json`.

## 1. Ne bilinmiyordu?

K-015 açıktı: Binance'e Türkiye'den erişilebiliyor mu, kimlik doğrulamalı endpoint'ler
coğrafi olarak engellenmiş mi, rate limit'in gerçek sayıları ne, Spot Testnet hâlâ ayakta mı.
Faz 1'in indirici mimarisi (sayfalama, hız, host seçimi) ve Faz 7'nin testnet planı bu
cevaplar olmadan tasarlanamıyordu.

Spike 4 yalnızca **public** endpoint'in cevap verdiğini görmüştü; bu yetersiz kanıttı çünkü
Binance coğrafi kısıtlamayı public veriye değil kimlik doğrulamalı yola uygular.

---

## 2. Ne ölçüldü?

### 2.1 Coğrafi kısıtlama — ayırt edici test

Coğrafi engel varsa Binance kimlik doğrulamalı yolda **HTTP 451** döner. Anahtar eksikse
**400/401** döner. Bu iki cevabı ayırt etmek için anahtarsız ve sahte anahtarlı istekler
yapıldı:

| Endpoint | HTTP | Gövde |
| --- | --- | --- |
| `/api/v3/account?timestamp=1` | **400** | `-1102 Mandatory parameter 'signature' was not sent…` |
| `/api/v3/openOrders?timestamp=1` | **400** | `-1102` (aynı) |
| `/sapi/v1/system/status` | **200** | `{"status":0,"msg":"normal"}` |
| `/sapi/v1/capital/config/getall` | **400** | `-2014 API-key format invalid.` |
| `/sapi/v1/account/apiRestrictions` | **400** | `-2014 API-key format invalid.` |
| `/api/v3/account` + sahte anahtar | **401** | `-2014 API-key format invalid.` |

**Hiçbir istekte 451 yok.** İstekler Binance'in imza/anahtar doğrulama katmanına kadar
ulaşıyor ve orada normal API hatasıyla dönüyor — yani ağ yolu ve endpoint erişimi açık,
reddedilme sebebi yalnızca elimizde anahtar olmaması. `sapi` (hesap tarafı) endpoint'leri de
`api` (piyasa tarafı) kadar erişilebilir.

### 2.2 Gecikme — altı host, 10'ar istek, keep-alive, IPv4

| Host | HTTP | min | p50 | max |
| --- | --- | --- | --- | --- |
| `api.binance.com` | 200 | 287,1 | 340,7 | 643,9 |
| `api1.binance.com` | 200 | 290,6 | 330,4 | 1375,7 |
| `api2.binance.com` | 200 | 260,2 | 354,8 | 1455,1 |
| `api3.binance.com` | 200 | 262,4 | **263,4** | 1316,0 |
| `api4.binance.com` | 200 | 291,1 | 361,7 | 1590,5 |
| `data-api.binance.vision` | 200 | 270,2 | **277,6** | 1361,1 |

Hepsi 60/60 istekte başarılı. p50 ≈ 260–360 ms. Kuyruk gecikmesi (max) 0,6–1,6 s'ye çıkıyor —
Faz 1'in timeout'u bu gerçeğe göre seçilmeli, 1 saniye yetersizdir.

### 2.3 Ortam bulgusu — IPv6 DNS 12 saniye kaybettiriyor

Bu Binance'e ait değil, **yerel çözümleyiciye** ait bir davranış ve ölçüm sırasında ilk
denemeyi 300 saniyeden fazla astığı için ayrıca ölçüldü:

| Host | `AF_UNSPEC` | `AF_INET` (v4) | `AF_INET6` (v6) |
| --- | --- | --- | --- |
| `api.binance.com` | 34,3 ms | 14,5 ms | 15,0 ms (hata) |
| `testnet.binance.vision` | **12.098,8 ms** | 26,6 ms | **12.094,8 ms** (timeout) |
| `data-api.binance.vision` | **12.070,1 ms** | 20,3 ms | **12.067,4 ms** (timeout) |

`*.binance.vision` için AAAA (IPv6) sorgusu cevapsız kalıyor ve ~12 saniye sonra düşüyor.
Python varsayılanı `AF_UNSPEC` olduğu için **her yeni bağlantı 12 saniye bekliyor.**
`AF_INET`'e zorlanınca 20–27 ms.

**Faz 1/7 gereksinimi:** exchange adapter'ı IPv4'e zorlamalı veya kalıcı bir bağlantı havuzu
(session/keep-alive) kullanmalı. Bu yapılmazsa testnet'e her bağlantı 12 saniye gecikir ve
sebep koda bakarak anlaşılmaz.

### 2.4 Rate limit — beyan edilen değerler

`GET /api/v3/exchangeInfo` → `rateLimits`:

| Tip | Limit | Pencere |
| --- | --- | --- |
| `REQUEST_WEIGHT` | **6.000** | 1 dakika |
| `ORDERS` | 100 | 10 saniye |
| `ORDERS` | 200.000 | 1 gün |
| `RAW_REQUESTS` | 300.000 | 5 dakika |

### 2.5 Rate limit — gerçek tüketim ölçümü

Beyan edilen limit tek başına yetmez; asıl soru bir klines çağrısının kaç weight yaktığı.
`X-MBX-USED-WEIGHT-1M` başlığındaki artış ardışık çağrılarla ölçüldü:

```
limit=1000 -> weight dizisi [106, 108, 110, 112]   delta [2, 2, 2]
```

| İstenen bar | Çağrı başına weight |
| --- | --- |
| 100 | 2 |
| 500 | 2 |
| 1000 | **2** |

**Weight, istenen bar sayısından bağımsız: her klines çağrısı 2.** Yani her zaman
`limit=1000` istemek 10 kat daha ucuza aynı veriyi getiriyor.

**Teorik tavan:** 6000 weight/dk ÷ 2 = 3.000 çağrı/dk × 1000 bar = **3.000.000 bar/dk.**
Bu rakam gerçekte ağ gecikmesiyle sınırlanır (Spike 2'de gerçek hız ölçüldü) — ama sonuç şu:
**rate limit bu proje için darboğaz değil.** Faz 1'in indiricisi karmaşık bir token-bucket
kuyruğuna ihtiyaç duymuyor; başlıktan gelen weight'i izleyip eşiğe yaklaşınca beklemek yeter.

### 2.6 BTCUSDT emir kuralları (Faz 7 için)

| Alan | Değer |
| --- | --- |
| `status` | `TRADING` |
| `tickSize` (fiyat adımı) | 0,01 USDT |
| `stepSize` (miktar adımı) | 0,00001 BTC |
| `minNotional` (asgari emir) | **5,00 USDT** |
| `orderTypes` | LIMIT, LIMIT_MAKER, MARKET, STOP_LOSS, STOP_LOSS_LIMIT, TAKE_PROFIT, TAKE_PROFIT_LIMIT |

### 2.7 Spot Testnet — ayakta ve canlıyı takip ediyor

| Endpoint | HTTP | Süre |
| --- | --- | --- |
| `/api/v3/ping` | 200 | 585,2 ms |
| `/api/v3/time` | 200 | 273,6 ms |
| `/api/v3/exchangeInfo?symbol=BTCUSDT` | 200 | 272,8 ms |
| `/api/v3/klines?symbol=BTCUSDT&interval=1h` | 200 | 273,0 ms |
| `/api/v3/account` (anahtarsız) | 400 `-1102` | 276,9 ms |

Testnet **kendi rate limit'ini de aynı 6000/dk olarak** beyan ediyor ve `X-MBX-USED-WEIGHT-1M`
başlığını döndürüyor.

Testnet'in veri gerçekliği ölçüldü — aynı üç saatlik bar, iki ortam:

| Bar (UTC) | Testnet close | Canlı close |
| --- | --- | --- |
| 2026-09-08 17:00 | 78.507,45 | 78.504,38 |
| 2026-09-08 18:00 | 78.438,43 | 78.436,00 |
| 2026-09-08 19:00 | 78.353,50 | 78.348,01 |

**Sapma %0,007.** Testnet donmuş bir kopya değil, canlı fiyatı takip eden ayrı bir emir
defteri. Faz 7'nin execution testleri için gerçekçi.

`ccxt.binance().set_sandbox_mode(True)` doğru host'a yöneliyor
(`https://testnet.binance.vision/api/v3`) ve veri çekiyor — adapter'da ayrı bir kod yolu
gerekmiyor.

### 2.8 Saat farkı (K-005)

RTT'si ortalanmış beş ölçüm, `yerel − sunucu`:

```
[-131,5  -119,2  -153,2  -161,8  -157,1] ms      ortanca = -153,2 ms
```

Yerel saat sunucudan **~153 ms geride.** Binance imzalı isteklerde `timestamp`
`serverTime + 1000 ms`'i aşarsa reddeder; geride olmak bu yönden güvenlidir. Yine de Faz 7
öncesi bir clock-drift kontrolü gerekiyor: bu fark işaret değiştirip +1000 ms'i aşarsa
emirler sessizce reddedilmeye başlar.

### 2.9 CCXT (Faz 1 adapter adayı)

| Ölçüm | Değer |
| --- | --- |
| Sürüm | 4.5.78 |
| `load_markets()` | 4.619 market, **3.220,5 ms** |
| `fetch_ohlcv("BTC/USDT","1h",limit=1000)` | 1000 bar, **308,1 ms** |
| Varsayılan `rateLimit` gecikmesi | 50 ms/istek |
| `fetch_balance()` anahtarsız | `AuthenticationError: binance requires "apiKey" credential` |

`load_markets()` 3,2 saniye sürüyor ve 4.619 marketin tamamını çekiyor — tek sembolle
çalışan bir sistemde her başlatmada ödenmemesi gereken bir maliyet. Faz 1'de önbelleğe
alınmalı.

CCXT'nin varsayılan `rateLimit` değeri 50 ms/istek, yani 1.200 istek/dk. Ölçülen gerçek weight
tavanı 3.000 çağrı/dk olduğuna göre CCXT bizden **2,5 kat daha muhafazakâr** davranıyor.
Sorun değil (Spike 2'nin ölçtüğü gerçek hız zaten ağ sınırlı), ama "yavaş" görünen bir indirme
gördüğümüzde sebebi burada.

### 2.10 Kapanmamış bar — REST her zaman yarım bar döndürüyor

Ayrı ölçüm (`research/spikes/out/kapanmamis_bar.json`), sunucu saati 19:56:25 UTC:

| Interval | Son bar açılışı | Kapanış zamanı | Kapandı mı? |
| --- | --- | --- | --- |
| 1m | 19:56:00 | 19:56:59 | **hayır** |
| 1h | 19:00:00 | 19:59:59 | **hayır** |

3 saniye sonra aynı istek tekrarlandığında **son bar değişti, sondan önceki değişmedi.**

`GET /api/v3/klines` kapanmışlık bayrağı döndürmüyor (o bayrak yalnızca WebSocket akışında,
`x` alanında var). Tek güvenilir kural: `close_time < serverTime` değilse bar kapanmamıştır.

**Bu üç kuralı doğrudan etkiliyor:** K-004 (yarım barla karar verilmez), K-009 ve Faz 1'in
**idempotency** bitti kriteri. Kapanmamış bar atılmazsa aynı indirme komutu iki kez
çalıştırıldığında dosya içeriği farklı çıkar — çünkü son bar mutasyona uğruyor. Yani
idempotency, "kapanmamış barı at" kuralı olmadan **imkânsızdır.**

---

## 3. Karar ne oldu?

**K-015 kapandı → `kabul`.** Binance'e Türkiye'den erişim var, coğrafi engel yok, testnet
ayakta ve canlıyı takip ediyor, rate limit bu projenin ölçeğinde darboğaz değil. Faz 1'in
indiricisi ve Faz 7'nin testnet planı bu temele kurulabilir.

Ölçümden çıkan ve Faz 1/7'ye bağlayıcı olarak geçen kurallar:

1. **Kapanmamış bar atılır** — `close_time < serverTime` değilse bar depoya yazılmaz.
   İdempotency'nin ön koşulu.
2. **`limit=1000` her zaman kullanılır** — weight çağrı başına sabit 2; küçük sayfa istemek
   saf kayıp.
3. **IPv4'e zorlanır veya kalıcı session kullanılır** — yoksa `*.binance.vision`'a her
   bağlantı 12 saniye gecikir.
4. **Timeout ≥ 5 saniye, retry'lı** — ölçülen kuyruk gecikmesi 1,6 saniyeye çıkıyor.
5. **Tarihsel indirme `data-api.binance.vision` üzerinden** — p50 277,6 ms ile en hızlı ikinci,
   ve emir trafiğiyle aynı IP weight havuzunu paylaşmaz.
6. **`load_markets()` önbelleğe alınır** — 3,2 saniye, tek sembol için gereksiz.
7. **Clock-drift kontrolü Faz 7'nin ön koşulu** — şu an −153 ms, güvenli tarafta; +1000 ms'i
   aşarsa imzalı istekler sessizce reddedilir.

---

## 4. Kapanmayan kısım — dürüst sınır

**Hesap ve KYC ölçülmedi, ölçülemezdi.** Bu spike elde API anahtarı olmadan yapıldı. Kanıtlanan
şey şu: kimlik doğrulamalı endpoint'lere giden yol Türkiye'den **açık** ve istek Binance'in
anahtar doğrulama katmanına ulaşıyor. Kanıtlanmayan şey: Scryne'ın bu konumdan hesap
açabildiği, KYC'yi tamamlayabildiği ve o hesabın spot işlem yetkisi aldığı.

Bunlar teknik değil idari adımlardır ve bir insanın yapması gerekir. Faz 7 (testnet execution)
başlamadan önce şu ikisi gerekli:

- **Testnet anahtarı** — `testnet.binance.vision` üzerinden GitHub hesabıyla alınır, KYC
  gerektirmez. Faz 7 için yeterli.
- **Canlı hesap + API anahtarı** — yalnızca Faz 8 için gerekli. O noktaya gelindiğinde bu
  spike'ın kimlik doğrulama kısmı gerçek anahtarla **tekrarlanmalıdır**; bugünkü kanıt "yol
  açık" der, "hesap çalışıyor" demez.

Bu iki adım Faz 7 ve Faz 8'in ön koşulu olarak Roadmap'e yazıldı.

## Kaynaklar

- `research/spikes/spike1_binance_erisim.py` (atılacak kod, commit edilmiyor)
- `research/spikes/out/spike1.json`, `research/spikes/out/kapanmamis_bar.json`
- Ölçüm zamanı: 2026-09-08T19:53:15Z – 19:56:25Z
