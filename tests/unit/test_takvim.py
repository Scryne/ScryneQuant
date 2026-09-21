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
from scryne_quant.common.zaman import timeframe_ms, utc_str
from scryne_quant.data import dogrulama
from scryne_quant.data.izgara import ortak_izgara
from scryne_quant.data.kimlik import TAKVIM_24X7 as KIMLIK_TAKVIM_24X7
from scryne_quant.data.takvim import (
    KATALOG,
    TAKVIM_24X7,
    TAKVIM_FX_5X24,
    Kapali,
    Seans,
    Takvim,
    TakvimHatasi,
    takvim,
)
from tests.conftest import bar_uret

KOK = Path(__file__).resolve().parents[2]
SRC = KOK / "src" / "scryne_quant"
SAAT = timeframe_ms("1h")
BAS = 1_699_999_200_000  # `bar_uret` varsayılanı; 1h ızgarasına hizalı


class TestKatalog:
    def test_katalog_24x7_ve_fx(self):
        assert list(KATALOG) == ["24x7", "fx-5x24"]
        assert TAKVIM_24X7 == KIMLIK_TAKVIM_24X7 == "24x7"  # enstrüman etiketi = katalog anahtarı

    def test_bilinmeyen_takvim_varsayilana_dusmez(self):
        with pytest.raises(TakvimHatasi, match="bilinmeyen takvim"):
            takvim("xnys")

    def test_seansli_takvim_seans_ister_surekli_seans_alamaz(self):
        with pytest.raises(TakvimHatasi, match="seans"):
            Takvim(kimlik="x", surekli=False, surum=1, aciklama="")
        with pytest.raises(TakvimHatasi, match="seans/kapalı"):
            Takvim("x", True, 1, "", seans=Seans("UTC", 6, 0, 4, 0))
        with pytest.raises(TakvimHatasi, match="ölçüm kapsamı"):
            Takvim("x", False, 1, "", seans=Seans("UTC", 6, 0, 4, 0), kapali=(Kapali(0, 1, "t"),))

    def test_24x7_sozlugu_r2_ile_ayni(self):
        """Seans alanları yalnız seanslı takvimde yazılır: 24x7 içerik hash'i R2'deki gibi."""
        assert list(takvim("24x7").sozluk()) == ["kimlik", "surekli", "surum", "aciklama"]
        assert takvim("24x7").icerik_hash == nesne_hash(
            {"kimlik": "24x7", "surekli": True, "surum": 1, "aciklama": takvim("24x7").aciklama}
        )

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
#: `izgara`/`dogrulama`/`metrikler` R4 Paket 1'de (K-093) takvime bağlandı — listeden çıktı;
#: 24x7 yolu bit-aynı (`test_takvim_baglama.py`).
KIMLIK_MODULLERI = (
    "data/depo.py",  # ParquetDepo.kirp (K-080 geri sarım)
    "research/deney.py",  # girdi_hash / cikti_hash / veri_son_ms
    "backtest/sonuc.py",  # sonuc_hash / config_hash
    "common/hash.py",
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


# ------------------------------------------------------------------ fx-5x24 (K-089)


def _ms(metin: str) -> int:
    import pandas as pd

    return int(pd.Timestamp(metin, tz="UTC").value // 1_000_000)


class TestFx5x24:
    def test_icerik_sabit_ve_olculmus_kapali_donemler(self):
        t = takvim(TAKVIM_FX_5X24)
        assert t.seans == Seans("America/New_York", 6, 17, 4, 17) and not t.surekli
        assert [(k.bas_ms, k.bit_ms) for k in t.kapali] == [
            (_ms("2023-12-25 01:00"), _ms("2023-12-26 05:00")),
            (_ms("2024-01-01 00:00"), _ms("2024-01-02 05:00")),
        ]
        assert t.olcum_kapsami == (_ms("2023-11-19 22:00"), _ms("2024-12-13 21:00"))
        assert t.icerik_hash == "16bafe1946d531946d02e63c35288ff4298647e68db70fe26d4605b171f4bdbf"
        assert set(t.sozluk()) == {"kimlik", "surekli", "surum", "aciklama", "seans", "kapali",
                                   "olcum_kapsami"}

    def test_dst_acilisi_utc_kayar(self):
        """Kış: Pazar 22:00 UTC; ABD yaz saati (10 Mart 2024'ten itibaren): 21:00 UTC (ölçüldü)."""
        t = takvim(TAKVIM_FX_5X24)
        kis = t.izgara(_ms("2024-03-03 00:00"), _ms("2024-03-04 02:00"), "1h")
        assert utc_str(int(kis[0])) == "2024-03-03 22:00:00 UTC"
        yaz = t.izgara(_ms("2024-03-10 00:00"), _ms("2024-03-11 02:00"), "1h")
        assert utc_str(int(yaz[0])) == "2024-03-10 21:00:00 UTC"
        # Cuma kapanış: kış 22:00 UTC'den itibaren kapalı (son bar 21:00), yaz 21:00 (son bar 20:00)
        kis_son = t.izgara(_ms("2024-03-08 18:00"), _ms("2024-03-10 00:00"), "1h")[-1]
        yaz_son = t.izgara(_ms("2024-03-15 18:00"), _ms("2024-03-17 00:00"), "1h")[-1]
        assert utc_str(int(kis_son)) == "2024-03-08 21:00:00 UTC"
        assert utc_str(int(yaz_son)) == "2024-03-15 20:00:00 UTC"

    def test_hafta_120_saat_hafta_sonu_yok(self):
        t = takvim(TAKVIM_FX_5X24)
        hafta = t.izgara(_ms("2024-01-07 00:00"), _ms("2024-01-14 00:00"), "1h")
        assert hafta.size == 120
        assert utc_str(int(hafta[0])) == "2024-01-07 22:00:00 UTC"
        assert utc_str(int(hafta[-1])) == "2024-01-12 21:00:00 UTC"
        assert np.all(np.diff(hafta) == SAAT)  # hafta içi kesintisiz
        assert t.beklenen_bar(int(hafta[0]), int(hafta[-1]), "1h") == 120
        assert not t.acik_mi(np.array([_ms("2024-01-13 12:00")]))[0]  # Cumartesi

    def test_kapali_donem_izgaradan_cikar_ve_isaretlenir(self):
        t = takvim(TAKVIM_FX_5X24)
        noel = t.izgara(_ms("2023-12-24 00:00"), _ms("2023-12-31 00:00"), "1h")
        assert noel.size == 120 - 28
        anlar = np.array([_ms("2023-12-25 12:00"), _ms("2023-12-27 12:00")])
        assert t.kapali_mi(anlar).tolist() == [True, False]
        assert t.olcum_icinde(_ms("2024-06-01 00:00"))
        assert not t.olcum_icinde(_ms("2025-06-01 00:00"))
        assert takvim("24x7").olcum_icinde(0)

    def test_gercek_depoyu_tam_aciklar(self):
        """Takvim + ölçülmüş kapanışlar, 55 haftalık gerçek EURUSD deposunu bar bar açıklar."""
        from scryne_quant.data.fx import FxDepo

        depo = FxDepo(KOK / "data" / "fx")
        if not depo.parquet_yolu("EURUSD").exists():
            pytest.skip("gerçek FX deposu yok (gitignore)")
        z = depo.oku("EURUSD")["open_time"].to_numpy()
        t = takvim(TAKVIM_FX_5X24)
        assert t.acik_mi(z).all()  # takvimin kapalı saydığı anda bar yok
        izg = set(t.izgara(int(z[0]), int(z[-1]) + SAAT, "1h").tolist()) - set(z.tolist())
        # Tek fark: sağlayıcının m1 dosyası olmayan 2024 h35 (25-30 Ağustos) — 120 saat.
        assert len(izg) in (0, 120)
