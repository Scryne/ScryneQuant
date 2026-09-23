"""Aktif bot defteri: işlemler, özkaynak izi, fren durumu, haftalık karne. (K-134)

Tek SQLite dosyası (`defter.sqlite`) koşu dizininde. Karne yalnız bu kayıttan hesaplanır;
aracının kendi raporuyla karşılaştırmak ayrı iştir.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

from scryne_quant.aktif.araci import Dolum
from scryne_quant.aktif.risk import FrenDurumu

SEMA = """
CREATE TABLE IF NOT EXISTS islem (
    zaman_ms INTEGER NOT NULL, sembol TEXT NOT NULL, adet REAL NOT NULL, fiyat REAL NOT NULL,
    notional REAL NOT NULL, ucret REAL NOT NULL, neden TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ozkaynak (zaman_ms INTEGER PRIMARY KEY, deger REAL NOT NULL);
CREATE TABLE IF NOT EXISTS olay (
    zaman_ms INTEGER NOT NULL, tur TEXT NOT NULL, ayrinti TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS durum (anahtar TEXT PRIMARY KEY, deger TEXT NOT NULL);
"""


class Defter:
    def __init__(self, dizin: Path) -> None:
        Path(dizin).mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(Path(dizin) / "defter.sqlite")
        self._db.executescript(SEMA)

    def kapat(self) -> None:
        self._db.close()

    def islem(self, zaman_ms: int, dolum: Dolum, notional: float, neden: str) -> None:
        self._db.execute(
            "INSERT INTO islem VALUES (?,?,?,?,?,?,?)",
            (zaman_ms, dolum.sembol, dolum.adet, dolum.fiyat, notional, dolum.ucret, neden),
        )
        self._db.commit()

    def ozkaynak(self, zaman_ms: int, deger: float) -> None:
        self._db.execute("INSERT OR REPLACE INTO ozkaynak VALUES (?,?)", (zaman_ms, deger))
        self._db.commit()

    def olay(self, zaman_ms: int, tur: str, ayrinti: dict[str, Any]) -> None:
        self._db.execute(
            "INSERT INTO olay VALUES (?,?,?)",
            (zaman_ms, tur, json.dumps(ayrinti, ensure_ascii=False)),
        )
        self._db.commit()

    def fren_oku(self) -> FrenDurumu:
        satir = self._db.execute("SELECT deger FROM durum WHERE anahtar='fren'").fetchone()
        return FrenDurumu.sozlukten(json.loads(satir[0])) if satir else FrenDurumu()

    def fren_yaz(self, fren: FrenDurumu) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO durum VALUES ('fren', ?)", (json.dumps(fren.sozluk()),)
        )
        self._db.commit()

    def karne(self) -> list[dict[str, Any]]:
        """ISO hafta başına: başlangıç/bitiş özkaynağı, getiri, işlem sayısı, ücret, en kötü gün."""
        ozk = self._db.execute("SELECT zaman_ms, deger FROM ozkaynak ORDER BY zaman_ms").fetchall()
        islemler = self._db.execute("SELECT zaman_ms, notional, ucret FROM islem").fetchall()
        haftalar: dict[str, dict[str, Any]] = {}
        # Dönem getirileri zincirlenir: bir günün/haftanın tabanı, önceki dönemin son değeri.
        onceki: float | None = None
        gun_son: dict[str, tuple[str, float, float]] = {}  # gün → (hafta, taban, son)

        def anahtarlar(ms: int) -> tuple[str, str]:
            an = dt.datetime.fromtimestamp(ms / 1000, tz=dt.UTC)
            y, h, _ = an.isocalendar()
            return f"{y}-W{h:02d}", an.strftime("%Y-%m-%d")

        for ms, deger in ozk:
            hafta, gun = anahtarlar(ms)
            taban = deger if onceki is None else onceki
            k = haftalar.setdefault(hafta, {"hafta": hafta, "bas": taban, "son": deger,
                                            "islem": 0, "hacim": 0.0, "ucret": 0.0})
            k["son"] = deger
            g = gun_son.get(gun)
            gun_son[gun] = (hafta, taban if g is None else g[1], deger)
            onceki = deger
        for ms, notional, ucret in islemler:
            hafta, _ = anahtarlar(ms)
            k = haftalar.get(hafta)
            if k is None:
                continue
            k["islem"] += 1
            k["hacim"] += abs(notional)
            k["ucret"] += ucret
        for k in haftalar.values():
            k["getiri"] = k["son"] / k["bas"] - 1.0 if k["bas"] else 0.0
            gunluk = [son / taban - 1.0 for h, taban, son in gun_son.values()
                      if h == k["hafta"] and taban]
            k["en_kotu_gun"] = min(gunluk) if gunluk else 0.0
        return [haftalar[h] for h in sorted(haftalar)]
