"""Canlı akış sözleşmesi, bayat-veri guard'ı ve kayan pencere. (Faz 6, §24, K-006)

Roadmap'in Faz 6 kriterlerinden biri: *"Veri akışı kesildiğinde yeni pozisyon
açılmıyor (stale-data guard testi)."* Bu dosya guard'ın **ölçüm** tarafını test ediyor;
guard'ın karara etkisi `test_paper_dongu.py`de.

Buradaki testlerin hiçbiri ağ kullanmıyor ve bir borsa tanımıyor: `BarAkisi` protokolü
tüketici tarafında (`live/akis.py`) tanımlı olduğu için sahte bir akış yeterli.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI, KaliteDurumu
from scryne_quant.live.akis import BAR_ALANLARI, AkisHatasi, Bar, Kaynak, Tazelik
from scryne_quant.live.pencere import BarPenceresi, PencereHatasi

SAAT = 3_600_000


def bar(
    zaman_ms: int,
    kapanis: float = 100.0,
    *,
    acilis: float | None = None,
    yuksek: float | None = None,
    dusuk: float | None = None,
    hacim: float = 10.0,
    trades: int = 25,
    kaynak: Kaynak = Kaynak.AKIS,
) -> Bar:
    a = kapanis if acilis is None else acilis
    return Bar(
        open_time=zaman_ms,
        open=a,
        high=max(a, kapanis) if yuksek is None else yuksek,
        low=min(a, kapanis) if dusuk is None else dusuk,
        close=kapanis,
        volume=hacim,
        quote_volume=hacim * kapanis,
        trades=trades,
        kaynak=kaynak,
    )


class TestBarSemaHizasi:
    """`Bar` ile depo şeması ayrışırsa canlı ve tarihsel yollar sessizce ikiye ayrılır."""

    def test_alanlar_ham_sema_ile_ayni(self) -> None:
        assert BAR_ALANLARI == HAM_BAR_SUTUNLARI

    def test_sozluk_tam_olarak_ham_sutunlari_veriyor(self) -> None:
        assert tuple(bar(0).sozluk()) == HAM_BAR_SUTUNLARI

    def test_kaynak_semaya_sizmiyor(self) -> None:
        # `kaynak` bir doğrulama girdisi, bir bar alanı değil: depoya yazılırsa şema
        # değişir ve mevcut tüm Parquet dosyalarının SHA-256'sı bozulur (K-011).
        assert "kaynak" not in bar(0, kaynak=Kaynak.BACKFILL).sozluk()

    def test_hizalama(self) -> None:
        assert bar(2 * SAAT).hizali_mi("1h")
        assert not bar(2 * SAAT + 1).hizali_mi("1h")

    def test_negatif_zaman_reddediliyor(self) -> None:
        with pytest.raises(AkisHatasi):
            bar(-1)


class TestTazelik:
    """§24: ölçülen şey **update**, bar değil."""

    def test_hic_nabiz_yoksa_bayat(self) -> None:
        # "Ölçülemeyen guard geçilmiş sayılmaz" — Faz 5'te ATR için verilen kural.
        t = Tazelik(azami_yas_ms=5_000)
        assert t.yas(1_000) is None
        assert t.bayat_mi(1_000) is True

    def test_taze_ve_bayat_sinirlari(self) -> None:
        t = Tazelik(azami_yas_ms=5_000)
        t.nabiz(10_000)
        assert t.yas(12_000) == 2_000
        assert not t.bayat_mi(15_000)  # tam sınır: 5000 ms, henüz bayat değil
        assert t.bayat_mi(15_001)

    def test_geriye_giden_nabiz_yok_sayiliyor(self) -> None:
        t = Tazelik(azami_yas_ms=5_000)
        t.nabiz(10_000)
        t.nabiz(9_000)
        assert t.son_nabiz_ms == 10_000

    def test_negatif_yas_uretilmiyor(self) -> None:
        t = Tazelik(azami_yas_ms=5_000)
        t.nabiz(10_000)
        assert t.yas(9_000) == 0

    def test_gecis_yalnizca_degisimde_bildiriliyor(self) -> None:
        # 30 günlük koşuda her kontrolde satır yazan bir guard kendi kanıtını gömer.
        t = Tazelik(azami_yas_ms=5_000)
        t.nabiz(10_000)
        assert t.gecis_isle(11_000) is None
        assert t.gecis_isle(20_000) is True
        assert t.gecis_isle(21_000) is None
        assert t.bayat_durumda
        t.nabiz(22_000)
        assert t.gecis_isle(22_000) is False
        assert not t.bayat_durumda
        assert t.bayat_giris == 1

    def test_gecersiz_esik(self) -> None:
        with pytest.raises(AkisHatasi):
            Tazelik(azami_yas_ms=0)


class TestPencereEkleme:
    def test_sirali_ekleme(self) -> None:
        p = BarPenceresi("BTC/USDT", "1h")
        assert p.ekle(bar(0)) is True
        assert p.ekle(bar(SAAT)) is True
        assert len(p) == 2
        assert p.son_ms == SAAT
        assert p.beklenen_sonraki_ms() == 2 * SAAT

    def test_ayni_zamanli_bar_revize_ediyor(self) -> None:
        p = BarPenceresi("BTC/USDT", "1h")
        p.ekle(bar(0, 100.0))
        assert p.ekle(bar(0, 101.0)) is False
        assert len(p) == 1
        assert p.diziler()["close"][-1] == 101.0

    def test_geriye_giden_bar_hata(self) -> None:
        p = BarPenceresi("BTC/USDT", "1h")
        p.ekle(bar(SAAT))
        with pytest.raises(PencereHatasi, match="geriye gitti"):
            p.ekle(bar(0))

    def test_hizasiz_bar_hata(self) -> None:
        p = BarPenceresi("BTC/USDT", "1h")
        with pytest.raises(PencereHatasi, match="hizalı değil"):
            p.ekle(bar(SAAT + 1))

    def test_kapasite_fifo(self) -> None:
        p = BarPenceresi("BTC/USDT", "1h", kapasite=3)
        p.doldur(bar(i * SAAT) for i in range(5))
        assert len(p) == 3
        assert p.dolu
        assert list(p.diziler()["open_time"]) == [2 * SAAT, 3 * SAAT, 4 * SAAT]

    def test_kucuk_kapasite_reddediliyor(self) -> None:
        with pytest.raises(PencereHatasi):
            BarPenceresi("BTC/USDT", "1h", kapasite=1)


class TestPencereDogrulama:
    """Pencere backtest'le **aynı** doğrulamayı kullanmalı (K-001)."""

    def test_bosluk_gap_isaretleniyor(self) -> None:
        p = BarPenceresi("BTC/USDT", "1h")
        p.ekle(bar(0))
        p.ekle(bar(SAAT))
        p.ekle(bar(3 * SAAT))  # 2*SAAT eksik
        durum = p.diziler()["quality_status"]
        assert str(durum[2]) == str(KaliteDurumu.GAP)
        assert p.rapor().bosluk_sayisi == 1
        # Boşluk uydurulmuyor (K-024): eksik bar için satır yok.
        assert len(p) == 3

    def test_sifir_hacim_suspect(self) -> None:
        p = BarPenceresi("BTC/USDT", "1h")
        p.ekle(bar(0))
        p.ekle(bar(SAAT, hacim=0.0, trades=0))
        assert str(p.diziler()["quality_status"][1]) == str(KaliteDurumu.SUSPECT)
        assert not p.son_bar_ok_mu()

    def test_backfill_bari_ok_degil_backfilled(self) -> None:
        p = BarPenceresi("BTC/USDT", "1h")
        p.ekle(bar(0, kaynak=Kaynak.BACKFILL))
        p.ekle(bar(SAAT, kaynak=Kaynak.AKIS))
        durum = p.diziler()["quality_status"]
        assert str(durum[0]) == str(KaliteDurumu.BACKFILLED)
        assert str(durum[1]) == str(KaliteDurumu.OK)

    def test_backfill_kusuru_gizlemiyor(self) -> None:
        # Öncelik sırası korunuyor: suspect > gap > duplicate > backfilled.
        p = BarPenceresi("BTC/USDT", "1h")
        p.ekle(bar(0))
        p.ekle(bar(SAAT, hacim=0.0, trades=0, kaynak=Kaynak.BACKFILL))
        assert str(p.diziler()["quality_status"][1]) == str(KaliteDurumu.SUSPECT)

    def test_diziler_salt_okunur(self) -> None:
        p = BarPenceresi("BTC/USDT", "1h")
        p.doldur(bar(i * SAAT) for i in range(3))
        with pytest.raises(ValueError):
            p.diziler()["close"][0] = 1.0

    def test_onbellek_yeni_barda_tazeleniyor(self) -> None:
        p = BarPenceresi("BTC/USDT", "1h")
        p.ekle(bar(0, 100.0))
        assert list(p.diziler()["close"]) == [100.0]
        p.ekle(bar(SAAT, 101.0))
        assert list(p.diziler()["close"]) == [100.0, 101.0]

    def test_bos_pencere_dogrulanmiyor(self) -> None:
        p = BarPenceresi("BTC/USDT", "1h")
        assert p.son_bar_ok_mu() is False
        assert p.sozluk()["bar_sayisi"] == 0
        with pytest.raises(PencereHatasi):
            p.diziler()

    def test_diziler_backtest_motorunun_bekledigi_anahtarlar(self) -> None:
        # `strategy/kosu.py:gorunum_kur` bu anahtarları arıyor; eksik biri canlıda
        # ancak çalışma anında patlardı.
        p = BarPenceresi("BTC/USDT", "1h")
        p.doldur(bar(i * SAAT) for i in range(3))
        diziler = p.diziler()
        for ad in (*HAM_BAR_SUTUNLARI, "quality_status"):
            assert ad in diziler
        assert diziler["open_time"].dtype == np.int64
        assert diziler["close"].dtype == np.float64
