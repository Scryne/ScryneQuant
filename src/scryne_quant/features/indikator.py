"""İndikatörler: saf, nedensel (causal), NaN-ısınmalı numpy fonksiyonları. (Faz 2)

Bu modülün üç sözleşmesi var ve üçü de testle korunur:

1. **Nedensellik.** `cikti[t]` yalnızca `girdi[0..t]`'ye bağlıdır. Bu, K-002'nin
   (look-ahead yasağı) indikatör katmanındaki karşılığı: strateji `ctx`'ten okuduğu
   indikatör değerinin geçmişten türediğini varsayabilmeli. Merkezlenmiş pencere,
   `bfill`, `interpolate` gibi geleceğe bakan hiçbir işlem burada kullanılmaz.
2. **Isınma NaN'dır, uydurulmaz.** Bir indikatörün ilk `n-1` (veya `n`) değeri yoktur;
   olmayan değer NaN olarak kalır. İleri doldurma veya kırpma yasak — kırpmak indeksleri
   kaydırır ve bar hizasını bozar, doldurmak veri uydurmaktır (K-024'ün ruhu).
3. **Girdi bozulmaz.** Fonksiyonlar argümanlarını değiştirmez, yeni dizi döndürür.

**Referans konvansiyonu (K-026):** TA-Lib. Ölçülerek doğrulandı, varsayılmadı:
- `EMA(n)`: ilk değer indeks `n-1`'de ve **ilk n değerin SMA'sı** ile tohumlanır.
- `RSI(n)`, `ATR(n)`: ilk değer indeks `n`'de (ikisi de fark serisi üzerinde çalışır).
- `BBANDS`: standart sapma **popülasyon** (ddof=0).

Kayan nokta notu: bu fonksiyonlar TA-Lib ile **bit düzeyinde** aynı olmaz (~1e-13 bağıl
fark) çünkü TA-Lib yürüyen toplam kullanır, numpy pencere başına toplar. İkisi de doğru;
determinizm iddiası (K-009) TA-Lib'e eşitlik değil, **kendi çıktımızın çalıştırmalar
arasında değişmemesi**dir.
"""

from __future__ import annotations

from typing import Final, NamedTuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

#: Isınma sırasında yazılan değer. Sıfır değil: sıfır geçerli bir indikatör değeridir ve
#: "henüz hesaplanamadı" ile "değeri sıfır" karıştırılırsa strateji sessizce yanlış işlem
#: açar.
YOK: Final[float] = np.nan


class GecersizParametre(ValueError):
    """İndikatör parametresi anlamsız (pencere < 1, seri pencereden kısa, vb.)."""


class Bantlar(NamedTuple):
    """Bollinger bantları. Üçü de aynı uzunlukta, aynı ısınma maskesiyle."""

    alt: np.ndarray
    orta: np.ndarray
    ust: np.ndarray


def _dizi(degerler: np.ndarray) -> np.ndarray:
    """Girdiyi tek boyutlu float64 diziye çevirir.

    `asarray` kopya üretmeyebilir; bu yüzden bu modüldeki hiçbir fonksiyon sonucu
    girdinin belleğine yazmaz — her biri kendi çıktı dizisini ayırır.
    """
    out = np.asarray(degerler, dtype=np.float64)
    if out.ndim != 1:
        raise GecersizParametre(f"tek boyutlu seri bekleniyor, ndim={out.ndim}")
    return out


def _pencere_kontrol(uzunluk: int, pencere: int) -> None:
    if pencere < 1:
        raise GecersizParametre(f"pencere en az 1 olmalı, verilen: {pencere}")
    if uzunluk < pencere:
        raise GecersizParametre(f"seri pencereden kısa: {uzunluk} < {pencere}")


def sma(degerler: np.ndarray, pencere: int) -> np.ndarray:
    """Basit hareketli ortalama. İlk geçerli değer indeks ``pencere-1``."""
    x = _dizi(degerler)
    _pencere_kontrol(x.size, pencere)

    out = np.full(x.size, YOK)
    if pencere == 1:
        out[:] = x
        return out
    out[pencere - 1 :] = sliding_window_view(x, pencere).mean(axis=-1)
    return out


def ema(degerler: np.ndarray, pencere: int) -> np.ndarray:
    """Üssel hareketli ortalama, α = 2/(n+1).

    Tohum: ilk `n` değerin SMA'sı, indeks `n-1`'e yazılır (TA-Lib konvansiyonu, K-026).
    "İlk değerden başlat" alternatifi ısınma bölgesinde farklı sayı üretir; ölçtük,
    TA-Lib'in yaptığı bu değil — ve grafik platformlarıyla karşılaştırma yapılacağı gün
    o farkın nereden geldiğini kimse hatırlamaz.
    """
    x = _dizi(degerler)
    _pencere_kontrol(x.size, pencere)

    out = np.full(x.size, YOK)
    alfa = 2.0 / (pencere + 1.0)
    onceki = float(x[:pencere].mean())
    out[pencere - 1] = onceki
    for i in range(pencere, x.size):
        onceki = alfa * x[i] + (1.0 - alfa) * onceki
        out[i] = onceki
    return out


def _wilder(seri: np.ndarray, pencere: int, ilk_indeks: int) -> np.ndarray:
    """Wilder yumuşatması: ilk değer basit ortalama, sonrası ``(önceki*(n-1) + x)/n``.

    `seri` NaN başlangıçlı olabilir; `ilk_indeks` ilk çıktının yazılacağı konumdur ve
    tohum ``seri[ilk_indeks-pencere+1 : ilk_indeks+1]``in ortalamasıdır.
    """
    out = np.full(seri.size, YOK)
    onceki = float(seri[ilk_indeks - pencere + 1 : ilk_indeks + 1].mean())
    out[ilk_indeks] = onceki
    for i in range(ilk_indeks + 1, seri.size):
        onceki = (onceki * (pencere - 1) + seri[i]) / pencere
        out[i] = onceki
    return out


def rsi(kapanis: np.ndarray, pencere: int = 14) -> np.ndarray:
    """Wilder RSI. İlk geçerli değer indeks ``pencere``.

    Formül ``100 · K / (K + Z)`` biçiminde yazılıyor (K = ortalama kazanç, Z = ortalama
    kayıp). Z > 0 iken bu, klasik ``100 − 100/(1+RS)`` ile cebirsel olarak aynıdır, ama
    Z → 0'da bölme patlaması yerine doğal olarak 100'e gider.

    **TA-Lib'den bilinçli tek sapma (K-026):** hem kazanç hem kayıp sıfırsa (pencere
    boyunca fiyat hiç kımıldamadıysa) TA-Lib **0.0** döndürür. 0, RSI ölçeğinde "azami
    aşırı satım" demektir — yani hiç hareket etmeyen bir piyasa, mean-reversion
    stratejisine üretilebilecek en güçlü alım sinyalini verir. Bu sayı yanlış değil,
    *tehlikeli*: hatalı ama makul görünen sonuç sınıfından. Biz NaN döndürüyoruz:
    hareket yoksa RSI tanımsızdır, ve NaN ile yapılan her karşılaştırma False olduğu
    için hiçbir eşik tetiklenmez.
    """
    x = _dizi(kapanis)
    _pencere_kontrol(x.size, pencere + 1)

    fark = np.diff(x)
    kazanc = np.where(fark > 0.0, fark, 0.0)
    kayip = np.where(fark < 0.0, -fark, 0.0)

    # Fark serisinin j. elemanı, kapanış serisinin j+1. barına aittir; bu yüzden fark
    # uzayındaki ilk indeks `pencere-1`, kapanış uzayında `pencere`ye denk gelir.
    ort_kazanc = _wilder(kazanc, pencere, pencere - 1)
    ort_kayip = _wilder(kayip, pencere, pencere - 1)

    gecerli = ~np.isnan(ort_kazanc)
    k = ort_kazanc[gecerli]
    z = ort_kayip[gecerli]

    toplam = k + z
    hareket_var = toplam > 0.0
    deger = np.full(k.size, YOK)
    deger[hareket_var] = 100.0 * k[hareket_var] / toplam[hareket_var]

    out = np.full(x.size, YOK)
    out[1:][gecerli] = deger
    return out


def gercek_aralik(yuksek: np.ndarray, dusuk: np.ndarray, kapanis: np.ndarray) -> np.ndarray:
    """True Range. İlk bar NaN: önceki kapanış olmadan TR tanımlı değil.

    TA-Lib ilk bara `high-low` yazar ama ATR hesabında onu kullanmaz; biz de
    kullanmıyoruz. NaN bırakmak "önceki kapanış yoktu" bilgisini korur.
    """
    h, d, k = _dizi(yuksek), _dizi(dusuk), _dizi(kapanis)
    if not h.size == d.size == k.size:
        raise GecersizParametre(f"seri uzunlukları eşit değil: {h.size}/{d.size}/{k.size}")
    if h.size < 2:
        raise GecersizParametre("true range için en az 2 bar gerekir")

    out = np.full(h.size, YOK)
    onceki_kapanis = k[:-1]
    out[1:] = np.maximum(
        h[1:] - d[1:],
        np.maximum(np.abs(h[1:] - onceki_kapanis), np.abs(d[1:] - onceki_kapanis)),
    )
    return out


def atr(
    yuksek: np.ndarray, dusuk: np.ndarray, kapanis: np.ndarray, pencere: int = 14
) -> np.ndarray:
    """Wilder ATR. İlk geçerli değer indeks ``pencere`` — TR indeks 1'den başladığı için."""
    tr = gercek_aralik(yuksek, dusuk, kapanis)
    _pencere_kontrol(tr.size, pencere + 1)
    return _wilder(tr, pencere, pencere)


def bollinger(kapanis: np.ndarray, pencere: int = 20, katsayi: float = 2.0) -> Bantlar:
    """Bollinger bantları: SMA ± katsayı × popülasyon standart sapması (ddof=0, K-026).

    ddof seçimi ölçümle sabitlendi: TA-Lib popülasyon sapması kullanıyor. ddof=1'e
    geçmek 20 barlık pencerede bandı ~%2,6 genişletir — yani her breakout stratejisinin
    tetiklenme sayısını değiştirir. Bu bir tercih değil, kalibrasyon sabiti.
    """
    x = _dizi(kapanis)
    _pencere_kontrol(x.size, pencere)
    if katsayi < 0.0:
        raise GecersizParametre(f"katsayı negatif olamaz: {katsayi}")

    orta = sma(x, pencere)
    sapma = np.full(x.size, YOK)
    sapma[pencere - 1 :] = sliding_window_view(x, pencere).std(axis=-1, ddof=0)
    return Bantlar(alt=orta - katsayi * sapma, orta=orta, ust=orta + katsayi * sapma)


def hacim_ortalamasi(hacim: np.ndarray, pencere: int = 20) -> np.ndarray:
    """Hacmin basit hareketli ortalaması.

    Ayrı bir isimle duruyor çünkü çağrı yerinde "hangi seri" sorusunu ortadan kaldırıyor:
    `sma(df["close"], 20)` yerine yanlışlıkla `sma(df["volume"], 20)` yazmak sessiz bir
    hatadır, `hacim_ortalamasi` çağrısı değil.
    """
    return sma(hacim, pencere)


def en_yuksek(degerler: np.ndarray, pencere: int) -> np.ndarray:
    """Kayan pencere azamisi (Donchian üst kanalı). İlk geçerli değer indeks ``pencere-1``.

    **Dikkat — pencere `t` barını içerir.** Donchian kırılımı "fiyat önceki N barın
    zirvesini aştı mı" diye sorar; `t`'nin kendi zirvesini içeren bir kanalla
    karşılaştırma yapmak her zaman `kapanış ≤ kanal` verir ve kırılım hiç oluşmaz.
    Bu yüzden kaydırma **stratejinin** işi: `ctx.ozellik("kanal_ust", 1)` ile bir bar
    geriden okunur. İndikatörün kendisi TA-Lib'in `MAX`'ıyla birebir kalır (K-026) —
    kaydırmayı buraya gömmek, referansla karşılaştırmayı imkânsız kılardı.
    """
    x = _dizi(degerler)
    _pencere_kontrol(x.size, pencere)

    out = np.full(x.size, YOK)
    if pencere == 1:
        out[:] = x
        return out
    out[pencere - 1 :] = sliding_window_view(x, pencere).max(axis=-1)
    return out


def en_dusuk(degerler: np.ndarray, pencere: int) -> np.ndarray:
    """Kayan pencere asgarisi (Donchian alt kanalı). Kaydırma notu: bkz. `en_yuksek`."""
    x = _dizi(degerler)
    _pencere_kontrol(x.size, pencere)

    out = np.full(x.size, YOK)
    if pencere == 1:
        out[:] = x
        return out
    out[pencere - 1 :] = sliding_window_view(x, pencere).min(axis=-1)
    return out


def roc(kapanis: np.ndarray, pencere: int = 10) -> np.ndarray:
    """Değişim oranı, **yüzde** olarak (TA-Lib `ROC` konvansiyonu, K-026).

    ``(close[t] / close[t-n] - 1) × 100``. İlk geçerli değer indeks ``pencere``.

    Yüzde ölçeği bilinçli: TA-Lib `ROC` yüzde, `ROCP` kesir döndürür. İkisinden birini
    seçmek zorundaydık ve referansla karşılaştırılabilir olan `ROC`. Eşik yazarken
    `ctx.ozellik("roc") > 2.0` "%2" demektir, "2 kat" değil — bu ayrım bir stratejide
    50 kat yanlış pozisyon büyüklüğü demek olurdu, o yüzden isim ve birim burada sabit.
    """
    x = _dizi(kapanis)
    _pencere_kontrol(x.size, pencere + 1)

    out = np.full(x.size, YOK)
    onceki = x[:-pencere]
    with np.errstate(divide="ignore", invalid="ignore"):
        oran = np.where(onceki != 0.0, x[pencere:] / onceki - 1.0, np.nan)
    out[pencere:] = oran * 100.0
    return out


def persentil_sirasi(degerler: np.ndarray, pencere: int) -> np.ndarray:
    """Değerin kendi kayan penceresi içindeki persentil sırası, [0,1]. (K-042/3)

    ``(pencerede x[t]'den küçük veya eşit değer sayısı) / pencere``. İlk geçerli değer
    indeks ``pencere-1``; pencere `t` barını **içerir** ve içermesi gerekir — sorulan şey
    "bugünkü değer, son N günün neresinde", ve bugünkü değer bugün biliniyor.

    **Neden persentil, neden mutlak eşik değil (K-042/3).** Funding'in medyanı kalıcı
    olarak pozitif (ölçülen: +0,0096% / 8 saat). "funding > 0" koşulu neredeyse her zaman
    doğru olur ve hiçbir şey ayırt etmez. Persentil sırası seviyeyi değil **göreliliği**
    ölçer: "bu, son N barın en yüksek %5'inde mi" sorusu, serinin ortalaması kaysa bile
    aynı anlamı taşır.

    `en_yuksek`/`en_dusuk`ün aksine burada **kaydırma yok** ve olmamalı: Donchian'da
    karşılaştırılan şey fiyatın kanalı aşıp aşmadığıydı ve kanal `t`'yi içerince
    karşılaştırma anlamsızlaşıyordu. Burada `t`, penceresinin içindeki yerini soruyor;
    kendini dışlamak soruyu değiştirirdi.

    Penceresinde `NaN` bulunan hiçbir nokta hesaplanmaz — boşluk uydurulmaz (K-024).
    """
    x = _dizi(degerler)
    _pencere_kontrol(x.size, pencere)

    out = np.full(x.size, YOK)
    if pencere == 1:
        # Tek elemanlı pencerede her değer kendi penceresinin tamamı: sıra her zaman 1,0.
        out[:] = np.where(np.isnan(x), YOK, 1.0)
        return out

    gorunum = sliding_window_view(x, pencere)
    gecerli = ~np.isnan(gorunum).any(axis=-1)
    simdi = gorunum[:, -1]
    sayim = (gorunum <= simdi[:, None]).sum(axis=-1)
    out[pencere - 1 :] = np.where(gecerli, sayim / pencere, YOK)
    return out


def kumulatif(degerler: np.ndarray, pencere: int) -> np.ndarray:
    """Kayan pencere toplamı. İlk geçerli değer indeks ``pencere-1``.

    Funding için anlamı: son N bar boyunca **birikmiş** ödeme baskısı. Tek bir ölçüm
    gürültülü; birikim, rejimi tek değerden daha kararlı gösterir — hipotez bu
    (`funding_egilim`, K-042/5).

    Penceresinde `NaN` varsa sonuç `NaN`; sıfır sayıp toplamak, olmayan bir ödemeyi
    olmuş gibi göstermek olurdu (K-024).
    """
    x = _dizi(degerler)
    _pencere_kontrol(x.size, pencere)

    out = np.full(x.size, YOK)
    gorunum = sliding_window_view(x, pencere)
    gecerli = ~np.isnan(gorunum).any(axis=-1)
    out[pencere - 1 :] = np.where(gecerli, gorunum.sum(axis=-1), YOK)
    return out


def kumulatif_persentil(
    degerler: np.ndarray, birikim: int, pencere: int
) -> np.ndarray:
    """Önce kayan toplam, sonra o toplamın kendi penceresindeki persentil sırası.

    İki adımı tek fonksiyonda birleştirmek bir kolaylık değil **zorunluluk**: özellik
    motoru indikatörleri zincirleyemiyor — her kaydın girdisi bir *bar alanı*, başka bir
    özellik değil (`features/motor.py`'nin `DEFTER`i). Zincirlemeyi motora eklemek,
    hesaplama sırasına ve ad çözümlemesine bağlı yeni bir yüzey açardı; iki adımlık tek
    bir soru için bu fazla pahalı.

    İlk geçerli değer indeks ``birikim + pencere - 2``: önce toplam ısınır, sonra persentil.
    """
    x = _dizi(degerler)
    _pencere_kontrol(x.size, birikim)
    toplam = kumulatif(x, birikim)
    _pencere_kontrol(toplam.size, pencere)
    return persentil_sirasi(toplam, pencere)
