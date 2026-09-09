"""Veri bölme: kronoloji, örtüşmezlik, ısınma yönü. (Faz 4)

Bu testlerin yakaladığı hata sınıfı sessizdir: yanlış bölünmüş bir deney çalışır, sonuç
üretir ve **olduğundan iyi** görünür. Bir çökme beklenmiyor, o yüzden her kural ayrı ayrı
sabitleniyor.
"""

from __future__ import annotations

import pytest

from scryne_quant.research.bolme import (
    BolmeHatasi,
    Katman,
    Pencere,
    is_oos,
    katman_test_pencereleri,
    walk_forward,
)


class TestPencere:
    def test_temel(self):
        p = Pencere("x", baslangic=100, bitis=200, isinma_baslangic=50)
        assert p.uzunluk == 100
        assert p.olcum_baslangici == 50
        assert p.dilim() == slice(50, 200)

    def test_isinma_ileriye_tasamaz(self):
        """Isınma başlangıcı ölçüm başlangıcından sonraysa, ısınma geleceği okurdu."""
        with pytest.raises(BolmeHatasi, match="ileriye taşamaz"):
            Pencere("x", baslangic=100, bitis=200, isinma_baslangic=150)

    def test_bos_pencere(self):
        with pytest.raises(BolmeHatasi, match="boş"):
            Pencere("x", baslangic=100, bitis=100, isinma_baslangic=0)

    def test_isinmasiz_pencere_gecerli(self):
        p = Pencere("x", baslangic=0, bitis=10, isinma_baslangic=0)
        assert p.olcum_baslangici == 0


class TestIsOos:
    def test_oos_sonda(self):
        """OOS **sonda** olur: en yeni veri, stratejinin bugüne yakın davranışını ölçer."""
        ins, oos = is_oos(1000, isinma=50, oos_orani=0.30)
        assert ins.baslangic == 50
        assert ins.bitis == 700
        assert oos.baslangic == 700
        assert oos.bitis == 1000

    def test_ortusme_yok(self):
        ins, oos = is_oos(1000, isinma=50, oos_orani=0.30)
        assert ins.bitis <= oos.baslangic

    def test_oos_isinmasi_geriye_tasiyor(self):
        """OOS indikatörleri IS verisiyle ısınır — canlıda da o veri elde olurdu."""
        _, oos = is_oos(1000, isinma=50, oos_orani=0.30)
        assert oos.isinma_baslangic == 650
        assert oos.olcum_baslangici == 50

    def test_isinma_kesme_noktasindan_once_baslar(self):
        """IS penceresi ısınmadan kısa olamaz — `is_oos` bu durumu zaten reddediyor."""
        for isinma in (10, 50, 200):
            _, oos = is_oos(2000, isinma=isinma, oos_orani=0.30)
            assert 0 <= oos.isinma_baslangic < oos.baslangic
            assert oos.olcum_baslangici == isinma

    @pytest.mark.parametrize("oran", [0.05, 0.6, 1.0, -0.1])
    def test_makul_olmayan_oos_orani(self, oran: float):
        with pytest.raises(BolmeHatasi, match="oos_orani"):
            is_oos(1000, isinma=50, oos_orani=oran)

    def test_yetersiz_veri(self):
        with pytest.raises(BolmeHatasi, match="bölünemiyor"):
            is_oos(60, isinma=50, oos_orani=0.30)

    def test_negatif_isinma(self):
        with pytest.raises(BolmeHatasi, match="ısınma"):
            is_oos(1000, isinma=-1)


class TestWalkForward:
    def test_katman_sayisi(self):
        # 1000 bar, 50 ısınma. Katman 0: eğitim [50,450), test [450,550).
        # Her katman 100 bar ileri kayar; son katmanın testi 1000'i aşamaz.
        katmanlar = walk_forward(1000, isinma=50, egitim_bar=400, test_bar=100)
        assert len(katmanlar) == 5
        assert [k.sira for k in katmanlar] == [0, 1, 2, 3, 4]
        assert katmanlar[-1].test.bitis == 950

    def test_test_egitimden_sonra(self):
        for k in walk_forward(1000, isinma=50, egitim_bar=400, test_bar=100):
            assert k.test.baslangic == k.egitim.bitis
            assert k.test.bitis > k.test.baslangic

    def test_test_pencereleri_kesintisiz(self):
        """Test pencerelerinin birleşimi bileşik OOS zincirini verir — boşluk olamaz."""
        katmanlar = walk_forward(1000, isinma=50, egitim_bar=400, test_bar=100)
        pencereler = list(katman_test_pencereleri(katmanlar))
        for onceki, sonraki in zip(pencereler, pencereler[1:], strict=False):
            assert onceki.bitis == sonraki.baslangic

    def test_kaydirmali_egitim_sabit_uzunlukta(self):
        katmanlar = walk_forward(1000, isinma=50, egitim_bar=400, test_bar=100, kaydirmali=True)
        assert {k.egitim.uzunluk for k in katmanlar} == {400}

    def test_sabit_capa_egitim_buyuyor(self):
        katmanlar = walk_forward(1000, isinma=50, egitim_bar=400, test_bar=100, kaydirmali=False)
        uzunluklar = [k.egitim.uzunluk for k in katmanlar]
        assert uzunluklar == sorted(uzunluklar)
        assert uzunluklar[0] < uzunluklar[-1]
        assert all(k.egitim.baslangic == 50 for k in katmanlar)

    def test_kaydirmali_egitim_ileri_kayiyor(self):
        katmanlar = walk_forward(1000, isinma=50, egitim_bar=400, test_bar=100, kaydirmali=True)
        baslangiclar = [k.egitim.baslangic for k in katmanlar]
        assert baslangiclar == [50, 150, 250, 350, 450]

    def test_test_isinmasi_geriye_tasiyor(self):
        for k in walk_forward(1000, isinma=50, egitim_bar=400, test_bar=100):
            assert k.test.isinma_baslangic == k.test.baslangic - 50
            assert k.test.olcum_baslangici == 50

    def test_veri_bitince_duruyor(self):
        """Son katman veriyi aşmaz — aşsaydı olmayan barlar okunurdu."""
        katmanlar = walk_forward(1000, isinma=50, egitim_bar=400, test_bar=100)
        assert katmanlar[-1].test.bitis <= 1000

    def test_tek_katman_bile_cikmiyorsa_hata(self):
        with pytest.raises(BolmeHatasi, match="tek bir katman"):
            walk_forward(200, isinma=50, egitim_bar=400, test_bar=100)

    @pytest.mark.parametrize(("egitim", "test"), [(1, 100), (400, 1), (0, 0)])
    def test_cok_kisa_pencere(self, egitim: int, test: int):
        with pytest.raises(BolmeHatasi, match="en az 2 bar"):
            walk_forward(1000, isinma=50, egitim_bar=egitim, test_bar=test)


class TestKatman:
    def test_ortusen_katman_reddediliyor(self):
        """Optimize edilen parametre kendi test verisini görürse walk-forward anlamsız."""
        with pytest.raises(BolmeHatasi, match="örtüşüyor"):
            Katman(
                sira=0,
                egitim=Pencere("e", baslangic=0, bitis=100, isinma_baslangic=0),
                test=Pencere("t", baslangic=50, bitis=150, isinma_baslangic=0),
            )

    def test_bitisik_katman_gecerli(self):
        k = Katman(
            sira=0,
            egitim=Pencere("e", baslangic=0, bitis=100, isinma_baslangic=0),
            test=Pencere("t", baslangic=100, bitis=150, isinma_baslangic=50),
        )
        assert k.sozluk()["sira"] == 0
