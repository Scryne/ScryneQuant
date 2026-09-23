"""Execution panosu: salt okuma, on bölüm + CURRENT MODE. (K-114)"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from scryne_quant.trader.pano import uygulama

REPO = Path(__file__).resolve().parents[2]


def test_pano_bos_kurulumda_disabled_ve_bolumler(tmp_path):
    (tmp_path / "config").mkdir()
    shutil.copy(REPO / "config/r8_kriterler.json", tmp_path / "config/r8_kriterler.json")
    c = TestClient(uygulama(tmp_path))
    d = c.get("/api/durum").json()
    assert d["sistem"]["mod"] == "DISABLED"
    assert d["sistem"]["r8"]["kriter_sozlesmesi"] == "dondurulmuş"
    assert d["secili"] is None and d["kosular"] == []
    html = c.get("/klasik").text
    for bolum in ("SYSTEM", "MARKET", "STRATEGY", "SIGNAL", "PORTFOLIO", "RISK", "ORDERS",
                  "EXECUTION", "JEV", "AUDIT", "CURRENT MODE"):
        assert bolum in html


def test_pano_kosu_durumunu_okur_yazmaz(tmp_path):
    k = tmp_path / "runs/execution/k1"
    k.mkdir(parents=True)
    (k / "durum.json").write_text(json.dumps(
        {"mod": "PAPER", "zaman_ms": 5, "halt": "", "kosu": {"strateji": "s"}}), encoding="utf-8")
    once = sorted(p.name for p in tmp_path.rglob("*"))
    d = TestClient(uygulama(tmp_path)).get("/api/durum").json()
    assert d["secili"]["_ad"] == "k1" and d["promotion_asamasi"] == "yok"
    assert sorted(p.name for p in tmp_path.rglob("*")) == once
