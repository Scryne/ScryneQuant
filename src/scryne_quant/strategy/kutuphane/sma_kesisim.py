"""SMA kesişimi — sözleşmenin **referans** uygulaması. (Faz 2)

Bu stratejinin amacı para kazanmak değil; `Strateji` sözleşmesinin gerçekten
yazılabildiğini göstermek ve Faz 2'nin iki testine (look-ahead, izolasyon) somut bir özne
vermek. Faz 4'ün strateji ailelerinden biri buradan türeyecek, ama beklenti şudur:
maliyetlerden sonra bu strateji muhtemelen anlamlı bir getiri üretmez — ve bu, sistemin
çalıştığının kanıtıdır (Roadmap Faz 4 notu).

**Kural:** yalnızca `t` ve öncesine bakılır. Kesişim kontrolü `geri=0` ile `geri=1`
arasında yapılır; ikisi de geçmiştir. Sinyalin doldurulacağı fiyat `t+1`in açılışıdır
(K-004) ama bu strateji o fiyatı ne bilir ne sorar — bilseydi look-ahead olurdu.
"""

from __future__ import annotations

from collections.abc import Sequence

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji

HIZLI = "sma_hizli"
YAVAS = "sma_yavas"


class SmaKesisim(Strateji):
    """Hızlı SMA yavaşı yukarı keserse gir, aşağı keserse çık.

    Parametreler:
        hizli: hızlı SMA penceresi (bar).
        yavas: yavaş SMA penceresi (bar); `hizli`dan büyük olmalı.
        maruziyet: giriş sinyalinin hedef maruziyeti [0,1].
    """

    ad = "sma_kesisim"

    def __init__(self, hizli: int = 20, yavas: int = 50, maruziyet: float = 0.2) -> None:
        super().__init__(hizli=hizli, yavas=yavas, maruziyet=maruziyet)

    def dogrula(self) -> None:
        hizli = self.parametreler["hizli"]
        yavas = self.parametreler["yavas"]
        maruziyet = self.parametreler["maruziyet"]
        if not isinstance(hizli, int) or not isinstance(yavas, int):
            raise ValueError("hizli ve yavas tamsayı olmalı")
        if hizli < 2:
            raise ValueError(f"hizli en az 2 olmalı: {hizli}")
        if yavas <= hizli:
            # Eşit pencerelerde iki seri özdeş olur ve kesişim hiç gerçekleşmez; strateji
            # sessizce hiçbir sinyal üretmez. Sessiz "hiç işlem yok", parametre hatasının
            # en zor fark edilen biçimi.
            raise ValueError(f"yavas > hizli olmalı: {yavas} <= {hizli}")
        if not 0.0 < float(maruziyet) <= 1.0:
            raise ValueError(f"maruziyet (0,1] aralığında olmalı: {maruziyet}")

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (
            OzellikTanimi(HIZLI, "sma", {"pencere": self.parametreler["hizli"]}),
            OzellikTanimi(YAVAS, "sma", {"pencere": self.parametreler["yavas"]}),
        )

    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        # Kesişim iki bar gerektirir: `t` ve `t-1`. İkisinde de her iki SMA hesaplanmış
        # olmalı — ısınma bölgesindeki NaN karşılaştırması sessizce False verir ve
        # ilk gerçek kesişim kaçırılırdı.
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
                reason="SMA_FAST_CROSSED_ABOVE_SLOW",
                timestamp=ctx.zaman,
            )
        if onceki >= 0.0 > simdi:
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.FLAT,
                target_exposure=0.0,
                confidence=0.5,
                reason="SMA_FAST_CROSSED_BELOW_SLOW",
                timestamp=ctx.zaman,
            )
        return None
