"""Evren kıyasının üstüne **konumlanma** dışlaması. (Faz 16, `konumlanma_evren` programı)

Program kaydı `docs/Arastirma-Programlari.jsonl` (kimlik `ccf75606a8ab0d52`), taslak
`docs/arsiv/Faz-16-Konumlanma-Program-Taslagi.md`, kaynak ölçüsü
`runs/faz16/kaynak-olcumu-konumlanma.json`.

**Soru:** Faz 12 kalabalığın *fiyatını* ölçtü (funding) ve vadeli talebi (basis); dördü de
kıyası geçemedi. Burada aynı olgu **miktar ve bileşim** tarafından ölçülüyor: kaç sözleşme
açık, pozisyonlar kimde ve agresif akış hangi yönde.

**Mekanizma iddiası:** pozisyon yoğunlaşması tasfiyeye açıklıktır. Kaldıraç, fiyat hareketi
olmadan da birikebilir; funding bunu ancak taşıma maliyeti yükseldiğinde gösterir, açık
pozisyon doğrudan gösterir.

## Önden sabitlenen kurallar (funding ailesiyle **birebir aynı**)

- Tasarım: kıyas + **tek** dışlama. Seçim, eşit ağırlık, tavan ve dengeleme takvimi kıyasla
  aynı; `dislama_orani = 0` iken sonuç kıyasla bit düzeyinde aynıdır (testli).
- **Skoru olmayan üye dışlanmaz.** Perp'i yok, verisi yok ya da seri bayat (`BAYAT_MS`):
  kalabalık bilgisi yok demektir, kalabalık var demek değil.
- **Kesim:** skoru olan `m` üye arasında en yüksek `ceil(oran × m)` tanesi; eşitlikte sembol
  adına göre.
- **Karar anı:** yeniden dengeleme barı, kıyasla aynı takvim. Skor `t`de görülebilen
  gözlemlerden (`create_time + 5 dk ≤ t`, K-052/15).
- Filtre yalnızca **daraltır** (K-037'nin ruhu): konumlanma bir sembolü evrene sokamaz.

## Dört çekiliş (bütçe 4, durma kuralı program kaydında)

| Sınıf | Skor | Soru |
| --- | --- | --- |
| `evren_oi_birikim` | Açık pozisyonun `pencere` barlık log değişimi | Kaldıraç birikimi |
| `evren_taker_baski` | Taker long/short oranının ortalaması | Agresif alım baskısı |
| `evren_buyuk_hesap` | Büyük hesap long/short ortalaması | Kalabalığın **kim** olduğu |
| `evren_oi_taker` | İlk ikisinin kesit sırası ortalaması | İkisi birlikte |
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import ClassVar

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.evren import EvrenBaglam

# Aynı iskelet: "kıyas + tek dışlama" mantığı tek yerde yaşıyor (K-001). Funding ailesinden
# miras almak, iki ailenin seçim/kurma katmanının sessizce ayrışmasını imkânsız kılıyor.
from scryne_quant.strategy.kutuphane.evren_funding import (
    SKOR,
    EvrenFundingBirikim,
    _FundingDislama,
    _sira,
)

#: İkinci skorun özellik adı (`evren_oi_taker`).
TAKER = "taker_skor"


class EvrenOiBirikim(EvrenFundingBirikim):
    """Son `pencere` barda açık pozisyonu (sözleşme adedi) en çok artan dilimi dışla."""

    ad: ClassVar[str] = "evren_oi_birikim"

    def _skor_ozelligi(self) -> OzellikTanimi:
        return OzellikTanimi(
            SKOR, "acik_pozisyon_degisimi", {"pencere": int(self.parametreler["pencere"])}
        )


class EvrenTakerBaski(EvrenFundingBirikim):
    """Son `pencere` barın ortalama taker long/short oranı en yüksek dilimi dışla."""

    ad: ClassVar[str] = "evren_taker_baski"

    def _skor_ozelligi(self) -> OzellikTanimi:
        return OzellikTanimi(SKOR, "taker_sma", {"pencere": int(self.parametreler["pencere"])})


class EvrenBuyukHesap(EvrenFundingBirikim):
    """Büyük hesapların long/short oranı en yüksek dilimi dışla."""

    ad: ClassVar[str] = "evren_buyuk_hesap"

    def _skor_ozelligi(self) -> OzellikTanimi:
        return OzellikTanimi(
            SKOR, "buyuk_hesap_sma", {"pencere": int(self.parametreler["pencere"])}
        )


class EvrenOiTaker(EvrenOiBirikim):
    """Açık pozisyon birikimi ve taker baskısının kesit sırası ortalaması en yüksek dilim.

    `evren_funding_basis` ile birebir aynı birleştirme kuralı: iki skoru da olan üye sıralanır,
    birinden yoksun üye **dışlanmaz** (bilginin yokluğu kalabalık kanıtı değildir).

    Birinci skor `EvrenOiBirikim`den miras alınır (açık pozisyon birikimi); ikinci skor taker
    ortalaması. Miras zinciri funding ailesine değil konumlanmaya bağlı — aksi hâlde birinci
    skor sessizce funding olurdu (testte yakalandı).
    """

    ad: ClassVar[str] = "evren_oi_taker"

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        w = int(self.parametreler["pencere"])
        return (*super().ozellikler(), OzellikTanimi(TAKER, "taker_sma", {"pencere": w}))

    def _aday_uyeler(self, ctx: EvrenBaglam) -> tuple[str, ...]:
        uyeler = ctx.uyeler()
        oran = float(self.parametreler["dislama_orani"])
        if oran <= 0.0:
            return uyeler
        adlar, oi, taker = [], [], []
        for sembol in uyeler:
            b = ctx.enstruman(sembol)
            if b.hazir(SKOR, TAKER):
                adlar.append(sembol)
                oi.append(b.ozellik(SKOR))
                taker.append(b.ozellik(TAKER))
        if not adlar:
            return uyeler
        birlesik = (_sira(oi) + _sira(taker)) / 2.0
        kesim = math.ceil(oran * len(adlar))
        sirali = sorted(zip((-s for s in birlesik), adlar, strict=True))
        dislanan = {s for _, s in sirali[:kesim]}
        return tuple(s for s in uyeler if s not in dislanan)


#: Program çekilişlerinin sırası (durma kuralı ilk ikisine bakar).
KONUMLANMA_AILELERI: dict[str, type[_FundingDislama]] = {
    EvrenOiBirikim.ad: EvrenOiBirikim,
    EvrenTakerBaski.ad: EvrenTakerBaski,
    EvrenBuyukHesap.ad: EvrenBuyukHesap,
    EvrenOiTaker.ad: EvrenOiTaker,
}

__all__ = ["KONUMLANMA_AILELERI", "EvrenBuyukHesap", "EvrenOiBirikim", "EvrenOiTaker",
           "EvrenTakerBaski"]
