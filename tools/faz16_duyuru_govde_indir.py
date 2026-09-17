"""Duyuru gövdeleri — listeleme ve delisting metinleri. (Faz 16)

    uv run python tools/faz16_duyuru_govde_indir.py --katalog listeleme delisting

Başlıkların yalnızca **%17,7'sinde** parantezli sembol var (ölçüldü, 10.380 duyuru); "Notice of
Removal of Spot Trading Pairs - 2026-09-18" gibi bir başlık hangi pariteyi kaldırdığını
söylemiyor. Hangi sembolün etkilendiği gövdede.

Kaynak: aynı CMS'in `article/detail/query` ucu (`articleCode` ile). Gövde iç içe düğümlerden
oluşan bir JSON ağacı; metin düğümleri sırayla toplanır.

**PIT:** kayıt `yayin_ms` ile duyurular tablosundan gelir; gövde metni **ilk görüldüğü hâliyle**
saklanır (duyurular sonradan düzenlenebiliyor). Bu araç sınıflandırma yapmaz, getiriye bakmaz.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from scryne_quant.common.zaman import simdi_ms, utc_str

KOK = Path(__file__).resolve().parent.parent
DEPO = KOK / "data" / "duyuru"
DUYURU = DEPO / "duyurular.parquet"
PARQUET = DEPO / "govdeler.parquet"
KAYNAK = DEPO / "govdeler.kaynak.json"
UC = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query"
BASLIKLAR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "lang": "en",
             "clienttype": "web"}
BEKLEME_S = 0.5
KISIT_BEKLEME_S = 20.0
DENEME = 5


def _metin(dugum: Any, parcalar: list[str]) -> None:
    """Gövde ağacındaki metin düğümlerini sırayla toplar."""
    if isinstance(dugum, dict):
        if dugum.get("node") == "text" and isinstance(dugum.get("text"), str):
            parcalar.append(dugum["text"])
        for cocuk in dugum.get("child") or []:
            _metin(cocuk, parcalar)
    elif isinstance(dugum, list):
        for c in dugum:
            _metin(c, parcalar)


def _govde(kod: str) -> str | None:
    son: Any = "?"
    for deneme in range(DENEME):
        try:
            y = requests.get(UC, params={"articleCode": kod}, headers=BASLIKLAR, timeout=30)
            if y.status_code == 429:
                time.sleep(KISIT_BEKLEME_S * 2**deneme)
                son = "HTTP 429"
                continue
            if y.status_code == 200:
                veri = (y.json() or {}).get("data") or {}
                ham = veri.get("body")
                if not ham:
                    return ""
                parcalar: list[str] = []
                agac: Any = ham
                if isinstance(ham, str):
                    try:
                        agac = json.loads(ham)
                    except json.JSONDecodeError:
                        # Eski duyurularda gövde JSON ağacı değil düz HTML; etiketler
                        # temizlenir, metin olduğu gibi saklanır (ölçüldü: ~%0,1).
                        return re.sub(r"<[^>]+>", " ", ham)
                _metin(agac, parcalar)
                return "".join(parcalar)
            if y.status_code in (400, 404):
                return None
            son = f"HTTP {y.status_code}"
        except requests.RequestException as hata:
            son = hata
        time.sleep(1.5 * 2**deneme)
    raise SystemExit(f"gövde alınamadı ({kod}): {son}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--katalog", nargs="*", default=["listeleme", "delisting"])
    ap.add_argument("--azami", type=int, default=0, help="0 = sınırsız")
    a = ap.parse_args()

    duyuru = pd.read_parquet(DUYURU)
    hedef = duyuru[duyuru["katalog"].isin(a.katalog)].sort_values("yayin_ms", ascending=False)
    eski = pd.read_parquet(PARQUET) if PARQUET.exists() else pd.DataFrame(
        columns=["id", "kod", "metin", "indirildi_ms"])
    bilinen = set(eski["id"].astype("int64")) if len(eski) else set()
    kalan = hedef[~hedef["id"].isin(bilinen)]
    if a.azami:
        kalan = kalan.head(a.azami)
    print(f"{len(hedef)} duyuru, {len(bilinen)} zaten var, {len(kalan)} indirilecek", flush=True)

    yeni, hatali = [], 0
    for i, satir in enumerate(kalan.itertuples(), start=1):
        metin = _govde(str(satir.kod))
        if metin is None:
            hatali += 1
        else:
            yeni.append({"id": int(satir.id), "kod": str(satir.kod), "metin": metin,
                         "indirildi_ms": simdi_ms()})
        time.sleep(BEKLEME_S)
        if i % 100 == 0:
            print(f"  {i}/{len(kalan)}", flush=True)
            if yeni:
                pd.concat([eski, pd.DataFrame(yeni)], ignore_index=True).to_parquet(
                    PARQUET, index=False)

    df = pd.concat([eski, pd.DataFrame(yeni)], ignore_index=True) if yeni else eski
    df = df.drop_duplicates("id", keep="first").reset_index(drop=True)
    DEPO.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PARQUET, index=False)
    ozet = {
        "uretildi": utc_str(simdi_ms()),
        "uc": UC,
        "kataloglar": a.katalog,
        "satir": len(df),
        "yeni": len(yeni),
        "govdesi_alinamayan": hatali,
        "bos_govde": int((df["metin"].str.len() == 0).sum()),
        "ortalama_karakter": int(df["metin"].str.len().mean()) if len(df) else 0,
        "parquet_sha256": hashlib.sha256(PARQUET.read_bytes()).hexdigest(),
    }
    KAYNAK.write_text(json.dumps(ozet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(json.dumps(ozet, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
