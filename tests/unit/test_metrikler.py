"""Performans metrikleri: elle hesaplanabilir vakalar ve kenar durumlar. (§17)

Buradaki beklenen değerler motordan değil, tanımdan geliyor: %20 düşüş için `1 − 80/100`,
profit factor için `kazanç toplamı / kayıp toplamı`. Bir metriğin "motorun verdiği sayı"
ile test edilmesi, metriği değil kendini doğrular.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from scryne_quant.backtest.metrikler import (
    ASGARI_YILLIK_PENCERE_MS,
    CAGR_TAVANI,
    YIL_MS,
    Islem,
    bar_yili,
    drawdown,
    hesapla,
)

SAAT = 3_600_000
GUN = 24 * SAAT


def _islem(net: float, sure_bar: int = 1, komisyon: float = 0.0, giris: float = 1_000.0) -> Islem:
    return Islem(
        acilis_ms=0,
        kapanis_ms=sure_bar * SAAT,
        giris_notional=giris,
        giris_miktar=1.0,
        cikis_notional=giris + net,
        cikis_miktar=1.0,
        komisyon=komisyon,
        net_pnl=net,
        fill_sayisi=2,
    )


def _metrikler(ozkaynak: list[float], islemler: list[Islem] | None = None, sermaye: float = 100.0):
    dizi = np.array(ozkaynak, dtype=np.float64)
    return hesapla(dizi, np.zeros_like(dizi), islemler or [], SAAT, sermaye)


class TestBarYili:
    def test_saatlik(self):
        assert bar_yili(SAAT) == pytest.approx(8766.0)

    def test_gunluk(self):
        assert bar_yili(GUN) == pytest.approx(365.25)

    def test_takvim_bazli_252_degil(self):
        """Kripto 7/24; hisse senedinin 252 işlem günü konvansiyonu buraya taşınmaz."""
        assert bar_yili(GUN) > 252

    def test_gecersiz_timeframe(self):
        with pytest.raises(ValueError):
            bar_yili(0)


class TestDrawdown:
    def test_basit_dusus(self):
        d = drawdown(np.array([100.0, 120.0, 96.0, 110.0]))
        assert d.azami == pytest.approx(0.2)  # 120 → 96

    def test_dusus_yoksa_sifir(self):
        assert drawdown(np.array([100.0, 110.0, 120.0])).azami == 0.0

    def test_sure_zirveden_zirveye(self):
        # 100 → 90 → 95 → 105: zirvenin altında 2 bar geçti.
        assert drawdown(np.array([100.0, 90.0, 95.0, 105.0])).en_uzun_bar == 2

    def test_toparlanmamis_dusus_de_sayiliyor(self):
        """Serinin sonunda hâlâ düşüşteysek, görmezden gelmek en kötüyü gizlemek olurdu."""
        assert drawdown(np.array([100.0, 90.0, 80.0, 70.0])).en_uzun_bar == 3

    def test_en_uzun_ile_en_derin_farkli_olabilir(self):
        d = drawdown(np.array([100.0, 50.0, 100.0, 99.0, 99.0, 99.0, 99.0, 100.0]))
        assert d.azami == pytest.approx(0.5)
        assert d.en_uzun_bar == 4

    def test_bos_seri(self):
        assert drawdown(np.array([])).azami == 0.0


class TestGetiri:
    def test_toplam_getiri(self):
        assert _metrikler([100.0, 150.0]).toplam_getiri == pytest.approx(0.5)

    def test_negatif_getiri(self):
        assert _metrikler([100.0, 60.0]).toplam_getiri == pytest.approx(-0.4)

    def test_cagr_bir_yillik_pencerede_toplam_getiriye_esit(self):
        n = round(bar_yili(SAAT))
        egri = list(np.linspace(100.0, 120.0, n))
        m = _metrikler(egri)
        assert m.cagr == pytest.approx(0.2, rel=1e-2)
        assert m.yillik_anlamli

    def test_kisa_pencerede_yillik_anlamsiz(self):
        m = _metrikler([100.0, 150.0, 200.0])
        assert not m.yillik_anlamli

    def test_kisa_pencerede_cagr_tasmiyor(self):
        """Ölçülmüş hata: doğrudan üs alma 3 barlık koşuda `OverflowError` fırlatıyordu."""
        m = _metrikler([100.0, 200.0, 300.0])
        assert math.isfinite(m.cagr)
        assert m.cagr == CAGR_TAVANI

    def test_esik_tam_30_gun(self):
        n = ASGARI_YILLIK_PENCERE_MS // SAAT
        assert _metrikler([100.0] * n).yillik_anlamli
        assert not _metrikler([100.0] * (n - 1)).yillik_anlamli

    def test_sermaye_tukendiyse_cagr_eksi_bir(self):
        assert _metrikler([100.0, 50.0, 0.0]).cagr == -1.0


class TestRiskMetrikleri:
    def test_sabit_getiride_volatilite_sifir(self):
        m = _metrikler([100.0] * 50)
        assert m.yillik_volatilite == 0.0
        assert m.sharpe == 0.0

    def test_sharpe_yillik_olcekli(self):
        rng = np.random.default_rng(7)
        getiriler = rng.normal(0.0005, 0.01, 2000)
        egri = 100.0 * np.cumprod(1.0 + getiriler)
        m = hesapla(egri, np.zeros_like(egri), [], SAAT, 100.0)
        beklenen = getiriler.mean() / getiriler.std(ddof=1) * math.sqrt(bar_yili(SAAT))
        assert m.sharpe == pytest.approx(beklenen, rel=1e-2)

    def test_sortino_sharpeden_buyuk_pozitif_carpik_seride(self):
        """Aşağı yönlü sapma toplam sapmadan küçükse Sortino Sharpe'ı aşar."""
        egri = np.array([100.0, 105.0, 110.0, 109.0, 130.0, 129.0, 160.0])
        m = hesapla(egri, np.zeros_like(egri), [], SAAT, 100.0)
        assert m.sortino > m.sharpe > 0

    def test_hic_kayip_yoksa_sortino_sifira_bolunmuyor(self):
        m = _metrikler([100.0, 110.0, 120.0, 130.0])
        assert math.isfinite(m.sortino)

    def test_calmar(self):
        m = _metrikler([100.0, 120.0, 96.0, 110.0])
        assert m.max_drawdown == pytest.approx(0.2)
        assert m.calmar == pytest.approx(m.cagr / 0.2)

    def test_dususu_olmayan_seride_calmar_sifir(self):
        """Sıfıra bölmek `inf` verirdi ve tabloda "mükemmel" diye okunurdu."""
        m = _metrikler([100.0, 110.0, 120.0])
        assert m.max_drawdown == 0.0
        assert m.calmar == 0.0


class TestIslemMetrikleri:
    def test_win_rate_ve_profit_factor(self):
        islemler = [_islem(100.0), _islem(50.0), _islem(-30.0), _islem(-20.0)]
        m = _metrikler([100.0, 200.0], islemler)
        assert m.islem_sayisi == 4
        assert m.kazanan == 2
        assert m.kaybeden == 2
        assert m.win_rate == pytest.approx(0.5)
        assert m.profit_factor == pytest.approx(150.0 / 50.0)

    def test_expectancy_islem_basina_ortalama(self):
        m = _metrikler([100.0, 200.0], [_islem(100.0), _islem(-40.0)])
        assert m.expectancy == pytest.approx(30.0)

    def test_ortalama_kazanc_ve_kayip(self):
        m = _metrikler([100.0, 200.0], [_islem(100.0), _islem(60.0), _islem(-40.0)])
        assert m.ortalama_kazanc == pytest.approx(80.0)
        assert m.ortalama_kayip == pytest.approx(-40.0)

    def test_sifir_pnl_kayip_sayilir(self):
        """Maliyetten sonra tam başabaş bir işlem kazanç değildir."""
        m = _metrikler([100.0, 100.0], [_islem(0.0)])
        assert m.kaybeden == 1
        assert m.kazanan == 0

    def test_hic_kayip_yoksa_profit_factor_sonsuz_degil(self):
        m = _metrikler([100.0, 200.0], [_islem(100.0)])
        assert m.profit_factor == 0.0, "sıfıra bölme `inf` yerine açık varsayılana düşmeli"

    def test_ardisik_kayip(self):
        islemler = [
            _islem(10.0), _islem(-1.0), _islem(-2.0), _islem(-3.0), _islem(5.0), _islem(-1.0)
        ]
        assert _metrikler([100.0, 110.0], islemler).ardisik_kayip == 3

    def test_en_iyi_en_kotu(self):
        m = _metrikler([100.0, 110.0], [_islem(10.0), _islem(-25.0), _islem(3.0)])
        assert m.en_iyi_islem == pytest.approx(10.0)
        assert m.en_kotu_islem == pytest.approx(-25.0)

    def test_ortalama_tutma_suresi(self):
        m = _metrikler([100.0, 110.0], [_islem(1.0, sure_bar=2), _islem(1.0, sure_bar=4)])
        assert m.ortalama_tutma_bar == pytest.approx(3.0)
        assert m.ortalama_tutma_ms == pytest.approx(3 * SAAT)

    def test_kapanmamis_islem_sayilmiyor(self):
        acik = Islem(acilis_ms=0, giris_notional=1_000.0, giris_miktar=1.0)
        m = _metrikler([100.0, 110.0], [_islem(10.0), acik])
        assert m.islem_sayisi == 1

    def test_islemsiz_kosu(self):
        m = _metrikler([100.0, 100.0])
        assert m.islem_sayisi == 0
        assert m.win_rate == 0.0
        assert m.expectancy == 0.0
        assert m.en_iyi_islem == 0.0

    def test_turnover_ve_hacim(self):
        m = _metrikler([100.0, 110.0], [_islem(10.0, giris=1_000.0)], sermaye=100.0)
        assert m.islem_hacmi == pytest.approx(2_010.0)
        assert m.turnover == pytest.approx(20.1)


class TestSozluk:
    def test_tum_alanlar_serilesiyor(self):
        d = _metrikler([100.0, 110.0], [_islem(10.0)]).sozluk()
        assert "yillik_anlamli" in d
        assert all(isinstance(v, int | float | bool) for v in d.values())

    def test_bos_egri_reddediliyor(self):
        with pytest.raises(ValueError, match="boş"):
            hesapla(np.array([]), np.array([]), [], SAAT, 100.0)

    def test_uzunluk_uyusmazligi(self):
        with pytest.raises(ValueError, match="aynı uzunlukta"):
            hesapla(np.array([1.0, 2.0]), np.array([1.0]), [], SAAT, 100.0)

    def test_yil_sabiti(self):
        assert YIL_MS == 365.25 * 24 * 3_600_000
