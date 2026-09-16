"""Çok enstrümanlı motorun çıktısı, motordan bağımsız referansla uyuşuyor mu. (Faz 10)

Faz 10'un bitti kriterinin en zor maddesi burada ve Faz 3'ünkiyle aynı üç ayağa basıyor:

1. `tools/coklu_referans_uret.py` `scryne_quant`ı import etmiyor — ve bunu bir test tarıyor.
2. Referans `Decimal` (50 basamak), motor `float64`.
3. Senaryo C kapalı formülle de doğrulanıyor — üstelik **Faz 3'ün formülüyle aynısıyla**.
   Aynı olması kanıtın kendisi: iki enstrüman arasında dönüşümlü işlem yapmak, tek
   enstrümanla işlem yapmaktan farklı bir aritmetik gerektirmiyor (K-052/2).

Senaryo D kapalı formüle uymuyor ve kanıt gücü orada daha zayıf; ölçtüğü şey aritmetik
değil **sıralama**: aynı barda önce satışlar, tek özkaynak anlık görüntüsü, nakit tavanı.
Fixture bu senaryonun gerçekten karışık bar ürettiğini sayıyla kaydediyor.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.strategy.kosu import evren_gorunum_kur
from tests.conftest import PlanliHedef

KOK = Path(__file__).resolve().parents[2]
FIXTURE = KOK / "tests" / "fixtures" / "coklu_referans.json"
URETICI = KOK / "tools" / "coklu_referans_uret.py"

#: float64 ile Decimal arasındaki kaçınılmaz fark (Faz 3 ile aynı gerekçe ve aynı sayı).
TOLERANS = 1e-12

REFERANS = json.loads(FIXTURE.read_text(encoding="utf-8"))
SENARYOLAR = {s["ad"]: s for s in REFERANS["senaryolar"]}
SEMBOLLER = tuple(REFERANS["semboller"])


def _bar_dizileri(barlar: list[dict]) -> dict[str, np.ndarray]:
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


def _takvim(hedefler: list[dict]) -> dict[int, dict[str, float]]:
    return {h["bar"]: {s: float(a) for s, a in h["agirliklar"].items()} for h in hedefler}


def _kosu(ad: str):
    senaryo = SENARYOLAR[ad]
    maliyet = MaliyetModeli(**REFERANS["maliyet"])
    strateji = PlanliHedef(_takvim(senaryo["hedefler"]))
    diziler = {s: _bar_dizileri(senaryo["barlar"][s]) for s in SEMBOLLER}
    n = len(diziler[SEMBOLLER[0]]["open_time"])
    gorunum = evren_gorunum_kur(
        REFERANS["timeframe"],
        diziler,
        # Referans senaryosunda evren kuralı yok: iki sembol de her barda üye. Ölçülen şey
        # portföy aritmetiği; evren seçiminin kendi testi `test_evren_baglam.py`de.
        {s: np.ones(n, dtype=bool) for s in SEMBOLLER},
        strateji,
        kural_kimligi="referans",
    )
    motor = CokluBacktest(
        strateji, maliyet, baslangic_sermaye=float(REFERANS["baslangic_sermaye"])
    )
    return senaryo, motor.calistir(gorunum)


def _yakin(bizim: float, beklenen_str: str, etiket: str) -> None:
    beklenen = float(beklenen_str)
    olcek = max(abs(beklenen), 1.0)
    fark = abs(bizim - beklenen)
    assert fark <= TOLERANS * olcek, (
        f"{etiket}: motor {bizim!r}, referans {beklenen_str} (fark {fark:.3e})"
    )


@pytest.fixture(scope="module")
def kosu_c():
    return _kosu("donusumlu_tam_giris_cikis")


@pytest.fixture(scope="module")
def kosu_d():
    return _kosu("eszamanli_dengeleme")


class TestReferansBagimsizligi:
    def test_ureticisi_motoru_import_etmiyor(self):
        """Referans motorun çıktısından türetilemez. Statik tarama — üreticiyi çalıştırıp
        `sys.modules`'a bakmak, kaçınmaya çalıştığımız şeyi yapmak olurdu."""
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
        kf = SENARYOLAR["donusumlu_tam_giris_cikis"]["kapali_form"]
        assert len(kf["tur_sonu_sermaye"]) >= 10
        assert float(kf["defter_ile_azami_bagil_fark"]) < 1e-40

    def test_kapali_form_faz3_formuluyle_ayni(self):
        """Çok enstrümanlı referansın formülü, tek enstrümanlınınkiyle birebir aynı metin.

        Ayrı bir formül yazılsaydı, "tek enstrüman özel hâldir" iddiası referans
        katmanında da bölünmüş olurdu — iki farklı doğru, iki farklı yanlış imkânı.
        """
        tek = json.loads(
            (KOK / "tests" / "fixtures" / "backtest_referans.json").read_text(encoding="utf-8")
        )
        tek_kf = next(
            s for s in tek["senaryolar"] if s["ad"] == "tam_giris_cikis"
        )["kapali_form"]["formul"]
        coklu_kf = SENARYOLAR["donusumlu_tam_giris_cikis"]["kapali_form"]["formul"]
        assert coklu_kf == tek_kf

    def test_senaryo_d_gercekten_karisik_bar_uretiyor(self):
        """Sıralama kuralını ölçen senaryo, ölçtüğünü sanıp hiçbir şey ölçmesin."""
        assert SENARYOLAR["eszamanli_dengeleme"]["olcum"]["ayni_barda_satis_ve_alim"] >= 3


class TestSenaryoC:
    """12 tur, iki enstrüman arasında dönüşümlü tam giriş/çıkış."""

    def test_islem_sayisi(self, kosu_c):
        senaryo, sonuc = kosu_c
        ozet = senaryo["beklenen"]["ozet"]
        assert sonuc.metrikler.islem_sayisi == ozet["islem_sayisi"] == 12
        assert sonuc.metrikler.kazanan == ozet["kazanan"]
        assert sonuc.metrikler.kaybeden == ozet["kaybeden"]

    def test_iki_enstruman_da_islem_gormus(self, kosu_c):
        _, sonuc = kosu_c
        assert {i.sembol for i in sonuc.islemler} == set(SEMBOLLER)

    def test_bitis_sermayesi(self, kosu_c):
        senaryo, sonuc = kosu_c
        _yakin(
            sonuc.metrikler.bitis_sermaye,
            senaryo["beklenen"]["ozet"]["bitis_sermaye"],
            "bitiş sermayesi",
        )

    def test_her_tur_ayni(self, kosu_c):
        senaryo, sonuc = kosu_c
        beklenen = senaryo["beklenen"]["turlar"]
        assert len(sonuc.islemler) == len(beklenen)
        for i, (bizim, ref) in enumerate(zip(sonuc.islemler, beklenen, strict=True)):
            assert bizim.sembol == ref["sembol"], f"tur {i} sembol"
            assert bizim.acilis_ms == ref["acilis_ms"], f"tur {i} açılış"
            assert bizim.kapanis_ms == ref["kapanis_ms"], f"tur {i} kapanış"
            _yakin(bizim.giris_notional, ref["giris_notional"], f"tur {i} giriş notional")
            _yakin(bizim.cikis_notional, ref["cikis_notional"], f"tur {i} çıkış notional")
            _yakin(bizim.giris_miktar, ref["miktar"], f"tur {i} miktar")
            _yakin(bizim.komisyon, ref["komisyon"], f"tur {i} komisyon")
            _yakin(bizim.slippage, ref["slippage"], f"tur {i} slippage")
            _yakin(bizim.net_pnl, ref["net_pnl"], f"tur {i} net P&L")

    def test_equity_egrisi_bar_bar_ayni(self, kosu_c):
        senaryo, sonuc = kosu_c
        beklenen = senaryo["beklenen"]["ozkaynak"]
        assert sonuc.ozkaynak.size == len(beklenen)
        for i, (bizim, ref) in enumerate(zip(sonuc.ozkaynak, beklenen, strict=True)):
            _yakin(float(bizim), ref, f"bar {i} özkaynak")

    def test_kapali_form_motorla_da_uyusuyor(self, kosu_c):
        """Motorun tur sonu nakdi, cebirsel zincirle aynı — fixture'ın defterine hiç bakmadan.

        Defter ile motor aynı anda aynı hatayı yapsa bile burası kırılır.
        """
        _, sonuc = kosu_c
        maliyet = REFERANS["maliyet"]
        f = maliyet["fee_taker_bps"] * 1e-4
        s = maliyet["slippage_bps"] * 1e-4
        carpan = (1 - s) * (1 - f) / ((1 + s) * (1 + f))

        oranlar = [
            (20600 / 20000), (1470 / 1500), (21320 / 20500), (1465 / 1480),
            (21000 / 21000), (1537 / 1450), (21186 / 21400), (1596 / 1520),
            (21582 / 21800), (1659 / 1580), (21780 / 22000), (1738 / 1640),
        ]
        c = float(REFERANS["baslangic_sermaye"])
        motor_nakit = float(REFERANS["baslangic_sermaye"])
        for i, oran in enumerate(oranlar):
            c *= oran * carpan
            islem = sonuc.islemler[i]
            motor_nakit = (
                motor_nakit - islem.giris_notional * (1 + f) + islem.cikis_notional * (1 - f)
            )
            assert abs(motor_nakit - c) <= TOLERANS * max(abs(c), 1.0), (
                f"tur {i}: motor {motor_nakit!r}, kapalı formül {c!r}"
            )

    def test_toplam_maliyetler(self, kosu_c):
        senaryo, sonuc = kosu_c
        ozet = senaryo["beklenen"]["ozet"]
        _yakin(sonuc.metrikler.toplam_komisyon, ozet["toplam_komisyon"], "toplam komisyon")
        _yakin(sonuc.metrikler.toplam_slippage, ozet["toplam_slippage"], "toplam slippage")

    def test_sermaye_muhasebesi(self, kosu_c):
        senaryo, sonuc = kosu_c
        net = float(senaryo["beklenen"]["ozet"]["net_pnl_toplam"])
        _yakin(
            sonuc.metrikler.baslangic_sermaye + net,
            senaryo["beklenen"]["ozet"]["bitis_sermaye"],
            "sermaye muhasebesi",
        )

    def test_hicbir_hedef_atlanmadi(self, kosu_c):
        senaryo, sonuc = kosu_c
        assert not senaryo["beklenen"]["atlanan"]
        assert sum(v for a, v in sonuc.atlanan.items() if a != "bayat_degerleme") == 0


class TestSenaryoD:
    """Eşzamanlı dengeleme: aynı barda satış + alım, bahsedilmeyen sembol, tam çıkış."""

    def test_bitis_sermayesi(self, kosu_d):
        senaryo, sonuc = kosu_d
        _yakin(
            sonuc.metrikler.bitis_sermaye,
            senaryo["beklenen"]["ozet"]["bitis_sermaye"],
            "bitiş sermayesi",
        )

    def test_turlar_ayni(self, kosu_d):
        senaryo, sonuc = kosu_d
        beklenen = senaryo["beklenen"]["turlar"]
        assert len(sonuc.islemler) == len(beklenen)
        for i, (bizim, ref) in enumerate(zip(sonuc.islemler, beklenen, strict=True)):
            assert bizim.sembol == ref["sembol"], f"tur {i} sembol"
            _yakin(bizim.net_pnl, ref["net_pnl"], f"tur {i} net P&L")
            _yakin(bizim.komisyon, ref["komisyon"], f"tur {i} komisyon")
            assert bizim.fill_sayisi == ref["fill_sayisi"], f"tur {i} fill sayısı"

    def test_equity_egrisi_bar_bar_ayni(self, kosu_d):
        senaryo, sonuc = kosu_d
        for i, (bizim, ref) in enumerate(
            zip(sonuc.ozkaynak, senaryo["beklenen"]["ozkaynak"], strict=True)
        ):
            _yakin(float(bizim), ref, f"bar {i} özkaynak")

    def test_bahsedilmeyen_sembol_pozisyonu_korunuyor(self, kosu_d):
        """Bar 19'da yalnızca AAA'dan bahsediliyor; BBB pozisyonu kapanmamalı.

        Fixture'ın defteri bu kuralı uyguladı; motor uygulamasaydı equity eğrisi ve tur
        sayısı ayrışırdı. Testin burada ayrıca durmasının sebebi, kuralın **adının**
        kayıtta kalması.
        """
        senaryo, sonuc = kosu_d
        bar19 = [h for h in senaryo["hedefler"] if h["bar"] == 19]
        assert bar19 and set(bar19[0]["agirliklar"]) == {"AAAUSDT"}
        bbb = [i for i in sonuc.islemler if i.sembol == "BBBUSDT"]
        # BBB bar 10'da kapandı, 13'te yeniden açıldı ve 22'ye kadar açık kaldı: 19'da
        # kapansaydı bu tur 22'den önce bitmiş olurdu.
        assert any(i.kapanis_ms and i.fill_sayisi >= 2 for i in bbb)

    def test_ayni_barda_satis_alimdan_once(self, kosu_d):
        """Nakit tavanı: satış önce gelmeseydi alım `nakit_yok` ile kısılırdı."""
        _, sonuc = kosu_d
        assert sonuc.atlanan.get("nakit_yok", 0) == 0


class TestDeterminizm:
    def test_iki_kosu_ayni_hash(self):
        _, a = _kosu("eszamanli_dengeleme")
        _, b = _kosu("eszamanli_dengeleme")
        assert a.sonuc_hash == b.sonuc_hash
        assert a.config_hash == b.config_hash

    def test_farkli_maliyet_farkli_hash(self):
        """Determinizm testi, her şeyi aynı gösteren bir hash'le de yeşil olurdu."""
        senaryo = SENARYOLAR["eszamanli_dengeleme"]
        diziler = {s: _bar_dizileri(senaryo["barlar"][s]) for s in SEMBOLLER}
        n = len(diziler[SEMBOLLER[0]]["open_time"])
        sonuclar = []
        for fee in (10.0, 20.0):
            strateji = PlanliHedef(_takvim(senaryo["hedefler"]))
            gorunum = evren_gorunum_kur(
                "1h", diziler, {s: np.ones(n, dtype=bool) for s in SEMBOLLER}, strateji
            )
            sonuclar.append(
                CokluBacktest(
                    strateji, MaliyetModeli(fee_taker_bps=fee, slippage_bps=5.0)
                ).calistir(gorunum)
            )
        assert sonuclar[0].sonuc_hash != sonuclar[1].sonuc_hash


class TestKayit:
    def test_evren_kimligi_kayitta(self, kosu_c):
        senaryo, sonuc = kosu_c
        evren = sonuc.sozluk()["evren"]
        assert evren["enstruman_sayisi"] == len(SEMBOLLER)
        assert {e["sembol"] for e in evren["enstrumanlar"]} == set(SEMBOLLER)
        assert sonuc.veri.sembol.startswith("EVREN:")
        assert senaryo["beklenen"]["ozet"]["islem_sayisi"] == sonuc.metrikler.islem_sayisi

    def test_islem_satirlarinda_sembol_var(self, kosu_c):
        """Çok enstrümanlı kayıtta sembol zorunlu; tek sembollüde yazılmıyor (K-009)."""
        _, sonuc = kosu_c
        satirlar = sonuc.sozluk()["islemler"]
        assert all(s["sembol"] in SEMBOLLER for s in satirlar)

    def test_kapasite_olculdu(self, kosu_c):
        """§16'nın kapasite metriği raporlanıyor ve sıfır değil — yani gerçekten ölçülmüş."""
        _, sonuc = kosu_c
        assert sonuc.metrikler.kapasite_adv_azami > 0.0
        assert (
            sonuc.metrikler.kapasite_adv_ortalama <= sonuc.metrikler.kapasite_adv_azami
        )

    def test_var_cvar_tutarli(self, kosu_c):
        """CVaR her zaman VaR'dan büyük ya da eşit: kuyruğun ortalaması eşiğinden kötüdür."""
        m = sonuc_metrikleri(kosu_c)
        assert m.cvar_95 >= m.var_95
        assert m.cvar_99 >= m.var_99
        assert m.var_99 >= m.var_95


def sonuc_metrikleri(kosu):
    return kosu[1].metrikler
