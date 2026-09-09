"""Stratejiyi bar bar dolaştıran ince sürücü. (Faz 2)

Bu bir backtest motoru **değil**: fill yok, maliyet yok, portföy yok — onlar Faz 3'ün
işi. Burada olan tek şey, sözleşmenin uçtan uca çalıştığını gösteren döngü:

    özellikleri hesapla → her bar için ctx kes → on_bar çağır → sinyalleri topla

Faz 2'nin look-ahead testi bu döngü üzerinden ölçüyor. Sözleşmeye bakan testler
(erişimcinin hata fırlatması) ayrı; bu testin ölçtüğü **sonuç**: geleceği bozunca
sinyaller değişiyor mu.

Faz 3'ün event loop'u bu modülü değil, aynı parçaları kullanacak — pozisyonu her barda
kendi portföyünden vererek. `PiyasaGorunumu.baglam(i, pozisyon)` o yüzden ayrı duruyor.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from scryne_quant.features.motor import hesapla
from scryne_quant.strategy.baglam import PiyasaGorunumu
from scryne_quant.strategy.sinyal import Sinyal
from scryne_quant.strategy.temel import Strateji


def gorunum_kur(
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    strateji: Strateji,
) -> PiyasaGorunumu:
    """Stratejinin bildirdiği özellikleri hesaplayıp piyasa görünümünü kurar."""
    return PiyasaGorunumu(
        sembol=sembol,
        timeframe=timeframe,
        barlar=dict(bar_dizileri),
        ozellikler=hesapla(bar_dizileri, strateji.ozellikler()),
    )


def sinyalleri_uret(strateji: Strateji, gorunum: PiyasaGorunumu) -> list[Sinyal]:
    """Stratejiyi tüm seri üzerinde dolaştırır, ürettiği sinyalleri sırayla döndürür.

    `hazirla()` başta çağrılır: aynı strateji örneğiyle yapılan ikinci koşunun
    birincisinden etkilenmemesi determinizmin (K-009) ön koşulu.
    """
    strateji.hazirla()
    return [
        sinyal
        for ctx in gorunum.akis(parametreler=strateji.parametreler)
        if (sinyal := strateji.on_bar(ctx)) is not None
    ]
