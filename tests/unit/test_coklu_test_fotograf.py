"""Ölçüm fotoğrafı (`coklu_test_fotograf`): bekçinin kaynağı tutarsızsa hiç yazılmaz. (K-081 D3)"""

from __future__ import annotations

import pytest

from scryne_quant.research import coklu_test_fotograf as f


def _birlesik(olculebilir: int, defter: int) -> dict:
    return {
        "olculebilir": olculebilir, "defter_sayisi": defter, "tek_sembollu": olculebilir,
        "evren": 0, "mevcut_esik": 1.04, "uretildi": "2026-09-20 17:36:57 UTC",
        "git": {"commit": "abc", "dirty": False},
        "null": {"deneme": 500, "seed": 0},
        "duzeltilmis_esikler": {"0.05": 1.0039},
        "esik_guven_araliklari": {"0.05": [0.98, 1.06]},
        "mevcut_esigin_yanlis_pozitifi": 0.042,
    }


@pytest.fixture
def defter_dosyasi(tmp_path):
    p = tmp_path / "defter.jsonl"
    p.write_text('{"kimlik":"a"}\n{"kimlik":"b"}\n{"kimlik":"c"}\n', encoding="utf-8")
    return p


class TestKur:
    def test_tutarli_fotograf(self, defter_dosyasi, tmp_path):
        foto = f.kur(_birlesik(2, 3), ["b", "a"], ["a", "b", "c"], defter_dosyasi, "x.json")
        assert foto["cekilis_kimlikleri"] == ["a", "b"]
        assert foto["olculemez_kimlikleri"] == ["c"]
        assert foto["defter_sayisi"] == 3 and foto["olculebilir"] == 2
        assert len(foto["defter_sha256"]) == 64
        yol = f.yaz(foto, tmp_path / "foto.json")
        assert f.oku(yol) == foto

    def test_olculen_defterde_yoksa_hata(self, defter_dosyasi):
        with pytest.raises(f.FotografHatasi, match="defterde yok"):
            f.kur(_birlesik(2, 3), ["a", "z"], ["a", "b", "c"], defter_dosyasi, "x")

    def test_onbellek_sayisi_ciktiyla_uyusmazsa_hata(self, defter_dosyasi):
        with pytest.raises(f.FotografHatasi, match="önbellek"):
            f.kur(_birlesik(3, 3), ["a", "b"], ["a", "b", "c"], defter_dosyasi, "x")

    def test_defter_sayisi_ciktiyla_uyusmazsa_hata(self, defter_dosyasi):
        with pytest.raises(f.FotografHatasi, match="defter"):
            f.kur(_birlesik(2, 2), ["a", "b"], ["a", "b", "c"], defter_dosyasi, "x")

    def test_tekrarlanan_kimlik_hata(self, defter_dosyasi):
        with pytest.raises(f.FotografHatasi, match="tekrarlanan"):
            f.kur(_birlesik(2, 3), ["a", "b"], ["a", "b", "b"], defter_dosyasi, "x")

    def test_fotograf_yoksa_oku_hata(self, tmp_path):
        with pytest.raises(f.FotografHatasi, match="fotoğrafı yok"):
            f.oku(tmp_path / "yok.json")
