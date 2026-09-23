"""`sq execution` uçtan uca: mod tavanı, paper tekrar koşusu, kill switch. (K-114)"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scryne_quant.cli.main import app
from scryne_quant.exchange.akis import df_barlara
from scryne_quant.exchange.kurallar import SembolKurallari
from scryne_quant.exchange.paper_adaptoru import PaperBorsa, PaperMaliyet
from scryne_quant.execution.mod import CalismaModu
from scryne_quant.trader.kurulum import KosuIstegi, KurulumHatasi, kosu_kur
from tests.conftest import bar_uret

REPO = Path(__file__).resolve().parents[2]
K = SembolKurallari("BTCUSDT", 0.01, 0.00001, 5.0, "TRADING", "BTC", "USDT")


@pytest.fixture
def calisma(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    for ad in ("r8_kriterler.json", "risk.json", "maliyet.json"):
        shutil.copy(REPO / "config" / ad, tmp_path / "config" / ad)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def istek(**kw):
    return KosuIstegi(mod=CalismaModu.PAPER, kosu="k", strateji="sma_kesisim",
                      parametreler={"hizli": 5, "yavas": 20}, kurallar=K,
                      tekrar_barlari=df_barlara(bar_uret(n=300)), **kw)


def test_mod_tavani_disabled_iken_paper_kosusu_acilmaz(calisma):
    with pytest.raises(KurulumHatasi, match="sistem modu DISABLED"):
        kosu_kur(istek())


def test_paper_tekrar_ve_kill(calisma):
    r = CliRunner()
    assert r.invoke(app, ["execution", "yukselt", "PAPER", "--not", "test"]).exit_code == 0
    y, kaynak = kosu_kur(istek())
    rapor = y.tekrar_oynat(kaynak, isinma=100)
    assert rapor["gecti"], rapor["kalan"]
    (calisma / "runs/execution/k/kurallar.json").write_text(
        json.dumps({f: getattr(K, f) for f in K.__dataclass_fields__}), encoding="utf-8")

    # Açık bir emir bırak (koşu dışından, paper borsaya): kill onu iptal etmeli.
    pb = PaperBorsa(kurallar={"BTCUSDT": K}, maliyet=PaperMaliyet(0, 0), saat=lambda: 1,
                    yol=calisma / "runs/execution/k/paper_borsa.sqlite")
    pb.market_emri(istemci_kimligi="acik1", sembol="BTCUSDT", yon="BUY", miktar=0.001)
    pb.kapat()

    s = r.invoke(app, ["execution", "kill", "--kosu", "k", "--sebep", "tatbikat", "--json"])
    assert s.exit_code == 0, s.output
    kayit = json.loads((calisma / "runs/execution/k/kill.json").read_text(encoding="utf-8"))
    assert kayit["basarili"] and kayit["kalan_acik_emir"] == {"BTCUSDT": 0}
    assert not kayit["canli_host"]
    assert (calisma / "runs/execution/k/kosu.safemode").is_file()

    # SAFE_MODE yalnız gerekçeyle kalkar.
    assert r.invoke(app, ["execution", "safe-kaldir", "--kosu", "k", "--not", "kısa"]).exit_code
    s = r.invoke(app, ["execution", "safe-kaldir", "--kosu", "k", "--not",
                       "tatbikat bitti, işaret kaldırılıyor"])
    assert s.exit_code == 0 and not (calisma / "runs/execution/k/kosu.safemode").exists()


def test_live_preflight_bugun_kapali(calisma):
    s = CliRunner().invoke(app, ["execution", "preflight", "--hedef", "LIVE_PENDING_APPROVAL",
                                 "--strateji", "sma_kesisim", "--json"])
    assert s.exit_code == 1
    rapor = json.loads(s.output)
    assert not rapor["gecti"] and rapor["engeller"]


def test_onay_tty_olmadan_verilmez(calisma):
    s = CliRunner().invoke(app, ["execution", "onayla", "--strateji", "s", "--hash", "x",
                                 "--not", "yirmi karakterden uzun bir not"])
    assert s.exit_code == 2 and "etkileşimli" in s.output


def test_kill_adaptor_kurulamasa_da_isaret_ve_basarisiz_rapor(calisma):
    """Kill'in borsaya bağlı olmayan adımları (SAFE_MODE işareti) adaptör hatasında da olur;
    açık emirler doğrulanamadığı için rapor BAŞARISIZ (önceden komut tamamen patlıyordu)."""
    r = CliRunner()
    assert r.invoke(app, ["execution", "yukselt", "PAPER", "--not", "test"]).exit_code == 0
    y, kaynak = kosu_kur(istek())
    assert y.hat.mod_tavani is not None  # çalışan koşu sistem modunu okur
    y.tekrar_oynat(kaynak, isinma=100)
    # kurallar.json yok → paper adaptörü kurulamaz
    s = r.invoke(app, ["execution", "kill", "--kosu", "k", "--sebep", "adaptor yok", "--json"])
    assert s.exit_code == 1
    kayit = json.loads((calisma / "runs/execution/k/kill.json").read_text(encoding="utf-8"))
    assert not kayit["basarili"] and any("adaptör kurulamadı" in h for h in kayit["hatalar"])
    assert (calisma / "runs/execution/k/kosu.safemode").is_file()


def test_kosu_kapat_gate_i_birakir_ama_kosu_bir_daha_baslamaz(calisma):
    from scryne_quant.execution.canli_kapi import KapiBaglami, kritik_hata_kontrolu

    r = CliRunner()
    assert r.invoke(app, ["execution", "yukselt", "PAPER", "--not", "test"]).exit_code == 0
    y, kaynak = kosu_kur(istek())
    y.tekrar_oynat(kaynak, isinma=100)
    y.hat.safe_isaretle("tatbikat")
    b = KapiBaglami(kok=calisma)
    assert kritik_hata_kontrolu(b).gecti is False
    assert r.invoke(app, ["execution", "kosu-kapat", "--kosu", "k", "--not", "kisa"]).exit_code
    s = r.invoke(app, ["execution", "kosu-kapat", "--kosu", "k", "--not",
                       "tatbikat koşusu, işlem yapamaz hâlde arşivleniyor"])
    assert s.exit_code == 0, s.output
    assert kritik_hata_kontrolu(b).gecti is True
    assert (calisma / "runs/execution/k/kosu.safemode").is_file()  # işaret kalkmadı
    with pytest.raises(KurulumHatasi, match="kapatılmış"):
        kosu_kur(istek())


def test_sabit_oran_paper_tekrari_risk_profiliyle_hedefe_ulasir(calisma):
    """K-132: yatırım kuralı canlı yolla aynı kurulumdan geçer; risk profili config eşlemesinden
    gelir ve %50 hedefi ~%11'e (genel profilin ATR boyutlandırması) kırpılmaz."""
    for ad in ("risk_profilleri.json", "risk_yatirim.json"):
        shutil.copy(REPO / "config" / ad, calisma / "config" / ad)
    r = CliRunner()
    assert r.invoke(app, ["execution", "yukselt", "PAPER", "--not", "test"]).exit_code == 0
    y, kaynak = kosu_kur(KosuIstegi(mod=CalismaModu.PAPER, kosu="u", strateji="sabit_oran",
                                    parametreler={}, kurallar=K, sermaye_usdt=100.0,
                                    tekrar_barlari=df_barlara(bar_uret(n=300))))
    rapor = y.tekrar_oynat(kaynak, isinma=100)
    assert rapor["gecti"], rapor["kalan"]
    durum = json.loads((calisma / "runs/execution/u/durum.json").read_text(encoding="utf-8"))
    hesap = durum.get("hesap") or {}
    maruziyet = hesap.get("maruziyet") or hesap.get("brut_maruziyet")
    assert maruziyet is not None, list(hesap)
    assert 0.40 < float(maruziyet) < 0.60, hesap
