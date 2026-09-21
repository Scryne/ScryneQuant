"""Zaman serisi ortalama dönüş ailesi: kendi ortalamasından aşağı sapan üyeler taşınır. (R6, K-104)

`kesitsel_ters` (h54) evreni sıralar: "en çok düşen N". Bu aile sıralamaz, **eşikler**: bir üye
kendi geçmişine göre aşırı satılmışsa adaydır, değilse değildir — evrenin tamamı ortalamasının
üstündeyse portföy nakitte kalır (`zaman_serisi_trend`in ayna kalıbı, yön ters). Tavan
(`azami_enstruman`) eşiği geçenler arasında en aşırı olanı seçer; bağlamıyorsa "eşiği geçen
herkesi eşit taşı" olur.

İki üye, iki aşırılık ölçüsü:

| Aile | Ölçü | Aday koşulu |
|---|---|---|
| `zaman_serisi_sapma` | `z = (close − sma(pencere)) / atr(14)` | `z < −esik` |
| `zaman_serisi_rsi` | Wilder `rsi(pencere)` | `rsi < esik` |

İskelet `kesitsel.py` ile aynı: haftalık dengeleme, eşit ağırlık, `hedef_brut` sabit, ATR 14 aday
uygunluğu. **Yalnız uzun** (kısa bacak K-095'te yok): "ortalamanın üstüne çıkanı kısa sat" yarısı
sorulmuyor. ATR'nin ölçek birimi olması bilinçli: FX çiftlerinin fiyat düzeyleri (JPY çiftleri ×100)
farklı, mutlak sapma karşılaştırılamaz; ATR normalleştirmesi kıyasın oynaklık ölçüsüyle aynı.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, ClassVar

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.evren import EvrenBaglam
from scryne_quant.strategy.hedef import HedefPortfoy
from scryne_quant.strategy.kurma import Aday, KurmaAyarlari, kur, oynaklik_olculebilir
from scryne_quant.strategy.kutuphane.kesitsel import ATR_PENCERESI, VARSAYILAN_HEDEF_BRUT
from scryne_quant.strategy.temel import PortfoyStratejisi


class _EsikliDonus(PortfoyStratejisi):
    """Ortak iskelet: eşik `esik`, alt sınıf `_olcu` (küçük = daha aşırı satılmış) tanımlar."""

    ad: ClassVar[str] = ""
    neden: ClassVar[str] = "ORTALAMA_DONUS"

    def __init__(
        self,
        pencere: int = 120,
        esik: float = 1.0,
        azami_enstruman: int = 10,
        yeniden_dengele_bar: int = 120,
        hedef_brut: float = VARSAYILAN_HEDEF_BRUT,
    ) -> None:
        super().__init__(
            pencere=pencere,
            esik=esik,
            azami_enstruman=azami_enstruman,
            yeniden_dengele_bar=yeniden_dengele_bar,
            hedef_brut=hedef_brut,
        )
        self._ayarlar = KurmaAyarlari(
            yontem="KESITSEL_ESIT",
            azami_enstruman=int(azami_enstruman),
            hedef_brut=float(hedef_brut),
            azami_agirlik=float(hedef_brut) / int(azami_enstruman),
            esit_agirlik=True,
        )
        self._son_dengeleme: int | None = None

    def dogrula(self) -> None:
        p = self.parametreler
        if int(p["pencere"]) < 2:
            raise ValueError("pencere ≥ 2 olmalı")
        if not float(p["esik"]) > 0.0:
            raise ValueError("esik > 0 olmalı")
        if int(p["azami_enstruman"]) < 1:
            raise ValueError("azami_enstruman ≥ 1 olmalı")
        if int(p["yeniden_dengele_bar"]) < 1:
            raise ValueError("yeniden_dengele_bar ≥ 1 olmalı")
        if not 0.0 < float(p["hedef_brut"]) <= 1.0:
            raise ValueError("hedef_brut (0, 1] aralığında olmalı")

    def hazirla(self) -> None:
        self._son_dengeleme = None

    def isinma_bar(self) -> int:
        return max(ATR_PENCERESI, int(self.parametreler["pencere"])) + 2

    def _olcu(self, baglam: Any) -> float:
        """Aşırılık ölçüsü; `< −esik` ya da `< esik` koşulunu `_aday_mi` kurar."""
        raise NotImplementedError

    def _aday_mi(self, olcu: float) -> bool:
        raise NotImplementedError

    def on_bar(self, ctx: EvrenBaglam) -> HedefPortfoy | None:
        periyot = int(self.parametreler["yeniden_dengele_bar"])
        i = ctx.uzunluk - 1
        if self._son_dengeleme is not None and i - self._son_dengeleme < periyot:
            return None

        adaylar: list[Aday] = []
        for sembol in ctx.uyeler():
            baglam = ctx.enstruman(sembol)
            if not baglam.hazir("atr", "skor_ham"):
                continue
            fiyat = baglam.bar("close")
            if fiyat <= 0.0:
                continue
            oynaklik = baglam.ozellik("atr") / fiyat
            if not oynaklik_olculebilir(oynaklik):
                continue
            olcu = self._olcu(baglam)
            if math.isnan(olcu) or not self._aday_mi(olcu):  # NaN aday değil
                continue
            adaylar.append(
                Aday(
                    sembol=sembol,
                    skor=-olcu,  # en aşırı satılmış önce
                    oynaklik=oynaklik,
                    mevcut_agirlik=ctx.pozisyon(sembol).exposure,
                    reason=self.neden,
                    confidence=0.5,
                )
            )

        if not adaylar and not ctx.acik_pozisyonlar():
            return None
        self._son_dengeleme = i
        return kur(
            ctx.zaman,
            adaylar,
            self._ayarlar,
            acik_pozisyonlar=tuple(s for s in ctx.acik_pozisyonlar() if s in ctx.gorunur()),
        )


class ZamanSerisiSapma(_EsikliDonus):
    """`(close − sma(pencere)) / atr(14) < −esik` olan üyeler; en derin sapma önce."""

    ad = "zaman_serisi_sapma"
    neden = "ORTALAMA_DONUS_SAPMA"

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (
            OzellikTanimi("atr", "atr", {"pencere": ATR_PENCERESI}),
            OzellikTanimi("skor_ham", "sma", {"pencere": int(self.parametreler["pencere"])}),
        )

    def _olcu(self, baglam: Any) -> float:
        atr = baglam.ozellik("atr")
        if not atr > 0.0:
            return float("nan")
        return (baglam.bar("close") - baglam.ozellik("skor_ham")) / atr

    def _aday_mi(self, olcu: float) -> bool:
        return olcu < -float(self.parametreler["esik"])


class ZamanSerisiRsi(_EsikliDonus):
    """Wilder `rsi(pencere) < esik` olan üyeler; en düşük RSI önce."""

    ad = "zaman_serisi_rsi"
    neden = "ORTALAMA_DONUS_RSI"

    def dogrula(self) -> None:
        super().dogrula()
        if not 0.0 < float(self.parametreler["esik"]) < 100.0:
            raise ValueError("RSI eşiği (0, 100) aralığında olmalı")

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (
            OzellikTanimi("atr", "atr", {"pencere": ATR_PENCERESI}),
            OzellikTanimi("skor_ham", "rsi", {"pencere": int(self.parametreler["pencere"])}),
        )

    def _olcu(self, baglam: Any) -> float:
        return float(baglam.ozellik("skor_ham"))

    def _aday_mi(self, olcu: float) -> bool:
        return olcu < float(self.parametreler["esik"])


__all__ = ["ZamanSerisiRsi", "ZamanSerisiSapma"]
