---
proje: ScryneQuant
faz: 16
tur: spike — vadeli tarife (fee) ve bakım marjı kademeleri: erişim ve kayıt
tarih: 2026-09-20
type: spike
durum: kısmen — likidasyon ücreti kaydedildi; fee ve kademeler anahtar yetkisi bekliyor
---
# Spike 8 — USDⓈ-M tarife ve bakım marjı kademeleri (K-066 ek)

**Soru:** Hat 1 ikinci tavanının iki DATA BLOCKED girdisi — VIP 0 taker fee ve C-isolated MMR
kademeleri — K-066 ekinin izin verdiği iki salt okunur uçla (`commissionRate`,
`leverageBracket`) alınabiliyor mu, doğrulanabiliyor mu?

## 1. Denemeler (2026-09-20 UTC)

| Saat | Uç | Anahtar | Sonuç | Kayıt |
| --- | --- | --- | --- | --- |
| 07:07:59 | `GET /fapi/v1/exchangeInfo?symbol=BTCUSDT` | yok (herkese açık) | HTTP 200, 1.123.073 bayt | `data/turev/kurallar/exchangeInfo_BTCUSDT_20260920T070759Z.json` SHA-256 `926d6672eee3f19e9628b6a1a29428c34d638d4dd70ec5ffef0939a6f0216c70` + `.kaynak.json`; `serverTime` 1789806688641 |
| 07:13:10 | `GET /fapi/v1/commissionRate` BTC/ETH (imzalı) | mevcut `BINANCE_API_KEY` (spot salt okunur, Faz 14) | **HTTP 401 `-2015` "Invalid API-key, IP, or permissions for action"** | `data/turev/kurallar/_kayit_20260920T071310Z.json` |
| 07:13:10 | `GET /fapi/v1/leverageBracket` BTC/ETH (imzalı) | aynı | **HTTP 401 `-2015`** | aynı kayıt |

Araç: `tools/faz16_vadeli_okuma.py` — yalnız bu iki uç, HMAC-SHA256, anahtar hiçbir çıktıya
yazılmaz, ham yanıt + SHA-256 `data/turev/kurallar/` (gitignore) altına.

**Bulgu:** mevcut anahtar vadeli okuma yetkisi taşımıyor (ya da IP kısıtı). K-066 eki
**yetkiyi tanımladı**, anahtarı üretmedi: Binance API yönetiminde "Enable Futures" (yalnız
okuma; işlem/çekim kapalı) verilmiş yeni ya da güncellenmiş bir anahtar **Scryne'ın**
eylemidir. O gelene kadar fee ve kademeler **blocked**; araç hazır, yeniden koşturulur.

## 2. Kaydedilen (doğrulanmış)

| Girdi | Değer | Kaynak | PIT |
| --- | --- | --- | --- |
| Likidasyon ücreti BTCUSDT | `0.012500` | `exchangeInfo.symbols[].liquidationFee` — resmî dokümanda "liquidation fee rate" | kayıt anı 2026-09-20 07:07:59 UTC; öncesi bilinmiyor |
| Likidasyon ücreti ETHUSDT | `0.012500` | aynı | aynı |
| `maintMarginPercent` 2,5 %, `requiredMarginPercent` 5 % | — | resmî dokümanda **"ignore"** | **kullanılmaz**; kademe yerine geçmez |

## 3. Kaydedilmeyen / eksik

| Girdi | Durum | Neden |
| --- | --- | --- |
| VIP 0 USDT-M taker fee → `fee_taker_bps_perp` | **BLOCKED** | `commissionRate` `-2015`; resmî ücret sayfası JS/202; FAQ'lar oran vermiyor |
| MMR kademeleri (`maintMarginRatio`, `cum`, `notionalFloor/Cap`) | **BLOCKED** | `leverageBracket` `-2015`; Leverage & Margin sayfası 202; FAQ 360033162192 tablo görsel |
| Likidasyon formülü metni | **kısmen** | FAQ b3c689c1… (güncelleme 2025-12-31): değişken tanımları ve "Maintenance Margin = Notional Position Value × Maintenance Margin Rate − Maintenance Amount" **metin olarak** doğrulandı; formülün kendisi **görsel** ve bu ortamda görüntülenemedi (sayfa `curl` 202; WebFetch metin) → **aktarım yapılmadı, uydurulmadı** |
| Maker fee, BNB indirimi, tarihsel tarife | açılmadı (karar) | — |

Formül provenance (metin kısmı): `https://www.binance.com/en/support/faq/detail/b3c689c1f50a44cabb3a84e663b81d93`,
"Published on 2020-06-11 09:01, Updated 2025-12-31 05:00"; değişkenler: WB (Wallet Balance),
TMM₁ (diğer sözleşmelerin bakım marjı), UPNL₁, cumB/cumL/cumS (bakım tutarı), Side₁BOTH,
Position₁BOTH, EP₁BOTH, MMRB/L/S. Görsel formül metne dökülünce bu bölüm güncellenir.

## 4. Sonraki adım (Scryne)

Vadeli okuma yetkili anahtar (yalnız `commissionRate` + `leverageBracket`; işlem/çekim
kapalı) → `uv run python tools/faz16_vadeli_okuma.py` → §1 tablosu güncellenir → bağımsız
doğrulama (ikinci koşu, hash eşleşmesi; kademeler FAQ metniyle tutarlılık) → metodoloji
minimum şartları kontrolü → ayrı rapor. Stres/likidasyon hesabı **yok**.
