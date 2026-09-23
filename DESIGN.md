---
version: alpha
name: ScryneQuant
description: Kripto spot stratejilerini araştıran, backtest eden ve risk kapılarından geçirerek uygulayan tek kişilik quant platformu.
colors:
  # --- nötr yüzeyler: veri buraya yazılır, opak ------------------------------
  background: "#0A0C14"
  surface: "#12141E"
  surface-raised: "#171A26"
  surface-sunken: "#0D0F18"
  border: "#252A3A"
  border-strong: "#39405480"
  # --- metin: üç kademe, üçü de ≥4.5:1 -------------------------------------
  primary: "#E8EAF0"
  secondary: "#9AA1B4"
  tertiary: "#7C8397"
  # --- risk: TEK yüksek doygunluklu renk, başka hiçbir yerde kullanılmaz ----
  risk: "#FF5A1F"
  risk-surface: "#2A150C"
  risk-border: "#7A3312"
  on-risk: "#0A0C14"
  # --- yön: kâr/zarar. Düşük doygunluk, işaret her zaman yanında -----------
  direction-up: "#7FB5A2"
  direction-down: "#C08B7D"
  direction-flat: "#7C8397"
  # --- etkileşim: nötr-soğuk, veri renkleriyle karışmaz --------------------
  interactive: "#8AA6E4"
  interactive-strong: "#6E8FD6"
  interactive-surface: "#171C2E"
  # --- mod göstergesi: live ve paper bir saniyede ayrılmalı ----------------
  mode-gozlem: "#7C8397"
  mode-paper: "#8AA6E4"
  mode-live: "#FF5A1F"
  # --- grafik: nötr, düşük doygunluk. Renk tek başına anlam taşımaz --------
  chart-line: "#9AA1B4"
  chart-benchmark: "#5C6478"
  chart-grid: "#1C2030"
  chart-area: "#9AA1B41F"
  # --- cam: yalnızca üst katman yüzeyleri (bkz. "Elevation & Depth") -------
  overlay-surface: "#12141ECC"
  overlay-border: "#FFFFFF1A"
  # --- bot takip ekranı (K-132, `apps/web/bot.html`): koyu yeşil zemin, nane marka -----
  bot-bg: "#070A09"
  bot-surface: "#0E1312"
  bot-surface-2: "#131A18"
  bot-surface-3: "#1A2320"
  bot-line: "#1F2A27"
  bot-line-strong: "#2C3935"
  bot-text: "#E7F0EC"
  bot-text-2: "#9FAEA8"
  bot-text-3: "#7C8C86"
  bot-mint: "#2FE3A0"
  bot-mint-ink: "#03140D"
  bot-mint-soft: "#2FE3A01F"
  bot-mint-deep: "#1BB77E"
  bot-down: "#F2766D"
  bot-risk: "#FFB23E"
  bot-risk-ink: "#1A1204"
  bot-risk-surface: "#2B1F0A"
  bot-sky: "#7FB2FF"
typography:
  # Fira Sans etiket ve başlık; Fira Code sayı, zaman ve kod. İki aile, daha fazlası değil.
  # Sayısal her token `tnum` + `zero` taşıyor: sütunda ondalık hizası tutar ve sayı
  # değiştiğinde satır genişliği oynamaz.
  display:
    fontFamily: Fira Sans
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: -0.01em
  h1:
    fontFamily: Fira Sans
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.3
  h2:
    fontFamily: Fira Sans
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: Fira Sans
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: Fira Sans
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0.02em
  metric:
    fontFamily: Fira Code
    fontSize: 28px
    fontWeight: 500
    lineHeight: 1.15
    letterSpacing: -0.02em
    fontFeature: "'tnum' 1, 'zero' 1"
  numeric:
    fontFamily: Fira Code
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "'tnum' 1, 'zero' 1"
  numeric-sm:
    fontFamily: Fira Code
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.35
    fontFeature: "'tnum' 1, 'zero' 1"
  bot-display:
    fontFamily: Manrope
    fontSize: 40px
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: -0.03em
    fontFeature: "'tnum' 1"
  bot-title:
    fontFamily: Manrope
    fontSize: 15px
    fontWeight: 650
    lineHeight: 1.3
  bot-body:
    fontFamily: Manrope
    fontSize: 14px
    fontWeight: 450
    lineHeight: 1.5
  bot-numeric:
    fontFamily: Fira Code
    fontSize: 13px
    fontWeight: 450
    lineHeight: 1.45
    fontFeature: "'tnum' 1, 'zero' 1"
spacing:
  # Yoğun ölçek (8-32px). Bu bir dashboard; boşluk bilgiyi değil, sayfayı büyütür.
  "0": 0px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  "2xl": 32px
rounded:
  sm: 2px
  md: 4px
  lg: 6px
  xl: 10px
  full: 9999px
components:
  # Alt token sözlüğü spec tarafından sabit: backgroundColor, textColor, typography,
  # rounded, padding, size, height, width. Kenarlık rengi ve blur bu sözlükte yok —
  # onlar `colors` token'ları ve aşağıdaki "Elevation & Depth" bölümünde tarif ediliyor.
  metric-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.metric}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
  data-table-cell:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.numeric}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm}"
  risk-banner:
    backgroundColor: "{colors.risk-surface}"
    textColor: "{colors.risk}"
    typography: "{typography.h2}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  overlay:
    # Camın **tek** yaşadığı yer: modal, kill switch onayı, komut paleti, bildirim.
    backgroundColor: "{colors.overlay-surface}"
    textColor: "{colors.primary}"
    typography: "{typography.body}"
    rounded: "{rounded.xl}"
    padding: "{spacing.xl}"
---

# ScryneQuant

> **Token durumu:** Frontmatter **dolu ve normatif** (Faz 6, 2026-09-11). Kesin değerler
> yalnızca orada yaşar; aşağıdaki Markdown gövdesi gerekçedir, ikinci bir kaynak değil.
> Bir token iki yerde yazılıysa biri yanlıştır.
>
> Palet `ui-ux-pro-max` ile aranan "Dark Mode (OLED)" profilinden **kısmen** alındı:
> tipografi eşleşmesi (Fira Sans + Fira Code, "Dashboard Data") ve yoğun boşluk ölçeği
> olduğu gibi; ama önerilen `#22C55E` yeşil "pozitif gösterge" accent'i **reddedildi** —
> aşağıdaki doygunluk kuralıyla doğrudan çelişiyor. Çelişkide bu dosya kazanır.
>
> Doğrulama:
>
> ```bash
> npx --package @google/design.md -c "designmd lint DESIGN.md"
> npx --package @google/design.md -c "designmd export --format css-tailwind DESIGN.md"
> ```

## Overview

Taban disiplin (sabit, tüm projelerde aynı): global `~/.claude/CLAUDE.md` içindeki Dark
Glassmorphism kuralları. Bu dosya yalnızca ScryneQuant'ı diğerlerinden ayıran katmanı
kaydeder — ve bir yerde tabanı **bilerek ezer** (aşağıda "Cam kısıtı").

- **Mood:** Laboratuvar cihazı, kumarhane terminali değil. Sakin, yoğun, okunaklı. Arayüz
  heyecan üretmez; ölçüm gösterir. Kullanıcı ekrana baktığında hissetmesi gereken şey
  merak ve dikkat, ivedilik değil.
- **Farklılaştırıcı detay:** **Doygunluk aciliyeti gösterir, kârı değil.** Yüksek
  doygunluklu renk yalnızca risk durumlarına ayrılmıştır (limit ihlali, kill switch,
  bayat veri, uzlaşmazlık). Kâr/zarar yalnızca düşük doygunluklu bir yön işaretiyle
  gösterilir. Ekranda parlayan bir şey varsa, o şey para değil tehlikedir.

Ana bilgi hiyerarşisi Proje-Fikri §29'dan gelir ve her sayfada aynı zihinsel modeli kurar:

```
Signal → Decision → Risk → Execution → Outcome
```

## Colors

Kesin değerler frontmatter'da; burada **neden** öyle oldukları var.

| Rol | Token | Kullanım | Kısıt |
| --- | --- | --- | --- |
| Risk / uyarı | `risk` `#FF5A1F` | Limit ihlali, SAFE_MODE, kill switch, bayat veri, uzlaşmazlık, toparlanma ayrışması | **Tek** yüksek doygunluklu renk. Arayüzde başka hiçbir yerde kullanılmaz. |
| Yön (kâr/zarar) | `direction-up` `#7FB5A2` · `direction-down` `#C08B7D` | Getiri, PnL, değişim | Düşük doygunluk. Renk tek başına anlam taşımaz; işaret (+/−) her zaman yanındadır. |
| Etkileşim | `interactive` `#8AA6E4` | Buton, link, seçili satır, odak halkası | Nötr-soğuk. Veri renkleriyle karışmaz. |
| Nötr yüzey | `background` · `surface` · `surface-raised` | Tablo, kart, arka plan | **Opak.** Gri skalası veri yoğunluğuna göre kademelenir. |
| Mod | `mode-gozlem` · `mode-paper` · `mode-live` | Hangi modda çalışıldığı | `mode-live` risk rengiyle aynı — çünkü canlı mod bir risk durumudur. |

**Neden kâr için canlı yeşil/kırmızı yok:** Standart trading arayüzü her sayıyı yeşil-kırmızı
boyar. Sonuç: ekran sürekli parlar, göz renge alışır ve **gerçekten önemli olan tek şey —
risk uyarısı — aynı görsel dili konuştuğu için kaybolur.** Doygunluğu risk için saklamak, bu
projede sinyal/gürültü oranını yükselten en ucuz karardır. Ayrıca yeşil-kırmızı yoğun
arayüzler bu ürünün tam olarak olmak istemediği şeyi çağrıştırır: kumarhane.

**Şiddet hue ile değil, doluluk ile anlatılır.** Risk tek bir renk olduğuna göre "ne kadar
kötü" sorusu renk değiştirerek cevaplanamaz — ve cevaplanmamalı, çünkü üç tonlu bir uyarı
paleti (sarı/turuncu/kırmızı) ilk iki tonu birkaç haftada görünmez yapar. Şiddet üç kademeli
**doluluk** ile gösterilir: kenarlık (`risk-border`) → dolu zemin (`risk-surface`) → tam
kontrast (`risk` zemin + `on-risk` metin). Aynı renk, artan alan.

**Ölçülmüş kontrastlar** (zemin `#0A0C14`, yüzey `#12141E`): `primary` 16,2:1 ·
`secondary` 7,6:1 · `tertiary` 5,2:1 · `risk` 6,3:1 · `direction-up` 8,4:1 ·
`direction-down` 6,7:1 · `interactive` 8,1:1. Hepsi WCAG AA normal metin eşiğinin
(4,5:1) üstünde — yoğunluk lehine küçük punto kullanıldığı için burada pay bırakmak şart.

> **Linter notu:** `designmd lint` `orphaned-tokens` uyarıları veriyor. Sebebi, bu paletin
> çoğu token'ının dört örnek bileşen yerine doğrudan sayfalarda tüketilmesi; linter her
> rengin bir bileşen tarafından referanslanmasını bekliyor. Uyarı doğru bir gözlem ama
> burada bir kusur değil — bileşen listesini token'ları "kullanılmış" göstermek için
> şişirmek, dosyayı linter'a göre yazmak olurdu.

## Typography

Eşleşme: **Fira Sans** (etiket, başlık, açıklama) + **Fira Code** (sayı, zaman damgası,
hash). `ui-ux-pro-max`ın "Dashboard Data" çiftinden geliyor; aynı ailenin iki üyesi
olduğu için birlikte durduklarında çatışmıyorlar.

- **Sayılar birinci sınıf.** Sayısal her token `font-feature-settings: 'tnum' 1, 'zero' 1`
  taşıyor: sabit genişlikli rakam, sütunda ondalık hizası tutuyor ve sayı değiştiğinde
  satırın genişliği oynamıyor. Sıfır çizgili — `0`/`O` karışması bir hash okurken pahalı.
- Fiyat, miktar, oran ve zaman damgası **mono** (`metric`, `numeric`, `numeric-sm`);
  başlık ve açıklama **sans** (`display`, `h1`, `h2`, `body`, `label`). İki aile, daha
  fazlası değil.
- Yoğunluk lehine küçük taban boyut kabul edilebilir (`numeric` 13px, `label` 12px), ama
  **kontrast asla feda edilmez** (WCAG 4,5:1 normal metin). 12px'in altına inilmiyor.
- `metric` tek bir skaler değeri öne çıkarmak için var ve sayfada **azdır**: her şey büyükse
  hiçbir şey büyük değildir.

## Layout & Spacing

Yoğun ölçek (`xs` 4px → `2xl` 32px). Bu bir dashboard; boşluk bilgiyi değil sayfayı
büyütür. `ui-ux-pro-max` yoğunluk kadranı 8/10'da ayarlandı.

- **Tek sütunlu, sabit genişlikli içerik yok.** Tablolar mevcut genişliği kullanır; ekran
  büyüdükçe daha çok satır görünür, satırlar büyümez.
- **Sol kenarda kalıcı gezinme**, dört sayfa (Overview, Strategies, Positions, Logs —
  K-012). Beşinci sayfa eklenmeden önce K-012'ye bakılır; §28'in kalan altı sayfası Faz
  7+'ya bırakıldı.
- **Risk şeridi sayfa gövdesinin en üstünde, her sayfada aynı yerde.** Kaydırmadan
  etkilenmez: bir uyarının görünürlüğü kullanıcının nereye kaydırdığına bağlı olamaz.
- Kırılma noktaları 768px / 1024px / 1440px. 768px altında tablolar yatay kaydırılır,
  sütun gizlenmez — gizlenen sütun, olmayan veri gibi görünür.

## Elevation & Depth

**Cam kısıtı — global varsayılanın bilinçli ezilmesi.** Global taban dark glassmorphism'i
varsayılan estetik yapıyor. **Bu projede cam yalnızca üst katman yüzeylerinde kullanılır:**
modal, kill switch onayı, komut paleti, bildirim (`overlay` bileşeni, `overlay-surface` +
14px blur).

**Veri yüzeyleri (tablo, sayı, grafik, risk paneli) opaktır.** Gerekçe global dosyanın
kendi kuralından çıkıyor: `backdrop-filter` kontrastı düşürür ve altındaki içeriğe göre
**değişken** bir zemin yaratır. Yoğun sayısal veride bu iki şey doğrudan okuma hatasına yol
açar — ve bu üründe okuma hatasının bedeli para. Cam, arkasında bir şey olduğunda güzeldir;
arkasında bir sayı olduğunda tehlikelidir.

Bu, global `~/.claude/CLAUDE.md`'nin "sadece kilit elementlerde kullan" kuralının bu projeye
özel, daha sıkı hâlidir — çelişki değil, daraltma.

**Derinlik gölgeyle değil yüzey tonuyla anlatılır.** Üç kademe: `surface-sunken` (tablo
zebrası, girinti) → `surface` (varsayılan) → `surface-raised` (hover, seçili satır,
yükseltilmiş kart). Gölge yalnızca `overlay` katmanında var. Gerekçe: koyu zeminde gölge
neredeyse görünmez ve onu görünür kılmak için koyulaştırmak, panelin altında olmayan bir
boşluk hissi üretir.

**Arka plan gradient mesh'i yalnızca `background` katmanında.** Derin indigo/menekşe
tonları çok düşük alfa ile, sol-üst açık → sağ-alt koyu. Amacı camın arkasında "bir şey"
olması; veri yüzeylerinin altına girmez.

## Shapes

Küçük yarıçaplar (`sm` 2px → `xl` 10px). Yoğun bir tablo arayüzünde büyük yarıçap iki şey
yapar: satır yüksekliğini büyütür ve hücre sınırını belirsizleştirir. `full` yalnızca durum
noktaları ve mod rozeti için.

**Sınırlar çizgiyle, boşlukla değil.** Etkileşimli alanların sınırları `border` ile net
çizilir — koyu temada yalnızca zemin farkına güvenmek, düşük parlaklıkta ekranlarda
sınırları görünmez yapar.

## Components

- **Tablo ana bileşendir**, kart değil. Bu ürünün doğal veri şekli satırdır: trade listesi,
  emir listesi, deney listesi, log. Kart yalnızca tek bir skaler değeri öne çıkarmak için
  kullanılır (Overview'daki portföy değeri, drawdown gibi) ve sayısı azdır.
- **Risk durumu her sayfada aynı yerde durur.** Sayfa değiştiğinde kullanıcının bakması
  gereken yer değişmez. Bu bileşen boşken de görünür — "sorun yok" da bir bilgidir ve
  yokluğuyla değil varlığıyla söylenir.
- **Kill switch her zaman erişilebilir ve her zaman onay ister.** Erişim tek tık, tetikleme
  iki adım. Onay diyaloğunun butonu "Onayla" değil, yapacağı işi söyler.
- **Yıkıcı ve geri alınamaz eylemler** (live'a promotion, kill switch, deney silme) diğer
  butonlarla aynı görsel ağırlıkta olamaz.
- **Boş durumlar bir sonraki adımı söyler.** "Henüz backtest yok" değil; hangi komutun
  backtest üreteceğini söyler — Faz 1-5'te arayüz CLI'ın önünde değil yanındadır.

## Bot takip ekranı (K-133)

`apps/web/bot.html` (`sq execution pano`, 8790) sabit oranlı yatırım botunu (`sabit_oran`) takip
ekranıdır; `bot-` önekli token'lar yalnız orada kullanılır. Kimlik Scryne'ın referansından geliyor
(koyu zemin + nane yeşili, 2026-09-23) ve yukarıdaki "doygunluk yalnız risk" ilkesini **bu ekranda
bilerek daraltıyor**: nane (`bot-mint`) marka, etkin gezinme ve kâr rengidir; ama **risk hâlâ tek
ve ayrı bir renkte** (`bot-risk` kehribar) ve başka hiçbir şeye verilmez. Zarar mercan
(`bot-down`), riskle karışmaz. Yön her zaman işaretle (+/−) yazılır.

- **İmza öğesi — Denge:** %50 hedefin, ±5 puan bandın ve anlık BTC oranının tek bir yatay
  ölçekte gösterimi; altında botun bir sonraki alış ve satış yapacağı BTC fiyatları. Kullanıcının
  "bot ne zaman bir şey yapacak" sorusunu tek bakışta cevaplar.
- **Sayılar:** büyük bakiye Manrope `tnum`; tablo ve fiyatlar Fira Code. Sayılar anlık değişir,
  sayma animasyonu yok.
- **Adlı genişlik sınıfı yok.** `spacing` token'ları (`xs`…`2xl`) Tailwind v4'te `max-w-sm` gibi adlı sınıfları
  ele geçirir (`max-w-sm` = 8px olur). Genişlik sınırı açık değerle yazılır: `max-w-[24rem]`.
- **Yeşil gradient** yalnız iki yerde: grafik alan dolgusu ve pilot kartı (`bot-mint` → `bot-mint-deep`; referansın "öne çıkan
  kart"ı). Başka yüzeyde gradient yok; kartlar opak (`bot-surface`), cam yok.
- **Salt okuma:** ekranda emir/onay/kill düğmesi yoktur (K-036, K-043). Acil durdurma kartı
  CLI komutunu gösterir ve kopyalar.
- Ölçülmüş kontrastlar (zemin `bot-surface`): `bot-text` 16,1:1 · `bot-text-2` 8,1:1 ·
  `bot-text-3` 5,3:1 · `bot-mint` 11,3:1 · `bot-down` 6,8:1 · `bot-risk` 10,4:1 · `bot-sky` 8,7:1;
  en kötü durum `bot-text-3` / `bot-surface-3` 4,56:1.

## Do's and Don'ts

**Do**
- Sayıyı öne çıkar; etiketi ikinci plana at.
- Her risk durumunu metinle de yaz — renk tek taşıyıcı olamaz.
- Zaman gösterilen her yerde saat dilimini etiketle (depolama UTC, gösterim yerel — K-005).
- Bir değer bayat olabiliyorsa (fiyat, pozisyon), yaşını göster.

**Don't**
- **Veri değişimini animasyonla gösterme.** Kayan/sayan rakam okunamaz ve bir an için
  yanlış sayı gösterir. Değerler anında değişir; yalnızca durum geçişleri (SAFE_MODE'a
  giriş gibi) animasyon alabilir.
- **Kâr/zarar için yüksek doygunluklu renk kullanma.** O doygunluk riske ayrılmıştır.
- **Sayıyı cam üzerine koyma.** (Cam kısıtı)
- **Backtest sonucunu kutlayıcı bir dille sunma.** Yeşil onay işareti, konfeti, "harika
  sonuç" tonu yok. Sonuç bir ölçümdür; yorumu kullanıcıya aittir (§4.3 No Fake Alpha).
- **Live ve paper'ı görsel olarak birbirine benzetme.** Live modda olunduğu ekranın her
  yerinden, bir saniyede anlaşılmalı.
