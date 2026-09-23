"""Binance spot adaptörü. (K-015, Faz 0 gereksinim 1-6)

Bu dosyadaki hemen her sabit bir **ölçümün** sonucudur, tercih değil. Spike 1 (bkz.
`docs/arsiv/spikes/01-binance-erisim.md`) neyin darboğaz olduğunu ve neyin olmadığını ölçtü;
aşağıdaki her karar o ölçüme dayanıyor ve yorumu yanında yazılı.

**Neden `fetch_ohlcv` değil, ham `publicGetKlines`:** ccxt'nin normalize ettiği OHLCV altı
alan döndürür — `quote_volume` ve `trades` yok. `BAR_SEMASI` ikisini de zorunlu tutuyor
(hacim ortalaması indikatörü ve `suspect` tespiti bunlara bakar). ccxt yine transport
katmanı olarak kalıyor (kalıcı session, rate limiter, hata sınıfları); yalnızca şema kaybı
olan sarmalayıcı atlanıyor. Karar: K-023.

**IPv4 zorlaması:** yerel çözümleyici `*.binance.vision` için AAAA sorgusunu ~12 saniye
sonra düşürüyor (ölçüldü: 12.098 ms vs 26,6 ms). Bu Binance'e ait bir davranış değil,
ortama ait — ama koda bakarak anlaşılmaz. urllib3'ün `allowed_gai_family` kancası süreç
genelinde etkilidir; o yüzden açıkça, tek bir yerden ve kapatılabilir biçimde yapılıyor.
"""

from __future__ import annotations

import socket
import time
from typing import Any, Final

import ccxt
import pandas as pd
import urllib3.util.connection as urllib3_baglanti

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI, HAM_PANDAS_DTYPES
from scryne_quant.exchange.temel import (
    SAYFA_BOYU,
    BorsaAdaptoru,
    BorsaHatasi,
    SembolKurallari,
)

#: Tarihsel indirme buradan yapılır (Spike 1/5): p50 277,6 ms, ve emir trafiğiyle aynı IP
#: weight havuzunu paylaşmaz. Faz 7'nin emir akışı bu host'u kullanmayacak.
VERI_HOST: Final = "https://data-api.binance.vision"

#: Veri ucu cevap vermezse aynı public verinin alındığı yedek uçlar (K-122). Gösterim öncesi
#: ölçüldü: `testnet-surekli-1` 10 saatte 107 döngüde `data-api` `/time`a 5 denemede
#: ulaşamadı; aynı anda ölçülen dört uç (data-api, api, api1, api-gcp) ayrı IP'lerde. Uç
#: değişimi veriyi değiştirmez (aynı borsa, aynı kline); yalnız tek uca bağımlılığı kaldırır.
YEDEK_HOSTLAR: Final[tuple[str, ...]] = (
    VERI_HOST, "https://api.binance.com", "https://api-gcp.binance.com",
)

#: Ölçülen kuyruk gecikmesi 1,6 s; timeout ≥ 5 s olmalı (Spike 1/4). 15 s, kuyruğun ~10
#: katı — geçici bir yavaşlamada boşuna hata üretmeyecek kadar geniş, asılı kalmayacak
#: kadar dar.
TIMEOUT_MS: Final = 15_000

#: Ağ hatasında yeniden deneme. Spike 1'de 60/60 istek başarılıydı; yine de 8 dakikalık
#: bir indirmenin tek bir kopan bağlantı yüzünden yarıda kalması kabul edilemez.
DENEME_SAYISI: Final = 5
BEKLEME_TABANI_S: Final = 1.0

#: Sunucu saati bu süre boyunca önbellekte tutulur. Bayat değer **güvenli yöndedir**:
#: gerçekte kapanmış bir barı kapanmamış sayar (bar atlanır, sonraki çağrıda gelir);
#: tersi — kapanmamış barı kapanmış saymak — idempotency'yi kırardı.
ZAMAN_TAZELIK_MS: Final = 60_000

#: Binance kline dizisindeki alan sıraları. Ham dizi 12 elemanlı; kullanmadıklarımız
#: (taker_base, taker_quote, ignore) bilerek alınmıyor.
_KLINE_ALANLARI: Final[dict[str, int]] = {
    "open_time": 0,
    "open": 1,
    "high": 2,
    "low": 3,
    "close": 4,
    "volume": 5,
    "quote_volume": 7,
    "trades": 8,
}

_ipv4_zorlandi = False


def ipv4_zorla() -> None:
    """Süreç genelinde IPv4 çözümlemeye zorla. (Spike 1/3)

    urllib3'ün kancasını değiştirir; `socket.getaddrinfo`'yu maymun-yamalamaktan daha dar
    bir müdahale. İki kez çağrılması zararsızdır.
    """
    global _ipv4_zorlandi
    if _ipv4_zorlandi:
        return
    urllib3_baglanti.allowed_gai_family = lambda: socket.AF_INET
    _ipv4_zorlandi = True


class BinanceAdaptoru(BorsaAdaptoru):
    """Binance spot, yalnızca public veri uçları.

    Anahtar tutmaz ve imzalı istek yapmaz — Faz 1'in ihtiyacı bu kadar. Kimlik doğrulama
    Faz 7'de, gerçek testnet anahtarıyla eklenir (K-015'in kapanmayan kısmı).
    """

    def __init__(
        self,
        *,
        host: str = VERI_HOST,
        timeout_ms: int = TIMEOUT_MS,
        ipv4: bool = True,
        deneme_sayisi: int = DENEME_SAYISI,
        yedek_hostlar: tuple[str, ...] | None = None,
    ) -> None:
        if ipv4:
            ipv4_zorla()

        self._borsa = ccxt.binance(
            {
                "enableRateLimit": True,
                "timeout": timeout_ms,
                # `load_markets()` 3,2 s sürüyor ve 4.619 marketin tamamını çekiyor
                # (Spike 1/6). Tek sembolle çalışan bir sistemde her başlatmada
                # ödenmemeli; bu adaptör onu hiç çağırmıyor.
                "options": {"adjustForTimeDifference": False},
            }
        )
        # Tarihsel uçlar veri host'una yönlendirilir; ccxt'nin kalıcı session'ı korunur.
        self._borsa.urls["api"]["public"] = f"{host}/api/v3"
        self._deneme_sayisi = deneme_sayisi
        # Varsayılan veri ucunda yedekler açık; açıkça başka bir host verilmişse (test, testnet)
        # yalnız o host kullanılır — sessizce başka bir uca geçilmez.
        if yedek_hostlar is None:
            yedek_hostlar = YEDEK_HOSTLAR if host == VERI_HOST else (host,)
        self._hostlar = tuple(yedek_hostlar)
        self._host_sira = self._hostlar.index(host) if host in self._hostlar else 0

        self._zaman_onbellek: tuple[int, float] | None = None
        self._kural_onbellek: dict[str, SembolKurallari] = {}

    # ------------------------------------------------------------------- ağ

    def _dene(self, ad: str, cagri: Any, *args: Any) -> Any:
        """Ağ hatalarında üstel geri çekilmeyle yeniden dener.

        Yalnızca **geçici** hatalar tekrarlanır. `ExchangeError` (geçersiz sembol,
        geçersiz interval) tekrarlanmaz: aynı istek aynı hatayı verecektir; tekrar
        denemek hatayı yalnızca geciktirir ve sebebini bulanıklaştırır.
        """
        son: Exception | None = None
        for deneme in range(self._deneme_sayisi):
            try:
                return cagri(*args)
            except (ccxt.NetworkError, ccxt.RateLimitExceeded, ccxt.DDoSProtection) as hata:
                son = hata
                hiz = isinstance(hata, (ccxt.RateLimitExceeded, ccxt.DDoSProtection))
                if not hiz and len(self._hostlar) > 1:
                    # Ağ hatasında sıradaki uca geç ve orada kal (K-122). Hız sınırı hatası
                    # (ccxt'de `NetworkError` alt sınıfı) uç değiştirmez: aynı IP'nin weight'i,
                    # uç değişse de aynı borsada.
                    self._host_sira = (self._host_sira + 1) % len(self._hostlar)
                    self._borsa.urls["api"]["public"] = (
                        f"{self._hostlar[self._host_sira]}/api/v3"
                    )
                if deneme + 1 < self._deneme_sayisi:
                    time.sleep(BEKLEME_TABANI_S * (2**deneme))
            except ccxt.BaseError as hata:
                raise BorsaHatasi(f"{ad}: {type(hata).__name__}: {hata}") from hata
        raise BorsaHatasi(
            f"{ad}: {self._deneme_sayisi} denemede başarısız: {type(son).__name__}: {son}"
        ) from son

    # ---------------------------------------------------------------- zaman

    def sunucu_zamani_ms(self) -> int:
        """Borsanın saati (K-015). Bayat önbellek güvenli yön — bkz. `ZAMAN_TAZELIK_MS`."""
        simdi = time.monotonic()
        if self._zaman_onbellek is not None:
            deger, alindi = self._zaman_onbellek
            if (simdi - alindi) * 1000 < ZAMAN_TAZELIK_MS:
                return deger

        yanit = self._dene("serverTime", self._borsa.publicGetTime)
        try:
            deger = int(yanit["serverTime"])
        except (KeyError, TypeError, ValueError) as hata:
            raise BorsaHatasi(f"serverTime okunamadı: {yanit!r}") from hata
        self._zaman_onbellek = (deger, simdi)
        return deger

    # --------------------------------------------------------------- klines

    def klines(
        self, sembol: str, timeframe: str, baslangic_ms: int, bitis_ms: int
    ) -> pd.DataFrame:
        """Kapanmış barlar, en fazla `SAYFA_BOYU` tane. Sözleşme: `temel.BorsaAdaptoru`."""
        adim = timeframe_ms(timeframe)  # tanınmayan timeframe ağa çıkmadan patlasın
        if bitis_ms <= baslangic_ms:
            return bos_ham_df()

        ham = self._dene(
            "klines",
            self._borsa.publicGetKlines,
            {
                "symbol": sembol.upper(),
                "interval": timeframe,
                "startTime": int(baslangic_ms),
                # Binance'in `endTime`'ı kapsayıcı, bizim aralığımız değil.
                "endTime": int(bitis_ms) - 1,
                "limit": SAYFA_BOYU,  # her zaman 1000 (Spike 1/2)
            },
        )
        if not ham:
            return bos_ham_df()

        df = kline_df(ham)

        # Kapanmamış bar atılır (K-015/1). Bu satır olmadan aynı komut iki kez
        # çalıştırıldığında dosya farklı çıkar — Faz 1'in bitti kriteri düşer.
        acik = df["open_time"] + adim > self.sunucu_zamani_ms()
        if acik.any():
            df = df.loc[~acik]

        return df.reset_index(drop=True)

    def son_fiyat(self, sembol: str) -> float:
        """Son işlem fiyatı (public `ticker/price`). Aktif demo botun dolum fiyatı (K-134)."""
        yanit = self._dene(
            "tickerPrice", self._borsa.publicGetTickerPrice, {"symbol": sembol.upper()}
        )
        try:
            fiyat = float(yanit["price"])
        except (KeyError, TypeError, ValueError) as hata:
            raise BorsaHatasi(f"ticker/price okunamadı: {yanit!r}") from hata
        if not fiyat > 0:
            raise BorsaHatasi(f"ticker/price geçersiz: {yanit!r}")
        return fiyat

    # ------------------------------------------------------------- kurallar

    def sembol_kurallari(self, sembol: str) -> SembolKurallari:
        """Emir kuralları; sembol başına önbellekli (Spike 1/6)."""
        anahtar = sembol.upper()
        if anahtar in self._kural_onbellek:
            return self._kural_onbellek[anahtar]

        bilgi = self._dene("exchangeInfo", self._borsa.publicGetExchangeInfo, {"symbol": anahtar})
        semboller = bilgi.get("symbols") or []
        if not semboller:
            raise BorsaHatasi(f"sembol borsada yok: {anahtar}")

        s = semboller[0]
        filtreler = {f["filterType"]: f for f in s.get("filters", [])}
        kural = SembolKurallari(
            sembol=anahtar,
            tick_size=float(filtreler["PRICE_FILTER"]["tickSize"]),
            step_size=float(filtreler["LOT_SIZE"]["stepSize"]),
            min_notional=float(filtreler.get("NOTIONAL", {}).get("minNotional", 0.0)),
            durum=str(s.get("status", "")),
        )
        self._kural_onbellek[anahtar] = kural
        return kural


# ---------------------------------------------------------------- yardımcı


def bos_ham_df() -> pd.DataFrame:
    """Doğru şemalı boş DataFrame. Boş liste dönmek çağıranı dtype tahminine zorlardı."""
    return pd.DataFrame({s: pd.Series(dtype=d) for s, d in HAM_PANDAS_DTYPES.items()})


def kline_df(ham: list[list[Any]]) -> pd.DataFrame:
    """Binance kline dizisi → ham bar DataFrame'i.

    Fiyatlar Binance'ten **string** gelir. `float` dönüşümü burada, tek yerde yapılır:
    dağıtılmış bir dönüşüm bir yerde unutulduğunda karşılaştırmalar sessizce string
    sıralaması yapmaya başlar — ve sonuç makul görünmeye devam eder.
    """
    sutunlar = {ad: [satir[idx] for satir in ham] for ad, idx in _KLINE_ALANLARI.items()}
    df = pd.DataFrame(sutunlar)
    for sutun, dtype in HAM_PANDAS_DTYPES.items():
        df[sutun] = df[sutun].astype(dtype)
    return df.loc[:, list(HAM_BAR_SUTUNLARI)]
