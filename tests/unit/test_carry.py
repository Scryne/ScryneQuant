"""Funding carry demo (K-139): muhasebe, funding tahakkuku, giriş/çıkış kuralı."""

from __future__ import annotations

from pathlib import Path

import pytest

from scryne_quant.aktif.carry import GUN_MS, CarryAyari, CarryHesap, carry_tur
from scryne_quant.aktif.defter import Defter

T0 = 1_790_035_200_000  # 2026-09-22 00:00 UTC


class Sahte:
    def __init__(self) -> None:
        self.oran = {"AUSDT": 0.0005, "BUSDT": 0.00001}  # A: %55/yıl (3×/gün), B: ~%1
        self.fiyat = {"AUSDT": 100.0, "BUSDT": 50.0}
        self.hacim = {"AUSDT": 50e6, "BUSDT": 50e6}
        self.ekstra: list[tuple[int, float, float]] = []

    def perp_ozet(self):
        return {s: {"oran": o, "mark": self.fiyat[s], "sonraki_ms": 0}
                for s, o in self.oran.items()}

    def funding(self, sembol, bas_ms):
        olay = [(T0 - k * 8 * 3_600_000, self.oran[sembol], self.fiyat[sembol])
                for k in range(1, 120)]
        olay += [e for e in self.ekstra if sembol == "AUSDT"]
        return sorted(o for o in olay if o[0] >= bas_ms)

    def spot_hacim_medyan(self, sembol, gun):
        return self.hacim[sembol]

    def spot_fiyat(self, sembol):
        return self.fiyat[sembol]

    def perp_fiyat(self, sembol):
        return self.fiyat[sembol]


def test_giris_notrluk_funding_ve_cikis(tmp_path: Path) -> None:
    v, a = Sahte(), CarryAyari()
    h, d = CarryHesap(tmp_path, 10_000.0), Defter(tmp_path)
    r = carry_tur(v, h, d, a, T0 + 60_000)
    assert list(h.poz) == ["AUSDT"]  # yalnız eşik üstü
    n = 10_000 / (1.5 * 8)
    maliyet = n * (10 + 5 + 2 * 2) / 1e4
    assert r["ozkaynak"] == pytest.approx(10_000 - maliyet)
    # Fiyat iki bacakta %30 yükselir: değer değişmez (yön nötr).
    v.fiyat["AUSDT"] = 130.0
    r = carry_tur(v, h, d, a, T0 + 3_600_000)
    assert r["ozkaynak"] == pytest.approx(10_000 - maliyet)
    # Funding olayı: short'a öder (adet × mark × oran).
    v.ekstra = [(T0 + 8 * 3_600_000, 0.001, 130.0)]
    r = carry_tur(v, h, d, a, T0 + 9 * 3_600_000)
    assert r["ozkaynak"] == pytest.approx(10_000 - maliyet + (n / 100.0) * 130.0 * 0.001)
    # Ertesi gün funding düşer → çıkış (sinyal < %5).
    v.oran["AUSDT"] = 0.0
    v.ekstra = []
    carry_tur(v, h, d, a, T0 + GUN_MS + 60_000 + 4 * GUN_MS)
    assert h.poz == {}
    d.kapat()


def test_likidite_ve_azami_pozisyon(tmp_path: Path) -> None:
    v, a = Sahte(), CarryAyari(azami_poz=1)
    v.oran["BUSDT"] = 0.001
    v.hacim["BUSDT"] = 5e6  # likit değil
    h, d = CarryHesap(tmp_path, 10_000.0), Defter(tmp_path)
    carry_tur(v, h, d, a, T0 + 60_000)
    assert list(h.poz) == ["AUSDT"]
    d.kapat()


def test_tasfiye_vekili(tmp_path: Path) -> None:
    v, a = Sahte(), CarryAyari()
    h, d = CarryHesap(tmp_path, 10_000.0), Defter(tmp_path)
    carry_tur(v, h, d, a, T0 + 60_000)
    v.fiyat["AUSDT"] = 150.0  # dengelemeden %50 yukarı
    r = carry_tur(v, h, d, a, T0 + 3_600_000)
    assert h.poz == {} and any("tasfiye" in o for o in r["olaylar"])
    d.kapat()
