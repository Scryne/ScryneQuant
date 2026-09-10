"""Kill switch: K-008'in beş davranışının hepsi. (Roadmap Faz 5 bitti kriteri)

Roadmap kriteri: *"Kill switch tetiklendiğinde K-008'deki beş davranışın hepsi
gerçekleşiyor."* K-008 o beşi şöyle sayıyor:

1. Yeni pozisyon girişi durur — **istisnasız**.
2. Açık pozisyonlar piyasadan **otomatik kapatılmaz**.
3. Mevcut çıkış emirleri (stop / take-profit) **çalışmaya devam eder**.
4. Sistem `SAFE_MODE`'a geçer; bu durumdan çıkış **yalnızca elle onayla** olur.
5. Tetikleyen sebep, o andaki tüm pozisyon ve emir durumuyla birlikte **audit log'a** yazılır.

Her davranışın kendi test sınıfı var (`TestDavranis1` … `TestDavranis5`), çünkü "kill
switch çalışıyor" diye tek bir test, beşten dördünü sessizce atlayabilir.

**İkinci davranış nasıl test edilir** — "otomatik kapatılmaz" bir *yokluk* iddiası, ve
yoklukları test etmek zordur. Burada iki yoldan ölçülüyor: motorun portföye erişimi
olmadığı statik olarak (`risk/` paketinin import grafiğinde `portfolio` yok) ve kill
sonrası pozisyonun yerinde kaldığı davranışsal olarak (backtest koşusunda).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

from scryne_quant.risk.audit import BellekDefteri, OlayTuru, SqliteDefter
from scryne_quant.risk.durum import RiskDurumu, durum_oku, durum_yaz
from scryne_quant.risk.motor import KILL_DRAWDOWN, RiskHatasi, RiskMotoru
from scryne_quant.risk.niyet import OnayliNiyet, Red, RedSebebi
from scryne_quant.strategy.sinyal import Yon
from tests.unit.test_risk_limitleri import BAR, T0, limitler, olcum, sinyal

KOK: Final = Path(__file__).resolve().parents[2] / "src"


def motor_kur(*, defter=None, durum=None, **limit_degisikligi) -> RiskMotoru:
    return RiskMotoru(
        limitler(**limit_degisikligi), "1h", mod="backtest", defter=defter, durum=durum
    )


class TestDavranis1YeniGirisDurur:
    """K-008/1: yeni pozisyon girişi durur — istisnasız."""

    @pytest.mark.parametrize("hedef", [0.01, 0.10, 0.30, 1.0])
    def test_her_buyuklukte_giris_reddedilir(self, hedef):
        m = motor_kur()
        m.kill("TEST_SEBEBI", T0)
        karar = m.degerlendir(sinyal(hedef), olcum())
        assert isinstance(karar, Red)
        assert karar.sebep is RedSebebi.SAFE_MODE

    def test_guven_yuksek_olsa_da_reddedilir(self):
        """`confidence` risk motorunun girdisidir, kararı değil (Sinyal docstring'i)."""
        m = motor_kur()
        m.kill("TEST_SEBEBI", T0)
        from scryne_quant.strategy.sinyal import Sinyal

        kesin = Sinyal(
            symbol="BTCUSDT",
            side=Yon.BUY,
            target_exposure=0.3,
            confidence=1.0,
            reason="COK_EMINIM",
            timestamp=T0,
        )
        assert isinstance(m.degerlendir(kesin, olcum()), Red)

    def test_limitler_gevsek_olsa_da_reddedilir(self):
        """SAFE_MODE her limitin önünde: gevşek limit kill switch'i aşmaz."""
        m = motor_kur(azami_maruziyet=1.0, islem_basina_risk=1.0, volatilite_esigi=10.0)
        m.kill("TEST_SEBEBI", T0)
        assert isinstance(m.degerlendir(sinyal(1.0), olcum()), Red)


class TestDavranis2PozisyonKapatilmaz:
    """K-008/2: açık pozisyonlar piyasadan otomatik kapatılmaz."""

    def test_risk_paketi_portfoye_erisemez(self):
        """Motorun pozisyon kapatma **yetkisi** yok: portföyü hiç import etmiyor.

        Bu, yokluk iddiasını davranışsal değil yapısal olarak ölçüyor — K-003'ün
        izolasyon testiyle aynı mantık. Motor portföyü görmediği sürece, bir gün birinin
        "kill switch pozisyonu kapatsın" diye eklediği kod derlenmez bile.

        `portfolio.durum` hariç tutulmuyor: `PiyasaOlcumu` özkaynağı **sayı olarak**
        alıyor, portföy nesnesi olarak değil. Bu bilinçli; nesneyi alsaydı `sat()`
        çağırmak bir satır uzakta olurdu.
        """
        yasakli = {"scryne_quant.portfolio", "scryne_quant.portfolio.durum"}
        for dosya in (KOK / "scryne_quant" / "risk").rglob("*.py"):
            agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
            for dugum in ast.walk(agac):
                adlar: set[str] = set()
                if isinstance(dugum, ast.Import):
                    adlar = {a.name for a in dugum.names}
                elif isinstance(dugum, ast.ImportFrom) and dugum.module:
                    adlar = {dugum.module}
                assert not adlar & yasakli, (
                    f"{dosya.name} portföyü import ediyor; kill switch'in pozisyon "
                    "kapatma yetkisi olmamalı (K-008/2)"
                )

    def test_kill_sonrasi_pozisyon_yerinde_kalir(self):
        """Davranışsal kanıt: SAFE_MODE açıkken portföy değişmiyor.

        Motorun bir `degerlendir` çağrısı portföye dokunamaz — dönen şey veri.
        """
        m = motor_kur()
        m.bar_isle(T0, 10_000.0)
        m.kill("TEST_SEBEBI", T0)
        onceki = m.durum.son_ozkaynak
        m.degerlendir(sinyal(0.3), olcum(maruziyet=0.25))
        assert m.durum.son_ozkaynak == onceki
        assert m.ozet()["durum"]["safe_mode"] is True


class TestDavranis3CikislarCalisir:
    """K-008/3: mevcut çıkış emirleri çalışmaya devam eder."""

    def test_flat_gecer(self):
        m = motor_kur()
        m.kill("TEST_SEBEBI", T0)
        karar = m.degerlendir(sinyal(0.0, Yon.FLAT), olcum(maruziyet=0.3))
        assert isinstance(karar, OnayliNiyet)
        assert karar.onayli_maruziyet == 0.0

    def test_kismi_satis_gecer(self):
        m = motor_kur()
        m.kill("TEST_SEBEBI", T0)
        karar = m.degerlendir(sinyal(0.1, Yon.SELL), olcum(maruziyet=0.3))
        assert isinstance(karar, OnayliNiyet)
        assert karar.onayli_maruziyet == pytest.approx(0.1)

    def test_cikis_kill_switchten_sonra_da_kisitlanmaz(self):
        """Çıkış hedefi aşağı çekilmiyor: yarım kapatılan bir pozisyon daha riskli."""
        m = motor_kur(azami_maruziyet=0.01, islem_basina_risk=1e-9)
        m.kill("TEST_SEBEBI", T0)
        karar = m.degerlendir(sinyal(0.25, Yon.SELL), olcum(maruziyet=0.3))
        assert isinstance(karar, OnayliNiyet)
        assert karar.onayli_maruziyet == pytest.approx(0.25)
        assert karar.kisitlayan == ()


class TestDavranis4SafeModeEllaOnay:
    """K-008/4: SAFE_MODE'dan çıkış yalnızca elle onayla."""

    def test_kill_safe_mode_acar(self):
        m = motor_kur()
        assert m.durum.safe_mode is False
        m.kill("SEBEP_KODU", T0)
        assert m.durum.safe_mode is True
        assert m.durum.safe_mode_sebep == "SEBEP_KODU"
        assert m.durum.safe_mode_ms == T0

    def test_safe_mode_kendiliginden_kapanmaz(self):
        """Ne gün dönümü, ne yeni bar, ne kazanan işlem SAFE_MODE'u kapatır."""
        m = motor_kur()
        m.bar_isle(T0, 10_000.0)
        m.kill("SEBEP_KODU", T0)
        for gun in range(1, 40):
            m.bar_isle(T0 + gun * 86_400_000, 20_000.0)  # özkaynak ikiye katlandı
            m.islem_kapandi(+500.0, T0 + gun * 86_400_000)
        assert m.durum.safe_mode is True
        assert isinstance(m.degerlendir(sinyal(), olcum(ozkaynak=20_000.0)), Red)

    def test_serbest_birakma_gerekce_ister(self):
        m = motor_kur()
        m.kill("SEBEP_KODU", T0)
        with pytest.raises(RiskHatasi, match="gerekçe ister"):
            m.serbest_birak("ok", T0)
        assert m.durum.safe_mode is True

    def test_gerekceli_serbest_birakma_calisir(self):
        m = motor_kur()
        m.kill("SEBEP_KODU", T0)
        m.serbest_birak("veri akışı düzeldi, boşluk dolduruldu", T0 + BAR)
        assert m.durum.safe_mode is False
        assert isinstance(m.degerlendir(sinyal(), olcum(bar_ms=T0 + BAR)), OnayliNiyet)

    def test_kapaliyken_serbest_birakma_hata(self):
        with pytest.raises(RiskHatasi, match="açık değil"):
            motor_kur().serbest_birak("gerekçe metni burada", T0)

    def test_ilk_sebep_korunur(self):
        """İkinci tetikleyici birincinin **sonucu** olabilir; kök nedeni silmemeli."""
        m = motor_kur()
        m.kill("ILK_SEBEP", T0)
        m.kill("IKINCI_SEBEP", T0 + BAR)
        assert m.durum.safe_mode_sebep == "ILK_SEBEP"
        assert m.durum.safe_mode_ms == T0

    def test_risk_paketinde_otomatik_serbest_birakma_yok(self):
        """`serbest_birak`/`RiskDurumu.serbest_birak` `risk/` içinde koşula bağlı çağrılmıyor.

        Bu test, kill switch'i kendini kapatan bir uyarıya çeviren kodu yakalar. İzin
        verilen tek çağrı `RiskMotoru.serbest_birak`ın kendi gövdesindeki
        `self.durum.serbest_birak()` — yani elle onay yolunun ta kendisi.
        """
        bulunan: list[str] = []
        for dosya in (KOK / "scryne_quant" / "risk").rglob("*.py"):
            agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
            for fonksiyon in ast.walk(agac):
                if not isinstance(fonksiyon, ast.FunctionDef):
                    continue
                if fonksiyon.name == "serbest_birak":
                    continue  # elle onay yolunun kendisi
                for dugum in ast.walk(fonksiyon):
                    if (
                        isinstance(dugum, ast.Call)
                        and isinstance(dugum.func, ast.Attribute)
                        and dugum.func.attr == "serbest_birak"
                    ):
                        bulunan.append(f"{dosya.name}:{fonksiyon.name}")
        assert not bulunan, (
            "SAFE_MODE kod içinden kapatılıyor — kendini kapatan bir kill switch bir "
            f"uyarıdır (K-008/4): {', '.join(bulunan)}"
        )

    def test_safe_mode_surec_arasinda_korunur(self, tmp_path):
        """Bir çöküşle sıfırlanan kill switch, kill switch değildir.

        Faz 6'nın restart kriterinin risk tarafı: durum diskten aynen geri geliyor.
        """
        m = motor_kur()
        m.bar_isle(T0, 10_000.0)
        m.kill("DRAWDOWN_LIMITI", T0)
        yol = durum_yaz(m.durum, tmp_path / "risk-durum.json")

        geri = durum_oku(yol)
        assert geri.safe_mode is True
        assert geri.safe_mode_sebep == "DRAWDOWN_LIMITI"
        assert geri.safe_mode_ms == T0
        assert geri.zirve_ozkaynak == 10_000.0

        yeni_motor = motor_kur(durum=geri)
        assert isinstance(yeni_motor.degerlendir(sinyal(), olcum()), Red)

    def test_eksik_durum_dosyasi_guvenli_yone_duser(self, tmp_path):
        d = durum_oku(tmp_path / "yok.json")
        assert d.safe_mode is False
        assert d.zirve_ozkaynak == 0.0
        assert d.bar_sayisi == 0


class TestDavranis5AuditKaydi:
    """K-008/5: sebep + o andaki tüm durum audit log'a yazılır."""

    def test_kill_audite_yazilir(self):
        defter = BellekDefteri()
        m = motor_kur(defter=defter)
        m.bar_isle(T0, 10_000.0)
        m.kill("SEBEP_KODU", T0, {"ek_bilgi": 42})

        killler = [o for o in defter.olaylar if o.tur is OlayTuru.KILL]
        assert len(killler) == 1
        olay = killler[0]
        assert olay.govde["sebep"] == "SEBEP_KODU"
        assert olay.govde["ek_bilgi"] == 42
        assert olay.zaman_ms == T0

    def test_kayit_tum_durumu_tasiyor(self):
        """"O andaki tüm durumla" — kaydın eksik alanı olmamalı."""
        defter = BellekDefteri()
        m = motor_kur(defter=defter)
        m.bar_isle(T0, 10_000.0)
        m.kill("SEBEP_KODU", T0)

        durum = next(o for o in defter.olaylar if o.tur is OlayTuru.KILL).durum
        for alan in RiskDurumu().sozluk():
            assert alan in durum, f"audit kaydında eksik durum alanı: {alan}"
        assert durum["mod"] == "backtest"
        assert durum["limit_kimligi"]

    def test_drawdown_killinin_sayisal_dayanagi_kayitta(self):
        """"Drawdown tetikledi" cümlesi sayı olmadan altı ay sonra hiçbir şey anlatmaz."""
        defter = BellekDefteri()
        m = motor_kur(defter=defter)
        m.bar_isle(T0, 10_000.0)
        yarin = T0 + 86_400_000
        m.bar_isle(yarin, 7_000.0)
        m.degerlendir(sinyal(), olcum(bar_ms=yarin, ozkaynak=7_000.0))

        kill = next(o for o in defter.olaylar if o.tur is OlayTuru.KILL)
        assert kill.govde["sebep"] == KILL_DRAWDOWN
        assert kill.govde["drawdown"] == pytest.approx(0.30)
        assert kill.govde["limit"] == pytest.approx(0.20)
        assert kill.govde["zirve_ozkaynak"] == 10_000.0
        assert kill.govde["son_ozkaynak"] == 7_000.0

    def test_serbest_birakma_gerekcesi_audite_yazilir(self):
        defter = BellekDefteri()
        m = motor_kur(defter=defter)
        m.kill("ILK_SEBEP", T0)
        m.serbest_birak("veri boşluğu dolduruldu, yeniden doğrulandı", T0 + BAR)

        serbest = next(o for o in defter.olaylar if o.tur is OlayTuru.SERBEST)
        assert serbest.govde["onceki_sebep"] == "ILK_SEBEP"
        assert "veri boşluğu" in serbest.govde["gerekce"]

    def test_cooldown_audite_yazilir(self):
        defter = BellekDefteri()
        m = motor_kur(defter=defter, ardisik_kayip_limiti=2, cooldown_bar=5)
        m.islem_kapandi(-10.0, T0)
        m.islem_kapandi(-10.0, T0 + BAR)

        cd = [o for o in defter.olaylar if o.tur is OlayTuru.COOLDOWN]
        assert len(cd) == 1
        assert cd[0].govde["cooldown_bar"] == 5
        assert cd[0].govde["bitis_ms"] == T0 + BAR + 5 * BAR

    def test_kill_kaydi_diskte_kalici(self, tmp_path):
        """Gerçek deftere yazıldığında kayıt süreçten sonra da orada."""
        yol = tmp_path / "audit.sqlite"
        with SqliteDefter(yol) as defter:
            m = motor_kur(defter=defter)
            m.bar_isle(T0, 10_000.0)
            m.kill("SEBEP_KODU", T0)

        with SqliteDefter(yol) as tekrar:
            killler = tekrar.oku(tur=OlayTuru.KILL)
            assert len(killler) == 1
            assert killler[0]["govde"]["sebep"] == "SEBEP_KODU"
            assert tekrar.dogrula() is True
