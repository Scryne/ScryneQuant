"""Vadeli (long/short) tavan ölçümü: short bacağı zaman serisi trendine değer katıyor mu? (K-123)

**Soru:** vadeli hesap açmaya (K-079/2) değer mi? h63 (yalnız-long zaman serisi trend) OOS'ta
2025-26 düşüşünde kaybetti; aynı sinyal short tarafıyla düşüşten kazanabilirdi. Bu araç hesap
açmadan, **yalnız IS'te** (2023-12-24'e kadar; OOS'a bakılmaz) long/short'un long-only'ye göre
katkısını ölçer. Çekiliş değil: promotion kanıtı üretmez, defteri büyütmez, parametre seçmez
(dört pencere birlikte raporlanır, en iyisi seçilmez).

**Model (tavan, sade):** 12 sembol (funding geçmişi olanlar), haftalık (168 bar) dengeleme, sinyal
= kendi `pencere` barlık getirisinin işareti. Long bacak spot (funding yok); short bacak perp
(fiyat ≈ spot, **funding alınır/ödenir** gerçek geçmiş oranlarla). Eşit ağırlık, brüt 1. Maliyet
taraf başı 15,3 bps (spot: 10 fee + 5,3 kayma; perp: public 5 bps taker'ın **2 katı** + 5,3 kayma
≈ aynı); long→short geçişi iki bacak işlem sayılır. Basis değişimi ve likidasyon yok (kaldıraç 1).

**Sınırlar:** bugün listede olan 12 sembol (hayatta kalma yanlılığı — iki kolu da aynı etkiler);
perp fiyatı = spot varsayımı; fee kademesi doğrulanmadı (K-079: bu yüzden ×2 tutucu).

**Karar kuralı (ölçümden ÖNCE yazıldı):** vadeli hesap açmak için veriye dayalı gerekçe **yalnız**
şu üçü birlikte sağlanırsa var:
  (1) dört pencerenin **en az üçünde** long/short IS Sharpe ≥ long-only IS Sharpe + 0,30;
  (2) aynı pencerelerde long/short IS Sharpe ≥ 0,80;
  (3) short bacağın kendi katkısı IS yıllarının (2020-2023) **en az üçünde** pozitif (yalnız 2022
      ayısına bağlı olmamalı).
Aksi hâlde K-079/2 (vadeli hesap açılmıyor) veriyle desteklenir; short mimarisi yazılmaz.

    uv run python tools/vadeli_tavan.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

KOK = Path(__file__).resolve().parent.parent
SEMBOLLER = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "LTCUSDT", "ADAUSDT", "DOGEUSDT",
             "SOLUSDT", "LINKUSDT", "TRXUSDT", "BCHUSDT", "XLMUSDT")
IS_SONU = pd.Timestamp("2023-12-24 02:00", tz="UTC")  # evren IS/OOS sınırı (bar 55.678)
PENCERELER = (336, 720, 1440, 2160)
HAFTA = 168
MALIYET = 15.3e-4  # taraf başı
#: Ortak haftalık karar takvimi (Pazartesi 00:00 UTC). Sembol başına ayrı takvim kurmak tarihleri
#: hizalamıyordu: her "hafta" tek sembol taşıyıp çeşitlendirmeyi yok ediyordu (ilk koşuda
#: 1.815 hafta, %100 düşüş — ölçüm hatası, sonuç değil).
TAKVIM = pd.date_range(pd.Timestamp("2019-09-16 00:00", tz="UTC"),
                       IS_SONU - pd.Timedelta(hours=HAFTA + 1), freq=f"{HAFTA}h")


def _veri(sembol: str) -> tuple[pd.Series, pd.Series]:
    sp = pd.read_parquet(KOK / "data" / "evren" / sembol / "1h.parquet")
    acilis = pd.Series(sp["open"].to_numpy(float),
                       index=pd.to_datetime(sp["open_time"], unit="ms", utc=True))
    kapanis = pd.Series(sp["close"].to_numpy(float), index=acilis.index)
    fu = pd.read_parquet(KOK / "data" / "funding" / f"{sembol}.parquet")
    fon = pd.Series(fu["funding_rate"].to_numpy(float),
                    index=pd.to_datetime(fu["funding_time"], unit="ms", utc=True)).sort_index()
    return pd.concat([acilis, kapanis], axis=1, keys=["o", "c"]), fon


def sembol_haftalari(sembol: str, pencere: int) -> pd.DataFrame:
    """Her karar anı için: sinyal, sonraki haftanın spot getirisi, o haftada ödenen funding."""
    fiyat, fon = _veri(sembol)
    fiyat = fiyat.asfreq("1h").ffill()  # boşluk barları ileri doldurulur (gap sayısı küçük)
    bas = max(fon.index.min().ceil("h"), fiyat.index.min() + pd.Timedelta(hours=pencere))
    satir = []
    # Ortak takvim: bütün semboller aynı karar anlarında (TAKVIM), yalnız verisi başlamışsa.
    for t in TAKVIM[bas <= TAKVIM]:
        gecmis = fiyat["c"].asof(t - pd.Timedelta(hours=pencere))
        simdi = fiyat["c"].asof(t)
        giris = fiyat["o"].asof(t + pd.Timedelta(hours=1))
        cikis = fiyat["o"].asof(t + pd.Timedelta(hours=HAFTA + 1))
        if not all(np.isfinite([gecmis, simdi, giris, cikis])) or gecmis <= 0 or giris <= 0:
            continue
        f = fon[(fon.index > t + pd.Timedelta(hours=1))
                & (fon.index <= t + pd.Timedelta(hours=HAFTA + 1))].sum()
        satir.append({"t": t, "sinyal": np.sign(np.log(simdi / gecmis)),
                      "r": cikis / giris - 1.0, "funding": float(f)})
    return pd.DataFrame(satir).set_index("t")


def portfoy(pencere: int) -> pd.DataFrame:
    """Haftalık portföy getirileri: long-only, long/short ve short bacağın katkısı."""
    parca = {s: sembol_haftalari(s, pencere) for s in SEMBOLLER}
    tarih = sorted(set().union(*(p.index for p in parca.values())))
    onceki_lo = {s: 0.0 for s in SEMBOLLER}
    onceki_ls = {s: 0.0 for s in SEMBOLLER}
    out = []
    for t in tarih:
        mevcut = [s for s in SEMBOLLER if t in parca[s].index]
        if not mevcut:
            continue
        w = 1.0 / len(mevcut)
        lo = ls = kisa = 0.0
        for s in mevcut:
            x = parca[s].loc[t]
            p_lo = 1.0 if x["sinyal"] > 0 else 0.0
            p_ls = 1.0 if x["sinyal"] > 0 else -1.0
            # Short perp: fiyat hareketinin tersi + funding (pozitif oranı short alır).
            getiri_ls = x["r"] if p_ls > 0 else (-x["r"] + x["funding"])
            lo += w * (p_lo * x["r"] - abs(p_lo - onceki_lo[s]) * MALIYET)
            ls += w * (getiri_ls - abs(p_ls - onceki_ls[s]) * MALIYET)
            if p_ls < 0:
                kisa += w * (getiri_ls - abs(p_ls - onceki_ls[s]) * MALIYET)
            onceki_lo[s], onceki_ls[s] = p_lo, p_ls
        out.append({"t": t, "long_only": lo, "long_short": ls, "short_bacak": kisa})
    return pd.DataFrame(out).set_index("t")


def _ozet(r: pd.Series) -> dict[str, float]:
    sh = r.mean() / r.std(ddof=1) * np.sqrt(52) if r.std(ddof=1) > 0 else 0.0
    egri = (1 + r).cumprod()
    son = float(egri.iloc[-1])
    yillik = son ** (52 / len(r)) - 1 if son > 0 else -1.0
    return {"sharpe": round(float(sh), 3), "yillik": round(float(yillik), 4),
            "max_dd": round(float((1 - egri / egri.cummax()).max()), 4)}


def main() -> int:
    sonuc: dict[str, object] = {"pencereler": {}, "is_sonu": str(IS_SONU)}
    kural_1 = kural_2 = 0
    for p in PENCERELER:
        df = portfoy(p)
        lo, ls, kisa = _ozet(df["long_only"]), _ozet(df["long_short"]), df["short_bacak"]
        yillar = {int(y): round(float(g.sum()), 4) for y, g in kisa.groupby(kisa.index.year)}
        k1 = ls["sharpe"] >= lo["sharpe"] + 0.30
        k2 = ls["sharpe"] >= 0.80
        kural_1 += k1
        kural_2 += k1 and k2
        sonuc["pencereler"][p] = {"hafta": len(df), "baslangic": str(df.index.min().date()),
                                  "long_only": lo, "long_short": ls,
                                  "short_bacak_yillik_toplam": yillar,
                                  "kural_1": bool(k1), "kural_2": bool(k2)}
        print(f"pencere {p:>4}: {len(df)} hafta  long-only Sh {lo['sharpe']:+.2f} "
              f"({lo['yillik']:+.1%}, DD {lo['max_dd']:.1%})  long/short Sh {ls['sharpe']:+.2f} "
              f"({ls['yillik']:+.1%}, DD {ls['max_dd']:.1%})  short bacak/yıl {yillar}")
    # Kural 3: short bacağın yıllık katkısı, dört pencerenin ortalamasıyla, ≥ 3 yılda pozitif.
    yil_ort: dict[int, float] = {}
    for v in sonuc["pencereler"].values():
        for y, x in v["short_bacak_yillik_toplam"].items():
            yil_ort.setdefault(y, []).append(x)  # type: ignore[arg-type]
    # Kural yazıldığı gibi: IS'in tam yılları 2020-2023 (2019 yalnız Eylül-Aralık, sayılmaz).
    pozitif_yil = sum(1 for y, xs in yil_ort.items() if 2020 <= y <= 2023 and np.mean(xs) > 0)
    k3 = pozitif_yil >= 3
    karar = kural_2 >= 3 and k3
    sonuc |= {"kural_1_pencere": kural_1, "kural_1_2_pencere": kural_2,
              "short_pozitif_yil": pozitif_yil, "kural_3": k3, "karar_vadeli_gerekceli": karar}
    print(f"kural 1+2: {kural_2}/4 pencere (≥3 gerekli) · kural 3: short bacak {pozitif_yil} yılda "
          f"pozitif (≥3 gerekli) → vadeli hesap gerekçesi: {'VAR' if karar else 'YOK'}")
    yol = KOK / "runs" / "vadeli_tavan.json"
    yol.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"yazıldı: {yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
