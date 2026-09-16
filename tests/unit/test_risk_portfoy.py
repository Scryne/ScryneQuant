"""Risk motorunun portföy düzeyi: brüt maruziyet, enstrüman sayısı, ve "izin veremez".

K-037 bu fazın en kolay ihlal edilen kuralı: *"Engelleyen katman risk motorunun dışında
olabilir; izin veren katman olamaz."* Çok enstrümanlıda portföy kurma katmanı ağırlık
üretiyor ve o ağırlıklar bir onay gibi **görünüyor**. Bu dosya onların onay olmadığını
ölçüyor.

İkinci konu sıra: sinyal düzeyindeki 0-8 adımı **önce**, portföy tavanları **sonra**. Ters
sırada, sinyal düzeyinde reddedilecek bir hedef brüt bütçeden yer kaplar ve geçecek bir
hedefi sessizce kısardı.
"""

from __future__ import annotations

import pytest

from scryne_quant.risk.motor import PiyasaOlcumu, RiskMotoru
from scryne_quant.risk.niyet import OnayliNiyet, Red, RedSebebi
from scryne_quant.strategy.hedef import hedef_kur
from scryne_quant.strategy.sinyal import Sinyal, Yon
from tests.conftest import risk_limitleri

ZAMAN = 1_699_999_200_000


def _sinyal(sembol: str, hedef: float, *, yon: Yon = Yon.BUY, guven: float = 0.5) -> Sinyal:
    return Sinyal(
        symbol=sembol,
        side=yon,
        target_exposure=hedef,
        confidence=guven,
        reason="TEST_HEDEF",
        timestamp=ZAMAN,
    )


def _olcum(
    fiyat: float = 100.0, maruziyet: float = 0.0, atr: float | None = 0.05
) -> PiyasaOlcumu:
    """Varsayılan ATR bilinçli olarak **küçük**: `islem_basina_risk` tavanı bağlamasın.

    Bağlasaydı bu dosyadaki her sayı iki limitin bileşkesi olurdu ve portföy tavanının
    ne yaptığı görünmezdi. Boyutlandırmanın kendi testi `test_risk_limitleri.py`de.
    """
    return PiyasaOlcumu(
        fiyat=fiyat,
        ozkaynak=10_000.0,
        mevcut_maruziyet=maruziyet,
        bar_ms=ZAMAN,
        atr=atr,
    )


def _motor(**limit_degisikligi) -> RiskMotoru:
    """Promotion kapısını geçmiş, backtest modunda bir motor.

    `backtest` modu `MOD_ESIGI`nde `YOK` eşiğinde: bu dosyanın ölçtüğü şey promotion değil,
    portföy tavanları. Promotion'un kendi testi `test_promotion.py`de.
    """
    return RiskMotoru(risk_limitleri(**limit_degisikligi), "1h")


class TestBrutMaruziyet:
    def test_tavan_hedefleri_asagi_cekiyor(self):
        motor = _motor(azami_maruziyet=1.0, azami_brut_maruziyet=0.6)
        hedef = hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.5), _sinyal("BBBUSDT", 0.5)])
        karar = motor.portfoy_degerlendir(
            hedef,
            {"AAAUSDT": _olcum(), "BBBUSDT": _olcum()},
            mevcut_maruziyetler={},
        )
        toplam = sum(o.onayli_maruziyet for o in karar.onaylar)
        assert toplam == pytest.approx(0.6)
        assert "azami_brut_maruziyet" in karar.portfoy_kisiti
        assert all("azami_brut_maruziyet" in o.kisitlayan for o in karar.onaylar)

    def test_tavan_yukari_cekmiyor(self):
        """İzin veren katman yok: bol bütçe hedefleri büyütmez."""
        motor = _motor(azami_maruziyet=1.0, azami_brut_maruziyet=1.0)
        hedef = hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.1)])
        karar = motor.portfoy_degerlendir(
            hedef, {"AAAUSDT": _olcum()}, mevcut_maruziyetler={}
        )
        assert karar.onaylar[0].onayli_maruziyet == pytest.approx(0.1)
        assert not karar.portfoy_kisiti

    def test_bahsedilmeyen_pozisyon_da_butceyi_tuketiyor(self):
        """Portföyün yarısını görmeyen bir tavan, tavan değildir."""
        motor = _motor(azami_maruziyet=1.0, azami_brut_maruziyet=0.6)
        hedef = hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.5)])
        karar = motor.portfoy_degerlendir(
            hedef,
            {"AAAUSDT": _olcum()},
            mevcut_maruziyetler={"CCCUSDT": 0.4},
        )
        assert karar.onaylar[0].onayli_maruziyet == pytest.approx(0.2)

    def test_azaltan_niyet_tavandan_etkilenmiyor(self):
        """Brüt maruziyeti düşüren bir emri brüt maruziyet limitiyle engellemek saçmadır."""
        motor = _motor(azami_brut_maruziyet=0.1)
        hedef = hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.0, yon=Yon.FLAT)])
        karar = motor.portfoy_degerlendir(
            hedef,
            {"AAAUSDT": _olcum(maruziyet=0.8)},
            mevcut_maruziyetler={"AAAUSDT": 0.8},
        )
        assert isinstance(karar.kararlar[0], OnayliNiyet)
        assert not karar.portfoy_kisiti

    def test_butce_bitince_red(self):
        motor = _motor(azami_maruziyet=1.0, azami_brut_maruziyet=0.5)
        hedef = hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.5)])
        karar = motor.portfoy_degerlendir(
            hedef, {"AAAUSDT": _olcum()}, mevcut_maruziyetler={"CCCUSDT": 0.5}
        )
        red = karar.kararlar[0]
        assert isinstance(red, Red) and red.sebep is RedSebebi.BRUT_MARUZIYET

    def test_tavan_mevcudun_altina_zorlamiyor(self):
        """Tavan bir **satış emri** üretmez: stratejinin istemediği çıkışı risk yazamaz."""
        motor = _motor(azami_maruziyet=1.0, azami_brut_maruziyet=0.4)
        hedef = hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.9)])
        karar = motor.portfoy_degerlendir(
            hedef,
            {"AAAUSDT": _olcum(maruziyet=0.7)},
            mevcut_maruziyetler={"AAAUSDT": 0.7},
        )
        assert karar.onaylar[0].onayli_maruziyet == pytest.approx(0.7)


class TestEnstrumanSayisi:
    def test_tavan_yeni_girisleri_eliyor(self):
        motor = _motor(azami_maruziyet=1.0, azami_enstruman=2)
        hedef = hedef_kur(
            ZAMAN,
            [
                _sinyal("AAAUSDT", 0.2, guven=0.9),
                _sinyal("BBBUSDT", 0.2, guven=0.7),
                _sinyal("CCCUSDT", 0.2, guven=0.3),
            ],
        )
        karar = motor.portfoy_degerlendir(
            hedef,
            {s: _olcum() for s in ("AAAUSDT", "BBBUSDT", "CCCUSDT")},
            mevcut_maruziyetler={},
        )
        onaylananlar = {o.sinyal.symbol for o in karar.onaylar}
        assert onaylananlar == {"AAAUSDT", "BBBUSDT"}
        red = next(k for k in karar.kararlar if isinstance(k, Red))
        assert red.sebep is RedSebebi.ENSTRUMAN_SAYISI
        assert red.sinyal.symbol == "CCCUSDT"

    def test_mevcut_pozisyonlar_elenmiyor(self):
        """Tavan dolu olsa bile açık pozisyonlara dokunulmaz; yalnızca yeni giriş kapanır."""
        motor = _motor(azami_maruziyet=1.0, azami_enstruman=1)
        hedef = hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.3), _sinyal("BBBUSDT", 0.3)])
        karar = motor.portfoy_degerlendir(
            hedef,
            {"AAAUSDT": _olcum(maruziyet=0.3), "BBBUSDT": _olcum()},
            mevcut_maruziyetler={"AAAUSDT": 0.3},
        )
        assert {o.sinyal.symbol for o in karar.onaylar} == {"AAAUSDT"}

    def test_cikislar_hicbir_zaman_engellenmiyor(self):
        motor = _motor(azami_enstruman=1)
        hedef = hedef_kur(
            ZAMAN,
            [
                _sinyal("AAAUSDT", 0.0, yon=Yon.FLAT),
                _sinyal("BBBUSDT", 0.0, yon=Yon.FLAT),
            ],
        )
        karar = motor.portfoy_degerlendir(
            hedef,
            {"AAAUSDT": _olcum(maruziyet=0.3), "BBBUSDT": _olcum(maruziyet=0.3)},
            mevcut_maruziyetler={"AAAUSDT": 0.3, "BBBUSDT": 0.3},
        )
        assert len(karar.onaylar) == 2

    def test_eleme_guvene_gore_ve_deterministik(self):
        """Eşit güvende sembol adı bozar: aynı girdi iki koşuda aynı portföyü vermeli."""
        motor = _motor(azami_maruziyet=1.0, azami_enstruman=1)
        hedef = hedef_kur(
            ZAMAN, [_sinyal("BBBUSDT", 0.2, guven=0.5), _sinyal("AAAUSDT", 0.2, guven=0.5)]
        )
        olcumler = {"AAAUSDT": _olcum(), "BBBUSDT": _olcum()}
        a = motor.portfoy_degerlendir(hedef, olcumler, mevcut_maruziyetler={})
        b = _motor(azami_maruziyet=1.0, azami_enstruman=1).portfoy_degerlendir(
            hedef, olcumler, mevcut_maruziyetler={}
        )
        assert [o.sinyal.symbol for o in a.onaylar] == [o.sinyal.symbol for o in b.onaylar]
        assert {o.sinyal.symbol for o in a.onaylar} == {"AAAUSDT"}


class TestSira:
    def test_sinyal_duzeyi_redleri_butceden_yer_kaplamiyor(self):
        """Volatilite guard'ında düşen bir hedef, geçen hedefin bütçesini yemez."""
        motor = _motor(azami_maruziyet=1.0, azami_brut_maruziyet=0.5, volatilite_esigi=0.01)
        hedef = hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.5), _sinyal("BBBUSDT", 0.5)])
        karar = motor.portfoy_degerlendir(
            hedef,
            {"AAAUSDT": _olcum(atr=0.05), "BBBUSDT": _olcum(atr=5.0)},  # BBB guard'da düşer
            mevcut_maruziyetler={},
        )
        onay = {o.sinyal.symbol: o.onayli_maruziyet for o in karar.onaylar}
        assert set(onay) == {"AAAUSDT"}
        assert onay["AAAUSDT"] == pytest.approx(0.5)
        assert not karar.portfoy_kisiti

    def test_her_sinyal_icin_bir_karar_var(self):
        """Sinyal kaybolmaz: kararlar hedefle aynı sırada ve aynı uzunlukta."""
        motor = _motor(azami_maruziyet=1.0, azami_enstruman=1)
        hedef = hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.2), _sinyal("BBBUSDT", 0.2)])
        karar = motor.portfoy_degerlendir(
            hedef,
            {"AAAUSDT": _olcum(), "BBBUSDT": _olcum()},
            mevcut_maruziyetler={},
        )
        assert len(karar.kararlar) == len(hedef.sinyaller)
        assert [k.sinyal.symbol for k in karar.kararlar] == list(hedef.semboller)

    def test_olcumsuz_sembol_reddediliyor(self):
        """Ölçümü olmayan bir hedefe karar verilmez; sessizce atlanmaz."""
        motor = _motor()
        hedef = hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.2)])
        with pytest.raises(Exception, match="piyasa ölçümü verilmedi"):
            motor.portfoy_degerlendir(hedef, {}, mevcut_maruziyetler={})

    def test_audit_her_karari_kaydediyor(self):
        from scryne_quant.risk.audit import SqliteDefter

        defter = SqliteDefter(":memory:")
        motor = RiskMotoru(risk_limitleri(azami_enstruman=1), "1h", defter=defter)
        hedef = hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.2), _sinyal("BBBUSDT", 0.2)])
        motor.portfoy_degerlendir(
            hedef,
            {"AAAUSDT": _olcum(), "BBBUSDT": _olcum()},
            mevcut_maruziyetler={},
        )
        assert motor.degerlendirilen == 2
        assert motor.onay_sayisi + sum(motor.red_sayimi.values()) == 2
        defter.kapat()


class TestKurmaIzinVeremez:
    """Portföy kurma bir öneri üretir; onay yalnızca risk motorundan çıkar (K-037)."""

    def test_kurmanin_agirligi_risk_tavanini_asamaz(self):
        from scryne_quant.strategy.kurma import Aday, KurmaAyarlari, kur

        # Kurma katmanı %80 istiyor; risk motorunun tek enstrüman tavanı %30.
        ayarlar = KurmaAyarlari(azami_enstruman=1, azami_agirlik=0.8, hedef_brut=0.8)
        hedef = kur(ZAMAN, [Aday("AAAUSDT", 1.0, 0.02)], ayarlar)
        assert hedef.sinyaller[0].target_exposure == pytest.approx(0.8)

        motor = _motor(azami_maruziyet=0.3)
        karar = motor.portfoy_degerlendir(
            hedef, {"AAAUSDT": _olcum()}, mevcut_maruziyetler={}
        )
        assert karar.onaylar[0].onayli_maruziyet <= 0.3
        assert "azami_maruziyet" in karar.onaylar[0].kisitlayan


class TestMotorYolu:
    """Kararın motora bağlandığı yer: onaylanmayan hedef **fill üretemez**."""

    def _kosu(self, mod: str):
        import numpy as np

        from scryne_quant.backtest.coklu_motor import CokluBacktest
        from scryne_quant.common.maliyet import MaliyetModeli
        from scryne_quant.features.barlar import bar_dizileri
        from scryne_quant.strategy.kosu import evren_gorunum_kur
        from tests.conftest import PlanliHedef, bar_uret

        n = 120
        diziler = {
            "AAAUSDT": bar_dizileri(bar_uret(n=n, tohum=3)),
            "BBBUSDT": bar_dizileri(bar_uret(n=n, tohum=4)),
        }
        uyelik = {s: np.ones(n, dtype=bool) for s in diziler}
        strateji = PlanliHedef({40: {"AAAUSDT": 0.2, "BBBUSDT": 0.2}})
        gorunum = evren_gorunum_kur("1h", diziler, uyelik, strateji)
        motor = RiskMotoru(risk_limitleri(), "1h", mod=mod)
        return CokluBacktest(
            strateji,
            MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0),
            risk=motor,
        ).calistir(gorunum)

    def test_promotion_gecmeyen_strateji_fill_uretemiyor(self):
        """`paper` modunda promotion kaydı olmayan strateji reddedilir (K-010).

        Ölçülen şey kararın kendisi değil, kararın **motora bağlı** olduğu: red edilen
        hedef `bekleyen`e girmiyor, yani hiçbir bar onu dolduramıyor.
        """
        sonuc = self._kosu("paper")
        assert sonuc.metrikler.islem_sayisi == 0
        assert sonuc.atlanan["risk_reddetti"] == 2
        assert sonuc.risk is not None
        assert sonuc.risk["red"]["promotion_yok"] == 2

    def test_backtest_modunda_ayni_hedef_doluyor(self):
        """Negatif kontrol: üstteki test, hiç sinyal üretmeyen bir kurulumla da yeşil olurdu."""
        sonuc = self._kosu("backtest")
        # `islem_sayisi` **kapanan** turları sayıyor; bu senaryoda iki tur açılıp seri
        # bitene kadar açık kalıyor. Ölçülen şey turun kapanması değil, fill'in olması.
        assert len(sonuc.islemler) == 2
        assert sonuc.acik_pozisyon_sonda
        assert sonuc.atlanan["risk_reddetti"] == 0
