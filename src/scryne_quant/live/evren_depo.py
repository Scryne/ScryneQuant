"""Evren paper koşusunun deposu: tek SQLite dosyası, yeniden üretime yetecek her şey. (Faz 14)

Tek sembollü koşu deposu (`live/depo.py`) bir **kontrol noktası** saklıyor ve toparlanmada
bekleyen kararı yeniden üretiyor. Evren motoru bir adım daha ileri gidiyor: durum saklamıyor,
**girdileri** saklıyor ve toparlanmada bütün adımları baştan oynatıyor (K-038: geri yükleme
değil yeniden üretim). Bunun için her girdinin **ne zaman bilindiği** kayıtlı olmalı:

- `bar.bilindi_adim` — bar, o numaralı ızgara adımı işlenmeden **önce** biliniyordu. Geç gelen
  bir bar geçmiş adımların görünümüne sızmaz.
- `uyelik.bilindi_adim` — bir ayın üye listesi o adımdan itibaren kullanılabilir.
- `adim` — her işlenen ızgara barı: zamanı, ısınma mı, eksik semboller, sonuç özeti
  (özkaynak, brüt maruziyet — `repr` ile, kayan nokta **bit düzeyinde** karşılaştırılsın).

`bar`, `adim`, `uyelik`, `olay` tabloları ekleme-yalnız (tetikleyiciyle): kaydedilmiş bir
girdi düzeltilebilseydi yeniden üretim kanıt olmaktan çıkardı.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.zaman import simdi_ms
from scryne_quant.live.akis import Bar, Kaynak

SEMA: Final = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS kosu (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    kimlik   TEXT NOT NULL,
    olustu_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bar (
    sembol       TEXT    NOT NULL,
    open_time    INTEGER NOT NULL,
    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
    volume REAL NOT NULL, quote_volume REAL NOT NULL, trades INTEGER NOT NULL,
    kaynak       TEXT    NOT NULL,
    bilindi_adim INTEGER NOT NULL,
    PRIMARY KEY (sembol, open_time)
);
CREATE TABLE IF NOT EXISTS uyelik (
    ay           TEXT PRIMARY KEY,
    semboller    TEXT    NOT NULL,
    tablo_hash   TEXT    NOT NULL,
    bilindi_adim INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS adim (
    adim       INTEGER PRIMARY KEY,
    open_time  INTEGER NOT NULL UNIQUE,
    isinma     INTEGER NOT NULL,
    eksik      TEXT    NOT NULL,
    ozkaynak   TEXT    NOT NULL,
    brut       TEXT    NOT NULL,
    islem      INTEGER NOT NULL,
    islendi_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS olay (
    id       INTEGER PRIMARY KEY,
    tur      TEXT    NOT NULL,
    zaman_ms INTEGER NOT NULL,
    bar_ms   INTEGER,
    ayrinti  TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS funding (
    sembol       TEXT    NOT NULL,
    calc_time    INTEGER NOT NULL,
    aralik_saat  INTEGER NOT NULL,
    oran         REAL    NOT NULL,
    bilindi_adim INTEGER NOT NULL,
    PRIMARY KEY (sembol, calc_time)
);
CREATE TABLE IF NOT EXISTS premium (
    sembol       TEXT    NOT NULL,
    open_time    INTEGER NOT NULL,
    close        REAL    NOT NULL,
    bilindi_adim INTEGER NOT NULL,
    PRIMARY KEY (sembol, open_time)
);
CREATE TABLE IF NOT EXISTS makro (
    seri         TEXT    NOT NULL,
    gun          INTEGER NOT NULL,
    deger        REAL,
    bilindi_adim INTEGER NOT NULL,
    PRIMARY KEY (seri, gun, bilindi_adim)
);
CREATE TRIGGER IF NOT EXISTS makro_degismez BEFORE UPDATE ON makro
BEGIN SELECT RAISE(ABORT, 'makro kaydı değiştirilemez'); END;
CREATE TRIGGER IF NOT EXISTS funding_degismez BEFORE UPDATE ON funding
BEGIN SELECT RAISE(ABORT, 'funding kaydı değiştirilemez'); END;
CREATE TRIGGER IF NOT EXISTS premium_degismez BEFORE UPDATE ON premium
BEGIN SELECT RAISE(ABORT, 'premium kaydı değiştirilemez'); END;
CREATE TRIGGER IF NOT EXISTS bar_degismez BEFORE UPDATE ON bar
BEGIN SELECT RAISE(ABORT, 'bar kaydı değiştirilemez'); END;
CREATE TRIGGER IF NOT EXISTS bar_silinmez BEFORE DELETE ON bar
BEGIN SELECT RAISE(ABORT, 'bar kaydı silinemez'); END;
CREATE TRIGGER IF NOT EXISTS adim_degismez BEFORE UPDATE ON adim
BEGIN SELECT RAISE(ABORT, 'adım kaydı değiştirilemez'); END;
CREATE TRIGGER IF NOT EXISTS adim_silinmez BEFORE DELETE ON adim
BEGIN SELECT RAISE(ABORT, 'adım kaydı silinemez'); END;
CREATE TRIGGER IF NOT EXISTS uyelik_degismez BEFORE UPDATE ON uyelik
BEGIN SELECT RAISE(ABORT, 'üyelik kaydı değiştirilemez'); END;
CREATE TRIGGER IF NOT EXISTS olay_degismez BEFORE UPDATE ON olay
BEGIN SELECT RAISE(ABORT, 'olay kaydı değiştirilemez'); END;
"""


class EvrenDepoHatasi(RuntimeError):
    """Depo sözleşmesi ihlal edildi."""


@dataclass(frozen=True, slots=True)
class KayitliBar:
    sembol: str
    bar: Bar
    bilindi_adim: int


@dataclass(frozen=True, slots=True)
class KayitliAdim:
    adim: int
    open_time: int
    isinma: bool
    eksik: tuple[str, ...]
    ozkaynak: float
    brut: float
    islem: int


class EvrenKosuDeposu:
    def __init__(self, yol: str | Path) -> None:
        self.yol = Path(yol)
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        self._baglanti = sqlite3.connect(self.yol, isolation_level=None)
        self._baglanti.executescript(SEMA)

    def kapat(self) -> None:
        self._baglanti.close()

    # ------------------------------------------------------------------ kimlik

    def kimlik_yaz(self, kimlik: dict[str, Any]) -> None:
        """İlk açılışta yazar; sonraki açılışta **aynı** olmak zorunda (K-009)."""
        metin = json.dumps(kimlik, ensure_ascii=False, sort_keys=True)
        satir = self._baglanti.execute("SELECT kimlik FROM kosu WHERE id = 1").fetchone()
        if satir is None:
            self._baglanti.execute("INSERT INTO kosu VALUES (1, ?, ?)", (metin, simdi_ms()))
        elif satir[0] != metin:
            raise EvrenDepoHatasi(
                "bu koşu farklı bir konfigürasyonla açılmış; aynı ada farklı konfigürasyon "
                "yazılamaz, yeni bir koşu adı verin (K-009)"
            )

    def kimlik_oku(self) -> dict[str, Any] | None:
        satir = self._baglanti.execute("SELECT kimlik FROM kosu WHERE id = 1").fetchone()
        return None if satir is None else json.loads(satir[0])

    # ------------------------------------------------------------------ girdiler

    def bar_yaz(self, sembol: str, bar: Bar, bilindi_adim: int) -> bool:
        """Barı ekler. Aynı `(sembol, open_time)` zaten varsa **eklemez** ve `False` döner.

        Borsa kapanmış bir barı revize ederse ilk kayıt kalır: karar o bar ile verildi.
        """
        try:
            self._baglanti.execute(
                "INSERT INTO bar VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (sembol, bar.open_time, bar.open, bar.high, bar.low, bar.close, bar.volume,
                 bar.quote_volume, bar.trades, str(bar.kaynak), bilindi_adim),
            )
        except sqlite3.IntegrityError:
            return False
        return True

    def barlar(self) -> Iterator[KayitliBar]:
        for r in self._baglanti.execute(
            "SELECT sembol, open_time, open, high, low, close, volume, quote_volume, trades, "
            "kaynak, bilindi_adim FROM bar ORDER BY bilindi_adim, sembol, open_time"
        ):
            yield KayitliBar(
                r[0],
                Bar(open_time=r[1], open=r[2], high=r[3], low=r[4], close=r[5], volume=r[6],
                    quote_volume=r[7], trades=r[8], kaynak=Kaynak(r[9])),
                r[10],
            )

    def uyelik_yaz(self, ay: str, semboller: tuple[str, ...], tablo_hash: str,
                   bilindi_adim: int) -> bool:
        try:
            self._baglanti.execute("INSERT INTO uyelik VALUES (?,?,?,?)",
                                   (ay, json.dumps(list(semboller)), tablo_hash, bilindi_adim))
        except sqlite3.IntegrityError:
            return False
        return True

    def uyelikler(self) -> list[tuple[str, tuple[str, ...], str, int]]:
        return [(r[0], tuple(json.loads(r[1])), r[2], r[3]) for r in self._baglanti.execute(
            "SELECT ay, semboller, tablo_hash, bilindi_adim FROM uyelik ORDER BY bilindi_adim, ay")]

    # ------------------------------------------------------------------ türev girdileri

    def funding_yaz(self, sembol: str, calc_time: int, aralik_saat: int, oran: float,
                    bilindi_adim: int) -> bool:
        """Funding ödemesi (Faz 14 Aşama F). İlk kayıt kalır, bar ile aynı kural."""
        try:
            self._baglanti.execute("INSERT INTO funding VALUES (?,?,?,?,?)",
                                   (sembol, calc_time, aralik_saat, oran, bilindi_adim))
        except sqlite3.IntegrityError:
            return False
        return True

    def fundingler(self) -> list[tuple[str, int, int, float, int]]:
        return list(self._baglanti.execute(
            "SELECT sembol, calc_time, aralik_saat, oran, bilindi_adim FROM funding "
            "ORDER BY bilindi_adim, sembol, calc_time"))

    def premium_yaz(self, sembol: str, open_time: int, close: float, bilindi_adim: int) -> bool:
        try:
            self._baglanti.execute("INSERT INTO premium VALUES (?,?,?,?)",
                                   (sembol, open_time, close, bilindi_adim))
        except sqlite3.IntegrityError:
            return False
        return True

    def premiumlar(self) -> list[tuple[str, int, float, int]]:
        return list(self._baglanti.execute(
            "SELECT sembol, open_time, close, bilindi_adim FROM premium "
            "ORDER BY bilindi_adim, sembol, open_time"))

    def makro_yaz(self, seri: str, gun: int, deger: float | None, bilindi_adim: int) -> bool:
        """Bir günün gün sonunda bilinen PIT değeri (`NaN` → `NULL`). Aynı gün sonradan
        farklı bilinirse yeni satır (revizyon kaydı); görünüm en son bilineni alır."""
        try:
            self._baglanti.execute(
                "INSERT INTO makro VALUES (?,?,?,?)",
                (seri, gun, None if deger is None or deger != deger else deger, bilindi_adim))
        except sqlite3.IntegrityError:
            return False
        return True

    def makrolar(self) -> list[tuple[str, int, float, int]]:
        return [(r[0], r[1], float("nan") if r[2] is None else r[2], r[3])
                for r in self._baglanti.execute(
                    "SELECT seri, gun, deger, bilindi_adim FROM makro "
                    "ORDER BY bilindi_adim, seri, gun")]

    # ------------------------------------------------------------------ adımlar

    def adim_yaz(self, a: KayitliAdim) -> None:
        self._baglanti.execute(
            "INSERT INTO adim VALUES (?,?,?,?,?,?,?,?)",
            (a.adim, a.open_time, int(a.isinma), json.dumps(list(a.eksik)), repr(a.ozkaynak),
             repr(a.brut), a.islem, simdi_ms()),
        )

    def adimlar(self) -> list[KayitliAdim]:
        return [
            KayitliAdim(r[0], r[1], bool(r[2]), tuple(json.loads(r[3])), float(r[4]),
                        float(r[5]), r[6])
            for r in self._baglanti.execute(
                "SELECT adim, open_time, isinma, eksik, ozkaynak, brut, islem FROM adim "
                "ORDER BY adim")
        ]

    def olay_yaz(self, tur: str, *, bar_ms: int | None = None,
                 ayrinti: dict[str, Any] | None = None) -> None:
        self._baglanti.execute(
            "INSERT INTO olay (tur, zaman_ms, bar_ms, ayrinti) VALUES (?,?,?,?)",
            (tur, simdi_ms(), bar_ms, json.dumps(ayrinti or {}, ensure_ascii=False, default=str)),
        )

    def olaylar(self) -> list[dict[str, Any]]:
        return [{"tur": r[0], "zaman_ms": r[1], "bar_ms": r[2], "ayrinti": json.loads(r[3])}
                for r in self._baglanti.execute(
                    "SELECT tur, zaman_ms, bar_ms, ayrinti FROM olay ORDER BY id")]


__all__ = ["EvrenDepoHatasi", "EvrenKosuDeposu", "KayitliAdim", "KayitliBar"]
