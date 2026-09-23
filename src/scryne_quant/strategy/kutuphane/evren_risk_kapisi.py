"""Evren kıyasının üstüne piyasa rejimi kapısı: risk kapalıyken nakit. (K-130, C fazı, RYPP)

**Soru (K-125):** Evren kıyasının (hacimde ilk 10, eşit ağırlık, haftalık dengeleme) büyük
düşüşlerini, piyasanın kendi uzun vadeli trendi bozulduğunda nakde geçerek azaltmak, getiriyi
kabul edilebilir ölçüde koruyarak mümkün mü? Bu bir alfa iddiası değil, risk yönetimi iddiası;
promotion yolu RYPP'dir (plasebo, iki vintage bağımsız doğrulama).

## Önden sabitlenen kural (ızgara yok, tek nokta)

- **Rejim:** `rejim_sembol` (BTCUSDT) kapanışı kendi `rejim_pencere` barlık (4800 × 1h = 200
  gün) basit hareketli ortalamasının üstündeyse **risk açık**, değilse **kapalı**. 200 günlük
  ortalama literatürün standart trend filtresi; değer sonuçlara bakılarak seçilmedi ve taranmadı.
- **Kontrol:** her `kontrol_bar` barda bir (24 = günde bir). Karar bar kapanışında, dolum sonraki
  barın açılışında (K-004, motor).
- **Risk açık:** kıyasın kendisi (seçim, eşit ağırlık, haftalık dengeleme aynen). Kapalıdan açığa
  geçişte dengeleme hemen yapılır.
- **Risk kapalı:** bütün açık pozisyonlar kapatılır, yeni pozisyon alınmaz; nakit getirisi 0
  (motorla aynı, K-125 tutucu yön).
- **Rejim bilgisi yoksa** (sembol görünmüyor ya da ortalama ısınmamış): risk **kapalı**. Makro
  engelinden (K-060) farkı bilerek: burada kapı çıkışı da yönetiyor ve bilinmeyen rejimde risk
  almamak tutucu yöndür.

Kıyastan tek farkı zamanlama; bu yüzden P3 plasebosu (rejim takviminin dairesel kaydırılmışı)
sorunun doğru sıfır noktasıdır.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.evren import EvrenBaglam, EvrenDisi
from scryne_quant.strategy.hedef import HedefPortfoy
from scryne_quant.strategy.kurma import kur
from scryne_quant.strategy.kutuphane.evren_esit_agirlik import EvrenEsitAgirlik

REJIM = "rejim_sma"


class EvrenRiskKapisi(EvrenEsitAgirlik):
    """Kıyas portföyü; `rejim_sembol` 200 günlük ortalamasının altındayken nakit."""

    ad = "evren_risk_kapisi"

    def __init__(
        self,
        rejim_sembol: str = "BTCUSDT",
        rejim_pencere: int = 4800,
        kontrol_bar: int = 24,
        azami_enstruman: int = 10,
        yeniden_dengele_bar: int = 168,
        hedef_brut: float = 1.0,
    ) -> None:
        super().__init__(
            yeniden_dengele_bar=yeniden_dengele_bar,
            azami_enstruman=azami_enstruman,
            azami_agirlik=float(hedef_brut) / int(azami_enstruman),
            hedef_brut=hedef_brut,
            esit_agirlik=True,
        )
        self.parametreler = {
            "rejim_sembol": rejim_sembol,
            "rejim_pencere": rejim_pencere,
            "kontrol_bar": kontrol_bar,
            "azami_enstruman": azami_enstruman,
            "yeniden_dengele_bar": yeniden_dengele_bar,
            "hedef_brut": hedef_brut,
        }
        self.dogrula()
        self._risk_acik: bool | None = None
        self._son_kontrol: int | None = None
        self.gecis = 0
        """Rejim değişimi sayısı (ölçüm, karar değil)."""

    def dogrula(self) -> None:
        p = self.parametreler
        if int(p["yeniden_dengele_bar"]) < 1 or int(p.get("kontrol_bar", 1)) < 1:
            raise ValueError("yeniden_dengele_bar ve kontrol_bar ≥ 1 olmalı")
        if "rejim_pencere" in p and int(p["rejim_pencere"]) < 2:
            raise ValueError("rejim_pencere ≥ 2 olmalı")

    def hazirla(self) -> None:
        super().hazirla()
        self._risk_acik = None
        self._son_kontrol = None
        self.gecis = 0

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (*super().ozellikler(),
                OzellikTanimi(REJIM, "sma", {"pencere": int(self.parametreler["rejim_pencere"])}))

    def isinma_bar(self) -> int:
        return max(super().isinma_bar(), int(self.parametreler["rejim_pencere"]) + 2)

    def _rejim(self, ctx: EvrenBaglam) -> bool:
        """Risk açık mı? Bilinmiyorsa kapalı (tutucu)."""
        try:
            b = ctx.enstruman(str(self.parametreler["rejim_sembol"]))
        except EvrenDisi:
            return False
        if not b.hazir(REJIM):
            return False
        return b.bar("close") > b.ozellik(REJIM)

    def on_bar(self, ctx: EvrenBaglam) -> HedefPortfoy | None:
        i = ctx.uzunluk - 1
        if self._son_kontrol is None or i - self._son_kontrol >= int(
            self.parametreler["kontrol_bar"]
        ):
            self._son_kontrol = i
            acik = self._rejim(ctx)
            if acik != self._risk_acik:
                self._risk_acik = acik
                self.gecis += 1
                if acik:
                    self._son_dengeleme = None  # açığa geçişte hemen dengele
                else:
                    kapat = tuple(s for s in ctx.acik_pozisyonlar() if s in ctx.gorunur())
                    self._son_dengeleme = None
                    return kur(ctx.zaman, [], self._ayarlar, acik_pozisyonlar=kapat) if kapat \
                        else None
        if not self._risk_acik:
            return None
        return super().on_bar(ctx)

    def sozluk(self) -> dict[str, Any]:
        govde = super().sozluk()
        govde.pop("kiyas", None)
        return govde


__all__ = ["REJIM", "EvrenRiskKapisi"]
