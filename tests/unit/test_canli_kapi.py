"""Mod kapıları ve live gate. (K-114)

Ölçülen iddialar:
- PAPER kapısı repo durumuyla geçer (mod kaydı, R8 sözleşme hash'i, risk config).
- LIVE kapısı **bugün kapalı** ve engelleri adıyla listeler (strateji, R8, kademe, venue…).
- Ağ verilmeyen kontrol **ölçülemedi** yazar ve kapıyı kapatır.
- R8 kriter dosyası değişirse her kapı kapanır.
- `canli_yetki_ver`: mod LIVE değilse, kapı şimdi geçmiyorsa ya da hash onaylanan hash'le
  aynı değilse yetki yok; hepsi tutarsa mühürlü yetki ve canlı adaptör kurulabilir.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scryne_quant.exchange.canli import CANLI_HOST, canli_emir_adaptoru
from scryne_quant.execution import canli_kapi
from scryne_quant.execution.canli_kapi import (
    AgYoklamasi,
    CanliKapiKapali,
    KapiBaglami,
    Kontrol,
    canli_yetki_ver,
    kapi_raporu,
)
from scryne_quant.execution.mod import CalismaModu, ModDefteri, canli_onayla
from scryne_quant.risk.audit import Olay, OlayTuru, SqliteDefter

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def kok(tmp_path):
    (tmp_path / "config").mkdir()
    for ad in ("r8_kriterler.json", "risk.json"):
        shutil.copy(REPO / "config" / ad, tmp_path / "config" / ad)
    return tmp_path


def test_paper_kapisi_gecer(kok):
    r = kapi_raporu(CalismaModu.PAPER, KapiBaglami(kok=kok))
    assert r["gecti"], r["engeller"]
    assert {k["ad"] for k in r["kontroller"]} == {"mod_kaydi", "r8_sozlesmesi", "risk_config"}


def test_r8_kriteri_degisirse_kapi_kapanir(kok):
    p = kok / "config/r8_kriterler.json"
    p.write_text(p.read_text(encoding="utf-8") + " ", encoding="utf-8")
    r = kapi_raporu(CalismaModu.PAPER, KapiBaglami(kok=kok))
    assert not r["gecti"] and r["engeller"][0]["ad"] == "r8_sozlesmesi"


def test_shadow_kapisi_ag_yoksa_olculemedi(kok):
    r = kapi_raporu(CalismaModu.SHADOW, KapiBaglami(kok=kok))
    k = {x["ad"]: x for x in r["kontroller"]}
    assert k["okuma_anahtari_yetkisi"]["gecti"] is None
    assert k["paper_kaniti"]["gecti"] is False
    assert not r["gecti"]


def capali_rapor(dizin: Path, govde: dict) -> Path:
    """Yürütücünün yaptığı gibi: rapor.json + hash'i koşunun audit zincirinde."""
    import hashlib

    dizin.mkdir(parents=True, exist_ok=True)
    p = dizin / "rapor.json"
    p.write_text(json.dumps(govde), encoding="utf-8")
    d = SqliteDefter(dizin / "audit.sqlite")
    d.yaz(Olay(tur=OlayTuru.EXECUTION, zaman_ms=1, sembol="BTCUSDT", durum={},
               govde={"olay": "rapor",
                      "rapor_sha256": hashlib.sha256(p.read_bytes()).hexdigest()}))
    d.kapat()
    return p


def test_shadow_kapisi_islem_yetkili_anahtari_reddeder(kok):
    capali_rapor(kok / "runs/execution/p1", {"mod": "PAPER", "gecti": True, "bitis_ms": 1})
    ag = AgYoklamasi(
        okuma_anahtari_kisitlari=lambda: {"enableReading": True,
                                          "enableSpotAndMarginTrading": True},
        canli_baglantisi=lambda: {"ok": True},
    )
    r = kapi_raporu(CalismaModu.SHADOW, KapiBaglami(kok=kok, ag=ag))
    k = {x["ad"]: x for x in r["kontroller"]}
    assert k["paper_kaniti"]["gecti"] is True
    assert k["okuma_anahtari_yetkisi"]["gecti"] is False
    assert "enableSpotAndMarginTrading" in k["okuma_anahtari_yetkisi"]["ayrinti"]


def test_live_kapisi_bugun_kapali_ve_engelleri_adlandirir(kok):
    r = kapi_raporu(CalismaModu.LIVE_PENDING_APPROVAL, KapiBaglami(kok=kok, strateji="sma_kesisim"))
    assert not r["gecti"]
    engeller = {e["ad"] for e in r["engeller"]}
    for ad in ("strateji_onayi", "operasyon_r8", "kademe", "venue_statusu", "kill_tatbikati",
               "testler", "islem_anahtari_yetkisi", "testnet_kaniti", "shadow_live_kaniti"):
        assert ad in engeller, ad


def _hepsi_gecer(monkeypatch):
    monkeypatch.setattr(
        canli_kapi, "_kontroller",
        lambda hedef, b: [Kontrol("x", True, "ok", kanit="sabit")],
    )
    monkeypatch.setattr(canli_kapi, "kademe_tablosu", lambda b: {
        "aktif_kademe": 1, "kademeler": [{"kademe": 1, "sermaye_usdt": 150.0}]})


def test_yetki_yalniz_live_modda_ve_onaylanan_hashle(kok, monkeypatch):
    _hepsi_gecer(monkeypatch)
    audit = SqliteDefter(":memory:")
    md = ModDefteri(kok / "runs/execution/mod.json", audit=audit)
    b = KapiBaglami(kok=kok, strateji="s", mod_defteri=md, audit=audit)
    with pytest.raises(CanliKapiKapali, match="LIVE değil"):
        canli_yetki_ver(b)
    for m in list(CalismaModu)[1:5]:
        md.yukselt(m, kapi_raporu=kapi_raporu(m, b))
    rapor = kapi_raporu(CalismaModu.LIVE, b)
    canli_onayla(md, kapi_raporu=rapor, gorulen_hash=rapor["hash"],
                 not_metni="test: bütün kapılar sahte-geçer, yetki mekanizması",
                 onaylayan="test")
    yetki, _ = canli_yetki_ver(b)
    assert yetki.gecerli and yetki.sermaye_usdt == 150.0 and yetki.kademe == 1
    a = canli_emir_adaptoru(yetki, "anahtar", "sir", oturum=object())
    assert a.canli and not a.salt_okunur

    # Onaydan sonra karar değiştiren bir şey değişirse (kanıt), yetki yok.
    monkeypatch.setattr(canli_kapi, "_kontroller",
                        lambda hedef, b: [Kontrol("x", True, "ok", kanit="BASKA")])
    with pytest.raises(CanliKapiKapali, match="farklı"):
        canli_yetki_ver(b)
    # Kapı şimdi geçmiyorsa yetki yok.
    monkeypatch.setattr(canli_kapi, "_kontroller",
                        lambda hedef, b: [Kontrol("x", False, "kaldı")])
    with pytest.raises(CanliKapiKapali, match="geçmiyor"):
        canli_yetki_ver(b)
    assert CANLI_HOST.startswith("https://")


def test_rapor_hash_oynak_ayrintiya_bagli_degil(kok):
    ag1 = AgYoklamasi(canli_baglantisi=lambda: {"ok": True, "rtt_ms": 10})
    ag2 = AgYoklamasi(canli_baglantisi=lambda: {"ok": True, "rtt_ms": 999})
    r1 = kapi_raporu(CalismaModu.SHADOW, KapiBaglami(kok=kok, ag=ag1))
    r2 = kapi_raporu(CalismaModu.SHADOW, KapiBaglami(kok=kok, ag=ag2))
    assert r1["hash"] == r2["hash"]


def test_golge_olcutu_istah_sayilarini_kademe_dosyasindan_okur(kok):
    (kok / "config/kademe.json").write_text(json.dumps(
        {"golge_olcutu": {"asgari_gun": 14, "asgari_golge": 20}}), encoding="utf-8")
    olc = canli_kapi.golge_olcutu(KapiBaglami(kok=kok, strateji="s"))
    iyi = {"strateji": "s", "risk_modu": "shadow", "sure_gun": 15, "golge_sayisi": 25,
           "kural_reddi": 0, "pozisyon_farki": 0, "saat_sicramasi": 0, "aciklanamaz_kesinti": 0}
    assert olc(iyi) is None
    assert "gozlem" in olc({**iyi, "risk_modu": "gozlem"})
    assert olc({**iyi, "sure_gun": 3})
    assert olc({**iyi, "kural_reddi": 1})
