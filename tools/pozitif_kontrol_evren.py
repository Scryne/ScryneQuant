"""Evren yolu pozitif kontrolü: gömülü trendli sentetik evrende portföy stratejisi 12 kapıyı
geçebiliyor mu? (K-118/K-119)

K-054'e göre tek sembollü strateji `evren_dayanikliligi`ni tanım gereği geçemez; gerçek bir
strateji ancak evren (çok enstrümanlı) yolundan promotion alabilir. Bu araç o yolun
(`research/evren_degerlendirme.degerlendir`, `butun_kapilar`) gücünü ölçer: her sembolün
getirisi = rejim_i × m + σ·(ρ·ortak + √(1−ρ²)·özel); rejim_i ±1, ortalama `sure_gun` günde
değişen bağımsız Markov zincirleri. Kütüphanedeki `ZamanSerisiTrend` (yükselen üyeleri taşır)
bu evrende gerçekten kazanır; m = 0'da kazanmaz.

Ölçüm aleti; defter/program/çekiliş değil (veri sentetik, K-039 kapsamı dışı).

    uv run python tools/pozitif_kontrol_evren.py --m 0 3 5 --tohum 3
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.data.semalar import BAR_SUTUNLARI, KaliteDurumu
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research.evren_kosu import EvrenVerisi
from scryne_quant.strategy.kutuphane.zaman_serisi import ZamanSerisiTrend

SEMBOLLER = ("BTCUSDT", *(f"S{i:02d}USDT" for i in range(1, 10)))
N_BAR = 79_530
SIGMA = 0.008
RHO = 0.5
T0 = 1_502_942_400_000
IZGARA = {
    "pencere": (168, 336, 720),
    "azami_enstruman": (3, 5),
    "yeniden_dengele_bar": (168,),
    "hedef_brut": (0.2,),
}


def veri(m_sharpe: float, tohum: int, n: int = N_BAR, sure_gun: float = 20.0) -> EvrenVerisi:
    rng = np.random.default_rng(tohum)
    m = m_sharpe * SIGMA / np.sqrt(8766)
    ortak = rng.standard_normal(n)
    diziler: dict[str, dict[str, np.ndarray]] = {}
    for s in SEMBOLLER:
        degis = rng.random(n) < 1.0 / (24.0 * sure_gun)
        rejim = np.where(np.cumsum(degis) % 2 == 0, 1.0, -1.0) * rng.choice([-1.0, 1.0])
        eps = RHO * ortak + np.sqrt(1 - RHO**2) * rng.standard_normal(n)
        r = rejim * m + SIGMA * eps
        close = 100.0 * np.exp(np.cumsum(r))
        acilis = np.concatenate([[100.0], close[:-1]])
        oyn = np.abs(rng.normal(0, SIGMA * 0.5, n))
        hacim = np.abs(rng.normal(1e6, 2e5, n))
        df = pd.DataFrame({
            "open_time": T0 + np.arange(n, dtype="int64") * 3_600_000,
            "open": acilis, "high": np.maximum(acilis, close) * (1 + oyn),
            "low": np.minimum(acilis, close) * (1 - oyn), "close": close, "volume": hacim,
            "quote_volume": hacim * close, "trades": rng.integers(1000, 5000, n),
            "quality_status": KaliteDurumu.OK,
        }).loc[:, list(BAR_SUTUNLARI)]
        diziler[s] = {a: np.array(x, copy=True) for a, x in bar_dizileri(df).items()}
    return EvrenVerisi(
        timeframe="1h", zamanlar=diziler["BTCUSDT"]["open_time"], diziler=diziler,
        uyelik={s: np.ones(n, dtype=bool) for s in SEMBOLLER},
        veri_sha256={s: "0" * 64 for s in SEMBOLLER}, meta={}, olcum_baslangici=0,
        kural_kimligi="sentetik",
    )


def degerlendir(m_sharpe: float, tohum: int) -> dict[str, Any]:
    r = ed.degerlendir(ZamanSerisiTrend, IZGARA, maliyet_mod.yukle(), veri(m_sharpe, tohum))
    kapi = r["kapilar"]
    return {"m": m_sharpe, "tohum": tohum,
            "olcumler": {k: v for k, v in r["olcumler"].items() if not isinstance(v, dict)},
            "kalan": kapi["kalan_kapilar"], "gecti": kapi["gecti"]}


def _is(a: tuple[float, int]) -> dict[str, Any]:
    return degerlendir(*a)


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--m", type=float, nargs="+", default=[0.0, 3.0, 5.0])
    ap.add_argument("--tohum", type=int, default=3)
    ap.add_argument("--isci", type=int, default=3)
    ap.add_argument("--cikti", default="runs/pozitif_kontrol/evren.json")
    a = ap.parse_args(argv)
    with ProcessPoolExecutor(a.isci) as ex:
        sonuc = list(ex.map(_is, [(m, s) for m in a.m for s in range(a.tohum)]))
    Path(a.cikti).parent.mkdir(parents=True, exist_ok=True)
    Path(a.cikti).write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, default=str),
                             encoding="utf-8")
    for r in sonuc:
        o = r["olcumler"]
        print(f"m={r['m']:<4} t={r['tohum']} OOS {o.get('oos_sharpe', np.nan):5.2f} "
              f"IS {o.get('is_sharpe', np.nan):5.2f} gecti={r['gecti']} kalan={r['kalan']}")


if __name__ == "__main__":
    main(sys.argv[1:])
