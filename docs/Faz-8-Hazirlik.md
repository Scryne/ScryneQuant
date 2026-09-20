---
proje: ScryneQuant
faz: 8
tarih: 2026-09-20
type: hazırlık
durum: taslak — Faz 8 tetiklenmedi (0/52), kod yazılmadı, karar açılmadı
---
# Faz 8 — Kontrollü live: hazırlık dokümanı

**Bu doküman ne değildir.** Faz 8'i açmaz, canlıya giden yolu kısaltmaz, hiçbir kapıyı
gevşetmez. Faz 8 sıraya değil **tetiklenmeye** bağlıdır (Roadmap): promotion zincirini geçen
ilk strateji çıktığında başlar, ve bugün o strateji **yok** — 52 çekilişin 52'si kaldı,
`oos_sharpe` eşiği 1,04 (K-064/K-071). Tetik gelmeden kod yazılmaz; bu doküman tetik geldiği
gün "ne yapılacağı" sorusunun o gün, aceleyle, gerçek para masadayken cevaplanmasını önlemek
için **şimdi** yazıldı.

**Ne yapar.** Roadmap'in Faz 8 bölümünde ad verilip tanımlanmayan üç şeyi tanımlar: (1) shadow
adımı, (2) kademeli sermaye tablosunun **biçimi**, (3) venue hukuki statü kaydının **biçimi**.
Bir de ön koşulların bugünkü ölçülmüş durumunu tek tabloda toplar. Sayı gerektiren yerlerde
sayı vermez; hangi sayının nereden ölçüleceğini yazar (K-033 kalıbı: `olculdu` / `istah` +
gözden geçirme koşulu).

Bağlayıcı kaynaklar: Roadmap §Faz 8, K-010, K-014, K-018, K-038, K-041, K-046, K-050/3,
K-055, K-062/5, K-063, K-065, K-069, Denetim-v2 B8 ve D2.

---

## 0. Tetik ve ön koşullar — bugünkü durum (2026-09-20)

| # | Ön koşul | Kaynak | Durum | Kanıt / eksik |
| --- | --- | --- | --- | --- |
| T | Promotion zincirini geçmiş ≥1 strateji | Roadmap, K-010 | ❌ **yok** | 0/52; araştırma uzayı mevcut eylem uzayında kapalı (K-078). Tetik gelmeden aşağıdakilerin hiçbiri koda dönmez |
| 1 | Süreç dışı kill switch | K-065 | ✅ testnet'te | `sq kill calistir`, 2,97 s, dondurulmuş sürece karşı. **Canlı host'ta tekrarlanmadı** — ilk canlı tatbikat §5'te |
| 2 | Shadow adımı | Denetim-v2 B8 | ⏳ tanım bu doküman §1 | Kod yok; `MODLAR`da `shadow` yok |
| 3 | Kademeli sermaye tablosu | K-050/3 | ⏳ biçim bu doküman §2 | Sayılar Faz 8'in ilk koşusunda kalibre edilir (K-050/3 aynen) |
| 4 | Venue hukuki statüsü | Denetim-v2 D2 | ⏳ biçim bu doküman §3 | **Doldurulmadı.** Kaynaklı kayıt Scryne'dan; bu oturumda tahmin edilmedi |
| 5 | Sürekli açık host + açık pozisyonla toparlanma | K-055, K-063, K-069 | 🔄 | host-1 2026-09-17'den beri; açık pozisyonla toparlanma 25 Eylül senkron restart'ında ölçülebilir |
| 6 | Canlı hesap + KYC + **spot işlem yetkili** anahtar | Roadmap (Faz 0'dan) | 🔶 kısmen | Hesap var, salt okunur anahtar var ve **çalışıyor** (Spike 8 §1b: `apiRestrictions` HTTP 200, `enableReading=true`, `enableSpotAndMarginTrading=false`, `createTime` 2026-09-17). İşlem yetkili anahtar **bilerek yok** (K-062/5) ve Faz 8'in elle onayından önce üretilmez |
| 7 | Risk sermayesi bütçesi | Final-Doküman §Bütçeler | ❌ açık | Yalnızca Scryne'dan gelebilir; ilk kademenin büyüklüğü buna bağlı |

Spike 1'in "kimlik doğrulama gerçek anahtarla tekrar" şartı **okuma tarafı için** Spike 8'de
fiilen karşılandı (imzalı istek, canlı spot host, HTTP 200). İşlem tarafı için tekrar ancak
işlem anahtarı üretildiğinde, yani elle onaydan sonra yapılabilir — ve o tekrarın kendisi
shadow'un son adımı değil, canlının ilk adımıdır (§1.6).

---

## 1. Shadow adımı

### 1.1 Tanım

**Canlı modun tamamı, emir gönderimi hariç.** Gerçek hesabın bakiyesi okunur, gerçek sembol
kuralları çekilir, sinyal risk motorundan geçer, emir kurulur, deftere yazılır — ve ağa
**çıkmaz**. Paper'ın ölçemediği üç şeyi ölçer: gerçek bakiye, gerçek sembol kuralları,
karar→emir gecikmesi. Sıradaki hiçbir şey yeni değil; yalnızca `execution/motor.py`nin altı
adımlı sırasının 5. adımının yerine "gönderilmedi" kaydı geçiyor.

Shadow, `gozlem` ve `paper`dan **farklı bir soru** sorar:

| Mod | Veri | Fill | Hesap | Emir | Kanıt üretir mi |
| --- | --- | --- | --- | --- | --- |
| `gozlem` | canlı | simüle | sanal | yok | hayır (K-035) |
| `paper` | canlı | simüle | sanal | yok | evet, `paper` aşaması için |
| **`shadow`** | canlı | **yok** | **gerçek, salt okunur** | kurulur, **gönderilmez** | evet, elle onayın **girdisi** (§1.5) |
| `live` | canlı | gerçek | gerçek | gönderilir | drift ölçümü (§2) |

### 1.2 "Gönderilmez" garantisi yapısaldır, kodsal değil

Shadow'un emir gönderemeyeceği **koddan önce anahtarla** garanti edilir: shadow koşusu
yalnızca `enableSpotAndMarginTrading=false` bir anahtarla açılabilir. Bugünkü salt okunur
anahtar tam olarak budur. Başlangıçta `GET /sapi/v1/account/apiRestrictions` çekilir
(`tools/faz14_anahtar_denetimi.py` aynı ucu zaten kullanıyor) ve mod ile yetki uyuşmazsa süreç
**başlamaz**:

| Mod | `enableSpotAndMarginTrading` | `enableWithdrawals` | `ipRestrict` | Başka bir alan |
| --- | --- | --- | --- | --- |
| `shadow` | **false** (zorunlu) | false | — | hepsi false |
| `live` | **true** | **false** (zorunlu) | **true** (zorunlu) | `enableFutures/Margin/…` false |

Yanlış anahtarla yanlış mod bir uyarı değil, açılış hatasıdır. Bu, K-065'in "işaret ilk"
mantığının anahtar düzeyine taşınmış hâli: kod bir yazım hatasıyla emir yolunu açsa bile
borsa `-2015` ile reddeder. Kodsal katman (aşağıda) ikinci katmandır, birinci değil.

### 1.3 Kodsal tasarım (tetik gelince yazılacak, şimdi değil)

1. **`risk/motor.MODLAR`a `shadow` eklenir**, `paper` ile `live` arasına. `MOD_ESIGI["shadow"]
   = Asama.LIVE_ADAYI`: makine kontrollerinin tamamı geçilmiş, sırada insan var. Shadow o
   insanın bakacağı şeyi üretir. Daha düşük bir eşik (örn. `PAPER`) anlamsız — `PAPER`
   geçildiği anda `LIVE_ADAYI` otomatik; daha yüksek olamaz — `ELLE_ONAY` shadow'dan sonra.
2. **Canlı host ayrı bir modülde** (`exchange/canli.py`), `imzali.py`de değil. `imzali.py`nin
   "canlı host bilerek tanımlı değil" notu **kalır**; `canli.py`yi yalnızca shadow ve live
   giriş noktaları import eder ve bu `test_izolasyon.py` kalıbıyla AST testine bağlanır:
   `backtest/`, `research/`, `live/motor.py` (paper) `exchange.canli`yi import edemez.
3. **`GolgeAdaptoru(EmirAdaptoru)`**: okuma metodları (`bakiye`, `sembol_kurallari`,
   `son_fiyat`, `acik_emirler`, `emir_sorgula`) gerçek imzalı adaptöre delege eder; yazma
   metodları (`market_emri`, `limit_emri`, `emir_iptal`) **ağa çıkmaz**, `GolgeGonderim`
   istisnası fırlatır. `EmirMotoru.gonder` bu istisnayı yeni bir durumla kapatır:
   `EmirDurumu.GOLGE` ("kuruldu, doğrulandı, gönderilmedi"). Deftere yazılan miktar yine
   kurallara uydurulmuş miktardır (motor §2. adım) — shadow'un ölçtüğü "gerçek sembol kuralı
   reddi" tam olarak bu adımda çıkar.
4. **Zaman damgaları:** her `GOLGE` kaydı üç anı taşır — bar kapanışı (`t_bar`), sinyalin risk
   motorundan çıkışı (`t_karar`), emrin gönderilebilir hâle geldiği an (`t_emir`). Hepsi
   `SaatSenkronu`nun borsa saatinden (K-041). `t_emir − t_bar` ölçülen gecikmedir; K-004'ün
   "fill sonraki barın açılışında" varsayımının canlıda ne kadar tuttuğunu bu sayı söyler.
5. **Pozisyon mutabakatı shadow'da da çalışır** (K-046): çıpa shadow başında atılır, akış
   **boştur** (fill yok), gerçek = borsa. Fark sıfırdan başka çıkarsa **dışarıdan** bir
   hareket var demektir (yatırma, elle işlem, dust dönüşümü, başka bir sürecin emri). Shadow,
   bu gürültüyü sistemin kendi işlemi olmadan ölçen tek yer; canlıda aynı gürültü işlem
   etkisiyle karışır.
6. **Kill switch canlı host'a karşı tatbikatı** shadow sırasında yapılır: açık emir yok,
   `sq kill calistir --canli` süreci öldürür, işaret diske iner, iptal adımı "iptal edilecek
   emir yok" ile döner. Bu, K-065'in canlı host'ta ilk çalışması ve canlıya geçmeden **önce**
   olmak zorunda (Roadmap: "Faz 14'ün ilk kalemi, Faz 8 ondan önce tetiklenirse yine önce").

### 1.4 Shadow'un ölçtükleri

| Ölçüm | Nasıl | Beklenen | Sapma ne demek |
| --- | --- | --- | --- |
| Gerçek bakiye okuma | her barda `bakiye()`, `free` + `locked` | başarı %100 | ağ/anahtar sorunu canlıda emir kaybı olur |
| Sembol kuralı reddi | `EmirMotoru` 2. adım `REJECTED` sayısı | **0** | strateji sermaye/lot ölçeğinde kurallara uymuyor; paper bunu göremez |
| `minNotional` marjı | shadow emir notional / `min_notional` (BTCUSDT: 5 USDT) | kayıt | ilk kademe sermayesi bunun altındaysa canlı emir hiç çıkmaz (§2) |
| Karar→emir gecikmesi | `t_emir − t_bar`, p50/p95/maks | kayıt, bar süresinin küçük bir kesri | K-004 varsayımı bozuluyor; slippage kalibrasyonu (K-021) eksik kalıyor |
| Bar kapanışı → bar geliş gecikmesi | WebSocket bar zamanı vs geliş | kayıt (`GEC_BAR` olayı zaten var) | aynı |
| Açıklanamayan pozisyon farkı | K-046 mutabakatı, akış boş | **0** | hesapta sistemin dışında hareket var; canlıda "açıklanamayan fark: sıfır" kriteri kirlenir |
| Saat sapması | `SaatSenkronu`, `SaatSapmasi` sayısı | 0 sıçrama | K-041 |
| Kesinti | koşu günlüğü | sebebi kayıtlı ve giderilmiş | K-069 kalıbı |

Shadow **PnL üretmez** ve bu bilinçli: fill yok. "Shadow'da kazandı" diye bir cümle yoktur.

### 1.5 Shadow ne zaman biter — elle onayın girdisi

K-050/2: izni artıran her adım **sayısal kapı → elle onay**. Shadow raporu elle onayın
girdisidir; `sq promotion onayla` notu shadow rapor dosyasına atıf yapmadan kabul edilmez
(`elle_onayla` bugün ≥10 karakter not istiyor; shadow rapor yolu zorunlu alan olur). Kapının
makine tarafı:

| Kapı | Eşik | Kaynak |
| --- | --- | --- |
| Süre | ≥ **14 gün** kesintisiz | `istah` — bir haftalık yeniden dengeleme turunu iki kez görmek (K-069'un "bir tam tur" ölçütünün iki katı). Gözden geçirme: ilk shadow koşusunda strateji başına gerçek emir sıklığı ölçülünce |
| Emir niyeti | ≥ **20** `GOLGE` kaydı | `istah` — gecikme dağılımının p95'i için asgari örneklem. Gözden geçirme: aynı |
| Sembol kuralı reddi | **0** | K-018 (makine eşiği) |
| Açıklanamayan pozisyon farkı | **0** | K-046 |
| Saat sıçraması | **0** | K-041 |
| Açıklanamayan kesinti | **0** | K-069 |
| Canlı host kill tatbikatı | 1, başarılı (`<koşu>.kill.json` çıkış 0) | K-065 |

İki `istah` sayısı **öneridir**, K-033 kalıbıyla `config/`e yazılana kadar bağlayıcı değil.
Shadow'un promotion zincirine **aşama** olarak mı (K-010'un dokuz halkasına onuncu), yoksa
`LIVE_ADAYI` ile `ELLE_ONAY` arasında **elle onayın zorunlu girdisi** olarak mı gireceği bir
karardır ve §6'da Scryne'a bırakıldı. Öneri ikincisi: zincir değişmez, onay notunun biçimi
değişir.

### 1.6 Shadow → live geçişi

**Ön koşul (K-082, 2026-09-20):** stratejinin promotion kaydı zincirli ve global audit'e
bağlı olmalı; `sq promotion onayla --audit` ve `live` açılışı bütünlük doğrulanmadan
**çalışmaz** (fail closed). K-082 öncesi bir kayıt önce `sq promotion zincirle` ile göç edilir.

Elle onay verildikten sonra, **aynı gün değil**, sırayla:

1. İşlem yetkili **yeni** anahtar üretilir: spot işlem açık, çekim/transfer/margin/futures
   kapalı, **IP kısıtlı** (host-1'in IP'si). Salt okunur anahtar **silinmez**; okuma
   (dashboard, pano, izleme) onunla devam eder — anahtar ayrımı (Faz 14 kriteri) canlıda da
   korunur.
2. Spike 1'in kimlik doğrulaması bu anahtarla tekrarlanır: `apiRestrictions` beklenen tabloyu
   (§1.2 `live` satırı) vermezse anahtar **kullanılmaz**.
3. Kademe 1 (§2) ile açılır. Kademe 0 = shadow'dur; tabloda görünür, sermayesi sıfırdır.

---

## 2. Kademeli sermaye tablosu — biçim

K-050/3 biçimi sabitledi, sayıları Faz 8'in ilk koşusuna bıraktı. Burada biçim **makine
tarafından okunabilir** hâle getiriliyor. Kaynak dosya `config/kademe.json`, `config/risk.json`
ile aynı sözleşmeyle (K-033: her sayı `kaynak` + `gozden_gecirme` taşır) ve `sq risk limitler`
kalıbıyla okunur.

### 2.1 Şema

```json
{
  "surum": 1,
  "risk_sermayesi_usdt": null,
  "drift_tanimi": "§2.3",
  "kademeler": [
    {
      "kademe": 0,
      "ad": "shadow",
      "sermaye_usdt": 0.0,
      "asgari_gun": 14,
      "asgari_emir": 20,
      "drift_ust_siniri_bps": null,
      "pozisyon_farki": 0,
      "onay": {"gerekli": true, "not": null, "tarih": null}
    },
    {
      "kademe": 1,
      "ad": "micro-live",
      "sermaye_usdt": null,
      "asgari_gun": null,
      "asgari_emir": null,
      "drift_ust_siniri_bps": null,
      "pozisyon_farki": 0,
      "onay": {"gerekli": true, "not": null, "tarih": null}
    }
  ],
  "gerekceler": { "<alan>": {"kaynak": "olculdu|istah", "metin": "", "gozden_gecirme": "", "olcum_tarihi": ""} }
}
```

Kurallar:

- **Kademe atlanamaz.** `n`'den `n+1`'e geçiş, `n`'in dört şartının tamamı (gün, drift,
  pozisyon farkı, onay) sağlanmadan yazılamaz; yazılsa bile risk motoru `n+1`'in sermayesini
  kabul etmez. Onay `null` olan kademe **yoktur**.
- **Sermaye artışı yalnızca bir kademe.** `n` → `n+2` yazımı şema hatasıdır.
- **Otomatik iniş** (K-050/1): drift üst sınırı aşılırsa, kill switch tetiklenirse ya da
  açıklanamayan kesinti olursa sermaye **kendiliğinden** `n−1`'e iner ve bu audit'e yazılır.
  Pozisyon farkı ≠ 0 **iniş değil, halt**tır (K-046: koşu durur, tahmin yürütülmez).
- **Yeniden çıkış** inişten sonra sayaç sıfırdan: `asgari_gun` yeniden dolmalı, onay yeniden
  alınmalı. "Zaten onaylanmıştı" geçerli değil.
- **Kademe 1'in sermayesi alt sınırdan bağımsız değil:** `sermaye_usdt × islem_basina_risk`
  (0,005) × tipik pozisyon büyüklüğü `min_notional`'ın (5 USDT) altına düşerse strateji tek
  emir bile çıkaramaz. Shadow'un `minNotional` marjı ölçümü (§1.4) tam olarak bunun için:
  Kademe 1'in sermayesi, shadow'da gözlenen emir notional dağılımının **p5'i** `min_notional`ın
  üstünde kalacak kadar olmalı. Sayı buradan **ölçülür**, iştahla konmaz.

### 2.2 Ölçüm noktası ve kaynağı

| Alan | Nereden ölçülür | Kaynak türü |
| --- | --- | --- |
| `risk_sermayesi_usdt` | Scryne | karar (Final-Doküman §Bütçeler, **açık**) |
| Kademe 1 `sermaye_usdt` | shadow emir notional p5 / `min_notional` marjı | `olculdu` (shadow) |
| Kademe n>1 `sermaye_usdt` | bir önceki kademenin drift raporu; artış oranı sabit (öneri ×2, `istah`) | `istah` + `olculdu` |
| `asgari_gun` | strateji başına gerçek emir sıklığı: `asgari_emir` kadar emri görmeye yetecek gün | `olculdu` (shadow) |
| `drift_ust_siniri_bps` | Kademe 1'in ilk 30 gününde ölçülen drift dağılımı; üst sınır p95 | `olculdu` (Faz 8 ilk koşu, K-050/3 aynen) |

### 2.3 Drift tanımı — `|paper − live|` ne demek

Roadmap "drift" diyor, Proje-Fikri §45 ayrıştırma başlıklarını sayıyor (fee, slippage, fill
rate, regime, latency, signal frequency, liquidity). İkisi de sayıyı tanımlamıyor. Öneri:

**Düzenek.** Aynı dondurulmuş strateji, aynı host'ta, aynı bar akışıyla **iki süreçte** koşar:
biri `paper` (simüle fill, K-021 slippage modeli), biri `live`. İkisi aynı barda aynı sinyali
üretmek **zorundadır** (K-009 determinizm; üretmezse drift değil, hata). Fark yalnızca fill'de
doğabilir.

**Birincil sayı — işlem başına net getiri farkı:**

```
d_i = (net_getiri_live_i − net_getiri_paper_i)   [bps, aynı sinyal, aynı miktar]
drift_bps = medyan(|d_i|)          → kademe kapısı bu
drift_isaret = ortalama(d_i)       → sistematik mi (K-021 slippage yanlış) yoksa gürültü mü
```

**İkincil sayı — özkaynak farkı:** `|E_live(t) − E_paper(t)| / E_paper(t)` bps, koşu sonu ve
azami. `live/evren_sapma.py`nin `SapmaRaporu`su bu biçimi zaten kuruyor (canlı vs referans);
aynı rapor `paper` vs `live` için yeniden kullanılır — yeni bir ölçüm aracı yazılmaz.

**Ayrıştırma** (§45'in listesi, her biri `d_i`'nin bir bileşeni):

| Bileşen | Ölçüm | Kaynak |
| --- | --- | --- |
| Komisyon | gerçek `commission` (emir_islemleri) − model `fee_taker_bps` (10 bps) | K-016; testnet komisyon kesmediği için **ilk gerçek ölçüm burada** (Faz 7 §7) |
| Slippage | fill fiyatı − sinyal barının sonraki açılışı (K-004) − model slippage | K-021 |
| Fill oranı | `FILLED` / gönderilen; `PARTIALLY_FILLED` kalanı | Faz 7 |
| Gecikme | `t_fill − t_bar` (shadow'un `t_emir − t_bar`ına ek olarak borsa tarafı) | §1.4 |
| Sinyal sıklığı | live ve paper'da sinyal sayısı — **eşit olmalı**, değilse hata | K-009 |

Rejim ve likidite bu ayrıştırmada **yoktur**: ikisi de paper ve live'da aynı; fark üretemez.
§45'in listesinden çıkarılmaları bilinçli.

**Eşik nasıl yazılır.** `drift_ust_siniri_bps` Kademe 1'de `null` başlar (ölçüm yok); ilk 30
günün `|d_i|` dağılımı `config/kademe.json`'a `dagilim` olarak yazılır (`risk.json`'daki
`gunluk_zarar_limiti` kalıbı) ve üst sınır p95 olarak seçilir. Kademe 2'ye geçiş bu sayı
dolmadan **yazılamaz**. Kademe 1'de kendisi için eşik yoktur; Kademe 1'in kapısı sermayenin
küçüklüğüdür.

---

## 3. Venue hukuki statü kaydı — biçim

Denetim-v2 D2: SPK'nın 2025 düzenlemesi (III-35/B.1, B.2) hizmet sağlayıcıyı düzenler; proje
K-014 içinde kaldıkça hizmet sağlayıcı değildir. Doğrulanacak şey **venue'nun** Türkiye
yerleşiği bir kullanıcıya hizmet statüsü. K-015 teknik erişimi ölçtü (451 yok); hukuki
erişim ölçülmedi.

**Bu bölüm bu oturumda doldurulmadı ve doldurulmayacak.** Hukuki statü, PIT veri gibi
**kaynaklı ve tarihli** bir kayıttır; kaynağı olmayan bir "durum" cümlesi, kaynağı olmayan
bir fiyat barı kadar değersizdir. Aşağıdaki biçim, Scryne'ın dolduracağı şablondur.

### 3.1 Kayıt biçimi (`docs/Venue-Statu.md`, tetik gelince açılır)

| Alan | İçerik |
| --- | --- |
| `venue` | Binance (spot) — Faz 7/8'in tek venue'su |
| `kullanici_yerlesikligi` | Türkiye |
| `duzenleme` | SPK III-35/B.1 ve B.2 (2025), resmî gazete tarih/sayı, madde numaraları |
| `venue_statusu` | SPK listesinde (varsa) / başvuru durumu / TR kullanıcıya hizmet politikası — **venue'nun kendi beyanından**, üçüncü el haberden değil |
| `kaynaklar` | her iddia için URL + erişim tarihi + sayfanın SHA-256'sı (arşiv kopyası `data/hukuki/`, `.gitignore`'da) |
| `kayit_tarihi` | UTC; bu tarih **PIT sınırıdır** — sonraki bir değişiklik geriye uygulanmaz, yeni satır olur |
| `gozden_gecirme` | ≥ 90 günde bir, ya da venue politikası değişince (hangisi önce) |
| `sonuc` | `AÇIK` / `KISITLI` / `KAPALI` / `BELİRSİZ` — `BELİRSİZ` de bir sonuçtur ve **canlıyı açmaz** |

### 3.2 Doldururken cevaplanacak sorular

1. Venue, Türkiye yerleşiği bireysel kullanıcıya spot hizmet verdiğini **kendi** kanalından
   beyan ediyor mu (ToS, bölgesel kısıt listesi, destek sayfası)? Tarih ve URL.
2. SPK'nın 2025 düzenlemesi kapsamında venue lisans/başvuru listesinde mi? SPK'nın kendi
   sayfasından, tarih ve URL.
3. Hesap sözleşmesi hangi tüzel kişilikle (Binance'in hangi kuruluşu)? Hesap ekranından.
4. Vergi: kripto kazancının beyanı bu projenin kapsamı **dışında** ama kaydın "bilinmiyor"
   satırı olarak durması gerekir — "kapsam dışı" ile "düşünülmedi" aynı şey değil.
5. K-014 sınırı: proje tek hesap, tek kişi, sinyal paylaşımı yok. Bu kayıt, o sınırın
   **dışına** çıkıldığında geçersizleşir; kayıt bunu açıkça söyler.

`sonuc` `AÇIK` değilse Faz 8 **tetiklense bile** açılmaz. Bu bir kapı değil bir ön koşuldur:
K-018 makine eşiği burada geçerli değil, çünkü ölçülen şey sayı değil metin; ama "kaynak yok →
`BELİRSİZ` → açılmaz" kuralı makine gibi işler.

---

## 4. Faz 8 bitti kriterleri — nasıl ölçülür

| Kriter (Roadmap) | Makine kontrolü | Bugün var mı |
| --- | --- | --- |
| Promotion zincirini geçmiş ≥1 strateji live'da | `PromotionKaydi.asama == LIVE` + `MOD_ESIGI["live"]` | ✅ `risk/promotion.py` |
| ≥30 gün + backtest/paper/live farkı ölçülüp raporlanmış | §2.3 drift raporu, `SapmaRaporu` biçimi | 🔶 `evren_sapma.py` canlı-vs-referans için var; paper-vs-live sarmalayıcısı yok |
| Kill switch canlıda kasıtlı test | `<koşu>.kill.json` çıkış 0, canlı host | 🔶 K-065 testnet'te; canlı host'ta shadow sırasında (§1.3/6) |
| Uzlaşmazlık / duplicate / açıklanamayan fark: **sıfır** | `oms/mutabakat.py` halt sayısı, `oms/defter.py` duplicate tablosu, `oms/pozisyon.py` `aciklanamaz` | ✅ üçü de var, testnet'te ölçüldü (Faz 7 §9) |

---

## 5. Tetik geldiğinde iş sırası

Tetik = bir strateji `LIVE_ADAYI`ya ulaştı. O gün yapılacaklar, **sırayla**, hiçbiri
atlanmadan:

1. Bu doküman yeniden okunur; §6'daki açık kararlar Kararlar.md'ye K olarak yazılır.
2. §3 venue kaydı doldurulur. `AÇIK` değilse **dur**.
3. Risk sermayesi sayısı Scryne'dan alınır, `config/kademe.json` açılır (§2.1), Kademe 0.
4. Kod: `shadow` modu, `exchange/canli.py`, `GolgeAdaptoru`, `EmirDurumu.GOLGE`, anahtar
   yetki kontrolü (§1.2), izolasyon testi (§1.3/2). Mevcut testler bit düzeyinde aynı kalır
   (K-057 kalıbı: paper motoru shadow'un özel hâli değildir; shadow ayrı bir adaptördür,
   motor değişmez).
5. Shadow koşusu, salt okunur anahtarla, ≥14 gün (§1.5). Kill tatbikatı canlı host'a karşı.
6. Shadow raporu → elle onay (`sq promotion onayla --shadow-rapor <yol> --not …`).
7. İşlem anahtarı üretilir (§1.6), Spike 1 tekrarı, Kademe 1.
8. Kademe 1'de ≥30 gün; drift dağılımı yazılır; Faz 8 raporu (`docs/Faz-8-Live-Raporu.md`).

Adım 4'ün kestirimi: ~2 iş günü kod + test, çünkü altyapının tamamı var — yeni olan bir
adaptör, bir durum, bir mod ve bir açılış kontrolü. Bu kestirim tetik gelmeden **harcanmaz**.

---

## 6. Scryne'ın vereceği kararlar (tetik gelince K olarak yazılır)

| # | Karar | Öneri | Neden şimdi verilmiyor |
| --- | --- | --- | --- |
| 1 | Shadow, K-010 zincirine **aşama** mı, elle onayın **zorunlu girdisi** mi | Girdi (zincir değişmez, onay notu biçimi değişir) | Zincir K-010'un kendisi; tetik yokken değiştirmek ölçüsüz |
| 2 | Shadow asgari süre / asgari emir | 14 gün / 20 emir (`istah`) | İlk shadow koşusu emir sıklığını ölçmeden sayı iştah kalır |
| 3 | Risk sermayesi (USDT) | — | Final-Doküman: yalnızca Scryne |
| 4 | Kademe artış oranı | ×2 (`istah`) | Aynı |
| 5 | Drift üst sınırı seçim kuralı | Kademe 1'in ilk 30 gün `|d_i|` p95'i | K-050/3: ilk koşuda kalibre |
| 6 | Venue kaydı `sonuc` | — | Kaynaklı doğrulama Scryne'dan |
| 7 | Canlı host modülü + AST izolasyon sınırı | `exchange/canli.py`, yalnız shadow/live giriş noktaları | K-052/1 (import sınırında kanıt) |

---

## 7. Bu doküman neyi değiştirmedi

`src/`, `config/`, `tests/`, `MODLAR`, `MOD_ESIGI`, `ASGARI_PAPER_GUN`, `imzali.py`nin canlı
host notu, promotion zinciri, kapı eşikleri — hiçbiri. Kararlar.md'ye K açılmadı: karar
verilmedi, biçim yazıldı. Roadmap Faz 8 bölümüne bu dokümana işaret eden tek satır eklendi.
