"""PBO: backtest overfitting olasılığı, CSCV ile. (K-054, Faz 11)

**Sorduğu soru diğer kapılardan farklı.** `oos_sharpe` *"bu strateji dışarıda iyi mi"*
diye sorar; `oos_is_orani` *"içerideki başarının ne kadarı korundu"* diye. PBO ise
prosedürü sorgular: *"in-sample'da en iyiyi seçme yöntemim, out-of-sample'da medyanın
altına düşen bir aday seçme olasılığı nedir?"* Yani ölçtüğü şey bir stratejinin
performansı değil, **seçim yönteminin kendisinin** ne kadar kandırdığı.

## Yöntem (Bailey, Borwein, López de Prado, Zhu — CSCV)

1. Izgaradaki her parametre kombinasyonunun bar-bar getiri serisi alınır: `N × T` matris.
2. `T`, `S` adet bitişik dilime bölünür (`S` çift).
3. `S/2` dilimin **her** seçimi bir IS kümesi, kalanı OOS kümesi olur —
   `C(S, S/2)` kombinasyon. "Kombinatoryal simetrik" adı buradan: her IS bölümünün
   tümleyeni de ayrıca bir IS bölümü olarak değerlendirilir, yani zaman yönü lehte veya
   aleyhte çalışamaz.
4. Her kombinasyonda IS'in en iyi adayı seçilir; o adayın **OOS sıralamasındaki göreli
   yeri** `w ∈ (0,1)` hesaplanır ve logit'i alınır: `λ = ln(w / (1−w))`.
5. **PBO = λ < 0 olan kombinasyonların oranı** — yani IS'in en iyisinin OOS'ta medyanın
   altına düştüğü durumların payı.

**Null'ı teoremdir, tahmin değil:** hiçbir adayın gerçek bir edge'i yoksa IS-en iyisinin
OOS sırası düzgün dağılır ve PBO 0,5'e gider. Bu yüzden 0,5 "yazı tura" çizgisidir ve
eşiğin ondan **belirgin biçimde** aşağıda olması gerekir; ne kadar aşağıda olacağı bu
projede ölçülür (`sq lab pbo --null`), varsayılmaz.

## Neden dilim toplamlarıyla hesaplanıyor

`S=16` için 12.870 kombinasyon var ve her birinde `N` adayın Sharpe'ı gerekiyor. Ham
yoldan bu, 45.000 barlık seriyi kombinasyon başına yeniden gezmek demek. Bunun yerine
dilim başına `n`, `Σr`, `Σr²` önceden hesaplanıyor; bir kümenin Sharpe'ı bu üç toplamın
toplanmasıyla **tam olarak** çıkıyor. Yaklaşım yok — aynı sayı, sabit zamanda.

## Ölçmediği şeyler

- **Maliyet modelinin doğruluğunu.** Getiri serileri gerçek motordan geliyor, yani
  maliyet içinde; ama maliyet varsayımı yanlışsa PBO da yanlış veriyle çalışır.
- **Izgaranın dışını.** PBO verilen ızgaradaki seçim yöntemini ölçer. Izgarayı sonuca
  bakarak genişletmek PBO'ya görünmez ve o sapmayı hipotez defteri sayar (K-039).
- **Tek adaylı ızgarayı.** `N < 2` ise seçim diye bir şey yoktur; PBO **ölçülemez**
  (`None`) ve ölçülemeyen kapı geçilmiş sayılmaz (K-019).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np

from scryne_quant.backtest.motor import Backtest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.tarama import ASGARI_ISLEM, izgara
from scryne_quant.strategy.temel import Strateji

#: Dilim sayısı. Bailey ve arkadaşlarının kullandığı değer; 12.870 kombinasyon üretiyor.
#: Daha az dilim daha az kombinasyon (yani daha gürültülü bir PBO tahmini), daha fazlası
#: kombinasyon sayısını patlatır — `S=20` için 184.756.
VARSAYILAN_DILIM: Final = 16

#: `w` logit'e girerken 0 ve 1'den uzak tutulur: `ln(0)` tanımsız. Pay, sıralamanın
#: `(sira + 0.5) / N` biçiminde hesaplanmasıyla zaten sağlanıyor; bu sabit yalnızca
#: kayan nokta uçlarına karşı emniyet.
LOGIT_PAYI: Final = 1e-12


class PboHatasi(ValueError):
    """PBO girdisi geçersiz."""


@dataclass(frozen=True, slots=True)
class PboSonucu:
    """CSCV çıktısı."""

    pbo: float
    """IS'in en iyisinin OOS'ta medyanın altına düştüğü kombinasyonların oranı."""

    aday_sayisi: int
    dilim_sayisi: int
    kombinasyon_sayisi: int
    bar_sayisi: int

    medyan_logit: float
    """`λ` medyanı. Pozitif = seçim OOS'ta medyanın üstünde kalıyor."""

    performans_bozulmasi: float
    """OOS Sharpe'ın IS Sharpe'a göre ortalama düşüşü (Sharpe birimi).

    PBO bir **sıra** ölçüsü: seçilen adayın diğerlerine göre yerini söyler, mutlak
    performansını değil. Bütün adaylar OOS'ta çöküyorsa PBO düşük kalabilir. Bu alan o
    kör noktayı kapatıyor ve bu yüzden PBO ile **birlikte** okunur.
    """

    zarar_olasiligi: float
    """Seçilen adayın OOS Sharpe'ının negatif çıktığı kombinasyonların oranı."""

    logitler: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))

    def sozluk(self) -> dict[str, Any]:
        return {
            "pbo": self.pbo,
            "aday_sayisi": self.aday_sayisi,
            "dilim_sayisi": self.dilim_sayisi,
            "kombinasyon_sayisi": self.kombinasyon_sayisi,
            "bar_sayisi": self.bar_sayisi,
            "medyan_logit": self.medyan_logit,
            "performans_bozulmasi": self.performans_bozulmasi,
            "zarar_olasiligi": self.zarar_olasiligi,
        }


def _dilim_sinirlari(n: int, dilim: int) -> list[tuple[int, int]]:
    """`n` barı `dilim` adet **bitişik** parçaya böler; artan bar ilk dilimlere dağılır.

    Bitişik olması şart: rastgele bölme komşu barları eğitim ve teste dağıtır ve zaman
    serisinde komşu barlar birbirine benzer (`research/bolme.py`nin birinci kuralı).
    """
    if dilim < 2 or dilim % 2:
        raise PboHatasi(f"dilim sayısı çift ve ≥2 olmalı: {dilim}")
    if n < dilim * 2:
        raise PboHatasi(f"{n} bar {dilim} dilime bölünemez (dilim başına <2 bar)")
    taban, artan = divmod(n, dilim)
    sinirlar: list[tuple[int, int]] = []
    bas = 0
    for i in range(dilim):
        boy = taban + (1 if i < artan else 0)
        sinirlar.append((bas, bas + boy))
        bas += boy
    return sinirlar


def _dilim_toplamlari(
    getiriler: np.ndarray, sinirlar: Sequence[tuple[int, int]]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Dilim başına `(n, Σr, Σr²)`. Bir kümenin Sharpe'ı bunların toplamından **tam** çıkar."""
    s = len(sinirlar)
    n_ = np.array([bit - bas for bas, bit in sinirlar], dtype=np.float64)
    toplam = np.empty((getiriler.shape[0], s), dtype=np.float64)
    kare = np.empty_like(toplam)
    for j, (bas, bit) in enumerate(sinirlar):
        parca = getiriler[:, bas:bit]
        toplam[:, j] = parca.sum(axis=1)
        kare[:, j] = (parca**2).sum(axis=1)
    return n_, toplam, kare


def _sharpe(n: np.ndarray, toplam: np.ndarray, kare: np.ndarray, yil_bar: float) -> np.ndarray:
    """Toplamlardan yıllıklandırılmış Sharpe. `n<2` veya sapma 0 ise 0 (ölçülemez değil, düz).

    Sıfır dönmek bilinçli: sapması sıfır olan bir aday hiç işlem yapmamış demektir ve
    sıralamada en alta değil **ortaya** düşmeli — sıfır getirili bir aday, kaybeden bir
    adaydan iyidir.
    """
    n_toplam = n.sum()
    if n_toplam < 2:
        return np.zeros(toplam.shape[0], dtype=np.float64)
    ort = toplam / n_toplam
    # Örneklem varyansı: (Σr² − n·ort²) / (n−1)
    var = (kare - n_toplam * ort**2) / (n_toplam - 1.0)
    var = np.maximum(var, 0.0)
    sapma = np.sqrt(var)
    with np.errstate(divide="ignore", invalid="ignore"):
        sr = np.where(sapma > 0.0, ort / sapma, 0.0)
    return np.nan_to_num(sr, nan=0.0, posinf=0.0, neginf=0.0) * math.sqrt(yil_bar)


def cscv(
    getiriler: np.ndarray,
    *,
    yil_bar: float,
    dilim: int = VARSAYILAN_DILIM,
) -> PboSonucu:
    """CSCV ile PBO. `getiriler`: `N × T` bar getiri matrisi (satır = aday).

    `yil_bar` yıllıklandırma için; Sharpe'ların **sırası** ondan bağımsız, ama
    `performans_bozulmasi` ve `zarar_olasiligi` mutlak Sharpe okuduğu için gerekli.
    """
    getiriler = np.asarray(getiriler, dtype=np.float64)
    if getiriler.ndim != 2:
        raise PboHatasi(f"getiri matrisi 2 boyutlu olmalı, verilen: {getiriler.ndim}")
    aday, bar = getiriler.shape
    if aday < 2:
        raise PboHatasi(
            f"PBO en az 2 aday ister, verilen: {aday}. Tek adaylı bir ızgarada "
            "'seçim' diye bir şey yok ve ölçülecek seçim sapması da yok."
        )

    sinirlar = _dilim_sinirlari(bar, dilim)
    n_, toplam, kare = _dilim_toplamlari(getiriler, sinirlar)
    tum = set(range(dilim))

    logitler: list[float] = []
    bozulmalar: list[float] = []
    zararlar: list[bool] = []

    for ins in itertools.combinations(range(dilim), dilim // 2):
        ins_idx = list(ins)
        oos_idx = sorted(tum - set(ins))

        is_sr = _sharpe(n_[ins_idx], toplam[:, ins_idx].sum(1), kare[:, ins_idx].sum(1), yil_bar)
        oos_sr = _sharpe(n_[oos_idx], toplam[:, oos_idx].sum(1), kare[:, oos_idx].sum(1), yil_bar)

        # Eşit skorda küçük indeksli aday seçilir — `argmax`ın davranışı ve determinizmin
        # (K-009) gereği: rastgele bozmak aynı ızgarada iki farklı PBO üretirdi.
        secilen = int(np.argmax(is_sr))

        # Göreli sıra: seçilenin OOS Sharpe'ının kaçından büyük olduğu. `(sira+0.5)/N`
        # ile 0 ve 1 uçlarından kaçınılıyor — tek adaylı uçta logit tanımsız olurdu.
        sira = int((oos_sr < oos_sr[secilen]).sum()) + 0.5 * int(
            (oos_sr == oos_sr[secilen]).sum()
        )
        w = min(max(sira / aday, LOGIT_PAYI), 1.0 - LOGIT_PAYI)
        logitler.append(math.log(w / (1.0 - w)))
        bozulmalar.append(float(is_sr[secilen] - oos_sr[secilen]))
        zararlar.append(bool(oos_sr[secilen] < 0.0))

    dizi = np.array(logitler, dtype=np.float64)
    return PboSonucu(
        pbo=float((dizi < 0.0).mean()),
        aday_sayisi=aday,
        dilim_sayisi=dilim,
        kombinasyon_sayisi=len(logitler),
        bar_sayisi=bar,
        medyan_logit=float(np.median(dizi)),
        performans_bozulmasi=float(np.mean(bozulmalar)),
        zarar_olasiligi=float(np.mean(zararlar)),
        logitler=dizi,
    )


def getiri_matrisi(
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
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Izgaradaki her geçerli adayın bar getiri serisini toplar.

    Döner: `(N × T matris, aday parametreleri)`. Yalnızca `asgari_islem` şartını sağlayan
    adaylar alınıyor — `tarama.tara`nın `gecerli` kuralının aynısı. Geçersizleri katmak
    PBO'yu **iyimser** yapardı: hiç işlem yapmayan bir aday OOS'ta kaybetmez ve seçilenin
    sırasını yapay olarak yükseltir.
    """
    dilim = {ad: dizi[pencere.dilim()] for ad, dizi in bar_dizileri.items()}
    satirlar: list[np.ndarray] = []
    parametreler: list[dict[str, Any]] = []

    for p in izgara(secenekler):
        try:
            strateji = strateji_sinifi(**p)
        except (ValueError, TypeError):
            continue  # ızgaranın anlamsız köşesi; strateji kendi kuralını uyguladı
        sonuc = Backtest(strateji, maliyet, baslangic_sermaye=baslangic_sermaye).calistir(
            sembol, timeframe, dilim, olcum_baslangici=pencere.olcum_baslangici
        )
        if sonuc.metrikler.islem_sayisi < asgari_islem:
            continue
        ozkaynak = sonuc.ozkaynak
        onceki = np.where(ozkaynak[:-1] != 0.0, ozkaynak[:-1], np.nan)
        getiri = np.nan_to_num(np.diff(ozkaynak) / onceki, nan=0.0, posinf=0.0, neginf=0.0)
        satirlar.append(getiri)
        parametreler.append(dict(sorted(p.items())))

    if len(satirlar) < 2:
        raise PboHatasi(
            f"{len(satirlar)} geçerli aday: PBO ölçülemez. Bu bir hata değil bir bulgu — "
            "ızgarada yeterince işlem yapan iki aday yoksa ölçülecek bir seçim de yok."
        )
    return np.vstack(satirlar), parametreler


__all__ = [
    "LOGIT_PAYI",
    "VARSAYILAN_DILIM",
    "PboHatasi",
    "PboSonucu",
    "cscv",
    "getiri_matrisi",
]
