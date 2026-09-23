"""K-054'ün dört kapısı (K-119 tanımlarıyla): eşikler, yön, ölçülemezlik ve **iki yönlü
doğrulama**. (Faz 11, K-119)

`test_kapilar.py::test_faz4_olcumlerinden_hicbiri_gecmiyor`in kardeşi. K-117/K-118 gösterdi ki
eşikleri yalnız null'ın kuyruğuna göre seçmek (tek yönlü kalibrasyon) gerçek üstünlüğü de
eliyordu. Bu dosya her eşiği **iki** ölçüme bağlar:

1. **Pozitif kontrol geçer.** Gömülü trendli sentetik evrende (`tools/pozitif_kontrol_evren.py`,
   m ∈ {3, 5}, 12 örnek) ölçülen değerlerin **hepsi** eşiği geçer. Eşik bunları eleyecek kadar
   sıkılaşırsa kapı yine gücünü kaybetmiş demektir.
2. **Null'ın tipik değeri geçmez.** Trendsiz (m = 0) sentetik evrenin medyanı kapıda kalır;
   kalmıyorsa eşik null'ın gövdesine inmiş demektir.

Sayılar `docs/research/records/2026-09-23-kapi-yeniden-tasarim.md`deki ölçümün kopyası; eşik
değişirse ölçüm de yeniden yapılmış olmalı ve bu test birlikte güncellenmeli.
"""

from __future__ import annotations

import pytest

from scryne_quant.research import kapilar as kapilar_mod
from scryne_quant.research import kapilar_v2 as v2

#: Pozitif kontrol (m ∈ {3, 5}, 12 örnek, evren yolu): uç değerler.
POZITIF_ZARAR_AZAMI = 0.007
POZITIF_KORUMA_ASGARI = 0.855
#: K-058 null kalibrasyonu (rejim) ve yapısal evren bandı — değişmedi.
OLCULEN_REJIM_P95 = {"donchian": 0.4811, "rsi_donus": 0.6850}
OLCULEN_EVREN_BANDI_ALT = 0.832

#: Null'ın gövdesinden bir çekiliş: trendsiz sentetik evren medyanları (zarar, koruma) ve
#: K-058 donchian kaydırma null'ı (rejim).
NULL_MEDYANI = {
    "pbo_zarar_olasiligi": 0.143,
    "perturbasyon_koruma": 0.650,
    "en_kotu_rejim_sharpe": -0.741,
    "evren_dayaniklilik_orani": None,
}


def _esik(ad: str) -> kapilar_mod.Esik:
    return next(e for e in v2.ESIKLER_V2 if e.ad == ad)


class TestGevsetme:
    def test_zarar_esigi_pozitif_kontrolu_geciriyor_ama_null_u_degil(self):
        assert POZITIF_ZARAR_AZAMI <= v2.PBO_ZARAR_ESIGI < NULL_MEDYANI["pbo_zarar_olasiligi"]

    def test_koruma_esigi_pozitif_kontrolu_geciriyor_ama_null_u_degil(self):
        assert (NULL_MEDYANI["perturbasyon_koruma"] < v2.PERTURBASYON_KORUMA_ESIGI
                <= POZITIF_KORUMA_ASGARI)

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
        assert _esik("parametre_perturbasyonu").yon == ">="
        assert _esik("rejim_kararliligi").yon == ">="
        assert _esik("evren_dayanikliligi").yon == ">="


class TestDegerlendirme:
    KUSURSUZ = {
        "pbo_zarar_olasiligi": 0.0,
        "perturbasyon_koruma": 1.0,
        "en_kotu_rejim_sharpe": 3.0,
        "evren_dayaniklilik_orani": 1.0,
    }

    def test_kusursuz_olcumler_geciyor(self):
        assert v2.kapilari_degerlendir("x", self.KUSURSUZ).gecti

    @pytest.mark.parametrize(
        "alan",
        ["pbo_zarar_olasiligi", "perturbasyon_koruma", "en_kotu_rejim_sharpe",
         "evren_dayaniklilik_orani"],
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

    def test_butun_kapilar_on_iki_kapi(self):
        """K-019 yedi + K-113 `oos_suresi` + K-054 dört."""
        sonuc = v2.butun_kapilar("x", self.KUSURSUZ)
        assert len(sonuc.kapilar) == len(kapilar_mod.ESIKLER) + len(v2.ESIKLER_V2) == 12
        assert "oos_suresi" in sonuc.kapilar

    def test_butun_kapilar_mutlak_engeli_tasiyor(self):
        sonuc = v2.butun_kapilar("x", self.KUSURSUZ, mutlak_engeller=["leak_riski"])
        assert "leak_riski" in sonuc.mutlak_engeller and not sonuc.gecti

    def test_her_esigin_gerekcesi_var(self):
        for e in v2.ESIKLER_V2:
            assert len(e.gerekce) > 200, f"{e.ad}: gerekçe bir ölçüme dayanmalı (K-019)"


class TestKapiAlanlariYaziliyor:
    """K-119 regresyonu: `perturbasyon_koruma` tek sembollü yolda yalnız `detay`a yazılıyor,
    kapının okuduğu `olcumler`e yazılmıyordu — kapı her çekilişte sessizce "ölçülemedi"
    kalırdı. Kapının okuduğu her alan ölçümle aynı olmalı."""

    def test_tek_sembollu_olc_kapi_alanlarini_yazar(self):
        from scryne_quant.common.maliyet import MaliyetModeli
        from scryne_quant.features.barlar import bar_dizileri
        from scryne_quant.research.bolme import Pencere, is_oos
        from scryne_quant.strategy.kutuphane.sma_kesisim import SmaKesisim
        from tests.conftest import bar_uret

        d = bar_dizileri(bar_uret(n=3_000, tohum=3))
        ins, oos = is_oos(3_000, 60)
        tam = Pencere("tam", baslangic=60, bitis=3_000, isinma_baslangic=0)
        izgara = {"hizli": (5, 10, 15), "yavas": (30, 60), "maruziyet": (0.2,)}
        o = v2.olc(SmaKesisim, izgara, MaliyetModeli(fee_taker_bps=1.0, slippage_bps=0.0),
                   "BTCUSDT", "1h", d, ins=ins, oos=oos, tam=tam, asgari_islem=1)
        detay = o["detay"]
        assert o["perturbasyon_koruma"] is not None
        assert o["perturbasyon_koruma"] == detay["perturbasyon"]["perturbasyon_koruma"]
        if "zarar_olasiligi" in detay["pbo"]:
            assert o["pbo_zarar_olasiligi"] == detay["pbo"]["zarar_olasiligi"]
        for e in v2.ESIKLER_V2:
            assert e.alan in o, f"{e.ad}: kapı alanı `{e.alan}` ölçümlerde yok"
