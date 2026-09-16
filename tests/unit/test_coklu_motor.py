"""Çok enstrümanlı motorun davranışı; ve tek enstrümanın **özel hâl** olduğunun kanıtı.

Faz 10'un bitti kriterinin birinci maddesi: *"Tek enstrüman özel hâldir: Faz 3'ün bağımsız
referans fixture'ı yeni motorda bit düzeyinde aynı sonucu veriyor. (K-052/2 — bu kriter
düşerse K-001 düşer.)"*

Kanıt iki katmanlı:

1. `Backtest` artık `CokluBacktest`in **sarmalayıcısı** — yani "iki motor aynı sonucu
   veriyor" değil, tek motor var. Bunu `test_tek_motor_kalmadi` statik olarak kontrol
   ediyor; iki ayrı döngü geri gelirse test kırılır.
2. Faz 3'ün Decimal referansı, `CokluBacktest`e **doğrudan** (sarmalayıcıya uğramadan)
   tek elemanlı bir evren verilerek de aynı sayıları üretiyor.

Geri kalan sınıflar çok enstrümanlıya özgü davranışları ölçüyor: barı kaybolan
enstrümanın değerlemesi, ortak ızgara, ve sonuç kaydının atlama sebebi listesinin
büyümesine karşı dayanıklılığı.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from scryne_quant.backtest.coklu_motor import CokluBacktest, CokluBacktestHatasi
from scryne_quant.backtest.motor import Backtest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.strategy.evren import LISTELENMEDI
from scryne_quant.strategy.kosu import evren_gorunum_kur
from tests.conftest import PlanliHedef, PlanliStrateji, bar_uret

KOK = Path(__file__).resolve().parents[2]
FIXTURE = KOK / "tests" / "fixtures" / "backtest_referans.json"
REFERANS = json.loads(FIXTURE.read_text(encoding="utf-8"))
SENARYOLAR = {s["ad"]: s for s in REFERANS["senaryolar"]}
TOLERANS = 1e-12
SEMBOL = "BTCUSDT"


def _bar_dizileri(barlar: list[dict]) -> dict[str, np.ndarray]:
    sayisal = ("open", "high", "low", "close", "volume", "quote_volume")
    diziler: dict[str, np.ndarray] = {
        "open_time": np.array([b["open_time"] for b in barlar], dtype="int64"),
        "trades": np.array([b["trades"] for b in barlar], dtype="int64"),
        "quality_status": np.array([b["quality_status"] for b in barlar], dtype=object),
    }
    for alan in sayisal:
        diziler[alan] = np.array([float(b[alan]) for b in barlar], dtype="float64")
    return diziler


class TestTekEnstrumanOzelHal:
    """K-052/2: tek enstrüman çok enstrümanlının özel hâli, "yakın" değil **aynı**."""

    def test_tek_motor_kalmadi(self):
        """`backtest/motor.py` kendi event loop'unu **taşımıyor**: tek kod yolu (K-001).

        İki döngünün "aynı sonucu verdiğini" test etmek, tek döngünün aynı sonucu
        vermesiyle aynı şey değil: ikisi bir gün ayrışabilir, tek kod yolu ayrışamaz.
        Tarama statik — modülü import edip davranışına bakmak bu ayrışmayı göstermez.
        """
        kaynak = (KOK / "src" / "scryne_quant" / "backtest" / "motor.py").read_text(
            encoding="utf-8"
        )
        agac = ast.parse(kaynak)
        cagrilar = {
            d.func.attr
            for d in ast.walk(agac)
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
        }
        assert "calistir" in cagrilar, "sarmalayıcı çok enstrümanlı motoru çağırmıyor"
        # Kendi döngüsü olsaydı fill/defter katmanına doğrudan dokunurdu.
        for yasak in ("emir_hazirla", "uygula_coklu", "emirleri_hazirla", "bar_isle"):
            assert yasak not in kaynak, (
                f"tek sembollü motor kendi event loop'unu geri getirmiş ({yasak})"
            )

    @pytest.mark.parametrize("senaryo_adi", ["tam_giris_cikis", "kismi_maruziyet"])
    def test_faz3_referansi_coklu_motorda_ayni(self, senaryo_adi: str):
        """Faz 3'ün Decimal referansı, tek elemanlı bir evrende de birebir çıkıyor.

        Sarmalayıcıya uğramadan: burada `CokluBacktest` doğrudan çağrılıyor ve sonuç
        **çok enstrümanlı biçimde** (evren kaydıyla) kuruluyor. Yani eşitlik, kaydın
        biçiminden değil aritmetiğinden geliyor.
        """
        senaryo = SENARYOLAR[senaryo_adi]
        maliyet = MaliyetModeli(**REFERANS["maliyet"])
        diziler = _bar_dizileri(senaryo["barlar"])
        n = len(diziler["open_time"])
        takvim = {
            s["bar"]: {SEMBOL: float(s["target_exposure"])} for s in senaryo["sinyaller"]
        }
        strateji = PlanliHedef(takvim)
        gorunum = evren_gorunum_kur(
            "1h", {SEMBOL: diziler}, {SEMBOL: np.ones(n, dtype=bool)}, strateji
        )
        sonuc = CokluBacktest(
            strateji, maliyet, baslangic_sermaye=float(REFERANS["baslangic_sermaye"])
        ).calistir(gorunum)

        beklenen = senaryo["beklenen"]
        assert sonuc.metrikler.islem_sayisi == beklenen["ozet"]["islem_sayisi"]
        for i, (bizim, ref) in enumerate(
            zip(sonuc.islemler, beklenen["turlar"], strict=True)
        ):
            for alan, anahtar in (
                ("giris_notional", "giris_notional"),
                ("cikis_notional", "cikis_notional"),
                ("komisyon", "komisyon"),
                ("slippage", "slippage"),
                ("net_pnl", "net_pnl"),
            ):
                b, r = getattr(bizim, alan), float(ref[anahtar])
                assert abs(b - r) <= TOLERANS * max(abs(r), 1.0), f"tur {i} {alan}"
        for i, (bizim, ref) in enumerate(
            zip(sonuc.ozkaynak, beklenen["ozkaynak"], strict=True)
        ):
            r = float(ref)
            assert abs(float(bizim) - r) <= TOLERANS * max(abs(r), 1.0), f"bar {i} özkaynak"

    def test_sarmalayici_ile_dogrudan_kosu_ayni_sayilari_veriyor(self):
        """`Backtest` ile doğrudan `CokluBacktest`: equity eğrisi **bit düzeyinde** aynı."""
        senaryo = SENARYOLAR["kismi_maruziyet"]
        maliyet = MaliyetModeli(**REFERANS["maliyet"])
        diziler = _bar_dizileri(senaryo["barlar"])
        n = len(diziler["open_time"])
        takvim_tek = {
            s["bar"]: (s["side"], float(s["target_exposure"])) for s in senaryo["sinyaller"]
        }
        takvim_coklu = {
            s["bar"]: {SEMBOL: float(s["target_exposure"])} for s in senaryo["sinyaller"]
        }

        tek = Backtest(PlanliStrateji(takvim_tek), maliyet).calistir("BTCUSDT", "1h", diziler)
        strateji = PlanliHedef(takvim_coklu)
        gorunum = evren_gorunum_kur(
            "1h", {SEMBOL: diziler}, {SEMBOL: np.ones(n, dtype=bool)}, strateji
        )
        coklu = CokluBacktest(strateji, maliyet).calistir(gorunum)

        assert np.array_equal(tek.ozkaynak, coklu.ozkaynak)
        assert np.array_equal(tek.maruziyet, coklu.maruziyet)
        assert tek.metrikler.sozluk() == coklu.metrikler.sozluk()

    def test_tek_sembollu_kayit_bicimi_degismedi(self):
        """Tek sembollü koşuda `evren` yazılmaz ve işlem satırında sembol olmaz (K-009).

        Yazılsaydı Faz 1-7'de `runs/` altına kaydedilmiş her sonucun `sonuc_hash`i
        değişirdi — çok enstrümanlı motoru eklemek, onu hiç kullanmayan eski deneyleri
        yeniden üretilemez yapardı.
        """
        senaryo = SENARYOLAR["tam_giris_cikis"]
        takvim = {
            s["bar"]: (s["side"], float(s["target_exposure"])) for s in senaryo["sinyaller"]
        }
        sonuc = Backtest(
            PlanliStrateji(takvim), MaliyetModeli(**REFERANS["maliyet"])
        ).calistir("BTCUSDT", "1h", _bar_dizileri(senaryo["barlar"]))
        kayit = sonuc.sozluk()
        assert "evren" not in kayit
        assert sonuc.evren is None
        assert all("sembol" not in satir for satir in kayit["islemler"])
        assert sonuc.veri.sembol == "BTCUSDT"


class TestKayitDayanikliligi:
    def test_sifir_atlama_sayaci_hash_degistirmiyor(self):
        """Yeni bir `AtlamaSebebi` eklemek, o sebebi hiç üretmemiş koşuların hash'ini bozmaz.

        Ölçüldü ve bir kez gerçekten oldu: Faz 4'ün tarama kayıtları, Faz 5/6'da eklenen
        `risk_reddetti` ve `veri_bayat` sayaçları yüzünden yeniden üretilemez hâle geldi —
        üstelik **hiçbir ekonomik değer değişmemişken** (Faz 10 raporu §3). Sıfır sayaç
        hash'e girmiyor; kayda (okunabilirlik için) yazılmaya devam ediyor.
        """
        from dataclasses import replace

        senaryo = SENARYOLAR["tam_giris_cikis"]
        takvim = {
            s["bar"]: (s["side"], float(s["target_exposure"])) for s in senaryo["sinyaller"]
        }
        sonuc = Backtest(
            PlanliStrateji(takvim), MaliyetModeli(**REFERANS["maliyet"])
        ).calistir("BTCUSDT", "1h", _bar_dizileri(senaryo["barlar"]))

        genisletilmis = replace(sonuc, atlanan=sonuc.atlanan | {"yeni_bir_sebep": 0})
        assert genisletilmis.sonuc_hash == sonuc.sonuc_hash
        assert "yeni_bir_sebep" in genisletilmis.sozluk()["akis"]["atlanan"]

    def test_sifir_olmayan_atlama_hash_degistiriyor(self):
        """Dayanıklılık körlük olmasın: gerçekten atlanan bir sinyal hash'i değiştirmeli."""
        from dataclasses import replace

        senaryo = SENARYOLAR["tam_giris_cikis"]
        takvim = {
            s["bar"]: (s["side"], float(s["target_exposure"])) for s in senaryo["sinyaller"]
        }
        sonuc = Backtest(
            PlanliStrateji(takvim), MaliyetModeli(**REFERANS["maliyet"])
        ).calistir("BTCUSDT", "1h", _bar_dizileri(senaryo["barlar"]))
        bozuk = replace(sonuc, atlanan=sonuc.atlanan | {"nakit_yok": 1})
        assert bozuk.sonuc_hash != sonuc.sonuc_hash


def _iki_sembollu(n: int = 120):
    diziler = {
        "AAAUSDT": bar_dizileri(bar_uret(n=n, tohum=3)),
        "BBBUSDT": bar_dizileri(bar_uret(n=n, tohum=4)),
    }
    uyelik = {s: np.ones(n, dtype=bool) for s in diziler}
    return diziler, uyelik


class TestBariOlmayanEnstruman:
    """Delist / henüz listelenmemiş enstrümanın davranışı."""

    def test_pozisyon_kapatilamayinca_bayat_fiyatla_degerleniyor(self):
        n = 120
        diziler, uyelik = _iki_sembollu(n)
        kayip_bar = 40
        for alan in ("open", "high", "low", "close", "volume", "quote_volume"):
            diziler["BBBUSDT"][alan] = np.array(diziler["BBBUSDT"][alan])
            diziler["BBBUSDT"][alan][kayip_bar:] = np.nan
        diziler["BBBUSDT"]["quality_status"] = np.array(
            diziler["BBBUSDT"]["quality_status"], dtype=object
        )
        diziler["BBBUSDT"]["quality_status"][kayip_bar:] = LISTELENMEDI
        uyelik["BBBUSDT"] = np.array(uyelik["BBBUSDT"])
        uyelik["BBBUSDT"][kayip_bar:] = False

        strateji = PlanliHedef({10: {"AAAUSDT": 0.4, "BBBUSDT": 0.4}, 60: {"BBBUSDT": 0.0}})
        gorunum = evren_gorunum_kur("1h", diziler, uyelik, strateji)
        sonuc = CokluBacktest(
            strateji, MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
        ).calistir(gorunum)

        assert sonuc.atlanan["bayat_degerleme"] > 0, "bayat değerleme sayılmamış"
        assert sonuc.acik_pozisyon_sonda, "kapatılamayan pozisyon sessizce yok olmuş"
        # Sıfıra yazılmadı: özkaynak son bilinen fiyattan hesaplanıyor.
        assert float(sonuc.ozkaynak[-1]) > 0.0
        # Strateji 60. barda BBB'yi kapatmak istedi ama sembol görünmüyordu: hedef hiç
        # üretilmedi ve bu sessizce değil, sayılabilir biçimde oldu.
        assert (60, "BBBUSDT") in strateji.atlanan_semboller

    # ---------------------------------------------------- sıfıra yazma politikası (K-059)

    @staticmethod
    def _bosluklu(n: int, bas: int, bit: int | None):
        """BBB `bas`..`bit` arasında barsız (bit None = delist)."""
        diziler, uyelik = _iki_sembollu(n)
        son = n if bit is None else bit
        b = diziler["BBBUSDT"]
        for alan in ("open", "high", "low", "close", "volume", "quote_volume"):
            b[alan] = np.array(b[alan])
            b[alan][bas:son] = np.nan
        b["quality_status"] = np.array(b["quality_status"], dtype=object)
        b["quality_status"][bas:son] = LISTELENMEDI
        uyelik["BBBUSDT"] = np.array(uyelik["BBBUSDT"])
        uyelik["BBBUSDT"][bas:son] = False
        return diziler, uyelik

    @staticmethod
    def _kos(diziler, uyelik, sifira_yaz_bar):
        strateji = PlanliHedef({10: {"AAAUSDT": 0.4, "BBBUSDT": 0.4}})
        g = evren_gorunum_kur("1h", diziler, uyelik, strateji)
        return CokluBacktest(
            strateji, MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0),
            sifira_yaz_bar=sifira_yaz_bar,
        ).calistir(g)

    def test_politika_kapaliyken_kayit_degismiyor(self):
        diziler, uyelik = self._bosluklu(120, 40, None)
        a = self._kos(diziler, uyelik, None)
        assert "sifira_yazma" not in a.evren

    def test_esikten_once_son_fiyat_esikte_sifir(self):
        n, bas, esik = 120, 40, 12
        diziler, uyelik = self._bosluklu(n, bas, None)
        eski = self._kos(diziler, uyelik, None)
        yeni = self._kos(diziler, uyelik, esik)
        # Barı olmayan ilk `esik - 1` barda iki politika aynı değerliyor.
        assert np.array_equal(eski.ozkaynak[: bas + esik - 1], yeni.ozkaynak[: bas + esik - 1])
        # Eşikten sonra fark tam olarak BBB'nin son fiyattan değeri: sıfıra yazıldı.
        miktar = sum(i.giris_miktar - i.cikis_miktar for i in eski.islemler
                     if i.sembol == "BBBUSDT" and i.kapanis_ms is None)
        son_fiyat = float(diziler["BBBUSDT"]["close"][bas - 1])
        fark = eski.ozkaynak[bas + esik:] - yeni.ozkaynak[bas + esik:]
        assert miktar > 0.0
        assert np.allclose(fark, miktar * son_fiyat, rtol=1e-12, atol=1e-9)
        assert yeni.evren["sifira_yazma"] == {
            "bar": esik, "sifira_yazilan_pozisyon_bar": n - (bas + esik - 1),
        }
        assert yeni.sonuc_hash != eski.sonuc_hash

    def test_bar_geri_gelince_piyasa_fiyatina_donuyor(self):
        """Uzun durdurma (FTT tipi): sıfır geçici, bar dönünce değerleme yeniden piyasadan."""
        n, bas, bit, esik = 160, 40, 90, 12
        diziler, uyelik = self._bosluklu(n, bas, bit)
        eski = self._kos(diziler, uyelik, None)
        yeni = self._kos(diziler, uyelik, esik)
        assert np.all(eski.ozkaynak[bas + esik:bit] > yeni.ozkaynak[bas + esik:bit])
        assert np.array_equal(eski.ozkaynak[bit:], yeni.ozkaynak[bit:])

    def test_kisa_bosluk_sifira_yazilmiyor(self):
        diziler, uyelik = self._bosluklu(120, 40, 50)  # 10 bar: 2018 bakımı
        eski = self._kos(diziler, uyelik, None)
        yeni = self._kos(diziler, uyelik, 48)
        assert np.array_equal(eski.ozkaynak, yeni.ozkaynak)
        assert yeni.evren["sifira_yazma"]["sifira_yazilan_pozisyon_bar"] == 0

    def test_sifira_yazma_gelecegi_gormuyor(self):
        """K-002: `t` sonrası bar bozulunca (dönüş/kalış) `t`ye kadarki özkaynak aynı."""
        n, bas, esik, t = 160, 40, 12, 70
        kalici, uk = self._bosluklu(n, bas, None)
        donen, ud = self._bosluklu(n, bas, t + 1)
        a = self._kos(kalici, uk, esik)
        b = self._kos(donen, ud, esik)
        assert np.array_equal(a.ozkaynak[: t + 1], b.ozkaynak[: t + 1])

    def test_gecersiz_esik_reddediliyor(self):
        with pytest.raises(CokluBacktestHatasi):
            CokluBacktest(
                PlanliHedef({}), MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0),
                sifira_yaz_bar=0,
            )

    def test_gorunmeyen_sembol_icin_hedef_uretilemiyor(self):
        """Strateji `ctx.gorunur()` dışında bir sembol için hedef veremez."""
        n = 60
        diziler, uyelik = _iki_sembollu(n)
        uyelik["BBBUSDT"] = np.zeros(n, dtype=bool)
        strateji = PlanliHedef({10: {"AAAUSDT": 0.4, "BBBUSDT": 0.4}})
        gorunum = evren_gorunum_kur("1h", diziler, uyelik, strateji)
        sonuc = CokluBacktest(
            strateji, MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
        ).calistir(gorunum)
        assert ("BBBUSDT" in {s for _, s in strateji.atlanan_semboller})
        assert all(i.sembol == "AAAUSDT" for i in sonuc.islemler)


class TestKurulum:
    def test_iki_bardan_az_reddediliyor(self):
        diziler, uyelik = _iki_sembollu(2)
        strateji = PlanliHedef({})
        gorunum = evren_gorunum_kur("1h", diziler, uyelik, strateji)
        with pytest.raises(CokluBacktestHatasi, match="ölçüm başlangıcı"):
            CokluBacktest(strateji, MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)).calistir(
                gorunum, olcum_baslangici=1
            )

    def test_negatif_sermaye_reddediliyor(self):
        with pytest.raises(CokluBacktestHatasi, match="pozitif"):
            CokluBacktest(
                PlanliHedef({}),
                MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0),
                baslangic_sermaye=0.0,
            )

    def test_determinizm(self):
        diziler, uyelik = _iki_sembollu()
        takvim = {10: {"AAAUSDT": 0.4, "BBBUSDT": 0.3}, 50: {"AAAUSDT": 0.0, "BBBUSDT": 0.6}}
        hashler = []
        for _ in range(2):
            strateji = PlanliHedef(takvim)
            gorunum = evren_gorunum_kur("1h", diziler, uyelik, strateji)
            hashler.append(
                CokluBacktest(
                    strateji, MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
                ).calistir(gorunum).sonuc_hash
            )
        assert hashler[0] == hashler[1]

    def test_ayni_ornekle_ikinci_kosu_ayni(self):
        """`hazirla()` durumu sıfırlıyor mu (K-009)."""
        diziler, uyelik = _iki_sembollu()
        strateji = PlanliHedef({10: {"AAAUSDT": 0.4}, 50: {"AAAUSDT": 0.0}})
        gorunum = evren_gorunum_kur("1h", diziler, uyelik, strateji)
        motor = CokluBacktest(strateji, MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0))
        assert motor.calistir(gorunum).sonuc_hash == motor.calistir(gorunum).sonuc_hash
