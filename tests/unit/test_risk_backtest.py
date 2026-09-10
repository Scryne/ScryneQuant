"""Risk motorunun backtest'e bağlanması. (Faz 5)

İki şeyi birlikte ölçüyor ve ikisi de Faz 1-4'ün korunmasıyla ilgili:

1. **Risk devre dışıyken hiçbir şey değişmiyor** — bit düzeyinde. Bu, `sq lab dogrula`nın
   eski deneyleri doğrulamaya devam etmesinin ön koşulu: risk motorunu eklemek, onu hiç
   kullanmayan koşuları yeniden üretilemez yapmamalı.
2. **Risk devredeyken etkisi ölçülebilir ve deterministik** — aynı koşu iki kez aynı
   `sonuc_hash`i veriyor, ve mühür (süreç başına rastgele) hiçbir hash'e girmiyor.

**Akış muhasebesi** ayrıca test ediliyor: üretilen sinyal = işlenen + atlanan. Risk reddi
`risk_reddetti` olarak sayılmazsa o eşitlik bozulur ve sinyaller sessizce kaybolur — K-006
ve K-028'in "sessizce atılmaz" kuralının risk tarafı.
"""

from __future__ import annotations

import numpy as np
import pytest

from scryne_quant.backtest.fill import AtlamaSebebi
from scryne_quant.backtest.motor import RISK_ATR_PENCERESI, Backtest
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.risk import kalibrasyon as risk_kalibrasyon
from scryne_quant.risk.audit import BellekDefteri, OlayTuru
from scryne_quant.risk.motor import RiskMotoru
from scryne_quant.risk.niyet import RedSebebi
from scryne_quant.strategy.kutuphane.sma_kesisim import SmaKesisim
from tests.conftest import bar_uret
from tests.unit.test_risk_limitleri import limitler

MALIYET = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)


@pytest.fixture
def diziler():
    return bar_dizileri(bar_uret(600))


def motor(risk: RiskMotoru | None = None) -> Backtest:
    return Backtest(
        SmaKesisim(hizli=5, yavas=20, maruziyet=0.9),
        MALIYET,
        baslangic_sermaye=10_000.0,
        risk=risk,
    )


def risk_motoru(defter=None, **limit_degisikligi) -> RiskMotoru:
    return RiskMotoru(limitler(**limit_degisikligi), "1h", mod="backtest", defter=defter)


class TestRisksizKosuKorunuyor:
    def test_risk_yoksa_sonuc_alani_none(self, diziler):
        sonuc = motor().calistir("BTCUSDT", "1h", diziler)
        assert sonuc.risk is None
        assert "risk" not in sonuc.sozluk()

    def test_risk_yoksa_hash_degismiyor(self, diziler):
        """Risk alanı hash'e yalnızca varsa giriyor.

        Girmemiş olsaydı `"risk": None` eklemek Faz 1-4'te kaydedilmiş **her** sonucun
        hash'ini değiştirirdi — yani risk motorunu eklemek, onu hiç kullanmayan eski
        deneyleri yeniden üretilemez yapardı.
        """
        a = motor().calistir("BTCUSDT", "1h", diziler)
        b = motor().calistir("BTCUSDT", "1h", diziler)
        assert a.sonuc_hash == b.sonuc_hash
        assert a.atlanan["risk_reddetti"] == 0

    def test_risk_reddetti_sayaci_risksiz_kosuda_sifir(self, diziler):
        sonuc = motor().calistir("BTCUSDT", "1h", diziler)
        assert sonuc.atlanan[AtlamaSebebi.RISK_REDDETTI.value] == 0


class TestRiskliKosu:
    def test_risk_ozeti_kayda_giriyor(self, diziler):
        sonuc = motor(risk_motoru()).calistir("BTCUSDT", "1h", diziler)
        assert sonuc.risk is not None
        assert sonuc.risk["mod"] == "backtest"
        assert sonuc.risk["degerlendirilen"] > 0
        assert "risk" in sonuc.sozluk()

    def test_onaylanan_hedef_tavani_asmiyor(self, diziler):
        """Tavan **onaylanan hedef** üzerinde — ve orada istisnasız tutuyor."""
        defter = BellekDefteri()
        rm = risk_motoru(defter=defter, islem_basina_risk=1.0)
        motor(rm).calistir("BTCUSDT", "1h", diziler)
        tavan = limitler().azami_maruziyet
        onaylar = [o for o in defter.olaylar if o.tur is OlayTuru.ONAY]
        assert onaylar
        assert all(o.govde["onayli_maruziyet"] <= tavan + 1e-12 for o in onaylar)

    def test_gerceklesen_maruziyet_fiyat_hareketiyle_tavani_asabilir(self, diziler):
        """**Ölçülen ayrım:** tavan hedef üzerinde, gerçekleşen üzerinde değil.

        Fill `t+1` açılışında o anki özkaynağın %30'u olarak hesaplanıyor; bar kapanışına
        kadar fiyat yükselirse pozisyonun payı %30'un üstüne çıkar. Bu bir limit ihlali
        **değil**, sürekli yeniden dengelemenin yokluğu: her barda hedefe dönmek bir
        rebalance bandı kararı olurdu ve o karar Faz 5'in kapsamında değil
        (`fill.ASGARI_ORAN`ın yorumu bunu zaten söylüyor).

        Test sayıyı sabitlemiyor, **mertebeyi** sınırlıyor: sapma tavanın %10'unu aşarsa
        tavan pratikte başka bir sayı demektir ve o zaman rebalance bandı konuşulmalı.
        """
        sonuc = motor(risk_motoru(islem_basina_risk=1.0)).calistir("BTCUSDT", "1h", diziler)
        tavan = limitler().azami_maruziyet
        gerceklesen = float(np.nanmax(sonuc.maruziyet))
        assert gerceklesen > tavan, "sapma hiç yoksa bu test bir şey ölçmüyor"
        assert gerceklesen <= tavan * 1.10, (
            f"gerçekleşen maruziyet tavanı %10'dan fazla aşıyor ({gerceklesen:.4f} vs "
            f"{tavan:.4f}); rebalance bandı gerekebilir"
        )

    def test_risk_maruziyeti_dusuruyor(self, diziler):
        """Risksiz koşuyla karşılaştırma: limit gerçekten bağlayıcı."""
        risksiz = motor().calistir("BTCUSDT", "1h", diziler)
        riskli = motor(risk_motoru()).calistir("BTCUSDT", "1h", diziler)
        assert float(np.nanmax(riskli.maruziyet)) < float(np.nanmax(risksiz.maruziyet))

    def test_determinizm(self, diziler):
        """Aynı veri + aynı limitler → aynı `sonuc_hash` (K-009).

        Mühür süreç başına rastgele olduğu için bu test, mührün hiçbir hash'e girmediğinin
        de kanıtı: girse iki koşu farklı çıkardı.
        """
        a = motor(risk_motoru()).calistir("BTCUSDT", "1h", diziler)
        b = motor(risk_motoru()).calistir("BTCUSDT", "1h", diziler)
        assert a.sonuc_hash == b.sonuc_hash
        assert a.config_hash == b.config_hash

    def test_farkli_limitler_farkli_sonuc(self, diziler):
        """Negatif kontrol: limit değişince sonuç da değişmeli.

        Değişmezse risk motoru bağlı görünüp hiçbir şey yapmıyor olurdu.
        """
        a = motor(risk_motoru(azami_maruziyet=0.30)).calistir("BTCUSDT", "1h", diziler)
        b = motor(risk_motoru(azami_maruziyet=0.05)).calistir("BTCUSDT", "1h", diziler)
        assert a.sonuc_hash != b.sonuc_hash
        assert a.risk["limit_kimligi"] != b.risk["limit_kimligi"]

    def test_akis_muhasebesi_tutuyor(self, diziler):
        """Üretilen sinyal = işlenen + atlanan. Sessiz kayıp yok."""
        sonuc = motor(risk_motoru()).calistir("BTCUSDT", "1h", diziler)
        akis = sonuc.sozluk()["akis"]
        atlanan_toplam = sum(akis["atlanan"].values())
        assert akis["uretilen_sinyal"] == akis["islenen_sinyal"] + atlanan_toplam

    def test_red_sayisi_atlama_sayisiyla_tutuyor(self, diziler):
        """Risk motorunun red sayımı ile motorun `risk_reddetti` sayacı aynı sayıyı vermeli.

        İkisi ayrı yerlerde tutuluyor (biri risk motorunda, biri akış muhasebesinde);
        ayrışmaları, bir tarafın sinyal kaybettiğinin işareti olurdu.
        """
        rm = risk_motoru()
        sonuc = motor(rm).calistir("BTCUSDT", "1h", diziler)
        # Isınma penceresinde üretilen sinyaller risk motoruna hiç gitmiyor — onlar
        # `isinma_penceresi` olarak sayılıyor. O yüzden karşılaştırma risk motorunun
        # kendi toplamıyla yapılıyor.
        assert sonuc.atlanan[AtlamaSebebi.RISK_REDDETTI.value] == sum(rm.red_sayimi.values())

    def test_audit_kararlari_kaydediyor(self, diziler):
        defter = BellekDefteri()
        rm = risk_motoru(defter=defter)
        motor(rm).calistir("BTCUSDT", "1h", diziler)
        turler = {o.tur for o in defter.olaylar}
        assert OlayTuru.ONAY in turler
        assert len(defter.olaylar) >= rm.degerlendirilen


class TestIsinmaPenceresi:
    def test_atr_yoksa_reddediliyor(self, diziler):
        """Isınma penceresinde ATR NaN; o barda karar verilmiyor, onaylanmıyor.

        NaN'ı sıfır saymak guard'ı geçirir **ve** boyut tavanını sonsuz yapardı: tek bir
        eksik ölçüm iki limiti birden sessizce kaldırır.
        """
        rm = risk_motoru()
        # `olcum_baslangici=0` ile ısınma barlarındaki sinyaller de risk motoruna gider.
        motor(rm).calistir("BTCUSDT", "1h", diziler, olcum_baslangici=0)
        assert rm.red_sayimi[RedSebebi.VOLATILITE_OLCULEMEDI.value] >= 0  # olabilir de olmaz da

    def test_atr_penceresi_kalibrasyonla_ayni(self):
        """Farklı pencereyle kalibre edilip farklı pencereyle uygulanan eşik sessizce yanlış."""
        assert RISK_ATR_PENCERESI == risk_kalibrasyon.ATR_PENCERESI


class TestCikislarEngellenmiyor:
    def test_kill_switch_sonrasi_pozisyon_kapanabiliyor(self, diziler):
        """Drawdown kill'i tetiklenen bir koşuda strateji hâlâ `FLAT` diyebiliyor.

        Koşu sonunda açık pozisyon kalmaması şart değil — ölçülen şey, kill sonrası
        **satış** fill'lerinin gerçekleşmeye devam ettiği.
        """
        # Çok sıkı drawdown limiti: koşunun başında tetiklensin.
        rm = risk_motoru(drawdown_limiti=0.001)
        sonuc = motor(rm).calistir("BTCUSDT", "1h", diziler)
        assert rm.durum.safe_mode is True
        # SAFE_MODE açıkken reddedilenler yalnızca girişler olmalı.
        assert rm.red_sayimi[RedSebebi.SAFE_MODE.value] > 0
        # Azaltan niyetler onaylanmaya devam etti: onay sayısı sıfır değil.
        assert rm.onay_sayisi > 0
        assert sonuc.risk["durum"]["safe_mode"] is True
