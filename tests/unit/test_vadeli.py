"""Kaldıraçlı vadeli demo (K-140): giriş, keskin stop, likidasyon, funding."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scryne_quant.aktif import vadeli as v
from scryne_quant.aktif.defter import Defter

GUN, SAAT = v.GUN_MS, v.SAAT_MS
T0 = 1_790_035_200_000  # 2026-09-22 00:00 UTC


class Sahte:
    """Günlük seri: 80 gün yatay (100), son gün sert yükseliş (110) → Bollinger long sinyali."""

    def __init__(self) -> None:
        gunler = T0 - GUN * np.arange(80, 0, -1)
        c = np.full(80, 100.0) + np.sin(np.arange(80)) * 0.5
        c[-1] = 110.0
        self.gunluk = pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999, "close": c},
                                   index=pd.Index(gunler, name="open_time"))
        self.saatlik = pd.DataFrame(columns=["open", "high", "low", "close"])
        self.mark = 110.0
        self.fund: list[tuple[int, float, float]] = []

    def klines(self, sembol, aralik, adet):
        return self.gunluk if aralik == "1d" else self.saatlik

    def fiyat(self, sembol):
        return self.mark

    def funding(self, sembol, bas_ms):
        return [f for f in self.fund if f[0] >= bas_ms]


def saat(t: int, o: float, h: float, lo: float, c: float) -> pd.DataFrame:
    return pd.DataFrame({"open": [o], "high": [h], "low": [lo], "close": [c]},
                        index=pd.Index([t], name="open_time"))


def kur(tmp_path: Path, L: float = 3.0, stop: bool = True):
    ayar = v.VadeliAyari(strat="S3", kaldirac=L, sert_stop=stop, semboller=("XUSDT",))
    return Sahte(), v.VadeliHesap(tmp_path, 1000.0, ayar.semboller), Defter(tmp_path), ayar


def test_bollinger_girisi_ve_notional(tmp_path: Path) -> None:
    veri, h, d, a = kur(tmp_path)
    r = v.vadeli_tur(veri, h, d, a, T0 + 60_000)
    dl = h.dilimler["XUSDT"]
    assert r["poz"] == {"XUSDT": 1} and dl.giris == 110.0
    assert dl.notional == pytest.approx(3000.0)
    assert r["ozkaynak"] == pytest.approx(1000 - 3000 * a.maliyet)
    d.kapat()


def test_keskin_stop_yuzde_iki_dolum(tmp_path: Path) -> None:
    veri, h, d, a = kur(tmp_path)
    v.vadeli_tur(veri, h, d, a, T0 + 60_000)
    veri.saatlik = saat(T0, 110.0, 110.5, 107.0, 107.5)  # %2 stop = 107,8 tetiklenir
    veri.mark = 107.5
    r = v.vadeli_tur(veri, h, d, a, T0 + SAAT + 60_000)
    assert "stop XUSDT" in r["olaylar"] and h.dilimler["XUSDT"].poz == 0
    beklenen = 1000 - 3000 * a.maliyet + 3000 * (107.8 / 110 - 1) - 3000 * a.maliyet
    assert h.dilimler["XUSDT"].ozk == pytest.approx(beklenen)
    d.kapat()


def test_likidasyon_dilimi_sifirlar(tmp_path: Path) -> None:
    veri, h, d, a = kur(tmp_path, L=20.0, stop=False)  # eşik 1/20 − %0,5 = %4,5
    v.vadeli_tur(veri, h, d, a, T0 + 60_000)
    veri.saatlik = saat(T0, 110.0, 110.2, 104.5, 105.0)  # %5 aleyhte
    r = v.vadeli_tur(veri, h, d, a, T0 + SAAT + 60_000)
    assert "LİKİDASYON XUSDT" in r["olaylar"]
    dl = h.dilimler["XUSDT"]
    assert dl.tasfiye and dl.ozk == 0.0 and r["ozkaynak"] == 0.0
    d.kapat()


def test_funding_long_oder(tmp_path: Path) -> None:
    veri, h, d, a = kur(tmp_path, stop=False)
    v.vadeli_tur(veri, h, d, a, T0 + 60_000)
    once = h.dilimler["XUSDT"].ozk
    veri.fund = [(T0 + 8 * SAAT, 0.001, 110.0)]
    v.vadeli_tur(veri, h, d, a, T0 + 9 * SAAT)
    assert h.dilimler["XUSDT"].ozk == pytest.approx(once - 3000 * 0.001)
    d.kapat()


def test_supertrend_bilinen_donus() -> None:
    c = np.r_[np.linspace(100, 200, 150), np.linspace(200, 100, 150)]
    b = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c})
    y = v.supertrend(b)
    assert set(y[20:].astype(int)) == {-1, 1}
    assert y[140] == 1 and y[-1] == -1
