"""`oos_sharpe` eşiğinin kalibre edildiği çekilişlerin OOS süresi: en kısası kaç gün? (K-113)

    uv run python tools/r5_oos_suresi_olcum.py [--deney-kok runs/deneyler]
        [--evren-kok runs/faz12] [--fx-kok runs/fx] [--cikti docs/research/records/…json]

`research/kapilar.COKLU_TEST_ESIGI` (1,04) bir null dağılımından ölçüldü (K-044/064/071/081) ve o
null, fotoğraftaki (`docs/research/coklu-test-olcum.json`) 48 çekilişin **kendi OOS pencerelerinde**
koşuldu. Sharpe kestiriminin sapması OOS uzunluğuyla daralır; eşik yalnız kalibre edildiği en kısa
OOS'tan uzun pencerelerde okunabilir. Bu araç o en kısa süreyi **kayıtlardan** okur (uydurmaz):

- tek sembollü çekilişler → `runs/deneyler/degerlendirme/*.json` `cikti.pencereler.out_of_sample`
  (eşleşme anahtarı `sq lab coklu-test` ile aynı: `(timeframe, secim, veri_sha256)`);
- evren çekilişleri → `runs/faz12/*.json` (`kimlik` eşleşir) `pencereler.out_of_sample`;
- fotoğrafın **ölçülemez** saydığı FX çekilişleri → `runs/fx/*.json`, yalnız rapor için (eşiğe
  girmezler; K-102/6).

Süre bar-zamanıdır (`bar × timeframe`), `Metrikler.yillik_anlamli` ile aynı ölçek
(`kapilar.oos_suresi_gun`). Çıktı `asgari_oos_gun` (en kısa OOS'un kendisi — yuvarlanmaz, çünkü
kalibrasyon kümesinin üyeleri kendi kapılarından tanım gereği geçmeli; 570'e yuvarlamak 1h tek
sembollü çekilişlerin tamamını eliyordu) taşır; `kapilar.ASGARI_OOS_GUN` ona eşit olmak zorunda
(`tests/unit/test_esikler.py`). Fotoğraf değişince yeniden koşulur.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from scryne_quant.common.hash import dosya_hash
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.research import coklu_test_fotograf as fotograf_mod
from scryne_quant.research import hipotez as hipotez_mod
from scryne_quant.research.kapilar import oos_suresi_gun

VARSAYILAN_CIKTI = Path("docs/research/records/2026-09-22-R5-oos-suresi.json")


def _oku(yol: Path) -> dict[str, Any]:
    return json.loads(yol.read_text(encoding="utf-8"))


def _bul(o: Any, anahtar: str) -> Any:
    """İlk `anahtar` eşleşmesini derinlemesine bulur (kayıt biçimleri arasında tek fark yuva)."""
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


def _satir(kimlik: str, kaynak: str, tf: str, oos: dict[str, Any], sinif: str) -> dict[str, Any]:
    bar = int(oos["bitis"]) - int(oos["baslangic"])
    return {
        "kimlik": kimlik,
        "sinif": sinif,
        "timeframe": tf,
        "oos_bar": bar,
        "oos_gun": oos_suresi_gun(bar, timeframe_ms(tf)),
        "kaynak": kaynak,
    }


def olc(
    deney_kok: Path,
    evren_kok: Path,
    fx_kok: Path,
    fotograf_yolu: Path = fotograf_mod.VARSAYILAN_YOL,
) -> dict[str, Any]:
    fotograf = fotograf_mod.oku(fotograf_yolu)
    defter = {h["kimlik"]: h for h in hipotez_mod.HipotezDefteri().tumu()}

    tek_indeks: dict[tuple[str, str, str], tuple[Path, dict[str, Any]]] = {}
    for yol in sorted(deney_kok.glob("degerlendirme/*.json")):
        kayit = _oku(yol)
        g = kayit["girdi"]
        tek_indeks[(g["timeframe"], g.get("secim", "tepe"), kayit["kimlik"]["veri_sha256"])] = (
            yol, kayit
        )
    kimlik_indeks: dict[str, tuple[Path, dict[str, Any]]] = {}
    for kok in (evren_kok, fx_kok):
        for yol in sorted(kok.glob("*.json")):
            try:
                kayit = _oku(yol)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            k = _bul(kayit, "kimlik")
            if isinstance(k, str) and _bul(kayit, "pencereler"):
                kimlik_indeks[k] = (yol, kayit)

    satirlar: list[dict[str, Any]] = []
    eksik: list[str] = []
    for kimlik in fotograf["cekilis_kimlikleri"]:
        h = defter.get(kimlik)
        if h is None:
            eksik.append(kimlik)
            continue
        if kimlik in kimlik_indeks:
            yol, kayit = kimlik_indeks[kimlik]
            p = _bul(kayit, "pencereler")
            tf = _bul(kayit, "timeframe") or h["timeframe"]
            satirlar.append(_satir(kimlik, str(yol), tf, p["out_of_sample"], "evren"))
            continue
        anahtar = (h["timeframe"], h["secim"], h["veri_sha256"])
        if anahtar in tek_indeks:
            yol, kayit = tek_indeks[anahtar]
            p = kayit["cikti"]["pencereler"]
            satirlar.append(
                _satir(kimlik, str(yol), h["timeframe"], p["out_of_sample"], "tek_sembollu")
            )
            continue
        eksik.append(kimlik)

    olculemez: list[dict[str, Any]] = []
    for kimlik in fotograf.get("olculemez_kimlikleri", []):
        if kimlik in kimlik_indeks:
            yol, kayit = kimlik_indeks[kimlik]
            p = _bul(kayit, "pencereler")
            tf = _bul(kayit, "timeframe") or defter.get(kimlik, {}).get("timeframe", "1h")
            olculemez.append(_satir(kimlik, str(yol), tf, p["out_of_sample"], "olculemez"))

    if eksik:
        raise SystemExit(
            f"{len(eksik)} fotoğraf çekilişinin OOS penceresi kayıtlarda bulunamadı: "
            f"{', '.join(k[:12] for k in eksik)} — sayı uydurulmaz, araç durur."
        )
    en_kisa = min(satirlar, key=lambda s: s["oos_gun"])
    return {
        "uretildi": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "fotograf": {
            "yol": str(fotograf_yolu),
            "sha256": dosya_hash(fotograf_yolu),
            "olculebilir": fotograf["olculebilir"],
            "defter_sayisi": fotograf["defter_sayisi"],
        },
        "cekilis_sayisi": len(satirlar),
        "asgari_oos_gun": en_kisa["oos_gun"],
        "asgari_oos_bar": en_kisa["oos_bar"],
        "asgari_oos_timeframe": en_kisa["timeframe"],
        "en_kisa": en_kisa,
        "dagilim": sorted(
            {(s["sinif"], s["timeframe"], s["oos_bar"], s["oos_gun"]) for s in satirlar}
        ),
        "cekilisler": satirlar,
        "olculemez_cekilisler": olculemez,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--deney-kok", type=Path, default=Path("runs/deneyler"))
    ap.add_argument("--evren-kok", type=Path, default=Path("runs/faz12"))
    ap.add_argument("--fx-kok", type=Path, default=Path("runs/fx"))
    ap.add_argument("--cikti", type=Path, default=VARSAYILAN_CIKTI)
    a = ap.parse_args()
    govde = olc(a.deney_kok, a.evren_kok, a.fx_kok)
    a.cikti.parent.mkdir(parents=True, exist_ok=True)
    a.cikti.write_text(json.dumps(govde, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    k = govde["en_kisa"]
    print(f"çekiliş {govde['cekilis_sayisi']} · en kısa OOS {govde['asgari_oos_gun']:.4f} gün "
          f"({k['sinif']} {k['timeframe']} {k['oos_bar']} bar) = ASGARI_OOS_GUN")
    for sinif, tf, bar, gun in govde["dagilim"]:
        print(f"  {sinif:<13} {tf:<3} {bar:>6} bar  {gun:>8.2f} gün")
    for s in govde["olculemez_cekilisler"]:
        print(f"  ölçülemez     {s['timeframe']:<3} {s['oos_bar']:>6} bar  "
              f"{s['oos_gun']:>8.2f} gün  {s['kimlik'][:12]}")
    print(f"kayıt : {a.cikti}")


if __name__ == "__main__":
    main()
