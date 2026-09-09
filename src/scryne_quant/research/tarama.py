"""Parametre taraması ve seçim ölçütü. (Faz 4)

Tarama, overfitting'in **kaynağıdır**: 1.000 parametre denenip en iyisi seçilirse, o "en
iyi" büyük ihtimalle gürültünün en şanslı örneğidir. Bu modül taramayı yapar ama üç yerde
o riski görünür kılar:

1. **Seçim ölçütü açıkça yazılır ve kayda girer.** "En iyi" kendiliğinden anlaşılan bir
   şey değil; getiriye göre seçmek en çok risk alanı, Sharpe'a göre seçmek en düzgün
   olanı seçer. Ölçüt bir parametre, gizli bir varsayım değil.
2. **Asgari işlem sayısı şartı var.** 3 işlemle %400 getiri bir strateji değil, bir
   tesadüftür. Şartı sağlamayan aday sıralamaya bile girmez.
3. **Duyarlılık ölçülür.** En iyi parametrenin komşuları da iyiyse bölge sağlamdır;
   sadece o nokta iyiyse tepe gürültüdür. `duyarlilik()` bunu sayıya çeviriyor ve K-019'un
   adaylarından biri bu sayı.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from scryne_quant.backtest.metrikler import Metrikler
from scryne_quant.backtest.motor import Backtest
from scryne_quant.backtest.sonuc import Sonuc
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.research.bolme import Pencere
from scryne_quant.strategy.temel import Strateji

#: Bir adayın sıralamaya girebilmesi için gereken en az işlem sayısı.
#:
#: 20 sayısı bir istatistik teoreminden değil, oran hatasının büyüklüğünden geliyor:
#: 20 işlemde win rate'in standart hatası ~%11, yani ölçülen %60 gerçekte %38-%82 arası
#: olabilir. Daha azı için "bu strateji kazanıyor" cümlesi kurulamaz. Kesin eşik K-019'da.
ASGARI_ISLEM: Final = 20


class TaramaHatasi(ValueError):
    """Tarama ızgarası veya ölçütü geçersiz."""


#: Bir sonucu tek bir skora indiren fonksiyon. Yüksek olan iyi.
Olcut = Callable[[Metrikler], float]


def olcut_sharpe(m: Metrikler) -> float:
    return m.sharpe


def olcut_calmar(m: Metrikler) -> float:
    return m.calmar


def olcut_getiri(m: Metrikler) -> float:
    return m.toplam_getiri


def olcut_profit_factor(m: Metrikler) -> float:
    return m.profit_factor


#: Kayda yazılabilir isimden fonksiyona. Ölçüt bir string olarak deney kaydına giriyor;
#: callable'ın kimliği bellek adresidir ve altı ay sonra hangi ölçütle seçildiği
#: sorusunu cevaplamaz (K-009'un config hash mantığının aynısı).
OLCUTLER: Final[dict[str, Olcut]] = {
    "sharpe": olcut_sharpe,
    "calmar": olcut_calmar,
    "getiri": olcut_getiri,
    "profit_factor": olcut_profit_factor,
}


@dataclass(frozen=True, slots=True)
class Aday:
    """Tarama ızgarasındaki bir parametre kombinasyonunun sonucu."""

    parametreler: tuple[tuple[str, Any], ...]
    skor: float
    metrikler: Metrikler
    sonuc_hash: str
    gecerli: bool
    """Asgari işlem sayısı şartını sağlıyor mu."""

    @property
    def sozluk_parametreler(self) -> dict[str, Any]:
        return dict(self.parametreler)

    def sozluk(self) -> dict[str, Any]:
        return {
            "parametreler": self.sozluk_parametreler,
            "skor": self.skor,
            "gecerli": self.gecerli,
            "sonuc_hash": self.sonuc_hash,
            "islem_sayisi": self.metrikler.islem_sayisi,
            "sharpe": self.metrikler.sharpe,
            "getiri": self.metrikler.toplam_getiri,
            "max_drawdown": self.metrikler.max_drawdown,
            "profit_factor": self.metrikler.profit_factor,
        }


@dataclass(frozen=True, slots=True)
class TaramaSonucu:
    """Bir taramanın tamamı."""

    strateji_adi: str
    olcut: str
    adaylar: list[Aday]
    pencere: dict[str, Any]
    asgari_islem: int

    @property
    def gecerliler(self) -> list[Aday]:
        return [a for a in self.adaylar if a.gecerli]

    @property
    def en_iyi(self) -> Aday | None:
        """En yüksek skorlu **geçerli** aday. Geçerli aday yoksa `None`.

        `None` dönmek bir hata değil, bir bulgudur: "bu ızgarada yeterince işlem yapan
        hiçbir parametre yok". Sessizce geçersiz bir adayı seçmek, o bulguyu silerdi.
        """
        gecerli = self.gecerliler
        return max(gecerli, key=lambda a: a.skor) if gecerli else None

    def duyarlilik(self) -> float:
        """Skorun parametreye duyarlılığı: geçerli adayların skor standart sapması.

        Yüksek değer "tepe dar" demek — komşu parametreler çok farklı sonuç veriyor, yani
        seçilen nokta muhtemelen gürültü. Düşük değer platoyu gösterir, ve plato bir
        stratejinin gerçekten bir şey yakaladığının en ucuz kanıtıdır.

        Tek başına yorumlanmaz: skorların ölçeğine bağlıdır. K-019 bunu skor aralığına
        oranlayarak kullanacak.
        """
        skorlar = [a.skor for a in self.gecerliler]
        return float(np.std(skorlar, ddof=1)) if len(skorlar) > 1 else 0.0

    def ust_yuzde_plato(self, yuzde: float = 0.10) -> float:
        """En iyi skorun %`yuzde` yakınındaki geçerli adayların oranı.

        "Tepe mi plato mu" sorusunun duyarlılıktan daha okunur hâli: 0,45 dönerse geçerli
        adayların %45'i en iyiye yakın demektir — geniş plato. 0,01 dönerse tek bir nokta
        parlıyor demektir ve o noktaya güvenilmez.
        """
        gecerli = self.gecerliler
        if not gecerli:
            return 0.0
        skorlar = np.array([a.skor for a in gecerli])
        en_iyi = skorlar.max()
        aralik = skorlar.max() - skorlar.min()
        if aralik <= 0.0:
            return 1.0
        return float((skorlar >= en_iyi - yuzde * aralik).mean())

    def sozluk(self, *, aday_listesi: bool = True) -> dict[str, Any]:
        en_iyi = self.en_iyi
        govde: dict[str, Any] = {
            "strateji": self.strateji_adi,
            "olcut": self.olcut,
            "pencere": self.pencere,
            "asgari_islem": self.asgari_islem,
            "aday_sayisi": len(self.adaylar),
            "gecerli_aday": len(self.gecerliler),
            "en_iyi": en_iyi.sozluk() if en_iyi else None,
            "duyarlilik": self.duyarlilik(),
            "plato_orani": self.ust_yuzde_plato(),
        }
        if aday_listesi:
            govde["adaylar"] = [a.sozluk() for a in self.adaylar]
        return govde


def izgara(secenekler: Mapping[str, Sequence[Any]]) -> list[dict[str, Any]]:
    """Kartezyen çarpım. Anahtar sırası sabitleniyor — kombinasyon sırası kayda giriyor.

    >>> izgara({"a": [1, 2], "b": [3]})
    [{'a': 1, 'b': 3}, {'a': 2, 'b': 3}]
    """
    if not secenekler:
        raise TaramaHatasi("boş ızgara")
    adlar = sorted(secenekler)
    for ad in adlar:
        if not secenekler[ad]:
            raise TaramaHatasi(f"{ad}: en az bir değer gerekli")
    return [
        dict(zip(adlar, kombinasyon, strict=True))
        for kombinasyon in itertools.product(*(secenekler[a] for a in adlar))
    ]


def tara(
    strateji_sinifi: type[Strateji],
    secenekler: Mapping[str, Sequence[Any]],
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    pencere: Pencere,
    *,
    olcut: str = "sharpe",
    baslangic_sermaye: float = 10_000.0,
    asgari_islem: int = ASGARI_ISLEM,
) -> TaramaSonucu:
    """Izgaradaki her kombinasyonu `pencere` üzerinde koşturur.

    Geçersiz parametre kombinasyonları (örneğin `yavas <= hizli`) **sessizce atlanır**:
    ızgarayı elle temizlemek yerine stratejinin kendi doğrulamasına güveniyoruz. Atlanan
    kombinasyon sonuçta görünmez ama `aday_sayisi` ile ızgara boyutunu karşılaştıran
    okuyucu farkı görür.
    """
    if olcut not in OLCUTLER:
        raise TaramaHatasi(f"bilinmeyen ölçüt {olcut!r}; geçerli: {', '.join(sorted(OLCUTLER))}")
    skorla = OLCUTLER[olcut]

    dilim = {ad: dizi[pencere.dilim()] for ad, dizi in bar_dizileri.items()}
    adaylar: list[Aday] = []

    for parametreler in izgara(secenekler):
        try:
            strateji = strateji_sinifi(**parametreler)
        except (ValueError, TypeError):
            continue  # ızgaranın anlamsız köşesi; strateji kendi kuralını uyguladı
        sonuc = Backtest(strateji, maliyet, baslangic_sermaye=baslangic_sermaye).calistir(
            sembol, timeframe, dilim, olcum_baslangici=pencere.olcum_baslangici
        )
        adaylar.append(
            Aday(
                parametreler=tuple(sorted(parametreler.items())),
                skor=skorla(sonuc.metrikler),
                metrikler=sonuc.metrikler,
                sonuc_hash=sonuc.sonuc_hash,
                gecerli=sonuc.metrikler.islem_sayisi >= asgari_islem,
            )
        )

    if not adaylar:
        raise TaramaHatasi("ızgaradaki hiçbir kombinasyon geçerli bir strateji kurmadı")

    return TaramaSonucu(
        strateji_adi=getattr(strateji_sinifi, "ad", strateji_sinifi.__name__),
        olcut=olcut,
        adaylar=adaylar,
        pencere=pencere.sozluk(),
        asgari_islem=asgari_islem,
    )


def kosu(
    strateji: Strateji,
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    pencere: Pencere,
    *,
    baslangic_sermaye: float = 10_000.0,
    veri_sha256: str = "",
) -> Sonuc:
    """Tek bir stratejiyi tek bir pencerede koşturur. Tarama ve walk-forward bunu kullanır."""
    dilim = {ad: dizi[pencere.dilim()] for ad, dizi in bar_dizileri.items()}
    return Backtest(strateji, maliyet, baslangic_sermaye=baslangic_sermaye).calistir(
        sembol,
        timeframe,
        dilim,
        veri_sha256=veri_sha256,
        olcum_baslangici=pencere.olcum_baslangici,
    )
