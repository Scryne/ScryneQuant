"""Al ve tut — **kıyas ölçütü**, strateji ailesi değil. (Faz 4)

Bir stratejinin "%15 kazandı" cümlesi tek başına hiçbir şey söylemez. Aynı dönemde varlık
%200 yükseldiyse o strateji para kazandırmadı, **kaybettirdi** — sermayeyi piyasada
tutmak yerine sistemin içinde tuttu ve fark kadar fırsat maliyeti ödetti.

Bu yüzden al-tut kıyası her karşılaştırmada bulunur ve `AILELER`e **kaydedilmez**: beş
aileden biri değil, hepsinin karşısındaki çizgi.

Kıyasın adil olması için diğer stratejilerle **tam olarak aynı yoldan** geçiyor: aynı
`ctx` sözleşmesi, aynı fill kuralı (K-004), aynı komisyon ve slippage (K-007). Fiyat
serisinden doğrudan `close[-1]/close[0]` hesaplamak daha kolay olurdu ama maliyetsiz ve
fill'siz bir kıyas, stratejileri haksız yere kötü gösterirdi.
"""

from __future__ import annotations

from collections.abc import Sequence

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji


class AlTut(Strateji):
    """İlk barda hedef maruziyete gir, bir daha hiç işlem yapma.

    Parametreler:
        maruziyet: hedef maruziyet [0,1]. Karşılaştırmada diğer stratejilerle aynı
            değere ayarlanır — %100 al-tut ile %20 maruziyetli bir stratejiyi
            karşılaştırmak, riski değil sadece kaldıracı ölçerdi.
    """

    ad = "al_tut"

    def __init__(self, maruziyet: float = 0.2) -> None:
        super().__init__(maruziyet=maruziyet)

    def dogrula(self) -> None:
        maruziyet = float(self.parametreler["maruziyet"])
        if not 0.0 < maruziyet <= 1.0:
            raise ValueError(f"maruziyet (0,1] aralığında olmalı: {maruziyet}")

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return ()

    def isinma_bar(self) -> int:
        """İndikatör yok; ilk bardan itibaren işlem yapabilir."""
        return 0

    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        # Durum `ctx.pozisyon`dan okunuyor, strateji içinde tutulmuyor.
        #
        # İlk hâli bir `_girildi` bayrağı tutuyordu ve **sessizce bozuldu**: walk-forward
        # penceresinde bayrak ısınma barında kalkıyor, o barda üretilen sinyal ölçüm
        # penceresine girmediği için atılıyor, ve strateji bir daha hiç sinyal
        # üretmiyordu. Kıyas çizgisi tabloda %0,0 getiri olarak göründü.
        #
        # Ders genel: kendi durumunu tutan bir strateji, sinyalinin **kabul edildiğini**
        # varsayamaz. Sinyal risk motorunda da reddedilebilir (Faz 5). Durumu portföyden
        # okumak bu varsayımı ortadan kaldırıyor.
        if ctx.pozisyon.acik:
            return None
        return Sinyal(
            symbol=ctx.sembol,
            side=Yon.BUY,
            target_exposure=float(self.parametreler["maruziyet"]),
            confidence=1.0,
            reason="BUY_AND_HOLD_ENTRY",
            timestamp=ctx.zaman,
        )
