"""Evren dayanıklılığı: sonuç kaç enstrümana bağlı? (K-054, Faz 11)

K-054'ün cümlesi: *"Sonuç kaç enstrümana bağlı; en iyi k enstrüman çıkarıldığında geriye
ne kalıyor."* Yakalamaya çalıştığı hata şu: 40 enstrümanlı bir portföyün getirisinin
tamamı iki isimden geliyorsa, o sonuç bir **portföy stratejisi** değil, iki şanslı bahsin
etrafına sarılmış 38 enstrümanlık gürültüdür. Cross-sectional bir ailenin iddiası
"kuralım evrende çalışıyor"dur; tek bir ismi çıkarınca çöküyorsa iddia yanlıştır.

## Neden yeniden koşuluyor, atıf yapılmıyor

En kolay yol o enstrümanın işlemlerinin P&L'ini toplamdan çıkarmak olurdu. Yanlış olurdu:
o enstrüman evrende olmasaydı **sermaye başka yere giderdi.** Çıkarma, serbest kalan
sermayenin nakitte beklediğini varsayar ve portföyün gerçekte ne yapacağını ölçmez.

Bu yüzden ölçüm bir **yeniden koşudur**: enstrüman evren üyeliğinden düşürülür ve strateji
baştan koşar. Pahalı (k+1 koşu) ve öyle olmalı — K-019'un *"promotion kararı ucuz olması
gereken bir şey değil"* kalıbı.

## Tek sembolde ölçülemez ve bu bilinçli

K-054: *"`evren_dayanikliligi` tek bir sembolde **ölçülemez** — yani tek sembolde
geliştirilen bir strateji de artık evrene karşı sınanmak zorunda."* Ölçülemeyen kapı
geçilmiş sayılmaz (K-019), dolayısıyla tek sembollü bir sonuç bu kapıda durur. K-045 tek
sembollü yönlü aramayı zaten kapatmıştı; bu kapı o kararın promotion tarafındaki karşılığı.

## Ölçü: kapı **oranı** okur, düşüş raporlanır

    evren_dayaniklilik_orani = azaltılmış_sharpe / tam_sharpe      (tam_sharpe > 0 iken)
    evren_dayaniklilik_dususu = tam_sharpe − azaltılmış_sharpe     (her zaman)

İlk yazımda kapı **mutlak düşüşü** okuyordu ve kalibrasyon onu çürüttü: düşüş, Sharpe'ın
büyüklüğüyle ölçekleniyor. Kıyas portföyünde (Sharpe ≈ −0,5) en yoğun kurulumda bile
düşüş 0,035 çıktı; aynı yoğunluktaki Sharpe 1,5'lik bir strateji çok daha büyük bir
mutlak düşüş üretirdi ve aynı eşik ikisine farklı davranırdı. Oran ölçekten bağımsız:
"performansın ne kadarı tek bir isim çıkınca hayatta kalıyor".

**Oran `tam_sharpe ≤ 0` iken tanımsız** ve o hâlde kapı **ölçülemez** (`None`). Bu bir
kaçamak değil: negatif Sharpe'lı bir sonucun "dayanıklılığı" diye bir şey yok, ve o sonuç
zaten `oos_sharpe` kapısında durmuş oluyor. Ölçülemeyen kapı geçilmiş sayılmaz (K-019).

Düşüş yine de raporlanıyor: oranın paydası küçükken (Sharpe 0,05 gibi) oran gürültülü
olur ve iki sayı birlikte okunmalı.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from scryne_quant.backtest.sonuc import Sonuc


class DayaniklilikHatasi(ValueError):
    """Evren dayanıklılığı ölçümünün girdisi geçersiz."""


@dataclass(frozen=True, slots=True)
class DayaniklilikOlcumu:
    """Leave-k-out sonucu."""

    oran: float | None
    """`azaltılmış / tam` Sharpe oranı — **kapının okuduğu sayı**. `None` = ölçülemedi
    (tek enstrüman, katkı yok, ya da `tam_sharpe ≤ 0`)."""

    dusus: float | None
    """`tam − azaltılmış` Sharpe farkı. Ölçekten bağımsız değil; oranla birlikte okunur."""

    k: int
    cikarilan: list[str]
    tam_sharpe: float
    azaltilmis_sharpe: float | None
    katkilar: dict[str, float]
    """Sembol → kapanmış turların net P&L toplamı. Hangi ismin çıkarıldığının gerekçesi."""

    def sozluk(self) -> dict[str, Any]:
        return {
            "evren_dayaniklilik_orani": self.oran,
            "evren_dayaniklilik_dususu": self.dusus,
            "k": self.k,
            "cikarilan": self.cikarilan,
            "tam_sharpe": self.tam_sharpe,
            "azaltilmis_sharpe": self.azaltilmis_sharpe,
            "katkilar": dict(sorted(self.katkilar.items())),
        }


def katkilar(sonuc: Sonuc) -> dict[str, float]:
    """Sembol başına net P&L. Yalnızca **kapanmış** turlar sayılıyor.

    Açık turun P&L'i gerçekleşmemiştir ve fiyat hareketiyle değişmeye devam eder; onu
    katkı olarak saymak, henüz olmamış bir kârı bir enstrümana yazmak olurdu.
    """
    cikti: dict[str, float] = {}
    for islem in sonuc.islemler:
        if not islem.kapali or not islem.sembol:
            continue
        cikti[islem.sembol] = cikti.get(islem.sembol, 0.0) + islem.net_pnl
    return cikti


def olc(
    tam: Sonuc,
    yeniden_kos: Callable[[frozenset[str]], Sonuc],
    *,
    k: int = 1,
) -> DayaniklilikOlcumu:
    """En iyi `k` katkıyı evrenden düşürüp yeniden koşturur.

    `yeniden_kos(cikarilanlar)` verilen sembolleri evren üyeliğinden **düşürerek** aynı
    stratejiyi aynı pencerede koşturmalı. Çağıranın vermesi bilinçli: bu modülün depo,
    tablo veya CLI bilgisi yok (K-003'ün kalıbı).
    """
    if k < 1:
        raise DayaniklilikHatasi(f"k ≥ 1 olmalı: {k}")
    if tam.evren is None:
        # Tek sembollü koşu: çıkarılacak ikinci enstrüman yok.
        return DayaniklilikOlcumu(None, None, k, [], tam.metrikler.sharpe, None, {})

    katki = katkilar(tam)
    if len(katki) <= k:
        # Çıkarınca geriye enstrüman kalmıyor ya da hiç kapanmış tur yok: ölçülemez.
        return DayaniklilikOlcumu(None, None, k, [], tam.metrikler.sharpe, None, katki)

    # En yüksek katkı önce; eşitlikte sembol adı — determinizm (K-009).
    sirali = sorted(katki, key=lambda s: (-katki[s], s))
    cikarilan = sirali[:k]
    azaltilmis = yeniden_kos(frozenset(cikarilan))
    tam_sharpe = tam.metrikler.sharpe
    return DayaniklilikOlcumu(
        # Oran yalnızca pozitif Sharpe'ta tanımlı — bkz. modül başlığı.
        oran=(azaltilmis.metrikler.sharpe / tam_sharpe) if tam_sharpe > 0.0 else None,
        dusus=tam_sharpe - azaltilmis.metrikler.sharpe,
        k=k,
        cikarilan=cikarilan,
        tam_sharpe=tam.metrikler.sharpe,
        azaltilmis_sharpe=azaltilmis.metrikler.sharpe,
        katkilar=katki,
    )


def uyeligi_dusur(uyelik: dict[str, Any], cikarilanlar: Iterable[str]) -> dict[str, Any]:
    """Verilen sembollerin üyelik maskesini tamamen `False` yapar (kopya döner).

    Sembolü görünümden **silmek** yerine üyeliğini düşürmek bilinçli: silmek ortak
    ızgarayı ve dolayısıyla bar indekslerini değiştirebilirdi; üyeliği düşürmek yalnızca
    o enstrümanın seçilebilirliğini kaldırır ve karşılaştırma aynı pencerede kalır.
    """
    import numpy as np

    cikar = set(cikarilanlar)
    return {
        s: (np.zeros_like(np.asarray(m, dtype=bool)) if s in cikar else np.asarray(m, dtype=bool))
        for s, m in uyelik.items()
    }


__all__ = [
    "DayaniklilikHatasi",
    "DayaniklilikOlcumu",
    "katkilar",
    "olc",
    "uyeligi_dusur",
]
