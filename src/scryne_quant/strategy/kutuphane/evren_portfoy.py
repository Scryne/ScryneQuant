"""Portföy düzeyi kurma: korelasyon budaması ve oynaklık hedefi. (R7, `portfoy_kurma`, K-108)

`kurma_evren` (Faz 16, K-070/K-072) iki şeyi ölçtü: kurma katmanı seçim katmanının geçemediği
genelleşme kapılarını geçiyor, ama Sharpe/PBO/pertürbasyon kapılarına uzak. Harcanmayan iki
çekilişten biri korelasyon budamasıydı ("kur()'a bir korelasyon matrisi beslemek — henüz var
olmayan bir makine"). Bu modül o makineyi ve roadmap R7'nin adıyla andığı ikinci mekanizmayı
(oynaklık hedefi) kurar. İskelet `evren_kurma._KurmaDegisimi`: **seçim, sıralama ve dengeleme
takvimi kıyasınkiyle aynı**, değişen yalnızca kurma.

- `evren_korelasyon_budama`: `sec` sırayla gider; tutulan bir isimle `|ρ| > tavan` olan aday
  atlanır, sıradaki alır. Kapalı konum `korelasyon_tavani = 1` → matris hesaplanmaz, `None`
  geçer, kıyasla bit-aynı.
- `evren_oynaklik_hedefi`: evren oynaklığı (uygun üyelerin `atr14/close` medyanı) hedefin
  üstündeyse brüt `hedef_brut × hedef/σ_t`; **yalnız düşürür**. Kapalı konum `hedef_oynaklik = ∞`
  → hiç düşürmez, bit-aynı.

**Neden yalnız düşürür:** K-050 asimetrisi (riski azaltan otomatik olabilir, artıran olamaz)
ve `izgaralar.py`nin uyarısı (maruziyeti taramak "daha çok risk al" cevabını her zaman bulur).
Sakin rejimde brütü 0,2'nin üstüne çıkaran bir hedef, tarama için kaldıraç eksenidir; burada yok.

**Korelasyon ölçüsü:** kapanış log getirilerinin `pencere` barlık Pearson korelasyonu, çiftler
arası ortak geçerli barlarla (ızgara doldurma barları NaN, K-057); ortak bar `pencere/2`nin
altındaysa çift **ölçülemez** → matriste yok → `kurma._korelasyon` 1,0 döner → budanır
(ölçülemeyen guard geçilmiş sayılmaz, K-019). Pencere kıyasın hacim ufkuyla aynı (720 = 30 gün)
ve eksen değil.

Optimizasyon (ERC, minimum varyans) **yok**: `kurma.py` başlığı optimizasyonu "aynı veriye daha
çok soru sormak" sayıp ayrı çekiliş istiyor; bu paket iki kapalı-formlu mekanizmayla sınırlı.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, ClassVar

import numpy as np

from scryne_quant.strategy.evren import EvrenBaglam
from scryne_quant.strategy.kurma import Aday, KurmaAyarlari, oynaklik_olculebilir
from scryne_quant.strategy.kutuphane.evren_esit_agirlik import HACIM_PENCERESI
from scryne_quant.strategy.kutuphane.evren_kurma import _KurmaDegisimi


class EvrenKorelasyonBudama(_KurmaDegisimi):
    """Kıyasın seçimi + açgözlü korelasyon budaması (`kurma.sec`, `korelasyon_tavani`)."""

    ad: ClassVar[str] = "evren_korelasyon_budama"

    def __init__(
        self,
        korelasyon_tavani: float = 0.7,
        pencere: int = HACIM_PENCERESI,
        azami_enstruman: int = 10,
        yeniden_dengele_bar: int = 168,
        hedef_brut: float = 0.2,
    ) -> None:
        super().__init__(
            azami_enstruman=azami_enstruman,
            yeniden_dengele_bar=yeniden_dengele_bar,
            hedef_brut=hedef_brut,
            korelasyon_tavani=korelasyon_tavani,
            pencere=pencere,
        )

    def _dogrula_ayar(self) -> None:
        p = self.parametreler
        if not 0.0 < float(p["korelasyon_tavani"]) <= 1.0:
            raise ValueError("korelasyon_tavani (0, 1] aralığında olmalı")
        if int(p["pencere"]) < 3:
            raise ValueError("pencere ≥ 3 olmalı")

    def _kurma_ayarlari(self) -> KurmaAyarlari:
        p = self.parametreler
        return KurmaAyarlari(
            yontem="EVREN_ESIT_KOR",
            azami_enstruman=int(p["azami_enstruman"]),
            azami_agirlik=float(p["hedef_brut"]) / int(p["azami_enstruman"]),
            hedef_brut=float(p["hedef_brut"]),
            esit_agirlik=True,
            korelasyon_tavani=float(p["korelasyon_tavani"]),
        )

    def isinma_bar(self) -> int:
        return max(super().isinma_bar(), int(self.parametreler["pencere"]) + 2)

    def _korelasyon_icin(
        self, ctx: EvrenBaglam, adaylar: Sequence[Aday]
    ) -> Mapping[tuple[str, str], float] | None:
        if float(self.parametreler["korelasyon_tavani"]) >= 1.0:
            # `|ρ| > 1` hiçbir çiftte tutmaz: matris hesaplamak sonucu değiştirmez, kod yolu
            # kıyasınkiyle aynı kalsın (kapalı konum bit-aynı).
            return None
        pencere = int(self.parametreler["pencere"])
        semboller: list[str] = []
        getiriler: list[np.ndarray] = []
        for aday in adaylar:
            b = ctx.enstruman(aday.sembol)
            if b.uzunluk < pencere + 1:
                continue
            kapanis = b.bar_serisi("close", pencere + 1)
            with np.errstate(divide="ignore", invalid="ignore"):
                g = np.diff(np.log(np.where(kapanis > 0.0, kapanis, np.nan)))
            semboller.append(aday.sembol)
            getiriler.append(g)
        if len(semboller) < 2:
            return {}
        return _ciftli_korelasyon(semboller, np.vstack(getiriler), asgari_ortak=pencere // 2)


def _ciftli_korelasyon(
    semboller: Sequence[str], r: np.ndarray, *, asgari_ortak: int
) -> dict[tuple[str, str], float]:
    """Çiftler arası ortak geçerli barlarla Pearson korelasyonu. Ölçülemeyen çift sözlükte yok."""
    gecerli = np.isfinite(r)
    n = len(semboller)
    out: dict[tuple[str, str], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            m = gecerli[i] & gecerli[j]
            k = int(m.sum())
            if k < asgari_ortak or k < 3:
                continue
            a = r[i][m]
            b = r[j][m]
            sa = a.std()
            sb = b.std()
            if not (sa > 0.0 and sb > 0.0):
                continue
            rho = float(((a - a.mean()) * (b - b.mean())).mean() / (sa * sb))
            if math.isfinite(rho):
                out[(semboller[i], semboller[j])] = rho
    return out


class EvrenOynaklikHedefi(_KurmaDegisimi):
    """Kıyasın seçimi ve eşit ağırlığı; evren oynaklığı hedefin üstündeyse brüt oranla düşer.

    `σ_t` = o dengelemede **uygun** üyelerin (kıyasın aday kümesi: ısınmış, fiyat > 0, ölçülebilir
    oynaklık) `atr14/close` medyanı — 1h bar biriminde, kıyasın/risk motorunun kendi oynaklık ölçüsü
    (`ATR_PENCERESI` 14, eksen değil). `σ_t ≤ hedef` → kıyasın kendisi; `σ_t > hedef` →
    `hedef_brut × hedef/σ_t`. Tavan (`azami_agirlik`) sabit kalır: eşit payın kendisi; brüt düşünce
    pay zaten tavanın altında.
    """

    ad: ClassVar[str] = "evren_oynaklik_hedefi"

    def __init__(
        self,
        hedef_oynaklik: float = 0.01,
        azami_enstruman: int = 10,
        yeniden_dengele_bar: int = 168,
        hedef_brut: float = 0.2,
    ) -> None:
        super().__init__(
            azami_enstruman=azami_enstruman,
            yeniden_dengele_bar=yeniden_dengele_bar,
            hedef_brut=hedef_brut,
            hedef_oynaklik=hedef_oynaklik,
        )

    def _dogrula_ayar(self) -> None:
        h = float(self.parametreler["hedef_oynaklik"])
        if not h > 0.0:  # ∞ geçerli: kapalı konum (test için), ızgarada yok
            raise ValueError("hedef_oynaklik > 0 olmalı")

    def _kurma_ayarlari(self) -> KurmaAyarlari:
        p = self.parametreler
        return KurmaAyarlari(
            yontem="EVREN_ESIT_OYNAKLIK_HEDEFI",
            azami_enstruman=int(p["azami_enstruman"]),
            azami_agirlik=float(p["hedef_brut"]) / int(p["azami_enstruman"]),
            hedef_brut=float(p["hedef_brut"]),
            esit_agirlik=True,
        )

    def _evren_oynakligi(self, ctx: EvrenBaglam) -> float:
        degerler: list[float] = []
        for sembol in ctx.uyeler():
            b = ctx.enstruman(sembol)
            if not b.hazir(*self._hazirlik_ozellikleri()):
                continue
            fiyat = b.bar("close")
            if fiyat <= 0.0:
                continue
            oynaklik = b.ozellik("atr") / fiyat
            if oynaklik_olculebilir(oynaklik):
                degerler.append(oynaklik)
        return float(np.median(degerler)) if degerler else float("nan")

    def _ayarlar_icin(self, ctx: EvrenBaglam) -> KurmaAyarlari:
        hedef = float(self.parametreler["hedef_oynaklik"])
        if math.isinf(hedef):
            return self._ayarlar
        sigma = self._evren_oynakligi(ctx)
        if not (sigma > hedef):  # NaN dahil: ölçülemeyen oynaklıkta kıyas gibi davranır
            return self._ayarlar
        return replace(self._ayarlar, hedef_brut=self._ayarlar.hedef_brut * hedef / sigma)

    def sozluk(self) -> dict[str, Any]:
        d = super().sozluk()
        h = d.get("parametreler", {}).get("hedef_oynaklik")
        if isinstance(h, float) and math.isinf(h):
            d["parametreler"] = dict(d["parametreler"]) | {"hedef_oynaklik": "inf"}
        return d


#: Program çekilişlerinin sırası (durma kuralı bu sırayla okur).
PORTFOY_AILELERI: dict[str, type[_KurmaDegisimi]] = {
    EvrenKorelasyonBudama.ad: EvrenKorelasyonBudama,
    EvrenOynaklikHedefi.ad: EvrenOynaklikHedefi,
}

__all__ = ["EvrenKorelasyonBudama", "EvrenOynaklikHedefi", "PORTFOY_AILELERI"]
