"""Execution hattı: niyet → engeller → miktar → emir → mutabakat. (K-114, R9)

Paper borsa gerçek `EmirAdaptoru` sözleşmesiyle karşı taraf; yani `EmirMotoru`, emir
defteri, emir mutabakatı ve pozisyon mutabakatı burada **gerçekten** çalışıyor.
"""

from __future__ import annotations

import json

import pytest

from scryne_quant.exchange.golge import GolgeAdaptoru
from scryne_quant.exchange.kurallar import SembolKurallari
from scryne_quant.exchange.paper_adaptoru import PaperBorsa, PaperMaliyet
from scryne_quant.execution.hat import (
    Engel,
    ExecutionHatti,
    GuvenlikLimitleri,
    HatHatasi,
)
from scryne_quant.execution.mod import CalismaModu
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.oms.emir import EmirDurumu
from scryne_quant.risk.audit import BellekDefteri
from scryne_quant.risk.niyet import onayla
from scryne_quant.strategy.sinyal import Sinyal, Yon

K = SembolKurallari("BTCUSDT", 0.01, 0.00001, 5.0, "TRADING", "BTC", "USDT")
T0 = 1_699_999_200_000
SAAT = 3_600_000
LIM = GuvenlikLimitleri(
    sermaye_usdt=10_000.0,
    azami_maruziyet=0.3,
    azami_brut_maruziyet=1.0,
    gunluk_zarar_limiti=0.05,
    drawdown_limiti=0.2,
)


class Saat:
    def __init__(self) -> None:
        self.t = T0 + SAAT

    def __call__(self) -> int:
        return self.t


def niyet(hedef=0.2, yon=Yon.BUY, zaman=T0, onayli=None, sebep="TEST"):
    return onayla(
        sinyal=Sinyal(symbol="BTCUSDT", side=yon, target_exposure=hedef, confidence=0.9,
                      reason=sebep, timestamp=zaman),
        onayli_maruziyet=hedef if onayli is None else onayli,
        limit_kimligi="k" * 64,
        karar_ms=zaman,
    )


@pytest.fixture
def kurulum(tmp_path):
    saat = Saat()
    b = PaperBorsa(kurallar={"BTCUSDT": K}, maliyet=PaperMaliyet(10.0, 5.0), saat=saat,
                   acilis_bakiyesi={"USDT": 10_000.0})
    b.fiyat_bildir("BTCUSDT", 50_000.0, saat.t)
    audit = BellekDefteri()
    hat = ExecutionHatti(mod=CalismaModu.PAPER, adaptor=b, defter=EmirDefteri(), limitler=LIM,
                         sembol="BTCUSDT", kosu_dizini=tmp_path / "k", audit=audit, saat=saat)
    hat.baslat()
    return hat, b, saat, audit


def test_uctan_uca_alim_sonraki_acilista_dolar_mutabakat_temiz(kurulum):
    hat, b, saat, audit = kurulum
    u = hat.uygula(niyet(0.2), son_kapali_bar_ms=T0)
    assert u.sonuc == "gonderildi"
    assert u.miktar == pytest.approx(0.04)  # 0.2 × 10.000 / 50.000
    assert hat.hesap().miktar == 0.0  # henüz dolmadı (K-004)
    saat.t += SAAT
    b.bar_acilisi("BTCUSDT", 50_500.0, T0 + SAAT)
    s = hat.mutabakat_yap()
    assert s["ok"] and not s["pozisyon_mutabakati"]["halt"]
    h = hat.hesap()
    assert h.miktar == pytest.approx(0.04)
    assert h.nakit == pytest.approx(10_000 - 0.04 * 50_500 * 1.0005 * 1.001)
    assert audit.dogrula()
    assert any(r["govde"].get("olay") == "niyet" for r in audit.oku())


def test_acik_emir_varken_yeni_emir_yok_sonra_ayni_bar_yok(kurulum):
    hat, b, saat, _ = kurulum
    hat.uygula(niyet(0.2), son_kapali_bar_ms=T0)
    assert hat.uygula(niyet(0.2), son_kapali_bar_ms=T0).engel == Engel.ACIK_EMIR
    b.bar_acilisi("BTCUSDT", 50_000.0, T0 + SAAT)
    hat.mutabakat_yap()
    # Aynı bar için başka bir niyet (farklı sebep → farklı kimlik) de gitmez.
    assert hat.uygula(niyet(0.25, sebep="BASKA"), son_kapali_bar_ms=T0).engel == Engel.AYNI_BAR
    assert len(hat.defter.tumu()) == 1


def test_safe_mode_artirani_engeller_azaltani_gecirir(kurulum):
    hat, b, saat, _ = kurulum
    hat.uygula(niyet(0.2), son_kapali_bar_ms=T0)
    b.bar_acilisi("BTCUSDT", 50_000.0, T0 + SAAT)
    hat.mutabakat_yap()
    hat.safe_isaretle("test")
    t1 = T0 + SAAT
    assert hat.uygula(niyet(0.3, zaman=t1), son_kapali_bar_ms=t1).engel == Engel.SAFE_MODE
    t2 = t1 + SAAT
    u = hat.uygula(niyet(0.0, yon=Yon.FLAT, zaman=t2), son_kapali_bar_ms=t2)
    assert u.sonuc == "gonderildi" and u.miktar == pytest.approx(0.04)


def test_bayat_karar_artirani_engeller(kurulum):
    hat, *_ = kurulum
    assert hat.uygula(niyet(0.2, zaman=T0), son_kapali_bar_ms=T0 + SAAT).engel == Engel.BAYAT_KARAR


def test_halt_her_seyi_engeller_ve_diske_yazilir(kurulum, tmp_path):
    hat, b, saat, _ = kurulum
    hat.durdur("test uyuşmazlığı")
    assert hat.uygula(niyet(0.0, yon=Yon.FLAT), son_kapali_bar_ms=T0).engel == Engel.HALT
    yeni = ExecutionHatti(mod=CalismaModu.PAPER, adaptor=b, defter=EmirDefteri(), limitler=LIM,
                          sembol="BTCUSDT", kosu_dizini=tmp_path / "k", saat=saat)
    assert yeni.halt == "test uyuşmazlığı"


def test_tavan_yalniz_asagi_ceker(kurulum):
    hat, *_ = kurulum
    u = hat.uygula(niyet(0.9), son_kapali_bar_ms=T0)
    assert u.kisitlayan == ("azami_maruziyet",)
    assert u.miktar == pytest.approx(0.3 * 10_000 / 50_000)


def test_yetim_emir_halt(kurulum):
    hat, b, *_ = kurulum
    b.market_emri(istemci_kimligi="elle", sembol="BTCUSDT", yon="BUY", miktar=0.001)
    s = hat.mutabakat_yap()
    assert not s["ok"] and hat.halt


def test_drawdown_borsa_olcumlu_safe_mode(kurulum):
    hat, b, saat, _ = kurulum
    hat.uygula(niyet(0.3), son_kapali_bar_ms=T0)
    b.bar_acilisi("BTCUSDT", 50_000.0, T0 + SAAT)
    hat.mutabakat_yap()
    t1 = T0 + SAAT
    hat.uygula(niyet(0.3, sebep="ZIRVE", zaman=t1), son_kapali_bar_ms=t1)  # zirveyi işler
    b.fiyat_bildir("BTCUSDT", 1_000.0, saat.t)  # %98 düşüş: özkaynak ~7.060
    hat.izleyici.zirve = 10_000.0
    hat.izleyici.gun_basi = 10_000.0
    t2 = t1 + SAAT
    u = hat.uygula(niyet(0.3, sebep="YENI", zaman=t2), son_kapali_bar_ms=t2)
    assert u.engel == Engel.DRAWDOWN and hat.safe_mode


def test_acil_iptal_defter_ve_yetim(kurulum):
    hat, b, *_ = kurulum
    hat.uygula(niyet(0.2), son_kapali_bar_ms=T0)
    b.market_emri(istemci_kimligi="yetim", sembol="BTCUSDT", yon="BUY", miktar=0.001)
    r = hat.acil_iptal("tatbikat")
    assert r["basarili"] and r["kalan_acik_emir"] == 0
    assert any(i.get("yetim") for i in r["iptaller"])
    assert hat.safe_mode


def test_shadow_gonderilmez_golge_yazilir(tmp_path):
    saat = Saat()
    b = PaperBorsa(kurallar={"BTCUSDT": K}, maliyet=PaperMaliyet(10.0, 5.0), saat=saat,
                   acilis_bakiyesi={"USDT": 10_000.0})
    b.fiyat_bildir("BTCUSDT", 50_000.0, saat.t)
    hat = ExecutionHatti(mod=CalismaModu.SHADOW, adaptor=GolgeAdaptoru(b), defter=EmirDefteri(),
                         limitler=LIM, sembol="BTCUSDT", kosu_dizini=tmp_path, saat=saat)
    hat.baslat()
    u = hat.uygula(niyet(0.2), son_kapali_bar_ms=T0)
    assert u.sonuc == "golge"
    e = hat.defter.tumu()[0]
    assert e.durum is EmirDurumu.GOLGE and "SUBMITTED" not in e.gecmis
    assert b.acik_emirler("BTCUSDT") == [] and "BTC" not in b.bakiye()
    assert not hat.mutabakat_yap()["halt"]


def test_mod_adaptor_uyumu(tmp_path):
    saat = Saat()
    b = PaperBorsa(kurallar={"BTCUSDT": K}, maliyet=PaperMaliyet(0, 0), saat=saat)
    ortak = dict(defter=EmirDefteri(), limitler=LIM, sembol="BTCUSDT", kosu_dizini=tmp_path,
                 saat=saat)
    with pytest.raises(HatHatasi):
        ExecutionHatti(mod=CalismaModu.SHADOW, adaptor=b, **ortak)
    with pytest.raises(HatHatasi):
        ExecutionHatti(mod=CalismaModu.PAPER, adaptor=GolgeAdaptoru(b), **ortak)
    with pytest.raises(HatHatasi):
        ExecutionHatti(mod=CalismaModu.LIVE, adaptor=b, **ortak)
    with pytest.raises(HatHatasi):
        ExecutionHatti(mod=CalismaModu.DISABLED, adaptor=b, **ortak)


def test_durum_dosyasi_pano_alanlari(kurulum):
    hat, *_ = kurulum
    hat.uygula(niyet(0.2), son_kapali_bar_ms=T0)
    d = hat.durum_yaz()
    kayit = json.loads((hat.kosu_dizini / "durum.json").read_text(encoding="utf-8"))
    for alan in ("mod", "hesap", "bakiye", "acik_emirler_borsa", "emirler", "son_kararlar",
                 "mutabakat", "pozisyon_mutabakati", "baglanti", "limitler"):
        assert alan in d and alan in kayit
    assert d["emirler"]["acik"] == 1
