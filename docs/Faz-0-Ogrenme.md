---
proje: ScryneQuant
created: 2026-09-08
type: ogrenme-listesi
status: aktif
---
# Faz 0 — Öğrenme Listesi

Bu liste "trading öğren" listesi **değil.** Amacı tek şey: bu projede senin vereceğin
kararları verebilecek kadar bilmek. Her maddenin yanında **hangi kararda işine yarayacağı**
yazıyor — o karar gelmeden önce o maddeyi bilmen gerekiyor.

**Ölçü:** her kavram için ScryneOS vault'unda `🧠 500-Knowledge/` altına kendi cümlelerinle
bir paragraf. Kopyala-yapıştır değil — kendi cümlen olmazsa anlamamışsındır, ve bunu ancak
yazmaya çalışınca fark edersin.

**Süre beklentisi:** 12 madde, her biri 15-30 dakika. Toplam bir hafta sonu. Uzarsa fazla
derine iniyorsundur; bu liste bilerek sığdır.

---

## Grup 1 — Piyasa neye benziyor (4 madde)

### 1. Candle (mum) ve OHLCV
Bir mum nedir; açılış, en yüksek, en düşük, kapanış, hacim. Timeframe ne demek (1m, 1h, 1d).
Bir mumun "kapanması" ne demek.

> **Nerede lazım:** K-005 ve K-004. Sistemde bir mumun `timestamp`'i o mumun **açılış**
> zamanı, ve sinyal ancak mum **kapandığında** üretiliyor. Bu ikisi anlaşılmadan Faz 3'te
> motorun doğru çalışıp çalışmadığını kontrol edemezsin.

### 2. Order book, bid / ask, spread
Alış-satış defteri nedir. En iyi alış (bid) ile en iyi satış (ask) arasındaki farka spread
denir. Neden sıfır değildir.

> **Nerede lazım:** K-007. Spread, slippage'ın kaynağı. "8 bps slippage varsayımı makul mü"
> sorusuna cevap veremezsen backtest'in yalan söylediğini fark edemezsin.

### 3. Likidite ve derinlik
Bir emir fiyatı ne kadar hareket ettirir. Neden 10.000₺'lik emir BTC'de hiçbir şeyi
oynatmazken küçük bir coinde fiyatı yukarı iter.

> **Nerede lazım:** Neden BTC/USDT ile başlıyoruz, ve ileride sembol eklerken neyin
> sorulacağı. Backtest küçük coinlerde neden sistematik olarak yalan söyler.

### 4. Spot vs. futures, kaldıraç, likidasyon
Spot: parayla varlık alırsın, elinde durur. Futures: kaldıraçlı sözleşme, fiyat aleyhine
gidince pozisyon zorla kapatılır (likidasyon) ve para gider.

> **Nerede lazım:** K-008. Kill switch'in "pozisyonları kapatma, tut" kararı **spot'a
> özeldir.** Futures'a geçilirse bu karar yanlış olur ve neden yanlış olduğunu bilmen
> gerekir. v1'de futures yok, ama bu farkı bilmeden neden yok olduğunu da bilemezsin.

---

## Grup 2 — İşlem nasıl yapılır (3 madde)

### 5. Emir türleri: market, limit, stop — ve maker/taker
Market emri: hemen, mevcut fiyattan. Limit emri: belirlediğin fiyattan, dolmayabilir.
Stop: bir seviyeye değince tetiklenen emir. **Maker** defterde bekleyen, **taker** defterden
alan taraftır ve komisyonları farklıdır.

> **Nerede lazım:** K-007 her iki bacakta da **taker** varsayıyor — yani en pahalı senaryo.
> Bu muhafazakâr bir seçim; neden muhafazakâr olduğunu anlaman lazım.

### 6. Long / short
Long: yükseleceğini düşünüp alırsın. Short: düşeceğini düşünüp ödünç alıp satarsın.

> **Nerede lazım:** Spot piyasada pratikte sadece long var. v1'in bütün stratejileri tek
> yönlü; bu bir kısıt ve nereden geldiğini bilmelisin.

### 7. Slippage
Emri gönderdiğin andaki fiyat ile gerçekten dolduğu fiyat arasındaki fark. Her zaman
aleyhine çalışma eğilimindedir.

> **Nerede lazım:** Sana anlattığım %43'lük örnek buydu. Slippage'ı 1 bps yerine 8 bps
> girmek, 400 işlemde sermayenin ~%43'ünü backtest'te görünmeden yok eder. Kod doğru
> çalışır, test yeşil kalır, sadece sayı yanlıştır.

---

## Grup 3 — Maliyet (2 madde)

### 8. Komisyon (fee) ve tarife
Borsa her işlemden komisyon alır. **Alışta bir kez, satışta bir kez** — yani bir
gidiş-dönüş iki komisyon demek. Binance'in güncel spot tarifesine bak, maker ve taker
oranlarını not et.

> **Nerede lazım:** Faz 0'ın sınavı (aşağıda) doğrudan bu. Ayrıca K-016 spike'ının çıktısı
> bu sayılar olacak.

### 9. İşlem sıklığı ile maliyet ilişkisi
Bir strateji ne kadar çok işlem yaparsa maliyet o kadar birikir. Günde 10 işlem yapan bir
strateji, işlem başına çok küçük bir avantaja sahip olsa bile maliyetin altında kalır.

> **Nerede lazım:** Faz 4'te stratejileri karşılaştırırken. "Çok işlem yapan strateji daha
> çok kazanır" sezgisi yanlıştır ve dokümanının §56'sı bunu yanılgı listesine koymuş.

---

## Grup 4 — Risk ve sonucu okuma (3 madde)

### 10. Position sizing / işlem başına risk
Bir işleme sermayenin ne kadarını koyuyorsun, ve o işlemde en fazla ne kadar kaybetmeyi
göze alıyorsun. Bu ikisi farklı şeyler.

> **Nerede lazım:** Faz 5'in tamamı. Risk motorunun ilk işi bu.

### 11. Drawdown ve max drawdown
Sermayenin tepe noktasından dibe kadar yaptığı düşüş. Max drawdown, en kötüsü.

> **Nerede lazım:** **K-010'un kapısında okuyacağın sayı bu.** "%34 max drawdown"
> 100.000₺'nin bir noktada 66.000₺ olması demek. Bu sayıyı hissetmeden o kapıyı tutamazsın.

### 12. Volatilite
Fiyatın ne kadar oynadığı. Neden aynı stratejinin aynı pozisyon boyutu farklı
volatilitelerde farklı risk taşır.

> **Nerede lazım:** Faz 5'te volatilite guard, ve pozisyon boyutunun neden sabit olmadığı.

---

## Sonra (Faz 4'e kadar gerekmez, ama listede dursun)

- **Sharpe oranı** — getiriyi aldığın riske bölen ölçü. Faz 4'te karşılaştırmanın ana metriği.
- **Win rate tuzağı** — %70 kazanma oranı iyi demek değildir; 7 küçük kazanç 3 büyük kayba
  yenilir. Dokümanının §56'sı bunu ayrıca uyarıyor.
- **Profit factor** — toplam kazancın toplam kayba oranı; win rate'ten daha dürüst.

---

## Sınav — kalemle bir işlem

Kavramları bitirdiğinde bunu yap. Amaç sınav geçmek değil: **bu sayı Faz 3'te backtest
motorunun doğru çalıştığını kanıtlayan referans olacak.** Motor senin elle bulduğun sayıyı
tutturamıyorsa motor bozuktur.

Senaryo:

```
Sermaye        : 10.000 ₺ karşılığı USDT
Alış           : BTC/USDT, market emri (yani taker)
Alış fiyatı    : (Binance'ten güncel bir fiyat al)
Slippage       : alışta aleyhine 8 bps
Komisyon       : Binance'in güncel taker oranı
...pozisyonu tut, fiyat %2 yükselsin...
Satış          : market emri (yine taker)
Slippage       : satışta aleyhine 8 bps
Komisyon       : yine taker
```

**Sorular:**
1. Elinde net kaç ₺ kaldı?
2. Brüt %2 kazanmıştın — net yüzde kaç kazandın?
3. Bu işlemin kârlı olması için fiyatın **en az** yüzde kaç yükselmesi gerekiyordu?

Üçüncü soru en önemlisi. Cevabı gördüğünde, "günde 10 işlem yapan bot" fikrinin neden
tehlikeli olduğunu kimse anlatmadan anlayacaksın.

---

## Nereden öğrenilir

- **Binance Academy** — ücretsiz, kavram sözlüğü iyi, ve zaten kullanacağımız borsa.
  Terimler birebir eşleşir.
- **Investopedia** — tanım aramak için. Uzun okumalarına girme, tanımı al çık.
- Herhangi bir kaynağın kendi arayüzünden bak: Binance'te bir order book aç, spread'i
  gözünle gör. **Beş dakikalık bakış, otuz dakikalık okumadan iyi.**

## Ne öğrenmemelisin (bilerek liste dışı)

Aşağıdakiler bu projede işine yaramaz ve zamanını yer:

- **Grafik formasyonları** (omuz-baş-omuz, üçgen, bayrak) — sistematik olarak test edilmesi
  zor, ve bizim stratejilerimiz kural tabanlı olacak.
- **Elliott Wave, Fibonacci, Gann** ve benzeri.
- **"Hangi indikatör en iyi"** tartışmaları — cevabı yok; Faz 4'ün amacı zaten bunu ölçmek.
- **Haber/temel analiz, on-chain metrikler** — v1 kapsamı dışında.
- **Futures ve opsiyon mekaniği** — madde 4'teki farkı bilmen yeterli, derinine girme.
- **Vergi** — henüz gerçek para yok, sırası gelince.

**Uyarı:** trading içeriğinin büyük kısmı bir şey satıyor (kurs, sinyal grubu, referans
linki). Kavram öğrenirken sorun değil ama "şu strateji çalışıyor" diyen hiçbir kaynağa
inanma — zaten bu projenin tamamı, o cümlenin doğru olup olmadığını **ölçmek** için var.

---

## Bitti kriteri

- [ ] 12 kavramın her biri için vault'ta kendi cümlelerinle bir paragraf
- [ ] Sınavdaki üç sorunun cevabı hesaplanmış ve yazılmış
- [ ] Binance'te bir order book'a bakılmış, spread gözle görülmüş

Bunlar bittiğinde Faz 0'ın öğrenme kısmı kapanır; geriye dört spike kalır
(`docs/spikes/README.md`).
