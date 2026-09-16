"""Kanonik enstrüman kimliği ve kimlik kırılması. (K-052/4, Faz 9 bitti kriteri)

**LUNAUSDT fixture'ı gerçek veri.** Değerler 2026-09-15'te `data.binance.vision` arşivinden
indirilen `LUNAUSDT-1h-2022-05.zip` dosyasının ilgili satırları (bkz. Faz 9 raporu): boşluktan
önceki üç bar ve sonraki üç bar. Roadmap Faz 9: *"LUNAUSDT 2022-05 vakası fixture olarak
testte, seri iki kimliğe bölünüyor."*

Eşikler bu testlerde **yalnızca test değeri**: tespit kuralının mantığını sınıyor. Üretimde
kullanılan değerler evren ölçümünden gelir ve ayrı bir testle korunur.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.kimlik import (
    KIRILMA_ASGARI_EKSIK_BAR,
    KIRILMA_ASGARI_LOG_ORAN,
    KimlikHatasi,
    bosluklar,
    kimlikleri_kur,
    kirilmalar,
)
from tests.conftest import bar_uret

SAAT = timeframe_ms("1h")


def _utc_ms(s: str) -> int:
    return int(pd.Timestamp(s, tz="UTC").value // 1_000_000)


#: Arşivden: (UTC açılış, open, close). Boşluk 2022-05-13 01:00 → 2022-05-31 05:00.
LUNA_GERCEK = [
    ("2022-05-12 22:00", 0.00409, 0.00240),
    ("2022-05-12 23:00", 0.00241, 0.00032),
    ("2022-05-13 00:00", 0.00032, 0.00005),
    ("2022-05-31 06:00", 1.00000, 8.55580),
    ("2022-05-31 07:00", 8.55580, 8.60630),
    ("2022-05-31 08:00", 8.60590, 8.49350),
]

ESIK = {"asgari_eksik_bar": 24, "asgari_log_oran": 3.0}


def luna_df() -> pd.DataFrame:
    satir = []
    for t, o, c in LUNA_GERCEK:
        satir.append(
            {
                "open_time": _utc_ms(t),
                "open": o,
                "high": max(o, c),
                "low": min(o, c),
                "close": c,
            }
        )
    return pd.DataFrame(satir)


class TestLunaVakasi:
    def test_seri_iki_kimlige_bolunuyor(self):
        df = luna_df()
        k = kirilmalar(df, "1h", sembol="LUNAUSDT", **ESIK)
        kimlikler = kimlikleri_kur(df, "1h", "LUNAUSDT", k)

        assert len(k) == 1
        assert [e.kanonik_id for e in kimlikler] == [
            "binance-spot:LUNAUSDT@2022-05-12",
            "binance-spot:LUNAUSDT@2022-05-31",
        ]
        eski, yeni = kimlikler
        assert eski.gecerli_bitis_ms == _utc_ms("2022-05-13 01:00")
        assert yeni.gecerli_baslangic_ms == _utc_ms("2022-05-31 06:00")
        assert not eski.kirilma_ile_basladi and yeni.kirilma_ile_basladi
        assert eski.bar_sayisi + yeni.bar_sayisi == len(df)

    def test_kirilmanin_olculen_buyuklugu(self):
        (k,) = kirilmalar(luna_df(), "1h", sembol="LUNAUSDT", **ESIK)
        assert k.eksik_bar == 437  # 18 gün 5 saat
        assert k.oran == pytest.approx(20_000.0)
        assert k.log_oran == pytest.approx(9.903, abs=1e-3)

    def test_kimlik_araliklari_ortusmez_ve_seriyi_kapsar(self):
        df = luna_df()
        kimlikler = kimlikleri_kur(df, "1h", "LUNAUSDT", kirilmalar(df, "1h", **ESIK))
        for once, sonra in zip(kimlikler, kimlikler[1:], strict=False):
            assert once.gecerli_bitis_ms <= sonra.gecerli_baslangic_ms


class TestTespitKurali:
    def _bosluklu(self, eksik_bar: int, carpan: float) -> pd.DataFrame:
        df = bar_uret(n=100)
        on, arka = df.iloc[:50].copy(), df.iloc[50:].copy()
        arka["open_time"] += eksik_bar * SAAT
        for s in ("open", "high", "low", "close"):
            arka[s] *= carpan
        return pd.concat([on, arka], ignore_index=True)

    def test_uzun_bosluk_normal_oran_kirilma_degil(self):
        """Borsa bakımı / askıya alma: fiyat kaldığı yerden devam eder."""
        df = self._bosluklu(eksik_bar=500, carpan=1.0)
        assert len(bosluklar(df, "1h")) == 1
        assert kirilmalar(df, "1h", **ESIK) == []

    def test_kisa_bosluk_buyuk_oran_kirilma_degil(self):
        """Boşluksuz ya da kısa boşluklu çöküş `suspect` kuralının konusu, kimliğin değil."""
        df = self._bosluklu(eksik_bar=3, carpan=1 / 50_000)
        assert kirilmalar(df, "1h", **ESIK) == []

    def test_iki_kosul_birden_kirilma(self):
        df = self._bosluklu(eksik_bar=500, carpan=1 / 50_000)
        assert len(kirilmalar(df, "1h", **ESIK)) == 1

    def test_yon_bagimsiz(self):
        yukari = self._bosluklu(eksik_bar=500, carpan=50_000)
        asagi = self._bosluklu(eksik_bar=500, carpan=1 / 50_000)
        (a,) = kirilmalar(yukari, "1h", **ESIK)
        (b,) = kirilmalar(asagi, "1h", **ESIK)
        assert a.log_oran == pytest.approx(b.log_oran, rel=1e-3)

    def test_bosluksuz_seri_tek_kimlik(self):
        df = bar_uret(n=200)
        kimlikler = kimlikleri_kur(df, "1h", "BTCUSDT", kirilmalar(df, "1h", **ESIK))
        assert len(kimlikler) == 1
        assert kimlikler[0].gecerli_bitis_ms == int(df["open_time"].iloc[-1]) + SAAT

    @pytest.mark.parametrize(
        "esik",
        [
            {"asgari_eksik_bar": 0, "asgari_log_oran": 3.0},
            {"asgari_eksik_bar": 24, "asgari_log_oran": 0.0},
        ],
    )
    def test_esiksiz_kirilma_tanimsiz(self, esik):
        with pytest.raises(KimlikHatasi):
            kirilmalar(bar_uret(n=10), "1h", **esik)


class TestOlculenEsikler:
    """Eşikler evren ölçümünden geldi (2026-09-16, 734 sembol, 3.598 boşluk). Bu test onları
    kilitler: değiştiren, ölçümü yeniden yapmak zorunda."""

    def test_esik_degerleri(self):
        assert KIRILMA_ASGARI_EKSIK_BAR == 12
        assert pytest.approx(math.log(10)) == KIRILMA_ASGARI_LOG_ORAN

    def test_luna_olculen_esiklerle_de_yakalaniyor(self):
        df = luna_df()
        k = kirilmalar(
            df,
            "1h",
            asgari_eksik_bar=KIRILMA_ASGARI_EKSIK_BAR,
            asgari_log_oran=KIRILMA_ASGARI_LOG_ORAN,
            sembol="LUNAUSDT",
        )
        assert len(k) == 1

    def test_2021_05_19_kesintisi_kirilma_sayilmaz(self):
        """Ölçülen yanlış-pozitif vakası: 4 barlık kesinti, |ln| 3,02 (XLMUPUSDT)."""
        df = bar_uret(n=40)
        on, arka = df.iloc[:20].copy(), df.iloc[20:].copy()
        arka["open_time"] += 4 * SAAT
        for s in ("open", "high", "low", "close"):
            arka[s] *= 0.04875
        bozuk = pd.concat([on, arka], ignore_index=True)
        assert (
            kirilmalar(
                bozuk,
                "1h",
                asgari_eksik_bar=KIRILMA_ASGARI_EKSIK_BAR,
                asgari_log_oran=KIRILMA_ASGARI_LOG_ORAN,
            )
            == []
        )


class TestKimlikKararliligi:
    def test_yeni_bar_eklenmesi_mevcut_kimlikleri_degistirmez(self):
        df = luna_df()
        once = kimlikleri_kur(df, "1h", "LUNAUSDT", kirilmalar(df, "1h", **ESIK))
        ek = pd.DataFrame(
            [
                {
                    "open_time": _utc_ms("2022-05-31 09:00"),
                    "open": 8.5,
                    "high": 8.7,
                    "low": 8.4,
                    "close": 8.6,
                }
            ]
        )
        uzun = pd.concat([df, ek], ignore_index=True)
        sonra = kimlikleri_kur(uzun, "1h", "LUNAUSDT", kirilmalar(uzun, "1h", **ESIK))
        assert [e.kanonik_id for e in once] == [e.kanonik_id for e in sonra]

    def test_sirasiz_seri_reddedilir(self):
        df = luna_df().iloc[::-1].reset_index(drop=True)
        with pytest.raises(KimlikHatasi, match="sıralı"):
            bosluklar(df, "1h")

    def test_seride_olmayan_kirilma_noktasi_reddedilir(self):
        df = luna_df()
        (k,) = kirilmalar(df, "1h", **ESIK)
        sahte = type(k)(
            k.sembol,
            k.onceki_son_ms,
            k.onceki_son_ms + SAAT,  # boşluğun içi: seride bar yok
            k.eksik_bar,
            k.onceki_kapanis,
            k.sonraki_acilis,
        )
        with pytest.raises(KimlikHatasi, match="bar değil"):
            kimlikleri_kur(df, "1h", "LUNAUSDT", [sahte])
