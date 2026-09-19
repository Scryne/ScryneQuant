"""Jev karar defteri: silinemez, zincir hash'li, durumu da taşıyan SQLite kaydı. (K-074/5, §33-34)

`risk/audit.py::SqliteDefter`in kalıbı: append-only (UPDATE/DELETE tetikleyicileri), her satır
öncekinin hash'ini taşır, `dogrula()` zinciri baştan hesaplar. Aynı sınıf yeniden
kullanılmıyor çünkü orası risk olaylarının (`OlayTuru`) defteri; buradaki satır bir karar,
bir durum ve bir ham yanıt. Kalıp aynı, tablo ayrı — ayrı süreç, ayrı dosya, ayrı zincir
(K-074/5: Jev'in defteri trading defterine karışmaz).

**Üç tablo, bir dosya** (`runs/jev/<kosu>.sqlite`):

- `kosu` — tek satır: koşu kimliği, ayarlar, soru hash'i, git durumu, ortam (K-009).
- `karar` — her bar bir satır: `JevKarari` (JSON), **kanonik durumun kendisi** (bytes) ve ham
  yanıt (JSON). Durum satırda duruyor ki spec §6'nın "her kararın girdi state'i sonradan
  bulunabilmeli" şartı bir dosya aramasına bağlı olmasın; hash ayrıca sütunda ve indeksli.
- `olay` — süreç günlüğü: başladı, durdu, hata, tutarlılık ölçümü, sürüm uyuşmazlığı.

**Sır yok.** Yazılan her serbest metin `istemci.sir_temizle`den geçer; durum ve yanıt zaten
sırsız (istemci taradı). Anahtar hiçbir sütunda bulunmaz.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.hash import git_durumu, nesne_hash, ortam_kaydi
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.jev.ayarlar import JevAyarlari
from scryne_quant.jev.durum import kanonik_json
from scryne_quant.jev.istemci import sir_temizle
from scryne_quant.jev.karar import JevKarari

KOK_HASH: Final = "0" * 64
BELLEK: Final = ":memory:"


class DefterHatasi(RuntimeError):
    """Defter sözleşmesi ihlal edildi (çift karar, hash uyuşmazlığı, bozuk zincir)."""


class OlayTuru(StrEnum):
    BASLADI = "basladi"
    DURDU = "durdu"
    HATA = "hata"
    TUTARLILIK = "tutarlilik"
    """Aynı durum ikinci kez soruldu; olasılık sapması `ayrinti`de (K-074/6)."""

    SURUM_UYUSMAZ = "surum_uyusmaz"
    BAYAT_VERI = "bayat_veri"
    BAR_ATLANDI = "bar_atlandi"
    """`ok` olmayan bar ya da eksik pencere: durum kurulmadı, Jev'e sorulmadı."""


@dataclass(frozen=True, slots=True)
class KosuKimligi:
    kosu: str
    sembol: str
    mod: str
    """`golge` ya da `tekrar` (replay)."""

    ayarlar: dict[str, Any]
    soru_sha256: str
    baslangic_ms: int
    git: dict[str, Any]
    ortam: dict[str, Any]

    def sozluk(self) -> dict[str, Any]:
        return {
            "kosu": self.kosu,
            "sembol": self.sembol,
            "mod": self.mod,
            "ayarlar": self.ayarlar,
            "soru_sha256": self.soru_sha256,
            "baslangic_ms": self.baslangic_ms,
            "baslangic_utc": utc_str(self.baslangic_ms),
            "git": self.git,
            "ortam": self.ortam,
        }


def kosu_kimligi_kur(kosu: str, mod: str, ayarlar: JevAyarlari, soru_sha256: str) -> KosuKimligi:
    if mod not in ("golge", "tekrar"):
        raise DefterHatasi(f"mod `golge` ya da `tekrar` olmalı: {mod!r}")
    return KosuKimligi(
        kosu=kosu,
        sembol=ayarlar.sembol,
        mod=mod,
        ayarlar=ayarlar.sozluk(),
        soru_sha256=soru_sha256,
        baslangic_ms=simdi_ms(),
        git=git_durumu(),
        ortam=ortam_kaydi(),
    )


_SEMA: Final = """
CREATE TABLE IF NOT EXISTS kosu (
    tek         INTEGER PRIMARY KEY CHECK (tek = 1),
    govde       TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS karar (
    id          INTEGER PRIMARY KEY,
    karar_id    TEXT    NOT NULL UNIQUE,
    karar_ms    INTEGER NOT NULL,
    uretim_ms   INTEGER NOT NULL,
    yazim_ms    INTEGER NOT NULL,
    durum_kodu  TEXT    NOT NULL,
    durum_hash  TEXT    NOT NULL,
    durum_json  BLOB    NOT NULL,
    yanit_json  TEXT,
    karar_json  TEXT    NOT NULL,
    onceki_hash TEXT    NOT NULL,
    satir_hash  TEXT    NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS karar_zaman ON karar (karar_ms);
CREATE INDEX IF NOT EXISTS karar_durum_hash ON karar (durum_hash);
CREATE TABLE IF NOT EXISTS olay (
    id          INTEGER PRIMARY KEY,
    tur         TEXT    NOT NULL,
    zaman_ms    INTEGER NOT NULL,
    ayrinti     TEXT    NOT NULL
);
CREATE TRIGGER IF NOT EXISTS karar_guncelleme_yok BEFORE UPDATE ON karar
BEGIN SELECT RAISE(ABORT, 'jev karar defteri append-only: UPDATE yasak (K-074/5)'); END;
CREATE TRIGGER IF NOT EXISTS karar_silme_yok BEFORE DELETE ON karar
BEGIN SELECT RAISE(ABORT, 'jev karar defteri append-only: DELETE yasak (K-074/5)'); END;
CREATE TRIGGER IF NOT EXISTS olay_guncelleme_yok BEFORE UPDATE ON olay
BEGIN SELECT RAISE(ABORT, 'jev olay gunlugu append-only'); END;
CREATE TRIGGER IF NOT EXISTS olay_silme_yok BEFORE DELETE ON olay
BEGIN SELECT RAISE(ABORT, 'jev olay gunlugu append-only'); END;
"""


def satir_hashi(
    karar: JevKarari, durum_json: bytes, yanit: Mapping[str, Any] | None, onceki: str
) -> str:
    return nesne_hash(
        {
            "karar": karar.sozluk(),
            "durum_sha256": nesne_hash(durum_json.decode("utf-8")),
            "yanit": None if yanit is None else dict(yanit),
            "onceki": onceki,
        }
    )


class JevDefteri:
    """Bir Jev koşusunun tamamı: kimlik, kararlar, olaylar. Tek yazıcı."""

    def __init__(self, yol: str | Path = BELLEK) -> None:
        self.yol = Path(yol) if str(yol) != BELLEK else None
        if self.yol is not None:
            self.yol.parent.mkdir(parents=True, exist_ok=True)
        self._kilit = threading.RLock()
        self._baglanti = sqlite3.connect(str(yol), isolation_level=None, check_same_thread=False)
        self._baglanti.row_factory = sqlite3.Row
        if self.yol is not None:
            self._baglanti.execute("PRAGMA journal_mode=WAL")
        self._baglanti.executescript(_SEMA)

    # ------------------------------------------------------------------ koşu

    def kosu_yaz(self, kimlik: KosuKimligi) -> None:
        with self._kilit:
            mevcut = self.kosu_oku()
            if mevcut is not None:
                if mevcut["kosu"] != kimlik.kosu or mevcut["soru_sha256"] != kimlik.soru_sha256:
                    raise DefterHatasi(
                        "defter başka bir koşuya ya da başka bir soru setine ait; yeni dosya aç"
                    )
                return
            self._baglanti.execute(
                "INSERT INTO kosu (tek, govde) VALUES (1, ?)", (_json(kimlik.sozluk()),)
            )

    def kosu_oku(self) -> dict[str, Any] | None:
        with self._kilit:
            s = self._baglanti.execute("SELECT govde FROM kosu WHERE tek = 1").fetchone()
        return None if s is None else json.loads(s["govde"])

    # ------------------------------------------------------------------ karar

    def karar_yaz(
        self, karar: JevKarari, durum: Mapping[str, Any], yanit: Mapping[str, Any] | None
    ) -> str:
        """Kararı, kanonik durumu ve ham yanıtı tek satırda yazar; zincir hash'ini döndürür.

        Aynı `karar_ms` için ikinci bir **geçerli** karar yazılamaz: aynı bar iki kez
        sorulmuşsa ikincisi `tutarlilik_yaz` ile olay olarak kaydedilir, karar olarak değil.
        Geçersiz kayıttan sonra aynı bar yeniden denenebilir (fail-closed'un kendisi bir karar
        değildir), ama her deneme ayrı satırdır ve hiçbiri silinmez.
        """
        durum_json = kanonik_json(durum)
        beklenen = nesne_hash(durum)
        if karar.durum_hash != beklenen:
            raise DefterHatasi(
                f"karar durum hash'i {karar.durum_hash[:12]} verilen durumla "
                f"{beklenen[:12]} uyuşmuyor"
            )
        with self._kilit:
            if karar.gecerli and self._gecerli_var_mi(karar.karar_ms):
                raise DefterHatasi(
                    f"{karar.karar_ms} barı için geçerli karar zaten var; ikinci sorgu "
                    "`tutarlilik_yaz` ile kaydedilir"
                )
            onceki = self._son_hash()
            h = satir_hashi(karar, durum_json, yanit, onceki)
            self._baglanti.execute(
                "INSERT INTO karar (karar_id, karar_ms, uretim_ms, yazim_ms, durum_kodu, "
                "durum_hash, durum_json, yanit_json, karar_json, onceki_hash, satir_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    karar.karar_id,
                    karar.karar_ms,
                    karar.uretim_ms,
                    simdi_ms(),
                    str(karar.durum),
                    karar.durum_hash,
                    durum_json,
                    None if yanit is None else _json(dict(yanit)),
                    _json(karar.sozluk()),
                    onceki,
                    h,
                ),
            )
        return h

    def _gecerli_var_mi(self, karar_ms: int) -> bool:
        s = self._baglanti.execute(
            "SELECT 1 FROM karar WHERE karar_ms = ? AND durum_kodu = 'gecerli' LIMIT 1",
            (karar_ms,),
        ).fetchone()
        return s is not None

    def _son_hash(self) -> str:
        s = self._baglanti.execute(
            "SELECT satir_hash FROM karar ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return KOK_HASH if s is None else str(s["satir_hash"])

    def kararlar(
        self, *, limit: int | None = None, yalniz_gecerli: bool = False
    ) -> list[dict[str, Any]]:
        sorgu = "SELECT * FROM karar"
        if yalniz_gecerli:
            sorgu += " WHERE durum_kodu = 'gecerli'"
        sorgu += " ORDER BY id"
        p: list[Any] = []
        if limit is not None:
            sorgu += " LIMIT ?"
            p.append(limit)
        with self._kilit:
            return [self._satir(s) for s in self._baglanti.execute(sorgu, p)]

    def durum_bul(self, durum_hash: str) -> dict[str, Any] | None:
        """Hash'ten kanonik durumu geri getirir (spec §17: aynı girdi kullanıldı mı kontrolü)."""
        with self._kilit:
            s = self._baglanti.execute(
                "SELECT durum_json FROM karar WHERE durum_hash = ? LIMIT 1", (durum_hash,)
            ).fetchone()
        return None if s is None else json.loads(bytes(s["durum_json"]).decode("utf-8"))

    def son_karar_ms(self) -> int | None:
        with self._kilit:
            s = self._baglanti.execute("SELECT MAX(karar_ms) AS m FROM karar").fetchone()
        return None if s is None or s["m"] is None else int(s["m"])

    def sayim(self) -> dict[str, int]:
        with self._kilit:
            return {
                str(s["durum_kodu"]): int(s["n"])
                for s in self._baglanti.execute(
                    "SELECT durum_kodu, COUNT(*) AS n FROM karar GROUP BY durum_kodu"
                )
            }

    @staticmethod
    def _satir(s: sqlite3.Row) -> dict[str, Any]:
        k = dict(s)
        k["karar"] = json.loads(k.pop("karar_json"))
        k["durum"] = json.loads(bytes(k.pop("durum_json")).decode("utf-8"))
        y = k.pop("yanit_json")
        k["yanit"] = None if y is None else json.loads(y)
        k["karar_utc"] = utc_str(int(k["karar_ms"]))
        return k

    # ------------------------------------------------------------------ olay

    def olay_yaz(
        self,
        tur: OlayTuru,
        ayrinti: Mapping[str, Any] | None = None,
        *,
        zaman_ms: int | None = None,
    ) -> None:
        temiz = json.loads(sir_temizle(_json(dict(ayrinti or {}))))
        with self._kilit:
            self._baglanti.execute(
                "INSERT INTO olay (tur, zaman_ms, ayrinti) VALUES (?, ?, ?)",
                (str(tur), simdi_ms() if zaman_ms is None else zaman_ms, _json(temiz)),
            )

    def tutarlilik_yaz(self, ilk: JevKarari, ikinci: JevKarari) -> dict[str, Any]:
        """Aynı durumun ikinci sorgusu: sapma hesaplanır ve olay olarak yazılır (K-074/6)."""
        if ilk.durum_hash != ikinci.durum_hash:
            raise DefterHatasi("tutarlılık ölçümü aynı durum hash'ini ister")
        ayrinti: dict[str, Any] = {
            "karar_ms": ilk.karar_ms,
            "durum_hash": ilk.durum_hash,
            "ilk_karar_id": ilk.karar_id,
            "ikinci_karar_id": ikinci.karar_id,
            "ikisi_gecerli": ilk.gecerli and ikinci.gecerli,
        }
        if ilk.gecerli and ikinci.gecerli:
            assert ilk.yon_olasiliklari and ikinci.yon_olasiliklari
            assert ilk.rejim_olasiliklari and ikinci.rejim_olasiliklari
            ayrinti["yon_sapma"] = max(
                abs(ilk.yon_olasiliklari[y] - ikinci.yon_olasiliklari[y])
                for y in ilk.yon_olasiliklari
            )
            ayrinti["rejim_sapma"] = max(
                abs(ilk.rejim_olasiliklari[r] - ikinci.rejim_olasiliklari[r])
                for r in ilk.rejim_olasiliklari
            )
            ayrinti["yon_etiketi_ayni"] = ilk.yon == ikinci.yon
            ayrinti["kurulum_sapma"] = abs(float(ilk.kurulum_skor) - float(ikinci.kurulum_skor))  # type: ignore[arg-type]
            ayrinti["cekimser_sapma"] = abs(float(ilk.cekimser) - float(ikinci.cekimser))  # type: ignore[arg-type]
        self.olay_yaz(OlayTuru.TUTARLILIK, ayrinti, zaman_ms=ikinci.uretim_ms)
        return ayrinti

    def olaylar(
        self, *, tur: OlayTuru | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        sorgu, p = "SELECT * FROM olay", []
        if tur is not None:
            sorgu += " WHERE tur = ?"
            p.append(str(tur))
        sorgu += " ORDER BY id"
        if limit is not None:
            sorgu += " LIMIT ?"
            p.append(limit)
        with self._kilit:
            return [
                {
                    **dict(s),
                    "ayrinti": json.loads(s["ayrinti"]),
                    "zaman_utc": utc_str(int(s["zaman_ms"])),
                }
                for s in self._baglanti.execute(sorgu, p)
            ]

    # ------------------------------------------------------------------ doğrulama

    def dogrula(self) -> bool:
        """Zinciri baştan hesaplar; tek satır oynamışsa `False`."""
        onceki = KOK_HASH
        with self._kilit:
            satirlar = list(self._baglanti.execute("SELECT * FROM karar ORDER BY id"))
        for s in satirlar:
            karar = JevKarari(**json.loads(s["karar_json"]))
            yanit = None if s["yanit_json"] is None else json.loads(s["yanit_json"])
            if s["onceki_hash"] != onceki:
                return False
            beklenen = satir_hashi(karar, bytes(s["durum_json"]), yanit, onceki)
            if s["satir_hash"] != beklenen:
                return False
            if nesne_hash(json.loads(bytes(s["durum_json"]).decode("utf-8"))) != karar.durum_hash:
                return False
            onceki = beklenen
        return True

    def kapat(self) -> None:
        with self._kilit:
            self._baglanti.close()

    def __enter__(self) -> JevDefteri:
        return self

    def __exit__(self, *_: object) -> None:
        self.kapat()


def _json(nesne: Any) -> str:
    return json.dumps(nesne, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = [
    "BELLEK",
    "KOK_HASH",
    "DefterHatasi",
    "JevDefteri",
    "KosuKimligi",
    "OlayTuru",
    "kosu_kimligi_kur",
    "satir_hashi",
]
