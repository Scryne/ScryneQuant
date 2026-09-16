"""Hipotez defteri: kaç çekiliş yapıldığının kaydı. (K-039)

**Kapatmaya çalıştığı boşluk.** K-019'un yedi kapısı strateji **başına** çalışıyor ve
hiçbiri "bu kaçıncı denemeydi" sorusunu sormuyor. Faz 4'te yedi hipotez denendi, yedisi de
kaldı — doğru sonuç. Ama elli tane daha denenirse, kapılara **hiç dokunmadan**, birinin
şans eseri geçme olasılığı ciddi biçimde yükselir. Yani K-018'in *"sayısal eşik
esnetilemez"* kuralı, eşiğe el sürmeden, yalnızca yeterince çok deneyerek delinebilir.

Bu, promotion zincirinin en sessiz başarısızlık yolu: hiçbir kural çiğnenmez, hiçbir test
kırılmaz, ve sonunda "kapıları geçen bir strateji" ortaya çıkar. O stratejinin kaçıncı
deneme olduğu kayıtlı değilse, geçtiği kapının ne anlama geldiği de bilinmiyor demektir.

**Bu modülün yapmadığı şey: eşiği düzeltmek.** Bonferroni benzeri bir düzeltme çekici ama
buraya yanlış oturur — stratejiler bağımsız değil (aynı veri, örtüşen sinyaller), yani
düzeltme çarpanı bilinmiyor ve uydurulan bir çarpan, olmayan bir kesinlik iddia eder.
K-019'un eşikleri Faz 4'ün ölçümüne kadar nasıl **açık** bırakıldıysa, düzeltme de öyle
açık bırakılıyor (K-039).

**Yaptığı iki şey:**

1. **Ön kayıt.** Bir hipotez, sonucu görülmeden **önce** deftere yazılır. Sonradan yazılan
   bir hipotez "zaten bunu bekliyordum" demenin kaydıdır, kanıt değil.
2. **Sayım.** Her promotion kanıtı, o stratejinin kaçıncı hipotez olduğunu taşır. Sayı bir
   eşik değil; okunması zorunlu bir bağlam.

**Defter `docs/Hipotez-Defteri.jsonl` ve bu bir karar.** `runs/` altında olması doğal
görünüyordu ama yanlış: `runs/` `.gitignore`'da ve **iz bırakmadan silinebilen bir defter,
defter değildir.** Sayacı sıfırlamak, K-039'un engellemeye çalıştığı şeyi bir `rm` ile
yapmak olurdu. Defter `docs/` altında, sürüm kontrolünde, karar günlüğünün yanında —
çünkü tuttuğu şey bir çalışma çıktısı değil, bir araştırma kaydı.

Biçim JSONL: append-only, satır başına bir hipotez. Tek bir JSON dizisi olsaydı her ekleme
dosyanın tamamını yeniden yazardı ve diff'te "her şey değişti" gibi görünürdü; JSONL'de bir
hipotez eklemek diff'te **tek bir satır**.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.zaman import simdi_ms, utc_str

VARSAYILAN_YOL: Final = Path("docs/Hipotez-Defteri.jsonl")

#: Tanınan parametre seçim yöntemleri. Yeni bir yöntem eklemek buraya yazmakla olur ve
#: **her strateji için yeni bir çekiliş** demektir.
SECIM_YONTEMLERI: Final[tuple[str, ...]] = ("tepe", "plato")


class HipotezHatasi(ValueError):
    """Hipotez defteri kuralı ihlal edildi."""


@dataclass(frozen=True, slots=True)
class Hipotez:
    """Tek bir çekiliş: neyin, hangi veride, hangi parametre uzayında sınandığı.

    `kimlik` bu dördünün hash'i. Aynı hipotezi iki kez kaydetmek yeni bir çekiliş
    **değil** — aynı soruyu iki kez sormak yeni bir bilgi üretmez. Ama farklı bir
    parametre ızgarası veya farklı bir veri aralığı yeni bir çekiliştir ve sayılır.
    """

    strateji: str
    timeframe: str
    veri_sha256: str
    izgara: dict[str, list[Any]]
    secim: str
    """Parametre **seçim yöntemi** (`tepe` | `plato`). Kimliğin parçası ve bu bir karar.

    Seçim yöntemini kimliğin dışında bırakmak, "argmax dene, olmadı platoyu dene, olmadı
    şunu dene" zincirini **bedava çekiliş** yapardı: aynı ızgara, aynı veri, ama her
    seferinde farklı bir kural — yani yeni bir tahmin. Aynı veriye yeni bir soru sormanın
    her biçimi sayılmak zorunda.
    """

    gerekce: str
    """Bu hipotezin **neden** denendiği. Sonuç görülmeden yazılıyor; boş bırakılamaz.

    Zorunlu olması bilinçli: gerekçesiz bir hipotez, ızgarayı genişletmenin kibar adıdır.
    """

    # ------------------------------------------------------------ v2 alanları (K-051/4)

    program: str = ""
    """Bu çekilişin ait olduğu araştırma programı (`research/program.py`). Boş = Faz 4'ün
    program öncesi çekilişleri; yeni hipotezlerde CLI zorunlu kılıyor (K-051/2)."""

    evren: str = ""
    """`EvrenKurali.kimlik` — hangi enstrüman evreninde sorulduğu."""

    portfoy: str = ""
    """`KurmaAyarlari.yontem` — hangi portföy kurma yöntemiyle."""

    rejim: str = ""
    """Rejim tanımının kimliği — hangi rejim bölümlemesi altında."""

    zaman_ms: int = field(default_factory=simdi_ms)

    def __post_init__(self) -> None:
        if not self.strateji or not self.timeframe:
            raise HipotezHatasi("hipotez strateji ve timeframe taşımalı")
        if self.secim not in SECIM_YONTEMLERI:
            raise HipotezHatasi(
                f"bilinmeyen seçim yöntemi {self.secim!r}; geçerli: "
                f"{', '.join(SECIM_YONTEMLERI)}"
            )
        if len(self.gerekce.strip()) < 20:
            raise HipotezHatasi(
                "hipotez bir gerekçe ister (≥20 karakter): gerekçesiz bir hipotez, "
                "ızgarayı genişletmenin kibar adıdır (K-039)"
            )

    @property
    def kimlik(self) -> str:
        """Hipotezin içerik hash'i. Gerekçe ve zaman **dahil değil** — ikisi de aynı
        soruyu farklı kelimelerle sormayı yeni bir çekiliş yapmamalı.

        **K-051/4'ün üç yeni alanı (evren, portföy, rejim) hash'e yalnızca doluysa
        giriyor.** Üçü de "aynı veriye yeni bir soru sormanın" biçimleri ve kimliğin
        dışında kalırlarsa bedava çekiliş olurlar — ama koşulsuz eklemek, defterdeki 38
        eski satırın kimliğini değiştirir ve `dogrula()` hiçbirini tanımaz hâle gelirdi.
        Eski çekilişlerin evreni tek sembol, portföyü yok, rejimi yoktu; boş alan o
        yokluğun kaydı, bir eksiklik değil.

        `program` **hash'e girmiyor**: aynı soruyu iki program altında sormak yeni bir
        soru değildir. Program muhasebenin alanı (bütçe), kimliğin değil.
        """
        govde: dict[str, Any] = {
            "strateji": self.strateji,
            "timeframe": self.timeframe,
            "veri_sha256": self.veri_sha256,
            "izgara": {a: list(d) for a, d in sorted(self.izgara.items())},
            "secim": self.secim,
        }
        for ad, deger in (("evren", self.evren), ("portfoy", self.portfoy), ("rejim", self.rejim)):
            if deger:
                govde[ad] = deger
        return nesne_hash(govde)

    def sozluk(self) -> dict[str, Any]:
        return {
            "kimlik": self.kimlik,
            "strateji": self.strateji,
            "timeframe": self.timeframe,
            "veri_sha256": self.veri_sha256,
            "izgara": {a: list(d) for a, d in sorted(self.izgara.items())},
            "secim": self.secim,
            "gerekce": self.gerekce,
            "program": self.program,
            "evren": self.evren,
            "portfoy": self.portfoy,
            "rejim": self.rejim,
            "zaman_ms": self.zaman_ms,
            "zaman_utc": utc_str(self.zaman_ms),
        }

    @classmethod
    def kur(
        cls,
        strateji: str,
        timeframe: str,
        veri_sha256: str,
        izgara: Mapping[str, Sequence[Any]],
        gerekce: str,
        secim: str = "tepe",
        program: str = "",
        evren: str = "",
        portfoy: str = "",
        rejim: str = "",
    ) -> Hipotez:
        return cls(
            strateji=strateji,
            timeframe=timeframe,
            veri_sha256=veri_sha256,
            izgara={a: list(d) for a, d in izgara.items()},
            secim=secim,
            gerekce=gerekce,
            program=program,
            evren=evren,
            portfoy=portfoy,
            rejim=rejim,
        )


class HipotezDefteri:
    """Append-only hipotez kaydı. Satır başına bir hipotez (JSONL)."""

    __slots__ = ("yol",)

    def __init__(self, yol: str | Path = VARSAYILAN_YOL) -> None:
        self.yol = Path(yol)

    # ------------------------------------------------------------------ yazma

    def kaydet(self, hipotez: Hipotez, *, programlar: Any = None) -> int:
        """Hipotezi deftere yazar ve **kaçıncı çekiliş** olduğunu döndürür.

        Aynı kimlik zaten kayıtlıysa yeni satır yazılmaz ve mevcut sırası döner: aynı
        soruyu iki kez sormak yeni bir çekiliş değildir.

        `programlar` verilirse (bir `ProgramDefteri`) hipotezin programı **açık** ve
        bütçesi dolmamış olmak zorunda (K-051/2). Verilmemesi yalnızca Faz 4 öncesi
        kayıtların ve testlerin yolu; `sq lab hipotez-kaydet` her zaman veriyor.
        """
        mevcut = self.tumu()
        if programlar is not None:
            programlar.dogrula_cekilis(hipotez.program, mevcut)
        for sira, kayit in enumerate(mevcut, start=1):
            if kayit["kimlik"] == hipotez.kimlik:
                return sira

        self.yol.parent.mkdir(parents=True, exist_ok=True)
        satir = json.dumps(hipotez.sozluk(), ensure_ascii=False, sort_keys=True)
        with self.yol.open("a", encoding="utf-8", newline="\n") as dosya:
            dosya.write(satir + "\n")
        return len(mevcut) + 1

    # ------------------------------------------------------------------ okuma

    def tumu(self) -> list[dict[str, Any]]:
        if not self.yol.exists():
            return []
        return [
            json.loads(satir)
            for satir in self.yol.read_text(encoding="utf-8").splitlines()
            if satir.strip()
        ]

    def sayi(self) -> int:
        """Şimdiye kadar kaç farklı hipotez denendi."""
        return len(self.tumu())

    def sira(self, hipotez: Hipotez) -> int | None:
        """Bu hipotez kaçıncı sırada kayıtlı? Kayıtlı değilse `None`."""
        for sira, kayit in enumerate(self.tumu(), start=1):
            if kayit["kimlik"] == hipotez.kimlik:
                return sira
        return None

    def dogrula(self, hipotez: Hipotez) -> int:
        """Hipotezin **önceden** kayıtlı olduğunu doğrular ve sırasını döndürür.

        Kayıtlı değilse hata. Ön kaydın anlamı bu: sonucu gördükten sonra yazılan bir
        hipotez, "zaten bunu bekliyordum" demenin kaydıdır — kanıt değil.
        """
        sira = self.sira(hipotez)
        if sira is None:
            raise HipotezHatasi(
                f"hipotez önceden kaydedilmemiş: {hipotez.strateji}/{hipotez.timeframe} "
                f"({hipotez.kimlik[:12]}). Sonuç görüldükten sonra kaydedilen bir hipotez "
                "kanıt değildir (K-039)"
            )
        return sira

    def ozet(self) -> dict[str, Any]:
        kayitlar = self.tumu()
        stratejiler: dict[str, int] = {}
        programlar: dict[str, int] = {}
        for k in kayitlar:
            stratejiler[k["strateji"]] = stratejiler.get(k["strateji"], 0) + 1
            ad = k.get("program") or "(program_oncesi)"
            programlar[ad] = programlar.get(ad, 0) + 1
        return {
            "toplam": len(kayitlar),
            "strateji_basina": dict(sorted(stratejiler.items())),
            "program_basina": dict(sorted(programlar.items())),
            "ilk_ms": kayitlar[0]["zaman_ms"] if kayitlar else None,
            "son_ms": kayitlar[-1]["zaman_ms"] if kayitlar else None,
        }


__all__ = [
    "SECIM_YONTEMLERI",
    "VARSAYILAN_YOL",
    "Hipotez",
    "HipotezDefteri",
    "HipotezHatasi",
]
