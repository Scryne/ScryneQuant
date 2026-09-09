"""Veri bölme: in-sample / out-of-sample ve walk-forward pencereleri. (Faz 4)

Bu modül overfitting'e karşı ilk savunma hattı ve **look-ahead'in ikinci kapısı.** K-002
strateji katmanında geleceği kapattı; burada kapatılan şey **deney** katmanındaki
sızıntı: bir parametreyi tüm veride optimize edip aynı veride raporlamak da geleceği
kullanmaktır, sadece daha sinsi biçimde.

Üç değişmez kural, üçü de testle korunuyor:

1. **Bölme kronolojiktir, asla rastgele değil.** Zaman serisinde rastgele bölme, eğitim
   kümesine test döneminden bar sızdırır ve komşu barlar birbirine çok benzediği için
   sonuç neredeyse mükemmel çıkar. Bu, klasik "makine öğrenmesi kütüphanesini zaman
   serisine uygulama" hatasıdır.
2. **Test penceresi eğitim penceresinden sonra gelir**, örtüşme yok.
3. **Isınma eğitim penceresinden geriye taşar, ileriye asla.** Bir katmanın indikatörleri
   kendi başlangıcından önceki barlarla ısıtılır — canlıda o tarihe gelindiğinde o veri
   elde olurdu; indikatörler nedensel olduğu için bu look-ahead değil, gerçekçilik.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Final

#: OOS payının makul aralığı. Çok küçük OOS istatistiksel olarak anlamsız, çok büyük OOS
#: geriye optimize edilecek veri bırakmaz.
OOS_ALT: Final = 0.10
OOS_UST: Final = 0.50


class BolmeHatasi(ValueError):
    """Bölme parametreleri veri uzunluğuyla bağdaşmıyor."""


@dataclass(frozen=True, slots=True)
class Pencere:
    """Bar indeksleriyle tanımlı bir değerlendirme penceresi.

    `isinma_baslangic` ile `baslangic` arasındaki barlar backtest'e **verilir** ama
    ölçülmez: indikatörler orada ısınır. `baslangic`..`bitis` (dışlayıcı) ölçülen aralık.
    """

    ad: str
    baslangic: int
    bitis: int
    isinma_baslangic: int

    def __post_init__(self) -> None:
        if self.isinma_baslangic > self.baslangic:
            raise BolmeHatasi(
                f"{self.ad}: ısınma ileriye taşamaz "
                f"({self.isinma_baslangic} > {self.baslangic})"
            )
        if self.bitis <= self.baslangic:
            raise BolmeHatasi(f"{self.ad}: boş pencere ({self.baslangic}..{self.bitis})")
        if self.isinma_baslangic < 0:
            raise BolmeHatasi(f"{self.ad}: negatif ısınma başlangıcı")

    @property
    def uzunluk(self) -> int:
        """Ölçülen bar sayısı."""
        return self.bitis - self.baslangic

    @property
    def olcum_baslangici(self) -> int:
        """Dilimlenmiş dizide ölçümün başladığı indeks (motora bu değer verilir)."""
        return self.baslangic - self.isinma_baslangic

    def dilim(self) -> slice:
        """Bar dizilerinden alınacak dilim — ısınma dahil."""
        return slice(self.isinma_baslangic, self.bitis)

    def sozluk(self) -> dict[str, Any]:
        return {
            "ad": self.ad,
            "baslangic": self.baslangic,
            "bitis": self.bitis,
            "isinma_baslangic": self.isinma_baslangic,
            "uzunluk": self.uzunluk,
        }


@dataclass(frozen=True, slots=True)
class Katman:
    """Bir walk-forward katmanı: önce eğitim, sonra test."""

    sira: int
    egitim: Pencere
    test: Pencere

    def __post_init__(self) -> None:
        if self.test.baslangic < self.egitim.bitis:
            # Test eğitimle örtüşürse optimize edilen parametre kendi test verisini
            # görmüş olur; walk-forward'ın tek amacı bunu engellemek.
            raise BolmeHatasi(
                f"katman {self.sira}: test eğitimle örtüşüyor "
                f"({self.test.baslangic} < {self.egitim.bitis})"
            )

    def sozluk(self) -> dict[str, Any]:
        return {"sira": self.sira, "egitim": self.egitim.sozluk(), "test": self.test.sozluk()}


def is_oos(bar_sayisi: int, isinma: int, oos_orani: float = 0.30) -> tuple[Pencere, Pencere]:
    """Veriyi kronolojik olarak in-sample / out-of-sample ikiye böler.

    OOS **sonda** olur, başta değil. Sondaki veri en yeni veridir ve bir stratejinin
    bugüne yakın davranışı, beş yıl önceki davranışından daha bilgilendiricidir. Ayrıca
    parametre araması eskiden yeniye doğru yapılır — canlıda da öyle olacak.
    """
    if not OOS_ALT <= oos_orani <= OOS_UST:
        raise BolmeHatasi(f"oos_orani {OOS_ALT}-{OOS_UST} aralığında olmalı: {oos_orani}")
    if isinma < 0:
        raise BolmeHatasi(f"ısınma negatif olamaz: {isinma}")

    oos_uzunluk = int(bar_sayisi * oos_orani)
    kesme = bar_sayisi - oos_uzunluk
    if kesme - isinma < 2 or oos_uzunluk < 2:
        raise BolmeHatasi(
            f"{bar_sayisi} bar, {isinma} ısınma ve %{oos_orani:.0%} OOS ile bölünemiyor"
        )

    # Yukarıdaki kontrol `kesme - isinma >= 2` olduğunu garanti ediyor, yani OOS'un
    # ısınma başlangıcı hep pozitif. `max(0, ...)` yazmak, hiç gerçekleşmeyen bir durumu
    # ele alıyormuş gibi görünen ölü kod olurdu.
    return (
        Pencere("in_sample", baslangic=isinma, bitis=kesme, isinma_baslangic=0),
        Pencere("out_of_sample", baslangic=kesme, bitis=bar_sayisi,
                isinma_baslangic=kesme - isinma),
    )


def walk_forward(
    bar_sayisi: int,
    isinma: int,
    egitim_bar: int,
    test_bar: int,
    *,
    kaydirmali: bool = True,
) -> list[Katman]:
    """Walk-forward katmanları üretir.

    `kaydirmali=True` (rolling): eğitim penceresi sabit uzunlukta, ileri kayar.
    `kaydirmali=False` (anchored/expanding): eğitim penceresi başlangıçtan itibaren büyür.

    İkisi farklı soru soruyor: kaydırmalı "strateji **son** N barla ayarlanınca sonraki
    dönemde tutuyor mu", sabit-çapa "tüm geçmişle ayarlanınca tutuyor mu". Kaydırmalı
    varsayılan çünkü piyasa rejimi değişir ve beş yıl önceki veriyle bugünü ayarlamak,
    ayarın hangi rejime ait olduğunu belirsizleştirir.
    """
    if egitim_bar < 2 or test_bar < 2:
        raise BolmeHatasi(f"pencereler en az 2 bar olmalı: egitim={egitim_bar}, test={test_bar}")
    if isinma < 0:
        raise BolmeHatasi(f"ısınma negatif olamaz: {isinma}")

    katmanlar: list[Katman] = []
    egitim_baslangic = isinma
    sira = 0

    while True:
        egitim_bitis = egitim_baslangic + egitim_bar
        test_bitis = egitim_bitis + test_bar
        if test_bitis > bar_sayisi:
            break

        katmanlar.append(
            Katman(
                sira=sira,
                egitim=Pencere(
                    f"egitim_{sira}",
                    baslangic=egitim_baslangic,
                    bitis=egitim_bitis,
                    isinma_baslangic=max(0, egitim_baslangic - isinma),
                ),
                test=Pencere(
                    f"test_{sira}",
                    baslangic=egitim_bitis,
                    bitis=test_bitis,
                    isinma_baslangic=max(0, egitim_bitis - isinma),
                ),
            )
        )
        sira += 1
        if kaydirmali:
            egitim_baslangic += test_bar
        else:
            egitim_bar += test_bar

    if not katmanlar:
        raise BolmeHatasi(
            f"{bar_sayisi} bar, {isinma} ısınma, {egitim_bar}+{test_bar} pencereyle "
            "tek bir katman bile çıkmıyor"
        )
    return katmanlar


def katman_test_pencereleri(katmanlar: list[Katman]) -> Iterator[Pencere]:
    """Katmanların test pencereleri — birleşimi kesintisiz OOS zincirini verir.

    Adı `test_` ile başlamıyor: pytest `test_` önekli her modül düzeyi fonksiyonu
    test vakası sanıyor ve import edildiği yerde toplama hatası veriyor. Ölçüldü.
    """
    yield from (k.test for k in katmanlar)
