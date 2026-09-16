"""Portföy stratejisi için tam değerlendirme: 11 kapının hepsi. (Faz 12)

`research/degerlendirme.py` (K-019'un yedi kapısı) ve `research/kapilar_v2.py` (K-054'ün
dört kapısı) **tek sembol** için yazıldı: tarama, walk-forward, stres ve PBO hep
`Backtest(sembol, bar_dizileri)` çağırıyor. Faz 12'nin programları evren üzerinde koşuyor
ve aynı kapılardan geçmek zorunda. Bu modül o kapıların **aynı tanımlarla** çok enstrümanlı
karşılığı; yeni bir kapı, yeni bir eşik veya gevşetilmiş bir ölçü yok.

## Tek sembollü hatla birebir aynı olanlar

- Bölme: `bolme.is_oos` ve `bolme.walk_forward` (kronolojik, OOS sonda, ısınma geriye).
- Tarama, seçim, plato merkezi, duyarlılık: `tarama.Aday` / `tarama.TaramaSonucu`.
- Walk-forward sonucu ve parametre kararlılığı: `walkforward.KatmanSonucu` /
  `WalkForwardSonucu`; sermaye katmanlar arasında taşınır.
- Stres senaryoları: `analiz.STRES_SENARYOLARI`, bozulma `analiz.StresSonucu.bozulma`.
- PBO: `pbo.cscv`; pertürbasyon: `perturbasyon.olc`; rejim: `rejim.etiketle` + `rejim.olc`.
- Kapılar: `kapilar_v2.butun_kapilar` (7 + 4).

## Çok enstrümana özgü üç karar

1. **Her koşu kendi görünümünü kurar.** Pencere dilimi (ısınma dahil) alınır ve özellikler
   o dilimde, sembol başına, yalnızca var olan barlar üzerinde hesaplanır
   (`strategy.kosu.ozellikleri_hesapla`). Tek sembollü hat da her pencerede özellikleri
   yeniden hesaplıyor; tam seriden hesaplayıp dilimlemek Wilder tohumunu pencerenin dışına
   taşırdı ve iki hat aynı stratejiye farklı sayı verirdi.
2. **Rejim etiketi kıyas enstrümanının kapanışından** (varsayılan `BTCUSDT`). Eşik
   (K-058) BTC 1h kapanışı üzerinde kalibre edildi; evrende başka bir kıyas seçmek
   kapının sorusunu değiştirirdi.
3. **Evren dayanıklılığı OOS penceresinde ölçülür.** Kapıların performans okuyanları
   (`oos_sharpe`, `rejim_kararliligi`) OOS'a bakıyor; "sonuç tek isme mi bağlı" sorusu da
   promotion'a giden sonucun kendisine sorulmalı. Faz 11'in yapısal kalibrasyonu tam
   pencerede koşmuştu — fark kayıtlı (Faz 12 raporu).

## Stres neden seçilen parametreyle

Tek sembollü `degerlendirme.py` stresi stratejinin **varsayılan** parametreleriyle
koşturuyor. Portföy stratejisinde varsayılan parametre sözleşmenin parçası değil; promotion'a
aday olan şey seçilen parametre olduğu için stres onunla ve **tam** pencerede koşulur.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.backtest.metrikler import Islem, bar_yili, hesapla
from scryne_quant.backtest.sonuc import Sonuc
from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.research import evren_dayaniklilik as day_mod
from scryne_quant.research import hipotez as hipotez_mod
from scryne_quant.research import kapilar_v2
from scryne_quant.research import pbo as pbo_mod
from scryne_quant.research import perturbasyon as pert_mod
from scryne_quant.research import rejim as rejim_mod
from scryne_quant.research.analiz import STRES_SENARYOLARI, StresSonucu
from scryne_quant.research.bolme import Katman, Pencere, is_oos, walk_forward
from scryne_quant.research.degerlendirme import EGITIM_BAR, TEST_BAR, _kararsizlik
from scryne_quant.research.evren_kosu import EvrenVerisi
from scryne_quant.research.izgaralar import evren_cekilisi
from scryne_quant.research.tarama import (
    ASGARI_ISLEM,
    OLCUTLER,
    Aday,
    TaramaHatasi,
    TaramaSonucu,
    izgara,
)
from scryne_quant.research.walkforward import (
    KatmanSonucu,
    WalkForwardHatasi,
    WalkForwardSonucu,
)
from scryne_quant.strategy.evren import EvrenGorunumu
from scryne_quant.strategy.kosu import evren_gorunum_kur
from scryne_quant.strategy.temel import PortfoyStratejisi

#: Rejim etiketinin kıyası. Bkz. modül başlığı, karar 2.
REJIM_KIYASI: Final = "BTCUSDT"

#: Kesitsel ailelerin portföy kurma yöntemi (`kesitsel._Kesitsel`), hipotez kimliğine girer.
KESITSEL_PORTFOY: Final = "KESITSEL_ESIT"

#: Kesitsel çekilişlerin seçim yöntemi. Tek sembollü arama `tepe` ve `plato`yu ayrı
#: çekiliş saydı (K-039); programda tek yöntem önceden sabit: plato, çünkü K-054'ün
#: pertürbasyon kapısı tepe seçimini zaten cezalandırıyor.
KESITSEL_SECIM: Final = "plato"


# --------------------------------------------------------------------- kimlik ve kayıt


def veri_kimligi(veri: EvrenVerisi) -> str:
    """Evren çekilişinin veri kimliği: üyelik tablosu + kural + her sembolün bar hash'i.

    Tek sembollü hatta `veri_sha256` tek bir dosyanın hash'i. Evrende soru üç şeye bağlı:
    hangi barlar (sembol başına SHA-256), hangi üyelik (PIT tablonun hash'i) ve hangi
    pencere. Biri değişirse aynı ızgara **yeni bir hipotezdir** (K-039).
    """
    return nesne_hash(
        {
            "timeframe": veri.timeframe,
            "tablo_hash": veri.meta.get("tablo_hash", ""),
            "kural": veri.kural_kimligi,
            "pencere": veri.meta.get("pencere", {}),
            "veri_sha256": dict(sorted(veri.veri_sha256.items())),
        }
    )


def hipotez_kur(
    cekilis: str, veri: EvrenVerisi, *, program: str, gerekce: str
) -> hipotez_mod.Hipotez:
    """Bir evren çekilişinin hipotez nesnesi. Kayıt ve koşu **aynı** fonksiyondan kurar;
    iki yerde ayrı kurulan kimlik, ön kaydı yapılmış bir koşuyu defterde bulamaz."""
    strateji, izgara_ = evren_cekilisi(cekilis)
    return hipotez_mod.Hipotez.kur(
        strateji,
        veri.timeframe,
        veri_kimligi(veri),
        izgara_,
        gerekce,
        secim=KESITSEL_SECIM,
        program=program,
        evren=veri.kural_kimligi,
        portfoy=KESITSEL_PORTFOY,
    )

@dataclass(frozen=True, slots=True)
class KosuIsi:
    """Tek bir koşunun tarifi. Süreçler arası taşınabilsin diye callable değil veri."""

    sinif: type[PortfoyStratejisi]
    parametreler: tuple[tuple[str, Any], ...]
    pencere: Pencere
    baslangic_sermaye: float
    cikarilanlar: frozenset[str] = frozenset()


#: İşleri koşturup **aynı sırada** sonuç döndüren fonksiyon. Varsayılanı seri;
#: `tools/faz12_evren_kos.py` süreç havuzlu bir uygulama veriyor. Her iş bağımsız ve
#: deterministik olduğu için sonuç koşucudan bağımsızdır.
Kosucu = Callable[[list[KosuIsi]], list[Sonuc]]


def isi_kos(is_: KosuIsi, maliyet: MaliyetModeli, veri: EvrenVerisi) -> Sonuc:
    return kosu(
        is_.sinif(**dict(is_.parametreler)), maliyet, veri, is_.pencere,
        baslangic_sermaye=is_.baslangic_sermaye, cikarilanlar=is_.cikarilanlar,
    )


def seri_kosucu(maliyet: MaliyetModeli, veri: EvrenVerisi) -> Kosucu:
    return lambda isler: [isi_kos(i, maliyet, veri) for i in isler]


#: Havuz işçisinin süreç içi durumu. Veri işçiye **pickle ile taşınmaz** (≈2,5 GB):
#: işçi onu `veri_uretici` ile kendisi kurar.
_ISCI: dict[str, Any] = {}


def isci_baslat(veri_uretici: Callable[[], EvrenVerisi], maliyet: MaliyetModeli) -> None:
    """`ProcessPoolExecutor(initializer=...)` için. `veri_uretici` modül düzeyinde olmalı."""
    _ISCI["veri"] = veri_uretici()
    _ISCI["maliyet"] = maliyet


def isci_kos(is_: KosuIsi) -> Sonuc:
    return isi_kos(is_, _ISCI["maliyet"], _ISCI["veri"])


def havuz_kosucu(
    havuz: Any, *, buyuk_is_bar: int | None = None, buyuk_is_eszamanli: int = 1
) -> Kosucu:
    """`isci_baslat` ile başlatılmış bir havuzdan koşucu. Sonuç sırası iş sırasıdır.

    Bellek işçi başına pencere uzunluğuyla büyüyor (görünüm + özellikler sembol × bar).
    Faz 12'de ölçüldü: tam pencere (79.420 bar) taraması 4 işçide 24 GB'lık makinede
    sistemin koşuyu öldürmesine yol açtı; in-sample (55.594 bar) 4 işçide sığdı. Uzunluğu
    `buyuk_is_bar`ı aşan işler en fazla `buyuk_is_eszamanli` tanesi bir arada gönderilir.
    Eşzamanlılık sonucu değiştirmez: işler bağımsız ve deterministik.
    """
    def kos(isler: list[KosuIsi]) -> list[Sonuc]:
        buyuk = buyuk_is_bar is not None and any(
            i.pencere.bitis - i.pencere.isinma_baslangic > buyuk_is_bar for i in isler
        )
        if not buyuk:
            return list(havuz.map(isci_kos, isler))
        adim = max(1, buyuk_is_eszamanli)
        out: list[Sonuc] = []
        for bas in range(0, len(isler), adim):
            out.extend(havuz.map(isci_kos, isler[bas:bas + adim]))
        return out

    return kos


class EvrenDegerlendirmeHatasi(ValueError):
    """Evren değerlendirmesinin girdisi geçersiz."""


# --------------------------------------------------------------------- tek koşu


def gorunum(
    veri: EvrenVerisi,
    strateji: PortfoyStratejisi,
    pencere: Pencere,
    *,
    cikarilanlar: frozenset[str] = frozenset(),
) -> EvrenGorunumu:
    """Pencerenin dilimi (ısınma dahil) için görünüm; özellikler dilimde hesaplanır."""
    dilim = pencere.dilim()
    diziler = {s: {a: d[dilim] for a, d in dz.items()} for s, dz in veri.diziler.items()}
    uyelik = {
        s: (np.zeros(pencere.bitis - pencere.isinma_baslangic, dtype=bool)
            if s in cikarilanlar else np.asarray(u)[dilim])
        for s, u in veri.uyelik.items()
    }
    return evren_gorunum_kur(
        veri.timeframe, diziler, uyelik, strateji, kural_kimligi=veri.kural_kimligi
    )


def kosu(
    strateji: PortfoyStratejisi,
    maliyet: MaliyetModeli,
    veri: EvrenVerisi,
    pencere: Pencere,
    *,
    baslangic_sermaye: float = 10_000.0,
    cikarilanlar: frozenset[str] = frozenset(),
) -> Sonuc:
    """Tek bir portföy stratejisini tek bir pencerede koşturur."""
    g = gorunum(veri, strateji, pencere, cikarilanlar=cikarilanlar)
    return CokluBacktest(strateji, maliyet, baslangic_sermaye=baslangic_sermaye).calistir(
        g, veri_sha256=veri.veri_sha256, olcum_baslangici=pencere.olcum_baslangici
    )


def _kurulabilir(
    sinif: type[PortfoyStratejisi], secenekler: Mapping[str, Sequence[Any]]
) -> list[dict[str, Any]]:
    """Izgaranın strateji kurabilen noktaları (tek sembollü `tara`nın atlama kuralı)."""
    out = []
    for p in izgara(secenekler):
        try:
            sinif(**p)  # kurucu `dogrula()`yı çağırıyor
        except (ValueError, TypeError):
            continue
        out.append(p)
    return out


# --------------------------------------------------------------------- tarama


def tara(
    sinif: type[PortfoyStratejisi],
    secenekler: Mapping[str, Sequence[Any]],
    maliyet: MaliyetModeli,
    veri: EvrenVerisi,
    pencere: Pencere,
    *,
    olcut: str = "sharpe",
    baslangic_sermaye: float = 10_000.0,
    asgari_islem: int = ASGARI_ISLEM,
    kosucu: Kosucu | None = None,
) -> tuple[TaramaSonucu, list[Sonuc]]:
    """Izgaradaki her noktayı `pencere`de koşturur. Sonuçlar da döner (PBO için)."""
    if olcut not in OLCUTLER:
        raise TaramaHatasi(f"bilinmeyen ölçüt {olcut!r}")
    skorla = OLCUTLER[olcut]
    noktalar = _kurulabilir(sinif, secenekler)
    if not noktalar:
        raise TaramaHatasi("ızgaradaki hiçbir kombinasyon geçerli bir strateji kurmadı")
    kosucu = kosucu or seri_kosucu(maliyet, veri)
    sonuclar = kosucu(
        [KosuIsi(sinif, tuple(sorted(p.items())), pencere, baslangic_sermaye) for p in noktalar]
    )
    adaylar = [
        Aday(
            parametreler=tuple(sorted(p.items())),
            skor=skorla(s.metrikler),
            metrikler=s.metrikler,
            sonuc_hash=s.sonuc_hash,
            gecerli=s.metrikler.islem_sayisi >= asgari_islem,
        )
        for p, s in zip(noktalar, sonuclar, strict=True)
    ]
    return (
        TaramaSonucu(
            strateji_adi=getattr(sinif, "ad", sinif.__name__),
            olcut=olcut,
            adaylar=adaylar,
            pencere=pencere.sozluk(),
            asgari_islem=asgari_islem,
        ),
        sonuclar,
    )


# --------------------------------------------------------------------- walk-forward


def walkforward(
    sinif: type[PortfoyStratejisi],
    secenekler: Mapping[str, Sequence[Any]],
    maliyet: MaliyetModeli,
    veri: EvrenVerisi,
    katmanlar: list[Katman],
    *,
    olcut: str = "sharpe",
    secim: str = "tepe",
    baslangic_sermaye: float = 10_000.0,
    asgari_islem: int = ASGARI_ISLEM,
    kosucu: Kosucu | None = None,
) -> WalkForwardSonucu:
    """`walkforward.calistir`ın evren karşılığı: eğitimde tara, seçileni testte koştur."""
    if not katmanlar:
        raise WalkForwardHatasi("katman listesi boş")
    sonuclar: list[KatmanSonucu] = []
    sermaye = baslangic_sermaye
    egriler: list[np.ndarray] = []
    zamanlar: list[np.ndarray] = []
    maruziyet: list[np.ndarray] = []
    islemler: list[Islem] = []
    for katman in katmanlar:
        egitim, _ = tara(
            sinif, secenekler, maliyet, veri, katman.egitim, olcut=olcut,
            baslangic_sermaye=sermaye, asgari_islem=asgari_islem, kosucu=kosucu,
        )
        en_iyi = egitim.sec(secim)
        if en_iyi is None:
            sonuclar.append(
                KatmanSonucu(
                    sira=katman.sira, secilen=None, egitim_skor=float("nan"), egitim_islem=0,
                    egitim_plato=egitim.ust_yuzde_plato(), test_metrikler=None,
                    test_islemler=[], test_ozkaynak=np.array([], dtype=np.float64),
                    test_maruziyet=np.array([], dtype=np.float64),
                    test_zamanlar=np.array([], dtype="int64"), katman=katman,
                )
            )
            continue
        test = kosu(
            sinif(**en_iyi.sozluk_parametreler), maliyet, veri, katman.test,
            baslangic_sermaye=sermaye,
        )
        sermaye = test.metrikler.bitis_sermaye
        sonuclar.append(
            KatmanSonucu(
                sira=katman.sira, secilen=en_iyi.sozluk_parametreler,
                egitim_skor=en_iyi.skor, egitim_islem=en_iyi.metrikler.islem_sayisi,
                egitim_plato=egitim.ust_yuzde_plato(), test_metrikler=test.metrikler,
                test_islemler=test.islemler, test_ozkaynak=test.ozkaynak,
                test_maruziyet=test.maruziyet, test_zamanlar=test.zamanlar, katman=katman,
            )
        )
        egriler.append(test.ozkaynak)
        zamanlar.append(test.zamanlar)
        maruziyet.append(test.maruziyet)
        islemler.extend(test.islemler)
    if not egriler:
        raise WalkForwardHatasi("hiçbir katmanda geçerli aday bulunamadı")
    bilesik = np.concatenate(egriler)
    return WalkForwardSonucu(
        strateji_adi=getattr(sinif, "ad", sinif.__name__),
        olcut=olcut,
        secim=secim,
        katmanlar=sonuclar,
        bilesik_metrikler=hesapla(
            bilesik, np.concatenate(maruziyet), islemler, timeframe_ms(veri.timeframe),
            baslangic_sermaye,
        ),
        bilesik_ozkaynak=bilesik,
        bilesik_zamanlar=np.concatenate(zamanlar),
        baslangic_sermaye=baslangic_sermaye,
    )


# --------------------------------------------------------------------- stres


def stres(
    strateji_uret: Callable[[], PortfoyStratejisi],
    maliyet: MaliyetModeli,
    veri: EvrenVerisi,
    pencere: Pencere,
    *,
    baslangic_sermaye: float = 10_000.0,
    senaryolar: Mapping[str, Mapping[str, float]] = STRES_SENARYOLARI,
) -> StresSonucu:
    """`analiz.stres`in evren karşılığı; bozulmuş maliyet kalibre değildir."""
    out: dict[str, dict[str, Any]] = {}
    ad = ""
    for senaryo, carpan in senaryolar.items():
        bozuk = MaliyetModeli(
            fee_taker_bps=maliyet.fee_taker_bps * carpan["fee"],
            slippage_bps=maliyet.slippage_bps * carpan["slippage"],
            kalibrasyon=None,
        )
        strateji = strateji_uret()
        ad = getattr(strateji, "ad", type(strateji).__name__)
        m = kosu(strateji, bozuk, veri, pencere, baslangic_sermaye=baslangic_sermaye).metrikler
        out[senaryo] = {
            "carpanlar": dict(carpan),
            "fee_taker_bps": bozuk.fee_taker_bps,
            "slippage_bps": bozuk.slippage_bps,
            "toplam_getiri": m.toplam_getiri,
            "sharpe": m.sharpe,
            "max_drawdown": m.max_drawdown,
            "islem_sayisi": m.islem_sayisi,
            "profit_factor": m.profit_factor,
            "toplam_maliyet": m.toplam_komisyon + m.toplam_slippage,
        }
    return StresSonucu(strateji_adi=ad, senaryolar=out)


# --------------------------------------------------------------------- pencereler


def pencereler(
    veri: EvrenVerisi,
    *,
    oos_orani: float = 0.30,
    egitim_bar: int = EGITIM_BAR,
    test_bar: int = TEST_BAR,
) -> tuple[Pencere, Pencere, Pencere, list[Katman]]:
    """`(in_sample, out_of_sample, tam, walk_forward katmanları)`.

    Isınma, veride pencere başından önce yüklenmiş barlardır (`veri.olcum_baslangici`):
    her pencere ısınmasını oradan alır. Veri ızgaranın en büyük ısınmasıyla yüklenmeli.
    """
    n = len(veri)
    isinma = veri.olcum_baslangici
    ins, oos = is_oos(n, isinma, oos_orani)
    tam = Pencere("tam", baslangic=isinma, bitis=n, isinma_baslangic=0)
    katmanlar = walk_forward(n, isinma, egitim_bar, test_bar, kaydirmali=True)
    return ins, oos, tam, katmanlar


def _getiriler(sonuc: Sonuc) -> np.ndarray:
    ozkaynak = sonuc.ozkaynak
    onceki = np.where(ozkaynak[:-1] != 0.0, ozkaynak[:-1], np.nan)
    return np.nan_to_num(np.diff(ozkaynak) / onceki, nan=0.0, posinf=0.0, neginf=0.0)


# --------------------------------------------------------------------- tam değerlendirme


def degerlendir(
    sinif: type[PortfoyStratejisi],
    secenekler: Mapping[str, Sequence[Any]],
    maliyet: MaliyetModeli,
    veri: EvrenVerisi,
    *,
    secim: str = "plato",
    olcut: str = "sharpe",
    oos_orani: float = 0.30,
    egitim_bar: int = EGITIM_BAR,
    test_bar: int = TEST_BAR,
    baslangic_sermaye: float = 10_000.0,
    asgari_islem: int = ASGARI_ISLEM,
    rejim_kiyasi: str = REJIM_KIYASI,
    kosucu: Kosucu | None = None,
    ilerleme: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Bir portföy çekilişini 11 kapının tamamına karşı ölçer.

    Döner: `olcumler` (kapıların okuduğu düz alanlar), `detay`, `kapilar`
    (`butun_kapilar` çıktısı) ve kayıt için pencere/parametre bilgisi.
    """
    def bildir(mesaj: str) -> None:
        if ilerleme is not None:
            ilerleme(mesaj)

    if rejim_kiyasi not in veri.diziler:
        raise EvrenDegerlendirmeHatasi(f"rejim kıyası {rejim_kiyasi} evren verisinde yok")
    kosucu = kosucu or seri_kosucu(maliyet, veri)
    yil_bar = bar_yili(timeframe_ms(veri.timeframe))
    ins, oos, tam, katmanlar = pencereler(
        veri, oos_orani=oos_orani, egitim_bar=egitim_bar, test_bar=test_bar
    )
    olcumler: dict[str, Any] = {}
    detay: dict[str, Any] = {}
    engeller: list[str] = []

    # --- in-sample tarama, seçim, pertürbasyon
    bildir("in-sample tarama")
    tarama, _ = tara(
        sinif, secenekler, maliyet, veri, ins, olcut=olcut,
        baslangic_sermaye=baslangic_sermaye, asgari_islem=asgari_islem, kosucu=kosucu,
    )
    detay["tarama"] = tarama.sozluk()
    secilen = tarama.sec(secim)

    if secilen is not None:
        parametreler = secilen.sozluk_parametreler
        detay["secim"] = {"yontem": secim, "secilen": parametreler}
        pert = pert_mod.olc(tarama, secilen)
        olcumler["perturbasyon_dusus"] = pert.dusus
        detay["perturbasyon"] = pert.sozluk()

        bildir("out-of-sample")
        oos_sonuc = kosu(sinif(**parametreler), maliyet, veri, oos,
                         baslangic_sermaye=baslangic_sermaye)
        m = oos_sonuc.metrikler
        ins_sharpe = secilen.metrikler.sharpe
        olcumler |= {
            "oos_sharpe": m.sharpe,
            "oos_getiri": m.toplam_getiri,
            "oos_islem": m.islem_sayisi,
            "oos_max_drawdown": m.max_drawdown,
            "is_sharpe": ins_sharpe,
            "oos_is_orani": (m.sharpe / ins_sharpe) if ins_sharpe > 0 else float("nan"),
            "plato_orani": tarama.ust_yuzde_plato(),
        }
        detay["oos"] = {"metrikler": m.sozluk(), "sonuc_hash": oos_sonuc.sonuc_hash,
                        "atlanan": oos_sonuc.atlanan}
        engeller = list(oos_sonuc.promotion_engelleri)

        # rejim — kıyas kapanışından, OOS'ta, ısınma barları kesilerek
        kapanis = np.asarray(veri.diziler[rejim_kiyasi]["close"], dtype=np.float64)
        pencere_bar = rejim_mod.pencere_bar(timeframe_ms(veri.timeframe))
        etiket = rejim_mod.etiketle(kapanis[oos.dilim()], pencere=pencere_bar)
        rej = rejim_mod.olc(oos_sonuc.ozkaynak, etiket[oos.olcum_baslangici:], yil_bar=yil_bar)
        olcumler["en_kotu_rejim_sharpe"] = rej.en_kotu_sharpe
        detay["rejim"] = rej.sozluk() | {"pencere": pencere_bar, "kiyas": rejim_kiyasi}

        # evren dayanıklılığı — OOS sonucunun kendisi
        bildir("evren dayanıklılığı")
        day = day_mod.olc(
            oos_sonuc,
            lambda cikar: kosu(sinif(**parametreler), maliyet, veri, oos,
                               baslangic_sermaye=baslangic_sermaye, cikarilanlar=cikar),
            k=1,
        )
        olcumler["evren_dayaniklilik_orani"] = day.oran
        detay["evren_dayanikliligi"] = day.sozluk()

        bildir("stres")
        st = stres(lambda: sinif(**parametreler), maliyet, veri, tam,
                   baslangic_sermaye=baslangic_sermaye)
        olcumler["stres_bozulma"] = st.bozulma()
        detay["stres"] = st.sozluk()
    else:
        detay["secim"] = {"yontem": secim, "secilen": None, "sebep": "geçerli aday yok"}

    # --- walk-forward
    bildir("walk-forward")
    try:
        wf = walkforward(
            sinif, secenekler, maliyet, veri, katmanlar, olcut=olcut, secim=secim,
            baslangic_sermaye=baslangic_sermaye, asgari_islem=asgari_islem, kosucu=kosucu,
        )
        basarili = wf.basarili_katmanlar
        pozitif = sum(1 for k in basarili if k.test_metrikler.toplam_getiri > 0.0)
        olcumler |= {
            "wf_sharpe": wf.bilesik_metrikler.sharpe,
            "wf_getiri": wf.bilesik_metrikler.toplam_getiri,
            "wf_max_drawdown": wf.bilesik_metrikler.max_drawdown,
            "wf_katman": len(basarili),
            "wf_pozitif_katman": pozitif,
            "wf_pozitif_katman_orani": pozitif / len(basarili) if basarili else float("nan"),
            "wf_kararsizlik": _kararsizlik(wf.parametre_kararliligi()),
        }
        detay["walk_forward"] = wf.sozluk()
    except WalkForwardHatasi as hata:
        detay["walk_forward"] = {"olculemedi": str(hata)}

    # --- PBO, tam pencere
    bildir("pbo")
    tam_tarama, tam_sonuclar = tara(
        sinif, secenekler, maliyet, veri, tam, olcut=olcut,
        baslangic_sermaye=baslangic_sermaye, asgari_islem=asgari_islem, kosucu=kosucu,
    )
    satirlar = [
        _getiriler(s)
        for a, s in zip(tam_tarama.adaylar, tam_sonuclar, strict=True)
        if a.gecerli
    ]
    try:
        if len(satirlar) < 2:
            raise pbo_mod.PboHatasi(f"{len(satirlar)} geçerli aday: PBO ölçülemez")
        pbo_sonucu = pbo_mod.cscv(np.vstack(satirlar), yil_bar=yil_bar)
        olcumler["pbo"] = pbo_sonucu.pbo
        detay["pbo"] = pbo_sonucu.sozluk()
    except pbo_mod.PboHatasi as hata:
        olcumler["pbo"] = None
        detay["pbo"] = {"olculemedi": str(hata)}

    kapi = kapilar_v2.butun_kapilar(
        getattr(sinif, "ad", sinif.__name__), olcumler, mutlak_engeller=engeller
    )
    return {
        "strateji": getattr(sinif, "ad", sinif.__name__),
        "izgara": {a: list(d) for a, d in sorted(secenekler.items())},
        "secim": secim,
        "olcut": olcut,
        "pencereler": {
            "in_sample": ins.sozluk(),
            "out_of_sample": oos.sozluk(),
            "tam": tam.sozluk(),
            "walk_forward": {"egitim_bar": egitim_bar, "test_bar": test_bar,
                             "katman": len(katmanlar)},
        },
        "olcumler": olcumler,
        "detay": detay,
        "kapilar": kapi.sozluk(),
    }


__all__ = [
    "KESITSEL_PORTFOY",
    "KESITSEL_SECIM",
    "REJIM_KIYASI",
    "EvrenDegerlendirmeHatasi",
    "KosuIsi",
    "Kosucu",
    "isi_kos",
    "degerlendir",
    "gorunum",
    "havuz_kosucu",
    "hipotez_kur",
    "isci_baslat",
    "isci_kos",
    "kosu",
    "pencereler",
    "seri_kosucu",
    "stres",
    "tara",
    "veri_kimligi",
    "walkforward",
]
