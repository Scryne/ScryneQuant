"""Bot takip ekranının veri ucu: `/api/bot` (K-132). Salt okuma, borsaya bağlanmaz.

`sq execution pano` (8790) bu modülün `bot_topla` çıktısını `/api/bot`tan verir; React ekranı
(`apps/web/bot.html`) onu okur. Kaynaklar yalnız diskteki kayıtlar: her koşunun `durum.json`,
`yurutucu.json`, `egri.jsonl` (yürütücünün bar başına izi), `emirler.sqlite`, `hatalar.jsonl`;
hazırlık hükümleri (`execution.hazirlik`), kademe tablosu ve test kaydı.

Pano hiçbir şeyi değiştirmez (K-036, K-043): emir, iptal, mod geçişi, onay, kill yok.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from scryne_quant.common.hash import git_durumu
from scryne_quant.common.zaman import simdi_ms, timeframe_ms, utc_str
from scryne_quant.execution.mod import ModDefteri

AZAMI_EGRI_NOKTASI = 1500
EMIR_SAYISI = 40
KOSU_KOKU = Path("runs/execution")


def _json(p: Path) -> dict[str, Any] | None:
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None


def _satirlar(p: Path) -> list[dict[str, Any]]:
    if not p.is_file():
        return []
    out = []
    for s in p.read_text(encoding="utf-8").splitlines():
        try:
            v = json.loads(s)
        except ValueError:
            continue
        if isinstance(v, dict):
            out.append(v)
    return out


def _canli_mi(dizin: Path) -> bool:
    from scryne_quant.live import kill as kill_mod

    try:
        pid = kill_mod.pid_oku(dizin / "kosu")
    except (TypeError, ValueError, OSError):
        return False
    return pid is not None and kill_mod.surec_yasiyor_mu(pid)


def egri(dizin: Path, azami: int = AZAMI_EGRI_NOKTASI) -> list[dict[str, Any]]:
    """`egri.jsonl` (aynı bar birden çok yazıldıysa sonuncusu); en çok `azami` noktaya seyreltilir,
    ilk ve son nokta her zaman korunur."""
    tekil: dict[int, dict[str, Any]] = {}
    for s in _satirlar(dizin / "egri.jsonl"):
        if isinstance(s.get("bar_ms"), int):
            tekil[s["bar_ms"]] = s
    noktalar = [tekil[k] for k in sorted(tekil)]
    if len(noktalar) <= azami:
        return noktalar
    adim = len(noktalar) / (azami - 1)
    secilen = [noktalar[int(i * adim)] for i in range(azami - 1)]
    return [*secilen, noktalar[-1]]


def emirler(dizin: Path, n: int = EMIR_SAYISI) -> list[dict[str, Any]]:
    yol = dizin / "emirler.sqlite"
    if not yol.is_file():
        return []
    try:
        db = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        satirlar = [dict(s) for s in db.execute(
            "SELECT istemci_kimligi, yon, miktar, dolan_miktar, ortalama_fiyat, durum, "
            "olusturuldu_ms, guncellendi_ms, komisyon, tur, hata FROM emir "
            "ORDER BY olusturuldu_ms DESC LIMIT ?", (n,))]
        db.close()
    except sqlite3.Error:
        return []
    return satirlar


def denge(
    strateji: str | None, parametreler: dict[str, Any], hesap: dict[str, Any]
) -> dict[str, Any] | None:
    """Sabit oranlı yatırımın (K-132) bant durumu ve bir sonraki alış/satış tetik fiyatları.

    Maruziyet x = qP / (qP + c) ⇒ P = x·c / (q·(1 − x)). Alış tetiği x = hedef − bant, satış
    tetiği x = hedef + bant. Pozisyon yoksa tetik yok: ilk alım bir sonraki kararda.
    """
    if strateji != "sabit_oran":
        return None
    hedef = float(parametreler.get("hedef", 0.5))
    bant = float(parametreler.get("bant", 0.05))
    q = float(hesap.get("miktar") or 0.0)
    c = float(hesap.get("nakit") or 0.0)

    def tetik(x: float) -> float | None:
        return x * c / (q * (1.0 - x)) if q > 0 and c > 0 and 0 < x < 1 else None

    return {"hedef": hedef, "bant": bant, "maruziyet": float(hesap.get("maruziyet") or 0.0),
            "alis_tetigi": tetik(hedef - bant), "satis_tetigi": tetik(hedef + bant),
            "fiyat": hesap.get("fiyat")}


def _kosu_ozeti(dizin: Path, d: dict[str, Any], simdi: int) -> dict[str, Any]:
    kosu = d.get("kosu") or {}
    taze = d.get("veri_tazeligi") or {}
    tf = timeframe_ms(str(kosu.get("timeframe", "1h")))
    son = taze.get("son_bar_ms")
    yas = (simdi - (int(son) + tf)) if son else None
    return {
        "ad": dizin.name,
        "mod": d.get("mod"),
        "strateji": kosu.get("strateji"),
        "sembol": kosu.get("sembol") or d.get("sembol"),
        "canli": _canli_mi(dizin),
        "kapatildi": (dizin / "kapatildi.json").is_file(),
        "halt": d.get("halt") or "",
        "safe_mode": bool(d.get("safe_mode")),
        "son_bar_utc": taze.get("son_bar_utc"),
        "veri_yasi_ms": yas,
        "bar": (d.get("sayac") or {}).get("bar"),
        "hata": len(_satirlar(dizin / "hatalar.jsonl")),
        "ozkaynak": (d.get("hesap") or {}).get("ozkaynak"),
        "durum_ms": d.get("zaman_ms"),
    }


def _pilot(kok: Path) -> dict[str, Any] | None:
    tablo = _json(kok / "config/kademe.json") or {}
    aktif = tablo.get("aktif_kademe")
    for k in tablo.get("kademeler") or []:
        if k.get("kademe") == aktif and k.get("pilot"):
            return {"kademe": aktif, "strateji": k.get("strateji"), "sembol": k.get("sembol"),
                    "sermaye_usdt": k.get("sermaye_usdt"),
                    "azami_kayip_usdt": k.get("azami_kayip_usdt")}
    return None


def _hazirlik(kok: Path) -> dict[str, Any] | None:
    from scryne_quant.execution import hazirlik as hz

    try:
        r = hz.rapor(kok)
    except Exception as hata:  # noqa: BLE001 — pano çökmez, hazırlık "okunamadı" der
        return {"hata": f"{type(hata).__name__}: {hata}"}
    gunler = []
    for ad in hz.GOSTERIM_KOSULARI:
        bas = (_json(kok / KOSU_KOKU / ad / "yurutucu.json") or {}).get("baslangic_ms")
        gunler.append((simdi_ms() - int(bas)) / 86_400_000 if bas else 0.0)
    return r.sozluk() | {"pilot_gosterim_gun": hz.PILOT_GOSTERIM_GUN,
                         "gosterim_gun": min(gunler) if gunler else 0.0}


def bot_topla(kok: Path, kosu: str | None = None) -> dict[str, Any]:
    simdi = simdi_ms()
    ex = kok / KOSU_KOKU
    ozetler, durumlar = [], {}
    for p in sorted(ex.glob("*/durum.json")) if ex.is_dir() else []:
        d = _json(p)
        if d is None:
            continue
        durumlar[p.parent.name] = d
        ozetler.append(_kosu_ozeti(p.parent, d, simdi))
    # Varsayılan seçim: canlı (LIVE) koşu varsa o; yoksa ürün koşusu; yoksa en yeni.
    tercih = ([o["ad"] for o in ozetler if o["mod"] == "LIVE" and not o["kapatildi"]]
              + [o["ad"] for o in ozetler if o["strateji"] == "sabit_oran" and not o["kapatildi"]]
              + [o["ad"] for o in sorted(ozetler, key=lambda o: -(o["durum_ms"] or 0))])
    secili_ad = kosu if kosu in durumlar else (tercih[0] if tercih else None)
    secili = None
    if secili_ad:
        d = durumlar[secili_ad]
        dizin = ex / secili_ad
        k = d.get("kosu") or {}
        yur = _json(dizin / "yurutucu.json") or {}
        hesap = d.get("hesap") or {}
        secili = {
            "ad": secili_ad,
            "mod": d.get("mod"),
            "kosu": k,
            "hesap": hesap,
            "limitler": d.get("limitler") or {},
            "risk": (d.get("risk") or {}).get("durum") or {},
            "risk_modu": (d.get("risk") or {}).get("mod"),
            "sayac": d.get("sayac") or {},
            "veri_tazeligi": d.get("veri_tazeligi") or {},
            "son_hata": d.get("son_hata") or "",
            "halt": d.get("halt") or "",
            "safe_mode": bool(d.get("safe_mode")),
            "baglanti": d.get("baglanti") or {},
            "baslangic_ms": yur.get("baslangic_ms"),
            "egri": egri(dizin),
            "emirler": emirler(dizin),
            "denge": denge(k.get("strateji"), k.get("parametreler") or {}, hesap),
            "durum_ms": d.get("zaman_ms"),
        }
    git = git_durumu(kok)
    return {
        "zaman_ms": simdi,
        "zaman_utc": utc_str(simdi),
        "kosular": ozetler,
        "secili": secili,
        "pilot": _pilot(kok),
        "hazirlik": _hazirlik(kok),
        "sistem": {
            "mod": str(ModDefteri(ex / "mod.json").oku().mod),
            "commit": git.get("commit"),
            "dirty": git.get("dirty"),
            "testler": _json(ex / "testler.json"),
        },
    }


__all__ = ["bot_topla", "denge", "egri", "emirler"]
