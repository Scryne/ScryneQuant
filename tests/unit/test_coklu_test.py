"""Çoklu test düzeltmesi: null kurgusunun kendisi doğru mu? (K-039'un açık düzeltmesi)

Bu dosyanın ölçtüğü şey bir strateji değil, bir **ölçüm aletidir** — ve alet yanlışsa
ürettiği eşik de yanlış olur, üstelik makul görünerek. Geliştirme sırasında tam olarak bu
oldu: null dağılımı rastgele bir stratejiye p99'da 4,2 Sharpe atfetti ve sayı **absürt
olduğu için** fark edildi. Biraz daha makul olsaydı fark edilmezdi ve K-039'un düzeltmesi
uydurulmuş bir sayıyla kapanırdı.

İki hata da burada teste bağlandı:

1. **Takvimin tanım kümesi** ölçüm penceresiyle karıştırılmıştı; taşan indeksler dairesel
   kaydırmada birbirinin üstüne yazıp sinyalleri sessizce düşürüyordu (`TestKaydir`).
2. **Maksimum** uygunluk süzgeci olmadan alınıyordu; az işlemli çekilişler şansa yüksek
   Sharpe üretip düzeltmeyi şişiriyordu (`TestUygunluk`).
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.research.coklu_test import (
    BetikStrateji,
    Cekilis,
    CokluTestHatasi,
    KayitliStrateji,
    beklenen_azami_sharpe,
    kaydir,
    null_dagilimi,
)
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji


def cekilis(kimlik: str = "a", *, sharpe: float = 0.0, bar: int = 100, sinyal: int = 10) -> Cekilis:
    takvim = {i: ("BUY" if i % 2 == 0 else "FLAT", 0.5) for i in range(0, sinyal * 2, 2)}
    return Cekilis(
        kimlik=kimlik,
        strateji="test",
        timeframe="1h",
        secim="tepe",
        secilen={},
        veri_sha256="0" * 64,
        gercek_sharpe=sharpe,
        isinma_bar=0,
        oos_bar=bar // 2,
        takvim_bar=bar,
        takvim=takvim,
    )


class TestKaydir:
    def test_dairesel_kaydirma_sinyal_sayisini_koruyor(self) -> None:
        t = {0: ("BUY", 1.0), 5: ("FLAT", 0.0), 9: ("BUY", 0.5)}
        for k in range(10):
            assert len(kaydir(t, k, 10)) == 3

    def test_sifir_kaydirma_kimlik(self) -> None:
        t = {0: ("BUY", 1.0), 5: ("FLAT", 0.0)}
        assert kaydir(t, 0, 10) == t

    def test_sarmalama_dairesel(self) -> None:
        assert kaydir({8: ("BUY", 1.0)}, 5, 10) == {3: ("BUY", 1.0)}

    def test_tanim_kumesi_disindaki_indeks_hata(self) -> None:
        """Sessizce mod almak, sinyalleri kaybettiren hatanın ta kendisiydi.

        Takvim indeksleri motorun gördüğü dilimin tamamı üzerinde üretiliyor, ölçüm ise
        dilimin son kısmında. Modül olarak ölçüm uzunluğu verilince taşan indeksler
        sarmalanıp üst üste yazdı — ve null dağılımı absürt çıktı.
        """
        with pytest.raises(CokluTestHatasi, match="tanım kümesi dışında"):
            kaydir({15: ("BUY", 1.0)}, 3, 10)

    def test_negatif_indeks_hata(self) -> None:
        with pytest.raises(CokluTestHatasi, match="tanım kümesi dışında"):
            kaydir({-1: ("BUY", 1.0)}, 3, 10)

    def test_sifir_uzunluk_hata(self) -> None:
        with pytest.raises(CokluTestHatasi, match="pozitif olmalı"):
            kaydir({0: ("BUY", 1.0)}, 1, 0)


class TestBetikStrateji:
    def test_takvimdeki_barda_sinyal_uretiyor(self) -> None:
        s = BetikStrateji({3: ("BUY", 0.4)})
        assert s.on_bar(_ctx(4)) is not None

    def test_takvim_disi_barda_sinyal_yok(self) -> None:
        s = BetikStrateji({3: ("BUY", 0.4)})
        assert s.on_bar(_ctx(2)) is None

    def test_sinyal_takvimdeki_degerleri_tasiyor(self) -> None:
        sinyal = BetikStrateji({0: ("BUY", 0.25)}).on_bar(_ctx(1))
        assert sinyal is not None
        assert sinyal.side is Yon.BUY
        assert sinyal.target_exposure == 0.25

    def test_isinma_bar_metot_sozlesmesi(self) -> None:
        """Taban sınıfta `isinma_bar` bir metot; property yapmak sözleşmeyi bozardı."""
        assert BetikStrateji({}, isinma=7).isinma_bar() == 7

    def test_kutuphaneye_kayitli_degil(self) -> None:
        """Ölçüm aleti bir hipotez değildir — kayıtlı olsaydı çekiliş sayılabilirdi (K-039)."""
        from scryne_quant.strategy.kutuphane import KIYAS, KUTUPHANE

        assert "betik" not in {**KUTUPHANE, **KIYAS}
        assert "kayitli" not in {**KUTUPHANE, **KIYAS}


class TestKayitliStrateji:
    def test_ic_stratejinin_sinyalini_aynen_geciriyor(self) -> None:
        ic = _SabitStrateji(0.33)
        sarmal = KayitliStrateji(ic)
        a, b = ic.on_bar(_ctx(1)), sarmal.on_bar(_ctx(1))
        assert b is not None and a is not None
        assert (b.side, b.target_exposure) == (a.side, a.target_exposure)

    def test_takvime_yaziyor(self) -> None:
        sarmal = KayitliStrateji(_SabitStrateji(0.33))
        sarmal.on_bar(_ctx(1))
        sarmal.on_bar(_ctx(4))
        assert sarmal.takvim == {0: ("BUY", 0.33), 3: ("BUY", 0.33)}

    def test_hazirla_takvimi_sifirliyor(self) -> None:
        sarmal = KayitliStrateji(_SabitStrateji(0.33))
        sarmal.on_bar(_ctx(1))
        sarmal.hazirla()
        assert sarmal.takvim == {}

    def test_sinyal_uretmeyen_bar_takvime_girmiyor(self) -> None:
        sarmal = KayitliStrateji(_SabitStrateji(0.33, sessiz=True))
        sarmal.on_bar(_ctx(1))
        assert sarmal.takvim == {}


class TestNullDagilimi:
    def test_paylasilan_kaydirma_ayni_turda_ayni_oran(self) -> None:
        """Korelasyonun korunması buna bağlı: iterasyon başına tek oran.

        İki çekiliş aynı `takvim_bar`a sahipse aynı `k` ile kaydırılmalı. Bağımsız
        kaydırma stratejiler arası ilişkiyi koparır ve maksimumun dağılımını genişletir —
        yani düzeltmeyi olduğundan büyük gösterir.
        """
        gorulen: dict[str, list[int]] = {"a": [], "b": []}

        def kosturucu(c, takvim):
            gorulen[c.kimlik].append(min(takvim))
            return 0.0, True

        null_dagilimi([cekilis("a"), cekilis("b")], kosturucu, deneme=25, seed=3)
        assert gorulen["a"] == gorulen["b"]

    def test_ayni_seed_ayni_sonuc(self) -> None:
        def kosturucu(c, takvim):
            return float(min(takvim)) / 100.0, True

        a = null_dagilimi([cekilis()], kosturucu, deneme=30, seed=5)
        b = null_dagilimi([cekilis()], kosturucu, deneme=30, seed=5)
        assert a.azami_dagilimi == b.azami_dagilimi

    def test_farkli_seed_farkli_sonuc(self) -> None:
        def kosturucu(c, takvim):
            return float(min(takvim)) / 100.0, True

        a = null_dagilimi([cekilis()], kosturucu, deneme=30, seed=5)
        b = null_dagilimi([cekilis()], kosturucu, deneme=30, seed=6)
        assert a.azami_dagilimi != b.azami_dagilimi

    def test_kaydirma_hicbir_zaman_sifir_degil(self) -> None:
        """`k = 0` gerçek dizilimdir; null örneğine gerçek sonucu koymak onu kirletirdi."""
        kaydirmalar: list[int] = []

        def kosturucu(c, takvim):
            kaydirmalar.append(min(takvim))
            return 0.0, True

        null_dagilimi([cekilis(sinyal=1)], kosturucu, deneme=100, seed=1)
        assert 0 not in kaydirmalar

    def test_p_degeri_gercek_sonuca_gore(self) -> None:
        def kosturucu(c, takvim):
            return 1.0, True  # null her zaman gerçekten iyi

        n = null_dagilimi([cekilis(sharpe=0.5)], kosturucu, deneme=20, seed=1)
        assert n.p_degeri == 1.0

    def test_bos_cekilis_hata(self) -> None:
        with pytest.raises(CokluTestHatasi, match="en az bir çekiliş"):
            null_dagilimi([], lambda c, t: (0.0, True), deneme=5)

    def test_sifir_deneme_hata(self) -> None:
        with pytest.raises(CokluTestHatasi, match="deneme sayısı pozitif"):
            null_dagilimi([cekilis()], lambda c, t: (0.0, True), deneme=0)


class TestUygunluk:
    def test_uygun_olmayan_cekilis_maksimuma_girmiyor(self) -> None:
        """Düzeltmeyi şişiren ikinci hata buydu.

        Az işlemli bir çekiliş şansa yüksek Sharpe üretir ama `asgari_islem` kapısında
        zaten ölür. Onu maksimuma katmak, hiçbir zaman geçemeyecek bir kapıdan geçme
        olasılığını hesaplamak olurdu.
        """

        def kosturucu(c, takvim):
            return (9.0, False) if c.kimlik == "gurultu" else (0.1, True)

        n = null_dagilimi(
            [cekilis("gurultu"), cekilis("saglam")], kosturucu, deneme=20, seed=1
        )
        assert n.azami_dagilimi["p99"] == pytest.approx(0.1)
        assert n.ham_azami_dagilimi["p99"] == pytest.approx(9.0)

    def test_uygun_oran_raporlaniyor(self) -> None:
        def kosturucu(c, takvim):
            return 0.1, c.kimlik == "a"

        n = null_dagilimi([cekilis("a"), cekilis("b")], kosturucu, deneme=20, seed=1)
        assert n.uygun_oran == pytest.approx(0.5)

    def test_hic_uygun_yoksa_hata(self) -> None:
        """Sessizce boş dağılım dönmek, eşiği yokluktan türetmek olurdu."""
        with pytest.raises(CokluTestHatasi, match="hiçbir iterasyonda uygun"):
            null_dagilimi([cekilis()], lambda c, t: (1.0, False), deneme=10, seed=1)


class TestDuzeltilmisEsik:
    def _null(self):
        def kosturucu(c, takvim):
            return float(min(takvim)) / 100.0, True

        return null_dagilimi([cekilis(bar=1000, sinyal=1)], kosturucu, deneme=400, seed=2)

    def test_dusuk_yanlis_pozitif_daha_yuksek_esik(self) -> None:
        n = self._null()
        assert n.duzeltilmis_esik(0.01) > n.duzeltilmis_esik(0.05) > n.duzeltilmis_esik(0.20)

    def test_esik_p95_ile_tutarli(self) -> None:
        n = self._null()
        assert n.duzeltilmis_esik(0.05) == pytest.approx(n.azami_dagilimi["p95"], rel=1e-9)

    def test_gecersiz_oran_hata(self) -> None:
        n = self._null()
        for kotu in (0.0, 1.0, -0.1, 2.0):
            with pytest.raises(CokluTestHatasi, match="aralığında olmalı"):
                n.duzeltilmis_esik(kotu)


class TestDeflatedSharpe:
    def test_deneme_arttikca_beklenen_maksimum_artiyor(self) -> None:
        assert beklenen_azami_sharpe(100, 0.5) > beklenen_azami_sharpe(10, 0.5)

    def test_sapma_arttikca_beklenen_maksimum_artiyor(self) -> None:
        assert beklenen_azami_sharpe(31, 1.0) > beklenen_azami_sharpe(31, 0.5)

    def test_sapmayla_orantili(self) -> None:
        """Korelasyon veriden geliyor: yakın Sharpe'lar küçük sapma, küçük düzeltme."""
        assert beklenen_azami_sharpe(31, 1.0) == pytest.approx(
            2.0 * beklenen_azami_sharpe(31, 0.5)
        )

    def test_gecersiz_girdi_hata(self) -> None:
        with pytest.raises(CokluTestHatasi, match="en az 2 deneme"):
            beklenen_azami_sharpe(1, 0.5)
        with pytest.raises(CokluTestHatasi, match="sapması pozitif"):
            beklenen_azami_sharpe(31, 0.0)


# ------------------------------------------------------------------ yardımcılar


class _Ctx:
    """`Baglam`ın bu testlerde kullanılan yüzeyi kadarı."""

    def __init__(self, uzunluk: int) -> None:
        self.uzunluk = uzunluk
        self.sembol = "BTCUSDT"
        self.zaman = 1_700_000_000_000


def _ctx(uzunluk: int) -> _Ctx:
    return _Ctx(uzunluk)


class _SabitStrateji(Strateji):
    ad = "sabit"

    def __init__(self, maruziyet: float, *, sessiz: bool = False) -> None:
        self._maruziyet = maruziyet
        self._sessiz = sessiz
        super().__init__(maruziyet=maruziyet)

    def ozellikler(self):
        return ()

    def on_bar(self, ctx):
        if self._sessiz:
            return None
        return Sinyal(
            symbol=ctx.sembol,
            side=Yon.BUY,
            target_exposure=self._maruziyet,
            confidence=1.0,
            reason="SABIT",
            timestamp=ctx.zaman,
        )


def test_numpy_kullanilabiliyor() -> None:
    """Dağılım hesapları numpy'a dayanıyor; import kırılırsa testler sessizce atlanmasın."""
    assert np.percentile([1.0, 2.0, 3.0], 50) == pytest.approx(2.0)


class TestGuvenAraligi:
    """Eşik bir **tahmin**; hata payı sayının kendisi kadar kayda geçmeli.

    Gerekçe ölçümle geldi: 200 iterasyonda p95 = 0,854 çıkan dağılım 2.000 iterasyonda
    1,021 verdi. Fark gürültüydü ama sayıyı tek başına okuyan biri onu kesinlik sanardı.
    """

    def _null(self, deneme: int):
        def kosturucu(c, takvim):
            return float(min(takvim)) / 100.0, True

        return null_dagilimi(
            [cekilis(bar=1000, sinyal=1)], kosturucu, deneme=deneme, seed=2
        )

    def test_aralik_esigi_iceriyor(self) -> None:
        n = self._null(600)
        alt, ust = n.esik_guven_araligi(0.05, deneme=300, seed=1)
        assert alt <= n.duzeltilmis_esik(0.05) <= ust

    def test_daha_cok_iterasyon_daha_dar_aralik(self) -> None:
        dar = self._null(2_000).esik_guven_araligi(0.05, deneme=300, seed=1)
        genis = self._null(200).esik_guven_araligi(0.05, deneme=300, seed=1)
        assert (dar[1] - dar[0]) < (genis[1] - genis[0])

    def test_bos_ornek_hata(self) -> None:
        from scryne_quant.research.coklu_test import NullSonucu

        bos = NullSonucu(
            cekilis_sayisi=1, deneme=0, seed=0, gercek_en_iyi=0.0,
            gercek_en_iyi_strateji="x", azami_dagilimi={}, ham_azami_dagilimi={},
            uygun_oran=0.0, p_degeri=0.0,
        )
        with pytest.raises(CokluTestHatasi, match="güven aralığı hesaplanamaz"):
            bos.esik_guven_araligi(0.05)

    def test_ham_ornek_kayda_giriyor(self) -> None:
        """Özetten aralık çıkmaz: farklı bir oran 60 dakikalık koşu tekrarı istememeli."""
        n = self._null(50)
        assert len(n.sozluk()["azami_ornegi"]) == n.azami.size


class TestEsigiDefteBagla:
    """Düzeltilmiş eşik bir sabit değil, **defterin bir fotoğrafı**. (K-044)

    Tehlike somut: defter büyüdükçe gerçek eşik yükselir, ama `COKLU_TEST_ESIGI` sabiti
    yerinde kalır. O anda kapı, olduğundan gevşek bir kapıya dönüşür — ve bunu hiçbir
    test yakalamazsa, K-039'un engellemeye çalıştığı şey (yeterince çok deneyerek kapıyı
    delmek) düzeltmenin **kendi içinden** geri gelir.
    """

    def test_esik_defterdeki_olculebilir_cekilis_sayisina_bagli(self) -> None:
        from scryne_quant.research.kapilar import COKLU_TEST_CEKILIS_SAYISI

        assert COKLU_TEST_CEKILIS_SAYISI == 31, (
            "Ölçülebilir çekiliş sayısı değiştiyse COKLU_TEST_ESIGI bayattır: "
            "`sq lab coklu-test` yeniden koşturulup eşik güncellenmeli (K-044). "
            "Sabiti elle düzeltmek, ölçülmemiş bir sayıya ölçülmüş süsü vermektir."
        )

    def test_kapi_olculen_degeri_tasiyor(self) -> None:
        from scryne_quant.research.kapilar import COKLU_TEST_ESIGI, ESIKLER

        kapi = next(e for e in ESIKLER if e.ad == "oos_sharpe")
        assert kapi.sinir == COKLU_TEST_ESIGI

    def test_duzeltilmis_esik_eski_esikten_yuksek(self) -> None:
        """Düzeltme yalnızca **sıkılaştırabilir**. Gevşetseydi K-018'i delerdi."""
        from scryne_quant.research.kapilar import COKLU_TEST_ESIGI

        assert COKLU_TEST_ESIGI > 0.5

    def test_gerekce_olcume_isaret_ediyor(self) -> None:
        """K-033'ün kalıbı: her sınır kaynağını taşır. Bu sınırın kaynağı bir ölçüm."""
        from scryne_quant.research.kapilar import ESIKLER

        gerekce = next(e for e in ESIKLER if e.ad == "oos_sharpe").gerekce
        assert "K-044" in gerekce
        assert "coklu-test" in gerekce
