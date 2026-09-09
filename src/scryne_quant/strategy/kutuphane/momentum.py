"""Momentum — yakın dönem hareketin devam edeceği hipotezi. (Faz 4, §9)

Giriş: N barlık değişim oranı (ROC) pozitif eşiği aştığında. Çıkış: ROC negatif eşiğin
altına indiğinde. Aradaki bant bilerek geniş: tek bir eşik kullanmak, ROC sıfır civarında
salınırken her barda gir-çık üretir ve strateji yalnızca komisyon öder.

**Birim tuzağı:** `roc` indikatörü **yüzde** döndürür (TA-Lib `ROC` konvansiyonu, K-026).
`giris_esigi=2.0` "%2" demektir. Kesir sanılıp `0.02` yazılırsa strateji neredeyse her
barda tetiklenir — ve bu sessiz bir hatadır, sonuç yalnızca "çok işlem yapmış" görünür.
Bu yüzden doğrulama eşikleri makul bir yüzde aralığına sınırlıyor.
"""

from __future__ import annotations

from collections.abc import Sequence

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji

ROC = "roc"

#: Eşiklerin kabul edildiği yüzde aralığı. Üst sınır BTC'nin ölçülen hareketine göre
#: cömert; asıl işi alt sınır görüyor — kesir/yüzde karışıklığını yakalamak.
ESIK_TAVANI = 500.0


class Momentum(Strateji):
    """ROC pozitif eşiği aşınca gir, negatif eşiğin altına inince çık.

    Parametreler:
        pencere: ROC penceresi (bar).
        giris_esigi: giriş için gereken yüzde değişim (> 0).
        cikis_esigi: çıkış için gereken yüzde değişim (< 0).
        maruziyet: giriş sinyalinin hedef maruziyeti [0,1].
    """

    ad = "momentum"

    def __init__(
        self,
        pencere: int = 24,
        giris_esigi: float = 2.0,
        cikis_esigi: float = -2.0,
        maruziyet: float = 0.2,
    ) -> None:
        super().__init__(
            pencere=pencere,
            giris_esigi=giris_esigi,
            cikis_esigi=cikis_esigi,
            maruziyet=maruziyet,
        )

    def dogrula(self) -> None:
        pencere = self.parametreler["pencere"]
        giris = float(self.parametreler["giris_esigi"])
        cikis = float(self.parametreler["cikis_esigi"])
        maruziyet = float(self.parametreler["maruziyet"])
        if not isinstance(pencere, int) or pencere < 1:
            raise ValueError(f"pencere en az 1 tamsayı olmalı: {pencere}")
        if not 0.0 < giris <= ESIK_TAVANI:
            raise ValueError(f"giris_esigi (0, {ESIK_TAVANI}] yüzde aralığında olmalı: {giris}")
        if not -ESIK_TAVANI <= cikis < 0.0:
            raise ValueError(f"cikis_esigi [-{ESIK_TAVANI}, 0) yüzde aralığında olmalı: {cikis}")
        if not 0.0 < maruziyet <= 1.0:
            raise ValueError(f"maruziyet (0,1] aralığında olmalı: {maruziyet}")

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (OzellikTanimi(ROC, "roc", {"pencere": self.parametreler["pencere"]}),)

    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        if not ctx.hazir(ROC):
            return None

        deger = ctx.ozellik(ROC)
        if deger > float(self.parametreler["giris_esigi"]):
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.BUY,
                target_exposure=float(self.parametreler["maruziyet"]),
                confidence=0.5,
                reason="MOMENTUM_ABOVE_ENTRY_THRESHOLD",
                timestamp=ctx.zaman,
            )
        if deger < float(self.parametreler["cikis_esigi"]):
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.FLAT,
                target_exposure=0.0,
                confidence=0.5,
                reason="MOMENTUM_BELOW_EXIT_THRESHOLD",
                timestamp=ctx.zaman,
            )
        return None
