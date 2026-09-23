"""Tam hat pozitif kontrolü: gömülü trendli sentetik piyasada kütüphane stratejileri 12 kapıyı
geçebiliyor mu? (K-117 devamı)

`tools/pozitif_kontrol.py` kapıların gücünü geleceğe bakan bir kahinle ölçtü; parametresiz
olduğu için K-054'ün ızgaraya bağlı kapıları (PBO, pertürbasyon) orada ölçülemiyordu. Bu araç
**gerçek** kütüphane stratejilerini (`sma_kesisim`, `donchian`, `momentum`) kendi ızgaralarıyla,
içine bilinen bir üstünlük gömülmüş sentetik bir seride koşturur: getiri = rejim × m + σ·ε,
rejim ±1, ortalama `sure_gun` günde bir değişen Markov zinciri. Trend takipçisi bu seride
gerçekten kazanır; kazancın büyüklüğü `m` ile ayarlanır. Hat doğru çalışıyorsa güçlü bir
trendde bu stratejiler kapılardan geçmeli, trendsiz (m = 0) seride geçmemeli.

Ölçüm aleti; defter/program/çekiliş değil (veri sentetik, K-039 kapsamı dışı).

    uv run python tools/pozitif_kontrol_tam.py --m 0 1.5 3 --tohum 3
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
from scryne_quant.research import degerlendirme, kapilar_v2
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.izgaralar import izgara
from scryne_quant.research.karsilastirma import ortak_isinma, ortak_pencereler
from scryne_quant.research.tarama import ASGARI_ISLEM
from scryne_quant.strategy.kutuphane import coz

STRATEJILER = ("sma_kesisim", "donchian", "momentum")
N_BAR = 79_530  # data/evren BTCUSDT 1h (2017-08 →) ile aynı uzunluk (K-118)
SIGMA = 0.006  # BTC 1h getiri oynaklığı mertebesi
T0 = 1_502_942_400_000  # 2017-08-17 04:00 UTC, arşiv deposunun ilk barı


def seri(m_sharpe: float, tohum: int, sure_gun: float = 20.0) -> pd.DataFrame:
    """Rejim anahtarlı sürüklenme. `m_sharpe`: rejimi kusursuz izleyen long/short'un yıllık
    Sharpe'ı (m/σ·√8766); long-only takipçinin gerçek Sharpe'ı bunun altında kalır."""
    rng = np.random.default_rng(tohum)
    m = m_sharpe * SIGMA / np.sqrt(8766)
    p_degis = 1.0 / (24.0 * sure_gun)
    rejim = np.empty(N_BAR)
    s = 1.0
    for i in range(N_BAR):
        if rng.random() < p_degis:
            s = -s
        rejim[i] = s
    r = rejim * m + SIGMA * rng.standard_normal(N_BAR)
    close = 30_000.0 * np.exp(np.cumsum(r))
    acilis = np.concatenate([[30_000.0], close[:-1]])
    oyn = np.abs(rng.normal(0, SIGMA * 0.5, N_BAR))
    high = np.maximum(acilis, close) * (1 + oyn)
    low = np.minimum(acilis, close) * (1 - oyn)
    hacim = np.abs(rng.normal(500, 100, N_BAR))
    df = pd.DataFrame({
        "open_time": T0 + np.arange(N_BAR, dtype="int64") * 3_600_000,
        "open": acilis, "high": high, "low": low, "close": close, "volume": hacim,
        "quote_volume": hacim * close, "trades": rng.integers(1000, 5000, N_BAR),
        "quality_status": KaliteDurumu.OK,
    })
    return df.loc[:, list(BAR_SUTUNLARI)]


def degerlendir(m_sharpe: float, tohum: int) -> dict[str, Any]:
    d = bar_dizileri(seri(m_sharpe, tohum))
    model = maliyet_mod.yukle()
    k019 = degerlendirme.degerlendir(model, "BTCUSDT", "1h", d, stratejiler=list(STRATEJILER))
    n = len(d["open_time"])
    out: dict[str, Any] = {"m": m_sharpe, "tohum": tohum, "stratejiler": {}}
    for ad in STRATEJILER:
        isinma = ortak_isinma([ad])
        ins, oos = ortak_pencereler(n, [ad])
        tam = Pencere("tam", baslangic=isinma, bitis=n, isinma_baslangic=0)
        try:
            v2 = kapilar_v2.olc(coz(ad), izgara(ad), model, "BTCUSDT", "1h", d,
                                ins=ins, oos=oos, tam=tam, asgari_islem=ASGARI_ISLEM)
            v2.pop("detay", None)
        except (ValueError, KeyError) as e:
            v2 = {"hata": f"{type(e).__name__}: {e}"}
        s = k019["stratejiler"][ad]
        kv2 = kapilar_v2.butun_kapilar(ad, {**s["olcumler"], **v2}).sozluk()
        out["stratejiler"][ad] = {
            "olcumler": {**s["olcumler"], **v2},
            "k019_kalan": s["kapilar"]["kalan_kapilar"],
            "tum_kalan": kv2["kalan_kapilar"],
        }
    return out


def _is(a: tuple[float, int]) -> dict[str, Any]:
    return degerlendir(*a)


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--m", type=float, nargs="+", default=[0.0, 1.5, 3.0])
    ap.add_argument("--tohum", type=int, default=3)
    ap.add_argument("--isci", type=int, default=3)
    ap.add_argument("--cikti", default="runs/pozitif_kontrol/tam.json")
    a = ap.parse_args(argv)
    isler = [(m, s) for m in a.m for s in range(a.tohum)]
    with ProcessPoolExecutor(a.isci) as ex:
        sonuc = list(ex.map(_is, isler))
    Path(a.cikti).parent.mkdir(parents=True, exist_ok=True)
    Path(a.cikti).write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, default=str),
                             encoding="utf-8")
    for r in sonuc:
        for ad, s in r["stratejiler"].items():
            o = s["olcumler"]
            print(f"m={r['m']:<4} t={r['tohum']} {ad:12s} IS {o.get('is_sharpe', np.nan):5.2f} "
                  f"OOS {o.get('oos_sharpe', np.nan):5.2f} islem {o.get('oos_islem')} | "
                  f"K019 kalan {s['k019_kalan']} | 12 kapı kalan {s['tum_kalan']}")


if __name__ == "__main__":
    main(sys.argv[1:])
