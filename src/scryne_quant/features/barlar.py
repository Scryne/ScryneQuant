"""Bar DataFrame'i → numpy dizileri. **Bu paketteki tek pandas kullanıcısı.**

Ayrı bir modülde duruyor çünkü pandas dosya okuyabilen bir kütüphanedir
(`read_parquet`, `read_csv`). Strateji katmanının import edebildiği bir modülde bulunması,
K-003'ün kapattığı I/O yüzeyini dolaylı yoldan geri açardı. İzolasyon testi bu modülü
strateji için **yasaklı** kabul eder: `features.indikator` ve `features.motor` serbest,
`features.barlar` değil.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scryne_quant.data.semalar import BAR_SUTUNLARI

#: Diziye çevrilirken float64'e zorlanan sütunlar.
SAYISAL: tuple[str, ...] = ("open", "high", "low", "close", "volume", "quote_volume")


class BarHatasi(ValueError):
    """Bar çerçevesi motorun beklediği biçimde değil."""


def bar_dizileri(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Kanonik bar çerçevesini salt-okunur numpy dizilerine çevirir.

    Diziler `writeable=False` işaretlenir: aynı diziler hem özellik hesabına hem `ctx`'e
    gidiyor, ve tek bir yerde yapılan yerinde değişiklik backtest'in her yerine sessizce
    yayılırdı.

    Sıra kontrol edilir, düzeltilmez. Sıralamayı burada sessizce onarmak, deponun
    kanonikleştirme sözleşmesini (bkz. `data/depo.py`) ikinci bir yere kopyalamak olurdu;
    bozuksa sebebi yukarıda aranmalı.
    """
    eksik = [s for s in BAR_SUTUNLARI if s not in df.columns]
    if eksik:
        raise BarHatasi(f"eksik sütun(lar): {', '.join(eksik)}")
    if df.empty:
        raise BarHatasi("boş bar çerçevesi")

    zaman = df["open_time"].to_numpy(dtype="int64")
    if np.any(np.diff(zaman) <= 0):
        raise BarHatasi("open_time artan ve tekil olmalı — depo dışından gelen veri mi?")

    out: dict[str, np.ndarray] = {"open_time": zaman}
    for sutun in SAYISAL:
        out[sutun] = df[sutun].to_numpy(dtype="float64")
    out["trades"] = df["trades"].to_numpy(dtype="int64")
    out["quality_status"] = df["quality_status"].astype("string").to_numpy(dtype=object)

    for dizi in out.values():
        dizi.flags.writeable = False
    return out
