"""Promotion zinciri: bir stratejinin live'a giden tek yolu. (K-010, K-019, K-032)

K-010 zinciri şöyle çiziyor:

    BACKTEST → KALİTE KONTROL → OUT-OF-SAMPLE → RİSK İNCELEMESİ
            → PAPER → LIVE ADAYI → ELLE ONAY → LIVE

`research/kapilar.py` K-019'un yedi sayısal eşiğini **değerlendirir**; bu modül o
değerlendirmeyi zincirin bir aşaması olarak **zorlar**. Aradaki fark Faz 4'ün notunda
yazılıydı: biri bir sonucun kapılardan geçip geçmediğini söyler, diğeri geçmemiş bir
stratejinin execution'a ulaşmasını engeller.

**Üç kural bu modülün tamamı:**

1. **Aşamalar sırayla geçilir.** `live`a atlamak diye bir yol yok; `ilerlet` yalnızca
   sıradaki aşamayı değerlendirir. Sıra atlanabilseydi zincir bir liste olurdu, kapı değil.
2. **Ölçülemeyen aşama geçilmiş sayılmaz.** Kanıtı olmayan aşama `olculemedi` döner ve
   zincir orada durur. K-019'un cümlesi: *"'Veri yoktu' ile 'kapıdan geçti' aynı şey
   değil."*
3. **`elle_onay` makine tarafından verilemez.** Bu aşamanın tek geçiş yolu `elle_onayla()`
   çağrısı ve o çağrı bir **not** istiyor. Otomatikleştirilmesi teknik olarak mümkün
   (her şey mümkün) ama `tests/unit/test_promotion.py` `risk/` içinde bu fonksiyonu
   çağıran başka bir yer olmadığını statik olarak kontrol ediyor.

**`risk/` neden `research/`i import etmiyor.** Canlı karar yolunun araştırma koduna
bağımlı olması, bir deney betiğindeki değişikliğin canlı davranışı etkileyebilmesi demek.
Bu yüzden kapı sonucu buraya **veri olarak** geliyor (`Kanit.kapi_sonucu`); değerlendirmeyi
CLI yapıyor ve sonucu taşıyor. Bağımlılık yönü testle korunuyor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.zaman import simdi_ms, utc_str


class Asama(StrEnum):
    """K-010'un zinciri, sırayla. Değer sırası anlamlıdır (`SIRA` listesi)."""

    YOK = "yok"
    """Hiçbir aşama geçilmemiş. Bir stratejinin başlangıç hâli."""

    BACKTEST = "backtest"
    """Yeniden üretilebilir bir backtest sonucu var (K-009: temiz ağaç, kayıtlı kimlik)."""

    KALITE_KONTROL = "kalite_kontrol"
    """Veri kalitesi ve maliyet modeli engel üretmiyor (K-006, K-021)."""

    OUT_OF_SAMPLE = "out_of_sample"
    """K-019'un yedi sayısal eşiğinin hepsi geçildi."""

    RISK_INCELEMESI = "risk_incelemesi"
    """Sonuç **risk motorundan geçerek** üretildi ve düşüşü risk limitinin altında kaldı."""

    PAPER = "paper"
    """Faz 6'nın 30 günlük kesintisiz paper koşusu tamamlandı."""

    LIVE_ADAYI = "live_adayi"
    """Makine kontrollerinin tamamı geçildi; kalan tek şey elle onay."""

    ELLE_ONAY = "elle_onay"
    """İnsan onayı verildi (K-010: bu adım kaldırılamaz)."""

    LIVE = "live"
    """Canlıda çalışmaya yetkili."""


#: Zincirin kanonik sırası. `ilerlet` bu listede yalnızca bir adım ileriye bakar.
SIRA: Final[tuple[Asama, ...]] = (
    Asama.YOK,
    Asama.BACKTEST,
    Asama.KALITE_KONTROL,
    Asama.OUT_OF_SAMPLE,
    Asama.RISK_INCELEMESI,
    Asama.PAPER,
    Asama.LIVE_ADAYI,
    Asama.ELLE_ONAY,
    Asama.LIVE,
)

#: Hangi çalışma modu hangi aşamayı şart koşuyor. Risk motoru bu eşlemeye bakıyor.
#:
#: `BACKTEST` modu promotion istemiyor: araştırma sırasında her strateji backtest edilebilir
#: olmalı, yoksa laboratuvar çalışmaz. `PAPER` risk incelemesini şart koşuyor — yani paper'a
#: giren bir strateji K-019'un yedi kapısını çoktan geçmiş olmak zorunda. `LIVE` yalnızca
#: zincirin sonunu kabul ediyor.
MOD_ESIGI: Final[dict[str, Asama]] = {
    "backtest": Asama.YOK,
    "paper": Asama.RISK_INCELEMESI,
    "live": Asama.LIVE,
}


class PromotionHatasi(ValueError):
    """Promotion zinciri kuralı ihlal edildi."""


@dataclass(frozen=True, slots=True)
class Kanit:
    """Bir aşamanın değerlendirilmesi için gereken ölçümler.

    Alanların `None` olabilmesi bilinçli ve anlamı tek: **ölçülemedi.** Varsayılan değer
    verilmiyor; bir kanıt alanının varsayılanı olsaydı eksik ölçüm dolu ölçüm gibi
    görünürdü.
    """

    config_hash: str | None = None
    sonuc_hash: str | None = None
    veri_sha256: str | None = None
    commit: str | None = None
    dirty: bool | None = None

    mutlak_engeller: tuple[str, ...] = ()
    """`Sonuc.promotion_engelleri` — dirty, data_quality_warning, gecici_maliyet_modeli."""

    kapi_sonucu: dict[str, Any] | None = None
    """`research.kapilar.degerlendir(...).sozluk()` çıktısı. K-019'un yedi eşiği."""

    risk_limit_kimligi: str | None = None
    """Sonucu üreten koşudaki risk limitlerinin hash'i. Yoksa risk motoru devrede değildi."""

    risk_max_drawdown: float | None = None
    """Risk motoruyla koşulan sonucun azami düşüşü."""

    risk_drawdown_limiti: float | None = None
    """Koşu anındaki drawdown limiti. Düşüşün bunun altında kalması şart."""

    paper_gun: float | None = None
    """Kesintisiz paper trading günü (Faz 6)."""

    paper_kesinti: int | None = None
    """Açıklanamayan kesinti sayısı. Sıfırdan büyükse PAPER aşaması geçilmez."""

    def sozluk(self) -> dict[str, Any]:
        return {
            "config_hash": self.config_hash,
            "sonuc_hash": self.sonuc_hash,
            "veri_sha256": self.veri_sha256,
            "commit": self.commit,
            "dirty": self.dirty,
            "mutlak_engeller": list(self.mutlak_engeller),
            "kapi_gecti": None if self.kapi_sonucu is None else self.kapi_sonucu.get("gecti"),
            "risk_limit_kimligi": self.risk_limit_kimligi,
            "risk_max_drawdown": self.risk_max_drawdown,
            "risk_drawdown_limiti": self.risk_drawdown_limiti,
            "paper_gun": self.paper_gun,
            "paper_kesinti": self.paper_kesinti,
        }


@dataclass(frozen=True, slots=True)
class AsamaSonucu:
    """Tek bir aşamanın makine kontrolü sonucu."""

    asama: Asama
    gecti: bool | None
    """`True` geçti, `False` kaldı, `None` **ölçülemedi**. Üçü ayrı şey."""

    gerekce: str

    @property
    def ilerleyebilir(self) -> bool:
        return self.gecti is True

    def sozluk(self) -> dict[str, Any]:
        return {"asama": str(self.asama), "gecti": self.gecti, "gerekce": self.gerekce}


#: Asgari paper günü (K-010 zincirinin PAPER aşaması, Roadmap Faz 6 bitti kriteri).
ASGARI_PAPER_GUN: Final = 30.0


def _backtest(k: Kanit) -> AsamaSonucu:
    if k.sonuc_hash is None or k.config_hash is None or k.commit is None:
        return AsamaSonucu(
            Asama.BACKTEST, None, "yeniden üretilebilir bir sonuç kaydı yok (K-009)"
        )
    if k.dirty:
        return AsamaSonucu(
            Asama.BACKTEST, False, "sonuç kirli bir working tree'den üretilmiş (K-009)"
        )
    if k.dirty is None:
        return AsamaSonucu(Asama.BACKTEST, None, "git durumu okunamadı; `dirty` bilinmiyor")
    return AsamaSonucu(Asama.BACKTEST, True, f"temiz ağaç, sonuç kaydı {k.sonuc_hash[:12]}")


def _kalite_kontrol(k: Kanit) -> AsamaSonucu:
    engeller = [e for e in k.mutlak_engeller if e != "dirty"]
    if engeller:
        return AsamaSonucu(
            Asama.KALITE_KONTROL, False, f"mutlak engel(ler): {', '.join(sorted(engeller))}"
        )
    if k.veri_sha256 is None:
        return AsamaSonucu(Asama.KALITE_KONTROL, None, "veri kimliği yok; kalite iddiası boş")
    return AsamaSonucu(Asama.KALITE_KONTROL, True, "veri kalitesi ve maliyet modeli engelsiz")


def _out_of_sample(k: Kanit) -> AsamaSonucu:
    if k.kapi_sonucu is None:
        return AsamaSonucu(Asama.OUT_OF_SAMPLE, None, "K-019 kapıları değerlendirilmemiş")
    if k.kapi_sonucu.get("gecti") is True:
        return AsamaSonucu(Asama.OUT_OF_SAMPLE, True, "K-019'un yedi eşiği geçildi")
    kalan = k.kapi_sonucu.get("kalan_kapilar") or []
    return AsamaSonucu(
        Asama.OUT_OF_SAMPLE, False, f"geçilmeyen kapı(lar): {', '.join(kalan) or 'bilinmiyor'}"
    )


def _risk_incelemesi(k: Kanit) -> AsamaSonucu:
    if k.risk_limit_kimligi is None:
        return AsamaSonucu(
            Asama.RISK_INCELEMESI,
            None,
            "sonuç risk motoru devrede değilken üretilmiş; risk incelemesi yapılamaz",
        )
    if k.risk_max_drawdown is None or k.risk_drawdown_limiti is None:
        return AsamaSonucu(Asama.RISK_INCELEMESI, None, "risk altında düşüş ölçülmemiş")
    if k.risk_max_drawdown > k.risk_drawdown_limiti:
        # **Limitin aşılması limitin çalışmadığı anlamına gelmez.** Drawdown limiti bir
        # tavan değil bir **tetikleyici**: aşıldığında kill switch'i açar ve yeni girişi
        # durdurur, ama zaten olmuş bir düşüşü geri alamaz — K-008/2 açık pozisyonları
        # kapatmayı açıkça yasaklıyor. Yani gerçekleşen düşüş limitin bir tık üstünde
        # çıkabilir ve bu doğru davranıştır.
        #
        # Kapının reddetme sebebi başka: limite **değmiş** olmak. Backtest'te kill
        # switch'i tetikleyen bir strateji, canlıda da tetikler; ve kill switch'ten çıkış
        # elle onay gerektirdiği için (K-008/4) o strateji canlıda insan müdahalesi
        # bekleyerek durur. Böyle bir stratejiyi live adayı saymak, zincirin sonunda
        # duran insanı zincirin ortasına koymak olurdu.
        return AsamaSonucu(
            Asama.RISK_INCELEMESI,
            False,
            f"risk altında düşüş {k.risk_max_drawdown:.1%} > limit "
            f"{k.risk_drawdown_limiti:.1%}: kill switch tetiklenmiş. Backtest'te kill "
            "switch'e değen strateji canlıda elle onay bekleyerek durur (K-008/4)",
        )
    return AsamaSonucu(
        Asama.RISK_INCELEMESI,
        True,
        f"risk limitleri {k.risk_limit_kimligi[:12]} altında düşüş "
        f"{k.risk_max_drawdown:.1%} ≤ {k.risk_drawdown_limiti:.1%}",
    )


def _paper(k: Kanit) -> AsamaSonucu:
    if k.paper_gun is None:
        return AsamaSonucu(Asama.PAPER, None, "paper trading koşusu yok (Faz 6)")
    if k.paper_kesinti is None:
        return AsamaSonucu(Asama.PAPER, None, "paper kesinti sayısı kaydedilmemiş")
    if k.paper_kesinti > 0:
        return AsamaSonucu(
            Asama.PAPER, False, f"{k.paper_kesinti} açıklanamayan kesinti (Roadmap Faz 6)"
        )
    if k.paper_gun < ASGARI_PAPER_GUN:
        return AsamaSonucu(
            Asama.PAPER, False, f"{k.paper_gun:.1f} gün < {ASGARI_PAPER_GUN:.0f} gün"
        )
    return AsamaSonucu(Asama.PAPER, True, f"{k.paper_gun:.1f} gün kesintisiz")


def _live_adayi(k: Kanit) -> AsamaSonucu:
    """Makine kontrollerinin tamamı geçildiyse aday. Kendi ek kontrolü yok.

    Ayrı bir aşama olmasının sebebi zincirde bir **durak** olması: "tüm makine kontrolleri
    bitti, sırada insan var" hâli kayıtta görünür olmalı. K-010'un diyagramındaki
    `LIVE ADAYI` kutusu budur.
    """
    return AsamaSonucu(Asama.LIVE_ADAYI, True, "makine kontrollerinin tamamı geçildi")


def _elle_onay(k: Kanit) -> AsamaSonucu:
    """**Her zaman `None`.** Makine bu aşamayı geçiremez (K-010)."""
    return AsamaSonucu(
        Asama.ELLE_ONAY,
        None,
        "elle onay bekliyor: bu aşama makine tarafından geçilemez (K-010). "
        "`sq promotion onayla <strateji> --not '<gerekçe>'`",
    )


def _live(k: Kanit) -> AsamaSonucu:
    """Elle onaydan sonra otomatik. Onay verildikten sonra ayrı bir kapı yok."""
    return AsamaSonucu(Asama.LIVE, True, "elle onay verildi; canlıya yetkili")


#: Aşama → kontrol fonksiyonu. `YOK` başlangıç hâli, kontrolü yok.
KONTROLLER: Final[dict[Asama, Any]] = {
    Asama.BACKTEST: _backtest,
    Asama.KALITE_KONTROL: _kalite_kontrol,
    Asama.OUT_OF_SAMPLE: _out_of_sample,
    Asama.RISK_INCELEMESI: _risk_incelemesi,
    Asama.PAPER: _paper,
    Asama.LIVE_ADAYI: _live_adayi,
    Asama.ELLE_ONAY: _elle_onay,
    Asama.LIVE: _live,
}


def sonraki(asama: Asama) -> Asama | None:
    """Zincirde bir sonraki aşama; son aşamadaysa `None`."""
    i = SIRA.index(asama)
    return None if i + 1 >= len(SIRA) else SIRA[i + 1]


def yeterli_mi(asama: Asama, gereken: Asama) -> bool:
    """`asama`, `gereken` aşamaya eşit veya ondan ileride mi?"""
    return SIRA.index(asama) >= SIRA.index(gereken)


@dataclass
class PromotionKaydi:
    """Bir stratejinin promotion geçmişi. Append-only: aşama kaydı silinmez."""

    strateji: str
    asama: Asama = Asama.YOK
    gecmis: list[dict[str, Any]] = field(default_factory=list)

    def ilerlet(self, kanit: Kanit) -> AsamaSonucu:
        """Yalnızca **sıradaki** aşamayı değerlendirir ve geçtiyse ilerletir.

        Tek adım ilerlemesi kasıtlı: bir çağrıda zinciri sonuna kadar koşturmak, araya
        giren elle onay adımını "geçilecek bir engel" hâline getirirdi. Zincir adım adım
        tırmanılır, koşulmaz.
        """
        hedef = sonraki(self.asama)
        if hedef is None:
            return AsamaSonucu(self.asama, True, "zincirin sonunda")
        if hedef is Asama.ELLE_ONAY:
            return _elle_onay(kanit)

        sonuc = KONTROLLER[hedef](kanit)
        self._kaydet(sonuc, kanit)
        if sonuc.ilerleyebilir:
            self.asama = hedef
        return sonuc

    def elle_onayla(self, not_metni: str, *, kanit: Kanit | None = None) -> AsamaSonucu:
        """K-010'un kaldırılamaz adımı. **Yalnızca insan çağırır.**

        İki kontrol var ve ikisi de bilinçli:

        - Strateji `live_adayi` aşamasında olmak zorunda. Onayı zincirin ortasına vermek,
          atlanan aşamaları onaylanmış göstermek olurdu.
        - Not zorunlu ve en az 10 karakter. "ok" yazarak geçilebilen bir onay, bir tık;
          gerekçe yazmak zorunda olmak, kararın kendisi.
        """
        if self.asama is not Asama.LIVE_ADAYI:
            raise PromotionHatasi(
                f"elle onay yalnızca `live_adayi` aşamasında verilebilir; strateji "
                f"{self.strateji!r} şu an {self.asama}. Atlanan aşamalar: "
                f"{', '.join(str(a) for a in self.eksik_asamalar())}"
            )
        metin = not_metni.strip()
        if len(metin) < 10:
            raise PromotionHatasi(
                "elle onay bir gerekçe ister (≥10 karakter): gerekçesiz onay bir tıktır, "
                "karar değil (K-010)"
            )
        k = kanit or Kanit()
        sonuc = AsamaSonucu(Asama.ELLE_ONAY, True, f"elle onay: {metin}")
        self._kaydet(sonuc, k)
        self.asama = Asama.ELLE_ONAY
        # Elle onaydan sonra `live` ayrı bir kapı değil; onay verildiyse canlıya yetkili.
        self._kaydet(_live(k), k)
        self.asama = Asama.LIVE
        return sonuc

    def eksik_asamalar(self) -> list[Asama]:
        """Bu stratejinin henüz geçmediği aşamalar."""
        i = SIRA.index(self.asama)
        return list(SIRA[i + 1 :])

    def _kaydet(self, sonuc: AsamaSonucu, kanit: Kanit) -> None:
        self.gecmis.append(
            {
                "zaman_ms": simdi_ms(),
                "zaman_utc": utc_str(simdi_ms()),
                "onceki_asama": str(self.asama),
                **sonuc.sozluk(),
                "kanit": kanit.sozluk(),
            }
        )

    def sozluk(self) -> dict[str, Any]:
        return {
            "strateji": self.strateji,
            "asama": str(self.asama),
            "eksik_asamalar": [str(a) for a in self.eksik_asamalar()],
            "canliya_yetkili": self.asama is Asama.LIVE,
            "gecmis": self.gecmis,
        }

    @classmethod
    def yukle(cls, kayit: dict[str, Any]) -> PromotionKaydi:
        return cls(
            strateji=str(kayit["strateji"]),
            asama=Asama(kayit.get("asama", Asama.YOK)),
            gecmis=list(kayit.get("gecmis", [])),
        )


class PromotionDefteri:
    """Promotion kayıtlarının kalıcı deposu. Strateji başına bir JSON dosyası.

    Ayrı dosyalar, tek bir dizin indeksi değil: bir stratejinin kaydının bozulması
    diğerlerini etkilememeli, ve bir kaydın elle okunması `cat` ile mümkün olmalı —
    K-010'un korumaya çalıştığı şey sabırsızlık, ve sabırsız insan anlamadığı bir formatı
    atlar.
    """

    def __init__(self, kok: str | Path = "runs/promotion") -> None:
        self.kok = Path(kok)
        self.kok.mkdir(parents=True, exist_ok=True)

    def yol(self, strateji: str) -> Path:
        return self.kok / f"{strateji}.json"

    def oku(self, strateji: str) -> PromotionKaydi:
        """Kaydı okur; yoksa `YOK` aşamasında yeni bir kayıt döndürür.

        Eksik dosyanın "hiçbir aşama geçilmemiş" anlamına gelmesi güvenli yön: kaydı
        silmek bir stratejiyi live'a değil başa götürür.
        """
        p = self.yol(strateji)
        if not p.exists():
            return PromotionKaydi(strateji=strateji)
        return PromotionKaydi.yukle(json.loads(p.read_text(encoding="utf-8")))

    def yaz(self, kayit: PromotionKaydi) -> Path:
        p = self.yol(kayit.strateji)
        p.write_text(
            json.dumps(kayit.sozluk(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return p

    def hepsi(self) -> list[PromotionKaydi]:
        return [
            PromotionKaydi.yukle(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(self.kok.glob("*.json"))
        ]


__all__ = [
    "ASGARI_PAPER_GUN",
    "KONTROLLER",
    "MOD_ESIGI",
    "SIRA",
    "Asama",
    "AsamaSonucu",
    "Kanit",
    "PromotionDefteri",
    "PromotionHatasi",
    "PromotionKaydi",
    "sonraki",
    "yeterli_mi",
]
