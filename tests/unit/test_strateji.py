"""`Strateji` sözleşmesi ve referans strateji (SMA kesişimi). (Faz 2)"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scryne_quant.data.semalar import BAR_SUTUNLARI, KaliteDurumu
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import PiyasaGorunumu
from scryne_quant.strategy.kosu import gorunum_kur, sinyalleri_uret
from scryne_quant.strategy.kutuphane.sma_kesisim import HIZLI, YAVAS, SmaKesisim
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji
from tests.conftest import bar_uret


def _diziler(n: int = 400, tohum: int = 5):
    return bar_dizileri(bar_uret(n=n, tohum=tohum))


class TestSozlesme:
    def test_soyut_metotlar_zorunlu(self):
        class Eksik(Strateji):
            pass

        with pytest.raises(TypeError):
            Eksik()

    def test_sozluk_kayit_icin_deterministik(self):
        """K-009: sonuç kaydına yazılan gösterim çalıştırmalar arasında aynı olmalı."""
        a = SmaKesisim(20, 50).sozluk()
        b = SmaKesisim(20, 50).sozluk()
        assert a == b
        assert a["ad"] == "sma_kesisim"
        assert a["sinif"].endswith("sma_kesisim.SmaKesisim")
        assert a["parametreler"] == {"hizli": 20, "maruziyet": 0.2, "yavas": 50}
        assert [o["indikator"] for o in a["ozellikler"]] == ["sma", "sma"]

    def test_parametre_dogrulamasi_kurulumda(self):
        """Geçersiz parametreli bir strateji hiç var olmamalı — 40. dakikada patlamamalı."""
        with pytest.raises(ValueError, match="yavas > hizli"):
            SmaKesisim(50, 20)
        with pytest.raises(ValueError, match="yavas > hizli"):
            SmaKesisim(20, 20)
        with pytest.raises(ValueError, match="hizli en az 2"):
            SmaKesisim(1, 50)
        with pytest.raises(ValueError, match="maruziyet"):
            SmaKesisim(20, 50, maruziyet=1.5)
        with pytest.raises(ValueError, match="maruziyet"):
            SmaKesisim(20, 50, maruziyet=0.0)

    def test_ozellik_bildirimi(self):
        tanimlar = SmaKesisim(10, 30).ozellikler()
        assert [t.ad for t in tanimlar] == [HIZLI, YAVAS]
        assert tanimlar[0] == OzellikTanimi(HIZLI, "sma", {"pencere": 10})


class TestSmaKesisim:
    def test_isinmadan_once_sinyal_yok(self):
        strateji = SmaKesisim(20, 50)
        gorunum = gorunum_kur("BTCUSDT", "1h", _diziler(), strateji)
        for i in range(50):
            assert strateji.on_bar(gorunum.baglam(i)) is None

    def test_sinyal_uretiliyor(self):
        strateji = SmaKesisim(20, 50)
        sinyaller = sinyalleri_uret(strateji, gorunum_kur("BTCUSDT", "1h", _diziler(), strateji))
        assert sinyaller, "referans strateji hiç sinyal üretmedi — test bir şey ölçmüyor"
        assert all(isinstance(s, Sinyal) for s in sinyaller)
        assert {s.reason for s in sinyaller} <= {
            "SMA_FAST_CROSSED_ABOVE_SLOW",
            "SMA_FAST_CROSSED_BELOW_SLOW",
        }

    def test_sinyal_zamani_bar_acilisi(self):
        """Sinyal "şu an"a değil, kararın verildiği bara ait (K-005)."""
        diziler = _diziler()
        strateji = SmaKesisim(20, 50)
        sinyaller = sinyalleri_uret(strateji, gorunum_kur("BTCUSDT", "1h", diziler, strateji))
        gecerli = set(diziler["open_time"].tolist())
        assert all(s.timestamp in gecerli for s in sinyaller)

    def test_kesisimler_donusumlu(self):
        """Aynı yön üst üste iki kez gelemez: kesişim tanımı gereği yön değiştirir.

        Arka arkaya iki `BUY`, ya kesişim mantığının ya da ısınma kontrolünün bozulduğunu
        gösterirdi — ve çift giriş, pozisyon büyüklüğünü sessizce ikiye katlardı.
        """
        strateji = SmaKesisim(20, 50)
        sinyaller = sinyalleri_uret(strateji, gorunum_kur("BTCUSDT", "1h", _diziler(), strateji))
        yonler = [s.side for s in sinyaller]
        assert all(a != b for a, b in zip(yonler, yonler[1:], strict=False))

    def test_kesisim_dogru_barda(self):
        """Elle kurulmuş bir kesişim: sinyal, kesişimin gerçekleştiği barda gelmeli."""
        n = 120
        kapanis = np.concatenate([np.linspace(100.0, 80.0, 60), np.linspace(80.0, 140.0, n - 60)])
        df = pd.DataFrame(
            {
                "open_time": 1_699_999_200_000 + np.arange(n, dtype="int64") * 3_600_000,
                "open": kapanis,
                "high": kapanis + 0.5,
                "low": kapanis - 0.5,
                "close": kapanis,
                "volume": np.full(n, 10.0),
                "quote_volume": np.full(n, 1000.0),
                "trades": np.full(n, 5, dtype="int64"),
                "quality_status": KaliteDurumu.OK,
            }
        ).loc[:, list(BAR_SUTUNLARI)]

        strateji = SmaKesisim(5, 20)
        gorunum = gorunum_kur("BTCUSDT", "1h", bar_dizileri(df), strateji)
        sinyaller = sinyalleri_uret(strateji, gorunum)

        assert [s.reason for s in sinyaller] == ["SMA_FAST_CROSSED_ABOVE_SLOW"]
        sinyal = sinyaller[0]
        i = int(np.where(gorunum.barlar["open_time"] == sinyal.timestamp)[0][0])

        hizli = gorunum.ozellikler[HIZLI]
        yavas = gorunum.ozellikler[YAVAS]
        assert hizli[i] > yavas[i]
        assert hizli[i - 1] <= yavas[i - 1]

    def test_giris_ve_cikis_tutarli(self):
        strateji = SmaKesisim(20, 50)
        for s in sinyalleri_uret(strateji, gorunum_kur("BTCUSDT", "1h", _diziler(), strateji)):
            if s.side is Yon.BUY:
                assert s.target_exposure == pytest.approx(0.2)
            else:
                assert s.side is Yon.FLAT
                assert s.target_exposure == 0.0

    def test_maruziyet_parametresi_sinyale_yansiyor(self):
        strateji = SmaKesisim(20, 50, maruziyet=0.35)
        sinyaller = sinyalleri_uret(strateji, gorunum_kur("BTCUSDT", "1h", _diziler(), strateji))
        alislar = [s for s in sinyaller if s.side is Yon.BUY]
        assert alislar
        assert all(s.target_exposure == pytest.approx(0.35) for s in alislar)

    def test_yalnizca_kapanmis_barla_calisiyor(self):
        """Strateji `t+1`in açılışını (fill fiyatı, K-004) ne bilir ne sorar."""
        diziler = _diziler()
        strateji = SmaKesisim(20, 50)
        gorunum = gorunum_kur("BTCUSDT", "1h", diziler, strateji)
        ctx = gorunum.baglam(100)
        # `on_bar` yalnızca `ctx` alıyor; `ctx`'in erişimcilerinde `t+1` diye bir konum yok.
        assert strateji.on_bar(ctx) is None or isinstance(strateji.on_bar(ctx), Sinyal)


class TestKosu:
    def test_gorunum_kur_stratejinin_ozelliklerini_hesapliyor(self):
        strateji = SmaKesisim(10, 30)
        gorunum = gorunum_kur("BTCUSDT", "1h", _diziler(), strateji)
        assert set(gorunum.ozellikler) == {HIZLI, YAVAS}

    def test_kosu_bos_ozellikli_stratejiyle_calisiyor(self):
        class Sessiz(Strateji):
            ad = "sessiz"

            def ozellikler(self):
                return ()

            def on_bar(self, ctx):
                return None

        strateji = Sessiz()
        gorunum = gorunum_kur("BTCUSDT", "1h", _diziler(n=50), strateji)
        assert isinstance(gorunum, PiyasaGorunumu)
        assert sinyalleri_uret(strateji, gorunum) == []

    def test_hazirla_her_kosuda_cagriliyor(self):
        class Sayan(Strateji):
            ad = "sayan"
            kosu = 0

            def ozellikler(self):
                return ()

            def hazirla(self):
                self.kosu += 1

            def on_bar(self, ctx):
                return None

        strateji = Sayan()
        gorunum = gorunum_kur("BTCUSDT", "1h", _diziler(n=30), strateji)
        sinyalleri_uret(strateji, gorunum)
        sinyalleri_uret(strateji, gorunum)
        assert strateji.kosu == 2
