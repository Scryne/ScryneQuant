"""`evren_dayanikliligi` eşiğinin kalibrasyonu. **Elle çalıştırılır.**

    uv run python tools/evren_dayaniklilik_kalibre.py

Diğer üç yeni kapı null dağılımından kalibre ediliyor (`tools/kalibrasyon_v2_kos.py`).
Bu kapı **edilemiyor** ve sebebi yazılı: null, sinyal takvimini kaydırarak edge'i yok
eder; evren dayanıklılığı ise edge'i değil **yoğunlaşmayı** ölçüyor. Kaydırılmış bir
portföy de yoğun olabilir, yani null "kabul edilebilir yoğunlaşma"yı tanımlamıyor.

Onun yerine **yapısal** bir kalibrasyon: aynı kıyas portföyü farklı yoğunlaşma
seviyelerinde koşturulup, en iyi katkı çıkarıldığında Sharpe'ın ne kadar düştüğü ölçülür.
İki uç bilinen:

- `azami_enstruman = 2` — tanımı gereği yoğun; bir ismi çıkarmak portföyün yarısını siler.
- `azami_enstruman = 20` — dağıtılmış; bir ismin çıkması az fark etmeli.

Eşik bu ikisinin arasından, ölçülen sayılara bakılarak seçilir ve **hangi sayılara
bakıldığı rapora yazılır.** Bu, null'a dayalı eşiklerden zayıf bir gerekçe ve öyle
olduğu kayıtlı: Faz 12'de gerçek cross-sectional adaylar çıktığında yeniden ölçülecek.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import git_durumu
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.research import evren_dayaniklilik as day_mod
from scryne_quant.research import evren_kosu
from scryne_quant.strategy.evren import EvrenGorunumu
from scryne_quant.strategy.kutuphane import EvrenEsitAgirlik

KOK = Path(__file__).resolve().parent.parent
TABLO = KOK / "data" / "evren" / "_evren" / "27b7a16ed0ed.parquet"
CIKTI = KOK / "runs" / "kalibrasyon-v2" / "evren-dayaniklilik.json"
BASLANGIC, BITIS = "2023-01", "2026-08"
YOGUNLUKLAR = (2, 3, 5, 10, 20)

#: İki varyant da koşuluyor: kıyasın Sharpe'ı pencereye göre işaret değiştiriyor ve oran
#: yalnızca pozitif Sharpe'ta tanımlı. Ölçülemeyen satır da rapora giriyor.
VARYANTLAR = ((True, "esit"), (False, "oynaklik"))


def main() -> int:
    maliyet = maliyet_mod.yukle()
    satirlar = []

    for esit, varyant in VARYANTLAR:
      for azami in YOGUNLUKLAR:
        basladi = time.perf_counter()
        strateji = EvrenEsitAgirlik(
            azami_enstruman=azami, azami_agirlik=1.0 / azami, esit_agirlik=esit
        )
        kurulum = evren_kosu.kur(
            TABLO,
            strateji,
            depo_kok=KOK / "data" / "evren",
            baslangic_ay=BASLANGIC,
            bitis_ay=BITIS,
            azami_sembol=400,
        )
        motor = CokluBacktest(strateji, maliyet)
        tam = motor.calistir(
            kurulum.gorunum,
            veri_sha256=kurulum.veri_sha256,
            olcum_baslangici=kurulum.olcum_baslangici,
        )

        def yeniden(cikarilanlar: frozenset[str], _k=kurulum, _m=motor, _s=strateji):
            gorunum = EvrenGorunumu(
                timeframe=_k.gorunum.timeframe,
                zamanlar=_k.gorunum.zamanlar,
                gorunumler=dict(_k.gorunum.gorunumler),
                uyelik=day_mod.uyeligi_dusur(dict(_k.gorunum.uyelik), cikarilanlar),
                kural_kimligi=_k.gorunum.kural_kimligi,
            )
            return _m.calistir(
                gorunum,
                veri_sha256=_k.veri_sha256,
                olcum_baslangici=_k.olcum_baslangici,
            )

        olcum = day_mod.olc(tam, yeniden, k=1)
        gecen = time.perf_counter() - basladi
        satir = {
            "varyant": varyant,
            "azami_enstruman": azami,
            "tam_sharpe": tam.metrikler.sharpe,
            "azaltilmis_sharpe": olcum.azaltilmis_sharpe,
            "oran": olcum.oran,
            "dusus": olcum.dusus,
            "cikarilan": olcum.cikarilan,
            "enstruman_sayisi": len(olcum.katkilar),
            "islem": tam.metrikler.islem_sayisi,
            "sure_sn": round(gecen, 1),
        }
        satirlar.append(satir)
        def _f(x: float | None) -> str:
            return "olculemedi" if x is None else f"{x:+.3f}"

        print(
            f"{varyant:<9} N={azami:>2}  tam={satir['tam_sharpe']:+.3f}  "
            f"azalt={_f(satir['azaltilmis_sharpe'])}  oran={_f(satir['oran'])}  "
            f"dusus={_f(satir['dusus'])}  enstruman={satir['enstruman_sayisi']:>3}  "
            f"islem={satir['islem']:>3}  ({gecen:.0f}s)",
            flush=True,
        )

    govde = {
        "tablo": str(TABLO),
        "pencere": {"baslangic": BASLANGIC, "bitis": BITIS},
        "strateji": "evren_esit_agirlik (kıyas)",
        "k": 1,
        "olcumler": satirlar,
        "uretildi": utc_str(simdi_ms()),
        "git": git_durumu(),
    }
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    metin = json.dumps(govde, ensure_ascii=False, indent=2, sort_keys=True)
    CIKTI.write_text(metin + "\n", encoding="utf-8")
    print(f"yazildi: {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
