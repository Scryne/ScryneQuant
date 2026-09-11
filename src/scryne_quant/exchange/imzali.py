"""İmzalı Binance istemcisi: emir gönderen adaptör. (K-015, Faz 7)

**Neden ccxt değil, doğrudan `requests`.** Faz 1'in okuma adaptörü ccxt'yi transport olarak
kullanıyor ve bu doğru bir karardı (rate limiter, kalıcı session, hata sınıfları). Emir
tarafında aynı tercih **yanlış** olurdu: bu modülün tek gerçek işi bir ağ hatasının
"istek hiç gitmedi" mi yoksa "yanıt kayboldu" mu olduğunu ayırt etmek, ve ccxt o ayrımı
kendi istisna hiyerarşisinde siliyor — `NetworkError` ikisini de kapsıyor. Silinen ayrım,
duplicate emrin ta kendisi. Burada ham `requests` istisnalarına bakılıyor çünkü ayrımı
yalnızca transport biliyor.

**Zaman: yerel saate güvenilmiyor.** İmzalı her istek `timestamp` taşır ve Binance onu
kendi saatiyle karşılaştırır; fark `recvWindow`u aşarsa istek `-1021` ile reddedilir. Bu
makinede yerel saatin borsadan **2,64 s geride** olduğu ölçüldü (2026-09-11; sapma
kararlı, yayılım 46-247 ms). `recvWindow=5000` ile bugün çalışır, ama saat kaymaya devam
eder ve o gün emirler sessizce reddedilir — sebebi emir mantığında aranır.

İşletim sistemi saatini düzeltmek (`w32tm`) bu sorunu **ertelemek** olurdu. Bunun yerine
timestamp borsanın saatinden türetiliyor: açılışta bir kez ölçülen fark `time.monotonic()`
çıpasına bağlanıyor ve periyodik tazeleniyor. Sistem saati değişse bile — kullanıcı elle
değiştirse, NTP sıçratsa — `monotonic` etkilenmez, yani imza geçerli kalır.

**Sıçrama tespiti.** İki senkron arasında farkın kendisi `SICRAMA_SINIRI_MS`den çok
değiştiyse, o iki senkron arasında üretilmiş timestamp'ler güvenilmez demektir. Bu
`SaatSapmasi` ile raporlanıyor — sessizce yeni değere geçmek, geçersiz bir pencereyi
görünmez yapardı.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from pathlib import Path
from typing import Any, Final, Protocol
from urllib.parse import urlencode

import requests

from scryne_quant.exchange.binance import ipv4_zorla
from scryne_quant.exchange.emir_adaptoru import (
    BorsaEmri,
    EmirAdaptoru,
    borsa_yonu,
    durum_esle,
)
from scryne_quant.exchange.hatalar import (
    BelirsizSonuc,
    BorsaHatasi,
    BorsaReddetti,
    GonderilemediHatasi,
    SaatSapmasi,
)
from scryne_quant.exchange.kurallar import SembolKurallari, miktar_metni, miktar_uydur

#: Spot Testnet. Faz 7'nin tamamı buraya bakar.
TESTNET_HOST: Final = "https://testnet.binance.vision"

#: Canlı host **bilerek burada tanımlı değil.** Faz 8'in ön koşulu gerçek hesap + KYC +
#: yetkili anahtar, ve o geçiş `docs/Kararlar.md`de bir karar olarak yazılacak. Sabiti
#: şimdiden koymak, bir yazım hatasının gerçek parayla işlem yapmasına yetecek kadar
#: yakınlaştırırdı.

#: Anahtarların okunduğu ortam değişkenleri.
ANAHTAR_DEGISKENI: Final = "SQ_BINANCE_TESTNET_API_KEY"
SIR_DEGISKENI: Final = "SQ_BINANCE_TESTNET_API_SECRET"

#: Binance'in kabul ettiği azami `recvWindow` 60.000; 5.000 Binance'in kendi önerisi.
#: Büyütmek sapmayı gizlemek olurdu: geniş pencere, bozuk saati fark etmeden çalıştırır.
RECV_WINDOW_MS: Final = 5_000

#: Saat farkı bu süre geçince yeniden ölçülür.
SENKRON_TAZELIK_MS: Final = 300_000

#: İki senkron arasında fark bu kadar değiştiyse yerel saat sıçramıştır.
SICRAMA_SINIRI_MS: Final = 2_000

#: Okuma isteklerinde yeniden deneme. **Yazma isteklerinde yok** ve olmayacak.
OKUMA_DENEMESI: Final = 4
BEKLEME_TABANI_S: Final = 0.5

TIMEOUT_S: Final = 15.0

#: Binance hata kodları. Tam liste değil — davranışı **değiştiren** kodlar.
KOD_SAAT: Final = -1021
"""Timestamp pencerenin dışında. Emir oluşmadı; sebep saat."""

KOD_DUPLICATE: Final = -2010
"""`Duplicate order sent` bu kodla gelir. Emir oluşmadı — çünkü zaten vardı."""

KOD_EMIR_YOK: Final = -2013
"""`Order does not exist`. Sorgulamanın kesin "hayır"ı."""


class Transport(Protocol):
    """`requests.Session`in bu modülün kullandığı yüzeyi.

    Protokol olarak yazılı çünkü testler gerçek ağa çıkmadan hata sınıflandırmasını
    ölçmek zorunda — ve sınıflandırma bu modülün asıl işi. Ağa çıkan bir testle
    ölçülemeyecek tek şey tam da ölçülmesi gereken şey: yanıtın kaybolduğu an.
    """

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response: ...


def anahtarlari_oku(env_dosyasi: str | Path | None = ".env") -> tuple[str, str]:
    """Ortamdan, yoksa `.env` dosyasından anahtar çifti okur.

    Ortam değişkeni dosyayı **ezer**: bir CI veya servis ortamında anahtar dosyaya değil
    ortama konur, ve yanlışlıkla kalmış bir `.env` onu gölgelememeli.
    """
    anahtar = os.environ.get(ANAHTAR_DEGISKENI, "")
    sir = os.environ.get(SIR_DEGISKENI, "")
    if anahtar and sir:
        return anahtar, sir

    yol = Path(env_dosyasi) if env_dosyasi else None
    if yol is not None and yol.is_file():
        for ham in yol.read_text(encoding="utf-8").splitlines():
            satir = ham.strip()
            if not satir or satir.startswith("#") or "=" not in satir:
                continue
            ad, _, deger = satir.partition("=")
            ad = ad.strip()
            deger = deger.strip().strip("\"'")
            if ad == ANAHTAR_DEGISKENI and not anahtar:
                anahtar = deger
            elif ad == SIR_DEGISKENI and not sir:
                sir = deger

    if not anahtar or not sir:
        raise BorsaHatasi(
            f"testnet anahtarı bulunamadı. {ANAHTAR_DEGISKENI} ve {SIR_DEGISKENI} "
            f"ortam değişkenlerinde ya da .env dosyasında olmalı (bkz. .env.example). "
            f"Anahtar {TESTNET_HOST} adresinden GitHub hesabıyla alınır."
        )
    return anahtar, sir


class SaatSenkronu:
    """Borsa saatini `time.monotonic()` çıpasına bağlı tutar.

    Tutulan şey bir zaman değil bir **fark** ve bir çıpa. Şimdiki borsa zamanı
    `fark_ms + (monotonic() - cipa) * 1000`. Sistem saatini hiç okumaz (tek istisna
    `yerel_sapma_ms`, ki o zaten sistem saatini **ölçmek** için var), o yüzden sistem
    saatinin değişmesinden etkilenmez.
    """

    __slots__ = ("_cipa", "_fark_ms", "_kilit", "_olc", "_son_yerel_sapma_ms")

    def __init__(self, olc: Any) -> None:
        self._olc = olc
        self._kilit = threading.RLock()
        self._fark_ms: float | None = None
        self._cipa: float = 0.0
        self._son_yerel_sapma_ms: int = 0

    def _senkronla(self) -> None:
        t0 = time.monotonic()
        sunucu_ms = float(self._olc())
        t1 = time.monotonic()
        # Gidiş-dönüşün ortası: sunucu zamanı yanıtın *bir yerinde* üretildi, en iyi
        # tahmin orta nokta. Hata ±RTT/2; ölçülen RTT ~300 ms → ±150 ms.
        orta = (t0 + t1) / 2.0
        simdi = time.monotonic()
        yeni_fark = sunucu_ms + (simdi - orta) * 1000.0
        self._son_yerel_sapma_ms = int(time.time() * 1000.0 - sunucu_ms)

        eski = self._fark_ms
        eski_cipa = self._cipa
        self._fark_ms, self._cipa = yeni_fark, simdi

        if eski is not None:
            sicrama = abs(yeni_fark - (eski + (simdi - eski_cipa) * 1000.0))
            if sicrama > SICRAMA_SINIRI_MS:
                raise SaatSapmasi(
                    f"saat sıçradı: iki senkron arasında {sicrama:.0f} ms fark "
                    f"(sınır {SICRAMA_SINIRI_MS} ms). Bu aralıkta üretilmiş imzalar "
                    f"güvenilmez; koşu durmalı ve açık emirler sorgulanmalı."
                )

    def simdi_ms(self) -> int:
        """Borsa saatine göre şimdi, UTC epoch ms."""
        with self._kilit:
            simdi = time.monotonic()
            bayat = (
                self._fark_ms is None
                or (simdi - self._cipa) * 1000.0 > SENKRON_TAZELIK_MS
            )
            if bayat:
                self._senkronla()
                simdi = time.monotonic()
            assert self._fark_ms is not None
            return int(self._fark_ms + (simdi - self._cipa) * 1000.0)

    def yerel_sapma_ms(self) -> int:
        """Yerel saat − borsa saati, son senkrondaki hâliyle. Sağlık göstergesi."""
        with self._kilit:
            if self._fark_ms is None:
                self._senkronla()
            return self._son_yerel_sapma_ms


class BinanceImzaliAdaptoru(EmirAdaptoru):
    """Binance Spot Testnet, imzalı uçlar. (Faz 7)

    Tek sembolle çalışan bir sistem için yazıldı: sembol kuralları ve saat farkı
    önbellekli, `load_markets()` benzeri toplu çağrı yok (Spike 1/6: 3,2 s ve 4.619
    market, tek sembol için saf kayıp).
    """

    __slots__ = ("_host", "_kural_onbellek", "_oturum", "_saat", "_sir")

    def __init__(
        self,
        *,
        anahtar: str | None = None,
        sir: str | None = None,
        host: str = TESTNET_HOST,
        oturum: Transport | None = None,
        ipv4: bool = True,
    ) -> None:
        if anahtar is None or sir is None:
            anahtar, sir = anahtarlari_oku()
        if ipv4 and oturum is None:
            ipv4_zorla()

        self._host = host.rstrip("/")
        self._sir = sir.encode()
        if oturum is None:
            gercek = requests.Session()
            gercek.headers["X-MBX-APIKEY"] = anahtar
            self._oturum: Transport = gercek
        else:
            self._oturum = oturum
        self._saat = SaatSenkronu(self._ham_sunucu_zamani_ms)
        self._kural_onbellek: dict[str, SembolKurallari] = {}

    # ------------------------------------------------------------------- ağ

    def _cagir(
        self,
        method: str,
        yol: str,
        parametreler: dict[str, Any] | None = None,
        *,
        imzali: bool = False,
        yazma: bool = False,
    ) -> Any:
        """Tek ağ giriş noktası. `yazma=True` ise **yeniden deneme yok**.

        Yazma isteklerinde yeniden deneme, bu modülün engellemek için var olduğu şeyin ta
        kendisi: aynı emri iki kez göndermek. Deterministik istemci kimliği ikinciyi
        borsada engeller (`-2010`), ama o korumaya **yaslanarak** tekrar göndermek, tek
        bir katmanı iki katmanmış gibi kullanmaktır.
        """
        p = dict(parametreler or {})
        if imzali:
            p["recvWindow"] = RECV_WINDOW_MS
            p["timestamp"] = self._saat.simdi_ms()

        # Sorgu metni **burada** kuruluyor ve URL'ye gömülüyor; `params=` kullanılmıyor.
        # Sebep: imza sorgu metninin baytları üzerinden hesaplanır, ve `params=` verildiğinde
        # o metni `requests` kendi kodlayıcısıyla yeniden üretir. İki kodlayıcının bugün
        # aynı çıktıyı vermesi bir varsayımdır — bir gün bir sembol adında, bir ondalık
        # gösteriminde ayrışırlarsa imza tutmaz ve hata `-1022` olarak, yani imza hatası
        # olarak görünür; sebebi kodlamada aranmaz. İmzalanan metin gönderilen metin olmalı.
        sorgu = urlencode(p, safe="")
        if imzali:
            imza = hmac.new(self._sir, sorgu.encode(), hashlib.sha256).hexdigest()
            sorgu = f"{sorgu}&signature={imza}"

        url = f"{self._host}{yol}?{sorgu}" if sorgu else f"{self._host}{yol}"
        deneme_sayisi = 1 if yazma else OKUMA_DENEMESI
        son: Exception | None = None

        for deneme in range(deneme_sayisi):
            try:
                yanit = self._oturum.request(method, url, timeout=TIMEOUT_S)
            except requests.exceptions.ConnectTimeout as hata:
                # Bağlantı hiç kurulamadı → istek bayta dökülmedi. Kesin bilgi.
                son = GonderilemediHatasi(f"{yol}: bağlantı kurulamadı: {hata}")
            except requests.exceptions.ReadTimeout as hata:
                # İstek gitti, yanıt gelmedi. Emir oluşmuş **olabilir**.
                if yazma:
                    raise BelirsizSonuc(
                        f"{yol}: istek gönderildi, yanıt gelmedi ({hata}). "
                        f"Emir borsada olabilir; sorgulanmadan yeniden gönderilemez."
                    ) from hata
                son = BorsaHatasi(f"{yol}: okuma zaman aşımı: {hata}")
            except requests.exceptions.ConnectionError as hata:
                # Bağlantı koptu; ne zaman koptuğu bilinmiyor. Yazmada **belirsiz**
                # saymak zorundayız — "herhalde gitmedi" demek duplicate'in kapısıdır.
                if yazma:
                    raise BelirsizSonuc(
                        f"{yol}: bağlantı koptu, sonuç bilinmiyor ({hata})"
                    ) from hata
                son = BorsaHatasi(f"{yol}: bağlantı hatası: {hata}")
            except requests.exceptions.RequestException as hata:
                son = GonderilemediHatasi(f"{yol}: istek kurulamadı: {hata}")
            else:
                return self._yaniti_coz(yanit, yol=yol, yazma=yazma)

            if deneme + 1 < deneme_sayisi:
                time.sleep(BEKLEME_TABANI_S * (2**deneme))

        assert son is not None
        raise son

    def _yaniti_coz(self, yanit: requests.Response, *, yol: str, yazma: bool) -> Any:
        durum = yanit.status_code
        if durum == 200:
            return yanit.json()

        # 5xx: Binance'in kendi sözleşmesi gereği **yürütme durumu bilinmiyor**.
        # 504 açıkça "istek alındı ama sonuç zamanında gelmedi" demek.
        if durum >= 500:
            if yazma:
                raise BelirsizSonuc(
                    f"{yol}: borsa {durum} döndü — yürütme durumu bilinmiyor. "
                    f"Emir sorgulanmadan yeniden gönderilemez."
                )
            raise BorsaHatasi(f"{yol}: borsa {durum} döndü")

        kod, mesaj = self._hata_govdesi(yanit)
        if kod == KOD_SAAT:
            raise SaatSapmasi(
                f"{yol}: timestamp penceresi dışında (-1021). Son ölçülen yerel sapma: "
                f"{self._saat.yerel_sapma_ms()} ms, recvWindow {RECV_WINDOW_MS} ms."
            )
        if durum in (418, 429):
            raise BorsaReddetti(f"{yol}: hız sınırı ({durum}): {mesaj}", kod=kod)
        raise BorsaReddetti(f"{yol}: borsa reddetti ({durum}): {mesaj}", kod=kod)

    @staticmethod
    def _hata_govdesi(yanit: requests.Response) -> tuple[int | None, str]:
        try:
            govde = yanit.json()
        except ValueError:
            return None, yanit.text[:200]
        if isinstance(govde, dict):
            kod = govde.get("code")
            return (int(kod) if isinstance(kod, int) else None), str(govde.get("msg", ""))
        return None, str(govde)[:200]

    def _ham_sunucu_zamani_ms(self) -> int:
        return int(self._cagir("GET", "/api/v3/time")["serverTime"])

    # ------------------------------------------------------------ EmirAdaptoru

    def sunucu_zamani_ms(self) -> int:
        return self._saat.simdi_ms()

    def saat_sapmasi_ms(self) -> int:
        return self._saat.yerel_sapma_ms()

    def sembol_kurallari(self, sembol: str) -> SembolKurallari:
        if sembol in self._kural_onbellek:
            return self._kural_onbellek[sembol]
        govde = self._cagir("GET", "/api/v3/exchangeInfo", {"symbol": sembol})
        semboller = govde.get("symbols") or []
        if not semboller:
            raise BorsaHatasi(f"sembol bulunamadı: {sembol}")
        s = semboller[0]
        filtreler = {f["filterType"]: f for f in s.get("filters", [])}
        notional = filtreler.get("NOTIONAL") or filtreler.get("MIN_NOTIONAL") or {}
        kural = SembolKurallari(
            sembol=str(s["symbol"]),
            tick_size=float(filtreler["PRICE_FILTER"]["tickSize"]),
            step_size=float(filtreler["LOT_SIZE"]["stepSize"]),
            min_notional=float(notional.get("minNotional", 0.0)),
            durum=str(s["status"]),
        )
        self._kural_onbellek[sembol] = kural
        return kural

    def son_fiyat(self, sembol: str) -> float:
        return float(
            self._cagir("GET", "/api/v3/ticker/price", {"symbol": sembol})["price"]
        )

    def market_emri(
        self, *, istemci_kimligi: str, sembol: str, yon: str, miktar: float
    ) -> BorsaEmri:
        kural = self.sembol_kurallari(sembol)
        uydurulmus = miktar_uydur(miktar, kural.step_size)
        govde = self._cagir(
            "POST",
            "/api/v3/order",
            {
                "symbol": sembol,
                "side": borsa_yonu(yon),
                "type": "MARKET",
                "quantity": miktar_metni(uydurulmus, kural.step_size),
                "newClientOrderId": istemci_kimligi,
                "newOrderRespType": "FULL",
            },
            imzali=True,
            yazma=True,
        )
        return self._borsa_emri(govde)

    def emir_sorgula(self, *, sembol: str, istemci_kimligi: str) -> BorsaEmri | None:
        try:
            govde = self._cagir(
                "GET",
                "/api/v3/order",
                {"symbol": sembol, "origClientOrderId": istemci_kimligi},
                imzali=True,
            )
        except BorsaReddetti as hata:
            if hata.kod == KOD_EMIR_YOK:
                return None
            raise
        return self._borsa_emri(govde)

    def acik_emirler(self, sembol: str) -> list[BorsaEmri]:
        govde = self._cagir("GET", "/api/v3/openOrders", {"symbol": sembol}, imzali=True)
        return [self._borsa_emri(e) for e in govde]

    def bakiye(self) -> dict[str, float]:
        govde = self._cagir("GET", "/api/v3/account", imzali=True)
        return {
            str(b["asset"]): float(b["free"])
            for b in govde.get("balances", [])
            if float(b["free"]) > 0.0 or float(b["locked"]) > 0.0
        }

    # ---------------------------------------------------------------- çeviri

    @staticmethod
    def _borsa_emri(govde: dict[str, Any]) -> BorsaEmri:
        """Binance yanıtını `BorsaEmri`ye çevirir.

        Ortalama fiyat `cummulativeQuoteQty / executedQty` ile hesaplanıyor (Binance'in
        yazım hatalı alan adı dahil): market emrinde `price` alanı 0 gelir, gerçek fill
        fiyatı yalnızca bu bölümden çıkar. Dolan miktar sıfırken bölme yapılmıyor —
        fiyatı 0 bırakmak, uydurulmuş bir fiyat yazmaktan dürüst.
        """
        dolan = float(govde.get("executedQty", 0.0) or 0.0)
        kote = float(govde.get("cummulativeQuoteQty", 0.0) or 0.0)
        ham = str(govde.get("status", ""))
        zaman = (
            govde.get("updateTime") or govde.get("transactTime") or govde.get("time") or 0
        )
        return BorsaEmri(
            istemci_kimligi=str(govde.get("clientOrderId", "")),
            borsa_kimligi=str(govde.get("orderId", "")),
            sembol=str(govde.get("symbol", "")),
            yon=str(govde.get("side", "")),
            durum=durum_esle(ham),
            miktar=float(govde.get("origQty", 0.0) or 0.0),
            dolan_miktar=dolan,
            ortalama_fiyat=(kote / dolan) if dolan > 0.0 else 0.0,
            guncellendi_ms=int(zaman),
            ham_durum=ham,
        )


__all__ = [
    "ANAHTAR_DEGISKENI",
    "KOD_DUPLICATE",
    "KOD_EMIR_YOK",
    "KOD_SAAT",
    "RECV_WINDOW_MS",
    "SICRAMA_SINIRI_MS",
    "SIR_DEGISKENI",
    "TESTNET_HOST",
    "BinanceImzaliAdaptoru",
    "SaatSenkronu",
    "Transport",
    "anahtarlari_oku",
]
