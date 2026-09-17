"""Evren paper motoru: backtest'le eşitlik, toparlanma, geç bar, ayrışma. (Faz 14)"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.data.izgara import hizala, uyeligi_barlara_kis
from scryne_quant.live.akis import Bar
from scryne_quant.live.canli_evren import AyUyeligi, UyelikTakvimi
from scryne_quant.live.evren_depo import EvrenDepoHatasi, EvrenKosuDeposu
from scryne_quant.live.evren_motor import EvrenPaperMotoru, EvrenToparlanmaAyrismasi
from scryne_quant.live.pencere import BarPenceresi
from scryne_quant.strategy.kosu import evren_gorunum_kur
from scryne_quant.strategy.kutuphane import EvrenEsitAgirlik, KesitselGuc
from tests.conftest import bar_uret

SAAT = 3_600_000
MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
SEMBOLLER = ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT")
N = 900


def _barlar() -> dict[str, list[Bar]]:
    cikti = {}
    for i, s in enumerate(SEMBOLLER):
        df = bar_uret(n=N, tohum=121 + i)
        barlar = [Bar(open_time=int(r.open_time), open=float(r.open), high=float(r.high),
                      low=float(r.low), close=float(r.close), volume=float(r.volume),
                      quote_volume=float(r.quote_volume), trades=int(r.trades))
                  for r in df.itertuples()]
        if s == "DDDUSDT":
            barlar = barlar[400:]         # geç listelenen
        if s == "CCCUSDT":
            barlar = barlar[:850]         # ortada biten
        cikti[s] = barlar
    return cikti


def _uyelik(barlar) -> AyUyeligi:
    t0 = barlar["AAAUSDT"][0].open_time
    ay = str(np.datetime64(t0, "ms").astype("datetime64[M]"))
    return AyUyeligi(ay, SEMBOLLER, "test")


def _strateji(ad="kesitsel"):
    if ad == "kiyas":
        return EvrenEsitAgirlik(yeniden_dengele_bar=24, azami_enstruman=3,
                                azami_agirlik=0.2 / 3, hedef_brut=0.2)
    return KesitselGuc(pencere=24, azami_enstruman=2, yeniden_dengele_bar=12)


def _kurulum(ad="kesitsel", maliyet=MALIYET):
    return dict(strateji=_strateji(ad), maliyet=maliyet, baslangic_sermaye=10_000.0,
                risk=None, timeframe="1h", sifira_yaz_bar=48)


def _izgara(barlar):
    return sorted({b.open_time for bs in barlar.values() for b in bs})


def _takvim_uyumlu(barlar):
    """Test verisi tek bir ay içinde değilse bütün aylar için aynı listeyi yaz."""
    aylar = sorted({str(np.datetime64(t, "ms").astype("datetime64[M]")) for t in _izgara(barlar)})
    return [AyUyeligi(a, SEMBOLLER, "test") for a in aylar]


@pytest.mark.parametrize("ad", ["kesitsel", "kiyas"])
def test_bar_bar_motor_tam_backtestle_ayni(ad):
    barlar = _barlar()
    izgara = np.asarray(_izgara(barlar), dtype="int64")
    isinma = _strateji(ad).isinma_bar()

    # Backtest yolu: aynı doğrulama, aynı hizalama, aynı üyelik — ama tüm seri tek seferde.
    diziler = {}
    for s, bs in barlar.items():
        p = BarPenceresi(s, "1h", kapasite=len(bs))
        p.doldur(bs)
        diziler[s] = hizala(pd.DataFrame(p.diziler()), izgara)
    tk = UyelikTakvimi()
    for u in _takvim_uyumlu(barlar):
        tk.ekle(u)
    uyelik, _ = uyeligi_barlara_kis(tk.dizileri(izgara, diziler), diziler)
    kur = _kurulum(ad)
    beklenen = CokluBacktest(kur["strateji"], MALIYET, sifira_yaz_bar=48).calistir(
        evren_gorunum_kur("1h", diziler, uyelik, kur["strateji"]), olcum_baslangici=isinma
    )

    motor = EvrenPaperMotoru(depo=None, **_kurulum(ad))
    for u in _takvim_uyumlu(barlar):
        motor.uyelik_ekle(u)
    for s, bs in barlar.items():
        for b in bs:
            motor.bar_ekle(s, b)
    ozkaynak = [a.ozkaynak for a in motor.isinma(izgara[:isinma])]
    ozkaynak += [motor.adim(int(t)).ozkaynak for t in izgara[isinma:]]

    # Backtest'in son barı `SONRAKI_BAR_YOK` sayar, canlı saymaz: özkaynak aynı, son bar hariç
    # işlemler aynı.
    assert np.asarray(ozkaynak[isinma:]).tobytes() == beklenen.ozkaynak.tobytes()
    assert [i.sozluk(sembol_yaz=True) for i in motor.adimci.islemler] == [
        i.sozluk(sembol_yaz=True) for i in beklenen.islemler]
    assert beklenen.islemler


ISINMA = 60


def _canli_kos(motor, barlar, adimlar, *, gec=None):
    """Isınma toplu; sonra barlar ait oldukları saatin adımından hemen önce 'gelir'."""
    izgara = _izgara(barlar)
    for u in _takvim_uyumlu(barlar):
        motor.uyelik_ekle(u)
    for s, bs in barlar.items():
        for b in bs:
            if b.open_time < izgara[ISINMA]:
                motor.bar_ekle(s, b)
    motor.isinma(izgara[:ISINMA])
    for j, t in enumerate(izgara[ISINMA:adimlar], start=ISINMA):
        for s, bs in barlar.items():
            for b in bs:
                if b.open_time == t:
                    motor.bar_ekle(s, b)
        if gec is not None and j == gec[0]:
            motor.bar_ekle(gec[1], gec[2])
        motor.adim(t)


def test_toparlanma_ayni_yolu_yeniden_uretir_ve_devam_eder(tmp_path):
    barlar = {s: bs[:260] for s, bs in _barlar().items()}
    # BBB'nin 100. barı akıştan düşmüş, 150. adımda geç geliyor: geçmişi değiştirmemeli.
    kayip = barlar["BBBUSDT"][100]
    barlar_eksik = {s: [b for b in bs if not (s == "BBBUSDT" and b is kayip)]
                    for s, bs in barlar.items()}

    kesintisiz = EvrenPaperMotoru(depo=None, **_kurulum())
    _canli_kos(kesintisiz, barlar_eksik, 200, gec=(150, "BBBUSDT", kayip))

    depo = EvrenKosuDeposu(tmp_path / "e.sqlite")
    depo.kimlik_yaz({"test": 1})
    ilk = EvrenPaperMotoru(depo=depo, **_kurulum())
    _canli_kos(ilk, barlar_eksik, 170, gec=(150, "BBBUSDT", kayip))
    depo.kapat()

    depo2 = EvrenKosuDeposu(tmp_path / "e.sqlite")
    ikinci = EvrenPaperMotoru.toparlan(depo2, **_kurulum())
    assert ikinci.adim_sayisi == 170
    izgara = _izgara(barlar_eksik)
    for t in izgara[170:200]:
        for s, bs in barlar_eksik.items():
            for b in bs:
                if b.open_time == t:
                    ikinci.bar_ekle(s, b)
        ikinci.adim(t)
    assert ikinci.son_sonuc.ozkaynak == kesintisiz.son_sonuc.ozkaynak
    assert [i.sozluk(sembol_yaz=True) for i in ikinci.adimci.islemler] == [
        i.sozluk(sembol_yaz=True) for i in kesintisiz.adimci.islemler]
    depo2.kapat()


def test_farkli_konfigurasyonla_toparlanma_ayrisir(tmp_path):
    barlar = {s: bs[:260] for s, bs in _barlar().items()}
    depo = EvrenKosuDeposu(tmp_path / "e.sqlite")
    motor = EvrenPaperMotoru(depo=depo, **_kurulum())
    _canli_kos(motor, barlar, 120)
    assert motor.adimci.islemler
    depo.kapat()
    depo2 = EvrenKosuDeposu(tmp_path / "e.sqlite")
    with pytest.raises(EvrenToparlanmaAyrismasi):
        EvrenPaperMotoru.toparlan(
            depo2, **_kurulum(maliyet=MaliyetModeli(fee_taker_bps=30.0, slippage_bps=5.0)))
    depo2.kapat()


def test_depo_kimligi_degisemez_ve_kayitlar_degistirilemez(tmp_path):
    depo = EvrenKosuDeposu(tmp_path / "e.sqlite")
    depo.kimlik_yaz({"a": 1})
    depo.kimlik_yaz({"a": 1})
    with pytest.raises(EvrenDepoHatasi):
        depo.kimlik_yaz({"a": 2})
    bar = _barlar()["AAAUSDT"][0]
    assert depo.bar_yaz("AAAUSDT", bar, 0) is True
    assert depo.bar_yaz("AAAUSDT", bar, 3) is False
    import sqlite3

    with pytest.raises(sqlite3.DatabaseError):
        depo._baglanti.execute("UPDATE bar SET close = 0")
    depo.kapat()


def test_izgara_sirasi_atlanamaz():
    barlar = _barlar()
    motor = EvrenPaperMotoru(depo=None, **_kurulum())
    for u in _takvim_uyumlu(barlar):
        motor.uyelik_ekle(u)
    izgara = _izgara(barlar)
    with pytest.raises(Exception, match="ısınma gerekir"):
        motor.adim(izgara[0])
    for s, bs in barlar.items():
        for b in bs[:40]:
            motor.bar_ekle(s, b)
    motor.isinma(izgara[:40])
    with pytest.raises(Exception, match="sırası"):
        motor.adim(izgara[40] + SAAT)


def test_sapma_geciksiz_kosuda_sifir_gec_barda_sebebine_baglanir(tmp_path):
    from scryne_quant.live.evren_sapma import sapma_olc

    barlar = {s: bs[:260] for s, bs in _barlar().items()}
    depo = EvrenKosuDeposu(tmp_path / "temiz.sqlite")
    _canli_kos(EvrenPaperMotoru(depo=depo, **_kurulum()), barlar, 200)
    r = sapma_olc(depo, **_kurulum())
    assert r.ilk_ayrisan_adim is None and r.azami_ozkaynak_farki == 0.0
    assert r.canli_adim == 200 - ISINMA and r.gec_bilinen_bar == 0
    depo.kapat()

    # BBB'nin 100. barı 150. adımda geliyor: 100-149 arası canlı onu görmedi.
    kayip = barlar["BBBUSDT"][100]
    eksik = {s: [b for b in bs if b is not kayip] for s, bs in barlar.items()}
    depo = EvrenKosuDeposu(tmp_path / "gec.sqlite")
    _canli_kos(EvrenPaperMotoru(depo=depo, **_kurulum()), eksik, 200,
               gec=(150, "BBBUSDT", kayip))
    r = sapma_olc(depo, **_kurulum())
    assert r.gec_bilinen_bar == 1
    assert r.ilk_ayrisan_adim is None or r.ilk_ayrisan_adim >= 100
    depo.kapat()


def test_dogrulama_onbellegi_bit_esit():
    """Artımlı doğrulama = her adımda baştan doğrulama; bozuk, boşluklu, geç ve BACKFILL
    barlarla. Karşılaştırma bütün adım sonuçları ve işlemler üzerinde, bit düzeyinde."""
    from dataclasses import replace as dc_replace

    from scryne_quant.live.akis import Kaynak

    barlar = {s: bs[:300] for s, bs in _barlar().items()}
    a = barlar["AAAUSDT"]
    a[150] = dc_replace(a[150], close=a[150].close * 3, high=a[150].close * 3)  # aşırı hareket
    a[151] = dc_replace(a[151], volume=0.0)                                     # sıfır hacim
    barlar["BBBUSDT"] = [b for i, b in enumerate(barlar["BBBUSDT"]) if not 120 <= i < 124]
    barlar["CCCUSDT"] = [dc_replace(b, kaynak=Kaynak.BACKFILL) if i % 7 == 0 else b
                         for i, b in enumerate(barlar["CCCUSDT"])]
    kayip = barlar["AAAUSDT"][200]
    eksik = {s: [b for b in bs if b is not kayip] for s, bs in barlar.items()}

    def kos(onbellek):
        m = EvrenPaperMotoru(depo=None, **_kurulum())
        m.dogrulama_onbellegi = onbellek
        sonuc = []
        izgara = _izgara(eksik)
        for u in _takvim_uyumlu(eksik):
            m.uyelik_ekle(u)
        for s, bs in eksik.items():
            for b in bs:
                if b.open_time < izgara[ISINMA]:
                    m.bar_ekle(s, b)
        sonuc += m.isinma(izgara[:ISINMA])
        for j, t in enumerate(izgara[ISINMA:280], start=ISINMA):
            for s, bs in eksik.items():
                for b in bs:
                    if b.open_time == t:
                        m.bar_ekle(s, b)
            if j == 230:
                m.bar_ekle("AAAUSDT", kayip)  # geç bar: ortaya girer, önbellek geçersiz
            sonuc.append(m.adim(t))
        return sonuc, [i.sozluk(sembol_yaz=True) for i in m.adimci.islemler]

    acik, kapali = kos(True), kos(False)
    assert [(repr(x.ozkaynak), repr(x.brut), x.islem) for x in acik[0]] == [
        (repr(x.ozkaynak), repr(x.brut), x.islem) for x in kapali[0]]
    assert acik[1] == kapali[1] and acik[1]
