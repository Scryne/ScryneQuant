"""Sabit oranlı yatırım: hesabın sabit kesri varlıkta, bant dışında yeniden dengele. (K-132)

**Bu bir alfa ya da zamanlama stratejisi değil.** K-132 hedefi "sabit risk bütçeli sistematik
yatırım"dır: piyasa yönü tahmin edilmez; risk, tutulan kesirle (maruziyet) ve kodda sabit
kayıp tavanlarıyla sınırlanır. Getiri tamamen varlığın gelecekteki getirisine bağlıdır;
strateji onu artırmaz, yalnız disiplinle uygular. Bu yüzden promotion ölçütü plasebo değil
operasyoneldir (K-132).

## Kural (üç satır)

- Hedef: portföyün `hedef` kesri varlıkta (varsayılan 0,5), gerisi nakit (USDT).
- Mevcut maruziyet `[hedef − bant, hedef + bant]` dışına çıkarsa hedefe dön: altındaysa `BUY`,
  üstündeyse `SELL` (ikisi de mutlak hedef `hedef`). İçindeyse hiçbir şey yapma.
- Pozisyon yoksa (ilk bar, ya da risk motoru bir önceki alımı reddettiyse) `BUY`.

Durum stratejide tutulmaz, `ctx.pozisyon`dan okunur (K-031: sinyal kabul edilmiş varsayılamaz).
İndikatör yok, ısınma yok, geleceğe bakacak bir şey yok.
"""

from __future__ import annotations

from collections.abc import Sequence

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji


class SabitOran(Strateji):
    """Portföyün `hedef` kesrini varlıkta tutar; `bant` dışına çıkınca yeniden dengeler.

    Parametreler:
        hedef: hedef maruziyet (0, 1].
        bant: yeniden dengeleme bandının yarı genişliği; 0 < bant < hedef, hedef + bant ≤ 1.
    """

    ad = "sabit_oran"

    def __init__(self, hedef: float = 0.5, bant: float = 0.05) -> None:
        super().__init__(hedef=hedef, bant=bant)

    def dogrula(self) -> None:
        hedef = float(self.parametreler["hedef"])
        bant = float(self.parametreler["bant"])
        if not 0.0 < hedef <= 1.0:
            raise ValueError(f"hedef (0,1] aralığında olmalı: {hedef}")
        if not 0.0 < bant < hedef or hedef + bant > 1.0 + 1e-12:
            raise ValueError(f"bant 0 < bant < hedef ve hedef + bant ≤ 1 olmalı: {bant}")

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return ()

    def isinma_bar(self) -> int:
        return 0

    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        hedef = float(self.parametreler["hedef"])
        bant = float(self.parametreler["bant"])
        mevcut = ctx.pozisyon.exposure if ctx.pozisyon.acik else 0.0
        if mevcut < hedef - bant:
            yon, neden = Yon.BUY, "SABIT_ORAN_ALT_BANT"
        elif mevcut > hedef + bant:
            yon, neden = Yon.SELL, "SABIT_ORAN_UST_BANT"
        else:
            return None
        return Sinyal(
            symbol=ctx.sembol,
            side=yon,
            target_exposure=hedef,
            confidence=1.0,
            reason=neden,
            timestamp=ctx.zaman,
        )


__all__ = ["SabitOran"]
