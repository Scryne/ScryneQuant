"""Faz 12 evren çekilişleri: ön kayıt ve 11 kapılık değerlendirme. (K-039, K-051, K-058)

    python tools/faz12_evren_kos.py kaydet <cekilis> -g "<gerekçe>"
    python tools/faz12_evren_kos.py kos <cekilis> [--isci 3]
    python tools/faz12_evren_kos.py durum

`kaydet` hipotezi defterde **sonuç görülmeden** açar ve programın bütçesinden düşer.
`kos` yalnızca kayıtlı bir hipotezi koşturur; kaçış kapısı yok (`_defteri_zorla`nın
evren karşılığı). Hipotez nesnesi iki komutta da `evren_degerlendirme.hipotez_kur`dan
kurulur, yani kayıt ile koşu aynı kimliği görür.

Kıyas (`evren_esit_agirlik`, K-030) her koşuda aynı OOS penceresinde ve aynı iskeletle
(yeniden dengeleme, `hedef_brut`, yoğunluk 10) ölçülür: programın durma kuralı "OOS'ta
kıyasın Sharpe'ını geçmek" diyor ve o sayı sonuç dosyasında durmalı. Kıyas çekiliş değildir.

Havuz: her işçi veriyi kendisi yükler (≈2,5 GB). İşler bağımsız ve deterministik; sonuç
koşucudan bağımsızdır (`tests/unit/test_evren_degerlendirme.py`).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np

from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import git_durumu
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research import evren_kosu
from scryne_quant.research import hipotez as hipotez_mod
from scryne_quant.research import program as program_mod
from scryne_quant.research.izgaralar import (
    PROGRAM_CEKILISLERI,
    cekilis_programi,
    evren_cekilisi,
)
from scryne_quant.strategy.kutuphane import EVREN_AILELER, EvrenEsitAgirlik

KOK = Path(__file__).resolve().parent.parent
TABLO = KOK / "data" / "evren" / "_evren" / "27b7a16ed0ed.parquet"
DEPO = KOK / "data" / "evren"
CIKTI = KOK / "runs" / "faz12"
FUNDING_DEPO = KOK / "data" / "turev" / "funding"
PREMIUM_DEPO = KOK / "data" / "turev" / "premium"
MAKRO_DEPO = KOK / "data" / "makro"
#: Premium verisi yüklenen çekilişler (basis). Funding çekilişleri (43-44) premium'suz
#: kaydedildi; onların veri kimliği premium hash'ini içermez ve değişmemeli.
PREMIUM_CEKILISLERI = frozenset({"turev_basis", "turev_funding_basis"})
#: Konumlanma deposu (Faz 16, `tools/faz16_metrics_indir.py`).
KONUMLANMA_DEPO = KOK / "data" / "turev" / "metrics"
AZAMI_SEMBOL = 600
#: Kesitsel programın kıyası sabit yoğunlukla koşuldu (hipotez 39-42). Türev programında
#: kıyas **seçilen** yoğunlukla koşulur: filtre kıyasın üstüne tek bir dışlama, fark yalnız
#: ondan gelmeli.
KIYAS_YOGUNLUK = 10
#: `kurma_evren` programının portföy kodu. `TUREV_PORTFOY` ("EVREN_ESIT") olamaz: o kod
#: "kıyasın kurma yöntemi" demek ve bu programın çekilişlerinde tam olarak o değişiyor.
KURMA_PORTFOY = "EVREN_KURMA"
#: Program → (funding yüklenir mi, portföy kodu, kıyas yoğunluğu seçilenden mi)
PROGRAM_AYARI = {
    "kesitsel_fiyat": (False, ed.KESITSEL_PORTFOY, False),
    "turev_evren": (True, ed.TUREV_PORTFOY, True),
    "makro_rejim": (False, ed.TUREV_PORTFOY, True),
    # Faz 16: konumlanma dışlaması. Funding yüklenmez (skor konumlanmadan gelir), portföy ve
    # kıyas yoğunluğu türev programıyla aynı.
    "konumlanma_evren": (False, ed.TUREV_PORTFOY, True),
    # Faz 16: aynı seçim, farklı kurma. Ek veri yok. Portföy kodu ayrı (`EVREN_KURMA`):
    # bu programda değişen şey **portföy yöntemi**, ve K-051 yöntemi hipotez kimliğinin
    # parçası sayıyor. Kıyas seçilen yoğunlukla koşulur — fark yalnızca kurmadan gelmeli.
    "kurma_evren": (False, KURMA_PORTFOY, True),
    # R7 (K-108): portföy düzeyi kurma — aynı seçim, `KurmaAyarlari`/brüt değişiyor; kurma
    # programıyla aynı portföy kodu ve seçilen yoğunlukta kıyas.
    "portfoy_kurma": (False, KURMA_PORTFOY, True),
    # R7(2) (K-109): kesitsel düşük oynaklık — Faz 12 kesitsel programının iskeleti ve kıyas kalıbı
    # (sabit yoğunluk 10, K-072: kıyas ayarlanmaz).
    "kesit_oynaklik": (False, ed.KESITSEL_PORTFOY, False),
}
#: Ölçüm (24 GB makine): veri yüklü süreç ≈4,5 GB; tek koşunun tepesi in-sample +0,6 GB,
#: tam pencere +0,9 GB. Ana süreç + 3 işçi in-sample'da ≈20 GB; tam pencere 2 işçiyle.
#: 4 işçi (≈6,2 GB/süreç, düzeltmelerden önce) sistemin koşuyu iki kez öldürmesine yol açtı.
VARSAYILAN_ISCI = 3
BUYUK_IS_BAR = 60_000



def _veri_uretici(program: str, cekilis: str = ""):
    funding, _, _ = PROGRAM_AYARI[program]
    return partial(
        evren_kosu.veri_kur, TABLO, depo_kok=DEPO, azami_sembol=AZAMI_SEMBOL,
        funding_depo=FUNDING_DEPO if funding else None,
        premium_depo=PREMIUM_DEPO if cekilis in PREMIUM_CEKILISLERI else None,
        makro_depo=MAKRO_DEPO if program == "makro_rejim" else None,
        konumlanma_depo=KONUMLANMA_DEPO if program == "konumlanma_evren" else None,
    )


def _temiz(x: Any) -> Any:
    """JSON'a yazılabilir hâl: NaN/inf → None, numpy skalerleri → Python."""
    if isinstance(x, dict):
        return {str(k): _temiz(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_temiz(v) for v in x]
    if isinstance(x, np.ndarray):
        return _temiz(x.tolist())
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def _defter_sirasi(cekilis: str, veri: evren_kosu.EvrenVerisi) -> tuple[int | None, Any]:
    program = cekilis_programi(cekilis)
    hip = ed.hipotez_kur(
        cekilis, veri, program=program, gerekce="kimlik kontrolü için geçici nesne",
        portfoy=PROGRAM_AYARI[program][1],
    )
    return hipotez_mod.HipotezDefteri().sira(hip), hip


def kaydet(cekilis: str, gerekce: str) -> int:
    program = cekilis_programi(cekilis)
    veri = _veri_uretici(program, cekilis)()
    hip = ed.hipotez_kur(
        cekilis, veri, program=program, gerekce=gerekce, portfoy=PROGRAM_AYARI[program][1]
    )
    defter = hipotez_mod.HipotezDefteri()
    programlar = program_mod.ProgramDefteri()
    onceki = defter.sira(hip)
    sira = defter.kaydet(hip, programlar=None if onceki is not None else programlar)
    butce = programlar.butce(program, defter.tumu())
    print(("zaten kayıtlı" if onceki is not None else "kaydedildi") + f": {sira}. hipotez")
    print(f"kimlik : {hip.kimlik[:16]} · strateji {hip.strateji} · veri {hip.veri_sha256[:12]}")
    print(
        f"bütçe  : {program} {butce['harcanan']}/{butce['azami_cekilis']} "
        f"(kalan {butce['kalan']})"
    )
    return 0


def kos(cekilis: str, isci: int) -> int:
    strateji_adi, secenekler = evren_cekilisi(cekilis)
    sinif = EVREN_AILELER[strateji_adi]
    basladi = time.perf_counter()
    program = cekilis_programi(cekilis)
    uretici = _veri_uretici(program, cekilis)
    veri = uretici()
    sira, hip = _defter_sirasi(cekilis, veri)
    if sira is None:
        print(
            f"HATA: {cekilis} hipotez defterinde kayıtlı değil. Sonucu gördükten sonra "
            f"kaydetmek ön kayıt değildir (K-039). Önce: kaydet {cekilis} -g ...",
            file=sys.stderr,
        )
        return 2
    maliyet = maliyet_mod.yukle()

    def ilerleme(m: str) -> None:
        print(f"[{time.perf_counter() - basladi:7.0f} s] {m}", flush=True)

    ilerleme(f"veri hazır · {len(veri.diziler)} sembol · {len(veri):,} bar · hipotez {sira}")
    havuz = (
        ProcessPoolExecutor(max_workers=isci, initializer=ed.isci_baslat,
                            initargs=(uretici, maliyet))
        if isci > 1 else None
    )
    try:
        kosucu = (
            ed.havuz_kosucu(havuz, buyuk_is_bar=BUYUK_IS_BAR, buyuk_is_eszamanli=2)
            if havuz else None
        )
        sonuc = ed.degerlendir(
            sinif, secenekler, maliyet, veri,
            secim=ed.KESITSEL_SECIM, kosucu=kosucu, ilerleme=ilerleme,
        )
    finally:
        if havuz:
            havuz.shutdown()

    ilerleme("kıyas (OOS)")
    _, oos, _, _ = ed.pencereler(veri)
    tek = dict((a, d[0]) for a, d in secenekler.items() if len(d) == 1)
    secilen = sonuc["detay"]["secim"].get("secilen") or {}
    yogunluk = (
        int(secilen.get("azami_enstruman", tek.get("azami_enstruman", KIYAS_YOGUNLUK)))
        if PROGRAM_AYARI[program][2] else KIYAS_YOGUNLUK
    )
    kiyas = ed.kosu(
        EvrenEsitAgirlik(
            yeniden_dengele_bar=int(tek["yeniden_dengele_bar"]),
            azami_enstruman=yogunluk,
            azami_agirlik=float(tek["hedef_brut"]) / yogunluk,
            hedef_brut=float(tek["hedef_brut"]),
        ),
        maliyet, veri, oos,
    )
    oos_sharpe = sonuc["olcumler"].get("oos_sharpe")
    govde = {
        "cekilis": cekilis,
        "program": program,
        "hipotez": {"sira": sira, "kimlik": hip.kimlik, "veri_kimligi": hip.veri_sha256},
        "evren": veri.meta,
        "kiyas_oos": {
            "strateji": EvrenEsitAgirlik.ad,
            "parametreler": {
                "yeniden_dengele_bar": int(tek["yeniden_dengele_bar"]),
                "azami_enstruman": yogunluk,
                "hedef_brut": float(tek["hedef_brut"]),
            },
            "metrikler": kiyas.metrikler.sozluk(),
            "sonuc_hash": kiyas.sonuc_hash,
        },
        "durma_kurali_olcumu": {
            "oos_sharpe": oos_sharpe,
            "kiyas_oos_sharpe": kiyas.metrikler.sharpe,
            "kiyasi_gecti": (oos_sharpe is not None and math.isfinite(oos_sharpe)
                             and oos_sharpe > kiyas.metrikler.sharpe),
        },
        "sonuc": sonuc,
        "git": git_durumu(KOK),
        "sure_sn": round(time.perf_counter() - basladi, 1),
        "zaman_utc": utc_str(simdi_ms()),
    }
    CIKTI.mkdir(parents=True, exist_ok=True)
    yol = CIKTI / f"{cekilis}.json"
    yol.write_text(json.dumps(_temiz(govde), ensure_ascii=False, indent=1), encoding="utf-8")

    k = sonuc["kapilar"]
    ilerleme(f"yazıldı: {yol}")
    print(json.dumps(_temiz({"olcumler": sonuc["olcumler"], "durma": govde["durma_kurali_olcumu"]}),
                     ensure_ascii=False, indent=1))
    print(json.dumps(_temiz(k), ensure_ascii=False, indent=1)[:4000])
    return 0


def durum() -> int:
    defter = hipotez_mod.HipotezDefteri()
    programlar = program_mod.ProgramDefteri()
    print(f"defter {defter.sayi()}")
    for program, adlar in PROGRAM_CEKILISLERI.items():
        acik = programlar.acik(program)
        if acik is None:
            print(f"{program}: kapalı")
        else:
            b = programlar.butce(program, defter.tumu())
            print(f"{program}: {b['harcanan']}/{b['azami_cekilis']}")
        for ad in adlar:
            _durum_satiri(ad)
    return 0


def _durum_satiri(ad: str) -> None:
    yol = CIKTI / f"{ad}.json"
    if not yol.exists():
        print(f"  {ad:36s} sonuç yok")
        return
    d = json.loads(yol.read_text(encoding="utf-8"))["durma_kurali_olcumu"]
    print(f"  {ad:36s} oos {d['oos_sharpe']} · kıyas {d['kiyas_oos_sharpe']:.3f} · "
          f"geçti={d['kiyasi_gecti']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    alt = ap.add_subparsers(dest="komut", required=True)
    k = alt.add_parser("kaydet")
    hepsi = [a for adlar in PROGRAM_CEKILISLERI.values() for a in adlar]
    k.add_argument("cekilis", choices=hepsi)
    k.add_argument("-g", "--gerekce", required=True)
    r = alt.add_parser("kos")
    r.add_argument("cekilis", choices=hepsi)
    r.add_argument("--isci", type=int, default=VARSAYILAN_ISCI)
    alt.add_parser("durum")
    a = ap.parse_args()
    if a.komut == "kaydet":
        return kaydet(a.cekilis, a.gerekce)
    if a.komut == "kos":
        return kos(a.cekilis, a.isci)
    return durum()


if __name__ == "__main__":
    raise SystemExit(main())
