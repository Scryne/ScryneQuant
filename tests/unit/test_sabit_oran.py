"""Sabit oranlı yatırım (K-132): kural, bant davranışı, risk profili eşlemesi ve profil bekçisi.

Ölçülenler:

1. Pozisyon yokken hedefe alım; bant içinde işlem yok; bant dışında hedefe dönüş (alım/satım).
2. Motorla uçtan uca: yeniden dengeleme yalnız bant aşılınca; maruziyet bant civarında kalır.
3. Risk profili stratejinin kodundan değil config'deki eşlemeden gelir; eşlenmemiş strateji genel
   profili kullanır; profil dosyası yoksa hata (varsayılana düşülmez).
4. Bekçi: yatırım profili genel profilden **yalnız** `azami_maruziyet` ve `islem_basina_risk`te
   ayrılır. Başka bir limitin sessizce gevşetilmesi bu testi kırar (K-050: izni artıran
   değişiklik K ister).
5. Risk motoru yatırım profiliyle %50 hedefi onaylar, genel profille 0,30'a (ya da altına) indirir.
6. Canlı kapının risk_config kanıtı kullanılacak profile bağlıdır.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scryne_quant.backtest.motor import Backtest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.risk import limitler as limit_mod
from scryne_quant.risk.motor import RiskMotoru
from scryne_quant.strategy.kutuphane import YATIRIM, coz
from scryne_quant.strategy.kutuphane.sabit_oran import SabitOran
from scryne_quant.strategy.sinyal import Yon
from tests.conftest import bar_uret

KOK = Path(__file__).resolve().parents[2]
MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)


class _Poz:
    def __init__(self, exposure: float) -> None:
        self.exposure = exposure
        self.acik = exposure > 0


class _Ctx:
    sembol = "BTCUSDT"
    zaman = 1_700_000_000_000

    def __init__(self, exposure: float) -> None:
        self.pozisyon = _Poz(exposure)


@pytest.mark.parametrize(("mevcut", "yon"), [
    (0.0, Yon.BUY), (0.44, Yon.BUY), (0.45, None), (0.50, None), (0.55, None), (0.56, Yon.SELL),
])
def test_bant_kurali(mevcut, yon):
    s = SabitOran().on_bar(_Ctx(mevcut))
    if yon is None:
        assert s is None
    else:
        assert s.side is yon and s.target_exposure == 0.5


@pytest.mark.parametrize("p", [{"hedef": 0.0}, {"hedef": 1.2}, {"bant": 0.0},
                               {"hedef": 0.5, "bant": 0.5}, {"hedef": 0.9, "bant": 0.2}])
def test_parametre_dogrulama(p):
    with pytest.raises(ValueError):
        SabitOran(**p)


def test_kayit_ve_varsayilanlar():
    assert coz("sabit_oran") is SabitOran and "sabit_oran" in YATIRIM
    assert SabitOran().parametreler == {"hedef": 0.5, "bant": 0.05}
    assert SabitOran().isinma_bar() == 0


def _yol(n: int, getiri: float, tohum: int = 1) -> dict[str, np.ndarray]:
    d = {a: np.array(x, copy=True) for a, x in bar_dizileri(bar_uret(n=n, tohum=tohum)).items()}
    rng = np.random.default_rng(tohum)
    close = 30_000.0 * np.exp(np.cumsum(rng.normal(getiri, 0.004, n)))
    acilis = np.concatenate([[close[0]], close[:-1]])
    d["open"], d["close"] = acilis, close
    d["high"], d["low"] = np.maximum(acilis, close) * 1.001, np.minimum(acilis, close) * 0.999
    return d


@pytest.mark.parametrize("egilim", [0.0015, -0.0015])
def test_motorla_yeniden_dengeleme_bant_asilinca(egilim):
    """Güçlü eğilimde maruziyet banda çarpar ve hedefe döner; hiçbir bar sonunda
    [0,40, 0,60] dışına taşmaz (bant ± bir barlık hareket payı)."""
    d = _yol(800, egilim)
    s = Backtest(SabitOran(), MALIYET, baslangic_sermaye=10_000.0).calistir("BTCUSDT", "1h", d)
    maruz = np.asarray(s.maruziyet)[5:]
    # Pozisyon hiç kapanmaz (islem_sayisi kapanan işlemi sayar); dengelemeler sinyal olarak görünür.
    assert maruz.min() > 0.40 and maruz.max() < 0.60
    assert s.uretilen_sinyal >= 3  # ilk alım + en az iki dengeleme


def test_yatay_piyasada_ilk_alimdan_sonra_islem_yok():
    d = _yol(400, 0.0, tohum=3)
    d["close"] = np.full(400, 30_000.0)
    d["open"], d["high"], d["low"] = d["close"].copy(), d["close"] * 1.0001, d["close"] * 0.9999
    s = Backtest(SabitOran(), MALIYET, baslangic_sermaye=10_000.0).calistir("BTCUSDT", "1h", d)
    assert s.uretilen_sinyal == 1


# ------------------------------------------------------------------ risk profili


def test_profil_eslemesi_configden():
    assert limit_mod.profil_yolu("sabit_oran", KOK) == KOK / "config/risk_yatirim.json"
    assert limit_mod.profil_yolu("sma_kesisim", KOK) == KOK / "config/risk.json"
    assert limit_mod.profil_yolu(None, KOK) == KOK / "config/risk.json"


def test_profil_dosyasi_yoksa_hata(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/risk_profilleri.json").write_text(
        json.dumps({"strateji_profilleri": {"x": "config/yok.json"}}), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        limit_mod.strateji_icin_yukle("x", tmp_path)


def test_bekci_yatirim_profili_yalniz_iki_alanda_farkli():
    genel = json.loads((KOK / "config/risk.json").read_text(encoding="utf-8"))
    yat = json.loads((KOK / "config/risk_yatirim.json").read_text(encoding="utf-8"))
    farkli = {a for a in set(genel) | set(yat) if a != "gerekceler" and genel.get(a) != yat.get(a)}
    assert farkli == {"azami_maruziyet", "islem_basina_risk"}
    assert (yat["azami_maruziyet"], yat["islem_basina_risk"]) == (0.5, 0.05)
    g_farkli = {a for a in genel["gerekceler"] if genel["gerekceler"][a] != yat["gerekceler"][a]}
    assert g_farkli == {"azami_maruziyet", "islem_basina_risk"}
    for a in g_farkli:
        assert "K-132" in yat["gerekceler"][a]["metin"]
    tablo = json.loads((KOK / "config/risk_profilleri.json").read_text(encoding="utf-8"))
    assert tablo["strateji_profilleri"] == {"sabit_oran": "config/risk_yatirim.json"}


def _olcum(atr_oran: float):
    from scryne_quant.risk.motor import PiyasaOlcumu

    fiyat = 30_000.0
    return PiyasaOlcumu(bar_ms=1_700_000_000_000, fiyat=fiyat, atr=atr_oran * fiyat,
                        ozkaynak=100.0, mevcut_maruziyet=0.0)


@pytest.mark.parametrize("atr", [0.004, 0.008, 0.015])
def test_risk_motoru_yatirim_profiliyle_hedefi_onaylar_genelle_kisar(atr):
    from scryne_quant.strategy.sinyal import Sinyal

    sinyal = Sinyal(symbol="BTCUSDT", side=Yon.BUY, target_exposure=0.5, confidence=1.0,
                    reason="SABIT_ORAN_ALT_BANT", timestamp=1_700_000_000_000)
    yat = RiskMotoru(limit_mod.strateji_icin_yukle("sabit_oran", KOK), "1h", mod="backtest")
    genel = RiskMotoru(limit_mod.yukle(KOK / "config/risk.json"), "1h", mod="backtest")
    k_yat, k_gen = yat.degerlendir(sinyal, _olcum(atr)), genel.degerlendir(sinyal, _olcum(atr))
    assert getattr(k_yat, "onayli_maruziyet", None) == pytest.approx(0.5), k_yat
    assert getattr(k_gen, "onayli_maruziyet", 0.0) <= 0.30 + 1e-12


def test_canli_kapi_risk_kaniti_profile_bagli():
    from scryne_quant.execution.canli_kapi import KapiBaglami, risk_config_kontrolu

    a = risk_config_kontrolu(KapiBaglami(kok=KOK, strateji="sabit_oran"))
    b = risk_config_kontrolu(KapiBaglami(kok=KOK, strateji="sma_kesisim"))
    assert a.gecti and b.gecti and a.kanit != b.kanit
    assert "risk_yatirim.json" in a.ayrinti and "risk.json" in b.ayrinti
