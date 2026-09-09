"""`Sinyal`: stratejinin ürettiği **niyet**. Emir değil. (§10, K-003)

Aradaki fark bu projenin güvenlik mimarisinin tamamı: strateji "ne kadar pozisyonda olmak
istediğini" söyler, "kaç lot, hangi fiyattan, hangi emir tipiyle" sorusuna karışmaz.
O sorular risk motorunun (Faz 5) ve OMS'in (Faz 7) alanıdır.

Bu yüzden model `extra="forbid"`: `price`, `quantity`, `order_type` gibi bir alan
sızdırmaya çalışan strateji derlenmez bile — yasak, gözden geçirmeye değil tipe bağlı.

Alan adları İngilizce ve §10'daki JSON şekliyle birebir: bu nesne audit log'a, sonuç
kaydına ve Faz 6'da arayüze gidecek; şekli sözleşmedir, çeviri değil.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: `reason` bir **kod**tur, cümle değil: audit log'da gruplanabilir, testte eşitlenebilir,
#: dilden bağımsız olmalı. Serbest metne izin vermek onu okunamaz hâle getirirdi.
NEDEN_DESENI: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


class Yon(StrEnum):
    """Niyetin yönü. v1 **spot**: açığa satış ve kaldıraç yok (Final-Doküman, kapsam)."""

    BUY = "BUY"
    """Pozisyona gir veya artır."""

    SELL = "SELL"
    """Pozisyonu azalt (tamamen kapatmak için `FLAT` kullanılır)."""

    FLAT = "FLAT"
    """Pozisyonu tamamen kapat — hedef maruziyet sıfır."""


class Sinyal(BaseModel):
    """Strateji çıktısı. Değişmez; üretildiği andan sonra hiçbir katman düzeltemez."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    symbol: Annotated[str, Field(min_length=3, max_length=32)]
    """Örn. ``BTCUSDT``. Depo ve adaptörle aynı yazım — dönüşüm burada yapılmaz."""

    side: Yon

    target_exposure: Annotated[float, Field(ge=0.0, le=1.0)]
    """Portföyün bu sembolde olması istenen kesri. Mutlak hedef, delta değil.

    Delta ("%5 artır") yerine mutlak hedef seçildi: delta, sinyalin doğru uygulanması
    için stratejinin gerçek pozisyonu doğru bildiğini varsayar. Kaçırılan tek bir emir o
    varsayımı bozar ve strateji sessizce yanlış büyüklükte kalır. Mutlak hedef,
    uyuşmazlığı her barda kendiliğinden düzeltir.

    Üst sınır 1.0: v1 kaldıraçsız spot. Risk motoru bunu **aşağı** çekebilir, yukarı asla.
    """

    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    """Stratejinin kendi güveni. Risk motorunun girdisidir, kararı değil."""

    reason: str
    """Makine-okunur gerekçe kodu, örn. ``SMA_FAST_CROSSED_ABOVE_SLOW``."""

    timestamp: int
    """Sinyali üreten **kapanmış** barın açılış zamanı (UTC epoch ms, K-005).

    Sinyalin üretildiği an değil, karar verilen bar. Fill bunun bir sonraki barının
    açılışındadır (K-004) — o hesabı yapan backtest/execution bu alana bakar.
    """

    @field_validator("symbol")
    @classmethod
    def _sembol_buyuk(cls, deger: str) -> str:
        if not deger.isalnum():
            raise ValueError(f"sembol yalnızca harf/rakam içermeli: {deger!r}")
        return deger.upper()

    @field_validator("reason")
    @classmethod
    def _neden_kod(cls, deger: str) -> str:
        if not NEDEN_DESENI.fullmatch(deger):
            raise ValueError(
                f"reason bir kod olmalı (A-Z, 0-9, _; 3-64 karakter), cümle değil: {deger!r}"
            )
        return deger

    @field_validator("timestamp")
    @classmethod
    def _zaman_makul(cls, deger: int) -> int:
        # 2001-09-09'dan önce bir bar yok; negatif veya saniye cinsinden verilmiş bir
        # timestamp buradan geçerse hata Faz 3'te "sonuç biraz tuhaf" olarak görünürdü.
        if deger < 1_000_000_000_000:
            raise ValueError(f"timestamp UTC epoch **ms** olmalı (K-005): {deger}")
        return deger

    @model_validator(mode="after")
    def _yon_maruziyet_tutarli(self) -> Sinyal:
        """Yön ile hedef maruziyet birbirini yalanlayamaz.

        `FLAT` ama hedef %20 gibi bir sinyal, aşağı akıştaki her katmanda farklı
        yorumlanır — ve bu projede iki katmanın aynı sinyali farklı anlaması, tek bir
        hatadan daha pahalıdır.
        """
        if self.side is Yon.FLAT and self.target_exposure != 0.0:
            raise ValueError("FLAT sinyalinde target_exposure 0 olmalı")
        if self.side is Yon.BUY and self.target_exposure <= 0.0:
            raise ValueError("BUY sinyalinde target_exposure sıfırdan büyük olmalı")
        if self.side is Yon.SELL and self.target_exposure <= 0.0:
            raise ValueError("tamamen çıkış SELL değil FLAT ile ifade edilir")
        return self
