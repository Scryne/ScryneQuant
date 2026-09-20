---
proje: ScryneQuant
faz: 16
tur: kaynak ölçümü (M-1 kalıbı; çekiliş değil, Jev yok, backtest yok)
tarih: 2026-09-20
type: rapor
durum: CLOSE
---
# Hat 2 / Adım 0 — Funding uzlaşma anı (00/08/16 UTC) mikroyapısı

**Sonuç: CLOSE.** Ödeme anının ±60 dakikasında, önceki ödemenin işaretine koşullu en iyi
bacağın ortalama etkisi **+0,9 bps**; maliyet 30,6 bps; net **−29,7 bps**. 32 üçlü plaseboda
sıra 5, p = 0,156. Karar kuralının iki koşulu da (net ≤ 0, p > 0,05) CLOSE diyor.

## 1. Olay tanımı

| | |
| --- | --- |
| Olay | BTCUSDT funding ödeme anı `t` — `data/funding/BTCUSDT.parquet::funding_time`, saate yuvarlı; veri penceresinde yalnız 00:00 / 08:00 / 16:00 UTC (betik başka saat görürse durur) |
| Pencere | ±60 dk, 1m `ok` barlar; `y_on = ln(close[t]/close[t−60])`, `y_son = ln(close[t+60]/close[t])` |
| Koşullama | `s` = **bir önceki** ödemenin oranının işareti — `t`de kesinleşmiş tek bilgi (o anki oran uzlaşmada kesinleşir; kullanmak look-ahead olurdu). IS'te ödemelerin %90,2'si pozitif işaretli. |
| Mekanizma (literatür) | pozitif funding'de long'lar ödemeden kaçmak için kapatır → ödemeye doğru düşüş, sonra toparlanma |
| İşaretli bacaklar | straddle `s·(−y_on + y_son)` (2 gidiş-dönüş); ön `s·(−y_on)`; son `s·y_son` (1 gidiş-dönüş); koşulsuz straddle |
| İstatistik | S = ortalama / standart hata (M-1 ile aynı) |
| Pencere | **In-sample:** 2023-08-04 → 2025-02-16 18:00 UTC (BTC tek-sembol OOS başlangıcı dışlanır); 810.103 `ok` 1m bar; **1.688 olay** |
| Veri | 1m SHA-256 `5a3b33c7…`; funding SHA-256 `900484f2…` |
| Betik | `tools/faz16_funding_uzlasma.py` → `runs/faz16/funding_uzlasma.json`; deterministik, 1 s |

## 2. Plasebo metodolojisi

M-1'in 96-çapa kalıbı, 8 saatlik yapıyı koruyacak biçimde: çapa **üçlüsü** (a, a+8h,
a+16h), a ∈ {00:00, 00:15, …, 07:45} → **32 üçlü**, gerçek olay a = 00:00. Her plasebo
üçlüsü aynı koşullama kuralıyla (çapadan önceki son ödemenin işareti) ölçülür. p =
sıra(S_gerçek) / 32, tek taraflı. Ayrıca 96 tekil çapa tablosu şeffaflık için yazıldı
(`tekil_96_capa_S`), karar için **kullanılmadı** — M-1'in kuralı: başka çapa seçilmez.

## 3. Sonuçlar

| Bacak | n | Ortalama (bps) | SE (bps) | S | Sıra / 32 | p | Maliyet (bps) | **Net (bps)** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| koşullu ön (`s·−y_on`) | 1.688 | **+0,89** | 1,31 | 0,68 | 5 | 0,156 | 30,6 | **−29,7** |
| koşullu son (`s·y_son`) | 1.688 | −1,09 | 1,22 | −0,89 | 30 | 0,938 | 30,6 | −31,7 |
| koşullu straddle | 1.688 | −0,20 | 1,79 | −0,11 | 20 | 0,625 | 61,2 | −61,4 |
| koşulsuz straddle | 1.688 | +0,05 | 1,79 | 0,03 | 17 | 0,531 | 61,2 | −61,1 |

Plasebo S dağılımı (koşullu ön): medyan −0,32, min −2,70, max 0,85. Gerçek 0,68, dağılımın
içinde. Koşullu son bacağın işareti mekanizmanın **tersi** (ödeme sonrası toparlanma yok,
hafif düşüş) ve plaseboda 30/32.

## 4. Okuma

- Etki büyüklüğü (≈1 bps) maliyetin (30,6 bps) otuzda biri. Maliyet sıfır olsa bile 1.688
  olayda S 0,68 — anlamlı değil. Bu, K-045'in "maliyet duvar değil" bulgusunun mikroyapı
  ölçeğindeki karşılığı: sinyal yok.
- Koşullama işareti %90 pozitif olduğu için "koşullu" ölçüm neredeyse koşulsuzla aynı;
  negatif funding alt örneği (n ≈ 165) ayrı raporlanacak kadar büyük değil ve rapor
  edilmedi — ayrı bir çekiliş olurdu.
- Çoklu test: dört bacak × 32 plasebo; en iyi bacağın p'si 0,156 düzeltmesiz. Düzeltme
  gerekmedi, sonuç zaten eşiğin dışında.
- 96 tekil çapa tablosu bilgi amaçlı; içinde 2,5–3 civarı S'ler var (32 üçlüde max 3,08) —
  96/32 sıfır hipotezinde beklenen en büyük değer. Seçilmedi.

## 5. Karar

**CLOSE.** Funding uzlaşma anı mikroyapısı BTC 1m'de, bu pencere ve bu tanımla, işlem
maliyetinin altında ve plasebodan ayrışmıyor. Çapa, pencere, koşullama ya da ufuk
değiştirilerek **tekrar ölçülmez** (M-1 kuralı). Program yok, defter satırı yok, açılan
karar kaydı yok.
