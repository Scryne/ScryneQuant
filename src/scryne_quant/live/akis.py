"""Canlı bar akışı: sözleşme, nabız ve bayat-veri guard'ı. (§24, K-005, K-006, K-028)

Faz 1-5 boyunca veri **elde**ydi: bir Parquet dosyası açılır, barlar okunur, hepsi
oradadır. Canlıda veri bir **beklenti**dir ve beklentinin karşılanmaması normal bir hata
değil, tasarım gereksinimidir (§24). Bu modül o gereksinimi üç parçaya ayırıyor:

1. **`Bar`** — akıştan gelen tek bir kapanmış bar. Depo şemasının ham hâliyle (K-006:
   kalite bayrağı borsanın beyanı değil, doğrulama katmanının kararı) birebir aynı.
2. **`Tazelik`** — "en son ne zaman bir şey duydum" sayacı. Bayatlık **barla değil
   nabızla** ölçülür; gerekçe aşağıda.
3. **`BarAkisi`** — akışın sözleşmesi. Protokol burada, uygulaması `exchange/`te:
   tüketicinin arayüzü tanımlaması, testin bir borsaya ihtiyaç duymaması demek.

**Bayatlık neden barla değil nabızla ölçülür.** 1h timeframe'de barlar saatte bir kapanır;
"son bar 40 dakika önce geldi" bayatlık değil, normaldir. Bağlantının canlı olduğunu
söyleyen şey bar değil, akıştaki her mesajdır (kapanmamış barın her güncellemesi de bir
mesajdır). §24'ün örneği de bunu söylüyor: *"Last market update: 37 seconds ago / Expected
update: < 5 sec"* — ölçülen şey **update**, bar değil. Bar süresine bakan bir guard, 1h'te
bir saat boyunca kör kalırdı.

**Ölçülemeyen guard geçilmiş sayılmaz.** Hiç nabız alınmadıysa (`son_nabiz_ms is None`)
akış **bayat** kabul edilir. Faz 5'te aynı kural ATR için verilmişti: ölçülemeyen
volatilite guard'ı reddeder, geçirmez. Tersi — "bilgi yoksa sorun yoktur" — bu projedeki
en pahalı varsayım sınıfı.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Protocol, runtime_checkable

import numpy as np

from scryne_quant.common.zaman import timeframe_ms, utc_str
from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI
from scryne_quant.data.takvim import Takvim


class AkisHatasi(RuntimeError):
    """Akış sözleşmesi ihlal edildi."""


class Kaynak(StrEnum):
    """Bir barın nereden geldiği. Kalite bayrağını etkiler (K-006)."""

    AKIS = "akis"
    """Birincil akıştan (WebSocket) geldi."""

    BACKFILL = "backfill"
    """Sonradan REST ile tamamlandı — kopma sonrası resync veya ilk doldurma.

    Kusursuz olsa bile `ok` değil `backfilled` işaretlenir (K-006). Ayrım şu soruyu
    cevaplanabilir tutuyor: "bu barda karar verdiğimizde bu veri elimizde miydi, yoksa
    sonradan mı öğrendik?" İkisini `ok` diye birleştirmek, kopmaların izini silerdi.
    """


@dataclass(frozen=True, slots=True)
class Bar:
    """Akıştan gelen kapanmış bar. `quality_status` **yok** — o bayrağı akış vermez.

    Alan adları ve sırası `data/semalar.py:HAM_BAR_SUTUNLARI` ile birebir aynı; ikisinin
    ayrışmadığı testle korunuyor. Sebep: canlı bar da tarihsel bar da aynı doğrulamadan
    (`data/dogrulama.py:dogrula`) geçmek zorunda, yoksa canlıda `suspect` sayılan bir bar
    backtest'te `ok` sayılır ve iki kod yolu sessizce ayrışır (K-001).
    """

    open_time: int
    """Barın **açılış** zamanı, UTC epoch ms (K-005). Kapanış değil."""

    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trades: int

    kaynak: Kaynak = Kaynak.AKIS
    """Bayrağa girer, şemaya girmez — bu yüzden `sozluk()` onu dışarıda bırakıyor."""

    def __post_init__(self) -> None:
        if self.open_time < 0:
            raise AkisHatasi(f"negatif bar zamanı: {self.open_time}")

    def hizali_mi(self, timeframe: str) -> bool:
        """Bar epoch'a hizalı bir ızgara noktasında mı? (K-005)"""
        return self.open_time % timeframe_ms(timeframe) == 0

    def sozluk(self) -> dict[str, Any]:
        """Ham bar sütunları — `dogrula`'nın beklediği biçim. `kaynak` burada yok."""
        return {ad: getattr(self, ad) for ad in HAM_BAR_SUTUNLARI}

    def __str__(self) -> str:
        return (
            f"{utc_str(self.open_time)} O{self.open:g} H{self.high:g} "
            f"L{self.low:g} C{self.close:g}"
        )


#: Bar alanlarının şemayla hizası. `Bar` alan **eklerse** buradaki tuple değişmez —
#: `kaynak` şemanın parçası değil. Testin kontrol ettiği şey bu iki listenin eşitliği.
BAR_ALANLARI: Final[tuple[str, ...]] = HAM_BAR_SUTUNLARI


class Tazelik:
    """Bayat-veri guard'ı: "en son ne zaman bir şey duydum". (§24)

    Duvar saatini **dışarıdan** alıyor (`simdi_ms` parametresi), kendi içinde
    `time.time()` çağırmıyor. Sebep test edilebilirlik değil, determinizm: bu sınıfın
    kararına giren her sayı çağıranın kaydettiği bir sayı olmalı ki audit'te "o an
    veri kaç saniyeliktı" sorusunun cevabı bulunabilsin.
    """

    __slots__ = ("_azami_yas_ms", "_son_nabiz_ms", "_bayat_giris", "_bayat_cikis", "_takvim")

    def __init__(self, azami_yas_ms: int, takvim: Takvim | None = None) -> None:
        if azami_yas_ms <= 0:
            raise AkisHatasi(f"azami veri yaşı pozitif olmalı: {azami_yas_ms}")
        self._azami_yas_ms = azami_yas_ms
        self._takvim = takvim
        """R4 Paket 1: seanslı takvimde piyasa kapalıyken sessizlik bayatlık değildir. `None`/24x7
        → davranış Faz 6 ile aynı (bit-aynı)."""
        self._son_nabiz_ms: int | None = None
        self._bayat_giris = 0
        """Kaç kez bayat duruma girildi. Faz 6'nın "kesinti sebebi kayıtlı" kriterinin sayacı."""
        self._bayat_cikis = 0

    @property
    def azami_yas_ms(self) -> int:
        return self._azami_yas_ms

    @property
    def son_nabiz_ms(self) -> int | None:
        """En son mesaj alınan duvar saati anı. `None` = hiç mesaj alınmadı."""
        return self._son_nabiz_ms

    @property
    def bayat_giris(self) -> int:
        return self._bayat_giris

    def nabiz(self, simdi_ms: int) -> None:
        """Akıştan bir mesaj geldiğini bildirir. Kapanmamış bar güncellemesi de sayılır.

        Geriye giden bir nabız yok sayılıyor, hata verilmiyor: sistem saatinin NTP ile
        geri çekilmesi gerçek bir olay ve bu yüzden bir koşuyu düşürmek, düzeltmekten
        pahalıdır. En son duyduğumuz anın ileri gitmesi yeterli.
        """
        if self._son_nabiz_ms is None or simdi_ms > self._son_nabiz_ms:
            self._son_nabiz_ms = simdi_ms

    def yas(self, simdi_ms: int) -> int | None:
        """Verinin yaşı (ms). `None` = hiç nabız alınmadı, yani yaş **ölçülemedi**."""
        if self._son_nabiz_ms is None:
            return None
        return max(0, simdi_ms - self._son_nabiz_ms)

    def bayat_mi(self, simdi_ms: int) -> bool:
        """Veri bayat mı? Hiç nabız alınmadıysa **evet** — ölçülemeyen guard geçilmez.

        Seanslı takvimde (R4) piyasa kapalıyken (`acik_mi` False) daha önce nabız alınmışsa bayat
        **değil**: kapanışta veri gelmemesi beklenen durumdur; hiç nabız yoksa yine evet.
        """
        yas = self.yas(simdi_ms)
        if yas is None:
            return True
        if (
            self._takvim is not None
            and not self._takvim.surekli
            and not bool(self._takvim.acik_mi(np.array([simdi_ms], dtype="int64"))[0])
        ):
            return False
        return yas > self._azami_yas_ms

    def gecis_isle(self, simdi_ms: int) -> bool | None:
        """Durum değiştiyse yeni durumu, değişmediyse `None` döner. Sayaçları günceller.

        Ayrı bir metot olmasının sebebi log gürültüsü: bayatlık her kontrolde değil,
        **girildiğinde ve çıkıldığında** bir kez kaydedilmeli. Her kontrolde satır yazan
        bir guard, 30 günlük koşuda kendi kanıtını okunmaz hâle getirir.
        """
        bayat = self.bayat_mi(simdi_ms)
        oncekiler = self._bayat_giris > self._bayat_cikis
        if bayat and not oncekiler:
            self._bayat_giris += 1
            return True
        if not bayat and oncekiler:
            self._bayat_cikis += 1
            return False
        return None

    @property
    def bayat_durumda(self) -> bool:
        """`gecis_isle`'nin gördüğü son duruma göre şu an bayat mıyız?"""
        return self._bayat_giris > self._bayat_cikis

    def sozluk(self, simdi_ms: int) -> dict[str, Any]:
        return {
            "son_nabiz_ms": self._son_nabiz_ms,
            "yas_ms": self.yas(simdi_ms),
            "azami_yas_ms": self._azami_yas_ms,
            "bayat": self.bayat_mi(simdi_ms),
            "bayat_giris": self._bayat_giris,
            "bayat_cikis": self._bayat_cikis,
        }


@runtime_checkable
class BarAkisi(Protocol):
    """Canlı bar akışının sözleşmesi. Uygulaması `exchange/akis.py`te.

    Protokolün **tüketici tarafında** (burada) tanımlı olması bilinçli: `live/` döngüsü
    bir borsa tanımadan test edilebilmeli. Testlerdeki sahte akış bu protokolü uygular ve
    `exchange/`i hiç import etmez.
    """

    @property
    def sembol(self) -> str: ...

    @property
    def timeframe(self) -> str: ...

    def kapat(self) -> None:
        """Akışı kapatır. İki kez çağrılabilir olmalı."""
        ...

    def barlar(self) -> AsyncIterator[Bar]:
        """Kapanmış barları sırayla üretir.

        **Yalnızca kapanmış bar üretilir.** Kapanmamış bar üretmek, stratejinin henüz
        oluşmakta olan bir kapanışa göre karar vermesi demek olurdu — K-004'ün fill
        kuralının karar tarafındaki karşılığı. Kapanmamış barın tek işlevi nabızdır
        (`Tazelik.nabiz`), ve o bilgi bar olarak değil sayaç olarak dışarı çıkar.
        """
        ...


__all__ = [
    "BAR_ALANLARI",
    "AkisHatasi",
    "Bar",
    "BarAkisi",
    "Kaynak",
    "Tazelik",
]
