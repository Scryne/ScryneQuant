---
proje: ScryneQuant
guncellendi: 2026-09-23
type: durum
---
# ScryneQuant — şu anki gerçek

**Asıl hedef (K-134, 2026-09-23):** çok varlıkta (kripto, EURUSD, US500, NAS100) sık işlem. Yürürlükteki hat
**aktif demo bot** (`scryne_quant.aktif`, `sq aktif …`); gerçek para yok.
- Kripto paper: `kripto-trend` / `kripto-kirilim` / `kripto-donus` (15m, 10 sembol, long-only, 10.000 USDT simüle)
  gözetmenle ayakta; karne `sq aktif karne --hesap <ad>`, durdurma `sq aktif durdur --hesap <ad>`.
- MT5 demo (K-135): Integral Yatırım demo, `mt5-demo` = `mt5_paper` (gerçek fiyat/spread, simüle dolum; kurum
  algoritmik emri kapalı tutuyor, 10026), EURUSD/GBPUSD/XAUUSD/S&P/NASDAQ, 1h `rsi_donus`, 100.000 USD, gözetmenle
  ayakta. TR'de kaldıraçlı FX/CFD gerçek parası ≥ 50.000 TL teminat + 1:10 (SPK).
- İlk geriye bakış: 3 strateji × 3 zaman dilimi, **9/9 maliyet sonrası negatif**; 15m dönüşün brüt etkisi spot
  ücretine gidiyor. Sık işlemin asıl engeli maliyet (K-134 tablosu).
- `urun-testnet` durduruldu (gösterim hesabını paylaşıyordu). Aşağıdaki K-125/K-132 BTC yatırım hattı tarihsel/ikincil.

**Ürün (K-132, 2026-09-23):** sabit risk bütçeli sistematik yatırım — `sabit_oran`: hesabın %50'si BTC, %50 USDT,
±5 puan bant dışında yeniden dengeleme; risk profili `config/risk_yatirim.json` (yalnız maruziyet tavanı 0,5 ve işlem
başı risk 0,05 farklı). Mikro pilotun stratejisi bu kural; alfa/zamanlama iddiası yok. Geçmişte (2017-2026) azami
düşüş %56 (tam BTC %84) — beklenti değil.

**Hedef (K-125, 2026-09-23):** riski yönetilen sistematik yatırım — piyasayı yenmek değil, önceden
tanımlı kurallarla maruziyet sağlayıp büyük düşüşlerde riski azaltmak. Promotion yolu: Risk Yönetimli
Promotion Protokolü (`docs/research/Risk-Yonetimli-Protokol.md`); alfa yolu (12 kapı) aynen durur.
Faz sırası A (sistem gösterimi + R8) → B (RYPP, R13) → C (kripto strateji, R14) → D (paper, R15) → E (gerçek para).
**B kapandı (K-128):** RYPP zincirde (K-126); B-3 French verisi vintage dayanıklılığı şartıyla (202607 + 201705 eşi);
P3 k'sı = RYPP programının bütçesi.
**C ilk programı (K-130/K-131):** h64 `evren_risk_kapisi` (evren kıyası + BTC 100g kapısı) RYPP **FAIL** — kripto OOS'ta
düşüşü %21 azalttı ama zamanlama plasebodan iyi değil (maruziyet düşürme etkisi); French iki vintage da FAIL. Program kapandı.

**Takip ekranı (K-133):** `sq execution pano` → http://127.0.0.1:8790 bot ekranı (hesap değeri, denge/tetikler,
eğri, emirler, risk, pilot hazırlığı); klasik on bölümlü pano `/klasik`. Derleme: `cd apps/web && npm run build`.

Tek sayfa, **yürürlükteki** durum. "Neden böyle" için `docs/Kararlar.md`, sayılar için
`docs/research/records/` ve faz raporları. Bu sayfa ile başka bir doküman çelişirse bu sayfa ve
en yeni K kazanır; eski doküman tarihsel kayıttır.

## 1. Doğrulanmış olanlar (cevabı bilinen girdiyle, K-117/K-118)

| Bileşen | Nasıl doğrulandı |
| --- | --- |
| Tek sembollü backtest motoru | Bağımsız vektörel hesapla getiri/Sharpe 4/4 eşit (±%4) |
| Çok enstrümanlı motor | Bağımsız Decimal referans testi (`test_coklu_referans.py`) |
| Look-ahead | Her kayıtlı gösterge + her kütüphane stratejisi, 3 bozma (`test_look_ahead_genel.py`) |
| IS/OOS/walk-forward bölmesi | Kronolojik, örtüşmesiz, ısınma yalnız geriye |
| Çoklu test null'u (`oos_sharpe` 1,04) | Üstünlüksüz kahin 0/60 |
| Promotion kapıları (K-119) | Null 0/60 + gerçek defter 0/38; güçlü sentetik evren 5/6; %65 kahin 17-20/20 |
| Canlı emir katmanı (`exchange/imzali.py`) | Yazmada yeniden deneme yok, belirsiz sonuç sorgulanmadan tekrarlanmaz |
| Risk motoru → execution | Cooldown artık canlı yolda da çalışıyor (K-118) |

## 2. Strateji durumu

- **Promotion'u geçen strateji: yok.** Defter 64 çekiliş (63 alfa + 1 RYPP, h64 FAIL).
- 62 çekilişin OOS sonuçları gerçek ölçümdür: null persentili medyan 0,50 (K-110), en iyi OOS
  Sharpe 0,46. Eski kapıların güçsüzlüğü (K-117) bu sonuçları değiştirmiyor.
- h63 (kripto evren zaman serisi trend, K-120): OOS Sharpe −0,54 vs kıyas 0,30 → elendi.
- **Tükenen aileler** (tekrar denenmez): tek sembol TA, funding yönlü, kesitsel
  momentum/ters/düşük oynaklık, kıyas-üstü dışlama, rejim/Jev yönü, kurma katmanı, FX
  seçim/dönüş/oynaklık, zaman serisi trend (kripto evreni) — `docs/research/records/2026-09-22-R7-kapanis-alfa-envanteri.md` §3.
- **Carry (Hat B):** funding son 12 ay BTC %3,4/yıl; bugün risksiz getirinin altında
  (`tools/funding_guncel.py`, işaret: son 90 gün ≥ %8).
- **Vadeli long/short (K-123):** IS tavanında short bacak her pencerede risk-ayarlı getiriyi
  düşürüyor (yalnız 2022'de kazanıyor) → vadeli hesap gerekçesi yok, short mimarisi yazılmaz.
- **Açık kaynaklar:** on-chain, emir defteri, haber (ileriye toplama ister); envanter §5.

## 3. Kapılar (12, K-119)

`oos_suresi`, `oos_sharpe` ≥ 1,04 (çoklu test), `oos_is_orani` ≥ 0,5, `wf_katman_basari` ≥ 0,6,
`parametre_kararliligi` ≤ 0,35, `asgari_islem` ≥ 30, `max_drawdown` ≤ 0,25,
`stres_dayanikliligi` (OOS Sharpe oranı) ≥ 0,5, `pbo` (CSCV zarar olasılığı) ≤ 0,05,
`parametre_perturbasyonu` (komşu koruma) ≥ 0,80, `rejim_kararliligi` ≥ 0,685,
`evren_dayanikliligi` ≥ 0,75. Kayıt `config/esikler.json`; promotion 12'sinin tamamını ister.
Tek sembollü strateji `evren_dayanikliligi` yüzünden promotion alamaz — aday evren yolundan gelir.
Yeni/değişen kapı **iki yönlü** doğrulanır (null + `tools/pozitif_kontrol*.py`).

## 4. Canlı / operasyon

- **Gerçek para kuralı (K-122 → K-129):** sermaye büyütme (Kademe ≥ 2) iki hüküm ister — **sistem hazır**
  (14 günlük testnet + shadow gösterimi, kill tatbikatı, R8 PASS, HEAD'de yeşil testler) ve
  **strateji hazır** (promotion `live_adayi`). **Mikro pilot (100 USDT, 10 USDT kayıp tavanı) K-129 ile
  ayrıldı:** yeşil testler + 7 günlük temiz gösterim + kill tatbikatı yeter (`sq execution hazirlik` →
  MİKRO PİLOT; canlı kapıda `pilot_gosterim`). En erken ~2026-09-30; işlem anahtarı + ~100 USDT + elle
  onay Scryne'da.
- **Gösterim dönemi (2026-09-23 →):** `gosterim-testnet` (sanal para, gerçek borsa emri) ve
  `gosterim-shadow` (gerçek hesap, salt okunur) bu bilgisayarda; `tools/gosterim_gozetmen.ps1` +
  zamanlanmış görev `ScryneQuant-Gosterim` (10 dk) ayakta tutar; durdurmak `runs/gosterim/DURDUR`.
  İkisi de 2026-09-23'te başladı (testnet 07:31, shadow 07:38 UTC; `BINANCE_API_KEY` salt okunura
  çekildi ve shadow yetki denetimi geçti).
- **Mikro pilot (K-115/K-116/K-132):** 100 USDT, 10 USDT kayıpta SAFE_MODE, `sabit_oran` BTCUSDT 1h (%50 BTC),
  alfa iddiası yok; `urun-testnet` koşusu ürünü testnet'te gösteriyor; K-129 şartları (yeşil testler, 7 gün temiz gösterim, kill tatbikatı) ve elle onayla açılır. Yordam `docs/Execution-Runbook.md` §4.3.
- **R8:** `r8-kiyas` gözlem koşusu, host-1, 2026-09-25 başlar, 14 gün, kriterler dondurulmuş
  (`config/r8_kriterler.json`). Operasyon kanıtı, alfa değil.
- Kademe ≥ 2 (gerçek sermaye büyütme) promotion ister; tavan büyütmek kod + test + yeni K.

## 5. Jev

Yön tahmini %49 (K-074…077): işlem kararına bağlanmaz. Yürürlükteki rolü araştırma yönetişimi
(gizli tekrar dedektörü, K-061). Değerlendirilecek: duyuru/delist metni → yalnız **engelleyen**
katman (K-037 izin verir; K-074 izolasyonu yeni K ister).

## 6. Açık işler

1. Çoklu test fotoğrafı 63 çekilişe güncellendi (49 ölçülebilir; %5 sınırı 1,0039, mevcut 1,04'ün
   yanlış pozitifi 0,042). `oos_sharpe` eşiği 9 yıllık tek sembollü OOS için ayrıca kalibre edilmedi
   (uzun OOS'ta tutucu yönde).
2. `asgari_islem` 30 aylık stratejileri dışarıda bırakıyor (bilinçli; null bu çekilişlerde kalibre değil).
3. Maliyet modeli tutucu (taraf başı 10 + 5,3 bps); pilotun gerçek fill'leriyle yeniden kalibre edilir.
