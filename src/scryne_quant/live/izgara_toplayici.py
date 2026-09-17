"""Izgara barı toplayıcı: çok sembollü canlı akıştan "t barı işlenmeye hazır" kararı. (Faz 14)

Backtest'te `t` barı için bütün sembollerin barları aynı anda eldedir. Canlıda her sembolün
kapanmış barı ayrı bir mesajla, farklı gecikmeyle gelir; bazıları hiç gelmez (işlem
durdurulmuş, delist, kopma). Bu modül aradaki farkı tek bir kurala bağlar
(`docs/Faz-14-Coklu-Paper-Tasarim.md` §2):

- `t` barı, **beklenen** sembollerin (`t` anındaki üyeler ∪ açık pozisyonlar) hepsinin `t`
  barı geldiğinde **ya da** `t` barının kapanışından `bekleme_ms` sonra hazırdır.
- O ana kadar barı gelmeyen sembol `t`de **mevcut değildir**: karar yok, fill yok (K-028).
  Yeni bir kalite bayrağı gerekmez; ızgarada `listelenmedi` ile aynı muamele.
- `t` teslim edildikten sonra gelen `t` barı **geç bardır**: geçmiş kararı değiştirmez, olay
  olarak kaydedilir ve sayılır. Bu, canlının backtest'ten bilinçli tek farkı.
- Hazır barlar **sırayla** teslim edilir; `t+1`, `t` teslim edilmeden teslim edilmez.

Saf sınıf: ağ yok, saat dışarıdan verilir (`simdi_ms`). Testler zamanı elle ilerletir.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Final

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.live.akis import AkisHatasi, Bar

#: Önerilen bekleme: kapanıştan 120 s sonra eksik semboller mevcut değil sayılır. Binance
#: kline kapanış mesajları normalde kapanıştan sonraki ilk saniyelerde geliyor; 120 s,
#: yavaş bir sembolü düşürmeyecek kadar geniş, kararı saatin ortasına kaydırmayacak kadar dar.
VARSAYILAN_BEKLEME_MS: Final = 120_000


class ToplayiciHatasi(AkisHatasi):
    """Toplayıcı sözleşmesi ihlal edildi."""


@dataclass(frozen=True, slots=True)
class IzgaraBari:
    """Teslim edilen ızgara barı: `t` ve o ana kadar gelen semboller."""

    open_time: int
    barlar: dict[str, Bar]
    eksik: tuple[str, ...]
    """Beklenen ama bekleme süresinde gelmeyen semboller."""

    zaman_asimi: bool
    """Teslim, hepsi geldiği için değil süre dolduğu için mi yapıldı."""


@dataclass(frozen=True, slots=True)
class GecBar:
    sembol: str
    open_time: int
    teslim_edilen: int
    """Geldiğinde teslim edilmiş son ızgara barı."""


@dataclass
class IzgaraToplayici:
    timeframe: str
    beklenen: Callable[[int], Iterable[str]]
    """`t` → o barda beklenen semboller (üyeler ∪ açık pozisyonlar)."""

    bekleme_ms: int = VARSAYILAN_BEKLEME_MS
    son_teslim: int | None = None
    """Teslim edilmiş son ızgara barının açılış zamanı (toparlanmada dışarıdan verilir)."""

    gec_barlar: list[GecBar] = field(default_factory=list)
    _bekleyen: dict[int, dict[str, Bar]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._adim = timeframe_ms(self.timeframe)
        if self.bekleme_ms < 0:
            raise ToplayiciHatasi("bekleme negatif olamaz")

    def bar_ekle(self, sembol: str, bar: Bar) -> GecBar | None:
        """Bir sembolün kapanmış barını ekler. Geç bar ise kaydeder ve döndürür."""
        if not bar.hizali_mi(self.timeframe):
            raise ToplayiciHatasi(f"{sembol}: ızgaraya hizasız bar {bar.open_time}")
        if self.son_teslim is not None and bar.open_time <= self.son_teslim:
            gec = GecBar(sembol, bar.open_time, self.son_teslim)
            self.gec_barlar.append(gec)
            return gec
        self._bekleyen.setdefault(bar.open_time, {})[sembol] = bar
        return None

    def hazir(self, simdi_ms: int) -> list[IzgaraBari]:
        """Teslim edilebilecek ızgara barları, sırayla.

        Sıradaki `t` = son teslimden bir adım sonrası (ilk teslimde bekleyenlerin en küçüğü).
        `t` hazır değilse sonraki barlar da beklenir: sıra atlanmaz.
        """
        cikti: list[IzgaraBari] = []
        while True:
            if self.son_teslim is None:
                if not self._bekleyen:
                    return cikti
                t = min(self._bekleyen)
            else:
                t = self.son_teslim + self._adim
            beklenen = tuple(sorted(set(self.beklenen(t))))
            gelen = self._bekleyen.get(t, {})
            eksik = tuple(s for s in beklenen if s not in gelen)
            kapanis = t + self._adim
            sure_doldu = simdi_ms >= kapanis + self.bekleme_ms
            if eksik and not sure_doldu:
                return cikti
            if not beklenen and not gelen and not sure_doldu:
                return cikti
            # Kapanışı gelmemiş bir bar asla teslim edilmez (K-004: karar kapanmış barda).
            if simdi_ms < kapanis:
                return cikti
            self._bekleyen.pop(t, None)
            self.son_teslim = t
            cikti.append(IzgaraBari(t, dict(gelen), eksik, bool(eksik)))


__all__ = [
    "VARSAYILAN_BEKLEME_MS",
    "GecBar",
    "IzgaraBari",
    "IzgaraToplayici",
    "ToplayiciHatasi",
]
