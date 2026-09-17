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


def _turev_verisi(barlar):
    """Sentetik funding (4 s ve 8 s aralık karışık, arada aralık değişimi) ve premium."""
    rng = np.random.default_rng(7)
    izgara = _izgara(barlar)
    funding, premium = {}, {}
    for i, s in enumerate(SEMBOLLER):
        if s == "CCCUSDT":
            continue  # perp'i yok: dizileri NaN kalmalı, dışlanmamalı
        aralik = 4 if i % 2 else 8
        satir, t = [], izgara[0] - 48 * SAAT
        while t <= izgara[-1]:
            if s == "AAAUSDT" and t > izgara[500]:
                aralik = 4
            satir.append((t, aralik, float(rng.normal(1e-4, 3e-4))))
            t += aralik * SAAT
        funding[s] = satir
        premium[s] = [(b.open_time, float(rng.normal(0, 5e-4))) for b in barlar[s]
                      if rng.random() > 0.02]  # arada eksik premium barı
    return funding, premium


def test_turev_motoru_arastirma_yoluyla_ayni():
    from scryne_quant.data import funding as funding_mod
    from scryne_quant.strategy.kutuphane import EVREN_AILELER

    barlar = _barlar()
    funding, premium = _turev_verisi(barlar)
    izgara = np.asarray(_izgara(barlar), dtype="int64")

    def strateji():
        return EVREN_AILELER["evren_funding_basis"](
            yeniden_dengele_bar=24, azami_enstruman=3, hedef_brut=0.2,
            dislama_orani=0.34, pencere=48)

    isinma = strateji().isinma_bar()
    diziler = {}
    for s, bs in barlar.items():
        p = BarPenceresi(s, "1h", kapasite=len(bs))
        p.doldur(bs)
        diziler[s] = hizala(pd.DataFrame(p.diziler()), izgara)
        fdf = (pd.DataFrame(funding[s], columns=["calc_time", "funding_interval_hours",
                                                 "last_funding_rate"])
               if s in funding else pd.DataFrame())
        diziler[s].update(funding_mod.evren_dizileri(izgara, fdf))
        pdf = (pd.DataFrame(premium[s], columns=["open_time", "close"])
               if s in premium else pd.DataFrame())
        diziler[s]["basis"] = funding_mod.evren_premium_dizisi(izgara, pdf)
    tk = UyelikTakvimi()
    for u in _takvim_uyumlu(barlar):
        tk.ekle(u)
    uyelik, _ = uyeligi_barlara_kis(tk.dizileri(izgara, diziler), diziler)
    st = strateji()
    beklenen = CokluBacktest(st, MALIYET, sifira_yaz_bar=48).calistir(
        evren_gorunum_kur("1h", diziler, uyelik, st), olcum_baslangici=isinma)

    motor = EvrenPaperMotoru(depo=None, turev=True, **{**_kurulum(), "strateji": strateji()})
    for u in _takvim_uyumlu(barlar):
        motor.uyelik_ekle(u)

    def besle(bas, bit):
        for s, bs in barlar.items():
            for b in bs:
                if bas <= b.open_time <= bit:
                    motor.bar_ekle(s, b)
        for s, satir in funding.items():
            for t, a, o in satir:
                if t <= bit:
                    motor.funding_ekle(s, t, a, o)
        for s, satir in premium.items():
            for t, c in satir:
                if bas <= t <= bit:
                    motor.premium_ekle(s, t, c)

    besle(int(izgara[0]), int(izgara[isinma - 1]))
    ozkaynak = [a.ozkaynak for a in motor.isinma(izgara[:isinma])]
    for t in izgara[isinma:]:
        besle(int(t), int(t))
        ozkaynak.append(motor.adim(int(t)).ozkaynak)
    assert np.asarray(ozkaynak[isinma:]).tobytes() == beklenen.ozkaynak.tobytes()
    assert [i.sozluk(sembol_yaz=True) for i in motor.adimci.islemler] == [
        i.sozluk(sembol_yaz=True) for i in beklenen.islemler]
    assert beklenen.islemler

    # Dışlama gerçekten bir şey değiştiriyor mu (test boş geçmesin): kıyasla farklı olmalı.
    kiyas = CokluBacktest(_strateji("kiyas").__class__(
        yeniden_dengele_bar=24, azami_enstruman=3, azami_agirlik=0.2 / 3, hedef_brut=0.2),
        MALIYET, sifira_yaz_bar=48).calistir(
        evren_gorunum_kur("1h", diziler, uyelik, _strateji("kiyas")), olcum_baslangici=isinma)
    assert kiyas.ozkaynak.tobytes() != beklenen.ozkaynak.tobytes()


def test_turev_toparlanma_ve_sapma(tmp_path):
    from scryne_quant.live.evren_sapma import sapma_olc
    from scryne_quant.strategy.kutuphane import EVREN_AILELER

    barlar = {s: bs[:820] for s, bs in _barlar().items()}
    funding, premium = _turev_verisi(barlar)

    def kurulum():
        return {**_kurulum(), "turev": True, "strateji": EVREN_AILELER["evren_funding_basis"](
            yeniden_dengele_bar=12, azami_enstruman=3, hedef_brut=0.2,
            dislama_orani=0.34, pencere=24)}

    isinma = kurulum()["strateji"].isinma_bar()
    depo = EvrenKosuDeposu(tmp_path / "t.sqlite")
    m = EvrenPaperMotoru(depo=depo, **kurulum())
    izgara = _izgara(barlar)
    for u in _takvim_uyumlu(barlar):
        m.uyelik_ekle(u)
    for s, bs in barlar.items():
        for b in bs:
            if b.open_time < izgara[isinma]:
                m.bar_ekle(s, b)
    for s, satir in funding.items():
        for t, a, o in satir:
            if t < izgara[isinma]:
                m.funding_ekle(s, t, a, o)
    m.isinma(izgara[:isinma])
    for j, t in enumerate(izgara[isinma:isinma + 60], start=isinma):
        for s, bs in barlar.items():
            for b in bs:
                if b.open_time == t:
                    m.bar_ekle(s, b)
        for s, satir in funding.items():
            for ft, a, o in satir:
                if ft == t:
                    m.funding_ekle(s, ft, a, o)
        for s, satir in premium.items():
            for pt, c in satir:
                # premium'un bir kısmı bir adım geç geliyor
                if pt == t or (pt == t - SAAT and j % 5 == 0):
                    m.premium_ekle(s, pt, c)
        m.adim(t)
    depo.kapat()
    depo = EvrenKosuDeposu(tmp_path / "t.sqlite")
    m2 = EvrenPaperMotoru.toparlan(depo, **kurulum())
    assert m2.son_sonuc.ozkaynak == m.son_sonuc.ozkaynak
    r = sapma_olc(depo, **kurulum())
    assert r.canli_adim == 60
    assert m.adimci.islemler
    depo.kapat()


def test_makro_motoru_arastirma_yoluyla_ayni(tmp_path):
    """Günlük PIT değerleri gün gün gelir (d günü, d+1'in ilk adımından önce), bir gün sonradan
    revize edilir; motor = aynı `gunlukten_alanlar` ile kurulan backtest, bit düzeyinde.
    Revizyon yalnızca bilindiği adımdan sonra etkiler: referans (son değer) ile canlı
    arasında fark ancak o günden sonra doğabilir."""
    from scryne_quant.data import makro as makro_mod
    from scryne_quant.strategy.kutuphane import EVREN_AILELER

    GUN = 86_400_000
    barlar = _barlar()
    izgara = np.asarray(_izgara(barlar), dtype="int64")
    gunler = makro_mod.gunluk_gerekli(izgara)
    rng = np.random.default_rng(3)
    deger = {int(g): float(v) for g, v in zip(gunler, np.cumsum(rng.normal(0, 1, len(gunler))),
                                               strict=True)}

    def strateji():
        return EVREN_AILELER["evren_makro_nfci"](pencere_gun=30, esik=0.6, azami_enstruman=3,
                                                 yeniden_dengele_bar=24, hedef_brut=0.2)

    isinma = strateji().isinma_bar()
    diziler = {}
    for s, bs in barlar.items():
        p = BarPenceresi(s, "1h", kapasite=len(bs))
        p.doldur(bs)
        diziler[s] = hizala(pd.DataFrame(p.diziler()), izgara)
    alanlar = makro_mod.gunlukten_alanlar(
        izgara, {"nfci": lambda gs: np.array([deger.get(int(g), np.nan) for g in gs])})
    for dz in diziler.values():
        dz.update(alanlar)
    tk = UyelikTakvimi()
    for u in _takvim_uyumlu(barlar):
        tk.ekle(u)
    uyelik, _ = uyeligi_barlara_kis(tk.dizileri(izgara, diziler), diziler)
    st = strateji()
    beklenen = CokluBacktest(st, MALIYET, sifira_yaz_bar=48).calistir(
        evren_gorunum_kur("1h", diziler, uyelik, st), olcum_baslangici=isinma)
    assert st.stres_dengeleme > 0  # engel gerçekten devreye giriyor

    depo = EvrenKosuDeposu(tmp_path / "m.sqlite")
    motor = EvrenPaperMotoru(depo=depo, makro=("nfci",), **{**_kurulum(), "strateji": strateji()})
    for u in _takvim_uyumlu(barlar):
        motor.uyelik_ekle(u)
    for s, bs in barlar.items():
        for b in bs:
            if b.open_time <= izgara[isinma - 1]:
                motor.bar_ekle(s, b)
    for g, v in deger.items():
        if g <= izgara[isinma - 1] // GUN - 1:
            motor.makro_ekle("nfci", g, v)
    ozkaynak = [a.ozkaynak for a in motor.isinma(izgara[:isinma])]
    for t in izgara[isinma:]:
        for s, bs in barlar.items():
            for b in bs:
                if b.open_time == t:
                    motor.bar_ekle(s, b)
        g = int(t) // GUN - 1
        if motor.son_makro_gunu("nfci") < g:
            motor.makro_ekle("nfci", g, deger[g])
        ozkaynak.append(motor.adim(int(t)).ozkaynak)
    assert np.asarray(ozkaynak[isinma:]).tobytes() == beklenen.ozkaynak.tobytes()
    assert [i.sozluk(sembol_yaz=True) for i in motor.adimci.islemler] == [
        i.sozluk(sembol_yaz=True) for i in beklenen.islemler]
    depo.kapat()

    depo = EvrenKosuDeposu(tmp_path / "m.sqlite")
    kur = {**_kurulum(), "strateji": strateji(), "makro": ("nfci",)}
    assert EvrenPaperMotoru.toparlan(depo, **kur).son_sonuc.ozkaynak == ozkaynak[-1]
    depo.kapat()
