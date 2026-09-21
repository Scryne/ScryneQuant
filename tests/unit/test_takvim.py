"""Takvim seam'i (U15) ve K-080/U16 regresyon bekçileri. (K-083, R2 Paket 2)

Paket 2 takvim motoru yazmaz; `24x7`nin bugünkü ızgara/beklenen-bar davranışıyla **bit-aynı**
olduğunu ve takvimin hiçbir kimlik/hash yoluna girmediğini sabitler.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data import dogrulama
from scryne_quant.data.izgara import ortak_izgara
from scryne_quant.data.kimlik import TAKVIM_24X7 as KIMLIK_TAKVIM_24X7
from scryne_quant.data.takvim import KATALOG, TAKVIM_24X7, Takvim, TakvimHatasi, takvim
from tests.conftest import bar_uret

KOK = Path(__file__).resolve().parents[2]
SRC = KOK / "src" / "scryne_quant"
SAAT = timeframe_ms("1h")
BAS = 1_699_999_200_000  # `bar_uret` varsayılanı; 1h ızgarasına hizalı


class TestKatalog:
    def test_yalniz_24x7(self):
        assert list(KATALOG) == ["24x7"]
        assert TAKVIM_24X7 == KIMLIK_TAKVIM_24X7 == "24x7"  # enstrüman etiketi = katalog anahtarı

    def test_bilinmeyen_takvim_varsayilana_dusmez(self):
        with pytest.raises(TakvimHatasi, match="bilinmeyen takvim"):
            takvim("xnys")

    def test_seansli_takvim_bu_surumde_tanimsiz(self):
        with pytest.raises(TakvimHatasi, match="seanslı takvim"):
            Takvim(kimlik="fx-5x24", surekli=False, surum=1, aciklama="")

    def test_icerik_hashi_deterministik_ve_icerige_bagli(self):
        t = takvim("24x7")
        assert t.icerik_hash == nesne_hash(t.sozluk()) == takvim("24x7").icerik_hash
        assert Takvim("24x7", True, 2, t.aciklama).icerik_hash != t.icerik_hash  # sürüm içeriktir
        assert Takvim("24x7", True, 1, "başka").icerik_hash != t.icerik_hash


class TestBitAyni24x7:
    """Mevcut ızgara semantiğiyle eleman-eleman eşitlik — R4 bunları takvime bağladığında sabit."""

    @pytest.mark.parametrize("timeframe", ["1m", "1h", "4h", "1d"])
    def test_izgara_np_arange_ile_ayni(self, timeframe):
        adim = timeframe_ms(timeframe)
        bas = (BAS // adim) * adim
        beklenen = np.arange(bas, bas + 500 * adim, adim, dtype="int64")
        cikti = takvim("24x7").izgara(bas, bas + 500 * adim, timeframe)
        assert cikti.dtype == np.dtype("int64")
        assert np.array_equal(cikti, beklenen)

    def test_izgara_bossuz_seriyle_ortak_izgara_ile_ayni(self):
        df = bar_uret(300)
        zaman = df["open_time"].to_numpy(dtype="int64")
        mevcut = ortak_izgara([zaman], "1h")
        yeni = takvim("24x7").izgara(int(zaman[0]), int(zaman[-1]) + SAAT, "1h")
        assert np.array_equal(mevcut, yeni)

    def test_beklenen_bar_dogrulama_formulu_ile_ayni(self):
        """`dogrulama.py`: `(son − ilk) // adım + 1` — boşluklu seride de aynı sayı."""
        df = bar_uret(200)
        bosluklu = df.drop(index=range(50, 62)).reset_index(drop=True)
        _, rapor = dogrulama.dogrula(bosluklu, "1h")
        t = takvim("24x7")
        assert rapor.beklenen_bar == t.beklenen_bar(
            int(bosluklu["open_time"].iloc[0]), int(bosluklu["open_time"].iloc[-1]), "1h"
        )
        assert rapor.beklenen_bar == 200 and rapor.bar_sayisi == 188
        assert t.beklenen_bar(BAS, BAS, "1h") == 1  # tek bar

    def test_izgara_hizasiz_baslangic_red(self):
        with pytest.raises(TakvimHatasi, match="hizalı değil"):
            takvim("24x7").izgara(BAS + 1, BAS + SAAT, "1h")

    def test_izgara_ters_aralik_red_bos_aralik_bos(self):
        with pytest.raises(TakvimHatasi, match="bitiş"):
            takvim("24x7").izgara(BAS + SAAT, BAS, "1h")
        assert takvim("24x7").izgara(BAS, BAS, "1h").size == 0


#: Veri sonu / kimlik / hash yolları: takvimi **görmemeli** (U16 — K-080 semantiği değişmez).
KIMLIK_MODULLERI = (
    "data/depo.py",  # ParquetDepo.kirp (K-080 geri sarım)
    "research/deney.py",  # girdi_hash / cikti_hash / veri_son_ms
    "backtest/sonuc.py",  # sonuc_hash / config_hash
    "common/hash.py",
    "data/izgara.py",  # ortak_izgara / hizala — R4'te bağlanır, bugün değil
    "data/dogrulama.py",  # beklenen_bar — R4
    "backtest/metrikler.py",  # bar_yili — R4
)


class TestU16KimlikYollariTakvimsiz:
    @pytest.mark.parametrize("yol", KIMLIK_MODULLERI)
    def test_takvim_import_edilmiyor(self, yol):
        kaynak = (SRC / yol).read_text(encoding="utf-8")
        for dugum in ast.walk(ast.parse(kaynak)):
            if isinstance(dugum, ast.ImportFrom):
                assert dugum.module != "scryne_quant.data.takvim", yol
            if isinstance(dugum, ast.Import):
                assert all(a.name != "scryne_quant.data.takvim" for a in dugum.names), yol

    def test_kirp_bar_zamaniyla_keser_takvim_parametresi_yok(self):
        import inspect

        from scryne_quant.data.depo import ParquetDepo

        imza = inspect.signature(ParquetDepo.kirp)
        assert list(imza.parameters) == ["self", "sembol", "timeframe", "bitis_ms"]
