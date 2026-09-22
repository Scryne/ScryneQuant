"""Canlı adaptör: geçerli yetkiyle, sahte taşıma üzerinde emir yolunun tamamı. (K-114)

**Gerçek ağa çıkılmaz, gerçek emir yoktur.** Taşıma sahtedir; ölçülen şey canlı kurulumun
(host, imza, yetki) testnet kurulumuyla aynı emir sözleşmesini taşıdığıdır: istek canlı host'a
gider, kısmi dolum `PARTIALLY_FILLED`, açık red `REJECTED`, 5xx `UNKNOWN` olur ve mutabakat onu
borsaya sorarak çözer; duplicate kimlik ikinci kez ağa çıkmaz.
"""

from __future__ import annotations

import json
from typing import Any

from scryne_quant.exchange import yetki
from scryne_quant.exchange.canli import CANLI_HOST, canli_emir_adaptoru
from scryne_quant.execution.motor import EmirMotoru
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.oms.emir import EmirDurumu
from scryne_quant.oms.mutabakat import mutabakat
from scryne_quant.risk.niyet import onayla
from scryne_quant.strategy.sinyal import Sinyal, Yon

T0 = 1_699_999_200_000
BILGI = {"symbols": [{"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC",
                      "quoteAsset": "USDT", "filters": [
                          {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                          {"filterType": "LOT_SIZE", "stepSize": "0.00001", "minQty": "0.00001",
                           "maxQty": "9000"},
                          {"filterType": "MARKET_LOT_SIZE", "stepSize": "0", "maxQty": "120"},
                          {"filterType": "NOTIONAL", "minNotional": "5", "maxNotional": "9000000"},
                      ]}]}


class Y:
    def __init__(self, durum: int, govde: Any) -> None:
        self.status_code, self._g, self.headers = durum, govde, {}
        self.text = json.dumps(govde)

    def json(self) -> Any:
        return self._g


class Borsa:
    """Canlı Binance'i taklit eden sahte taşıma: emir yanıtları sıradan verilir."""

    def __init__(self, *emir_yanitlari: Any, sorgu: Any = None) -> None:
        self.emir = list(emir_yanitlari)
        self.sorgu = sorgu
        self.istekler: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **_: Any) -> Any:
        self.istekler.append((method, url))
        if "/api/v3/time" in url:
            return Y(200, {"serverTime": T0 + 3_600_000})
        if "exchangeInfo" in url:
            return Y(200, BILGI)
        if "ticker/price" in url:
            return Y(200, {"price": "50000"})
        if method == "POST":
            return self.emir.pop(0)
        if "openOrders" in url:
            return Y(200, [])
        if method == "GET" and "/api/v3/order" in url:
            return self.sorgu
        raise AssertionError(url)


def niyet(sebep="TEST"):
    return onayla(
        sinyal=Sinyal(symbol="BTCUSDT", side=Yon.BUY, target_exposure=0.2, confidence=0.9,
                      reason=sebep, timestamp=T0),
        onayli_maruziyet=0.2, limit_kimligi="k" * 64, karar_ms=T0,
    )


def adaptor(b: Borsa):
    y = yetki.ver(host=CANLI_HOST, kanit_hash="k", onay_hash="o", strateji="s",
                  kademe=1, sermaye_usdt=200.0)
    return canli_emir_adaptoru(y, "anahtar", "sir", oturum=b)


def govde(durum: str, dolan: str = "0", kimlik: str = "") -> dict:
    return {"symbol": "BTCUSDT", "orderId": 7, "clientOrderId": kimlik, "side": "BUY",
            "status": durum, "origQty": "0.002", "executedQty": dolan,
            "cummulativeQuoteQty": str(float(dolan) * 50_000), "transactTime": T0 + 1,
            "fills": ([{"commission": "0.0000001", "commissionAsset": "BTC"}]
                      if float(dolan) else [])}


def test_kismi_dolum_canli_host_ve_duplicate_aga_cikmaz():
    b = Borsa(Y(200, govde("PARTIALLY_FILLED", "0.001")))
    d = EmirDefteri()
    s = EmirMotoru(d, adaptor(b)).gonder(niyet(), 0.002)
    assert s.emir.durum is EmirDurumu.PARTIALLY_FILLED and s.emir.dolan_miktar == 0.001
    post = [u for m, u in b.istekler if m == "POST"]
    assert len(post) == 1 and post[0].startswith(CANLI_HOST + "/api/v3/order?")
    assert "signature=" in post[0]
    tekrar = EmirMotoru(d, adaptor(b)).gonder(niyet(), 0.002)
    assert not tekrar.gonderildi and len([m for m, _ in b.istekler if m == "POST"]) == 1


def test_red_rejected():
    b = Borsa(Y(400, {"code": -2010, "msg": "Account has insufficient balance"}))
    s = EmirMotoru(EmirDefteri(), adaptor(b)).gonder(niyet(), 0.002)
    assert s.emir.durum is EmirDurumu.REJECTED


def test_5xx_belirsiz_mutabakat_borsaya_sorarak_cozer():
    d = EmirDefteri()
    b = Borsa(Y(503, {"code": -1001, "msg": "unknown"}))
    a = adaptor(b)
    s = EmirMotoru(d, a).gonder(niyet(), 0.002)
    assert s.emir.durum is EmirDurumu.UNKNOWN
    b.sorgu = Y(200, {**govde("FILLED", "0.002", s.emir.istemci_kimligi), "updateTime": T0 + 2})
    sonuc = mutabakat(d, a, "BTCUSDT")
    assert not sonuc.halt and d.al(s.emir.istemci_kimligi).durum is EmirDurumu.FILLED


def test_market_lot_tavani_yerelde_reddedilir():
    b = Borsa()
    s = EmirMotoru(EmirDefteri(), adaptor(b)).gonder(niyet(), 200.0)  # > MARKET_LOT_SIZE 120
    assert s.emir.durum is EmirDurumu.REJECTED and "marketMaxQty" in s.emir.hata
    assert not [m for m, _ in b.istekler if m == "POST"]
