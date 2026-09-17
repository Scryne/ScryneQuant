"""Faz 14 kill switch tatbikatı — gerçek testnet'e karşı, donmuş trader ile. (K-065)

    uv run python tools/faz14_kill_tatbikati.py

Faz 14 bitti kriteri: *"Kill switch, trader süreci askıdayken çalışıyor ve testnet'te
kanıtlanmış: açık emirler iptal edilmiş, süreç durmuş, yeniden başlatma SAFE_MODE'da açılmış."*

1. **Trader** (ayrı süreç): koşu kilidini alır, pid dosyasını yazar, testnet'e piyasanın
   %50 altından iki GTC limit alım emri koyar (dolmaz), sonra sonsuza kadar bekler.
2. Trader **askıya alınır** (`NtSuspendProcess`): yanıt vermeyen süreç.
3. `sq kill calistir ... --testnet` **ayrı bir süreçten** çalışır.
4. Doğrulama bağımsız okumayla: borsada o emirler açık mı, süreç yaşıyor mu, koşu yeniden
   kurulunca risk motoru SAFE_MODE'da mı.
5. İşaret gerekçeyle kaldırılır; rapor `runs/faz14/kill-tatbikati-<zaman>.json`.

Testnet dışına çıkamaz: yalnızca `BinanceImzaliAdaptoru` (testnet host) kurulur.
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.exchange.imzali import BinanceImzaliAdaptoru
from scryne_quant.live import kill as kill_mod

KOK = Path(__file__).resolve().parent.parent
SEMBOL = "BTCUSDT"
NOTIONAL = 10.0

TRADER = r"""
import json, sys, time
from scryne_quant.exchange.imzali import BinanceImzaliAdaptoru
from scryne_quant.live import kill
from scryne_quant.live.kilit import KosuKilidi
kosu, sembol, notional, onek = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
kilit = KosuKilidi(kosu).al()
kill.pid_yaz(kosu)
b = BinanceImzaliAdaptoru()
fiyat = b.son_fiyat(sembol) * 0.5
kimlikler = []
for i in range(2):
    k = f"{onek}-{i}"
    b.limit_emri(istemci_kimligi=k, sembol=sembol, yon="BUY", miktar=notional / fiyat, fiyat=fiyat)
    kimlikler.append(k)
print(json.dumps({"hazir": True, "kimlikler": kimlikler, "fiyat": fiyat}), flush=True)
while True:
    time.sleep(0.5)
"""


def _askiya_al(pid: int) -> int:
    k32 = ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = ctypes.c_void_p
    tut = k32.OpenProcess(0x0800, False, pid)
    if not tut:
        raise SystemExit(f"süreç {pid} açılamadı")
    try:
        return int(ctypes.WinDLL("ntdll").NtSuspendProcess(ctypes.c_void_p(tut)))
    finally:
        k32.CloseHandle(ctypes.c_void_p(tut))


def _acik(borsa: BinanceImzaliAdaptoru, kimlikler: list[str]) -> list[str]:
    return [e.istemci_kimligi for e in borsa.acik_emirler(SEMBOL)
            if e.istemci_kimligi in kimlikler]


def main() -> int:
    zaman = simdi_ms()
    dizin = KOK / "runs" / "faz14"
    dizin.mkdir(parents=True, exist_ok=True)
    kosu = dizin / f"kill-tatbikati-{zaman}.sqlite"
    onek = f"sqkill{zaman}"
    borsa = BinanceImzaliAdaptoru()
    rapor: dict = {"basladi_utc": utc_str(zaman), "kosu": str(kosu), "sembol": SEMBOL}

    trader = subprocess.Popen(
        [sys.executable, "-c", TRADER, str(kosu), SEMBOL, str(NOTIONAL), onek],
        stdout=subprocess.PIPE, text=True, cwd=KOK,
    )
    satir = json.loads(trader.stdout.readline())
    kimlikler = satir["kimlikler"]
    pid = kill_mod.pid_oku(kosu)
    rapor["trader"] = {"baslatici_pid": trader.pid, "pid": pid, "emirler": kimlikler,
                       "limit_fiyat": satir["fiyat"]}
    rapor["once_acik"] = _acik(borsa, kimlikler)

    rapor["askiya_alma_ntstatus"] = _askiya_al(pid)
    time.sleep(1.0)
    rapor["askida_yasiyor"] = kill_mod.surec_yasiyor_mu(pid)

    t0 = time.perf_counter()
    cikti = subprocess.run(
        [sys.executable, "-m", "scryne_quant.cli.main", "kill", "calistir", str(kosu),
         "--sebep", "Faz 14 tatbikati: askidaki trader", "--testnet", "--sembol", SEMBOL,
         "--json"],
        capture_output=True, text=True, cwd=KOK, encoding="utf-8",
    )
    rapor["kill_sure_s"] = round(time.perf_counter() - t0, 2)
    rapor["kill_cikis_kodu"] = cikti.returncode
    rapor["kill_raporu"] = json.loads(cikti.stdout) if cikti.stdout.strip().startswith("{") \
        else {"ham": cikti.stdout[-2000:], "hata": cikti.stderr[-2000:]}

    # Bağımsız doğrulama: kill'in kendi raporuna değil, borsaya ve işletim sistemine sor.
    rapor["sonra_acik"] = _acik(borsa, kimlikler)
    rapor["sonra_yasiyor"] = kill_mod.surec_yasiyor_mu(pid)
    trader.kill()

    from scryne_quant.common.maliyet import MaliyetModeli
    from scryne_quant.live import baslat as baslat_mod
    from scryne_quant.risk import limitler as limitler_mod
    from scryne_quant.strategy.kutuphane.sma_kesisim import SmaKesisim

    strateji = SmaKesisim(hizli=5, yavas=20)
    maliyet = MaliyetModeli(fee_taker_bps=10.0, slippage_bps=5.0)
    limitler = limitler_mod.yukle()
    kimlik = baslat_mod.kimlik_kur(kosu_adi=kosu.stem, mod="gozlem", sembol=SEMBOL,
                                   timeframe="1h", strateji=strateji, maliyet=maliyet,
                                   limitler=limitler, baslangic_sermaye=10_000.0)
    kurulum, _ = baslat_mod.kur(kimlik=kimlik, strateji=strateji, maliyet=maliyet,
                                limitler=limitler, kosu_yolu=kosu, depo_kok=dizin / "depo",
                                adaptor=None)
    try:
        rapor["yeniden_baslatma"] = {
            "safe_mode": kurulum.motor.risk.durum.safe_mode,
            "sebep": kurulum.motor.risk.durum.safe_mode_sebep,
        }
    finally:
        kurulum.kapat()
    kill_mod.safe_kaldir(kosu, "Faz 14 kill tatbikati tamamlandi; isaret temizleniyor")

    rapor["gecti"] = bool(
        len(rapor["once_acik"]) == 2
        and rapor["askiya_alma_ntstatus"] == 0 and rapor["askida_yasiyor"]
        and rapor["kill_cikis_kodu"] == 0
        and rapor["sonra_acik"] == [] and rapor["sonra_yasiyor"] is False
        and rapor["yeniden_baslatma"]["safe_mode"] is True
    )
    yol = dizin / f"kill-tatbikati-{zaman}.json"
    yol.write_text(json.dumps(rapor, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: rapor[k] for k in ("once_acik", "askida_yasiyor", "kill_cikis_kodu",
                                            "kill_sure_s", "sonra_acik", "sonra_yasiyor",
                                            "yeniden_baslatma", "gecti")},
                     ensure_ascii=False, indent=1))
    print(f"yazıldı: {yol}")
    return 0 if rapor["gecti"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
