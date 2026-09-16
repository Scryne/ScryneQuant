"""Evren görünümünde özellikler yalnızca **var olan** barlardan hesaplanır. (Faz 12)

Ölçülen hata: ızgara doldurma barları (`listelenmedi`) NaN fiyat taşıyor ve Wilder
yumuşatması (ATR) bir NaN gördükten sonra sonsuza kadar NaN üretiyor. Pencere başladıktan
sonra listelenen her sembolün ATR'si bu yüzden hiç hesaplanmıyordu; `evren_esit_agirlik`
ve her ATR kullanan portföy stratejisi o sembolleri hiçbir zaman aday yapmıyordu.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.features.motor import OzellikHatasi, OzellikTanimi, hesapla
from scryne_quant.strategy.evren import LISTELENMEDI
from scryne_quant.strategy.kosu import ozellikleri_hesapla
from tests.conftest import bar_uret

TANIMLAR = (
    OzellikTanimi("atr", "atr", {"pencere": 14}),
    OzellikTanimi("roc", "roc", {"pencere": 24}),
    OzellikTanimi("kote_hacim", "kote_hacim_sma", {"pencere": 20}),
)


def _bosluklu(diziler: dict[str, np.ndarray], maske: np.ndarray) -> dict[str, np.ndarray]:
    """`maske` True olan barları ızgara doldurma barına çevirir (`data.izgara.hizala` gibi)."""
    out = {ad: np.array(d, copy=True) for ad, d in diziler.items()}
    for ad, d in out.items():
        if ad in ("open_time",):
            continue
        if ad == "quality_status":
            d = d.astype(object)
            d[maske] = LISTELENMEDI
            out[ad] = d
        elif ad == "trades":
            d[maske] = 0
        else:
            d[maske] = np.nan
    return out


def test_bosluk_yoksa_hesapla_ile_bit_duzeyinde_ayni() -> None:
    diziler = bar_dizileri(bar_uret(n=200, tohum=3))
    beklenen = hesapla(diziler, TANIMLAR)
    gelen = ozellikleri_hesapla(diziler, TANIMLAR)
    for ad in beklenen:
        assert beklenen[ad].tobytes() == gelen[ad].tobytes()


def test_gec_listelenen_sembolun_atr_si_hesaplanir() -> None:
    """Regresyon: eski yol 0 geçerli ATR üretiyordu."""
    diziler = bar_dizileri(bar_uret(n=300, tohum=5))
    maske = np.zeros(300, dtype=bool)
    maske[:80] = True
    bosluklu = _bosluklu(diziler, maske)

    eski = hesapla(bosluklu, TANIMLAR)
    assert np.isfinite(eski["atr"]).sum() == 0  # hatanın kendisi — ölçülen durum

    yeni = ozellikleri_hesapla(bosluklu, TANIMLAR)
    tekil = hesapla({ad: np.asarray(d)[~maske] for ad, d in diziler.items()}, TANIMLAR)
    for ad in tekil:
        assert np.isnan(yeni[ad][maske]).all()
        # Var olan barlarda, sembolün tek başına (tek sembollü yol) ürettiğiyle aynı.
        assert yeni[ad][~maske].tobytes() == tekil[ad].tobytes()


def test_ara_bosluk_atr_yi_kalici_olarak_oldurmez() -> None:
    diziler = bar_dizileri(bar_uret(n=300, tohum=11))
    maske = np.zeros(300, dtype=bool)
    maske[150:160] = True
    yeni = ozellikleri_hesapla(_bosluklu(diziler, maske), TANIMLAR)
    assert np.isfinite(yeni["atr"][160:]).all()


def test_pencereye_yetmeyen_kisa_seri_nan_kalir_hata_vermez() -> None:
    diziler = bar_dizileri(bar_uret(n=300, tohum=2))
    maske = np.ones(300, dtype=bool)
    maske[-10:] = False  # yalnızca 10 bar var; roc(24) ve atr(14) ısınamaz
    yeni = ozellikleri_hesapla(_bosluklu(diziler, maske), TANIMLAR)
    assert np.isnan(yeni["atr"]).all()
    assert np.isnan(yeni["roc"]).all()
    assert not yeni["atr"].flags.writeable


def test_ayni_ad_iki_kez_hata() -> None:
    diziler = bar_dizileri(bar_uret(n=100, tohum=1))
    maske = np.zeros(100, dtype=bool)
    maske[:5] = True
    with pytest.raises(OzellikHatasi):
        ozellikleri_hesapla(
            _bosluklu(diziler, maske),
            (OzellikTanimi("x", "atr", {"pencere": 14}), OzellikTanimi("x", "roc", {"pencere": 5})),
        )
