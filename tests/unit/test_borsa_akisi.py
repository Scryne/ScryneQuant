"""`BinanceBarAkisi`: yeniden bağlanma, backoff ve kopma sonrası resync. (§24, Faz 6)

**Bu dosya bir boşluğu kapatıyor.** Faz 6 kapanmadan önce `exchange/akis.py`ten yalnızca
iki saf fonksiyon (`bar_cikar`, `akis_adi`) test ediliyordu; sınıfın kendisi — yani
*"30 gün kesintisiz"* kriterinin doğrudan dayandığı kod — hiç koşturulmamıştı. Kopma
döngüsü, backoff merdiveni, resync ve tekrar süzme, ancak gerçek bir kesinti olduğunda
ilk kez çalışacaktı.

Ağ yok: `aiohttp.ClientSession`in kullanılan yüzeyi (`ws_connect` → async bağlam
yöneticisi → `receive()`) taklit ediliyor. Taklit dar tutuldu; geniş bir sahte, testi
aiohttp'nin davranışı yerine sahtenin davranışına bağlardı.
"""

from __future__ import annotations

import asyncio
import json

import aiohttp
import pandas as pd
import pytest

from scryne_quant.exchange import akis as akis_mod
from scryne_quant.exchange.akis import BinanceBarAkisi
from scryne_quant.exchange.temel import BorsaHatasi
from scryne_quant.live.akis import Kaynak

ADIM = 3_600_000
T0 = 1_700_000_000_000 // ADIM * ADIM


def kline_mesaji(acilis_ms: int, *, kapandi: bool = True) -> str:
    return json.dumps(
        {
            "e": "kline",
            "k": {
                "t": acilis_ms,
                "o": "30000.0",
                "c": "30100.0",
                "h": "30200.0",
                "l": "29900.0",
                "v": "12.5",
                "q": "376250.0",
                "n": 1234,
                "x": kapandi,
            },
        }
    )


class SahteMesaj:
    __slots__ = ("type", "data")

    def __init__(self, tur: aiohttp.WSMsgType, data: str = "") -> None:
        self.type = tur
        self.data = data


def metin(acilis_ms: int, *, kapandi: bool = True) -> SahteMesaj:
    return SahteMesaj(aiohttp.WSMsgType.TEXT, kline_mesaji(acilis_ms, kapandi=kapandi))


KAPANDI = SahteMesaj(aiohttp.WSMsgType.CLOSED)


class SahteWS:
    def __init__(self, mesajlar: list[SahteMesaj]) -> None:
        self._mesajlar = list(mesajlar)

    async def receive(self) -> SahteMesaj:
        if not self._mesajlar:
            # Mesajı biten bir oturum, kapanmış bir bağlantı gibi davranır.
            return KAPANDI
        return self._mesajlar.pop(0)


class SahteBaglanti:
    def __init__(self, ws: SahteWS | BaseException) -> None:
        self._ws = ws

    async def __aenter__(self) -> SahteWS:
        if isinstance(self._ws, BaseException):
            raise self._ws
        return self._ws

    async def __aexit__(self, *_: object) -> bool:
        return False


class SahteOturum:
    """`ClientSession`in bu modülde kullanılan tek yüzeyi: `ws_connect`.

    Her eleman bir **bağlantı denemesi**: ya bir mesaj listesi ya fırlatılacak bir hata.
    """

    def __init__(self, oturumlar: list[list[SahteMesaj] | BaseException]) -> None:
        self._oturumlar = list(oturumlar)
        self.deneme = 0
        self.kapatildi = False

    def ws_connect(self, url: str, **_: object) -> SahteBaglanti:
        self.deneme += 1
        if not self._oturumlar:
            return SahteBaglanti(aiohttp.ClientError("sahte oturum tükendi"))
        sonraki = self._oturumlar.pop(0)
        if isinstance(sonraki, BaseException):
            return SahteBaglanti(sonraki)
        return SahteBaglanti(SahteWS(sonraki))

    async def close(self) -> None:
        self.kapatildi = True


class SahteAdaptor:
    """`_resync`in ihtiyaç duyduğu tek metot. Verilmezse resync yapılamaz."""

    def __init__(self, acilislar: list[int] | None = None, *, hata: bool = False) -> None:
        self.acilislar = acilislar or []
        self.hata = hata
        self.cagrilar: list[tuple[int, int]] = []

    def klines(self, sembol: str, timeframe: str, baslangic: int, bitis: int) -> pd.DataFrame:
        self.cagrilar.append((baslangic, bitis))
        if self.hata:
            raise BorsaHatasi("REST de erişilemiyor")
        return pd.DataFrame(
            [
                {
                    "open_time": t,
                    "open": 30000.0,
                    "high": 30200.0,
                    "low": 29900.0,
                    "close": 30100.0,
                    "volume": 12.5,
                    "quote_volume": 376250.0,
                    "trades": 1234,
                }
                for t in self.acilislar
                if baslangic <= t < bitis
            ]
        )


@pytest.fixture
def uykusuz(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Backoff beklemelerini kaydeder ama uyumaz. Testin süresi eşiklere bağlı olmamalı."""
    kayit: list[float] = []

    async def sahte_uyku(saniye: float) -> None:
        kayit.append(saniye)

    monkeypatch.setattr(akis_mod.asyncio, "sleep", sahte_uyku)
    return kayit


async def topla(akis: BinanceBarAkisi, adet: int) -> list:
    """`adet` bar toplayınca akışı kapatır. Sonsuz döngüyü testte sınırlandıran şey bu."""
    sonuc = []
    async for bar in akis.barlar():
        sonuc.append(bar)
        if len(sonuc) >= adet:
            akis.kapat()
            break
    return sonuc


def akis_kur(oturumlar, **kw) -> tuple[BinanceBarAkisi, SahteOturum]:
    oturum = SahteOturum(oturumlar)
    akis = BinanceBarAkisi("BTCUSDT", "1h", oturum=oturum, **kw)
    return akis, oturum


class TestTeslim:
    def test_kapanmis_barlar_sirayla_geliyor(self, uykusuz: list[float]) -> None:
        akis, _ = akis_kur([[metin(T0), metin(T0 + ADIM)]])
        barlar = asyncio.run(topla(akis, 2))
        assert [b.open_time for b in barlar] == [T0, T0 + ADIM]
        assert all(b.kaynak is Kaynak.AKIS for b in barlar)

    def test_kapanmamis_bar_teslim_edilmiyor_ama_nabiz_sayiliyor(
        self, uykusuz: list[float]
    ) -> None:
        nabizlar: list[int] = []
        akis, _ = akis_kur(
            [[metin(T0, kapandi=False), metin(T0, kapandi=False), metin(T0)]],
            nabiz_kancasi=nabizlar.append,
        )
        barlar = asyncio.run(topla(akis, 1))
        assert [b.open_time for b in barlar] == [T0]
        # Üç mesaj, üç nabız: guard'ın ölçtüğü şey bar değil trafik (K-037/2).
        assert len(nabizlar) == 3

    def test_ayni_bar_ikinci_kez_teslim_edilmiyor(self, uykusuz: list[float]) -> None:
        akis, _ = akis_kur([[metin(T0), metin(T0), metin(T0 + ADIM)]])
        barlar = asyncio.run(topla(akis, 2))
        assert [b.open_time for b in barlar] == [T0, T0 + ADIM]

    def test_geriye_giden_bar_suzuluyor(self, uykusuz: list[float]) -> None:
        akis, _ = akis_kur([[metin(T0 + ADIM), metin(T0), metin(T0 + 2 * ADIM)]])
        barlar = asyncio.run(topla(akis, 2))
        assert [b.open_time for b in barlar] == [T0 + ADIM, T0 + 2 * ADIM]


class TestKopma:
    def test_kopma_kancasi_sebebiyle_cagriliyor(self, uykusuz: list[float]) -> None:
        sebepler: list[str] = []
        akis, _ = akis_kur(
            [[metin(T0), KAPANDI], [metin(T0 + ADIM)]], kopma_kancasi=sebepler.append
        )
        asyncio.run(topla(akis, 2))
        assert len(sebepler) == 1
        assert "CLOSED" in sebepler[0]

    def test_yeniden_baglandi_ancak_trafik_donunce_bildiriliyor(
        self, uykusuz: list[float]
    ) -> None:
        """Bağlantının kurulması yetmez: el sıkışıp susan bir uç kesintiyi kapatamaz."""
        bildirimler: list[dict] = []
        akis, _ = akis_kur(
            [
                [metin(T0), KAPANDI],
                [],  # bağlanıyor ama hiç mesaj yok → hâlâ kopuk
                [metin(T0 + ADIM)],
            ],
            yeniden_baglanma_kancasi=bildirimler.append,
        )
        asyncio.run(topla(akis, 2))
        assert len(bildirimler) == 1
        assert bildirimler[0]["son_teslim_ms"] == T0

    def test_yeniden_baglanma_resync_barlarini_sayiyor(self, uykusuz: list[float]) -> None:
        bildirimler: list[dict] = []
        adaptor = SahteAdaptor([T0 + ADIM, T0 + 2 * ADIM])
        akis, _ = akis_kur(
            [[metin(T0), KAPANDI], [metin(T0 + 3 * ADIM)]],
            adaptor=adaptor,
            yeniden_baglanma_kancasi=bildirimler.append,
        )
        barlar = asyncio.run(topla(akis, 4))
        assert [b.open_time for b in barlar] == [T0, T0 + ADIM, T0 + 2 * ADIM, T0 + 3 * ADIM]
        assert bildirimler[0]["resync_bar"] == 2

    def test_kopma_basina_tek_yeniden_baglanma(self, uykusuz: list[float]) -> None:
        bildirimler: list[dict] = []
        akis, _ = akis_kur(
            [[metin(T0), KAPANDI], [metin(T0 + ADIM), metin(T0 + 2 * ADIM)]],
            yeniden_baglanma_kancasi=bildirimler.append,
        )
        asyncio.run(topla(akis, 3))
        assert len(bildirimler) == 1

    def test_kapatilan_akis_yeniden_baglanmiyor(self, uykusuz: list[float]) -> None:
        akis, oturum = akis_kur([[metin(T0), KAPANDI]])
        asyncio.run(topla(akis, 1))
        assert oturum.deneme == 1


class TestBackoff:
    def test_baglanamayan_denemelerde_merdiven_tirmaniyor(self, uykusuz: list[float]) -> None:
        hata = aiohttp.ClientError("bağlanamadı")
        akis, _ = akis_kur([[metin(T0), KAPANDI], hata, hata, hata, [metin(T0 + ADIM)]])
        asyncio.run(topla(akis, 2))
        # İlk kopmada trafik görülmüştü → 1.0; sonraki üç deneme hiç mesaj almadı.
        assert uykusuz[:4] == list(akis_mod.BACKOFF[:4])

    def test_trafik_goren_oturum_merdiveni_sifirliyor(self, uykusuz: list[float]) -> None:
        """1h'te barlar saatte bir kapanır; ölçüt bar değil mesaj olmalı.

        Sayaç yalnızca teslim edilen barda sıfırlansaydı, aşağıdaki üç kopmanın hepsi
        ardışık başarısızlık sayılır ve bekleme 1 → 2 → 5 diye tırmanırdı — oysa her
        oturumda trafik vardı.
        """
        kapanmamis = [metin(T0, kapandi=False), KAPANDI]
        akis, _ = akis_kur([list(kapanmamis), list(kapanmamis), list(kapanmamis), [metin(T0)]])
        asyncio.run(topla(akis, 1))
        assert uykusuz[:3] == [akis_mod.BACKOFF[0]] * 3

    def test_merdiven_tavanda_duruyor(self, uykusuz: list[float]) -> None:
        hata = aiohttp.ClientError("bağlanamadı")
        akis, _ = akis_kur([*([hata] * 9), [metin(T0)]])
        asyncio.run(topla(akis, 1))
        assert uykusuz[-1] == akis_mod.BACKOFF[-1]
        assert max(uykusuz) == akis_mod.BACKOFF[-1]


class TestResync:
    def test_resync_barlari_backfill_isaretli(self, uykusuz: list[float]) -> None:
        """K-028'in canlıdaki dayanağı: bağlı olmadığımız sürede fill iddia edilmez."""
        adaptor = SahteAdaptor([T0 + ADIM])
        akis, _ = akis_kur([[metin(T0), KAPANDI], [metin(T0 + 2 * ADIM)]], adaptor=adaptor)
        barlar = asyncio.run(topla(akis, 3))
        kaynaklar = {b.open_time: b.kaynak for b in barlar}
        assert kaynaklar[T0] is Kaynak.AKIS
        assert kaynaklar[T0 + ADIM] is Kaynak.BACKFILL
        assert kaynaklar[T0 + 2 * ADIM] is Kaynak.AKIS

    def test_resync_son_teslimden_sonrasini_istiyor(self, uykusuz: list[float]) -> None:
        adaptor = SahteAdaptor([])
        akis, _ = akis_kur([[metin(T0), KAPANDI], [metin(T0 + ADIM)]], adaptor=adaptor)
        asyncio.run(topla(akis, 2))
        assert adaptor.cagrilar[0][0] == T0 + ADIM

    def test_adaptor_yoksa_resync_yok_ve_akis_devam_ediyor(self, uykusuz: list[float]) -> None:
        akis, _ = akis_kur([[metin(T0), KAPANDI], [metin(T0 + 2 * ADIM)]])
        barlar = asyncio.run(topla(akis, 2))
        # Boşluk uydurulmuyor; T0+ADIM hiç gelmiyor ve pencere onu `gap` işaretleyecek.
        assert [b.open_time for b in barlar] == [T0, T0 + 2 * ADIM]

    def test_rest_de_erisilemiyorsa_bosluk_bosluk_kaliyor(self, uykusuz: list[float]) -> None:
        adaptor = SahteAdaptor([T0 + ADIM], hata=True)
        akis, _ = akis_kur([[metin(T0), KAPANDI], [metin(T0 + 2 * ADIM)]], adaptor=adaptor)
        barlar = asyncio.run(topla(akis, 2))
        assert [b.open_time for b in barlar] == [T0, T0 + 2 * ADIM]

    def test_resync_tekrar_eden_bari_suzuyor(self, uykusuz: list[float]) -> None:
        adaptor = SahteAdaptor([T0, T0 + ADIM])
        akis, _ = akis_kur([[metin(T0), KAPANDI], [metin(T0 + 2 * ADIM)]], adaptor=adaptor)
        barlar = asyncio.run(topla(akis, 3))
        assert [b.open_time for b in barlar] == [T0, T0 + ADIM, T0 + 2 * ADIM]


class TestOturumOmru:
    def test_disaridan_verilen_oturum_kapatilmiyor(self, uykusuz: list[float]) -> None:
        akis, oturum = akis_kur([[metin(T0)]])
        asyncio.run(topla(akis, 1))
        asyncio.run(akis.temizle())
        assert oturum.kapatildi is False

    def test_kendi_actigi_oturum_kapatiliyor(self) -> None:
        akis = BinanceBarAkisi("BTCUSDT", "1h")
        oturum = SahteOturum([])
        akis._oturum = oturum  # noqa: SLF001 - ömür testinin ölçtüğü şey bu alan
        asyncio.run(akis.temizle())
        assert oturum.kapatildi is True

    def test_kapat_iki_kez_cagrilabiliyor(self) -> None:
        akis = BinanceBarAkisi("BTCUSDT", "1h")
        akis.kapat()
        akis.kapat()
