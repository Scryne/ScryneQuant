"""Funding eğilimi — birikimli baskı rejimi. (K-042, Faz 4'e dönüş 3, hipotez 3)

**Hipotez:** tek bir funding ölçümü gürültülüdür — 8 saatlik bir ödeme, o anın
konumlanmasını söyler ama rejimi söylemez. Birikimli funding (son N barın toplamı) daha
kararlı bir büyüklük: uzun süre pozitif kalması, yükselişin kaldıraçla finanse edildiğini
gösterir ve o finansmanın kendisi bir kırılganlıktır.

`funding_ters`ten farkı **zaman ölçeği**: o, tek bir ölçümün kendi penceresindeki yerine
bakar (anlık aşırılık); bu, ödemelerin toplamına bakar (süregelen baskı). İkisi aynı veriyi
farklı soruyla okuyor, ve K-039 gereği **ayrı** birer çekiliş olarak sayılıyorlar.

Birikimin persentili alınıyor, ham toplamı değil — K-042/3 ile aynı gerekçe: toplam da
kalıcı pozitif bir serinin toplamı olduğu için sürekli büyür, ve mutlak bir eşik zamanla
anlamını yitirir.
"""

from __future__ import annotations

from collections.abc import Sequence

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji

PERSENTIL = "funding_kum_p"


class FundingEgilim(Strateji):
    """Birikimli funding baskısı düşük rejimde pozisyonda kal, yüksek rejimde çık.

    Parametreler:
        birikim: kaç barın funding'i toplanacak.
        pencere: birikimin persentil penceresi (bar).
        giris_p: bu persentilin **altında** gir [0,1].
        cikis_p: bu persentilin **üstünde** çık [0,1].
        maruziyet: giriş sinyalinin hedef maruziyeti [0,1].
    """

    ad = "funding_egilim"

    def __init__(
        self,
        birikim: int = 72,
        pencere: int = 480,
        giris_p: float = 0.20,
        cikis_p: float = 0.85,
        maruziyet: float = 0.2,
    ) -> None:
        super().__init__(
            birikim=birikim,
            pencere=pencere,
            giris_p=giris_p,
            cikis_p=cikis_p,
            maruziyet=maruziyet,
        )

    def dogrula(self) -> None:
        birikim, pencere = self.parametreler["birikim"], self.parametreler["pencere"]
        giris_p = float(self.parametreler["giris_p"])
        cikis_p = float(self.parametreler["cikis_p"])
        maruziyet = float(self.parametreler["maruziyet"])
        if not all(isinstance(v, int) for v in (birikim, pencere)):
            raise ValueError("birikim ve pencere tamsayı olmalı")
        if birikim < 2 or pencere < 2:
            raise ValueError(f"pencereler en az 2 olmalı: {birikim}, {pencere}")
        if not 0.0 < giris_p < 1.0 or not 0.0 < cikis_p <= 1.0:
            raise ValueError(f"persentiller (0,1] aralığında olmalı: {giris_p}, {cikis_p}")
        if giris_p >= cikis_p:
            raise ValueError(f"giris_p < cikis_p olmalı ({giris_p} >= {cikis_p})")
        if not 0.0 < maruziyet <= 1.0:
            raise ValueError(f"maruziyet (0,1] aralığında olmalı: {maruziyet}")

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (
            OzellikTanimi(
                PERSENTIL,
                "funding_kumulatif_persentil",
                {
                    "birikim": self.parametreler["birikim"],
                    "pencere": self.parametreler["pencere"],
                },
            ),
        )

    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        if not ctx.hazir(PERSENTIL):
            return None

        p = ctx.ozellik(PERSENTIL)
        if p <= float(self.parametreler["giris_p"]):
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.BUY,
                target_exposure=float(self.parametreler["maruziyet"]),
                confidence=0.5,
                reason="CUMULATIVE_FUNDING_PRESSURE_LOW",
                timestamp=ctx.zaman,
            )
        if p >= float(self.parametreler["cikis_p"]):
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.FLAT,
                target_exposure=0.0,
                confidence=0.5,
                reason="CUMULATIVE_FUNDING_PRESSURE_HIGH",
                timestamp=ctx.zaman,
            )
        return None
