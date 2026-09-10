"""Fill modeli: `t+1` açılışı, her zaman aleyhte slippage. (K-004, K-007)

İki kural bu modülde yaşıyor ve ikisi de tek satırda özetlenebilir:

- **K-004:** `t` barında üretilen sinyal `t+1` barının **açılış** fiyatından dolar. Sinyal
  barının kapanışından doldurmak, karar anında henüz bilinmeyen bir fiyatı kullanmaktır —
  gizli bir look-ahead. Bu kural tek başına backtest getirilerini düşürür; bu bir kayıp
  değil, kâğıt üzerindeki sahte kazancın kaldırılmasıdır.
- **K-007:** slippage **her zaman aleyhte**. Alışta fiyat yukarı, satışta aşağı kayar.
  Belirsizlikte kötü yöne yuvarla: backtest gerçeğinden kötü çıkarsa sürpriz iyi olur,
  iyi çıkarsa sürpriz para kaybettirir.

**Boyutlandırma neden burada:** `Sinyal.target_exposure` mutlak bir hedeftir ("portföyün
%20'si"), delta değil. Hedefi miktara çevirmek fiyat gerektirir, fiyat da fill anında
belli olur. İkisini ayırmak, sizing'in hangi fiyata göre yapıldığını belirsiz bırakırdı.

**Yön kararı ham açılıştan, işlem kayan fiyattan.** Önce ham `open` ile "almalı mıyım
satmalı mıyım" sorusu cevaplanır, sonra o yönün aleyhte fiyatı uygulanır. Ters sıra
döngüsel olurdu: kayma yönünü bilmek için yönü, yönü bilmek için kaymayı bilmek gerekirdi.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.portfolio.durum import Portfoy
from scryne_quant.strategy.sinyal import Sinyal

BPS: Final = 1e-4

#: İşlem sayılması için gereken en küçük büyüklük, özkaynağa oranla. Bunun altındaki
#: farklar kayan nokta artığıdır; komisyon ödeyip toz miktar almak, metrikleri gerçek
#: olmayan yüzlerce işlemle şişirirdi.
#:
#: Bu bir **rebalance bandı değildir** — "%1'den az sapmayı düzeltme" gibi bir kural risk
#: motorunun kararıdır (Faz 5), motorun değil. Buradaki eşik yalnızca sıfırı sıfır saymak
#: içindir. Borsanın gerçek minimum emir büyüklüğü Faz 7'nin konusu.
ASGARI_ORAN: Final = 1e-12


class IslemYonu(StrEnum):
    AL = "AL"
    SAT = "SAT"


class AtlamaSebebi(StrEnum):
    """Bir sinyalin neden işleme dönüşmediği. Sessiz kayıp olmasın diye sayılır."""

    ISINMA_PENCERESI = "isinma_penceresi"
    """Sinyal ölçüm penceresinden önce üretildi; o barlar yalnızca indikatör ısınması için var."""

    SONRAKI_BAR_YOK = "sonraki_bar_yok"
    """Sinyal son barda üretildi; dolacağı `t+1` barı yok (K-004)."""

    FILL_BARI_OK_DEGIL = "fill_bari_ok_degil"
    """`t+1` barının kalite bayrağı `ok` değil; şüpheli fiyattan doldurmuyoruz (K-006)."""

    HEDEF_ZATEN_TUTTURULMUS = "hedef_zaten_tutturulmus"
    """İstenen maruziyet zaten mevcut; işleme gerek yok."""

    NAKIT_YOK = "nakit_yok"
    """Alım isteniyor ama harcanabilir nakit sıfır."""

    POZISYON_YOK = "pozisyon_yok"
    """Satım isteniyor ama elde varlık yok."""

    RISK_REDDETTI = "risk_reddetti"
    """Risk motoru sinyali onaylamadı (Faz 5). Sebebin kendisi audit'te ve `risk` özetinde;
    burada yalnızca akış muhasebesi için sayılıyor — üretilen sinyallerin toplamı
    işlenen + atlanan'a eşit kalmalı, yoksa bir yerde sessiz kayıp var."""


@dataclass(frozen=True, slots=True)
class Emir:
    """Bir sinyalin `t+1`de dönüştüğü somut işlem. Henüz uygulanmamış hâli."""

    yon: IslemYonu
    miktar: float
    """Baz varlık miktarı."""

    fiyat: float
    """Slippage uygulanmış gerçekleşme fiyatı."""

    referans_fiyat: float
    """Slippage öncesi ham `open[t+1]`. Slippage maliyetini raporlamak için saklanıyor."""

    komisyon: float
    """Quote biriminde taker komisyonu."""

    zaman_ms: int
    """Fill barının açılış zamanı — yani `t+1`in timestamp'i (K-005)."""

    @property
    def notional(self) -> float:
        return self.miktar * self.fiyat

    @property
    def slippage_maliyeti(self) -> float:
        """Slippage'ın quote cinsinden bedeli. Her zaman ≥ 0 — aleyhte olduğu için."""
        return abs(self.fiyat - self.referans_fiyat) * self.miktar


def fill_fiyati(referans: float, yon: IslemYonu, maliyet: MaliyetModeli) -> float:
    """Aleyhte kaydırılmış fill fiyatı (K-007).

    >>> from scryne_quant.common.maliyet import MaliyetModeli
    >>> m = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
    >>> fill_fiyati(100.0, IslemYonu.AL, m)
    100.05
    """
    kayma = maliyet.slippage_bps * BPS
    return referans * (1.0 + kayma) if yon is IslemYonu.AL else referans * (1.0 - kayma)


def emir_hazirla(
    sinyal: Sinyal,
    portfoy: Portfoy,
    acilis: float,
    zaman_ms: int,
    maliyet: MaliyetModeli,
    *,
    hedef_maruziyet: float | None = None,
) -> Emir | AtlamaSebebi:
    """Sinyali `t+1` açılışında somut bir emre çevirir; çevrilemiyorsa sebebini döndürür.

    Sebebi `None` yerine bir enum olarak döndürmek bilinçli: "sinyal işleme dönmedi"
    bilgisi sonuç kaydına yazılıyor. Sessizce `None` dönen bir fonksiyon, stratejinin
    ürettiği sinyallerin kaçının neden kaybolduğunu görünmez kılardı.

    `hedef_maruziyet` risk motoru devredeyken (Faz 5) veriliyor: boyutu belirleyen şey o
    hâlde stratejinin istediği değil, riskin **onayladığı** hedef. Ayrı bir parametre
    olmasının sebebi `Sinyal`in değişmez olması ve olması gerektiği — risk motorunun
    stratejinin sinyalini yeniden yazabildiği bir mimaride, audit'te "strateji ne istedi"
    sorusunun cevabı kaybolurdu (`OnayliNiyet` ikisini birlikte taşıyor).

    Sinyalin hedefinden **büyük** bir değer kabul edilmiyor: risk aşağı çeker, yukarı asla.
    """
    if acilis <= 0.0:
        raise ValueError(f"geçersiz açılış fiyatı: {acilis}")

    hedef = sinyal.target_exposure if hedef_maruziyet is None else hedef_maruziyet
    if not 0.0 <= hedef <= sinyal.target_exposure:
        raise ValueError(
            "hedef maruziyet [0, sinyalin hedefi] aralığında olmalı: "
            f"sinyal={sinyal.target_exposure}, verilen={hedef}"
        )

    fee = maliyet.fee_taker_bps * BPS
    deger = portfoy.deger(acilis)
    ozkaynak = portfoy.nakit + deger
    fark = ozkaynak * hedef - deger

    if abs(fark) <= ASGARI_ORAN * max(ozkaynak, 1.0):
        return AtlamaSebebi.HEDEF_ZATEN_TUTTURULMUS

    if fark > 0.0:
        yon = IslemYonu.AL
        fiyat = fill_fiyati(acilis, yon, maliyet)
        # Notional N'i almak N + N·fee nakit ister; harcanabilir tavan bu yüzden
        # nakit/(1+fee). Tavanı aşmak, olmayan parayla işlem yapmak olurdu.
        notional = min(fark, portfoy.nakit / (1.0 + fee))
        if notional <= ASGARI_ORAN * max(ozkaynak, 1.0):
            return AtlamaSebebi.NAKIT_YOK
    else:
        yon = IslemYonu.SAT
        fiyat = fill_fiyati(acilis, yon, maliyet)
        # Tavan elde olan: `FLAT` sinyalinde bu tavan devreye girer ve pozisyonu tam
        # kapatır — hedef ham `open`den, satış kaymış fiyattan hesaplandığı için
        # tavansız bir çıkış elde olandan fazlasını satmaya çalışırdı.
        notional = min(-fark, portfoy.miktar * fiyat)
        if notional <= ASGARI_ORAN * max(ozkaynak, 1.0):
            return AtlamaSebebi.POZISYON_YOK

    return Emir(
        yon=yon,
        miktar=notional / fiyat,
        fiyat=fiyat,
        referans_fiyat=acilis,
        komisyon=notional * fee,
        zaman_ms=zaman_ms,
    )
