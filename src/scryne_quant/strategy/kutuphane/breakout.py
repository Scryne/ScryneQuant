"""Donchian kırılımı — kırılım (breakout) ailesi. (Faz 4, §8 "High/low breaks")

Hipotez: fiyat son N barın zirvesini kırdıysa hareket devam eder. Çıkış, son M barın
dibinin kırılmasıyla (klasik "turtle" yapısı).

**Kanal bir bar geriden okunur — bu bir ayrıntı değil, stratejinin çalışıp çalışmamasıdır.**
`en_yuksek(high, N)` penceresi `t` barının kendi zirvesini de içerir. `close[t] > kanal[t]`
karşılaştırması bu yüzden neredeyse hiç doğru olmaz: `kanal[t] ≥ high[t] ≥ close[t]`.
Doğru soru "kapanış, **önceki** N barın zirvesini aştı mı" ve cevabı `ctx.ozellik(UST, 1)`.
Kaydırmanın indikatöre değil buraya konmasının sebebi K-026: indikatör TA-Lib `MAX` ile
birebir kalmalı, yoksa referansla karşılaştırılamaz.
"""

from __future__ import annotations

from collections.abc import Sequence

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji

UST = "kanal_ust"
ALT = "kanal_alt"


class DonchianKirilim(Strateji):
    """Giriş kanalının üstü kırılınca gir, çıkış kanalının altı kırılınca çık.

    Parametreler:
        giris: giriş kanalı penceresi (bar).
        cikis: çıkış kanalı penceresi (bar); girişten kısa olması olağandır —
            kırılımdan çıkmak girmekten hızlı olmalı.
        maruziyet: giriş sinyalinin hedef maruziyeti [0,1].
    """

    ad = "donchian"

    def __init__(self, giris: int = 55, cikis: int = 20, maruziyet: float = 0.2) -> None:
        super().__init__(giris=giris, cikis=cikis, maruziyet=maruziyet)

    def dogrula(self) -> None:
        giris, cikis = self.parametreler["giris"], self.parametreler["cikis"]
        maruziyet = float(self.parametreler["maruziyet"])
        if not isinstance(giris, int) or not isinstance(cikis, int):
            raise ValueError("giris ve cikis tamsayı olmalı")
        if giris < 2 or cikis < 2:
            raise ValueError(f"kanal pencereleri en az 2 olmalı: giris={giris}, cikis={cikis}")
        if not 0.0 < maruziyet <= 1.0:
            raise ValueError(f"maruziyet (0,1] aralığında olmalı: {maruziyet}")

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (
            OzellikTanimi(UST, "en_yuksek", {"pencere": self.parametreler["giris"]}),
            OzellikTanimi(ALT, "en_dusuk", {"pencere": self.parametreler["cikis"]}),
        )

    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        # `geri=1`: kanal önceki barda biten pencereden okunur (bkz. modül docstring'i).
        if not ctx.hazir(UST, ALT, geri=1):
            return None

        kapanis = ctx.bar("close")
        if kapanis > ctx.ozellik(UST, 1):
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.BUY,
                target_exposure=float(self.parametreler["maruziyet"]),
                confidence=0.5,
                reason="CLOSE_BROKE_UPPER_CHANNEL",
                timestamp=ctx.zaman,
            )
        if kapanis < ctx.ozellik(ALT, 1):
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.FLAT,
                target_exposure=0.0,
                confidence=0.5,
                reason="CLOSE_BROKE_LOWER_CHANNEL",
                timestamp=ctx.zaman,
            )
        return None
