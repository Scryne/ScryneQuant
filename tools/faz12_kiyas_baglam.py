"""Türev programının kıyas bağlamı: `evren_esit_agirlik` IS / OOS / walk-forward. (Faz 12)

Kıyas bir çekiliş değildir (K-030); defterde sayılmaz. Çekilişlerin pencereleriyle **aynı**
bölmede (`evren_degerlendirme.pencereler`), aynı K-059 politikasıyla koşar. Walk-forward
kıyası tek noktalı "ızgara" ile `evren_degerlendirme.walkforward`tan geçer — seçim yok,
katmanlar ve sermaye taşıma çekilişlerle aynı.
"""

from __future__ import annotations

import json
from pathlib import Path

from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import git_durumu
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research import evren_kosu
from scryne_quant.strategy.kutuphane import EvrenEsitAgirlik

KOK = Path(__file__).resolve().parent.parent
TABLO = KOK / "data" / "evren" / "_evren" / "27b7a16ed0ed.parquet"
CIKTI = KOK / "runs" / "faz12" / "turev-kiyas-baglam.json"


def main() -> int:
    veri = evren_kosu.veri_kur(TABLO, depo_kok=KOK / "data" / "evren", azami_sembol=600)
    maliyet = maliyet_mod.yukle()
    ins, oos, _, katmanlar = ed.pencereler(veri)
    satirlar = []
    for yogunluk in (5, 10):
        p = {"yeniden_dengele_bar": 168, "azami_enstruman": yogunluk,
             "azami_agirlik": 0.2 / yogunluk, "hedef_brut": 0.2}
        m_is = ed.kosu(EvrenEsitAgirlik(**p), maliyet, veri, ins).metrikler
        m_oos = ed.kosu(EvrenEsitAgirlik(**p), maliyet, veri, oos).metrikler
        wf = ed.walkforward(EvrenEsitAgirlik, {a: (d,) for a, d in p.items()}, maliyet, veri,
                            katmanlar, asgari_islem=1)
        satir = {
            "parametreler": p,
            "is_sharpe": m_is.sharpe,
            "oos_sharpe": m_oos.sharpe,
            "oos_getiri": m_oos.toplam_getiri,
            "wf_sharpe": wf.bilesik_metrikler.sharpe,
            "wf_katman": len(wf.basarili_katmanlar),
            "wf_pozitif_katman": sum(1 for k in wf.basarili_katmanlar
                                     if k.test_metrikler.toplam_getiri > 0.0),
        }
        satirlar.append(satir)
        print(json.dumps(satir, ensure_ascii=False), flush=True)
    CIKTI.write_text(json.dumps({"kiyas": satirlar, "git": git_durumu(KOK)},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
