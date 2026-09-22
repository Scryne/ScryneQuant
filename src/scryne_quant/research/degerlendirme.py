"""Tam değerlendirme: IS/OOS + walk-forward + stres → K-019 kapıları. (Faz 4)

Faz 4'ün son adımı. Her strateji için üç ayrı ölçüm zincirini koşturur ve sonuçları
`kapilar.ESIKLER`e karşı değerlendirir:

1. **IS/OOS bölmesi** — in-sample'da optimize, out-of-sample'da test. `oos_sharpe`,
   `oos_is_orani`, `oos_islem`, `oos_max_drawdown` buradan.
2. **Walk-forward** — her katmanda yeniden optimize. `wf_pozitif_katman_orani` ve
   `wf_kararsizlik` buradan.
3. **Stres** — maliyet varsayımlarını bozarak. `stres_bozulma` buradan.

Üçünü tek bir komutta toplamanın sebebi, kapıların **birlikte** anlamlı olması: yüksek
OOS Sharpe'ı olan ama her katmanda başka parametre seçen bir strateji, tek bir sayıya
bakıldığında iyi görünür.

**Pahalı bir işlem** (BTC/USDT 1h, 5,2 yıl, 7 strateji için ~5 dakika). Bu bilinçli:
promotion kararı, ucuz olması gereken bir şey değil.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.research import analiz, kapilar, walkforward
from scryne_quant.research.bolme import Pencere, walk_forward
from scryne_quant.research.izgaralar import izgara
from scryne_quant.research.karsilastirma import ortak_isinma, ortak_pencereler
from scryne_quant.research.tarama import ASGARI_ISLEM, kosu, tara
from scryne_quant.strategy.kutuphane import KIYAS, KUTUPHANE

#: Varsayılan walk-forward pencereleri: 1 yıl eğitim, 3 ay test (1h barda).
EGITIM_BAR = 8766
TEST_BAR = 2190


def _kararsizlik(kararlilik: Mapping[str, Any]) -> float:
    """Katmanlar arası benzersiz parametre değeri oranı (ortalama).

    0 = her katmanda aynı parametre seçildi. 1 = her katmanda farklı bir parametre.
    Sabit (tek noktalı) parametreler paydayı şişirmesin diye yalnızca **değişen**
    parametreler sayılıyor; hiçbiri değişmiyorsa sonuç 0.
    """
    katman = kararlilik.get("katman", 0)
    if not katman:
        return float("nan")
    oranlar = [
        v["benzersiz"] / katman
        for v in kararlilik["parametreler"].values()
        if v["benzersiz"] > 1
    ]
    return float(np.mean(oranlar)) if oranlar else 0.0


def degerlendir(
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    *,
    stratejiler: Sequence[str] | None = None,
    oos_orani: float = 0.30,
    olcut: str = "sharpe",
    secim: str = "tepe",
    baslangic_sermaye: float = 10_000.0,
    egitim_bar: int = EGITIM_BAR,
    test_bar: int = TEST_BAR,
) -> dict[str, Any]:
    """Her strateji için üç ölçüm zincirini koşturup kapıları değerlendirir."""
    hepsi = {**KUTUPHANE, **KIYAS}
    adlar = list(stratejiler) if stratejiler else list(hepsi)

    n = len(bar_dizileri["open_time"])
    # Ortak ısınma ve ortak katmanlar: pencereler stratejiden stratejiye değişirse
    # tablo karşılaştırılamaz hâle gelir.
    isinma = ortak_isinma(adlar)
    ins_pencere, oos_pencere = ortak_pencereler(n, adlar, oos_orani=oos_orani)
    katmanlar = walk_forward(n, isinma, egitim_bar, test_bar, kaydirmali=True)
    tam = Pencere("tam", baslangic=isinma, bitis=n, isinma_baslangic=0)

    satirlar: dict[str, Any] = {}
    for ad in adlar:
        sinif = hepsi[ad]
        kiyas_mi = ad in KIYAS
        asgari = 0 if kiyas_mi else ASGARI_ISLEM

        tarama_sonucu = tara(
            sinif, izgara(ad), maliyet, sembol, timeframe, bar_dizileri, ins_pencere,
            olcut=olcut, baslangic_sermaye=baslangic_sermaye, asgari_islem=asgari,
        )
        en_iyi = tarama_sonucu.sec(secim)
        olcumler: dict[str, Any] = {}

        if en_iyi is not None:
            oos_sonuc = kosu(
                sinif(**en_iyi.sozluk_parametreler), maliyet, sembol, timeframe,
                bar_dizileri, oos_pencere, baslangic_sermaye=baslangic_sermaye,
            )
            oos = oos_sonuc.metrikler
            ins_sharpe = en_iyi.metrikler.sharpe
            olcumler |= {
                "oos_sharpe": oos.sharpe,
                "oos_getiri": oos.toplam_getiri,
                "oos_islem": oos.islem_sayisi,
                "oos_max_drawdown": oos.max_drawdown,
                "is_sharpe": ins_sharpe,
                # IS Sharpe pozitif değilse oran tanımsız: korunacak bir başarı yok.
                "oos_is_orani": (oos.sharpe / ins_sharpe) if ins_sharpe > 0 else float("nan"),
                # K-113: Sharpe'ın yorumlanabilirliği (ön koşul) ve OOS süresi (kapı) —
                # ikisi de ölçülen bar sayısından, `Metrikler.yillik_anlamli` ile aynı ölçek.
                "oos_yillik_anlamli": oos.yillik_anlamli,
                "oos_gun": kapilar.oos_suresi_gun(
                    int(oos_sonuc.ozkaynak.size), timeframe_ms(timeframe)
                ),
                "secilen": en_iyi.sozluk_parametreler,
                "plato_orani": tarama_sonucu.ust_yuzde_plato(),
            }

        wf = walkforward.calistir(
            sinif, izgara(ad), maliyet, sembol, timeframe, bar_dizileri, katmanlar,
            olcut=olcut, secim=secim, baslangic_sermaye=baslangic_sermaye,
            asgari_islem=asgari,
        )
        basarili = wf.basarili_katmanlar
        pozitif = sum(1 for k in basarili if k.test_metrikler.toplam_getiri > 0.0)
        olcumler |= {
            "wf_sharpe": wf.bilesik_metrikler.sharpe,
            "wf_getiri": wf.bilesik_metrikler.toplam_getiri,
            "wf_max_drawdown": wf.bilesik_metrikler.max_drawdown,
            "wf_islem": wf.bilesik_metrikler.islem_sayisi,
            "wf_katman": len(basarili),
            "wf_pozitif_katman": pozitif,
            "wf_pozitif_katman_orani": pozitif / len(basarili) if basarili else float("nan"),
            "wf_kararsizlik": _kararsizlik(wf.parametre_kararliligi()),
        }

        stres = analiz.stres(
            sinif(), maliyet, sembol, timeframe, bar_dizileri, tam,
            baslangic_sermaye=baslangic_sermaye,
        )
        olcumler["stres_bozulma"] = stres.bozulma()

        engeller = ["gecici_maliyet_modeli"] if maliyet.gecici else []
        satirlar[ad] = {
            "olcumler": olcumler,
            "kapilar": kapilar.degerlendir(ad, olcumler, mutlak_engeller=engeller).sozluk(),
        }

    return {
        "sembol": sembol,
        "timeframe": timeframe,
        "olcut": olcut,
        "baslangic_sermaye": baslangic_sermaye,
        "pencereler": {
            "in_sample": ins_pencere.sozluk(),
            "out_of_sample": oos_pencere.sozluk(),
            "walk_forward": {
                "isinma": isinma,
                "egitim_bar": egitim_bar,
                "test_bar": test_bar,
                "katman": len(katmanlar),
            },
        },
        "esikler": kapilar.esik_tablosu(),
        "stratejiler": satirlar,
        "gecen": sorted(a for a, s in satirlar.items() if s["kapilar"]["gecti"]),
    }
