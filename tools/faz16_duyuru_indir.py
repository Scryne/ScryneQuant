"""Binance duyuruları — başlık ve **yayın zamanı**. (Faz 16)

    uv run python tools/faz16_duyuru_indir.py            # artımlı
    uv run python tools/faz16_duyuru_indir.py --hepsi     # baştan

Kaynak: `www.binance.com/bapi/composite/v1/public/cms/article/list/query` (kamuya açık CMS
ucu, kimlik gerektirmez). Kataloglar:

| id | Katalog | Neden |
| --- | --- | --- |
| 48 | New Cryptocurrency Listing | Erişimin **artması**: yeni pariteler, teminat, marjin |
| 161 | Delisting | Erişimin **azalması** |
| 49 | Latest Binance News | Kural/parametre değişiklikleri (kaldıraç, funding, koruma) |
| 93 | Latest Activities | Kampanya, yarışma, airdrop tetikleyicileri |
| 128 | Crypto Airdrop | HODLer airdrop duyuruları |

**PIT:** `releaseDate` duyurunun yayımlandığı an (ms, UTC) ve `available_time` odur —
bar benzeri olmayan gözlem, `event_time` değil (K-052/15). Metin sonradan düzenlenebilir;
bu yüzden başlık ilk görüldüğü hâliyle saklanır ve **değiştirilmez** (aynı `id` ikinci kez
gelirse ilk kayıt kalır, değişiklik `duzeltme` olarak sayılır).

**Bu araç hiçbir getiriye bakmaz ve hiçbir sınıflandırma yapmaz.** Ham başlık + zaman.
Sınıflandırma iki ayrı yolda: geçmiş için **kural** (sızıntısız), ileri için **Jev**
(K-049: LLM türetimi yalnız ileriye dönük toplanırsa kapıya aday olabilir).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

from scryne_quant.common.zaman import simdi_ms, utc_str

KOK = Path(__file__).resolve().parent.parent
DEPO = KOK / "data" / "duyuru"
PARQUET = DEPO / "duyurular.parquet"
KAYNAK = DEPO / "duyurular.kaynak.json"
UC = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
BASLIKLAR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
KATALOGLAR = {48: "listeleme", 161: "delisting", 49: "haber", 93: "etkinlik", 128: "airdrop",
              51: "api"}
SAYFA = 50
DENEME = 5
#: Sayfalar arası bekleme. CMS ucu 429 veriyor (ölçüldü: ~70 hızlı sayfada); bu araç günde
#: bir kez koşuyor, yavaşlığın maliyeti yok.
BEKLEME_S = 0.7
#: 429 sonrası bekleme; katlanarak artar.
KISIT_BEKLEME_S = 20.0


def _sayfa(katalog: int, sayfa_no: int) -> tuple[str, list[dict]]:
    son: Exception | str = "?"
    for deneme in range(DENEME):
        try:
            y = requests.get(UC, params={"type": 1, "catalogId": katalog, "pageNo": sayfa_no,
                                         "pageSize": SAYFA}, headers=BASLIKLAR, timeout=30)
            if y.status_code == 429:
                time.sleep(KISIT_BEKLEME_S * 2**deneme)
                son = "HTTP 429"
                continue
            if y.status_code == 200:
                govde = y.json()
                kataloglar = govde.get("data", {}).get("catalogs") or []
                if not kataloglar:
                    return "", []
                k0 = kataloglar[0]
                return str(k0.get("catalogName", "")), k0.get("articles") or []
            son = f"HTTP {y.status_code}"
        except requests.RequestException as hata:
            son = hata
        time.sleep(1.5 * 2**deneme)
    raise SystemExit(f"katalog {katalog} sayfa {sayfa_no} alınamadı: {son}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hepsi", action="store_true", help="Bilinen kayıtları da yeniden çek")
    ap.add_argument("--azami-sayfa", type=int, default=200)
    a = ap.parse_args()

    eski = pd.read_parquet(PARQUET) if PARQUET.exists() else pd.DataFrame(
        columns=["id", "katalog_id", "katalog", "kod", "baslik", "yayin_ms", "ilk_gorulen_ms"])
    bilinen = set(eski["id"].astype("int64")) if len(eski) else set()

    yeni: list[dict] = []
    duzeltme = 0
    eski_baslik = dict(zip(eski["id"].astype("int64"), eski["baslik"], strict=False)) if len(
        eski) else {}
    for kid, ad in KATALOGLAR.items():
        sayfa_no = 1
        while sayfa_no <= a.azami_sayfa:
            _, makaleler = _sayfa(kid, sayfa_no)
            time.sleep(BEKLEME_S)
            if not makaleler:
                break
            yeni_var = False
            for m in makaleler:
                mid = int(m["id"])
                if mid in bilinen:
                    if eski_baslik.get(mid) != m["title"]:
                        duzeltme += 1
                    if not a.hepsi:
                        continue
                yeni_var = True
                yeni.append({"id": mid, "katalog_id": kid, "katalog": ad,
                             "kod": str(m.get("code", "")), "baslik": str(m["title"]),
                             "yayin_ms": int(m["releaseDate"]), "ilk_gorulen_ms": simdi_ms()})
            # Sayfalar yeniden eskiye sıralı: hepsi bilinen bir sayfa geldiyse yeter.
            if not yeni_var and not a.hepsi:
                break
            sayfa_no += 1
        print(f"{ad:10} katalog {kid}: sayfa {sayfa_no - 1}", flush=True)

    df = pd.concat([eski, pd.DataFrame(yeni)], ignore_index=True) if yeni else eski
    if df.empty:
        raise SystemExit("hiç duyuru alınamadı")
    # İlk kayıt kalır: sonradan düzenlenen başlık geçmişi değiştirmez.
    df = (df.sort_values("ilk_gorulen_ms", kind="mergesort")
            .drop_duplicates("id", keep="first")
            .sort_values("yayin_ms", kind="mergesort")
            .reset_index(drop=True))
    DEPO.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PARQUET, index=False)
    ozet = {
        "uretildi": utc_str(simdi_ms()),
        "uc": UC,
        "kataloglar": KATALOGLAR,
        "satir": len(df),
        "yeni": len(yeni),
        "baslik_duzeltmesi_gorulen": duzeltme,
        "ilk": utc_str(int(df["yayin_ms"].min())),
        "son": utc_str(int(df["yayin_ms"].max())),
        "katalog_dagilimi": df["katalog"].value_counts().to_dict(),
        "parquet_sha256": hashlib.sha256(PARQUET.read_bytes()).hexdigest(),
    }
    KAYNAK.write_text(json.dumps(ozet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(json.dumps(ozet, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
