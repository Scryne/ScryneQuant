"""Veri sonu sabitleme ve geri sarma (K-080).

W3 denetiminin bulgusu: veri seti kimliği dosyanın SHA-256'sı ve OOS penceresi veri sonuna
göreli; depo uzatılınca kayıtlı deneylerin **hiçbiri** yeniden üretilemedi (0/16). Bu dosya o
bulgunun kapandığını üç katmanda kanıtlıyor:

1. **Depo:** uzatılmış bir depo eski veri sonuna kırpılınca dosya **bayt düzeyinde** eski
   dosyaya döner (`TestDepoKirp`).
2. **İndiriciler:** REST ve arşiv indiricileri `bitis_gun` ile sabitlenince sınırın ötesini
   indirmez, depoda varsa atar; sabitlenmiş depo, o güne kadar sıfırdan indirilmiş depoyla
   aynı bayttır; sabiti kaldırıp uzatmak da eski dosyayı geri verir (`TestRestVeriSonu`,
   `TestArsivVeriSonu`).
3. **Kayıt zinciri:** `sq lab tara` kaydı `veri_son_ms` taşır; depo uzatılınca `sq lab dogrula`
   reddeder, `--geri-sar` ile depo kaydın veri sonuna döner ve deney **yeniden üretilir**;
   K-080 öncesi kayıtlar (`veri_son_ms` yok) için adres elle verilir (`TestDogrulaGeriSar`).

Kanıt gerçek depodan da alındı (2026-09-20): `data/market/BTCUSDT/1h.parquet` (45.828 bar,
2026-09-19'a kadar) 2026-09-09 10:00 UTC'ye kırpılınca defterdeki 38 tek sembollü çekilişin
`veri_sha256`'sı (`e3adb02c…`, 45.576 bar) bayt düzeyinde geri geldi.
"""

from __future__ import annotations

import json
import shutil

import pandas as pd
import pytest
from typer.testing import CliRunner

from scryne_quant.cli import main as cli
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.arsiv_indirici import ArsivIndirici, ArsivIndirmeHatasi
from scryne_quant.data.depo import DepoHatasi, ParquetDepo
from scryne_quant.data.dogrulama import dogrula
from scryne_quant.data.indirici import IndirmeHatasi, TarihselIndirici
from scryne_quant.research import tekrar
from tests.conftest import bar_uret
from tests.unit.test_arsiv_indirici import (
    ARALIK_2024_12,
    ARALIK_2025_01,
    ARALIK_2025_02,
    SAAT,
    SahteArsiv,
    zip_getirmeleri,
)
from tests.unit.test_indirici import BASLANGIC, SahteAdaptor, seri, tam_aralik

runner = CliRunner()
SAAT_MS = timeframe_ms("1h")


def _metin(sonuc) -> str:
    """CliRunner'da yakalanmayan istisna stdout'a değil `exception`a düşer."""
    return sonuc.stdout + ("" if sonuc.exception is None else str(sonuc.exception))


def _bayrakli(n: int, baslangic_ms: int = BASLANGIC, tohum: int = 42) -> pd.DataFrame:
    ham = bar_uret(n=n, baslangic_ms=baslangic_ms, tohum=tohum).drop(columns=["quality_status"])
    bayrakli, _ = dogrula(ham, "1h", sembol="BTCUSDT")
    return bayrakli


def _uzat(depo: ParquetDepo, ek: int, tohum: int = 7) -> None:
    """Depoyu `ek` yeni barla **uzatır** — mevcut barlara dokunmaz (indirici gibi)."""
    mevcut = depo.oku("BTCUSDT", "1h")
    son = int(mevcut["open_time"].iloc[-1])
    yeni = bar_uret(n=ek, baslangic_ms=son + SAAT_MS, tohum=tohum).drop(
        columns=["quality_status"]
    )
    ham = pd.concat(
        [mevcut.drop(columns=["quality_status"]), yeni], ignore_index=True
    )
    bayrakli, _ = dogrula(ham, "1h", sembol="BTCUSDT")
    depo.yaz("BTCUSDT", "1h", bayrakli)


# ------------------------------------------------------------------ 1. depo


class TestDepoKirp:
    def test_uzatilmis_depo_kirpilinca_bayt_duzeyinde_eskiye_donuyor(self, depo_kok):
        depo = ParquetDepo(depo_kok)
        ilk = depo.yaz("BTCUSDT", "1h", _bayrakli(300))
        eski_bayt = depo.yol("BTCUSDT", "1h").read_bytes()

        _uzat(depo, 100)
        assert depo.sha256("BTCUSDT", "1h") != ilk.sha256, "uzatma hash'i değiştirmeli"

        kirpma = depo.kirp("BTCUSDT", "1h", ilk.son_ms + SAAT_MS)

        assert kirpma.sha256 == ilk.sha256
        assert kirpma.bar_sayisi == 300
        assert depo.yol("BTCUSDT", "1h").read_bytes() == eski_bayt

    def test_kirpilacak_bar_yoksa_dosyaya_dokunulmuyor(self, depo_kok):
        depo = ParquetDepo(depo_kok)
        ilk = depo.yaz("BTCUSDT", "1h", _bayrakli(50))
        mtime = depo.yol("BTCUSDT", "1h").stat().st_mtime_ns

        kirpma = depo.kirp("BTCUSDT", "1h", ilk.son_ms + 10 * SAAT_MS)

        assert kirpma.sha256 == ilk.sha256
        assert depo.yol("BTCUSDT", "1h").stat().st_mtime_ns == mtime

    def test_her_sey_kirpilirsa_hata(self, depo_kok):
        depo = ParquetDepo(depo_kok)
        depo.yaz("BTCUSDT", "1h", _bayrakli(50))
        with pytest.raises(DepoHatasi):
            depo.kirp("BTCUSDT", "1h", BASLANGIC)

    def test_geri_sar_yardimcisi_son_bari_dahil_tutuyor(self, depo_kok):
        depo = ParquetDepo(depo_kok)
        depo.yaz("BTCUSDT", "1h", _bayrakli(100))
        hedef_son = BASLANGIC + 59 * SAAT_MS

        kirpma = tekrar.geri_sar(depo, "BTCUSDT", "1h", hedef_son)

        assert kirpma.bar_sayisi == 60
        assert kirpma.son_ms == hedef_son


# ------------------------------------------------------------------ 2. REST


class TestRestVeriSonu:
    """`TarihselIndirici(bitis_gun=...)`: 2023-11-14 22:00'de başlayan 2.500 barlık seri."""

    GUN = "2023-11-20"  # seri içinde bir gün; ertesi 00:00 = sınır

    @staticmethod
    def _sinir_ms() -> int:
        return int((pd.Timestamp("2023-11-20", tz="UTC") + pd.Timedelta(days=1)).value // 1e6)

    def test_gecersiz_gun_reddediliyor(self, depo_kok):
        with pytest.raises(IndirmeHatasi):
            TarihselIndirici(SahteAdaptor(seri(10)), ParquetDepo(depo_kok), bitis_gun="20231120")

    def test_sabit_depo_sinirin_otesini_ne_ister_ne_yazar(self, depo_kok):
        barlar = seri(2_500)
        adaptor = SahteAdaptor(barlar)
        indirici = TarihselIndirici(adaptor, ParquetDepo(depo_kok), bitis_gun=self.GUN)
        bas, bit = tam_aralik(barlar)

        sonuc = indirici.indir("BTCUSDT", "1h", bas, bit)

        assert sonuc.aralik.bitis_ms == self._sinir_ms()
        assert all(b <= self._sinir_ms() for _, b in adaptor.cagrilar)
        assert sonuc.depo.son_ms == self._sinir_ms() - SAAT_MS

    def test_uzatilmis_depo_sabitlenince_sifirdan_sabit_depoyla_ayni_bayt(
        self, depo_kok, tmp_path
    ):
        barlar = seri(2_500)
        bas, bit = tam_aralik(barlar)

        # A: baştan sabit
        a_kok = tmp_path / "a"
        a = TarihselIndirici(SahteAdaptor(barlar), ParquetDepo(a_kok), bitis_gun=self.GUN)
        a_sonuc = a.indir("BTCUSDT", "1h", bas, bit)

        # B: önce tam indir (uzun), sonra sabitle — ağ kullanmadan kırpılmalı
        b_depo = ParquetDepo(depo_kok)
        TarihselIndirici(SahteAdaptor(barlar), b_depo).indir("BTCUSDT", "1h", bas, bit)
        assert b_depo.sha256("BTCUSDT", "1h") != a_sonuc.depo.sha256
        b_adaptor = SahteAdaptor(barlar)
        b_sonuc = TarihselIndirici(b_adaptor, b_depo, bitis_gun=self.GUN).indir(
            "BTCUSDT", "1h", bas, bit
        )

        assert b_sonuc.inen_bar == 0 and b_adaptor.cagrilar == []
        assert b_sonuc.degisti is True
        assert b_sonuc.depo.sha256 == a_sonuc.depo.sha256
        assert (
            ParquetDepo(a_kok).yol("BTCUSDT", "1h").read_bytes()
            == b_depo.yol("BTCUSDT", "1h").read_bytes()
        )

    def test_sabiti_kaldirip_uzatmak_eski_dosyayi_geri_veriyor(self, depo_kok):
        barlar = seri(2_500)
        bas, bit = tam_aralik(barlar)
        depo = ParquetDepo(depo_kok)
        tam = TarihselIndirici(SahteAdaptor(barlar), depo).indir("BTCUSDT", "1h", bas, bit)

        TarihselIndirici(SahteAdaptor(barlar), depo, bitis_gun=self.GUN).indir(
            "BTCUSDT", "1h", bas, bit
        )
        assert depo.sha256("BTCUSDT", "1h") != tam.depo.sha256

        yeniden = TarihselIndirici(SahteAdaptor(barlar), depo).indir("BTCUSDT", "1h", bas, bit)

        assert yeniden.depo.sha256 == tam.depo.sha256


# ------------------------------------------------------------------ 3. arşiv


class TestArsivVeriSonu:
    """Aylık 2024-12, 2025-01 + günlük 2025-02-01/02 arşivi (test_arsiv_indirici fixture'ı)."""

    @staticmethod
    def _arsiv() -> SahteArsiv:
        arsiv = SahteArsiv()
        arsiv.aylik("BTCUSDT", "2024-12", ARALIK_2024_12, 744)
        arsiv.aylik("BTCUSDT", "2025-01", ARALIK_2025_01, 744, fiyat=844.0)
        arsiv.gunluk("BTCUSDT", "2025-02-01", ARALIK_2025_02, fiyat=1588.0)
        arsiv.gunluk("BTCUSDT", "2025-02-02", ARALIK_2025_02 + 24 * SAAT, fiyat=1612.0)
        return arsiv

    def test_gecersiz_gun_reddediliyor(self, depo_kok):
        with pytest.raises(ValueError):
            ArsivIndirici(self._arsiv(), ParquetDepo(depo_kok), bitis_gun="2025-2-1")

    def test_plan_bitis_gununun_ayini_aylik_katmandan_almiyor(self, depo_kok):
        indirici = ArsivIndirici(self._arsiv(), ParquetDepo(depo_kok), bitis_gun="2025-01-15")
        aylik, gunluk = indirici.plan("BTCUSDT", "1h")
        assert list(aylik) == ["2024-12"]
        assert gunluk == {}  # Ocak'ın günlükleri sahte arşivde yok: ay kurulamaz, atlanır

    def test_sabit_depo_sinirin_otesini_indirmiyor_ve_manifesto_tarihi_tasiyor(self, depo_kok):
        arsiv = self._arsiv()
        depo = ParquetDepo(depo_kok)
        indirici = ArsivIndirici(arsiv, depo, bitis_gun="2025-02-01")

        sonuc = indirici.indir("BTCUSDT")

        assert sonuc.depo is not None and sonuc.depo.bar_sayisi == 744 + 744 + 24
        assert not any(a.endswith("2025-02-02.zip") for a in zip_getirmeleri(arsiv))
        govde = json.loads(indirici.manifesto_yolu("BTCUSDT", "1h").read_text(encoding="utf-8"))
        assert govde["bitis_gun"] == "2025-02-01"
        assert not any(a.endswith("2025-02-02.zip") for a in govde["dosyalar"])

    def test_uzatilmis_depo_sabitlenince_sifirdan_sabit_depoyla_ayni_bayt(self, tmp_path):
        a_depo = ParquetDepo(tmp_path / "a")
        a = ArsivIndirici(self._arsiv(), a_depo, bitis_gun="2025-02-01").indir("BTCUSDT")

        b_depo = ParquetDepo(tmp_path / "b")
        tam = ArsivIndirici(self._arsiv(), b_depo).indir("BTCUSDT")
        assert tam.depo is not None and a.depo is not None
        assert tam.depo.sha256 != a.depo.sha256
        arsiv = self._arsiv()
        b = ArsivIndirici(arsiv, b_depo, bitis_gun="2025-02-01").indir("BTCUSDT")

        assert zip_getirmeleri(arsiv) == []  # geri sarım ağ kullanmaz
        assert b.depo is not None and b.depo.sha256 == a.depo.sha256
        assert (
            a_depo.yol("BTCUSDT", "1h").read_bytes() == b_depo.yol("BTCUSDT", "1h").read_bytes()
        )
        # sabiti kaldırınca yalnız 02-02 iner ve tam dosya geri gelir
        arsiv2 = self._arsiv()
        yeniden = ArsivIndirici(arsiv2, b_depo).indir("BTCUSDT")
        assert [a.rsplit("/", 1)[-1] for a in zip_getirmeleri(arsiv2)] == [
            "BTCUSDT-1h-2025-02-02.zip"
        ]
        assert yeniden.depo is not None and yeniden.depo.sha256 == tam.depo.sha256

    def test_sinirdan_once_dosya_yoksa_veri_yok_sonucu(self, depo_kok):
        """Arşivin mevcut sözleşmesi: dosya yoksa hata değil `veri_yok` (delist edilmiş
        sembollerle aynı yol). Sabitleme bunu değiştirmez."""
        sonuc = ArsivIndirici(
            self._arsiv(), ParquetDepo(depo_kok), bitis_gun="2024-01-01"
        ).indir("BTCUSDT")
        assert sonuc.veri_yok and sonuc.depo is None

    def test_sinirin_otesi_kirpilinca_depo_bos_kalirsa_hata(self, depo_kok):
        depo = ParquetDepo(depo_kok)
        ArsivIndirici(self._arsiv(), depo).indir("BTCUSDT")
        with pytest.raises(ArsivIndirmeHatasi):
            ArsivIndirici(self._arsiv(), depo, bitis_gun="2024-01-01").indir("BTCUSDT")


# ------------------------------------------------------------------ 4. kayıt zinciri


@pytest.fixture
def lab_ortami(tmp_path, monkeypatch):
    """`sq lab tara` için gereken her şey geçici dizinde: depo, maliyet, program, hipotez."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    shutil.copy(cli.Path(__file__).resolve().parents[2] / "config" / "maliyet.json",
                tmp_path / "config" / "maliyet.json")
    depo_kok = tmp_path / "depo"
    ParquetDepo(depo_kok).yaz("BTCUSDT", "1h", _bayrakli(400))

    acilis = runner.invoke(cli.app, [
        "lab", "program-kaydet", "geri_sarim_testi",
        "-g", (
            "K-080 geri sarma zincirini uçtan uca ölçen test programı: depo uzatılınca "
            "kayıt reddedilmeli, geri sarılınca yeniden üretilmeli."
        ),
        "-k", (
            "Kaynak farkı bu testte bir kurgu; gerçek bir programda K-051 ölçüyle yazılır "
            "ve program kaydı o ölçüye atıf yapar."
        ),
        "--kaynak-olcumu", '{"test": 1}', "-n", "1",
        "-d", "Tek çekilişlik bütçe.", "--esik-tahmini", '{"tahmin": 1.04}',
    ])
    assert acilis.exit_code == 0, acilis.stdout
    kayit = runner.invoke(cli.app, [
        "lab", "hipotez-kaydet", "sma_kesisim", "-p", "geri_sarim_testi",
        "-g", "geri sarma testinin ön kaydı; sonuç görülmeden yazıldı",
        "--depo", str(depo_kok), "--json",
    ])
    assert kayit.exit_code == 0, kayit.stdout
    return depo_kok


class TestDogrulaGeriSar:
    def _tara(self, depo_kok, tmp_path):
        sonuc = runner.invoke(cli.app, [
            "lab", "tara", "sma_kesisim", "--depo", str(depo_kok),
            "--deney-kok", str(tmp_path / "deneyler"), "--json",
        ])
        assert sonuc.exit_code == 0, sonuc.stdout
        kayitlar = list((tmp_path / "deneyler" / "tarama").glob("*.json"))
        assert len(kayitlar) == 1
        return kayitlar[0]

    def test_hipotez_defteri_veri_sonunu_tasiyor(self, lab_ortami, tmp_path):
        satirlar = (tmp_path / "docs" / "Hipotez-Defteri.jsonl").read_text(encoding="utf-8")
        kayit = json.loads(satirlar.strip().splitlines()[-1])
        assert kayit["veri_son_ms"] == BASLANGIC + 399 * SAAT_MS

    def test_kayit_veri_sonunu_tasiyor_ve_uzatma_sonrasi_geri_sarilip_uretiliyor(
        self, lab_ortami, tmp_path
    ):
        depo_kok = lab_ortami
        kayit_yolu = self._tara(depo_kok, tmp_path)
        kayit = json.loads(kayit_yolu.read_text(encoding="utf-8"))
        assert kayit["kimlik"]["veri_son_ms"] == BASLANGIC + 399 * SAAT_MS
        eski_hash = kayit["kimlik"]["veri_sha256"]

        temiz = runner.invoke(cli.app, ["lab", "dogrula", str(kayit_yolu), "--depo", str(depo_kok)])
        assert temiz.exit_code == 0, temiz.stdout

        _uzat(ParquetDepo(depo_kok), 120)
        red = runner.invoke(cli.app, ["lab", "dogrula", str(kayit_yolu), "--depo", str(depo_kok)])
        assert red.exit_code == 1 and "veri seti değişmiş" in _metin(red)

        geri = runner.invoke(cli.app, [
            "lab", "dogrula", str(kayit_yolu), "--depo", str(depo_kok), "--geri-sar", "--json",
        ])
        assert geri.exit_code == 0, geri.stdout
        govde = json.loads(geri.stdout)
        assert govde["ayni"] is True
        assert govde["geri_sarildi"]["hash_geri_geldi"] is True
        assert govde["geri_sarildi"]["bar_sayisi"] == 400
        assert ParquetDepo(depo_kok).sha256("BTCUSDT", "1h") == eski_hash

    def test_eski_kayit_adressiz_geri_sarilamiyor_adresle_sariliyor(self, lab_ortami, tmp_path):
        depo_kok = lab_ortami
        kayit_yolu = self._tara(depo_kok, tmp_path)
        kayit = json.loads(kayit_yolu.read_text(encoding="utf-8"))
        kayit["kimlik"].pop("veri_son_ms")  # K-080 öncesi kayıt gibi
        kayit_yolu.write_text(json.dumps(kayit, ensure_ascii=False), encoding="utf-8")
        _uzat(ParquetDepo(depo_kok), 30)

        adressiz = runner.invoke(cli.app, [
            "lab", "dogrula", str(kayit_yolu), "--depo", str(depo_kok), "--geri-sar",
        ])
        assert adressiz.exit_code == 1 and "veri_son_ms" in adressiz.stdout

        son_bar = pd.Timestamp(BASLANGIC + 399 * SAAT_MS, unit="ms").strftime("%Y-%m-%d %H:%M")
        adresli = runner.invoke(cli.app, [
            "lab", "dogrula", str(kayit_yolu), "--depo", str(depo_kok),
            "--geri-sar", "--veri-sonu", son_bar, "--json",
        ])
        assert adresli.exit_code == 0, adresli.stdout
        assert json.loads(adresli.stdout)["geri_sarildi"]["hash_geri_geldi"] is True

    def test_geri_sarim_hashi_geri_getirmezse_red_kaliyor(self, lab_ortami, tmp_path):
        """Kırpma bir tahmin değil: yanlış adres verilirse red aynen kalır."""
        depo_kok = lab_ortami
        kayit_yolu = self._tara(depo_kok, tmp_path)
        _uzat(ParquetDepo(depo_kok), 30)
        yanlis = pd.Timestamp(BASLANGIC + 380 * SAAT_MS, unit="ms").strftime("%Y-%m-%d %H:%M")

        sonuc = runner.invoke(cli.app, [
            "lab", "dogrula", str(kayit_yolu), "--depo", str(depo_kok),
            "--geri-sar", "--veri-sonu", yanlis, "--json",
        ])
        assert sonuc.exit_code == 1
        assert "veri seti değişmiş" in _metin(sonuc)

    def test_veri_sonu_geri_sar_olmadan_reddediliyor(self, lab_ortami, tmp_path):
        kayit_yolu = self._tara(lab_ortami, tmp_path)
        sonuc = runner.invoke(cli.app, [
            "lab", "dogrula", str(kayit_yolu), "--depo", str(lab_ortami),
            "--veri-sonu", "2023-11-20 00:00",
        ])
        assert sonuc.exit_code != 0


# ------------------------------------------------------------------ 5. defter kimliği


class TestHipotezKimligi:
    def test_veri_sonu_kimlige_girmiyor_ama_kayda_yaziliyor(self):
        from scryne_quant.research.hipotez import Hipotez

        ortak = dict(
            strateji="sma_kesisim", timeframe="1h", veri_sha256="a" * 64,
            izgara={"hizli": [5, 10]},
            gerekce="geri sarma adresi kimliği değiştirmemeli, çekiliş aynı",
        )
        eski = Hipotez.kur(**ortak)
        yeni = Hipotez.kur(**ortak, veri_son_ms=BASLANGIC + 99 * SAAT_MS)

        assert eski.kimlik == yeni.kimlik
        assert eski.sozluk()["veri_son_ms"] is None
        assert yeni.sozluk()["veri_son_ms"] == BASLANGIC + 99 * SAAT_MS
