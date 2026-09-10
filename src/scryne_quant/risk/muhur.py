"""Onay mührü: bir niyetin gerçekten risk motorundan geçtiğinin kanıtı. (K-032)

**Bu modülün ne yaptığı ve ne yapmadığı konusunda net olmak gerekiyor.**

Python'da bir sınıfın dışarıdan kurulmasını *imkânsız* kılmanın yolu yok. `__init__`e
gizli bir anahtar koymak, modül-özel bir sentinel kullanmak, `__slots__` oyunları —
hiçbiri `risk.muhur._ANAHTAR` yazmayı engelleyemez. Bu gerçeği saklayıp "atlanamaz"
demek, K-003'ün "zorlanmayan kural temennidir" cümlesinin tersi olurdu.

O hâlde bu mühür neyi sağlıyor:

1. **Kazara atlamayı imkânsız kılıyor.** `execution` katmanına `Sinyal` vermek tip
   hatasıdır; mühürsüz bir `OnayliNiyet` kurmak çalışma zamanı hatasıdır. Yani "risk
   motorunu çağırmayı unutmak" diye bir hata biçimi yok — unutulursa kod çalışmaz.
2. **Onay sonrası değişikliği yakalıyor.** Mühür niyetin **içeriğinin** HMAC'i. Onaylı bir
   niyetin `target_exposure`ını büyütmek mührü geçersiz kılar; `execution` kapıda
   doğruladığı için o niyet borsaya gitmez. Risk motorunun "aşağı çekebilir, yukarı asla"
   kuralı böylece onay anıyla sınırlı kalmıyor, niyetin ömrü boyunca sürüyor.
3. **Kasıtlı atlamayı görünür kılıyor.** Anahtar bir modül globali değil, bir closure
   hücresinde. Ona ulaşmak `_imzala.__closure__[0].cell_contents` yazmak demek — yani
   niyet kazası değil, diff'te görünen, gözden geçirmede açıklanması gereken bir satır.

Üçüncüsü savunmanın tamamı değil; asıl zorlama `tests/unit/test_risk_bypass.py`'in statik
taramasında: `execution/` ve `oms/` paketlerinin `strategy.sinyal`e bağımlı olmadığı ve
dışa açık her giriş noktasının `OnayliNiyet` istediği `ast` ile kontrol ediliyor. K-003'ün
izolasyon testi hangi kalıbı kurduysa, bu onun risk tarafındaki ikizi.

**Anahtar süreç başına üretilir ve hiçbir yere yazılmaz.** Sonuç: mühür iki koşuda
farklıdır, dolayısıyla hiçbir hash'e, hiçbir sonuç kaydına, hiçbir audit satırına
girmez — girerse determinizm (K-009) kırılırdı. Mühür kalıcı bir kimlik değil, tek bir
sürecin içindeki bir taşıma güvencesi.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable
from hashlib import sha256
from typing import Final


class MuhurGecersiz(PermissionError):
    """Mühürsüz, bozulmuş ya da başka bir süreçte üretilmiş bir niyet sunuldu.

    `PermissionError` bilinçli: bu bir veri hatası değil, bir **yetki** hatası. Sunulan
    nesne iyi biçimli olabilir; olmayan şey risk motorunun onayı.
    """


def _kur() -> tuple[Callable[[bytes], str], Callable[[bytes, str], bool]]:
    """Anahtarı bir closure hücresine kapatıp imzala/doğrula çiftini üretir.

    Modül globali olarak tutulsaydı `risk.muhur._ANAHTAR` yazmak yeterli olurdu. Closure
    da aşılabilir, ama aşmak için yazılması gereken satır kazara yazılmaz.
    """
    anahtar = secrets.token_bytes(32)

    def imzala(icerik: bytes) -> str:
        return hmac.new(anahtar, icerik, sha256).hexdigest()

    def dogrula(icerik: bytes, muhur: str) -> bool:
        # `compare_digest`: mühür karşılaştırmasında erken çıkış yapmak zamanlama
        # sızıntısıdır. Bu projede saldırgan modeli yok ama doğru alışkanlığın maliyeti
        # de yok.
        return hmac.compare_digest(imzala(icerik), muhur)

    return imzala, dogrula


_imzala, _dogrula = _kur()

#: Mühürlenen içeriğin biçim sürümü. İçeriğin şekli değişirse bu artar ve eski mühürler
#: geçersiz olur — sessizce uyumlu görünmek, onayın neyi kapsadığını belirsizleştirirdi.
SURUM: Final = 1


def icerik_bytes(alanlar: tuple[object, ...]) -> bytes:
    """Mühürlenecek kanonik byte dizisi.

    Ayırıcı `\\x00`: alan değerlerinin içinde geçemeyen bir byte. Virgülle birleştirmek,
    iki farklı alan kümesinin aynı dizeye düşmesine ("a,b" + "c" vs "a" + "b,c") izin
    verirdi ve mühür o iki niyeti ayırt edemezdi.
    """
    return b"\x00".join([str(SURUM).encode(), *(repr(a).encode("utf-8") for a in alanlar)])


def muhurle(alanlar: tuple[object, ...]) -> str:
    """Alanların mührü. Yalnızca `risk/` içinden çağrılır."""
    return _imzala(icerik_bytes(alanlar))


def gecerli_mi(alanlar: tuple[object, ...], muhur: str) -> bool:
    """Mühür bu alanlara mı ait?"""
    return bool(muhur) and _dogrula(icerik_bytes(alanlar), muhur)


__all__ = ["SURUM", "MuhurGecersiz", "gecerli_mi", "icerik_bytes", "muhurle"]
