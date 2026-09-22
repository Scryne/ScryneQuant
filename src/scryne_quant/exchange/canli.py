"""Canlı Binance spot: host, anahtarlar, anahtar yetki denetimi, canlı adaptörler. (K-114)

Faz-8-Hazirlik §1.3/2'nin modülü: canlı host `imzali.py`de değil **burada** tanımlı ve bu
modülü yalnızca shadow/live giriş noktaları import edebilir
(`tests/unit/test_canli_izolasyon.py`: `backtest/`, `research/`, `strategy/`, `live/`,
`risk/`, `oms/`, `data/`, `features/`, `portfolio/`, `jev/` import edemez).

**İki anahtar, iki yetki, iki kurulum (Faz-8-Hazirlik §1.2, §1.6):**

- **shadow / izleme:** `BINANCE_API_KEY` / `_SECRET`; işlem **kapalı**, çekim kapalı;
  `okuma_anahtari_oku()` ile açıkça okunur.
- **live:** `SQ_BINANCE_LIVE_API_KEY` / `_SECRET`; spot işlem açık, çekim kapalı, **IP
  kısıtlı**, margin/futures kapalı; `islem_anahtari_oku(yetki)` — **yalnızca geçerli
  `CanliYetki` ile**.

**Anahtar yetkisi koddan önce gelir.** Başlangıçta `GET /sapi/v1/account/apiRestrictions`
çekilir ve mod ile yetki uyuşmazsa kurulum **başlamaz** (`yetki_denetle`). Shadow işlem
yetkili bir anahtarla açılamaz: kod bir yazım hatasıyla emir yolunu açsa bile borsa
`-2015` ile reddeder. Canlı, çekim yetkili ya da IP kısıtsız bir anahtarla açılamaz.

**İşlem anahtarı kendiliğinden okunmaz.** `islem_anahtari_oku` geçerli bir `CanliYetki`
ister; yetki yalnızca live gate'in bütün kontrolleri geçip elle onay verildiğinde üretilir
(`execution/canli_kapi.py`). `.env`de işlem anahtarı dursa bile, onay olmadan hiçbir kod
yolu onu okuyamaz.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlencode

import requests

from scryne_quant.exchange import yetki as yetki_mod
from scryne_quant.exchange.hatalar import BorsaHatasi
from scryne_quant.exchange.imzali import BinanceImzaliAdaptoru, Transport

#: Binance spot canlı REST host'u. Yalnızca bu modülde.
CANLI_HOST: Final = "https://api.binance.com"

OKUMA_ANAHTARI: Final = "BINANCE_API_KEY"
OKUMA_SIRRI: Final = "BINANCE_API_SECRET"
ISLEM_ANAHTARI: Final = "SQ_BINANCE_LIVE_API_KEY"
ISLEM_SIRRI: Final = "SQ_BINANCE_LIVE_API_SECRET"

#: `apiRestrictions` alanlarının mod başına beklenen değeri. `None` = bakılmaz.
#: Tablo Faz-8-Hazirlik §1.2'nin birebir makine hâli; gevşetmek yeni bir K ister.
YETKI_TABLOSU: Final[dict[str, dict[str, bool | None]]] = {
    "shadow": {
        "enableReading": True,
        "enableSpotAndMarginTrading": False,
        "enableWithdrawals": False,
        "enableInternalTransfer": False,
        "enableMargin": False,
        "enableFutures": False,
        "permitsUniversalTransfer": False,
        "enableVanillaOptions": False,
        "enablePortfolioMarginTrading": False,
        "ipRestrict": None,
    },
    "live": {
        "enableReading": True,
        "enableSpotAndMarginTrading": True,
        "enableWithdrawals": False,
        "enableInternalTransfer": False,
        "enableMargin": False,
        "enableFutures": False,
        "permitsUniversalTransfer": False,
        "enableVanillaOptions": False,
        "enablePortfolioMarginTrading": False,
        "ipRestrict": True,
    },
}


class AnahtarYetkisiUyusmuyor(PermissionError):
    """Anahtarın borsadaki yetkisi modun gerektirdiğiyle uyuşmuyor. Kurulum başlamaz."""

    def __init__(self, mod: str, ihlaller: list[str]) -> None:
        super().__init__(
            f"{mod} modu için anahtar yetkisi uyuşmuyor: {'; '.join(ihlaller)} "
            f"(Faz-8-Hazirlik §1.2, K-114)"
        )
        self.mod = mod
        self.ihlaller = ihlaller


def _env_oku(ad: str, env_dosyasi: str | Path | None) -> str:
    deger = os.environ.get(ad, "")
    if deger:
        return deger
    yol = Path(env_dosyasi) if env_dosyasi else None
    if yol is not None and yol.is_file():
        for ham in yol.read_text(encoding="utf-8").splitlines():
            satir = ham.strip()
            if satir.startswith("#") or "=" not in satir:
                continue
            k, _, v = satir.partition("=")
            if k.strip() == ad:
                return v.strip().strip("\"'")
    return ""


def okuma_anahtari_oku(env_dosyasi: str | Path | None = ".env") -> tuple[str, str]:
    """Salt okunur canlı anahtar (shadow, izleme). Yetkisi `yetki_denetle` ile sınanır."""
    anahtar, sir = _env_oku(OKUMA_ANAHTARI, env_dosyasi), _env_oku(OKUMA_SIRRI, env_dosyasi)
    if not anahtar or not sir:
        raise BorsaHatasi(
            f"salt okunur canlı anahtar yok: {OKUMA_ANAHTARI}/{OKUMA_SIRRI} ortamda ya da "
            f".env'de olmalı. Anahtar **işlem kapalı** üretilir (Faz-8-Hazirlik §1.2)."
        )
    return anahtar, sir


def islem_anahtari_oku(
    yetki: yetki_mod.CanliYetki, env_dosyasi: str | Path | None = ".env"
) -> tuple[str, str]:
    """İşlem yetkili canlı anahtar. **Geçerli `CanliYetki` olmadan okunamaz** (K-114)."""
    yetki_mod.dogrula(yetki)
    anahtar, sir = _env_oku(ISLEM_ANAHTARI, env_dosyasi), _env_oku(ISLEM_SIRRI, env_dosyasi)
    if not anahtar or not sir:
        raise BorsaHatasi(
            f"işlem anahtarı yok: {ISLEM_ANAHTARI}/{ISLEM_SIRRI}. Anahtar elle onaydan "
            f"**sonra** üretilir: spot işlem açık, çekim/transfer/margin/futures kapalı, IP "
            f"kısıtlı (Faz-8-Hazirlik §1.6)."
        )
    return anahtar, sir


def api_kisitlari(
    anahtar: str,
    sir: str,
    *,
    oturum: Transport | None = None,
    zaman_ms: int,
) -> dict[str, Any]:
    """`GET /sapi/v1/account/apiRestrictions` — anahtarın borsadaki yetkileri.

    Tek imzalı GET; yazma yok. `zaman_ms` borsa saati olmalı (çağıran `SaatSenkronu`ndan
    ya da `/api/v3/time`dan alır).
    """
    sorgu = urlencode({"recvWindow": 5_000, "timestamp": int(zaman_ms)})
    imza = hmac.new(sir.encode(), sorgu.encode(), hashlib.sha256).hexdigest()
    url = f"{CANLI_HOST}/sapi/v1/account/apiRestrictions?{sorgu}&signature={imza}"
    if oturum is None:
        s = requests.Session()
        s.headers["X-MBX-APIKEY"] = anahtar
        oturum = s
    try:
        yanit = oturum.request("GET", url, timeout=15.0)
    except requests.exceptions.RequestException as hata:
        raise BorsaHatasi(f"apiRestrictions okunamadı: {hata}") from hata
    if yanit.status_code != 200:
        raise BorsaHatasi(f"apiRestrictions {yanit.status_code}: {yanit.text[:200]}")
    govde = yanit.json()
    if not isinstance(govde, dict):
        raise BorsaHatasi(f"apiRestrictions beklenmeyen gövde: {str(govde)[:200]}")
    return govde


def yetki_ihlalleri(mod: str, kisitlar: dict[str, Any]) -> list[str]:
    """Modun tablosuna göre ihlal listesi. Boş liste = uyumlu.

    Tabloda olup yanıtta **olmayan** alan da ihlaldir: borsanın söylemediği bir yetkiyi
    "herhalde kapalıdır" saymak, ölçülmemiş bir şeyi ölçülmüş saymaktır.
    """
    try:
        tablo = YETKI_TABLOSU[mod]
    except KeyError as hata:
        raise ValueError(f"yetki tablosunda olmayan mod: {mod!r}") from hata
    ihlaller: list[str] = []
    for alan, beklenen in tablo.items():
        if beklenen is None:
            continue
        if alan not in kisitlar:
            ihlaller.append(f"{alan} yanıtta yok (beklenen {beklenen})")
        elif bool(kisitlar[alan]) is not beklenen:
            ihlaller.append(f"{alan}={kisitlar[alan]} (beklenen {beklenen})")
    return ihlaller


def yetki_denetle(mod: str, kisitlar: dict[str, Any]) -> None:
    """İhlal varsa `AnahtarYetkisiUyusmuyor`. Kurulumların ilk satırı."""
    ihlaller = yetki_ihlalleri(mod, kisitlar)
    if ihlaller:
        raise AnahtarYetkisiUyusmuyor(mod, ihlaller)


def canli_okuyucu(
    anahtar: str, sir: str, *, oturum: Transport | None = None
) -> BinanceImzaliAdaptoru:
    """Canlı hesaba **salt okunur** imzalı adaptör (shadow, izleme). Yazma taşımada reddedilir."""
    return BinanceImzaliAdaptoru(
        anahtar=anahtar, sir=sir, host=CANLI_HOST, oturum=oturum, salt_okunur=True
    )


def canli_iptal_adaptoru(
    env_dosyasi: str | Path | None = ".env", *, oturum: Transport | None = None
) -> BinanceImzaliAdaptoru:
    """Acil iptal için canlı adaptör: okuma + iptal, **emir açamaz** (taşımada POST yok).

    Kill ve acil iptal, live gate'i geçemeyen bir anda (halt, kopukluk) da çalışmak zorunda;
    iptal riski azaltır (K-050). İşlem anahtarı bu fonksiyonun **içinde** okunur ve yalnızca
    yalnız-iptal kurulumuna verilir — dışarıya anahtar dönmez.
    """
    anahtar, sir = _env_oku(ISLEM_ANAHTARI, env_dosyasi), _env_oku(ISLEM_SIRRI, env_dosyasi)
    if not anahtar or not sir:
        raise BorsaHatasi(f"acil iptal için işlem anahtarı yok ({ISLEM_ANAHTARI})")
    return BinanceImzaliAdaptoru(
        anahtar=anahtar, sir=sir, host=CANLI_HOST, oturum=oturum, yalniz_iptal=True
    )


def islem_anahtari_kisitlari(
    env_dosyasi: str | Path | None = ".env",
    *,
    zaman_ms: int,
    oturum: Transport | None = None,
) -> dict[str, Any]:
    """İşlem anahtarının `apiRestrictions`ı — live gate'in anahtar kontrolü için.

    Anahtar okunur, **yalnızca** bu GET için kullanılır ve dışarıya dönmez; dönen şey
    borsanın yetki beyanıdır. Yetki (emir) üretmez.
    """
    anahtar, sir = _env_oku(ISLEM_ANAHTARI, env_dosyasi), _env_oku(ISLEM_SIRRI, env_dosyasi)
    if not anahtar or not sir:
        raise BorsaHatasi(f"işlem anahtarı yok ({ISLEM_ANAHTARI}); elle onaydan sonra üretilir")
    return api_kisitlari(anahtar, sir, oturum=oturum, zaman_ms=zaman_ms)


def canli_emir_adaptoru(
    yetki: yetki_mod.CanliYetki,
    anahtar: str,
    sir: str,
    *,
    oturum: Transport | None = None,
) -> BinanceImzaliAdaptoru:
    """Canlı hesaba emir gönderen adaptör. **Geçerli `CanliYetki` olmadan kurulamaz.**

    Anahtar yetkisi burada ayrıca denetlenmez; denetim live gate'in kontrol listesinde
    (`canli_kapi.anahtar_kontrolu`) yetki üretilmeden **önce** yapılır ve yetkinin
    `kanit_hash`i o raporu taşır.
    """
    return BinanceImzaliAdaptoru(
        anahtar=anahtar, sir=sir, host=CANLI_HOST, oturum=oturum, canli_yetki=yetki
    )


__all__ = [
    "CANLI_HOST",
    "ISLEM_ANAHTARI",
    "ISLEM_SIRRI",
    "OKUMA_ANAHTARI",
    "OKUMA_SIRRI",
    "YETKI_TABLOSU",
    "AnahtarYetkisiUyusmuyor",
    "api_kisitlari",
    "canli_emir_adaptoru",
    "canli_iptal_adaptoru",
    "canli_okuyucu",
    "islem_anahtari_kisitlari",
    "islem_anahtari_oku",
    "okuma_anahtari_oku",
    "yetki_denetle",
    "yetki_ihlalleri",
]
