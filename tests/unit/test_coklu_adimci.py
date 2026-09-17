"""Tek kod yolu: backtest döngüsü ile bar bar besleme aynı sonucu verir. (Faz 14, K-001)

`CokluAdimci` hem `CokluBacktest.calistir`ın döngüsünü hem de canlı paper motorunu taşıyacak.
Kabul (tasarım §1b): geçmiş barları **tek tek**, her adımda yalnızca o ana kadarki barlarla
kurulmuş (büyüyen) bir görünümle beslemek, tüm seriyle koşan backtest'le **bit düzeyinde**
aynı özkaynak eğrisini, maruziyeti ve işlemleri üretir.

Büyüyen görünüm bilinçli: stratejiler yeniden dengeleme takvimini `ctx.uzunluk`la sayıyor;
kayan pencerede o sayı sabit kalır ve takvim bozulurdu. Canlı motor bu yüzden koşu başından
beri gelen barların tamamını tutar ve yeniden başlatmada onları yeniden oynatır (K-038).
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.backtest.coklu_motor import CokluAdimci, CokluBacktest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.strategy.evren import LISTELENMEDI
from scryne_quant.strategy.kosu import evren_gorunum_kur
from scryne_quant.strategy.kutuphane import EvrenEsitAgirlik, KesitselGuc
from tests.conftest import bar_uret

MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
SEMBOLLER = ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT")
N = 1_200


def _diziler():
    diziler = {
        s: {a: np.array(x, copy=True) for a, x in bar_dizileri(bar_uret(n=N, tohum=91 + i)).items()}
        for i, s in enumerate(SEMBOLLER)
    }
    # DDD geç listeleniyor, CCC ortada delist oluyor: mevcut olmayan barlar da yoldan geçsin.
    for s, dilim in (("DDDUSDT", slice(0, 300)), ("CCCUSDT", slice(900, N))):
        d = diziler[s]
        for ad in ("open", "high", "low", "close", "volume", "quote_volume"):
            d[ad][dilim] = np.nan
        d["trades"][dilim] = 0
        q = d["quality_status"].astype(object)
        q[dilim] = LISTELENMEDI
        d["quality_status"] = q
    uyelik = {s: np.ones(N, dtype=bool) for s in SEMBOLLER}
    uyelik["DDDUSDT"][:300] = False
    uyelik["CCCUSDT"][900:] = False
    return diziler, uyelik


def _strateji(ad):
    if ad == "kiyas":
        return EvrenEsitAgirlik(yeniden_dengele_bar=24, azami_enstruman=3, azami_agirlik=0.2 / 3,
                                hedef_brut=0.2)
    return KesitselGuc(pencere=48, azami_enstruman=2, yeniden_dengele_bar=24)


@pytest.mark.parametrize("ad", ["kiyas", "kesitsel"])
@pytest.mark.parametrize("sifira", [None, 12])
def test_bar_bar_besleme_backtestle_bit_duzeyinde_ayni(ad, sifira):
    diziler, uyelik = _diziler()
    olcum = 60

    tam = evren_gorunum_kur("1h", diziler, uyelik, _strateji(ad))
    motor = CokluBacktest(_strateji(ad), MALIYET, sifira_yaz_bar=sifira)
    beklenen = motor.calistir(tam, olcum_baslangici=olcum)

    canli = CokluBacktest(_strateji(ad), MALIYET, sifira_yaz_bar=sifira)
    adimci = CokluAdimci(canli)
    ozkaynak, brut = [], []
    # Canlı motor stratejinin ısınması kadar barla başlar: ilk `W` bar tek görünümle oynatılır,
    # sonrası her yeni barda o ana kadarki barlarla kurulan büyüyen görünümle.
    w = canli.strateji.isinma_bar()
    girdi = None
    for t in range(N):
        if t < w and girdi is not None:
            pass
        else:
            son = max(t + 1, w)
            on = {s: {a: x[:son] for a, x in d.items()} for s, d in diziler.items()}
            onu = {s: u[:son] for s, u in uyelik.items()}
            girdi = canli.girdi_kur(evren_gorunum_kur("1h", on, onu, canli.strateji))
        o, b = adimci.adim(girdi, t, isinma=t < olcum, son_bar=t == N - 1)
        ozkaynak.append(o)
        brut.append(b)

    assert np.asarray(ozkaynak[olcum:]).tobytes() == beklenen.ozkaynak.tobytes()
    assert np.asarray(brut[olcum:]).tobytes() == beklenen.maruziyet.tobytes()
    assert [i.sozluk(sembol_yaz=True) for i in adimci.islemler] == [
        i.sozluk(sembol_yaz=True) for i in beklenen.islemler
    ]
    assert beklenen.islemler and beklenen.metrikler.azami_maruziyet > 0  # boş koşu değil
