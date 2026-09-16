"""Portföy kurma ve hedef portföy sözleşmesi. (§12, Faz 10)

İki şey ölçülüyor:

1. `HedefPortfoy` sözleşmesi — sıra, tekillik, zaman tutarlılığı, toplam sınırı. Bunların
   hepsi determinizmin (K-009) ya da kaldıraç yasağının kod hâli.
2. Kurma katmanının kendisi — seçim, budama, ağırlık, turnover bandı. Kurmanın **izin
   veremediği** ayrıca `test_risk_portfoy.py`de ölçülüyor.
"""

from __future__ import annotations

import pytest

from scryne_quant.strategy.hedef import HedefPortfoy, hedef_kur
from scryne_quant.strategy.kurma import (
    Aday,
    KurmaAyarlari,
    KurmaHatasi,
    agirliklar,
    kur,
    sec,
    turnover_uygula,
)
from scryne_quant.strategy.sinyal import Sinyal, Yon

ZAMAN = 1_699_999_200_000


def _sinyal(sembol: str, hedef: float = 0.2, *, zaman: int = ZAMAN) -> Sinyal:
    return Sinyal(
        symbol=sembol,
        side=Yon.BUY if hedef > 0 else Yon.FLAT,
        target_exposure=hedef,
        confidence=0.5,
        reason="TEST",
        timestamp=zaman,
    )


class TestHedefPortfoy:
    def test_siralama_zorunlu(self):
        """Sıra determinizmin parçası: emir sırası kayan nokta toplamını etkiliyor."""
        with pytest.raises(ValueError, match="sembole göre sıralı"):
            HedefPortfoy(
                timestamp=ZAMAN, sinyaller=(_sinyal("BBBUSDT"), _sinyal("AAAUSDT"))
            )

    def test_hedef_kur_siralar(self):
        h = hedef_kur(ZAMAN, [_sinyal("BBBUSDT"), _sinyal("AAAUSDT")])
        assert h.semboller == ("AAAUSDT", "BBBUSDT")

    def test_tekrarlayan_sembol_reddediliyor(self):
        with pytest.raises(ValueError, match="aynı sembol için iki hedef"):
            hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.2), _sinyal("AAAUSDT", 0.3)])

    def test_farkli_zamanli_sinyal_reddediliyor(self):
        with pytest.raises(ValueError, match="tek bir barın kararıdır"):
            hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.2, zaman=ZAMAN + 3_600_000)])

    def test_toplam_biri_asamaz(self):
        with pytest.raises(ValueError, match="toplamı 1'i aşamaz"):
            hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.6), _sinyal("BBBUSDT", 0.6)])

    def test_bos_demet_gecerli(self):
        """Boş hedef "hiçbir şey söylemiyorum" değil, "hiçbir sembolde hedefim yok"."""
        h = hedef_kur(ZAMAN, [])
        assert h.semboller == () and h.asgari_nakit_agirligi == 1.0

    def test_yontem_kod_olmali(self):
        with pytest.raises(ValueError, match="kod olmalı"):
            hedef_kur(ZAMAN, [], yontem="oynaklık ayarlı")

    def test_nakit_agirligi(self):
        h = hedef_kur(ZAMAN, [_sinyal("AAAUSDT", 0.3), _sinyal("BBBUSDT", 0.2)])
        assert h.asgari_nakit_agirligi == pytest.approx(0.5)


class TestSecim:
    def test_skora_gore_ilk_n(self):
        adaylar = [
            Aday(f"{h}USDT", skor, 0.02)
            for h, skor in zip("ABCD", [1, 4, 3, 2], strict=True)
        ]
        secilen = sec(adaylar, KurmaAyarlari(azami_enstruman=2))
        assert [a.sembol for a in secilen] == ["BUSDT", "CUSDT"]

    def test_esit_skorda_sembol_bozuyor(self):
        adaylar = [Aday("BBBUSDT", 1.0, 0.02), Aday("AAAUSDT", 1.0, 0.02)]
        assert [a.sembol for a in sec(adaylar, KurmaAyarlari(azami_enstruman=1))] == [
            "AAAUSDT"
        ]

    def test_korelasyon_budamasi(self):
        adaylar = [Aday("AAAUSDT", 2.0, 0.02), Aday("BBBUSDT", 1.0, 0.02)]
        ayarlar = KurmaAyarlari(azami_enstruman=2, korelasyon_tavani=0.8)
        secilen = sec(adaylar, ayarlar, {("AAAUSDT", "BBBUSDT"): 0.95})
        assert [a.sembol for a in secilen] == ["AAAUSDT"]

    def test_dusuk_korelasyonda_budama_yok(self):
        adaylar = [Aday("AAAUSDT", 2.0, 0.02), Aday("BBBUSDT", 1.0, 0.02)]
        ayarlar = KurmaAyarlari(azami_enstruman=2, korelasyon_tavani=0.8)
        secilen = sec(adaylar, ayarlar, {("AAAUSDT", "BBBUSDT"): 0.1})
        assert len(secilen) == 2

    def test_olculmemis_korelasyon_sifir_sayilmiyor(self):
        """Ölçülemeyen guard geçilmiş sayılmaz: eksik çift en muhafazakâr değeri alır."""
        adaylar = [Aday("AAAUSDT", 2.0, 0.02), Aday("BBBUSDT", 1.0, 0.02)]
        ayarlar = KurmaAyarlari(azami_enstruman=2, korelasyon_tavani=0.8)
        assert len(sec(adaylar, ayarlar, {})) == 1


class TestAgirlik:
    def test_oynaklik_ayarli_ters_orantili(self):
        adaylar = [Aday("AAAUSDT", 1.0, 0.04), Aday("BBBUSDT", 1.0, 0.02)]
        w = agirliklar(adaylar, KurmaAyarlari(azami_agirlik=1.0))
        assert w["BBBUSDT"] == pytest.approx(2 * w["AAAUSDT"])
        assert sum(w.values()) == pytest.approx(1.0)

    def test_esit_agirlik_oynakligi_yok_sayiyor(self):
        adaylar = [Aday("AAAUSDT", 1.0, 0.04), Aday("BBBUSDT", 1.0, 0.02)]
        w = agirliklar(adaylar, KurmaAyarlari(azami_agirlik=1.0, esit_agirlik=True))
        assert w["AAAUSDT"] == pytest.approx(w["BBBUSDT"])

    def test_tavan_asilmiyor_ve_artan_dagitiliyor(self):
        adaylar = [
            Aday("AAAUSDT", 1.0, 0.01),  # ham payı çok büyük
            Aday("BBBUSDT", 1.0, 0.04),
            Aday("CCCUSDT", 1.0, 0.04),
        ]
        w = agirliklar(adaylar, KurmaAyarlari(azami_agirlik=0.4))
        assert max(w.values()) <= 0.4 + 1e-12
        assert sum(w.values()) == pytest.approx(1.0)

    def test_hedef_brut_nakit_birakiyor(self):
        adaylar = [Aday("AAAUSDT", 1.0, 0.02), Aday("BBBUSDT", 1.0, 0.02)]
        w = agirliklar(adaylar, KurmaAyarlari(hedef_brut=0.6, azami_agirlik=0.5))
        assert sum(w.values()) == pytest.approx(0.6)

    def test_asgari_agirlik_altinda_sifirlaniyor(self):
        adaylar = [Aday("AAAUSDT", 1.0, 0.0001), Aday("BBBUSDT", 1.0, 10.0)]
        w = agirliklar(adaylar, KurmaAyarlari(azami_agirlik=1.0, asgari_agirlik=0.01))
        assert w["BBBUSDT"] == 0.0

    def test_dagitilamayan_kisim_nakitte_kaliyor(self):
        """Tavanı zorla dağıtmak, tavanı tavan olmaktan çıkarırdı."""
        adaylar = [Aday("AAAUSDT", 1.0, 0.02), Aday("BBBUSDT", 1.0, 0.02)]
        w = agirliklar(adaylar, KurmaAyarlari(azami_agirlik=0.3))
        assert sum(w.values()) == pytest.approx(0.6)


class TestTurnover:
    def test_bant_altinda_degisiklik_yapilmiyor(self):
        adaylar = {"AAAUSDT": Aday("AAAUSDT", 1.0, 0.02, mevcut_agirlik=0.30)}
        sonuc = turnover_uygula({"AAAUSDT": 0.32}, adaylar, 0.05)
        assert sonuc["AAAUSDT"] == pytest.approx(0.30)

    def test_bant_ustunde_degisiklik_yapiliyor(self):
        adaylar = {"AAAUSDT": Aday("AAAUSDT", 1.0, 0.02, mevcut_agirlik=0.30)}
        sonuc = turnover_uygula({"AAAUSDT": 0.40}, adaylar, 0.05)
        assert sonuc["AAAUSDT"] == pytest.approx(0.40)

    def test_bant_simetrik(self):
        """Yalnızca artışı engelleyen bir bant portföyü tek yöne sürüklerdi."""
        adaylar = {"AAAUSDT": Aday("AAAUSDT", 1.0, 0.02, mevcut_agirlik=0.30)}
        assert turnover_uygula({"AAAUSDT": 0.28}, adaylar, 0.05)["AAAUSDT"] == pytest.approx(
            0.30
        )

    def test_bant_sifirken_kimlik(self):
        adaylar = {"AAAUSDT": Aday("AAAUSDT", 1.0, 0.02, mevcut_agirlik=0.30)}
        assert turnover_uygula({"AAAUSDT": 0.31}, adaylar, 0.0)["AAAUSDT"] == 0.31


class TestKur:
    def test_hedef_portfoy_uretiyor(self):
        adaylar = [Aday("AAAUSDT", 2.0, 0.02), Aday("BBBUSDT", 1.0, 0.02)]
        h = kur(ZAMAN, adaylar, KurmaAyarlari(azami_enstruman=2, azami_agirlik=0.5))
        assert h.semboller == ("AAAUSDT", "BBBUSDT")
        assert h.yontem == "OYNAKLIK_AYARLI"
        assert h.hedef_toplami == pytest.approx(1.0)

    def test_elenen_acik_pozisyon_flat_aliyor(self):
        """Kurma katmanı portföyün tamamını söylüyor; sessizliğe yorum yüklenmiyor."""
        adaylar = [Aday("AAAUSDT", 2.0, 0.02), Aday("BBBUSDT", 1.0, 0.02)]
        h = kur(
            ZAMAN,
            adaylar,
            KurmaAyarlari(azami_enstruman=1, azami_agirlik=1.0),
            acik_pozisyonlar=("BBBUSDT", "CCCUSDT"),
        )
        flatlar = {s.symbol for s in h.sinyaller if s.side is Yon.FLAT}
        assert flatlar == {"BBBUSDT", "CCCUSDT"}

    def test_yontem_kimligi_ayarlara_bagli(self):
        """Yöntem bir çekiliştir (K-051/4): ayar değişirse kimlik değişmeli."""
        a = KurmaAyarlari(azami_enstruman=5)
        b = KurmaAyarlari(azami_enstruman=6)
        assert a.sozluk() != b.sozluk()

    def test_ayni_girdi_ayni_hedef(self):
        adaylar = [Aday("AAAUSDT", 2.0, 0.02), Aday("BBBUSDT", 1.0, 0.03)]
        ayarlar = KurmaAyarlari(azami_enstruman=2, azami_agirlik=0.6)
        assert kur(ZAMAN, adaylar, ayarlar).sozluk() == kur(ZAMAN, adaylar, ayarlar).sozluk()

    def test_tekrarlayan_aday_reddediliyor(self):
        with pytest.raises(KurmaHatasi, match="aynı sembol için iki aday"):
            kur(ZAMAN, [Aday("AAAUSDT", 1.0, 0.02), Aday("AAAUSDT", 2.0, 0.02)], KurmaAyarlari())

    def test_sifir_oynaklik_reddediliyor(self):
        with pytest.raises(KurmaHatasi, match="oynaklık pozitif"):
            Aday("AAAUSDT", 1.0, 0.0)

    def test_gecersiz_ayar_reddediliyor(self):
        with pytest.raises(KurmaHatasi, match="hedef_brut"):
            KurmaAyarlari(hedef_brut=1.5)
