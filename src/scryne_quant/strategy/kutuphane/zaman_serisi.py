"""Zaman serisi trend ailesi: yalnız kendi geçmişine göre yükselen üyeler taşınır. (R5, `fx_fiyat`)

Kesitsel ailelerden (`kesitsel.py`) farkı **sorunun kendisi**: kesitsel güç "evrenin en iyi
N'i kim" diye sorar ve her dengelemede N isim taşır — evrenin tamamı düşüyor olsa bile.
Zaman serisi trend "hangi üyeler kendi son `pencere` barında yükseldi" diye sorar; yükselen
yoksa **hiç pozisyon almaz**, nakitte kalır. İki aile aynı skoru (`roc`) okur ama biri
sıralar, öteki eşikler; bu yüzden ayrı ailedir ve ayrı çekiliştir (K-039).

İskelet kesitsel ailelerinkiyle aynı (`_Kesitsel`): aynı yeniden dengeleme takvimi, aynı
kurma katmanı, eşit ağırlık, `hedef_brut` sabit. Tek fark aday filtresi: `roc ≤ 0` olan üye
adaya girmez. `azami_enstruman` tavanı yükselenler arasında en güçlü N'i seçer; tavan
bağlamıyorsa (yükselen sayısı ≤ N) "yükselen her şeyi eşit taşı" hâline gelir.

**Yalnız uzun.** Motor ve finansman modeli bugün kısa bacağı taşımıyor (K-095: short
rollover modelde yok). Düşen üyeyi kısa satmak bu ailenin doğal ikinci yarısı olurdu; o
yarı finansman kısa bacağı ölçülene kadar **sorulmuyor**, uydurulmuyor.
"""

from __future__ import annotations

from typing import Any

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.evren import EvrenBaglam
from scryne_quant.strategy.hedef import HedefPortfoy
from scryne_quant.strategy.kurma import Aday, kur, oynaklik_olculebilir
from scryne_quant.strategy.kutuphane.kesitsel import _Kesitsel


class ZamanSerisiTrend(_Kesitsel):
    """Son `pencere` bar getirisi pozitif olan üyeler; en güçlü `azami_enstruman` tanesi."""

    ad = "zaman_serisi_trend"
    neden = "ZAMAN_SERISI_TREND"

    def _skor_ozelligi(self) -> OzellikTanimi:
        return OzellikTanimi("skor_ham", "roc", {"pencere": int(self.parametreler["pencere"])})

    def _skor(self, baglam: Any) -> float:
        return baglam.ozellik("skor_ham")

    def on_bar(self, ctx: EvrenBaglam) -> HedefPortfoy | None:
        periyot = int(self.parametreler["yeniden_dengele_bar"])
        i = ctx.uzunluk - 1
        if self._son_dengeleme is not None and i - self._son_dengeleme < periyot:
            return None

        adaylar: list[Aday] = []
        for sembol in ctx.uyeler():
            baglam = ctx.enstruman(sembol)
            if not baglam.hazir("atr", "skor_ham"):
                continue
            fiyat = baglam.bar("close")
            if fiyat <= 0.0:
                continue
            oynaklik = baglam.ozellik("atr") / fiyat
            if not oynaklik_olculebilir(oynaklik):
                continue
            skor = self._skor(baglam)
            if not skor > 0.0:  # NaN da elenir: ölçülemeyen trend, trend değildir
                continue
            adaylar.append(
                Aday(
                    sembol=sembol,
                    skor=skor,
                    oynaklik=oynaklik,
                    mevcut_agirlik=ctx.pozisyon(sembol).exposure,
                    reason=self.neden,
                    confidence=0.5,
                )
            )

        if not adaylar and not ctx.acik_pozisyonlar():
            return None
        self._son_dengeleme = i
        # Aday yoksa `kur` açık pozisyonları kapatan bir hedef döndürür: yükselen kalmadıysa
        # portföy nakde döner. Kesitsel ailede bu durum yok — orada her zaman N aday var.
        return kur(
            ctx.zaman,
            adaylar,
            self._ayarlar,
            acik_pozisyonlar=tuple(s for s in ctx.acik_pozisyonlar() if s in ctx.gorunur()),
        )


__all__ = ["ZamanSerisiTrend"]
