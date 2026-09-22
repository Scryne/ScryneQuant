"""Execution modu durum makinesi. (K-114)

DISABLED → PAPER → SHADOW → TESTNET → LIVE_PENDING_APPROVAL → LIVE. Yukarı yalnızca bir adım
ve kapıdan geçerek; aşağı her zaman; LIVE yalnızca `canli_onayla` ile, doğru hash ve notla.
Kırık zincir DISABLED okunur (fail closed).
"""

from __future__ import annotations

import json

import pytest

from scryne_quant.execution.mod import (
    CalismaModu,
    ModDefteri,
    ModHatasi,
    OnayGerekli,
    canli_onayla,
)
from scryne_quant.risk.audit import BellekDefteri


def rapor(hedef: CalismaModu, gecti: bool = True, h: str = "h" * 64) -> dict:
    return {"hedef": str(hedef), "gecti": gecti, "hash": h, "kontroller": [],
            "strateji": "s", "kademe": 1, "sermaye_usdt": 100.0}


def tirman(d: ModDefteri, son: CalismaModu) -> None:
    for m in CalismaModu:
        if m is CalismaModu.DISABLED:
            continue
        if m is CalismaModu.LIVE or list(CalismaModu).index(m) > list(CalismaModu).index(son):
            return
        d.yukselt(m, kapi_raporu=rapor(m))


def test_bos_kayit_disabled(tmp_path):
    assert ModDefteri(tmp_path / "m.json").mod() is CalismaModu.DISABLED


def test_yukari_bir_adim_ve_kapi_sart(tmp_path):
    d = ModDefteri(tmp_path / "m.json", audit=BellekDefteri())
    with pytest.raises(ModHatasi, match="bir adım"):
        d.yukselt(CalismaModu.SHADOW, kapi_raporu=rapor(CalismaModu.SHADOW))
    with pytest.raises(ModHatasi, match="geçilmedi"):
        d.yukselt(CalismaModu.PAPER, kapi_raporu=rapor(CalismaModu.PAPER, gecti=False))
    with pytest.raises(ModHatasi, match="başka bir mod"):
        d.yukselt(CalismaModu.PAPER, kapi_raporu=rapor(CalismaModu.SHADOW))
    d.yukselt(CalismaModu.PAPER, kapi_raporu=rapor(CalismaModu.PAPER))
    assert d.mod() is CalismaModu.PAPER
    assert d.audit.dogrula()


def test_live_yukselt_ile_acilamaz(tmp_path):
    d = ModDefteri(tmp_path / "m.json")
    tirman(d, CalismaModu.LIVE_PENDING_APPROVAL)
    assert d.mod() is CalismaModu.LIVE_PENDING_APPROVAL
    with pytest.raises(OnayGerekli):
        d.yukselt(CalismaModu.LIVE, kapi_raporu=rapor(CalismaModu.LIVE))


def test_canli_onay_hash_not_ve_kapi(tmp_path):
    d = ModDefteri(tmp_path / "m.json")
    tirman(d, CalismaModu.LIVE_PENDING_APPROVAL)
    r = rapor(CalismaModu.LIVE)
    with pytest.raises(ModHatasi, match="gerekçe"):
        canli_onayla(d, kapi_raporu=r, gorulen_hash=r["hash"], not_metni="kısa", onaylayan="S")
    with pytest.raises(ModHatasi, match="hash"):
        canli_onayla(d, kapi_raporu=r, gorulen_hash="x" * 64,
                     not_metni="yirmi karakterden uzun gerekçe", onaylayan="S")
    with pytest.raises(ModHatasi, match="geçmedi"):
        canli_onayla(d, kapi_raporu=rapor(CalismaModu.LIVE, gecti=False), gorulen_hash=r["hash"],
                     not_metni="yirmi karakterden uzun gerekçe", onaylayan="S")
    satir = canli_onayla(d, kapi_raporu=r, gorulen_hash=r["hash"],
                         not_metni="yirmi karakterden uzun gerekçe", onaylayan="S")
    assert d.mod() is CalismaModu.LIVE and satir["kapi_hash"] == r["hash"]
    assert d.oku().son_onay["strateji"] == "s"


def test_onay_yalniz_pending_den(tmp_path):
    d = ModDefteri(tmp_path / "m.json")
    tirman(d, CalismaModu.TESTNET)
    r = rapor(CalismaModu.LIVE)
    with pytest.raises(ModHatasi, match="LIVE_PENDING_APPROVAL"):
        canli_onayla(d, kapi_raporu=r, gorulen_hash=r["hash"],
                     not_metni="yirmi karakterden uzun gerekçe", onaylayan="S")


def test_asagi_her_zaman_onaysiz(tmp_path):
    d = ModDefteri(tmp_path / "m.json")
    tirman(d, CalismaModu.TESTNET)
    assert d.indir(CalismaModu.TESTNET, sebep="aynı mod") is None
    satir = d.indir(CalismaModu.DISABLED, sebep="kill switch")
    assert satir["yon"] == "asagi" and d.mod() is CalismaModu.DISABLED
    with pytest.raises(ModHatasi):
        d.indir(CalismaModu.DISABLED, sebep="")


def test_elle_duzenlenen_kayit_disabled_okunur(tmp_path):
    yol = tmp_path / "m.json"
    d = ModDefteri(yol)
    tirman(d, CalismaModu.SHADOW)
    kayit = json.loads(yol.read_text(encoding="utf-8"))
    kayit["gecmis"][-1]["nereye"] = "LIVE"  # elle "LIVE" yazmak
    yol.write_text(json.dumps(kayit), encoding="utf-8")
    k = d.oku()
    assert k.bozuk and k.mod is CalismaModu.DISABLED
    with pytest.raises(ModHatasi, match="bozuk"):
        d.yukselt(CalismaModu.PAPER, kapi_raporu=rapor(CalismaModu.PAPER))
