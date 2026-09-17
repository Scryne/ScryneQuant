"""Izgara barı toplayıcı: hazır olma, zaman aşımı, sıra ve geç bar. (Faz 14)"""

from __future__ import annotations

import pytest

from scryne_quant.live.akis import Bar
from scryne_quant.live.izgara_toplayici import IzgaraToplayici, ToplayiciHatasi

SAAT = 3_600_000
T0 = 1_699_999_200_000


def bar(t: int) -> Bar:
    return Bar(open_time=t, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0,
               quote_volume=1.0, trades=1)


def toplayici(beklenen=("A", "B")):
    return IzgaraToplayici("1h", beklenen=lambda t: beklenen, bekleme_ms=120_000)


def test_hepsi_gelince_kapanista_hazir():
    tp = toplayici()
    tp.bar_ekle("A", bar(T0))
    assert tp.hazir(T0 + SAAT + 1) == []  # B yok, süre dolmadı
    tp.bar_ekle("B", bar(T0))
    [ib] = tp.hazir(T0 + SAAT + 1)
    assert ib.open_time == T0 and set(ib.barlar) == {"A", "B"} and ib.eksik == ()
    assert not ib.zaman_asimi


def test_kapanis_gelmeden_teslim_yok():
    tp = toplayici()
    tp.bar_ekle("A", bar(T0))
    tp.bar_ekle("B", bar(T0))
    assert tp.hazir(T0 + SAAT - 1) == []


def test_sure_dolunca_eksikle_teslim():
    tp = toplayici()
    tp.bar_ekle("A", bar(T0))
    assert tp.hazir(T0 + SAAT + 119_999) == []
    [ib] = tp.hazir(T0 + SAAT + 120_000)
    assert ib.eksik == ("B",) and ib.zaman_asimi and set(ib.barlar) == {"A"}


def test_sira_atlanmaz_ve_bosluklu_bar_sure_dolunca_bos_teslim():
    tp = toplayici()
    tp.bar_ekle("A", bar(T0))
    tp.bar_ekle("B", bar(T0))
    assert [b.open_time for b in tp.hazir(T0 + SAAT)] == [T0]
    # t+1 hiç gelmedi, t+2 tam geldi: t+1 süre dolmadan t+2 teslim edilmez.
    tp.bar_ekle("A", bar(T0 + 2 * SAAT))
    tp.bar_ekle("B", bar(T0 + 2 * SAAT))
    # t+1 kapanışı T0+2h, beklemesi T0+2h+120 s'de doluyor; ondan önce hiçbir şey teslim edilmez.
    assert tp.hazir(T0 + 2 * SAAT + 60_000) == []
    teslim = tp.hazir(T0 + 3 * SAAT)
    assert [b.open_time for b in teslim] == [T0 + SAAT, T0 + 2 * SAAT]
    assert teslim[0].eksik == ("A", "B") and teslim[1].eksik == ()


def test_gec_bar_kaydedilir_gecmisi_degistirmez():
    tp = toplayici()
    tp.bar_ekle("A", bar(T0))
    [ib] = tp.hazir(T0 + SAAT + 120_000)
    gec = tp.bar_ekle("B", bar(T0))
    assert gec is not None and gec.sembol == "B" and gec.teslim_edilen == T0
    assert tp.gec_barlar == [gec]
    assert set(ib.barlar) == {"A"}


def test_hizasiz_bar_reddedilir():
    with pytest.raises(ToplayiciHatasi):
        toplayici().bar_ekle("A", bar(T0 + 1))


def test_toparlanmada_son_teslimden_devam():
    tp = IzgaraToplayici("1h", beklenen=lambda t: ("A",), son_teslim=T0)
    tp.bar_ekle("A", bar(T0))  # zaten işlenmiş: geç bar
    tp.bar_ekle("A", bar(T0 + SAAT))
    [ib] = tp.hazir(T0 + 2 * SAAT)
    assert ib.open_time == T0 + SAAT
    assert len(tp.gec_barlar) == 1


def test_beklenen_zamana_gore_degisir():
    uyeler = {T0: ("A",), T0 + SAAT: ("A", "B")}
    tp = IzgaraToplayici("1h", beklenen=lambda t: uyeler.get(t, ()))
    tp.bar_ekle("A", bar(T0))
    tp.bar_ekle("A", bar(T0 + SAAT))
    assert [b.open_time for b in tp.hazir(T0 + 2 * SAAT)] == [T0]  # T0+1h B'yi bekliyor
