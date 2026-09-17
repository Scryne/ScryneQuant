"""Canlı evren tablosunun aylık yenilenmesi: güncel, M−1 eksik, geçmiş değişmez. (Faz 14)

Gerçek depoyla eşitlik (yenilenen tablo = araştırma tablosu, aynı hash) `Faz-14-Coklu-Paper-
Tasarim.md`de ölçüldü; burada koruma yolları sınanır.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from scryne_quant.live.evren_yenileme import (
    EvrenYenilemeHatasi,
    ay_basi_ms,
    gecmis_aylar_ayni,
    kurali_coz,
    yenile,
)

SAAT = 3_600_000


class SahteDepo:
    def __init__(self, son_ms):
        self.son_ms = son_ms

    def oku(self, sembol, timeframe):
        return pd.DataFrame({"open_time": [self.son_ms - SAAT, self.son_ms]})


def _hedef(tmp_path, son_ay="2026-08"):
    yol = tmp_path / "evren.parquet"
    pd.DataFrame({"ay": [son_ay], "sira": [1], "kanonik_id": ["A"], "sembol": ["AUSDT"],
                  "onceki_ay_quote_hacim": [1.0]}).to_parquet(yol)
    yol.with_suffix(".json").write_text(json.dumps({
        "son_uye_ay": son_ay, "tablo_hash": "h", "timeframe": "1h",
        "kural": {"ust_n": 50, "asgari_quote_hacim": 1.0}, "kural_kimlik": "yanlis",
        "kimlik_kirilmasi": {"asgari_eksik_bar": 12, "asgari_log_oran": 2.3},
    }))
    return yol


def test_guncel_tabloya_dokunmaz(tmp_path):
    yol = _hedef(tmp_path, "2026-09")
    r = yenile(yol, SahteDepo(0), [], simdi=ay_basi_ms("2026-09") + 10 * SAAT)
    assert r.durum == "guncel"


def test_m1_eksikse_yazmaz(tmp_path):
    yol = _hedef(tmp_path)
    json_once = yol.with_suffix(".json").read_text()
    # Kural kimliği yanlış: kural kontrolü M−1 kontrolünden önce koşar.
    with pytest.raises(EvrenYenilemeHatasi, match="kuralı"):
        yenile(yol, SahteDepo(ay_basi_ms("2026-09") - 2 * SAAT), [],
               simdi=ay_basi_ms("2026-09") + SAAT)
    meta = json.loads(json_once)
    from scryne_quant.data.evren import EvrenKurali

    meta["kural_kimlik"] = EvrenKurali(ust_n=50, asgari_quote_hacim=1.0).kimlik
    yol.with_suffix(".json").write_text(json.dumps(meta))
    r = yenile(yol, SahteDepo(ay_basi_ms("2026-09") - 2 * SAAT), [],
               simdi=ay_basi_ms("2026-09") + SAAT)
    assert r.durum == "m1_eksik"
    assert json.loads(yol.with_suffix(".json").read_text())["son_uye_ay"] == "2026-08"


def test_kural_sozlukten_ayni_kimlikle_kurulur():
    from scryne_quant.data.evren import EvrenKurali

    k = EvrenKurali(ust_n=50, asgari_quote_hacim=5e6)
    sozluk = json.loads(json.dumps(k.sozluk()))  # tuple → liste, diskteki hali
    assert kurali_coz({"kural": sozluk, "kural_kimlik": k.kimlik}) == k


def test_gecmis_ay_degisimi_yakalanir():
    eski = pd.DataFrame({"ay": ["2026-07", "2026-07", "2026-08"], "sira": [1, 2, 1],
                         "sembol": ["A", "B", "A"]})
    yeni = pd.concat([eski, pd.DataFrame({"ay": ["2026-09"], "sira": [1], "sembol": ["C"]})])
    assert gecmis_aylar_ayni(eski, yeni) == []
    bozuk = yeni.copy()
    bozuk.loc[(bozuk.ay == "2026-07") & (bozuk.sira == 2), "sembol"] = "Z"
    assert gecmis_aylar_ayni(eski, bozuk) == ["2026-07"]
