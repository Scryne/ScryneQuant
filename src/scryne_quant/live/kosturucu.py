"""Koşturucu: akışı motora bağlayan ve 30 gün ayakta kalması beklenen döngü. (Faz 6)

Motor (`live/motor.py`) bir barı nasıl işleyeceğini biliyor; akış (`exchange/akis.py`)
barların nereden geldiğini. Bu modül ikisini birleştiriyor ve arada kalan üç işi yapıyor:

1. **Nabız.** Akıştan gelen her mesaj `motor.nabiz()`e gidiyor — kapanmamış bar
   güncellemeleri dahil. K-037/2'nin sözleşmesi bu: çağrılmazsa bayat-veri guard'ı
   sürekli açık kalır ve işe yaramaz hâle gelir.
2. **Bayatlık yoklaması.** Bayatlık bar gelmediğinde anlaşılır, dolayısıyla bar işlemeyle
   aynı döngüde ölçülemez. Ayrı bir görev periyodik olarak yokluyor.
3. **Kesinti kaydı.** Kopma, hata ve düzgün kapanış koşu günlüğüne yazılıyor — Faz 6'nın
   *"kesinti olduysa sebebi kayıtlı ve giderilmiş"* kriterinin kaynağı.

**Neden iki ayrı görev, neden tek bir `select` döngüsü değil:** bar işleme uzun sürebilir
(pencere doğrulaması, strateji, disk yazımı) ve o sürede bayatlık yoklaması durursa guard
tam ihtiyaç duyulduğu anda kör kalır. Ayrı görevler bu bağlılığı kesiyor.

**Hata politikası:** beklenmeyen bir istisna koşuyu **durdurur** ve kayda geçer. Yeniden
denemek cazip ama yanlış: bu döngüdeki bir hata ya veri sözleşmesi ihlali (pencere geriye
gitti, bar hizasız) ya da toparlanma ayrışmasıdır, ve ikisi de "tekrar dene" ile geçmez.
Bağlantı hataları burada görünmez — onları akış kendi içinde yeniden bağlanarak ele alıyor.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Final

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.live.akis import Bar, BarAkisi
from scryne_quant.live.depo import KosuOlayi
from scryne_quant.live.motor import BarSonucu, PaperMotoru


class KosturucuHatasi(RuntimeError):
    """Koşturucu sözleşmesi ihlal edildi; koşu devam edemez."""


#: Bayatlık yoklamasının periyodu (saniye). Guard'ın eşiğinden (varsayılan 60 s) belirgin
#: olarak küçük: yoklama periyodu eşikten büyük olsaydı, guard eşiği değil yoklama
#: periyodu belirlerdi.
YOKLAMA_ARALIGI_S: Final = 15.0


@dataclass(frozen=True, slots=True)
class KosuOzeti:
    """Koşturucu durduğunda ne olduğunun özeti."""

    islenen_bar: int
    baslangic_ms: int
    bitis_ms: int
    hata: str | None

    @property
    def sure_gun(self) -> float:
        return (self.bitis_ms - self.baslangic_ms) / 86_400_000

    def sozluk(self) -> dict[str, Any]:
        return {
            "islenen_bar": self.islenen_bar,
            "baslangic_ms": self.baslangic_ms,
            "baslangic_utc": utc_str(self.baslangic_ms),
            "bitis_ms": self.bitis_ms,
            "bitis_utc": utc_str(self.bitis_ms),
            "sure_gun": self.sure_gun,
            "hata": self.hata,
        }


class Kosturucu:
    """Akış → motor döngüsü. Tek sembol, tek strateji, tek süreç."""

    def __init__(
        self,
        motor: PaperMotoru,
        akis: BarAkisi,
        *,
        yoklama_araligi_s: float = YOKLAMA_ARALIGI_S,
        bar_kancasi: Callable[[BarSonucu], None] | None = None,
        durdurma_istegi: Callable[[], dict[str, Any] | None] | None = None,
    ) -> None:
        self.motor = motor
        self.akis = akis
        self.yoklama_araligi_s = yoklama_araligi_s
        self.bar_kancasi = bar_kancasi
        """Her işlenmiş bardan sonra çağrılır. API'nin canlı yayını (SSE) buna bağlanıyor;
        motorun bir dinleyici listesi tutmasına gerek kalmıyor."""

        self.durdurma_istegi = durdurma_istegi
        """Dışarıdan gelen **düzgün** durdurma isteğini yoklar; varsa ayrıntısını döner.

        Koşturucu bir dosya ya da bir soket tanımıyor — yalnızca "birisi durmamı istedi
        mi" sorusunu soruyor. Uygulaması `live/durdurma.py`te ve bağlanması
        `live/baslat.py`te; bu ayrım sayesinde koşturucu testi dosya sistemine
        dokunmuyor."""

        self.islenen_bar = 0
        self._durduruldu = False
        self._baslangic_ms = 0
        self._yoklama_hatasi: str | None = None
        """Bayatlık yoklaması bir istisnayla öldüyse sebebi. Ayrıntı `_yoklama_gozetimi`."""

        self.durdurma_sebebi: str | None = None
        """Düzgün durdurma isteği geldiyse sebebi; `durdu` satırına yazılıyor."""

    # ------------------------------------------------------------------ ömür

    def durdur(self) -> None:
        """Döngüyü düzgün durdurur. Sinyal işleyicisinden çağrılabilir."""
        self._durduruldu = True
        self.akis.kapat()

    async def calistir(self) -> KosuOzeti:
        """Akış bitene veya `durdur()` çağrılana kadar barları işler."""
        self._baslangic_ms = simdi_ms()
        self.motor.depo.olay_yaz(
            KosuOlayi.BASLADI,
            ayrinti={"kosu": self.motor.kimlik.kosu_adi, "mod": self.motor.kimlik.mod},
        )
        yoklama = asyncio.create_task(self._yoklama_gozetimi())
        hata: str | None = None
        try:
            async for bar in self.akis.barlar():
                if self._durduruldu:
                    break
                self._bari_isle(bar)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - kaydedilip yükseltiliyor, yutulmuyor
            hata = f"{type(e).__name__}: {e}"
            self.motor.depo.olay_yaz(
                KosuOlayi.HATA,
                bar_ms=self.motor.son_bar_ms,
                ayrinti={"hata": hata, "islenen_bar": self.islenen_bar},
            )
            raise
        finally:
            yoklama.cancel()
            with suppress(asyncio.CancelledError):
                await yoklama
            if hata is None and self._yoklama_hatasi is not None:
                hata = self._yoklama_hatasi
            self.motor.depo.olay_yaz(
                KosuOlayi.DURDU,
                ayrinti={
                    "islenen_bar": self.islenen_bar,
                    "hata": hata,
                    "sebep": self.durdurma_sebebi,
                },
            )

        if self._yoklama_hatasi is not None:
            raise KosturucuHatasi(
                f"bayatlık yoklaması durdu: {self._yoklama_hatasi}. Guard körken koşuya "
                "devam edilmez — ölçülemeyen guard geçilmiş sayılmaz (§24)."
            )

        return KosuOzeti(
            islenen_bar=self.islenen_bar,
            baslangic_ms=self._baslangic_ms,
            bitis_ms=simdi_ms(),
            hata=hata,
        )

    # ------------------------------------------------------------------ döngüler

    def _bari_isle(self, bar: Bar) -> None:
        sonuc = self.motor.bar_isle(bar)
        self.islenen_bar += 1
        if self.bar_kancasi is not None:
            self.bar_kancasi(sonuc)

    async def _yoklama_dongusu(self) -> None:
        """Periyodik iki iş: bayatlık yoklaması ve düzgün durdurma isteği.

        İkisi aynı tik'i paylaşıyor çünkü ikisi de *"bar gelmese de çalışmalı"* sınıfına
        giriyor — modül başlığındaki ayrım bar işleme ile periyodik iş arasındaydı,
        periyodik işlerin kendi aralarında değil. Ayrı bir görev açmak, gözetlenecek
        ikinci bir sessiz ölüm noktası üretirdi.
        """
        while not self._durduruldu:
            await asyncio.sleep(self.yoklama_araligi_s)
            self.motor.tazelik_kontrol()
            self._durdurma_istegini_yokla()

    def _durdurma_istegini_yokla(self) -> None:
        """Dışarıdan düzgün durdurma istendiyse döngüyü **kendi** kapanış yolundan çıkarır.

        Sert kill'den farkı kayıtta görünüyor: burada `durdu` satırı sebebiyle birlikte
        yazılıyor ve koşu kesinti saymıyor. Planlı bir duruşu beklenmedik bir çökmeyle
        aynı kefeye koymak, *"30 gün kesintisiz"* kriterini tek bir makine oturumuna
        bağlamak olurdu.
        """
        if self.durdurma_istegi is None:
            return
        istek = self.durdurma_istegi()
        if istek is None:
            return
        self.durdurma_sebebi = str(istek.get("sebep") or "bilinmiyor")
        self.durdur()

    async def _yoklama_gozetimi(self) -> None:
        """Yoklama döngüsünü gözetir: öldüyse kayda geçirir ve **koşuyu durdurur**.

        Gözetimsiz hâli sessiz bir arıza üretiyordu ve tam olarak bu projenin en
        tehlikeli bulduğu türdendi. `tazelik_kontrol` diske yazıyor (`olay_yaz`), yani
        bir `sqlite3.OperationalError` ya da dolu disk onu fırlatabilir. O istisna
        `create_task` ile açılmış bir görevin içinde kaldığı için hiçbir yere
        ulaşmıyordu: görev ölür, ana döngü devam eder, ve bayat-veri guard'ı kalan 30 gün
        boyunca **kör** kalırdı. Dashboard yine "sistem sağlıklı" gösterirdi çünkü
        gösterdiği şey guard'ın son bildiği durum.

        Dahası istisna çıkışta zarar veriyordu: bitmiş bir göreve `cancel()` etkisiz,
        ve `finally` içindeki `await yoklama` saklı istisnayı oradan yeniden fırlatarak
        koşunun gerçek kapanış sebebinin üstüne yazıyordu.

        Politika `calistir`'ınkiyle aynı: kaydet ve dur. "Yeniden dene" yanlış olurdu —
        guard'ın körlüğü bir gecikme değil, §24'ün dayandığı ölçümün yokluğu.
        """
        try:
            await self._yoklama_dongusu()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - kaydedilip koşu durduruluyor, yutulmuyor
            self._yoklama_hatasi = f"{type(e).__name__}: {e}"
            # Kaydın kendisi de başarısız olabilir (arızanın kaynağı disk ise). Kaydı
            # kaybetmek üzücü, durdurmayı kaybetmek tehlikeli — bu yüzden ayrı.
            with suppress(Exception):
                self.motor.depo.olay_yaz(
                    KosuOlayi.HATA,
                    bar_ms=self.motor.son_bar_ms,
                    ayrinti={
                        "hata": self._yoklama_hatasi,
                        "kaynak": "bayatlik_yoklamasi",
                        "islenen_bar": self.islenen_bar,
                    },
                )
            self.durdur()


__all__ = ["YOKLAMA_ARALIGI_S", "Kosturucu", "KosturucuHatasi", "KosuOzeti"]
