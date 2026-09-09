"""RSI ortalamaya dönüş — mean reversion ailesi. (Faz 4, §9)

Hipotez: aşırı satım bölgesine düşen fiyat ortalamaya döner. Giriş RSI eşiğin **altına
inip yukarı geri geçtiğinde**, çıkış RSI üst eşiği aştığında.

**Neden "eşiğin altına inince" değil "altına inip geri çıkınca":** düşen bir bıçağı
yakalamak mean reversion değil, trendle ters işlem yapmaktır. RSI 30'un altına indiği anda
almak, RSI 5'e kadar inen bir düşüşte pozisyonu en tepeden açar. Geri geçişi beklemek
girişin **dönüşün başladığına dair** en az bir kanıtı olmasını sağlar.

**Kenar durumu — RSI NaN olabilir.** K-026/4 gereği hareketsiz pencerede RSI tanımsızdır.
`ctx.hazir` bunu yakalar; NaN ile yapılan karşılaştırmalar zaten False verirdi ama sessizce
False vermek ile "ısınma bitmemiş" demek farklı şeyler.
"""

from __future__ import annotations

from collections.abc import Sequence

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji

RSI = "rsi"


class RsiOrtalamaDonus(Strateji):
    """RSI aşırı satımdan geri dönünce gir, aşırı alıma ulaşınca çık.

    Parametreler:
        pencere: RSI penceresi (bar).
        alt: aşırı satım eşiği; giriş bu eşiğin altından yukarı geçişte.
        ust: aşırı alım eşiği; çıkış bu eşiğe ulaşınca.
        maruziyet: giriş sinyalinin hedef maruziyeti [0,1].
    """

    ad = "rsi_donus"

    def __init__(
        self,
        pencere: int = 14,
        alt: float = 30.0,
        ust: float = 70.0,
        maruziyet: float = 0.2,
    ) -> None:
        super().__init__(pencere=pencere, alt=alt, ust=ust, maruziyet=maruziyet)

    def dogrula(self) -> None:
        pencere = self.parametreler["pencere"]
        alt, ust = float(self.parametreler["alt"]), float(self.parametreler["ust"])
        maruziyet = float(self.parametreler["maruziyet"])
        if not isinstance(pencere, int) or pencere < 2:
            raise ValueError(f"pencere en az 2 tamsayı olmalı: {pencere}")
        if not 0.0 < alt < ust < 100.0:
            # `alt >= ust` durumunda giriş koşulu sağlandığı anda çıkış da sağlanır ve
            # strateji her barda gir-çık yapar: yüzlerce işlem, hepsi yalnızca maliyet.
            raise ValueError(f"0 < alt < ust < 100 olmalı: alt={alt}, ust={ust}")
        if not 0.0 < maruziyet <= 1.0:
            raise ValueError(f"maruziyet (0,1] aralığında olmalı: {maruziyet}")

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (OzellikTanimi(RSI, "rsi", {"pencere": self.parametreler["pencere"]}),)

    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        if not (ctx.hazir(RSI) and ctx.hazir(RSI, geri=1)):
            return None

        simdi = ctx.ozellik(RSI)
        onceki = ctx.ozellik(RSI, 1)
        alt = float(self.parametreler["alt"])
        ust = float(self.parametreler["ust"])

        if onceki < alt <= simdi:
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.BUY,
                target_exposure=float(self.parametreler["maruziyet"]),
                confidence=0.5,
                reason="RSI_CROSSED_UP_FROM_OVERSOLD",
                timestamp=ctx.zaman,
            )
        if simdi >= ust:
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.FLAT,
                target_exposure=0.0,
                confidence=0.5,
                reason="RSI_REACHED_OVERBOUGHT",
                timestamp=ctx.zaman,
            )
        return None
