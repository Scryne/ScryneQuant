"""Live gate: `preflight`teki **her** blokerin kodda enforce edildiğinin kanıtı. (K-114 denetimi)

Her kontrol fonksiyonu için: eksik/bilinmeyen/kötü girdi → `gecti` `True` değil (kapı
kapalı); geçerli girdi → `True` (kontrol her zaman kapalı kalan bir süs değil). Kullanıcı
kararı gerektiren alanlar (risk sermayesi, kademe, venue, açık kararlar) repo'daki gerçek
`config/kademe.json` ile de sınanır: bugün `UNDECIDED` ve kapıyı kapatıyor.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from scryne_quant.execution import canli_kapi as ck
from scryne_quant.execution.mod import CalismaModu
from scryne_quant.risk.audit import Olay, OlayTuru, SqliteDefter
from scryne_quant.risk.promotion import Asama, AsamaSonucu, Kanit, PromotionDefteri, PromotionKaydi

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def kok(tmp_path):
    (tmp_path / "config").mkdir()
    for ad in ("r8_kriterler.json", "risk.json"):
        shutil.copy(REPO / "config" / ad, tmp_path / "config" / ad)
    return tmp_path


def b(kok, **kw) -> ck.KapiBaglami:
    return ck.KapiBaglami(kok=kok, **kw)


def yaz(p: Path, veri: dict) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(veri), encoding="utf-8")
    return p


def capala(dizin: Path, olay: str, dosya: Path, alan: str) -> None:
    d = SqliteDefter(dizin / "audit.sqlite")
    d.yaz(Olay(tur=OlayTuru.EXECUTION, zaman_ms=1, sembol="BTCUSDT", durum={},
               govde={"olay": olay, alan: hashlib.sha256(dosya.read_bytes()).hexdigest()}))
    d.kapat()


# ------------------------------------------------------------ temel


def test_mod_kaydi_bozuksa_kapali(kok):
    yaz(kok / "runs/execution/mod.json", {"gecmis": [{"nereye": "LIVE"}]})
    assert ck.mod_kaydi_kontrolu(b(kok)).gecti is False


def test_risk_config_yoksa_kapali(kok):
    (kok / "config/risk.json").unlink()
    assert ck.risk_config_kontrolu(b(kok)).gecti is False


def test_r8_kriter_dosyasi_yoksa_kapali(kok):
    (kok / "config/r8_kriterler.json").unlink()
    assert ck.r8_sozlesmesi_kontrolu(b(kok)).gecti is False


# ------------------------------------------------------------ koşu kanıtları


@pytest.mark.parametrize("durum", ["yok", "gecmedi", "capasiz", "duzenlenmis", "iyi"])
def test_kosu_kaniti(kok, durum):
    dizin = kok / "runs/execution/t1"
    if durum != "yok":
        p = yaz(dizin / "rapor.json", {"mod": "TESTNET", "gecti": durum != "gecmedi",
                                       "bitis_ms": 1, "kalan": []})
        if durum != "capasiz":
            capala(dizin, "rapor", p, "rapor_sha256")
        if durum == "duzenlenmis":  # çapadan sonra elle değiştirilmiş
            yaz(p, {"mod": "TESTNET", "gecti": True, "bitis_ms": 2, "kalan": []})
    k = ck.kosu_raporu_kontrolu(b(kok), CalismaModu.TESTNET, ad="t", engel="e")
    assert k.gecti is (durum == "iyi"), k.ayrinti


# ------------------------------------------------------------ strateji (promotion)


def _promotion(kok: Path, asama: Asama, audit: SqliteDefter) -> None:
    kayit = PromotionKaydi(strateji="s")
    if asama is not Asama.YOK:
        kayit._kaydet(AsamaSonucu(asama, True, "test"), Kanit())
        kayit.asama = asama
    PromotionDefteri(kok / "runs/promotion").yaz(kayit, audit=audit)


def test_strateji_onayi(kok):
    audit = SqliteDefter(":memory:")
    assert ck.strateji_onayi_kontrolu(b(kok, audit=audit)).gecti is False  # strateji yok
    assert ck.strateji_onayi_kontrolu(b(kok, strateji="s")).gecti is None  # audit yok
    _promotion(kok, Asama.LIVE_ADAYI, audit)
    assert ck.strateji_onayi_kontrolu(b(kok, strateji="s", audit=audit)).gecti is False
    # Aynı audit'e ikinci (farklı) bir kayıt yazmak kısaltma gibi görünür → K-082 fail closed.
    _promotion(kok, Asama.LIVE, audit)
    assert ck.strateji_onayi_kontrolu(b(kok, strateji="s", audit=audit)).gecti is False
    audit = SqliteDefter(":memory:")
    _promotion(kok, Asama.LIVE, audit)
    assert ck.strateji_onayi_kontrolu(b(kok, strateji="s", audit=audit)).gecti is True
    # Dosyada aşama elle LIVE yazılmış ama geçmiş öyle demiyor → fail closed.
    p = kok / "runs/promotion/s.json"
    v = json.loads(p.read_text(encoding="utf-8"))
    v["gecmis"][-1]["asama"] = "live_adayi"
    p.write_text(json.dumps(v), encoding="utf-8")
    assert ck.strateji_onayi_kontrolu(b(kok, strateji="s", audit=audit)).gecti is False


# ------------------------------------------------------------ R8 (operasyon)


def _r8(kok, **kw) -> None:
    sha = ck.r8_kriter_sha256(kok / "config/r8_kriterler.json")
    yaz(kok / "config/operasyon_dogrulama.json",
        {"r8": {"sonuc": "PASS", "karar": "K-112", "kriter_sha256": sha, "kayit": "x", **kw}})


@pytest.mark.parametrize("ek, beklenen", [
    (None, False), ({"sonuc": "FAIL"}, False), ({"karar": "K-999"}, False),
    ({"kriter_sha256": "0" * 64}, False), ({}, True),
])
def test_operasyon_r8(kok, ek, beklenen):
    if ek is not None:
        _r8(kok, **ek)
    assert ck.operasyon_kontrolu(b(kok)).gecti is beklenen


# ------------------------------------------------------------ kademe / kararlar / venue


def _kademe(**kw) -> dict:
    t = {"risk_sermayesi_usdt": 1000.0, "aktif_kademe": 1, "kademeler": [
        {"kademe": 0, "sermaye_usdt": 0.0, "onay": {"not": "shadow tamam", "tarih": "2026"}},
        {"kademe": 1, "sermaye_usdt": 100.0, "onay": {"not": "ilk kademe", "tarih": "2026"}}]}
    t.update(kw)
    return t


@pytest.mark.parametrize("tablo, beklenen", [
    (None, False),
    (_kademe(risk_sermayesi_usdt=None), False),
    (_kademe(aktif_kademe=0), False),
    (_kademe(kademeler=[{"kademe": 1, "sermaye_usdt": None, "onay": {}}]), False),
    (_kademe(kademeler=[{"kademe": 1, "sermaye_usdt": 5000.0,
                         "onay": {"not": "x", "tarih": "y"}}]), False),  # > risk sermayesi
    (_kademe(kademeler=[{"kademe": 1, "sermaye_usdt": 100.0, "onay": {"not": None}}]), False),
    (_kademe(aktif_kademe=2, kademeler=[
        {"kademe": 1, "sermaye_usdt": 100.0, "onay": {"not": None, "tarih": None}},
        {"kademe": 2, "sermaye_usdt": 200.0, "onay": {"not": "x", "tarih": "y"}}]), False),
    (_kademe(), True),
])
def test_kademe(kok, tablo, beklenen):
    if tablo is not None:
        yaz(kok / "config/kademe.json", tablo)
    assert ck.kademe_kontrolu(b(kok)).gecti is beklenen


def test_repodaki_kademe_tablosu_bugun_undecided_ve_kapali(kok):
    shutil.copy(REPO / "config/kademe.json", kok / "config/kademe.json")
    assert ck.kademe_kontrolu(b(kok)).gecti is False
    k = ck.kademe_kararlari_kontrolu(b(kok))
    assert k.gecti is False and "risk_sermayesi" in k.ayrinti and "venue_statusu" in k.ayrinti


def test_acik_kararlar_kapaninca_gecer(kok):
    yaz(kok / "config/kademe.json", {"kararlar": {"a": {"durum": "kabul (K-200)"}}})
    assert ck.kademe_kararlari_kontrolu(b(kok)).gecti is True


@pytest.mark.parametrize("venue, beklenen", [
    (None, False), ({"sonuc": "BELİRSİZ", "kaynaklar": ["u"]}, False),
    ({"sonuc": "AÇIK", "kaynaklar": []}, False), ({"sonuc": "AÇIK", "kaynaklar": ["u"]}, True),
])
def test_venue(kok, venue, beklenen):
    if venue is not None:
        yaz(kok / "config/venue_statu.json", venue)
    assert ck.venue_kontrolu(b(kok)).gecti is beklenen


# ------------------------------------------------------------ kill / kritik hata / ağ


def _kill(kok, capali=True, **kw) -> None:
    dizin = kok / "runs/execution/s1"
    veri = {"canli_host": True, "basarili": True, "kalan_acik_emir": {"BTCUSDT": 0},
            "surec": {"pid": 1, "sonlandirildi": True, "terminate": True}}
    veri.update(kw)
    p = yaz(dizin / "kill.json", veri)
    if capali:
        capala(dizin, "kill", p, "kill_sha256")


@pytest.mark.parametrize("ek, capali, beklenen", [
    ({"canli_host": False}, True, False),
    ({"surec": {"sonlandirildi": True, "not": "zaten ölüydü"}}, True, False),
    ({"surec": {}}, True, False),
    ({"kalan_acik_emir": {}}, True, False),  # açık emirler doğrulanmadı
    ({"basarili": False}, True, False),
    ({}, False, False),  # audit çapası yok
    ({}, True, True),
])
def test_kill_tatbikati(kok, ek, capali, beklenen):
    _kill(kok, capali, **ek)
    assert ck.kill_tatbikati_kontrolu(b(kok)).gecti is beklenen


@pytest.mark.parametrize("sorun", ["safe", "halt", "unknown", "yok"])
def test_kritik_hata(kok, sorun):
    dizin = kok / "runs/execution/k1"
    yaz(dizin / "kosu.json", {"mod": "PAPER"})
    yaz(dizin / "durum.json", {"halt": "x" if sorun == "halt" else "",
                               "emirler": {"belirsiz": 1 if sorun == "unknown" else 0}})
    if sorun == "safe":
        (dizin / "kosu.safemode").write_text("{}", encoding="utf-8")
    assert ck.kritik_hata_kontrolu(b(kok)).gecti is (sorun == "yok")


def test_ag_kontrolleri_olculemedi_hata_ve_kotu_yanit_kapali():
    d = ck._baglanti_degerlendir
    assert ck._ag_kontrolu("x", None, d, "").gecti is None

    def patlar() -> dict:
        raise TimeoutError("ağ yok")

    assert ck._ag_kontrolu("x", patlar, d, "").gecti is False
    assert ck._ag_kontrolu("x", lambda: {"ok": False}, d, "").gecti is False
    assert ck._ag_kontrolu("x", lambda: {"ok": True}, d, "").gecti is True


def test_live_gate_tek_bir_kontrol_bile_kaldiysa_kapali(kok, monkeypatch):
    liste = [ck.Kontrol(f"k{i}", True, "") for i in range(15)] + [ck.Kontrol("son", None, "")]
    monkeypatch.setattr(ck, "_kontroller", lambda hedef, b_: liste)
    r = ck.kapi_raporu(CalismaModu.LIVE, b(kok))
    assert not r["gecti"] and [e["ad"] for e in r["engeller"]] == ["son"]
