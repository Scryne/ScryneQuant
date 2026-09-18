"""Portföy kurma: skorlardan hedef ağırlığa. (§12, K-051/4, Faz 10)

Sinyaller doğrudan emir değildir ve **skorlar doğrudan ağırlık değildir.** Bu modül
aradaki dönüşümü yapıyor: oynaklık ayarlı boyut, korelasyon budaması, konsantrasyon ve
turnover bandı. Girdi bir aday listesi, çıktı bir `HedefPortfoy`.

## Neden `strategy/` altında

Portföy kurma saf hesap: I/O yok, gelecek yok. `strategy/` altında olması onu K-003'ün
izolasyon testinin kapsamına sokuyor — `portfolio/` altında olsaydı o testi genişletmek
ya da kapsam dışı bırakmak gerekirdi. İkincisi, kurma katmanının bir gün "şu sembolün
likiditesini veritabanından çek" demesinin önünü açardı.

## Bu katman izin veremez (K-037)

Kurma bir **öneri** üretir; onay yalnızca risk motorundan çıkar. Buradaki `azami_agirlik`
ve `hedef_brut` risk limitlerinin kopyası değil, stratejinin kendi iştahı — ve ikisi
çeliştiğinde risk motoru kazanır, çünkü o aşağı çeker. Buradaki bir sayıyı gevşetmek
canlıda hiçbir kapıyı açmaz.

## Yöntem bir çekiliştir (K-051/4)

`KurmaAyarlari`nın her alanı `yontem_kimligi`ne giriyor ve hipotez kaydının parçası.
"Eşit ağırlık yerine oynaklık ayarlı deneyelim" cümlesi, aynı veriye sorulan **yeni bir
soru**dur; deftere yazılmadan koşturulması K-039'un yasakladığı şey.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from scryne_quant.strategy.hedef import HedefPortfoy, hedef_kur
from scryne_quant.strategy.sinyal import NEDEN_DESENI, Sinyal, Yon

#: Ağırlıkların sıfır sayıldığı eşik. Bunun altındaki bir hedef komisyon ödeyip toz pozisyon
#: almak demek; `fill.ASGARI_ORAN` kayan nokta artığını sıfır sayıyor, bu ise **ekonomik
#: olarak anlamsızı** sıfır sayıyor. İkisi farklı sorular, farklı mertebeler.
VARSAYILAN_ASGARI_AGIRLIK: Final = 0.005


class KurmaHatasi(ValueError):
    """Portföy kurma girdisi veya ayarı geçersiz."""


@dataclass(frozen=True, slots=True)
class Aday:
    """Kurma katmanına giren tek enstrüman. Strateji doldurur, kurma yorumlar."""

    sembol: str
    skor: float
    """Stratejinin sıralama ölçüsü. Büyük = tercih edilir. Ölçeği stratejiye ait; kurma
    yalnızca **sırayı** kullanır, mutlak büyüklüğü değil — iki farklı ailenin skorlarını
    aynı ölçekte varsaymak, ikisini gizlice karşılaştırmak olurdu."""

    oynaklik: float
    """Boyutlandırmanın paydası (örn. ATR/fiyat). Pozitif olmak zorunda: sıfır oynaklık
    sonsuz pozisyon demektir ve bu bir hata, bir fırsat değil."""

    mevcut_agirlik: float = 0.0
    """Portföyün şu anda bu enstrümandaki kesri. Turnover bandı buna bakar."""

    reason: str = "PORTFOY_KURMA"
    confidence: float = 0.5

    def __post_init__(self) -> None:
        if not NEDEN_DESENI.fullmatch(self.reason):
            raise KurmaHatasi(f"reason bir kod olmalı: {self.reason!r}")
        if self.oynaklik <= 0.0 or not np.isfinite(self.oynaklik):
            raise KurmaHatasi(
                f"{self.sembol}: oynaklık pozitif ve sonlu olmalı, verilen {self.oynaklik}. "
                "Ölçülemeyen oynaklıkla boyut hesaplanmaz (risk motorunun volatilite "
                "guard'ıyla aynı kural)"
            )
        if not np.isfinite(self.skor):
            raise KurmaHatasi(f"{self.sembol}: skor sonlu olmalı")


@dataclass(frozen=True, slots=True)
class KurmaAyarlari:
    """Kurma yönteminin tamamı. Her alan yöntem kimliğine girer (K-051/4)."""

    yontem: str = "OYNAKLIK_AYARLI"
    """`HedefPortfoy.yontem`e yazılan kod."""

    azami_enstruman: int = 10
    """Aynı anda kaç enstrüman taşınacağı. Konsantrasyonun birinci kolu."""

    hedef_brut: float = 1.0
    """Nakit dışı toplam hedef. `< 1` ise fark **aktif bir nakit pozisyonudur** (§12):
    "yatırılmamış bakiye" değil, bilinçli bir risk kararı."""

    azami_agirlik: float = 0.30
    """Tek enstrümanın tavanı. Risk motorunun `azami_maruziyet`inin kopyası değil,
    stratejinin kendi iştahı; ikisinden **düşük olanı** bağlar."""

    asgari_agirlik: float = VARSAYILAN_ASGARI_AGIRLIK

    esit_agirlik: bool = False
    """`True` ise oynaklık yok sayılır ve seçilenler eşit bölüşür. Kıyas için var:
    oynaklık ayarlamanın bir şey **kattığını** göstermenin tek yolu, katmadığı hâlle
    yan yana koymak (K-030'un al-tut kıyasıyla aynı disiplin)."""

    korelasyon_tavani: float | None = None
    """Verilirse: bu eşiği aşan korelasyonda, **düşük skorlu** aday elenir. Aynı ekonomik
    riskin iki kez alınmasını engeller (§12). `None` = budama yok, ve bu bilinçli bir
    varsayılan: korelasyon matrisi yoksa uydurulmaz."""

    turnover_bandi: float = 0.0
    """Hedef ile mevcut ağırlık farkı bu bandın altındaysa **mevcut korunur**.

    §12'nin *cost-aware turnover penalty*'sinin bu projedeki hâli. Ceza katsayısı yerine
    bant seçildi çünkü bandın birimi ağırlık ve sayısı doğrudan maliyet modelinden
    türetilebilir: gidiş-dönüş maliyeti (2×(fee+slippage)) kadar iyileşme getirmeyen bir
    yeniden dengeleme, tanımı gereği zarar. Ceza katsayısı ise skor ölçeğine bağlı olurdu —
    ve skor ölçeği stratejiden stratejiye değişiyor.

    Varsayılan 0: Faz 10 yöntemi **kurar**, sayıyı ölçmez. Bağlayıcı bir bant Faz 12'de,
    turnover'ın gerçek maliyeti ölçüldüğünde yazılır.
    """

    def __post_init__(self) -> None:
        if not NEDEN_DESENI.fullmatch(self.yontem):
            raise KurmaHatasi(f"yontem bir kod olmalı: {self.yontem!r}")
        if self.azami_enstruman < 1:
            raise KurmaHatasi("azami_enstruman ≥ 1 olmalı")
        if not 0.0 < self.hedef_brut <= 1.0:
            raise KurmaHatasi("hedef_brut (0, 1] aralığında olmalı (kaldıraç yok)")
        if not 0.0 < self.azami_agirlik <= 1.0:
            raise KurmaHatasi("azami_agirlik (0, 1] aralığında olmalı")
        if self.asgari_agirlik < 0.0 or self.asgari_agirlik >= self.azami_agirlik:
            raise KurmaHatasi("asgari_agirlik, azami_agirlik'in altında olmalı")
        if self.korelasyon_tavani is not None and not 0.0 < self.korelasyon_tavani <= 1.0:
            raise KurmaHatasi("korelasyon_tavani (0, 1] aralığında olmalı")
        if self.turnover_bandi < 0.0:
            raise KurmaHatasi("turnover_bandi negatif olamaz")

    def sozluk(self) -> dict[str, Any]:
        return {
            "yontem": self.yontem,
            "azami_enstruman": self.azami_enstruman,
            "hedef_brut": self.hedef_brut,
            "azami_agirlik": self.azami_agirlik,
            "asgari_agirlik": self.asgari_agirlik,
            "esit_agirlik": self.esit_agirlik,
            "korelasyon_tavani": self.korelasyon_tavani,
            "turnover_bandi": self.turnover_bandi,
        }


def sec(
    adaylar: Sequence[Aday],
    ayarlar: KurmaAyarlari,
    korelasyon: Mapping[tuple[str, str], float] | None = None,
) -> list[Aday]:
    """Adayları skora göre sıralar, korelasyonu budar, ilk N'i seçer.

    Sıralama `(-skor, sembol)`: eşit skorda sembol adı bozar. Rastgele bozmak, aynı
    girdinin iki koşuda farklı portföy üretmesi demek olurdu (K-009).

    Budama **açgözlü ve sıralı**: en yüksek skorlu tutulur, ona fazla benzeyen elenir.
    Bu, "en iyi k'lı alt kümeyi bul" probleminin optimali değil; optimali kombinatoryal ve
    aynı veriye daha çok soru sormak demek. Açgözlü kural tek ve açık bir kural.
    """
    sirali = sorted(adaylar, key=lambda a: (-a.skor, a.sembol))
    secilen: list[Aday] = []
    for aday in sirali:
        if len(secilen) >= ayarlar.azami_enstruman:
            break
        if ayarlar.korelasyon_tavani is not None and korelasyon is not None:
            fazla_benzer = any(
                abs(_korelasyon(korelasyon, aday.sembol, s.sembol)) > ayarlar.korelasyon_tavani
                for s in secilen
            )
            if fazla_benzer:
                continue
        secilen.append(aday)
    return secilen


def _korelasyon(matris: Mapping[tuple[str, str], float], a: str, b: str) -> float:
    """Simetrik okuma; eksik çift **0 değil** kabul edilmez — ölçülmemiş korelasyon sıfır
    değildir. Eksikse budama yapılamaz, o yüzden 1.0 (en muhafazakâr) döner: ölçülemeyen
    guard geçilmiş sayılmaz (K-019'un cümlesi, kurma katmanındaki hâli)."""
    if (a, b) in matris:
        return matris[(a, b)]
    if (b, a) in matris:
        return matris[(b, a)]
    return 1.0


def agirliklar(secilen: Sequence[Aday], ayarlar: KurmaAyarlari) -> dict[str, float]:
    """Seçilen adaylara ağırlık dağıtır: oynaklık ayarlı (veya eşit), tavanlı, brüte ölçekli.

    Oynaklık ayarlı dağıtım `w_i ∝ 1/σ_i`: her pozisyonun portföye kattığı risk yaklaşık
    eşit olur. "Yaklaşık", çünkü gerçek risk katkısı korelasyona da bağlı ve bu formül onu
    yok sayıyor — korelasyon bu yöntemde **budama** aşamasında ele alınıyor, ağırlıkta
    değil. Tam risk paritesi bir optimizasyon; optimizasyon aynı veriye daha çok soru
    sormaktır ve bir çekiliş olarak ayrıca kaydedilmelidir.

    Tavan uygulandıktan sonra artan bütçe kalan enstrümanlara **yeniden dağıtılır**, ama
    hiçbiri tavanı aşamaz; dağıtılamayan kısım nakitte kalır. Zorla dağıtmak, tavanı
    tavan olmaktan çıkarırdı.
    """
    if not secilen:
        return {}

    if ayarlar.esit_agirlik:
        ham = np.ones(len(secilen), dtype=np.float64)
    else:
        ham = np.array([1.0 / a.oynaklik for a in secilen], dtype=np.float64)
    pay = ham / ham.sum()

    w = pay * ayarlar.hedef_brut
    tavan = ayarlar.azami_agirlik
    # Tavanı aşanları kırp, artanı **kırpılmamış** olanlara payları oranında dağıt. Bir kez
    # tavana oturan enstrüman `kilitli`ye girer ve bir daha pay almaz. Kilit olmadan bu
    # döngü yakınsamıyordu: kırpılan enstrüman `w == tavan` olduğu için sonraki turda
    # `w > tavan` testine takılmıyor, "serbest" sayılıyor ve yeniden pay alıp tavanı
    # aşıyordu — yani tavan bir tavan değil, salınan bir sayı oluyordu (3 adaylı bir vakada
    # tavanın iki katına çıktığı ölçüldü). Kilitle sabit nokta garanti: her tur en az bir
    # enstrüman kilitlenir, yani en fazla len(secilen) tur.
    kilitli = np.zeros(len(secilen), dtype=bool)
    for _ in range(len(secilen)):
        asan = (w > tavan) & ~kilitli
        if not asan.any():
            break
        artan = float((w[asan] - tavan).sum())
        w = np.where(asan, tavan, w)
        kilitli |= asan
        serbest = ~kilitli & (w > 0.0)
        if not serbest.any():
            break
        w = np.where(serbest, w + artan * (w / w[serbest].sum()), w)

    sonuc = {a.sembol: float(x) for a, x in zip(secilen, w, strict=True)}
    return {s: (x if x >= ayarlar.asgari_agirlik else 0.0) for s, x in sonuc.items()}


def turnover_uygula(
    hedefler: Mapping[str, float], adaylar: Mapping[str, Aday], bant: float
) -> dict[str, float]:
    """Bandın altındaki değişiklikleri **yapmaz**: mevcut ağırlık korunur.

    Bandın simetrik olması bilinçli: küçük bir artışı da küçük bir azalışı da engelliyor.
    Yalnızca artışı engelleyen bir bant, portföyü zamanla tek yöne sürüklerdi.
    """
    if bant <= 0.0:
        return dict(hedefler)
    return {
        s: (adaylar[s].mevcut_agirlik if abs(h - adaylar[s].mevcut_agirlik) < bant else h)
        for s, h in hedefler.items()
    }


def kur(
    zaman: int,
    adaylar: Sequence[Aday],
    ayarlar: KurmaAyarlari,
    *,
    korelasyon: Mapping[tuple[str, str], float] | None = None,
    acik_pozisyonlar: Sequence[str] = (),
) -> HedefPortfoy:
    """Adaylardan hedef portföy üretir. Kurma zincirinin tek girişi.

    `acik_pozisyonlar`: seçilmeyen ama **elde olan** enstrümanlar. Onlar için `FLAT`
    üretilir — çünkü "bahsedilmeyen sembol kapat demek değildir" (`hedef.py`) ve kurma
    katmanı bir portföyün **tamamını** söylediğini iddia ediyor. Bu iddiayı açıkça
    `FLAT` yazarak yapmak, sessizliğe yorum yüklemekten güvenli.
    """
    tekil = {a.sembol: a for a in adaylar}
    if len(tekil) != len(adaylar):
        raise KurmaHatasi("aynı sembol için iki aday")

    secilen = sec(adaylar, ayarlar, korelasyon)
    hedefler = turnover_uygula(agirliklar(secilen, ayarlar), tekil, ayarlar.turnover_bandi)

    sinyaller: list[Sinyal] = []
    for sembol, agirlik in hedefler.items():
        aday = tekil[sembol]
        if agirlik <= 0.0:
            if sembol in acik_pozisyonlar:
                sinyaller.append(_flat(sembol, zaman, aday.reason))
            continue
        sinyaller.append(
            Sinyal(
                symbol=sembol,
                side=Yon.BUY,
                target_exposure=agirlik,
                confidence=aday.confidence,
                reason=aday.reason,
                timestamp=zaman,
            )
        )

    secilen_adlar = set(hedefler)
    for sembol in acik_pozisyonlar:
        if sembol not in secilen_adlar:
            sinyaller.append(_flat(sembol, zaman, "PORTFOY_KURMA_ELEDI"))

    return hedef_kur(zaman, sinyaller, yontem=ayarlar.yontem)


def _flat(sembol: str, zaman: int, reason: str) -> Sinyal:
    return Sinyal(
        symbol=sembol,
        side=Yon.FLAT,
        target_exposure=0.0,
        confidence=0.0,
        reason=reason,
        timestamp=zaman,
    )


__all__ = [
    "VARSAYILAN_ASGARI_AGIRLIK",
    "Aday",
    "KurmaAyarlari",
    "KurmaHatasi",
    "agirliklar",
    "kur",
    "sec",
    "turnover_uygula",
]
