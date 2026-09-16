"""Parametre pertürbasyonu: seçilen nokta bir plato mu, yoksa yalnız bir zirve mi?

K-054'ün cümlesi net: *"Mevcut `parametre_kararliligi` **başka bir şey** ölçüyor:
katmanlar arası seçim değişkenliği."* Yani `wf_kararsizlik` "her katmanda başka parametre
mi seçiliyor" diye sorar; bu modül **tek bir taramanın içinde**, seçilen noktanın hemen
yanındaki parametrelerin ne yaptığını sorar.

İkisi farklı hata sınıflarını yakalar:

- `parametre_kararliligi` yüksekse: prosedür kararsız, canlıda hangi parametreyle
  çalıştırılacağı belirsiz.
- `parametre_perturbasyonu` yüksekse: seçilen nokta **izole bir zirve**. Komşuları çok
  daha kötüyse o zirve bir keşif değil, gürültünün en şanslı hücresidir — ve gürültü
  out-of-sample'da aynı hücrede tekrar etmez.

Bir strateji ikisini birden geçebilir ve yine de kötü olabilir; ikisinden birinde kalırsa
o strateji **hangi parametreyle** çalıştırılacağı sorusuna güvenilir cevap veremiyor
demektir.

## Ölçü

    perturbasyon_dusus = (seçilen.skor − komşuların medyanı) / (geçerli skorların aralığı)

Payda **aralık** (max − min), skorun kendisi değil. Skora bölmek negatif Sharpe'ta işareti
çevirir ve ölçüyü okunamaz yapar; aralığa bölmek ölçüyü ızgaranın kendi skalasında tutar
ve stratejiler arası karşılaştırılabilir kılar.

Medyan, ortalama değil: tek bir çok kötü komşu (ızgaranın anlamsız köşesi) ortalamayı
aşağı çeker ve her seçimi zirve gibi gösterirdi.

## Komşu tanımı

**Izgarada tam bir eksende bir adım.** İki eksende birden oynayan bir nokta komşu
sayılmaz: iki değişkeni aynı anda değiştirmek, hangisinin bozulmayı ürettiğini
bilinemez kılar (Faz 4'e dönüş 3'ün `funding_filtre` ızgarasını daraltma gerekçesiyle
aynı disiplin).

Tek noktalı eksenler (örn. sabit `maruziyet`) komşuluk üretmez ve payda dışında kalır;
o eksende adım yok.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from scryne_quant.research.tarama import Aday, TaramaSonucu


class PerturbasyonHatasi(ValueError):
    """Pertürbasyon ölçümünün girdisi geçersiz."""


@dataclass(frozen=True, slots=True)
class PerturbasyonOlcumu:
    """Seçilen noktanın komşularına göre durumu."""

    dusus: float | None
    """`(seçilen − komşu medyanı) / aralık`. `None` = komşu yok, ölçülemedi."""

    komsu_sayisi: int
    secilen_skor: float
    komsu_medyan: float | None
    skor_araligi: float
    eksenler: list[str]
    """Komşuluk üretebilen (birden fazla değer taşıyan) parametre eksenleri."""

    def sozluk(self) -> dict[str, Any]:
        return {
            "perturbasyon_dusus": self.dusus,
            "komsu_sayisi": self.komsu_sayisi,
            "secilen_skor": self.secilen_skor,
            "komsu_medyan": self.komsu_medyan,
            "skor_araligi": self.skor_araligi,
            "eksenler": self.eksenler,
        }


def _eksen_degerleri(adaylar: Sequence[Aday]) -> dict[str, list[Any]]:
    """Eksen adı → o eksenin ızgaradaki sıralı değerleri."""
    eksenler: dict[str, set[Any]] = {}
    for a in adaylar:
        for ad, deger in a.sozluk_parametreler.items():
            eksenler.setdefault(ad, set()).add(deger)
    return {ad: sorted(degerler) for ad, degerler in sorted(eksenler.items())}


def komsular(secilen: Aday, adaylar: Sequence[Aday]) -> list[Aday]:
    """Izgarada tam bir eksende bir adım uzaktaki adaylar.

    Adaylar listesi taramanın **geçerli** adayları olmalı: geçersiz (az işlemli) bir
    komşuyu hesaba katmak, "komşu kötü" ile "komşu ölçülemedi"yi karıştırırdı.
    """
    if not adaylar:
        return []
    eksenler = _eksen_degerleri(adaylar)
    hedef = secilen.sozluk_parametreler
    cikti: list[Aday] = []
    for aday in adaylar:
        p = aday.sozluk_parametreler
        if p == hedef:
            continue
        farklar = [ad for ad in eksenler if p.get(ad) != hedef.get(ad)]
        if len(farklar) != 1:
            continue
        ad = farklar[0]
        degerler = eksenler[ad]
        try:
            i, j = degerler.index(hedef[ad]), degerler.index(p[ad])
        except (KeyError, ValueError):  # pragma: no cover - ızgara dışı değer
            continue
        if abs(i - j) == 1:
            cikti.append(aday)
    return cikti


def dusus_hesapla(
    parametreler: Sequence[dict[str, Any]],
    skorlar: np.ndarray,
    secilen: int,
) -> float | None:
    """Ölçünün çekirdeği: `Aday` nesnesi olmadan, ham parametre+skor üzerinde.

    Ayrı durmasının sebebi null kalibrasyonu: `research/kalibrasyon_v2.py` kaydırılmış
    takvimleri koşturup elinde yalnızca parametre listesi ve skor dizisi tutuyor;
    o listeden `TaramaSonucu` kurmak, ölçüm aleti uğruna araştırma tipini taklit etmek
    olurdu.
    """
    skorlar = np.asarray(skorlar, dtype=np.float64)
    if len(parametreler) != skorlar.size:
        raise PerturbasyonHatasi(
            f"parametre sayısı {len(parametreler)}, skor {skorlar.size} — aynı olmalı"
        )
    if not 0 <= secilen < skorlar.size:
        raise PerturbasyonHatasi(f"seçilen indeks aralık dışı: {secilen}")

    eksenler: dict[str, list[Any]] = {
        ad: sorted({p[ad] for p in parametreler})
        for ad in sorted({a for p in parametreler for a in p})
    }
    hedef = parametreler[secilen]
    komsu_skorlari = [
        float(skorlar[i])
        for i, p in enumerate(parametreler)
        if i != secilen and _bir_adim_mi(p, hedef, eksenler)
    ]
    aralik = float(skorlar.max() - skorlar.min())
    if not komsu_skorlari or aralik <= 0.0:
        return None
    return (float(skorlar[secilen]) - float(np.median(komsu_skorlari))) / aralik


def _bir_adim_mi(
    aday: dict[str, Any], hedef: dict[str, Any], eksenler: dict[str, list[Any]]
) -> bool:
    farklar = [ad for ad in eksenler if aday.get(ad) != hedef.get(ad)]
    if len(farklar) != 1:
        return False
    ad = farklar[0]
    degerler = eksenler[ad]
    try:
        return abs(degerler.index(hedef[ad]) - degerler.index(aday[ad])) == 1
    except (KeyError, ValueError):  # pragma: no cover - ızgara dışı değer
        return False


def olc(tarama: TaramaSonucu, secilen: Aday) -> PerturbasyonOlcumu:
    """Seçilen adayın pertürbasyon düşüşü."""
    gecerli = tarama.gecerliler
    if not gecerli:
        raise PerturbasyonHatasi("geçerli aday yok: pertürbasyon ölçülemez")

    skorlar = np.array([a.skor for a in gecerli], dtype=np.float64)
    aralik = float(skorlar.max() - skorlar.min())
    eksenler = [ad for ad, d in _eksen_degerleri(gecerli).items() if len(d) > 1]
    komsu = komsular(secilen, gecerli)

    if not komsu or aralik <= 0.0:
        # Aralık sıfırsa bütün ızgara aynı skoru veriyor — seçim diye bir şey yok ve
        # "düşüş" tanımsız. Sıfır dönmek onu "kusursuz plato" diye raporlamak olurdu.
        return PerturbasyonOlcumu(
            dusus=None,
            komsu_sayisi=len(komsu),
            secilen_skor=secilen.skor,
            komsu_medyan=float(np.median([a.skor for a in komsu])) if komsu else None,
            skor_araligi=aralik,
            eksenler=eksenler,
        )

    medyan = float(np.median([a.skor for a in komsu]))
    return PerturbasyonOlcumu(
        dusus=(secilen.skor - medyan) / aralik,
        komsu_sayisi=len(komsu),
        secilen_skor=secilen.skor,
        komsu_medyan=medyan,
        skor_araligi=aralik,
        eksenler=eksenler,
    )


__all__ = [
    "PerturbasyonHatasi",
    "PerturbasyonOlcumu",
    "dusus_hesapla",
    "komsular",
    "olc",
]
