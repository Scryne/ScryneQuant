"""Portföy stratejisi değerlendirme hattı ve kesitsel aileler. (Faz 12)

Ölçülenler:

1. Hat 11 kapının hepsini üretiyor; ölçülemeyen kapı `None` ve geçilmiş sayılmıyor.
2. Tek bir pencere koşusu, aynı pencerenin görünümünü elle kurup motordan geçirmekle
   **bit düzeyinde** aynı (hat kendi aritmetiğini uydurmuyor).
3. Kesitsel aileler skoru doğru yönde sıralıyor ve geleceği görmüyor.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.evren_kosu import EvrenVerisi
from scryne_quant.strategy.evren import LISTELENMEDI
from scryne_quant.strategy.kosu import evren_gorunum_kur
from scryne_quant.strategy.kutuphane.kesitsel import (
    KesitselDusukOynaklik,
    KesitselGuc,
    KesitselTers,
)
from tests.conftest import bar_uret

MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
SEMBOLLER = ("AAAUSDT", "BBBUSDT", "BTCUSDT", "CCCUSDT", "DDDUSDT")
N = 1_600


def _veri(n: int = N, isinma: int = 60, gec: int = 400) -> EvrenVerisi:
    diziler = {
        s: {a: np.array(x, copy=True) for a, x in bar_dizileri(bar_uret(n=n, tohum=21 + i)).items()}  # noqa: E501
        for i, s in enumerate(SEMBOLLER)
    }
    # DDD geç listeleniyor: ilk `gec` bar ızgara doldurma barı.
    d = diziler["DDDUSDT"]
    for ad, dizi in d.items():
        if ad == "open_time":
            continue
        if ad == "quality_status":
            q = dizi.astype(object)
            q[:gec] = LISTELENMEDI
            d[ad] = q
        elif ad == "trades":
            dizi[:gec] = 0
        else:
            dizi[:gec] = np.nan
    uyelik = {s: np.ones(n, dtype=bool) for s in SEMBOLLER}
    uyelik["DDDUSDT"][:gec] = False
    return EvrenVerisi(
        timeframe="1h",
        zamanlar=diziler["AAAUSDT"]["open_time"],
        diziler=diziler,
        uyelik=uyelik,
        veri_sha256={s: "0" * 64 for s in SEMBOLLER},
        meta={},
        olcum_baslangici=isinma,
        kural_kimligi="test",
    )


IZGARA = {"pencere": (12, 24), "azami_enstruman": (2, 3), "yeniden_dengele_bar": (24,)}


class TestTekKosu:
    def test_elle_kurulan_gorunumle_bit_duzeyinde_ayni(self):
        veri = _veri()
        pencere = Pencere("p", baslangic=200, bitis=900, isinma_baslangic=150)
        strateji = KesitselGuc(pencere=24, azami_enstruman=2, yeniden_dengele_bar=24)
        hat = ed.kosu(strateji, MALIYET, veri, pencere)

        dilim = pencere.dilim()
        g = evren_gorunum_kur(
            "1h",
            {s: {a: x[dilim] for a, x in dz.items()} for s, dz in veri.diziler.items()},
            {s: u[dilim] for s, u in veri.uyelik.items()},
            KesitselGuc(pencere=24, azami_enstruman=2, yeniden_dengele_bar=24),
            kural_kimligi="test",
        )
        elle = CokluBacktest(
            KesitselGuc(pencere=24, azami_enstruman=2, yeniden_dengele_bar=24), MALIYET,
            sifira_yaz_bar=ed.SIFIRA_YAZ_BAR,
        ).calistir(g, veri_sha256=veri.veri_sha256, olcum_baslangici=pencere.olcum_baslangici)
        assert hat.ozkaynak.tobytes() == elle.ozkaynak.tobytes()
        assert hat.sonuc_hash == elle.sonuc_hash

    def test_cikarilan_sembol_hic_tasinmaz(self):
        veri = _veri()
        pencere = Pencere("p", baslangic=100, bitis=1_200, isinma_baslangic=40)
        s = ed.kosu(
            KesitselGuc(pencere=24, azami_enstruman=2, yeniden_dengele_bar=24),
            MALIYET, veri, pencere, cikarilanlar=frozenset({"AAAUSDT"}),
        )
        assert all(i.sembol != "AAAUSDT" for i in s.islemler)

    def test_gec_listelenen_sembol_aday_olabiliyor(self):
        """ATR düzeltmesinin (Faz 12) hattaki karşılığı: DDD listelendikten sonra işlem görür."""
        veri = _veri()
        pencere = Pencere("p", baslangic=60, bitis=N, isinma_baslangic=0)
        s = ed.kosu(
            KesitselGuc(pencere=12, azami_enstruman=4, yeniden_dengele_bar=24),
            MALIYET, veri, pencere,
        )
        assert any(i.sembol == "DDDUSDT" for i in s.islemler)


class TestKesitselSiralama:
    @pytest.mark.parametrize(
        ("sinif", "beklenen_yon"),
        [(KesitselGuc, 1.0), (KesitselTers, -1.0)],
    )
    def test_skor_yonu(self, sinif, beklenen_yon):
        veri = _veri()
        pencere = Pencere("p", baslangic=100, bitis=101 + 1, isinma_baslangic=0)
        strateji = sinif(pencere=24, azami_enstruman=1, yeniden_dengele_bar=24)
        g = ed.gorunum(veri, strateji, pencere)
        strateji.hazirla()
        hedef = strateji.on_bar(g.baglam(100))
        secilen = [x.symbol for x in hedef.sinyaller if x.target_exposure > 0]
        roc = {
            s: g.gorunumler[s].ozellikler["skor_ham"][100]
            for s in SEMBOLLER if veri.uyelik[s][100]
        }
        hedef_sembol = max(roc, key=lambda s: beklenen_yon * roc[s])
        assert secilen == [hedef_sembol]

    def test_hedef_brut_ve_esit_agirlik(self):
        veri = _veri()
        pencere = Pencere("p", baslangic=100, bitis=102, isinma_baslangic=0)
        strateji = KesitselDusukOynaklik(pencere=24, azami_enstruman=3, yeniden_dengele_bar=24)
        g = ed.gorunum(veri, strateji, pencere)
        strateji.hazirla()
        hedef = strateji.on_bar(g.baglam(100))
        agirliklar = [x.target_exposure for x in hedef.sinyaller if x.target_exposure > 0]
        assert len(agirliklar) == 3
        assert sum(agirliklar) == pytest.approx(0.2)
        assert max(agirliklar) == pytest.approx(min(agirliklar))

    def test_gelecek_bozulunca_t_kadarki_kararlar_ayni(self):
        """K-002: `t` sonrası fiyatlar tanınmaz hâle getirilince `t`ye kadarki hedefler aynı."""
        veri = _veri()
        t = 700
        pencere = Pencere("p", baslangic=60, bitis=N, isinma_baslangic=0)

        def kararlar(v: EvrenVerisi) -> list[str]:
            strateji = KesitselTers(pencere=24, azami_enstruman=2, yeniden_dengele_bar=24)
            g = ed.gorunum(v, strateji, pencere)
            strateji.hazirla()
            out = []
            for i in range(t + 1):
                h = strateji.on_bar(g.baglam(i))
                if h is not None:
                    out.append(json.dumps(h.model_dump(), sort_keys=True))
            return out

        bozuk = _veri()
        rng = np.random.default_rng(0)
        for dz in bozuk.diziler.values():
            for ad in ("open", "high", "low", "close"):
                dz[ad][t + 1:] = dz[ad][t + 1:] * rng.uniform(0.2, 5.0, N - t - 1)
        assert kararlar(veri) == kararlar(bozuk)


class TestTamDegerlendirme:
    def test_on_iki_kapi_uretiliyor(self):
        veri = _veri()
        sonuc = ed.degerlendir(
            KesitselGuc, IZGARA, MALIYET, veri, secim="plato",
            egitim_bar=500, test_bar=200, asgari_islem=1,
        )
        kapilar = sonuc["kapilar"]["kapilar"]
        assert set(kapilar) == {
            "oos_suresi", "oos_sharpe", "oos_is_orani", "wf_katman_basari", "parametre_kararliligi",
            "asgari_islem", "max_drawdown", "stres_dayanikliligi",
            "pbo", "parametre_perturbasyonu", "rejim_kararliligi", "evren_dayanikliligi",
        }
        # Ölçülemeyen kapı geçilmiş sayılmıyor.
        for k in kapilar.values():
            if k["deger"] is None:
                assert k["gecti"] is None
        assert sonuc["kapilar"]["gecti"] is False or all(
            k["gecti"] is True for k in kapilar.values()
        )
        assert sonuc["pencereler"]["walk_forward"]["katman"] >= 2
        json.dumps(sonuc, default=str)  # kayda yazılabilir

    def test_gecerli_aday_yoksa_secime_bagli_kapilar_olculemez(self):
        veri = _veri()
        sonuc = ed.degerlendir(
            KesitselGuc, IZGARA, MALIYET, veri, egitim_bar=500, test_bar=200,
            asgari_islem=10_000,
        )
        k = sonuc["kapilar"]["kapilar"]
        assert k["oos_sharpe"]["gecti"] is None
        assert k["evren_dayanikliligi"]["gecti"] is None
        assert sonuc["kapilar"]["gecti"] is False

    def test_rejim_kiyasi_yoksa_hata(self):
        veri = _veri()
        with pytest.raises(ed.EvrenDegerlendirmeHatasi):
            ed.degerlendir(KesitselGuc, IZGARA, MALIYET, veri, rejim_kiyasi="YOKUSDT")


def _havuz_verisi() -> EvrenVerisi:
    """Havuz işçisinin veri üreticisi: modül düzeyinde, yani spawn ile pickle'lanabilir."""
    return _veri()


class TestHavuzKosucu:
    def test_havuz_seri_ile_bit_duzeyinde_ayni(self):
        from concurrent.futures import ProcessPoolExecutor

        veri = _veri()
        pencere = Pencere("p", baslangic=200, bitis=1_200, isinma_baslangic=100)
        seri, seri_sonuc = ed.tara(KesitselGuc, IZGARA, MALIYET, veri, pencere, asgari_islem=1)
        with ProcessPoolExecutor(
            max_workers=2, initializer=ed.isci_baslat, initargs=(_havuz_verisi, MALIYET)
        ) as havuz:
            paralel, paralel_sonuc = ed.tara(
                KesitselGuc, IZGARA, MALIYET, veri, pencere, asgari_islem=1,
                kosucu=ed.havuz_kosucu(havuz),
            )
            _, kisitli_sonuc = ed.tara(
                KesitselGuc, IZGARA, MALIYET, veri, pencere, asgari_islem=1,
                kosucu=ed.havuz_kosucu(havuz, buyuk_is_bar=10, buyuk_is_eszamanli=1),
            )
        assert [s.sonuc_hash for s in seri_sonuc] == [s.sonuc_hash for s in paralel_sonuc]
        assert [s.sonuc_hash for s in seri_sonuc] == [s.sonuc_hash for s in kisitli_sonuc]
        assert seri.sozluk() == paralel.sozluk()


class TestHipotezKimligi:
    def test_kayit_ve_kosu_ayni_kimligi_gorur(self):
        a = ed.hipotez_kur("kesitsel_guc_haftalik", _veri(), program="p", gerekce="x" * 20)
        b = ed.hipotez_kur("kesitsel_guc_haftalik", _veri(), program="q", gerekce="y" * 20)
        assert a.kimlik == b.kimlik  # program ve gerekçe kimliğe girmiyor
        assert a.evren == "test" and a.portfoy == ed.KESITSEL_PORTFOY
        assert a.secim == ed.KESITSEL_SECIM

    def test_yeniden_dengeleme_ve_veri_yeni_hipotezdir(self):
        veri = _veri()
        haftalik = ed.hipotez_kur("kesitsel_guc_haftalik", veri, program="p", gerekce="x" * 20)
        aylik = ed.hipotez_kur("kesitsel_guc_aylik", veri, program="p", gerekce="x" * 20)
        assert haftalik.kimlik != aylik.kimlik
        baska = _veri()
        baska.veri_sha256["AAAUSDT"] = "1" * 64
        assert ed.veri_kimligi(baska) != ed.veri_kimligi(veri)
        uyelik_baska = _veri()
        uyelik_baska.meta["tablo_hash"] = "farkli"
        assert ed.veri_kimligi(uyelik_baska) != ed.veri_kimligi(veri)


class TestEvrenIzgaralari:
    def test_her_cekilis_12_noktali_ve_kurulabilir(self):
        from scryne_quant.research.izgaralar import EVREN_CEKILISLERI
        from scryne_quant.research.tarama import izgara
        from scryne_quant.strategy.kutuphane import EVREN_AILELER

        assert len(EVREN_CEKILISLERI) == 6
        for strateji, secenekler in EVREN_CEKILISLERI.values():
            noktalar = izgara(secenekler)
            assert len(noktalar) == 12
            for p in noktalar:
                EVREN_AILELER[strateji](**p)
            assert secenekler["hedef_brut"] == (0.2,)
            assert len(secenekler["yeniden_dengele_bar"]) == 1
