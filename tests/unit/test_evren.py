"""PIT evren tablosu. (K-052/3, Faz 9 bitti kriteri)

Roadmap Faz 9: *"`sq data evren` PIT evren tablosu üretiyor: bir ayın üyeliği yalnızca o aya
kadarki veriyle hesaplanıyor. Testle kanıtlı: gelecekteki veri bozulduğunda geçmiş üyelik bit
düzeyinde değişmiyor."* O kanıt `TestLookAhead`te.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scryne_quant.data.evren import EvrenHatasi, EvrenKurali, aylik_ozet, evren_tablosu, tablo_hash
from scryne_quant.data.kimlik import kimlikleri_kur, kirilmalar
from scryne_quant.data.semalar import BAR_SUTUNLARI

SAAT = 3_600_000
ESIK = {"asgari_eksik_bar": 24, "asgari_log_oran": 3.0}


def ms(s: str) -> int:
    return int(pd.Timestamp(s, tz="UTC").value // 1_000_000)


def seri(bas: str, bit: str, *, saatlik_hacim: float, fiyat: float = 10.0) -> pd.DataFrame:
    """`[bas, bit)` saatlik barlar, sabit fiyat ve sabit saatlik quote hacmi."""
    zaman = np.arange(ms(bas), ms(bit), SAAT, dtype="int64")
    n = zaman.size
    return pd.DataFrame(
        {
            "open_time": zaman,
            "open": np.full(n, fiyat),
            "high": np.full(n, fiyat * 1.01),
            "low": np.full(n, fiyat * 0.99),
            "close": np.full(n, fiyat),
            "volume": np.full(n, saatlik_hacim / fiyat),
            "quote_volume": np.full(n, saatlik_hacim),
            "trades": np.full(n, 10, dtype="int64"),
            "quality_status": pd.Series(["ok"] * n, dtype="string"),
        }
    ).loc[:, list(BAR_SUTUNLARI)]


def ozet_kur(seriler: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parcalar = []
    for sembol, df in sorted(seriler.items()):
        df = df.sort_values("open_time").reset_index(drop=True)
        kimlikler = kimlikleri_kur(df, "1h", sembol, kirilmalar(df, "1h", **ESIK))
        parcalar.append(aylik_ozet(df, kimlikler))
    return pd.concat(parcalar, ignore_index=True)


def evren(seriler, kural, son="2024-05"):
    return evren_tablosu(ozet_kur(seriler), kural, son_uye_ay=son)


def uyeler(tablo: pd.DataFrame, ay: str) -> list[str]:
    return tablo.loc[tablo["ay"] == ay, "sembol"].tolist()


@pytest.fixture
def temel():
    return {
        "AAAUSDT": seri("2024-01-01", "2024-05-01", saatlik_hacim=300.0),
        "BBBUSDT": seri("2024-01-01", "2024-05-01", saatlik_hacim=200.0),
        "CCCUSDT": seri("2024-01-01", "2024-05-01", saatlik_hacim=100.0),
    }


class TestUyelik:
    def test_onceki_ay_hacmine_gore_ilk_n(self, temel):
        tablo = evren(temel, EvrenKurali(ust_n=2, asgari_quote_hacim=0.0))
        assert uyeler(tablo, "2024-02") == ["AAAUSDT", "BBBUSDT"]
        assert tablo.loc[tablo["ay"] == "2024-02", "sira"].tolist() == [1, 2]
        assert "2024-01" not in set(tablo["ay"])  # ilk ayın öncesi yok

    def test_hacim_esigi(self, temel):
        # Ocak: 744 saat × 150 = 111.600 eşiği; CCC (74.400) altında.
        tablo = evren(temel, EvrenKurali(ust_n=10, asgari_quote_hacim=111_600.0))
        assert uyeler(tablo, "2024-02") == ["AAAUSDT", "BBBUSDT"]

    def test_ay_icinde_delist_edilen_sonraki_ay_uye_degil(self, temel):
        temel["DDDUSDT"] = seri("2024-01-01", "2024-02-15", saatlik_hacim=900.0)
        tablo = evren(temel, EvrenKurali(ust_n=10, asgari_quote_hacim=0.0))
        assert "DDDUSDT" in uyeler(tablo, "2024-02")  # Ocak sonunda işlem görüyordu
        assert "DDDUSDT" not in uyeler(tablo, "2024-03")  # Şubat sonunda görmüyordu

    def test_delist_edilen_gecmiste_kalir_hayatta_kalma_yanliligi_yok(self, temel):
        temel["DDDUSDT"] = seri("2024-01-01", "2024-02-15", saatlik_hacim=900.0)
        tablo = evren(temel, EvrenKurali(ust_n=1, asgari_quote_hacim=0.0))
        assert uyeler(tablo, "2024-02") == ["DDDUSDT"]

    def test_ay_icinde_listelenen_o_ay_uye_degil(self, temel):
        temel["EEEUSDT"] = seri("2024-02-10", "2024-05-01", saatlik_hacim=900.0)
        tablo = evren(temel, EvrenKurali(ust_n=10, asgari_quote_hacim=0.0))
        assert "EEEUSDT" not in uyeler(tablo, "2024-02")
        assert uyeler(tablo, "2024-03")[0] == "EEEUSDT"

    def test_kaldiracli_stabil_ve_baska_kote_dislanir(self, temel):
        for s in ("BTCUPUSDT", "USDCUSDT", "ETHBTC"):
            temel[s] = seri("2024-01-01", "2024-05-01", saatlik_hacim=10_000.0)
        tablo = evren(temel, EvrenKurali(ust_n=10, asgari_quote_hacim=0.0))
        assert not {"BTCUPUSDT", "USDCUSDT", "ETHBTC"} & set(tablo["sembol"])

    def test_esit_hacimde_sira_kanonik_idyle_bozulur(self):
        seriler = {
            s: seri("2024-01-01", "2024-03-01", saatlik_hacim=100.0)
            for s in ("ZZZUSDT", "AAAUSDT", "MMMUSDT")
        }
        tablo = evren(seriler, EvrenKurali(ust_n=3, asgari_quote_hacim=0.0), son="2024-02")
        assert uyeler(tablo, "2024-02") == ["AAAUSDT", "MMMUSDT", "ZZZUSDT"]


class TestKimlik:
    def test_kirilmadan_sonra_yeni_kimlik_eski_hacmi_devralmaz(self, temel):
        """LUNA vakası: eski varlık çöker, 17 gün boşluk, aynı ticker başka varlık."""
        eski = seri("2024-01-01", "2024-02-13", saatlik_hacim=5_000.0, fiyat=80.0)
        eski.loc[eski.index[-1], ["open", "close", "low"]] = 0.00005
        yeni = seri("2024-03-01", "2024-05-01", saatlik_hacim=50.0, fiyat=1.0)
        temel["LUNAUSDT"] = pd.concat([eski, yeni], ignore_index=True)

        tablo = evren(temel, EvrenKurali(ust_n=10, asgari_quote_hacim=0.0))

        subat = tablo[tablo["ay"] == "2024-02"]
        assert subat.loc[subat["sembol"] == "LUNAUSDT", "kanonik_id"].tolist() == [
            "binance-spot:LUNAUSDT@2024-01-01"
        ]
        assert "LUNAUSDT" not in uyeler(tablo, "2024-03")  # Şubat sonunda eski kimlik yok
        nisan = tablo[(tablo["ay"] == "2024-04") & (tablo["sembol"] == "LUNAUSDT")]
        assert nisan["kanonik_id"].tolist() == ["binance-spot:LUNAUSDT@2024-03-01"]
        assert nisan["onceki_ay_quote_hacim"].tolist() == [744 * 50.0]
        assert nisan["sira"].tolist() == [4]  # yeni kimliğin kendi hacmi: en küçük


class TestLookAhead:
    """Gelecekteki veri bozulduğunda geçmiş üyelik bit düzeyinde değişmiyor."""

    def test_mart_sonrasi_bozulma_mart_ve_oncesini_degistirmez(self, temel):
        temel["DDDUSDT"] = seri("2024-01-01", "2024-05-01", saatlik_hacim=150.0)
        kural = EvrenKurali(ust_n=2, asgari_quote_hacim=0.0)
        once = evren(temel, kural)

        kesim = ms("2024-03-01")
        bozuk = {}
        for s, df in temel.items():
            df = df.copy()
            gelecek = df["open_time"] >= kesim
            df.loc[gelecek, "quote_volume"] *= 1_000.0 if s == "CCCUSDT" else 0.001
            bozuk[s] = df
        # Gelecekte sahte bir kimlik kırılması ve bir sembolün gelecek barlarının silinmesi.
        a = bozuk["AAAUSDT"]
        a = a[(a["open_time"] < ms("2024-03-10")) | (a["open_time"] >= ms("2024-03-20"))].copy()
        a.loc[a["open_time"] >= ms("2024-03-20"), ["open", "high", "low", "close"]] *= 50_000
        bozuk["AAAUSDT"] = a
        b = bozuk["BBBUSDT"]
        bozuk["BBBUSDT"] = b[b["open_time"] < ms("2024-03-05")]
        sonra = evren(bozuk, kural)

        def gecmis(t):
            return t[t["ay"] <= "2024-03"].reset_index(drop=True)

        assert tablo_hash(gecmis(once)) == tablo_hash(gecmis(sonra))
        pd.testing.assert_frame_equal(gecmis(once), gecmis(sonra))
        # Bozulma gerçekten bir şey değiştirdi — test boş yere geçmiyor.
        assert tablo_hash(once) != tablo_hash(sonra)

    def test_son_uye_ay_sonrasi_uretilmez(self, temel):
        tablo = evren(temel, EvrenKurali(ust_n=3, asgari_quote_hacim=0.0), son="2024-03")
        assert tablo["ay"].max() == "2024-03"


class TestKural:
    def test_kimlik_her_alana_duyarli(self):
        taban = EvrenKurali(ust_n=50, asgari_quote_hacim=30e6)
        assert taban.kimlik == EvrenKurali(ust_n=50, asgari_quote_hacim=30e6).kimlik
        degisik = [
            EvrenKurali(ust_n=51, asgari_quote_hacim=30e6),
            EvrenKurali(ust_n=50, asgari_quote_hacim=31e6),
            EvrenKurali(ust_n=50, asgari_quote_hacim=30e6, kote="USDC"),
            EvrenKurali(ust_n=50, asgari_quote_hacim=30e6, haric_desenler=()),
            EvrenKurali(ust_n=50, asgari_quote_hacim=30e6, haric_tabanlar=("USDC",)),
            EvrenKurali(ust_n=50, asgari_quote_hacim=30e6, ay_sonu_tolerans_saat=48),
        ]
        assert len({taban.kimlik, *(k.kimlik for k in degisik)}) == 1 + len(degisik)

    @pytest.mark.parametrize(
        "alanlar",
        [
            {"ust_n": 0, "asgari_quote_hacim": 0.0},
            {"ust_n": 5, "asgari_quote_hacim": -1.0},
            {"ust_n": 5, "asgari_quote_hacim": 0.0, "ay_sonu_tolerans_saat": 0},
        ],
    )
    def test_gecersiz_kural(self, alanlar):
        with pytest.raises(EvrenHatasi):
            EvrenKurali(**alanlar)
