"""Makro seriler — ALFRED vintage'larıyla. **Elle çalıştırılır.** (Faz 12, K-052/5)

    uv run python tools/faz12_makro_indir.py

`makro_rejim` programının kaynak ölçüsü (`tools/faz12_kaynak_olcumu.py --makro`) için.
Seri listesi **önceden sabit** ve risk iştahının standart piyasa göstergeleri: VIX,
10 yıllık getiri, 10-2 eğimi, geniş dolar endeksi, Chicago Fed finansal koşullar endeksi
(NFCI, haftalık ve **revize edilir**), yüksek getirili kredi spread'i. Liste sonuca bakılarak
genişletilmez.

## PIT kuralı (K-052/5)

Her gözlem için ALFRED'in **bütün vintage'ları** indirilir. Bir gözlemin
`available_time`ı, değerinin ilk yayımlandığı vintage'ın `realtime_start` günüdür ve gün
çözünürlüğünde olduğu için **gün sonuna** (UTC 23:59:59.999) yuvarlanır. Revize edilen
seride (NFCI) t anında görülebilen değer, t'de geçerli olan vintage'ınkidir — bugünkü
son değer değil.

- FRED dosya tipi başına 2.000 vintage tarihi sınırı var; istek realtime penceresi yıl yıl
  bölünerek atılır ve birleştirilir.
- Değeri `.` olan satır "o vintage'da değer yok" demektir; NaN saklanır, uydurulmaz.
- **API anahtarı hiçbir dosyaya ve loga yazılmaz**; kaynak kaydındaki URL anahtarsızdır.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

from scryne_quant.common.zaman import simdi_ms, utc_str

KOK = Path(__file__).resolve().parent.parent
DEPO = KOK / "data" / "makro"
UC = "https://api.stlouisfed.org/fred/series/observations"
SERILER = ("VIXCLS", "DGS10", "T10Y2Y", "DTWEXBGS", "NFCI", "BAMLH0A0HYM2")
GOZLEM_BASI = "2017-01-01"
REALTIME_BASI_YIL = 2017


def _anahtar() -> str:
    for satir in (KOK / ".env").read_text(encoding="utf-8").splitlines():
        if satir.startswith("FRED_API_KEY="):
            deger = satir.split("=", 1)[1].strip().strip('"')
            if deger:
                return deger
    raise SystemExit("FRED_API_KEY .env'de yok")


def _istek(params: dict[str, str]) -> bytes | None:
    """Yanıt gövdesi; realtime penceresi serinin ALFRED geçmişinden önceyse `None`."""
    for deneme in range(5):
        try:
            r = requests.get(UC, params=params, timeout=90)
            if r.status_code == 200:
                return r.content
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(str(r.status_code))
            mesaj = r.json().get("error_message", "")
            if r.status_code == 400 and "does not exist in ALFRED" in mesaj:
                return None
            raise SystemExit(f"{params['series_id']}: HTTP {r.status_code} {mesaj}")
        except requests.RequestException:
            time.sleep(2**deneme)
    raise SystemExit(f"{params['series_id']}: 5 denemede indirilemedi")


def seri(sid: str, anahtar: str) -> dict:
    satirlar, parcalar = [], []
    bu_yil = pd.Timestamp.now(tz="UTC").year
    for yil in range(REALTIME_BASI_YIL, bu_yil + 1):
        params = {
            "series_id": sid,
            "file_type": "json",
            "observation_start": GOZLEM_BASI,
            "realtime_start": f"{yil}-01-01",
            "realtime_end": f"{yil}-12-31" if yil < bu_yil else "9999-12-31",
        }
        govde = _istek({**params, "api_key": anahtar})
        if govde is None:
            # Bu realtime penceresinde vintage yok: seri ALFRED'e daha geç girmiş. O yılın
            # "o gün ne biliniyordu" cevabı yoktur ve uydurulmaz; kayda geçer.
            parcalar.append({"params": params, "sha256": None, "vintage_yok": True})
            continue
        parcalar.append({"params": params, "sha256": hashlib.sha256(govde).hexdigest()})
        satirlar.extend(json.loads(govde)["observations"])
    if not satirlar:
        raise SystemExit(f"{sid}: hiçbir realtime penceresinde vintage yok")
    df = pd.DataFrame(satirlar, columns=["date", "realtime_start", "realtime_end", "value"])
    df["value"] = pd.to_numeric(df["value"].where(df["value"] != "."), errors="coerce")
    # Yıl pencereleri sınırda aynı vintage'ı iki kez döndürebilir; aynı (gözlem, vintage
    # başı) çiftinin değeri aynı olmak zorunda — değilse kaynak tutarsız, kabul edilmez.
    cift = df.groupby(["date", "realtime_start"])["value"].nunique(dropna=False)
    if (cift > 1).any():
        raise SystemExit(f"{sid}: aynı vintage için iki farklı değer — kaynak tutarsız")
    df = df.drop_duplicates(["date", "realtime_start"]).sort_values(["date", "realtime_start"])
    DEPO.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DEPO / f"{sid}.parquet", index=False)
    kayit = {
        "seri": sid,
        "uc": UC,
        "parcalar": parcalar,
        "satir": len(df),
        "gozlem": int(df["date"].nunique()),
        "ilk_gozlem": str(df["date"].min()),
        "son_gozlem": str(df["date"].max()),
        "vintage_sayisi": int(df["realtime_start"].nunique()),
        "ilk_vintage": str(df["realtime_start"].min()),
        "vintage_olmayan_yillar": [p["params"]["realtime_start"][:4] for p in parcalar
                                   if p.get("vintage_yok")],
    }
    (DEPO / f"{sid}.kaynak.json").write_text(
        json.dumps(kayit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {k: v for k, v in kayit.items() if k != "parcalar"}


def main() -> int:
    anahtar = _anahtar()
    ozet = []
    for sid in SERILER:
        s = seri(sid, anahtar)
        ozet.append(s)
        print(json.dumps(s, ensure_ascii=False), flush=True)
    (DEPO / "_ozet.json").write_text(
        json.dumps({"seriler": ozet, "uretildi": utc_str(simdi_ms())}, ensure_ascii=False,
                   indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
