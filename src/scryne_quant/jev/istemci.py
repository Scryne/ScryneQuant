"""TypeSafe adaptörü: tek istek, sınıflandırılmış hata, sır sızdırmayan kayıt. (K-074/5, K-074/6)

**SDK yalnızca burada import edilir** (`test_jev_izolasyon.py`). Geri kalan her modül düz
sözlüklerle çalışır: durum sözlük, sorular sözlük (`sorular.py`), yanıt sözlük. Böylece
karar şeması, defter ve değerlendirme SDK sürümünden bağımsız test edilir ve `research/
gizli_tekrar.py`nin `Istemci` Protocol kalıbı aynen korunur (testte sahtesi geçer).

**Hata = karar yok.** Bu modül hiçbir durumda "varsayılan cevap" üretmez; `sor()` ya geçerli bir
yanıt sözlüğü ya da bir `KararDurumu` kodu + sebep döndürür. Retry SDK'nın kendi
`RetryPolicy`siyle, `config/jev.json::azami_deneme` kadar; sonrasında hâlâ hata varsa hata.
Önceki kararı taşıyacak bir durum bu modülde yoktur.

**Sır sızmaz.** Hata metinlerinden `TYPESAFE_API_KEY` değeri temizlenir; duruma ya da
sorulara herhangi bir sır girmediği kayıttan önce `sir_var_mi` ile taranır (spec §34).
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol

from scryne_quant.jev.ayarlar import JevAyarlari
from scryne_quant.jev.karar import KararDurumu
from scryne_quant.jev.sorular import SORULAR

#: Ortamda aranan sır değişkenleri. Değerleri kayda giremez; adları girebilir.
SIR_DEGISKENLERI: Final[tuple[str, ...]] = (
    "TYPESAFE_API_KEY",
    "SQ_BINANCE_API_KEY",
    "SQ_BINANCE_API_SECRET",
    "SQ_BINANCE_TESTNET_API_KEY",
    "SQ_BINANCE_TESTNET_API_SECRET",
)

#: Bu kadar kısa bir "sır" (boş, ya da tesadüfen metinde geçebilecek kadar kısa) taranmaz.
_ASGARI_SIR_UZUNLUGU: Final = 8


class Istemci(Protocol):
    """`typesafe_sdk.TypeSafeClient`in burada kullanılan yüzü."""

    def system_one(
        self, state: Any, questions: Mapping[str, Any], *, model: str | None = ...
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class SorguSonucu:
    yanit: dict[str, Any] | None
    """Düz yanıt: `{"model", "usage", "answers"}`. Hata varsa `None`."""

    durum: KararDurumu
    hata: str | None
    gecikme_ms: int


def _sirlar() -> tuple[str, ...]:
    return tuple(
        v
        for a in SIR_DEGISKENLERI
        if (v := os.environ.get(a, "")) and len(v) >= _ASGARI_SIR_UZUNLUGU
    )


def sir_temizle(metin: str) -> str:
    """Bilinen sır değerlerini metinden siler. Kayda giden her serbest metin buradan geçer."""
    for s in _sirlar():
        metin = metin.replace(s, "[SIR]")
    return metin


def sir_var_mi(nesne: Any) -> bool:
    """Bir sözlük/dizge içinde bilinen sır değerlerinden biri geçiyor mu?"""
    import json

    metin = nesne if isinstance(nesne, str) else json.dumps(nesne, ensure_ascii=False, default=str)
    return any(s in metin for s in _sirlar())


def typesafe_istemci(ayarlar: JevAyarlari) -> Any:
    """Uzun ömürlü gerçek istemci. Anahtar SDK tarafından ortamdan okunur; kod dokunmaz."""
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    return TypeSafeClient(
        timeout=ayarlar.timeout_s,
        retry=RetryPolicy(max_retries=max(0, ayarlar.azami_deneme - 1)),
    )


def _duz_yanit(yanit: Any) -> dict[str, Any]:
    """SDK yanıtını düz sözlüğe çevirir. Şema doğrulaması burada değil, `karar.py`de."""
    cevaplar: dict[str, Any] = {}
    for ad, c in dict(getattr(yanit, "answers", {}) or {}).items():
        d: dict[str, Any] = {}
        for alan in ("choice", "confidence", "probabilities", "score", "noul"):
            if hasattr(c, alan):
                deger = getattr(c, alan)
                d[alan] = dict(deger) if isinstance(deger, Mapping) else deger
        cevaplar[str(ad)] = d
    kullanim = getattr(yanit, "usage", None)
    return {
        "model": getattr(yanit, "model", None),
        "usage": {
            "input_tokens": getattr(kullanim, "input_tokens", None),
            "output_tokens": getattr(kullanim, "output_tokens", None),
        },
        "answers": cevaplar,
    }


def _siniflandir(e: BaseException) -> KararDurumu:
    """SDK istisnasını karar durumuna çevirir. Bilinmeyen her şey `API_HATASI`."""
    try:
        from typesafe_sdk import (
            TypeSafeAPITimeoutError,
            TypeSafeAuthenticationError,
            TypeSafePermissionDeniedError,
            TypeSafeRateLimitError,
        )
    except ImportError:  # pragma: no cover - SDK yoksa hepsi API hatası
        return KararDurumu.API_HATASI
    if isinstance(e, TypeSafeAPITimeoutError | TimeoutError):
        return KararDurumu.TIMEOUT
    if isinstance(e, TypeSafeAuthenticationError | TypeSafePermissionDeniedError):
        return KararDurumu.KIMLIK_HATASI
    if isinstance(e, TypeSafeRateLimitError):
        return KararDurumu.ORAN_SINIRI
    return KararDurumu.API_HATASI


def sor(istemci: Istemci, durum: Mapping[str, Any], ayarlar: JevAyarlari) -> SorguSonucu:
    """Kanonik durumu dondurulmuş soru setiyle Jev'e sorar. Asla fırlatmaz; sınıflandırır.

    Yanıtın şemaya uyup uymadığı burada bakılmaz (`karar.karar_kur` bakar); burada
    yalnızca "cevap geldi mi, gelmediyse neden" sorusu cevaplanır.
    """
    if sir_var_mi(durum):
        return SorguSonucu(None, KararDurumu.EKSIK_VERI, "durumda sır değeri var; gönderilmedi", 0)
    t0 = time.perf_counter()
    try:
        ham = istemci.system_one(dict(durum), SORULAR, model=ayarlar.model)
    except Exception as e:  # noqa: BLE001 - her hata sınıflandırılıp kayda gider
        gecikme = int((time.perf_counter() - t0) * 1000)
        return SorguSonucu(None, _siniflandir(e), sir_temizle(f"{type(e).__name__}: {e}"), gecikme)
    gecikme = int((time.perf_counter() - t0) * 1000)
    try:
        yanit = _duz_yanit(ham)
    except Exception as e:  # noqa: BLE001
        return SorguSonucu(
            None, KararDurumu.SEMA_HATASI, sir_temizle(f"yanıt okunamadı: {e}"), gecikme
        )
    return SorguSonucu(yanit, KararDurumu.GECERLI, None, gecikme)


__all__ = [
    "SIR_DEGISKENLERI",
    "Istemci",
    "SorguSonucu",
    "sir_temizle",
    "sir_var_mi",
    "sor",
    "typesafe_istemci",
]
