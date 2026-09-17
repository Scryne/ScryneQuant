"""USDⓈ-M perpetual **konumlanma** geçmişi (`metrics`) — arşivden. **Elle çalıştırılır.** (Faz 16)

    uv run python tools/faz16_metrics_indir.py --sembol BTCUSDT ETHUSDT --bas 2024-01

`data.binance.vision` `futures/um/daily/metrics/<SEMBOL>/` altındaki günlük dosyalar. İçerik
5 dakikalık ızgarada:

| Sütun | Ne |
| --- | --- |
| `sum_open_interest` / `sum_open_interest_value` | Açık pozisyon (sözleşme / USD) |
| `count_toptrader_long_short_ratio` | Büyük hesapların **sayısında** long/short oranı |
| `sum_toptrader_long_short_ratio` | Büyük hesapların **pozisyon büyüklüğünde** long/short |
| `count_long_short_ratio` | Bütün hesapların sayısında long/short |
| `sum_taker_long_short_vol_ratio` | Taker alım/satım hacim oranı (agresif akış) |

**Neden bu kaynak:** funding kalabalığın *fiyatını*, basis vadeli talebi ölçüyordu (Faz 12);
bunlar kalabalığın *miktarını* ve *kimliğini* ölçüyor. Farklı bir ölçüm olup olmadığı
`tools/faz16_kaynak_olcumu.py` ile sayıya bağlanır — bu araç yalnızca indirir.

**PIT:** `create_time` gözlemin ait olduğu 5 dakikalık dilimin başı ve o an yayımlanır;
`available_time = create_time + 5 dk` alınır (dilim kapanmadan değer bilinemez, K-052/15).
Kesme ölçüm/çekiliş tarafında yapılır, burada ham saklanır.

Her zip `.CHECKSUM` ile doğrulanır, SHA-256'lar `<SEMBOL>.kaynak.json`a yazılır (K-009).
`data/turev/metrics/` altına yazar; REST ve kline depolarıyla karışmaz (K-056/1).

**Bu araç hiçbir getiriye bakmaz.**
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from scryne_quant.common.zaman import utc_str
from scryne_quant.exchange.binance_arsiv import ArsivHatasi, HttpArsiv, checksum_dogrula

KOK = Path(__file__).resolve().parent.parent
DEPO = KOK / "data" / "turev" / "metrics"
ONEK = "data/futures/um/daily/metrics/"
_GUN = re.compile(r"-metrics-(\d{4}-\d{2}-\d{2})\.zip$")
SAYISAL = ("sum_open_interest", "sum_open_interest_value", "count_toptrader_long_short_ratio",
           "sum_toptrader_long_short_ratio", "count_long_short_ratio",
           "sum_taker_long_short_vol_ratio")


def _zip_oku(anahtar: str, bayt: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(bayt)) as z:
        adlar = z.namelist()
        if len(adlar) != 1:
            raise ArsivHatasi(f"{anahtar}: zip tek dosya içermeli, {len(adlar)} var")
        ham = z.read(adlar[0])
    if not ham.strip():
        return pd.DataFrame(columns=["create_time", *SAYISAL])
    df = pd.read_csv(io.BytesIO(ham), float_precision="round_trip")
    if "create_time" not in df.columns:
        raise ArsivHatasi(f"{anahtar}: beklenmeyen biçim: {ham[:80]!r}")
    # Boş dizge ("") olan oran sütunları NaN kalır — uydurulmaz (K-024).
    for s in SAYISAL:
        if s not in df.columns:
            df[s] = float("nan")
        df[s] = pd.to_numeric(df[s], errors="coerce")
    # `astype("int64")` çözünürlüğü pandas'ın ayrıştırmada seçtiği birime bağlı (burada µs
    # geldi ve tarihler 1970'e düştü — ölçüldü). Birim açıkça sabitleniyor: ns → ms.
    zaman = pd.to_datetime(df["create_time"], utc=True).astype("datetime64[ns, UTC]")
    df["create_time"] = zaman.astype("int64") // 10**6
    return df[["create_time", *SAYISAL]]


def _dosya(arsiv: HttpArsiv, anahtar: str) -> tuple[str, pd.DataFrame]:
    bayt = arsiv.getir(anahtar)
    if bayt is None:
        raise ArsivHatasi(f"{anahtar}: listede var, indirilemedi")
    hash_ = checksum_dogrula(anahtar, bayt, arsiv.getir(anahtar + ".CHECKSUM"))
    return hash_, _zip_oku(anahtar, bayt)


def _sembol(arsiv: HttpArsiv, sembol: str, bas: str, havuz: ThreadPoolExecutor) -> dict:
    kaynak_yolu, parquet_yolu = DEPO / f"{sembol}.kaynak.json", DEPO / f"{sembol}.parquet"
    onceki = json.loads(kaynak_yolu.read_text(encoding="utf-8")) if kaynak_yolu.exists() else {}
    inen = dict(onceki.get("dosyalar", {}))
    _, anahtarlar = arsiv.listele(f"{ONEK}{sembol}/")
    ziplar = sorted(a for a in anahtarlar
                    if (m := _GUN.search(a)) and m.group(1) >= bas and a not in inen)
    if not ziplar and parquet_yolu.exists():
        return {"sembol": sembol, "durum": "guncel", "satir": onceki.get("satir")}
    if not ziplar and not inen:
        return {"sembol": sembol, "durum": "metrics_yok"}
    parcalar = [pd.read_parquet(parquet_yolu)] if parquet_yolu.exists() else []
    for anahtar, (hash_, df) in zip(
        ziplar, havuz.map(lambda a: _dosya(arsiv, a), ziplar), strict=True
    ):
        inen[anahtar] = hash_
        parcalar.append(df)
    df = pd.concat(parcalar, ignore_index=True).sort_values("create_time", kind="mergesort")
    tekrar = int(df.duplicated("create_time").sum())
    df = df.drop_duplicates("create_time", keep="last").reset_index(drop=True)
    DEPO.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parquet_yolu, index=False)
    kaynak = {
        "sembol": sembol,
        "kaynak": "data.binance.vision",
        "onek": ONEK,
        "dosyalar": dict(sorted(inen.items())),
        "gun_sayisi": len(inen),
        "satir": len(df),
        "tekrar_atilan": tekrar,
        "ilk": utc_str(int(df["create_time"].iloc[0])) if len(df) else None,
        "son": utc_str(int(df["create_time"].iloc[-1])) if len(df) else None,
        "bos_oran_sutunu": {s: int(df[s].isna().sum()) for s in SAYISAL},
    }
    kaynak_yolu.write_text(
        json.dumps(kaynak, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"durum": "indi", **{k: v for k, v in kaynak.items() if k != "dosyalar"}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sembol", nargs="*", help="Boşsa evren tablosundaki bütün üyeler")
    ap.add_argument("--bas", default="2023-01-01", help="Bu günden itibaren (YYYY-MM-DD)")
    ap.add_argument("--evren-tablo", default="data/evren/_evren/27b7a16ed0ed.parquet")
    ap.add_argument("--son-ay", default=None,
                    help="Evren tablosundan yalnız bu aydan sonraki üyeler")
    ap.add_argument("--is", dest="isci", type=int, default=6)
    a = ap.parse_args()

    if a.sembol:
        semboller = sorted({s.upper() for s in a.sembol})
    else:
        tablo = pd.read_parquet(KOK / a.evren_tablo)
        if a.son_ay:
            tablo = tablo[tablo["ay"].astype(str) >= a.son_ay]
        semboller = sorted(set(tablo["sembol"].astype(str)))
    print(f"{len(semboller)} sembol, {a.bas} sonrası", flush=True)

    arsiv = HttpArsiv(havuz=64)
    sonuclar: list[dict] = []
    with ThreadPoolExecutor(max_workers=a.isci) as dis, ThreadPoolExecutor(max_workers=48) as ic:
        for s in dis.map(lambda x: _sembol(arsiv, x, a.bas, ic), semboller):
            sonuclar.append(s)
            print(json.dumps(s, ensure_ascii=False), flush=True)
    ozet = {"sembol": len(sonuclar),
            "indi": sum(1 for s in sonuclar if s["durum"] == "indi"),
            "guncel": sum(1 for s in sonuclar if s["durum"] == "guncel"),
            "metrics_yok": sorted(s["sembol"] for s in sonuclar if s["durum"] == "metrics_yok"),
            "satir": sum(s.get("satir") or 0 for s in sonuclar)}
    print(json.dumps(ozet, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
