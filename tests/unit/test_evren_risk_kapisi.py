"""Evren risk kapısı (K-130): risk açıkken kıyasın kendisi, kapalıyken nakit; geleceği görmez.

Ölçülenler:

1. Rejim hep açıkken işlemler ve özkaynak kıyasla **aynı** (tek fark zamanlama olmalı).
2. Rejim hep kapalıyken (ya da rejim sembolü yokken) hiç pozisyon açılmaz.
3. Rejim kapandığında bütün pozisyonlar bir kontrol periyodu içinde kapanır, kapalıyken yeni
   pozisyon açılmaz; yeniden açılınca hemen dengelenir.
4. `t` sonrası veri bozulunca `t`ye kadarki kararlar aynı (negatif kontrollü).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.evren_kosu import EvrenVerisi
from scryne_quant.strategy.kutuphane.evren_esit_agirlik import EvrenEsitAgirlik
from scryne_quant.strategy.kutuphane.evren_risk_kapisi import EvrenRiskKapisi
from tests.conftest import bar_uret

MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
SEMBOLLER = ("AAAUSDT", "BBBUSDT", "BTCUSDT", "CCCUSDT")
N = 1_600
BAS = 722
PENCERE = 50


def _btc(egri: np.ndarray) -> dict[str, np.ndarray]:
    d = {a: np.array(x, copy=True) for a, x in bar_dizileri(bar_uret(n=N, tohum=77)).items()}
    acilis = np.concatenate([[egri[0]], egri[:-1]])
    d["open"], d["close"] = acilis, egri
    d["high"], d["low"] = np.maximum(acilis, egri) * 1.001, np.minimum(acilis, egri) * 0.999
    return d


def _veri(btc_egri: np.ndarray | None, *, btc_var: bool = True) -> EvrenVerisi:
    diziler = {}
    for i, s in enumerate(SEMBOLLER):
        if s == "BTCUSDT" and not btc_var:
            continue
        if s == "BTCUSDT" and btc_egri is not None:
            diziler[s] = _btc(btc_egri)
            continue
        diziler[s] = {a: np.array(x, copy=True)
                      for a, x in bar_dizileri(bar_uret(n=N, tohum=51 + i)).items()}
    ilk = next(iter(diziler))
    return EvrenVerisi(
        timeframe="1h", zamanlar=diziler[ilk]["open_time"], diziler=diziler,
        uyelik={s: np.ones(N, dtype=bool) for s in diziler},
        veri_sha256={s: "0" * 64 for s in diziler}, meta={}, olcum_baslangici=BAS,
        kural_kimligi="test",
    )


def _pencere() -> Pencere:
    return Pencere("p", baslangic=BAS, bitis=N, isinma_baslangic=0)


def _kapi(**deg) -> EvrenRiskKapisi:
    return EvrenRiskKapisi(**({"rejim_pencere": PENCERE, "azami_enstruman": 3} | deg))


def _kiyas() -> EvrenEsitAgirlik:
    return EvrenEsitAgirlik(yeniden_dengele_bar=168, azami_enstruman=3, azami_agirlik=1.0 / 3,
                            hedef_brut=1.0)


YUKSELEN = 30_000.0 * np.exp(np.linspace(0.0, 1.0, N))
DUSEN = 30_000.0 * np.exp(np.linspace(0.0, -1.0, N))


def test_rejim_hep_acikken_kiyasla_ayni():
    veri = _veri(YUKSELEN)
    s = ed.kosu(_kapi(), MALIYET, veri, _pencere())
    k = ed.kosu(_kiyas(), MALIYET, veri, _pencere())
    assert s.metrikler.islem_sayisi == k.metrikler.islem_sayisi > 0
    np.testing.assert_array_equal(s.ozkaynak, k.ozkaynak)


@pytest.mark.parametrize("veri_kur", [lambda: _veri(DUSEN), lambda: _veri(None, btc_var=False)])
def test_rejim_kapali_ya_da_bilinmiyorsa_hic_pozisyon_yok(veri_kur):
    s = ed.kosu(_kapi(), MALIYET, veri_kur(), _pencere())
    assert s.metrikler.islem_sayisi == 0


def test_rejim_kapaninca_cikis_kapaliyken_giris_yok_acilinca_hemen_giris():
    kapan, acil = 1_000, 1_300
    egri = np.concatenate([
        30_000.0 * np.exp(np.linspace(0.0, 0.5, kapan)),
        30_000.0 * np.exp(0.5) * np.exp(np.linspace(0.0, -0.6, acil - kapan)),
        30_000.0 * np.exp(-0.1) * np.exp(np.linspace(0.0, 1.0, N - acil)),
    ])
    veri = _veri(egri)
    st = _kapi()
    s = ed.kosu(st, MALIYET, veri, _pencere())
    saat = 3_600_000
    t0 = int(veri.zamanlar[0])
    kapanis_sinir = t0 + (kapan + 24 + 2) * saat
    # rejim kapandıktan sonra açılan her işlem, rejim yeniden açıldıktan sonra açılmış olmalı
    kapali_bas = t0 + (kapan + 1) * saat
    acilma_sinir = t0 + (acil + PENCERE) * saat
    for i in s.islemler:
        assert not (kapali_bas + 24 * saat < i.acilis_ms < t0 + acil * saat), i
    oncekiler = [i for i in s.islemler if i.acilis_ms < kapali_bas]
    assert oncekiler and all(i.kapanis_ms is not None and i.kapanis_ms <= kapanis_sinir
                             for i in oncekiler)
    assert any(t0 + acil * saat < i.acilis_ms <= acilma_sinir for i in s.islemler)
    assert st.gecis >= 2


def test_gelecek_bozulunca_t_kadarki_kararlar_ayni():
    t = 1_100
    rng = np.random.default_rng(3)
    temel = 30_000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, N)))
    bozuk = temel.copy()
    bozuk[t + 1:] = 30_000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.05, N - t - 1)))

    def kararlar(egri, son):
        st = _kapi(kontrol_bar=6)
        v = _veri(egri)
        g = ed.gorunum(v, st, _pencere())
        st.hazirla()
        out = []
        for i in range(son + 1):
            h = st.on_bar(g.baglam(i, {}, 1.0, st.parametreler))
            if h is not None:
                out.append(json.dumps(h.model_dump(), sort_keys=True))
        return out

    assert kararlar(temel, t) == kararlar(bozuk, t)
    assert kararlar(temel, N - 1) != kararlar(bozuk, N - 1)


def test_parametre_dogrulama():
    with pytest.raises(ValueError):
        EvrenRiskKapisi(kontrol_bar=0)
    with pytest.raises(ValueError):
        EvrenRiskKapisi(rejim_pencere=1)
    p = EvrenRiskKapisi().parametreler
    assert (p["rejim_sembol"], p["rejim_pencere"], p["kontrol_bar"]) == ("BTCUSDT", 4800, 24)
    assert (p["azami_enstruman"], p["yeniden_dengele_bar"], p["hedef_brut"]) == (10, 168, 1.0)
