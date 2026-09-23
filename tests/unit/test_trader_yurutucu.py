"""Yürütücü: strateji → risk → execution hattı, tekrar oynatmayla uçtan uca. (K-114)

Ölçülen iddialar:
- PAPER koşusu uçtan uca geçer: emir dolar, mutabakat temiz, rapor `gecti`.
- Fill fiyatı sinyal barının **sonraki** açılışı × (1 ± slippage) (K-004, K-007).
- Determinizm: aynı girdi aynı emir kimliklerini ve aynı hesabı verir (K-009).
- Toparlanma: koşu ortada kesilip yeniden kurulduğunda sonuç kesintisiz koşuyla aynı (K-038).
- Kimlik değişikliğiyle aynı koşu adı başlatılamaz.
"""

from __future__ import annotations

import pytest

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.exchange.akis import df_barlara
from scryne_quant.exchange.kurallar import SembolKurallari
from scryne_quant.exchange.paper_adaptoru import PaperBorsa, PaperMaliyet
from scryne_quant.execution.hat import ExecutionHatti, GuvenlikLimitleri
from scryne_quant.execution.mod import CalismaModu
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.risk import limitler as lm
from scryne_quant.risk.audit import SqliteDefter
from scryne_quant.risk.motor import RiskMotoru
from scryne_quant.strategy.kutuphane.sma_kesisim import SmaKesisim
from scryne_quant.trader.yurutucu import (
    ListeBarKaynagi,
    Yurutucu,
    YurutucuAyari,
    YurutucuHatasi,
)
from tests.conftest import bar_uret

K = SembolKurallari("BTCUSDT", 0.01, 0.00001, 5.0, "TRADING", "BTC", "USDT")
MALIYET = PaperMaliyet(10.0, 5.0)
PARAM = {"hizli": 5, "yavas": 20, "maruziyet": 0.2}


def kur(dizin, barlar, *, param=PARAM, sermaye=10_000.0):
    kaynak = ListeBarKaynagi(barlar, "1h")
    dizin.mkdir(parents=True, exist_ok=True)
    paper = PaperBorsa(kurallar={"BTCUSDT": K}, maliyet=MALIYET, saat=kaynak.sunucu_zamani_ms,
                       yol=dizin / "paper_borsa.sqlite", acilis_bakiyesi={"USDT": sermaye})
    lim = lm.yukle()
    audit = SqliteDefter(dizin / "audit.sqlite")
    hat = ExecutionHatti(mod=CalismaModu.PAPER, adaptor=paper,
                         defter=EmirDefteri(dizin / "emirler.sqlite"),
                         limitler=GuvenlikLimitleri.risk_limitlerinden(lim, sermaye),
                         sembol="BTCUSDT", kosu_dizini=dizin, audit=audit,
                         saat=kaynak.sunucu_zamani_ms)
    risk = RiskMotoru(lim, "1h", mod="gozlem", defter=audit)
    st = SmaKesisim(**param)
    ayar = YurutucuAyari("t", CalismaModu.PAPER, "gozlem", "sma_kesisim", st.parametreler,
                         "BTCUSDT", "1h", sermaye, dizin)
    y = Yurutucu(ayar=ayar, strateji=st, risk=risk, hat=hat, kaynak=kaynak, paper=paper,
                 saat=kaynak.sunucu_zamani_ms)
    return y, kaynak


@pytest.fixture(scope="module")
def barlar():
    return df_barlara(bar_uret(n=500))


def test_paper_uctan_uca_gecer_ve_fill_sonraki_acilista(tmp_path, barlar):
    y, k = kur(tmp_path / "a", barlar)
    r = y.tekrar_oynat(k, isinma=100)
    assert r["gecti"], r["kalan"]
    assert r["dolan_emir"] > 0 and r["pozisyon_farki"] == 0
    acilis = {b.open_time: b.open for b in barlar}
    adim = timeframe_ms("1h")
    for e in (x for x in y.hat.defter.tumu() if x.dolan_miktar > 0):
        beklenen = acilis[e.karar_ms + adim] * (1 + 5e-4 if e.yon == "BUY" else 1 - 5e-4)
        assert e.ortalama_fiyat == pytest.approx(beklenen, rel=1e-12)
    assert SqliteDefter(tmp_path / "a" / "audit.sqlite").dogrula()


def test_determinizm(tmp_path, barlar):
    y1, k1 = kur(tmp_path / "a", barlar)
    y2, k2 = kur(tmp_path / "b", barlar)
    r1, r2 = y1.tekrar_oynat(k1, isinma=100), y2.tekrar_oynat(k2, isinma=100)
    assert [e.istemci_kimligi for e in y1.hat.defter.tumu()] == [
        e.istemci_kimligi for e in y2.hat.defter.tumu()
    ]
    assert r1["hesap"]["ozkaynak"] == r2["hesap"]["ozkaynak"]


def test_toparlanma_kesintisiz_kosuyla_ayni(tmp_path, barlar):
    tam, kt = kur(tmp_path / "tam", barlar)
    beklenen = tam.tekrar_oynat(kt, isinma=100)

    # Kesintili: 100 ısınma + 150 bar, süreç "ölür", yeni kurulum aynı dizinden devam eder.
    y1, k1 = kur(tmp_path / "kes", barlar)
    adim = timeframe_ms("1h")
    k1.simdi = barlar[99].open_time + adim
    y1.baslat()
    for b in barlar[100:250]:
        k1.simdi = b.open_time + adim
        y1.adim()
    del y1  # kapat() çağrılmadı: plansız kesinti
    y2, k2 = kur(tmp_path / "kes", barlar)
    k2.simdi = barlar[249].open_time + adim
    y2.baslat()
    for b in barlar[250:]:
        k2.simdi = b.open_time + adim
        y2.adim()
    r = y2.kapat()
    assert r["hesap"]["ozkaynak"] == pytest.approx(beklenen["hesap"]["ozkaynak"], rel=1e-12)
    assert r["dolan_emir"] == beklenen["dolan_emir"]
    assert r["aciklanamaz_kesinti"] == 1 and r["sayac"]["yeniden_baslatma"] == 1


def test_kimlik_degisirse_baslamaz(tmp_path, barlar):
    kur(tmp_path / "a", barlar)
    with pytest.raises(YurutucuHatasi, match="kimliği değişti"):
        kur(tmp_path / "a", barlar, param={"hizli": 6, "yavas": 20, "maruziyet": 0.2})


# ================================================================ K-118: kapanan tur → risk


from types import SimpleNamespace  # noqa: E402

from scryne_quant.trader.yurutucu import kapanan_turlar  # noqa: E402


def _e(yon, q, fiyat, t, komisyon=()):
    return SimpleNamespace(sembol="BTCUSDT", yon=yon, dolan_miktar=q, ortalama_fiyat=fiyat,
                           karar_ms=t, olusturuldu_ms=t, guncellendi_ms=t + 1,
                           komisyon=komisyon)


def test_kapanan_turlar_komisyon_ve_kirinti():
    # Alış 0,001 BTC @ 100.000, komisyon taban varlıkta 0,000001 → elde 0,000999.
    # Satış 0,00099 @ 101.000 (adım 1e-5'e yuvarlandı), komisyon 0,1 USDT → kırıntı 0,000009.
    em = [_e("BUY", 0.001, 100_000.0, 1, (("BTC", 0.000001),)),
          _e("SELL", 0.00099, 101_000.0, 2, (("USDT", 0.1),))]
    (z, pnl), = kapanan_turlar(em, "BTCUSDT", min_notional=5.0, taban="BTC", kote="USDT")
    beklenen = -100.0 + 0.00099 * 101_000.0 - 0.1 + 0.000009 * 101_000.0
    assert z == 3 and pnl == pytest.approx(beklenen, rel=1e-12)


def test_kismi_satis_turu_kapatmaz_ve_flat_kapatir():
    em = [_e("BUY", 0.002, 100_000.0, 1), _e("SELL", 0.001, 99_000.0, 2),
          _e("FLAT", 0.001, 98_000.0, 3), _e("BUY", 0.001, 98_000.0, 4)]
    turlar = kapanan_turlar(em, "BTCUSDT", min_notional=5.0, taban="BTC", kote="USDT")
    assert len(turlar) == 1 and turlar[0][1] == pytest.approx(-200.0 + 99.0 + 98.0)


def _risk_sayimi(y):
    turlar = kapanan_turlar(y.hat.defter.tumu(), "BTCUSDT", min_notional=K.min_notional,
                            taban="BTC", kote="USDT")
    return turlar


def test_yurutucu_kapanan_turlari_risk_motoruna_bildirir(tmp_path, barlar):
    y, k = kur(tmp_path / "a", barlar)
    y.tekrar_oynat(k, isinma=100)
    turlar = _risk_sayimi(y)
    assert turlar, "test anlamsız: hiç tur kapanmadı"
    assert y.islenen_tur == len(turlar)
    # Ardışık kayıp sayacı, turların sonundaki kesintisiz kayıp serisiyle aynı.
    seri = 0
    for _, pnl in turlar:
        seri = 0 if pnl > 0 else seri + 1
    assert y.risk.durum.ardisik_kayip == seri % y.risk.limitler.ardisik_kayip_limiti


def test_cooldown_canli_yolda_emri_engeller(tmp_path, barlar):
    y, k = kur(tmp_path / "a", barlar)
    y.risk.limitler = y.risk.limitler.model_copy(update={"ardisik_kayip_limiti": 1})
    y.tekrar_oynat(k, isinma=100)
    kayipli = [p for _, p in _risk_sayimi(y) if p <= 0]
    assert kayipli, "test anlamsız: kaybeden tur yok"
    assert y.risk.red_sayimi.get("cooldown", 0) > 0


def test_yeniden_baslatmada_tur_iki_kez_sayilmaz(tmp_path, barlar):
    tam, kt = kur(tmp_path / "tam", barlar)
    tam.tekrar_oynat(kt, isinma=100)
    adim = timeframe_ms("1h")
    y1, k1 = kur(tmp_path / "kes", barlar)
    k1.simdi = barlar[99].open_time + adim
    y1.baslat()
    for b in barlar[100:300]:
        k1.simdi = b.open_time + adim
        y1.adim()
    del y1
    y2, k2 = kur(tmp_path / "kes", barlar)
    k2.simdi = barlar[299].open_time + adim
    y2.baslat()
    for b in barlar[300:]:
        k2.simdi = b.open_time + adim
        y2.adim()
    y2.kapat()
    assert y2.islenen_tur == tam.islenen_tur
    assert y2.risk.durum.ardisik_kayip == tam.risk.durum.ardisik_kayip
