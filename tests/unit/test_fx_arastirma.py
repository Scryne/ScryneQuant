"""R5 (K-102): araştırma hattı FX evreninde gerçekten koşuyor mu?

Kanıt: (1) `evren_degerlendirme.kosu` FX verisinde çift başına maliyet, finansman ve seanslı
takvimi **veriden** çözüp motora veriyor — kayıtta `maliyetler`/`finansmanlar`/`takvim` blokları,
spread ve finansman bileşenleri sıfırdan büyük, `gecici_finansman_modeli` engeli duruyor;
(2) aynı çağrı kripto verisinde eski yolla bit-aynı (`test_coklu_referans` + burada seri/ayar
kıyası); (3) stres çarpanı çok modelli evrende her çiftin modelini bozuyor; (4) `pencereler`
ısınma tabanını uyguluyor ve sığmayan walk-forward'ı boş katmanla ("ölçülemedi") döndürüyor;
(5) `zaman_serisi_trend` yalnız `roc > 0` üyeleri taşıyor, yükselen yoksa nakde dönüyor;
(6) `fx_fiyat` çekilişleri 12 noktalı ve kurulabilir, kayıt ile koşu aynı kimliği görüyor;
(7) `degerlendir` FX fixture'ında 11 kapıyı üretiyor (walk-forward ve rejim ölçülemedi).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.data.takvim import TAKVIM_FX_5X24
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research import evren_kosu
from scryne_quant.research import hipotez as hipotez_mod
from scryne_quant.research.analiz import STRES_SENARYOLARI
from scryne_quant.research.izgaralar import (
    FX_CEKILISLERI,
    PROGRAM_CEKILISLERI,
    cekilis_programi,
    evren_cekilisi,
)
from scryne_quant.research.tarama import izgara
from scryne_quant.strategy.kutuphane import EVREN_AILELER
from scryne_quant.strategy.kutuphane.kesitsel import KesitselGuc
from scryne_quant.strategy.kutuphane.zaman_serisi import ZamanSerisiTrend

KOK = Path(__file__).resolve().parents[2]
FIXTURE = KOK / "tests" / "fixtures" / "fx"
TABLO = FIXTURE / "_evren" / "27f528fa4aec.parquet"
MALIYET = maliyet_mod.yukle()
CIFTLER = ("EURUSD", "GBPUSD", "USDJPY")
#: Fixture kısa (EURUSD 7 hafta); ızgara küçük, ısınma verinin içinden (K-100: depo geriye gitmez).
IZGARA = {"pencere": (24, 48), "azami_enstruman": (1, 2), "yeniden_dengele_bar": (120,),
          "hedef_brut": (0.2,)}
ISINMA = 48 + 2


@pytest.fixture(scope="module")
def veri() -> evren_kosu.EvrenVerisi:
    return evren_kosu.fx_veri_kur(TABLO, depo_kok=FIXTURE, isinma_bar=ISINMA)


# ------------------------------------------------------------------ motor ayarları


class TestMotorAyarlari:
    def test_fx_verisinden_cozuluyor(self, veri):
        ayar = ed.motor_ayarlari(veri)
        assert ayar.coklu_model
        assert {s: em.kimlik for s, em in ayar.maliyetler.items()} == {
            c: f"fxcm-{c.lower()}" for c in CIFTLER
        }
        assert {s: sf.kimlik for s, sf in ayar.finansmanlar.items()} == {
            c: f"fxcm-{c.lower()}" for c in CIFTLER
        }
        assert ayar.takvim is not None and ayar.takvim.kimlik == TAKVIM_FX_5X24
        assert not ayar.takvim.surekli

    def test_kosu_motor_hattindan_geciyor(self, veri):
        """Spread, slippage, komisyon, finansman: hepsi motorun kendi kaydında, sıfır değil."""
        ins, oos, tam, _ = ed.pencereler(veri, isinma_bar=ISINMA)
        sonuc = ed.kosu(KesitselGuc(pencere=24, azami_enstruman=2, yeniden_dengele_bar=120),
                        MALIYET, veri, tam)
        m = sonuc.metrikler
        assert m.islem_sayisi > 0
        assert m.toplam_spread is not None and m.toplam_spread > 0
        assert m.toplam_finansman is not None and m.toplam_finansman > 0
        assert m.toplam_slippage > 0 and m.toplam_komisyon > 0
        assert "gecici_finansman_modeli" in sonuc.promotion_engelleri
        k = sonuc.sozluk()["config"]
        assert k["maliyetler"]["EURUSD"]["id"] == "fxcm-eurusd"
        assert set(k["finansmanlar"]) == set(CIFTLER)
        assert sonuc.takvim is not None and sonuc.takvim["id"] == TAKVIM_FX_5X24

    def test_stres_carpani_her_ciftin_modelini_bozuyor(self, veri):
        """`fee`/`slippage` çarpanı 1 olan senaryo temel koşuyla aynı, büyük olan daha pahalı."""
        _, _, tam, _ = ed.pencereler(veri, isinma_bar=ISINMA)
        def uret():
            return KesitselGuc(pencere=24, azami_enstruman=2, yeniden_dengele_bar=120)
        temel = ed.kosu(uret(), MALIYET, veri, tam).metrikler
        st = ed.stres(uret, MALIYET, veri, tam)
        assert set(st.senaryolar) == set(STRES_SENARYOLARI)
        for ad, s in st.senaryolar.items():
            c = STRES_SENARYOLARI[ad]
            beklenen = temel.toplam_komisyon * c["fee"] + temel.toplam_slippage * c["slippage"]
            # Aynı işlemler: bileşenler çarpanla ölçeklenir. Slippage fill fiyatını, fiyat da
            # komisyonun notional'ını oynatır (bps mertebesi) — tolerans o kadar, daha fazla değil.
            if s["islem_sayisi"] == temel.islem_sayisi:
                assert s["toplam_maliyet"] == pytest.approx(beklenen, rel=2e-3)

    def test_kripto_verisinde_ayar_yok(self):
        """Kripto `EvrenVerisi` → üç ayar da `None`: eski yol, bit-aynı (test_coklu_referans)."""
        from tests.unit.test_evren_degerlendirme import _veri as kripto_veri

        ayar = ed.motor_ayarlari(kripto_veri())
        assert ayar.maliyetler is None and ayar.finansmanlar is None and ayar.takvim is None
        assert not ayar.coklu_model


# ------------------------------------------------------------------ pencereler


class TestPencereler:
    def test_isinma_tabani_ve_sigmayan_walk_forward(self, veri):
        assert veri.olcum_baslangici == 0  # depo pencere başından geriye gitmiyor
        ins, oos, tam, katmanlar = ed.pencereler(veri, isinma_bar=ISINMA)
        assert ins.baslangic == ISINMA and tam.baslangic == ISINMA
        assert oos.isinma_baslangic == oos.baslangic - ISINMA
        assert katmanlar == []  # 8.766 + 2.190 bar fixture'a sığmaz → ölçülemedi

    def test_isinma_tabani_mevcut_isinmayi_kucultmez(self, veri):
        ins, *_ = ed.pencereler(veri, isinma_bar=0)
        assert ins.baslangic == veri.olcum_baslangici

    def test_sigan_walk_forward_degismedi(self, veri):
        _, _, _, katmanlar = ed.pencereler(veri, egitim_bar=300, test_bar=100, isinma_bar=ISINMA)
        assert len(katmanlar) >= 1


# ------------------------------------------------------------------ zaman serisi trend


class TestZamanSerisiTrend:
    def test_kayitli_ve_kesitsel_iskelet(self):
        assert EVREN_AILELER["zaman_serisi_trend"] is ZamanSerisiTrend
        s = ZamanSerisiTrend(pencere=24, azami_enstruman=3, yeniden_dengele_bar=120)
        assert [o.ad for o in s.ozellikler()] == ["atr", "skor_ham"]
        assert s.isinma_bar() == 24 + 2

    def test_yalniz_yukselen_tasinir(self, veri):
        """Her dengeleme anında alınan sembolün `roc(pencere) > 0` olması zorunlu."""
        from scryne_quant.strategy.kosu import evren_gorunum_kur

        s = ZamanSerisiTrend(pencere=24, azami_enstruman=3, yeniden_dengele_bar=120)
        _, _, tam, _ = ed.pencereler(veri, isinma_bar=ISINMA)
        sonuc = ed.kosu(s, MALIYET, veri, tam)
        assert sonuc.metrikler.islem_sayisi > 0
        g = evren_gorunum_kur(veri.timeframe, veri.diziler, veri.uyelik, s,
                              kural_kimligi=veri.kural_kimligi)
        for islem in sonuc.islemler:
            i = int(np.searchsorted(g.zamanlar, islem.acilis_ms))
            # Fill sinyal barının **sonraki** açılışında (K-004): karar barı i-1.
            roc = g.gorunumler[islem.sembol].ozellikler["skor_ham"][i - 1]
            assert roc > 0.0, (islem.sembol, islem.acilis_ms, roc)

    def test_yukselen_yoksa_nakit(self):
        """Tüm evren düşerken aday yok: yeni giriş yok, işlem sıfır."""
        from scryne_quant.backtest.coklu_motor import CokluBacktest
        from scryne_quant.features.barlar import bar_dizileri
        from scryne_quant.strategy.kosu import evren_gorunum_kur
        from tests.conftest import bar_uret

        n = 400
        diziler = {}
        for i, sembol in enumerate(("AAAUSDT", "BBBUSDT")):
            ham = bar_dizileri(bar_uret(n=n, tohum=7 + i))
            d = {a: np.array(x, copy=True) for a, x in ham.items()}
            # Fiyat tekdüze düşüyor: her `roc` negatif.
            egim = 1.0 - 0.001 * (i + 1) * np.arange(n)
            for alan in ("open", "high", "low", "close"):
                kayma = {"high": 0.0005, "low": -0.0005}.get(alan, 0.0)
                d[alan] = 100.0 * egim * (1.0 + kayma)
            diziler[sembol] = d
        uyelik = {s: np.ones(n, dtype=bool) for s in diziler}
        s = ZamanSerisiTrend(pencere=24, azami_enstruman=2, yeniden_dengele_bar=48)
        g = evren_gorunum_kur("1h", diziler, uyelik, s, kural_kimligi="test")
        sonuc = CokluBacktest(s, MALIYET).calistir(g, veri_sha256={}, olcum_baslangici=0)
        assert sonuc.metrikler.islem_sayisi == 0


# ------------------------------------------------------------------ çekilişler


class TestFxCekilisleri:
    def test_uc_cekilis_on_iki_noktali_kurulabilir(self):
        assert tuple(FX_CEKILISLERI) == (
            "fx_kesitsel_guc", "fx_kesitsel_ters", "fx_zaman_serisi_trend"
        )
        assert PROGRAM_CEKILISLERI["fx_fiyat"] == tuple(FX_CEKILISLERI)
        for ad in FX_CEKILISLERI:
            assert cekilis_programi(ad) == "fx_fiyat"
            strateji, g = evren_cekilisi(ad)
            noktalar = list(izgara(g))
            assert len(noktalar) == 12
            assert g["yeniden_dengele_bar"] == (120,) and g["hedef_brut"] == (0.2,)
            assert max(g["pencere"]) == 240  # ısınma 242 bar; K-101 penceresinin %14'ü
            for p in noktalar:
                EVREN_AILELER[strateji](**p)  # kurucu `dogrula()` çağırır

    def test_kayit_ve_kosu_ayni_kimlik(self, veri, tmp_path):
        hip = ed.hipotez_kur("fx_kesitsel_guc", veri, program="fx_fiyat",
                             gerekce="test: kayıt ile koşu aynı kimliği görmeli (K-039)",
                             portfoy=ed.KESITSEL_PORTFOY)
        defter = hipotez_mod.HipotezDefteri(tmp_path / "defter.jsonl")
        assert defter.kaydet(hip) == 1
        tekrar = ed.hipotez_kur("fx_kesitsel_guc", veri, program="fx_fiyat",
                                gerekce="başka kelimelerle aynı soru", portfoy=ed.KESITSEL_PORTFOY)
        assert defter.sira(tekrar) == 1
        assert hip.evren == veri.kural_kimligi and hip.timeframe == "1h"


# ------------------------------------------------------------------ tam değerlendirme


class TestTamDegerlendirmeFx:
    def test_on_bir_kapi_fx_fixture(self, veri):
        sonuc = ed.degerlendir(
            KesitselGuc, IZGARA, MALIYET, veri, secim="plato", asgari_islem=1,
            rejim_kiyasi="EURUSD", isinma_bar=ISINMA,
        )
        kapilar = sonuc["kapilar"]["kapilar"]
        assert len(kapilar) == 11
        assert sonuc["motor"]["coklu_model"] is True
        assert sonuc["motor"]["takvim"]["id"] == TAKVIM_FX_5X24
        assert sonuc["motor"]["rejim_kiyasi"] == "EURUSD"
        assert sonuc["pencereler"]["walk_forward"]["katman"] == 0
        assert "olculemedi" in sonuc["detay"]["walk_forward"]
        assert kapilar["wf_katman_basari"]["gecti"] is None  # ölçülemeyen kapı geçilmez
        assert "gecici_finansman_modeli" in sonuc["kapilar"]["mutlak_engeller"]
        assert sonuc["kapilar"]["gecti"] is False
        oos = sonuc["detay"]["oos"]["metrikler"]
        assert oos["toplam_spread"] > 0 and oos["toplam_finansman"] > 0
        json.dumps(sonuc, default=str)

    def test_rejim_kiyasi_evrende_olmali(self, veri):
        with pytest.raises(ed.EvrenDegerlendirmeHatasi):
            ed.degerlendir(KesitselGuc, IZGARA, MALIYET, veri, isinma_bar=ISINMA)  # BTCUSDT yok


# ----------------------------------------------------------- K-103: alt evren, haftalık kesim


class TestAltEvrenVeHaftalikKesim:
    def test_semboller_alt_kume_meta_ve_hata(self):
        v = evren_kosu.fx_veri_kur(TABLO, depo_kok=FIXTURE, semboller=["EURUSD", "GBPUSD"])
        assert sorted(v.diziler) == ["EURUSD", "GBPUSD"]
        assert v.meta["alt_evren"] == ["EURUSD", "GBPUSD"]
        ayar = ed.motor_ayarlari(v)
        assert ayar.coklu_model and set(ayar.finansmanlar) == {"EURUSD", "GBPUSD"}
        tam = evren_kosu.fx_veri_kur(TABLO, depo_kok=FIXTURE, semboller=list(CIFTLER))
        assert "alt_evren" not in tam.meta  # tam küme alt evren değil
        with pytest.raises(evren_kosu.EvrenKosuHatasi):
            evren_kosu.fx_veri_kur(TABLO, depo_kok=FIXTURE, semboller=["EURUSD", "YOKUSD"])

    def test_bitis_pazar_son_haftayi_keser(self, veri):
        # Fixture EURUSD 2024-2..2024-8 haftaları; Pazar 2024-01-21 ile kes: 3 hafta kalır.
        kesik = evren_kosu.fx_veri_kur(TABLO, depo_kok=FIXTURE, bitis_pazar="2024-01-21")
        ust = int(np.datetime64("2024-01-28", "D").astype("datetime64[ms]").astype("int64"))
        assert int(kesik.zamanlar[-1]) < ust <= int(veri.zamanlar[-1])
        assert kesik.meta["pencere"]["bitis_pazar"] == "2024-01-21"
        assert len(kesik) < len(veri)
