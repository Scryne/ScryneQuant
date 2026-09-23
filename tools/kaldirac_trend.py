"""Kaldıraçlı vadeli trend / kırılım (K-140). Ön kayıt: `2026-09-23-kaldirac-trend-onkayit.md`.

    .venv/Scripts/python.exe tools/kaldirac_trend.py

İşlemler kaldıraçsız bir kez üretilir (giriş/çıkış, işlem içi en kötü aleyhte hareket = MAE,
funding);
kaldıraç sonradan uygulanır: MAE ≥ 1/L − %0,5 ise dilim o işlemde tamamen kaybedilir.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scryne_quant.aktif import vadeli

KOK = Path(__file__).resolve().parents[1]
SONUC = KOK / "docs/research/records/2026-09-23-kaldirac-trend-sonuc.json"
SEMBOLLER = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT")
BAS, BIT, OOS = "2020-01-01", "2026-09-01", "2024-01-01"
KALDIRACLAR = (1, 2, 3, 5, 10, 20)
MALIYET = (5 + 2) / 1e4
BAKIM = 0.005
SAAT = 3_600_000
TF_MS = {"4h": 4 * SAAT, "1d": 24 * SAAT}


def yukle(s: str) -> tuple[pd.DataFrame, pd.Series]:
    h = pd.read_parquet(
        KOK / f"data/evren/{s}/1h.parquet", columns=["open_time", "open", "high", "low", "close"]
    )
    b, t = pd.Timestamp(BAS, tz="UTC").value // 10**6, pd.Timestamp(BIT, tz="UTC").value // 10**6
    h = h[(h.open_time >= b) & (h.open_time < t)].reset_index(drop=True)
    f = pd.read_parquet(KOK / f"data/turev/funding/{s}.parquet")
    return h, pd.Series(f["last_funding_rate"].to_numpy(), index=f["calc_time"].to_numpy())


def tf_bar(h: pd.DataFrame, tf: str) -> pd.DataFrame:
    g = h.open_time // TF_MS[tf] * TF_MS[tf]
    b = h.groupby(g).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        n=("open", "size"),
    )
    beklenen = TF_MS[tf] // SAAT
    return b[b.n >= beklenen * 0.75]


def islemler(h: pd.DataFrame, fund: pd.Series, tf: str, strat: str, sert_stop: bool) -> list[dict]:
    """Karar/stop mantığı `scryne_quant.aktif.vadeli`den (canlı demo ile aynı kod)."""
    b = tf_bar(h, tf)
    g = vadeli.Gostergeler.hesapla(b)
    kapanis_idx = {int(t) + TF_MS[tf]: k for k, t in enumerate(b.index)}

    o, hi, lo, t = (h[x].to_numpy() for x in ("open", "high", "low", "open_time"))
    f_t, f_r = fund.index.to_numpy(), fund.to_numpy()
    kayit: list[dict] = []
    poz, giris, uc, mae, giris_t, bekleyen, stop_atr = 0, 0.0, 0.0, 0.0, 0, None, np.nan

    def kapat(fiyat: float, zaman: int, neden: str) -> None:
        nonlocal poz
        m = (f_t > giris_t) & (f_t <= zaman)
        kayit.append({"yon": poz, "giris": giris, "cikis": fiyat, "giris_t": giris_t,
                      "cikis_t": zaman, "mae": mae, "funding": float(-poz * f_r[m].sum()),
                      "neden": neden})
        poz = 0

    for i in range(len(h)):
        if bekleyen is not None:  # önceki grafik kapanışında verilen karar, bu barın açılışında
            hedef = bekleyen
            bekleyen = None
            if poz != 0 and hedef != poz:
                kapat(o[i], int(t[i]), "sinyal")
            if hedef != 0 and poz == 0:
                poz, giris, uc, mae, giris_t = hedef, o[i], o[i], 0.0, int(t[i])
        if poz != 0:
            aleyh = (giris - lo[i]) / giris if poz > 0 else (hi[i] - giris) / giris
            mae = max(mae, aleyh)
            seviye = vadeli.stoplar(strat, poz, giris, uc, stop_atr, sert_stop)
            dolum = vadeli.stop_dolumu(poz, o[i], hi[i], lo[i], seviye)
            if dolum is not None:
                kapat(dolum, int(t[i]) + SAAT, "stop")
            else:
                uc = max(uc, hi[i]) if poz > 0 else min(uc, lo[i])
        k = kapanis_idx.get(int(t[i]) + SAAT)
        if k is None:
            continue
        stop_atr = g.atr20[k]
        bekleyen = vadeli.karar(strat, g, k, poz)
    if poz != 0:  # dönem sonunda açık işlem son fiyattan kapatılır (sayılmaması yanlılıktı)
        kapat(float(h["close"].iloc[-1]), int(t[-1]) + SAAT, "donem_sonu")
    return kayit


def uygula(islem: list[dict], L: int) -> tuple[pd.Series, int, float]:
    """Dilim özkaynağı (başlangıç 1) işlem çıkışlarında; likidasyon sayısı; işlem içi en kötü DD."""
    s, liq, zirve, en_kotu = 1.0, 0, 1.0, 0.0
    noktalar = {}
    for x in islem:
        if s <= 0:
            break
        dip = s * (1 - L * x["mae"])
        en_kotu = min(en_kotu, max(dip, 0) / zirve - 1)
        if x["mae"] >= 1 / L - BAKIM:
            s, liq = 0.0, liq + 1
        else:
            brut = x["yon"] * (x["cikis"] / x["giris"] - 1)
            s *= 1 + L * (brut + x["funding"]) - L * 2 * MALIYET
            s = max(s, 0.0)
        zirve = max(zirve, s)
        en_kotu = min(en_kotu, s / zirve - 1)
        noktalar[pd.Timestamp(x["cikis_t"], unit="ms", tz="UTC")] = s
    return pd.Series(noktalar, dtype=float), liq, en_kotu


def portfoy(dilimler: dict[str, list[dict]], L: int, bas: str, bit: str) -> dict[str, Any]:
    b, t = pd.Timestamp(bas, tz="UTC").value // 10**6, pd.Timestamp(bit, tz="UTC").value // 10**6
    gunler = pd.date_range(bas, bit, freq="D", tz="UTC")
    toplam, liq, dd_dilim, islem_say = pd.Series(0.0, index=gunler), 0, 0.0, 0
    for isl in dilimler.values():
        secili = [x for x in isl if b <= x["giris_t"] < t]
        islem_say += len(secili)
        seri, n_liq, dd = uygula(secili, L)
        liq += n_liq
        dd_dilim = min(dd_dilim, dd)
        gunluk = (
            seri.resample("D").last().reindex(gunler).ffill().fillna(1.0)
            if len(seri)
            else pd.Series(1.0, index=gunler)
        )
        toplam += gunluk / len(dilimler)
    yil = len(gunler) / 365.25
    son = float(toplam.iloc[-1])
    return {
        "son": son,
        "yillik": float(max(son, 1e-9) ** (1 / yil) - 1) if son > 0 else -1.0,
        "max_dusus_gunluk": float((toplam / toplam.cummax() - 1).min()),
        "en_kotu_dilim_ici": dd_dilim,
        "likidasyon": liq,
        "islem_hafta": islem_say / (len(gunler) / 7),
    }


def main() -> None:
    veri = {s: yukle(s) for s in SEMBOLLER}
    sonuc = []
    for strat, tf, sert in itertools.product(("S1", "S2", "S3"), ("4h", "1d"), (False, True)):
        dilim = {s: islemler(h, f, tf, strat, sert) for s, (h, f) in veri.items()}
        for L in KALDIRACLAR:
            sonuc.append(
                {
                    "strateji": strat,
                    "tf": tf,
                    "sert_stop": sert,
                    "kaldirac": L,
                    "is": portfoy(dilim, L, BAS, OOS),
                    "oos": portfoy(dilim, L, OOS, BIT),
                }
            )
        print(strat, tf, "sert" if sert else "-", "tamam", flush=True)
    secilen = max(sonuc, key=lambda r: r["is"]["son"])
    rapor = {
        "onkayit": "docs/research/records/2026-09-23-kaldirac-trend-onkayit.md (239d880)",
        "secilen": secilen,
        "demo_olcutu_oos_pozitif": secilen["oos"]["son"] > 1.0,
        "hepsi": sonuc,
    }
    SONUC.write_text(json.dumps(rapor, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\nstrateji tf stop  L | IS son  yıllık  liq | OOS son  yıllık  liq  günlükDD  işlem/hf")
    for r in sonuc:
        i, o = r["is"], r["oos"]
        print(
            f"{r['strateji']} {r['tf']:>3} {'2%' if r['sert_stop'] else ' -'} {r['kaldirac']:>2} | "
            f"{i['son']:7.2f} {i['yillik']:+7.1%} {i['likidasyon']:3d} | {o['son']:7.2f} "
            f"{o['yillik']:+7.1%} {o['likidasyon']:3d} {o['max_dusus_gunluk']:8.1%} "
            f"{o['islem_hafta']:6.1f}"
        )
    print(
        "\nSEÇİLEN:",
        {k: secilen[k] for k in ("strateji", "tf", "sert_stop", "kaldirac")},
        "OOS son",
        round(secilen["oos"]["son"], 3),
    )


if __name__ == "__main__":
    main()
