"""Gerçek paraya giden yolun yapısal korumaları. (K-114)

1. **Import sınırı:** `exchange.canli` (canlı host + işlem anahtarı) yalnızca shadow/live giriş
   noktalarından import edilir; araştırma, backtest, strateji, R8'in `live/` yolu, risk,
   oms, veri, Jev ulaşamaz (Faz-8-Hazirlik §1.3/2).
2. **Tek yetki üreticisi:** `yetki.ver` yalnızca `execution/canli_kapi.py`de çağrılır.
3. **Tek onay çağrısı:** `mod.canli_onayla` yalnızca `cli/execution.py`de (insanın komutu).
4. **Host koruması:** imzalı adaptör testnet dışında yetkisiz kurulamaz; salt okunur ve
   yalnız-iptal kurulumlar taşımada emir açamaz; sahte/değiştirilmiş yetki geçmez.
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path

import pytest

from scryne_quant.exchange import yetki
from scryne_quant.exchange.canli import CANLI_HOST, yetki_ihlalleri
from scryne_quant.exchange.imzali import BinanceImzaliAdaptoru, SaltOkunurIhlali

KOK = Path(__file__).resolve().parents[2] / "src" / "scryne_quant"

#: `exchange.canli`yi import etmesine izin verilen modüller.
CANLI_IZINLI = {
    "cli/execution.py",
    "trader/kurulum.py",
    "execution/canli_kapi.py",
}

YASAKLI_PAKETLER = ("backtest", "research", "strategy", "live", "risk", "oms", "data",
                    "features", "portfolio", "jev")


def _dosyalar():
    for p in KOK.rglob("*.py"):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            agac = ast.parse(p.read_text(encoding="utf-8"))
        yield p.relative_to(KOK).as_posix(), agac


def _importlar(agac: ast.AST) -> set[str]:
    out: set[str] = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.ImportFrom) and d.module:
            out.add(d.module)
            out.update(f"{d.module}.{a.name}" for a in d.names)
        elif isinstance(d, ast.Import):
            out.update(a.name for a in d.names)
    return out


def _cagrilar(agac: ast.AST, ad: str) -> int:
    n = 0
    for d in ast.walk(agac):
        if isinstance(d, ast.Call):
            f = d.func
            if (isinstance(f, ast.Attribute) and f.attr == ad) or (
                isinstance(f, ast.Name) and f.id == ad
            ):
                n += 1
    return n


def test_canli_modulu_yalniz_izinli_yerlerden():
    ihlal = []
    for yol, agac in _dosyalar():
        if yol == "exchange/canli.py":
            continue
        canli_var = any(
            i == "scryne_quant.exchange.canli" or i.startswith("scryne_quant.exchange.canli.")
            for i in _importlar(agac)
        )
        if canli_var and yol not in CANLI_IZINLI:
            ihlal.append(yol)
    assert not ihlal, f"exchange.canli'yi import etmemesi gereken modüller: {ihlal}"


def test_yasakli_paketler_canli_ve_yetkiye_ulasamaz():
    for yol, agac in _dosyalar():
        if yol.split("/")[0] not in YASAKLI_PAKETLER:
            continue
        imp = _importlar(agac)
        assert not any("exchange.canli" in i or "exchange.yetki" in i for i in imp), yol


def test_yetki_ver_tek_yerde():
    yerler = [yol for yol, a in _dosyalar() if _cagrilar(a, "ver") and "yetki" in yol + str(
        _importlar(a))]
    cagiranlar = [yol for yol, a in _dosyalar()
                  if yol != "exchange/yetki.py" and "scryne_quant.exchange.yetki" in str(
                      _importlar(a)) and _cagrilar(a, "ver")]
    assert cagiranlar == ["execution/canli_kapi.py"], (cagiranlar, yerler)


def test_canli_onayla_yalniz_cli():
    cagiranlar = [yol for yol, a in _dosyalar()
                  if yol != "execution/mod.py" and _cagrilar(a, "canli_onayla")]
    assert cagiranlar == ["cli/execution.py"]


def test_imzali_canli_host_sabiti_tasimiyor():
    metin = (KOK / "exchange/imzali.py").read_text(encoding="utf-8")
    assert "api.binance.com" not in metin


class Oturum:
    def __init__(self) -> None:
        self.istekler: list[tuple[str, str]] = []

    def request(self, method, url, **_):
        self.istekler.append((method, url))
        raise AssertionError("ağa çıkılmamalıydı")


def test_canli_host_yetkisiz_kurulmaz():
    with pytest.raises(yetki.CanliYetkiGecersiz):
        BinanceImzaliAdaptoru(anahtar="a", sir="b", host=CANLI_HOST, oturum=Oturum())


def test_sahte_ya_da_degistirilmis_yetki_gecmez():
    sahte = yetki.CanliYetki(CANLI_HOST, "k", "o", "s", 1, 100.0, imza="0" * 64)
    with pytest.raises(yetki.CanliYetkiGecersiz):
        BinanceImzaliAdaptoru(anahtar="a", sir="b", host=CANLI_HOST, oturum=Oturum(),
                              canli_yetki=sahte)
    gercek = yetki.ver(host=CANLI_HOST, kanit_hash="k", onay_hash="o", strateji="s",
                  kademe=1, sermaye_usdt=100.0)
    from dataclasses import replace

    buyutulmus = replace(gercek, sermaye_usdt=1_000_000.0)
    assert gercek.gecerli and not buyutulmus.gecerli
    with pytest.raises(yetki.CanliYetkiGecersiz):
        yetki.dogrula(buyutulmus)


def test_canli_yetkili_kurulum_anahtari_acikca_ister():
    y = yetki.ver(host=CANLI_HOST, kanit_hash="k", onay_hash="o", strateji="s",
                  kademe=1, sermaye_usdt=100.0)
    with pytest.raises(yetki.CanliYetkiGecersiz, match="açıkça"):
        BinanceImzaliAdaptoru(host=CANLI_HOST, oturum=Oturum(), canli_yetki=y)


def test_salt_okunur_emir_acamaz_ve_aga_cikmaz():
    o = Oturum()
    a = BinanceImzaliAdaptoru(anahtar="a", sir="b", host=CANLI_HOST, oturum=o, salt_okunur=True)
    with pytest.raises(SaltOkunurIhlali):
        a.market_emri(istemci_kimligi="x", sembol="BTCUSDT", yon="BUY", miktar=0.001)
    with pytest.raises(SaltOkunurIhlali):
        a.emir_iptal(sembol="BTCUSDT", istemci_kimligi="x")
    assert not [i for i in o.istekler if i[0] != "GET"]


def test_yalniz_iptal_emir_acamaz():
    a = BinanceImzaliAdaptoru(anahtar="a", sir="b", host=CANLI_HOST, oturum=Oturum(),
                              yalniz_iptal=True)
    a._kural_onbellek["BTCUSDT"] = __import__(
        "scryne_quant.exchange.kurallar", fromlist=["SembolKurallari"]
    ).SembolKurallari("BTCUSDT", 0.01, 0.00001, 5.0, "TRADING", "BTC", "USDT")
    with pytest.raises(SaltOkunurIhlali):
        a.market_emri(istemci_kimligi="x", sembol="BTCUSDT", yon="BUY", miktar=0.001)


def test_yetki_tablosu():
    shadow_ok = {"enableReading": True, "enableSpotAndMarginTrading": False,
                 "enableWithdrawals": False, "enableInternalTransfer": False,
                 "enableMargin": False, "enableFutures": False,
                 "permitsUniversalTransfer": False, "enableVanillaOptions": False,
                 "enablePortfolioMarginTrading": False, "ipRestrict": False}
    assert yetki_ihlalleri("shadow", shadow_ok) == []
    # İşlem yetkili anahtar shadow'u açamaz; IP kısıtsız/çekim yetkili anahtar live'ı açamaz.
    assert yetki_ihlalleri("shadow", {**shadow_ok, "enableSpotAndMarginTrading": True})
    live = {**shadow_ok, "enableSpotAndMarginTrading": True, "ipRestrict": True}
    assert yetki_ihlalleri("live", live) == []
    assert yetki_ihlalleri("live", {**live, "ipRestrict": False})
    assert yetki_ihlalleri("live", {**live, "enableWithdrawals": True})
    eksik = dict(live)
    del eksik["enableWithdrawals"]
    assert yetki_ihlalleri("live", eksik)  # söylenmeyen yetki kapalı sayılmaz
