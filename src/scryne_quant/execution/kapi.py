"""Execution kapısı: borsaya giden **tek** kapı. (§9.1/3, K-032)

Mimarinin üçüncü değişmez kuralı: *"Sinyal risk motorunu atlayamaz. Execution'a giden tek
yol onaylanmış intent'tir."* Bu modül o kuralın fiziksel karşılığı — bir fonksiyon, bir
doğrulama, ve başka hiçbir giriş yolu.

**Bu dosya `strategy.sinyal`i import etmiyor ve etmeyecek.** `tests/unit/test_risk_bypass.py`
bunu `ast` ile kontrol ediyor: `execution/` ve `oms/` paketlerinin geçişli import grafiğinde
`strategy.sinyal` görünürse test kırılır. Yani bir `Sinyal`i execution'a sokmak için önce
bu testi kırmak gerekir — ve kırılan test, diff'te görünen bir satırdır.

K-003'ün izolasyon testi "strateji dışarıya erişemez" diyordu; bu onun aynadaki hâli:
"dışarısı stratejiden doğrudan beslenemez". İki testin birlikte kapattığı şey şu döngü:
strateji → (risk motoru) → execution. Parantezi atlamanın statik bir yolu yok.

**Faz 5'te borsa yok.** `gonder` bugün emir üretmiyor; `OnayliNiyet`i doğrulayıp kabul
kaydını döndürüyor. Emir state machine, idempotency key ve gerçek borsa çağrısı Faz 7'nin
işi (§33). Kapının şimdi var olmasının sebebi, Faz 7'nin bir kapı **tasarlamak** zorunda
kalmaması: o faz hazır bir kapının arkasına emir mantığı koyacak, kapıyı açmaya çalışmayacak.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scryne_quant.risk.niyet import OnayliNiyet, dogrula


class ExecutionHatasi(RuntimeError):
    """Execution kapısı bir niyeti kabul etmedi."""


@dataclass(frozen=True, slots=True)
class KabulKaydi:
    """Kapının kabul ettiği niyetin kaydı. Faz 7'de bunun yerine bir `Emir` dönecek."""

    sembol: str
    hedef_maruziyet: float
    karar_ms: int
    limit_kimligi: str
    kisitlayan: tuple[str, ...]

    def sozluk(self) -> dict[str, Any]:
        return {
            "sembol": self.sembol,
            "hedef_maruziyet": self.hedef_maruziyet,
            "karar_ms": self.karar_ms,
            "limit_kimligi": self.limit_kimligi,
            "kisitlayan": list(self.kisitlayan),
        }


def gonder(niyet: OnayliNiyet) -> KabulKaydi:
    """Onaylı niyeti execution'a alır. Mührü geçersizse hiçbir şey yapmaz.

    Doğrulama **burada** tekrar yapılıyor, onay anına güvenilmiyor. Sebebi: niyetin
    üretildiği an ile borsaya gittiği an arasında kod çalışıyor, ve o kodun niyete
    dokunmadığını varsaymak bir güvenlik sınırını varsayıma dayandırmak olurdu. Mühür
    içeriğin HMAC'i olduğu için, aradaki herhangi bir değişiklik burada yakalanır.
    """
    onayli = dogrula(niyet)
    return KabulKaydi(
        sembol=onayli.sinyal.symbol,
        hedef_maruziyet=onayli.onayli_maruziyet,
        karar_ms=onayli.karar_ms,
        limit_kimligi=onayli.limit_kimligi,
        kisitlayan=onayli.kisitlayan,
    )


__all__ = ["ExecutionHatasi", "KabulKaydi", "gonder"]
