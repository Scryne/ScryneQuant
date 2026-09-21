"""FX maliyet kalibrasyonu: M1 bid/ask spread dağılımı + slippage (kripto kalıbı). (K-098, R5/1)

**Yeni kalibrasyon sistemi değil.** Slippage `data/kalibrasyon.kalibre_et` ile ölçülür — kripto
ile aynı büyüklük (1 dakikalık bar-to-bar kapanış hareketi, K-021), tek fark girdinin **orta**
fiyat (`(bid + ask) / 2`) olması. Spread ise bu modülün eklediği tek ölçüm: dakika başına
`(ask_close − bid_close) / orta × 10⁴` bps dağılımı. Spread **modele yazılmaz** — K-094 ile fill
zaten bar bar gerçek `bid_open`/`ask_open`dan olur; buradaki dağılım kanıt ve kıyas içindir (iki
kez sayım yok).

**Rollover penceresi ayrı raporlanır** (K-088: kısa saatler NY 17:00'de yığılı, spread orada
genişler): seans takviminin yerel kapanış saatine ±`ROLLOVER_PENCERE_DK` dakika. Slippage tek
sayısına gizlenmez; pencere içi/dışı ayrı dağılım verilir.

**Kaynak notu (FXCM MarketData README, 2026-09-21):** "Data points are indicative and based on the
lowest spreads available exclusively on Active Trader accounts" — yani ölçülen spread **Active
Trader** kotasyonudur ve o hesap tipi komisyonludur (`fee_taker_bps` 0 değil; `FEE_KAYNAGI`).
Standart hesabın daha geniş spread'i bu veride **yok**; model yalnız Active Trader koşulları için
geçerlidir ve bunu kayda yazar.

Veri: `_gelen/<PAIR>/<yıl>-<hafta>.csv.gz` (haftalık M1, `fx.m1_oku` sözleşmesiyle). Boşluk
(eksik dakika, hafta sonu) sonrası dakika `gap` bayraklı → `kalibre_et` o hareketi atar.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from scryne_quant.common.hash import dosya_hash
from scryne_quant.common.zaman import utc_str
from scryne_quant.data import fx as fx_mod
from scryne_quant.data.kalibrasyon import (
    PERSENTILLER,
    VARSAYILAN_PERSENTIL,
    KalibrasyonSonucu,
    kalibre_et,
)
from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.data.takvim import TAKVIM_FX_5X24, Takvim, takvim

#: Rollover penceresi: yerel seans kapanış saatinin ±15 dakikası (NY 16:45–17:15).
ROLLOVER_PENCERE_DK: Final = 15

#: Çiftler arası fark eşiği (venue modeli kararı): p75 slippage'ların max/min oranı bu değerin
#: altındaysa tek `fxcm-fx` modeli, değilse çift başına. Ölçümden **önce** yazıldı (K-039 ruhu).
VENUE_ORAN_ESIGI: Final = 1.5

FEE_KAYNAGI: Final = (
    "FXCM Active Trader (UK): '£2.00 per side per 100K traded volume for monthly volumes above "
    "50 million' (https://www.fxcm.com/uk/accounts/active-trader/, okundu 2026-09-21); "
    "MarketData README: veri 'lowest spreads available exclusively on Active Trader accounts' "
    "(https://raw.githubusercontent.com/fxcm/MarketData/master/README.md, okundu 2026-09-21). "
    "Koşul: aylık ≥ 50M hacim ve ≥ £25.000 özkaynak; altında standart hesap = komisyonsuz ama "
    "daha geniş spread (bu veride yok, ölçülmedi)."
)
#: £2 / 100K taban birim → bps: `0.2 × GBPUSD / (quote USD ise çift fiyatı, taban USD ise 1)`.
_FEE_GBP_PER_100K: Final = 2.0


class FxKalibrasyonHatasi(ValueError):
    """M1 dosyası yok, boş ya da sözleşme dışı."""


# ------------------------------------------------------------------ M1 çerçevesi


def m1_cerceve(depo: fx_mod.FxDepo, pair: str) -> tuple[pd.DataFrame, dict[str, str]]:
    """Depodaki tüm haftalık M1 dosyalarını tek çerçevede birleştirir; dosya sha'larını döner.

    Sütunlar: bid/ask OHLC + `open`/`high`/`low`/`close` (orta) + `quality_status` (`ok`; bir
    önceki dakika eksikse `gap` — hafta sonu dahil) + `spread_bps` (kapanışta).
    """
    dizin = depo.kok / fx_mod.GELEN_DIZINI / pair
    dosyalar = sorted(dizin.glob("*.csv.gz"))
    if not dosyalar:
        raise FxKalibrasyonHatasi(f"{pair}: M1 dosyası yok ({dizin})")
    parcalar: list[pd.DataFrame] = []
    shalar: dict[str, str] = {}
    for yol in dosyalar:
        parcalar.append(fx_mod.m1_oku(yol.read_bytes(), ad=yol.name))
        shalar[yol.name] = dosya_hash(yol)
    df = (
        pd.concat(parcalar, ignore_index=True)
        .sort_values("open_time", kind="stable")
        .drop_duplicates("open_time")
        .reset_index(drop=True)
    )
    for a in ("open", "high", "low", "close"):
        df[a] = (df[f"bid_{a}"] + df[f"ask_{a}"]) / 2.0
    zaman = df["open_time"].to_numpy(dtype="int64")
    gap = np.zeros(len(df), dtype=bool)
    gap[1:] = np.diff(zaman) > fx_mod.DAKIKA_MS
    durum = np.where(gap, str(KaliteDurumu.GAP), str(KaliteDurumu.OK))
    df["quality_status"] = pd.Series(durum, dtype="string")
    df["spread_bps"] = (df["ask_close"] - df["bid_close"]) / df["close"] * 10_000
    return df, shalar


# ------------------------------------------------------------------ spread


def _dagilim(x: np.ndarray) -> dict[str, float]:
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {}
    d = {f"p{int(p)}": float(np.percentile(x, p)) for p in PERSENTILLER}
    d["ort"] = float(x.mean())
    d["max"] = float(x.max())
    d["n"] = int(x.size)
    return d


def rollover_penceresi(zamanlar: np.ndarray, tk: Takvim) -> np.ndarray:
    """Yerel seans kapanış saatine ±`ROLLOVER_PENCERE_DK` dakika içindeki damgalar (bool)."""
    if tk.seans is None:
        raise FxKalibrasyonHatasi(f"{tk.kimlik}: seanslı takvim ister")
    yerel = pd.to_datetime(np.asarray(zamanlar, dtype="int64"), unit="ms", utc=True).tz_convert(
        tk.seans.zaman_dilimi
    )
    dakika = (yerel.hour * 60 + yerel.minute).to_numpy()
    kapanis = tk.seans.kapanis_saat * 60
    return np.abs(dakika - kapanis) <= ROLLOVER_PENCERE_DK


def spread_dagilimi(m1: pd.DataFrame, tk: Takvim) -> dict[str, Any]:
    """Spread (bps, kapanış) dağılımı: tümü, rollover penceresi içi, dışı; yerel saat medyanları."""
    s = m1["spread_bps"].to_numpy(dtype="float64")
    pencere = rollover_penceresi(m1["open_time"].to_numpy(), tk)
    yerel = pd.to_datetime(m1["open_time"].to_numpy(dtype="int64"), unit="ms", utc=True).tz_convert(
        tk.seans.zaman_dilimi  # type: ignore[union-attr]
    )
    saat = yerel.hour.to_numpy()
    saatlik = {
        f"{h:02d}": float(np.median(s[saat == h])) for h in range(24) if bool((saat == h).any())
    }
    tum, ici, disi = _dagilim(s), _dagilim(s[pencere]), _dagilim(s[~pencere])
    return {
        "yontem": "(ask_close − bid_close) / orta_close × 10⁴, dakika başına (M1)",
        "tum": tum,
        "rollover_penceresi": {"dakika": ROLLOVER_PENCERE_DK, **ici},
        "rollover_disi": disi,
        "genisleme_orani_p50": (ici["p50"] / disi["p50"]) if ici and disi and disi["p50"] else None,
        "yerel_saat_medyani_bps": saatlik,
    }


# ------------------------------------------------------------------ kalibrasyon


def fx_kalibre(
    depo: fx_mod.FxDepo,
    pair: str,
    *,
    persentil: float = VARSAYILAN_PERSENTIL,
    takvim_id: str = TAKVIM_FX_5X24,
    baslangic_ms: int | None = None,
    bitis_ms: int | None = None,
) -> dict[str, Any]:
    """Bir çift için spread dağılımı + slippage kalibrasyonu (kripto `kalibre_et`); rapor."""
    tk = takvim(takvim_id)
    m1, shalar = m1_cerceve(depo, pair)
    if baslangic_ms is not None:
        m1 = m1[m1["open_time"] >= baslangic_ms]
    if bitis_ms is not None:
        m1 = m1[m1["open_time"] < bitis_ms]
    m1 = m1.reset_index(drop=True)
    if m1.empty:
        raise FxKalibrasyonHatasi(f"{pair}: pencerede M1 satırı yok")
    slip: KalibrasyonSonucu = kalibre_et(m1, sembol=pair, timeframe="1m", persentil=persentil)
    pencere = rollover_penceresi(m1["open_time"].to_numpy(), tk)
    # Slippage'ın rollover penceresindeki hâli de ayrı: tek sayıya gizlenmesin (talimat).
    ici = (
        kalibre_et(m1[pencere], sembol=pair, timeframe="1m", persentil=persentil)
        if pencere.sum() > 1
        else None
    )
    return {
        "pair": pair,
        "takvim": {"kimlik": tk.kimlik, "icerik_hash": tk.icerik_hash},
        "m1": {
            "satir": int(len(m1)),
            "ilk": utc_str(int(m1["open_time"].iloc[0])),
            "son": utc_str(int(m1["open_time"].iloc[-1])),
            "gap_dakika": int((m1["quality_status"] == "gap").sum()),
            "dosya_sha256": shalar,
        },
        "spread": spread_dagilimi(m1, tk),
        "slippage": slip.sozluk(),
        "slippage_rollover_penceresi": None if ici is None else ici.sozluk()["dagilim_bps"],
    }


def fee_bps(gbpusd_orta: float, cift_fiyati: float, quote_usd: bool) -> float:
    """£2 / 100K taban → quote bps; K-007: iki ondalığa **yukarı** yuvarlanır.

    Quote USD olan çiftte (EURUSD, GBPUSD) notional = 100K × fiyat USD; taban USD olan çiftte
    (USDJPY) notional = 100K USD (JPY'ye çevirince oran değişmez).
    """
    fee_usd = _FEE_GBP_PER_100K * gbpusd_orta
    notional_usd = 100_000.0 * (cift_fiyati if quote_usd else 1.0)
    ham = fee_usd / notional_usd * 10_000
    return float(np.ceil(ham * 100) / 100)


def venue_karari(p75: dict[str, float]) -> dict[str, Any]:
    """Çiftler arası p75 slippage oranı `VENUE_ORAN_ESIGI` altındaysa tek venue modeli."""
    if not p75:
        raise FxKalibrasyonHatasi("karar için ölçüm yok")
    en_kucuk, en_buyuk = min(p75.values()), max(p75.values())
    oran = (en_buyuk / en_kucuk) if en_kucuk > 0 else float("inf")
    return {
        "p75_bps": dict(sorted(p75.items())),
        "oran": oran,
        "esik": VENUE_ORAN_ESIGI,
        "model": "fxcm-fx" if oran < VENUE_ORAN_ESIGI else "cift-basi",
    }


# ------------------------------------------------------------------ finansman proxy (K-098/2)


def finansman_proxy_bps(
    taban_orani: tuple[float, float], quote_orani: tuple[float, float]
) -> tuple[float, float]:
    """Faiz farkından uzun pozisyonun günlük bedeli (bps/gün): `(ham, taban_uygulanmis)`.

    Uzun pozisyon taban parayı tutar (faiz **alır**), quote parayı borçlanır (faiz **öder**).
    `(alt, üst)` yıllık % aralıkları; K-007 aleyhte: alınan faiz aralığın **altı**, ödenen faiz
    aralığın **üstü**. `ham = (quote_üst − taban_alt) / 365 × 100` bps/gün (pozitif = bedel,
    negatif = carry lehte). Taban: `max(ham, 0)` — K-095/1 (`uzun_gunluk_bps ≥ 0`, K-007: lehte
    carry modellenmez); ham değer kayda girer, sessizce kaybolmaz. Broker marjı **yok** (bilinmiyor,
    uydurulmaz) — bu yüzden proxy bedeli gerçek brokerınkinden düşük olabilir; `tur="proxy"`.
    """
    ham = (quote_orani[1] - taban_orani[0]) / 365.0 * 100.0
    return float(ham), float(max(ham, 0.0))


def gun_ms(gun: dt.date) -> int:
    return int(dt.datetime.combine(gun, dt.time(), tzinfo=dt.UTC).timestamp() * 1000)


def yol_yaz(yol: Path, govde: dict[str, Any]) -> Path:
    import json

    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(
        json.dumps(govde, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    return yol


__all__ = [
    "FEE_KAYNAGI",
    "ROLLOVER_PENCERE_DK",
    "VENUE_ORAN_ESIGI",
    "FxKalibrasyonHatasi",
    "fee_bps",
    "finansman_proxy_bps",
    "fx_kalibre",
    "gun_ms",
    "m1_cerceve",
    "rollover_penceresi",
    "spread_dagilimi",
    "venue_karari",
    "yol_yaz",
]
