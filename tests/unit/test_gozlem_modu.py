"""Gözlem modu zinciri atlamanın yolu olmamalı. (K-035)

K-035 gözlem modunu şu gerekçeyle ekledi: Faz 4'te yedi stratejinin yedisi de promotion
kapılarında kaldı (K-019), dolayısıyla `paper` modunda risk motoru her sinyali
`PROMOTION_YOK` ile reddeder ve Faz 6'nın *"restart sonrası pozisyon state'i doğru"*
kriteri hiç pozisyon açılmadığı için **boş yere** geçer.

Bu dosya o eklemenin bedelini ödüyor: yeni bir mod eklemek, zinciri atlamanın yeni bir
yolunu açmadığının **kanıtlanmasını** gerektirir. Üç kanıt:

1. Gözlem modu promotion dışındaki hiçbir limiti gevşetmiyor.
2. Gözlem koşusundan promotion kanıtı **kurulamıyor** — değerlendirilip kalmıyor,
   kurulamıyor. İkisi farklı: "ölçüldü ve yetmedi" ile "bu ölçüm bu koşudan alınamaz"
   ayrı şeyler ve ikincisi bir kanıt hatasıdır.
3. K-019'un sayısal eşikleri gevşetilmedi; `test_kapilar.py`nin gevşetme dedektörü
   yerinde duruyor.
"""

from __future__ import annotations

import pytest

from scryne_quant.risk.motor import MODLAR, RiskMotoru
from scryne_quant.risk.niyet import OnayliNiyet, RedSebebi
from scryne_quant.risk.promotion import (
    MOD_ESIGI,
    Asama,
    Kanit,
    PromotionHatasi,
)
from tests.conftest import risk_limitleri

T0 = 1_699_999_200_000


def sinyal(hedef: float = 0.30):
    from scryne_quant.strategy.sinyal import Sinyal, Yon

    return Sinyal(
        symbol="BTCUSDT",
        side=Yon.BUY,
        target_exposure=hedef,
        confidence=0.9,
        reason="TEST",
        timestamp=T0,
    )


def olcum(**degisiklik):
    from scryne_quant.risk.motor import PiyasaOlcumu

    alanlar = {
        "fiyat": 30_000.0,
        "ozkaynak": 10_000.0,
        "mevcut_maruziyet": 0.0,
        "bar_ms": T0,
        "atr": 150.0,
    }
    return PiyasaOlcumu(**(alanlar | degisiklik))


def motor(mod: str = "gozlem", **degisiklik) -> RiskMotoru:
    durum = degisiklik.pop("durum", None)
    return RiskMotoru(risk_limitleri(**degisiklik), "1h", mod=mod, durum=durum)


class TestModTanimi:
    def test_gozlem_kayitli_bir_mod(self) -> None:
        assert "gozlem" in MODLAR
        assert MOD_ESIGI["gozlem"] is Asama.YOK

    def test_paper_esigi_indirilmedi(self) -> None:
        # K-018: sayısal eşik esnetilemez. Gözlem modu eklenirken paper'ın eşiğine
        # dokunulmadığının testi — K-035'in tüm gerekçesi buna dayanıyor.
        assert MOD_ESIGI["paper"] is Asama.RISK_INCELEMESI
        assert MOD_ESIGI["live"] is Asama.LIVE
        assert MOD_ESIGI["backtest"] is Asama.YOK


class TestLimitlerGevsemiyor:
    """Gözlem modu **yalnızca** promotion kapısını atlıyor."""

    def test_promotion_kapisi_atlaniyor(self) -> None:
        karar = motor("gozlem").degerlendir(sinyal(), olcum())
        assert isinstance(karar, OnayliNiyet)

    def test_ayni_sinyal_paper_modunda_reddediliyor(self) -> None:
        karar = motor("paper").degerlendir(sinyal(), olcum())
        assert not isinstance(karar, OnayliNiyet)
        assert karar.sebep is RedSebebi.PROMOTION_YOK

    def test_safe_mode_gozlem_modunda_da_durduruyor(self) -> None:
        m = motor("gozlem")
        m.kill("TEST", T0)
        karar = m.degerlendir(sinyal(), olcum())
        assert karar.sebep is RedSebebi.SAFE_MODE

    def test_volatilite_guardi_gozlem_modunda_da_calisiyor(self) -> None:
        m = motor("gozlem")
        karar = m.degerlendir(sinyal(), olcum(atr=None))
        assert karar.sebep is RedSebebi.VOLATILITE_OLCULEMEDI

    def test_boyutlandirma_tavani_gozlem_modunda_da_baglayici(self) -> None:
        m = motor("gozlem")
        karar = m.degerlendir(sinyal(hedef=1.0), olcum())
        assert isinstance(karar, OnayliNiyet)
        assert karar.onayli_maruziyet <= m.limitler.azami_maruziyet

    def test_drawdown_limiti_gozlem_modunda_da_kill_tetikliyor(self) -> None:
        m = motor("gozlem")
        m.bar_isle(T0, 10_000.0)
        m.bar_isle(T0 + 3_600_000, 7_000.0)
        karar = m.degerlendir(sinyal(), olcum(ozkaynak=7_000.0))
        assert karar.sebep is RedSebebi.DRAWDOWN
        assert m.durum.safe_mode is True


class TestKanitUretilemiyor:
    """K-035/2: gözlem koşusunun ürettiği hiçbir kayıt promotion kanıtı olamaz."""

    def test_gozlem_modundan_paper_kaniti_kurulamiyor(self) -> None:
        with pytest.raises(PromotionHatasi, match="yalnızca `paper` modundan"):
            Kanit(paper_gun=45.0, paper_kesinti=0, paper_mod="gozlem")

    def test_mod_yazilmamis_paper_kaniti_da_kurulamiyor(self) -> None:
        # Varsayılan `None`. Eksik bilgi "geçerli" sayılsaydı, alanı yazmayı unutmak
        # kapıyı açmanın en kolay yolu olurdu.
        with pytest.raises(PromotionHatasi):
            Kanit(paper_gun=45.0, paper_kesinti=0)

    def test_yalnizca_kesinti_yazilmis_olsa_da_kurulamiyor(self) -> None:
        with pytest.raises(PromotionHatasi):
            Kanit(paper_kesinti=0, paper_mod="gozlem")

    def test_paper_modundan_kanit_kurulabiliyor(self) -> None:
        k = Kanit(paper_gun=45.0, paper_kesinti=0, paper_mod="paper")
        assert k.sozluk()["paper_mod"] == "paper"

    def test_paper_kaniti_olmayan_kanit_serbest(self) -> None:
        # Faz 1-5'in kanıtları paper alanlarını hiç doldurmuyor; kontrol onları etkilemez.
        k = Kanit(commit="a" * 40, dirty=False)
        assert k.paper_mod is None
