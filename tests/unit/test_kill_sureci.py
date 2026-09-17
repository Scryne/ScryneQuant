"""Süreç dışı kill switch. (Faz 14, K-065, Denetim-v2 A8)

Faz 14'ün bitti kriteri: *"Kill switch, trader süreci **askıdayken** çalışıyor: açık emirler
iptal edilmiş, süreç durmuş, yeniden başlatma SAFE_MODE'da açılmış."* Borsa kısmı burada
sahte bir borsayla; testnet kanıtı `docs/Faz-14-*` raporunda.
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from dataclasses import dataclass

import pytest

from scryne_quant.live import kill as kill_mod

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows süreç API'si")


def _askiya_al(pid: int) -> None:
    """`NtSuspendProcess`: sürecin bütün iş parçacıklarını dondurur (yanıt vermeyen trader)."""
    k32 = ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = ctypes.c_void_p
    tut = k32.OpenProcess(0x0800, False, pid)  # PROCESS_SUSPEND_RESUME
    assert tut, "süreç açılamadı"
    try:
        assert ctypes.WinDLL("ntdll").NtSuspendProcess(ctypes.c_void_p(tut)) == 0
    finally:
        k32.CloseHandle(ctypes.c_void_p(tut))


@pytest.fixture
def donmus_trader(tmp_path):
    """Koşu kilidini tutan, pid dosyasını yazan ve sonra askıya alınan bir süreç."""
    kosu = tmp_path / "k.sqlite"
    betik = (
        "import sys, time\n"
        "from scryne_quant.live.kilit import KosuKilidi\n"
        "from scryne_quant.live import kill\n"
        f"k = KosuKilidi(r'{kosu}').al()\n"
        f"kill.pid_yaz(r'{kosu}')\n"
        "print('hazir', flush=True)\n"
        "while True: time.sleep(0.1)\n"
    )
    cocuk = subprocess.Popen([sys.executable, "-c", betik], stdout=subprocess.PIPE, text=True)
    assert cocuk.stdout.readline().strip() == "hazir"
    # `.venv\Scripts\python.exe` bir başlatıcı; asıl yorumlayıcı onun alt süreci. Trader'ın
    # kimliği pid dosyasındaki süreçtir — kill de onu hedefler, test de onu dondurur.
    pid = kill_mod.pid_oku(kosu)
    assert pid is not None
    _askiya_al(pid)
    yield kosu, pid
    if kill_mod.surec_yasiyor_mu(pid):
        kill_mod.sureci_sonlandir(pid)
    cocuk.kill()


@dataclass
class Emir:
    istemci_kimligi: str


class SahteBorsa:
    def __init__(self, emirler, izlenen_pid=None, iptal_hatasi=False):
        self.emirler = list(emirler)
        self.izlenen_pid = izlenen_pid
        self.iptal_hatasi = iptal_hatasi
        self.iptal_aninda_surec_yasiyordu: list[bool] = []

    def acik_emirler(self, sembol):
        return list(self.emirler)

    def emir_iptal(self, *, sembol, istemci_kimligi):
        if self.izlenen_pid is not None:
            self.iptal_aninda_surec_yasiyordu.append(
                kill_mod.surec_yasiyor_mu(self.izlenen_pid))
        if self.iptal_hatasi:
            raise RuntimeError("borsa reddetti")
        self.emirler = [e for e in self.emirler if e.istemci_kimligi != istemci_kimligi]


class TestDonmusTrader:
    def test_askidaki_surec_sonlandirilir_emirler_iptal_isaret_yazilir(self, donmus_trader):
        kosu, pid = donmus_trader
        borsa = SahteBorsa([Emir("a"), Emir("b")], izlenen_pid=pid)
        rapor = kill_mod.kill(kosu, sebep="tatbikat: donmuş trader", borsa=borsa,
                              semboller=("BTCUSDT",))
        assert rapor.basarili, rapor.sozluk()
        assert rapor.surec["sonlandirildi"] is True
        assert kill_mod.surec_yasiyor_mu(pid) is False
        assert borsa.emirler == [] and rapor.kalan_acik_emir == {"BTCUSDT": 0}
        # Sıra: emirler süreç öldükten **sonra** iptal edildi.
        assert borsa.iptal_aninda_surec_yasiyordu == [False, False]
        assert kill_mod.safe_isareti(kosu)["sebep"].startswith("süreç dışı kill")
        kayit = json.loads(kosu.with_suffix(".sqlite.kill.json").read_text(encoding="utf-8"))
        assert kayit["basarili"] is True and len(kayit["iptaller"]) == 2

    def test_kilit_serbest_kalir(self, donmus_trader):
        from scryne_quant.live.kilit import KosuKilidi

        kosu, pid = donmus_trader
        kill_mod.kill(kosu, sebep="tatbikat: kilit")
        assert kill_mod.surec_yasiyor_mu(pid) is False
        KosuKilidi(kosu).al().kapat()


class TestRapor:
    def test_iptal_basarisizsa_kill_basarisiz(self, tmp_path):
        kosu = tmp_path / "k.sqlite"
        rapor = kill_mod.kill(kosu, sebep="tatbikat: red",
                              borsa=SahteBorsa([Emir("a")], iptal_hatasi=True),
                              semboller=("BTCUSDT",))
        assert not rapor.basarili
        assert rapor.kalan_acik_emir == {"BTCUSDT": 1}
        assert kill_mod.safe_isareti(kosu) is not None  # işaret yine de yazıldı

    def test_pid_dosyasi_yoksa_surec_adimi_atlanir(self, tmp_path):
        rapor = kill_mod.kill(tmp_path / "k.sqlite", sebep="tatbikat: pidsiz")
        assert rapor.pid is None and rapor.basarili

    def test_sebep_zorunlu(self, tmp_path):
        with pytest.raises(kill_mod.KillHatasi):
            kill_mod.kill(tmp_path / "k.sqlite", sebep=" ")


class TestIsaret:
    def test_kaldirmak_gerekce_ister_ve_kaydeder(self, tmp_path):
        kosu = tmp_path / "k.sqlite"
        kill_mod.safe_isaretle(kosu, "deneme")
        with pytest.raises(kill_mod.KillHatasi):
            kill_mod.safe_kaldir(kosu, "kısa")
        kill_mod.safe_kaldir(kosu, "tatbikat bitti, host sağlıklı")
        assert kill_mod.safe_isareti(kosu) is None
        gecmis = kosu.with_suffix(".sqlite.safemode-gecmis.jsonl").read_text(encoding="utf-8")
        assert "tatbikat bitti" in gecmis

    def test_bozuk_isaret_kilidi_acmaz(self, tmp_path):
        kosu = tmp_path / "k.sqlite"
        kosu.with_suffix(".sqlite.safemode").write_text("{bozuk", encoding="utf-8")
        assert kill_mod.safe_isareti(kosu) is not None


class TestBaslatma:
    def _ortak(self, tmp_path):
        from scryne_quant.common.maliyet import MaliyetModeli
        from scryne_quant.strategy.kutuphane.sma_kesisim import SmaKesisim
        from tests.conftest import risk_limitleri

        return {
            "strateji": SmaKesisim(hizli=5, yavas=20),
            "maliyet": MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0),
            "limitler": risk_limitleri(),
            "kosu_yolu": tmp_path / "k.sqlite",
            "depo_kok": tmp_path / "depo",
            "adaptor": None,
        }

    def _kimlik(self):
        from scryne_quant.strategy.kutuphane.sma_kesisim import SmaKesisim
        from tests.unit.test_paper_dongu import kimlik as kimlik_kur

        return kimlik_kur("gozlem", strateji=SmaKesisim(hizli=5, yavas=20).sozluk())

    def test_isaret_varsa_safe_modeda_acilir_pid_yazilir_ve_silinir(self, tmp_path):
        from scryne_quant.live import baslat as baslat_mod

        ortak = self._ortak(tmp_path)
        kill_mod.safe_isaretle(ortak["kosu_yolu"], "süreç dışı kill: tatbikat")
        kurulum, _ = baslat_mod.kur(kimlik=self._kimlik(), **ortak)
        try:
            assert kurulum.motor.risk.durum.safe_mode is True
            assert "tatbikat" in kurulum.motor.risk.durum.safe_mode_sebep
            assert kill_mod.pid_oku(ortak["kosu_yolu"]) is not None
        finally:
            kurulum.kapat()
        assert kill_mod.pid_oku(ortak["kosu_yolu"]) is None

    def test_isaret_yoksa_normal_acilir(self, tmp_path):
        from scryne_quant.live import baslat as baslat_mod

        kurulum, _ = baslat_mod.kur(kimlik=self._kimlik(), **self._ortak(tmp_path))
        try:
            assert kurulum.motor.risk.durum.safe_mode is False
        finally:
            kurulum.kapat()


def test_surec_yasiyor_mu_olu_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait(timeout=10)
    time.sleep(0.2)
    assert kill_mod.surec_yasiyor_mu(p.pid) is False
