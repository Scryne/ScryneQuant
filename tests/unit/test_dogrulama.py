"""Kalite bayrakları — yapay bozuk fixture'larla. (K-006, Faz 1 bitti kriteri)

**Bu dosyanın var olma sebebi bir ölçüm:** Spike 2, 3 yıllık 1h (26.281 bar) ve 1 yıllık
1m (525.601 bar) gerçek BTC/USDT verisinde tek bir eksik bar, tek bir tekrar eden
timestamp, tek bir OHLC tutarsızlığı, tek bir sıfır-hacimli bar bulamadı. Yani `gap`,
`duplicate` ve `suspect` kod yolları gerçek veriyle **hiç çalışmayacak.**

Hiç çalıştırılmamış bir güvenlik mekanizmasına güvenmek, o mekanizmanın hiç olmamasından
beterdir: yokluğu bilinir, bozukluğu bilinmez. Aşağıdaki her test bir kuralı kasten
tetikler.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.dogrulama import DogrulamaHatasi, dogrula, rapor_cikar
from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI, KaliteDurumu
from tests.conftest import bar_uret


def ham(n: int = 50, **kw) -> pd.DataFrame:
    """Bayraksız (ham) sentetik bar serisi — doğrulamanın girdisi."""
    return bar_uret(n=n, **kw).loc[:, list(HAM_BAR_SUTUNLARI)]


class TestTemizVeri:
    def test_hepsi_ok(self):
        df, rapor = dogrula(ham(100), "1h", sembol="BTCUSDT")
        assert (df["quality_status"] == KaliteDurumu.OK).all()
        assert rapor.kusursuz
        assert rapor.ok_orani == 1.0
        assert rapor.eksik_bar == 0
        assert rapor.bosluk_sayisi == 0

    def test_bayrak_sutunu_ekleniyor(self):
        df, _ = dogrula(ham(10), "1h")
        assert "quality_status" in df.columns
        assert list(df.columns)[:-1] == list(HAM_BAR_SUTUNLARI)

    def test_bos_girdi_bos_rapor(self):
        df, rapor = dogrula(ham(5).iloc[0:0], "1h")
        assert df.empty
        assert rapor.bar_sayisi == 0
        # Boş veri "kusursuz" değildir; ok_orani 0.0, kusursuz False.
        assert rapor.ok_orani == 0.0
        assert not rapor.kusursuz


class TestGap:
    """Boşluk: eksik barlardan **sonraki** bar işaretlenir, sentetik satır üretilmez."""

    def test_tek_boslugun_sonrasi_isaretlenir(self):
        veri = ham(20)
        eksiltilmis = veri.drop(index=[5, 6, 7]).reset_index(drop=True)

        df, rapor = dogrula(eksiltilmis, "1h")

        # Boşluktan sonraki bar (eski index 8, yeni index 5) gap.
        assert df.loc[5, "quality_status"] == KaliteDurumu.GAP
        assert (df.drop(index=5)["quality_status"] == KaliteDurumu.OK).all()
        assert rapor.bosluk_sayisi == 1
        assert rapor.eksik_bar == 3
        assert rapor.bosluklar[0].eksik_bar == 3

    def test_bosluk_satiri_uydurulmuyor(self):
        """Eksik bar için satır üretmek, olmayan bir fiyatı varmış gibi göstermek olurdu."""
        veri = ham(20).drop(index=[10]).reset_index(drop=True)
        df, rapor = dogrula(veri, "1h")
        assert len(df) == 19
        assert rapor.beklenen_bar == 20
        assert rapor.kapsama == pytest.approx(19 / 20)

    def test_cok_bosluk(self):
        veri = ham(60).drop(index=[10, 11, 30, 45, 46, 47, 48]).reset_index(drop=True)
        df, rapor = dogrula(veri, "1h")
        assert rapor.bosluk_sayisi == 3
        assert rapor.eksik_bar == 7
        assert (df["quality_status"] == KaliteDurumu.GAP).sum() == 3

    def test_bosluk_araligi_dogru(self):
        adim = timeframe_ms("1h")
        veri = ham(20)
        beklenen_bas = int(veri.loc[5, "open_time"])
        beklenen_bit = int(veri.loc[8, "open_time"])
        _, rapor = dogrula(veri.drop(index=[5, 6, 7]).reset_index(drop=True), "1h")

        b = rapor.bosluklar[0]
        assert (b.baslangic_ms, b.bitis_ms) == (beklenen_bas, beklenen_bit)
        assert b.eksik_bar == (b.bitis_ms - b.baslangic_ms) // adim


class TestDuplicate:
    def test_tekrar_eden_timestamp_isaretlenir(self):
        veri = ham(20)
        tekrar = pd.concat([veri, veri.iloc[[7]]], ignore_index=True)

        df, rapor = dogrula(tekrar, "1h")

        assert len(df) == 20  # tekilleştirildi
        assert df.loc[7, "quality_status"] == KaliteDurumu.DUPLICATE
        assert rapor.bayraklar[KaliteDurumu.DUPLICATE] == 1

    def test_son_kayit_tutulur(self):
        """Çakışmada sonraki çağrı kazanır — depo ile aynı kural (`keep='last'`)."""
        veri = ham(20)
        duzeltme = veri.iloc[[7]].copy()
        duzeltme["close"] = 12_345.0
        df, _ = dogrula(pd.concat([veri, duzeltme], ignore_index=True), "1h")
        assert df.loc[7, "close"] == 12_345.0

    def test_bayrak_tekrar_sayisindan_bagimsiz(self):
        veri = ham(20)
        uc_kez = pd.concat([veri, veri.iloc[[3]], veri.iloc[[3]]], ignore_index=True)
        df, _ = dogrula(uc_kez, "1h")
        assert len(df) == 20
        assert df.loc[3, "quality_status"] == KaliteDurumu.DUPLICATE


class TestSuspect:
    """Her `suspect` kuralı ayrı ayrı tetikleniyor — hiçbiri ölü kod kalmasın."""

    @pytest.mark.parametrize(
        ("neden", "sutun", "deger"),
        [
            ("high_low_ters", "high", 1.0),  # high, low'un çok altına iner
            ("sifir_hacim", "volume", 0.0),
            ("pozitif_olmayan_fiyat", "low", 0.0),
            ("negatif_hacim", "quote_volume", -1.0),
            ("islemsiz_hacim", "trades", 0),
        ],
    )
    def test_kural_tetikleniyor(self, neden, sutun, deger):
        veri = ham(20)
        veri.loc[5, sutun] = deger
        df, rapor = dogrula(veri, "1h")

        assert df.loc[5, "quality_status"] == KaliteDurumu.SUSPECT
        assert neden in rapor.suspect_nedenleri
        assert rapor.suspect_nedenleri[neden] >= 1

    def test_high_govdeyi_kapsamiyor(self):
        veri = ham(20)
        veri.loc[5, "high"] = min(veri.loc[5, "open"], veri.loc[5, "close"]) - 1.0
        df, rapor = dogrula(veri, "1h")
        assert df.loc[5, "quality_status"] == KaliteDurumu.SUSPECT
        assert "high_govdeyi_kapsamiyor" in rapor.suspect_nedenleri

    def test_low_govdeyi_kapsamiyor(self):
        veri = ham(20)
        veri.loc[5, "low"] = max(veri.loc[5, "open"], veri.loc[5, "close"]) + 1.0
        df, rapor = dogrula(veri, "1h")
        assert df.loc[5, "quality_status"] == KaliteDurumu.SUSPECT
        assert "low_govdeyi_kapsamiyor" in rapor.suspect_nedenleri

    def test_sonlu_olmayan_deger(self):
        veri = ham(20)
        veri.loc[5, "close"] = np.nan
        df, rapor = dogrula(veri, "1h")
        assert df.loc[5, "quality_status"] == KaliteDurumu.SUSPECT
        assert "sonlu_olmayan" in rapor.suspect_nedenleri

    def test_asiri_hareket(self):
        """Ondalık kayması gibi bozulmalar; oynaklık değil."""
        veri = ham(20)
        veri.loc[10, ["open", "high", "low", "close"]] *= 10  # bir hane kaymış fiyat
        df, rapor = dogrula(veri, "1h")
        assert df.loc[10, "quality_status"] == KaliteDurumu.SUSPECT
        assert rapor.suspect_nedenleri["asiri_hareket"] >= 1

    def test_gercekci_oynaklik_suspect_degil(self):
        """%5'lik bir saatlik hareket gerçektir (Spike 2: 3 yılda max 533 bps) — atılamaz.

        Eşiği piyasa hareketine yaklaştırmak, kriz dönemlerini veri setinden silen bir
        bias üretirdi.
        """
        veri = ham(20)
        veri.loc[10, ["open", "high", "low", "close"]] *= 1.05
        df, _ = dogrula(veri, "1h")
        assert df.loc[10, "quality_status"] == KaliteDurumu.OK

    def test_esik_ayarlanabilir(self):
        veri = ham(20)
        veri.loc[10, ["open", "high", "low", "close"]] *= 1.05
        df, _ = dogrula(veri, "1h", asiri_hareket_bps=100.0)
        assert df.loc[10, "quality_status"] == KaliteDurumu.SUSPECT


class TestOncelik:
    """Bayrak tekildir: suspect > gap > duplicate > backfilled > ok."""

    def test_suspect_gapi_ezer(self):
        veri = ham(20).drop(index=[5, 6]).reset_index(drop=True)
        veri.loc[5, "volume"] = 0.0  # boşluktan sonraki bar aynı zamanda şüpheli
        df, _ = dogrula(veri, "1h")
        assert df.loc[5, "quality_status"] == KaliteDurumu.SUSPECT

    def test_gap_duplicatei_ezer(self):
        veri = ham(20).drop(index=[5, 6]).reset_index(drop=True)
        tekrar = pd.concat([veri, veri.iloc[[5]]], ignore_index=True)
        df, _ = dogrula(tekrar, "1h")
        assert df.loc[5, "quality_status"] == KaliteDurumu.GAP

    def test_backfill_temiz_bari_isaretler(self):
        df, rapor = dogrula(ham(10), "1h", backfill=True)
        assert (df["quality_status"] == KaliteDurumu.BACKFILLED).all()
        assert rapor.ok_sayisi == 0

    def test_backfill_suspecti_ezmez(self):
        veri = ham(10)
        veri.loc[3, "volume"] = 0.0
        df, _ = dogrula(veri, "1h", backfill=True)
        assert df.loc[3, "quality_status"] == KaliteDurumu.SUSPECT


class TestSozlesmeIhlalleri:
    def test_hizasiz_timestamp_reddedilir(self):
        """K-005: bar timestamp'i epoch'a hizalı açılış zamanıdır.

        Hizasızlık tek barın kusuru değil, serinin yanlış hizalanmış olmasıdır. `suspect`
        deyip devam etmek, yanlış bir zaman eksenini "biraz şüpheli veri" diye kaydetmek
        olurdu.
        """
        veri = ham(10)
        veri["open_time"] = veri["open_time"] + 1
        with pytest.raises(DogrulamaHatasi, match="hizalı değil"):
            dogrula(veri, "1h")

    def test_eksik_sutun_reddedilir(self):
        with pytest.raises(DogrulamaHatasi, match="eksik sütun"):
            dogrula(ham(10).drop(columns=["trades"]), "1h")

    def test_bilinmeyen_timeframe(self):
        from scryne_quant.common.zaman import GecersizTimeframe

        with pytest.raises(GecersizTimeframe):
            dogrula(ham(10), "7h")


class TestDeterminizm:
    def test_ayni_girdi_ayni_bayrak(self):
        veri = ham(200).drop(index=[7, 8, 50]).reset_index(drop=True)
        veri.loc[100, "volume"] = 0.0
        a, ra = dogrula(veri, "1h")
        b, rb = dogrula(veri, "1h")
        pd.testing.assert_frame_equal(a, b)
        assert ra.sozluk() == rb.sozluk()

    def test_satir_sirasi_bayragi_degistirmez(self):
        """Barlar karışık gelse de bayrak aynı — sıralama doğrulamadan önce yapılıyor."""
        veri = ham(100).drop(index=[7, 8]).reset_index(drop=True)
        duz, _ = dogrula(veri, "1h")
        karisik, _ = dogrula(veri.sample(frac=1, random_state=3).reset_index(drop=True), "1h")
        pd.testing.assert_frame_equal(duz, karisik)


class TestRaporCikar:
    """`data quality` komutunun yolu: bayrağı yeniden hesaplamaz, mevcut olanı sayar."""

    def test_depodan_okunan_veriyi_sayar(self):
        veri = ham(50).drop(index=[10, 11]).reset_index(drop=True)
        bayrakli, ilk = dogrula(veri, "1h", sembol="BTCUSDT")

        ikinci = rapor_cikar(bayrakli, "1h", sembol="BTCUSDT")

        assert ikinci.bayraklar == ilk.bayraklar
        assert ikinci.bosluk_sayisi == ilk.bosluk_sayisi
        assert ikinci.eksik_bar == ilk.eksik_bar

    def test_bayraksiz_veri_reddedilir(self):
        with pytest.raises(DogrulamaHatasi, match="quality_status"):
            rapor_cikar(ham(10), "1h")
