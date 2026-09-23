"""`/api/aktif`: aktif demo bot hesaplarının salt okunur özeti. (K-134)

Kaynaklar: `config/aktif.json` (hesap tanımı) ve her hesabın `runs/aktif/<hesap>/` dizini —
`defter.sqlite` (işlem, özkaynak izi, olay, fren) ve `paper.json` (simüle pozisyonlar).
SQLite `mode=ro` açılır; bu uç hiçbir şey yazmaz (K-036/K-043).

"Çalışıyor" bir süreç kontrolü değil, **tazelik**tir: son tur, zaman diliminin iki katından
eskiyse hesap durmuş sayılır. Piyasa kapalıyken (MT5 hafta sonu) de tur atılır, yani tazelik
sürecin yaşadığını gösterir.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from scryne_quant.common.zaman import timeframe_ms

EGRI_AZAMI = 1500
ISLEM_SON = 40


def _ro(yol: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{yol.as_posix()}?mode=ro", uri=True)


def _hafta(ms: int) -> str:
    y, h, _ = dt.datetime.fromtimestamp(ms / 1000, tz=dt.UTC).isocalendar()
    return f"{y}-W{h:02d}"


def _seyrelt(noktalar: list[tuple[int, float]], azami: int) -> list[tuple[int, float]]:
    if len(noktalar) <= azami:
        return noktalar
    adim = len(noktalar) / azami
    secilen = [noktalar[int(i * adim)] for i in range(azami - 1)]
    return [*secilen, noktalar[-1]]


def hesap_ozeti(ad: str, tanim: dict[str, Any], dizin: Path, simdi_ms: int) -> dict[str, Any]:
    tf = str(tanim.get("timeframe", "15m"))
    sermaye = tanim.get("sermaye")
    ozet: dict[str, Any] = {
        "ad": ad,
        "araci": tanim.get("araci"),
        "strateji": tanim.get("strateji"),
        "timeframe": tf,
        "semboller": list(tanim.get("semboller", [])),
        "sermaye": float(sermaye) if sermaye is not None else None,
        "para_birimi": "USDT" if tanim.get("araci") in ("kripto_paper", "carry_paper") else "USD",
        "yalniz_long": bool(tanim.get("yalniz_long", False)),
        "kapali": (dizin / "kapali").is_file(),
        "var": False,
        "calisiyor": False,
        "ozkaynak": None,
        "son_tur_ms": None,
        "egri": [],
        "islemler": [],
        "pozisyonlar": [],
        "karne": [],
        "olaylar": [],
        "fren": None,
        "hafta_islem": 0,
        "toplam_islem": 0,
        "toplam_ucret": 0.0,
        "swap_toplam": None,
    }
    db_yolu = dizin / "defter.sqlite"
    if not db_yolu.is_file():
        return ozet
    ozet["var"] = True
    db = _ro(db_yolu)
    try:
        egri = db.execute("SELECT zaman_ms, deger FROM ozkaynak ORDER BY zaman_ms").fetchall()
        islemler = db.execute(
            "SELECT zaman_ms, sembol, adet, fiyat, notional, ucret, neden FROM islem "
            "ORDER BY rowid DESC LIMIT ?",
            (ISLEM_SON,),
        ).fetchall()
        sayim = db.execute("SELECT COUNT(*), COALESCE(SUM(ucret), 0) FROM islem").fetchone()
        hafta_bas = _hafta_baslangici_ms(simdi_ms)
        hafta_islem = db.execute(
            "SELECT COUNT(*) FROM islem WHERE zaman_ms >= ?", (hafta_bas,)
        ).fetchone()[0]
        olaylar = db.execute(
            "SELECT zaman_ms, tur, ayrinti FROM olay WHERE tur NOT IN ('basla') "
            "ORDER BY rowid DESC LIMIT 8"
        ).fetchall()
        fren_satir = db.execute("SELECT deger FROM durum WHERE anahtar='fren'").fetchone()
        acilislar = db.execute(
            "SELECT sembol, fiyat, zaman_ms FROM islem WHERE neden IN ('giris', 'donus') "
            "ORDER BY rowid"
        ).fetchall()
    finally:
        db.close()

    if egri:
        ozet["ozkaynak"] = egri[-1][1]
        ozet["son_tur_ms"] = egri[-1][0]
        ozet["calisiyor"] = simdi_ms - egri[-1][0] <= 2 * timeframe_ms(tf) + 120_000
        if ozet["sermaye"] is None:
            ozet["sermaye"] = egri[0][1]
    ozet["egri"] = [{"t": t, "v": v} for t, v in _seyrelt(egri, EGRI_AZAMI)]
    ozet["islemler"] = [
        {"t": t, "sembol": s, "adet": a, "fiyat": f, "notional": n, "ucret": u, "neden": ne}
        for t, s, a, f, n, u, ne in islemler
    ]
    ozet["toplam_islem"], ozet["toplam_ucret"] = int(sayim[0]), float(sayim[1])
    ozet["hafta_islem"] = int(hafta_islem)
    ozet["olaylar"] = [
        {"t": t, "tur": tur, "ayrinti": _kisa(ayrinti)} for t, tur, ayrinti in olaylar
    ]

    fren = json.loads(fren_satir[0]) if fren_satir else {}
    ozet["fren"] = _fren_ozeti(fren, ozet["ozkaynak"], olaylar)
    ozet["karne"] = _karne(egri, simdi_ms)

    son_acilis = {s: (f, t) for s, f, t in acilislar}
    paper = dizin / "paper.json"
    if paper.is_file():
        durum = json.loads(paper.read_text(encoding="utf-8"))
        adet = durum.get("adet", {})
        if "swap_toplam" in durum.get("ek", {}):
            ozet["swap_toplam"] = float(durum["ek"]["swap_toplam"])
        ozet["pozisyonlar"] = [
            {"sembol": s, "adet": a, "yon": "long" if a > 0 else "short",
             "giris_fiyat": son_acilis.get(s, (None, None))[0],
             "giris_ms": son_acilis.get(s, (None, None))[1]}
            for s, a in sorted(adet.items())
            if a
        ]
    return ozet


def _hafta_baslangici_ms(ms: int) -> int:
    an = dt.datetime.fromtimestamp(ms / 1000, tz=dt.UTC)
    pazartesi = (an - dt.timedelta(days=an.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int(pazartesi.timestamp() * 1000)


def _kisa(ayrinti: str) -> str:
    try:
        d = json.loads(ayrinti)
    except ValueError:
        return ayrinti[:200]
    if isinstance(d, dict):
        for anahtar in ("hata", "sebep"):
            if anahtar in d:
                on = f"{d['sembol']}: " if "sembol" in d else ""
                return f"{on}{d[anahtar]}"[:200]
    return json.dumps(d, ensure_ascii=False)[:200]


def _fren_ozeti(fren: dict[str, Any], ozk: float | None, olaylar: list[Any]) -> dict[str, Any]:
    gun_basi = float(fren.get("gun_basi") or 0.0)
    hafta_basi = float(fren.get("hafta_basi") or 0.0)
    son_fren = next((o for o in olaylar if o[1] == "fren"), None)
    return {
        "gun_getiri": (ozk / gun_basi - 1.0) if ozk and gun_basi else None,
        "hafta_getiri": (ozk / hafta_basi - 1.0) if ozk and hafta_basi else None,
        "son_fren_ms": son_fren[0] if son_fren else None,
        "son_fren_sebep": _kisa(son_fren[2]) if son_fren else None,
    }


def _karne(egri: list[tuple[int, float]], simdi_ms: int) -> list[dict[str, Any]]:
    haftalar: dict[str, dict[str, Any]] = {}
    onceki: float | None = None
    for t, v in egri:
        h = _hafta(t)
        k = haftalar.setdefault(h, {"hafta": h, "bas": v if onceki is None else onceki, "son": v})
        k["son"] = v
        onceki = v
    sonuc = []
    for h in sorted(haftalar):
        k = haftalar[h]
        k["getiri"] = k["son"] / k["bas"] - 1.0 if k["bas"] else 0.0
        k["suruyor"] = h == _hafta(simdi_ms)
        sonuc.append(k)
    return sonuc


def aktif_topla(kok: Path, simdi_ms: int | None = None) -> dict[str, Any]:
    simdi = int(time.time() * 1000) if simdi_ms is None else simdi_ms
    ayar_yolu = kok / "config" / "aktif.json"
    if not ayar_yolu.is_file():
        return {"zaman_ms": simdi, "hesaplar": [], "hata": "config/aktif.json yok"}
    ayar = json.loads(ayar_yolu.read_text(encoding="utf-8"))
    hesaplar = [
        hesap_ozeti(ad, tanim, kok / "runs" / "aktif" / ad, simdi)
        for ad, tanim in ayar.get("hesaplar", {}).items()
    ]
    return {"zaman_ms": simdi, "hesaplar": hesaplar, "risk": {
        k: v for k, v in ayar.get("risk", {}).items() if not k.startswith("_")}}
