"""Emir tarafı borsa sözleşmesi. (§25, §33, Faz 7)

`temel.BorsaAdaptoru` okuma tarafıdır — bar çeker, saat sorar. Bu modül **yazma**
tarafıdır ve ayrı olmasının iki sebebi var:

1. **Bağımlılık.** `temel.py` pandas taşıyor; `oms/` ve `execution/` kapanışında pandas
   yasak (`test_risk_bypass.py`). Emir yolu bu sözleşmeyi import etmek zorunda.
2. **Yetki.** Bar çekmek için anahtar gerekmez, emir göndermek için gerekir. İki yeteneği
   tek arayüzde toplamak, yalnızca veri okuyan bir bileşene emir gönderme yetkisi
   **vermiş** olurdu — tip düzeyinde. Ayrı arayüz, ayrı yetki.

**Sözleşmenin en önemli maddesi bir dönüş değeri değil, bir istisna.** `emir_gonder`
başarısız olduğunda üç ayrı hata atabilir ve aralarındaki fark bu projenin en pahalı
ayrımı:

| Hata | Anlamı | Emir borsada var mı | Yeniden gönderilir mi |
| --- | --- | --- | --- |
| `GonderilemediHatasi` | İstek hiç çıkmadı | **Hayır**, biliniyor | Evet |
| `BorsaReddetti` | Borsa açıkça reddetti | **Hayır**, biliniyor | Hayır (sebep giderilmeden) |
| `BelirsizSonuc` | Yanıt kayboldu | **Bilinmiyor** | **Asla** |

Bu ayrımı **adaptör** yapar, çağıran değil: istek bayta dökülüp dökülmediğini yalnızca
transport bilir. Çağırana bırakılsaydı, her çağıranın aynı doğru kararı vermesi gerekirdi
— ve bir kez unutulan yerde duplicate emir doğardı.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from scryne_quant.exchange.kurallar import SembolKurallari
from scryne_quant.oms.emir import EmirDurumu

#: Binance emir durumlarının bizim state machine'imize eşlenmesi.
#:
#: `PENDING_CANCEL` bilerek `ACKNOWLEDGED`a eşleniyor, `CANCELED`a değil: iptal **istendi**
#: ama tamamlanmadı, yani emir hâlâ dolabilir. `CANCELED` saymak, dolabilecek bir emri
#: defterde kapalı göstermek olurdu — ve pozisyon farkı tam olarak böyle doğar.
BINANCE_DURUM: dict[str, EmirDurumu] = {
    "NEW": EmirDurumu.ACKNOWLEDGED,
    "PENDING_NEW": EmirDurumu.ACKNOWLEDGED,
    "PARTIALLY_FILLED": EmirDurumu.PARTIALLY_FILLED,
    "FILLED": EmirDurumu.FILLED,
    "CANCELED": EmirDurumu.CANCELED,
    "PENDING_CANCEL": EmirDurumu.ACKNOWLEDGED,
    "REJECTED": EmirDurumu.REJECTED,
    "EXPIRED": EmirDurumu.EXPIRED,
    "EXPIRED_IN_MATCH": EmirDurumu.EXPIRED,
}


#: Bizim yön sözlüğümüzün borsa karşılığı.
#:
#: `FLAT` (tam çıkış) borsada yok — orada yalnızca BUY ve SELL var. Çeviri **burada**,
#: sözleşmenin kenarında yapılıyor; defterde yön `FLAT` olarak kalıyor. Sebep: "pozisyonu
#: tamamen kapat" ile "pozisyonu azalt" farklı kararlardır ve audit'in ikisini ayırt
#: edebilmesi gerekir. Defteri borsanın sözlüğüne indirgemek o farkı kalıcı olarak silerdi.
BORSA_YONU: dict[str, str] = {"BUY": "BUY", "SELL": "SELL", "FLAT": "SELL"}


class GecersizYon(ValueError):
    """Yön borsanın sözlüğüne çevrilemiyor."""


def borsa_yonu(yon: str) -> str:
    try:
        return BORSA_YONU[yon.upper()]
    except KeyError as hata:
        raise GecersizYon(
            f"borsaya çevrilemeyen yön: {yon!r}. Bilinen: {', '.join(sorted(BORSA_YONU))}"
        ) from hata


class BilinmeyenDurum(ValueError):
    """Borsa tanımadığımız bir emir durumu döndürdü.

    **Tahmin edilmiyor, hata veriliyor.** Bilinmeyen bir durumu "herhalde açıktır" veya
    "herhalde kapanmıştır" diye eşlemek, bu projenin en tehlikeli hata sınıfı olan
    *"neredeyse doğru"* sonucu üretir. Borsa yeni bir durum eklerse eşleme tablosu
    elle güncellenir — ve o güncelleme bir diff satırı olarak görülür.
    """


def durum_esle(ham: str) -> EmirDurumu:
    try:
        return BINANCE_DURUM[ham]
    except KeyError as hata:
        raise BilinmeyenDurum(
            f"borsa tanınmayan emir durumu döndürdü: {ham!r}. "
            f"Bilinen: {', '.join(sorted(BINANCE_DURUM))}"
        ) from hata


@dataclass(frozen=True, slots=True)
class BorsaEmri:
    """Borsanın bir emir hakkında **söylediği** şey. Bizim kaydımız değil.

    `oms/emir.Emir` ile bilerek ayrı bir tip: biri bizim defterimiz, diğeri borsanın
    beyanı, ve reconciliation (§25) tam olarak ikisini karşılaştırır. Aynı tipi
    kullansaydık karşılaştırmanın iki tarafı isim düzeyinde karışırdı — ve "hangisi
    bizim kaydımızdı" sorusu bir okuma dikkatine kalırdı.
    """

    istemci_kimligi: str
    borsa_kimligi: str
    sembol: str
    yon: str
    durum: EmirDurumu
    miktar: float
    dolan_miktar: float
    ortalama_fiyat: float
    guncellendi_ms: int
    ham_durum: str = ""

    def sozluk(self) -> dict[str, Any]:
        return {
            "istemci_kimligi": self.istemci_kimligi,
            "borsa_kimligi": self.borsa_kimligi,
            "sembol": self.sembol,
            "yon": self.yon,
            "durum": str(self.durum),
            "ham_durum": self.ham_durum,
            "miktar": self.miktar,
            "dolan_miktar": self.dolan_miktar,
            "ortalama_fiyat": self.ortalama_fiyat,
            "guncellendi_ms": self.guncellendi_ms,
        }


class EmirAdaptoru(ABC):
    """Emir gönderen borsa sözleşmesi. Anahtar taşır, imzalı istek yapar."""

    @abstractmethod
    def sunucu_zamani_ms(self) -> int:
        """Borsanın saati, UTC epoch ms."""

    @abstractmethod
    def saat_sapmasi_ms(self) -> int:
        """Yerel saat − borsa saati. Pozitif: yerel ileride.

        Ayrı bir metot çünkü bu sayı bir **sağlık göstergesi**, bir ara değer değil:
        dashboard'da görünür ve sapma büyüdüğünde koşu durur.
        """

    @abstractmethod
    def sembol_kurallari(self, sembol: str) -> SembolKurallari:
        """Emir kuralları (tick, step, minNotional). Önbelleklenmesi beklenir."""

    @abstractmethod
    def son_fiyat(self, sembol: str) -> float:
        """Son işlem fiyatı — yalnızca `minNotional` ön kontrolü için."""

    @abstractmethod
    def market_emri(
        self, *, istemci_kimligi: str, sembol: str, yon: str, miktar: float
    ) -> BorsaEmri:
        """Market emri gönderir. `istemci_kimligi` **borsaya** gider (idempotency).

        Aynı `istemci_kimligi` ile ikinci çağrı `BorsaReddetti(kod=-2010)` almalıdır —
        duplicate korumasının borsa tarafındaki yarısı budur ve gerçek testnet'e karşı
        ölçülmesi Faz 7'nin bitti kriteri.

        Hata sözleşmesi modül docstring'indeki tabloda; `BelirsizSonuc` **asla** yeniden
        denenmez.
        """

    @abstractmethod
    def emir_sorgula(self, *, sembol: str, istemci_kimligi: str) -> BorsaEmri | None:
        """Emri istemci kimliğiyle sorgular. Borsa tanımıyorsa `None`.

        `None` burada kesin bir cevaptır: *"bu kimlikle bir emir oluşmadı"*. `UNKNOWN`dan
        çıkışın tek yolu bu metottur — ve tek yol olması bir tasarım kararı, kolaylık
        değil (`oms/emir.py`).
        """

    @abstractmethod
    def acik_emirler(self, sembol: str) -> list[BorsaEmri]:
        """Borsada açık görünen emirler. Reconciliation'ın **borsa tarafı** (§25).

        Defterin bilmediği bir emir buradan çıkar — ve o, sistemin üretmediği ya da
        kaydını kaybettiği bir emirdir. İkisi de koşuyu durdurur.
        """

    @abstractmethod
    def bakiye(self) -> dict[str, float]:
        """Varlık → serbest miktar. Pozisyon mutabakatının borsa tarafı."""


__all__ = [
    "BINANCE_DURUM",
    "BORSA_YONU",
    "BilinmeyenDurum",
    "GecersizYon",
    "BorsaEmri",
    "EmirAdaptoru",
    "borsa_yonu",
    "durum_esle",
]
