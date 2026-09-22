"""Paper borsa: gerçek emir yolunun (EmirMotoru → mutabakat → pozisyon) simüle karşı tarafı. (K-114)

**Neden bir adaptör, neden motorun içinde simülasyon değil.** Faz 6'nın paper motoru fill'i
kendi içinde simüle ediyor (`live/motor.py`); o yol `EmirMotoru`nu, emir defterini, emir
mutabakatını ve pozisyon mutabakatını **hiç çalıştırmıyor**. Canlıya giden yolun paper'da
uçtan uca sınanabilmesi için simülasyonun yeri motor değil, **borsanın kendisi** olmalı:
`EmirAdaptoru` sözleşmesinin arkasında duran, bakiyesi, emir kaydı ve işlem listesi olan
bir borsa. Böylece paper, testnet ve live arasındaki tek fark adaptör olur (K-001'in
"tek kod yolu" ilkesinin execution'daki karşılığı).

**Fill kuralı projenin kuralları (K-004, K-007):**

- Market emri gönderildiği an **dolmaz**: `ACKNOWLEDGED` (borsada `NEW`) kalır ve bir
  sonraki barın **açılışında** dolar (`bar_acilisi`). Sinyal barının kapanışından dolan
  bir paper, backtest'in ve canlının ölçmediği bir fiyatı kaydeder.
- Slippage her zaman **aleyhte**: alış `açılış × (1 + s)`, satış `açılış × (1 − s)`.
- Komisyon kote varlıktan (USDT) kesilir; `fills` listesiyle döner, yani `komisyon_kaynagi`
  gerçek borsadaki gibi `yanit`/`islemler` olur ve pozisyon mutabakatı aynı yoldan geçer.

`aninda=True` ile market emri gerçek borsa gibi hemen (son bildirilen fiyattan, aynı
aleyhte slippage ile) dolar — testler ve karşılaştırma içindir; paper koşusu varsayılanı
kullanır.

**Durum diskte (SQLite).** Paper borsanın bakiyesi ve emirleri süreçten bağımsız
yaşamalı: süreç ölürse, yeniden başlayan koşu mutabakatı **borsaya** sorarak yapar
(K-038) — borsa süreçle birlikte ölseydi mutabakat kendi kendini doğrulamak olurdu.

**Duplicate kimlik reddedilir** (`-2010`), tıpkı Binance gibi: duplicate korumasının borsa
tarafındaki yarısı paper'da da sınanır.

Bu modül ağa çıkmaz, anahtar taşımaz; pandas'a bağlı değildir.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from scryne_quant.exchange.emir_adaptoru import (
    BorsaEmri,
    EmirAdaptoru,
    Komisyon,
    Varlik,
    borsa_yonu,
    durum_esle,
)
from scryne_quant.exchange.hatalar import BorsaHatasi, BorsaReddetti
from scryne_quant.exchange.kurallar import SembolKurallari, miktar_uydur

BELLEK: Final = ":memory:"

#: Binance ile aynı kodlar: davranışı değiştiren iki tanesi.
KOD_DUPLICATE: Final = -2010
KOD_YETERSIZ_BAKIYE: Final = -2010
KOD_EMIR_YOK: Final = -2013

_SEMA = """
CREATE TABLE IF NOT EXISTS bakiye (
    varlik  TEXT PRIMARY KEY,
    serbest REAL NOT NULL,
    kilitli REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS emir (
    istemci_kimligi TEXT PRIMARY KEY,
    borsa_kimligi   INTEGER NOT NULL,
    govde           TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS islem (
    sira            INTEGER PRIMARY KEY AUTOINCREMENT,
    borsa_kimligi   INTEGER NOT NULL,
    sembol          TEXT NOT NULL,
    miktar          REAL NOT NULL,
    fiyat           REAL NOT NULL,
    komisyon        REAL NOT NULL,
    komisyon_varlik TEXT NOT NULL,
    zaman_ms        INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS fiyat (
    sembol   TEXT PRIMARY KEY,
    fiyat    REAL NOT NULL,
    zaman_ms INTEGER NOT NULL
);
"""


class PaperHatasi(BorsaHatasi):
    """Paper borsa sözleşmesi ihlal edildi (fiyat yok, sembol tanımsız)."""


@dataclass(frozen=True, slots=True)
class PaperMaliyet:
    """Paper borsanın kestiği maliyet. `common.maliyet.MaliyetModeli`nin iki alanı.

    Ayrı tip çünkü bu modül pydantic'e bağlanmak istemiyor ve iki sayı yeterli; çağıran
    (`trader/`) değerleri `config/maliyet`ten okur — paper borsa kendi maliyetini uydurmaz.
    """

    fee_bps: float
    slippage_bps: float

    def __post_init__(self) -> None:
        if self.fee_bps < 0.0 or self.slippage_bps < 0.0:
            raise PaperHatasi(f"maliyet negatif olamaz: {self}")


class PaperBorsa(EmirAdaptoru):
    """Simüle spot borsa. `EmirAdaptoru` sözleşmesinin tamamı, ağ olmadan."""

    #: Pano ve preflight için: bu adaptör gerçek emir göndermez.
    GERCEK_EMIR: Final = False

    def __init__(
        self,
        *,
        kurallar: dict[str, SembolKurallari],
        maliyet: PaperMaliyet,
        saat: Callable[[], int],
        yol: str | Path = BELLEK,
        acilis_bakiyesi: dict[str, float] | None = None,
        aninda: bool = False,
    ) -> None:
        self._kurallar = dict(kurallar)
        self._maliyet = maliyet
        self._saat = saat
        self._aninda = aninda
        self._kilit = threading.RLock()
        bellekte = str(yol) == BELLEK
        if not bellekte:
            Path(yol).parent.mkdir(parents=True, exist_ok=True)
        self.yol = str(yol)
        self._db = sqlite3.connect(str(yol), isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        if not bellekte:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript(_SEMA)
        # Açılış bakiyesi **yalnızca boş** bir borsaya yazılır: yeniden başlayan bir koşu
        # bakiyesini sıfırlayamaz (çıpayı tazelemenin paper'daki karşılığı olurdu).
        if acilis_bakiyesi and not self._db.execute("SELECT 1 FROM bakiye").fetchone():
            with self._islem() as db:
                for varlik, miktar in acilis_bakiyesi.items():
                    db.execute(
                        "INSERT INTO bakiye VALUES (?, ?, 0.0)", (varlik, float(miktar))
                    )

    # ------------------------------------------------------------------ iç

    def _islem(self) -> Any:
        db, kilit = self._db, self._kilit

        class _Islem:
            def __enter__(self) -> sqlite3.Connection:
                kilit.acquire()
                db.execute("BEGIN IMMEDIATE")
                return db

            def __exit__(self, tur: Any, *_: Any) -> None:
                try:
                    db.execute("ROLLBACK" if tur else "COMMIT")
                finally:
                    kilit.release()

        return _Islem()

    def _varlik(self, db: sqlite3.Connection, varlik: str) -> Varlik:
        s = db.execute("SELECT serbest, kilitli FROM bakiye WHERE varlik=?", (varlik,)).fetchone()
        return Varlik() if s is None else Varlik(float(s["serbest"]), float(s["kilitli"]))

    def _varlik_yaz(self, db: sqlite3.Connection, varlik: str, v: Varlik) -> None:
        # Kayan nokta artığı (−1e-12) negatif bakiye gibi görünmesin; gerçek bir açık ise
        # bu eşiğin çok üstünde olur ve aşağıdaki kontrol onu yakalar.
        serbest = 0.0 if abs(v.serbest) < 1e-12 else v.serbest
        kilitli = 0.0 if abs(v.kilitli) < 1e-12 else v.kilitli
        if serbest < 0.0 or kilitli < 0.0:
            raise PaperHatasi(f"negatif bakiye: {varlik} {serbest}/{kilitli}")
        db.execute(
            "INSERT INTO bakiye VALUES (?, ?, ?) ON CONFLICT(varlik) "
            "DO UPDATE SET serbest=excluded.serbest, kilitli=excluded.kilitli",
            (varlik, serbest, kilitli),
        )

    def _emir_oku(self, db: sqlite3.Connection, kimlik: str) -> dict[str, Any] | None:
        s = db.execute("SELECT govde FROM emir WHERE istemci_kimligi=?", (kimlik,)).fetchone()
        return None if s is None else json.loads(s["govde"])

    def _emir_yaz(self, db: sqlite3.Connection, govde: dict[str, Any]) -> None:
        db.execute(
            "INSERT INTO emir VALUES (?, ?, ?) ON CONFLICT(istemci_kimligi) "
            "DO UPDATE SET govde=excluded.govde",
            (govde["clientOrderId"], int(govde["orderId"]), json.dumps(govde)),
        )

    def _kural(self, sembol: str) -> SembolKurallari:
        try:
            return self._kurallar[sembol]
        except KeyError as hata:
            raise PaperHatasi(f"paper borsada tanımsız sembol: {sembol}") from hata

    def _fiyat(self, db: sqlite3.Connection, sembol: str) -> float:
        s = db.execute("SELECT fiyat FROM fiyat WHERE sembol=?", (sembol,)).fetchone()
        if s is None:
            raise PaperHatasi(
                f"{sembol} için fiyat bildirilmedi; paper borsa fiyat uydurmaz "
                f"(`fiyat_bildir` ya da `bar_acilisi` önce çağrılmalı)"
            )
        return float(s["fiyat"])

    def _slip(self, fiyat: float, yon: str) -> float:
        s = self._maliyet.slippage_bps / 10_000.0
        return fiyat * (1.0 + s) if yon == "BUY" else fiyat * (1.0 - s)

    # ------------------------------------------------------------------ piyasa girdisi

    def fiyat_bildir(self, sembol: str, fiyat: float, zaman_ms: int) -> None:
        """Son işlem fiyatını bildirir (`son_fiyat`, `minNotional` ön kontrolü, `aninda`)."""
        if fiyat <= 0.0:
            raise PaperHatasi(f"fiyat pozitif olmalı: {sembol} {fiyat}")
        with self._islem() as db:
            db.execute(
                "INSERT INTO fiyat VALUES (?, ?, ?) ON CONFLICT(sembol) "
                "DO UPDATE SET fiyat=excluded.fiyat, zaman_ms=excluded.zaman_ms",
                (sembol, float(fiyat), int(zaman_ms)),
            )

    def bar_acilisi(self, sembol: str, acilis: float, zaman_ms: int) -> list[str]:
        """Yeni barın açılışı: bekleyen market emirleri **bu fiyattan** dolar (K-004).

        Açık limit emirleri de burada sınanır: açılış limit fiyatını geçtiyse limit (ya da
        daha iyi olan açılış) fiyatından dolar. Dönen liste dolan emirlerin kimlikleri.
        """
        self.fiyat_bildir(sembol, acilis, zaman_ms)
        dolan: list[str] = []
        with self._islem() as db:
            satirlar = db.execute("SELECT govde FROM emir ORDER BY borsa_kimligi").fetchall()
            for s in satirlar:
                g = json.loads(s["govde"])
                if g["symbol"] != sembol or g["status"] not in ("NEW", "PARTIALLY_FILLED"):
                    continue
                # Bu barın açılışından **sonra** verilmiş emir bu açılıştan dolamaz (K-004):
                # çökme sonrası aynı bar yeniden işlenirse emir kendi karar barının açılışında
                # dolmuş gibi görünürdü (K-114 denetimi).
                if int(g.get("transactTime", 0)) > int(zaman_ms):
                    continue
                if g["type"] == "MARKET":
                    fiyat = self._slip(acilis, g["side"])
                else:
                    limit = float(g["price"])
                    if g["side"] == "BUY" and acilis > limit:
                        continue
                    if g["side"] == "SELL" and acilis < limit:
                        continue
                    fiyat = min(acilis, limit) if g["side"] == "BUY" else max(acilis, limit)
                self._doldur(db, g, fiyat, zaman_ms)
                dolan.append(g["clientOrderId"])
        return dolan

    def _doldur(
        self, db: sqlite3.Connection, g: dict[str, Any], fiyat: float, zaman_ms: int
    ) -> None:
        """Emri tamamen doldurur ve bakiyeyi taşır. Kilitli tutar serbest bırakılır."""
        kural = self._kural(g["symbol"])
        taban, kote = kural.taban_varlik, kural.kote_varlik
        miktar = float(g["origQty"]) - float(g["executedQty"])
        tutar = miktar * fiyat
        komisyon = tutar * self._maliyet.fee_bps / 10_000.0
        tb, kt = self._varlik(db, taban), self._varlik(db, kote)
        kilit = float(g.get("_kilit", 0.0))
        if g["side"] == "BUY":
            # Kilitlenen tahmin (gönderim anı fiyatıyla) serbest bırakılır, gerçek gider düşer.
            serbest = kt.serbest + kilit - tutar - komisyon
            if serbest < -1e-9:
                # Açılış fiyatı kilitlenen tahminden yüksek geldi ve serbest nakit farkı
                # karşılamıyor: gerçek borsada emir kısmen dolar/reddedilir. Paper **tahmin
                # yürütmez**, emri iptal eder ve kilidi geri verir (bakiye yetmedi).
                self._varlik_yaz(db, kote, Varlik(kt.serbest + kilit, kt.kilitli - kilit))
                g.update(status="EXPIRED", updateTime=zaman_ms, _kilit=0.0)
                self._emir_yaz(db, g)
                return
            self._varlik_yaz(db, kote, Varlik(serbest, kt.kilitli - kilit))
            self._varlik_yaz(db, taban, Varlik(tb.serbest + miktar, tb.kilitli))
        else:
            self._varlik_yaz(db, taban, Varlik(tb.serbest, tb.kilitli - kilit))
            self._varlik_yaz(db, kote, Varlik(kt.serbest + tutar - komisyon, kt.kilitli))
        db.execute(
            "INSERT INTO islem (borsa_kimligi, sembol, miktar, fiyat, komisyon, "
            "komisyon_varlik, zaman_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(g["orderId"]), g["symbol"], miktar, fiyat, komisyon, kote, zaman_ms),
        )
        onceki_kote = float(g["cummulativeQuoteQty"])
        g.update(
            status="FILLED",
            executedQty=float(g["origQty"]),
            cummulativeQuoteQty=onceki_kote + tutar,
            updateTime=zaman_ms,
            _kilit=0.0,
        )
        g.setdefault("fills", [])
        g["fills"].append(
            {"price": fiyat, "qty": miktar, "commission": komisyon, "commissionAsset": kote}
        )
        self._emir_yaz(db, g)

    # ------------------------------------------------------------------ EmirAdaptoru

    def sunucu_zamani_ms(self) -> int:
        return int(self._saat())

    def saat_sapmasi_ms(self) -> int:
        return 0

    def sembol_kurallari(self, sembol: str) -> SembolKurallari:
        return self._kural(sembol)

    def son_fiyat(self, sembol: str) -> float:
        with self._kilit:
            return self._fiyat(self._db, sembol)

    def market_emri(
        self, *, istemci_kimligi: str, sembol: str, yon: str, miktar: float
    ) -> BorsaEmri:
        return self._gonder(istemci_kimligi, sembol, yon, miktar, "MARKET", 0.0)

    def limit_emri(
        self,
        *,
        istemci_kimligi: str,
        sembol: str,
        yon: str,
        miktar: float,
        fiyat: float,
    ) -> BorsaEmri:
        return self._gonder(istemci_kimligi, sembol, yon, miktar, "LIMIT", fiyat)

    def _gonder(
        self, kimlik: str, sembol: str, yon: str, miktar: float, tur: str, fiyat: float
    ) -> BorsaEmri:
        kural = self._kural(sembol)
        taraf = borsa_yonu(yon)
        miktar = miktar_uydur(miktar, kural.step_size)
        if miktar <= 0.0:
            raise BorsaReddetti(f"{sembol}: miktar lot adımının altında", kod=-1013)
        simdi = self.sunucu_zamani_ms()
        with self._islem() as db:
            if self._emir_oku(db, kimlik) is not None:
                raise BorsaReddetti("Duplicate order sent.", kod=KOD_DUPLICATE)
            referans = fiyat if tur == "LIMIT" else self._fiyat(db, sembol)
            # Kilit: alışta kote (tahmini tutar + komisyon + slippage payı), satışta taban.
            if taraf == "BUY":
                s = self._maliyet.slippage_bps / 10_000.0
                f = self._maliyet.fee_bps / 10_000.0
                kilit = miktar * referans * (1.0 + s) * (1.0 + f)
                kt = self._varlik(db, kural.kote_varlik)
                if kt.serbest + 1e-9 < kilit:
                    raise BorsaReddetti(
                        "Account has insufficient balance for requested action.",
                        kod=KOD_YETERSIZ_BAKIYE,
                    )
                kilit = min(kilit, kt.serbest)
                self._varlik_yaz(
                    db, kural.kote_varlik, Varlik(kt.serbest - kilit, kt.kilitli + kilit)
                )
            else:
                kilit = miktar
                tb = self._varlik(db, kural.taban_varlik)
                if tb.serbest + 1e-12 < kilit:
                    raise BorsaReddetti(
                        "Account has insufficient balance for requested action.",
                        kod=KOD_YETERSIZ_BAKIYE,
                    )
                kilit = min(kilit, tb.serbest)
                self._varlik_yaz(
                    db, kural.taban_varlik, Varlik(tb.serbest - kilit, tb.kilitli + kilit)
                )
            borsa_kimligi = int(
                db.execute("SELECT COALESCE(MAX(borsa_kimligi), 0) + 1 FROM emir").fetchone()[0]
            )
            g: dict[str, Any] = {
                "symbol": sembol,
                "orderId": borsa_kimligi,
                "clientOrderId": kimlik,
                "side": taraf,
                "type": tur,
                "price": fiyat,
                "origQty": miktar,
                "executedQty": 0.0,
                "cummulativeQuoteQty": 0.0,
                "status": "NEW",
                "transactTime": simdi,
                "updateTime": simdi,
                "_kilit": kilit,
                "fills": [],
            }
            if tur == "MARKET" and self._aninda:
                self._doldur(db, g, self._slip(referans, taraf), simdi)
            else:
                self._emir_yaz(db, g)
        return _borsa_emri(g, fills=True)

    def emir_iptal(self, *, sembol: str, istemci_kimligi: str) -> BorsaEmri | None:
        simdi = self.sunucu_zamani_ms()
        with self._islem() as db:
            g = self._emir_oku(db, istemci_kimligi)
            if g is None or g["status"] not in ("NEW", "PARTIALLY_FILLED"):
                return None
            kural = self._kural(sembol)
            kilit = float(g.get("_kilit", 0.0))
            varlik = kural.kote_varlik if g["side"] == "BUY" else kural.taban_varlik
            v = self._varlik(db, varlik)
            self._varlik_yaz(db, varlik, Varlik(v.serbest + kilit, v.kilitli - kilit))
            g.update(status="CANCELED", updateTime=simdi, _kilit=0.0)
            self._emir_yaz(db, g)
        return _borsa_emri(g, fills=False)

    def emir_sorgula(self, *, sembol: str, istemci_kimligi: str) -> BorsaEmri | None:
        with self._kilit:
            g = self._emir_oku(self._db, istemci_kimligi)
        # `GET /api/v3/order` gibi: `fills` taşımaz (komisyon `emir_islemleri`nden).
        return None if g is None else _borsa_emri(g, fills=False)

    def acik_emirler(self, sembol: str) -> list[BorsaEmri]:
        with self._kilit:
            satirlar = self._db.execute(
                "SELECT govde FROM emir ORDER BY borsa_kimligi"
            ).fetchall()
        out = []
        for s in satirlar:
            g = json.loads(s["govde"])
            if g["symbol"] == sembol and g["status"] in ("NEW", "PARTIALLY_FILLED"):
                out.append(_borsa_emri(g, fills=False))
        return out

    def bakiye(self) -> dict[str, Varlik]:
        with self._kilit:
            satirlar = self._db.execute("SELECT varlik, serbest, kilitli FROM bakiye").fetchall()
        bak = {str(s["varlik"]): Varlik(float(s["serbest"]), float(s["kilitli"])) for s in satirlar}
        return {a: v for a, v in bak.items() if v.toplam > 0.0}

    def emir_islemleri(self, *, sembol: str, borsa_kimligi: str) -> Komisyon:
        if not borsa_kimligi:
            return ()
        with self._kilit:
            satirlar = self._db.execute(
                "SELECT komisyon_varlik, SUM(komisyon) AS k FROM islem "
                "WHERE borsa_kimligi=? AND sembol=? GROUP BY komisyon_varlik",
                (int(borsa_kimligi), sembol),
            ).fetchall()
        return tuple(
            sorted((str(s["komisyon_varlik"]), float(s["k"])) for s in satirlar if s["k"])
        )

    def kapat(self) -> None:
        with self._kilit:
            self._db.close()


def _borsa_emri(g: dict[str, Any], *, fills: bool) -> BorsaEmri:
    """Paper gövdesini `BorsaEmri`ye çevirir; Binance çevirisiyle aynı kurallar."""
    dolan = float(g["executedQty"])
    kote = float(g["cummulativeQuoteQty"])
    if fills:
        komisyon_: dict[str, float] = {}
        for f in g.get("fills", []):
            komisyon_[f["commissionAsset"]] = (
                komisyon_.get(f["commissionAsset"], 0.0) + float(f["commission"])
            )
        komisyon: Komisyon = tuple(sorted((a, m) for a, m in komisyon_.items() if m))
        kaynak = "yanit"
    else:
        komisyon, kaynak = (), ""
    return BorsaEmri(
        istemci_kimligi=str(g["clientOrderId"]),
        borsa_kimligi=str(g["orderId"]),
        sembol=str(g["symbol"]),
        yon=str(g["side"]),
        durum=durum_esle(str(g["status"])),
        miktar=float(g["origQty"]),
        dolan_miktar=dolan,
        ortalama_fiyat=(kote / dolan) if dolan > 0.0 else 0.0,
        guncellendi_ms=int(g["updateTime"]),
        ham_durum=str(g["status"]),
        komisyon=komisyon,
        komisyon_kaynagi=kaynak,
    )


__all__ = ["BELLEK", "PaperBorsa", "PaperHatasi", "PaperMaliyet"]
