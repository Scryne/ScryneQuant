"""K-113 önce/sonra: kayıtlı ölçümler eski ve yeni kapı semantiğinde ne veriyor? (yeni koşu yok)

    uv run python tools/r5_oos_kapi_once_sonra.py [--cikti docs/research/records/…json]

Kaynak yalnız mevcut kayıtlar (`runs/fx`, `runs/faz12`, `runs/deneyler/degerlendirme`): her kaydın
`olcumler`i alınır, OOS penceresinden `oos_gun`/`oos_yillik_anlamli` türetilir (kayıt bu alanları
taşımıyorsa — K-113 öncesi — `Metrikler.yillik_anlamli` ile aynı formül: `bar × timeframe`), sonra
iki değerlendirme yapılır:

- **önce:** kayıtta duran `kapilar` bloğu (eski semantik, dosyadan; yeniden hesaplanmaz);
- **sonra:** aynı `olcumler` + türetilen iki alan, bugünkü `kapilar.degerlendir` (+ v2 varsa).

Rapor: strateji başına `oos_sharpe`/`oos_is_orani`/`oos_suresi` önce/sonra ve **öteki kapıların
birebir aynı kaldığı** (gevşeme yok kanıtı: hiçbir kapı `False`/`None` → `True` olmadı).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from scryne_quant.backtest.metrikler import ASGARI_YILLIK_PENCERE_MS
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.research import kapilar as kapilar_mod
from scryne_quant.research import kapilar_v2

VARSAYILAN_CIKTI = Path("docs/research/records/2026-09-22-R5-oos-kapi-once-sonra.json")


def _bul(o: Any, anahtar: str) -> Any:
    if isinstance(o, dict):
        if anahtar in o:
            return o[anahtar]
        for v in o.values():
            r = _bul(v, anahtar)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _bul(v, anahtar)
            if r is not None:
                return r
    return None


def _bloklar(
    kayit: dict[str, Any], yol: Path
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """`(strateji, olcumler, eski_kapilar)` üçlüleri; iki kayıt biçimi var."""
    if "cikti" in kayit and "stratejiler" in kayit["cikti"]:  # tip=degerlendirme (tek sembollü)
        return [
            (ad, s["olcumler"], s["kapilar"])
            for ad, s in kayit["cikti"]["stratejiler"].items()
            if "oos_sharpe" in s["olcumler"]
        ]
    olc = _bul(kayit, "olcumler")
    kap = _bul(kayit, "kapilar")
    if isinstance(olc, dict) and isinstance(kap, dict) and "oos_sharpe" in olc:
        sonuc = kayit.get("sonuc") if isinstance(kayit.get("sonuc"), dict) else None
        ad = (
            (sonuc or {}).get("strateji")
            or kayit.get("cekilis")
            or kayit.get("strateji")
            or yol.stem
        )
        return [(str(ad), olc, kap if "kapilar" in kap else {"kapilar": kap})]
    return []


def _satir(
    ad: str,
    yol: Path,
    tf: str,
    oos_bar: int,
    olc: dict[str, Any],
    eski: dict[str, Any],
) -> dict[str, Any]:
    tf_ms = timeframe_ms(tf)
    yeni_olc = dict(olc)
    yeni_olc.setdefault("oos_gun", kapilar_mod.oos_suresi_gun(oos_bar, tf_ms))
    yeni_olc.setdefault("oos_yillik_anlamli", oos_bar * tf_ms >= ASGARI_YILLIK_PENCERE_MS)
    v2_var = any(a in olc for a in ("pbo", "perturbasyon_dusus"))
    engeller = list(eski.get("mutlak_engeller") or [])
    yeni = (kapilar_v2.butun_kapilar if v2_var else kapilar_mod.degerlendir)(
        ad, yeni_olc, mutlak_engeller=engeller
    ).sozluk()
    eski_k = eski["kapilar"]
    degisen = {
        k: {"once": eski_k[k]["gecti"], "sonra": yeni["kapilar"][k]["gecti"]}
        for k in eski_k
        if k in yeni["kapilar"] and eski_k[k]["gecti"] != yeni["kapilar"][k]["gecti"]
    }
    gevseyen = [k for k, d in degisen.items() if d["sonra"] is True and d["once"] is not True]
    return {
        "strateji": ad,
        "kaynak": str(yol),
        "timeframe": tf,
        "oos_bar": oos_bar,
        "oos_gun": yeni_olc["oos_gun"],
        "oos_yillik_anlamli": yeni_olc["oos_yillik_anlamli"],
        "oos_sharpe": olc.get("oos_sharpe"),
        "once": {
            "gecti": eski.get("gecti"),
            "oos_sharpe": eski_k["oos_sharpe"]["gecti"],
            "oos_is_orani": eski_k.get("oos_is_orani", {}).get("gecti"),
            "kalan": eski.get("kalan_kapilar"),
        },
        "sonra": {
            "gecti": yeni["gecti"],
            "oos_suresi": yeni["kapilar"]["oos_suresi"]["gecti"],
            "oos_sharpe": yeni["kapilar"]["oos_sharpe"]["gecti"],
            "oos_is_orani": yeni["kapilar"]["oos_is_orani"]["gecti"],
            "kalan": yeni["kalan_kapilar"],
        },
        "degisen_kapilar": degisen,
        "gevseyen_kapilar": gevseyen,
    }


def olc(kokler: list[Path]) -> dict[str, Any]:
    satirlar: list[dict[str, Any]] = []
    for kok in kokler:
        for yol in sorted(kok.glob("*.json")):
            try:
                kayit = json.loads(yol.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            p = _bul(kayit, "pencereler")
            if not (isinstance(p, dict) and "out_of_sample" in p):
                continue
            oos = p["out_of_sample"]
            oos_bar = int(oos["bitis"]) - int(oos["baslangic"])
            tf = _bul(kayit, "timeframe") or "1h"
            for ad, o, k in _bloklar(kayit, yol):
                satirlar.append(_satir(ad, yol, tf, oos_bar, o, k))
    ozet = {
        "kayit": len(satirlar),
        "once_oos_sharpe_gecti": sum(1 for s in satirlar if s["once"]["oos_sharpe"] is True),
        "sonra_oos_sharpe_gecti": sum(1 for s in satirlar if s["sonra"]["oos_sharpe"] is True),
        "kisa_oos": sum(1 for s in satirlar if not s["oos_yillik_anlamli"]),
        "oos_suresi_kalan": sum(1 for s in satirlar if s["sonra"]["oos_suresi"] is False),
        "once_toplam_gecti": sum(1 for s in satirlar if s["once"]["gecti"] is True),
        "sonra_toplam_gecti": sum(1 for s in satirlar if s["sonra"]["gecti"] is True),
        "gevseyen_kapi_sayisi": sum(len(s["gevseyen_kapilar"]) for s in satirlar),
    }
    return {
        "uretildi": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "asgari_oos_gun": kapilar_mod.ASGARI_OOS_GUN,
        "ozet": ozet,
        "satirlar": satirlar,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--kok", type=Path, nargs="*",
        default=[Path("runs/fx"), Path("runs/faz12"), Path("runs/deneyler/degerlendirme")],
    )
    ap.add_argument("--cikti", type=Path, default=VARSAYILAN_CIKTI)
    a = ap.parse_args()
    govde = olc(a.kok)
    a.cikti.parent.mkdir(parents=True, exist_ok=True)
    a.cikti.write_text(json.dumps(govde, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(govde["ozet"], ensure_ascii=False))
    def f(v: bool | None) -> str:
        return "✓" if v is True else ("—" if v is None else "✗")

    print(f"{'strateji':<28}{'tf':<4}{'oos_gün':>9}{'anlamlı':>9}{'sharpe':>8}  "
          f"{'önce shp/top':<14}{'sonra süre/shp/top':<20} gevşeyen")
    for s in govde["satirlar"]:
        shp = s["oos_sharpe"] if s["oos_sharpe"] is not None else float("nan")
        print(f"{s['strateji'][:27]:<28}{s['timeframe']:<4}{s['oos_gun']:>9.1f}"
              f"{str(s['oos_yillik_anlamli']):>9}{shp:>8.2f}  "
              f"{f(s['once']['oos_sharpe'])}/{f(s['once']['gecti']):<12}"
              f"{f(s['sonra']['oos_suresi'])}/{f(s['sonra']['oos_sharpe'])}/"
              f"{f(s['sonra']['gecti']):<16} {s['gevseyen_kapilar'] or '-'}")
    print(f"kayıt : {a.cikti}")


if __name__ == "__main__":
    main()
