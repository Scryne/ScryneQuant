"""USDⓈ-M perpetual **mark price** 1h klines — arşivden, yalnız IS. **Elle çalıştırılır.** (Hat 1, veri kararı C)

    uv run python tools/faz16_mark_indir.py [--semboller BTCUSDT ETHUSDT]

Amaç: likidasyon mark price'a göre tetiklenir; repodaki premium index mark değildir. Bu seri
ikinci tavanın likidasyon **fiyat yolu**dur (C-1 iki senaryo, C-2 PIT/NON_PIT ayrımı —
`docs/arsiv/Faz-16-Hat1-Veri-Karari-Tasarimi.md`). Tek başına likidasyon sayısı üretmez (`mmr` yok).

- Kaynak: `data.binance.vision` `data/futures/um/monthly/markPriceKlines/<S>/1h/` + `.CHECKSUM`
  (`tools/faz12_premium_indir.py` kalıbı; aynı arşiv ailesi). Kapsam filtresi 2020-01 → 2025-02
  (ay dosyası tamamı iner; IS kesmesi ölçümde).
- Depo `data/turev/mark/<S>.parquet` + `<S>.kaynak.json` (zip SHA-256'ları, K-009/K-056);
  REST/spot depolarıyla karışmaz (K-056/1).
- Kontroller (reddetme yok, sayılır): saat ızgarasına oturmayan satır atılır ve sayılır;
  tekrar atılır ve sayılır; sonlu olmayan ya da ≤ 0 mark **hata** (kabul edilmez);
  beklenen saatlik ızgaraya göre boşluk sayısı ve listesi; spot 1h `close` (`data/evren`) ile
  oran |mark/spot − 1| > %5 olan bar `suspect` sayılır (bayrak, düşürülmez).
- İki koşu aynı parquet SHA'sını vermeli (deterministik; koşu sırası/paralellik sonucu değiştirmez).
- Bu araç **hiçbir getiriye bakmaz.**
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from scryne_quant.common.hash import dosya_hash
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.exchange.binance_arsiv import ArsivHatasi, HttpArsiv, checksum_dogrula

KOK = Path(__file__).resolve().parent.parent
DEPO = KOK / "data" / "turev" / "mark"
SPOT = KOK / "data" / "evren"
ONEK = "data/futures/um/monthly/markPriceKlines/"
_AY = re.compile(r"-1h-(\d{4}-\d{2})\.zip$")
IS_ILK_AY, IS_SON_AY = "2020-01", "2025-02"
SAAT = 3_600_000
SUTUNLAR = ["open_time", "open", "high", "low", "close", "volume", "close_time",
            "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]
SUSPECT_ORAN = 0.05


def _zip_oku(anahtar: str, bayt: bytes) -> tuple[pd.DataFrame, int]:
    with zipfile.ZipFile(io.BytesIO(bayt)) as z:
        adlar = z.namelist()
        if len(adlar) != 1:
            raise ArsivHatasi(f"{anahtar}: zip tek dosya içermeli, {len(adlar)} var")
        ham = z.read(adlar[0])
    if not ham.strip():
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close"]), 0
    ilk = ham.split(b"\n", 1)[0]
    baslik = 0 if ilk.startswith(b"open_time") else None
    if baslik is None and not ilk.split(b",", 1)[0].strip().isdigit():
        raise ArsivHatasi(f"{anahtar}: beklenmeyen biçim: {ham[:80]!r}")
    df = pd.read_csv(io.BytesIO(ham), header=baslik, names=SUTUNLAR, dtype={"open_time": "int64"}, float_precision="round_trip")
    return df[["open_time", "open", "high", "low", "close"]], (1 if baslik == 0 else 0)


def _dosya(arsiv: HttpArsiv, anahtar: str) -> tuple[str, pd.DataFrame, int]:
    bayt = arsiv.getir(anahtar)
    if bayt is None:
        raise ArsivHatasi(f"{anahtar}: listede var, indirilemedi")
    h = checksum_dogrula(anahtar, bayt, arsiv.getir(anahtar + ".CHECKSUM"))
    df, baslik = _zip_oku(anahtar, bayt)
    return h, df, baslik


def _sembol(arsiv: HttpArsiv, sembol: str, havuz: ThreadPoolExecutor) -> dict:
    _, anahtarlar = arsiv.listele(f"{ONEK}{sembol}/1h/")
    ziplar = sorted(a for a in anahtarlar if (m := _AY.search(a)) and IS_ILK_AY <= m.group(1) <= IS_SON_AY)
    if not ziplar:
        raise ArsivHatasi(f"{sembol}: {ONEK}{sembol}/1h/ altında IS ayı yok")
    hashler, parcalar, baslik_sayisi = {}, [], 0
    for anahtar, (h, df, baslik) in zip(ziplar, havuz.map(lambda a: _dosya(arsiv, a), ziplar), strict=True):
        hashler[anahtar] = h
        parcalar.append(df)
        baslik_sayisi += baslik
    df = pd.concat(parcalar, ignore_index=True).sort_values("open_time", kind="mergesort")
    tekrar = int(df.duplicated("open_time").sum())
    df = df.drop_duplicates("open_time", keep="last").reset_index(drop=True)
    hizasiz = int((df["open_time"] % SAAT != 0).sum())
    df = df[df["open_time"] % SAAT == 0].reset_index(drop=True)
    fiyat = df[["open", "high", "low", "close"]].to_numpy(dtype="float64")
    if not np.isfinite(fiyat).all() or (fiyat <= 0).any():
        raise ArsivHatasi(f"{sembol}: sonlu olmayan ya da ≤ 0 mark — kabul edilmez")
    # boşluk: saatlik ızgara
    zaman = df["open_time"].to_numpy()
    fark = np.diff(zaman)
    bosluk_idx = np.flatnonzero(fark != SAAT)
    bosluklar = [{"sonrasi": utc_str(int(zaman[i])), "eksik_bar": int(fark[i] // SAAT - 1)} for i in bosluk_idx]
    eksik_bar = int(sum(b["eksik_bar"] for b in bosluklar))
    beklenen = int((zaman[-1] - zaman[0]) // SAAT + 1)
    # spot oran kontrolü (suspect sayacı; düşürülmez)
    spot_yol = SPOT / sembol / "1h.parquet"
    suspect, spot_eslesen, oran_ozeti = None, None, None
    if spot_yol.exists():
        sp = pd.read_parquet(spot_yol, columns=["open_time", "close"])
        e = df.merge(sp, on="open_time", how="inner", suffixes=("", "_spot"))
        oran = e["close"] / e["close_spot"] - 1.0
        spot_eslesen = int(len(e))
        suspect = int((oran.abs() > SUSPECT_ORAN).sum())
        oran_ozeti = {"p1": float(oran.quantile(0.01)), "p50": float(oran.median()), "p99": float(oran.quantile(0.99)), "max_mutlak": float(oran.abs().max())}
    DEPO.mkdir(parents=True, exist_ok=True)
    yol = DEPO / f"{sembol}.parquet"
    df.to_parquet(yol, index=False)
    kaynak = {
        "sembol": sembol, "timeframe": "1h", "kaynak": "data.binance.vision", "onek": ONEK,
        "is_ay_araligi": [IS_ILK_AY, IS_SON_AY], "ay_sayisi": len(ziplar), "dosyalar": hashler,
        "baslik_satiri_atilan": baslik_sayisi, "satir": int(len(df)), "tekrar_atilan": tekrar, "hizasiz_atilan": hizasiz,
        "ilk": utc_str(int(zaman[0])), "son": utc_str(int(zaman[-1])),
        "beklenen_bar": beklenen, "eksik_bar": eksik_bar, "kapsama": float(len(df) / beklenen), "bosluk_sayisi": len(bosluklar), "bosluklar": bosluklar[:50],
        "spot_eslesen_bar": spot_eslesen, "suspect_oran_ustu_bar": suspect, "suspect_oran_esigi": SUSPECT_ORAN, "mark_spot_oran": oran_ozeti,
        "parquet_sha256": dosya_hash(yol),
        "uretildi": utc_str(simdi_ms()),
        "not": "Hat 1 veri kararı C: likidasyon fiyat yolu; mmr yok, likidasyon sayısı üretmez; PIT/NON_PIT ayrımı mmr tablosuna aittir (C-2)",
    }
    (DEPO / f"{sembol}.kaynak.json").write_text(json.dumps(kaynak, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {k: v for k, v in kaynak.items() if k not in ("dosyalar", "bosluklar")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semboller", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    a = ap.parse_args()
    arsiv = HttpArsiv(havuz=16)
    with ThreadPoolExecutor(max_workers=8) as havuz:
        for s in a.semboller:
            try:
                print(json.dumps(_sembol(arsiv, s.upper(), havuz), ensure_ascii=False), flush=True)
            except ArsivHatasi as hata:
                print(f"{s}: HATA {hata}", file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
