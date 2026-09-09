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
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji


def bar_uret(
    n: int = 500,
    timeframe: str = "1h",
    # 2023-11-14 22:00 UTC — 1h ızgarasına hizalı. Yuvarlak görünen 1_700_000_000_000
    # değil, çünkü o 22:13:20'ye denk gelir ve K-005'in "bar timestamp'i epoch'a hizalı
    # açılış zamanıdır" kuralını ihlal eder; doğrulama katmanı onu haklı olarak reddediyor.
    baslangic_ms: int = 1_699_999_200_000,
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


class PlanliStrateji(Strateji):
    """Takvimden sinyal üreten test stratejisi.

    Referans senaryolarında strateji mantığı **ölçülen şey değil** — ölçülen, motorun fill
    ve muhasebe aritmetiği. Sinyalleri sabit bir takvimden vermek o ikisini ayırıyor:
    referans fixture'ı bir stratejinin davranışını yeniden üretmek zorunda kalmıyor.

    Takvim bar indeksine bakar; bu geleceğe bakmak değil, takvime bakmaktır — indeks
    `ctx.uzunluk - 1`den, yani zaten görülmüş bar sayısından türetiliyor.
    """

    ad = "planli"

    def __init__(self, takvim: dict[int, tuple[str, float]]) -> None:
        self._takvim = dict(takvim)
        super().__init__(takvim=tuple(sorted(takvim.items())))

    def ozellikler(self):
        return ()

    def on_bar(self, ctx):
        girdi = self._takvim.get(ctx.uzunluk - 1)
        if girdi is None:
            return None
        yon, hedef = girdi
        return Sinyal(
            symbol=ctx.sembol,
            side=Yon(yon),
            target_exposure=hedef,
            confidence=1.0,
            reason="PLANLI_TAKVIM",
            timestamp=ctx.zaman,
        )
