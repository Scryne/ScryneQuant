"""Hat 1 / B-5 — USDT fırsat maliyeti benchmark'ı (DTB3) ve ideal carry'nin **benchmark-üstü**
getirisi. Ölçüm; ikinci tavan DEĞİL (maliyet katmanı B-1 henüz yok), karar yok, seçim yok.

Veri kararı A (2026-09-20): FRED/ALFRED `DTB3` — 3-Month Treasury Bill Secondary Market
Rate, Discount Basis, günlük, yüzde (`data/makro/DTB3.parquet`, `tools/faz12_makro_indir.py
--ek`, yıl-parçalı SHA `.kaynak.json`). `makro.SERILER` program sözlüğüne girmez.

PIT: `data/makro.pit_gunluk` (K-060) — `d` gününün değeri `d` günü sonunda bilinen en son
gözlem; hafta sonu/tatil = bilinen son gözlem (bilgi durumu, uydurma değil); ilk vintage
öncesi NaN ve **doldurulmaz** (o günler excess'ten düşer, sayısı raporlanır).

Benchmark tanımı (tasarım §7; iki satır, ikisi de raporlanır):
- discount basis (kote edildiği gibi, 360 gün):     r_disc,d = DTB3_d / 100 / 360
- bond-equivalent (yatırım getirisi, 365 gün) —
  Hazine'nin yayımladığı çevrim, t = 91 gün:        BEY = 365·d / (360 − d·t), d = DTB3/100
                                                    r_bey,d = BEY / 365
  Kaynak: U.S. Treasury / TreasuryDirect "Treasury Bills — Rates & Terms" (discount rate →
  investment rate); H.15 notları. Birincil satır: BEY (sermaye getirisiyle aynı 365-gün
  tabanı). Fark küçük; ikisi de yazılır, seçim kaydı budur.

Carry tarafı: Adım 0 formülü aynen (`tools/faz16_carry_tavan.py`): r_pos,t = funding_t −
Δbasis_t, UTC güne toplanır. Tutarlılık: BTC günlük Sharpe Adım 0 kaydıyla eşit olmalı.
Sermaye: r_cap,d = r_pos,d / (1 + m + b), m = 1/L, L ∈ {1,2,3,5}, b ∈ {0, m} (A-8 ızgarası).
Excess: r_excess,d = r_cap,d − r_bey,d; yıllık ortalama ve excess Sharpe (√365). Benchmark
toplam sermayeye uygulanır (tasarım §7). GRID — hiçbir hücre seçilmez.

Bu çıktı "ideal − benchmark"tır: perp maliyeti, marjin faizi, likidasyon yok. İkinci tavanın
3. aşaması ancak 2. aşama (B-1) eklenince tamamlanır; burada CLOSE/ELIGIBLE verilmez.

Kullanım: uv run python tools/faz16_hat1_b5_benchmark.py
Çıktı:    runs/faz16/hat1_b5_benchmark.json
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from scryne_quant.common.hash import dosya_hash
from scryne_quant.data.makro import pit_gunluk

IS_BITIS_MS = 1739728800000
SAAT_MS = 3_600_000
GUN_MS = 86_400_000
T_GUN = 91
L_IZGARA = (1, 2, 3, 5)


def _sharpe(x: pd.Series) -> float | None:
    x = x.dropna()
    if len(x) < 30 or x.std(ddof=1) == 0:
        return None
    return float(x.mean() / x.std(ddof=1) * math.sqrt(365))


def carry_gunluk(sembol: str, funding_depo: Path, premium_depo: Path) -> pd.Series | None:
    f_yol, p_yol = funding_depo / f"{sembol}.parquet", premium_depo / f"{sembol}.parquet"
    if not (f_yol.exists() and p_yol.exists()):
        return None
    f = pd.read_parquet(f_yol)
    p = pd.read_parquet(p_yol, columns=["open_time", "close"])
    f = f[f["funding_time"] < IS_BITIS_MS].sort_values("funding_time")
    p = p[p["open_time"] + SAAT_MS <= IS_BITIS_MS]
    basis = pd.Series(p["close"].to_numpy(), index=(p["open_time"] + SAAT_MS).to_numpy())
    ft = ((f["funding_time"] + SAAT_MS // 2) // SAAT_MS * SAAT_MS).to_numpy()
    b = basis.reindex(ft).to_numpy()
    d = b - np.concatenate([[np.nan], b[:-1]])
    ok = ~np.isnan(d)
    if ok.sum() < 90:
        return None
    r = pd.Series(f["funding_rate"].to_numpy()[ok] - d[ok], index=ft[ok] // GUN_MS)
    return r.groupby(level=0).sum()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adim0", default="runs/faz16/carry_tavan.json")
    ap.add_argument("--dtb3", default="data/makro/DTB3.parquet")
    ap.add_argument("--cikti", default="runs/faz16/hat1_b5_benchmark.json")
    a = ap.parse_args()
    adim0 = json.loads(Path(a.adim0).read_text(encoding="utf-8"))
    semboller = list(adim0["semboller"].keys())

    vintage = pd.read_parquet(a.dtb3)
    kaynak_yol = Path(str(a.dtb3).replace(".parquet", ".kaynak.json"))
    kaynak = json.loads(kaynak_yol.read_text(encoding="utf-8")) if kaynak_yol.exists() else {}

    seriler = {s: carry_gunluk(s, Path("data/funding"), Path("data/turev/premium")) for s in semboller}
    seriler = {s: r for s, r in seriler.items() if r is not None}
    gun_min = min(int(r.index.min()) for r in seriler.values())
    gun_max = max(int(r.index.max()) for r in seriler.values())
    gunler = np.arange(gun_min, gun_max + 1, dtype="int64")
    dtb3 = pit_gunluk(vintage, gunler)  # yüzde, PIT (K-060)
    d = dtb3 / 100.0
    r_disc = pd.Series(d / 360.0, index=gunler)
    bey = 365.0 * d / (360.0 - d * T_GUN)
    r_bey = pd.Series(bey / 365.0, index=gunler)
    nan_gun = int(np.isnan(dtb3).sum())

    # tutarlılık: BTC günlük Sharpe = Adım 0
    btc_sharpe = _sharpe(seriler["BTCUSDT"])
    adim0_btc = adim0["semboller"]["BTCUSDT"]["toplam"]["sharpe"]
    tutarli = abs(btc_sharpe - adim0_btc) < 1e-9

    def grid(r_pos: pd.Series) -> dict:
        out = {}
        rb = r_bey.reindex(r_pos.index)
        for L in L_IZGARA:
            m = 1.0 / L
            for b_ad, b in (("b0", 0.0), ("b_m", m)):
                r_cap = r_pos / (1 + m + b)
                ex = (r_cap - rb).dropna()
                out[f"L{L}_{b_ad}"] = {
                    "r_cap_yillik_pct": float(r_cap.mean() * 365 * 100),
                    "r_excess_yillik_pct": float(ex.mean() * 365 * 100),
                    "excess_sharpe": _sharpe(ex),
                    "gun": int(len(ex)),
                }
        return out

    sembol_sonuc = {}
    for s, r in seriler.items():
        rb = r_bey.reindex(r.index)
        sembol_sonuc[s] = {
            "gun": int(len(r)),
            "r_pos_yillik_pct": float(r.mean() * 365 * 100),
            "r_pos_sharpe": _sharpe(r),
            "benchmark_bey_yillik_pct_ort": float(np.nanmean(rb) * 365 * 100),
            "benchmark_disc_yillik_pct_ort": float(np.nanmean(r_disc.reindex(r.index)) * 365 * 100),
            "grid": grid(r),
        }

    # havuz: eşit ağırlık, o gün verisi olan semboller
    df = pd.DataFrame(seriler)
    havuz = df.mean(axis=1)
    uye = df.notna().sum(axis=1)
    yillik_bench = {}
    yil = pd.to_datetime(gunler * GUN_MS, unit="ms", utc=True).year
    for y in np.unique(yil):
        m = yil == y
        yillik_bench[int(y)] = {"dtb3_ort_pct": float(np.nanmean(dtb3[m])), "bey_ort_pct": float(np.nanmean(bey[m]) * 100), "gun": int(m.sum()), "nan_gun": int(np.isnan(dtb3[m]).sum())}

    cikti = {
        "olcum": "Hat 1 / B-5 — DTB3 benchmark ve ideal carry'nin benchmark-üstü getirisi (GRID)",
        "tur": "ölçüm; ikinci tavan değil (B-1 maliyet katmanı yok); seçim yok; karar yok",
        "uretim_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "veri": {
            "dtb3": {"yol": a.dtb3, "sha256": dosya_hash(a.dtb3), "kaynak_json": {k: v for k, v in kaynak.items() if k != "parcalar"}, "parca_sha256": [p["sha256"] for p in kaynak.get("parcalar", [])]},
            "adim0": {"yol": a.adim0, "sha256": dosya_hash(a.adim0)},
        },
        "pencere": {"ilk_utc": datetime.fromtimestamp(gun_min * 86400, UTC).date().isoformat(), "son_utc": datetime.fromtimestamp(gun_max * 86400, UTC).date().isoformat(), "is_bitis_utc": datetime.fromtimestamp(IS_BITIS_MS / 1000, UTC).isoformat(), "gun": int(gunler.size), "dtb3_nan_gun": nan_gun},
        "benchmark": {
            "tanim_birincil": "BEY = 365·d/(360 − d·91), d = DTB3/100; r_bey,d = BEY/365; PIT K-060",
            "tanim_ikincil": "r_disc,d = DTB3/100/360",
            "bey_yillik_ort_pct": float(np.nanmean(bey) * 100),
            "disc_yillik_ort_pct": float(np.nanmean(d) * 100),
            "yillik": yillik_bench,
        },
        "tutarlilik": {"btc_gunluk_sharpe": btc_sharpe, "adim0_btc_sharpe": adim0_btc, "esit": tutarli},
        "havuz": {"sembol": int(df.shape[1]), "uye_medyan": float(uye.median()), "r_pos_yillik_pct": float(havuz.mean() * 365 * 100), "r_pos_sharpe": _sharpe(havuz), "grid": grid(havuz)},
        "semboller": sembol_sonuc,
    }
    Path(a.cikti).parent.mkdir(parents=True, exist_ok=True)
    Path(a.cikti).write_text(json.dumps(cikti, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    icerik = {k: v for k, v in cikti.items() if k != "uretim_utc"}
    print("icerik_sha256:", __import__("hashlib").sha256(json.dumps(icerik, ensure_ascii=False, sort_keys=True, default=float).encode()).hexdigest())
    print(json.dumps({k: cikti[k] for k in ("pencere", "benchmark", "tutarlilik")}, ensure_ascii=False, indent=1))
    print(f"\n{'':10} " + " ".join(f"{k:>12}" for k in cikti["havuz"]["grid"]))
    for s in ("BTCUSDT", "ETHUSDT"):
        g = sembol_sonuc[s]["grid"]
        print(f"{s:10} " + " ".join(f"{v['r_excess_yillik_pct']:>6.2f}/{(v['excess_sharpe'] or float('nan')):>5.2f}" for v in g.values()))
    g = cikti["havuz"]["grid"]
    print(f"{'HAVUZ':10} " + " ".join(f"{v['r_excess_yillik_pct']:>6.2f}/{(v['excess_sharpe'] or float('nan')):>5.2f}" for v in g.values()))
    print("(hücre: r_excess %/yıl / excess Sharpe — ideal − benchmark; maliyet yok; seçim yok)")


if __name__ == "__main__":
    main()
