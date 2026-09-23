"""RYPP koşusunun saf hesapları (K-130): eşleme, kıyas, rejim, gecikme, girdi kurulumu.

Gerçek bağımsız veri kullanılmaz (strateji sonucu üretilmez); hepsi sentetik ve cevabı bilinen.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scryne_quant.research import risk_protokolu as rp
from scryne_quant.research import rypp_kosu as rk

SEK = ("A", "B", "C")


def test_takvim_gunu_esleme_sozlesmesi():
    """K-128/4: kripto parametreleri takvim süresi olarak taşınır."""
    assert rk.takvim_gunu(4800) == 138     # 200 gün
    assert rk.takvim_gunu(24) == 1         # günde bir kontrol
    assert rk.takvim_gunu(168) == 5        # haftalık dengeleme
    assert rk.takvim_gunu(1) == 1          # en az bir gün
    e = rk.Esleme.kripto_parametrelerinden(
        {"rejim_pencere": 4800, "kontrol_bar": 24, "yeniden_dengele_bar": 168})
    assert (e.rejim_gun, e.kontrol_gun, e.dengele_gun, e.maliyet_bps) == (138, 1, 5, 5.0)
    assert e.sozluk()["gecikme_gun"] == 2 and e.sozluk()["epizot_esigi"] == 0.10


def test_sektor_kiyasi_elle_hesapla_esit():
    r = np.array([[0.01, 0.02, -0.01], [0.00, 0.01, 0.02], [0.03, -0.02, 0.00]])
    out = rk.sektor_kiyasi(r, dengele_gun=2, maliyet_orani=0.001)
    # gün 0: eşit kuruluş (devir 1,0)
    assert out[0] == pytest.approx(np.mean(r[0]) - 0.001)
    # gün 1: kaymış ağırlıklar, dengeleme yok
    w = (1 + r[0]) / 3
    w = w / w.sum()
    assert out[1] == pytest.approx(w @ r[1])
    # gün 2: dengeleme, devir = |eşit − kaymış|
    w2 = w * (1 + r[1])
    w2 = w2 / w2.sum()
    assert out[2] == pytest.approx(np.mean(r[2]) - np.abs(1 / 3 - w2).sum() * 0.001)


def test_piyasa_rejimi_isinmadan_kapali_ve_kontrol_araliginda_sabit():
    m = np.concatenate([np.full(10, 0.01), np.full(10, -0.02)])
    g = rk.piyasa_rejimi(m, rejim_gun=5, kontrol_gun=1)
    assert not g[:4].any()           # ortalama ısınmadı
    assert g[5:10].all()             # yükselişte açık
    assert not g[-3:].any()          # düşüşte kapalı
    g3 = rk.piyasa_rejimi(m, rejim_gun=5, kontrol_gun=3)
    for i in range(len(g3)):
        assert g3[i] == g3[i - i % 3]  # karar yalnız kontrol günlerinde değişir


def test_rejim_gelecegi_gormez():
    rng = np.random.default_rng(1)
    m = rng.normal(0, 0.01, 300)
    b = m.copy()
    b[151:] = rng.normal(0, 0.05, 149)
    assert np.array_equal(rk.piyasa_rejimi(m, 20, 1)[:151], rk.piyasa_rejimi(b, 20, 1)[:151])


def test_gecikme_ve_zamanlanmis_getiri():
    g = np.array([1.0, 1.0, 0.0, 1.0])
    assert rk.gecikmeli(g, 2).tolist() == [0.0, 0.0, 1.0, 1.0]
    r = np.array([0.01, 0.02, 0.03, 0.04])
    s = rk.zamanlanmis_getiri(r, np.array([0.0, 1.0, 1.0, 0.0]), 0.001)
    assert s.tolist() == pytest.approx([0.0, 0.02 - 0.001, 0.03, -0.001])
    # hep açıkken kıyasın kendisi (ilk kuruluş devri hariç)
    assert rk.zamanlanmis_getiri(r, np.ones(4), 0.0).tolist() == pytest.approx(r.tolist())


def _cerceve(n: int = 1400, tohum: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(tohum)
    rejim = (np.arange(n) // 150) % 3 != 2  # 2 boğa, 1 ayı
    piyasa = np.where(rejim, rng.normal(0.0008, 0.008, n), rng.normal(-0.002, 0.018, n))
    df = pd.DataFrame({s: piyasa + rng.normal(0, 0.004, n) for s in SEK})
    df["Mkt-RF"], df["RF"] = piyasa, 0.0
    df.insert(0, "tarih", 20040601 + np.arange(n))
    return df


def test_bagimsiz_girdi_uctan_uca_ve_k_programi_tasir():
    e = rk.Esleme(rejim_gun=40, kontrol_gun=1, dengele_gun=5)
    g, meta = rk.bagimsiz_girdi(_cerceve(), e, aile_sayisi=1, aile_program="p_test",
                                sektorler=SEK)
    assert g.yil_bar == 252.0 and g.epizot_esigi == 0.10
    assert g.aile_sayisi == 1 and g.aile_program == "p_test"
    assert len(g.strateji) == len(g.kiyas) == len(g.strateji_2x_maliyet)
    assert meta["gun"] == 1400 - 42 and 0 < meta["risk_acik_orani"] < 1
    s = rp.degerlendir(g)
    assert s.aile == {"sayi": 1, "program": "p_test", "persentil": 0.95}
    assert s.durum in (rp.Durum.PASS, rp.Durum.FAIL, rp.Durum.INCONCLUSIVE)
    # 2x maliyet stratejiyi hiçbir zaman iyileştirmez
    assert g.strateji_2x_maliyet[-1] <= g.strateji[-1]


def test_bagimsiz_girdi_deterministik():
    e = rk.Esleme(rejim_gun=40, kontrol_gun=1, dengele_gun=5)
    a, _ = rk.bagimsiz_girdi(_cerceve(), e, aile_sayisi=1, aile_program="p", sektorler=SEK)
    b, _ = rk.bagimsiz_girdi(_cerceve(), e, aile_sayisi=1, aile_program="p", sektorler=SEK)
    assert rp.degerlendir(a).sozluk() == rp.degerlendir(b).sozluk()


def _sonuc(oz, maruz, zaman, islem=10):
    return SimpleNamespace(ozkaynak=np.asarray(oz, float), maruziyet=np.asarray(maruz, float),
                           zamanlar=np.asarray(zaman),
                           metrikler=SimpleNamespace(islem_sayisi=islem))


def test_kripto_girdi_zamanlama_takvimini_maruziyetten_cikarir():
    n = 3000
    rng = np.random.default_rng(4)
    r = rng.normal(0.0002, 0.01, n)
    oz_k = 10_000 * np.concatenate([[1.0], np.cumprod(1 + r)])
    g = (np.arange(n + 1) // 200) % 2 == 0
    oz_s = 10_000 * np.concatenate([[1.0], np.cumprod(1 + np.where(g[1:], r, 0.0))])
    maruz = np.where(g, 0.98, 0.0)  # motor maruziyeti KESİR olarak verir (K-131)
    z = np.arange(n + 1)
    girdi, meta = rk.kripto_girdi(_sonuc(oz_s, maruz, z), _sonuc(oz_k, oz_k, z),
                                  _sonuc(oz_s * 0.999, maruz, z), maliyet_orani=0.0,
                                  aile_sayisi=1, aile_program="p")
    assert meta["risk_acik_orani"] == pytest.approx(g[1:].mean())
    assert meta["dogrusal_model_mar"] == pytest.approx(meta["motor_mar"], rel=1e-9)
    assert girdi.epizot_esigi == 0.20 and girdi.yil_bar == 24 * 365.25
    with pytest.raises(rp.ProtokolHatasi):
        rk.kripto_girdi(_sonuc(oz_s, maruz, z), _sonuc(oz_k, oz_k, z + 1),
                        _sonuc(oz_s, maruz, z), maliyet_orani=0.0, aile_sayisi=1,
                        aile_program="p")


def test_kripto_girdi_birim_ve_bos_takvim_bekcisi():
    """K-131: maruziyet kesir değilse ya da işlem varken takvim boşsa hata (sessiz P3 yok)."""
    n = 50
    z = np.arange(n + 1)
    oz = 10_000 * np.ones(n + 1)
    with pytest.raises(rp.ProtokolHatasi, match="kesir"):
        rk.kripto_girdi(_sonuc(oz, oz, z), _sonuc(oz, oz, z), _sonuc(oz, oz, z),
                        maliyet_orani=0.0, aile_sayisi=1, aile_program="p")
    with pytest.raises(rp.ProtokolHatasi, match="hep kapalı"):
        rk.kripto_girdi(_sonuc(oz, np.zeros(n + 1), z), _sonuc(oz, oz / oz, z),
                        _sonuc(oz, np.zeros(n + 1), z), maliyet_orani=0.0, aile_sayisi=1,
                        aile_program="p")

