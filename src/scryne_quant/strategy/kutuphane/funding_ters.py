"""Funding tersine — kalabalıklaşma ailesi. (K-042, Faz 4'e dönüş 3, hipotez 1)

**Hipotez:** funding, türev piyasasındaki kalabalıklaşmanın fiyatı. Aşırı pozitif funding
long'ların kalabalıklaştığı anlamına gelir ve kalabalık taraf tasfiyeye açıktır; aşırı
negatif funding'de tersi. O hâlde *"funding kendi son N barının en düşük yüzdelik
diliminde"* bir giriş koşulu, *"en yüksek diliminde"* bir çıkış koşulu olabilir.

**Eşikler persentil, mutlak değil (K-042/3).** Ölçülen medyan funding +0,0096% / 8 saat —
kalıcı pozitif. `funding > 0` koşulu neredeyse her zaman doğru olur ve hiçbir şey ayırt
etmez. `persentil_sirasi` seviyeyi değil göreliliği ölçer: serinin ortalaması kaysa bile
"son N barın en düşük %10'u" aynı şeyi söyler.

**Bu bir tahmin değil, bir sorudur.** Faz 4 ve iki dönüş, aktif yönetimin bu veride
al-tut'u yenemediğini ölçtü. Funding'in bunu değiştireceğine dair bir kanıt yok — olsaydı
hipoteze gerek kalmazdı. Çürümesi beklenen sonuçtur.
"""

from __future__ import annotations

from collections.abc import Sequence

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji

PERSENTIL = "funding_p"


class FundingTers(Strateji):
    """Funding kendi penceresinin dibindeyken gir, tepesindeyken çık.

    Parametreler:
        pencere: persentil penceresi (bar). 1h barda 240 = 10 gün.
        giris_p: bu persentilin **altında** gir [0,1].
        cikis_p: bu persentilin **üstünde** çık [0,1].
        maruziyet: giriş sinyalinin hedef maruziyeti [0,1].
    """

    ad = "funding_ters"

    def __init__(
        self,
        pencere: int = 240,
        giris_p: float = 0.10,
        cikis_p: float = 0.90,
        maruziyet: float = 0.2,
    ) -> None:
        super().__init__(
            pencere=pencere, giris_p=giris_p, cikis_p=cikis_p, maruziyet=maruziyet
        )

    def dogrula(self) -> None:
        pencere = self.parametreler["pencere"]
        giris_p = float(self.parametreler["giris_p"])
        cikis_p = float(self.parametreler["cikis_p"])
        maruziyet = float(self.parametreler["maruziyet"])
        if not isinstance(pencere, int) or pencere < 2:
            raise ValueError(f"pencere en az 2 olmalı: {pencere}")
        if not 0.0 < giris_p < 1.0 or not 0.0 < cikis_p <= 1.0:
            raise ValueError(f"persentiller (0,1] aralığında olmalı: {giris_p}, {cikis_p}")
        if giris_p >= cikis_p:
            raise ValueError(
                f"giris_p < cikis_p olmalı ({giris_p} >= {cikis_p}); aksi hâlde aynı bar "
                f"hem giriş hem çıkış koşulunu sağlar ve strateji tanımsızdır"
            )
        if not 0.0 < maruziyet <= 1.0:
            raise ValueError(f"maruziyet (0,1] aralığında olmalı: {maruziyet}")

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (
            OzellikTanimi(
                PERSENTIL, "funding_persentil", {"pencere": self.parametreler["pencere"]}
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
                reason="FUNDING_IN_LOW_PERCENTILE",
                timestamp=ctx.zaman,
            )
        if p >= float(self.parametreler["cikis_p"]):
            return Sinyal(
                symbol=ctx.sembol,
                side=Yon.FLAT,
                target_exposure=0.0,
                confidence=0.5,
                reason="FUNDING_IN_HIGH_PERCENTILE",
                timestamp=ctx.zaman,
            )
        return None
