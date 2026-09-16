"""Binance açık veri arşivi (`data.binance.vision`): liste, indirme, checksum, CSV. (Faz 9)

REST adaptörü (`exchange/binance.py`) tek sembolün yakın geçmişi için kuruldu; çoklu sembol
evreni için doğru kaynak arşiv. Spike 6 ölçtü: delist edilmiş 192 sembolün 191'inin 1h
geçmişi burada duruyor, REST'te durmuyor. Hayatta kalma yanlılığı olmayan bir evren (K-052/3)
ancak bu kaynaktan kurulabilir.

**Ölçülen ve burada kural hâline getirilen dört şey** (2026-09-15, BTCUSDT/LUNAUSDT örnekleri):

1. **Zaman birimi 2025-01'de değişti.** 2024-12 dosyasının ilk `open_time`'ı
   `1733011200000` (ms), 2025-01'inki `1735689600000000` (**µs**). Aynı sütun adı, aynı
   dosya düzeni, 1000 kat fark. Okuyan kod bunu bilmezse seri iki parçaya ayrılmaz — 2025
   sonrası barlar 55.000 yıl sonrasına düşer, sıralama ve boşluk hesabı sessizce bozulur.
   Birim sayının büyüklüğünden çıkarılır ve **dosya içinde karışık birim reddedilir.**
2. **CSV'de başlık satırı yok** ve sütunlar REST kline dizisiyle aynı sırada (12 alan).
3. **`.CHECKSUM` dosyası zip'in SHA-256'sı.** Beş örnekte beşi eşleşti. Checksum'ı olmayan
   ya da eşleşmeyen dosya **kabul edilmez**: doğrulanamayan veri depoya girmez.
4. **Arşiv REST'in birebir kopyası değil — ama neredeyse.** Önce ayrıştırma: pandas'ın
   varsayılan hızlı float ayrıştırıcısı 744 satırlık bir ayda 50 `quote_volume` değerini
   2,4e-7 kaydırdı; `float_precision="round_trip"` ile beş örnek ayda fark sıfır. Kaydırma
   önemsiz görünür ama veri seti kimliği dosyanın hash'i (K-009): aynı veri iki farklı
   kimlik alırdı. Sonra kaynak: BTCUSDT 1h'in REST'le ortak **45.576 barının 4'ünde**
   (2021-12-24 03:00/04:00, 2021-12-27 07:00, 2022-04-13 05:00) değerler gerçekten farklı —
   hacim en çok %1,8, işlem sayısı en çok 767, iki kapanış en çok 0,06. Hangisinin doğru
   olduğu bilinmiyor; bu yüzden iki kaynak **karıştırılmaz**: evren arşivden, `data/market`
   REST'ten kalır (bkz. `data/arsiv_indirici.py`).
"""

from __future__ import annotations

import hashlib
import io
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from abc import ABC, abstractmethod
from typing import Final

import pandas as pd
import requests

from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI, HAM_PANDAS_DTYPES
from scryne_quant.exchange.binance import ipv4_zorla

ARSIV_HOST: Final = "https://data.binance.vision"

#: Arşivin S3 listeleme ucu. `data.binance.vision` kendi başına dizin listesi vermiyor;
#: liste bu kovadan okunuyor (Spike 6).
S3_HOST: Final = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"

SPOT_KLINE_ONEKI: Final = "data/spot"

TIMEOUT_S: Final = 60.0
DENEME_SAYISI: Final = 5
BEKLEME_TABANI_S: Final = 1.0

#: Arşiv CSV'sinin 12 alanı, REST kline dizisiyle aynı sırada. Kullanılmayanlar
#: (close_time, taker_*, ignore) okunmuyor.
_CSV_ALANLARI: Final[tuple[str, ...]] = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_base",
    "taker_quote",
    "ignore",
)

#: ms ile µs'i ayıran sınır. Bugünün epoch ms'i ~1,8e12, µs'i ~1,8e15. 1e14 ms, 5138
#: yılına denk gelir; µs olarak 1973'e. İki birimin gerçekçi aralıkları bu sınırın iki
#: yanında üç mertebe boşlukla ayrılıyor.
MIKROSANIYE_SINIRI: Final = 10**14

_AY_DOSYASI = re.compile(r"-(\d{4}-\d{2})\.zip$")
_GUN_DOSYASI = re.compile(r"-(\d{4}-\d{2}-\d{2})\.zip$")


class ArsivHatasi(Exception):
    """Arşiv sözleşmesinin ihlali: doğrulanamayan, ayrıştırılamayan veya eksik dosya."""


# ------------------------------------------------------------------ kaynak


class ArsivKaynagi(ABC):
    """Arşive erişim sözleşmesi. Testler ağa çıkmadan bunun sahtesiyle çalışır."""

    @abstractmethod
    def listele(self, onek: str) -> tuple[list[str], list[str]]:
        """`onek` altındaki (alt önekler, anahtarlar). Sayfalama içeride yapılır."""

    @abstractmethod
    def getir(self, anahtar: str) -> bytes | None:
        """Dosyanın baytları; dosya yoksa `None`. Ağ hatası `ArsivHatasi`."""


class HttpArsiv(ArsivKaynagi):
    """Gerçek arşiv. IPv4 zorlanır (Spike 1/3: `*.binance.vision` AAAA sorgusu ~12 s)."""

    def __init__(self, *, timeout_s: float = TIMEOUT_S, havuz: int = 32) -> None:
        ipv4_zorla()
        self._oturum = requests.Session()
        adaptor = requests.adapters.HTTPAdapter(pool_connections=havuz, pool_maxsize=havuz)
        self._oturum.mount("https://", adaptor)
        self._timeout_s = timeout_s

    def _istek(self, url: str, params: dict[str, str] | None = None) -> requests.Response:
        son: Exception | None = None
        for deneme in range(DENEME_SAYISI):
            try:
                yanit = self._oturum.get(url, params=params, timeout=self._timeout_s)
                if yanit.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {yanit.status_code}")
                return yanit
            except requests.RequestException as hata:
                son = hata
                if deneme + 1 < DENEME_SAYISI:
                    time.sleep(BEKLEME_TABANI_S * (2**deneme))
        raise ArsivHatasi(f"{url}: {DENEME_SAYISI} denemede başarısız: {son}") from son

    def listele(self, onek: str) -> tuple[list[str], list[str]]:
        onekler: list[str] = []
        anahtarlar: list[str] = []
        isaret = ""
        while True:
            yanit = self._istek(S3_HOST, {"prefix": onek, "delimiter": "/", "marker": isaret})
            if yanit.status_code != 200:
                raise ArsivHatasi(f"listeleme {onek}: HTTP {yanit.status_code}")
            kok = ET.fromstring(yanit.content)
            ns = {"s3": kok.tag.split("}")[0].strip("{")} if kok.tag.startswith("{") else {}
            p = "s3:" if ns else ""
            yeni_onek = [e.text or "" for e in kok.findall(f"{p}CommonPrefixes/{p}Prefix", ns)]
            yeni_anahtar = [e.text or "" for e in kok.findall(f"{p}Contents/{p}Key", ns)]
            onekler += [x for x in yeni_onek if x != onek]
            anahtarlar += yeni_anahtar
            kesik = kok.findtext(f"{p}IsTruncated", default="false", namespaces=ns)
            if kesik != "true":
                return onekler, anahtarlar
            sonraki = kok.findtext(f"{p}NextMarker", default="", namespaces=ns)
            isaret = sonraki or max([*yeni_anahtar, *yeni_onek])

    def getir(self, anahtar: str) -> bytes | None:
        yanit = self._istek(f"{ARSIV_HOST}/{anahtar}")
        if yanit.status_code == 404:
            return None
        if yanit.status_code != 200:
            raise ArsivHatasi(f"{anahtar}: HTTP {yanit.status_code}")
        return yanit.content


# ------------------------------------------------------------------ yollar


def ay_oneki(sembol: str, timeframe: str) -> str:
    return f"{SPOT_KLINE_ONEKI}/monthly/klines/{sembol.upper()}/{timeframe}/"


def gun_oneki(sembol: str, timeframe: str) -> str:
    return f"{SPOT_KLINE_ONEKI}/daily/klines/{sembol.upper()}/{timeframe}/"


def spot_sembolleri(kaynak: ArsivKaynagi) -> list[str]:
    """Arşivde aylık kline klasörü olan tüm spot semboller, sıralı.

    Filtre **yok**: kaldıraçlı token, stablecoin, fiat paritesi hepsi döner. Hangi
    sembolün evrene gireceği bir evren kuralıdır (K-051/4: evren tanımı bir çekiliştir);
    veri katmanı o kararı sessizce önceden vermemeli.
    """
    onekler, _ = kaynak.listele(f"{SPOT_KLINE_ONEKI}/monthly/klines/")
    return sorted({o.rstrip("/").rsplit("/", 1)[-1] for o in onekler})


def zip_anahtarlari(anahtarlar: list[str], desen: re.Pattern[str]) -> dict[str, str]:
    """Anahtar listesinden `{dönem: zip anahtarı}`; CHECKSUM dosyaları ayıklanır."""
    out: dict[str, str] = {}
    for a in anahtarlar:
        eslesme = desen.search(a)
        if eslesme:
            out[eslesme.group(1)] = a
    return dict(sorted(out.items()))


def aylik_dosyalar(kaynak: ArsivKaynagi, sembol: str, timeframe: str) -> dict[str, str]:
    """`{YYYY-MM: anahtar}`."""
    _, anahtarlar = kaynak.listele(ay_oneki(sembol, timeframe))
    return zip_anahtarlari(anahtarlar, _AY_DOSYASI)


def gunluk_dosyalar(kaynak: ArsivKaynagi, sembol: str, timeframe: str) -> dict[str, str]:
    """`{YYYY-MM-DD: anahtar}`."""
    _, anahtarlar = kaynak.listele(gun_oneki(sembol, timeframe))
    return zip_anahtarlari(anahtarlar, _GUN_DOSYASI)


# ------------------------------------------------------------ doğrulama/okuma


def sha256(bayt: bytes) -> str:
    return hashlib.sha256(bayt).hexdigest()


def checksum_dogrula(anahtar: str, zip_bayt: bytes, checksum_bayt: bytes | None) -> str:
    """Zip'in SHA-256'sını `.CHECKSUM` dosyasıyla karşılaştırır, hash'i döndürür.

    Checksum dosyası yoksa **hata**: doğrulanamayan dosyayı kabul etmek, bozuk bir indirmeyi
    veri seti kimliğine (K-009) kalıcı olarak gömmek olurdu.
    """
    if checksum_bayt is None:
        raise ArsivHatasi(f"{anahtar}: .CHECKSUM dosyası yok; doğrulanamayan veri kabul edilmez")
    parca = checksum_bayt.decode("ascii", errors="replace").split()
    if not parca or not re.fullmatch(r"[0-9a-f]{64}", parca[0]):
        raise ArsivHatasi(f"{anahtar}: .CHECKSUM okunamadı: {checksum_bayt[:80]!r}")
    gercek = sha256(zip_bayt)
    if gercek != parca[0]:
        raise ArsivHatasi(f"{anahtar}: checksum uyuşmuyor (beklenen {parca[0]}, gelen {gercek})")
    return gercek


def zip_barlari(anahtar: str, zip_bayt: bytes) -> pd.DataFrame:
    """Arşiv zip'i → ham bar DataFrame'i (`HAM_BAR_SUTUNLARI`, `open_time` ms).

    Zip tek bir CSV içermeli. Başlık satırı yok (ölçüldü); gelecekte eklenirse sessizce veri
    satırı gibi okunmasın diye sayısal olmayan ilk alan **hata** verir.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bayt)) as z:
            adlar = z.namelist()
            if len(adlar) != 1:
                raise ArsivHatasi(f"{anahtar}: zip tek dosya içermeli, {len(adlar)} var")
            ham = z.read(adlar[0])
    except zipfile.BadZipFile as hata:
        raise ArsivHatasi(f"{anahtar}: bozuk zip: {hata}") from hata

    if not ham.strip():
        return pd.DataFrame({s: pd.Series(dtype=d) for s, d in HAM_PANDAS_DTYPES.items()})

    ilk_alan = ham.split(b",", 1)[0].strip()
    if not ilk_alan.isdigit():
        raise ArsivHatasi(f"{anahtar}: beklenmeyen başlık/biçim: {ham[:80]!r}")

    try:
        df = pd.read_csv(
            io.BytesIO(ham),
            header=None,
            names=list(_CSV_ALANLARI),
            usecols=list(HAM_BAR_SUTUNLARI),
            dtype={"open_time": "int64", "trades": "int64"},
            # Varsayılan hızlı ayrıştırıcı değerleri 1e-7 mertebesinde kaydırıyor (ölçüldü);
            # REST'le bit düzeyinde aynı olmak için round_trip.
            float_precision="round_trip",
        )
    except (ValueError, pd.errors.ParserError) as hata:
        raise ArsivHatasi(f"{anahtar}: CSV ayrıştırılamadı: {hata}") from hata

    df["open_time"] = _ms_yap(anahtar, df["open_time"])
    for sutun, dtype in HAM_PANDAS_DTYPES.items():
        df[sutun] = df[sutun].astype(dtype)
    return df.loc[:, list(HAM_BAR_SUTUNLARI)]


def _ms_yap(anahtar: str, zaman: pd.Series) -> pd.Series:
    """`open_time`'ı ms'e çevirir. Birim sayının büyüklüğünden çıkarılır.

    Aynı dosyada iki birim birden varsa ya da µs değeri 1000'e bölünmüyorsa **hata**: ilki
    birim kuralının yanlış olduğunu, ikincisi değerin bir bar sınırı olmadığını söyler.
    İkisini de "düzeltmek" tahmin yürütmek olurdu.
    """
    mikro = zaman >= MIKROSANIYE_SINIRI
    if mikro.any() and not mikro.all():
        raise ArsivHatasi(f"{anahtar}: dosyada ms ve µs karışık open_time var")
    if not mikro.any():
        return zaman
    if (zaman % 1000 != 0).any():
        raise ArsivHatasi(f"{anahtar}: µs open_time 1000'e bölünmüyor")
    return zaman // 1000


__all__ = [
    "ARSIV_HOST",
    "MIKROSANIYE_SINIRI",
    "ArsivHatasi",
    "ArsivKaynagi",
    "HttpArsiv",
    "aylik_dosyalar",
    "checksum_dogrula",
    "gunluk_dosyalar",
    "sha256",
    "spot_sembolleri",
    "zip_barlari",
]
