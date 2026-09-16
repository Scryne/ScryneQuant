"""Çok sembollü veriyi ortak bar ızgarasına oturtma + PIT üyelik matrisi. (Faz 10)

`data/evren.py` **aylık** bir üyelik tablosu üretiyor; `strategy/evren.py` ise **bar
başına** bir üyelik dizisi istiyor. Bu modül aradaki çeviri, ve çevirinin iki kuralı var:

1. **Üyelik ayın tamamı boyunca sabittir.** M ayının üye listesi M−1'in verisiyle bir kez
   hesaplanır ve M boyunca değişmez. Ay içinde yeniden hesaplamak, listeyi gün içi hacimle
   güncellemek demek olurdu — ve o hacim, kararın verildiği anda henüz oluşmamıştır.
2. **Üyelik kanonik kimliğe bağlanır, ticker'a değil** (K-052/4). `LUNAUSDT`in 2022-05
   öncesi ve sonrası iki farklı varlıktır; ikincisinin evrene girişi, birincisinin
   hacmiyle olamaz. Bar başına kimlik, barın zamanının hangi geçerlilik aralığına
   düştüğüne bakılarak bulunur.

**Var olmayan bar NaN'la doldurulur, sıfırla değil.** Sıfır fiyat bir fiyattır: indikatör
onu hesaba katar, getiri −%100 çıkar, drawdown patlar. NaN "yok" demektir ve nedensel
indikatörlerin tamamı onu zaten yayıyor. Kalite bayrağı `listelenmedi` olduğu için motor o
barda ne karar veriyor ne dolduruyor (K-028'in doğal uzantısı).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

import numpy as np
import pandas as pd

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.kimlik import Enstruman
from scryne_quant.strategy.evren import LISTELENMEDI

#: Doldurma barında NaN alan alacak sütunlar. `trades` tamsayı olduğu için ayrı: NaN'a
#: çevirmek onu float yapar ve `ctx.bar("trades")` sözleşmesini sessizce değiştirirdi.
NAN_SUTUNLARI: Final[tuple[str, ...]] = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
)


class IzgaraHatasi(ValueError):
    """Izgaraya oturtma girdisi tutarsız."""


def ortak_izgara(zamanlar: Sequence[np.ndarray], timeframe: str) -> np.ndarray:
    """Tüm sembollerin zamanlarının birleşimi, ızgaraya hizalı ve artan.

    Birleşim (kesişim değil) seçildi: kesişim, en kısa geçmişli sembolün penceresine
    herkesi hapsederdi — yani evrenin tamamını en yeni üyesi kadar kısaltırdı.
    """
    adim = timeframe_ms(timeframe)
    if not zamanlar:
        raise IzgaraHatasi("en az bir zaman serisi gerekir")
    birlesim = np.unique(np.concatenate([np.asarray(z, dtype="int64") for z in zamanlar]))
    if birlesim.size == 0:
        raise IzgaraHatasi("boş zaman ızgarası")
    if (birlesim % adim != birlesim[0] % adim).any():
        raise IzgaraHatasi(
            f"ızgaraya oturmayan timestamp var (adım {adim} ms). Faz 9'da ölçülmüştü: "
            "2018-02 kesintisinden sonra bazı semboller ızgara dışına düşüyor (K-056)"
        )
    return birlesim


def hizala(df: pd.DataFrame, zamanlar: np.ndarray) -> dict[str, np.ndarray]:
    """Bir sembolün barlarını ortak ızgaraya oturtur; eksik barları `listelenmedi` doldurur.

    Dönen sözlük doğrudan `PiyasaGorunumu(barlar=...)`e verilebilir.
    """
    n = len(zamanlar)
    diziler: dict[str, np.ndarray] = {"open_time": np.asarray(zamanlar, dtype="int64")}
    for ad in NAN_SUTUNLARI:
        diziler[ad] = np.full(n, np.nan, dtype="float64")
    diziler["trades"] = np.zeros(n, dtype="int64")
    diziler["quality_status"] = np.full(n, LISTELENMEDI, dtype=object)

    if df.empty:
        return diziler

    kendi = df["open_time"].to_numpy(dtype="int64")
    idx = np.searchsorted(zamanlar, kendi)
    if (idx >= n).any() or not np.array_equal(np.asarray(zamanlar)[idx], kendi):
        raise IzgaraHatasi("sembolün barları ortak ızgarada yok — ızgara yanlış kurulmuş")

    for ad in NAN_SUTUNLARI:
        diziler[ad][idx] = df[ad].to_numpy(dtype="float64")
    diziler["trades"][idx] = df["trades"].to_numpy(dtype="int64")
    diziler["quality_status"][idx] = df["quality_status"].astype("string").to_numpy(dtype=object)
    return diziler


def _ay(ms: np.ndarray) -> np.ndarray:
    """Epoch ms → `YYYY-MM`. `data/evren.py`nin `_ay`ı ile aynı sözleşme."""
    return np.datetime_as_string(ms.astype("datetime64[ms]").astype("datetime64[M]"), unit="M")


def uyelik_matrisi(
    tablo: pd.DataFrame,
    zamanlar: np.ndarray,
    kimlikler: Mapping[str, Sequence[Enstruman]],
) -> dict[str, np.ndarray]:
    """Aylık PIT evren tablosunu bar başına üyelik dizilerine çevirir.

    `kimlikler`: sembol → o sembolün kanonik segmentleri (başlangıca göre sıralı,
    `data/kimlik.py:kimlikleri_kur` çıktısı). Bir barın kimliği, zamanının hangi segmente
    düştüğüyle bulunur; üyelik `(kanonik_id, ay)` çiftine bakar.

    Tabloda olmayan bir sembol için hep-`False` dizi döner — "tablo bilmiyorsa üye
    değildir". Ters varsayım (bilinmiyorsa üye) evren kuralını sessizce kaldırırdı.
    """
    zamanlar = np.asarray(zamanlar, dtype="int64")
    aylar = _ay(zamanlar)
    uyeler: set[tuple[str, str]] = set()
    if not tablo.empty:
        uyeler = {
            (str(k), str(a))
            for k, a in zip(tablo["kanonik_id"], tablo["ay"], strict=True)
        }

    cikti: dict[str, np.ndarray] = {}
    for sembol, segmentler in kimlikler.items():
        maske = np.zeros(len(zamanlar), dtype=bool)
        if segmentler:
            baslangiclar = np.array([s.gecerli_baslangic_ms for s in segmentler], dtype="int64")
            if (np.diff(baslangiclar) <= 0).any():
                raise IzgaraHatasi(f"{sembol}: kimlik segmentleri sıralı değil")
            idx = np.searchsorted(baslangiclar, zamanlar, side="right") - 1
            for i, (seg_idx, ay) in enumerate(zip(idx, aylar, strict=True)):
                if seg_idx < 0:
                    continue
                segment = segmentler[seg_idx]
                if not segment.gecerli_baslangic_ms <= zamanlar[i] < segment.gecerli_bitis_ms:
                    continue
                maske[i] = (segment.kanonik_id, str(ay)) in uyeler
        cikti[sembol] = maske
    return cikti


__all__ = [
    "NAN_SUTUNLARI",
    "IzgaraHatasi",
    "hizala",
    "ortak_izgara",
    "uyelik_matrisi",
]
