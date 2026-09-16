"""Deflated Sharpe Ratio: çapraz kontrol aracı, kapı değil. (K-054, Faz 11)

DSR bir **model**: getirilerin bağımsız ve aynı dağılımlı olduğunu varsayıyor. Kaydırma
null'ı (K-044) bu varsayımı yapmıyor. İkisi ayrı yollardan aynı soruyu cevaplıyor ve bu
dosya DSR'ın yönünü, sınırlarını ve **reddetmesi gereken yerleri** ölçüyor.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.research import dsr
from scryne_quant.research.coklu_test import beklenen_azami_sharpe


def _getiri(n: int = 5000, ort: float = 0.0, sapma: float = 0.01, tohum: int = 0):
    return np.random.default_rng(tohum).normal(ort, sapma, n)


class TestYon:
    def test_gercek_edge_yuksek_dsr(self):
        assert dsr.hesapla(
            _getiri(ort=0.0008), deneme_sayisi=38, sharpe_sapmasi=0.01
        ).dsr > 0.99

    def test_edge_yoksa_dusuk_dsr(self):
        assert dsr.hesapla(_getiri(ort=0.0), deneme_sayisi=38, sharpe_sapmasi=0.01).dsr < 0.6

    def test_deneme_sayisi_arttikca_dsr_dusuyor(self):
        """Çoklu test düzeltmesinin ta kendisi: daha çok deneme, daha yüksek çıta."""
        r = _getiri(ort=0.0004)
        az = dsr.hesapla(r, deneme_sayisi=5, sharpe_sapmasi=0.01).dsr
        cok = dsr.hesapla(r, deneme_sayisi=500, sharpe_sapmasi=0.01).dsr
        assert cok < az

    def test_sharpe_sapmasi_arttikca_dsr_dusuyor(self):
        """Denemeler birbirinden ne kadar farklıysa, en iyisinin şansa borcu o kadar büyük."""
        r = _getiri(ort=0.0004)
        dar = dsr.hesapla(r, deneme_sayisi=38, sharpe_sapmasi=0.005).dsr
        genis = dsr.hesapla(r, deneme_sayisi=38, sharpe_sapmasi=0.05).dsr
        assert genis < dar


class TestSinirlar:
    def test_az_gozlem_reddediliyor(self):
        with pytest.raises(dsr.DsrHatasi, match="en az"):
            dsr.hesapla(_getiri(n=10), deneme_sayisi=10, sharpe_sapmasi=0.01)

    def test_sifir_sapma_reddediliyor(self):
        with pytest.raises(dsr.DsrHatasi, match="sapması sıfır"):
            dsr.hesapla(np.zeros(100), deneme_sayisi=10, sharpe_sapmasi=0.01)

    def test_ham_basiklik_kullaniliyor(self):
        """Normal dağılımda basıklık ~3 olmalı; fazlalık basıklık (~0) verilseydi
        `(γ₄−1)/4` terimi yanlış hesaplanır ve DSR sistematik olarak iyimser çıkardı."""
        sonuc = dsr.hesapla(_getiri(n=20_000), deneme_sayisi=10, sharpe_sapmasi=0.01)
        assert 2.8 < sonuc.basiklik < 3.2

    def test_ozkaynaktan_ayni_sonuc(self):
        """`n` noktalı bir equity eğrisi `n−1` getiri verir; eğri başlangıç sermayesiyle
        kuruluyor ki getirilerin hepsi geri çıkarılabilsin."""
        r = _getiri(ort=0.0005, n=2000)
        oz = 10_000 * np.cumprod(np.concatenate([[1.0], 1 + r]))
        a = dsr.ozkaynaktan(oz, deneme_sayisi=38, sharpe_sapmasi=0.01)
        b = dsr.hesapla(r, deneme_sayisi=38, sharpe_sapmasi=0.01)
        assert abs(a.dsr - b.dsr) < 1e-6

    def test_beklenen_azami_sharpe_pozitif(self):
        """N denemenin en iyisi, hiç edge yokken bile sıfırdan büyüktür."""
        assert beklenen_azami_sharpe(38, 0.01) > 0.0
        assert beklenen_azami_sharpe(500, 0.01) > beklenen_azami_sharpe(38, 0.01)

    def test_kayit_ara_degerleri_tasiyor(self):
        """Tek bir olasılık, hangi varsayımlarla çıktığını söylemiyor."""
        d = dsr.hesapla(_getiri(), deneme_sayisi=38, sharpe_sapmasi=0.01).sozluk()
        assert set(d) == {
            "dsr",
            "sharpe_bar",
            "beklenen_azami_sharpe_bar",
            "deneme_sayisi",
            "gozlem",
            "carpiklik",
            "basiklik",
        }
