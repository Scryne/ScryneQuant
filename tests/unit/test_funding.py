"""Funding verisi: doğrulama ve **nedensel** hizalama. (K-042, K-002)

Bu dosyanın asıl testi `TestNedensellik`. Funding 8 saatte bir, barlar 1 saatte bir; 8'e 1
yayarken yön yanlış seçilirse her bar, kendi gelecek funding'ini görür. O sızıntı
**sessizdir**: hiçbir şey çökmez, hiçbir test kırılmaz, backtest sadece fazla iyi çıkar.
Faz 4'ün tüm tablosunu çöpe atacak bir hata sınıfı ve tek savunması buradaki test.

Sentetik veri kullanılıyor, gerçek funding değil: gerçek veride her bar doğru cevabı
verse bile bu, kuralın doğru olduğunu değil o verinin şanslı olduğunu gösterirdi. Sentetik
seride funding değerleri **kasıtlı olarak birbirinden farklı** (0, 1, 2, ...), yani yanlış
bir hizalama gizlenemez.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scryne_quant.data.funding import (
    ORAN_TAVANI,
    PERIYOT_MS,
    FundingHatasi,
    barlara_hizala,
    dogrula,
)

SAAT_MS = 3_600_000
T0 = 1_600_000_000_000 // SAAT_MS * SAAT_MS  # saat sınırına oturtulmuş


def funding_serisi(n: int = 10, baslangic_ms: int = T0) -> pd.DataFrame:
    """Her kaydın oranı kendi sırasına eşit (ölçekli): yanlış hizalama görünür olsun."""
    return pd.DataFrame(
        {
            "funding_time": [baslangic_ms + i * PERIYOT_MS for i in range(n)],
            "funding_rate": [i * 1e-5 for i in range(n)],
        }
    )


def bar_serisi(n: int = 48, baslangic_ms: int = T0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time": [baslangic_ms + i * SAAT_MS for i in range(n)],
            "open": np.full(n, 100.0),
            "high": np.full(n, 101.0),
            "low": np.full(n, 99.0),
            "close": np.full(n, 100.5),
            "volume": np.full(n, 10.0),
            "quote_volume": np.full(n, 1000.0),
            "trades": np.arange(n, dtype="int64"),
            "quality_status": ["ok"] * n,
        }
    )


class TestNedensellik:
    """`t` barı yalnızca `funding_time <= t` olan kayıtları görebilir. (K-002, K-042/4)"""

    def test_her_bar_en_son_gerceklesmis_kaydi_goruyor(self) -> None:
        f, b = funding_serisi(6), bar_serisi(40)
        h = barlara_hizala(b, f)

        ft = f.funding_time.to_numpy()
        fr = f.funding_rate.to_numpy()
        idx = np.searchsorted(ft, h.open_time.to_numpy(), side="right") - 1
        beklenen = np.where(idx >= 0, fr[np.clip(idx, 0, None)], np.nan)

        assert np.allclose(h.funding.to_numpy(), beklenen, equal_nan=True), (
            "bir bar, kendisinden sonra gerçekleşmiş bir funding kaydını görüyor. "
            "Bu look-ahead'dir ve backtest sonuçlarını sessizce iyileştirir (K-002)."
        )

    def test_funding_anindaki_bar_o_kaydi_goruyor(self) -> None:
        """`funding_time == open_time` dahildir: o anda ödeme gerçekleşmiştir."""
        f, b = funding_serisi(3), bar_serisi(24)
        h = barlara_hizala(b, f)
        tam_bar = h[h.open_time == f.funding_time.iloc[1]]
        assert len(tam_bar) == 1
        assert tam_bar.funding.iloc[0] == pytest.approx(f.funding_rate.iloc[1])

    def test_funding_oncesi_barlar_nan(self) -> None:
        """Isınma penceresinde değer uydurulmaz (K-024)."""
        f = funding_serisi(3, baslangic_ms=T0 + 10 * SAAT_MS)
        h = barlara_hizala(bar_serisi(24), f)
        onceki = h[h.open_time < f.funding_time.iloc[0]]
        assert len(onceki) == 10
        assert onceki.funding.isna().all()

    def test_gelecek_funding_bozulunca_gecmis_degismiyor(self) -> None:
        """Bozulmuş-gelecek testinin funding hâli. `test_look_ahead.py` ile aynı kalıp.

        Son iki funding kaydı tanınmayacak kadar değiştiriliyor; ilk barların gördüğü
        değerler bit düzeyinde aynı kalmalı.
        """
        f, b = funding_serisi(6), bar_serisi(40)
        temiz = barlara_hizala(b, f).funding.to_numpy()

        bozuk_f = f.copy()
        bozuk_f.loc[4:, "funding_rate"] = -0.003
        bozuk = barlara_hizala(b, bozuk_f).funding.to_numpy()

        sinir = int(f.funding_time.iloc[4])
        maske = b.open_time.to_numpy() < sinir
        assert np.array_equal(temiz[maske], bozuk[maske], equal_nan=True), (
            "geleceği bozmak geçmişi değiştirdi — hizalama nedensel değil"
        )

    def test_sutun_cakismasi_hata(self) -> None:
        b = bar_serisi(4)
        b["funding"] = 0.0
        with pytest.raises(FundingHatasi, match="zaten var"):
            barlara_hizala(b, funding_serisi(2))

    def test_girdi_cercevesi_degismiyor(self) -> None:
        """Bar çerçevesi hem özellik hesabına hem ctx'e gidiyor; yerinde değişim yayılır."""
        b = bar_serisi(8)
        once = b.copy(deep=True)
        barlara_hizala(b, funding_serisi(2))
        pd.testing.assert_frame_equal(b, once)


class TestDogrulama:
    """Bozukluk düzeltilmez, hata verilir (K-006 ile aynı felsefe)."""

    def test_temiz_seri_rapor_uretiyor(self) -> None:
        rapor = dogrula(funding_serisi(10))
        assert rapor["kayit"] == 10
        assert rapor["anormal_aralik"] == 0
        assert rapor["periyot_medyan_saat"] == pytest.approx(8.0)

    def test_tekrar_eden_zaman_hata(self) -> None:
        f = funding_serisi(4)
        f.loc[2, "funding_time"] = int(f.funding_time.iloc[1])
        with pytest.raises(FundingHatasi, match="artan ve tekil"):
            dogrula(f)

    def test_tavan_disi_oran_hata(self) -> None:
        """±%0,3 Binance'in tavanı; dışına taşan bir değer veri hatasıdır."""
        f = funding_serisi(4)
        f.loc[2, "funding_rate"] = ORAN_TAVANI * 2
        with pytest.raises(FundingHatasi, match="tavanının dışında"):
            dogrula(f)

    def test_bos_oran_hata(self) -> None:
        f = funding_serisi(4)
        f.loc[1, "funding_rate"] = np.nan
        with pytest.raises(FundingHatasi, match="boş"):
            dogrula(f)

    def test_anormal_aralik_raporlaniyor_ama_hata_degil(self) -> None:
        """Bir boşluk veriyi geçersiz kılmaz; sayılır ve rapora girer.

        Faz 1'in dersi: gerçek veride boşluk **vardı** (2023-03 Binance kesintisi) ve
        doğru davranış onu görünür kılmaktı, koşuyu durdurmak değil.
        """
        f = funding_serisi(5)
        f.loc[3:, "funding_time"] += PERIYOT_MS  # bir periyot atlanmış
        rapor = dogrula(f)
        assert rapor["anormal_aralik"] == 1
        assert len(rapor["anormal_ornekler"]) == 1

    def test_bos_cerceve_hata(self) -> None:
        with pytest.raises(FundingHatasi, match="boş"):
            dogrula(pd.DataFrame(columns=["funding_time", "funding_rate"]))


class TestGercekVeri:
    """Depoda gerçek veri varsa onun üzerinde de ölçülür; yoksa test atlanır.

    Sentetik test kuralı ölçüyor, bu test **verinin kendisini**. İkisi farklı sorular:
    biri "kod doğru mu", diğeri "elimizdeki veri kullanılabilir mi".
    """

    def test_depodaki_funding_temiz(self) -> None:
        from scryne_quant.data.funding import oku

        try:
            f = oku("BTCUSDT")
        except FundingHatasi:
            pytest.skip("funding verisi indirilmemiş (`sq funding indir`)")

        rapor = dogrula(f)
        assert rapor["anormal_aralik"] == 0, rapor["anormal_ornekler"]
        assert rapor["kapsam_gun"] > 2_000, "kapsam 5,2 yıllık bar setini kaplamıyor"
