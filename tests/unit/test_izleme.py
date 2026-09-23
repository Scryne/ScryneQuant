"""İzleme kuralları ve runbook bağı. (Faz 14)"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from scryne_quant.common.zaman import utc_str
from scryne_quant.live.izleme import RUNBOOK_KODLARI, alarmlar

SAAT = 3_600_000
KOK = Path(__file__).resolve().parents[2]
SIMDI = int(dt.datetime(2026, 9, 17, 16, 10, tzinfo=dt.UTC).timestamp() * 1000)
SISTEM = {"disk_bos_gb": 100.0, "bellek_bos_gb": 8.0}


def _kosu(simdi=SIMDI, **kw):
    g = {"kosu": "k", "var": True, "surec_yasiyor": True, "adim": 800,
         "son_bar_ms": simdi // SAAT * SAAT - SAAT, "ozkaynak": 10_000.0, "brut": 0.2,
         "zirve_ozkaynak": 10_000.0, "eksik_adim_24s": 0, "olay_24s": {}, "son_hata": None,
         "safe_mode": False, "hedef_brut": 0.2}
    g.update(kw)
    return g


def _kodlar(*kosular, sistem=SISTEM, simdi=SIMDI):
    return sorted(a.kod for a in alarmlar(sistem, list(kosular), simdi))


def test_saglikli_kosuda_alarm_yok():
    assert _kodlar(_kosu()) == []


def test_her_kural_tetiklenir():
    assert _kodlar(_kosu(surec_yasiyor=False)) == ["SUREC_YOK"]
    assert _kodlar(_kosu(son_bar_ms=SIMDI // SAAT * SAAT - 3 * SAAT)) == ["SON_BAR_GECIKTI"]
    assert _kodlar(_kosu(eksik_adim_24s=4)) == ["EKSIK_ADIM"]
    assert _kodlar(_kosu(olay_24s={"kopma": 6})) == ["KOPMA"]
    assert _kodlar(_kosu(safe_mode=True)) == ["SAFE_MODE"]
    assert _kodlar(_kosu(ozkaynak=9_400.0)) == ["DUSUS"]
    assert _kodlar(_kosu(brut=0.31)) == ["BRUT_ASIMI"]
    assert _kodlar(_kosu(son_hata={"hata": "x"})) == ["KOSU_HATASI"]
    assert _kodlar(_kosu(yenileme_son_satir="HATA: geçmiş ay")) == ["TABLO_YENILEME_HATASI"]
    assert _kodlar(_kosu(), sistem={"disk_bos_gb": 1.0, "bellek_bos_gb": 0.5}) == [
        "BELLEK_AZ", "DISK_AZ"]


def test_dusus_seviyesi():
    (a,) = alarmlar(SISTEM, [_kosu(ozkaynak=8_900.0)], SIMDI)
    assert a.seviye == "kritik"


def test_uyelik_gecikmesi_ayin_ilk_gunlerinde_sessiz():
    ayin_2si = int(dt.datetime(2026, 10, 2, 5, 10, tzinfo=dt.UTC).timestamp() * 1000)
    ayin_5i = int(dt.datetime(2026, 10, 5, 5, 10, tzinfo=dt.UTC).timestamp() * 1000)
    assert _kodlar(_kosu(ayin_2si, uyelik_gecikmesi_suruyor=True), simdi=ayin_2si) == []
    assert _kodlar(_kosu(ayin_5i, uyelik_gecikmesi_suruyor=True), simdi=ayin_5i) == [
        "UYELIK_GECIKMESI"]


def test_sapma_sebepli_sebepsiz_ve_bayat():
    temel = {"olculdu": utc_str(SIMDI - SAAT), "ilk_ayrisan_adim": 900, "ilk_ayrisan_utc": "x",
             "gec_bilinen_bar": 0, "eksikli_adim": 0, "uyelik_gecikmesi": 0,
             "son_ozkaynak_farki_bps": 0.1}
    assert _kodlar(_kosu(sapma=temel)) == ["SEBEPSIZ_SAPMA"]
    assert _kodlar(_kosu(sapma={**temel, "makro_revizyon": 1})) == []
    assert _kodlar(_kosu(sapma={**temel, "gec_bilinen_turev": 3})) == []
    sebepli = {**temel, "gec_bilinen_bar": 2, "son_ozkaynak_farki_bps": 80.0}
    assert _kodlar(_kosu(sapma=sebepli)) == ["SAPMA"]
    assert _kodlar(_kosu(sapma={**sebepli, "son_ozkaynak_farki_bps": 3.0})) == []
    bayat = {**temel, "olculdu": utc_str(SIMDI - 48 * SAAT), "ilk_ayrisan_adim": None}
    assert _kodlar(_kosu(sapma=bayat)) == ["SAPMA_OLCUMU_YOK"]


def test_her_kodun_runbook_satiri_var_ve_fazlasi_yok():
    metin = (KOK / "docs/arsiv/Runbook.md").read_text(encoding="utf-8")
    runbook = set(re.findall(r"^\| `([A-Z_]+)` \|", metin, flags=re.M))
    assert runbook == set(RUNBOOK_KODLARI)
    kaynak = (KOK / "src/scryne_quant/live/izleme.py").read_text(encoding="utf-8")
    assert set(re.findall(r'Alarm\("([A-Z_]+)"', kaynak)) == set(RUNBOOK_KODLARI)
