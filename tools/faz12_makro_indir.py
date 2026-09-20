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

import json
import sys
from pathlib import Path

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.data import alfred

KOK = Path(__file__).resolve().parent.parent
DEPO = KOK / "data" / "makro"
UC = alfred.UC
SERILER = ("VIXCLS", "DGS10", "T10Y2Y", "DTWEXBGS", "NFCI", "BAMLH0A0HYM2")
#: Araştırma programı dışı ek seriler (Hat 1 B-5 benchmark, veri kararı A, 2026-09-20):
#: 3 aylık hazine bonosu ikincil piyasa oranı (discount basis, günlük). `makro.SERILER`
#: program sözlüğüne **girmez** — o sözlük evren koşularının alanlarını ve koşu kimliğini
#: belirler (K-051/2); benchmark bir tavan girdisidir. Yalnız `--ek` ile iner; varsayılan
#: çağrı program serilerini olduğu gibi bırakır.
EK_SERILER = ("DTB3",)
GOZLEM_BASI = "2017-01-01"
REALTIME_BASI_YIL = 2017


def _anahtar() -> str:
    try:
        return alfred.anahtar_oku(KOK / ".env")
    except alfred.AlfredHatasi as hata:
        raise SystemExit(str(hata)) from hata


def seri(sid: str, anahtar: str) -> dict:
    try:
        df, parcalar = alfred.vintage_indir(sid, anahtar, gozlem_basi=GOZLEM_BASI,
                                            realtime_basi_yil=REALTIME_BASI_YIL)
    except alfred.AlfredHatasi as hata:
        raise SystemExit(str(hata)) from hata
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
    if "--ek" in sys.argv[1:]:
        # Yalnız ek seriler; program serilerinin dosyalarına ve `_ozet.json`a dokunmaz.
        for sid in EK_SERILER:
            print(json.dumps(seri(sid, anahtar), ensure_ascii=False), flush=True)
        return 0
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
