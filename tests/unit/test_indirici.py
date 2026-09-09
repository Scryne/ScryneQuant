"""İndirici: sayfalama, kaldığı yerden devam, idempotency. (Faz 1 bitti kriteri)

Testler **sahte bir adaptörle** çalışır. Sebep sadece hız değil: gerçek borsa her çağrıda
biraz farklı veri döndürebilir, ve "aynı komut iki kez → aynı dosya" iddiasını değişken
bir kaynağın üzerinde kanıtlamak mümkün değil. Sahte adaptör, gerçeğinin **ölçülmüş**
davranışını taklit eder — 1000'lik sayfa, kapanmamış barın gizlenmesi, aralık dışı bar
döndürmeme — ve sabit kalır.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.data.indirici import Aralik, IndirmeHatasi, TarihselIndirici
from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI, KaliteDurumu
from scryne_quant.exchange.temel import SAYFA_BOYU, BorsaAdaptoru, BorsaHatasi, SembolKurallari
from tests.conftest import bar_uret

BASLANGIC = 1_699_999_200_000  # 2023-11-14 22:00 UTC, 1h hizalı


class SahteAdaptor(BorsaAdaptoru):
    """Ölçülmüş Binance davranışını taklit eden adaptör.

    Gerçek adaptörle paylaştığı sözleşme: sayfa başına en fazla `SAYFA_BOYU` bar, **hiç
    kapanmamış bar yok**, aralık dışına taşma yok.
    """

    def __init__(self, barlar: pd.DataFrame, timeframe: str = "1h", sunucu_ms: int | None = None):
        self.barlar = barlar.sort_values("open_time").reset_index(drop=True)
        self.timeframe = timeframe
        adim = timeframe_ms(timeframe)
        son = int(self.barlar["open_time"].iloc[-1])
        # Varsayılan: son bar kapanmış, sonraki bar açık (gerçekte olduğu gibi).
        self._sunucu_ms = sunucu_ms if sunucu_ms is not None else son + adim + 1
        self.cagrilar: list[tuple[int, int]] = []
        self.hata_ver = False

    def sunucu_zamani_ms(self) -> int:
        return self._sunucu_ms

    def klines(self, sembol, timeframe, baslangic_ms, bitis_ms):
        if self.hata_ver:
            raise BorsaHatasi("sahte ağ hatası")
        self.cagrilar.append((baslangic_ms, bitis_ms))
        adim = timeframe_ms(timeframe)
        df = self.barlar
        secim = df[(df["open_time"] >= baslangic_ms) & (df["open_time"] < bitis_ms)]
        # Kapanmamış bar asla dönmez (K-015/1).
        secim = secim[secim["open_time"] + adim <= self._sunucu_ms]
        return secim.head(SAYFA_BOYU).loc[:, list(HAM_BAR_SUTUNLARI)].reset_index(drop=True)

    def sembol_kurallari(self, sembol):
        return SembolKurallari(sembol.upper(), 0.01, 0.00001, 5.0, "TRADING")


def seri(n: int, timeframe: str = "1h") -> pd.DataFrame:
    return bar_uret(n=n, timeframe=timeframe, baslangic_ms=BASLANGIC).loc[
        :, list(HAM_BAR_SUTUNLARI)
    ]


@pytest.fixture
def kurulum(depo_kok):
    barlar = seri(2_500)  # üç sayfadan uzun: sayfalama gerçekten çalışsın
    adaptor = SahteAdaptor(barlar)
    return TarihselIndirici(adaptor, ParquetDepo(depo_kok)), adaptor, barlar


def tam_aralik(barlar: pd.DataFrame, timeframe: str = "1h") -> tuple[int, int]:
    adim = timeframe_ms(timeframe)
    return int(barlar["open_time"].iloc[0]), int(barlar["open_time"].iloc[-1]) + adim


class TestSayfalama:
    def test_tum_barlar_iniyor(self, kurulum):
        indirici, adaptor, barlar = kurulum
        bas, bit = tam_aralik(barlar)

        sonuc = indirici.indir("BTCUSDT", "1h", bas, bit)

        assert sonuc.inen_bar == len(barlar)
        assert sonuc.depo.bar_sayisi == len(barlar)
        assert sonuc.kalite.kusursuz

    def test_sayfa_sayisi_beklenen(self, kurulum):
        indirici, adaptor, barlar = kurulum
        bas, bit = tam_aralik(barlar)
        indirici.indir("BTCUSDT", "1h", bas, bit)
        # 2500 bar = 1000 + 1000 + 500. Üçüncü sayfadan sonra imleç aralığın sonuna
        # ulaşır, yani boşuna bir dördüncü çağrı yapılmaz. Boş yanıt maliyeti yalnızca
        # istenen aralık verinin bittiği yerin ötesine uzandığında ödenir.
        assert len(adaptor.cagrilar) == 3

    def test_imlec_geri_gitmiyor(self, kurulum):
        indirici, adaptor, barlar = kurulum
        bas, bit = tam_aralik(barlar)
        indirici.indir("BTCUSDT", "1h", bas, bit)
        baslangiclar = [c[0] for c in adaptor.cagrilar]
        assert baslangiclar == sorted(baslangiclar)
        assert len(set(baslangiclar)) == len(baslangiclar)


class TestIdempotency:
    """Faz 1'in bitti kriteri: aynı komut iki kez → dosya bit düzeyinde aynı."""

    def test_ikinci_calistirma_dosyayi_degistirmiyor(self, kurulum):
        indirici, adaptor, barlar = kurulum
        bas, bit = tam_aralik(barlar)

        ilk = indirici.indir("BTCUSDT", "1h", bas, bit)
        ikinci = indirici.indir("BTCUSDT", "1h", bas, bit)

        assert ilk.degisti is True
        assert ikinci.degisti is False
        assert ilk.depo.sha256 == ikinci.depo.sha256

    def test_ikinci_calistirma_ag_kullanmiyor(self, kurulum):
        """Depoda olan aralık yeniden indirilmez — "kaldığı yerden devam"ın diğer yüzü."""
        indirici, adaptor, barlar = kurulum
        bas, bit = tam_aralik(barlar)

        indirici.indir("BTCUSDT", "1h", bas, bit)
        onceki_cagri = len(adaptor.cagrilar)
        indirici.indir("BTCUSDT", "1h", bas, bit)

        assert len(adaptor.cagrilar) == onceki_cagri

    def test_parcali_indirme_butun_indirmeyle_ayni_dosya(self, depo_kok, tmp_path):
        """Aynı veri, farklı parçalarla inince aynı dosyayı vermeli.

        Bu testin özel değeri şurada: `gap` bayrağı bir barın **öncekiyle** arasındaki
        mesafeye bakar. Doğrulama sayfa sayfa yapılsaydı her sayfanın ilk barı kendinden
        öncekine ulaşamaz, ve dosya indirmenin kaç parçaya bölündüğüne göre değişirdi.
        """
        barlar = seri(1_500)
        bas, bit = tam_aralik(barlar)
        orta = bas + 700 * timeframe_ms("1h")

        butun = TarihselIndirici(SahteAdaptor(barlar), ParquetDepo(tmp_path / "a"))
        beklenen = butun.indir("BTCUSDT", "1h", bas, bit).depo.sha256

        parcali = TarihselIndirici(SahteAdaptor(barlar), ParquetDepo(tmp_path / "b"))
        parcali.indir("BTCUSDT", "1h", bas, orta)
        sonuc = parcali.indir("BTCUSDT", "1h", bas, bit)

        assert sonuc.depo.sha256 == beklenen

    def test_ortusen_yeniden_indirme_duplicate_uretmiyor(self, depo_kok):
        """Depoyla çakışan bir aralığı yeniden indirmek sahte `duplicate` üretmemeli.

        `duplicate` borsanın aynı timestamp'i iki kez göndermesini kaydeder (K-006);
        kendi depomuzu yeni bir indirmeyle birleştirmek olağan işleyiştir. İkisi
        ayrılmazsa örtüşen her yeniden indirme yüzlerce barı yanlış bayraklar — ve
        `ok` oranı sebepsiz düşer.
        """
        barlar = seri(1_200)
        adim = timeframe_ms("1h")
        bas, bit = tam_aralik(barlar)
        depo = ParquetDepo(depo_kok)
        indirici = TarihselIndirici(SahteAdaptor(barlar), depo)

        indirici.indir("BTCUSDT", "1h", bas, bas + 800 * adim)
        # Depoyu kasten "delik" bırakacak şekilde bozmak yerine tam aralığı tekrar iste:
        sonuc = indirici.indir("BTCUSDT", "1h", bas, bit)

        assert sonuc.kalite.bayraklar.get(KaliteDurumu.DUPLICATE, 0) == 0
        assert sonuc.kalite.kusursuz


class TestKaldigiYerdenDevam:
    def test_yalnizca_eksik_kisim_iniyor(self, depo_kok):
        barlar = seri(1_000)
        adim = timeframe_ms("1h")
        bas, bit = tam_aralik(barlar)
        adaptor = SahteAdaptor(barlar)
        indirici = TarihselIndirici(adaptor, ParquetDepo(depo_kok))

        indirici.indir("BTCUSDT", "1h", bas, bas + 600 * adim)
        ikinci = indirici.indir("BTCUSDT", "1h", bas, bit)

        assert ikinci.inen_bar == 400
        assert ikinci.depo.bar_sayisi == 1_000
        assert ikinci.eksik_araliklar == (Aralik(bas + 600 * adim, bit),)

    def test_bastan_geriye_dogru_genisletme(self, depo_kok):
        """Depoda 2024 varken 2023 istenirse baş taraf indirilir."""
        barlar = seri(1_000)
        adim = timeframe_ms("1h")
        bas, bit = tam_aralik(barlar)
        indirici = TarihselIndirici(SahteAdaptor(barlar), ParquetDepo(depo_kok))

        indirici.indir("BTCUSDT", "1h", bas + 400 * adim, bit)
        ikinci = indirici.indir("BTCUSDT", "1h", bas, bit)

        assert ikinci.inen_bar == 400
        assert ikinci.eksik_araliklar == (Aralik(bas, bas + 400 * adim),)

    def test_ic_bosluk_yeniden_deneniyor(self, depo_kok):
        """Depodaki bir boşluk sonraki çalıştırmada yeniden istenir — veri seti iyileşsin."""
        barlar = seri(500)
        bas, bit = tam_aralik(barlar)
        depo = ParquetDepo(depo_kok)

        eksik = barlar.drop(index=range(100, 110)).reset_index(drop=True)
        eksik_indirici = TarihselIndirici(SahteAdaptor(eksik), depo)
        ilk = eksik_indirici.indir("BTCUSDT", "1h", bas, bit)
        assert ilk.kalite.bosluk_sayisi == 1

        # Borsa boşluğu doldurdu: aynı komut artık tam veriyi getirir.
        tam_indirici = TarihselIndirici(SahteAdaptor(barlar), depo)
        ikinci = tam_indirici.indir("BTCUSDT", "1h", bas, bit)

        assert ikinci.inen_bar == 10
        assert ikinci.kalite.bosluk_sayisi == 0
        assert ikinci.kalite.kusursuz


class TestKapanmamisBar:
    def test_acik_bar_depoya_girmiyor(self, depo_kok):
        """K-015/1: kapanmamış bar yazılırsa idempotency imkânsız."""
        barlar = seri(100)
        adim = timeframe_ms("1h")
        son = int(barlar["open_time"].iloc[-1])
        # Sunucu saati son barın **ortasında**: o bar henüz kapanmadı.
        adaptor = SahteAdaptor(barlar, sunucu_ms=son + adim // 2)
        indirici = TarihselIndirici(adaptor, ParquetDepo(depo_kok))

        sonuc = indirici.indir("BTCUSDT", "1h", int(barlar["open_time"].iloc[0]), son + adim)

        assert sonuc.depo.bar_sayisi == 99
        assert sonuc.depo.son_ms == son - adim

    def test_varsayilan_bitis_acik_barin_acilisi(self, kurulum):
        indirici, adaptor, barlar = kurulum
        adim = timeframe_ms("1h")
        beklenen = (adaptor.sunucu_zamani_ms() // adim) * adim
        assert indirici.son_kapali_bar_sonu("1h") == beklenen


class TestHatalar:
    def test_bos_aralik_reddedilir(self, kurulum):
        indirici, _, barlar = kurulum
        bas = int(barlar["open_time"].iloc[0])
        with pytest.raises(IndirmeHatasi, match="boş aralık"):
            indirici.indir("BTCUSDT", "1h", bas, bas)

    def test_ag_hatasi_sarilir(self, kurulum):
        indirici, adaptor, barlar = kurulum
        adaptor.hata_ver = True
        bas, bit = tam_aralik(barlar)
        with pytest.raises(IndirmeHatasi, match="indirilemedi"):
            indirici.indir("BTCUSDT", "1h", bas, bit)

    def test_hicbir_veri_yoksa_hata(self, depo_kok):
        barlar = seri(100)
        adim = timeframe_ms("1h")
        bas = int(barlar["open_time"].iloc[0])
        indirici = TarihselIndirici(SahteAdaptor(barlar), ParquetDepo(depo_kok))
        # Serinin tamamen dışında bir aralık: ne inen var ne depoda olan.
        uzak = bas + 10_000 * adim
        with pytest.raises(IndirmeHatasi, match="hiç bar yok"):
            indirici.indir("BTCUSDT", "1h", uzak, uzak + 100 * adim)

    def test_hizasiz_baslangic_hizalanir(self, kurulum):
        """Kullanıcının verdiği tarih ızgaraya oturmuyorsa sessizce hizalanır, patlamaz."""
        indirici, _, barlar = kurulum
        bas, bit = tam_aralik(barlar)
        sonuc = indirici.indir("BTCUSDT", "1h", bas + 137, bit)
        assert sonuc.aralik.baslangic_ms == bas


class TestZamanSozlesmesi:
    def test_tum_timestampler_hizali_ve_utc(self, kurulum):
        """K-005: bar timestamp'i epoch'a hizalı açılış zamanıdır — depoda da öyle."""
        indirici, _, barlar = kurulum
        bas, bit = tam_aralik(barlar)
        sonuc = indirici.indir("BTCUSDT", "1h", bas, bit)

        okunan = indirici.depo.oku("BTCUSDT", "1h")
        adim = timeframe_ms("1h")
        assert (okunan["open_time"] % adim == 0).all()
        assert okunan["open_time"].dtype == "int64"
        assert okunan["open_time"].is_monotonic_increasing
        assert sonuc.depo.ilk_ms == bas
