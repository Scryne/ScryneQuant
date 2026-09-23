"""Aktif demo — ortalamaya dönüş araştırması (K-136).

Ön kayıt: `docs/research/records/2026-09-23-aktif-donus-onkayit.md` (koşudan önce commit'li).
Izgara, IS seçim kuralı ve OOS geçme ölçütü oradadır; bu betik onu uygular ve sonucu
`docs/research/records/2026-09-23-aktif-donus-sonuc.json`a yazar.

    .venv/Scripts/python.exe tools/aktif_arastirma.py
"""

from __future__ import annotations

import itertools
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from scryne_quant.aktif import geriye as geriye_mod
from scryne_quant.aktif.araci import binance_gecmis
from scryne_quant.cli.aktif import _araci, _ayar, _mt5_swap
from scryne_quant.common.zaman import simdi_ms, timeframe_ms

KOK = Path(__file__).resolve().parents[1]
SONUC = KOK / "docs/research/records/2026-09-23-aktif-donus-sonuc.json"
GUN = 730
IS_ORANI = 0.7
IZGARA = {"n": (2, 3, 5), "alt": (5.0, 10.0, 15.0), "trend": (100, 200), "tf": ("1h", "4h")}
ASGARI_ISLEM_HAFTA = 5.0
GECME = {"toplam_getiri": 0.0, "sharpe": 0.5, "pozitif_hafta": 0.5}


def kripto_barlar(semboller: tuple[str, ...], tf: str) -> dict[str, pd.DataFrame]:
    adim = timeframe_ms(tf)
    bitis = simdi_ms() // 86_400_000 * 86_400_000  # günlük sabit uç: tekrar koşu aynı veri
    bas = bitis - GUN * 86_400_000
    veri = KOK / "runs/aktif/veri"
    veri.mkdir(parents=True, exist_ok=True)
    cikti = {}
    for s in semboller:
        yol = veri / f"{s}_{tf}_{bas}_{bitis}.parquet"
        if yol.is_file():
            cikti[s] = pd.read_parquet(yol)
        else:
            df = binance_gecmis(s, tf, bas, bitis)
            df.to_parquet(yol)
            cikti[s] = df
        assert adim > 0
    return cikti


def bol(sonuc: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
    kesim = int(len(sonuc) * IS_ORANI)
    is_ = sonuc.iloc[:kesim]
    oos = sonuc.iloc[kesim:].copy()
    oos["ozkaynak"] = oos["ozkaynak"] / sonuc["ozkaynak"].iloc[kesim - 1]
    return geriye_mod.ozet(is_), geriye_mod.ozet(oos)


def piyasa(hesap: str) -> dict[str, Any]:
    ayar, ham = _ayar(hesap)
    mt5 = ayar.araci.startswith("mt5")
    araci = _araci(ayar, ham) if mt5 else None
    swap_ek = _mt5_swap(araci, ayar.semboller) if mt5 else {}
    yalniz_long = False if mt5 else bool(ham.get("yalniz_long", True))
    adaylar = []
    donem: dict[str, Any] = {}
    for tf in IZGARA["tf"]:
        if mt5:
            adet = GUN * 86_400_000 // timeframe_ms(tf)
            barlar = {s: araci.barlar(s, tf, int(min(adet, 99_000))) for s in ayar.semboller}
        else:
            barlar = kripto_barlar(ayar.semboller, tf)
        # K-136 notu: ilk koşuda bu sözlük zaman dilimi başına ezildi (yalnız 4h kaldı).
        donem[tf] = {s: [str(pd.to_datetime(df.index[0], unit="ms", utc=True)),
                         str(pd.to_datetime(df.index[-1], unit="ms", utc=True)), len(df)]
                     for s, df in barlar.items()}
        for n, alt, trend in itertools.product(IZGARA["n"], IZGARA["alt"], IZGARA["trend"]):
            p = {"n": n, "alt": alt, "ust": 100.0 - alt, "cikis": 50.0, "trend": trend}
            a = replace(ayar, strateji="rsi_donus", parametreler=p, timeframe=tf)
            sonuc = geriye_mod.geriye(barlar, a, yalniz_long=yalniz_long,
                                      ucret_bps=float(ham.get("ucret_bps", 10)),
                                      kayma_bps=float(ham.get("kayma_bps", 5)), **swap_ek)
            is_, oos = bol(sonuc)
            adaylar.append({"tf": tf, "parametreler": p, "is": is_, "oos": oos})
        print(f"{hesap} {tf}: {len(adaylar)} aday", flush=True)

    uygun = [a for a in adaylar if a["is"]["islem_hafta"] >= ASGARI_ISLEM_HAFTA]
    secilen = max(uygun, key=lambda a: (a["is"]["sharpe_haftalik_yillik"],
                                        -a["is"]["islem_hafta"]), default=None)
    hukum = None
    if secilen is not None:
        o = secilen["oos"]
        hukum = {
            "toplam_getiri": o["toplam_getiri"] > GECME["toplam_getiri"],
            "sharpe": o["sharpe_haftalik_yillik"] >= GECME["sharpe"],
            "pozitif_hafta": o["pozitif_hafta"] >= GECME["pozitif_hafta"],
        }
        hukum["gecti"] = all(hukum.values())
    oos_toplam = sorted(a["oos"]["toplam_getiri"] for a in adaylar)
    return {
        "hesap": hesap,
        "veri": donem,
        "aday_sayisi": len(adaylar),
        "uygun_sayisi": len(uygun),
        "secilen": secilen,
        "hukum": hukum,
        "oos_dagilim": {
            "pozitif_aday": sum(1 for x in oos_toplam if x > 0),
            "medyan_toplam": oos_toplam[len(oos_toplam) // 2],
            "en_iyi": oos_toplam[-1],
            "en_kotu": oos_toplam[0],
        },
        "adaylar": adaylar,
    }


def main() -> None:
    rapor = {"onkayit": "docs/research/records/2026-09-23-aktif-donus-onkayit.md",
             "zaman_ms": simdi_ms(), "piyasalar": [piyasa("kripto-donus"), piyasa("mt5-demo")]}
    SONUC.write_text(json.dumps(rapor, indent=1, ensure_ascii=False), encoding="utf-8")
    for p in rapor["piyasalar"]:
        s = p["secilen"]
        print(f"\n== {p['hesap']}: {p['uygun_sayisi']}/{p['aday_sayisi']} aday >= 5 işlem/hafta")
        if s is None:
            print("  seçim yok")
            continue
        print(f"  seçilen {s['tf']} {s['parametreler']}")
        for ad in ("is", "oos"):
            o = s[ad]
            print(f"  {ad:3s} toplam {o['toplam_getiri']:+.1%}"
                  f" · hafta ort {o['haftalik_ortalama']:+.2%}"
                  f" · kârlı hafta {o['pozitif_hafta']:.0%}"
                  f" · Sharpe {o['sharpe_haftalik_yillik']:.2f}"
                  f" · maxDD {o['max_dusus']:.1%} · işlem/hafta {o['islem_hafta']:.0f}")
        print(f"  hüküm {p['hukum']}")
        print(f"  OOS dağılımı (36 aday): {p['oos_dagilim']}")


if __name__ == "__main__":
    main()
