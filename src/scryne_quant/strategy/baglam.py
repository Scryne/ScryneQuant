"""`ctx` sözleşmesi: stratejinin dünyaya bakabildiği **tek** pencere. (K-002, K-003)

Tasarımın tek amacı geleceği **ifade edilemez** kılmak. Bunun için indeks yönü ters
çevrildi: strateji mutlak indeksle değil, "kaç bar geriye" ile okur.

    ctx.bar("close")      # t barının kapanışı
    ctx.bar("close", 1)   # bir önceki bar
    ctx.bar("close", -1)  # GelecekErisimi

Mutlak indeks verilebilseydi `t+1` yazmak mümkün — dolayısıyla er ya da geç kaçınılmaz —
olurdu. Ters indekste geleceğe karşılık gelen bir sayı yok: negatif indeks bir *hata*,
bir *seçenek* değil. K-002 "ihlal denemesi hata fırlatır" diyor; fırlatan yer burası.

Bu, look-ahead'e karşı üç savunmanın **birincisi**. Diğer ikisi:
- İndikatörlerin nedenselliği (`features/indikator.py`), her biri ayrıca test edilir.
- Bozulmuş-gelecek testi: `t` sonrası veri bozulduğunda sinyal dizisi bit düzeyinde
  değişmez (`tests/unit/test_look_ahead.py`). Sözleşmeye değil, sonuca bakan tek test bu.

**Bu modül numpy dışında hiçbir şey import etmez** (K-003): pandas, pyarrow, pathlib —
hiçbiri. Böylece strateji katmanının dolaylı bir I/O yüzeyi kalmıyor.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

import numpy as np


class GelecekErisimi(LookupError):
    """Strateji `t`'den sonrasını istedi. K-002'nin ihlali; sessizce geçilmez."""


class GecmisYok(LookupError):
    """Strateji serinin başlangıcından öncesini istedi (ısınma tamamlanmamış)."""


class BilinmeyenAlan(KeyError):
    """İstenen bar alanı ya da özellik `ctx`'te yok."""


#: `ctx.bar(...)` ile okunabilen sayısal bar alanları. `quality_status` ayrı bir
#: erişimcide: string döndürür ve float sözleşmesini bozar.
BAR_ALANLARI: Final[tuple[str, ...]] = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trades",
)


@dataclass(frozen=True, slots=True)
class PozisyonDurumu:
    """Stratejinin gördüğü pozisyon. Salt-okunur; strateji buradan hiçbir şey değiştiremez.

    Faz 2'de her zaman düz (flat) verilir — portföy simülasyonu Faz 3'ün işi. Alanlar
    şimdiden burada çünkü `ctx`'in şekli sonradan genişletilirse Faz 2'de yazılan her
    strateji yeniden gözden geçirilmek zorunda kalır.
    """

    miktar: float = 0.0
    """Elde tutulan baz varlık miktarı (BTC). Spot v1: negatif olamaz."""

    ortalama_maliyet: float = 0.0
    """Ortalama giriş fiyatı (quote birimi). Pozisyon yoksa 0."""

    exposure: float = 0.0
    """Portföyün bu sembolde olan kesri [0,1] — `Sinyal.target_exposure` ile aynı ölçek."""

    giris_ms: int | None = None
    """İlk girişin bar açılış zamanı (UTC epoch ms). Tutma süresi hesabı buna bakar."""

    @property
    def acik(self) -> bool:
        return self.miktar > 0.0


#: Pozisyonsuz durum. Tek bir örnek paylaşılıyor — nesne değişmez olduğu için güvenli.
DUZ: Final[PozisyonDurumu] = PozisyonDurumu()


def _salt_okunur(dizi: np.ndarray) -> np.ndarray:
    if dizi.flags.writeable:
        dizi = dizi.view()
        dizi.flags.writeable = False
    return dizi


@dataclass(frozen=True, slots=True)
class PiyasaGorunumu:
    """Bar dizileri + hesaplanmış özellikler; tüm seri, tek yerde.

    Bir kez kurulur ve backtest boyunca paylaşılır. `Baglam` bunun üzerine bir **kesme
    noktası** koyar; kesme noktasını taşımak yeni bir `Baglam` üretmekle olur, mevcut
    olanı değiştirmekle değil — strateji elinde tuttuğu bir ctx'in altından verinin
    kaymadığından emin olabilmeli.
    """

    sembol: str
    timeframe: str
    barlar: Mapping[str, np.ndarray]
    ozellikler: Mapping[str, np.ndarray] = field(default_factory=dict)

    def __post_init__(self) -> None:
        eksik = [
            a for a in (*BAR_ALANLARI, "open_time", "quality_status") if a not in self.barlar
        ]
        if eksik:
            raise BilinmeyenAlan(f"bar dizilerinde eksik alan(lar): {', '.join(eksik)}")

        n = len(self.barlar["open_time"])
        if n == 0:
            raise ValueError("boş piyasa görünümü")
        for ad, dizi in (*self.barlar.items(), *self.ozellikler.items()):
            if len(dizi) != n:
                raise ValueError(f"{ad}: uzunluk {len(dizi)}, beklenen {n}")

        cakisan = set(self.barlar) & set(self.ozellikler)
        if cakisan:
            raise ValueError(f"özellik adı bar alanıyla çakışıyor: {', '.join(sorted(cakisan))}")

        object.__setattr__(
            self, "barlar", MappingProxyType({a: _salt_okunur(d) for a, d in self.barlar.items()})
        )
        object.__setattr__(
            self,
            "ozellikler",
            MappingProxyType({a: _salt_okunur(d) for a, d in self.ozellikler.items()}),
        )

    def __len__(self) -> int:
        return len(self.barlar["open_time"])

    def baglam(
        self,
        i: int,
        pozisyon: PozisyonDurumu = DUZ,
        parametreler: Mapping[str, Any] | None = None,
    ) -> Baglam:
        """`i`. barda kesilmiş bir `ctx` üretir."""
        if not 0 <= i < len(self):
            raise IndexError(f"bar indeksi aralık dışı: {i} (0..{len(self) - 1})")
        return Baglam(self, i, pozisyon, MappingProxyType(dict(parametreler or {})))

    def akis(
        self,
        parametreler: Mapping[str, Any] | None = None,
        baslangic: int = 0,
    ) -> Iterator[Baglam]:
        """Barları sırayla dolaşan `ctx` üreteci.

        Faz 3'ün event loop'u pozisyonu her barda kendisi vereceği için bu üreteç
        pozisyonsuzdur; look-ahead testi ve tek başına strateji denemeleri için var.
        """
        donmus = MappingProxyType(dict(parametreler or {}))
        for i in range(baslangic, len(self)):
            yield Baglam(self, i, DUZ, donmus)


@dataclass(frozen=True, slots=True)
class Baglam:
    """`t` anında kesilmiş, salt-okunur piyasa görünümü. Stratejiye verilen `ctx` budur."""

    _gorunum: PiyasaGorunumu
    _i: int
    pozisyon: PozisyonDurumu
    parametreler: Mapping[str, Any]

    # ------------------------------------------------------------- kimlik

    @property
    def sembol(self) -> str:
        return self._gorunum.sembol

    @property
    def timeframe(self) -> str:
        return self._gorunum.timeframe

    @property
    def zaman(self) -> int:
        """`t` barının **açılış** zamanı, UTC epoch ms (K-005).

        `Sinyal.timestamp` bu değerle doldurulur: sinyal "şu an"a değil, kararın
        verildiği bara aittir.
        """
        return int(self._gorunum.barlar["open_time"][self._i])

    @property
    def uzunluk(self) -> int:
        """Şu ana kadar görülen bar sayısı (`t` dahil).

        Mutlak indeks yerine bu var: strateji ısınmasını `ctx.uzunluk < 50` diye
        kontrol eder, ve elinde geleceğe işaret edebileceği bir sayı olmaz.
        """
        return self._i + 1

    @property
    def kalite(self) -> str:
        """`t` barının kalite bayrağı (K-006). `ok` dışındaysa strateji temkinli olmalı."""
        return str(self._gorunum.barlar["quality_status"][self._i])

    # ---------------------------------------------------------- tekil okuma

    def _indeks(self, geri: int) -> int:
        """Ters indeksi mutlak indekse çevirir; geleceği ve ısınma öncesini reddeder."""
        if not isinstance(geri, int) or isinstance(geri, bool):
            raise TypeError(f"`geri` tamsayı olmalı, verilen: {geri!r}")
        if geri < 0:
            raise GelecekErisimi(
                f"geri={geri}: strateji geleceği göremez (K-002). "
                "`geri` 0 (şu anki bar) veya pozitif olmalı."
            )
        if geri > self._i:
            raise GecmisYok(
                f"geri={geri}: yalnızca {self.uzunluk} bar var. "
                "Isınmayı `ctx.uzunluk` ile kontrol edin."
            )
        return self._i - geri

    def bar(self, alan: str, geri: int = 0) -> float:
        """`geri` bar önceki barın `alan` değeri. `geri=0` şu anki bar."""
        if alan not in BAR_ALANLARI:
            raise BilinmeyenAlan(f"{alan!r}; okunabilir alanlar: {', '.join(BAR_ALANLARI)}")
        return float(self._gorunum.barlar[alan][self._indeks(geri)])

    def ozellik(self, ad: str, geri: int = 0) -> float:
        """`geri` bar önceki özellik değeri. Isınma bölgesinde NaN döner, hata değil.

        NaN'ı hata yapmamak bilinçli: ısınma normal bir durumdur ve her stratejiyi
        `try/except` ile yazdırmak, asıl hataları da yutan bir alışkanlık üretir. Bunun
        yerine `ctx.hazir(...)` ile açıkça sorulur.
        """
        try:
            dizi = self._gorunum.ozellikler[ad]
        except KeyError:
            mevcut = ", ".join(sorted(self._gorunum.ozellikler)) or "yok"
            raise BilinmeyenAlan(f"özellik {ad!r} hesaplanmamış; mevcut: {mevcut}") from None
        return float(dizi[self._indeks(geri)])

    def hazir(self, *adlar: str, geri: int = 0) -> bool:
        """Verilen özelliklerin hepsi bu barda hesaplanmış mı (NaN değil mi)?

        Stratejinin ilk satırı genelde budur: ısınma bitmeden sinyal üretmek, ilk
        birkaç işlemi rastgele yapmak demektir — ve o işlemler backtest metriklerine
        gerçek işlem gibi girer.
        """
        if geri > self._i:
            return False
        return all(not np.isnan(self.ozellik(ad, geri)) for ad in adlar)

    # ----------------------------------------------------------- seri okuma

    def _seri(self, dizi: np.ndarray, uzunluk: int) -> np.ndarray:
        if uzunluk < 1:
            raise ValueError(f"uzunluk en az 1 olmalı: {uzunluk}")
        if uzunluk > self.uzunluk:
            raise GecmisYok(f"{uzunluk} bar istendi, yalnızca {self.uzunluk} bar var")
        # Kopya: dilim döndürmek `.base` üzerinden tüm seriye — yani geleceğe — bir yol
        # bırakırdı. Kopyanın maliyeti, o yolun kapalı olmasının bedeli.
        return np.array(dizi[self._i - uzunluk + 1 : self._i + 1], dtype=np.float64)

    def bar_serisi(self, alan: str, uzunluk: int) -> np.ndarray:
        """Son `uzunluk` barın `alan` değerleri; sonuncusu `t`. Yeni bir dizi döner."""
        if alan not in BAR_ALANLARI:
            raise BilinmeyenAlan(f"{alan!r}; okunabilir alanlar: {', '.join(BAR_ALANLARI)}")
        return self._seri(self._gorunum.barlar[alan], uzunluk)

    def ozellik_serisi(self, ad: str, uzunluk: int) -> np.ndarray:
        """Son `uzunluk` barın özellik değerleri; sonuncusu `t`. Yeni bir dizi döner."""
        try:
            dizi = self._gorunum.ozellikler[ad]
        except KeyError:
            mevcut = ", ".join(sorted(self._gorunum.ozellikler)) or "yok"
            raise BilinmeyenAlan(f"özellik {ad!r} hesaplanmamış; mevcut: {mevcut}") from None
        return self._seri(dizi, uzunluk)
