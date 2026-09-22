"""Portföy düzeyi kurma: korelasyon budaması ve oynaklık hedefi. (R7, `portfoy_kurma`, K-108)

Ölçülenler:

1. **Kapalı konumda kıyasla bit düzeyinde aynı**: `korelasyon_tavani = 1` (matris hesaplanmaz) ve
   `hedef_oynaklik = ∞` (brüt hiç düşmez). Kıyasın kendi kod yolu da `korelasyon=None` ile
   değişmedi (`test_evren_kurma`nın bant testi bunu zaten hash düzeyinde kanıtlıyor).
2. Kapalı konum ızgaralarda **yok**.
3. Budama gerçekten buduyor: birebir aynı getiriye sahip iki sembolden sıralamada alttaki, sıkı
   tavanda taşınmaz; gevşek tavanda taşınır. Ölçülemeyen çift budanır (K-019).
4. Oynaklık hedefi **yalnız düşürür**: maruziyet kıyasınkini hiçbir barda aşmaz, düşük hedefte
   ortalaması düşer; ölçülemeyen oynaklıkta kıyas gibi davranır.
5. Kayıtlar: program, aile, sinyal özelliği, 12 nokta.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.coklu_test_evren import SINYAL_OZELLIKLERI
from scryne_quant.research.evren_kosu import EvrenVerisi
from scryne_quant.research.izgaralar import (
    PORTFOY_CEKILISLERI,
    cekilis_programi,
    evren_cekilisi,
)
from scryne_quant.research.tarama import izgara as izgara_uret
from scryne_quant.strategy.kurma import Aday, KurmaAyarlari, sec
from scryne_quant.strategy.kutuphane import (
    EVREN_AILELER,
    EvrenEsitAgirlik,
    EvrenKorelasyonBudama,
    EvrenOynaklikHedefi,
)
from scryne_quant.strategy.kutuphane.evren_portfoy import _ciftli_korelasyon
from tests.conftest import bar_uret

MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
N = 1_600
SEMBOLLER = ("AAAUSDT", "BBBUSDT", "BTCUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT")
HEDEF_BRUT = 0.2
PENCERE = 240


def _veri(kopya: dict[str, str] | None = None) -> EvrenVerisi:
    """`kopya={"BBBUSDT": "AAAUSDT"}`: BBB'nin fiyatları AAA'nın ölçekli kopyası (ρ = 1)."""
    diziler = {
        s: {a: np.array(x, copy=True)
            for a, x in bar_dizileri(bar_uret(n=N, tohum=101 + 7 * i)).items()}
        for i, s in enumerate(SEMBOLLER)
    }
    for hedef, kaynak in (kopya or {}).items():
        for alan in ("open", "high", "low", "close"):
            diziler[hedef][alan] = diziler[kaynak][alan] * 0.5
    return EvrenVerisi(
        timeframe="1h",
        zamanlar=diziler["AAAUSDT"]["open_time"],
        diziler=diziler,
        uyelik={s: np.ones(N, dtype=bool) for s in SEMBOLLER},
        veri_sha256={s: "0" * 64 for s in SEMBOLLER},
        meta={},
        olcum_baslangici=722,
        kural_kimligi="test",
    )


def _pencere() -> Pencere:
    return Pencere("p", baslangic=722, bitis=N, isinma_baslangic=0)


def _evren_sigma(veri: EvrenVerisi) -> float:
    """Fixture'ın kaba oynaklık düzeyi (bar aralığı / kapanış medyanı); hedefleri ölçekler."""
    return float(np.median(np.concatenate([
        (veri.diziler[s]["high"] - veri.diziler[s]["low"])[800:] / veri.diziler[s]["close"][800:]
        for s in SEMBOLLER
    ])))


def _kiyas(veri: EvrenVerisi, azami: int):
    return ed.kosu(
        EvrenEsitAgirlik(yeniden_dengele_bar=168, azami_enstruman=azami,
                         azami_agirlik=HEDEF_BRUT / azami, hedef_brut=HEDEF_BRUT),
        MALIYET, veri, _pencere(),
    )


class TestKapaliKonum:
    @pytest.mark.parametrize("azami", [2, 4])
    def test_tavan_bir_iken_kiyasla_bit_ayni(self, azami):
        veri = _veri()
        kiyas = _kiyas(veri, azami)
        s = ed.kosu(
            EvrenKorelasyonBudama(korelasyon_tavani=1.0, pencere=PENCERE, azami_enstruman=azami,
                                  yeniden_dengele_bar=168, hedef_brut=HEDEF_BRUT),
            MALIYET, veri, _pencere(),
        )
        assert s.sonuc_hash == kiyas.sonuc_hash
        assert s.ozkaynak.tobytes() == kiyas.ozkaynak.tobytes()

    @pytest.mark.parametrize("azami", [2, 4])
    def test_hedef_sonsuzken_kiyasla_bit_ayni(self, azami):
        veri = _veri()
        kiyas = _kiyas(veri, azami)
        s = ed.kosu(
            EvrenOynaklikHedefi(hedef_oynaklik=float("inf"), azami_enstruman=azami,
                                yeniden_dengele_bar=168, hedef_brut=HEDEF_BRUT),
            MALIYET, veri, _pencere(),
        )
        assert s.sonuc_hash == kiyas.sonuc_hash
        assert s.ozkaynak.tobytes() == kiyas.ozkaynak.tobytes()

    def test_kapali_konum_izgaralarda_yok(self):
        assert 1.0 not in PORTFOY_CEKILISLERI["portfoy_korelasyon"][1]["korelasyon_tavani"]
        assert all(np.isfinite(h) for h in
                   PORTFOY_CEKILISLERI["portfoy_oynaklik_hedefi"][1]["hedef_oynaklik"])


class TestKorelasyonBudama:
    def test_ayni_getirili_sembol_siki_tavanda_tasinmaz(self):
        """BBB = AAA'nın kopyası (ρ = 1). Sıralama hacimle; hangisi üstteyse öteki budanır."""
        veri = _veri(kopya={"BBBUSDT": "AAAUSDT"})
        siki = ed.kosu(
            EvrenKorelasyonBudama(korelasyon_tavani=0.9, pencere=PENCERE, azami_enstruman=6,
                                  yeniden_dengele_bar=168, hedef_brut=HEDEF_BRUT),
            MALIYET, veri, _pencere(),
        )
        gevsek = ed.kosu(
            EvrenKorelasyonBudama(korelasyon_tavani=1.0, pencere=PENCERE, azami_enstruman=6,
                                  yeniden_dengele_bar=168, hedef_brut=HEDEF_BRUT),
            MALIYET, veri, _pencere(),
        )
        siki_semboller = {i.sembol for i in siki.islemler}
        gevsek_semboller = {i.sembol for i in gevsek.islemler}
        assert {"AAAUSDT", "BBBUSDT"} <= gevsek_semboller
        assert len({"AAAUSDT", "BBBUSDT"} & siki_semboller) == 1
        # Budanan ismin payı nakitte kalmaz: 6 aday, tavan 6 → 5 isim taşınır, brüt kıyasın altında.
        assert siki.maruziyet.max() < gevsek.maruziyet.max()

    def test_ciftli_korelasyon_olculemeyen_cift_sozlukte_yok(self):
        r = np.array([
            [0.01, -0.02, 0.03, 0.01, -0.01, 0.02],
            [0.02, -0.04, 0.06, 0.02, -0.02, 0.04],
            [np.nan, np.nan, np.nan, np.nan, 0.01, 0.02],
        ])
        k = _ciftli_korelasyon(("A", "B", "C"), r, asgari_ortak=3)
        assert k[("A", "B")] == pytest.approx(1.0)
        assert ("A", "C") not in k and ("B", "C") not in k
        # `sec`: ölçülemeyen çift 1,0 sayılır → sıkı tavanda C budanır (K-019).
        adaylar = [Aday(sembol=s, skor=3.0 - i, oynaklik=0.01, reason="TEST")
                   for i, s in enumerate("ABC")]
        ayar = KurmaAyarlari(yontem="TEST", azami_enstruman=3, hedef_brut=0.2,
                             azami_agirlik=0.1, esit_agirlik=True, korelasyon_tavani=0.9)
        assert [a.sembol for a in sec(adaylar, ayar, k)] == ["A"]

    def test_tavan_araligi_dogrulaniyor(self):
        with pytest.raises(ValueError):
            EvrenKorelasyonBudama(korelasyon_tavani=0.0)
        with pytest.raises(ValueError):
            EvrenKorelasyonBudama(korelasyon_tavani=1.5)


class TestOynaklikHedefi:
    def test_yalniz_dusurur(self):
        """Hedef evren oynaklığının yarısı: brüt yaklaşık yarıya iner, hiçbir barda kıyası aşmaz.

        Çok düşük hedef (ör. 1e-4) brütü toz eşiğinin (`asgari_agirlik` 0,005) altına iter ve
        kurma katmanı pozisyonu sıfırlar — bu kurma sözleşmesi, hedefin hatası değil; gerçek
        ızgarada n=20 × en oynak haftalarda aynı şey olabilir ve kayda `maruziyet` olarak girer.
        """
        veri = _veri()
        kiyas = _kiyas(veri, 4)
        sigma = _evren_sigma(veri)
        dusuk = ed.kosu(
            EvrenOynaklikHedefi(hedef_oynaklik=0.5 * sigma, azami_enstruman=4,
                                yeniden_dengele_bar=168, hedef_brut=HEDEF_BRUT),
            MALIYET, veri, _pencere(),
        )
        assert dusuk.maruziyet.max() <= kiyas.maruziyet.max() + 1e-12
        assert dusuk.maruziyet.mean() < 0.75 * kiyas.maruziyet.mean()
        assert dusuk.metrikler.islem_sayisi > 0

    def test_hedef_ekseni_canli(self):
        """Izgaradaki dört hedef aynı sonucu vermemeli (ölü eksen plato uydurur)."""
        veri = _veri()
        sigma = _evren_sigma(veri)
        hedefler = (0.25 * sigma, 0.5 * sigma, 1.0 * sigma, 2.0 * sigma)
        hashler = {
            h: ed.kosu(EvrenOynaklikHedefi(hedef_oynaklik=h, azami_enstruman=4,
                                           yeniden_dengele_bar=168, hedef_brut=HEDEF_BRUT),
                       MALIYET, veri, _pencere()).sonuc_hash
            for h in hedefler
        }
        assert len(set(hashler.values())) > 1

    def test_hedef_pozitif_olmali(self):
        with pytest.raises(ValueError):
            EvrenOynaklikHedefi(hedef_oynaklik=0.0)


class TestKayitTutarliligi:
    def test_cekilisler_programa_bagli_ve_aile_kayitli(self):
        for ad, (strateji, _) in PORTFOY_CEKILISLERI.items():
            assert cekilis_programi(ad) == "portfoy_kurma"
            assert evren_cekilisi(ad)[0] == strateji
            assert strateji in EVREN_AILELER
            assert strateji in SINYAL_OZELLIKLERI

    def test_izgaralar_on_iki_noktali(self):
        for ad, (strateji, g) in PORTFOY_CEKILISLERI.items():
            noktalar = list(izgara_uret(g))
            assert len(noktalar) == 12, ad
            for p in noktalar:
                assert EVREN_AILELER[strateji](**p).sozluk()["kiyas"] is False
