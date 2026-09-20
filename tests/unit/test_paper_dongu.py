"""Paper/gözlem döngüsü: bar içi sıra, fill, bayat-veri guard'ı. (Faz 6, §24, K-004, K-028)

Roadmap'in Faz 6 kriterlerinden ikisi burada ölçülüyor:

- *"Veri akışı kesildiğinde yeni pozisyon açılmıyor."*
- (Kısmen) *"Dashboard'un risk durumu"*nun beslendiği özet.

Üçüncü kriter (restart) `test_toparlanma.py`de, dördüncüsü (30 gün) tanım gereği bir
koşunun kendisi.

**Neden `PlanliStrateji`:** ölçülen şey strateji mantığı değil, motorun sırası ve
muhasebesi. Sinyalleri sabit bir takvimden vermek ikisini ayırıyor — bir strateji
davranışını yeniden üretmek zorunda kalan test, aslında iki şeyi birden test eder ve
biri bozulunca hangisi olduğunu söyleyemez.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from scryne_quant.backtest.fill import AtlamaSebebi
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.live.akis import Bar, Kaynak
from scryne_quant.live.depo import KESINTI_OLAYLARI, KosuDeposu, KosuKimligi, KosuOlayi
from scryne_quant.live.motor import MotorHatasi, PaperMotoru
from scryne_quant.risk.audit import BellekDefteri
from scryne_quant.risk.motor import RiskMotoru
from scryne_quant.risk.promotion import Asama
from tests.conftest import PlanliStrateji, bar_uret
from tests.conftest import risk_limitleri as limitler

SAAT = 3_600_000
BASLANGIC = 1_699_999_200_000


def barlar(n: int = 60, **kw) -> list[Bar]:
    df = bar_uret(n, **kw)
    return [
        Bar(
            open_time=int(r["open_time"]),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r["volume"]),
            quote_volume=float(r["quote_volume"]),
            trades=int(r["trades"]),
        )
        for r in df.to_dict("records")
    ]


def kimlik(mod: str = "gozlem", **kw) -> KosuKimligi:
    alanlar = {
        "kosu_adi": "test",
        "mod": mod,
        "sembol": "BTCUSDT",
        "timeframe": "1h",
        "strateji": {"ad": "planli"},
        "maliyet": {"fee_taker_bps": 10.0, "slippage_bps": 5.0},
        "limitler": {},
        "limit_kimligi": "k" * 64,
        "baslangic_sermaye": 10_000.0,
        "commit_sha": "a" * 40,
        "dirty": False,
        "kutuphaneler": {},
        "olusturuldu_ms": BASLANGIC,
    }
    return KosuKimligi(**{**alanlar, **kw})


def motor_kur(
    takvim: dict[int, tuple[str, float]] | None = None,
    *,
    mod: str = "gozlem",
    depo: KosuDeposu | None = None,
    asamalar: dict[str, Asama] | None = None,
    **motor_kw,
) -> PaperMotoru:
    lim = limitler()
    return PaperMotoru(
        kimlik=kimlik(mod),
        strateji=PlanliStrateji(takvim or {}),
        maliyet=MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0),
        risk=RiskMotoru(lim, "1h", mod=mod, defter=BellekDefteri(), asamalar=asamalar),
        depo=depo if depo is not None else KosuDeposu(),
        **motor_kw,
    )


def kosuyu_isle(motor: PaperMotoru, bar_listesi, *, baslangic_ms: int = 0):
    """Barları sırayla işler; her barda taze bir nabız varmış gibi davranır."""
    return [
        motor.bar_isle(b, simdi=baslangic_ms + i * 1000)
        for i, b in enumerate(bar_listesi)
    ]


class TestKurulum:
    def test_backtest_modu_reddediliyor(self) -> None:
        # `backtest` modu promotion istemiyor ve gerçek zaman kavramı yok; canlı döngüde
        # o modu kabul etmek, gözlem modunu (K-035) anlamsız kılardı.
        with pytest.raises(MotorHatasi, match="modunda çalışmaz"):
            motor_kur(mod="backtest")

    def test_live_modu_reddediliyor(self) -> None:
        # Simüle fill üreten motor `live` etiketi taşıyamaz: Faz 8'in drift ölçümü
        # paper ile live'ı ayrı kayıtlarda ister; aynı motorun iki adı olamaz.
        with pytest.raises(MotorHatasi, match="modunda çalışmaz"):
            motor_kur(mod="live")

    def test_risk_modu_kosu_moduyla_uyusmali(self) -> None:
        with pytest.raises(MotorHatasi, match="uyuşmuyor"):
            PaperMotoru(
                kimlik=kimlik("gozlem"),
                strateji=PlanliStrateji({}),
                maliyet=MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0),
                risk=RiskMotoru(limitler(), "1h", mod="paper", defter=BellekDefteri()),
                depo=KosuDeposu(),
            )

    def test_kosu_kimligi_yaziliyor(self) -> None:
        m = motor_kur()
        assert m.depo.kosu_oku() == m.kimlik

    def test_ayni_depoya_baska_kosu_yazilamaz(self) -> None:
        depo = KosuDeposu()
        motor_kur(depo=depo)
        with pytest.raises(Exception, match="başka bir koşuya ait"):
            PaperMotoru(
                kimlik=kimlik("gozlem", kosu_adi="baska"),
                strateji=PlanliStrateji({}),
                maliyet=MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0),
                risk=RiskMotoru(limitler(), "1h", mod="gozlem", defter=BellekDefteri()),
                depo=depo,
            )


class TestBarIciSira:
    """Sıra backtest motoruyla birebir aynı olmalı (K-001)."""

    def test_sinyal_bir_sonraki_barin_acilisinda_doluyor(self) -> None:
        # K-004: sinyal barının kapanışından **asla**.
        m = motor_kur({20: ("BUY", 0.2)})
        bl = barlar(30)
        sonuclar = kosuyu_isle(m, bl)
        assert sonuclar[20].karar == "onay"
        assert sonuclar[20].fill is None
        assert sonuclar[21].fill is not None
        assert sonuclar[21].fill["zaman_ms"] == bl[21].open_time

    def test_fill_fiyati_aleyhte_kayiyor(self) -> None:
        # K-007: alışta yukarı.
        m = motor_kur({20: ("BUY", 0.2)})
        bl = barlar(30)
        sonuclar = kosuyu_isle(m, bl)
        fill = sonuclar[21].fill
        assert fill["referans_fiyat"] == pytest.approx(bl[21].open)
        assert fill["fiyat"] > fill["referans_fiyat"]

    def test_tur_kapaninca_gerceklesen_pnl_yaziliyor(self) -> None:
        m = motor_kur({20: ("BUY", 0.2), 40: ("FLAT", 0.0)})
        sonuclar = kosuyu_isle(m, barlar(50))
        assert sonuclar[41].fill["gerceklesen_pnl"] is not None
        assert m.risk.durum.kapanan_islem == 1

    def test_ayni_bar_iki_kez_islenemiyor(self) -> None:
        # Aynı bar için ikinci bir karar, canlıda "duplicate order"ın habercisi.
        m = motor_kur()
        bl = barlar(5)
        kosuyu_isle(m, bl)
        with pytest.raises(MotorHatasi, match="zaten işlendi"):
            m.bar_isle(bl[-1])


class TestKaliteGuardi:
    """K-028'in canlıdaki hâli: `ok` olmayan barda ne karar ne fill."""

    def test_backfill_barinda_fill_yapilmiyor(self) -> None:
        # Kopma sonrası REST'ten gelen bar `backfilled`dır — yani bağlı olmadığımız
        # sürede fill iddia etmiyoruz. Faz 6'nın en değerli yan etkisi bu.
        m = motor_kur({20: ("BUY", 0.2)})
        bl = barlar(25)
        bl[21] = replace(bl[21], kaynak=Kaynak.BACKFILL)
        sonuclar = kosuyu_isle(m, bl)
        assert sonuclar[21].fill is None
        assert sonuclar[21].atlama is AtlamaSebebi.FILL_BARI_OK_DEGIL
        assert m.portfoy.miktar == 0.0

    def test_suspect_barda_karar_verilmiyor(self) -> None:
        m = motor_kur({20: ("BUY", 0.2)})
        bl = barlar(25)
        bl[20] = replace(bl[20], volume=0.0, trades=0)
        sonuclar = kosuyu_isle(m, bl)
        assert sonuclar[20].bar_ok is False
        assert sonuclar[20].karar is None


class TestBayatVeriGuardi:
    """Roadmap Faz 6: *"Veri akışı kesildiğinde yeni pozisyon açılmıyor."*"""

    def test_bayat_veride_giris_karari_verilmiyor(self) -> None:
        m = motor_kur({20: ("BUY", 0.2)}, azami_veri_yasi_ms=5_000)
        bl = barlar(25)
        # Barlar geliyor ama nabızlar arasında dakikalar var: akış tıkanmış.
        sonuclar = [m.bar_isle(b, simdi=i * 600_000) for i, b in enumerate(bl)]
        # İlk bar hariç her barda "önceki nabızdan bu yana 600 s geçti".
        assert sonuclar[20].bayat is True
        assert sonuclar[20].karar == "atlandi"
        assert sonuclar[20].red_sebebi == str(AtlamaSebebi.VERI_BAYAT)
        assert m.bekleyen is None

    def test_bayat_veride_cikis_karari_geciyor(self) -> None:
        # Bir çıkışı engellemek riski azaltmaz, artırır (K-037; `AZALTAN_YONLER`).
        #
        # Giriş 16. barda (ATR ısınması için ≥15 bar gerekiyor) ve veri hâlâ taze;
        # çıkış 22. barda ve o an akış on dakikadır sessiz.
        m = motor_kur({16: ("BUY", 0.2), 22: ("FLAT", 0.0)}, azami_veri_yasi_ms=5_000)
        bl = barlar(28)
        sonuclar = []
        for i, b in enumerate(bl):
            an = i * 1000 if i < 20 else 20_000 + (i - 19) * 600_000
            sonuclar.append(m.bar_isle(b, simdi=an))

        assert sonuclar[16].karar == "onay"
        assert sonuclar[17].fill is not None  # pozisyon açıldı

        assert sonuclar[22].bayat is True
        assert sonuclar[22].karar == "onay"  # azaltan niyet bayat veride de geçiyor
        assert sonuclar[23].fill["yon"] == "SAT"
        assert m.portfoy.miktar == 0.0

    def test_bayat_gecisleri_kayda_yaziliyor(self) -> None:
        m = motor_kur(azami_veri_yasi_ms=5_000)
        m.nabiz(1_000)
        assert m.tazelik_kontrol(1_500) is None
        assert m.tazelik_kontrol(100_000) is True
        m.nabiz(100_001)
        assert m.tazelik_kontrol(100_001) is False
        turler = [o["tur"] for o in m.depo.olaylar()]
        assert str(KosuOlayi.BAYAT_GIRIS) in turler
        assert str(KosuOlayi.BAYAT_CIKIS) in turler

    def test_bayat_veri_kesinti_sayilmiyor(self) -> None:
        # §24: bayat veri koşuyu **bölmez**, yalnızca yeni girişi durdurur.
        assert KosuOlayi.BAYAT_GIRIS not in KESINTI_OLAYLARI
        m = motor_kur(azami_veri_yasi_ms=5_000)
        m.nabiz(1_000)
        m.tazelik_kontrol(100_000)
        assert m.depo.kesinti_sayisi() == 0


class TestRiskZorunlulugu:
    def test_promotion_gecmemis_strateji_paper_modunda_reddediliyor(self) -> None:
        # Faz 6'nın gözlem modu tam olarak bu yüzden var (K-035).
        m = motor_kur({20: ("BUY", 0.2)}, mod="paper")
        sonuclar = kosuyu_isle(m, barlar(25))
        assert sonuclar[20].karar == "red"
        assert sonuclar[20].red_sebebi == "promotion_yok"
        assert m.bekleyen is None

    def test_gozlem_modunda_ayni_sinyal_onaylaniyor(self) -> None:
        m = motor_kur({20: ("BUY", 0.2)}, mod="gozlem")
        sonuclar = kosuyu_isle(m, barlar(25))
        assert sonuclar[20].karar == "onay"

    def test_gozlem_modu_diger_limitleri_gevsetmiyor(self) -> None:
        # Gözlem modu yalnızca promotion kapısını atlıyor; boyutlandırma tavanı duruyor.
        m = motor_kur({20: ("BUY", 1.0)}, mod="gozlem")
        sonuclar = kosuyu_isle(m, barlar(25))
        assert sonuclar[20].onayli_maruziyet <= limitler().azami_maruziyet


class TestOzet:
    def test_ozet_dashboardun_bekledigi_alanlari_veriyor(self) -> None:
        m = motor_kur({20: ("BUY", 0.2)})
        kosuyu_isle(m, barlar(30))
        o = m.ozet(simdi=0)
        for ad in ("kosu", "portfoy", "ozkaynak", "maruziyet", "risk", "tazelik", "pencere"):
            assert ad in o
        assert o["risk"]["mod"] == "gozlem"
        assert o["pencere"]["bar_sayisi"] == 30
