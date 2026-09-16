"""Evren `ctx`i: `t` anında **hangi enstrümanlar var** ve her biri nasıl görünüyor. (K-052/3)

`Baglam` tek bir enstrümanı `t`de keser. `EvrenBaglam` iki şeyi birden keser:

1. **Zamanı** — her enstrümanın serisi `t`de kesik (`Baglam`ın işi, aynen devralınıyor).
2. **Evreni** — `t` anında listelenmiş ve evren kuralını *yalnızca `t`ye kadarki veriyle*
   sağlayan enstrümanlar görünür. Bugünkü listeden kurulan bir evren, Spike 6'nın ölçtüğü
   gibi her ayın likit isimlerinin medyan %18'ini — sonradan başarısız olanları — atar
   (Faz 9'da yeniden ölçüldü: %16,7). Bu bir istatistik detayı değil, **look-ahead'in
   ikinci biçimi**: fiyat geleceğini değil, *hayatta kalma* geleceğini görmek.

**Üyelik hesabı burada yapılmaz, hazır gelir** (K-003). Evren kuralı bir veri sorgusudur
(aylık hacim toplamı, listeleme durumu); stratejinin içinde olamaz. `data/evren.py` PIT
tabloyu üretir, `uyelik_matrisi` onu bar ızgarasına çevirir, bu modül yalnızca **okur**.

## Görünürlük üyelikten biraz geniştir ve bunun sebebi bir look-ahead değil

`uyeler()` `t`deki evren üyeleridir. `enstruman(sembol)` ise üyelere **ek olarak** açık
pozisyon taşınan sembollere de izin verir. Gerekçe: evrenden çıkan bir enstrümanı
göremeyen strateji, elindeki pozisyonu kapatmak için `FLAT` bile diyemez — yani evren
kuralı sessizce "sonsuza kadar tut" emrine dönüşürdü. Zaten sahip olduğun bir şeyi görmek
gelecek bilgisi değildir; onu **seçmek** gelecek bilgisi olurdu ve o kapı kapalı:
`uyeler()` yalnızca üyeleri döndürür.

## Listelenmemiş bar

Enstrümanların geçmişleri farklı tarihlerde başlar ve kimi delist edilir. Ortak ızgaraya
oturtmak için var olmayan barlar `LISTELENMEDI` kalite bayrağıyla doldurulur. Bu bayrağın
`quality_status` alanında yaşaması bilinçli: motorun **her** kod yolu zaten "`ok` değilse
ne karar ver ne doldur" diyor (K-028), yani varlık yokluğu ayrı bir kontrol istemiyor.
`ok` olmayan bar oranı sayılırken bu barlar ayrı tutulur — yoksa 700 sembollü bir koşuda
veri kalitesi uyarısı (K-006) her zaman tetiklenirdi.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

import numpy as np

from scryne_quant.strategy.baglam import DUZ, Baglam, PiyasaGorunumu, PozisyonDurumu

#: Karar verilebilecek bar. `data.semalar.KaliteDurumu.OK` ile aynı değer; oradan import
#: **edilmiyor** çünkü `data/` strateji katmanının izin listesinde yok (K-027) ve o listeyi
#: bir sabit için genişletmek, izolasyon testinin anlamını bir sabit kadar zayıflatırdı.
#: `tests/unit/test_evren.py` ikisinin aynı kaldığını kontrol ediyor.
KARAR_VERILEBILIR: Final = "ok"

#: Ortak ızgaraya doldurma amaçlı eklenmiş, **gerçekte var olmayan** bar. `KaliteDurumu`
#: enum'una eklenmedi: orası indirilen bir barın doğrulama durumunu anlatır, bu ise barın
#: var olup olmadığını. İkisini aynı listede toplamak, indiricinin alanına ait olmayan bir
#: değeri oraya sızdırırdı.
LISTELENMEDI: Final = "listelenmedi"


class EvrenDisi(LookupError):
    """Strateji `t` anında görünmeyen bir enstrümanı istedi. K-052/3'ün ihlali."""


class EvrenSozlesmesi(ValueError):
    """Evren görünümü tutarsız kuruldu."""


def _salt_okunur(dizi: np.ndarray) -> np.ndarray:
    if dizi.flags.writeable:
        dizi = dizi.view()
        dizi.flags.writeable = False
    return dizi


@dataclass(frozen=True, slots=True)
class EvrenGorunumu:
    """Ortak zaman ızgarası + enstrüman başına `PiyasaGorunumu` + PIT üyelik matrisi.

    Her enstrümanın görünümü **aynı uzunlukta ve aynı ızgarada**. Farklı uzunluklarda
    tutup indeksleri eşlemek de mümkündü; ortak ızgara seçildi çünkü indeks eşlemesi
    yapılan her yer, bir gün yanlış enstrümanın barına bakma ihtimali taşır — ve o hata
    çökme değil, "biraz farklı" bir sonuç üretir.
    """

    timeframe: str
    zamanlar: np.ndarray
    """Ortak bar açılış zamanları (UTC epoch ms, K-005), artan."""

    gorunumler: Mapping[str, PiyasaGorunumu]
    uyelik: Mapping[str, np.ndarray]
    """Sembol → bool dizi. `True` = bu barda evren üyesi (PIT)."""

    kural_kimligi: str = ""
    """`EvrenKurali.kimlik()` — üyeliği üreten kuralın hash'i. Kayda ve hipoteze girer."""

    def __post_init__(self) -> None:
        if len(self.zamanlar) == 0:
            raise EvrenSozlesmesi("boş zaman ızgarası")
        zamanlar = np.asarray(self.zamanlar, dtype="int64")
        if (np.diff(zamanlar) <= 0).any():
            raise EvrenSozlesmesi("zaman ızgarası kesin artan olmalı")
        if not self.gorunumler:
            raise EvrenSozlesmesi("en az bir enstrüman gerekir")

        n = len(zamanlar)
        if set(self.uyelik) != set(self.gorunumler):
            raise EvrenSozlesmesi(
                "her enstrümanın bir üyelik dizisi olmalı; eksik üyeliği 'hep üye' saymak, "
                "evren kuralını sessizce kaldırmak olurdu"
            )
        uyelik: dict[str, np.ndarray] = {}
        for sembol in sorted(self.gorunumler):
            gorunum = self.gorunumler[sembol]
            if len(gorunum) != n:
                raise EvrenSozlesmesi(
                    f"{sembol}: {len(gorunum)} bar, ızgarada {n} bar var"
                )
            if gorunum.timeframe != self.timeframe:
                raise EvrenSozlesmesi(
                    f"{sembol}: timeframe {gorunum.timeframe}, evren {self.timeframe}"
                )
            if not np.array_equal(
                np.asarray(gorunum.barlar["open_time"], dtype="int64"), zamanlar
            ):
                raise EvrenSozlesmesi(f"{sembol}: bar zamanları ortak ızgaraya oturmuyor")

            u = np.asarray(self.uyelik[sembol], dtype=bool)
            if len(u) != n:
                raise EvrenSozlesmesi(f"{sembol}: üyelik dizisi {len(u)}, ızgara {n}")
            # Var olmayan bir barda üyelik, evrenin veriden daha çok şey bildiğini iddia
            # etmek olurdu. Kırılsın: sessiz geçerse o sembol boş barlarla sıralamaya girer.
            yok = np.asarray(gorunum.barlar["quality_status"], dtype=object) == LISTELENMEDI
            if bool((u & yok).any()):
                raise EvrenSozlesmesi(
                    f"{sembol}: listelenmemiş barda evren üyeliği var "
                    f"({int((u & yok).sum())} bar)"
                )
            uyelik[sembol] = _salt_okunur(u)

        object.__setattr__(self, "zamanlar", _salt_okunur(zamanlar))
        object.__setattr__(
            self, "gorunumler", MappingProxyType(dict(sorted(self.gorunumler.items())))
        )
        object.__setattr__(self, "uyelik", MappingProxyType(uyelik))

    def __len__(self) -> int:
        return len(self.zamanlar)

    @property
    def semboller(self) -> tuple[str, ...]:
        """Görünümdeki tüm enstrümanlar, sıralı. Üyelik ayrı bir soru."""
        return tuple(self.gorunumler)

    def mevcut(self, sembol: str, i: int) -> bool:
        """`i`. barda bu enstrümanın gerçek bir barı var mı (doldurma değil)?"""
        return str(self.gorunumler[sembol].barlar["quality_status"][i]) != LISTELENMEDI

    def karar_verilebilir(self, sembol: str, i: int) -> bool:
        """`i`. barda bu enstrümanda karar verilebilir mi — yani barı `ok` mu? (K-028)"""
        return str(self.gorunumler[sembol].barlar["quality_status"][i]) == KARAR_VERILEBILIR

    def baglam(
        self,
        i: int,
        pozisyonlar: Mapping[str, PozisyonDurumu] | None = None,
        nakit_agirligi: float = 1.0,
        parametreler: Mapping[str, Any] | None = None,
    ) -> EvrenBaglam:
        """`i`. barda kesilmiş evren `ctx`i."""
        if not 0 <= i < len(self):
            raise IndexError(f"bar indeksi aralık dışı: {i} (0..{len(self) - 1})")
        poz = MappingProxyType(dict(pozisyonlar or {}))
        # Üyelik **ve** karar verilebilirlik. `ok` olmayan bir barda karar verilmez (K-028);
        # bunu `ctx`e gömmek, her stratejinin aynı kontrolü yazmasını beklemekten güvenli:
        # unutulduğunda sonuç çökmez, yalnızca şüpheli bir fiyattan karar verilir.
        uyeler = tuple(
            s
            for s in self.gorunumler
            if bool(self.uyelik[s][i]) and self.karar_verilebilir(s, i)
        )
        return EvrenBaglam(
            self,
            i,
            uyeler,
            poz,
            nakit_agirligi,
            MappingProxyType(dict(parametreler or {})),
        )

    def akis(
        self,
        parametreler: Mapping[str, Any] | None = None,
        baslangic: int = 0,
    ) -> Iterator[EvrenBaglam]:
        """Barları sırayla dolaşan pozisyonsuz evren `ctx` üreteci (look-ahead testi için)."""
        donmus = MappingProxyType(dict(parametreler or {}))
        for i in range(baslangic, len(self)):
            yield self.baglam(i, parametreler=donmus)


@dataclass(frozen=True, slots=True)
class EvrenBaglam:
    """`t` anında kesilmiş evren görünümü. Çok enstrümanlı stratejiye verilen `ctx` budur."""

    _gorunum: EvrenGorunumu
    _i: int
    _uyeler: tuple[str, ...]
    pozisyonlar: Mapping[str, PozisyonDurumu]
    nakit_agirligi: float
    parametreler: Mapping[str, Any]

    # ------------------------------------------------------------- kimlik

    @property
    def timeframe(self) -> str:
        return self._gorunum.timeframe

    @property
    def zaman(self) -> int:
        """`t` barının **açılış** zamanı (UTC epoch ms, K-005)."""
        return int(self._gorunum.zamanlar[self._i])

    @property
    def uzunluk(self) -> int:
        """Şu ana kadar görülen bar sayısı (`t` dahil). Mutlak indeks verilmez (K-002)."""
        return self._i + 1

    @property
    def kural_kimligi(self) -> str:
        return self._gorunum.kural_kimligi

    # ------------------------------------------------------------- evren

    def uyeler(self) -> tuple[str, ...]:
        """`t` anındaki evren üyeleri, sembole göre sıralı.

        Sıralı olması sözleşmenin parçası: strateji "ilk N"i seçerken sıralamayı kendi
        yapar, ama eşitlik durumunda hangi sembolün önce geldiği burada belirlenir ve
        çağrıdan çağrıya değişmez.
        """
        return self._uyeler

    def uye_mi(self, sembol: str) -> bool:
        return sembol in self._uyeler

    def gorunur(self) -> tuple[str, ...]:
        """Üyeler + barı olan açık pozisyonlar. `enstruman()`ın kabul ettiği küme."""
        ek = tuple(
            s
            for s in sorted(self.pozisyonlar)
            if s not in self._uyeler
            and self.pozisyonlar[s].acik
            and s in self._gorunum.gorunumler
            and self._gorunum.karar_verilebilir(s, self._i)
        )
        return tuple(sorted((*self._uyeler, *ek)))

    def enstruman(self, sembol: str) -> Baglam:
        """Bu enstrümanın `t`de kesilmiş `ctx`i. Görünmüyorsa `EvrenDisi`.

        Hata fırlatmak, `None` döndürmekten farklı bir karar: `None` "yok" diye sessizce
        atlanabilirdi ve strateji evren dışı bir sembolü sorup sorduğunu fark etmezdi.
        """
        if sembol not in self._gorunum.gorunumler:
            raise EvrenDisi(f"{sembol}: bu evren görünümünde yok")
        if sembol not in self.gorunur():
            raise EvrenDisi(
                f"{sembol}: `t`={self.zaman} anında evren üyesi değil ve açık pozisyon yok "
                "(K-052/3). Bugünkü listeden kurulan bir evren hayatta kalma yanlılığıdır."
            )
        return self._gorunum.gorunumler[sembol].baglam(
            self._i, self.pozisyon(sembol), self.parametreler
        )

    # ------------------------------------------------------------- portföy

    def pozisyon(self, sembol: str) -> PozisyonDurumu:
        return self.pozisyonlar.get(sembol, DUZ)

    def acik_pozisyonlar(self) -> tuple[str, ...]:
        return tuple(s for s in sorted(self.pozisyonlar) if self.pozisyonlar[s].acik)

    @property
    def brut_maruziyet(self) -> float:
        """Nakit dışı kesir. `1 − nakit_agirligi`; nakit bir pozisyondur (§12)."""
        return 1.0 - self.nakit_agirligi


__all__ = [
    "KARAR_VERILEBILIR",
    "LISTELENMEDI",
    "EvrenBaglam",
    "EvrenDisi",
    "EvrenGorunumu",
    "EvrenSozlesmesi",
]
