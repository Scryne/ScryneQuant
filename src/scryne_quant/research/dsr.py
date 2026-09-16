"""Deflated Sharpe Ratio: çoklu denemeye ve getiri şekline göre düzeltilmiş Sharpe.

K-054 bunu **raporlanan ama kapı olmayan** metrikler arasında sayıyor ve sebebi
K-019'unkiyle aynı: eşiği ölçülmemiş bir sayı kapı değildir. Burada hesaplanan şey bir
olasılık — *"gözlenen Sharpe, N deneme ve bu getiri şekli altında, gerçekten sıfırdan
büyük mü?"* — ve kararı `oos_sharpe` kapısı veriyor (K-044, ölçülmüş null'dan).

## Neden yine de hesaplanıyor

K-044'ün çapraz kontrolü. Kaydırma null'ı bir **ampirik** dağılım; DSR bir **model**.
İkisi uyuşursa eşiğe güven artar, uyuşmazsa uyuşmazlık kaydedilir ve biri seçilmez.
Faz 4'e dönüş 4'te ikisi uyuşmuştu: kaydırma 1,02, DSR 0,92, Bonferroni 1,30.

## Model ve varsayımları — ikisi de yazılı olmak zorunda

    DSR = Φ( (SR − SR₀)·√(T−1) / √(1 − γ₃·SR + (γ₄−1)/4·SR²) )

- `SR` **bar başına** Sharpe (yıllıklandırılmamış). Yıllıklandırılmış bir değeri buraya
  vermek payda terimlerini ölçekten düşürür ve sonucu sessizce bozar.
- `SR₀` null altında beklenen **en yüksek** Sharpe (`coklu_test.beklenen_azami_sharpe`):
  N denemenin en iyisi, hiç edge yokken bile sıfırdan büyüktür.
- `γ₃`, `γ₄` getirilerin çarpıklığı ve basıklığı. Formülün Sharpe'ın normalliğini
  varsaymamasının sebebi bunlar: kripto getirileri çarpık ve kalın kuyruklu.
- `T` gözlem sayısı.

**Varsayımı:** getiriler bağımsız ve aynı dağılımlı. Otokorelasyon varsa DSR iyimserdir.
Bu bir kusur değil, bir sınır — ve sınırın yazılı olması, sayının nerede kullanılabileceğini
belirliyor: çapraz kontrol olarak evet, kapı olarak hayır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any, Final

import numpy as np

from scryne_quant.research.coklu_test import beklenen_azami_sharpe

#: Getiri sayısının altında DSR'ın anlamsız olduğu sınır. 30 gözlemde çarpıklık ve
#: basıklık tahminleri o kadar gürültülüdür ki paydayı negatife bile sokabilir.
ASGARI_GOZLEM: Final = 30


class DsrHatasi(ValueError):
    """DSR girdisi geçersiz."""


@dataclass(frozen=True, slots=True)
class DsrSonucu:
    """DSR ve onu üreten her ara değer. Ara değerler kayda giriyor: tek bir olasılık,
    hangi varsayımlarla çıktığını söylemiyor."""

    dsr: float
    """`P(gerçek Sharpe > 0)` — model altında."""

    sharpe_bar: float
    beklenen_azami_sharpe_bar: float
    deneme_sayisi: int
    gozlem: int
    carpiklik: float
    basiklik: float

    def sozluk(self) -> dict[str, Any]:
        return {
            "dsr": self.dsr,
            "sharpe_bar": self.sharpe_bar,
            "beklenen_azami_sharpe_bar": self.beklenen_azami_sharpe_bar,
            "deneme_sayisi": self.deneme_sayisi,
            "gozlem": self.gozlem,
            "carpiklik": self.carpiklik,
            "basiklik": self.basiklik,
        }


def _moment(getiriler: np.ndarray) -> tuple[float, float, float]:
    """`(bar başına Sharpe, çarpıklık, basıklık)`. Basıklık **fazlalık değil ham** (normal = 3).

    Formül ham basıklık istiyor; fazlalık basıklık (normal = 0) vermek `(γ₄−1)/4` terimini
    yanlış hesaplar ve sonucu iyimser yapar.
    """
    n = getiriler.size
    ort = float(getiriler.mean())
    sapma = float(getiriler.std(ddof=1))
    if sapma <= 0.0:
        raise DsrHatasi("getiri sapması sıfır: Sharpe tanımsız")
    merkezli = (getiriler - ort) / sapma
    # Popülasyon momentleri: örneklem düzeltmesi bu formülde kullanılmıyor.
    carpiklik = float((merkezli**3).sum() / n)
    basiklik = float((merkezli**4).sum() / n)
    return ort / sapma, carpiklik, basiklik


def hesapla(
    getiriler: np.ndarray,
    *,
    deneme_sayisi: int,
    sharpe_sapmasi: float,
) -> DsrSonucu:
    """Deflated Sharpe Ratio.

    `sharpe_sapmasi`: denemelerin **gözlenen** (bar başına) Sharpe'larının standart
    sapması. Bağımsızlık varsayılmıyor; korelasyon bu sapmadan kendiliğinden geliyor —
    ilişkili denemeler birbirine yakın Sharpe üretir, sapma küçülür, beklenen maksimum
    da küçülür (`coklu_test.beklenen_azami_sharpe`in gerekçesi).
    """
    r = np.asarray(getiriler, dtype=np.float64)
    r = r[np.isfinite(r)]
    if r.size < ASGARI_GOZLEM:
        raise DsrHatasi(
            f"DSR en az {ASGARI_GOZLEM} gözlem ister, verilen: {r.size}. Daha azında "
            "çarpıklık ve basıklık tahminleri paydayı anlamsız kılıyor"
        )

    sharpe, carpiklik, basiklik = _moment(r)
    sifir = beklenen_azami_sharpe(deneme_sayisi, sharpe_sapmasi)
    payda_kare = 1.0 - carpiklik * sharpe + (basiklik - 1.0) / 4.0 * sharpe**2
    if payda_kare <= 0.0:
        raise DsrHatasi(
            f"DSR paydası negatif ({payda_kare:.4f}): getiri şekli bu modelin "
            "varsayımlarını taşımıyor. Sayı uydurmak yerine reddediliyor"
        )
    z = (sharpe - sifir) * math.sqrt(r.size - 1) / math.sqrt(payda_kare)
    return DsrSonucu(
        dsr=float(NormalDist().cdf(z)),
        sharpe_bar=sharpe,
        beklenen_azami_sharpe_bar=sifir,
        deneme_sayisi=deneme_sayisi,
        gozlem=int(r.size),
        carpiklik=carpiklik,
        basiklik=basiklik,
    )


def ozkaynaktan(
    ozkaynak: np.ndarray, *, deneme_sayisi: int, sharpe_sapmasi: float
) -> DsrSonucu:
    """Equity eğrisinden bar getirisi çıkarıp DSR hesaplar."""
    oz = np.asarray(ozkaynak, dtype=np.float64)
    if oz.size < 2:
        raise DsrHatasi("equity eğrisi en az 2 nokta olmalı")
    onceki = np.where(oz[:-1] != 0.0, oz[:-1], np.nan)
    getiri = np.nan_to_num(np.diff(oz) / onceki, nan=0.0, posinf=0.0, neginf=0.0)
    return hesapla(getiri, deneme_sayisi=deneme_sayisi, sharpe_sapmasi=sharpe_sapmasi)


__all__ = ["ASGARI_GOZLEM", "DsrHatasi", "DsrSonucu", "hesapla", "ozkaynaktan"]
