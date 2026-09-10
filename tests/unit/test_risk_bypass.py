"""Risk motoru atlanamaz. (§9.1/3, K-032, Roadmap Faz 5 bitti kriteri)

Roadmap'in Faz 5 kriteri şu: *"Risk motoru atlanamıyor — bir sinyalin risk onayı olmadan
execution'a ulaşamayacağı testle kanıtlı."* Bu dosya o kanıt, ve **üç ayrı katmanda**
ölçüyor çünkü hiçbiri tek başına yeterli değil:

1. **Statik katman** (`TestImportGrafigi`): `execution/` ve `oms/` paketlerinin geçişli
   import grafiğinde `strategy.sinyal` yok. Yani execution bir `Sinyal`i tip olarak
   **tanımıyor**; ona sinyal vermek için önce bu testi kırmak gerekir. K-003'ün izolasyon
   testiyle aynı kalıp — ve kasıtlı olarak aynı yöntem (`ast`, import edip `sys.modules`a
   bakmak değil).

2. **Tip katmanı** (`TestKapiTipKontrolu`): kapı `OnayliNiyet` dışında hiçbir şey kabul
   etmiyor. `Sinyal`, `Red`, sözlük, `None` — hepsi `MuhurGecersiz`.

3. **Mühür katmanı** (`TestMuhur`): elle kurulmuş bir `OnayliNiyet` kurulamaz; onaydan
   sonra içeriği değiştirilmiş bir niyet kapıda yakalanır.

**Üçüncü katmanın sınırı açıkça test ediliyor** (`test_muhur_kasitli_asilabilir`): closure
hücresine ulaşıp anahtarı çalmak mümkün ve bu test onu gösteriyor. Neden böyle bir test:
mühürün *ne kadar* koruduğunu belgelemeyen bir test takımı, olmayan bir garanti vaat eder.
Asıl zorlama birinci katman; mühür kazayı ve onay-sonrası değişikliği kapatıyor.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

from scryne_quant.execution.kapi import gonder
from scryne_quant.risk import muhur
from scryne_quant.risk.niyet import OnayliNiyet, Red, RedSebebi, dogrula, onayla
from scryne_quant.strategy.sinyal import Sinyal, Yon

KOK: Final = Path(__file__).resolve().parents[2] / "src"
PAKET: Final = "scryne_quant"

#: Risk onayını atlamanın yolu olabilecek paketler: borsaya giden yolun üstündekiler.
EXECUTION_PAKETLERI: Final[tuple[str, ...]] = (f"{PAKET}.execution", f"{PAKET}.oms")

#: Bu modüllere ulaşmak, execution'ın strateji çıktısını doğrudan görebildiği anlamına
#: gelir. `strategy.sinyal` listede çünkü `Sinyal` tipinin kendisi; `strategy.temel` ve
#: `strategy.kosu` çünkü ikisi de stratejiyi çalıştırıp sinyal üretebilir.
YASAKLI_MODULLER: Final[frozenset[str]] = frozenset(
    {
        f"{PAKET}.strategy.sinyal",
        f"{PAKET}.strategy.temel",
        f"{PAKET}.strategy.kosu",
        f"{PAKET}.strategy.baglam",
    }
)


def _modul_yolu(modul: str) -> Path | None:
    parcalar = modul.split(".")
    dosya = KOK.joinpath(*parcalar).with_suffix(".py")
    if dosya.is_file():
        return dosya
    paket = KOK.joinpath(*parcalar, "__init__.py")
    return paket if paket.is_file() else None


def _proje_modulleri(kok_modul: str) -> list[str]:
    dizin = KOK.joinpath(*kok_modul.split("."))
    adlar: set[str] = set()
    for dosya in dizin.rglob("*.py"):
        parcalar = dosya.relative_to(KOK).with_suffix("").parts
        if parcalar[-1] == "__init__":
            parcalar = parcalar[:-1]
        adlar.add(".".join(parcalar))
    return sorted(adlar)


def _importlar(dosya: Path, modul: str) -> set[str]:
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
            out.update(
                f"{hedef}.{a.name}"
                for a in dugum.names
                if a.name != "*" and _modul_yolu(f"{hedef}.{a.name}")
            )
    return out


#: Zincirin **kesme noktası**: execution'dan strateji katmanına giden her yol bu modülden
#: geçmek zorunda. `OnayliNiyet` sinyali içinde taşıdığı için `risk.niyet → strategy.sinyal`
#: bağımlılığı kaçınılmaz ve **doğru**: onaylı niyet, strateji ne istedi + risk ne verdi
#: ikilisini birlikte taşıyor (audit bu karşılaştırmaya dayanıyor). O hâlde iddia
#: "execution stratejiye hiç ulaşmıyor" değil — ulaşıyor, ama yalnızca risk onayının
#: içinden. Doğru test bunu ölçen test.
KESME_NOKTASI: Final = f"{PAKET}.risk.niyet"


def _kapanis(
    baslangiclar: tuple[str, ...], *, kesilen: frozenset[str] = frozenset()
) -> dict[str, list[str]]:
    """Geçişli import kapanışı: modül → ona ulaşılan yol.

    `kesilen` modüller grafikten **çıkarılır** — o modüle giden kenar izlenmez. Kesme
    noktası testinin mekanizması bu: `risk.niyet` çıkarıldığında strateji katmanı
    ulaşılamaz hâle geliyorsa, oraya giden her yol o modülden geçiyordur.

    Yol tutuluyor çünkü "yasaklı bağımlılık var" teşhis değil;
    `execution.kapi -> risk.niyet -> strategy.sinyal` zinciri teşhis.
    """
    bulunan: dict[str, list[str]] = {}
    kuyruk: list[tuple[str, list[str]]] = []
    for baslangic in baslangiclar:
        for m in _proje_modulleri(baslangic):
            if m in kesilen:
                continue
            bulunan.setdefault(m, [m])
            kuyruk.append((m, [m]))

    while kuyruk:
        modul, yol = kuyruk.pop()
        dosya = _modul_yolu(modul)
        if dosya is None:
            continue
        for hedef in _importlar(dosya, modul):
            if hedef in bulunan or hedef in kesilen:
                continue
            yeni = [*yol, hedef]
            bulunan[hedef] = yeni
            if hedef == PAKET or hedef.startswith(f"{PAKET}."):
                kuyruk.append((hedef, yeni))
    return bulunan


KAPANIS: Final = _kapanis(EXECUTION_PAKETLERI)

#: `risk.niyet` kesilmiş grafik. Strateji katmanı burada görünmemeli.
KAPANIS_KESILMIS: Final = _kapanis(EXECUTION_PAKETLERI, kesilen=frozenset({KESME_NOKTASI}))


def _dogrudan_importlar(paketler: tuple[str, ...]) -> dict[str, set[str]]:
    """Paketlerdeki her modülün **doğrudan** import ettikleri (geçişli değil)."""
    out: dict[str, set[str]] = {}
    for paket in paketler:
        for modul in _proje_modulleri(paket):
            dosya = _modul_yolu(modul)
            if dosya is not None:
                out[modul] = _importlar(dosya, modul)
    return out


def _sinyal(hedef: float = 0.5, yon: Yon = Yon.BUY) -> Sinyal:
    return Sinyal(
        symbol="BTCUSDT",
        side=yon,
        target_exposure=hedef,
        confidence=0.8,
        reason="TEST_SINYALI",
        timestamp=1_700_000_000_000,
    )


class TestImportGrafigi:
    """Birinci katman: execution strateji çıktısını tip olarak tanımıyor."""

    def test_tarama_gercekten_bir_sey_buldu(self):
        """Tarama bozuksa boş küme döner ve her şey temiz görünürdü.

        `test_izolasyon.py`'nin aynı dersi: yeşil ama boş bir tarama, taramasızlıktan
        kötüdür çünkü koruma sanılır.
        """
        assert len(_proje_modulleri(EXECUTION_PAKETLERI[0])) >= 2
        assert f"{PAKET}.risk.niyet" in KAPANIS, "kapı risk.niyet'i import etmeli"

    def test_execution_stratejiyi_dogrudan_import_etmiyor(self):
        """Hiçbir execution/oms modülü strateji katmanından **doğrudan** bir şey almıyor."""
        ihlal = {
            modul: sorted(hedefler & YASAKLI_MODULLER)
            for modul, hedefler in _dogrudan_importlar(EXECUTION_PAKETLERI).items()
            if hedefler & YASAKLI_MODULLER
        }
        assert not ihlal, (
            "execution/oms strateji katmanını doğrudan import ediyor; risk motoru "
            "atlanabilir hâle gelir (§9.1/3):\n"
            + "\n".join(f"  {m}: {', '.join(h)}" for m, h in sorted(ihlal.items()))
        )

    def test_stratejiye_giden_her_yol_risk_onayindan_geciyor(self):
        """**Fazın kriterinin asıl kanıtı.** `risk.niyet` bir kesme noktası.

        `OnayliNiyet` sinyali taşıdığı için `execution → strategy.sinyal` yolu geçişli
        olarak vardır ve olmalıdır. Ölçülen şey o yolun **nereden** geçtiği: `risk.niyet`
        grafikten çıkarıldığında strateji katmanı ulaşılamaz hâle geliyorsa, oraya giden
        tek kapı risk onayıdır.

        Bu test, bir gün `execution/` içine `from scryne_quant.strategy.kosu import ...`
        yazan her denemeyi yakalar — doğrudan import testi kaçırsa bile (örn. araya bir
        `common` modülü koyarak).
        """
        sizan = {
            m: " -> ".join(KAPANIS_KESILMIS[m])
            for m in YASAKLI_MODULLER
            if m in KAPANIS_KESILMIS
        }
        assert not sizan, (
            "risk onayı atlanarak strateji katmanına ulaşan yol var "
            f"({KESME_NOKTASI} kesildiğinde hâlâ erişilebiliyor):\n"
            + "\n".join(f"  {m}: {y}" for m, y in sorted(sizan.items()))
        )

    def test_kesme_noktasi_gercekten_yolun_uzerinde(self):
        """Kesme noktası testinin kendi testi: kesilmemiş grafikte yol **var**.

        Olmasaydı, kesme testi boş bir iddiayı doğrulardı — `execution/`i tamamen silmek
        de onu geçirirdi. Faz 2'nin dersi: yeşil ama boş bir test, testsizlikten kötüdür.
        """
        assert KESME_NOKTASI in KAPANIS
        assert f"{PAKET}.strategy.sinyal" in KAPANIS, (
            "kesilmemiş grafikte strateji katmanına ulaşılamıyorsa kesme testi hiçbir "
            "şey kanıtlamıyor"
        )
        assert f"{PAKET}.risk.muhur" in KAPANIS


class TestKapiTipKontrolu:
    """İkinci katman: kapı `OnayliNiyet` dışında hiçbir şey kabul etmiyor."""

    def test_onayli_niyet_gecer(self):
        niyet = onayla(_sinyal(), 0.3, "limit-kimligi", 1_700_000_000_000, ("azami_maruziyet",))
        kayit = gonder(niyet)
        assert kayit.sembol == "BTCUSDT"
        assert kayit.hedef_maruziyet == 0.3
        assert kayit.kisitlayan == ("azami_maruziyet",)

    def test_ham_sinyal_gecmez(self):
        """En önemli tek test: strateji çıktısı doğrudan execution'a sunulamaz."""
        with pytest.raises(muhur.MuhurGecersiz, match="yalnızca OnayliNiyet"):
            gonder(_sinyal())  # type: ignore[arg-type]

    def test_red_gecmez(self):
        red = Red(
            sinyal=_sinyal(),
            sebep=RedSebebi.SAFE_MODE,
            karar_ms=1_700_000_000_000,
            limit_kimligi="x",
        )
        with pytest.raises(muhur.MuhurGecersiz):
            gonder(red)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "nesne",
        [
            None,
            {},
            {"sembol": "BTCUSDT", "onayli_maruziyet": 1.0},
            "BTCUSDT",
            0.5,
        ],
    )
    def test_taklit_nesneler_gecmez(self, nesne):
        """Sözlük veya sayı göndererek kapıyı geçmek mümkün olmamalı."""
        with pytest.raises(muhur.MuhurGecersiz):
            gonder(nesne)  # type: ignore[arg-type]

    def test_sahte_sinif_gecmez(self):
        """`OnayliNiyet` gibi **görünen** bir sınıf da geçmez: kontrol yapısal değil tipsel.

        Duck typing'e güvenilemez: alanları doğru olan bir nesne, risk motorundan geçmiş
        olduğunu kanıtlamaz.
        """

        class SahteNiyet:
            sinyal = _sinyal()
            onayli_maruziyet = 1.0
            limit_kimligi = "x"
            karar_ms = 1_700_000_000_000
            kisitlayan: tuple[str, ...] = ()
            muhur = "deadbeef"

        with pytest.raises(muhur.MuhurGecersiz):
            gonder(SahteNiyet())  # type: ignore[arg-type]


class TestMuhur:
    """Üçüncü katman: mühür kazara atlamayı ve onay-sonrası değişikliği kapatıyor."""

    def test_elle_kurulan_niyet_kurulamaz(self):
        with pytest.raises(muhur.MuhurGecersiz, match="mühürsüz"):
            OnayliNiyet(
                sinyal=_sinyal(),
                onayli_maruziyet=0.5,
                limit_kimligi="x",
                karar_ms=1_700_000_000_000,
            )

    def test_uydurma_muhur_gecmez(self):
        with pytest.raises(muhur.MuhurGecersiz):
            OnayliNiyet(
                sinyal=_sinyal(),
                onayli_maruziyet=0.5,
                limit_kimligi="x",
                karar_ms=1_700_000_000_000,
                muhur="f" * 64,
            )

    def test_baska_niyetin_muhuru_gecmez(self):
        """Mühür içeriğe bağlı: bir niyetin mührü başka bir niyette çalışmaz."""
        a = onayla(_sinyal(0.5), 0.2, "limit", 1_700_000_000_000)
        with pytest.raises(muhur.MuhurGecersiz):
            OnayliNiyet(
                sinyal=_sinyal(0.5),
                onayli_maruziyet=0.4,  # farklı hedef, aynı mühür
                limit_kimligi="limit",
                karar_ms=1_700_000_000_000,
                muhur=a.muhur,
            )

    def test_onay_sonrasi_degisiklik_kapida_yakalanir(self):
        """Frozen dataclass'ı `object.__setattr__` ile delmek mümkün; kapı yakalıyor.

        Bu, mührün asıl işi: onay bir **an** değil, niyetin ömrü boyunca süren bir
        güvence. Aksi hâlde risk motorunun "aşağı çekebilir, yukarı asla" kuralı yalnızca
        onay anında geçerli olurdu.
        """
        niyet = onayla(_sinyal(0.9), 0.1, "limit", 1_700_000_000_000)
        object.__setattr__(niyet, "onayli_maruziyet", 0.9)
        with pytest.raises(muhur.MuhurGecersiz, match="onay sonrası değiştirilmiş"):
            gonder(niyet)

    def test_risk_yukari_cekemez(self):
        """Onay, sinyalin hedefinden büyük olamaz — kurucu reddeder."""
        with pytest.raises(ValueError, match="aşağı çekebilir, yukarı asla"):
            onayla(_sinyal(0.3), 0.5, "limit", 1_700_000_000_000)

    def test_negatif_onay_kurulamaz(self):
        with pytest.raises(ValueError):
            onayla(_sinyal(0.3), -0.1, "limit", 1_700_000_000_000)

    def test_dogrula_ayni_nesneyi_dondurur(self):
        niyet = onayla(_sinyal(), 0.2, "limit", 1_700_000_000_000)
        assert dogrula(niyet) is niyet

    def test_muhur_kayda_girmiyor(self):
        """Mühür süreç başına rastgele; bir hash'e veya kayda girerse determinizm kırılır.

        K-009'un sessizce ihlal edileceği yer tam olarak burası: audit'e yazılan bir
        mühür, aynı koşunun iki çalıştırmasını farklı gösterirdi.
        """
        niyet = onayla(_sinyal(), 0.2, "limit", 1_700_000_000_000)
        kayit = niyet.sozluk()
        assert "muhur" not in kayit
        assert niyet.muhur not in str(kayit)

    def test_muhur_kasitli_asilabilir(self):
        """**Mührün sınırı belgeleniyor:** closure hücresindeki anahtara ulaşmak mümkün.

        Bu testin amacı mührü zayıflatmak değil, ne vaat ettiğini dürüst tutmak. Python'da
        bir sınıfın dışarıdan kurulmasını imkânsız kılmanın yolu yok; mührün işi kazayı ve
        onay-sonrası değişikliği kapatmak. Kasıtlı atlama mümkün ama aşağıdaki satır gibi
        görünür: gözden geçirmede açıklanması gereken bir kod.

        Asıl zorlama `TestImportGrafigi`: kapı `Sinyal` tipini hiç tanımıyor, dolayısıyla
        mührü aşan biri bile sinyali execution'a **tip olarak** sokamaz.
        """
        anahtar = muhur._imzala.__closure__[0].cell_contents  # type: ignore[union-attr]
        assert isinstance(anahtar, bytes) and len(anahtar) == 32
        # Anahtara ulaşan biri geçerli mühür üretebilir — ve bu beklenen davranış.
        sinyal = _sinyal(0.5)
        alanlar = (sinyal.model_dump_json(), 0.5, "uydurma", 1_700_000_000_000, ())
        sahte = OnayliNiyet(
            sinyal=sinyal,
            onayli_maruziyet=0.5,
            limit_kimligi="uydurma",
            karar_ms=1_700_000_000_000,
            muhur=muhur.muhurle(alanlar),
        )
        assert gonder(sahte).limit_kimligi == "uydurma"
