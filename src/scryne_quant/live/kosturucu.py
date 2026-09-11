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
    ) -> None:
        self.motor = motor
        self.akis = akis
        self.yoklama_araligi_s = yoklama_araligi_s
        self.bar_kancasi = bar_kancasi
        """Her işlenmiş bardan sonra çağrılır. API'nin canlı yayını (SSE) buna bağlanıyor;
        motorun bir dinleyici listesi tutmasına gerek kalmıyor."""

        self.islenen_bar = 0
        self._durduruldu = False
        self._baslangic_ms = 0

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
        yoklama = asyncio.create_task(self._yoklama_dongusu())
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
            self.motor.depo.olay_yaz(
                KosuOlayi.DURDU,
                ayrinti={"islenen_bar": self.islenen_bar, "hata": hata},
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
        """Bayatlığı periyodik olarak yoklar. Bar gelmese de çalışır — asıl mesele o."""
        while not self._durduruldu:
            await asyncio.sleep(self.yoklama_araligi_s)
            self.motor.tazelik_kontrol()


__all__ = ["YOKLAMA_ARALIGI_S", "Kosturucu", "KosuOzeti"]
