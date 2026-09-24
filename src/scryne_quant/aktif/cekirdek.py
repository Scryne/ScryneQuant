"""Çekirdek portföy (K-141): BTC + ETH, trend filtreli, oynaklık hedefli, kaldıraçsız spot.

Her gün UTC 00:00 kapanışından sonra bir kez:
- Varlık başına ağırlık = (hedef_vol / varlık sayısı) / 30 günlük yıllık oynaklık (EWM).
- Trend filtresi: kapanışın SMA100 ve SMA200 üstünde olma oranı (0, ½, 1) ile çarpılır — tek
  bir SMA uzunluğu seçilmez.
- Brüt ağırlık toplamı ≤ `tavan` (spot, kaldıraç yok → 1,0).
- Hedefle mevcut arasındaki mutlak fark `bant`ı aşmıyorsa işlem yok (hedef 0 ise her zaman kapat).

Karar fonksiyonu (`hedef_agirliklar`, `dengele`) **tek yerde**; geriye bakış
(`tools/cekirdek_arastirma.py`) de buradan çağırır. Emir yok: `KriptoPaper` Binance spot
fiyatıyla simüle dolum yapar.
"""

from __future__ import annotations

import datetime as dt
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from scryne_quant.aktif.araci import AraciHatasi
from scryne_quant.aktif.defter import Defter
from scryne_quant.common.zaman import simdi_ms

GUN_MS: Final = 86_400_000
SMA_BOYLARI: Final = (100, 200)
VOL_SPAN: Final = 30
ISINMA: Final = max(SMA_BOYLARI) + 1


@dataclass(frozen=True)
class CekirdekAyari:
    semboller: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    hedef_vol: float = 0.3
    tavan: float = 1.0
    bant: float = 0.05
    asgari_emir: float = 10.0


def hedef_agirliklar(kapanis: pd.DataFrame, ayar: CekirdekAyari) -> pd.DataFrame:
    """Günlük kapanış paneli (satır = gün, sütun = sembol) → her günün kapanışındaki hedef.

    Satır d yalnız d ve öncesini kullanır; işlem d+1 açılışında (K-004).
    """
    getiri = kapanis.pct_change(fill_method=None)
    vol = getiri.ewm(span=VOL_SPAN, min_periods=20).std() * np.sqrt(365)
    filtre = sum((kapanis > kapanis.rolling(n).mean()).astype(float) for n in SMA_BOYLARI)
    filtre = filtre / len(SMA_BOYLARI)
    w = (ayar.hedef_vol / len(ayar.semboller)) / vol * filtre
    w = w.where(kapanis.rolling(max(SMA_BOYLARI)).mean().notna())
    w = w.replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(lower=0.0)
    brut = w.sum(axis=1)
    return w.div(np.maximum(brut / ayar.tavan, 1.0), axis=0)


def dengele(onceki: dict[str, float], hedef: dict[str, float], bant: float) -> dict[str, float]:
    """Bant içindeki farkları yok say; hedef 0 ise pozisyon her zaman kapanır."""
    yeni = {}
    for s, w in hedef.items():
        w0 = onceki.get(s, 0.0)
        yeni[s] = w if (w == 0.0 or abs(w - w0) > bant) else w0
    return yeni


# ------------------------------------------------------------------ canlı demo


def _gunluk(araci: Any, sembol: str, simdi: int) -> pd.Series:
    """Kapanmış günlük barlar (UTC). Açık gün atılır."""
    df = araci.barlar(sembol, "1d", ISINMA + 60)
    df = df[df.index + GUN_MS <= simdi]
    return df["close"].astype(float)


def cekirdek_tur(araci: Any, defter: Defter, ayar: CekirdekAyari, simdi: int) -> dict[str, Any]:
    kapanis = pd.DataFrame({s: _gunluk(araci, s, simdi) for s in ayar.semboller}).sort_index()
    son_gun = int(kapanis.index[-1])
    if son_gun + 2 * GUN_MS <= simdi:  # dünün barı yoksa veri bayat: işlem yok (K-037)
        raise AraciHatasi(f"bayat günlük veri: son bar {son_gun}")
    hedef = hedef_agirliklar(kapanis, ayar).iloc[-1].to_dict()
    ozk = araci.ozkaynak()
    pozlar = araci.pozisyonlar()
    fiyat = {s: araci.fiyat(s) for s in ayar.semboller}
    onceki = {s: pozlar.get(s, 0.0) * fiyat[s] / ozk for s in ayar.semboller}
    yeni = dengele(onceki, hedef, ayar.bant)
    emirler = []
    for s in ayar.semboller:
        hedef_adet = araci.adet_yuvarla(s, yeni[s] * ozk / fiyat[s])
        delta = round(hedef_adet - pozlar.get(s, 0.0), 8)
        if delta == 0 or (yeni[s] != 0.0 and abs(delta) * fiyat[s] < ayar.asgari_emir):
            continue
        emirler.append((s, delta, "cikis" if yeni[s] == 0.0 else "dengele"))
    emirler.sort(key=lambda e: 0 if e[1] < 0 else 1)  # önce satış (nakit açar)
    yapilan = []
    for s, delta, neden in emirler:
        try:
            dolum = araci.emir(s, delta, neden)
        except AraciHatasi as hata:
            defter.olay(simdi, "emir_hatasi", {"sembol": s, "delta": delta, "hata": str(hata)})
            continue
        defter.islem(simdi, dolum, dolum.adet * dolum.fiyat, neden)
        yapilan.append(f"{s} {delta:+.6f} @ {dolum.fiyat:.2f}")
    son = araci.ozkaynak()
    defter.ozkaynak(simdi, son)
    defter.olay(simdi, "cekirdek", {"hedef": hedef, "uygulanan": yeni})
    return {"ozkaynak": son, "hedef": hedef, "emirler": yapilan}


def calistir_cekirdek(araci: Any, dizin: Path, ayar: CekirdekAyari, yaz: Any = print) -> None:
    """Günde bir karar (UTC 00:05); saatlik özkaynak izi. `dizin/dur` görülünce temiz biter."""
    from scryne_quant.live.kilit import KosuKilidi

    dizin.mkdir(parents=True, exist_ok=True)
    kilit = KosuKilidi(dizin / "aktif")
    kilit.al()
    defter = Defter(dizin)
    dur = dizin / "dur"
    son_karar_gun = -1
    try:
        defter.olay(simdi_ms(), "basla", {"strateji": "cekirdek", "hedef_vol": ayar.hedef_vol})
        while not dur.exists():
            simdi = simdi_ms()
            try:
                gun = simdi // GUN_MS
                if gun != son_karar_gun and simdi % GUN_MS >= 5 * 60_000:
                    r = cekirdek_tur(araci, defter, ayar, simdi)
                    son_karar_gun = gun
                    yaz(f"{dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} özkaynak {r['ozkaynak']:.2f} "
                        f"hedef {({k: round(v, 3) for k, v in r['hedef'].items()})} "
                        f"{'; '.join(r['emirler'])}")
                else:
                    defter.ozkaynak(simdi, araci.ozkaynak())
            except Exception as hata:  # noqa: BLE001 — tur hatası döngüyü öldürmez
                defter.olay(simdi_ms(), "tur_hatasi",
                            {"hata": repr(hata), "iz": traceback.format_exc()[-2000:]})
                yaz(f"tur hatası: {hata!r}")
            sonraki = (simdi_ms() // 3_600_000 + 1) * 3_600_000 + 5 * 60_000
            while not dur.exists() and simdi_ms() < sonraki:
                time.sleep(min(5.0, max(0.5, (sonraki - simdi_ms()) / 1000)))
        defter.olay(simdi_ms(), "dur", {})
        dur.unlink(missing_ok=True)
    finally:
        defter.kapat()
        kilit.kapat()
