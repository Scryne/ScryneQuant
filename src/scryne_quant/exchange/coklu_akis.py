"""Binance çok sembollü kline akışı: birleşik WebSocket + sembol başına REST resync. (Faz 14)

Tek sembollü `exchange/akis.py:BinanceBarAkisi` Faz 6'da bilinçli olarak genel yazılmamıştı:
*"çoklu sembol Faz 7+'nın işi; birden çok örnek mi birleşik akış mı, ölçülerek karara
bağlanacak."* Evren paper motoru (tasarım `docs/Faz-14-Coklu-Paper-Tasarim.md` §2) ≈50 sembol
izliyor. Karar: **tek birleşik akış** (`/stream?streams=a@kline_1h/b@kline_1h/...`).
Sebepler: 50 ayrı bağlantı Binance'in IP başına bağlantı sınırını gereksiz yere zorlar ve her
biri ayrı bir kopma/yeniden bağlanma yaşar; birleşik akışta kopma **tek** olaydır ve resync
bütün semboller için aynı anda yapılır.

Tek sembollü akıştan **aynen** korunanlar (davranış testleri `test_coklu_akis.py`):

- yalnızca kapanmış bar teslim edilir (`k.x`), her mesaj nabızdır;
- sembol başına aynı/geriye giden bar süzülür;
- kopmada üstel ama tavanlı backoff; sayaç **trafik** görülünce sıfırlanır;
- yeniden bağlanınca her sembol için son teslimden sonraki barlar REST'ten `BACKFILL` olarak
  gelir; "giderildi" ancak trafik dönünce bildirilir.

Birleşik akış mesajı `{"stream": "...", "data": {<kline>}}`; sembol `data.s`'den okunur.
Teslim edilen öğe `(sembol, Bar)`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any, Final

import aiohttp

from scryne_quant.common.zaman import simdi_ms, timeframe_ms
from scryne_quant.exchange.akis import (
    BACKOFF,
    OKUMA_ZAMAN_ASIMI,
    AkisKoptu,
    akis_adi,
    bar_cikar,
    df_barlara,
)
from scryne_quant.exchange.temel import BorsaAdaptoru, BorsaHatasi
from scryne_quant.live.akis import AkisHatasi, Bar

#: Birleşik akış kökü.
WS_BIRLESIK_KOK: Final = "wss://stream.binance.com:9443/stream"

#: Binance birleşik akışta bağlantı başına azami akış sayısı 1.024; evren 50 civarında.
AZAMI_AKIS: Final = 1_024


class BinanceCokluBarAkisi:
    """Birden çok sembolün kapanmış barlarını tek bağlantıdan `(sembol, Bar)` olarak üretir."""

    def __init__(
        self,
        semboller: Sequence[str],
        timeframe: str,
        *,
        adaptor: BorsaAdaptoru | None = None,
        nabiz_kancasi: Callable[[int], None] | None = None,
        kopma_kancasi: Callable[[str], None] | None = None,
        yeniden_baglanma_kancasi: Callable[[dict[str, Any]], None] | None = None,
        ws_kok: str = WS_BIRLESIK_KOK,
        oturum: aiohttp.ClientSession | None = None,
        son_teslim: dict[str, int] | None = None,
    ) -> None:
        semboller = tuple(sorted({s.upper() for s in semboller}))
        if not semboller:
            raise AkisHatasi("en az bir sembol gerekir")
        if len(semboller) > AZAMI_AKIS:
            raise AkisHatasi(f"birleşik akış en fazla {AZAMI_AKIS} sembol taşır")
        self._semboller = semboller
        self._timeframe = timeframe
        self._adim = timeframe_ms(timeframe)
        self._adaptor = adaptor
        self._nabiz = nabiz_kancasi or (lambda _: None)
        self._kopma = kopma_kancasi or (lambda _: None)
        self._yeniden_baglandi = yeniden_baglanma_kancasi or (lambda _: None)
        self._ws_kok = ws_kok.rstrip("/")
        self._dis_oturum = oturum
        self._oturum = oturum
        self._kapali = False
        self._son_teslim: dict[str, int] = dict(son_teslim or {})
        self._kopuk = False
        self._resync_bar = 0
        self._kopma_ms: int | None = None
        self._oturum_mesaji = 0

    @property
    def semboller(self) -> tuple[str, ...]:
        return self._semboller

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def son_teslim(self) -> dict[str, int]:
        return dict(self._son_teslim)

    @property
    def url(self) -> str:
        akislar = "/".join(akis_adi(s, self._timeframe) for s in self._semboller)
        return f"{self._ws_kok}?streams={akislar}"

    def kapat(self) -> None:
        self._kapali = True

    async def temizle(self) -> None:
        if self._oturum is not None and self._dis_oturum is None:
            await self._oturum.close()
        self._oturum = None

    async def barlar(self) -> AsyncIterator[tuple[str, Bar]]:
        deneme = 0
        while not self._kapali:
            try:
                async for oge in self._oturumda_barlar():
                    yield oge
            except (TimeoutError, aiohttp.ClientError, AkisKoptu) as hata:
                if self._kapali:
                    break
                if self._oturum_mesaji > 0:
                    deneme = 0
                self._kopuk = True
                self._kopma_ms = simdi_ms()
                self._resync_bar = 0
                self._kopma(f"{type(hata).__name__}: {hata}")
                await asyncio.sleep(BACKOFF[min(deneme, len(BACKOFF) - 1)])
                deneme += 1
                async for oge in self._resync():
                    self._resync_bar += 1
                    yield oge

    async def _oturumda_barlar(self) -> AsyncIterator[tuple[str, Bar]]:
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
                    if self._kopuk:
                        self._kopuk = False
                        self._yeniden_baglandi({
                            "resync_bar": self._resync_bar,
                            "kopuk_ms": None if self._kopma_ms is None
                            else simdi_ms() - self._kopma_ms,
                            "sembol": len(self._semboller),
                        })
                        self._resync_bar = 0
                        self._kopma_ms = None
                    self._nabiz(simdi_ms())
                    govde = json.loads(mesaj.data)
                    veri = govde.get("data", govde)
                    sembol = str(veri.get("s", "")).upper()
                    bar = bar_cikar(veri)
                    abone = sembol in self._semboller
                    if bar is not None and abone and self._ileri_mi(sembol, bar):
                        self._son_teslim[sembol] = bar.open_time
                        yield sembol, bar
                elif mesaj.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING,
                                    aiohttp.WSMsgType.ERROR):
                    raise AkisKoptu(f"WebSocket kapandı: {mesaj.type.name}")

    def _ileri_mi(self, sembol: str, bar: Bar) -> bool:
        son = self._son_teslim.get(sembol)
        return son is None or bar.open_time > son

    async def _resync(self) -> AsyncIterator[tuple[str, Bar]]:
        """Her sembol için son teslimden sonraki kapanmış barlar, `BACKFILL` olarak (§24)."""
        if self._adaptor is None:
            return
        bitis = simdi_ms()
        for sembol in self._semboller:
            son = self._son_teslim.get(sembol)
            if son is None or son + self._adim >= bitis:
                continue
            try:
                df = await asyncio.to_thread(
                    self._adaptor.klines, sembol, self._timeframe, son + self._adim, bitis
                )
            except BorsaHatasi:
                continue  # boşluk uydurulmaz (K-024); sonraki bar `gap` işaretlenir
            for bar in df_barlara(df):
                if self._ileri_mi(sembol, bar):
                    self._son_teslim[sembol] = bar.open_time
                    yield sembol, bar


__all__ = ["AZAMI_AKIS", "WS_BIRLESIK_KOK", "BinanceCokluBarAkisi"]
