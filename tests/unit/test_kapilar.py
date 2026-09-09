"""Promotion kapıları: eşiklerin sayısal ve esnetilemez olması. (K-010, K-018, K-019)

K-018'in cümlesi: *"İnsan yargısına bırakılan bir kapı esnetilebilir, sayısal eşik
esnetilemez — değiştirmek için karar günlüğüne yazmak gerekir ve bu iz bırakır."*

Bu testlerin işi o cümleyi koda bağlamak: her eşiğin bir gerekçesi olmalı, ölçülemeyen
bir kapı geçilmiş sayılmamalı, ve mutlak engeller sayısal sonuç ne olursa olsun kapıyı
kapatmalı.
"""

from __future__ import annotations

import pytest

from scryne_quant.research.kapilar import (
    ESIKLER,
    MUTLAK_ENGELLER,
    Esik,
    degerlendir,
    esik_tablosu,
)

#: Tüm kapıları rahatça geçen ölçüm kümesi. Testlerin çoğu bunu bozarak çalışıyor.
GECEN = {
    "oos_sharpe": 1.2,
    "oos_is_orani": 0.9,
    "wf_pozitif_katman_orani": 0.8,
    "wf_kararsizlik": 0.1,
    "oos_islem": 120,
    "oos_max_drawdown": 0.12,
    "stres_bozulma": 0.05,
}


class TestEsikTanimlari:
    def test_her_esigin_gerekcesi_var(self):
        """Gerekçesiz bir eşik, altı ay sonra 'biraz gevşetsek' tartışmasına açıktır."""
        for esik in ESIKLER:
            assert len(esik.gerekce) > 80, f"{esik.ad}: gerekçe çok kısa"

    def test_yon_gecerli(self):
        for esik in ESIKLER:
            assert esik.yon in (">=", "<=")

    def test_esik_adlari_tekil(self):
        assert len({e.ad for e in ESIKLER}) == len(ESIKLER)

    def test_k018in_saydigi_adaylar_kapsanmis(self):
        """K-018/3 beş aday saymıştı; hepsinin karşılığı olmalı."""
        adlar = {e.ad for e in ESIKLER}
        assert "oos_is_orani" in adlar  # OOS/IS Sharpe oranı alt sınırı
        assert "max_drawdown" in adlar  # max drawdown üst sınırı
        assert "asgari_islem" in adlar  # minimum işlem sayısı
        assert "parametre_kararliligi" in adlar  # parametre duyarlılığı üst sınırı
        # Beşinci aday (paper-backtest drift) Faz 6'nın ölçümü; burada ölçülemez.

    def test_tablo_serilesiyor(self):
        tablo = esik_tablosu()
        assert len(tablo) == len(ESIKLER)
        assert all({"ad", "alan", "sinir", "yon", "gerekce"} <= set(s) for s in tablo)


class TestEsikDegerlendirme:
    def test_buyuk_esittir_yonu(self):
        e = Esik("x", "x", sinir=0.5, yon=">=", gerekce="test")
        assert e.gecti_mi(0.5) is True
        assert e.gecti_mi(0.6) is True
        assert e.gecti_mi(0.49) is False

    def test_kucuk_esittir_yonu(self):
        e = Esik("x", "x", sinir=0.25, yon="<=", gerekce="test")
        assert e.gecti_mi(0.25) is True
        assert e.gecti_mi(0.1) is True
        assert e.gecti_mi(0.26) is False

    def test_olculemeyen_kapi_gecilmis_sayilmiyor(self):
        """'Veri yoktu' ile 'kapıdan geçti' aynı şey değil."""
        e = Esik("x", "x", sinir=0.5, yon=">=", gerekce="test")
        assert e.gecti_mi(None) is None
        assert e.gecti_mi(float("nan")) is None


class TestDegerlendirme:
    def test_tum_kapilari_gecen_sonuc(self):
        sonuc = degerlendir("test", GECEN)
        assert sonuc.gecti
        assert sonuc.kalan_kapilar == []

    def test_tek_kapi_kalinca_gecmiyor(self):
        for esik in ESIKLER:
            bozuk = dict(GECEN)
            bozuk[esik.alan] = esik.sinir + (-1.0 if esik.yon == ">=" else 1.0)
            sonuc = degerlendir("test", bozuk)
            assert not sonuc.gecti, f"{esik.ad} ihlal edilmesine rağmen geçti"
            assert esik.ad in sonuc.kalan_kapilar

    def test_eksik_olcum_kapiyi_kapatiyor(self):
        eksik = {a: d for a, d in GECEN.items() if a != "oos_sharpe"}
        sonuc = degerlendir("test", eksik)
        assert not sonuc.gecti
        assert "oos_sharpe" in sonuc.kalan_kapilar
        assert sonuc.kapilar["oos_sharpe"]["gecti"] is None

    def test_mutlak_engel_sayisal_sonuctan_bagimsiz(self):
        """`dirty` bir ağaçtan çıkan sonuç ne kadar iyi olursa olsun geçemez (K-009)."""
        sonuc = degerlendir("test", GECEN, mutlak_engeller=["dirty"])
        assert not sonuc.gecti
        assert sonuc.kalan_kapilar == []  # kapılar geçildi ama engel var
        assert sonuc.mutlak_engeller == ["dirty"]

    @pytest.mark.parametrize("engel", MUTLAK_ENGELLER)
    def test_her_mutlak_engel_kapatiyor(self, engel: str):
        assert not degerlendir("test", GECEN, mutlak_engeller=[engel]).gecti

    def test_sozluk_kayda_uygun(self):
        d = degerlendir("test", GECEN).sozluk()
        assert set(d) == {"strateji", "gecti", "kalan_kapilar", "mutlak_engeller", "kapilar"}
        assert len(d["kapilar"]) == len(ESIKLER)

    def test_faz4_olcumlerinden_hicbiri_gecmiyor(self):
        """Faz 4'te ölçülen gerçek değerler kapılardan geçmemeli.

        Eşikleri bugünkü sonuca göre gevşetmek kapıyı kaldırmakla aynı şey olurdu
        (K-010'un uyardığı sabırsızlık). Bu test o gevşetmeyi fark eder: birisi eşikleri
        indirirse burası kırmızıya döner ve gerekçe yazmaya zorlar.
        """
        # BTC/USDT 1h, 5,2 yıl, 2026-09-09 ölçümü (docs/Faz-4-Laboratuvar-Raporu.md).
        faz4 = {
            "sma_kesisim": {"oos_sharpe": -1.03, "oos_is_orani": -1.67,
                            "wf_pozitif_katman_orani": 0.5, "wf_kararsizlik": 0.25,
                            "oos_islem": 70, "oos_max_drawdown": 0.124,
                            "stres_bozulma": 0.245},
            "donchian": {"oos_sharpe": -0.35, "oos_is_orani": -0.46,
                         "wf_pozitif_katman_orani": 0.5, "wf_kararsizlik": 0.19,
                         "oos_islem": 56, "oos_max_drawdown": 0.066,
                         "stres_bozulma": 0.153},
            "momentum": {"oos_sharpe": -0.08, "oos_is_orani": -0.09,
                         "wf_pozitif_katman_orani": 0.5, "wf_kararsizlik": 0.21,
                         "oos_islem": 22, "oos_max_drawdown": 0.122,
                         "stres_bozulma": 0.169},
        }
        for ad, olcumler in faz4.items():
            assert not degerlendir(ad, olcumler).gecti, f"{ad} kapılardan geçmemeliydi"
