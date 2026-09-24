"""Çekirdek portföy (K-141): gelecek görmezlik, filtre, tavan, bant, canlı tur."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scryne_quant.aktif import cekirdek as c
from scryne_quant.aktif.araci import KriptoPaper
from scryne_quant.aktif.defter import Defter

GUN = c.GUN_MS
T0 = 1_790_035_200_000  # 2026-09-22 00:00 UTC


def panel(n: int = 400, egim: float = 0.002, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    r = rng.normal(egim, 0.03, size=(n, 2))
    return pd.DataFrame(100 * np.exp(np.cumsum(r, axis=0)), index=idx,
                        columns=["BTCUSDT", "ETHUSDT"])


def test_gelecek_bozulunca_gecmis_agirlik_degismez() -> None:
    p = panel()
    a = c.hedef_agirliklar(p, c.CekirdekAyari())
    bozuk = p.copy()
    bozuk.iloc[300:] *= 5.0
    b = c.hedef_agirliklar(bozuk, c.CekirdekAyari())
    pd.testing.assert_frame_equal(a.iloc[:300], b.iloc[:300])


def test_isinma_ve_dusus_trendinde_agirlik_sifir() -> None:
    w = c.hedef_agirliklar(panel(egim=-0.01), c.CekirdekAyari())
    assert (w.iloc[: c.ISINMA - 1] == 0).all().all()
    assert (w.iloc[-50:] == 0).all().all()


def test_yukselis_trendinde_pozitif_ve_tavan_altinda() -> None:
    ayar = c.CekirdekAyari(hedef_vol=5.0)  # tavanı zorla
    w = c.hedef_agirliklar(panel(egim=0.01), ayar)
    assert (w.iloc[-1] > 0).all()
    assert (w.sum(axis=1) <= ayar.tavan + 1e-12).all()


def test_bant() -> None:
    assert c.dengele({"A": 0.30}, {"A": 0.33}, 0.05) == {"A": 0.30}
    assert c.dengele({"A": 0.30}, {"A": 0.40}, 0.05) == {"A": 0.40}
    assert c.dengele({"A": 0.03}, {"A": 0.0}, 0.05) == {"A": 0.0}


class SahteVeri:
    """Binance adaptörü yerine: günlük barlar + anlık fiyat."""

    def __init__(self, p: pd.DataFrame) -> None:
        self.p = p

    def sunucu_zamani_ms(self) -> int:
        return T0 + 10 * 60_000

    def klines(self, sembol, timeframe, bas, bit):
        s = self.p[sembol]
        t = (T0 - GUN * np.arange(len(s), 0, -1)).astype("int64")
        return {"open_time": t, "open": s.to_numpy(), "high": s.to_numpy(),
                "low": s.to_numpy(), "close": s.to_numpy()}

    def son_fiyat(self, sembol):
        return float(self.p[sembol].iloc[-1])


def test_canli_tur_hedefe_gider_ve_ikinci_tur_islem_yapmaz(tmp_path: Path) -> None:
    p = panel(egim=0.01)
    araci = KriptoPaper(tmp_path, sermaye=10_000, ucret_bps=10, kayma_bps=5,
                        veri=SahteVeri(p))
    d = Defter(tmp_path)
    ayar = c.CekirdekAyari()
    r = c.cekirdek_tur(araci, d, ayar, T0 + 10 * 60_000)
    beklenen = c.hedef_agirliklar(p, ayar).iloc[-1]
    assert len(r["emirler"]) == 2
    for s in ayar.semboller:
        w = araci.pozisyonlar()[s] * p[s].iloc[-1] / araci.ozkaynak()
        assert w == pytest.approx(beklenen[s], abs=0.01)
    r2 = c.cekirdek_tur(araci, d, ayar, T0 + 11 * 60_000)
    assert r2["emirler"] == []
    d.kapat()
