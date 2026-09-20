"""Hat 1 / Adım 0 — delta-nötr carry'nin **maliyetsiz, ideal** in-sample tavanı. Çekiliş değil.

Soru (Alpha-Discovery-Gap-Audit §3 Hat 1): spot long + perp short pozisyonunun, yalnız
kayıtlı funding + premium (basis) verisinden hesaplanan ekonomik getirisi, maliyet ve
likidasyon **sıfır** sayıldığında bile `oos_sharpe` eşiğine (1,04) ulaşıyor mu? Ulaşmıyorsa
hat kapanır (K-045 tavan kalıbı). Ulaşırsa yalnız sonraki adımın gerekçesidir, kanıt değil.

Repo tanımları (uydurulmadı):
- funding: `data/funding.py` — ödeme olayı, `funding_time` + `funding_rate`; pozitif oran
  long'un short'a ödediği tutardır (K-042).
- basis: `data/funding.py::evren_premium_dizisi` — premium index 1h klines `close`'u
  (`data/turev/premium/<sembol>.parquet`), "perp primi (vadeli talep)" (`evren_funding.py`).
- carry: repoda pozisyon olarak tanımı **yok**; burada kullanılan tanım Gap Audit Hat 1:
  eşit notional spot long + perp short.

Getiri tanımı (notional'a oranla, ödeme dönemi t):
    r_t = funding_rate_t − (basis_t − basis_{t−1})
Short perp funding'i alır (pozitifse), basis düşerse kazanır (perp − spot daralır); spot bacak
fiyat yönünü nötrler. basis_t = ödeme anında kapanan 1h premium barının `close`'u. Basis
terimi teleskopiktir (uzun vadede ≈ 0) ama M2M varyansı ve düşüşü gerçektir; iki bileşen
ayrı ayrı da raporlanır. Dönemler UTC güne toplanır (funding aralığı sembole göre 8h/4h/1h
olabilir), Sharpe = ort_günlük / σ_günlük · √365.

İdeal varsayımlar (hepsi tavanı **yukarı** iter): komisyon/spread/slippage 0, marjin faizi 0,
likidasyon yok, notional tam eşit, funding tam alınır, premium index = mark basis.

Pencere: in-sample = BTC tek-sembol kuralının IS'i (`research/bolme.is_oos`, 45.576 barlık
dosya, OOS başlangıcı 2025-02-16 18:00 UTC); bu andan sonraki hiçbir veri okunmaz (K-068 ek
şart). Başlangıç verinin ilk ödemesi.

Kullanım: uv run python tools/faz16_carry_tavan.py [--semboller runs/jev/evren50.txt]
Çıktı:    runs/faz16/carry_tavan.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

IS_BITIS_MS = 1739728800000  # 2025-02-16 18:00 UTC — Faz 4/11 OOS başlangıcı, dahil değil
ESIK_SHARPE = 1.04           # research/kapilar.py::oos_sharpe (K-071)
ESIK_DD = 0.25               # research/kapilar.py::max_drawdown
SAAT_MS = 3_600_000


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _dd(kumulatif: np.ndarray) -> float:
    zirve = np.maximum.accumulate(kumulatif)
    return float((zirve - kumulatif).max()) if kumulatif.size else 0.0


def _sharpe(gunluk: pd.Series) -> float | None:
    if len(gunluk) < 30 or gunluk.std(ddof=1) == 0:
        return None
    return float(gunluk.mean() / gunluk.std(ddof=1) * math.sqrt(365))


def sembol_olc(sembol: str, funding_depo: Path, premium_depo: Path) -> dict | None:
    f_yol, p_yol = funding_depo / f"{sembol}.parquet", premium_depo / f"{sembol}.parquet"
    if not f_yol.exists() or not p_yol.exists():
        return None
    f = pd.read_parquet(f_yol)
    p = pd.read_parquet(p_yol, columns=["open_time", "close"])
    f = f[f["funding_time"] < IS_BITIS_MS].sort_values("funding_time").reset_index(drop=True)
    p = p[p["open_time"] + SAAT_MS <= IS_BITIS_MS]
    if len(f) < 90:
        return None
    # basis_t: ödeme anında kapanan 1h premium barı (open_time = funding_time − 1h)
    basis = pd.Series(p["close"].to_numpy(), index=(p["open_time"] + SAAT_MS).to_numpy())
    # funding_time'ı saate yuvarla (kayıtta +2 ms gibi sapmalar var)
    ft = ((f["funding_time"] + SAAT_MS // 2) // SAAT_MS * SAAT_MS).to_numpy()
    b_t = basis.reindex(ft).to_numpy()
    # önceki ödeme anındaki basis
    b_onceki = np.concatenate([[np.nan], b_t[:-1]])
    d_basis = b_t - b_onceki
    gecerli = ~np.isnan(d_basis)
    if gecerli.sum() < 90:
        return None
    df = pd.DataFrame({
        "ms": ft[gecerli],
        "funding": f["funding_rate"].to_numpy()[gecerli],
        "basis_pnl": -d_basis[gecerli],
    })
    df["toplam"] = df["funding"] + df["basis_pnl"]
    df["gun"] = (df["ms"] // 86_400_000).astype(np.int64)
    g = df.groupby("gun")[["funding", "basis_pnl", "toplam"]].sum()
    gun_sayisi = int(len(g))
    kum = g["toplam"].cumsum().to_numpy()
    kum_f = g["funding"].cumsum().to_numpy()

    # negatif funding serileri (ardışık ödeme)
    neg = (df["funding"] < 0).to_numpy()
    en_uzun, sayac = 0, 0
    for x in neg:
        sayac = sayac + 1 if x else 0
        en_uzun = max(en_uzun, sayac)

    yil = df.assign(yil=pd.to_datetime(df["ms"], unit="ms", utc=True).dt.year)
    yillik = {}
    for y, grup in yil.groupby("yil"):
        gg = grup.groupby("gun")[["funding", "basis_pnl", "toplam"]].sum()
        yillik[int(y)] = {
            "gun": int(len(gg)),
            "funding_yillik_pct": float(grup["funding"].mean() * (len(grup) / max(len(gg), 1)) * 365 * 100),
            "toplam_sharpe": _sharpe(gg["toplam"]),
            "funding_sharpe": _sharpe(gg["funding"]),
            "negatif_funding_payi": float((grup["funding"] < 0).mean()),
        }

    return {
        "sembol": sembol,
        "veri": {
            "funding": {"yol": str(f_yol), "sha256": _sha(f_yol)},
            "premium": {"yol": str(p_yol), "sha256": _sha(p_yol)},
        },
        "pencere": {
            "ilk_utc": datetime.fromtimestamp(int(df["ms"].iloc[0]) / 1000, UTC).isoformat(),
            "son_utc": datetime.fromtimestamp(int(df["ms"].iloc[-1]) / 1000, UTC).isoformat(),
            "odeme": int(len(df)), "gun": gun_sayisi,
            "eslesmeyen_odeme": int((~gecerli).sum()),
        },
        "toplam": {
            "sharpe": _sharpe(g["toplam"]),
            "yillik_getiri_pct": float(g["toplam"].mean() * 365 * 100),
            "yillik_vol_pct": float(g["toplam"].std(ddof=1) * math.sqrt(365) * 100),
            "max_drawdown": _dd(kum),
        },
        "funding_bileseni": {
            "sharpe": _sharpe(g["funding"]),
            "yillik_getiri_pct": float(g["funding"].mean() * 365 * 100),
            "max_drawdown": _dd(kum_f),
            "negatif_odeme_payi": float(neg.mean()),
            "en_uzun_negatif_seri_odeme": int(en_uzun),
        },
        "basis_bileseni": {
            "sharpe": _sharpe(g["basis_pnl"]),
            "yillik_getiri_pct": float(g["basis_pnl"].mean() * 365 * 100),
            "yillik_vol_pct": float(g["basis_pnl"].std(ddof=1) * math.sqrt(365) * 100),
        },
        "yillik": yillik,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semboller", default="runs/jev/evren50.txt")
    ap.add_argument("--funding-depo", default="data/funding")
    ap.add_argument("--premium-depo", default="data/turev/premium")
    ap.add_argument("--cikti", default="runs/faz16/carry_tavan.json")
    a = ap.parse_args()
    semboller = ["BTCUSDT", "ETHUSDT"] + [
        s for s in Path(a.semboller).read_text().split() if s.strip() and s not in ("BTCUSDT", "ETHUSDT")
    ]
    sonuclar, atlanan = {}, []
    for s in semboller:
        r = sembol_olc(s, Path(a.funding_depo), Path(a.premium_depo))
        if r is None:
            atlanan.append(s)
        else:
            sonuclar[s] = r

    # eşit ağırlıklı havuz: günlük ortalama (o gün verisi olan semboller üzerinden)
    gunler = {}
    for s, r in sonuclar.items():
        pass  # havuz aşağıda ham serilerden
    havuz = []
    for s in sonuclar:
        f = pd.read_parquet(Path(a.funding_depo) / f"{s}.parquet")
        p = pd.read_parquet(Path(a.premium_depo) / f"{s}.parquet", columns=["open_time", "close"])
        f = f[f["funding_time"] < IS_BITIS_MS].sort_values("funding_time")
        basis = pd.Series(p["close"].to_numpy(), index=(p["open_time"] + SAAT_MS).to_numpy())
        ft = ((f["funding_time"] + SAAT_MS // 2) // SAAT_MS * SAAT_MS).to_numpy()
        b = basis.reindex(ft).to_numpy()
        d = b - np.concatenate([[np.nan], b[:-1]])
        ok = ~np.isnan(d)
        havuz.append(pd.DataFrame({"gun": ft[ok] // 86_400_000, "toplam": f["funding_rate"].to_numpy()[ok] - d[ok], "sembol": s}))
    h = pd.concat(havuz)
    gunluk_sembol = h.groupby(["gun", "sembol"])["toplam"].sum().reset_index()
    havuz_gunluk = gunluk_sembol.groupby("gun")["toplam"].mean()
    havuz_uye = gunluk_sembol.groupby("gun")["sembol"].nunique()

    en_iyi = max(sonuclar.values(), key=lambda r: r["toplam"]["sharpe"] or -9)
    karar = {
        "esik_sharpe": ESIK_SHARPE, "esik_max_drawdown": ESIK_DD,
        "BTCUSDT_toplam_sharpe": sonuclar["BTCUSDT"]["toplam"]["sharpe"],
        "en_iyi_sembol": en_iyi["sembol"], "en_iyi_toplam_sharpe": en_iyi["toplam"]["sharpe"],
        "havuz_toplam_sharpe": _sharpe(havuz_gunluk),
        "havuz_yillik_getiri_pct": float(havuz_gunluk.mean() * 365 * 100),
        "havuz_max_drawdown": _dd(havuz_gunluk.cumsum().to_numpy()),
        "havuz_uye_medyan": float(havuz_uye.median()),
        "esigi_gecen_sembol": [s for s, r in sonuclar.items() if (r["toplam"]["sharpe"] or -9) >= ESIK_SHARPE],
    }
    karar["sonuc"] = (
        "FURTHER-RESEARCH-ELIGIBLE"
        if (karar["havuz_toplam_sharpe"] or -9) >= ESIK_SHARPE or karar["esigi_gecen_sembol"]
        else "CLOSE"
    )
    cikti = {
        "olcum": "Hat 1 / Adım 0 — delta-nötr carry maliyetsiz IS tavanı",
        "tur": "tavan ölçümü — çekiliş değil; ideal varsayımlar tavanı yukarı iter",
        "uretim_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "formul": "r_t = funding_rate_t − (basis_t − basis_{t−1}); basis = premium index 1h close (ödeme anında kapanan bar); günlük toplam; Sharpe = ort/σ·√365",
        "is_bitis_utc": datetime.fromtimestamp(IS_BITIS_MS / 1000, UTC).isoformat(),
        "karar": karar,
        "atlanan": atlanan,
        "semboller": sonuclar,
    }
    Path(a.cikti).parent.mkdir(parents=True, exist_ok=True)
    Path(a.cikti).write_text(json.dumps(cikti, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(karar, ensure_ascii=False, indent=1))
    print(f"\n{'sembol':12} {'gün':>5} {'toplam S':>9} {'fund S':>7} {'fund %/y':>9} {'basis vol%':>10} {'DD':>6} {'neg pay':>7} {'neg seri':>8}")
    for s, r in sorted(sonuclar.items(), key=lambda kv: -(kv[1]["toplam"]["sharpe"] or -9)):
        t, fb, bb = r["toplam"], r["funding_bileseni"], r["basis_bileseni"]
        print(f"{s:12} {r['pencere']['gun']:>5} {t['sharpe'] or float('nan'):>9.2f} {fb['sharpe'] or float('nan'):>7.2f} {fb['yillik_getiri_pct']:>9.1f} {bb['yillik_vol_pct']:>10.1f} {t['max_drawdown']*100:>5.1f}% {fb['negatif_odeme_payi']:>7.2f} {fb['en_uzun_negatif_seri_odeme']:>8}")
    print("atlanan:", atlanan)


if __name__ == "__main__":
    main()
