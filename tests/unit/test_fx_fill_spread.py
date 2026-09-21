"""R4 Paket 2 (K-094): bid/ask fill + spread bileşeni + kayda seanslı takvim; 24x7 yolu bit-aynı.

K-057 kalıbı: (1) **statik** — yeni parametre/alanların hepsi varsayılanıyla "yok" demek
(`kotasyon=None`, `spread=None`, `takvim=None`), tek fiyatlı kaydın sözlüğünde yeni anahtar yok;
(2) **referans** — kripto senaryosu `takvim=None` ve `takvim("24x7")` ile tam kayıt düzeyinde
bit-aynı, `(mid, mid)` kotasyonu tek fiyat yoluyla sayı sayıya aynı; mevcut referans fixture
testleri (`test_backtest_referans`, `test_coklu_referans`) dokunulmadan geçiyor; (3) **FX**:
elle doğrulanmış bid/ask fixture'ında alış `ask × (1+s)`, satış `bid × (1−s)`; spread ve
slippage bileşenleri `Decimal` referansla ayrı ayrı; seanslı takvim kayda `{id, icerik_hash}`
ile deterministik giriyor ve `config_hash`i değiştiriyor.
"""

from __future__ import annotations

import inspect
from decimal import Decimal, getcontext

import numpy as np
import pytest

from scryne_quant.backtest.coklu_motor import CokluBacktest, CokluBacktestHatasi
from scryne_quant.backtest.fill import Emir, IslemYonu, emir_hazirla_genel, emirleri_hazirla
from scryne_quant.backtest.metrikler import Islem, Metrikler, hesapla
from scryne_quant.backtest.sonuc import Sonuc
from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.data.takvim import TAKVIM_24X7, TAKVIM_FX_5X24, takvim
from scryne_quant.strategy.kosu import evren_gorunum_kur
from scryne_quant.strategy.sinyal import Sinyal, Yon
from tests.conftest import PlanliHedef
from tests.unit.test_maliyet_katalogu import SEMBOLLER, SENARYO, _bar_dizileri

getcontext().prec = 50

T24 = takvim(TAKVIM_24X7)
TFX = takvim(TAKVIM_FX_5X24)
SAAT_MS = 3_600_000
#: 2024-01-08 Pazartesi 00:00 UTC — fx-5x24 seansının içi (Pazar 22:00 UTC açılışından sonra).
PAZARTESI_MS = 1_704_672_000_000
#: float64 ile Decimal arasındaki kaçınılmaz fark (Faz 3 / Faz 10 ile aynı sayı).
TOLERANS = 1e-12

MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
SIFIR_KAYMA = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=0.0)

#: Elle yazılmış bid/ask fixture'ı (EURUSD, 6 bar). `open` = orta fiyat; spread bar bar farklı
#: ki "hangi barın kotasyonu" sorusu sayıyla cevaplansın (fill barı: `t+1`).
BID_OPEN = (1.0800, 1.0810, 1.0820, 1.0830, 1.0790, 1.0800)
ASK_OPEN = (1.0802, 1.0813, 1.0824, 1.0832, 1.0794, 1.0803)
#: bar 1'de %50 al (bar 2 açılışı ask'ten dolar), bar 3'te düze in (bar 4 açılışı bid'den).
HEDEFLER = {1: {"EURUSD": 0.5}, 3: {"EURUSD": 0.0}}


def _fx_dizileri(*, kotasyon: bool = True, ayni: bool = False) -> dict[str, np.ndarray]:
    n = len(BID_OPEN)
    bid = np.array(BID_OPEN, dtype="float64")
    ask = np.array(ASK_OPEN, dtype="float64")
    mid = (bid + ask) / 2.0
    if ayni:  # spread sıfır: bid = ask = mid
        bid = ask = mid
    diziler: dict[str, np.ndarray] = {
        "open_time": PAZARTESI_MS + SAAT_MS * np.arange(n, dtype="int64"),
        "open": mid,
        "high": mid + 0.001,
        "low": mid - 0.001,
        "close": mid,
        "volume": np.full(n, np.nan),
        "quote_volume": np.full(n, np.nan),
        "trades": np.zeros(n, dtype="int64"),
        "quality_status": np.array([str(KaliteDurumu.OK)] * n, dtype=object),
    }
    if kotasyon:
        diziler["bid_open"] = bid
        diziler["ask_open"] = ask
    return diziler


def _fx_kosu(
    maliyet: MaliyetModeli = MALIYET, *, kotasyon: bool = True, ayni: bool = False, takvim=None
) -> Sonuc:
    strateji = PlanliHedef(HEDEFLER)
    diziler = {"EURUSD": _fx_dizileri(kotasyon=kotasyon, ayni=ayni)}
    gorunum = evren_gorunum_kur(
        "1h", diziler, {"EURUSD": np.ones(len(BID_OPEN), dtype=bool)}, strateji
    )
    return CokluBacktest(strateji, maliyet, takvim=takvim).calistir(
        gorunum, veri_sha256={"EURUSD": "f" * 64}
    )


def _kripto_kosu(takvim=None) -> Sonuc:
    strateji = PlanliHedef(
        {h["bar"]: {s: float(a) for s, a in h["agirliklar"].items()} for h in SENARYO["hedefler"]}
    )
    diziler = {s: _bar_dizileri(SENARYO["barlar"][s]) for s in SEMBOLLER}
    n = len(diziler[SEMBOLLER[0]]["open_time"])
    gorunum = evren_gorunum_kur(
        "1h", diziler, {s: np.ones(n, dtype=bool) for s in SEMBOLLER}, strateji
    )
    return CokluBacktest(strateji, MALIYET, takvim=takvim).calistir(gorunum)


def _kayit(sonuc: Sonuc) -> dict:
    """Tam kayıt, git/ortam alanları dışında (onlar kimliğe girmez, K-009)."""
    k = sonuc.sozluk(islem_listesi=True, egri=True)
    k["kimlik"] = {a: d for a, d in k["kimlik"].items() if a not in ("commit", "dirty", "ortam")}
    return k


# ------------------------------------------------------------------ statik


class TestStatik:
    def test_yeni_parametreler_varsayilan_yok(self):
        assert inspect.signature(emir_hazirla_genel).parameters["kotasyon"].default is None
        assert inspect.signature(emirleri_hazirla).parameters["kotasyonlar"].default is None
        assert inspect.signature(hesapla).parameters["spread_bileseni"].default is False
        assert Emir.__dataclass_fields__["kotasyon_fiyat"].default is None
        assert Islem.__dataclass_fields__["spread"].default is None
        assert Metrikler.__dataclass_fields__["toplam_spread"].default is None
        assert Sonuc.__dataclass_fields__["takvim"].default is None

    def test_tek_fiyatli_emirde_spread_sifir_slippage_eski_ifade(self):
        e = Emir(
            IslemYonu.AL, miktar=2.0, fiyat=100.05, referans_fiyat=100.0, komisyon=0.2, zaman_ms=0
        )
        assert e.kotasyon_fiyat is None and e.spread_maliyeti == 0.0
        assert e.slippage_maliyeti == abs(100.05 - 100.0) * 2.0

    def test_islem_sozlugunde_spread_yalniz_varsa(self):
        assert "spread" not in Islem(acilis_ms=0).sozluk()
        assert Islem(acilis_ms=0, spread=0.0).sozluk()["spread"] == 0.0

    def test_kripto_kaydinda_yeni_anahtar_yok(self):
        k = _kayit(_kripto_kosu())
        assert "toplam_spread" not in k["metrikler"] and "takvim" not in k["config"]
        assert all("spread" not in i for i in k["islemler"])


# ------------------------------------------------------------------ referans: 24x7 ≡ None


class TestBitAyniKripto:
    def test_none_ve_24x7_tam_kayit_bit_ayni(self):
        eski, yeni = _kripto_kosu(None), _kripto_kosu(T24)
        assert eski.takvim is None and yeni.takvim is None
        assert eski.sonuc_hash == yeni.sonuc_hash and eski.config_hash == yeni.config_hash
        assert _kayit(eski) == _kayit(yeni)

    def test_sifir_spread_kotasyonu_tek_fiyat_yoluyla_ayni_sayilar(self):
        """`(mid, mid)` kotasyonu: fill fiyatı, miktar, komisyon, slippage tek fiyat yoluyla
        birebir; tek fark spread anahtarlarının **0 ile var** olması (ölçülmüş sıfır)."""
        tek, ayni = _fx_kosu(kotasyon=False), _fx_kosu(ayni=True)
        assert ayni.metrikler.toplam_spread == 0.0 and tek.metrikler.toplam_spread is None
        assert tek.ozkaynak.tolist() == ayni.ozkaynak.tolist()
        for a, b in zip(tek.islemler, ayni.islemler, strict=True):
            sa, sb = a.sozluk(), b.sozluk()
            assert sb.pop("spread") == 0.0 and "spread" not in sa
            assert sa == sb
        ma, mb = tek.metrikler.sozluk(), ayni.metrikler.sozluk()
        mb.pop("toplam_spread")
        assert ma == mb


# ------------------------------------------------------------------ FX: bid/ask fill + spread


def _referans(maliyet: MaliyetModeli) -> dict[str, Decimal]:
    """Motordan bağımsız `Decimal` referans: iki fill, `emir_hazirla_genel` sözleşmesiyle."""
    D = Decimal
    fee = D(str(maliyet.fee_taker_bps)) / D(10_000)
    s = D(str(maliyet.slippage_bps)) / D(10_000)
    # Fiyatlar float64'ün **tam** Decimal karşılığı (motor da o sayıyı görüyor); orta fiyat
    # motorun `(bid + ask) / 2` float'ıyla aynı (toplam ve yarılama float'ta tam).
    mid2 = (D(BID_OPEN[2]) + D(ASK_OPEN[2])) / 2
    mid4 = (D(BID_OPEN[4]) + D(ASK_OPEN[4])) / 2
    nakit = D(10_000)
    # Alış (bar 2): hedef %50, özkaynak = nakit (pozisyon yok).
    fark = nakit * D("0.5")
    notional_al = min(fark, nakit / (1 + fee))
    fiyat_al = D(ASK_OPEN[2]) * (1 + s)
    miktar = notional_al / fiyat_al
    komisyon_al = notional_al * fee
    spread_al = (D(ASK_OPEN[2]) - mid2) * miktar
    slippage_al = (fiyat_al - D(ASK_OPEN[2])) * miktar
    nakit -= notional_al + komisyon_al
    # Satış (bar 4): hedef 0 → `-fark = miktar × mid4`, tavan `miktar × fiyat_sat` (< mid4).
    fiyat_sat = D(BID_OPEN[4]) * (1 - s)
    notional_sat = min(miktar * mid4, miktar * fiyat_sat)
    komisyon_sat = notional_sat * fee
    spread_sat = (mid4 - D(BID_OPEN[4])) * (notional_sat / fiyat_sat)
    slippage_sat = (D(BID_OPEN[4]) - fiyat_sat) * (notional_sat / fiyat_sat)
    bitis = nakit + notional_sat - komisyon_sat
    return {
        "fiyat_al": fiyat_al,
        "fiyat_sat": fiyat_sat,
        "miktar": miktar,
        "komisyon": komisyon_al + komisyon_sat,
        "spread": spread_al + spread_sat,
        "slippage": slippage_al + slippage_sat,
        "bitis": bitis,
    }


def _sinyal() -> Sinyal:
    return Sinyal(
        symbol="EURUSD",
        side=Yon.BUY,
        target_exposure=1.0,
        confidence=1.0,
        reason="TEST",
        timestamp=PAZARTESI_MS,
    )


def _yakin(a: float, b: Decimal) -> bool:
    return abs(Decimal(a) - b) <= Decimal(TOLERANS) * max(abs(b), Decimal(1))


class TestFxBidAsk:
    @pytest.mark.parametrize("maliyet", [MALIYET, SIFIR_KAYMA], ids=["kaymali", "kaymasiz"])
    def test_alis_ask_satis_bid_referansla_birebir(self, maliyet):
        sonuc = _fx_kosu(maliyet)
        ref = _referans(maliyet)
        [tur] = sonuc.islemler
        assert tur.fill_sayisi == 2 and tur.kapali
        assert _yakin(tur.giris_notional / tur.giris_miktar, ref["fiyat_al"])
        assert _yakin(tur.cikis_notional / tur.cikis_miktar, ref["fiyat_sat"])
        assert _yakin(tur.giris_miktar, ref["miktar"])
        assert _yakin(tur.komisyon, ref["komisyon"])
        assert _yakin(tur.spread, ref["spread"])
        assert _yakin(tur.slippage, ref["slippage"])
        assert _yakin(float(sonuc.ozkaynak[-1]), ref["bitis"])
        assert _yakin(sonuc.metrikler.toplam_spread, ref["spread"])
        assert _yakin(sonuc.metrikler.toplam_slippage, ref["slippage"])

    def test_k007_aleyhte_korunuyor(self):
        """Alış fiyatı ask'in üstünde (≥), satış bid'in altında (≤); ikisi de orta fiyattan kötü."""
        sonuc = _fx_kosu(MALIYET)
        [tur] = sonuc.islemler
        al, sat = tur.giris_notional / tur.giris_miktar, tur.cikis_notional / tur.cikis_miktar
        mid2 = (BID_OPEN[2] + ASK_OPEN[2]) / 2
        mid4 = (BID_OPEN[4] + ASK_OPEN[4]) / 2
        assert al > ASK_OPEN[2] > mid2 and sat < BID_OPEN[4] < mid4
        k = _fx_kosu(SIFIR_KAYMA).islemler[0]
        assert k.giris_notional / k.giris_miktar == pytest.approx(ASK_OPEN[2], abs=1e-15)
        assert k.cikis_notional / k.cikis_miktar == pytest.approx(BID_OPEN[4], abs=1e-15)
        kaymasiz = k
        assert kaymasiz.slippage == 0.0 and kaymasiz.spread > 0.0

    def test_spread_ve_slippage_ayri_bilesenler(self):
        """Kaymayı sıfırlamak spread'i değiştirmez; spread'i sıfırlamak kaymayı değiştirmez."""
        kaymali, kaymasiz = _fx_kosu(MALIYET).islemler[0], _fx_kosu(SIFIR_KAYMA).islemler[0]
        # Aynı miktar alınmaz (fill fiyatı farklı) — bileşenleri **birim başına** kıyasla.
        assert kaymali.spread / kaymali.giris_miktar == pytest.approx(
            kaymasiz.spread / kaymasiz.giris_miktar, rel=1e-3
        )
        sifir_spread = _fx_kosu(MALIYET, ayni=True).islemler[0]
        assert sifir_spread.spread == 0.0 and sifir_spread.slippage > 0.0

    def test_emir_duzeyinde_kotasyon(self):
        e = emir_hazirla_genel(
            _sinyal(),
            acilis=1.0,
            zaman_ms=0,
            maliyet=SIFIR_KAYMA,
            nakit=1000.0,
            elde_miktar=0.0,
            ozkaynak=1000.0,
            kotasyon=(0.999, 1.001),
        )
        assert isinstance(e, Emir) and e.yon is IslemYonu.AL
        assert e.fiyat == 1.001 and e.kotasyon_fiyat == 1.001 and e.referans_fiyat == 1.0
        assert e.spread_maliyeti == pytest.approx(0.001 * e.miktar)
        assert e.slippage_maliyeti == 0.0

    @pytest.mark.parametrize("kotasyon", [(1.001, 0.999), (1.0005, 1.001), (0.0, 1.0)])
    def test_tutarsiz_kotasyon_reddedilir(self, kotasyon):
        with pytest.raises(ValueError, match="kotasyon tutarsız"):
            emir_hazirla_genel(
                _sinyal(),
                acilis=1.0,
                zaman_ms=0,
                maliyet=MALIYET,
                nakit=1000.0,
                elde_miktar=0.0,
                ozkaynak=1000.0,
                kotasyon=kotasyon,
            )

    def test_yalniz_bir_kotasyon_sutunu_hata(self):
        strateji = PlanliHedef(HEDEFLER)
        diziler = _fx_dizileri()
        del diziler["ask_open"]
        gorunum = evren_gorunum_kur(
            "1h", {"EURUSD": diziler}, {"EURUSD": np.ones(len(BID_OPEN), dtype=bool)}, strateji
        )
        with pytest.raises(CokluBacktestHatasi, match="yalnız biri"):
            CokluBacktest(strateji, MALIYET).calistir(gorunum)

    def test_fx_kaydi_deterministik(self):
        a, b = _fx_kosu(MALIYET, takvim=TFX), _fx_kosu(MALIYET, takvim=TFX)
        assert a.sonuc_hash == b.sonuc_hash and a.config_hash == b.config_hash
        assert _kayit(a) == _kayit(b)


# ------------------------------------------------------------------ kayda takvim bloğu


class TestTakvimKaydi:
    def test_seansli_takvim_kayda_giriyor(self):
        sonuc = _fx_kosu(MALIYET, takvim=TFX)
        blok = {"id": TAKVIM_FX_5X24, "icerik_hash": TFX.icerik_hash}
        assert sonuc.takvim == blok
        assert sonuc.sozluk()["config"]["takvim"] == blok
        assert (
            blok["icerik_hash"]
            == nesne_hash(TFX.sozluk())
            == ("16bafe1946d531946d02e63c35288ff4298647e68db70fe26d4605b171f4bdbf")
        )

    def test_24x7_ve_none_kayda_girmiyor(self):
        for t in (None, T24):
            sonuc = _fx_kosu(MALIYET, takvim=t)
            assert sonuc.takvim is None and "takvim" not in sonuc.sozluk()["config"]

    def test_takvim_config_hashi_degistiriyor_sonucu_deterministik(self):
        yok, fx, fx2 = (_fx_kosu(MALIYET, takvim=t) for t in (None, TFX, TFX))
        assert fx.config_hash == fx2.config_hash and fx.config_hash != yok.config_hash
        # Takvim bloğu `sonuc_hash`e değil `config_hash`e girer: çıktı (metrikler) yıllıklandırma
        # dışında aynı; takvim değişince Sharpe ölçeği değişir, bu beklenen ve K-093'te ölçülü.
        assert fx.metrikler.islem_sayisi == yok.metrikler.islem_sayisi
        assert fx.metrikler.toplam_spread == yok.metrikler.toplam_spread
