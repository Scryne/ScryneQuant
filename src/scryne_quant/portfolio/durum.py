"""Portföy durumu: nakit, pozisyon(lar), ortalama maliyet. (Faz 3, Faz 10)

Kapsam v1 (Final-Doküman): **spot, açığa satış ve kaldıraç yok.** Bunun iki somut sonucu
var ve ikisi de burada zorlanıyor: `nakit` ve `miktar` asla negatif olamaz. Bu, bir tercih
değil — açığa satış yasağının kod karşılığı. İhlali sessiz bir "borçlanma" olurdu ve
backtest karşılığı olmayan bir sermayeyle işlem yapardı.

Ortalama maliyet neden burada: gerçekleşen kâr/zarar (`realized P&L`) ancak bir çıkış
fiyatı bir giriş fiyatıyla karşılaştırılınca anlam kazanır. Kısmi alımlarda "hangi giriş"
sorusunun cevabı FIFO, LIFO veya ortalama maliyet olabilir; **ortalama maliyet** seçildi:
spot ve uzun-yönlü bir portföyde üçü de aynı toplam P&L'i verir, ama ortalama maliyet tek
bir sayı tutar — parti listesi tutmaya göre hem daha az durum hem daha az sessiz hata
yüzeyi.

**Faz 10'un değişikliği: aritmetik `Pozisyon`a indi.** (K-057, K-001) Tek sembollü
`Portfoy` ile çok sembollü `CokluPortfoy` aynı `Pozisyon.al`/`Pozisyon.sat`ı çağırıyor —
iki ayrı defter değil, bir defterin iki sarmalayıcısı. İkiye ayrılsaydı ortalama maliyet,
kapanış tanımı ve tolerans üç sessiz yerde ayrışabilirdi; üçü de sonucu "biraz farklı"
yapar, çökme üretmez.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from scryne_quant.strategy.baglam import PozisyonDurumu

#: Kayan nokta karşılaştırma payı. Mutlak değil bağıl kullanılıyor: 10.000 USDT'lik bir
#: portföyde 1e-12 mutlak eşik, 1.000.000 USDT'likte anlamsız olurdu.
_TOLERANS = 1e-9


class PortfoyHatasi(ValueError):
    """Portföy değişmezi ihlal edildi (negatif nakit, negatif miktar, geçersiz fiyat)."""


@dataclass(frozen=True, slots=True)
class Pozisyon:
    """Tek bir enstrümandaki pozisyon. Nakit **burada değil** — nakit portföyün ortak kaynağı.

    Ayrımın sebebi çok enstrümanlı portföy: on sembolün her birinin kendi nakdi olsaydı
    sermaye tahsisi pozisyonların içinde gizlenirdi. Nakit tek bir havuzdur ve kim ne kadar
    aldıysa oradan düşülür; `al`/`sat` bu yüzden nakit **deltası** döndürüyor, nakdin
    kendisini değil.
    """

    miktar: float = 0.0
    """Baz varlık. Negatif olamaz — açığa satış yok."""

    ortalama_maliyet: float = 0.0
    """Elde tutulan miktarın komisyon **dahil** ortalama birim maliyeti. Pozisyon yoksa 0.

    Komisyon dahil olması bilinçli: "kaça mal oldu" sorusunun dürüst cevabı, ödenen
    komisyonu içerir. Hariç tutmak, her pozisyonu gerçekte olduğundan ucuz gösterirdi.
    """

    giris_ms: int | None = None
    """Pozisyonun **ilk** açıldığı barın zamanı. Tutma süresi metriği buna bakar."""

    def __post_init__(self) -> None:
        if self.miktar < 0.0:
            raise PortfoyHatasi(f"miktar negatif olamaz (açığa satış yok): {self.miktar}")

    @property
    def acik(self) -> bool:
        return self.miktar > 0.0

    def deger(self, fiyat: float) -> float:
        """Pozisyonun verilen fiyattan piyasa değeri."""
        return self.miktar * fiyat

    def al(
        self, miktar: float, fiyat: float, komisyon: float, zaman_ms: int
    ) -> tuple[Pozisyon, float]:
        """Alım uygular. Döner: `(yeni pozisyon, nakitten düşülecek gider)`.

        Nakit yeterliliğini **çağıran** kontrol eder (`_nakit_yeter`): pozisyon nakdin ne
        kadar olduğunu bilmez, bilmemeli.
        """
        if miktar <= 0.0 or fiyat <= 0.0:
            raise PortfoyHatasi(f"geçersiz alım: miktar={miktar}, fiyat={fiyat}")
        gider = miktar * fiyat + komisyon
        yeni_miktar = self.miktar + miktar
        # Komisyon ortalama maliyete giriyor: "kaça mal oldu"nun dürüst cevabı bu.
        yeni_maliyet = (self.ortalama_maliyet * self.miktar + gider) / yeni_miktar
        return (
            Pozisyon(
                miktar=yeni_miktar,
                ortalama_maliyet=yeni_maliyet,
                giris_ms=self.giris_ms if self.acik else zaman_ms,
            ),
            gider,
        )

    def sat(self, miktar: float, fiyat: float, komisyon: float) -> tuple[Pozisyon, float, float]:
        """Satım uygular. Döner: `(yeni pozisyon, nakite eklenecek hasılat, gerçekleşen P&L)`.

        Gerçekleşen P&L = satış hasılatı (komisyon düşülmüş) − satılan miktarın ortalama
        maliyeti (komisyon dahil). Yani hem giriş hem çıkış komisyonu bu sayının içinde.
        """
        if miktar <= 0.0 or fiyat <= 0.0:
            raise PortfoyHatasi(f"geçersiz satım: miktar={miktar}, fiyat={fiyat}")
        if miktar > self.miktar + _TOLERANS * max(self.miktar, 1.0):
            raise PortfoyHatasi(f"elde yok: satılan {miktar}, mevcut {self.miktar}")

        satilan = min(miktar, self.miktar)
        hasilat = satilan * fiyat - komisyon
        maliyet = satilan * self.ortalama_maliyet
        kalan = self.miktar - satilan

        kapandi = kalan <= _TOLERANS * max(self.miktar, 1.0)
        return (
            Pozisyon(
                miktar=0.0 if kapandi else kalan,
                ortalama_maliyet=0.0 if kapandi else self.ortalama_maliyet,
                giris_ms=None if kapandi else self.giris_ms,
            ),
            hasilat,
            hasilat - maliyet,
        )


#: Pozisyonsuz durum. Tek örnek paylaşılıyor — nesne değişmez olduğu için güvenli.
BOS: Pozisyon = Pozisyon()


def _nakit_yeter(gider: float, nakit: float) -> None:
    if gider > nakit + _TOLERANS * max(nakit, 1.0):
        raise PortfoyHatasi(f"yetersiz nakit: gerekli {gider}, mevcut {nakit}")


@dataclass(frozen=True, slots=True)
class Portfoy:
    """Tek sembollü portföy. Değişmez: her işlem **yeni** bir portföy üretir.

    Değişmezlik burada lüks değil: backtest motoru bar bar ilerlerken bir önceki durumu
    kazara paylaşmak, equity eğrisinin geçmişini de değiştirirdi — ve o hata sonuçta
    "biraz farklı bir eğri" olarak görünür, çökme olarak değil.

    Faz 10'dan sonra bu sınıf `CokluPortfoy`un tek enstrümanlı **özel hâli**: aritmetiği
    aynı `Pozisyon`dan alıyor. Alan ve metot adları değişmedi — `live/`, `oms/` ve Faz 3-7
    testleri olduğu gibi çalışıyor.
    """

    nakit: float
    """Quote varlık (USDT). Negatif olamaz — kaldıraç yok."""

    miktar: float = 0.0
    ortalama_maliyet: float = 0.0
    giris_ms: int | None = None

    def __post_init__(self) -> None:
        if self.nakit < 0.0:
            raise PortfoyHatasi(f"nakit negatif olamaz (kaldıraç yok): {self.nakit}")
        if self.miktar < 0.0:
            raise PortfoyHatasi(f"miktar negatif olamaz (açığa satış yok): {self.miktar}")

    # ------------------------------------------------------------------ ölçüm

    @property
    def pozisyon(self) -> Pozisyon:
        return Pozisyon(self.miktar, self.ortalama_maliyet, self.giris_ms)

    @property
    def acik(self) -> bool:
        return self.miktar > 0.0

    def deger(self, fiyat: float) -> float:
        """Pozisyonun verilen fiyattan piyasa değeri."""
        return self.miktar * fiyat

    def ozkaynak(self, fiyat: float) -> float:
        """Nakit + pozisyon değeri. Equity eğrisinin her noktası budur."""
        return self.nakit + self.deger(fiyat)

    def maruziyet(self, fiyat: float) -> float:
        """Portföyün bu sembolde olan kesri [0,1] — `Sinyal.target_exposure` ile aynı ölçek."""
        toplam = self.ozkaynak(fiyat)
        return self.deger(fiyat) / toplam if toplam > 0.0 else 0.0

    def gorunum(self, fiyat: float) -> PozisyonDurumu:
        """Stratejinin `ctx.pozisyon`'da göreceği salt-okunur özet."""
        return PozisyonDurumu(
            miktar=self.miktar,
            ortalama_maliyet=self.ortalama_maliyet,
            exposure=self.maruziyet(fiyat),
            giris_ms=self.giris_ms,
        )

    # ------------------------------------------------------------------ işlem

    def al(self, miktar: float, fiyat: float, komisyon: float, zaman_ms: int) -> Portfoy:
        """Alım uygular. `komisyon` quote biriminde, nakitten ayrıca düşülür."""
        yeni, gider = self.pozisyon.al(miktar, fiyat, komisyon, zaman_ms)
        _nakit_yeter(gider, self.nakit)
        return replace(
            self,
            nakit=max(self.nakit - gider, 0.0),
            miktar=yeni.miktar,
            ortalama_maliyet=yeni.ortalama_maliyet,
            giris_ms=yeni.giris_ms,
        )

    def sat(self, miktar: float, fiyat: float, komisyon: float) -> tuple[Portfoy, float]:
        """Satım uygular. Portföy ve bu satımın **gerçekleşen** kâr/zararını döndürür."""
        yeni, hasilat, gerceklesen = self.pozisyon.sat(miktar, fiyat, komisyon)
        return (
            replace(
                self,
                nakit=self.nakit + hasilat,
                miktar=yeni.miktar,
                ortalama_maliyet=yeni.ortalama_maliyet,
                giris_ms=yeni.giris_ms,
            ),
            gerceklesen,
        )


@dataclass(frozen=True, slots=True)
class CokluPortfoy:
    """Çok enstrümanlı portföy: tek nakit havuzu + sembol başına pozisyon. (Faz 10)

    **Toplamlar sembol adına göre sıralı gezilir.** Kayan nokta toplaması sıraya bağlıdır;
    sözlük ekleme sırasına güvenmek, sembollerin hangi sırada evrene girdiğine bağlı bir
    özkaynak eğrisi üretirdi — yani determinizm (K-009) verinin okunma sırasına bağlanırdı.

    Kapalı pozisyonlar sözlükte **tutulmaz**. Tutulsaydı `sirali_semboller` koşu ilerledikçe
    büyür ve toplama sırası, geçmişte bir kez işlem görmüş her sembolü içerirdi; sonuç
    aynı olurdu ama "şu an hangi pozisyonlar açık" sorusunun cevabı kaybolurdu.
    """

    nakit: float
    pozisyonlar: Mapping[str, Pozisyon] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.nakit < 0.0:
            raise PortfoyHatasi(f"nakit negatif olamaz (kaldıraç yok): {self.nakit}")
        object.__setattr__(
            self,
            "pozisyonlar",
            MappingProxyType({s: p for s, p in sorted(self.pozisyonlar.items()) if p.acik}),
        )

    # ------------------------------------------------------------------ ölçüm

    @property
    def sirali_semboller(self) -> tuple[str, ...]:
        return tuple(self.pozisyonlar)

    @property
    def acik(self) -> bool:
        return bool(self.pozisyonlar)

    def pozisyon(self, sembol: str) -> Pozisyon:
        return self.pozisyonlar.get(sembol, BOS)

    def deger(self, sembol: str, fiyat: float) -> float:
        return self.pozisyon(sembol).deger(fiyat)

    def brut_deger(self, fiyatlar: Mapping[str, float]) -> float:
        """Açık pozisyonların toplam piyasa değeri. Sembol sırasına göre deterministik."""
        return sum(p.deger(fiyatlar[s]) for s, p in self.pozisyonlar.items())

    def ozkaynak(self, fiyatlar: Mapping[str, float]) -> float:
        return self.nakit + self.brut_deger(fiyatlar)

    def maruziyet(self, sembol: str, fiyatlar: Mapping[str, float]) -> float:
        """Portföyün bu sembolde olan kesri [0,1]."""
        toplam = self.ozkaynak(fiyatlar)
        return self.deger(sembol, fiyatlar[sembol]) / toplam if toplam > 0.0 else 0.0

    def brut_maruziyet(self, fiyatlar: Mapping[str, float]) -> float:
        """Nakit dışı kesir — gross exposure (§12). Kaldıraçsız spotta [0,1]."""
        toplam = self.ozkaynak(fiyatlar)
        return self.brut_deger(fiyatlar) / toplam if toplam > 0.0 else 0.0

    def nakit_agirligi(self, fiyatlar: Mapping[str, float]) -> float:
        """Nakit bir pozisyondur (§12): ağırlığı ayrıca raporlanır, artık değil."""
        toplam = self.ozkaynak(fiyatlar)
        return self.nakit / toplam if toplam > 0.0 else 0.0

    def gorunum(self, sembol: str, fiyatlar: Mapping[str, float]) -> PozisyonDurumu:
        p = self.pozisyon(sembol)
        return PozisyonDurumu(
            miktar=p.miktar,
            ortalama_maliyet=p.ortalama_maliyet,
            exposure=self.maruziyet(sembol, fiyatlar) if sembol in fiyatlar else 0.0,
            giris_ms=p.giris_ms,
        )

    # ------------------------------------------------------------------ işlem

    def al(
        self, sembol: str, miktar: float, fiyat: float, komisyon: float, zaman_ms: int
    ) -> CokluPortfoy:
        yeni, gider = self.pozisyon(sembol).al(miktar, fiyat, komisyon, zaman_ms)
        _nakit_yeter(gider, self.nakit)
        return CokluPortfoy(
            nakit=max(self.nakit - gider, 0.0),
            pozisyonlar={**self.pozisyonlar, sembol: yeni},
        )

    def nakit_dus(self, tutar: float) -> CokluPortfoy:
        """Pozisyona dokunmadan nakitten düşer (finansman/rollover bedeli, K-095).

        Nakit yetmezse `PortfoyHatasi` — kaldıraçsız portföyde borç yoktur; bedeli sessizce
        kırpmak (`max(…, 0)`) maliyeti yok saymak olurdu.
        """
        if tutar < 0.0:
            raise PortfoyHatasi(f"düşülecek tutar negatif olamaz: {tutar}")
        _nakit_yeter(tutar, self.nakit)
        return CokluPortfoy(nakit=max(self.nakit - tutar, 0.0), pozisyonlar=dict(self.pozisyonlar))

    def sat(
        self, sembol: str, miktar: float, fiyat: float, komisyon: float
    ) -> tuple[CokluPortfoy, float]:
        yeni, hasilat, gerceklesen = self.pozisyon(sembol).sat(miktar, fiyat, komisyon)
        kalan = dict(self.pozisyonlar)
        if yeni.acik:
            kalan[sembol] = yeni
        else:
            kalan.pop(sembol, None)
        return CokluPortfoy(nakit=self.nakit + hasilat, pozisyonlar=kalan), gerceklesen


def fiyat_sozlugu(semboller: Iterable[str], fiyatlar: Mapping[str, float]) -> dict[str, float]:
    """Verilen sembollerin fiyatlarını eksiksiz bir sözlüğe toplar; eksik varsa hata.

    Eksik fiyatı sıfırla doldurmak, bir pozisyonu değersiz göstermek olurdu: özkaynak
    sessizce düşer, drawdown limiti tetiklenir ve sebebi hiçbir yerde yazmaz.
    """
    eksik = [s for s in semboller if s not in fiyatlar]
    if eksik:
        raise PortfoyHatasi(f"fiyatı olmayan pozisyon(lar): {', '.join(sorted(eksik))}")
    return {s: fiyatlar[s] for s in semboller}


__all__ = [
    "BOS",
    "CokluPortfoy",
    "Portfoy",
    "PortfoyHatasi",
    "Pozisyon",
    "fiyat_sozlugu",
]
