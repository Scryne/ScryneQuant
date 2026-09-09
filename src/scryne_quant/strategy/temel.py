"""`Strateji` sözleşmesi: `on_bar(ctx) -> Sinyal | None`. (§9.1, K-002, K-003)

Sözleşmenin tamamı üç kuraldan ibaret ve üçü de testle korunuyor:

1. Strateji `ctx`'ten okur, `Sinyal` döndürür. Başka hiçbir yan etkisi yoktur — ne
   dosya, ne ağ, ne borsa (K-003; `tests/unit/test_izolasyon.py`).
2. Strateji geleceği göremez; `ctx` `t`'de kesiktir (K-002;
   `tests/unit/test_look_ahead.py`).
3. Strateji **hangi özelliklere ihtiyacı olduğunu bildirir**, kendi hesaplamaz.

Üçüncü kural niçin: indikatörü strateji içinde hesaplamak, nedensellik garantisini her
strateji yazarının dikkatine bırakır — ve o dikkat er ya da geç bir gün eksik kalır.
Bildirimsel tanım, hesabı tek bir denetlenmiş yere (`features/motor.py`) toplar; ayrıca
sonuç kaydına yazılabilir bir config üretir (K-009).

Durum tutma: strateji örneği barlar arasında kendi alanlarında durum tutabilir (son
kesişim yönü gibi), ama bu durumun **yalnızca geçmişten** türemesi gerekir. `hazirla()`
her koşunun başında çağrılır ve durumu sıfırlar; aynı örneğin iki koşusu birbirini
etkilerse determinizm (K-009) kırılır.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal


class Strateji(ABC):
    """Tüm stratejilerin ortak arayüzü."""

    ad: str = ""
    """Kayıt ve raporlarda kullanılan kısa isim. Alt sınıf doldurur."""

    def __init__(self, **parametreler: Any) -> None:
        self.parametreler: Mapping[str, Any] = dict(parametreler)
        self.dogrula()

    # ------------------------------------------------------------ sözleşme

    @abstractmethod
    def ozellikler(self) -> Sequence[OzellikTanimi]:
        """Bu stratejinin ihtiyaç duyduğu özelliklerin bildirimi.

        Motor bunları koşu başında bir kez hesaplar; `ctx.ozellik(ad)` ile okunur.
        """

    @abstractmethod
    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        """**Kapanmış** bir bar için niyet üretir; niyet yoksa `None`.

        `None` "pozisyonu kapat" değil, "yeni bir şey söylemiyorum" demektir. Kapatmak
        `Yon.FLAT` ile açıkça ifade edilir — sessizliğin bir emre dönüştüğü bir sözleşme,
        her boş barda pozisyon kapatırdı.
        """

    # ------------------------------------------------------------ yaşam döngüsü

    def dogrula(self) -> None:  # noqa: B027 - bilinçli olarak isteğe bağlı kanca
        """Parametreleri kontrol eder. Geçersizse `ValueError`.

        `__init__` içinde çağrılır: geçersiz parametreyle kurulmuş bir strateji hiç var
        olmamalı. Backtest'in 40. dakikasında patlayan parametre hatası, hatanın en pahalı
        biçimi.
        """

    def hazirla(self) -> None:  # noqa: B027 - bilinçli olarak isteğe bağlı kanca
        """Koşu başında çağrılır; strateji içi durumu sıfırlar.

        Varsayılanı boş: durumsuz stratejiler için yazacak bir şey yok. Durum tutan bir
        strateji bunu **yazmak zorundadır**, yoksa aynı örnekle yapılan ikinci koşu
        birincisinden farklı sonuç verir ve K-009 sessizce ihlal edilir.
        """

    # ------------------------------------------------------------ kayıt

    def sozluk(self) -> dict[str, Any]:
        """Sonuç kaydına (K-009) yazılan deterministik gösterim."""
        return {
            "ad": self.ad or type(self).__name__,
            "sinif": f"{type(self).__module__}.{type(self).__qualname__}",
            "parametreler": dict(sorted(self.parametreler.items())),
            "ozellikler": [t.sozluk() for t in self.ozellikler()],
        }

    def __repr__(self) -> str:
        p = ", ".join(f"{a}={d!r}" for a, d in sorted(self.parametreler.items()))
        return f"{type(self).__name__}({p})"
