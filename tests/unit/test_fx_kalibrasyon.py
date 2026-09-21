"""R5 Paket 1 (K-098): FX spread/slippage kalibrasyonu (kripto kalıbı) + finansman proxy.

Kanıt: (1) sentetik M1 deposunda spread/slippage/rollover penceresi/gap ayrımı sayıyla;
(2) `fee_bps`, `finansman_proxy_bps`, `venue_karari` aritmetiği; (3) yazılmış gerçek dosyalar —
`config/maliyet/fxcm-fx.json` ölçülmüş (gecici değil, fee 0,26, değer üç çiftin en büyük p75'i)
ve `config/finansman/fxcm-*.json` **proxy** (gecici, aralık + ham değer kayıtlı) — rapor
`docs/research/records/2026-09-21-R5-fx-kalibrasyon.json` ile tutarlı.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from scryne_quant.common import finansman as fin_mod
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.data import fx as fx_mod
from scryne_quant.data import fx_kalibrasyon as fk
from scryne_quant.data.takvim import TAKVIM_FX_5X24, takvim

KOK = Path(__file__).resolve().parents[2]
RAPOR = KOK / "docs" / "research" / "records" / "2026-09-21-R5-fx-kalibrasyon.json"
TFX = takvim(TAKVIM_FX_5X24)
CIFTLER = ("EURUSD", "GBPUSD", "USDJPY")


def _ms(metin: str) -> int:
    return int(pd.Timestamp(metin, tz="UTC").value // 1_000_000)


def _m1_depo(tmp_path: Path) -> fx_mod.FxDepo:
    """Pzt 2024-01-08 21:30 → 22:30 UTC (NY 16:30–17:30) 1 dk; 22:05 dakikası eksik; rollover
    penceresinde (16:45–17:15 NY = 21:45–22:15 UTC) spread 4 pip, dışında 1 pip; orta fiyat her
    dakika +0,0001 (≈0,93 bps) artar."""
    z = np.arange(_ms("2024-01-08 21:30"), _ms("2024-01-08 22:31"), 60_000)
    z = z[z != _ms("2024-01-08 22:05")]
    satirlar = [fx_mod.KAYNAK_BASLIK]
    for i, t in enumerate(z):
        ts = pd.Timestamp(int(t), unit="ms", tz="UTC")
        orta = 1.0700 + 0.0001 * i
        pencere = abs((ts.hour * 60 + ts.minute) - (22 * 60)) <= 15
        yarim = 0.0002 if pencere else 0.00005
        b, a = orta - yarim, orta + yarim
        damga = ts.strftime("%m/%d/%Y %H:%M:%S.000")
        satirlar.append(f"{damga},{b:.5f},{b:.5f},{b:.5f},{b:.5f},{a:.5f},{a:.5f},{a:.5f},{a:.5f}")
    depo = fx_mod.FxDepo(tmp_path)
    yol = depo.gelen_yolu("EURUSD", 2024, 2)
    yol.parent.mkdir(parents=True)
    yol.write_bytes(gzip.compress("\n".join(satirlar).encode("utf-8")))
    return depo


class TestOlcum:
    def test_spread_rollover_ve_gap(self, tmp_path):
        depo = _m1_depo(tmp_path)
        r = fk.fx_kalibre(depo, "EURUSD")
        assert r["m1"]["satir"] == 60 and r["m1"]["gap_dakika"] == 1
        sp = r["spread"]
        assert sp["rollover_penceresi"]["n"] == 30 and sp["rollover_disi"]["n"] == 30
        # Orta fiyat pencere boyunca 1,0700 → 1,0760 kayar: ±%0,6 tolerans.
        assert sp["rollover_penceresi"]["p50"] == pytest.approx(4 / 1.073 * 1e-4 * 1e4, rel=6e-3)
        assert sp["rollover_disi"]["p50"] == pytest.approx(1 / 1.073 * 1e-4 * 1e4, rel=6e-3)
        assert sp["genisleme_orani_p50"] == pytest.approx(4.0, rel=6e-3)
        # Slippage: 1 dk hareket ≈ 0,93 bps; 22:05 eksik → 22:06 `gap`, iki ucu da temiz olmayan
        # iki hareket (22:04→22:06, 22:06→22:07) atıldı (`kalibre_et` kuralı, K-021).
        sl = r["slippage"]
        assert sl["kullanilan_bar"] == 57 and sl["atilan_bar"] == 2
        assert sl["deger_bps"] == pytest.approx(0.0001 / 1.07 * 1e4, rel=0.01)
        assert r["slippage_rollover_penceresi"]["p50"] == pytest.approx(
            sl["dagilim_bps"]["p50"], rel=0.02
        )
        assert list(r["m1"]["dosya_sha256"]) == ["2024-2.csv.gz"]

    def test_pencere_disi_hata(self, tmp_path):
        depo = _m1_depo(tmp_path)
        with pytest.raises(fk.FxKalibrasyonHatasi, match="pencerede"):
            fk.fx_kalibre(depo, "EURUSD", baslangic_ms=_ms("2025-01-01 00:00"))
        with pytest.raises(fk.FxKalibrasyonHatasi, match="M1 dosyası yok"):
            fk.fx_kalibre(depo, "GBPUSD")


class TestAritmetik:
    def test_fee_bps_yukari_yuvarlar(self):
        assert fk.fee_bps(1.27, 1.0, False) == 0.26  # USDJPY: 2×1,27 / 100k = 0,254 → 0,26
        assert fk.fee_bps(1.27, 1.09, True) == 0.24  # EURUSD: 0,233 → 0,24
        assert fk.fee_bps(1.0, 1.0, False) == 0.2

    def test_finansman_proxy_taban_ve_ham(self):
        ham, deger = fk.finansman_proxy_bps((4.00, 4.00), (5.25, 5.50))  # EURUSD
        assert ham == pytest.approx(1.5 / 365 * 100) and deger == ham
        ham, deger = fk.finansman_proxy_bps((5.25, 5.50), (-0.10, -0.10))  # USDJPY
        assert ham == pytest.approx(-5.35 / 365 * 100) and deger == 0.0

    def test_venue_karari_esik(self):
        assert fk.venue_karari({"A": 1.0, "B": 1.4})["model"] == "fxcm-fx"
        assert fk.venue_karari({"A": 1.0, "B": 1.6})["model"] == "cift-basi"
        with pytest.raises(fk.FxKalibrasyonHatasi):
            fk.venue_karari({})


class TestKaynakSemasi:
    def test_tur_ve_aralik_zorunlu_proxy_gecici(self):
        with pytest.raises(ValidationError):
            fin_mod.FinansmanKaynagi(saglayici="x", tarih="2026-09-21", gerekce="g")
        broker = fin_mod.FinansmanKaynagi(
            saglayici="x",
            tarih="2026-09-21",
            gerekce="g",
            aralik="2024-01-01..2024-02-01",
            tur="broker",
        )
        proxy = broker.model_copy(update={"tur": "proxy", "ham_gunluk_bps": -1.0})
        assert not fin_mod.FinansmanModeli(uzun_gunluk_bps=1.0, kaynak=broker).gecici
        assert fin_mod.FinansmanModeli(uzun_gunluk_bps=0.0, kaynak=proxy).gecici
        assert fin_mod.FinansmanModeli(uzun_gunluk_bps=1.0).gecici


class TestYazilanDosyalar:
    def test_maliyet_modeli_olculmus(self):
        m = maliyet_mod.MaliyetKatalogu().coz("fxcm-fx", binance_spot_kripto=False)
        assert not m.gecici and m.fee_taker_bps == 0.26
        k = m.kalibrasyon
        assert k is not None and k.sembol == "EURUSD,GBPUSD,USDJPY" and k.timeframe == "1m"
        p75 = {c: k.dagilim_bps[f"{c}_p75"] for c in CIFTLER}
        assert m.slippage_bps == max(p75.values()) == k.deger_bps
        assert max(p75.values()) / min(p75.values()) < fk.VENUE_ORAN_ESIGI
        assert "Active Trader" in k.gerekce and "0 DEGIL" in k.gerekce
        assert k.aralik_baslangic_ms >= _ms("2024-01-07 00:00")
        assert k.aralik_bitis_ms < _ms("2024-02-03 00:00")

    def test_rapor_ile_tutarli(self):
        rapor = json.loads(RAPOR.read_text(encoding="utf-8"))
        m = maliyet_mod.MaliyetKatalogu().coz("fxcm-fx", binance_spot_kripto=False)
        assert rapor["venue_karari"]["model"] == "fxcm-fx"
        assert rapor["fee"]["fee_taker_bps"] == m.fee_taker_bps
        for c in CIFTLER:
            o = rapor["olcumler"][c]
            assert o["slippage"]["deger_bps"] == m.kalibrasyon.dagilim_bps[f"{c}_p75"]
            # Rollover penceresi spread'i ayrı ve belirgin: p50 genişleme ≥ 3×.
            assert o["spread"]["genisleme_orani_p50"] >= 3.0
            assert o["spread"]["rollover_penceresi"]["p50"] > o["spread"]["rollover_disi"]["p95"]

    def test_finansman_dosyalari_proxy_ve_gecici(self):
        katalog = fin_mod.FinansmanKatalogu()
        for c in CIFTLER:
            m = katalog.coz(f"fxcm-{c.lower()}")
            assert m.gecici and m.kaynak is not None and m.kaynak.tur == "proxy"
            assert ".." in m.kaynak.aralik and m.kaynak.ham_gunluk_bps is not None
            assert m.uzun_gunluk_bps == max(m.kaynak.ham_gunluk_bps, 0.0)
            assert "PROXY" in m.kaynak.gerekce and "http" in m.kaynak.gerekce
        assert katalog.coz("fxcm-usdjpy").uzun_gunluk_bps == 0.0
        assert katalog.coz("fxcm-usdjpy").kaynak.ham_gunluk_bps < 0  # lehte carry, tabana çekildi
        assert katalog.coz("fxcm-eurusd").uzun_gunluk_bps == pytest.approx(1.5 / 365 * 100)
