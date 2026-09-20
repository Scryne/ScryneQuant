"""Çoklu test ölçümünün **git'e giren fotoğrafı**: bekçinin kaynak gerçekliği. (R1(d) D3, K-081)

`COKLU_TEST_ESIGI` defterin belli bir hâlinde ölçüldü; defter büyürse eşik bayattır (K-039,
K-044). Bunu yakalayan bekçi eskiden `runs/faz12/coklu-test-birlesik-*.json`u okuyordu — o
dosya gitignore'da, yani CI'da **yok** ve test sessizce geçiyordu; ölçülebilir sayı da defterden
değil ölçüm çıktısından geliyordu (W6 T2). Bu modül ölçümün küçük bir özetini
`docs/research/coklu-test-olcum.json`a (git'te) yazar: kaç çekiliş ölçüldü, hangi kimlikler,
hangileri ölçülemez, defter kaç satırdı ve **defter dosyasının SHA-256'sı**. Testler
(`tests/unit/test_coklu_test.py::TestEsigiDefteBagla`) sabitleri ve defteri bu fotoğrafla
karşılaştırır: defter bir satır büyürse ya da kimlikler kayarsa CI kırmızı olur.

Fotoğraf **ölçüm aracı tarafından** yazılır (`tools/faz12_coklu_test.py --birlestir` sonunda);
elle düzenlenmez. `COKLU_TEST_CEKILIS_SAYISI` sabiti ayrı durur (eşiğin ölçüldüğü çekiliş
sayısı, D1 kararı) ve fotoğrafla eşit olmak zorundadır — ikisi ayrıştığında sabit değil ölçüm
haklıdır: ya yeniden ölçülür ya da sabit karar kaydıyla güncellenir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from scryne_quant.common.hash import dosya_hash

VARSAYILAN_YOL: Final = Path("docs/research/coklu-test-olcum.json")


class FotografHatasi(ValueError):
    """Fotoğraf yok ya da tutarsız."""


def kur(
    birlesik: dict[str, Any],
    cekilis_kimlikleri: list[str],
    defter_kimlikleri: list[str],
    defter_yolu: str | Path,
    kaynak: str,
) -> dict[str, Any]:
    """Birleşik ölçüm çıktısından fotoğraf gövdesi. Ölçüm dosyasına **yazmaz**, yalnız okur."""
    cekilis = sorted(set(cekilis_kimlikleri))
    defter = list(defter_kimlikleri)
    if len(set(defter)) != len(defter):
        raise FotografHatasi("defterde tekrarlanan kimlik var")
    eksik = sorted(set(cekilis) - set(defter))
    if eksik:
        raise FotografHatasi(f"ölçülen çekiliş defterde yok: {eksik[:3]}…")
    if len(cekilis) != int(birlesik["olculebilir"]):
        raise FotografHatasi(
            f"önbellek {len(cekilis)} çekiliş, birleşik çıktı {birlesik['olculebilir']} diyor"
        )
    if len(defter) != int(birlesik["defter_sayisi"]):
        raise FotografHatasi(
            f"defter {len(defter)} satır, birleşik çıktı {birlesik['defter_sayisi']} diyor"
        )
    null = birlesik["null"]
    return {
        "kaynak": kaynak,
        "uretildi": birlesik["uretildi"],
        "git": birlesik.get("git"),
        "deneme": int(null["deneme"]),
        "seed": int(null["seed"]),
        "defter_sayisi": len(defter),
        "defter_sha256": dosya_hash(Path(defter_yolu)),
        "olculebilir": len(cekilis),
        "tek_sembollu": int(birlesik["tek_sembollu"]),
        "evren": int(birlesik["evren"]),
        "mevcut_esik": float(birlesik["mevcut_esik"]),
        "p05": float(birlesik["duzeltilmis_esikler"]["0.05"]),
        "ga05": [float(x) for x in birlesik["esik_guven_araliklari"]["0.05"]],
        "mevcut_esigin_yanlis_pozitifi": float(birlesik["mevcut_esigin_yanlis_pozitifi"]),
        "cekilis_kimlikleri": cekilis,
        "olculemez_kimlikleri": [k for k in defter if k not in set(cekilis)],
    }


def yaz(govde: dict[str, Any], yol: str | Path = VARSAYILAN_YOL) -> Path:
    p = Path(yol)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(govde, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return p


def oku(yol: str | Path = VARSAYILAN_YOL) -> dict[str, Any]:
    p = Path(yol)
    if not p.exists():
        raise FotografHatasi(f"ölçüm fotoğrafı yok: {p} — `tools/faz12_coklu_test.py --birlestir`")
    return json.loads(p.read_text(encoding="utf-8"))


__all__ = ["VARSAYILAN_YOL", "FotografHatasi", "kur", "oku", "yaz"]
