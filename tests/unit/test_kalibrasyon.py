"""Slippage kalibrasyonu ve maliyet modeli. (K-021, K-007)

K-021'in kapanması bir sayıya değil, o sayının **nereden geldiğine** bağlı. Buradaki
testler iki şeyi sabitliyor: ölçümün tanımı (bilinen bir dağılımda bilinen bir sonuç
vermesi) ve kalibre edilmemiş modelin kendini `gecici` ilan etmesi.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.data.kalibrasyon import (
    KalibrasyonHatasi,
    hareket_bps,
    kalibre_et,
)
from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI, KaliteDurumu
from tests.conftest import bar_uret

BASLANGIC = 1_699_999_200_000


def bar_serisi(kapanislar: list[float], kalite: list[str] | None = None) -> pd.DataFrame:
    """Kapanış dizisinden elle kurulmuş bar serisi — beklenen sonucu hesaplanabilsin."""
    n = len(kapanislar)
    kapanis = np.array(kapanislar, dtype="float64")
    df = pd.DataFrame(
        {
            "open_time": BASLANGIC + np.arange(n, dtype="int64") * 60_000,
            "open": kapanis,
            "high": kapanis * 1.001,
            "low": kapanis * 0.999,
            "close": kapanis,
            "volume": np.full(n, 10.0),
            "quote_volume": kapanis * 10.0,
            "trades": np.full(n, 100, dtype="int64"),
        }
    )
    df["quality_status"] = pd.Series(kalite or [str(KaliteDurumu.OK)] * n, dtype="string")
    return df


class TestHareketOlcumu:
    def test_bilinen_dizide_bilinen_hareket(self):
        """100 → 101 = 100 bps; 101 → 100 = 99,0099 bps (payda önceki kapanış)."""
        h = hareket_bps(np.array([100.0, 101.0, 100.0]))
        assert h[0] == pytest.approx(100.0)
        assert h[1] == pytest.approx(10_000 / 101)

    def test_yon_onemsiz(self):
        """Slippage her zaman aleyhtedir; büyüklük ölçülür, işaret değil (K-007)."""
        yukari = hareket_bps(np.array([100.0, 102.0]))
        asagi = hareket_bps(np.array([102.0, 100.0]))
        assert yukari[0] > 0 and asagi[0] > 0

    def test_bir_kisa_doner(self):
        assert len(hareket_bps(np.arange(1.0, 11.0))) == 9


class TestPersentil:
    def test_bilinen_dagilimda_bilinen_persentil(self):
        """Sabit adımlı bir seride her hareket ~aynı; persentil de o değer olmalı."""
        kapanis = [100.0 * (1.001**i) for i in range(101)]  # her adım ~10 bps
        sonuc = kalibre_et(bar_serisi(kapanis), sembol="BTCUSDT")
        assert sonuc.deger_bps == pytest.approx(10.0, abs=0.01)

    def test_persentil_secimi_sonucu_degistirir(self):
        rng = np.random.default_rng(11)
        kapanis = list(100.0 * np.cumprod(1 + rng.normal(0, 0.001, 2_000)))
        veri = bar_serisi(kapanis)

        p50 = kalibre_et(veri, sembol="BTCUSDT", persentil=50).deger_bps
        p75 = kalibre_et(veri, sembol="BTCUSDT", persentil=75).deger_bps
        p95 = kalibre_et(veri, sembol="BTCUSDT", persentil=95).deger_bps

        assert p50 < p75 < p95

    def test_dagilim_tam_kaydediliyor(self):
        """Persentil kararı yeniden ölçüm gerektirmeden değişebilsin diye tam dağılım yazılır."""
        sonuc = kalibre_et(bar_serisi([100.0 + i for i in range(200)]), sembol="BTCUSDT")
        assert {"p50", "p75", "p90", "p95", "p99", "ort", "max"} <= set(sonuc.dagilim_bps)


class TestKaliteFiltresi:
    def test_sadece_ok_barlar_kullaniliyor(self):
        """Şüpheli bir bar dağılımın kuyruğunu tek başına taşıyabilir — ve slippage tam
        olarak kuyruktan okunan bir sayıdır."""
        kapanis = [100.0] * 50 + [10_000.0] + [100.0] * 50
        kalite = [str(KaliteDurumu.OK)] * 101
        kalite[50] = str(KaliteDurumu.SUSPECT)

        kirli = kalibre_et(bar_serisi(kapanis), sembol="BTCUSDT", persentil=99)
        temiz = kalibre_et(bar_serisi(kapanis, kalite), sembol="BTCUSDT", persentil=99)

        assert kirli.deger_bps > 1_000  # bozuk bar kuyruğu taşıdı
        assert temiz.deger_bps == pytest.approx(0.0)

    def test_bosluk_ustunden_hareket_atiliyor(self):
        """`gap` bayraklı bar `ok` olmadığı için hareket kendiliğinden düşer."""
        kapanis = [100.0 + i for i in range(20)]
        kalite = [str(KaliteDurumu.OK)] * 20
        kalite[10] = str(KaliteDurumu.GAP)

        sonuc = kalibre_et(bar_serisi(kapanis, kalite), sembol="BTCUSDT")
        # 19 olası hareketten ikisi (10'a giren ve 10'dan çıkan) düşer.
        assert sonuc.kullanilan_bar == 17

    def test_hic_temiz_cift_yoksa_hata(self):
        kalite = [str(KaliteDurumu.SUSPECT)] * 10
        with pytest.raises(KalibrasyonHatasi, match="ok"):
            kalibre_et(bar_serisi([100.0] * 10, kalite), sembol="BTCUSDT")

    def test_tek_bar_kalibre_edilemez(self):
        with pytest.raises(KalibrasyonHatasi, match="en az 2"):
            kalibre_et(bar_serisi([100.0]), sembol="BTCUSDT")


class TestDeterminizm:
    def test_ayni_veri_ayni_sonuc(self):
        veri = bar_uret(n=500, timeframe="1m", baslangic_ms=BASLANGIC)
        a = kalibre_et(veri, sembol="BTCUSDT")
        b = kalibre_et(veri, sembol="BTCUSDT")
        assert a.sozluk() == b.sozluk()

    def test_satir_sirasi_sonucu_degistirmez(self):
        veri = bar_uret(n=500, timeframe="1m", baslangic_ms=BASLANGIC)
        duz = kalibre_et(veri, sembol="BTCUSDT").deger_bps
        karisik = kalibre_et(
            veri.sample(frac=1, random_state=5).reset_index(drop=True), sembol="BTCUSDT"
        ).deger_bps
        assert duz == pytest.approx(karisik)

    def test_bayraksiz_veri_de_calisir(self):
        """Kalite sütunu yoksa hepsi kullanılır — ama bu yol yalnızca testler içindir."""
        veri = bar_uret(n=100, timeframe="1m", baslangic_ms=BASLANGIC)
        sonuc = kalibre_et(veri.loc[:, list(HAM_BAR_SUTUNLARI)], sembol="BTCUSDT")
        assert sonuc.kullanilan_bar == 99


class TestMaliyetModeli:
    def test_kalibrasyonsuz_model_gecici(self, tmp_path):
        yol = tmp_path / "maliyet.json"
        maliyet_mod.yaz(maliyet_mod.MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0), yol)
        model = maliyet_mod.yukle(yol)
        assert model.gecici is True
        assert model.sozluk()["gecici"] is True

    def test_kalibre_model_gecici_degil(self, tmp_path):
        yol = tmp_path / "maliyet.json"
        kalibrasyon = maliyet_mod.SlippageKalibrasyonu(
            yontem="test",
            persentil=75.0,
            deger_bps=5.01,
            sembol="BTCUSDT",
            timeframe="1m",
            aralik_baslangic_ms=BASLANGIC,
            aralik_bitis_ms=BASLANGIC + 60_000,
            bar_sayisi=2,
            veri_sha256="0" * 64,
            tarih="2026-09-09",
            gerekce="test",
        )
        maliyet_mod.yaz(
            maliyet_mod.MaliyetModeli(
                fee_taker_bps=10.0, slippage_bps=5.01, kalibrasyon=kalibrasyon
            ),
            yol,
        )
        model = maliyet_mod.yukle(yol)
        assert model.gecici is False
        assert model.gidis_donus_bps == pytest.approx(30.02)

    def test_gerekcesiz_kalibrasyon_reddedilir(self):
        """Gerekçesiz bir kalibrasyon, K-020'nin hatasını tekrarlamaya açık kapı bırakır."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            maliyet_mod.SlippageKalibrasyonu(
                yontem="test",
                persentil=75.0,
                deger_bps=5.0,
                sembol="BTCUSDT",
                timeframe="1m",
                aralik_baslangic_ms=0,
                aralik_bitis_ms=1,
                bar_sayisi=2,
                veri_sha256="0" * 64,
                tarih="2026-09-09",
                gerekce="",
            )

    def test_dosya_yoksa_varsayilana_dusmez(self, tmp_path):
        """Sessizce varsayılan bir maliyetle çalışmak K-007'nin engellediği şeyin ta kendisi."""
        with pytest.raises(FileNotFoundError, match="K-007"):
            maliyet_mod.yukle(tmp_path / "yok.json")

    def test_yazim_kararli(self, tmp_path):
        yol = tmp_path / "maliyet.json"
        model = maliyet_mod.MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
        maliyet_mod.yaz(model, yol)
        ilk = yol.read_bytes()
        maliyet_mod.yaz(maliyet_mod.yukle(yol), yol)
        assert yol.read_bytes() == ilk

    def test_negatif_maliyet_reddedilir(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            maliyet_mod.MaliyetModeli(fee_taker_bps=-1.0, slippage_bps=5.0)
