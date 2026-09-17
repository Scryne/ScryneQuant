"""Evren koşucusu uçtan uca: ısınma, akış, toparlanma, boşluk tamamlama. (Faz 14)

Ağ yok: REST, akış ve saat sahte. Bar verisi tek bir sentetik tablodan gelir; REST ve akış
aynı barları verir, böylece "kapalıyken kaçırılan saatler REST'ten tamamlanınca koşu aynı
yoldan devam eder" iddiası sınanabilir.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd

from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.live.akis import Bar, Kaynak
from scryne_quant.live.evren_depo import EvrenKosuDeposu
from scryne_quant.live.evren_kosturucu import EvrenKosucu, EvrenTablosu, kos
from scryne_quant.strategy.kutuphane import KesitselGuc
from tests.conftest import bar_uret

SAAT = 3_600_000
SEMBOLLER = ("AAAUSDT", "BBBUSDT", "CCCUSDT")
N = 400
T0 = int(bar_uret(n=1)["open_time"].iloc[0])


def _veri() -> dict[str, pd.DataFrame]:
    return {s: bar_uret(n=N, tohum=301 + i) for i, s in enumerate(SEMBOLLER)}


VERI = _veri()


class SahteRest:
    def __init__(self):
        self.cagri = 0

    def klines(self, sembol, timeframe, bas, bit):
        self.cagri += 1
        df = VERI[sembol]
        return df[(df.open_time >= bas) & (df.open_time < bit)].head(1000).drop(
            columns=["quality_status"], errors="ignore").reset_index(drop=True)


class SahteAkis:
    """`[bas, bit)` saatlerindeki barları sırayla verir, sonra bekler."""

    def __init__(self, semboller, bas, bit):
        self.semboller, self.bas, self.bit = semboller, bas, bit
        self.kapali = False

    def kapat(self):
        self.kapali = True

    async def barlar(self):
        for t in range(self.bas, self.bit, SAAT):
            for s in self.semboller:
                r = VERI[s][VERI[s].open_time == t].iloc[0]
                yield s, Bar(open_time=t, open=r.open, high=r.high, low=r.low, close=r.close,
                             volume=r.volume, quote_volume=r.quote_volume, trades=int(r.trades),
                             kaynak=Kaynak.AKIS)
            await asyncio.sleep(0)
        while not self.kapali:
            await asyncio.sleep(0)


class Saat:
    def __init__(self, ms):
        self.ms = ms

    def __call__(self):
        return self.ms


def _tablo():
    aylar = sorted({str(np.datetime64(int(t), "ms").astype("datetime64[M]"))
                    for t in VERI["AAAUSDT"].open_time})
    satirlar = [{"ay": a, "sira": j + 1, "kanonik_id": s, "sembol": s,
                 "onceki_ay_quote_hacim": 1.0} for a in aylar for j, s in enumerate(SEMBOLLER)]
    return EvrenTablosu(pd.DataFrame(satirlar), "test-hash")


def _kosucu(yol, saat, akis_bas, akis_bit, rest):
    kurulum = dict(strateji=KesitselGuc(pencere=24, azami_enstruman=2, yeniden_dengele_bar=6),
                   maliyet=MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0),
                   baslangic_sermaye=10_000.0, risk=None, timeframe="1h", sifira_yaz_bar=48)
    return EvrenKosucu(
        kosu_yolu=yol, kimlik={"test": 1}, kurulum=kurulum, tablo=_tablo(), rest=rest,
        akis_fabrikasi=lambda semboller, son: SahteAkis(semboller, akis_bas, akis_bit),
        saat=saat, bekleme_ms=60_000, gunluk=lambda _: None,
    )


def test_uctan_uca_isinma_akis_toparlanma_bosluk(tmp_path):
    yol = tmp_path / "evren-1.sqlite"
    # Şimdi = 200. barın açılışı + 30 dk: kapanmış son bar 199.
    saat = Saat(T0 + 200 * SAAT + 30 * 60_000)
    rest = SahteRest()
    k1 = _kosucu(yol, saat, T0 + 200 * SAAT, T0 + 203 * SAAT, rest)

    async def ilerleyen_uyku(_):
        saat.ms += 10 * 60_000
        await asyncio.sleep(0)

    asyncio.run(kos(k1, uyku=ilerleyen_uyku, azami_adim=3))
    isinma = KesitselGuc(pencere=24, azami_enstruman=2, yeniden_dengele_bar=6).isinma_bar() + 48
    assert k1.motor.adim_sayisi == isinma + 3
    assert k1.motor.son_bar_ms == T0 + 202 * SAAT
    assert yol.with_suffix(".sqlite.durum.json").exists()
    assert not yol.with_suffix(".sqlite.pid").exists()  # kapanışta silindi

    # Kapalıyken 2 saat geçti (203, 204 kapandı): yeniden başlatma toparlanır + REST'ten tamamlar.
    saat.ms = T0 + 205 * SAAT + 5 * 60_000
    k2 = _kosucu(yol, saat, T0 + 205 * SAAT, T0 + 206 * SAAT, rest)
    motor = k2.baslat()
    assert motor.adim_sayisi == isinma + 3
    assert motor.son_sonuc.ozkaynak == k1.motor.son_sonuc.ozkaynak  # yeniden üretildi
    assert k2.bosluk_tamamla(motor) == 2
    assert motor.son_bar_ms == T0 + 204 * SAAT

    depo = k2.depo
    turler = [o["tur"] for o in depo.olaylar()]
    assert {"isinma", "durdu", "toparlandi", "bosluk_tamamlandi"} <= set(turler)
    depo.kapat()

    # Üçüncü açılış: bütün adımlar (boşluk dahil) yeniden üretilebiliyor.
    depo3 = EvrenKosuDeposu(yol)
    from scryne_quant.live.evren_motor import EvrenPaperMotoru

    m3 = EvrenPaperMotoru.toparlan(depo3, **k2.kurulum)
    assert m3.adim_sayisi == isinma + 5
    depo3.kapat()


def test_tablo_yenileme_ayni_kural_yeni_ay(tmp_path):
    import json
    import os

    tablo = _tablo()
    yol = tmp_path / "evren.parquet"
    tablo.tablo.iloc[:3].to_parquet(yol)
    yol.with_suffix(".json").write_text(json.dumps({"tablo_hash": "h1", "kural_kimlik": "k"}))
    t = EvrenTablosu.oku(yol)
    assert t.yenile() is False
    tablo.tablo.to_parquet(yol)
    yol.with_suffix(".json").write_text(json.dumps({"tablo_hash": "h2", "kural_kimlik": "k"}))
    os.utime(yol, (1, t._mtime + 10))
    assert t.yenile() is True
    assert t.tablo_hash == "h2" and len(t.tablo) == len(tablo.tablo)
    yol.with_suffix(".json").write_text(json.dumps({"tablo_hash": "h3", "kural_kimlik": "baska"}))
    os.utime(yol, (1, t._mtime + 20))
    import pytest

    with pytest.raises(ValueError, match="kuralı"):
        t.yenile()


def test_ay_donumunde_yeni_uye_gecmisle_eklenir(tmp_path):
    """Kasım: AAA, BBB. Aralık: + CCC. CCC canlıda hiç izlenmemişti; geçmişi REST'ten dolmalı."""
    from scryne_quant.live.evren_motor import EvrenPaperMotoru

    aralik = int(pd.Timestamp("2023-12-01", tz="UTC").timestamp() * 1000)
    j = (aralik - T0) // SAAT
    satirlar = [{"ay": "2023-11", "sira": i + 1, "kanonik_id": s, "sembol": s,
                 "onceki_ay_quote_hacim": 1.0} for i, s in enumerate(SEMBOLLER[:2])]
    satirlar += [{"ay": "2023-12", "sira": i + 1, "kanonik_id": s, "sembol": s,
                  "onceki_ay_quote_hacim": 1.0} for i, s in enumerate(SEMBOLLER)]
    yol = tmp_path / "evren-2.sqlite"
    saat = Saat(T0 + (j - 3) * SAAT + 30 * 60_000)
    k = _kosucu(yol, saat, T0 + (j - 3) * SAAT, T0 + (j + 3) * SAAT, SahteRest())
    k.tablo = EvrenTablosu(pd.DataFrame(satirlar), "h")

    async def ilerleyen_uyku(_):
        saat.ms += 10 * 60_000
        await asyncio.sleep(0)

    asyncio.run(kos(k, uyku=ilerleyen_uyku, azami_adim=6))
    m = k.motor
    assert m.son_bar_ms == T0 + (j + 2) * SAAT
    isinma = k.kurulum["strateji"].isinma_bar() + 48
    ccc = sorted(m._g.barlar["CCCUSDT"])
    assert ccc[0] == aralik - isinma * SAAT and ccc[-1] == T0 + (j + 2) * SAAT
    assert len(ccc) == isinma + 3
    depo = EvrenKosuDeposu(yol)
    turler = [o["tur"] for o in depo.olaylar()]
    assert {"yeni_uye_gecmisi", "abonelik_degisti"} <= set(turler)
    m2 = EvrenPaperMotoru.toparlan(depo, **k.kurulum)
    assert m2.son_sonuc.ozkaynak == m.son_sonuc.ozkaynak
    depo.kapat()


class SahteTurev:
    """8 saatte bir funding (CCC'nin perp'i yok), her saat premium; kapanmamış bar verilmez."""

    def __init__(self):
        self.cagri = 0

    def araliklar(self):
        return {"BBBUSDT": 4}

    def funding(self, sembol, bas):
        self.cagri += 1
        if sembol == "CCCUSDT":
            return []
        adim = 4 if sembol == "BBBUSDT" else 8
        t0 = (T0 // (adim * SAAT)) * adim * SAAT - 48 * SAAT
        return [(t, 1e-4 * ((t // SAAT) % 7 - 3)) for t in range(t0, T0 + N * SAAT, adim * SAAT)
                if t >= bas]

    def premium(self, sembol, bas, bit, simdi):
        return [(t, 1e-5 * ((t // SAAT) % 11 - 5)) for t in range(bas, bit, SAAT)
                if T0 <= t < T0 + N * SAAT and t + SAAT <= simdi]


def test_turev_girdileri_toplanir_ve_yeniden_uretilir(tmp_path):
    from scryne_quant.live.evren_motor import EvrenPaperMotoru
    from scryne_quant.live.evren_sapma import sapma_olc

    yol = tmp_path / "turev.sqlite"
    saat = Saat(T0 + 200 * SAAT + 30 * 60_000)
    k = _kosucu(yol, saat, T0 + 200 * SAAT, T0 + 204 * SAAT, SahteRest())
    k.kurulum["turev"] = True
    k.turev = SahteTurev()

    async def ilerleyen_uyku(_):
        saat.ms += 10 * 60_000
        await asyncio.sleep(0)

    asyncio.run(kos(k, uyku=ilerleyen_uyku, azami_adim=4))
    depo = EvrenKosuDeposu(yol)
    f = depo.fundingler()
    p = depo.premiumlar()
    assert {s for s, *_ in f} == {"AAAUSDT", "BBBUSDT"}
    assert {a for s, _, a, _, _ in f if s == "BBBUSDT"} == {4}
    # Premium: ısınma başından son işlenen bara kadar her saat, sembol başına, boşluksuz.
    son = k.motor.son_bar_ms
    for s in SEMBOLLER:
        zamanlar = sorted(t for s_, t, _, _ in p if s_ == s)
        assert zamanlar[-1] == son and len(zamanlar) == (son - zamanlar[0]) // SAAT + 1
    # Canlıda gelen premium, adımından önce biliniyordu: geç bilinen yok.
    adim_no = {a.open_time: a.adim for a in depo.adimlar()}
    assert all(b <= adim_no[t] for _, t, _, b in p if t in adim_no and not
               depo.adimlar()[adim_no[t]].isinma)
    m2 = EvrenPaperMotoru.toparlan(depo, **k.kurulum)
    assert m2.son_sonuc.ozkaynak == k.motor.son_sonuc.ozkaynak
    r = sapma_olc(depo, **k.kurulum)
    assert r.ilk_ayrisan_adim is None
    depo.kapat()


class SahteMakro:
    def __init__(self):
        self.istekler = []

    def gunluk(self, kisa, gunler):
        self.istekler.append((kisa, int(gunler[0]), int(gunler[-1])))
        return np.array([float((g % 13) - 6) for g in gunler])


def test_makro_girdileri_toplanir_ve_yeniden_uretilir(tmp_path):
    from scryne_quant.data import makro as makro_mod
    from scryne_quant.live.evren_motor import EvrenPaperMotoru

    yol = tmp_path / "makro.sqlite"
    saat = Saat(T0 + 200 * SAAT + 30 * 60_000)
    k = _kosucu(yol, saat, T0 + 200 * SAAT, T0 + 230 * SAAT, SahteRest())
    k.kurulum["makro"] = ("nfci",)
    k.makro = SahteMakro()

    async def ilerleyen_uyku(_):
        saat.ms += 10 * 60_000
        await asyncio.sleep(0)

    asyncio.run(kos(k, uyku=ilerleyen_uyku, azami_adim=30))
    m = k.motor
    gun = 86_400_000
    ilk_bar = int(min(m._izgara))
    # Isınma: persentil geçmişinin tamamı; sonra her gün bir önceki gün eklenmiş.
    assert min(m._g.makro["nfci"]) == int(makro_mod.gunluk_gerekli(np.array([ilk_bar]))[0])
    assert m.son_makro_gunu("nfci") == m.son_bar_ms // gun - 1
    depo = EvrenKosuDeposu(yol)
    assert EvrenPaperMotoru.toparlan(depo, **k.kurulum).son_sonuc.ozkaynak == m.son_sonuc.ozkaynak
    depo.kapat()
