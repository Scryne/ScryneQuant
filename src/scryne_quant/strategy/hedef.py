"""`HedefPortfoy`: çok enstrümanlı stratejinin ürettiği **niyet demeti**. (§12, K-057)

`Sinyal` tek bir enstrüman için "portföyün şu kesri kadar pozisyonda olmak istiyorum" der.
Cross-sectional bir aile ise tek bir enstrüman hakkında değil, **evren hakkında** konuşur:
"bu on sembolden şu üçünde şu ağırlıklarla olmak istiyorum". Bu modül o cümlenin tipi.

**Neden `Sinyal` demeti, yeni bir ağırlık sözlüğü değil.** İki gerekçe:

1. **Tek enstrüman özel hâl olarak kalsın (K-001, K-052/2).** Tek sembollü bir koşu, tek
   elemanlı bir `HedefPortfoy`tur; risk motoru aynı `Sinyal`i aynı kapılardan geçirir ve
   Faz 3'ün referans fixture'ı bit düzeyinde aynı sonucu verir. Ağırlık sözlüğü seçilseydi
   `side`, `confidence` ve `reason` kaybolurdu — yani "azaltan niyete engel konmaz"
   (K-008/3) kuralı çok enstrümanlı yolda **uygulanamaz** hâle gelirdi: hangi hedefin bir
   çıkış olduğunu ancak mevcut pozisyona bakarak tahmin edebilirdik, ve tahmin bu projede
   yasak.
2. **Audit'te "strateji ne istedi" sorusu cevaplanabilir kalsın (K-032).** `OnayliNiyet`
   sinyali olduğu gibi taşıyor; hedef portföy de sinyallerden kuruluysa portföy düzeyinde
   onay, sinyal düzeyindeki onayların demetidir — ikinci bir onay tipi doğmaz.

**Bahsedilmeyen sembol "kapat" demek değildir.** `Sinyal` sözleşmesindeki kuralın portföy
hâli: demette olmayan bir sembolün pozisyonu olduğu gibi kalır. Sessizliğin bir emre
dönüştüğü bir sözleşme, her barda bahsedilmeyen her pozisyonu kapatırdı — ve bir strateji
yalnızca ilgilendiği enstrüman hakkında konuşabilmeli.

**Toplam kontrolü gerekli ama yeterli değil.** Burada yalnızca **bahsedilen** hedeflerin
toplamı kontrol edilir (kaldıraç yok: ≤ 1). Bahsedilmeyen açık pozisyonlar da özkaynağı
tüketir; gerçek brüt maruziyet kısıtını uygulayan yer **risk motorudur** (K-037: izin veren
katman yalnızca orası).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from scryne_quant.strategy.sinyal import NEDEN_DESENI, Sinyal

#: Hedef toplamının kayan nokta payı. Ağırlıklar bölmeyle üretilir (1/3 + 1/3 + 1/3);
#: tam eşitlik istemek, matematiksel olarak doğru bir portföyü reddetmek olurdu.
TOPLAM_TOLERANS: Final = 1e-9


class HedefPortfoy(BaseModel):
    """Bir barda üretilen hedef portföy. Değişmez; üretildikten sonra düzeltilemez."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: int
    """Hedefi üreten **kapanmış** barın açılış zamanı (UTC epoch ms, K-005)."""

    sinyaller: tuple[Sinyal, ...]
    """Sembole göre sıralı, sembolleri benzersiz niyet demeti. Boş olabilir.

    Sıralama bir tercih değil, determinizmin (K-009) yapısal hâli: motor emirleri bu sırada
    hazırlıyor ve kayan nokta toplaması sıraya bağlı. Strateji sırayı belirleseydi, aynı
    hedef iki farklı sırada gelip iki farklı özkaynak eğrisi üretebilirdi.
    """

    yontem: str = "DOGRUDAN"
    """Hedefi üreten portföy kurma yönteminin **kodu** (`Sinyal.reason` ile aynı kalıp).

    `DOGRUDAN` = strateji ağırlıkları kendi verdi, kurma katmanı çalışmadı. Yöntem bir
    çekiliştir (K-051/4) ve hipotez kimliğine girer; kayıtta bir kod olarak durması,
    defterle eşleştirilebilmesi için.
    """

    @field_validator("yontem")
    @classmethod
    def _yontem_kod(cls, deger: str) -> str:
        if not NEDEN_DESENI.fullmatch(deger):
            raise ValueError(f"yontem bir kod olmalı (A-Z, 0-9, _), cümle değil: {deger!r}")
        return deger

    @model_validator(mode="after")
    def _tutarli(self) -> HedefPortfoy:
        semboller = [s.symbol for s in self.sinyaller]
        if len(set(semboller)) != len(semboller):
            tekrar = sorted({s for s in semboller if semboller.count(s) > 1})
            raise ValueError(
                f"aynı sembol için iki hedef: {', '.join(tekrar)}. Hangisinin geçerli "
                "olduğu sorusunun cevabı sıraya bırakılamaz"
            )
        if semboller != sorted(semboller):
            raise ValueError(
                "sinyaller sembole göre sıralı olmalı: emir sırası kayan nokta toplamını "
                "etkiler, yani sıra determinizmin (K-009) parçasıdır"
            )
        for s in self.sinyaller:
            if s.timestamp != self.timestamp:
                raise ValueError(
                    f"{s.symbol}: sinyal zamanı {s.timestamp}, hedef portföy zamanı "
                    f"{self.timestamp}. Bir hedef portföy tek bir barın kararıdır"
                )
        toplam = sum(s.target_exposure for s in self.sinyaller)
        if toplam > 1.0 + TOPLAM_TOLERANS:
            raise ValueError(
                f"hedeflerin toplamı 1'i aşamaz (kaldıraç yok): {toplam}. Bu kontrol "
                "**gerekli ama yeterli değil** — bahsedilmeyen açık pozisyonlar da "
                "özkaynağı tüketir; brüt maruziyeti bağlayan yer risk motorudur"
            )
        return self

    # ------------------------------------------------------------------ ölçüm

    @property
    def semboller(self) -> tuple[str, ...]:
        return tuple(s.symbol for s in self.sinyaller)

    @property
    def hedef_toplami(self) -> float:
        """Bahsedilen hedeflerin toplamı."""
        return sum(s.target_exposure for s in self.sinyaller)

    @property
    def asgari_nakit_agirligi(self) -> float:
        """Yalnızca bu demet uygulansaydı kalacak nakit kesri.

        "Asgari" değil "tam" demiyoruz çünkü bahsedilmeyen pozisyonlar da yer kaplar;
        gerçek nakit ağırlığı `CokluPortfoy.nakit_agirligi` ile ölçülür.
        """
        return max(0.0, 1.0 - self.hedef_toplami)

    def sinyal(self, sembol: str) -> Sinyal | None:
        for s in self.sinyaller:
            if s.symbol == sembol:
                return s
        return None

    def sozluk(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "yontem": self.yontem,
            "sinyaller": [s.model_dump(mode="json") for s in self.sinyaller],
        }


def hedef_kur(
    timestamp: int,
    sinyaller: Sequence[Sinyal],
    *,
    yontem: str = "DOGRUDAN",
) -> HedefPortfoy:
    """Sinyalleri sembole göre sıralayıp hedef portföyü kurar.

    Sıralamayı burada yapmak, her stratejinin aynı üç satırı yazmasını önlüyor; sözleşme
    yine de sıralı olmayan bir demeti **reddediyor** — kolaylık fonksiyonunu atlayıp
    doğrudan model kuran kod da aynı kuralla karşılaşsın diye.
    """
    return HedefPortfoy(
        timestamp=timestamp,
        sinyaller=tuple(sorted(sinyaller, key=lambda s: s.symbol)),
        yontem=yontem,
    )


__all__ = ["TOPLAM_TOLERANS", "HedefPortfoy", "hedef_kur"]
