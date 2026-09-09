"""Strateji başına varsayılan tarama ızgaraları. (Faz 4)

Izgaralar **stratejilerin içinde değil burada** duruyor: `strategy/` paketi araştırma
katmanını tanımaz (K-003'ün ruhu), ve bir ızgara stratejinin tanımı değil, ona sorulan
sorunun tanımıdır.

**Izgaralar bilerek küçük.** 1.000 kombinasyon denemek, gürültünün en şanslı örneğini
"en iyi parametre" diye sunmanın en kestirme yolu. Her ızgara 24-48 nokta: parametre
duyarlılığını (plato mu tepe mi) görmeye yetecek kadar geniş, bulunanı ciddiye almayı
zorlaştıracak kadar dar. §16.2'nin overfitting uyarısı tam olarak bunu söylüyor.

**Maruziyet ızgaraya girmiyor.** Pozisyon büyüklüğü risk motorunun kararıdır (Faz 5);
burada sabit tutulmazsa tarama, "daha çok risk al" cevabını her zaman bulur — çünkü
yükselen bir varlıkta maruziyeti artırmak Sharpe'ı değil ama getiriyi her koşulda büyütür.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

#: Tüm ızgaralarda sabit tutulan hedef maruziyet. Bkz. modül docstring'i.
SABIT_MARUZIYET: Final = 0.2

IZGARALAR: Final[dict[str, dict[str, Sequence[Any]]]] = {
    # Kıyas ölçütünün ızgarası tek noktalı: al-tut'ta optimize edilecek bir şey yok,
    # ve olmaması gerekiyor — kıyas sabit bir çizgi olmalı, ayarlanan bir rakip değil.
    "al_tut": {"maruziyet": (SABIT_MARUZIYET,)},
    "sma_kesisim": {
        "hizli": (10, 20, 30, 50),
        "yavas": (50, 100, 150, 200),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "ema_kesisim": {
        "hizli": (10, 20, 30, 50),
        "yavas": (50, 100, 150, 200),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "rsi_donus": {
        "pencere": (7, 14, 21),
        "alt": (20.0, 25.0, 30.0, 35.0),
        "ust": (60.0, 70.0, 80.0),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "donchian": {
        "giris": (20, 40, 55, 80),
        "cikis": (10, 20, 40),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "momentum": {
        "pencere": (12, 24, 48, 96),
        "giris_esigi": (1.0, 2.0, 4.0),
        "cikis_esigi": (-1.0, -2.0, -4.0),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "cok_faktor": {
        "trend_pencere": (50, 100, 200),
        "roc_pencere": (12, 24, 48),
        "hacim_pencere": (20,),
        "giris_oyu": (2, 3),
        "cikis_oyu": (1, 2),
        "maruziyet": (SABIT_MARUZIYET,),
    },
}


class IzgaraYok(KeyError):
    """Bu strateji için tanımlı ızgara yok."""


def izgara(strateji_adi: str) -> Mapping[str, Sequence[Any]]:
    """Bir stratejinin varsayılan ızgarası."""
    try:
        return IZGARALAR[strateji_adi]
    except KeyError:
        raise IzgaraYok(
            f"{strateji_adi!r} için ızgara tanımlı değil; tanımlı: {', '.join(sorted(IZGARALAR))}"
        ) from None


def boyut(strateji_adi: str) -> int:
    """Izgaradaki ham kombinasyon sayısı (stratejinin reddedecekleri dahil)."""
    n = 1
    for degerler in izgara(strateji_adi).values():
        n *= len(degerler)
    return n
