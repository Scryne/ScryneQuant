"""Motor davranışı: fill semantiği, portföy değişmezleri, kalite kuralı. (K-004, K-006, K-007)

`test_backtest_referans.py` motorun **aritmetiğini** bağımsız bir referansa karşı ölçüyor.
Bu dosya **kurallarını** ölçüyor: hangi barda dolar, hangi yöne kayar, ne zaman atlar.
İkisi ayrı çünkü bir motor doğru aritmetikle yanlış barda da dolabilir.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.backtest.fill import (
    AtlamaSebebi,
    IslemYonu,
    emir_hazirla,
    fill_fiyati,
)
from scryne_quant.backtest.motor import Backtest, BacktestHatasi
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.portfolio.durum import Portfoy, PortfoyHatasi
from scryne_quant.strategy.sinyal import Sinyal, Yon
from tests.conftest import PlanliStrateji

BAR_MS = 3_600_000
BASLANGIC_MS = 1_699_999_200_000
MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
SIFIR_MALIYET = MaliyetModeli(fee_taker_bps=0.0, slippage_bps=0.0)


def diziler(
    acilis: list[float],
    kapanis: list[float] | None = None,
    kalite: list[str] | None = None,
) -> dict[str, np.ndarray]:
    """Elle kurulmuş bar dizileri. `kapanis` verilmezse açılışla aynı."""
    n = len(acilis)
    k = kapanis if kapanis is not None else list(acilis)
    out = {
        "open_time": np.array([BASLANGIC_MS + i * BAR_MS for i in range(n)], dtype="int64"),
        "open": np.array(acilis, dtype="float64"),
        "high": np.array([max(a, c) + 1 for a, c in zip(acilis, k, strict=True)], dtype="float64"),
        "low": np.array([min(a, c) - 1 for a, c in zip(acilis, k, strict=True)], dtype="float64"),
        "close": np.array(k, dtype="float64"),
        "volume": np.full(n, 10.0),
        "quote_volume": np.array([a * 10 for a in acilis], dtype="float64"),
        "trades": np.full(n, 100, dtype="int64"),
        "quality_status": np.array(kalite or [KaliteDurumu.OK] * n, dtype=object),
    }
    for d in out.values():
        d.flags.writeable = False
    return out


def _sinyal(hedef: float, zaman: int = BASLANGIC_MS) -> Sinyal:
    return Sinyal(
        symbol="BTCUSDT",
        side=Yon.BUY if hedef > 0 else Yon.FLAT,
        target_exposure=hedef,
        confidence=1.0,
        reason="TEST",
        timestamp=zaman,
    )


class TestFillSemantigi:
    """K-004: fill `t+1` açılışındadır, sinyal barının kapanışında değil."""

    def test_fill_sonraki_barin_acilisindan(self):
        """Dört olası fiyatın hepsi farklı: yanlış olan hangisiyse ayırt edilebilsin.

        Bu vakanın ilk hâli **hatalıydı** ve mutasyon testinde yakalandı: fill barının
        açılışı ile kapanışı aynı sayıydı, dolayısıyla "kapanıştan doldur" hatası testi
        kırmıyordu. Yeşil ama hiçbir şey kanıtlamayan test, testsizlikten daha kötüdür —
        koruma sanılır.

        `test_backtest_referans.py`'deki senaryo gerçekçi olsun diye `close[i]=open[i+1]`
        kullanıyor; bu, bir bar kaymasını zayıf yakalar. Buradaki vaka o boşluğu kapatır.
        """
        # Sermaye 20.000. Sinyal bar 0'da üretilir, bar 1'de dolar.
        #   doğru      → open[1]  = 20.000 → 1,0 birim
        #   kapanıştan → close[1] = 40.000 → 0,5 birim
        #   sinyal barının kapanışından → close[0] = 99.000 → 0,202 birim
        #   sinyal barının açılışından  → open[0]  = 10.000 → 2,0 birim
        d = diziler(acilis=[10_000, 20_000, 30_000], kapanis=[99_000, 40_000, 30_000])
        sonuc = Backtest(
            PlanliStrateji({0: ("BUY", 1.0)}), SIFIR_MALIYET, baslangic_sermaye=20_000.0
        ).calistir("BTCUSDT", "1h", d)

        islem = sonuc.islemler[0]
        assert islem.giris_miktar == pytest.approx(1.0)
        assert islem.giris_notional == pytest.approx(20_000.0)
        assert islem.acilis_ms == BASLANGIC_MS + BAR_MS

    def test_son_barin_sinyali_dolmaz(self):
        """Dolacağı bar yok. Kendi kapanışından doldurmak K-004'ün yasağı."""
        d = diziler([100.0, 100.0, 100.0])
        sonuc = Backtest(PlanliStrateji({2: ("BUY", 1.0)}), MALIYET).calistir("BTCUSDT", "1h", d)
        assert sonuc.uretilen_sinyal == 1
        assert sonuc.atlanan[AtlamaSebebi.SONRAKI_BAR_YOK] == 1
        assert not sonuc.islemler

    def test_cikis_da_sonraki_barin_acilisindan(self):
        """Giriş kadar çıkış da `t+1` açılışında. Çıkışta bir bar kayması kârı şişirir."""
        # Bar 1'de gir (açılış 10.000), bar 2'de FLAT sinyali, bar 3'te çık (açılış 12.000).
        d = diziler(
            acilis=[10_000, 10_000, 11_000, 12_000, 12_000],
            kapanis=[10_000, 11_000, 50_000, 12_000, 12_000],
        )
        sonuc = Backtest(
            PlanliStrateji({0: ("BUY", 1.0), 2: ("FLAT", 0.0)}),
            SIFIR_MALIYET,
            baslangic_sermaye=10_000.0,
        ).calistir("BTCUSDT", "1h", d)

        islem = sonuc.islemler[0]
        assert islem.giris_notional == pytest.approx(10_000.0)  # open[1]
        assert islem.cikis_notional == pytest.approx(12_000.0)  # open[3], close[2]=50.000 değil
        assert islem.net_pnl == pytest.approx(2_000.0)


class TestSlippageYonu:
    """K-007: slippage her zaman aleyhte."""

    def test_alista_yukari_satista_asagi(self):
        assert fill_fiyati(100.0, IslemYonu.AL, MALIYET) == pytest.approx(100.05)
        assert fill_fiyati(100.0, IslemYonu.SAT, MALIYET) == pytest.approx(99.95)

    def test_slippage_maliyeti_pozitif(self):
        p = Portfoy(nakit=10_000.0)
        emir = emir_hazirla(_sinyal(1.0), p, 100.0, BASLANGIC_MS, MALIYET)
        assert not isinstance(emir, AtlamaSebebi)
        assert emir.slippage_maliyeti > 0.0
        assert emir.fiyat > emir.referans_fiyat

    def test_sifir_slippage_fiyati_kaydirmaz(self):
        assert fill_fiyati(100.0, IslemYonu.AL, SIFIR_MALIYET) == 100.0

    def test_maliyet_her_zaman_zarar_yazar(self):
        """Fiyat hiç değişmese bile bir gidiş-dönüş para kaybettirmeli."""
        d = diziler([100.0] * 6)
        sonuc = Backtest(
            PlanliStrateji({0: ("BUY", 1.0), 2: ("FLAT", 0.0)}), MALIYET
        ).calistir("BTCUSDT", "1h", d)
        assert sonuc.metrikler.islem_sayisi == 1
        assert sonuc.islemler[0].net_pnl < 0.0
        assert sonuc.metrikler.bitis_sermaye < sonuc.metrikler.baslangic_sermaye


class TestKaliteKurali:
    """K-006 / K-028: `ok` olmayan barda ne karar verilir ne fill yapılır."""

    def test_ok_olmayan_barda_fill_yok(self):
        d = diziler(
            [100.0] * 4,
            kalite=[KaliteDurumu.OK, KaliteDurumu.SUSPECT, KaliteDurumu.OK, KaliteDurumu.OK],
        )
        sonuc = Backtest(PlanliStrateji({0: ("BUY", 1.0)}), MALIYET).calistir("BTCUSDT", "1h", d)
        assert sonuc.atlanan[AtlamaSebebi.FILL_BARI_OK_DEGIL] == 1
        assert not sonuc.islemler

    def test_ok_olmayan_barda_karar_yok(self):
        d = diziler(
            [100.0] * 4,
            kalite=[KaliteDurumu.OK, KaliteDurumu.GAP, KaliteDurumu.OK, KaliteDurumu.OK],
        )
        sonuc = Backtest(PlanliStrateji({1: ("BUY", 1.0)}), MALIYET).calistir("BTCUSDT", "1h", d)
        assert sonuc.uretilen_sinyal == 0, "şüpheli barda strateji çağrılmamalı"

    def test_kalite_orani_kayitta(self):
        d = diziler([100.0] * 4, kalite=[KaliteDurumu.OK] * 3 + [KaliteDurumu.SUSPECT])
        sonuc = Backtest(PlanliStrateji({}), MALIYET).calistir("BTCUSDT", "1h", d)
        assert sonuc.veri.ok_olmayan_bar == 1
        assert sonuc.veri.ok_olmayan_oran == pytest.approx(0.25)
        assert sonuc.data_quality_warning
        assert "data_quality_warning" in sonuc.promotion_engelleri

    def test_esik_altinda_uyari_yok(self):
        d = diziler([100.0] * 200, kalite=[KaliteDurumu.OK] * 200)
        sonuc = Backtest(PlanliStrateji({}), MALIYET).calistir("BTCUSDT", "1h", d)
        assert not sonuc.data_quality_warning

    def test_gecici_maliyet_modeli_promotion_engeli(self):
        """K-021: kalibre edilmemiş maliyetle üretilen sonuç promotion'a giremez."""
        d = diziler([100.0] * 5)
        sonuc = Backtest(PlanliStrateji({}), MALIYET).calistir("BTCUSDT", "1h", d)
        assert MALIYET.gecici
        assert "gecici_maliyet_modeli" in sonuc.promotion_engelleri


class TestBoyutlandirma:
    def test_flat_pozisyonu_tam_kapatir(self):
        d = diziler([100.0, 110.0, 120.0, 130.0])
        sonuc = Backtest(
            PlanliStrateji({0: ("BUY", 1.0), 1: ("FLAT", 0.0)}), MALIYET
        ).calistir("BTCUSDT", "1h", d)
        assert not sonuc.acik_pozisyon_sonda
        assert sonuc.islemler[0].kapali
        assert sonuc.metrikler.azami_maruziyet <= 1.0

    def test_nakitten_fazlasi_harcanmaz(self):
        p = Portfoy(nakit=1_000.0)
        emir = emir_hazirla(_sinyal(1.0), p, 100.0, BASLANGIC_MS, MALIYET)
        assert not isinstance(emir, AtlamaSebebi)
        assert emir.notional + emir.komisyon <= 1_000.0 + 1e-9

    def test_elde_olandan_fazlasi_satilmaz(self):
        p = Portfoy(nakit=0.0, miktar=1.0, ortalama_maliyet=100.0)
        emir = emir_hazirla(_sinyal(0.0), p, 100.0, BASLANGIC_MS, MALIYET)
        assert not isinstance(emir, AtlamaSebebi)
        assert emir.miktar <= 1.0 + 1e-12

    def test_hedef_tutturulmussa_islem_yok(self):
        p = Portfoy(nakit=0.0, miktar=0.0)
        assert emir_hazirla(_sinyal(0.0), p, 100.0, BASLANGIC_MS, MALIYET) is (
            AtlamaSebebi.HEDEF_ZATEN_TUTTURULMUS
        )

    def test_nakit_yoksa_alim_atlanir(self):
        p = Portfoy(nakit=0.0, miktar=1.0, ortalama_maliyet=100.0)
        # Hedef %100 ama pozisyon zaten %100 → fark sıfır; hedefi aşmak için 1.0 üstü yok.
        sonuc = emir_hazirla(_sinyal(1.0), p, 100.0, BASLANGIC_MS, MALIYET)
        assert sonuc is AtlamaSebebi.HEDEF_ZATEN_TUTTURULMUS

    def test_gecersiz_acilis_fiyati(self):
        with pytest.raises(ValueError, match="açılış"):
            emir_hazirla(_sinyal(1.0), Portfoy(nakit=100.0), 0.0, BASLANGIC_MS, MALIYET)


class TestPortfoyDegismezleri:
    """Spot v1: negatif nakit yok (kaldıraç), negatif miktar yok (açığa satış)."""

    def test_negatif_nakit_reddediliyor(self):
        with pytest.raises(PortfoyHatasi, match="kaldıraç"):
            Portfoy(nakit=-1.0)

    def test_negatif_miktar_reddediliyor(self):
        with pytest.raises(PortfoyHatasi, match="açığa satış"):
            Portfoy(nakit=100.0, miktar=-1.0)

    def test_yetersiz_nakitle_alim_reddediliyor(self):
        with pytest.raises(PortfoyHatasi, match="yetersiz nakit"):
            Portfoy(nakit=100.0).al(2.0, 100.0, 0.2, BASLANGIC_MS)

    def test_elde_olmayani_satmak_reddediliyor(self):
        with pytest.raises(PortfoyHatasi, match="elde yok"):
            Portfoy(nakit=0.0, miktar=1.0, ortalama_maliyet=100.0).sat(2.0, 100.0, 0.2)

    def test_ortalama_maliyet_komisyon_dahil(self):
        p = Portfoy(nakit=1_000.0).al(1.0, 100.0, 10.0, BASLANGIC_MS)
        assert p.ortalama_maliyet == pytest.approx(110.0)
        assert p.nakit == pytest.approx(890.0)

    def test_iki_alimda_ortalama_maliyet(self):
        p = Portfoy(nakit=1_000.0).al(1.0, 100.0, 0.0, BASLANGIC_MS)
        p = p.al(1.0, 200.0, 0.0, BASLANGIC_MS + BAR_MS)
        assert p.ortalama_maliyet == pytest.approx(150.0)
        assert p.giris_ms == BASLANGIC_MS, "giriş zamanı ilk alımda sabitlenmeli"

    def test_gerceklesen_pnl(self):
        p = Portfoy(nakit=1_000.0).al(1.0, 100.0, 1.0, BASLANGIC_MS)
        p, pnl = p.sat(1.0, 150.0, 1.5)
        # Hasılat 150 − 1,5 = 148,5; maliyet 101 → 47,5
        assert pnl == pytest.approx(47.5)
        assert not p.acik
        assert p.ortalama_maliyet == 0.0
        assert p.giris_ms is None

    def test_kismi_satista_maliyet_korunuyor(self):
        p = Portfoy(nakit=1_000.0).al(2.0, 100.0, 0.0, BASLANGIC_MS)
        p, _ = p.sat(1.0, 150.0, 0.0)
        assert p.miktar == pytest.approx(1.0)
        assert p.ortalama_maliyet == pytest.approx(100.0)
        assert p.giris_ms == BASLANGIC_MS

    def test_maruziyet_olcegi(self):
        p = Portfoy(nakit=500.0, miktar=5.0, ortalama_maliyet=100.0)
        assert p.maruziyet(100.0) == pytest.approx(0.5)
        assert p.ozkaynak(100.0) == pytest.approx(1_000.0)

    def test_bos_portfoyde_maruziyet_sifir(self):
        assert Portfoy(nakit=0.0).maruziyet(100.0) == 0.0


class TestKurulum:
    def test_tek_bar_reddediliyor(self):
        with pytest.raises(BacktestHatasi, match="en az 2 bar"):
            Backtest(PlanliStrateji({}), MALIYET).calistir("BTCUSDT", "1h", diziler([100.0]))

    def test_negatif_sermaye_reddediliyor(self):
        with pytest.raises(BacktestHatasi, match="pozitif"):
            Backtest(PlanliStrateji({}), MALIYET, baslangic_sermaye=0.0)

    def test_islemsiz_kosu_gecerli_sonuc_verir(self):
        motor = Backtest(PlanliStrateji({}), MALIYET)
        sonuc = motor.calistir("BTCUSDT", "1h", diziler([100.0] * 5))
        assert sonuc.metrikler.islem_sayisi == 0
        assert sonuc.metrikler.bitis_sermaye == pytest.approx(sonuc.metrikler.baslangic_sermaye)
        assert sonuc.metrikler.max_drawdown == 0.0
        assert sonuc.metrikler.profit_factor == 0.0

    def test_sonda_acik_pozisyon_isaretleniyor(self):
        d = diziler([100.0] * 5)
        sonuc = Backtest(PlanliStrateji({0: ("BUY", 1.0)}), MALIYET).calistir("BTCUSDT", "1h", d)
        assert sonuc.acik_pozisyon_sonda
        assert not sonuc.islemler[0].kapali
        assert sonuc.metrikler.islem_sayisi == 0, "kapanmamış tur metriklere girmemeli"

    def test_equity_egrisi_bar_basina_bir_nokta(self):
        d = diziler([100.0] * 7)
        sonuc = Backtest(PlanliStrateji({}), MALIYET).calistir("BTCUSDT", "1h", d)
        assert sonuc.ozkaynak.size == 7
        assert sonuc.maruziyet.size == 7
        assert sonuc.zamanlar.size == 7
