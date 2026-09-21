"""FX PIT evren tablosu ve hayatta kalma yanlılığı ölçümü. (K-052, K-088, K-089; R3 Paket 1(e))

**Kural (K-051/4 kalıbı, içerik hash'li):** bir çift `w` haftasında evren üyesidir ⇔
(1) sözleşmede (`FXCM_CIFTLER`, `fxcm-candledata-m1`), (2) o haftanın M1 dosyası sağlayıcıda
**var** (kesif/HEAD ya da indirilmiş manifesto), (3) hafta sağlayıcı kapsamında. Hacim yok
(FXCM volume vermiyor), o yüzden kripto evreninin `quote_volume` sıralaması burada yok; kural
"varlık" kuralıdır ve bunu adıyla söyler. Kalite bazlı eleme (`fx_kalite`) dosya indirilince
ayrı bir kural sürümü olarak eklenir — burada uydurulmaz.

**PIT (K-052/5):** haftalık dosya hafta bitince yayımlanır (ölçüldü: ~1-2 hafta gecikme); üyelik
`w` haftası için `w`nin dosyasına bakar, yani bar `t`de kullanılabilirlik `t`nin haftası
kapandıktan sonradır. Araştırma yolunda bu, `available_time = bar kapanışı` sözleşmesiyle uyumlu:
hafta içi bir bar, haftanın dosyası yayımlanmadan araştırmaya girmez — canlı yok (K-087/2).

**Kanıt kaynağı ikidir ve ayrılır:** `kesif.json` (HEAD, dosya indirilmedi) ve `1h.kaynak.json`
(indirilmiş, sha'lı). İkisi çelişirse (manifesto `var`, kesif `yok`) hata — kaynak sessizce
"düzeltilmez". Kanıtı olmayan `(çift, hafta)` **bilinmiyor**dur; `yok` değil. Tablo yalnız
kanıtı olan hücrelerden kurulur ve `kapsam` bunu raporlar: tam tablo için 21 çift × tüm haftalar
kanıt ister (HEAD taraması yeter, indirme gerekmez).

**Hayatta kalma yanlılığı (Spike 6 kalıbı):** "bugünkü listeden kurulan evren" = kanıtı olan
haftalarda **bugün** var olan çiftler; PIT evren = o hafta dosyası olan çiftler. Hafta başına
`|bugün \\ PIT| / |bugün|`; özet: medyan, maksimum, sıfır olmayan hafta sayısı. Sağlayıcının
**tüm çiftlerde** boş bıraktığı haftalar (2024 h35, h51-53, 2025 h2) evren yok demektir, hayatta
kalma olayı değil — `saglayici_boslugu` olarak ayrı sayılır.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

from scryne_quant.common.hash import nesne_hash
from scryne_quant.data import fx as fx_mod
from scryne_quant.data.kimlik import VENUE_FXCM_FX, kanonik_kimlik
from scryne_quant.data.takvim import TAKVIM_FX_5X24

EVREN_DIZINI: Final = "_evren"
TIP: Final = "cfd"


class FxEvrenHatasi(ValueError):
    """Kanıt çelişkisi, bilinmeyen çift ya da kural ihlali."""


@dataclass(frozen=True, slots=True)
class FxEvrenKurali:
    """Üyelik kuralı — tüm alanlar kimliğe girer (K-051/4)."""

    ciftler: tuple[str, ...] = fx_mod.FXCM_CIFTLER
    kaynak: str = "fxcm-candledata-m1"
    takvim: str = TAKVIM_FX_5X24
    kural: str = "dosya-var"
    """`dosya-var`: haftanın M1 dosyası sağlayıcıda var. Kalite eşiği ileride ayrı kural adı."""

    def __post_init__(self) -> None:
        bilinmeyen = sorted(set(self.ciftler) - set(fx_mod.FXCM_CIFTLER))
        if bilinmeyen:
            raise FxEvrenHatasi(f"sözleşme dışı çift: {bilinmeyen} (K-088)")
        if not self.ciftler:
            raise FxEvrenHatasi("çift listesi boş")

    def sozluk(self) -> dict[str, Any]:
        return {
            "ciftler": sorted(self.ciftler),
            "kaynak": self.kaynak,
            "takvim": self.takvim,
            "kural": self.kural,
        }

    @property
    def kimlik(self) -> str:
        return nesne_hash(self.sozluk())


# ------------------------------------------------------------------ kanıt toplama

Varlik = dict[str, dict[str, bool]]
"""çift → `"YYYY-W"` → var mı. Kanıtı olmayan hücre sözlükte **yok**."""


def kanit_topla(depo: fx_mod.FxDepo, ciftler: tuple[str, ...]) -> tuple[Varlik, dict[str, Any]]:
    """`_gelen/<PAIR>/kesif*.json` ve `<PAIR>/1h.kaynak.json`dan varlık matrisi; çelişki → hata."""
    varlik: Varlik = {}
    kaynaklar: dict[str, Any] = {}
    for pair in sorted(ciftler):
        hucre: dict[str, bool] = {}
        neden: dict[str, str] = {}
        gelen = depo.kok / fx_mod.GELEN_DIZINI / pair
        for yol in sorted(gelen.glob("kesif*.json")) if gelen.exists() else []:
            k = json.loads(yol.read_text(encoding="utf-8"))
            for hafta, h in k.get("haftalar", {}).items():
                _yaz(hucre, neden, pair, hafta, bool(h["var"]), f"kesif:{yol.name}")
        m = depo.manifesto(pair)
        if m is not None:
            for hafta, h in m.get("haftalar", {}).items():
                _yaz(hucre, neden, pair, hafta, h.get("durum") == "var", "manifesto")
        if hucre:
            varlik[pair] = hucre
            kaynaklar[pair] = {"hafta": len(hucre), "var": sum(hucre.values())}
    return varlik, kaynaklar


def _yaz(hucre: dict[str, bool], neden: dict[str, str], pair: str, hafta: str, var: bool,
         kaynak: str) -> None:
    if hafta in hucre and hucre[hafta] != var:
        raise FxEvrenHatasi(
            f"{pair} {hafta}: kanıt çelişkisi — {neden[hafta]} {'var' if hucre[hafta] else 'yok'}, "
            f"{kaynak} {'var' if var else 'yok'}"
        )
    hucre[hafta] = var
    neden[hafta] = kaynak


# ------------------------------------------------------------------ tablo


def _pazar(hafta: str) -> dt.date:
    """`"YYYY-W"` → haftanın Pazar'ı (`fx.hafta_no`'nun tersi, o yılın Pazar'ları taranarak)."""
    yil, w = (int(x) for x in hafta.split("-"))
    p = dt.date(yil, 1, 1)
    p -= dt.timedelta(days=(p.weekday() + 1) % 7)  # yılın ilk gününü içeren haftanın Pazar'ı
    if p.year < yil:
        p += dt.timedelta(days=7)  # 1 Ocak'ı içeren hafta önceki yılın anahtarıyla yazılır
    while True:
        y, ww = fx_mod.hafta_no(p)
        if (y, ww) == (yil, w):
            return p
        if y > yil or (y == yil and ww > w):
            raise FxEvrenHatasi(f"hafta anahtarı çözülemedi: {hafta}")
        p += dt.timedelta(days=7)


def pit_tablo(kural: FxEvrenKurali, varlik: Mapping[str, Mapping[str, bool]]) -> pd.DataFrame:
    """Kanıtı olan `(çift, hafta)` hücrelerinden üyelik tablosu.

    Sütunlar: `hafta`, `pazar`, `kanonik_id`, `sembol`, `uye` (bool), `kanit` (`var`/`yok`).
    Yalnız kanıtlı hücreler; sıralama deterministik (`hafta` → `sembol`).
    """
    satirlar: list[dict[str, Any]] = []
    for pair in sorted(kural.ciftler):
        for hafta, var in sorted(varlik.get(pair, {}).items(), key=lambda kv: _pazar(kv[0])):
            pazar = _pazar(hafta)
            satirlar.append(
                {
                    "hafta": hafta,
                    "pazar": pazar.isoformat(),
                    "kanonik_id": kanonik_kimlik(
                        VENUE_FXCM_FX, TIP, pair, fx_mod.KAYNAK_BASLANGIC.isoformat()
                    ),
                    "sembol": pair,
                    "uye": bool(var),
                    "kanit": "var" if var else "yok",
                }
            )
    sutunlar = ["hafta", "pazar", "kanonik_id", "sembol", "uye", "kanit"]
    if not satirlar:
        return pd.DataFrame(columns=sutunlar)
    df = pd.DataFrame(satirlar, columns=sutunlar)
    return df.sort_values(["pazar", "sembol"], kind="stable").reset_index(drop=True)


def tablo_hash(tablo: pd.DataFrame) -> str:
    return nesne_hash(
        {
            "sutunlar": list(tablo.columns),
            "satirlar": [
                [str(v) for v in satir] for satir in tablo.itertuples(index=False, name=None)
            ],
        }
    )


# ------------------------------------------------------------------ hayatta kalma


def hayatta_kalma(tablo: pd.DataFrame, kural: FxEvrenKurali) -> dict[str, Any]:
    """Spike 6 kalıbı: bugünkü liste (sözleşmedeki çiftler) vs PIT üyelik, hafta başına.

    Yalnız **tam kanıtlı** haftalar ölçülür: tüm çiftler için hücre var. Kısmi kanıtlı hafta
    ölçüme girmez ve `kismi_kanit_hafta` olarak sayılır — eksik kanıt "yok" sayılmaz.
    Hiçbir çiftin dosyası olmayan hafta `saglayici_boslugu` (evren yok, yanlılık değil).
    """
    bugun = set(kural.ciftler)
    haftalar: dict[str, dict[str, Any]] = {}
    kismi = 0
    boslugu: list[str] = []
    oranlar: list[float] = []
    for hafta, g in tablo.groupby("hafta", sort=False):
        if set(g["sembol"]) != bugun:
            kismi += 1
            continue
        pit = set(g.loc[g["uye"], "sembol"])
        if not pit:
            boslugu.append(hafta)
            continue
        eksik = sorted(bugun - pit)
        oran = len(eksik) / len(bugun)
        oranlar.append(oran)
        haftalar[hafta] = {"pazar": str(g["pazar"].iloc[0]), "pit_uye": len(pit),
                           "bugun_olup_pit_olmayan": eksik, "oran": oran}
    sirali = dict(sorted(haftalar.items(), key=lambda kv: kv[1]["pazar"]))
    dizi = np.array(oranlar, dtype="float64")
    return {
        "yontem": "hafta başına |bugünkü liste \\ PIT| / |bugünkü liste| (Spike 6 kalıbı)",
        "bugunku_liste": sorted(bugun),
        "olculen_hafta": len(sirali),
        "kismi_kanit_hafta": kismi,
        "saglayici_boslugu": sorted(boslugu, key=lambda h: _pazar(h)),
        "medyan": float(np.median(dizi)) if dizi.size else None,
        "azami": float(dizi.max()) if dizi.size else None,
        "sifir_olmayan_hafta": int((dizi > 0).sum()) if dizi.size else 0,
        "haftalar": {h: v for h, v in sirali.items() if v["oran"] > 0},
    }


# ------------------------------------------------------------------ kapsam / yazma


def kapsam(varlik: Mapping[str, Mapping[str, bool]], kural: FxEvrenKurali) -> dict[str, Any]:
    """Kanıtın kapsamı: hangi çiftlerde, kaç haftada kanıt var; tam tablo için ne eksik."""
    ciftler = sorted(kural.ciftler)
    haftalar: set[str] = set()
    for h in varlik.values():
        haftalar |= set(h)
    tam = [p for p in ciftler if set(varlik.get(p, {})) >= haftalar and haftalar]
    return {
        "cift": len(ciftler),
        "kanitli_cift": len([p for p in ciftler if varlik.get(p)]),
        "hafta": len(haftalar),
        "ilk_hafta": min(haftalar, key=_pazar) if haftalar else None,
        "son_hafta": max(haftalar, key=_pazar) if haftalar else None,
        "tam_kanitli_cift": tam,
        "durum": "tam" if len(tam) == len(ciftler) and haftalar else "kismi",
        "not": "tam tablo için her çift × her hafta kanıt (HEAD yeter; indirme gerekmez)",
    }


def evren_kur(depo: fx_mod.FxDepo, kural: FxEvrenKurali) -> dict[str, Any]:
    """Kanıt topla → tablo → hayatta kalma; `data/fx/_evren/<kural>.parquet + .json` yazar."""
    varlik, kaynaklar = kanit_topla(depo, kural.ciftler)
    tablo = pit_tablo(kural, varlik)
    hk = hayatta_kalma(tablo, kural)
    dizin = depo.kok / EVREN_DIZINI
    dizin.mkdir(parents=True, exist_ok=True)
    ad = kural.kimlik[:12]
    parquet = dizin / f"{ad}.parquet"
    if not tablo.empty:
        tablo.to_parquet(parquet, index=False)
    meta = {
        "kural": kural.sozluk(),
        "kural_kimlik": kural.kimlik,
        "tablo": str(parquet) if not tablo.empty else None,
        "tablo_hash": tablo_hash(tablo),
        "satir": int(len(tablo)),
        "uye_satir": int(tablo["uye"].sum()) if not tablo.empty else 0,
        "kanit_kaynaklari": kaynaklar,
        "kapsam": kapsam(varlik, kural),
        "hayatta_kalma": hk,
    }
    (dizin / f"{ad}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    return meta


__all__ = [
    "FxEvrenHatasi",
    "FxEvrenKurali",
    "evren_kur",
    "hayatta_kalma",
    "kanit_topla",
    "kapsam",
    "pit_tablo",
    "tablo_hash",
]
