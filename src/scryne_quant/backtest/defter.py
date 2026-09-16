"""İşlem defteri: bir emrin portföye ve tur kaydına işlenmesi. (K-001, Faz 3/6 ortak)

Bu fonksiyon Faz 3'te `Backtest._uygula` olarak doğdu ve Faz 6'da buraya taşındı. Sebep
K-001: *"backtest = paper = live, tek kod yolu."* Paper döngüsü de bir emri portföye
uygulayıp turu kapatmak zorunda, ve o mantığın ikinci bir kopyası şu üç şeyin ikiye
ayrılması demek olurdu: ortalama maliyet, tur muhasebesi, ve cooldown'ı tetikleyen
"kapanan tur" tanımı. Üçünün de sessizce ayrışması mümkün, üçü de sonucu "biraz farklı"
yapar.

Ayrı bir modül olmasının sebebi ise import yönü: `live/` bu mantığı `backtest.motor`dan
alsaydı, canlı döngü koca bir `Backtest` sınıfını import etmek zorunda kalırdı.
"""

from __future__ import annotations

from scryne_quant.backtest.fill import Emir, IslemYonu
from scryne_quant.backtest.metrikler import Islem
from scryne_quant.portfolio.durum import CokluPortfoy, Portfoy
from scryne_quant.risk.motor import RiskMotoru


class DefterHatasi(ValueError):
    """İşlem defteri tutarsız bir duruma sokuldu."""


def uygula(
    emir: Emir,
    portfoy: Portfoy,
    acik: Islem | None,
    islemler: list[Islem],
    *,
    risk: RiskMotoru | None = None,
) -> tuple[Portfoy, Islem | None, Islem | None]:
    """Emri portföye uygular ve tur defterini günceller.

    Döner: `(yeni portföy, hâlâ açık tur, bu emirle **kapanan** tur)`. Üçüncü değer
    çağıranın kayda geçireceği şey: bir tur kapandığında gerçekleşen P&L ancak orada
    bellidir.

    Bir "işlem" düzden düze bir pozisyon turudur: ilk alımda açılır, pozisyon sıfıra
    döndüğünde kapanır. Aradaki her fill aynı turun içindedir.
    """
    if emir.yon is IslemYonu.AL:
        if acik is None:
            acik = Islem(acilis_ms=emir.zaman_ms)
            islemler.append(acik)
        portfoy = portfoy.al(emir.miktar, emir.fiyat, emir.komisyon, emir.zaman_ms)
        acik.giris_notional += emir.notional
        acik.giris_miktar += emir.miktar
    else:
        if acik is None:  # pragma: no cover - pozisyon yokken satış emri üretilmez
            raise DefterHatasi("açık işlem yokken satış emri")
        portfoy, gerceklesen = portfoy.sat(emir.miktar, emir.fiyat, emir.komisyon)
        acik.cikis_notional += emir.notional
        acik.cikis_miktar += emir.miktar
        acik.net_pnl += gerceklesen

    acik.komisyon += emir.komisyon
    acik.slippage += emir.slippage_maliyeti
    acik.fill_sayisi += 1

    kapanan: Islem | None = None
    if not portfoy.acik:
        acik.kapanis_ms = emir.zaman_ms
        # Risk motorunun ardışık kayıp sayacı kapanmış **turları** sayar, fill'leri
        # değil: bir pozisyonu iki taksitte kapatmak iki kayıp olarak sayılsaydı
        # cooldown limiti sessizce yarıya inerdi.
        if risk is not None:
            risk.islem_kapandi(acik.net_pnl, emir.zaman_ms)
        kapanan, acik = acik, None
    return portfoy, acik, kapanan


def uygula_coklu(
    emir: Emir,
    portfoy: CokluPortfoy,
    acik: dict[str, Islem],
    islemler: list[Islem],
    *,
    risk: RiskMotoru | None = None,
) -> tuple[CokluPortfoy, Islem | None]:
    """`uygula`nın çok enstrümanlı hâli: tur defteri sembol başına tutulur. (Faz 10)

    Döner: `(yeni portföy, bu emirle kapanan tur)`. `acik` sözlüğü **yerinde** güncellenir —
    tek sembollü hâlde tek bir `Islem | None` taşımakla aynı şey, sembol başına.

    Turun tanımı değişmiyor: ilk alımda açılır, o sembolün pozisyonu sıfıra döndüğünde
    kapanır. Bir sembolün turu başka bir sembolün pozisyonundan etkilenmez; portföy düzeyi
    kararları `Islem` değil `Metrikler` ölçüyor.
    """
    sembol = emir.sembol
    if not sembol:
        raise DefterHatasi("çok enstrümanlı defterde sembolsüz emir")

    if emir.yon is IslemYonu.AL:
        tur = acik.get(sembol)
        if tur is None:
            tur = Islem(acilis_ms=emir.zaman_ms, sembol=sembol)
            acik[sembol] = tur
            islemler.append(tur)
        portfoy = portfoy.al(sembol, emir.miktar, emir.fiyat, emir.komisyon, emir.zaman_ms)
        tur.giris_notional += emir.notional
        tur.giris_miktar += emir.miktar
    else:
        tur = acik.get(sembol)
        if tur is None:  # pragma: no cover - pozisyon yokken satış emri üretilmez
            raise DefterHatasi(f"{sembol}: açık işlem yokken satış emri")
        portfoy, gerceklesen = portfoy.sat(sembol, emir.miktar, emir.fiyat, emir.komisyon)
        tur.cikis_notional += emir.notional
        tur.cikis_miktar += emir.miktar
        tur.net_pnl += gerceklesen

    tur.komisyon += emir.komisyon
    tur.slippage += emir.slippage_maliyeti
    tur.fill_sayisi += 1

    kapanan: Islem | None = None
    if not portfoy.pozisyon(sembol).acik:
        tur.kapanis_ms = emir.zaman_ms
        if risk is not None:
            risk.islem_kapandi(tur.net_pnl, emir.zaman_ms)
        kapanan = tur
        acik.pop(sembol, None)
    return portfoy, kapanan


__all__ = ["DefterHatasi", "uygula", "uygula_coklu"]
