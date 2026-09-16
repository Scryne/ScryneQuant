"""Evren funding'i: hizalama ve kıyas + dışlama stratejileri. (Faz 12, `turev_evren`)

Ölçülenler:

1. Hizalama nedensel: ödeme `calc_time`dan önce açılan bara görünmez; aralık normalizasyonu
   ve bayatlık kuralı; ödeme dizisinin kayan toplamı fiilen ödeneni verir.
2. Dışlama oranı 0 iken strateji kıyasla **bit düzeyinde** aynı sonucu verir.
3. Dışlanan küme skoru en yüksek dilim; funding'i olmayan üye dışlanmaz.
4. `t` sonrası funding bozulunca `t`ye kadarki kararlar aynı (K-002).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.data import funding as funding_mod
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.features.motor import DEFTER
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.evren_kosu import EvrenVerisi
from scryne_quant.research.izgaralar import TUREV_CEKILISLERI, cekilis_programi
from scryne_quant.research.tarama import izgara
from scryne_quant.strategy.kutuphane import (
    EVREN_AILELER,
    EvrenBasis,
    EvrenEsitAgirlik,
    EvrenFundingBasis,
    EvrenFundingBirikim,
    EvrenFundingKesit,
)
from scryne_quant.strategy.kutuphane.evren_funding import SKOR
from tests.conftest import bar_uret

SAAT = 3_600_000
T0 = 1_699_999_200_000
MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)


def _funding(zamanlar_ms, oranlar, aralik=8) -> pd.DataFrame:
    return pd.DataFrame({
        "calc_time": np.asarray(zamanlar_ms, dtype="int64"),
        "funding_interval_hours": np.full(len(zamanlar_ms), aralik, dtype="int64"),
        "last_funding_rate": np.asarray(oranlar, dtype="float64"),
    })


class TestHizalama:
    def test_odeme_calc_time_oncesi_bara_gorunmez(self):
        z = T0 + SAAT * np.arange(24)
        # 8. barın açılışından 2 ms sonra gerçekleşen ödeme (arşivdeki gerçek ofset gibi).
        f = _funding([T0 + 8 * SAAT + 2], [0.0004])
        d = funding_mod.evren_dizileri(z, f)
        assert np.isnan(d["funding"][: 9]).all()
        assert d["funding"][9] == pytest.approx(0.0004)
        assert d["funding_odeme"][9] == pytest.approx(0.0004)
        assert np.isnan(d["funding_odeme"][:9]).all()

    def test_esitlik_dahil(self):
        z = T0 + SAAT * np.arange(10)
        d = funding_mod.evren_dizileri(z, _funding([T0 + 3 * SAAT], [0.001]))
        assert np.isnan(d["funding"][2]) and d["funding"][3] == pytest.approx(0.001)

    def test_aralik_8_saate_normalize(self):
        z = T0 + SAAT * np.arange(6)
        d = funding_mod.evren_dizileri(z, _funding([T0], [0.0001], aralik=4))
        assert d["funding"][0] == pytest.approx(0.0002)
        assert d["funding_odeme"][0] == pytest.approx(0.0001)  # ödeme ham kalır

    def test_bayat_seri_nan(self):
        z = T0 + SAAT * np.arange(40)
        d = funding_mod.evren_dizileri(z, _funding([T0], [0.0001]))
        assert not np.isnan(d["funding"][24])  # tam 24 saat: taze
        assert np.isnan(d["funding"][25:]).all()
        assert np.isnan(d["funding_odeme"][25:]).all()

    def test_odeme_toplami_fiilen_odeneni_verir(self):
        z = T0 + SAAT * np.arange(48)
        zam = [T0 + k * 8 * SAAT for k in range(6)]
        oran = [0.0001, 0.0002, 0.0003, 0.0004, 0.0005, 0.0006]
        d = funding_mod.evren_dizileri(z, _funding(zam, oran))
        kayit = DEFTER["funding_odeme_toplami"]
        assert kayit.girdiler == ("funding_odeme",)
        t = kayit.fonksiyon(d["funding_odeme"], 24)
        # 47. barda son 24 saat (bar 24..47): 24, 32, 40. saatlerdeki ödemeler.
        assert t[47] == pytest.approx(0.0004 + 0.0005 + 0.0006)

    def test_funding_yoksa_hepsi_nan(self):
        z = T0 + SAAT * np.arange(5)
        d = funding_mod.evren_dizileri(z, pd.DataFrame())
        assert np.isnan(d["funding"]).all() and np.isnan(d["funding_odeme"]).all()


SEMBOLLER = ("AAAUSDT", "BBBUSDT", "BTCUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT")
N = 1_600


def _veri(funding_oranlari: dict[str, float] | None = None, bozuk_t: int | None = None):
    """Her sembolde sabit oranlı funding; `None` = perp yok. `bozuk_t`: sonrası rastgele."""
    oranlar = funding_oranlari or {
        "AAAUSDT": 0.0010, "BBBUSDT": 0.0001, "BTCUSDT": 0.0002,
        "CCCUSDT": 0.0030, "DDDUSDT": None, "EEEUSDT": 0.0005,
    }
    diziler = {}
    for i, s in enumerate(SEMBOLLER):
        dz = {a: np.array(x, copy=True)
              for a, x in bar_dizileri(bar_uret(n=N, tohum=31 + i)).items()}
        z = dz["open_time"]
        if oranlar.get(s) is None:
            f = pd.DataFrame()
        else:
            zam = np.arange(z[0], z[-1] + 1, 8 * SAAT)
            o = np.full(len(zam), oranlar[s])
            if bozuk_t is not None:
                rng = np.random.default_rng(7 + i)
                gelecek = zam > z[bozuk_t]
                o[gelecek] = rng.uniform(-0.003, 0.003, int(gelecek.sum()))
            f = _funding(zam, o)
        dz.update(funding_mod.evren_dizileri(z, f))
        diziler[s] = dz
    return EvrenVerisi(
        timeframe="1h",
        zamanlar=diziler["AAAUSDT"]["open_time"],
        diziler=diziler,
        uyelik={s: np.ones(N, dtype=bool) for s in SEMBOLLER},
        veri_sha256={s: "0" * 64 for s in SEMBOLLER},
        meta={"ek_veri_sha256": {"funding/AAAUSDT": "1" * 64}},
        olcum_baslangici=722,
        kural_kimligi="test",
    )


def _pencere() -> Pencere:
    return Pencere("p", baslangic=722, bitis=N, isinma_baslangic=0)


class TestKiyasUstuneDislama:
    @pytest.mark.parametrize("azami", [2, 4])
    def test_oran_sifirken_kiyasla_bit_duzeyinde_ayni(self, azami):
        veri = _veri()
        kiyas = ed.kosu(
            EvrenEsitAgirlik(yeniden_dengele_bar=168, azami_enstruman=azami,
                             azami_agirlik=0.2 / azami, hedef_brut=0.2),
            MALIYET, veri, _pencere(),
        )
        for sinif in (EvrenFundingKesit, EvrenFundingBirikim):
            s = ed.kosu(sinif(dislama_orani=0.0, azami_enstruman=azami,
                              yeniden_dengele_bar=168, hedef_brut=0.2),
                        MALIYET, veri, _pencere())
            assert s.sonuc_hash == kiyas.sonuc_hash, sinif.ad
            assert s.ozkaynak.tobytes() == kiyas.ozkaynak.tobytes()

    def test_en_yuksek_funding_dilimi_dislaniyor_funding_yok_kaliyor(self):
        veri = _veri()
        strateji = EvrenFundingKesit(dislama_orani=0.4, azami_enstruman=6)
        g = ed.gorunum(veri, strateji, _pencere())
        strateji.hazirla()
        ctx = g.baglam(900, {}, 1.0, strateji.parametreler)
        adaylar = strateji._aday_uyeler(ctx)
        # Skorlu 5 üye → ceil(0,4 × 5) = 2 dışlanır: CCC (0,003) ve AAA (0,001).
        assert set(adaylar) == {"BBBUSDT", "BTCUSDT", "DDDUSDT", "EEEUSDT"}
        assert np.isnan(g.gorunumler["DDDUSDT"].ozellikler[SKOR][900])  # perp yok, kaldı

    def test_gelecek_funding_bozulunca_t_kadarki_kararlar_ayni(self):
        t = 1_100
        pencere = _pencere()

        def kararlar(v, son):
            st = EvrenFundingBirikim(pencere=72, dislama_orani=0.3, azami_enstruman=3,
                                     yeniden_dengele_bar=24)
            g = ed.gorunum(v, st, pencere)
            st.hazirla()
            out = []
            for i in range(son + 1):
                h = st.on_bar(g.baglam(i, {}, 1.0, st.parametreler))
                if h is not None:
                    out.append(json.dumps(h.model_dump(), sort_keys=True))
            return out

        assert kararlar(_veri(), t) == kararlar(_veri(bozuk_t=t), t)
        # Negatif kontrol: funding kararları gerçekten etkiliyor; bozulma t sonrası görünür.
        assert kararlar(_veri(), N - 1) != kararlar(_veri(bozuk_t=t), N - 1)

    def test_motor_kosusu_ve_parametre_kaydi(self):
        veri = _veri()
        st = EvrenFundingBirikim(pencere=168, dislama_orani=0.2, azami_enstruman=3)
        s = CokluBacktest(st, MALIYET).calistir(
            ed.gorunum(veri, st, _pencere()), olcum_baslangici=_pencere().olcum_baslangici
        )
        assert s.metrikler.islem_sayisi > 0
        assert st.sozluk()["parametreler"]["pencere"] == 168
        assert "kiyas" not in st.sozluk()


class TestTurevCekilisleri:
    def test_izgaralar_12_noktali_ve_kurulabilir(self):
        assert list(TUREV_CEKILISLERI) == [
            "turev_funding_kesit", "turev_funding_birikim", "turev_basis", "turev_funding_basis"
        ]
        for ad, (strateji, secenekler) in TUREV_CEKILISLERI.items():
            assert cekilis_programi(ad) == "turev_evren"
            noktalar = izgara(secenekler)
            assert len(noktalar) == 12
            for p in noktalar:
                EVREN_AILELER[strateji](**p)

    def test_funding_verisi_kimlige_giriyor(self):
        a = _veri()
        b = _veri()
        b.meta["ek_veri_sha256"] = {"funding/AAAUSDT": "2" * 64}
        assert ed.veri_kimligi(a) != ed.veri_kimligi(b)
        h = ed.hipotez_kur("turev_funding_kesit", a, program="turev_evren",
                           gerekce="x" * 20, portfoy=ed.TUREV_PORTFOY)
        assert h.portfoy == "EVREN_ESIT" and h.strateji == "evren_funding_kesit"


# --------------------------------------------------------------------- basis (Faz 12)


class TestPremiumHizalama:
    def test_tam_zaman_eslesmesi_eksik_doldurulmaz(self):
        z = T0 + SAAT * np.arange(6)
        prem = pd.DataFrame({"open_time": [T0, T0 + 2 * SAAT, T0 + 9 * SAAT],
                             "close": [0.001, -0.002, 0.5]})
        b = funding_mod.evren_premium_dizisi(z, prem)
        assert b[0] == pytest.approx(0.001) and b[2] == pytest.approx(-0.002)
        assert np.isnan(b[1]) and np.isnan(b[3:]).all()  # önceki değer taşınmıyor

    def test_premium_yoksa_nan(self):
        assert np.isnan(funding_mod.evren_premium_dizisi(T0 + SAAT * np.arange(3),
                                                         pd.DataFrame())).all()


def _basisli(bozuk_t: int | None = None) -> EvrenVerisi:
    veri = _veri(bozuk_t=bozuk_t)
    sabit = {"AAAUSDT": 0.002, "BBBUSDT": 0.004, "BTCUSDT": -0.001,
             "CCCUSDT": 0.0005, "DDDUSDT": 0.003, "EEEUSDT": None}
    for i, s in enumerate(SEMBOLLER):
        z = veri.diziler[s]["open_time"]
        if sabit[s] is None:
            veri.diziler[s]["basis"] = np.full(N, np.nan)
            continue
        b = np.full(N, sabit[s])
        if bozuk_t is not None:
            b[bozuk_t + 1:] = np.random.default_rng(99 + i).uniform(-0.01, 0.01, N - bozuk_t - 1)
        veri.diziler[s]["basis"] = funding_mod.evren_premium_dizisi(
            z, pd.DataFrame({"open_time": z, "close": b})
        )
    return veri


class TestBasisCekilisleri:
    def test_oran_sifirken_kiyasla_ayni(self):
        veri = _basisli()
        kiyas = ed.kosu(EvrenEsitAgirlik(yeniden_dengele_bar=168, azami_enstruman=4,
                                         azami_agirlik=0.05, hedef_brut=0.2),
                        MALIYET, veri, _pencere())
        for sinif in (EvrenBasis, EvrenFundingBasis):
            s = ed.kosu(sinif(pencere=72, dislama_orani=0.0, azami_enstruman=4),
                        MALIYET, veri, _pencere())
            assert s.sonuc_hash == kiyas.sonuc_hash, sinif.ad

    def test_basis_en_yuksek_dilim_dislaniyor(self):
        veri = _basisli()
        st = EvrenBasis(pencere=24, dislama_orani=0.4, azami_enstruman=6)
        g = ed.gorunum(veri, st, _pencere())
        ctx = g.baglam(900, {}, 1.0, st.parametreler)
        # Basis'li 5 üye → 2 dışlanır: BBB (0,004), DDD (0,003). EEE basis'siz, kalır.
        assert set(st._aday_uyeler(ctx)) == {"AAAUSDT", "BTCUSDT", "CCCUSDT", "EEEUSDT"}

    def test_birlesik_sira_iki_skoru_esit_agirliklandirir(self):
        veri = _basisli()
        st = EvrenFundingBasis(pencere=24, dislama_orani=0.25, azami_enstruman=6)
        g = ed.gorunum(veri, st, _pencere())
        ctx = g.baglam(900, {}, 1.0, st.parametreler)
        # İki skoru da olan: AAA, BBB, BTC, CCC (DDD funding'siz, EEE basis'siz → kalır).
        # funding birikimi sırası: BBB 0, BTC 1/3, AAA 2/3, CCC 1
        # basis sırası:             BTC 0, CCC 1/3, AAA 2/3, BBB 1
        # ortalama: AAA 2/3, BBB 1/2, BTC 1/6, CCC 2/3 → ceil(0,25×4)=1; eşitlikte ad: AAA.
        assert set(st._aday_uyeler(ctx)) == {"BBBUSDT", "BTCUSDT", "CCCUSDT",
                                             "DDDUSDT", "EEEUSDT"}

    def test_sira_esitlikte_ortalama(self):
        from scryne_quant.strategy.kutuphane.evren_funding import _sira
        assert _sira([3.0, 1.0, 3.0]).tolist() == [0.75, 0.0, 0.75]
        assert _sira([5.0]).tolist() == [0.5]

    def test_gelecek_basis_bozulunca_t_kadarki_kararlar_ayni(self):
        t = 1_100

        def kararlar(v, son):
            st = EvrenFundingBasis(pencere=72, dislama_orani=0.3, azami_enstruman=3,
                                   yeniden_dengele_bar=24)
            g = ed.gorunum(v, st, _pencere())
            st.hazirla()
            out = []
            for i in range(son + 1):
                h = st.on_bar(g.baglam(i, {}, 1.0, st.parametreler))
                if h is not None:
                    out.append(json.dumps(h.model_dump(), sort_keys=True))
            return out

        assert kararlar(_basisli(), t) == kararlar(_basisli(bozuk_t=t), t)
        assert kararlar(_basisli(), N - 1) != kararlar(_basisli(bozuk_t=t), N - 1)

    def test_izgaralar_funding_birikimin_aynasi(self):
        assert TUREV_CEKILISLERI["turev_basis"][1] == TUREV_CEKILISLERI["turev_funding_birikim"][1]
        assert TUREV_CEKILISLERI["turev_funding_basis"][1] == TUREV_CEKILISLERI[
            "turev_funding_birikim"][1]
        for ad in ("turev_basis", "turev_funding_basis"):
            assert cekilis_programi(ad) == "turev_evren"
