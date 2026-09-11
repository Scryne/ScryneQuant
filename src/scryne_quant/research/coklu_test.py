"""Çoklu test düzeltmesi: 38 çekilişin en iyisi şansa ne kadar borçlu? (K-039'un açık düzeltmesi)

**Kapatmaya çalıştığı boşluk.** K-039 şunu kaydetti: K-019'un yedi kapısı strateji
**başına** çalışıyor ve hiçbiri *"bu kaçıncı denemeydi"* sorusunu sormuyor. Yeterince çok
denenirse, kapılara hiç dokunmadan, birinin şans eseri geçme olasılığı yükselir. Sayım
(`research/hipotez.py`) o kararla geldi; **düzeltme açık bırakıldı** çünkü o gün
ölçülmemişti.

K-039'un düzeltmeyi ertelerken verdiği gerekçe aynen şuydu: *"Bonferroni benzeri bir
düzeltme çekici ama buraya yanlış oturur — stratejiler bağımsız değil (aynı veri, örtüşen
sinyaller, aynı rejim), yani düzeltme çarpanı bilinmiyor. Uydurulan bir çarpan, olmayan bir
kesinlik iddia eder."*

Bu modül çarpanı **uydurmuyor, ölçüyor.** Bağımsızlık varsayımına hiç ihtiyaç duymuyor
çünkü stratejileri modellemiyor — çekilişlerin **kendisini** null bir dünyada yeniden
koşturuyor ve aralarındaki korelasyon ne ise o kalıyor.

## Yöntem: paylaşılan dairesel kaydırma

Her iterasyonda:

1. Defterdeki her çekilişin OOS **sinyal takvimi** alınır (bar indeksi → yön, hedef
   maruziyet). Takvim, o çekilişin kayıtlı parametreleriyle gerçek stratejiyi koşturarak
   çıkarılıyor — uydurma değil, kaydın yeniden üretimi (K-009).
2. Takvim `k` bar **dairesel** kaydırılır. Korunanlar: sinyal sayısı, sinyaller arası
   aralık deseni, hedef maruziyet dağılımı, yani stratejinin bütün işlem yapısı. Yok
   edilen tek şey fiyatla **hizalanma** — yani edge'in ta kendisi.
3. Kaydırılmış takvim **gerçek backtest motorundan** geçirilir. Yaklaşım yok: fill bir
   sonraki barın açılışında (K-004), maliyet aynı model, Sharpe aynı formül. Null sayı ile
   gerçek sayı aynı kod yolundan çıkıyor, dolayısıyla karşılaştırılabilirler.
4. O iterasyonun **maksimum** OOS Sharpe'ı kaydedilir.

`deneme` iterasyon sonunda elde kalan şey, *"38 çekiliş yapsaydım ve hiçbirinin edge'i
olmasaydı, en iyisi ne kadar iyi görünürdü"* sorusunun ampirik dağılımı.

## Kaydırma neden bütün çekilişlerde **aynı**

İterasyon başına tek bir `k` seçiliyor ve 38'ine birden uygulanıyor. Bağımsız kaydırma
kolay olurdu ve **yanlış** olurdu: stratejiler gerçekte birbiriyle ilişkili (aynı veri,
örtüşen sinyaller, aynı rejim) ve bağımsız kaydırma o ilişkiyi koparırdı. Korelasyonu
koparmak maksimumun dağılımını **genişletir** — yani düzeltmeyi olduğundan büyük gösterir
ve tam olarak K-039'un reddettiği şeyi, uydurulmuş bir çarpanı, arka kapıdan geri getirir.

Paylaşılan kaydırma altında ilişkili stratejiler null dünyada da ilişkili kalıyor. Ölçülen
çarpan, verinin kendi korelasyon yapısından geliyor.

## Ne ölçüyor, ne ölçmüyor

**Ölçtüğü:** "OOS sonucuna 38 kez baktık" sapması. Kapıyı geçecek bir sayının, hiç edge
olmadan bile kaç çekilişte bir ortaya çıkacağı.

**Ölçmediği:** her çekilişin **içindeki** parametre arama sapması. Onu IS/OOS bölmesi
taşıyor — parametre in-sample'da seçiliyor, ölçüm out-of-sample'da yapılıyor. Bu modül o
bölmenin üstüne binen ikinci katmanı, yani bölmenin kendisine 38 kez bakılmış olmasını
ölçüyor. İkisi farklı sapmalar ve bu modül yalnızca ikincisini kapatıyor.

## Maksimum neden **uygun** çekilişler üzerinden alınıyor

İlk yazımda maksimum 31 çekilişin hepsi üzerinden alınıyordu ve null dağılımı absürt
çıktı: rastgele bir stratejiye p99'da 4,2 Sharpe. Ölçüm sebebi gösterdi — uç değerlerin
tamamı **az işlemli** çekilişlerden geliyordu (`ema_kesisim` 4h, 14 işlem → null p99 3,03;
`cok_faktor` 1h/plato, 98 işlem → null p99 −0,12). Bu bir kusur değil, gerçek: 14 işlemle
ölçülen bir Sharpe'ın örnekleme varyansı devasadır.

**Ama o çekiliş promotion'a zaten aday olamaz.** K-019 yedi kapıyı **birlikte** istiyor ve
`asgari_islem ≥ 30` tam olarak bu gürültüyü eliyor. Şansa 3,03 üreten 14 işlemlik bir
çekilişi maksimuma katmak, hiçbir zaman geçemeyecek bir kapıdan geçme olasılığını
hesaplamak olurdu — düzeltmeyi kendi kendine şişiren bir hata.

Bu yüzden maksimum, o iterasyonda **uygunluk yordamını** geçen çekilişler üzerinden
alınıyor. Yordam çağıran tarafından veriliyor; varsayılan yok, çünkü hangi kapının
eleyeceği bu modülün değil K-019'un bilgisi.

**Bunun da ölçmediği şey yazılı:** uygunluk yalnızca ucuz hesaplanabilen kapılarla
sınırlı. Walk-forward ve stres kapıları her iterasyonda yeniden ölçülemeyecek kadar pahalı
(tek bir tam değerlendirme dakikalar sürüyor). Yani bu null, gerçek promotion kapısından
**daha gevşek** bir uygunluk kullanıyor ve dolayısıyla düzeltmeyi olduğundan **büyük**
gösteriyor. Yön bilinçli: belirsizlikte kötü yöne yuvarla (K-007).

**Ölçmediği üçüncü şey:** dairesel kaydırmanın kendisi bir null **modeli**dir. Takvimi
kaydırmak, sinyal zamanlamasının fiyattan bağımsız olduğu bir dünya kuruyor. Stratejinin
sinyal **yoğunluğu** rejime bağlıysa (örn. yalnızca oynak dönemlerde sinyal üretiyorsa),
kaydırma o bağı da koparır ve null'ı bir miktar iyimser yapabilir. Bu bir kusur değil ama
bir varsayım, ve yazılı olmak zorunda.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np

from scryne_quant.backtest.sonuc import Sonuc
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.tarama import kosu
from scryne_quant.strategy.baglam import Baglam
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji

#: Raporlanan null persentilleri. p95 ve p99 ayrı ayrı veriliyor çünkü seçilecek
#: yanlış-pozitif oranı bir **iştah** kararı (K-033), ölçüm değil — modül sayıyı seçmiyor,
#: seçeneği sunuyor.
PERSENTILLER: Final[tuple[int, ...]] = (50, 75, 90, 95, 99)


class CokluTestHatasi(ValueError):
    """Çoklu test ölçümünün girdi sözleşmesi ihlal edildi."""


# --------------------------------------------------------------------- aletler


class KayitliStrateji(Strateji):
    """Bir stratejiyi sarıp ürettiği sinyalleri **takvime** yazar. Ölçüm aleti.

    Motor sinyalleri dışarı vermiyor ve vermemeli — `Sonuc` bir equity eğrisi ve işlem
    defteri taşıyor, karar dizisi değil. Takvimi çıkarmanın tek temiz yolu stratejinin
    kendisini sarmak: iç stratejinin `on_bar`ı aynen çağrılıyor, dönen sinyal aynen geri
    veriliyor, yalnızca kayda geçiyor. Yani sarmalayıcı davranışı **değiştirmiyor** ve bu
    testle sabitlendi (`test_coklu_test.py`).
    """

    ad = "kayitli"

    def __init__(self, ic: Strateji) -> None:
        self._ic = ic
        self.takvim: dict[int, tuple[str, float]] = {}
        super().__init__(ic=ic.ad, parametreler=ic.sozluk().get("parametreler", {}))

    def ozellikler(self) -> Sequence[Any]:
        return self._ic.ozellikler()

    def dogrula(self) -> None:
        self._ic.dogrula()

    def hazirla(self) -> None:
        self._ic.hazirla()
        self.takvim = {}

    def isinma_bar(self) -> int:
        return self._ic.isinma_bar()

    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        sinyal = self._ic.on_bar(ctx)
        if sinyal is not None:
            self.takvim[ctx.uzunluk - 1] = (str(sinyal.side), sinyal.target_exposure)
        return sinyal


class BetikStrateji(Strateji):
    """Sabit bir takvimden sinyal üreten ölçüm aleti — **hipotez değil**.

    `KUTUPHANE`ye **bilerek kaydedilmedi.** Kaydedilseydi `sq lab` onu koşturulabilir bir
    strateji olarak görürdü ve bir ölçüm aleti, hipotez defterine yazılabilir bir çekiliş
    hâline gelirdi (K-039). Bu sınıf bir strateji değil; bir stratejinin kaydının
    oynatıcısı.

    Isınma barı dışarıdan veriliyor: takvim zaten ısınmış bir stratejiden çıkarıldı, ve
    motorun aynı pencereyi ölçmesi için ısınmanın da aynı olması gerekiyor.
    """

    ad = "betik"

    def __init__(self, takvim: Mapping[int, tuple[str, float]], *, isinma: int = 0) -> None:
        self._takvim = dict(takvim)
        self._isinma = int(isinma)
        super().__init__(sinyal=len(self._takvim), isinma=self._isinma)

    def ozellikler(self) -> Sequence[Any]:
        return ()

    def isinma_bar(self) -> int:
        """Taban sınıfta bu bir **metot**, property değil — sözleşme aynen korunuyor.

        Ölçüme girmiyor: OOS penceresi kayıttan geldiği için motor ısınmayı yeniden
        hesaplamıyor. Yine de doğru değeri taşıyor; sarmalayıcının sözleşmeyi
        değiştirmemesi, "alet ölçtüğü şeye dokunmaz" kuralının bu dosyadaki hâli.
        """
        return self._isinma

    def on_bar(self, ctx: Baglam) -> Sinyal | None:
        girdi = self._takvim.get(ctx.uzunluk - 1)
        if girdi is None:
            return None
        yon, hedef = girdi
        return Sinyal(
            symbol=ctx.sembol,
            side=Yon(yon),
            target_exposure=hedef,
            confidence=1.0,
            reason="COKLU_TEST_NULL",
            timestamp=ctx.zaman,
        )


def kaydir(
    takvim: Mapping[int, tuple[str, float]], k: int, uzunluk: int
) -> dict[int, tuple[str, float]]:
    """Takvimi `k` bar **dairesel** kaydırır.

    Dairesel olması bir tercih değil, zorunluluk: düz kaydırma pencerenin sonundaki
    sinyalleri düşürürdü ve null, gerçekten daha az işlem yapan bir strateji olurdu. Daha
    az işlem daha düşük Sharpe değil, daha **gürültülü** Sharpe demek — yani null'ı
    olduğundan geniş gösterirdi.

    **`uzunluk` takvimin tanım kümesidir, ölçüm penceresi değil.** Ayrım bir hatayla
    öğrenildi: takvim indeksleri motorun gördüğü dilimin tamamı üzerinde (ısınma dahil)
    üretiliyor, ölçüm ise dilimin yalnızca son kısmında yapılıyor. Modül olarak ölçüm
    uzunluğu verilince taşan indeksler sarmalanıp **birbirinin üstüne yazdı** — sinyaller
    sessizce kayboldu, işlem sayısı düştü, Sharpe gürültüsü patladı ve null dağılımı
    rastgele bir stratejiye p99'da 4,1 Sharpe atfetti. Sayı absürt olduğu için fark
    edildi; biraz daha makul olsaydı fark edilmezdi.

    Bu yüzden sığmayan indeks artık **hata**. Sessizce mod almak, aynı hatanın bir
    dahaki sefere sessiz kalması demekti.
    """
    if uzunluk <= 0:
        raise CokluTestHatasi(f"takvim uzunluğu pozitif olmalı: {uzunluk}")
    tasan = [i for i in takvim if not 0 <= i < uzunluk]
    if tasan:
        raise CokluTestHatasi(
            f"takvimde tanım kümesi dışında {len(tasan)} indeks var "
            f"(uzunluk={uzunluk}, örn. {sorted(tasan)[:5]}). Dairesel kaydırma bunları "
            "üst üste yazar ve sinyalleri sessizce düşürür."
        )
    kaydirilmis = {(i + k) % uzunluk: v for i, v in takvim.items()}
    if len(kaydirilmis) != len(takvim):
        raise CokluTestHatasi(
            f"kaydırma sinyal düşürdü: {len(takvim)} → {len(kaydirilmis)}"
        )
    return kaydirilmis


# --------------------------------------------------------------------- çekiliş


@dataclass(frozen=True, slots=True)
class Cekilis:
    """Defterdeki bir hipotezin yeniden üretilmiş, oynatılabilir hâli."""

    kimlik: str
    strateji: str
    timeframe: str
    secim: str
    secilen: dict[str, Any]
    veri_sha256: str
    gercek_sharpe: float
    isinma_bar: int
    oos_bar: int
    """Ölçümün yapıldığı bar sayısı. Raporlama için; kaydırmanın modülü **bu değil**."""

    takvim_bar: int
    """Takvimin tanım kümesi: motorun gördüğü dilimin tamamı (ısınma dahil).

    `oos_bar`dan ayrı tutulması bir hata düzeltmesi — ayrıntı `kaydir`in gövdesinde."""

    takvim: dict[int, tuple[str, float]] = field(repr=False)

    @property
    def sinyal_sayisi(self) -> int:
        return len(self.takvim)

    def sozluk(self) -> dict[str, Any]:
        return {
            "kimlik": self.kimlik,
            "strateji": self.strateji,
            "timeframe": self.timeframe,
            "secim": self.secim,
            "secilen": self.secilen,
            "veri_sha256": self.veri_sha256,
            "gercek_sharpe": self.gercek_sharpe,
            "sinyal_sayisi": self.sinyal_sayisi,
            "oos_bar": self.oos_bar,
            "takvim_bar": self.takvim_bar,
        }


def takvim_cikar(
    strateji: Strateji,
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    pencere: Pencere,
    *,
    baslangic_sermaye: float = 10_000.0,
    veri_sha256: str = "",
) -> tuple[dict[int, tuple[str, float]], Sonuc]:
    """Stratejiyi OOS penceresinde koşturur; sinyal takvimini ve sonucu birlikte döner.

    Sonucun da dönmesi bilinçli: takvimi çıkaran koşu ile gerçek Sharpe'ı veren koşu
    **aynı** koşu olmalı. İki ayrı koşu olsaydı, ikisinin aynı sayıyı verdiği bir
    varsayım olurdu.
    """
    kayitli = KayitliStrateji(strateji)
    sonuc = kosu(
        kayitli,
        maliyet,
        sembol,
        timeframe,
        bar_dizileri,
        pencere,
        baslangic_sermaye=baslangic_sermaye,
        veri_sha256=veri_sha256,
    )
    return dict(kayitli.takvim), sonuc


# ------------------------------------------------------------------------ null


@dataclass(frozen=True, slots=True)
class NullSonucu:
    """Paylaşılan dairesel kaydırma altında "en iyi çekiliş"in null dağılımı."""

    cekilis_sayisi: int
    deneme: int
    seed: int
    gercek_en_iyi: float
    gercek_en_iyi_strateji: str
    azami_dagilimi: dict[str, float]
    """Her iterasyonun **uygun** çekilişler arasındaki maksimum OOS Sharpe'ı."""

    ham_azami_dagilimi: dict[str, float]
    """Uygunluk süzgeci **olmadan** maksimum. Yalnızca karşılaştırma için raporlanıyor:
    ikisinin farkı, süzgecin ne kadar gürültü elediğini görünür kılıyor."""

    uygun_oran: float
    """İterasyon başına ortalama kaç çekilişin uygun çıktığı (0-1). Düşükse düzeltme az
    sayıda çekilişe dayanıyor demektir ve bu okunmadan eşik seçilmemeli."""

    p_degeri: float
    """Null'da gerçek en iyiden **daha iyi** çıkan iterasyonların oranı.

    Doğrudan okunabilir: 0,40 ise, hiçbir stratejinin edge'i olmasa bile 38 çekilişin
    en iyisi vakaların %40'ında bu kadar iyi görünürdü.
    """

    tekil_dagilim: dict[str, dict[str, float]] = field(repr=False, default_factory=dict)
    """Çekiliş başına null Sharpe persentilleri. Maksimumun hangi çekilişten geldiğini
    değil, her çekilişin kendi gürültü tabanını gösterir."""

    azami: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    """Ham maksimum örneği. Eşik türetmek için saklanıyor: persentil tablosu yuvarlanmış
    bir özet, eşik ise tam sayıdan hesaplanmalı."""

    def duzeltilmis_esik(self, yanlis_pozitif: float) -> float:
        """Verilen yanlış-pozitif oranına karşılık gelen düzeltilmiş OOS Sharpe eşiği.

        `yanlis_pozitif=0.05` → null dağılımının p95'i. Yani *"edge yokken bu eşiği
        geçme olasılığı %5"*. Oranın kendisi bir **iştah** kararı (K-033) ve bu modülün
        işi değil; modül yalnızca oranı sayıya çeviriyor.
        """
        if not 0.0 < yanlis_pozitif < 1.0:
            raise CokluTestHatasi(f"yanlış-pozitif oranı (0,1) aralığında olmalı: {yanlis_pozitif}")
        if self.azami.size == 0:
            raise CokluTestHatasi("null örneği boş: eşik türetilemez")
        return float(np.percentile(self.azami, 100.0 * (1.0 - yanlis_pozitif)))

    def esik_guven_araligi(
        self, yanlis_pozitif: float, *, deneme: int = 2_000, seed: int = 0
    ) -> tuple[float, float]:
        """Düzeltilmiş eşiğin %90 bootstrap güven aralığı.

        **Neden zorunlu.** Eşik bir persentil ve persentil bir **tahmin**: 200
        iterasyonda p95 = 0,854 çıkan dağılım, 2.000 iterasyonda 1,021 verdi. Aradaki
        fark gürültüydü, ama sayıyı tek başına okuyan biri onu kesinlik sanardı.
        Promotion eşiği olacak bir sayının hata payı, sayının kendisi kadar kayda
        geçmeli — bu projede "neredeyse doğru", yanlıştan tehlikelidir.

        Aralık genişse çare eşiği yuvarlamak değil, **iterasyonu artırmaktır**.
        """
        if self.azami.size == 0:
            raise CokluTestHatasi("null örneği boş: güven aralığı hesaplanamaz")
        rng = np.random.default_rng(seed)
        yuzde = 100.0 * (1.0 - yanlis_pozitif)
        ornekler = np.array(
            [
                np.percentile(rng.choice(self.azami, self.azami.size, replace=True), yuzde)
                for _ in range(deneme)
            ]
        )
        return float(np.percentile(ornekler, 5)), float(np.percentile(ornekler, 95))

    def sozluk(self) -> dict[str, Any]:
        return {
            "cekilis_sayisi": self.cekilis_sayisi,
            "deneme": self.deneme,
            "seed": self.seed,
            "gercek_en_iyi": self.gercek_en_iyi,
            "gercek_en_iyi_strateji": self.gercek_en_iyi_strateji,
            "azami_dagilimi": self.azami_dagilimi,
            "ham_azami_dagilimi": self.ham_azami_dagilimi,
            "uygun_oran": self.uygun_oran,
            "p_degeri": self.p_degeri,
            "tekil_dagilim": self.tekil_dagilim,
            # Ham örnek kayda giriyor: eşiğin güven aralığı ya da farklı bir
            # yanlış-pozitif oranı, 30 dakikalık koşuyu tekrarlamadan türetilebilsin.
            # Persentil tablosu bir özet; özetten aralık çıkmaz.
            "azami_ornegi": [float(x) for x in self.azami],
        }


def null_dagilimi(
    cekilisler: Sequence[Cekilis],
    kosturucu: Callable[[Cekilis, dict[int, tuple[str, float]]], tuple[float, bool]],
    *,
    deneme: int = 1_000,
    seed: int = 0,
) -> NullSonucu:
    """Paylaşılan dairesel kaydırma ile "en iyi çekiliş"in null dağılımını çıkarır.

    `kosturucu(cekilis, takvim) -> (oos_sharpe, uygun_mu)` döndürmeli. Çağıranın vermesi
    bilinçli: bu modülün veri deposu, Parquet dosyası veya `config/` bilgisi yok
    (K-003'ün kalıbı) — hangi barlarla koşturulacağını bilen taraf çağıran. `uygun_mu`
    da çağırandan geliyor çünkü hangi kapının eleyeceği K-019'un bilgisi, bu modülün
    değil.

    **Hiçbir çekilişin uygun çıkmadığı iterasyon**da maksimum `-inf` değil, o turun
    ham maksimumu olarak değil, **atlanmış** sayılıyor: uygun aday üretmeyen bir tur,
    "kapıyı geçen olmadı" turudur ve dağılıma sıfır katkı verir. Onu ham maksimumla
    doldurmak, elenmiş çekilişi arka kapıdan geri sokmak olurdu.

    **Kaydırma sıfır seçilmez.** `k = 0` gerçek dizilimin ta kendisidir; null örneğine
    gerçek sonucu koymak, dağılımı ölçmeye çalıştığı şeyle kirletmek olurdu.
    """
    if not cekilisler:
        raise CokluTestHatasi("en az bir çekiliş gerekir")
    if deneme < 1:
        raise CokluTestHatasi(f"deneme sayısı pozitif olmalı: {deneme}")

    rng = np.random.default_rng(seed)
    azami: list[float] = []
    ham_azami = np.empty(deneme, dtype=np.float64)
    uygun_sayilari: list[int] = []
    tekil: dict[str, list[float]] = {c.kimlik: [] for c in cekilisler}

    for d in range(deneme):
        # **İterasyon başına tek oran.** Modül başlığındaki gerekçe: bağımsız kaydırma
        # stratejiler arası korelasyonu koparır, maksimumun dağılımını genişletir ve
        # düzeltmeyi olduğundan büyük gösterir. Oran (bar sayısı değil) paylaşılıyor
        # çünkü çekilişler farklı timeframe'lerden geliyor; 1h'te 100 bar ile 4h'te 100
        # bar aynı kaydırma değil. Oran, hepsini aynı **zaman** kadar kaydırıyor.
        oran = float(rng.random())
        tur: list[float] = []
        uygunlar: list[float] = []
        for c in cekilisler:
            k = 1 + int(oran * (c.takvim_bar - 2))
            sharpe, uygun = kosturucu(c, kaydir(c.takvim, k, c.takvim_bar))
            tur.append(sharpe)
            if uygun:
                uygunlar.append(sharpe)
            tekil[c.kimlik].append(sharpe)
        ham_azami[d] = max(tur)
        uygun_sayilari.append(len(uygunlar))
        if uygunlar:
            azami.append(max(uygunlar))

    if not azami:
        raise CokluTestHatasi(
            "hiçbir iterasyonda uygun çekiliş çıkmadı: uygunluk yordamı her şeyi eliyor, "
            "eşik türetilemez"
        )
    azami_dizi = np.array(azami, dtype=np.float64)
    gercek = max(cekilisler, key=lambda c: c.gercek_sharpe)
    return NullSonucu(
        cekilis_sayisi=len(cekilisler),
        deneme=deneme,
        seed=seed,
        gercek_en_iyi=gercek.gercek_sharpe,
        gercek_en_iyi_strateji=gercek.strateji,
        azami_dagilimi={
            f"p{p:02d}": float(np.percentile(azami_dizi, p)) for p in PERSENTILLER
        },
        ham_azami_dagilimi={
            f"p{p:02d}": float(np.percentile(ham_azami, p)) for p in PERSENTILLER
        },
        uygun_oran=float(np.mean(uygun_sayilari) / len(cekilisler)),
        p_degeri=float((azami_dizi >= gercek.gercek_sharpe).mean()),
        tekil_dagilim={
            k: {f"p{p:02d}": float(np.percentile(v, p)) for p in PERSENTILLER}
            for k, v in tekil.items()
        },
        azami=azami_dizi,
    )


# ------------------------------------------------------------- deflated sharpe


def beklenen_azami_sharpe(deneme_sayisi: int, sharpe_sapmasi: float) -> float:
    """Bağımsız olmayan denemelerde beklenen **en yüksek** Sharpe. (Bailey & López de Prado)

    K-039 bu yöntemi adıyla anıp *"varsayımları tartışmalı ve bu veri üzerinde
    ölçülmedi"* demişti. Burada çapraz kontrol olarak hesaplanıyor — karar verici değil.

    Zarafeti şurada: denemelerin **gözlenen Sharpe dağılımının** standart sapmasını
    kullanıyor, bağımsızlık varsayıp bir çarpan uydurmuyor. İlişkili denemeler birbirine
    yakın Sharpe üretir, sapma küçülür, beklenen maksimum da küçülür — yani korelasyon
    veriden kendiliğinden geliyor.

    Yine de bir **model**: denemelerin Sharpe'larının normal dağıldığını varsayıyor.
    Kaydırma null'ı bu varsayımı yapmıyor. İkisi uyuşursa güven; uyuşmazsa uyuşmazlık
    kaydedilir, biri seçilmez.
    """
    if deneme_sayisi < 2:
        raise CokluTestHatasi(f"en az 2 deneme gerekir: {deneme_sayisi}")
    if sharpe_sapmasi <= 0.0:
        raise CokluTestHatasi(f"Sharpe sapması pozitif olmalı: {sharpe_sapmasi}")

    from statistics import NormalDist

    nd = NormalDist()
    gama = 0.5772156649015329  # Euler-Mascheroni
    n = float(deneme_sayisi)
    # Gumbel yaklaşımı: E[max] ≈ σ·[(1−γ)·z(1−1/N) + γ·z(1−1/(N·e))]
    ilk = nd.inv_cdf(1.0 - 1.0 / n)
    ikinci = nd.inv_cdf(1.0 - 1.0 / (n * math.e))
    return sharpe_sapmasi * ((1.0 - gama) * ilk + gama * ikinci)


__all__ = [
    "PERSENTILLER",
    "BetikStrateji",
    "Cekilis",
    "CokluTestHatasi",
    "KayitliStrateji",
    "NullSonucu",
    "beklenen_azami_sharpe",
    "kaydir",
    "null_dagilimi",
    "takvim_cikar",
]
