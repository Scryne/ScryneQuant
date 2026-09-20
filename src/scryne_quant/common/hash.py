"""Reproducibility kimlikleri: veri seti hash'i, config hash'i, ortam kaydı. (K-009)

Spike 3 ölçtü ki PyArrow'un Parquet çıktısı bit düzeyinde deterministik — aynı DataFrame
iki kez yazıldığında dosyanın SHA-256'sı aynı. Bu yüzden veri seti kimliği için ayrı bir
içerik-hash mekanizmasına gerek yok: **dosyanın kendi hash'i kimliktir.**

Bunun kıymeti şu: dosya kopyalanınca, taşınınca, altı ay sonra yeniden açılınca aynı
kimliği veriyor — canlı bir veritabanının durumu için aynısı geçerli değil.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

_OKUMA_BLOGU = 1 << 20  # 1 MiB


def dosya_hash(yol: str | Path) -> str:
    """Dosyanın SHA-256'sı. Veri seti kimliği budur (K-009)."""
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for blok in iter(lambda: f.read(_OKUMA_BLOGU), b""):
            h.update(blok)
    return h.hexdigest()


def nesne_hash(nesne: Any) -> str:
    """Config gibi JSON'a çevrilebilir bir nesnenin deterministik hash'i.

    `sort_keys` şart: sözlük sırası değişince hash'in değişmesi, aynı config'i farklı
    göstermek olurdu.
    """
    ham = json.dumps(nesne, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(ham.encode("utf-8")).hexdigest()


def git_durumu(repo: str | Path | None = None) -> dict[str, Any]:
    """Commit SHA ve working tree'nin kirli olup olmadığı.

    K-009: kirli ağaçtan üretilen sonuç engellenmez ama `dirty` işaretlenir ve promotion
    zincirine giremez. Kirli ağaçta kaydedilen commit, sonucu üreten kodu tarif etmez —
    yani reproducibility iddiası o sonuç için yalandır.
    """
    kok = str(repo) if repo else None

    def calistir(*args: str) -> str | None:
        try:
            ciktisi = subprocess.run(
                ["git", *args],
                cwd=kok,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if ciktisi.returncode != 0:
            return None
        return ciktisi.stdout.strip()

    sha = calistir("rev-parse", "HEAD")
    if sha is None:
        return {"commit": None, "dirty": None, "git_yok": True}

    durum = calistir("status", "--porcelain")
    return {"commit": sha, "dirty": bool(durum), "git_yok": False}


#: Ortam kaydına sürümü yazılan paketler. `duckdb` 2026-09-20'de çıktı (R1(f)): hiç kullanılmıyordu
#: ve bağımlılıktan kaldırıldı. Eski kayıtların `kimlik.ortam.paketler`inde `duckdb` anahtarı var,
#: yenilerinde yok — bu bilgilendirici bir alan, hiçbir hash'e (`girdi_hash`, `cikti_hash`,
#: `config_hash`, `sonuc_hash`) girmiyor; `tests/unit/test_ortam_kaydi.py` bunu koruyor.
VARSAYILAN_PAKETLER: tuple[str, ...] = ("pandas", "numpy", "pyarrow", "ccxt")


def ortam_kaydi(paketler: tuple[str, ...] = VARSAYILAN_PAKETLER) -> dict[str, Any]:
    """Sonuç kaydına yazılacak ortam bilgisi (K-009).

    Kütüphane sürümleri `uv.lock` ile kilitli, ama kayıt yine de çalıştırma anındaki
    gerçeği yazar — kilit dosyası ile kurulu ortamın ayrışabildiği durumları görmek için.
    """
    surumler: dict[str, str | None] = {}
    for ad in paketler:
        try:
            surumler[ad] = version(ad)
        except PackageNotFoundError:
            surumler[ad] = None
    return {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "paketler": surumler,
    }
