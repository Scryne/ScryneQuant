"""Tek sembollü değerlendirmede stres, **seçilen** parametrelerle ölçülür. (K-117)

`research/degerlendirme.degerlendir` stres testini `sinif()` ile — varsayılan parametrelerle —
koşuyordu; kapı, promotion'a aday olan stratejiyi değil başka bir parametre setini ölçüyordu.
Evren yolu (`evren_degerlendirme`) seçileni koşuyordu. Bu test iki yolu aynı kurala bağlar.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.research import degerlendirme


def _metrik(**ek):
    taban = dict(sharpe=1.0, toplam_getiri=0.1, islem_sayisi=40, max_drawdown=0.05,
                 yillik_anlamli=True)
    return SimpleNamespace(**(taban | ek))


def _kur(monkeypatch, secilen):
    gorulen: list[dict] = []
    pencereler: list = []

    class _Tarama:
        def sec(self, _secim):
            if secilen is None:
                return None
            return SimpleNamespace(sozluk_parametreler=secilen, metrikler=_metrik())

        def ust_yuzde_plato(self):
            return 1.0

    monkeypatch.setattr(degerlendirme, "tara", lambda *a, **k: _Tarama())
    monkeypatch.setattr(
        degerlendirme, "kosu",
        lambda *a, **k: SimpleNamespace(metrikler=_metrik(), ozkaynak=np.ones(20_000)),
    )
    monkeypatch.setattr(
        degerlendirme.walkforward, "calistir",
        lambda *a, **k: SimpleNamespace(
            basarili_katmanlar=[], bilesik_metrikler=_metrik(),
            parametre_kararliligi=lambda: {"katman": 0, "parametreler": {}},
        ),
    )

    def stres(strateji, *a, **k):
        gorulen.append(dict(strateji.parametreler))
        pencereler.append(a[4])
        return SimpleNamespace(bozulma=lambda: 0.0, sharpe_orani=lambda: 1.0)

    monkeypatch.setattr(degerlendirme.analiz, "stres", stres)
    return gorulen, pencereler


def _calistir():
    n = 40_000
    diziler = {"open_time": np.arange(n, dtype=np.int64) * 3_600_000}
    return degerlendirme.degerlendir(
        MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0), "BTCUSDT", "1h", diziler,
        stratejiler=["sma_kesisim"],
    )


def test_stres_secilen_parametrelerle_kosar(monkeypatch):
    secilen = {"hizli": 7, "yavas": 90, "maruziyet": 0.2}
    gorulen, pencereler = _kur(monkeypatch, secilen)
    sonuc = _calistir()
    assert gorulen == [secilen]  # varsayılan (20/50) değil
    o = sonuc["stratejiler"]["sma_kesisim"]["olcumler"]
    assert o["stres_bozulma"] == 0.0 and o["stres_sharpe_orani"] == 1.0
    # K-119: stres OOS penceresinde koşar (tam dönemde değil).
    assert pencereler[0].ad == "out_of_sample"


def test_secilen_yoksa_stres_olculmez_ve_kapi_gecmez(monkeypatch):
    gorulen, _ = _kur(monkeypatch, None)
    sonuc = _calistir()
    assert gorulen == []
    s = sonuc["stratejiler"]["sma_kesisim"]
    assert "stres_bozulma" not in s["olcumler"]
    assert "stres_dayanikliligi" in s["kapilar"]["kalan_kapilar"]
