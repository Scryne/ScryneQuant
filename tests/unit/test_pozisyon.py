"""Pozisyon mutabakatı. (Faz 8 kriteri: *"açıklanamayan pozisyon farkı: sıfır"*)

Faz 7 bu ölçümü bilerek yapmadı ve sebebini yazdı: bağımsız bir açılış kaydı olmadan
yapılan karşılaştırma *"borsa ne diyorsa o"* demenin süslü hâli olur. Bu dosya o kaydın
kurulduğunu ve karşılaştırmanın **gerçekten bir şey ölçtüğünü** kanıtlıyor.

Bir ölçümün bir şey ölçtüğünü göstermenin tek yolu, ölçtüğü şey bozulduğunda **bozulması**.
O yüzden testlerin çoğu temiz yolu değil, bozuk yolları sürüyor: komisyonu unutulan emir,
çıpası olmayan koşu, dışarıdan para giren hesap, tazelenmeye çalışılan çıpa.

`SahteBorsa` `test_mutabakat`ten alınıyor ve orada gerçek bir muhasebe tutuyor: her fill
bakiyeyi değiştiriyor ve komisyon alınan varlıktan kesiliyor. Sabit bakiye döndüren bir
sahteye karşı bu testlerin hiçbiri anlamlı olmazdı.
"""

from __future__ import annotations

import pytest

from scryne_quant.exchange.emir_adaptoru import Varlik
from scryne_quant.exchange.hatalar import GonderilemediHatasi
from scryne_quant.execution.motor import EmirMotoru
from scryne_quant.oms.defter import DefterHatasi, EmirDefteri
from scryne_quant.oms.emir import EmirDurumu
from scryne_quant.oms.pozisyon import (
    CipaYok,
    PozisyonHatasi,
    PozisyonUyusmazligi,
    cipa_at,
    pozisyon_mutabakati,
)
from scryne_quant.strategy.sinyal import Yon
from tests.unit.test_mutabakat import (
    ACILIS_BTC,
    ACILIS_USDT,
    KOMISYON_ORANI,
    SahteBorsa,
    niyet,
)

MIKTAR = 0.001


@pytest.fixture
def kurulum(tmp_path):
    """Çıpası atılmış, hiç emir girmemiş bir koşu."""
    defter = EmirDefteri(tmp_path / "kosu.sqlite")
    borsa = SahteBorsa()
    cipa_at(defter, borsa, not_metni="test")
    yield defter, borsa, EmirMotoru(defter, borsa)
    defter.kapat()


class TestCipa:
    """Çıpa olmadan ölçüm yok; çıpa değişirse ölçüm yalan."""

    @pytest.mark.parametrize("durdur", [True, False])
    def test_cipasiz_kosu_mutabakat_yapamaz(self, tmp_path, durdur) -> None:
        """Çıpa yokluğu bir **ölçülemezlik**, uyuşmazlık değil — ayrı istisna.

        İkisini aynı yere toplamak, "ölçtüm ve fark buldum" ile "ölçemedim" arasındaki
        farkı silerdi (K-039'un aynı ayrımı). `durdur=False` de kurtarmıyor: rapor modu,
        hiç yapılmamış bir ölçümü "temiz" diye raporlayamaz.
        """
        defter = EmirDefteri(tmp_path / "cipasiz.sqlite")
        with pytest.raises(CipaYok):
            pozisyon_mutabakati(defter, SahteBorsa(), "BTCUSDT", durdur=durdur)
        defter.kapat()

    def test_cipa_ikinci_kez_atilamaz(self, kurulum) -> None:
        defter, borsa, _ = kurulum
        with pytest.raises(DefterHatasi, match="zaten yazılmış"):
            cipa_at(defter, borsa)

    def test_cipa_guncellenemez(self, kurulum) -> None:
        """Tetik seviyesinde: 'çıpayı tazele' diye bir yol **yok**.

        Bu testin koruduğu şey bir API değil bir mekanizma. `acilis_yaz` kapatılsa bile
        bağlantı üzerinden doğrudan `UPDATE` çalıştırmak da reddedilmeli — aksi hâlde
        açıklanamayan bir fark, araştırılmak yerine sıfırlanabilirdi.
        """
        defter, _, _ = kurulum
        with pytest.raises(Exception, match="değiştirilemez"):
            defter._baglanti.execute(  # noqa: SLF001 — tetiği doğrudan sınamak şart
                "UPDATE acilis_bakiyesi SET varliklar = '{}' WHERE tek = 1"
            )

    def test_cipa_silinemez(self, kurulum) -> None:
        defter, _, _ = kurulum
        with pytest.raises(Exception, match="silinemez"):
            defter._baglanti.execute("DELETE FROM acilis_bakiyesi")  # noqa: SLF001

    def test_cipa_emirlerden_sonra_atilamaz(self, tmp_path) -> None:
        """Emirler varken atılan çıpa, o emirleri iki kez sayar.

        Bakiye onların etkisini zaten içerir, defter akışı da ekler — fark tam olarak
        o emirler kadar çıkar. Sessizce izin vermek, mutabakatı ilk koşuda yanlış yapan
        bir kurulum hatasını kalıcı kılardı.
        """
        defter = EmirDefteri(tmp_path / "gec.sqlite")
        borsa = SahteBorsa()
        EmirMotoru(defter, borsa).gonder(niyet(), MIKTAR)
        with pytest.raises(DefterHatasi, match="emirlerden sonra"):
            cipa_at(defter, borsa)
        defter.kapat()


class TestTemizKosu:
    """Doğru çalışan bir koşu fark üretmemeli — yoksa ölçü her zaman bağırır."""

    def test_emirsiz_kosu_temiz(self, kurulum) -> None:
        defter, borsa, _ = kurulum
        sonuc = pozisyon_mutabakati(defter, borsa, "BTCUSDT")
        assert not sonuc.halt
        assert [f.fark for f in sonuc.farklar] == [0.0, 0.0]

    def test_alim_sonrasi_temiz(self, kurulum) -> None:
        defter, borsa, motor = kurulum
        motor.gonder(niyet(), MIKTAR)
        sonuc = pozisyon_mutabakati(defter, borsa, "BTCUSDT")
        assert not sonuc.halt, sonuc.ozet()

    def test_al_sat_dongusu_temiz(self, kurulum) -> None:
        """Dört emirlik bir tur: net sıfıra yakın, ama komisyon birikmiş.

        Bu test tam olarak komisyonun doğru işlendiğini ölçüyor: komisyon yok sayılsaydı
        dört emrin her birinde ~%0,1 kaçak birikir ve fark toleransı kat kat aşardı.
        """
        defter, borsa, motor = kurulum
        for i in range(4):
            yon = Yon.BUY if i % 2 == 0 else Yon.FLAT
            hedef = 0.20 if yon is Yon.BUY else 0.0
            motor.gonder(
                niyet(hedef, yon, zaman=1_700_000_000_000 + i * 3_600_000), MIKTAR
            )
        sonuc = pozisyon_mutabakati(defter, borsa, "BTCUSDT")
        assert not sonuc.halt, sonuc.ozet()

    def test_kilitli_bakiye_fark_uretmiyor(self, kurulum) -> None:
        """Açık bir limit emri parayı serbestten kilitliye taşır; toplam değişmez.

        Yalnızca `serbest`e bakan bir mutabakat burada haksız yere dururdu. Faz 7 market
        emriyle çalıştığı için bu vaka o fazda hiç doğmadı — limit yolu açılırken doğuyor.
        """
        defter, borsa, _ = kurulum
        borsa.varliklar["USDT"] = Varlik(serbest=ACILIS_USDT - 500.0, kilitli=500.0)
        sonuc = pozisyon_mutabakati(defter, borsa, "BTCUSDT")
        assert not sonuc.halt, sonuc.ozet()


class TestAciklanamayanFark:
    """Ölçünün asıl işi: dışarıdan gelen her değişimi yakalamak."""

    def test_disaridan_para_girisi_halt(self, kurulum) -> None:
        defter, borsa, _ = kurulum
        borsa.varliklar["USDT"] = Varlik(serbest=ACILIS_USDT + 100.0)
        with pytest.raises(PozisyonUyusmazligi):
            pozisyon_mutabakati(defter, borsa, "BTCUSDT")

    def test_elle_satis_halt(self, kurulum) -> None:
        """Defterin bilmediği bir işlem: BTC azalmış, kaydı yok."""
        defter, borsa, _ = kurulum
        borsa.varliklar["BTC"] = Varlik(serbest=ACILIS_BTC - 0.01)
        sonuc = pozisyon_mutabakati(defter, borsa, "BTCUSDT", durdur=False)
        assert sonuc.halt
        btc = next(f for f in sonuc.farklar if f.varlik == "BTC")
        assert btc.aciklanamaz and btc.fark == pytest.approx(-0.01)

    def test_bir_lot_adimi_fark_yakalaniyor(self, kurulum) -> None:
        """Tolerans, gerçekleşebilecek **en küçük** farkı yutmamalı.

        Borsada bir emrin üretebileceği en küçük miktar değişimi bir lot adımı (1e-5).
        Tolerans onu geçirseydi, ölçü gerçek bir kaçağa karşı kör olurdu.
        """
        defter, borsa, _ = kurulum
        borsa.varliklar["BTC"] = Varlik(serbest=ACILIS_BTC - 1e-5)
        sonuc = pozisyon_mutabakati(defter, borsa, "BTCUSDT", durdur=False)
        assert sonuc.halt

    def test_kayan_nokta_gurultusu_halt_uretmiyor(self, kurulum) -> None:
        """Ters yön: toleransın altındaki gürültü yanlış alarm vermemeli."""
        defter, borsa, _ = kurulum
        borsa.varliklar["BTC"] = Varlik(serbest=ACILIS_BTC - 1e-13)
        sonuc = pozisyon_mutabakati(defter, borsa, "BTCUSDT", durdur=False)
        assert not sonuc.halt, sonuc.ozet()


class TestKomisyon:
    """Komisyon hesabın yarısı; bilinmemesi ile sıfır olması ayrı şeyler."""

    def test_komisyon_yanittan_yaziliyor(self, kurulum) -> None:
        defter, _, motor = kurulum
        sonuc = motor.gonder(niyet(), MIKTAR)
        emir = defter.al(sonuc.emir.istemci_kimligi)
        assert emir.komisyon_kaynagi == "yanit"
        assert emir.komisyon == (("BTC", pytest.approx(MIKTAR * KOMISYON_ORANI)),)

    def test_komisyonsuz_hesap_fark_uretirdi(self, kurulum) -> None:
        """Komisyon **gerçekten** gerekli mi? Yok sayıldığında ölçü bozulmalı.

        Bu, kodun bir dalını değil bir gerekçeyi test ediyor: komisyonu hesaba katmayan
        bir beklenen bakiye her alımda ~%0,1 yanılır. `_akis` komisyonsuz bir emir
        listesiyle çağrılıyor ve farkın toleransı kat kat aştığı gösteriliyor.
        """
        from dataclasses import replace

        from scryne_quant.oms.pozisyon import _akis

        defter, _, motor = kurulum
        motor.gonder(niyet(), MIKTAR)
        emirler = defter.tumu()
        komisyonsuz = [replace(e, komisyon=(), komisyon_kaynagi="") for e in emirler]

        dogru, _ = _akis(emirler, taban="BTC", kote="USDT")
        yanlis, _ = _akis(komisyonsuz, taban="BTC", kote="USDT")
        assert yanlis["BTC"] - dogru["BTC"] == pytest.approx(MIKTAR * KOMISYON_ORANI)

    def test_bilinmeyen_komisyon_halt_uretiyor(self, kurulum) -> None:
        """Komisyonu öğrenilememiş dolmuş emir varken beklenen bakiye hesaplanamaz.

        Bu bir fark bulgusu değil, hesabın **yapılamadığının** kaydı. `%0,1 varsaydım`
        demek yerine durmak, bu projenin "tahmin etme, ölç" kuralının doğrudan uygulaması.
        """
        defter, borsa, motor = kurulum
        borsa.komisyonu_yanitta_gizle = True
        borsa.islemler.clear()
        sonuc_g = motor.gonder(niyet(), MIKTAR)
        borsa.islemler.clear()  # myTrades de bilmiyor

        sonuc = pozisyon_mutabakati(defter, borsa, "BTCUSDT", durdur=False)
        assert sonuc.halt
        assert sonuc.eksik_komisyon == (sonuc_g.emir.istemci_kimligi,)

    def test_eksik_komisyon_islemlerden_dolduruluyor(self, kurulum) -> None:
        """`POST` yanıtı komisyonu taşımasa bile `/api/v3/myTrades` taşır.

        Yanıtı kaybolmuş (`UNKNOWN → FILLED`) emirlerin tek komisyon kaynağı bu ve
        doldurma mutabakatın kendi içinde, ayrı bir bakım adımı olarak değil.
        """
        defter, borsa, motor = kurulum
        borsa.komisyonu_yanitta_gizle = True
        gonderim = motor.gonder(niyet(), MIKTAR)

        sonuc = pozisyon_mutabakati(defter, borsa, "BTCUSDT")
        assert sonuc.doldurulan_komisyon == (gonderim.emir.istemci_kimligi,)
        assert not sonuc.halt, sonuc.ozet()
        assert defter.al(gonderim.emir.istemci_kimligi).komisyon_kaynagi == "islemler"

    def test_komisyon_uzerine_yazilmiyor(self, kurulum) -> None:
        """İlk ölçüm korunur: ikinci bir kaynak sessizce üzerine yazamaz."""
        defter, _, motor = kurulum
        gonderim = motor.gonder(niyet(), MIKTAR)
        kimlik = gonderim.emir.istemci_kimligi
        onceki = defter.al(kimlik).komisyon

        defter.komisyon_yaz(kimlik, (("BTC", 999.0),), kaynak="islemler")
        assert defter.al(kimlik).komisyon == onceki

    def test_dolmamis_emir_komisyon_eksigi_saymiyor(self, kurulum) -> None:
        """Dolmamış emrin komisyonu zaten yoktur; eksik listesine girmemeli."""
        defter, borsa, motor = kurulum
        borsa.hata = GonderilemediHatasi("ağ yok")
        gonderim = motor.gonder(niyet(), MIKTAR)
        assert gonderim.emir.durum is EmirDurumu.FAILED

        sonuc = pozisyon_mutabakati(defter, borsa, "BTCUSDT", durdur=False)
        assert sonuc.eksik_komisyon == ()
        assert not sonuc.halt, sonuc.ozet()


class TestSembolBilgisi:
    def test_taban_kote_bilinmiyorsa_tahmin_yok(self, kurulum, monkeypatch) -> None:
        """Sembol adını kesip tahmin etmek yok — BNBBTC'de sessizce yanlış olurdu."""
        from dataclasses import replace as dc_replace

        defter, borsa, _ = kurulum
        eksik = dc_replace(borsa.sembol_kurallari("BTCUSDT"), taban_varlik="")
        monkeypatch.setattr(borsa, "sembol_kurallari", lambda sembol: eksik)
        with pytest.raises(PozisyonHatasi, match="taban/kote"):
            pozisyon_mutabakati(defter, borsa, "BTCUSDT", durdur=False)
