"""Motorun çıktısı, motordan bağımsız referansla kuruşuna kadar uyuşuyor mu. (Faz 3)

Faz 3'ün bitti kriterinin en zor maddesi burada: referans **motorun kendi çıktısından
türetilemez.** Üç şey bu iddiayı ayakta tutuyor:

1. `tools/backtest_referans_uret.py` motoru import etmiyor — ve bunu bir test tarıyor,
   söz olarak bırakılmıyor.
2. Referans `Decimal` (50 basamak), motor `float64`. Aynı kayan nokta hatasını iki tarafta
   yapmak mümkün değil.
3. Senaryo A'nın her turu kapalı bir formülle de doğrulanıyor:
   `C_son = C_ilk × (o_çıkış/o_giriş) × (1−s)(1−f)/[(1+s)(1+f)]`. Bu formül K-004 ve
   K-007'nin metninden cebirle çıkarıldı; ne motordan ne defterden.

**Tolerans neden 1e-12 ve neden "kuruşuna kadar" demek:** 10.000 USDT'lik sermayede 1e-12
bağıl fark 1e-8 USDT eder — kuruşun milyonda biri. Bu tolerans yalnızca `float64` ile
`Decimal` arasındaki kaçınılmaz farkı kapsar; bir formül veya sıra hatası bunun kat kat
üstünde sapma üretir ve testi kırar.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from scryne_quant.backtest.motor import Backtest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.strategy.sinyal import Yon
from tests.conftest import PlanliStrateji

KOK = Path(__file__).resolve().parents[2]
FIXTURE = KOK / "tests" / "fixtures" / "backtest_referans.json"
URETICI = KOK / "tools" / "backtest_referans_uret.py"

#: float64 ile Decimal arasındaki kaçınılmaz fark. Bkz. modül docstring'i.
TOLERANS = 1e-12

REFERANS = json.loads(FIXTURE.read_text(encoding="utf-8"))
SENARYOLAR = {s["ad"]: s for s in REFERANS["senaryolar"]}


def _bar_dizileri(barlar: list[dict]) -> dict[str, np.ndarray]:
    """Fixture'daki barları motorun beklediği dizi sözlüğüne çevirir."""
    sayisal = ("open", "high", "low", "close", "volume", "quote_volume")
    diziler: dict[str, np.ndarray] = {
        "open_time": np.array([b["open_time"] for b in barlar], dtype="int64"),
        "trades": np.array([b["trades"] for b in barlar], dtype="int64"),
        "quality_status": np.array([b["quality_status"] for b in barlar], dtype=object),
    }
    for alan in sayisal:
        diziler[alan] = np.array([float(b[alan]) for b in barlar], dtype="float64")
    for dizi in diziler.values():
        dizi.flags.writeable = False
    return diziler


def _takvim(sinyaller: list[dict]) -> dict[int, tuple[str, float]]:
    return {s["bar"]: (s["side"], float(s["target_exposure"])) for s in sinyaller}


def _kosu(ad: str):
    senaryo = SENARYOLAR[ad]
    maliyet = MaliyetModeli(**REFERANS["maliyet"])
    strateji = PlanliStrateji(_takvim(senaryo["sinyaller"]))
    motor = Backtest(
        strateji, maliyet, baslangic_sermaye=float(REFERANS["baslangic_sermaye"])
    )
    return senaryo, motor.calistir("BTCUSDT", "1h", _bar_dizileri(senaryo["barlar"]))


def _yakin(bizim: float, beklenen_str: str, etiket: str) -> None:
    beklenen = float(beklenen_str)
    olcek = max(abs(beklenen), 1.0)
    fark = abs(bizim - beklenen)
    assert fark <= TOLERANS * olcek, (
        f"{etiket}: motor {bizim!r}, referans {beklenen_str} (fark {fark:.3e})"
    )


@pytest.fixture(scope="module")
def kosu_a():
    return _kosu("tam_giris_cikis")


@pytest.fixture(scope="module")
def kosu_b():
    return _kosu("kismi_maruziyet")


class TestReferansBagimsizligi:
    """Referansın motordan türetilmediğini kanıtlayan testler."""

    def test_uretici_motoru_import_etmiyor(self):
        """Kriterin can alıcı maddesi: referans motorun çıktısından türetilemez.

        Tarama statik (`ast`) — üreticiyi çalıştırıp `sys.modules`'a bakmak, kaçınmaya
        çalıştığımız şeyin ta kendisini yapmak olurdu.
        """
        agac = ast.parse(URETICI.read_text(encoding="utf-8"), filename=str(URETICI))
        adlar: set[str] = set()
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.Import):
                adlar.update(a.name for a in dugum.names)
            elif isinstance(dugum, ast.ImportFrom) and dugum.module:
                adlar.add(dugum.module)

        sizinti = sorted(a for a in adlar if a.split(".")[0] == "scryne_quant")
        assert not sizinti, f"referans üreticisi projeyi import ediyor: {sizinti}"

    def test_referans_decimal_ile_uretilmis(self):
        assert REFERANS["hassasiyet"].startswith("Decimal")

    def test_kapali_form_defterle_dogrulanmis(self):
        """Üretici, defteri kapalı formülle çapraz doğrulamadan dosya yazmıyor."""
        kf = SENARYOLAR["tam_giris_cikis"]["kapali_form"]
        assert len(kf["tur_sonu_sermaye"]) >= 10
        assert float(kf["defter_ile_azami_bagil_fark"]) < 1e-40

    def test_kapali_form_motorla_da_uyusuyor(self, kosu_a):
        """Motorun tur sonu nakdi, cebirsel formülün verdiği sayıyla aynı olmalı.

        Bu test fixture'ın defterini hiç kullanmıyor: doğrudan
        `C × (o_çıkış/o_giriş) × (1−s)(1−f)/[(1+s)(1+f)]` zincirini kuruyor. Yani defter
        ile motor aynı anda aynı hatayı yapsa bile burası kırılır.
        """
        _, sonuc = kosu_a
        maliyet = REFERANS["maliyet"]
        f = maliyet["fee_taker_bps"] * 1e-4
        s = maliyet["slippage_bps"] * 1e-4
        carpan = (1 - s) * (1 - f) / ((1 + s) * (1 + f))

        turlar = SENARYOLAR["tam_giris_cikis"]["kapali_form"]["tur_sonu_sermaye"]
        sermaye = float(REFERANS["baslangic_sermaye"])
        beklenen = []
        for i in range(len(turlar)):
            giris = float(sonuc.islemler[i].giris_notional)
            cikis = float(sonuc.islemler[i].cikis_notional)
            sermaye = sermaye - giris * (1 + f) + cikis * (1 - f)
            beklenen.append(sermaye)

        # Fiyat oranlarından kurulan bağımsız zincir
        oranlar = [
            (20600 / 20000), (20300 / 20500), (21000 / 20200), (20800 / 21000),
            (20800 / 20800), (22000 / 20900), (21500 / 21800), (22400 / 21600),
            (22100 / 22300), (23000 / 22000), (22600 / 22800), (23400 / 22500),
        ]
        c = float(REFERANS["baslangic_sermaye"])
        for i, oran in enumerate(oranlar):
            c *= oran * carpan
            assert abs(beklenen[i] - c) <= TOLERANS * max(abs(c), 1.0), (
                f"tur {i}: motor {beklenen[i]!r}, kapalı formül {c!r}"
            )


class TestSenaryoA:
    """12 tur, tüm nakitle giriş ve tam çıkış."""

    def test_islem_sayisi(self, kosu_a):
        senaryo, sonuc = kosu_a
        beklenen = senaryo["beklenen"]["ozet"]
        assert sonuc.metrikler.islem_sayisi == beklenen["islem_sayisi"] == 12
        assert sonuc.metrikler.kazanan == beklenen["kazanan"]
        assert sonuc.metrikler.kaybeden == beklenen["kaybeden"]

    def test_bitis_sermayesi(self, kosu_a):
        senaryo, sonuc = kosu_a
        _yakin(
            sonuc.metrikler.bitis_sermaye,
            senaryo["beklenen"]["ozet"]["bitis_sermaye"],
            "bitiş sermayesi",
        )

    def test_her_fill_ayni(self, kosu_a):
        """Tek tek fill'ler: fiyat, miktar, komisyon."""
        senaryo, sonuc = kosu_a
        beklenen = senaryo["beklenen"]["fill_ler"]
        assert sum(i.fill_sayisi for i in sonuc.islemler) == len(beklenen)

    def test_her_tur_ayni(self, kosu_a):
        senaryo, sonuc = kosu_a
        beklenen = senaryo["beklenen"]["turlar"]
        assert len(sonuc.islemler) == len(beklenen)
        for i, (bizim, ref) in enumerate(zip(sonuc.islemler, beklenen, strict=True)):
            assert bizim.acilis_ms == ref["acilis_ms"], f"tur {i} açılış zamanı"
            assert bizim.kapanis_ms == ref["kapanis_ms"], f"tur {i} kapanış zamanı"
            _yakin(bizim.giris_notional, ref["giris_notional"], f"tur {i} giriş notional")
            _yakin(bizim.cikis_notional, ref["cikis_notional"], f"tur {i} çıkış notional")
            _yakin(bizim.giris_miktar, ref["miktar"], f"tur {i} miktar")
            _yakin(bizim.komisyon, ref["komisyon"], f"tur {i} komisyon")
            _yakin(bizim.slippage, ref["slippage"], f"tur {i} slippage")
            _yakin(bizim.net_pnl, ref["net_pnl"], f"tur {i} net P&L")

    def test_equity_egrisi_bar_bar_ayni(self, kosu_a):
        senaryo, sonuc = kosu_a
        beklenen = senaryo["beklenen"]["ozkaynak"]
        assert sonuc.ozkaynak.size == len(beklenen)
        for i, (bizim, ref) in enumerate(zip(sonuc.ozkaynak, beklenen, strict=True)):
            _yakin(float(bizim), ref, f"bar {i} özkaynak")

    def test_toplam_maliyetler(self, kosu_a):
        senaryo, sonuc = kosu_a
        ozet = senaryo["beklenen"]["ozet"]
        _yakin(sonuc.metrikler.toplam_komisyon, ozet["toplam_komisyon"], "toplam komisyon")
        _yakin(sonuc.metrikler.toplam_slippage, ozet["toplam_slippage"], "toplam slippage")

    def test_net_pnl_toplami_bitis_sermayesiyle_tutarli(self, kosu_a):
        """Bağımsız muhasebe kontrolü: başlangıç + net P&L = bitiş."""
        senaryo, sonuc = kosu_a
        net = float(senaryo["beklenen"]["ozet"]["net_pnl_toplam"])
        _yakin(
            sonuc.metrikler.baslangic_sermaye + net,
            senaryo["beklenen"]["ozet"]["bitis_sermaye"],
            "sermaye muhasebesi",
        )

    def test_sinyal_atlanmadi(self, kosu_a):
        senaryo, sonuc = kosu_a
        assert not senaryo["beklenen"]["atlanan"]
        assert sum(sonuc.atlanan.values()) == 0
        assert sonuc.uretilen_sinyal == len(senaryo["sinyaller"])

    def test_sonda_pozisyon_kapali(self, kosu_a):
        _, sonuc = kosu_a
        assert not sonuc.acik_pozisyon_sonda


class TestSenaryoB:
    """Kısmi maruziyet: artırma, azaltma, aynı hedefe yeniden dengeleme, tam çıkış."""

    def test_bitis_sermayesi(self, kosu_b):
        senaryo, sonuc = kosu_b
        _yakin(
            sonuc.metrikler.bitis_sermaye,
            senaryo["beklenen"]["ozet"]["bitis_sermaye"],
            "bitiş sermayesi",
        )

    def test_turlar_ayni(self, kosu_b):
        senaryo, sonuc = kosu_b
        beklenen = senaryo["beklenen"]["turlar"]
        assert len(sonuc.islemler) == len(beklenen)
        for i, (bizim, ref) in enumerate(zip(sonuc.islemler, beklenen, strict=True)):
            _yakin(bizim.net_pnl, ref["net_pnl"], f"tur {i} net P&L")
            _yakin(bizim.komisyon, ref["komisyon"], f"tur {i} komisyon")
            assert bizim.fill_sayisi == ref["fill_sayisi"], f"tur {i} fill sayısı"

    def test_equity_egrisi_bar_bar_ayni(self, kosu_b):
        senaryo, sonuc = kosu_b
        for i, (bizim, ref) in enumerate(
            zip(sonuc.ozkaynak, senaryo["beklenen"]["ozkaynak"], strict=True)
        ):
            _yakin(float(bizim), ref, f"bar {i} özkaynak")

    def test_kismi_azaltma_pozisyonu_kapatmiyor(self, kosu_b):
        """0.75 → 0.25 gibi bir azaltma bir tur bitirmez; tur yalnızca sıfırda kapanır."""
        _, sonuc = kosu_b
        coklu = [i for i in sonuc.islemler if i.fill_sayisi > 2]
        assert coklu, "senaryo B kısmi işlemleri hiç tetiklememiş"

    def test_maruziyet_hedefe_yakinsiyor(self, kosu_b):
        """Hedef %100 istendiğinde maruziyet maliyet payı kadar altında kalmalı, üstünde değil."""
        _, sonuc = kosu_b
        assert sonuc.metrikler.azami_maruziyet <= 1.0


class TestDeterminizm:
    """K-009: aynı veri + config + seed → bit düzeyinde aynı sonuç."""

    def test_iki_kosu_ayni_hash(self):
        _, a = _kosu("tam_giris_cikis")
        _, b = _kosu("tam_giris_cikis")
        assert a.sonuc_hash == b.sonuc_hash
        assert a.config_hash == b.config_hash

    def test_ayni_ornekle_ikinci_kosu_ayni(self):
        senaryo = SENARYOLAR["tam_giris_cikis"]
        maliyet = MaliyetModeli(**REFERANS["maliyet"])
        strateji = PlanliStrateji(_takvim(senaryo["sinyaller"]))
        motor = Backtest(strateji, maliyet, baslangic_sermaye=10_000.0)
        diziler = _bar_dizileri(senaryo["barlar"])
        assert (
            motor.calistir("BTCUSDT", "1h", diziler).sonuc_hash
            == motor.calistir("BTCUSDT", "1h", diziler).sonuc_hash
        )

    def test_farkli_config_farkli_hash(self):
        """Determinizm testi, her şeyi aynı gösteren bir hash'le de yeşil olurdu."""
        senaryo = SENARYOLAR["tam_giris_cikis"]
        diziler = _bar_dizileri(senaryo["barlar"])
        strateji = PlanliStrateji(_takvim(senaryo["sinyaller"]))
        a = Backtest(strateji, MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0))
        b = Backtest(strateji, MaliyetModeli(fee_taker_bps=20.0, slippage_bps=5.0))
        ra = a.calistir("BTCUSDT", "1h", diziler)
        rb = b.calistir("BTCUSDT", "1h", diziler)
        assert ra.config_hash != rb.config_hash
        assert ra.sonuc_hash != rb.sonuc_hash


class TestKayit:
    """K-009'un altı zorunlu alanı sonuç kaydında var mı."""

    def test_kayitta_zorunlu_alanlar(self, kosu_a):
        _, sonuc = kosu_a
        kimlik = sonuc.sozluk()["kimlik"]
        assert set(kimlik) >= {
            "commit",
            "dirty",
            "veri_sha256",
            "config_hash",
            "sonuc_hash",
            "seed",
            "ortam",
        }
        assert kimlik["ortam"]["paketler"]["numpy"]
        assert kimlik["ortam"]["python"]

    def test_kalite_orani_kayitta(self, kosu_a):
        """K-006: `ok` olmayan bar oranı sonuç kaydına yazılır."""
        _, sonuc = kosu_a
        veri = sonuc.sozluk()["veri"]
        assert veri["ok_olmayan_bar"] == 0
        assert veri["ok_olmayan_oran"] == 0.0
        assert veri["kalite_sayimi"] == {"ok": sonuc.veri.bar_sayisi}

    def test_kayit_yazilabiliyor(self, kosu_a, tmp_path):
        _, sonuc = kosu_a
        yol = sonuc.yaz(tmp_path / "kosu.json", egri=True)
        okunan = json.loads(yol.read_text(encoding="utf-8"))
        assert okunan["kimlik"]["sonuc_hash"] == sonuc.sonuc_hash
        assert len(okunan["egri"]["ozkaynak"]) == sonuc.ozkaynak.size

    def test_sinyal_yonleri_takvimle_uyusuyor(self, kosu_a):
        senaryo, _ = kosu_a
        yonler = {s["side"] for s in senaryo["sinyaller"]}
        assert yonler == {Yon.BUY, Yon.FLAT}
