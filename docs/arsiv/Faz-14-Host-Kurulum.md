---
proje: ScryneQuant
faz: 14
tarih: 2026-09-17
type: runbook
durum: host ayakta, host-1 koşuyor, yeniden başlatma tatbikatı geçti
---
# Faz 14 — Sürekli açık host kurulumu (K-063)

Host Scryne'ın **ikinci bilgisayarı**: Windows 11 (build 26200), i5-12400F, 16 GB RAM,
kablolu ağ, ev ağında `192.168.1.4`, kullanıcı `Scryne\scryn`. Ana makine (`192.168.1.5`)
araştırmayı taşır; host yalnızca canlı paper/gözlem koşusunu taşır.

## 1. Erişim: SSH, yalnızca anahtar, yalnızca ev ağı

Scryne'ın hostta elle yaptığı tek adım yönetici PowerShell'de OpenSSH sunucusunu açmaktı.
Sonrası ana makineden SSH ile yapıldı.

| Ayar | Değer | Doğrulama |
| --- | --- | --- |
| Anahtar | `~/.ssh/scrynequant_vps` (ed25519, yalnızca bu host) | `administrators_authorized_keys` |
| `PasswordAuthentication` | `no` | `sshd -T`; parolayla deneme → `Permission denied (publickey)` |
| `KbdInteractiveAuthentication` | `no` | aynı |
| Güvenlik duvarı | `OpenSSH-Server` kuralı `RemoteAddress = LocalSubnet`, profil Private | `Get-NetFirewallAddressFilter` |
| Uyku / hazırda bekleme (AC) | hiçbir zaman (`0`) | `powercfg /query` |
| Windows Update etkin saatler | 09:00-03:00 | kayıt defteri |

Bağlanmak: `ssh -i ~/.ssh/scrynequant_vps scryn@192.168.1.4`

**Öğrenilen iki tuzak:**

1. `sshd_config`in sonuna eklenen satır Windows varsayılan dosyasındaki `Match Group
   administrators` bloğunun **içine** düşer ve yalnızca o grupta geçerli olur. Global ayar
   dosyanın **başına** yazılmalı; `sshd -T` ile doğrulanmalı.
2. SSH oturumu içinden `Restart-Service sshd` oturumu koparır. Oturum içinden başlatılan
   arka plan işi (`Start-Job`) ise oturumla birlikte ölür ve servis hiç yeniden başlamaz.
   Güvenli yol: SYSTEM hesabıyla 20 sn sonrasına tek seferlik zamanlanmış görev, sonra silinir.

## 2. Ortam

- `uv` 0.12.15 (`%USERPROFILE%\.local\bin\uv.exe`), CPython 3.12.14, `uv sync --frozen`.
- Kod: `%USERPROFILE%\Documents\Projeler\ScryneQuant`. Depo private; hosta GitHub kimlik
  bilgisi **konmadı**. Kod ana makineden `git bundle` ile gider.
- Test paketi hostta: **1.529 geçti, 2 atlandı** (funding verisi yok; bilinçli TA-Lib sapması).
- Veri: `sq data indir BTCUSDT 1h --yil 1` → 8.766 bar, kalite %100, 3,4 sn. Binance REST
  hosttan erişilebilir.

## 3. Koşu: `host-1`

| | |
| --- | --- |
| Görev | `ScryneQuant-Paper`: açılışta, oturum açmadan (S4U), çökerse 1 dk arayla yeniden başlar, süre sınırı yok |
| Komut | `tools\paper-kosu.ps1 -KosuAdi host-1 -Strateji ema_kesisim -Mod gozlem -Port 8787` |
| Başladı | 2026-09-17 14:29:39 UTC, temiz başlangıç |
| Mod | **gözlem** — promotion kanıtı üretmez (K-035); ölçülen şey hostun dayanıklılığı (K-055) |
| Kayıt | `runs\paper\host-1.sqlite` (koşunun tamamı), `runs\paper\host-1.log` |
| Dashboard | `http://127.0.0.1:8787` (yalnızca host içinden; ağa açılmadı) |

Neden tek sembollü ve gözlem: paper motoru bugün tek sembollü. Çok enstrümanlı paper motoru
Faz 14'ün işi; hazır olana kadar 30 günlük dayanıklılık sayacı bu koşuyla işler.

## 4. Operasyon

**Durum:**
```
ssh -i ~/.ssh/scrynequant_vps scryn@192.168.1.4 "cd %USERPROFILE%\Documents\Projeler\ScryneQuant && .venv\Scripts\python.exe -m scryne_quant.cli.main paper durum host-1"
```

**Kod güncelleme (planlı durdurma kesinti sayılmaz, K-043):**
1. Ana makinede: `git bundle create scrynequant.bundle master` → `scp` hosta.
2. Hostta: `sq paper durdur host-1 --sebep "kod guncellemesi"`.
3. Hostta: `git pull <bundle> master`, `uv sync --frozen`, testler.
4. `Start-ScheduledTask ScryneQuant-Paper` (ve `ScryneQuant-Evren`). **Zorunlu adım:** düzgün
   kapanan koşuyu görev yeniden başlatmıyor; `RestartCount` yalnızca sıfırdan farklı çıkışta
   devreye giriyor (2026-09-17'de görüldü). Aynı gün bulunan ikinci kusur: başlatıcı betikler
   python'un çıkış kodunu geçirmiyordu, yani **çökme de** yeniden başlatılmıyordu —
   `exit $LASTEXITCODE` eklendi (100dea6).

**Görevi kaldırmak:** `Unregister-ScheduledTask -TaskName ScryneQuant-Paper -Confirm:$false`

## 3b. Koşu: `evren-kiyas` (2026-09-17)

| | |
| --- | --- |
| Görev | `ScryneQuant-Evren`: açılışta, S4U, çökerse 1 dk arayla yeniden başlar (`tools\evren-gorev-kur.ps1` kurar) |
| Komut | `tools\evren-kosu.ps1 -KosuAdi evren-kiyas` → `sq paper evren-baslat` |
| Strateji | `evren_esit_agirlik` yeniden_dengele_bar=168, azami_enstruman=10, azami_agirlik=0,02, hedef_brut=0,2 — kıyas (K-030), aday değil |
| Mod | gözlem; kayıt `runs\paper\evren-kiyas.sqlite`, günlük `runs\paper\evren-kiyas.log` |
| Evren tablosu | `runs\paper\evren-kiyas.evren.parquet` (araştırma tablosunun kopyası `b06857c0…`) |
| Yenileme | `ScryneQuant-EvrenTablo`, her gün 06:15 TR (03:15 UTC); günlük `runs\paper\evren-kiyas.yenileme.log` |
| Veri deposu | `data\evren` ana makineden kopyalandı (735 sembol). Doğrulama: hostta Ağustos kopyasından uzatılan tablo araştırma hash'ini bit düzeyinde verdi. `tar` Çince adlı bir sembolü (`币安人生USDT`) atladı, `scp` ile ayrıca taşındı. |

**Durum:** `sq paper evren-durum evren-kiyas`

## 3c. Bütün görevler (2026-09-17 akşam)

`tools\evren-gorev-kur.ps1` idempotent kurar. Saatler TR (UTC+3).

| Görev | Ne | Zaman |
| --- | --- | --- |
| `ScryneQuant-Paper` | `host-1` tek sembollü gözlem (30 gün sayacı) + dashboard | açılışta |
| `ScryneQuant-Evren` | `evren-kiyas`: kıyas, n=10, haftalık | açılışta |
| `ScryneQuant-EvrenFB` | `evren-funding-basis`: #46, `--turev` | açılışta |
| `ScryneQuant-EvrenNFCI` | `evren-makro-nfci`: #48, `--makro nfci` (FRED anahtarı `.env`) | açılışta |
| `ScryneQuant-Izleme` | `sq izle kontrol --bildir` | 15 dk |
| `ScryneQuant-Yedek` | `sq paper evren-yedek` | 05:30 |
| `ScryneQuant-EvrenTablo` | evren tablosu yenileme (üç koşu) | 06:15 |
| `ScryneQuant-EvrenSapma` | canlı-backtest sapması (üç koşu) | 06:45 |
| `ScryneQuant-Ozet` | günlük özet bildirimi | 09:00 |
| `ScryneQuant-Pano` | salt okunur gözlem panosu, port 8788 (`tools\pano.py`) | açılışta |

## 3d. Gözlem panosu (2026-09-18, port 8788)

**Neden ayrı bir süreç:** 8787'yi `host-1`in **kendi süreci** servis ediyor ve yalnızca o
koşuyu tanıyor — tek sembol, 1 fill. İşlemlerin tamamı üç evren koşusunda ve onların arayüzü
yoktu. Panoyu koşunun içine eklemek onu yeniden başlatmayı gerektirirdi; K-069 penceresi
açıkken bu ölçümü silerdi.

**Salt okunur** (`live/evren_pano.py`): her okuma anlık kopyadan (`anlik_kopya`, günlük
yedeğin kullandığı SQLite online backup yolu), yalnızca `GET` uçları, gölge yeniden üretim
audit defterine yazmıyor. Testler `tests/unit/test_evren_pano.py`.

**Pencere ortasında nasıl kuruldu — ve neye dokunulmadı.** Hosta **yalnızca yeni dosyalar**
kopyalandı: `src/scryne_quant/live/evren_pano.py`, `.../evren_kurulum.py`, `tools/pano.py`,
`apps/web/dist/pano.html` ve yeni asset'ler. Çalışan görevlerin içe aktardığı tek bir dosya
(`cli/main.py` dahil) değişmedi — `tools/pano.py` tam olarak bunun için var, `sq paper pano`
ile aynı işi CLI'ya dokunmadan yapıyor. Eski `dist/index.html` ve asset'leri yerinde duruyor,
8787 etkilenmedi. **Host bu yüzden master'ın 17 commit gerisinde bırakıldı** (K-073 "Yan
doğrulama": canlı yolu etkileyen tek değişiklik K-070 ve `esit_agirlik=True` altında 1.000
vakada 0 fark ölçüldü). Senkronlama pencere kapandıktan sonra, K-043'ün planlı durdurma
yordamıyla yapılır.

**Geri yükleme tatbikatı (2026-09-17 20:05 TR):** üç koşunun yedeği alındı, her biri boş
dizinde yeniden üretildi: kayıtla ve canlıyla bit düzeyinde aynı (`evren-kiyas` 772 adım, 8
işlem, özkaynak 9997.863289282135; yeniden üretim 1,0-1,4 sn). Raporlar
`runsaz14	atbikat-<kosu>.json`.

**İlk simüle işlemler (20:00 TR):** `evren-kiyas` 10 hedef üretti, 8'i doldu; ZECUSDT ve
NEARUSDT risk motorunun oynaklık limitine takıldı (saatlik ATR oranı %2,6 / %2,4, eşik %2,05).
Ana makinedeki eş duman koşusu aynı özkaynağı bit düzeyinde üretti. **Not:** evrende RLUSDUSDT
(bir stablecoin) var — evren kuralının stabil taban listesinde yok. Araştırma tablosu aynı kuralla
kurulduğu için parite doğru; kuralın kendisi sonraki bir program kaydında düzeltilmeli, koşu
ortasında değiştirilemez.

## 4b. Anahtar ayrımı denetimi (2026-09-17 20:43 TR) — Faz 14 kriteri ✅

`tools/faz14_anahtar_denetimi.py`, tek salt okunur imzalı çağrı
(`GET /sapi/v1/account/apiRestrictions`). Anahtar ve sır yalnız ana makinenin `.env`inde
(`BINANCE_API_KEY`, `BINANCE_API_SECRET`); hiçbir çıktıya yazılmadı, hosta **kopyalanmadı**
(hostun ihtiyacı yok: gözlem koşuları herkese açık uçları kullanıyor). Rapor
`runs/faz14/anahtar-denetimi-2026-09-17.json`, anahtar parmak izi `f5662f703f58`.

| Yetki | Değer |
| --- | --- |
| Okuma | açık |
| Spot/marjin işlem, vadeli, marjin, opsiyon, portföy marjin, FIX işlem | **kapalı** |
| Çekim | **kapalı** |
| İç transfer, evrensel transfer | **kapalı** |
| IP kısıtı | yok |

Sonuç: `cekim_kapali = true`, `salt_okunur_anahtar = true`. Okuma anahtarı ile işlem anahtarı
ayrı: işlem yetkili anahtar bugün **yok**; Faz 8'de ayrı anahtar olarak, IP kısıtlı ve elle
onayla gelir (K-050). **Öneri:** okuma anahtarına da IP kısıtı eklenmesi (ev IP'si sabitse);
sızarsa bile yalnızca okuma yetkisi var.

## 5. Açık kalemler

1. ~~Yeniden başlatma tatbikatı~~ → **yapıldı**, §6.
2. Süreç dışı kill switch, alarmlar/runbook, çok enstrümanlı paper motoru (Faz 14 bitti kriteri).
3. Dashboard'a ana makineden erişim (ağa açmak ayrı bir karar: şu an yalnızca host içi).

## 6. Yeniden başlatma tatbikatı (2026-09-17)

Ana makineden SSH ile: planlı durdurma → kod güncellemesi (`8e51933`, hostta 1.562 test geçti)
→ `shutdown /r`. Kimse oturum açmadı.

| Zaman (UTC) | Olay |
| --- | --- |
| 15:00:10 | `host-1` ilk barını (14:00) işledi |
| 15:00:55 | `durdu` — sebep "kod guncellemesi ve yeniden baslatma tatbikati", kesinti sayılmadı (K-043) |
| 15:02:33 | yeniden başlatma komutu |
| 15:03:03 | host açıldı (`LastBootUpTime`), oturum açan kullanıcı **yok** |
| 15:03:20 | `ScryneQuant-Paper` görevi kendiliğinden başladı (S4U) |
| 15:03:30 | `kod_degisti` olayı (a25b1fd → 8e51933) |
| 15:03:32 | `basladi`, `toparlandi` (pencere 1.000 bar) |

**Kesinti sayısı: 0.** Açılıştan koşunun toparlanmasına 29 saniye.

## 3e. Tek komut ve Jev gölgesi (2026-09-20, K-074)

`tools\servisler.ps1 kur|baslat|durum|durdur` bütün görevleri tek noktadan yönetir
(`docs/arsiv/Runbook.md` "Tek komut"). Yeni görev: **`ScryneQuant-Jev`** → `tools\jev-kosu.ps1
-KosuAdi golge-1` → `sq jev golge`. Ayrı süreç, ayrı defter (`runs\jev\golge-1.sqlite`), emir
yok; `TYPESAFE_API_KEY` hostta **kullanıcı ortam değişkeni** olarak durur (`.env`de değil).
Pano (8788) Jev'i `/api/jev`, `/api/jev/<kosu>`, sağlık şeridini `/api/servisler` ile okur;
`apps\web\dist` ana makinede `npm run build` ile üretilip kopyalanır.

Hosta kurulum sırası: bundle → `uv sync --frozen` → testler → `setx TYPESAFE_API_KEY ...`
(yeni oturum) → `servisler.ps1 kur` → `servisler.ps1 baslat` → `servisler.ps1 durum`.

**Pencere içinde nasıl kuruldu (2026-09-19 21:55 UTC).** K-069 penceresi (→ 2026-09-25) açık
olduğu için bundle senkronu **yapılmadı**; 3d'deki kalıp tekrarlandı: hosta yalnızca **yeni**
dosyalar gitti (`src/scryne_quant/jev/`, `src/scryne_quant/cli/jev.py`, `config/jev.json`,
`tools/jev-kosu.ps1`). `jev-kosu.ps1` bu yüzden `cli.main jev` yerine doğrudan
`python -m scryne_quant.cli.jev golge` çağırıyor — hosttaki `cli/main.py` (3a74ebf) Jev alt
komutunu tanımıyor ve çalışan görevlerin içe aktardığı hiçbir dosya değişmedi. Jev'in
`features.indikator`dan kullandığı 7 fonksiyon (atr, bollinger, ema, en_dusuk, en_yuksek, roc,
rsi) 3a74ebf'te de var; master'daki ekler (`log_degisim`) gerekmedi. `typesafe-sdk 0.6.0`
hostta zaten kuruluydu (K-061). Anahtar `setx` ile kullanıcı ortamına yazıldı, hiçbir dosyaya
ve loga girmedi. `ScryneQuant-Jev` görevi tek başına kaydedildi (`servisler.ps1 kur` diğer
görevlere dokunacağı için çağrılmadı); `--kuru` doğrulaması: pencere 1.248 bar, boşluk 0,
funding 360. Koşu **`golge-1`**, `runs\jev\golge-1.sqlite`. Ana makinedeki `golge-3` de
koşmaya devam ediyor: aynı barda iki bağımsız süreç aynı `durum_hash`i vermeli — makineler
arası determinizm kontrolü, bedava.

**Neden şimdi:** gölge kanıtı ileriye dönük bardan başka hiçbir yerden gelmiyor (K-074/3,
replay `leak_riski=true`). Her kapalı gün bir günlük örneklem kaybı; masaüstü her gün
kapanıyor (`gozlem-2`yi kesen şey). Kanıtın birikmesinin tek yolu bu koşunun hostta kesintisiz
durmasıydı.

## 7. K-069 penceresi: kesinti kaydı ve açık pozisyonlu toparlanma (2026-09-20 denetimi)

Bu bölüm K-069/1'in *"kesinti olduysa sebebi kayıtlı ve giderilmiş"* şartının **"kayıtlı"**
yarısını belgeye işler. K-069'un kapanış kararı ayrıdır ve burada verilmiyor. Kanıt kaynağı:
hostta salt okunur okunan `runs\paper\<koşu>.sqlite` `olay` tabloları, `Get-Process`,
Windows System günlüğü (`wevtutil`), `evren-kiyas.log`. Hosta ve koşulara dokunulmadı.

### 7a. Dört WebSocket kopması (2026-09-19)

| Koşu | Bağlantı başlangıcı (UTC) | `kopma` (UTC) | `yeniden_baglandi` | `kopuk_ms` | `resync_bar` | Bağlantıdan bu yana |
| --- | --- | --- | --- | ---: | ---: | --- |
| `evren-makro-nfci` | 09-17 16:50:58 (`basladi`) | 09-19 16:54:01 | 16:54:31 | 29.141 | 0 | 48 sa 03 dk |
| `evren-funding-basis` | 09-17 16:34:53 (`basladi`) | 09-19 17:01:02 | 17:01:31 | 29.636 | 0 | 48 sa 26 dk |
| `evren-kiyas` | 09-17 16:22:50 (`toparlandi`) | 09-19 17:15:02 | 17:15:31 | 29.800 | 0 | 48 sa 52 dk |
| `host-1` | 09-17 17:04:32 (`toparlandi`) | 09-19 17:47:01 | 17:47:18 | 16.575 | 0 | 48 sa 42 dk |

Dördünde `sebep` aynı: `AkisKoptu: WebSocket kapandı: CLOSED`. **Kesinti sayısı koşu başına
1** (`KOPMA ∈ KESINTI_OLAYLARI`, `live/depo.py`). `runs\izleme\alarmlar.jsonl` boş — `KOPMA`
alarmının eşiği 24 saatte >5 (Runbook), aşılmadı.

**Giderilme (ölçüldü):** yeniden bağlanma otomatik ve K-043'ün tasarladığı yoldan
(`BACKOFF[0]` 1 s → REST resync → yeni bağlantı → ilk mesajda `yeniden_baglandi`): 16,6 s tek
sembolde, ≈29,5 s 50 sembollü birleşik akışta. `resync_bar 0` beklenen değer — kopma bir bardan
kısa sürdü, tamamlanacak kapanmış bar yoktu. Kayıp bar 0, `backfilled` bar 0, toparlanma
ayrışması 0; `evren-kiyas.log` saatlik satırları 16:00 → 17:00 → 18:00 kesintisiz, `eksik 0`.
Süreçler yeniden başlamadı (`Get-Process`: dört koşu 2026-09-17'den beri aynı PID'de);
`olay` tablolarında 09-19'da başka kayıt yok.

**Kanıtla dışlananlar** (`exchange/akis.py`, `exchange/coklu_akis.py`, aiohttp 3.14.3):
- Uygulama kapatması: `kapat()` çağrılmadı, süreç aynı; kapatma `AkisKoptu` fırlatmaz.
- aiohttp heartbeat (30 s ping / 15 s pong) zaman aşımı: `WSMsgType.ERROR` üretir, `CLOSED` değil.
- 90 s okuma sessizliği: farklı metin (`"90 s boyunca mesaj gelmedi"`).
- Yeniden bağlanma hatası: `aiohttp.ClientError` adıyla yazılırdı.
- Host OS/zamanlayıcı: System günlüğü 16:00–18:30 UTC'de yalnız 16:06:47 DCOM 10010 (GameBar,
  ilgisiz); NDIS/TCPIP/DHCP/güç/uyku/Time-Service olayı yok; Windows Update indirmeleri
  22:11 UTC'de (olaydan 4,5 sa sonra); zamanlanmış görev ızgarası (`Izleme` :00/:15/:30/:45)
  kopma dakikalarıyla örtüşmüyor.
- Tek ağ kesintisi/NAT sıfırlaması/uyku: dört olay 53 dakikaya dağılmış, eşzamanlı değil.

**Sınıf: dış sonlandırma.** aiohttp `CLOSED`ı üç yoldan üretir (karşı taraftan CLOSE frame;
TCP EOF; `ServerDisconnectedError`) ve üçü de bağlantının uygulama dışından bitirilmesidir.
**Kök neden belirlenemedi:** kapanış kodu (`ws.close_code`) ve `ws.exception()` hiçbir yere
yazılmıyor; sunucunun düzenli kapatması ile yol üstünde kopma bu kayıtla ayrılamaz. Binance'in
belgelenmiş 24 saatlik bağlantı sınırı bu olayları açıklamıyor: 24 sa işaretinde (09-18
15:28–17:04 UTC) hiçbir koşuda kopma yok. **Binance tarafı bakım/duyuru kaydı kontrol
edilmedi** — o yönde kanıt yok, her iki yönde.

**Gözlemler — sebep değil:** (1) dört olay dakika sınırının +1…+2 s içinde; kayıt `except`
bloğunda anında yazıldığı için damga kapanma anını yansıtır. (2) Bağlantıdan ≈48 sa sonra,
ama ofset 3–52 dk oynuyor; sabit bir bağlantı ömrü değil ve **sebep olarak kullanılmaz**.
(3) Günün saati 16:54–17:47 UTC.

**K-055 ile karşılaştırma:** `gozlem-2` (ana makine, 2026-09-14 17:58:59 UTC) aynı imza
(`CLOSED`, 18.013 ms, `resync_bar 0`), bağlantıdan +2 sa 57 dk sonra. Aynı mekanizma sınıfı,
farklı makine ve ağ; 48 saatlik bir ömür hipotezini çürütür — bu yüzden öyle bir hipotez
(H3) **kaydedilmiyor**.

**Ön kayıtlı gözlem hipotezleri** (pencere 2026-09-20 → 2026-09-25, müdahale yok; tutmaları
kök nedeni **kanıtlamaz**, yalnız sınıfı daraltır):
- **H1 (dakika tiki):** bir sonraki her `CLOSED` olayı dakika sınırının ±2 s içindedir.
  Bandın dışına düşen tek olay H1'i çürütür.
- **H2 (saat bandı):** sonraki olaylar 16:54–17:59 UTC bandındadır. Zayıf; band dışı tek
  olay yeter.

**Pencere sonrası backlog (kod, şimdi yapılmıyor):** `AkisKoptu` metnine `ws.close_code` ve
`ws.exception()` eklenmesi (`exchange/akis.py`, `exchange/coklu_akis.py`; ayrıca `CLOSE`
mesaj tipinin ele alınması) — kök nedeni ölçebilecek tek değişiklik. K-069 penceresi
kapanmadan hosta konamaz; senkronla birlikte değerlendirilir.

### 7b. host-1: açık pozisyonla toparlanma (2026-09-17 17:04 UTC)

§6 yalnız 15:00 tatbikatını yazıyor. `host-1.sqlite` şunu da kaydetmiş:

| Zaman (UTC) | Olay |
| --- | --- |
| 09-17 16:00:00 | `fill` #1: AL 0,016472547 BTC @ 76.820,70 (sinyal barı 15:00, fill sonraki barın açılışında — K-004) |
| 09-17 17:04:18 | `durdu` — sebep "kod guncellemesi: izleme paneli", planlı (K-043, kesinti sayılmadı) |
| 09-17 17:04:32 | `toparlandi` `{"fill_sayisi": 1, "pencere_bar": 1000, "yazim": 3, "bekleyen_dogrulandi": null}`; `host-1.log`: "toparlandı: son bar 2026-09-17 16:00:00 UTC, 1 fill" |

Pozisyon bugün hâlâ açık (`durum`: `giris_ms` 1789660800000, miktar 0,016472547, `fill_sayisi` 1,
`kapanis_ms` null). Toparlanma ayrışması 0. Bu, K-055/4'te *"toparlanmanın açık pozisyonla
canlıda sınanması (0 fill)"* diye açık bırakılan yolun **tek sembolde bir kez** çalıştığı
kayıttır. Sınırları: planlı durdurma, tek fill, tek sembol. Çok enstrümanlı yol
(`live/evren_kosturucu.py`) yalnız 09-17 16:22:50'de, adım 771'de ve pozisyon öncesi çalıştı;
`evren-kiyas` şu an 8 pozisyon taşıyor — çok enstrümanlı açık pozisyonlu toparlanma henüz
görülmedi, pencere sonrası senkron restart'ında ölçülebilir.
