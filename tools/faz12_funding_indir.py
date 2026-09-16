"""Evren geneli funding geçmişi — arşivden. **Elle çalıştırılır.** (Faz 12, K-056/1)

    uv run python tools/faz12_funding_indir.py

Türev programının kaynak ölçüsü (`tools/faz12_kaynak_olcumu.py`) için: PIT evrenine
**hiç girmiş** her sembolün USDⓈ-M perpetual funding geçmişi `data.binance.vision`
`futures/um/monthly/fundingRate/` altından indirilir.

- **REST deposuyla karışmaz** (K-056/1): `data/funding/` REST'ten gelen BTC serisi; bu
  araç `data/turev/funding/` altına yazar.
- Her zip `.CHECKSUM` ile doğrulanır; doğrulanamayan dosya kabul edilmez. SHA-256'lar
  `<SEMBOL>.kaynak.json`a yazılır (veri seti kimliği, K-009).
- **Eşleşme ticker adıyla ve tam.** Spot `PEPEUSDT` ↔ perp `1000PEPEUSDT` gibi çarpanlı
  sözleşmeler eşlenmez; eşlenemeyen semboller kayda "perp yok" diye girer, tahmin
  yürütülmez. Kapsam oranı ölçünün parçası.
- Arşivin CSV'si `calc_time, funding_interval_hours, last_funding_rate` taşır. Aralık 8
  saatten farklı olabilir (4 s, 1 s); ham değer olduğu gibi saklanır, toplama ölçüm
  aracının işi.
- Bu araç **hiçbir getiriye bakmaz.** Yalnızca veriyi indirir (Spike 5'in kalıbı).
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.exchange.binance_arsiv import ArsivHatasi, HttpArsiv, checksum_dogrula

KOK = Path(__file__).resolve().parent.parent
TABLO = KOK / "data" / "evren" / "_evren" / "27b7a16ed0ed.parquet"
DEPO = KOK / "data" / "turev" / "funding"
ONEK = "data/futures/um/monthly/fundingRate/"
_AY = re.compile(r"-fundingRate-(\d{4}-\d{2})\.zip$")


def _zip_oku(anahtar: str, bayt: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(bayt)) as z:
        adlar = z.namelist()
        if len(adlar) != 1:
            raise ArsivHatasi(f"{anahtar}: zip tek dosya içermeli, {len(adlar)} var")
        ham = z.read(adlar[0])
    if not ham.strip():
        return pd.DataFrame(columns=["calc_time", "funding_interval_hours", "last_funding_rate"])
    ilk = ham.split(b"\n", 1)[0]
    baslik = 0 if ilk.startswith(b"calc_time") else None
    if baslik is None and not ilk.split(b",", 1)[0].strip().isdigit():
        raise ArsivHatasi(f"{anahtar}: beklenmeyen biçim: {ham[:80]!r}")
    df = pd.read_csv(
        io.BytesIO(ham),
        header=baslik,
        names=["calc_time", "funding_interval_hours", "last_funding_rate"],
        dtype={"calc_time": "int64", "funding_interval_hours": "int64"},
        float_precision="round_trip",
    )
    return df


def _dosya(arsiv: HttpArsiv, anahtar: str) -> tuple[str, pd.DataFrame]:
    bayt = arsiv.getir(anahtar)
    if bayt is None:
        raise ArsivHatasi(f"{anahtar}: listede var, indirilemedi")
    hash_ = checksum_dogrula(anahtar, bayt, arsiv.getir(anahtar + ".CHECKSUM"))
    return hash_, _zip_oku(anahtar, bayt)


def _sembol(arsiv: HttpArsiv, sembol: str, havuz: ThreadPoolExecutor) -> dict:
    kaynak_yolu = DEPO / f"{sembol}.kaynak.json"
    if kaynak_yolu.exists() and (DEPO / f"{sembol}.parquet").exists():
        kayit = json.loads(kaynak_yolu.read_text(encoding="utf-8"))
        return {"durum": "indi", **{k: v for k, v in kayit.items() if k != "dosyalar"}}
    _, anahtarlar = arsiv.listele(f"{ONEK}{sembol}/")
    ziplar = sorted(a for a in anahtarlar if _AY.search(a))
    if not ziplar:
        return {"sembol": sembol, "durum": "perp_yok"}
    parcalar, hashler = [], {}
    for anahtar, (hash_, df) in zip(
        ziplar, havuz.map(lambda a: _dosya(arsiv, a), ziplar), strict=True
    ):
        hashler[anahtar] = hash_
        parcalar.append(df)
    df = pd.concat(parcalar, ignore_index=True).sort_values("calc_time")
    tekrar = int(df.duplicated("calc_time").sum())
    df = df.drop_duplicates("calc_time", keep="last").reset_index(drop=True)
    if (df["last_funding_rate"].abs() > 0.05).any():
        raise ArsivHatasi(f"{sembol}: |funding| > %5 — veri hatası, kabul edilmez")
    DEPO.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DEPO / f"{sembol}.parquet", index=False)
    kaynak = {
        "sembol": sembol,
        "kaynak": "data.binance.vision",
        "onek": ONEK,
        "dosyalar": hashler,
        "satir": len(df),
        "tekrar_atilan": tekrar,
        "ilk": utc_str(int(df["calc_time"].iloc[0])),
        "son": utc_str(int(df["calc_time"].iloc[-1])),
        "aralik_saat": sorted(int(x) for x in df["funding_interval_hours"].unique()),
    }
    (DEPO / f"{sembol}.kaynak.json").write_text(
        json.dumps(kaynak, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"durum": "indi", **{k: v for k, v in kaynak.items() if k != "dosyalar"}}


def main() -> int:
    semboller = sorted(pd.read_parquet(TABLO)["sembol"].unique())
    arsiv = HttpArsiv(havuz=64)
    sonuclar: list[dict] = []
    # İki havuz: sembol düzeyi ve dosya düzeyi. Tek havuzda iç içe `map` kilitlenir.
    with ThreadPoolExecutor(max_workers=6) as dis, ThreadPoolExecutor(max_workers=48) as ic:
        for i, s in enumerate(dis.map(lambda x: _sembol(arsiv, x, ic), semboller), 1):
            sonuclar.append(s)
            print(f"[{i}/{len(semboller)}] {s['sembol']}: {s['durum']}", flush=True)
    ozet = {
        "tablo": str(TABLO.relative_to(KOK)),
        "evren_sembolu": len(semboller),
        "indi": sum(s["durum"] == "indi" for s in sonuclar),
        "perp_yok": sorted(s["sembol"] for s in sonuclar if s["durum"] == "perp_yok"),
        "semboller": sonuclar,
        "uretildi": utc_str(simdi_ms()),
    }
    (DEPO / "_ozet.json").write_text(
        json.dumps(ozet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"indi {ozet['indi']}/{len(semboller)}; perp yok {len(ozet['perp_yok'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
