---
version: alpha
name: ScryneQuant
description: Kripto spot stratejilerini araştıran, backtest eden ve risk kapılarından geçirerek uygulayan tek kişilik quant platformu.
---

# ScryneQuant

> **Token durumu:** Bu dosyanın frontmatter'ında `colors` / `typography` / `spacing`
> blokları **bilerek yok.** Arayüz Faz 6'da başlıyor (K-012); token'ları uyduran değil,
> gerçek bir kaynaktan (Tailwind config / tema dosyası) türeten bir dosya istiyoruz.
> Faz 6'ya gelindiğinde `ui-ux-pro-max` ile palet ve tipografi seçilir, `create-design-md`
> ile bu dosya koddan kanıta dayanarak tamamlanır, sonra doğrulanır:
>
> ```bash
> npx @google/design.md lint DESIGN.md
> npx @google/design.md export --format css-tailwind DESIGN.md
> ```
>
> Aşağıdaki karar katmanı ise **şimdi** geçerlidir ve Faz 6'da bağlayıcıdır.

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

Kesin değerler Faz 6'da frontmatter'a girer. Şimdiden bağlayıcı olan **anlam ataması**:

| Rol | Kullanım | Kısıt |
| --- | --- | --- |
| Risk / uyarı | Limit ihlali, SAFE_MODE, kill switch, bayat veri, reconciliation uyuşmazlığı | Tek yüksek doygunluklu renk. Arayüzde başka hiçbir yerde kullanılmaz. |
| Yön (kâr/zarar) | Getiri, PnL, değişim | Düşük doygunluk. Renk tek başına anlam taşımaz; işaret (+/−) her zaman yanındadır. |
| Etkileşim | Buton, link, seçili satır | Nötr-soğuk accent. Veri renkleriyle karışmaz. |
| Nötr yüzey | Tablo, kart, arka plan | Opak. Gri skalası veri yoğunluğuna göre kademelenir. |

**Neden kâr için canlı yeşil/kırmızı yok:** Standart trading arayüzü her sayıyı yeşil-kırmızı
boyar. Sonuç: ekran sürekli parlar, göz renge alışır ve **gerçekten önemli olan tek şey —
risk uyarısı — aynı görsel dili konuştuğu için kaybolur.** Doygunluğu risk için saklamak, bu
projede sinyal/gürültü oranını yükselten en ucuz karardır. Ayrıca yeşil-kırmızı yoğun
arayüzler bu ürünün tam olarak olmak istemediği şeyi çağrıştırır: kumarhane.

## Typography

Kesin eşleşme Faz 6'da. Şimdiden bağlayıcı olan:

- **Sayılar birinci sınıf.** Tüm sayısal veri **tabular (sabit genişlikli) rakamlarla**
  dizilir; sütunlarda ondalık hizası tutar. Sayı değiştiğinde satırın genişliği oynamaz.
- Fiyat, miktar, oran ve zaman damgası için **mono**; başlık ve açıklama için okunaklı bir
  sans. İki aile, daha fazlası değil.
- Yoğunluk lehine küçük taban boyut kabul edilebilir, ama **kontrast asla feda edilmez**
  (WCAG 4.5:1 normal metin).

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

## Cam kısıtı — global varsayılanın bilinçli ezilmesi

Global taban dark glassmorphism'i varsayılan estetik yapıyor. **Bu projede cam yalnızca
üst katman yüzeylerinde kullanılır:** modal, kill switch onayı, komut paleti, bildirim.

**Veri yüzeyleri (tablo, sayı, grafik, risk paneli) opaktır.** Gerekçe global dosyanın
kendi kuralından çıkıyor: `backdrop-filter` kontrastı düşürür ve altındaki içeriğe göre
değişken bir zemin yaratır. Yoğun sayısal veride bu iki şey doğrudan okuma hatasına yol
açar — ve bu üründe okuma hatasının bedeli para. Cam, arkasında bir şey olduğunda güzeldir;
arkasında bir sayı olduğunda tehlikelidir.

Bu, global `~/.claude/CLAUDE.md`'nin "sadece kilit elementlerde kullan" kuralının bu projeye
özel, daha sıkı hâlidir — çelişki değil, daraltma.

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
