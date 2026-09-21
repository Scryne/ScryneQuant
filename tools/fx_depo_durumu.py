"""21 FXCM çiftinin depo durumu: sağlayıcı kanıtı (kesif) × indirilmiş depo (manifesto). (K-100)

    uv run python tools/fx_depo_durumu.py [--depo data/fx] [--bas 2023-11-19 --bit 2024-12-13]
                                          [--cikti …json] [--md …md]

Hedef pencere `[bas, bit]` (o haftalar dahil). Çift başına sınıf (yalnız **kanıtlı** hücreler,
uydurma yok — K-090):

- `tam`        : pencerede sağlayıcıda var olan her hafta depoda `var` ya da `bozuk` (indirildi).
- `kismi`      : sağlayıcıda var olan bazı haftalar depoda yok (indirilmedi).
- `depoda_yok` : çift için hiç depo (manifesto) yok.

Ayrıca sayılır: `saglayici_yok` (kesif/manifesto 404 — sağlayıcı yayımlamamış; eksik dosya değil,
evrende üye değil, K-089/K-091), `bozuk` (sağlayıcı 200 döndü, gövde kullanılamaz; K-100/4 — dosya
var sayılır, bar yok), `kanit_yok` (kesif de manifesto da bilmiyor — bilinmiyor, "yok" değil).
Kaynak kanıtı `_gelen/<PAIR>/kesif-*.json` (HEAD) ve `<PAIR>/1h.kaynak.json`; çelişki → hata.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from scryne_quant.data import fx as fx_mod
from scryne_quant.data import fx_evren


def hafta_anahtarlari(bas: dt.date, bit: dt.date) -> list[str]:
    return [f"{y}-{w}" for y, w in (fx_mod.hafta_no(p) for p in fx_mod.pazarlar(bas, bit))]


def durum(depo: fx_mod.FxDepo, bas: dt.date, bit: dt.date) -> dict[str, Any]:
    varlik, kaynaklar = fx_evren.kanit_topla(depo, fx_mod.FXCM_CIFTLER)
    pencere = hafta_anahtarlari(bas, bit)
    ciftler: dict[str, dict[str, Any]] = {}
    ozet = {
        "tam": 0, "kismi": 0, "depoda_yok": 0,
        "saglayici_yok_hafta": 0, "bozuk_hafta": 0, "kanit_yok_hafta": 0,
    }
    for pair in fx_mod.FXCM_CIFTLER:
        manifesto = depo.manifesto(pair)
        haftalar = (manifesto or {}).get("haftalar", {})
        depo_var = {k for k, h in haftalar.items() if h.get("durum") == "var"}
        bozuk = sorted(k for k in pencere if haftalar.get(k, {}).get("durum") == "bozuk")
        kanit = varlik.get(pair, {})
        saglayici_var = [h for h in pencere if kanit.get(h) is True]
        saglayici_yok = [h for h in pencere if kanit.get(h) is False]
        kanit_yok = [h for h in pencere if h not in kanit]
        eksik = [h for h in saglayici_var if h not in depo_var and h not in bozuk]
        if manifesto is None:
            sinif = "depoda_yok"
        elif eksik:
            sinif = "kismi"
        else:
            sinif = "tam"
        ozet[sinif] += 1
        ozet["saglayici_yok_hafta"] += len(saglayici_yok)
        ozet["bozuk_hafta"] += len(bozuk)
        ozet["kanit_yok_hafta"] += len(kanit_yok)
        ciftler[pair] = {
            "sinif": sinif,
            "pencere_hafta": len(pencere),
            "saglayici_var": len(saglayici_var),
            "saglayici_yok": saglayici_yok,
            "bozuk": bozuk,
            "kanit_yok": kanit_yok,
            "depoda_var": len([h for h in pencere if h in depo_var]),
            "eksik_indirme": eksik,
            "bar_sayisi": (manifesto or {}).get("bar_sayisi"),
            "ilk": (manifesto or {}).get("ilk"),
            "son": (manifesto or {}).get("son"),
            "sha256": (manifesto or {}).get("sha256"),
        }
    return {
        "uretildi": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "pencere": {
            "bas": bas.isoformat(), "bit": bit.isoformat(), "hafta": len(pencere),
            "ilk_hafta": pencere[0], "son_hafta": pencere[-1],
        },
        "ozet": ozet,
        "kanit_kaynaklari": kaynaklar,
        "ciftler": ciftler,
    }


def markdown(rapor: dict[str, Any]) -> str:
    p = rapor["pencere"]
    ozet = ", ".join(f"{k} {v}" for k, v in rapor["ozet"].items())
    satirlar = [
        f"# FX depo durumu — {p['bas']}..{p['bit']} "
        f"({p['hafta']} hafta, {p['ilk_hafta']}…{p['son_hafta']})",
        "",
        f"Üretildi: {rapor['uretildi']}. Özet: {ozet}.",
        "",
        "Sınıflar: `tam` = sağlayıcıda var olan her hafta indirildi; `bozuk` = sağlayıcı 200 ama "
        "gövde kullanılamaz (K-100/4, dosya var sayılır, bar yok); sağlayıcı boşluğu = 404 "
        "(K-089/K-091, üye değil).",
        "",
        "| Çift | Sınıf | Sağlayıcıda var | Depoda var | Eksik indirme | Bozuk | "
        "Sağlayıcı boşluğu | Bar | Depo aralığı (UTC) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for pair, c in rapor["ciftler"].items():
        satirlar.append(
            f"| {pair} | {c['sinif']} | {c['saglayici_var']} | {c['depoda_var']} | "
            f"{len(c['eksik_indirme'])} | {', '.join(c['bozuk']) or '—'} | "
            f"{', '.join(c['saglayici_yok']) or '—'} | {c['bar_sayisi'] or '—'} | "
            f"{(c['ilk'] or '—')[:10]} → {(c['son'] or '—')[:10]} |"
        )
    return "\n".join(satirlar) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depo", default=str(fx_mod.VARSAYILAN_DEPO))
    ap.add_argument("--bas", default="2023-11-19")
    ap.add_argument("--bit", default="2024-12-13")
    ap.add_argument("--cikti", default=None)
    ap.add_argument("--md", default=None)
    args = ap.parse_args()
    rapor = durum(
        fx_mod.FxDepo(args.depo), dt.date.fromisoformat(args.bas), dt.date.fromisoformat(args.bit)
    )
    if args.cikti:
        Path(args.cikti).write_text(
            json.dumps(rapor, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.md:
        Path(args.md).write_text(markdown(rapor), encoding="utf-8", newline="\n")
    print(json.dumps(rapor["ozet"], ensure_ascii=False))
    for pair, c in rapor["ciftler"].items():
        print(
            f"  {pair}: {c['sinif']:10s} sağlayıcı {c['saglayici_var']:3d} depo "
            f"{c['depoda_var']:3d} eksik {len(c['eksik_indirme']):3d} bozuk {len(c['bozuk'])} "
            f"boşluk {len(c['saglayici_yok'])} kanıt-yok {len(c['kanit_yok'])}"
        )


if __name__ == "__main__":
    main()
