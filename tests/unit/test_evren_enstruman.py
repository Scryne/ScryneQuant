"""Canlı evren girişi: katalogdan kimlik, borsadan tick/lot, U17 fail-closed doğrulama. (K-085)"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pandas as pd
import pytest

from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.data.kimlik import kanonik_kimlik
from scryne_quant.exchange.kurallar import SembolKurallari
from scryne_quant.live.evren_depo import EvrenKosuDeposu
from scryne_quant.live.evren_enstruman import (
    KATALOG_ADI,
    EvrenEnstrumanHatasi,
    enstrumanlari_kur,
    katalog_yolu,
    katalogu_oku,
    ozet,
)
from scryne_quant.live.evren_kosturucu import EvrenTablosu, kos
from scryne_quant.research.evren_kosu import enstruman_maliyetleri
from tests.unit.test_evren_kosturucu import SAAT, SEMBOLLER, T0, Saat, SahteRest, _kosucu

KOK = Path(__file__).resolve().parents[2]
GERCEK_KATALOG = KOK / "data" / "evren" / "_evren" / KATALOG_ADI
GERCEK_TABLO = KOK / "data" / "evren" / "_evren" / "27b7a16ed0ed.parquet"


def _v1_kayit(sembol: str, bas_ms: int, bit_ms: int, tarih: str) -> dict:
    """Paket 1 öncesi katalog biçimi (gerçek dosyadaki 9 anahtar)."""
    return {
        "bar_sayisi": (bit_ms - bas_ms) // SAAT,
        "gecerli_baslangic": f"{tarih} 00:00:00 UTC",
        "gecerli_baslangic_ms": bas_ms,
        "gecerli_bitis": "2026-01-01 00:00:00 UTC",
        "gecerli_bitis_ms": bit_ms,
        "kanonik_id": kanonik_kimlik("binance-spot", "spot", sembol, tarih),
        "kirilma_ile_basladi": False,
        "sembol": sembol,
        "venue": "binance-spot",
    }


def _katalog_yaz(dizin: Path, kayitlar: list[dict]) -> Path:
    yol = dizin / KATALOG_ADI
    yol.write_text(json.dumps({"kirilmalar": [], "enstrumanlar": kayitlar}), encoding="utf-8")
    return yol


def _kurallar(durum: str = "TRADING", tick: float = 0.01, step: float = 0.001):
    def kaynak(sembol: str) -> SembolKurallari:
        return SembolKurallari(sembol, tick, step, 5.0, durum, taban_varlik="X", kote_varlik="USDT")

    return kaynak


@pytest.fixture
def katalog(tmp_path):
    bas = 1_704_067_200_000  # 2024-01-01
    kayitlar = [
        _v1_kayit("AAAUSDT", bas, bas + 100 * SAAT, "2024-01-01"),
        # BBB: iki segment (kimlik kırılması), sonraki önce yazılmış — okuma sıralar
        _v1_kayit("BBBUSDT", bas + 200 * SAAT, bas + 300 * SAAT, "2024-01-09"),
        _v1_kayit("BBBUSDT", bas, bas + 100 * SAAT, "2024-01-01"),
        # CCC: v2 kaydı (Paket 1 sonrası katalog)
        {**_v1_kayit("CCCUSDT", bas, bas + 100 * SAAT, "2024-01-01"), "asset_class": "kripto",
         "instrument_type": "spot", "takvim_id": "24x7", "tick_size": None, "lot_size": None,
         "contract_size": None, "maliyet_modeli_id": "global", "finansman_modeli_id": None},
    ]
    return katalogu_oku(_katalog_yaz(tmp_path, kayitlar))


class TestKatalogOkuma:
    def test_v1_ve_v2_kayitlar_okunur_segmentler_sirali(self, katalog):
        assert set(katalog) == {"AAAUSDT", "BBBUSDT", "CCCUSDT"}
        b = katalog["BBBUSDT"]
        assert [e.gecerli_baslangic_ms for e in b] == sorted(e.gecerli_baslangic_ms for e in b)
        assert b[1].kanonik_id == "binance-spot:BBBUSDT@2024-01-09"
        a = katalog["AAAUSDT"]
        assert all(e.tick_size is None and e.maliyet_modeli_id == "global" for e in a)

    def test_katalog_yolu_tablonun_yaninda(self, tmp_path):
        assert katalog_yolu(tmp_path / "x" / "27b7.parquet") == tmp_path / "x" / KATALOG_ADI

    def test_eksik_ve_bozuk_katalog(self, tmp_path):
        with pytest.raises(EvrenEnstrumanHatasi, match="kataloğu yok"):
            katalogu_oku(tmp_path / KATALOG_ADI)
        (tmp_path / KATALOG_ADI).write_text("{", encoding="utf-8")
        with pytest.raises(EvrenEnstrumanHatasi, match="bozuk"):
            katalogu_oku(tmp_path / KATALOG_ADI)
        (tmp_path / KATALOG_ADI).write_text(json.dumps({"kirilmalar": []}), encoding="utf-8")
        with pytest.raises(EvrenEnstrumanHatasi, match="bozuk"):
            katalogu_oku(tmp_path / KATALOG_ADI)

    def test_gecersiz_kayit_fail_closed(self, tmp_path):
        bas = 1_704_067_200_000
        kotu = {**_v1_kayit("AAAUSDT", bas, bas + SAAT, "2024-01-01"), "yeni_alan": 1}
        with pytest.raises(EvrenEnstrumanHatasi, match="geçersiz"):
            katalogu_oku(_katalog_yaz(tmp_path, [kotu]))
        tutarsiz = {**_v1_kayit("AAAUSDT", bas, bas + SAAT, "2024-01-01"), "kanonik_id": "x"}
        with pytest.raises(EvrenEnstrumanHatasi, match="tutarsız"):
            katalogu_oku(_katalog_yaz(tmp_path, [tutarsiz]))


class TestEnstrumanlariKur:
    def test_tick_lot_borsadan_dolar_ve_dogrulanir(self, katalog):
        hazir = enstrumanlari_kur(katalog, ("BBBUSDT", "AAAUSDT"), _kurallar())
        assert list(hazir) == ["AAAUSDT", "BBBUSDT"]  # sıralı
        for segmentler in hazir.values():
            for e in segmentler:
                assert (e.tick_size, e.lot_size) == (0.01, 0.001)
                e.islem_icin_dogrula()  # tekrar geçer
        assert len(hazir["BBBUSDT"]) == 2  # her segmente yazıldı
        assert katalog["AAAUSDT"][0].tick_size is None  # kaynak katalog değişmedi
        assert ozet(hazir) == {
            "sembol": 2, "segment": 3, "tipler": ["spot"], "maliyet_modelleri": ["global"]
        }

    def test_katalogda_olmayan_uye_fail_closed(self, katalog):
        with pytest.raises(EvrenEnstrumanHatasi, match="kataloğunda yok"):
            enstrumanlari_kur(katalog, ("AAAUSDT", "ZZZUSDT"), _kurallar())

    def test_islem_gormeyen_sembol_fail_closed(self, katalog):
        with pytest.raises(EvrenEnstrumanHatasi, match="işlem görmüyor"):
            enstrumanlari_kur(katalog, ("AAAUSDT",), _kurallar(durum="BREAK"))

    def test_gecersiz_kural_degeri_u17_reddi(self, katalog):
        with pytest.raises(EvrenEnstrumanHatasi, match="tick_size"):
            enstrumanlari_kur(katalog, ("AAAUSDT",), _kurallar(tick=0.0))

    def test_maliyet_cozumleme_zinciri_spot_global_none(self, katalog):
        hazir = enstrumanlari_kur(katalog, SEMBOLLER, _kurallar())
        assert enstruman_maliyetleri(maliyet_mod.MaliyetKatalogu(), hazir) is None


@pytest.mark.skipif(not GERCEK_KATALOG.exists(), reason="gerçek evren deposu yok (gitignore)")
class TestGercekKatalog:
    def test_761_kimlik_okunur_ve_son_ay_uyeleri_kurulur(self):
        katalog = katalogu_oku(GERCEK_KATALOG)
        assert sum(len(s) for s in katalog.values()) == 761
        tablo = EvrenTablosu.oku(GERCEK_TABLO)
        son = tablo.uyelik(tablo.aylar()[-1])
        assert son is not None and len(son.semboller) == 50
        hazir = enstrumanlari_kur(katalog, son.semboller, _kurallar())
        assert set(hazir) == set(son.semboller)
        assert enstruman_maliyetleri(maliyet_mod.MaliyetKatalogu(), hazir) is None


class TestKosucuDogrulayici:
    """Ay dönümünde evrene giren üyelik: doğrulayıcı çağrılır; hata → olay + koşu durur."""

    def _kur(self, tmp_path, dogrulayici):
        aralik = int(pd.Timestamp("2023-12-01", tz="UTC").timestamp() * 1000)
        j = (aralik - T0) // SAAT
        satirlar = [{"ay": "2023-11", "sira": i + 1, "kanonik_id": s, "sembol": s,
                     "onceki_ay_quote_hacim": 1.0} for i, s in enumerate(SEMBOLLER[:2])]
        satirlar += [{"ay": "2023-12", "sira": i + 1, "kanonik_id": s, "sembol": s,
                      "onceki_ay_quote_hacim": 1.0} for i, s in enumerate(SEMBOLLER)]
        yol = tmp_path / "evren.sqlite"
        saat = Saat(T0 + (j - 3) * SAAT + 30 * 60_000)
        k = _kosucu(yol, saat, T0 + (j - 3) * SAAT, T0 + (j + 3) * SAAT, SahteRest())
        k.tablo = EvrenTablosu(pd.DataFrame(satirlar), "h")
        k.enstruman_dogrulayici = dogrulayici

        async def ilerleyen_uyku(_):
            saat.ms += 10 * 60_000
            await asyncio.sleep(0)

        return k, yol, ilerleyen_uyku

    def test_yeni_uyelik_dogrulanir_ve_olay_yazilir(self, tmp_path):
        cagrilar = []
        k, yol, uyku = self._kur(tmp_path, lambda u: cagrilar.append((u.ay, u.semboller)))
        asyncio.run(kos(k, uyku=uyku, azami_adim=6))
        assert cagrilar == [("2023-12", SEMBOLLER)]
        depo = EvrenKosuDeposu(yol)
        turler = [o["tur"] for o in depo.olaylar()]
        assert "enstruman_dogrulandi" in turler and "enstruman_dogrulama_hatasi" not in turler
        depo.kapat()

    def test_dogrulama_hatasi_kosuyu_durdurur(self, tmp_path):
        def kotu(u):
            raise EvrenEnstrumanHatasi(f"{u.ay}: test reddi")

        k, yol, uyku = self._kur(tmp_path, kotu)
        with pytest.raises(EvrenEnstrumanHatasi, match="test reddi"):
            asyncio.run(kos(k, uyku=uyku, azami_adim=6))
        depo = EvrenKosuDeposu(yol)
        olaylar = [o for o in depo.olaylar() if o["tur"] == "enstruman_dogrulama_hatasi"]
        assert len(olaylar) == 1 and olaylar[0]["ayrinti"]["ay"] == "2023-12"
        depo.kapat()

    def test_dogrulayici_yoksa_eski_davranis(self, tmp_path):
        k, yol, uyku = self._kur(tmp_path, None)
        asyncio.run(kos(k, uyku=uyku, azami_adim=6))
        depo = EvrenKosuDeposu(yol)
        assert "enstruman_dogrulandi" not in [o["tur"] for o in depo.olaylar()]
        depo.kapat()
