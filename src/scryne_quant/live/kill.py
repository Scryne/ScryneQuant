"""Süreç dışı kill switch: trader sürecine güvenmeden durdurmak. (Faz 14, Denetim-v2 A8, K-065)

**Kapatmaya çalıştığı boşluk.** Bugünkü kill switch (SAFE_MODE, K-008) risk motorunun,
yani trader sürecinin **içinde**. K-043'ün durdurma bayrağı da bir istek: onu da aynı süreç
okuyor. Süreç kilitlenirse (sonsuz döngü, takılan ağ çağrısı, askıya alınmış süreç) ikisi
de onunla birlikte kilitlenir. Paper'da bedeli yok; canlıda borsada açık emir bırakır.

Bu modül trader sürecinin **hiçbir** işbirliğine ihtiyaç duymayan üç adımı yapar:

1. **SAFE_MODE işareti diske** (`<koşu>.safemode`). İlk adım, çünkü sonraki adımlardan biri
   başarısız olsa bile koşu yeniden başladığında kilitli açılmalı. İşaret veritabanında
   değil ayrı bir dosyada: donmuş süreç SQLite yazma kilidini tutuyor olabilir.
2. **Süreci sonlandır** (`TerminateProcess`). Askıya alınmış bir süreç de sonlandırılabilir;
   süreç kimliği başlangıçta yazılan `<koşu>.pid` dosyasından okunur (kilit dosyası tutulurken
   Windows'ta okunamıyor, `live/kilit.py`). Sonlandırma **emir iptalinden önce**: tersi, iptal
   ile ölüm arasında yeni bir emir girme yarışı bırakırdı.
3. **Borsadaki açık emirleri iptal et ve doğrula.** Süreç öldükten sonra açık emir listesi
   yeniden okunur; boş değilse kill **başarısız** raporlanır, "denedik" sayılmaz.

**Yeniden başlatma SAFE_MODE'da açılır** (`live/baslat.py`): işaret varsa risk motoru ilk bardan
önce kilitlenir. İşaret yalnızca elle ve gerekçeyle kaldırılır (`sq kill kaldir --not`,
K-008/4): izni artıran otomasyon yok (K-050).

Sonuç her zaman `<koşu>.kill.json` raporuna yazılır — hangi adımın ne döndürdüğü, sıfır
emirle bile. Raporsuz bir kill, *"kill switch kasıtlı olarak test edilmiş ve doğru davranmış"*
kriterinin kanıtı olamaz.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol

from scryne_quant.common.zaman import simdi_ms, utc_str

SAFE_UZANTI: Final = ".safemode"
PID_UZANTI: Final = ".pid"
RAPOR_UZANTI: Final = ".kill.json"

#: Sonlandırılan sürecin gerçekten ölmesi için beklenen süre (ms).
OLUM_BEKLEME_MS: Final = 10_000


class KillHatasi(RuntimeError):
    """Kill switch girdisi geçersiz."""


class EmirIptalEdici(Protocol):
    """Kill'in borsadan istediği iki şey. `exchange/imzali.py` bunu karşılıyor."""

    def acik_emirler(self, sembol: str) -> list[Any]: ...

    def emir_iptal(self, *, sembol: str, istemci_kimligi: str) -> Any: ...


def _yol(kosu_yolu: str | Path, uzanti: str) -> Path:
    yol = Path(str(kosu_yolu))
    return yol.with_suffix(yol.suffix + uzanti)


# --------------------------------------------------------------------- pid


def pid_yaz(kosu_yolu: str | Path, pid: int | None = None) -> Path:
    """Trader süreci başlarken çağırır (kilit alındıktan **sonra**)."""
    yol = _yol(kosu_yolu, PID_UZANTI)
    yol.write_text(json.dumps({"pid": pid or os.getpid(), "yazildi_ms": simdi_ms()}),
                   encoding="utf-8")
    return yol


def pid_oku(kosu_yolu: str | Path) -> int | None:
    yol = _yol(kosu_yolu, PID_UZANTI)
    if not yol.is_file():
        return None
    try:
        return int(json.loads(yol.read_text(encoding="utf-8"))["pid"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def pid_sil(kosu_yolu: str | Path) -> None:
    _yol(kosu_yolu, PID_UZANTI).unlink(missing_ok=True)


# --------------------------------------------------------------------- SAFE_MODE işareti


def safe_isaretle(kosu_yolu: str | Path, sebep: str) -> Path:
    yol = _yol(kosu_yolu, SAFE_UZANTI)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(
        json.dumps({"sebep": sebep, "zaman_ms": simdi_ms(), "zaman_utc": utc_str(simdi_ms()),
                    "isteyen_pid": os.getpid()}, ensure_ascii=False),
        encoding="utf-8",
    )
    return yol


def safe_isareti(kosu_yolu: str | Path) -> dict[str, Any] | None:
    """İşaret varsa içeriği. Okunamayan işaret de **işarettir** (bozuk dosya kilidi açmaz)."""
    yol = _yol(kosu_yolu, SAFE_UZANTI)
    if not yol.exists():
        return None
    try:
        return dict(json.loads(yol.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {"sebep": "okunamayan SAFE_MODE işareti", "zaman_ms": None}


def safe_kaldir(kosu_yolu: str | Path, not_metni: str) -> dict[str, Any]:
    """İşareti **elle** kaldırır (K-008/4). Gerekçe ≥ 10 karakter ve kayda geçer."""
    if len(not_metni.strip()) < 10:
        raise KillHatasi("SAFE_MODE işaretini kaldırmak ≥10 karakterlik bir gerekçe ister")
    onceki = safe_isareti(kosu_yolu)
    if onceki is None:
        raise KillHatasi("SAFE_MODE işareti yok")
    _yol(kosu_yolu, SAFE_UZANTI).unlink()
    kayit = {"kaldirildi_ms": simdi_ms(), "not": not_metni, "onceki": onceki}
    gunluk = _yol(kosu_yolu, ".safemode-gecmis.jsonl")
    with gunluk.open("a", encoding="utf-8") as f:
        f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    return kayit


# --------------------------------------------------------------------- süreç


def surec_yasiyor_mu(pid: int) -> bool:
    if sys.platform != "win32":  # pragma: no cover - proje Windows'ta koşuyor
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    tut = k32.OpenProcess(0x1000 | 0x00100000, False, pid)  # QUERY_LIMITED | SYNCHRONIZE
    if not tut:
        return False
    try:
        return k32.WaitForSingleObject(ctypes.c_void_p(tut), 0) == 0x102  # WAIT_TIMEOUT
    finally:
        k32.CloseHandle(ctypes.c_void_p(tut))


def sureci_sonlandir(pid: int, bekleme_ms: int = OLUM_BEKLEME_MS) -> dict[str, Any]:
    """`TerminateProcess` — askıya alınmış süreçte de çalışır. Ölümü bekleyip doğrular."""
    if sys.platform != "win32":  # pragma: no cover
        os.kill(pid, 9)
        return {"pid": pid, "sonlandirildi": not surec_yasiyor_mu(pid)}
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    tut = k32.OpenProcess(0x0001 | 0x00100000, False, pid)  # TERMINATE | SYNCHRONIZE
    if not tut:
        return {"pid": pid, "sonlandirildi": not surec_yasiyor_mu(pid),
                "not": f"süreç açılamadı (hata {ctypes.get_last_error()})"}
    try:
        ok = bool(k32.TerminateProcess(ctypes.c_void_p(tut), 1))
        beklendi = k32.WaitForSingleObject(ctypes.c_void_p(tut), bekleme_ms)
        return {"pid": pid, "terminate": ok, "sonlandirildi": beklendi == 0}
    finally:
        k32.CloseHandle(ctypes.c_void_p(tut))


# --------------------------------------------------------------------- kill


@dataclass
class KillRaporu:
    kosu: str
    sebep: str
    basladi_ms: int
    safe_isaret: str = ""
    pid: int | None = None
    surec: dict[str, Any] = field(default_factory=dict)
    iptaller: list[dict[str, Any]] = field(default_factory=list)
    kalan_acik_emir: dict[str, int] = field(default_factory=dict)
    hatalar: list[str] = field(default_factory=list)
    bitti_ms: int = 0

    @property
    def basarili(self) -> bool:
        surec_tamam = self.pid is None or bool(self.surec.get("sonlandirildi"))
        return (bool(self.safe_isaret) and surec_tamam and not self.hatalar
                and not any(self.kalan_acik_emir.values()))

    def sozluk(self) -> dict[str, Any]:
        return asdict(self) | {"basarili": self.basarili,
                               "basladi_utc": utc_str(self.basladi_ms),
                               "bitti_utc": utc_str(self.bitti_ms) if self.bitti_ms else None}


def kill(
    kosu_yolu: str | Path,
    *,
    sebep: str,
    borsa: EmirIptalEdici | None = None,
    semboller: Sequence[str] = (),
) -> KillRaporu:
    """Üç adım, sıra sabit: SAFE_MODE işareti → süreci sonlandır → açık emirleri iptal et."""
    if len(sebep.strip()) < 5:
        raise KillHatasi("kill bir sebep ister (≥5 karakter)")
    rapor = KillRaporu(kosu=str(kosu_yolu), sebep=sebep, basladi_ms=simdi_ms())

    # 1) İşaret ilk: sonraki adımlar başarısız olsa da yeniden başlatma kilitli açılır.
    rapor.safe_isaret = str(safe_isaretle(kosu_yolu, f"süreç dışı kill: {sebep}"))

    # 2) Süreç.
    rapor.pid = pid_oku(kosu_yolu)
    if rapor.pid is not None:
        if surec_yasiyor_mu(rapor.pid):
            rapor.surec = sureci_sonlandir(rapor.pid)
            if not rapor.surec.get("sonlandirildi"):
                rapor.hatalar.append(f"süreç {rapor.pid} sonlandırılamadı")
        else:
            rapor.surec = {"pid": rapor.pid, "sonlandirildi": True, "not": "zaten ölüydü"}

    # 3) Borsa: iptal, sonra yeniden oku ve doğrula.
    if borsa is not None:
        for sembol in semboller:
            try:
                acik = borsa.acik_emirler(sembol)
            except Exception as hata:  # noqa: BLE001 - her borsa hatası rapora girer
                rapor.hatalar.append(f"{sembol}: açık emirler okunamadı: {hata}")
                continue
            for emir in acik:
                kimlik = getattr(emir, "istemci_kimligi", None)
                try:
                    borsa.emir_iptal(sembol=sembol, istemci_kimligi=kimlik)
                    rapor.iptaller.append({"sembol": sembol, "istemci_kimligi": kimlik,
                                           "sonuc": "iptal"})
                except Exception as hata:  # noqa: BLE001
                    rapor.iptaller.append({"sembol": sembol, "istemci_kimligi": kimlik,
                                           "sonuc": f"hata: {hata}"})
            try:
                rapor.kalan_acik_emir[sembol] = len(borsa.acik_emirler(sembol))
            except Exception as hata:  # noqa: BLE001
                rapor.hatalar.append(f"{sembol}: doğrulama okunamadı: {hata}")
    rapor.bitti_ms = simdi_ms()
    _yol(kosu_yolu, RAPOR_UZANTI).write_text(
        json.dumps(rapor.sozluk(), ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    return rapor


__all__ = [
    "EmirIptalEdici",
    "KillHatasi",
    "KillRaporu",
    "kill",
    "pid_oku",
    "pid_sil",
    "pid_yaz",
    "safe_isaretle",
    "safe_isareti",
    "safe_kaldir",
    "sureci_sonlandir",
    "surec_yasiyor_mu",
]
