"""Gizli tekrar çekiliş dedektörü. (K-061)

Testler ağa çıkmaz: istemci sahtedir. Gerçek davranış 2026-09-16 spike'ında ölçüldü ve
eşikler oradan geliyor; burada korunan şey o ölçümün **geçerli kalma koşulları**: soru metni
değişmedi, model sabit, kademe kodu eşiklere sadık, modül işlem katmanına sızmıyor.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from scryne_quant.cli import main as cli
from scryne_quant.research import gizli_tekrar as g

KOK = Path(__file__).resolve().parents[2] / "src" / "scryne_quant"


def kayit(n: int, **ek) -> dict:
    return {
        "strateji": f"s{n}",
        "program": "p",
        "timeframe": "1h",
        "secim": "plato",
        "portfoy": "",
        "izgara": {"pencere": [n]},
        "gerekce": f"gerekce {n}",
        "kimlik": f"{n:064x}",
        "veri_sha256": "ab" * 32,
        "zaman_ms": n,
        **ek,
    }


class SahteIstemci:
    """Soru başına sabit dağılım döner; her çağrıyı kaydeder."""

    def __init__(self, dagilim: dict[str, dict[str, float]] | None = None, model: str = g.MODEL):
        self.dagilim = dagilim or {}
        self.model = model
        self.cagrilar: list[tuple[dict, dict, str]] = []
        self.kapandi = False

    def system_one(self, state, questions, *, model=None):
        self.cagrilar.append((state, dict(questions), model))
        choices = {}
        for q in questions:
            p = self.dagilim.get(
                q, {"ayni_mekanizma": 0.01, "parametre_varyasyonu": 0.01, "farkli": 0.98}
            )
            secilen = max(p, key=p.get)
            choices[q] = SimpleNamespace(
                choice=secilen, confidence=max(p.values()), probabilities=p
            )
        return SimpleNamespace(
            model=self.model,
            usage=SimpleNamespace(input_tokens=10, output_tokens=1),
            choices=choices,
        )

    def close(self):
        self.kapandi = True


class TestDonmusSoru:
    def test_soru_metni_ve_model_spiketa_olculen(self):
        # Eşikler bu metinle ölçüldü. Bu hash değişiyorsa yeni spike + yeni K-kaydı gerekir;
        # sabiti güncellemek yetmez (K-061/1).
        assert g.SORU_SHA256 == "e153a7b5ff550bf6ff1577d9855562a075e9392fdda9a76270b3fbff740c0795"
        assert g.MODEL == "jev-1.13.0"
        assert (g.ESIK_UYARI, g.ESIK_INCELE) == (0.80, 0.50)

    def test_kategoriler_kriterlerle_ayni(self):
        assert tuple(g.KRITERLER) == g.KATEGORILER


class TestIstek:
    def test_modele_kimlik_hash_zaman_gitmez(self):
        state, _ = g.istek_kur(kayit(9), [(1, kayit(1))])
        for ozet in (state["yeni"], state["onceki"]["h1"]):
            assert set(ozet) <= set(g.ALANLAR)
            assert "portfoy" not in ozet  # boş alan atılır

    def test_soru_kimligi_ve_referansi_sirayla_eslesir(self):
        _, sorular = g.istek_kur(kayit(9), [(3, kayit(3)), (7, kayit(7))])
        assert list(sorular) == ["h3", "h7"]
        assert "`onceki.h7`" in sorular["h7"]["instructions"]["gorev"]
        assert sorular["h7"]["type"] == "choice"


class TestSeviye:
    @pytest.mark.parametrize(
        ("ilgili", "beklenen"),
        [(0.80, "uyari"), (0.7999, "incele"), (0.50, "incele"), (0.4999, "temiz"), (0.0, "temiz")],
    )
    def test_esik_sinirlari(self, ilgili, beklenen):
        assert g.seviye(ilgili) == beklenen

    def test_ilgili_iki_tekrar_kategorisinin_toplami(self):
        # Ayrı ayrı eşiğin altında, toplamda uyarı: bölünmüş olasılık kaçmamalı.
        cevap = SimpleNamespace(
            choice="farkli",
            confidence=0.1,
            probabilities={"ayni_mekanizma": 0.45, "parametre_varyasyonu": 0.40, "farkli": 0.15},
        )
        b = g.bulgu(1, kayit(1), cevap)
        assert b.ilgili == pytest.approx(0.85)
        assert b.seviye == "uyari"


class TestKontrol:
    def test_parcalara_bolunur_ve_siralanir(self, tmp_path):
        defter = [kayit(i) for i in range(1, g.PARCA_BOYU + 3)]
        istemci = SahteIstemci(
            {
                "h2": {"ayni_mekanizma": 0.9, "parametre_varyasyonu": 0.05, "farkli": 0.05},
                f"h{g.PARCA_BOYU + 1}": {
                    "ayni_mekanizma": 0.3,
                    "parametre_varyasyonu": 0.3,
                    "farkli": 0.4,
                },
            }
        )
        govde = g.kontrol_et(istemci, kayit(999), defter, kayit_koku=tmp_path)

        assert len(istemci.cagrilar) == 2
        assert all(m == g.MODEL for _, _, m in istemci.cagrilar)
        assert govde["karsilastirma"] == len(defter)
        assert [b["sira"] for b in govde["bulgular"][:2]] == [2, g.PARCA_BOYU + 1]
        assert (govde["uyari"], govde["incele"]) == (1, 1)

        dondurulmus = json.loads(Path(govde["kayit"]).read_text(encoding="utf-8"))
        assert dondurulmus["soru_sha256"] == g.SORU_SHA256
        assert len(dondurulmus["istekler"]) == 2

    def test_farkli_model_cozulurse_durur(self):
        with pytest.raises(RuntimeError, match="eşikler geçersiz"):
            g.kontrol_et(SahteIstemci(model="jev-1.14.0"), kayit(9), [kayit(1)], kayit_koku=None)


class TestCli:
    @pytest.fixture
    def defter(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        yol = tmp_path / "docs" / "Hipotez-Defteri.jsonl"
        yol.parent.mkdir()
        yol.write_text("".join(json.dumps(kayit(i)) + "\n" for i in (1, 2, 3)), encoding="utf-8")
        return yol

    def test_sira_ile_oncekilere_bakar_ve_defteri_degistirmez(self, defter, monkeypatch):
        istemci = SahteIstemci(
            {"h1": {"ayni_mekanizma": 0.95, "parametre_varyasyonu": 0.0, "farkli": 0.05}}
        )
        monkeypatch.setattr(cli, "_typesafe_istemci", lambda: istemci)
        once = defter.read_bytes()

        sonuc = CliRunner().invoke(cli.app, ["lab", "tekrar-kontrol", "--sira", "3", "--json"])

        assert sonuc.exit_code == 0, sonuc.output
        govde = json.loads(sonuc.output)
        assert govde["karsilastirma"] == 2
        assert govde["bulgular"][0]["sira"] == 1 and govde["uyari"] == 1
        assert defter.read_bytes() == once  # uyarır, kaydetmez, saymaz
        assert istemci.kapandi

    def test_gerekcesiz_reddedilir_ve_aga_cikmaz(self, defter, monkeypatch):
        monkeypatch.setattr(cli, "_typesafe_istemci", lambda: pytest.fail("ağa çıkmamalı"))
        sonuc = CliRunner().invoke(cli.app, ["lab", "tekrar-kontrol", "al_tut", "-g", "kısa"])
        assert sonuc.exit_code != 0


@pytest.mark.parametrize("paket", ["strategy", "backtest", "features", "risk", "execution", "live"])
def test_islem_katmani_dedektoru_import_etmez(paket):
    """K-049/1, K-049/5: semantik AI alım-satım yoluna ve backtest'e girmez."""
    for dosya in (KOK / paket).rglob("*.py"):
        for dugum in ast.walk(ast.parse(dosya.read_text(encoding="utf-8"))):
            adlar = []
            if isinstance(dugum, ast.Import):
                adlar = [a.name for a in dugum.names]
            elif isinstance(dugum, ast.ImportFrom):
                adlar = [dugum.module or ""] + [a.name for a in dugum.names]
            for ad in adlar:
                assert "typesafe" not in ad and "gizli_tekrar" not in ad, f"{dosya}: {ad}"
