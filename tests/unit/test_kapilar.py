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
    ASGARI_OOS_GUN,
    ESIKLER,
    MUTLAK_ENGELLER,
    Esik,
    degerlendir,
    esik_tablosu,
    oos_suresi_gun,
)

#: Tüm kapıları rahatça geçen ölçüm kümesi. Testlerin çoğu bunu bozarak çalışıyor.
GECEN = {
    "oos_gun": 600.0,
    "oos_yillik_anlamli": True,
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
        # OOS 13.672 bar = 569,67 gün (yıllıklandırma anlamlı; K-113 sınırının kendisi).
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


class TestOosSuresiVeSharpeAnlamliligi:
    """K-113: kısa OOS'un yıllıklandırılmış Sharpe'ı kanıt değildir; iki koşul ayrı.

    (1) `oos_sharpe`/`oos_is_orani` yalnız `oos_yillik_anlamli=True` iken okunur — ön koşul.
    (2) `oos_suresi` ayrı bir kapı: OOS, eşiğin kalibre edildiği en kısa pencereden kısa
        olamaz. İkisi de K-050 yönünde: eksik bilgi = geçilmedi, hiçbir yolla "geçti" olmaz.
    """

    #: R5 FX programının gerçek vakası: OOS 516 bar 1h = 21,5 gün, kontrol Sharpe 6,082
    #: (`docs/research/records/2026-09-21-R5-fx-alpha-1.md`), `yillik_anlamli=False`.
    FX_21_GUN = {
        **GECEN,
        "oos_gun": oos_suresi_gun(516, 3_600_000),
        "oos_yillik_anlamli": False,
        "oos_sharpe": 6.082,
        "oos_is_orani": 3.0,
    }

    def test_oos_suresi_gun_yillik_anlamli_ile_ayni_olcek(self):
        assert oos_suresi_gun(516, 3_600_000) == pytest.approx(21.5)
        assert oos_suresi_gun(13_672, 3_600_000) == pytest.approx(569.6667, abs=1e-3)
        assert oos_suresi_gun(3_484, 4 * 3_600_000) == pytest.approx(580.6667, abs=1e-3)
        assert oos_suresi_gun(0, 3_600_000) == 0.0
        with pytest.raises(ValueError):
            oos_suresi_gun(-1, 3_600_000)
        with pytest.raises(ValueError):
            oos_suresi_gun(10, 0)

    def test_kisa_oos_yuksek_sharpe_kapiyi_gecmiyor(self):
        """21,5 gün / Sharpe 6,08: eskiden 'geçti', şimdi ölçülemedi + süre kaldı."""
        sonuc = degerlendir("fx_kontrol", self.FX_21_GUN)
        assert not sonuc.gecti
        assert sonuc.kapilar["oos_sharpe"]["gecti"] is None
        # sayı kayda girer, karar girmez:
        assert sonuc.kapilar["oos_sharpe"]["deger"] == 6.082
        assert sonuc.kapilar["oos_sharpe"]["on_kosul"] == {
            "alan": "oos_yillik_anlamli", "deger": False,
        }
        assert sonuc.kapilar["oos_is_orani"]["gecti"] is None
        assert sonuc.kapilar["oos_suresi"]["gecti"] is False
        assert {"oos_suresi", "oos_sharpe", "oos_is_orani"} <= set(sonuc.kalan_kapilar)

    def test_on_kosul_eksikse_gecilmis_sayilmiyor(self):
        """Bayrağı hiç taşımayan (K-113 öncesi) ölçüm kümesi de geçemez: eksik = sağlanmadı."""
        eski = {a: d for a, d in GECEN.items() if a not in ("oos_yillik_anlamli", "oos_gun")}
        sonuc = degerlendir("eski", eski)
        assert not sonuc.gecti
        assert sonuc.kapilar["oos_sharpe"]["gecti"] is None
        assert sonuc.kapilar["oos_sharpe"]["on_kosul"] == {
            "alan": "oos_yillik_anlamli", "deger": None,
        }
        assert sonuc.kapilar["oos_suresi"]["gecti"] is None

    @pytest.mark.parametrize("deger", [1, "True", 1.0, "evet"])
    def test_on_kosul_yalniz_gercek_true_ile_saglanir(self, deger):
        sonuc = degerlendir("x", {**GECEN, "oos_yillik_anlamli": deger})
        assert sonuc.kapilar["oos_sharpe"]["gecti"] is None
        assert not sonuc.gecti

    def test_anlamli_oos_ta_sharpe_mantigi_aynen(self):
        """Ön koşul sağlanınca eski eşik ve yön birebir: 1,04 sınırı, ≥ yönü."""
        esik = next(e for e in ESIKLER if e.ad == "oos_sharpe")
        for sharpe, beklenen in ((1.04, True), (1.0399, False), (1.2, True), (-0.5, False)):
            sonuc = degerlendir("x", {**GECEN, "oos_sharpe": sharpe})
            assert sonuc.kapilar["oos_sharpe"]["gecti"] is beklenen, sharpe
            assert "on_kosul" not in sonuc.kapilar["oos_sharpe"]
        assert esik.sinir == 1.04 and esik.yon == ">="

    def test_oos_suresi_siniri(self):
        """Sınır = en kısa kalibre OOS (13.672 bar × 1h): o geçer, bir bar eksiği kalır."""
        assert oos_suresi_gun(13_672, 3_600_000) == ASGARI_OOS_GUN
        sinamalar = (
            (13_672, True), (13_671, False), (3_484 * 4, True), (516, False), (23_826, True),
        )
        for bar, beklenen in sinamalar:
            sonuc = degerlendir("x", {**GECEN, "oos_gun": oos_suresi_gun(bar, 3_600_000)})
            assert sonuc.kapilar["oos_suresi"]["gecti"] is beklenen, bar

    def test_uzun_oos_kisa_sharpe_yine_kalir(self):
        """Süre kapısı Sharpe kapısının yerine geçmez: ikisi bağımsız."""
        sonuc = degerlendir("x", {**GECEN, "oos_gun": 2000.0, "oos_sharpe": 0.9})
        assert sonuc.kapilar["oos_suresi"]["gecti"] is True
        assert sonuc.kapilar["oos_sharpe"]["gecti"] is False
        assert not sonuc.gecti

    def test_yillik_anlamli_ama_sure_kisa(self):
        """30 gün ≤ OOS < 570 gün: Sharpe yorumlanabilir ama eşik bu uzunlukta ölçülmemiş."""
        kisa = {**GECEN, "oos_gun": 45.0, "oos_yillik_anlamli": True, "oos_sharpe": 3.0}
        sonuc = degerlendir("x", kisa)
        assert sonuc.kapilar["oos_sharpe"]["gecti"] is True  # sayı okunabilir…
        assert sonuc.kapilar["oos_suresi"]["gecti"] is False  # …ama eşik bu pencere için yok
        assert not sonuc.gecti

    def test_on_kosul_tabloya_ve_kayda_giriyor(self):
        tablo = {s["ad"]: s for s in esik_tablosu()}
        assert tablo["oos_sharpe"]["on_kosul"] == "oos_yillik_anlamli"
        assert tablo["oos_is_orani"]["on_kosul"] == "oos_yillik_anlamli"
        assert "on_kosul" not in tablo["oos_suresi"]
        assert "on_kosul" not in tablo["max_drawdown"]

    def test_on_kosul_kapiyi_gevsetemez(self):
        """Ön koşul yalnız `gecti`yi None yapar; True olan bir şeyi asla True yapmaz."""
        for esik in ESIKLER:
            if esik.on_kosul is None:
                continue
            kotu = {**GECEN, esik.alan: esik.sinir - 1.0, "oos_yillik_anlamli": True}
            assert degerlendir("x", kotu).kapilar[esik.ad]["gecti"] is False
            kotu["oos_yillik_anlamli"] = False
            assert degerlendir("x", kotu).kapilar[esik.ad]["gecti"] is None
