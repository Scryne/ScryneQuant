"""Ortak bar ızgarası ve PIT üyelik matrisi. (Faz 10, K-052/3, K-052/4)

Aylık evren tablosunu bar başına üyelik dizisine çevirmek görünüşte mekanik bir iş; iki
yerde sessizce yanlış olabiliyor ve ikisi de burada ölçülüyor:

1. **Var olmayan bar sıfırla doldurulursa** indikatörler onu bir fiyat sanar ve getiri
   −%100 çıkar. NaN "yok" demektir ve nedensel indikatörler onu zaten yayar.
2. **Üyelik ticker'a bağlanırsa** (K-052/4) `LUNAUSDT`in 2022-05 sonrası hâli, öncesinin
   hacmiyle evrene girer. Kimlik segmentlerine bağlanması şart.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scryne_quant.data.izgara import (
    IzgaraHatasi,
    hizala,
    ortak_izgara,
    uyeligi_barlara_kis,
    uyelik_matrisi,
)
from scryne_quant.data.kimlik import Enstruman
from scryne_quant.strategy.evren import LISTELENMEDI
from tests.conftest import bar_uret

SAAT = 3_600_000
BASLANGIC = 1_699_999_200_000


def _enstruman(sembol: str, bas: int, bit: int, kanonik: str | None = None) -> Enstruman:
    return Enstruman(
        kanonik_id=kanonik or f"binance:{sembol}:1",
        venue="binance",
        sembol=sembol,
        gecerli_baslangic_ms=bas,
        gecerli_bitis_ms=bit,
        bar_sayisi=(bit - bas) // SAAT,
        kirilma_ile_basladi=False,
    )


class TestOrtakIzgara:
    def test_birlesim_aliniyor(self):
        """Kesişim, evrenin tamamını en yeni üyesi kadar kısaltırdı."""
        a = BASLANGIC + np.arange(5) * SAAT
        b = BASLANGIC + np.arange(3, 8) * SAAT
        izgara = ortak_izgara([a, b], "1h")
        assert len(izgara) == 8
        assert izgara[0] == a[0] and izgara[-1] == b[-1]

    def test_sirali_ve_tekil(self):
        a = BASLANGIC + np.arange(5) * SAAT
        izgara = ortak_izgara([a, a], "1h")
        assert np.array_equal(izgara, a)

    def test_izgaraya_oturmayan_reddediliyor(self):
        """Faz 9'da ölçülmüştü: 2018-02 kesintisinden sonra bazı semboller ızgara dışına
        düşüyor (K-056). Sessizce kabul etmek, iki farklı barı aynı satıra yazardı."""
        a = BASLANGIC + np.arange(5) * SAAT
        b = a + 137
        with pytest.raises(IzgaraHatasi, match="ızgaraya oturmayan"):
            ortak_izgara([a, b], "1h")


class TestHizala:
    def test_eksik_barlar_nan_ve_listelenmedi(self):
        df = bar_uret(n=5, baslangic_ms=BASLANGIC + 2 * SAAT)
        izgara = BASLANGIC + np.arange(9) * SAAT
        diziler = hizala(df, izgara)

        assert len(diziler["close"]) == 9
        assert np.isnan(diziler["close"][0]) and np.isnan(diziler["close"][1])
        assert not np.isnan(diziler["close"][2])
        assert list(diziler["quality_status"][:2]) == [LISTELENMEDI, LISTELENMEDI]
        assert diziler["quality_status"][2] == "ok"

    def test_gercek_barlar_dokunulmamis(self):
        df = bar_uret(n=5, baslangic_ms=BASLANGIC)
        izgara = BASLANGIC + np.arange(7) * SAAT
        diziler = hizala(df, izgara)
        assert np.allclose(diziler["close"][:5], df["close"].to_numpy())
        assert np.array_equal(diziler["open_time"], izgara)

    def test_sifir_degil_nan(self):
        """Sıfır bir fiyattır; NaN "yok" demektir. Aradaki fark −%100 getiridir."""
        df = bar_uret(n=3, baslangic_ms=BASLANGIC)
        diziler = hizala(df, BASLANGIC + np.arange(6) * SAAT)
        assert np.isnan(diziler["open"][5])
        assert diziler["open"][5] != 0.0 or np.isnan(diziler["open"][5])

    def test_izgara_disi_bar_reddediliyor(self):
        df = bar_uret(n=3, baslangic_ms=BASLANGIC)
        with pytest.raises(IzgaraHatasi, match="ortak ızgarada yok"):
            hizala(df, BASLANGIC + np.arange(3) * SAAT + 137)

    def test_bos_df_tamamen_listelenmedi(self):
        izgara = BASLANGIC + np.arange(4) * SAAT
        diziler = hizala(pd.DataFrame(columns=["open_time"]), izgara)
        assert set(diziler["quality_status"]) == {LISTELENMEDI}


class TestUyelikMatrisi:
    def _tablo(self, satirlar: list[tuple[str, str]]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "ay": [a for _, a in satirlar],
                "sira": list(range(1, len(satirlar) + 1)),
                "kanonik_id": [k for k, _ in satirlar],
                "sembol": ["X" for _ in satirlar],
                "onceki_ay_quote_hacim": [1.0] * len(satirlar),
            }
        )

    def test_ay_boyunca_sabit(self):
        """M'nin üyeliği M−1'in verisiyle bir kez hesaplanır, ay içinde değişmez."""
        zamanlar = np.array(
            [
                int(np.datetime64("2024-03-01T00", "ms").astype("int64")),
                int(np.datetime64("2024-03-15T12", "ms").astype("int64")),
                int(np.datetime64("2024-04-01T00", "ms").astype("int64")),
            ],
            dtype="int64",
        )
        kimlik = _enstruman("AAAUSDT", int(zamanlar[0]) - SAAT, int(zamanlar[-1]) + SAAT)
        tablo = self._tablo([(kimlik.kanonik_id, "2024-03")])
        maske = uyelik_matrisi(tablo, zamanlar, {"AAAUSDT": [kimlik]})
        assert list(maske["AAAUSDT"]) == [True, True, False]

    def test_kimlik_kirilmasi_uyeligi_tasimiyor(self):
        """K-052/4: yeni kimlik, eskinin hacmiyle evrene giremez."""
        bas = int(np.datetime64("2024-03-01T00", "ms").astype("int64"))
        kirilma = int(np.datetime64("2024-03-16T00", "ms").astype("int64"))
        son = int(np.datetime64("2024-04-01T00", "ms").astype("int64"))
        zamanlar = np.array([bas, kirilma, son - SAAT], dtype="int64")
        eski = _enstruman("LUNAUSDT", bas, kirilma, "binance:LUNAUSDT:1")
        yeni = _enstruman("LUNAUSDT", kirilma, son, "binance:LUNAUSDT:2")
        # Tabloda **yalnızca eski kimlik** üye.
        tablo = self._tablo([("binance:LUNAUSDT:1", "2024-03")])
        maske = uyelik_matrisi(tablo, zamanlar, {"LUNAUSDT": [eski, yeni]})
        assert list(maske["LUNAUSDT"]) == [True, False, False]

    def test_tabloda_olmayan_sembol_uye_degil(self):
        """Bilinmiyorsa üye değildir; ters varsayım evren kuralını sessizce kaldırırdı."""
        zamanlar = np.array([BASLANGIC, BASLANGIC + SAAT], dtype="int64")
        kimlik = _enstruman("ZZZUSDT", BASLANGIC - SAAT, BASLANGIC + 5 * SAAT)
        maske = uyelik_matrisi(pd.DataFrame(), zamanlar, {"ZZZUSDT": [kimlik]})
        assert not maske["ZZZUSDT"].any()

    def test_gecerlilik_araligi_disinda_uyelik_yok(self):
        bas = int(np.datetime64("2024-03-01T00", "ms").astype("int64"))
        zamanlar = np.array([bas, bas + 10 * SAAT], dtype="int64")
        kimlik = _enstruman("AAAUSDT", bas, bas + 5 * SAAT)
        tablo = self._tablo([(kimlik.kanonik_id, "2024-03")])
        maske = uyelik_matrisi(tablo, zamanlar, {"AAAUSDT": [kimlik]})
        assert list(maske["AAAUSDT"]) == [True, False]

    def test_sirasiz_segment_reddediliyor(self):
        bas = BASLANGIC
        a = _enstruman("AAAUSDT", bas + 5 * SAAT, bas + 10 * SAAT, "id:2")
        b = _enstruman("AAAUSDT", bas, bas + 5 * SAAT, "id:1")
        with pytest.raises(IzgaraHatasi, match="sıralı değil"):
            uyelik_matrisi(
                pd.DataFrame(), np.array([bas], dtype="int64"), {"AAAUSDT": [a, b]}
            )


class TestUyeligiBarlaraKis:
    """Ay içi kesinti / ay ortası delist: üye ama barı yok. (Faz 12)"""

    def _diziler(self, kalite: list[str]) -> dict[str, np.ndarray]:
        return {"quality_status": np.array(kalite, dtype=object)}

    def test_bari_olmayan_saat_uyelikten_duser_ve_sayilir(self):
        uyelik = {"A": np.array([True, True, True, False]), "B": np.array([True] * 4)}
        diziler = {
            "A": self._diziler(["ok", LISTELENMEDI, "ok", LISTELENMEDI]),
            "B": self._diziler(["ok"] * 4),
        }
        kesik, dusen = uyeligi_barlara_kis(uyelik, diziler)
        assert kesik["A"].tolist() == [True, False, True, False]
        assert kesik["B"].tolist() == [True] * 4
        assert dusen == {"A": 1}  # üye olmayan boş bar sayılmaz

    def test_yalnizca_engelleyici(self):
        """K-037: üyelik hiçbir zaman False → True olmaz."""
        rng = np.random.default_rng(3)
        u = rng.random(500) < 0.5
        kalite = np.where(rng.random(500) < 0.2, LISTELENMEDI, "ok").astype(object)
        kesik, _ = uyeligi_barlara_kis({"A": u}, {"A": {"quality_status": kalite}})
        assert not (kesik["A"] & ~u).any()
        assert not (kesik["A"] & (kalite == LISTELENMEDI)).any()

