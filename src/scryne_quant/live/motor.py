"""Paper/gözlem motoru: canlı barların karara ve simüle fill'e dönüştüğü döngü. (Faz 6)

Backtest motorunun (`backtest/motor.py`) canlı ikizi. **Bar içi sıra birebir aynı** ve bu
tesadüf değil, K-001'in ("backtest = paper = live, tek kod yolu") en somut yeri:

    1. Fill      — bir önceki barda onaylanmış niyet, bu barın **açılışından** dolar (K-004)
    2. Risk      — bu barın özkaynağı işlenir (gün dönümü, zirve, drawdown) — karardan önce
    3. Kontrol noktası — durum diske yazılır (aşağıdaki "neden burada")
    4. Karar     — strateji kapanmış barı görür, sinyal risk motorundan geçer
    5. Bekleyen  — kararın özeti kayda yazılır

Backtest'te olmayan tek adım üçüncüsü, ve yeri bir karardır. Kontrol noktası **kararın
öncesinde** yazılıyor çünkü `OnayliNiyet` mühürlü ve mühür süreç başına rastgele (K-032):
serileştirilmiş bir onay, yeniden başlayan süreçte doğrulanamaz. Onu yeniden mühürlemek
"onayın tek üreticisi risk motorudur" garantisini kırardı. Dolayısıyla onay saklanmıyor,
**yeniden türetiliyor** — ve yeniden türetmenin doğru sonucu vermesi için başlangıç
noktasının karardan *önceki* durum olması şart (karar adımı `kill()` ile risk durumunu
değiştirebilir).

Bunun yan etkisi Faz 6'nın en sert kriterini gerçekten ölçülebilir kılıyor: restart bir
"geri yükleme" değil, state'in yeniden üretilebildiğinin **kanıtı**. Yeniden üretilen karar
kayıtlı özetle uyuşmazsa koşu durur (`ToparlanmaAyrismasi`) — tahmin yürütülmez.

**Üç engel, üç farklı katman ve hiçbiri diğerinin yerine geçmiyor:**

- `ok` olmayan bar → ne karar ne fill (K-028). Kopma sonrası REST'ten gelen barlar
  `backfilled` olduğu için bu kural, *bağlı olmadığımız sürede* fill iddia etmeyi
  kendiliğinden engelliyor.
- Bayat veri → yeni **giriş** kararı yok (§24, K-037). Azaltan niyetler geçer.
- Risk motoru → her zaman ve son söz onda.

İlk ikisi sinyali **engeller**, onaylamaz. Engellemenin risk motorunun dışında olması
güvenli; tehlikeli olan tersi olurdu (izin vermek).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final

import numpy as np

from scryne_quant.backtest.defter import uygula as defter_uygula
from scryne_quant.backtest.fill import AtlamaSebebi, Emir, emir_hazirla
from scryne_quant.backtest.metrikler import Islem
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.common.zaman import simdi_ms as duvar_saati
from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.execution.kapi import gonder as execution_gonder
from scryne_quant.features.indikator import atr as atr_hesapla
from scryne_quant.live.akis import Bar, Tazelik
from scryne_quant.live.depo import KosuDeposu, KosuKimligi, KosuOlayi
from scryne_quant.live.pencere import VARSAYILAN_KAPASITE, BarPenceresi
from scryne_quant.portfolio.durum import Portfoy
from scryne_quant.risk.motor import RISK_ATR_PENCERESI, PiyasaOlcumu, RiskMotoru
from scryne_quant.risk.niyet import AZALTAN_YONLER, OnayliNiyet
from scryne_quant.strategy.kosu import gorunum_kur
from scryne_quant.strategy.sinyal import Sinyal
from scryne_quant.strategy.temel import Strateji

#: Bayatlık eşiğinin varsayılanı. Binance kline akışı saniyede birkaç mesaj gönderiyor;
#: 60 saniye sessizlik bir bağlantı sorununun ilk işaretidir. §24'ün örneği 5 saniyelik
#: bir beklenti kuruyor — burada eşik daha gevşek çünkü tetiklendiğinde yaptığı şey
#: (yeni girişi durdurmak) ucuz değil: gereksiz tetiklenen bir guard, kapatılan bir
#: guard'a dönüşür.
VARSAYILAN_AZAMI_VERI_YASI_MS: Final = 60_000

#: Karar verilebilmesi için penceredeki asgari bar sayısı. İki: fill bir önceki bardan,
#: karar bu bardan. Gerçek ihtiyaç stratejinin ısınmasıdır ve onu strateji söylüyor
#: (`Strateji.isinma_bar`); bu sabit yalnızca motorun kendi alt sınırı.
ASGARI_BAR: Final = 2


class MotorHatasi(RuntimeError):
    """Paper motoru sözleşmesi ihlal edildi."""


class ToparlanmaAyrismasi(MotorHatasi):
    """Yeniden üretilen durum kayıtlıyla uyuşmadı. Koşu durur.

    Bu istisna bir hata raporu değil, bir **karar**: uyuşmazlık tespit edildiğinde sistem
    tahmin yürütmez. Faz 7'nin reconciliation kuralının (§25) Faz 6'daki habercisi.
    """


@dataclass(frozen=True, slots=True)
class BarSonucu:
    """Bir barın işlenmesinden çıkan özet. Dashboard ve testler bunu okur."""

    bar_ms: int
    ozkaynak: float
    maruziyet: float
    bar_ok: bool
    bayat: bool
    fill: dict[str, Any] | None = None
    atlama: AtlamaSebebi | None = None
    karar: str | None = None
    """`"onay"` / `"red"` / `None` (strateji sinyal üretmedi)."""

    red_sebebi: str | None = None
    onayli_maruziyet: float | None = None
    kapanan_islem: dict[str, Any] | None = None

    def sozluk(self) -> dict[str, Any]:
        return {
            "bar_ms": self.bar_ms,
            "ozkaynak": self.ozkaynak,
            "maruziyet": self.maruziyet,
            "bar_ok": self.bar_ok,
            "bayat": self.bayat,
            "fill": self.fill,
            "atlama": None if self.atlama is None else str(self.atlama),
            "karar": self.karar,
            "red_sebebi": self.red_sebebi,
            "onayli_maruziyet": self.onayli_maruziyet,
        }


@dataclass(slots=True)
class _Bekleyen:
    """`t`'de onaylanmış, `t+1`'de dolacak niyet. Yalnızca bellekte yaşar."""

    sinyal: Sinyal
    hedef_maruziyet: float
    karar_ms: int
    kisitlayan: tuple[str, ...] = ()

    def ozet(self) -> dict[str, Any]:
        """Kayda yazılan **özet**. Mühür yok — bu bir onay değil, bir karşılaştırma anahtarı."""
        return {
            "sinyal": self.sinyal.model_dump(mode="json"),
            "hedef_maruziyet": self.hedef_maruziyet,
            "karar_ms": self.karar_ms,
            "kisitlayan": list(self.kisitlayan),
        }


class PaperMotoru:
    """Tek sembol, tek strateji, canlı barlarla çalışan simülasyon motoru.

    **Risk motoru zorunlu.** Backtest'te opsiyoneldi (`Backtest(risk=None)`) ve o bilinçli
    bir araştırma seçeneğiydi: Faz 1-4'ün ölçümleri yeniden üretilebilir kalmalıydı. Burada
    öyle bir gerekçe yok — canlı veriyle çalışan bir döngüde risk motorunu kapatmak,
    kapatılabilir bir risk motoru demek olurdu.
    """

    def __init__(
        self,
        *,
        kimlik: KosuKimligi,
        strateji: Strateji,
        maliyet: MaliyetModeli,
        risk: RiskMotoru,
        depo: KosuDeposu,
        kapasite: int = VARSAYILAN_KAPASITE,
        azami_veri_yasi_ms: int = VARSAYILAN_AZAMI_VERI_YASI_MS,
    ) -> None:
        # `live` burada **yok** ve bu bir eksik değil: bu motorun fill'leri simülasyondur.
        # Simüle fill üreten bir koşuya `live` etiketi vermek, drift ölçümünün (Faz 8) iki
        # tarafını aynı kayıtta karıştırırdı. Canlı motor Faz 8'in işi; o gelene kadar
        # `live` etiketli tek bir koşu kaydı bile olmamalı.
        if kimlik.mod not in ("gozlem", "paper"):
            raise MotorHatasi(
                f"paper motoru {kimlik.mod!r} modunda çalışmaz; `gozlem` veya `paper` "
                "bekleniyor (K-035). `live` bu motorun işi değil: fill'ler simüle"
            )
        if risk.mod != kimlik.mod:
            raise MotorHatasi(
                f"risk motoru modu ({risk.mod!r}) koşu moduyla ({kimlik.mod!r}) uyuşmuyor"
            )
        if kimlik.baslangic_sermaye <= 0.0:
            raise MotorHatasi(f"başlangıç sermayesi pozitif olmalı: {kimlik.baslangic_sermaye}")

        self.kimlik = kimlik
        self.strateji = strateji
        self.maliyet = maliyet
        self.risk = risk
        self.depo = depo
        self.tazelik = Tazelik(azami_veri_yasi_ms)
        self.pencere = BarPenceresi(kimlik.sembol, kimlik.timeframe, kapasite=kapasite)

        self.portfoy = Portfoy(nakit=kimlik.baslangic_sermaye)
        self.islemler: list[Islem] = []
        self.acik: Islem | None = None
        self._bekleyen: _Bekleyen | None = None
        self._son_bar_ms: int | None = None
        self._durdu = False

        self.depo.kosu_yaz(kimlik)

    # ------------------------------------------------------------------ ölçüm

    @property
    def bekleyen(self) -> _Bekleyen | None:
        return self._bekleyen

    @property
    def son_bar_ms(self) -> int | None:
        return self._son_bar_ms

    @property
    def durdu(self) -> bool:
        """Koşu bir uyuşmazlık yüzünden durduruldu mu? Durduysa bar işlenmez."""
        return self._durdu

    def fiyat(self) -> float | None:
        """Penceredeki son kapanış. Değerleme ve dashboard bunu kullanıyor."""
        son = self.pencere.son
        return None if son is None else son.close

    # ------------------------------------------------------------------ nabız

    def nabiz(self, simdi: int | None = None) -> None:
        """Akıştan bir mesaj geldiğini bildirir (kapanmamış bar güncellemesi dahil)."""
        self.tazelik.nabiz(duvar_saati() if simdi is None else simdi)

    def tazelik_kontrol(self, simdi: int | None = None) -> bool | None:
        """Bayatlık durumunu kontrol eder; **değiştiyse** kayda yazar ve yeni durumu döner.

        Periyodik olarak çağrılmak üzere var: bayatlığın kendisi bir bar gelmediğinde
        anlaşılır, ve bar gelmediğinde `bar_isle` de çağrılmaz.
        """
        an = duvar_saati() if simdi is None else simdi
        gecis = self.tazelik.gecis_isle(an)
        if gecis is True:
            self.depo.olay_yaz(
                KosuOlayi.BAYAT_GIRIS, ayrinti=self.tazelik.sozluk(an), zaman_ms=an
            )
        elif gecis is False:
            self.depo.olay_yaz(
                KosuOlayi.BAYAT_CIKIS, ayrinti=self.tazelik.sozluk(an), zaman_ms=an
            )
        return gecis

    # ------------------------------------------------------------------ döngü

    def bar_isle(self, bar: Bar, *, simdi: int | None = None) -> BarSonucu:
        """Kapanmış bir barı işler. Backtest motorunun bar içi sırasının aynısı.

        `simdi` duvar saati; verilmezse okunur. Test edilebilirlik için parametre, ama
        asıl sebep kayıt: bayatlık kararına giren an, kayda yazılan anla aynı olmalı.
        """
        if self._durdu:
            raise MotorHatasi("koşu durduruldu; yeni bar işlenmiyor (uyuşmazlık kaydına bakın)")
        an = duvar_saati() if simdi is None else simdi

        # Bayatlık **bu barın nabzından önce** ölçülüyor ve sıra bir karardır. Barın
        # kendisi de bir mesajdır; nabzı önce işlersek akış her bar geldiğinde taze
        # görünür ve guard 1h timeframe'de hiç tetiklenmez. Ölçülmek istenen şey "bu bar
        # gelene kadar ne kadar sessizlik vardı" — çünkü o sessizlikte kaçırılmış bar
        # olabilir ve o hâlde yeni pozisyon açmak §24'ün yasakladığı şey.
        #
        # Bunun ön koşulu: koşturucu **her** akış mesajında `nabiz()` çağırmalı, yalnızca
        # kapanmış barlarda değil. Aksi hâlde her bar bayat sayılır ve guard sürekli açık
        # kalır — o da bir güvenlik açığı değil, ama guard'ı işe yaramaz hâle getirir.
        bayat = self.tazelik.bayat_mi(an)
        self.tazelik.nabiz(an)

        yeni = self.pencere.ekle(bar)
        if not yeni and self._son_bar_ms is not None and bar.open_time <= self._son_bar_ms:
            # Aynı barın revizyonu: kararı yeniden vermiyoruz. Vermek, aynı bar için iki
            # karar ve iki fill üretirdi — canlıda "duplicate order"ın Faz 6'daki hâli.
            raise MotorHatasi(
                f"bar {bar.open_time} zaten işlendi; revizyon karar üretmez (§33 duplicate)"
            )

        diziler = self.pencere.diziler()
        i = len(self.pencere) - 1
        bar_ok = str(diziler["quality_status"][i]) == str(KaliteDurumu.OK)

        # 1) Fill — bekleyen niyet bu barın **açılışından** dolar (K-004).
        fill_kaydi: dict[str, Any] | None = None
        atlama: AtlamaSebebi | None = None
        kapanan: Islem | None = None
        if self._bekleyen is not None:
            if not bar_ok:
                # Kopma sonrası REST'ten gelen bar `backfilled`dır, yani `ok` değil. Yani
                # bağlı olmadığımız sürede fill iddia etmiyoruz — K-028'in canlıdaki en
                # değerli sonucu bu.
                atlama = AtlamaSebebi.FILL_BARI_OK_DEGIL
            else:
                fill_kaydi, kapanan, atlama = self._fill(bar)
            self._bekleyen = None

        fiyat = bar.close

        # 2) Risk durumu — karardan **önce**. Sonra olsaydı drawdown ve günlük zarar bir
        #    bar gecikmeli ölçülür, yani limit bir bar geç devreye girerdi.
        ozkaynak = self.portfoy.ozkaynak(fiyat)
        self.risk.bar_isle(bar.open_time, ozkaynak)
        self._son_bar_ms = bar.open_time

        # 3) Kontrol noktası — kararın **öncesinde**. Gerekçe modül başlığında.
        self.depo.kontrol_noktasi_yaz(
            son_bar_ms=bar.open_time,
            portfoy=_portfoy_sozluk(self.portfoy),
            risk=self.risk.durum.sozluk(),
            acik_islem=None if self.acik is None else asdict(self.acik),
            bayat=bayat,
            bekleyen=None,
            fill=fill_kaydi,
        )

        # 4) Karar.
        karar_adi, red_sebebi, onayli = self._karar_ver(bar, diziler, i, bar_ok, bayat)

        # 5) Bekleyen kararın özeti.
        self.depo.bekleyen_yaz(None if self._bekleyen is None else self._bekleyen.ozet())

        return BarSonucu(
            bar_ms=bar.open_time,
            ozkaynak=self.portfoy.ozkaynak(fiyat),
            maruziyet=self.portfoy.maruziyet(fiyat),
            bar_ok=bar_ok,
            bayat=bayat,
            fill=fill_kaydi,
            atlama=atlama,
            karar=karar_adi,
            red_sebebi=red_sebebi,
            onayli_maruziyet=onayli,
            kapanan_islem=None if kapanan is None else asdict(kapanan),
        )

    # ------------------------------------------------------------------ fill

    def _fill(self, bar: Bar) -> tuple[dict[str, Any] | None, Islem | None, AtlamaSebebi | None]:
        """Bekleyen niyeti bu barın açılışında somut bir emre çevirip uygular."""
        assert self._bekleyen is not None
        b = self._bekleyen
        sonuc = emir_hazirla(
            b.sinyal,
            self.portfoy,
            bar.open,
            bar.open_time,
            self.maliyet,
            hedef_maruziyet=b.hedef_maruziyet,
        )
        if isinstance(sonuc, AtlamaSebebi):
            return None, None, sonuc

        self.portfoy, self.acik, kapanan = defter_uygula(
            sonuc, self.portfoy, self.acik, self.islemler, risk=self.risk
        )
        return self._fill_kaydi(sonuc, b, kapanan), kapanan, None

    def _fill_kaydi(self, emir: Emir, b: _Bekleyen, kapanan: Islem | None) -> dict[str, Any]:
        return {
            "zaman_ms": emir.zaman_ms,
            "sinyal_ms": b.sinyal.timestamp,
            "yon": str(emir.yon),
            "miktar": emir.miktar,
            "fiyat": emir.fiyat,
            "referans_fiyat": emir.referans_fiyat,
            "komisyon": emir.komisyon,
            "onayli_maruziyet": b.hedef_maruziyet,
            "kisitlayan": list(b.kisitlayan),
            "nakit_sonra": self.portfoy.nakit,
            "miktar_sonra": self.portfoy.miktar,
            "ozkaynak_sonra": self.portfoy.ozkaynak(emir.fiyat),
            "gerceklesen_pnl": None if kapanan is None else kapanan.net_pnl,
        }

    # ------------------------------------------------------------------ karar

    def _karar_ver(
        self,
        bar: Bar,
        diziler: dict[str, np.ndarray],
        i: int,
        bar_ok: bool,
        bayat: bool,
    ) -> tuple[str | None, str | None, float | None]:
        """Stratejiyi çağırır, sinyali risk motorundan geçirir, bekleyeni kurar."""
        if not bar_ok or len(self.pencere) < ASGARI_BAR:
            return None, None, None

        gorunum = gorunum_kur(
            self.kimlik.sembol, self.kimlik.timeframe, diziler, self.strateji
        )
        ctx = gorunum.baglam(i, self.portfoy.gorunum(bar.close))
        sinyal = self.strateji.on_bar(ctx)
        if sinyal is None:
            return None, None, None

        # Bayat veri: yeni **giriş** yok (§24). Azaltan niyet geçer — bir çıkışı
        # engellemek riski azaltmaz, artırır (K-037, `AZALTAN_YONLER` ile aynı kural).
        if bayat and sinyal.side not in AZALTAN_YONLER:
            return "atlandi", str(AtlamaSebebi.VERI_BAYAT), None

        karar = self.risk.degerlendir(sinyal, self._olcum(bar, diziler, i))
        if not isinstance(karar, OnayliNiyet):
            return "red", str(karar.sebep), None

        # Execution kapısı: paper'da da borsaya giden yol buradan geçiyor (K-032). Faz
        # 7'de bu çağrının arkasına gerçek emir mantığı gelecek; kapının şimdi de devrede
        # olması, o gün kapının **eklenmesi** gerekmemesi demek.
        kabul = execution_gonder(karar)
        self._bekleyen = _Bekleyen(
            sinyal=sinyal,
            hedef_maruziyet=kabul.hedef_maruziyet,
            karar_ms=kabul.karar_ms,
            kisitlayan=kabul.kisitlayan,
        )
        return "onay", None, kabul.hedef_maruziyet

    def _olcum(self, bar: Bar, diziler: dict[str, np.ndarray], i: int) -> PiyasaOlcumu:
        """Risk motorunun ölçüsü — stratejinin bildirdiği özelliklerden **bağımsız**.

        **Kısa pencerede ATR hesaplanmıyor, `None` veriliyor.** Backtest'te bu durum hiç
        doğmaz: seri baştan sona elde ve ATR bir kez hesaplanır. Canlıda pencere sıfırdan
        büyür, yani ilk `RISK_ATR_PENCERESI + 1` barda seri penceresinden kısa olur ve
        `atr()` haklı olarak hata verir. Hatayı yakalayıp sıfır ya da bir tahmin koymak,
        volatilite guard'ını ve boyut tavanını koşunun ilk saatlerinde sessizce devre
        dışı bırakırdı — oysa `None` "ölçülemedi" demek ve risk motoru ölçülemeyen
        guard'ı **geçilmiş saymıyor** (Faz 5). Koşunun ilk barlarında giriş yapılmaması
        doğru davranıştır.
        """
        gereken = RISK_ATR_PENCERESI + 1
        if len(diziler["close"]) < gereken:
            return self._olcum_kur(bar, None)

        atr = atr_hesapla(
            diziler["high"], diziler["low"], diziler["close"], RISK_ATR_PENCERESI
        )
        deger = float(atr[i])
        return self._olcum_kur(bar, None if np.isnan(deger) else deger)

    def _olcum_kur(self, bar: Bar, atr: float | None) -> PiyasaOlcumu:
        return PiyasaOlcumu(
            fiyat=bar.close,
            ozkaynak=self.portfoy.ozkaynak(bar.close),
            mevcut_maruziyet=self.portfoy.maruziyet(bar.close),
            bar_ms=bar.open_time,
            # `None` "ölçülemedi" demek, sıfır değil: sıfır ATR volatilite guard'ını
            # geçer ve boyut tavanını sonsuz yapardı.
            atr=atr,
        )

    # ------------------------------------------------------------------ özet

    def ozet(self, simdi: int | None = None) -> dict[str, Any]:
        """API ve CLI'ın okuduğu tek görüntü."""
        an = duvar_saati() if simdi is None else simdi
        fiyat = self.fiyat()
        return {
            "kosu": self.kimlik.sozluk(),
            "son_bar_ms": self._son_bar_ms,
            "fiyat": fiyat,
            "portfoy": _portfoy_sozluk(self.portfoy),
            "ozkaynak": None if fiyat is None else self.portfoy.ozkaynak(fiyat),
            "maruziyet": None if fiyat is None else self.portfoy.maruziyet(fiyat),
            "risk": self.risk.ozet(),
            "tazelik": self.tazelik.sozluk(an),
            "pencere": self.pencere.sozluk(),
            "bekleyen": None if self._bekleyen is None else self._bekleyen.ozet(),
            "acik_islem": None if self.acik is None else asdict(self.acik),
            # Kapanan tur sayısı risk durumundan okunuyor, bellekteki listeden değil:
            # toparlanan bir süreçte `islemler` yalnızca açık turu taşır (kapanmış turlar
            # `fill` tablosunda), oysa `RiskDurumu.kapanan_islem` kalıcı ve cooldown
            # sayacının dayandığı sayının ta kendisi.
            "kapanan_islem": self.risk.durum.kapanan_islem,
            "durdu": self._durdu,
        }


def _portfoy_sozluk(p: Portfoy) -> dict[str, Any]:
    return {
        "nakit": p.nakit,
        "miktar": p.miktar,
        "ortalama_maliyet": p.ortalama_maliyet,
        "giris_ms": p.giris_ms,
    }


__all__ = [
    "ASGARI_BAR",
    "VARSAYILAN_AZAMI_VERI_YASI_MS",
    "BarSonucu",
    "MotorHatasi",
    "PaperMotoru",
    "ToparlanmaAyrismasi",
]
