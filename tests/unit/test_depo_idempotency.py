"""Depo determinizmi ve idempotency. (K-009, K-011)

**Faz 1'in bitti kriterlerinden biri burada kanıtlanıyor:** aynı indirme komutu iki kez
çalıştırıldığında dosya içeriği bit düzeyinde aynı olmalı.

Spike 3 parquet yazımının deterministik olduğunu ölçtü; Spike 1 ise REST'in kapanmamış
barı sürekli değiştirerek döndürdüğünü ölçtü. İkisi birleşince şu çıkıyor: bit-eşitliğini
bozabilecek tek şey kapanmamış bar. Buradaki testler önce deponun kendi determinizmini,
sonra "veri nasıl gelirse gelsin aynı dosya" sözleşmesini sabitliyor.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scryne_quant.common.hash import dosya_hash
from scryne_quant.data.depo import DepoHatasi, ParquetDepo
from scryne_quant.data.semalar import BAR_SUTUNLARI, KaliteDurumu
from tests.conftest import bar_uret


@pytest.fixture
def depo(depo_kok) -> ParquetDepo:
    return ParquetDepo(depo_kok)


class TestDeterminizm:
    def test_ayni_veri_ayni_bayt(self, depo, barlar):
        """Aynı DataFrame iki kez yazılınca dosya bit düzeyinde aynı."""
        ilk = depo.yaz("BTCUSDT", "1h", barlar)
        ilk_bayt = depo.yol("BTCUSDT", "1h").read_bytes()

        ikinci = depo.yaz("BTCUSDT", "1h", barlar)
        ikinci_bayt = depo.yol("BTCUSDT", "1h").read_bytes()

        assert ilk.sha256 == ikinci.sha256
        assert ilk_bayt == ikinci_bayt

    def test_farkli_kok_ayni_hash(self, tmp_path, barlar):
        """Dosya yolu kimliğe karışmaz — hash yalnızca içeriğe bağlı."""
        a = ParquetDepo(tmp_path / "a").yaz("BTCUSDT", "1h", barlar)
        b = ParquetDepo(tmp_path / "b").yaz("BTCUSDT", "1h", barlar)
        assert a.sha256 == b.sha256

    def test_satir_sirasi_hashi_degistirmez(self, depo, barlar):
        """Barlar karışık sırayla gelse de dosya aynı — normalize sıralıyor."""
        duz = depo.yaz("BTCUSDT", "1h", barlar)
        karisik = depo.yaz(
            "BTCUSDT", "1h", barlar.sample(frac=1, random_state=7).reset_index(drop=True)
        )
        assert duz.sha256 == karisik.sha256

    def test_sutun_sirasi_hashi_degistirmez(self, depo, barlar):
        duz = depo.yaz("BTCUSDT", "1h", barlar)
        ters = depo.yaz("BTCUSDT", "1h", barlar.loc[:, list(reversed(BAR_SUTUNLARI))])
        assert duz.sha256 == ters.sha256

    def test_dtype_kaymasi_hashi_degistirmez(self, depo, barlar):
        """int32/float32 ile gelen veri de kanonik dtype'a çekilir."""
        duz = depo.yaz("BTCUSDT", "1h", barlar)
        kaymis = barlar.copy()
        kaymis["trades"] = kaymis["trades"].astype("int32")
        kaymis["volume"] = kaymis["volume"].astype("float32").astype("float64")
        # float32'ye düşüp geri çıkan hacim gerçekten farklı bir sayı; bu testin amacı
        # dtype'ın kendisinin hash'e karışmaması, o yüzden hacmi geri yazıyoruz.
        kaymis["volume"] = barlar["volume"]
        assert depo.yaz("BTCUSDT", "1h", kaymis).sha256 == duz.sha256

    def test_pandas_metadata_gomulmuyor(self, depo, barlar):
        """Dosyaya pandas sürümü yazılmamalı.

        `Table.from_pandas` pandas sürümünü ve index şemasını dosyaya gömer; pandas
        güncellendiğinde aynı verinin hash'i sessizce değişirdi.
        """
        depo.yaz("BTCUSDT", "1h", barlar)
        ham = depo.yol("BTCUSDT", "1h").read_bytes()
        assert b"pandas_version" not in ham
        assert b'"index_columns"' not in ham


class TestIdempotency:
    """Aynı veri kaç kez, hangi parçalar hâlinde yazılırsa yazılsın dosya aynı."""

    def test_tekrarli_yazim(self, depo, barlar):
        hashler = {depo.yaz("BTCUSDT", "1h", barlar).sha256 for _ in range(5)}
        assert len(hashler) == 1

    def test_parcali_indirme_butun_indirmeyle_ayni(self, depo, barlar):
        """Sayfalama ile parça parça inen veri, tek seferde inenle aynı dosyayı üretir.

        İndiricinin "kaldığı yerden devam" davranışının sözleşmesi budur.
        """
        butun = depo.yaz("BTCUSDT", "1h", barlar).sha256

        depo.yol("BTCUSDT", "1h").unlink()
        for bas in range(0, len(barlar), 137):  # 1000'e bölünmeyen bir sayfa boyu
            depo.birlestir("BTCUSDT", "1h", barlar.iloc[bas : bas + 137])

        assert depo.sha256("BTCUSDT", "1h") == butun

    def test_ortusen_aralik_tekrar_indirilebilir(self, depo, barlar):
        """Aynı aralık iki kez indirilirse dosya değişmez — tekilleştirme çalışıyor."""
        depo.yaz("BTCUSDT", "1h", barlar.iloc[:300])
        depo.birlestir("BTCUSDT", "1h", barlar.iloc[200:])
        ilk = depo.sha256("BTCUSDT", "1h")

        depo.birlestir("BTCUSDT", "1h", barlar.iloc[150:400])  # tamamen örtüşen aralık
        assert depo.sha256("BTCUSDT", "1h") == ilk
        assert len(depo.oku("BTCUSDT", "1h")) == len(barlar)

    def test_yeni_veri_eskisini_ezer(self, depo, barlar):
        """Çakışan timestamp'te sonraki çağrı kazanır (`keep='last'`)."""
        depo.yaz("BTCUSDT", "1h", barlar)
        duzeltme = barlar.iloc[:1].copy()
        duzeltme.loc[:, "close"] = 99_999.0
        depo.birlestir("BTCUSDT", "1h", duzeltme)

        okunan = depo.oku("BTCUSDT", "1h")
        assert okunan["close"].iloc[0] == 99_999.0
        assert len(okunan) == len(barlar)


class TestGidisDonus:
    def test_yazilan_okunan_esit(self, depo, barlar):
        depo.yaz("BTCUSDT", "1h", barlar)
        okunan = depo.oku("BTCUSDT", "1h")
        beklenen = ParquetDepo.normalize(barlar)
        pd.testing.assert_frame_equal(okunan, beklenen)

    def test_okunan_yeniden_yazilinca_ayni_hash(self, depo, barlar):
        """Gidiş-dönüş kayıpsız: oku→yaz döngüsü dosyayı değiştirmiyor."""
        ilk = depo.yaz("BTCUSDT", "1h", barlar).sha256
        assert depo.yaz("BTCUSDT", "1h", depo.oku("BTCUSDT", "1h")).sha256 == ilk

    def test_kalite_bayragi_korunuyor(self, depo):
        """K-006: bayrak bar başına saklanır, okumada kaybolmaz."""
        df = bar_uret(n=10)
        df.loc[3, "quality_status"] = KaliteDurumu.SUSPECT
        df.loc[7, "quality_status"] = KaliteDurumu.GAP
        depo.yaz("BTCUSDT", "1h", df)

        okunan = depo.oku("BTCUSDT", "1h")
        assert okunan.loc[3, "quality_status"] == "suspect"
        assert okunan.loc[7, "quality_status"] == "gap"
        assert (okunan["quality_status"] == "ok").sum() == 8


class TestSozlesmeIhlalleri:
    def test_eksik_sutun_reddedilir(self, depo, barlar):
        with pytest.raises(DepoHatasi, match="eksik sütun"):
            depo.yaz("BTCUSDT", "1h", barlar.drop(columns=["quote_volume"]))

    def test_kalite_bayragi_zorunlu(self, depo, barlar):
        """Bayrak varsayılana düşürülmez: doğrulanmamış barı `ok` saymak sessiz yalandır."""
        with pytest.raises(DepoHatasi, match="eksik sütun"):
            depo.yaz("BTCUSDT", "1h", barlar.drop(columns=["quality_status"]))

    def test_bos_dataframe_reddedilir(self, depo, barlar):
        with pytest.raises(DepoHatasi, match="boş"):
            depo.yaz("BTCUSDT", "1h", barlar.iloc[0:0])

    def test_olmayan_veri_okunamaz(self, depo):
        with pytest.raises(DepoHatasi, match="depoda yok"):
            depo.oku("ETHUSDT", "1h")

    def test_bilinmeyen_timeframe_yolda_patlar(self, depo):
        from scryne_quant.common.zaman import GecersizTimeframe

        with pytest.raises(GecersizTimeframe):
            depo.yol("BTCUSDT", "7h")


class TestKismiYazim:
    def test_gecici_dosya_birakilmiyor(self, depo, barlar):
        depo.yaz("BTCUSDT", "1h", barlar)
        kalintilar = list(depo.yol("BTCUSDT", "1h").parent.glob("*.tmp"))
        assert kalintilar == []

    def test_hash_dosyayla_tutarli(self, depo, barlar):
        kayit = depo.yaz("BTCUSDT", "1h", barlar)
        assert kayit.sha256 == dosya_hash(kayit.yol) == depo.sha256("BTCUSDT", "1h")
        assert kayit.bayt == kayit.yol.stat().st_size
