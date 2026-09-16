"""Evren çekilişlerinin çoklu test null'ı. (Faz 12)

Ölçülenler:

1. Kaydırma yalnızca sinyal özelliklerine dokunur; barlar, üyelik ve diğer özellikler aynı.
2. Kaydırmasız koşu kayıttaki `sonuc_hash`i vermezse ölçüm durur.
3. `oranlar` ve `birlesik_null`, tek sembollü `null_dagilimi` ile aynı oran dizisini ve aynı
   maksimum kuralını kullanır (bit düzeyinde aynı dağılım).
4. Kaydırma sinyali fiyattan koparır: kaydırılmış koşular gerçek koşudan farklı sonuç verir.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.research import coklu_test as coklu_mod
from scryne_quant.research import coklu_test_evren as cte
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.evren_kosu import EvrenVerisi
from scryne_quant.strategy.kutuphane import EVREN_AILELER, KesitselGuc
from tests.conftest import bar_uret

MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
SEMBOLLER = ("AAAUSDT", "BBBUSDT", "BTCUSDT", "CCCUSDT")
N = 1_200
PARAM = {"pencere": 48, "azami_enstruman": 2, "yeniden_dengele_bar": 24, "hedef_brut": 0.2}


def _veri() -> EvrenVerisi:
    diziler = {
        s: {a: np.array(x, copy=True)
            for a, x in bar_dizileri(bar_uret(n=N, tohum=71 + i)).items()}
        for i, s in enumerate(SEMBOLLER)
    }
    return EvrenVerisi(
        timeframe="1h", zamanlar=diziler["AAAUSDT"]["open_time"], diziler=diziler,
        uyelik={s: np.ones(N, dtype=bool) for s in SEMBOLLER},
        veri_sha256={s: "0" * 64 for s in SEMBOLLER}, meta={}, olcum_baslangici=100,
        kural_kimligi="test",
    )


PENCERE = Pencere("oos", baslangic=600, bitis=N, isinma_baslangic=500)


def test_her_evren_ailesinin_sinyal_ozelligi_tanimli():
    assert set(EVREN_AILELER) <= set(cte.SINYAL_OZELLIKLERI)


def test_kaydirma_yalnizca_sinyal_ozelligine_dokunur():
    g = ed.gorunum(_veri(), KesitselGuc(**PARAM), PENCERE)
    k = 37
    g2 = cte.kaydirilmis_gorunum(g, ("skor_ham",), k)
    for s in SEMBOLLER:
        a, b = g.gorunumler[s], g2.gorunumler[s]
        assert np.array_equal(b.ozellikler["skor_ham"], np.roll(a.ozellikler["skor_ham"], k),
                              equal_nan=True)
        assert np.array_equal(b.ozellikler["atr"], a.ozellikler["atr"], equal_nan=True)
        assert all(b.barlar[alan] is a.barlar[alan] for alan in a.barlar)  # kopya yok
    assert all(np.array_equal(g2.uyelik[s], g.uyelik[s]) for s in SEMBOLLER)


def _cekilis(hash_: str) -> cte.EvrenCekilisi:
    return cte.EvrenCekilisi(kimlik="x" * 64, strateji="kesitsel_guc", parametreler=PARAM,
                             gercek_sharpe=0.1, gercek_sonuc_hash=hash_, sifira_yaz_bar=48)


def _uygun(islem: int, dd: float) -> bool:
    return islem >= 1


def test_kayit_yeniden_uretilemezse_durur():
    with pytest.raises(cte.EvrenCokluTestHatasi):
        cte.cekilis_null(_cekilis("0" * 64), KesitselGuc, _veri(), MALIYET, PENCERE,
                         [0.5], _uygun)


def test_satirlar_uretiliyor_ve_kaydirma_sonucu_degistiriyor():
    veri = _veri()
    gercek = ed.kosu(KesitselGuc(**PARAM), MALIYET, veri, PENCERE, sifira_yaz_bar=48)
    oranlar = cte.oranlar(4, seed=3)
    c = cte.cekilis_null(_cekilis(gercek.sonuc_hash), KesitselGuc, veri, MALIYET, PENCERE,
                         oranlar, _uygun)
    assert len(c.satirlar) == 4
    assert any(abs(s - gercek.metrikler.sharpe) > 1e-9 for s, _ in c.satirlar)


def test_oranlar_ve_birlesik_null_tek_sembollu_null_ile_ayni():
    """Aynı tohum, aynı satırlar → `null_dagilimi` ile bit düzeyinde aynı dağılım."""
    deneme, seed, uzunluk = 50, 11, 100
    rng = np.random.default_rng(0)
    cekilisler = [
        coklu_mod.Cekilis(
            kimlik=f"c{j}", strateji=f"s{j}", timeframe="1h", secim="tepe", secilen={},
            veri_sha256="0" * 64, takvim={3: ("BUY", 0.2)}, takvim_bar=uzunluk,
            gercek_sharpe=float(rng.normal()), isinma_bar=0, oos_bar=uzunluk,
        )
        for j in range(3)
    ]
    tablo = {c.kimlik: rng.normal(size=uzunluk) for c in cekilisler}

    def kosturucu(c, takvim):
        k = next(iter(takvim))  # kaydırılmış tek sinyalin indeksi = 3 + k (mod uzunluk)
        return float(tablo[c.kimlik][k]), bool(k % 3)

    beklenen = coklu_mod.null_dagilimi(cekilisler, kosturucu, deneme=deneme, seed=seed)
    satirlar = {}
    for c in cekilisler:
        satir = []
        for oran in cte.oranlar(deneme, seed):
            k = 1 + int(oran * (uzunluk - 2))
            satir.append(kosturucu(c, coklu_mod.kaydir(c.takvim, k, uzunluk)))
        satirlar[c.kimlik] = satir
    gercek = {c.kimlik: (c.strateji, c.gercek_sharpe) for c in cekilisler}
    sonuc = cte.birlesik_null(satirlar, gercek, seed=seed)
    assert sonuc.azami.tobytes() == beklenen.azami.tobytes()
    assert sonuc.p_degeri == beklenen.p_degeri
    assert sonuc.uygun_oran == beklenen.uygun_oran
