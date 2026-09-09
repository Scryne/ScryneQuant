"""`Sinyal` sözleşmesi: niyet, emir değil. (§10, K-003, K-005)"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scryne_quant.strategy.sinyal import Sinyal, Yon

ZAMAN = 1_700_000_000_000


def _sinyal(**degisiklik) -> Sinyal:
    alanlar = {
        "symbol": "BTCUSDT",
        "side": Yon.BUY,
        "target_exposure": 0.2,
        "confidence": 0.5,
        "reason": "TEST_KODU",
        "timestamp": ZAMAN,
    }
    return Sinyal(**(alanlar | degisiklik))


class TestSekil:
    def test_alan_adlari_dokumandaki_json_ile_ayni(self):
        """§10'daki şekil sözleşmedir: audit log, sonuç kaydı ve arayüz buna bakacak."""
        assert set(_sinyal().model_dump()) == {
            "symbol",
            "side",
            "target_exposure",
            "confidence",
            "reason",
            "timestamp",
        }

    def test_emir_alanlari_reddediliyor(self):
        """Strateji emir üretemez: fiyat/miktar/emir tipi sözleşmeye giremez (K-003)."""
        for alan in ("price", "quantity", "order_type", "stop_loss"):
            with pytest.raises(ValidationError):
                _sinyal(**{alan: 1.0})

    def test_degismez(self):
        s = _sinyal()
        with pytest.raises(ValidationError):
            s.target_exposure = 0.9


class TestDogrulama:
    def test_sembol_buyuk_harfe_cevriliyor(self):
        assert _sinyal(symbol="btcusdt").symbol == "BTCUSDT"

    def test_sembolde_ayrac_kabul_edilmiyor(self):
        # Depo ve adaptör `BTCUSDT` kullanıyor; ikinci bir yazım biçimi, iki katmanın
        # aynı sembolü farklı anlaması demek olurdu.
        with pytest.raises(ValidationError):
            _sinyal(symbol="BTC/USDT")

    @pytest.mark.parametrize("deger", [-0.01, 1.01, 2.0])
    def test_maruziyet_araligi(self, deger: float):
        with pytest.raises(ValidationError):
            _sinyal(target_exposure=deger)

    @pytest.mark.parametrize("deger", [-0.1, 1.5])
    def test_guven_araligi(self, deger: float):
        with pytest.raises(ValidationError):
            _sinyal(confidence=deger)

    @pytest.mark.parametrize("deger", ["ema kesişti", "lowercase_code", "AB", "A" * 65, ""])
    def test_neden_kod_olmali(self, deger: str):
        with pytest.raises(ValidationError):
            _sinyal(reason=deger)

    def test_saniye_cinsinden_zaman_reddediliyor(self):
        """K-005: epoch **ms**. Saniye verilirse hata Faz 3'te "sonuç biraz tuhaf" olurdu."""
        with pytest.raises(ValidationError, match="ms"):
            _sinyal(timestamp=1_700_000_000)


class TestYonTutarliligi:
    def test_flat_maruziyet_sifir_olmali(self):
        with pytest.raises(ValidationError):
            _sinyal(side=Yon.FLAT, target_exposure=0.2)

    def test_flat_sifirla_gecerli(self):
        assert _sinyal(side=Yon.FLAT, target_exposure=0.0).target_exposure == 0.0

    def test_buy_sifir_maruziyet_reddediliyor(self):
        with pytest.raises(ValidationError):
            _sinyal(side=Yon.BUY, target_exposure=0.0)

    def test_tam_cikis_flat_ile_ifade_edilir(self):
        """`SELL` + hedef 0 ile `FLAT` aynı niyeti iki farklı şekilde söylerdi."""
        with pytest.raises(ValidationError, match="FLAT"):
            _sinyal(side=Yon.SELL, target_exposure=0.0)

    def test_sell_kismi_azaltma_gecerli(self):
        assert _sinyal(side=Yon.SELL, target_exposure=0.1).side is Yon.SELL
