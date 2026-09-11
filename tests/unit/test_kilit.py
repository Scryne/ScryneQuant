"""Koşu kilidi: bir koşu dosyasını aynı anda tek süreç yazabilir. (Faz 6)

`sq paper baslat` aynı koşu için iki kez çağrılabiliyordu ve hiçbir şey engellemiyordu.
Sonuç bir çökme **olmazdı** — SQLite yazımları serileştirir; tehlikeli olan da bu. İki
trader döngüsü aynı barları işleseydi fill defteri çiftlenir, kontrol noktası birbirinin
üstüne yazılır ve hata ancak bir sonraki toparlanmada, üstelik **yanlış sebeple**
("portföy fill defteriyle ayrıştı") görünürdü.

Kilidin işletim sistemi düzeyinde olması da bir karar: veritabanına pid yazmak, süreç
çökünce bayat bir satır bırakır ve "kilitli mi yoksa ölü mü" sorusu cevapsız kalır — yani
`temiz_kapanmadi`nin çözmek zorunda kaldığı problemin ikinci kopyası. İşletim sistemi
kilidini çekirdek bırakır.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from scryne_quant.live.kilit import KilitAlinamadi, KosuKilidi


class TestAyniSurec:
    def test_alinip_birakiliyor(self, tmp_path) -> None:
        k = KosuKilidi(tmp_path / "k.sqlite").al()
        assert k.tutuluyor
        assert k.yol.name == "k.sqlite.lock"
        k.kapat()
        assert not k.tutuluyor

    def test_kapat_iki_kez_cagrilabiliyor(self, tmp_path) -> None:
        # Kapanış yollarının hepsi (düzgün çıkış, istisna, sinyal) aynı metodu çağırıyor;
        # ikinci çağrının patlaması o basitliği bozardı.
        k = KosuKilidi(tmp_path / "k.sqlite").al()
        k.kapat()
        k.kapat()

    def test_baglam_yoneticisi(self, tmp_path) -> None:
        yol = tmp_path / "k.sqlite"
        with KosuKilidi(yol) as k:
            assert k.tutuluyor
        assert not k.tutuluyor

    def test_birakilan_kilit_yeniden_alinabiliyor(self, tmp_path) -> None:
        yol = tmp_path / "k.sqlite"
        KosuKilidi(yol).al().kapat()
        KosuKilidi(yol).al().kapat()

    def test_pid_olum_sonrasi_iz_olarak_yaziliyor(self, tmp_path) -> None:
        # Pid **kilit tutulurken dışarıdan okunamıyor**: Windows dosyayı başka bir sürece
        # hiç açtırmıyor. Ölçüldü ve kabul edildi — kilit tutulurken sorulan sorunun
        # cevabı zaten `KilitAlinamadi` mesajı. Pid'in işe yaradığı yer ölüm sonrası:
        # "en son kim tutuyordu".
        yol = tmp_path / "k.sqlite"
        k = KosuKilidi(yol).al()
        k.kapat()
        assert f"pid={os.getpid()}".encode() in k.yol.read_bytes()


#: İkinci süreci taklit eden betik. Ayrı bir **süreç** şart: aynı süreç içinde ikinci bir
#: kilit denemesi işletim sisteminin kendi tanıtıcısına çarpar ve gerçek senaryoyu
#: ölçmez — kaza iki ayrı süreçle oldu.
_BETIK = textwrap.dedent(
    """
    import sys
    from scryne_quant.live.kilit import KilitAlinamadi, KosuKilidi

    try:
        KosuKilidi(sys.argv[1]).al()
    except KilitAlinamadi:
        sys.exit(42)
    sys.exit(0)
    """
)


def _ikinci_surec(yol) -> int:
    return subprocess.run(
        [sys.executable, "-c", _BETIK, str(yol)],
        capture_output=True,
        text=True,
        timeout=60,
    ).returncode


class TestIkinciSurec:
    def test_kilit_tutulurken_ikinci_surec_giremiyor(self, tmp_path) -> None:
        yol = tmp_path / "k.sqlite"
        k = KosuKilidi(yol).al()
        try:
            assert _ikinci_surec(yol) == 42
        finally:
            k.kapat()

    def test_kilit_birakilinca_ikinci_surec_girebiliyor(self, tmp_path) -> None:
        yol = tmp_path / "k.sqlite"
        KosuKilidi(yol).al().kapat()
        assert _ikinci_surec(yol) == 0

    def test_surec_olunce_kilit_cekirdek_tarafindan_birakiliyor(self, tmp_path) -> None:
        # Bayat kilit diye bir durum olmamalı: kilidi tutan süreç ölürse kilit gider.
        # Veritabanı satırıyla yapılsaydı bu test yazılamazdı.
        yol = tmp_path / "k.sqlite"
        cocuk = subprocess.Popen(
            [
                sys.executable,
                "-c",
                textwrap.dedent(
                    """
                    import sys, time
                    from scryne_quant.live.kilit import KosuKilidi
                    KosuKilidi(sys.argv[1]).al()
                    print("alindi", flush=True)
                    time.sleep(120)
                    """
                ),
                str(yol),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            assert cocuk.stdout is not None
            assert cocuk.stdout.readline().strip() == "alindi"
            assert _ikinci_surec(yol) == 42  # tutuluyor
        finally:
            cocuk.kill()
            cocuk.wait(timeout=30)
        assert _ikinci_surec(yol) == 0  # süreç öldü, kilit gitti


class TestKurulumKilidi:
    """Kilit `baslat.kur` içinde, koşuya dokunan **ilk** işlem olarak alınıyor."""

    def test_ayni_kosu_iki_kez_kurulamiyor(self, tmp_path) -> None:
        from scryne_quant.common.maliyet import MaliyetModeli
        from scryne_quant.live import baslat as baslat_mod
        from scryne_quant.strategy.kutuphane.sma_kesisim import SmaKesisim
        from tests.conftest import risk_limitleri
        from tests.unit.test_paper_dongu import kimlik as kimlik_kur

        ortak = {
            "strateji": SmaKesisim(hizli=5, yavas=20),
            "maliyet": MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0),
            "limitler": risk_limitleri(),
            "kosu_yolu": tmp_path / "k.sqlite",
            "depo_kok": tmp_path / "depo",
            "adaptor": None,
        }
        kimlik = kimlik_kur("gozlem", strateji=SmaKesisim(hizli=5, yavas=20).sozluk())

        kurulum, _ = baslat_mod.kur(kimlik=kimlik, **ortak)
        try:
            with pytest.raises(KilitAlinamadi, match="zaten çalışıyor"):
                baslat_mod.kur(kimlik=kimlik, **ortak)
        finally:
            kurulum.kapat()

        # Kilit bırakıldıktan sonra aynı koşu yeniden kurulabilmeli (restart yolu).
        ikinci, _ = baslat_mod.kur(kimlik=kimlik, **ortak)
        ikinci.kapat()
