"""Aktif bot stratejileri: saf, nedensel yön serileri. (K-134)

Her strateji `df` (kapanmış barlar; `open/high/low/close`, zamana göre sıralı) alır ve aynı
indeksli bir `pd.Series` döndürür: bar t'nin değeri, **t'nin kapanışında** verilen karardır
(+1 long, −1 short, 0 düz). Yalnız `rolling`, `ewm(adjust=False)` ve ileri doğru döngü
kullanılır; t sonrası veri t'nin kararını değiştiremez (`test_aktif.py` kesme testi).

Canlı döngü serinin son değerini, backtest tamamını kullanır — iki yol aynı kodu çağırır.

**Bu stratejilerin hiçbiri doğrulanmış bir üstünlük iddia etmez.** Demo, maliyet sonrası
gerçek sonucu ölçmek içindir.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import numpy as np
import pandas as pd

StratejiFn = Callable[..., pd.Series]


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder ATR (ewm, adjust=False — nedensel)."""
    onceki = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - onceki).abs(), (df["low"] - onceki).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int) -> pd.Series:
    fark = close.diff()
    kazanc = fark.clip(lower=0.0).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    kayip = (-fark.clip(upper=0.0)).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = kazanc / kayip.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(100.0).where(kazanc.notna())


def ema_trend(df: pd.DataFrame, hizli: int = 20, yavas: int = 50) -> pd.Series:
    """Hızlı EMA yavaşın üstündeyse long, altındaysa short. Hep piyasada."""
    c = df["close"]
    f = c.ewm(span=hizli, adjust=False).mean()
    s = c.ewm(span=yavas, adjust=False).mean()
    yon = np.sign(f - s)
    yon.iloc[:yavas] = 0.0
    return yon.astype(float)


def kirilim(df: pd.DataFrame, giris: int = 20, cikis: int = 10) -> pd.Series:
    """Donchian kırılımı: son `giris` barın tepesi kırılınca long, dibi kırılınca short;
    ters yöndeki `cikis` kanalı kırılınca düz."""
    h, lo, c = df["high"], df["low"], df["close"]
    ust = h.rolling(giris).max().shift(1).to_numpy()
    alt = lo.rolling(giris).min().shift(1).to_numpy()
    c_ust = h.rolling(cikis).max().shift(1).to_numpy()
    c_alt = lo.rolling(cikis).min().shift(1).to_numpy()
    kapanis = c.to_numpy()
    sonuc = np.zeros(len(df))
    poz = 0.0
    for i in range(len(df)):
        if np.isnan(ust[i]):
            sonuc[i] = 0.0
            continue
        if poz > 0 and kapanis[i] < c_alt[i] or poz < 0 and kapanis[i] > c_ust[i]:
            poz = 0.0
        if kapanis[i] > ust[i]:
            poz = 1.0
        elif kapanis[i] < alt[i]:
            poz = -1.0
        sonuc[i] = poz
    return pd.Series(sonuc, index=df.index)


def rsi_donus(
    df: pd.DataFrame,
    n: int = 3,
    alt: float = 15.0,
    ust: float = 85.0,
    cikis: float = 50.0,
    trend: int = 200,
) -> pd.Series:
    """Kısa RSI ile ortalamaya dönüş, trend yönünde: trend yukarıyken aşırı satımda long,
    aşağıyken aşırı alımda short; RSI `cikis`i geçince düz."""
    c = df["close"]
    r = rsi(c, n).to_numpy()
    ort = c.rolling(trend).mean().to_numpy()
    kapanis = c.to_numpy()
    sonuc = np.zeros(len(df))
    poz = 0.0
    for i in range(len(df)):
        if np.isnan(ort[i]) or np.isnan(r[i]):
            sonuc[i] = 0.0
            continue
        if poz > 0 and r[i] > cikis or poz < 0 and r[i] < cikis:
            poz = 0.0
        if poz == 0.0:
            if r[i] < alt and kapanis[i] > ort[i]:
                poz = 1.0
            elif r[i] > ust and kapanis[i] < ort[i]:
                poz = -1.0
        sonuc[i] = poz
    return pd.Series(sonuc, index=df.index)


STRATEJILER: Final[dict[str, StratejiFn]] = {
    "ema_trend": ema_trend,
    "kirilim": kirilim,
    "rsi_donus": rsi_donus,
}

#: Serinin anlamlı olması için gereken asgari bar (en uzun pencere + ATR payı).
ISINMA: Final[dict[str, int]] = {"ema_trend": 60, "kirilim": 30, "rsi_donus": 210}


def yon_serisi(
    ad: str, df: pd.DataFrame, parametreler: dict[str, Any] | None = None, *, yalniz_long: bool
) -> pd.Series:
    """Kayıtlı stratejinin yön serisi; `yalniz_long` short'u düze çevirir (spot)."""
    try:
        fn = STRATEJILER[ad]
    except KeyError:
        raise ValueError(f"bilinmeyen strateji {ad!r}; geçerli: {', '.join(STRATEJILER)}") from None
    yon = fn(df, **(parametreler or {}))
    return yon.clip(lower=0.0) if yalniz_long else yon
