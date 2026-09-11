"""Toparlanma: süreç öldükten sonra durumun **yeniden üretilmesi**. (Faz 6 bitti kriteri)

Roadmap: *"Süreç öldürülüp yeniden başlatıldığında pozisyon ve emir state'i doğru
toparlanıyor."* Bu modül o cümlenin uygulaması — ve cümledeki "doğru" kelimesini
ölçülebilir kılan şey burada:

**Toparlanma bir geri yükleme değil, bir yeniden üretimdir.** Diskten okunan her sayı
bağımsız bir kaynaktan **yeniden hesaplanıp** karşılaştırılıyor:

| Diskten okunan | Yeniden üretilen kaynak | Uyuşmazsa |
| --- | --- | --- |
| Portföy (nakit, miktar, ort. maliyet) | `fill` defterinin baştan uygulanması | ayrışma |
| Bekleyen kararın özeti | Strateji + risk motorunun bardan yeniden karar üretmesi | ayrışma |
| Risk durumu | — (tek kaynak; türetilecek bağımsız bir kaynağı yok) | — |

("ayrışma" = `ToparlanmaAyrismasi`; koşu durur.)

İlk satır sessiz bozulmayı yakalar: kontrol noktası ile fill defteri ayrışmışsa portföy
"makul görünen" ama yanlış bir sayıdır ve o yanlışlık bir daha hiç fark edilmez. İkinci
satır K-032'nin sonucu: mühürlü bir onay serileştirilemez, dolayısıyla onay yeniden
türetilmek zorunda — ve madem yeniden türetiliyor, türetilenin kayıtlıyla aynı olması bir
determinizm testidir (K-009'un canlıdaki hâli).

**Üçüncü satır bilerek boş.** Risk durumunun (zirve özkaynak, gün başı özkaynak, ardışık
kayıp, cooldown, SAFE_MODE) bağımsız bir ikinci kaynağı yok; equity eğrisinin tamamını
saklamadan yeniden hesaplanamaz. Bunu "doğrulandı" diye yazmak, doğrulanmamış bir şeyi
doğrulanmış göstermek olurdu. Korunması yazım tarafında: `durum_yaz` atomik ve
`synchronous=FULL` (K-034).

**Strateji durumu neden yeniden oynatılıyor:** strateji barlar arasında kendi alanlarında
durum tutabilir (`Strategy.hazirla` sözleşmesi). O durumun serileştirilmiş bir hâli yok ve
olmamalı — her strateji yazarına bir `sozluk()`/`yukle()` çifti yazdırmak, unutulduğunda
sessizce yanlış çalışan bir sistem üretirdi. Bunun yerine durum penceredeki barlar üzerinde
`on_bar` yeniden çağrılarak yeniden kuruluyor: kaynak zaten "yalnızca geçmişten türer"
(K-002), dolayısıyla aynı geçmiş aynı durumu verir.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from scryne_quant.backtest.fill import IslemYonu
from scryne_quant.backtest.metrikler import Islem
from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.live.akis import Bar
from scryne_quant.live.depo import KontrolNoktasi, KosuOlayi
from scryne_quant.live.motor import PaperMotoru, ToparlanmaAyrismasi
from scryne_quant.portfolio.durum import Portfoy
from scryne_quant.risk.durum import RiskDurumu
from scryne_quant.strategy.kosu import gorunum_kur

#: Portföy karşılaştırmasının bağıl toleransı. Mutlak değil bağıl: 10.000 USDT'lik bir
#: portföyde anlamlı olan eşik 1.000.000 USDT'likte gürültüdür. Kayan nokta toplamanın
#: sırası fill tekrar oynatılırken birebir aynı olduğu için pratikte fark sıfır çıkıyor;
#: tolerans yine de var çünkü "tam eşitlik" beklentisi ilk float değişikliğinde koşuyu
#: durdurmanın en gereksiz yolu olurdu.
TOLERANS: Final = 1e-9


@dataclass(frozen=True, slots=True)
class ToparlanmaSonucu:
    """Toparlanmanın ne bulduğu. `temiz_baslangic` dışındaki her alan bir kanıttır."""

    temiz_baslangic: bool
    son_bar_ms: int | None
    pencere_bar: int
    fill_sayisi: int
    portfoy_dogrulandi: bool
    bekleyen_dogrulandi: bool | None
    """`None` = karşılaştırılacak kayıtlı karar yoktu (süreç karar öncesinde ölmüş)."""

    def sozluk(self) -> dict[str, Any]:
        return {
            "temiz_baslangic": self.temiz_baslangic,
            "son_bar_ms": self.son_bar_ms,
            "pencere_bar": self.pencere_bar,
            "fill_sayisi": self.fill_sayisi,
            "portfoy_dogrulandi": self.portfoy_dogrulandi,
            "bekleyen_dogrulandi": self.bekleyen_dogrulandi,
        }


def toparlan(motor: PaperMotoru, barlar: Sequence[Bar]) -> ToparlanmaSonucu:
    """Motoru kayıtlı durumdan toparlar. Uyuşmazlıkta `ToparlanmaAyrismasi` fırlatır.

    `barlar` toparlanma penceresi: depodan ve/veya REST'ten getirilmiş, `son_bar_ms`i
    **içeren** ve stratejinin ısınmasına yetecek kadar geriye giden barlar. Bunları
    getirmek çağıranın işi; bu modülün borsa bilgisi yok (K-003'ün kalıbı).
    """
    kontrol = motor.depo.kontrol_noktasi_oku()
    motor.pencere.doldur(barlar)

    if kontrol is None:
        motor.depo.olay_yaz(
            KosuOlayi.BASLADI,
            ayrinti={"temiz_baslangic": True, "pencere_bar": len(motor.pencere)},
        )
        return ToparlanmaSonucu(
            temiz_baslangic=True,
            son_bar_ms=None,
            pencere_bar=len(motor.pencere),
            fill_sayisi=0,
            portfoy_dogrulandi=True,
            bekleyen_dogrulandi=None,
        )

    filller = _filller(motor)
    portfoy = _portfoy_yeniden_uret(motor.kimlik.baslangic_sermaye, filller)
    _portfoy_karsilastir(motor, kontrol, portfoy)

    motor.portfoy = portfoy
    motor.risk.durum = RiskDurumu.yukle(kontrol.risk)
    motor.acik = None if kontrol.acik_islem is None else Islem(**kontrol.acik_islem)
    motor.islemler = [] if motor.acik is None else [motor.acik]
    motor._son_bar_ms = kontrol.son_bar_ms

    bekleyen_dogrulandi = _karari_yeniden_uret(motor, kontrol, filller)

    motor.depo.olay_yaz(
        KosuOlayi.TOPARLANDI,
        bar_ms=kontrol.son_bar_ms,
        ayrinti={
            "yazim": kontrol.yazim,
            "fill_sayisi": len(filller),
            "pencere_bar": len(motor.pencere),
            "bekleyen_dogrulandi": bekleyen_dogrulandi,
        },
    )
    return ToparlanmaSonucu(
        temiz_baslangic=False,
        son_bar_ms=kontrol.son_bar_ms,
        pencere_bar=len(motor.pencere),
        fill_sayisi=len(filller),
        portfoy_dogrulandi=True,
        bekleyen_dogrulandi=bekleyen_dogrulandi,
    )


# ---------------------------------------------------------------------- portföy


def _filller(motor: PaperMotoru) -> list[dict[str, Any]]:
    """Fill defteri, **yazıldığı sırada**. `filller()` en yeniden eskiye döndürüyor."""
    return sorted(motor.depo.filller(), key=lambda f: int(f["id"]))


def _portfoy_yeniden_uret(baslangic: float, filller: Sequence[dict[str, Any]]) -> Portfoy:
    """Fill defterini baştan uygulayarak portföyü yeniden üretir.

    `Portfoy.al`/`sat` kullanılıyor, kontrol noktasındaki sayılar değil: amaç kayıtlı
    portföyü *okumak* değil, ondan **bağımsız** bir yoldan aynı sayıya varmak. Aynı
    fonksiyonları kullanması sorun değil — doğrulanan şey aritmetik değil, iki kaydın
    (kontrol noktası ve fill defteri) birbiriyle tutarlılığı.
    """
    p = Portfoy(nakit=baslangic)
    for f in filller:
        miktar = float(f["miktar"])
        fiyat = float(f["fiyat"])
        komisyon = float(f["komisyon"])
        if str(f["yon"]) == str(IslemYonu.AL):
            p = p.al(miktar, fiyat, komisyon, int(f["zaman_ms"]))
        else:
            p, _ = p.sat(miktar, fiyat, komisyon)
    return p


def _portfoy_karsilastir(
    motor: PaperMotoru, kontrol: KontrolNoktasi, uretilen: Portfoy
) -> None:
    kayitli = kontrol.portfoy
    farklar = {
        ad: (float(kayitli[ad]), deger)
        for ad, deger in (
            ("nakit", uretilen.nakit),
            ("miktar", uretilen.miktar),
            ("ortalama_maliyet", uretilen.ortalama_maliyet),
        )
        if abs(float(kayitli[ad]) - deger) > TOLERANS * max(abs(float(kayitli[ad])), 1.0)
    }
    if not farklar:
        return
    ayrinti = {"alan": {a: {"kayitli": k, "uretilen": u} for a, (k, u) in farklar.items()}}
    motor.depo.olay_yaz(
        KosuOlayi.TOPARLANMA_AYRISMASI, bar_ms=kontrol.son_bar_ms, ayrinti=ayrinti
    )
    motor._durdu = True
    raise ToparlanmaAyrismasi(
        "kontrol noktası ile fill defteri ayrıştı; portföy yeniden üretilemedi: "
        f"{ayrinti['alan']}. Koşu durduruldu — bu noktadan sonra her sayı tahmindir."
    )


# ------------------------------------------------------------------------ karar


def _karari_yeniden_uret(
    motor: PaperMotoru, kontrol: KontrolNoktasi, filller: Sequence[dict[str, Any]]
) -> bool | None:
    """Son barın kararını yeniden üretir ve kayıtlı özetle karşılaştırır.

    Yeniden üretim `PaperMotoru._karar_ver`i çağırıyor — yani canlı döngünün kullandığı
    **aynı** kod yolu. Ayrı bir "toparlanma kararı" fonksiyonu yazmak, karşılaştırmayı
    anlamsız kılardı: iki farklı kod yolunun aynı sonucu vermesi kanıtlanan şey olmazdı.
    """
    if kontrol.son_bar_ms is None:
        return None

    diziler = motor.pencere.diziler()
    zamanlar = [int(t) for t in diziler["open_time"]]
    if kontrol.son_bar_ms not in zamanlar:
        motor._durdu = True
        motor.depo.olay_yaz(
            KosuOlayi.TOPARLANMA_AYRISMASI,
            bar_ms=kontrol.son_bar_ms,
            ayrinti={"sebep": "son_bar_pencerede_yok", "pencere_bar": len(zamanlar)},
        )
        raise ToparlanmaAyrismasi(
            f"kayıtlı son bar {kontrol.son_bar_ms} toparlanma penceresinde yok; "
            "pencere bu barı içermeli"
        )

    i = zamanlar.index(kontrol.son_bar_ms)
    son_bar = list(motor.pencere)[i]
    bar_ok = str(diziler["quality_status"][i]) == str(KaliteDurumu.OK)

    # Strateji durumunu yeniden kur: `hazirla()` + penceredeki her bar için `on_bar`.
    # Portföy görünümü her barda o barın **o anki** hâlinden veriliyor; sabit bir portföy
    # vermek, pozisyona göre dallanan bir stratejiyi yanlış oynatırdı.
    motor.strateji.hazirla()
    _oynat(motor, diziler, zamanlar, filller, son_indeks=i)

    # Kararı canlı yoldan yeniden ver. Bu çağrı audit'e ikinci bir satır yazar ve bu
    # bilinçli: karar gerçekten yeniden verildi, ve `TOPARLANDI` olayı bunun sebebini
    # açıklıyor. Sessizce yazmayan bir yol açmak, risk kararlarını audit'ten gizlemenin
    # kapısını aralardı (K-032).
    motor._bekleyen = None
    # Bayatlık kayıttan okunuyor, yeniden ölçülmüyor: toparlanan süreç henüz hiç nabız
    # almadığı için `bayat_mi` her zaman `True` döner ve karar bayat yoldan yeniden
    # üretilirdi — yani süreç kendi kendine ayrışma ilan ederdi.
    motor._karar_ver(son_bar, diziler, i, bar_ok, kontrol.bayat)
    uretilen = None if motor._bekleyen is None else motor._bekleyen.ozet()

    if kontrol.bekleyen is None:
        # Süreç karar adımından önce ölmüş: karşılaştırılacak bir şey yok. Üretilen karar
        # geçerli ve bekleyen olarak kalıyor.
        return None

    if uretilen != kontrol.bekleyen:
        motor._durdu = True
        motor.depo.olay_yaz(
            KosuOlayi.TOPARLANMA_AYRISMASI,
            bar_ms=kontrol.son_bar_ms,
            ayrinti={"kayitli": kontrol.bekleyen, "uretilen": uretilen},
        )
        raise ToparlanmaAyrismasi(
            "yeniden üretilen karar kayıtlıyla uyuşmadı — aynı girdi aynı çıktıyı vermedi "
            f"(K-009). Kayıtlı: {kontrol.bekleyen}, üretilen: {uretilen}"
        )
    return True


def _oynat(
    motor: PaperMotoru,
    diziler: dict[str, Any],
    zamanlar: Sequence[int],
    filller: Sequence[dict[str, Any]],
    *,
    son_indeks: int,
) -> None:
    """Stratejiyi pencerenin başından `son_indeks`ten **bir önceki** bara kadar oynatır.

    Üretilen sinyaller atılıyor: bu oynatmanın tek amacı stratejinin iç durumunu (son
    kesişim yönü, sayaçlar) o ana getirmek. Son barın sinyali ayrıca ve canlı yoldan
    üretiliyor, çünkü karşılaştırılacak olan o.
    """
    gorunum = gorunum_kur(motor.kimlik.sembol, motor.kimlik.timeframe, diziler, motor.strateji)
    portfoyler = _portfoy_gecmisi(motor.kimlik.baslangic_sermaye, zamanlar, filller)
    for j in range(son_indeks):
        fiyat = float(diziler["close"][j])
        ctx = gorunum.baglam(j, portfoyler[j].gorunum(fiyat))
        motor.strateji.on_bar(ctx)


def _portfoy_gecmisi(
    baslangic: float, zamanlar: Sequence[int], filller: Sequence[dict[str, Any]]
) -> list[Portfoy]:
    """Her bar için o barın **kararı verilirken** geçerli olan portföy.

    Fill `t`nin açılışında olur, karar `t`nin kapanışında verilir — yani `zaman_ms <= t`
    olan her fill o barın kararında zaten uygulanmıştır. Sınırın `<=` olması bu yüzden;
    `<` olsaydı strateji kendi doldurduğu pozisyonu bir bar geç görürdü.
    """
    p = Portfoy(nakit=baslangic)
    sonuc: list[Portfoy] = []
    j = 0
    for t in zamanlar:
        while j < len(filller) and int(filller[j]["zaman_ms"]) <= t:
            f = filller[j]
            miktar, fiyat, komisyon = (
                float(f["miktar"]),
                float(f["fiyat"]),
                float(f["komisyon"]),
            )
            if str(f["yon"]) == str(IslemYonu.AL):
                p = p.al(miktar, fiyat, komisyon, int(f["zaman_ms"]))
            else:
                p, _ = p.sat(miktar, fiyat, komisyon)
            j += 1
        sonuc.append(p)
    return sonuc


__all__ = ["TOLERANS", "ToparlanmaSonucu", "toparlan"]
