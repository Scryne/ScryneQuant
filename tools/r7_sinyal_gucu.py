"""R7(2) — K-068 ön koşulu: aday sinyallerin **in-sample** ileriye dönük sıralama gücü. (K-109)

    python tools/r7_sinyal_gucu.py

K-068: kıyas-üstü bir sinyal programı açılabilmesi için kaynak farkına **ek olarak** ölçütün kesitte
ileriye dönük getiri sırasıyla ölçülmüş ve sıfırdan ayrışan bir ilişkisi gerekir; ölçüm **yalnızca
in-sample** penceresinde (K-068 ek şartı) ve çekiliş sayılmaz (strateji koşmaz, parametre seçilmez).

Ölçülen: her haftalık dengeleme anında (kıyasın takvimi: 168 bar, ısınma sonrası) kıyasın aday
kümesindeki üyelerde sinyal ↔ sonraki 168 barlık kapanış getirisi **Spearman sıra korelasyonu**
(IC);
haftalar üstünden ortalama, t = ort/(sd/√n), pozitif hafta oranı, IS'in iki yarısında işaret.
Zaman serisi sinyaller için ayrıca işaret testi: sinyal > 0 üyelerinin ortalama ileri getirisi −
≤ 0 olanların (bilgi amaçlı; K-068'in ölçütü sıralama gücü, yani IC).

**Karar ölçütü (koşudan önce yazıldı):** |t| ≥ 2,0 **ve** iki IS yarısında aynı işaret → aday; aksi
hâlde o sinyal için program açılmaz. Hiçbiri sağlamazsa çekiliş harcanmaz (FAIL, K-068 aynen).

Yalnız in-sample: OOS barlarına (≥ 55.678) hiçbir şekilde bakılmaz — dizi orada kesilir.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.features.motor import OzellikTanimi
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research import evren_kosu
from scryne_quant.strategy.kosu import evren_gorunum_kur
from scryne_quant.strategy.kutuphane import EvrenEsitAgirlik

KOK = Path(__file__).resolve().parent.parent
TABLO = KOK / "data" / "evren" / "_evren" / "27b7a16ed0ed.parquet"
DEPO = KOK / "data" / "evren"
CIKTI = KOK / "runs" / "faz12" / "r7-sinyal-gucu.json"
HAFTA = 168
ILERI = 168
T_ESIGI = 2.0

#: Aday sinyaller (fiyat/hacim geçmişinden; funding yok, K-068).
PENCERELER_MOM = (168, 336, 720, 1440)
PENCERELER_TERS = (24, 72, 168)
PENCERELER_SAPMA = (168, 720)
#: Faz 12 `kesitsel_dusuk_oynaklik` ızgarasının pencereleri (ölçülen sinyal ızgaradaki olmalı).
PENCERELER_OYNAKLIK = (168, 336, 720, 1440)


class _Olcum(EvrenEsitAgirlik):
    def ozellikler(self):
        return (
            *super().ozellikler(),
            *[OzellikTanimi(f"roc_{p}", "roc", {"pencere": p}) for p in
              sorted(set(PENCERELER_MOM) | set(PENCERELER_TERS))],
            *[OzellikTanimi(f"sma_{p}", "sma", {"pencere": p}) for p in PENCERELER_SAPMA],
            OzellikTanimi("hacim_24", "kote_hacim_sma", {"pencere": 24}),
            *[OzellikTanimi(f"atr_{p}", "atr", {"pencere": p}) for p in PENCERELER_OYNAKLIK],
        )


def _sira(x: np.ndarray) -> np.ndarray:
    """Ortalama-sıra (bağlarda ortalama)."""
    sirali = np.argsort(x, kind="mergesort")
    r = np.empty(len(x), dtype=np.float64)
    r[sirali] = np.arange(1, len(x) + 1, dtype=np.float64)
    # bağ düzeltmesi
    degerler, ters, sayim = np.unique(x, return_inverse=True, return_counts=True)
    if (sayim > 1).any():
        toplam = np.zeros(len(degerler))
        np.add.at(toplam, ters, r)
        r = (toplam / sayim)[ters]
    return r


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman ρ = sıraların Pearson korelasyonu (scipy bağımlılığı yok)."""
    rx, ry = _sira(x), _sira(y)
    sx, sy = rx.std(), ry.std()
    if not (sx > 0 and sy > 0):
        return float("nan")
    return float(((rx - rx.mean()) * (ry - ry.mean())).mean() / (sx * sy))


def main() -> int:
    veri = evren_kosu.veri_kur(TABLO, depo_kok=DEPO, azami_sembol=600)
    ins, _, _, _ = ed.pencereler(veri)
    son = ins.bitis  # OOS'a bakılmaz: ileri getiri de bu sınırı aşamaz
    s = _Olcum(yeniden_dengele_bar=HAFTA, azami_enstruman=10, azami_agirlik=0.02, hedef_brut=0.2)
    g = evren_gorunum_kur(veri.timeframe, veri.diziler, veri.uyelik, s,
                          kural_kimligi=veri.kural_kimligi)
    ilk = max(1440, s.isinma_bar()) + 2
    anlar = [i for i in range(ins.baslangic + ilk, son - ILERI, HAFTA)]
    semboller = sorted(g.gorunumler)

    def sinyaller(i: int) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for sm in semboller:
            if not veri.uyelik[sm][i]:
                continue
            pg = g.gorunumler[sm]
            c = pg.barlar["close"][i]
            a = pg.ozellikler["atr"][i]
            h = pg.ozellikler["kote_hacim"][i]
            if not (c > 0 and np.isfinite(a) and a > 0 and np.isfinite(h) and h > 0):
                continue
            c_ileri = pg.barlar["close"][i + ILERI]
            if not (np.isfinite(c_ileri) and c_ileri > 0):
                continue
            d: dict[str, float] = {"ileri": float(np.log(c_ileri / c))}
            for p in PENCERELER_MOM:
                d[f"ts_mom_{p}"] = float(pg.ozellikler[f"roc_{p}"][i])
            for p in PENCERELER_TERS:
                d[f"ts_ters_{p}"] = -float(pg.ozellikler[f"roc_{p}"][i])
            for p in PENCERELER_SAPMA:
                d[f"sapma_{p}"] = -float((c - pg.ozellikler[f"sma_{p}"][i]) / a)
            h24 = pg.ozellikler["hacim_24"][i]
            d["hacim_soku"] = float(h24 / h) if np.isfinite(h24) and h > 0 else float("nan")
            d["dusuk_oynaklik"] = -float(a / c)
            for p in PENCERELER_OYNAKLIK:
                d[f"dusuk_oynaklik_{p}"] = -float(pg.ozellikler[f"atr_{p}"][i] / c)
            out[sm] = d
        return out

    adlar = ([f"ts_mom_{p}" for p in PENCERELER_MOM] + [f"ts_ters_{p}" for p in PENCERELER_TERS]
             + [f"sapma_{p}" for p in PENCERELER_SAPMA] + ["hacim_soku", "dusuk_oynaklik"]
             + [f"dusuk_oynaklik_{p}" for p in PENCERELER_OYNAKLIK])
    ic: dict[str, list[float]] = {a: [] for a in adlar}
    isaret: dict[str, list[float]] = {a: [] for a in adlar if a.startswith("ts_")}
    uye_sayilari = []
    for i in anlar:
        sn = sinyaller(i)
        if len(sn) < 8:
            continue
        uye_sayilari.append(len(sn))
        ileri = np.array([d["ileri"] for d in sn.values()])
        for a in adlar:
            x = np.array([d[a] for d in sn.values()])
            m = np.isfinite(x)
            if m.sum() < 8:
                continue
            r = spearman(x[m], ileri[m])
            if np.isfinite(r):
                ic[a].append(float(r))
            if a in isaret:
                poz, neg = ileri[m & (x > 0)], ileri[m & (x <= 0)]
                if len(poz) >= 3 and len(neg) >= 3:
                    isaret[a].append(float(poz.mean() - neg.mean()))

    def ozet(dizi: list[float]) -> dict:
        v = np.array(dizi)
        n = len(v)
        if n < 4:
            return {"n": n}
        yarim = n // 2
        t = float(v.mean() / (v.std(ddof=1) / np.sqrt(n)))
        return {
            "n": n, "ort": float(v.mean()), "sd": float(v.std(ddof=1)), "t": t,
            "pozitif_oran": float((v > 0).mean()),
            "yari_1": float(v[:yarim].mean()), "yari_2": float(v[yarim:].mean()),
            "ayni_isaret": bool(np.sign(v[:yarim].mean()) == np.sign(v[yarim:].mean())),
            "aday": bool(abs(t) >= T_ESIGI
                         and np.sign(v[:yarim].mean()) == np.sign(v[yarim:].mean())),
        }

    sonuc = {
        "pencere": {"in_sample": [ins.baslangic, ins.bitis], "oos_bakilmadi": True,
                    "dengeleme_sayisi": len(uye_sayilari), "ort_uye": float(np.mean(uye_sayilari)),
                    "ileri_bar": ILERI, "hafta_bar": HAFTA},
        "olcut": {"t_esigi": T_ESIGI,
                  "kural": "IC: |t| >= 2,0 ve IS iki yarisinda ayni isaret -> aday"},
        "ic": {a: ozet(ic[a]) for a in adlar},
        "isaret_testi_ts": {a: ozet(isaret[a]) for a in isaret},
        "zaman_utc": utc_str(simdi_ms()),
    }
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
    for a in adlar:
        o = sonuc["ic"][a]
        nan = float("nan")
        print(f"{a:20s} n={o.get('n'):3d} IC={o.get('ort', nan):+.4f} t={o.get('t', nan):+.2f} "
              f"poz={o.get('pozitif_oran', nan):.2f} yarı=({o.get('yari_1', nan):+.3f},"
              f"{o.get('yari_2', nan):+.3f}) aday={o.get('aday')}")
    for a, o in sonuc["isaret_testi_ts"].items():
        print(f"işaret {a:12s} n={o.get('n'):3d} fark={o.get('ort', float('nan')):+.4f} "
              f"t={o.get('t', float('nan')):+.2f} aday={o.get('aday')}")
    print(f"yazıldı: {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
