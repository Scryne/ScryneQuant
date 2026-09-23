"""Funding carry backtest'i (K-139). Ön kayıt: `docs/research/records/2026-09-23-carry-onkayit.md`.

    .venv/Scripts/python.exe tools/carry_arastirma.py

Spot long + perp short; günlük karar (00:00 UTC). Getiri = funding − Δpremium − maliyet.
Veri projede (PIT): funding olayları, 1h premium index, 1h spot (listeden çıkanlar dahil).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

KOK = Path(__file__).resolve().parents[1]
SONUC = KOK / "docs/research/records/2026-09-23-carry-sonuc.json"
GUN_MS = 86_400_000

GIRIS_YILLIK = 0.20
CIKIS_YILLIK = 0.05
AZAMI_POZ = 8
SERMAYE_CARPANI = 1.5
MALIYET_TARAF = (10 + 5 + 2 * 2) / 10_000
ASGARI_HACIM = 20e6
SINYAL_GUN = 3
TASFIYE_SICRAMA = 0.45
TASFIYE_KAYIP = 0.06


def gunluk_paneller() -> dict[str, pd.DataFrame]:
    """Gün × sembol panelleri: funding toplamı, premium gün sonu, spot yüksek/kapanış, hacim."""
    fund, prem, yuksek, kapanis, hacim = {}, {}, {}, {}, {}
    for f in sorted((KOK / "data/turev/funding").glob("*.parquet")):
        s = f.stem
        p_yol = KOK / "data/turev/premium" / f"{s}.parquet"
        spot_yol = KOK / "data/evren" / s / "1h.parquet"
        if not (p_yol.is_file() and spot_yol.is_file()):
            continue
        fd = pd.read_parquet(f)
        gun = (fd["calc_time"] // GUN_MS).astype("int64")
        fund[s] = fd.groupby(gun)["last_funding_rate"].sum()
        pr = pd.read_parquet(p_yol, columns=["open_time", "close"])
        prem[s] = pr.groupby(pr["open_time"] // GUN_MS)["close"].last()
        sp = pd.read_parquet(spot_yol, columns=["open_time", "high", "close", "quote_volume"])
        g = sp["open_time"] // GUN_MS
        yuksek[s] = sp.groupby(g)["high"].max()
        kapanis[s] = sp.groupby(g)["close"].last()
        hacim[s] = sp.groupby(g)["quote_volume"].sum()
    return {"fund": pd.DataFrame(fund), "prem": pd.DataFrame(prem),
            "yuksek": pd.DataFrame(yuksek),
            "kapanis": pd.DataFrame(kapanis), "hacim": pd.DataFrame(hacim)}


def kos(p: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    gunler = p["fund"].index.union(p["prem"].index)
    gunler = gunler[(gunler >= p["kapanis"].index.min())]
    fund = p["fund"].reindex(gunler)
    prem = p["prem"].reindex(gunler)
    kap = p["kapanis"].reindex(gunler)
    yuk = p["yuksek"].reindex(gunler)
    hac = p["hacim"].reindex(gunler)
    # D gününün kararı yalnız D'den önceki günleri görür (shift(1)).
    sinyal = (fund.fillna(0).rolling(SINYAL_GUN).sum() / SINYAL_GUN * 365).shift(1)
    fund_gecmis = fund.notna().cumsum().shift(1)
    likidite = hac.rolling(30, min_periods=20).median().shift(1)
    uygun = (likidite >= ASGARI_HACIM) & (fund_gecmis >= 30) & prem.notna() & kap.notna()
    dprem = prem.diff()

    ozk = 1.0
    poz: dict[str, float] = {}  # sembol → notional (para)
    dengeleme: dict[str, float] = {}  # son günlük dengelemedeki spot fiyatı
    kayit = []
    parca = {"funding": 0.0, "premium": 0.0, "maliyet": 0.0, "tasfiye": 0.0}
    islem = 0
    tasfiye_sayisi = 0
    for i, d in enumerate(gunler):
        if i == 0:
            continue
        sn = sinyal.iloc[i]
        uy = uygun.iloc[i]
        # 1) Çıkışlar
        for s in list(poz):
            if not bool(uy.get(s, False)) or not (sn.get(s, np.nan) >= CIKIS_YILLIK):
                m = poz.pop(s) * MALIYET_TARAF
                ozk -= m
                parca["maliyet"] -= m
                islem += 1
                dengeleme.pop(s, None)
        # 2) Girişler
        adaylar = sn[(uy.reindex(sn.index).fillna(False)) & (sn >= GIRIS_YILLIK)]
        adaylar = adaylar.drop([s for s in poz if s in adaylar.index]).sort_values(ascending=False)
        for s in adaylar.index[: max(AZAMI_POZ - len(poz), 0)]:
            n = ozk / (SERMAYE_CARPANI * AZAMI_POZ)
            poz[s] = n
            m = n * MALIYET_TARAF
            ozk -= m
            parca["maliyet"] -= m
            islem += 1
            dengeleme[s] = float(kap.iloc[i - 1][s]) if pd.notna(kap.iloc[i - 1][s]) else np.nan
        # 3) Günün getirisi (D 00:00 → D+1 00:00)
        for s in list(poz):
            n = poz[s]
            f = fund.iloc[i].get(s, np.nan)
            dp = dprem.iloc[i].get(s, np.nan)
            gelir = n * (0.0 if np.isnan(f) else f)
            baz = -n * (0.0 if np.isnan(dp) else dp)
            ozk += gelir + baz
            parca["funding"] += gelir
            parca["premium"] += baz
            ref = dengeleme.get(s, np.nan)
            y = yuk.iloc[i].get(s, np.nan)
            if ref and not np.isnan(ref) and not np.isnan(y) and y / ref - 1 >= TASFIYE_SICRAMA:
                kayip = n * TASFIYE_KAYIP
                ozk -= kayip
                parca["tasfiye"] -= kayip
                tasfiye_sayisi += 1
                poz.pop(s)
                dengeleme.pop(s, None)
                islem += 1
            else:
                k = kap.iloc[i].get(s, np.nan)
                if not np.isnan(k):
                    dengeleme[s] = float(k)
        kayit.append({"gun": pd.Timestamp((d + 1) * GUN_MS, unit="ms"), "ozk": ozk,
                      "poz": len(poz), "islem": islem})
    df = pd.DataFrame(kayit).set_index("gun")
    return df, {"parca": parca, "tasfiye": tasfiye_sayisi}


def ozet(df: pd.DataFrame) -> dict[str, Any]:
    eq = df["ozk"] / df["ozk"].iloc[0]
    yil = (eq.index[-1] - eq.index[0]).days / 365.25
    haftalik = eq.resample("W").last().pct_change().dropna()
    gunluk = eq.pct_change().dropna()
    return {
        "donem": [str(eq.index[0].date()), str(eq.index[-1].date())],
        "yillik_getiri": float(eq.iloc[-1] ** (1 / yil) - 1),
        "toplam": float(eq.iloc[-1] - 1),
        "sharpe": float(gunluk.mean() / gunluk.std() * np.sqrt(365)) if gunluk.std() > 0 else 0.0,
        "max_dusus": float((eq / eq.cummax() - 1).min()),
        "pozitif_hafta": float((haftalik > 0).mean()),
        "en_kotu_hafta": float(haftalik.min()),
        "ort_haftalik": float(haftalik.mean()),
        "ort_poz": float(df["poz"].mean()),
        "islem_hafta": float(df["islem"].diff().fillna(df["islem"]).sum() / max(len(haftalik), 1)),
    }


def main() -> None:
    p = gunluk_paneller()
    df, ek = kos(p)
    yillar = {str(y): ozet(g) for y, g in df.groupby(df.index.year) if len(g) > 30}
    rapor = {
        "onkayit": "docs/research/records/2026-09-23-carry-onkayit.md (ad61b5d)",
        "sembol_sayisi": int(p["fund"].shape[1]),
        "tamami": ozet(df),
        "2020_2023": ozet(df[df.index < "2024-01-01"]),
        "2024_2026": ozet(df[df.index >= "2024-01-01"]),
        "yillar": yillar,
        "kaynak_ayrimi_ilk_ozk_orani": ek["parca"],
        "tasfiye_sayisi": ek["tasfiye"],
    }
    o = rapor["2024_2026"]
    rapor["demo_olcutu"] = {"yillik>0": o["yillik_getiri"] > 0, "dd<%10": o["max_dusus"] > -0.10}
    SONUC.write_text(json.dumps(rapor, indent=1, ensure_ascii=False), encoding="utf-8")
    ozet_rapor = {k: v for k, v in rapor.items() if k != "yillar"}
    print(json.dumps(ozet_rapor, indent=1, ensure_ascii=False))
    for y, o in yillar.items():
        print(y, f"yıllık {o['yillik_getiri']:+.1%} DD {o['max_dusus']:.1%} "
                 f"kârlı hafta {o['pozitif_hafta']:.0%} ort poz {o['ort_poz']:.1f}")


if __name__ == "__main__":
    main()
