"""Ortak test fixture'ları.

Buradaki bar üreteci **sentetik**tir ve öyle kalmalı: Spike 2 gerçek BTC/USDT verisinde
(3 yıl 1h + 1 yıl 1m) tek bir eksik/tekrar/tutarsız bar bulamadı. Yani K-006'nın kalite
kod yolları gerçek veriyle hiç tetiklenmiyor — sentetik bozuk veri olmadan test edilemezler.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.semalar import BAR_SUTUNLARI, KaliteDurumu


def bar_uret(
    n: int = 500,
    timeframe: str = "1h",
    baslangic_ms: int = 1_700_000_000_000,
    tohum: int = 42,
    kalite: str = KaliteDurumu.OK,
) -> pd.DataFrame:
    """Deterministik sentetik bar serisi.

    Fiyat rastgele yürüyüş; ama `tohum` sabit olduğu için aynı çağrı her zaman aynı
    barları verir — determinizm testlerinin ön koşulu.
    """
    adim = timeframe_ms(timeframe)
    rng = np.random.default_rng(tohum)

    close = 30_000.0 + np.cumsum(rng.normal(0, 25, n))
    acilis = np.concatenate([[close[0]], close[:-1]])
    sapma = np.abs(rng.normal(0, 15, n))
    high = np.maximum(acilis, close) + sapma
    low = np.minimum(acilis, close) - sapma
    hacim = np.abs(rng.normal(50, 12, n))

    df = pd.DataFrame(
        {
            "open_time": baslangic_ms + np.arange(n, dtype="int64") * adim,
            "open": acilis,
            "high": high,
            "low": low,
            "close": close,
            "volume": hacim,
            "quote_volume": hacim * close,
            "trades": rng.integers(100, 5000, n),
            "quality_status": kalite,
        }
    )
    return df.loc[:, list(BAR_SUTUNLARI)]


@pytest.fixture
def barlar() -> pd.DataFrame:
    """500 barlık temiz 1h serisi."""
    return bar_uret()


@pytest.fixture
def depo_kok(tmp_path):
    """Teste özel boş depo kökü."""
    return tmp_path / "depo"
