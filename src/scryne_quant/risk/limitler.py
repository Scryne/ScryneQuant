"""Risk limitleri: sayılar ve nereden geldikleri. (§11, K-032, K-033)

Bu modülde **hiçbir karar verilmiyor** — yalnızca limitlerin tanımı ve yüklenmesi var.
Kararı `motor.py` veriyor. Ayrı durmalarının sebebi K-007'nin maliyet modelinde kurduğu
aynı disiplin: bir sayı koda gömülüyse o sayının neden o olduğu sorusunun adresi yoktur,
ve altı ay sonra değiştiren kişi neyi değiştirdiğini bilmez.

**Her limitin bir `kaynak` alanı var ve iki değerden birini alır:**

- `olculdu` — sayı gerçek veriden çıktı. Dağılımı `dagilim` alanında duruyor; persentil
  kararı yeniden ölçmeden değiştirilebilir (K-021'in kurduğu kalıp).
- `istah` — sayı bir risk iştahı tercihi, ölçüm değil. Bunu gizlemek en tehlikelisi
  olurdu: ölçülmüş bir sayı gibi görünen bir tercih, tartışılamaz hâle gelir.

`istah` işaretli her limitin bir `gozden_gecirme` koşulu olmak **zorunda** — "ne zaman
yeniden düşüneceğiz" sorusu cevapsız kalırsa o sayı kalıcı olur, kalıcı olmayı hak ettiği
için değil, kimse dokunmadığı için.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Repoya ait konfigürasyon — depo kökünden bağımsız (maliyet.json ile aynı yerde).
VARSAYILAN_YOL: Final = Path("config/risk.json")

Kaynak = Literal["olculdu", "istah"]


class LimitHatasi(ValueError):
    """Risk konfigürasyonu geçersiz."""


class Gerekce(BaseModel):
    """Bir limitin değerinin yanında taşıdığı kanıt.

    Değerin kendisi burada değil: değer limiti tutan alanda. Burada **niçin o değer**
    sorusunun cevabı var. İkisini ayrı tutmak, `MaliyetModeli`/`SlippageKalibrasyonu`
    ikilisiyle aynı kalıp.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kaynak: Kaynak
    metin: str = Field(min_length=1)
    dagilim: dict[str, float] = Field(
        default_factory=dict,
        description="Ölçülmüş limitlerde tam persentil dağılımı — persentil kararı "
        "yeniden ölçmeden değişebilsin (K-021 kalıbı)",
    )
    gozden_gecirme: str = ""
    """Bu sayının yeniden düşünülmesi gereken koşul. `istah` kaynağında zorunlu."""

    olcum_tarihi: str = ""
    veri_sha256: str = ""
    """Ölçümün okuduğu Parquet dosyasının kimliği. `olculdu` kaynağında zorunlu."""

    @model_validator(mode="after")
    def _kaynak_gerekleri(self) -> Gerekce:
        if self.kaynak == "istah" and not self.gozden_gecirme:
            raise LimitHatasi(
                "iştah kaynaklı limit bir `gozden_gecirme` koşulu olmadan tanımlanamaz: "
                "ne zaman yeniden düşünüleceği yazılmayan bir tercih kalıcı olur (K-033)"
            )
        if self.kaynak == "olculdu" and not self.veri_sha256:
            raise LimitHatasi(
                "ölçülmüş limit `veri_sha256` olmadan tanımlanamaz: hangi veriden "
                "çıktığı bilinmeyen bir ölçüm tekrar edilemez (K-009)"
            )
        return self


class RiskLimitleri(BaseModel):
    """Risk motorunun uyguladığı limitlerin tamamı. (§11)

    Hepsi tek nesnede duruyor çünkü risk kararı bunların **birleşimi**: ayrı ayrı
    yüklenen limitler, hangi kombinasyonun çalıştığı belirsiz bir sistem üretir ve audit
    kaydı "hangi limitlerle karar verildi" sorusuna cevap veremez. Bu nesnenin hash'i
    audit kaydına giriyor (`kimlik()`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ----------------------------------------------------------- boyutlandırma

    azami_maruziyet: float = Field(gt=0.0, le=1.0)
    """Portföyün bu sembolde olabileceği azami kesir. `Sinyal.target_exposure`'ın tavanı.

    **Tavan hedef üzerindedir, gerçekleşen üzerinde değil.** Fill `t+1` açılışında o anki
    özkaynağın bu kesri olarak hesaplanıyor; fill'den sonra fiyat yükselirse pozisyonun
    payı tavanın üstüne çıkar. Ölçüldü: %30 tavanda gerçekleşen azami maruziyet %30,14
    (`tests/unit/test_risk_backtest.py`).

    Bu bir limit ihlali değil, **sürekli yeniden dengelemenin yokluğu**. Her barda hedefe
    dönmek bir rebalance bandı kararıdır ve ayrı bir limit olarak konuşulmalı — sapma
    tavanın %10'unu aşarsa testin kırılmasının sebebi bu: o gün tavan pratikte başka bir
    sayı demektir.
    """

    islem_basina_risk: float = Field(gt=0.0, le=1.0)
    """Tek bir pozisyonun aleyhte senaryoda özkaynağın kaçını riske atabileceği.

    Boyuta çevrilmesi bir **aleyhte hareket varsayımı** gerektirir; o varsayım
    `ters_hareket_atr_carpani`. v1'de borsada duran bir stop emri yok (Faz 7), dolayısıyla
    pozisyon strateji `FLAT` diyene kadar açık kalır — aleyhte hareket ufku tutma
    süresidir, bir stop mesafesi değil.
    """

    ters_hareket_atr_carpani: float = Field(gt=0.0)
    """Aleyhte hareketin ATR'nin kaç katı varsayılacağı. Ölçülmüş olmak zorunda.

    Geleneksel "2×ATR" bu veride **riski hafife alıyor**: 24 barlık ufukta aleyhte
    hareketin medyanı 2,07 ATR, p90'ı 6,39 ATR. 2,0 seçmek, vakaların yarısında gerçek
    riskin altında kalmak olurdu (K-007: belirsizlikte kötü yöne yuvarla).
    """

    # ------------------------------------------------------------------ durdurma

    gunluk_zarar_limiti: float = Field(gt=0.0, le=1.0)
    """Bir UTC gününde özkaynağın bu kesrini kaybetmek yeni girişleri durdurur."""

    drawdown_limiti: float = Field(gt=0.0, le=1.0)
    """Zirveden bu kesir kadar düşmek **kill switch'i tetikler** (K-008), sadece durdurmaz.

    Günlük zarardan farkı: günlük zarar geçici bir durumdur ve gün dönümünde kendiliğinden
    kalkar; drawdown birikmiş bir hasardır ve kendiliğinden iyileşmesi beklenmez. Biri
    fren, diğeri kontak kapatmadır.
    """

    ardisik_kayip_limiti: int = Field(ge=1)
    """Bu kadar ardışık kayıplı işlem, `cooldown_bar` kadar yeni girişi durdurur."""

    cooldown_bar: int = Field(ge=1)
    """Ardışık kayıp tetiklendiğinde kaç bar yeni giriş yapılmayacağı."""

    volatilite_esigi: float = Field(gt=0.0)
    """ATR/fiyat bu oranı aşarsa yeni giriş yapılmaz. Ölçülmüş olmak zorunda."""

    # ------------------------------------------------------------------ portföy (Faz 10)

    azami_brut_maruziyet: float = Field(default=1.0, gt=0.0, le=1.0)
    """Nakit dışı toplam kesrin tavanı — §12'nin *gross exposure* limiti.

    `azami_maruziyet` tek bir enstrümanı sınırlar; bu, hepsinin toplamını. İkisi farklı
    şeyler: %30 tek-enstrüman tavanı dört enstrümanla %120 brüt maruziyet demektir — yani
    kaldıraç. Kaldıraçsız spotta üst sınır 1,0 ve varsayılan da odur: **tek sembollü koşuda
    bağlayıcı olmasın** diye. Bağlayıcı bir sayı, ölçüldüğünde (Faz 12) yazılır.

    İkisi arasında bir sıralama kuralı **yok** ve olmaması bilinçli: brüt tavanın tek
    enstrüman tavanının altında olduğu bir konfigürasyon geçerlidir (örn. enstrüman başına
    %30, toplamda %20) ve o hâlde brüt olan bağlar. Hangisinin bağladığı tahmin edilmiyor,
    `OnayliNiyet.kisitlayan` alanında **adıyla** kaydediliyor.
    """

    azami_enstruman: int = Field(default=1_000, ge=1)
    """Aynı anda kaç enstrümanda pozisyon taşınabileceği — §12'nin *concentration* limiti.

    Varsayılan bilinçli olarak bağlamayacak kadar büyük: Faz 10 yöntemi **kurar**, sayıyı
    ölçmez. Gerçek sayı, portföy kurma yönteminin kapasite ve turnover ölçümüyle birlikte
    Faz 12'de belirlenir. Bugünden bir sayı yazmak, ölçülmemiş bir kapı olurdu (K-019).
    """

    # ------------------------------------------------------------------ gerekçe

    gerekceler: dict[str, Gerekce] = Field(default_factory=dict)
    """Limit adı → gerekçesi. Her limit için bir kayıt olmak **zorunda**."""

    @model_validator(mode="after")
    def _tutarlilik(self) -> RiskLimitleri:
        eksik = [ad for ad in LIMIT_ADLARI if ad not in self.gerekceler]
        if eksik:
            raise LimitHatasi(
                f"gerekçesi olmayan limit(ler): {', '.join(eksik)}. Bir sayının neden o "
                "sayı olduğu yazılmadıysa o sayı tartışılamaz, yalnızca devralınır (K-033)"
            )
        fazla = [ad for ad in self.gerekceler if ad not in LIMIT_ADLARI]
        if fazla:
            raise LimitHatasi(f"bilinmeyen limite gerekçe: {', '.join(fazla)}")

        # Drawdown limiti promotion kapısının **altında** olmak zorunda: kapı 0,25 diyorsa
        # canlıda 0,25'e ulaşmak, o stratejiyi bugün promote etmeyeceğimiz bir düşüşe
        # ulaşmış olmak demektir. Fren kapıdan sonra değil önce devreye girmeli.
        if self.drawdown_limiti >= PROMOTION_DRAWDOWN_KAPISI:
            raise LimitHatasi(
                f"drawdown_limiti ({self.drawdown_limiti}) promotion kapısının "
                f"({PROMOTION_DRAWDOWN_KAPISI}, K-019) altında olmalı: kapıya eşit veya "
                "üstünde bir fren, promote etmeyeceğimiz bir düşüşe izin vermiş olur"
            )

        for ad in ("ters_hareket_atr_carpani", "volatilite_esigi", "gunluk_zarar_limiti"):
            if self.gerekceler[ad].kaynak != "olculdu":
                raise LimitHatasi(
                    f"{ad} ölçülmüş olmak zorunda (kaynak='olculdu'); bu sayı bir iştah "
                    "tercihi değil, veriden çıkan bir büyüklüktür"
                )
        return self

    # -------------------------------------------------------------------- kayıt

    def sozluk(self) -> dict[str, Any]:
        """Audit kaydına ve sonuç kaydına yazılan biçim."""
        return {
            ad: getattr(self, ad) for ad in LIMIT_ADLARI
        } | {"gerekceler": {a: g.model_dump() for a, g in sorted(self.gerekceler.items())}}

    def kimlik(self) -> str:
        """Limit kümesinin hash'i. Hangi limitlerle karar verildiğinin kimliği.

        Gerekçeler hash'e **girmiyor**: gerekçe metninde bir yazım düzeltmesi, limitlerin
        değiştiği anlamına gelmez — ve değişmiş gibi görünmesi, audit kaydındaki gerçek
        değişiklikleri gürültüye boğardı.
        """
        from scryne_quant.common.hash import nesne_hash

        return nesne_hash({ad: getattr(self, ad) for ad in LIMIT_ADLARI})


#: Limit alanlarının kanonik sırası. Gerekçe kontrolü ve kayıt bu listeyi kullanıyor;
#: yeni bir limit eklemek buraya yazmakla olur, yoksa gerekçesiz geçer.
LIMIT_ADLARI: Final[tuple[str, ...]] = (
    "azami_maruziyet",
    "islem_basina_risk",
    "ters_hareket_atr_carpani",
    "gunluk_zarar_limiti",
    "drawdown_limiti",
    "ardisik_kayip_limiti",
    "cooldown_bar",
    "volatilite_esigi",
    "azami_brut_maruziyet",
    "azami_enstruman",
)

#: K-019'un `max_drawdown` kapısı. Drawdown freninin altında kalmak zorunda olduğu sınır.
#: `research.kapilar`dan import edilmiyor: `risk/` paketinin `research/`e bağımlı olması,
#: canlı karar yolunu araştırma koduna bağlardı. Sayı tek yerde yaşamıyor ama
#: `tests/unit/test_risk_limitleri.py` ikisinin aynı kaldığını kontrol ediyor.
PROMOTION_DRAWDOWN_KAPISI: Final = 0.25


def yukle(yol: str | Path = VARSAYILAN_YOL) -> RiskLimitleri:
    """Limitleri dosyadan okur.

    Dosya yoksa **varsayılana düşmez** — K-007'nin maliyet modelinde olduğu gibi.
    Sessizce bir varsayılan limit kümesiyle işlem yapmak, risk motorunun var olma
    sebebinin tersi: hangi limitlerle çalıştığı belirsiz bir sistem.
    """
    p = Path(yol)
    if not p.exists():
        raise FileNotFoundError(f"risk konfigürasyonu yok: {p} (K-032)")
    return RiskLimitleri.model_validate_json(p.read_text(encoding="utf-8"))


def yaz(limitler: RiskLimitleri, yol: str | Path = VARSAYILAN_YOL) -> Path:
    """Limitleri dosyaya yazar. Anahtarlar sıralı — byte düzeyinde kararlı."""
    p = Path(yol)
    p.parent.mkdir(parents=True, exist_ok=True)
    icerik = json.dumps(
        limitler.model_dump(exclude_none=False), ensure_ascii=False, indent=2, sort_keys=True
    )
    p.write_text(icerik + "\n", encoding="utf-8", newline="\n")
    return p


__all__ = [
    "LIMIT_ADLARI",
    "PROMOTION_DRAWDOWN_KAPISI",
    "VARSAYILAN_YOL",
    "Gerekce",
    "LimitHatasi",
    "RiskLimitleri",
    "yaz",
    "yukle",
]
