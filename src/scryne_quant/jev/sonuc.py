"""Karar → ileri sonuç bağlama ve önceden tanımlı ölçütlerle değerlendirme. (K-074/7, §35, §42-44)

Sonuç tanımları **koddan önce** `config/jev.json::sonuc`ta sabitlendi; bu modül onları uygular,
seçmez:

- giriş `open[t+1]` (K-004: karar barının kapanışından değil, sonraki barın açılışından),
- ufuklar `ufuk_bar` (1/4/24), `getiri_h = close[t+h] / giris − 1`,
- `mae_h = min(low[t+1..t+h]) / giris − 1`, `mfe_h = max(high[t+1..t+h]) / giris − 1`,
- maliyet: gidiş-dönüş (`MaliyetModeli.gidis_donus_bps`, K-007), net getiri yöne göre işaretli,
- yön isabeti yalnızca `long`/`short` kararlarda; `flat` çekimserliktir, isabete girmez,
- güven kovaları `kalibrasyon_kovalari`; Brier ve ECE "güven = isabet olasılığı" varsayımını
  **sınar**, kabul etmez (spec §21: confidence ≠ probability).

**Gelecek burada var, kararda yok.** Bu modül `t+h` barını okur; okuduğu şey karar üretildikten
**sonra** oluşmuş veridir ve karar kaydına geri yazılmaz (kararlar defterde değişmez, bağlama
ayrı bir çerçevedir). Spec §36'nın "outcome hesaplanırken gelecek decision input'una sızmaz"
kuralı yapısal olarak sağlanıyor: iki ayrı nesne, tek yönlü akış.

**Kıyas** (K-030): her tabloda `al_tut` — aynı barlarda her zaman `long` — yer alır. Jev'in
isabeti tek başına bir sayı değil, aynı örneklemde kıyasın isabetiyle yan yana bir sayıdır.

**Kanıt sınıfı.** `leak_riski=true` satır içeren her değerlendirme `kanit: false` taşır ve
raporun başlığında görünür (K-074/3). Bu modül "Jev çalışıyor" demez; sayıları ve örneklem
büyüklüğünü verir, yorumu K-074/7'ye bırakır.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.common.zaman import timeframe_ms, utc_str
from scryne_quant.jev.ayarlar import JevAyarlari
from scryne_quant.jev.durum import KARAR_TF


class SonucHatasi(ValueError):
    """Bağlama ya da değerlendirme girdisi geçersiz."""


# ------------------------------------------------------------------ bağlama


def _bar_indeksi(barlar: pd.DataFrame) -> tuple[np.ndarray, dict[int, int]]:
    zaman = barlar["open_time"].to_numpy(dtype=np.int64)
    if zaman.size and np.any(np.diff(zaman) <= 0):
        raise SonucHatasi("bar çerçevesi open_time'a göre artan ve tekil olmalı")
    return zaman, {int(t): i for i, t in enumerate(zaman)}


def sonuclari_bagla(
    kararlar: pd.DataFrame,
    barlar: pd.DataFrame,
    *,
    ayarlar: JevAyarlari,
    maliyet: MaliyetModeli,
) -> pd.DataFrame:
    """Her karar satırına ufuk başına getiri/MAE/MFE ve maliyet sonrası net getiri ekler.

    `t+1..t+h` barları eksikse (henüz oluşmadı ya da seride boşluk var) alanlar `NaN` kalır:
    henüz bilinmeyen bir sonuç uydurulmaz (K-024). Kararlar değiştirilmez; yeni sütunlar
    eklenmiş bir **kopya** döner.
    """
    gerekli = {"karar_ms", "durum_kodu", "yon"}
    if eksik := gerekli - set(kararlar.columns):
        raise SonucHatasi(f"karar çerçevesinde eksik sütun(lar): {', '.join(sorted(eksik))}")
    adim = timeframe_ms(KARAR_TF)
    zaman, konum = _bar_indeksi(barlar)
    acilis = barlar["open"].to_numpy(dtype=np.float64)
    kapanis = barlar["close"].to_numpy(dtype=np.float64)
    yuksek = barlar["high"].to_numpy(dtype=np.float64)
    dusuk = barlar["low"].to_numpy(dtype=np.float64)
    maliyet_gd = maliyet.gidis_donus_bps / 10_000.0

    out = kararlar.copy().reset_index(drop=True)
    n = len(out)
    giris = np.full(n, np.nan)
    sutunlar: dict[str, np.ndarray] = {}
    for h in ayarlar.ufuk_bar:
        for ad in ("getiri", "mae", "mfe", "net"):
            sutunlar[f"{ad}_{h}"] = np.full(n, np.nan)

    for r, t in enumerate(out["karar_ms"].to_numpy(dtype=np.int64)):
        i = konum.get(int(t))
        if i is None or i + 1 >= zaman.size or zaman[i + 1] != t + adim:
            continue
        g = acilis[i + 1]
        if not (g > 0):
            continue
        giris[r] = g
        yon = out.at[r, "yon"]
        isaret = 1.0 if yon == "long" else -1.0 if yon == "short" else 0.0
        for h in ayarlar.ufuk_bar:
            j = i + h
            if j >= zaman.size or zaman[j] != t + h * adim:
                continue
            getiri = kapanis[j] / g - 1.0
            sutunlar[f"getiri_{h}"][r] = getiri
            sutunlar[f"mae_{h}"][r] = dusuk[i + 1 : j + 1].min() / g - 1.0
            sutunlar[f"mfe_{h}"][r] = yuksek[i + 1 : j + 1].max() / g - 1.0
            # flat: işlem yok, maliyet yok, net 0. Yönlü: yön × getiri − gidiş-dönüş maliyet.
            sutunlar[f"net_{h}"][r] = 0.0 if isaret == 0.0 else isaret * getiri - maliyet_gd
    out["giris"] = giris
    for ad, dizi in sutunlar.items():
        out[ad] = dizi
    return out


# ------------------------------------------------------------------ istatistik


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None, float | None]:
    """Oran ve Wilson %95 aralığı. `n = 0` → hepsi `None`; sıfır örneklem sayı üretmez."""
    if n <= 0:
        return None, None, None
    p = k / n
    payda = 1 + z * z / n
    merkez = (p + z * z / (2 * n)) / payda
    yari = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / payda
    return p, max(0.0, merkez - yari), min(1.0, merkez + yari)


def _isabet(yon: pd.Series, getiri: pd.Series) -> pd.Series:
    """Yönlü kararda isabet: long ve getiri > 0, ya da short ve getiri < 0. Sıfır getiri = ıska."""
    return ((yon == "long") & (getiri > 0)) | ((yon == "short") & (getiri < 0))


def _oran_blogu(isabet: pd.Series) -> dict[str, Any]:
    k, n = int(isabet.sum()), int(len(isabet))
    p, alt, ust = wilson(k, n)
    return {"n": n, "isabet": k, "oran": p, "ci95": None if p is None else [alt, ust]}


def kalibrasyon(guven: pd.Series, isabet: pd.Series, kovalar: Sequence[float]) -> dict[str, Any]:
    """Güven kovaları: kova başına ortalama güven vs gerçekleşen isabet; Brier ve ECE.

    "Güven = isabet olasılığı" **hipotezi** sınanıyor. Brier `mean((g − y)²)`; ECE kova
    ağırlıklı `|ort_güven − isabet|`. Boş kovalar raporda `n=0` ile durur, atlanmaz.
    """
    g = guven.to_numpy(dtype=np.float64)
    y = isabet.to_numpy(dtype=np.float64)
    n = int(g.size)
    satirlar: list[dict[str, Any]] = []
    ece = 0.0
    for lo, hi in zip(kovalar[:-1], kovalar[1:], strict=True):
        son = hi == kovalar[-1]
        m = (g >= lo) & ((g <= hi) if son else (g < hi))
        k = int(m.sum())
        if k:
            ort_g, ort_y = float(g[m].mean()), float(y[m].mean())
            ece += k / n * abs(ort_g - ort_y)
        else:
            ort_g = ort_y = None
        satirlar.append({"kova": [lo, hi], "n": k, "ort_guven": ort_g, "isabet_orani": ort_y})
    return {
        "n": n,
        "brier": None if n == 0 else float(np.mean((g - y) ** 2)),
        "ece": None if n == 0 else float(ece),
        "kovalar": satirlar,
    }


def _yuzdelik(x: pd.Series, q: float) -> float | None:
    x = x.dropna()
    return None if x.empty else float(np.percentile(x.to_numpy(dtype=np.float64), q))


def _ortalama(x: pd.Series) -> float | None:
    x = x.dropna()
    return None if x.empty else float(x.mean())


# ------------------------------------------------------------------ değerlendirme


def degerlendir(bagli: pd.DataFrame, *, ayarlar: JevAyarlari) -> dict[str, Any]:
    """Önceden tanımlı ölçütlerle rapor sözlüğü. Yorum yapmaz; sayı ve örneklem verir."""
    h = ayarlar.birincil_ufuk_bar
    g = f"getiri_{h}"
    if g not in bagli.columns:
        raise SonucHatasi(f"bağlanmış çerçevede {g} yok; önce `sonuclari_bagla`")
    toplam = int(len(bagli))
    gecerli = bagli[bagli["durum_kodu"] == "gecerli"]
    sayim = bagli["durum_kodu"].value_counts().to_dict()
    hata = toplam - int(len(gecerli))

    # Sonucu bilinen geçerli kararlar (ufuk barları oluşmuş)
    bilinen = gecerli[gecerli[g].notna()]
    yonlu = bilinen[bilinen["yon"].isin(["long", "short"])]
    isabet = _isabet(yonlu["yon"], yonlu[g])
    al_tut = bilinen[g] > 0  # aynı barlarda her zaman long

    rapor: dict[str, Any] = {
        "kanit": bool(len(gecerli))
        and not bool(gecerli.get("leak_riski", pd.Series(dtype=bool)).any()),
        "kanit_notu": (
            "leak_riski=true satır var: bu rapor boru hattı doğrulamasıdır, isabet kanıtı değil "
            "(K-074/3)"
            if len(gecerli) and bool(gecerli.get("leak_riski", pd.Series(dtype=bool)).any())
            else "yalnızca ileriye dönük kararlar; yine de örneklem büyüklüğüne bak (K-074/7)"
        ),
        "birincil_ufuk_bar": h,
        "toplam_kayit": toplam,
        "sayim": {str(k): int(v) for k, v in sayim.items()},
        "hata_orani": None if toplam == 0 else hata / toplam,
        "gecerli": int(len(gecerli)),
        "cekimserlik_orani": None
        if len(gecerli) == 0
        else float((gecerli["yon"] == "flat").mean()),
        "yon_dagilimi": {str(k): int(v) for k, v in gecerli["yon"].value_counts().items()},
        "rejim_dagilimi": {str(k): int(v) for k, v in gecerli["rejim"].value_counts().items()}
        if "rejim" in gecerli.columns
        else {},
        "sonucu_bilinen": int(len(bilinen)),
        "yonlu": int(len(yonlu)),
        "yon_isabeti": _oran_blogu(isabet),
        "kiyas_al_tut": _oran_blogu(al_tut),
        "ortalama_getiri": {
            f"jev_yonlu_net_{h}": _ortalama(yonlu[f"net_{h}"]),
            f"jev_yonlu_brut_{h}": _ortalama(
                yonlu[g] * np.where(yonlu["yon"] == "long", 1.0, -1.0)
            ),
            f"al_tut_brut_{h}": _ortalama(bilinen[g]),
            **{
                f"jev_yonlu_net_{u}": _ortalama(yonlu[f"net_{u}"])
                for u in ayarlar.ufuk_bar
                if u != h and f"net_{u}" in yonlu.columns
            },
        },
        "mae_mfe": {
            f"mae_{h}_ort": _ortalama(yonlu[f"mae_{h}"]),
            f"mfe_{h}_ort": _ortalama(yonlu[f"mfe_{h}"]),
            f"mae_{h}_p95_kotu": _yuzdelik(yonlu[f"mae_{h}"], 5),
        },
        "gecikme_ms": {
            "p50": _yuzdelik(gecerli["gecikme_ms"], 50) if "gecikme_ms" in gecerli else None,
            "p95": _yuzdelik(gecerli["gecikme_ms"], 95) if "gecikme_ms" in gecerli else None,
            "p99": _yuzdelik(gecerli["gecikme_ms"], 99) if "gecikme_ms" in gecerli else None,
        },
        "kalibrasyon": kalibrasyon(
            yonlu["yon_guven"] if "yon_guven" in yonlu else pd.Series(dtype=float),
            isabet,
            ayarlar.kalibrasyon_kovalari,
        ),
        "rejim_basina": _rejim_basina(bilinen, g, h),
        "kapsam": {
            "ilk_karar_utc": utc_str(int(bagli["karar_ms"].min())) if toplam else None,
            "son_karar_utc": utc_str(int(bagli["karar_ms"].max())) if toplam else None,
        },
    }
    return rapor


def _rejim_basina(bilinen: pd.DataFrame, g: str, h: int) -> dict[str, Any]:
    if "rejim" not in bilinen.columns or bilinen.empty:
        return {}
    out: dict[str, Any] = {}
    for rejim, grup in bilinen.groupby("rejim"):
        yonlu = grup[grup["yon"].isin(["long", "short"])]
        out[str(rejim)] = {
            "n": int(len(grup)),
            "yonlu": int(len(yonlu)),
            "isabet": _oran_blogu(_isabet(yonlu["yon"], yonlu[g])),
            f"net_{h}_ort": _ortalama(yonlu[f"net_{h}"]),
            f"al_tut_brut_{h}": _ortalama(grup[g]),
        }
    return out


def defterden_cerceve(satirlar: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """`JevDefteri.kararlar()` çıktısını değerlendirme çerçevesine çevirir."""
    kayitlar = []
    for s in satirlar:
        k = dict(s["karar"])
        k["durum_kodu"] = k.pop("durum")
        kayitlar.append(k)
    if not kayitlar:
        return pd.DataFrame(columns=["karar_ms", "durum_kodu", "yon"])
    return pd.DataFrame(kayitlar).sort_values(["karar_ms", "uretim_ms"]).reset_index(drop=True)


__all__ = [
    "SonucHatasi",
    "defterden_cerceve",
    "degerlendir",
    "kalibrasyon",
    "sonuclari_bagla",
    "wilson",
]
