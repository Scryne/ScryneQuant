"""Konumlanma verisinin (`metrics`) kaynak ölçüsü — K-045'in istisna şartı. (Faz 16, K-051/2)

    uv run python tools/faz16_kaynak_olcumu.py

**Soru:** Açık pozisyon, büyük hesapların long/short dengesi ve taker akışı; Faz 12'nin
kapattığı kaynakların (fiyat kesiti, funding, basis) **göremediği** bir şey ölçüyor mu?

Funding kalabalığın *fiyatını* ölçüyordu, basis vadeli talebi. Bunlar kalabalığın *miktarı*
(açık pozisyon) ve *bileşimi* (kimin hangi yönde, hangi büyüklükte). Yakın akraba olmaları
işin püf noktası: ölçü, "farklı bir isim" ile "farklı bir bilgi"yi ayırmak için var.

## Bu araç bir çekiliş değildir

**İleriye dönük hiçbir getiriye bakmaz** (K-039). Bütün istatistikler eşzamanlı ya da
geriye dönük: bağımsızlık R²'si, kesit sapması, eşzamanlı sıra korelasyonu, temel bileşen
payı, kapsama. Gelecek getiriyle ilişki arayan her şey program kaydından sonra, bütçeden
düşerek koşar. Farklı olmak **değerli** olmak değildir; bu ölçü yalnızca K-045'in
istisnasını sayıya bağlar.

## Kurallar

- Evren üyeliği PIT tablosundan, ay ay (K-052/3).
- Günlük konumlanma değeri = o günün **son** 5 dakikalık gözlemi (UTC 23:55); gün içi
  ortalama değil, çünkü çekilişte de bar kapanışında bilinen değer kullanılacak.
- `available_time = create_time + 5 dk` (dilim kapanmadan bilinemez, K-052/15). Günlük
  değer bu yüzden ertesi günün ilk barından itibaren "bilinen" sayılır; ölçüde gün
  hizalaması buna göre yapılır.
- Kimlik kırılması şüpheli sembol-aylar dışarıda (katalog).
- Eksik gün uydurulmaz; oranı boş (`""`) gelen satır NaN kalır.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from scryne_quant.common.hash import git_durumu
from scryne_quant.common.zaman import simdi_ms, utc_str

KOK = Path(__file__).resolve().parent.parent
EVREN = KOK / "data" / "evren"
TABLO = EVREN / "_evren" / "27b7a16ed0ed.parquet"
TABLO_OZET = EVREN / "_evren" / "27b7a16ed0ed.json"
FUNDING = KOK / "data" / "turev" / "funding"
METRICS = KOK / "data" / "turev" / "metrics"
CIKTI = KOK / "runs" / "faz16" / "kaynak-olcumu-konumlanma.json"

GUN_MS = 86_400_000
SAAT_MS = 3_600_000
ASGARI_GUN = 15
ASGARI_UYE = 10
BTC = "BTCUSDT"
#: Günün konumlanma gözlemi: 23:55 dilimi (gün kapanışında bilinen son değer).
GUN_SONU_MS = 23 * SAAT_MS + 55 * 60_000
ALANLAR = ("sum_open_interest_value", "count_toptrader_long_short_ratio",
           "sum_toptrader_long_short_ratio", "count_long_short_ratio",
           "sum_taker_long_short_vol_ratio")


def _yuzdelik(x) -> dict[str, float | int]:
    a = np.asarray(list(x), dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0}
    return {"n": int(a.size), "p10": float(np.percentile(a, 10)),
            "p25": float(np.percentile(a, 25)), "medyan": float(np.median(a)),
            "p75": float(np.percentile(a, 75)), "p90": float(np.percentile(a, 90))}


def _r2(y: np.ndarray, x: np.ndarray) -> float:
    if y.std() == 0 or x.std() == 0:
        return float("nan")
    return float(np.corrcoef(y, x)[0, 1] ** 2)


def _gunluk_kapanis(sembol: str) -> pd.Series | None:
    yol = EVREN / sembol / "1h.parquet"
    if not yol.is_file():
        return None
    df = pd.read_parquet(yol, columns=["open_time", "close", "quality_status"])
    df = df[(df["quality_status"] == "ok") & (df["open_time"] % GUN_MS == 23 * SAAT_MS)]
    if df.empty:
        return None
    return pd.Series(np.log(df["close"].to_numpy()), index=(df["open_time"] // GUN_MS).to_numpy())


def _gunluk_getiri(kapanis: pd.Series) -> pd.Series:
    fark = kapanis.diff()
    ardisik = pd.Series(kapanis.index, index=kapanis.index).diff() == 1
    return fark[ardisik]


def _gunluk_funding(sembol: str) -> pd.Series | None:
    yol = FUNDING / f"{sembol}.parquet"
    if not yol.is_file():
        return None
    df = pd.read_parquet(yol)
    return df.groupby(df["calc_time"] // GUN_MS)["last_funding_rate"].sum()


def _gunluk_konumlanma(sembol: str) -> pd.DataFrame | None:
    """Gün sonu (23:55) gözlemleri, gün indeksiyle."""
    yol = METRICS / f"{sembol}.parquet"
    if not yol.is_file():
        return None
    df = pd.read_parquet(yol)
    gun_ici = df["create_time"] % GUN_MS
    son = df[gun_ici == GUN_SONU_MS].copy()
    if son.empty:
        return None
    son.index = (son["create_time"] // GUN_MS).to_numpy()
    return son[list(ALANLAR)]


def _kirik_aylar() -> set[tuple[str, str]]:
    ozet = json.loads(TABLO_OZET.read_text(encoding="utf-8"))
    kirik = set()
    for k in ozet.get("kirilmalar", []):
        for ms in (k["onceki_son_ms"], k["sonraki_ilk_ms"]):
            kirik.add((k["sembol"], pd.Timestamp(ms, unit="ms", tz="UTC").strftime("%Y-%m")))
    return kirik


def _ay_gunleri(ay: str) -> tuple[int, int]:
    bas = pd.Timestamp(f"{ay}-01", tz="UTC")
    son = bas + pd.offsets.MonthBegin(1)
    return int(bas.value // 10**6 // GUN_MS), int(son.value // 10**6 // GUN_MS)


def kapsama(uyelik: pd.DataFrame, konum: dict[str, pd.DataFrame], kirik: set) -> dict:
    """Üye-ay başına veri var mı, günlerin kaçında gün sonu gözlemi var, oran sütunları ne
    kadar boş."""
    uye_ay = kapsanan = 0
    gun_orani, bos_oran = [], {a: [] for a in ALANLAR}
    for ay, grup in uyelik.groupby("ay"):
        bas, son = _ay_gunleri(str(ay))
        for s in grup["sembol"]:
            if (s, ay) in kirik:
                continue
            uye_ay += 1
            k = konum.get(s)
            if k is None:
                continue
            pencere = k[(k.index >= bas) & (k.index < son)]
            if pencere.empty:
                continue
            kapsanan += 1
            gun_orani.append(len(pencere) / (son - bas))
            for a in ALANLAR:
                bos_oran[a].append(float(pencere[a].isna().mean()))
    return {
        "uye_ay": uye_ay,
        "veri_olan_uye_ay_orani": kapsanan / uye_ay if uye_ay else None,
        "ay_ici_gun_kapsamasi": _yuzdelik(gun_orani),
        "bos_deger_orani": {a: _yuzdelik(v) for a, v in bos_oran.items()},
    }


def bagimsizlik(uyelik: pd.DataFrame, konum: dict[str, pd.DataFrame],
                getiriler: dict[str, pd.Series], fundingler: dict[str, pd.Series],
                kirik: set) -> dict:
    """Konumlanma değişimi, aynı günün getirisi ve funding'i ile ne kadar açıklanıyor?

    `1 − R²` yüksekse: bu seri fiyat/funding'in yeniden ifadesi değil."""
    oi_getiri, oi_funding, tt_getiri, taker_getiri, oi_btc = [], [], [], [], []
    btc_oi = konum.get(BTC)
    btc_doi = (np.log(btc_oi["sum_open_interest_value"]).diff()
               if btc_oi is not None else pd.Series(dtype=float))
    for ay, grup in uyelik.groupby("ay"):
        bas, son = _ay_gunleri(str(ay))
        for s in grup["sembol"]:
            if (s, ay) in kirik or s not in konum or s not in getiriler:
                continue
            k = konum[s]
            k = k[(k.index >= bas) & (k.index < son)]
            if len(k) < ASGARI_GUN:
                continue
            doi = np.log(k["sum_open_interest_value"].replace(0, np.nan)).diff().dropna()
            g = getiriler[s]
            ortak = doi.index.intersection(g.index)
            if len(ortak) >= ASGARI_GUN:
                oi_getiri.append(1.0 - _r2(doi.loc[ortak].to_numpy(), g.loc[ortak].to_numpy()))
                bo = btc_doi.reindex(ortak).dropna() if len(btc_doi) else pd.Series(dtype=float)
                if len(bo) >= ASGARI_GUN and s != BTC:
                    oi_btc.append(1.0 - _r2(doi.loc[bo.index].to_numpy(), bo.to_numpy()))
                for alan, kutu in (("sum_toptrader_long_short_ratio", tt_getiri),
                                   ("sum_taker_long_short_vol_ratio", taker_getiri)):
                    seri = k[alan].dropna()
                    o2 = seri.index.intersection(g.index)
                    if len(o2) >= ASGARI_GUN:
                        kutu.append(1.0 - _r2(seri.loc[o2].to_numpy(), g.loc[o2].to_numpy()))
            f = fundingler.get(s)
            if f is not None:
                o3 = doi.index.intersection(f.index)
                if len(o3) >= ASGARI_GUN:
                    oi_funding.append(1.0 - _r2(doi.loc[o3].to_numpy(), f.loc[o3].to_numpy()))
    return {
        "soru": "Konumlanma serileri aynı günün getirisi/funding'i ile açıklanıyor mu",
        "acik_pozisyon_degisimi_vs_getiri_1_eksi_r2": _yuzdelik(oi_getiri),
        "acik_pozisyon_degisimi_vs_funding_1_eksi_r2": _yuzdelik(oi_funding),
        "acik_pozisyon_degisimi_vs_btc_oi_1_eksi_r2": _yuzdelik(oi_btc),
        "buyuk_hesap_long_short_vs_getiri_1_eksi_r2": _yuzdelik(tt_getiri),
        "taker_akisi_vs_getiri_1_eksi_r2": _yuzdelik(taker_getiri),
    }


def kesit(uyelik: pd.DataFrame, konum: dict[str, pd.DataFrame],
          getiriler: dict[str, pd.Series], fundingler: dict[str, pd.Series],
          kirik: set) -> dict:
    """Konumlanma kesiti, mevcut kesitlerle aynı sıralamayı mı veriyor? (eşzamanlı/geriye)"""
    sonuc: dict[str, list[float]] = {"oi_degisimi_vs_7g_getiri": [], "oi_degisimi_vs_funding": [],
                                     "buyuk_hesap_vs_funding": [], "taker_vs_7g_getiri": [],
                                     "pc1_payi": []}
    for ay, grup in uyelik.groupby("ay"):
        bas, son = _ay_gunleri(str(ay))
        uyeler = [s for s in grup["sembol"] if (s, ay) not in kirik and s in konum]
        if len(uyeler) < ASGARI_UYE:
            continue
        doi = pd.DataFrame({s: np.log(konum[s]["sum_open_interest_value"].replace(0, np.nan)
                                      ).diff() for s in uyeler})
        doi = doi[(doi.index >= bas) & (doi.index < son)]
        tt = pd.DataFrame({s: konum[s]["sum_toptrader_long_short_ratio"] for s in uyeler})
        tt = tt[(tt.index >= bas) & (tt.index < son)]
        taker = pd.DataFrame({s: konum[s]["sum_taker_long_short_vol_ratio"] for s in uyeler})
        taker = taker[(taker.index >= bas) & (taker.index < son)]
        gp = pd.DataFrame({s: getiriler[s] for s in uyeler if s in getiriler})
        if gp.shape[1] >= ASGARI_UYE:
            gp = gp.reindex(range(bas - 7, son)).rolling(7, min_periods=7).sum()
        fp = pd.DataFrame({s: fundingler[s] for s in uyeler if s in fundingler})
        fp = fp[(fp.index >= bas) & (fp.index < son)] if fp.shape[1] else fp

        def sira(a: pd.DataFrame, b: pd.DataFrame, kutu: str) -> None:
            if a.empty or b.empty:
                return
            for d in a.index:
                if d not in b.index:
                    continue
                ikili = pd.concat([a.loc[d], b.loc[d]], axis=1, keys=["a", "b"]).dropna()
                if len(ikili) >= ASGARI_UYE:
                    sonuc[kutu].append(float(ikili["a"].rank().corr(ikili["b"].rank())))

        sira(doi, gp, "oi_degisimi_vs_7g_getiri")
        sira(doi, fp, "oi_degisimi_vs_funding")
        sira(tt, fp, "buyuk_hesap_vs_funding")
        sira(taker, gp, "taker_vs_7g_getiri")
        tam = doi.dropna(axis=1, thresh=len(doi) - 1).dropna(axis=0)
        if tam.shape[1] >= ASGARI_UYE and len(tam) >= ASGARI_GUN:
            x = (tam - tam.mean()) / tam.std(ddof=1).replace(0, np.nan)
            x = x.dropna(axis=1)
            if x.shape[1] >= ASGARI_UYE:
                ozdeger = np.linalg.eigvalsh(np.cov(x.to_numpy(), rowvar=False))
                sonuc["pc1_payi"].append(float(ozdeger[-1] / ozdeger.sum()))
    return {
        "soru": "Konumlanma kesiti mevcut kesitlerle aynı sıralamayı mı veriyor (eşzamanlı)",
        **{k: _yuzdelik(v) for k, v in sonuc.items()},
    }


def main() -> int:
    tablo = pd.read_parquet(TABLO)
    kirik = _kirik_aylar()
    semboller = sorted(set(tablo["sembol"].astype(str)))
    konum = {s: k for s in semboller if (k := _gunluk_konumlanma(s)) is not None}
    if len(konum) < ASGARI_UYE:
        raise SystemExit(f"konumlanma verisi yetersiz ({len(konum)} sembol) — önce indirici")
    ilgili = sorted(konum)
    getiriler = {s: _gunluk_getiri(k) for s in ilgili if (k := _gunluk_kapanis(s)) is not None}
    fundingler = {s: f for s in ilgili if (f := _gunluk_funding(s)) is not None}
    # Ölçüm yalnızca verinin olduğu aylara bakar; kapsama ayrıca raporlanıyor.
    uyelik = tablo[tablo["sembol"].isin(set(ilgili))][["ay", "sembol"]]

    govde = {
        "uretildi": utc_str(simdi_ms()),
        "kaynak": "data.binance.vision futures/um/daily/metrics",
        "evren_tablosu": str(TABLO),
        "sembol_sayisi": len(konum),
        "funding_olan": len(fundingler),
        "kapsama": kapsama(uyelik, konum, kirik),
        "bagimsizlik": bagimsizlik(uyelik, konum, getiriler, fundingler, kirik),
        "kesit": kesit(uyelik, konum, getiriler, fundingler, kirik),
        "not": ("İleriye dönük getiriye bakılmadı; bütün istatistikler eşzamanlı ya da "
                "geriye dönük (K-039). Farklı olmak değerli olmak değildir."),
        "git": git_durumu(),
    }
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text(json.dumps(govde, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                     encoding="utf-8")
    print(json.dumps({k: v for k, v in govde.items() if k != "git"}, ensure_ascii=False,
                     indent=2)[:4000])
    print(f"\nrapor: {CIKTI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
