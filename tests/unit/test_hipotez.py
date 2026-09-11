"""Hipotez defteri: kaç çekiliş yapıldığının kaydı. (K-039)

K-019'un yedi kapısı strateji **başına** çalışıyor. Hiçbiri "bu kaçıncı denemeydi"
sorusunu sormuyor — ve o soru sorulmadığı sürece, yeterince çok deneyen biri eşiğe hiç
dokunmadan K-018'in *"sayısal eşik esnetilemez"* kuralını deler. Hiçbir test kırılmaz,
hiçbir kural çiğnenmez, ve sonunda "kapıları geçen bir strateji" ortaya çıkar.

Bu dosyanın test ettiği şey defterin kendisi değil, **ön kayıt disiplini**: sonucu
gördükten sonra yazılan bir hipotez kanıt değildir.
"""

from __future__ import annotations

import pytest

from scryne_quant.research.hipotez import Hipotez, HipotezDefteri, HipotezHatasi

GEREKCE = "Faz 4'te 1h'te çalışmayan trend takibinin 4h'te denenmesi; hipotez önceden yazıldı."


def hipotez(**degisiklik) -> Hipotez:
    alanlar = {
        "strateji": "ema_kesisim",
        "timeframe": "1h",
        "veri_sha256": "a" * 64,
        "izgara": {"hizli": [10, 20], "yavas": [50, 100]},
        "gerekce": GEREKCE,
    }
    return Hipotez.kur(**{**alanlar, **degisiklik})


class TestHipotez:
    def test_gerekce_zorunlu(self) -> None:
        # Gerekçesiz bir hipotez, ızgarayı genişletmenin kibar adıdır.
        with pytest.raises(HipotezHatasi, match="gerekçe"):
            hipotez(gerekce="deneme")

    def test_bos_strateji_reddediliyor(self) -> None:
        with pytest.raises(HipotezHatasi):
            hipotez(strateji="")

    def test_kimlik_icerikten_tureiyor(self) -> None:
        assert hipotez().kimlik == hipotez().kimlik
        assert hipotez().kimlik != hipotez(timeframe="4h").kimlik
        assert hipotez().kimlik != hipotez(izgara={"hizli": [10]}).kimlik
        assert hipotez().kimlik != hipotez(veri_sha256="b" * 64).kimlik

    def test_gerekce_kimligi_degistirmiyor(self) -> None:
        # Aynı soruyu farklı kelimelerle sormak yeni bir çekiliş değil.
        baska = "Tamamen farklı bir cümleyle yazılmış ama aynı soruyu soran gerekçe metni."
        assert hipotez().kimlik == hipotez(gerekce=baska).kimlik

    def test_izgara_sirasi_kimligi_degistirmiyor(self) -> None:
        a = hipotez(izgara={"hizli": [10, 20], "yavas": [50, 100]})
        b = hipotez(izgara={"yavas": [50, 100], "hizli": [10, 20]})
        assert a.kimlik == b.kimlik


class TestDefter:
    def test_bos_defter(self, tmp_path) -> None:
        d = HipotezDefteri(tmp_path / "h.jsonl")
        assert d.sayi() == 0
        assert d.tumu() == []
        assert d.ozet()["toplam"] == 0

    def test_kaydedip_sayiyor(self, tmp_path) -> None:
        d = HipotezDefteri(tmp_path / "h.jsonl")
        assert d.kaydet(hipotez()) == 1
        assert d.kaydet(hipotez(timeframe="4h")) == 2
        assert d.kaydet(hipotez(strateji="donchian")) == 3
        assert d.sayi() == 3

    def test_ayni_hipotez_yeni_cekilis_degil(self, tmp_path) -> None:
        # Aynı soruyu iki kez sormak yeni bir bilgi üretmez.
        d = HipotezDefteri(tmp_path / "h.jsonl")
        assert d.kaydet(hipotez()) == 1
        assert d.kaydet(hipotez()) == 1
        assert d.sayi() == 1

    def test_farkli_izgara_yeni_cekilis(self, tmp_path) -> None:
        # Ama ızgarayı genişletmek yeni bir çekiliştir ve sayılmak zorunda — bu modülün
        # var olma sebebi tam olarak bu.
        d = HipotezDefteri(tmp_path / "h.jsonl")
        d.kaydet(hipotez(izgara={"hizli": [10, 20]}))
        assert d.kaydet(hipotez(izgara={"hizli": [10, 20, 30, 40, 50]})) == 2

    def test_defter_append_only_kaliyor(self, tmp_path) -> None:
        yol = tmp_path / "h.jsonl"
        d = HipotezDefteri(yol)
        d.kaydet(hipotez())
        d.kaydet(hipotez(timeframe="4h"))
        assert len([s for s in yol.read_text(encoding="utf-8").splitlines() if s]) == 2

    def test_ozet_strateji_basina_sayiyor(self, tmp_path) -> None:
        d = HipotezDefteri(tmp_path / "h.jsonl")
        d.kaydet(hipotez())
        d.kaydet(hipotez(timeframe="4h"))
        d.kaydet(hipotez(strateji="donchian"))
        assert d.ozet()["strateji_basina"] == {"donchian": 1, "ema_kesisim": 2}


class TestOnKayit:
    """Sonucu gördükten sonra yazılan bir hipotez kanıt değildir."""

    def test_kayitsiz_hipotez_dogrulanmiyor(self, tmp_path) -> None:
        d = HipotezDefteri(tmp_path / "h.jsonl")
        with pytest.raises(HipotezHatasi, match="önceden kaydedilmemiş"):
            d.dogrula(hipotez())

    def test_kayitli_hipotez_sirasini_veriyor(self, tmp_path) -> None:
        d = HipotezDefteri(tmp_path / "h.jsonl")
        d.kaydet(hipotez())
        d.kaydet(hipotez(timeframe="4h"))
        assert d.dogrula(hipotez(timeframe="4h")) == 2

    def test_sira_kayitsizda_none(self, tmp_path) -> None:
        d = HipotezDefteri(tmp_path / "h.jsonl")
        assert d.sira(hipotez()) is None
