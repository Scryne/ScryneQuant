"""Borsa katmanının hata tipleri. (Faz 7)

**Neden `temel.py`den ayrı bir dosya.** `temel.py` pandas'a bağlı (bar sözleşmesi bir
`DataFrame` döndürüyor), ve `tests/unit/test_risk_bypass.py` `execution/` ile `oms/`
paketlerinin import kapanışında pandas'ı yasaklıyor. Emir yolundaki kod bu hataları
yakalamak zorunda; onları pandas taşıyan bir modülde bırakmak, emir katmanını veri
katmanının bağımlılıklarına zincirlerdi. `BorsaHatasi` `temel.py`den buraya taşındı ve
orada yeniden dışa veriliyor — mevcut importlar kırılmıyor.

**Hiyerarşinin şekli bir karardır, kolaylık değil.** `BelirsizSonuc` `BorsaHatasi`nın alt
sınıfı ama anlamı taban tabana zıt: diğer her hata *"olmadı"* der, o *"bilmiyorum"* der.
Alt sınıf olmasının sebebi, `except BorsaHatasi` yazan mevcut kodun onu **yakalaması** —
görmezden gelmemesi. Ayrı bir kök olsaydı, bugün doğru çalışan bir `try/except` yarın
sessizce belirsiz bir sonucu kaçırırdı.
"""

from __future__ import annotations


class BorsaHatasi(Exception):
    """Borsa katmanının dışarı verdiği tek hata tipi.

    Kütüphaneye özgü istisnalar (ccxt, requests) burada sarılır: üst katmanlar o
    kütüphaneleri import etmek zorunda kalmasın, ve borsa değiştiğinde hata yakalayan kod
    değişmesin.
    """


class BelirsizSonuc(BorsaHatasi):
    """İstek gönderildi, sonucu **bilinmiyor**. Emir borsada olabilir de olmayabilir de.

    Bu projedeki en tehlikeli hata sınıfı, çünkü en masum görüneni: bir timeout, bir
    kopan bağlantı. `EmirDurumu.UNKNOWN`un doğduğu yer burası.

    **Asla yeniden denenmez.** Yeniden denemek duplicate emir üretmenin en kısa yolu
    (`oms/emir.py`). Çıkış tek yoldan: borsaya sorup gerçek durumu öğrenmek (§25).

    Bir isteğin belirsiz sayılması, bayta dökülüp dökülmediğine bağlı: bağlantı
    kurulamadıysa istek hiç gitmemiştir ve bu **belirsiz değildir** (`GonderilemediHatasi`).
    Ayrımı adaptör yapar, çağıran değil — çağıranın unutabileceği bir ayrım, ayrım değildir.
    """


class GonderilemediHatasi(BorsaHatasi):
    """İstek **hiç gönderilemedi** — yani borsada emir olmadığı biliniyor.

    DNS çözülemedi, bağlantı kurulamadı, istek yerel doğrulamada kaldı. `EmirDurumu.FAILED`
    buraya karşılık gelir ve `BelirsizSonuc`un tersine **yeniden gönderilebilir**.
    """


class BorsaReddetti(BorsaHatasi):
    """Borsa emri açıkça reddetti (kural ihlali, bakiye yetersiz, duplicate kimlik).

    Kesin bilgi: emir yok. `kod` borsanın hata kodu (Binance `-2010` gibi), teşhis için
    saklanıyor — mesaj metni sürüme göre değişir, kod değişmez.
    """

    def __init__(self, mesaj: str, *, kod: int | None = None) -> None:
        super().__init__(mesaj)
        self.kod = kod


class SaatSapmasi(BorsaHatasi):
    """Yerel saat ile borsa saati arasındaki fark güvenli sınırı aştı.

    İmzalı istekler `timestamp` taşır ve borsa onu kendi saatiyle karşılaştırır; fark
    pencereyi aşarsa istek **sessizce** reddedilir (Binance `-1021`). "Sessizce" kelimesi
    burada kritik: emir gönderilmiş gibi görünüp hiç oluşmaz, ve sebep emir mantığında
    aranır. Bu yüzden sapma bir emir hatası olarak değil, **kendi tipiyle** raporlanıyor.
    """


__all__ = [
    "BelirsizSonuc",
    "BorsaHatasi",
    "BorsaReddetti",
    "GonderilemediHatasi",
    "SaatSapmasi",
]
