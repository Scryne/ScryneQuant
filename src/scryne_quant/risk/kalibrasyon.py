"""Risk limitlerinin veriden kalibrasyonu. (K-033, K-021 kalıbı)

Üç limit bu modülde **ölçülüyor**, seçilmiyor:

1. `volatilite_esigi` — ATR(14)/fiyat dağılımının yüksek persentili. Guard'ın amacı
   "olağandışı çalkantıda işlem yapmamak"; olağandışının tanımı veriden gelmeli.
2. `ters_hareket_atr_carpani` — bir girişin **risk ufku** boyunca gördüğü en kötü aleyhte
   hareketin kaç ATR olduğu. Geleneksel "2×ATR" varsayımı bu veride riski hafife alıyor
   (ölçüm: 24 barlık ufukta medyan 2,07 ATR); bu yüzden varsayım ölçülüyor.
3. `gunluk_zarar_limiti` — günlük getiri dağılımı ile azami maruziyetin birleşimi. Limitin
   "kaç günde bir tetiklenir" sorusuna sayısal bir cevabı olmak zorunda, yoksa ya her kötü
   günde duran ya da hiç durmayan bir fren olur.

Diğer beş limit iştah tercihidir ve burada ölçülmüyor — `limitler.Gerekce.kaynak` onları
`istah` olarak işaretliyor ve her birine bir gözden geçirme koşulu yazmak zorunlu.

**Risk ufku neden tutma süresi:** v1'de borsada duran bir stop emri yok (Faz 7), yani
pozisyon strateji `FLAT` diyene kadar açık kalır. "Aleyhte ne kadar giderim" sorusunun ufku
bu yüzden bir stop mesafesi değil, **tutma süresi**. Faz 4'ün altı stratejisinin kapanmış
2.834 işleminde medyan tutma süresi 27 saat ölçüldü — 1h barda 24-27 bar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np

from scryne_quant.features.indikator import atr as atr_hesapla

#: Persentiller: hem karar için hem `Gerekce.dagilim` kaydına. K-021'in kalıbı — tam
#: dağılımı saklamak, persentil kararını yeniden ölçmeden değiştirilebilir kılıyor.
PERSENTILLER: Final[tuple[float, ...]] = (50.0, 75.0, 90.0, 95.0, 99.0, 99.5, 99.9)

#: Volatilite guard'ının persentili. p99: "yüzde birlik en çalkantılı barlarda işlem yok".
#: p95 seçilseydi guard her 20 barda bir devreye girer ve stratejinin kendi kararlarının
#: yerine geçerdi; p99,9 ise yılda birkaç bar demek, yani neredeyse hiç.
VOLATILITE_PERSENTILI: Final = 99.0

#: Aleyhte hareket persentili. p90: onda dokuz vakada gerçek aleyhte hareket bu varsayımın
#: altında kalır. p50 (yani geleneksel 2×ATR civarı) vakaların **yarısında** riski hafife
#: almak demek — K-007'nin "belirsizlikte kötü yöne yuvarla" kuralının ihlali.
TERS_HAREKET_PERSENTILI: Final = 90.0

#: Risk ufku (bar). Faz 4'te ölçülen medyan tutma süresi 27 saat ≈ 24 bar (1h).
VARSAYILAN_UFUK_BAR: Final = 24

#: ATR penceresi. `backtest.motor.RISK_ATR_PENCERESI` ile aynı olmak zorunda — testle
#: kontrol ediliyor, çünkü farklı pencereyle kalibre edilip farklı pencereyle uygulanan
#: bir eşik sessizce yanlış olur.
ATR_PENCERESI: Final = 14


@dataclass(frozen=True, slots=True)
class VolatiliteOlcumu:
    """ATR/fiyat dağılımı ve seçilen eşik."""

    esik: float
    persentil: float
    dagilim: dict[str, float]
    bar_sayisi: int

    def sozluk(self) -> dict[str, Any]:
        return {
            "esik": self.esik,
            "persentil": self.persentil,
            "dagilim": self.dagilim,
            "bar_sayisi": self.bar_sayisi,
        }


@dataclass(frozen=True, slots=True)
class TersHareketOlcumu:
    """Aleyhte hareketin ATR katı cinsinden dağılımı ve seçilen çarpan."""

    carpan: float
    persentil: float
    ufuk_bar: int
    dagilim: dict[str, float]
    ornek_sayisi: int

    def sozluk(self) -> dict[str, Any]:
        return {
            "carpan": self.carpan,
            "persentil": self.persentil,
            "ufuk_bar": self.ufuk_bar,
            "dagilim": self.dagilim,
            "ornek_sayisi": self.ornek_sayisi,
        }


@dataclass(frozen=True, slots=True)
class GunlukZararOlcumu:
    """Günlük getiri dağılımı ve bir limitin tetikleme sıklığı."""

    limit: float
    azami_maruziyet: float
    tetikleme_orani: float
    """Limitin tetiklendiği günlerin oranı — ölçülmüş maruziyet tavanında."""

    tetiklenen_gun: int
    gun_sayisi: int
    dagilim: dict[str, float]
    """Günlük getiri persentilleri (kayıp tarafı)."""

    aday_tablosu: dict[str, float] = field(default_factory=dict)
    """Aday limit → tetikleme oranı. Kararın neden bu sayı olduğunu gösteren tablo."""

    def sozluk(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "azami_maruziyet": self.azami_maruziyet,
            "tetikleme_orani": self.tetikleme_orani,
            "tetiklenen_gun": self.tetiklenen_gun,
            "gun_sayisi": self.gun_sayisi,
            "dagilim": self.dagilim,
            "aday_tablosu": self.aday_tablosu,
        }


def _dagilim(
    degerler: np.ndarray, persentiller: tuple[float, ...] = PERSENTILLER
) -> dict[str, float]:
    return {f"p{p:g}": float(np.percentile(degerler, p)) for p in persentiller}


def volatilite_olc(
    yuksek: np.ndarray,
    dusuk: np.ndarray,
    kapanis: np.ndarray,
    *,
    persentil: float = VOLATILITE_PERSENTILI,
    pencere: int = ATR_PENCERESI,
) -> VolatiliteOlcumu:
    """ATR/fiyat dağılımını ölçer ve guard eşiğini seçer."""
    oran = atr_hesapla(yuksek, dusuk, kapanis, pencere) / np.asarray(kapanis, dtype=np.float64)
    gecerli = oran[~np.isnan(oran)]
    if gecerli.size == 0:
        raise ValueError("ATR/fiyat ölçülemedi: geçerli bar yok")
    return VolatiliteOlcumu(
        esik=float(np.percentile(gecerli, persentil)),
        persentil=persentil,
        dagilim=_dagilim(gecerli),
        bar_sayisi=int(gecerli.size),
    )


def ters_hareket_olc(
    acilis: np.ndarray,
    dusuk: np.ndarray,
    yuksek: np.ndarray,
    kapanis: np.ndarray,
    *,
    ufuk_bar: int = VARSAYILAN_UFUK_BAR,
    persentil: float = TERS_HAREKET_PERSENTILI,
    pencere: int = ATR_PENCERESI,
) -> TersHareketOlcumu:
    """Bir girişin `ufuk_bar` içinde gördüğü en kötü aleyhte hareketi ATR katı olarak ölçer.

    Uzun-yönlü spot portföy için aleyhte yön **aşağı**: `i` barında girilse, `i..i+ufuk`
    aralığındaki en düşük fiyatın girişe göre farkı. Bu ölçü, v1'de olmayan bir stop
    emrinin yerine geçiyor: pozisyon elde tutulduğu sürece taşınan gerçek fiyat riski.
    """
    a = np.asarray(acilis, dtype=np.float64)
    d = np.asarray(dusuk, dtype=np.float64)
    atr_serisi = atr_hesapla(yuksek, dusuk, kapanis, pencere)
    n = a.size
    if n <= ufuk_bar:
        raise ValueError(f"ufuk ({ufuk_bar}) için yeterli bar yok: {n}")

    # Kayan pencere minimumu: her i için d[i..i+ufuk] en küçüğü. `np.minimum.reduce`
    # ile vektörel — döngü 45.000 barda fark etmez ama kalibrasyon birden çok kez
    # koşturulacak bir araç.
    kaydirilmis = np.lib.stride_tricks.sliding_window_view(d, ufuk_bar + 1)
    dip = kaydirilmis.min(axis=1)
    giris = a[: dip.size]
    atr_kesit = atr_serisi[: dip.size]

    ters = (giris - dip) / atr_kesit
    gecerli = ters[~np.isnan(ters) & np.isfinite(ters)]
    if gecerli.size == 0:
        raise ValueError("aleyhte hareket ölçülemedi")
    return TersHareketOlcumu(
        carpan=float(np.percentile(gecerli, persentil)),
        persentil=persentil,
        ufuk_bar=ufuk_bar,
        dagilim=_dagilim(gecerli),
        ornek_sayisi=int(gecerli.size),
    )


#: Günlük zarar limiti adayları. Kararın tablosu bunlar üzerinden kuruluyor.
GUNLUK_ADAYLAR: Final[tuple[float, ...]] = (0.015, 0.02, 0.025, 0.03)


def gunluk_zarar_olc(
    acilis_zamanlari: np.ndarray,
    kapanis: np.ndarray,
    *,
    azami_maruziyet: float,
    adaylar: tuple[float, ...] = GUNLUK_ADAYLAR,
    hedef_tetikleme: float = 0.0125,
) -> GunlukZararOlcumu:
    """Günlük getiri dağılımını ölçer ve hedef tetikleme oranına en yakın limiti seçer.

    `hedef_tetikleme` = %1,25: yaklaşık olarak "yüzde birlik en kötü günler". Bunun altında
    (örn. %3) limit normal bir kötü günde devreye girer ve stratejinin yerine karar verir;
    üstünde (%0,4) fren neredeyse hiç çalışmaz — varmış gibi görünüp yokmuş gibi davranır.

    Portföy zararı `azami_maruziyet × günlük getiri` olarak yaklaşılıyor: tavanda duran bir
    pozisyonun en kötü hâli. Daha düşük maruziyette limit daha da geç tetiklenir, yani
    yaklaşım **muhafazakâr** yönde hatalı (K-007).
    """
    t = np.asarray(acilis_zamanlari, dtype=np.int64)
    c = np.asarray(kapanis, dtype=np.float64)
    gun = t // 86_400_000

    # Her günün son barının kapanışı. `np.unique` son indeksi doğrudan vermediği için
    # ters çevirip ilk indeksi alıyoruz — sonuç aynı, döngü yok.
    ters_gun = gun[::-1]
    _, ilk_ters = np.unique(ters_gun, return_index=True)
    son_indeksler = np.sort(len(gun) - 1 - ilk_ters)
    gunluk_kapanis = c[son_indeksler]
    if gunluk_kapanis.size < 2:
        raise ValueError("günlük getiri için en az 2 gün gerekir")

    getiri = np.diff(gunluk_kapanis) / gunluk_kapanis[:-1]
    gun_sayisi = int(getiri.size)

    tablo: dict[str, float] = {}
    for aday in adaylar:
        tetiklenen = int((azami_maruziyet * getiri <= -aday).sum())
        tablo[f"{aday:.3f}"] = tetiklenen / gun_sayisi

    secilen = min(adaylar, key=lambda a: abs(tablo[f"{a:.3f}"] - hedef_tetikleme))
    tetiklenen = int(round(tablo[f"{secilen:.3f}"] * gun_sayisi))
    return GunlukZararOlcumu(
        limit=secilen,
        azami_maruziyet=azami_maruziyet,
        tetikleme_orani=tablo[f"{secilen:.3f}"],
        tetiklenen_gun=tetiklenen,
        gun_sayisi=gun_sayisi,
        dagilim=_dagilim(getiri, (0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 50.0)),
        aday_tablosu=tablo,
    )


__all__ = [
    "ATR_PENCERESI",
    "GUNLUK_ADAYLAR",
    "PERSENTILLER",
    "TERS_HAREKET_PERSENTILI",
    "VARSAYILAN_UFUK_BAR",
    "VOLATILITE_PERSENTILI",
    "GunlukZararOlcumu",
    "TersHareketOlcumu",
    "VolatiliteOlcumu",
    "gunluk_zarar_olc",
    "ters_hareket_olc",
    "volatilite_olc",
]
