"""Paper borsa: gerçek emir yolunun simüle karşı tarafı. (K-114)

Ölçülen iddialar: fill sonraki barın açılışında (K-004), slippage aleyhte (K-007), komisyon
kote varlıktan ve `fills`le döner, duplicate kimlik reddedilir (-2010), yetersiz bakiye
reddedilir, iptal kilidi geri verir, durum diskte kalır (yeniden açılan borsa aynı).
"""

from __future__ import annotations

import pytest

from scryne_quant.exchange.hatalar import BorsaReddetti
from scryne_quant.exchange.kurallar import SembolKurallari
from scryne_quant.exchange.paper_adaptoru import PaperBorsa, PaperHatasi, PaperMaliyet
from scryne_quant.oms.emir import EmirDurumu

K = SembolKurallari("BTCUSDT", 0.01, 0.00001, 5.0, "TRADING", "BTC", "USDT")
T0 = 1_700_000_000_000


class Saat:
    def __init__(self) -> None:
        self.t = T0

    def __call__(self) -> int:
        return self.t


def borsa(tmp_path=None, **kw) -> PaperBorsa:
    saat = kw.pop("saat", Saat())
    return PaperBorsa(
        kurallar={"BTCUSDT": K},
        maliyet=kw.pop("maliyet", PaperMaliyet(10.0, 5.0)),
        saat=saat,
        yol=(tmp_path / "pb.sqlite") if tmp_path else ":memory:",
        acilis_bakiyesi=kw.pop("acilis", {"USDT": 10_000.0}),
        **kw,
    )


def test_market_emri_sonraki_acilista_dolar_aleyhte_slippage():
    b = borsa()
    b.fiyat_bildir("BTCUSDT", 50_000.0, T0)
    y = b.market_emri(istemci_kimligi="a1", sembol="BTCUSDT", yon="BUY", miktar=0.01)
    assert y.durum is EmirDurumu.ACKNOWLEDGED and y.dolan_miktar == 0.0
    b.bar_acilisi("BTCUSDT", 51_000.0, T0 + 3_600_000)
    s = b.emir_sorgula(sembol="BTCUSDT", istemci_kimligi="a1")
    assert s.durum is EmirDurumu.FILLED
    assert s.ortalama_fiyat == pytest.approx(51_000.0 * (1 + 5e-4))
    kom = b.emir_islemleri(sembol="BTCUSDT", borsa_kimligi=s.borsa_kimligi)
    assert kom == (("USDT", pytest.approx(0.01 * 51_000.0 * 1.0005 * 1e-3)),)
    bak = b.bakiye()
    assert bak["BTC"].toplam == pytest.approx(0.01)
    assert bak["USDT"].kilitli == pytest.approx(0.0)
    assert bak["USDT"].toplam == pytest.approx(10_000 - 0.01 * 51_025.5 * 1.001)


def test_satis_aleyhte_ve_komisyon_kote():
    b = borsa(acilis={"USDT": 0.0, "BTC": 1.0})
    b.fiyat_bildir("BTCUSDT", 50_000.0, T0)
    b.market_emri(istemci_kimligi="s1", sembol="BTCUSDT", yon="FLAT", miktar=0.5)
    b.bar_acilisi("BTCUSDT", 40_000.0, T0 + 1)
    s = b.emir_sorgula(sembol="BTCUSDT", istemci_kimligi="s1")
    assert s.ortalama_fiyat == pytest.approx(40_000 * (1 - 5e-4))
    assert b.bakiye()["USDT"].toplam == pytest.approx(0.5 * 39_980 * (1 - 1e-3))


def test_duplicate_kimlik_reddedilir():
    b = borsa()
    b.fiyat_bildir("BTCUSDT", 50_000.0, T0)
    b.market_emri(istemci_kimligi="d", sembol="BTCUSDT", yon="BUY", miktar=0.001)
    with pytest.raises(BorsaReddetti) as e:
        b.market_emri(istemci_kimligi="d", sembol="BTCUSDT", yon="BUY", miktar=0.001)
    assert e.value.kod == -2010


def test_yetersiz_bakiye_reddedilir_ve_bakiye_degismez():
    b = borsa(acilis={"USDT": 100.0})
    b.fiyat_bildir("BTCUSDT", 50_000.0, T0)
    with pytest.raises(BorsaReddetti):
        b.market_emri(istemci_kimligi="x", sembol="BTCUSDT", yon="BUY", miktar=0.01)
    assert b.bakiye()["USDT"].serbest == pytest.approx(100.0)
    assert b.emir_sorgula(sembol="BTCUSDT", istemci_kimligi="x") is None


def test_iptal_kilidi_geri_verir_ve_ikinci_iptal_none():
    b = borsa()
    b.fiyat_bildir("BTCUSDT", 50_000.0, T0)
    b.market_emri(istemci_kimligi="c", sembol="BTCUSDT", yon="BUY", miktar=0.01)
    assert b.bakiye()["USDT"].kilitli > 0
    y = b.emir_iptal(sembol="BTCUSDT", istemci_kimligi="c")
    assert y.durum is EmirDurumu.CANCELED
    assert b.bakiye()["USDT"].serbest == pytest.approx(10_000.0)
    assert b.emir_iptal(sembol="BTCUSDT", istemci_kimligi="c") is None
    assert b.acik_emirler("BTCUSDT") == []


def test_limit_emri_yalniz_gecince_dolar():
    b = borsa()
    b.fiyat_bildir("BTCUSDT", 50_000.0, T0)
    b.limit_emri(istemci_kimligi="l", sembol="BTCUSDT", yon="BUY", miktar=0.01, fiyat=49_000.0)
    b.bar_acilisi("BTCUSDT", 49_500.0, T0 + 1)
    assert b.emir_sorgula(sembol="BTCUSDT", istemci_kimligi="l").durum is EmirDurumu.ACKNOWLEDGED
    b.bar_acilisi("BTCUSDT", 48_000.0, T0 + 2)
    s = b.emir_sorgula(sembol="BTCUSDT", istemci_kimligi="l")
    assert s.durum is EmirDurumu.FILLED and s.ortalama_fiyat == pytest.approx(48_000.0)


def test_fiyat_uydurmaz():
    b = borsa()
    with pytest.raises(PaperHatasi):
        b.son_fiyat("BTCUSDT")


def test_durum_diskte_kalir(tmp_path):
    saat = Saat()
    b = borsa(tmp_path, saat=saat)
    b.fiyat_bildir("BTCUSDT", 50_000.0, T0)
    b.market_emri(istemci_kimligi="k", sembol="BTCUSDT", yon="BUY", miktar=0.01)
    b.kapat()
    # Yeniden açılış açılış bakiyesini yeniden yazmaz; emir hâlâ açık ve dolabilir.
    b2 = borsa(tmp_path, saat=saat, acilis={"USDT": 999.0})
    assert [e.istemci_kimligi for e in b2.acik_emirler("BTCUSDT")] == ["k"]
    b2.bar_acilisi("BTCUSDT", 50_000.0, T0 + 1)
    assert b2.bakiye()["BTC"].toplam == pytest.approx(0.01)


def test_aninda_mod_gercek_borsa_gibi_hemen_dolar():
    b = borsa(aninda=True)
    b.fiyat_bildir("BTCUSDT", 50_000.0, T0)
    y = b.market_emri(istemci_kimligi="h", sembol="BTCUSDT", yon="BUY", miktar=0.01)
    assert y.durum is EmirDurumu.FILLED and y.komisyon_kaynagi == "yanit"
