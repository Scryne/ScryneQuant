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
from scryne_quant.portfolio.durum import Portfoy
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


__all__ = ["DefterHatasi", "uygula"]
