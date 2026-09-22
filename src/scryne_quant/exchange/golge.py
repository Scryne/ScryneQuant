"""Shadow adaptörü: gerçek hesabı okur, **emir gönderemez**. (Faz-8-Hazirlik §1, K-114)

Shadow = canlı modun tamamı, emir gönderimi hariç. Gerçek bakiye, gerçek sembol kuralları,
gerçek fiyat okunur; niyet risk motorundan geçer, emir kurulur, kurallara uydurulur,
deftere `GOLGE` olarak yazılır — ve ağa **çıkmaz**.

**"Gönderilmez" garantisi dört katmanlıdır ve hiçbiri diğerine yaslanmaz:**

1. **Anahtar** (birinci ve asıl katman): shadow yalnızca `enableSpotAndMarginTrading=false`
   bir anahtarla açılır (`exchange/canli.yetki_denetle("shadow", …)`). Kod bütün diğer
   katmanları bir hatayla aşsa bile borsa `-2015` ile reddeder.
2. **Taşıma:** alttaki okuyucu `salt_okunur=True` kurulmuş olmak **zorunda**; `GET`
   dışındaki her istek kurulmadan `SaltOkunurIhlali` ile reddedilir (`imzali.py`).
3. **Adaptör:** bu sınıfın yazma metodları (`market_emri`, `limit_emri`, `emir_iptal`)
   hiçbir şeyi çağırmadan `GolgeGonderim` fırlatır.
4. **Emir motoru:** `EmirMotoru.gonder` `GOLGE` özniteliğini görünce emri `VALIDATED →
   GOLGE` geçirir ve `SUBMITTED`a hiç uğramaz (`execution/motor.golge_mi`).

`tests/unit/test_golge.py` her katmanı ayrı ayrı ve birlikte sınar.
"""

from __future__ import annotations

from typing import Any, Final

from scryne_quant.exchange.emir_adaptoru import BorsaEmri, EmirAdaptoru, Komisyon, Varlik
from scryne_quant.exchange.kurallar import SembolKurallari


class GolgeGonderim(PermissionError):
    """Shadow adaptöründen yazma istendi. Hiçbir ağ çağrısı yapılmadı."""


class GolgeAdaptoru(EmirAdaptoru):
    """Okumaları gerçek (salt okunur) adaptöre delege eder, yazmaları reddeder."""

    #: `execution/motor.golge_mi` bunu okur. Yalnızca bu sınıfta `True`.
    GOLGE: Final = True
    GERCEK_EMIR: Final = False

    def __init__(self, okuyucu: Any) -> None:
        # Paper borsa da okuyucu olabilir (shadow'u ağsız sınamak için); onun zaten emir
        # gönderme yeteneği yok. Gerçek imzalı adaptör ise salt okunur kurulmuş olmalı.
        salt = getattr(okuyucu, "salt_okunur", None)
        gercek = getattr(okuyucu, "GERCEK_EMIR", True)
        if gercek and salt is not True:
            raise GolgeGonderim(
                "shadow'un okuyucusu salt okunur kurulmalı (`canli.canli_okuyucu`); emir "
                "gönderebilen bir adaptör shadow'a verilemez (K-114)"
            )
        self._o = okuyucu

    # ------------------------------------------------------------------ okuma

    def sunucu_zamani_ms(self) -> int:
        return int(self._o.sunucu_zamani_ms())

    def saat_sapmasi_ms(self) -> int:
        return int(self._o.saat_sapmasi_ms())

    def sembol_kurallari(self, sembol: str) -> SembolKurallari:
        return self._o.sembol_kurallari(sembol)

    def son_fiyat(self, sembol: str) -> float:
        return float(self._o.son_fiyat(sembol))

    def emir_sorgula(self, *, sembol: str, istemci_kimligi: str) -> BorsaEmri | None:
        return self._o.emir_sorgula(sembol=sembol, istemci_kimligi=istemci_kimligi)

    def acik_emirler(self, sembol: str) -> list[BorsaEmri]:
        return list(self._o.acik_emirler(sembol))

    def bakiye(self) -> dict[str, Varlik]:
        return dict(self._o.bakiye())

    def emir_islemleri(self, *, sembol: str, borsa_kimligi: str) -> Komisyon:
        return self._o.emir_islemleri(sembol=sembol, borsa_kimligi=borsa_kimligi)

    # ------------------------------------------------------------------ yazma: yok

    def market_emri(self, **_: Any) -> BorsaEmri:
        raise GolgeGonderim("shadow: market emri gönderilmez")

    def limit_emri(self, **_: Any) -> BorsaEmri:
        raise GolgeGonderim("shadow: limit emri gönderilmez")

    def emir_iptal(self, **_: Any) -> BorsaEmri | None:
        raise GolgeGonderim("shadow: iptal gönderilmez (shadow'un açık emri olamaz)")


__all__ = ["GolgeAdaptoru", "GolgeGonderim"]
