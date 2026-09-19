"""Jev karar defteri: append-only, zincir hash, durum geri bulunur, sır yok. (K-074/5)"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.jev import ayarlar as ayar_mod
from scryne_quant.jev.defter import (
    KOK_HASH,
    DefterHatasi,
    JevDefteri,
    OlayTuru,
    kosu_kimligi_kur,
)
from scryne_quant.jev.durum import durum_hash, kanonik_durum
from scryne_quant.jev.karar import JevKarari, KararDurumu, karar_kur
from scryne_quant.jev.sorular import soru_sha256
from tests.conftest import bar_uret

SAAT = 3_600_000


@pytest.fixture
def ayar():
    return ayar_mod.yukle()


@pytest.fixture
def diziler():
    return bar_dizileri(bar_uret(n=400, tohum=3))


def _yanit(flat: float = 0.7) -> dict[str, Any]:
    long = round(1 - flat - 0.05, 2)
    return {
        "model": "jev-1.13.0",
        "usage": {"input_tokens": 100, "output_tokens": 10},
        "answers": {
            "yon": {
                "choice": "flat",
                "confidence": 0.6,
                "probabilities": {"long": long, "short": 0.05, "flat": flat},
            },
            "rejim": {
                "choice": "aralik",
                "confidence": 0.5,
                "probabilities": {
                    "trend_yukari": 0.2,
                    "trend_asagi": 0.1,
                    "aralik": 0.5,
                    "yuksek_volatilite": 0.1,
                    "belirsiz": 0.1,
                },
            },
            "kurulum": {"score": 1.2, "confidence": 0.4},
            "cekimser": {"noul": 0.3},
        },
    }


def _karar(
    diziler, i, ayar, *, kod=KararDurumu.GECERLI, yanit=None, uretim_ek=1_000, kosu="golge-t"
):
    d = kanonik_durum(diziler, i, sembol="BTCUSDT")
    k = karar_kur(
        kosu=kosu,
        durum=d,
        durum_hash=durum_hash(d),
        soru_sha256=soru_sha256(ayar.model),
        model_istenen=ayar.model,
        uretim_ms=d["veri_kesimi_ms"] + uretim_ek,
        bayat_ms=ayar.bayat_ms,
        yon_marji=ayar.yon_marji,
        egitim_kesim_ms=None,
        yanit=yanit if yanit is not None else (_yanit() if kod is KararDurumu.GECERLI else None),
        durum_kodu=kod,
        hata=None if kod is KararDurumu.GECERLI else "sebep",
        gecikme_ms=300,
    )
    return d, k


class TestKosu:
    def test_kimlik_yazilir_ve_okunur(self, ayar):
        with JevDefteri() as df:
            kim = kosu_kimligi_kur("golge-1", "golge", ayar, soru_sha256(ayar.model))
            df.kosu_yaz(kim)
            okunan = df.kosu_oku()
        assert okunan["kosu"] == "golge-1" and okunan["mod"] == "golge"
        assert okunan["ayarlar"]["model"] == ayar.model and "commit" in okunan["git"]
        assert okunan["ayarlar"]["egitim_kesim_ms"] is None

    def test_baska_kosu_ayni_dosyaya_yazamaz(self, ayar):
        with JevDefteri() as df:
            df.kosu_yaz(kosu_kimligi_kur("a", "golge", ayar, soru_sha256(ayar.model)))
            with pytest.raises(DefterHatasi):
                df.kosu_yaz(kosu_kimligi_kur("b", "golge", ayar, soru_sha256(ayar.model)))
            with pytest.raises(DefterHatasi):
                df.kosu_yaz(kosu_kimligi_kur("a", "golge", ayar, "f" * 64))

    def test_gecersiz_mod(self, ayar):
        with pytest.raises(DefterHatasi):
            kosu_kimligi_kur("a", "live", ayar, "x")


class TestKarar:
    def test_yaz_oku_zincir(self, diziler, ayar):
        with JevDefteri() as df:
            d, k = _karar(diziler, 300, ayar)
            h1 = df.karar_yaz(k, d, _yanit())
            d2, k2 = _karar(diziler, 301, ayar)
            h2 = df.karar_yaz(k2, d2, _yanit())
            satirlar = df.kararlar()
            assert [s["karar_id"] for s in satirlar] == [k.karar_id, k2.karar_id]
            assert satirlar[0]["onceki_hash"] == KOK_HASH and satirlar[1]["onceki_hash"] == h1
            assert satirlar[1]["satir_hash"] == h2
            assert satirlar[0]["durum"] == d and satirlar[0]["yanit"] == _yanit()
            assert JevKarari(**satirlar[0]["karar"]) == k
            assert df.dogrula()
            assert df.son_karar_ms() == k2.karar_ms
            assert df.sayim() == {"gecerli": 2}

    def test_durum_hashten_bulunur(self, diziler, ayar):
        with JevDefteri() as df:
            d, k = _karar(diziler, 300, ayar)
            df.karar_yaz(k, d, _yanit())
            assert df.durum_bul(k.durum_hash) == d
            assert df.durum_bul("0" * 64) is None

    def test_durum_hash_uyusmazsa_yazilmaz(self, diziler, ayar):
        with JevDefteri() as df:
            d, k = _karar(diziler, 300, ayar)
            baska = kanonik_durum(diziler, 299, sembol="BTCUSDT")
            with pytest.raises(DefterHatasi, match="uyuşmuyor"):
                df.karar_yaz(k, baska, _yanit())

    def test_ayni_bara_ikinci_gecerli_karar_yazilamaz(self, diziler, ayar):
        with JevDefteri() as df:
            d, k = _karar(diziler, 300, ayar)
            df.karar_yaz(k, d, _yanit())
            d, k2 = _karar(diziler, 300, ayar, uretim_ek=2_000)
            with pytest.raises(DefterHatasi, match="zaten var"):
                df.karar_yaz(k2, d, _yanit())

    def test_gecersizden_sonra_yeniden_deneme_ayri_satir(self, diziler, ayar):
        with JevDefteri() as df:
            d, k = _karar(diziler, 300, ayar, kod=KararDurumu.TIMEOUT)
            df.karar_yaz(k, d, None)
            d, k2 = _karar(diziler, 300, ayar, uretim_ek=2_000)
            df.karar_yaz(k2, d, _yanit())
            assert df.sayim() == {"timeout": 1, "gecerli": 1}
            assert len(df.kararlar(yalniz_gecerli=True)) == 1
            assert df.dogrula()

    def test_append_only_tetikleyiciler(self, diziler, ayar, tmp_path):
        yol = tmp_path / "d.sqlite"
        with JevDefteri(yol) as df:
            d, k = _karar(diziler, 300, ayar)
            df.karar_yaz(k, d, _yanit())
            df.olay_yaz(OlayTuru.BASLADI, {})
        b = sqlite3.connect(yol)
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            b.execute("UPDATE karar SET durum_kodu = 'x'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            b.execute("DELETE FROM karar")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            b.execute("DELETE FROM olay")
        b.close()

    def test_kurcalama_dogrulamada_yakalanir(self, diziler, ayar, tmp_path):
        yol = tmp_path / "d.sqlite"
        with JevDefteri(yol) as df:
            for i in (300, 301, 302):
                d, k = _karar(diziler, i, ayar)
                df.karar_yaz(k, d, _yanit())
            assert df.dogrula()
        b = sqlite3.connect(yol)
        b.execute("DROP TRIGGER karar_guncelleme_yok")
        satir = json.loads(b.execute("SELECT karar_json FROM karar WHERE id = 2").fetchone()[0])
        satir["yon"] = "long"
        satir["yon_olasiliklari"] = {"long": 0.9, "short": 0.05, "flat": 0.05}
        b.execute("UPDATE karar SET karar_json = ? WHERE id = 2", (json.dumps(satir),))
        b.commit()
        b.close()
        with JevDefteri(yol) as df:
            assert not df.dogrula()

    def test_dosya_kalici(self, diziler, ayar, tmp_path):
        yol = tmp_path / "runs" / "jev" / "g.sqlite"
        with JevDefteri(yol) as df:
            df.kosu_yaz(kosu_kimligi_kur("g", "golge", ayar, soru_sha256(ayar.model)))
            d, k = _karar(diziler, 300, ayar)
            df.karar_yaz(k, d, _yanit())
        with JevDefteri(yol) as df:
            assert df.kosu_oku()["kosu"] == "g" and len(df.kararlar()) == 1 and df.dogrula()


class TestOlay:
    def test_olay_yaz_oku(self):
        with JevDefteri() as df:
            df.olay_yaz(OlayTuru.BASLADI, {"pid": 1})
            df.olay_yaz(OlayTuru.HATA, {"mesaj": "x"}, zaman_ms=1_700_000_000_000)
            o = df.olaylar()
        assert [x["tur"] for x in o] == ["basladi", "hata"]
        assert o[1]["zaman_ms"] == 1_700_000_000_000 and o[1]["ayrinti"] == {"mesaj": "x"}
        assert [x["tur"] for x in JevDefteri().olaylar(tur=OlayTuru.HATA)] == []

    def test_olay_metninden_sir_temizlenir(self, monkeypatch):
        sir = "sk-typesafe-gizli-anahtar-123456"
        monkeypatch.setenv("TYPESAFE_API_KEY", sir)
        with JevDefteri() as df:
            df.olay_yaz(OlayTuru.HATA, {"mesaj": f"401 for {sir}"})
            o = df.olaylar()[0]
        assert sir not in json.dumps(o) and "[SIR]" in o["ayrinti"]["mesaj"]

    def test_tutarlilik_olcumu(self, diziler, ayar):
        with JevDefteri() as df:
            d, k1 = _karar(diziler, 300, ayar, yanit=_yanit(0.70))
            df.karar_yaz(k1, d, _yanit(0.70))
            _, k2 = _karar(diziler, 300, ayar, yanit=_yanit(0.64), uretim_ek=5_000)
            a = df.tutarlilik_yaz(k1, k2)
            assert a["ikisi_gecerli"] and a["yon_etiketi_ayni"]
            assert a["yon_sapma"] == pytest.approx(0.06)
            assert df.olaylar(tur=OlayTuru.TUTARLILIK)[0]["ayrinti"]["durum_hash"] == k1.durum_hash
            # İkinci sorgu karar olarak yazılmadı
            assert df.sayim() == {"gecerli": 1}

    def test_tutarlilik_farkli_durum_reddedilir(self, diziler, ayar):
        with JevDefteri() as df:
            _, k1 = _karar(diziler, 300, ayar)
            _, k2 = _karar(diziler, 301, ayar)
            with pytest.raises(DefterHatasi):
                df.tutarlilik_yaz(k1, k2)
