"""Public veri adaptörü: ağ hatasında yedek uca geçer. (K-122)

Gösterim öncesi ölçüm: `testnet-surekli-1` 10 saatte 107 döngüde `data-api` `/time`a 5 denemede
ulaşamadı. Tek uca bağımlılık kalktı; aynı veri `api.binance.com`/`api-gcp` üzerinden de okunur.
"""

from __future__ import annotations

import ccxt
import pytest

from scryne_quant.exchange import binance as b


@pytest.fixture(autouse=True)
def _uyuma(monkeypatch):
    monkeypatch.setattr(b.time, "sleep", lambda s: None)


def _cagri(adaptor, hatalar):
    """İlk `hatalar` çağrıda NetworkError; her çağrıda o anki public URL'yi kaydeder."""
    gorulen: list[str] = []

    def cagri():
        gorulen.append(adaptor._borsa.urls["api"]["public"])
        if len(gorulen) <= hatalar:
            raise ccxt.NetworkError("bağlantı yok")
        return {"serverTime": 1}

    return cagri, gorulen


def test_ag_hatasinda_siradaki_uca_gecer_ve_orada_kalir():
    a = b.BinanceAdaptoru()
    cagri, gorulen = _cagri(a, 2)
    assert a._dene("t", cagri) == {"serverTime": 1}
    assert gorulen == [f"{h}/api/v3" for h in b.YEDEK_HOSTLAR]
    assert a._borsa.urls["api"]["public"] == f"{b.YEDEK_HOSTLAR[2]}/api/v3"


def test_acik_verilen_host_yedege_gecmez():
    a = b.BinanceAdaptoru(host="https://testnet.binance.vision", deneme_sayisi=3)
    cagri, gorulen = _cagri(a, 99)
    with pytest.raises(b.BorsaHatasi):
        a._dene("t", cagri)
    assert set(gorulen) == {"https://testnet.binance.vision/api/v3"}


def test_hiz_siniri_uc_degistirmez():
    a = b.BinanceAdaptoru(deneme_sayisi=2)
    gorulen: list[str] = []

    def cagri():
        gorulen.append(a._borsa.urls["api"]["public"])
        raise ccxt.RateLimitExceeded("429")

    with pytest.raises(b.BorsaHatasi):
        a._dene("t", cagri)
    assert set(gorulen) == {f"{b.VERI_HOST}/api/v3"}
