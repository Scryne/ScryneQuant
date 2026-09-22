"""FX oynaklık filtresi: kıyasın üstüne tek bir **engelleyici** adım, elenen pay nakitte. (R6,
K-105)

`fx_fiyat` (K-102) ve `fx_ortalama_donus` (K-104) fiyat sinyalinden **seçim** yaptı. Bu aile seçim
yapmaz: kıyasın (`fx_evren_esit_agirlik`, K-099) evrenini, eşit ağırlığını ve haftalık takvimini
aynen alır; tek eklediği, oynaklığı kendi taban çizgisine göre **genişlemiş** üyeyi o hafta dışarıda
bırakmaktır. Ölçü `atr(14) / atr(pencere)` — kısa vadeli gerçekleşen oynaklığın uzun tabana oranı.
ATR 14 kıyasın/risk motorunun ölçüsüdür ve eksen değildir (`evren_kurma.py` gerekçesi); eksen yalnız
taban penceresi ve eşik.

**Elenen üyenin payı nakitte kalır, kalanlara dağıtılmaz.** Kripto türev filtrelerinde
(`evren_funding`) dışlanan ismin yerini sıradaki alır, çünkü orada evren tavandan büyüktür. FX'te
kıyas evrenin tamamını taşır; dışlananın payı kalanlara dağıtılsa "yüksek oynaklıkta yoğunlaş"
olurdu — sorulan sorunun tersi.
Bu yüzden tavan her dengelemede **filtre öncesi uygun üye sayısına** göre eşit paya oturtulur
(`_ayarlar_icin`): hiç eleme olmadığında ağırlıklar kıyasla aynı (testle, hash düzeyinde), eleme
olduğunda brüt maruziyet düşer. K-037 ile uyumlu: bu katman yalnız engeller, izin vermez.

İki üye, aynı ölçü, iki kapsam:

| Aile | Karar | Mekanizma |
|---|---|---|
| `fx_oynaklik_filtre_cift` | üye başına `oran > esik` → o çift nakit | çiftin kendi genişlemesi |
| `fx_oynaklik_filtre_evren` | **medyan** oran `> esik` → **hepsi** nakit | piyasa geneli rejim |

Ölçülemeyen oran (`atr(pencere)` ısınmamış ya da 0) o üyeyi dışarıda bırakır — ölçülemeyen guard
geçilmiş sayılmaz (K-019). Boyutlandırma yok: `1/σ` ağırlık bu pencerede yapısal olarak ölçülemez
(kapalı tur üretmez, `runs/fx/oynaklik-kaynak-olcumu.json`); seçim ile boyut karıştırılmaz.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, ClassVar

import numpy as np

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.evren import EvrenBaglam
from scryne_quant.strategy.hedef import HedefPortfoy
from scryne_quant.strategy.kurma import KurmaAyarlari, oynaklik_olculebilir
from scryne_quant.strategy.kutuphane.evren_esit_agirlik import (
    ATR_PENCERESI,
    FxEvrenEsitAgirlik,
)

#: Uzun taban ATR'sinin özellik adı; `atr` (14) kıyasınki.
ATR_UZUN = "atr_uzun"


class _OynaklikFiltre(FxEvrenEsitAgirlik):
    """Ortak iskelet: kıyasın seçimi ve kurması; alt sınıf yalnızca kimin elendiğini söyler."""

    ad: ClassVar[str] = ""

    def __init__(
        self,
        pencere: int = 120,
        esik: float = 1.0,
        azami_enstruman: int = 21,
        yeniden_dengele_bar: int = 120,
        hedef_brut: float = 0.2,
    ) -> None:
        super().__init__(
            yeniden_dengele_bar=yeniden_dengele_bar,
            azami_enstruman=azami_enstruman,
            hedef_brut=hedef_brut,
            esit_agirlik=True,
        )
        # Kayıt için parametre sözlüğü: kıyasın alanları + bu ailenin iki ekseni.
        self.parametreler = {
            "pencere": pencere,
            "esik": esik,
            "azami_enstruman": azami_enstruman,
            "yeniden_dengele_bar": yeniden_dengele_bar,
            "hedef_brut": hedef_brut,
        }
        self.dogrula()
        self._uygun_sayisi = 0

    def dogrula(self) -> None:
        p = self.parametreler
        if int(p["yeniden_dengele_bar"]) < 1:
            raise ValueError("yeniden_dengele_bar ≥ 1 olmalı")
        if int(p["azami_enstruman"]) < 1:
            raise ValueError("azami_enstruman ≥ 1 olmalı")
        if not 0.0 < float(p["hedef_brut"]) <= 1.0:
            raise ValueError("hedef_brut (0, 1] aralığında olmalı")
        if "pencere" in p and int(p["pencere"]) <= ATR_PENCERESI:
            # Taban kısa ATR'den uzun olmalı; eşit ya da kısa bir taban oranı 1'e çiviler.
            raise ValueError(f"pencere > {ATR_PENCERESI} olmalı")
        if "esik" in p and not (math.isfinite(float(p["esik"])) and float(p["esik"]) > 0.0):
            raise ValueError("esik pozitif ve sonlu olmalı")

    def hazirla(self) -> None:
        super().hazirla()
        self._uygun_sayisi = 0

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (
            *super().ozellikler(),
            OzellikTanimi(ATR_UZUN, "atr", {"pencere": int(self.parametreler["pencere"])}),
        )

    def isinma_bar(self) -> int:
        return max(ATR_PENCERESI, int(self.parametreler["pencere"])) + 2

    def _hazirlik_ozellikleri(self) -> tuple[str, ...]:
        # Uygunluk kıyasınki (yalnız ATR 14): dengeleme takviminin çıpası ilk uygun barda
        # atılır ve kıyasla **aynı** kalmalı. Taban ATR'si ısınmamışsa oran ölçülemez → o üye
        # o hafta elenir (K-019); ısınma tabanı 242 gerçek koşuda bunu ölçüm dışında bırakır.
        return ("atr",)

    def _oranlar(self, ctx: EvrenBaglam) -> list[tuple[str, float]]:
        """Filtre öncesi uygun üyeler ve oranları. Uygunluk kıyasın `on_bar` kontrolleriyle
        aynı (ısınma, fiyat, ölçülebilir oynaklık) — böylece eleme olmadığında aday kümesi
        kıyasınkiyle **aynı** olur ve tavan doğru üye sayısına oturur."""
        oranlar: list[tuple[str, float]] = []
        for sembol in ctx.uyeler():
            b = ctx.enstruman(sembol)
            if not b.hazir("atr"):
                continue
            fiyat = b.bar("close")
            if fiyat <= 0.0:
                continue
            atr = b.ozellik("atr")
            if not oynaklik_olculebilir(atr / fiyat):
                continue
            oran = float("nan")
            if b.hazir(ATR_UZUN):
                uzun = b.ozellik(ATR_UZUN)
                if uzun > 0.0:
                    oran = atr / uzun
            oranlar.append((sembol, float(oran)))
        return oranlar

    def _tutulanlar(self, oranlar: list[tuple[str, float]]) -> set[str]:
        raise NotImplementedError

    def _aday_uyeler(self, ctx: EvrenBaglam) -> tuple[str, ...]:
        oranlar = self._oranlar(ctx)
        self._uygun_sayisi = len(oranlar)
        tutulan = self._tutulanlar(oranlar)
        return tuple(s for s in ctx.uyeler() if s in tutulan)

    def on_bar(self, ctx: EvrenBaglam) -> HedefPortfoy | None:
        periyot = int(self.parametreler["yeniden_dengele_bar"])
        i = ctx.uzunluk - 1
        if self._son_dengeleme is not None and i - self._son_dengeleme < periyot:
            return None
        hedef = super().on_bar(ctx)
        if hedef is None and self._uygun_sayisi > 0:
            # Kıyas bu barda dengelerdi (uygun üye var); filtre hepsini eledi ve elde pozisyon yok.
            # Takvim çıpası yine atılır: aksi hâlde filtre kıyastan farklı bir haftalık fazda
            # koşar ve fark filtreden değil takvimden gelirdi.
            self._son_dengeleme = i
        return hedef

    def _ayarlar_icin(self, ctx: EvrenBaglam) -> KurmaAyarlari:
        """Tavan = filtre öncesi eşit pay. Elenen üyenin payı nakitte kalır.

        Pay, `kurma.agirliklar`ın eşit ağırlık aritmetiğiyle **aynı sırada** hesaplanır
        (`(1/n) · hedef_brut`): eleme yokken `w > tavan` hiçbir üyede tutmaz, kırpma döngüsüne
        girilmez ve sonuç kıyasla bit düzeyinde aynı kalır. Takılı pozisyon payı kıyasta olduğu
        gibi brütten düşülür (K-100/3).
        """
        ayarlar = super()._ayarlar_icin(ctx)
        if self._uygun_sayisi <= 0:
            return ayarlar
        tavan = (1.0 / self._uygun_sayisi) * ayarlar.hedef_brut
        return replace(ayarlar, azami_agirlik=tavan)

    def sozluk(self) -> dict[str, Any]:
        return super().sozluk() | {"kiyas": False}


class FxOynaklikFiltreCift(_OynaklikFiltre):
    """Üye başına: `atr(14)/atr(pencere) > esik` olan çift o hafta taşınmaz (payı nakit)."""

    ad = "fx_oynaklik_filtre_cift"

    def _tutulanlar(self, oranlar: list[tuple[str, float]]) -> set[str]:
        esik = float(self.parametreler["esik"])
        return {s for s, oran in oranlar if math.isfinite(oran) and oran <= esik}


class FxEvrenOynaklikFiltre(_OynaklikFiltre):
    """Evren geneli: uygun üyelerin medyan oranı `> esik` ise o hafta hiçbir şey taşınmaz."""

    ad = "fx_oynaklik_filtre_evren"

    def _tutulanlar(self, oranlar: list[tuple[str, float]]) -> set[str]:
        olculen = [oran for _, oran in oranlar if math.isfinite(oran)]
        if not olculen:
            return set()
        if float(np.median(olculen)) > float(self.parametreler["esik"]):
            return set()
        # Rejim sakinken kıyasın kendisi: ölçülemeyen oranlı üye yine dışarıda (K-019).
        return {s for s, oran in oranlar if math.isfinite(oran)}


__all__ = ["ATR_UZUN", "FxEvrenOynaklikFiltre", "FxOynaklikFiltreCift"]
