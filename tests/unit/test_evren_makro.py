"""Makro stres engeli: PIT vintage okuma, bara yayma ve engelleyici strateji. (Faz 12)

Ölçülenler:

1. Revize edilen seride `d` gününde görülen değer o gün geçerli vintage'ınki; ilk yayından
   önce değer yok.
2. `d` gününün değeri `d` günündeki hiçbir bara görünmez, `d+1` 00:00 barından itibaren
   görünür.
3. Makro bilgisi yokken strateji kıyasla **bit düzeyinde** aynı.
4. Stres rejiminde yeni pozisyon açılmaz; çıkışlar engellenmez.
5. `t` sonrası makro bozulunca `t`ye kadarki kararlar aynı (negatif kontrollü).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.data import makro as makro_mod
from scryne_quant.features.barlar import EK_SAYISAL, bar_dizileri
from scryne_quant.features.motor import DEFTER
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.evren_kosu import EvrenVerisi
from scryne_quant.research.izgaralar import MAKRO_CEKILISLERI, cekilis_programi
from scryne_quant.research.tarama import izgara
from scryne_quant.strategy.kutuphane import (
    EVREN_AILELER,
    EvrenEsitAgirlik,
    EvrenMakroVix,
    evren_makro,
)
from tests.conftest import bar_uret

GUN = makro_mod.GUN_MS
MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)


def _gun(tarih: str) -> int:
    return int((pd.Timestamp(tarih) - pd.Timestamp("1970-01-01")) // pd.Timedelta(days=1))


class TestPitGunluk:
    def test_revizyon_o_gun_gecerli_vintage(self):
        df = pd.DataFrame({
            "date": ["2024-03-01", "2024-03-01", "2024-03-08"],
            "realtime_start": ["2024-03-06", "2024-03-13", "2024-03-13"],
            "realtime_end": ["2024-03-12", "9999-12-31", "9999-12-31"],
            "value": [-0.46, -0.49, -0.40],
        })
        gunler = np.array([_gun(d) for d in ("2024-03-05", "2024-03-06", "2024-03-12",
                                             "2024-03-13")])
        out = makro_mod.pit_gunluk(df, gunler)
        assert np.isnan(out[0])                       # ilk yayından önce
        assert out[1] == pytest.approx(-0.46)         # ilk vintage
        assert out[2] == pytest.approx(-0.46)         # revizyon henüz yok
        assert out[3] == pytest.approx(-0.40)         # yeni gözlem en geç tarihli

    def test_bos_deger_uydurulmaz(self):
        df = pd.DataFrame({"date": ["2024-01-02"], "realtime_start": ["2024-01-02"],
                           "realtime_end": ["9999-12-31"], "value": [np.nan]})
        assert np.isnan(makro_mod.pit_gunluk(df, np.array([_gun("2024-01-05")]))).all()


def _depo(tmp_path, degerler: dict[str, list[tuple[str, float]]]):
    for sid in makro_mod.SERILER.values():
        satir = degerler.get(sid, [])
        pd.DataFrame({
            "date": [d for d, _ in satir],
            "realtime_start": [d for d, _ in satir],
            "realtime_end": ["9999-12-31"] * len(satir),
            "value": [v for _, v in satir],
        }).to_parquet(tmp_path / f"{sid}.parquet")
    return tmp_path


class TestBarAlanlari:
    def test_deger_ertesi_gun_gorunur(self, tmp_path):
        gunler = pd.date_range("2023-01-01", periods=40, freq="D")
        # Azalan seri (persentil düşük), 31. günde sıçrama: persentil 1,0'a çıkmalı, ama
        # ancak 32. günün barlarında. (Sabit seri kullanılamaz: eşit değerlerde sıra hep 1,0.)
        seri = [(str(d.date()), 1_000.0 if i == 30 else 100.0 - i) for i, d in enumerate(gunler)]
        depo = _depo(tmp_path, {"VIXCLS": seri, "NFCI": seri})
        bas = int(pd.Timestamp("2023-01-29").value // 10**6)
        zamanlar = bas + 3_600_000 * np.arange(24 * 6)
        alanlar, _ = makro_mod.bar_alanlari(zamanlar, depo)
        p = alanlar["vix_p30"]
        gun_idx = (zamanlar // GUN) - _gun("2023-01-29")
        sicrama_gunu = _gun(str(gunler[30].date())) - _gun("2023-01-29")
        assert (p[gun_idx == sicrama_gunu] < 1.0).all()      # aynı gün görünmez
        assert (p[gun_idx == sicrama_gunu + 1] == 1.0).all()  # ertesi gün görünür
        assert set(alanlar) == set(makro_mod.butun_alanlar())

    def test_alanlar_defterde_ve_ek_sayisalda(self):
        for alan in makro_mod.butun_alanlar():
            assert alan in DEFTER and alan in EK_SAYISAL
        assert evren_makro.PENCERELER_GUN == makro_mod.PENCERELER_GUN


SEMBOLLER = ("AAAUSDT", "BBBUSDT", "BTCUSDT", "CCCUSDT")
N = 1_600


def _veri(makro: np.ndarray) -> EvrenVerisi:
    diziler = {}
    for i, s in enumerate(SEMBOLLER):
        dz = {a: np.array(x, copy=True)
              for a, x in bar_dizileri(bar_uret(n=N, tohum=51 + i)).items()}
        for alan in makro_mod.butun_alanlar():
            dz[alan] = makro
        diziler[s] = dz
    return EvrenVerisi(
        timeframe="1h", zamanlar=diziler["AAAUSDT"]["open_time"], diziler=diziler,
        uyelik={s: np.ones(N, dtype=bool) for s in SEMBOLLER},
        veri_sha256={s: "0" * 64 for s in SEMBOLLER}, meta={}, olcum_baslangici=722,
        kural_kimligi="test",
    )


def _pencere() -> Pencere:
    return Pencere("p", baslangic=722, bitis=N, isinma_baslangic=0)


class TestMakroEngel:
    def test_makro_bilgisi_yokken_kiyasla_ayni(self):
        veri = _veri(np.full(N, np.nan))
        kiyas = ed.kosu(EvrenEsitAgirlik(yeniden_dengele_bar=168, azami_enstruman=3,
                                         azami_agirlik=0.2 / 3, hedef_brut=0.2),
                        MALIYET, veri, _pencere())
        s = ed.kosu(EvrenMakroVix(pencere_gun=90, esik=0.8, azami_enstruman=3),
                    MALIYET, veri, _pencere())
        assert s.sonuc_hash == kiyas.sonuc_hash

    def test_hep_stresken_hic_pozisyon_acilmaz(self):
        veri = _veri(np.ones(N))
        s = ed.kosu(EvrenMakroVix(esik=0.8, azami_enstruman=3), MALIYET, veri, _pencere())
        assert s.metrikler.islem_sayisi == 0

    def test_stres_basladiktan_sonra_yeni_giris_yok_cikis_serbest(self):
        k = 1_100
        makro = np.zeros(N)
        makro[k:] = 1.0
        veri = _veri(makro)
        # Stres başladıktan sonra BBB evrenden çıksın: çıkış engellenmemeli.
        veri.uyelik["BBBUSDT"][k + 50:] = False
        st = EvrenMakroVix(esik=0.8, azami_enstruman=3, yeniden_dengele_bar=24)
        s = ed.kosu(st, MALIYET, veri, _pencere())
        stres_ms = int(veri.zamanlar[k])
        assert s.metrikler.islem_sayisi > 0
        assert all(i.acilis_ms <= stres_ms + 24 * 3_600_000 for i in s.islemler)
        bbb = [i for i in s.islemler if i.sembol == "BBBUSDT"]
        assert bbb and all(i.kapanis_ms is not None for i in bbb)

    def test_gelecek_makro_bozulunca_t_kadarki_kararlar_ayni(self):
        t = 1_100
        rng = np.random.default_rng(3)
        temel = rng.uniform(0.0, 1.0, N)
        bozuk = temel.copy()
        bozuk[t + 1:] = rng.uniform(0.0, 1.0, N - t - 1)

        def kararlar(v, son):
            st = EvrenMakroVix(esik=0.6, azami_enstruman=2, yeniden_dengele_bar=24)
            g = ed.gorunum(v, st, _pencere())
            st.hazirla()
            out = []
            for i in range(son + 1):
                h = st.on_bar(g.baglam(i, {}, 1.0, st.parametreler))
                if h is not None:
                    out.append(json.dumps(h.model_dump(), sort_keys=True))
            return out

        assert kararlar(_veri(temel), t) == kararlar(_veri(bozuk), t)
        assert kararlar(_veri(temel), N - 1) != kararlar(_veri(bozuk), N - 1)


class TestMakroCekilisleri:
    def test_izgaralar(self):
        assert list(MAKRO_CEKILISLERI) == ["makro_vix", "makro_nfci"]
        for ad, (strateji, secenekler) in MAKRO_CEKILISLERI.items():
            assert cekilis_programi(ad) == "makro_rejim"
            noktalar = izgara(secenekler)
            assert len(noktalar) == 12
            for p in noktalar:
                EVREN_AILELER[strateji](**p)
        with pytest.raises(ValueError):
            EvrenMakroVix(pencere_gun=60)
