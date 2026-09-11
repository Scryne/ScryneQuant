"""Mutabakat: defter ile borsayı karşılaştırır, uyuşmazlıkta koşuyu durdurur. (§25, Faz 7)

Faz 7'nin iki bitti kriteri burada yaşıyor:

> *"Süreç emir gönderiminin ortasında öldürüldüğünde, yeniden başlayınca borsadaki gerçek
> durumla local state uyuşuyor."*
> *"Uyuşmazlık tespit edildiğinde sistem işlem yapmayı durduruyor (halt), tahmin
> yürütmüyor."*

**İki kriter aynı mekanizmanın iki yüzü.** Mutabakat, çözebildiği farkları çözer;
çözemediklerini **çözmeye çalışmaz**. Aradaki sınır keyfi değil, bilgiye dayalı: defterin
"bilmiyorum" dediği yerde borsa otoritedir ve cevabı yazılır; defterin "biliyorum" dediği
yerde borsa başka bir şey söylüyorsa ortada bir **çelişki** vardır ve çelişkiyi çözmenin
tek dürüst yolu durmaktır.

| Defter | Borsa | Karar | Gerekçe |
| --- | --- | --- | --- |
| `SUBMITTED` | emir yok | `FAILED` | Yazım gönderimden önceydi; gönderim olmamış |
| `SUBMITTED` | emir var | borsanın durumu | Gönderim olmuş, yanıt kaybolmuş |
| `UNKNOWN` | emir yok | `FAILED` | Bilinmezliğin cevabı: oluşmamış |
| `UNKNOWN` | emir var | borsanın durumu | Bilinmezliğin cevabı: oluşmuş |
| `ACKNOWLEDGED` | emir yok | **HALT** | Borsa kabul ettiği emri tanımıyor — çelişki |
| `ACKNOWLEDGED` | emir var | borsanın durumu | Normal ilerleme |
| defterde yok | borsada açık | **HALT** | Sistemin üretmediği ya da kaydını kaybettiği emir |

**Neden `ACKNOWLEDGED` + "emir yok" bir çelişki.** Binance `origClientOrderId` ile yapılan
sorguyu geçmiş emirlerde de yanıtlar; dolmuş, iptal edilmiş, süresi geçmiş bir emir de
bulunur. Yani "bulunamadı" cevabı *"böyle bir emir hiç olmadı"* demektir. Biz o emrin
borsa kimliğini elimizde tutarken borsanın onu tanımaması, iki tarafın farklı gerçeklikte
olduğu anlamına gelir — ve bu noktadan sonra hesaplanan her pozisyon bir tahmindir.

**Bu modül pozisyon mutabakatı yapmıyor ve bu bilinçli.** Bakiye farkını emirlerden
türetmek, koşunun başındaki bakiyenin bağımsız bir kaydını gerektirir; o kayıt yoksa
yapılan karşılaştırma "borsa ne diyorsa o" demenin süslü hâli olur. Faz 8'in *"açıklanamayan
pozisyon farkı: sıfır"* kriteri o kaydı kurar. Ölçülemeyen bir şeyi ölçüyormuş gibi yapmak,
bu projede en pahalı hata sınıfı (K-039'un "ölçülemedi ≠ kaldı" ayrımı).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scryne_quant.exchange.emir_adaptoru import BorsaEmri, EmirAdaptoru
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.oms.emir import Emir, EmirDurumu, gecis_yasal_mi

#: Defterin "bilmiyorum" dediği durumlar: borsa ne derse o yazılır.
BELIRSIZ: frozenset[EmirDurumu] = frozenset(
    {EmirDurumu.SUBMITTED, EmirDurumu.UNKNOWN}
)


class Uyusmazlik(RuntimeError):
    """Defter ile borsa çelişiyor. **Koşu durur.**

    Bu istisna yakalanıp yutulmamalı: K-038'in kuralı *"uyuşmazlıkta koşu durur, tahmin
    yürütülmez."* Bir uyuşmazlığı loglayıp devam etmek, tahmin yürütmenin en yaygın
    biçimidir.
    """

    def __init__(self, sonuc: MutabakatSonucu) -> None:
        super().__init__(sonuc.ozet())
        self.sonuc = sonuc


@dataclass(frozen=True, slots=True)
class Fark:
    """Mutabakatın bulduğu tek bir fark."""

    istemci_kimligi: str
    defter_durumu: str
    borsa_durumu: str
    karar: str
    aciklama: str

    def sozluk(self) -> dict[str, Any]:
        return {
            "istemci_kimligi": self.istemci_kimligi,
            "defter_durumu": self.defter_durumu,
            "borsa_durumu": self.borsa_durumu,
            "karar": self.karar,
            "aciklama": self.aciklama,
        }


@dataclass(frozen=True, slots=True)
class MutabakatSonucu:
    """Bir mutabakat koşusunun tamamı.

    `uyusmazlik` boş değilse koşu devam **etmemeli**; `halt` bunu tek bir soruya indiriyor.
    """

    incelenen: int = 0
    cozulen: tuple[Fark, ...] = field(default=())
    uyusmazlik: tuple[Fark, ...] = field(default=())
    degismeyen: int = 0

    @property
    def halt(self) -> bool:
        return bool(self.uyusmazlik)

    def ozet(self) -> str:
        if not self.halt:
            return (
                f"mutabakat temiz: {self.incelenen} emir incelendi, "
                f"{len(self.cozulen)} fark çözüldü, {self.degismeyen} değişmedi"
            )
        satirlar = "\n".join(
            f"  - {f.istemci_kimligi}: defter={f.defter_durumu} "
            f"borsa={f.borsa_durumu} — {f.aciklama}"
            for f in self.uyusmazlik
        )
        return (
            f"UYUŞMAZLIK: {len(self.uyusmazlik)} emir defterle borsayı çelişkiye "
            f"düşürüyor. Koşu durmalı; pozisyon hesabı bu noktadan sonra tahmindir.\n"
            f"{satirlar}"
        )

    def sozluk(self) -> dict[str, Any]:
        return {
            "incelenen": self.incelenen,
            "degismeyen": self.degismeyen,
            "halt": self.halt,
            "cozulen": [f.sozluk() for f in self.cozulen],
            "uyusmazlik": [f.sozluk() for f in self.uyusmazlik],
        }


def mutabakat(
    defter: EmirDefteri, adaptor: EmirAdaptoru, sembol: str, *, durdur: bool = True
) -> MutabakatSonucu:
    """Defterin açık emirlerini borsayla karşılaştırır ve çözebildiklerini yazar.

    `durdur=False` yalnızca **raporlama** içindir (CLI'ın `sq testnet mutabakat` komutu,
    dashboard): uyuşmazlığı görmek isteyip koşuyu durdurmak istemeyen çağıran. Emir
    yolunda çağrılırken varsayılan kullanılır ve `Uyusmazlik` fırlar.
    """
    cozulen: list[Fark] = []
    uyusmazlik: list[Fark] = []
    degismeyen = 0

    acik = defter.acik_emirler()
    for emir in acik:
        borsada = adaptor.emir_sorgula(
            sembol=emir.sembol, istemci_kimligi=emir.istemci_kimligi
        )
        fark, degisti = _tek_emir(defter, emir, borsada)
        if fark is None:
            degismeyen += 1
        elif degisti:
            cozulen.append(fark)
        else:
            uyusmazlik.append(fark)

    uyusmazlik.extend(_defterde_olmayanlar(defter, adaptor, sembol))

    sonuc = MutabakatSonucu(
        incelenen=len(acik),
        cozulen=tuple(cozulen),
        uyusmazlik=tuple(uyusmazlik),
        degismeyen=degismeyen,
    )
    if sonuc.halt and durdur:
        raise Uyusmazlik(sonuc)
    return sonuc


def _tek_emir(
    defter: EmirDefteri, emir: Emir, borsada: BorsaEmri | None
) -> tuple[Fark | None, bool]:
    """Tek emrin mutabakatı. Döner: `(fark, cozuldu_mu)`; fark yoksa `(None, False)`."""
    if borsada is None:
        if emir.durum in BELIRSIZ:
            defter.gecir(
                emir.istemci_kimligi,
                EmirDurumu.FAILED,
                zaman_ms=emir.guncellendi_ms,
                hata="mutabakat: borsa bu kimlikte emir tanımıyor — gönderim olmamış",
            )
            return (
                Fark(
                    emir.istemci_kimligi,
                    str(emir.durum),
                    "yok",
                    str(EmirDurumu.FAILED),
                    "borsa emri tanımıyor; belirsizlik 'oluşmadı' olarak kapandı",
                ),
                True,
            )
        return (
            Fark(
                emir.istemci_kimligi,
                str(emir.durum),
                "yok",
                "HALT",
                "borsa kabul ettiği emri tanımıyor — iki taraf farklı gerçeklikte",
            ),
            False,
        )

    if borsada.durum is emir.durum and _dolum_ayni(emir, borsada):
        return None, False

    if not gecis_yasal_mi(emir.durum, borsada.durum):
        return (
            Fark(
                emir.istemci_kimligi,
                str(emir.durum),
                str(borsada.durum),
                "HALT",
                f"borsanın durumu state machine'de ulaşılamaz: "
                f"{emir.durum} → {borsada.durum}",
            ),
            False,
        )

    defter.gecir(
        emir.istemci_kimligi,
        borsada.durum,
        zaman_ms=borsada.guncellendi_ms or emir.guncellendi_ms,
        borsa_kimligi=borsada.borsa_kimligi,
        dolan_miktar=borsada.dolan_miktar,
        ortalama_fiyat=borsada.ortalama_fiyat,
        hata="mutabakat: borsanın durumu yazıldı",
    )
    return (
        Fark(
            emir.istemci_kimligi,
            str(emir.durum),
            str(borsada.durum),
            str(borsada.durum),
            "borsa otorite; defter borsanın durumuna güncellendi",
        ),
        True,
    )


def _dolum_ayni(emir: Emir, borsada: BorsaEmri) -> bool:
    """Dolan miktarlar aynı mı? Lot adımının çok altında bir tolerans yeter.

    Tolerans **sıfır değil** çünkü iki taraf da kayan nokta taşıyor; ama lot adımından
    (BTCUSDT'de 1e-5) üç kat küçük, yani gerçek bir kısmi dolum farkını asla yutmaz.
    """
    return abs(emir.dolan_miktar - borsada.dolan_miktar) < 1e-8


def _defterde_olmayanlar(
    defter: EmirDefteri, adaptor: EmirAdaptoru, sembol: str
) -> list[Fark]:
    """Borsada açık ama defterde olmayan emirler — her biri bir uyuşmazlık.

    Böyle bir emir iki şeyden biridir: sistemin üretmediği (elle girilmiş, başka bir
    süreçten gelmiş) ya da sistemin kaydını kaybettiği bir emir. İkisi de koşuyu
    durdurur — çünkü ikisinde de defter, borsadaki maruziyeti eksik biliyor demektir.
    """
    farklar: list[Fark] = []
    for borsada in adaptor.acik_emirler(sembol):
        if defter.al(borsada.istemci_kimligi) is not None:
            continue
        farklar.append(
            Fark(
                borsada.istemci_kimligi or borsada.borsa_kimligi,
                "yok",
                str(borsada.durum),
                "HALT",
                "borsada açık emir var, defterde kaydı yok — sistemin üretmediği "
                "ya da kaydını kaybettiği bir emir",
            )
        )
    return farklar


__all__ = [
    "BELIRSIZ",
    "Fark",
    "MutabakatSonucu",
    "Uyusmazlik",
    "mutabakat",
]
