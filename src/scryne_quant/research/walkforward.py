"""Walk-forward analizi: her katmanda optimize et, **sonraki** katmanda test et. (Faz 4)

Tek bir in-sample/out-of-sample bölmesi bir soruyu cevaplar: "bu parametre bir kez de
görmediği veride tuttu mu". Walk-forward daha zor bir soruyu sorar: **"parametre seçimi
prosedürü tekrarlanabilir mi"** — yani her dönem yeniden optimize edip sonraki dönemde
kullanmak sistematik olarak işe yarıyor mu.

Aradaki fark küçük görünüyor ama kritik: tek bir OOS testi şansla geçilebilir. Sekiz
katmanın sekizinde de tutan bir prosedür şansla açıklanamaz. Tersi de doğru ve bu projede
daha muhtemel: katmanlar arasında **seçilen parametrenin zıplaması**, stratejinin
gerçekte bir şey yakalamadığının en net göstergesidir.

**Bileşik OOS eğrisi**, katmanların test sonuçlarını uç uca ekler ve gerçek bir "prosedürü
baştan sona uygulasaydık ne olurdu" cevabı verir. Katman başına sermaye sıfırlanmaz;
önceki katmanın bitiş sermayesi sonrakinin başlangıcı olur — aksi hâlde bileşik getiri
hesabı kaybı da kazancı da yok sayardı.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from scryne_quant.backtest.metrikler import Islem, Metrikler, hesapla
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.research.bolme import Katman
from scryne_quant.research.tarama import ASGARI_ISLEM, Aday, TaramaSonucu, kosu, tara
from scryne_quant.strategy.temel import Strateji


class WalkForwardHatasi(ValueError):
    """Walk-forward kurulumu geçersiz."""


@dataclass(frozen=True, slots=True)
class KatmanSonucu:
    """Bir katmanın eğitim taraması ve test sonucu."""

    sira: int
    secilen: dict[str, Any] | None
    egitim_skor: float
    egitim_islem: int
    egitim_plato: float
    test_metrikler: Metrikler | None
    test_islemler: list[Islem]
    test_ozkaynak: np.ndarray
    test_maruziyet: np.ndarray
    test_zamanlar: np.ndarray
    katman: Katman

    @property
    def basarili(self) -> bool:
        """Eğitimde geçerli bir aday bulundu ve testte koşturuldu mu."""
        return self.secilen is not None and self.test_metrikler is not None

    def sozluk(self) -> dict[str, Any]:
        return {
            "sira": self.sira,
            "pencereler": self.katman.sozluk(),
            "secilen": self.secilen,
            "egitim": {
                "skor": self.egitim_skor,
                "islem": self.egitim_islem,
                "plato_orani": self.egitim_plato,
            },
            "test": self.test_metrikler.sozluk() if self.test_metrikler else None,
        }


@dataclass(frozen=True, slots=True)
class WalkForwardSonucu:
    """Tüm katmanlar + birleşik OOS eğrisi."""

    strateji_adi: str
    olcut: str
    katmanlar: list[KatmanSonucu]
    bilesik_metrikler: Metrikler
    bilesik_ozkaynak: np.ndarray
    bilesik_zamanlar: np.ndarray
    baslangic_sermaye: float

    @property
    def basarili_katmanlar(self) -> list[KatmanSonucu]:
        return [k for k in self.katmanlar if k.basarili]

    def parametre_kararliligi(self) -> dict[str, Any]:
        """Katmanlar arasında seçilen parametreler ne kadar oynak.

        **Faz 4'ün bitti kriterindeki "parametre kararlılığı görülebiliyor" maddesi bu.**
        Her sayısal parametre için katmanlar boyunca benzersiz değer sayısı, değişim
        katsayısı (std/ortalama) ve değerlerin kendisi raporlanıyor.

        Nasıl okunur: `benzersiz == 1` ise prosedür her katmanda aynı parametreyi seçti —
        güçlü bir kararlılık işareti. `degisim_katsayisi` büyükse seçim katmandan katmana
        zıplıyor demektir ve o strateji, canlıda hangi parametreyle çalıştırılacağı
        sorusuna cevap veremez.
        """
        basarili = self.basarili_katmanlar
        if not basarili:
            return {"katman": 0, "parametreler": {}}

        adlar = sorted(basarili[0].secilen or {})
        out: dict[str, Any] = {}
        for ad in adlar:
            degerler = [k.secilen[ad] for k in basarili if k.secilen and ad in k.secilen]
            sayisal = [float(d) for d in degerler if isinstance(d, int | float)]
            kayit: dict[str, Any] = {
                "degerler": degerler,
                "benzersiz": len(set(map(repr, degerler))),
            }
            if sayisal:
                ort = float(np.mean(sayisal))
                std = float(np.std(sayisal, ddof=1)) if len(sayisal) > 1 else 0.0
                kayit["ortalama"] = ort
                kayit["std"] = std
                kayit["degisim_katsayisi"] = std / abs(ort) if ort else 0.0
            out[ad] = kayit
        return {"katman": len(basarili), "parametreler": out}

    def sozluk(self, *, egri: bool = False) -> dict[str, Any]:
        govde: dict[str, Any] = {
            "strateji": self.strateji_adi,
            "olcut": self.olcut,
            "katman_sayisi": len(self.katmanlar),
            "basarili_katman": len(self.basarili_katmanlar),
            "baslangic_sermaye": self.baslangic_sermaye,
            "bilesik_oos": self.bilesik_metrikler.sozluk(),
            "parametre_kararliligi": self.parametre_kararliligi(),
            "katmanlar": [k.sozluk() for k in self.katmanlar],
        }
        if egri:
            govde["bilesik_egri"] = {
                "zamanlar": self.bilesik_zamanlar.tolist(),
                "ozkaynak": self.bilesik_ozkaynak.tolist(),
            }
        return govde


def calistir(
    strateji_sinifi: type[Strateji],
    secenekler: Mapping[str, Sequence[Any]],
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    katmanlar: list[Katman],
    *,
    olcut: str = "sharpe",
    baslangic_sermaye: float = 10_000.0,
    asgari_islem: int = ASGARI_ISLEM,
) -> WalkForwardSonucu:
    """Katmanları sırayla işler: eğitimde tara, seçileni testte koştur.

    `asgari_islem`: kıyas ölçütü için 0 verilir. Al-tut bir kez alıp tutar, yani katman
    içinde kapanmış tur sayısı sıfırdır; varsayılan şart ona uygulanınca "hiçbir katmanda
    geçerli aday yok" hatası çıkar ve karşılaştırmanın referans çizgisi kaybolur.
    Ölçüldü — bu hatayı gerçekten aldık.

    Sermaye katmanlar arasında **taşınır**. Her katmanı 10.000 ile başlatmak, kaybeden bir
    katmanın sonrakini küçültmesini engellerdi — yani bileşik sonuç gerçekte olacaktan
    daha iyi çıkardı. K-007'nin "belirsizlikte aleyhte yuvarla" kuralının aynı ailesi.
    """
    if not katmanlar:
        raise WalkForwardHatasi("katman listesi boş")

    sonuclar: list[KatmanSonucu] = []
    sermaye = baslangic_sermaye
    egriler: list[np.ndarray] = []
    zamanlar: list[np.ndarray] = []
    tum_islemler: list[Islem] = []
    tum_maruziyet: list[np.ndarray] = []

    for katman in katmanlar:
        egitim: TaramaSonucu = tara(
            strateji_sinifi,
            secenekler,
            maliyet,
            sembol,
            timeframe,
            bar_dizileri,
            katman.egitim,
            olcut=olcut,
            baslangic_sermaye=sermaye,
            asgari_islem=asgari_islem,
        )
        en_iyi: Aday | None = egitim.en_iyi

        if en_iyi is None:
            # Bu katmanda yeterli işlem yapan aday yok. Zorla bir aday seçmek, "hiçbir
            # parametre çalışmadı" bulgusunu silerdi; sermaye değişmeden devam ediyoruz.
            sonuclar.append(
                KatmanSonucu(
                    sira=katman.sira,
                    secilen=None,
                    egitim_skor=float("nan"),
                    egitim_islem=0,
                    egitim_plato=egitim.ust_yuzde_plato(),
                    test_metrikler=None,
                    test_islemler=[],
                    test_ozkaynak=np.array([], dtype=np.float64),
                    test_maruziyet=np.array([], dtype=np.float64),
                    test_zamanlar=np.array([], dtype="int64"),
                    katman=katman,
                )
            )
            continue

        test = kosu(
            strateji_sinifi(**en_iyi.sozluk_parametreler),
            maliyet,
            sembol,
            timeframe,
            bar_dizileri,
            katman.test,
            baslangic_sermaye=sermaye,
        )
        sermaye = test.metrikler.bitis_sermaye

        sonuclar.append(
            KatmanSonucu(
                sira=katman.sira,
                secilen=en_iyi.sozluk_parametreler,
                egitim_skor=en_iyi.skor,
                egitim_islem=en_iyi.metrikler.islem_sayisi,
                egitim_plato=egitim.ust_yuzde_plato(),
                test_metrikler=test.metrikler,
                test_islemler=test.islemler,
                test_ozkaynak=test.ozkaynak,
                test_maruziyet=test.maruziyet,
                test_zamanlar=test.zamanlar,
                katman=katman,
            )
        )
        egriler.append(test.ozkaynak)
        zamanlar.append(test.zamanlar)
        tum_maruziyet.append(test.maruziyet)
        tum_islemler.extend(test.islemler)

    if not egriler:
        raise WalkForwardHatasi(
            "hiçbir katmanda geçerli aday bulunamadı — ızgara veya asgari işlem şartı gözden "
            "geçirilmeli"
        )

    bilesik = np.concatenate(egriler)
    return WalkForwardSonucu(
        strateji_adi=getattr(strateji_sinifi, "ad", strateji_sinifi.__name__),
        olcut=olcut,
        katmanlar=sonuclar,
        bilesik_metrikler=hesapla(
            bilesik,
            np.concatenate(tum_maruziyet),
            tum_islemler,
            timeframe_ms(timeframe),
            baslangic_sermaye,
        ),
        bilesik_ozkaynak=bilesik,
        bilesik_zamanlar=np.concatenate(zamanlar),
        baslangic_sermaye=baslangic_sermaye,
    )
