"""Evren kıyası: PIT evrenin tamamını taşı, periyodik yeniden dengele. (K-030, Faz 10)

**Bu bir alfa adayı değil, bir kıyastır.** K-030 her karşılaştırmada al-tut kıyasının
bulunmasını istiyor; tek sembolde o kıyas `al_tut`, evrende ise **evrenin kendisi**:
"hiçbir seçim yapmadan, o ay listelenmiş likit isimlerin hepsini taşısaydım ne olurdu".
Cross-sectional bir ailenin katma değeri ancak bu çizginin üstüne çıkarak gösterilebilir.

Kıyas olduğu için **hipotez defterine çekiliş olarak girmez** (K-039/K-051): bir soru
sormuyor, sorulan soruların ölçüleceği sıfır noktasını tanımlıyor. Aynı sebeple K-045'in
"yeni strateji/aile/parametre çekilişi yapılmayacak" kuralını da delmiyor — Faz 4'ün
`al_tut`u da o kuralın kapsamı dışındaydı.

İki varyantı var ve ikisi de aynı kıyasın parçası:

- `esit_agirlik=True` — saf kıyas: seçim yok, boyutlandırma yok.
- `esit_agirlik=False` — oynaklık ayarlı: **boyutlandırmanın** tek başına ne kattığını
  ölçer. İkisinin farkı "portföy kurma yöntemi bir şey yapıyor mu" sorusunun cevabı; tek
  başına oynaklık ayarlı hâli raporlamak, o farkı görünmez kılardı.

Yeniden dengeleme periyodu bar cinsinden ve **bir parametredir**: evren üyeliği aylık
değişiyor, ama portföy her barda hedefe dönmek zorunda değil — her barda dönmek turnover
maliyetini ödemek demek. Bu sayının iştahı Faz 12'nin ölçeceği şey.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.strategy.evren import EvrenBaglam
from scryne_quant.strategy.hedef import HedefPortfoy
from scryne_quant.strategy.kurma import Aday, KurmaAyarlari, kur, oynaklik_olculebilir
from scryne_quant.strategy.temel import PortfoyStratejisi

#: Boyutlandırmanın oynaklık ölçüsü. Risk motorunun `RISK_ATR_PENCERESI`siyle aynı sayı ve
#: bu tesadüf değil: aynı büyüklüğü iki farklı pencereyle ölçmek, kurma katmanı ile risk
#: katmanının aynı pozisyon hakkında farklı şeyler söylemesine yol açardı.
ATR_PENCERESI = 14

#: Sıralama ölçüsünün penceresi (bar). 1h'te 720 bar = 30 gün; evren kuralının aylık
#: `quote_volume` toplamıyla **aynı büyüklük ve aynı ufuk**. Aynı olması şart: kıyasın
#: sıralaması evren kuralından farklı bir şey ölçseydi, "evreni taşıyorum" cümlesi
#: doğru olmazdı.
HACIM_PENCERESI = 720


class EvrenEsitAgirlik(PortfoyStratejisi):
    """Evrenin üyelerini (en fazla `azami_enstruman` tanesini) taşıyan kıyas portföyü."""

    ad = "evren_esit_agirlik"

    def __init__(
        self,
        yeniden_dengele_bar: int = 720,
        azami_enstruman: int = 10,
        azami_agirlik: float = 0.30,
        hedef_brut: float = 1.0,
        esit_agirlik: bool = True,
    ) -> None:
        super().__init__(
            yeniden_dengele_bar=yeniden_dengele_bar,
            azami_enstruman=azami_enstruman,
            azami_agirlik=azami_agirlik,
            hedef_brut=hedef_brut,
            esit_agirlik=esit_agirlik,
        )
        self._ayarlar = KurmaAyarlari(
            yontem="EVREN_ESIT" if esit_agirlik else "EVREN_OYNAKLIK",
            azami_enstruman=azami_enstruman,
            azami_agirlik=azami_agirlik,
            hedef_brut=hedef_brut,
            esit_agirlik=esit_agirlik,
        )
        self._son_dengeleme: int | None = None

    def dogrula(self) -> None:
        if int(self.parametreler["yeniden_dengele_bar"]) < 1:
            raise ValueError("yeniden_dengele_bar ≥ 1 olmalı")

    def hazirla(self) -> None:
        self._son_dengeleme = None

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (
            OzellikTanimi("atr", "atr", {"pencere": ATR_PENCERESI}),
            OzellikTanimi("kote_hacim", "kote_hacim_sma", {"pencere": HACIM_PENCERESI}),
        )

    def isinma_bar(self) -> int:
        return max(ATR_PENCERESI, HACIM_PENCERESI) + 2

    def on_bar(self, ctx: EvrenBaglam) -> HedefPortfoy | None:
        periyot = int(self.parametreler["yeniden_dengele_bar"])
        i = ctx.uzunluk - 1
        if self._son_dengeleme is not None and i - self._son_dengeleme < periyot:
            return None

        adaylar: list[Aday] = []
        for sembol in self._aday_uyeler(ctx):
            baglam = ctx.enstruman(sembol)
            if not baglam.hazir("atr", "kote_hacim"):
                # Isınmamış bir enstrümanda boyut hesaplanmaz. Eşit ağırlık varyantında
                # oynaklık kullanılmıyor ama aday yine de dışarıda kalıyor: iki varyantın
                # **aynı** evreni görmesi, farkın yalnızca boyutlandırmadan gelmesini
                # sağlıyor. Aksi hâlde eşit ağırlıklı varyant daha geniş bir evrenle
                # koşardı ve karşılaştırma iki şeyi birden değiştirirdi.
                continue
            fiyat = baglam.bar("close")
            if fiyat <= 0.0:
                continue
            oynaklik = baglam.ozellik("atr") / fiyat
            if not oynaklik_olculebilir(oynaklik):
                # Ölçülemeyen oynaklık = aday değil (kurma.py başlığı, R1(c)). Eşit ağırlık
                # varyantı oynaklığı kullanmıyor ama sembol yine dışarıda kalıyor — ısınma
                # kontrolüyle aynı gerekçe: iki varyant aynı evreni görmeli.
                continue
            adaylar.append(
                Aday(
                    sembol=sembol,
                    # Sıra, evren kuralının kendi ölçütüyle **aynı** büyüklükten:
                    # 30 günlük ortalama kote hacim. Skoru sabit bırakmak sıralamayı
                    # sembol adına düşürürdü — yani tavan bağladığında kıyas, evrenin
                    # alfabetik ilk N'ini taşıyan keyfi bir alt küme olurdu. Ölçüldü:
                    # 205 sembollü pencerede tavan gerçekten bağlıyor (Faz 10 raporu §5).
                    skor=baglam.ozellik("kote_hacim"),
                    oynaklik=oynaklik,
                    mevcut_agirlik=ctx.pozisyon(sembol).exposure,
                    reason="EVREN_KIYASI",
                    confidence=0.5,
                )
            )

        if not adaylar and not ctx.acik_pozisyonlar():
            return None

        self._son_dengeleme = i
        return kur(
            ctx.zaman,
            adaylar,
            self._ayarlar,
            acik_pozisyonlar=tuple(s for s in ctx.acik_pozisyonlar() if s in ctx.gorunur()),
        )

    def _aday_uyeler(self, ctx: EvrenBaglam) -> tuple[str, ...]:
        """Sıralamaya girecek üyeler. Kıyasta hepsi; alt sınıf yalnızca **daraltabilir**.

        Faz 12'nin türev filtreleri (`evren_funding.py`) bu kancayı kullanıyor: filtre kıyasın
        üstüne tek bir dışlama adımı koyar, seçim/boyut/dengeleme aynen kalır ve dışlama
        oranı 0 iken sonuç kıyasla bit düzeyinde aynıdır (testle).
        """
        return ctx.uyeler()

    def sozluk(self) -> dict[str, Any]:
        return super().sozluk() | {"kiyas": True}


__all__ = ["ATR_PENCERESI", "HACIM_PENCERESI", "EvrenEsitAgirlik"]
