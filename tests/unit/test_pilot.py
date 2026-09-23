"""Mikro canlı pilot. (K-115)

Ölçülen iddialar:
- Pilot tavanları kodda sabit (100 / 10 USDT) ve `config/kademe.json` bunları aşamaz.
- Pilot kademede live gate promotion/R8/shadow kanıtı istemez; yerine `pilot_siniri` ve
  `pilot_hesap_degeri` gelir. Geri kalan her kontrol (anahtar yetkisi, kill, testler,
  venue…) aynen durur. Pilot olmayan kademe hâlâ promotion ister.
- Hesap değeri tavanın dışındaysa (fazla para ya da eksik para) ya da ölçülemiyorsa kapı kapalı.
- `pilot` risk modu promotion istemez ama promotion kanıtı da üretemez (K-035 kalıbı).
- Execution hattı: özkaynak sermaye − azami kayıp altına inince SAFE_MODE; artıran emir yok,
  azaltan geçer; işaret kaldırılsa da her barda yeniden konur.
- Kurulum: pilot kademe yalnız `pilot` risk moduyla, hat mutlak kayıp tavanını taşır.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scryne_quant.exchange import yetki
from scryne_quant.exchange.canli import CANLI_HOST
from scryne_quant.exchange.kurallar import SembolKurallari
from scryne_quant.exchange.paper_adaptoru import PaperBorsa, PaperMaliyet
from scryne_quant.execution import canli_kapi
from scryne_quant.execution.canli_kapi import (
    PILOT_AZAMI_KAYIP_USDT,
    PILOT_AZAMI_SERMAYE_USDT,
    AgYoklamasi,
    KapiBaglami,
    hesap_degeri_hesapla,
    kapi_raporu,
    pilot_mu,
)
from scryne_quant.execution.hat import Engel, ExecutionHatti, GuvenlikLimitleri
from scryne_quant.execution.mod import CalismaModu
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.risk.audit import BellekDefteri
from scryne_quant.risk.motor import MODLAR
from scryne_quant.risk.niyet import onayla
from scryne_quant.risk.promotion import MOD_ESIGI, Asama, Kanit, PromotionHatasi
from scryne_quant.strategy.sinyal import Sinyal, Yon

REPO = Path(__file__).resolve().parents[2]


def _kademe(**pilot_alanlari) -> dict:
    pilot = {"kademe": 1, "ad": "pilot", "pilot": True, "sermaye_usdt": 100.0,
             "azami_kayip_usdt": 10.0, "strateji": "sma_kesisim", "sembol": "BTCUSDT",
             "onay": {"gerekli": True, "not": "test", "tarih": "t"}}
    pilot.update(pilot_alanlari)
    return {
        "risk_sermayesi_usdt": 100.0,
        "aktif_kademe": 1,
        "golge_olcutu": {"asgari_gun": 14, "asgari_golge": 20},
        "kademeler": [{"kademe": 0, "ad": "shadow", "sermaye_usdt": 0.0}, pilot],
        "kararlar": {
            "risk_sermayesi": {"durum": "kabul (K-115)"},
            "venue_statusu": {"durum": "kabul (K-115)"},
            "canli_modul_sinir": {"durum": "kabul (K-114)"},
            "kademe_artis_orani": {"durum": "DECISION REQUIRED"},
            "drift_ust_siniri_kurali": {"durum": "DECISION REQUIRED"},
        },
    }


@pytest.fixture
def kok(tmp_path):
    (tmp_path / "config").mkdir()
    for ad in ("r8_kriterler.json", "risk.json"):
        shutil.copy(REPO / "config" / ad, tmp_path / "config" / ad)
    return tmp_path


def _yaz(kok: Path, tablo: dict) -> None:
    (kok / "config/kademe.json").write_text(json.dumps(tablo), encoding="utf-8")


def _k(rapor: dict) -> dict:
    return {x["ad"]: x for x in rapor["kontroller"]}


def _hesap(toplam: float, olculemeyen: tuple[str, ...] = ()) -> AgYoklamasi:
    return AgYoklamasi(canli_hesap_degeri=lambda: {"toplam_usdt": toplam, "varliklar": {},
                                                   "olculemeyen": list(olculemeyen)})


# ============================================================ sabitler ve repo durumu


def test_pilot_tavanlari_kodda_sabit():
    # Yükseltmek bu testi, kodu ve yeni bir K'yı birlikte değiştirmeyi ister (K-050/2).
    assert PILOT_AZAMI_SERMAYE_USDT == 100.0
    assert PILOT_AZAMI_KAYIP_USDT == 10.0


def test_repo_kademe_dosyasi_pilot_ve_tavanlarin_icinde():
    tablo = json.loads((REPO / "config/kademe.json").read_text(encoding="utf-8"))
    assert pilot_mu(tablo)
    k = canli_kapi.aktif_kademe(tablo)
    assert k["sermaye_usdt"] <= PILOT_AZAMI_SERMAYE_USDT
    assert k["azami_kayip_usdt"] <= PILOT_AZAMI_KAYIP_USDT
    # Kademe 2 (micro-live) promotion sonrası içindir ve onaysız.
    k2 = [x for x in tablo["kademeler"] if x["kademe"] == 2][0]
    assert k2.get("pilot") is not True and not (k2.get("onay") or {}).get("tarih")


def test_repo_venue_kaydi_kaynakli():
    v = json.loads((REPO / "config/venue_statu.json").read_text(encoding="utf-8"))
    assert v["sonuc"] == "AÇIK" and v["kaynaklar"] and v["kayit_tarihi"]


# ============================================================ live gate


def test_pilot_kapisi_promotion_r8_shadow_istemez_digerleri_durur(kok):
    _yaz(kok, _kademe())
    r = kapi_raporu(CalismaModu.LIVE_PENDING_APPROVAL,
                    KapiBaglami(kok=kok, strateji="sma_kesisim", ag=_hesap(100.0)))
    k = _k(r)
    for yok in ("strateji_onayi", "operasyon_r8", "shadow_live_kaniti"):
        assert yok not in k
    for var in ("paper_kaniti", "testnet_kaniti", "kademe", "acik_kararlar", "venue_statusu",
                "kill_tatbikati", "testler", "kritik_hata_yok", "islem_anahtari_yetkisi",
                "canli_baglanti"):
        assert var in k, var
    assert k["pilot_siniri"]["gecti"] is True
    assert k["pilot_hesap_degeri"]["gecti"] is True
    assert k["kademe"]["gecti"] is True
    assert k["acik_kararlar"]["gecti"] is True  # Kademe 2 kararları pilotu tutmaz
    assert r["pilot"] is True and r["azami_kayip_usdt"] == 10.0
    assert not r["gecti"]  # venue/anahtar/kill/testler bu tmp kökte yok


def test_pilot_olmayan_kademe_hala_promotion_ister(kok):
    t = _kademe()
    t["kademeler"][1]["pilot"] = False
    _yaz(kok, t)
    r = kapi_raporu(CalismaModu.LIVE_PENDING_APPROVAL, KapiBaglami(kok=kok, strateji="s"))
    k = _k(r)
    assert "strateji_onayi" in k and "shadow_live_kaniti" in k and "pilot_siniri" not in k
    assert r["pilot"] is False and r["azami_kayip_usdt"] is None


@pytest.mark.parametrize("alanlar", [
    {"sermaye_usdt": 100.01},
    {"sermaye_usdt": None},
    {"azami_kayip_usdt": 10.5},
    {"azami_kayip_usdt": None},
    {"azami_kayip_usdt": 0.0},
    {"sermaye_usdt": 8.0, "azami_kayip_usdt": 8.0},
])
def test_pilot_siniri_tavani_asan_kademeyi_reddeder(kok, alanlar):
    _yaz(kok, _kademe(**alanlar))
    k = _k(kapi_raporu(CalismaModu.LIVE,
                       KapiBaglami(kok=kok, strateji="sma_kesisim", ag=_hesap(100.0))))
    assert k["pilot_siniri"]["gecti"] is False


@pytest.mark.parametrize(("alanlar", "strateji"), [
    ({}, "baska_strateji"),                 # onay kademedeki stratejiye verildi
    ({"strateji": None}, "sma_kesisim"),    # kayıtta strateji yok
    ({"sembol": None}, "sma_kesisim"),      # kayıtta sembol yok
    ({"sembol": ""}, "sma_kesisim"),
])
def test_pilot_siniri_kademe_strateji_ve_sembolune_bagli(kok, alanlar, strateji):
    _yaz(kok, _kademe(**alanlar))
    k = _k(kapi_raporu(CalismaModu.LIVE,
                       KapiBaglami(kok=kok, strateji=strateji, ag=_hesap(100.0))))
    assert k["pilot_siniri"]["gecti"] is False


def test_pilot_raporu_sembolu_tasir_ve_hash_sembole_bagli(kok):
    _yaz(kok, _kademe())
    b = KapiBaglami(kok=kok, strateji="sma_kesisim", ag=_hesap(100.0))
    r1 = kapi_raporu(CalismaModu.LIVE, b)
    assert r1["sembol"] == "BTCUSDT"
    _yaz(kok, _kademe(sembol="ETHUSDT"))
    r2 = kapi_raporu(CalismaModu.LIVE, b)
    assert r2["sembol"] == "ETHUSDT" and r2["hash"] != r1["hash"]


def test_pilot_siniri_strateji_ister(kok):
    _yaz(kok, _kademe())
    k = _k(kapi_raporu(CalismaModu.LIVE, KapiBaglami(kok=kok)))
    assert k["pilot_siniri"]["gecti"] is False


@pytest.mark.parametrize(("toplam", "olculemeyen", "gecer"), [
    (100.0, (), True),
    (90.0, (), True),     # sermaye − azami kayıp: sınır dahil
    (150.0, (), True),    # sermaye × 1,5: sınır dahil
    (150.01, (), False),  # fazla para pilot hesabında durmaz
    (89.99, (), False),   # yatırılmamış
    (100.0, ("XYZ",), False),  # ölçülemeyen varlık tahmin edilmez
])
def test_pilot_hesap_degeri(kok, toplam, olculemeyen, gecer):
    _yaz(kok, _kademe())
    k = _k(kapi_raporu(CalismaModu.LIVE,
                       KapiBaglami(kok=kok, strateji="s", ag=_hesap(toplam, olculemeyen))))
    assert k["pilot_hesap_degeri"]["gecti"] is gecer


def test_pilot_hesap_degeri_ag_yoksa_olculemedi(kok):
    _yaz(kok, _kademe())
    k = _k(kapi_raporu(CalismaModu.LIVE, KapiBaglami(kok=kok, strateji="s")))
    assert k["pilot_hesap_degeri"]["gecti"] is None


def test_pilot_kararlari_eksik_ya_da_acik_ise_kapali(kok):
    t = _kademe()
    t["kararlar"]["venue_statusu"] = {"durum": "DECISION REQUIRED"}
    _yaz(kok, t)
    k = _k(kapi_raporu(CalismaModu.LIVE, KapiBaglami(kok=kok, strateji="s")))
    assert k["acik_kararlar"]["gecti"] is False
    del t["kararlar"]["venue_statusu"]
    _yaz(kok, t)
    k = _k(kapi_raporu(CalismaModu.LIVE, KapiBaglami(kok=kok, strateji="s")))
    assert k["acik_kararlar"]["gecti"] is False


def test_rapor_hash_hesap_degerinin_oynakligina_bagli_degil(kok):
    _yaz(kok, _kademe())
    h1 = kapi_raporu(CalismaModu.LIVE, KapiBaglami(kok=kok, strateji="s", ag=_hesap(100.0)))
    h2 = kapi_raporu(CalismaModu.LIVE, KapiBaglami(kok=kok, strateji="s", ag=_hesap(97.3)))
    assert h1["hash"] == h2["hash"]


def test_hesap_degeri_hesapla():
    class V:
        def __init__(self, t):
            self.toplam = t

    def fiyat(sembol):
        if sembol == "BTCUSDT":
            return 50_000.0
        raise KeyError(sembol)

    s = hesap_degeri_hesapla({"USDT": V(60.0), "BTC": V(0.001), "USDC": 5.0, "ZZZ": V(3.0),
                              "BNB": V(0.0)}, fiyat)
    assert s["toplam_usdt"] == pytest.approx(115.0)
    assert s["olculemeyen"] == ["ZZZ"]
    assert "BNB" not in s["varliklar"]


# ============================================================ risk modu


def test_pilot_risk_modu_promotion_istemez_kanit_uretemez():
    assert "pilot" in MODLAR
    assert MOD_ESIGI["pilot"] is Asama.YOK
    assert MOD_ESIGI["live"] is Asama.LIVE
    with pytest.raises(PromotionHatasi):
        Kanit(paper_gun=30.0, paper_kesinti=0, paper_mod="pilot")


# ============================================================ execution hattı

K = SembolKurallari("BTCUSDT", 0.01, 0.00001, 5.0, "TRADING", "BTC", "USDT")
T0 = 1_699_999_200_000
SAAT = 3_600_000


class Saat:
    def __init__(self) -> None:
        self.t = T0 + SAAT

    def __call__(self) -> int:
        return self.t


def niyet(hedef=0.3, yon=Yon.BUY, zaman=T0, sebep="TEST"):
    return onayla(
        sinyal=Sinyal(symbol="BTCUSDT", side=yon, target_exposure=hedef, confidence=0.9,
                      reason=sebep, timestamp=zaman),
        onayli_maruziyet=hedef, limit_kimligi="k" * 64, karar_ms=zaman,
    )


def test_guvenlik_limitleri_kayip_tavani_dogrulanir():
    class L:
        azami_maruziyet, azami_brut_maruziyet = 0.3, 1.0
        gunluk_zarar_limiti, drawdown_limiti = 0.02, 0.2

    assert GuvenlikLimitleri.risk_limitlerinden(L, 100.0).azami_kayip_usdt is None
    g = GuvenlikLimitleri.risk_limitlerinden(L, 100.0, azami_kayip_usdt=10.0)
    assert g.azami_kayip_usdt == 10.0 and g.sozluk()["azami_kayip_usdt"] == 10.0
    assert g.kayip_tavani_asildi(90.0) and not g.kayip_tavani_asildi(90.01)
    for yanlis in (0.0, 100.0, 150.0):
        with pytest.raises(ValueError):
            GuvenlikLimitleri.risk_limitlerinden(L, 100.0, azami_kayip_usdt=yanlis)


def test_kayip_tavani_safe_mode_artirani_engeller_azaltani_gecirir(tmp_path):
    saat = Saat()
    b = PaperBorsa(kurallar={"BTCUSDT": K}, maliyet=PaperMaliyet(10.0, 5.0), saat=saat,
                   acilis_bakiyesi={"USDT": 100.0})
    b.fiyat_bildir("BTCUSDT", 50_000.0, saat.t)
    lim = GuvenlikLimitleri(sermaye_usdt=100.0, azami_maruziyet=0.3, azami_brut_maruziyet=1.0,
                            gunluk_zarar_limiti=0.99, drawdown_limiti=0.99,
                            azami_kayip_usdt=10.0)
    hat = ExecutionHatti(mod=CalismaModu.PAPER, adaptor=b, defter=EmirDefteri(), limitler=lim,
                         sembol="BTCUSDT", kosu_dizini=tmp_path / "k", audit=BellekDefteri(),
                         saat=saat)
    hat.baslat()
    assert hat.uygula(niyet(0.3), son_kapali_bar_ms=T0).sonuc == "gonderildi"
    b.bar_acilisi("BTCUSDT", 50_000.0, T0 + SAAT)
    hat.mutabakat_yap()
    miktar = hat.hesap().miktar
    assert miktar > 0.0
    # Fiyat %70 düşer: 30 USDT'lik pozisyon ≈ 9 USDT → özkaynak ≈ 79 ≤ 90.
    b.fiyat_bildir("BTCUSDT", 15_000.0, saat.t)
    t1 = T0 + SAAT
    u = hat.uygula(niyet(0.3, sebep="YENI", zaman=t1), son_kapali_bar_ms=t1)
    assert u.engel == Engel.KAYIP_TAVANI and hat.safe_mode
    assert "K-115" in hat.safe_isareti.read_text(encoding="utf-8")
    # Azaltan geçer.
    t2 = t1 + SAAT
    u = hat.uygula(niyet(0.0, yon=Yon.FLAT, zaman=t2), son_kapali_bar_ms=t2)
    assert u.sonuc == "gonderildi" and u.miktar == pytest.approx(miktar)
    # İşaret elle kaldırılsa da özkaynak tavanın altındayken her barda yeniden konur.
    hat.safe_isareti.unlink()
    hat.ozkaynak_isle(hat.hesap().ozkaynak, t2 + SAAT)
    assert hat.safe_mode


# ============================================================ kurulum


class _CanliMod:
    def mod(self) -> CalismaModu:
        return CalismaModu.LIVE


def _canli_kur(monkeypatch, tmp_path, *, pilot: bool, risk_modu: str, sembol: str = "BTCUSDT"):
    from scryne_quant.trader import kurulum
    from scryne_quant.trader.kurulum import KosuIstegi

    y = yetki.ver(host=CANLI_HOST, kanit_hash="k", onay_hash="o", strateji="sma_kesisim",
                  kademe=1, sermaye_usdt=100.0)
    rapor = {"pilot": pilot, "azami_kayip_usdt": 10.0 if pilot else None,
             "sembol": "BTCUSDT" if pilot else None}
    monkeypatch.setattr(kurulum, "canli_yetki_ver", lambda b: (y, rapor))
    env = tmp_path / ".env"
    env.write_text("SQ_BINANCE_LIVE_API_KEY=a\nSQ_BINANCE_LIVE_API_SECRET=b\n", encoding="utf-8")
    istek = KosuIstegi(mod=CalismaModu.LIVE, kosu="p1", strateji="sma_kesisim", parametreler={},
                       sembol=sembol, sermaye_usdt=10_000.0, risk_modu=risk_modu,
                       kok=tmp_path / "runs", env_dosyasi=env, kurallar=K)
    return kurulum.kosu_kur(istek, mod_defteri=_CanliMod(),
                            kapi_baglami=KapiBaglami(strateji="sma_kesisim"))


def test_kurulum_pilot_kademe_live_risk_modunu_reddeder(monkeypatch, tmp_path):
    from scryne_quant.trader.kurulum import KurulumHatasi

    with pytest.raises(KurulumHatasi, match="'pilot' olmalı"):
        _canli_kur(monkeypatch, tmp_path, pilot=True, risk_modu="live")
    with pytest.raises(KurulumHatasi, match="'live' olmalı"):
        _canli_kur(monkeypatch, tmp_path, pilot=False, risk_modu="pilot")


def test_kurulum_pilot_hat_kayip_tavanini_ve_kademe_sermayesini_tasir(monkeypatch, tmp_path):
    y, _ = _canli_kur(monkeypatch, tmp_path, pilot=True, risk_modu="pilot")
    assert y.hat.limitler.azami_kayip_usdt == 10.0
    assert y.hat.limitler.sermaye_usdt == 100.0  # istek 10.000 idi; kademe tavanı bağlar
    assert y.risk.mod == "pilot" and y.ayar.risk_modu == "pilot"


def test_kurulum_pilot_baska_sembolde_kurulmaz(monkeypatch, tmp_path):
    from scryne_quant.trader.kurulum import KurulumHatasi

    with pytest.raises(KurulumHatasi, match="pilot kademesi 'BTCUSDT' için onaylı"):
        _canli_kur(monkeypatch, tmp_path, pilot=True, risk_modu="pilot", sembol="ETHUSDT")
