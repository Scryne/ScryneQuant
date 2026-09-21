"""R4 Paket 1 (K-093): takvim ızgara/bar_yili/gap/bayatlık hesaplarına bağlı; 24x7 yolu bit-aynı.

K-057 kalıbı: (1) **statik** — hesaplar takvim parametresi alıyor ve `24x7`/`None` yolu eski
ifadeyle aynı; (2) **referans** — aynı girdi, `takvim=None` ve `takvim("24x7")` ile bit düzeyinde
aynı çıktı (metrikler, `sonuc_hash`, kalite raporu, kırılma listesi, ortak ızgara); mevcut referans
fixture testleri (`test_backtest_referans`, `test_coklu_referans`) dokunulmadan geçiyor;
(3) seanslı takvimde (fx-5x24) davranış **farklı ve beklenen**: hafta sonu gap değil, seans dışı
damga reddedilir, kapalı piyasada sessizlik bayat değil, yıllık bar 120/168 ile ölçekli.
"""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from scryne_quant.backtest import metrikler as metrikler_mod
from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.backtest.metrikler import YIL_MS, bar_yili, hesapla
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data import dogrulama, izgara, kimlik
from scryne_quant.data import takvim as takvim_mod
from scryne_quant.data.takvim import TAKVIM_24X7, TAKVIM_FX_5X24, takvim
from scryne_quant.live.akis import Tazelik
from scryne_quant.strategy.kosu import evren_gorunum_kur
from tests.conftest import PlanliHedef, bar_uret
from tests.unit.test_maliyet_katalogu import SEMBOLLER, SENARYO, _bar_dizileri

SAAT = timeframe_ms("1h")
T24 = takvim(TAKVIM_24X7)
TFX = takvim(TAKVIM_FX_5X24)
ESIK = {"asgari_eksik_bar": 12, "asgari_log_oran": 2.302585092994046}


def _ms(metin: str) -> int:
    return int(pd.Timestamp(metin, tz="UTC").value // 1_000_000)


# ------------------------------------------------------------------ statik


class TestStatik:
    @pytest.mark.parametrize(
        "fn", [bar_yili, hesapla, dogrulama.dogrula, dogrulama.rapor_cikar, kimlik.bosluklar,
               kimlik.kirilmalar, izgara.ortak_izgara]
    )
    def test_hesaplar_takvim_parametresi_aliyor_varsayilan_none(self, fn):
        p = inspect.signature(fn).parameters["takvim"]
        assert p.default is None

    def test_yil_sabiti_takvimden_ve_ayni_deger(self):
        assert metrikler_mod.YIL_MS is takvim_mod.YIL_MS
        assert YIL_MS == 365.25 * 24 * 3_600_000

    def test_24x7_icerik_hashi_r2_ile_ayni(self):
        assert list(T24.sozluk()) == ["kimlik", "surekli", "surum", "aciklama"]
        assert T24.icerik_hash == takvim_mod.nesne_hash(T24.sozluk())

    def test_coklu_backtest_takvim_alani_kayda_girmiyor(self):
        assert inspect.signature(CokluBacktest.__init__).parameters["takvim"].default is None


# ------------------------------------------------------------------ referans: 24x7 ≡ None


class TestBitAyni24x7:
    @pytest.mark.parametrize("timeframe", ["1m", "1h", "4h", "1d"])
    def test_bar_yili(self, timeframe):
        adim = timeframe_ms(timeframe)
        assert bar_yili(adim, T24) == bar_yili(adim) == YIL_MS / adim
        assert T24.yillik_bar(adim) == YIL_MS / adim

    def _kosu(self, takvim):
        strateji = PlanliHedef(
            {h["bar"]: {s: float(a) for s, a in h["agirliklar"].items()}
             for h in SENARYO["hedefler"]}
        )
        diziler = {s: _bar_dizileri(SENARYO["barlar"][s]) for s in SEMBOLLER}
        n = len(diziler[SEMBOLLER[0]]["open_time"])
        gorunum = evren_gorunum_kur(
            "1h", diziler, {s: np.ones(n, dtype=bool) for s in SEMBOLLER}, strateji
        )
        m = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
        return CokluBacktest(strateji, m, takvim=takvim).calistir(gorunum)

    def test_motor_sonuc_ve_config_hash_ayni(self):
        eski, yeni = self._kosu(None), self._kosu(T24)
        assert eski.sonuc_hash == yeni.sonuc_hash and eski.config_hash == yeni.config_hash
        assert eski.metrikler.sozluk() == yeni.metrikler.sozluk()
        assert eski.metrikler.sharpe == yeni.metrikler.sharpe  # yıllıklandırma aynı sayı

    def test_hesapla_metrikleri_bit_ayni(self):
        oz = np.cumprod(1 + np.random.default_rng(1).normal(0, 0.001, 500)) * 10_000
        maruz = np.full(500, 0.5)
        a = hesapla(oz, maruz, [], SAAT, 10_000.0)
        b = hesapla(oz, maruz, [], SAAT, 10_000.0, takvim=T24)
        assert a.sozluk() == b.sozluk()

    def test_dogrulama_raporu_ve_bayraklar_ayni(self):
        df = bar_uret(300).drop(index=range(40, 47)).drop(index=range(120, 121))
        df = df.reset_index(drop=True)
        (d1, r1), (d2, r2) = dogrulama.dogrula(df, "1h"), dogrulama.dogrula(df, "1h", takvim=T24)
        assert r1.sozluk() == r2.sozluk() and r1.bosluk_sayisi == 2
        assert list(d1["quality_status"]) == list(d2["quality_status"])
        assert dogrulama.rapor_cikar(d1, "1h").sozluk() == (
            dogrulama.rapor_cikar(d1, "1h", takvim=T24).sozluk()
        )
        assert r1.bosluklar[0].eksik_bar == 7 and r1.beklenen_bar == 300

    def test_kirilma_ve_bosluk_listesi_ayni(self):
        from tests.unit.test_kimlik import luna_df

        df = luna_df()
        assert [b.sozluk() for b in kimlik.bosluklar(df, "1h")] == [
            b.sozluk() for b in kimlik.bosluklar(df, "1h", takvim=T24)
        ]
        assert [k.sozluk() for k in kimlik.kirilmalar(df, "1h", **ESIK)] == [
            k.sozluk() for k in kimlik.kirilmalar(df, "1h", takvim=T24, **ESIK)
        ]
        assert kimlik.kirilmalar(df, "1h", **ESIK)[0].eksik_bar == 437  # LUNA boşluğu (Faz 9)

    def test_ortak_izgara_ayni(self):
        ikinci = bar_uret(80, baslangic_ms=1_699_999_200_000 + 50 * SAAT)
        z = [bar_uret(100)["open_time"].to_numpy(), ikinci["open_time"].to_numpy()]
        eski, yeni = izgara.ortak_izgara(z, "1h"), izgara.ortak_izgara(z, "1h", takvim=T24)
        assert np.array_equal(eski, yeni)

    def test_tazelik_ayni(self):
        a, b = Tazelik(60_000), Tazelik(60_000, takvim=T24)
        for t in (a, b):
            t.nabiz(1_000_000)
        assert a.bayat_mi(1_050_000) == b.bayat_mi(1_050_000) is False
        assert a.bayat_mi(1_070_000) == b.bayat_mi(1_070_000) is True
        assert Tazelik(60_000, takvim=T24).bayat_mi(0) is True  # nabız yok → bayat


# ------------------------------------------------------------------ seanslı: fx-5x24


class TestSeansliFx:
    def test_bar_yili_haftalik_saat_orani(self):
        assert TFX.haftalik_saat() == 120.0 and T24.haftalik_saat() == 168.0
        assert bar_yili(SAAT, TFX) == pytest.approx(YIL_MS / SAAT * 120 / 168)
        assert bar_yili(SAAT, TFX) == pytest.approx(6261.43, abs=0.01)

    def _fx_seri(self):
        """İki hafta, hafta sonu boşluklu (Cuma 21:00 → Pazar 22:00), Salı 10:00 barı eksik."""
        h1 = np.arange(_ms("2024-01-07 22:00"), _ms("2024-01-12 22:00"), SAAT)
        h2 = np.arange(_ms("2024-01-14 22:00"), _ms("2024-01-19 22:00"), SAAT)
        z = np.concatenate([h1, h2])
        z = z[z != _ms("2024-01-16 10:00")]
        df = bar_uret(len(z))
        df["open_time"] = z
        return df

    def test_gap_hafta_sonunu_saymiyor_hafta_ici_eksigi_sayiyor(self):
        df = self._fx_seri()
        _, r24 = dogrulama.dogrula(df, "1h")
        _, rfx = dogrulama.dogrula(df, "1h", takvim=TFX)
        assert r24.bosluk_sayisi == 2  # hafta sonu + Salı
        assert rfx.bosluk_sayisi == 1 and rfx.bosluklar[0].eksik_bar == 1
        assert rfx.beklenen_bar == 240 and r24.beklenen_bar == 240 + 48
        assert rfx.bar_sayisi == 239

    def test_kirilma_hafta_sonunu_bosluk_saymiyor(self):
        df = self._fx_seri()
        b24 = kimlik.bosluklar(df, "1h")
        bfx = kimlik.bosluklar(df, "1h", takvim=TFX)
        assert [b.eksik_bar for b in b24] == [48, 1] and [b.eksik_bar for b in bfx] == [1]

    def test_ortak_izgara_seans_disi_damgayi_reddeder(self):
        z = self._fx_seri()["open_time"].to_numpy()
        assert np.array_equal(izgara.ortak_izgara([z], "1h", takvim=TFX), z)
        cumartesi = np.append(z, _ms("2024-01-13 12:00"))
        with pytest.raises(izgara.IzgaraHatasi, match="seans dışı"):
            izgara.ortak_izgara([np.sort(cumartesi)], "1h", takvim=TFX)

    def test_tazelik_kapali_piyasada_bayat_degil(self):
        t = Tazelik(60_000, takvim=TFX)
        t.nabiz(_ms("2024-01-12 21:59"))  # Cuma kapanış öncesi son nabız
        assert t.bayat_mi(_ms("2024-01-13 12:00")) is False  # Cumartesi: kapalı
        assert t.bayat_mi(_ms("2024-01-14 22:05")) is True  # Pazar açılış: 2 gün sessizlik bayat
        assert Tazelik(60_000, takvim=TFX).bayat_mi(_ms("2024-01-13 12:00")) is True  # nabız yok
