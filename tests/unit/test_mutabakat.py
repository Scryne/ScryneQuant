"""Execution motoru ve mutabakat. (§25, §33, Faz 7 bitti kriterleri)

Faz 7'nin dört kriterinden üçü bu dosyada ölçülüyor:

1. *"Aynı intent iki kez gönderildiğinde tek emir oluşuyor."* — `TestDuplicate`
2. *"Süreç emir gönderiminin ortasında öldürüldüğünde, yeniden başlayınca borsadaki
   gerçek durumla local state uyuşuyor."* — `TestSurecOrtadaOldu`
3. *"Uyuşmazlık tespit edildiğinde sistem işlem yapmayı durduruyor."* — `TestHalt`

Dördüncü kriter (testnet'te ≥100 emir) tanımı gereği ağ ister ve burada ölçülemez.

**Süreç ölümü nasıl taklit ediliyor.** Gerçekten `os.kill` etmek yerine, ölümün *bıraktığı
iz* üretiliyor: gönderim ağ çağrısında kesiliyor, defter diskte kalıyor, sonra **yeni bir
defter nesnesi** aynı dosyadan açılıyor. Sürecin yeniden başlaması buradaki tek anlamlı
şey — ve o, diskteki durumdan yeni bir nesne kurmak demek. `os.kill` ile ölçülen şey
işletim sisteminin sinyal davranışı olurdu, bizim değişmezimiz değil.
"""

from __future__ import annotations

import pytest

from scryne_quant.exchange.emir_adaptoru import (
    BorsaEmri,
    EmirAdaptoru,
    Komisyon,
    Varlik,
    borsa_yonu,
)
from scryne_quant.exchange.hatalar import (
    BelirsizSonuc,
    BorsaReddetti,
    GonderilemediHatasi,
    SaatSapmasi,
)
from scryne_quant.exchange.kurallar import SembolKurallari
from scryne_quant.execution.motor import EmirMotoru, SaatEngeli
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.oms.emir import EmirDurumu, istemci_kimligi
from scryne_quant.oms.mutabakat import Uyusmazlik, mutabakat
from scryne_quant.risk.niyet import onayla
from scryne_quant.strategy.sinyal import Sinyal, Yon

T0 = 1_700_000_000_000
FIYAT = 77_000.0
KURALLAR = SembolKurallari(
    sembol="BTCUSDT",
    tick_size=0.01,
    step_size=0.00001,
    min_notional=5.0,
    durum="TRADING",
    taban_varlik="BTC",
    kote_varlik="USDT",
)

#: Binance spot komisyon oranı (BNB indirimi yok). Sahte borsa bunu **gerçekten**
#: uyguluyor: alınan varlıktan kesiyor ve bakiyeye o şekilde yansıtıyor. Komisyonsuz bir
#: sahte, pozisyon mutabakatının ölçmek istediği tek şeyi yok ederdi.
KOMISYON_ORANI = 0.001

#: Sahte hesabın açılış bakiyesi.
ACILIS_BTC = 1.0
ACILIS_USDT = 10_000.0


def niyet(hedef: float = 0.20, yon: Yon = Yon.BUY, zaman: int = T0):
    return onayla(
        sinyal=Sinyal(
            symbol="BTCUSDT",
            side=yon,
            target_exposure=hedef,
            confidence=0.9,
            reason="TEST_GIRIS",
            timestamp=zaman,
        ),
        onayli_maruziyet=hedef,
        limit_kimligi="k" * 64,
        karar_ms=zaman,
    )


class SahteBorsa(EmirAdaptoru):
    """Emir tutan, sorgulanabilen sahte borsa.

    Gerçek bir borsanın burada önemli olan tek davranışını taşıyor: aynı
    `newClientOrderId` ikinci kez geldiğinde `-2010` ile reddetmek. Duplicate korumasının
    borsa tarafındaki yarısı bu; testnet'e karşı ölçülmesi Faz 7'nin bitti kriteri, ama
    motorun o redde **doğru tepki verdiği** ağa çıkmadan ölçülmeli.
    """

    def __init__(self, *, zaman_ms: int = T0) -> None:
        self.emirler: dict[str, BorsaEmri] = {}
        self.gonderimler: list[str] = []
        self.zaman_ms = zaman_ms
        self.hata: Exception | None = None
        self.sapma_ms = 0
        # Bakiye **gerçekten** tutuluyor ve her fill onu değiştiriyor. Sabit bir bakiye
        # döndüren bir sahte, pozisyon mutabakatını her koşuda "fark var" diye
        # bağırtırdı — yani ölçüyü test edilemez kılardı. Faz 7'nin dersi: bir sahte,
        # gerçeğin yaptığını yapmıyorsa ona karşı yeşil olan test bir şey kanıtlamaz.
        self.varliklar: dict[str, Varlik] = {
            "BTC": Varlik(serbest=ACILIS_BTC),
            "USDT": Varlik(serbest=ACILIS_USDT),
        }
        self.islemler: dict[str, Komisyon] = {}
        #: Komisyonu `POST` yanıtında **gizle** — `GET /api/v3/order`ın davranışı bu.
        self.komisyonu_yanitta_gizle = False
        self.iptaller: list[str] = []
        self.iptal_hatasi: Exception | None = None
        #: Açık limit emirlerinin kilitlediği miktar: borsa kimliği → (varlık, miktar).
        self.kilitler: dict[str, tuple[str, float]] = {}

    # -- sözleşme --------------------------------------------------------

    def sunucu_zamani_ms(self) -> int:
        return self.zaman_ms

    def saat_sapmasi_ms(self) -> int:
        return self.sapma_ms

    def sembol_kurallari(self, sembol: str) -> SembolKurallari:
        return KURALLAR

    def son_fiyat(self, sembol: str) -> float:
        return FIYAT

    def market_emri(
        self, *, istemci_kimligi: str, sembol: str, yon: str, miktar: float
    ) -> BorsaEmri:
        self.gonderimler.append(istemci_kimligi)
        if self.hata is not None:
            hata, self.hata = self.hata, None
            raise hata
        if istemci_kimligi in self.emirler:
            raise BorsaReddetti("Duplicate order sent.", kod=-2010)

        # Çeviri her somut adaptörün kendi işi (`imzali.market_emri` de burada yapıyor);
        # sahte borsa o katmanın yerini tuttuğu için aynı çeviriyi yapmak zorunda.
        yon = borsa_yonu(yon)

        # Gerçek borsanın iki kısıtı burada da uygulanıyor. Bunlar eklenmeden önce sahte
        # borsa gerçeğinden **hoşgörülüydü**; gerçek testnet `Invalid side` ve lot adımı
        # hatalarını döndürdü. Bir sahte, gerçeğin reddettiğini kabul ediyorsa ona karşı
        # yeşil olan test bir şey kanıtlamaz.
        if yon not in ("BUY", "SELL"):
            raise BorsaReddetti(f"Invalid side: {yon}", kod=-1121)
        if abs(miktar / KURALLAR.step_size - round(miktar / KURALLAR.step_size)) > 1e-6:
            raise BorsaReddetti(f"Lot size hatası: {miktar}", kod=-1013)

        borsa_kimligi = f"B{len(self.emirler) + 1}"
        komisyon = self._doldur(borsa_kimligi, yon=yon, miktar=miktar, fiyat=FIYAT)
        emir = BorsaEmri(
            istemci_kimligi=istemci_kimligi,
            borsa_kimligi=borsa_kimligi,
            sembol=sembol,
            yon=yon,
            durum=EmirDurumu.FILLED,
            miktar=miktar,
            dolan_miktar=miktar,
            ortalama_fiyat=FIYAT,
            guncellendi_ms=self.zaman_ms,
            ham_durum="FILLED",
            komisyon=() if self.komisyonu_yanitta_gizle else komisyon,
            komisyon_kaynagi="" if self.komisyonu_yanitta_gizle else "yanit",
        )
        self.emirler[istemci_kimligi] = emir
        return emir

    def limit_emri(
        self,
        *,
        istemci_kimligi: str,
        sembol: str,
        yon: str,
        miktar: float,
        fiyat: float,
    ) -> BorsaEmri:
        """Dolabilir ya da açık kalabilir — ve **açık kalan para kilitler**.

        Gerçek borsanın limit emrinde önemli olan iki davranışı bu: piyasa fiyatına göre
        ya hemen dolar ya defterde bekler, ve beklerken bakiyeyi `serbest`ten
        `kilitli`ye taşır. Kilitlemeyen bir sahte, pozisyon mutabakatının `toplam`
        kullandığını hiç sınamazdı.
        """
        self.gonderimler.append(istemci_kimligi)
        if self.hata is not None:
            hata, self.hata = self.hata, None
            raise hata
        if istemci_kimligi in self.emirler:
            raise BorsaReddetti("Duplicate order sent.", kod=-2010)

        yon = borsa_yonu(yon)
        if yon not in ("BUY", "SELL"):
            raise BorsaReddetti(f"Invalid side: {yon}", kod=-1121)
        if abs(fiyat / KURALLAR.tick_size - round(fiyat / KURALLAR.tick_size)) > 1e-6:
            raise BorsaReddetti(f"Tick size hatası: {fiyat}", kod=-1013)

        borsa_kimligi = f"B{len(self.emirler) + 1}"
        dolar = (yon == "BUY" and fiyat >= FIYAT) or (yon == "SELL" and fiyat <= FIYAT)

        if dolar:
            # Marketable limit: borsa **daha iyi** olan fiyattan doldurur, limitten değil.
            gerceklesen = min(fiyat, FIYAT) if yon == "BUY" else max(fiyat, FIYAT)
            komisyon = self._doldur(
                borsa_kimligi, yon=yon, miktar=miktar, fiyat=gerceklesen
            )
            emir = BorsaEmri(
                istemci_kimligi=istemci_kimligi,
                borsa_kimligi=borsa_kimligi,
                sembol=sembol,
                yon=yon,
                durum=EmirDurumu.FILLED,
                miktar=miktar,
                dolan_miktar=miktar,
                ortalama_fiyat=gerceklesen,
                guncellendi_ms=self.zaman_ms,
                ham_durum="FILLED",
                komisyon=() if self.komisyonu_yanitta_gizle else komisyon,
                komisyon_kaynagi="" if self.komisyonu_yanitta_gizle else "yanit",
            )
        else:
            self._kilitle(borsa_kimligi, yon=yon, miktar=miktar, fiyat=fiyat)
            emir = BorsaEmri(
                istemci_kimligi=istemci_kimligi,
                borsa_kimligi=borsa_kimligi,
                sembol=sembol,
                yon=yon,
                durum=EmirDurumu.ACKNOWLEDGED,
                miktar=miktar,
                dolan_miktar=0.0,
                ortalama_fiyat=0.0,
                guncellendi_ms=self.zaman_ms,
                ham_durum="NEW",
                komisyon=(),
                komisyon_kaynagi="yanit",
            )
        self.emirler[istemci_kimligi] = emir
        return emir

    def emir_iptal(self, *, sembol: str, istemci_kimligi: str) -> BorsaEmri | None:
        self.iptaller.append(istemci_kimligi)
        if self.iptal_hatasi is not None:
            hata, self.iptal_hatasi = self.iptal_hatasi, None
            raise hata
        emir = self.emirler.get(istemci_kimligi)
        if emir is None or emir.durum is not EmirDurumu.ACKNOWLEDGED:
            # Gerçek borsanın `-2011`i: iptal edilecek bir şey yok.
            return None
        self._kilidi_coz(emir.borsa_kimligi)
        iptal = BorsaEmri(
            istemci_kimligi=emir.istemci_kimligi,
            borsa_kimligi=emir.borsa_kimligi,
            sembol=emir.sembol,
            yon=emir.yon,
            durum=EmirDurumu.CANCELED,
            miktar=emir.miktar,
            dolan_miktar=emir.dolan_miktar,
            ortalama_fiyat=emir.ortalama_fiyat,
            guncellendi_ms=self.zaman_ms,
            ham_durum="CANCELED",
        )
        self.emirler[istemci_kimligi] = iptal
        return iptal

    def emir_sorgula(self, *, sembol: str, istemci_kimligi: str) -> BorsaEmri | None:
        return self.emirler.get(istemci_kimligi)

    def acik_emirler(self, sembol: str) -> list[BorsaEmri]:
        return [
            e
            for e in self.emirler.values()
            if e.sembol == sembol and e.durum is EmirDurumu.ACKNOWLEDGED
        ]

    def bakiye(self) -> dict[str, Varlik]:
        return dict(self.varliklar)

    def emir_islemleri(self, *, sembol: str, borsa_kimligi: str) -> Komisyon:
        return self.islemler.get(borsa_kimligi, ())

    # -- muhasebe --------------------------------------------------------

    def _doldur(
        self, borsa_kimligi: str, *, yon: str, miktar: float, fiyat: float
    ) -> Komisyon:
        """Fill'i bakiyeye işler ve komisyonu **alınan varlıktan** keser."""
        kote = miktar * fiyat
        if yon == "BUY":
            kazanilan, harcanan = ("BTC", miktar), ("USDT", kote)
        else:
            kazanilan, harcanan = ("USDT", kote), ("BTC", miktar)

        komisyon = round(kazanilan[1] * KOMISYON_ORANI, 12)
        self._ekle(kazanilan[0], kazanilan[1] - komisyon)
        self._ekle(harcanan[0], -harcanan[1])
        toplam: Komisyon = ((kazanilan[0], komisyon),)
        self.islemler[borsa_kimligi] = toplam
        return toplam

    def _kilitle(
        self, borsa_kimligi: str, *, yon: str, miktar: float, fiyat: float
    ) -> None:
        """Açık emir parayı `serbest`ten `kilitli`ye taşır; toplam **değişmez**."""
        varlik, tutar = ("USDT", miktar * fiyat) if yon == "BUY" else ("BTC", miktar)
        mevcut = self.varliklar.get(varlik, Varlik())
        self.varliklar[varlik] = Varlik(
            serbest=mevcut.serbest - tutar, kilitli=mevcut.kilitli + tutar
        )
        self.kilitler[borsa_kimligi] = (varlik, tutar)

    def _kilidi_coz(self, borsa_kimligi: str) -> None:
        kilit = self.kilitler.pop(borsa_kimligi, None)
        if kilit is None:
            return
        varlik, tutar = kilit
        mevcut = self.varliklar.get(varlik, Varlik())
        self.varliklar[varlik] = Varlik(
            serbest=mevcut.serbest + tutar, kilitli=mevcut.kilitli - tutar
        )

    def _ekle(self, varlik: str, miktar: float) -> None:
        mevcut = self.varliklar.get(varlik, Varlik())
        self.varliklar[varlik] = Varlik(
            serbest=mevcut.serbest + miktar, kilitli=mevcut.kilitli
        )

    # -- test yardımcıları -----------------------------------------------

    def sessizce_doldur(self, kimlik: str) -> None:
        """Açık bir limit emri borsada dolar — ve çağıranın haberi olmaz.

        İptal ile fill'in yarıştığı anın borsadan görünüşü bu. Gerçek bir zamanlama
        yarışını taklit etmeye çalışmak testi kırılgan yapardı; ölçülmesi gereken şey
        yarışın kendisi değil, **yarışı kaybeden iptalin ne yaptığı**.
        """
        emir = self.emirler[kimlik]
        self._kilidi_coz(emir.borsa_kimligi)
        self._doldur(
            emir.borsa_kimligi,
            yon=emir.yon,
            miktar=emir.miktar,
            fiyat=emir.ortalama_fiyat or FIYAT,
        )
        self.emirler[kimlik] = BorsaEmri(
            istemci_kimligi=emir.istemci_kimligi,
            borsa_kimligi=emir.borsa_kimligi,
            sembol=emir.sembol,
            yon=emir.yon,
            durum=EmirDurumu.FILLED,
            miktar=emir.miktar,
            dolan_miktar=emir.miktar,
            ortalama_fiyat=emir.ortalama_fiyat or FIYAT,
            guncellendi_ms=self.zaman_ms,
            ham_durum="FILLED",
        )

    def sessizce_kabul_et(self, kimlik: str, *, durum=EmirDurumu.FILLED) -> None:
        """Emri borsaya yazar ama çağırana haber vermez — 'yanıt kayboldu' hâli."""
        borsa_kimligi = f"B{len(self.emirler) + 1}"
        dolan = 0.001 if durum is EmirDurumu.FILLED else 0.0
        if dolan:
            self._doldur(borsa_kimligi, yon="BUY", miktar=dolan, fiyat=FIYAT)
        self.emirler[kimlik] = BorsaEmri(
            istemci_kimligi=kimlik,
            borsa_kimligi=borsa_kimligi,
            sembol="BTCUSDT",
            yon="BUY",
            durum=durum,
            miktar=0.001,
            dolan_miktar=dolan,
            ortalama_fiyat=FIYAT if durum is EmirDurumu.FILLED else 0.0,
            guncellendi_ms=self.zaman_ms,
            ham_durum=str(durum),
        )


@pytest.fixture
def kurulum(tmp_path):
    yol = tmp_path / "kosu.sqlite"
    defter = EmirDefteri(yol)
    borsa = SahteBorsa()
    yield defter, borsa, EmirMotoru(defter, borsa), yol
    defter.kapat()


class TestDuplicate:
    """Aynı niyet iki kez → tek emir, ve ikincisi **ağa hiç çıkmıyor**."""

    def test_ikinci_gonderim_aga_cikmiyor(self, kurulum) -> None:
        _, borsa, motor, _ = kurulum
        ilk = motor.gonder(niyet(), 0.001)
        ikinci = motor.gonder(niyet(), 0.001)

        assert ilk.gonderildi and not ikinci.gonderildi
        assert ilk.emir.istemci_kimligi == ikinci.emir.istemci_kimligi
        assert len(borsa.gonderimler) == 1, (
            "ikinci niyet borsaya gitti. Defter katmanı duplicate'i durdurmalı; "
            "borsanın -2010 reddine yaslanmak tek katmanı iki katman sanmaktır."
        )

    def test_defter_silinse_bile_borsa_koruyor(self, kurulum) -> None:
        """İkinci katman: defter kaybolsa da kimlik aynı kaldığı için borsa reddeder."""
        defter, borsa, motor, yol = kurulum
        motor.gonder(niyet(), 0.001)

        defter.kapat()
        yol.unlink()
        yeni_defter = EmirDefteri(yol)
        sonuc = EmirMotoru(yeni_defter, borsa).gonder(niyet(), 0.001)

        assert sonuc.emir.durum is EmirDurumu.REJECTED
        assert len(borsa.emirler) == 1
        yeni_defter.kapat()

    def test_farkli_niyet_farkli_emir(self, kurulum) -> None:
        _, borsa, motor, _ = kurulum
        motor.gonder(niyet(hedef=0.20), 0.001)
        motor.gonder(niyet(hedef=0.30), 0.001)
        assert len(borsa.emirler) == 2


class TestGonderimSirasi:
    """`SUBMITTED` ağ çağrısından önce diske yazılır — yetim emir bırakmamak için."""

    def test_submitted_agdan_once_yaziliyor(self, kurulum) -> None:
        defter, borsa, motor, _ = kurulum
        gorulen: list[str] = []

        gercek = borsa.market_emri

        def gozetle(**kw):
            kayit = defter.al(kw["istemci_kimligi"])
            gorulen.append(str(kayit.durum) if kayit else "yok")
            return gercek(**kw)

        borsa.market_emri = gozetle  # type: ignore[method-assign]
        motor.gonder(niyet(), 0.001)
        assert gorulen == [str(EmirDurumu.SUBMITTED)]

    def test_kural_ihlali_aga_cikmiyor(self, kurulum) -> None:
        """minNotional'ın altındaki emir borsaya gönderilmez — reddi görmeye gerek yok.

        Gönderim başlı başına risk: yanıt kaybolursa emrin oluşmadığını bilmemize rağmen
        `UNKNOWN`a düşeriz. Yerel kontrol o riski hiç almamaktır.
        """
        _, borsa, motor, _ = kurulum
        sonuc = motor.gonder(niyet(), 0.00001)  # 0,77 USDT < 5,00
        assert sonuc.emir.durum is EmirDurumu.REJECTED
        assert not borsa.gonderimler
        assert "minNotional" in sonuc.emir.hata

    def test_gecmis_yolu_koruyor(self, kurulum) -> None:
        """Market emri tek yanıtta dolsa bile `ACKNOWLEDGED` kayıttan silinmiyor."""
        _, _, motor, _ = kurulum
        sonuc = motor.gonder(niyet(), 0.001)
        assert list(sonuc.emir.gecmis) == [
            "CREATED",
            "VALIDATED",
            "SUBMITTED",
            "ACKNOWLEDGED",
            "FILLED",
        ]


class TestHataSonuclari:
    """Üç hata, üç ayrı durum. Karışırlarsa duplicate ya da kayıp emir doğar."""

    def test_gonderilemedi_failed(self, kurulum) -> None:
        _, borsa, motor, _ = kurulum
        borsa.hata = GonderilemediHatasi("bağlanamadı")
        sonuc = motor.gonder(niyet(), 0.001)
        assert sonuc.emir.durum is EmirDurumu.FAILED
        assert not sonuc.gonderildi and not sonuc.belirsiz

    def test_belirsiz_unknown(self, kurulum) -> None:
        _, borsa, motor, _ = kurulum
        borsa.hata = BelirsizSonuc("yanıt kayboldu")
        sonuc = motor.gonder(niyet(), 0.001)
        assert sonuc.emir.durum is EmirDurumu.UNKNOWN
        assert sonuc.belirsiz

    def test_red_rejected(self, kurulum) -> None:
        _, borsa, motor, _ = kurulum
        borsa.hata = BorsaReddetti("bakiye yetersiz", kod=-2010)
        assert motor.gonder(niyet(), 0.001).emir.durum is EmirDurumu.REJECTED

    def test_saat_sapmasi_kosuyu_durduruyor(self, kurulum) -> None:
        """Bozuk saatle devam eden bir koşu emirlerini sessizce kaybeder."""
        defter, borsa, motor, _ = kurulum
        borsa.hata = SaatSapmasi("-1021")
        with pytest.raises(SaatEngeli, match="Koşu durmalı"):
            motor.gonder(niyet(), 0.001)
        assert defter.al(istemci_kimligi(niyet())).durum is EmirDurumu.FAILED

    def test_unknown_yeniden_gonderilemiyor(self, kurulum) -> None:
        """`UNKNOWN`u yeniden denemek duplicate'in en kısa yolu — state machine engelliyor."""
        _, borsa, motor, _ = kurulum
        borsa.hata = BelirsizSonuc("kayıp")
        motor.gonder(niyet(), 0.001)

        tekrar = motor.gonder(niyet(), 0.001)
        assert not tekrar.gonderildi
        assert tekrar.emir.durum is EmirDurumu.UNKNOWN
        assert len(borsa.gonderimler) == 1


class TestSurecOrtadaOldu:
    """Faz 7 kriteri: süreç gönderimin ortasında ölünce state borsayla uyuşmalı."""

    def _oldur_ve_yeniden_basla(self, defter, yol, borsa):
        """Defteri kapatıp diskten yeniden açar — sürecin yeniden başlamasının izi."""
        defter.kapat()
        return EmirDefteri(yol)

    def test_emir_olusmusken_yanit_kayboldu(self, kurulum) -> None:
        """En zor vaka: borsada emir **var**, bizim kaydımız `UNKNOWN`.

        Mutabakat bunu borsanın lehine çözmeli — ve çözerken dolum bilgisini de almalı,
        yoksa pozisyon eksik bilinir.
        """
        defter, borsa, motor, yol = kurulum
        kimlik = istemci_kimligi(niyet())
        borsa.hata = BelirsizSonuc("yanıt kayboldu")
        motor.gonder(niyet(), 0.001)
        borsa.sessizce_kabul_et(kimlik)  # emir aslında oluşmuştu

        yeni = self._oldur_ve_yeniden_basla(defter, yol, borsa)
        sonuc = mutabakat(yeni, borsa, "BTCUSDT")

        emir = yeni.al(kimlik)
        assert not sonuc.halt
        assert emir.durum is EmirDurumu.FILLED
        assert emir.dolan_miktar == pytest.approx(0.001)
        assert emir.ortalama_fiyat == pytest.approx(FIYAT)
        yeni.kapat()

    def test_emir_olusmamisken_yanit_kayboldu(self, kurulum) -> None:
        """Diğer yarısı: borsada emir **yok**. Belirsizlik 'oluşmadı' olarak kapanır."""
        defter, borsa, motor, yol = kurulum
        kimlik = istemci_kimligi(niyet())
        borsa.hata = BelirsizSonuc("yanıt kayboldu")
        motor.gonder(niyet(), 0.001)

        yeni = self._oldur_ve_yeniden_basla(defter, yol, borsa)
        sonuc = mutabakat(yeni, borsa, "BTCUSDT")

        assert not sonuc.halt
        assert yeni.al(kimlik).durum is EmirDurumu.FAILED
        yeni.kapat()

    def test_submitted_yazildi_ama_gonderim_olmadi(self, kurulum) -> None:
        """Süreç `SUBMITTED` yazımı ile ağ çağrısı **arasında** ölürse.

        Bu, gönderim sırasının kasıtlı olarak ürettiği 'en kötü durum': hiç gönderilmemiş
        bir emrin kaydı. Mutabakat onu kapatabilmeli.
        """
        defter, borsa, motor, yol = kurulum
        emir = motor.gonder(niyet(), 0.001).emir
        # Elle `UNKNOWN`a değil, taze bir `SUBMITTED` kaydı kuruyoruz: ikinci bir niyet.
        ikinci = niyet(hedef=0.35)
        kimlik = istemci_kimligi(ikinci)
        borsa.hata = BelirsizSonuc("süreç öldü")
        motor.gonder(ikinci, 0.001)

        yeni = self._oldur_ve_yeniden_basla(defter, yol, borsa)
        mutabakat(yeni, borsa, "BTCUSDT")

        assert yeni.al(kimlik).durum is EmirDurumu.FAILED
        assert yeni.al(emir.istemci_kimligi).durum is EmirDurumu.FILLED
        yeni.kapat()

    def test_mutabakat_sonrasi_yeniden_gonderilebilir(self, kurulum) -> None:
        """`FAILED`e kapanan emir yeniden gönderilebilir — ama aynı kimlikle değil.

        Defterde kimlik birincil anahtar ve emir silinemez; yani aynı niyet mutabakattan
        sonra da yeni bir emir doğurmaz. Bu **doğru**: emrin oluşmadığı biliniyor olsa
        bile, onu yeniden göndermek bir strateji kararıdır, bir kurtarma değil.
        """
        defter, borsa, motor, yol = kurulum
        borsa.hata = BelirsizSonuc("kayıp")
        motor.gonder(niyet(), 0.001)
        mutabakat(defter, borsa, "BTCUSDT")

        tekrar = motor.gonder(niyet(), 0.001)
        assert not tekrar.gonderildi
        assert tekrar.emir.durum is EmirDurumu.FAILED


class TestHalt:
    """Uyuşmazlıkta koşu **durur**; tahmin yürütülmez (K-038)."""

    def test_borsa_kabul_ettigi_emri_tanimiyorsa_halt(self, kurulum) -> None:
        defter, borsa, motor, _ = kurulum
        borsa.hata = BelirsizSonuc("kayıp")
        motor.gonder(niyet(), 0.001)
        kimlik = istemci_kimligi(niyet())
        # Defter 'kabul edildi' diyor ama borsa tanımıyor: iki farklı gerçeklik.
        defter.gecir(kimlik, EmirDurumu.ACKNOWLEDGED, zaman_ms=T0, borsa_kimligi="B9")

        with pytest.raises(Uyusmazlik, match="UYUŞMAZLIK"):
            mutabakat(defter, borsa, "BTCUSDT")

    def test_defterde_olmayan_acik_emir_halt(self, kurulum) -> None:
        """Sistemin üretmediği ya da kaydını kaybettiği emir — ikisi de durdurur."""
        defter, borsa, motor, _ = kurulum
        borsa.sessizce_kabul_et("elle_girilmis", durum=EmirDurumu.ACKNOWLEDGED)

        with pytest.raises(Uyusmazlik) as bilgi:
            mutabakat(defter, borsa, "BTCUSDT")
        assert "defterde kaydı yok" in bilgi.value.sonuc.ozet()

    def test_durdur_false_rapor_veriyor(self, kurulum) -> None:
        """CLI/dashboard uyuşmazlığı görmek isteyip koşuyu durdurmayabilir."""
        defter, borsa, _, _ = kurulum
        borsa.sessizce_kabul_et("elle_girilmis", durum=EmirDurumu.ACKNOWLEDGED)
        sonuc = mutabakat(defter, borsa, "BTCUSDT", durdur=False)
        assert sonuc.halt and len(sonuc.uyusmazlik) == 1

    def test_temiz_mutabakat_halt_etmiyor(self, kurulum) -> None:
        defter, borsa, motor, _ = kurulum
        motor.gonder(niyet(), 0.001)
        sonuc = mutabakat(defter, borsa, "BTCUSDT")
        assert not sonuc.halt
        assert "temiz" in sonuc.ozet()

    def test_ulasilamaz_durum_halt(self, kurulum) -> None:
        """Borsa state machine'de ulaşılamaz bir duruma işaret ederse tahmin yürütülmez.

        `ACKNOWLEDGED → REJECTED` tanımlı bir geçiş değil: kabul edilmiş bir emir
        reddedilmiş olamaz. Borsa bunu söylüyorsa ya bizim modelimiz ya borsanın cevabı
        yanlış — ikisinde de doğru davranış durmak, "herhalde şöyle olmuştur" demek değil.
        """
        defter, borsa, motor, _ = kurulum
        borsa.hata = BelirsizSonuc("kayıp")
        motor.gonder(niyet(), 0.001)
        kimlik = istemci_kimligi(niyet())
        defter.gecir(kimlik, EmirDurumu.ACKNOWLEDGED, zaman_ms=T0, borsa_kimligi="B1")
        borsa.sessizce_kabul_et(kimlik, durum=EmirDurumu.REJECTED)

        with pytest.raises(Uyusmazlik) as bilgi:
            mutabakat(defter, borsa, "BTCUSDT")
        assert "ulaşılamaz" in bilgi.value.sonuc.ozet()

    def test_nihai_emir_incelenmiyor(self, kurulum) -> None:
        """Kapanmış emir mutabakatın konusu değil — `acik` kümesi bilerek dar."""
        defter, borsa, motor, _ = kurulum
        motor.gonder(niyet(), 0.001)  # tek yanıtta FILLED
        assert mutabakat(defter, borsa, "BTCUSDT").incelenen == 0


class TestSonucOzeti:
    def test_ozet_uyusmazligi_acikliyor(self, kurulum) -> None:
        defter, borsa, _, _ = kurulum
        borsa.sessizce_kabul_et("yabanci", durum=EmirDurumu.ACKNOWLEDGED)
        sonuc = mutabakat(defter, borsa, "BTCUSDT", durdur=False)
        ozet = sonuc.ozet()
        assert "yabanci" in ozet and "Koşu durmalı" in ozet

    def test_sozluk_serilestirilebiliyor(self, kurulum) -> None:
        """Dashboard ve koşu günlüğü bu sözlüğü yazacak."""
        import json

        defter, borsa, motor, _ = kurulum
        motor.gonder(niyet(), 0.001)
        json.dumps(mutabakat(defter, borsa, "BTCUSDT").sozluk())


class TestGercekKosudanCikanlar:
    """İlk testnet koşusunun ortaya çıkardığı iki hata. İkisi de birim testte görünmüyordu.

    Buradaki ders kayda değer: `SahteBorsa` `yon`u hiç doğrulamıyordu ve miktarı olduğu
    gibi dolduruyordu — yani sahte borsa gerçek borsadan **daha hoşgörülüydü**. Bir sahte,
    gerçeğin kabul etmediği şeyi kabul ediyorsa, o sahteye karşı yeşil olan test bir şey
    kanıtlamaz.
    """

    def test_flat_borsaya_sell_olarak_gidiyor(self) -> None:
        """`FLAT` bizim sözlüğümüzde var, Binance'te yok. Çeviri sözleşmenin kenarında.

        İlk koşuda `FLAT` doğrudan gönderildi ve borsa `Invalid side` ile reddetti.
        """
        from scryne_quant.exchange.emir_adaptoru import GecersizYon, borsa_yonu

        assert borsa_yonu("FLAT") == "SELL"
        assert borsa_yonu("SELL") == "SELL"
        assert borsa_yonu("BUY") == "BUY"
        with pytest.raises(GecersizYon):
            borsa_yonu("KAPAT")

    def test_defter_gonderilebilir_miktari_yaziyor(self, kurulum) -> None:
        """Lot adımına uymayan bir miktar deftere **uydurulmuş** hâliyle yazılır.

        Ham miktar yazılsaydı emir `FILLED` olurken `kalan` sıfırdan farklı kalırdı:
        tamamen dolmuş ama defterde hâlâ bakiyesi olan bir emir.
        """
        _, _, motor, _ = kurulum
        ham = 0.00012981951711813134  # step 0,00001'e uymuyor
        sonuc = motor.gonder(niyet(), ham)

        assert sonuc.emir.miktar == pytest.approx(0.00012)
        assert sonuc.emir.durum is EmirDurumu.FILLED
        assert sonuc.emir.kalan == pytest.approx(0.0), (
            "tamamen dolmuş emrin kalanı sıfır olmalı; değilse defter gönderilmeyen "
            "bir miktarı taşıyor demektir"
        )

    def test_duplicate_tek_ag_cagrisi_bile_yapmiyor(self, kurulum) -> None:
        """Tekrarlanan niyet fiyat sorgusuna bile mal olmamalı — kimlik içerikten türüyor."""
        _, borsa, motor, _ = kurulum
        motor.gonder(niyet(), 0.001)

        sorgular: list[str] = []
        gercek = borsa.son_fiyat
        borsa.son_fiyat = lambda s: (sorgular.append(s), gercek(s))[1]  # type: ignore[method-assign]
        motor.gonder(niyet(), 0.001)
        assert not sorgular
