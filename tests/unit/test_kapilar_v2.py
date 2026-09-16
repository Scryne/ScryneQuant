"""K-054'ün dört yeni kapısı: eşikler, yön, ölçülemezlik ve **gevşetme**. (Faz 11)

`test_kapilar.py::test_faz4_olcumlerinden_hicbiri_gecmiyor`in kardeşi burada ve aynı işi
görüyor: birisi bir eşiği bugünkü sonuca bakıp gevşetirse kırmızıya dönüyor. İki katmanlı:

1. **Eşik ölçümün gerisine düşemez.** Her eşik, iki ızgarada ölçülen null sınırlarının
   *sıkı olanına* eşit ya da ondan sıkı olmak zorunda (K-007: belirsizlikte aleyhte).
   Sayılar `docs/Faz-11-Dogrulama-Raporu.md`deki ölçümün kopyası; eşik değişirse ölçüm de
   yeniden yapılmış olmalı ve bu test birlikte güncellenmeli.
2. **Null'ın tipik bir değeri geçmemeli.** Kalibrasyonun medyan değerleriyle kurulan bir
   çekiliş kapılarda kalmalı — kalmıyorsa eşik null'un gövdesine inmiş demektir.
"""

from __future__ import annotations

import pytest

from scryne_quant.research import kapilar as kapilar_mod
from scryne_quant.research import kapilar_v2 as v2

#: Kalibrasyon ölçümleri (runs/kalibrasyon-v2/, 2026-09-16). `<=` kapısında sıkı olan
#: düşük, `>=` kapısında yüksek olanı.
OLCULEN_PBO_P05 = {"donchian": 0.0087, "rsi_donus": 0.0462}
OLCULEN_PERTURBASYON_P05 = {"donchian": 0.0752, "rsi_donus": 0.0565}
OLCULEN_REJIM_P95 = {"donchian": 0.4811, "rsi_donus": 0.6850}
OLCULEN_EVREN_BANDI_ALT = 0.832

#: Null'ın gövdesinden bir çekiliş (donchian kaydırma null'ının medyanları).
NULL_MEDYANI = {
    "pbo": 0.237,
    "perturbasyon_dusus": 0.246,
    "en_kotu_rejim_sharpe": -0.741,
    "evren_dayaniklilik_orani": None,
}


def _esik(ad: str) -> kapilar_mod.Esik:
    return next(e for e in v2.ESIKLER_V2 if e.ad == ad)


class TestGevsetme:
    def test_pbo_esigi_olcumun_gerisine_dusmuyor(self):
        assert min(OLCULEN_PBO_P05.values()) >= v2.PBO_ESIGI

    def test_perturbasyon_esigi_olcumun_gerisine_dusmuyor(self):
        assert min(OLCULEN_PERTURBASYON_P05.values()) >= v2.PERTURBASYON_ESIGI

    def test_rejim_esigi_olcumun_gerisine_dusmuyor(self):
        assert max(OLCULEN_REJIM_P95.values()) <= v2.REJIM_ESIGI

    def test_evren_esigi_olculen_bandin_altinda_kaliyor(self):
        """Evren eşiği bir iştah seçimi, ama ölçülen bandın **içine** giremez: girerse
        çeşitlendirilmiş bir kıyas portföyü bile kapıda kalır ve kapı bilgi taşımaz.
        Yarım performans çizgisinin (0,5) altına da inemez: o hâlde patolojik yoğunlaşmayı
        bile geçirir."""
        assert 0.5 < v2.EVREN_DAYANIKLILIK_ESIGI < OLCULEN_EVREN_BANDI_ALT

    def test_null_medyani_gecmiyor(self):
        """Edge'siz bir ızgaranın tipik değerleri kapılarda kalmalı."""
        sonuc = v2.kapilari_degerlendir("null", NULL_MEDYANI)
        assert not sonuc.gecti
        for ad in ("pbo", "parametre_perturbasyonu", "rejim_kararliligi"):
            assert sonuc.kapilar[ad]["gecti"] is False, f"{ad} null medyanını geçirdi"

    def test_yonler_degismedi(self):
        """Yönü ters çevirmek eşiği değiştirmeden kapıyı kaldırmanın en sessiz yolu."""
        assert _esik("pbo").yon == "<="
        assert _esik("parametre_perturbasyonu").yon == "<="
        assert _esik("rejim_kararliligi").yon == ">="
        assert _esik("evren_dayanikliligi").yon == ">="


class TestDegerlendirme:
    KUSURSUZ = {
        "pbo": 0.0,
        "perturbasyon_dusus": 0.0,
        "en_kotu_rejim_sharpe": 3.0,
        "evren_dayaniklilik_orani": 1.0,
    }

    def test_kusursuz_olcumler_geciyor(self):
        assert v2.kapilari_degerlendir("x", self.KUSURSUZ).gecti

    @pytest.mark.parametrize(
        "alan",
        ["pbo", "perturbasyon_dusus", "en_kotu_rejim_sharpe", "evren_dayaniklilik_orani"],
    )
    def test_olculemeyen_kapi_gecilmis_sayilmaz(self, alan: str):
        """K-019: 'veri yoktu' ile 'kapıdan geçti' aynı şey değil."""
        olcumler = dict(self.KUSURSUZ) | {alan: None}
        sonuc = v2.kapilari_degerlendir("x", olcumler)
        assert not sonuc.gecti

    def test_tek_sembollu_cekilis_evren_kapisinda_duruyor(self):
        """K-054: tek sembolde geliştirilen strateji de evrene karşı sınanmak zorunda."""
        olcumler = dict(self.KUSURSUZ) | {"evren_dayaniklilik_orani": None}
        sonuc = v2.kapilari_degerlendir("x", olcumler)
        assert sonuc.kalan_kapilar == ["evren_dayanikliligi"]

    def test_butun_kapilar_on_bir_kapi(self):
        sonuc = v2.butun_kapilar("x", self.KUSURSUZ)
        assert len(sonuc.kapilar) == len(kapilar_mod.ESIKLER) + len(v2.ESIKLER_V2) == 11

    def test_butun_kapilar_mutlak_engeli_tasiyor(self):
        sonuc = v2.butun_kapilar("x", self.KUSURSUZ, mutlak_engeller=["leak_riski"])
        assert "leak_riski" in sonuc.mutlak_engeller and not sonuc.gecti

    def test_her_esigin_gerekcesi_var(self):
        for e in v2.ESIKLER_V2:
            assert len(e.gerekce) > 200, f"{e.ad}: gerekçe bir ölçüme dayanmalı (K-019)"
