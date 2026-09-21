"""Finansman/rollover modeli: `Enstruman.finansman_modeli_id` → katalog → model. (K-095, R4 Paket 3)

`common/maliyet.py`nin ikizi, aynı gerekçelerle: parametre kodda gömülü değil, dosyada; kimlik
kararlı ad, içerik değil; gövde deney kaydına girer; kalibre edilmemiş model `gecici`dir ve
promotion'a giremez (K-021 kalıbı). Fark: **global model yok.** Finansman yalnız finansmanlı
tiplerde (`vadeli`/`cfd`, U17) var; spot kripto için "varsayılan finansman" diye bir şey
tanımlanmaz — kimliği olmayan enstrüman katalogdan model isteyemez, kimliği olan ama dosyası
olmayan enstrüman **çalışmaz** (fail closed; sessiz 0 yok).

**Model ne söyler:** uzun pozisyonun günlük rollover bedeli, notional'ın bps'i cinsinden
(`uzun_gunluk_bps ≥ 0`). Rollover **anları** modelin değil takvimin işi
(`Takvim.rollover_anlari`, K-095/2): FX'te her hafta içi günün NY 17:00'si; Çarşamba 3 gün
(hafta sonu değer tarihi, `uclu_swap_gunu`). Kısa pozisyon yok (kaldıraçsız, long-only v1) —
`kisa_gunluk_bps` diye bir alan **uydurulmadı**; kısa pozisyon gelirse alan ve K gelir.

**K-007:** bedel hiçbir zaman negatif değil (pozitif carry modellenmez — belirsizlikte kötü yön);
kapalı dönemde (ölçülmüş tatil) rollover **atlanmaz** (bedel yine işler).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

#: Enstrüman-başı modeller: `config/finansman/<id>.json`.
VARSAYILAN_KATALOG_DIZINI: Final = Path("config/finansman")

_KIMLIK_DESENI: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}$")

#: Haftanın günleri (`datetime.weekday`): 0 Pazartesi … 6 Pazar. FX'te üçlü swap Çarşamba.
CARSAMBA: Final = 2


class FinansmanHatasi(ValueError):
    """Finansman modeli çözümlenemedi ya da uygulanamadı: bilinmeyen kimlik, eksik/bozuk dosya,
    rollover üretemeyen takvim, bedel için yetmeyen nakit."""


class FinansmanKaynagi(BaseModel):
    """Bir `uzun_gunluk_bps` değerinin nereden geldiğinin kaydı (K-021 kalıbı).

    `tur` (K-098): **`broker`** = brokerın yayımladığı tarihli rollover oranı (gerçek);
    **`proxy`** = türetilmiş (ör. merkez bankası faiz farkı) — gerçek broker oranı **gibi
    kaydedilmez**, model `gecici` sayılır ve promotion'a giremez. `aralik` zorunlu: sabit oran
    yalnız o dönem için geçerlidir. `ham_gunluk_bps` türetimin işaretli hâli (negatif = carry
    lehte); K-095/K-007 tabanı (`uzun_gunluk_bps ≥ 0`) uygulanmadan önceki sayı görünür kalsın.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    saglayici: str = Field(min_length=1, description="Oranı yayımlayan kaynak (URL/belge)")
    tarih: str = Field(min_length=1, description="Oranın okunduğu gün (UTC)")
    gerekce: str = Field(min_length=1)
    aralik: str = Field(min_length=1, description="Geçerlilik dönemi, `YYYY-MM-DD..YYYY-MM-DD`")
    tur: Literal["broker", "proxy"]
    ham_gunluk_bps: float | None = Field(
        default=None, description="Türetimin işaretli değeri, taban uygulanmadan (proxy'de zorunlu)"
    )


class FinansmanModeli(BaseModel):
    """Uzun pozisyonun günlük rollover bedeli, notional'ın bps'i cinsinden. (K-095)

    `uclu_swap_gunu`: haftanın hangi günü 3 günlük bedel işler (`datetime.weekday`, FX'te 2 =
    Çarşamba — Cumartesi/Pazar değer tarihleri). Diğer hafta içi günler 1 gün.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    uzun_gunluk_bps: float = Field(ge=0, description="Uzun pozisyon, gün başına, notional bps")
    uclu_swap_gunu: int = Field(default=CARSAMBA, ge=0, le=6)
    kaynak: FinansmanKaynagi | None = None

    @property
    def gecici(self) -> bool:
        """Kaynağı yazılmamış **ya da proxy** model; promotion'a giremez (K-021, K-095, K-098)."""
        return self.kaynak is None or self.kaynak.tur == "proxy"

    def gun_bedeli(self, notional: float, gun: int) -> float:
        """`gun` günlük rollover bedeli, quote biriminde; her zaman ≥ 0 (K-007)."""
        if notional < 0.0 or gun < 0:
            raise FinansmanHatasi(f"notional/gün negatif olamaz: {notional}, {gun}")
        return notional * self.uzun_gunluk_bps * 1e-4 * gun

    def sozluk(self) -> dict[str, Any]:
        return {
            "uzun_gunluk_bps": self.uzun_gunluk_bps,
            "uclu_swap_gunu": self.uclu_swap_gunu,
            "gecici": self.gecici,
            "kaynak": self.kaynak.model_dump() if self.kaynak else None,
        }


def govde(model: FinansmanModeli) -> dict[str, Any]:
    """Deney kaydına giden hâl (`maliyet.govde` kalıbı): `gecici` türetilir, yazılmaz."""
    return {
        "uzun_gunluk_bps": model.uzun_gunluk_bps,
        "uclu_swap_gunu": model.uclu_swap_gunu,
        "kaynak": model.kaynak.model_dump() if model.kaynak else None,
    }


def govdeden(g: Mapping[str, Any]) -> FinansmanModeli:
    try:
        kaynak = g.get("kaynak")
        return FinansmanModeli(
            uzun_gunluk_bps=float(g["uzun_gunluk_bps"]),
            uclu_swap_gunu=int(g.get("uclu_swap_gunu", CARSAMBA)),
            kaynak=FinansmanKaynagi(**kaynak) if kaynak else None,
        )
    except (KeyError, TypeError, ValueError, ValidationError) as hata:
        raise FinansmanHatasi(f"finansman gövdesi bozuk: {hata}") from hata


@dataclass(frozen=True, slots=True)
class SembolFinansmani:
    kimlik: str
    model: FinansmanModeli


#: Sembol → çözümlenmiş model. `None` = koşuda finansmanlı enstrüman yok (kripto spot, bit-aynı).
Finansmanlar = Mapping[str, SembolFinansmani]


def finansmanlar_govdesi(finansmanlar: Finansmanlar) -> dict[str, dict[str, Any]]:
    """Kanonik blok `{sembol: {"id", "govde"}}`, sembol sırasıyla — `maliyetler` kalıbı."""
    return {
        sembol: {"id": sf.kimlik, "govde": govde(sf.model)}
        for sembol, sf in sorted(finansmanlar.items())
    }


def finansmanlar_govdeden(blok: Mapping[str, Any]) -> dict[str, SembolFinansmani]:
    out: dict[str, SembolFinansmani] = {}
    for sembol in sorted(blok):
        kayit = blok[sembol]
        if not isinstance(kayit, Mapping) or "id" not in kayit or "govde" not in kayit:
            raise FinansmanHatasi(f"{sembol}: finansmanlar bloğu {{id, govde}} taşımalı")
        out[sembol] = SembolFinansmani(str(kayit["id"]), govdeden(kayit["govde"]))
    return out


def gecici_mi(finansmanlar: Finansmanlar | None) -> bool | None:
    """`None` = finansman yok (bayrak yok); aksi hâlde herhangi biri geçiciyse `True`."""
    if finansmanlar is None:
        return None
    return any(sf.model.gecici for sf in finansmanlar.values())


class FinansmanKatalogu:
    """Kimlik → model. Deterministik ve yalnız dosya; global yok; eksik/bozuk → hata."""

    def __init__(self, dizin: str | Path | None = None) -> None:
        self.dizin = Path(VARSAYILAN_KATALOG_DIZINI if dizin is None else dizin)

    def yol(self, kimlik: str) -> Path:
        if not _KIMLIK_DESENI.match(kimlik):
            raise FinansmanHatasi(f"geçersiz finansman modeli kimliği {kimlik!r}")
        return self.dizin / f"{kimlik}.json"

    def coz(self, kimlik: str) -> FinansmanModeli:
        p = self.yol(kimlik)
        if not p.is_file():
            raise FinansmanHatasi(
                f"finansman modeli {kimlik!r} için dosya yok: {p} — sessiz 0 yok (K-095)"
            )
        try:
            return FinansmanModeli.model_validate_json(p.read_text(encoding="utf-8"))
        except (ValidationError, ValueError) as hata:
            raise FinansmanHatasi(f"finansman modeli {kimlik!r} bozuk ({p}): {hata}") from hata


__all__ = [
    "CARSAMBA",
    "VARSAYILAN_KATALOG_DIZINI",
    "FinansmanHatasi",
    "FinansmanKatalogu",
    "FinansmanKaynagi",
    "FinansmanModeli",
    "Finansmanlar",
    "SembolFinansmani",
    "finansmanlar_govdeden",
    "finansmanlar_govdesi",
    "gecici_mi",
    "govde",
    "govdeden",
]
