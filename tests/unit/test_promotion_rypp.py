"""RYPP promotion zincirine bağlandı; alfa yolu değişmedi (K-126).

Ölçülenler:

- **Üç sonuç ayrı:** RYPP PASS → `out_of_sample` geçer; FAIL → `False`; INCONCLUSIVE → `None`.
  Hüküm raporlanan `durum`dan değil satırlardan türer; ikisi uyuşmazsa kanıt kurulmaz.
- **Eksik kanıt PASS değildir:** herhangi bir zorunlu koşul satırı, plasebo, stres, bootstrap,
  OOS süresi ya da B-3 bağımsız doğrulaması kaldırıldığında PASS üretilemez (özellik testi).
- **B-3:** bağımsız doğrulama yok → INCONCLUSIVE; bağımsız veride FAIL → FAIL; yetersiz bağımsız
  veri → INCONCLUSIVE; ana OOS ile aynı veri → kanıt hatası.
- **Protokol karışmaz:** alfa kanıtı RYPP sonucu, RYPP kanıtı alfa kapı sonucu taşıyamaz; RYPP
  gövdesi alfa kapısı yerine geçmez; `out_of_sample`ı bir protokolle geçen strateji ötekinin
  kanıtıyla ilerlemez.
- **Sistem değişmezleri RYPP'de de geçerli:** temiz ağaç, veri kalitesi, K-039 sayımı, risk
  incelemesi, paper, elle onay.
- **Alfa regresyonu:** varsayılan protokol alfa; alfa kararları ve kanıt alanları K-126
  öncesiyle aynı.
- Determinizm, zincir hash'i ve audit bağı RYPP satırlarında da çalışıyor.

RYPP kanıtı gerçek `risk_protokolu.degerlendir` çıktısından (sentetik piyasa) gelir ve JSON'dan
geçirilir (CLI'ın okuduğu biçim).
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from functools import cache
from typing import Any

import numpy as np
import pytest

from scryne_quant.research import risk_protokolu as rp
from scryne_quant.risk.audit import SqliteDefter
from scryne_quant.risk.promotion import (
    RYPP_BELIRSIZLIK,
    RYPP_ESIKLER,
    RYPP_KOSULLARI,
    RYPP_NOKTA,
    RYPP_YETERLILIK,
    ZORUNLU_KAPILAR,
    Asama,
    Kanit,
    PromotionDefteri,
    PromotionHatasi,
    PromotionKaydi,
    Protokol,
    bagimsiz_hukmu,
    rypp_hukmu,
)
from tests.unit.test_promotion import TAM_KANIT, tam_ilerlet
from tests.unit.test_risk_protokolu import _zamanlayici, girdi, piyasa

ANA_VERI = "v" * 64
BAGIMSIZ_VERI = "b" * 64
VINTAGE_VERI = "c" * 64
#: Senaryoların P3 bağlamı (K-128): k=1, `rypp_test` programının açılış bütçesi.
K = 1
PROGRAM = "rypp_test"


def _json(s: rp.RyppSonucu) -> dict[str, Any]:
    """CLI'ın okuduğu biçim: `RyppSonucu.sozluk()` → JSON dosyası → dict."""
    return json.loads(json.dumps(s.sozluk(), ensure_ascii=False))


@cache
def _uret(ad: str) -> str:
    """Senaryo → RYPP gövdesi (JSON metni; her çağıran kendi kopyasını açar)."""
    if ad in ("pass", "bagimsiz_pass", "vintage_pass"):
        r, rejim = piyasa(tohum={"pass": 1, "bagimsiz_pass": 3, "vintage_pass": 4}[ad])
        s = rp.degerlendir(girdi(r, _zamanlayici(rejim), aile_program=PROGRAM))
    elif ad == "fail_maruziyet":
        r, _ = piyasa()
        s = rp.degerlendir(girdi(r, np.full_like(r, 0.5), aile_program=PROGRAM))
    elif ad == "fail_stres":
        r, rejim = piyasa()
        g = girdi(r, _zamanlayici(rejim), aile_program=PROGRAM)
        coken = np.linspace(1.0, 0.5, len(r) + 1)
        s = rp.degerlendir(rp.RyppGirdisi(**{**g.__dict__, "strateji_2x_maliyet": coken}))
    elif ad == "fail_tek_olay":
        r, rejim = piyasa()
        w = np.ones_like(r)
        bas = np.flatnonzero(~rejim)[0]
        w[bas + 1:bas + np.argmax(rejim[bas:]) + 1] = 0.0
        s = rp.degerlendir(girdi(r, w, aile_program=PROGRAM))
    elif ad == "kisa_oos":
        r, rejim = piyasa(yil=1.2)
        s = rp.degerlendir(girdi(r, _zamanlayici(rejim), aile_program=PROGRAM))
    elif ad == "plasebo_yok":
        r, rejim = piyasa()
        s = rp.degerlendir(girdi(r, _zamanlayici(rejim), plasebo=False,
                                   aile_program=PROGRAM))
    elif ad == "stres_yok":
        r, rejim = piyasa()
        s = rp.degerlendir(girdi(r, _zamanlayici(rejim), stres=False,
                                   aile_program=PROGRAM))
    else:  # pragma: no cover
        raise KeyError(ad)
    return json.dumps(_json(s), ensure_ascii=False)


def govde(ad: str) -> dict[str, Any]:
    return json.loads(_uret(ad))


def VIN_FAIL() -> dict[str, Any]:  # noqa: N802 — senaryo sabiti gibi okunur
    """Vintage eşinde de FAIL (iki vintage tutarlı FAIL → FAIL, K-128)."""
    return bagimsiz("fail_maruziyet", veri=VINTAGE_VERI)


def bagimsiz(ad: str = "bagimsiz_pass", veri: str | None = BAGIMSIZ_VERI) -> dict[str, Any]:
    g = govde(ad)
    if veri is not None:
        g["veri_sha256"] = veri
    return g


def rypp_kanit(rypp: Any = "pass", bag: Any = "bagimsiz_pass", vin: Any = "vintage_pass",
               **deg: Any) -> Kanit:
    """TAM_KANIT'in sistem alanları + RYPP. `rypp`/`bag`/`vin` senaryo adı, dict ya da `None`.
    `vin` B-3'ün vintage eşi (K-128)."""
    r = govde(rypp) if isinstance(rypp, str) else rypp
    b = bagimsiz(bag) if isinstance(bag, str) else bag
    v = bagimsiz(vin, veri=VINTAGE_VERI) if isinstance(vin, str) else vin
    alanlar = {**{a: getattr(TAM_KANIT, a) for a in TAM_KANIT.__dataclass_fields__},
               "kapi_sonucu": None, "protokol": Protokol.RYPP, "rypp_sonucu": r,
               "bagimsiz_dogrulama": b, "bagimsiz_vintage": v, "veri_sha256": ANA_VERI,
               "rypp_aile_sayisi": K, **deg}
    return Kanit(**alanlar)


def oos(kanit: Kanit):
    """Zinciri `out_of_sample`a kadar götürür; o aşamanın sonucunu döndürür."""
    k = PromotionKaydi(strateji="rypp_aday")
    k.ilerlet(kanit)  # backtest
    k.ilerlet(kanit)  # kalite_kontrol
    assert k.asama is Asama.KALITE_KONTROL
    return k.ilerlet(kanit)


def _durum_yeniden(g: dict[str, Any]) -> dict[str, Any]:
    """Satırlar elle değiştirildiğinde `durum`u satırlarla tutarlı hâle getirir (dürüst sahte)."""
    g = copy.deepcopy(g)
    g["durum"] = "PASS"
    try:
        rypp_hukmu(g)
    except PromotionHatasi as e:
        for etiket in ("FAIL", "INCONCLUSIVE"):
            if f"türeyen {etiket}" in str(e):
                g["durum"] = etiket
    return g


def _satir_degistir(g: dict[str, Any], ad: str, gecti: Any = None, *, sil: bool = False):
    g = copy.deepcopy(g)
    if sil:
        g["kosullar"] = [s for s in g["kosullar"] if s["ad"] != ad]
    else:
        for s in g["kosullar"]:
            if s["ad"] == ad:
                s["gecti"] = gecti
    return g


# ------------------------------------------------------------------ sözleşme eşitliği


def test_kosul_listesi_risk_protokoluyle_ayni():
    """`risk/` `research/`i import edemez; liste kopya, eşitliği burada korunur."""
    g = govde("pass")
    assert g["durum"] == "PASS"
    adlar = [s["ad"] for s in g["kosullar"]]
    assert set(adlar) == RYPP_KOSULLARI and len(adlar) == len(RYPP_KOSULLARI)
    assert tuple(adlar) == (*RYPP_YETERLILIK, *RYPP_NOKTA, *RYPP_BELIRSIZLIK)


def test_esikler_risk_protokoluyle_ayni():
    assert {a: v["deger"] for a, v in rp.ESIKLER.items()} == RYPP_ESIKLER


def test_alfa_ve_rypp_listeleri_ayri():
    """RYPP koşulları alfa kapılarının yerine geçmez; ikisi ayrı kümeler (ad çakışması
    `oos_suresi` hariç — o da farklı eşikle, farklı gövdede)."""
    ortak = RYPP_KOSULLARI & ZORUNLU_KAPILAR
    assert ortak == {"oos_suresi"}


# ------------------------------------------------------------------ A-C: üç sonuç


def test_A_rypp_pass_out_of_sample_gecer_ve_zincir_live_adayina_kadar_gider():
    s = oos(rypp_kanit())
    assert s.gecti is True and s.gerekce.startswith("RYPP PASS"), s.gerekce
    k = PromotionKaydi(strateji="rypp_aday")
    tam_ilerlet(k, rypp_kanit())
    assert k.asama is Asama.LIVE_ADAYI
    assert k.protokol is Protokol.RYPP
    # elle onay makinece geçilemiyor (K-010): zincir live_adayi'nda duruyor
    assert k.ilerlet(rypp_kanit()).gecti is None and k.asama is Asama.LIVE_ADAYI


@pytest.mark.parametrize("ad", ["fail_maruziyet", "fail_stres", "fail_tek_olay"])
def test_B_rypp_fail_gecmez(ad):
    assert govde(ad)["durum"] == "FAIL"
    s = oos(rypp_kanit(ad))
    assert s.gecti is False and s.gerekce.startswith("RYPP FAIL"), s.gerekce


@pytest.mark.parametrize("ad", ["kisa_oos", "plasebo_yok", "stres_yok"])
def test_C_D_rypp_inconclusive_olculemedi_sayilir(ad):
    """Kısa OOS, plasebo yok, stres yok → INCONCLUSIVE → `None`: ne PASS ne FAIL."""
    assert govde(ad)["durum"] == "INCONCLUSIVE"
    s = oos(rypp_kanit(ad))
    assert s.gecti is None and s.gerekce.startswith("RYPP INCONCLUSIVE"), s.gerekce


def test_C_bootstrap_belirsizligi_inconclusive():
    g = _durum_yeniden(_satir_degistir(govde("pass"), "B_bootstrap", False))
    assert g["durum"] == "INCONCLUSIVE"
    assert oos(rypp_kanit(g)).gecti is None


def test_rypp_degerlendirmesi_yoksa_olculemedi():
    assert oos(rypp_kanit(None)).gecti is None


# ------------------------------------------------------------------ E: B-3 bağımsız doğrulama


def test_E_bagimsiz_dogrulama_yoksa_pass_yok_inconclusive():
    s = oos(rypp_kanit(bag=None))
    assert s.gecti is None and "B-3" in s.gerekce


def test_E_bagimsiz_veride_fail_fail():
    s = oos(rypp_kanit(bag=bagimsiz("fail_maruziyet"), vin=VIN_FAIL()))
    assert s.gecti is False and "bağımsız veride FAIL" in s.gerekce


@pytest.mark.parametrize("ad", ["kisa_oos", "plasebo_yok", "stres_yok"])
def test_E_yetersiz_bagimsiz_veri_yok_sayilir(ad):
    """Çok kısa bir seri vererek B-3 boşa düşürülemez: yetersiz veri = veri yok."""
    assert oos(rypp_kanit(bag=bagimsiz(ad))).gecti is None


def test_E_bagimsiz_veride_yalniz_bootstrap_belirsizligi_fail_degil():
    """K-125 §5: "PASS için bağımsız veride en az FAIL olmamalı". Veri yeterli, nokta
    koşulları geçti, bootstrap belirsiz → FAIL değil → ana PASS korunur."""
    b = _durum_yeniden(_satir_degistir(bagimsiz(), "B_bootstrap", False))
    assert b["durum"] == "INCONCLUSIVE"
    assert oos(rypp_kanit(bag=b)).gecti is True


def test_E_bagimsiz_verinin_kimligi_yoksa_inconclusive():
    assert oos(rypp_kanit(bag=bagimsiz(veri=None))).gecti is None


def test_E_ana_oos_verisi_bagimsiz_sayilmaz():
    with pytest.raises(PromotionHatasi, match="aynı veride"):
        rypp_kanit(bag=bagimsiz(veri=ANA_VERI))


def test_E_bagimsiz_pass_ana_fail_iken_fail():
    assert oos(rypp_kanit("fail_maruziyet")).gecti is False


def test_E_bagimsiz_fail_ana_inconclusive_iken_fail():
    """Üç değerli VE: ölçülmüş bir başarısızlık belirsizliğe baskındır."""
    kanit = rypp_kanit("kisa_oos", bag=bagimsiz("fail_maruziyet"), vin=VIN_FAIL())
    assert oos(kanit).gecti is False


# ------------------------------------------------------------------ F-H: tek tek koşullar


def test_F_bootstrap_satiri_yoksa_pass_yok():
    g = _satir_degistir(govde("pass"), "B_bootstrap", sil=True)
    with pytest.raises(PromotionHatasi, match="tutarsız"):
        rypp_kanit(g)  # durum hâlâ PASS diyor → kanıt kurulmaz
    assert oos(rypp_kanit(_durum_yeniden(g))).gecti is None


def test_G_iki_kat_maliyet_satiri_kalirsa_fail():
    g = _durum_yeniden(_satir_degistir(govde("pass"), "S1_maliyet_stresi", False))
    assert oos(rypp_kanit(g)).gecti is False


@pytest.mark.parametrize("ad", ["R1_baslangic", "R2_alt_donem", "R3_tek_olay"])
def test_H_dayaniklilik_kalirsa_fail(ad):
    g = _durum_yeniden(_satir_degistir(govde("pass"), ad, False))
    assert g["durum"] == "FAIL"
    s = oos(rypp_kanit(g))
    assert s.gecti is False and ad in s.gerekce


# ------------------------------------------------------------------ özellik: eksik kanıt PASS değil


def _pass_mi(**deg: Any) -> bool:
    """Kanıt kurulamıyorsa (hata) ya da `out_of_sample` True değilse PASS yok."""
    try:
        return oos(rypp_kanit(**deg)).gecti is True
    except PromotionHatasi:
        return False


def test_tam_kanit_pass():
    assert _pass_mi()


@pytest.mark.parametrize("ad", sorted(RYPP_KOSULLARI))
@pytest.mark.parametrize("hedef", ["rypp", "bag"])
def test_ozellik_herhangi_bir_satir_kaldirilinca_pass_yok(ad, hedef):
    """Tam kanıttan tek bir koşul satırı (ana ya da bağımsız gövdede) silinir. `durum` ister
    olduğu gibi kalsın (tutarsız → hata) ister dürüstçe yeniden hesaplansın: PASS yok. Bağımsız
    gövdede bootstrap hariç — K-125 §5 orada yalnız "FAIL değil" ister."""
    kaynak = govde("pass") if hedef == "rypp" else bagimsiz()
    silinmis = _satir_degistir(kaynak, ad, sil=True)
    yeniden = _durum_yeniden(silinmis)
    assert _pass_mi(**{hedef: silinmis}) is False, "tutarsız durum kanıt kurmamalı"
    beklenen = hedef == "bag" and ad == "B_bootstrap"
    assert _pass_mi(**{hedef: yeniden}) is beklenen, (hedef, ad, yeniden["durum"])


@pytest.mark.parametrize("ad", sorted(RYPP_KOSULLARI - {"B_bootstrap"}))
@pytest.mark.parametrize("deger", [None, False, 1, "true", "PASS"])
def test_ozellik_true_olmayan_gecti_pass_degil(ad, deger):
    """Yalnız `gecti is True` geçer; `1`, `"true"`, `None` geçmiş sayılmaz."""
    g = _satir_degistir(govde("pass"), ad, deger)
    assert not _pass_mi(rypp=g) and not _pass_mi(rypp=_durum_yeniden(g))


@pytest.mark.parametrize(("ne", "deg"), [
    ("rypp_yok", {"rypp": None}),
    ("plasebo_yok", {"rypp": "plasebo_yok"}),
    ("stres_yok", {"rypp": "stres_yok"}),
    ("oos_kisa", {"rypp": "kisa_oos"}),
    ("bagimsiz_yok", {"bag": None}),
    ("bagimsiz_kimliksiz", {"bag": "_kimliksiz"}),
    ("hipotez_yok", {"hipotez_sirasi": None}),
    ("bootstrap_yok", {"rypp": "_bootstrapsiz"}),
])
def test_ozellik_zorunlu_kanit_kaldirilinca_pass_yok(ne, deg):
    if deg.get("bag") == "_kimliksiz":
        deg = {"bag": bagimsiz(veri=None)}
    if deg.get("rypp") == "_bootstrapsiz":
        deg = {"rypp": _durum_yeniden(_satir_degistir(govde("pass"), "B_bootstrap", sil=True))}
    assert not _pass_mi(**deg), ne


# ------------------------------------------------------------------ L: eksik/bozuk alanlar


@pytest.mark.parametrize("bozma", ["esikler_yok", "durum_yok", "kosullar_yok", "esik_gevsek",
                                   "bilinmeyen_satir", "cift_satir", "durum_yalan"])
def test_L_bozuk_rypp_govdesi_kanit_kurmaz(bozma):
    g = govde("pass")
    if bozma == "esikler_yok":
        del g["esikler"]
    elif bozma == "durum_yok":
        del g["durum"]
    elif bozma == "kosullar_yok":
        del g["kosullar"]
    elif bozma == "esik_gevsek":
        g["esikler"]["asgari_dd_azaltim"]["deger"] = 0.10
    elif bozma == "bilinmeyen_satir":
        g["kosullar"].append({"ad": "oos_sharpe", "gecti": True})
    elif bozma == "cift_satir":
        g["kosullar"].append(copy.deepcopy(g["kosullar"][4]))
    elif bozma == "durum_yalan":
        g = _satir_degistir(g, "P3_plasebo", False)  # satır kaldı, durum hâlâ PASS
    with pytest.raises(PromotionHatasi):
        rypp_kanit(g)


def test_L_bos_kosullar_durum_dogruysa_inconclusive():
    g = govde("pass")
    g["kosullar"], g["durum"] = [], "INCONCLUSIVE"
    assert oos(rypp_kanit(g)).gecti is None


# ------------------------------------------------------------------ I-J: protokol karışması


def test_I_alfa_kaniti_rypp_sonucu_tasiyamaz():
    with pytest.raises(PromotionHatasi, match="protokol karışması"):
        replace(TAM_KANIT, rypp_sonucu=govde("pass"))
    with pytest.raises(PromotionHatasi, match="protokol karışması"):
        replace(TAM_KANIT, bagimsiz_dogrulama=bagimsiz())


def test_I_rypp_kaniti_alfa_kapi_sonucu_tasiyamaz():
    with pytest.raises(PromotionHatasi, match="protokol karışması"):
        rypp_kanit(kapi_sonucu=TAM_KANIT.kapi_sonucu)


def test_I_alfa_kapi_govdesi_rypp_sonucu_gibi_okunmaz():
    """Alfa kapı sonucunu `rypp_sonucu` alanına koymak: eşik yok, koşullar tanınmaz → hata."""
    with pytest.raises(PromotionHatasi):
        rypp_kanit(TAM_KANIT.kapi_sonucu)


def test_I_bilinmeyen_protokol_reddedilir():
    with pytest.raises(PromotionHatasi, match="bilinmeyen"):
        replace(TAM_KANIT, protokol="gevsek")


def test_J_rypp_gecmis_govde_alfa_kapisi_yerine_gecmez():
    """RYPP PASS gövdesini alfa yolunun `kapi_sonucu`na koymak `out_of_sample`ı geçirmez."""
    g = govde("pass")
    sahte = {"gecti": True, "kalan_kapilar": [], "kapilar": {}, **g}
    s = oos(replace(TAM_KANIT, kapi_sonucu=sahte))
    assert s.gecti is False and "K-118" in s.gerekce


def test_I_J_protokol_kilidi_zincir_ortasinda_degistirilemez():
    k = PromotionKaydi(strateji="rypp_aday")
    for _ in range(3):
        k.ilerlet(rypp_kanit())
    assert k.asama is Asama.OUT_OF_SAMPLE and k.protokol is Protokol.RYPP
    with pytest.raises(PromotionHatasi, match="protokol"):
        k.ilerlet(TAM_KANIT)  # alfa kanıtıyla risk incelemesine geçilemez

    a = PromotionKaydi(strateji="alfa_aday")
    for _ in range(3):
        a.ilerlet(TAM_KANIT)
    assert a.asama is Asama.OUT_OF_SAMPLE and a.protokol is Protokol.ALFA
    with pytest.raises(PromotionHatasi, match="protokol"):
        a.ilerlet(rypp_kanit())


def test_elle_onay_protokolu_kayda_dogru_yaziliyor():
    k = PromotionKaydi(strateji="rypp_aday")
    tam_ilerlet(k, rypp_kanit())
    with pytest.raises(PromotionHatasi, match="protokol"):
        k.elle_onayla("yeterince uzun bir gerekçe", kanit=TAM_KANIT)
    k.elle_onayla("yeterince uzun bir gerekçe")
    assert k.asama is Asama.LIVE
    assert {s["kanit"]["protokol"] for s in k.gecmis} == {"rypp"}


# ------------------------------------------------------------------ sistem değişmezleri


@pytest.mark.parametrize(("deg", "asama", "gecti"), [
    ({"dirty": True}, Asama.BACKTEST, False),
    ({"sonuc_hash": None}, Asama.BACKTEST, None),
    ({"mutlak_engeller": ("data_quality_warning",)}, Asama.KALITE_KONTROL, False),
    ({"veri_sha256": None}, Asama.KALITE_KONTROL, None),
    ({"hipotez_sirasi": None}, Asama.OUT_OF_SAMPLE, None),
    ({"risk_limit_kimligi": None}, Asama.RISK_INCELEMESI, None),
    ({"risk_max_drawdown": 0.35}, Asama.RISK_INCELEMESI, False),
    ({"paper_gun": 10.0}, Asama.PAPER, False),
    ({"paper_kesinti": 1}, Asama.PAPER, False),
])
def test_rypp_sistem_degismezlerini_atlamaz(deg, asama, gecti):
    """RYPP yalnız `out_of_sample`ın ölçütünü değiştirir; diğer aşamalar aynen zorlanır."""
    k = PromotionKaydi(strateji="rypp_aday")
    tam_ilerlet(k, rypp_kanit(**deg))
    son = k.gecmis[-1]
    assert son["asama"] == asama and son["gecti"] is gecti, son["gerekce"]
    assert k.asama is not Asama.LIVE_ADAYI


def test_rypp_paper_kaniti_da_yalniz_paper_modundan():
    with pytest.raises(PromotionHatasi, match="K-035"):
        rypp_kanit(paper_mod="gozlem")


# ------------------------------------------------------------------ K: alfa regresyonu


def test_K_varsayilan_protokol_alfa_ve_alfa_zinciri_ayni():
    assert Kanit().protokol is Protokol.ALFA and TAM_KANIT.protokol is Protokol.ALFA
    k = PromotionKaydi(strateji="alfa")
    assert tam_ilerlet(k) == ["backtest", "kalite_kontrol", "out_of_sample",
                              "risk_incelemesi", "paper", "live_adayi"]


def test_K_alfa_kanit_sozlugu_yalniz_protokol_alani_eklendi():
    d = TAM_KANIT.sozluk()
    assert d.pop("protokol") == "alfa"
    assert d == TAM_KANIT._alfa_sozlugu()
    assert not any(a.startswith(("rypp", "bagimsiz")) for a in d)


def test_K_k126_oncesi_satir_alfa_sayilir():
    """Eski satırlarda `protokol` yok; anlamı alfa (kilit ve raporlama için)."""
    k = PromotionKaydi(strateji="eski")
    for _ in range(3):
        k.ilerlet(TAM_KANIT)
    for s in k.gecmis:
        s["kanit"].pop("protokol")
    assert k.protokol is Protokol.ALFA


# ------------------------------------------------------------------ determinizm, hash, audit


def test_ayni_kanit_ayni_sonuc_ve_ayni_kanit_ozeti():
    a, b = rypp_kanit(), rypp_kanit()
    assert oos(a) == oos(b)
    assert a.sozluk() == b.sozluk()
    assert a.sozluk()["rypp_hash"] == b.sozluk()["rypp_hash"]


def test_rypp_satiri_protokol_ve_kanit_hashlerini_tasiyor():
    k = PromotionKaydi(strateji="rypp_aday")
    tam_ilerlet(k, rypp_kanit())
    ozet = next(s for s in k.gecmis if s["asama"] == "out_of_sample")["kanit"]
    assert ozet["protokol"] == "rypp" and ozet["rypp_durum"] == "PASS"
    assert ozet["bagimsiz_durum"] == "PASS" and ozet["bagimsiz_veri_sha256"] == BAGIMSIZ_VERI
    assert len(ozet["rypp_hash"]) == 64 and len(ozet["bagimsiz_hash"]) == 64


def test_rypp_kaniti_degisince_hash_degisir():
    g = govde("pass")
    g["strateji"]["cagr"] += 1e-9
    assert rypp_kanit(g).sozluk()["rypp_hash"] != rypp_kanit().sozluk()["rypp_hash"]


def test_zincir_ve_audit_rypp_satirlarinda_calisiyor(tmp_path):
    defter = PromotionDefteri(tmp_path / "promotion")
    with SqliteDefter(tmp_path / "audit.sqlite") as audit:
        k = defter.oku("rypp_aday", audit=audit)
        tam_ilerlet(k, rypp_kanit())
        defter.yaz(k, audit=audit)
        geri = defter.oku("rypp_aday", audit=audit)  # zincir + audit çapraz kontrol
    assert geri.asama is Asama.LIVE_ADAYI and geri.protokol is Protokol.RYPP
    assert geri.gecmis == k.gecmis

    # Satırdaki protokolü alfa'ya çevirmek zinciri kırar (fail closed)
    ham = json.loads(defter.yol("rypp_aday").read_text(encoding="utf-8"))
    ham["gecmis"][2]["kanit"]["protokol"] = "alfa"
    with pytest.raises(PromotionHatasi, match="hash"):
        PromotionKaydi.yukle(ham)


def test_hukum_fonksiyonlari_saf():
    g, b = govde("pass"), bagimsiz()
    once = (json.dumps(g, sort_keys=True), json.dumps(b, sort_keys=True))
    assert rypp_hukmu(g) == rypp_hukmu(g)
    assert bagimsiz_hukmu(b, ANA_VERI) == bagimsiz_hukmu(b, ANA_VERI)
    assert once == (json.dumps(g, sort_keys=True), json.dumps(b, sort_keys=True))


# ------------------------------------------------------------------ CLI giriş noktası


def test_cli_rypp_kaniti_kurar_ve_karisik_girdiyi_reddeder(tmp_path, monkeypatch):
    import typer

    from scryne_quant.cli.main import _kanit_kur
    from scryne_quant.data import french

    _kayit_kur(tmp_path, monkeypatch, french)
    r, b, v = tmp_path / "rypp.json", tmp_path / "bagimsiz.json", tmp_path / "vintage.json"
    r.write_text(json.dumps(govde("pass")), encoding="utf-8")
    b.write_text(json.dumps({**bagimsiz(), "dataset_id": "test_set"}), encoding="utf-8")
    v.write_text(json.dumps({**bagimsiz("vintage_pass", veri=VINTAGE_VERI),
                             "dataset_id": "test_vintage"}), encoding="utf-8")
    pr = _program_defteri(tmp_path / "program.jsonl", K)
    k = _kanit_kur(None, None, "x", protokol="rypp", rypp_yolu=r, bagimsiz_yolu=b,
                   vintage_yolu=v, program_yolu=pr)
    assert k.protokol is Protokol.RYPP and k.rypp_sonucu["durum"] == "PASS"
    assert k.rypp_aile_sayisi == K and k.bagimsiz_vintage["dataset_id"] == "test_vintage"
    # vintage eşi birincil yerine, birincil vintage yerine kullanılamaz (K-128)
    with pytest.raises(typer.BadParameter, match="rolü"):
        _kanit_kur(None, None, "x", protokol="rypp", bagimsiz_yolu=v)
    with pytest.raises(typer.BadParameter, match="vintage eşi değil"):
        _kanit_kur(None, None, "x", protokol="rypp", bagimsiz_yolu=b, vintage_yolu=b)
    with pytest.raises(typer.BadParameter, match="yalnız --bagimsiz ile"):
        _kanit_kur(None, None, "x", protokol="rypp", vintage_yolu=v)
    assert _kanit_kur(None, None, "x").protokol is Protokol.ALFA

    with pytest.raises(typer.BadParameter):
        _kanit_kur(None, None, "x", rypp_yolu=r)  # alfa + rypp
    with pytest.raises(typer.BadParameter):
        _kanit_kur(None, [r], "x", protokol="rypp", rypp_yolu=r)  # rypp + alfa kapıları
    with pytest.raises(typer.BadParameter):
        _kanit_kur(None, None, "x", protokol="gevsek")


def test_E_bagimsiz_veride_olculmemis_plasebo_fail_degil_sayilmaz():
    """Özellik testinin yakaladığı açık (K-126): bağımsız gövdede P3 hiç ölçülmemişse hüküm
    INCONCLUSIVE'dir ama "FAIL değil" diye geçirilemez — tolere edilen tek belirsizlik bootstrap."""
    b = _durum_yeniden(_satir_degistir(bagimsiz(), "P3_plasebo", sil=True))
    assert b["durum"] == "INCONCLUSIVE"
    s = oos(rypp_kanit(bag=b))
    assert s.gecti is None and "ölçülmemiş" in s.gerekce


# ------------------------------------------------------------------ K-127: P3'ün k'sı


def _program_defteri(yol, butce: int, ad: str = PROGRAM):
    """Açılış satırı `azami_cekilis = butce` olan geçici program defteri (K-128'in k kaynağı)."""
    yol.write_text(json.dumps({"ad": ad, "tur": "acilis", "azami_cekilis": butce},
                              ensure_ascii=False) + "\n", encoding="utf-8")
    return yol


def _kayit_kur(tmp_path, monkeypatch, french):
    """Birincil + vintage eşi, ikisi de `promotion_uygun` geçici bağımsız veri kaydı."""
    kayit = tmp_path / "bagimsiz_veri.json"
    kayit.write_text(json.dumps({"veri_setleri": [
        {"dataset_id": "test_set", "veri_sha256": BAGIMSIZ_VERI, "promotion_uygun": True,
         "rol": "birincil", "vintage_eslesi": "test_vintage"},
        {"dataset_id": "test_vintage", "veri_sha256": VINTAGE_VERI, "promotion_uygun": True,
         "rol": "ikinci_vintage"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(french, "MANIFEST_YOLU", kayit)


def _hipotez_defteri(yol, *, protokol: str = "rypp", program: str = PROGRAM,
                     strateji: str = "x"):
    from scryne_quant.research.hipotez import Hipotez, HipotezDefteri

    d = HipotezDefteri(yol)
    for i in range(1, 3):
        d.kaydet(Hipotez.kur(f"baska{i}", "1d", f"{i:064d}", {"n": [i]},
                             "geçici defter satırı, test için yazıldı"))
    d.kaydet(Hipotez.kur(strateji, "1d", "a" * 64, {"n": [1]},
                         "RYPP adayı, test için yazıldı", protokol=protokol, program=program))
    return yol, d.tumu()[-1]["kimlik"]


def _aile_degistir(g: dict[str, Any], **aile: Any) -> dict[str, Any]:
    g = copy.deepcopy(g)
    g["aile"] = {**g["aile"], **aile}
    return g


def test_k1_kanit_k_tasiyor_promotion_ayni_k_ile_geciyor():
    g = govde("pass")
    assert g["aile"] == {"sayi": K, "program": PROGRAM, "persentil": 1 - 0.05 / K}
    p3 = next(s for s in g["kosullar"] if s["ad"] == "P3_plasebo")
    assert p3["persentil"] == g["aile"]["persentil"]
    kanit = rypp_kanit()
    assert kanit.rypp_aile_sayisi == K and oos(kanit).gecti is True


def test_k2_k_degisince_kanit_hashi_degisiyor():
    """k farklı bir P3 eşiği demek: aynı serilerle k=1 ve k=5 ayrı kanıtlardır."""
    from scryne_quant.common.hash import nesne_hash

    r, rejim = piyasa()
    k1 = _json(rp.degerlendir(girdi(r, _zamanlayici(rejim), k=1, aile_program=PROGRAM)))
    k5 = _json(rp.degerlendir(girdi(r, _zamanlayici(rejim), k=5, aile_program=PROGRAM)))
    assert nesne_hash(k1) != nesne_hash(k5)
    assert k1["aile"]["sayi"] == 1 and k5["aile"]["sayi"] == 5
    a = rypp_kanit(k1).sozluk()["rypp_hash"]
    assert a == rypp_kanit().sozluk()["rypp_hash"]


@pytest.mark.parametrize("disaridan", [2, 7])
def test_k3_promotion_farkli_k_ile_calistirilirsa_hata(disaridan):
    with pytest.raises(PromotionHatasi, match="k'sı uyuşmuyor"):
        rypp_kanit(rypp_aile_sayisi=disaridan)


def test_k4_eksik_k_pass_yok():
    """Kanıtta `aile` yok → kurulmaz; promotion yeniden sayımı yok → ölçülemedi."""
    g = govde("pass")
    del g["aile"]
    with pytest.raises(PromotionHatasi, match="aile"):
        rypp_kanit(g)
    assert oos(rypp_kanit(rypp_aile_sayisi=None)).gecti is None
    with pytest.raises(PromotionHatasi, match="program"):
        rypp_kanit(_aile_degistir(govde("pass"), program=None))


@pytest.mark.parametrize("k", [0, -1, -5])
def test_k5_k6_sifir_ve_negatif_k_reddedilir(k):
    r, rejim = piyasa()
    with pytest.raises(rp.ProtokolHatasi, match="aile_sayisi"):
        rp.degerlendir(girdi(r, _zamanlayici(rejim), k=k))
    with pytest.raises(PromotionHatasi):
        rypp_kanit(_aile_degistir(govde("pass"), sayi=k))
    with pytest.raises(PromotionHatasi):
        rypp_kanit(rypp_aile_sayisi=k)


@pytest.mark.parametrize("k", [1.0, 2.5, "1", True, None, [1]])
def test_k7_yanlis_tipte_k_reddedilir(k):
    r, rejim = piyasa()
    with pytest.raises(rp.ProtokolHatasi, match="aile_sayisi"):
        rp.degerlendir(girdi(r, _zamanlayici(rejim), k=k))
    with pytest.raises(PromotionHatasi):
        rypp_kanit(_aile_degistir(govde("pass"), sayi=k))
    if k is not None:
        with pytest.raises(PromotionHatasi):
            rypp_kanit(rypp_aile_sayisi=k)


def test_k8_arastirmanin_k_si_ile_kanitin_k_si_farkliysa_pass_yok():
    """P3 k=1 ile (gevşek persentil) uygulanmış, kanıt k=5 diyor: araştırma farklı k kullandı."""
    sahte = _aile_degistir(govde("pass"), sayi=5, persentil=1 - 0.05 / 5)
    with pytest.raises(PromotionHatasi, match="P3 persentil"):
        rypp_kanit(sahte, rypp_aile_sayisi=5)
    with pytest.raises(PromotionHatasi, match="persentil"):
        rypp_kanit(_aile_degistir(govde("pass"), persentil=0.9))
    # bağımsız doğrulama başka k ile değerlendirilmiş
    r, rejim = piyasa(tohum=3)
    b5 = _json(rp.degerlendir(girdi(r, _zamanlayici(rejim), k=5, aile_program=PROGRAM)))
    b5["veri_sha256"] = BAGIMSIZ_VERI
    with pytest.raises(PromotionHatasi, match="aynı k"):
        rypp_kanit(bag=b5)


def test_k9_replay_program_butcesinden_ayni_k_ve_ayni_sonuc(tmp_path):
    """Program açılırken bütçe yazılır → araştırma k'yı oradan alır → kanıta donar → promotion
    aynı açılış satırından yeniden okur. Program kapansa da k değişmez (açılışta sabit)."""
    from scryne_quant.cli.main import _kanit_kur, _program_butcesi

    pr = _program_defteri(tmp_path / "program.jsonl", 3)
    arastirma_k = _program_butcesi(PROGRAM, pr)
    assert arastirma_k == 3
    r, rejim = piyasa()
    g = _json(rp.degerlendir(girdi(r, _zamanlayici(rejim), k=arastirma_k, aile_program=PROGRAM)))
    y = tmp_path / "rypp.json"
    y.write_text(json.dumps(g), encoding="utf-8")
    with pr.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ad": PROGRAM, "tur": "kapanis", "harcanan_cekilis": 3}) + "\n")
    k1 = _kanit_kur(None, None, "x", protokol="rypp", rypp_yolu=y, program_yolu=pr)
    k2 = _kanit_kur(None, None, "x", protokol="rypp", rypp_yolu=y, program_yolu=pr)
    assert k1.rypp_aile_sayisi == k2.rypp_aile_sayisi == 3
    assert k1.sozluk() == k2.sozluk()


def test_k_program_butcesi_kanittan_farkliysa_hata(tmp_path):
    from scryne_quant.cli.main import _kanit_kur

    pr = _program_defteri(tmp_path / "program.jsonl", 2)  # bütçe 2, kanıt k=1 diyor
    y = tmp_path / "rypp.json"
    y.write_text(json.dumps(govde("pass")), encoding="utf-8")
    with pytest.raises(PromotionHatasi, match="bütçesi"):
        _kanit_kur(None, None, "x", protokol="rypp", rypp_yolu=y, program_yolu=pr)


def test_k_program_defterde_yoksa_k_dogrulanamaz(tmp_path):
    """Gerçek program defterinde `rypp_test` yok: k okunamaz → `out_of_sample` ölçülemedi."""
    from scryne_quant.cli.main import _kanit_kur

    y = tmp_path / "rypp.json"
    y.write_text(json.dumps(govde("pass")), encoding="utf-8")
    k = _kanit_kur(None, None, "x", protokol="rypp", rypp_yolu=y)
    assert k.rypp_aile_sayisi is None
    assert oos(replace(rypp_kanit(), rypp_aile_sayisi=None)).gecti is None


def test_k_program_iki_kez_acilmissa_hata(tmp_path):
    import typer

    from scryne_quant.cli.main import _program_butcesi

    pr = _program_defteri(tmp_path / "program.jsonl", 2)
    with pr.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ad": PROGRAM, "tur": "acilis", "azami_cekilis": 9}) + "\n")
    with pytest.raises(typer.BadParameter, match="birden çok"):
        _program_butcesi(PROGRAM, pr)


# ------------------------------------------------------------------ K-128: CLI --hipotez


def test_cli_hipotez_sirasini_doldurur_iki_protokolde(tmp_path, monkeypatch):
    """K-128 öncesi CLI `hipotez_sirasi`nı hiç doldurmuyordu: `out_of_sample` CLI'dan hep
    ölçülemedi kalıyordu."""
    from scryne_quant.cli.main import _kanit_kur

    d, kimlik = _hipotez_defteri(tmp_path / "h.jsonl", protokol="", program="")
    k = _kanit_kur(None, None, "x", hipotez_kimlik=kimlik, defter_yolu=d)
    assert (k.hipotez_sirasi, k.hipotez_toplami) == (3, 3)

    d2, kimlik2 = _hipotez_defteri(tmp_path / "h2.jsonl")
    y = tmp_path / "rypp.json"
    y.write_text(json.dumps(govde("pass")), encoding="utf-8")
    k2 = _kanit_kur(None, None, "x", protokol="rypp", rypp_yolu=y, hipotez_kimlik=kimlik2,
                    defter_yolu=d2, program_yolu=_program_defteri(tmp_path / "p.jsonl", K))
    assert k2.hipotez_sirasi == 3 and k2.rypp_aile_sayisi == K


@pytest.mark.parametrize(("ayar", "mesaj"), [
    ({"strateji": "baska"}, "başka bir stratejinin"),
    ({"protokol": ""}, "RYPP protokolüyle"),
    ({"program": "baska_program"}, "programında"),
])
def test_cli_hipotez_tutarsizsa_reddeder(tmp_path, ayar, mesaj):
    import typer

    from scryne_quant.cli.main import _kanit_kur

    d, kimlik = _hipotez_defteri(tmp_path / "h.jsonl", **ayar)
    y = tmp_path / "rypp.json"
    y.write_text(json.dumps(govde("pass")), encoding="utf-8")
    with pytest.raises(typer.BadParameter, match=mesaj):
        _kanit_kur(None, None, "x", protokol="rypp", rypp_yolu=y, hipotez_kimlik=kimlik,
                   defter_yolu=d, program_yolu=_program_defteri(tmp_path / "p.jsonl", K))


def test_cli_bilinmeyen_hipotez_reddedilir(tmp_path):
    import typer

    from scryne_quant.cli.main import _kanit_kur

    d, _ = _hipotez_defteri(tmp_path / "h.jsonl")
    with pytest.raises(typer.BadParameter, match="defterde yok"):
        _kanit_kur(None, None, "x", hipotez_kimlik="f" * 64, defter_yolu=d)


# ------------------------------------------------------------------ K-128: vintage dayanıklılığı


@pytest.mark.parametrize(("bag", "vin", "beklenen"), [
    ("bagimsiz_pass", "vintage_pass", True),        # iki vintage da FAIL değil
    ("fail_maruziyet", "fail_maruziyet", False),    # ikisi de FAIL
    ("bagimsiz_pass", "fail_maruziyet", None),      # ayrışma: revizyona duyarlı
    ("fail_maruziyet", "vintage_pass", None),       # ayrışma: revizyona duyarlı
    ("fail_maruziyet", "kisa_oos", False),          # FAIL + yapılmamış → FAIL
    ("bagimsiz_pass", "kisa_oos", None),            # vintage eşi yetersiz → yapılmamış
    ("bagimsiz_pass", None, None),                  # vintage eşi yok
    (None, "vintage_pass", None),                   # birincil yok
])
def test_K128_vintage_karar_tablosu(bag, vin, beklenen):
    from scryne_quant.risk.promotion import vintage_hukmu

    b = None if bag is None else bagimsiz(bag)
    v = None if vin is None else bagimsiz(vin, veri=VINTAGE_VERI)
    assert vintage_hukmu(b, v, ANA_VERI)[0] is beklenen
    assert oos(rypp_kanit(bag=b, vin=v)).gecti is beklenen


def test_K128_vintage_esi_birincille_ayni_veride_olamaz():
    with pytest.raises(PromotionHatasi, match="aynı veride"):
        rypp_kanit(vin=bagimsiz("vintage_pass", veri=BAGIMSIZ_VERI))


def test_K128_vintage_esi_farkli_k_ile_reddedilir():
    r, rejim = piyasa(tohum=4)
    v5 = _json(rp.degerlendir(girdi(r, _zamanlayici(rejim), k=5, aile_program=PROGRAM)))
    v5["veri_sha256"] = VINTAGE_VERI
    with pytest.raises(PromotionHatasi, match="vintage eşi"):
        rypp_kanit(vin=v5)


def test_K128_alfa_kaniti_vintage_tasiyamaz():
    with pytest.raises(PromotionHatasi, match="protokol karışması"):
        replace(TAM_KANIT, bagimsiz_vintage=bagimsiz("vintage_pass", veri=VINTAGE_VERI))


def test_K128_satir_vintage_kanitini_hashliyor():
    ozet = rypp_kanit().sozluk()
    assert ozet["vintage_durum"] == "PASS" and ozet["vintage_veri_sha256"] == VINTAGE_VERI
    assert len(ozet["vintage_hash"]) == 64


def test_protokol_hipotez_kimligine_girer_bos_iken_eski_kimlik_ayni():
    from scryne_quant.research.hipotez import Hipotez, HipotezHatasi

    ortak = ("s", "1d", "a" * 64, {"n": [1]}, "aynı soru, farklı kabul ölçütü")
    alfa, rypp = Hipotez.kur(*ortak), Hipotez.kur(*ortak, protokol="rypp")
    assert alfa.kimlik != rypp.kimlik
    assert "protokol" not in alfa.sozluk() and rypp.sozluk()["protokol"] == "rypp"
    with pytest.raises(HipotezHatasi):
        Hipotez.kur(*ortak, protokol="alfa_gevsek")


def test_gercek_defterin_kimlikleri_degismedi():
    """`protokol` boşken kimliğe girmez: defterdeki bütün satırların kimliği yeniden üretilir."""
    from scryne_quant.research.hipotez import VARSAYILAN_YOL, Hipotez, HipotezDefteri

    alanlar = ("strateji", "timeframe", "veri_sha256", "izgara", "secim", "gerekce",
               "program", "evren", "portfoy", "rejim", "protokol")
    satirlar = HipotezDefteri(VARSAYILAN_YOL).tumu()
    assert len(satirlar) >= 63
    for satir in satirlar:
        h = Hipotez.kur(**{a: satir.get(a, "") for a in alanlar})
        assert h.kimlik == satir["kimlik"]


# ------------------------------------------------------------------ K-127 §1: B-3 karar tablosu


@pytest.mark.parametrize(("senaryo", "beklenen"), [
    ("yok", None),                        # doğrulama yapılmadı
    ("kimliksiz", None),                  # bağımsızlığı gösterilemiyor
    ("fail", False),                      # ölçüldü ve kaldı
    ("yetersiz", None),                   # yeterlilik sağlanmadı = yapılmamış sayılır
    ("olculmemis_nokta", None),           # bir nokta koşulu ölçülmedi = yapılmamış sayılır
    ("yalniz_bootstrap_belirsiz", True),  # K-125 §5 "FAIL değil" → izin
    ("pass", True),
])
def test_K127_bagimsiz_dogrulama_karar_tablosu(senaryo, beklenen):
    """K-127 §1: K-125 §5'in "PASS için bağımsız veride en az FAIL olmamalı" cümlesinin
    kodlanmış hâli. Bağımsız doğrulama ancak yeterlilik + 8 nokta koşulunun hepsi ölçülüp
    geçtiyse "yapılmış ve FAIL değil" sayılır; tolere edilen tek belirsizlik bootstrap."""
    b = {
        "yok": lambda: None,
        "kimliksiz": lambda: bagimsiz(veri=None),
        "fail": lambda: bagimsiz("fail_maruziyet"),
        "yetersiz": lambda: bagimsiz("kisa_oos"),
        "olculmemis_nokta": lambda: _durum_yeniden(
            _satir_degistir(bagimsiz(), "R2_alt_donem", sil=True)),
        "yalniz_bootstrap_belirsiz": lambda: _durum_yeniden(
            _satir_degistir(bagimsiz(), "B_bootstrap", False)),
        "pass": bagimsiz,
    }[senaryo]()
    hukum, _ = bagimsiz_hukmu(b, ANA_VERI)
    assert hukum is beklenen
    # Vintage eşi (K-128) birincille aynı yönde: FAIL senaryosunda o da FAIL, yoksa geçer.
    vin = VIN_FAIL() if senaryo == "fail" else "vintage_pass"
    assert oos(rypp_kanit(bag=b, vin=vin)).gecti is beklenen
