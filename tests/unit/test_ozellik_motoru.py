"""Özellik motoru ve bar dönüşümü. (Faz 2)"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scryne_quant.features import indikator as ind
from scryne_quant.features.barlar import BarHatasi, bar_dizileri
from scryne_quant.features.motor import DEFTER, OzellikHatasi, OzellikTanimi, hesapla
from tests.conftest import bar_uret


class TestBarDizileri:
    def test_kanonik_cerceve_cevriliyor(self, barlar: pd.DataFrame):
        d = bar_dizileri(barlar)
        assert d["open_time"].dtype == np.int64
        assert d["close"].dtype == np.float64
        assert len(d["close"]) == len(barlar)

    def test_diziler_yazilamaz(self, barlar: pd.DataFrame):
        """Aynı diziler hem özellik hesabına hem ctx'e gidiyor; yerinde değişiklik
        backtest'in her yerine sessizce yayılırdı."""
        d = bar_dizileri(barlar)
        with pytest.raises(ValueError, match="read-only"):
            d["close"][0] = 1.0

    def test_eksik_sutun_hata(self, barlar: pd.DataFrame):
        with pytest.raises(BarHatasi, match="eksik"):
            bar_dizileri(barlar.drop(columns=["volume"]))

    def test_bos_cerceve_hata(self, barlar: pd.DataFrame):
        with pytest.raises(BarHatasi, match="boş"):
            bar_dizileri(barlar.iloc[0:0])

    def test_sirasiz_zaman_hata(self, barlar: pd.DataFrame):
        """Sıra burada düzeltilmiyor: kanonikleştirme deponun işi, iki yerde yaşamamalı."""
        bozuk = barlar.iloc[::-1].reset_index(drop=True)
        with pytest.raises(BarHatasi, match="artan"):
            bar_dizileri(bozuk)

    def test_tekrarli_zaman_hata(self, barlar: pd.DataFrame):
        bozuk = barlar.copy()
        bozuk.loc[5, "open_time"] = bozuk.loc[4, "open_time"]
        with pytest.raises(BarHatasi):
            bar_dizileri(bozuk)


class TestTanim:
    def test_bilinmeyen_indikator(self):
        with pytest.raises(OzellikHatasi, match="bilinmeyen indikatör"):
            OzellikTanimi("x", "macd", {"pencere": 12})

    def test_eksik_parametre(self):
        with pytest.raises(OzellikHatasi, match="eksik"):
            OzellikTanimi("x", "sma", {})

    def test_taninmayan_parametre(self):
        with pytest.raises(OzellikHatasi, match="tanınmayan"):
            OzellikTanimi("x", "sma", {"pencere": 20, "alpha": 0.1})

    def test_gecersiz_ad(self):
        with pytest.raises(OzellikHatasi):
            OzellikTanimi("sma 20", "sma", {"pencere": 20})

    def test_parametreler_kanonik_ve_hashlenebilir(self):
        """Aynı tanım her zaman aynı config hash'ini vermeli (K-009)."""
        a = OzellikTanimi("bb", "bollinger", {"katsayi": 2.0, "pencere": 20})
        b = OzellikTanimi("bb", "bollinger", {"pencere": 20, "katsayi": 2.0})
        assert a == b
        assert hash(a) == hash(b)
        assert a.sozluk() == b.sozluk()

    def test_cok_ciktili_sutun_adlari(self):
        t = OzellikTanimi("bb", "bollinger", {"pencere": 20, "katsayi": 2.0})
        assert t.sutunlar == ("bb_alt", "bb_orta", "bb_ust")

    def test_tek_ciktili_sutun_adi(self):
        assert OzellikTanimi("hizli", "sma", {"pencere": 20}).sutunlar == ("hizli",)

    def test_true_range_parametresiz(self):
        assert OzellikTanimi("tr", "true_range").sutunlar == ("tr",)


class TestHesapla:
    def _diziler(self, n: int = 200):
        return bar_dizileri(bar_uret(n=n, tohum=3))

    def test_indikator_ciktisiyla_ayni(self):
        d = self._diziler()
        out = hesapla(d, [OzellikTanimi("e", "ema", {"pencere": 20})])
        np.testing.assert_array_equal(out["e"], ind.ema(d["close"], 20))

    def test_bollinger_uc_sutun(self):
        d = self._diziler()
        out = hesapla(d, [OzellikTanimi("bb", "bollinger", {"pencere": 20, "katsayi": 2.0})])
        assert set(out) == {"bb_alt", "bb_orta", "bb_ust"}
        b = ind.bollinger(d["close"], 20, 2.0)
        np.testing.assert_array_equal(out["bb_ust"], b.ust)

    def test_atr_high_low_close_aliyor(self):
        d = self._diziler()
        out = hesapla(d, [OzellikTanimi("a", "atr", {"pencere": 14})])
        np.testing.assert_array_equal(out["a"], ind.atr(d["high"], d["low"], d["close"], 14))

    def test_hacim_ortalamasi_hacimden_hesaplaniyor(self):
        """Yanlış seriye bakan bir kayıt sessiz bir hata olurdu; defter bunu sabitliyor."""
        d = self._diziler()
        out = hesapla(d, [OzellikTanimi("h", "hacim_sma", {"pencere": 20})])
        np.testing.assert_array_equal(out["h"], ind.sma(d["volume"], 20))
        assert not np.array_equal(out["h"][30:], ind.sma(d["close"], 20)[30:])

    def test_cikti_yazilamaz(self):
        out = hesapla(self._diziler(), [OzellikTanimi("e", "ema", {"pencere": 20})])
        with pytest.raises(ValueError, match="read-only"):
            out["e"][0] = 1.0

    def test_ayni_ad_iki_kez(self):
        d = self._diziler()
        with pytest.raises(OzellikHatasi, match="iki kez"):
            hesapla(
                d,
                [
                    OzellikTanimi("x", "sma", {"pencere": 20}),
                    OzellikTanimi("x", "ema", {"pencere": 20}),
                ],
            )

    def test_eksik_alan(self):
        d = self._diziler()
        del d["volume"]
        with pytest.raises(OzellikHatasi, match="eksik alan"):
            hesapla(d, [OzellikTanimi("e", "ema", {"pencere": 20})])

    def test_bos_tanim_listesi_bos_sozluk(self):
        assert hesapla(self._diziler(), []) == {}

    def test_defterdeki_her_indikator_hesaplanabiliyor(self):
        """Deftere eklenip hiç denenmemiş bir kayıt, ilk backtest'te patlardı.

        `funding` girdisi isteyen kayıtlar (K-042) için alan ayrıca veriliyor: o sütun
        kanonik bar şemasında yok, laboratuvar boru hattında ekleniyor.
        """
        d = dict(self._diziler())
        d["funding"] = np.linspace(-1e-4, 3e-4, d["close"].size)
        # Evren funding'inin ödeme dizisi (Faz 12, `data/funding.evren_dizileri`).
        d["funding_odeme"] = np.linspace(0.0, 1e-4, d["close"].size)
        varsayilan = {"pencere": 14, "katsayi": 2.0, "birikim": 5}
        for ad, kayit in DEFTER.items():
            tanim = OzellikTanimi(
                "x", ad, {p: varsayilan[p] for p in kayit.parametreler}
            )
            out = hesapla(d, [tanim])
            assert set(out) == set(tanim.sutunlar)
            assert all(v.dtype == np.float64 for v in out.values())

    def test_eksik_girdi_alani_acik_hata(self):
        """`funding` olmadan funding indikatörü istemek sessizce KeyError vermemeli."""
        with pytest.raises(OzellikHatasi, match="barlara_hizala"):
            hesapla(
                self._diziler(),
                [OzellikTanimi("f", "funding_persentil", {"pencere": 14})],
            )

    def test_determinizm(self):
        d = self._diziler()
        tanimlar = [
            OzellikTanimi("s", "sma", {"pencere": 20}),
            OzellikTanimi("bb", "bollinger", {"pencere": 20, "katsayi": 2.0}),
        ]
        a = hesapla(d, tanimlar)
        b = hesapla(d, tanimlar)
        for ad in a:
            np.testing.assert_array_equal(a[ad], b[ad])

    def test_kote_hacim_sma_hacim_sma_ile_ayni_fonksiyon(self):
        """`kote_hacim_sma` (Faz 10) yalnızca **girdi sütunu** bakımından farklı.

        Ayrı bir referans doğrulaması (K-026) gerekmiyor çünkü hesap `hacim_sma` ile aynı
        fonksiyon; ölçülmesi gereken tek şey, deftere yanlış sütunla kaydedilmemiş olması.
        Aynı seriyi iki sütuna koyup çıktıların birebir aynı olmasını bekliyoruz.
        """
        d = self._diziler()
        seri = d["volume"]
        ayni = dict(d) | {"volume": seri, "quote_volume": seri}
        a = hesapla(ayni, [OzellikTanimi("x", "hacim_sma", {"pencere": 10})])
        b = hesapla(ayni, [OzellikTanimi("x", "kote_hacim_sma", {"pencere": 10})])
        np.testing.assert_array_equal(a["x"], b["x"])

    def test_kote_hacim_sma_quote_volume_okuyor(self):
        """Negatif kontrol: iki sütun farklıysa çıktılar da farklı olmalı.

        Olmasaydı üstteki test, `kote_hacim_sma`nın hâlâ `volume` okuduğu bir dünyada da
        yeşil kalırdı.
        """
        d = self._diziler()
        farkli = dict(d) | {"quote_volume": d["volume"] * 3.0 + 1.0}
        a = hesapla(farkli, [OzellikTanimi("x", "hacim_sma", {"pencere": 10})])
        b = hesapla(farkli, [OzellikTanimi("x", "kote_hacim_sma", {"pencere": 10})])
        assert not np.array_equal(a["x"][20:], b["x"][20:])
