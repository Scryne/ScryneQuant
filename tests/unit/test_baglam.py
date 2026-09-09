"""`ctx` sözleşmesinin geri kalanı. (K-002, K-005, K-006)

Geleceğe erişimin engellenmesi `test_look_ahead.py`'de. Burada kalan: görünümün
kurulumu, ısınma sorgusu, kimlik alanları ve değişmezlik.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.features.motor import OzellikTanimi, hesapla
from scryne_quant.strategy.baglam import (
    DUZ,
    BilinmeyenAlan,
    GecmisYok,
    PiyasaGorunumu,
    PozisyonDurumu,
)
from tests.conftest import bar_uret

TANIMLAR = [
    OzellikTanimi("hizli", "sma", {"pencere": 10}),
    OzellikTanimi("bb", "bollinger", {"pencere": 20, "katsayi": 2.0}),
]


@pytest.fixture
def gorunum() -> PiyasaGorunumu:
    d = bar_dizileri(bar_uret(n=300, tohum=5))
    return PiyasaGorunumu("BTCUSDT", "1h", d, hesapla(d, TANIMLAR))


class TestGorunumKurulumu:
    def test_uzunluk(self, gorunum: PiyasaGorunumu):
        assert len(gorunum) == 300

    def test_eksik_bar_alani(self):
        d = bar_dizileri(bar_uret(n=50))
        del d["high"]
        with pytest.raises(BilinmeyenAlan, match="eksik"):
            PiyasaGorunumu("BTCUSDT", "1h", d)

    def test_kalite_alani_zorunlu(self):
        """`ctx.kalite` K-006'nın bayrağını okuyor; alan yoksa sessizce kaybolurdu."""
        d = bar_dizileri(bar_uret(n=50))
        del d["quality_status"]
        with pytest.raises(BilinmeyenAlan, match="quality_status"):
            PiyasaGorunumu("BTCUSDT", "1h", d)

    def test_uzunluk_uyusmazligi(self):
        d = bar_dizileri(bar_uret(n=50))
        with pytest.raises(ValueError, match="uzunluk"):
            PiyasaGorunumu("BTCUSDT", "1h", d, {"kisa": np.zeros(10)})

    def test_ozellik_adi_bar_alaniyla_cakisamaz(self):
        d = bar_dizileri(bar_uret(n=50))
        with pytest.raises(ValueError, match="çakışıyor"):
            PiyasaGorunumu("BTCUSDT", "1h", d, {"close": np.zeros(50)})

    def test_aralik_disi_indeks(self, gorunum: PiyasaGorunumu):
        with pytest.raises(IndexError):
            gorunum.baglam(300)
        with pytest.raises(IndexError):
            gorunum.baglam(-1)

    def test_akis_her_bari_bir_kez_veriyor(self, gorunum: PiyasaGorunumu):
        zamanlar = [ctx.zaman for ctx in gorunum.akis()]
        assert len(zamanlar) == len(gorunum)
        assert zamanlar == sorted(zamanlar)
        assert len(set(zamanlar)) == len(zamanlar)

    def test_akis_baslangictan_itibaren(self, gorunum: PiyasaGorunumu):
        assert len(list(gorunum.akis(baslangic=290))) == 10


class TestOkuma:
    def test_geri_sifir_su_anki_bar(self, gorunum: PiyasaGorunumu):
        ctx = gorunum.baglam(100)
        assert ctx.bar("close") == float(gorunum.barlar["close"][100])
        assert ctx.bar("close", 3) == float(gorunum.barlar["close"][97])

    def test_zaman_bar_acilisi(self, gorunum: PiyasaGorunumu):
        """K-005: bar timestamp'i açılış zamanıdır, sinyal de ona bağlanır."""
        ctx = gorunum.baglam(100)
        assert ctx.zaman == int(gorunum.barlar["open_time"][100])

    def test_uzunluk_gorulen_bar_sayisi(self, gorunum: PiyasaGorunumu):
        assert gorunum.baglam(0).uzunluk == 1
        assert gorunum.baglam(99).uzunluk == 100

    def test_kalite_bayragi(self, gorunum: PiyasaGorunumu):
        assert gorunum.baglam(5).kalite == KaliteDurumu.OK

    def test_bilinmeyen_alan(self, gorunum: PiyasaGorunumu):
        with pytest.raises(BilinmeyenAlan):
            gorunum.baglam(10).bar("kapanis")

    def test_bilinmeyen_ozellik_mevcutlari_soyluyor(self, gorunum: PiyasaGorunumu):
        with pytest.raises(BilinmeyenAlan, match="hizli"):
            gorunum.baglam(10).ozellik("yavas")

    def test_kimlik_alanlari(self, gorunum: PiyasaGorunumu):
        ctx = gorunum.baglam(10)
        assert ctx.sembol == "BTCUSDT"
        assert ctx.timeframe == "1h"


class TestIsinma:
    def test_isinma_bolgesinde_nan(self, gorunum: PiyasaGorunumu):
        assert np.isnan(gorunum.baglam(3).ozellik("hizli"))

    def test_hazir_isinmayi_bildiriyor(self, gorunum: PiyasaGorunumu):
        assert not gorunum.baglam(8).hazir("hizli")
        assert gorunum.baglam(9).hazir("hizli")

    def test_hazir_coklu_ozellik(self, gorunum: PiyasaGorunumu):
        assert gorunum.baglam(15).hazir("hizli")
        assert not gorunum.baglam(15).hazir("hizli", "bb_ust")
        assert gorunum.baglam(25).hazir("hizli", "bb_ust", "bb_alt")

    def test_hazir_geriye_bakabiliyor(self, gorunum: PiyasaGorunumu):
        assert gorunum.baglam(10).hazir("hizli", geri=1)
        assert not gorunum.baglam(9).hazir("hizli", geri=1)

    def test_hazir_gecmis_yoksa_false(self, gorunum: PiyasaGorunumu):
        """Seri başında `hazir` hata değil `False` vermeli; ilk barda çağrılıyor."""
        assert not gorunum.baglam(2).hazir("hizli", geri=50)


class TestSeri:
    def test_seri_sonu_su_anki_bar(self, gorunum: PiyasaGorunumu):
        ctx = gorunum.baglam(100)
        seri = ctx.bar_serisi("close", 5)
        assert seri.size == 5
        assert seri[-1] == ctx.bar("close")
        assert seri[0] == ctx.bar("close", 4)

    def test_ozellik_serisi(self, gorunum: PiyasaGorunumu):
        ctx = gorunum.baglam(100)
        seri = ctx.ozellik_serisi("hizli", 3)
        assert seri[-1] == ctx.ozellik("hizli")

    def test_yetersiz_gecmis(self, gorunum: PiyasaGorunumu):
        with pytest.raises(GecmisYok):
            gorunum.baglam(5).bar_serisi("close", 10)

    def test_sifir_uzunluk(self, gorunum: PiyasaGorunumu):
        with pytest.raises(ValueError):
            gorunum.baglam(50).bar_serisi("close", 0)


class TestPozisyon:
    def test_varsayilan_duz(self, gorunum: PiyasaGorunumu):
        ctx = gorunum.baglam(10)
        assert ctx.pozisyon == DUZ
        assert not ctx.pozisyon.acik

    def test_verilen_pozisyon_gorunuyor(self, gorunum: PiyasaGorunumu):
        p = PozisyonDurumu(miktar=0.5, ortalama_maliyet=30_000.0, exposure=0.2, giris_ms=1)
        ctx = gorunum.baglam(10, p)
        assert ctx.pozisyon.acik
        assert ctx.pozisyon.exposure == 0.2

    def test_pozisyon_degistirilemez(self, gorunum: PiyasaGorunumu):
        with pytest.raises(AttributeError):
            gorunum.baglam(10).pozisyon.miktar = 1.0


class TestDegismezlik:
    def test_baglam_alan_eklenemez(self, gorunum: PiyasaGorunumu):
        """Strateji `ctx`'e durum saklayamamalı: ctx barlar arası taşınan bir kap değil."""
        ctx = gorunum.baglam(10)
        with pytest.raises((AttributeError, TypeError)):
            ctx.gizli_durum = 1

    def test_baglam_alanlari_yeniden_baglanamaz(self, gorunum: PiyasaGorunumu):
        ctx = gorunum.baglam(10)
        with pytest.raises((AttributeError, TypeError)):
            ctx.pozisyon = DUZ

    def test_parametreler_degistirilemez(self, gorunum: PiyasaGorunumu):
        ctx = gorunum.baglam(10, DUZ, {"hizli": 10})
        assert ctx.parametreler["hizli"] == 10
        with pytest.raises(TypeError):
            ctx.parametreler["hizli"] = 99

    def test_gorunum_sozlukleri_degistirilemez(self, gorunum: PiyasaGorunumu):
        with pytest.raises(TypeError):
            gorunum.ozellikler["yeni"] = np.zeros(300)

    def test_farkli_baglamlar_bagimsiz(self, gorunum: PiyasaGorunumu):
        """Strateji elinde tuttuğu bir ctx'in altından verinin kaymadığını varsayabilmeli."""
        a = gorunum.baglam(10)
        b = gorunum.baglam(200)
        assert a.uzunluk == 11
        assert b.uzunluk == 201
        assert a.zaman != b.zaman
