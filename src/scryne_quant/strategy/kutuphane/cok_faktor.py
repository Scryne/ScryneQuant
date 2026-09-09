"""Çok faktörlü — birden fazla sinyalin birlikte değerlendirilmesi. (Faz 4, §9)

Üç faktör oy verir, oy sayısı eşiği geçerse pozisyon açılır:

1. **Trend** — kapanış uzun SMA'nın üstünde mi.
2. **Momentum** — ROC pozitif mi.
3. **Hacim teyidi** — bar hacmi hacim ortalamasının üstünde mi (hareketin arkasında işlem
   var mı, yoksa ince bir piyasada mı oluştu).

Çıkış girişten **daha kolay**: oy sayısı çıkış eşiğinin altına düşünce kapatılır. Asimetri
bilinçli — K-007'nin "belirsizlikte aleyhte yuvarla" kuralının strateji katmanındaki
karşılığı. Girmek için üç kanıt istemek, çıkmak için birinin kaybolmasını yeterli saymak,
her iki yönde de aynı eşiği kullanmaktan muhafazakârdır.

**`confidence` burada gerçekten bir şey ifade ediyor:** oy oranı. Diğer ailelerde sabit
0,5 çünkü ikili bir koşuldan güven derecesi türetmek uydurma olurdu. Risk motoru (Faz 5)
bu alanı pozisyon büyüklüğünde kullanacak; anlamlı doldurulabildiği tek yer burası.
"""

from __future__ import annotations

from collections.abc import Sequence

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji

TREND = "cf_trend_sma"
ROC = "cf_roc"
HACIM = "cf_hacim_sma"

FAKTOR_SAYISI = 3


class CokFaktor(Strateji):
    """Trend + momentum + hacim teyidi; oy sayısına göre gir/çık.

    Parametreler:
        trend_pencere: trend SMA penceresi (bar).
        roc_pencere: ROC penceresi (bar).
        hacim_pencere: hacim ortalaması penceresi (bar).
        giris_oyu: girmek için gereken oy sayısı (1-3).
        cikis_oyu: bu oy sayısının **altına** düşünce çıkılır (0-3).
        maruziyet: tam oyda hedef maruziyet; kısmi oyda oranla ölçeklenir.
    """

    ad = "cok_faktor"

    def __init__(
        self,
        trend_pencere: int = 100,
        roc_pencere: int = 24,
        hacim_pencere: int = 20,
        giris_oyu: int = 3,
        cikis_oyu: int = 2,
        maruziyet: float = 0.2,
    ) -> None:
        super().__init__(
            trend_pencere=trend_pencere,
            roc_pencere=roc_pencere,
            hacim_pencere=hacim_pencere,
            giris_oyu=giris_oyu,
            cikis_oyu=cikis_oyu,
            maruziyet=maruziyet,
        )

    def dogrula(self) -> None:
        p = self.parametreler
        for ad in ("trend_pencere", "roc_pencere", "hacim_pencere"):
            if not isinstance(p[ad], int) or p[ad] < 2:
                raise ValueError(f"{ad} en az 2 tamsayı olmalı: {p[ad]}")
        giris, cikis = p["giris_oyu"], p["cikis_oyu"]
        if not isinstance(giris, int) or not 1 <= giris <= FAKTOR_SAYISI:
            raise ValueError(f"giris_oyu 1-{FAKTOR_SAYISI} olmalı: {giris}")
        if not isinstance(cikis, int) or not 0 <= cikis <= FAKTOR_SAYISI:
            raise ValueError(f"cikis_oyu 0-{FAKTOR_SAYISI} olmalı: {cikis}")
        if cikis > giris:
            # Çıkış eşiği girişten yüksekse, girilen bar aynı anda çıkış koşulunu da
            # sağlar: strateji her sinyalde gir-çık yapar ve yalnızca maliyet öder.
            raise ValueError(f"cikis_oyu <= giris_oyu olmalı: {cikis} > {giris}")
        if not 0.0 < float(p["maruziyet"]) <= 1.0:
            raise ValueError(f"maruziyet (0,1] aralığında olmalı: {p['maruziyet']}")

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (
            OzellikTanimi(TREND, "sma", {"pencere": self.parametreler["trend_pencere"]}),
            OzellikTanimi(ROC, "roc", {"pencere": self.parametreler["roc_pencere"]}),
            OzellikTanimi(HACIM, "hacim_sma", {"pencere": self.parametreler["hacim_pencere"]}),
        )

    def _oylar(self, ctx: Baglam) -> int:
        return sum(
            (
                ctx.bar("close") > ctx.ozellik(TREND),
                ctx.ozellik(ROC) > 0.0,
                ctx.bar("volume") > ctx.ozellik(HACIM),
            )
        )

    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        if not ctx.hazir(TREND, ROC, HACIM):
            return None

        oy = self._oylar(ctx)
        guven = oy / FAKTOR_SAYISI

        if oy >= int(self.parametreler["giris_oyu"]):
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.BUY,
                # Oy oranıyla ölçekleniyor: iki faktörle girilen bir pozisyon, üç
                # faktörle girilenden küçük olmalı.
                target_exposure=float(self.parametreler["maruziyet"]) * guven,
                confidence=guven,
                reason=f"MULTIFACTOR_VOTES_{oy}_OF_{FAKTOR_SAYISI}",
                timestamp=ctx.zaman,
            )
        if oy < int(self.parametreler["cikis_oyu"]):
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.FLAT,
                target_exposure=0.0,
                confidence=1.0 - guven,
                reason=f"MULTIFACTOR_VOTES_FELL_TO_{oy}",
                timestamp=ctx.zaman,
            )
        return None
