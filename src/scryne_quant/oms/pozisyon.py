"""Pozisyon mutabakatı: defterin *söylediği* bakiye ile borsanın *gösterdiği* bakiye.
(§25, Faz 7'nin ölçmediği, Faz 8'in kriteri)

Faz 7 emir mutabakatını kurdu (`oms/mutabakat.py`) ve pozisyon tarafını bilerek açık
bıraktı. Gerekçesi o dosyada yazılı ve hâlâ geçerli:

> *"Bakiye farkını emirlerden türetmek, koşunun başındaki bakiyenin bağımsız bir kaydını
> gerektirir; o kayıt yoksa yapılan karşılaştırma 'borsa ne diyorsa o' demenin süslü hâli
> olur."*

Bu modül o kaydı kuruyor ve karşılaştırmayı yapıyor. Faz 8'in bitti kriterlerinden biri
tam olarak burada yaşıyor: *"uzlaşmazlık, duplicate emir veya **açıklanamayan pozisyon
farkı** sayısı: sıfır."*

## Üç taraflı bir karşılaştırma, iki taraflı değil

| Taraf | Nereden | Değişmez mi |
| --- | --- | --- |
| **Çıpa** — açılış bakiyesi | Borsadan, ilk emirden önce | **Evet**, yazılıp bırakılır |
| **Akış** — defterin fill'leri | Bizim kaydımız | Hayır, koşu boyunca büyür |
| **Gerçek** — bugünkü bakiye | Borsadan, şimdi | — |

`çıpa + akış` bizim **iddiamız**; `gerçek` borsanın beyanı. Fark sıfır değilse, iddiayla
beyan arasında açıklanamayan bir şey var demektir.

**Çıpanın değişmezliği bu ölçümün tamamı.** Yazılabilir olsaydı, açıklanamayan bir farkla
karşılaşan herkesin elinde *"çıpayı tazele"* düğmesi olurdu; fark araştırılmak yerine
sıfırlanırdı ve kriter her koşuda kendiliğinden geçerdi. Değişmezlik `oms/defter.py`de iki
SQLite tetiğiyle uygulanıyor, bir kod nezaketiyle değil.

## Komisyon isteğe bağlı bir ayrıntı değil, hesabın yarısı

Binance komisyonu **alınan varlıktan** keser: BTC alırken gelen BTC'den, satarken gelen
USDT'den. Yani 0,001 BTC'lik bir alımda hesaba 0,001 BTC girmez, 0,000999 girer.
Komisyonu hesaba katmayan bir "beklenen bakiye" her alımda ~%0,1 yanılır — ve bu, bu
projenin *"neredeyse doğru"* dediği sınıfın ta kendisi: çökme yok, hata yok, sadece emir
sayısıyla birlikte büyüyen sessiz bir fark.

O yüzden komisyonun **bilinmemesi** ile **sıfır olması** diskte bile ayrı tutuluyor
(`oms/emir.KOMISYON_KAYNAKLARI`). Komisyonu bilinmeyen dolmuş bir emir varken beklenen
bakiye hesaplanamaz, ve bu modül o durumda **tahmin yürütmüyor**: `%0,1 varsaydım` diyen
bir satır yazmak yerine mutabakat "ölçülemedi" diyor ve koşu duruyor. (`VARSAYILAN_ORAN`
diye bir sabit bu dosyada bilerek yok.)

Eksik komisyonun **doldurulabilir** bir yolu var ve mutabakat önce onu deniyor:
`/api/v3/myTrades`, yani `EmirAdaptoru.emir_islemleri`. `POST` yanıtı kaybolmuş bir emrin
(`UNKNOWN → FILLED`) komisyonu yalnızca oradan öğrenilir.

## Hangi varlıklar karşılaştırılıyor

Yalnızca işlem çiftinin iki ayağı: `taban_varlik` ve `kote_varlik`. Hesaptaki başka bir
varlığın değişmesi bu koşunun iddiasını yanlışlamaz — strateji ona hiç dokunmadı.
İstisna, komisyonun üçüncü bir varlıktan (BNB) kesilmesi: o zaman komisyon taban/koteden
**düşülmez** ve hesap kendiliğinden doğru kalır, çünkü toplama varlık bazında yapılıyor.

## Tolerans neden var ve neden bu kadar küçük

İki taraf da kayan nokta taşıyor: bizim tarafta `dolan × ortalama_fiyat` çarpımı, borsa
tarafında ondalık bir metnin `float`a çevrilmesi. Tolerans bu gürültüyü geçecek kadar
büyük, gerçek bir farkı yutamayacak kadar küçük olmalı — ve **ciro ile** ölçeklenmeli,
net pozisyonla değil: hata her işlemde birikir, net bakiyede değil.

`tolerans = max(MUTLAK_TABAN, brüt_ciro × GORELI)` ile `GORELI = 1e-9`, yani `float`
epsilon'unun ~10 milyon katı (asla yanlış alarm) ama bir lot adımının on binde biri (hiçbir
gerçek farkı gizleyemez).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from scryne_quant.exchange.emir_adaptoru import BORSA_YONU, EmirAdaptoru, Varlik
from scryne_quant.oms.emir import Emir, Komisyon

#: Kayan nokta gürültüsünün brüt ciroya oranlı payı. Bkz. modül docstring'i.
GORELI_TOLERANS = 1e-9

#: Cironun sıfıra yakın olduğu durumlar için mutlak taban. `oms/mutabakat.py`nin dolum
#: karşılaştırmasıyla aynı büyüklük ve aynı gerekçe: lot adımının (1e-5) üç kat altında.
MUTLAK_TOLERANS = 1e-8

#: Bakiyeyi **artıran** yön. `FLAT` (tam çıkış) satıştır, `BORSA_YONU` ile aynı çeviri.
_ALIS = "BUY"


class PozisyonHatasi(RuntimeError):
    """Pozisyon mutabakatı yapılamıyor."""


class CipaYok(PozisyonHatasi):
    """Koşunun açılış bakiyesi kaydedilmemiş — karşılaştırılacak bir çıpa yok.

    Bu bir uyuşmazlık **değil**, bir ölçülemezlik. İkisini aynı istisnaya toplamak,
    "ölçtüm ve fark buldum" ile "ölçemedim" arasındaki farkı silerdi — K-039'un
    *"ölçülemedi ≠ kaldı"* ayrımının aynısı.
    """


class PozisyonUyusmazligi(RuntimeError):
    """Açıklanamayan pozisyon farkı. **Koşu durur.**

    `oms/mutabakat.Uyusmazlik` ile aynı sözleşme: yakalanıp yutulmaz. Bir farkı loglayıp
    devam etmek, tahmin yürütmenin en yaygın biçimi (K-038).
    """

    def __init__(self, sonuc: PozisyonSonucu) -> None:
        super().__init__(sonuc.ozet())
        self.sonuc = sonuc


class PozisyonDefteri(Protocol):
    """Pozisyon mutabakatının defterden istediği yüzey.

    `EmirDefteri`nin tamamı değil: bu modül emir **yazmaz**, yalnızca eksik komisyonu
    doldurur. Dar bir protokol, `sq testnet pozisyon --sadece-rapor`un yazma yolunu
    kapatabilmesini de mümkün kılıyor (`cli/testnet._YazmayanDefter` ile aynı kalıp).
    """

    def tumu(self, *, limit: int | None = ...) -> list[Emir]: ...

    def acilis_oku(self) -> dict[str, Any] | None: ...

    def komisyon_yaz(
        self, istemci_kimligi: str, komisyon: Komisyon, *, kaynak: str
    ) -> Emir: ...


@dataclass(frozen=True, slots=True)
class VarlikFarki:
    """Tek bir varlığın mutabakatı."""

    varlik: str
    acilis: float
    akis: float
    """Defterden türeyen net değişim (komisyon düşülmüş)."""

    beklenen: float
    gercek: float
    tolerans: float
    brut_ciro: float

    @property
    def fark(self) -> float:
        return self.gercek - self.beklenen

    @property
    def aciklanamaz(self) -> bool:
        return abs(self.fark) > self.tolerans

    def sozluk(self) -> dict[str, Any]:
        return {
            "varlik": self.varlik,
            "acilis": self.acilis,
            "akis": self.akis,
            "beklenen": self.beklenen,
            "gercek": self.gercek,
            "fark": self.fark,
            "tolerans": self.tolerans,
            "brut_ciro": self.brut_ciro,
            "aciklanamaz": self.aciklanamaz,
        }


@dataclass(frozen=True, slots=True)
class PozisyonSonucu:
    """Bir pozisyon mutabakatının tamamı."""

    sembol: str
    farklar: tuple[VarlikFarki, ...] = field(default=())
    eksik_komisyon: tuple[str, ...] = field(default=())
    """Dolmuş ama komisyonu hâlâ bilinmeyen emirlerin istemci kimlikleri.

    Boş değilse beklenen bakiye **hesaplanamaz** ve sonuç `halt` verir. Bu bir fark
    bulgusu değil, hesabın yapılamadığının kaydı — `ozet()` ikisini ayrı yazıyor.
    """

    doldurulan_komisyon: tuple[str, ...] = field(default=())
    """Mutabakat sırasında `/api/v3/myTrades`ten öğrenilip deftere yazılanlar."""

    @property
    def halt(self) -> bool:
        return bool(self.eksik_komisyon) or any(f.aciklanamaz for f in self.farklar)

    def ozet(self) -> str:
        if not self.halt:
            satirlar = " · ".join(
                f"{f.varlik} fark {f.fark:+.10f} (tol {f.tolerans:.10f})"
                for f in self.farklar
            )
            return f"pozisyon mutabakatı temiz: {satirlar}"

        parcalar: list[str] = []
        if self.eksik_komisyon:
            parcalar.append(
                f"KOMİSYON EKSİK: {len(self.eksik_komisyon)} dolmuş emrin komisyonu "
                f"bilinmiyor, beklenen bakiye hesaplanamaz. Borsa bu emirler için işlem "
                f"kaydı vermedi; tahmin yürütülmüyor.\n  "
                + ", ".join(self.eksik_komisyon[:10])
            )
        for f in self.farklar:
            if f.aciklanamaz:
                parcalar.append(
                    f"AÇIKLANAMAYAN FARK — {f.varlik}: beklenen {f.beklenen:.10f}, "
                    f"borsada {f.gercek:.10f}, fark {f.fark:+.10f} "
                    f"(tolerans {f.tolerans:.10f}).\n  Çıpa {f.acilis:.10f} + "
                    f"defter akışı {f.akis:+.10f}. Farkın kaynağı bu koşunun dışında: "
                    f"yatırma/çekme, elle işlem, başka bir süreç ya da kayba uğramış "
                    f"bir kayıt."
                )
        return "\n".join(parcalar)

    def sozluk(self) -> dict[str, Any]:
        return {
            "sembol": self.sembol,
            "halt": self.halt,
            "farklar": [f.sozluk() for f in self.farklar],
            "eksik_komisyon": list(self.eksik_komisyon),
            "doldurulan_komisyon": list(self.doldurulan_komisyon),
        }


def pozisyon_mutabakati(
    defter: PozisyonDefteri,
    adaptor: EmirAdaptoru,
    sembol: str,
    *,
    durdur: bool = True,
) -> PozisyonSonucu:
    """Çıpa + defter akışını borsanın bakiyesiyle karşılaştırır.

    `durdur=False` yalnızca raporlama içindir (`sq testnet pozisyon`, dashboard). Emir
    yolunda varsayılan kullanılır ve `PozisyonUyusmazligi` fırlar — `oms/mutabakat.py`
    ile aynı sözleşme.

    Çıpa yoksa `CipaYok` fırlar ve bu `durdur`dan **bağımsızdır**: raporlama modu bile
    olmayan bir ölçümü "temiz" diye raporlayamaz.
    """
    acilis = defter.acilis_oku()
    if acilis is None:
        raise CipaYok(
            "koşunun açılış bakiyesi kaydedilmemiş; pozisyon mutabakatı yapılamaz. "
            "Çıpa ilk emirden önce `EmirDefteri.acilis_yaz` ile atılır. Çıpasız bir "
            "karşılaştırma, borsanın beyanını doğrulamak değil tekrarlamak olurdu."
        )

    kurallar = adaptor.sembol_kurallari(sembol)
    taban, kote = kurallar.taban_varlik, kurallar.kote_varlik
    if not taban or not kote:
        raise PozisyonHatasi(
            f"{sembol} için taban/kote varlık bilinmiyor (borsadan gelmemiş). "
            f"Sembol adını kesip tahmin etmek BNBBTC gibi çiftlerde sessizce yanlış "
            f"cevap verir; mutabakat tahminle yapılmaz."
        )

    emirler = defter.tumu()
    doldurulan = _eksik_komisyonlari_doldur(defter, adaptor, sembol, emirler)
    if doldurulan:
        emirler = defter.tumu()

    eksik = tuple(
        e.istemci_kimligi for e in emirler if e.komisyon_bilinmiyor
    )

    akis, brut = _akis(emirler, taban=taban, kote=kote)
    gercek = adaptor.bakiye()

    farklar = tuple(
        _fark(
            varlik,
            acilis=_acilistan(acilis, varlik),
            akis=akis.get(varlik, 0.0),
            gercek=gercek.get(varlik, Varlik()).toplam,
            brut_ciro=brut.get(varlik, 0.0),
        )
        for varlik in (taban, kote)
    )

    sonuc = PozisyonSonucu(
        sembol=sembol,
        farklar=farklar,
        eksik_komisyon=eksik,
        doldurulan_komisyon=doldurulan,
    )
    if sonuc.halt and durdur:
        raise PozisyonUyusmazligi(sonuc)
    return sonuc


# --------------------------------------------------------------------------- iç


def _eksik_komisyonlari_doldur(
    defter: PozisyonDefteri,
    adaptor: EmirAdaptoru,
    sembol: str,
    emirler: list[Emir],
) -> tuple[str, ...]:
    """Komisyonu bilinmeyen dolmuş emirler için `/api/v3/myTrades`e sorar.

    Yalnızca borsa kimliği olan emirler sorulabilir: kimliği olmayan bir emir borsada
    kabul edilmemiştir, ve kabul edilmemiş bir emrin dolmuş görünmesi zaten başka bir
    sorundur (emir mutabakatının işi).

    Borsa boş dönerse komisyon yazılmıyor ve emir *eksik* kalıyor — boş yanıtı "komisyon
    sıfırdı" diye yazmak, öğrenilmemiş bir şeyi ölçülmüş göstermek olurdu.
    """
    doldurulan: list[str] = []
    for emir in emirler:
        if not emir.komisyon_bilinmiyor or not emir.borsa_kimligi:
            continue
        komisyon = adaptor.emir_islemleri(
            sembol=emir.sembol or sembol, borsa_kimligi=emir.borsa_kimligi
        )
        if not komisyon:
            continue
        defter.komisyon_yaz(emir.istemci_kimligi, komisyon, kaynak="islemler")
        doldurulan.append(emir.istemci_kimligi)
    return tuple(doldurulan)


def _akis(
    emirler: list[Emir], *, taban: str, kote: str
) -> tuple[dict[str, float], dict[str, float]]:
    """Defterin fill'lerinden varlık bazında net akış ve brüt ciro.

    Net akış beklenen bakiyeyi verir; brüt ciro toleransı ölçekler. İkisi ayrı toplanıyor
    çünkü BUY–SELL–BUY–SELL biçiminde dönen bir koşunun neti sıfıra yakındır ama kayan
    nokta hatası işlem sayısıyla birikir.
    """
    net: dict[str, float] = {taban: 0.0, kote: 0.0}
    brut: dict[str, float] = {taban: 0.0, kote: 0.0}

    for emir in emirler:
        if emir.dolan_miktar <= 0.0:
            continue
        taban_miktar = emir.dolan_miktar
        kote_miktar = emir.dolan_miktar * emir.ortalama_fiyat
        isaret = 1.0 if BORSA_YONU.get(emir.yon.upper()) == _ALIS else -1.0

        net[taban] += isaret * taban_miktar
        net[kote] -= isaret * kote_miktar
        brut[taban] += taban_miktar
        brut[kote] += kote_miktar

        # Komisyon her zaman **azaltır** ve her zaman kesildiği varlıktan. Üçüncü bir
        # varlıktan kesilmişse (BNB) taban/koteye hiç dokunmuyor — toplama varlık
        # bazında yapıldığı için bu kendiliğinden doğru çıkıyor, ayrı bir dal gerekmiyor.
        for varlik, miktar in emir.komisyon:
            if varlik in net:
                net[varlik] -= miktar
                brut[varlik] += miktar

    return net, brut


def _acilistan(acilis: dict[str, Any], varlik: str) -> float:
    """Çıpadaki bir varlığın **toplamı** (serbest + kilitli).

    Toplam kullanılıyor, serbest değil: açık bir limit emri parayı serbestten kilitliye
    taşır ve hesabın toplamını değiştirmez. Yalnızca serbeste bakan bir mutabakat, her
    açık limit emrinde haksız yere durur (`exchange/emir_adaptoru.Varlik`).
    """
    kalem = acilis.get("varliklar", {}).get(varlik)
    if not kalem:
        return 0.0
    return float(kalem.get("serbest", 0.0)) + float(kalem.get("kilitli", 0.0))


def _fark(
    varlik: str, *, acilis: float, akis: float, gercek: float, brut_ciro: float
) -> VarlikFarki:
    beklenen = acilis + akis
    tolerans = max(MUTLAK_TOLERANS, (brut_ciro + abs(acilis)) * GORELI_TOLERANS)
    return VarlikFarki(
        varlik=varlik,
        acilis=acilis,
        akis=akis,
        beklenen=beklenen,
        gercek=gercek,
        tolerans=tolerans,
        brut_ciro=brut_ciro,
    )


def cipa_at(
    defter: Any, adaptor: EmirAdaptoru, *, not_metni: str = ""
) -> dict[str, Any]:
    """Koşunun açılış bakiyesini borsadan okuyup deftere **bir kez** yazar.

    Koşuyu başlatan yer bunu ilk emirden **önce** çağırmak zorunda; `EmirDefteri.acilis_yaz`
    deftere emir girmişse reddediyor. Burada bir "zaten varsa geç" kolaylığı **yok**:
    ikinci bir çağrı hata alır, çünkü bir koşunun tek bir başlangıcı vardır.
    """
    bakiye = adaptor.bakiye()
    borsa_ms = adaptor.sunucu_zamani_ms()
    defter.acilis_yaz(
        {a: (v.serbest, v.kilitli) for a, v in bakiye.items()},
        borsa_ms=borsa_ms,
        # `saat_sapmasi_ms` = yerel − borsa, yani yerel = borsa + sapma. İkisi de
        # yazılıyor: çıpanın ne zaman atıldığı bir sonraki araştırmanın ilk sorusu ve
        # o soruyu yalnızca borsa saatiyle cevaplamak, makinenin saatinin o an ne
        # dediğini kaybetmek olurdu.
        yerel_ms=borsa_ms + adaptor.saat_sapmasi_ms(),
        not_metni=not_metni,
    )
    return defter.acilis_oku()


__all__ = [
    "GORELI_TOLERANS",
    "MUTLAK_TOLERANS",
    "CipaYok",
    "PozisyonDefteri",
    "PozisyonHatasi",
    "PozisyonSonucu",
    "PozisyonUyusmazligi",
    "VarlikFarki",
    "cipa_at",
    "pozisyon_mutabakati",
]
