"""Zaman sözleşmesi testleri. (K-005)"""

from __future__ import annotations

import datetime as dt

import pytest

from scryne_quant.common import zaman


class TestTimeframe:
    def test_bilinen_timeframe(self):
        assert zaman.timeframe_ms("1h") == 3_600_000
        assert zaman.timeframe_ms("1m") == 60_000
        assert zaman.timeframe_ms("1d") == 86_400_000

    def test_bilinmeyen_timeframe_hata_verir(self):
        # Sessizce varsayılana düşmek, yanlış aralıkta backtest çalıştırmak demek olurdu.
        with pytest.raises(zaman.GecersizTimeframe):
            zaman.timeframe_ms("7h")


class TestDonusum:
    def test_ms_datetime_gidis_donus(self):
        ms = 1_700_000_000_000
        assert zaman.datetime_to_ms(zaman.ms_to_datetime(ms)) == ms

    def test_ms_to_datetime_utc_aware(self):
        d = zaman.ms_to_datetime(1_700_000_000_000)
        assert d.tzinfo is not None
        assert d.utcoffset() == dt.timedelta(0)

    def test_naive_datetime_reddedilir(self):
        # "Hangi saat dilimi" sorusunu sessizce varsaymak, bu modülün engellemek için
        # var olduğu hatanın ta kendisi (K-005).
        with pytest.raises(ValueError, match="naive"):
            zaman.datetime_to_ms(dt.datetime(2026, 1, 1, 12, 0, 0))

    def test_yerel_saat_sonucu_degistirmez(self):
        """UTC+3'teki bir an ile aynı anın UTC gösterimi aynı epoch ms'i verir."""
        utc3 = dt.timezone(dt.timedelta(hours=3))
        an_utc3 = dt.datetime(2026, 9, 8, 22, 0, 0, tzinfo=utc3)
        an_utc = dt.datetime(2026, 9, 8, 19, 0, 0, tzinfo=dt.UTC)
        assert zaman.datetime_to_ms(an_utc3) == zaman.datetime_to_ms(an_utc)


class TestBarSinirlari:
    def test_bar_acilisi_epoch_hizali(self):
        # 12:34:56 -> 12:00:00 (1h)
        an = zaman.datetime_to_ms(dt.datetime(2026, 9, 8, 12, 34, 56, tzinfo=dt.UTC))
        beklenen = zaman.datetime_to_ms(dt.datetime(2026, 9, 8, 12, 0, 0, tzinfo=dt.UTC))
        assert zaman.bar_acilisi(an, "1h") == beklenen

    def test_bar_acilisi_idempotent(self):
        """Zaten hizalı bir timestamp'i tekrar hizalamak değiştirmez."""
        an = zaman.datetime_to_ms(dt.datetime(2026, 9, 8, 12, 0, 0, tzinfo=dt.UTC))
        assert zaman.bar_acilisi(zaman.bar_acilisi(an, "1h"), "1h") == an

    def test_timestamp_acilis_zamanidir(self):
        """K-005: bar timestamp'i açılış zamanıdır, kapanış değil."""
        acilis = zaman.datetime_to_ms(dt.datetime(2026, 9, 8, 12, 0, 0, tzinfo=dt.UTC))
        # Bar boyunca geçen her an aynı barın açılışına eşlenir.
        for dakika in (0, 1, 30, 59):
            an = acilis + dakika * 60_000
            assert zaman.bar_acilisi(an, "1h") == acilis
        # Bir sonraki saatin ilk anı artık yeni bar.
        assert zaman.bar_acilisi(acilis + 3_600_000, "1h") != acilis


class TestKapanmislik:
    """Faz 1'in idempotency kriterinin dayandığı kural.

    Spike 1 ölçtü: REST `klines` her zaman devam eden barı son eleman olarak döndürüyor
    ve o bar çağrılar arasında değişiyor. Kapanmamış bar depoya yazılırsa aynı komut iki
    kez çalıştırıldığında dosya farklı çıkar.
    """

    acilis = 1_788_894_000_000  # 2026-09-08 19:00 UTC

    def test_kapanmis_bar(self):
        # Bar 20:00'da kapanır; 20:00 ve sonrası kapanmış sayılır.
        assert zaman.bar_kapandi_mi(self.acilis, "1h", self.acilis + 3_600_000)
        assert zaman.bar_kapandi_mi(self.acilis, "1h", self.acilis + 3_600_001)

    def test_kapanmamis_bar(self):
        # Spike 1'in ölçtüğü gerçek durum: sunucu saati 19:56, bar 20:00'da kapanacak.
        sunucu = 1_788_897_385_973  # 2026-09-08 19:56:25 UTC
        assert not zaman.bar_kapandi_mi(self.acilis, "1h", sunucu)

    def test_tam_sinirda_kapanmis_sayilir(self):
        """Sınır dahil: kapanış anına ulaşıldığında bar kapanmıştır."""
        assert zaman.bar_kapandi_mi(self.acilis, "1h", zaman.bar_kapanisi(self.acilis, "1h"))

    def test_bir_ms_once_kapanmamis(self):
        kapanis = zaman.bar_kapanisi(self.acilis, "1h")
        assert not zaman.bar_kapandi_mi(self.acilis, "1h", kapanis - 1)
