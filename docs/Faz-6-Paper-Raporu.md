---
proje: ScryneQuant
created: 2026-09-11
type: faz-raporu
faz: 6
status: devam-ediyor
---
# Faz 6 — Paper trading + dashboard

> **Bu faz kapanmadı ve kapanamaz.** Dört bitti kriterinden üçü karşılandı ve testle
> kanıtlı; dördüncüsü (*"30 gün kesintisiz çalışma"*) tanım gereği duvar saati ister.
> Rapor altyapının durumunu kaydediyor; koşunun sonucu 30 gün sonra bu dosyaya eklenecek.

## Bitti kriteri durumu

| Kriter | Durum | Kanıt |
| --- | --- | --- |
| 30 gün kesintisiz çalışma | ⏳ **koşu bekliyor** | — |
| Restart sonrası state doğru toparlanıyor | ✅ | `tests/unit/test_toparlanma.py` (18 test) |
| Veri akışı kesilince yeni pozisyon açılmıyor | ✅ | `tests/unit/test_paper_dongu.py::TestBayatVeriGuardi` |
| Dashboard'un 4 sayfası çalışıyor, risk ilk bakışta görünüyor | ✅ | `tests/unit/test_api.py` + uçtan uca canlı doğrulama |

Toplam **881 test** yeşil (Faz 5 sonunda 757'ydi).

## Koşu kaydı

**Başladı: 2026-09-11 06:26:43 UTC**

| Alan | Değer |
| --- | --- |
| Koşu adı | `gozlem-1` → **`gozlem-2`** (bkz. aşağıdaki denetim bölümü) |
| Mod | `gozlem` — promotion kanıtı üretmez (K-035) |
| Sembol / timeframe | BTCUSDT / 1h |
| Strateji | `ema_kesisim` {"hizli": 20, "maruziyet": 0.2, "yavas": 50} |
| Başlangıç sermayesi | 10,000 |
| Commit | `ba7e20e180b1` · dirty: **false** |
| Risk limitleri | `c3608583bd9f6d93` |
| Isınma penceresi | 1.000 bar, tamamı `backfilled` |

**Neden `ema_kesisim`:** Faz 5'in ölçümünde risk motoru altında en iyi davranan strateji
oydu (getiri −%8,3 → +%8,1, Sharpe −0,19 → +0,37) ve 1h'te düzenli kesişim üretiyor. Seçim
bir beklenti değil bir **test yükü** kararı: altyapıyı ölçmek için pozisyon açıp kapatan
bir akış gerekiyor. `al_tut` 30 günde bir-iki fill üretir ve restart-açık-pozisyon yolunu
hiç sınamaz; `cok_faktor` backtest'te drawdown limitini aşıp kill switch'i tetikliyordu ve
sonrasında hiç giriş yapmazdı.

**Nasıl çalışıyor:** Windows zamanlanmış görevi `ScryneQuant-Paper`, oturum açılışında
tetikleniyor, hata hâlinde iki dakikada bir yeniden deniyor, süre sınırı yok
(`tools/paper-kosu.ps1`). Görev kesintiyi **sıfırlamıyor**, boşluk süresini kısaltıyor:
temiz kapanmayan her oturum yine `temiz_kapanmadi` olarak kesinti sayılıyor.

Görevi kaldırmak: `Unregister-ScheduledTask -TaskName "ScryneQuant-Paper" -Confirm:$false`

İzleme: dashboard `http://127.0.0.1:8787` · `sq paper durum gozlem-1` ·
`sq paper olaylar gozlem-1`

## Ölçülen şey ne, ölçülmeyen ne

Faz 6'nın ölçtüğü şey **stratejinin kârı değil, altyapının ayakta kalması ve doğru
toparlanması**. Bu ayrım bu fazda ilk kez keskinleşti ve bir karara dönüştü (K-035).

**Ölçülmüyor ve bu kayıtlı:** paper/backtest drift üst sınırı (K-018/3'ün beşinci eşik
adayı). Faz 6'da ölçülebilir hâle geleceği yazılmıştı; gelmedi. Sebebi aşağıda.

## En önemli bulgu: paper trading'in kargosu yoktu

`MOD_ESIGI["paper"] = RISK_INCELEMESI` — yani paper modunda bir stratejinin sinyali ancak
`out_of_sample` kapısını geçtiyse risk motorundan geçer. Faz 4'te ölçülen **yedi
stratejinin yedisi de kaldı** (K-019) ve Faz 5 eşikleri gevşetmedi. Dolayısıyla bugün
başlatılan bir paper koşusunda risk motoru **her sinyali** `PROMOTION_YOK` ile reddeder.

Bunun sonucu sessiz ve tehlikeliydi: hiç pozisyon açılmayan bir koşuda *"restart sonrası
pozisyon ve emir state'i doğru toparlanıyor"* kriteri **boş yere** geçerdi. Ölçülmemiş bir
şey ölçülmüş görünürdü.

Üç seçenek vardı ve ikisi reddedildi:

- **Eşiği indirmek** — K-018'in *"sayısal eşik esnetilemez"* kuralını doğrudan deler ve
  K-019'un gevşetme dedektörünü etkisiz kılar. Kriteri ölçülebilir kılmak için kapıyı
  indirmek, kriteri ölçmenin sebebini yok eder.
- **Faz 4'e dönmek** — sıralı ve doğru, ama Faz 6'nın 30 günlük saati belirsiz süre hiç
  başlamaz ve altyapı yazılmamış kalır.
- **Gözlem modu (seçilen, K-035)** — promotion dışındaki her risk limiti tam olarak
  uygulanır; tek fark `MOD_ESIGI["gozlem"] = YOK`. O koşunun ürettiği hiçbir kayıt
  promotion kanıtı **olamaz** ve bu bir söz değil bir kısıt: `Kanit.__post_init__` gözlem
  modundan gelen paper kanıtını **kurulmadan** reddediyor.

**Bunun bedeli, açıkça:** gözlem koşusu 30 gün sürse bile drift eşiğini kalibre etmeye
yetmez — drift'in büyüklüğü stratejiye bağlıdır. Gözlem koşusundan çıkacak olan şey ölçüm
**yönteminin** çalıştığının kanıtı; sayının kendisi değil. O sayı, kapıları geçen ilk
stratejinin gerçek paper koşusunda ölçülecek.

## Toparlanma: geri yükleme değil, yeniden üretim (K-038)

Faz 6'nın en sert kriteri *"state doğru toparlanıyor"*du ve o cümledeki **"doğru"**
kelimesi ölçülebilir olmak zorundaydı. Kayıtlı alanları okuyup "eşit mi" diye bakmak,
kaydı kendisiyle doğrulamak olurdu.

Bunun yerine diskten okunan her sayı bağımsız bir kaynaktan yeniden üretiliyor:

| Diskten okunan | Bağımsız kaynak |
| --- | --- |
| Portföy (nakit, miktar, ort. maliyet) | `fill` defterinin baştan uygulanması |
| Bekleyen kararın özeti | Strateji + risk motorunun barı yeniden karara bağlaması |
| Risk durumu | **yok** — türetilecek bağımsız kaynağı yok, ve bu bir eksiklik olarak kayıtlı |

Bekleyen kararın saklanmaması K-032'nin sonucu: `OnayliNiyet` mühürlü ve mühür süreç
başına rastgele, yani serileştirilmiş bir onay yeniden başlayan süreçte doğrulanamaz. Onu
yeniden mühürlemek "onayın tek üreticisi risk motorudur" garantisini kırardı.

**Testin kendisi de dolaylı ve bu bilinçli:** 60 barı kesintisiz işleyen koşu ile 30 barda
öldürülüp yeniden başlatılan koşunun portföyü, risk durumu ve fill defteri **birebir** aynı
çıkıyor. Kesinti hiçbir iz bırakmıyor.

Ayrıca üç bozma senaryosu test ediliyor ve üçünde de koşu **duruyor**: kontrol noktası fill
defteriyle ayrıştığında, yeniden üretilen karar kayıtlıyla uyuşmadığında, ve kayıtlı son
bar toparlanma penceresinde olmadığında. Uyuşmazlıkta tahmin yürütülmüyor — §25'in Faz
7'de tam olarak isteyeceği davranışın habercisi.

## Üç engel, üç katman (K-037)

Faz 6 iki yeni engel getirdi ve ikisi de risk motorunun **dışında**:

1. **`ok` olmayan bar** → ne karar ne fill (K-028). Kopma sonrası REST'ten gelen barlar
   `backfilled` olduğu için bu kural, *bağlı olmadığımız sürede* fill iddia etmeyi
   kendiliğinden engelliyor. Bu, Faz 6'nın en değerli yan etkisi: downtime'da "olmuş gibi"
   bir işlem üretmek yapısal olarak imkânsız.
2. **Bayat veri** → yeni **giriş** kararı yok (§24). Azaltan niyetler geçiyor — bir çıkışı
   engellemek riski azaltmaz, artırır (K-008/3 ile aynı mantık).

K-037 asimetriyi açıkça yazdı: **engelleyen** katman risk motorunun dışında olabilir,
**izin veren** katman olamaz. §9.1/3'ün koruduğu şey "her sinyal risk motorunu görsün"
değil, "borsaya giden yolda risk motorundan geçmemiş hiçbir şey olmasın".

## Kriterin kendisinde bir boşluk vardı

Koşu başlatılmadan önce fark edildi ve kapatıldı: **süreç çökerse, elektrik giderse veya
sert öldürülürse hiçbir iz kalmıyordu.** `durdu` satırını yazacak olan sürecin kendisiydi
ve ölürken yazamaz; yeniden başlayınca kayıtta yalnızca yeni bir `basladi` görünürdü. Yani
**en sık gerçek kesinti türü kesinti sayımının dışında kalıyordu** ve *"30 gün kesintisiz
(kesinti olduysa sebebi kayıtlı ve giderilmiş)"* kriteri, ölçmediği bir şeyi ölçüyormuş
gibi görünecekti.

Çözüm geriye dönük kayıt: her başlangıçta kayıttaki son `basladi`/`durdu` satırına bakılıyor
ve `basladi` daha yeniyse `temiz_kapanmadi` yazılıyor — kesinti olarak sayılan dördüncü
olay türü. Sebep "bilinmiyor" olarak geçiyor ve bu kabul ediliyor: bilinmeyen bir sebep,
kaydedilmemiş bir kesintiden iyidir.

İlk yazım aynı çökmeyi **iki kez** saydı (art arda iki toparlanma, aradaki `basladi` hâlâ
en yeni satır olduğu için) ve bunu testi yakaladı. Tarama `temiz_kapanmadi`yi de kapsayacak
şekilde düzeltildi: bir kez kaydedilmiş kesinti kaydedilmiştir; sayacın iki kez artması
olmayan bir kesinti uydurmak olurdu.

## Koşunun tek-örnek koruması yoktu

`sq paper baslat` aynı koşu için iki kez çağrılabiliyordu ve hiçbir şey engellemiyordu —
zamanlanmış görev koşuyu tutarken elle bir `sq paper baslat` yazmak yeterliydi. Sonuç bir
çökme **olmazdı**: SQLite yazımları serileştirir. Tehlikeli olan da bu. İki trader döngüsü
aynı barları işleseydi fill defteri çiftlenir, kontrol noktası birbirinin üstüne yazılır ve
hata ancak bir sonraki toparlanmada, üstelik **yanlış sebeple** ("portföy fill defteriyle
ayrıştı") görünürdü — yani sistemin en iyi teşhis aracı yanlış yeri gösterirdi.

Çözüm işletim sistemi düzeyinde tavsiye kilidi (`live/kilit.py`), veritabanı satırı değil.
Bir `kilit` tablosuna pid yazmak cazipti ama yanlış: süreç çökünce satır kalır ve "kilitli
mi yoksa ölü mü" sorusu cevapsız kalır — `temiz_kapanmadi`nin çözmek zorunda kaldığı
problemin ikinci kopyası. İşletim sistemi kilidini çekirdek bırakır; bayat kilit diye bir
durum yoktur. Test bunu ölçüyor: kilidi tutan çocuk süreç öldürülüyor ve kilidin gittiği
doğrulanıyor. Gerçek koşuda da doğrulandı — ayakta bir koşu varken ikinci bir
`sq paper baslat` reddediliyor.

**Bu bölümün ilk hâli yanlış bir gözleme dayanıyordu ve düzeltildi.** İki `python.exe`
süreci görüp "iki koşu çalışıyor" diye okumuştum; oysa ikincisinin ebeveyni birincisiydi —
`uv`'nin sanal ortam `python.exe`'si gerçek yorumlayıcıyı çocuk süreç olarak başlatan bir
sarmalayıcı. Yani o an gerçek bir çakışma **yoktu**. Kilit yine de doğru ve gerekli, ama
"yaşanmış bir kaza" olarak değil, "korumasız bırakılmış bir yol" olarak.

**Pid hakkında ölçülen ikinci şey:** kilit dosyasına yazılan pid, kilit tutulurken
dışarıdan **okunamıyor** — Windows dosyayı başka bir sürece hiç açtırmıyor, bayt aralığı
kilidinden bağımsız olarak. Kilit baytını içeriğin dışına taşımak bunu değiştirmedi. Pid
ölüm sonrası iz olarak kalıyor ("en son kim tutuyordu"); kilit tutulurken sorulan sorunun
cevabı zaten hata mesajı.

## Bulunan hatalar

Yedisi de testler yazılırken veya uçtan uca doğrulamada çıktı.

1. **Canlı pencere kısayken ATR hesabı patlıyordu.** Backtest'te seri baştan sona elde ve
   ATR bir kez hesaplanıyor; canlıda pencere sıfırdan büyüyor ve ilk 15 barda seri
   penceresinden kısa kalıyor. Hatayı yakalayıp sıfır koymak volatilite guard'ını ve boyut
   tavanını koşunun ilk saatlerinde sessizce kapatırdı. Düzeltme `None` ("ölçülemedi")
   döndürüyor ve risk motoru ölçülemeyen guard'ı geçilmiş saymıyor.
2. **Koşu kimliğinin eşitliği `olusturuldu_ms`'i de kapsıyordu**, yani aynı koşu hiçbir
   zaman yeniden başlatılamıyordu. Kimlik ikiye ayrıldı: **konfigürasyon** (eşit olmak
   zorunda) ve **köken** (commit/dirty/kütüphane). Köken değişirse koşu durmuyor ama
   `kod_degisti` olayı yazılıyor — bir commit atmak 30 günlük ölçümü sıfırlamamalı, ama
   sessizce de geçilmemeli (K-009).
3. **SQLite bağlantıları iş parçacığına bağlıydı** ve FastAPI senkron işleyicileri bir
   havuzda çalıştırıyor. `check_same_thread` kontrolü kapatılmadı — o kontrol tam bu
   hatayı yakalamak için var; kısıt bir kilide taşındı ve uçlar `async def` yapıldı.
4. **Pencere kalite raporu bar-başına düzeltmeden önceki bayrakları sayıyordu.** Dashboard
   "1000 bar `ok`" derken motor aynı barları `backfilled` görüyordu. Aynı veriyi iki farklı
   anlatan iki sayı — ve rapor, ekranda okunan taraf.
5. **Çökme kesinti sayılmıyordu** — yukarıdaki bölüm. Kriterin kendisini ölçülebilir
   kılan düzeltme; koşu başlatılmadan önce yapıldı.
6. **Koşunun tek-örnek koruması yoktu** — yukarıdaki bölüm. Koşuyu başlatırken fark
   edildi (yanlış bir gözlem üzerinden; gözlem düzeltildi, bulgu geçerli kaldı).
7. **Arayüzde üç denetim bulgusu:** `role="tablist"` gerekli ARIA kalıbı olmadan
   verilmişti; risk şeridi SAFE_MODE'da bile `role="status"` ile sıraya giriyordu;
   `background-attachment: fixed` her kaydırmada arka planı yeniden boyatıyordu.

## Arayüz: doygunluk aciliyeti gösterir, kârı değil

`DESIGN.md`'nin karar katmanı Faz 6'dan önce yazılmıştı; bu fazda token'ları dolduruldu ve
karar katmanı **bir kez sınandı**: `ui-ux-pro-max`ın önerdiği profil `#22C55E` yeşili
"pozitif gösterge" accent'i olarak veriyordu. Reddedildi — doygunluk kuralıyla doğrudan
çelişiyor ve çelişkide `DESIGN.md` kazanıyor (proje kuralı). Tipografi eşleşmesi (Fira
Sans + Fira Code) ve yoğun boşluk ölçeği olduğu gibi alındı.

Yüksek doygunluk **tek** bir renge (`#FF5A1F`) ve yalnızca risk durumlarına ayrıldı.
Şiddet hue ile değil **doluluk** ile anlatılıyor: kenarlık → dolu zemin → tam kontrast.
Üç tonlu bir uyarı paleti (sarı/turuncu/kırmızı) ilk iki tonu birkaç haftada görünmez
yapardı.

**Cam kısıtı uygulandı:** `backdrop-filter` arayüzde **hiç** kullanılmıyor. Veri yüzeyleri
opak; cam token'ları tanımlı ama şu an tüketen bir bileşen yok (ilk modal ile gelecek).

## Üretilen paketler

`live/` (`akis`, `pencere`, `depo`, `motor`, `toparlanma`, `kosturucu`, `api`, `baslat`),
`exchange/akis.py`, `backtest/defter.py` (Faz 3'ten taşındı), `apps/web/` (Vite SPA),
CLI: `sq paper {baslat,durum,durdur,olaylar}`.

## Faz 6'nın verdiği kararlar

K-034 (operasyonel state SQLite; Postgres Faz 7'ye), K-035 (gözlem modu), K-036 (dashboard
Vite+React, FastAPI servis eder), K-037 (engelleyen katman dışarıda olabilir, izin veren
olamaz), K-038 (toparlanma yeniden üretimdir), K-043 (planlı duruş kesinti değildir).

## Koşu başladıktan sonraki denetim (2026-09-11)

Gözlem koşusu 5,5 saattir ayaktayken altyapı baştan sona denetlendi. Koşunun kendisinde
arıza yok — 0 kesinti, 0 fill (beklenen: `ema_kesisim` 1h'te saatlerce kesişim üretmeyebilir),
dashboard'un dört sayfası ve altı API ucu ayakta, canlı fiyat akıyor. Bulunan altı sorun
**altyapının 30 günü nasıl geçireceğiyle** ilgiliydi ve altısı da giderildi.

| # | Bulgu | Neden önemliydi | Durum |
| --- | --- | --- | --- |
| 1 | `exchange/akis.py` **hiç test edilmemişti** | Sınıfın kendisi — kopma döngüsü, backoff, resync, tekrar süzme — yalnızca gerçek bir kesintide ilk kez çalışacaktı. Kriterin en çok dayandığı kod, en az sınanan koddu | ✅ 20 test |
| 2 | `YENIDEN_BAGLANDI` olayı **hiç yazılmıyordu** | Enum'da tanımlı, kancası yok. Kopma kayda geçiyordu, giderilmesi geçmiyordu — kriterin *"ve giderilmiş"* yarısı boştu | ✅ kanca + kayıt |
| 3 | Bayatlık yoklaması **sessizce ölebiliyordu** | `tazelik_kontrol` diske yazıyor; bir `OperationalError` görevi öldürür, ana döngü devam eder ve guard kalan 30 gün **kör** kalırdı. Dashboard yine "sağlıklı" derdi | ✅ gözetim + dur |
| 4 | Düzgün durdurmanın **kapısı yoktu** | K-043. Sert kill tek seçenekti ve `temiz_kapanmadi` sayılıyordu: planlı her yeniden başlatma kriteri kırardı | ✅ `sq paper durdur` |
| 5 | Backoff yalnızca **bar** geldiğinde sıfırlanıyordu | 1h'te bar saatte bir kapanır; trafik gören sağlıklı bir oturum da "başarısız deneme" sayılır ve bekleme kısa kesintilerde bile 60 s'ye tırmanırdı | ✅ ölçüt mesaj |
| 6 | Kapanışta oturum/bağlantı **kapatılmıyordu** | aiohttp oturumu ve iki SQLite bağlantısı açık kalıyordu; WAL checkpoint'i yorumlayıcının çıkış sırasına bağlıydı | ✅ `Kurulum.kapat` |

Ayrıca iki küçük düzeltme: tanınmayan bir `/api/...` yolu SPA geri düşüşüne takılıp
`index.html`i **200** ile döndürüyordu (artık 404 — kaldırılmış bir uç çalışıyor gibi
görünmemeli), ve `session-start` hook'u Roadmap'teki spike tablosunu da faz sanıp 9 fazı
**13** diye sayıyordu.

**Testler 1023 → 1061.**

### Koşu neden sıfırdan başlatıldı: `gozlem-1` → `gozlem-2`

`gozlem-1` (2026-09-11 06:26 UTC, 5,5 saat, 6 bar, 0 fill) **emekliye ayrıldı** ve 30
günlük saat `gozlem-2` ile sıfırdan başladı. Gerekçe iki katlı:

**1. Eski süreç kendi kapısını tanımıyordu.** Düzeltmeler diskteydi ama çalışan süreç
K-043 öncesi koddu; durdurma bayrağını yoklamıyordu. Yani onu durdurmanın tek yolu sert
kill'di, ve sistem — kendi kuralı gereği, doğru biçimde — bunu `temiz_kapanmadi` diye
kaydederdi. `gozlem-1`'e devam etmek, 30 günlük koşuya **sebebi "bilinmiyor" olan bir
kesintiyle** başlamak demekti. Kriter *"kesinti olduysa sebebi kayıtlı"* diyor; sebebi
yalnızca bu rapora elle yazarak "kayıtlı" saymak, kaydın söylemediği bir şeyi söylemiş
gibi göstermek olurdu.

**2. O 5,5 saat artık var olmayan kodu ölçüyordu.** Ölçülen şey altyapının ayakta kalması
ve altyapı tam da o noktada değişti: yeniden bağlanma kaydı, backoff ölçütü, guard'ın
gözetimi ve kapanış yolu. Saati devretmek, 30 günlük bir iddianın ilk saatlerini artık
çalışmayan bir sürümle doldurmak olurdu. Kaybedilen ölçüm değeri sıfır: 0 fill, 6 bar.

Bu, K-009'un *"bir commit atmak 30 günlük ölçümü sıfırlamamalı"* kuralıyla çelişmiyor.
O kural koşunun **ortasındaki** bir kod değişikliğini kesinti saymamak için var ve
`KOD_DEGISTI` ile kaydediyor; buradaki durum bir yan değişiklik değil, ölçülen mekanizmanın
kendisinin düzeltilmesi — ve zaten temiz devretme imkânı da yoktu.

Bundan sonrası için kapı açık: `sq paper durdur gozlem-2 --sebep "..."` planlı bir duruşu
`durdu` satırıyla kapatıyor, kesinti sayacına dokunmuyor (K-043).

## Sırada ne var

1. **Gözlem koşusunu başlat** ve 30 gün çalıştır. Kesinti olursa sebebi koşu günlüğünde
   olacak (`sq paper olaylar`) ve giderilecek.
2. **Paralelde Faz 4'e dön:** promotion kapılarını geçen bir strateji ara. Geçen ilk
   strateji ile gerçek bir `paper` koşusu başlar ve K-018/3'ün drift eşiği ancak orada
   kalibre edilir.
3. Faz 7'nin ön koşulu: `testnet.binance.vision` API anahtarı.
