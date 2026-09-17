"""Konumlanma serileri: açık pozisyon, hesap dengesi, taker akışı. (Faz 16, `konumlanma_evren`)

Kaynak `data.binance.vision futures/um/daily/metrics`, 5 dakikalık ızgara
(`tools/faz16_metrics_indir.py`). Program kaydı `docs/Arastirma-Programlari.jsonl`, kaynak
ölçüsü `runs/faz16/kaynak-olcumu-konumlanma.json`.

## PIT kuralı (K-052/15)

`create_time` gözlemin ait olduğu 5 dakikalık **dilimin başı**; değer dilim kapanmadan
bilinemez, dolayısıyla `available_time = create_time + 5 dk`. Bir bar açılışında `t`
görülebilen değer, `create_time + 5 dk ≤ t` olan **en son** gözlemdir. Eşitlik dahildir.

`BAYAT_MS`den uzun süredir gözlem yoksa değer `NaN`: perp'i durmuş ya da arşivde boşluk olan
bir sembolün son konumlanması sonsuza kadar taşınmaz (funding'deki `BAYAT_MS` ile aynı gerekçe).

## Alanlar

| Dizi | Kaynak sütun | Ne |
| --- | --- | --- |
| `acik_pozisyon` | `sum_open_interest` | Açık pozisyon, **sözleşme adedi** |
| `taker_oran` | `sum_taker_long_short_vol_ratio` | Agresif alım/satım hacim oranı |
| `buyuk_hesap_oran` | `sum_toptrader_long_short_ratio` | Büyük hesapların pozisyonunda long/short |
| `hesap_oran` | `count_long_short_ratio` | Bütün hesapların sayısında long/short |

**Açık pozisyon USD değeri bilerek yok:** değer = adet × fiyat, yani değişimi fiyat değişimini
mekanik olarak içerir (ölçüldü: getiriyle R² 0,62; adet üzerinden 0,11).
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

SUTUNLAR: Final[dict[str, str]] = {
    "acik_pozisyon": "sum_open_interest",
    "taker_oran": "sum_taker_long_short_vol_ratio",
    "buyuk_hesap_oran": "sum_toptrader_long_short_ratio",
    "hesap_oran": "count_long_short_ratio",
}

#: Gözlem dilimi: değer dilimin **sonunda** bilinir.
DILIM_MS: Final = 5 * 60_000

#: Son gözlemden bu kadar sonra seri bayat: değer `NaN`. Bir günlük boşluk, arşivde
#: kaydı duran bir sembolü işaretlemeye yeter (funding'in `BAYAT_MS`i ile aynı).
BAYAT_MS: Final = 24 * 3_600_000


class KonumlanmaHatasi(ValueError):
    """Konumlanma girdisi geçersiz."""


def evren_dizileri(zamanlar: np.ndarray, konum: pd.DataFrame) -> dict[str, np.ndarray]:
    """5 dakikalık gözlemleri ortak bar ızgarasına **nedensel** olarak oturtur.

    Her bar açılışı `t` için `create_time + 5 dk ≤ t` olan son gözlem; yoksa ya da gözlem
    `BAYAT_MS`den eskiyse `NaN`. Veri yoksa bütün diziler `NaN` — sembol dışlanmaz, bilgisiz
    kalır (`evren_funding` ile aynı kural).
    """
    zamanlar = np.asarray(zamanlar, dtype="int64")
    n = len(zamanlar)
    bos = {ad: np.full(n, np.nan) for ad in SUTUNLAR}
    if konum is None or konum.empty:
        return bos
    eksik = [s for s in ("create_time", *SUTUNLAR.values()) if s not in konum.columns]
    if eksik:
        raise KonumlanmaHatasi(f"konumlanma verisinde eksik sütun: {', '.join(eksik)}")

    df = konum.sort_values("create_time", kind="mergesort")
    gorulur = df["create_time"].to_numpy(dtype="int64") + DILIM_MS
    # `gorulur <= t` olan son gözlem.
    son = np.searchsorted(gorulur, zamanlar, side="right") - 1
    var = son >= 0
    taze = var & (zamanlar - gorulur[np.maximum(son, 0)] <= BAYAT_MS)

    cikti: dict[str, np.ndarray] = {}
    for ad, sutun in SUTUNLAR.items():
        kaynak = df[sutun].to_numpy(dtype="float64")
        dizi = np.full(n, np.nan)
        dizi[taze] = kaynak[son[taze]]
        cikti[ad] = dizi
    return cikti


__all__ = ["BAYAT_MS", "DILIM_MS", "SUTUNLAR", "KonumlanmaHatasi", "evren_dizileri"]
