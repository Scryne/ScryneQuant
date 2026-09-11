"""İmzalı istemci: saat senkronu ve hata sınıflandırması. (Faz 7)

**Bu dosyanın ölçtüğü şey ağa çıkarak ölçülemez.** Asıl soru şu: bir ağ hatası "istek hiç
gitmedi" mi, yoksa "yanıt kayboldu" mu? İkisinin farkı duplicate emrin doğduğu yer, ve
gerçek bir bağlantı üzerinde ikincisini **isteyerek** üretmek mümkün değil. O yüzden
transport sahte: her istisna türü kasıtlı olarak fırlatılıyor ve adaptörün onu hangi
sınıfa koyduğu ölçülüyor.

Saat tarafında ölçülen iddia şu: imzalı isteğin `timestamp`i **yerel saatten bağımsız**.
Bu makinede yerel saat borsadan 2,64 s geride (2026-09-11) ve sistem tam olarak bu yüzden
sunucu saatine bağlandı; test yerel saati 30 saniye ileri sıçratıp timestamp'in yine de
sunucu saatinde kaldığını gösteriyor.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
import requests

from scryne_quant.exchange.emir_adaptoru import BilinmeyenDurum
from scryne_quant.exchange.hatalar import (
    BelirsizSonuc,
    BorsaHatasi,
    BorsaReddetti,
    GonderilemediHatasi,
    SaatSapmasi,
)
from scryne_quant.exchange.imzali import (
    ANAHTAR_DEGISKENI,
    RECV_WINDOW_MS,
    SICRAMA_SINIRI_MS,
    SIR_DEGISKENI,
    BinanceImzaliAdaptoru,
    SaatSenkronu,
    anahtarlari_oku,
)

SUNUCU_MS = 1_800_000_000_000


class SahteYanit:
    """`requests.Response`un bu modülün dokunduğu yüzeyi."""

    def __init__(self, durum: int, govde: Any = None, metin: str = "") -> None:
        self.status_code = durum
        self._govde = govde
        self.text = metin or (json.dumps(govde) if govde is not None else "")

    def json(self) -> Any:
        if self._govde is None:
            raise ValueError("gövde JSON değil")
        return self._govde


class SahteTransport:
    """Sıraya konmuş yanıtları/istisnaları döndürür ve gönderilen URL'leri kaydeder.

    `/api/v3/time` **sıradan yenmez**, her zaman yanıtlanır. Sebep: saat senkronu tembel
    ve yalnızca imzalı çağrılarda tetikleniyor, yani onu sıraya koymak testin imzalı mı
    imzasız mı çağrı yaptığına bağlı kırılgan bir sıralama yaratırdı. Gerçek borsa da
    zaten saati her istendiğinde veriyor.
    """

    def __init__(self, *cevaplar: Any) -> None:
        self.cevaplar = list(cevaplar)
        self.istekler: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **_: Any) -> Any:
        self.istekler.append((method, url))
        if "/api/v3/time" in url:
            return zaman_yaniti()
        cevap = self.cevaplar.pop(0) if self.cevaplar else SahteYanit(200, {})
        if isinstance(cevap, BaseException):
            raise cevap
        return cevap


def zaman_yaniti(ms: int = SUNUCU_MS) -> SahteYanit:
    return SahteYanit(200, {"serverTime": ms})


def adaptor(*cevaplar: Any) -> tuple[BinanceImzaliAdaptoru, SahteTransport]:
    tasiyici = SahteTransport(*cevaplar)
    return (
        BinanceImzaliAdaptoru(
            anahtar="anahtar", sir="sir", oturum=tasiyici, ipv4=False
        ),
        tasiyici,
    )


EMIR_YANITI = {
    "symbol": "BTCUSDT",
    "orderId": 12345,
    "clientOrderId": "sqABC",
    "side": "BUY",
    "status": "FILLED",
    "origQty": "0.00100000",
    "executedQty": "0.00100000",
    "cummulativeQuoteQty": "77.00000000",
    "transactTime": SUNUCU_MS,
}

KURAL_YANITI = {
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "status": "TRADING",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
                {"filterType": "LOT_SIZE", "stepSize": "0.00001000"},
                {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
            ],
        }
    ]
}


class TestSaatSenkronu:
    """Timestamp sunucu saatinden türer; yerel saat değişse bile kaymaz."""

    def test_yerel_saat_sicrasa_da_timestamp_sunucuda_kalir(self, monkeypatch) -> None:
        a, _ = adaptor()
        once = a.sunucu_zamani_ms()

        # Yerel saati 30 saniye ileri sıçrat. `monotonic`e dokunulmuyor — gerçek bir
        # NTP düzeltmesi de tam olarak böyle davranır.
        gercek_time = time.time
        monkeypatch.setattr(time, "time", lambda: gercek_time() + 30.0)

        sonra = a.sunucu_zamani_ms()
        assert abs(sonra - once) < 1_000, (
            f"yerel saat sıçrayınca sunucu zamanı da sıçradı: {once} → {sonra}. "
            f"Timestamp yerel saatten türüyor demektir."
        )

    def test_yerel_sapma_olculuyor(self, monkeypatch) -> None:
        """Sapma bir sağlık göstergesi: dashboard'da görünmesi gereken sayı."""
        sabit = SUNUCU_MS / 1000.0 - 2.64  # yerel saat 2,64 s geride
        monkeypatch.setattr(time, "time", lambda: sabit)
        a, _ = adaptor()
        assert -2_800 < a.saat_sapmasi_ms() < -2_500

    def test_sicrama_yakalaniyor(self) -> None:
        """İki senkron arasında fark çok değiştiyse aradaki imzalar güvenilmez."""
        zamanlar = iter([SUNUCU_MS, SUNUCU_MS + SICRAMA_SINIRI_MS * 5])
        senkron = SaatSenkronu(lambda: next(zamanlar))
        senkron.simdi_ms()
        with pytest.raises(SaatSapmasi, match="saat sıçradı"):
            senkron._senkronla()

    def test_kucuk_fark_sicrama_sayilmaz(self) -> None:
        zamanlar = iter([SUNUCU_MS, SUNUCU_MS + 200])
        senkron = SaatSenkronu(lambda: next(zamanlar))
        senkron.simdi_ms()
        senkron._senkronla()  # hata yok

    def test_imzali_istek_recv_window_tasiyor(self) -> None:
        a, t = adaptor(SahteYanit(200, {"balances": []}))
        a.bakiye()
        _, url = t.istekler[-1]
        assert f"recvWindow={RECV_WINDOW_MS}" in url
        assert "timestamp=" in url and "signature=" in url

    def test_imza_gonderilen_sorgu_metninin_uzerinde(self) -> None:
        """İmzalanan metin gönderilen metin olmalı — `params=` ile yeniden kodlanmamalı.

        URL'de imzadan **önceki** kısım, imzanın hesaplandığı metindir. Bu testin
        koruduğu şey bir davranış değil bir değişmezlik: iki ayrı kodlayıcı devreye
        girerse imza sessizce tutmaz ve hata `-1022` olarak görünür.
        """
        import hashlib
        import hmac

        a, t = adaptor(SahteYanit(200, {"balances": []}))
        a.bakiye()
        _, url = t.istekler[-1]
        sorgu = url.split("?", 1)[1]
        govde, _, imza = sorgu.rpartition("&signature=")
        beklenen = hmac.new(b"sir", govde.encode(), hashlib.sha256).hexdigest()
        assert imza == beklenen


class TestHataSiniflandirmasi:
    """Bu sınıf projenin en pahalı ayrımını ölçüyor: "gitmedi" mi "bilmiyorum" mu."""

    def _emir(self, a: BinanceImzaliAdaptoru):
        return a.market_emri(
            istemci_kimligi="sqTEST", sembol="BTCUSDT", yon="BUY", miktar=0.001
        )

    @pytest.fixture
    def hazir(self):
        """Sembol kuralları önbelleğe alınmış adaptör — emir yolu ona bakıyor."""

        def kur(*cevaplar: Any):
            a, t = adaptor(SahteYanit(200, KURAL_YANITI), *cevaplar)
            a.sembol_kurallari("BTCUSDT")
            return a, t

        return kur

    def test_okuma_zaman_asimi_belirsiz(self, hazir) -> None:
        """Yanıt kayboldu → emir borsada **olabilir**. En tehlikeli hata sınıfı."""
        a, _ = hazir(requests.exceptions.ReadTimeout("zaman aşımı"))
        with pytest.raises(BelirsizSonuc, match="yanıt gelmedi"):
            self._emir(a)

    def test_baglanti_kurulamadi_gonderilemedi(self, hazir) -> None:
        """Bağlantı hiç kurulmadı → istek bayta dökülmedi. Kesin bilgi."""
        a, _ = hazir(requests.exceptions.ConnectTimeout("bağlanamadı"))
        with pytest.raises(GonderilemediHatasi):
            self._emir(a)

    def test_baglanti_koptu_belirsiz(self, hazir) -> None:
        """Ne zaman koptuğu bilinmiyor; yazmada 'herhalde gitmedi' demek yasak."""
        a, _ = hazir(requests.exceptions.ConnectionError("kopuk"))
        with pytest.raises(BelirsizSonuc, match="bağlantı koptu"):
            self._emir(a)

    def test_5xx_yazmada_belirsiz(self, hazir) -> None:
        """Binance'in kendi sözleşmesi: 5xx'te yürütme durumu bilinmiyor."""
        a, _ = hazir(SahteYanit(503, {"code": -1000, "msg": "hizmet dışı"}))
        with pytest.raises(BelirsizSonuc, match="yürütme durumu bilinmiyor"):
            self._emir(a)

    def test_4xx_kesin_red(self, hazir) -> None:
        a, _ = hazir(SahteYanit(400, {"code": -2010, "msg": "Duplicate order sent."}))
        with pytest.raises(BorsaReddetti) as bilgi:
            self._emir(a)
        assert bilgi.value.kod == -2010

    def test_saat_hatasi_kendi_tipiyle(self, hazir) -> None:
        """`-1021` emir mantığı hatası gibi görünmemeli — sebebi saat."""
        a, _ = hazir(SahteYanit(400, {"code": -1021, "msg": "Timestamp ... ahead"}))
        with pytest.raises(SaatSapmasi, match="-1021"):
            self._emir(a)

    def test_yazmada_yeniden_deneme_yok(self, hazir) -> None:
        """Yazma isteği **bir kez** gönderilir. Tekrar, duplicate'in ta kendisi."""
        a, t = hazir(
            requests.exceptions.ConnectTimeout("1"),
            requests.exceptions.ConnectTimeout("2"),
        )
        with pytest.raises(GonderilemediHatasi):
            self._emir(a)
        # Saat senkronu da bir istek; sayılan yalnızca emir gönderimi olmalı.
        gonderimler = [i for i in t.istekler if i[0] == "POST" and "/order" in i[1]]
        assert len(gonderimler) == 1, (
            f"emir {len(gonderimler)} kez gönderildi. Yazma isteğinde yeniden deneme, "
            f"duplicate emrin ta kendisidir."
        )

    def test_okumada_yeniden_deneme_var(self) -> None:
        """Okuma idempotent; geçici bir hata yüzünden koşu durmamalı."""
        a, t = adaptor(
            requests.exceptions.ConnectTimeout("1"),
            SahteYanit(200, {"price": "77000.00"}),
        )
        assert a.son_fiyat("BTCUSDT") == 77_000.0
        assert len(t.istekler) == 2  # başarısız + başarılı (fiyat ucu imzasız)


class TestYanitCevirisi:
    def test_market_emri_ortalama_fiyat_bolumden(self) -> None:
        """Market emrinde `price` 0 gelir; gerçek fiyat quote/executed bölümünden çıkar."""
        a, _ = adaptor(SahteYanit(200, KURAL_YANITI), SahteYanit(200, EMIR_YANITI))
        a.sembol_kurallari("BTCUSDT")
        emir = a.market_emri(
            istemci_kimligi="sqABC", sembol="BTCUSDT", yon="BUY", miktar=0.001
        )
        assert emir.ortalama_fiyat == pytest.approx(77_000.0)
        assert emir.dolan_miktar == pytest.approx(0.001)

    def test_dolum_yokken_fiyat_uydurulmuyor(self) -> None:
        a, _ = adaptor()
        emir = a._borsa_emri(
            {**EMIR_YANITI, "status": "NEW", "executedQty": "0",
             "cummulativeQuoteQty": "0"}
        )
        assert emir.ortalama_fiyat == 0.0

    def test_bilinmeyen_durum_tahmin_edilmiyor(self) -> None:
        """Tanınmayan bir durumu 'herhalde açıktır' diye eşlemek sessiz yanlış üretir."""
        a, _ = adaptor()
        with pytest.raises(BilinmeyenDurum, match="YENI_BIR_DURUM"):
            a._borsa_emri({**EMIR_YANITI, "status": "YENI_BIR_DURUM"})

    def test_emir_sorgula_yok_ise_none(self) -> None:
        a, _ = adaptor(SahteYanit(400, {"code": -2013, "msg": "Order does not exist."}))
        assert a.emir_sorgula(sembol="BTCUSDT", istemci_kimligi="sqYOK") is None

    def test_emir_sorgula_baska_hata_yutulmuyor(self) -> None:
        """Yalnızca `-2013` "yok" demektir; başka her red yukarı çıkar."""
        a, _ = adaptor(SahteYanit(400, {"code": -1102, "msg": "Bad parameter."}))
        with pytest.raises(BorsaReddetti):
            a.emir_sorgula(sembol="BTCUSDT", istemci_kimligi="sqX")

    def test_sembol_kurallari_onbellekli(self) -> None:
        a, t = adaptor(SahteYanit(200, KURAL_YANITI))
        a.sembol_kurallari("BTCUSDT")
        sayi = len(t.istekler)
        a.sembol_kurallari("BTCUSDT")
        assert len(t.istekler) == sayi


class TestAnahtarOkuma:
    def test_ortam_dosyayi_eziyor(self, monkeypatch, tmp_path) -> None:
        dosya = tmp_path / ".env"
        dosya.write_text(
            f"{ANAHTAR_DEGISKENI}=dosyadan\n{SIR_DEGISKENI}=dosyadan_sir\n",
            encoding="utf-8",
        )
        monkeypatch.setenv(ANAHTAR_DEGISKENI, "ortamdan")
        monkeypatch.setenv(SIR_DEGISKENI, "ortamdan_sir")
        assert anahtarlari_oku(dosya) == ("ortamdan", "ortamdan_sir")

    def test_dosyadan_okunuyor(self, monkeypatch, tmp_path) -> None:
        monkeypatch.delenv(ANAHTAR_DEGISKENI, raising=False)
        monkeypatch.delenv(SIR_DEGISKENI, raising=False)
        dosya = tmp_path / ".env"
        dosya.write_text(
            f'# yorum\n{ANAHTAR_DEGISKENI}="tirnakli"\n{SIR_DEGISKENI}=sir\n',
            encoding="utf-8",
        )
        assert anahtarlari_oku(dosya) == ("tirnakli", "sir")

    def test_eksikse_yol_gosteren_hata(self, monkeypatch, tmp_path) -> None:
        monkeypatch.delenv(ANAHTAR_DEGISKENI, raising=False)
        monkeypatch.delenv(SIR_DEGISKENI, raising=False)
        with pytest.raises(BorsaHatasi, match="testnet.binance.vision"):
            anahtarlari_oku(tmp_path / "yok.env")
