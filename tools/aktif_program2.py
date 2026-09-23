"""Aktif demo — Program 2: literatür etkileri (K-137).

Ön kayıt: `docs/research/records/2026-09-23-aktif-program2-onkayit.md` (koşudan önce commit'li,
`e3c31e9`). Tanımlar, maliyetler, test ve karar kuralı oradadır; bu betik yalnız uygular.

    .venv/Scripts/python.exe tools/aktif_program2.py

Çıktı: `docs/research/records/2026-09-23-aktif-program2-sonuc.json` (+ MT5 verisi `runs/aktif/p2/`).
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

KOK = Path(__file__).resolve().parents[1]
SONUC = KOK / "docs/research/records/2026-09-23-aktif-program2-sonuc.json"
VERI = KOK / "runs/aktif/p2"
NY = "America/New_York"
SUNUCU_FARKI_S = 3 * 3600  # Integral MT5 sunucusu sabit UTC+3 (ön kayıtta ölçüldü)
H1_BASLANGIC = pd.Timestamp("2021-04-01", tz="UTC")
ALFA = 0.05
NW_GECIKME = 5
ENDEKSLER = ("S&P", "NASDAQ", "DJI")
B1_SEMBOLLER = ("EURUSD", "GBPUSD", "USDCHF", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD",
                "XAUUSD", "S&P", "NASDAQ", "DJI")
KOMISYON_BPS = 0.5
EK_KAYMA_BPS = 0.5


# ------------------------------------------------------------------ veri


def mt5_baglan() -> Any:
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise SystemExit(f"MT5 bağlantısı yok: {mt5.last_error()}")
    if mt5.account_info().trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise SystemExit("yalnız demo hesap")
    return mt5


def mt5_bar(mt5: Any, sembol: str, tf: str) -> pd.DataFrame:
    """UTC açılış zamanlı barlar; koşu anında çekilir ve `runs/aktif/p2`ye yazılır (iz için)."""
    kod = {"H1": mt5.TIMEFRAME_H1, "D1": mt5.TIMEFRAME_D1}[tf]
    mt5.symbol_select(sembol, True)
    r = mt5.copy_rates_from_pos(sembol, kod, 1, 42_000 if tf == "H1" else 9_800)
    if r is None or not len(r):
        raise SystemExit(f"{sembol} {tf}: veri yok {mt5.last_error()}")
    df = pd.DataFrame(r)
    df["sunucu"] = pd.to_datetime(df["time"], unit="s")
    df["utc"] = pd.to_datetime(df["time"] - SUNUCU_FARKI_S, unit="s", utc=True)
    df = df.set_index("utc")[["sunucu", "open", "high", "low", "close"]].sort_index()
    VERI.mkdir(parents=True, exist_ok=True)
    df.to_parquet(VERI / f"{sembol.replace('&', '')}_{tf}.parquet")
    return df


def maliyet_bps(mt5: Any, sembol: str) -> float:
    """Taraf başı: yarım spread (şimdi) + komisyon + ek kayma (ön kayıt)."""
    t = mt5.symbol_info_tick(sembol)
    orta = (t.bid + t.ask) / 2
    return (t.ask - t.bid) / orta * 1e4 / 2 + KOMISYON_BPS + EK_KAYMA_BPS


def swap_orani(mt5: Any, sembol: str) -> tuple[float, float]:
    """Gecelik swap, notional kesri (long, short); swap yoksa (0, 0)."""
    b = mt5.symbol_info(sembol)
    if int(b.swap_mode) != 1:
        return (0.0, 0.0)
    t = mt5.symbol_info_tick(sembol)
    f = (t.bid + t.ask) / 2
    return (float(b.swap_long) * float(b.point) / f, float(b.swap_short) * float(b.point) / f)


def yahoo(sembol: str) -> pd.DataFrame:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sembol}"
           f"?period1=0&period2={int(time.time())}&interval=1d&events=div")
    j = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30).json()
    r = j["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame({"open": q["open"], "close": q["close"],
                       "adjclose": r["indicators"]["adjclose"][0]["adjclose"]},
                      index=pd.to_datetime(r["timestamp"], unit="s", utc=True).tz_convert(NY).date)
    df.index = pd.to_datetime(df.index)
    df["temettu"] = 0.0
    for d in (r.get("events", {}).get("dividends", {}) or {}).values():
        gun = pd.Timestamp(pd.to_datetime(d["date"], unit="s", utc=True).tz_convert(NY).date())
        if gun in df.index:
            df.loc[gun, "temettu"] = float(d["amount"])
    df = df.dropna(subset=["open", "close"])
    VERI.mkdir(parents=True, exist_ok=True)
    df.to_parquet(VERI / f"yahoo_{sembol}.parquet")
    return df


# ------------------------------------------------------------------ istatistik


def nw_t(x: np.ndarray, gecikme: int = NW_GECIKME) -> float:
    """Ortalamanın Newey-West t istatistiği (Bartlett ağırlıkları)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 10:
        return float("nan")
    e = x - x.mean()
    s = float(e @ e) / n
    for k in range(1, gecikme + 1):
        s += 2 * (1 - k / (gecikme + 1)) * float(e[k:] @ e[:-k]) / n
    return float(x.mean() / math.sqrt(s / n)) if s > 0 else float("nan")


def tek_yonlu_p(t: float) -> float:
    return 0.5 * math.erfc(t / math.sqrt(2)) if t == t else 1.0


def ozet(gunluk: pd.Series, islem_sayisi: int) -> dict[str, Any]:
    g = gunluk.dropna()
    eq = (1 + g).cumprod()
    yil = max((g.index[-1] - g.index[0]).days / 365.25, 1e-9)
    haftalik = (1 + g).resample("W").prod() - 1
    t = nw_t(g.to_numpy())
    yarim = len(g) // 2
    return {
        "donem": [str(g.index[0].date()), str(g.index[-1].date())],
        "gun": int(len(g)),
        "ort_gunluk_bps": float(g.mean() * 1e4),
        "yillik_getiri": float(eq.iloc[-1] ** (1 / yil) - 1),
        "yillik_sharpe": float(g.mean() / g.std() * math.sqrt(252)) if g.std() > 0 else 0.0,
        "max_dusus": float((eq / eq.cummax() - 1).min()),
        "pozitif_hafta": float((haftalik > 0).mean()),
        "islem_hafta": float(islem_sayisi / max(len(haftalik), 1)),
        "nw_t": t,
        "p_tek": tek_yonlu_p(t),
        "yari1_ort_bps": float(g.iloc[:yarim].mean() * 1e4),
        "yari2_ort_bps": float(g.iloc[yarim:].mean() * 1e4),
    }


# ------------------------------------------------------------------ hipotezler


def gun_serisi(bar_getiri: pd.Series) -> pd.Series:
    """Bar getirilerini NY takvim gününe birleştirir (bileşik)."""
    et = bar_getiri.index.tz_convert(NY)
    return (1 + bar_getiri).groupby(et.date).prod().pipe(
        lambda s: s.set_axis(pd.to_datetime(s.index))) - 1


def a1_gece(df: pd.DataFrame, c: float) -> tuple[pd.Series, int]:
    df = df[df.index >= H1_BASLANGIC]
    saat = df.index.tz_convert(NY).hour
    poz = pd.Series(np.where((saat >= 16) | (saat < 9), 1.0, 0.0), index=df.index)
    r = df["open"].shift(-1) / df["open"] - 1
    dp = poz.diff().abs().fillna(poz.abs())
    net = (poz * r).fillna(0) - dp * c / 1e4
    return gun_serisi(net), int(dp.sum())


def a2_momentum(df: pd.DataFrame, c: float) -> tuple[pd.Series, int]:
    df = df[df.index >= H1_BASLANGIC]
    et = df.index.tz_convert(NY)
    acilis = pd.Series(df["open"].to_numpy(), index=et)
    gunler = sorted(set(et.date))
    sonuc = {}
    islem = 0
    onceki_16 = None
    for g in gunler:
        gun = acilis[acilis.index.date == g]
        saat = {t.hour: v for t, v in gun.items()}
        if onceki_16 is not None and all(h in saat for h in (10, 15, 16)):
            yon = np.sign(saat[10] / onceki_16 - 1)
            getiri = yon * (saat[16] / saat[15] - 1)
            sonuc[pd.Timestamp(g)] = getiri - (2 * c / 1e4 if yon else 0.0)
            islem += 2 if yon else 0
        else:
            sonuc[pd.Timestamp(g)] = float("nan")  # işlem günü değil (gerekli barlar yok)
        if 16 in saat:
            onceki_16 = saat[16]
    return pd.Series(sonuc).sort_index(), islem


def a3_ay_donumu(d1: pd.DataFrame, c: float) -> tuple[pd.Series, int]:
    """D1: sunucu tarihli barlar (UTC+3 gece yarısı ≈ 17:00 ET); kapanıştan kapanışa."""
    tarih = pd.to_datetime(d1["sunucu"].dt.date)
    kap = pd.Series(d1["close"].to_numpy(), index=tarih)
    kap = kap[~kap.index.duplicated(keep="last")]
    ay = kap.index.to_period("M")
    sira = pd.Series(1, index=kap.index).groupby(ay).cumsum()
    poz = (sira <= 3).astype(float)  # yeni ayın 1.-3. işlem günleri tutulur
    r = kap / kap.shift(1) - 1
    dp = poz.diff().abs().fillna(0)
    net = (poz * r).fillna(0) - dp * c / 1e4
    return net, int(dp.sum())


def b1_tsmom(d1: pd.DataFrame, c: float, swap: tuple[float, float]) -> tuple[pd.Series, int]:
    tarih = pd.to_datetime(d1["sunucu"].dt.date)
    kap = pd.Series(d1["close"].to_numpy(), index=tarih)
    kap = kap[~kap.index.duplicated(keep="last")]
    r = kap / kap.shift(1) - 1
    isaret = np.sign(kap / kap.shift(252) - 1)
    vol = r.rolling(60).std() * math.sqrt(252)
    hedef = (isaret * np.minimum(0.10 / vol, 3.0)).where(vol > 0)
    # Haftalık: haftanın son işlem günü kapanışında hesaplanan hedef, sonraki gün(ler) tutulur.
    hafta = kap.index.to_period("W")
    son_gun = pd.Series(kap.index, index=kap.index).groupby(hafta).transform("max")
    # Sapma notu (K-137): ön kayıt "haftanın ilk işlem günü açılışı" diyor; D1 kapanıştan kapanışa
    # hesapta yeniden dengeleme haftanın son kapanışında olur (hafta sonu boşluğu dahil tutulur).
    agirlik = hedef.where(kap.index.to_numpy() == son_gun.to_numpy()).ffill().shift(1).fillna(0.0)
    dp = agirlik.diff().abs().fillna(agirlik.abs())
    onceki_carsamba = pd.Series(kap.index, index=kap.index).shift(1).dt.weekday == 2
    swap_gece = np.where(agirlik > 0, swap[0], np.where(agirlik < 0, swap[1], 0.0))
    swap_getiri = agirlik.abs() * swap_gece * np.where(onceki_carsamba, 3.0, 1.0)
    net = (agirlik * r).fillna(0) - dp * c / 1e4 + swap_getiri
    return net, int((dp > 1e-9).sum())


def portfoy(parcalar: dict[str, pd.Series]) -> pd.Series:
    df = pd.DataFrame(parcalar).dropna(how="all").fillna(0.0)
    return df.mean(axis=1)


# ------------------------------------------------------------------ referans (Yahoo, maliyetsiz)


def referans() -> dict[str, Any]:
    cikti: dict[str, Any] = {}
    for s in ("SPY", "QQQ", "DIA"):
        y = yahoo(s)
        gece = (y["open"] + y["temettu"]) / y["close"].shift(1) - 1
        gun_ici = y["close"] / y["open"] - 1
        tr = y["adjclose"] / y["adjclose"].shift(1) - 1
        ay = y.index.to_period("M")
        sira = pd.Series(1, index=y.index).groupby(ay).cumsum()
        tom = tr.where(sira <= 3, 0.0)
        on_yil = {}
        for bas in range(1990, 2030, 10):
            parca = gece[(gece.index.year >= bas) & (gece.index.year < bas + 10)].dropna()
            if len(parca) > 200:
                on_yil[f"{bas}s"] = {"gece_ort_bps": float(parca.mean() * 1e4),
                                     "nw_t": nw_t(parca.to_numpy())}
        cikti[s] = {
            "donem": [str(y.index[0].date()), str(y.index[-1].date())],
            "gece_ort_bps": float(gece.mean() * 1e4), "gece_nw_t": nw_t(gece.dropna().to_numpy()),
            "gun_ici_ort_bps": float(gun_ici.mean() * 1e4),
            "gun_ici_nw_t": nw_t(gun_ici.dropna().to_numpy()),
            "gece_on_yil": on_yil,
            "tom_gunluk_ort_bps": float(tr[sira <= 3].mean() * 1e4),
            "diger_gunluk_ort_bps": float(tr[sira > 3].mean() * 1e4),
            "tom_nw_t": nw_t(tom.dropna().to_numpy()),
        }
    return cikti


# ------------------------------------------------------------------ ana


def main() -> None:
    mt5 = mt5_baglan()
    h1 = {s: mt5_bar(mt5, s, "H1") for s in ENDEKSLER}
    d1 = {s: mt5_bar(mt5, s, "D1") for s in B1_SEMBOLLER}
    c = {s: maliyet_bps(mt5, s) for s in B1_SEMBOLLER}
    sw = {s: swap_orani(mt5, s) for s in B1_SEMBOLLER}

    hipotezler: dict[str, dict[str, Any]] = {}
    for ad, fn, kaynak, semboller in (
        ("A1", a1_gece, h1, ENDEKSLER),
        ("A2", a2_momentum, h1, ENDEKSLER),
        ("A3", a3_ay_donumu, d1, ENDEKSLER),
    ):
        parca, islem = {}, 0
        for s in semboller:
            parca[s], n = fn(kaynak[s], c[s])
            islem += n
        port = portfoy(parca)
        hipotezler[ad] = {
            "portfoy": ozet(port, islem),
            "sembol": {s: ozet(v, 0) for s, v in parca.items()},
        }
    parca, islem = {}, 0
    for s in B1_SEMBOLLER:
        parca[s], n = b1_tsmom(d1[s], c[s], sw[s])
        islem += n
    port = portfoy(parca)
    port = port[port.index >= port.ne(0).idxmax()]  # ilk pozisyondan itibaren
    hipotezler["B1"] = {"portfoy": ozet(port, islem),
                        "sembol": {s: ozet(v[v.ne(0).idxmax():], 0) for s, v in parca.items()}}

    # Holm-Bonferroni, k = 4
    sirali = sorted(hipotezler, key=lambda h: hipotezler[h]["portfoy"]["p_tek"])
    reddedildi = True
    for i, h in enumerate(sirali):
        esik = ALFA / (len(sirali) - i)
        anlamli = reddedildi and hipotezler[h]["portfoy"]["p_tek"] <= esik
        reddedildi = anlamli
        p = hipotezler[h]["portfoy"]
        pozitif = sum(1 for o in hipotezler[h]["sembol"].values() if o["ort_gunluk_bps"] > 0)
        gereken = 2 if h.startswith("A") else math.ceil(len(hipotezler[h]["sembol"]) / 2)
        kosul = {"holm": anlamli, "holm_esik": esik,
                 "iki_yari": p["yari1_ort_bps"] > 0 and p["yari2_ort_bps"] > 0,
                 "sembol_pozitif": f"{pozitif}/{len(hipotezler[h]['sembol'])}",
                 "sembol_kosulu": pozitif >= gereken}
        kosul["PASS"] = kosul["holm"] and kosul["iki_yari"] and kosul["sembol_kosulu"]
        hipotezler[h]["karar"] = kosul

    rapor = {
        "onkayit": "docs/research/records/2026-09-23-aktif-program2-onkayit.md (e3c31e9)",
        "zaman_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "maliyet_taraf_bps": c, "swap_gecelik_kesir": sw,
        "hipotezler": hipotezler,
        "referans_yahoo_maliyetsiz": referans(),
    }
    SONUC.write_text(json.dumps(rapor, indent=1, ensure_ascii=False), encoding="utf-8")
    for h, v in hipotezler.items():
        p, k = v["portfoy"], v["karar"]
        print(f"{h}: yıllık {p['yillik_getiri']:+.1%} Sharpe {p['yillik_sharpe']:.2f} "
              f"ort {p['ort_gunluk_bps']:+.2f} bps/gün t={p['nw_t']:.2f} p={p['p_tek']:.4f} "
              f"işlem/hafta {p['islem_hafta']:.1f} DD {p['max_dusus']:.1%} "
              f"yarılar {p['yari1_ort_bps']:+.2f}/{p['yari2_ort_bps']:+.2f} "
              f"semboller {k['sembol_pozitif']} -> {'PASS' if k['PASS'] else 'FAIL'}")


if __name__ == "__main__":
    main()
