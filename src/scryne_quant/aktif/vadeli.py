"""Kaldıraçlı vadeli trend/kırılım demo botu (K-140): günlük karar, saatlik stop, izole dilim.

Karar ve stop mantığı **tek yerde** (bu modül); backtest (`tools/kaldirac_trend.py`) de buradan
çağırır, yani canlı demo ve geriye bakış aynı kodu çalıştırır.

- S1 Donchian (Turtle 2): kapanış > 55 günlük tepe → long, < 55 günlük dip → short; çıkış ters
  20 günlük kanal ya da 3 × ATR(20) iz süren stop.
- S2 SuperTrend (10, 3): yön değişince ters çevir.
- S3 Bollinger (20, 2σ): bant dışı kapanışta o yöne gir; orta bandı ters geçince çık.
- İsteğe bağlı %2 keskin stop (girişten aleyhte %2 fiyat).

Sermaye sembollere eşit bölünür (izole dilim). Notional = kaldıraç × dilim. Likidasyon: işlem
içi en kötü aleyhte hareket ≥ 1/kaldıraç − %0,5 → dilim sıfırlanır. Emir yok; Binance USDT-M
public uçlarından fiyat/funding okunur, dolumlar simüle.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np
import pandas as pd

from scryne_quant.aktif.araci import AraciHatasi, Dolum
from scryne_quant.aktif.defter import Defter
from scryne_quant.common.zaman import simdi_ms

SAAT_MS: Final = 3_600_000
GUN_MS: Final = 86_400_000
FAPI: Final = "https://fapi.binance.com"
BAKIM: Final = 0.005


# ------------------------------------------------------------------ göstergeler ve karar


def atr(b: pd.DataFrame, n: int) -> pd.Series:
    onceki = b["close"].shift(1)
    tr = pd.concat(
        [b["high"] - b["low"], (b["high"] - onceki).abs(), (b["low"] - onceki).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def supertrend(b: pd.DataFrame, n: int = 10, m: float = 3.0) -> np.ndarray:
    a = atr(b, n).to_numpy()
    hl2 = ((b["high"] + b["low"]) / 2).to_numpy()
    c = b["close"].to_numpy()
    ust, alt = hl2 + m * a, hl2 - m * a
    yon = np.zeros(len(b))
    fu, fl = ust.copy(), alt.copy()
    for i in range(1, len(b)):
        if np.isnan(a[i]):
            continue
        # Önceki bant yoksa (ısınma) bugünkü bant alınır; NaN karşılaştırması bandı
        # kalıcı NaN bırakıyordu (K-140 hata düzeltmesi).
        if np.isnan(fu[i - 1]) or ust[i] < fu[i - 1] or c[i - 1] > fu[i - 1]:
            fu[i] = ust[i]
        else:
            fu[i] = fu[i - 1]
        if np.isnan(fl[i - 1]) or alt[i] > fl[i - 1] or c[i - 1] < fl[i - 1]:
            fl[i] = alt[i]
        else:
            fl[i] = fl[i - 1]
        if np.isnan(fu[i - 1]):
            continue
        if yon[i - 1] <= 0:
            yon[i] = 1 if c[i] > fu[i - 1] else -1
        else:
            yon[i] = -1 if c[i] < fl[i - 1] else 1
    return yon


@dataclass(frozen=True)
class Gostergeler:
    """Karar için gereken göstergeler; bar k'nin değeri yalnız k'ye kadarki veriden."""

    c: np.ndarray
    atr20: np.ndarray
    hh55: np.ndarray
    ll55: np.ndarray
    hh20: np.ndarray
    ll20: np.ndarray
    st: np.ndarray
    sma: np.ndarray
    sd: np.ndarray

    @classmethod
    def hesapla(cls, b: pd.DataFrame) -> Gostergeler:
        h, lo, c = b["high"], b["low"], b["close"]
        return cls(
            c=c.to_numpy(), atr20=atr(b, 20).to_numpy(),
            hh55=h.rolling(55).max().shift(1).to_numpy(),
            ll55=lo.rolling(55).min().shift(1).to_numpy(),
            hh20=h.rolling(20).max().shift(1).to_numpy(),
            ll20=lo.rolling(20).min().shift(1).to_numpy(),
            st=supertrend(b), sma=c.rolling(20).mean().to_numpy(),
            sd=c.rolling(20).std().to_numpy(),
        )


def karar(strat: str, g: Gostergeler, k: int, poz: int) -> int | None:
    """Bar k kapanışında hedef pozisyon (+1/0/−1) ya da None (değişiklik yok)."""
    c = g.c[k]
    if strat == "S1":
        if poz == 0 or (poz > 0 and c < g.ll20[k]) or (poz < 0 and c > g.hh20[k]):
            yeni = 1 if c > g.hh55[k] else (-1 if c < g.ll55[k] else 0)
            return yeni if yeni != poz else None
        return None
    if strat == "S2":
        return int(g.st[k]) if g.st[k] != 0 and g.st[k] != poz else None
    ust, alt = g.sma[k] + 2 * g.sd[k], g.sma[k] - 2 * g.sd[k]
    yeni = 1 if c > ust else (-1 if c < alt else None)
    if poz > 0 and c < g.sma[k]:
        return yeni if yeni == -1 else 0
    if poz < 0 and c > g.sma[k]:
        return yeni if yeni == 1 else 0
    if poz == 0 and yeni is not None:
        return yeni
    return None


def stoplar(strat: str, poz: int, giris: float, uc: float, stop_atr: float,
            sert_stop: bool) -> list[float]:
    """Açık pozisyonun stop seviyeleri (saatlik barla denetlenir)."""
    cikti = []
    if sert_stop:
        cikti.append(giris * (1 - 0.02 * poz))
    if strat == "S1" and not np.isnan(stop_atr):
        cikti.append(uc - poz * 3 * stop_atr)
    return cikti


def stop_dolumu(poz: int, acilis: float, yuksek: float, dusuk: float,
                seviyeler: list[float]) -> float | None:
    """Barda tetiklenen ilk stopun dolumu (boşlukta açılıştan, K-007 aleyhte)."""
    for sp in seviyeler:
        if (poz > 0 and dusuk <= sp) or (poz < 0 and yuksek >= sp):
            return min(acilis, sp) if poz > 0 else max(acilis, sp)
    return None


# ------------------------------------------------------------------ canlı demo


@dataclass(frozen=True)
class VadeliAyari:
    strat: str
    kaldirac: float
    sert_stop: bool
    semboller: tuple[str, ...]
    maliyet: float = (5 + 2) / 1e4  # taker + kayma, taraf başı, notional üzerinden


class VadeliVeri(Protocol):
    def klines(self, sembol: str, aralik: str, adet: int) -> pd.DataFrame: ...
    def fiyat(self, sembol: str) -> float: ...
    def funding(self, sembol: str, bas_ms: int) -> list[tuple[int, float, float]]: ...


class BinanceVadeliVeri:
    """USDT-M public: kapanmış klines (açık bar atılır), mark fiyatı, funding geçmişi."""

    def __init__(self) -> None:
        import requests

        from scryne_quant.exchange.binance import ipv4_zorla

        ipv4_zorla()
        self._s = requests.Session()

    def _al(self, yol: str, **params: Any) -> Any:
        son: Exception | None = None
        for deneme in range(4):
            try:
                r = self._s.get(FAPI + yol, params=params, timeout=15)
                r.raise_for_status()
                return r.json()
            except Exception as hata:  # noqa: BLE001 — okuma: yeniden denenir
                son = hata
                time.sleep(1.5 * (deneme + 1))
        raise AraciHatasi(f"{yol}: {son}")

    def klines(self, sembol: str, aralik: str, adet: int) -> pd.DataFrame:
        ham = self._al("/fapi/v1/klines", symbol=sembol, interval=aralik, limit=adet + 1)
        simdi = simdi_ms()
        satir = [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]))
                 for k in ham if int(k[6]) < simdi]  # yalnız kapanmış barlar
        return pd.DataFrame(satir, columns=["open_time", "open", "high", "low", "close"]
                            ).set_index("open_time")

    def fiyat(self, sembol: str) -> float:
        return float(self._al("/fapi/v1/premiumIndex", symbol=sembol)["markPrice"])

    def funding(self, sembol: str, bas_ms: int) -> list[tuple[int, float, float]]:
        ham = self._al("/fapi/v1/fundingRate", symbol=sembol, startTime=bas_ms, limit=1000)
        return [(int(r["fundingTime"]), float(r["fundingRate"]), float(r.get("markPrice") or 0))
                for r in ham]


@dataclass
class Dilim:
    ozk: float
    poz: int = 0
    giris: float = 0.0
    notional: float = 0.0
    uc: float = 0.0
    mae: float = 0.0
    giris_ms: int = 0
    stop_atr: float = float("nan")
    son_bar_ms: int = 0
    son_funding_ms: int = 0
    tasfiye: bool = False
    ek: dict[str, Any] = field(default_factory=dict)


class VadeliHesap:
    """Dilimler `paper.json`da (`ek.dilimler`); `adet` = işaretli adet (pano uyumlu)."""

    def __init__(self, dizin: Path, sermaye: float, semboller: tuple[str, ...]) -> None:
        self._yol = Path(dizin) / "paper.json"
        self.ek: dict[str, Any] = {}
        if self._yol.is_file():
            d = json.loads(self._yol.read_text(encoding="utf-8"))
            self.ek = d.get("ek", {})
            self.dilimler = {s: Dilim(**v) for s, v in self.ek.get("dilimler", {}).items()}
        else:
            self.dilimler = {s: Dilim(ozk=sermaye / len(semboller)) for s in semboller}
            self.yaz()

    def yaz(self) -> None:
        self.ek["dilimler"] = {s: vars(d) for s, d in self.dilimler.items()}
        adet = {s: d.poz * d.notional / d.giris for s, d in self.dilimler.items()
                if d.poz and d.giris}
        nakit = sum(d.ozk for d in self.dilimler.values())
        veri = {"nakit": nakit, "adet": adet, "doviz": {}, "ek": self.ek}
        self._yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = self._yol.with_suffix(".tmp")
        gecici.write_text(json.dumps(veri, indent=1), encoding="utf-8")
        os.replace(gecici, self._yol)

    def deger(self, fiyat: dict[str, float]) -> float:
        toplam = 0.0
        for s, d in self.dilimler.items():
            toplam += d.ozk
            if d.poz and d.giris:
                toplam += d.notional * d.poz * (fiyat[s] / d.giris - 1)
        return toplam


def _kapat(d: Dilim, s: str, fiyat: float, zaman: int, neden: str, ayar: VadeliAyari,
           defter: Defter) -> None:
    kar = d.notional * d.poz * (fiyat / d.giris - 1)
    d.ozk += kar - d.notional * ayar.maliyet
    defter.islem(zaman, Dolum(s, -d.poz * d.notional / d.giris, fiyat, d.notional * ayar.maliyet),
                 -d.poz * d.notional, neden)
    d.poz, d.notional, d.giris, d.mae = 0, 0.0, 0.0, 0.0


def _ac(d: Dilim, s: str, yon: int, fiyat: float, zaman: int, ayar: VadeliAyari,
        defter: Defter) -> None:
    d.notional = ayar.kaldirac * d.ozk
    d.ozk -= d.notional * ayar.maliyet
    d.poz, d.giris, d.uc, d.mae, d.giris_ms = yon, fiyat, fiyat, 0.0, zaman
    d.son_funding_ms = zaman
    defter.islem(zaman, Dolum(s, yon * d.notional / fiyat, fiyat, d.notional * ayar.maliyet),
                 yon * d.notional, "giris")


def vadeli_tur(veri: VadeliVeri, hesap: VadeliHesap, defter: Defter, ayar: VadeliAyari,
               simdi: int) -> dict[str, Any]:
    olaylar: list[str] = []
    for s, d in hesap.dilimler.items():
        if d.tasfiye:
            continue
        # 1) Kapanan saatlik barlar: işlem içi en kötü hareket, stoplar, likidasyon, uç nokta.
        if d.poz:
            saatlik = veri.klines(s, "1h", 30)
            for t, bar in saatlik.iterrows():
                # Giriş barı da denetlenir (giriş, barın açılışından saniyeler sonra; backtest
                # o barın yüksek/düşüğünü de sayar).
                if int(t) < max(d.son_bar_ms + SAAT_MS, d.giris_ms // SAAT_MS * SAAT_MS):
                    continue
                d.son_bar_ms = int(t)
                aleyh = ((d.giris - bar["low"]) if d.poz > 0 else (bar["high"] - d.giris)) / d.giris
                d.mae = max(d.mae, aleyh)
                if d.mae >= 1 / ayar.kaldirac - BAKIM:
                    defter.olay(simdi, "tasfiye", {"sembol": s, "mae": d.mae})
                    defter.islem(simdi, Dolum(s, -d.poz * d.notional / d.giris, bar["close"], 0.0),
                                 -d.poz * d.notional, "tasfiye")
                    d.ozk, d.poz, d.notional, d.tasfiye = 0.0, 0, 0.0, True
                    olaylar.append(f"LİKİDASYON {s}")
                    break
                dolum = stop_dolumu(d.poz, bar["open"], bar["high"], bar["low"],
                                    stoplar(ayar.strat, d.poz, d.giris, d.uc, d.stop_atr,
                                            ayar.sert_stop))
                if dolum is not None:
                    _kapat(d, s, dolum, int(t) + SAAT_MS, "stop", ayar, defter)
                    olaylar.append(f"stop {s}")
                    break
                d.uc = max(d.uc, bar["high"]) if d.poz > 0 else min(d.uc, bar["low"])
        # 2) Funding (long pozitif oranda öder, short alır).
        if d.poz:
            for zaman, oran, mark in veri.funding(s, d.son_funding_ms + 1):
                if zaman <= simdi:
                    d.ozk -= d.poz * (d.notional / d.giris) * (mark or d.giris) * oran
                    d.son_funding_ms = zaman
    # 3) Günlük karar (00:00 UTC'den sonraki ilk tur); dolum anlık mark fiyatından.
    gun = simdi // GUN_MS
    if hesap.ek.get("son_karar_gun") != gun:
        for s, d in hesap.dilimler.items():
            if d.tasfiye:
                continue
            gunluk = veri.klines(s, "1d", 150)
            if len(gunluk) < 60:
                continue
            g = Gostergeler.hesapla(gunluk)
            k = len(gunluk) - 1
            d.stop_atr = float(g.atr20[k])
            hedef = karar(ayar.strat, g, k, d.poz)
            if hedef is None:
                continue
            fiyat = veri.fiyat(s)
            if d.poz and hedef != d.poz:
                _kapat(d, s, fiyat, simdi, "sinyal", ayar, defter)
                olaylar.append(f"çıkış {s}")
            if hedef != 0 and d.poz == 0:
                _ac(d, s, hedef, fiyat, simdi, ayar, defter)
                d.son_bar_ms = (simdi // SAAT_MS) * SAAT_MS - SAAT_MS
                olaylar.append(f"{'LONG' if hedef > 0 else 'SHORT'} {s}")
        hesap.ek["son_karar_gun"] = int(gun)
    hesap.yaz()
    fiyatlar = {s: veri.fiyat(s) for s, d in hesap.dilimler.items() if d.poz}
    deger = hesap.deger(fiyatlar)
    defter.ozkaynak(simdi, deger)
    return {"zaman_ms": simdi, "ozkaynak": deger, "olaylar": olaylar,
            "poz": {s: d.poz for s, d in hesap.dilimler.items() if d.poz}}


def calistir_vadeli(dizin: Path, sermaye: float, ayar: VadeliAyari,
                    veri: VadeliVeri | None = None, yaz: Any = print) -> None:
    from scryne_quant.live.kilit import KosuKilidi

    veri = veri or BinanceVadeliVeri()
    dizin.mkdir(parents=True, exist_ok=True)
    kilit = KosuKilidi(dizin / "aktif")
    kilit.al()
    defter = Defter(dizin)
    hesap = VadeliHesap(dizin, sermaye, ayar.semboller)
    dur = dizin / "dur"
    try:
        defter.olay(simdi_ms(), "basla", {"strateji": ayar.strat, "kaldirac": ayar.kaldirac})
        while not dur.exists():
            try:
                r = vadeli_tur(veri, hesap, defter, ayar, simdi_ms())
                yaz(f"{dt.datetime.now(dt.UTC):%H:%M} özkaynak {r['ozkaynak']:.2f} "
                    f"poz {r['poz']} {'; '.join(r['olaylar'])}")
            except Exception as hata:  # noqa: BLE001 — tur hatası döngüyü öldürmez
                defter.olay(simdi_ms(), "tur_hatasi",
                            {"hata": repr(hata), "iz": traceback.format_exc()[-2000:]})
                yaz(f"tur hatası: {hata!r}")
            sonraki = (simdi_ms() // SAAT_MS + 1) * SAAT_MS + 20_000
            while not dur.exists() and simdi_ms() < sonraki:
                time.sleep(min(5.0, max(0.5, (sonraki - simdi_ms()) / 1000)))
        defter.olay(simdi_ms(), "dur", {})
        dur.unlink(missing_ok=True)
    finally:
        defter.kapat()
        kilit.kapat()
