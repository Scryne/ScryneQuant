"""Evren kıyasının üstüne funding dışlaması. (Faz 12, `turev_evren` programı)

Program kaydı `docs/Arastirma-Programlari.jsonl`, kaynak ölçüsü
`docs/Faz-12-Program-Taslaklari.md` §1.2.

**Soru:** K-042'nin `funding_filtre` mekanizması — aşırı pozitif funding, kaldıraçla
finanse edilmiş bir kalabalığın işaretidir ve o kalabalık tasfiyeye açıktır — evren
kesitinde tekrar ediyor mu? Tek sembolde (BTC) üç çekiliş denendi ve geçen olmadı.

**Tasarım: kıyas + tek bir dışlama.** Seçim (30 günlük kote hacme göre ilk N), eşit ağırlık,
yeniden dengeleme ve kurma katmanı `evren_esit_agirlik` ile **aynı**; tek fark, sıralamadan
önce funding skoru en yüksek `dislama_orani` kadar üyenin dışlanması. Dışlama oranı 0 iken
sonuç kıyasla bit düzeyinde aynıdır (testle). Böylece kıyasa göre fark yalnızca filtreye
atfedilebilir — K-042'nin "tek bir koşul ekle" kuralı.

**Filtre yalnızca daraltır** (K-037'nin ruhu): funding bir sembolü evrene sokamaz, yalnızca
çıkarabilir.

## Önden sabitlenen kurallar

- **Funding'i olmayan üye dışlanmaz.** Perp'i yok, henüz listelenmemiş ya da serisi bayat
  (`data/funding.BAYAT_MS`): kalabalık bilgisi yok demektir, kalabalık var demek değil.
  Dışlanırsa filtre funding'i değil perp varlığını ölçerdi.
- **Kesim:** skoru olan `m` üye arasında en yüksek `ceil(oran × m)` tanesi. Eşitlikte sembol
  adına göre (deterministik). `m = 0` ise dışlama yok.
- **Karar anı:** yeniden dengeleme barı, kıyasla aynı takvim. Skor `t`ye kadar
  **gerçekleşmiş** ödemelerden (`calc_time <= open_time`).
- **Açık pozisyonlar:** dışlanan bir sembol kıyasta olduğu gibi kurma katmanında kapatılır;
  filtre çıkışı engellemez.

## İki çekiliş

| Sınıf | Skor | Soru: en yüksek dilim geride mi kalıyor? |
| --- | --- | --- |
| `evren_funding_kesit` | son gerçekleşen oran (8 s eşdeğer) | Anlık kaldıraç baskısı |
| `evren_funding_birikim` | son `pencere` saatte ödenen toplam | Süregelen baskı |
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, ClassVar

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.evren import EvrenBaglam
from scryne_quant.strategy.kutuphane.evren_esit_agirlik import (
    ATR_PENCERESI,
    HACIM_PENCERESI,
    EvrenEsitAgirlik,
)

SKOR = "funding_skor"


class _FundingDislama(EvrenEsitAgirlik):
    """İki çekilişin ortak iskeleti. Alt sınıf yalnızca skor özelliğini tanımlar."""

    ad: ClassVar[str] = ""

    def __init__(
        self,
        dislama_orani: float = 0.2,
        azami_enstruman: int = 10,
        yeniden_dengele_bar: int = 168,
        hedef_brut: float = 0.2,
        **ek: Any,
    ) -> None:
        # Kıyasla aynı kurma ayarları: eşit ağırlık, tavan = eşit pay. Kıyas da
        # `azami_agirlik = hedef_brut / azami_enstruman` ile kurulur (koşucu ve test).
        super().__init__(
            yeniden_dengele_bar=yeniden_dengele_bar,
            azami_enstruman=azami_enstruman,
            azami_agirlik=float(hedef_brut) / int(azami_enstruman),
            hedef_brut=hedef_brut,
            esit_agirlik=True,
        )
        # Parametre sözlüğü kaydı taşıyor: kıyasın alanları + bu sınıfın alanları.
        self.parametreler = {
            "dislama_orani": dislama_orani,
            "azami_enstruman": azami_enstruman,
            "yeniden_dengele_bar": yeniden_dengele_bar,
            "hedef_brut": hedef_brut,
            **ek,
        }
        self.dogrula()

    def dogrula(self) -> None:
        p = self.parametreler
        if int(p["yeniden_dengele_bar"]) < 1:
            raise ValueError("yeniden_dengele_bar ≥ 1 olmalı")
        if int(p["azami_enstruman"]) < 1:
            raise ValueError("azami_enstruman ≥ 1 olmalı")
        if not 0.0 <= float(p.get("dislama_orani", 0.0)) < 1.0:
            raise ValueError("dislama_orani [0, 1) aralığında olmalı")
        if not 0.0 < float(p["hedef_brut"]) <= 1.0:
            raise ValueError("hedef_brut (0, 1] aralığında olmalı")

    def _skor_ozelligi(self) -> OzellikTanimi:
        raise NotImplementedError

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (*super().ozellikler(), self._skor_ozelligi())

    def isinma_bar(self) -> int:
        return max(ATR_PENCERESI, HACIM_PENCERESI, self._skor_isinmasi()) + 2

    def _skor_isinmasi(self) -> int:
        return 1

    def _aday_uyeler(self, ctx: EvrenBaglam) -> tuple[str, ...]:
        uyeler = ctx.uyeler()
        oran = float(self.parametreler["dislama_orani"])
        if oran <= 0.0:
            return uyeler
        skorlu = []
        for sembol in uyeler:
            b = ctx.enstruman(sembol)
            if b.hazir(SKOR):
                skorlu.append((-b.ozellik(SKOR), sembol))
        if not skorlu:
            return uyeler
        kesim = math.ceil(oran * len(skorlu))
        dislanan = {s for _, s in sorted(skorlu)[:kesim]}
        return tuple(s for s in uyeler if s not in dislanan)

    def sozluk(self) -> dict[str, Any]:
        govde = super().sozluk()
        govde.pop("kiyas", None)
        return govde


class EvrenFundingKesit(_FundingDislama):
    """Son gerçekleşen funding oranı (8 s eşdeğer) en yüksek dilimi dışla."""

    ad = "evren_funding_kesit"

    def _skor_ozelligi(self) -> OzellikTanimi:
        # Tek pencereli kayan toplam = değerin kendisi; `funding` alanını özellik olarak
        # `ctx`e taşımanın defterdeki yolu.
        return OzellikTanimi(SKOR, "funding_kumulatif", {"pencere": 1})


class EvrenFundingBirikim(_FundingDislama):
    """Son `pencere` saatte fiilen ödenen funding toplamı en yüksek dilimi dışla."""

    ad = "evren_funding_birikim"

    def __init__(
        self,
        pencere: int = 168,
        dislama_orani: float = 0.2,
        azami_enstruman: int = 10,
        yeniden_dengele_bar: int = 168,
        hedef_brut: float = 0.2,
    ) -> None:
        super().__init__(
            dislama_orani=dislama_orani,
            azami_enstruman=azami_enstruman,
            yeniden_dengele_bar=yeniden_dengele_bar,
            hedef_brut=hedef_brut,
            pencere=pencere,
        )

    def dogrula(self) -> None:
        super().dogrula()
        # Üst sınıfın kurucusu `dogrula`yı pencere henüz sözlükte yokken de çağırıyor.
        if int(self.parametreler.get("pencere", 1)) < 1:
            raise ValueError("pencere ≥ 1 olmalı")

    def _skor_isinmasi(self) -> int:
        return int(self.parametreler["pencere"])

    def _skor_ozelligi(self) -> OzellikTanimi:
        return OzellikTanimi(
            SKOR, "funding_odeme_toplami", {"pencere": int(self.parametreler["pencere"])}
        )


__all__ = ["SKOR", "EvrenFundingBirikim", "EvrenFundingKesit"]
