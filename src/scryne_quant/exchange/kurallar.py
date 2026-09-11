"""Sembolün emir kuralları ve onlara uydurma. (Faz 7, K-007)

`SembolKurallari` Faz 1'de `temel.py`de tanımlanmıştı ve yalnızca kaydediliyordu. Faz 7'de
emir yolunun onu **kullanması** gerekiyor (`EmirDurumu.VALIDATED` tam olarak bu kontrol),
ama `temel.py` pandas'a bağlı ve `oms/`+`execution/` kapanışında pandas yasak
(`test_risk_bypass.py`). Tip buraya taşındı, `temel.py` yeniden dışa veriyor.

**Yuvarlama yönü bir karardır, ayrıntı değil (K-007).** Miktar her zaman **aşağı**
yuvarlanır: istenen 0,001234 BTC ve adım 0,00001 ise 0,00123 gönderilir, 0,00124 değil.
Gerekçe slippage kuralının aynısı — belirsizlikte aleyhte yuvarla. Yukarı yuvarlamak,
risk motorunun onayladığı maruziyetin **üstüne** çıkmak demektir; onay bir tavandır, hedef
değil. Aşağı yuvarlamanın bedeli birkaç satoshi eksik işlem, yukarı yuvarlamanınki
onaylanmamış risk.

**Fiyat (tick) yuvarlaması yöne bağlıdır ve Faz 7'de bilerek yoktu** — o faz market emri
kullanıyordu, limit fiyatı göndermiyordu. Limit yolu açılınca (K-047) yazıldı ve yönü
miktarınkiyle **aynı ilkeden** türüyor: emir, istenenden daha saldırgan olamaz.

| Yön | Yuvarlama | Sonuç |
| --- | --- | --- |
| BUY | **aşağı** | İstenenden yüksek fiyat teklif edilmez |
| SELL | **yukarı** | İstenenden düşük fiyata satılmaz |

Bedeli dolmama ihtimali, ve bu **bilinçli bir tercih**: dolmayan bir emir görünür — defterde
`ACKNOWLEDGED` olarak durur, iptal edilebilir, raporda sayılır. Oysa bir tick kötüye
yuvarlanmış bir fill sessizdir: emir dolar, kayıt temiz görünür, ve fark yalnızca uzun
vadeli maliyet hesabında ortaya çıkar. Bu projede gürültülü hata, sessiz hataya yeğdir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class KuralIhlali(ValueError):
    """Emir sembolün kurallarını sağlamıyor. Borsaya **gönderilmeden** yakalanır.

    Borsanın da reddedeceği bir isteği göndermek saf risk: yanıt kaybolursa emrin
    oluşmadığını bilmemize rağmen `UNKNOWN`a düşeriz (`hatalar.BelirsizSonuc`). Yerel
    kontrol o riski hiç almamaktır.
    """


@dataclass(frozen=True, slots=True)
class SembolKurallari:
    """Bir sembolün emir kuralları.

    Spike 1'de BTCUSDT için ölçülen: tick 0,01 · step 0,00001 · minNotional 5,00.
    """

    sembol: str
    tick_size: float
    step_size: float
    min_notional: float
    durum: str

    taban_varlik: str = ""
    """`BTCUSDT`in `BTC`si — emirde **miktarı** ölçülen varlık."""

    kote_varlik: str = ""
    """`BTCUSDT`in `USDT`si — emirde **fiyatı** ölçülen varlık.

    İkisi de borsanın `exchangeInfo` yanıtından geliyor, sembol adı **kesilerek değil**.
    "USDT ile biter" kuralı BTCUSDT'de doğru çalışır ve BNBBTC'de sessizce yanlış cevap
    verir; pozisyon mutabakatı hangi varlığın arttığını bu iki alandan öğreniyor, o yüzden
    burada bir tahmin bir muhasebe hatasına doğrudan dönüşürdü. Faz 1'in veri tarafı bu
    alanları doldurmuyor (ihtiyacı yok) — boşluğu pozisyon mutabakatı yüksek sesle
    reddediyor, sessizce varsaymıyor.
    """

    @property
    def islenebilir(self) -> bool:
        return self.durum == "TRADING"


def miktar_uydur(miktar: float, step_size: float) -> float:
    """Miktarı lot adımına **aşağı** yuvarlar (K-007).

    `math.floor(miktar / step)` kayan nokta yüzünden tam katlarda bir adım aşağı düşebilir
    (0,3/0,1 = 2,9999...). Bölümü adım hassasiyetinde yuvarlayıp sonra taban almak bunu
    kapatıyor: tam kat tam kat kalır, arada kalan aşağı iner.
    """
    if step_size <= 0.0:
        raise KuralIhlali(f"step_size pozitif olmalı: {step_size}")
    if miktar < 0.0:
        raise KuralIhlali(f"miktar negatif olamaz: {miktar}")
    adim = round(miktar / step_size, 9)
    return math.floor(adim) * step_size


def fiyat_uydur(fiyat: float, tick_size: float, *, yon: str) -> float:
    """Limit fiyatını tick'e uydurur; **yön bağımlı** (modül docstring'indeki tablo).

    `BUY` aşağı, `SELL`/`FLAT` yukarı yuvarlanır — yani emir hiçbir zaman istenenden
    saldırgan olmaz. `miktar_uydur`daki aynı kayan nokta önlemi burada da var: bölümü
    tick hassasiyetinde yuvarlayıp sonra taban/tavan almak, tam katların bir tick
    kaymasını engelliyor.
    """
    if tick_size <= 0.0:
        raise KuralIhlali(f"tick_size pozitif olmalı: {tick_size}")
    if fiyat <= 0.0:
        raise KuralIhlali(f"limit fiyatı pozitif olmalı: {fiyat}")

    adim = round(fiyat / tick_size, 9)
    if yon.upper() == "BUY":
        return math.floor(adim) * tick_size
    return math.ceil(adim) * tick_size


def fiyat_metni(fiyat: float, tick_size: float) -> str:
    """Uydurulmuş fiyatın borsaya gidecek metin hâli. `miktar_metni` ile aynı gerekçe."""
    return f"{fiyat:.{basamak(tick_size)}f}"


def basamak(step_size: float) -> int:
    """Adımın ondalık basamak sayısı — borsaya gönderilecek metnin biçimi için.

    Binance `quantity` alanını metin olarak alır ve fazla basamak `-1111` ile reddedilir.
    `repr` üzerinden sayılıyor çünkü `0.00001` float olarak tam değil; `repr` Python'un
    en kısa doğru gösterimini verir ve adım değerleri borsadan zaten kısa gelir.
    """
    metin = repr(float(step_size))
    if "e" in metin or "E" in metin:
        return max(0, -int(metin.split("e")[-1].split("E")[-1]))
    _, _, kesir = metin.partition(".")
    return len(kesir.rstrip("0"))


def miktar_metni(miktar: float, step_size: float) -> str:
    """Uydurulmuş miktarın borsaya gidecek metin hâli. Bilimsel gösterim üretmez."""
    return f"{miktar:.{basamak(step_size)}f}"


def emri_dogrula(
    kurallar: SembolKurallari, miktar: float, *, referans_fiyat: float
) -> float:
    """Miktarı kurallara uydurup döndürür; sağlanamıyorsa `KuralIhlali`.

    `referans_fiyat` yalnızca `minNotional` kontrolü için — market emrinde gerçek fiyat
    fill anında belli olur, o yüzden bu kontrol **tahminî** ve bilerek muhafazakâr: sınıra
    çok yakın bir emir borsada reddedilebilir, ve reddedilen emir gönderilmemiş emirden
    daha pahalıdır (bkz. `KuralIhlali`).
    """
    if not kurallar.islenebilir:
        raise KuralIhlali(f"{kurallar.sembol} işleme kapalı: {kurallar.durum}")
    uydurulmus = miktar_uydur(miktar, kurallar.step_size)
    if uydurulmus <= 0.0:
        raise KuralIhlali(
            f"{kurallar.sembol}: miktar lot adımının altında "
            f"({miktar} < step {kurallar.step_size})"
        )
    notional = uydurulmus * referans_fiyat
    if notional < kurallar.min_notional:
        raise KuralIhlali(
            f"{kurallar.sembol}: notional {notional:.2f} < minNotional "
            f"{kurallar.min_notional:.2f} (miktar {uydurulmus}, fiyat {referans_fiyat})"
        )
    return uydurulmus


__all__ = [
    "KuralIhlali",
    "SembolKurallari",
    "basamak",
    "emri_dogrula",
    "fiyat_metni",
    "fiyat_uydur",
    "miktar_metni",
    "miktar_uydur",
]
