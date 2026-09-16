"""`OnayliNiyet` ve `Red`: risk motorunun iki olası çıktısı. (§9.1, K-010, K-032)

Mimarinin üçüncü değişmez kuralı şu: *"Sinyal risk motorunu atlayamaz. Execution'a giden
tek yol onaylanmış intent'tir."* Bu modül o kuralın tip karşılığı.

Zincir bilinçli olarak **tek yönlü ve tek yollu**:

    Strateji → Sinyal → RiskMotoru → OnayliNiyet → execution kapısı → borsa
                                   ↘ Red → audit (ve orada biter)

`Sinyal`in execution'a giden bir yolu yok, çünkü `execution` `Sinyal` tipini hiç tanımıyor
(statik olarak test ediliyor). `OnayliNiyet`in risk motorundan başka bir üreticisi yok,
çünkü mührü olmayan bir örnek kurulamaz (`muhur.py`).

**`Red` bir `None` değil.** Reddedilen sinyal sessizce kaybolmaz: sebebi, o anki durumu ve
hangi limitin kapattığı audit'e yazılır. Faz 3'ün `AtlamaSebebi` enum'u aynı gerekçeyle
vardı — "sinyal işleme dönmedi" bilgisi kaydın parçası, yokluğu değil.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from scryne_quant.risk import muhur
from scryne_quant.strategy.hedef import HedefPortfoy
from scryne_quant.strategy.sinyal import Sinyal, Yon


class RedSebebi(StrEnum):
    """Bir sinyalin neden onaylanmadığı. Audit'te gruplanabilmesi için kod, cümle değil."""

    SAFE_MODE = "safe_mode"
    """Kill switch tetiklenmiş; sistem SAFE_MODE'da ve çıkış yalnızca elle onayla (K-008/4)."""

    PROMOTION_YOK = "promotion_yok"
    """Strateji bu çalışma modu için promotion zincirini geçmemiş (K-010)."""

    GUNLUK_ZARAR = "gunluk_zarar"
    """Bu UTC gününün zararı limiti aştı; gün dönümüne kadar yeni giriş yok."""

    DRAWDOWN = "drawdown"
    """Zirveden düşüş limiti aştı; kill switch tetiklendi."""

    COOLDOWN = "cooldown"
    """Ardışık kayıp limiti tetiklendi; cooldown penceresi dolmadı."""

    VOLATILITE = "volatilite"
    """ATR/fiyat eşiğin üstünde; bu barda yeni giriş yapılmıyor."""

    VOLATILITE_OLCULEMEDI = "volatilite_olculemedi"
    """Volatilite ölçülemedi (ATR yok). Ölçülemeyen guard geçilmiş sayılmaz."""

    BRUT_MARUZIYET = "brut_maruziyet"
    """Portföyün brüt maruziyet tavanı doldu; bu hedef için yer kalmadı (Faz 10, §12).

    Tavan **aşağı çeker**; sıfıra kadar çekmek zorunda kaldığında red olur. Azaltan
    niyetlere uygulanmaz: brüt maruziyeti düşüren bir emri brüt maruziyet limitiyle
    engellemek, limitin amacının tersini yapardı."""

    ENSTRUMAN_SAYISI = "enstruman_sayisi"
    """Eşzamanlı enstrüman tavanı dolu; bu **yeni** giriş açılmıyor (Faz 10, §12).

    Mevcut pozisyonlar etkilenmez ve çıkışlar hiçbir zaman engellenmez. Hangi adayın
    eleneceği stratejinin kendi `confidence`ına göre belirlenir, eşitlikte sembol sırasına."""

    SIFIR_BOYUT = "sifir_boyut"
    """Limitler hedefi sıfıra indirdi; gönderilecek bir pozisyon kalmadı."""

    GECERSIZ_OLCUM = "gecersiz_olcum"
    """Fiyat veya özkaynak geçersiz (≤0); bu durumda karar verilmez."""


#: Pozisyonu **azaltan** niyetler. Bu ayrım risk motorunun en önemli tek kuralını taşıyor:
#: bir çıkışı engellemek riski azaltmaz, artırır. Halt, cooldown, SAFE_MODE — hiçbiri bir
#: azaltmayı durdurmaz (K-008/3 ile aynı mantık: mevcut çıkışlar çalışmaya devam eder).
AZALTAN_YONLER: frozenset[Yon] = frozenset({Yon.SELL, Yon.FLAT})


@dataclass(frozen=True, slots=True)
class OnayliNiyet:
    """Risk motorundan geçmiş, execution'a sunulabilir niyet.

    `Sinyal`den iki farkı var ve ikisi de kasıtlı:

    - `onayli_maruziyet` stratejinin istediği değil, riskin **izin verdiği** hedef. Asla
      sinyalin hedefinden büyük olamaz (`__post_init__` kontrol ediyor).
    - `muhur` bu nesnenin risk motorunda üretildiğinin kanıtı. Mührü doğrulamayan bir
      execution kapısı, olmayan bir kapıdır.

    `sinyal` alanı olduğu gibi taşınıyor: audit'te "strateji ne istedi, risk ne verdi"
    karşılaştırması ancak ikisi bir aradaysa yapılabilir.
    """

    sinyal: Sinyal
    onayli_maruziyet: float
    limit_kimligi: str
    """Kararı veren limit kümesinin hash'i (`RiskLimitleri.kimlik()`)."""

    karar_ms: int
    """Kararın verildiği barın açılış zamanı (UTC epoch ms, K-005)."""

    kisitlayan: tuple[str, ...] = ()
    """Hedefi aşağı çeken limitlerin adları, sırayla. Boşsa sinyal olduğu gibi onaylandı."""

    muhur: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.onayli_maruziyet <= self.sinyal.target_exposure:
            raise ValueError(
                "onaylı maruziyet [0, sinyalin hedefi] aralığında olmalı — risk motoru "
                f"aşağı çekebilir, yukarı asla: sinyal={self.sinyal.target_exposure}, "
                f"onaylı={self.onayli_maruziyet}"
            )
        if not muhur.gecerli_mi(self._muhur_alanlari, self.muhur):
            raise muhur.MuhurGecersiz(
                "mühürsüz veya bozulmuş OnayliNiyet. Bu nesne yalnızca RiskMotoru "
                "tarafından üretilebilir; elle kurulan bir onay, onay değildir (K-032)"
            )

    @property
    def _muhur_alanlari(self) -> tuple[object, ...]:
        """Mührün kapsadığı içerik. Buradaki her alan onay sonrası değiştirilemez.

        `sinyal` bütün olarak giriyor (frozen Pydantic modeli, alanları da değişmez):
        onaylanan şey "bu sembol için şu kadar maruziyet" değil, **bu sinyal** için o
        kadar maruziyet. Sinyali değiştirip mührü korumak mümkün olmamalı.
        """
        return (
            self.sinyal.model_dump_json(),
            self.onayli_maruziyet,
            self.limit_kimligi,
            self.karar_ms,
            self.kisitlayan,
        )

    @property
    def azaltma(self) -> bool:
        """Bu niyet pozisyonu azaltıyor mu? Azaltmalar hiçbir halt tarafından engellenmez."""
        return self.sinyal.side in AZALTAN_YONLER

    def sozluk(self) -> dict[str, Any]:
        """Audit kaydına yazılan biçim. **Mühür yazılmaz** — süreç başına rastgeledir."""
        return {
            "karar": "onay",
            "sembol": self.sinyal.symbol,
            "yon": str(self.sinyal.side),
            "istenen_maruziyet": self.sinyal.target_exposure,
            "onayli_maruziyet": self.onayli_maruziyet,
            "kisitlayan": list(self.kisitlayan),
            "reason": self.sinyal.reason,
            "confidence": self.sinyal.confidence,
            "sinyal_ms": self.sinyal.timestamp,
            "karar_ms": self.karar_ms,
            "limit_kimligi": self.limit_kimligi,
        }


@dataclass(frozen=True, slots=True)
class Red:
    """Reddedilmiş sinyal: sebebi ve karar anındaki durumla birlikte.

    Mühürsüz — çünkü hiçbir yere gitmiyor. Red, execution'a sunulabilecek bir nesne
    değil; audit'e yazılan bir kayıt. Tip düzeyinde de böyle: `execution` kapısı `Red`
    kabul etmez, `OnayliNiyet` ister.
    """

    sinyal: Sinyal
    sebep: RedSebebi
    karar_ms: int
    limit_kimligi: str
    ayrinti: dict[str, Any] = field(default_factory=dict)
    """Kararın sayısal dayanağı: hangi limit, ölçülen değer, sınır. Audit'in okunabilirliği
    buna bağlı — "cooldown" yazan bir satır, cooldown'ın ne zaman biteceğini söylemiyorsa
    altı ay sonra hiçbir şey anlatmaz."""

    def sozluk(self) -> dict[str, Any]:
        return {
            "karar": "red",
            "sebep": str(self.sebep),
            "sembol": self.sinyal.symbol,
            "yon": str(self.sinyal.side),
            "istenen_maruziyet": self.sinyal.target_exposure,
            "reason": self.sinyal.reason,
            "confidence": self.sinyal.confidence,
            "sinyal_ms": self.sinyal.timestamp,
            "karar_ms": self.karar_ms,
            "limit_kimligi": self.limit_kimligi,
            "ayrinti": self.ayrinti,
        }


Karar = OnayliNiyet | Red


@dataclass(frozen=True, slots=True)
class PortfoyKarari:
    """Bir hedef portföyün risk motorundan çıkan hâli: sembol başına karar. (Faz 10)

    **İkinci bir mühür yok.** Onay hâlâ `OnayliNiyet` düzeyinde ve sembol başına
    mühürlü; bu nesne yalnızca onları bir arada taşıyor. Portföy düzeyinde ayrı bir
    mühür olsaydı execution kapısının iki farklı onay tipini tanıması gerekirdi ve
    "onaylanmış intent dışında hiçbir şey geçmez" cümlesi iki cümleye bölünürdü.

    `portfoy_kisiti` portföy düzeyinde **aşağı çeken** limitlerin adları. Bu katman
    izin veremez, yalnızca kısabilir (K-037).
    """

    hedef: HedefPortfoy
    kararlar: tuple[Karar, ...]
    """Sembole göre sıralı — `HedefPortfoy.sinyaller` ile aynı sırada."""

    portfoy_kisiti: tuple[str, ...] = ()

    @property
    def onaylar(self) -> tuple[OnayliNiyet, ...]:
        return tuple(k for k in self.kararlar if isinstance(k, OnayliNiyet))

    @property
    def redler(self) -> tuple[Red, ...]:
        return tuple(k for k in self.kararlar if isinstance(k, Red))

    def onayli_hedefler(self) -> dict[str, tuple[Sinyal, float]]:
        """Motorun emre çevireceği biçim: sembol → (sinyal, onaylı maruziyet)."""
        return {o.sinyal.symbol: (o.sinyal, o.onayli_maruziyet) for o in self.onaylar}

    def sozluk(self) -> dict[str, Any]:
        return {
            "timestamp": self.hedef.timestamp,
            "yontem": self.hedef.yontem,
            "portfoy_kisiti": list(self.portfoy_kisiti),
            "kararlar": [k.sozluk() for k in self.kararlar],
        }


def onayla(
    sinyal: Sinyal,
    onayli_maruziyet: float,
    limit_kimligi: str,
    karar_ms: int,
    kisitlayan: tuple[str, ...] = (),
) -> OnayliNiyet:
    """Mühürlü bir `OnayliNiyet` üretir. **Yalnızca `risk.motor` çağırır.**

    Ayrı bir fonksiyon olmasının sebebi `OnayliNiyet.__post_init__`in mührü *doğrulaması*,
    *üretmemesi*: doğrulama ile üretim aynı yerde olsaydı her kurulum kendi mührünü
    yazar ve mühür hiçbir şey kanıtlamazdı.
    """
    alanlar = (sinyal.model_dump_json(), onayli_maruziyet, limit_kimligi, karar_ms, kisitlayan)
    return OnayliNiyet(
        sinyal=sinyal,
        onayli_maruziyet=onayli_maruziyet,
        limit_kimligi=limit_kimligi,
        karar_ms=karar_ms,
        kisitlayan=kisitlayan,
        muhur=muhur.muhurle(alanlar),
    )


def dogrula(niyet: object) -> OnayliNiyet:
    """Execution kapısının çağırdığı doğrulayıcı. Geçmeyen her şey `MuhurGecersiz`.

    Tip kontrolü burada da yapılıyor (`isinstance`), yalnızca annotation'a güvenilmiyor:
    Python annotation'ları çalışma zamanında zorlanmaz ve bu kapı bir borsa emrinden
    önceki son kontrol.
    """
    if not isinstance(niyet, OnayliNiyet):
        raise muhur.MuhurGecersiz(
            f"execution yalnızca OnayliNiyet kabul eder, verilen: {type(niyet).__name__}. "
            "Sinyal doğrudan execution'a gidemez (§9.1/3)"
        )
    if not muhur.gecerli_mi(niyet._muhur_alanlari, niyet.muhur):
        raise muhur.MuhurGecersiz(
            "OnayliNiyet onay sonrası değiştirilmiş: mühür içeriğiyle uyuşmuyor (K-032)"
        )
    return niyet


__all__ = [
    "AZALTAN_YONLER",
    "Karar",
    "OnayliNiyet",
    "PortfoyKarari",
    "Red",
    "RedSebebi",
    "dogrula",
    "onayla",
]
