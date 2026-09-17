"""ALFRED (FRED vintage) indirme — araştırma ve canlı aynı kodla. (Faz 12, Faz 14 F)

`tools/faz12_makro_indir.py` araştırma deposunu bununla kurdu; canlı evren koşusu
(`evren_makro_nfci`) günlük PIT değerini de bununla ve `data/makro.pit_gunluk` ile üretir.

- FRED dosya tipi başına 2.000 vintage tarihi sınırı var; istek realtime penceresi yıl yıl
  bölünerek atılır ve birleştirilir.
- Değeri `.` olan satır "o vintage'da değer yok" demektir; NaN saklanır, uydurulmaz.
- **API anahtarı hiçbir dosyaya ve loga yazılmaz**; kayıtlara giden parametreler anahtarsızdır.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Final

import pandas as pd
import requests

UC: Final = "https://api.stlouisfed.org/fred/series/observations"


class AlfredHatasi(RuntimeError):
    """ALFRED isteği başarısız ya da kaynak tutarsız."""


def anahtar_oku(env_yolu: str | Path) -> str:
    """`.env`deki `FRED_API_KEY`. Değer döndürülür, hiçbir yere yazılmaz."""
    yol = Path(env_yolu)
    if yol.is_file():
        for satir in yol.read_text(encoding="utf-8").splitlines():
            if satir.startswith("FRED_API_KEY="):
                deger = satir.split("=", 1)[1].strip().strip('"')
                if deger:
                    return deger
    raise AlfredHatasi(f"FRED_API_KEY {yol} içinde yok")


def _istek(params: dict[str, str], anahtar: str) -> bytes | None:
    """Yanıt gövdesi; realtime penceresi serinin ALFRED geçmişinden önceyse `None`."""
    for deneme in range(5):
        try:
            r = requests.get(UC, params={**params, "api_key": anahtar}, timeout=90)
            if r.status_code == 200:
                return r.content
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(str(r.status_code))
            mesaj = r.json().get("error_message", "")
            if r.status_code == 400 and "does not exist in ALFRED" in mesaj:
                return None
            raise AlfredHatasi(f"{params['series_id']}: HTTP {r.status_code} {mesaj}")
        except requests.RequestException:
            time.sleep(2**deneme)
    raise AlfredHatasi(f"{params['series_id']}: 5 denemede indirilemedi")


def vintage_indir(sid: str, anahtar: str, *, gozlem_basi: str, realtime_basi_yil: int,
                  bu_yil: int | None = None) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Serinin `realtime_basi_yil`dan bugüne bütün vintage satırları + parça kaydı."""
    satirlar: list[dict[str, Any]] = []
    parcalar: list[dict[str, Any]] = []
    bu_yil = pd.Timestamp.now(tz="UTC").year if bu_yil is None else bu_yil
    for yil in range(realtime_basi_yil, bu_yil + 1):
        params = {
            "series_id": sid,
            "file_type": "json",
            "observation_start": gozlem_basi,
            "realtime_start": f"{yil}-01-01",
            "realtime_end": f"{yil}-12-31" if yil < bu_yil else "9999-12-31",
        }
        govde = _istek(params, anahtar)
        if govde is None:
            # Bu realtime penceresinde vintage yok: seri ALFRED'e daha geç girmiş. O yılın
            # "o gün ne biliniyordu" cevabı yoktur ve uydurulmaz; kayda geçer.
            parcalar.append({"params": params, "sha256": None, "vintage_yok": True})
            continue
        parcalar.append({"params": params, "sha256": hashlib.sha256(govde).hexdigest()})
        satirlar.extend(json.loads(govde)["observations"])
    if not satirlar:
        raise AlfredHatasi(f"{sid}: hiçbir realtime penceresinde vintage yok")
    df = pd.DataFrame(satirlar, columns=["date", "realtime_start", "realtime_end", "value"])
    df["value"] = pd.to_numeric(df["value"].where(df["value"] != "."), errors="coerce")
    # Yıl pencereleri sınırda aynı vintage'ı iki kez döndürebilir; aynı (gözlem, vintage
    # başı) çiftinin değeri aynı olmak zorunda — değilse kaynak tutarsız, kabul edilmez.
    cift = df.groupby(["date", "realtime_start"])["value"].nunique(dropna=False)
    if (cift > 1).any():
        raise AlfredHatasi(f"{sid}: aynı vintage için iki farklı değer — kaynak tutarsız")
    df = df.drop_duplicates(["date", "realtime_start"]).sort_values(["date", "realtime_start"])
    return df.reset_index(drop=True), parcalar


class AlfredMakroKaynagi:
    """Canlı evren koşusunun makro kaynağı: istenen günlerin gün sonunda bilinen değeri.

    Vintage'lar araştırmayla aynı fonksiyonla iner (`vintage_indir`), değer aynı PIT kuralıyla
    çıkar (`data/makro.pit_gunluk`). İstenen en erken günün yılından bugüne realtime
    pencereleri, gözlemler o günden 120 gün öncesinden (haftalık seride son görünen gözlem
    birkaç hafta geride olabilir).
    """

    def __init__(self, anahtar: str) -> None:
        self._anahtar = anahtar

    def gunluk(self, kisa: str, gunler: Any) -> Any:
        import numpy as np

        from scryne_quant.data import makro as makro_mod

        gunler = np.asarray(gunler, dtype="int64")
        ilk = pd.Timestamp(int(gunler.min()), unit="D")
        df, _ = vintage_indir(makro_mod.SERILER[kisa], self._anahtar,
                              gozlem_basi=(ilk - pd.Timedelta(days=120)).strftime("%Y-%m-%d"),
                              realtime_basi_yil=ilk.year)
        return makro_mod.pit_gunluk(df, gunler)


__all__ = ["UC", "AlfredHatasi", "AlfredMakroKaynagi", "anahtar_oku", "vintage_indir"]
