"""Canlı evren tablosunun aylık yenilenmesi. (Faz 14)

Koşu kendi dizinindeki tabloyu okur (`EvrenTablosu`); ay dönünce yeni ayın satırı bu dosyaya
eklenmelidir, yoksa koşu bilinen son ayın listesiyle devam eder ve `uyelik_gecikmesi` yazar.

Yenileme **aynı kuralla** ve araştırmanın kullandığı **aynı fonksiyonla** (`tablo_kur`) yapılır
(K-001). Araştırma tablosunun üstüne yazılmaz: o tablonun hash'i hipotezlerin veri kimliği.

İki koruma:

1. **M−1 tamam mı:** `tablo_kur` yalnızca takvime bakar; depo M−1'in son gününü henüz
   indirmemişse (arşivin günlük dosyası ertesi gün yayımlanır) `ay_sonu_tolerans_saat` bu
   eksikliği sessizce yutabilir. Referans sembolün M−1'in son saatine kadar barı yoksa
   yenileme **yazmaz**, sonra yeniden denenir.
2. **Geçmiş değişmez:** eski tablodaki her ayın sembol listesi yenide aynı olmalı. Değilse
   yazılmaz; motor zaten geçmiş ayın değişmesini reddederdi (`UyelikTakvimi.ekle`), bu onu
   dosya düzeyinde erkenden yakalar.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.data import evren as evren_mod

SAAT_MS = 3_600_000
REFERANS_SEMBOL = "BTCUSDT"


class EvrenYenilemeHatasi(RuntimeError):
    """Yenileme yazılamadı: geçmiş ay değişti ya da kural uyuşmuyor."""


@dataclass(frozen=True)
class YenilemeSonucu:
    durum: str
    """`guncel` | `m1_eksik` | `yazildi`."""
    son_uye_ay: str
    tablo_hash: str | None = None
    ayrinti: str = ""


def ay_basi_ms(ay: str) -> int:
    t = dt.datetime.strptime(ay, "%Y-%m").replace(tzinfo=dt.UTC)
    return int(t.timestamp() * 1000)


def kurali_coz(meta: dict[str, Any]) -> evren_mod.EvrenKurali:
    k = dict(meta["kural"])
    for alan in ("haric_desenler", "haric_tabanlar"):
        if alan in k:
            k[alan] = tuple(k[alan])
    kural = evren_mod.EvrenKurali(**k)
    if kural.kimlik != meta["kural_kimlik"]:
        raise EvrenYenilemeHatasi(
            f"tablonun kuralı yeniden kurulamadı: {kural.kimlik} ≠ {meta['kural_kimlik']}"
        )
    return kural


def gecmis_aylar_ayni(eski: pd.DataFrame, yeni: pd.DataFrame) -> list[str]:
    """Eski tablodaki aylardan sembol listesi değişenler (boşsa geçmiş aynı)."""

    def listeler(df: pd.DataFrame) -> dict[str, list[str]]:
        return {a: g.sort_values("sira")["sembol"].tolist() for a, g in df.groupby("ay")}

    e, y = listeler(eski), listeler(yeni)
    return sorted(a for a in e if y.get(a) != e[a])


def _atomik_yaz(yol: Path, yaz) -> None:
    gecici = yol.with_name(yol.name + ".tmp")
    yaz(gecici)
    os.replace(gecici, yol)


def yenile(
    hedef: Path,
    depo: Any,
    semboller: list[str],
    *,
    simdi: int | None = None,
    referans: str = REFERANS_SEMBOL,
) -> YenilemeSonucu:
    """`hedef` tablosunu içinde bulunulan aya kadar uzatır. İdempotent."""
    hedef = Path(hedef)
    meta = json.loads(hedef.with_suffix(".json").read_text(encoding="utf-8"))
    simdi = simdi_ms() if simdi is None else simdi
    ay = str(pd.Timestamp(simdi, unit="ms").strftime("%Y-%m"))
    if meta["son_uye_ay"] >= ay:
        return YenilemeSonucu("guncel", meta["son_uye_ay"], meta["tablo_hash"])

    kural = kurali_coz(meta)  # M−1 kontrolünden önce: bozuk kural her gün sessizce beklemesin
    son_gereken = ay_basi_ms(ay) - SAAT_MS
    ref = depo.oku(referans, meta["timeframe"])
    son_bar = int(ref["open_time"].max()) if len(ref) else -1
    if son_bar < son_gereken:
        return YenilemeSonucu(
            "m1_eksik", meta["son_uye_ay"], meta["tablo_hash"],
            f"{referans} son bar {utc_str(son_bar)} < {utc_str(son_gereken)}",
        )

    kirilma = meta["kimlik_kirilmasi"]
    sonuc = evren_mod.tablo_kur(
        depo, semboller, kural, son_uye_ay=ay, timeframe=meta["timeframe"],
        asgari_eksik_bar=kirilma["asgari_eksik_bar"], asgari_log_oran=kirilma["asgari_log_oran"],
    )
    eski = pd.read_parquet(hedef)
    degisen = gecmis_aylar_ayni(eski, sonuc.tablo)
    if degisen:
        raise EvrenYenilemeHatasi(f"geçmiş ayların listesi değişti: {degisen[:5]}")

    tablo_hash = evren_mod.tablo_hash(sonuc.tablo)
    yeni_meta = {
        **{k: v for k, v in meta.items() if k not in ("veri_sha256", "kirilmalar")},
        "uretildi": utc_str(simdi_ms()),
        "son_uye_ay": ay,
        "tablo": str(hedef),
        "tablo_hash": tablo_hash,
        "ay_sayisi": int(sonuc.tablo["ay"].nunique()),
        "satir": len(sonuc.tablo),
        "onceki_tablo_hash": meta["tablo_hash"],
        "veri_sha256": dict(sorted(sonuc.veri_sha256.items())),
    }
    # Önce meta, sonra parquet: koşu parquet'in mtime'ına bakıp ikisini birlikte okur.
    _atomik_yaz(hedef.with_suffix(".json"), lambda p: p.write_text(
        json.dumps(yeni_meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n"))
    _atomik_yaz(hedef, lambda p: sonuc.tablo.to_parquet(p, index=False))
    return YenilemeSonucu("yazildi", ay, tablo_hash, f"{len(sonuc.tablo)} satır")
