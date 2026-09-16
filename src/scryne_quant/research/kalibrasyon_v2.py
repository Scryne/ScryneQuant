"""K-054'ün yeni kapılarının eşiklerini **null dağılımından** kalibre eder. (Faz 11)

K-019 eşikleri Faz 4'ün ölçümlerine bakarak seçti; K-044 o yöntemin eksiğini ölçtü
(*"0,5 hiçbir zaman %5'lik bir kapı değildi"*) ve eşiği **edge'i olmayan bir dünyada**
ölçmeye geçti. Bu modül aynı yöntemi üç yeni kapıya uyguluyor:

    eşik = null dağılımının, istenen yanlış-pozitif oranına karşılık gelen persentili

Yani *"hiçbir stratejinin gerçek bir edge'i olmasaydı, bu kapı vakaların %5'inde
geçilirdi"* diyen sayı. Eşiğin gerekçesi bu yüzden bir yargı değil bir ölçüm, ve
**bugünkü sonuçlara bakılarak seçilmiyor** — null'a bakılarak seçiliyor.

## Null nasıl kuruluyor

`research/coklu_test.py`nin paylaşılan dairesel kaydırması aynen kullanılıyor: ızgaranın
her noktasının sinyal takvimi bir kez çıkarılır, sonra her iterasyonda **hepsi aynı
oranda** kaydırılıp gerçek motordan geçirilir. Korunanlar: sinyal sayısı, aralık deseni,
maruziyet dağılımı, ve noktalar arası korelasyon. Yok edilen tek şey fiyatla hizalanma —
yani edge.

Kaydırmanın **paylaşılması** burada K-044'tekinden bile önemli: ızgaranın komşu noktaları
neredeyse aynı stratejidir ve bağımsız kaydırma o benzerliği koparıp PBO'yu ile
pertürbasyonu tanınmaz hâle getirirdi.

## Üç kapı, üç pencere

| Kapı | Hangi pencerede ölçülür | Neden |
| --- | --- | --- |
| `pbo` | tam ölçüm penceresi | CSCV kendi IS/OOS bölmesini içeride kuruyor |
| `parametre_perturbasyonu` | in-sample | Seçim orada yapılıyor; komşuluk seçimin özelliği |
| `rejim_kararliligi` | out-of-sample | Kapı OOS performansını ölçüyor |

Null da **aynı pencerelerde** koşuyor. Farklı pencerede ölçmek istatistiğin örneklem
büyüklüğünü değiştirir ve dağılımın genişliğini olduğundan farklı gösterir — daha uzun
pencere daha dar dağılım, yani sessizce daha gevşek bir kapı.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np

from scryne_quant.backtest.sonuc import Sonuc
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.research import pbo as pbo_mod
from scryne_quant.research import perturbasyon as pert_mod
from scryne_quant.research import rejim as rejim_mod
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.coklu_test import BetikStrateji, kaydir, takvim_cikar
from scryne_quant.research.tarama import ASGARI_ISLEM, OLCUTLER, izgara, kosu
from scryne_quant.strategy.temel import Strateji

PERSENTILLER: Final[tuple[int, ...]] = (1, 5, 10, 25, 50, 75, 90, 95, 99)


class KalibrasyonHatasi(ValueError):
    """Kalibrasyon girdisi geçersiz."""


@dataclass(frozen=True, slots=True)
class NullOlcumu:
    """Bir istatistiğin edge'siz dünyadaki dağılımı."""

    ad: str
    yon: str
    """Kapının yönü: `>=` (büyük geçer) veya `<=` (küçük geçer)."""

    deneme: int
    seed: int
    gecerli_deneme: int
    """Ölçülebilen iterasyon sayısı. `deneme`den küçükse istatistik bazı turlarda
    tanımsız kalmış demektir ve bu okunmadan eşik seçilmemeli."""

    dagilim: dict[str, float]
    ornek: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))

    def esik(self, yanlis_pozitif: float = 0.05) -> float:
        """Verilen yanlış-pozitif oranına karşılık gelen eşik.

        `>=` kapısında üst kuyruk (null'ın %95'i eşiğin altında kalır), `<=` kapısında
        alt kuyruk. İki yönü tek fonksiyonda toplamak bilinçli: yönü elle seçmek, bir
        kapıda yanlış kuyruğu almanın en kolay yolu — ve o hata sessizdir, çünkü sayı
        makul görünür.
        """
        if not 0.0 < yanlis_pozitif < 1.0:
            raise KalibrasyonHatasi(
                f"yanlış-pozitif oranı (0,1) aralığında olmalı: {yanlis_pozitif}"
            )
        if self.ornek.size == 0:
            raise KalibrasyonHatasi(f"{self.ad}: null örneği boş, eşik türetilemez")
        yuzde = 100.0 * (1.0 - yanlis_pozitif) if self.yon == ">=" else 100.0 * yanlis_pozitif
        return float(np.percentile(self.ornek, yuzde))

    def guven_araligi(
        self, yanlis_pozitif: float = 0.05, *, deneme: int = 2_000, seed: int = 0
    ) -> tuple[float, float]:
        """Eşiğin %90 bootstrap güven aralığı. (K-044'ün zorunlu kıldığı okuma)

        Persentil bir **tahmin**: aralık genişse çare eşiği yuvarlamak değil, iterasyonu
        artırmaktır.
        """
        if self.ornek.size == 0:
            raise KalibrasyonHatasi(f"{self.ad}: null örneği boş")
        rng = np.random.default_rng(seed)
        yuzde = 100.0 * (1.0 - yanlis_pozitif) if self.yon == ">=" else 100.0 * yanlis_pozitif
        ornekler = np.array(
            [
                np.percentile(rng.choice(self.ornek, self.ornek.size, replace=True), yuzde)
                for _ in range(deneme)
            ]
        )
        return float(np.percentile(ornekler, 5)), float(np.percentile(ornekler, 95))

    def sozluk(self) -> dict[str, Any]:
        return {
            "ad": self.ad,
            "yon": self.yon,
            "deneme": self.deneme,
            "gecerli_deneme": self.gecerli_deneme,
            "seed": self.seed,
            "dagilim": self.dagilim,
            "ornek": [float(x) for x in self.ornek],
        }


def _null_olcumu(ad: str, yon: str, ornek: list[float], deneme: int, seed: int) -> NullOlcumu:
    dizi = np.array([x for x in ornek if np.isfinite(x)], dtype=np.float64)
    return NullOlcumu(
        ad=ad,
        yon=yon,
        deneme=deneme,
        seed=seed,
        gecerli_deneme=int(dizi.size),
        dagilim={f"p{p:02d}": float(np.percentile(dizi, p)) for p in PERSENTILLER}
        if dizi.size
        else {},
        ornek=dizi,
    )


@dataclass(frozen=True, slots=True)
class IzgaraTakvimi:
    """Izgaranın bir penceredeki sinyal takvimleri — null'ın girdisi.

    Takvimler **bir kez** çıkarılıyor: her iterasyonda yeniden çıkarmak, kaydırmanın
    ölçtüğü şeyi (hizalanmanın kaybı) gerçek stratejinin yeniden koşmasıyla karıştırırdı.
    """

    pencere: Pencere
    parametreler: list[dict[str, Any]]
    takvimler: list[dict[int, tuple[str, float]]]
    takvim_bar: int
    """Takvimin tanım kümesi: motorun gördüğü dilimin tamamı (ısınma dahil)."""

    isinma: int

    def __len__(self) -> int:
        return len(self.parametreler)


def izgara_takvimi(
    strateji_sinifi: type[Strateji],
    secenekler: Mapping[str, Sequence[Any]],
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    pencere: Pencere,
    *,
    baslangic_sermaye: float = 10_000.0,
    asgari_islem: int = ASGARI_ISLEM,
) -> IzgaraTakvimi:
    """Izgaradaki her **geçerli** noktanın sinyal takvimini çıkarır.

    Geçersiz (az işlemli) noktalar dışarıda: null'da da dışarıda kalmalılar, yoksa
    dağılım hiçbir zaman kapıya aday olmayacak gürültüyle şişer (K-044'ün uygunluk
    süzgeci gerekçesi).
    """
    parametreler: list[dict[str, Any]] = []
    takvimler: list[dict[int, tuple[str, float]]] = []
    takvim_bar = pencere.bitis - pencere.isinma_baslangic

    for p in izgara(secenekler):
        try:
            strateji = strateji_sinifi(**p)
        except (ValueError, TypeError):
            continue
        takvim, sonuc = takvim_cikar(
            strateji,
            maliyet,
            sembol,
            timeframe,
            bar_dizileri,
            pencere,
            baslangic_sermaye=baslangic_sermaye,
        )
        if sonuc.metrikler.islem_sayisi < asgari_islem:
            continue
        parametreler.append(dict(sorted(p.items())))
        takvimler.append(takvim)

    if len(parametreler) < 2:
        raise KalibrasyonHatasi(
            f"{len(parametreler)} geçerli nokta: null kurulamaz. Izgarada yeterince "
            "işlem yapan iki nokta yoksa ölçülecek bir seçim de yok."
        )
    return IzgaraTakvimi(
        pencere=pencere,
        parametreler=parametreler,
        takvimler=takvimler,
        takvim_bar=takvim_bar,
        isinma=pencere.olcum_baslangici,
    )


def _tur_kosulari(
    takvim: IzgaraTakvimi,
    oran: float,
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    baslangic_sermaye: float,
) -> list[Sonuc]:
    """Bir null iterasyonu: bütün noktalar **aynı oranda** kaydırılıp koşturulur."""
    k = 1 + int(oran * (takvim.takvim_bar - 2))
    sonuclar: list[Sonuc] = []
    for t in takvim.takvimler:
        betik = BetikStrateji(kaydir(t, k, takvim.takvim_bar), isinma=takvim.isinma)
        sonuclar.append(
            kosu(
                betik,
                maliyet,
                sembol,
                timeframe,
                bar_dizileri,
                takvim.pencere,
                baslangic_sermaye=baslangic_sermaye,
            )
        )
    return sonuclar


def _getiri_satiri(sonuc: Sonuc) -> np.ndarray:
    oz = sonuc.ozkaynak
    onceki = np.where(oz[:-1] != 0.0, oz[:-1], np.nan)
    return np.nan_to_num(np.diff(oz) / onceki, nan=0.0, posinf=0.0, neginf=0.0)


def null_olc(
    takvim: IzgaraTakvimi,
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    *,
    olcum: str,
    deneme: int = 200,
    seed: int = 0,
    baslangic_sermaye: float = 10_000.0,
    olcut: str = "sharpe",
    yil_bar: float = 8766.0,
    dilim: int = pbo_mod.VARSAYILAN_DILIM,
    rejim_etiketleri: np.ndarray | None = None,
) -> NullOlcumu:
    """Üç istatistikten birinin null dağılımını ölçer.

    `olcum`: `"pbo"` | `"perturbasyon"` | `"rejim"`. Her biri kendi penceresinde
    çağrılmalı (modül başlığındaki tablo); modül pencereyi seçmiyor, `takvim` taşıyor.
    """
    if deneme < 1:
        raise KalibrasyonHatasi(f"deneme sayısı pozitif olmalı: {deneme}")
    if olcum not in ("pbo", "perturbasyon", "rejim"):
        raise KalibrasyonHatasi(f"bilinmeyen ölçüm {olcum!r}")
    if olcum == "rejim" and rejim_etiketleri is None:
        raise KalibrasyonHatasi("rejim null'ı için etiket dizisi gerekir")

    skorla = OLCUTLER[olcut]
    rng = np.random.default_rng(seed)
    ornek: list[float] = []

    for _ in range(deneme):
        # K-044'ün kuralı: iterasyon başına **tek** oran, bütün noktalara birden.
        sonuclar = _tur_kosulari(
            takvim, float(rng.random()), maliyet, sembol, timeframe, bar_dizileri,
            baslangic_sermaye,
        )
        if olcum == "pbo":
            matris = np.vstack([_getiri_satiri(s) for s in sonuclar])
            try:
                ornek.append(pbo_mod.cscv(matris, yil_bar=yil_bar, dilim=dilim).pbo)
            except pbo_mod.PboHatasi:
                continue
            continue

        skorlar = np.array([skorla(s.metrikler) for s in sonuclar], dtype=np.float64)
        secilen = int(np.argmax(skorlar))

        if olcum == "perturbasyon":
            dusus = pert_mod.dusus_hesapla(takvim.parametreler, skorlar, secilen)
            if dusus is not None:
                ornek.append(dusus)
        else:
            olcum_sonucu = rejim_mod.olc(
                sonuclar[secilen].ozkaynak,
                rejim_etiketleri,
                yil_bar=yil_bar,
            )
            if olcum_sonucu.en_kotu_sharpe is not None:
                ornek.append(olcum_sonucu.en_kotu_sharpe)

    yon = {"pbo": "<=", "perturbasyon": "<=", "rejim": ">="}[olcum]
    olcum_sonucu = _null_olcumu(olcum, yon, ornek, deneme, seed)
    if olcum_sonucu.gecerli_deneme == 0:
        raise KalibrasyonHatasi(
            f"{olcum}: hiçbir iterasyonda ölçülemedi. İstatistik bu kurulumda tanımsız; "
            "eşik türetilemez ve türetilmiş gibi yapılmaz"
        )
    return olcum_sonucu


__all__ = [
    "PERSENTILLER",
    "IzgaraTakvimi",
    "KalibrasyonHatasi",
    "NullOlcumu",
    "izgara_takvimi",
    "null_olc",
]
