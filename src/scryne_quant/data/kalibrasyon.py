"""Slippage kalibrasyonu: yürütme penceresindeki fiyat hareketi. (K-021)

**Kapatılan karar:** K-021. `slippage_bps` tahmin edilmez, kullanılacak veri aralığı
üzerinde ölçülür.

**Neden bu büyüklük ölçülüyor.** Zincir üç ölçüme dayanıyor, hepsi Faz 0'dan:

1. Spike 4 spread'i **0,00128 bps** ölçtü, komisyonu **20 bps**. Spread bu projede bir
   maliyet kalemi değil — 15.600 kat küçük. Yani `slippage_bps` bir mikroyapı proxy'si
   olamaz.
2. K-020 bunun üzerine `|open[t+1] − close[t]|` dağılımını önerdi. Spike 2 onu da ölçtü:
   vakaların **%52,2'sinde iki fiyat birebir aynı**, p75 = 0,0014 bps. Kripto 7/24
   işliyor; `open[t+1]`, `close[t]`'in birkaç milisaniye sonrasıdır. Bu dağılım yürütme
   belirsizliğini değil iki komşu işlemin tick farkını ölçüyor — ve maliyeti fiilen
   sıfırlardı.
3. Geriye gerçek pencere kalıyor: **bar kapanışı ile emrin borsada dolması arası.** Spike
   1 bunun ağ ayağını ölçtü (p50 ~300 ms, kuyruk 1,6 s); üstüne emir işleme eklenir. Yani
   pencere saniye altı ile birkaç saniye arası.

Saniyelik bir pencerede fiyatın ne oynadığını 1h veriden görmek mümkün değil; en ince
elimizdeki ölçek **1 dakika**. Bu yüzden ölçülen büyüklük 1 dakikalık fiyat hareketidir ve
**bilerek muhafazakâr bir üst sınırdır**: gerçek pencere 1 dakikadan onlarca kat kısa.

**Persentil seçimi neden p75.** Rastgele yürüyüşte hareket ~√t ile büyür; 1 s'lik gerçek
pencere yerine 60 s ölçmek büyüklüğü ~√60 ≈ 7,7 kat abartır. Yani metrik **zaten**
muhafazakâr. Üstüne p95/p99 koymak iki muhafazakârlığı çarpar ve her stratejiyi gerçek
olmayan bir sebeple zararlı gösterir — bu da bir hata türüdür, sadece diğer yöne doğru.
Medyan ise K-007'nin "belirsizlikte aleyhte yuvarla" kuralını çiğner. p75 tek ve bilinçli
bir emniyet payı bırakır. Tam dağılım konfigürasyona yazılır; persentil kararı yeniden
ölçüm gerektirmeden değiştirilebilsin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

from scryne_quant.common.zaman import utc_str
from scryne_quant.data.semalar import KaliteDurumu

#: Kalibrasyonun okuduğu timeframe. 1m verisi tam da bunun için indiriliyor (K-017).
KALIBRASYON_TIMEFRAME: Final = "1m"

#: Varsayılan persentil. Gerekçe modül docstring'inde; değiştirilirse orada da değişmeli.
VARSAYILAN_PERSENTIL: Final = 75.0

#: Raporlanan persentiller. Spike 2'nin tablosuyla aynı kolonlar — karşılaştırılabilirlik
#: için; ölçüm yöntemi aynıysa sayılar da yakın çıkmalı, çıkmıyorsa sebebi araştırılmalı.
PERSENTILLER: Final[tuple[float, ...]] = (50.0, 75.0, 90.0, 95.0, 99.0)

YONTEM: Final = (
    "1 dakikalık bar-to-bar kapanış hareketi: "
    "|close[t] - close[t-1]| / close[t-1] * 10000 (bps). "
    "Yürütme penceresinin (bar kapanışı → emrin dolması, ölçülen p50 ~300 ms) "
    "muhafazakâr üst sınırı: gerçek pencere 1 dakikadan onlarca kat kısa."
)


@dataclass(frozen=True, slots=True)
class KalibrasyonSonucu:
    """Ölçümün tam çıktısı. Konfigürasyona yazılan değer bunun bir alanıdır."""

    sembol: str
    timeframe: str
    bar_sayisi: int
    kullanilan_bar: int
    ilk_ms: int
    son_ms: int
    persentil: float
    deger_bps: float
    dagilim_bps: dict[str, float]
    bar_ici_salinim_bps: dict[str, float]
    atilan_bar: int

    def sozluk(self) -> dict[str, Any]:
        return {
            "sembol": self.sembol,
            "timeframe": self.timeframe,
            "yontem": YONTEM,
            "bar_sayisi": self.bar_sayisi,
            "kullanilan_bar": self.kullanilan_bar,
            "atilan_bar": self.atilan_bar,
            "ilk": utc_str(self.ilk_ms),
            "son": utc_str(self.son_ms),
            "ilk_ms": self.ilk_ms,
            "son_ms": self.son_ms,
            "persentil": self.persentil,
            "deger_bps": self.deger_bps,
            "dagilim_bps": self.dagilim_bps,
            "bar_ici_salinim_bps": self.bar_ici_salinim_bps,
        }


class KalibrasyonHatasi(Exception):
    """Kalibrasyon yapılamayacak girdi."""


def hareket_bps(kapanis: np.ndarray) -> np.ndarray:
    """Bar-to-bar kapanış hareketi, bps. İlk bar için tanımsız — dizi bir kısa döner."""
    onceki = kapanis[:-1]
    return np.abs(kapanis[1:] - onceki) / onceki * 10_000


def kalibre_et(
    df: pd.DataFrame,
    *,
    sembol: str,
    timeframe: str = KALIBRASYON_TIMEFRAME,
    persentil: float = VARSAYILAN_PERSENTIL,
) -> KalibrasyonSonucu:
    """1m barlardan `slippage_bps` adayını hesaplar. (K-021)

    **Yalnızca `ok` barlar kullanılır** (K-006). Şüpheli bir bar dağılımın kuyruğunu
    tek başına taşıyabilir — ve slippage tam olarak kuyruktan okunan bir sayıdır.
    Doğrulanmamış bir barın buraya sızması, maliyeti veriye değil bir hataya bağlar.

    Boşluğun ötesindeki hareket de atılır: bir boşluğun iki yakasındaki kapanışlar arası
    fark 1 dakikalık hareket değil, boşluk kadar sürenin hareketidir.
    """
    if "close" not in df.columns or "open_time" not in df.columns:
        raise KalibrasyonHatasi("close/open_time sütunları gerekli")
    if len(df) < 2:
        raise KalibrasyonHatasi(f"kalibrasyon için en az 2 bar gerekli, {len(df)} var")

    ham_sayi = len(df)
    calisma = df.sort_values("open_time", kind="stable").reset_index(drop=True)

    if "quality_status" in calisma.columns:
        temiz = calisma["quality_status"].astype("string") == str(KaliteDurumu.OK)
    else:
        temiz = pd.Series(True, index=calisma.index)

    kapanis = calisma["close"].to_numpy(dtype="float64")
    yuksek = calisma["high"].to_numpy(dtype="float64")
    dusuk = calisma["low"].to_numpy(dtype="float64")
    acilis = calisma["open"].to_numpy(dtype="float64")
    temiz_np = temiz.to_numpy(dtype=bool)

    # Bir hareket ancak **iki ucu da** temiz barsa kullanılır. Boşluğun ötesine geçen
    # hareketler bu kuralla kendiliğinden düşer: boşluktan sonraki bar `gap` bayraklıdır,
    # yani `ok` değildir. Tesadüf değil — bayrağın boşluktan **sonraki** bara konmasının
    # sebeplerinden biri tam olarak bu.
    gecerli = temiz_np[1:] & temiz_np[:-1]
    hareket = hareket_bps(kapanis)
    hareket = hareket[gecerli & np.isfinite(hareket)]

    if hareket.size == 0:
        raise KalibrasyonHatasi("kullanılabilir (ok) ardışık bar çifti yok")

    with np.errstate(divide="ignore", invalid="ignore"):
        salinim = (yuksek - dusuk) / acilis * 10_000
    salinim = salinim[temiz_np & np.isfinite(salinim)]

    dagilim = {f"p{int(p)}": float(np.percentile(hareket, p)) for p in PERSENTILLER}
    dagilim["ort"] = float(hareket.mean())
    dagilim["max"] = float(hareket.max())

    salinim_dagilim = {f"p{int(p)}": float(np.percentile(salinim, p)) for p in PERSENTILLER}
    salinim_dagilim["ort"] = float(salinim.mean())
    salinim_dagilim["max"] = float(salinim.max())

    return KalibrasyonSonucu(
        sembol=sembol.upper(),
        timeframe=timeframe,
        bar_sayisi=ham_sayi,
        kullanilan_bar=int(hareket.size),
        ilk_ms=int(calisma["open_time"].iloc[0]),
        son_ms=int(calisma["open_time"].iloc[-1]),
        persentil=persentil,
        deger_bps=float(np.percentile(hareket, persentil)),
        dagilim_bps=dagilim,
        bar_ici_salinim_bps=salinim_dagilim,
        atilan_bar=int(ham_sayi - 1 - hareket.size),
    )
