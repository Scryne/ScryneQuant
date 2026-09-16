"""Evren geneli premium index (basis) geçmişi — arşivden. **Elle çalıştırılır.** (Faz 12)

    uv run python tools/faz12_premium_indir.py

`turev_evren` programının basis çekilişleri için: funding'i indirilmiş (`data/turev/funding/`)
her sembolün USDⓈ-M perpetual **premium index** 1h barları `data.binance.vision`
`futures/um/monthly/premiumIndexKlines/<SEMBOL>/1h/` altından indirilir.

- Premium index barı: `(perp fiyatı − spot endeksi) / endeks`in saatlik OHLC'si. `close`,
  barın kapanışındaki basis; fiyat barıyla **aynı anda** kapanır ve aynı anda bilinir.
- **REST deposuyla karışmaz** (K-056/1): `data/turev/premium/` altına yazar.
- Her zip `.CHECKSUM` ile doğrulanır; SHA-256'lar `<SEMBOL>.kaynak.json`a yazılır (K-009).
- Eşleşme funding deposunun sembol listesiyle; perp'i olmayan sembol için dosya aranmaz.
- Bu araç **hiçbir getiriye bakmaz.** Yalnızca veriyi indirir.
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.exchange.binance_arsiv import ArsivHatasi, HttpArsiv, checksum_dogrula

KOK = Path(__file__).resolve().parent.parent
FUNDING = KOK / "data" / "turev" / "funding"
DEPO = KOK / "data" / "turev" / "premium"
ONEK = "data/futures/um/monthly/premiumIndexKlines/"
_AY = re.compile(r"-1h-(\d{4}-\d{2})\.zip$")
SUTUNLAR = ["open_time", "open", "high", "low", "close", "volume", "close_time",
            "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
SAAT = 3_600_000
#: **Değer eşiğiyle reddetme yok.** İki kez denendi, ikisi de yanlıştı — ölçüldü:
#: (1) |x| > 0,5: 2021-05-19 çöküşünde 1INCHUSDT kapanışı −0,432, `low` −0,50; ETHUSDT `low`
#: −0,23. (2) |x| ≥ 1: LEVERUSDT 2025-09-03'te `high` 1,247, sonra 120 saat 0,719'da donuk
#: (spot delisti sonrası bayat endeks; o saatlerde spot barı yok, sembol evren üyesi değil).
#: İkisi de arşivin gerçek içeriği. Yalnızca sonlu olmayan değer hatadır; uç değerler
#: ayıklanmaz, sayılır (`kaynak.json`).
UC_ESIK = 0.05


def _zip_oku(anahtar: str, bayt: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(bayt)) as z:
        adlar = z.namelist()
        if len(adlar) != 1:
            raise ArsivHatasi(f"{anahtar}: zip tek dosya içermeli, {len(adlar)} var")
        ham = z.read(adlar[0])
    if not ham.strip():
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close"])
    ilk = ham.split(b"\n", 1)[0]
    baslik = 0 if ilk.startswith(b"open_time") else None
    if baslik is None and not ilk.split(b",", 1)[0].strip().isdigit():
        raise ArsivHatasi(f"{anahtar}: beklenmeyen biçim: {ham[:80]!r}")
    df = pd.read_csv(io.BytesIO(ham), header=baslik, names=SUTUNLAR,
                     dtype={"open_time": "int64"}, float_precision="round_trip")
    return df[["open_time", "open", "high", "low", "close"]]


def _dosya(arsiv: HttpArsiv, anahtar: str) -> tuple[str, pd.DataFrame]:
    bayt = arsiv.getir(anahtar)
    if bayt is None:
        raise ArsivHatasi(f"{anahtar}: listede var, indirilemedi")
    hash_ = checksum_dogrula(anahtar, bayt, arsiv.getir(anahtar + ".CHECKSUM"))
    return hash_, _zip_oku(anahtar, bayt)


def _sembol(arsiv: HttpArsiv, sembol: str, havuz: ThreadPoolExecutor) -> dict:
    if (DEPO / f"{sembol}.kaynak.json").exists() and (DEPO / f"{sembol}.parquet").exists():
        return {"sembol": sembol, "durum": "indi"}
    _, anahtarlar = arsiv.listele(f"{ONEK}{sembol}/1h/")
    ziplar = sorted(a for a in anahtarlar if _AY.search(a))
    if not ziplar:
        return {"sembol": sembol, "durum": "premium_yok"}
    parcalar, hashler = [], {}
    for anahtar, (hash_, df) in zip(
        ziplar, havuz.map(lambda a: _dosya(arsiv, a), ziplar), strict=True
    ):
        hashler[anahtar] = hash_
        parcalar.append(df)
    df = pd.concat(parcalar, ignore_index=True).sort_values("open_time", kind="mergesort")
    tekrar = int(df.duplicated("open_time").sum())
    df = df.drop_duplicates("open_time", keep="last").reset_index(drop=True)
    hizasiz = int((df["open_time"] % SAAT != 0).sum())
    df = df[df["open_time"] % SAAT == 0].reset_index(drop=True)
    if not np.isfinite(df[["open", "high", "low", "close"]].to_numpy(dtype="float64")).all():
        raise ArsivHatasi(f"{sembol}: sonlu olmayan premium değeri — kabul edilmez")
    DEPO.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DEPO / f"{sembol}.parquet", index=False)
    kaynak = {
        "sembol": sembol,
        "kaynak": "data.binance.vision",
        "onek": ONEK,
        "dosyalar": hashler,
        "satir": len(df),
        "tekrar_atilan": tekrar,
        "hizasiz_atilan": hizasiz,
        "close_uc_bar": int((df["close"].abs() > UC_ESIK).sum()),
        "close_azami_mutlak": float(df["close"].abs().max()) if len(df) else None,
        "ilk": utc_str(int(df["open_time"].iloc[0])) if len(df) else None,
        "son": utc_str(int(df["open_time"].iloc[-1])) if len(df) else None,
    }
    (DEPO / f"{sembol}.kaynak.json").write_text(
        json.dumps(kaynak, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"durum": "indi", **{k: v for k, v in kaynak.items() if k != "dosyalar"}}


def main() -> int:
    semboller = sorted(p.stem for p in FUNDING.glob("*.parquet"))
    arsiv = HttpArsiv(havuz=64)
    sonuclar: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as dis, ThreadPoolExecutor(max_workers=48) as ic:
        for i, s in enumerate(dis.map(lambda x: _sembol(arsiv, x, ic), semboller), 1):
            sonuclar.append(s)
            print(f"[{i}/{len(semboller)}] {s['sembol']}: {s['durum']}", flush=True)
    ozet = {
        "funding_sembolu": len(semboller),
        "indi": sum(s["durum"] == "indi" for s in sonuclar),
        "premium_yok": sorted(s["sembol"] for s in sonuclar if s["durum"] == "premium_yok"),
        "hizasiz_atilan": sum(int(s.get("hizasiz_atilan", 0)) for s in sonuclar),
        "semboller": sonuclar,
        "uretildi": utc_str(simdi_ms()),
    }
    DEPO.mkdir(parents=True, exist_ok=True)
    (DEPO / "_ozet.json").write_text(
        json.dumps(ozet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"indi {ozet['indi']}/{len(semboller)}; premium yok {len(ozet['premium_yok'])}; "
          f"hizasız {ozet['hizasiz_atilan']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
