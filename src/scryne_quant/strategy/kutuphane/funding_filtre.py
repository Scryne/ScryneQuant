"""Funding filtresi — kırılıma kalabalıklaşma koşulu. (K-042, Faz 4'e dönüş 3, hipotez 2)

**Hipotez — bu üçünün en somutu.** Faz 4 ve iki dönüşte ölçülen desen tek istisnasızdı:
in-sample Sharpe pozitif, out-of-sample negatif, `oos_is_orani` her ailede ve her
timeframe'de düşük. Dönüş 2 bunun *parametre seçiminden* geldiğini varsaydı ve çürüdü.

Geriye bir açıklama daha kalıyor: **kırılımların bir kısmı kalabalıklaşmış bir piyasada
oluyor.** Herkesin aynı yönde konumlandığı bir anda tetiklenen bir kırılım, devam etmesi
gereken hareketin değil tasfiye edilecek kalabalığın işareti olabilir. Doğruysa, aynı
kırılım stratejisine "funding aşırı yüksek değilken gir" koşulu eklemek OOS çöküşünün bir
kısmını almalı.

**Bu hipotez neden ayrı bir aile değil, bir filtre.** Yeni bir giriş mantığı icat etmiyor;
`donchian`ın tam olarak aynı kanal kırılımını kullanıyor ve üstüne **tek** bir koşul
koyuyor. Böylece ölçülen fark tek bir şeye atfedilebilir. İki şeyi aynı anda değiştiren bir
karşılaştırma, hangisinin işe yaradığını söyleyemez.

Çıkış koşuluna funding **eklenmiyor**: bir çıkışı engellemek riski artırır (risk motorunun
`AZALTAN_YONLER` kuralıyla aynı mantık). Filtre yalnızca girişe uygulanır.
"""

from __future__ import annotations

from collections.abc import Sequence

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji

UST = "kanal_ust"
ALT = "kanal_alt"
PERSENTIL = "funding_p"


class FundingFiltre(Strateji):
    """Donchian kırılımı, ama funding aşırı yüksekken girme.

    Parametreler:
        giris: giriş kanalı penceresi (bar).
        cikis: çıkış kanalı penceresi (bar).
        funding_pencere: persentil penceresi (bar).
        azami_p: funding persentili bunun **üstündeyse** giriş elenir [0,1].
        maruziyet: giriş sinyalinin hedef maruziyeti [0,1].
    """

    ad = "funding_filtre"

    def __init__(
        self,
        giris: int = 55,
        cikis: int = 20,
        funding_pencere: int = 240,
        azami_p: float = 0.80,
        maruziyet: float = 0.2,
    ) -> None:
        super().__init__(
            giris=giris,
            cikis=cikis,
            funding_pencere=funding_pencere,
            azami_p=azami_p,
            maruziyet=maruziyet,
        )

    def dogrula(self) -> None:
        giris, cikis = self.parametreler["giris"], self.parametreler["cikis"]
        pencere = self.parametreler["funding_pencere"]
        azami_p = float(self.parametreler["azami_p"])
        maruziyet = float(self.parametreler["maruziyet"])
        if not all(isinstance(v, int) for v in (giris, cikis, pencere)):
            raise ValueError("giris, cikis ve funding_pencere tamsayı olmalı")
        if giris < 2 or cikis < 2 or pencere < 2:
            raise ValueError(
                f"pencereler en az 2 olmalı: giris={giris}, cikis={cikis}, "
                f"funding_pencere={pencere}"
            )
        if not 0.0 < azami_p <= 1.0:
            raise ValueError(f"azami_p (0,1] aralığında olmalı: {azami_p}")
        if not 0.0 < maruziyet <= 1.0:
            raise ValueError(f"maruziyet (0,1] aralığında olmalı: {maruziyet}")

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (
            OzellikTanimi(UST, "en_yuksek", {"pencere": self.parametreler["giris"]}),
            OzellikTanimi(ALT, "en_dusuk", {"pencere": self.parametreler["cikis"]}),
            OzellikTanimi(
                PERSENTIL,
                "funding_persentil",
                {"pencere": self.parametreler["funding_pencere"]},
            ),
        )

    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        # Kanal bir bar geriden okunur — `donchian`la aynı gerekçe (o modülün docstring'i).
        if not ctx.hazir(UST, ALT, geri=1):
            return None

        kapanis = ctx.bar("close")

        # Çıkış **önce** ve filtresiz: bir çıkışı engellemek riski artırır.
        if kapanis < ctx.ozellik(ALT, 1):
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.FLAT,
                target_exposure=0.0,
                confidence=0.5,
                reason="CLOSE_BROKE_LOWER_CHANNEL",
                timestamp=ctx.zaman,
            )

        if kapanis <= ctx.ozellik(UST, 1):
            return None
        if not ctx.hazir(PERSENTIL):
            # Funding penceresi ısınmadan giriş yapılmaz. Filtreyi "henüz bilmiyorum"
            # diye atlamak, filtresiz stratejiyi koşturmak olurdu — ve ölçülen fark
            # o barlarda hangi stratejiye ait olduğu belirsiz kalırdı.
            return None
        if ctx.ozellik(PERSENTIL) > float(self.parametreler["azami_p"]):
            return None

        return Sinyal(
            symbol=ctx.sembol,
            side=Yon.BUY,
            target_exposure=float(self.parametreler["maruziyet"]),
            confidence=0.5,
            reason="CHANNEL_BREAK_WITH_CALM_FUNDING",
            timestamp=ctx.zaman,
        )
