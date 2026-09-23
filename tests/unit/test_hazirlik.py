"""Hazırlık raporu: sistem ve strateji hükümleri kanıttan çıkar, varsayılmaz. (K-122)"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scryne_quant.execution import hazirlik as hz
from scryne_quant.live import kill as kill_mod

GUN = 86_400_000
SAAT = 3_600_000
SIMDI = 1_800_000_000_000 // SAAT * SAAT + 600_000  # bar açılışından 10 dk sonra


def _kosu(kok: Path, ad: str, mod: str, **deg) -> Path:
    d = kok / "runs" / "execution" / ad
    d.mkdir(parents=True)
    ayar = {
        "gun": 15.0, "bar": 360, "kacirilan": 0, "yeniden": 1, "saat": 0, "halt": "",
        "belirsiz": 0, "poz": {"halt": False}, "sayim": {"FILLED": 6} if mod == "TESTNET"
        else {"GOLGE": 6}, "gecikme_bar": 0, "pid": os.getpid(),
    } | deg
    (d / "kosu.json").write_text(json.dumps({"mod": mod, "timeframe": "1h"}), encoding="utf-8")
    son = (SIMDI // SAAT) * SAAT - SAAT - ayar["gecikme_bar"] * SAAT
    (d / "yurutucu.json").write_text(json.dumps({
        "baslangic_ms": SIMDI - int(ayar["gun"] * GUN), "son_islenen_ms": son,
        "sayac": {"bar": ayar["bar"], "kacirilan_karar": ayar["kacirilan"],
                  "yeniden_baslatma": ayar["yeniden"], "saat_sicramasi": ayar["saat"]},
    }), encoding="utf-8")
    (d / "durum.json").write_text(json.dumps({
        "halt": ayar["halt"], "pozisyon_mutabakati": ayar["poz"],
        "emirler": {"belirsiz": ayar["belirsiz"], "sayim": ayar["sayim"]},
    }), encoding="utf-8")
    if ayar["pid"] is not None:
        kill_mod.pid_yaz(d / "kosu", ayar["pid"])
    return d


def _k(kok, ad="gosterim-testnet", mod="TESTNET"):
    return hz.kosu_kontrolu(kok, ad, mod, simdi=SIMDI)


def test_tam_kanitli_testnet_kosusu_gecer(tmp_path):
    _kosu(tmp_path, "gosterim-testnet", "TESTNET")
    k = _k(tmp_path)
    assert k.gecti is True, k.ayrinti


def test_tam_kanitli_shadow_kosusu_gecer(tmp_path):
    _kosu(tmp_path, "gosterim-shadow", "SHADOW")
    assert _k(tmp_path, "gosterim-shadow", "SHADOW").gecti is True


@pytest.mark.parametrize(("deg", "beklenen"), [
    ({"gun": 13.9}, "süre"),
    ({"pid": None}, "süreç çalışmıyor"),
    ({"gecikme_bar": 3}, "veri bayat"),
    ({"halt": "pozisyon farkı"}, "halt"),
    ({"belirsiz": 1}, "UNKNOWN"),
    ({"poz": {"halt": True}}, "pozisyon mutabakatı"),
    ({"poz": {}}, "pozisyon mutabakatı"),
    ({"sayim": {"FILLED": 3}}, "dolan emir"),
    ({"kacirilan": 8}, "kaçırılan karar"),
    ({"saat": 1}, "saat sıçraması"),
    ({"yeniden": 0}, "yeniden başlatma"),
])
def test_her_eksik_kosuyu_hazir_saymaz(tmp_path, deg, beklenen):
    _kosu(tmp_path, "gosterim-testnet", "TESTNET", **deg)
    k = _k(tmp_path)
    assert k.gecti is False and beklenen in k.ayrinti


def test_shadowda_gonderilmis_emir_kalir(tmp_path):
    _kosu(tmp_path, "gosterim-shadow", "SHADOW", sayim={"GOLGE": 6, "FILLED": 1})
    k = _k(tmp_path, "gosterim-shadow", "SHADOW")
    assert k.gecti is False and "OLMAMALI" in k.ayrinti


def test_kosu_yoksa_ve_mod_yanlissa_kalir(tmp_path):
    assert _k(tmp_path).gecti is False
    _kosu(tmp_path, "gosterim-testnet", "PAPER")
    assert _k(tmp_path).gecti is False


def test_safe_mode_ve_kapatilmis_kosu_kalir(tmp_path):
    d = _kosu(tmp_path, "gosterim-testnet", "TESTNET")
    (d / "kosu.safemode").write_text("{}", encoding="utf-8")
    assert "SAFE_MODE" in _k(tmp_path).ayrinti
    (d / "kapatildi.json").write_text("{}", encoding="utf-8")
    assert "kapatılmış" in _k(tmp_path).ayrinti


def test_strateji_hukmu_promotion_kaydindan(tmp_path):
    kok = tmp_path / "runs" / "promotion"
    kok.mkdir(parents=True)
    (kok / "a.json").write_text(json.dumps({"asama": "paper"}), encoding="utf-8")
    assert hz.strateji_kontrolu(tmp_path).gecti is False
    (kok / "b.json").write_text(json.dumps({"asama": "live_adayi"}), encoding="utf-8")
    assert hz.strateji_kontrolu(tmp_path).gecti is True


def test_bos_kok_hic_hazir_degil(tmp_path):
    r = hz.rapor(tmp_path, simdi=SIMDI)
    assert not r.sistem_hazir and not r.strateji_hazir and not r.gercek_paraya_hazir
    assert {k.ad for k in r.sistem} >= {"testler", "kosu:gosterim-testnet",
                                        "kosu:gosterim-shadow", "kill_tatbikati", "operasyon_r8"}


def test_bozuk_pid_dosyasi_calismiyor_sayilir(tmp_path):
    d = _kosu(tmp_path, "gosterim-testnet", "TESTNET", pid=None)
    (d / "kosu.pid").write_text("12345", encoding="utf-8")  # JSON ama nesne değil
    k = _k(tmp_path)
    assert k.gecti is False and "süreç çalışmıyor" in k.ayrinti
