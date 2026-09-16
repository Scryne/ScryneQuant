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
from scryne_quant.strategy.evren import EvrenBaglam, EvrenDisi
from scryne_quant.strategy.hedef import HedefPortfoy, hedef_kur
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

    def isinma_bar(self) -> int:
        """Bu stratejinin ilk sinyalini üretebilmesi için gereken bar sayısı.

        Varsayılan, bildirilen özelliklerin en büyük penceresi + 2. İki barlık pay:
        `rsi`/`atr` gibi indikatörlerin ilk geçerli değeri `pencere` indeksinde (yani
        `pencere+1`. barda) çıkıyor, ve kesişim soran stratejiler `geri=1` ile bir bar
        daha geriye bakıyor.

        Faz 4'ün walk-forward'ı bu sayıyı gerçekten kullanıyor: bir katmanın önüne kaç
        barlık ısınma ekleneceğini belirliyor. Eksik tahmin edilirse katmanın ilk
        sinyalleri kaybolur ve sonuç sessizce olduğundan sakin görünür — bu yüzden
        varsayılan cömert tarafta.
        """
        pencereler = [
            int(deger)
            for tanim in self.ozellikler()
            for ad, deger in dict(tanim.parametreler).items()
            if ad == "pencere"
        ]
        return max(pencereler, default=0) + 2

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


class PortfoyStratejisi(ABC):
    """Çok enstrümanlı strateji sözleşmesi: `on_bar(ctx) -> HedefPortfoy | None`. (Faz 10)

    `Strateji` tek bir enstrüman hakkında konuşur; bu sınıf **evren hakkında**. Üç kural
    aynen geçerli ve aynı testlerle korunuyor: I/O yok (K-003), gelecek yok (K-002),
    özellikler bildirilir (`features/motor.py`).

    **Özellikler bir kez bildirilir, her enstrüman için hesaplanır.** Cross-sectional bir
    ailenin tanımı zaten budur: aynı ölçüyü evrenin tamamına uygula, sonra sırala.
    Enstrüman başına farklı özellik bildirmek mümkün olsaydı, "aynı ölçü" iddiası
    stratejinin dikkatine kalırdı.

    **`None` "her şeyi kapat" değil, "yeni bir şey söylemiyorum" demektir** — `Strateji`
    ile aynı kural. Kapatmak, hedef portföyde o sembol için `FLAT` ile ifade edilir.
    """

    ad: str = ""

    def __init__(self, **parametreler: Any) -> None:
        self.parametreler: Mapping[str, Any] = dict(parametreler)
        self.dogrula()

    # ------------------------------------------------------------ sözleşme

    @abstractmethod
    def ozellikler(self) -> Sequence[OzellikTanimi]:
        """Evrenin **her** enstrümanı için hesaplanacak özelliklerin bildirimi."""

    @abstractmethod
    def on_bar(self, ctx: EvrenBaglam) -> HedefPortfoy | None:
        """Kapanmış bir bar için hedef portföy üretir; niyet yoksa `None`."""

    # ------------------------------------------------------------ yaşam döngüsü

    def dogrula(self) -> None:  # noqa: B027 - bilinçli olarak isteğe bağlı kanca
        """Parametreleri kontrol eder. Geçersizse `ValueError`."""

    def hazirla(self) -> None:  # noqa: B027 - bilinçli olarak isteğe bağlı kanca
        """Koşu başında çağrılır; strateji içi durumu sıfırlar (K-009)."""

    def isinma_bar(self) -> int:
        """İlk hedefin üretilebilmesi için gereken bar sayısı. Kalıp `Strateji` ile aynı."""
        pencereler = [
            int(deger)
            for tanim in self.ozellikler()
            for ad, deger in dict(tanim.parametreler).items()
            if ad == "pencere"
        ]
        return max(pencereler, default=0) + 2

    # ------------------------------------------------------------ kayıt

    def sozluk(self) -> dict[str, Any]:
        return {
            "ad": self.ad or type(self).__name__,
            "sinif": f"{type(self).__module__}.{type(self).__qualname__}",
            "parametreler": dict(sorted(self.parametreler.items())),
            "ozellikler": [t.sozluk() for t in self.ozellikler()],
        }

    def __repr__(self) -> str:
        p = ", ".join(f"{a}={d!r}" for a, d in sorted(self.parametreler.items()))
        return f"{type(self).__name__}({p})"


class TekEnstruman(PortfoyStratejisi):
    """Tek enstrümanlı bir `Strateji`yi çok enstrümanlı sözleşmeye taşır. (K-001, K-052/2)

    Bu sınıf, "tek enstrüman çok enstrümanlının **özel hâlidir**" cümlesinin kodu. Faz 3-7'nin
    her stratejisi bu sarmalayıcıyla yeni motorda koşuyor ve Faz 3'ün bağımsız referans
    fixture'ı bit düzeyinde aynı sonucu veriyor — iki motor olsaydı bu iddia yalnızca
    "sayılar yakın" olurdu.

    **`sozluk()` sarmalananın sözlüğünü aynen döndürür.** Sarmalayıcının adını yazmak
    `Sonuc.config_hash`i değiştirirdi, yani Faz 1-7'de kaydedilmiş her deney yeniden
    üretilemez hâle gelirdi (K-009). Sarmalayıcı bir uygulama detayı; deneyin kimliği
    stratejinin kendisi.
    """

    def __init__(self, strateji: Strateji, sembol: str) -> None:
        self.strateji = strateji
        self.sembol = sembol.upper()
        super().__init__(**dict(strateji.parametreler))
        self.ad = strateji.ad or type(strateji).__name__

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return self.strateji.ozellikler()

    def hazirla(self) -> None:
        self.strateji.hazirla()

    def isinma_bar(self) -> int:
        return self.strateji.isinma_bar()

    def on_bar(self, ctx: EvrenBaglam) -> HedefPortfoy | None:
        try:
            baglam = ctx.enstruman(self.sembol)
        except EvrenDisi:
            # Evren dışı bir barda karar verilmez. Tek sembollü koşuda bu hiç olmaz
            # (sembol her barda üye); çok sembollü bir evrende sarmalanmış bir strateji
            # kendi enstrümanı listelenmeden önce sessizce beklemeli.
            return None
        sinyal = self.strateji.on_bar(baglam)
        if sinyal is None:
            return None
        return hedef_kur(baglam.zaman, (sinyal,))

    def sozluk(self) -> dict[str, Any]:
        return self.strateji.sozluk()

    def __repr__(self) -> str:
        return f"TekEnstruman({self.strateji!r}, {self.sembol!r})"
