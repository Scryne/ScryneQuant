"""R4 Paket 3 (K-095): FX finansman/rollover bacağı maliyet hattında; finansmansız yol bit-aynı.

K-057 kalıbı: (1) **statik** — `finansmanlar=None`, `Islem.finansman=None`, `toplam_finansman`,
`Sonuc.finansmanlar` varsayılanları "yok"; kripto kaydında yeni anahtar yok; (2) **referans** —
aynı FX fixture'ı finansmanlı/finansmansız: özkaynak eğrisi tam olarak birikimli bedel kadar
ayrışıyor, ilk turun `net_pnl`i tam bedel kadar düşük (`Decimal` referans ≤ 1e-12); (3) **FX**:
rollover anları takvimden (Pzt-Cum NY 17:00, DST'de UTC kayar, Çarşamba 3 gün, hafta sonu 0),
rollover geçmeyen kısa tur **0.0** (ölçülmüş sıfır), fail-closed: takvimsiz/sürekli takvim, eksik
sembol, eksik/bozuk dosya, yetmeyen nakit.
"""

from __future__ import annotations

import inspect
import json
from decimal import Decimal, getcontext

import numpy as np
import pandas as pd
import pytest

from scryne_quant.backtest.coklu_motor import CokluBacktest, CokluBacktestHatasi
from scryne_quant.backtest.metrikler import Islem, Metrikler, hesapla
from scryne_quant.backtest.sonuc import Sonuc
from scryne_quant.common import finansman as fin_mod
from scryne_quant.common.finansman import (
    FinansmanHatasi,
    FinansmanKatalogu,
    FinansmanKaynagi,
    FinansmanModeli,
    SembolFinansmani,
)
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.data import kimlik as kimlik_mod
from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.data.takvim import TAKVIM_24X7, TAKVIM_FX_5X24, TakvimHatasi, takvim
from scryne_quant.research import evren_kosu
from scryne_quant.strategy.kosu import evren_gorunum_kur
from tests.conftest import PlanliHedef
from tests.unit.test_fx_fill_spread import _kayit, _kripto_kosu

getcontext().prec = 50

T24 = takvim(TAKVIM_24X7)
TFX = takvim(TAKVIM_FX_5X24)
SAAT = 3_600_000
TOLERANS = 1e-12
MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
KAYNAK = FinansmanKaynagi(saglayici="test", tarih="2026-09-21", gerekce="fixture")
MODEL = FinansmanModeli(uzun_gunluk_bps=2.5, kaynak=KAYNAK)


def _ms(metin: str) -> int:
    return int(pd.Timestamp(metin, tz="UTC").value // 1_000_000)


#: Pzt 2024-01-08 00:00 → Cum 2024-01-12 22:00 UTC, saatlik (seans içi). Rollover'lar 22:00 UTC
#: (NY 17:00, kış) → bar `21:00`ın aralığına düşer: Pzt/Sal/Per/Cum 1 gün, Çar 3 gün.
ZAMANLAR = np.arange(_ms("2024-01-08 00:00"), _ms("2024-01-12 23:00"), SAAT, dtype="int64")


def _bar(z: int) -> int:
    return int(np.searchsorted(ZAMANLAR, z))


#: Tur 1: bar 1'de %50 al (bar 2 açılışı), Per 09:00'da düze (Per 10:00 açılışı) → Pzt, Sal,
#: Çar rollover'ları (1+1+3 = 5 gün). Tur 2: Per 12:00 al (13:00), Per 14:00 düze (15:00) →
#: rollover yok.
HEDEFLER = {
    1: {"EURUSD": 0.5},
    _bar(_ms("2024-01-11 09:00")): {"EURUSD": 0.0},
    _bar(_ms("2024-01-11 12:00")): {"EURUSD": 0.5},
    _bar(_ms("2024-01-11 14:00")): {"EURUSD": 0.0},
}
ROLLOVER_BARLARI = {
    _bar(_ms("2024-01-08 21:00")): 1,
    _bar(_ms("2024-01-09 21:00")): 1,
    _bar(_ms("2024-01-10 21:00")): 3,
    _bar(_ms("2024-01-11 21:00")): 1,
    _bar(_ms("2024-01-12 21:00")): 1,
}


def _fx_dizileri() -> dict[str, np.ndarray]:
    n = ZAMANLAR.size
    # Deterministik, hafif eğimli seri; bid/ask 2 pip spread, orta = open.
    mid = 1.08 + 0.0001 * np.sin(np.arange(n) / 3.0) + 0.00002 * np.arange(n)
    return {
        "open_time": ZAMANLAR.copy(),
        "open": mid,
        "high": mid + 0.0005,
        "low": mid - 0.0005,
        "close": mid + 0.00003,
        "volume": np.full(n, np.nan),
        "quote_volume": np.full(n, np.nan),
        "trades": np.zeros(n, dtype="int64"),
        "quality_status": np.array([str(KaliteDurumu.OK)] * n, dtype=object),
        "bid_open": mid - 0.0001,
        "ask_open": mid + 0.0001,
    }


def _kosu(finansmanlar=None, *, takvim=TFX, hedefler=HEDEFLER, model=MODEL) -> Sonuc:
    strateji = PlanliHedef(hedefler)
    gorunum = evren_gorunum_kur(
        "1h",
        {"EURUSD": _fx_dizileri()},
        {"EURUSD": np.ones(ZAMANLAR.size, dtype=bool)},
        strateji,
    )
    if finansmanlar == "var":
        finansmanlar = {"EURUSD": SembolFinansmani("test-fx", model)}
    return CokluBacktest(strateji, MALIYET, takvim=takvim, finansmanlar=finansmanlar).calistir(
        gorunum, veri_sha256={"EURUSD": "e" * 64}
    )


# ------------------------------------------------------------------ statik


class TestStatik:
    def test_varsayilanlar_yok(self):
        assert inspect.signature(CokluBacktest.__init__).parameters["finansmanlar"].default is None
        assert inspect.signature(hesapla).parameters["finansman_bileseni"].default is False
        assert Islem.__dataclass_fields__["finansman"].default is None
        assert Metrikler.__dataclass_fields__["toplam_finansman"].default is None
        assert Sonuc.__dataclass_fields__["finansmanlar"].default is None
        assert Sonuc.__dataclass_fields__["finansman_gecici"].default is None
        assert "finansman" not in Islem(acilis_ms=0).sozluk()

    def test_kripto_kaydinda_yeni_anahtar_yok(self):
        k = _kayit(_kripto_kosu())
        assert "toplam_finansman" not in k["metrikler"] and "finansmanlar" not in k["config"]
        assert all("finansman" not in i for i in k["islemler"])
        assert "gecici_finansman_modeli" not in k["promotion"]["engeller"]

    def test_fx_finansmansiz_kayitta_da_anahtar_yok(self):
        k = _kayit(_kosu(None))
        assert "toplam_finansman" not in k["metrikler"] and "finansmanlar" not in k["config"]


# ------------------------------------------------------------------ takvim: rollover anları


class TestRolloverAnlari:
    def test_hafta_ici_ny_17_dst_ile_kayar(self):
        kis = TFX.rollover_anlari(_ms("2024-01-07 00:00"), _ms("2024-01-14 00:00"))
        yaz = TFX.rollover_anlari(_ms("2024-07-07 00:00"), _ms("2024-07-14 00:00"))
        assert [str(pd.Timestamp(x, unit="ms", tz="UTC"))[:16] for x in kis] == [
            f"2024-01-{g:02d} 22:00" for g in (8, 9, 10, 11, 12)
        ]
        assert [str(pd.Timestamp(x, unit="ms", tz="UTC"))[:16] for x in yaz] == [
            f"2024-07-{g:02d} 21:00" for g in (8, 9, 10, 11, 12)
        ]

    def test_aralik_sol_acik_sag_kapali(self):
        r = _ms("2024-01-08 22:00")
        assert TFX.rollover_anlari(r, r + SAAT).size == 0
        assert TFX.rollover_anlari(r - SAAT, r).tolist() == [r]

    def test_bar_basina_gun_carsamba_uc_hafta_yedi(self):
        g = TFX.rollover_gunleri(ZAMANLAR, uclu_swap_gunu=2)
        assert {int(i): int(g[i]) for i in np.nonzero(g)[0]} == ROLLOVER_BARLARI
        assert int(g.sum()) == 7

    def test_hafta_sonu_bosluklu_izgarada_cuma_rollover_cuma_barina(self):
        z = np.concatenate(
            [
                np.arange(_ms("2024-01-12 18:00"), _ms("2024-01-12 22:00"), SAAT),
                np.arange(_ms("2024-01-14 22:00"), _ms("2024-01-15 02:00"), SAAT),
            ]
        )
        g = TFX.rollover_gunleri(z, 2)
        assert g.tolist() == [0, 0, 0, 1, 0, 0, 0, 0]

    def test_surekli_takvimde_rollover_tanimsiz(self):
        with pytest.raises(TakvimHatasi, match="rollover"):
            T24.rollover_anlari(0, SAAT)


# ------------------------------------------------------------------ referans: bedel


def _referans_bedel(yok: Sonuc) -> tuple[dict[int, Decimal], Decimal]:
    """Motordan bağımsız: tur 1'in miktarı × rollover barının kapanışı × bps × gün."""
    tur = yok.islemler[0]
    miktar = Decimal(tur.giris_miktar)
    kapanis = _fx_dizileri()["close"]
    bps = Decimal(str(MODEL.uzun_gunluk_bps)) / Decimal(10_000)
    bedeller = {
        b: miktar * Decimal(float(kapanis[b])) * bps * gun
        for b, gun in ROLLOVER_BARLARI.items()
        if b < _bar(_ms("2024-01-11 10:00"))  # tur 1 kapanmadan önceki rollover'lar
    }
    return bedeller, sum(bedeller.values(), Decimal(0))


def _yakin(a: float, b: Decimal) -> bool:
    return abs(Decimal(a) - b) <= Decimal(TOLERANS) * max(abs(b), Decimal(1))


class TestFxRollover:
    def test_bedel_referansla_birebir_ve_tek_kez(self):
        yok, var = _kosu(None), _kosu("var")
        bedeller, toplam = _referans_bedel(yok)
        assert len(bedeller) == 3 and toplam > 0
        t_yok, t_var = yok.islemler[0], var.islemler[0]
        # Tur 1 aynı miktarla açılır (bedel öncesi boyutlandırma) → farkı yalnız finansman.
        assert t_var.giris_miktar == t_yok.giris_miktar
        assert _yakin(t_var.finansman, toplam)
        assert _yakin(t_var.net_pnl, Decimal(t_yok.net_pnl) - toplam)
        assert t_var.komisyon == t_yok.komisyon and t_var.spread == t_yok.spread
        # Özkaynak eğrisi bar bar tam olarak birikimli bedel kadar düşük — tur 2 açılana kadar.
        birikim = Decimal(0)
        for i in range(_bar(_ms("2024-01-11 13:00"))):
            birikim += bedeller.get(i, Decimal(0))
            assert _yakin(float(var.ozkaynak[i]), Decimal(float(yok.ozkaynak[i])) - birikim)
        # Toplam: tur 1 + tur 2 (0.0) = tur 1; iki kez sayılmaz.
        assert var.metrikler.toplam_finansman == t_var.finansman + var.islemler[1].finansman
        assert _yakin(var.metrikler.toplam_finansman, toplam)

    def test_rollover_gecmeyen_kisa_tur_sifir(self):
        """Per 13:00 → 15:00 arası tur hiçbir rollover anını içermez: bedel **0.0**, anahtar var."""
        var = _kosu("var")
        [t1, t2] = var.islemler
        assert t1.finansman > 0.0 and t2.kapali
        assert t2.finansman == 0.0 and t2.sozluk()["finansman"] == 0.0
        # Tur 2'nin net_pnl'i yalnız fiyat/komisyon/spread'den: bedel düşülmedi.
        assert t2.net_pnl == pytest.approx(
            t2.cikis_notional - t2.giris_notional - t2.komisyon, rel=1e-9
        )

    def test_carsamba_uc_gun(self):
        bedeller, _ = _referans_bedel(_kosu(None))
        kapanis = _fx_dizileri()["close"]
        sal, car = (_bar(_ms(f"2024-01-{g:02d} 21:00")) for g in (9, 10))
        birim_sal = bedeller[sal] / Decimal(float(kapanis[sal]))
        birim_car = bedeller[car] / Decimal(float(kapanis[car]))
        assert birim_car == birim_sal * 3

    def test_sifir_bps_modeli_bedel_sifir_ama_olculmus(self):
        sifir = FinansmanModeli(uzun_gunluk_bps=0.0, kaynak=KAYNAK)
        var, yok = _kosu("var", model=sifir), _kosu(None)
        assert var.metrikler.toplam_finansman == 0.0
        assert var.ozkaynak.tolist() == yok.ozkaynak.tolist()
        assert [i.finansman for i in var.islemler] == [0.0, 0.0]

    def test_kayit_ve_config_hash(self):
        var, var2, yok = _kosu("var"), _kosu("var"), _kosu(None)
        blok = {"EURUSD": {"id": "test-fx", "govde": fin_mod.govde(MODEL)}}
        assert var.finansmanlar == blok and var.sozluk()["config"]["finansmanlar"] == blok
        assert var.config_hash == var2.config_hash != yok.config_hash
        assert var.sonuc_hash == var2.sonuc_hash
        assert var.takvim == {"id": TAKVIM_FX_5X24, "icerik_hash": TFX.icerik_hash}
        assert fin_mod.finansmanlar_govdeden(blok)["EURUSD"].model == MODEL
        assert "gecici_finansman_modeli" not in var.promotion_engelleri

    def test_gecici_model_promotion_engeli(self):
        gecici = FinansmanModeli(uzun_gunluk_bps=2.5)
        var = _kosu("var", model=gecici)
        assert var.finansman_gecici is True
        assert "gecici_finansman_modeli" in var.promotion_engelleri


# ------------------------------------------------------------------ fail closed


class TestFailClosed:
    def test_takvimsiz_ya_da_surekli_takvim_reddedilir(self):
        for t in (None, T24):
            with pytest.raises(CokluBacktestHatasi, match="seanslı takvim"):
                _kosu("var", takvim=t)

    def test_eksik_sembol_reddedilir(self):
        with pytest.raises(CokluBacktestHatasi, match="finansman modeli olmayan"):
            _kosu({"BASKA": SembolFinansmani("x", MODEL)})

    def test_nakit_yetmezse_kosu_durur(self):
        hedefler = {1: {"EURUSD": 1.0}}  # tüm nakit pozisyonda → rollover için nakit yok
        with pytest.raises(FinansmanHatasi, match="nakit yetersiz"):
            _kosu("var", hedefler=hedefler)

    def test_katalog_eksik_ve_bozuk_dosya(self, tmp_path):
        katalog = FinansmanKatalogu(tmp_path)
        with pytest.raises(FinansmanHatasi, match="dosya yok"):
            katalog.coz("yok")
        (tmp_path / "bozuk.json").write_text('{"uzun_gunluk_bps": -1}', encoding="utf-8")
        with pytest.raises(FinansmanHatasi, match="bozuk"):
            katalog.coz("bozuk")
        (tmp_path / "fazla.json").write_text(
            '{"uzun_gunluk_bps": 1, "kisa_gunluk_bps": 1}', encoding="utf-8"
        )
        with pytest.raises(FinansmanHatasi, match="bozuk"):
            katalog.coz("fazla")
        with pytest.raises(FinansmanHatasi, match="geçersiz"):
            katalog.coz("../x")
        (tmp_path / "iyi.json").write_text(json.dumps(MODEL.model_dump()), encoding="utf-8")
        assert katalog.coz("iyi") == MODEL and not katalog.coz("iyi").gecici

    def test_negatif_bedel_yok(self):
        with pytest.raises(FinansmanHatasi):
            MODEL.gun_bedeli(-1.0, 1)
        assert MODEL.gun_bedeli(10_000.0, 3) == 10_000.0 * 2.5e-4 * 3


# ------------------------------------------------------------------ Enstruman → katalog


def _enstruman(tip: str, fin_id: str | None) -> kimlik_mod.Enstruman:
    venue = kimlik_mod.VENUE_FXCM_FX if tip == "cfd" else kimlik_mod.VENUE_BINANCE_SPOT
    return kimlik_mod.Enstruman(
        kanonik_id=kimlik_mod.kanonik_kimlik(venue, tip, "EURUSD", "2024-01-08"),
        venue=venue,
        sembol="EURUSD",
        gecerli_baslangic_ms=_ms("2024-01-08 00:00"),
        gecerli_bitis_ms=_ms("2024-01-13 00:00"),
        bar_sayisi=1,
        kirilma_ile_basladi=False,
        asset_class="fx" if tip == "cfd" else "kripto",
        instrument_type=tip,
        takvim_id=TAKVIM_FX_5X24 if tip == "cfd" else TAKVIM_24X7,
        maliyet_modeli_id="fxcm-eurusd" if tip == "cfd" else "global",
        finansman_modeli_id=fin_id,
    )


class TestEnstrumanBaglama:
    def test_cfd_kimligi_katalogdan_cozulur_spot_none(self, tmp_path):
        (tmp_path / "fxcm-eurusd.json").write_text(json.dumps(MODEL.model_dump()), encoding="utf-8")
        katalog = FinansmanKatalogu(tmp_path)
        out = evren_kosu.enstruman_finansmanlari(
            katalog, {"EURUSD": [_enstruman("cfd", "fxcm-eurusd")]}
        )
        assert out == {"EURUSD": SembolFinansmani("fxcm-eurusd", MODEL)}
        assert (
            evren_kosu.enstruman_finansmanlari(katalog, {"BTCUSDT": [_enstruman("spot", None)]})
            is None
        )

    def test_cfd_kimligi_dosyasiz_hata(self, tmp_path):
        with pytest.raises(FinansmanHatasi, match="dosya yok"):
            evren_kosu.enstruman_finansmanlari(
                FinansmanKatalogu(tmp_path), {"EURUSD": [_enstruman("cfd", "fxcm-eurusd")]}
            )

    def test_cfd_kimliksiz_enstruman_zaten_kurulamaz(self):
        with pytest.raises(kimlik_mod.KimlikHatasi, match="finansman_modeli_id zorunlu"):
            _enstruman("cfd", None)
