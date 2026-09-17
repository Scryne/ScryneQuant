"""`BinanceCokluBarAkisi`: birleşik akış, sembol başına süzme, kopma ve resync. (Faz 14)

Tek sembollü akışın davranış testlerinin (`test_borsa_akisi.py`) çok sembollü karşılığı;
aynı dar sahte oturum kullanılıyor.
"""

from __future__ import annotations

import asyncio
import json

import aiohttp
import pytest

from scryne_quant.exchange import coklu_akis as coklu_mod
from scryne_quant.exchange.coklu_akis import BinanceCokluBarAkisi
from scryne_quant.live.akis import AkisHatasi, Kaynak
from tests.unit.test_borsa_akisi import ADIM, T0, SahteAdaptor, SahteMesaj, SahteOturum


def mesaj(sembol: str, acilis_ms: int, *, kapandi: bool = True) -> SahteMesaj:
    veri = {"e": "kline", "s": sembol, "k": {
        "t": acilis_ms, "o": "1.0", "c": "1.1", "h": "1.2", "l": "0.9", "v": "10",
        "q": "11", "n": 5, "x": kapandi}}
    return SahteMesaj(aiohttp.WSMsgType.TEXT,
                      json.dumps({"stream": f"{sembol.lower()}@kline_1h", "data": veri}))


@pytest.fixture
def uykusuz(monkeypatch):
    kayit: list[float] = []

    async def sahte_uyku(saniye: float) -> None:
        kayit.append(saniye)

    monkeypatch.setattr(coklu_mod.asyncio, "sleep", sahte_uyku)
    return kayit


def topla(akis, adet):
    async def _():
        sonuc = []
        async for oge in akis.barlar():
            sonuc.append(oge)
            if len(sonuc) >= adet:
                akis.kapat()
                break
        return sonuc

    return asyncio.run(_())


def kur(oturumlar, semboller=("BTCUSDT", "ETHUSDT"), **kw):
    oturum = SahteOturum(oturumlar)
    return BinanceCokluBarAkisi(semboller, "1h", oturum=oturum, **kw), oturum


def test_url_birlesik_ve_sirali():
    akis, _ = kur([], semboller=("ethusdt", "BTCUSDT"))
    assert akis.url.endswith("?streams=btcusdt@kline_1h/ethusdt@kline_1h")


def test_bos_sembol_listesi_reddedilir():
    with pytest.raises(AkisHatasi):
        BinanceCokluBarAkisi([], "1h")


def test_sembol_basina_teslim_ve_suzme(uykusuz):
    nabizlar = []
    akis, _ = kur([[
        mesaj("BTCUSDT", T0), mesaj("ETHUSDT", T0, kapandi=False), mesaj("ETHUSDT", T0),
        mesaj("BTCUSDT", T0),            # aynı bar ikinci kez: süzülür
        mesaj("XRPUSDT", T0),            # abone olunmayan sembol: süzülür
        mesaj("BTCUSDT", T0 + ADIM),
    ]], nabiz_kancasi=nabizlar.append)
    sonuc = topla(akis, 3)
    assert [(s, b.open_time) for s, b in sonuc] == [
        ("BTCUSDT", T0), ("ETHUSDT", T0), ("BTCUSDT", T0 + ADIM)]
    assert len(nabizlar) >= 5  # kapanmamış bar ve süzülen mesajlar da nabız


def test_kopmada_sembol_basina_resync_backfill(uykusuz):
    adaptor = SahteAdaptor([T0 + ADIM, T0 + 2 * ADIM])
    kopmalar, donusler = [], []
    akis, _ = kur(
        [[mesaj("BTCUSDT", T0), mesaj("ETHUSDT", T0)],  # sonra kapanır → kopma
         [mesaj("BTCUSDT", T0 + 3 * ADIM)]],
        adaptor=adaptor, kopma_kancasi=kopmalar.append,
        yeniden_baglanma_kancasi=donusler.append,
    )
    sonuc = topla(akis, 7)
    backfill = [(s, b.open_time) for s, b in sonuc if b.kaynak is Kaynak.BACKFILL]
    assert sorted(backfill) == [("BTCUSDT", T0 + ADIM), ("BTCUSDT", T0 + 2 * ADIM),
                                ("ETHUSDT", T0 + ADIM), ("ETHUSDT", T0 + 2 * ADIM)]
    assert len(adaptor.cagrilar) == 2 and all(c[0] == T0 + ADIM for c in adaptor.cagrilar)
    assert len(kopmalar) == 1 and donusler[0]["resync_bar"] == 4
    assert uykusuz == [1.0]


def test_toparlanmada_son_teslimden_devam(uykusuz):
    akis, _ = kur([[mesaj("BTCUSDT", T0), mesaj("BTCUSDT", T0 + ADIM)]],
                  semboller=("BTCUSDT",), son_teslim={"BTCUSDT": T0})
    [(s, b)] = topla(akis, 1)
    assert b.open_time == T0 + ADIM
