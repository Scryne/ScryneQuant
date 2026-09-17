"""Canlı evren üyeliği: hangi barda hangi ayın üye listesi geçerli? (Faz 14, K-052/3)

Backtest'te `t` barının üyeliği `t`nin ayının PIT tablosundan gelir ve tablo baştan bellidir.
Canlıda M ayının tablosu ancak M−1'in son gününün arşiv dosyası yayımlanınca kurulabilir
(`data.binance.vision` günlük dosyaları ertesi gün gelir). Arada birkaç saatlik bir boşluk
vardır ve bu modül o boşluğun tek kuralını taşır:

- `t`nin ayının tablosu biliniyorsa üyelik o tablodan.
- Bilinmiyorsa **bilinen en son ayın** listesi kullanılır ve `gecikme` işaretlenir. Eski bilgi
  kullanmak geleceği görmek değildir (K-052/3); M'nin listesini M kurulmadan kullanmak olurdu.
- Hiç tablo yoksa üye yok: karar yok (engelleyici yön, K-037).

Tablo **yazılmaz**, burada yalnızca okunur; hesap `data/evren.py:tablo_kur` (araştırma tablosuyla
aynı fonksiyon). Hangi ayın listesinin hangi bardan itibaren uygulandığı koşu kaydına girer ki
toparlanma aynı üyeliği yeniden üretebilsin (K-038).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from scryne_quant.common.hash import nesne_hash


class CanliEvrenHatasi(ValueError):
    """Canlı evren girdisi geçersiz."""


def ay_metni(ms: int) -> str:
    return str(np.datetime64(int(ms), "ms").astype("datetime64[M]"))


@dataclass(frozen=True, slots=True)
class AyUyeligi:
    ay: str
    semboller: tuple[str, ...]
    tablo_hash: str

    def sozluk(self) -> dict[str, Any]:
        return {"ay": self.ay, "semboller": list(self.semboller), "tablo_hash": self.tablo_hash}


def tablodan(tablo: pd.DataFrame, ay: str, tablo_hash: str) -> AyUyeligi:
    """PIT evren tablosundan bir ayın üyeliği. Tabloda o ay yoksa hata (sessiz boş liste değil)."""
    satirlar = tablo[tablo["ay"].astype(str) == ay]
    if satirlar.empty:
        raise CanliEvrenHatasi(f"evren tablosunda {ay} ayı yok")
    return AyUyeligi(ay, tuple(sorted(satirlar["sembol"].astype(str))), tablo_hash)


@dataclass
class UyelikTakvimi:
    aylar: dict[str, AyUyeligi] = field(default_factory=dict)

    def ekle(self, uyelik: AyUyeligi) -> None:
        onceki = self.aylar.get(uyelik.ay)
        if onceki is not None and onceki != uyelik:
            raise CanliEvrenHatasi(
                f"{uyelik.ay} için farklı bir üyelik zaten kayıtlı (tablo "
                f"{onceki.tablo_hash[:12]} ≠ {uyelik.tablo_hash[:12]}): aynı ay iki listeyle "
                "işlenemez"
            )
        self.aylar[uyelik.ay] = uyelik

    def uyeler(self, t_ms: int) -> tuple[tuple[str, ...], str | None, bool]:
        """`(semboller, kullanılan ay, gecikme)`."""
        ay = ay_metni(t_ms)
        if ay in self.aylar:
            return self.aylar[ay].semboller, ay, False
        onceki = sorted(a for a in self.aylar if a < ay)
        if not onceki:
            return (), None, True
        return self.aylar[onceki[-1]].semboller, onceki[-1], True

    def dizileri(
        self, zamanlar: Sequence[int] | np.ndarray, semboller: Iterable[str]
    ) -> dict[str, np.ndarray]:
        """Görünüm için sembol başına bar üyelik dizisi."""
        zamanlar = np.asarray(zamanlar, dtype="int64")
        semboller = tuple(semboller)
        cikti = {s: np.zeros(len(zamanlar), dtype=bool) for s in semboller}
        onbellek: dict[str, frozenset[str]] = {}
        for i, t in enumerate(zamanlar):
            ay = ay_metni(int(t))
            if ay not in onbellek:
                onbellek[ay] = frozenset(self.uyeler(int(t))[0])
            uye = onbellek[ay]
            for s in semboller:
                if s in uye:
                    cikti[s][i] = True
        return cikti

    def kimlik(self) -> str:
        return nesne_hash({a: u.sozluk() for a, u in sorted(self.aylar.items())})

    @classmethod
    def sozlukten(cls, veri: Mapping[str, Mapping[str, Any]]) -> UyelikTakvimi:
        return cls({a: AyUyeligi(a, tuple(v["semboller"]), str(v["tablo_hash"]))
                    for a, v in veri.items()})

    def sozluk(self) -> dict[str, Any]:
        return {a: u.sozluk() for a, u in sorted(self.aylar.items())}


__all__ = ["AyUyeligi", "CanliEvrenHatasi", "UyelikTakvimi", "ay_metni", "tablodan"]
