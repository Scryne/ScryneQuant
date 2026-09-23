"""B-3 bağımsız doğrulama veri yolu (K-127): kimlik, kilit, bütünlük, PIT işareti, bağımsızlık.

Strateji koşulmaz, getiri istatistiği hesaplanmaz. Ölçülenler:

- Kanonik kimlik deterministik; tek bir değer değişince değişiyor; float ayrıştırmasına bağlı değil.
- Şema, tarih (sıra/tekrar/geçersiz/hafta sonu), eksik değer kodu, sayı biçimi, iki dosyanın aynı
  günleri taşıması, pencerenin kaynakta tam bitmesi → aksi `FrenchHatasi`.
- `yukle` her parçayı manifestle karşılaştırır (zip/CSV hash, üye adı, şema, satır, ilk gün,
  kanonik hash); `indir` farklı vintage'ı kilitli dosyanın yerine yazmaz.
- Manifest dondurulmuş (test sabitleri) ve set `promotion_uygun: false` (PIT revizyon koşulu).
- Promotion yalnız kayıtlı ve uygun bir setin kanıtını kabul eder (CLI).
- Gerçek veri varsa (gitignore; CI'da yok) yeniden üretim ve defterle çakışmasızlık.
"""

from __future__ import annotations

import copy
import io
import json
import zipfile
from pathlib import Path
from typing import Final

import pytest

from scryne_quant.data import french as fr

GERCEK_KOK: Final = Path("data/bagimsiz/french")

# ------------------------------------------------------------ dondurulmuş manifest (çift kilit)

SET: Final = "french_12ind_vw_gunluk_202607"
VERI_SHA: Final = "2448dddc19747d1138675c461b214279e27beda8a4e2867e43ff51be1c21dbc1"
VINTAGE_SET: Final = "french_12ind_vw_gunluk_201705"
VINTAGE_SHA: Final = "10256f9182bf8155d187c969b92da9a9c960329252a934b5fbe412c1ed5ad0b5"
VINTAGE_ZIPLER: Final = {
    "12_Industry_Portfolios_Daily_CSV.zip":
        "44d2e5856a534ccc81170501d76ff1f567fc07d50dd0ea95f882eac58fa195f7",
    "F-F_Research_Data_Factors_daily_CSV.zip":
        "f929700fe922f9937f0e0b8273382d8451a56f0b049ff108de8cb8d9dde94add",
}
ZIPLER: Final = {
    "12_Industry_Portfolios_Daily_CSV.zip":
        "ff4f0b6c4bd6fe13950f9cd80adbf474de6040f9b4fe254ecfaad6a3dcdbf1c3",
    "F-F_Research_Data_Factors_daily_CSV.zip":
        "1916d331c2c51d2aee3d00215897d2b8e5995cb387f1f4569ba46bff5fb049a8",
}


def test_manifest_dondurulmus_ve_vintage_sartiyla_uygun():
    """Pencere/kaynak/şema/hash değiştirilerek doğrulama yeniden seçilemez: değişiklik bu testi
    kırar ve yeni bir K ister (K-127 §5). K-128: PIT değil ama vintage eşiyle uygun."""
    m = fr.manifest_oku(SET)
    assert m["veri_sha256"] == VERI_SHA
    assert {a: d["zip_sha256"] for a, d in m["kaynak"]["dosyalar"].items()} == ZIPLER
    assert m["donem"]["baslangic"] == "2004-06-01" and m["donem"]["bitis"] == "2026-07-31"
    assert m["satir"] == 5577 and m["ilk_islem_gunu"] == "2004-06-01"
    assert m["sema"]["sutunlar"] == list(fr.KANONIK_SUTUNLAR)
    assert m["pit"]["sonuc"].startswith("PIT değil")
    assert m["promotion_uygun"] is True and m["rol"] == "birincil"
    assert m["vintage_eslesi"] == VINTAGE_SET and "K-128" in m["kabul"]
    v = fr.manifest_oku(VINTAGE_SET)
    assert v["veri_sha256"] == VINTAGE_SHA and v["rol"] == "ikinci_vintage"
    assert v["donem"]["baslangic"] == "2004-06-01" and v["donem"]["bitis"] == "2017-05-31"
    assert v["satir"] == 3273
    assert {a: d["zip_sha256"] for a, d in v["kaynak"]["dosyalar"].items()} == VINTAGE_ZIPLER
    assert [x["dataset_id"] for x in fr.veri_setleri()] == [SET, VINTAGE_SET]


# ------------------------------------------------------------------ sentetik kaynak dosyalar

GUNLER: Final = ["20040528", "20040601", "20040602", "20040603", "20040604", "20040607"]


def _sektor_csv(gunler=GUNLER, *, deger="0.10", sutunlar=fr.SEKTORLER, degis=None) -> str:
    bas = ("This file was created using the 202607 CRSP database.\n"
           "Missing data are indicated by -99.99 or -999.\n\n\n")
    def bolum(ad):
        satirlar = [f"  {ad}", "," + ",".join(sutunlar)]
        for g in gunler:
            hucre = [deger] * len(sutunlar)
            if degis and g in degis:
                hucre[0] = degis[g]
            satirlar.append(g + "," + ",".join(f"{h:>8}" for h in hucre))
        return "\n".join(satirlar) + "\n\n\n"
    return (bas + bolum(fr.VW_BOLUMU) + bolum("Average Equal Weighted Returns -- Daily")
            + "Copyright 2026 Eugene F. Fama and Kenneth R. French\n").replace("\n", "\r\n")


def _faktor_csv(gunler=GUNLER) -> str:
    satirlar = ["This file was created by using the 202607 CRSP database.",
                "The Tbill return is the simple daily rate.", "",
                "," + ",".join(fr.FAKTORLER)]
    satirlar += [f"{g},    0.05,   -0.01,    0.02,    0.01" for g in gunler]
    return "\r\n".join([*satirlar, "", "Copyright 2026"]) + "\r\n"


def _zip(ad: str, metin: str, *, ek: bool = False) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(ad, metin.encode("latin-1"))
        if ek:
            z.writestr("fazla.txt", b"x")
    return b.getvalue()


def _kaynak(**deg):
    s = _zip("12_Industry_Portfolios_Daily.csv", _sektor_csv(**deg))
    f = _zip("F-F_Research_Data_Factors_daily.csv", _faktor_csv())
    return s, f


def _satirlar(s, f, bitis=20040607):
    return fr.kanonik_satirlar(s, f, baslangic=20040601, bitis=bitis)


def test_kanonik_pencere_ve_sutunlar():
    s = _satirlar(*_kaynak())
    assert [r[0] for r in s] == GUNLER[1:]
    assert all(len(r) == len(fr.KANONIK_SUTUNLAR) for r in s)
    assert s[0][-2:] == ["0.05", "0.01"]  # Mkt-RF ve RF; SMB/HML girmez
    assert fr.kanonik_metin(s).splitlines()[0] == b",".join(
        c.encode() for c in fr.KANONIK_SUTUNLAR)


def test_hash_deterministik_ve_degisiklige_duyarli():
    a = fr.veri_sha256(_satirlar(*_kaynak()))
    assert a == fr.veri_sha256(_satirlar(*_kaynak()))
    assert a != fr.veri_sha256(_satirlar(*_kaynak(degis={"20040603": "0.11"})))
    # Pencere dışındaki değişiklik kimliği etkilemez
    assert a == fr.veri_sha256(_satirlar(*_kaynak(degis={"20040528": "9.99"})))


def test_hash_ondalik_metinden_float_esitligi_yetmez():
    """0.10 ile 0.1 aynı float ama farklı kaynak metni: kimlik kaynak metnini tutar."""
    assert fr.veri_sha256(_satirlar(*_kaynak(deger="0.10"))) != fr.veri_sha256(
        _satirlar(*_kaynak(deger="0.1")))


@pytest.mark.parametrize(("bozma", "mesaj"), [
    ({"gunler": [*GUNLER[:3], GUNLER[2], *GUNLER[3:]]}, "tekrar"),
    ({"gunler": [GUNLER[0], GUNLER[2], GUNLER[1], *GUNLER[3:]]}, "sıra"),
    ({"gunler": [*GUNLER[:3], "20040605", *GUNLER[3:]]}, "hafta sonu"),
    ({"gunler": [*GUNLER, "20040631"]}, "geçersiz"),
    ({"degis": {"20040602": "-99.99"}}, "eksik değer"),
    ({"degis": {"20040602": "-999"}}, "eksik değer"),
    ({"degis": {"20040602": "abc"}}, "sayı olmayan"),
    ({"sutunlar": ("NoDur", "Durbl", "Manuf", "Enrgy", "Chems", "BusEq", "Telcm", "Utils",
                   "Shops", "Hlth", "Money", "Diger")}, "şema"),
])
def test_bozuk_kaynak_reddedilir(bozma, mesaj):
    s = _zip("12_Industry_Portfolios_Daily.csv", _sektor_csv(**bozma))
    f = _zip("F-F_Research_Data_Factors_daily.csv", _faktor_csv())
    with pytest.raises(fr.FrenchHatasi, match=mesaj):
        _satirlar(s, f)


def test_iki_dosya_ayni_gunleri_tasimali():
    s = _zip("12_Industry_Portfolios_Daily.csv", _sektor_csv())
    f = _zip("F-F_Research_Data_Factors_daily.csv", _faktor_csv(GUNLER[:-2] + GUNLER[-1:]))
    with pytest.raises(fr.FrenchHatasi, match="aynı işlem günlerini"):
        _satirlar(s, f)


def test_pencere_kaynakta_tam_bitmeli():
    with pytest.raises(fr.FrenchHatasi, match="bitmiyor"):
        _satirlar(*_kaynak(), bitis=20040608)


def test_zip_tek_uye_tasimali():
    with pytest.raises(fr.FrenchHatasi, match="tek dosya"):
        fr.zip_icerigi(_zip("a.csv", "x", ek=True))


# ------------------------------------------------------------------ yukle: kilit


def _manifest_ve_kok(tmp_path, s, f):
    ham = tmp_path / "ham"
    ham.mkdir()
    (ham / fr.SEKTOR_ZIP).write_bytes(s)
    (ham / fr.FAKTOR_ZIP).write_bytes(f)
    satir = _satirlar(s, f)
    m = copy.deepcopy(fr.manifest_oku(SET))
    for ad, b in ((fr.SEKTOR_ZIP, s), (fr.FAKTOR_ZIP, f)):
        uye, csv = fr.zip_icerigi(b)
        m["kaynak"]["dosyalar"][ad] = {"zip_sha256": fr.sha256(b), "csv": uye,
                                       "csv_sha256": fr.sha256(csv)}
    m["donem"] = {"baslangic": "2004-06-01", "bitis": "2004-06-07"}
    m["ilk_islem_gunu"], m["satir"] = "2004-06-01", len(satir)
    m["veri_sha256"] = fr.veri_sha256(satir)
    return m, tmp_path


def test_yukle_kimligi_yeniden_uretiyor_ve_iki_kez_ayni(tmp_path):
    m, kok = _manifest_ve_kok(tmp_path, *_kaynak())
    a, b = fr.yukle(kok, m), fr.yukle(kok, m)
    assert a.satirlar == b.satirlar and a.kimlik() == b.kimlik()
    assert a.kimlik()["veri_sha256"] == m["veri_sha256"]
    df = a.cerceve()
    assert list(df.columns) == list(fr.KANONIK_SUTUNLAR)
    assert df.index.name == "zaman_ms" and df.index.is_monotonic_increasing
    assert int(df.index[0]) == 1086048000000  # 2004-06-01 00:00 UTC (K-005: açılış)
    assert not df.isna().any().any()


@pytest.mark.parametrize("bozma", ["zip", "csv_uye", "satir", "ilk_gun", "veri_sha", "sema",
                                   "donem_bitis"])
def test_yukle_manifestle_uyusmayan_her_parcada_durur(tmp_path, bozma):
    m, kok = _manifest_ve_kok(tmp_path, *_kaynak())
    d = m["kaynak"]["dosyalar"][fr.SEKTOR_ZIP]
    if bozma == "zip":
        d["zip_sha256"] = "0" * 64
    elif bozma == "csv_uye":
        d["csv"] = "baska.csv"
    elif bozma == "satir":
        m["satir"] += 1
    elif bozma == "ilk_gun":
        m["ilk_islem_gunu"] = "2004-06-02"
    elif bozma == "veri_sha":
        m["veri_sha256"] = "f" * 64
    elif bozma == "sema":
        m["sema"]["sutunlar"] = m["sema"]["sutunlar"][:-1]
    elif bozma == "donem_bitis":
        m["donem"]["bitis"] = "2004-06-04"  # pencereyi kısaltmak veriyi değiştirir
    with pytest.raises(fr.FrenchHatasi):
        fr.yukle(kok, m)


def test_yukle_degismis_ham_dosyayi_reddeder(tmp_path):
    m, kok = _manifest_ve_kok(tmp_path, *_kaynak())
    s2, _ = _kaynak(degis={"20040603": "0.11"})
    (kok / "ham" / fr.SEKTOR_ZIP).write_bytes(s2)
    with pytest.raises(fr.FrenchHatasi, match="vintage"):
        fr.yukle(kok, m)


def test_yukle_dosya_yoksa_durur(tmp_path):
    m, kok = _manifest_ve_kok(tmp_path, *_kaynak())
    (kok / "ham" / fr.FAKTOR_ZIP).unlink()
    with pytest.raises(fr.FrenchHatasi, match="yok"):
        fr.yukle(kok, m)


def test_indir_farkli_vintage_kilitli_dosyanin_yerine_yazilmaz(tmp_path, monkeypatch):
    import requests

    s, f = _kaynak()
    m, kok = _manifest_ve_kok(tmp_path, s, f)
    yeni, _ = _kaynak(degis={"20040603": "0.12"})

    class Yanit:
        def __init__(self, b):
            self.content = b

        def raise_for_status(self):
            return None

    monkeypatch.setattr(requests, "get", lambda url, timeout: Yanit(
        yeni if url.endswith(fr.SEKTOR_ZIP) else f))
    with pytest.raises(fr.FrenchHatasi, match="vintage değişmiş"):
        fr.indir(kok, m)
    assert (kok / "ham" / fr.SEKTOR_ZIP).read_bytes() == s
    assert (kok / "ham" / f"{fr.SEKTOR_ZIP}.yeni").read_bytes() == yeni
    fr.yukle(kok, m)  # kilitli veri hâlâ geçerli


# ------------------------------------------------------------------ revizyon ve bağımsızlık


def test_revizyon_olc_hucre_farklarini_sayar():
    eski, _ = _kaynak()
    yeni, _ = _kaynak(degis={"20040602": "0.30", "20040603": "0.11"})
    r = fr.revizyon_olc(eski, yeni, baslangic=20040601)
    assert r["gun"] == 5 and r["hucre"] == 60
    assert r["degisen_oran"] == pytest.approx(2 / 60)
    assert r["bp10_ustu_oran"] == pytest.approx(1 / 60)
    assert r["azami_fark_yuzde_puan"] == pytest.approx(0.20)


def test_bagimsizlik_denetimi_defterdeki_carpismayi_bulur():
    m = fr.manifest_oku(SET)
    temiz = [{"kimlik": "a", "veri_sha256": "x" * 64}]
    assert fr.bagimsizlik_denetimi(temiz, m)["bagimsiz"] is True
    kirli = [*temiz, {"kimlik": "b", "veri_sha256": VERI_SHA}]
    assert fr.bagimsizlik_denetimi(kirli, m) == {
        "defter_satiri": 2, "carpisan_cekilis": ["b"], "bagimsiz": False}
    ham = [{"kimlik": "c", "veri_sha256": next(iter(ZIPLER.values()))}]
    assert fr.bagimsizlik_denetimi(ham, m)["bagimsiz"] is False


def test_gercek_defterde_bu_veriyle_cekilis_yok():
    from scryne_quant.research.hipotez import HipotezDefteri

    d = fr.bagimsizlik_denetimi(HipotezDefteri().tumu(), fr.manifest_oku(SET))
    assert d["bagimsiz"] is True and d["defter_satiri"] >= 63


# ------------------------------------------------------------------ promotion kilidi


def test_promotion_kaydi_rol_ve_kimlik_ister():
    assert fr.promotion_icin_kayit(VERI_SHA, SET)["dataset_id"] == SET
    assert fr.promotion_icin_kayit(VINTAGE_SHA, VINTAGE_SET, rol="ikinci_vintage")
    with pytest.raises(fr.FrenchHatasi, match="rolü"):
        fr.promotion_icin_kayit(VINTAGE_SHA, VINTAGE_SET)  # vintage eşi birincil olamaz
    with pytest.raises(fr.FrenchHatasi, match="rolü"):
        fr.promotion_icin_kayit(VERI_SHA, SET, rol="ikinci_vintage")
    with pytest.raises(fr.FrenchHatasi, match="kayıtlı"):
        fr.promotion_icin_kayit("b" * 64, SET)
    with pytest.raises(fr.FrenchHatasi, match="kayıtlı"):
        fr.promotion_icin_kayit(VERI_SHA, "baska_set")


def test_uygun_olmayan_isaretli_set_reddedilir(tmp_path, monkeypatch):
    kayit = json.loads(fr.MANIFEST_YOLU.read_text(encoding="utf-8"))
    kayit["veri_setleri"][0]["promotion_uygun"] = False
    kayit["veri_setleri"][0]["engel"] = "test"
    y = tmp_path / "bagimsiz_veri.json"
    y.write_text(json.dumps(kayit), encoding="utf-8")
    monkeypatch.setattr(fr, "MANIFEST_YOLU", y)
    with pytest.raises(fr.FrenchHatasi, match="uygun değil"):
        fr.promotion_icin_kayit(VERI_SHA, SET)


def test_cli_kayitsiz_ya_da_yanlis_rollu_bagimsiz_kaniti_reddeder(tmp_path):
    import typer

    from scryne_quant.cli.main import _kanit_kur

    b = tmp_path / "bagimsiz.json"
    b.write_text(json.dumps({"dataset_id": VINTAGE_SET, "veri_sha256": VINTAGE_SHA}),
                 encoding="utf-8")
    with pytest.raises(typer.BadParameter, match="rolü"):
        _kanit_kur(None, None, "x", protokol="rypp", bagimsiz_yolu=b)
    b.write_text(json.dumps({"veri_sha256": "b" * 64}), encoding="utf-8")
    with pytest.raises(typer.BadParameter, match="kayıtlı"):
        _kanit_kur(None, None, "x", protokol="rypp", bagimsiz_yolu=b)


# ------------------------------------------------------------------ gerçek veri (varsa)

gercek = pytest.mark.skipif(
    not (GERCEK_KOK / "ham" / fr.SEKTOR_ZIP).is_file(),
    reason="bağımsız veri indirilmemiş (data/ gitignore; `sq data bagimsiz-indir`)",
)


@gercek
def test_gercek_veri_kimligi_yeniden_uretiliyor():
    a, b = fr.yukle(GERCEK_KOK), fr.yukle(GERCEK_KOK)
    assert a.veri_sha256 == b.veri_sha256 == VERI_SHA
    assert len(a.satirlar) == 5577
    assert a.satirlar[0][0] == "20040601" and a.satirlar[-1][0] == "20260731"
    assert a.kimlik() == {"dataset_id": SET, "kaynak": fr.manifest_oku(SET)["kaynak"]["ad"],
                          "period_start": "2004-06-01", "period_end": "2026-07-31",
                          "veri_sha256": VERI_SHA}


gercek_vintage = pytest.mark.skipif(
    not (Path("data/bagimsiz/french_201707/ham") / fr.SEKTOR_ZIP).is_file(),
    reason="vintage eşi indirilmemiş (`sq data bagimsiz-indir french_12ind_vw_gunluk_201705`)",
)


@gercek_vintage
def test_gercek_vintage_esi_kimligi_yeniden_uretiliyor():
    v = fr.yukle(manifest=fr.manifest_oku(VINTAGE_SET))
    assert v.veri_sha256 == VINTAGE_SHA and len(v.satirlar) == 3273
    assert v.satirlar[-1][0] == "20170531"
