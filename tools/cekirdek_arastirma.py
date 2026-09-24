"""Çekirdek portföy geriye bakışı (K-141). Karar kodu `scryne_quant.aktif.cekirdek`.

    .venv/Scripts/python.exe tools/cekirdek_arastirma.py

Spot, kaldıraçsız. Karar d kapanışında, dolum d+1 açılışında; açılıştan açılışa getiri.
Maliyet 15 bps/taraf (ücret 10 + kayma 5; demo hesapla aynı). Boş nakit faiz almaz (tutucu).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from scryne_quant.aktif.cekirdek import CekirdekAyari, dengele, hedef_agirliklar

KOK = Path(__file__).resolve().parents[1]
SONUC = KOK / "docs/research/records/2026-09-24-cekirdek-sonuc.json"
TARAF = 15 / 1e4
DONEMLER = {"2018-2019": ("2018-01-01", "2020-01-01"), "2020-2022": ("2020-01-01", "2023-01-01"),
            "2023-2026": ("2023-01-01", "2026-09-20"), "tum": ("2018-01-01", "2026-09-20")}


def gunluk(s: str) -> pd.DataFrame:
    h = pd.read_parquet(KOK / f"data/evren/{s}/1h.parquet", columns=["open_time", "open", "close"])
    g = h.groupby(h.open_time // 86_400_000).agg(open=("open", "first"), close=("close", "last"),
                                                 n=("open", "size"))
    g = g[g.n >= 20]
    g.index = pd.to_datetime(g.index * 86_400_000, unit="ms", utc=True)
    return g


def geriye(ayar: CekirdekAyari) -> tuple[pd.Series, float]:
    veri = {s: gunluk(s) for s in ayar.semboller}
    kapanis = pd.DataFrame({s: d.close for s, d in veri.items()}).sort_index()
    acilis = pd.DataFrame({s: d.open for s, d in veri.items()})
    acilis = acilis.reindex(kapanis.index).ffill(limit=3)
    hedef = hedef_agirliklar(kapanis, ayar)
    uyg = np.zeros(hedef.shape)
    onceki: dict[str, float] = {}
    for i, (_, satir) in enumerate(hedef.iterrows()):
        onceki = dengele(onceki, satir.to_dict(), ayar.bant)
        uyg[i] = [onceki[s] for s in hedef.columns]
    W = pd.DataFrame(uyg, index=hedef.index, columns=hedef.columns)
    tut = W.shift(1).fillna(0.0)  # d kararı d+1 boyunca (açılıştan açılışa)
    r = (acilis.shift(-1) / acilis - 1).fillna(0.0)
    devir = tut.diff().abs().sum(axis=1).fillna(tut.abs().sum(axis=1))
    net = (tut * r).sum(axis=1) - devir * TARAF
    return net, float(devir.mean() * 365)


def ozet(r: pd.Series) -> dict:
    e = (1 + r).cumprod()
    yil = len(r) / 365
    return {"yillik": float(e.iloc[-1] ** (1 / yil) - 1),
            "sharpe": float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else 0.0,
            "max_dd": float((e / e.cummax() - 1).min())}


def main() -> None:
    satirlar = []
    temel = CekirdekAyari()
    denemeler = [("BTC+ETH", temel)]
    denemeler += [(f"BTC+ETH vol{v}", replace(temel, hedef_vol=v)) for v in (0.2, 0.4, 0.5)]
    denemeler += [("BTC", replace(temel, semboller=("BTCUSDT",))),
                  ("BTC+ETH bant0", replace(temel, bant=0.0)),
                  ("BTC+ETH bant0.1", replace(temel, bant=0.1))]
    for ad, ayar in denemeler:
        net, devir = geriye(ayar)
        satir = {"ad": ad, "hedef_vol": ayar.hedef_vol, "bant": ayar.bant, "devir_yillik": devir,
                 **{k: ozet(net.loc[a:b]) for k, (a, b) in DONEMLER.items()},
                 "yillar": {str(y): ozet(net[net.index.year == y])["yillik"]
                            for y in range(2018, 2027)}}
        satirlar.append(satir)
        print(f"{ad:<16} devir {devir:4.1f}/yıl | " + " | ".join(
            f"{k} {satir[k]['yillik']:+6.1%} SR {satir[k]['sharpe']:4.2f} "
            f"DD {satir[k]['max_dd']:6.1%}"
            for k in DONEMLER) + " | " + " ".join(
            f"{y[2:]}:{v:+.0%}" for y, v in satir["yillar"].items()))
    for s in ("BTCUSDT", "ETHUSDT"):
        c = gunluk(s).close.pct_change().loc["2018-01-01":"2026-09-20"].dropna()
        print(f"{s} tut-bekle      | " + " | ".join(
            f"{k} {ozet(c.loc[a:b])['yillik']:+6.1%} DD {ozet(c.loc[a:b])['max_dd']:6.1%}"
            for k, (a, b) in DONEMLER.items()))
    SONUC.write_text(json.dumps(satirlar, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
