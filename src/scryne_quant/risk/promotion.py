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

**Kayıt zinciri ve audit bağı (K-082, İz A P1/P2).** `PromotionKaydi.gecmis`in her satırı
`onceki_hash` + `satir_hash` taşır (audit defterinin kalıbı: içerik + önceki satırın hash'i,
`nesne_hash` ile kanonik JSON; ilk satırın öncekisi `KOK_HASH`). Hash'e giren içerik satırın
kendisi **eksi** `onceki_hash`/`satir_hash`/`audit_hash` alanları, artı stratejinin adı (bir
stratejinin zinciri başka bir dosyaya taşınamaz). `PromotionKaydi.yukle()` zinciri baştan
doğrular ve `asama`nın son geçilen satırla tutarlı olmasını ister; eksik/değişmiş/yeniden
sıralanmış satır ya da zincirsiz (K-082 öncesi) biçim → `PromotionHatasi`, **fail closed**.
Eski kayıt sessizce kabul edilmez: `PromotionDefteri.zincirle()` açık göçtür. Her satır ayrıca
audit defterine (`runs/audit.sqlite`, `OlayTuru.PROMOTION`) yazılır; audit satırının hash'i
promotion satırına `audit_hash` olarak döner, audit gövdesi promotion `satir_hash`ini taşır —
iki yönlü referans. Son satırların silinmesi (kısaltma) dosya içinden fark edilemez; onu
audit çapraz kontrolü yakalar (`audit_ile_dogrula`).

**`risk/` neden `research/`i import etmiyor.** Canlı karar yolunun araştırma koduna
bağımlı olması, bir deney betiğindeki değişikliğin canlı davranışı etkileyebilmesi demek.
Bu yüzden kapı sonucu buraya **veri olarak** geliyor (`Kanit.kapi_sonucu`); değerlendirmeyi
CLI yapıyor ve sonucu taşıyor. Bağımlılık yönü testle korunuyor.

**İki protokol, tek zincir (K-126).** `Kanit.protokol` yalnızca `out_of_sample` aşamasının
**ekonomik/istatistiksel ölçütünü** seçer: `alfa` → `ZORUNLU_KAPILAR` (K-119'un 12 kapısı),
`rypp` → `RYPP_KOSULLARI` (K-125'in 13 koşulu) + B-3 bağımsız doğrulaması. Geri kalan her şey
iki protokolde **aynı** ve protokolden bağımsız sistem değişmezidir: yeniden üretilebilirlik ve
temiz ağaç (`backtest`), veri kalitesi ve maliyet modeli (`kalite_kontrol`), K-039 çekiliş sayımı
(`hipotez_sirasi`, iki yolda da `out_of_sample`ın ön şartı), risk motoru altında düşüş
(`risk_incelemesi`), 30 gün paper, `elle_onay`. RYPP bu aşamaların hiçbirini atlamaz. Kanıt
kurulurken protokoller karıştırılamaz (alfa kanıtı RYPP sonucu, RYPP kanıtı alfa kapı sonucu
taşıyamaz); `out_of_sample`ı bir protokolle geçen strateji sonraki aşamalarda başka protokolün
kanıtıyla ilerletilemez. Protokol her satırın `kanit`ine, dolayısıyla zincir hash'ine ve audit'e
girer; K-126 öncesi satırlarda alan yok ve anlamı `alfa`dır.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.risk.audit import KOK_HASH, Defter, Olay, OlayTuru

#: Zincir hash'ine **girmeyen** alanlar: hash'in kendisi ve audit referansı. Kanonikleştirme
#: `nesne_hash` (sort_keys, ensure_ascii=False, ayırıcısız) — audit ile aynı.
HASH_DISI: Final[frozenset[str]] = frozenset({"onceki_hash", "satir_hash", "audit_hash"})

#: `out_of_sample` aşamasının istediği kapıların **tam** listesi: K-019 yedi + K-113 bir + K-054
#: dört (K-118). Kanıtta bunlardan biri yoksa aşama geçilmez. Önceden yalnız kanıttaki `gecti`
#: okunuyordu ve tek sembollü `sq lab kapilar` çıktısı K-054'ün dört kapısını hiç taşımıyordu:
#: promotion, K-054'ü uygulamadan ilerleyebilirdi. `risk/` `research/`i import edemediği için
#: liste burada; `research.kapilar` + `research.kapilar_v2` ile eşitliğini test korur.
ZORUNLU_KAPILAR: Final[frozenset[str]] = frozenset({
    "oos_suresi", "oos_sharpe", "oos_is_orani", "wf_katman_basari", "parametre_kararliligi",
    "asgari_islem", "max_drawdown", "stres_dayanikliligi",
    "pbo", "parametre_perturbasyonu", "rejim_kararliligi", "evren_dayanikliligi",
})


class Protokol(StrEnum):
    """Kanıtın hangi promotion protokolüne göre üretildiği (K-126)."""

    ALFA = "alfa"
    """K-019/K-113/K-054 → K-119: 12 kapı. K-126 öncesi bütün kanıtlar bu protokoldür."""

    RYPP = "rypp"
    """K-125: Risk Yönetimli Promotion Protokolü (`research/risk_protokolu.py`)."""


#: RYPP koşulları, `research.risk_protokolu.degerlendir`in karar sırasıyla (K-125). `risk/`
#: `research/`i import edemediği için kopya; eşitliğini `test_promotion_rypp.py` korur.
#: Yeterlilik: biri sağlanmazsa INCONCLUSIVE. Nokta: biri kalırsa FAIL. Belirsizlik: nokta
#: koşulları geçtiği hâlde bootstrap yetmezse INCONCLUSIVE.
RYPP_YETERLILIK: Final[tuple[str, ...]] = ("oos_suresi", "kiyas_epizot", "plasebo_var", "stres_var")
RYPP_NOKTA: Final[tuple[str, ...]] = (
    "P1_dusus_azaltimi", "P2a_getiri_korunumu", "P2b_verimlilik", "P3_plasebo",
    "S1_maliyet_stresi", "R1_baslangic", "R2_alt_donem", "R3_tek_olay",
)
RYPP_BELIRSIZLIK: Final[tuple[str, ...]] = ("B_bootstrap",)
RYPP_KOSULLARI: Final[frozenset[str]] = frozenset(
    (*RYPP_YETERLILIK, *RYPP_NOKTA, *RYPP_BELIRSIZLIK)
)

#: K-125 eşiklerinin değerleri. Kanıt `esikler` alanında bunlardan farklı bir değer taşıyorsa
#: (gevşetilmiş kodla üretilmiş) kabul edilmez. Kopya; `risk_protokolu.ESIKLER` ile eşitliğini
#: test korur.
RYPP_ESIKLER: Final[dict[str, float]] = {
    "asgari_oos_yil": 2.0, "asgari_epizot": 2, "asgari_dd_azaltim": 0.25,
    "asgari_getiri_koruma": 0.5, "alfa": 0.05, "asgari_baslangic_orani": 0.70,
    "epizot_iyilesme": 0.90, "asgari_bootstrap_p": 0.80,
}

#: Üç değerli hüküm → RYPP etiketi. `True` PASS, `False` FAIL, `None` INCONCLUSIVE;
#: `AsamaSonucu.gecti` ile aynı anlam ("ölçülemedi/karara yetmedi" ≠ "kaldı" ≠ "geçti").
RYPP_ETIKET: Final[dict[bool | None, str]] = {True: "PASS", False: "FAIL", None: "INCONCLUSIVE"}


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
#: `GOZLEM` de promotion istemiyor ve bu bir gevşetme **değil** (K-035): gözlem koşusunun
#: ürettiği hiçbir kayıt promotion kanıtı olamaz — `Kanit.__post_init__` gözlem modundan
#: gelen paper kanıtını kurulmadan reddeder. Yani gözlem modu zinciri atlamıyor; zincire
#: hiç girmiyor.
MOD_ESIGI: Final[dict[str, Asama]] = {
    "backtest": Asama.YOK,
    "gozlem": Asama.YOK,
    "paper": Asama.RISK_INCELEMESI,
    # K-114: shadow'un ürettiği rapor elle onayın girdisidir; onu yalnızca makine
    # kontrollerinin tamamını geçmiş (`LIVE_ADAYI`) bir strateji üretebilir.
    "shadow": Asama.LIVE_ADAYI,
    "live": Asama.LIVE,
    # K-115: mikro canlı pilot. `gozlem`in gerçek paradaki karşılığı: promotion istemiyor,
    # ve aynı sebeple zincire hiç girmiyor (`Kanit.paper_mod` yalnız `paper`). Gerçek parayı
    # sınırlayan promotion değil, kodda sabit tavanlar (`canli_kapi.PILOT_*`) + elle onay.
    "pilot": Asama.YOK,
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
    """Kapı değerlendirmesi (`KapiSonucu.sozluk()` biçimi). `kapilar` alanı `ZORUNLU_KAPILAR`ın
    tamamını taşımalı (K-118); birden çok kayıt CLI'da birleştirilir."""

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

    hipotez_sirasi: int | None = None
    """Bu strateji **kaçıncı** denenen hipotezdi (K-039). `None` = kaydedilmemiş.

    Bir eşik değil, okunması zorunlu bir bağlam — ve ölçülemediğinde `out_of_sample`
    aşaması geçilmiş sayılmıyor. Sebep: K-019'un yedi kapısı strateji başına çalışıyor ve
    hiçbiri "bu kaçıncı çekilişti" sorusunu sormuyor. Yeterince çok deneyen biri, eşiğe
    hiç dokunmadan, K-018'in 'sayısal eşik esnetilemez' kuralını deler."""

    hipotez_toplami: int | None = None
    """Defterdeki toplam hipotez sayısı. `hipotez_sirasi` ile birlikte okunur."""

    paper_mod: str | None = None
    """Paper kanıtını üreten koşunun **modu**. `paper` dışındaki bir mod kanıt üretemez.

    K-035'in ikinci maddesinin zorlaması burada ve `__post_init__`te. Gözlem modu
    (`gozlem`) promotion geçmemiş bir stratejiyi canlı veride koşturabiliyor; o koşunun
    30 gün sürmesi PAPER aşamasını geçirseydi, gözlem modu zinciri atlamanın en kolay yolu
    olurdu — yani K-018'in "eşik esnetilemez" kuralı bir mod adı yazarak delinirdi.
    """

    protokol: Protokol = Protokol.ALFA
    """Kanıtın promotion protokolü (K-126). Varsayılan `alfa`: K-126 öncesi davranışın aynısı
    ve en katı yol (12 kapının tamamını ister); varsayılan hiçbir ölçümü dolu göstermez."""

    rypp_sonucu: dict[str, Any] | None = None
    """RYPP değerlendirmesi (`RyppSonucu.sozluk()` biçimi): donmuş adayın OOS koşusu. Yalnız
    `rypp` kanıtında. Hüküm satırlardan **yeniden türetilir** (`rypp_hukmu`)."""

    bagimsiz_dogrulama: dict[str, Any] | None = None
    """B-3 bağımsız doğrulaması (K-125 §5): aynı donmuş kuralın, OOS'una bu projede hiç
    bakılmamış veride RYPP değerlendirmesi + `veri_sha256`. Yoksa RYPP PASS üretilemez."""

    bagimsiz_vintage: dict[str, Any] | None = None
    """B-3 vintage eşi (K-128): aynı donmuş kuralın, birincil bağımsız verinin **başka bir
    revizyonunda** (French 201705) değerlendirmesi. Birincil set PIT değil (revize edilir);
    sonuç revizyona dayanıklı değilse PASS yok (`vintage_hukmu`)."""

    rypp_aile_sayisi: int | None = None
    """P3'ün k'sı, **promotion tarafında** yeniden okunmuş hâli (K-128): kanıttaki
    `aile.program` araştırma programının açılışta yazılan bütçesi (`azami_cekilis`). Kanıttaki k
    ile aynı olmak zorunda; farklıysa kanıt kurulmaz, yoksa `out_of_sample` ölçülemedi. `risk/`
    program defterini okumaz (`research/` bağımlılığı); okumayı CLI yapar."""

    def __post_init__(self) -> None:
        """Kanıtın **kurulmasını** engelleyen kontroller. Değerlendirmeye bırakılmadı.

        `_paper` içinde `gecti=False` döndürmek de bir reddetme olurdu, ama farklı bir
        şey: "ölçüldü ve yetmedi" ile "bu ölçüm bu koşudan alınamaz" aynı şey değil.
        İkincisi bir kanıt hatasıdır ve sessizce bir kapı sonucuna dönüşmemeli (K-035/2).
        Protokol karışması ve kendi içinde tutarsız RYPP kanıtı da bu türdendir (K-126).
        """
        try:
            object.__setattr__(self, "protokol", Protokol(self.protokol))
        except ValueError:
            raise PromotionHatasi(f"bilinmeyen promotion protokolü: {self.protokol!r}") from None
        if self.protokol is Protokol.ALFA and (
            self.rypp_sonucu is not None or self.bagimsiz_dogrulama is not None
            or self.bagimsiz_vintage is not None
        ):
            raise PromotionHatasi(
                "alfa kanıtı RYPP değerlendirmesi taşıyamaz: RYPP sonucu alfa kapısı yerine "
                "geçmez (K-126, protokol karışması)"
            )
        if self.protokol is Protokol.RYPP:
            if self.kapi_sonucu is not None:
                raise PromotionHatasi(
                    "RYPP kanıtı alfa kapı sonucu taşıyamaz: RYPP yolu alfa kapılarını "
                    "değerlendirmez, alfa kapıları RYPP koşulu sayılmaz (K-126, protokol karışması)"
                )
            # Yapısal hatalar (bilinmeyen koşul, farklı eşik, raporlanan durum ≠ satırlar,
            # ana OOS verisiyle aynı "bağımsız" veri) burada, kurulurken patlar.
            if self.rypp_sonucu is not None:
                rypp_hukmu(self.rypp_sonucu)
            vintage_hukmu(self.bagimsiz_dogrulama, self.bagimsiz_vintage, self.veri_sha256)
            self._aile_tutarliligi()

        if self.paper_gun is None and self.paper_kesinti is None:
            return
        if self.paper_mod != "paper":
            raise PromotionHatasi(
                f"paper kanıtı yalnızca `paper` modundan gelebilir, verilen: "
                f"{self.paper_mod!r}. Gözlem koşusu promotion kanıtı üretmez (K-035/2)"
            )

    def _aile_tutarliligi(self) -> None:
        """k her yerde aynı olmalı (K-127/K-128): ana kanıt (araştırmanın P3'te kullandığı),
        bağımsız doğrulama ve vintage eşi (aynı çekilişin parçaları, aynı program) ve
        promotion'ın program defterinden okuduğu bütçe."""
        if self.rypp_aile_sayisi is not None and (
            type(self.rypp_aile_sayisi) is not int or self.rypp_aile_sayisi < 1
        ):
            raise PromotionHatasi(
                f"rypp_aile_sayisi ≥ 1 tam sayı olmalı, verilen: {self.rypp_aile_sayisi!r}"
            )
        if self.rypp_sonucu is None:
            return
        k, program = rypp_ailesi(self.rypp_sonucu)
        if self.rypp_aile_sayisi is not None and self.rypp_aile_sayisi != k:
            raise PromotionHatasi(
                f"P3'ün k'sı uyuşmuyor: kanıt k={k}, `{program}` programının bütçesi "
                f"{self.rypp_aile_sayisi} — k promotion'da seçilemez (K-128)"
            )
        for ne, govde in (("B-3 bağımsız doğrulama", self.bagimsiz_dogrulama),
                          ("B-3 vintage eşi", self.bagimsiz_vintage)):
            if govde is None:
                continue
            aile_b = rypp_ailesi(govde, ne=ne)
            if aile_b != (k, program):
                raise PromotionHatasi(
                    f"{ne} (k, program)={aile_b}, ana kanıt {(k, program)}: aynı çekilişin "
                    "parçası, aynı k ile değerlendirilmeli (K-127/K-128)"
                )

    def sozluk(self) -> dict[str, Any]:
        """Satıra (dolayısıyla zincir hash'ine ve audit'e) giren kanıt özeti. `protokol` her
        satırda; RYPP'ye özgü alanlar yalnız RYPP kanıtında — alfa satırının geri kalanı K-126
        öncesiyle aynı. Tam RYPP gövdeleri hash'leriyle bağlanır (kanıt dosyası sonradan
        değiştirilirse fark edilir)."""
        d = self._alfa_sozlugu()
        d["protokol"] = str(self.protokol)
        if self.protokol is Protokol.RYPP:
            r, b, v = self.rypp_sonucu, self.bagimsiz_dogrulama, self.bagimsiz_vintage
            d |= {
                "rypp_durum": None if r is None else r.get("durum"),
                "rypp_hash": None if r is None else nesne_hash(r),
                "rypp_aile_sayisi": self.rypp_aile_sayisi,
                "bagimsiz_durum": None if b is None else b.get("durum"),
                "bagimsiz_veri_sha256": None if b is None else b.get("veri_sha256"),
                "bagimsiz_hash": None if b is None else nesne_hash(b),
                "vintage_durum": None if v is None else v.get("durum"),
                "vintage_veri_sha256": None if v is None else v.get("veri_sha256"),
                "vintage_hash": None if v is None else nesne_hash(v),
            }
        return d

    def _alfa_sozlugu(self) -> dict[str, Any]:
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
            "paper_mod": self.paper_mod,
            "hipotez_sirasi": self.hipotez_sirasi,
            "hipotez_toplami": self.hipotez_toplami,
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


def _rypp_satirlari(sonuc: dict[str, Any], ne: str) -> dict[str, Any]:
    """RYPP gövdesinin koşul satırları `{ad: gecti}`. Yapısal hata → `PromotionHatasi`."""
    esikler = sonuc.get("esikler")
    if not isinstance(esikler, dict) or {
        a: (v or {}).get("deger") for a, v in esikler.items()
    } != RYPP_ESIKLER:
        raise PromotionHatasi(
            f"{ne}: eşikler yok ya da K-125'tekinden farklı — RYPP eşiği gevşetilemez, farklı "
            "eşikle üretilmiş kanıt kabul edilmez (K-125)"
        )
    satirlar: dict[str, Any] = {}
    for s in sonuc.get("kosullar") or []:
        ad = (s or {}).get("ad")
        if ad not in RYPP_KOSULLARI:
            raise PromotionHatasi(f"{ne}: bilinmeyen koşul {ad!r} — protokol karışması (K-126)")
        if ad in satirlar:
            raise PromotionHatasi(f"{ne}: {ad} koşulu iki kez var — hangisinin kanıt olduğu "
                                  "tahmin edilmez")
        satirlar[ad] = s.get("gecti")
    return satirlar


def rypp_ailesi(sonuc: dict[str, Any], *, ne: str = "RYPP kanıtı") -> tuple[int, str]:
    """Kanıttaki P3 çoklu test bağlamı `(k, program)`; yapısal hata → `PromotionHatasi`.

    K-128: k, adayın ait olduğu RYPP araştırma programının **açılışta** yazılan bütçesidir
    (`azami_cekilis`): önceden sabit, sonuçtan bağımsız ve programın bütün çekilişleri için aynı
    (aile içi Bonferroni tam kontrol; K-127'nin birikimli sayımı aile hatasını α·H(n)'e kadar
    kaçırıyordu). Promotion k'yı seçmez, program defterinden okuyup doğrular.
    `aile.persentil` = 1 − α/k ve P3 satırının kullandığı `persentil` aynı olmalı (araştırmanın
    P3'te gerçekten bu k'yı kullandığı). Tip katı: `bool`, `float`, `str` k değildir.
    """
    aile = sonuc.get("aile")
    if not isinstance(aile, dict):
        raise PromotionHatasi(f"{ne}: `aile` (P3'ün k'sı) yok — k yeniden sayılamaz (K-127)")
    k, program = aile.get("sayi"), aile.get("program")
    if type(k) is not int or k < 1:
        raise PromotionHatasi(f"{ne}: k ≥ 1 tam sayı olmalı, verilen: {k!r} (K-127)")
    if not isinstance(program, str) or not program:
        raise PromotionHatasi(
            f"{ne}: aile.program yok — k'nın kaynağı (program bütçesi) doğrulanamaz (K-128)"
        )
    beklenen = 1 - RYPP_ESIKLER["alfa"] / k
    if aile.get("persentil") != beklenen:
        raise PromotionHatasi(f"{ne}: aile.persentil {aile.get('persentil')!r} ≠ 1 − α/k")
    for satir_ in sonuc.get("kosullar") or []:
        if (satir_ or {}).get("ad") == "P3_plasebo" and satir_.get("persentil") != beklenen:
            raise PromotionHatasi(
                f"{ne}: P3 persentil {satir_.get('persentil')!r} ile uygulanmış, kanıt k={k} "
                "diyor (1 − α/k farklı) — araştırmanın k'sı ile kanıtın k'sı aynı değil (K-127)"
            )
    return k, program


def _gecti(v: Any) -> bool:
    return v is True


def _kaldi(v: Any) -> bool:
    return v is False


def rypp_hukmu(sonuc: dict[str, Any], *, ne: str = "RYPP kanıtı") -> tuple[bool | None, str]:
    """RYPP değerlendirmesinin hükmü, raporlanan `durum`a değil **satırlara** bakarak (K-126).

    `True` PASS, `False` FAIL, `None` INCONCLUSIVE. Sıra `risk_protokolu.degerlendir`inkiyle
    aynı: (1) yeterlilik satırlarından biri yok ya da geçmedi → INCONCLUSIVE; (2) nokta
    koşullarından biri **kaldı** → FAIL; ölçülmemiş nokta koşulu → INCONCLUSIVE; (3) bootstrap
    yok ya da geçmedi → INCONCLUSIVE; (4) hepsi → PASS. Yalnız `gecti is True` geçer: eksik
    satır, `None`, `1`, `"true"` geçmiş sayılmaz. Türetilen hüküm raporlanan `durum`la
    uyuşmazsa kanıt kendi içinde tutarsızdır → `PromotionHatasi` (fail closed).
    """
    satirlar = _rypp_satirlari(sonuc, ne)
    rypp_ailesi(sonuc, ne=ne)
    yetersiz = [a for a in RYPP_YETERLILIK if not _gecti(satirlar.get(a))]
    kalan = [a for a in RYPP_NOKTA if _kaldi(satirlar.get(a))]
    olcusuz = [a for a in RYPP_NOKTA
               if not (_gecti(satirlar.get(a)) or _kaldi(satirlar.get(a)))]
    hukum: bool | None
    if yetersiz:
        hukum, gerekce = None, f"veri yeterliliği sağlanmadı: {', '.join(yetersiz)}"
    elif kalan:
        hukum, gerekce = False, f"kalan koşul(lar): {', '.join(kalan)}"
    elif olcusuz:
        hukum, gerekce = None, f"ölçülmemiş koşul(lar): {', '.join(olcusuz)}"
    elif not _gecti(satirlar.get("B_bootstrap")):
        hukum, gerekce = None, "bootstrap güven aralığı karara yetmiyor ya da ölçülmedi"
    else:
        hukum, gerekce = True, f"{len(RYPP_KOSULLARI)} koşulun tamamı geçti"
    rapor = sonuc.get("durum")
    if rapor != RYPP_ETIKET[hukum]:
        raise PromotionHatasi(
            f"{ne} kendi içinde tutarsız: raporlanan durum {rapor!r}, satırlardan türeyen "
            f"{RYPP_ETIKET[hukum]} (fail closed)"
        )
    return hukum, gerekce


def bagimsiz_hukmu(
    bagimsiz: dict[str, Any] | None, ana_veri_sha256: str | None
) -> tuple[bool | None, str]:
    """B-3 bağımsız doğrulamasının ana hükme katkısı (K-125 §5, K-126).

    Kripto OOS'una 18 çekiliş baktı; o pencere risk-off tasarımı için kirli. K-125 §5: "PASS
    için bağımsız veride en az FAIL olmamalı". Buradan:

    - **Yok → `None` (INCONCLUSIVE), FAIL değil.** Donmuş aday bağımsız veride ölçülmedi;
      yanlışlanmadı da. FAIL "ölçüldü ve kaldı" demektir ve K-125 §5.3'e göre yeni araştırma
      döngüsü açtırır; burada ölçülmüş bir başarısızlık yok, eksik kanıt var. INCONCLUSIVE'in
      tanımı (eşik gevşemez, veri beklenir) B-3'ün durumunun ta kendisi.
    - Kimliği (`veri_sha256`) yok → `None`: bağımsızlık kanıtlanamıyor. Ana OOS verisiyle aynı
      kimlik → `PromotionHatasi`: kirli veri bağımsız sayılamaz.
    - Bağımsız veride FAIL → `False`.
    - Bağımsız veride **veri yeterliliği** sağlanmadıysa → `None`. "En az FAIL olmamalı"
      kuralı yeterliliği sağlanmamış bir INCONCLUSIVE'e uygulanırsa, çok kısa bir seri vererek
      B-3 boşa düşürülebilirdi; yetersiz veri "veri yok"la aynıdır.
    - Nokta koşullarından biri ölçülmemişse → `None` (aynı gerekçe: ölçülmemiş = FAIL-olmadığı
      gösterilmemiş).
    - Yeterli veride, bütün nokta koşulları ölçülüp geçmişken PASS ya da (yalnız bootstrap
      belirsizliğinden) INCONCLUSIVE → `True`: K-125 §5'in "FAIL olmamalı" şartı sağlandı.
    """
    if bagimsiz is None:
        return None, ("B-3: bağımsız doğrulama yok — kripto OOS'u kirli (18 çekiliş), tek başına "
                      "PASS üretemez")
    veri = bagimsiz.get("veri_sha256")
    if not veri:
        return None, "B-3: bağımsız verinin kimliği (veri_sha256) yok; bağımsızlık kanıtlanamıyor"
    if veri == ana_veri_sha256:
        raise PromotionHatasi(
            "B-3: bağımsız doğrulama ana OOS ile aynı veride (veri_sha256 aynı) — kirli veri "
            "bağımsız sayılmaz"
        )
    hukum, gerekce = rypp_hukmu(bagimsiz, ne="B-3 bağımsız doğrulama")
    if hukum is False:
        return False, f"B-3 bağımsız veride FAIL ({gerekce})"
    satirlar = _rypp_satirlari(bagimsiz, "B-3 bağımsız doğrulama")
    if not all(_gecti(satirlar.get(a)) for a in RYPP_YETERLILIK):
        return None, f"B-3: bağımsız veri yetersiz ({gerekce}); yetersiz veri yok sayılır"
    if not all(_gecti(satirlar.get(a)) for a in RYPP_NOKTA):
        # Ölçülmemiş nokta koşulu da "FAIL değil" sayılamaz: P3'ü hiç koşmadan bağımsız
        # doğrulamayı geçmek mümkün olurdu. Tolere edilen tek belirsizlik bootstrap'tır.
        return None, f"B-3: bağımsız veride ölçülmemiş koşul ({gerekce})"
    return True, f"B-3 bağımsız veride {RYPP_ETIKET[hukum]} (FAIL değil, K-125 §5)"


def vintage_hukmu(
    bagimsiz: dict[str, Any] | None, vintage: dict[str, Any] | None, ana_veri_sha256: str | None
) -> tuple[bool | None, str]:
    """B-3'ün vintage dayanıklılığı (K-128). Birincil bağımsız veri PIT değil (French her ay
    geçmişi yeniden üretir); aynı donmuş kural başka bir revizyonda da değerlendirilir.

    Her biri `bagimsiz_hukmu` ile (yapıldı-ve-FAIL-değil / FAIL / yapılmadı). Birleşim:
    ikisi de geçti → `True`; ikisi de FAIL → `False`; biri FAIL öteki geçti → `None`
    (revizyona duyarlı: FAIL ölçülmüş ama tutarlı değil); biri FAIL öteki yapılmadı → `False`;
    aksi hâlde (biri yok/yapılmadı) → `None`. İki gövde aynı veride olamaz.
    """
    h_b, g_b = bagimsiz_hukmu(bagimsiz, ana_veri_sha256)
    if vintage is None:
        return (False, g_b) if h_b is False else (None, f"{g_b}; B-3 vintage eşi yok (K-128)")
    if bagimsiz is not None and vintage.get("veri_sha256") == bagimsiz.get("veri_sha256"):
        raise PromotionHatasi("B-3 vintage eşi birincil bağımsız veriyle aynı veride (K-128)")
    h_v, g_v = bagimsiz_hukmu(vintage, ana_veri_sha256)
    g = f"{g_b}; vintage eşi: {g_v}"
    if h_b is True and h_v is True:
        return True, g
    if h_b is False and h_v is False:
        return False, g
    if {h_b, h_v} == {True, False}:
        return None, f"{g} — revizyona duyarlı (iki vintage farklı hüküm, K-128)"
    if False in (h_b, h_v):
        return False, g
    return None, g


def _ve(*hukumler: bool | None) -> bool | None:
    """Üç değerli VE: bir `False` → `False`; yoksa bir `None` → `None`; hepsi `True` → `True`."""
    if any(h is False for h in hukumler):
        return False
    if any(h is None for h in hukumler):
        return None
    return True


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
    if k.protokol is Protokol.RYPP:
        return _out_of_sample_rypp(k)
    if k.kapi_sonucu is None:
        return AsamaSonucu(Asama.OUT_OF_SAMPLE, None, "K-019 kapıları değerlendirilmemiş")

    # Kaçıncı çekiliş olduğu **ölçülemediyse** aşama geçilmiş sayılmaz (K-039). Aynı
    # kural volatilite guard'ında ve K-019'un her kapısında var: "veri yoktu" ile
    # "geçti" aynı şey değil. Burada özellikle keskin, çünkü kaydedilmemiş bir çekiliş
    # sayısı, geçilen kapının ne anlama geldiğini de bilinmez yapar.
    if k.hipotez_sirasi is None:
        return AsamaSonucu(
            Asama.OUT_OF_SAMPLE,
            None,
            "hipotez defterinde kayıt yok: bu stratejinin kaçıncı deneme olduğu "
            "bilinmiyor (K-039)",
        )

    satirlar = k.kapi_sonucu.get("kapilar") or {}
    eksik = sorted(ZORUNLU_KAPILAR - set(satirlar))
    if eksik:
        return AsamaSonucu(
            Asama.OUT_OF_SAMPLE, False,
            f"kanıtta değerlendirilmemiş kapı(lar): {', '.join(eksik)} (K-118: tam liste zorunlu)",
        )
    if k.kapi_sonucu.get("gecti") is True and all(
        (satirlar[a] or {}).get("gecti") is True for a in ZORUNLU_KAPILAR
    ):
        toplam = k.hipotez_toplami or k.hipotez_sirasi
        return AsamaSonucu(
            Asama.OUT_OF_SAMPLE,
            True,
            f"{len(ZORUNLU_KAPILAR)} kapının tamamı geçildi — {k.hipotez_sirasi}. hipotez "
            f"(defterde toplam {toplam})",
        )
    kalan = k.kapi_sonucu.get("kalan_kapilar") or []
    return AsamaSonucu(
        Asama.OUT_OF_SAMPLE, False, f"geçilmeyen kapı(lar): {', '.join(kalan) or 'bilinmiyor'}"
    )


def _out_of_sample_rypp(k: Kanit) -> AsamaSonucu:
    """RYPP yolunda `out_of_sample` (K-126). `ZORUNLU_KAPILAR` burada aranmaz; yerine RYPP'nin
    13 koşulu + B-3. K-039 ön şartı alfa yoluyla aynı. PASS/FAIL/INCONCLUSIVE → True/False/None."""
    if k.rypp_sonucu is None:
        return AsamaSonucu(
            Asama.OUT_OF_SAMPLE, None, "RYPP INCONCLUSIVE — RYPP değerlendirmesi yok (K-125)"
        )
    if k.hipotez_sirasi is None:
        return AsamaSonucu(
            Asama.OUT_OF_SAMPLE,
            None,
            "hipotez defterinde kayıt yok: bu stratejinin kaçıncı deneme olduğu "
            "bilinmiyor (K-039)",
        )
    if k.rypp_aile_sayisi is None:
        return AsamaSonucu(
            Asama.OUT_OF_SAMPLE,
            None,
            "RYPP INCONCLUSIVE — P3'ün k'sı defterden yeniden sayılmadı; kanıttaki k "
            "doğrulanamıyor (K-127)",
        )
    ana, g_ana = rypp_hukmu(k.rypp_sonucu)
    bag, g_bag = vintage_hukmu(k.bagimsiz_dogrulama, k.bagimsiz_vintage, k.veri_sha256)
    hukum = _ve(ana, bag)
    toplam = k.hipotez_toplami or k.hipotez_sirasi
    return AsamaSonucu(
        Asama.OUT_OF_SAMPLE,
        hukum,
        f"RYPP {RYPP_ETIKET[hukum]} — OOS {RYPP_ETIKET[ana]}: {g_ana}; {g_bag} — "
        f"{k.hipotez_sirasi}. hipotez (defterde toplam {toplam})",
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


def satir_hashi(strateji: str, satir: dict[str, Any], onceki_hash: str) -> str:
    """Bir geçmiş satırının zincir hash'i: kanonik içerik + strateji + öncekinin hash'i."""
    icerik = {k: v for k, v in satir.items() if k not in HASH_DISI}
    return nesne_hash({"strateji": strateji, "satir": icerik, "onceki": onceki_hash})


def zinciri_dogrula(strateji: str, gecmis: list[dict[str, Any]]) -> str:
    """Zinciri baştan yeniden hesaplar; kırıksa `PromotionHatasi`. Döner: son satırın hash'i.

    Yakaladıkları: hash alanı olmayan satır (K-082 öncesi biçim), yanlış `onceki_hash`
    (eksik/yeniden sıralanmış satır), içerik değişikliği (`satir_hash` uyuşmazlığı). Kısaltmayı
    (son satırların silinmesi) yakalayamaz — o `audit_ile_dogrula`nın işi.
    """
    onceki = KOK_HASH
    for i, satir in enumerate(gecmis):
        if "onceki_hash" not in satir or "satir_hash" not in satir:
            raise PromotionHatasi(
                f"{strateji}: {i}. geçmiş satırında zincir hash'i yok — K-082 öncesi biçim; "
                "`sq promotion zincirle` ile açıkça göç ettirilmeli, sessiz kabul yok"
            )
        if satir["onceki_hash"] != onceki:
            raise PromotionHatasi(
                f"{strateji}: {i}. satırın onceki_hash'i zincirle uyuşmuyor — eksik ya da "
                "yeniden sıralanmış satır (fail closed)"
            )
        beklenen = satir_hashi(strateji, satir, onceki)
        if satir["satir_hash"] != beklenen:
            raise PromotionHatasi(
                f"{strateji}: {i}. satırın içeriği hash'iyle uyuşmuyor — değiştirilmiş kayıt "
                "(fail closed)"
            )
        onceki = beklenen
    return onceki


def beklenen_asama(gecmis: list[dict[str, Any]]) -> Asama:
    """Geçmişten türeyen aşama: son **geçilen** satırın aşaması; hiç yoksa `YOK`."""
    for satir in reversed(gecmis):
        if satir.get("gecti") is True:
            return Asama(satir["asama"])
    return Asama.YOK


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
        self._protokol_kilidi(kanit)
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
        k = kanit or Kanit(protokol=self.protokol or Protokol.ALFA)
        self._protokol_kilidi(k)
        sonuc = AsamaSonucu(Asama.ELLE_ONAY, True, f"elle onay: {metin}")
        self._kaydet(sonuc, k)
        self.asama = Asama.ELLE_ONAY
        # Elle onaydan sonra `live` ayrı bir kapı değil; onay verildiyse canlıya yetkili.
        self._kaydet(_live(k), k)
        self.asama = Asama.LIVE
        return sonuc

    @property
    def protokol(self) -> Protokol | None:
        """`out_of_sample`ı hangi protokolle geçtiği; geçmediyse `None` (K-126). Geçmişten
        türer (zincir hash'li satırlar); K-126 öncesi satırda alan yok → `alfa`."""
        for satir in reversed(self.gecmis):
            if satir.get("asama") == Asama.OUT_OF_SAMPLE and satir.get("gecti") is True:
                return Protokol((satir.get("kanit") or {}).get("protokol", Protokol.ALFA))
        return None

    def _protokol_kilidi(self, kanit: Kanit) -> None:
        """`out_of_sample`ı bir protokolle geçen strateji başka protokolün kanıtıyla ilerlemez."""
        kilit = self.protokol
        if kilit is not None and kanit.protokol is not kilit:
            raise PromotionHatasi(
                f"{self.strateji}: out_of_sample {kilit} protokolüyle geçildi; {kanit.protokol} "
                "kanıtıyla ilerletilemez (K-126, protokol karışması)"
            )

    def eksik_asamalar(self) -> list[Asama]:
        """Bu stratejinin henüz geçmediği aşamalar."""
        i = SIRA.index(self.asama)
        return list(SIRA[i + 1 :])

    def _kaydet(self, sonuc: AsamaSonucu, kanit: Kanit) -> None:
        an = simdi_ms()
        satir: dict[str, Any] = {
            "zaman_ms": an,
            "zaman_utc": utc_str(an),
            "onceki_asama": str(self.asama),
            **sonuc.sozluk(),
            "kanit": kanit.sozluk(),
        }
        onceki = self.gecmis[-1]["satir_hash"] if self.gecmis else KOK_HASH
        satir["onceki_hash"] = onceki
        satir["satir_hash"] = satir_hashi(self.strateji, satir, onceki)
        self.gecmis.append(satir)

    @property
    def son_hash(self) -> str:
        """Zincirin ucu; boş geçmişte `KOK_HASH`."""
        return self.gecmis[-1]["satir_hash"] if self.gecmis else KOK_HASH

    def audit_ile_dogrula(self, audit: Defter) -> None:
        """Her satırın audit defterinde karşılığı var mı (K-082 P2)? Yoksa `PromotionHatasi`.

        Audit'in kendi zinciri de doğrulanır. Kısaltılmış bir dosya (son satırlar silinmiş)
        burada yakalanır: audit'te bu stratejiye ait, dosyada olmayan bir satır kalır.
        """
        if not audit.dogrula():
            raise PromotionHatasi("audit defterinin zinciri bozuk — promotion doğrulanamaz")
        olaylar = [
            o
            for o in audit.oku(tur=OlayTuru.PROMOTION)  # type: ignore[call-arg]
            if o["govde"].get("strateji") == self.strateji
        ]
        auditte = {o["satir_hash"]: o for o in olaylar}
        for i, satir in enumerate(self.gecmis):
            ref = satir.get("audit_hash")
            if not ref:
                raise PromotionHatasi(
                    f"{self.strateji}: {i}. satır audit defterine yazılmamış (audit_hash yok)"
                )
            olay = auditte.get(ref)
            if olay is None or olay["govde"].get("satir_hash") != satir["satir_hash"]:
                raise PromotionHatasi(
                    f"{self.strateji}: {i}. satırın audit karşılığı yok ya da uyuşmuyor "
                    f"(audit_hash {ref[:12]}…)"
                )
        dosyada = {s["satir_hash"] for s in self.gecmis}
        fazla = [o for o in olaylar if o["govde"].get("satir_hash") not in dosyada]
        if fazla:
            raise PromotionHatasi(
                f"{self.strateji}: audit'te {len(fazla)} promotion satırı var, dosyada yok — "
                "kayıt kısaltılmış ya da eski bir kopya (fail closed)"
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
        """Kaydı yükler; zincir **tam** doğrulanmadan kabul etmez (K-082 P1, fail closed)."""
        strateji = str(kayit["strateji"])
        gecmis = list(kayit.get("gecmis", []))
        zinciri_dogrula(strateji, gecmis)
        asama = Asama(kayit.get("asama", Asama.YOK))
        beklenen = beklenen_asama(gecmis)
        if asama is not beklenen:
            raise PromotionHatasi(
                f"{strateji}: dosyadaki aşama {asama} ama geçmiş {beklenen} diyor — "
                "aşama alanı geçmişle uyuşmuyor (fail closed)"
            )
        return cls(strateji=strateji, asama=asama, gecmis=gecmis)


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

    def oku(self, strateji: str, *, audit: Defter | None = None) -> PromotionKaydi:
        """Kaydı okur; yoksa `YOK` aşamasında yeni bir kayıt döndürür.

        Eksik dosyanın "hiçbir aşama geçilmemiş" anlamına gelmesi güvenli yön: kaydı
        silmek bir stratejiyi live'a değil başa götürür. Zincir her okumada doğrulanır
        (`yukle`); `audit` verilirse audit çapraz kontrolü de yapılır (P2).
        """
        p = self.yol(strateji)
        if not p.exists():
            return PromotionKaydi(strateji=strateji)
        kayit = PromotionKaydi.yukle(json.loads(p.read_text(encoding="utf-8")))
        if audit is not None:
            kayit.audit_ile_dogrula(audit)
        return kayit

    def yaz(self, kayit: PromotionKaydi, *, audit: Defter | None = None) -> Path:
        """Kaydı yazar. `audit` verilirse audit'e yazılmamış her satır önce oraya gider (P2).

        Sıra bir karardır: önce audit (append-only, zincirli), sonra JSON. Arada ölen bir
        süreç audit'te olan ama dosyada olmayan bir satır bırakır — `audit_ile_dogrula` bunu
        "dosya kısaltılmış" diye yakalar ve kayıt yeniden yazılana kadar fail closed kalır.
        Tersi sıra, audit'i olmayan bir promotion satırı bırakırdı: sessiz olan o.
        """
        p = self.yol(kayit.strateji)
        if audit is not None:
            for satir in kayit.gecmis:
                if satir.get("audit_hash"):
                    continue
                satir["audit_hash"] = audit.yaz(_promotion_olayi(kayit, satir, p))
        self._dosyaya_yaz(p, kayit)
        return p

    @staticmethod
    def _dosyaya_yaz(p: Path, kayit: PromotionKaydi) -> None:
        p.write_text(
            json.dumps(kayit.sozluk(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def hepsi(self, *, audit: Defter | None = None) -> list[PromotionKaydi]:
        """Bütün kayıtlar, ad sırasıyla; her biri zincir (ve audit) doğrulamasından geçer."""
        return [self.oku(p.stem, audit=audit) for p in sorted(self.kok.glob("*.json"))]

    def zincirle(self, strateji: str, *, audit: Defter) -> PromotionKaydi:
        """K-082 öncesi (zincirsiz) kaydı **açıkça** göç ettirir: içerik değişmez, hash'ler
        eklenir, her satır audit'e `goc=True` ile yazılır. Zincirli kayıtta hata."""
        p = self.yol(strateji)
        if not p.exists():
            raise PromotionHatasi(f"{strateji}: kayıt yok, göç edilecek bir şey yok")
        ham = json.loads(p.read_text(encoding="utf-8"))
        gecmis = list(ham.get("gecmis", []))
        if any("satir_hash" in satir for satir in gecmis):
            raise PromotionHatasi(f"{strateji}: kayıt zaten zincirli, göç gerekmiyor")
        onceki = KOK_HASH
        for satir in gecmis:
            satir.pop("audit_hash", None)
            satir["onceki_hash"] = onceki
            satir["satir_hash"] = satir_hashi(strateji, satir, onceki)
            onceki = satir["satir_hash"]
        kayit = PromotionKaydi(
            strateji=strateji, asama=Asama(ham.get("asama", Asama.YOK)), gecmis=gecmis
        )
        if kayit.asama is not beklenen_asama(gecmis):
            raise PromotionHatasi(
                f"{strateji}: eski kaydın aşaması geçmişiyle uyuşmuyor; göç edilmez"
            )
        for satir in kayit.gecmis:
            satir["audit_hash"] = audit.yaz(_promotion_olayi(kayit, satir, p, goc=True))
        self._dosyaya_yaz(p, kayit)
        return kayit


def _promotion_olayi(
    kayit: PromotionKaydi, satir: dict[str, Any], yol: Path, *, goc: bool = False
) -> Olay:
    """Bir promotion satırının audit karşılığı. `zaman_ms` satırın kendi zamanı (duvar saati
    audit'in `yazim_ms`inde); `sembol` boş — promotion enstrümana değil stratejiye ait."""
    govde: dict[str, Any] = {
        "strateji": kayit.strateji,
        "satir_hash": satir["satir_hash"],
        "onceki_hash": satir["onceki_hash"],
        "asama": satir["asama"],
        "gecti": satir["gecti"],
        "gerekce": satir["gerekce"],
        "onceki_asama": satir["onceki_asama"],
        "kanit": satir["kanit"],
    }
    if goc:
        govde["goc"] = True
    return Olay(
        tur=OlayTuru.PROMOTION,
        zaman_ms=int(satir["zaman_ms"]),
        sembol="",
        govde=govde,
        durum={"asama_sonrasi": str(kayit.asama), "kayit": str(yol)},
    )


__all__ = [
    "ASGARI_PAPER_GUN",
    "KONTROLLER",
    "MOD_ESIGI",
    "RYPP_BELIRSIZLIK",
    "RYPP_ESIKLER",
    "RYPP_ETIKET",
    "RYPP_KOSULLARI",
    "RYPP_NOKTA",
    "RYPP_YETERLILIK",
    "SIRA",
    "ZORUNLU_KAPILAR",
    "Asama",
    "AsamaSonucu",
    "Kanit",
    "PromotionDefteri",
    "PromotionHatasi",
    "PromotionKaydi",
    "Protokol",
    "bagimsiz_hukmu",
    "beklenen_asama",
    "rypp_ailesi",
    "vintage_hukmu",
    "rypp_hukmu",
    "satir_hashi",
    "sonraki",
    "yeterli_mi",
    "zinciri_dogrula",
]
