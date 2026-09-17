"""İzleme: dört boyut (sistem, veri, trading, model) + alarm kuralları. (Faz 14)

İki katman, bilerek ayrı:

- **Toplama** (`evren_gozlemi`, `sistem_gozlemi`): dosyalardan ve işletim sisteminden okur.
  Koşu dosyasına **yazmaz**; SQLite salt okunur açılır.
- **Kurallar** (`alarmlar`): saf fonksiyon, gözlem sözlüğü → alarm listesi. Test edilebilir,
  eşikler tek yerde (`ESIKLER`).

Her alarm kodunun `docs/Runbook.md`de bir satırı var; `RUNBOOK_KODLARI` testle o dosyaya
bağlı (yeni kod runbook satırı olmadan eklenemez).

Alarm yalnızca **gözlem** üretir: koşuyu durdurmaz, limit değiştirmez (K-050: izni artıran
otomatik olamaz; riski azaltan otomatik olabilir ama burada bilinçli olarak yok — gözlem koşusu
emir göndermiyor, yanlış alarmla durdurmak 30 günlük sayacı boşa bozardı).
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

from scryne_quant.live import kill as kill_mod

SAAT_MS: Final = 3_600_000
GUN_MS: Final = 24 * SAAT_MS

ESIKLER: Final[dict[str, float]] = {
    "son_bar_gecikme_saat": 2.0,     # kapanmış son bar ile işlenen son bar arası
    "eksik_adim_24s": 3,
    "kopma_24s": 5,
    "uyelik_gecikmesi_gun": 3,       # ayın kaçıncı gününden sonra uyarı
    "dusus_uyari": 0.05,
    "dusus_kritik": 0.10,
    "brut_carpan": 1.5,              # hedef brüt × bu
    "sapma_bps": 50.0,
    "sapma_olcum_yasi_saat": 36.0,
    "disk_uyari_gb": 10.0,
    "disk_kritik_gb": 2.0,
    "bellek_uyari_gb": 1.0,
}


@dataclass(frozen=True)
class Alarm:
    kod: str
    boyut: str       # sistem | veri | trading | model
    seviye: str      # uyari | kritik
    kosu: str | None
    mesaj: str

    def sozluk(self) -> dict[str, Any]:
        return asdict(self)


RUNBOOK_KODLARI: Final = (
    "SUREC_YOK", "DISK_AZ", "BELLEK_AZ",
    "SON_BAR_GECIKTI", "EKSIK_ADIM", "KOPMA", "UYELIK_GECIKMESI", "TABLO_YENILEME_HATASI",
    "SAFE_MODE", "DUSUS", "BRUT_ASIMI", "KOSU_HATASI",
    "SAPMA", "SEBEPSIZ_SAPMA", "SAPMA_OLCUMU_YOK",
)


# ---------------------------------------------------------------------- toplama


def _satirlar(yol: Path, sorgu: str, arg: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    baglanti = sqlite3.connect(f"file:{yol.as_posix()}?mode=ro", uri=True)
    try:
        return baglanti.execute(sorgu, arg).fetchall()
    finally:
        baglanti.close()


def evren_gozlemi(kosu_yolu: Path, simdi: int,
                  surec_yasiyor: Callable[[int], bool] = kill_mod.surec_yasiyor_mu
                  ) -> dict[str, Any]:
    """Bir evren koşusunun izleme için gereken her şeyi (salt okunur)."""
    kosu_yolu = Path(kosu_yolu)
    g: dict[str, Any] = {"kosu": kosu_yolu.stem, "var": kosu_yolu.exists()}
    pid = kill_mod.pid_oku(kosu_yolu)
    g["pid"] = pid
    g["surec_yasiyor"] = bool(pid is not None and surec_yasiyor(pid))
    if not g["var"]:
        return g
    kimlik = _satirlar(kosu_yolu, "SELECT kimlik FROM kosu WHERE id = 1")
    g["hedef_brut"] = (json.loads(kimlik[0][0]).get("strateji", {}).get("parametreler", {})
                       .get("hedef_brut") if kimlik else None)
    adimlar = _satirlar(kosu_yolu, "SELECT open_time, isinma, eksik, ozkaynak, brut, islendi_ms "
                                   "FROM adim ORDER BY adim")
    g["adim"] = len(adimlar)
    if adimlar:
        son = adimlar[-1]
        g["son_bar_ms"] = int(son[0])
        g["ozkaynak"] = float(son[3])
        g["brut"] = float(son[4])
        g["zirve_ozkaynak"] = max(float(a[3]) for a in adimlar)
        g["eksik_adim_24s"] = sum(1 for a in adimlar
                                  if a[5] >= simdi - GUN_MS and json.loads(a[2]))
        ay = dt.datetime.fromtimestamp(int(adimlar[-1][0]) / 1000, dt.UTC).strftime("%Y-%m")
        g["uyelik_gecikmesi_suruyor"] = not _satirlar(
            kosu_yolu, "SELECT 1 FROM uyelik WHERE ay = ?", (ay,))
    olaylar = _satirlar(kosu_yolu, "SELECT tur, zaman_ms, ayrinti FROM olay "
                                   "WHERE zaman_ms >= ? ORDER BY id", (simdi - GUN_MS,))
    g["olay_24s"] = {}
    for tur, _, _ in olaylar:
        g["olay_24s"][tur] = g["olay_24s"].get(tur, 0) + 1
    g["son_hata"] = next((json.loads(a) for tur, _, a in reversed(olaylar) if tur == "hata"),
                         None)
    safe = kill_mod.safe_isareti(kosu_yolu)
    durum_yolu = kosu_yolu.with_suffix(kosu_yolu.suffix + ".durum.json")
    durum = (json.loads(durum_yolu.read_text(encoding="utf-8")) if durum_yolu.exists() else {})
    g["safe_mode"] = bool(safe) or bool(durum.get("safe_mode"))
    sapma_yolu = kosu_yolu.with_name(kosu_yolu.stem + ".sapma.jsonl")
    if sapma_yolu.exists():
        satirlar = sapma_yolu.read_text(encoding="utf-8").strip().splitlines()
        g["sapma"] = json.loads(satirlar[-1]) if satirlar else None
    yenileme_yolu = kosu_yolu.with_name(kosu_yolu.stem + ".yenileme.log")
    if yenileme_yolu.exists():
        metin = yenileme_yolu.read_text(encoding="utf-8", errors="replace")
        satirlar = metin.strip().splitlines()
        g["yenileme_son_satir"] = satirlar[-1] if satirlar else ""
    return g


def sistem_gozlemi(kok: Path) -> dict[str, Any]:
    disk = shutil.disk_usage(kok)
    g: dict[str, Any] = {"disk_bos_gb": disk.free / 1024**3}
    g["bellek_bos_gb"] = _bos_bellek_gb()
    return g


def _bos_bellek_gb() -> float | None:
    """Windows'ta `GlobalMemoryStatusEx`; başka platformda ölçülmez (host Windows)."""
    import ctypes
    import sys

    if sys.platform != "win32":
        return None

    class _Durum(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    d = _Durum()
    d.dwLength = ctypes.sizeof(_Durum)
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(d)):
        return None
    return d.ullAvailPhys / 1024**3


# ---------------------------------------------------------------------- kurallar


def _tarih_ms_gunu(ms: int) -> int:
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).day


def _utc_metninden_ms(metin: str) -> int:
    """`utc_str` biçimi: `2026-09-17 15:33:31 UTC`."""
    t = dt.datetime.strptime(metin, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=dt.UTC)
    return int(t.timestamp() * 1000)


def alarmlar(sistem: dict[str, Any], kosular: list[dict[str, Any]], simdi: int,
             esik: dict[str, float] = ESIKLER) -> list[Alarm]:
    a: list[Alarm] = []
    bos = sistem.get("disk_bos_gb")
    if bos is not None and bos < esik["disk_uyari_gb"]:
        seviye = "kritik" if bos < esik["disk_kritik_gb"] else "uyari"
        a.append(Alarm("DISK_AZ", "sistem", seviye, None, f"boş disk {bos:.1f} GB"))
    bellek = sistem.get("bellek_bos_gb")
    if bellek is not None and bellek < esik["bellek_uyari_gb"]:
        a.append(Alarm("BELLEK_AZ", "sistem", "uyari", None, f"boş bellek {bellek:.2f} GB"))

    for g in kosular:
        k = g["kosu"]
        if not g["surec_yasiyor"]:
            a.append(Alarm("SUREC_YOK", "sistem", "kritik", k, "koşu süreci çalışmıyor"))
        if not g.get("var"):
            continue
        olay = g.get("olay_24s", {})
        if g.get("son_hata"):
            a.append(Alarm("KOSU_HATASI", "trading", "kritik", k, str(g["son_hata"])[:300]))
        son_bar = g.get("son_bar_ms")
        if son_bar is not None:
            kapanmis_son = (simdi // SAAT_MS) * SAAT_MS - SAAT_MS
            gecikme = (kapanmis_son - son_bar) / SAAT_MS
            if gecikme >= esik["son_bar_gecikme_saat"]:
                a.append(Alarm("SON_BAR_GECIKTI", "veri", "kritik", k,
                               f"işlenen son bar {gecikme:.0f} saat geride"))
        if g.get("eksik_adim_24s", 0) > esik["eksik_adim_24s"]:
            a.append(Alarm("EKSIK_ADIM", "veri", "uyari", k,
                           f"24 saatte {g['eksik_adim_24s']} adım eksik sembolle işlendi"))
        if olay.get("kopma", 0) > esik["kopma_24s"]:
            a.append(Alarm("KOPMA", "veri", "uyari", k, f"24 saatte {olay['kopma']} kopma"))
        if (g.get("uyelik_gecikmesi_suruyor")
                and _tarih_ms_gunu(simdi) > esik["uyelik_gecikmesi_gun"]):
            a.append(Alarm("UYELIK_GECIKMESI", "veri", "uyari", k,
                           "yeni ayın evren listesi hâlâ yok; önceki ayla devam ediliyor"))
        satir = g.get("yenileme_son_satir") or ""
        if "HATA" in satir:
            a.append(Alarm("TABLO_YENILEME_HATASI", "veri", "kritik", k, satir[:300]))
        if g.get("safe_mode"):
            a.append(Alarm("SAFE_MODE", "trading", "kritik", k, "koşu SAFE_MODE'da"))
        zirve, oz = g.get("zirve_ozkaynak"), g.get("ozkaynak")
        if zirve and oz is not None:
            dusus = 1 - oz / zirve
            if dusus >= esik["dusus_uyari"]:
                seviye = "kritik" if dusus >= esik["dusus_kritik"] else "uyari"
                a.append(Alarm("DUSUS", "trading", seviye, k, f"zirveden düşüş %{dusus * 100:.1f}"))
        hedef = g.get("hedef_brut")
        if hedef and g.get("brut") is not None and g["brut"] > hedef * esik["brut_carpan"]:
            a.append(Alarm("BRUT_ASIMI", "trading", "uyari", k,
                           f"brüt maruziyet {g['brut']:.3f} > hedef {hedef} × "
                           f"{esik['brut_carpan']}"))
        sapma = g.get("sapma")
        if sapma is not None:
            yas = (simdi - _utc_metninden_ms(sapma["olculdu"])) / SAAT_MS
            if yas > esik["sapma_olcum_yasi_saat"]:
                a.append(Alarm("SAPMA_OLCUMU_YOK", "model", "uyari", k,
                               f"son sapma ölçümü {yas:.0f} saat önce"))
            if sapma.get("ilk_ayrisan_adim") is not None:
                sebep = sum(sapma.get(k, 0) for k in (
                    "gec_bilinen_bar", "eksikli_adim", "uyelik_gecikmesi", "gec_bilinen_turev",
                    "makro_revizyon"))
                if sebep == 0:
                    a.append(Alarm("SEBEPSIZ_SAPMA", "model", "kritik", k,
                                   f"canlı referanstan {sapma['ilk_ayrisan_utc']}'de ayrıştı, "
                                   "geç bar/eksik adım/üyelik gecikmesi yok"))
                elif abs(sapma.get("son_ozkaynak_farki_bps", 0.0)) > esik["sapma_bps"]:
                    a.append(Alarm("SAPMA", "model", "uyari", k,
                                   f"canlı-referans özkaynak farkı "
                                   f"{sapma['son_ozkaynak_farki_bps']:.1f} bps"))
    return a


__all__ = ["ESIKLER", "RUNBOOK_KODLARI", "Alarm", "alarmlar", "evren_gozlemi", "sistem_gozlemi"]
