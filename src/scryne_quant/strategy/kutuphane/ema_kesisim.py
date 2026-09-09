"""EMA kesişimi — kesişim ailesinin ikinci üyesi. (Faz 4)

SMA sürümünden tek farkı ortalama tipi, ve bu fark bilerek korunuyor: EMA son barlara
daha çok ağırlık verdiği için sinyal daha erken gelir ama gürültüye daha açıktır. Aynı
ailede iki üye tutmanın amacı, Faz 4'ün "parametre kararlılığı" ölçümünün **ortalama tipi
seçiminin** de bir parametre olduğunu göstermesi.
"""

from __future__ import annotations

from collections.abc import Sequence

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji

HIZLI = "ema_hizli"
YAVAS = "ema_yavas"


class EmaKesisim(Strateji):
    """Hızlı EMA yavaşı yukarı keserse gir, aşağı keserse çık."""

    ad = "ema_kesisim"

    def __init__(self, hizli: int = 20, yavas: int = 50, maruziyet: float = 0.2) -> None:
        super().__init__(hizli=hizli, yavas=yavas, maruziyet=maruziyet)

    def dogrula(self) -> None:
        hizli, yavas = self.parametreler["hizli"], self.parametreler["yavas"]
        maruziyet = float(self.parametreler["maruziyet"])
        if not isinstance(hizli, int) or not isinstance(yavas, int):
            raise ValueError("hizli ve yavas tamsayı olmalı")
        if hizli < 2:
            raise ValueError(f"hizli en az 2 olmalı: {hizli}")
        if yavas <= hizli:
            raise ValueError(f"yavas > hizli olmalı: {yavas} <= {hizli}")
        if not 0.0 < maruziyet <= 1.0:
            raise ValueError(f"maruziyet (0,1] aralığında olmalı: {maruziyet}")

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (
            OzellikTanimi(HIZLI, "ema", {"pencere": self.parametreler["hizli"]}),
            OzellikTanimi(YAVAS, "ema", {"pencere": self.parametreler["yavas"]}),
        )

    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        if not (ctx.hazir(HIZLI, YAVAS) and ctx.hazir(HIZLI, YAVAS, geri=1)):
            return None

        simdi = ctx.ozellik(HIZLI) - ctx.ozellik(YAVAS)
        onceki = ctx.ozellik(HIZLI, 1) - ctx.ozellik(YAVAS, 1)

        if onceki <= 0.0 < simdi:
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.BUY,
                target_exposure=float(self.parametreler["maruziyet"]),
                confidence=0.5,
                reason="EMA_FAST_CROSSED_ABOVE_SLOW",
                timestamp=ctx.zaman,
            )
        if onceki >= 0.0 > simdi:
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.FLAT,
                target_exposure=0.0,
                confidence=0.5,
                reason="EMA_FAST_CROSSED_BELOW_SLOW",
                timestamp=ctx.zaman,
            )
        return None
