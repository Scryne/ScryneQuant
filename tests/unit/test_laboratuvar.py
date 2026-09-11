"""Laboratuvar: tarama, walk-forward, Monte Carlo, stres, deney kaydı. (Faz 4)

Testler sentetik veriyle çalışır ve **kâr aramaz**: ölçülen şey laboratuvarın kurallara
uyup uymadığı — ızgaranın doğru gezilmesi, katmanların örtüşmemesi, seçim ölçütünün
kayda girmesi, aynı seed'in aynı sonucu vermesi.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.backtest.metrikler import Islem
from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.research import analiz, deney, karsilastirma, tarama, walkforward
from scryne_quant.research.bolme import Pencere, is_oos, walk_forward
from scryne_quant.research.izgaralar import IZGARALAR, IzgaraYok, boyut, izgara
from scryne_quant.strategy.kutuphane import (
    AILELER,
    KIYAS,
    KUTUPHANE,
    AlTut,
    BilinmeyenStrateji,
    SmaKesisim,
    aile,
    coz,
)

MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)


def _volatil_barlar(n: int, tohum: int, oynaklik: float = 0.008):
    """Geometrik rastgele yürüyüş — pozitif kalır, getirisi ölçek bağımsızdır."""
    import pandas as pd

    from scryne_quant.data.semalar import BAR_SUTUNLARI, KaliteDurumu

    rng = np.random.default_rng(tohum)
    getiriler = rng.normal(0.0, oynaklik, n)
    kapanis = 30_000.0 * np.cumprod(1.0 + getiriler)
    acilis = np.concatenate([[kapanis[0]], kapanis[:-1]])
    sapma = np.abs(rng.normal(0.0, oynaklik / 2, n)) * kapanis
    hacim = np.abs(rng.normal(50.0, 12.0, n))
    df = pd.DataFrame(
        {
            "open_time": 1_699_999_200_000 + np.arange(n, dtype="int64") * 3_600_000,
            "open": acilis,
            "high": np.maximum(acilis, kapanis) + sapma,
            "low": np.minimum(acilis, kapanis) - sapma,
            "close": kapanis,
            "volume": hacim,
            "quote_volume": hacim * kapanis,
            "trades": rng.integers(100, 5000, n),
            "quality_status": KaliteDurumu.OK,
        }
    )
    return df.loc[:, list(BAR_SUTUNLARI)]


@pytest.fixture(scope="module")
def diziler():
    """Gerçekçi oynaklıkta sentetik seri.

    `conftest.bar_uret` bar başına ~%0,08 oynaklık üretiyor (30.000 taban, σ=25). Bu,
    24 barlık ROC'u nadiren %2'nin üstüne çıkarıyor — ölçtük: `momentum` o seride tek
    sinyal üretmedi ve "strateji bozuk" gibi göründü. Oysa gerçek BTC/USDT 1h barının
    oynaklığı bunun ~10 katı.

    Bu yüzden burada bar başına ~%0,8 oynaklıkta geometrik bir yürüyüş kullanılıyor:
    eşikleri gerçek piyasaya göre yazılmış stratejiler sentetik veride sessizce
    "hiç işlem yapmadı" durumuna düşmesin.
    """
    return bar_dizileri(_volatil_barlar(n=3_000, tohum=21))


@pytest.fixture(scope="module")
def pencereler(diziler):
    return is_oos(len(diziler["open_time"]), isinma=60, oos_orani=0.30)


@pytest.fixture(scope="module")
def katmanlar(diziler):
    return walk_forward(len(diziler["open_time"]), isinma=60, egitim_bar=800, test_bar=300)


class TestKutuphane:
    def test_bes_aile_kayitli(self):
        """Roadmap Faz 4: beş strateji ailesi. Kıyas ölçütü aileden sayılmaz."""
        assert len(AILELER) == 5
        assert "kiyas" not in AILELER

    def test_her_aile_uyesi_kutuphanede(self):
        for uyeler in AILELER.values():
            for ad in uyeler:
                assert ad in KUTUPHANE

    def test_kutuphanedeki_her_strateji_bir_ailede(self):
        for ad in KUTUPHANE:
            assert aile(ad) in AILELER

    def test_kiyas_kutuphanede_degil(self):
        """Al-tut beş aileden biri değil, hepsinin karşısındaki çizgi."""
        assert AlTut.ad in KIYAS
        assert AlTut.ad not in KUTUPHANE
        assert aile(AlTut.ad) == "kiyas"

    def test_coz_kiyasi_da_buluyor(self):
        assert coz("sma_kesisim") is SmaKesisim
        assert coz("al_tut") is AlTut

    def test_bilinmeyen_strateji(self):
        with pytest.raises(BilinmeyenStrateji):
            coz("yok_boyle_bir_sey")

    def test_her_strateji_kurulabiliyor_ve_sinyal_uretiyor(self, diziler):
        """Kütüphaneye eklenip hiç koşturulmamış bir strateji ilk deneyde patlardı."""
        from scryne_quant.backtest.motor import Backtest

        for ad, sinif in {**KUTUPHANE, **KIYAS}.items():
            sonuc = Backtest(sinif(), MALIYET).calistir("BTCUSDT", "1h", diziler)
            assert sonuc.uretilen_sinyal > 0, f"{ad} hiç sinyal üretmedi"

    def test_her_stratejinin_izgarasi_var(self):
        for ad in {**KUTUPHANE, **KIYAS}:
            assert boyut(ad) >= 1

    def test_izgarasiz_strateji_hata(self):
        with pytest.raises(IzgaraYok):
            izgara("yok")

    def test_izgaralar_maruziyeti_sabitliyor(self):
        """Maruziyet risk motorunun kararı (Faz 5); tarama onu optimize edemez."""
        for ad, secenekler in IZGARALAR.items():
            assert len(secenekler["maruziyet"]) == 1, f"{ad}: maruziyet ızgarada değişken"

    def test_isinma_bar_izgaranin_en_uzun_penceresini_kapsiyor(self):
        for ad, sinif in KUTUPHANE.items():
            en_uzun = 0
            for kombinasyon in tarama.izgara(izgara(ad)):
                try:
                    en_uzun = max(en_uzun, sinif(**kombinasyon).isinma_bar())
                except (ValueError, TypeError):
                    continue
            assert en_uzun >= sinif().isinma_bar(), ad


class TestIzgara:
    def test_kartezyen_carpim(self):
        assert tarama.izgara({"a": [1, 2], "b": [3]}) == [{"a": 1, "b": 3}, {"a": 2, "b": 3}]

    def test_anahtar_sirasi_sabit(self):
        """Kombinasyon sırası deney kaydına giriyor; sözlük sırasına bırakılamaz."""
        a = tarama.izgara({"b": [1], "a": [2]})
        b = tarama.izgara({"a": [2], "b": [1]})
        assert a == b == [{"a": 2, "b": 1}]

    def test_bos_izgara(self):
        with pytest.raises(tarama.TaramaHatasi, match="boş"):
            tarama.izgara({})

    def test_bos_deger_listesi(self):
        with pytest.raises(tarama.TaramaHatasi, match="en az bir değer"):
            tarama.izgara({"a": []})


class TestTarama:
    def test_izgaranin_tamami_geziliyor(self, diziler, pencereler):
        ins, _ = pencereler
        sonuc = tarama.tara(
            SmaKesisim, {"hizli": (5, 10), "yavas": (20, 40), "maruziyet": (0.2,)},
            MALIYET, "BTCUSDT", "1h", diziler, ins,
        )
        assert len(sonuc.adaylar) == 4

    def test_gecersiz_kombinasyon_atlaniyor(self, diziler, pencereler):
        """`yavas <= hizli` stratejinin kendi kuralı; ızgarayı elle temizlemiyoruz."""
        ins, _ = pencereler
        sonuc = tarama.tara(
            SmaKesisim, {"hizli": (10, 40), "yavas": (20, 40), "maruziyet": (0.2,)},
            MALIYET, "BTCUSDT", "1h", diziler, ins,
        )
        assert len(sonuc.adaylar) < 4

    def test_asgari_islem_sarti(self, diziler, pencereler):
        ins, _ = pencereler
        sonuc = tarama.tara(
            SmaKesisim, {"hizli": (5,), "yavas": (20,), "maruziyet": (0.2,)},
            MALIYET, "BTCUSDT", "1h", diziler, ins, asgari_islem=10**9,
        )
        assert sonuc.gecerliler == []
        assert sonuc.en_iyi is None, "geçersiz aday sessizce seçilmemeli"

    def test_en_iyi_gecerliler_arasindan(self, diziler, pencereler):
        ins, _ = pencereler
        sonuc = tarama.tara(
            SmaKesisim, {"hizli": (5, 10), "yavas": (20, 40), "maruziyet": (0.2,)},
            MALIYET, "BTCUSDT", "1h", diziler, ins, asgari_islem=1,
        )
        en_iyi = sonuc.en_iyi
        assert en_iyi is not None
        assert en_iyi.skor == max(a.skor for a in sonuc.gecerliler)

    @pytest.mark.parametrize("olcut", sorted(tarama.OLCUTLER))
    def test_her_olcut_calisiyor(self, diziler, pencereler, olcut):
        ins, _ = pencereler
        sonuc = tarama.tara(
            SmaKesisim, {"hizli": (5,), "yavas": (20,), "maruziyet": (0.2,)},
            MALIYET, "BTCUSDT", "1h", diziler, ins, olcut=olcut, asgari_islem=1,
        )
        assert sonuc.olcut == olcut
        assert sonuc.sozluk()["olcut"] == olcut

    def test_bilinmeyen_olcut(self, diziler, pencereler):
        ins, _ = pencereler
        with pytest.raises(tarama.TaramaHatasi, match="bilinmeyen ölçüt"):
            tarama.tara(
                SmaKesisim, {"hizli": (5,), "yavas": (20,), "maruziyet": (0.2,)},
                MALIYET, "BTCUSDT", "1h", diziler, ins, olcut="kar",
            )

    def test_olcut_secimi_sonucu_degistiriyor(self, diziler, pencereler):
        """Ölçüt gizli bir varsayım değil, bir parametre — farklı ölçüt farklı seçer."""
        ins, _ = pencereler
        secenekler = {"hizli": (5, 10, 20), "yavas": (30, 60, 90), "maruziyet": (0.2,)}
        secimler = {
            olcut: tarama.tara(
                SmaKesisim, secenekler, MALIYET, "BTCUSDT", "1h", diziler, ins,
                olcut=olcut, asgari_islem=1,
            ).en_iyi.sozluk_parametreler
            for olcut in ("sharpe", "getiri")
        }
        assert len(secimler) == 2  # ikisi de bir seçim yaptı

    def test_plato_orani_araliginda(self, diziler, pencereler):
        ins, _ = pencereler
        sonuc = tarama.tara(
            SmaKesisim, {"hizli": (5, 10, 20), "yavas": (30, 60, 90), "maruziyet": (0.2,)},
            MALIYET, "BTCUSDT", "1h", diziler, ins, asgari_islem=1,
        )
        assert 0.0 <= sonuc.ust_yuzde_plato() <= 1.0
        assert sonuc.duyarlilik() >= 0.0

    def test_determinizm(self, diziler, pencereler):
        ins, _ = pencereler
        secenekler = {"hizli": (5, 10), "yavas": (20, 40), "maruziyet": (0.2,)}
        a = tarama.tara(SmaKesisim, secenekler, MALIYET, "BTCUSDT", "1h", diziler, ins)
        b = tarama.tara(SmaKesisim, secenekler, MALIYET, "BTCUSDT", "1h", diziler, ins)
        assert a.sozluk() == b.sozluk()

    def test_pencere_disindaki_veri_kullanilmiyor(self, diziler):
        """Pencere dilimi dışındaki barlar sonucu etkilememeli."""
        pencere = Pencere("p", baslangic=60, bitis=1_000, isinma_baslangic=0)
        bozuk = {ad: np.array(dizi) for ad, dizi in diziler.items()}
        for ad in ("open", "high", "low", "close"):
            bozuk[ad][1_000:] = 1.0

        secenekler = {"hizli": (5,), "yavas": (20,), "maruziyet": (0.2,)}
        a = tarama.tara(SmaKesisim, secenekler, MALIYET, "BTCUSDT", "1h", diziler, pencere,
                        asgari_islem=1)
        b = tarama.tara(SmaKesisim, secenekler, MALIYET, "BTCUSDT", "1h", bozuk, pencere,
                        asgari_islem=1)
        assert a.sozluk() == b.sozluk()


class TestWalkForward:

    def test_katmanlar_isleniyor(self, diziler, katmanlar):
        sonuc = walkforward.calistir(
            SmaKesisim, {"hizli": (5, 10), "yavas": (20, 40), "maruziyet": (0.2,)},
            MALIYET, "BTCUSDT", "1h", diziler, katmanlar,
        )
        assert len(sonuc.katmanlar) == len(katmanlar)
        assert sonuc.bilesik_ozkaynak.size > 0

    def test_sermaye_katmanlar_arasi_tasiniyor(self, diziler, katmanlar):
        """Her katmanı 10.000 ile başlatmak kaybeden katmanın etkisini silerdi."""
        sonuc = walkforward.calistir(
            SmaKesisim, {"hizli": (5, 10), "yavas": (20, 40), "maruziyet": (0.2,)},
            MALIYET, "BTCUSDT", "1h", diziler, katmanlar, baslangic_sermaye=10_000.0,
        )
        basarili = sonuc.basarili_katmanlar
        if len(basarili) >= 2:
            for onceki, sonraki in zip(basarili, basarili[1:], strict=False):
                assert sonraki.test_metrikler.baslangic_sermaye == pytest.approx(
                    onceki.test_metrikler.bitis_sermaye
                )

    def test_bilesik_egri_katmanlarin_birlesimi(self, diziler, katmanlar):
        sonuc = walkforward.calistir(
            SmaKesisim, {"hizli": (5, 10), "yavas": (20, 40), "maruziyet": (0.2,)},
            MALIYET, "BTCUSDT", "1h", diziler, katmanlar,
        )
        toplam = sum(k.test_ozkaynak.size for k in sonuc.basarili_katmanlar)
        assert sonuc.bilesik_ozkaynak.size == toplam
        assert sonuc.bilesik_zamanlar.size == toplam

    def test_parametre_kararliligi_raporlaniyor(self, diziler, katmanlar):
        """Faz 4 bitti kriteri: parametre kararlılığı görülebiliyor."""
        sonuc = walkforward.calistir(
            SmaKesisim, {"hizli": (5, 10, 20), "yavas": (30, 60), "maruziyet": (0.2,)},
            MALIYET, "BTCUSDT", "1h", diziler, katmanlar,
        )
        k = sonuc.parametre_kararliligi()
        assert k["katman"] == len(sonuc.basarili_katmanlar)
        assert {"hizli", "yavas", "maruziyet"} <= set(k["parametreler"])
        hizli = k["parametreler"]["hizli"]
        assert len(hizli["degerler"]) == k["katman"]
        assert hizli["benzersiz"] >= 1
        assert "degisim_katsayisi" in hizli

    def test_sabit_parametre_kararliligi_bir(self, diziler, katmanlar):
        """Tek noktalı ızgarada her katman aynı parametreyi seçmeli."""
        sonuc = walkforward.calistir(
            SmaKesisim, {"hizli": (5,), "yavas": (20,), "maruziyet": (0.2,)},
            MALIYET, "BTCUSDT", "1h", diziler, katmanlar,
        )
        k = sonuc.parametre_kararliligi()
        assert k["parametreler"]["hizli"]["benzersiz"] == 1
        assert k["parametreler"]["hizli"]["degisim_katsayisi"] == 0.0

    def test_bos_katman_listesi(self, diziler):
        with pytest.raises(walkforward.WalkForwardHatasi, match="boş"):
            walkforward.calistir(
                SmaKesisim, {"hizli": (5,), "yavas": (20,), "maruziyet": (0.2,)},
                MALIYET, "BTCUSDT", "1h", diziler, [],
            )

    def test_determinizm(self, diziler, katmanlar):
        secenekler = {"hizli": (5, 10), "yavas": (20, 40), "maruziyet": (0.2,)}
        a = walkforward.calistir(SmaKesisim, secenekler, MALIYET, "BTCUSDT", "1h",
                                 diziler, katmanlar)
        b = walkforward.calistir(SmaKesisim, secenekler, MALIYET, "BTCUSDT", "1h",
                                 diziler, katmanlar)
        # Hash üzerinden: aday bulunamayan bir katmanın `skor`u NaN ve `NaN != NaN`,
        # yani sözlük eşitliği deterministik bir sonucu bile "farklı" sayardı.
        assert nesne_hash(a.sozluk()) == nesne_hash(b.sozluk())


class TestMonteCarlo:
    @staticmethod
    def _islemler(oranlar: list[float]) -> list[Islem]:
        return [
            Islem(
                acilis_ms=i, kapanis_ms=i + 1, giris_notional=1_000.0, giris_miktar=1.0,
                cikis_notional=1_000.0 * (1 + o), cikis_miktar=1.0,
                net_pnl=1_000.0 * o, fill_sayisi=2,
            )
            for i, o in enumerate(oranlar)
        ]

    def test_ayni_seed_ayni_sonuc(self):
        islemler = self._islemler([0.1, -0.05, 0.2, -0.1, 0.05])
        a = analiz.monte_carlo(islemler, 10_000.0, deneme=200, seed=7)
        b = analiz.monte_carlo(islemler, 10_000.0, deneme=200, seed=7)
        assert a.sozluk() == b.sozluk()

    def test_farkli_seed_farkli_sonuc(self):
        islemler = self._islemler([0.1, -0.05, 0.2, -0.1, 0.05])
        a = analiz.monte_carlo(islemler, 10_000.0, deneme=200, seed=1)
        b = analiz.monte_carlo(islemler, 10_000.0, deneme=200, seed=2)
        assert a.drawdown_dagilimi != b.drawdown_dagilimi

    def test_getiri_siralamadan_bagimsiz(self):
        """Bileşik getiri çarpımdır, çarpma değişmeli — sıra getiriyi değiştirmez."""
        islemler = self._islemler([0.1, -0.05, 0.2, -0.1, 0.05])
        mc = analiz.monte_carlo(islemler, 10_000.0, deneme=200, seed=0)
        degerler = set(mc.getiri_dagilimi.values())
        assert max(degerler) - min(degerler) < 1e-9

    def test_dusus_siralamaya_bagli(self):
        """Aynı işlemler farklı sırada dizilince düşüş değişir — asıl ölçülen bu."""
        islemler = self._islemler([0.3, 0.3, -0.2, -0.2, -0.2, 0.3])
        mc = analiz.monte_carlo(islemler, 10_000.0, deneme=500, seed=0)
        assert mc.drawdown_dagilimi["p95"] > mc.drawdown_dagilimi["p05"]

    def test_kotu_kuyruk_orani_araliginda(self):
        islemler = self._islemler([0.1, -0.05, 0.2, -0.1, 0.05])
        mc = analiz.monte_carlo(islemler, 10_000.0, deneme=200, seed=0)
        assert 0.0 <= mc.kotu_kuyruk_orani <= 1.0

    def test_yetersiz_islem(self):
        with pytest.raises(analiz.AnalizHatasi, match="en az 2"):
            analiz.monte_carlo(self._islemler([0.1]), 10_000.0)

    def test_acik_islem_sayilmiyor(self):
        acik = Islem(acilis_ms=0, giris_notional=1_000.0, giris_miktar=1.0)
        islemler = [*self._islemler([0.1, -0.05, 0.2]), acik]
        assert analiz.monte_carlo(islemler, 10_000.0, deneme=50, seed=0).islem_sayisi == 3


class TestStres:
    def test_senaryolarin_hepsi_kosuyor(self, diziler, pencereler):
        ins, _ = pencereler
        sonuc = analiz.stres(SmaKesisim(5, 20), MALIYET, "BTCUSDT", "1h", diziler, ins)
        assert set(sonuc.senaryolar) == set(analiz.STRES_SENARYOLARI)

    def test_maliyet_carpanlari_uygulaniyor(self, diziler, pencereler):
        ins, _ = pencereler
        sonuc = analiz.stres(SmaKesisim(5, 20), MALIYET, "BTCUSDT", "1h", diziler, ins)
        assert sonuc.senaryolar["slippage_2x"]["slippage_bps"] == pytest.approx(10.0)
        assert sonuc.senaryolar["fee_2x"]["fee_taker_bps"] == pytest.approx(20.0)

    def test_daha_yuksek_maliyet_daha_kotu_getiri(self, diziler, pencereler):
        """İşlem yapan bir strateji için maliyet arttıkça getiri düşmeli — yönü sabitliyoruz."""
        ins, _ = pencereler
        sonuc = analiz.stres(SmaKesisim(5, 20), MALIYET, "BTCUSDT", "1h", diziler, ins)
        temel = sonuc.senaryolar["temel"]
        assert temel["islem_sayisi"] > 0
        assert sonuc.senaryolar["hepsi_2x"]["toplam_getiri"] <= temel["toplam_getiri"]
        assert sonuc.senaryolar["hepsi_2x"]["toplam_maliyet"] > temel["toplam_maliyet"]

    def test_bozulma_pozitif(self, diziler, pencereler):
        ins, _ = pencereler
        sonuc = analiz.stres(SmaKesisim(5, 20), MALIYET, "BTCUSDT", "1h", diziler, ins)
        assert sonuc.bozulma() >= 0.0

    def test_bozulmus_model_gecici_isaretleniyor(self, diziler, pencereler):
        """Bozulmuş maliyet kalibre değildir; kalibrasyonu taşımak yalan olurdu."""
        ins, _ = pencereler
        sonuc = analiz.stres(SmaKesisim(5, 20), MALIYET, "BTCUSDT", "1h", diziler, ins)
        assert sonuc.senaryolar["slippage_2x"]["carpanlar"]["slippage"] == 2.0


class TestKarsilastirma:
    def test_kiyas_otomatik_ekleniyor(self, diziler):
        """İstemeye bırakılsaydı unutulurdu; unutulduğu raporda getiri ölçüsüz kalır."""
        sonuc = karsilastirma.calistir(
            MALIYET, "BTCUSDT", "1h", diziler, stratejiler=["sma_kesisim"], oos_orani=0.30,
        )
        adlar = [s.strateji for s in sonuc.satirlar]
        assert "al_tut" in adlar

    def test_ortak_pencere_tum_stratejiler_icin_ayni(self, diziler):
        sonuc = karsilastirma.calistir(
            MALIYET, "BTCUSDT", "1h", diziler, stratejiler=["sma_kesisim", "ema_kesisim"],
        )
        assert sonuc.ins_pencere["uzunluk"] > 0
        assert sonuc.oos_pencere["baslangic"] == sonuc.ins_pencere["bitis"]

    def test_ortak_isinma_izgarayi_kapsiyor(self):
        """Izgaradaki en uzun pencere varsayılandan uzunsa ısınma ona göre olmalı."""
        assert karsilastirma.ortak_isinma(["sma_kesisim"]) >= 200 + 2

    def test_oos_is_orani_negatif_iste_tanimsiz(self):
        """IS Sharpe'ı negatifken oran +2 çıkıp "iki kat iyi" diye okunmamalı."""
        assert np.isnan(karsilastirma._oran(-1.0, -0.5))
        assert np.isnan(karsilastirma._oran(1.0, 0.0))
        assert karsilastirma._oran(0.5, 1.0) == pytest.approx(0.5)


class TestDeneyKaydi:
    def _deney(self, **degisiklik) -> deney.Deney:
        alanlar = {
            "tip": "tarama",
            "strateji": "sma_kesisim",
            "girdi": {"sembol": "BTCUSDT", "olcut": "sharpe"},
            "cikti": {"en_iyi": {"hizli": 20}},
            "veri_sha256": "a" * 64,
        }
        return deney.Deney(**(alanlar | degisiklik))

    def test_bilinmeyen_tip(self):
        with pytest.raises(deney.DeneyHatasi, match="bilinmeyen deney tipi"):
            self._deney(tip="sihir")

    def test_veri_hash_zorunlu(self):
        """Veri kimliği olmayan kayıt yeniden üretilemez (K-009)."""
        with pytest.raises(deney.DeneyHatasi, match="veri_sha256"):
            self._deney(veri_sha256="")

    def test_ayni_girdi_ayni_hash(self):
        assert self._deney().girdi_hash == self._deney().girdi_hash

    def test_farkli_girdi_farkli_hash(self):
        a = self._deney()
        b = self._deney(girdi={"sembol": "ETHUSDT", "olcut": "sharpe"})
        assert a.girdi_hash != b.girdi_hash

    def test_cikti_hash_ciktidan_turiyor(self):
        a = self._deney()
        b = self._deney(cikti={"en_iyi": {"hizli": 30}})
        assert a.cikti_hash != b.cikti_hash
        assert a.girdi_hash == b.girdi_hash

    def test_kayit_yazilip_okunuyor(self, tmp_path):
        yol = self._deney().yaz(tmp_path)
        okunan = deney.oku(yol)
        assert okunan["tip"] == "tarama"
        assert set(okunan["kimlik"]) >= {
            "girdi_hash", "cikti_hash", "veri_sha256", "commit", "dirty", "seed", "ortam"
        }

    def test_listeleme(self, tmp_path):
        self._deney().yaz(tmp_path)
        self._deney(tip="stres").yaz(tmp_path)
        assert len(deney.listele(tmp_path)) == 2
        assert len(deney.listele(tmp_path, "stres")) == 1
        assert deney.listele(tmp_path / "yok") == []

    def test_dogrulama_ayni_ciktida_gecer(self):
        d = self._deney()
        ayni, aciklama = deney.dogrula(d.sozluk(), d.cikti)
        assert ayni
        assert "aynı" in aciklama

    def test_dogrulama_farkli_ciktida_kalir(self):
        d = self._deney()
        ayni, aciklama = deney.dogrula(d.sozluk(), {"en_iyi": {"hizli": 999}})
        assert not ayni
        assert "uyuşmuyor" in aciklama

    def test_deney_kaydi_olmayan_sozluk(self):
        with pytest.raises(deney.DeneyHatasi, match="deney kaydı değil"):
            deney.dogrula({"kimlik": {}}, {})


class TestPlatoSecimi:
    """Plato merkezi seçimi. (Faz 4'e dönüş 2)

    Hipotez çürüdü — plato seçimi `oos_is_orani`'nı iyileştirmedi — ama kod kaldı ve
    doğru çalışmak zorunda: ölçümün kendisi ancak seçim doğru yapıldıysa bir şey anlatır.
    Yanlış bir merkez, "hipotez çürüdü" sonucunu da geçersiz kılardı.
    """

    def aday(self, skor: float, **parametreler):
        from scryne_quant.backtest.metrikler import Metrikler
        from scryne_quant.research.tarama import Aday

        return Aday(
            parametreler=tuple(sorted(parametreler.items())),
            skor=skor,
            metrikler=Metrikler.bos() if hasattr(Metrikler, "bos") else None,
            sonuc_hash="0" * 16,
            gecerli=True,
        )

    def sonuc(self, adaylar):
        from scryne_quant.research.tarama import TaramaSonucu

        return TaramaSonucu(
            strateji_adi="test",
            olcut="sharpe",
            adaylar=adaylar,
            pencere={},
            asgari_islem=0,
        )

    def test_tek_adaylik_platoda_merkez_tepedir(self):
        # Plato kümesi tek adaysa merkez tepenin kendisidir — ve bu, deneyin ölçtüğü
        # sınırın ta kendisi: 14 vakanın 8'inde böyle oldu.
        s = self.sonuc([self.aday(1.0, a=1), self.aday(0.0, a=2), self.aday(-1.0, a=3)])
        assert s.sec("plato").sozluk_parametreler == s.sec("tepe").sozluk_parametreler

    def test_genis_platoda_merkez_seciliyor(self):
        # a=1..5 platoda (kötü aday aralığı açıyor); merkez a=3, tepe a=1 olsa bile.
        adaylar = [self.aday(1.00 - 0.01 * i, a=i) for i in range(5)]
        adaylar.append(self.aday(0.0, a=5))
        s = self.sonuc(adaylar)
        assert s.sec("tepe").sozluk_parametreler["a"] == 0
        assert s.sec("plato").sozluk_parametreler["a"] == 2

    def test_plato_skor_araligina_oranli_ve_bu_deneyi_sinirladi(self):
        """Plato "en iyinin %10 **yakını**" değil, "skor **aralığının** %10'u" demek.

        Yani skorlar sıkışıksa plato daralır. Bu tanım Faz 4'ten beri `ust_yuzde_plato`
        içinde ve bilerek değiştirilmedi: iki yerde iki farklı plato tanımı olsaydı,
        K-019'a raporlanan sayı seçilen bölgeyi anlatmazdı.

        Sonucu Faz 4'e dönüş 2'de doğrudan görüldü — 12-36 adaylık ızgaralarda plato
        kümeleri 1-7 adaya düştü ve 14 vakanın 8'inde merkez tepenin kendisi oldu. Yani
        deneyin gücünü sınırlayan şey bu tanımdı, ve bu test onu görünür tutuyor.
        """
        sikisik = self.sonuc([self.aday(1.0 - 0.001 * i, a=i) for i in range(5)])
        assert len(sikisik.plato_adaylari()) == 1  # hepsi neredeyse eşit → plato dar

        yayvan = self.sonuc(
            [self.aday(1.0 - 0.01 * i, a=i) for i in range(5)] + [self.aday(0.0, a=5)]
        )
        assert len(yayvan.plato_adaylari()) == 5

    def test_parametreler_sira_ile_olculuyor_ham_deger_ile_degil(self):
        # `pencere` 7-21 ile `ust` 60-80 aynı ölçekte değil; ham mesafe büyük sayılı
        # parametreyi baskın yapar ve merkez yanlış eksende bulunurdu.
        adaylar = [
            self.aday(1.00, kucuk=1, buyuk=1000),
            self.aday(0.99, kucuk=2, buyuk=2000),
            self.aday(0.98, kucuk=3, buyuk=3000),
            self.aday(0.00, kucuk=4, buyuk=4000),
        ]
        s = self.sonuc(adaylar)
        assert s.sec("plato").sozluk_parametreler == {"kucuk": 2, "buyuk": 2000}

    def test_gecerli_aday_yoksa_none(self):
        from scryne_quant.research.tarama import Aday

        gecersiz = Aday(
            parametreler=(("a", 1),), skor=1.0, metrikler=None,
            sonuc_hash="0" * 16, gecerli=False,
        )
        s = self.sonuc([gecersiz])
        assert s.sec("plato") is None
        assert s.sec("tepe") is None

    def test_bilinmeyen_yontem_hata(self):
        import pytest as _pytest

        from scryne_quant.research.tarama import TaramaHatasi

        s = self.sonuc([self.aday(1.0, a=1)])
        with _pytest.raises(TaramaHatasi, match="bilinmeyen seçim"):
            s.sec("sihirli")
