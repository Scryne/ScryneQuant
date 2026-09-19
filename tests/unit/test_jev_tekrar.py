"""Replay: kuru/gerçek koşu, kaldığı yerden devam, dondurma ve `leak_riski`. (K-049/5, K-074/3)"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import pytest

from scryne_quant.common.hash import dosya_hash
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.jev import ayarlar as ayar_mod
from scryne_quant.jev.defter import JevDefteri, OlayTuru
from scryne_quant.jev.durum import PENCERE_BAR, durum_hash, kanonik_durum
from scryne_quant.jev.tekrar import TekrarHatasi, dondur, kararlar_cercevesi, tekrar_kos
from tests.conftest import bar_uret

N = PENCERE_BAR + 60
ILK = PENCERE_BAR - 1


class _Cevap:
    def __init__(self, **k: Any) -> None:
        self.__dict__.update(k)


class _Yanit:
    def __init__(self, model: str, flat: float) -> None:
        self.model = model
        self.usage = _Cevap(input_tokens=1000, output_tokens=100)
        long = round(0.95 - flat, 2)
        self.answers = {
            "yon": _Cevap(
                choice="flat",
                confidence=0.5,
                probabilities={"long": long, "short": 0.05, "flat": flat},
            ),
            "rejim": _Cevap(
                choice="belirsiz",
                confidence=0.4,
                probabilities={
                    "trend_yukari": 0.3,
                    "trend_asagi": 0.1,
                    "aralik": 0.1,
                    "yuksek_volatilite": 0.0,
                    "belirsiz": 0.5,
                },
            ),
            "kurulum": _Cevap(score=0.9, confidence=0.3),
            "cekimser": _Cevap(noul=0.45),
        }


class _SahteIstemci:
    def __init__(self, model: str = "jev-1.13.0", hata_barlari: set[int] | None = None) -> None:
        self.model = model
        self.hata_barlari = hata_barlari or set()
        self.cagri = 0

    def system_one(self, state, questions, *, model=None):
        self.cagri += 1
        if state["karar_ms"] in self.hata_barlari:
            raise TimeoutError("sahte timeout")
        # Deterministik ama duruma bağlı bir "cevap": karar barına göre değişsin
        flat = 0.5 + (state["karar_ms"] // 3_600_000 % 5) / 20
        return _Yanit(self.model, flat)


@pytest.fixture
def ayar():
    return ayar_mod.yukle()


@pytest.fixture
def diziler():
    return bar_dizileri(bar_uret(n=N, tohum=7))


def _saat():
    return 1_800_000_000_000


class TestKuruKosu:
    def test_durumlar_yazilir_karar_yok(self, diziler, ayar):
        with JevDefteri() as df:
            oz = tekrar_kos(
                diziler,
                ayarlar=ayar,
                defter=df,
                kosu="tekrar-kuru",
                ilk=ILK,
                son=ILK + 9,
                istemci=None,
                saat=_saat,
            )
            satirlar = df.kararlar()
        assert oz.kuru and oz.sorulan == 0 and oz.bar_sayisi == 10 and len(satirlar) == 10
        assert all(s["durum_kodu"] == "eksik_veri" for s in satirlar)
        assert all(s["karar"]["leak_riski"] and not s["karar"]["ileriye_donuk"] for s in satirlar)
        # Durum hash'leri, aynı barın doğrudan kurulumuyla bit düzeyinde aynı
        for s, i in zip(satirlar, range(ILK, ILK + 10), strict=True):
            assert s["durum_hash"] == durum_hash(kanonik_durum(diziler, i, sembol="BTCUSDT"))

    def test_erken_bar_reddedilir(self, diziler, ayar):
        with JevDefteri() as df, pytest.raises(TekrarHatasi, match="pencere"):
            tekrar_kos(diziler, ayarlar=ayar, defter=df, kosu="t", ilk=10, son=20, istemci=None)

    def test_aralik_disi(self, diziler, ayar):
        with JevDefteri() as df, pytest.raises(TekrarHatasi):
            tekrar_kos(diziler, ayarlar=ayar, defter=df, kosu="t", ilk=ILK, son=N, istemci=None)


class TestGercekKosu:
    def test_sahte_istemciyle_kararlar(self, diziler, ayar):
        ist = _SahteIstemci()
        with JevDefteri() as df:
            oz = tekrar_kos(
                diziler,
                ayarlar=ayar,
                defter=df,
                kosu="tekrar-1",
                ilk=ILK,
                son=ILK + 4,
                istemci=ist,
                saat=_saat,
            )
            satirlar = df.kararlar()
            assert df.dogrula()
        assert oz.sorulan == 5 and ist.cagri == 5 and oz.sayim == {"gecerli": 5}
        assert all(s["karar"]["leak_riski"] for s in satirlar)  # kesim bilinmiyor
        assert all(s["yanit"]["model"] == "jev-1.13.0" for s in satirlar)
        assert oz.gecikme_ms_p50 is not None

    def test_ok_olmayan_bar_atlanir(self, diziler, ayar):
        bozuk = {k: np.array(v) for k, v in diziler.items()}
        bozuk["quality_status"] = np.array(diziler["quality_status"], dtype=object)
        bozuk["quality_status"][ILK + 2] = "gap"
        with JevDefteri() as df:
            oz = tekrar_kos(
                bozuk,
                ayarlar=ayar,
                defter=df,
                kosu="t",
                ilk=ILK,
                son=ILK + 4,
                istemci=_SahteIstemci(),
                saat=_saat,
            )
            atlanan = df.olaylar(tur=OlayTuru.BAR_ATLANDI)
        assert oz.sorulan == 4 and oz.atlanan == 1
        assert atlanan[0]["ayrinti"] == {
            "karar_ms": int(bozuk["open_time"][ILK + 2]),
            "kalite": "gap",
        }

    def test_hata_fail_closed_ve_devam(self, diziler, ayar):
        hatali = int(diziler["open_time"][ILK + 1])
        with JevDefteri() as df:
            oz = tekrar_kos(
                diziler,
                ayarlar=ayar,
                defter=df,
                kosu="t",
                ilk=ILK,
                son=ILK + 2,
                istemci=_SahteIstemci(hata_barlari={hatali}),
                saat=_saat,
            )
            satirlar = df.kararlar()
        assert oz.sayim == {"gecerli": 2, "timeout": 1}
        hatali_satir = next(s for s in satirlar if s["karar_ms"] == hatali)
        assert hatali_satir["karar"]["yon"] is None and hatali_satir["yanit"] is None

    def test_kaldigi_yerden_devam(self, diziler, ayar):
        ist = _SahteIstemci()
        with JevDefteri() as df:
            tekrar_kos(
                diziler,
                ayarlar=ayar,
                defter=df,
                kosu="t",
                ilk=ILK,
                son=ILK + 2,
                istemci=ist,
                saat=_saat,
            )
            tekrar_kos(
                diziler,
                ayarlar=ayar,
                defter=df,
                kosu="t",
                ilk=ILK,
                son=ILK + 5,
                istemci=ist,
                saat=_saat,
            )
            assert ist.cagri == 6 and df.sayim() == {"gecerli": 6}
            assert df.dogrula()

    def test_model_uyusmazligi_gecersiz(self, diziler, ayar):
        with JevDefteri() as df:
            oz = tekrar_kos(
                diziler,
                ayarlar=ayar,
                defter=df,
                kosu="t",
                ilk=ILK,
                son=ILK + 1,
                istemci=_SahteIstemci(model="jev-1.14.0"),
                saat=_saat,
            )
        assert oz.sayim == {"model_uyumsuz": 2}


class TestDondur:
    def test_parquet_ve_manifest(self, diziler, ayar, tmp_path):
        with JevDefteri() as df:
            tekrar_kos(
                diziler,
                ayarlar=ayar,
                defter=df,
                kosu="tekrar-d",
                ilk=ILK,
                son=ILK + 3,
                istemci=_SahteIstemci(),
                saat=_saat,
            )
            dizin, m = dondur(
                df, ayarlar=ayar, kok=tmp_path, girdi_sha256={"1h": "abc"}, saat=_saat
            )
        parquet = dizin / "kararlar.parquet"
        assert parquet.exists() and (dizin / "manifest.json").exists()
        assert dizin.name == dosya_hash(parquet)[:12] == m["turetim_id"]
        assert (
            m["leak_riski"] is True and m["egitim_kesim_ms"] is None and m["ileriye_donuk"] is False
        )
        assert m["gecerli"] == 4 and m["satir"] == 4 and m["girdi_sha256"] == {"1h": "abc"}
        assert m["defter_zinciri_gecerli"] and m["mod"] == "tekrar"
        okunan = json.loads((dizin / "manifest.json").read_text(encoding="utf-8"))
        assert okunan == m
        cerceve = pd.read_parquet(parquet)
        assert list(cerceve["durum_kodu"]) == ["gecerli"] * 4
        assert json.loads(cerceve["yon_olasiliklari"].iloc[0]).keys() == {"long", "short", "flat"}
        assert "yanit" not in cerceve.columns  # ham yanıt defterde, dondurulmuş dosyada özet

    def test_ayni_icerik_ayni_kimlik(self, diziler, ayar, tmp_path):
        with JevDefteri() as df:
            tekrar_kos(
                diziler,
                ayarlar=ayar,
                defter=df,
                kosu="t",
                ilk=ILK,
                son=ILK + 1,
                istemci=None,
                saat=_saat,
            )
            d1, m1 = dondur(df, ayarlar=ayar, kok=tmp_path, saat=_saat)
            d2, m2 = dondur(df, ayarlar=ayar, kok=tmp_path, saat=_saat)
        assert d1 == d2 and m1["kararlar_sha256"] == m2["kararlar_sha256"]

    def test_bos_defter_dondurulmaz(self, ayar, tmp_path):
        with JevDefteri() as df, pytest.raises(TekrarHatasi):
            dondur(df, ayarlar=ayar, kok=tmp_path)

    def test_cerceve_sirali(self, diziler, ayar):
        with JevDefteri() as df:
            tekrar_kos(
                diziler,
                ayarlar=ayar,
                defter=df,
                kosu="t",
                ilk=ILK,
                son=ILK + 3,
                istemci=None,
                saat=_saat,
            )
            c = kararlar_cercevesi(df)
        assert list(c["karar_ms"]) == sorted(c["karar_ms"])
        assert "durum_kodu" in c.columns and "durum" not in c.columns
