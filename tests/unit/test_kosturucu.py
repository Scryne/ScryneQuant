"""Koşturucu ve Binance akış ayrıştırması. (Faz 6, §24, K-006, K-037)

İki ayrı şey test ediliyor ve ikisi de ağsız:

1. **Ayrıştırma** (`bar_cikar`): saf fonksiyon. Kapanmamış barın süzülmesi ve `q`/`n`
   alanlarının taşınması burada ölçülüyor — ikincisi K-023'ün bu fazdaki gerekçesi.
2. **Koşturucu**: sahte bir akışla. `BarAkisi` protokolü tüketici tarafında tanımlı
   (`live/akis.py`) olduğu için sahte akış `exchange/`i hiç import etmiyor.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator

import pytest

from scryne_quant.exchange.akis import akis_adi, bar_cikar
from scryne_quant.live.akis import AkisHatasi, Bar, Kaynak
from scryne_quant.live.depo import KosuOlayi
from scryne_quant.live.kosturucu import Kosturucu, KosturucuHatasi
from scryne_quant.live.toparlanma import toparlan
from tests.unit.test_paper_dongu import barlar, motor_kur


def kline(kapandi: bool = True, **degisiklik) -> dict:
    k = {
        "t": 1_699_999_200_000,
        "T": 1_700_002_799_999,
        "s": "BTCUSDT",
        "i": "1h",
        "o": "30000.0",
        "c": "30100.0",
        "h": "30200.0",
        "l": "29900.0",
        "v": "12.5",
        "q": "376250.0",
        "n": 1234,
        "x": kapandi,
    }
    return {"e": "kline", "E": 1_700_002_800_000, "s": "BTCUSDT", "k": {**k, **degisiklik}}


class TestAyristirma:
    def test_kapanmamis_bar_suzuluyor(self) -> None:
        # Kapanmamış bar stratejiye verilseydi, oluşmakta olan bir kapanışa göre karar
        # verilmiş olurdu — K-004'ün karar tarafındaki ihlali.
        assert bar_cikar(kline(kapandi=False)) is None

    def test_kapanmis_bar_tam_cikiyor(self) -> None:
        bar = bar_cikar(kline())
        assert bar == Bar(
            open_time=1_699_999_200_000,
            open=30000.0,
            high=30200.0,
            low=29900.0,
            close=30100.0,
            volume=12.5,
            quote_volume=376250.0,
            trades=1234,
            kaynak=Kaynak.AKIS,
        )

    def test_quote_hacmi_ve_islem_sayisi_tasiniyor(self) -> None:
        # K-023'ün bu fazdaki gerekçesi: ccxt bu iki alanı düşürüyor, oysa `sifir_hacim`,
        # `negatif_hacim` ve `islemsiz_hacim` kuralları onlara bakıyor (K-006).
        bar = bar_cikar(kline())
        assert bar.quote_volume == 376250.0
        assert bar.trades == 1234

    def test_bozuk_mesaj_sessizce_gecmiyor(self) -> None:
        bozuk = kline()
        del bozuk["k"]["q"]
        with pytest.raises(AkisHatasi, match="ayrıştırılamadı"):
            bar_cikar(bozuk)

    def test_kline_disi_mesaj_none(self) -> None:
        assert bar_cikar({"result": None, "id": 1}) is None

    def test_akis_adi(self) -> None:
        assert akis_adi("BTC/USDT", "1h") == "btcusdt@kline_1h"
        assert akis_adi("BTCUSDT", "15m") == "btcusdt@kline_15m"


class SahteAkis:
    """`BarAkisi` protokolünü uygulayan, önceden belirlenmiş barları veren akış."""

    def __init__(self, bar_listesi: list[Bar], *, gecikme_s: float = 0.0) -> None:
        self._barlar = bar_listesi
        self._gecikme = gecikme_s
        self._kapali = False
        self.kapatildi = False

    @property
    def sembol(self) -> str:
        return "BTCUSDT"

    @property
    def timeframe(self) -> str:
        return "1h"

    def kapat(self) -> None:
        self._kapali = True
        self.kapatildi = True

    async def barlar(self) -> AsyncIterator[Bar]:
        for bar in self._barlar:
            if self._kapali:
                return
            if self._gecikme:
                await asyncio.sleep(self._gecikme)
            yield bar


class PatlayanAkis(SahteAkis):
    def __init__(self, bar_listesi: list[Bar], *, kacinci: int) -> None:
        super().__init__(bar_listesi)
        self._kacinci = kacinci

    async def barlar(self) -> AsyncIterator[Bar]:
        for i, bar in enumerate(self._barlar):
            if i == self._kacinci:
                raise RuntimeError("akış patladı")
            yield bar


def kosturucu_kur(bar_listesi, **kw):
    m = motor_kur({16: ("BUY", 0.25), 30: ("FLAT", 0.0)}, **kw.pop("motor_kw", {}))
    toparlan(m, [])
    return Kosturucu(m, SahteAkis(bar_listesi), yoklama_araligi_s=0.01, **kw)


class TestKosturucu:
    def test_tum_barlar_isleniyor(self) -> None:
        bl = barlar(40)
        k = kosturucu_kur(bl)
        ozet = asyncio.run(k.calistir())
        assert ozet.islenen_bar == 40
        assert ozet.hata is None
        assert k.motor.son_bar_ms == bl[-1].open_time

    def test_basladi_ve_durdu_kayda_yaziliyor(self) -> None:
        k = kosturucu_kur(barlar(5))
        asyncio.run(k.calistir())
        turler = [o["tur"] for o in k.motor.depo.olaylar()]
        assert str(KosuOlayi.BASLADI) in turler
        assert str(KosuOlayi.DURDU) in turler

    def test_bar_kancasi_her_barda_cagriliyor(self) -> None:
        gorulen = []
        k = kosturucu_kur(barlar(10), bar_kancasi=gorulen.append)
        asyncio.run(k.calistir())
        assert len(gorulen) == 10
        assert gorulen[-1].bar_ms == k.motor.son_bar_ms

    def test_hata_kayda_yazilip_yukseltiliyor(self) -> None:
        # Yutulan bir hata, 30 günlük koşuda sessizce duran bir sistem demek.
        m = motor_kur({})
        toparlan(m, [])
        k = Kosturucu(m, PatlayanAkis(barlar(10), kacinci=4), yoklama_araligi_s=0.01)
        with pytest.raises(RuntimeError, match="akış patladı"):
            asyncio.run(k.calistir())
        turler = [o["tur"] for o in m.depo.olaylar()]
        assert str(KosuOlayi.HATA) in turler
        assert str(KosuOlayi.DURDU) in turler
        assert m.depo.kesinti_sayisi() == 1

    def test_durdur_akisi_kapatiyor(self) -> None:
        bl = barlar(50)
        k = kosturucu_kur(bl)
        k.akis._gecikme = 0.001

        async def kos():
            gorev = asyncio.create_task(k.calistir())
            await asyncio.sleep(0.02)
            k.durdur()
            return await gorev

        ozet = asyncio.run(kos())
        assert k.akis.kapatildi
        assert 0 < ozet.islenen_bar < 50

    def test_yoklama_bar_gelmese_de_calisiyor(self) -> None:
        # §24'ün asıl derdi: bayatlık **bar gelmediğinde** anlaşılır.
        m = motor_kur({}, azami_veri_yasi_ms=1)
        toparlan(m, [])
        k = Kosturucu(m, SahteAkis(barlar(3), gecikme_s=0.05), yoklama_araligi_s=0.01)
        asyncio.run(k.calistir())
        turler = [o["tur"] for o in m.depo.olaylar()]
        assert str(KosuOlayi.BAYAT_GIRIS) in turler


class TestYoklamaGozetimi:
    """Bayatlık yoklaması **sessizce** ölmemeli. (§24)

    Gözetim eklenmeden önce `_yoklama_dongusu` ayrı bir `create_task` içindeydi ve
    içinden çıkan bir istisna hiçbir yere ulaşmıyordu: görev ölür, ana döngü barları
    işlemeye devam eder, ve guard kalan koşu boyunca **kör** kalırdı. Dashboard yine
    "sistem sağlıklı" gösterirdi, çünkü gösterdiği şey guard'ın son bildiği durum.

    Bu üç test o sessizliği kapatıyor: hata kayda geçer, koşu durur, ve gerçek kapanış
    sebebi başka bir istisnanın altında kaybolmaz.
    """

    @staticmethod
    def _kirik_yoklama(m, bar_listesi):
        def patla(*_: object, **__: object) -> None:
            raise sqlite3.OperationalError("disk I/O error")

        m.tazelik_kontrol = patla
        return Kosturucu(m, SahteAkis(bar_listesi, gecikme_s=0.05), yoklama_araligi_s=0.01)

    def test_yoklama_hatasi_kosuyu_durduruyor(self) -> None:
        m = motor_kur({})
        toparlan(m, [])
        k = self._kirik_yoklama(m, barlar(40))
        with pytest.raises(KosturucuHatasi, match="bayatlık yoklaması"):
            asyncio.run(k.calistir())
        # Guard kör kaldığı anda duruldu: barların tamamı işlenmedi.
        assert k.islenen_bar < 40

    def test_yoklama_hatasi_kayda_geciyor(self) -> None:
        m = motor_kur({})
        toparlan(m, [])
        k = self._kirik_yoklama(m, barlar(40))
        with pytest.raises(KosturucuHatasi):
            asyncio.run(k.calistir())
        olaylar = m.depo.olaylar()
        hatalar = [o for o in olaylar if o["tur"] == str(KosuOlayi.HATA)]
        assert len(hatalar) == 1
        assert hatalar[0]["ayrinti"]["kaynak"] == "bayatlik_yoklamasi"
        assert "OperationalError" in hatalar[0]["ayrinti"]["hata"]

    def test_durdu_satiri_sebebi_tasiyor(self) -> None:
        """Kapanış satırı boş sebeple yazılsaydı, kesinti açıklanamaz görünürdü."""
        m = motor_kur({})
        toparlan(m, [])
        k = self._kirik_yoklama(m, barlar(40))
        with pytest.raises(KosturucuHatasi):
            asyncio.run(k.calistir())
        durdu = [o for o in m.depo.olaylar() if o["tur"] == str(KosuOlayi.DURDU)]
        assert len(durdu) == 1
        assert "OperationalError" in (durdu[0]["ayrinti"]["hata"] or "")

    def test_saglikli_yoklama_hic_hata_yazmiyor(self) -> None:
        m = motor_kur({})
        toparlan(m, [])
        k = Kosturucu(m, SahteAkis(barlar(3)), yoklama_araligi_s=0.01)
        ozet = asyncio.run(k.calistir())
        assert ozet.hata is None
        assert not [o for o in m.depo.olaylar() if o["tur"] == str(KosuOlayi.HATA)]
