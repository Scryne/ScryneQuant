"""Binance adaptörü — ağa çıkmadan. (K-015)

Ağa çıkan bir test, ağ bozukken kırmızı yanar ve kod bozukken de kırmızı yanar; ikisini
ayırt edemeyen bir test hiçbir şey söylemez. Buradaki testler ccxt'nin HTTP çağrısını
yerine geçirerek **adaptörün kendi sözleşmesini** sınar: kapanmamış barın atılması,
`limit=1000`, alan eşleşmesi, hata sarma, önbellek.

`@pytest.mark.network` işaretli testler gerçek Binance'e çıkar; varsayılan koşuda
atlanmazlar ama `-m "not network"` ile ayrılabilirler.
"""

from __future__ import annotations

import ccxt
import pytest

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.exchange.binance import BinanceAdaptoru, kline_df
from scryne_quant.exchange.temel import SAYFA_BOYU, BorsaHatasi

BASLANGIC = 1_699_999_200_000  # 2023-11-14 22:00 UTC, 1h hizalı
ADIM = timeframe_ms("1h")


def ham_kline(acilis_ms: int, kapanis: float = 100.0) -> list:
    """Binance'in 12 alanlı kline dizisi. Fiyatlar **string** gelir — gerçekte olduğu gibi."""
    return [
        acilis_ms,
        "99.5",
        "101.0",
        "99.0",
        str(kapanis),
        "12.5",
        acilis_ms + ADIM - 1,  # close_time: kapsayıcı sınır
        "1250.0",
        42,
        "6.0",
        "600.0",
        "0",
    ]


class SahteCcxt:
    """ccxt.binance yerine geçen kukla. Yalnızca adaptörün kullandığı uçları taşır."""

    def __init__(self, klines: list[list], sunucu_ms: int, hata: Exception | None = None):
        self._klines = klines
        self._sunucu_ms = sunucu_ms
        self._hata = hata
        self.urls = {"api": {"public": ""}}
        self.klines_params: list[dict] = []
        self.zaman_cagrisi = 0
        self.exchange_info_cagrisi = 0

    def publicGetTime(self):  # noqa: N802 — ccxt'nin implicit metot adı
        self.zaman_cagrisi += 1
        return {"serverTime": self._sunucu_ms}

    def publicGetKlines(self, params):  # noqa: N802
        if self._hata is not None:
            raise self._hata
        self.klines_params.append(params)
        bas, bit = int(params["startTime"]), int(params["endTime"])
        secim = [k for k in self._klines if bas <= k[0] <= bit]
        return secim[: int(params["limit"])]

    def publicGetExchangeInfo(self, params):  # noqa: N802
        self.exchange_info_cagrisi += 1
        return {
            "symbols": [
                {
                    "status": "TRADING",
                    "filters": [
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
                        {"filterType": "LOT_SIZE", "stepSize": "0.00001000"},
                        {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
                    ],
                }
            ]
        }


def adaptor_kur(klines: list[list], sunucu_ms: int, hata: Exception | None = None):
    adaptor = BinanceAdaptoru(ipv4=False, deneme_sayisi=2)
    sahte = SahteCcxt(klines, sunucu_ms, hata)
    adaptor._borsa = sahte
    return adaptor, sahte


class TestKlineDonusumu:
    def test_string_fiyatlar_floata_cevriliyor(self):
        df = kline_df([ham_kline(BASLANGIC)])
        assert df["close"].dtype == "float64"
        assert df["open_time"].dtype == "int64"
        assert df["trades"].dtype == "int64"

    def test_alan_eslesmesi(self):
        """Binance dizisinde quote_volume 7., trades 8. sırada — karıştırılırsa sessiz hata."""
        df = kline_df([ham_kline(BASLANGIC, kapanis=100.5)])
        satir = df.iloc[0]
        assert satir["close"] == 100.5
        assert satir["quote_volume"] == 1250.0
        assert satir["trades"] == 42
        assert satir["volume"] == 12.5

    def test_kullanilmayan_alanlar_alinmiyor(self):
        df = kline_df([ham_kline(BASLANGIC)])
        assert "close_time" not in df.columns
        assert "taker_base" not in df.columns


class TestKapanmamisBar:
    def test_acik_bar_atiliyor(self):
        """Spike 1: REST her zaman devam eden barı son eleman olarak döndürüyor."""
        klines = [ham_kline(BASLANGIC + i * ADIM) for i in range(5)]
        # Sunucu saati son barın ortasında: o bar henüz kapanmadı.
        sunucu = BASLANGIC + 4 * ADIM + ADIM // 2
        adaptor, _ = adaptor_kur(klines, sunucu)

        df = adaptor.klines("BTCUSDT", "1h", BASLANGIC, BASLANGIC + 10 * ADIM)

        assert len(df) == 4
        assert int(df["open_time"].iloc[-1]) == BASLANGIC + 3 * ADIM

    def test_tam_kapanma_aninda_bar_kabul_edilir(self):
        """Sınır: `acilis + timeframe <= serverTime` kapanmış demektir."""
        klines = [ham_kline(BASLANGIC)]
        adaptor, _ = adaptor_kur(klines, BASLANGIC + ADIM)
        assert len(adaptor.klines("BTCUSDT", "1h", BASLANGIC, BASLANGIC + ADIM)) == 1

    def test_bir_ms_eksikse_bar_atilir(self):
        klines = [ham_kline(BASLANGIC)]
        adaptor, _ = adaptor_kur(klines, BASLANGIC + ADIM - 1)
        assert adaptor.klines("BTCUSDT", "1h", BASLANGIC, BASLANGIC + ADIM).empty


class TestIstekParametreleri:
    def test_limit_her_zaman_1000(self):
        """Spike 1/2: weight çağrı başına sabit; küçük sayfa istemek saf kayıp."""
        adaptor, sahte = adaptor_kur([ham_kline(BASLANGIC)], BASLANGIC + 10 * ADIM)
        adaptor.klines("BTCUSDT", "1h", BASLANGIC, BASLANGIC + ADIM)
        assert sahte.klines_params[0]["limit"] == SAYFA_BOYU == 1000

    def test_endtime_kapsayici_sinira_cevriliyor(self):
        """Bizim aralığımız dışlayıcı, Binance'inki kapsayıcı — fark 1 ms."""
        adaptor, sahte = adaptor_kur([ham_kline(BASLANGIC)], BASLANGIC + 10 * ADIM)
        adaptor.klines("BTCUSDT", "1h", BASLANGIC, BASLANGIC + 5 * ADIM)
        assert sahte.klines_params[0]["endTime"] == BASLANGIC + 5 * ADIM - 1

    def test_sembol_buyuk_harfe_cevriliyor(self):
        adaptor, sahte = adaptor_kur([ham_kline(BASLANGIC)], BASLANGIC + 10 * ADIM)
        adaptor.klines("btcusdt", "1h", BASLANGIC, BASLANGIC + ADIM)
        assert sahte.klines_params[0]["symbol"] == "BTCUSDT"

    def test_bos_aralik_aga_cikmiyor(self):
        adaptor, sahte = adaptor_kur([ham_kline(BASLANGIC)], BASLANGIC + 10 * ADIM)
        assert adaptor.klines("BTCUSDT", "1h", BASLANGIC, BASLANGIC).empty
        assert sahte.klines_params == []

    def test_bilinmeyen_timeframe_aga_cikmiyor(self):
        from scryne_quant.common.zaman import GecersizTimeframe

        adaptor, sahte = adaptor_kur([], BASLANGIC)
        with pytest.raises(GecersizTimeframe):
            adaptor.klines("BTCUSDT", "7h", BASLANGIC, BASLANGIC + ADIM)
        assert sahte.klines_params == []


class TestHataYonetimi:
    def test_kalici_hata_tekrarlanmiyor(self):
        """Geçersiz sembol aynı hatayı verecektir; tekrar denemek sebebi bulanıklaştırır."""
        adaptor, sahte = adaptor_kur([], BASLANGIC, hata=ccxt.BadSymbol("geçersiz sembol"))
        with pytest.raises(BorsaHatasi, match="BadSymbol"):
            adaptor.klines("YOKUSDT", "1h", BASLANGIC, BASLANGIC + ADIM)

    def test_ag_hatasi_sariliyor(self):
        adaptor, _ = adaptor_kur([], BASLANGIC, hata=ccxt.NetworkError("bağlantı koptu"))
        with pytest.raises(BorsaHatasi, match="denemede başarısız"):
            adaptor.klines("BTCUSDT", "1h", BASLANGIC, BASLANGIC + ADIM)

    def test_ccxt_disari_sizmiyor(self):
        """Üst katmanlar `ccxt` import etmek zorunda kalmasın; borsa değişince kod değişmesin."""
        adaptor, _ = adaptor_kur([], BASLANGIC, hata=ccxt.ExchangeError("bir şey"))
        with pytest.raises(BorsaHatasi):
            adaptor.klines("BTCUSDT", "1h", BASLANGIC, BASLANGIC + ADIM)

    def test_bozuk_server_time_yanit(self):
        adaptor, sahte = adaptor_kur([], BASLANGIC)
        sahte.publicGetTime = lambda: {"beklenmeyen": 1}
        with pytest.raises(BorsaHatasi, match="serverTime"):
            adaptor.sunucu_zamani_ms()


class TestOnbellek:
    def test_sunucu_zamani_onbelleklenir(self):
        """Bayat değer güvenli yöndedir: kapanmış barı kapanmamış sayar, tersini değil."""
        klines = [ham_kline(BASLANGIC + i * ADIM) for i in range(3)]
        adaptor, sahte = adaptor_kur(klines, BASLANGIC + 10 * ADIM)

        for _ in range(5):
            adaptor.klines("BTCUSDT", "1h", BASLANGIC, BASLANGIC + 3 * ADIM)

        assert sahte.zaman_cagrisi == 1

    def test_sembol_kurallari_onbelleklenir(self):
        """Spike 1/6: `load_markets()` 3,2 s sürüyor; her başlatmada ödenmemeli."""
        adaptor, sahte = adaptor_kur([], BASLANGIC)

        ilk = adaptor.sembol_kurallari("BTCUSDT")
        ikinci = adaptor.sembol_kurallari("btcusdt")

        assert sahte.exchange_info_cagrisi == 1
        assert ilk == ikinci
        assert (ilk.tick_size, ilk.step_size, ilk.min_notional) == (0.01, 0.00001, 5.0)


@pytest.mark.network
class TestGercekBinance:
    """Gerçek Binance'e çıkar. Spike 1'in ölçtüğü davranışın hâlâ geçerli olduğunu sınar."""

    def test_sunucu_saati_makul(self):
        from scryne_quant.common.zaman import simdi_ms

        adaptor = BinanceAdaptoru()
        fark = abs(adaptor.sunucu_zamani_ms() - simdi_ms())
        # Spike 1'de ölçülen −153 ms. 60 s'lik sınır saatin tamamen kaymış olmasını yakalar;
        # Faz 7'nin ±1000 ms imza toleransı ayrıca kontrol edilecek.
        assert fark < 60_000, f"yerel saat borsadan {fark} ms sapmış"

    def test_kapanmis_bar_geliyor(self):
        adaptor = BinanceAdaptoru()
        simdi = adaptor.sunucu_zamani_ms()
        bas = (simdi // ADIM) * ADIM - 10 * ADIM
        df = adaptor.klines("BTCUSDT", "1h", bas, simdi)

        assert not df.empty
        assert (df["open_time"] % ADIM == 0).all()
        # Hiçbiri açık olmamalı.
        assert (df["open_time"] + ADIM <= adaptor.sunucu_zamani_ms()).all()

    def test_sembol_kurallari(self):
        """Spike 1'de ölçülen: tick 0,01 · step 0,00001 · minNotional 5,00."""
        kural = BinanceAdaptoru().sembol_kurallari("BTCUSDT")
        assert kural.durum == "TRADING"
        assert kural.tick_size > 0 and kural.step_size > 0
        assert kural.min_notional > 0
