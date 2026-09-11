"""Limit emri ve iptal yolu. (K-047 — Faz 7'nin ölçmediği ikinci madde)

Faz 7 market emriyle çalıştı ve iptal yolunu bilerek açık bıraktı: *"`CANCELED` yolu
state machine'de tanımlı ama gerçek borsaya karşı hiç yürütülmedi."* Tanımlı ama hiç
yürütülmemiş bir yol, çalıştığı **sanılan** bir yoldur — ve bu projede en pahalı hata
sınıfı orada yaşar.

Bu dosyanın merkezinde tek bir değişmez var ve iptalin bütün zorluğu ondan geliyor:

> **Maruziyetin var olduğunu varsay.**

Gönderimde bu, kaydı ağ çağrısından *önce* yazmak demekti (emir olmuş olabilir). İptalde
tam tersi yönde aynı şey: kaydı yanıt doğrulandıktan *sonra* yazmak (emir hâlâ duruyor
olabilir). İkisi de aynı tarafa yanılıyor, ve o taraf güvenli olan — çünkü yanlış tarafa
yanılmanın bedeli, "pozisyonum yok" sanıp maruziyeti ikiye katlamak.
"""

from __future__ import annotations

import pytest

from scryne_quant.exchange.emir_adaptoru import Varlik
from scryne_quant.exchange.hatalar import BelirsizSonuc, GonderilemediHatasi
from scryne_quant.exchange.kurallar import KuralIhlali, fiyat_uydur
from scryne_quant.execution.motor import EmirMotoru, ExecutionHatasi
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.oms.emir import EmirDurumu, emir_kur, istemci_kimligi
from scryne_quant.oms.pozisyon import cipa_at, pozisyon_mutabakati
from scryne_quant.strategy.sinyal import Yon
from tests.unit.test_mutabakat import FIYAT, SahteBorsa, niyet

MIKTAR = 0.001

#: Dolmayacak kadar uzak bir alış fiyatı — emir defterde bekler ve para kilitlenir.
UZAK_ALIS = 60_000.0

#: Hemen dolacak bir alış fiyatı (piyasanın üstünde).
YAKIN_ALIS = 80_000.0


@pytest.fixture
def kurulum(tmp_path):
    defter = EmirDefteri(tmp_path / "kosu.sqlite")
    borsa = SahteBorsa()
    cipa_at(defter, borsa, not_metni="limit testi")
    yield defter, borsa, EmirMotoru(defter, borsa)
    defter.kapat()


class TestFiyatYuvarlamasi:
    """Yön bağımlı ve miktarınkiyle aynı ilkeden: emir istenenden saldırgan olamaz."""

    def test_alis_asagi_satis_yukari(self) -> None:
        assert fiyat_uydur(77_146.017, 0.01, yon="BUY") == pytest.approx(77_146.01)
        assert fiyat_uydur(77_146.017, 0.01, yon="SELL") == pytest.approx(77_146.02)

    def test_tam_tick_kaymiyor(self) -> None:
        """Kayan nokta yüzünden tam katların bir tick kayması, `miktar_uydur`un da
        engellediği hata. İki yönde de kaymamalı."""
        for yon in ("BUY", "SELL"):
            assert fiyat_uydur(77_146.00, 0.01, yon=yon) == pytest.approx(77_146.00)
            assert fiyat_uydur(0.30, 0.1, yon=yon) == pytest.approx(0.30)

    def test_gecersiz_fiyat_reddediliyor(self) -> None:
        with pytest.raises(KuralIhlali):
            fiyat_uydur(0.0, 0.01, yon="BUY")
        with pytest.raises(KuralIhlali):
            fiyat_uydur(100.0, 0.0, yon="BUY")


class TestLimitGonderimi:
    def test_dolmayan_limit_acik_kaliyor(self, kurulum) -> None:
        defter, borsa, motor = kurulum
        sonuc = motor.gonder(niyet(), MIKTAR, limit_fiyati=UZAK_ALIS)

        assert sonuc.emir.durum is EmirDurumu.ACKNOWLEDGED
        assert sonuc.emir.tur == "LIMIT"
        assert sonuc.emir.limit_fiyati == pytest.approx(UZAK_ALIS)
        assert borsa.acik_emirler("BTCUSDT")

    def test_marketable_limit_hemen_doluyor(self, kurulum) -> None:
        _, _, motor = kurulum
        sonuc = motor.gonder(niyet(), MIKTAR, limit_fiyati=YAKIN_ALIS)
        assert sonuc.emir.durum is EmirDurumu.FILLED
        # Borsa limitten değil, **daha iyi** olan piyasa fiyatından doldurur.
        assert sonuc.emir.ortalama_fiyat == pytest.approx(FIYAT)

    def test_defterdeki_fiyat_borsaya_gidenle_ayni(self, kurulum) -> None:
        """Tick'e uydurma **deftere yazmadan önce** olmalı.

        Sonra yapılsaydı "hangi fiyattan emir verdim" sorusunun iki cevabı olurdu:
        defterdeki ham fiyat ve borsadaki uydurulmuş fiyat.
        """
        _, _, motor = kurulum
        sonuc = motor.gonder(niyet(), MIKTAR, limit_fiyati=60_000.017)
        assert sonuc.emir.limit_fiyati == pytest.approx(60_000.01)

    def test_ayni_niyet_market_ve_limit_tek_emir(self, kurulum) -> None:
        """**Fiyat kimliğe girmiyor** ve bu kasıtlı.

        Girseydi aynı karar farklı fiyatlarla defalarca emre dönüşebilirdi — "market
        denedim olmadı, limit de deneyeyim" — yani execution katmanı kendi başına yeni
        maruziyet kararları üretirdi (değişmez kural 3).
        """
        _, borsa, motor = kurulum
        ilk = motor.gonder(niyet(), MIKTAR)
        ikinci = motor.gonder(niyet(), MIKTAR, limit_fiyati=UZAK_ALIS)

        assert ilk.emir.istemci_kimligi == ikinci.emir.istemci_kimligi
        assert not ikinci.gonderildi
        assert len(borsa.gonderimler) == 1

    def test_limit_emri_kimligi_turden_bagimsiz(self) -> None:
        """Kimlik yalnızca niyetten türüyor — tür ve fiyat ona dokunmuyor."""
        n = niyet()
        market = emir_kur(n, MIKTAR, zaman_ms=1)
        limit = emir_kur(n, MIKTAR, zaman_ms=1, tur="LIMIT", limit_fiyati=UZAK_ALIS)
        assert market.istemci_kimligi == limit.istemci_kimligi == istemci_kimligi(n)


class TestIptal:
    def test_acik_emir_iptal_ediliyor(self, kurulum) -> None:
        defter, borsa, motor = kurulum
        gonderim = motor.gonder(niyet(), MIKTAR, limit_fiyati=UZAK_ALIS)

        sonuc = motor.iptal(gonderim.emir.istemci_kimligi)
        assert sonuc.iptal_edildi
        assert sonuc.emir.durum is EmirDurumu.CANCELED
        assert defter.al(gonderim.emir.istemci_kimligi).durum is EmirDurumu.CANCELED
        assert not borsa.acik_emirler("BTCUSDT")

    def test_nihai_emir_icin_aga_cikilmiyor(self, kurulum) -> None:
        """İptal edilecek bir şey yokken yazma isteği göndermek saf risk.

        Yanıtı kaybolursa çözülmesi gereken yeni bir belirsizlik doğar — hiçbir şey
        kazanmadan.
        """
        _, borsa, motor = kurulum
        gonderim = motor.gonder(niyet(), MIKTAR)  # market → FILLED
        sonuc = motor.iptal(gonderim.emir.istemci_kimligi)

        assert not sonuc.gonderildi
        assert borsa.iptaller == []
        assert sonuc.emir.durum is EmirDurumu.FILLED

    def test_defterde_olmayan_emir_iptal_edilemez(self, kurulum) -> None:
        _, _, motor = kurulum
        with pytest.raises(ExecutionHatasi, match="defterde yok"):
            motor.iptal("sqolmayan")

    def test_belirsiz_iptal_defteri_degistirmiyor(self, kurulum) -> None:
        """**Bu dosyanın en önemli testi.**

        Yanıtı kaybolan bir iptal, emrin iptal edildiğini **kanıtlamaz**. `CANCELED`
        yazmak duran bir maruziyeti kapanmış göstermek olur; sistem "pozisyonum yok"
        sanıp yeni emir gönderir ve maruziyet ikiye katlanır.
        """
        defter, borsa, motor = kurulum
        gonderim = motor.gonder(niyet(), MIKTAR, limit_fiyati=UZAK_ALIS)
        kimlik = gonderim.emir.istemci_kimligi

        borsa.iptal_hatasi = BelirsizSonuc("yanıt kayboldu")
        sonuc = motor.iptal(kimlik)

        assert sonuc.belirsiz and not sonuc.iptal_edildi
        assert defter.al(kimlik).durum is EmirDurumu.ACKNOWLEDGED, (
            "belirsiz bir iptal defteri değiştirdi — duran bir maruziyet kapanmış "
            "gösteriliyor"
        )

    def test_gonderilemeyen_iptal_tekrar_denenebilir(self, kurulum) -> None:
        """İstek hiç çıkmadıysa emir de defter de olduğu gibi; iptal güvenle tekrarlanır."""
        defter, borsa, motor = kurulum
        gonderim = motor.gonder(niyet(), MIKTAR, limit_fiyati=UZAK_ALIS)
        kimlik = gonderim.emir.istemci_kimligi

        borsa.iptal_hatasi = GonderilemediHatasi("ağ yok")
        ilk = motor.iptal(kimlik)
        assert not ilk.gonderildi and not ilk.belirsiz
        assert defter.al(kimlik).durum is EmirDurumu.ACKNOWLEDGED

        ikinci = motor.iptal(kimlik)
        assert ikinci.iptal_edildi

    def test_dolmus_emrin_iptali_gercek_durumu_yaziyor(self, kurulum) -> None:
        """İptal ile fill yarıştı ve fill kazandı.

        Borsa "böyle bir emir yok" diyor (`-2011`). Bu bir başarısızlık değil, emrin bu
        arada dolduğunun haberi — ve doğru tepki tahmin yürütmek değil **sorgulamak**.
        """
        defter, borsa, motor = kurulum
        gonderim = motor.gonder(niyet(), MIKTAR, limit_fiyati=UZAK_ALIS)
        kimlik = gonderim.emir.istemci_kimligi

        # Emir defterin haberi olmadan doldu: borsa tarafında durum değişti.
        borsa.sessizce_doldur(kimlik)

        sonuc = motor.iptal(kimlik)
        assert sonuc.borsa_tanimiyor and not sonuc.iptal_edildi
        assert defter.al(kimlik).durum is EmirDurumu.FILLED, (
            "iptal edilemeyen emrin gerçek durumu deftere yazılmadı"
        )

    def test_iptal_edilen_emir_iki_kez_iptal_edilmiyor(self, kurulum) -> None:
        _, borsa, motor = kurulum
        gonderim = motor.gonder(niyet(), MIKTAR, limit_fiyati=UZAK_ALIS)
        kimlik = gonderim.emir.istemci_kimligi

        motor.iptal(kimlik)
        borsa.iptaller.clear()
        ikinci = motor.iptal(kimlik)

        assert not ikinci.gonderildi
        assert borsa.iptaller == []


class TestPozisyonlaBirlikte:
    """Limit yolunun pozisyon mutabakatıyla kesiştiği yer: kilitli bakiye."""

    def test_acik_limit_emri_fark_uretmiyor(self, kurulum) -> None:
        """Açık emir parayı kilitler; `toplam` değişmediği için mutabakat temiz kalmalı.

        Faz 7'nin `bakiye()`si yalnızca `free` okuyordu — bu test o hâliyle **kırmızı**
        olurdu ve kırılma sessiz değil gürültülü olurdu: her açık limit emrinde koşu
        dururdu.
        """
        defter, borsa, motor = kurulum
        motor.gonder(niyet(), MIKTAR, limit_fiyati=UZAK_ALIS)

        kilitli = borsa.bakiye()["USDT"].kilitli
        assert kilitli > 0.0, "sahte borsa kilitlemedi; test bir şey ölçmüyor"

        sonuc = pozisyon_mutabakati(defter, borsa, "BTCUSDT")
        assert not sonuc.halt, sonuc.ozet()

    def test_iptalden_sonra_kilit_cozuluyor(self, kurulum) -> None:
        defter, borsa, motor = kurulum
        gonderim = motor.gonder(niyet(), MIKTAR, limit_fiyati=UZAK_ALIS)
        motor.iptal(gonderim.emir.istemci_kimligi)

        assert borsa.bakiye()["USDT"].kilitli == pytest.approx(0.0)
        assert not pozisyon_mutabakati(defter, borsa, "BTCUSDT").halt

    def test_iptal_edilen_emir_akisa_girmiyor(self, kurulum) -> None:
        """Dolmamış bir emir pozisyona hiç dokunmaz — `CANCELED` olsa da olmasa da."""
        defter, borsa, motor = kurulum
        gonderim = motor.gonder(niyet(), MIKTAR, limit_fiyati=UZAK_ALIS)
        motor.iptal(gonderim.emir.istemci_kimligi)

        sonuc = pozisyon_mutabakati(defter, borsa, "BTCUSDT")
        assert all(f.akis == 0.0 for f in sonuc.farklar)


class TestSatisYonu:
    def test_satis_limiti_yukari_yuvarlaniyor(self, kurulum) -> None:
        """`FLAT` borsada `SELL`e çevriliyor ve yuvarlama o yöne göre yapılmalı."""
        _, borsa, motor = kurulum
        motor.gonder(niyet(), MIKTAR)  # önce pozisyon aç
        borsa.varliklar["USDT"] = Varlik(serbest=borsa.varliklar["USDT"].serbest)

        sonuc = motor.gonder(
            niyet(0.0, Yon.FLAT, zaman=1_700_000_003_600_000),
            MIKTAR,
            limit_fiyati=90_000.017,
        )
        assert sonuc.emir.limit_fiyati == pytest.approx(90_000.02)
        assert sonuc.emir.durum is EmirDurumu.ACKNOWLEDGED
