"""Gözlem panosu: salt okunurluk, keşif ve işlem defterinin doğru sayılması. (Faz 14)

Bu testlerin varlık sebebi tek bir cümle: **pano bir okuyucudur.** Koşu dosyasına yazan,
koşuyu bekleten ya da aynı işlemi iki kez gösteren bir pano, bakanı yanıltır — ve bu
projede yanıltan ekran, olmayan ekrandan tehlikelidir.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from scryne_quant.backtest.metrikler import Islem
from scryne_quant.live.depo import KosuDeposu, KosuKimligi
from scryne_quant.live.evren_depo import EvrenKosuDeposu, KayitliAdim
from scryne_quant.live.evren_pano import PanoKaynagi, _seyrelt, pano_kur
from scryne_quant.portfolio.durum import CokluPortfoy, Pozisyon

SAAT = 3_600_000
T0 = 1_789_000_000_000


def _evren_kosu(kok, ad="evren-x", adim_sayisi=5):
    """Küçük ama gerçek bir evren koşu dosyası: kimlik + ısınma + canlı adımlar."""
    depo = EvrenKosuDeposu(kok / f"{ad}.sqlite")
    depo.kimlik_yaz(
        {
            "strateji": {"ad": "evren_esit_agirlik", "parametreler": {"azami_enstruman": 10}},
            "baslangic_sermaye": 10_000.0,
            "timeframe": "1h",
        }
    )
    depo.uyelik_yaz("2026-09", ("AAAUSDT", "BBBUSDT"), "hash", 0)
    for i in range(adim_sayisi):
        depo.adim_yaz(
            KayitliAdim(
                adim=i,
                open_time=T0 + i * SAAT,
                isinma=i < 2,
                eksik=(),
                ozkaynak=10_000.0 + i,
                brut=0.1 * i,
                islem=i,
            )
        )
    depo.olay_yaz("basladi", bar_ms=T0, ayrinti={"a": 1})
    depo.kapat()
    return kok / f"{ad}.sqlite"


def _tek_kosu(kok, ad="tek-x"):
    """Tek sembollü koşu dosyası — `durum.json` **yazmaz**, tıpkı `host-1` gibi."""
    depo = KosuDeposu(kok / f"{ad}.sqlite")
    depo.kosu_yaz(
        KosuKimligi(
            kosu_adi=ad,
            mod="gozlem",
            sembol="BTCUSDT",
            timeframe="1h",
            strateji={"ad": "ema_kesisim", "parametreler": {"hizli": 20}},
            maliyet={},
            limitler={},
            limit_kimligi="x",
            baslangic_sermaye=10_000.0,
            commit_sha="abc",
            dirty=False,
            kutuphaneler={},
            olusturuldu_ms=T0,
        )
    )
    depo.kapat()
    return kok / f"{ad}.sqlite"


def _sha(yol) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


# --------------------------------------------------------------------- keşif


def test_kosular_hem_evreni_hem_tek_sembolluyu_buluyor(tmp_path):
    kok = tmp_path / "paper"
    kok.mkdir()
    _evren_kosu(kok)
    _tek_kosu(kok)

    kaynak = PanoKaynagi(kok, tmp_path / "izleme", onbellek_s=0.0)
    govde = kaynak.kosular()
    turler = {k["ad"]: k["tur"] for k in govde["kosular"]}
    assert turler == {"evren-x": "evren", "tek-x": "tek"}
    assert govde["izleme"]["var"] is False  # izleme hiç koşmadıysa "yok" der, uydurmaz


def test_durum_json_yoksa_son_adim_kosu_dosyasindan_okunuyor(tmp_path):
    """`host-1` durum.json yazmıyor; yedek yol olmasaydı satır boş görünürdü."""
    kok = tmp_path / "paper"
    kok.mkdir()
    _evren_kosu(kok, adim_sayisi=5)
    kaynak = PanoKaynagi(kok, tmp_path / "izleme", onbellek_s=0.0)

    satir = kaynak.kosular()["kosular"][0]
    assert satir["adim"] == 4
    assert satir["ozkaynak"] == pytest.approx(10_004.0)
    assert satir["getiri"] == pytest.approx(0.0004)


def test_durum_json_varsa_o_kazaniyor(tmp_path):
    kok = tmp_path / "paper"
    kok.mkdir()
    yol = _evren_kosu(kok)
    (kok / f"{yol.name}.durum.json").write_text(
        json.dumps({"adim": 99, "ozkaynak": 12_345.0, "pozisyonlar": ["AAAUSDT"]}),
        encoding="utf-8",
    )
    kaynak = PanoKaynagi(kok, tmp_path / "izleme", onbellek_s=0.0)
    satir = kaynak.kosular()["kosular"][0]
    assert satir["adim"] == 99
    assert satir["pozisyon_sayisi"] == 1


def test_izleme_yazildi_ms_dosya_mtimeindan_geliyor(tmp_path):
    """`durum.json` bu alanı **taşımıyor**; türetilmezse arayüz "izleme bayat" der.

    Bu, kontrol dakikası dakikasına koşarken kırmızı şerit basan sahte bir alarmdı —
    ve sahte alarm, alarmsızlıktan kötüdür: bakanı kırmızıyı yok saymaya alıştırır.
    """
    izleme_kok = tmp_path / "izleme"
    izleme_kok.mkdir()
    (izleme_kok / "durum.json").write_text(
        json.dumps({"zaman": "2026-09-18 18:00:00 UTC", "alarmlar": [], "kosular": []}),
        encoding="utf-8",
    )
    kaynak = PanoKaynagi(tmp_path / "paper", izleme_kok, onbellek_s=0.0)

    govde = kaynak.izleme()

    assert govde["var"] is True
    assert isinstance(govde["yazildi_ms"], int)
    assert govde["yazildi_ms"] > 0
    # Liste ucu da aynı alanı taşımalı: arayüzün bayatlık kararı buradan okunuyor.
    assert isinstance(kaynak.kosular()["izleme"]["yazildi_ms"], int)


def test_izleme_yoksa_bayat_degil_yok_diyor(tmp_path):
    kaynak = PanoKaynagi(tmp_path / "paper", tmp_path / "izleme", onbellek_s=0.0)
    govde = kaynak.izleme()
    assert govde["var"] is False
    assert "simdi_ms" in govde


def test_izleme_kosularina_son_sapma_ekleniyor(tmp_path):
    """Model boyutu (canlı-backtest sapması) panoda da görünebilsin diye."""
    paper = tmp_path / "paper"
    paper.mkdir()
    izleme_kok = tmp_path / "izleme"
    izleme_kok.mkdir()
    (izleme_kok / "durum.json").write_text(
        json.dumps({"alarmlar": [], "kosular": [{"kosu": "evren-x", "surec_yasiyor": True}]}),
        encoding="utf-8",
    )
    (paper / "evren-x.sapma.jsonl").write_text(
        json.dumps({"adim": 5, "son_ozkaynak_farki_bps": 0.0}) + "\n"
        + json.dumps({"adim": 9, "son_ozkaynak_farki_bps": 0.0}) + "\n",
        encoding="utf-8",
    )
    kaynak = PanoKaynagi(paper, izleme_kok, onbellek_s=0.0)

    kosu = kaynak.izleme()["kosular"][0]

    assert kosu["sapma"]["adim"] == 9  # **son** ölçüm


# ------------------------------------------------------------- salt okunurluk


def test_okuma_kosu_dosyasini_degistirmiyor(tmp_path):
    """Pano bir okuyucudur: bayt düzeyinde tek bir değişiklik bile kabul edilemez."""
    kok = tmp_path / "paper"
    kok.mkdir()
    evren = _evren_kosu(kok)
    tek = _tek_kosu(kok)
    onceki = {evren: _sha(evren), tek: _sha(tek)}

    kaynak = PanoKaynagi(kok, tmp_path / "izleme", onbellek_s=0.0)
    kaynak.kosular()
    kaynak.detay("evren-x")
    kaynak.detay("tek-x")

    assert {y: _sha(y) for y in onceki} == onceki


def test_yalnizca_get_uclari_var(tmp_path):
    """Yazan bir uç yanlışlıkla eklenirse bu test düşer: pano durum değiştiremez."""
    kok = tmp_path / "paper"
    kok.mkdir()
    _evren_kosu(kok)
    app = pano_kur(PanoKaynagi(kok, tmp_path / "izleme"))
    yollar = [
        (r.path, sorted(r.methods - {"HEAD"}))
        for r in app.routes
        if getattr(r, "methods", None)
    ]
    assert all(m == ["GET"] for _, m in yollar), yollar


def test_bilinmeyen_kosu_404(tmp_path):
    kok = tmp_path / "paper"
    kok.mkdir()
    istemci = TestClient(pano_kur(PanoKaynagi(kok, tmp_path / "izleme")))
    assert istemci.get("/api/kosu/yok-boyle").status_code == 404
    assert istemci.get("/api/kosu/yok-boyle/uretim").status_code == 404


def test_uclar_veriyi_dondururyor(tmp_path):
    kok = tmp_path / "paper"
    kok.mkdir()
    _evren_kosu(kok)
    istemci = TestClient(pano_kur(PanoKaynagi(kok, tmp_path / "izleme", onbellek_s=0.0)))

    liste = istemci.get("/api/kosular").json()
    assert [k["ad"] for k in liste["kosular"]] == ["evren-x"]

    detay = istemci.get("/api/kosu/evren-x").json()
    # Isınma adımları seriye girmez: grafiğin sıfır çizgisi koşunun başlangıcıdır.
    assert [n["adim"] for n in detay["seri"]] == [2, 3, 4]
    assert detay["isinma_adim"] == 2
    assert detay["uyelik"] == [{"ay": "2026-09", "sembol_sayisi": 2}]
    assert [o["tur"] for o in detay["olaylar"]] == ["basladi"]


# ------------------------------------------------------- işlem defteri sayımı


def _motor_taklidi(islemler, pozisyonlar, fiyatlar, ozkaynak=10_000.0):
    acik = {i.sembol: i for i in islemler if i.kapanis_ms is None}
    adimci = SimpleNamespace(
        islemler=islemler,
        acik=acik,
        portfoy=CokluPortfoy(nakit=1_000.0, pozisyonlar=pozisyonlar),
        son_kapanis=fiyatlar,
    )
    return SimpleNamespace(
        adimci=adimci,
        son_sonuc=SimpleNamespace(ozkaynak=ozkaynak),
        adim_sayisi=len(islemler),
    )


def test_acik_islem_iki_kez_sayilmiyor():
    """`adimci.islemler` açık turu **zaten** içeriyor; `acik` aynı nesneye bakan görünüm.

    İkisini birleştiren ilk sürüm 8 işlemi 16 gösteriyordu — sayıyı iki katına çıkaran bir
    ekran, işlem defteri olarak okunamaz.
    """
    kapali = Islem(acilis_ms=T0, kapanis_ms=T0 + SAAT, sembol="AAAUSDT", net_pnl=5.0,
                   giris_notional=100.0, giris_miktar=1.0, fill_sayisi=2)
    acik = Islem(acilis_ms=T0 + SAAT, sembol="BBBUSDT", giris_notional=200.0,
                 giris_miktar=2.0, fill_sayisi=1)
    motor = _motor_taklidi([kapali, acik], {}, {})

    uretim = PanoKaynagi._portfoyden(motor)

    assert len(uretim.islemler) == 2
    assert [i["sembol"] for i in uretim.islemler] == ["AAAUSDT", "BBBUSDT"]
    assert [i["acik"] for i in uretim.islemler] == [False, True]


def test_pozisyon_agirligi_ve_gerceklesmemis_pnl_hesaplaniyor():
    poz = {"AAAUSDT": Pozisyon(miktar=2.0, ortalama_maliyet=100.0, giris_ms=T0)}
    motor = _motor_taklidi([], poz, {"AAAUSDT": 110.0}, ozkaynak=1_000.0)

    p = PanoKaynagi._portfoyden(motor).pozisyonlar[0]

    assert p["deger"] == pytest.approx(220.0)
    assert p["maliyet"] == pytest.approx(200.0)
    assert p["gerceklesmemis_pnl"] == pytest.approx(20.0)
    assert p["getiri"] == pytest.approx(0.1)
    assert p["agirlik"] == pytest.approx(0.22)


def test_fiyati_bilinmeyen_pozisyon_sifir_degil_bilinmiyor():
    """Son fiyat yoksa değer **uydurulmaz** (K-024): `null` döner, arayüz '—' gösterir."""
    poz = {"AAAUSDT": Pozisyon(miktar=2.0, ortalama_maliyet=100.0, giris_ms=T0)}
    motor = _motor_taklidi([], poz, {})

    p = PanoKaynagi._portfoyden(motor).pozisyonlar[0]

    assert p["son_fiyat"] is None
    assert p["deger"] is None
    assert p["agirlik"] is None
    assert p["gerceklesmemis_pnl"] is None


# --------------------------------------------------------------- seyreltme


def test_seyreltme_son_noktayi_koruyor():
    seri = [{"ms": i, "ozkaynak": float(i)} for i in range(1000)]
    cikti = _seyrelt(seri, 100)
    assert len(cikti) == 100
    assert cikti[0] == seri[0]
    assert cikti[-1] == seri[-1]  # sağ uç gerçek son değer olmalı


def test_seyreltme_kucuk_seriye_dokunmuyor():
    seri = [{"ms": i, "ozkaynak": float(i)} for i in range(10)]
    assert _seyrelt(seri, 100) is seri


# ----------------------------------------------------------- üretim hataları


def test_kimlik_uyusmazliginda_uretim_hata_veriyor_kosu_durmuyor(tmp_path):
    """Yeniden üretim kurulamıyorsa ekran hatayı gösterir; boş tablo göstermez."""
    kok = tmp_path / "paper"
    kok.mkdir()
    depo = EvrenKosuDeposu(kok / "bozuk.sqlite")
    depo.kimlik_yaz({"strateji": {"ad": "boyle-bir-strateji-yok", "parametreler": {}},
                     "baslangic_sermaye": 10_000.0})
    depo.kapat()

    kaynak = PanoKaynagi(kok, tmp_path / "izleme", onbellek_s=0.0)
    sonuc = kaynak._yeniden_uret("bozuk")

    assert sonuc.durum == "hata"
    assert "strateji" in (sonuc.hata or "")


def test_anlik_kopya_kaynagi_kilitlemiyor(tmp_path):
    """Kopya alınırken koşu yazmaya devam edebilmeli — okuyucu yazarı bekletemez."""
    kok = tmp_path / "paper"
    kok.mkdir()
    yol = _evren_kosu(kok)
    yazar = sqlite3.connect(yol)
    try:
        yazar.execute("PRAGMA journal_mode = WAL")
        kaynak = PanoKaynagi(kok, tmp_path / "izleme", onbellek_s=0.0)
        kaynak.detay("evren-x")
        # Kopya alındıktan sonra yazar hâlâ yazabiliyor olmalı.
        yazar.execute(
            "INSERT INTO olay (tur, zaman_ms, bar_ms, ayrinti) VALUES ('x', 1, NULL, '{}')"
        )
        yazar.commit()
    finally:
        yazar.close()
