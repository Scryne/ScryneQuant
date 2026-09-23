"""Bot takip ekranı: `/api/bot` ve arkasındaki okuyucular salt okunur ve doğru. (K-133)

Ölçülen iddialar:
- Denge tetikleri: tetik fiyatında maruziyet tam olarak hedef ± bant olur (P = x·c / (q·(1 − x))).
- Eğri: aynı bar tekrar yazılmışsa sonuncusu; seyreltmede ilk ve son nokta korunur.
- Yürütücü her işlenen bar için `egri.jsonl`e bir satır yazar; son satır raporun özkaynağıdır.
- `/api/bot` gerçek bir paper koşusunun dizinini okur, hiçbir dosya yazmaz.
- `/` derlenmiş bot sayfası varsa onu, yoksa klasik panoyu verir; `/klasik` her zaman klasik.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scryne_quant.trader import bot_panosu as bp
from scryne_quant.trader.pano import uygulama
from tests.unit.test_trader_yurutucu import barlar, kur  # noqa: F401  (fixture)


def test_denge_tetiginde_maruziyet_bant_sinirinda():
    hesap = {"miktar": 0.0006, "nakit": 50.0, "fiyat": 84_000.0, "maruziyet": 0.5}
    d = bp.denge("sabit_oran", {"hedef": 0.5, "bant": 0.05}, hesap)
    assert d is not None
    for tetik, beklenen in ((d["alis_tetigi"], 0.45), (d["satis_tetigi"], 0.55)):
        deger = hesap["miktar"] * tetik
        assert deger / (deger + hesap["nakit"]) == pytest.approx(beklenen, rel=1e-12)
    assert d["alis_tetigi"] < hesap["fiyat"] < d["satis_tetigi"]


def test_denge_pozisyonsuz_tetik_yok_ve_baska_strateji_yok():
    d = bp.denge("sabit_oran", {}, {"miktar": 0.0, "nakit": 100.0})
    assert d is not None and d["alis_tetigi"] is None and d["satis_tetigi"] is None
    assert bp.denge("sma_kesisim", {}, {"miktar": 1.0, "nakit": 1.0}) is None


def test_egri_tekillestirir_ve_seyreltirken_uclari_korur(tmp_path):
    satirlar = [{"bar_ms": i, "ozkaynak": float(i), "maruziyet": 0.5, "fiyat": 1.0}
                for i in range(10)]
    satirlar.append({"bar_ms": 3, "ozkaynak": 99.0, "maruziyet": 0.5, "fiyat": 1.0})
    (tmp_path / "egri.jsonl").write_text(
        "\n".join(json.dumps(s) for s in satirlar) + "\nbozuk satır\n", encoding="utf-8")
    e = bp.egri(tmp_path)
    assert [n["bar_ms"] for n in e] == list(range(10))
    assert e[3]["ozkaynak"] == 99.0
    s = bp.egri(tmp_path, azami=4)
    assert len(s) == 4 and s[0]["bar_ms"] == 0 and s[-1]["bar_ms"] == 9
    assert bp.egri(tmp_path / "yok") == []


def test_yurutucu_bar_basina_egri_yazar(tmp_path, barlar):  # noqa: F811
    y, k = kur(tmp_path / "execution" / "t", barlar)
    r = y.tekrar_oynat(k, isinma=100)
    satirlar = [json.loads(s) for s in
                (tmp_path / "execution/t/egri.jsonl").read_text(encoding="utf-8").splitlines()]
    zamanlar = [s["bar_ms"] for s in satirlar]
    assert zamanlar == sorted(set(zamanlar)) and len(zamanlar) >= len(barlar) - 100
    assert satirlar[-1]["ozkaynak"] == pytest.approx(r["hesap"]["ozkaynak"], rel=1e-9)
    assert satirlar[-1]["fiyat"] == barlar[-1].close
    assert all(0.0 <= s["maruziyet"] <= 1.0 for s in satirlar)


def _dosyalar(kok: Path) -> dict[str, float]:
    return {str(p): p.stat().st_mtime_ns for p in kok.rglob("*") if p.is_file()}


def test_api_bot_gercek_paper_kosusunu_okur_yazmaz(tmp_path, barlar):  # noqa: F811
    dizin = tmp_path / "runs/execution/t"
    y, k = kur(dizin, barlar)
    r = y.tekrar_oynat(k, isinma=100)
    (dizin / "durum.json").write_text(json.dumps({
        "mod": "PAPER", "zaman_ms": 5, "halt": "", "hesap": r["hesap"],
        "kosu": {"strateji": "sma_kesisim", "sembol": "BTCUSDT", "parametreler": {}},
    }), encoding="utf-8")
    once = _dosyalar(tmp_path)
    c = TestClient(uygulama(tmp_path, web_dist=tmp_path / "dist-yok"))
    d = c.get("/api/bot").json()
    s = d["secili"]
    assert s["ad"] == "t" and s["denge"] is None
    assert s["egri"][-1]["ozkaynak"] == pytest.approx(r["hesap"]["ozkaynak"], rel=1e-9)
    dolan = [e for e in s["emirler"] if e["dolan_miktar"] > 0]
    assert len(dolan) == min(r["dolan_emir"], bp.EMIR_SAYISI)
    assert [e["olusturuldu_ms"] for e in s["emirler"]] == sorted(
        (e["olusturuldu_ms"] for e in s["emirler"]), reverse=True)
    assert d["kosular"][0]["ad"] == "t"
    assert c.get("/api/bot?kosu=olmayan").json()["secili"]["ad"] == "t"
    assert _dosyalar(tmp_path) == once


def test_kok_sayfa_derlenmis_bot_sayfasi_yoksa_klasik(tmp_path):
    dist = tmp_path / "dist"
    klasik = TestClient(uygulama(tmp_path, web_dist=dist))
    assert "CURRENT MODE" in klasik.get("/").text
    (dist / "assets").mkdir(parents=True)
    (dist / "bot.html").write_text("<title>Bot paneli</title>", encoding="utf-8")
    (dist / "assets/a.js").write_text("1", encoding="utf-8")
    c = TestClient(uygulama(tmp_path, web_dist=dist))
    assert "Bot paneli" in c.get("/").text
    assert c.get("/assets/a.js").status_code == 200
    assert "CURRENT MODE" in c.get("/klasik").text
    for yol in ("/api/bot", "/"):
        assert c.post(yol).status_code in (404, 405)
