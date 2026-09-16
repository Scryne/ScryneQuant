"""CSCV / PBO: ölçünün kendisi ve sınırları. (K-054, Faz 11)

PBO bir **seçim yöntemi** ölçüsü, bir performans ölçüsü değil. Bu dosyanın ölçtüğü üç şey:

1. Aritmetik doğru mu — dilim toplamlarından hesaplanan Sharpe, doğrudan hesaplananla
   birebir aynı mı.
2. Ölçü doğru yönde mi — gerçek edge düşük PBO, sahte edge yüksek PBO vermeli.
3. Sınırları yazılı mı — tek adaylı ızgarada ölçülemez, ve **tek ölçümü gürültülü.**

Üçüncüsü ölçülmüş bir bulgu: literatürün null referansı (0,5) *ortalamada* doğru çıktı
(40 tohumda 0,503), ama tek bir veri kümesindeki ölçüm ±0,2 sapma taşıyor (aralık
0,084-0,898). Yani 0,5'e yakın bir eşik, edge'i olmayan bir stratejiyi vakaların
yarısında geçirirdi. K-044'ün dersinin bu istatistikteki hâli: referans sayı, ölçülmüş
eşiğin yerini tutmaz.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from scryne_quant.research.pbo import (
    PboHatasi,
    _dilim_sinirlari,
    _dilim_toplamlari,
    _sharpe,
    cscv,
)

YIL_BAR = 8766.0


class TestAritmetik:
    def test_dilim_toplamlarindan_sharpe_dogrudan_hesapla_ayni(self):
        """Hızlı yol bir yaklaşım değil: aynı sayı, sabit zamanda."""
        rng = np.random.default_rng(0)
        g = rng.normal(0, 0.01, (5, 1000))
        sinirlar = _dilim_sinirlari(1000, 10)
        n_, t_, k_ = _dilim_toplamlari(g, sinirlar)
        idx = [0, 2, 4, 6, 8]
        maske = np.zeros(1000, dtype=bool)
        for i in idx:
            bas, bit = sinirlar[i]
            maske[bas:bit] = True
        dogrudan = g[:, maske]
        ref = dogrudan.mean(1) / dogrudan.std(1, ddof=1) * math.sqrt(YIL_BAR)
        hizli = _sharpe(n_[idx], t_[:, idx].sum(1), k_[:, idx].sum(1), YIL_BAR)
        np.testing.assert_allclose(ref, hizli, rtol=1e-12, atol=1e-12)

    def test_dilimler_bitisik_ve_tam(self):
        sinirlar = _dilim_sinirlari(103, 10)
        assert sinirlar[0][0] == 0 and sinirlar[-1][1] == 103
        assert all(a[1] == b[0] for a, b in zip(sinirlar, sinirlar[1:], strict=False))
        assert sum(b - a for a, b in sinirlar) == 103

    def test_tek_dilim_reddediliyor(self):
        with pytest.raises(PboHatasi, match="çift ve"):
            _dilim_sinirlari(100, 7)

    def test_kisa_seri_reddediliyor(self):
        with pytest.raises(PboHatasi, match="dilime bölünemez"):
            _dilim_sinirlari(10, 16)


class TestYon:
    def test_gercek_edge_dusuk_pbo(self):
        """Bir aday her yerde iyiyse IS'te de OOS'ta da seçilir: PBO sıfıra gider."""
        rng = np.random.default_rng(1)
        g = rng.normal(0, 0.01, (10, 4000))
        g[3] += 0.0015
        assert cscv(g, yil_bar=YIL_BAR).pbo < 0.05

    def test_overfit_senaryosu_yuksek_pbo(self):
        """Her aday **rastgele dilimlerde** şanslı: klasik overfitting senaryosu.

        IS'te kazanan, o bölümde şanslı olandır ve şansı OOS dilimlerinde tekrar etmez.
        Tek adaya yarım-seri edge vermek yerine bu kurgu seçildi çünkü gerçek bir ızgarada
        durum budur: hiçbir nokta gerçekten iyi değil, hepsi farklı yerlerde şanslı.
        Ölçüldü: 10 tohumda ortalama PBO 0,71 (null 0,50).
        """
        pbolar = []
        for s in range(6):
            rng = np.random.default_rng(100 + s)
            g = rng.normal(0, 0.01, (12, 4000))
            for i in range(12):
                for d in rng.choice(16, 4, replace=False):
                    g[i, d * 250 : (d + 1) * 250] += 0.0015
            pbolar.append(cscv(g, yil_bar=YIL_BAR).pbo)
        assert np.mean(pbolar) > 0.6

    def test_performans_bozulmasi_raporlaniyor(self):
        """PBO bir **sıra** ölçüsü; hepsi birden çökerse düşük kalabilir."""
        rng = np.random.default_rng(3)
        g = rng.normal(0, 0.01, (8, 3000))
        g[:, 1500:] -= 0.002  # herkes ikinci yarıda kaybediyor
        sonuc = cscv(g, yil_bar=YIL_BAR)
        assert sonuc.performans_bozulmasi > 0.0
        assert 0.0 <= sonuc.zarar_olasiligi <= 1.0


class TestSinirlar:
    def test_tek_aday_olculemez(self):
        with pytest.raises(PboHatasi, match="en az 2 aday"):
            cscv(np.zeros((1, 1000)), yil_bar=YIL_BAR)

    def test_null_ortalamasi_yarim_ama_tek_olcum_gurultulu(self):
        """**Ölçülmüş bulgu:** null'ın *ortalaması* teoremle uyuşuyor, *tek ölçümü* uyuşmuyor.

        40 tohumda (12 aday × 4.000 bar iid gürültü): ortalama **0,503** — yani
        literatürün 0,5 referansı doğru. Ama standart sapma **0,204** ve aralık
        0,084-0,898: tek bir veri kümesinde ölçülen PBO, ±0,2 belirsizlik taşıyor.

        Bunun kapı tasarımına doğrudan sonucu var: 0,5'e yakın bir eşik, edge'i olmayan
        bir stratejiyi vakaların yarısında geçirir. Eşik bu yüzden null dağılımının alt
        kuyruğundan ölçülüyor (`sq lab kalibrasyon-v2`), 0,5'ten değil.

        Test sayıyı değil **iki yönü** sabitliyor: ortalama 0,5 civarında, sapma büyük.
        """
        pbolar = [
            cscv(np.random.default_rng(s).normal(0, 0.01, (12, 4000)), yil_bar=YIL_BAR).pbo
            for s in range(20)
        ]
        assert abs(float(np.mean(pbolar)) - 0.5) < 0.12
        assert float(np.std(pbolar)) > 0.12

    def test_iki_boyutlu_olmayan_girdi_reddediliyor(self):
        with pytest.raises(PboHatasi, match="2 boyutlu"):
            cscv(np.zeros(100), yil_bar=YIL_BAR)

    def test_determinizm(self):
        rng = np.random.default_rng(4)
        g = rng.normal(0, 0.01, (6, 2000))
        assert cscv(g, yil_bar=YIL_BAR).pbo == cscv(g, yil_bar=YIL_BAR).pbo

    def test_kombinasyon_sayisi_beklenen(self):
        from math import comb

        sonuc = cscv(np.random.default_rng(5).normal(0, 0.01, (4, 2000)), yil_bar=YIL_BAR)
        assert sonuc.kombinasyon_sayisi == comb(16, 8)
