"""Audit defteri: risk kararlarının silinemez kaydı. (K-008/5, K-011, K-032)

K-008'in beşinci davranışı şu: *"Tetikleyen sebep, o andaki tüm pozisyon ve emir durumuyla
birlikte audit log'a yazılır."* Bu modül o log'un adresi.

**Neden bir arayüz, neden doğrudan PostgreSQL değil.** K-011 operasyonel state'i
PostgreSQL'e veriyor ve gerekçesi net: *"eşzamanlı yazma, transaction ve dayanıklı state
gerektiğinde (paper/live) anlamlı."* Faz 5'te o ihtiyacın hiçbiri yok — tek süreç, tek
yazıcı, canlı emir yok. Ayakta bir veritabanı gerektiren bir test takımı, Faz 5'in kendi
bitti kriterine hiçbir şey katmadan her koşuya bir bağımlılık eklerdi.

Ama yazım **yeri** Faz 6'da değişecekse, yazım **biçimi** şimdi sabitlenmeli: `Defter`
protokolü bugün SQLite'a yazıyor, Faz 6'da PostgreSQL'e yazacak, ve arada değişen tek şey
sınıf adı olacak. Şemanın PostgreSQL karşılığı `migrations/001_faz5.sql`'de şimdiden
duruyor ve `SqliteDefter` ile **aynı kolonları** taşıyor (testle kontrol ediliyor) — yani
Faz 6 bir şema tasarımıyla değil, bir bağlantı dizgisiyle başlıyor. (K-032)

**Append-only, ve bu teknik olarak zorlanıyor.** Defterin `sil`/`guncelle` diye bir metodu
yok; SQLite tarafında ayrıca UPDATE ve DELETE tetikleyicileri tabloyu koruyor. Bir risk
kararının sonradan düzeltilebildiği bir kayıt, kayıt değil not defteridir — ve bu projede
asıl korunan şey altı ay sonraki kendi hafızası.

**Zincir hash'i.** Her satır kendinden öncekinin hash'ini taşıyor. Bu, kurcalamayı
*engellemez* (dosyanın sahibi zinciri baştan yazabilir) ama **sessiz** kurcalamayı
imkânsız kılar: tek bir satırı değiştirmek sonraki tüm satırların hash'ini bozar ve
`dogrula()` bunu söyler. Kendi kaydına karşı kendini dürüst tutmanın ucuz yolu.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.zaman import simdi_ms, utc_str


class OlayTuru(StrEnum):
    """Audit'e yazılan olay türleri. Yeni tür eklemek buraya yazmakla olur."""

    ONAY = "onay"
    """Bir sinyal onaylandı (kısıtlanmış olabilir)."""

    RED = "red"
    """Bir sinyal reddedildi."""

    KILL = "kill"
    """Kill switch tetiklendi; SAFE_MODE açıldı (K-008)."""

    SERBEST = "serbest"
    """SAFE_MODE elle onayla kapatıldı (K-008/4)."""

    COOLDOWN = "cooldown"
    """Ardışık kayıp limiti cooldown başlattı."""

    PROMOTION = "promotion"
    """Promotion zincirinde bir aşama geçildi veya elle onay verildi (K-010)."""


#: Zincirin ilk satırının `onceki_hash`i. Sabit bir değer: boş dize kullanmak, zinciri
#: baştan kesilmiş bir defterle baştan yazılmış defteri ayırt edilemez kılardı.
KOK_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class Olay:
    """Audit defterine yazılan tek satır."""

    tur: OlayTuru
    zaman_ms: int
    """Olayın ait olduğu **bar** zamanı (UTC epoch ms, K-005). Duvar saati değil.

    Bu ayrım önemli: backtest'te duvar saati yazmak, aynı koşunun iki kez çalıştırıldığında
    farklı audit üretmesi demek olurdu. Duvar saati ayrı bir alanda (`yazim_ms`).
    """

    sembol: str
    govde: dict[str, Any]
    """Olayın tam içeriği. `OnayliNiyet.sozluk()` / `Red.sozluk()` buraya gidiyor."""

    durum: dict[str, Any]
    """Karar anındaki risk durumunun tam görüntüsü (K-008/5: "o andaki tüm durumla")."""

    def icerik_hash(self, onceki_hash: str) -> str:
        """Bu satırın zincir hash'i: içerik + öncekinin hash'i."""
        return nesne_hash(
            {
                "tur": str(self.tur),
                "zaman_ms": self.zaman_ms,
                "sembol": self.sembol,
                "govde": self.govde,
                "durum": self.durum,
                "onceki": onceki_hash,
            }
        )


class Defter(Protocol):
    """Audit deposu sözleşmesi. Faz 6'da PostgreSQL bu protokolü uygulayacak."""

    def yaz(self, olay: Olay) -> str:
        """Olayı ekler ve satırın zincir hash'ini döndürür."""
        ...

    def oku(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Olayları yazılma sırasıyla döndürür."""
        ...

    def dogrula(self) -> bool:
        """Zincir tutarlı mı? Tek bir satır değişmişse `False`."""
        ...

    def kapat(self) -> None: ...


#: Kolonların kanonik sırası. `migrations/001_faz5.sql` aynı kolonları aynı adla
#: tanımlıyor; `tests/unit/test_audit.py` ikisinin ayrışmadığını kontrol ediyor.
KOLONLAR: tuple[str, ...] = (
    "id",
    "tur",
    "zaman_ms",
    "yazim_ms",
    "sembol",
    "govde",
    "durum",
    "onceki_hash",
    "satir_hash",
)

_SEMA = """
CREATE TABLE IF NOT EXISTS audit (
    id          INTEGER PRIMARY KEY,
    tur         TEXT    NOT NULL,
    zaman_ms    INTEGER NOT NULL,
    yazim_ms    INTEGER NOT NULL,
    sembol      TEXT    NOT NULL,
    govde       TEXT    NOT NULL,
    durum       TEXT    NOT NULL,
    onceki_hash TEXT    NOT NULL,
    satir_hash  TEXT    NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS audit_zaman ON audit (zaman_ms);
CREATE INDEX IF NOT EXISTS audit_tur   ON audit (tur, zaman_ms);

-- Append-only: kural yorumda değil veritabanında. Bir risk kararının sonradan
-- düzeltilebildiği tablo, kayıt değil not defteridir (K-032).
CREATE TRIGGER IF NOT EXISTS audit_guncelleme_yok
BEFORE UPDATE ON audit
BEGIN
    SELECT RAISE(ABORT, 'audit append-only: UPDATE yasak (K-032)');
END;
CREATE TRIGGER IF NOT EXISTS audit_silme_yok
BEFORE DELETE ON audit
BEGIN
    SELECT RAISE(ABORT, 'audit append-only: DELETE yasak (K-032)');
END;
"""


class SqliteDefter:
    """Faz 5'in audit deposu. Tek süreç, tek yazıcı, dosya tabanlı.

    `:memory:` verilirse testler için bellekte çalışır — ama o hâlde zincir süreçle
    birlikte ölür, dolayısıyla gerçek koşularda kullanılmaz.
    """

    def __init__(self, yol: str | Path = "runs/audit.sqlite") -> None:
        self.yol = Path(yol) if str(yol) != ":memory:" else Path(":memory:")
        if str(yol) != ":memory:":
            self.yol.parent.mkdir(parents=True, exist_ok=True)
        # `check_same_thread=False` + kilit: Faz 6'da bu defter dashboard'un `/api/audit`
        # ucundan da okunuyor ve "okuyan ile yazan aynı iş parçacığında" bir varsayım.
        # Kısıt kapatılmıyor, kilide taşınıyor (`live/depo.py`deki aynı gerekçe, K-034).
        self._kilit = threading.RLock()
        self._baglanti = sqlite3.connect(
            str(yol), isolation_level=None, check_same_thread=False
        )
        self._baglanti.row_factory = sqlite3.Row
        # WAL: Faz 6'da okuyan bir dashboard ile yazan bir süreç aynı dosyaya bakacak.
        # Şimdi açmak, o gün şaşırmamak için.
        if str(yol) != ":memory:":
            self._baglanti.execute("PRAGMA journal_mode=WAL")
        self._baglanti.executescript(_SEMA)

    # ------------------------------------------------------------------ yazma

    def yaz(self, olay: Olay) -> str:
        with self._kilit:
            return self._yaz(olay)

    def _yaz(self, olay: Olay) -> str:
        onceki = self._son_hash()
        satir_hash = olay.icerik_hash(onceki)
        self._baglanti.execute(
            "INSERT INTO audit (tur, zaman_ms, yazim_ms, sembol, govde, durum, "
            "onceki_hash, satir_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(olay.tur),
                olay.zaman_ms,
                simdi_ms(),
                olay.sembol,
                _json(olay.govde),
                _json(olay.durum),
                onceki,
                satir_hash,
            ),
        )
        return satir_hash

    def _son_hash(self) -> str:
        satir = self._baglanti.execute(
            "SELECT satir_hash FROM audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return KOK_HASH if satir is None else str(satir["satir_hash"])

    # ------------------------------------------------------------------ okuma

    def oku(self, *, limit: int | None = None, tur: OlayTuru | None = None) -> list[dict[str, Any]]:
        sorgu = "SELECT * FROM audit"
        parametreler: list[Any] = []
        if tur is not None:
            sorgu += " WHERE tur = ?"
            parametreler.append(str(tur))
        sorgu += " ORDER BY id"
        if limit is not None:
            sorgu += " LIMIT ?"
            parametreler.append(limit)
        with self._kilit:
            return [self._satir(s) for s in self._baglanti.execute(sorgu, parametreler)]

    def sayim(self) -> dict[str, int]:
        """Olay türüne göre sayım. Rapora ve `sq risk durum`a gidiyor."""
        with self._kilit:
            return {
                str(s["tur"]): int(s["n"])
                for s in self._baglanti.execute(
                    "SELECT tur, COUNT(*) AS n FROM audit GROUP BY tur"
                )
            }

    @staticmethod
    def _satir(s: sqlite3.Row) -> dict[str, Any]:
        kayit = dict(s)
        kayit["govde"] = json.loads(kayit["govde"])
        kayit["durum"] = json.loads(kayit["durum"])
        kayit["zaman_utc"] = utc_str(int(kayit["zaman_ms"]))
        return kayit

    # --------------------------------------------------------------- doğrulama

    def dogrula(self) -> bool:
        """Zinciri baştan yeniden hesaplar ve kayıtlı hash'lerle karşılaştırır."""
        onceki = KOK_HASH
        with self._kilit:
            satirlar = list(self._baglanti.execute("SELECT * FROM audit ORDER BY id"))
        for satir in satirlar:
            olay = Olay(
                tur=OlayTuru(satir["tur"]),
                zaman_ms=int(satir["zaman_ms"]),
                sembol=str(satir["sembol"]),
                govde=json.loads(satir["govde"]),
                durum=json.loads(satir["durum"]),
            )
            if satir["onceki_hash"] != onceki:
                return False
            beklenen = olay.icerik_hash(onceki)
            if satir["satir_hash"] != beklenen:
                return False
            onceki = beklenen
        return True

    def kapat(self) -> None:
        with self._kilit:
            self._baglanti.close()

    def __enter__(self) -> SqliteDefter:
        return self

    def __exit__(self, *_: object) -> None:
        self.kapat()


class JsonlDefter:
    """Dosyaya satır satır JSON yazan defter. Araştırma koşuları ve gözle okuma için.

    SQLite'ın yanında durmasının sebebi şu: bir backtest'i risk motoruyla koşturup audit'e
    bakmak isteyen biri için `sqlite3` açmak gereksiz bir adım. Aynı `Defter` protokolünü
    uyguluyor, aynı zincir hash'ini tutuyor; farkı dayanıklılık (transaction yok) —
    bu yüzden paper/live için **kullanılmaz**.
    """

    def __init__(self, yol: str | Path) -> None:
        self.yol = Path(yol)
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        self._son = self._zincirin_sonu()

    def _zincirin_sonu(self) -> str:
        if not self.yol.exists():
            return KOK_HASH
        son = KOK_HASH
        for satir in self.yol.read_text(encoding="utf-8").splitlines():
            if satir.strip():
                son = json.loads(satir)["satir_hash"]
        return son

    def yaz(self, olay: Olay) -> str:
        satir_hash = olay.icerik_hash(self._son)
        kayit = {
            "tur": str(olay.tur),
            "zaman_ms": olay.zaman_ms,
            "yazim_ms": simdi_ms(),
            "sembol": olay.sembol,
            "govde": olay.govde,
            "durum": olay.durum,
            "onceki_hash": self._son,
            "satir_hash": satir_hash,
        }
        with self.yol.open("a", encoding="utf-8", newline="\n") as f:
            f.write(_json(kayit) + "\n")
        self._son = satir_hash
        return satir_hash

    def _satirlar(self) -> Iterator[dict[str, Any]]:
        if not self.yol.exists():
            return
        for satir in self.yol.read_text(encoding="utf-8").splitlines():
            if satir.strip():
                yield json.loads(satir)

    def oku(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        kayitlar = list(self._satirlar())
        if limit is not None:
            kayitlar = kayitlar[:limit]
        for k in kayitlar:
            k["zaman_utc"] = utc_str(int(k["zaman_ms"]))
        return kayitlar

    def dogrula(self) -> bool:
        onceki = KOK_HASH
        for kayit in self._satirlar():
            olay = Olay(
                tur=OlayTuru(kayit["tur"]),
                zaman_ms=int(kayit["zaman_ms"]),
                sembol=str(kayit["sembol"]),
                govde=kayit["govde"],
                durum=kayit["durum"],
            )
            if kayit["onceki_hash"] != onceki:
                return False
            beklenen = olay.icerik_hash(onceki)
            if kayit["satir_hash"] != beklenen:
                return False
            onceki = beklenen
        return True

    def kapat(self) -> None:
        """JSONL'de açık tutulan kaynak yok; protokolü tamamlamak için var."""


class BellekDefteri:
    """Hiçbir yere yazmayan defter. Yalnızca test ve araştırma koşuları için.

    Varsayılan **bu değil**: audit'i yazmayan bir varsayılan, K-008/5'i sessizce iptal
    ederdi. Motorun `defter=None` hâli de bunu kullanmıyor — kararı kaydetmemeyi seçmek
    açık bir çağrı olmak zorunda.
    """

    def __init__(self) -> None:
        self.olaylar: list[Olay] = []
        self._son = KOK_HASH

    def yaz(self, olay: Olay) -> str:
        self.olaylar.append(olay)
        self._son = olay.icerik_hash(self._son)
        return self._son

    def oku(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        olaylar = self.olaylar if limit is None else self.olaylar[:limit]
        return [
            {
                "tur": str(o.tur),
                "zaman_ms": o.zaman_ms,
                "sembol": o.sembol,
                "govde": o.govde,
                "durum": o.durum,
            }
            for o in olaylar
        ]

    def dogrula(self) -> bool:
        """Bellekte kurcalama yüzeyi yok; zincir tanım olarak tutarlı."""
        return True

    def kapat(self) -> None:
        """Kapatılacak kaynak yok."""


def _json(nesne: Any) -> str:
    """Kanonik JSON: anahtarlar sıralı. Zincir hash'inin kararlılığı buna bağlı."""
    return json.dumps(nesne, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = [
    "KOK_HASH",
    "KOLONLAR",
    "BellekDefteri",
    "Defter",
    "JsonlDefter",
    "Olay",
    "OlayTuru",
    "SqliteDefter",
]
