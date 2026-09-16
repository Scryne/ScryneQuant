"""Veri sözleşmeleri ve katman tamlığı. (Faz 9 bitti kriteri)

Roadmap Faz 9: *"Her veri kaynağının sözleşme dosyası var ve tamlık kontrolü otomatik
koşuyor; arşivin `1mo` katmanındaki eksiklik (Spike 6 §4b) bu kontrolle yakalanıyor."*
"""

from __future__ import annotations

import dataclasses

import pytest

from scryne_quant.data.sozlesme import SOZLESMELER, katman_karsilastir, katman_tamligi
from tests.unit.test_arsiv_indirici import SahteArsiv

ARALIK_2024_12 = 1_733_011_200_000


class TestSozlesmeler:
    @pytest.mark.parametrize(
        "ad", ["binance-spot-rest-kline", "binance-arsiv-spot-kline", "binance-usdm-funding"]
    )
    def test_kullanilan_her_kaynagin_sozlesmesi_var(self, ad):
        assert ad in SOZLESMELER

    @pytest.mark.parametrize("ad", sorted(SOZLESMELER))
    def test_hicbir_alan_bos_degil(self, ad):
        s = SOZLESMELER[ad]
        for alan in dataclasses.fields(s):
            deger = getattr(s, alan.name)
            assert deger, f"{ad}.{alan.name} boş"

    @pytest.mark.parametrize("ad", sorted(SOZLESMELER))
    def test_lisans_tahmin_edilmiyor(self, ad):
        """Doğrulanmamış lisans 'doğrulanmadı' der; bir lisans adı uydurmaz."""
        assert "doğrulanmadı" in SOZLESMELER[ad].lisans or "kaynak:" in SOZLESMELER[ad].lisans


class TestKatmanTamligi:
    def test_spike6_1mo_eksikligi_yakalaniyor(self):
        """Spike 6 §4b: 1h tam, 1mo 2026-03'ten beri yok."""
        h1 = {f"2026-0{m}" for m in range(1, 9)}
        mo = {"2026-01", "2026-02"}
        r = katman_karsilastir("BTCUSDT", h1, mo)
        assert not r.tam
        assert r.turetilmiste_eksik == tuple(f"2026-0{m}" for m in range(3, 9))
        assert r.referansta_eksik == ()

    def test_tam_sembol(self):
        aylar = {"2024-11", "2024-12", "2025-01"}
        assert katman_karsilastir("X", aylar, aylar).tam

    def test_ic_bosluk_raporlanir(self):
        r = katman_karsilastir("X", {"2024-01", "2024-04"}, {"2024-01", "2024-04"})
        assert r.referans_ic_bosluk == ("2024-02", "2024-03")
        assert not r.tam

    def test_arsiv_listesinden(self):
        arsiv = SahteArsiv()
        arsiv.aylik("BTCUSDT", "2024-12", ARALIK_2024_12, 2)
        arsiv.ekle("data/spot/monthly/klines/BTCUSDT/1mo/BTCUSDT-1mo-2024-11.zip", ["1"])
        r = katman_tamligi(arsiv, "BTCUSDT")
        assert r.turetilmiste_eksik == ("2024-12",)
        assert r.referansta_eksik == ("2024-11",)
