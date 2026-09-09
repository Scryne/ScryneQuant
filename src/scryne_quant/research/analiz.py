"""Monte Carlo ve stres testi. (Faz 4, §15.1)

İki farklı soru soruyor ve ikisi de "bu sonuca güvenilir mi" sorusunun parçası:

**Monte Carlo — sonuç sıralamaya ne kadar bağlı?** Aynı işlem kümesi farklı sırayla
gelseydi equity eğrisi ne olurdu. Toplam getiri sıralamadan bağımsızdır (çarpım
değişmeli), ama **max drawdown değildir**: aynı kazanç ve kayıplar farklı sırada dizilince
düşüş çok daha derin olabilir. Yani "geçmişte %20 düştü" cümlesi, "en fazla %20 düşer"
demek değil — bu ayrım risk limitlerini (Faz 5) belirleyen şey.

**Stres testi — maliyet ve gecikme varsayımları bozulursa ne olur?** Maliyet modeli
kalibre edildi (K-021) ama kalibrasyon bir tahmindir. Slippage iki katına çıkarsa hâlâ
ayakta kalan bir strateji ile ancak tam kalibrasyonda kârlı olan strateji aynı şey değil.

**Determinizm:** her iki analiz de `seed` alır ve aynı seed aynı sonucu verir (K-009).
`np.random.default_rng(seed)` — global rastgele durum **kullanılmaz**; global durum,
çağrı sırasına bağlı sonuç demek olurdu.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from scryne_quant.backtest.metrikler import Islem, drawdown
from scryne_quant.backtest.motor import Backtest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.research.bolme import Pencere
from scryne_quant.strategy.temel import Strateji

#: Raporlanan persentiller. p05 kötü senaryo, p50 tipik, p95 iyi senaryo.
PERSENTILLER: Final[tuple[int, ...]] = (5, 25, 50, 75, 95)


class AnalizHatasi(ValueError):
    """Analiz girdisi yetersiz."""


@dataclass(frozen=True, slots=True)
class MonteCarloSonucu:
    """İşlem sırası karıştırılarak üretilen dağılım."""

    deneme: int
    islem_sayisi: int
    gercek_max_drawdown: float
    gercek_getiri: float
    drawdown_dagilimi: dict[str, float]
    getiri_dagilimi: dict[str, float]
    kotu_kuyruk_orani: float
    """Gerçekleşen düşüşten **daha kötü** çıkan denemelerin oranı.

    Yüksek olması iyi haber değil — gerçekleşmiş geçmişin şanslı bir sıralama olduğunu
    gösterir. 0,90 ise: aynı işlemler başka sırayla gelseydi vakaların %90'ında daha derin
    düşerdik.
    """

    seed: int

    def sozluk(self) -> dict[str, Any]:
        return {
            "deneme": self.deneme,
            "islem_sayisi": self.islem_sayisi,
            "seed": self.seed,
            "gercek": {
                "max_drawdown": self.gercek_max_drawdown,
                "getiri": self.gercek_getiri,
            },
            "max_drawdown_dagilimi": self.drawdown_dagilimi,
            "getiri_dagilimi": self.getiri_dagilimi,
            "gercekten_kotu_oran": self.kotu_kuyruk_orani,
        }


def monte_carlo(
    islemler: Sequence[Islem],
    baslangic_sermaye: float,
    *,
    deneme: int = 1_000,
    seed: int = 0,
) -> MonteCarloSonucu:
    """İşlem sırasını karıştırarak düşüş ve getiri dağılımını çıkarır.

    Yöntem: her işlemin **oransal** getirisi (`net_pnl / giriş notional`) alınır, sıra
    karıştırılır ve sermaye üzerinde bileşik olarak uygulanır. Mutlak P&L'i karıştırmak
    yanlış olurdu: 10.000 sermayeyle yapılan 200 USDT kâr ile 4.000 sermayeyle yapılan
    200 USDT kâr aynı olay değil, ve sıralama değişince pozisyon büyüklükleri de değişir.

    **Ne kanıtlamaz:** işlemlerin bağımsız olduğunu varsayar. Trend takip eden bir
    stratejide ardışık kazançlar ilişkilidir; karıştırmak o ilişkiyi yok eder ve gerçek
    kuyruk riskini **olduğundan iyimser** gösterebilir. Yani bu test kötü haber verdiğinde
    inanılır, iyi haber verdiğinde tek başına yeterli değildir.
    """
    kapali = [i for i in islemler if i.kapali and i.giris_notional > 0.0]
    if len(kapali) < 2:
        raise AnalizHatasi(f"Monte Carlo için en az 2 kapalı işlem gerekir, verilen: {len(kapali)}")
    if deneme < 1:
        raise AnalizHatasi(f"deneme sayısı pozitif olmalı: {deneme}")

    oranlar = np.array([i.net_pnl / i.giris_notional for i in kapali], dtype=np.float64)
    # Maruziyet 1'in altındaysa işlem tüm sermayeyi bağlamaz; oranı olduğu gibi bileşik
    # uygulamak sermayeye göre biraz abartır. Muhafazakâr yön bu — dağılım gerçekten
    # olacağından geniş çıkar, dar değil.
    rng = np.random.default_rng(seed)

    dususler = np.empty(deneme, dtype=np.float64)
    getiriler = np.empty(deneme, dtype=np.float64)
    for d in range(deneme):
        sira = rng.permutation(oranlar)
        egri = baslangic_sermaye * np.cumprod(1.0 + sira)
        egri = np.concatenate([[baslangic_sermaye], egri])
        dususler[d] = drawdown(egri).azami
        getiriler[d] = egri[-1] / baslangic_sermaye - 1.0

    gercek_egri = np.concatenate([[baslangic_sermaye], baslangic_sermaye * np.cumprod(1.0 + oranlar)])
    gercek_dd = drawdown(gercek_egri).azami

    return MonteCarloSonucu(
        deneme=deneme,
        islem_sayisi=len(kapali),
        gercek_max_drawdown=gercek_dd,
        gercek_getiri=float(gercek_egri[-1] / baslangic_sermaye - 1.0),
        drawdown_dagilimi={f"p{p:02d}": float(np.percentile(dususler, p)) for p in PERSENTILLER},
        getiri_dagilimi={f"p{p:02d}": float(np.percentile(getiriler, p)) for p in PERSENTILLER},
        kotu_kuyruk_orani=float((dususler > gercek_dd).mean()),
        seed=seed,
    )


#: Stres senaryoları: maliyet modeline uygulanan çarpanlar. (§15.1 "yüksek slippage")
#:
#: 2× ve 3× keyfi değil — K-021'in kalibrasyonu p75 persentilini seçmişti; ölçülen
#: dağılımda p95 medyanın ~5 katı, p99 ~9 katı. 2× ve 3× o kuyruğun içinde kalıyor, yani
#: "olabilir" senaryolar, "imkânsız" senaryolar değil.
STRES_SENARYOLARI: Final[dict[str, dict[str, float]]] = {
    "temel": {"slippage": 1.0, "fee": 1.0},
    "slippage_2x": {"slippage": 2.0, "fee": 1.0},
    "slippage_3x": {"slippage": 3.0, "fee": 1.0},
    "fee_2x": {"slippage": 1.0, "fee": 2.0},
    "hepsi_2x": {"slippage": 2.0, "fee": 2.0},
}


@dataclass(frozen=True, slots=True)
class StresSonucu:
    """Bir stratejinin maliyet varsayımlarına dayanıklılığı."""

    strateji_adi: str
    senaryolar: dict[str, dict[str, Any]]

    @property
    def dayanikli(self) -> bool:
        """Her senaryoda toplam getiri pozitif mi.

        Bu, güçlü bir eşik ve bugünkü hiçbir strateji bunu geçmiyor. Öyle olması gerekiyor:
        stres testinin işi güven vermek değil, kırılganlığı görünür kılmak.
        """
        return all(s["toplam_getiri"] > 0.0 for s in self.senaryolar.values())

    def bozulma(self) -> float:
        """Temel senaryodan en kötü senaryoya getiri farkı (yüzde puan)."""
        if "temel" not in self.senaryolar:
            return 0.0
        temel = self.senaryolar["temel"]["toplam_getiri"]
        en_kotu = min(s["toplam_getiri"] for s in self.senaryolar.values())
        return temel - en_kotu

    def sozluk(self) -> dict[str, Any]:
        return {
            "strateji": self.strateji_adi,
            "dayanikli": self.dayanikli,
            "bozulma": self.bozulma(),
            "senaryolar": self.senaryolar,
        }


def stres(
    strateji: Strateji,
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    pencere: Pencere,
    *,
    baslangic_sermaye: float = 10_000.0,
    senaryolar: Mapping[str, Mapping[str, float]] = STRES_SENARYOLARI,
) -> StresSonucu:
    """Aynı stratejiyi bozulmuş maliyet varsayımlarıyla koşturur.

    Kalibre edilmiş maliyet bir **tahmindir** (K-021). "Tam bu sayılarla kârlı" olan bir
    strateji ile "sayılar iki katına çıksa da ayakta" olan strateji aynı şey değil, ve
    promotion kararını veren ikincisi olmalı.
    """
    dilim = {ad: dizi[pencere.dilim()] for ad, dizi in bar_dizileri.items()}
    out: dict[str, dict[str, Any]] = {}

    for ad, carpanlar in senaryolar.items():
        bozuk = MaliyetModeli(
            fee_taker_bps=maliyet.fee_taker_bps * carpanlar["fee"],
            slippage_bps=maliyet.slippage_bps * carpanlar["slippage"],
            kalibrasyon=None,  # bozulmuş model kalibre değildir; bayrak da öyle demeli
        )
        sonuc = Backtest(strateji, bozuk, baslangic_sermaye=baslangic_sermaye).calistir(
            sembol, timeframe, dilim, olcum_baslangici=pencere.olcum_baslangici
        )
        m = sonuc.metrikler
        out[ad] = {
            "carpanlar": dict(carpanlar),
            "fee_taker_bps": bozuk.fee_taker_bps,
            "slippage_bps": bozuk.slippage_bps,
            "toplam_getiri": m.toplam_getiri,
            "sharpe": m.sharpe,
            "max_drawdown": m.max_drawdown,
            "islem_sayisi": m.islem_sayisi,
            "profit_factor": m.profit_factor,
            "toplam_maliyet": m.toplam_komisyon + m.toplam_slippage,
        }

    return StresSonucu(
        strateji_adi=getattr(strateji, "ad", type(strateji).__name__), senaryolar=out
    )
