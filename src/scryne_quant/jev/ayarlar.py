"""`config/jev.json` okuyucusu: model pini, kesim beyanı, istemci ve etiketleme ayarları. (K-074)

`config/risk.json` kalıbı: her sayının yanında gerekçesi durur, kod yalnızca sayıyı okur.
Kesim tarihi `null` olabilir ve bu bir eksiklik değil, bir **beyandır**: bilinmiyor.
Bilinmeyen kesim, geriye dönük her türetimi `leak_riski=true` yapar (K-074/3). Bu modül
tarihi asla uydurmaz, varsayılan koymaz.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.zaman import datetime_to_ms

VARSAYILAN_YOL: Final = Path("config/jev.json")


class AyarHatasi(ValueError):
    """`config/jev.json` eksik ya da tutarsız."""


def _utc_ms(metin: str | None) -> int | None:
    if metin is None:
        return None
    try:
        an = dt.datetime.fromisoformat(metin.replace("Z", "+00:00"))
    except ValueError as e:
        raise AyarHatasi(f"tarih ISO-8601 olmalı: {metin!r}") from e
    return datetime_to_ms(an)


@dataclass(frozen=True, slots=True)
class JevAyarlari:
    model: str
    yayin_ms: int | None
    egitim_kesim_ms: int | None
    """`None` = bilinmiyor. Yayın tarihi buraya **kopyalanmaz** (K-074/3)."""

    egitim_kesim_kaynagi: str
    timeout_s: float
    azami_deneme: int
    durum_surumu: int
    sembol: str
    yon_marji: float
    bayat_ms: int
    ufuk_bar: tuple[int, ...]
    birincil_ufuk_bar: int
    kalibrasyon_kovalari: tuple[float, ...]
    tutarlilik_her_n_karar: int

    @property
    def kesim_biliniyor(self) -> bool:
        return self.egitim_kesim_ms is not None

    def sozluk(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "yayin_ms": self.yayin_ms,
            "egitim_kesim_ms": self.egitim_kesim_ms,
            "egitim_kesim_kaynagi": self.egitim_kesim_kaynagi,
            "timeout_s": self.timeout_s,
            "azami_deneme": self.azami_deneme,
            "durum_surumu": self.durum_surumu,
            "sembol": self.sembol,
            "yon_marji": self.yon_marji,
            "bayat_ms": self.bayat_ms,
            "ufuk_bar": list(self.ufuk_bar),
            "birincil_ufuk_bar": self.birincil_ufuk_bar,
            "kalibrasyon_kovalari": list(self.kalibrasyon_kovalari),
            "tutarlilik_her_n_karar": self.tutarlilik_her_n_karar,
        }


def yukle(yol: str | Path = VARSAYILAN_YOL) -> JevAyarlari:
    try:
        ham = json.loads(Path(yol).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise AyarHatasi(f"ayar dosyası yok: {yol}") from e
    return ayristir(ham)


def ayristir(ham: dict[str, Any]) -> JevAyarlari:
    try:
        m, i, k, s, g = ham["model"], ham["istemci"], ham["karar"], ham["sonuc"], ham["golge"]
        a = JevAyarlari(
            model=str(m["istenen"]),
            yayin_ms=_utc_ms(m.get("yayin_utc")),
            egitim_kesim_ms=_utc_ms(m.get("egitim_kesim_utc")),
            egitim_kesim_kaynagi=str(m.get("egitim_kesim_kaynagi", "dogrulanmadi")),
            timeout_s=float(i["timeout_s"]),
            azami_deneme=int(i["azami_deneme"]),
            durum_surumu=int(k["durum_surumu"]),
            sembol=str(k["sembol"]).upper(),
            yon_marji=float(k["yon_marji"]),
            bayat_ms=int(k["bayat_ms"]),
            ufuk_bar=tuple(int(u) for u in s["ufuk_bar"]),
            birincil_ufuk_bar=int(s["birincil_ufuk_bar"]),
            kalibrasyon_kovalari=tuple(float(x) for x in s["kalibrasyon_kovalari"]),
            tutarlilik_her_n_karar=int(g["tutarlilik_her_n_karar"]),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise AyarHatasi(f"config/jev.json alanı eksik ya da bozuk: {e}") from e

    if not a.model or a.model in ("jev-latest", "jev-preview"):
        raise AyarHatasi(
            f"model çözülmüş bir sürüm olmalı ({a.model!r} zamanla kayar; K-061/3, K-074/6)"
        )
    if a.egitim_kesim_ms is not None and a.egitim_kesim_kaynagi in ("", "dogrulanmadi"):
        raise AyarHatasi("kesim tarihi yazılmışsa kaynağı da yazılmalı (K-049/4)")
    if a.yayin_ms is not None and a.egitim_kesim_ms is not None and a.egitim_kesim_ms > a.yayin_ms:
        raise AyarHatasi("eğitim kesimi yayından sonra olamaz")
    if not 0.0 <= a.yon_marji <= 1.0:
        raise AyarHatasi(f"yon_marji [0,1] aralığında olmalı: {a.yon_marji}")
    if a.timeout_s <= 0 or a.azami_deneme < 1 or a.bayat_ms < 0:
        raise AyarHatasi("timeout_s > 0, azami_deneme ≥ 1, bayat_ms ≥ 0 olmalı")
    if a.birincil_ufuk_bar not in a.ufuk_bar or any(u < 1 for u in a.ufuk_bar):
        raise AyarHatasi("birincil ufuk `ufuk_bar` listesinde olmalı, ufuklar ≥ 1")
    if (
        list(a.kalibrasyon_kovalari) != sorted(a.kalibrasyon_kovalari)
        or len(a.kalibrasyon_kovalari) < 2
    ):
        raise AyarHatasi("kalibrasyon kovaları artan ve en az iki sınır olmalı")
    return a


__all__ = ["VARSAYILAN_YOL", "AyarHatasi", "JevAyarlari", "ayristir", "yukle"]
