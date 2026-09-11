"""Binance canlı bar akışı: WebSocket + kopma sonrası REST resync. (§24, K-023, Faz 6)

`live/akis.py` akışın **sözleşmesini** tanımlıyor; burası Binance uygulaması.

**Neden ccxt.pro'nun `watch_ohlcv`'si değil, ham WebSocket:** K-023 aynı kararı tarihsel
veri için vermişti — *"klines ccxt'nin ham ucundan alınır, `fetch_ohlcv`'den değil"*. Sebep
burada da aynı ve daha keskin: ccxt OHLCV'yi altı elemanlı bir listeye normalize ediyor ve
`q` (quote hacmi) ile `n` (işlem sayısı) alanlarını **düşürüyor**. O iki alan bizde süs
değil, doğrulama girdisi: `sifir_hacim`, `negatif_hacim` ve `islemsiz_hacim` kuralları
onlara bakıyor (K-006). Elde olmayınca ya kurallar canlıda sessizce devre dışı kalır ya da
sayılar uydurulur; ikisi de bu projede yasak. Ham akışta ikisi de var.

**Kapanmışlık bayrağı burada var.** `common/zaman.py:bar_kapandi_mi` şunu söylüyordu:
*"Kapanmışlık bayrağı REST'te yok (yalnızca WebSocket akışında)."* Bu modül o bayrağı
(`k.x`) kullanıyor — zaman karşılaştırmasına gerek kalmıyor.

**Kopma sonrası resync (§24):** yeniden bağlanıldığında, en son teslim edilen kapanmış
bardan sonraki her bar REST'ten çekilir ve `Kaynak.BACKFILL` işaretiyle akışa sokulur.
İşaret kritik: o barlar `backfilled` kalite bayrağı alır (K-006), yani paper motoru o
barların açılışında **fill iddia etmez** (K-028). Bağlı olmadığımız sürede olan bir fill'i
kayda geçirmemek, bu zincirin tek satırlık özeti.

**Nabız ayrı bir kanal.** İterator yalnızca kapanmış bar üretiyor (sözleşme gereği), ama
bayat-veri guard'ının ölçtüğü şey mesaj trafiği (K-037/2). Bu yüzden her mesajda
`nabiz_kancasi` çağrılıyor — kapanmamış bar güncellemeleri dahil.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any, Final

import aiohttp

from scryne_quant.common.zaman import simdi_ms, timeframe_ms
from scryne_quant.exchange.temel import BorsaAdaptoru, BorsaHatasi
from scryne_quant.live.akis import AkisHatasi, Bar, Kaynak

#: Binance spot birleşik akış kökü. `data-api.binance.vision` yalnızca REST için;
#: WebSocket ayrı bir uçta yaşıyor.
WS_KOK: Final = "wss://stream.binance.com:9443/ws"

#: Testnet akışı. Faz 7'nin execution testleri bunu kullanacak (Spike 1).
WS_KOK_TESTNET: Final = "wss://stream.testnet.binance.vision/ws"

#: Yeniden bağlanma bekleme süreleri (saniye). Üstel ama tavanlı: sonsuz büyüyen bir
#: backoff, kısa bir kesintiden sonra sistemin saatlerce bağlanmaması demek olurdu.
BACKOFF: Final[tuple[float, ...]] = (1.0, 2.0, 5.0, 10.0, 30.0, 60.0)

#: WebSocket'ten mesaj beklerken azami sessizlik. Binance 1h kline akışı saniyede
#: birkaç mesaj gönderiyor; 90 saniye sessizlik "bağlantı ölü ama TCP bunu bilmiyor"
#: durumudur ve ancak zaman aşımıyla fark edilir.
OKUMA_ZAMAN_ASIMI: Final = 90.0


class AkisKoptu(AkisHatasi):
    """Bağlantı koptu. Koşturucu bunu yakalayıp yeniden bağlanır."""


def akis_adi(sembol: str, timeframe: str) -> str:
    """Binance akış adı: `btcusdt@kline_1h`. Sembol normalize ediliyor, doğrulanmıyor."""
    return f"{sembol.replace('/', '').lower()}@kline_{timeframe}"


def bar_cikar(mesaj: dict[str, Any]) -> Bar | None:
    """Kline mesajından **kapanmış** barı çıkarır; kapanmamışsa `None`.

    Saf fonksiyon — ağ yok, durum yok. Akışın tek ayrıştırma noktası olması bilinçli:
    alan adı değişikliği burada patlar, sistemin ortasında değil.
    """
    k = mesaj.get("k")
    if not isinstance(k, dict):
        return None
    if not k.get("x"):
        # Kapanmamış bar: yalnızca nabızdır. Stratejiye verilirse, oluşmakta olan bir
        # kapanışa göre karar verilmiş olur — K-004'ün karar tarafındaki ihlali.
        return None
    try:
        return Bar(
            open_time=int(k["t"]),
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            quote_volume=float(k["q"]),
            trades=int(k["n"]),
            kaynak=Kaynak.AKIS,
        )
    except (KeyError, TypeError, ValueError) as hata:
        raise AkisHatasi(f"kline mesajı ayrıştırılamadı: {hata}; mesaj={mesaj!r}") from hata


def df_barlara(df: Any, *, kaynak: Kaynak = Kaynak.BACKFILL) -> list[Bar]:
    """REST'ten gelen ham kline DataFrame'ini `Bar` listesine çevirir."""
    return [
        Bar(
            open_time=int(r["open_time"]),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r["volume"]),
            quote_volume=float(r["quote_volume"]),
            trades=int(r["trades"]),
            kaynak=kaynak,
        )
        for _, r in df.iterrows()
    ]


class BinanceBarAkisi:
    """Binance spot kline akışı. `live/akis.py:BarAkisi` protokolünü uygular.

    Tek sembol, tek timeframe. Çoklu sembol Faz 7+'nın işi ve o gün bu sınıfın birden
    çok örneği mi yoksa birleşik akış mı kullanılacağı ölçülerek karara bağlanacak —
    şimdiden genel yazmak, hiç kullanılmamış bir kod yolunu test edilmemiş bırakırdı.
    """

    def __init__(
        self,
        sembol: str,
        timeframe: str,
        *,
        adaptor: BorsaAdaptoru | None = None,
        nabiz_kancasi: Callable[[int], None] | None = None,
        kopma_kancasi: Callable[[str], None] | None = None,
        yeniden_baglanma_kancasi: Callable[[dict[str, Any]], None] | None = None,
        ws_kok: str = WS_KOK,
        oturum: aiohttp.ClientSession | None = None,
    ) -> None:
        self._sembol = sembol
        self._timeframe = timeframe
        self._adim = timeframe_ms(timeframe)
        self._adaptor = adaptor
        """REST kaynağı. `None` ise kopma sonrası resync **yapılamaz** ve akış bunu
        söyler — sessizce boşluk bırakmak, boşluğun `gap` bayrağıyla bile olsa fark
        edilmemesi riskini alırdı."""

        self._nabiz = nabiz_kancasi or (lambda _: None)
        self._kopma = kopma_kancasi or (lambda _: None)
        self._yeniden_baglandi = yeniden_baglanma_kancasi or (lambda _: None)
        """Kopma **giderildiğinde** çağrılır. `kopma_kancasi`nın eksik yarısıydı: kopma
        kayda geçiyordu ama toparlanması geçmiyordu, yani koşu günlüğü *"kesinti olduysa
        sebebi kayıtlı ve giderilmiş"* kriterinin ikinci yarısını hiç yazmıyordu."""

        self._ws_kok = ws_kok.rstrip("/")
        self._dis_oturum = oturum
        self._oturum: aiohttp.ClientSession | None = oturum
        self._kapali = False
        self._son_teslim_ms: int | None = None
        self._kopuk = False
        """Şu an bir kopmadan sonraki yeniden bağlanmayı bekliyor muyuz?"""

        self._resync_bar = 0
        """Bu kopma boyunca REST'ten tamamlanan bar sayısı; yeniden bağlanma kaydına girer."""

        self._kopma_ms: int | None = None
        self._oturum_mesaji = 0
        """İçinde bulunulan WebSocket oturumunda alınan mesaj sayısı. Backoff'un
        sıfırlanıp sıfırlanmayacağını bu belirliyor — ayrıntı `barlar()`de."""

    # ------------------------------------------------------------------ sözleşme

    @property
    def sembol(self) -> str:
        return self._sembol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def son_teslim_ms(self) -> int | None:
        """Akışa verilen son kapanmış barın açılış zamanı. Resync sınırı bu."""
        return self._son_teslim_ms

    @property
    def url(self) -> str:
        return f"{self._ws_kok}/{akis_adi(self._sembol, self._timeframe)}"

    def kapat(self) -> None:
        """Akışı kapatır. İki kez çağrılabilir (sözleşme)."""
        self._kapali = True

    async def temizle(self) -> None:
        """Kendi açtığı oturumu kapatır. Dışarıdan verilen oturuma dokunmaz."""
        if self._oturum is not None and self._dis_oturum is None:
            await self._oturum.close()
        self._oturum = None

    # ------------------------------------------------------------------ akış

    async def barlar(self) -> AsyncIterator[Bar]:
        """Kapanmış barları sırayla üretir; kopmada yeniden bağlanıp eksikleri tamamlar.

        **Backoff bir bar değil, bir mesaj gördüğünde sıfırlanır.** İlk yazımda sayaç
        yalnızca `yield`lenen bir barda sıfırlanıyordu ve bu 1h timeframe'de yanlış
        davranırdı: bar saatte bir kapanır, yani bağlantı kurulup mesaj akmaya başlasa
        bile bir sonraki kopma "başarısız deneme" sayılır ve backoff kısa kesintilerde
        bile tavana (60 s) tırmanırdı. Ölçüt "bağlantı çalıştı mı", ve onu söyleyen şey
        trafik. Yalnızca *bağlanmış olmak* ölçüt değil: kabul edip anında kapatan bir uç
        sayacı her turda sıfırlar ve backoff'u tamamen devre dışı bırakırdı.
        """
        deneme = 0
        while not self._kapali:
            try:
                async for bar in self._oturumda_barlar():
                    yield bar
            except (TimeoutError, aiohttp.ClientError, AkisKoptu) as hata:
                if self._kapali:
                    break
                if self._oturum_mesaji > 0:
                    deneme = 0
                self._kopuk = True
                self._kopma_ms = simdi_ms()
                self._resync_bar = 0
                self._kopma(f"{type(hata).__name__}: {hata}")
                bekleme = BACKOFF[min(deneme, len(BACKOFF) - 1)]
                deneme += 1
                await asyncio.sleep(bekleme)
                async for bar in self._resync():
                    self._resync_bar += 1
                    yield bar

    async def _oturumda_barlar(self) -> AsyncIterator[Bar]:
        if self._oturum is None:
            self._oturum = aiohttp.ClientSession()
        self._oturum_mesaji = 0
        async with self._oturum.ws_connect(self.url, heartbeat=30.0) as ws:
            while not self._kapali:
                try:
                    mesaj = await asyncio.wait_for(ws.receive(), timeout=OKUMA_ZAMAN_ASIMI)
                except TimeoutError as hata:
                    raise AkisKoptu(
                        f"{OKUMA_ZAMAN_ASIMI:.0f} s boyunca mesaj gelmedi; bağlantı ölü kabul "
                        "ediliyor"
                    ) from hata

                if mesaj.type is aiohttp.WSMsgType.TEXT:
                    self._oturum_mesaji += 1
                    # Kopma ancak **trafik** geri geldiğinde giderilmiş sayılır.
                    # `ws_connect`in dönmesi yetmez: el sıkışan ama veri göndermeyen bir
                    # uç, koşu günlüğüne "giderildi" yazdırıp kesintiyi kapatırdı.
                    if self._kopuk:
                        self._kopuk = False
                        self._yeniden_baglandi(
                            {
                                "resync_bar": self._resync_bar,
                                "kopuk_ms": (
                                    None
                                    if self._kopma_ms is None
                                    else simdi_ms() - self._kopma_ms
                                ),
                                "son_teslim_ms": self._son_teslim_ms,
                            }
                        )
                        self._resync_bar = 0
                        self._kopma_ms = None
                    self._nabiz(simdi_ms())
                    bar = bar_cikar(json.loads(mesaj.data))
                    if bar is not None and self._ileri_mi(bar):
                        self._son_teslim_ms = bar.open_time
                        yield bar
                elif mesaj.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.ERROR,
                ):
                    raise AkisKoptu(f"WebSocket kapandı: {mesaj.type.name}")

    def _ileri_mi(self, bar: Bar) -> bool:
        """Aynı barın ikinci kez gelmesini süzer. Geriye gideni de süzer — pencere zaten
        reddederdi, ama akışın sözleşmesi "sırayla" diyor ve sözleşmeyi akış korur."""
        return self._son_teslim_ms is None or bar.open_time > self._son_teslim_ms

    # ------------------------------------------------------------------ resync

    async def _resync(self) -> AsyncIterator[Bar]:
        """Kopma boyunca kaçırılan kapanmış barları REST'ten tamamlar (§24).

        Tamamlanan barlar `Kaynak.BACKFILL` taşır: kusursuz olsalar bile `backfilled`
        kalite bayrağı alırlar (K-006) ve paper motoru o barların açılışında fill iddia
        etmez (K-028). Kopma sırasında "olmuş gibi" bir işlem üretmemek bu zincirin
        tek amacı.
        """
        if self._adaptor is None or self._son_teslim_ms is None:
            return
        baslangic = self._son_teslim_ms + self._adim
        bitis = simdi_ms()
        if baslangic >= bitis:
            return
        try:
            df = await asyncio.to_thread(
                self._adaptor.klines, self._sembol, self._timeframe, baslangic, bitis
            )
        except BorsaHatasi:
            # REST de erişilemiyorsa boşluk boşluk kalır ve bir sonraki bar `gap`
            # işaretlenir (K-024: boşluk uydurulmaz). Sessiz değil, eksik.
            return
        for bar in df_barlara(df):
            if self._ileri_mi(bar):
                self._son_teslim_ms = bar.open_time
                yield bar


__all__ = [
    "BACKOFF",
    "OKUMA_ZAMAN_ASIMI",
    "WS_KOK",
    "WS_KOK_TESTNET",
    "AkisKoptu",
    "BinanceBarAkisi",
    "akis_adi",
    "bar_cikar",
    "df_barlara",
]
