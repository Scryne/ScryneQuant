"""Strateji kütüphanesi: Faz 4'ün beş ailesi. (Roadmap Faz 4, §9)

Amaç kâr bulmak değil — aynı veri ve aynı maliyet varsayımlarıyla karşılaştırılabilir
beş hipotez ailesi kurmak. Aileler bilerek **basit** ve az parametreli: Faz 4'ün asıl
ölçtüğü şey stratejilerin kendisi değil, laboratuvarın (walk-forward, OOS, Monte Carlo,
stres) bir stratejiye güvenilip güvenilemeyeceğini ayırt edebilmesi.

`KUTUPHANE` sözlüğü aileleri isimden çözer; CLI ve tarama motoru buraya bakar. Bir
strateji buraya kaydedilmeden deneye giremez — "her yerden import edilebilen" bir
laboratuvar, hangi sonucun hangi koddan geldiğini kaybettirir.
"""

from __future__ import annotations

from typing import Final

from scryne_quant.strategy.kutuphane.al_tut import AlTut
from scryne_quant.strategy.kutuphane.breakout import DonchianKirilim
from scryne_quant.strategy.kutuphane.cok_faktor import CokFaktor
from scryne_quant.strategy.kutuphane.ema_kesisim import EmaKesisim
from scryne_quant.strategy.kutuphane.momentum import Momentum
from scryne_quant.strategy.kutuphane.rsi_donus import RsiOrtalamaDonus
from scryne_quant.strategy.kutuphane.sma_kesisim import SmaKesisim
from scryne_quant.strategy.temel import Strateji

#: Ad → sınıf. Faz 4'ün beş ailesi; `sma_kesisim` ile `ema_kesisim` aynı ailenin
#: (trend takibi / kesişim) iki üyesi olduğu için beş aile altı sınıf eder.
KUTUPHANE: Final[dict[str, type[Strateji]]] = {
    SmaKesisim.ad: SmaKesisim,
    EmaKesisim.ad: EmaKesisim,
    RsiOrtalamaDonus.ad: RsiOrtalamaDonus,
    DonchianKirilim.ad: DonchianKirilim,
    Momentum.ad: Momentum,
    CokFaktor.ad: CokFaktor,
}

#: Kıyas ölçütü. `KUTUPHANE`de **değil**: beş aileden biri değil, hepsinin karşısındaki
#: çizgi. Karşılaştırma raporlarına ayrı bir satır olarak giriyor — bir stratejinin
#: "%15 kazandı" cümlesi, aynı dönemde varlığın ne yaptığı bilinmeden okunamaz.
KIYAS: Final[dict[str, type[Strateji]]] = {AlTut.ad: AlTut}

#: Aile → o ailenin stratejileri. Roadmap "5 aile de aynı veri ve aynı maliyet
#: varsayımlarıyla çalıştırılmış, sonuçlar yan yana" diyor; karşılaştırma bu gruplamayı
#: kullanıyor.
AILELER: Final[dict[str, tuple[str, ...]]] = {
    "kesisim": (SmaKesisim.ad, EmaKesisim.ad),
    "ortalama_donus": (RsiOrtalamaDonus.ad,),
    "kirilim": (DonchianKirilim.ad,),
    "momentum": (Momentum.ad,),
    "cok_faktor": (CokFaktor.ad,),
}


class BilinmeyenStrateji(KeyError):
    """Kütüphanede kayıtlı olmayan strateji adı."""


def coz(ad: str) -> type[Strateji]:
    """Ada karşılık gelen strateji sınıfı. Kıyas ölçütü de çözülebilir."""
    hepsi = {**KUTUPHANE, **KIYAS}
    try:
        return hepsi[ad]
    except KeyError:
        raise BilinmeyenStrateji(
            f"{ad!r} kayıtlı değil; kütüphane: {', '.join(sorted(hepsi))}"
        ) from None


def aile(ad: str) -> str:
    """Bir stratejinin ait olduğu aile. Kıyas ölçütü `kiyas` ailesindedir."""
    if ad in KIYAS:
        return "kiyas"
    for aile_adi, uyeler in AILELER.items():
        if ad in uyeler:
            return aile_adi
    raise BilinmeyenStrateji(f"{ad!r} hiçbir aileye kayıtlı değil")


__all__ = [
    "AILELER",
    "KIYAS",
    "KUTUPHANE",
    "AlTut",
    "BilinmeyenStrateji",
    "CokFaktor",
    "DonchianKirilim",
    "EmaKesisim",
    "Momentum",
    "RsiOrtalamaDonus",
    "SmaKesisim",
    "aile",
    "coz",
]
