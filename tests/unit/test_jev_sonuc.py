"""Sonuç bağlama ve değerlendirme: tanımlar config'teki gibi, gelecek karara sızmaz. (K-074/7)"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.jev import ayarlar as ayar_mod
from scryne_quant.jev.sonuc import (
    SonucHatasi,
    defterden_cerceve,
    degerlendir,
    kalibrasyon,
    sonuclari_bagla,
    wilson,
)
from tests.conftest import bar_uret

SAAT = 3_600_000


@pytest.fixture
def ayar():
    return ayar_mod.yukle()


@pytest.fixture
def maliyet():
    return MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)


@pytest.fixture
def barlar():
    return bar_uret(n=200, tohum=9)


def _kararlar(barlar: pd.DataFrame, satirlar: list[tuple[int, str, str, float]]) -> pd.DataFrame:
    """(bar indeksi, durum_kodu, yon, guven) → karar çerçevesi."""
    return pd.DataFrame(
        {
            "karar_ms": [int(barlar.open_time.iloc[i]) for i, *_ in satirlar],
            "durum_kodu": [d for _, d, *_ in satirlar],
            "yon": [y for _, _, y, _ in satirlar],
            "yon_guven": [g for *_, g in satirlar],
            "rejim": ["aralik"] * len(satirlar),
            "gecikme_ms": [300] * len(satirlar),
            "leak_riski": [False] * len(satirlar),
        }
    )


class TestBaglama:
    def test_tanimlar_configteki_gibi(self, barlar, ayar, maliyet):
        i = 50
        k = _kararlar(barlar, [(i, "gecerli", "long", 0.7)])
        b = sonuclari_bagla(k, barlar, ayarlar=ayar, maliyet=maliyet)
        giris = float(barlar.open.iloc[i + 1])
        assert b.at[0, "giris"] == giris
        for h in ayar.ufuk_bar:
            assert b.at[0, f"getiri_{h}"] == pytest.approx(barlar.close.iloc[i + h] / giris - 1)
            assert b.at[0, f"mae_{h}"] == pytest.approx(
                barlar.low.iloc[i + 1 : i + h + 1].min() / giris - 1
            )
            assert b.at[0, f"mfe_{h}"] == pytest.approx(
                barlar.high.iloc[i + 1 : i + h + 1].max() / giris - 1
            )
            assert b.at[0, f"net_{h}"] == pytest.approx(
                b.at[0, f"getiri_{h}"] - maliyet.gidis_donus_bps / 10_000
            )

    def test_short_isareti_ve_flat_maliyetsiz(self, barlar, ayar, maliyet):
        k = _kararlar(barlar, [(50, "gecerli", "short", 0.7), (60, "gecerli", "flat", 0.9)])
        b = sonuclari_bagla(k, barlar, ayarlar=ayar, maliyet=maliyet)
        assert b.at[0, "net_4"] == pytest.approx(-b.at[0, "getiri_4"] - 30 / 10_000)
        assert b.at[1, "net_4"] == 0.0 and not np.isnan(b.at[1, "getiri_4"])

    def test_gelecek_yoksa_nan(self, barlar, ayar, maliyet):
        son = len(barlar) - 1
        k = _kararlar(barlar, [(son, "gecerli", "long", 0.7), (son - 2, "gecerli", "long", 0.7)])
        b = sonuclari_bagla(k, barlar, ayarlar=ayar, maliyet=maliyet)
        assert np.isnan(b.at[0, "giris"]) and np.isnan(b.at[0, "getiri_1"])
        assert not np.isnan(b.at[1, "getiri_1"]) and np.isnan(b.at[1, "getiri_4"])

    def test_bosluk_varsa_nan(self, barlar, ayar, maliyet):
        eksik = barlar.drop(index=52).reset_index(drop=True)  # 50'nin 2 bar sonrası yok
        k = _kararlar(barlar, [(50, "gecerli", "long", 0.7)])
        b = sonuclari_bagla(k, eksik, ayarlar=ayar, maliyet=maliyet)
        assert not np.isnan(b.at[0, "getiri_1"]) and np.isnan(b.at[0, "getiri_4"])

    def test_kararlar_degismez(self, barlar, ayar, maliyet):
        k = _kararlar(barlar, [(50, "gecerli", "long", 0.7)])
        kopya = k.copy()
        sonuclari_bagla(k, barlar, ayarlar=ayar, maliyet=maliyet)
        pd.testing.assert_frame_equal(k, kopya)

    def test_gecersiz_kararda_da_baglanir_ama_yon_yok(self, barlar, ayar, maliyet):
        k = _kararlar(barlar, [(50, "timeout", None, np.nan)])
        b = sonuclari_bagla(k, barlar, ayarlar=ayar, maliyet=maliyet)
        assert not np.isnan(b.at[0, "getiri_4"]) and b.at[0, "net_4"] == 0.0

    def test_eksik_sutun(self, barlar, ayar, maliyet):
        with pytest.raises(SonucHatasi):
            sonuclari_bagla(pd.DataFrame({"karar_ms": []}), barlar, ayarlar=ayar, maliyet=maliyet)


class TestIstatistik:
    def test_wilson(self):
        p, alt, ust = wilson(50, 100)
        assert (
            p == 0.5
            and alt == pytest.approx(0.404, abs=0.002)
            and ust == pytest.approx(0.596, abs=0.002)
        )
        assert wilson(0, 0) == (None, None, None)
        assert wilson(10, 10)[2] == 1.0

    def test_kalibrasyon_mukemmel(self):
        g = pd.Series([0.9] * 9 + [0.1] * 10)
        y = pd.Series([True] * 8 + [False] + [False] * 9 + [True])
        r = kalibrasyon(g, y, (0.0, 0.5, 1.0))
        assert r["n"] == 19 and r["ece"] == pytest.approx(
            (9 / 19) * abs(0.9 - 8 / 9) + (10 / 19) * abs(0.1 - 0.1)
        )
        assert r["kovalar"][1]["n"] == 9 and r["kovalar"][0]["n"] == 10

    def test_kalibrasyon_bos(self):
        r = kalibrasyon(pd.Series(dtype=float), pd.Series(dtype=bool), (0.0, 1.0))
        assert r["n"] == 0 and r["brier"] is None and r["kovalar"][0]["n"] == 0


class TestDegerlendir:
    def _rapor(self, barlar, ayar, maliyet, satirlar):
        k = _kararlar(barlar, satirlar)
        b = sonuclari_bagla(k, barlar, ayarlar=ayar, maliyet=maliyet)
        return degerlendir(b, ayarlar=ayar)

    def test_isabet_bilinen_sonuca_gore(self, barlar, ayar, maliyet):
        # Yönü geleceğe bakarak seçiyoruz: rapor mekaniğini test etmek için (kanıt değil!)
        satirlar = []
        for i in range(30, 60):
            giris = barlar.open.iloc[i + 1]
            getiri = barlar.close.iloc[i + 4] / giris - 1
            satirlar.append((i, "gecerli", "long" if getiri > 0 else "short", 0.8))
        r = self._rapor(barlar, ayar, maliyet, satirlar)
        assert r["yon_isabeti"]["n"] == 30 and r["yon_isabeti"]["oran"] == 1.0
        assert r["kiyas_al_tut"]["n"] == 30 and 0 < r["kiyas_al_tut"]["oran"] < 1
        assert r["kanit"] is True and r["cekimserlik_orani"] == 0.0
        assert r["kalibrasyon"]["brier"] == pytest.approx(0.04)  # (0.8 − 1)²

    def test_flat_cekimserlik_isabete_girmez(self, barlar, ayar, maliyet):
        r = self._rapor(
            barlar, ayar, maliyet, [(30, "gecerli", "flat", 0.9), (31, "gecerli", "long", 0.6)]
        )
        assert r["cekimserlik_orani"] == 0.5 and r["yonlu"] == 1 and r["yon_isabeti"]["n"] == 1
        assert r["sonucu_bilinen"] == 2 and r["kiyas_al_tut"]["n"] == 2

    def test_hata_orani_ve_sayim(self, barlar, ayar, maliyet):
        r = self._rapor(
            barlar,
            ayar,
            maliyet,
            [
                (30, "timeout", None, np.nan),
                (31, "sema_hatasi", None, np.nan),
                (32, "gecerli", "long", 0.6),
            ],
        )
        assert (
            r["toplam_kayit"] == 3 and r["gecerli"] == 1 and r["hata_orani"] == pytest.approx(2 / 3)
        )
        assert r["sayim"] == {"timeout": 1, "sema_hatasi": 1, "gecerli": 1}

    def test_leak_riski_kanit_degil(self, barlar, ayar, maliyet):
        k = _kararlar(barlar, [(30, "gecerli", "long", 0.6)])
        k["leak_riski"] = True
        b = sonuclari_bagla(k, barlar, ayarlar=ayar, maliyet=maliyet)
        r = degerlendir(b, ayarlar=ayar)
        assert r["kanit"] is False and "K-074/3" in r["kanit_notu"]

    def test_bos_rapor(self, barlar, ayar, maliyet):
        b = sonuclari_bagla(_kararlar(barlar, []), barlar, ayarlar=ayar, maliyet=maliyet)
        r = degerlendir(b, ayarlar=ayar)
        assert r["toplam_kayit"] == 0 and r["yon_isabeti"]["oran"] is None and r["kanit"] is False

    def test_rejim_basina(self, barlar, ayar, maliyet):
        k = _kararlar(barlar, [(30, "gecerli", "long", 0.6), (31, "gecerli", "flat", 0.6)])
        k.loc[1, "rejim"] = "belirsiz"
        b = sonuclari_bagla(k, barlar, ayarlar=ayar, maliyet=maliyet)
        r = degerlendir(b, ayarlar=ayar)
        assert set(r["rejim_basina"]) == {"aralik", "belirsiz"}
        assert r["rejim_basina"]["belirsiz"]["yonlu"] == 0


def test_defterden_cerceve_bos():
    c = defterden_cerceve([])
    assert list(c.columns) == ["karar_ms", "durum_kodu", "yon"] and c.empty
