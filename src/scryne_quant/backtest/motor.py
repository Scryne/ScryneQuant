"""Tek sembollü backtest: çok enstrümanlı motorun **özel hâli**. (Faz 3, Faz 10)

Faz 3'te bu dosya event loop'un kendisiydi. Faz 10'da döngü `coklu_motor.py`ye taşındı ve
burada bir sarmalayıcı kaldı — çünkü K-052/2 *"çok enstrümanlı motor ikinci bir motor
değildir"* diyor ve iki motorun "aynı sonucu verdiğini" test etmek, tek motorun aynı
sonucu vermesiyle aynı şey değil. İkisi bir gün ayrışabilir; tek kod yolu ayrışamaz.

**Sarmalayıcının yaptığı üç şey:**

1. Tek sembolü tek elemanlı bir evrene çevirir (üyelik: her barda üye — tek sembollü bir
   koşuda evren kuralı diye bir şey yoktur, sembol verilmiştir).
2. `Strateji`yi `TekEnstruman` ile portföy sözleşmesine taşır; sarmalayıcı `sozluk()`ü
   olduğu gibi devrettiği için `config_hash` değişmez (K-009).
3. Sonucu **tek sembollü biçimde** kurdurur (`tekil_sembol=`): `veri` o sembolü anlatır,
   `evren` alanı yazılmaz, işlem satırlarına sembol eklenmez. Böylece Faz 1-7'de `runs/`
   altına kaydedilmiş her sonucun `sonuc_hash`i aynı kalır.

Barın iç sırası, fill kuralı (K-004), maliyet (K-007), `ok` olmayan bar davranışı (K-028)
ve risk kesme noktası (K-032) değişmedi — hepsi `coklu_motor.py`de ve oradaki docstring
aynı gerekçeleri taşıyor.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.backtest.sonuc import VARSAYILAN_KALITE_ESIGI, Sonuc
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.risk.motor import RISK_ATR_PENCERESI, RiskMotoru
from scryne_quant.strategy.baglam import PiyasaGorunumu
from scryne_quant.strategy.kosu import evren_gorunum_kur
from scryne_quant.strategy.temel import Strateji, TekEnstruman


class BacktestHatasi(ValueError):
    """Backtest kurulumu geçersiz."""


class Backtest:
    """Tek sembol, tek strateji, spot, uzun-yönlü backtest.

    Kapsam v1'de bilinçli olarak dardı ve dar kalıyor: bu sınıf tek sembolü anlatır. Çok
    enstrümanlı koşular `CokluBacktest` ile yapılır; ikisi aynı döngüyü çalıştırır.
    """

    def __init__(
        self,
        strateji: Strateji,
        maliyet: MaliyetModeli,
        *,
        baslangic_sermaye: float = 10_000.0,
        seed: int = 0,
        kalite_esigi: float = VARSAYILAN_KALITE_ESIGI,
        risk: RiskMotoru | None = None,
    ) -> None:
        if baslangic_sermaye <= 0.0:
            raise BacktestHatasi(f"başlangıç sermayesi pozitif olmalı: {baslangic_sermaye}")
        self.strateji = strateji
        self.maliyet = maliyet
        self.baslangic_sermaye = baslangic_sermaye
        self.seed = seed
        self.kalite_esigi = kalite_esigi

        self.risk = risk
        """Risk motoru. `None` = devre dışı, ve bu **araştırma** için kasıtlı bir seçenek.

        Neden opsiyonel: Faz 1-4'ün tamamı risk motoru olmadan ölçüldü ve o ölçümler
        karşılaştırma tabanı. Risk motorunu zorunlu kılmak, Faz 4'ün sonuçlarını yeniden
        üretilemez hâle getirir — oysa `sq lab dogrula` tam olarak onu yapıyor.

        Bu, "risk atlanabilir" demek **değil**: backtest bir simülasyondur, execution
        değil. Gerçek emrin geçtiği kapı (`execution/kapi.py`) `OnayliNiyet` dışında
        hiçbir şey kabul etmiyor ve paper/live modunda motor zorunlu. Atlanamayan şey
        borsaya giden yol; ölçülebilir olan şey "risk limitleri bu stratejiye ne yapar".
        """

    # ------------------------------------------------------------------ koşu

    def calistir(
        self,
        sembol: str,
        timeframe: str,
        bar_dizileri: Mapping[str, np.ndarray],
        *,
        veri_sha256: str = "",
        olcum_baslangici: int = 0,
    ) -> Sonuc:
        """Backtest'i koşturur ve tam sonuç kaydını döndürür.

        `olcum_baslangici`: bu indeksten **önceki** barlar yalnızca indikatör ısınması
        içindir — orada üretilen sinyaller işleme dönmez ve equity eğrisi ile metrikler
        o indeksten başlar.

        Faz 4'ün walk-forward'ı için var. Bir katmanı yalnızca kendi barlarıyla
        koşturmak, indikatörleri sıfırdan ısıtmak demek olurdu — oysa canlıda o tarihe
        gelindiğinde geçmiş veri elde olurdu. İndikatörler nedensel olduğu için (K-002)
        önceki barları hesaba katmak look-ahead değil, **gerçekçilik**tir; ölçümü o
        barlardan başlatmak ise katmanın sınırını korur.
        """
        n = len(bar_dizileri["open_time"])
        if n < 2:
            raise BacktestHatasi(f"backtest için en az 2 bar gerekir, verilen: {n}")
        if not 0 <= olcum_baslangici < n - 1:
            raise BacktestHatasi(
                f"ölçüm başlangıcı 0..{n - 2} aralığında olmalı, verilen: {olcum_baslangici}"
            )

        sarmal = TekEnstruman(self.strateji, sembol)
        gorunum = evren_gorunum_kur(
            timeframe,
            {sembol: dict(bar_dizileri)},
            # Tek sembollü koşuda evren kuralı yok: sembol verilmiştir, seçilmemiştir.
            # Hep-üye bir maske, "evren seçimi bu koşunun sorusu değil" demenin kod hâli.
            {sembol: np.ones(n, dtype=bool)},
            sarmal,
        )
        coklu = CokluBacktest(
            sarmal,
            self.maliyet,
            baslangic_sermaye=self.baslangic_sermaye,
            seed=self.seed,
            kalite_esigi=self.kalite_esigi,
            risk=self.risk,
        )
        return coklu.calistir(
            gorunum,
            veri_sha256={sembol: veri_sha256},
            olcum_baslangici=olcum_baslangici,
            tekil_sembol=sembol,
        )


def calistir(
    strateji: Strateji,
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    *,
    baslangic_sermaye: float = 10_000.0,
    seed: int = 0,
    veri_sha256: str = "",
) -> Sonuc:
    """Tek çağrılık kolaylık sarmalayıcısı."""
    return Backtest(
        strateji, maliyet, baslangic_sermaye=baslangic_sermaye, seed=seed
    ).calistir(sembol, timeframe, bar_dizileri, veri_sha256=veri_sha256)


#: Faz 3'te bu sabit burada doğdu ve Faz 6'da `risk/motor.py`ye taşındı; adı burada da
#: görünür kalıyor çünkü Faz 5'in testleri backtest tarafından okuyor.
__all__ = [
    "RISK_ATR_PENCERESI",
    "Backtest",
    "BacktestHatasi",
    "PiyasaGorunumu",
    "calistir",
]
