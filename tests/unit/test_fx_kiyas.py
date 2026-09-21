"""R5 Paket 2 (K-099): hacimsiz FX evren kıyası `fx_evren_esit_agirlik` (K-030).

Kanıt: (1) kripto kıyası dokunulmadı — özellikleri, ısınması ve skoru aynı; (2) gerçek 3 çiftlik
fixture (EURUSD h2-h8, GBPUSD/USDJPY h2-h5) + gerçek model dosyalarıyla kıyas **işlem üretiyor**:
üç çift aynı barda eşit hedefle açılıyor, fill Parquet'teki `ask_open × (1+s)` (`Decimal`),
spread/slippage/komisyon/finansman motor hattından, `gecici_finansman_modeli` engeli duruyor;
(3) PIT çıkışı: üyelikten düşen ama barı olan çift bir sonraki dengelemede `bid`den kapanıyor ve
geri girmiyor; (4) `sq evren backtest --strateji fx_evren_esit_agirlik` koşuyor.
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
from scryne_quant.common.finansman import SembolFinansmani
from scryne_quant.common.maliyet import MaliyetModeli, SembolMaliyeti
from scryne_quant.data.fx import FxDepo
from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.data.takvim import TAKVIM_FX_5X24, takvim
from scryne_quant.research import evren_kosu
from scryne_quant.strategy.evren import LISTELENMEDI
from scryne_quant.strategy.kosu import evren_gorunum_kur
from scryne_quant.strategy.kutuphane import EVREN_KIYAS
from scryne_quant.strategy.kutuphane.evren_esit_agirlik import (
    ATR_PENCERESI,
    HACIM_PENCERESI,
    EvrenEsitAgirlik,
    FxEvrenEsitAgirlik,
)

getcontext().prec = 50

KOK = Path(__file__).resolve().parents[2]
FIXTURE = KOK / "tests" / "fixtures" / "fx"
TABLO = FIXTURE / "_evren" / "27f528fa4aec.parquet"
TFX = takvim(TAKVIM_FX_5X24)
CIFTLER = ("EURUSD", "GBPUSD", "USDJPY")
KAYNAK_2024 = fin_mod.FinansmanKaynagi(
    saglayici="test",
    tarih="2026-09-21",
    gerekce="fixture",
    aralik="2024-01-01..2025-01-01",
    tur="broker",
)
SAAT = 3_600_000
TOLERANS = 1e-12


def _ms(metin: str) -> int:
    return int(pd.Timestamp(metin, tz="UTC").value // 1_000_000)


def _kosu(strateji: FxEvrenEsitAgirlik):
    kurulum = evren_kosu.fx_kur(TABLO, strateji, depo_kok=FIXTURE)
    mal = evren_kosu.enstruman_maliyetleri(maliyet_mod.MaliyetKatalogu(), kurulum.kimlikler)
    fin = evren_kosu.enstruman_finansmanlari(fin_mod.FinansmanKatalogu(), kurulum.kimlikler)
    assert mal is not None and fin is not None
    sonuc = CokluBacktest(
        strateji, maliyet_mod.yukle(), maliyetler=mal, finansmanlar=fin, takvim=TFX
    ).calistir(
        kurulum.gorunum,
        veri_sha256=kurulum.veri_sha256,
        olcum_baslangici=kurulum.olcum_baslangici,
    )
    return kurulum, sonuc


# ------------------------------------------------------------------ statik


class TestStatik:
    def test_kayitli_ve_kripto_kiyasi_ayni(self):
        assert EVREN_KIYAS["evren_esit_agirlik"] is EvrenEsitAgirlik
        assert EVREN_KIYAS["fx_evren_esit_agirlik"] is FxEvrenEsitAgirlik
        k = EvrenEsitAgirlik()
        assert [o.ad for o in k.ozellikler()] == ["atr", "kote_hacim"]
        assert k.isinma_bar() == max(ATR_PENCERESI, HACIM_PENCERESI) + 2 == 722
        assert k._hazirlik_ozellikleri() == ("atr", "kote_hacim")
        assert k.sozluk()["kiyas"] is True and "hacimsiz" not in k.sozluk()

    def test_fx_kiyasi_hacimsiz(self):
        f = FxEvrenEsitAgirlik()
        assert [o.ad for o in f.ozellikler()] == ["atr"] and f.isinma_bar() == ATR_PENCERESI + 2
        assert f._hazirlik_ozellikleri() == ("atr",) and f._skor(None) == 0.0
        s = f.sozluk()
        assert s["kiyas"] is True and s["hacimsiz"] is True and s["ad"] == "fx_evren_esit_agirlik"
        assert (
            s["parametreler"]["azami_enstruman"] == 21
        )  # sözleşmedeki çift sayısı: tavan bağlamaz
        assert s["parametreler"]["yeniden_dengele_bar"] == 120  # bir seans haftası (1h)


# ------------------------------------------------------------------ gerçek fixture


class TestGercekFixture:
    def test_islem_uretiyor_uc_cift_esit_hedef(self):
        kurulum, sonuc = _kosu(FxEvrenEsitAgirlik())
        g = kurulum.gorunum
        assert {c: int(g.uyelik[c].sum()) for c in CIFTLER} == {
            "EURUSD": 839,
            "GBPUSD": 479,
            "USDJPY": 479,
        }
        assert sum(i.fill_sayisi for i in sonuc.islemler) >= 9  # 3 çift × ≥3 dengeleme
        assert sorted(i.sembol for i in sonuc.islemler) == sorted(CIFTLER)
        acilislar = {i.acilis_ms for i in sonuc.islemler}
        assert len(acilislar) == 1  # üçü aynı dengeleme barında açıldı
        m = sonuc.metrikler
        assert m.toplam_spread > 0 and m.toplam_slippage > 0 and m.toplam_komisyon > 0
        assert m.toplam_finansman > 0 and m.azami_maruziyet <= 0.92  # hedef 0,90 + kapanış kayması
        assert m.ortalama_maruziyet > 0.85  # 3 × 0,30 tavan = %90 brüt, hep piyasada
        assert "gecici_finansman_modeli" in sonuc.promotion_engelleri
        assert sonuc.takvim == {"id": TAKVIM_FX_5X24, "icerik_hash": TFX.icerik_hash}
        k = sonuc.sozluk()
        assert k["config"]["maliyetler"]["EURUSD"]["id"] == "fxcm-eurusd"
        assert {k["config"]["finansmanlar"][c]["id"] for c in CIFTLER} == {
            "fxcm-eurusd",
            "fxcm-gbpusd",
            "fxcm-usdjpy",
        }
        assert k["config"]["strateji"]["hacimsiz"] is True

    def test_tek_dengelemede_fill_parquetteki_askten(self):
        """Dengeleme periyodu koşudan uzun → çift başına tek alış: fiyat `ask_open[t] × (1+s)`."""
        kurulum, sonuc = _kosu(FxEvrenEsitAgirlik(yeniden_dengele_bar=100_000))
        z = kurulum.gorunum.zamanlar
        katalog = maliyet_mod.MaliyetKatalogu()
        for tur in sonuc.islemler:
            model = katalog.coz(f"fxcm-{tur.sembol.lower()}", binance_spot_kripto=False)
            s = Decimal(str(model.slippage_bps)) / Decimal(10_000)
            assert tur.fill_sayisi == 1 and not tur.kapali  # al-tut: sonda açık (K-030 istisnası)
            bar = int(np.searchsorted(z, tur.acilis_ms))
            assert bar == ATR_PENCERESI + 1  # ATR 14. barda hazır → hedef; fill `t+1` (K-004)
            ham = FxDepo(FIXTURE).oku(tur.sembol)
            ask = Decimal(float(ham.loc[ham["open_time"] == int(z[bar]), "ask_open"].iloc[0]))
            fiyat = Decimal(tur.giris_notional) / Decimal(tur.giris_miktar)
            assert abs(fiyat - ask * (1 + s)) <= Decimal(TOLERANS) * ask
            assert tur.giris_notional == pytest.approx(3000.0, rel=1e-9)  # 0,30 × 10.000
            assert tur.spread > 0
            assert tur.komisyon == pytest.approx(3000.0 * model.fee_taker_bps * 1e-4, rel=1e-9)
        # Rollover: proxy modelde EURUSD/GBPUSD bedel > 0, USDJPY 0 (lehte carry tabanı, K-098).
        fin = {i.sembol: i.finansman for i in sonuc.islemler}
        assert fin["EURUSD"] > fin["GBPUSD"] > 0 and fin["USDJPY"] == 0.0

    def test_kripto_kiyasi_fxte_hala_sinyal_uretmez(self):
        """Hacim isteyen kıyas FX'te dürüstçe sıfır: hacim uydurulmadı (K-096 davranışı korunur)."""
        strateji = EvrenEsitAgirlik()
        kurulum = evren_kosu.fx_kur(TABLO, strateji, depo_kok=FIXTURE)
        mal = evren_kosu.enstruman_maliyetleri(maliyet_mod.MaliyetKatalogu(), kurulum.kimlikler)
        fin = evren_kosu.enstruman_finansmanlari(fin_mod.FinansmanKatalogu(), kurulum.kimlikler)
        sonuc = CokluBacktest(
            strateji, maliyet_mod.yukle(), maliyetler=mal, finansmanlar=fin, takvim=TFX
        ).calistir(kurulum.gorunum, veri_sha256=kurulum.veri_sha256)
        assert sonuc.islemler == [] and sonuc.uretilen_sinyal == 0


# ------------------------------------------------------------------ PIT çıkışı (sentetik)


def _sentetik(pair: str, n: int, seviye: float) -> dict[str, np.ndarray]:
    """Pzt 2024-01-08 00:00'dan itibaren hafta içi saatlik ızgara (Cuma 21:00'e kadar, 2 hafta)."""
    z1 = np.arange(_ms("2024-01-08 00:00"), _ms("2024-01-12 22:00"), SAAT)
    z2 = np.arange(_ms("2024-01-14 22:00"), _ms("2024-01-19 22:00"), SAAT)
    z = np.concatenate([z1, z2])[:n]
    assert z.size == n
    mid = seviye + 0.00001 * np.arange(z.size)
    return {
        "open_time": z,
        "open": mid,
        "high": mid + 0.0003,
        "low": mid - 0.0003,
        "close": mid + 0.00001,
        "volume": np.full(z.size, np.nan),
        "quote_volume": np.full(z.size, np.nan),
        "trades": np.zeros(z.size, dtype="int64"),
        "quality_status": np.array([str(KaliteDurumu.OK)] * z.size, dtype=object),
        "bid_open": mid - 0.0001,
        "ask_open": mid + 0.0001,
    }


class TestPitCikisi:
    def test_uyelikten_dusen_cift_sonraki_dengelemede_bidden_kapanir(self):
        n, hafta1 = 238, 118  # Pzt 00:00→Cum 21:00 = 118 bar; sonra Paz 22:00→Cum 21:00
        a, b = _sentetik("AAAUSD", n, 1.10), _sentetik("BBBUSD", n, 1.30)
        uyelik_b = np.ones(n, dtype=bool)
        uyelik_b[hafta1:] = False  # ikinci hafta: B üyelikten düşer, barları var
        strateji = FxEvrenEsitAgirlik(
            yeniden_dengele_bar=200, azami_agirlik=0.45
        )  # tek satış; nakit payı
        g = evren_gorunum_kur(
            "1h",
            {"AAAUSD": a, "BBBUSD": b},
            {"AAAUSD": np.ones(n, dtype=bool), "BBBUSD": uyelik_b},
            strateji,
        )
        m = MaliyetModeli(fee_taker_bps=0.26, slippage_bps=1.0)
        fin = fin_mod.FinansmanModeli(
            uzun_gunluk_bps=1.0, kaynak=KAYNAK_2024
        )  # K-101: aralıksız model koşamaz
        sonuc = CokluBacktest(
            strateji,
            m,
            takvim=TFX,
            maliyetler={s: SembolMaliyeti("fxcm-fx", m) for s in ("AAAUSD", "BBBUSD")},
            finansmanlar={
                s: SembolFinansmani(f"fxcm-{s.lower()}", fin) for s in ("AAAUSD", "BBBUSD")
            },
        ).calistir(g)
        z = g.zamanlar
        turlar = {i.sembol: i for i in sonuc.islemler}
        assert set(turlar) == {"AAAUSD", "BBBUSD"} and len(sonuc.islemler) == 2
        bb = turlar["BBBUSD"]
        assert bb.kapali and not turlar["AAAUSD"].kapali
        kapanis_bar = int(np.searchsorted(z, bb.kapanis_ms))
        # Üyelik 118. barda bitti; kapanış = sonraki ilk dengeleme barı + 1 (fill `t+1`, K-004).
        assert kapanis_bar > hafta1 and (kapanis_bar - 1 - ATR_PENCERESI) % 200 == 0
        assert bb.fill_sayisi == 2  # alış (bar 15) + üyelik düşünce tek satış (bar 215)
        s = Decimal("1.0") / Decimal(10_000)
        bid = Decimal(float(b["bid_open"][kapanis_bar]))
        son_fiyat = Decimal(bb.cikis_notional) / Decimal(bb.cikis_miktar)
        assert abs(son_fiyat - bid * (1 - s)) <= Decimal(TOLERANS) * bid
        assert bb.finansman > 0 and turlar["AAAUSD"].finansman > 0
        assert sonuc.atlanan.get(str(AtlamaSebebi.RISK_REDDETTI), 0) == 0


class TestTakiliPozisyon:
    def test_bari_olmayan_pozisyon_brut_hedeften_dusulur(self):
        """K-100/3: B ikinci hafta bar üretmez (bozuk/sağlayıcı boşluğu kalıbı) ama pozisyon
        açık. Hedef 0,98 kalan çiftlere olduğu gibi dağıtılsaydı brüt > 1 → nakit 0 → rollover
        K-095 ile koşuyu durdururdu (ölçüldü: CADCHF 2024-18). FX kıyası takılı payı düşer."""
        n, hafta1 = 238, 118
        a = _sentetik("AAAUSD", n, 1.10)
        b = _sentetik("BBBUSD", n, 1.30)
        for k in ("open", "high", "low", "close", "bid_open", "ask_open"):
            b[k] = b[k].copy()
            b[k][hafta1:] = np.nan
        b["quality_status"] = b["quality_status"].copy()
        b["quality_status"][hafta1:] = LISTELENMEDI
        uyelik_b = np.ones(n, dtype=bool)
        uyelik_b[hafta1:] = False
        strateji = FxEvrenEsitAgirlik(yeniden_dengele_bar=24, azami_agirlik=0.6)
        g = evren_gorunum_kur(
            "1h",
            {"AAAUSD": a, "BBBUSD": b},
            {"AAAUSD": np.ones(n, dtype=bool), "BBBUSD": uyelik_b},
            strateji,
        )
        m = MaliyetModeli(fee_taker_bps=0.26, slippage_bps=1.0)
        fin = fin_mod.FinansmanModeli(
            uzun_gunluk_bps=1.0, kaynak=KAYNAK_2024
        )  # K-101: aralıksız model koşamaz
        sonuc = CokluBacktest(
            strateji,
            m,
            takvim=TFX,
            maliyetler={s: SembolMaliyeti("fxcm-fx", m) for s in ("AAAUSD", "BBBUSD")},
            finansmanlar={
                s: SembolFinansmani(f"fxcm-{s.lower()}", fin) for s in ("AAAUSD", "BBBUSD")
            },
        ).calistir(g)
        # Koşu durmadı; B kapanamadı (barı yok); A hedefi 0,98 − B payı → brüt ≈ 0,98.
        turlar = {i.sembol: i for i in sonuc.islemler}
        assert not turlar["BBBUSD"].kapali and sonuc.atlanan["bayat_degerleme"] == n - hafta1
        assert float(sonuc.maruziyet[hafta1 + 30 :].max()) <= 0.985
        assert sonuc.metrikler.toplam_finansman > 0

    def test_kripto_kiyasi_ayarlari_sabit(self):
        k = EvrenEsitAgirlik()
        assert k._ayarlar_icin(None) is k._ayarlar  # kanca kimlik: Faz 10 davranışı


# ------------------------------------------------------------------ sq


class TestCli:
    def test_sq_fx_kiyasi_kosar(self):
        from scryne_quant.cli.main import app

        r = CliRunner().invoke(
            app,
            [
                "evren",
                "backtest",
                str(TABLO),
                "--fx-depo",
                str(FIXTURE),
                "--yazma",
                "--json",
                "--strateji",
                "fx_evren_esit_agirlik",
                "--azami-enstruman",
                "21",
                "--yeniden-dengele",
                "120",
            ],
        )
        assert r.exit_code == 0, r.output
        govde = json.loads(r.output)
        assert govde["akis"]["islenen_sinyal"] >= 9 and govde["metrikler"]["toplam_finansman"] > 0
        assert govde["evren"]["takvim"]["id"] == TAKVIM_FX_5X24
