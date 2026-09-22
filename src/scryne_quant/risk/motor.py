"""Risk motoru: sinyalin onaya dönüştüğü tek yer. (§11, K-008, K-010, K-032)

Motorun tek sorusu §11'in sorusu: *"Bu sinyal teknik olarak doğru olsa bile bunu şimdi ve
bu büyüklükte gerçekleştirmek güvenli mi?"*

**Karar sırası sabittir ve sıranın kendisi bir karardır:**

    0. Azaltan niyet mi?      → evetse hiçbir engel uygulanmaz, olduğu gibi onaylanır
    1. Ölçüm geçerli mi?      → fiyat/özkaynak ≤ 0 ise karar verilmez
    2. SAFE_MODE              → kill switch açıksa yeni giriş yok (K-008/1)
    3. Promotion              → bu mod için zincir yeterli mi (K-010)
    4. Drawdown limiti        → aşıldıysa **kill switch tetiklenir**, sonra reddedilir
    5. Günlük zarar limiti    → aşıldıysa gün dönümüne kadar giriş yok
    6. Cooldown               → ardışık kayıp penceresi açıksa giriş yok
    7. Volatilite guard       → ATR/fiyat eşiğin üstündeyse giriş yok
    8. Boyutlandırma          → azami maruziyet ve işlem başına risk hedefi aşağı çeker

Sıranın iki yeri kritik:

- **Sıfır adım ilk.** Bir çıkışı engellemek riski azaltmaz, artırır. K-008/3 ("mevcut
  çıkış emirleri çalışmaya devam eder") bu adımın genel hâli: halt, cooldown, SAFE_MODE —
  hiçbiri pozisyon küçültmeyi durdurmaz. Bu adım sonra gelseydi, kill switch tetiklenen
  bir sistemde strateji `FLAT` diyemez, yani pozisyondan çıkamaz hâle gelirdi. Bu,
  kill switch'in amacının tam tersini yapardı: riski dondurmak yerine kilitlemek.
- **Durdurmalar boyutlandırmadan önce.** Ters sırada, reddedilecek bir sinyal için boyut
  hesaplanır ve audit'e "şu kadar onaylanacaktı" diye yanıltıcı bir sayı girerdi.

**Motor karar verir, uygulamaz.** Emir üretmez, portföye dokunmaz, borsaya bakmaz. Çıktısı
`OnayliNiyet` veya `Red`; ikisi de veridir. Uygulayan katman backtest motoru (Faz 5'te
`risk=` parametresi) ve execution (Faz 7).

**Determinizm (K-009).** Motor rastgelelik içermez ve duvar saatine bakmaz; tüm kararlar
bar zamanından ve durumdan türer. Mühür (`muhur.py`) süreç başına rastgeledir ama hiçbir
hash'e girmez — `OnayliNiyet.sozluk()` mührü yazmıyor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.risk import niyet as niyet_mod
from scryne_quant.risk.audit import Defter, Olay, OlayTuru
from scryne_quant.risk.durum import RiskDurumu
from scryne_quant.risk.limitler import RiskLimitleri
from scryne_quant.risk.niyet import Karar, OnayliNiyet, PortfoyKarari, Red, RedSebebi
from scryne_quant.risk.promotion import MOD_ESIGI, Asama, yeterli_mi
from scryne_quant.strategy.hedef import HedefPortfoy
from scryne_quant.strategy.sinyal import Sinyal

#: Çalışma modları. `MOD_ESIGI` her birinin hangi promotion aşamasını şart koştuğunu
#: söylüyor; buradaki tuple yalnızca geçerli ad kümesi.
#:
#: `gozlem` Faz 6'da eklendi (K-035): canlı veride koşan ama promotion kanıtı **üretemeyen**
#: mod. Risk motorunun promotion dışındaki her limiti orada da tam olarak uygulanır; tek
#: farkı `MOD_ESIGI` eşiğinin `YOK` olması. Gerekçe K-035'te: altyapıyı ölçmek için kapıyı
#: indirmek, kapının var olma sebebini yok ederdi.
#: `shadow` K-114'te eklendi (Faz-8-Hazirlik §1.3/1): emir gönderilmeyen ama gerçek hesabı
#: okuyan canlı provası; eşiği `LIVE_ADAYI` — sırada yalnızca insan onayı var. Diğer modların
#: davranışı değişmedi (yeni bir ad, yeni bir eşik; mevcut eşlemeler aynı).
MODLAR: Final[tuple[str, ...]] = ("backtest", "gozlem", "paper", "shadow", "live")

#: Hedefi aşağı çekebilen limitler. Audit'te "hangi limit kısıtladı" sayımı bunu kullanıyor.
#: İlk ikisi sinyal düzeyinde, son ikisi portföy düzeyinde (Faz 10).
KISIT_ADLARI: Final[tuple[str, ...]] = (
    "azami_maruziyet",
    "islem_basina_risk",
    "azami_brut_maruziyet",
    "azami_enstruman",
)

#: Portföy düzeyinde uygulanan kısıtlar. Bunlar **yalnızca aşağı çeker** ve yalnızca
#: artıran niyetlere uygulanır: brüt maruziyeti düşüren bir emri brüt maruziyet limitiyle
#: engellemek, limitin amacının tersini yapardı (K-008/3 ile aynı mantık).
PORTFOY_KISIT_ADLARI: Final[tuple[str, ...]] = ("azami_brut_maruziyet", "azami_enstruman")

#: Risk motorunun volatilite ölçüsünün penceresi. Stratejinin bildirdiği özelliklerden
#: **bağımsız**: risk kendi ölçüsünü kendi alır (`PiyasaOlcumu`). 14, limitlerin
#: kalibre edildiği pencere (`docs/Faz-5-Risk-Raporu.md`) — değiştirmek
#: `volatilite_esigi` ve `ters_hareket_atr_carpani`yi yeniden ölçmeyi gerektirir.
#:
#: Faz 3'te `backtest/motor.py`de doğdu, Faz 6'da buraya taşındı: paper döngüsü de aynı
#: pencereyi kullanmak zorunda ve ikisinin ayrışması, risk limitlerinin backtest'te bir
#: canlıda başka bir volatilite ölçüsüyle uygulanması demek olurdu (K-001).
RISK_ATR_PENCERESI: Final = 14

#: Kill switch sebep kodları. Audit'te gruplanabilmesi için kod, cümle değil.
KILL_DRAWDOWN: Final = "DRAWDOWN_LIMITI"

#: Gönderilmeye değer en küçük maruziyet. Bunun altına inen bir hedef onaylanmaz:
#: **sıfır boyutlu bir onay, audit'te "onaylandı" diye görünür ama execution'a gidecek bir
#: emir üretmez** — yani sayım yanlış olur ve "kaç sinyal onaylandı" sorusunun cevabı
#: şişer.
#:
#: Bu sayı borsanın gerçek minimum emir büyüklüğü **değil**; o Faz 7'nin konusu (§33) ve
#: sembol başına farklıdır. Buradaki eşik yalnızca "ölçülebilir bir şey kaldı mı"
#: sorusunu cevaplıyor. `fill.ASGARI_ORAN` ile aynı mertebede olması tesadüf değil: ikisi
#: de kayan nokta artığını sıfır saymak için var.
ASGARI_MARUZIYET: Final = 1e-9


class RiskHatasi(ValueError):
    """Risk motoru kurulumu geçersiz."""


@dataclass(frozen=True, slots=True)
class PiyasaOlcumu:
    """Risk motorunun karar için ihtiyaç duyduğu, stratejiden bağımsız ölçüler.

    **Stratejinin `ctx`inden gelmiyor, ayrı veriliyor.** Strateji ne gördüğünü kendi
    bildirdiği özelliklerden okur (K-002); risk motoru kendi ölçüsünü kendi alır. İkisini
    birleştirmek, stratejinin ATR'yi bildirmediği bir koşuda volatilite guard'ını sessizce
    devre dışı bırakırdı — ve o sessizlik tam olarak bu projenin kaçındığı şey.
    """

    fiyat: float
    """Kararın dayandığı fiyat (sinyal barının kapanışı)."""

    ozkaynak: float
    """Portföyün o andaki toplam özkaynağı (nakit + pozisyon değeri)."""

    mevcut_maruziyet: float
    """Portföyün şu andaki maruziyeti [0,1]."""

    bar_ms: int
    """Kararın verildiği barın açılış zamanı (UTC epoch ms, K-005)."""

    atr: float | None = None
    """Aynı timeframe'de ATR. `None` = ölçülemedi; volatilite guard'ı o hâlde **reddeder**."""

    @property
    def atr_oran(self) -> float | None:
        """ATR'nin fiyata oranı. Volatilite guard'ının ölçtüğü büyüklük."""
        if self.atr is None or self.fiyat <= 0.0:
            return None
        return self.atr / self.fiyat

    def sozluk(self) -> dict[str, Any]:
        return {
            "fiyat": self.fiyat,
            "ozkaynak": self.ozkaynak,
            "mevcut_maruziyet": self.mevcut_maruziyet,
            "bar_ms": self.bar_ms,
            "atr": self.atr,
            "atr_oran": self.atr_oran,
        }


class RiskMotoru:
    """Sinyalleri değerlendirir, onaylar veya reddeder; durumu barlar arasında tutar."""

    def __init__(
        self,
        limitler: RiskLimitleri,
        timeframe: str,
        *,
        mod: str = "backtest",
        defter: Defter | None = None,
        durum: RiskDurumu | None = None,
        asamalar: dict[str, Asama] | None = None,
    ) -> None:
        if mod not in MODLAR:
            raise RiskHatasi(f"bilinmeyen mod {mod!r}; geçerli: {', '.join(MODLAR)}")
        self.limitler = limitler
        self.timeframe = timeframe
        self.mod = mod
        self.defter = defter
        self.durum = durum if durum is not None else RiskDurumu()

        self.asamalar: dict[str, Asama] = dict(asamalar or {})
        """Strateji adı → promotion aşaması. Kayıtlı olmayan strateji `YOK` sayılır —
        yani `paper`/`live` modunda reddedilir. Varsayılanın güvenli yöne düşmesi şart:
        tanınmayan bir stratejiyi geçerli saymak, zinciri atlamanın en kolay yolu olurdu."""

        self._bar_ms = timeframe_ms(timeframe)
        self.limit_kimligi = limitler.kimlik()

        # Sayaçlar: sıfır olanlar da tutuluyor — yokluk da bir bilgi (Faz 3'ün
        # `atlama_sayimi` kalıbı).
        self.red_sayimi: dict[str, int] = dict.fromkeys((s.value for s in RedSebebi), 0)
        self.kisit_sayimi: dict[str, int] = dict.fromkeys(KISIT_ADLARI, 0)
        self.onay_sayisi = 0
        self.degerlendirilen = 0

    # ------------------------------------------------------------------ durum akışı

    def bar_isle(self, zaman_ms: int, ozkaynak: float) -> None:
        """Her barda bir kez çağrılır: özkaynağı işaretler, gün dönümünü yapar.

        Drawdown **burada** kontrol edilmiyor, kararda kontrol ediliyor. Sebebi: drawdown
        limiti aşıldığında tetiklenen şey kill switch ve K-008/5 o anın tam durumunu
        audit'e yazmayı istiyor — "hangi sinyal sırasında" bilgisi o durumun parçası.
        """
        self.durum.bar_isle(zaman_ms, ozkaynak)

    def islem_kapandi(self, net_pnl: float, zaman_ms: int) -> bool:
        """Kapanan bir işlemi bildirir. Cooldown tetiklendiyse `True`."""
        tetiklendi = self.durum.islem_kapandi(
            net_pnl,
            zaman_ms,
            limit=self.limitler.ardisik_kayip_limiti,
            cooldown_ms=self.limitler.cooldown_bar * self._bar_ms,
        )
        if tetiklendi:
            self._audit(
                OlayTuru.COOLDOWN,
                zaman_ms,
                "",
                {
                    "sebep": "ardisik_kayip",
                    "limit": self.limitler.ardisik_kayip_limiti,
                    "cooldown_bar": self.limitler.cooldown_bar,
                    "bitis_ms": self.durum.cooldown_bitis_ms,
                },
            )
        return tetiklendi

    # ------------------------------------------------------------------ kill switch

    def kill(self, sebep: str, zaman_ms: int, ayrinti: dict[str, Any] | None = None) -> None:
        """Kill switch'i tetikler (K-008). Zaten SAFE_MODE'daysa ilk sebep korunur.

        K-008'in beş davranışı ve nerede gerçekleştikleri:

        1. *Yeni pozisyon girişi durur* — `degerlendir`in 2. adımı, istisnasız.
        2. *Açık pozisyonlar otomatik kapatılmaz* — bu metot portföye dokunmuyor; motorun
           pozisyon kapatma yetkisi **yok**. Spot piyasada likidasyon riski olmadığı için
           pozisyonu tutmak güvenli; panik satışı sorunu çözmez, zararı gerçekleştirir.
        3. *Mevcut çıkışlar çalışmaya devam eder* — `degerlendir`in 0. adımı azaltan
           niyetleri hiçbir engele tabi tutmuyor.
        4. *SAFE_MODE ve yalnızca elle çıkış* — `durum.safe_mode`; tek kapatma yolu
           `serbest_birak`.
        5. *Sebep + o anki tüm durum audit'e* — aşağıdaki `_audit` çağrısı.
        """
        if self.durum.safe_mode:
            return
        self.durum.kill(sebep, zaman_ms)
        self._audit(OlayTuru.KILL, zaman_ms, "", {"sebep": sebep, **(ayrinti or {})})

    def serbest_birak(self, not_metni: str, zaman_ms: int) -> None:
        """SAFE_MODE'u **elle** kapatır (K-008/4). Gerekçe zorunlu.

        Kod içinden koşula bağlı çağrılmaması bir sözleşme, ve `tests/unit/test_kill_switch.py`
        `risk/` içinde bu metodu çağıran başka bir yer olmadığını statik olarak kontrol
        ediyor: kendini kapatan bir kill switch, bir uyarıdır.
        """
        metin = not_metni.strip()
        if len(metin) < 10:
            raise RiskHatasi(
                "SAFE_MODE'dan çıkış bir gerekçe ister (≥10 karakter): sebebi yazılmadan "
                "kapatılan bir kill switch, bir daha neden tetiklendiğini kimseye "
                "anlatamaz (K-008/5)"
            )
        if not self.durum.safe_mode:
            raise RiskHatasi("SAFE_MODE açık değil; serbest bırakılacak bir şey yok")
        onceki = self.durum.safe_mode_sebep
        self.durum.serbest_birak()
        self._audit(
            OlayTuru.SERBEST, zaman_ms, "", {"onceki_sebep": onceki, "gerekce": metin}
        )

    # ------------------------------------------------------------------ karar

    def degerlendir(self, sinyal: Sinyal, olcum: PiyasaOlcumu) -> Karar:
        """Sinyali değerlendirir. **Onay üreten tek yol budur.**

        Dönen `Red` de bir sonuç: audit'e yazılır, sayılır, raporlanır. `None` dönmüyor —
        "sinyal kayboldu" diye bir durum olmamalı.
        """
        self.degerlendirilen += 1
        karar = self._karar(sinyal, olcum)
        self._kaydet(karar, olcum)
        return karar

    def _karar(self, sinyal: Sinyal, olcum: PiyasaOlcumu) -> Karar:
        sonuc = self._karar_hedefi(sinyal, olcum)
        if isinstance(sonuc, Red):
            return sonuc
        hedef, kisitlayan = sonuc
        return self._onay(sinyal, hedef, olcum, kisitlayan)

    def _karar_hedefi(
        self, sinyal: Sinyal, olcum: PiyasaOlcumu
    ) -> tuple[float, tuple[str, ...]] | Red:
        """Sinyal düzeyindeki 0-8 adımı. Döner: `(onaylanabilir hedef, kısıtlayanlar)` ya da `Red`.

        Onayı **üretmiyor**, yalnızca hedefi hesaplıyor. Ayrımın sebebi portföy düzeyi
        (Faz 10): brüt maruziyet ve enstrüman sayısı tavanları hedefleri aşağı çekebilir ve
        `OnayliNiyet` mühürlü/değişmez olduğu için bu düzeltmenin mühürden **önce** olması
        şart. Aksi hâlde ya mühür kırılırdı ya da portföy düzeyi ikinci bir onay tipi
        üretirdi — ikisi de "onay üreten tek yer" iddiasını böler.
        """
        # 0) Azaltan niyet: hiçbir engel uygulanmaz. Bir çıkışı engellemek riski artırır.
        if sinyal.side in niyet_mod.AZALTAN_YONLER:
            return sinyal.target_exposure, ()

        # 1) Geçersiz ölçümle karar verilmez. Tahmin etmek yerine reddetmek, K-007'nin
        #    "belirsizlikte kötü yöne yuvarla" kuralının bu katmandaki karşılığı.
        if olcum.fiyat <= 0.0 or olcum.ozkaynak <= 0.0:
            return self._red_nesnesi(
                sinyal,
                RedSebebi.GECERSIZ_OLCUM,
                olcum,
                {"fiyat": olcum.fiyat, "ozkaynak": olcum.ozkaynak},
            )

        # 2) SAFE_MODE: yeni giriş yok, istisnasız (K-008/1).
        if self.durum.safe_mode:
            return self._red_nesnesi(
                sinyal,
                RedSebebi.SAFE_MODE,
                olcum,
                {
                    "safe_mode_sebep": self.durum.safe_mode_sebep,
                    "safe_mode_ms": self.durum.safe_mode_ms,
                },
            )

        # 3) Promotion: bu mod bu stratejiyi kabul ediyor mu (K-010)?
        gereken = MOD_ESIGI[self.mod]
        asama = self.asamalar.get(self._strateji_adi(sinyal), Asama.YOK)
        if not yeterli_mi(asama, gereken):
            return self._red_nesnesi(
                sinyal,
                RedSebebi.PROMOTION_YOK,
                olcum,
                {"mod": self.mod, "asama": str(asama), "gereken": str(gereken)},
            )

        # 4) Drawdown: limit aşıldıysa bu bir fren değil kontak kapatmadır.
        #
        # Karşılaştırma **çarpmayla**: `1 - son/zirve > limit` yerine
        # `son < zirve × (1 - limit)`. Sebebi kayan nokta: 8.000/10.000 için birincisi
        # 0,19999999999999996 üretir ve "tam %20 düşüş" limiti aşmış görünür. İkincisi
        # tam sayılarla tam sonuç verir. Sınır davranışı bir tercih ve yazılı olmak
        # zorunda — bu motorda sınır **dahil** geçer.
        dd = self.durum.drawdown
        if self.durum.son_ozkaynak < self.durum.zirve_ozkaynak * (
            1.0 - self.limitler.drawdown_limiti
        ):
            self.kill(
                KILL_DRAWDOWN,
                olcum.bar_ms,
                {
                    "drawdown": dd,
                    "limit": self.limitler.drawdown_limiti,
                    "zirve_ozkaynak": self.durum.zirve_ozkaynak,
                    "son_ozkaynak": self.durum.son_ozkaynak,
                    "mevcut_maruziyet": olcum.mevcut_maruziyet,
                },
            )
            return self._red_nesnesi(
                sinyal,
                RedSebebi.DRAWDOWN,
                olcum,
                {"drawdown": dd, "limit": self.limitler.drawdown_limiti},
            )

        # 5) Günlük zarar: gün dönümünde kendiliğinden kalkan geçici bir durdurma.
        #    Karşılaştırma yine çarpmayla — drawdown'daki aynı kayan nokta gerekçesi.
        gunluk = self.durum.gunluk_getiri
        if self.durum.son_ozkaynak < self.durum.gun_basi_ozkaynak * (
            1.0 - self.limitler.gunluk_zarar_limiti
        ):
            return self._red_nesnesi(
                sinyal,
                RedSebebi.GUNLUK_ZARAR,
                olcum,
                {
                    "gunluk_getiri": gunluk,
                    "limit": -self.limitler.gunluk_zarar_limiti,
                    "gun_basi_ozkaynak": self.durum.gun_basi_ozkaynak,
                },
            )

        # 6) Cooldown: ardışık kayıp penceresi.
        if self.durum.cooldownda_mi(olcum.bar_ms):
            return self._red_nesnesi(
                sinyal,
                RedSebebi.COOLDOWN,
                olcum,
                {
                    "bitis_ms": self.durum.cooldown_bitis_ms,
                    "kalan_bar": self._kalan_bar(olcum.bar_ms),
                },
            )

        # 7) Volatilite guard. Ölçülemeyen guard geçilmiş sayılmaz (K-019'un cümlesi
        #    promotion için yazılmıştı; risk tarafında aynısı geçerli ve daha da sert:
        #    volatiliteyi bilmeden boyut hesaplanamaz).
        oran = olcum.atr_oran
        if oran is None:
            return self._red_nesnesi(
                sinyal, RedSebebi.VOLATILITE_OLCULEMEDI, olcum, {"atr": olcum.atr}
            )
        if oran > self.limitler.volatilite_esigi:
            return self._red_nesnesi(
                sinyal,
                RedSebebi.VOLATILITE,
                olcum,
                {"atr_oran": oran, "esik": self.limitler.volatilite_esigi},
            )

        # 8) Boyutlandırma: iki tavan, düşük olanı bağlar.
        hedef, kisitlayan = self._boyutlandir(sinyal.target_exposure, oran)
        if hedef < ASGARI_MARUZIYET:
            return self._red_nesnesi(
                sinyal,
                RedSebebi.SIFIR_BOYUT,
                olcum,
                {"kisitlayan": list(kisitlayan), "atr_oran": oran},
            )
        return hedef, kisitlayan

    # ------------------------------------------------------------------ portföy düzeyi

    def portfoy_degerlendir(
        self,
        hedef: HedefPortfoy,
        olcumler: dict[str, PiyasaOlcumu],
        *,
        mevcut_maruziyetler: dict[str, float],
    ) -> PortfoyKarari:
        """Bir hedef portföyü değerlendirir. **Portföy düzeyinde onay üreten tek yol budur.**

        Sıra: önce her sinyal kendi 0-8 adımından geçer, **sonra** portföy düzeyi tavanları
        (brüt maruziyet, enstrüman sayısı) kalanları aşağı çeker. Ters sırada, sinyal
        düzeyinde reddedilecek bir hedef brüt bütçeden yer kaplar ve geçecek bir hedefi
        sessizce kısardı.

        `mevcut_maruziyetler` **tüm** açık pozisyonları içerir — hedefte bahsedilmeyenleri
        de. Bahsedilmeyen bir pozisyon da brüt maruziyetin parçasıdır; yalnızca bahsedilene
        bakan bir tavan, portföyün yarısını görmeyen bir tavan olurdu.

        Portföy katmanı **izin veremez** (K-037): hiçbir hedef sinyal düzeyinde onaylanan
        değerin üstüne çıkamaz, yalnızca aşağı çekilir veya reddedilir.
        """
        self.degerlendirilen += len(hedef.sinyaller)

        adaylar: dict[str, tuple[float, tuple[str, ...]]] = {}
        redler: dict[str, Red] = {}
        for sinyal in hedef.sinyaller:
            sembol = sinyal.symbol
            if sembol not in olcumler:
                raise RiskHatasi(
                    f"{sembol}: piyasa ölçümü verilmedi. Ölçümsüz karar vermek, "
                    "volatiliteyi bilmeden boyut hesaplamak olurdu"
                )
            sonuc = self._karar_hedefi(sinyal, olcumler[sembol])
            if isinstance(sonuc, Red):
                redler[sembol] = sonuc
            else:
                adaylar[sembol] = sonuc

        portfoy_kisiti = self._portfoy_kisitla(
            hedef, adaylar, redler, mevcut_maruziyetler, olcumler
        )

        kararlar: list[Karar] = []
        for sinyal in hedef.sinyaller:
            sembol = sinyal.symbol
            if sembol in redler:
                karar: Karar = redler[sembol]
            else:
                h, kisit = adaylar[sembol]
                karar = self._onay(sinyal, h, olcumler[sembol], kisit)
            self._kaydet(karar, olcumler[sembol])
            kararlar.append(karar)

        return PortfoyKarari(hedef=hedef, kararlar=tuple(kararlar), portfoy_kisiti=portfoy_kisiti)

    def _portfoy_kisitla(
        self,
        hedef: HedefPortfoy,
        adaylar: dict[str, tuple[float, tuple[str, ...]]],
        redler: dict[str, Red],
        mevcut: dict[str, float],
        olcumler: dict[str, PiyasaOlcumu],
    ) -> tuple[str, ...]:
        """Brüt maruziyet ve enstrüman sayısı tavanlarını uygular. `adaylar`ı yerinde kısar."""
        uygulanan: list[str] = []
        bahsedilen = set(hedef.semboller)
        disarida = sum(d for s, d in sorted(mevcut.items()) if s not in bahsedilen and d > 0.0)

        # --- brüt maruziyet: yalnızca **artıran** hedefler kısılır.
        artiran = {s for s, (h, _) in adaylar.items() if h > mevcut.get(s, 0.0)}
        sabit = disarida + sum(h for s, (h, _) in sorted(adaylar.items()) if s not in artiran)
        istenen = sum(h for s, (h, _) in sorted(adaylar.items()) if s in artiran)
        tavan = self.limitler.azami_brut_maruziyet

        if artiran and sabit + istenen > tavan:
            butce = max(0.0, tavan - sabit)
            olcek = butce / istenen if istenen > 0.0 else 0.0
            uygulanan.append("azami_brut_maruziyet")
            self.kisit_sayimi["azami_brut_maruziyet"] += 1
            for sembol in sorted(artiran):
                h, kisit = adaylar[sembol]
                # Tavan mevcut maruziyetin altına **indirmez**: bu bir zorunlu satış emri
                # olurdu ve stratejinin istemediği bir çıkışı risk motoru üretmiş olurdu.
                yeni_h = max(h * olcek, min(h, mevcut.get(sembol, 0.0)))
                if yeni_h < ASGARI_MARUZIYET:
                    redler[sembol] = self._red_nesnesi(
                        hedef.sinyal(sembol),  # type: ignore[arg-type]
                        RedSebebi.BRUT_MARUZIYET,
                        olcumler[sembol],
                        {"tavan": tavan, "bagli": sabit, "istenen": istenen},
                    )
                    del adaylar[sembol]
                elif yeni_h < h:
                    adaylar[sembol] = (yeni_h, (*kisit, "azami_brut_maruziyet"))

        # --- enstrüman sayısı: yalnızca **yeni** girişler elenir, mevcutlara dokunulmaz.
        acik = {s for s, d in mevcut.items() if d > 0.0}
        yeni_girisler = [
            s for s, (h, _) in adaylar.items() if s not in acik and h >= ASGARI_MARUZIYET
        ]
        kalacak = len(acik - {s for s, (h, _) in adaylar.items() if h < ASGARI_MARUZIYET})
        yer = max(0, self.limitler.azami_enstruman - kalacak)
        if len(yeni_girisler) > yer:
            # Sıralama: stratejinin kendi güveni (yüksek önce), eşitlikte sembol adı.
            # Risk motoru hangi fikrin daha iyi olduğunu bilmez ve bilmemeli; bildiği tek
            # şey stratejinin kendi beyanı.
            sirali = sorted(
                yeni_girisler,
                key=lambda s: (-(hedef.sinyal(s).confidence if hedef.sinyal(s) else 0.0), s),
            )
            uygulanan.append("azami_enstruman")
            self.kisit_sayimi["azami_enstruman"] += 1
            for sembol in sirali[yer:]:
                redler[sembol] = self._red_nesnesi(
                    hedef.sinyal(sembol),  # type: ignore[arg-type]
                    RedSebebi.ENSTRUMAN_SAYISI,
                    olcumler[sembol],
                    {"tavan": self.limitler.azami_enstruman, "acik": kalacak},
                )
                del adaylar[sembol]

        return tuple(uygulanan)

    # ------------------------------------------------------------------ boyutlandırma

    def _boyutlandir(self, istenen: float, atr_oran: float) -> tuple[float, tuple[str, ...]]:
        """Hedef maruziyeti iki tavanla sınırlar. Aşağı çeker, **asla yukarı**.

        - `azami_maruziyet`: doğrudan bir tavan.
        - `islem_basina_risk`: aleyhte senaryoda kaybedilebilecek bütçeden türetilen tavan.
          Varsayılan aleyhte hareket `ters_hareket_atr_carpani × ATR/fiyat`; bütçe
          `islem_basina_risk × özkaynak`. Maruziyet tavanı = bütçe / aleyhte hareket.

        İkinci tavanın davranışı dikkate değer: volatilite **arttıkça** daralıyor. Yani
        aynı risk bütçesi sakin piyasada büyük, çalkantılı piyasada küçük pozisyon demek.
        Guard (7. adım) işlemi tamamen kapatan sert bir sınırsa, bu onun sürekli hâli.
        """
        kisitlayan: list[str] = []
        hedef = istenen

        if hedef > self.limitler.azami_maruziyet:
            hedef = self.limitler.azami_maruziyet
            kisitlayan.append("azami_maruziyet")

        ters_hareket = self.limitler.ters_hareket_atr_carpani * atr_oran
        if ters_hareket > 0.0:
            risk_tavani = self.limitler.islem_basina_risk / ters_hareket
            if risk_tavani < hedef:
                hedef = risk_tavani
                kisitlayan.append("islem_basina_risk")

        return hedef, tuple(kisitlayan)

    # ------------------------------------------------------------------ yardımcılar

    def _kalan_bar(self, zaman_ms: int) -> int:
        bitis = self.durum.cooldown_bitis_ms
        if bitis is None or bitis <= zaman_ms:
            return 0
        return -(-(bitis - zaman_ms) // self._bar_ms)  # yukarı yuvarlama

    @staticmethod
    def _strateji_adi(sinyal: Sinyal) -> str:
        """Promotion kaydının anahtarı.

        `Sinyal`de strateji adı **yok** ve olmaması doğru: sinyal bir niyet, bir kimlik
        kartı değil. Bu yüzden eşleme `reason` koduna değil, motora verilen `asamalar`
        sözlüğüne dayanıyor ve anahtar sembol. Faz 6'da tek motor tek strateji çalıştırıyor;
        çoklu strateji geldiğinde motor örneği başına bir strateji olacak (o gün bu metot
        yerine kurucuya bir `strateji` alanı gelir — değişiklik tek satır ve görünür).
        """
        return sinyal.symbol

    def _onay(
        self,
        sinyal: Sinyal,
        hedef: float,
        olcum: PiyasaOlcumu,
        kisitlayan: tuple[str, ...],
    ) -> OnayliNiyet:
        self.onay_sayisi += 1
        for ad in kisitlayan:
            self.kisit_sayimi[ad] = self.kisit_sayimi.get(ad, 0) + 1
        return niyet_mod.onayla(sinyal, hedef, self.limit_kimligi, olcum.bar_ms, kisitlayan)

    def _red_nesnesi(
        self,
        sinyal: Sinyal,
        sebep: RedSebebi,
        olcum: PiyasaOlcumu,
        ayrinti: dict[str, Any],
    ) -> Red:
        """Red kaydını kurar **ve sayar**. Sayım burada çünkü her red bir kez üretiliyor."""
        self.red_sayimi[sebep.value] += 1
        return Red(
            sinyal=sinyal,
            sebep=sebep,
            karar_ms=olcum.bar_ms,
            limit_kimligi=self.limit_kimligi,
            ayrinti=ayrinti,
        )

    # ------------------------------------------------------------------ audit

    def _kaydet(self, karar: Karar, olcum: PiyasaOlcumu) -> None:
        tur = OlayTuru.ONAY if isinstance(karar, OnayliNiyet) else OlayTuru.RED
        govde = karar.sozluk() | {"olcum": olcum.sozluk()}
        self._audit(tur, karar.karar_ms, karar.sinyal.symbol, govde)

    def _audit(
        self, tur: OlayTuru, zaman_ms: int, sembol: str, govde: dict[str, Any]
    ) -> None:
        if self.defter is None:
            return
        self.defter.yaz(
            Olay(
                tur=tur,
                zaman_ms=zaman_ms,
                sembol=sembol,
                govde=govde,
                durum=self.durum.sozluk() | {"mod": self.mod, "limit_kimligi": self.limit_kimligi},
            )
        )

    # ------------------------------------------------------------------ rapor

    def ozet(self) -> dict[str, Any]:
        """Koşu sonunda sonuç kaydına yazılan risk özeti."""
        return {
            "mod": self.mod,
            "limit_kimligi": self.limit_kimligi,
            "limitler": {
                ad: getattr(self.limitler, ad)
                for ad in (
                    "azami_maruziyet",
                    "islem_basina_risk",
                    "ters_hareket_atr_carpani",
                    "gunluk_zarar_limiti",
                    "drawdown_limiti",
                    "ardisik_kayip_limiti",
                    "cooldown_bar",
                    "volatilite_esigi",
                )
            },
            "degerlendirilen": self.degerlendirilen,
            "onay": self.onay_sayisi,
            "red": dict(sorted(self.red_sayimi.items())),
            "kisitlayan": dict(sorted(self.kisit_sayimi.items())),
            "durum": self.durum.sozluk(),
        }


__all__ = [
    "ASGARI_MARUZIYET",
    "KILL_DRAWDOWN",
    "KISIT_ADLARI",
    "MODLAR",
    "PiyasaOlcumu",
    "RiskHatasi",
    "RiskMotoru",
]
