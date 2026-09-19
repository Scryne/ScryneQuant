"""M-1 "NY saati çapası" — program adayı 01'in gerekçe ölçüsü. **Çekiliş değil.**

Tanım `docs/program-adaylari/01-transkript-desenleri/README.md` §4'te 2026-09-15'te,
sonuç görülmeden yazıldı; bu betik o tanımı olduğu gibi hesaplar. Parametre yok, seçim yok:
çapa 13:00 ET, pencereler 60/30/60 dk, 96 plasebo çapası sabit. Karar kuralı önceden yazılı:

    Test 1: p = sıra(S(13:00 ET)) / 96 ≤ 0,05   VE   Test 2: kışın S(18:00 UTC) > S(17:00 UTC)
    → Lunch ailesi program kaydına gerekçe olarak girebilir. Değilse aile çekiliş harcanmadan
      kapanır; çapa, pencere ya da ufuk değiştirilerek TEKRAR ÖLÇÜLMEZ.

Olay (çapa a için, hafta içi ET günü): R = [a−60, a) aralığındaki 1m barların low min / high
max. [a, a+30) içindeki ilk bar `low < R_low` ve `close ≥ R_low` → alt süpürme,
y = ln(close[+60 dk] / close[olay]). Üst süpürme simetrik, y işaret çevrilmiş. Gün başına ilk
olay. S(a) = ortalama(y) / standart hata.

Kullanım: uv run python tools/faz16_m1_ny_saati.py [--veri data/market/BTCUSDT/1m.parquet]
Çıktı:    runs/faz16/m1_ny_saati.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

CAPA_ET_DK = 13 * 60  # 13:00 ET — Lunch ailesinin çapası (KAANERMI-LUNCH-*)
ON_DK, SON_DK, UFUK_DK = 60, 30, 60
PLASEBO_ADIM_DK = 15  # 96 çapa
ET = ZoneInfo("America/New_York")


def _yukle(yol: Path) -> tuple[pd.DataFrame, str]:
    sha = hashlib.sha256(yol.read_bytes()).hexdigest()
    df = pd.read_parquet(yol, columns=["open_time", "high", "low", "close", "quality_status"])
    df = df[df["quality_status"] == "ok"].reset_index(drop=True)
    ts = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    # ET yerel dakika (DST dahil): tz-aware → yerel naive → epoch dakikası
    yerel = ts.dt.tz_convert(ET).dt.tz_localize(None)
    df["et_dk"] = (yerel.astype("datetime64[ms]").astype("int64") // 60_000).astype(np.int64)
    df["utc_dk"] = (df["open_time"] // 60_000).astype(np.int64)
    df["kis"] = (ts.dt.tz_convert(ET).map(lambda t: t.utcoffset().total_seconds()) == -5 * 3600).to_numpy()
    return df, sha


def _s_istatistigi(df: pd.DataFrame, dk_sutunu: str, capa_dk: int, maske: np.ndarray | None = None) -> dict:
    """Verilen dakika ekseninde (ET ya da UTC) çapa a için S(a)."""
    d = df if maske is None else df[maske]
    m = d[dk_sutunu].to_numpy()
    baslangic = capa_dk - ON_DK
    seans = (m - baslangic) // 1440
    ofset = (m - baslangic) % 1440
    on = ofset < ON_DK
    son = (ofset >= ON_DK) & (ofset < ON_DK + SON_DK)

    r = pd.DataFrame({"seans": seans[on], "low": d["low"].to_numpy()[on], "high": d["high"].to_numpy()[on]})
    r = r.groupby("seans").agg(r_low=("low", "min"), r_high=("high", "max"))

    p = pd.DataFrame({
        "seans": seans[son], "ofset": ofset[son], "idx": np.flatnonzero(son),
        "low": d["low"].to_numpy()[son], "high": d["high"].to_numpy()[son], "close": d["close"].to_numpy()[son],
    }).merge(r, left_on="seans", right_index=True, how="inner").reset_index(drop=True)
    alt = (p["low"] < p["r_low"]) & (p["close"] >= p["r_low"])
    ust = (p["high"] > p["r_high"]) & (p["close"] <= p["r_high"])
    p = p[alt | ust].copy()
    p["isaret"] = np.where(alt.to_numpy()[p.index.to_numpy()], 1.0, -1.0)
    p = p.sort_values(["seans", "ofset"]).drop_duplicates("seans", keep="first")

    # Hafta içi: olay barının ET günü
    olay_idx = p["idx"].to_numpy()
    et_olay = d["et_dk"].to_numpy()[olay_idx]
    gun = ((et_olay // 1440) + 3) % 7  # 1970-01-01 Perşembe → +3 ile Pazartesi=0
    p = p[gun < 5]

    # İleri kapanış: olay + 60 dk, UTC dakikasında tam eşleşme (ET ekseni DST'de tekrarlı;
    # boşlukta olay düşer, uydurulmaz)
    utc = d["utc_dk"].to_numpy()
    ileri = pd.Series(d["close"].to_numpy(), index=utc)
    hedef = utc[p["idx"].to_numpy()] + UFUK_DK
    ileri_close = ileri.reindex(hedef).to_numpy()
    gecerli = ~np.isnan(ileri_close)
    y = p["isaret"].to_numpy()[gecerli] * np.log(ileri_close[gecerli] / p["close"].to_numpy()[gecerli])
    n = int(y.size)
    if n < 2:
        return {"n": n, "ortalama": None, "se": None, "S": None}
    ort = float(y.mean())
    se = float(y.std(ddof=1) / math.sqrt(n))
    return {"n": n, "ortalama": ort, "se": se, "S": ort / se if se > 0 else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--veri", default="data/market/BTCUSDT/1m.parquet")
    ap.add_argument("--cikti", default="runs/faz16/m1_ny_saati.json")
    a = ap.parse_args()

    df, sha = _yukle(Path(a.veri))

    # Test 1 — 96 çapa, ET ekseni
    plasebo = {}
    for capa in range(0, 1440, PLASEBO_ADIM_DK):
        plasebo[capa] = _s_istatistigi(df, "et_dk", capa)
    s_capa = plasebo[CAPA_ET_DK]["S"]
    s_hepsi = [v["S"] for v in plasebo.values() if v["S"] is not None]
    sira = sum(1 for s in s_hepsi if s >= s_capa)  # 1 = en büyük
    p_degeri = sira / len(s_hepsi)

    # Test 2 — kış (ET = UTC−5): UTC 18:00 (=13:00 ET) vs UTC 17:00
    kis = df["kis"].to_numpy()
    utc18 = _s_istatistigi(df, "utc_dk", 18 * 60, kis)
    utc17 = _s_istatistigi(df, "utc_dk", 17 * 60, kis)
    ny_destek = (utc18["S"] is not None and utc17["S"] is not None and utc18["S"] > utc17["S"])

    karar = bool(p_degeri <= 0.05 and ny_destek)
    sonuc = {
        "olcum": "M-1 NY saati çapası (program adayı 01 §4)",
        "tur": "gerekçe ölçüsü — çekiliş değil; karar kuralı 2026-09-15'te önceden yazıldı",
        "uretim_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "veri": {"yol": a.veri, "sha256": sha, "ok_bar": int(len(df)),
                  "ilk_utc": datetime.fromtimestamp(int(df["open_time"].iloc[0]) / 1000, UTC).isoformat(),
                  "son_utc": datetime.fromtimestamp(int(df["open_time"].iloc[-1]) / 1000, UTC).isoformat()},
        "tanim": {"capa_et": "13:00", "on_dk": ON_DK, "son_dk": SON_DK, "ufuk_dk": UFUK_DK,
                   "plasebo_capa_sayisi": len(plasebo), "hafta_ici": True, "gun_basina_ilk_olay": True},
        "test_1_saat_plasebosu": {
            "S_13_00_ET": s_capa, "n_13_00_ET": plasebo[CAPA_ET_DK]["n"],
            "sira_96_icinde": sira, "p_tek_tarafli": p_degeri, "gecti": p_degeri <= 0.05,
            "en_yuksek_5_capa": sorted(((f"{c//60:02d}:{c%60:02d}", round(v["S"], 3), v["n"]) for c, v in plasebo.items() if v["S"] is not None), key=lambda x: -x[1])[:5],
            "S_dagilimi": {"medyan": float(np.median(s_hepsi)), "min": float(min(s_hepsi)), "max": float(max(s_hepsi))},
        },
        "test_2_yaz_saati_ayrimi": {
            "kis_bar": int(kis.sum()), "S_utc_18_00": utc18, "S_utc_17_00": utc17, "ny_saatini_destekliyor": ny_destek,
        },
        "karar_kurali": "p ≤ 0,05 VE kışın S(18:00 UTC) > S(17:00 UTC) → Lunch ailesi programa girebilir",
        "lunch_ailesi_programa_girebilir": karar,
        "plasebo_tablosu": {f"{c//60:02d}:{c%60:02d}": v for c, v in plasebo.items()},
    }
    cikti = Path(a.cikti)
    cikti.parent.mkdir(parents=True, exist_ok=True)
    cikti.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
    ozet = {k: v for k, v in sonuc.items() if k != "plasebo_tablosu"}
    print(json.dumps(ozet, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
