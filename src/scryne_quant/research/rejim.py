"""Rejim bölümlemesi ve rejim başına performans. (K-054, K-052, Faz 11)

`rejim_kararliligi` kapısının ölçtüğü şey: *"bu strateji kârını tek bir piyasa rejiminden
mi alıyor?"* 2020-2021 boğasında kazanıp 2022 ayısında kaybeden bir strateji toplamda iyi
görünebilir; canlıda karşılaşacağı ilk rejim değişimi onu silebilir.

## Rejim burada bir **model** değil, bir bölümleme

K-052 rejim motorunu (filtrelenmiş olasılık, katman başına eğitim) Faz 12'ye bıraktı. Bu
modül onu beklemiyor ve beklememeli: kapının eşiği Faz 11'de kalibre edilecek, ve eşiği
henüz yazılmamış bir modele bağlamak, kapıyı o modelin kalitesine bağımlı kılardı.

Bölümleme bu yüzden **parametresiz ve nedensel**: `t` barının rejimi, `t−1`e kadarki
`pencere` barlık kıyas getirisinin **işareti**. Yükselen/düşen, iki rejim. Uydurulmuş bir
eşik yok, eğitilmiş bir model yok, dolayısıyla K-052'nin *"yumuşatılmış olasılık geleceği
görür"* tuzağı da yok — burada olasılık diye bir şey yok.

**Nedensellik zorlanıyor:** etiket `t−1`de biten pencereden hesaplanıyor, `t` dahil değil.
`t`yi dahil etmek, o barın getirisini o barın rejimini belirlemekte kullanmak olurdu —
kapanışı bilerek rejimi adlandırmak, look-ahead'in en kibar biçimi.

Faz 12 gerçek bir rejim motoru kurduğunda bu bölümleme onunla **değiştirilebilir**: kapı
etiket dizisini dışarıdan alıyor, kendi üretmiyor. O gün değişen şey eşik olmayacak,
etiketin kaynağı olacak — ve rejim tanımı bir çekiliştir (K-051/4), yani deftere yazılır.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

#: Kıyas getirisinin ölçüldüğü pencere (bar). 1h'te 720 bar = 30 gün — evren kuralının ve
#: kapasite ölçüsünün ufkuyla aynı. Aynı olması bilinçli: üç ayrı yerde üç ayrı "uzun
#: vade" tanımı, hangi sayının neyi anlattığını okunamaz kılar.
VARSAYILAN_PENCERE: Final = 720

#: Pencerenin **zaman** karşılığı. Kapı bar sayısını değil bu süreyi sabit tutar:
#: `VARSAYILAN_PENCERE` 1h'te doğru ama 4h'te 120 gün, 1d'de iki yıl ediyordu ve 1d
#: çekilişlerinin OOS penceresi tamamen ısınmada kalıp rejim **hiç ölçülemiyordu** —
#: Faz 11'in 38 çekilişlik ilk koşusunda görüldü.
PENCERE_GUN: Final = 30


def pencere_bar(timeframe_ms: int, gun: int = PENCERE_GUN) -> int:
    """`gun` günlük pencerenin bu timeframe'deki bar sayısı (en az 1)."""
    return max(1, round(gun * 86_400_000 / timeframe_ms))

#: Bir rejimin ölçülebilir sayılması için gereken asgari bar payı. Altındaysa o rejim
#: **ölçülemedi** sayılır ve kapı geçilmez (K-019) — "o dönemi görmedik" ile "o dönemde
#: iyiydi" aynı şey değil.
ASGARI_REJIM_PAYI: Final = 0.10

YUKSELEN: Final = "yukselen"
DUSEN: Final = "dusen"
ISINMA: Final = ""


class RejimHatasi(ValueError):
    """Rejim ölçümünün girdisi geçersiz."""


def etiketle(
    kiyas_kapanis: np.ndarray, *, pencere: int = VARSAYILAN_PENCERE
) -> np.ndarray:
    """Bar başına rejim etiketi. `t`nin etiketi `t−1`e kadarki pencere getirisinden.

    İlk `pencere + 1` bar `ISINMA` (boş etiket) alır: rejimi belirleyecek geçmiş yok.
    Bu barlar ölçüme girmez — sıfır getirili bir rejime atamak, o rejimi sulandırırdı.
    """
    kapanis = np.asarray(kiyas_kapanis, dtype=np.float64)
    if pencere < 1:
        raise RejimHatasi(f"pencere ≥ 1 olmalı: {pencere}")
    n = kapanis.size
    etiket = np.full(n, ISINMA, dtype=object)
    if n <= pencere + 1:
        return etiket

    # t'nin etiketi: (close[t-1] / close[t-1-pencere] - 1) işareti.
    son = kapanis[pencere : n - 1]
    ilk = kapanis[: n - 1 - pencere]
    with np.errstate(divide="ignore", invalid="ignore"):
        getiri = np.where(ilk > 0.0, son / ilk - 1.0, np.nan)
    gecerli = np.isfinite(getiri)
    hedef = etiket[pencere + 1 :]
    hedef[gecerli] = np.where(getiri[gecerli] > 0.0, YUKSELEN, DUSEN)
    return etiket


@dataclass(frozen=True, slots=True)
class RejimOlcumu:
    """Rejim başına performans + kapının okuduğu tek sayı."""

    rejimler: dict[str, dict[str, Any]]
    en_kotu_sharpe: float | None
    """Ölçülebilir rejimlerin en düşük Sharpe'ı. `None` = en az bir rejim ölçülemedi."""

    en_kotu_rejim: str
    olculemeyen: list[str]
    """Payı `ASGARI_REJIM_PAYI` altında kalan rejimler. Boş değilse kapı ölçülemez."""

    def sozluk(self) -> dict[str, Any]:
        return {
            "rejimler": self.rejimler,
            "en_kotu_sharpe": self.en_kotu_sharpe,
            "en_kotu_rejim": self.en_kotu_rejim,
            "olculemeyen": self.olculemeyen,
        }


def olc(
    ozkaynak: np.ndarray,
    etiketler: Sequence[str] | np.ndarray,
    *,
    yil_bar: float,
    asgari_pay: float = ASGARI_REJIM_PAYI,
    rejim_adlari: Sequence[str] = (YUKSELEN, DUSEN),
) -> RejimOlcumu:
    """Equity eğrisinin rejim başına Sharpe'ı.

    Getiriler bar bazında ayrıştırılıyor, işlem bazında değil: bir işlem iki rejime
    yayılabilir ve onu tek bir rejime atamak, kârı yanlış rejime yazmak olurdu.

    **Rejimler arası birleştirme yok.** Her rejimin Sharpe'ı kendi barlarından; farklı
    rejimlerin barları ardışık değil ama Sharpe bir ortalama/sapma oranı ve sıra
    gerektirmiyor.
    """
    ozkaynak = np.asarray(ozkaynak, dtype=np.float64)
    etiket = np.asarray(etiketler, dtype=object)
    if etiket.size != ozkaynak.size:
        raise RejimHatasi(
            f"etiket sayısı {etiket.size}, özkaynak {ozkaynak.size} — aynı olmalı"
        )
    if ozkaynak.size < 3:
        raise RejimHatasi("rejim ölçümü için en az 3 bar gerekir")

    onceki = np.where(ozkaynak[:-1] != 0.0, ozkaynak[:-1], np.nan)
    getiri = np.nan_to_num(np.diff(ozkaynak) / onceki, nan=0.0, posinf=0.0, neginf=0.0)
    # Bar `t`nin getirisi `t−1 → t` hareketi; rejimi de `t`nin etiketi.
    bar_etiketi = etiket[1:]

    toplam = int((bar_etiketi != ISINMA).sum())
    rejimler: dict[str, dict[str, Any]] = {}
    olculemeyen: list[str] = []
    sharpe_ler: dict[str, float] = {}

    for ad in rejim_adlari:
        maske = bar_etiketi == ad
        sayi = int(maske.sum())
        pay = sayi / toplam if toplam else 0.0
        govde: dict[str, Any] = {"bar": sayi, "pay": pay}
        if sayi < 2 or pay < asgari_pay:
            govde["sharpe"] = None
            govde["getiri"] = None
            olculemeyen.append(ad)
        else:
            r = getiri[maske]
            sapma = float(r.std(ddof=1))
            sharpe = float(r.mean() / sapma * np.sqrt(yil_bar)) if sapma > 0.0 else 0.0
            govde["sharpe"] = sharpe
            govde["getiri"] = float(np.expm1(np.log1p(r).sum()))
            sharpe_ler[ad] = sharpe
        rejimler[ad] = govde

    if olculemeyen or not sharpe_ler:
        return RejimOlcumu(rejimler, None, "", sorted(olculemeyen))
    en_kotu = min(sharpe_ler, key=lambda a: sharpe_ler[a])
    return RejimOlcumu(rejimler, sharpe_ler[en_kotu], en_kotu, [])


def olcum_alanlari(olcum: RejimOlcumu) -> Mapping[str, Any]:
    """Kapı değerlendiricisinin okuduğu düz alanlar."""
    return {"en_kotu_rejim_sharpe": olcum.en_kotu_sharpe}


__all__ = [
    "ASGARI_REJIM_PAYI",
    "DUSEN",
    "ISINMA",
    "PENCERE_GUN",
    "VARSAYILAN_PENCERE",
    "pencere_bar",
    "YUKSELEN",
    "RejimHatasi",
    "RejimOlcumu",
    "etiketle",
    "olc",
    "olcum_alanlari",
]
