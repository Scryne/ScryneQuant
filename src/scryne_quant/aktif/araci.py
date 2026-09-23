"""Aktif botun aracı adaptörleri: kripto paper ve MT5 demo. (K-134)

İkisi aynı yüzeyi sunar (`Araci`); döngü hangisiyle konuştuğunu bilmez.

- `KriptoPaper`: Binance **public** veri (anahtar yok), dolum simülasyonu. Hesap durumu
  koşu dizinindeki `paper.json`da; başka hiçbir koşu bu dosyayı paylaşmaz (testnet'teki
  ortak hesap hatasının tekrarı yok, K-134).
- `MT5Araci`: MetaTrader 5 terminali üzerinden. **Yalnız demo hesapta çalışır**: bağlanırken
  ve her emirden önce `trade_mode == DEMO` denetlenir; gerçek hesapta istisna atar.
  Pozisyonlar `magic` numarasıyla ayrılır; elle açılan işlemlere dokunulmaz.

Yazma (emir) çağrıları yeniden denenmez; belirsiz sonuçta istisna atılır, bir sonraki tur
durumu aracıdan yeniden okur (tahmin yürütülmez).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

import pandas as pd

from scryne_quant.common.zaman import timeframe_ms

SUTUNLAR: Final = ["open", "high", "low", "close"]


class AraciHatasi(RuntimeError):
    """Aracı işlemi yapılamadı ya da sonucu belirsiz."""


@dataclass(frozen=True)
class Dolum:
    sembol: str
    adet: float  # işaretli, aracı birimi (kripto: coin; MT5: lot)
    fiyat: float
    ucret: float  # hesap para birimi


class Araci(Protocol):
    ad: str
    yalniz_long: bool

    def barlar(self, sembol: str, timeframe: str, adet: int) -> pd.DataFrame: ...
    def fiyat(self, sembol: str) -> float: ...
    def ozkaynak(self) -> float: ...
    def pozisyonlar(self) -> dict[str, float]: ...
    def birim_notional(self, sembol: str, fiyat: float) -> float: ...
    def adet_yuvarla(self, sembol: str, adet: float) -> float: ...
    def emir(self, sembol: str, delta: float, neden: str) -> Dolum: ...


def _bar_df(open_time_ms: Any, o: Any, h: Any, lo: Any, c: Any) -> pd.DataFrame:
    # Değerler diziye çevrilir: Series verilirse pandas indekse göre hizalar ve her şey NaN olur.
    def dizi(x: Any) -> Any:
        return pd.Series(x).to_numpy(dtype=float)

    df = pd.DataFrame(
        {"open": dizi(o), "high": dizi(h), "low": dizi(lo), "close": dizi(c)},
        index=pd.Index(pd.Series(open_time_ms, dtype="int64").to_numpy(), name="open_time"),
    )
    return df[~df.index.duplicated(keep="last")].sort_index()


# ------------------------------------------------------------------ kripto paper


class KriptoPaper:
    """Binance spot fiyatıyla simüle hesap. Dolum = anlık fiyat ± kayma (aleyhte), + ücret."""

    ad = "kripto_paper"

    def __init__(
        self,
        dizin: Path,
        *,
        sermaye: float,
        ucret_bps: float,
        kayma_bps: float,
        yalniz_long: bool = True,
        veri: Any | None = None,
    ) -> None:
        if veri is None:
            from scryne_quant.exchange.binance import BinanceAdaptoru

            veri = BinanceAdaptoru()
        self._veri = veri
        self.yalniz_long = yalniz_long
        self._ucret = ucret_bps / 10_000
        self._kayma = kayma_bps / 10_000
        self._yol = Path(dizin) / "paper.json"
        if self._yol.is_file():
            d = json.loads(self._yol.read_text(encoding="utf-8"))
            self._nakit = float(d["nakit"])
            self._adet = {k: float(v) for k, v in d["adet"].items()}
        else:
            self._nakit = float(sermaye)
            self._adet = {}
            self._yaz()
        self._fiyat_onbellek: dict[str, tuple[float, float]] = {}

    def _yaz(self) -> None:
        self._yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = self._yol.with_suffix(".tmp")
        gecici.write_text(
            json.dumps({"nakit": self._nakit, "adet": self._adet}, indent=1), encoding="utf-8"
        )
        os.replace(gecici, self._yol)

    def barlar(self, sembol: str, timeframe: str, adet: int) -> pd.DataFrame:
        adim = timeframe_ms(timeframe)
        simdi = self._veri.sunucu_zamani_ms()
        ham = self._veri.klines(sembol, timeframe, simdi - (adet + 1) * adim, simdi)
        return _bar_df(ham["open_time"], ham["open"], ham["high"], ham["low"], ham["close"])

    def fiyat(self, sembol: str) -> float:
        onbellek = self._fiyat_onbellek.get(sembol)
        if onbellek is not None and time.monotonic() - onbellek[1] < 5.0:
            return onbellek[0]
        f = float(self._veri.son_fiyat(sembol))
        self._fiyat_onbellek[sembol] = (f, time.monotonic())
        return f

    def ozkaynak(self) -> float:
        return self._nakit + sum(a * self.fiyat(s) for s, a in self._adet.items() if a)

    def pozisyonlar(self) -> dict[str, float]:
        return {s: a for s, a in self._adet.items() if a}

    def birim_notional(self, sembol: str, fiyat: float) -> float:
        return fiyat

    def adet_yuvarla(self, sembol: str, adet: float) -> float:
        return round(adet, 8)

    def emir(self, sembol: str, delta: float, neden: str) -> Dolum:
        if delta == 0:
            raise AraciHatasi("sıfır adetli emir")
        mevcut = self._adet.get(sembol, 0.0)
        if self.yalniz_long and mevcut + delta < -1e-12:
            raise AraciHatasi(f"{sembol}: spot hesapta açığa satış yok")
        ref = float(self._veri.son_fiyat(sembol))
        fiyat = ref * (1 + self._kayma) if delta > 0 else ref * (1 - self._kayma)
        ucret = abs(delta) * fiyat * self._ucret
        self._nakit -= delta * fiyat + ucret
        yeni = round(mevcut + delta, 12)
        if abs(yeni) < 1e-12:
            self._adet.pop(sembol, None)
        else:
            self._adet[sembol] = yeni
        self._yaz()
        return Dolum(sembol, delta, fiyat, ucret)


def binance_gecmis(sembol: str, timeframe: str, baslangic_ms: int, bitis_ms: int,
                   veri: Any | None = None) -> pd.DataFrame:
    """Backtest için sayfalı geçmiş (public, kapanmış barlar)."""
    if veri is None:
        from scryne_quant.exchange.binance import BinanceAdaptoru

        veri = BinanceAdaptoru()
    adim = timeframe_ms(timeframe)
    parcalar = []
    t = baslangic_ms
    while t < bitis_ms:
        ham = veri.klines(sembol, timeframe, t, bitis_ms)
        if ham.empty:
            break
        parcalar.append(ham)
        t = int(ham["open_time"].iloc[-1]) + adim
    if not parcalar:
        return _bar_df([], [], [], [], [])
    ham = pd.concat(parcalar, ignore_index=True)
    return _bar_df(ham["open_time"], ham["open"], ham["high"], ham["low"], ham["close"])


# ------------------------------------------------------------------ MT5 demo

MAGIC: Final = 134_000


class MT5Araci:
    """MetaTrader 5 demo hesabı. Kimlik: ortam değişkenleri `MT5_LOGIN`, `MT5_PASSWORD`,
    `MT5_SERVER` (isteğe bağlı `MT5_PATH`); yoksa terminalde açık olan hesap kullanılır."""

    ad = "mt5"
    yalniz_long = False

    def __init__(
        self, *, sunucu_utc_farki_saat: float | None = None, mt5: Any | None = None
    ) -> None:
        if mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore[import-not-found, no-redef]
            except ImportError as hata:
                raise AraciHatasi(
                    "MetaTrader5 paketi yok: `uv add MetaTrader5` ve MT5 terminali gerekli"
                ) from hata
        self._mt5 = mt5
        argumanlar: dict[str, Any] = {}
        if os.environ.get("MT5_PATH"):
            argumanlar["path"] = os.environ["MT5_PATH"]
        if os.environ.get("MT5_LOGIN"):
            argumanlar.update(
                login=int(os.environ["MT5_LOGIN"]),
                password=os.environ.get("MT5_PASSWORD", ""),
                server=os.environ.get("MT5_SERVER", ""),
            )
        if not mt5.initialize(**argumanlar):
            raise AraciHatasi(f"MT5 bağlantısı kurulamadı: {mt5.last_error()}")
        self._demo_denetle()
        hesap = mt5.account_info()
        self.hedging = hesap.margin_mode == mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING
        self.para_birimi = str(hesap.currency)
        self._fark_s = None if sunucu_utc_farki_saat is None else int(sunucu_utc_farki_saat * 3600)
        self._tf = {
            "1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "15m": mt5.TIMEFRAME_M15,
            "30m": mt5.TIMEFRAME_M30, "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4,
            "1d": mt5.TIMEFRAME_D1,
        }

    def _demo_denetle(self) -> None:
        hesap = self._mt5.account_info()
        if hesap is None:
            raise AraciHatasi(f"MT5 hesap bilgisi yok: {self._mt5.last_error()}")
        if hesap.trade_mode != self._mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise AraciHatasi(
                "K-134: aktif bot yalnız MT5 DEMO hesapta çalışır; bu hesap demo değil"
            )

    def _sembol(self, sembol: str) -> Any:
        bilgi = self._mt5.symbol_info(sembol)
        if bilgi is None:
            raise AraciHatasi(f"MT5'te sembol yok: {sembol}")
        if not bilgi.visible:
            self._mt5.symbol_select(sembol, True)
        return bilgi

    def sunucu_farki_s(self, sembol: str) -> int:
        """Sunucu saati − UTC (saniye). Bar zamanları sunucu saatindedir; K-005 UTC ister.

        Ayarda verilmişse o; değilse taze bir tick'ten yarım saate yuvarlanarak ölçülür.
        Tick bayatsa (piyasa kapalı) ölçülemez ve istisna atılır — tahmin edilmez.
        """
        if self._fark_s is not None:
            return self._fark_s
        tick = self._mt5.symbol_info_tick(sembol)
        if tick is None:
            raise AraciHatasi(f"{sembol}: tick yok")
        ham = float(tick.time) - time.time()
        fark = int(round(ham / 1800.0) * 1800)
        if abs(ham - fark) > 300:
            raise AraciHatasi(
                f"{sembol}: tick bayat, sunucu saat farkı ölçülemedi (piyasa kapalı?)"
            )
        self._fark_s = fark
        return fark

    def barlar(self, sembol: str, timeframe: str, adet: int) -> pd.DataFrame:
        self._sembol(sembol)
        # Konum 1'den başla: 0 henüz kapanmamış bar.
        oranlar = self._mt5.copy_rates_from_pos(sembol, self._tf[timeframe], 1, adet)
        if oranlar is None or len(oranlar) == 0:
            raise AraciHatasi(f"{sembol}: bar alınamadı: {self._mt5.last_error()}")
        df = pd.DataFrame(oranlar)
        fark = self.sunucu_farki_s(sembol)
        acilis = (df["time"].astype("int64") - fark) * 1000
        return _bar_df(acilis, df["open"], df["high"], df["low"], df["close"])

    def fiyat(self, sembol: str) -> float:
        tick = self._mt5.symbol_info_tick(sembol)
        if tick is None or not tick.bid > 0:
            raise AraciHatasi(f"{sembol}: fiyat yok")
        return (float(tick.bid) + float(tick.ask)) / 2.0

    def ozkaynak(self) -> float:
        hesap = self._mt5.account_info()
        if hesap is None:
            raise AraciHatasi("MT5 hesap bilgisi yok")
        return float(hesap.equity)

    def _bizimkiler(self, sembol: str | None = None) -> list[Any]:
        pozlar = self._mt5.positions_get(symbol=sembol) if sembol else self._mt5.positions_get()
        return [p for p in (pozlar or ()) if p.magic == MAGIC]

    def pozisyonlar(self) -> dict[str, float]:
        sonuc: dict[str, float] = {}
        for p in self._bizimkiler():
            isaret = 1.0 if p.type == self._mt5.POSITION_TYPE_BUY else -1.0
            sonuc[p.symbol] = sonuc.get(p.symbol, 0.0) + isaret * float(p.volume)
        return {s: round(v, 8) for s, v in sonuc.items() if abs(v) > 1e-12}

    def birim_notional(self, sembol: str, fiyat: float) -> float:
        bilgi = self._sembol(sembol)
        if str(bilgi.currency_profit) != self.para_birimi:
            raise AraciHatasi(
                f"{sembol}: kâr para birimi {bilgi.currency_profit} ≠ hesap {self.para_birimi}; "
                "çevrim yok, sembol listeden çıkarılmalı"
            )
        return float(bilgi.trade_contract_size) * fiyat

    def adet_yuvarla(self, sembol: str, adet: float) -> float:
        bilgi = self._sembol(sembol)
        adim = float(bilgi.volume_step)
        lot = round(round(abs(adet) / adim) * adim, 8)
        if lot < float(bilgi.volume_min) - 1e-12:
            return 0.0
        lot = min(lot, float(bilgi.volume_max))
        return lot if adet > 0 else -lot

    def _dolum_turu(self, bilgi: Any) -> Any:
        m = self._mt5
        mod = int(bilgi.filling_mode)
        if mod & 1:
            return m.ORDER_FILLING_FOK
        if mod & 2:
            return m.ORDER_FILLING_IOC
        return m.ORDER_FILLING_RETURN

    def _gonder(self, sembol: str, hacim: float, alis: bool, pozisyon: int | None) -> Dolum:
        m = self._mt5
        bilgi = self._sembol(sembol)
        tick = m.symbol_info_tick(sembol)
        if tick is None:
            raise AraciHatasi(f"{sembol}: tick yok")
        istek: dict[str, Any] = {
            "action": m.TRADE_ACTION_DEAL,
            "symbol": sembol,
            "volume": hacim,
            "type": m.ORDER_TYPE_BUY if alis else m.ORDER_TYPE_SELL,
            "price": float(tick.ask if alis else tick.bid),
            "deviation": 20,
            "magic": MAGIC,
            "comment": "sq-aktif",
            "type_time": m.ORDER_TIME_GTC,
            "type_filling": self._dolum_turu(bilgi),
        }
        if pozisyon is not None:
            istek["position"] = pozisyon
        sonuc = m.order_send(istek)
        if sonuc is None:
            raise AraciHatasi(f"{sembol}: order_send yanıtsız (sonuç belirsiz): {m.last_error()}")
        if sonuc.retcode != m.TRADE_RETCODE_DONE:
            raise AraciHatasi(f"{sembol}: emir reddedildi retcode={sonuc.retcode} {sonuc.comment}")
        ucret = 0.0
        islemler = m.history_deals_get(ticket=sonuc.deal) if sonuc.deal else None
        for d in islemler or ():
            ucret -= float(getattr(d, "commission", 0.0)) + float(getattr(d, "fee", 0.0))
        return Dolum(sembol, hacim if alis else -hacim, float(sonuc.price), ucret)

    def emir(self, sembol: str, delta: float, neden: str) -> Dolum:
        self._demo_denetle()
        if delta == 0:
            raise AraciHatasi("sıfır adetli emir")
        alis = delta > 0
        kalan = abs(delta)
        dolumlar: list[Dolum] = []
        if self.hedging:
            # Hedging hesabında ters işlem pozisyonu kapatmaz, yenisini açar: önce ters
            # yöndeki kendi pozisyonlarımızı bilet numarasıyla kapat.
            ters = self._mt5.POSITION_TYPE_SELL if alis else self._mt5.POSITION_TYPE_BUY
            for p in self._bizimkiler(sembol):
                if kalan <= 1e-12 or p.type != ters:
                    continue
                hacim = min(float(p.volume), kalan)
                dolumlar.append(self._gonder(sembol, hacim, alis, int(p.ticket)))
                kalan = round(kalan - hacim, 8)
        if kalan > 1e-12:
            dolumlar.append(self._gonder(sembol, kalan, alis, None))
        toplam = sum(abs(d.adet) for d in dolumlar)
        ort = sum(abs(d.adet) * d.fiyat for d in dolumlar) / toplam
        return Dolum(sembol, delta, ort, sum(d.ucret for d in dolumlar))
