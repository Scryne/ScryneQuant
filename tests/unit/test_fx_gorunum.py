"""R4 Paket 4 (K-096): gerçek FXCM Parquet → `PiyasaGorunumu` → motor → bid/ask fill, uçtan uca.

Fixture `tests/fixtures/fx/` gerçek EURUSD deposunun 2024 h2-h8 dilimidir
(`tools/fx_fixture_uret.py`, 839 bar, FxDepo yazımı, bayt-aynı). K-057 kalıbı: (1) **statik** —
kripto `hizala`/`veri_kur` dokunulmadı, kripto kaydında yeni anahtar yok (test_fx_fill_spread /
test_finansman); (2) **uçtan uca** — fixture → `fx_kur` → `CokluBacktest(takvim=fx-5x24,
maliyetler, finansmanlar)` → fill fiyatları Parquet'teki `ask_open`/`bid_open`dan (`Decimal`
≤ 1e-12), spread ve rollover kayda; (3) **kalite/takvim** — gerçek dilimde 839/839 `ok`; bozulan
bar `suspect` olur ve motor o barda doldurmaz (`fill_bari_ok_degil`); takvim dışı damga, hizasız
damga, eksik sütun → hata; `sq evren backtest` FX tablosunu tanır ve model dosyası yoksa
**başlamaz**.
"""

from __future__ import annotations

import json
from decimal import Decimal, getcontext
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.backtest.fill import AtlamaSebebi
from scryne_quant.common import finansman as fin_mod
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.finansman import FinansmanKaynagi, FinansmanModeli, SembolFinansmani
from scryne_quant.common.maliyet import MaliyetModeli, SembolMaliyeti
from scryne_quant.data import fx_gorunum as fxg
from scryne_quant.data.fx import FxDepo
from scryne_quant.data.izgara import IzgaraHatasi
from scryne_quant.data.takvim import TAKVIM_24X7, TAKVIM_FX_5X24, takvim
from scryne_quant.research import evren_kosu
from scryne_quant.strategy.baglam import PiyasaGorunumu
from scryne_quant.strategy.evren import LISTELENMEDI
from tests.conftest import PlanliHedef

getcontext().prec = 50

KOK = Path(__file__).resolve().parents[2]
FIXTURE = KOK / "tests" / "fixtures" / "fx"
TABLO = FIXTURE / "_evren" / "8f90232205e9.parquet"
TFX = takvim(TAKVIM_FX_5X24)
SAAT = 3_600_000
TOLERANS = 1e-12
MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
KAYMASIZ = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=0.0)
FINANSMAN = FinansmanModeli(
    uzun_gunluk_bps=2.5,
    kaynak=FinansmanKaynagi(saglayici="test", tarih="2026-09-21", gerekce="fixture"),
)


def _ms(metin: str) -> int:
    return int(pd.Timestamp(metin, tz="UTC").value // 1_000_000)


def _ham() -> pd.DataFrame:
    return FxDepo(FIXTURE).oku("EURUSD")


def _kurulum(hedefler, **kw):
    strateji = PlanliHedef(hedefler)
    return strateji, evren_kosu.fx_kur(TABLO, strateji, depo_kok=FIXTURE, **kw)


def _kosu(hedefler, maliyet=MALIYET, *, finansman=True, takvim_=TFX):
    strateji, kurulum = _kurulum(hedefler)
    motor = CokluBacktest(
        strateji,
        maliyet,
        takvim=takvim_,
        maliyetler={"EURUSD": SembolMaliyeti(fxg.MALIYET_MODELI_FX, maliyet)},
        finansmanlar=(
            {"EURUSD": SembolFinansmani(fxg.finansman_modeli_id("EURUSD"), FINANSMAN)}
            if finansman
            else None
        ),
    )
    return kurulum, motor.calistir(
        kurulum.gorunum,
        veri_sha256=kurulum.veri_sha256,
        olcum_baslangici=kurulum.olcum_baslangici,
    )


# ------------------------------------------------------------------ adaptör


class TestAdaptor:
    def test_fixture_gercek_dilim_ve_bayt_sabit(self):
        manifesto = FxDepo(FIXTURE).manifesto("EURUSD")
        assert manifesto["bar_sayisi"] == 839
        assert set(manifesto["haftalar"]) == {f"2024-{h}" for h in range(2, 9)}
        assert (
            manifesto["sha256"]
            == "ced350678333d309685ff493b9c574a0b1b41054b40d76f39e1dc428f4db5f2c"
        )
        meta = json.loads(TABLO.with_suffix(".json").read_text(encoding="utf-8"))
        assert evren_kosu.fx_tablo_mu(meta) and meta["kaynak_depo"]["pair"] == "EURUSD"

    def test_gercek_dilim_kalite_239_ok(self):
        bayrakli, rapor = fxg.fx_dogrula(_ham(), TFX, pair="EURUSD")
        assert rapor["bayraklar"] == {"ok": 839} and rapor["suspect_nedenleri"] == {}
        assert rapor["beklenen_bar"] == 839 and rapor["bosluk_sayisi"] == 0
        assert rapor["kisa_saat"] == 51  # rollover dakikası: bilgi, bayrak değil
        assert rapor["takvim"] == {"kimlik": TAKVIM_FX_5X24, "icerik_hash": TFX.icerik_hash}
        assert list(bayrakli["quality_status"].unique()) == ["ok"]

    def test_barlar_orta_fiyat_ve_bid_ask_aynen(self):
        ham = _ham()
        bayrakli, _ = fxg.fx_dogrula(ham, TFX)
        d = fxg.fx_barlar(bayrakli)
        for a in ("open", "high", "low", "close"):
            assert np.array_equal(
                d[a], (ham[f"bid_{a}"].to_numpy() + ham[f"ask_{a}"].to_numpy()) / 2
            )
            assert np.array_equal(d[f"bid_{a}"], ham[f"bid_{a}"].to_numpy())
            assert np.array_equal(d[f"ask_{a}"], ham[f"ask_{a}"].to_numpy())
        assert np.isnan(d["volume"]).all() and np.isnan(d["quote_volume"]).all()
        assert (d["trades"] == 0).all() and np.array_equal(d["m1_sayisi"], ham["m1_sayisi"])
        assert (d["bid_open"] <= d["open"]).all() and (d["open"] <= d["ask_open"]).all()
        PiyasaGorunumu(sembol="EURUSD", timeframe="1h", barlar=d)  # sözleşmeyi karşılıyor

    def test_izgara_listelenmedi_ile_isaretler_uydurma_bar_yok(self):
        bayrakli, _ = fxg.fx_dogrula(_ham(), TFX)
        d = fxg.fx_barlar(bayrakli)
        # Hafta sonunu **içermeyen** ama bir saat ekleyen ızgara: eklenen saat listelenmedi.
        z = np.concatenate([d["open_time"], [d["open_time"][-1] + SAAT]])
        h = fxg.fx_hizala(d, z)
        assert h["quality_status"][-1] == LISTELENMEDI and np.isnan(h["ask_open"][-1])
        assert h["m1_sayisi"][-1] == 0 and (h["quality_status"][:-1] == "ok").all()
        with pytest.raises(fxg.FxGorunumHatasi, match="ızgara"):
            fxg.fx_hizala(d, d["open_time"][:-1])

    def test_hafta_anahtari_pazar_basli(self):
        assert fxg.hafta_anahtari(_ms("2024-01-07 22:00")) == "2024-2"  # Pazar açılışı
        assert fxg.hafta_anahtari(_ms("2024-01-12 21:00")) == "2024-2"  # Cuma kapanışı
        assert fxg.hafta_anahtari(_ms("2024-01-14 22:00")) == "2024-3"

    def test_enstruman_tablodaki_kimlikle_cfd(self):
        e = fxg.fx_enstruman("EURUSD", _ms("2024-02-23 21:00"), 839)
        tablo = pd.read_parquet(TABLO)
        assert e.kanonik_id == tablo["kanonik_id"].iloc[0] == "fxcm-fx:cfd:EURUSD@2012-01-01"
        assert e.instrument_type == "cfd" and e.takvim_id == TAKVIM_FX_5X24
        assert e.maliyet_modeli_id == "fxcm-fx" and e.finansman_modeli_id == "fxcm-eurusd"


# ------------------------------------------------------------------ kalite: fail closed


class TestKalite:
    def test_capraz_kotasyon_suspect_ve_motor_doldurmaz(self):
        """Fill barının ask'i bid'in altına çekilirse bar `suspect`; motor o barda doldurmaz."""
        ham = _ham()
        i = 5
        bozuk = ham.copy()
        bozuk.loc[i, "ask_open"] = bozuk.loc[i, "bid_open"] - 0.0001
        bayrakli, rapor = fxg.fx_dogrula(bozuk, TFX)
        assert rapor["suspect_nedenleri"] == {"capraz_kotasyon": 1}
        assert bayrakli["quality_status"].iloc[i] == "suspect"
        d = fxg.fx_barlar(bayrakli)
        strateji = PlanliHedef({i - 1: {"EURUSD": 0.5}})
        from scryne_quant.strategy.kosu import evren_gorunum_kur

        g = evren_gorunum_kur(
            "1h", {"EURUSD": d}, {"EURUSD": np.ones(len(d["open_time"]), bool)}, strateji
        )
        sonuc = CokluBacktest(strateji, MALIYET, takvim=TFX).calistir(g)
        assert sonuc.islemler == [] and sonuc.atlanan[str(AtlamaSebebi.FILL_BARI_OK_DEGIL)] == 1

    def test_suspect_kurallari(self):
        ham = _ham()
        for alan, deger, neden in (
            ("bid_high", 0.5, "high_govdeyi_kapsamiyor"),
            ("ask_low", 9.0, "low_govdeyi_kapsamiyor"),
            ("bid_open", -1.0, "pozitif_olmayan_fiyat"),
            ("ask_close", float("nan"), "sonlu_olmayan"),
            ("m1_sayisi", 61, "m1_sozlesme_disi"),
        ):
            bozuk = ham.copy()
            bozuk.loc[10, alan] = deger
            _, rapor = fxg.fx_dogrula(bozuk, TFX)
            assert neden in rapor["suspect_nedenleri"], (alan, rapor["suspect_nedenleri"])

    def test_gap_takvimin_bekledigi_saat(self):
        ham = _ham()
        eksik = ham.drop(index=[20, 21]).reset_index(drop=True)  # hafta içi iki saat
        bayrakli, rapor = fxg.fx_dogrula(eksik, TFX)
        assert rapor["bosluk_sayisi"] == 1 and rapor["eksik_bar"] == 2
        assert bayrakli["quality_status"].iloc[20] == "gap"
        # Hafta sonu boşluğu (Cuma 21:00 → Pazar 22:00) gap değil: gerçek dilimde 0 boşluk vardı.

    def test_takvim_disi_hizasiz_eksik_sutun_hata(self):
        ham = _ham()
        cumartesi = ham.copy()
        cumartesi.loc[0, "open_time"] = _ms("2024-01-13 12:00")
        with pytest.raises(fxg.FxGorunumHatasi, match="kapalı saydığı"):
            fxg.fx_dogrula(cumartesi.sort_values("open_time"), TFX)
        hizasiz = ham.copy()
        hizasiz.loc[0, "open_time"] += 1
        with pytest.raises(fxg.FxGorunumHatasi, match="hizalı"):
            fxg.fx_dogrula(hizasiz, TFX)
        with pytest.raises(fxg.FxGorunumHatasi, match="eksik sütun"):
            fxg.fx_dogrula(ham.drop(columns=["ask_open"]), TFX)
        with pytest.raises(fxg.FxGorunumHatasi, match="seanslı"):
            fxg.fx_dogrula(ham, takvim(TAKVIM_24X7))
        with pytest.raises(fxg.FxGorunumHatasi, match="tekil"):
            fxg.fx_dogrula(pd.concat([ham, ham.iloc[[3]]]).sort_values("open_time"), TFX)

    def test_ortak_izgara_seans_disi_damgayi_reddeder(self):
        z = np.append(_ham()["open_time"].to_numpy(), _ms("2024-01-13 12:00"))
        from scryne_quant.data.izgara import ortak_izgara

        with pytest.raises(IzgaraHatasi, match="seans dışı"):
            ortak_izgara([np.sort(z)], "1h", takvim=TFX)


# ------------------------------------------------------------------ uçtan uca


#: bar 2'de %50 al → bar 3 açılışı (ask); Çar 09:00 barında düze → sonraki bar açılışı (bid).
HEDEFLER = {2: {"EURUSD": 0.5}, 60: {"EURUSD": 0.0}}


class TestUctanUca:
    def test_kurulum_gercek_dilim(self):
        _, kurulum = _kurulum(HEDEFLER)
        g = kurulum.gorunum
        assert len(g) == 839 and g.semboller == ("EURUSD",)
        assert bool(g.uyelik["EURUSD"].all())  # iki hafta da üye, her saat barı var
        assert kurulum.meta["takvim"]["id"] == TAKVIM_FX_5X24
        assert kurulum.meta["kalite"]["EURUSD"]["bayraklar"] == {"ok": 839}
        assert kurulum.meta["bar_yok_uyelik"] == {}
        assert kurulum.veri_sha256["EURUSD"].startswith("ced35067")
        assert [e.finansman_modeli_id for e in kurulum.kimlikler["EURUSD"]] == ["fxcm-eurusd"]
        assert "bid_open" in g.gorunumler["EURUSD"].barlar

    @pytest.mark.parametrize("maliyet", [MALIYET, KAYMASIZ], ids=["kaymali", "kaymasiz"])
    def test_fill_parquetteki_ask_ve_bidden(self, maliyet):
        ham = _ham()
        kurulum, sonuc = _kosu(HEDEFLER, maliyet)
        z = kurulum.gorunum.zamanlar
        [tur] = sonuc.islemler
        s = Decimal(str(maliyet.slippage_bps)) / Decimal(10_000)
        al_bar, sat_bar = (
            int(np.searchsorted(z, tur.acilis_ms)),
            int(np.searchsorted(z, tur.kapanis_ms)),
        )
        assert (al_bar, sat_bar) == (3, 61)
        ask = Decimal(float(ham.loc[al_bar, "ask_open"]))
        bid = Decimal(float(ham.loc[sat_bar, "bid_open"]))
        al = Decimal(tur.giris_notional) / Decimal(tur.giris_miktar)
        sat = Decimal(tur.cikis_notional) / Decimal(tur.cikis_miktar)
        assert abs(al - ask * (1 + s)) <= Decimal(TOLERANS) * ask
        assert abs(sat - bid * (1 - s)) <= Decimal(TOLERANS) * bid
        # Spread bileşeni: yarım spread × miktar, iki bacak; Parquet'teki gerçek spread'den.
        mid_al = (Decimal(float(ham.loc[al_bar, "bid_open"])) + ask) / 2
        mid_sat = (bid + Decimal(float(ham.loc[sat_bar, "ask_open"]))) / 2
        beklenen_spread = (ask - mid_al) * Decimal(tur.giris_miktar) + (mid_sat - bid) * Decimal(
            tur.cikis_miktar
        )
        assert abs(Decimal(tur.spread) - beklenen_spread) <= Decimal(TOLERANS)
        assert tur.spread > 0.0 and sonuc.metrikler.toplam_spread == tur.spread

    def test_rollover_ve_kayit_bloklari(self):
        kurulum, sonuc = _kosu(HEDEFLER)
        [tur] = sonuc.islemler
        # Pzt 8 Oca 22:00 ve Sal 9 Oca 22:00 rollover'ları tur içinde (Çar 10:00'da kapandı): 2 gün.
        z = kurulum.gorunum.zamanlar
        g = TFX.rollover_gunleri(z, 2)
        icerde = int(g[3:61].sum())
        assert icerde == 2 and tur.finansman > 0.0
        assert sonuc.takvim == {"id": TAKVIM_FX_5X24, "icerik_hash": TFX.icerik_hash}
        k = sonuc.sozluk()
        assert k["config"]["takvim"] == sonuc.takvim
        assert k["config"]["maliyetler"]["EURUSD"]["id"] == "fxcm-fx"
        assert k["config"]["finansmanlar"]["EURUSD"]["id"] == "fxcm-eurusd"
        assert k["metrikler"]["toplam_finansman"] == tur.finansman
        assert k["islemler"][0]["spread"] == tur.spread and k["islemler"][0]["sembol"] == "EURUSD"
        assert k["evren"]["enstruman_sayisi"] == 1 and k["evren"]["uye_bar_toplami"] == 839

    def test_deterministik(self):
        a, b = _kosu(HEDEFLER)[1], _kosu(HEDEFLER)[1]
        assert a.sonuc_hash == b.sonuc_hash and a.config_hash == b.config_hash

    def test_finansmansiz_ve_24x7_reddi(self):
        _, yok = _kosu(HEDEFLER, finansman=False)
        assert yok.finansmanlar is None and yok.metrikler.toplam_finansman is None
        assert yok.metrikler.toplam_spread > 0.0
        from scryne_quant.backtest.coklu_motor import CokluBacktestHatasi

        with pytest.raises(CokluBacktestHatasi, match="seanslı takvim"):
            _kosu(HEDEFLER, takvim_=None)

    def test_pencere_ve_isinma(self):
        """Pencere ay bazlı (kripto ile aynı): Ocak = h2-h5'in Ocak barları (Şubat 1-2 kırpılır);
        Şubat = Şubat barları + ısınma; hafta üyeliği tabloya göre, bar kırpması pencereye."""
        _, ocak = _kurulum(HEDEFLER, baslangic_ay="2024-01", bitis_ay="2024-01")
        assert len(ocak.gorunum) == 433 and ocak.olcum_baslangici == 0
        assert int(ocak.gorunum.uyelik["EURUSD"].sum()) == 433
        _, subat = _kurulum(HEDEFLER, baslangic_ay="2024-02")
        assert len(subat.gorunum) == 408 and subat.olcum_baslangici == 2
        with pytest.raises(evren_kosu.EvrenKosuHatasi, match="hiç üyelik"):
            _kurulum(HEDEFLER, baslangic_ay="2025-01")


# ------------------------------------------------------------------ sq


class TestCli:
    def _cli(self, ekstra=()):
        from scryne_quant.cli.main import app

        return CliRunner().invoke(
            app,
            [
                "evren",
                "backtest",
                str(TABLO),
                "--fx-depo",
                str(FIXTURE),
                "--yazma",
                "--json",
                *ekstra,
            ],
        )

    def test_model_dosyasi_yoksa_baslamaz(self, tmp_path, monkeypatch):
        monkeypatch.setattr(maliyet_mod, "VARSAYILAN_KATALOG_DIZINI", tmp_path / "m")
        monkeypatch.setattr(fin_mod, "VARSAYILAN_KATALOG_DIZINI", tmp_path / "f")
        r = self._cli()
        assert r.exit_code != 0
        assert "fxcm-fx" in str(r.exception or r.output) and "dosya yok" in str(
            r.exception or r.output
        )

    def test_finansman_dosyasi_yoksa_baslamaz(self, tmp_path, monkeypatch):
        (tmp_path / "m").mkdir()
        (tmp_path / "m" / "fxcm-fx.json").write_text(MALIYET.model_dump_json(), encoding="utf-8")
        monkeypatch.setattr(maliyet_mod, "VARSAYILAN_KATALOG_DIZINI", tmp_path / "m")
        monkeypatch.setattr(fin_mod, "VARSAYILAN_KATALOG_DIZINI", tmp_path / "f")
        r = self._cli()
        assert r.exit_code != 0 and "fxcm-eurusd" in str(r.exception or r.output)

    def test_modeller_varsa_kosar_takvim_ve_bloklar_kayitta(self, tmp_path, monkeypatch):
        (tmp_path / "m").mkdir()
        (tmp_path / "f").mkdir()
        (tmp_path / "m" / "fxcm-fx.json").write_text(MALIYET.model_dump_json(), encoding="utf-8")
        (tmp_path / "f" / "fxcm-eurusd.json").write_text(
            FINANSMAN.model_dump_json(), encoding="utf-8"
        )
        monkeypatch.setattr(maliyet_mod, "VARSAYILAN_KATALOG_DIZINI", tmp_path / "m")
        monkeypatch.setattr(fin_mod, "VARSAYILAN_KATALOG_DIZINI", tmp_path / "f")
        r = self._cli()
        assert r.exit_code == 0, r.output
        govde = json.loads(r.output)
        assert govde["evren"]["takvim"]["id"] == TAKVIM_FX_5X24
        assert govde["evren"]["kalite"]["EURUSD"]["bayraklar"] == {"ok": 839}
        # Varsayılan kıyas kote hacim ister; FX'te yok → sinyal üretmez (dürüst sıfır).
        assert govde["metrikler"]["islem_sayisi"] == 0
        assert "toplam_finansman" in govde["metrikler"] and "toplam_spread" in govde["metrikler"]
