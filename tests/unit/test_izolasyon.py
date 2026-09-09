"""İzolasyon testi: `strategy/` paketi I/O yapamaz. (K-003, Faz 2)

K-003 diyor ki "zorlanmayan mimari kural, kural değil temennidir". Bu dosya o zorlamanın
kendisi: `scryne_quant.strategy` altındaki her modülün import grafiği **geçişli olarak**
taranır ve yasaklı bir bağımlılığa ulaşan bir yol bulunursa test kırılır.

Geçişlilik şart. `strategy` yalnızca `common.hash`'i import etse tarama yüzeysel olsaydı
temiz görünürdü — oysa `common.hash` `subprocess` çağırıyor. Bir adım derine bakmayan
izolasyon testi, tam da engellemesi gereken şeyi kaçırır.

**Yöntem: izin listesi, yasak listesi değil.** K-003 beş isim sayıyor (`ccxt`, `requests`,
`httpx`, `socket`, `open`) ama yasak listesi her zaman eksiktir: `aiohttp`, `urllib3`,
`smtplib`, `paramiko`, `pyarrow`... Yeni bir I/O kütüphanesi bir gün listeye eklenmeyi
unutulur ve kural sessizce delinir. İzin listesinde ise unutmanın yönü güvenli tarafa
düşer: listede olmayan her şey reddedilir ve eklemek bilinçli, gözden geçirilebilir bir
diff olur. K-003'ün saydığı beş isim ayrıca kendi testinde açıkça kontrol ediliyor —
kararın metni testte görünür kalsın diye.

Tarama statiktir (`ast`): modülleri import edip `sys.modules`'a bakmak, yan etkileri
çalıştırmak demek olurdu — ve yan etki tam olarak aradığımız şey.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

KOK = Path(__file__).resolve().parents[2] / "src"
PAKET = "scryne_quant"
BASLANGIC = f"{PAKET}.strategy"

#: Strateji katmanının erişebileceği **proje içi** modüller.
#: - `features.indikator`, `features.motor`: saf numpy hesap, I/O yok.
#: - `common.zaman`: yalnızca aritmetik; `common.hash` **yok** (subprocess çağırıyor).
#: - `features.barlar` **yok**: pandas'ı oraya hapsetmiş olmamızın tek sebebi bu satır.
IZINLI_PROJE: Final[frozenset[str]] = frozenset(
    {
        "scryne_quant",
        "scryne_quant.strategy",
        "scryne_quant.features",
        "scryne_quant.features.indikator",
        "scryne_quant.features.motor",
        "scryne_quant.common",
        "scryne_quant.common.zaman",
    }
)

#: Strateji katmanının erişebileceği dış kütüphaneler ve stdlib modülleri.
#: Hepsi saf hesap/tip: dosya, ağ, süreç veya rastgelelik yüzeyi yok.
IZINLI_DIS: Final[frozenset[str]] = frozenset(
    {
        "__future__",
        "abc",
        "collections",
        "dataclasses",
        "enum",
        "functools",
        "itertools",
        "math",
        "numpy",
        "operator",
        "pydantic",
        "re",
        "types",
        "typing",
    }
)

#: K-003'ün metninde geçen isimler. İzin listesi bunları zaten dışarıda bırakıyor; ayrıca
#: kontrol edilmelerinin sebebi, kararın hangi somut riski kapattığının testte okunur
#: kalması.
K003_YASAKLI: Final[frozenset[str]] = frozenset({"ccxt", "requests", "httpx", "socket"})

#: Bu isimlerin **çağrılması** yasak: import olmadan I/O açan veya statik taramayı
#: anlamsızlaştıran kaçış yolları.
YASAKLI_CAGRILAR: Final[frozenset[str]] = frozenset(
    {"open", "eval", "exec", "compile", "__import__", "input", "breakpoint"}
)


def _modul_yolu(modul: str) -> Path | None:
    parcalar = modul.split(".")
    dosya = KOK.joinpath(*parcalar).with_suffix(".py")
    if dosya.is_file():
        return dosya
    paket = KOK.joinpath(*parcalar, "__init__.py")
    return paket if paket.is_file() else None


def _proje_modulleri(kok_modul: str) -> list[str]:
    """`kok_modul` altındaki tüm proje modülleri (paketin kendisi dahil).

    `__init__.py` dosyaları paketin **kendi** adıyla döner (`...strategy`), sahte bir
    `...strategy.__init__` adıyla değil — yol çözümü ikisinde de çalışır ama hata
    mesajlarında görünen isim gerçek modül adı olmalı.
    """
    dizin = KOK.joinpath(*kok_modul.split("."))
    adlar: set[str] = set()
    for dosya in dizin.rglob("*.py"):
        parcalar = dosya.relative_to(KOK).with_suffix("").parts
        if parcalar[-1] == "__init__":
            parcalar = parcalar[:-1]
        adlar.add(".".join(parcalar))
    return sorted(adlar)


def _importlar(dosya: Path, modul: str) -> set[str]:
    """Bir dosyanın import ettiği modül adları (göreli import'lar çözülmüş)."""
    agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
    out: set[str] = set()
    paket = modul if dosya.name == "__init__.py" else modul.rpartition(".")[0]

    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            out.update(a.name for a in dugum.names)
        elif isinstance(dugum, ast.ImportFrom):
            if dugum.level:
                ust = paket.split(".")
                taban = ".".join(ust[: len(ust) - dugum.level + 1])
                hedef = f"{taban}.{dugum.module}" if dugum.module else taban
            else:
                hedef = dugum.module or ""
            if not hedef:
                continue
            out.add(hedef)
            # `from paket import modul` — alt modül import'u da bir bağımlılıktır.
            out.update(
                f"{hedef}.{a.name}"
                for a in dugum.names
                if a.name != "*" and _modul_yolu(f"{hedef}.{a.name}")
            )
    return out


def _kapanis(baslangic: str) -> dict[str, list[str]]:
    """Geçişli import kapanışı: her modül → ona ulaşılan yol.

    Yol da tutuluyor çünkü "yasaklı bağımlılık var" tek başına teşhis değil;
    `strategy.x → common.hash → subprocess` zinciri teşhis.
    """
    # Kök paket `baslangic`ten türetiliyor, sabit kodlanmıyor: `TestTaramaninKendisi`
    # tarayıcıyı sahte bir paket üzerinde çalıştırıyor ve sabit kodlanmış bir kök adı,
    # öz-testin hiçbir zaman gerçek tarayıcıyı denemediği anlamına gelirdi.
    kok_paket = baslangic.split(".")[0]

    bulunan: dict[str, list[str]] = {}
    kuyruk: list[tuple[str, list[str]]] = [(m, [m]) for m in _proje_modulleri(baslangic)]
    for modul, yol in kuyruk:
        bulunan.setdefault(modul, yol)

    while kuyruk:
        modul, yol = kuyruk.pop()
        dosya = _modul_yolu(modul)
        if dosya is None:  # proje dışı: içine bakmıyoruz, adına bakıyoruz
            continue
        for hedef in _importlar(dosya, modul):
            if hedef in bulunan:
                continue
            yeni = [*yol, hedef]
            bulunan[hedef] = yeni
            if hedef == kok_paket or hedef.startswith(f"{kok_paket}."):
                kuyruk.append((hedef, yeni))
    return bulunan


KAPANIS = _kapanis(BASLANGIC)


def _yol(modul: str) -> str:
    return " → ".join(KAPANIS[modul])


class TestImportGrafigi:
    def test_tarama_gercekten_bir_sey_buldu(self):
        """Tarama bozuksa boş küme döner ve her şey temiz görünürdü."""
        assert len(_proje_modulleri(BASLANGIC)) >= 5
        assert "numpy" in KAPANIS
        assert f"{PAKET}.features.motor" in KAPANIS

    def test_proje_ici_bagimliliklar_izinli(self):
        ihlal = {
            m: _yol(m)
            for m in KAPANIS
            if (m == PAKET or m.startswith(f"{PAKET}."))
            and not m.startswith(f"{BASLANGIC}.")
            and m not in IZINLI_PROJE
        }
        assert not ihlal, "strateji katmanı izinli olmayan proje modülüne ulaşıyor:\n" + "\n".join(
            f"  {m}: {y}" for m, y in sorted(ihlal.items())
        )

    def test_dis_bagimliliklar_izinli(self):
        ihlal = {
            m: _yol(m)
            for m in KAPANIS
            if not (m == PAKET or m.startswith(f"{PAKET}."))
            and m.split(".")[0] not in IZINLI_DIS
        }
        assert not ihlal, "strateji katmanı izinli olmayan dış modüle ulaşıyor:\n" + "\n".join(
            f"  {m}: {y}" for m, y in sorted(ihlal.items())
        )

    @pytest.mark.parametrize("yasak", sorted(K003_YASAKLI))
    def test_k003un_saydigi_isimler_yok(self, yasak: str):
        ulasilan = [m for m in KAPANIS if m == yasak or m.startswith(f"{yasak}.")]
        assert not ulasilan, f"K-003 açıkça yasaklıyor: {yasak} ({_yol(ulasilan[0])})"

    def test_pandas_ve_pyarrow_erisilemiyor(self):
        """pandas/pyarrow dosya okuyabilir; `features.barlar` bu yüzden ayrı bir modül."""
        for yasak in ("pandas", "pyarrow", "duckdb"):
            ulasan = [m for m in KAPANIS if m.split(".")[0] == yasak]
            assert not ulasan, f"{yasak} erişilebilir: {_yol(ulasan[0])}"

    def test_features_barlar_erisilemiyor(self):
        assert f"{PAKET}.features.barlar" not in KAPANIS

    def test_common_hash_erisilemiyor(self):
        """`common.hash` subprocess çağırıyor — yüzeysel bir tarama bunu kaçırırdı."""
        assert f"{PAKET}.common.hash" not in KAPANIS

    def test_exchange_data_execution_erisilemiyor(self):
        for katman in ("exchange", "data", "execution", "oms", "cli", "risk", "portfolio"):
            assert f"{PAKET}.{katman}" not in KAPANIS, f"{katman} erişilebilir"


class TestYasakliCagrilar:
    """Import etmeden I/O açan yollar: `open(...)`, `eval`, `__import__`."""

    @staticmethod
    def _cagri_adlari(dosya: Path) -> set[str]:
        agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
        return {
            d.func.id
            for d in ast.walk(agac)
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
        }

    @pytest.mark.parametrize("modul", _proje_modulleri(BASLANGIC))
    def test_yasakli_cagri_yok(self, modul: str):
        dosya = _modul_yolu(modul)
        assert dosya is not None
        ihlal = self._cagri_adlari(dosya) & YASAKLI_CAGRILAR
        assert not ihlal, f"{modul}: yasaklı çağrı {sorted(ihlal)} (K-003)"


class TestTaramaninKendisi:
    """Tarayıcı yakalayamıyorsa yeşil renk bir şey ifade etmez."""

    def test_gecisli_yasak_yakalaniyor(self, tmp_path: Path):
        """`a → b → socket` zinciri kurulur; tarayıcı `socket`e ulaşmalı."""
        paket = tmp_path / "sahte" / "strategy"
        paket.mkdir(parents=True)
        (tmp_path / "sahte" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "sahte" / "ara.py").write_text("import socket\n", encoding="utf-8")
        (paket / "__init__.py").write_text("", encoding="utf-8")
        (paket / "a.py").write_text("from sahte import ara\n", encoding="utf-8")

        global KOK  # noqa: PLW0603 - taramanın kökünü geçici olarak yönlendiriyoruz
        gercek = KOK
        try:
            KOK = tmp_path
            kapanis = _kapanis("sahte.strategy")
        finally:
            KOK = gercek

        assert "socket" in kapanis, "geçişli yasaklı bağımlılık yakalanamadı"
        assert kapanis["socket"] == ["sahte.strategy.a", "sahte.ara", "socket"]

    def test_yasakli_cagri_yakalaniyor(self, tmp_path: Path):
        dosya = tmp_path / "ornek.py"
        dosya.write_text("def f():\n    return open('x')\n", encoding="utf-8")
        assert "open" in TestYasakliCagrilar._cagri_adlari(dosya)
