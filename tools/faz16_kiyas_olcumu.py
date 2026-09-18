"""Kıyasın kendi parametre uzayı: sıfır noktası neredeymiş? (Faz 16, K-030'un denetimi)

    uv run python tools/faz16_kiyas_olcumu.py [--pencere is|oos|tam|hepsi]

**Soru:** `evren_esit_agirlik` kıyası `azami_enstruman = 10`, `yeniden_dengele_bar = 168`
ile koşuyor. Bu iki sayı **ölçülerek değil varsayılan olarak** seçildi ve Faz 12-16'nın on
çekilişinin tamamı bu sıfır noktasına karşı değerlendirildi. `kurma_evren` programı yan
ürün olarak n=5'in OOS Sharpe'ının 0,333, n=10'unkinin 0,167 olduğunu gösterdi — iki kat.

Bu araç o uzayı bütünüyle ölçüyor.

## Bu bir çekiliş değildir (K-039, K-051)

Kıyas bir **iddia taşımıyor**: "bu strateji para kazandırır" demiyor, "hiçbir seçim
yapmasaydım ne olurdu" sorusunun cevabını tanımlıyor. K-030 onu zaten defter dışında
tutuyor. Burada seçilen bir parametre de yok — bütün ızgara raporlanıyor, "en iyisi"
alınıp bir stratejiye dönüştürülmüyor.

## Ama sonucu bir karara bağlanmak zorunda

Ölçüm iki sonuçtan birini verecek:

- **Kıyasın en iyi parametresi IS ve OOS'ta aynıysa**, kıyas ayarlanabilir bir şeydir ve
  "her çekiliş kıyas ailesinin en iyisini geçmeli" kuralı yazılabilir. Bu çıtayı
  **yükseltir**, yani K-007'nin yönünde güvenlidir.
- **Aynı değilse**, kıyası ayarlamak ilkece imkânsızdır: bugün "en iyi" denen parametre
  yarın en iyi olmayacaktır ve onu sıfır noktası yapmak, kıyası kendisi bir aşırı uydurma
  ürünü hâline getirir. O durumda tek dürüst kıyas **parametresiz** olandır: evrenin
  uygun bütün üyelerini eşit taşımak.

  **Ama parametresiz kıyas bugünkü sözleşmede var olamıyor** (ölçüldü, ilk koşuda çıktı):
  evren kuralının `ust_n`'i 50, `hedef_brut` 0,2, yani eşit pay 0,004 — kurma katmanının
  asgari ağırlık tabanı 0,005'in **altında**. "Herkesi taşı" kıyası bu yüzden kurulamıyor;
  kurulabilmesi ya tabanı indirmeyi ya brütü büyütmeyi gerektirir ve ikisi de ayrı birer
  karardır. Izgaranın üst ucu bu yüzden tabanı aşan en büyük yoğunluk.

Hangi sonucun çıkacağı **ölçülmeden** karara bağlanamaz; o yüzden karar bu aracın
çıktısından sonra yazılır.

## Kurallar

- Bütün koşular aynı evren (`27b7a16ed0ed`), aynı maliyet, aynı K-059 değerleme politikası.
- `hedef_brut` sabit 0,2: bir performans düğmesi değil, risk iştahı; değiştirmek maruziyeti
  ölçekler ve bütün kayıtlı çekilişlerle karşılaştırılabilirliği bozar.
- Kıyasın tavanı koşucunun kurduğu gibi: `azami_agirlik = hedef_brut / azami_enstruman`
  (yani tam eşit pay). Bu bir eksen değil, kıyasın tanımı.
- Izgaranın üst ucu (`_azami_yogunluk`) elle yazılmıyor, `hedef_brut` ve asgari ağırlık
  tabanından hesaplanıyor: ikisinden biri değişirse üst uç da değişmeli.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import git_durumu
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.strategy.kutuphane import EvrenEsitAgirlik

sys.path.insert(0, str(Path(__file__).resolve().parent))
from faz12_evren_kos import _veri_uretici  # noqa: E402

KOK = Path(__file__).resolve().parent.parent
CIKTI = KOK / "runs" / "faz16" / "kiyas-olcumu.json"

#: Yoğunluk ekseni. Üst uç **ölçülerek** bulundu: "herkesi taşı" (n = 50, evren kuralının
#: `ust_n`'i) bu brüt hedefte **ifade edilemiyor** — eşit pay 0,2/50 = 0,004 ve kurma
#: katmanının asgari ağırlık tabanı 0,005 (`VARSAYILAN_ASGARI_AGIRLIK`: "ekonomik olarak
#: anlamsızı sıfır say"). Yani parametresiz kıyas, bugünkü sözleşmede var olamıyor; tabanı
#: indirmek ya da brütü büyütmek ayrı birer karar. Üst uç, tabanı aşan en büyük yoğunluk.
YOGUNLUK = (5, 10, 20, 30)
#: `hedef_brut / n > VARSAYILAN_ASGARI_AGIRLIK` sağlayan en büyük `n` (hesaplanıyor,
#: elle yazılmıyor: taban ya da brüt değişirse bu sayı da değişmeli).
#: Dengeleme periyodu (bar). 168 = haftalık, 336 = iki haftalık, 720 = aylık.
DENGELEME = (168, 336, 720)
HEDEF_BRUT = 0.2


def _azami_yogunluk() -> int:
    from scryne_quant.strategy.kurma import VARSAYILAN_ASGARI_AGIRLIK

    n = 1
    while HEDEF_BRUT / (n + 1) > VARSAYILAN_ASGARI_AGIRLIK:
        n += 1
    return n


def _kiyas(n: int, periyot: int) -> EvrenEsitAgirlik:
    return EvrenEsitAgirlik(
        yeniden_dengele_bar=periyot,
        azami_enstruman=n,
        azami_agirlik=HEDEF_BRUT / n,
        hedef_brut=HEDEF_BRUT,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pencere", choices=("is", "oos", "tam", "hepsi"), default="hepsi")
    a = ap.parse_args()

    basladi = time.perf_counter()
    veri = _veri_uretici("kurma_evren")()
    print(f"veri hazır · {len(veri.diziler)} sembol · {len(veri):,} bar "
          f"({time.perf_counter() - basladi:.0f} s)", flush=True)
    maliyet = maliyet_mod.yukle()
    ins, oos, tam, _ = ed.pencereler(veri)
    pencereler = {"is": ins, "oos": oos, "tam": tam}
    if a.pencere != "hepsi":
        pencereler = {a.pencere: pencereler[a.pencere]}

    azami = _azami_yogunluk()
    yogunluk = (*YOGUNLUK, azami)
    print(f"yoğunluk ekseni {yogunluk} · ifade edilebilir azami n = {azami} "
          f"(hedef_brut {HEDEF_BRUT}, asgari ağırlık tabanı aşılıyor)", flush=True)
    satirlar: list[dict] = []
    for ad, pencere in pencereler.items():
        for n in yogunluk:
            for periyot in DENGELEME:
                t0 = time.perf_counter()
                r = ed.kosu(_kiyas(n, periyot), maliyet, veri, pencere)
                m = r.metrikler
                satirlar.append({
                    "pencere": ad,
                    "azami_enstruman": n,
                    "yeniden_dengele_bar": periyot,
                    "sharpe": m.sharpe,
                    "getiri": m.toplam_getiri,
                    "max_drawdown": m.max_drawdown,
                    "islem": m.islem_sayisi,
                    "maliyet_usdt": m.toplam_komisyon + m.toplam_slippage,
                    "ortalama_maruziyet": m.ortalama_maruziyet,
                    "sonuc_hash": r.sonuc_hash,
                })
                print(f"  {ad:4s} n={n:<3d} periyot={periyot:<4d} "
                      f"sharpe {m.sharpe:+.4f} getiri {m.toplam_getiri:+.4f} "
                      f"dd {m.max_drawdown:.4f} islem {m.islem_sayisi:<4d} "
                      f"({time.perf_counter() - t0:.0f} s)", flush=True)

    # --- Kararın dayanacağı sayı: en iyi parametre pencereden pencereye taşınıyor mu? ---
    def _en_iyi(ad: str) -> dict | None:
        aday = [s for s in satirlar if s["pencere"] == ad and np.isfinite(s["sharpe"])]
        return max(aday, key=lambda s: s["sharpe"]) if aday else None

    kararlilik: dict = {}
    if {"is", "oos"} <= set(pencereler):
        i, o = _en_iyi("is"), _en_iyi("oos")
        # IS'te en iyi olan parametrenin OOS'taki sırası: 1 ise kıyas ayarlanabilir.
        oos_sirali = sorted(
            [s for s in satirlar if s["pencere"] == "oos" and np.isfinite(s["sharpe"])],
            key=lambda s: -s["sharpe"],
        )
        is_en_iyinin_oos_sirasi = next(
            (k + 1 for k, s in enumerate(oos_sirali)
             if (s["azami_enstruman"], s["yeniden_dengele_bar"])
             == (i["azami_enstruman"], i["yeniden_dengele_bar"])),
            None,
        ) if i else None
        kararlilik = {
            "is_en_iyi": {k: i[k] for k in ("azami_enstruman", "yeniden_dengele_bar", "sharpe")},
            "oos_en_iyi": {k: o[k] for k in ("azami_enstruman", "yeniden_dengele_bar", "sharpe")},
            "ayni_parametre_mi": (i["azami_enstruman"], i["yeniden_dengele_bar"])
                                 == (o["azami_enstruman"], o["yeniden_dengele_bar"]),
            "is_en_iyinin_oos_sirasi": is_en_iyinin_oos_sirasi,
            "oos_aday_sayisi": len(oos_sirali),
            "yorum": ("Ayni parametre ve OOS sirasi 1 ise kiyas ayarlanabilir; degilse "
                      "kiyasi ayarlamak ilkece imkansiz ve parametresiz kiyas gerekir."),
        }

    rapor = {
        "uretildi": utc_str(simdi_ms()),
        "git": git_durumu(KOK),
        "cekilis_degil": True,
        "hedef_brut": HEDEF_BRUT,
        "evren": {"sembol": len(veri.diziler), "bar": len(veri),
                  "kural_kimligi": veri.kural_kimligi},
        "izgara": {"azami_enstruman": list(yogunluk),
                   "yeniden_dengele_bar": list(DENGELEME)},
        "ifade_edilemeyen": {
            "herkesi_tasi_n": 50,
            "esit_pay": HEDEF_BRUT / 50,
            "asgari_agirlik_tabani": 0.005,
            "not": ("Evren kuralinin ust_n'i 50; hedef_brut 0,2'de esit pay 0,004 ve kurma "
                    "katmaninin asgari agirlik tabani 0,005. Parametresiz 'herkesi tasi' "
                    "kiyasi bugunku sozlesmede VAR OLAMIYOR."),
            "ifade_edilebilir_azami_n": azami,
        },
        "satirlar": satirlar,
        "kararlilik": kararlilik,
        "sure_sn": round(time.perf_counter() - basladi, 1),
    }
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text(json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nyazıldı: {CIKTI}")
    if kararlilik:
        print(json.dumps(kararlilik, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
