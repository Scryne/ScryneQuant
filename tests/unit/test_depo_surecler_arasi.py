"""Süreçler arası determinizm. (K-009, Faz 1 bitti kriteri)

Faz 1'in kriteri "aynı indirme **komutu** iki kez çalıştırıldığında dosya bit düzeyinde
aynı" diyor — komut demek ayrı bir süreç demek. Aynı süreç içinde iki kez yazmak bunu
kanıtlamaz: süreç ömrü boyunca sabit kalan (ama süreçler arasında değişebilen) bir şey
dosyaya sızarsa, tek süreçli test bunu göremez.

Bu yüzden test gerçekten ikinci bir Python süreci başlatıyor.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

from tests.conftest import bar_uret

_YAZICI = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, {tests_kok!r})
    from scryne_quant.data.depo import ParquetDepo
    from tests.conftest import bar_uret

    kok = sys.argv[1]
    print(ParquetDepo(kok).yaz("BTCUSDT", "1h", bar_uret()).sha256)
    """
)


def _ayri_surecte_yaz(kok, proje_kok) -> str:
    """Yeni bir Python sürecinde yazıp dosyanın SHA-256'sını döndürür."""
    kod = _YAZICI.format(tests_kok=str(proje_kok))
    sonuc = subprocess.run(
        [sys.executable, "-c", kod, str(kok)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert sonuc.returncode == 0, f"alt süreç hata verdi:\n{sonuc.stderr}"
    return sonuc.stdout.strip()


def test_iki_ayri_surec_ayni_bayt(tmp_path):
    """İki ayrı süreç aynı veriyi yazınca dosyalar bit düzeyinde aynı."""
    proje_kok = __import__("pathlib").Path(__file__).resolve().parents[2]

    a = _ayri_surecte_yaz(tmp_path / "a", proje_kok)
    b = _ayri_surecte_yaz(tmp_path / "b", proje_kok)

    assert a == b, "süreçler arası hash farklı — dosyaya süreç-özel bir şey sızıyor"

    bayt_a = (tmp_path / "a" / "BTCUSDT" / "1h.parquet").read_bytes()
    bayt_b = (tmp_path / "b" / "BTCUSDT" / "1h.parquet").read_bytes()
    assert bayt_a == bayt_b


def test_ayni_surecteki_hashle_tutarli(tmp_path):
    """Alt süreçteki hash, bu süreçte hesaplananla aynı olmalı."""
    from scryne_quant.data.depo import ParquetDepo

    proje_kok = __import__("pathlib").Path(__file__).resolve().parents[2]

    icerde = ParquetDepo(tmp_path / "ic").yaz("BTCUSDT", "1h", bar_uret()).sha256
    disarda = _ayri_surecte_yaz(tmp_path / "dis", proje_kok)

    assert icerde == disarda
