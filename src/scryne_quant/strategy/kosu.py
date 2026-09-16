"""Stratejiyi bar bar dolaştıran ince sürücü. (Faz 2)

Bu bir backtest motoru **değil**: fill yok, maliyet yok, portföy yok — onlar Faz 3'ün
işi. Burada olan tek şey, sözleşmenin uçtan uca çalıştığını gösteren döngü:

    özellikleri hesapla → her bar için ctx kes → on_bar çağır → sinyalleri topla

Faz 2'nin look-ahead testi bu döngü üzerinden ölçüyor. Sözleşmeye bakan testler
(erişimcinin hata fırlatması) ayrı; bu testin ölçtüğü **sonuç**: geleceği bozunca
sinyaller değişiyor mu.

Faz 3'ün event loop'u bu modülü değil, aynı parçaları kullanacak — pozisyonu her barda
kendi portföyünden vererek. `PiyasaGorunumu.baglam(i, pozisyon)` o yüzden ayrı duruyor.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from scryne_quant.features.indikator import GecersizParametre
from scryne_quant.features.motor import OzellikHatasi, OzellikTanimi, hesapla
from scryne_quant.strategy.baglam import PiyasaGorunumu
from scryne_quant.strategy.evren import LISTELENMEDI, EvrenGorunumu
from scryne_quant.strategy.sinyal import Sinyal
from scryne_quant.strategy.temel import PortfoyStratejisi, Strateji


def gorunum_kur(
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    strateji: Strateji,
) -> PiyasaGorunumu:
    """Stratejinin bildirdiği özellikleri hesaplayıp piyasa görünümünü kurar."""
    return PiyasaGorunumu(
        sembol=sembol,
        timeframe=timeframe,
        barlar=dict(bar_dizileri),
        ozellikler=hesapla(bar_dizileri, strateji.ozellikler()),
    )


def sinyalleri_uret(strateji: Strateji, gorunum: PiyasaGorunumu) -> list[Sinyal]:
    """Stratejiyi tüm seri üzerinde dolaştırır, ürettiği sinyalleri sırayla döndürür.

    `hazirla()` başta çağrılır: aynı strateji örneğiyle yapılan ikinci koşunun
    birincisinden etkilenmemesi determinizmin (K-009) ön koşulu.
    """
    strateji.hazirla()
    return [
        sinyal
        for ctx in gorunum.akis(parametreler=strateji.parametreler)
        if (sinyal := strateji.on_bar(ctx)) is not None
    ]


def ozellikleri_hesapla(
    diziler: Mapping[str, np.ndarray],
    tanimlar: Sequence[OzellikTanimi],
) -> dict[str, np.ndarray]:
    """Özellikleri enstrümanın **var olan** barları üzerinde hesaplar, ızgaraya geri koyar.

    Ortak ızgaraya oturtulmuş bir seride `listelenmedi` barlar gerçekte yoktur; tek
    sembollü yolda (Faz 1-7) bu barlar hiç satır olarak bulunmaz ve indikatör onları
    görmez. Burada da görmemeli (K-001): aynı sembolün aynı barları iki yolda aynı
    özelliği üretmek zorunda. Hiç `listelenmedi` bar yoksa sıkıştırma kimliktir ve sonuç
    `hesapla` ile **bit düzeyinde** aynıdır.

    Var olan bar sayısı bir özelliğin penceresine yetmiyorsa o özellik tamamen NaN kalır:
    ısınmayı hiç tamamlamamış bir sembol "hazır değil" demektir, bir hata değil.
    """
    kalite = np.asarray(diziler["quality_status"], dtype=object)
    var = kalite != LISTELENMEDI
    if bool(var.all()):
        return hesapla(diziler, tanimlar)

    n = len(kalite)
    sikisik = {ad: np.asarray(d)[var] for ad, d in diziler.items()}
    out: dict[str, np.ndarray] = {}
    for tanim in tanimlar:
        try:
            parca = hesapla(sikisik, (tanim,)) if int(var.sum()) else None
        except GecersizParametre:
            parca = None
        for sutun in tanim.sutunlar:
            if sutun in out:
                raise OzellikHatasi(f"özellik adı iki kez tanımlanmış: {sutun}")
            dizi = np.full(n, np.nan, dtype=np.float64)
            if parca is not None:
                dizi[var] = parca[sutun]
            dizi.flags.writeable = False
            out[sutun] = dizi
    return out


def evren_gorunum_kur(
    timeframe: str,
    bar_dizileri: Mapping[str, Mapping[str, np.ndarray]],
    uyelik: Mapping[str, np.ndarray],
    strateji: PortfoyStratejisi,
    *,
    kural_kimligi: str = "",
) -> EvrenGorunumu:
    """Ortak ızgaraya oturtulmuş bar dizilerinden evren görünümü kurar. (Faz 10)

    Stratejinin bildirdiği özellikler **her enstrüman için ayrı ayrı** hesaplanır. Ortak
    hesaplanamazlar: indikatörler nedensel ve seriye özgü; bir sembolün SMA'sını başka bir
    sembolün barlarından üretmek, cross-sectional bir karşılaştırmayı anlamsız kılar.

    Isınma penceresi enstrüman başına kendi barlarından doğar: geç listelenmiş bir sembol,
    kendi ilk barından itibaren ısınır ve o süre boyunca `ctx.hazir(...)` `False` döner.

    **Özellikler yalnızca var olan barlar üzerinde hesaplanır** (`ozellikleri_hesapla`).
    Faz 12'de ölçüldü: ızgara doldurma barlarının NaN'ı Wilder yumuşatmasına (ATR) girince
    NaN **kalıcı** oluyordu — pencere başladıktan sonra listelenen ya da arada boşluğu
    olan her sembolün ATR'si sonsuza kadar NaN'dı ve o sembol hiçbir zaman aday olamadı.
    Sessiz bir evren daraltması, yani K-052/3'ün yasakladığı yanlılığın ters yönden hâli.
    """
    gorunumler = {
        sembol: PiyasaGorunumu(
            sembol=sembol,
            timeframe=timeframe,
            barlar=dict(diziler),
            ozellikler=ozellikleri_hesapla(diziler, strateji.ozellikler()),
        )
        for sembol, diziler in sorted(bar_dizileri.items())
    }
    return EvrenGorunumu(
        timeframe=timeframe,
        zamanlar=next(iter(gorunumler.values())).barlar["open_time"],
        gorunumler=gorunumler,
        uyelik={s: np.asarray(d, dtype=bool) for s, d in uyelik.items()},
        kural_kimligi=kural_kimligi,
    )
