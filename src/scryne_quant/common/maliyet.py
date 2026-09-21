"""Maliyet modeli konfigürasyonu. (K-007, K-016, K-021)

K-007 iki şey istiyor: maliyet parametreleri **kodda gömülü sabit olmayacak**, ve her
backtest sonucuna hangi değerlerle çalıştığı yazılacak. Bu modül ikisinin de tek adresi.

**Neden JSON, TOML değil:** bu dosyayı `sq data slippage-kalibre --yaz` komutu **yazıyor**.
`tomllib` yalnızca okur; TOML yazmak için ya yeni bir bağımlılık ya da elle yazılmış bir
serileştirici gerekirdi — ikisi de, içeriği bir backtest sonucunun kimliğine giren bir
dosya için kötü takas. `json.dumps(sort_keys=True)` byte düzeyinde kararlı bir dosya verir;
K-009'un istediği de tam olarak bu.

**Geçici model bayrağı:** `kalibrasyon` alanı boşsa model `gecici`dir ve bu bayrak
sonuç kaydına geçer; geçici modelle üretilen sonuç promotion'a giremez (K-010, K-021).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

#: Depo kökünden bağımsız, repoya ait konfigürasyon.
VARSAYILAN_YOL: Final = Path("config/maliyet.json")


class SlippageKalibrasyonu(BaseModel):
    """Bir `slippage_bps` değerinin nereden geldiğinin tam kaydı. (K-021)

    Sayının kendisi yeterli değil: hangi veriden, hangi aralıkta, hangi persentille ve
    **hangi gerekçeyle** çıktığı olmadan altı ay sonra tartışılamaz, yalnızca yeniden
    hesaplanır — ki bu reproducibility'nin tam tersi.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    yontem: str = Field(description="Ölçülen büyüklüğün tanımı, formülüyle birlikte")
    persentil: float = Field(ge=0, le=100)
    deger_bps: float = Field(ge=0)
    sembol: str
    timeframe: str
    aralik_baslangic_ms: int
    aralik_bitis_ms: int
    bar_sayisi: int
    veri_sha256: str = Field(description="Kalibrasyonun okuduğu Parquet dosyasının kimliği")
    dagilim_bps: dict[str, float] = Field(
        default_factory=dict,
        description="Tam persentil dağılımı — persentil kararı yeniden ölçmeden değişebilsin",
    )
    tarih: str
    gerekce: str = Field(min_length=1)


class MaliyetModeli(BaseModel):
    """Backtest'in kullandığı maliyet varsayımları. (K-007)

    Her iki bacakta da **taker** varsayılır; maker indirimi varsayılmaz. Slippage her
    zaman aleyhtedir — yön kuralı motorun işi, buradaki sayı yalnızca büyüklüğü verir.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fee_taker_bps: float = Field(ge=0, description="Tek bacak taker komisyonu (Spike 4: 10,0)")
    slippage_bps: float = Field(ge=0, description="Tek bacak slippage, her zaman aleyhte")
    kalibrasyon: SlippageKalibrasyonu | None = None

    @property
    def gecici(self) -> bool:
        """Kalibre edilmemiş model. Bu bayrak taşıyan sonuç promotion'a giremez (K-021)."""
        return self.kalibrasyon is None

    @property
    def gidis_donus_bps(self) -> float:
        """Bir alım + bir satımın toplam maliyeti: iki bacak komisyon + iki bacak slippage.

        Spike 4'ün ölçtüğü **20,02 bps** yalnızca komisyon ayağıdır (2 × 10,01); slippage
        onun üstüne biner. K-017'nin timeframe kararını veren hareket/maliyet oranı o
        komisyon sayısına dayanıyordu — bu özellik onu kapsar, onunla aynı sayı değildir.
        """
        return 2 * (self.fee_taker_bps + self.slippage_bps)

    def sozluk(self) -> dict[str, Any]:
        """Sonuç kaydına yazılacak biçim (K-009)."""
        return {
            "fee_taker_bps": self.fee_taker_bps,
            "slippage_bps": self.slippage_bps,
            "gidis_donus_bps": self.gidis_donus_bps,
            "gecici": self.gecici,
            "kalibrasyon": self.kalibrasyon.model_dump() if self.kalibrasyon else None,
        }


def yukle(yol: str | Path = VARSAYILAN_YOL) -> MaliyetModeli:
    """Maliyet modelini dosyadan okur.

    Dosya yoksa **varsayılana düşmez.** Sessizce varsayılan bir maliyetle çalışmak,
    K-007'nin engellemek için var olduğu şeyin ta kendisi: sonuçta hangi varsayımın
    kullanıldığı belirsiz kalır.
    """
    p = Path(yol)
    if not p.exists():
        raise FileNotFoundError(f"maliyet konfigürasyonu yok: {p} (K-007)")
    return MaliyetModeli.model_validate_json(p.read_text(encoding="utf-8"))


def yaz(model: MaliyetModeli, yol: str | Path = VARSAYILAN_YOL) -> Path:
    """Modeli dosyaya yazar. Anahtarlar sıralı, satır sonu `\\n` — byte düzeyinde kararlı."""
    p = Path(yol)
    p.parent.mkdir(parents=True, exist_ok=True)
    icerik = json.dumps(
        model.model_dump(exclude_none=False),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    p.write_text(icerik + "\n", encoding="utf-8", newline="\n")
    return p


# ---------------------------------------------------------------- katalog + çözümleyici (K-084/U14)

#: Global modelin kimliği — `data/kimlik.MALIYET_MODELI_GLOBAL` ile aynı dize (enstrümanın
#: varsayılan model etiketi); ayrı tanımlı ki `common` → `data` bağı olmasın.
GLOBAL_KIMLIK: Final = "global"

#: Enstrüman-başı modeller: `config/maliyet/<id>.json`, şema `MaliyetModeli` ile **aynı**.
VARSAYILAN_KATALOG_DIZINI: Final = Path("config/maliyet")

#: Model kimliği dosya adı olur: yol ayırıcı, nokta-nokta, boşluk yok. Kararlı ad, içerik hash'i
#: değil (K-084/3): kanıt kayıttaki gövde + `kalibrasyon.veri_sha256`.
_KIMLIK_DESENI: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}$")


class MaliyetHatasi(ValueError):
    """Maliyet modeli çözümlenemedi: bilinmeyen kimlik, eksik/bozuk dosya, yasak kullanım."""


def govde(model: MaliyetModeli) -> dict[str, Any]:
    """Modelin **deney kaydına** giden hâli: `fee_taker_bps, slippage_bps, kalibrasyon`.

    `cli/main._maliyet_govdesi` buna delege eder; kayıt bu bloğu okur, `config/maliyet.json`ın
    bugünkü hâlini değil (K-009). Anahtar kümesi ve biçimi deney `girdi_hash`ine giriyor —
    `tests/unit/test_enstruman_v2.py` SHA sabitiyle koruyor; değiştirmek K ister.
    """
    return {
        "fee_taker_bps": model.fee_taker_bps,
        "slippage_bps": model.slippage_bps,
        "kalibrasyon": model.kalibrasyon.model_dump() if model.kalibrasyon else None,
    }


def govdeden(g: Mapping[str, Any]) -> MaliyetModeli:
    """`govde()` çıktısından model — dosyadan **okumaz** (`research/tekrar.py` kalıbı)."""
    try:
        kalibrasyon = g.get("kalibrasyon")
        return MaliyetModeli(
            fee_taker_bps=float(g["fee_taker_bps"]),
            slippage_bps=float(g["slippage_bps"]),
            kalibrasyon=SlippageKalibrasyonu(**kalibrasyon) if kalibrasyon else None,
        )
    except (KeyError, TypeError, ValueError, ValidationError) as hata:
        raise MaliyetHatasi(f"maliyet gövdesi bozuk: {hata}") from hata


@dataclass(frozen=True, slots=True)
class SembolMaliyeti:
    """Bir sembole çözümlenmiş model + hangi kimlikten geldiği."""

    kimlik: str
    model: MaliyetModeli


#: Sembol → çözümlenmiş model. `None` = tek model (bugünkü Binance spot yolu, bit-aynı).
Maliyetler = Mapping[str, SembolMaliyeti]


def maliyetler_govdesi(maliyetler: Maliyetler) -> dict[str, dict[str, Any]]:
    """Çok modelli koşunun kanonik bloğu: `{sembol: {"id", "govde"}}`, sembol sırasıyla.

    Girdi sözlüğünün ekleme sırası sonucu **değiştirmez** (sıralı üretim + `nesne_hash`
    `sort_keys`). Bu blok kayda **yalnız çok model varsa** girer (`risk`/`evren` kalıbı).
    """
    return {
        sembol: {"id": em.kimlik, "govde": govde(em.model)}
        for sembol, em in sorted(maliyetler.items())
    }


def maliyetler_govdeden(blok: Mapping[str, Any]) -> dict[str, SembolMaliyeti]:
    """Kayıttaki `maliyetler` bloğundan modeller; eksik/bozuk sembol → `MaliyetHatasi`."""
    out: dict[str, SembolMaliyeti] = {}
    for sembol in sorted(blok):
        kayit = blok[sembol]
        if not isinstance(kayit, Mapping) or "id" not in kayit or "govde" not in kayit:
            raise MaliyetHatasi(f"{sembol}: maliyetler bloğu {{id, govde}} taşımalı")
        out[sembol] = SembolMaliyeti(str(kayit["id"]), govdeden(kayit["govde"]))
    return out


def gecici_mi(maliyet: MaliyetModeli, maliyetler: Maliyetler | None) -> bool:
    """Koşu geçici mi: tek modelde modelin bayrağı; çok modelde **herhangi biri** (K-084/6)."""
    if maliyetler is None:
        return maliyet.gecici
    return any(em.model.gecici for em in maliyetler.values())


class MaliyetKatalogu:
    """Kimlik → model çözümleyici. Deterministik ve yalnız dosya: ortam, sağlayıcı, ağ yok.

    - `global` → `config/maliyet.json` (mevcut), **yalnız Binance spot kripto** için (K-083/U17,
      K-084/4); başka enstrümana `global` istemek hatadır, sessiz yayılma yok.
    - diğer kimlikler → `config/maliyet/<id>.json`, aynı şema.
    - dosya yok / JSON bozuk / şema uymuyor / kimlik biçimsiz → `MaliyetHatasi` (fail closed).

    Aynı gövdeyi taşıyan iki farklı kimlik **iki ayrı modeldir**: kimlik kararlı ad, içerik
    değil; kayıt ikisini de `id` + gövdeyle ayırt eder.
    """

    def __init__(
        self,
        global_yol: str | Path | None = None,
        dizin: str | Path | None = None,
    ) -> None:
        # Varsayılanlar çağrı anında okunur (testler modül sabitini geçici olarak yönlendirebilsin).
        self.global_yol = Path(VARSAYILAN_YOL if global_yol is None else global_yol)
        self.dizin = Path(VARSAYILAN_KATALOG_DIZINI if dizin is None else dizin)

    def yol(self, kimlik: str) -> Path:
        if kimlik == GLOBAL_KIMLIK:
            return self.global_yol
        if not _KIMLIK_DESENI.match(kimlik):
            raise MaliyetHatasi(f"geçersiz maliyet modeli kimliği {kimlik!r}")
        return self.dizin / f"{kimlik}.json"

    def coz(self, kimlik: str, *, binance_spot_kripto: bool) -> MaliyetModeli:
        if kimlik == GLOBAL_KIMLIK and not binance_spot_kripto:
            raise MaliyetHatasi(
                "global maliyet modeli yalnız Binance spot kripto için; enstrüman-başı model "
                "gerekir (K-084/U14)"
            )
        p = self.yol(kimlik)
        if not p.is_file():
            raise MaliyetHatasi(f"maliyet modeli {kimlik!r} için dosya yok: {p} (K-007)")
        try:
            return MaliyetModeli.model_validate_json(p.read_text(encoding="utf-8"))
        except (ValidationError, ValueError) as hata:
            raise MaliyetHatasi(f"maliyet modeli {kimlik!r} bozuk ({p}): {hata}") from hata
