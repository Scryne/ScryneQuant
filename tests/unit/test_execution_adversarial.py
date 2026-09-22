"""Execution katmanı adversarial denetimi (K-114 denetimi, 2026-09-22).

Mevcut testlerin **kapsamadığı** saldırı/arıza senaryoları. Her test bir güvenlik
değişmezini negatif yönden sınar: koşul eksik, bilinmiyor, bayat, doğrulanamıyor, onaysız,
mutabakat dışı ya da yetkisizse sonuç ALLOW değil BLOCK / SAFE_MODE / halt olmalı.
Gerçek ağ yok; gerçek emir yok; borsa `PaperBorsa` ya da sahte taşıma.
"""

from __future__ import annotations

import ast
import json
import pickle
import shutil
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

import pytest
import requests

from scryne_quant.exchange import yetki
from scryne_quant.exchange.canli import CANLI_HOST
from scryne_quant.exchange.golge import GolgeAdaptoru
from scryne_quant.exchange.hatalar import BelirsizSonuc, BorsaHatasi
from scryne_quant.exchange.imzali import TESTNET_HOST, BinanceImzaliAdaptoru
from scryne_quant.exchange.kurallar import KuralIhlali, SembolKurallari, emri_dogrula
from scryne_quant.exchange.paper_adaptoru import PaperBorsa, PaperMaliyet
from scryne_quant.execution import canli_kapi
from scryne_quant.execution.canli_kapi import (
    AgYoklamasi,
    CanliKapiKapali,
    KapiBaglami,
    Kontrol,
    canli_yetki_ver,
    kapi_raporu,
    r8_kriter_sha256,
)
from scryne_quant.execution.hat import Engel, ExecutionHatti, GuvenlikLimitleri, HatHatasi
from scryne_quant.execution.mod import (
    CalismaModu,
    ModDefteri,
    ModHatasi,
    OnayGerekli,
    canli_onayla,
    satir_hashi,
)
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.oms.emir import EmirDurumu
from scryne_quant.risk.audit import SqliteDefter
from scryne_quant.risk.niyet import onayla
from scryne_quant.strategy.sinyal import Sinyal, Yon

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "scryne_quant"
K = SembolKurallari("BTCUSDT", 0.01, 0.00001, 5.0, "TRADING", "BTC", "USDT",
                    min_miktar=0.0001, azami_miktar=100.0, market_azami_miktar=50.0,
                    azami_notional=1_000_000.0)
T0 = 1_699_999_200_000
SAAT = 3_600_000
LIM = GuvenlikLimitleri(10_000.0, 0.3, 1.0, 0.05, 0.2)


class Saat:
    def __init__(self) -> None:
        self.t = T0 + SAAT

    def __call__(self) -> int:
        return self.t


def niyet(hedef=0.2, yon=Yon.BUY, zaman=T0, sebep="TEST"):
    return onayla(
        sinyal=Sinyal(symbol="BTCUSDT", side=yon, target_exposure=hedef, confidence=0.9,
                      reason=sebep, timestamp=zaman),
        onayli_maruziyet=hedef, limit_kimligi="k" * 64, karar_ms=zaman,
    )


def paper(saat, yol=":memory:", **kw) -> PaperBorsa:
    b = PaperBorsa(kurallar={"BTCUSDT": K}, maliyet=PaperMaliyet(10.0, 5.0), saat=saat,
                   yol=yol, acilis_bakiyesi={"USDT": 10_000.0}, **kw)
    b.fiyat_bildir("BTCUSDT", 50_000.0, saat())
    return b


def hat(adaptor, dizin, saat, defter=None, mod=CalismaModu.PAPER, **kw) -> ExecutionHatti:
    return ExecutionHatti(mod=mod, adaptor=adaptor, defter=defter or EmirDefteri(),
                          limitler=LIM, sembol="BTCUSDT", kosu_dizini=dizin, saat=saat, **kw)


class Cokus(Exception):
    """Sürecin öldüğü an (BorsaHatasi değil: hiçbir katman yakalamaz)."""


class Sarmalayici:
    """Adaptörü sarar; emir anında sürecin öldüğünü taklit eder."""

    def __init__(self, ic: Any, cokus: str = "") -> None:
        self._ic, self.cokus = ic, cokus

    def __getattr__(self, ad: str) -> Any:
        return getattr(self._ic, ad)

    def market_emri(self, **kw: Any) -> Any:
        if self.cokus == "once":
            raise Cokus("gönderimden önce öldü")
        y = self._ic.market_emri(**kw)
        if self.cokus == "sonra":
            raise Cokus("gönderimden sonra öldü")
        return y


# ============================================================ yetki (authorization)


def test_live_pending_approval_bir_kosu_modu_degil(tmp_path):
    s = Saat()
    with pytest.raises(HatHatasi, match="onay bekler"):
        hat(paper(s), tmp_path, s, mod=CalismaModu.LIVE_PENDING_APPROVAL)


def test_live_pending_approval_iken_live_kosusu_kurulamaz(tmp_path, monkeypatch):
    from scryne_quant.trader.kurulum import KosuIstegi, KurulumHatasi, kosu_kur

    md = ModDefteri(tmp_path / "mod.json")
    for m in list(CalismaModu)[1:5]:
        md.yukselt(m, kapi_raporu={"hedef": str(m), "gecti": True, "hash": "h"})
    assert md.mod() is CalismaModu.LIVE_PENDING_APPROVAL
    with pytest.raises(KurulumHatasi, match="sistem modu LIVE_PENDING_APPROVAL"):
        kosu_kur(KosuIstegi(mod=CalismaModu.LIVE, kosu="x", strateji="sma_kesisim",
                            parametreler={}, risk_modu="live", kok=tmp_path),
                 mod_defteri=md)


def test_yetki_baska_surecte_gecersiz():
    y = yetki.ver(host=CANLI_HOST, kanit_hash="k", onay_hash="o", strateji="s", kademe=1,
                  sermaye_usdt=100.0)
    kod = (
        "from scryne_quant.exchange import yetki as Y;"
        f"t=Y.CanliYetki({y.host!r},{y.kanit_hash!r},{y.onay_hash!r},{y.strateji!r},"
        f"{y.kademe},{y.sermaye_usdt!r},imza={y.imza!r});print(t.gecerli)"
    )
    cikti = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True,
                           check=True, cwd=REPO)
    assert cikti.stdout.strip() == "False"


def test_yetki_serilestirilemez_ve_host_degisikligi_gecersiz():
    y = yetki.ver(host=CANLI_HOST, kanit_hash="k", onay_hash="o", strateji="s", kademe=1,
                  sermaye_usdt=100.0)
    with pytest.raises(TypeError, match="serileştirilemez"):
        pickle.dumps(y)
    from dataclasses import replace

    assert not replace(y, host="https://evil.example").gecerli


def test_yetki_baska_hosta_adaptor_kurmaz():
    y = yetki.ver(host=CANLI_HOST, kanit_hash="k", onay_hash="o", strateji="s", kademe=1,
                  sermaye_usdt=100.0)
    with pytest.raises(yetki.CanliYetkiGecersiz, match="host"):
        BinanceImzaliAdaptoru(anahtar="a", sir="b", host="https://evil.example",
                              oturum=object(), canli_yetki=y)
    # http:// testnet de "testnet" değil: yetkisiz kurulamaz.
    with pytest.raises(yetki.CanliYetkiGecersiz):
        BinanceImzaliAdaptoru(anahtar="a", sir="b", host="http://testnet.binance.vision",
                              oturum=object())


@pytest.fixture
def kok(tmp_path):
    (tmp_path / "config").mkdir()
    for ad in ("r8_kriterler.json", "risk.json"):
        shutil.copy(REPO / "config" / ad, tmp_path / "config" / ad)
    return tmp_path


def _sahte_gecer(monkeypatch, kanit="sabit"):
    monkeypatch.setattr(canli_kapi, "_kontroller",
                        lambda hedef, b: [Kontrol("x", True, "ok", kanit=kanit)])
    monkeypatch.setattr(canli_kapi, "kademe_tablosu", lambda b: {
        "aktif_kademe": 1, "kademeler": [{"kademe": 1, "sermaye_usdt": 150.0}]})


def test_audit_karsiligi_olmayan_sahte_onay_satiri_yetki_vermez(kok, monkeypatch):
    """Zinciri doğru hesaplanmış ama audit'e yazılmamış elle eklenmiş LIVE onayı."""
    _sahte_gecer(monkeypatch)
    audit = SqliteDefter(":memory:")
    md = ModDefteri(kok / "mod.json")  # audit'siz: satırların audit karşılığı yok
    b = KapiBaglami(kok=kok, strateji="s", mod_defteri=md, audit=audit)
    for m in list(CalismaModu)[1:5]:
        md.yukselt(m, kapi_raporu=kapi_raporu(m, b))
    r = kapi_raporu(CalismaModu.LIVE, b)
    kayit = json.loads((kok / "mod.json").read_text(encoding="utf-8"))
    onceki = kayit["gecmis"][-1]["satir_hash"]
    satir = {"nereden": "LIVE_PENDING_APPROVAL", "nereye": "LIVE", "yon": "yukari",
             "zaman_ms": 1, "kapi_hash": r["hash"], "not": "sahte", "strateji": "s",
             "kademe": 1, "sermaye_usdt": 150.0, "onceki_hash": onceki}
    satir["satir_hash"] = satir_hashi(satir, onceki)
    kayit["gecmis"].append(satir)
    (kok / "mod.json").write_text(json.dumps(kayit), encoding="utf-8")
    assert md.mod() is CalismaModu.LIVE  # zincir tutarlı...
    with pytest.raises(CanliKapiKapali, match="audit"):  # ...ama audit'te yok
        canli_yetki_ver(b)
    with pytest.raises(CanliKapiKapali, match="audit"):  # audit verilmezse de kapalı
        canli_yetki_ver(KapiBaglami(kok=kok, strateji="s", mod_defteri=md, audit=None))


def test_yeni_commit_sonrasi_eski_onay_yetki_vermez(kok, monkeypatch):
    git = {"commit": "a" * 40, "dirty": False, "git_yok": False}
    monkeypatch.setattr(canli_kapi, "git_durumu", lambda kok_: dict(git))
    ex = kok / "runs/execution"
    ex.mkdir(parents=True)
    (ex / "testler.json").write_text(json.dumps(
        {"commit": "a" * 40, "dirty": False, "gecen": 10, "kalan": 0}), encoding="utf-8")
    b = KapiBaglami(kok=kok)
    once = canli_kapi.testler_kontrolu(b)
    assert once.gecti is True
    git["commit"] = "b" * 40  # yeni commit, test kaydı eski
    assert canli_kapi.testler_kontrolu(b).gecti is False
    (ex / "testler.json").write_text(json.dumps(
        {"commit": "b" * 40, "dirty": False, "gecen": 10, "kalan": 0}), encoding="utf-8")
    sonra = canli_kapi.testler_kontrolu(b)
    assert sonra.gecti is True and sonra.kanit != once.kanit  # onay hash'i değişir


def test_anahtar_yetkisi_ya_da_anahtarin_kendisi_degisirse_kanit_degisir():
    from scryne_quant.execution.canli_kapi import _ag_kontrolu, _yetki_degerlendir

    ok = {"enableReading": True, "enableSpotAndMarginTrading": True,
          "enableWithdrawals": False, "enableInternalTransfer": False, "enableMargin": False,
          "enableFutures": False, "permitsUniversalTransfer": False,
          "enableVanillaOptions": False, "enablePortfolioMarginTrading": False,
          "ipRestrict": True, "createTime": 111}
    k1 = _ag_kontrolu("islem", lambda: ok, _yetki_degerlendir("live"), "")
    k2 = _ag_kontrolu("islem", lambda: {**ok, "createTime": 222}, _yetki_degerlendir("live"), "")
    k3 = _ag_kontrolu("islem", lambda: {**ok, "enableWithdrawals": True},
                      _yetki_degerlendir("live"), "")
    assert k1.gecti and k2.gecti and k1.kanit != k2.kanit  # başka anahtar → yeniden onay
    assert k3.gecti is False  # çekim yetkisi açılmış anahtar → kapalı


def test_onaydan_sonra_mod_indirilirse_calisan_kosu_artirmaz(tmp_path):
    s = Saat()
    mod = {"m": CalismaModu.PAPER}
    h = hat(paper(s), tmp_path, s, mod_tavani=lambda: mod["m"])
    h.baslat()
    mod["m"] = CalismaModu.DISABLED  # sq execution indir DISABLED
    assert h.uygula(niyet(), son_kapali_bar_ms=T0).engel == Engel.MOD


def test_mod_okunamazsa_disabled_sayilir(tmp_path):
    s = Saat()

    def bozuk() -> CalismaModu:
        raise OSError("mod.json okunamadı")

    h = hat(paper(s), tmp_path, s, mod_tavani=bozuk)
    h.baslat()
    assert h.uygula(niyet(), son_kapali_bar_ms=T0).engel == Engel.MOD


def test_canli_hat_tavansiz_artiran_emir_gondermez(tmp_path):
    """LIVE hattı `mod_tavani` verilmeden kurulursa artıran emir yok (fail closed)."""
    s = Saat()
    h = hat(paper(s), tmp_path, s)
    h.mod = CalismaModu.LIVE  # kurulum kontrolünü atlayan bir çağıran
    h.baslat()
    assert h.uygula(niyet(), son_kapali_bar_ms=T0).engel == Engel.MOD


# ============================================================ durum makinesi


@pytest.mark.parametrize("baslangic", [CalismaModu.DISABLED, CalismaModu.PAPER,
                                       CalismaModu.SHADOW, CalismaModu.TESTNET,
                                       CalismaModu.LIVE_PENDING_APPROVAL])
def test_hicbir_moddan_yukselt_ile_live_olmaz(tmp_path, baslangic):
    md = ModDefteri(tmp_path / "m.json")
    for m in list(CalismaModu)[1:list(CalismaModu).index(baslangic) + 1]:
        md.yukselt(m, kapi_raporu={"hedef": str(m), "gecti": True, "hash": "h"})
    assert md.mod() is baslangic
    with pytest.raises(OnayGerekli):
        md.yukselt(CalismaModu.LIVE, kapi_raporu={"hedef": "LIVE", "gecti": True, "hash": "h"})
    if baslangic is not CalismaModu.LIVE_PENDING_APPROVAL:
        r = {"hedef": "LIVE", "gecti": True, "hash": "h"}
        with pytest.raises(ModHatasi):
            canli_onayla(md, kapi_raporu=r, gorulen_hash="h",
                         not_metni="yirmi karakterden uzun gerekçe", onaylayan="x")
    assert md.mod() is baslangic


# ============================================================ emirler


def test_unknown_emir_varken_hicbir_emir_gitmez(tmp_path):
    s = Saat()
    b = paper(s)

    class Belirsiz(Sarmalayici):
        def market_emri(self, **kw: Any) -> Any:
            raise BelirsizSonuc("okuma zaman aşımı")

    h = hat(Belirsiz(b), tmp_path, s)
    h.baslat()
    u = h.uygula(niyet(), son_kapali_bar_ms=T0)
    assert u.sonuc == "belirsiz"
    t1 = T0 + SAAT
    assert h.uygula(niyet(0.0, yon=Yon.FLAT, zaman=t1),
                    son_kapali_bar_ms=t1).engel == Engel.BELIRSIZ_EMIR


def test_bozuk_borsa_yaniti_yeniden_gonderim_uretmez():
    """200 ama tanınmayan durum: istisna, emir SUBMITTED'da (açık) kalır, ikinci gönderim yok."""
    from scryne_quant.execution.motor import EmirMotoru

    class Tasima:
        def __init__(self) -> None:
            self.post = 0

        def request(self, method, url, **_):
            class Y:
                status_code = 200
                headers: dict = {}

                def __init__(self, g):
                    self._g = g
                    self.text = json.dumps(g)

                def json(self):
                    return self._g

            if "/api/v3/time" in url:
                return Y({"serverTime": T0})
            if "exchangeInfo" in url:
                return Y({"symbols": [{"symbol": "BTCUSDT", "status": "TRADING",
                                       "baseAsset": "BTC", "quoteAsset": "USDT", "filters": [
                                           {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                                           {"filterType": "LOT_SIZE", "stepSize": "0.00001"}]}]})
            if "ticker" in url:
                return Y({"price": "50000"})
            self.post += 1
            return Y({"status": "GARIP", "orderId": 1, "clientOrderId": "x"})

    t = Tasima()
    a = BinanceImzaliAdaptoru(anahtar="a", sir="b", oturum=t, ipv4=False)
    d = EmirDefteri()
    with pytest.raises(ValueError):
        EmirMotoru(d, a).gonder(niyet(), 0.002)
    assert d.tumu()[0].durum is EmirDurumu.SUBMITTED  # açık: hat yeni emir vermez
    tekrar = EmirMotoru(d, a).gonder(niyet(), 0.002)
    assert not tekrar.gonderildi and t.post == 1


def test_yazmada_429_reddedilir_tekrar_denenmez():
    from scryne_quant.execution.motor import EmirMotoru

    class Tasima:
        post = 0

        def request(self, method, url, **_):
            class Y:
                def __init__(self, k, g, h=None):
                    self.status_code, self._g, self.headers = k, g, h or {}
                    self.text = json.dumps(g)

                def json(self):
                    return self._g

            if "/api/v3/time" in url:
                return Y(200, {"serverTime": T0})
            if "exchangeInfo" in url:
                return Y(200, {"symbols": [{"symbol": "BTCUSDT", "status": "TRADING",
                                            "baseAsset": "BTC", "quoteAsset": "USDT",
                                            "filters": [
                                                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                                                {"filterType": "LOT_SIZE",
                                                 "stepSize": "0.00001"}]}]})
            if "ticker" in url:
                return Y(200, {"price": "50000"})
            Tasima.post += 1
            return Y(429, {"code": -1015, "msg": "Too many new orders"}, {"Retry-After": "1"})

    a = BinanceImzaliAdaptoru(anahtar="a", sir="b", oturum=Tasima(), ipv4=False)
    s = EmirMotoru(EmirDefteri(), a).gonder(niyet(), 0.002)
    assert s.emir.durum is EmirDurumu.REJECTED and Tasima.post == 1


@pytest.mark.parametrize("miktar, parca", [(0.00005, "minQty"), (150.0, "maxQty"),
                                           (60.0, "marketMaxQty")])
def test_sembol_kurali_tavanlari(miktar, parca):
    with pytest.raises(KuralIhlali, match=parca):
        emri_dogrula(K, miktar, referans_fiyat=50_000.0)


def test_max_notional():
    with pytest.raises(KuralIhlali, match="maxNotional"):
        emri_dogrula(K, 30.0, referans_fiyat=50_000.0)  # 1,5 M > 1 M


def test_hassasiyet_asagi_yuvarlanir_asla_yukari():
    assert emri_dogrula(K, 0.0012999, referans_fiyat=50_000.0) == pytest.approx(0.00129)


# ============================================================ risk


def test_mutabakat_yapilamadiysa_artiran_emir_yok(tmp_path):
    s = Saat()
    b = paper(s)

    class BakiyeYok(Sarmalayici):
        def bakiye(self) -> Any:
            raise BorsaHatasi("account uç noktası yanıt vermiyor")

    h = hat(BakiyeYok(b), tmp_path, s, defter=EmirDefteri())
    h.defter.acilis_yaz({"USDT": (10_000.0, 0.0)}, borsa_ms=s(), yerel_ms=s(), not_metni="")
    sonuc = h.mutabakat_yap()
    assert not sonuc["ok"] and not h.halt
    assert h.uygula(niyet(), son_kapali_bar_ms=T0).engel == Engel.MUTABAKAT


def test_baslangic_mutabakati_olmadan_artiran_emir_yok(tmp_path):
    s = Saat()
    h = hat(paper(s), tmp_path, s)  # baslat() çağrılmadı
    assert h.uygula(niyet(), son_kapali_bar_ms=T0).engel == Engel.MUTABAKAT


def test_disaridan_bakiye_degisimi_halt(tmp_path):
    s = Saat()
    b = paper(s)
    h = hat(b, tmp_path, s)
    h.baslat()
    with b._islem() as db:  # hesaba dışarıdan 500 USDT (yatırma / elle işlem)
        db.execute("UPDATE bakiye SET serbest = serbest + 500 WHERE varlik='USDT'")
    assert not h.mutabakat_yap()["ok"] and "pozisyon" in h.halt
    assert h.uygula(niyet(0.0, yon=Yon.FLAT), son_kapali_bar_ms=T0).engel == Engel.HALT


def test_gunluk_zarar_limiti(tmp_path):
    s = Saat()
    h = hat(paper(s), tmp_path, s)
    h.baslat()
    h.izleyici.gun, h.izleyici.gun_basi, h.izleyici.zirve = s() // 86_400_000, 10_600.0, 10_600.0
    assert h.uygula(niyet(), son_kapali_bar_ms=T0).engel == Engel.GUNLUK_ZARAR


def test_kar_birikse_de_boyut_sermaye_tavanini_asmaz(tmp_path):
    s = Saat()
    b = paper(s)
    h = hat(b, tmp_path, s)
    h.baslat()
    from scryne_quant.execution.hat import HesapGorunumu

    gor = HesapGorunumu("BTCUSDT", nakit=30_000.0, miktar=0.0, fiyat=50_000.0,
                        komisyon_toplam=0.0)
    miktar, kisit = h._miktar(niyet(0.3), gor)
    assert miktar * 50_000.0 == pytest.approx(0.3 * 10_000.0)  # taban = sermaye
    assert "sermaye_tavani" in kisit


def test_gonderim_aninda_bayat_karar_engellenir(tmp_path):
    """Yürütücü bayatlığı borsa saatinden ölçer: karar barından sonra bir bar daha kapandıysa
    artıran emir gitmez (önceki hâlde `son_kapali_bar_ms=bar.open_time` totolojiydi)."""
    s = Saat()
    h = hat(paper(s), tmp_path, s)
    h.baslat()
    assert h.uygula(niyet(zaman=T0), son_kapali_bar_ms=T0 + SAAT).engel == Engel.BAYAT_KARAR
    kaynak = (SRC / "trader/yurutucu.py").read_text(encoding="utf-8")
    assert "son_kapali_bar_ms=bar.open_time" not in kaynak


# ============================================================ toparlanma


def _yeniden(yol_defter, adaptor, dizin, saat) -> ExecutionHatti:
    h = hat(adaptor, dizin, saat, defter=EmirDefteri(yol_defter))
    h.baslat()
    return h


def test_gonderimden_once_olum_failed_kapanir(tmp_path):
    s = Saat()
    b = paper(s)
    h = hat(Sarmalayici(b, "once"), tmp_path, s, defter=EmirDefteri(tmp_path / "e.sqlite"))
    h.baslat()
    with pytest.raises(Cokus):
        h.uygula(niyet(), son_kapali_bar_ms=T0)
    assert h.defter.tumu()[0].durum is EmirDurumu.SUBMITTED
    h2 = _yeniden(tmp_path / "e.sqlite", b, tmp_path, s)
    assert h2.defter.tumu()[0].durum is EmirDurumu.FAILED
    assert not h2.halt and h2.mutabakat_tamam


def test_gonderimden_sonra_olum_borsadan_cozulur(tmp_path):
    s = Saat()
    b = paper(s)
    h = hat(Sarmalayici(b, "sonra"), tmp_path, s, defter=EmirDefteri(tmp_path / "e.sqlite"))
    h.baslat()
    with pytest.raises(Cokus):
        h.uygula(niyet(), son_kapali_bar_ms=T0)
    h2 = _yeniden(tmp_path / "e.sqlite", b, tmp_path, s)
    assert h2.defter.tumu()[0].durum is EmirDurumu.ACKNOWLEDGED
    # Açık emir varken ikinci emir yok; fill sonrası mutabakat temiz.
    assert h2.uygula(niyet(0.25, sebep="IKI"), son_kapali_bar_ms=T0).engel == Engel.ACIK_EMIR
    b.bar_acilisi("BTCUSDT", 50_100.0, T0 + SAAT)
    assert h2.mutabakat_yap()["ok"]
    assert h2.defter.tumu()[0].durum is EmirDurumu.FILLED


def test_fill_sonrasi_olum_pozisyon_tutarli(tmp_path):
    s = Saat()
    b = paper(s, aninda=True)
    h = hat(Sarmalayici(b, "sonra"), tmp_path, s, defter=EmirDefteri(tmp_path / "e.sqlite"))
    h.baslat()
    with pytest.raises(Cokus):
        h.uygula(niyet(), son_kapali_bar_ms=T0)
    h2 = _yeniden(tmp_path / "e.sqlite", b, tmp_path, s)
    assert h2.defter.tumu()[0].durum is EmirDurumu.FILLED
    assert h2.mutabakat_tamam and not h2.son_pozisyon.get("halt")
    assert h2.hesap().miktar == pytest.approx(0.04)


def test_yeniden_baslatmada_unknown_ve_borsa_yoksa_bloklu(tmp_path):
    s = Saat()
    b = paper(s)

    class Belirsiz(Sarmalayici):
        def market_emri(self, **kw: Any) -> Any:
            raise BelirsizSonuc("kopma")

    h = hat(Belirsiz(b), tmp_path, s, defter=EmirDefteri(tmp_path / "e.sqlite"))
    h.baslat()
    h.uygula(niyet(), son_kapali_bar_ms=T0)

    class Ulasilamaz(Sarmalayici):
        def emir_sorgula(self, **kw: Any) -> Any:
            raise BorsaHatasi("ağ yok")

    h2 = hat(Ulasilamaz(b), tmp_path, s, defter=EmirDefteri(tmp_path / "e.sqlite"))
    h2.baslat()
    assert not h2.mutabakat_tamam
    t1 = T0 + SAAT
    assert h2.uygula(niyet(0.0, yon=Yon.FLAT, zaman=t1),
                     son_kapali_bar_ms=t1).engel == Engel.BELIRSIZ_EMIR


def test_paper_ayni_bar_yeniden_islenirse_emir_kendi_barinda_dolmaz():
    s = Saat()
    b = paper(s)
    s.t = T0 + SAAT  # karar anı = t+1 açılışı
    b.market_emri(istemci_kimligi="c", sembol="BTCUSDT", yon="BUY", miktar=0.01)
    assert b.bar_acilisi("BTCUSDT", 49_000.0, T0) == []  # karar barının açılışı: dolmaz
    assert b.bar_acilisi("BTCUSDT", 50_000.0, T0 + SAAT) == ["c"]


def test_ayni_kosu_iki_surecle_surulemez_ve_tek_canli_kosu(tmp_path):
    from scryne_quant.exchange.akis import df_barlara
    from scryne_quant.live.kilit import KilitAlinamadi
    from tests.conftest import bar_uret
    from tests.unit.test_trader_yurutucu import kur

    barlar = df_barlara(bar_uret(n=150))
    y1, _ = kur(tmp_path / "a", barlar)
    y2, _ = kur(tmp_path / "a", barlar)
    kilitler = y1.kilitle()
    try:
        with pytest.raises(KilitAlinamadi):
            y2.kilitle()
    finally:
        for k in kilitler:
            k.kapat()
    # İki ayrı canlı koşu: ikincisi global canlı kilidini alamaz.
    c1, _ = kur(tmp_path / "c1", barlar)
    c2, _ = kur(tmp_path / "c2", barlar)
    c1.ayar.mod = c2.ayar.mod = CalismaModu.LIVE
    k1 = c1.kilitle()
    try:
        with pytest.raises(KilitAlinamadi):
            c2.kilitle()
    finally:
        for k in k1:
            k.kapat()


def test_safe_mode_isaretiyle_yeniden_baslatma_risk_motoru_kilitli(tmp_path):
    from scryne_quant.exchange.akis import df_barlara
    from scryne_quant.live import kill as kill_mod
    from tests.conftest import bar_uret
    from tests.unit.test_trader_yurutucu import kur

    barlar = df_barlara(bar_uret(n=150))
    kur(tmp_path / "a", barlar)
    kill_mod.safe_isaretle(tmp_path / "a" / "kosu", "kill tatbikatı")
    y, _ = kur(tmp_path / "a", barlar)
    assert y.risk.durum.safe_mode and y.hat.safe_mode


# ============================================================ izolasyon


def test_paper_modu_gercek_adaptorle_kurulamaz(tmp_path):
    a = BinanceImzaliAdaptoru(anahtar="a", sir="b", oturum=object(), ipv4=False)
    with pytest.raises(HatHatasi, match="PaperBorsa"):
        hat(a, tmp_path, Saat())


def test_testnet_modu_canli_adaptorle_kurulamaz(tmp_path):
    a = BinanceImzaliAdaptoru(anahtar="a", sir="b", host=CANLI_HOST, oturum=object(),
                              salt_okunur=True)
    with pytest.raises(HatHatasi, match="TESTNET"):
        hat(a, tmp_path, Saat(), mod=CalismaModu.TESTNET)


def test_golge_hic_yazmaz_hat_uzerinden_de():
    s = Saat()
    b = paper(s)
    yazmalar: list[str] = []

    class Izle(Sarmalayici):
        def market_emri(self, **kw: Any) -> Any:
            yazmalar.append("market")
            return super().market_emri(**kw)

    g = GolgeAdaptoru(Izle(b))
    for cagri in (g.market_emri, g.limit_emri, g.emir_iptal):
        with pytest.raises(PermissionError):
            cagri(istemci_kimligi="x", sembol="BTCUSDT", yon="BUY", miktar=1, fiyat=1)
    assert yazmalar == []


# ============================================================ sırlar


def test_hata_mesajlari_ve_repr_sir_tasimaz():
    SIR, ANAHTAR = "SIR_SENTINEL_9f3", "ANAHTAR_SENTINEL_7c1"

    class Kopuk:
        def request(self, method, url, **_):
            raise requests.exceptions.ConnectionError(f"bağlantı koptu: {url}")

    a = BinanceImzaliAdaptoru(anahtar=ANAHTAR, sir=SIR, oturum=Kopuk(), ipv4=False)
    for cagri in (lambda: a.son_fiyat("BTCUSDT"), lambda: a.bakiye()):
        with pytest.raises(BorsaHatasi) as e:
            cagri()
        assert SIR not in str(e.value) and ANAHTAR not in str(e.value)
    assert SIR not in repr(a) and ANAHTAR not in repr(a)


def test_kosu_ciktilari_sir_alanlari_tasimaz(tmp_path):
    from scryne_quant.exchange.akis import df_barlara
    from tests.conftest import bar_uret
    from tests.unit.test_trader_yurutucu import kur

    y, k = kur(tmp_path / "a", df_barlara(bar_uret(n=200)))
    y.tekrar_oynat(k, isinma=100)
    for p in (tmp_path / "a").glob("*.json"):
        metin = p.read_text(encoding="utf-8").lower()
        for kelime in ("api_key", "api_secret", "secret", "x-mbx-apikey", "sir\":"):
            assert kelime not in metin, (p.name, kelime)


# ============================================================ R8 ve araştırma izolasyonu


def _importlar(yol: Path) -> set[str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        agac = ast.parse(yol.read_text(encoding="utf-8"))
    out: set[str] = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.ImportFrom) and d.module:
            out.add(d.module)
            out.update(f"{d.module}.{a.name}" for a in d.names)
        elif isinstance(d, ast.Import):
            out.update(a.name for a in d.names)
    return {i for i in out if i.startswith("scryne_quant")}


def _modul_dosyasi(modul: str) -> Path | None:
    parca = modul.split(".")[1:]
    p = SRC.joinpath(*parca).with_suffix(".py")
    if p.is_file():
        return p
    p = SRC.joinpath(*parca, "__init__.py")
    return p if p.is_file() else None


def _kapanis(baslangic: list[str]) -> set[str]:
    gorulen: set[str] = set()
    kuyruk = list(baslangic)
    while kuyruk:
        m = kuyruk.pop()
        if m in gorulen:
            continue
        gorulen.add(m)
        d = _modul_dosyasi(m)
        if d is None:
            continue
        kuyruk.extend(i for i in _importlar(d) if _modul_dosyasi(i))
    return gorulen


#: R8'in çalışma zamanı modülleri (`sq paper evren-baslat` → `live/evren_*`).
R8_MODULLERI = ["scryne_quant.live.evren_kosturucu", "scryne_quant.live.evren_motor",
                "scryne_quant.live.evren_kurulum", "scryne_quant.live.motor",
                "scryne_quant.live.kosturucu", "scryne_quant.live.baslat",
                "scryne_quant.live.izleme", "scryne_quant.live.evren_pano"]
YENI_EXECUTION = {"scryne_quant.trader", "scryne_quant.execution.hat",
                  "scryne_quant.execution.mod", "scryne_quant.execution.canli_kapi",
                  "scryne_quant.exchange.canli", "scryne_quant.exchange.golge",
                  "scryne_quant.exchange.paper_adaptoru", "scryne_quant.exchange.yetki",
                  "scryne_quant.cli.execution"}


def test_r8_calisma_zamani_yeni_execution_paketlerine_ulasmaz():
    kapanis = _kapanis(R8_MODULLERI)
    sizinti = sorted(m for m in kapanis if any(m == y or m.startswith(y + ".")
                                               for y in YENI_EXECUTION))
    assert not sizinti, sizinti


def test_execution_katmani_arastirma_ve_promotion_yazmaz():
    yasak_cagri = {"ilerlet", "elle_onayla", "zincirle", "hipotez_kaydet", "program_kaydet"}
    for kok in ("execution", "trader", "exchange", "cli/execution.py"):
        yollar = [SRC / kok] if kok.endswith(".py") else list((SRC / kok).rglob("*.py"))
        for p in yollar:
            assert not any(i.startswith("scryne_quant.research") for i in _importlar(p)), p
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                agac = ast.parse(p.read_text(encoding="utf-8"))
            for d in ast.walk(agac):
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
                    assert d.func.attr not in yasak_cagri, (p, d.func.attr)
                    if d.func.attr == "yaz" and isinstance(d.func.value, ast.Call):
                        f = d.func.value.func
                        assert getattr(f, "id", "") != "PromotionDefteri", p


def test_r8_kriter_hashi_satir_sonundan_bagimsiz_icerige_duyarli(tmp_path):
    ham = (REPO / "config/r8_kriterler.json").read_bytes().replace(b"\r\n", b"\n")
    lf, crlf = tmp_path / "lf.json", tmp_path / "crlf.json"
    lf.write_bytes(ham)
    crlf.write_bytes(ham.replace(b"\n", b"\r\n"))
    assert r8_kriter_sha256(lf) == r8_kriter_sha256(crlf)
    assert r8_kriter_sha256(lf).startswith("2c3d520e8f3fe5d2")
    bozuk = tmp_path / "b.json"
    bozuk.write_bytes(ham.replace(b"PASS", b"PAS5", 1))
    assert not r8_kriter_sha256(bozuk).startswith("2c3d520e8f3fe5d2")


def test_r8_kriter_dosyasi_ve_r8_modulleri_k111den_beri_degismedi():
    def fark(*yollar: str) -> str:
        return subprocess.run(["git", "diff", "--stat", "dd66452", "--", *yollar],
                              capture_output=True, text=True, cwd=REPO, check=False).stdout

    if subprocess.run(["git", "cat-file", "-e", "dd66452"], cwd=REPO,
                      capture_output=True, check=False).returncode != 0:
        pytest.skip("K-111 commit'i bu klonda yok")
    assert fark("config/r8_kriterler.json") == ""
    assert fark("src/scryne_quant/live") == ""


def test_testnet_host_sabit():
    assert TESTNET_HOST == "https://testnet.binance.vision"
    assert AgYoklamasi().islem_anahtari_kisitlari is None  # ağ verilmezse ölçülemedi
