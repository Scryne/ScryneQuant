"""Düzgün durdurma: bayrak dosyası ve koşturucunun ona verdiği cevap. (Faz 6)

Ölçülen şey tek bir cümle: **planlı bir duruş kesinti sayılmamalı.** Sert kill'den başka
bir yol yokken, kodu düzeltmek için yapılan her yeniden başlatma `temiz_kapanmadi` olarak
kesintiye yazılıyordu — yani *"30 gün kesintisiz"* kriteri, ölçmek istediği şeyi (altyapı
beklenmedik şekilde düştü mü) değil, makinenin hiç yeniden başlatılmamış olmasını ölçerdi.
"""

from __future__ import annotations

import asyncio

from scryne_quant.live import durdurma
from scryne_quant.live.depo import KESINTI_OLAYLARI, KosuOlayi
from scryne_quant.live.kosturucu import Kosturucu
from scryne_quant.live.toparlanma import toparlan
from tests.unit.test_kosturucu import SahteAkis
from tests.unit.test_paper_dongu import barlar, motor_kur


class TestBayrak:
    def test_istek_yoksa_none(self, tmp_path) -> None:
        assert durdurma.istek(tmp_path / "k.sqlite") is None

    def test_sebep_dosyada_tasiniyor(self, tmp_path) -> None:
        yol = tmp_path / "k.sqlite"
        durdurma.dur_iste(yol, sebep="kod güncellemesi")
        istek = durdurma.istek(yol)
        assert istek is not None
        assert istek["sebep"] == "kod güncellemesi"
        assert "istendi_utc" in istek

    def test_bozuk_bayrak_yine_de_istek_sayiliyor(self, tmp_path) -> None:
        """Bayrağın **varlığı** niyettir; içeriği yalnızca kaydın zenginliği.

        Ayrıştırılamayan bir dosyayı yok saymak, durdurma isteğini bir JSON ayrıntısına
        bağlamak olurdu — durdurulamayan bir koşu, kaydı eksik bir koşudan kötüdür.
        """
        yol = tmp_path / "k.sqlite"
        durdurma.bayrak_yolu(yol).write_text("{yarım", encoding="utf-8")
        istek = durdurma.istek(yol)
        assert istek is not None
        assert "bilinmiyor" in istek["sebep"]

    def test_temizle_iki_kez_cagrilabiliyor(self, tmp_path) -> None:
        yol = tmp_path / "k.sqlite"
        durdurma.dur_iste(yol)
        durdurma.temizle(yol)
        durdurma.temizle(yol)
        assert durdurma.istek(yol) is None

    def test_bayrak_kosu_dosyasinin_yaninda(self, tmp_path) -> None:
        yol = tmp_path / "gozlem-1.sqlite"
        assert durdurma.bayrak_yolu(yol) == tmp_path / "gozlem-1.sqlite.dur"


def _kosturucu(m, bar_listesi, istek):
    return Kosturucu(
        m,
        SahteAkis(bar_listesi, gecikme_s=0.02),
        yoklama_araligi_s=0.01,
        durdurma_istegi=istek,
    )


class TestKosturucuCevabi:
    def test_istek_dongunun_durmasini_sagliyor(self) -> None:
        m = motor_kur({})
        toparlan(m, [])
        k = _kosturucu(m, barlar(200), lambda: {"sebep": "kod güncellemesi"})
        ozet = asyncio.run(k.calistir())
        assert ozet.islenen_bar < 200

    def test_duzgun_durus_kesinti_saymiyor(self) -> None:
        """Kriterin tam kalbi: `durdu` yazılır, `temiz_kapanmadi` yazılmaz."""
        m = motor_kur({})
        toparlan(m, [])
        k = _kosturucu(m, barlar(200), lambda: {"sebep": "kod güncellemesi"})
        asyncio.run(k.calistir())
        turler = [o["tur"] for o in m.depo.olaylar()]
        assert str(KosuOlayi.DURDU) in turler
        assert m.depo.kesinti_sayisi() == 0
        assert KosuOlayi.DURDU not in KESINTI_OLAYLARI

    def test_sebep_durdu_satirina_yaziliyor(self) -> None:
        m = motor_kur({})
        toparlan(m, [])
        k = _kosturucu(m, barlar(200), lambda: {"sebep": "disk değişimi"})
        asyncio.run(k.calistir())
        durdu = [o for o in m.depo.olaylar() if o["tur"] == str(KosuOlayi.DURDU)]
        assert durdu[0]["ayrinti"]["sebep"] == "disk değişimi"

    def test_istek_yokken_kosu_normal_bitiyor(self) -> None:
        m = motor_kur({})
        toparlan(m, [])
        k = Kosturucu(
            m, SahteAkis(barlar(5)), yoklama_araligi_s=0.01, durdurma_istegi=lambda: None
        )
        ozet = asyncio.run(k.calistir())
        assert ozet.islenen_bar == 5
        durdu = [o for o in m.depo.olaylar() if o["tur"] == str(KosuOlayi.DURDU)]
        assert durdu[0]["ayrinti"]["sebep"] is None

    def test_kanca_verilmezse_hicbir_sey_degismiyor(self) -> None:
        m = motor_kur({})
        toparlan(m, [])
        k = Kosturucu(m, SahteAkis(barlar(5)), yoklama_araligi_s=0.01)
        assert asyncio.run(k.calistir()).islenen_bar == 5
