"""Aktif demo bot (K-134): gelecek görmeme, zamanlama, risk/fren, aracı güvenliği."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from scryne_quant.aktif import strateji as st
from scryne_quant.aktif.araci import AraciHatasi, KriptoPaper, MT5Araci
from scryne_quant.aktif.defter import Defter
from scryne_quant.aktif.dongu import HesapAyari, bayat_mi, tur
from scryne_quant.aktif.geriye import geriye, ozet
from scryne_quant.aktif.risk import FrenDurumu, RiskAyari, agirlik_adimi, giris_agirligi

ADIM = 900_000  # 15m


def seri(n: int = 600, tohum: int = 0, t0: int = 1_700_000_000_000) -> pd.DataFrame:
    rng = np.random.default_rng(tohum)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.002, n))
    lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.002, n))
    idx = pd.Index(t0 + ADIM * np.arange(n), name="open_time")
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)


# ------------------------------------------------------------ strateji


@pytest.mark.parametrize("ad", sorted(st.STRATEJILER))
def test_strateji_gelecegi_gormez(ad: str) -> None:
    """t'ye kadar kesilmiş veriyle t'nin kararı, tüm veriyle aynı; t sonrası bozulsa da."""
    df = seri()
    tam = st.yon_serisi(ad, df, yalniz_long=False)
    assert (tam != 0).any(), "strateji hiç sinyal üretmiyor — test anlamsız olur"
    for t in (250, 400, 599):
        kesik = st.yon_serisi(ad, df.iloc[: t + 1], yalniz_long=False)
        pd.testing.assert_series_equal(kesik, tam.iloc[: t + 1])
        bozuk = df.copy()
        bozuk.iloc[t + 1 :] *= 3.0
        pd.testing.assert_series_equal(
            st.yon_serisi(ad, bozuk, yalniz_long=False).iloc[: t + 1], tam.iloc[: t + 1]
        )


def test_yalniz_long_shortu_duze_cevirir() -> None:
    y = st.yon_serisi("ema_trend", seri(), yalniz_long=True)
    assert set(y.unique()) <= {0.0, 1.0}


def test_strateji_modulu_io_yapmaz() -> None:
    kaynak = Path(st.__file__).read_text(encoding="utf-8")
    for yasak in ("import requests", "import ccxt", "open(", "sqlite3", "scryne_quant.exchange"):
        assert yasak not in kaynak


# ------------------------------------------------------------ risk


def test_giris_agirligi_atr_ve_tavan() -> None:
    a = RiskAyari(islem_riski=0.01, atr_carpan=2.0, sembol_kaldirac=0.3, toplam_kaldirac=1.0)
    assert giris_agirligi(1, 0.01, a) == pytest.approx(0.3)  # 0,5 → tavan 0,3
    assert giris_agirligi(-1, 0.05, a) == pytest.approx(-0.1)
    assert giris_agirligi(1, 0.0, a) == 0.0


def test_agirlik_yon_degismedikce_dokunmaz_ve_toplam_tavan() -> None:
    a = RiskAyari(sembol_kaldirac=0.5, toplam_kaldirac=0.6)
    w = agirlik_adimi({"A": 0.4}, {"A": 1.0, "B": 1.0}, {"A": 0.001, "B": 0.001}, a, fren=False)
    assert w["A"] == 0.4  # yön aynı: boyut değişmez
    assert w["B"] == pytest.approx(0.2)  # yalnız kalan 0,2 sığar
    w = agirlik_adimi({"A": 0.4}, {"A": -1.0}, {"A": 0.001}, a, fren=False)
    assert w["A"] == pytest.approx(-0.5)  # dönüş: yeniden boyut
    w = agirlik_adimi({"A": 0.4}, {}, {}, a, fren=False)
    assert w["A"] == 0.4  # veri yoksa dokunma


def test_fren_hepsini_kapatir_ve_takvimle_kalkar() -> None:
    a = RiskAyari(gunluk_kayip=0.03, haftalik_kayip=0.08)
    f = FrenDurumu()
    pazartesi = 1_790_035_200_000  # 2026-09-22 00:00 UTC (Salı; aynı ISO haftası)
    assert f.guncelle(100.0, pazartesi, a) is None
    assert f.guncelle(96.9, pazartesi + 3_600_000, a) == "gunluk_kayip"
    assert agirlik_adimi({"A": 0.3}, {"A": 1.0}, {"A": 0.01}, a, fren=True) == {"A": 0.0}
    assert f.guncelle(96.9, pazartesi + 86_400_000, a) is None  # ertesi gün yeni taban
    assert f.guncelle(91.9, pazartesi + 2 * 86_400_000 + 1, a) == "haftalik_kayip"


# ------------------------------------------------------------ aracı


class SahteVeri:
    def __init__(self, df: pd.DataFrame, fiyat: float = 100.0) -> None:
        self.df, self.f = df, fiyat

    def sunucu_zamani_ms(self) -> int:
        return int(self.df.index[-1]) + 2 * ADIM

    def klines(self, sembol: str, tf: str, bas: int, bit: int) -> pd.DataFrame:
        d = self.df[(self.df.index >= bas) & (self.df.index < bit)]
        return d.reset_index().rename(columns={"index": "open_time"})

    def son_fiyat(self, sembol: str) -> float:
        return self.f


def test_paper_dolum_aleyhte_ucretli_ve_kalici(tmp_path: Path) -> None:
    p = KriptoPaper(tmp_path, sermaye=1000.0, ucret_bps=10, kayma_bps=5, veri=SahteVeri(seri()))
    d = p.emir("BTCUSDT", 2.0, "giris")
    assert d.fiyat == pytest.approx(100.05)  # alış daha pahalı
    assert d.ucret == pytest.approx(2.0 * 100.05 * 0.001)
    assert p.ozkaynak() == pytest.approx(1000 - 2 * 0.05 - d.ucret)
    ikinci = KriptoPaper(tmp_path, sermaye=999.0, ucret_bps=10, kayma_bps=5, veri=SahteVeri(seri()))
    assert ikinci.pozisyonlar() == {"BTCUSDT": 2.0}  # durum diskten
    with pytest.raises(AraciHatasi):
        ikinci.emir("BTCUSDT", -3.0, "cikis")  # spot: açığa satış yok


def test_bayat_veri() -> None:
    assert not bayat_mi(0, ADIM, 2 * ADIM)
    assert bayat_mi(0, ADIM, 4 * ADIM)


def test_tur_giris_yapar_bayati_atlar(tmp_path: Path) -> None:
    df = seri(tohum=3)
    veri = SahteVeri(df, fiyat=float(df["close"].iloc[-1]))
    p = KriptoPaper(tmp_path / "p", sermaye=10_000.0, ucret_bps=10, kayma_bps=5,
                    yalniz_long=False, veri=veri)
    ayar = HesapAyari("t", "kripto_paper", ("X",), "15m", "ema_trend", {}, RiskAyari())
    simdi = int(df.index[-1]) + ADIM + 5_000
    defter = Defter(tmp_path / "d")
    rapor = tur(p, ayar, defter, simdi)
    beklenen = st.yon_serisi("ema_trend", df, yalniz_long=False).iloc[-1]
    assert rapor["yonler"]["X"] == beklenen
    assert len(rapor["emirler"]) == 1 and np.sign(rapor["emirler"][0]["adet"]) == beklenen
    # Aynı yön, ikinci tur: işlem yok.
    assert tur(p, ayar, defter, simdi)["emirler"] == []
    # Veri bayatsa atla.
    assert "X" in tur(p, ayar, defter, simdi + 10 * ADIM)["atlanan"]
    defter.kapat()


def sahte_mt5(trade_mode: int) -> Any:
    return SimpleNamespace(
        ACCOUNT_TRADE_MODE_DEMO=0, ACCOUNT_MARGIN_MODE_RETAIL_HEDGING=2,
        TIMEFRAME_M1=1, TIMEFRAME_M5=5, TIMEFRAME_M15=15, TIMEFRAME_M30=30, TIMEFRAME_H1=60,
        TIMEFRAME_H4=240, TIMEFRAME_D1=1440,
        initialize=lambda **k: True, last_error=lambda: (0, ""),
        account_info=lambda: SimpleNamespace(trade_mode=trade_mode, margin_mode=0,
                                             currency="USD", equity=1000.0),
    )


def test_mt5_yalniz_demo() -> None:
    MT5Araci(mt5=sahte_mt5(0))
    with pytest.raises(AraciHatasi, match="DEMO"):
        MT5Araci(mt5=sahte_mt5(2))  # gerçek hesap


# ------------------------------------------------------------ backtest


def test_geriye_zamanlama_sonraki_acilis() -> None:
    """Karar bar k kapanışında → getiri açılış k+1'den açılış k+2'ye."""
    n = 80
    idx = pd.Index(1_700_000_000_000 + ADIM * np.arange(n), name="open_time")
    o = np.full(n, 100.0)
    o[61] = 110.0  # yalnız açılış 60→61 (+%10) ve 61→62 (−%9,1) hareketi
    df = pd.DataFrame({"open": o, "high": o * 1.001, "low": o * 0.999, "close": o}, index=idx)
    ayar = HesapAyari("t", "p", ("X",), "15m", "ema_trend", {}, RiskAyari(
        islem_riski=1.0, atr_carpan=1.0, sembol_kaldirac=1.0, toplam_kaldirac=1.0))

    orijinal = st.STRATEJILER["ema_trend"]
    st.STRATEJILER["ema_trend"] = lambda d, **k: pd.Series(
        np.where(np.arange(len(d)) == 60, 1.0, 0.0), index=d.index)
    try:
        s = geriye({"X": df}, ayar, yalniz_long=True, ucret_bps=0, kayma_bps=0)
    finally:
        st.STRATEJILER["ema_trend"] = orijinal
    # Bar 60 kapanışında long → açılış 61'den 62'ye tutulur (110 → 100): kayıp.
    assert s["ozkaynak"].iloc[-1] == pytest.approx(100 / 110)
    assert s["islem"].sum() == 2


def test_geriye_deterministik() -> None:
    b = {"A": seri(tohum=1), "B": seri(tohum=2)}
    ayar = HesapAyari("t", "p", ("A", "B"), "15m", "rsi_donus", {}, RiskAyari())
    s1 = geriye(b, ayar, yalniz_long=False, ucret_bps=10, kayma_bps=5)
    s2 = geriye(b, ayar, yalniz_long=False, ucret_bps=10, kayma_bps=5)
    pd.testing.assert_frame_equal(s1, s2)
    assert ozet(s1)["hafta"] >= 1


def test_mt5_paper_spreadden_dolar_ve_demo_ister(tmp_path: Path) -> None:
    from scryne_quant.aktif.araci import MT5Paper

    m = sahte_mt5(0)
    simdi = __import__("time").time()
    m.symbol_info_tick = lambda s: SimpleNamespace(bid=1.1000, ask=1.1002, time=simdi + 3 * 3600)
    m.symbol_info = lambda s: SimpleNamespace(visible=True, currency_profit="USD",
                                              trade_contract_size=100_000.0, volume_step=0.01,
                                              volume_min=0.05, volume_max=100.0)
    p = MT5Paper(tmp_path, sermaye=100_000.0, ucret_bps=0.0, kayma_bps=0.0,
                 sunucu_utc_farki_saat=3, mt5=m)
    d = p.emir("EURUSD", 1.0, "giris")
    assert d.fiyat == pytest.approx(1.1002)  # alış ask'tan
    assert p.ozkaynak() == pytest.approx(100_000.0 - 1.0 * 100_000 * 0.0001)  # yarım spread
    d = p.emir("EURUSD", -2.0, "donus")
    assert d.fiyat == pytest.approx(1.1000)  # satış bid'den
    assert p.pozisyonlar() == {"EURUSD": -1.0}
    m.account_info = lambda: SimpleNamespace(trade_mode=2, margin_mode=0, currency="USD",
                                             equity=1.0)
    with pytest.raises(AraciHatasi, match="DEMO"):
        p.emir("EURUSD", 1.0, "cikis")


def _mt5_usdjpy() -> Any:
    """USDJPY (kâr JPY) sahte terminali: bid 150,00 / ask 150,02, swap long +7 / short −21 puan."""
    import time as _t

    m = sahte_mt5(0)
    bilgi = SimpleNamespace(visible=True, currency_profit="JPY", trade_contract_size=100_000.0,
                            volume_step=0.01, volume_min=0.05, volume_max=100.0, point=0.001,
                            swap_mode=1, swap_long=7.0, swap_short=-21.0, swap_rollover3days=3)
    m.symbol_info = lambda s: bilgi if s == "USDJPY" else None
    m.symbol_select = lambda s, a: True
    m.symbol_info_tick = lambda s: SimpleNamespace(
        bid=150.00, ask=150.02, time=_t.time() + 3 * 3600)
    return m


def test_mt5_paper_kur_cevrimi_usdjpy(tmp_path: Path) -> None:
    """K-136: kote JPY nakdi JPY kasasında, özkaynak güncel kurla USD."""
    from scryne_quant.aktif.araci import MT5Paper

    p = MT5Paper(tmp_path, sermaye=100_000.0, ucret_bps=0.0, kayma_bps=0.0,
                 sunucu_utc_farki_saat=3, mt5=_mt5_usdjpy())
    assert p.birim_notional("USDJPY", 150.01) == pytest.approx(100_000.0)  # 1 lot = 100k USD
    p.emir("USDJPY", 1.0, "giris")
    # Yalnız yarım spread kaybı: 0,01 JPY × 100.000 / 150,01 ≈ 6,67 USD.
    assert p.ozkaynak() == pytest.approx(100_000.0 - 0.01 * 100_000 / 150.01)
    assert p._hesap.doviz["JPY"] == pytest.approx(-150.02 * 100_000)


def test_mt5_paper_swap_gece_yarisi_ve_uc_kat(tmp_path: Path) -> None:
    """Swap sunucu gece yarısında (UTC+3 → 21:00 UTC); Çarşamba gecesi üç kat; hafta sonu yok."""
    from scryne_quant.aktif.araci import MT5Paper

    p = MT5Paper(tmp_path, sermaye=100_000.0, ucret_bps=0.0, kayma_bps=0.0,
                 sunucu_utc_farki_saat=3, mt5=_mt5_usdjpy())
    p.emir("USDJPY", 2.0, "giris")
    sali_20 = 1_790_107_200_000  # 2026-09-22 20:00 UTC (Salı, sunucu 23:00)
    assert p.tahakkuk(sali_20) == 0.0  # ilk çağrı yalnız işaretler
    kur = 1 / 150.01
    # Salı gecesi (21:00 UTC geçildi): 2 lot × 7 puan × 0,001 × 100.000 = 1.400 JPY.
    assert p.tahakkuk(sali_20 + 2 * 3_600_000) == pytest.approx(1_400 * kur)
    # Çarşamba gecesi üç kat.
    assert p.tahakkuk(sali_20 + 26 * 3_600_000) == pytest.approx(3 * 1_400 * kur)
    # Cuma → Pazartesi: Perşembe ve Cuma geceleri (2 × 1.400); Cumartesi/Pazar yok.
    cuma_20 = sali_20 + 3 * 86_400_000
    p.tahakkuk(cuma_20 - 3_600_000)
    assert p.tahakkuk(cuma_20 + 3 * 86_400_000) == pytest.approx(1_400 * kur)
    assert p.swap_toplam() == pytest.approx((1 + 3 + 1 + 1) * 1_400 * kur)


def test_geriye_swap_gece_yarisi() -> None:
    """Sabit fiyatta long pozisyon yalnız swap öder; Çarşamba gecesi üç kat, hafta sonu yok."""
    gun = 86_400_000
    t0 = 1_790_035_200_000  # 2026-09-22 00:00 UTC (Salı)
    n = 24 * 7
    idx = pd.Index(t0 + 3_600_000 * np.arange(n), name="open_time")
    o = np.full(n, 100.0)
    df = pd.DataFrame({"open": o, "high": o * 1.001, "low": o * 0.999, "close": o}, index=idx)
    ayar = HesapAyari("t", "p", ("X",), "1h", "ema_trend", {}, RiskAyari(
        islem_riski=1.0, atr_carpan=1.0, sembol_kaldirac=1.0, toplam_kaldirac=1.0))
    orijinal = st.STRATEJILER["ema_trend"]
    st.STRATEJILER["ema_trend"] = lambda d, **k: pd.Series(1.0, index=d.index)
    try:
        s = geriye({"X": df}, ayar, yalniz_long=True, ucret_bps=0, kayma_bps=0,
                   swap={"X": (-0.0001, 0.0)}, sunucu_farki_ms=3 * 3_600_000, uc_kat_gun=3)
    finally:
        st.STRATEJILER["ema_trend"] = orijinal
    # Salı 00:00 → Pazartesi 23:00 UTC: Salı, Çarşamba (×3), Perşembe, Cuma ve Pazartesi
    # geceleri (sunucu gece yarısı 21:00 UTC); Cumartesi/Pazar yok → 1+3+1+1+1 = 7 gece.
    assert s["ozkaynak"].iloc[-1] == pytest.approx((1 - 0.0001) ** 4 * (1 - 0.0003))
    assert int(s.index[-1].timestamp() * 1000) - t0 == 7 * gun
