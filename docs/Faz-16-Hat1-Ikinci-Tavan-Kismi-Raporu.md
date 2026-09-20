---
proje: ScryneQuant
faz: 16
tur: ölçüm — ikinci tavanın erişilebilen katmanları ("eksik sınıf" yaklaşımı, tasarım §9/§10)
tarih: 2026-09-20
type: rapor
durum: DATA BLOCKED — eksik katman (perp fee), eksik sınıf (likidasyon eşiği); CLOSE/ELIGIBLE verilmedi
---
# Hat 1 — İkinci tavan, kısmi: erişilebilen katmanlar ve eksik sınıf

**Karar çerçevesi (Scryne, 2026-09-20):** vadeli hesap açılmıyor; fee (`commissionRate`) ve
MMR kademeleri (`leverageBracket`) **BLOCKED** (`enableFutures=false`, Spike 8); PIT ve
NON_PIT MMR **EMPTY**; likidasyon-eşiği stres sınıfı **CLOSED / hesaplanamaz**; alternatif
uç, spot→perp taşıma, güncel MMR'yi geçmişe uygulama, varsayım **yok**. Bu rapor bloke
girdileri aşmaz; her sayı **üst sınır** ya da **ara ölçüm**dür ve `gecici_maliyet_modeli`
mutlak engeli altındadır (K-007, `research/kapilar.py::MUTLAK_ENGELLER`). **Resmi kapı
sonucu değildir.** Tasarım §10 kuralı uygulanamaz → **DATA BLOCKED — eksik katman**.

Betik `tools/faz16_hat1_ikinci_tavan_kismi.py` → `runs/faz16/hat1_ikinci_tavan_kismi.json`;
iki koşuda içerik hash'i aynı (`8fb5d248…`). Girdiler: Adım 0 (`carry_tavan.json`), A ölçümü,
B-1 perp slippage, `config/maliyet.json`, DTB3 (hash'ler JSON'da). IS 2020-01 → 2025-02-16.
Kapsam **BTC ve ETH** — perp slippage yalnız bu ikisinde ölçüldü (B-6); 28'lik havuz için
(2)–(4) DATA BLOCKED, yalnız ideal (13,80 %/yıl, Sharpe 6,55).

## 1. Aşama (2) — maliyet-düzeltilmiş ÜST SINIR (`r_gross_ust_sinir_fee0`)

Açılış+kapanış = 2·(fee_spot 10,0 + slip_spot) + 2·(**fee_perp = 0** + slip_perp); BTC slip_spot
5,30 (K-021), ETH kalibre değil → 0 (A-6); slip_perp BTC 7,11 / ETH 9,11 (B-1). δ-dengeleme
ihmal edilebilir (A-6), eklenmedi. Toplam: **BTC 44,8 bps, ETH 38,2 bps** — fee_perp ≥ 0
olduğundan gerçek maliyet bundan büyük, `r_gross` bundan küçük.

| Sembol | İdeal r_pos | H=30 g | H=90 g | H=365 g |
| --- | ---: | ---: | ---: | ---: |
| BTC (%/yıl, Sharpe) | 14,20 / 9,48 | 8,74 / 5,84 | 12,38 / 8,26 | 13,75 / 9,18 |
| ETH | 17,09 / 8,80 | 12,44 / 6,41 | 15,54 / 8,00 | 16,71 / 8,60 |

Tutma süresi belirleyici: H=30'da amortisman ideal getirinin %38'ini (BTC) yer — fee daha
eklenmeden. H seçilmedi; ızgara.

## 2. Aşama (3) — fırsat-maliyetli ÜST SINIR (`r_excess`, DTB3 BEY, K-060 PIT)

Sermaye tabanı `N(1+m+b)`; excess = `r_cap − r_bey`; benchmark IS ortalaması BEY %2,60
(2020 0,37 · 2021 0,05 · 2022 2,05 · 2023 5,20 · 2024 5,11).

| H=90 g, r_excess %/yıl / excess Sharpe | L1 b0 | L1 b=m | L2 b0 | L3 b0 | L5 b0 | L5 b=m |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC | 3,59 / 4,59 | 1,52 / 2,84 | 5,65 / 5,49 | 6,68 / 5,80 | 7,71 / 6,04 | 6,24 / 5,68 |
| ETH | 5,17 / 5,14 | 2,58 / 3,76 | 7,76 / 5,84 | 9,05 / 6,08 | 10,35 / 6,27 | 8,50 / 5,99 |

H=30 BTC L1/b0: 1,77 / 2,27; H=365: 4,27 / 5,47. Tam ızgara JSON'da. Bu satırlar fee=0
üst sınırıdır; gerçek `r_excess` daha düşük. **Karar verilmez.**

## 3. Başabaş perp fee (`basabas_fee_perp_bps`) — bilinmeyeni eşiğe çevirme

Excess Sharpe'ı tam 1,04'e indiren perp taker fee (bps, tek yön); gerçek fee bu değerin
**üstündeyse** o hücre kapı altına iner. Gerçek fee bilinmiyor; karşılaştırma yapılamaz.

| bps | H=30 L1 b0 | H=30 L1 b=m | H=30 L5 b0 | H=90 L1 b0 | H=90 L5 b0 | H=365 L1 b0 | H=365 L5 b0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC | **8** | **−3** | 17 | 68 | 94 | 346 | 452 |
| ETH | 21 | 10 | 30 | 102 | 128 | 471 | 576 |

Okuma (ölçüm, karar değil): H=30'da BTC L1 için tolerans 8 bps, tamponlu (b=m) hâlde
**negatif** — yani fee sıfır olsa bile kapı altı. H=90 ve 365'te tolerans onlarca/yüzlerce
bps. Fee'nin belirleyiciliği H'ye bağlı; H seçimi bir karar ve burada yapılmadı.

## 4. Aşama (4) — stres: yalnız erişilebilen sınıflar (yıllık getiri, %)

Temel = (2) üst sınırı. Senaryolar A-1/A-3/A-2 dağılımlarından, `STRES_SENARYOLARI`
çarpanlarından; parametre seçimi yok, ızgara. **Likidasyon eşiği: CLOSED** (satır boş).
**Execution `fee_2x`/`hepsi_2x`: KISMİ** (yalnız spot fee ×2; perp fee yok).

| Senaryo | BTC H=30 | BTC H=365 | ETH H=30 | ETH H=365 | Tanım |
| --- | ---: | ---: | ---: | ---: | --- |
| temel | 8,74 | 13,75 | 12,44 | 16,71 | (2) |
| funding_negatif_k1 / k2 | 7,71 / 6,67 | 12,71 / 11,67 | 11,09 / 9,74 | 15,36 / 14,00 | yılda bir ek en-derin negatif koşu (A-1: BTC −1,04 %, ETH −1,35 %) ×k |
| basis_aleyhte 1g / 7g / 30g | 7,25 / 6,92 / 6,59 | 13,63 / 13,60 / 13,57 | 10,59 / 10,32 / 9,94 | 16,56 / 16,54 / 16,50 | çıkışta p99 aleyhte Δbasis, H'ye amortize |
| execution slippage_2x / 3x | 5,72 / 2,70 | 13,50 / 13,25 | 10,22 / 8,01 | 16,53 / 16,35 | spot+perp slippage çarpanı |
| execution fee_2x / hepsi_2x **KISMİ** | 6,31 / 3,29 | 13,55 / 13,30 | 10,01 / 7,79 | 16,51 / 16,33 | yalnız spot fee ×2 |
| **borsa_taban0** | **−2,21** | **2,80** | **1,49** | **5,76** | faiz tabanı 0 → yalnız talep bileşeni (A-2) |
| erisim_kaybi D1 / D7 | −27,0 / −27,0 | 10,81 / 10,81 | −15,6 / −16,2 | 14,40 / 14,35 | zorunlu çıkışta azami aleyhte Δbasis (A-3 max ≈ 2,9 %), H'ye amortize; D=3 için 7g maksimumu (3g penceresi yok) |
| likidasyon_esigi | **CLOSED** | CLOSED | CLOSED | CLOSED | MMR yok |
| yüksek vol (koşullu, senaryo değil) | 298 YV günü (A-4) | | 498 | | bozulmaya girmez |

**`stres_bozulma` (temel − en kötü ölçülen; `analiz.StresSonucu.bozulma` tanımı) — ALT SINIR,
eksik sınıf nedeniyle:**

| | H=30 | H=90 | H=365 |
| --- | ---: | ---: | ---: |
| BTC (pp; en kötü) | **35,7** (erişim kaybı D1) | 11,9 (erişim kaybı D1) | **10,95** (taban 0) |
| ETH | 28,7 (erişim kaybı) | 10,95 (taban 0) | 10,95 (taban 0) |

Not: kapı `stres_dayanikliligi ≤ 0,15` OOS **toplam** getiri farkı üzerinden tanımlı; burada
yıllık oran üzerinden hesaplandı (IS, OOS değil) — kıyas yalnız mertebe içindir. Eksik sınıf
(likidasyon) eklendiğinde bozulma yalnız **artabilir**.

## 5. Bulgular (yorum değil, ölçüm)

1. **Taban bağımlılığı:** "taban 0" senaryosu tek başına 10,95 pp — BTC'de yıllık getirinin
   ≈%80'i Binance faiz bileşeni. Carry'nin gövdesi piyasa değil borsa parametresi (A-2 ile
   tutarlı).
2. **Erişim kaybı H=30'da yıkıcı, H=365'te küçük:** aynı 2,9 %'lik basis olayı kısa tutmada
   12 kez amortize ediliyor. `D` ve `H` parametre; hiçbiri seçilmedi.
3. **Fee toleransı H'ye bağlı:** H=30/L1'de 8 bps (tamponlu −3), H≥90'da onlarca bps. Gerçek
   fee bilinmediği için hiçbir hücre "geçti" denemez.
4. **Havuz için (2)–(4) yok:** perp slippage 26 sembolde ölçülmedi (B-6); BTC/ETH dışı
   sonuç yalnız ideal.
5. **Eksik sınıf:** likidasyon eşiği — MMR olmadan ne sayaç ne senaryo; `C-isolated`/`C-portfolio`
   ikisi de kapalı; C-portfolio ayrıca backlog.

## 6. Sonuç

**DATA BLOCKED — eksik katman (perp fee) + eksik sınıf (likidasyon eşiği).** Tasarım §10'un
CLOSE/ELIGIBLE kuralı uygulanmadı ve uygulanamaz; bu rapor karar vermez. Üretilen sayılar:
`r_gross_ust_sinir_fee0`, `r_excess` (üst sınır), `basabas_fee_perp_bps`, ölçülebilen beş
stres sınıfı + kısmi execution, `stres_bozulma` alt sınırı — hepsi kapı dışı. Değişmeyen:
`src/`, config, execution, K kayıtları, defter (52), eşik 1,04; Jev yok; program yok.
