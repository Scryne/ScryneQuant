"""Jev paketinin bağımlılık yönü tek ve statik olarak zorlanıyor. (K-074/2)

`test_gizli_tekrar.py::test_islem_katmani_dedektoru_import_etmez` bir yönü kapatıyor: işlem
katmanı `typesafe`i import etmez. Bu dosya diğer yönü kapatıyor: `jev/` paketi risk, execution
ve OMS'e **ulaşamaz** — geçişli olarak da. Böylece "Jev'den emir çıkmaz" cümlesi bir temenni
değil, diff'te görünen bir satır olmadan bozulamayan bir kural (K-003 ve K-032'nin kalıbı).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

KOK: Final = Path(__file__).resolve().parents[2] / "src" / "scryne_quant"

#: `jev/` paketinin geçişli import grafiğinde bulunamayacak modüller.
YASAKLI: Final[frozenset[str]] = frozenset(
    {
        "scryne_quant.risk",
        "scryne_quant.execution",
        "scryne_quant.oms",
        "scryne_quant.exchange.imzali",  # imzalı (yazma yetkili) borsa istemcisi
        "scryne_quant.exchange.emir_adaptoru",
    }
)

#: İşlem katmanı: `jev`i ve `typesafe`i import edemez (K-074/2; K-049/1, K-049/5).
ISLEM_KATMANI: Final[tuple[str, ...]] = (
    "strategy",
    "backtest",
    "features",
    "risk",
    "execution",
    "oms",
    "live",
)


def _importlar(dosya: Path) -> set[str]:
    agac = ast.parse(dosya.read_text(encoding="utf-8"))
    out: set[str] = set()
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            out.update(a.name for a in dugum.names)
        elif isinstance(dugum, ast.ImportFrom) and dugum.module:
            out.add(dugum.module)
            out.update(f"{dugum.module}.{a.name}" for a in dugum.names)
    return out


def _modul_dosyasi(ad: str) -> Path | None:
    parcalar = ad.split(".")
    if parcalar[0] != "scryne_quant":
        return None
    yol = KOK.joinpath(*parcalar[1:])
    if yol.with_suffix(".py").exists():
        return yol.with_suffix(".py")
    if (yol / "__init__.py").exists():
        return yol / "__init__.py"
    # `from paket import ad` biçiminde son parça bir isim olabilir
    ust = KOK.joinpath(*parcalar[1:-1])
    if ust.with_suffix(".py").exists():
        return ust.with_suffix(".py")
    if (ust / "__init__.py").exists():
        return ust / "__init__.py"
    return None


def _gecisli_kapanis(baslangic: Path) -> dict[str, set[str]]:
    """Dosyadan başlayarak proje içi geçişli import kapanışı: modül → import ettikleri."""
    kapanis: dict[str, set[str]] = {}
    yigin = [baslangic]
    gorulen: set[Path] = set()
    while yigin:
        dosya = yigin.pop()
        if dosya in gorulen:
            continue
        gorulen.add(dosya)
        adlar = _importlar(dosya)
        kapanis[str(dosya.relative_to(KOK.parent))] = adlar
        for ad in adlar:
            hedef = _modul_dosyasi(ad)
            if hedef is not None and hedef not in gorulen:
                yigin.append(hedef)
    return kapanis


def _jev_dosyalari() -> list[Path]:
    return sorted((KOK / "jev").rglob("*.py"))


def test_tarama_gercekten_bir_sey_buldu():
    assert _jev_dosyalari(), "jev/ paketi bulunamadı"


@pytest.mark.parametrize("dosya", _jev_dosyalari(), ids=lambda p: p.name)
def test_jev_risk_execution_omsa_ulasamaz(dosya: Path):
    kapanis = _gecisli_kapanis(dosya)
    ihlal = {
        modul: sorted(a for a in adlar if any(a == y or a.startswith(y + ".") for y in YASAKLI))
        for modul, adlar in kapanis.items()
    }
    ihlal = {m: a for m, a in ihlal.items() if a}
    assert not ihlal, "jev/ geçişli olarak yasaklı bir modüle ulaşıyor:\n" + "\n".join(
        f"  {m} → {', '.join(a)}" for m, a in ihlal.items()
    )


@pytest.mark.parametrize("paket", ISLEM_KATMANI)
def test_islem_katmani_jevi_import_etmez(paket: str):
    for dosya in (KOK / paket).rglob("*.py"):
        for ad in _importlar(dosya):
            assert "scryne_quant.jev" not in ad and "typesafe" not in ad, f"{dosya}: {ad}"


def test_typesafe_yalnizca_istemci_modulunde():
    """SDK'nın tek giriş noktası `jev/istemci.py` (ve K-061'in `research/gizli_tekrar.py`'si)."""
    for dosya in _jev_dosyalari():
        if dosya.name == "istemci.py":
            continue
        for ad in _importlar(dosya):
            assert "typesafe" not in ad, f"{dosya}: SDK yalnızca istemci.py'de import edilir"


def test_gecisli_yasak_yakalaniyor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Negatif kontrol: `jev.a → common.ara → execution` zinciri kurulur; tarayıcı yakalamalı."""
    kok = tmp_path / "scryne_quant"
    (kok / "jev").mkdir(parents=True)
    (kok / "common").mkdir()
    (kok / "execution").mkdir()
    for p in (kok, kok / "jev", kok / "common", kok / "execution"):
        (p / "__init__.py").write_text("", encoding="utf-8")
    (kok / "execution" / "kapi.py").write_text("def gonder(x):\n    return x\n", encoding="utf-8")
    (kok / "common" / "ara.py").write_text(
        "from scryne_quant.execution.kapi import gonder\n", encoding="utf-8"
    )
    (kok / "jev" / "a.py").write_text("from scryne_quant.common import ara\n", encoding="utf-8")

    import sys

    modul = sys.modules[__name__]
    monkeypatch.setattr(modul, "KOK", kok)
    kapanis = _gecisli_kapanis(kok / "jev" / "a.py")
    hepsi = {a for adlar in kapanis.values() for a in adlar}
    assert any(a.startswith("scryne_quant.execution") for a in hepsi), (
        "geçişli yasaklı bağımlılık yakalanamadı"
    )
