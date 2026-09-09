"""Portföy durumu: nakit, pozisyon, ortalama maliyet. (Faz 3)

Kapsam v1 (Final-Doküman): **spot, tek sembol, açığa satış ve kaldıraç yok.** Bunun iki
somut sonucu var ve ikisi de burada zorlanıyor: `nakit` ve `miktar` asla negatif olamaz.
Bu, bir tercih değil — açığa satış yasağının kod karşılığı. İhlali sessiz bir "borçlanma"
olurdu ve backtest karşılığı olmayan bir sermayeyle işlem yapardı.

Ortalama maliyet neden burada: gerçekleşen kâr/zarar (`realized P&L`) ancak bir çıkış
fiyatı bir giriş fiyatıyla karşılaştırılınca anlam kazanır. Kısmi alımlarda "hangi giriş"
sorusunun cevabı FIFO, LIFO veya ortalama maliyet olabilir; **ortalama maliyet** seçildi:
spot, tek sembol ve uzun-yönlü bir portföyde üçü de aynı toplam P&L'i verir, ama ortalama
maliyet tek bir sayı tutar — parti listesi tutmaya göre hem daha az durum hem daha az
sessiz hata yüzeyi.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from scryne_quant.strategy.baglam import PozisyonDurumu


class PortfoyHatasi(ValueError):
    """Portföy değişmezi ihlal edildi (negatif nakit, negatif miktar, geçersiz fiyat)."""


@dataclass(frozen=True, slots=True)
class Portfoy:
    """Bir andaki portföy. Değişmez: her işlem **yeni** bir portföy üretir.

    Değişmezlik burada lüks değil: backtest motoru bar bar ilerlerken bir önceki durumu
    kazara paylaşmak, equity eğrisinin geçmişini de değiştirirdi — ve o hata sonuçta
    "biraz farklı bir eğri" olarak görünür, çökme olarak değil.
    """

    nakit: float
    """Quote varlık (USDT). Negatif olamaz — kaldıraç yok."""

    miktar: float = 0.0
    """Baz varlık (BTC). Negatif olamaz — açığa satış yok."""

    ortalama_maliyet: float = 0.0
    """Elde tutulan miktarın komisyon **dahil** ortalama birim maliyeti. Pozisyon yoksa 0.

    Komisyon dahil olması bilinçli: "kaça mal oldu" sorusunun dürüst cevabı, ödenen
    komisyonu içerir. Hariç tutmak, her pozisyonu gerçekte olduğundan ucuz gösterirdi.
    """

    giris_ms: int | None = None
    """Pozisyonun **ilk** açıldığı barın zamanı. Tutma süresi metriği buna bakar."""

    def __post_init__(self) -> None:
        if self.nakit < 0.0:
            raise PortfoyHatasi(f"nakit negatif olamaz (kaldıraç yok): {self.nakit}")
        if self.miktar < 0.0:
            raise PortfoyHatasi(f"miktar negatif olamaz (açığa satış yok): {self.miktar}")

    # ------------------------------------------------------------------ ölçüm

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
        if miktar <= 0.0 or fiyat <= 0.0:
            raise PortfoyHatasi(f"geçersiz alım: miktar={miktar}, fiyat={fiyat}")
        gider = miktar * fiyat + komisyon
        if gider > self.nakit + _TOLERANS * max(self.nakit, 1.0):
            raise PortfoyHatasi(f"yetersiz nakit: gerekli {gider}, mevcut {self.nakit}")

        yeni_miktar = self.miktar + miktar
        # Komisyon ortalama maliyete giriyor: "kaça mal oldu"nun dürüst cevabı bu.
        yeni_maliyet = (self.ortalama_maliyet * self.miktar + gider) / yeni_miktar
        return replace(
            self,
            nakit=max(self.nakit - gider, 0.0),
            miktar=yeni_miktar,
            ortalama_maliyet=yeni_maliyet,
            giris_ms=self.giris_ms if self.acik else zaman_ms,
        )

    def sat(self, miktar: float, fiyat: float, komisyon: float) -> tuple[Portfoy, float]:
        """Satım uygular. Portföy ve bu satımın **gerçekleşen** kâr/zararını döndürür.

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
            replace(
                self,
                nakit=self.nakit + hasilat,
                miktar=0.0 if kapandi else kalan,
                ortalama_maliyet=0.0 if kapandi else self.ortalama_maliyet,
                giris_ms=None if kapandi else self.giris_ms,
            ),
            hasilat - maliyet,
        )


#: Kayan nokta karşılaştırma payı. Mutlak değil bağıl kullanılıyor: 10.000 USDT'lik bir
#: portföyde 1e-12 mutlak eşik, 1.000.000 USDT'likte anlamsız olurdu.
_TOLERANS = 1e-9
