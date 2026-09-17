"""Beş ailenin yan yana karşılaştırması: IS'te optimize, OOS'ta test. (Faz 4)

Roadmap'in iki bitti kriteri burada buluşuyor: *"5 aile de aynı veri ve aynı maliyet
varsayımlarıyla çalıştırılmış, sonuçlar yan yana"* ve *"her strateji için in-sample /
out-of-sample sonuçları ayrı raporlanıyor"*.

**Karşılaştırmanın adil olması için üç şey aynı tutuluyor:** veri (aynı dosya, aynı
SHA-256), maliyet modeli, ve başlangıç sermayesi. Farklı olmasına izin verilen tek şey
stratejinin kendisi ve ızgarası — çünkü ölçülmek istenen o.

**En önemli sütun `oos_is_orani`.** In-sample sonuç, tanımı gereği iyi olacak: parametre
o veriye bakılarak seçildi. Anlamlı olan, OOS'un IS'e oranı. 1'e yakınsa parametre
gerçekten bir şey yakalamış; sıfıra yakın veya negatifse IS başarısı gürültünün
ezberlenmesiydi. Bu oran K-019'un en güçlü adayı.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from scryne_quant.backtest.metrikler import Metrikler
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.research.bolme import Pencere, is_oos
from scryne_quant.research.izgaralar import izgara
from scryne_quant.research.tarama import ASGARI_ISLEM, kosu, tara
from scryne_quant.research.tarama import izgara as izgara_noktalari
from scryne_quant.strategy.kutuphane import KIYAS, KUTUPHANE, aile
from scryne_quant.strategy.temel import Strateji


def _oran(oos: float, ins: float) -> float:
    """OOS/IS oranı, işaret tuzağı kapatılmış hâlde.

    Naif bölme yanıltıcı: IS Sharpe'ı −0,5 ve OOS −1,0 iken oran +2,0 çıkar ve "OOS iki
    kat iyi" diye okunur. IS pozitif değilse oran tanımsızdır — çünkü sorulan soru
    "in-sample'daki **başarı** dışarıda korundu mu" ve başarı yoksa korunacak bir şey de
    yoktur.
    """
    if ins <= 0.0:
        return float("nan")
    return oos / ins


@dataclass(frozen=True, slots=True)
class Satir:
    """Bir stratejinin karşılaştırma tablosundaki satırı."""

    strateji: str
    aile: str
    secilen: dict[str, Any] | None
    izgara_boyutu: int
    gecerli_aday: int
    plato_orani: float
    duyarlilik: float
    ins: Metrikler | None
    oos: Metrikler | None

    @property
    def oos_is_sharpe_orani(self) -> float:
        if self.ins is None or self.oos is None:
            return float("nan")
        return _oran(self.oos.sharpe, self.ins.sharpe)

    def sozluk(self) -> dict[str, Any]:
        return {
            "strateji": self.strateji,
            "aile": self.aile,
            "secilen": self.secilen,
            "izgara_boyutu": self.izgara_boyutu,
            "gecerli_aday": self.gecerli_aday,
            "plato_orani": self.plato_orani,
            "duyarlilik": self.duyarlilik,
            "in_sample": self.ins.sozluk() if self.ins else None,
            "out_of_sample": self.oos.sozluk() if self.oos else None,
            "oos_is_sharpe_orani": self.oos_is_sharpe_orani,
        }


@dataclass(frozen=True, slots=True)
class Karsilastirma:
    """Tüm stratejilerin IS/OOS tablosu."""

    satirlar: list[Satir]
    ins_pencere: dict[str, Any]
    oos_pencere: dict[str, Any]
    olcut: str
    baslangic_sermaye: float

    def sozluk(self) -> dict[str, Any]:
        return {
            "olcut": self.olcut,
            "baslangic_sermaye": self.baslangic_sermaye,
            "pencereler": {"in_sample": self.ins_pencere, "out_of_sample": self.oos_pencere},
            "aile_sayisi": len({s.aile for s in self.satirlar if s.aile != "kiyas"}),
            "kiyas": next(
                (s.sozluk() for s in self.satirlar if s.aile == "kiyas"), None
            ),
            "satirlar": [s.sozluk() for s in self.satirlar],
        }


def calistir(
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    *,
    stratejiler: Sequence[str] | None = None,
    oos_orani: float = 0.30,
    olcut: str = "sharpe",
    secim: str = "tepe",
    baslangic_sermaye: float = 10_000.0,
    veri_sha256: str = "",
) -> Karsilastirma:
    """Her strateji için: IS'te ızgarayı tara, en iyisini OOS'ta koştur.

    Isınma **stratejiye göre** hesaplanıyor (`Strateji.isinma_bar`) ama pencereler
    **tüm stratejiler için ortak** olmak zorunda — aksi hâlde biri diğerinden farklı bir
    tarih aralığında ölçülür ve karşılaştırma anlamını yitirir. Bu yüzden ortak ısınma,
    kütüphanedeki en uzun ısınmadır.
    """
    # Kıyas ölçütü her karşılaştırmaya otomatik ekleniyor. İstemeye bırakılsaydı
    # unutulurdu, ve unutulduğu raporda "%15 kazandı" cümlesi ölçüsüz kalırdı.
    adlar = list(stratejiler) if stratejiler else list(KUTUPHANE)
    hepsi = {**KUTUPHANE, **KIYAS}
    if not any(a in KIYAS for a in adlar):
        adlar = [*adlar, *KIYAS]
    siniflar: dict[str, type[Strateji]] = {ad: hepsi[ad] for ad in adlar}

    n = len(bar_dizileri["open_time"])
    ins_pencere, oos_pencere = ortak_pencereler(n, adlar, oos_orani=oos_orani)

    satirlar: list[Satir] = []
    for ad, sinif in siniflar.items():
        secenekler = izgara(ad)
        # Asgari işlem şartı, ızgaradan **şanslı bir parametre seçilmesini** engellemek
        # için var. Kıyas ölçütünün ızgarası tek noktalı ve seçilecek bir şey yok: al-tut
        # bir kez alıp tutar, yani tanımı gereği 1 işlem yapar. Şartı ona uygulamak,
        # karşılaştırmanın referans çizgisini tablodan silerdi. Eşik sıfır: al-tut
        # pozisyonu pencerenin sonunda **açık** bırakır, yani kapanmış tur sayısı 0'dır.
        tarama = tara(
            sinif, secenekler, maliyet, sembol, timeframe, bar_dizileri, ins_pencere,
            olcut=olcut, baslangic_sermaye=baslangic_sermaye,
            asgari_islem=0 if ad in KIYAS else ASGARI_ISLEM,
        )
        en_iyi = tarama.sec(secim)

        oos_metrikler: Metrikler | None = None
        if en_iyi is not None:
            oos_metrikler = kosu(
                sinif(**en_iyi.sozluk_parametreler),
                maliyet, sembol, timeframe, bar_dizileri, oos_pencere,
                baslangic_sermaye=baslangic_sermaye, veri_sha256=veri_sha256,
            ).metrikler

        satirlar.append(
            Satir(
                strateji=ad,
                aile=aile(ad),
                secilen=en_iyi.sozluk_parametreler if en_iyi else None,
                izgara_boyutu=len(tarama.adaylar),
                gecerli_aday=len(tarama.gecerliler),
                plato_orani=tarama.ust_yuzde_plato(),
                duyarlilik=tarama.duyarlilik(),
                ins=en_iyi.metrikler if en_iyi else None,
                oos=oos_metrikler,
            )
        )

    return Karsilastirma(
        satirlar=satirlar,
        ins_pencere=ins_pencere.sozluk(),
        oos_pencere=oos_pencere.sozluk(),
        olcut=olcut,
        baslangic_sermaye=baslangic_sermaye,
    )


def ortak_isinma(stratejiler: Sequence[str] | None = None) -> int:
    """Verilen stratejilerin **ızgaraları dahil** en uzun ısınma ihtiyacı.

    Izgaradaki her geçerli kombinasyon kurulup kendi `isinma_bar()`i soruluyor: bir
    ızgara varsayılandan uzun bir pencere içerebilir (örneğin `sma_kesisim`in
    varsayılanı 50, ızgarası 200) ve o durumda ortak ısınma varsayılana göre hesaplanırsa
    en uzun pencereli aday ilk barlarında sessizce sinyal üretemez.
    """
    adlar = list(stratejiler) if stratejiler else list(KUTUPHANE)
    hepsi = {**KUTUPHANE, **KIYAS}
    en_uzun = 0
    for ad in adlar:
        sinif = hepsi[ad]
        for kombinasyon in izgara_noktalari(izgara(ad)):
            try:
                en_uzun = max(en_uzun, sinif(**kombinasyon).isinma_bar())
            except (ValueError, TypeError):
                continue  # ızgaranın anlamsız köşesi
    return en_uzun


def ortak_pencereler(
    bar_sayisi: int, stratejiler: Sequence[str] | None = None, oos_orani: float = 0.30
) -> tuple[Pencere, Pencere]:
    """Karşılaştırmanın kullandığı IS/OOS pencerelerini dışarıya verir.

    CLI ve testler aynı pencereleri yeniden hesaplamak zorunda kalmasın diye ayrı: iki
    yerde hesaplanan bir pencere, iki yerde farklı olmaya adaydır.
    """
    return is_oos(bar_sayisi, ortak_isinma(stratejiler), oos_orani=oos_orani)
