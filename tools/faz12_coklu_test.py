"""Faz 12 bitti kriteri: defter büyümesi sonrası `oos_sharpe` eşiğinin yeniden ölçümü. (K-044)

    uv run python tools/faz12_coklu_test.py --deneme 200 [--seed 0] [--birlestir]

`sq lab coklu-test` yalnızca tek sembollü çekilişleri ölçebiliyor; evren çekilişleri
(hipotez 39-) "değerlendirme kaydı yok" diye atlanıyordu. Bu araç ikisini **aynı oran
dizisiyle** koşturup birleştirir (`research/coklu_test_evren.py`).

- **Devam edilebilir:** her çekilişin satırları `runs/faz12/coklu-test/<kimlik>.json`a yazılır;
  aynı `deneme`/`seed` ile yazılmış dosya varsa atlanır. Saatler süren ölçüm bir kesintide
  baştan başlamaz.
- **Bellek:** evren verisi aile başına (ek veri gereksinimine göre) yüklenir ve bırakılır.
- **Doğrulama:** her evren çekilişi önce kayıttaki OOS `sonuc_hash`ini yeniden üretir.
- Uygunluk tek sembollü null ile aynı: `asgari_islem` ve `max_drawdown` kapıları.
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

import pyarrow as pa

from scryne_quant.cli.main import _coklu_test_cekilisleri
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import git_durumu
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.research import coklu_test as coklu_mod
from scryne_quant.research import coklu_test_evren as cte
from scryne_quant.research import deney as deney_mod
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research import evren_kosu
from scryne_quant.research import hipotez as hipotez_mod
from scryne_quant.research import kapilar as kapilar_mod
from scryne_quant.research import tarama as tarama_mod
from scryne_quant.research.izgaralar import PROGRAM_CEKILISLERI, cekilis_programi
from scryne_quant.strategy.kutuphane import EVREN_AILELER

KOK = Path(__file__).resolve().parent.parent
TABLO = KOK / "data" / "evren" / "_evren" / "27b7a16ed0ed.parquet"
CIKTI = KOK / "runs" / "faz12" / "coklu-test"
SONUCLAR = KOK / "runs" / "faz12"
PREMIUM = frozenset({"turev_basis", "turev_funding_basis"})


def _aile(cekilis: str) -> tuple[bool, bool, bool]:
    program = cekilis_programi(cekilis)
    return (program == "turev_evren", cekilis in PREMIUM, program == "makro_rejim")


def _uygunluk():
    asgari = next(e for e in kapilar_mod.ESIKLER if e.ad == "asgari_islem")
    azami_dd = next(e for e in kapilar_mod.ESIKLER if e.ad == "max_drawdown")
    return lambda islem, dd: bool(asgari.gecti_mi(islem)) and bool(azami_dd.gecti_mi(dd))


def _dosya(kimlik: str) -> Path:
    return CIKTI / f"{kimlik}.json"


def _hazir(kimlik: str, deneme: int, seed: int) -> list | None:
    yol = _dosya(kimlik)
    if not yol.exists():
        return None
    d = json.loads(yol.read_text(encoding="utf-8"))
    # K-064 öncesi (sızıntı paysız) satırlar yeniden kullanılmaz.
    if d["deneme"] != deneme or d["seed"] != seed or "sizinti_bar" not in d:
        return None
    return d


def _yaz(kimlik: str, govde: dict) -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    _dosya(kimlik).write_text(json.dumps(govde, ensure_ascii=False), encoding="utf-8")


def tek_sembollu(deneme: int, seed: int) -> None:
    cekilisler, ayar, diziler_ob, atlanan, _ = _coklu_test_cekilisleri(
        KOK / "data" / "market", deney_mod.VARSAYILAN_KOK
    )
    uygun_mu = _uygunluk()
    oranlar = cte.oranlar(deneme, seed)
    for c in cekilisler:
        if _hazir(c.kimlik, deneme, seed):
            continue
        a = ayar[c.kimlik]
        satirlar = []
        for oran in oranlar:
            # K-064: sinyali ısınma kadar öne alan kaydırma bölgesi dışarıda.
            k = 1 + int(oran * (c.takvim_bar - 2 - c.isinma_bar))
            r = tarama_mod.kosu(
                coklu_mod.BetikStrateji(coklu_mod.kaydir(c.takvim, k, c.takvim_bar),
                                        isinma=c.isinma_bar),
                a["maliyet"], "BTCUSDT", c.timeframe, diziler_ob[c.timeframe], a["pencere"],
                baslangic_sermaye=a["sermaye"], veri_sha256=c.veri_sha256,
            )
            islem = len([i for i in r.islemler if i.kapali])
            satirlar.append((float(r.metrikler.sharpe), uygun_mu(islem, r.metrikler.max_drawdown)))
        _yaz(c.kimlik, {"tur": "tek", "strateji": c.strateji, "timeframe": c.timeframe,
                        "gercek_sharpe": c.gercek_sharpe, "deneme": deneme, "seed": seed,
                        "sizinti_bar": c.isinma_bar, "satirlar": satirlar})
        print(f"tek   {c.strateji:<16} {c.timeframe:<3} tamam", flush=True)
    print(f"tek sembollü: ölçülebilir {len(cekilisler)}, atlanan {len(atlanan)}", flush=True)


def evren(deneme: int, seed: int) -> None:
    defter = {h["kimlik"]: h for h in hipotez_mod.HipotezDefteri().tumu()}
    uygun_mu = _uygunluk()
    oranlar = cte.oranlar(deneme, seed)
    maliyet = maliyet_mod.yukle()
    isler: dict[tuple[bool, bool, bool], list[tuple[str, dict]]] = {}
    for adlar in PROGRAM_CEKILISLERI.values():
        for ad in adlar:
            yol = SONUCLAR / f"{ad}.json"
            if not yol.exists():
                continue  # koşulmamış (harcanmamış) çekiliş
            kayit = json.loads(yol.read_text(encoding="utf-8"))
            if kayit["hipotez"]["kimlik"] not in defter:
                raise SystemExit(f"{ad}: sonuç kaydı defterde yok — ölçüm durdu")
            if _hazir(kayit["hipotez"]["kimlik"], deneme, seed):
                continue
            isler.setdefault(_aile(ad), []).append((ad, kayit))
    for (funding, premium, makro), liste in isler.items():
        basladi = time.perf_counter()
        veri = evren_kosu.veri_kur(
            TABLO, depo_kok=KOK / "data" / "evren", azami_sembol=600,
            funding_depo=KOK / "data" / "turev" / "funding" if funding else None,
            premium_depo=KOK / "data" / "turev" / "premium" if premium else None,
            makro_depo=KOK / "data" / "makro" if makro else None,
        )
        _, oos, _, _ = ed.pencereler(veri)
        for ad, kayit in liste:
            sonuc = kayit["sonuc"]
            strateji = kayit["sonuc"]["strateji"]
            c = cte.EvrenCekilisi(
                kimlik=kayit["hipotez"]["kimlik"], strateji=strateji,
                parametreler=sonuc["detay"]["secim"]["secilen"],
                gercek_sharpe=float(sonuc["olcumler"]["oos_sharpe"]),
                gercek_sonuc_hash=sonuc["detay"]["oos"]["sonuc_hash"],
                sifira_yaz_bar=sonuc.get("sifira_yaz_bar"),
            )
            t0 = time.perf_counter()

            def ilerleme(j: int, ad=ad, t0=t0) -> None:
                if (j + 1) % 10 == 0:
                    print(f"  {ad}: {j + 1}/{deneme} ({time.perf_counter() - t0:.0f} s)",
                          flush=True)

            sinif = EVREN_AILELER[strateji]
            sizinti = (sinif(**c.parametreler).isinma_bar()
                       + int(c.parametreler["yeniden_dengele_bar"]))
            c = cte.cekilis_null(c, sinif, veri, maliyet, oos, oranlar, uygun_mu,
                                 sizinti_bar=sizinti, ilerleme=ilerleme)
            _yaz(c.kimlik, {"tur": "evren", "cekilis": ad, "strateji": strateji,
                            "gercek_sharpe": c.gercek_sharpe, "deneme": deneme, "seed": seed,
                            "sizinti_bar": sizinti,
                            "satirlar": c.satirlar, "ozet": c.sozluk()})
            print(f"evren {ad:<24} tamam ({time.perf_counter() - t0:.0f} s)", flush=True)
        del veri
        gc.collect()
        pa.default_memory_pool().release_unused()
        print(f"aile bitti ({time.perf_counter() - basladi:.0f} s)", flush=True)


def birlestir(deneme: int, seed: int) -> int:
    satirlar, gercek, tur = {}, {}, {}
    for yol in sorted(CIKTI.glob("*.json")):
        d = json.loads(yol.read_text(encoding="utf-8"))
        if d["deneme"] != deneme or d["seed"] != seed or "sizinti_bar" not in d:
            continue
        satirlar[yol.stem] = [tuple(x) for x in d["satirlar"]]
        gercek[yol.stem] = (d["strateji"], d["gercek_sharpe"])
        tur[yol.stem] = d["tur"]
    defter = hipotez_mod.HipotezDefteri().sayi()
    null = cte.birlesik_null(satirlar, gercek, seed=seed)
    sharpe_kapisi = next(e for e in kapilar_mod.ESIKLER if e.ad == "oos_sharpe")
    oranlar = (0.20, 0.10, 0.05, 0.01)
    govde = {
        "defter_sayisi": defter,
        "olculebilir": len(satirlar),
        "tek_sembollu": sum(1 for t in tur.values() if t == "tek"),
        "evren": sum(1 for t in tur.values() if t == "evren"),
        "mevcut_esik": sharpe_kapisi.sinir,
        "null": null.sozluk(),
        "duzeltilmis_esikler": {f"{o:.2f}": null.duzeltilmis_esik(o) for o in oranlar},
        "esik_guven_araliklari": {f"{o:.2f}": list(null.esik_guven_araligi(o)) for o in oranlar},
        "mevcut_esigin_yanlis_pozitifi": float((null.azami >= sharpe_kapisi.sinir).mean()),
        "git": git_durumu(KOK),
        "uretildi": utc_str(simdi_ms()),
    }
    yol = SONUCLAR / f"coklu-test-birlesik-{deneme}-{seed}.json"
    yol.write_text(json.dumps(govde, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: govde[k] for k in ("defter_sayisi", "olculebilir", "tek_sembollu",
                                            "evren", "mevcut_esik", "duzeltilmis_esikler",
                                            "esik_guven_araliklari",
                                            "mevcut_esigin_yanlis_pozitifi")},
                     ensure_ascii=False, indent=1))
    print(f"yazıldı: {yol}")
    return 0


def sonradan_sizintisiz(deneme: int, seed: int) -> int:
    """K-064 öncesi (sızıntı paysız) satırlardan sızıntısız eşiği **dışlayarak** üretir.

    İlk 500 iterasyonluk koşu `k ∈ [1, L−2]` ile yapıldı. Aynı oran dizisiyle her çekilişin
    kaydırması yeniden hesaplanır; `k > L−2−H` (sinyal öne alınmış) olan satır o iterasyonda
    uygun sayılmaz. Yeni koşunun (`k ∈ [1, L−2−H]`) tam karşılığı değil — dışlama, örneklemeyi
    daraltmak yerine koşullar — ama aynı soruya aynı satırlardan cevap verir ve 10 saatlik
    koşuyu tekrarlamadan sızıntının etkisini ölçer.
    """
    import numpy as np

    cekilisler, _, _, _, _ = _coklu_test_cekilisleri(
        KOK / "data" / "market", deney_mod.VARSAYILAN_KOK
    )
    lh = {c.kimlik: (c.takvim_bar, c.isinma_bar) for c in cekilisler}
    oranlar = cte.oranlar(deneme, seed)
    satirlar, gercek, tur = {}, {}, {}
    for yol in sorted(CIKTI.glob("*.json")):
        d = json.loads(yol.read_text(encoding="utf-8"))
        if d["deneme"] != deneme or d["seed"] != seed or "sizinti_bar" in d:
            continue
        if d["tur"] == "evren":
            kayit = json.loads((SONUCLAR / f"{d['cekilis']}.json").read_text(encoding="utf-8"))
            p = kayit["sonuc"]["detay"]["secim"]["secilen"]
            pen = kayit["sonuc"]["pencereler"]["out_of_sample"]
            sinif = EVREN_AILELER[kayit["sonuc"]["strateji"]]
            lh[yol.stem] = (pen["bitis"] - pen["isinma_baslangic"],
                            sinif(**p).isinma_bar() + int(p["yeniden_dengele_bar"]))
        uzunluk, h = lh[yol.stem]
        satir = []
        for oran, (sharpe, uygun) in zip(oranlar, d["satirlar"], strict=True):
            k = 1 + int(oran * (uzunluk - 2))
            satir.append((sharpe, bool(uygun) and k <= uzunluk - 2 - h))
        satirlar[yol.stem] = satir
        gercek[yol.stem] = (d.get("cekilis", d["strateji"]), d["gercek_sharpe"])
        tur[yol.stem] = d["tur"]
    govde: dict = {"deneme": deneme, "seed": seed, "yontem": "sonradan dışlama (K-064)"}
    for ad, sec in (("tek", "tek"), ("evren", "evren"), ("hepsi", None)):
        r = {k: v for k, v in satirlar.items() if sec is None or tur[k] == sec}
        null = cte.birlesik_null(r, {k: gercek[k] for k in r}, seed=seed)
        govde[ad] = {
            "cekilis": len(r),
            "uygun_iterasyon": int(null.azami.size),
            "p95": null.duzeltilmis_esik(0.05),
            "p95_ga90": list(null.esik_guven_araligi(0.05)),
            "p90": null.duzeltilmis_esik(0.10),
            "azami_p99": float(np.percentile(null.azami, 99)),
        }
    govde["git"] = git_durumu(KOK)
    yol = SONUCLAR / f"coklu-test-sizintisiz-{deneme}-{seed}.json"
    yol.write_text(json.dumps(govde, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(govde, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deneme", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--birlestir", action="store_true", help="Yalnızca birleştir.")
    ap.add_argument("--yalniz", choices=("tek", "evren"), default=None)
    ap.add_argument("--sonradan-sizintisiz", action="store_true",
                    help="K-064 öncesi satırlardan sızıntı bölgesini dışlayarak eşik.")
    a = ap.parse_args()
    if a.sonradan_sizintisiz:
        return sonradan_sizintisiz(a.deneme, a.seed)
    if not a.birlestir:
        if a.yalniz in (None, "tek"):
            tek_sembollu(a.deneme, a.seed)
        if a.yalniz in (None, "evren"):
            evren(a.deneme, a.seed)
    return birlestir(a.deneme, a.seed)


if __name__ == "__main__":
    sys.exit(main())
