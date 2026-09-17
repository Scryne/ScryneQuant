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
