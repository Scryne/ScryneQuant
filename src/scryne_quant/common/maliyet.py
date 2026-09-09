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
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

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
