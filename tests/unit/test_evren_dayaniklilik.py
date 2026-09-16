"""Evren dayanıklılığı: en iyi katkı çıkarılınca geriye ne kalıyor? (K-054, Faz 11)

Ölçülen üç şey:

1. **Yeniden koşuyor, atıf yapmıyor.** En kolay yol o enstrümanın P&L'ini toplamdan
   çıkarmak olurdu ve yanlış olurdu: o enstrüman evrende olmasaydı sermaye başka yere
   giderdi. Test, çıkarılan enstrümanın yerine gerçekten başkasının geçtiğini gösteriyor.
2. **Tek sembolde ölçülemez** (K-054) — ve ölçülemeyen kapı geçilmiş sayılmaz.
3. **Katkı yalnızca kapanmış turlardan.** Açık bir turun P&L'i gerçekleşmemiştir.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.backtest.motor import Backtest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.research.evren_dayaniklilik import (
    DayaniklilikHatasi,
    katkilar,
    olc,
    uyeligi_dusur,
)
from scryne_quant.strategy.kosu import evren_gorunum_kur
from tests.conftest import PlanliHedef, PlanliStrateji, bar_uret

MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
SEMBOLLER = ("AAAUSDT", "BBBUSDT", "CCCUSDT")


def _evren(n: int = 200):
    diziler = {
        s: bar_dizileri(bar_uret(n=n, tohum=11 + i)) for i, s in enumerate(SEMBOLLER)
    }
    uyelik = {s: np.ones(n, dtype=bool) for s in SEMBOLLER}
    return diziler, uyelik


def _kos(diziler, uyelik, takvim):
    strateji = PlanliHedef(takvim)
    gorunum = evren_gorunum_kur("1h", diziler, uyelik, strateji)
    return CokluBacktest(strateji, MALIYET).calistir(gorunum)


class TestKatkilar:
    def test_sembol_basina_toplaniyor(self):
        diziler, uyelik = _evren()
        takvim = {
            20: {"AAAUSDT": 0.3, "BBBUSDT": 0.3},
            80: {"AAAUSDT": 0.0, "BBBUSDT": 0.0},
        }
        sonuc = _kos(diziler, uyelik, takvim)
        k = katkilar(sonuc)
        assert set(k) == {"AAAUSDT", "BBBUSDT"}

    def test_acik_tur_sayilmiyor(self):
        """Gerçekleşmemiş bir kârı bir enstrümana yazmak, olmayan bir katkı uydurmaktır."""
        diziler, uyelik = _evren()
        sonuc = _kos(diziler, uyelik, {20: {"AAAUSDT": 0.3}})
        assert sonuc.acik_pozisyon_sonda
        assert katkilar(sonuc) == {}


class TestOlcum:
    def test_tek_sembolde_olculemez(self):
        """K-054: tek sembolde geliştirilen strateji de evrene karşı sınanmak zorunda."""
        diziler = bar_dizileri(bar_uret(n=120))
        sonuc = Backtest(
            PlanliStrateji({20: ("BUY", 0.3), 80: ("FLAT", 0.0)}), MALIYET
        ).calistir("BTCUSDT", "1h", diziler)
        olcum = olc(sonuc, lambda _: sonuc)
        assert olcum.dusus is None
        assert olcum.azaltilmis_sharpe is None

    def test_cikarma_yeniden_kosuyor(self):
        """Çıkarılan enstrümanın sermayesi nakitte beklemiyor; portföy yeniden kuruluyor."""
        diziler, uyelik = _evren()
        takvim = {
            20: {"AAAUSDT": 0.3, "BBBUSDT": 0.3, "CCCUSDT": 0.3},
            150: {"AAAUSDT": 0.0, "BBBUSDT": 0.0, "CCCUSDT": 0.0},
        }
        tam = _kos(diziler, uyelik, takvim)

        cagrildi: list[frozenset[str]] = []

        def yeniden(cikarilanlar: frozenset[str]):
            cagrildi.append(cikarilanlar)
            return _kos(diziler, uyeligi_dusur(uyelik, cikarilanlar), takvim)

        olcum = olc(tam, yeniden, k=1)
        assert len(cagrildi) == 1 and len(cagrildi[0]) == 1
        assert olcum.dusus is not None
        assert olcum.cikarilan[0] in SEMBOLLER
        # Çıkarılan sembol azaltılmış koşuda hiç işlem görmemeli.
        azaltilmis = _kos(diziler, uyeligi_dusur(uyelik, cagrildi[0]), takvim)
        assert all(i.sembol not in cagrildi[0] for i in azaltilmis.islemler)

    def test_en_yuksek_katki_cikariliyor(self):
        diziler, uyelik = _evren()
        takvim = {
            20: {s: 0.3 for s in SEMBOLLER},
            150: {s: 0.0 for s in SEMBOLLER},
        }
        tam = _kos(diziler, uyelik, takvim)
        k = katkilar(tam)
        beklenen = max(sorted(k), key=lambda s: k[s])
        olcum = olc(tam, lambda c: _kos(diziler, uyeligi_dusur(uyelik, c), takvim), k=1)
        assert olcum.cikarilan == [beklenen]

    def test_yeterli_enstruman_yoksa_olculemez(self):
        diziler, uyelik = _evren()
        takvim = {20: {"AAAUSDT": 0.3}, 150: {"AAAUSDT": 0.0}}
        tam = _kos(diziler, uyelik, takvim)
        olcum = olc(tam, lambda c: tam, k=1)
        assert olcum.dusus is None

    def test_gecersiz_k(self):
        diziler, uyelik = _evren()
        tam = _kos(diziler, uyelik, {20: {"AAAUSDT": 0.3}, 150: {"AAAUSDT": 0.0}})
        with pytest.raises(DayaniklilikHatasi, match="k ≥ 1"):
            olc(tam, lambda c: tam, k=0)


class TestUyeligiDusur:
    def test_maske_sifirlaniyor_digerleri_bozulmuyor(self):
        _, uyelik = _evren(50)
        yeni = uyeligi_dusur(uyelik, {"BBBUSDT"})
        assert not yeni["BBBUSDT"].any()
        assert yeni["AAAUSDT"].all()
        # Kopya: kaynak maske değişmedi.
        assert uyelik["BBBUSDT"].all()

    def test_izgara_uzunlugu_korunuyor(self):
        """Sembolü silmek yerine üyeliğini düşürmek: ortak ızgara ve bar indeksleri aynı
        kalmalı, yoksa karşılaştırma başka bir pencerede yapılırdı."""
        _, uyelik = _evren(50)
        yeni = uyeligi_dusur(uyelik, {"CCCUSDT"})
        assert set(yeni) == set(uyelik)
        assert all(len(yeni[s]) == len(uyelik[s]) for s in uyelik)
