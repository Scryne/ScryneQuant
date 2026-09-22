"""Hız sınırı (429/418, ağırlık başlıkları) ve shadow adaptörünün katmanları. (K-114)"""

from __future__ import annotations

import json
from typing import Any

import pytest

from scryne_quant.exchange import imzali
from scryne_quant.exchange.golge import GolgeAdaptoru, GolgeGonderim
from scryne_quant.exchange.hatalar import GonderilemediHatasi
from scryne_quant.exchange.imzali import BinanceImzaliAdaptoru, HizSiniri
from scryne_quant.exchange.kurallar import SembolKurallari
from scryne_quant.exchange.paper_adaptoru import PaperBorsa, PaperMaliyet


class Yanit:
    def __init__(self, durum: int, govde: Any, basliklar: dict | None = None) -> None:
        self.status_code = durum
        self._g = govde
        self.text = json.dumps(govde)
        self.headers = basliklar or {}

    def json(self) -> Any:
        return self._g


class Transport:
    def __init__(self, *cevaplar: Any) -> None:
        self.cevaplar = list(cevaplar)
        self.istekler: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **_: Any) -> Any:
        self.istekler.append((method, url))
        if "/api/v3/time" in url:
            return Yanit(200, {"serverTime": 1_800_000_000_000})
        return self.cevaplar.pop(0)


def adaptor(t: Transport) -> BinanceImzaliAdaptoru:
    return BinanceImzaliAdaptoru(anahtar="a", sir="b", oturum=t, ipv4=False)


def test_okumada_429_retry_after_kadar_bekleyip_yeniden_dener(monkeypatch):
    uykular: list[float] = []
    monkeypatch.setattr(imzali.time, "sleep", uykular.append)
    t = Transport(Yanit(429, {"code": -1003, "msg": "Too many"}, {"Retry-After": "2"}),
                  Yanit(200, {"price": "50000"}))
    assert adaptor(t).son_fiyat("BTCUSDT") == 50_000.0
    assert 2.0 in uykular


def test_418_yasak_yeniden_denenmez(monkeypatch):
    monkeypatch.setattr(imzali.time, "sleep", lambda s: None)
    t = Transport(Yanit(418, {"code": -1003, "msg": "banned"}, {"Retry-After": "120"}))
    with pytest.raises(HizSiniri) as e:
        adaptor(t).son_fiyat("BTCUSDT")
    assert e.value.yasak


def test_agirlik_sinira_yakinsa_yazma_gonderilmez(monkeypatch):
    monkeypatch.setattr(imzali.time, "sleep", lambda s: None)
    t = Transport(Yanit(200, {"price": "1"}, {"X-MBX-USED-WEIGHT-1M": "5900"}))
    a = adaptor(t)
    a.son_fiyat("BTCUSDT")
    assert a.hiz.agirlik == 5900
    a._kural_onbellek["BTCUSDT"] = SembolKurallari(
        "BTCUSDT", 0.01, 0.00001, 5.0, "TRADING", "BTC", "USDT")
    oncesi = len(t.istekler)
    with pytest.raises(GonderilemediHatasi, match="hız sınırı"):
        a.market_emri(istemci_kimligi="x", sembol="BTCUSDT", yon="BUY", miktar=0.001)
    assert [m for m, _ in t.istekler[oncesi:] if m == "POST"] == []


def test_golge_yazmayi_reddeder_okumayi_delege_eder():
    k = SembolKurallari("BTCUSDT", 0.01, 0.00001, 5.0, "TRADING", "BTC", "USDT")
    b = PaperBorsa(kurallar={"BTCUSDT": k}, maliyet=PaperMaliyet(0, 0), saat=lambda: 1,
                   acilis_bakiyesi={"USDT": 5.0})
    b.fiyat_bildir("BTCUSDT", 100.0, 1)
    g = GolgeAdaptoru(b)
    assert g.son_fiyat("BTCUSDT") == 100.0 and g.bakiye()["USDT"].toplam == 5.0
    for cagri in (lambda: g.market_emri(istemci_kimligi="x", sembol="BTCUSDT", yon="BUY",
                                        miktar=1),
                  lambda: g.limit_emri(istemci_kimligi="x", sembol="BTCUSDT", yon="BUY",
                                       miktar=1, fiyat=1),
                  lambda: g.emir_iptal(sembol="BTCUSDT", istemci_kimligi="x")):
        with pytest.raises(GolgeGonderim):
            cagri()


def test_golge_yazabilen_gercek_adaptorle_kurulamaz():
    with pytest.raises(GolgeGonderim):
        GolgeAdaptoru(adaptor(Transport()))  # testnet adaptörü, salt okunur değil
