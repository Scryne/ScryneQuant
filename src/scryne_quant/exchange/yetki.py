"""Canlı yetki belirteci: gerçek parayla emir gönderen adaptörün tek anahtarı. (K-114)

`risk/muhur.py`nin execution tarafındaki ikizi ve aynı dürüstlükle yazılıyor: Python'da bir
nesnenin dışarıdan kurulmasını *imkânsız* kılmanın yolu yok. Bu modül üç şey sağlıyor:

1. **Kazara canlıya bağlanmayı imkânsız kılıyor.** `BinanceImzaliAdaptoru` testnet dışındaki
   her host için geçerli bir `CanliYetki` ister; yoksa kurulmaz. Yani bir yazım hatası,
   bir kopyala-yapıştır ya da "host'u değiştireyim bir bakayım" canlı borsaya emir
   göndermez — kurucuda patlar.
2. **Yetkiyi bir kanıta bağlıyor.** Belirteç, kendisini doğuran live-gate değerlendirmesinin
   hash'ini (`kanit_hash`) ve elle onayın hash'ini taşır; HMAC mühürlüdür ve süreç başına
   rastgele anahtarla imzalanır. Diskten okunan, başka süreçte üretilmiş ya da alanı
   değiştirilmiş bir belirteç geçersizdir — canlı yetki yeniden başlatmada **yeniden
   türetilir**, taşınmaz (K-038'in "geri yükleme değil yeniden üretim" ilkesi).
3. **Kasıtlı atlamayı görünür kılıyor.** `ver` yalnızca `execution/canli_kapi.py`den
   çağrılır ve bu `tests/unit/test_canli_izolasyon.py`de `ast` ile kontrol ediliyor. Başka
   bir yerden çağırmak testi kırar; kırılan test diff'te görünen bir satırdır.

Belirteç **hiçbir hash'e, hiçbir kayda girmez** (mühür gibi süreç başına rastgele).
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


class CanliYetkiGecersiz(PermissionError):
    """Canlı borsaya bağlanmak için geçerli bir yetki sunulmadı."""


def _kur() -> tuple[Callable[[bytes], str], Callable[[bytes, str], bool]]:
    anahtar = secrets.token_bytes(32)

    def imzala(icerik: bytes) -> str:
        return hmac.new(anahtar, icerik, sha256).hexdigest()

    def dogrula(icerik: bytes, imza: str) -> bool:
        return hmac.compare_digest(imzala(icerik), imza)

    return imzala, dogrula


_imzala, _dogrula = _kur()


@dataclass(frozen=True, slots=True)
class CanliYetki:
    """Canlı emir yetkisi. Yalnızca `ver()` üretir; alanları değişirse geçersizdir."""

    host: str
    """Yetkinin geçerli olduğu **tek** host (K-114 denetimi). Başka bir host'a kurulan adaptör
    bu yetkiyle kurulamaz — anahtarın yanlış/sahte bir uca gönderilmesi dahil."""

    kanit_hash: str
    """Yetkiyi doğuran live-gate raporunun (`execution/canli_kapi.py`) hash'i."""

    onay_hash: str
    """Elle onay kaydının satır hash'i."""

    strateji: str
    kademe: int
    sermaye_usdt: float
    """Bu yetkinin izin verdiği azami sermaye (kademe tablosundan, K-050/3)."""

    imza: str = ""

    def __reduce__(self) -> Any:
        # Serileştirme yok: yetki bir sürecin içinde doğar ve orada ölür (diske/kuyruğa
        # yazılamaz). Başka süreçte zaten geçersiz; bu, denemeyi görünür bir hataya çevirir.
        raise TypeError("CanliYetki serileştirilemez (K-114)")

    def _icerik(self) -> bytes:
        return "\x00".join(
            (
                self.host.rstrip("/"),
                self.kanit_hash,
                self.onay_hash,
                self.strateji,
                str(self.kademe),
                repr(float(self.sermaye_usdt)),
            )
        ).encode("utf-8")

    @property
    def gecerli(self) -> bool:
        return bool(self.imza) and _dogrula(self._icerik(), self.imza)


def ver(
    *,
    host: str,
    kanit_hash: str,
    onay_hash: str,
    strateji: str,
    kademe: int,
    sermaye_usdt: float,
) -> CanliYetki:
    """Mühürlü yetki üretir. **Yalnızca `execution/canli_kapi.py` çağırır** (AST testi)."""
    if kademe < 1 or sermaye_usdt <= 0.0:
        raise CanliYetkiGecersiz(
            f"canlı yetki kademe ≥ 1 ve pozitif sermaye ister: kademe={kademe}, "
            f"sermaye={sermaye_usdt}"
        )
    ham = CanliYetki(
        host=host.rstrip("/"),
        kanit_hash=kanit_hash,
        onay_hash=onay_hash,
        strateji=strateji,
        kademe=kademe,
        sermaye_usdt=float(sermaye_usdt),
    )
    return CanliYetki(
        host=ham.host,
        kanit_hash=ham.kanit_hash,
        onay_hash=ham.onay_hash,
        strateji=ham.strateji,
        kademe=ham.kademe,
        sermaye_usdt=ham.sermaye_usdt,
        imza=_imzala(ham._icerik()),
    )


def dogrula(yetki: object, *, host: str | None = None) -> CanliYetki:
    """Adaptör kurucularının çağırdığı doğrulayıcı. Geçmeyen her şey `CanliYetkiGecersiz`.

    `host` verilirse yetkinin host'uyla birebir aynı olmalı.
    """
    if not isinstance(yetki, CanliYetki) or not yetki.gecerli:
        raise CanliYetkiGecersiz(
            "canlı borsa host'u geçerli bir CanliYetki olmadan kullanılamaz (K-114). Yetki "
            "yalnızca live gate'in bütün kontrolleri geçip elle onay verildiğinde üretilir; "
            "`sq execution preflight` eksikleri listeler."
        )
    if host is not None and host.rstrip("/") != yetki.host:
        raise CanliYetkiGecersiz(
            f"canlı yetki {yetki.host} için; {host} host'una kurulum reddedildi (K-114)"
        )
    return yetki


__all__ = ["CanliYetki", "CanliYetkiGecersiz", "dogrula", "ver"]
