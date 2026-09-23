"""Funding carry'nin güncel düzeyi: yıllık funding (notional'a oranla) ve negatif ödeme payı.

Çekiliş değil, strateji değil: `docs/arsiv/Faz-16-Hat1-Carry-Tavan-Olcumu.md`'nin IS tavanının
(2020→2025-02) bugünkü karşılığını, aynı yerel depodan (`data/funding/<sembol>.parquet`)
ölçer. Maliyet, basis, marjin ve likidasyon yok — yani yine bir **tavandır**.

    uv run python tools/funding_guncel.py [SEMBOL ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

VARSAYILAN = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "LTCUSDT")
DEPO = Path("data/funding")


def olc(sembol: str) -> dict[str, object]:
    df = pd.read_parquet(DEPO / f"{sembol}.parquet")
    t = pd.to_datetime(df["funding_time"], unit="ms", utc=True)
    r = pd.Series(df["funding_rate"].astype(float).to_numpy(), index=t).sort_index()
    son = r.index.max()
    out: dict[str, object] = {"sembol": sembol, "son_odeme": str(son.date())}
    for yil in sorted(set(r.index.year) & {2024, 2025, 2026}):
        x = r[r.index.year == yil]
        gun = (x.index.max() - x.index.min()).days + 1
        out[f"{yil}_yillik_pct"] = round(x.sum() / gun * 365 * 100, 2)
        out[f"{yil}_neg_pay"] = round(float((x < 0).mean()), 3)
    son90 = r[r.index > son - pd.Timedelta(days=90)]
    # K-116 yeniden açılma işareti: son 90 gün, yıllık.
    out["son90g_yillik_pct"] = round(son90.sum() / 90 * 365 * 100, 2)
    son12 = r[r.index > son - pd.Timedelta(days=365)]
    out["son12ay_pct"] = round(son12.sum() * 100, 2)
    out["son12ay_neg_pay"] = round(float((son12 < 0).mean()), 3)
    return out


def main(argv: list[str]) -> None:
    satirlar = [olc(s) for s in (argv or VARSAYILAN)]
    print(pd.DataFrame(satirlar).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1:])
