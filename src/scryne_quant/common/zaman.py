"""Zaman: UTC epoch milisaniye, bar timestamp'i açılış zamanıdır. (K-005)

Bu modül sistemdeki **tek** zaman kaynağıdır. Yerel saat hiçbir yerde iş mantığına
girmez; yalnızca gösterim anında, saat dilimi etiketiyle birlikte kullanılır.

Neden ayrı bir modül: karışık saat dilimi, backtest'te çalışıyor gibi görünen ama canlıda
barları kaydıran hatalar üretir — ve bu hata sınıfı sessizdir, sonuç makul görünmeye devam
eder. Tek bir dönüşüm noktası olması, o sessizliği kırmanın önkoşulu.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

#: Desteklenen timeframe'ler ve milisaniye karşılıkları.
#: Yeni timeframe eklemek buraya yazmakla olur; string parse edilmez.
TIMEFRAME_MS: Final[dict[str, int]] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}

UTC: Final = dt.UTC


class GecersizTimeframe(ValueError):
    """Tanınmayan timeframe. Sessizce varsayılana düşmek yerine hata veriyoruz."""


def timeframe_ms(timeframe: str) -> int:
    """Timeframe'in milisaniye karşılığı.

    >>> timeframe_ms("1h")
    3600000
    """
    try:
        return TIMEFRAME_MS[timeframe]
    except KeyError:
        gecerli = ", ".join(TIMEFRAME_MS)
        raise GecersizTimeframe(f"bilinmeyen timeframe {timeframe!r}; geçerli: {gecerli}") from None


def simdi_ms() -> int:
    """Şu anın UTC epoch milisaniyesi.

    Sistem saatine dayanır. Borsayla karşılaştırmalı iş (imzalı istek, clock drift)
    yapılacaksa bu değil, borsanın `serverTime`'ı esas alınır — Spike 1 yerel saatin
    sunucudan −153 ms geride olduğunu ölçtü.
    """
    return int(dt.datetime.now(UTC).timestamp() * 1000)


def ms_to_datetime(ms: int) -> dt.datetime:
    """Epoch ms → timezone-aware UTC datetime. Naive datetime asla üretilmez."""
    return dt.datetime.fromtimestamp(ms / 1000, UTC)


def datetime_to_ms(moment: dt.datetime) -> int:
    """Timezone-aware datetime → epoch ms.

    Naive datetime reddedilir: "hangi saat dilimi" sorusunu sessizce varsaymak,
    bu modülün engellemek için var olduğu hatanın ta kendisi.
    """
    if moment.tzinfo is None:
        raise ValueError("naive datetime kabul edilmiyor; tzinfo zorunlu (K-005)")
    return int(moment.timestamp() * 1000)


def bar_acilisi(ms: int, timeframe: str) -> int:
    """`ms` anını içeren barın **açılış** timestamp'i.

    Bir barın timestamp'i açılış zamanıdır (K-005). Bu fonksiyon epoch'a hizalı
    kovalara böler — Binance'in kline sınırlarıyla birebir aynı hizalama.
    """
    adim = timeframe_ms(timeframe)
    return (ms // adim) * adim


def bar_kapanisi(acilis_ms: int, timeframe: str) -> int:
    """Barın kapanış anı (dışlayıcı sınır): açılış + timeframe.

    Dikkat: Binance'in `close_time` alanı bundan 1 ms eksiktir (kapsayıcı sınır).
    Karşılaştırma yaparken hangi sınırın kullanıldığı `bar_kapandi_mi`'da tek yerde
    ele alınır.
    """
    return acilis_ms + timeframe_ms(timeframe)


def bar_kapandi_mi(acilis_ms: int, timeframe: str, referans_ms: int) -> bool:
    """Bu bar `referans_ms` anında kapanmış mı?

    **Faz 1'in idempotency kriterinin dayandığı kural.** Spike 1 ölçtü: REST `klines`
    her zaman devam eden barı son eleman olarak döndürüyor ve o bar çağrılar arasında
    değişiyor. Kapanmışlık bayrağı REST'te yok (yalnızca WebSocket akışında), bu yüzden
    tek güvenilir kontrol zaman karşılaştırmasıdır.

    Kapanmamış bar depoya yazılırsa aynı indirme komutu iki kez çalıştırıldığında dosya
    içeriği farklı çıkar — yani idempotency imkânsız hale gelir.

    `referans_ms` borsanın `serverTime`'ı olmalıdır, yerel saat değil.
    """
    return bar_kapanisi(acilis_ms, timeframe) <= referans_ms


def utc_str(ms: int) -> str:
    """Log ve rapor için okunur UTC gösterimi. Saat dilimi etiketi zorunlu (K-005)."""
    return ms_to_datetime(ms).strftime("%Y-%m-%d %H:%M:%S UTC")
