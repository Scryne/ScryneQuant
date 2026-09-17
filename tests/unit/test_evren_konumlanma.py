"""Konumlanma verisi ve kıyas + konumlanma dışlaması. (Faz 16, `konumlanma_evren`)

Ölçülenler:

1. Hizalama nedensel: 5 dakikalık dilim **kapanmadan** değer görünmez (`create_time + 5 dk`);
   bayat seri `NaN`; verisi olmayan sembolde bütün diziler `NaN`.
2. Dışlama oranı 0 iken dört strateji de kıyasla **bit düzeyinde** aynı sonucu verir.
3. Dışlanan küme skoru en yüksek dilim; konumlanma verisi olmayan üye **dışlanmaz**.
4. `t` sonrası konumlanma bozulunca `t`ye kadarki kararlar değişmez (K-002).
5. Izgara/aile kayıtları program defteriyle tutarlı.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.data import konumlanma as konum_mod
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.features.motor import DEFTER
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.evren_kosu import EvrenVerisi
from scryne_quant.research.izgaralar import (
    KONUMLANMA_CEKILISLERI,
    cekilis_programi,
    evren_cekilisi,
)
from scryne_quant.research.tarama import izgara
from scryne_quant.strategy.kutuphane import (
    EVREN_AILELER,
    EvrenBuyukHesap,
    EvrenEsitAgirlik,
    EvrenOiBirikim,
    EvrenOiTaker,
    EvrenTakerBaski,
)
from scryne_quant.strategy.kutuphane.evren_funding import SKOR
from tests.conftest import bar_uret

SAAT = 3_600_000
DAKIKA = 60_000
N = 1_000
SEMBOLLER = ("AAAUSDT", "BBBUSDT", "BTCUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT")
MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)


def _konum(zamanlar_ms, oi, taker=1.0, buyuk=1.0, hesap=1.0) -> pd.DataFrame:
    n = len(zamanlar_ms)
    return pd.DataFrame({
        "create_time": np.asarray(zamanlar_ms, dtype="int64"),
        "sum_open_interest": np.asarray(oi, dtype="float64"),
        "sum_taker_long_short_vol_ratio": np.full(n, taker, dtype="float64"),
        "sum_toptrader_long_short_ratio": np.full(n, buyuk, dtype="float64"),
        "count_long_short_ratio": np.full(n, hesap, dtype="float64"),
    })


class TestHizalama:
    def test_dilim_kapanmadan_deger_gorunmez(self):
        t0 = int(bar_uret(n=1)["open_time"].iloc[0])
        z = t0 + SAAT * np.arange(6)
        # Gözlem 3. barın açılışından **tam** 5 dk önce başlıyor: o barda görünür.
        d = konum_mod.evren_dizileri(z, _konum([t0 + 3 * SAAT - 5 * DAKIKA], [100.0]))
        assert np.isnan(d["acik_pozisyon"][:3]).all()
        assert d["acik_pozisyon"][3] == 100.0
        # Bir dakika geç başlayan gözlem 3. barda **görünmez**, 4'te görünür.
        d2 = konum_mod.evren_dizileri(z, _konum([t0 + 3 * SAAT - 4 * DAKIKA], [100.0]))
        assert np.isnan(d2["acik_pozisyon"][3])
        assert d2["acik_pozisyon"][4] == 100.0

    def test_bayat_seri_nan_ve_veri_yoksa_hepsi_nan(self):
        t0 = int(bar_uret(n=1)["open_time"].iloc[0])
        z = t0 + SAAT * np.arange(48)
        d = konum_mod.evren_dizileri(z, _konum([t0], [50.0]))
        # BAYAT_MS = 24 saat: 24. bardan sonra taşınmaz.
        assert d["acik_pozisyon"][24] == 50.0
        assert np.isnan(d["acik_pozisyon"][26])
        bos = konum_mod.evren_dizileri(z, pd.DataFrame())
        assert all(np.isnan(v).all() for v in bos.values())

    def test_eksik_sutun_hata(self):
        with pytest.raises(konum_mod.KonumlanmaHatasi):
            konum_mod.evren_dizileri(np.array([0]), pd.DataFrame({"create_time": [0]}))

    def test_alanlar_ozellik_defterinde(self):
        for kayit in ("acik_pozisyon_degisimi", "taker_sma", "buyuk_hesap_sma",
                      "hesap_orani_sma"):
            assert kayit in DEFTER
            assert DEFTER[kayit].girdiler[0] in konum_mod.SUTUNLAR


def _veri(oi_egimi: dict[str, float | None] | None = None, bozuk_t: int | None = None):
    """Her sembolde düzenli artan açık pozisyon; `None` = konumlanma verisi yok."""
    egim = oi_egimi or {
        "AAAUSDT": 0.004, "BBBUSDT": 0.0005, "BTCUSDT": 0.001,
        "CCCUSDT": 0.010, "DDDUSDT": None, "EEEUSDT": 0.002,
    }
    diziler = {}
    for i, s in enumerate(SEMBOLLER):
        dz = {a: np.array(x, copy=True)
              for a, x in bar_dizileri(bar_uret(n=N, tohum=31 + i)).items()}
        z = dz["open_time"]
        if egim.get(s) is None:
            k = pd.DataFrame()
        else:
            # 5 dakikada bir gözlem; bar açılışından 5 dk önce kapanan dilimler görünür.
            zam = np.arange(z[0] - SAAT, z[-1] + SAAT, 5 * DAKIKA)
            adet = 1_000.0 * np.exp(egim[s] * np.arange(len(zam)) / 12.0)
            taker = 1.0 + egim[s] * 10.0
            if bozuk_t is not None:
                rng = np.random.default_rng(11 + i)
                gelecek = zam > z[bozuk_t]
                adet[gelecek] = rng.uniform(500.0, 5_000.0, int(gelecek.sum()))
            k = _konum(zam, adet, taker=taker, buyuk=taker, hesap=taker)
        dz.update(konum_mod.evren_dizileri(z, k))
        diziler[s] = dz
    return EvrenVerisi(
        timeframe="1h",
        zamanlar=diziler["AAAUSDT"]["open_time"],
        diziler=diziler,
        uyelik={s: np.ones(N, dtype=bool) for s in SEMBOLLER},
        veri_sha256={s: "0" * 64 for s in SEMBOLLER},
        meta={"ek_veri_sha256": {"konumlanma/AAAUSDT": "1" * 64}},
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
        for sinif in (EvrenOiBirikim, EvrenTakerBaski, EvrenBuyukHesap, EvrenOiTaker):
            s = ed.kosu(sinif(pencere=168, dislama_orani=0.0, azami_enstruman=azami,
                              yeniden_dengele_bar=168, hedef_brut=0.2),
                        MALIYET, veri, _pencere())
            assert s.sonuc_hash == kiyas.sonuc_hash, sinif.ad
            assert s.ozkaynak.tobytes() == kiyas.ozkaynak.tobytes()

    def test_en_cok_biriken_dilim_dislaniyor_verisiz_uye_kaliyor(self):
        veri = _veri()
        strateji = EvrenOiBirikim(pencere=168, dislama_orani=0.4, azami_enstruman=6)
        g = ed.gorunum(veri, strateji, _pencere())
        strateji.hazirla()
        ctx = g.baglam(900, {}, 1.0, strateji.parametreler)
        adaylar = strateji._aday_uyeler(ctx)
        # Skorlu 5 üye → ceil(0,4 × 5) = 2 dışlanır: CCC (en dik) ve AAA.
        assert set(adaylar) == {"BBBUSDT", "BTCUSDT", "DDDUSDT", "EEEUSDT"}
        assert np.isnan(g.gorunumler["DDDUSDT"].ozellikler[SKOR][900])  # verisi yok, kaldı

    def test_gelecek_konumlanma_bozulunca_t_kadarki_kararlar_ayni(self):
        t = 1_100 if N > 1_100 else N - 50
        pencere = _pencere()

        def kararlar(v, son):
            st = EvrenOiBirikim(pencere=72, dislama_orani=0.3, azami_enstruman=3,
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
        assert kararlar(_veri(), N - 1) != kararlar(_veri(bozuk_t=t), N - 1)


class TestIzgara:
    def test_cekilisler_programa_bagli_ve_izgara_kurulabiliyor(self):
        for ad, (strateji_adi, g) in KONUMLANMA_CEKILISLERI.items():
            assert cekilis_programi(ad) == "konumlanma_evren"
            assert strateji_adi in EVREN_AILELER
            assert evren_cekilisi(ad) == (strateji_adi, g)
            noktalar = izgara(g)
            assert len(noktalar) == 12  # 4 pencere × 3 dışlama oranı
            EVREN_AILELER[strateji_adi](**noktalar[0])
