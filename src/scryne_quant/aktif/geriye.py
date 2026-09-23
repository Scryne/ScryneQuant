"""Aktif bot backtest'i: canlı döngüyle aynı strateji, aynı ağırlık ve fren kuralları. (K-134)

Zamanlama (K-004): bar k'nın kapanışında verilen karar bar k+1'in açılışında uygulanır ve
k+1 açılışından k+2 açılışına kadar getiri kazanır. Maliyet her ağırlık değişiminde
`|Δw| × (ücret + kayma)` (K-007: kayma hep aleyhte).

Yaklaşım (yazılı kalsın): ağırlıklar bar boyunca sabit kabul edilir (fiyatla kayma yok);
15 dakikalık barlarda fark küçüktür, işlem sayısını değiştirmez.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from scryne_quant.aktif import strateji as strateji_mod
from scryne_quant.aktif.dongu import HesapAyari
from scryne_quant.aktif.risk import ESIK, FrenDurumu, agirlik_adimi
from scryne_quant.common.zaman import timeframe_ms


def geriye(
    barlar: dict[str, pd.DataFrame],
    ayar: HesapAyari,
    *,
    yalniz_long: bool,
    ucret_bps: float,
    kayma_bps: float,
) -> pd.DataFrame:
    """Kapanış zamanı indeksli çıktı: `ozkaynak`, `islem` (o bar kapanışında verilen emir sayısı),
    `brut` (toplam brüt ağırlık)."""
    adim = timeframe_ms(ayar.timeframe)
    maliyet = (ucret_bps + kayma_bps) / 10_000
    semboller = [s for s, df in barlar.items() if len(df)]
    zaman = np.array(sorted(set().union(*[set(barlar[s].index) for s in semboller])), dtype="int64")
    yon: dict[str, np.ndarray] = {}
    atr_o: dict[str, np.ndarray] = {}
    getiri: dict[str, np.ndarray] = {}
    for s in semboller:
        df = barlar[s]
        y = strateji_mod.yon_serisi(ayar.strateji, df, ayar.parametreler, yalniz_long=yalniz_long)
        a = strateji_mod.atr(df) / df["close"]
        g = df["open"].shift(-1) / df["open"] - 1.0
        yon[s] = y.reindex(zaman).to_numpy()
        atr_o[s] = a.reindex(zaman).to_numpy()
        getiri[s] = g.reindex(zaman).fillna(0.0).to_numpy()

    w: dict[str, float] = {}
    fren = FrenDurumu()
    ozk = 1.0
    cikti_ozk = np.empty(len(zaman))
    cikti_islem = np.zeros(len(zaman), dtype=int)
    cikti_brut = np.zeros(len(zaman))
    for k, t in enumerate(zaman):
        # 1) Bar k boyunca (açılış k → açılış k+1) mevcut ağırlıklar kazanır.
        #    Getiri dizisi sembolün kendi sonraki açılışına göre; bar yoksa 0.
        ozk *= 1.0 + sum(wi * getiri[s][k] for s, wi in w.items())
        # 2) Bar k kapanışında karar.
        sebep = fren.guncelle(ozk, int(t) + adim, ayar.risk)
        yonler = {s: float(yon[s][k]) for s in semboller if not np.isnan(yon[s][k])}
        oranlar = {s: float(atr_o[s][k]) for s in yonler if not np.isnan(atr_o[s][k])}
        yeni = agirlik_adimi(w, yonler, oranlar, ayar.risk, fren=sebep is not None)
        degisim = [abs(yeni.get(s, 0.0) - w.get(s, 0.0)) for s in set(yeni) | set(w)]
        ozk *= 1.0 - maliyet * sum(degisim)
        cikti_islem[k] = sum(1 for d in degisim if d > ESIK)
        w = {s: v for s, v in yeni.items() if abs(v) > ESIK}
        cikti_ozk[k] = ozk
        cikti_brut[k] = sum(abs(v) for v in w.values())
    indeks = pd.to_datetime(zaman + adim, unit="ms", utc=True)
    return pd.DataFrame({"ozkaynak": cikti_ozk, "islem": cikti_islem, "brut": cikti_brut},
                        index=indeks)


def ozet(sonuc: pd.DataFrame) -> dict[str, Any]:
    """Haftalık odaklı özet: kullanıcının sorusu 'haftada ne kazanır'."""
    if sonuc.empty:
        return {}
    eq = sonuc["ozkaynak"]
    son = eq.resample("W-SUN").last().ffill()
    haftalik = son / son.shift(1).fillna(1.0) - 1.0  # ilk haftanın tabanı başlangıç (1,0)
    hafta_sayisi = max(len(haftalik), 1)
    dd = float((eq / eq.cummax() - 1.0).min())
    std = float(haftalik.std()) if len(haftalik) > 1 else 0.0
    return {
        "hafta": int(hafta_sayisi),
        "toplam_getiri": float(eq.iloc[-1] - 1.0),
        "haftalik_ortalama": float(haftalik.mean()),
        "haftalik_medyan": float(haftalik.median()),
        "pozitif_hafta": float((haftalik > 0).mean()),
        "en_iyi_hafta": float(haftalik.max()),
        "en_kotu_hafta": float(haftalik.min()),
        "sharpe_haftalik_yillik": float(haftalik.mean() / std * np.sqrt(52)) if std > 0 else 0.0,
        "max_dusus": dd,
        "islem_hafta": float(sonuc["islem"].sum() / hafta_sayisi),
        "ort_brut": float(sonuc["brut"].mean()),
    }
