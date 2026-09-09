"""İndikatör referans fixture'ını üretir. **Testlerde çalışmaz, elle çalıştırılır.**

Faz 2'nin bitti kriteri her indikatörün *bağımsız* bir referansla doğrulanmasını istiyor.
Referans olarak TA-Lib seçildi (K-026). TA-Lib bir **proje bağımlılığı değil**: native bir
kütüphane ve yalnızca bu dosya için gerekli. Bu yüzden çıktısı bir kez üretilip
`tests/fixtures/indikator_referans.json` içine **dondurulur**, testler o dosyaya bakar.

Fixture kendi kendine yeter: hem girdi barlarını hem beklenen değerleri taşır. Yalnızca
beklenen değerleri saklamak, girdiyi üreten yardımcı bir gün değiştiğinde referansı
sessizce yanlış hale getirirdi — bu projede en pahalı hata sınıfı tam olarak budur.

Çalıştırma (ta-lib'i projeye eklemeden, geçici ortamla):

    uv run --with ta-lib python tools/referans_uret.py

Yeniden üretilirse `vakalar` bloğu **satırı satırına aynı çıkmalıdır** (üst düzeydeki
`uretildi` alanı tarihtir, o değişir). Vakalar değişiyorsa ya bir konvansiyon kaydı ya
TA-Lib sürümü değişmiştir — ikisi de sessizce geçilmez, `docs/Kararlar.md`'ye yazılır.

**Bilinen ve bilinçli sapma:** hareketsiz seride (kazanç = kayıp = 0) TA-Lib RSI olarak
`0.0` verir; biz NaN veriyoruz. Gerekçe `features/indikator.py:rsi` docstring'inde,
sapmayı sabitleyen test `tests/unit/test_indikator.py`'de.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

try:
    import talib
except ImportError:  # pragma: no cover - elle çalıştırılan araç
    sys.exit("talib yok. Çalıştır: uv run --with ta-lib python tools/referans_uret.py")

KOK = Path(__file__).resolve().parent.parent
HEDEF = KOK / "tests" / "fixtures" / "indikator_referans.json"

#: JSON'da NaN yok. `null` kullanılıyor ve okuma tarafında NaN'a çevriliyor — `Infinity`
#: veya `"NaN"` gibi standart dışı gösterimler ayrıştırıcıya göre değişir.
YOK = None


def _liste(dizi: np.ndarray) -> list[float | None]:
    return [YOK if np.isnan(x) else float(x) for x in dizi]


def _ohlcv_sentetik(n: int, tohum: int) -> dict[str, np.ndarray]:
    """`tests/conftest.py`'deki `bar_uret` ile aynı üretim — burada kopyalanmış.

    Kopya bilinçli: fixture üreticisinin test yardımcılarına bağlı olması, referansın
    test kodundan türemesi demek olurdu. Referans dışarıdan gelmeli.
    """
    rng = np.random.default_rng(tohum)
    close = 30_000.0 + np.cumsum(rng.normal(0, 25, n))
    acilis = np.concatenate([[close[0]], close[:-1]])
    sapma = np.abs(rng.normal(0, 15, n))
    hacim = np.abs(rng.normal(50, 12, n))
    return {
        "open": acilis,
        "high": np.maximum(acilis, close) + sapma,
        "low": np.minimum(acilis, close) - sapma,
        "close": close,
        "volume": hacim,
    }


def _ohlcv_kapanistan(close: np.ndarray, hacim_taban: float = 100.0) -> dict[str, np.ndarray]:
    """Yalnızca kapanış verilen vakalar için sentetik OHLCV sarmalayıcı."""
    n = close.size
    return {
        "open": np.concatenate([[close[0]], close[:-1]]),
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": np.full(n, hacim_taban) + np.arange(n, dtype=np.float64),
    }


#: Ders kitaplarında yaygın olarak kullanılan 30 kapanışlık RSI örneği. Küçük ve elle
#: kontrol edilebilir olması, bir regresyonun nerede kırıldığını okunur kılıyor.
DERS_KITABI = np.array(
    [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
        45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
        46.21, 46.25, 45.71, 46.45, 45.78, 45.35, 44.03, 44.18, 44.22, 44.57,
    ],
    dtype=np.float64,
)


def _vaka(ad: str, aciklama: str, ohlcv: dict[str, np.ndarray], pencereler: dict[str, Any]):
    h, d, k, v = ohlcv["high"], ohlcv["low"], ohlcv["close"], ohlcv["volume"]
    beklenen: dict[str, list[float | None]] = {}

    for n in pencereler["sma"]:
        beklenen[f"sma_{n}"] = _liste(talib.SMA(k, n))
    for n in pencereler["ema"]:
        beklenen[f"ema_{n}"] = _liste(talib.EMA(k, n))
    for n in pencereler["rsi"]:
        beklenen[f"rsi_{n}"] = _liste(talib.RSI(k, n))
    for n in pencereler["atr"]:
        beklenen[f"atr_{n}"] = _liste(talib.ATR(h, d, k, n))
    # TR'nin ilk barı TA-Lib'de high-low; bizde NaN (önceki kapanış yok — K-026).
    # Referansa da NaN yazılıyor ki test o barı karşılaştırma dışı bıraksın.
    tr = talib.TRANGE(h, d, k)
    tr[0] = np.nan
    beklenen["true_range"] = _liste(tr)
    for n, katsayi in pencereler["bollinger"]:
        ust, orta, alt = talib.BBANDS(k, n, katsayi, katsayi, 0)
        beklenen[f"bollinger_{n}_{katsayi:g}_ust"] = _liste(ust)
        beklenen[f"bollinger_{n}_{katsayi:g}_orta"] = _liste(orta)
        beklenen[f"bollinger_{n}_{katsayi:g}_alt"] = _liste(alt)
    for n in pencereler["hacim"]:
        beklenen[f"hacim_sma_{n}"] = _liste(talib.SMA(v, n))
    for n in pencereler["kanal"]:
        beklenen[f"enyuksek_{n}"] = _liste(talib.MAX(h, n))
        beklenen[f"endusuk_{n}"] = _liste(talib.MIN(d, n))
    for n in pencereler["roc"]:
        beklenen[f"roc_{n}"] = _liste(talib.ROC(k, n))

    return {
        "ad": ad,
        "aciklama": aciklama,
        "girdi": {ad_: _liste(seri) for ad_, seri in ohlcv.items()},
        "beklenen": beklenen,
    }


def main() -> int:
    genis = {
        "sma": (20, 50),
        "ema": (20, 50),
        "rsi": (7, 14),
        "atr": (14,),
        "bollinger": ((20, 2.0),),
        "hacim": (20,),
        "kanal": (20, 55),
        "roc": (10, 20),
    }
    dar = {
        "sma": (5,),
        "ema": (5,),
        "rsi": (14,),
        "atr": (14,),
        "bollinger": ((5, 2.0),),
        "hacim": (5,),
        "kanal": (5,),
        "roc": (3,),
    }

    duz = np.full(40, 100.0)
    artan = 100.0 + np.arange(40, dtype=np.float64)

    vakalar = [
        _vaka(
            "sentetik_400",
            "Rastgele yürüyüş, 400 bar — normal çalışma bölgesi.",
            _ohlcv_sentetik(400, tohum=7),
            genis,
        ),
        _vaka(
            "ders_kitabi_30",
            "30 kapanışlık klasik RSI örneği — küçük ve elle denetlenebilir.",
            _ohlcv_kapanistan(DERS_KITABI),
            dar,
        ),
        _vaka(
            "monoton_artan_40",
            "Kesintisiz yükseliş: ortalama kayıp sıfır, RSI'ın sıfıra bölme kenarı.",
            _ohlcv_kapanistan(artan),
            dar,
        ),
        _vaka(
            "duz_40",
            "Hiç hareket yok: hem kazanç hem kayıp sıfır, ATR sıfır, bant genişliği sıfır.",
            _ohlcv_kapanistan(duz),
            dar,
        ),
    ]

    belge = {
        "uretildi": dt.date.today().isoformat(),
        "ureten": "tools/referans_uret.py",
        "kaynak": {
            "kutuphane": "TA-Lib",
            "surum": talib.__version__,
            "numpy": np.__version__,
            "python": sys.version.split()[0],
        },
        "not": (
            "Bağımsız referans (K-026). Bizim indikatörlerimiz TA-Lib ile bit düzeyinde "
            "aynı olmaz — TA-Lib yürüyen toplam, numpy pencere başına toplam kullanır. "
            "Testlerdeki tolerans bu farkı kapsar, konvansiyon farkını kapsamaz: NaN "
            "maskeleri birebir eşit olmak zorundadır."
        ),
        "vakalar": vakalar,
    }

    HEDEF.parent.mkdir(parents=True, exist_ok=True)
    HEDEF.write_text(
        json.dumps(belge, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"yazıldı: {HEDEF.relative_to(KOK)}  ({HEDEF.stat().st_size / 1024:.0f} KB)")
    print(f"vaka: {len(vakalar)}  ·  TA-Lib {talib.__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
