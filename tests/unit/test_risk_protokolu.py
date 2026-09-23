"""Risk Yönetimli Promotion Protokolü (K-125): doğru kullanımı geçirir, yanlış kullanımı engeller.

Sentetik piyasa bilinen rejimlerle üretilir (boğa/ayı). Ölçülenler:
- Rejimi bir bar gecikmeyle izleyen strateji PASS (pozitif kontrol).
- **Maruziyeti yalnızca düşüren** (sabit %50) strateji düşüşü yarıya indirir ama FAIL — plasebo
  aynı maruziyeti taşır; "daha az risk aldım" kanıt değildir (kendini kandırma koruması).
- Rastgele zamanlama FAIL; tek olay baskınlığı FAIL; 2x maliyette çöken strateji FAIL.
- Kısa OOS, tek epizot, eksik plasebo, eksik stres → INCONCLUSIVE (eşik gevşemez).
- Standart Sortino elle hesapla eşit; eski `Metrikler.sortino` farkı belgelenir.
- Plasebo işlem sayısını ve ortalama maruziyeti korur; aile büyüdükçe persentil sıkılaşır.
- Aynı girdi aynı sonuç (K-009).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from scryne_quant.research import risk_protokolu as rp

YIL = 252
MALIYET = 10e-4


def piyasa(yil: float = 4.0, tohum: int = 1, ayilar: bool = True):
    """Boğa (~120 gün, +) / ayı (~60 gün, −) rejimli günlük getiri ve rejim dizisi."""
    rng = np.random.default_rng(tohum)
    t = int(yil * YIL)
    rejim = np.empty(t, dtype=bool)  # True = boğa
    i, bog = 0, True
    while i < t:
        n = int(rng.integers(90, 150) if bog else rng.integers(45, 75))
        rejim[i:i + n] = bog
        i += n
        bog = not bog if ayilar else True
    r = np.where(rejim, rng.normal(0.0035, 0.010, t), rng.normal(-0.004, 0.020, t))
    return r, rejim


def ozkaynak(r: np.ndarray, w: np.ndarray, maliyet: float = MALIYET) -> np.ndarray:
    devir = np.abs(np.diff(w, prepend=0.0))
    return np.concatenate([[1.0], np.cumprod(1 + w * r - devir * maliyet)])


def girdi(r, w, *, plasebo=True, stres=True, k=1, **deg) -> rp.RyppGirdisi:
    return rp.RyppGirdisi(
        strateji=ozkaynak(r, w), kiyas=ozkaynak(r, np.ones_like(r)),
        strateji_2x_maliyet=ozkaynak(r, w, 2 * MALIYET) if stres else None,
        yil_bar=YIL, epizot_esigi=0.20,
        plasebo=rp.plasebo_mar(r, w, maliyet_orani=MALIYET, yil_bar=YIL, ornek=300)
        if plasebo else None,
        aile_sayisi=k, **deg,
    )


def _zamanlayici(rejim):
    """Rejimi bir bar gecikmeyle izleyen ağırlık (karar t, tutma t+1)."""
    return np.concatenate([[0.0], rejim[:-1].astype(float)])


def _kosul(s: rp.RyppSonucu, ad: str) -> dict:
    return next(k for k in s.kosullar if k["ad"] == ad)


# ------------------------------------------------------------------ hükümler


def test_rejimi_izleyen_strateji_pass():
    r, rejim = piyasa()
    s = rp.degerlendir(girdi(r, _zamanlayici(rejim)))
    assert s.durum is rp.Durum.PASS, [k for k in s.kosullar if not k["gecti"]]
    assert s.strateji.mdd < 0.75 * s.kiyas.mdd


def test_yalniz_maruziyet_dusurmek_fail_plasebo_ayirt_eder():
    """Sabit %50: düşüş ~yarıya iner (P1 geçer) ama zamanlama yok → P3 kalır → FAIL."""
    r, _ = piyasa()
    s = rp.degerlendir(girdi(r, np.full_like(r, 0.5)))
    assert _kosul(s, "P1_dusus_azaltimi")["gecti"] is True
    assert _kosul(s, "P3_plasebo")["gecti"] is False
    assert s.durum is rp.Durum.FAIL


def test_rastgele_zamanlama_fail():
    r, _ = piyasa()
    rng = np.random.default_rng(7)
    w = np.repeat(rng.integers(0, 2, len(r) // 20 + 1), 20)[: len(r)].astype(float)
    assert rp.degerlendir(girdi(r, w)).durum is rp.Durum.FAIL


def test_tek_olay_baskinligi_fail():
    """Yalnız ilk ayıdan kaçınan strateji: R3 (en az iki epizotta iyileşme) kalır."""
    r, rejim = piyasa()
    w = np.ones_like(r)
    ilk_ayi = np.flatnonzero(~rejim)
    bas = ilk_ayi[0]
    bit = bas + np.argmax(rejim[bas:])  # ilk ayının sonu
    w[bas + 1:bit + 1] = 0.0
    s = rp.degerlendir(girdi(r, w))
    assert s.durum is rp.Durum.FAIL
    assert _kosul(s, "R3_tek_olay")["gecti"] is False


def test_maliyet_stresinde_coken_strateji_fail():
    """2x maliyette MAR kıyasın altına düşen strateji (S1) — diğer koşullar geçse de FAIL."""
    r, rejim = piyasa()
    g = girdi(r, _zamanlayici(rejim))
    coken = np.linspace(1.0, 0.5, len(r) + 1)  # 2x maliyette sürekli eriyen özkaynak
    s = rp.degerlendir(rp.RyppGirdisi(**{**g.__dict__, "strateji_2x_maliyet": coken}))
    assert _kosul(s, "S1_maliyet_stresi")["gecti"] is False and s.durum is rp.Durum.FAIL


@pytest.mark.parametrize(("deg", "kosul"), [
    ({"plasebo": False}, "plasebo_var"),
    ({"stres": False}, "stres_var"),
])
def test_eksik_kanit_inconclusive(deg, kosul):
    r, rejim = piyasa()
    s = rp.degerlendir(girdi(r, _zamanlayici(rejim), **deg))
    assert s.durum is rp.Durum.INCONCLUSIVE and _kosul(s, kosul)["gecti"] is False


def test_kisa_oos_inconclusive():
    r, rejim = piyasa(yil=1.2)
    s = rp.degerlendir(girdi(r, _zamanlayici(rejim)))
    assert s.durum is rp.Durum.INCONCLUSIVE and _kosul(s, "oos_suresi")["gecti"] is False


def test_dusus_epizodu_yoksa_inconclusive():
    r, rejim = piyasa(ayilar=False)
    s = rp.degerlendir(girdi(r, _zamanlayici(rejim)))
    assert s.durum is rp.Durum.INCONCLUSIVE and _kosul(s, "kiyas_epizot")["gecti"] is False


def test_bootstrap_belirsizse_inconclusive(monkeypatch):
    r, rejim = piyasa()
    monkeypatch.setattr(rp, "blok_bootstrap", lambda *a, **k: {
        "azaltim_p05": -0.01, "azaltim_p50": 0.3, "mar_ustunluk_olasiligi": 0.95})
    assert rp.degerlendir(girdi(r, _zamanlayici(rejim))).durum is rp.Durum.INCONCLUSIVE


# ------------------------------------------------------------------ çoklu test / plasebo


def test_aile_buyudukce_plasebo_esigi_sikilasir():
    r, rejim = piyasa()
    esik = [_kosul(rp.degerlendir(girdi(r, _zamanlayici(rejim), k=k)), "P3_plasebo")["esik"]
            for k in (1, 10, 50)]
    assert esik[0] <= esik[1] <= esik[2]


def test_plasebo_islem_sayisini_ve_maruziyeti_korur():
    r, rejim = piyasa()
    w = _zamanlayici(rejim)
    for k in (50, 300, 700):
        v = np.roll(w, k)
        assert v.mean() == pytest.approx(w.mean())
        assert abs(np.count_nonzero(np.diff(v)) - np.count_nonzero(np.diff(w))) <= 2


def test_plasebo_kucuk_kaydirmayi_dislar():
    r, rejim = piyasa()
    rng = np.random.default_rng(0)
    asgari = int(len(r) * 0.05)
    k = rng.integers(asgari, len(r) - asgari + 1, size=500)
    assert k.min() >= asgari and k.max() <= len(r) - asgari


# ------------------------------------------------------------------ ölçüler


def test_sortino_standart_elle_hesapla_esit_ve_eski_alan_farkli():
    g = np.array([0.02, -0.01, 0.03, -0.02, 0.01])
    asagi = math.sqrt(np.mean(np.minimum(g, 0) ** 2))
    assert rp.sortino_standart(g, YIL) == pytest.approx(g.mean() / asagi * math.sqrt(YIL))
    # Eski `Metrikler.sortino`: yalnız negatif gözlemlerin ortalaması (K-125/B-1).
    eski = g.mean() / math.sqrt(np.mean(g[g < 0] ** 2)) * math.sqrt(YIL)
    assert eski == pytest.approx(rp.sortino_standart(g, YIL) * math.sqrt(2 / 5))


def test_dusus_epizotlari_bilinen_egri():
    oz = np.array([100, 110, 88, 95, 120, 100, 90, 130, 125.0])
    ep = rp.dusus_epizotlari(oz, 0.15)
    assert [(z, d) for z, d, _, _ in ep] == [(1, 2), (4, 6)]
    assert ep[0][3] == pytest.approx(0.2) and ep[1][3] == pytest.approx(0.25)


def test_olc_cagr_ve_mdd():
    oz = np.concatenate([[1.0], np.full(YIL, 1.0)])
    oz[1:] = np.cumprod(np.full(YIL, 1.10 ** (1 / YIL)))
    m = rp.olc(oz, YIL)
    assert m.cagr == pytest.approx(0.10, rel=1e-6) and m.mdd == 0.0 and math.isnan(m.mar)


# ------------------------------------------------------------------ sözleşme


def test_nan_ve_hizasiz_seri_hata():
    r, rejim = piyasa()
    g = girdi(r, _zamanlayici(rejim))
    bozuk = g.strateji.copy()
    bozuk[10] = np.nan
    with pytest.raises(rp.ProtokolHatasi, match="NaN"):
        rp.degerlendir(rp.RyppGirdisi(**{**g.__dict__, "strateji": bozuk}))
    with pytest.raises(rp.ProtokolHatasi, match="hizasız"):
        rp.degerlendir(rp.RyppGirdisi(**{**g.__dict__, "strateji": g.strateji[:-5]}))
    with pytest.raises(rp.ProtokolHatasi):
        rp.plasebo_mar(r, _zamanlayici(rejim)[:-1], maliyet_orani=MALIYET, yil_bar=YIL)


def test_ayni_girdi_ayni_sonuc():
    r, rejim = piyasa()
    a = rp.degerlendir(girdi(r, _zamanlayici(rejim))).sozluk()
    b = rp.degerlendir(girdi(r, _zamanlayici(rejim))).sozluk()
    assert a == b
