---
proje: ScryneQuant
tarih: 2026-09-22
karar: K-114
type: runbook
---
# Execution Runbook — paper → shadow → testnet → live

Bu doküman sistemin **nasıl çalıştırılacağını** anlatır. Neden böyle olduğu K-114'te
(`docs/Kararlar.md`), shadow/kademe/venue tasarımı `docs/Faz-8-Hazirlik.md`de.

## 0. Tek bakışta

```
sq execution durum                     # CURRENT MODE + koşular + son raporlar
sq execution pano                      # http://127.0.0.1:8790 — SYSTEM…AUDIT, salt okuma
sq execution preflight --hedef <MOD> [--strateji S] [--ag]   # kontrol listesi, hiçbir şey yazmaz
```

Mod sırası: `DISABLED → PAPER → SHADOW → TESTNET → LIVE_PENDING_APPROVAL → LIVE`.

- **Yukarı:** `sq execution yukselt <MOD> [--ag] [--strateji S] --not "..."` — yalnızca bir adım,
  yalnızca hedef modun kontrol listesi tamamen geçerse. `LIVE` bu komutla açılmaz.
- **Aşağı:** `sq execution indir <MOD> --sebep "..."` — her zaman, onaysız.
- Sistem modu bir **tavandır**: mod SHADOW iken paper koşusu açılabilir, testnet açılamaz.

## 1. Paper (simüle borsa, gerçek emir yolu)

```
sq execution yukselt PAPER --not "..."
# Gerçek zamanlı (public Binance barları, emir paper borsaya):
sq execution calistir --mod paper --kosu p1 --strateji sma_kesisim --timeframe 1h --sermaye 10000
# Yerel depodan tekrar oynatma (hızlı, deterministik):
sq execution calistir --mod paper --kosu p-tekrar --strateji sma_kesisim --tekrar 2000 --isinma 300
```

Emir `EmirMotoru`ndan geçer, paper borsa (`runs/execution/<koşu>/paper_borsa.sqlite`) bir sonraki
barın açılışında doldurur (K-004, slippage aleyhte K-007), emir + pozisyon mutabakatı her barda
koşar. Risk modu varsayılan `gozlem` (kanıt üretmez, K-035); `--risk-modu paper` promotion
`RISK_INCELEMESI` ister.

## 2. Shadow (gerçek hesap salt okunur, emir gönderilmez)

Ön koşul: `.env`de **salt okunur** canlı anahtar `BINANCE_API_KEY` / `BINANCE_API_SECRET`
(Binance'te "Enable Spot & Margin Trading" **kapalı**, çekim kapalı).

```
sq execution yukselt SHADOW --ag --not "..."   # apiRestrictions: işlem kapalı olmalı
sq execution calistir --mod shadow --kosu s1 --strateji <S> --sermaye <sanal> [--risk-modu shadow]
```

Açılışta anahtarın yetkisi borsadan okunur; işlem yetkili anahtarla shadow **başlamaz**. Emirler
gerçek sembol kurallarıyla kurulur ve `GOLGE` olarak yazılır. Live gate'in shadow kanıtı yalnızca
`--risk-modu shadow` koşusundan sayılır; o mod stratejinin promotion'da `LIVE_ADAYI` olmasını ister.
Kill tatbikatı (canlı host'a karşı, live gate kanıtı):

```
sq execution kill --kosu s1 --sebep "canlı host kill tatbikatı"
```

## 3. Testnet (gerçek emir, sanal para)

Ön koşul: `.env`de `SQ_BINANCE_TESTNET_API_KEY` / `SQ_BINANCE_TESTNET_API_SECRET`.

```
sq execution yukselt TESTNET --ag --not "..."
sq execution calistir --mod testnet --kosu t1 --strateji <S> --timeframe 1h --sermaye 1000
```

## 4. Live

### 4.1 Live gate (hepsi makine kontrolü)

```
sq execution preflight --hedef LIVE_PENDING_APPROVAL --strateji <S> --ag
```

| Kontrol | Ne ister | Nereden gelir |
| --- | --- | --- |
| `strateji_onayi` | Strateji promotion'da `LIVE`, zincir + audit sağlam | K-010, K-082 (`sq promotion …`) |
| `operasyon_r8` | `config/operasyon_dogrulama.json` → `r8.sonuc=PASS`, `karar=K-112`, kriter hash'i | R8 kapanışı (2026-10-09 sonrası) |
| `kademe` | `config/kademe.json`: risk sermayesi, Kademe 1 sermayesi + onay | Scryne kararı (Faz-8-Hazirlik §2) |
| `acik_kararlar` | `kararlar` altında `DECISION REQUIRED` kalmamış | Faz-8-Hazirlik §6 |
| `venue_statusu` | `config/venue_statu.json` → `sonuc=AÇIK` + kaynaklar | Faz-8-Hazirlik §3 (Scryne) |
| `shadow_live_kaniti` | Aynı strateji, `shadow` risk modu, ≥14 gün, ≥20 GOLGE, kural reddi/pozisyon farkı/saat sıçraması/kesinti 0 | Faz-8-Hazirlik §1.5 |
| `testnet_kaniti`, `paper_kaniti` | Uçtan uca geçen koşu raporu | `rapor.json` |
| `kill_tatbikati` | Canlı host'a karşı başarılı `kill.json` | K-065 |
| `testler` | `sq execution test-kaydet` — HEAD'de, temiz ağaç, 0 kalan | K-009 |
| `kritik_hata_yok` | Açık SAFE_MODE / halt / UNKNOWN yok | K-008, K-038 |
| `islem_anahtari_yetkisi` | `SQ_BINANCE_LIVE_API_KEY`: spot işlem açık; çekim/transfer/margin/futures kapalı; **IP kısıtlı** | Faz-8-Hazirlik §1.2/§1.6 |
| `canli_baglanti`, `r8_sozlesmesi`, `risk_config`, `mod_kaydi` | — | — |

### 4.2 İlk canlı koşu yordamı

1. Promotion'u geçen strateji (K-010) ve R8 PASS (K-112) — ikisi de önceden varsayılmaz.
2. `config/venue_statu.json` (Faz-8-Hazirlik §3.1 biçimi) kaynaklı doldurulur.
3. `config/kademe.json`: `risk_sermayesi_usdt`, Kademe 1 `sermaye_usdt` (shadow notional p5 /
   minNotional marjından), `aktif_kademe: 1`, onay notu + tarih; `kararlar` kapatılır — her biri K.
4. Aynı stratejiyle `--risk-modu shadow` shadow koşusu ≥14 gün; bu sırada canlı host kill tatbikatı.
5. İşlem anahtarı **şimdi** üretilir: spot işlem açık, çekim/transfer/margin/futures kapalı, IP
   kısıtlı (host-1 IP'si). `.env`e `SQ_BINANCE_LIVE_API_KEY` / `_SECRET`. Salt okunur anahtar kalır.
6. `sq execution test-kaydet` (temiz ağaç).
7. `sq execution yukselt LIVE_PENDING_APPROVAL --strateji S --ag --not "..."`
8. `sq execution preflight --hedef LIVE --strateji S --ag` → raporu oku, `hash`i not et.
9. `sq execution onayla --strateji S --hash <hash> --not "<≥20 karakter gerekçe>"` — terminalde
   `CANLI <hash8>` yazılır. Kapı onay anında yeniden çalışır; hash tutmazsa onay yok.
10. `sq execution calistir --mod live --kosu live-k1 --strateji S` — yetki her başlangıçta yeniden
    türetilir; sermaye kademe sermayesiyle sınırlı; risk modu `live`.

Onaydan sonra kodda commit, kademe, strateji aşaması, anahtar yetkisi gibi **karar değiştiren** bir
şey değişirse canlı koşu başlamaz: 7-9 yeniden.

### 4.3 Mikro canlı pilot (K-115) — bugün açılabilen tek canlı yol

`config/kademe.json` aktif kademe 1 = `pilot`: sermaye 100 USDT, **10 USDT kayıpta SAFE_MODE**, strateji
`sma_kesisim` BTCUSDT 1h. Promotion, R8 ve shadow kanıtı istenmez; yerine kodda sabit tavanlar
(`canli_kapi.PILOT_*`) ve hesap değeri kontrolü. Alfa iddiası yok — beklenen getiri ≈ −komisyon; amaç
gerçek emir yolunu ölçmek.

1. **Binance'te işlem anahtarı üret** (API Management → Create API → System generated):
   - ✅ Enable Reading, ✅ **Enable Spot & Margin Trading**
   - ❌ Withdrawals, ❌ Margin loan/repay, ❌ Futures, ❌ Universal/Internal transfer, ❌ Options
   - **Restrict access to trusted IPs only** → bu makinenin genel IP'si (`curl -s https://api.ipify.org`).
     IP değişirse anahtar çalışmaz; Binance'te IP güncellenir ve 5-10. adımlar yeniden.
2. `.env`e ekle (salt okunur `BINANCE_API_KEY/SECRET` kalır — hesap değeri kontrolü onu kullanır):
   ```
   SQ_BINANCE_LIVE_API_KEY=...
   SQ_BINANCE_LIVE_API_SECRET=...
   ```
3. **Spot cüzdana 90-150 USDT** (öneri: tam 100) yatır. Hesapta başka varlık bırakma: toplam değer
   150 USDT'yi aşarsa kapı kapanır (işlem anahtarı bütün hesaba erişir).
4. Canlı host kill tatbikatı yoksa (preflight `kill_tatbikati` kalırsa): kısa bir shadow koşusu aç ve
   çalışırken öldür — `sq execution calistir --mod shadow --kosu kill-1 --strateji sma_kesisim
   --sermaye 100` (ayrı terminal) → `sq execution kill --kosu kill-1 --sebep "canlı host kill tatbikatı"`
   → `sq execution kosu-kapat --kosu kill-1 --not "tatbikat koşusu"`. (Mod SHADOW'un altındaysa önce
   bir adım yükselt; şu an TESTNET, yani izinli.)
5. Temiz ağaçta: `sq execution test-kaydet`
6. `sq execution preflight --hedef LIVE_PENDING_APPROVAL --strateji sma_kesisim --ag` → hepsi ✓ olmalı.
7. `sq execution yukselt LIVE_PENDING_APPROVAL --strateji sma_kesisim --ag --not "K-115 pilot"`
8. `sq execution preflight --hedef LIVE --strateji sma_kesisim --ag` → `hash`i not et.
9. `sq execution onayla --strateji sma_kesisim --hash <hash> --not "K-115 mikro canlı pilot, 100 USDT, 10 USDT kayıp tavanı"`
   → terminalde `CANLI <hash8>` yaz.
10. `sq execution calistir --mod live --kosu pilot-1 --strateji sma_kesisim` (risk modu kademeden
    `pilot` gelir). Süreç açık kaldığı sürece çalışır; bilgisayar uykuya geçerse durur, aynı komutla
    kaldığı yerden devam eder (kalıcı durum + başlangıç mutabakatı). İzleme: `sq execution pano`.

Durdurmak: `sq execution durdur --kosu pilot-1` (planlı) ya da `sq execution kill --kosu pilot-1 --sebep
"..."` (acil). Kayıp tavanı tetiklenirse koşu artıran emir göndermez; açık BTC pozisyonu strateji çıkış
sinyaliyle ya da elle kapatılır. Sermaye/kayıp artışı = kod + test + yeni K (config'den yapılamaz).

## 5. Acil durum

| Durum | Komut | Etki |
| --- | --- | --- |
| Hemen dur | `sq execution kill --kosu K --sebep "..."` | SAFE_MODE işareti → süreç öldürülür → açık emirler iptal (canlıda yalnız-iptal adaptör, emir açamaz) → doğrulama |
| Planlı dur | `sq execution durdur --kosu K` | Sonraki döngüde temiz kapanış + kapanış mutabakatı |
| SAFE_MODE kaldır | `sq execution safe-kaldir --kosu K --not "..."` | Yalnız elle, gerekçeyle (K-008/4) |
| Modu düşür | `sq execution indir DISABLED --sebep "..."` | Onaysız; **çalışan koşular da** bir sonraki artıran emirde durur (azaltanlar geçer) |
| Koşuyu kalıcı kapat | `sq execution kosu-kapat --kosu K --not "..."` | Halt/SAFE_MODE'lu koşu arşive geçer, bir daha başlatılamaz, live gate'i tutmaz |

Otomatik olanlar (riski azaltan, K-050): borsa ölçümlü drawdown → SAFE_MODE; mutabakat uyuşmazlığı,
yetim emir, açıklanamayan pozisyon farkı → **halt** (hiçbir emir, çıkış dahil — gerçek durum
bilinmiyor); bağlantı hatasında artıran emir yok; hız sınırına yaklaşınca yazma gönderilmez.
Kill açık pozisyonu **kapatmaz** (K-008/2, spot). Adaptör kurulamasa da (anahtar/dosya yok) SAFE_MODE işareti yazılır ve süreç sonlandırılır; açık emirler doğrulanamadığı için rapor başarısız döner.

Mutabakat **yapılamadığında** (borsa okunamadı, bozuk yanıt) artıran emir gitmez; koşu başında da ilk mutabakat geçene kadar. Aynı koşu iki süreçle, iki ayrı canlı koşu aynı anda açılamaz (kilit). Kanıt dosyaları (`rapor.json`, `kill.json`) koşunun audit zincirindeki hash'le tutmuyorsa live gate onları kanıt saymaz.

## 6. Dosyalar

`runs/execution/` (`.gitignore`): `mod.json` (zincirli mod kaydı), `preflight-<MOD>.json`,
`testler.json`, `<koşu>/{kosu.json, durum.json, rapor.json, emirler.sqlite, paper_borsa.sqlite,
audit.sqlite, risk.json, yurutucu.json, kill.json, kosu.safemode, kosu.pid, kosu.dur}`.
