"""PIT gözlem deposu. (K-052/5, Faz 9 bitti kriteri)

Roadmap Faz 9: *"Bar olmayan bir gözlem `available_time`e göre kesiliyor; `event_time`e göre
kesen bir uygulama testle reddediliyor. Gün çözünürlüklü kaynak gün sonuna yuvarlanıyor."*
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from scryne_quant.data.pit import (
    GUN_MS,
    Gozlem,
    GozlemDeposu,
    PitHatasi,
    gun_sonu_ms,
    kes,
    kesme_sozlesmesini_dogrula,
    tablo,
)

T = 1_700_000_000_000


class TestKesmeSozlesmesi:
    def test_available_time_kesicisi_gecer(self):
        kesme_sozlesmesini_dogrula(kes)

    def test_event_time_kesicisi_reddedilir(self):
        def event_time_kesici(df: pd.DataFrame, t: int) -> pd.DataFrame:
            gorunen = df[df["event_time_ms"] <= t].sort_values("available_time_ms")
            return gorunen.drop_duplicates("event_time_ms", keep="last")

        with pytest.raises(PitHatasi, match="sözleşmesine uymuyor"):
            kesme_sozlesmesini_dogrula(event_time_kesici)

    def test_ilk_revizyonu_sabitleyen_kesici_reddedilir(self):
        """Revizyonu hiç görmeyen (ilk açıklanan değerde donan) kesici de yanlış."""

        def ilk_deger(df: pd.DataFrame, t: int) -> pd.DataFrame:
            gorunen = df[df["available_time_ms"] <= t].sort_values("available_time_ms")
            return gorunen.drop_duplicates("event_time_ms", keep="first").iloc[:1]

        with pytest.raises(PitHatasi):
            kesme_sozlesmesini_dogrula(ilk_deger)

    def test_sinirda_strict_kesici_reddedilir(self):
        def strict(df: pd.DataFrame, t: int) -> pd.DataFrame:
            return kes(df, t - 1)

        with pytest.raises(PitHatasi):
            kesme_sozlesmesini_dogrula(strict)


class TestRevizyon:
    def _seri(self):
        return tablo(
            [
                Gozlem("cpi", T, T + 10 * GUN_MS, T + 30 * GUN_MS, 3.0),
                Gozlem("cpi", T, T + 20 * GUN_MS, T + 30 * GUN_MS, 3.2),
            ]
        )

    def test_revizyon_oncesi_ilk_deger_gorunur(self):
        assert kes(self._seri(), T + 15 * GUN_MS)["deger"].tolist() == [3.0]

    def test_revizyon_sonrasi_son_deger_gorunur(self):
        assert kes(self._seri(), T + 25 * GUN_MS)["deger"].tolist() == [3.2]

    def test_aciklanmadan_hicbir_sey_gorunmez(self):
        assert kes(self._seri(), T + 5 * GUN_MS).empty

    def test_gecmis_gorunum_revizyonla_degismez(self):
        """Revizyon eklemek, eski bir t'de görülen değeri değiştirmemeli."""
        ilk = tablo([Gozlem("cpi", T, T + 10 * GUN_MS, T + 11 * GUN_MS, 3.0)])
        once = kes(ilk, T + 15 * GUN_MS)
        sonra = kes(self._seri(), T + 15 * GUN_MS)
        pd.testing.assert_frame_equal(
            once.drop(columns="ingested_time_ms"), sonra.drop(columns="ingested_time_ms")
        )


class TestGunCozunurlugu:
    def test_gun_sonuna_yuvarlanir(self):
        g = Gozlem.gun_cozunurluklu(
            "alfred",
            event_gunu=dt.date(2024, 3, 31),
            available_gunu=dt.date(2024, 4, 10),
            ingested_time_ms=T,
            deger=1.0,
        )
        assert g.available_time_ms == int(
            dt.datetime(2024, 4, 10, 23, 59, 59, 999_000, tzinfo=dt.UTC).timestamp() * 1000
        )

    def test_aciklandigi_gunun_basinda_gorunmez(self):
        g = Gozlem.gun_cozunurluklu(
            "alfred",
            event_gunu=dt.date(2024, 3, 31),
            available_gunu=dt.date(2024, 4, 10),
            ingested_time_ms=T,
            deger=1.0,
        )
        df = tablo([g])
        gun_basi = gun_sonu_ms(dt.date(2024, 4, 10)) - GUN_MS + 1
        assert kes(df, gun_basi).empty
        assert kes(df, gun_basi + 12 * 3_600_000).empty
        assert kes(df, gun_sonu_ms(dt.date(2024, 4, 10)))["deger"].tolist() == [1.0]


class TestGozlemSozlesmesi:
    def test_olaydan_once_bilinemez(self):
        with pytest.raises(PitHatasi, match="önce olamaz"):
            Gozlem("x", event_time_ms=T, available_time_ms=T - 1, ingested_time_ms=T, deger=1.0)

    def test_effective_araligi_gecerli_olmali(self):
        with pytest.raises(PitHatasi):
            Gozlem("x", T, T, T, 1.0, effective_from_ms=T + 5, effective_to_ms=T + 5)

    def test_effective_filtresi(self):
        df = tablo(
            [
                Gozlem("liste", T, T, T, 1.0, effective_from_ms=T, effective_to_ms=T + GUN_MS),
                Gozlem("liste", T + 1, T + 1, T + 1, 0.0, effective_from_ms=T + GUN_MS),
            ]
        )
        assert kes(df, T + 100, effective=True)["deger"].tolist() == [1.0]
        assert kes(df, T + GUN_MS, effective=True)["deger"].tolist() == [0.0]


class TestDepo:
    def test_ekleme_idempotent_ve_revizyon_korunur(self, tmp_path):
        depo = GozlemDeposu(tmp_path)
        ilk = [Gozlem("cpi", T, T + GUN_MS, T + 2 * GUN_MS, 3.0)]
        assert depo.ekle("fred", ilk) == {"cpi": 1}
        yol = depo.yol("fred", "cpi")
        bayt = yol.read_bytes()

        assert depo.ekle("fred", ilk) == {"cpi": 0}
        assert yol.read_bytes() == bayt

        assert depo.ekle("fred", [Gozlem("cpi", T, T + 5 * GUN_MS, T + 6 * GUN_MS, 3.3)]) == {
            "cpi": 1
        }
        df = depo.oku("fred", "cpi")
        assert df["deger"].tolist() == [3.0, 3.3]
        assert kes(df, T + 2 * GUN_MS)["deger"].tolist() == [3.0]

    def test_yol_ayirici_reddedilir(self, tmp_path):
        with pytest.raises(PitHatasi):
            GozlemDeposu(tmp_path).yol("fred", "../kacis")
