"""Geniş evrenli kripto trend portföyü (K-141 araştırması).

    .venv/Scripts/python.exe tools/trend_portfoy.py

Evren her gün o güne kadarki veriyle kurulur: son 30 günün medyan günlük USDT hacmine göre ilk N,
en az 200 gün geçmiş, funding serisi başlamış (perp listelenmiş), stabil/kaldıraçlı token hariç.
Sinyal: birden çok geriye bakışın getiri işareti ortalaması (tek parametre seçilmez). Ağırlık:
varlık başına ters oynaklık, portföy 60 günlük kovaryansla hedef oynaklığa ölçeklenir, brüt
kaldıraç tavanı. Karar d günü kapanışında, işlem d+1 açılışında (açılıştan açılışa getiri).
Maliyet: devir × taraf maliyeti + tutulan pozisyonun funding'i.
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

KOK = Path(__file__).resolve().parents[1]
ONBELLEK = KOK / "data/turev/_trend_gunluk.parquet"
SONUC = KOK / "docs/research/records/2026-09-24-trend-portfoy-sonuc.json"
BAS, BIT, BOL = "2020-01-01", "2026-09-01", "2023-06-01"
STABIL = {
    "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USDP", "PAX", "UST", "EUR", "GBP", "AEUR",
    "USDS", "SUSD", "EURI", "USDE", "PYUSD", "XUSD", "BFUSD", "RLUSD", "USD1", "WBTC", "WBETH",
    "BTCST", "PAXG",
}
KALDIRACLI = re.compile(r"(UP|DOWN|BULL|BEAR)USDT$")
TARAF = 10 / 1e4  # taker 5 + kayma 5 bps, tutucu


def gunluk_veri() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if ONBELLEK.exists():
        d = pd.read_parquet(ONBELLEK)
    else:
        parca = []
        fund_var = {p.stem for p in (KOK / "data/turev/funding").glob("*.parquet")}
        for klasor in sorted((KOK / "data/evren").iterdir()):
            s = klasor.name
            if not s.endswith("USDT") or s[:-4] in STABIL or KALDIRACLI.search(s):
                continue
            if s not in fund_var or not (klasor / "1h.parquet").exists():
                continue
            h = pd.read_parquet(
                klasor / "1h.parquet", columns=["open_time", "open", "close", "quote_volume"]
            )
            h["gun"] = h.open_time // 86_400_000
            g = h.groupby("gun").agg(
                open=("open", "first"), close=("close", "last"),
                qv=("quote_volume", "sum"), n=("open", "size"),
            )
            g = g[g.n >= 20]
            g["s"] = s
            parca.append(g.reset_index())
        d = pd.concat(parca, ignore_index=True)
        d.to_parquet(ONBELLEK)
    d["tarih"] = pd.to_datetime(d.gun * 86_400_000, unit="ms", utc=True)
    acilis = d.pivot(index="tarih", columns="s", values="open").sort_index()
    kapanis = d.pivot(index="tarih", columns="s", values="close").sort_index()
    hacim = d.pivot(index="tarih", columns="s", values="qv").sort_index()
    # funding: günlük toplam oran (long öder)
    fparca = {}
    for s in kapanis.columns:
        f = pd.read_parquet(KOK / f"data/turev/funding/{s}.parquet")
        t = pd.to_datetime(f.calc_time // 86_400_000 * 86_400_000, unit="ms", utc=True)
        fparca[s] = pd.Series(f.last_funding_rate.to_numpy(), index=t).groupby(level=0).sum()
    fund = pd.DataFrame(fparca).reindex(kapanis.index)
    return acilis, kapanis, hacim, fund


def evren(hacim: pd.DataFrame, kapanis: pd.DataFrame, fund: pd.DataFrame, n: int) -> pd.DataFrame:
    med = hacim.rolling(30, min_periods=20).median()
    gecmis = kapanis.notna().cumsum() >= 200
    perp = fund.notna().cummax()
    uygun = gecmis & perp & kapanis.notna()
    sira = med.where(uygun).rank(axis=1, ascending=False)
    return sira <= n


def sinyal(kapanis: pd.DataFrame, bakislar: tuple[int, ...]) -> pd.DataFrame:
    toplam = sum(np.sign(kapanis / kapanis.shift(L) - 1) for L in bakislar)
    return toplam / len(bakislar)


def kos(veri, n: int, bakislar: tuple[int, ...], mod: str, hedef_vol: float, tavan: float,
        bant: float = 0.1) -> tuple[pd.Series, dict]:
    acilis, kapanis, hacim, fund = veri
    ev = evren(hacim, kapanis, fund, n)
    s = sinyal(kapanis, bakislar).where(ev).fillna(0.0)
    if mod == "long":
        s = s.clip(lower=0)
    getiri_c = kapanis.pct_change(fill_method=None)
    vol = getiri_c.ewm(span=30, min_periods=20).std() * np.sqrt(365)
    ham = (s / vol).replace([np.inf, -np.inf], 0).fillna(0.0)
    # portföy ölçeği: 60 günlük kovaryansla hedef oynaklık (haftalık yeniden hesap, hız için)
    tarih = kapanis.index
    olcek = pd.Series(np.nan, index=tarih)
    for i in range(60, len(tarih), 7):
        w = ham.iloc[i]
        aktif = w[w != 0].index
        if len(aktif) == 0:
            olcek.iloc[i] = 0.0
            continue
        pencere = getiri_c[aktif].iloc[i - 59 : i + 1].fillna(0.0)
        cov = pencere.cov().to_numpy() * 365
        pv = float(np.sqrt(max(w[aktif].to_numpy() @ cov @ w[aktif].to_numpy(), 1e-12)))
        olcek.iloc[i] = hedef_vol / pv
    olcek = olcek.ffill().fillna(0.0)
    hedef = ham.mul(olcek, axis=0)
    brut = hedef.abs().sum(axis=1)
    hedef = hedef.div(np.maximum(brut / tavan, 1.0), axis=0)
    # işlem bandı: hedeften sapma bant*|hedef|'i aşmadıkça pozisyon korunur
    W = np.zeros(hedef.shape)
    H = hedef.to_numpy()
    for i in range(1, len(H)):
        onceki = W[i - 1]
        fark = np.abs(H[i] - onceki) > bant * np.maximum(np.abs(H[i]), 0.02)
        W[i] = np.where(fark | (H[i] == 0), H[i], onceki)
    W = pd.DataFrame(W, index=tarih, columns=hedef.columns)
    # d kapanışında karar → d+1 açılışından d+2 açılışına getiri
    ac = acilis.ffill(limit=3)  # kısa veri boşlukları
    r_oo = ac.shift(-1) / ac - 1  # d açılışından d+1 açılışına
    tutulan = W.shift(1)  # d-1 kararı d açılışında uygulanır, d günü boyunca tutulur
    # seri biterse (delist): son kapanıştan çıkış + %20 aleyhte ceza (yöne göre)
    son = (kapanis / ac - 1) - 0.2 * np.sign(tutulan)
    bitis = r_oo.isna() & (tutulan != 0) & tutulan.notna()
    r_oo = r_oo.where(~bitis, son).fillna(0.0)
    pnl = (tutulan * r_oo).sum(axis=1)
    fon = (tutulan * fund.fillna(0.0)).sum(axis=1)
    devir = (W.shift(1).fillna(0) - W.shift(2).fillna(0)).abs().sum(axis=1)
    net = pnl - fon - devir * TARAF
    net = net.loc[BAS:BIT]
    ek = {
        "brut_ort": float(tutulan.abs().sum(axis=1).loc[BAS:BIT].mean()),
        "devir_yillik": float(devir.loc[BAS:BIT].mean() * 365),
        "funding_yillik": float(-fon.loc[BAS:BIT].mean() * 365),
        "maliyet_yillik": float((devir * TARAF).loc[BAS:BIT].mean() * 365),
        "delist_olay": int(bitis.loc[BAS:BIT].to_numpy().sum()),
    }
    return net, ek


def ozet(r: pd.Series) -> dict:
    if len(r) == 0:
        return {}
    e = (1 + r).cumprod()
    yil = len(r) / 365
    return {
        "yillik": float(e.iloc[-1] ** (1 / yil) - 1),
        "sharpe": float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else 0.0,
        "max_dd": float((e / e.cummax() - 1).min()),
        "son": float(e.iloc[-1]),
    }


def main() -> None:
    veri = gunluk_veri()
    print("sembol:", veri[1].shape[1], "gün:", veri[1].shape[0], flush=True)
    izgara = list(itertools.product(
        (10, 20, 40),
        ((10, 20, 40), (20, 40, 80, 160), (60, 120, 240)),
        ("long", "ls"),
        (0.2, 0.4),
    ))
    satirlar = []
    for n, bak, mod, hv in izgara:
        r, ek = kos(veri, n, bak, mod, hv, tavan=3.0)
        yillar = {str(y): ozet(r[r.index.year == y])["yillik"] for y in sorted(set(r.index.year))}
        satir = {
            "n": n, "bakis": list(bak), "mod": mod, "hedef_vol": hv,
            "tum": ozet(r), "ilk": ozet(r.loc[:BOL]), "son": ozet(r.loc[BOL:]),
            "yillar": yillar, **ek,
        }
        satirlar.append(satir)
        t, a, b = satir["tum"], satir["ilk"], satir["son"]
        print(
            f"N{n:>3} {str(bak):<18} {mod:<4} v{hv:.1f} | "
            f"tüm {t['yillik']:+6.1%} SR {t['sharpe']:4.2f} "
            f"DD {t['max_dd']:6.1%} | ilk {a['yillik']:+6.1%} son {b['yillik']:+6.1%} | "
            f"brüt {ek['brut_ort']:.2f} fon {ek['funding_yillik']:+.1%} "
            f"mal {ek['maliyet_yillik']:.1%} | "
            + " ".join(f"{y[2:]}:{v:+.0%}" for y, v in yillar.items()),
            flush=True,
        )
    SONUC.write_text(json.dumps(satirlar, indent=1, ensure_ascii=False), encoding="utf-8")
    pozitif = sum(s["ilk"]["yillik"] > 0 and s["son"]["yillik"] > 0 for s in satirlar)
    print(f"\nİki yarıda da pozitif: {pozitif}/{len(satirlar)}")


if __name__ == "__main__":
    main()
