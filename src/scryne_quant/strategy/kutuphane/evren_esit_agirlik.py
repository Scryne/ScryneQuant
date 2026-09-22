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

from collections.abc import Mapping, Sequence
from dataclasses import replace
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
            if not baglam.hazir(*self._hazirlik_ozellikleri()):
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
                    skor=self._skor(baglam),
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
            self._ayarlar_icin(ctx),
            korelasyon=self._korelasyon_icin(ctx, adaylar),
            acik_pozisyonlar=tuple(s for s in ctx.acik_pozisyonlar() if s in ctx.gorunur()),
        )

    def _korelasyon_icin(
        self, ctx: EvrenBaglam, adaylar: Sequence[Aday]
    ) -> Mapping[tuple[str, str], float] | None:
        """Bu barın korelasyon matrisi (`kur(korelasyon=)`). Kıyas: **yok** (`None`) — `sec`
        budama yapmaz, Faz 10 davranışı bit-aynı. R7 `evren_korelasyon_budama` doldurur."""
        return None

    def _ayarlar_icin(self, ctx: EvrenBaglam) -> KurmaAyarlari:
        """Bu barın kurma ayarları. Kripto: sabit (Faz 10 davranışı, bit-aynı)."""
        return self._ayarlar

    def _hazirlik_ozellikleri(self) -> tuple[str, ...]:
        """Adayın ısınmış olması gereken özellikler. Kripto: ATR **ve** kote hacim."""
        return ("atr", "kote_hacim")

    def _skor(self, baglam: Any) -> float:
        """Sıralama skoru: evren kuralının kendi ölçütü (kripto: 30 günlük kote hacim)."""
        return float(baglam.ozellik("kote_hacim"))

    def _aday_uyeler(self, ctx: EvrenBaglam) -> tuple[str, ...]:
        """Sıralamaya girecek üyeler. Kıyasta hepsi; alt sınıf yalnızca **daraltabilir**.

        Faz 12'nin türev filtreleri (`evren_funding.py`) bu kancayı kullanıyor: filtre kıyasın
        üstüne tek bir dışlama adımı koyar, seçim/boyut/dengeleme aynen kalır ve dışlama
        oranı 0 iken sonuç kıyasla bit düzeyinde aynıdır (testle).
        """
        return ctx.uyeler()

    def sozluk(self) -> dict[str, Any]:
        return super().sozluk() | {"kiyas": True}


class FxEvrenEsitAgirlik(EvrenEsitAgirlik):
    """FX evren kıyası: hacimsiz. (K-099, R5 Paket 2; K-030)

    **Tanım:** her yeniden dengeleme anında (`yeniden_dengele_bar`, 1h'te 120 = bir seans
    haftası) `t`de PIT üyesi olan (`dosya-var` kuralı, `fx_evren`) ve barı `ok` olan **tüm**
    çiftler eşit ağırlıkla tutulur (`hedef_brut` toplam, `azami_agirlik` tavanı); üyelikten
    düşen çift bir sonraki dengelemede kapatılır. Giriş/çıkış yalnız üyelik + dengeleme
    periyodundan gelir — fiyat, momentum, hacim yok. Fill/spread/slippage/finansman mevcut
    motor hattından (K-094/K-095/K-096).

    **Neden hacim gerektirmiyor:** FXCM hacim vermiyor (K-088) ve FX evren kuralı hacimle
    sıralamıyor — `dosya-var` bir varlık kuralı. Kripto kıyasının sıralaması evren kuralının
    ölçütünü (kote hacim) yansıtır; burada evren kuralında sıralama **yok**, dolayısıyla
    kıyasta da yok: skor sabit 0, tavan bağlarsa sıra sembol adına düşer (`kur` sözleşmesi,
    `(-skor, sembol)`). Bu yüzden `azami_enstruman` varsayılanı sözleşmedeki çift sayısı
    (21): tavan bağlamaz, "evrenin tamamını taşıyorum" cümlesi doğru kalır. Daha küçük bir
    tavan alfabetik bir alt küme demektir — uydurma değil, ama kıyas da değil; parametre
    kayda giriyor. Hacim **uydurulmaz**: `volume`/`quote_volume` NaN kalır, ısınma yalnız ATR.
    """

    ad = "fx_evren_esit_agirlik"

    #: Varsayılan brüt hedef (K-100/3): %2 nakit payı rollover bedeli için. Kaldıraçsız portföyde
    #: borç yok (K-095); %100 yatırılmış kıyas ilk rollover'da durur (ölçüldü: 21 çift, AUDCAD bar
    #: 138). Pay ölçülmüş en yüksek proxy bedeline göre: 0,411 bps/gün × 365 ≈ %1,5/yıl (K-098).
    HEDEF_BRUT_FX = 0.98

    def __init__(
        self,
        yeniden_dengele_bar: int = 120,
        azami_enstruman: int = 21,
        azami_agirlik: float = 0.30,
        hedef_brut: float = HEDEF_BRUT_FX,
        esit_agirlik: bool = True,
    ) -> None:
        super().__init__(
            yeniden_dengele_bar=yeniden_dengele_bar,
            azami_enstruman=azami_enstruman,
            azami_agirlik=azami_agirlik,
            hedef_brut=hedef_brut,
            esit_agirlik=esit_agirlik,
        )

    def ozellikler(self) -> Sequence[OzellikTanimi]:
        return (OzellikTanimi("atr", "atr", {"pencere": ATR_PENCERESI}),)

    def isinma_bar(self) -> int:
        return ATR_PENCERESI + 2

    def _hazirlik_ozellikleri(self) -> tuple[str, ...]:
        return ("atr",)

    def _skor(self, baglam: Any) -> float:
        return 0.0

    def _ayarlar_icin(self, ctx: EvrenBaglam) -> KurmaAyarlari:
        """Barı olmayan (satılamayan) açık pozisyonların payı brüt hedeften düşülür (K-100/3).

        Ölçüldü: CADCHF'nin `bozuk` haftasında (2024-18) çift görünmezken hedef 0,98 geri kalan 20
        çifte dağıtılıyor, satılamayan %4,7 üstüne binince nakit sıfırlanıyor ve rollover K-095 ile
        koşuyu durduruyordu. Kıyasın tanımı "brüt ≤ 0,98"dir; görünmeyen pozisyon da brütün parçası.
        Kripto kıyasına dokunulmadı (Faz 12'nin `bayat_degerleme` ölçümü aynı kalsın).
        """
        gorunur = set(ctx.gorunur())
        takili = sum(
            ctx.pozisyon(s).exposure for s in ctx.acik_pozisyonlar() if s not in gorunur
        )
        if takili <= 0.0:
            return self._ayarlar
        hedef = max(self._ayarlar.hedef_brut - takili, 1e-9)
        return replace(self._ayarlar, hedef_brut=hedef)

    def sozluk(self) -> dict[str, Any]:
        return super().sozluk() | {"hacimsiz": True}


__all__ = ["ATR_PENCERESI", "HACIM_PENCERESI", "EvrenEsitAgirlik", "FxEvrenEsitAgirlik"]
