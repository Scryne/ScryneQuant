"""Makro seriler: ALFRED vintage'larından PIT günlük seri ve bar alanları. (Faz 12, K-052/5)

`makro_rejim` programı. Veri `tools/faz12_makro_indir.py` ile `data/makro/` altına iner:
her gözlemin **bütün vintage'ları** (`date`, `realtime_start`, `realtime_end`, `value`).

## PIT kuralı

- Bir vintage satırı `d` gününde görülebilir ⇔ `realtime_start ≤ d ≤ realtime_end`. `d`
  gününün sonunda bilinen değer, o gün görülebilen satırlar arasında **en geç gözlem
  tarihli** olanın değeridir. Revize edilen seride (NFCI) bu, o gün geçerli vintage'dır —
  bugünkü son değer değil.
- `realtime_start` gün çözünürlüğünde, saat bilgisi yok: değer **gün sonunda** bilinir
  sayılır ve `d` gününün değeri ancak `d+1` gününün 00:00 barından itibaren görünür
  (K-052/15: bilinmeyen saat gün sonuna yuvarlanır). Aynı gün içindeki bir bar onu görmez.
- Hafta sonu ve tatilde yeni gözlem yoktur; o günün değeri bilinen son gözlemdir (bir
  **bilgi** durumu, uydurma değil). İlk vintage'dan önce değer `NaN`.

## Neden persentil yükleyicide

Persentil pencereleri gün cinsinden ve seri gün çözünürlüğünde değişiyor. Bar başına kayan
persentil (8.760 barlık pencere × 79.420 bar × 429 sembol × koşu başına) bir çekilişi
günlere uzatırdı; günlük seride bir kez hesaplayıp bara yaymak aynı sayıyı verir, çünkü
gün içinde değer sabit. Pencereler bu yüzden **önceden sabit** (`PENCERELER_GUN`); ızgara
bu kümenin dışına çıkamaz.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from scryne_quant.features.indikator import persentil_sirasi

GUN_MS: Final = 86_400_000

#: Program kaydındaki seriler (K-051/2): kısa ad → FRED kimliği.
SERILER: Final[dict[str, str]] = {"vix": "VIXCLS", "nfci": "NFCI"}

#: Persentil pencereleri (gün). Izgara bu kümeden seçer.
PENCERELER_GUN: Final[tuple[int, ...]] = (30, 90, 180, 365)


class MakroHatasi(ValueError):
    """Makro veri girdisi geçersiz."""


def alan_adi(seri: str, pencere_gun: int) -> str:
    """Bar alanının adı, örn. `vix_p90`."""
    return f"{seri}_p{pencere_gun}"


def butun_alanlar() -> tuple[str, ...]:
    return tuple(alan_adi(s, w) for s in SERILER for w in PENCERELER_GUN)


def _gun(x: pd.Series) -> np.ndarray:
    # Çözünürlükten bağımsız gün sayısı: `astype(int64)` pandas'ın seçtiği birime bağlı.
    return ((pd.to_datetime(x) - pd.Timestamp("1970-01-01")) // pd.Timedelta(days=1)).to_numpy()


def pit_gunluk(vintage: pd.DataFrame, gunler: np.ndarray) -> np.ndarray:
    """Her `d` günü için gün sonunda **bilinen** en son gözlem değeri. (bkz. modül notu)"""
    df = vintage.dropna(subset=["value"])
    gunler = np.asarray(gunler, dtype="int64")
    out = np.full(gunler.size, np.nan)
    if df.empty:
        return out
    bas = _gun(df["realtime_start"])
    bit = _gun(df["realtime_end"].replace("9999-12-31", "2262-01-01"))
    gozlem = _gun(df["date"])
    deger = df["value"].to_numpy(dtype="float64")
    # Gözlem tarihine göre sırala: görünür satırlar arasında en geç gözlem son indekstir.
    sira = np.argsort(gozlem, kind="mergesort")
    bas, bit, gozlem, deger = bas[sira], bit[sira], gozlem[sira], deger[sira]
    for k, d in enumerate(gunler):
        gorunur = np.flatnonzero((bas <= d) & (bit >= d))
        if gorunur.size:
            out[k] = deger[gorunur[-1]]
    return out


def gunluk_gerekli(zamanlar: np.ndarray) -> np.ndarray:
    """Izgaranın alanlarını kurmak için PIT değeri gereken günler (epoch gün)."""
    bar_gunu = np.asarray(zamanlar, dtype="int64") // GUN_MS
    ilk, son = int(bar_gunu[0]) - 1, int(bar_gunu[-1])
    return np.arange(ilk - max(PENCERELER_GUN), son + 1, dtype="int64")


def gunlukten_alanlar(
    zamanlar: np.ndarray, gunluk: Mapping[str, Callable[[np.ndarray], np.ndarray]]
) -> dict[str, np.ndarray]:
    """Seri başına günlük PIT değer kaynağından bar alanları.

    `gunluk[kisa](gunler)` o günlerin gün sonunda bilinen değerini verir. Araştırma
    (`bar_alanlari`) vintage dosyasından `pit_gunluk` ile, canlı motor günü gününe saklanan
    değerlerden besler; persentil ve bara yayma **tek** yerde (K-001).
    """
    zamanlar = np.asarray(zamanlar, dtype="int64")
    if zamanlar.size == 0:
        raise MakroHatasi("boş ızgara")
    bar_gunu = zamanlar // GUN_MS
    gunler = gunluk_gerekli(zamanlar)
    alanlar: dict[str, np.ndarray] = {}
    for kisa, kaynak in gunluk.items():
        seri_gunluk = np.asarray(kaynak(gunler), dtype="float64")
        # `d` gününün değeri `d+1` gününün barlarında görünür.
        idx = bar_gunu - 1 - gunler[0]
        for w in PENCERELER_GUN:
            p = persentil_sirasi(seri_gunluk, w)
            dizi = p[idx]
            dizi.flags.writeable = False
            alanlar[alan_adi(kisa, w)] = dizi
    return alanlar


def bar_alanlari(zamanlar: np.ndarray, depo: str | Path) -> tuple[dict[str, np.ndarray], dict]:
    """Ortak ızgara için makro persentil alanları + kaynak bilgisi.

    Döner: `{alan_adi: dizi}` (bütün semboller **aynı** diziyi paylaşır) ve seri başına
    dosya yolu (hash çağıranda).
    """
    zamanlar = np.asarray(zamanlar, dtype="int64")
    if zamanlar.size == 0:
        raise MakroHatasi("boş ızgara")
    dosyalar: dict[str, Path] = {}
    kaynaklar: dict[str, Callable[[np.ndarray], np.ndarray]] = {}
    for kisa, sid in SERILER.items():
        yol = Path(depo) / f"{sid}.parquet"
        if not yol.is_file():
            raise MakroHatasi(f"makro verisi yok: {yol}")
        dosyalar[sid] = yol
        vintage = pd.read_parquet(yol)
        kaynaklar[kisa] = lambda gunler, v=vintage: pit_gunluk(v, gunler)
    return gunlukten_alanlar(zamanlar, kaynaklar), dosyalar


__all__ = [
    "GUN_MS",
    "PENCERELER_GUN",
    "SERILER",
    "MakroHatasi",
    "alan_adi",
    "bar_alanlari",
    "gunluk_gerekli",
    "gunlukten_alanlar",
    "butun_alanlar",
    "pit_gunluk",
]
