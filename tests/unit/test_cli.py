"""CLI sözleşmesi. (K-012)

Faz 1-5'in tek arayüzü bu; bir komutun çıktısı değiştiğinde onu kullanan her şey kırılır.
Testler ağa çıkmaz: indirme komutu sahte adaptörle çalıştırılır, geri kalanı zaten yerel
depo üzerinde iş görür.

`--json` çıktısı ayrıca sınanıyor çünkü makine tarafının sözleşmesi odur — insan tablosu
biçimlenebilir, JSON alanları biçimlenemez.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from scryne_quant.cli import main as cli
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.data.dogrulama import dogrula
from tests.conftest import bar_uret
from tests.unit.test_indirici import BASLANGIC, SahteAdaptor, seri

runner = CliRunner()


@pytest.fixture
def dolu_depo(tmp_path):
    """Doğrulanmış 300 barlık 1h veri seti."""
    kok = tmp_path / "depo"
    ham = bar_uret(n=300, baslangic_ms=BASLANGIC).drop(columns=["quality_status"])
    bayrakli, _ = dogrula(ham, "1h", sembol="BTCUSDT")
    ParquetDepo(kok).yaz("BTCUSDT", "1h", bayrakli)
    return kok


def calistir(*argv: str):
    return runner.invoke(cli.app, list(argv))


class TestQuality:
    def test_insan_ciktisi(self, dolu_depo):
        sonuc = calistir("data", "quality", "BTCUSDT", "1h", "--depo", str(dolu_depo))
        assert sonuc.exit_code == 0
        assert "ok oranı" in sonuc.stdout
        assert "300" in sonuc.stdout

    def test_json_ciktisi(self, dolu_depo):
        sonuc = calistir("data", "quality", "BTCUSDT", "1h", "--depo", str(dolu_depo), "--json")
        assert sonuc.exit_code == 0
        govde = json.loads(sonuc.stdout)
        assert govde["kalite"]["bar_sayisi"] == 300
        assert govde["kalite"]["ok_orani"] == 1.0
        assert len(govde["veri_sha256"]) == 64
        # K-009: rapor kendi başına bir kimlik taşımalı.
        assert "git" in govde and "ortam" in govde

    def test_rapor_dosyasi_yaziliyor(self, dolu_depo, tmp_path):
        rapor = tmp_path / "cikti" / "kalite.json"
        sonuc = calistir(
            "data", "quality", "BTCUSDT", "1h", "--depo", str(dolu_depo), "--rapor", str(rapor)
        )
        assert sonuc.exit_code == 0
        assert json.loads(rapor.read_text(encoding="utf-8"))["kalite"]["bar_sayisi"] == 300

    def test_olmayan_veri_hata_verir(self, dolu_depo):
        sonuc = calistir("data", "quality", "ETHUSDT", "1h", "--depo", str(dolu_depo))
        assert sonuc.exit_code != 0


class TestLs:
    def test_bos_depo(self, tmp_path):
        sonuc = calistir("data", "ls", "--depo", str(tmp_path / "yok"))
        assert sonuc.exit_code == 0
        assert "boş" in sonuc.stdout

    def test_json_listesi(self, dolu_depo):
        sonuc = calistir("data", "ls", "--depo", str(dolu_depo), "--json")
        satirlar = json.loads(sonuc.stdout)
        assert len(satirlar) == 1
        assert satirlar[0]["sembol"] == "BTCUSDT"
        assert satirlar[0]["bar"] == 300


class TestMaliyet:
    def test_gecici_model_uyariyor(self, tmp_path):
        """Geçici modelle üretilen sonuç promotion'a giremez — komut bunu söylemeli."""
        yol = tmp_path / "maliyet.json"
        maliyet_mod.yaz(maliyet_mod.MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0), yol)
        sonuc = calistir("data", "maliyet", "--config", str(yol))
        assert sonuc.exit_code == 0
        assert "GEÇİCİ" in sonuc.stdout

    def test_repodaki_config_okunabiliyor(self):
        sonuc = calistir("data", "maliyet", "--json")
        assert sonuc.exit_code == 0
        govde = json.loads(sonuc.stdout)
        assert govde["fee_taker_bps"] == 10.0  # Spike 4'te ölçüldü


class TestSlippageKalibre:
    @pytest.fixture
    def depo_1m(self, tmp_path):
        kok = tmp_path / "depo"
        ham = bar_uret(n=2_000, timeframe="1m", baslangic_ms=BASLANGIC).drop(
            columns=["quality_status"]
        )
        bayrakli, _ = dogrula(ham, "1m", sembol="BTCUSDT")
        ParquetDepo(kok).yaz("BTCUSDT", "1m", bayrakli)
        return kok

    def test_olcum_yazmadan_calisir(self, depo_1m):
        sonuc = calistir("data", "slippage-kalibre", "BTCUSDT", "--depo", str(depo_1m))
        assert sonuc.exit_code == 0
        assert "yazılmadı" in sonuc.stdout

    def test_gerekcesiz_yazim_reddedilir(self, depo_1m, tmp_path):
        """Gerekçesiz kalibrasyon, K-020'nin hatasını tekrarlamaya açık kapı bırakır."""
        yol = tmp_path / "maliyet.json"
        maliyet_mod.yaz(maliyet_mod.MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0), yol)
        sonuc = calistir(
            "data", "slippage-kalibre", "BTCUSDT",
            "--depo", str(depo_1m), "--config", str(yol), "--yaz",
        )
        assert sonuc.exit_code != 0
        assert maliyet_mod.yukle(yol).gecici is True

    def test_yazim_gecici_bayragi_kaldirir(self, depo_1m, tmp_path):
        yol = tmp_path / "maliyet.json"
        maliyet_mod.yaz(maliyet_mod.MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0), yol)

        sonuc = calistir(
            "data", "slippage-kalibre", "BTCUSDT",
            "--depo", str(depo_1m), "--config", str(yol),
            "--yaz", "--gerekce", "test gerekçesi",
        )

        assert sonuc.exit_code == 0
        model = maliyet_mod.yukle(yol)
        assert model.gecici is False
        assert model.kalibrasyon is not None
        assert model.kalibrasyon.gerekce == "test gerekçesi"
        assert model.slippage_bps == model.kalibrasyon.deger_bps
        # Kalibrasyon hangi veriden çıktığını taşımalı (K-025).
        assert len(model.kalibrasyon.veri_sha256) == 64
        assert model.kalibrasyon.dagilim_bps


class TestIndir:
    def test_sahte_adaptorle_ucdan_uca(self, tmp_path, monkeypatch):
        """`data indir` akışının tamamı: aralık → indirme → doğrulama → depo → çıktı."""
        barlar = seri(500)
        adaptor = SahteAdaptor(barlar)
        monkeypatch.setattr(cli, "BinanceAdaptoru", lambda *a, **k: adaptor)

        adim = timeframe_ms("1h")
        bas = int(barlar["open_time"].iloc[0])
        bit = int(barlar["open_time"].iloc[-1]) + adim
        kok = tmp_path / "depo"

        ortak = ["data", "indir", "BTCUSDT", "1h", "--depo", str(kok), "--json"]
        tarih = ["--baslangic", "2023-11-14", "--bitis", "2024-02-27"]

        ilk = json.loads(calistir(*ortak, *tarih).stdout)
        ikinci = json.loads(calistir(*ortak, *tarih).stdout)

        assert ilk["degisti"] is True
        assert ikinci["degisti"] is False
        assert ilk["sha256"] == ikinci["sha256"]
        assert ikinci["inen_bar"] == 0
        # İstenen aralık verinin tamamını kapsıyor; veri seti tam inmiş olmalı.
        assert ilk["istenen_aralik"]["baslangic_ms"] <= bas
        assert ilk["istenen_aralik"]["bitis_ms"] >= bit
        assert ilk["toplam_bar"] == len(barlar)

    def test_baslangic_ve_yil_birlikte_verilemez(self, tmp_path):
        sonuc = calistir(
            "data", "indir", "BTCUSDT", "1h",
            "--baslangic", "2020-01-01", "--yil", "5", "--depo", str(tmp_path),
        )
        assert sonuc.exit_code != 0

    def test_baslangic_zorunlu(self, tmp_path):
        sonuc = calistir("data", "indir", "BTCUSDT", "1h", "--depo", str(tmp_path))
        assert sonuc.exit_code != 0

    def test_bozuk_tarih_reddedilir(self, tmp_path):
        sonuc = calistir(
            "data", "indir", "BTCUSDT", "1h", "--baslangic", "14.11.2023", "--depo", str(tmp_path)
        )
        assert sonuc.exit_code != 0


class TestBilgi:
    def test_kimlik_bilgisi(self):
        """K-009: her sonucun yanına yazılacak commit + ortam bilgisi."""
        govde = json.loads(calistir("bilgi", "--json").stdout)
        assert "commit" in govde["git"]
        assert govde["ortam"]["python"].startswith("3.12")
        assert "pandas" in govde["ortam"]["paketler"]


class TestBacktest:
    """`sq backtest` — Faz 3'ün CLI yüzü. (K-012)"""

    def test_json_ciktisi(self, dolu_depo, tmp_path, monkeypatch):
        monkeypatch.setattr(cli, "VARSAYILAN_KOSU_KOKU", tmp_path / "runs")
        sonuc = calistir(
            "backtest", "BTCUSDT", "--depo", str(dolu_depo),
            "--hizli", "5", "--yavas", "20", "--json",
        )
        assert sonuc.exit_code == 0, sonuc.output
        govde = json.loads(sonuc.stdout)

        # K-009'un altı zorunlu alanı
        assert set(govde["kimlik"]) >= {
            "commit", "dirty", "veri_sha256", "config_hash", "sonuc_hash", "seed", "ortam"
        }
        assert govde["kimlik"]["veri_sha256"], "veri hash'i boş olamaz"
        # K-006: kalite oranı kayıtta
        assert "ok_olmayan_oran" in govde["veri"]
        assert "yillik_anlamli" in govde["metrikler"]
        assert govde["kayit_yolu"]

    def test_kayit_dosyasi_yaziliyor(self, dolu_depo, tmp_path, monkeypatch):
        monkeypatch.setattr(cli, "VARSAYILAN_KOSU_KOKU", tmp_path / "runs")
        sonuc = calistir(
            "backtest", "BTCUSDT", "--depo", str(dolu_depo), "--hizli", "5", "--yavas", "20"
        )
        assert sonuc.exit_code == 0, sonuc.output
        dosyalar = list((tmp_path / "runs").glob("*.json"))
        assert len(dosyalar) == 1
        kayit = json.loads(dosyalar[0].read_text(encoding="utf-8"))
        assert kayit["kimlik"]["sonuc_hash"]
        assert "egri" not in kayit, "eğri açıkça istenmedikçe yazılmamalı"

    def test_egri_istenince_yaziliyor(self, dolu_depo, tmp_path, monkeypatch):
        monkeypatch.setattr(cli, "VARSAYILAN_KOSU_KOKU", tmp_path / "runs")
        calistir(
            "backtest", "BTCUSDT", "--depo", str(dolu_depo),
            "--hizli", "5", "--yavas", "20", "--egri",
        )
        kayit = json.loads(next((tmp_path / "runs").glob("*.json")).read_text(encoding="utf-8"))
        assert len(kayit["egri"]["ozkaynak"]) == kayit["veri"]["bar_sayisi"]

    def test_ayni_komut_ayni_sonuc_hash(self, dolu_depo, tmp_path, monkeypatch):
        """Determinizm CLI seviyesinde de görülmeli (K-009)."""
        monkeypatch.setattr(cli, "VARSAYILAN_KOSU_KOKU", tmp_path / "runs")
        argv = ("backtest", "BTCUSDT", "--depo", str(dolu_depo), "--hizli", "5",
                "--yavas", "20", "--json", "--kayit-yok")
        a = json.loads(calistir(*argv).stdout)["kimlik"]["sonuc_hash"]
        b = json.loads(calistir(*argv).stdout)["kimlik"]["sonuc_hash"]
        assert a == b

    def test_parametre_degisince_hash_degisiyor(self, dolu_depo):
        temel = ("backtest", "BTCUSDT", "--depo", str(dolu_depo), "--json", "--kayit-yok")
        a = json.loads(calistir(*temel, "--hizli", "5", "--yavas", "20").stdout)["kimlik"]
        b = json.loads(calistir(*temel, "--hizli", "6", "--yavas", "20").stdout)["kimlik"]
        assert a["config_hash"] != b["config_hash"]

    def test_insan_ciktisi(self, dolu_depo, tmp_path, monkeypatch):
        monkeypatch.setattr(cli, "VARSAYILAN_KOSU_KOKU", tmp_path / "runs")
        sonuc = calistir(
            "backtest", "BTCUSDT", "--depo", str(dolu_depo), "--hizli", "5", "--yavas", "20"
        )
        assert sonuc.exit_code == 0
        for parca in ("sermaye", "max drawdown", "Sharpe", "config_hash", "sonuc_hash"):
            assert parca in sonuc.stdout

    def test_olmayan_veri_hata_verir(self, dolu_depo):
        sonuc = calistir("backtest", "ETHUSDT", "--depo", str(dolu_depo))
        assert sonuc.exit_code != 0


class TestPaper:
    """`sq paper` komutları. (Faz 6, K-034, K-035, K-038)

    Hepsi `--ag-yok` ile: koşuyu kurar ama başlatmaz. Ağa çıkan tek yol `--ag`, ve o yolun
    testi bir borsa gerektirirdi — kurulum ile koşturmayı ayırmanın sebebi de bu.
    """

    def kur(self, dolu_depo, kok, *ek: str, ad: str = "t1"):
        return calistir(
            "paper", "baslat", ad,
            "--strateji", "sma_kesisim",
            "--parametre", "hizli=5",
            "--parametre", "yavas=20",
            "--depo", str(dolu_depo),
            "--kok", str(kok),
            "--pencere", "200",
            "--ag-yok",
            *ek,
        )

    def test_kurulum_temiz_baslangic(self, dolu_depo, tmp_path):
        sonuc = self.kur(dolu_depo, tmp_path / "paper")
        assert sonuc.exit_code == 0, sonuc.stdout
        assert "temiz" in sonuc.stdout
        assert (tmp_path / "paper" / "t1.sqlite").exists()

    def test_gozlem_modu_uyarisi_gorunuyor(self, dolu_depo, tmp_path):
        # K-035: gözlem koşusunun kanıt üretmediği ekranda yazmıyorsa ekran yanıltır.
        sonuc = self.kur(dolu_depo, tmp_path / "paper")
        assert "kanıtı üretmez" in sonuc.stdout

    def test_gecersiz_mod_reddediliyor(self, dolu_depo, tmp_path):
        sonuc = self.kur(dolu_depo, tmp_path / "paper", "--mod", "live")
        assert sonuc.exit_code != 0

    def test_ayni_ada_farkli_konfigurasyon_hata(self, dolu_depo, tmp_path):
        # Konfigürasyon koşu kimliğinin parçası ve değişmez (K-009).
        kok = tmp_path / "paper"
        assert self.kur(dolu_depo, kok).exit_code == 0
        ikinci = calistir(
            "paper", "baslat", "t1",
            "--strateji", "ema_kesisim",
            "--depo", str(dolu_depo), "--kok", str(kok), "--ag-yok",
        )
        assert ikinci.exit_code != 0

    def test_ayni_konfigurasyon_toparlaniyor(self, dolu_depo, tmp_path):
        kok = tmp_path / "paper"
        assert self.kur(dolu_depo, kok).exit_code == 0
        assert self.kur(dolu_depo, kok).exit_code == 0

    def test_durum_okunuyor(self, dolu_depo, tmp_path):
        kok = tmp_path / "paper"
        self.kur(dolu_depo, kok)
        sonuc = calistir("paper", "durum", "t1", "--kok", str(kok), "--json")
        assert sonuc.exit_code == 0
        govde = json.loads(sonuc.stdout)
        assert govde["kosu"]["mod"] == "gozlem"
        assert govde["kesinti_sayisi"] == 0
        assert govde["fill_sayisi"] == 0

    def test_olaylar_kesinti_sayisiyla(self, dolu_depo, tmp_path):
        # `--ag-yok` yalnızca kurar: koşturucu hiç çalışmadığı için `basladi`/`durdu`
        # çifti yazılmaz ve günlük boş kalır. Bu doğru davranış — kurulmuş ama
        # başlatılmamış bir koşuyu "başladı" diye kaydetmek, sonraki başlangıcın onu
        # temiz kapanmamış bir oturum sanmasına yol açardı.
        kok = tmp_path / "paper"
        self.kur(dolu_depo, kok)
        sonuc = calistir("paper", "olaylar", "t1", "--kok", str(kok), "--json")
        govde = json.loads(sonuc.stdout)
        assert govde["kesinti_sayisi"] == 0
        assert govde["olaylar"] == []

    def test_kurulum_tek_basina_kesinti_uretmiyor(self, dolu_depo, tmp_path):
        # Üst üste iki kurulum, olmayan bir çökme uydurmamalı.
        kok = tmp_path / "paper"
        self.kur(dolu_depo, kok)
        self.kur(dolu_depo, kok)
        govde = json.loads(
            calistir("paper", "olaylar", "t1", "--kok", str(kok), "--json").stdout
        )
        assert govde["kesinti_sayisi"] == 0

    def test_olmayan_kosu_hata(self, tmp_path):
        assert calistir("paper", "durum", "yok", "--kok", str(tmp_path)).exit_code != 0

    def test_parametre_bicimi_zorlaniyor(self, dolu_depo, tmp_path):
        sonuc = calistir(
            "paper", "baslat", "t2", "--parametre", "hizli5",
            "--depo", str(dolu_depo), "--kok", str(tmp_path), "--ag-yok",
        )
        assert sonuc.exit_code != 0
