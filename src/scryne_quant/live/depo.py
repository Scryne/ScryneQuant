"""Koşu deposu: 30 gün ayakta kalacak bir sürecin hafızası. (K-034, K-009, Faz 6)

Faz 6'nın bitti kriterlerinden biri şu: *"Süreç öldürülüp yeniden başlatıldığında pozisyon
ve emir state'i doğru toparlanıyor."* Bu modül o kriterin diske bakan yarısı.

**Neden SQLite, neden PostgreSQL değil:** K-034. Özeti: tek yazıcı (trader döngüsü), çok
okuyucu (dashboard), ve *"30 gün kesintisiz"* ölçülürken ayakta kalması gereken ikinci bir
servis o ölçümün paydası olurdu.

**Kontrol noktasının yeri bir karardır.** Durum satırı bir barın **fill'i ve risk
güncellemesi yapıldıktan sonra, kararı verilmeden önce** yazılır. Sebep K-032: `OnayliNiyet`
mühürlüdür ve mühür süreç başına rastgeledir — yani serileştirilmiş bir onay yeniden
başlayan süreçte doğrulanamaz. Onu yeniden mühürlemek, `OnayliNiyet`in risk motorundan
başka bir üreticisi olmadığı garantisini kırardı. Bu yüzden onay **saklanmaz, yeniden
türetilir**: toparlanma penceresi yeniden kurar, stratejiyi baştan oynatır ve son barın
kararını risk motoruna yeniden verdirir. Saklanan şey kararın **özeti**dir ve yalnızca tek
bir iş için kullanılır: yeniden türetilen kararla karşılaştırılıp ayrışma varsa koşuyu
durdurmak.

Yani bu tasarımda restart, state'i geri yükleyen bir işlem değil — state'in yeniden
üretilebildiğini **kanıtlayan** bir işlem. Faz 6'nın kriterini gerçekten ölçen şey de bu.

**Tablolar:** `kosu` (tek satır, koşunun kimliği), `durum` (tek satır, kontrol noktası),
`fill` ve `olay` (append-only). Audit defteri (`risk/audit.py:SqliteDefter`) aynı dosyayı
kullanabilir; `audit` tablosu orada tanımlı ve şeması `migrations/001_faz5.sql` ile hizalı
tutuluyor.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.zaman import simdi_ms, utc_str

BELLEK: Final = ":memory:"


class DepoHatasi(RuntimeError):
    """Koşu deposu sözleşmesi ihlal edildi."""


class KosuOlayi(StrEnum):
    """Koşunun operasyon günlüğü. Faz 6'nın *"kesinti sebebi kayıtlı"* kriterinin kaynağı."""

    BASLADI = "basladi"
    """Süreç başladı — ilk kez veya toparlanarak."""

    TOPARLANDI = "toparlandi"
    """Kayıtlı durumdan toparlanma tamamlandı; yeniden türetilen karar kayıtlıyla uyuştu."""

    TOPARLANMA_AYRISMASI = "toparlanma_ayrismasi"
    """Yeniden türetilen karar kayıtlı özetle uyuşmadı. Koşu durur; tahmin yürütülmez."""

    BAYAT_GIRIS = "bayat_giris"
    """Veri bayatladı (§24): yeni giriş yok."""

    BAYAT_CIKIS = "bayat_cikis"
    """Veri tazelendi."""

    KOPMA = "kopma"
    """Akış bağlantısı koptu."""

    YENIDEN_BAGLANDI = "yeniden_baglandi"
    """Akış geri geldi ve eksik barlar tamamlandı (resync)."""

    HATA = "hata"
    """Beklenmeyen hata. Koşuyu böldüyse kesinti sayılır."""

    DURDU = "durdu"
    """Süreç düzgün kapandı."""


#: Kesinti sayılan olaylar. *"30 gün kesintisiz (kesinti olduysa sebebi kayıtlı ve
#: giderilmiş)"* kriterinin sayacı bunları sayıyor — `BAYAT_GIRIS` dahil değil, çünkü
#: bayat veri koşuyu **bölmez**, yalnızca yeni girişi durdurur (§24).
KESINTI_OLAYLARI: Final[frozenset[KosuOlayi]] = frozenset(
    {KosuOlayi.KOPMA, KosuOlayi.HATA, KosuOlayi.TOPARLANMA_AYRISMASI}
)

_SEMA = """
CREATE TABLE IF NOT EXISTS kosu (
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    kosu_adi           TEXT    NOT NULL,
    mod                TEXT    NOT NULL,
    sembol             TEXT    NOT NULL,
    timeframe          TEXT    NOT NULL,
    strateji           TEXT    NOT NULL,
    maliyet            TEXT    NOT NULL,
    limitler           TEXT    NOT NULL,
    limit_kimligi      TEXT    NOT NULL,
    baslangic_sermaye  REAL    NOT NULL,
    commit_sha         TEXT    NOT NULL,
    dirty              INTEGER NOT NULL,
    kutuphaneler       TEXT    NOT NULL,
    olusturuldu_ms     INTEGER NOT NULL
);

-- Koşunun kimliği yazıldıktan sonra değişmez. Değişebilseydi, 30 günlük bir koşunun
-- ortasında strateji parametresi veya risk limiti değiştirilebilir ve kayıt hangi
-- konfigürasyonla üretildiğini söyleyemez hâle gelirdi (K-009).
CREATE TRIGGER IF NOT EXISTS kosu_degismez
BEFORE UPDATE ON kosu
BEGIN
    SELECT RAISE(ABORT, 'koşu kimliği değişmez: yeni konfigürasyon yeni koşudur (K-009)');
END;

CREATE TABLE IF NOT EXISTS durum (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    son_bar_ms     INTEGER,
    portfoy        TEXT    NOT NULL,
    risk           TEXT    NOT NULL,
    acik_islem     TEXT,
    bayat          INTEGER NOT NULL,
    bekleyen       TEXT,
    yazim          INTEGER NOT NULL,
    guncellendi_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fill (
    id               INTEGER PRIMARY KEY,
    zaman_ms         INTEGER NOT NULL,
    sinyal_ms        INTEGER NOT NULL,
    yon              TEXT    NOT NULL,
    miktar           REAL    NOT NULL,
    fiyat            REAL    NOT NULL,
    referans_fiyat   REAL    NOT NULL,
    komisyon         REAL    NOT NULL,
    onayli_maruziyet REAL    NOT NULL,
    kisitlayan       TEXT    NOT NULL,
    nakit_sonra      REAL    NOT NULL,
    miktar_sonra     REAL    NOT NULL,
    ozkaynak_sonra   REAL    NOT NULL,
    gerceklesen_pnl  REAL
);
CREATE INDEX IF NOT EXISTS fill_zaman ON fill (zaman_ms);

CREATE TABLE IF NOT EXISTS olay (
    id       INTEGER PRIMARY KEY,
    tur      TEXT    NOT NULL,
    zaman_ms INTEGER NOT NULL,
    bar_ms   INTEGER,
    ayrinti  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS olay_zaman ON olay (zaman_ms);

-- `fill` ve `olay` append-only: ikisi de olmuş bitmiş olayların kaydı. Düzeltilebilen
-- bir fill kaydı, P&L'i sonradan yazılabilir yapardı.
CREATE TRIGGER IF NOT EXISTS fill_guncelleme_yok
BEFORE UPDATE ON fill
BEGIN SELECT RAISE(ABORT, 'fill append-only'); END;
CREATE TRIGGER IF NOT EXISTS fill_silme_yok
BEFORE DELETE ON fill
BEGIN SELECT RAISE(ABORT, 'fill append-only'); END;
CREATE TRIGGER IF NOT EXISTS olay_guncelleme_yok
BEFORE UPDATE ON olay
BEGIN SELECT RAISE(ABORT, 'olay append-only'); END;
CREATE TRIGGER IF NOT EXISTS olay_silme_yok
BEFORE DELETE ON olay
BEGIN SELECT RAISE(ABORT, 'olay append-only'); END;
"""


@dataclass(frozen=True, slots=True)
class KosuKimligi:
    """Koşunun değişmez kimliği. Bir kez yazılır, `kosu_degismez` tetikleyicisi korur."""

    kosu_adi: str
    mod: str
    sembol: str
    timeframe: str
    strateji: dict[str, Any]
    maliyet: dict[str, Any]
    limitler: dict[str, Any]
    limit_kimligi: str
    baslangic_sermaye: float
    commit_sha: str
    dirty: bool
    kutuphaneler: dict[str, Any]
    olusturuldu_ms: int

    def sozluk(self) -> dict[str, Any]:
        return {
            "kosu_adi": self.kosu_adi,
            "mod": self.mod,
            "sembol": self.sembol,
            "timeframe": self.timeframe,
            "strateji": self.strateji,
            "maliyet": self.maliyet,
            "limitler": self.limitler,
            "limit_kimligi": self.limit_kimligi,
            "baslangic_sermaye": self.baslangic_sermaye,
            "commit": self.commit_sha,
            "dirty": self.dirty,
            "kutuphaneler": self.kutuphaneler,
            "olusturuldu_ms": self.olusturuldu_ms,
            "olusturuldu_utc": utc_str(self.olusturuldu_ms),
        }


@dataclass(frozen=True, slots=True)
class KontrolNoktasi:
    """Bir barın fill'i ve risk güncellemesi sonrası, kararı öncesi durum.

    `bekleyen` bir `OnayliNiyet` **değil**, onun özeti: mühür taşınmıyor (K-032). Bu
    özet toparlanmada yalnızca karşılaştırma için kullanılır, onay olarak değil.
    """

    son_bar_ms: int | None
    portfoy: dict[str, Any]
    risk: dict[str, Any]
    acik_islem: dict[str, Any] | None
    """Henüz kapanmamış pozisyon turu. Cooldown sayacı kapanan **turları** sayıyor
    (`backtest/defter.py`); açık tur kaybolursa o tur kapandığında ardışık kayıp sayacı
    hiç artmaz ve cooldown limiti sessizce devre dışı kalır."""

    bayat: bool
    """Bu barın kararı verilirken veri bayat mıydı (§24)?

    Kontrol noktasının parçası çünkü toparlanma kararı **yeniden üretiyor** ve bayatlık o
    kararın girdilerinden biri. Kaydedilmeseydi, toparlanan süreç henüz hiç nabız almamış
    olduğu için her kararı bayat veriyle yeniden üretir ve kayıtlıdan farklı bir sonuç
    bularak kendi kendine ayrışma ilan ederdi."""

    bekleyen: dict[str, Any] | None
    yazim: int
    guncellendi_ms: int

    def sozluk(self) -> dict[str, Any]:
        return {
            "son_bar_ms": self.son_bar_ms,
            "son_bar_utc": None if self.son_bar_ms is None else utc_str(self.son_bar_ms),
            "portfoy": self.portfoy,
            "risk": self.risk,
            "acik_islem": self.acik_islem,
            "bayat": self.bayat,
            "bekleyen": self.bekleyen,
            "yazim": self.yazim,
            "guncellendi_ms": self.guncellendi_ms,
        }


class KosuDeposu:
    """Tek bir paper/gözlem koşusunun dayanıklı durumu.

    Bağlantı `isolation_level=None` (autocommit) ile açılıyor ve yazımlar `_islem()`
    bağlam yöneticisiyle açıkça sarmalanıyor. Python'un örtük transaction yönetimine
    güvenmemek bilinçli: DDL'in transaction'ı sessizce commit ettiği ve `BEGIN`in gizli
    kaldığı bir kipte, "portföy ve risk durumu **birlikte** yazıldı mı" sorusunun cevabı
    kütüphane sürümüne bağlı olurdu.
    """

    __slots__ = ("yol", "_baglanti")

    def __init__(self, yol: str | Path = BELLEK) -> None:
        bellekte = str(yol) == BELLEK
        self.yol = Path(str(yol))
        if not bellekte:
            self.yol.parent.mkdir(parents=True, exist_ok=True)
        self._baglanti = sqlite3.connect(str(yol), isolation_level=None)
        self._baglanti.row_factory = sqlite3.Row
        self._baglanti.execute("PRAGMA foreign_keys=ON")
        if not bellekte:
            # WAL: dashboard okurken trader yazabilsin (K-034'ün dayandığı özellik).
            self._baglanti.execute("PRAGMA journal_mode=WAL")
            # FULL: WAL'ın varsayılanı NORMAL ve o kip işletim sistemi çökmesinde son
            # commit'leri kaybedebilir. Burada commit başına bir fsync'in bedeli saatte
            # bir ödeniyor; kaybedilen şey ise kill switch bayrağı olabilir.
            self._baglanti.execute("PRAGMA synchronous=FULL")
        self._baglanti.executescript(_SEMA)

    # ------------------------------------------------------------------ işlem

    @contextmanager
    def _islem(self) -> Iterator[sqlite3.Connection]:
        self._baglanti.execute("BEGIN IMMEDIATE")
        try:
            yield self._baglanti
        except BaseException:
            self._baglanti.execute("ROLLBACK")
            raise
        self._baglanti.execute("COMMIT")

    # ------------------------------------------------------------------ koşu

    def kosu_yaz(self, kimlik: KosuKimligi) -> None:
        """Koşu kimliğini yazar. İkinci kez farklı bir kimlik yazmak hatadır."""
        mevcut = self.kosu_oku()
        if mevcut is not None:
            if mevcut != kimlik:
                raise DepoHatasi(
                    "bu depo başka bir koşuya ait: "
                    f"kayıtlı {mevcut.kosu_adi!r}/{mevcut.mod}, verilen "
                    f"{kimlik.kosu_adi!r}/{kimlik.mod}. Yeni konfigürasyon yeni koşudur (K-009)"
                )
            return
        with self._islem() as b:
            b.execute(
                "INSERT INTO kosu (id, kosu_adi, mod, sembol, timeframe, strateji, maliyet, "
                "limitler, limit_kimligi, baslangic_sermaye, commit_sha, dirty, kutuphaneler, "
                "olusturuldu_ms) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    kimlik.kosu_adi,
                    kimlik.mod,
                    kimlik.sembol,
                    kimlik.timeframe,
                    _json(kimlik.strateji),
                    _json(kimlik.maliyet),
                    _json(kimlik.limitler),
                    kimlik.limit_kimligi,
                    kimlik.baslangic_sermaye,
                    kimlik.commit_sha,
                    int(kimlik.dirty),
                    _json(kimlik.kutuphaneler),
                    kimlik.olusturuldu_ms,
                ),
            )

    def kosu_oku(self) -> KosuKimligi | None:
        satir = self._baglanti.execute("SELECT * FROM kosu WHERE id = 1").fetchone()
        if satir is None:
            return None
        return KosuKimligi(
            kosu_adi=str(satir["kosu_adi"]),
            mod=str(satir["mod"]),
            sembol=str(satir["sembol"]),
            timeframe=str(satir["timeframe"]),
            strateji=json.loads(satir["strateji"]),
            maliyet=json.loads(satir["maliyet"]),
            limitler=json.loads(satir["limitler"]),
            limit_kimligi=str(satir["limit_kimligi"]),
            baslangic_sermaye=float(satir["baslangic_sermaye"]),
            commit_sha=str(satir["commit_sha"]),
            dirty=bool(satir["dirty"]),
            kutuphaneler=json.loads(satir["kutuphaneler"]),
            olusturuldu_ms=int(satir["olusturuldu_ms"]),
        )

    # ------------------------------------------------------------------ durum

    def kontrol_noktasi_yaz(
        self,
        *,
        son_bar_ms: int | None,
        portfoy: dict[str, Any],
        risk: dict[str, Any],
        acik_islem: dict[str, Any] | None = None,
        bayat: bool = False,
        bekleyen: dict[str, Any] | None = None,
        fill: dict[str, Any] | None = None,
    ) -> int:
        """Kontrol noktasını ve (varsa) bu barın fill'ini **tek transaction'da** yazar.

        İkisinin ayrı yazılması, süreç aradaki anda ölürse iki tür bozukluk üretirdi:
        fill kaydedilmiş ama portföy güncellenmemiş (P&L uydurma), veya tersi (defterde
        olmayan bir işlem). Tek transaction bu ikiliyi ya birlikte yapar ya hiç yapmaz.
        """
        with self._islem() as b:
            onceki = b.execute("SELECT yazim FROM durum WHERE id = 1").fetchone()
            yazim = 1 if onceki is None else int(onceki["yazim"]) + 1
            b.execute(
                "INSERT INTO durum (id, son_bar_ms, portfoy, risk, acik_islem, bayat, "
                "bekleyen, yazim, guncellendi_ms) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET son_bar_ms=excluded.son_bar_ms, "
                "portfoy=excluded.portfoy, risk=excluded.risk, "
                "acik_islem=excluded.acik_islem, bayat=excluded.bayat, "
                "bekleyen=excluded.bekleyen, "
                "yazim=excluded.yazim, guncellendi_ms=excluded.guncellendi_ms",
                (
                    son_bar_ms,
                    _json(portfoy),
                    _json(risk),
                    None if acik_islem is None else _json(acik_islem),
                    int(bayat),
                    None if bekleyen is None else _json(bekleyen),
                    yazim,
                    simdi_ms(),
                ),
            )
            if fill is not None:
                b.execute(
                    "INSERT INTO fill (zaman_ms, sinyal_ms, yon, miktar, fiyat, referans_fiyat, "
                    "komisyon, onayli_maruziyet, kisitlayan, nakit_sonra, miktar_sonra, "
                    "ozkaynak_sonra, gerceklesen_pnl) "
                    "VALUES (:zaman_ms, :sinyal_ms, :yon, :miktar, :fiyat, :referans_fiyat, "
                    ":komisyon, :onayli_maruziyet, :kisitlayan, :nakit_sonra, :miktar_sonra, "
                    ":ozkaynak_sonra, :gerceklesen_pnl)",
                    {**fill, "kisitlayan": _json(fill.get("kisitlayan", []))},
                )
            return yazim

    def bekleyen_yaz(self, bekleyen: dict[str, Any] | None) -> None:
        """Bu barın kararının **özetini** yazar. Risk durumuna dokunmaz — kasıtlı.

        Kontrol noktasındaki `risk` alanı barın **kararı verilmeden önceki** hâlidir ve
        öyle kalmalı. Sebep somut: karar adımı risk durumunu tek bir yerde değiştirebilir
        (drawdown limiti aşıldığında `kill()`). Karar sonrası durumu yazsaydık, toparlanan
        süreç kararı SAFE_MODE açıkken yeniden üretir ve `Red(DRAWDOWN)` yerine
        `Red(SAFE_MODE)` alırdı — yani yeniden üretim, üretilenden farklı çıkar ve
        determinizm kontrolü kendi kurduğu tuzağa düşerdi.

        Yazılan özet bir onay **değildir** (mühür taşımaz, K-032); tek işi toparlanmada
        yeniden üretilen kararla karşılaştırılmaktır.
        """
        with self._islem() as b:
            n = b.execute(
                "UPDATE durum SET bekleyen = ? WHERE id = 1",
                (None if bekleyen is None else _json(bekleyen),),
            ).rowcount
        if n == 0:
            raise DepoHatasi("kontrol noktası yok: bekleyen karar yazılamaz")

    def kontrol_noktasi_oku(self) -> KontrolNoktasi | None:
        satir = self._baglanti.execute("SELECT * FROM durum WHERE id = 1").fetchone()
        if satir is None:
            return None
        bekleyen = satir["bekleyen"]
        acik = satir["acik_islem"]
        return KontrolNoktasi(
            son_bar_ms=None if satir["son_bar_ms"] is None else int(satir["son_bar_ms"]),
            portfoy=json.loads(satir["portfoy"]),
            risk=json.loads(satir["risk"]),
            acik_islem=None if acik is None else json.loads(acik),
            bayat=bool(satir["bayat"]),
            bekleyen=None if bekleyen is None else json.loads(bekleyen),
            yazim=int(satir["yazim"]),
            guncellendi_ms=int(satir["guncellendi_ms"]),
        )

    # ------------------------------------------------------------------ fill

    def filller(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        sorgu = "SELECT * FROM fill ORDER BY id DESC"
        if limit is not None:
            sorgu += f" LIMIT {int(limit)}"
        kayitlar = [dict(s) for s in self._baglanti.execute(sorgu)]
        for k in kayitlar:
            k["kisitlayan"] = json.loads(k["kisitlayan"])
            k["zaman_utc"] = utc_str(int(k["zaman_ms"]))
        return kayitlar

    def fill_sayisi(self) -> int:
        return int(self._baglanti.execute("SELECT COUNT(*) AS n FROM fill").fetchone()["n"])

    # ------------------------------------------------------------------ olay

    def olay_yaz(
        self,
        tur: KosuOlayi,
        *,
        bar_ms: int | None = None,
        ayrinti: dict[str, Any] | None = None,
        zaman_ms: int | None = None,
    ) -> None:
        with self._islem() as b:
            b.execute(
                "INSERT INTO olay (tur, zaman_ms, bar_ms, ayrinti) VALUES (?, ?, ?, ?)",
                (
                    str(tur),
                    simdi_ms() if zaman_ms is None else zaman_ms,
                    bar_ms,
                    _json(ayrinti or {}),
                ),
            )

    def olaylar(
        self, *, limit: int | None = None, tur: KosuOlayi | None = None
    ) -> list[dict[str, Any]]:
        sorgu = "SELECT * FROM olay"
        parametreler: list[Any] = []
        if tur is not None:
            sorgu += " WHERE tur = ?"
            parametreler.append(str(tur))
        sorgu += " ORDER BY id DESC"
        if limit is not None:
            sorgu += " LIMIT ?"
            parametreler.append(int(limit))
        kayitlar = [dict(s) for s in self._baglanti.execute(sorgu, parametreler)]
        for k in kayitlar:
            k["ayrinti"] = json.loads(k["ayrinti"])
            k["zaman_utc"] = utc_str(int(k["zaman_ms"]))
        return kayitlar

    def kesinti_sayisi(self) -> int:
        """Koşuyu **bölen** olayların sayısı. Bayat veri buna dahil değil (§24)."""
        isaretler = ",".join("?" * len(KESINTI_OLAYLARI))
        satir = self._baglanti.execute(
            f"SELECT COUNT(*) AS n FROM olay WHERE tur IN ({isaretler})",
            [str(t) for t in sorted(KESINTI_OLAYLARI)],
        ).fetchone()
        return int(satir["n"])

    def ilk_olay_ms(self) -> int | None:
        satir = self._baglanti.execute("SELECT MIN(zaman_ms) AS t FROM olay").fetchone()
        return None if satir["t"] is None else int(satir["t"])

    # ------------------------------------------------------------------ ömür

    def kapat(self) -> None:
        self._baglanti.close()

    def __enter__(self) -> KosuDeposu:
        return self

    def __exit__(self, *_: object) -> None:
        self.kapat()


def _json(nesne: Any) -> str:
    """Kanonik JSON: anahtarlar sıralı, ASCII kaçışı yok. Aynı içerik aynı metin."""
    return json.dumps(nesne, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = [
    "BELLEK",
    "KESINTI_OLAYLARI",
    "DepoHatasi",
    "KontrolNoktasi",
    "KosuDeposu",
    "KosuKimligi",
    "KosuOlayi",
]
