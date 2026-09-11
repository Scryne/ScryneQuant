"""Emir state machine ve idempotency anahtarı. (§33, Faz 7)

Faz 7'nin bitti kriterlerinden biri şu: *"Aynı intent iki kez gönderildiğinde tek emir
oluşuyor (duplicate order üretilemiyor)."* Bu modül o cümlenin taşıyıcısı ve projenin
**gerçek parayla en doğrudan temas eden** yeri: yanlış bir duplicate, geri alınamaz bir
işlemdir.

**İki mekanizma, ve ikisi de tek başına yetmez:**

1. **Deterministik istemci emir kimliği.** Emrin kimliği, onaylı niyetin **içeriğinden**
   türetiliyor — rastgele üretilmiyor, sayaçtan gelmiyor. Aynı niyet ikinci kez
   gönderildiğinde aynı kimlik çıkıyor ve borsa ikincisini reddediyor. Rastgele bir kimlik
   olsaydı, "aynı niyet" ile "farklı niyet" borsanın gözünde ayırt edilemezdi.
2. **Yazım gönderimden önce.** `SUBMITTED` satırı ağ çağrısından **önce** diske yazılıyor.
   Ters sırada, gönderim ile yazım arasında ölen bir süreç, sistemin hiç bilmediği bir
   emir bırakırdı — yetim emir, ve onu bulmanın tek yolu borsayı sorgulamak olurdu ki
   sistem aramayı bile bilmezdi. Bu sırayla en kötü durum, hiç gönderilmemiş bir emrin
   kaydı; reconciliation onu borsaya sorup bulamayınca kapatır. İki hatadan **bilinen
   olanı** seçiliyor (Faz 6'nın kontrol noktası kararının, K-038, aynı mantığı).

**`UNKNOWN` bir başarısızlık değil, bir bilinmezliktir — ve fark hayati.** Gönderim yapıldı
ama yanıt kaybolduysa emir borsada olabilir de olmayabilir de. `UNKNOWN`u `FAILED` sayıp
yeniden denemek, duplicate emir üretmenin **en kısa yolu**. `UNKNOWN`dan çıkışın tek yolu
borsayı **sorgulamak**; varsayım yok.

`durum_gecisi` yasal olmayan her geçişi reddediyor. Sessizce izin vermek, bir emrin
`FILLED`ten `SUBMITTED`e dönebildiği bir sistem demek olurdu — ve o sistemde pozisyon
sayısı bir muhasebe sorusu değil, bir tahmin.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Final

from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.zaman import utc_str
from scryne_quant.risk.niyet import OnayliNiyet, dogrula

#: Binance `newClientOrderId` sınırı: 36 karakter, `[A-Za-z0-9_-]`. Kimlik bu sınıra
#: sığmak zorunda, yani hash kısaltılıyor.
KIMLIK_UZUNLUGU: Final = 32

#: Kimliğin önekine koşu adı girmiyor, **ön ek sabit**: kimlik yalnızca niyetin
#: içeriğinden türemeli. Koşu adı girseydi, aynı niyeti farklı bir koşu adıyla yeniden
#: göndermek yeni bir kimlik üretir ve duplicate koruması bir yazım hatasıyla delinirdi.
KIMLIK_ONEKI: Final = "sq"


#: Bir emirde kesilen komisyon: `(varlık, miktar)` çiftleri, varlık adına göre sıralı.
#:
#: **Neden tek bir sayı değil.** Binance komisyonu alınan varlıktan keser: BTC alırken
#: BTC'den, satarken USDT'den; hesapta BNB varsa ikisinin yerine BNB'den. Tek bir sayı
#: hangi varlığın azaldığını söylemez — ve pozisyon mutabakatı varlık bazında yapılır.
#: Sözlük yerine sıralı çift: değişmez, deterministik, JSON'a olduğu gibi yazılır.
#:
#: Bu tip `exchange/` değil `oms/` altında çünkü komisyon bir **muhasebe** büyüklüğü:
#: emrin kaydının parçası, borsa protokolünün ayrıntısı değil. `emir_adaptoru` buradan
#: import ediyor; ters yön (oms'un exchange'i import etmesi) hem döngü hem katman ihlali
#: olurdu.
Komisyon = tuple[tuple[str, float], ...]


def komisyon_topla(kalemler: Iterable[tuple[str, float]]) -> Komisyon:
    """Fill başına gelen komisyon kalemlerini varlık bazında toplar.

    Tek emir birden çok fill'e bölünebilir ve her fill kendi komisyonunu taşır; hatta
    hesaptaki BNB biterse aynı emrin bir kısmı BNB'den, kalanı alınan varlıktan kesilir.
    Toplamayı çağırana bırakmak o vakayı bir kez unutmaya bakardı.
    """
    toplam: dict[str, float] = {}
    for varlik, miktar in kalemler:
        if not varlik:
            continue
        toplam[varlik] = toplam.get(varlik, 0.0) + float(miktar)
    return tuple(sorted((v, m) for v, m in toplam.items() if m != 0.0))


#: `Emir.komisyon_kaynagi` alabileceği değerler.
#:
#: Boş dize **"komisyon yok" değil "komisyon bilinmiyor"** demek, ve bu ayrım pozisyon
#: mutabakatının tamamını taşıyor: bilinmeyeni sıfır saymak her alımda ~%0,1'lik sessiz
#: bir fark bırakır ve fark emir sayısıyla büyür.
KOMISYON_KAYNAKLARI: Final[frozenset[str]] = frozenset({"", "yanit", "islemler"})


#: Emir türleri. Faz 7 yalnızca `MARKET` kullandı; `LIMIT` Faz 8 hazırlığında açıldı (K-047).
#:
#: Tür defterde **ayrı bir sütun**, `limit_fiyati`nın dolu olup olmamasından çıkarılmıyor:
#: "fiyatı yoksa market'tir" kuralı, fiyatı yazılmayı unutulmuş bir limit emrini sessizce
#: market emri gibi okur. Tür bir beyandır, bir çıkarım değil.
EMIR_TURLERI: Final[frozenset[str]] = frozenset({"MARKET", "LIMIT"})


class EmirHatasi(ValueError):
    """Emir sözleşmesi ihlal edildi."""


class GecersizGecis(EmirHatasi):
    """State machine'de yasal olmayan bir geçiş denendi."""


class EmirDurumu(StrEnum):
    """§33'ün emir yaşam döngüsü."""

    CREATED = "CREATED"
    """Niyetten emir üretildi; henüz doğrulanmadı."""

    VALIDATED = "VALIDATED"
    """Sembol kuralları (lot, tick, minNotional) kontrol edildi."""

    SUBMITTED = "SUBMITTED"
    """Diske yazıldı ve borsaya **gönderilmek üzere**. Ağ çağrısından önceki son durum."""

    ACKNOWLEDGED = "ACKNOWLEDGED"
    """Borsa emri kabul etti ve bir kimlik döndürdü."""

    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"

    REJECTED = "REJECTED"
    """Borsa reddetti (kural ihlali, bakiye, duplicate kimlik). **Nihai.**"""

    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"

    FAILED = "FAILED"
    """Gönderim **hiç yapılamadı** — yani borsada emir olmadığı **biliniyor**.

    `UNKNOWN`dan farkı bu bilgi. `FAILED` bir emir yeniden gönderilebilir; `UNKNOWN` bir
    emir gönderilemez."""

    UNKNOWN = "UNKNOWN"
    """Gönderildi ama sonucu bilinmiyor (yanıt kayboldu, zaman aşımı, süreç öldü).

    **Yeniden gönderilmez.** Çıkış yalnızca borsayı sorgulayıp gerçek durumu öğrenmekle
    olur (§25 reconciliation). Bu durumu "başarısız" sayıp yeniden denemek, duplicate emir
    üretmenin en kısa yoludur."""


#: Nihai durumlar: buradan hiçbir yere geçilmez.
NIHAI: Final[frozenset[EmirDurumu]] = frozenset(
    {
        EmirDurumu.FILLED,
        EmirDurumu.REJECTED,
        EmirDurumu.CANCELED,
        EmirDurumu.EXPIRED,
        EmirDurumu.FAILED,
    }
)

#: Borsada emrin **var olabileceği** durumlar. Reconciliation'ın sorgulayacağı küme.
ACIK: Final[frozenset[EmirDurumu]] = frozenset(
    {
        EmirDurumu.SUBMITTED,
        EmirDurumu.ACKNOWLEDGED,
        EmirDurumu.PARTIALLY_FILLED,
        EmirDurumu.UNKNOWN,
    }
)

#: Yasal geçişler. Listede olmayan her geçiş hata.
#:
#: Dikkat çeken üç yer:
#: - `SUBMITTED → UNKNOWN`: yanıt kaybolduğunda gidilen yer. `FAILED` değil.
#: - `UNKNOWN → *`: yalnızca sorgulama sonucuyla; `UNKNOWN → SUBMITTED` **yok**, yani
#:   yeniden göndermek state machine düzeyinde imkânsız.
#: - `PARTIALLY_FILLED → CANCELED`: kısmi dolmuş bir emir iptal edilebilir ve dolan kısım
#:   kalır. Bunu `FILLED` saymak, olmayan bir miktarı defterde var etmek olurdu.
GECISLER: Final[dict[EmirDurumu, frozenset[EmirDurumu]]] = {
    EmirDurumu.CREATED: frozenset({EmirDurumu.VALIDATED, EmirDurumu.REJECTED}),
    EmirDurumu.VALIDATED: frozenset({EmirDurumu.SUBMITTED, EmirDurumu.REJECTED}),
    EmirDurumu.SUBMITTED: frozenset(
        {
            EmirDurumu.ACKNOWLEDGED,
            EmirDurumu.REJECTED,
            EmirDurumu.FAILED,
            EmirDurumu.UNKNOWN,
        }
    ),
    EmirDurumu.ACKNOWLEDGED: frozenset(
        {
            EmirDurumu.PARTIALLY_FILLED,
            EmirDurumu.FILLED,
            EmirDurumu.CANCELED,
            EmirDurumu.EXPIRED,
            EmirDurumu.UNKNOWN,
        }
    ),
    EmirDurumu.PARTIALLY_FILLED: frozenset(
        {
            EmirDurumu.PARTIALLY_FILLED,
            EmirDurumu.FILLED,
            EmirDurumu.CANCELED,
            EmirDurumu.EXPIRED,
            EmirDurumu.UNKNOWN,
        }
    ),
    EmirDurumu.UNKNOWN: frozenset(
        {
            EmirDurumu.ACKNOWLEDGED,
            EmirDurumu.PARTIALLY_FILLED,
            EmirDurumu.FILLED,
            EmirDurumu.CANCELED,
            EmirDurumu.EXPIRED,
            EmirDurumu.REJECTED,
            EmirDurumu.FAILED,
        }
    ),
    **dict.fromkeys(NIHAI, frozenset()),
}


def gecis_yasal_mi(nereden: EmirDurumu, nereye: EmirDurumu) -> bool:
    return nereye in GECISLER[nereden]


def istemci_kimligi(niyet: OnayliNiyet) -> str:
    """Onaylı niyetten **deterministik** istemci emir kimliği. (Faz 7 bitti kriteri)

    Aynı niyet → aynı kimlik → borsa ikinciyi reddeder. Duplicate korumasının tamamı bu
    cümlede ve iki ayrıntıda:

    - **Mühür kimliğe girmiyor.** Mühür süreç başına rastgele (K-032); girseydi, süreç
      yeniden başladığında aynı niyet farklı bir kimlik üretir ve koruma tam da en çok
      gerektiği anda — restart sonrasında — çökerdi.
    - **Niyet doğrulanıyor.** Mühürsüz bir nesneden kimlik üretmek, risk motorundan
      geçmemiş bir şeye emir kimliği vermek olurdu.

    Kimlik `KIMLIK_UZUNLUGU` altıgen karaktere kısaltılıyor (Binance 36 karakter sınırı).
    128 bit, çarpışma olasılığı bu ölçekte anlamsız.
    """
    onayli = dogrula(niyet)
    govde = nesne_hash(
        {
            "sinyal": onayli.sinyal.model_dump(mode="json"),
            "onayli_maruziyet": onayli.onayli_maruziyet,
            "limit_kimligi": onayli.limit_kimligi,
            "karar_ms": onayli.karar_ms,
            "kisitlayan": list(onayli.kisitlayan),
        }
    )
    return f"{KIMLIK_ONEKI}{govde[:KIMLIK_UZUNLUGU]}"


@dataclass(frozen=True, slots=True)
class Emir:
    """Bir emrin kaydı. Değişmez: her geçiş **yeni** bir emir üretir.

    Değişmezlik burada muhasebe güvenliği: bir emri yerinde güncellemek, geçmiş durumunu
    silmek demek. Oysa "bu emir hangi yoldan buraya geldi" sorusu, bir uyuşmazlık
    araştırmasının ilk sorusu.
    """

    istemci_kimligi: str
    sembol: str
    yon: str
    miktar: float
    durum: EmirDurumu = EmirDurumu.CREATED

    tur: str = "MARKET"
    """`MARKET` ya da `LIMIT` (`EMIR_TURLERI`)."""

    limit_fiyati: float = 0.0
    """Limit emrinin fiyatı; market emrinde 0. `ortalama_fiyat` ile karıştırılmamalı —
    biri **istenen**, diğeri **gerçekleşen**. İkisini tek alanda tutmak, dolmamış bir
    limit emrinin fiyatını "gerçekleşmiş fiyat" gibi okutur."""

    borsa_kimligi: str | None = None
    """Borsanın verdiği kimlik. `ACKNOWLEDGED` öncesi `None`."""

    dolan_miktar: float = 0.0
    ortalama_fiyat: float = 0.0
    karar_ms: int = 0
    """Emri doğuran kararın bar zamanı (K-005)."""

    olusturuldu_ms: int = 0
    guncellendi_ms: int = 0
    gecmis: tuple[str, ...] = field(default=())
    """Geçilen durumların sırası. Uyuşmazlık araştırmasının ilk baktığı yer."""

    komisyon: Komisyon = ()
    """Bu emirde kesilen komisyon. Boşsa `komisyon_kaynagi`ye bakılır."""

    komisyon_kaynagi: str = ""
    """`yanit`, `islemler`, ya da boş: **bilinmiyor.** (`KOMISYON_KAYNAKLARI`)"""

    hata: str = ""

    def __post_init__(self) -> None:
        if self.miktar <= 0.0:
            raise EmirHatasi(f"emir miktarı pozitif olmalı: {self.miktar}")
        if self.dolan_miktar < 0.0 or self.dolan_miktar > self.miktar * (1 + 1e-9):
            raise EmirHatasi(
                f"dolan miktar [0, miktar] aralığında olmalı: {self.dolan_miktar} / {self.miktar}"
            )
        if self.komisyon_kaynagi not in KOMISYON_KAYNAKLARI:
            raise EmirHatasi(
                f"bilinmeyen komisyon kaynağı: {self.komisyon_kaynagi!r}. "
                f"Geçerli: yanit, islemler, '' (bilinmiyor)"
            )
        if self.komisyon and not self.komisyon_kaynagi:
            raise EmirHatasi(
                "kaynaksız komisyon yazılamaz: bir rakam, nereden geldiği bilinmeden "
                "muhasebeye giremez"
            )
        if self.tur not in EMIR_TURLERI:
            raise EmirHatasi(
                f"bilinmeyen emir türü: {self.tur!r}. Geçerli: "
                f"{', '.join(sorted(EMIR_TURLERI))}"
            )
        if self.tur == "LIMIT" and self.limit_fiyati <= 0.0:
            raise EmirHatasi(
                f"limit emrinin fiyatı pozitif olmalı: {self.limit_fiyati}. Fiyatsız bir "
                f"limit emri, borsada market emrine dönüşmez — hiç oluşmaz."
            )
        if self.tur == "MARKET" and self.limit_fiyati != 0.0:
            raise EmirHatasi(
                f"market emrinin limit fiyatı olamaz: {self.limit_fiyati}. Bir fiyat "
                f"taşıyan market emri, okuyana o fiyattan dolduğunu düşündürür."
            )

    @property
    def komisyon_bilinmiyor(self) -> bool:
        """Dolmuş ama komisyonu öğrenilmemiş bir emir mi?

        Dolmamış emrin komisyonu zaten yoktur; soru yalnızca dolmuş emirler için anlamlı.
        Pozisyon mutabakatı bu emirleri **eksik** sayar, sıfır komisyonlu saymaz.
        """
        return self.dolan_miktar > 0.0 and not self.komisyon_kaynagi

    @property
    def acik(self) -> bool:
        """Borsada var olabilir mi? Reconciliation bu kümeyi sorguluyor."""
        return self.durum in ACIK

    @property
    def nihai(self) -> bool:
        return self.durum in NIHAI

    @property
    def kalan(self) -> float:
        return max(0.0, self.miktar - self.dolan_miktar)

    def gecir(
        self,
        durum: EmirDurumu,
        *,
        zaman_ms: int,
        borsa_kimligi: str | None = None,
        dolan_miktar: float | None = None,
        ortalama_fiyat: float | None = None,
        komisyon: Komisyon | None = None,
        komisyon_kaynagi: str | None = None,
        hata: str = "",
    ) -> Emir:
        """Yeni duruma geçmiş **yeni** bir emir döndürür. Yasal olmayan geçiş hatadır."""
        if not gecis_yasal_mi(self.durum, durum):
            raise GecersizGecis(
                f"yasal olmayan geçiş: {self.durum} → {durum} "
                f"(emir {self.istemci_kimligi}). Geçerli: "
                f"{', '.join(sorted(GECISLER[self.durum])) or 'yok (nihai durum)'}"
            )
        # Komisyon **üzerine yazılmaz, yalnızca boşken doldurulur.** Bir emrin komisyonu
        # bir kez ölçülür; ikinci bir kaynağın farklı bir sayı söylemesi sessizce kabul
        # edilecek bir şey değil, araştırılacak bir çelişkidir. Kaynak yazılıysa yeni
        # değer yok sayılıyor — ilk ölçüm korunuyor.
        yazilabilir = not self.komisyon_kaynagi
        return replace(
            self,
            durum=durum,
            borsa_kimligi=self.borsa_kimligi if borsa_kimligi is None else borsa_kimligi,
            dolan_miktar=self.dolan_miktar if dolan_miktar is None else dolan_miktar,
            ortalama_fiyat=(
                self.ortalama_fiyat if ortalama_fiyat is None else ortalama_fiyat
            ),
            komisyon=(
                komisyon if yazilabilir and komisyon is not None else self.komisyon
            ),
            komisyon_kaynagi=(
                komisyon_kaynagi
                if yazilabilir and komisyon_kaynagi
                else self.komisyon_kaynagi
            ),
            guncellendi_ms=zaman_ms,
            gecmis=(*self.gecmis, str(durum)),
            hata=hata or self.hata,
        )

    def sozluk(self) -> dict[str, Any]:
        return {
            "istemci_kimligi": self.istemci_kimligi,
            "sembol": self.sembol,
            "yon": self.yon,
            "tur": self.tur,
            "miktar": self.miktar,
            "limit_fiyati": self.limit_fiyati,
            "durum": str(self.durum),
            "borsa_kimligi": self.borsa_kimligi,
            "dolan_miktar": self.dolan_miktar,
            "kalan": self.kalan,
            "ortalama_fiyat": self.ortalama_fiyat,
            "karar_ms": self.karar_ms,
            "karar_utc": utc_str(self.karar_ms) if self.karar_ms else None,
            "olusturuldu_ms": self.olusturuldu_ms,
            "guncellendi_ms": self.guncellendi_ms,
            "gecmis": list(self.gecmis),
            "komisyon": [list(k) for k in self.komisyon],
            "komisyon_kaynagi": self.komisyon_kaynagi,
            "komisyon_bilinmiyor": self.komisyon_bilinmiyor,
            "hata": self.hata,
        }


def emir_kur(
    niyet: OnayliNiyet,
    miktar: float,
    *,
    zaman_ms: int,
    tur: str = "MARKET",
    limit_fiyati: float = 0.0,
) -> Emir:
    """Onaylı niyetten `CREATED` durumunda bir emir üretir.

    Miktar dışarıdan veriliyor: onaylı niyet **maruziyet** taşıyor, miktar değil. İkisi
    arasındaki çeviri fiyat gerektirir ve fiyat fill anında belli olur (`backtest/fill.py`
    ile aynı gerekçe).

    **`tur` ve `limit_fiyati` kimliğe girmiyor.** Kimlik yalnızca niyetin içeriğinden
    türüyor (`istemci_kimligi`), yani aynı niyet market olarak da limit olarak da
    gönderilse aynı kimliği alır ve ikincisi reddedilir. Bu istenen davranış: bir niyet
    bir emirdir. Türü kimliğe katmak, aynı kararın iki kez maruziyet üretmesine —
    "market denedim olmadı, limit de deneyeyim" — kapı açardı.
    """
    onayli = dogrula(niyet)
    return Emir(
        istemci_kimligi=istemci_kimligi(onayli),
        sembol=onayli.sinyal.symbol,
        yon=str(onayli.sinyal.side),
        tur=tur,
        miktar=miktar,
        limit_fiyati=limit_fiyati,
        karar_ms=onayli.karar_ms,
        olusturuldu_ms=zaman_ms,
        guncellendi_ms=zaman_ms,
        gecmis=(str(EmirDurumu.CREATED),),
    )


__all__ = [
    "ACIK",
    "EMIR_TURLERI",
    "GECISLER",
    "KIMLIK_ONEKI",
    "KIMLIK_UZUNLUGU",
    "KOMISYON_KAYNAKLARI",
    "NIHAI",
    "Emir",
    "EmirDurumu",
    "EmirHatasi",
    "GecersizGecis",
    "Komisyon",
    "emir_kur",
    "gecis_yasal_mi",
    "istemci_kimligi",
    "komisyon_topla",
]
