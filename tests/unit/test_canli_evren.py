"""Canlı evren üyeliği: ay seçimi, gecikme kuralı, gelecek ay yok. (Faz 14)"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scryne_quant.live.canli_evren import (
    AyUyeligi,
    CanliEvrenHatasi,
    UyelikTakvimi,
    ay_metni,
    tablodan,
)


def ms(tarih: str) -> int:
    return int(pd.Timestamp(tarih, tz="UTC").value // 10**6)


TABLO = pd.DataFrame({
    "ay": ["2026-08", "2026-08", "2026-09", "2026-09"],
    "sira": [1, 2, 1, 2],
    "kanonik_id": ["a", "b", "a", "c"],
    "sembol": ["BTCUSDT", "ETHUSDT", "BTCUSDT", "SOLUSDT"],
    "onceki_ay_quote_hacim": [2.0, 1.0, 2.0, 1.5],
})


def test_ay_metni_utc():
    assert ay_metni(ms("2026-09-30 23:00")) == "2026-09"
    assert ay_metni(ms("2026-10-01 00:00")) == "2026-10"


def test_tablodan_ay_yoksa_hata():
    assert tablodan(TABLO, "2026-09", "h").semboller == ("BTCUSDT", "SOLUSDT")
    with pytest.raises(CanliEvrenHatasi):
        tablodan(TABLO, "2026-10", "h")


def test_bilinen_ay_ve_gecikme():
    tk = UyelikTakvimi()
    tk.ekle(tablodan(TABLO, "2026-08", "h"))
    tk.ekle(tablodan(TABLO, "2026-09", "h"))
    assert tk.uyeler(ms("2026-09-15")) == (("BTCUSDT", "SOLUSDT"), "2026-09", False)
    # Ekim tablosu henüz yok: eylül listesi, gecikme işaretli.
    assert tk.uyeler(ms("2026-10-01 00:00")) == (("BTCUSDT", "SOLUSDT"), "2026-09", True)


def test_gelecek_ay_asla_kullanilmaz():
    tk = UyelikTakvimi()
    tk.ekle(tablodan(TABLO, "2026-09", "h"))
    assert tk.uyeler(ms("2026-08-20")) == ((), None, True)


def test_ayni_aya_farkli_liste_reddedilir():
    tk = UyelikTakvimi()
    tk.ekle(AyUyeligi("2026-09", ("A",), "h1"))
    tk.ekle(AyUyeligi("2026-09", ("A",), "h1"))  # aynısı sorun değil
    with pytest.raises(CanliEvrenHatasi):
        tk.ekle(AyUyeligi("2026-09", ("B",), "h2"))


def test_diziler_ve_sozluk_gidis_donus():
    tk = UyelikTakvimi()
    tk.ekle(tablodan(TABLO, "2026-08", "h"))
    tk.ekle(tablodan(TABLO, "2026-09", "h"))
    z = np.array([ms("2026-08-31 23:00"), ms("2026-09-01 00:00")])
    d = tk.dizileri(z, ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    assert d["ETHUSDT"].tolist() == [True, False]
    assert d["SOLUSDT"].tolist() == [False, True]
    assert d["BTCUSDT"].tolist() == [True, True]
    assert UyelikTakvimi.sozlukten(tk.sozluk()).kimlik() == tk.kimlik()
