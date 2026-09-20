"""Hat 2 / Adım 0 — funding uzlaşma anı (00/08/16 UTC) mikroyapısı. M-1 kalıbı; çekiliş değil.

Soru (Alpha-Discovery-Gap-Audit §3 Hat 2): funding ödeme anının çevresinde, ödeme işaretine
koşullu, maliyeti aşan bir fiyat sürüklenmesi var mı? K-042 funding *oranını* bilgi olarak
test etti; ödeme *anı* hiç ölçülmedi.

Olay: BTCUSDT funding ödeme anı `t` (`data/funding/BTCUSDT.parquet::funding_time`, saate
yuvarlı; Binance'te 00:00/08:00/16:00 UTC). Pencere ±60 dk, 1m barlar
(`data/market/BTCUSDT/1m.parquet`, yalnız `ok`):
    y_on  = ln(close[t]      / close[t−60])   (ödemeye giden sürüklenme)
    y_son = ln(close[t+60]   / close[t])      (ödeme sonrası)
Koşullama işareti `s` = **bir önceki** ödemenin oranının işareti — `t`de bilinen tek şey
(o anki oranı kullanmak kesinleşmemiş bir değeri kullanmak olurdu). Literatür mekanizması:
pozitif funding'de long'lar ödemeden kaçmak için kapatır → ödemeye doğru düşüş, sonra
toparlanma. İşaretli işlem: `y = s · (−y_on + y_son)` (öncesinde ters, sonrasında aynı yön).
Ayrıca tek bacaklar `s·(−y_on)` ve `s·y_son` ayrı raporlanır (tek gidiş-dönüş maliyet).
S = ortalama / standart hata (M-1 ile aynı).

Plasebo (M-1 kalıbı, 8 saatlik yapıyı koruyarak): çapa üçlüsü (a, a+8h, a+16h), a ∈ {00:00,
00:15, …, 07:45} → **32 üçlü**; gerçek olay a=00:00. p = sıra(S_gerçek) / 32, tek taraflı.
Ek şeffaflık: 96 tekil çapa tablosu (M-1'in tablosu) da yazılır, karar için kullanılmaz.
Plasebo çapalarında koşullama işareti aynı kuralla (çapadan önceki son ödemenin işareti).

Maliyet: `config/maliyet.json` gidiş-dönüş 30,6 bps. Çift bacak = 2 gidiş-dönüş.
Önceden yazılan karar kuralı: (|ortalama etki| − maliyet) ≤ 0 **veya** p > 0,05 → CLOSE.

Pencere: in-sample = BTC tek-sembol kuralı (OOS başlangıcı 2025-02-16 18:00 UTC dışlanır).
Rejim tanımı yok, Jev yok, backtest yok, strateji yok.

Kullanım: uv run python tools/faz16_funding_uzlasma.py
Çıktı:    runs/faz16/funding_uzlasma.json
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

from scryne_quant.common import maliyet as maliyet_mod

IS_BITIS_MS = 1739728800000  # 2025-02-16 18:00 UTC
PENCERE_DK = 60
SAAT_MS = 3_600_000
DK_MS = 60_000


def _s(y: np.ndarray) -> dict:
    n = int(y.size)
    if n < 2:
        return {"n": n, "ortalama": None, "se": None, "S": None}
    m, se = float(y.mean()), float(y.std(ddof=1) / math.sqrt(n))
    return {"n": n, "ortalama": m, "se": se, "S": m / se if se > 0 else None}


def _olc(kapanis: pd.Series, utc_dk_gun: np.ndarray, capalar_dk: tuple[int, ...],
         isaret_fn, ilk_ms: int, son_ms: int) -> dict:
    """Verilen gün-içi çapa dakikaları için işaretli y'ler; kapanis indeksi UTC dakika."""
    dk = kapanis.index.to_numpy()
    ilk_dk, son_dk = ilk_ms // DK_MS, son_ms // DK_MS
    gun0 = ilk_dk // 1440
    gunler = np.arange(gun0, son_dk // 1440 + 1)
    y_on_l, y_son_l, s_l = [], [], []
    for c in capalar_dk:
        t = gunler * 1440 + c
        t = t[(t - PENCERE_DK >= ilk_dk) & (t + PENCERE_DK <= son_dk)]
        c0 = kapanis.reindex(t - PENCERE_DK).to_numpy()
        c1 = kapanis.reindex(t).to_numpy()
        c2 = kapanis.reindex(t + PENCERE_DK).to_numpy()
        s = isaret_fn(t * DK_MS)
        ok = ~(np.isnan(c0) | np.isnan(c1) | np.isnan(c2)) & (s != 0)
        y_on_l.append(np.log(c1[ok] / c0[ok]))
        y_son_l.append(np.log(c2[ok] / c1[ok]))
        s_l.append(s[ok])
    y_on, y_son, s = map(np.concatenate, (y_on_l, y_son_l, s_l))
    return {
        "kosulsuz_straddle": _s(-y_on + y_son),
        "kosullu_straddle": _s(s * (-y_on + y_son)),
        "kosullu_on": _s(s * (-y_on)),
        "kosullu_son": _s(s * y_son),
        "pozitif_isaret_payi": float((s > 0).mean()) if s.size else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--veri", default="data/market/BTCUSDT/1m.parquet")
    ap.add_argument("--funding", default="data/funding/BTCUSDT.parquet")
    ap.add_argument("--cikti", default="runs/faz16/funding_uzlasma.json")
    a = ap.parse_args()

    v_yol, f_yol = Path(a.veri), Path(a.funding)
    df = pd.read_parquet(v_yol, columns=["open_time", "close", "quality_status"])
    df = df[(df["quality_status"] == "ok") & (df["open_time"] < IS_BITIS_MS)]
    kapanis = pd.Series(df["close"].to_numpy(), index=(df["open_time"] // DK_MS).to_numpy())
    ilk_ms, son_ms = int(df["open_time"].iloc[0]), int(df["open_time"].iloc[-1])

    f = pd.read_parquet(f_yol)
    f = f[f["funding_time"] < IS_BITIS_MS].sort_values("funding_time")
    f_ms = ((f["funding_time"] + SAAT_MS // 2) // SAAT_MS * SAAT_MS).to_numpy()
    f_oran = f["funding_rate"].to_numpy()
    # Gerçek olay saatleri: veri penceresindeki ödemelerin gün-içi dakikası
    pencere_f = f_ms[(f_ms >= ilk_ms) & (f_ms <= son_ms)]
    gun_ici = np.unique((pencere_f // DK_MS) % 1440)
    if not set(gun_ici.tolist()) <= {0, 480, 960}:
        raise SystemExit(f"beklenmeyen ödeme saati: {gun_ici}")

    def isaret_onceki(t_ms: np.ndarray) -> np.ndarray:
        """t'den ÖNCE kesinleşmiş son ödemenin işareti (t'deki ödeme dahil değil)."""
        idx = np.searchsorted(f_ms, t_ms, side="left") - 1
        s = np.where(idx >= 0, np.sign(f_oran[np.clip(idx, 0, None)]), 0.0)
        return s

    gercek = _olc(kapanis, None, (0, 480, 960), isaret_onceki, ilk_ms, son_ms)

    # Plasebo: 32 üçlü
    plasebo = {}
    for a0 in range(0, 480, 15):
        plasebo[a0] = _olc(kapanis, None, (a0, a0 + 480, a0 + 960), isaret_onceki, ilk_ms, son_ms)
    def sira_p(anahtar: str) -> dict:
        s_g = gercek[anahtar]["S"]
        s_h = [v[anahtar]["S"] for v in plasebo.values() if v[anahtar]["S"] is not None]
        sira = sum(1 for x in s_h if x >= s_g)
        return {"S_gercek": s_g, "sira_32_icinde": sira, "p_tek_tarafli": sira / len(s_h),
                "plasebo_S_medyan": float(np.median(s_h)), "plasebo_S_max": float(max(s_h)),
                "plasebo_S_min": float(min(s_h))}

    # 96 tekil çapa tablosu (şeffaflık; karar için değil)
    tekil = {}
    for c in range(0, 1440, 15):
        r = _olc(kapanis, None, (c,), isaret_onceki, ilk_ms, son_ms)
        tekil[f"{c // 60:02d}:{c % 60:02d}"] = {k: r[k]["S"] for k in ("kosulsuz_straddle", "kosullu_straddle", "kosullu_on", "kosullu_son")}

    m = maliyet_mod.yukle()
    gd = m.gidis_donus_bps / 10_000.0
    net = {
        "kosullu_straddle_net": gercek["kosullu_straddle"]["ortalama"] - 2 * gd,
        "kosullu_on_net": gercek["kosullu_on"]["ortalama"] - gd,
        "kosullu_son_net": gercek["kosullu_son"]["ortalama"] - gd,
        "kosulsuz_straddle_net": gercek["kosulsuz_straddle"]["ortalama"] - 2 * gd,
    }
    testler = {k: sira_p(k) for k in ("kosullu_straddle", "kosullu_on", "kosullu_son", "kosulsuz_straddle")}
    en_iyi = max(net, key=net.get)
    anahtar = en_iyi.replace("_net", "")
    karar = "CLOSE" if net[en_iyi] <= 0 or testler[anahtar]["p_tek_tarafli"] > 0.05 else "FURTHER-RESEARCH-ELIGIBLE"

    sonuc = {
        "olcum": "Hat 2 / Adım 0 — funding uzlaşma anı mikroyapısı (M-1 kalıbı)",
        "tur": "kaynak ölçümü — çekiliş değil; karar kuralı önceden yazılı",
        "uretim_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "veri": {"1m": {"yol": str(v_yol), "sha256": hashlib.sha256(v_yol.read_bytes()).hexdigest(), "ok_bar_is": int(len(df))},
                  "funding": {"yol": str(f_yol), "sha256": hashlib.sha256(f_yol.read_bytes()).hexdigest(), "odeme_is": int(len(f))}},
        "pencere": {"ilk_utc": datetime.fromtimestamp(ilk_ms / 1000, UTC).isoformat(),
                     "son_utc": datetime.fromtimestamp(son_ms / 1000, UTC).isoformat(),
                     "is_bitis_utc": datetime.fromtimestamp(IS_BITIS_MS / 1000, UTC).isoformat()},
        "olay": {"capalar_utc": ["00:00", "08:00", "16:00"], "pencere_dk": PENCERE_DK,
                  "kosullama": "bir önceki ödemenin oranının işareti (t'de bilinen)",
                  "olay_sayisi": gercek["kosullu_straddle"]["n"]},
        "gercek": gercek,
        "testler_32_uclu_plasebo": testler,
        "maliyet": {"gidis_donus_bps": m.gidis_donus_bps, "straddle_gidis_donus": 2},
        "net": net,
        "karar_kurali": "(|etki| − maliyet) ≤ 0 veya p > 0,05 → CLOSE",
        "en_iyi_bacak": en_iyi,
        "sonuc": karar,
        "tekil_96_capa_S": tekil,
        "plasebo_32": {f"{a0 // 60:02d}:{a0 % 60:02d}": {k: v[k]["S"] for k in ("kosullu_straddle", "kosullu_on", "kosullu_son", "kosulsuz_straddle")} for a0, v in plasebo.items()},
    }
    Path(a.cikti).parent.mkdir(parents=True, exist_ok=True)
    Path(a.cikti).write_text(json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
    ozet = {k: v for k, v in sonuc.items() if k not in ("tekil_96_capa_S", "plasebo_32")}
    print(json.dumps(ozet, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
