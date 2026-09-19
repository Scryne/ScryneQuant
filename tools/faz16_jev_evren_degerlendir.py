"""K-076: yayın sonrası çoklu sembol Jev replay'ini sembol başına ve havuzda değerlendirir.

`sq jev degerlendir`in ölçütleriyle aynı (`jev/sonuc.py`: `open[t+1]` giriş, ufuk 1/4/24,
maliyet sonrası net, Wilson CI, al-tut kıyası). Eklediği tek şey **havuz** (bütün semboller tek
çerçevede) ve **saat-küme etkin n**: aynı saatte farklı sembollere verilen yönlü kararlar
bağımsız değildir (kripto kesitsel korelasyonu); isabet, saat başına bir gözlem sayılarak
ikinci kez raporlanır.

Kullanım: uv run python tools/faz16_jev_evren_degerlendir.py --semboller runs/jev/evren50.txt
Çıktı:    runs/jev/evren/_degerlendirme.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.jev.ayarlar import yukle as ayarlar_yukle
from scryne_quant.jev.defter import JevDefteri
from scryne_quant.jev.sonuc import defterden_cerceve, degerlendir, sonuclari_bagla, wilson


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semboller", default="runs/jev/evren50.txt")
    ap.add_argument("--kok", default="runs/jev/evren")
    ap.add_argument("--depo", default="data/evren")
    ap.add_argument("--cikti", default="runs/jev/evren/_degerlendirme.json")
    a = ap.parse_args()

    ayarlar = ayarlar_yukle()
    maliyet = maliyet_mod.yukle()
    parquet = ParquetDepo(Path(a.depo))
    h = ayarlar.birincil_ufuk_bar
    g, net = f"getiri_{h}", f"net_{h}"

    semboller = [s.strip() for s in Path(a.semboller).read_text().split() if s.strip()]
    sembol_raporlari: dict[str, dict] = {}
    havuz: list[pd.DataFrame] = []
    eksik: list[str] = []
    for sembol in semboller:
        yol = Path(a.kok) / f"{sembol}.sqlite"
        if not yol.exists():
            eksik.append(sembol)
            continue
        with JevDefteri(yol) as defter:
            kararlar = defterden_cerceve(defter.kararlar())
        if kararlar.empty:
            eksik.append(sembol)
            continue
        barlar = parquet.oku(sembol, "1h")
        bagli = sonuclari_bagla(kararlar, barlar, ayarlar=ayarlar, maliyet=maliyet)
        r = degerlendir(bagli, ayarlar=ayarlar)
        sembol_raporlari[sembol] = {
            k: r[k]
            for k in (
                "kanit", "gecerli", "hata_orani", "cekimserlik_orani", "yon_dagilimi",
                "yonlu", "yon_isabeti", "kiyas_al_tut", "ortalama_getiri",
            )
        }
        bagli = bagli.assign(sembol=sembol)
        havuz.append(bagli)

    if not havuz:
        raise SystemExit("hiç defter yok")
    hepsi = pd.concat(havuz, ignore_index=True)
    gecerli = hepsi[hepsi["durum_kodu"] == "gecerli"]
    leak = bool(gecerli["leak_riski"].any())
    bilinen = gecerli[gecerli[g].notna()]
    yonlu = bilinen[bilinen["yon"].isin(["long", "short"])].copy()
    yonlu["isabet"] = np.where(yonlu["yon"] == "long", yonlu[g] > 0, yonlu[g] < 0)

    k, n = int(yonlu["isabet"].sum()), int(len(yonlu))
    oran, alt, ust = wilson(k, n)

    # Saat-küme: aynı karar saati tek gözlem (isabet oranı o saatteki yönlü kararların ortalaması)
    saat = yonlu.groupby("karar_ms")["isabet"].mean()
    n_saat = int(len(saat))
    k_saat = float(saat.sum())
    oran_s = k_saat / n_saat if n_saat else None
    se_s = math.sqrt(oran_s * (1 - oran_s) / n_saat) if n_saat and oran_s not in (None, 0.0, 1.0) else None

    # Aynı saatte kaç sembol yön verdi (kümelenme ölçüsü)
    kume = yonlu.groupby("karar_ms").size()
    # Aynı saatte verilen yönlerin uyumu: long/short oranı
    ayni_yon = yonlu.groupby("karar_ms")["yon"].agg(lambda s: s.value_counts().iloc[0] / len(s))

    al_tut = bilinen[g] > 0
    net_yonlu = yonlu[net]
    rapor = {
        "karar": "K-076",
        "kanit": bool(len(gecerli)) and not leak,
        "sembol_sayisi": len(sembol_raporlari),
        "eksik_semboller": eksik,
        "toplam_kayit": int(len(hepsi)),
        "gecerli": int(len(gecerli)),
        "hata_orani": 1.0 - len(gecerli) / len(hepsi) if len(hepsi) else None,
        "cekimserlik_orani": float((gecerli["yon"] == "flat").mean()),
        "yon_dagilimi": gecerli["yon"].value_counts().to_dict(),
        "rejim_dagilimi": gecerli["rejim"].value_counts().to_dict() if "rejim" in gecerli else None,
        "sonucu_bilinen": int(len(bilinen)),
        "yonlu": n,
        "yon_isabeti": {"n": n, "isabet": k, "oran": oran, "ci95": [alt, ust]},
        "yon_isabeti_saat_kume": {
            "n_saat": n_saat, "oran": oran_s,
            "ci95_normal": [oran_s - 1.96 * se_s, oran_s + 1.96 * se_s] if se_s else None,
            "ayni_saatte_yonlu_sembol_medyan": float(kume.median()) if n_saat else None,
            "ayni_saatte_yonlu_sembol_max": int(kume.max()) if n_saat else None,
            "ayni_saatte_ayni_yon_orani_medyan": float(ayni_yon.median()) if n_saat else None,
        },
        "kiyas_al_tut": {
            "n": int(len(bilinen)), "isabet": int(al_tut.sum()),
            "oran": float(al_tut.mean()) if len(bilinen) else None,
        },
        "ortalama_getiri": {
            f"jev_yonlu_net_{h}": float(net_yonlu.mean()) if n else None,
            f"jev_yonlu_net_{h}_se": float(net_yonlu.std(ddof=1) / math.sqrt(n)) if n > 1 else None,
            f"jev_yonlu_brut_{h}": float((np.where(yonlu["yon"] == "long", 1, -1) * yonlu[g]).mean()) if n else None,
            f"al_tut_brut_{h}": float(bilinen[g].mean()) if len(bilinen) else None,
            **{f"jev_yonlu_net_{u}": float(yonlu[f"net_{u}"].mean()) if n else None for u in ayarlar.ufuk_bar if u != h},
        },
        "guven_kovalari": (
            yonlu.assign(kova=pd.cut(yonlu["yon_guven"], [0, 0.4, 0.5, 0.6, 0.7, 1.0], include_lowest=True))
            .groupby("kova", observed=True)["isabet"].agg(["count", "mean"]).rename(columns={"count": "n", "mean": "isabet_orani"})
            .reset_index().assign(kova=lambda d: d["kova"].astype(str)).to_dict("records")
            if n else []
        ),
        "long_short_ayri": {
            y: {"n": int((yonlu["yon"] == y).sum()), "isabet_orani": float(yonlu.loc[yonlu["yon"] == y, "isabet"].mean()) if (yonlu["yon"] == y).any() else None}
            for y in ("long", "short")
        },
        "sembol_basina": sembol_raporlari,
        "maliyet": maliyet.sozluk(),
    }
    Path(a.cikti).write_text(json.dumps(rapor, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    ozet = {k: v for k, v in rapor.items() if k != "sembol_basina"}
    print(json.dumps(ozet, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
