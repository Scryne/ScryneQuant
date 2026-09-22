"""Araştırma programı defteri, arama bütçesi ve `leak_riski`. (K-051, K-049, Faz 11)

Faz 11'in iki bitti kriteri burada:

- *"Program kaydı olmadan bir araştırma programı koşturulamıyor (K-051/2, testle)."*
- *"`leak_riski` taşıyan bir sonuç kapıdan geçemiyor (testle)."*

İkisi de **sessiz geçilebilecek** kurallar: birincisinde hiçbir test kırılmaz, defter
sadece eksik kalır; ikincisinde look-ahead testi bile yeşil kalır çünkü sızıntı veride
değil modelin ağırlıklarında. Bu yüzden ikisinin de kendi testi var.
"""

from __future__ import annotations

import pytest

from scryne_quant.research import kapilar as kapilar_mod
from scryne_quant.research.hipotez import Hipotez, HipotezDefteri
from scryne_quant.research.program import (
    LlmTuretimi,
    ProgramDefteri,
    ProgramHatasi,
    ProgramKaydi,
    leak_riski_var_mi,
)

GEREKCE = (
    "Cross-sectional sıralama, tek sembol getirisinden farklı bir bilgi taşıyor mu diye "
    "sorulacak; kaynak evren geneli göreli güç."
)
FARK = (
    "Evren geneli göreli güç ile tek sembolün kendi getirisi arasındaki korelasyon 0,18 "
    "ölçüldü; yani sıralama fiyat geçmişinin tekrarı değil."
)


def _kayit(ad: str = "cross_sectional_01", azami: int = 5) -> ProgramKaydi:
    return ProgramKaydi(
        ad=ad,
        gerekce=GEREKCE,
        kaynak_farki=FARK,
        kaynak_olcumu={"korelasyon": 0.18, "ornek": 4464},
        azami_cekilis=azami,
        durma_kurali="Bütçe dolduğunda ya da ilk 3 çekilişin hepsi kapıda kalırsa durulur.",
        esik_tahmini={"yontem": "bonferroni", "mevcut": 1.02, "tahmin": 1.18},
    )


def _hipotez(sira: int, program: str = "cross_sectional_01") -> Hipotez:
    return Hipotez.kur(
        "donchian",
        "1h",
        f"sha-{sira}",
        {"giris": [20, 40]},
        "Bu hipotez neden deneniyor sorusunun yeterince uzun cevabı burada.",
        program=program,
    )


class TestProgramKaydi:
    def test_gecerli_kayit(self, tmp_path):
        d = ProgramDefteri(tmp_path / "p.jsonl")
        k = d.ac(_kayit())
        assert d.acik("cross_sectional_01") is not None
        assert k.kimlik

    def test_kisa_gerekce_reddediliyor(self):
        with pytest.raises(ProgramHatasi, match="gerekce en az"):
            ProgramKaydi(
                ad="x_programi",
                gerekce="kısa",
                kaynak_farki=FARK,
                kaynak_olcumu={"a": 1},
                azami_cekilis=3,
                durma_kurali="yeterince uzun bir durma kuralı",
                esik_tahmini={"a": 1},
            )

    def test_olcusuz_kaynak_farki_reddediliyor(self):
        """K-045'in istisnası 'ölçüyle gerekçelendirilmiş' diyor; iddia ölçü değildir."""
        with pytest.raises(ProgramHatasi, match="kaynak_olcumu boş olamaz"):
            ProgramKaydi(
                ad="x_programi",
                gerekce=GEREKCE,
                kaynak_farki=FARK,
                kaynak_olcumu={},
                azami_cekilis=3,
                durma_kurali="yeterince uzun bir durma kuralı",
                esik_tahmini={"a": 1},
            )

    def test_durma_kurali_zorunlu(self):
        with pytest.raises(ProgramHatasi, match="durma kuralı"):
            ProgramKaydi(
                ad="x_programi",
                gerekce=GEREKCE,
                kaynak_farki=FARK,
                kaynak_olcumu={"a": 1},
                azami_cekilis=3,
                durma_kurali="kısa",
                esik_tahmini={"a": 1},
            )

    def test_esik_tahmini_zorunlu(self):
        """K-051/3: program kendi dikeceği duvarı baştan görmeli."""
        with pytest.raises(ProgramHatasi, match="esik_tahmini"):
            ProgramKaydi(
                ad="x_programi",
                gerekce=GEREKCE,
                kaynak_farki=FARK,
                kaynak_olcumu={"a": 1},
                azami_cekilis=3,
                durma_kurali="yeterince uzun bir durma kuralı",
                esik_tahmini={},
            )

    def test_ad_kod_olmali(self):
        with pytest.raises(ProgramHatasi, match="kod olmalı"):
            ProgramKaydi(
                ad="Cross Sectional",
                gerekce=GEREKCE,
                kaynak_farki=FARK,
                kaynak_olcumu={"a": 1},
                azami_cekilis=3,
                durma_kurali="yeterince uzun bir durma kuralı",
                esik_tahmini={"a": 1},
            )

    def test_ayni_ad_iki_kez_acilamaz(self):
        """İkinci kayıt, bütçeyi sessizce ikiye katlamanın en kolay yolu olurdu."""
        d = ProgramDefteri.__new__(ProgramDefteri)
        import tempfile
        from pathlib import Path

        object.__setattr__(d, "yol", Path(tempfile.mkdtemp()) / "p.jsonl")
        d.ac(_kayit())
        with pytest.raises(ProgramHatasi, match="zaten açık"):
            d.ac(_kayit())

    def test_kapandiktan_sonra_yeniden_acilabilir(self, tmp_path):
        d = ProgramDefteri(tmp_path / "p.jsonl")
        d.ac(_kayit())
        d.kapat("cross_sectional_01", "Üç çekiliş de kapıda kaldı; program kapandı.", 3)
        assert d.acik("cross_sectional_01") is None
        d.ac(_kayit())  # yeni gerekçe, yeni kayıt — defter append-only
        assert d.acik("cross_sectional_01") is not None

    def test_kapanis_sonuc_metni_istiyor(self, tmp_path):
        d = ProgramDefteri(tmp_path / "p.jsonl")
        d.ac(_kayit())
        with pytest.raises(ProgramHatasi, match="sonuç metni"):
            d.kapat("cross_sectional_01", "yok", 0)


class TestButce:
    def test_program_kaydi_olmadan_cekilis_yazilamaz(self, tmp_path):
        """**Faz 11 bitti kriteri.** (K-051/2)"""
        programlar = ProgramDefteri(tmp_path / "p.jsonl")
        defter = HipotezDefteri(tmp_path / "h.jsonl")
        with pytest.raises(ProgramHatasi, match="açık bir program değil"):
            defter.kaydet(_hipotez(1), programlar=programlar)

    def test_programsiz_hipotez_reddediliyor(self, tmp_path):
        programlar = ProgramDefteri(tmp_path / "p.jsonl")
        programlar.ac(_kayit())
        defter = HipotezDefteri(tmp_path / "h.jsonl")
        with pytest.raises(ProgramHatasi, match="bir programa ait olmalı"):
            defter.kaydet(_hipotez(1, program=""), programlar=programlar)

    def test_butce_dolunca_duruyor(self, tmp_path):
        programlar = ProgramDefteri(tmp_path / "p.jsonl")
        programlar.ac(_kayit(azami=2))
        defter = HipotezDefteri(tmp_path / "h.jsonl")
        defter.kaydet(_hipotez(1), programlar=programlar)
        defter.kaydet(_hipotez(2), programlar=programlar)
        with pytest.raises(ProgramHatasi, match="arama bütçesi doldu"):
            defter.kaydet(_hipotez(3), programlar=programlar)

    def test_butce_durumu_okunabiliyor(self, tmp_path):
        programlar = ProgramDefteri(tmp_path / "p.jsonl")
        programlar.ac(_kayit(azami=4))
        defter = HipotezDefteri(tmp_path / "h.jsonl")
        defter.kaydet(_hipotez(1), programlar=programlar)
        durum = programlar.butce("cross_sectional_01", defter.tumu())
        assert durum["harcanan"] == 1 and durum["kalan"] == 3

    def test_programsiz_eski_kayitlar_bozulmuyor(self, tmp_path):
        """Faz 4'ün 38 çekilişi program öncesi; `programlar` verilmeden yazılabilir."""
        defter = HipotezDefteri(tmp_path / "h.jsonl")
        assert defter.kaydet(_hipotez(1, program="")) == 1
        assert defter.ozet()["program_basina"] == {"(program_oncesi)": 1}


class TestHipotezKimligi:
    def test_evren_kimligi_degistiriyor(self):
        """K-051/4: evren tanımı aynı veriye yeni bir soru sormanın biçimi."""
        a = _hipotez(1)
        b = Hipotez.kur(
            a.strateji, a.timeframe, a.veri_sha256, a.izgara, a.gerekce, evren="E1"
        )
        assert a.kimlik != b.kimlik

    def test_program_kimligi_degistirmiyor(self):
        """Aynı soruyu iki program altında sormak yeni bir soru değildir."""
        a = _hipotez(1, program="p_bir")
        b = _hipotez(1, program="p_iki")
        assert a.kimlik == b.kimlik

    def test_bos_v2_alanlari_kimligi_degistirmiyor(self):
        """Defterdeki 38 eski satırın kimliği korunmak zorunda: `dogrula()` onları tanımalı."""
        a = Hipotez.kur("donchian", "1h", "sha", {"giris": [20]}, "yeterince uzun gerekçe metni")
        b = Hipotez.kur(
            "donchian",
            "1h",
            "sha",
            {"giris": [20]},
            "yeterince uzun gerekçe metni",
            evren="",
            portfoy="",
            rejim="",
        )
        assert a.kimlik == b.kimlik


class TestLeakRiski:
    def test_egitim_kesimi_oncesi_donem_riskli(self):
        """K-049/4: 2026 modeli 2023 haberini okuduğunda sonrasını **biliyor**."""
        t = LlmTuretimi(
            model="ornek-model",
            egitim_kesim_ms=1_700_000_000_000,
            kapsam_baslangic_ms=1_600_000_000_000,
            kapsam_bitis_ms=1_800_000_000_000,
            prompt_hash="a" * 8,
            girdi_hash="b" * 8,
        )
        assert t.leak_riski is True
        assert leak_riski_var_mi([t])

    def test_kesim_sonrasi_donem_temiz(self):
        t = LlmTuretimi(
            model="ornek-model",
            egitim_kesim_ms=1_700_000_000_000,
            kapsam_baslangic_ms=1_700_000_000_001,
            kapsam_bitis_ms=1_800_000_000_000,
            prompt_hash="a" * 8,
            girdi_hash="b" * 8,
        )
        assert t.leak_riski is False
        assert not leak_riski_var_mi([t])

    def test_dondurulmamis_cikti_reddediliyor(self):
        """K-049/5: backtest içinde hesaplanan bir LLM çıktısı K-009'u düşürür."""
        with pytest.raises(ProgramHatasi, match="dondurulmuş"):
            LlmTuretimi(
                model="ornek-model",
                egitim_kesim_ms=1_700_000_000_000,
                kapsam_baslangic_ms=1_700_000_000_001,
                kapsam_bitis_ms=1_800_000_000_000,
                prompt_hash="",
                girdi_hash="b" * 8,
            )

    def test_leak_riski_mutlak_engel_listesinde(self):
        assert "leak_riski" in kapilar_mod.MUTLAK_ENGELLER

    def test_leak_riskli_sonuc_kapidan_gecemiyor(self):
        """**Faz 11 bitti kriteri.** Bütün sayısal kapılar geçse bile engel duruyor."""
        kusursuz = {
            "oos_gun": 1_000.0,  # K-113: süre kapısı + Sharpe'ın ön koşulu
            "oos_yillik_anlamli": True,
            "oos_sharpe": 99.0,
            "oos_is_orani": 99.0,
            "wf_pozitif_katman_orani": 1.0,
            "wf_kararsizlik": 0.0,
            "oos_islem": 1_000,
            "oos_max_drawdown": 0.0,
            "stres_bozulma": 0.0,
        }
        temiz = kapilar_mod.degerlendir("x", kusursuz)
        assert temiz.gecti is True
        riskli = kapilar_mod.degerlendir("x", kusursuz, mutlak_engeller=["leak_riski"])
        assert riskli.gecti is False
        assert "leak_riski" in riskli.mutlak_engeller

    def test_sonuc_leak_riskini_engel_olarak_tasiyor(self):
        from dataclasses import replace

        from scryne_quant.backtest.motor import Backtest
        from scryne_quant.common.maliyet import MaliyetModeli
        from scryne_quant.features.barlar import bar_dizileri
        from tests.conftest import PlanliStrateji, bar_uret

        diziler = bar_dizileri(bar_uret(n=80))
        sonuc = Backtest(
            PlanliStrateji({10: ("BUY", 0.2), 40: ("FLAT", 0.0)}),
            MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0),
        ).calistir("BTCUSDT", "1h", diziler)
        assert "leak_riski" not in sonuc.promotion_engelleri
        riskli = replace(sonuc, leak_riski=True)
        assert "leak_riski" in riskli.promotion_engelleri
        # Hash'e girmiyor: bir provenans beyanı, sonucun sayılarını değiştirmiyor.
        assert riskli.sonuc_hash == sonuc.sonuc_hash
