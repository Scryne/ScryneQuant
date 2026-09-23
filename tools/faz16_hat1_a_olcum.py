"""Hat 1 / ikinci tavan — A listesi: mevcut veriyle hesaplanabilen girdiler. Ölçüm; karar yok.

`docs/arsiv/Faz-16-Hat1-Ikinci-Tavan-Tasarimi.md` §A'nın sekiz kalemini, oradaki tanımlarla,
yalnız depodaki veriden ve deterministik olarak çıkarır. İkinci tavanı **hesaplamaz**;
CLOSE/ELIGIBLE demez; H/δ/L ızgaralarından seçim yapmaz; perp maliyeti, benchmark, likidasyon
modeli, marjin tipi, stres parametresi üretmez.

Kalemler ve dayandıkları repo tanımları:
 1. Funding koşu yapısı — `data/funding.py` ödeme olayı; ardışık aynı-işaretli ödeme koşuları.
 2. Taban/talep ayrışması — taban = sembolün funding serisinin **modu** (veriden ölçülür;
    8h sembollerde 0,0001, 4h'te 0,00005); talep = oran − taban.
 3. Basis aleyhte hareket — `evren_premium_dizisi` tanımı (premium 1h `close`); short perp
    için aleyhte yön basis **artışı**; w ∈ {1, 7, 30} gün değişimi dağılımı.
 4. Yüksek-vol alt örneği — `risk/kalibrasyon.volatilite_olc` tanımı: ATR(14)/close (1h);
    eşikler `config/risk.json::volatilite_esigi` (p99, BTC'de kalibre) ve aynı kayıttaki
    p90/p95. Yeni rejim tanımı yok; eşik BTC'de kalibre ve öyle raporlanır.
 5. MFE fiyat girdisi — `jev/sonuc.py` tanımı: giriş `open[i+1]` (K-004), pencere içinde
    `max(high)/giriş − 1`; short perp için likidasyon yönü. **Yalnız ölçüm girdisi**;
    geleceği kullanır (pencere ileri bakar) ve hiçbir seçim/filtre üretmez.
 6. Spot maliyet + dengeleme — `config/maliyet.json` (K-007 taker 10 bps iki yön; K-021
    slippage 5,30 bps yalnız BTC'de kalibre); dengeleme: eşit **miktar** hedge'inde bacak
    notional farkı = |basis|; δ ∈ {%1, %2, %5} aşım sayısı ve düzeltme maliyeti.
 7. PIT kesişimi — `data/evren/_evren/27b7a16ed0ed.parquet` aylık PIT tablosu (K-052); her
    IS ayı için sembol o ay ilk 50'de miydi.
 8. r_cap ızgarası — r_cap = r_pos / (1 + m + b), m = 1/L, L ∈ {1, 2, 3, 5}, b ∈ {0, m};
    r_pos Adım 0'ın ideal yıllık pozisyon getirisi. GRID; seçim yok.

Pencere: in-sample, veri başı → 2025-02-16 18:00 UTC (BTC tek-sembol OOS başlangıcı, dahil
değil). Semboller: Adım 0'ın 28'i (funding + premium'u olan).

Kullanım: uv run python tools/faz16_hat1_a_olcum.py
Çıktı:    runs/faz16/hat1_a_olcum.json  (+ stdout özet)
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from scryne_quant.common.hash import dosya_hash
from scryne_quant.features.indikator import atr as atr_hesapla
from scryne_quant.risk.kalibrasyon import ATR_PENCERESI

IS_BITIS_MS = 1739728800000
SAAT_MS = 3_600_000
GUN_MS = 86_400_000
BASIS_PENCERE_GUN = (1, 7, 30)
MFE_PENCERE_BAR = (24, 168, 720, 2160)  # 1, 7, 30, 90 gün — tasarım §5 tutma ızgarası
DELTA_IZGARA = (0.01, 0.02, 0.05)
L_IZGARA = (1, 2, 3, 5)
H_IZGARA_GUN = (30, 90, 365)


def _yil(ms: np.ndarray) -> np.ndarray:
    return pd.to_datetime(ms, unit="ms", utc=True).year.to_numpy()


def _q(x: np.ndarray, qs=(50, 90, 99)) -> dict:
    x = x[~np.isnan(x)]
    if x.size == 0:
        return {"n": 0}
    d = {"n": int(x.size), **{f"p{q}": float(np.percentile(x, q)) for q in qs}, "max": float(x.max()), "min": float(x.min()), "ort": float(x.mean())}
    return d


def _funding(sembol: str, depo: Path):
    f = pd.read_parquet(depo / f"{sembol}.parquet")
    f = f[f["funding_time"] < IS_BITIS_MS].sort_values("funding_time").reset_index(drop=True)
    return f


def _premium(sembol: str, depo: Path):
    p = pd.read_parquet(depo / f"{sembol}.parquet", columns=["open_time", "close"])
    return p[p["open_time"] + SAAT_MS <= IS_BITIS_MS].sort_values("open_time").reset_index(drop=True)


def _barlar(sembol: str, depo: Path):
    b = pd.read_parquet(depo / sembol / "1h.parquet", columns=["open_time", "open", "high", "low", "close", "quality_status"])
    return b[b["open_time"] < IS_BITIS_MS].sort_values("open_time").reset_index(drop=True)


# ---------------------------------------------------------------- 1 + 2: funding
def kalem_1_2(f: pd.DataFrame) -> tuple[dict, dict]:
    oran = f["funding_rate"].to_numpy()
    ms = f["funding_time"].to_numpy()
    taban = float(pd.Series(oran).mode().iloc[0])
    taban_payi = float(np.isclose(oran, taban).mean())
    periyot_h = float(np.median(np.diff(ms)) / SAAT_MS) if len(ms) > 1 else None
    odeme_yil = 365 * 24 / periyot_h if periyot_h else None
    yil = _yil(ms)
    isaret = np.sign(oran)

    # koşular
    kosular = []
    i = 0
    while i < len(oran):
        j = i
        while j + 1 < len(oran) and isaret[j + 1] == isaret[i]:
            j += 1
        kosular.append({"isaret": int(isaret[i]), "bas_ms": int(ms[i]), "odeme": j - i + 1, "toplam": float(oran[i:j + 1].sum())})
        i = j + 1
    neg = [k for k in kosular if k["isaret"] < 0]
    en_uzun = sorted(neg, key=lambda k: -k["odeme"])[:5]
    en_derin = sorted(neg, key=lambda k: k["toplam"])[:5]
    def _kosu_yaz(k):
        return {"baslangic_utc": datetime.fromtimestamp(k["bas_ms"] / 1000, UTC).strftime("%Y-%m-%d"), "odeme": k["odeme"], "gun": round(k["odeme"] * (periyot_h or 8) / 24, 1), "kumulatif_pct": round(k["toplam"] * 100, 3)}
    yillik = {}
    for y in np.unique(yil):
        m = yil == y
        neg_y = [k for k in neg if _yil(np.array([k["bas_ms"]]))[0] == y]
        yillik[int(y)] = {
            "odeme": int(m.sum()),
            "negatif_odeme_payi": float((oran[m] < 0).mean()),
            "negatif_kosu": len(neg_y),
            "en_uzun_negatif_kosu_odeme": max((k["odeme"] for k in neg_y), default=0),
            "en_derin_negatif_kosu_pct": round(min((k["toplam"] for k in neg_y), default=0.0) * 100, 3),
            "taban_payi": float(np.isclose(oran[m], taban).mean()),
            "taban_yillik_pct": float(taban * odeme_yil * 100) if odeme_yil else None,
            "talep_yillik_pct": float((oran[m] - taban).mean() * odeme_yil * 100) if odeme_yil else None,
            "toplam_yillik_pct": float(oran[m].mean() * odeme_yil * 100) if odeme_yil else None,
        }
    k1 = {
        "odeme": int(len(oran)), "periyot_saat": periyot_h,
        "kosu_sayisi": len(kosular), "negatif_kosu_sayisi": len(neg),
        "negatif_odeme_payi": float((oran < 0).mean()),
        "negatif_zaman_payi": float(sum(k["odeme"] for k in neg) / len(oran)),
        "en_uzun_negatif_kosular": [_kosu_yaz(k) for k in en_uzun],
        "en_derin_negatif_kosular": [_kosu_yaz(k) for k in en_derin],
        "negatif_kosu_uzunluk_dagilimi_odeme": _q(np.array([k["odeme"] for k in neg], dtype=float)) if neg else {"n": 0},
        "yillik": yillik,
    }
    k2 = {
        "taban_odeme_basina": taban, "taban_payi": taban_payi,
        "taban_yillik_pct": float(taban * odeme_yil * 100) if odeme_yil else None,
        "talep_yillik_pct": float((oran - taban).mean() * odeme_yil * 100) if odeme_yil else None,
        "toplam_yillik_pct": float(oran.mean() * odeme_yil * 100) if odeme_yil else None,
        "taban_sifir_senaryosu_yillik_pct": float((oran - taban).mean() * odeme_yil * 100) if odeme_yil else None,
        "talep_negatif_odeme_payi": float(((oran - taban) < 0).mean()),
    }
    return k1, k2


# ---------------------------------------------------------------- 3: basis
def kalem_3(p: pd.DataFrame) -> dict:
    b = pd.Series(p["close"].to_numpy(), index=(p["open_time"] + SAAT_MS).to_numpy())
    ms = b.index.to_numpy()
    yil = _yil(ms)
    out = {"bar": int(len(b)), "basis_dagilimi": _q(b.to_numpy(), (1, 50, 99)), "pencereler": {}, "yillik": {}}
    for w in BASIS_PENCERE_GUN:
        hedef = ms + w * GUN_MS
        ileri = b.reindex(hedef).to_numpy()
        d = ileri - b.to_numpy()  # pozitif = basis arttı = short perp aleyhine
        out["pencereler"][f"{w}g"] = {
            "aleyhte_degisim": _q(d, (50, 90, 99)),
            "aleyhte_1pct_ustu_payi": float(np.nanmean(d > 0.01)),
            "aleyhte_0_5pct_ustu_payi": float(np.nanmean(d > 0.005)),
        }
        # en kötü 3 olay (tarih)
        gecerli = ~np.isnan(d)
        sira = np.argsort(-np.where(gecerli, d, -np.inf))[:3]
        out["pencereler"][f"{w}g"]["en_kotu_3"] = [
            {"utc": datetime.fromtimestamp(int(ms[i]) / 1000, UTC).strftime("%Y-%m-%d %H:%M"), "degisim_pct": round(float(d[i]) * 100, 3)} for i in sira if gecerli[i]
        ]
    d7 = b.reindex(ms + 7 * GUN_MS).to_numpy() - b.to_numpy()
    for y in np.unique(yil):
        m = yil == y
        out["yillik"][int(y)] = {"basis_ort_pct": float(np.nanmean(b.to_numpy()[m]) * 100), "aleyhte_7g_p99_pct": float(np.nanpercentile(d7[m], 99) * 100) if np.isfinite(d7[m]).any() else None, "aleyhte_7g_max_pct": float(np.nanmax(d7[m]) * 100) if np.isfinite(d7[m]).any() else None}
    return out


# ---------------------------------------------------------------- 4 + 5: vol ve MFE
def kalem_4_5(barlar: pd.DataFrame, p: pd.DataFrame, f: pd.DataFrame, esikler: dict) -> tuple[dict, dict]:
    ok = barlar["quality_status"].to_numpy() == "ok"
    o, h, lo, c = (barlar[k].to_numpy(dtype=np.float64) for k in ("open", "high", "low", "close"))
    ms = barlar["open_time"].to_numpy()
    n = len(ms)
    atr_oran = atr_hesapla(h, lo, c, ATR_PENCERESI) / c

    # --- 5: MFE (jev/sonuc.py tanımı): giriş open[i+1], pencere w bar, max(high)/giriş − 1
    mfe = {}
    yil = _yil(ms)
    for w in MFE_PENCERE_BAR:
        if n <= w + 1:
            mfe[f"{w}bar"] = {"n": 0}
            continue
        giris = o[1:n - w]  # i = 0..n-w-2 → giriş open[i+1]
        # max high over [i+1, i+w]
        hv = np.lib.stride_tricks.sliding_window_view(h[1:], w).max(axis=1)[: len(giris)]
        # bar aralığı sürekli mi (boşluk → düş)
        surekli = (ms[1 + w - 1 : 1 + w - 1 + len(giris)] - ms[1 : 1 + len(giris)]) == (w - 1) * SAAT_MS
        x = np.where(surekli, hv / giris - 1.0, np.nan)
        rec = {"tanim": "max(high[i+1..i+w]) / open[i+1] − 1; short perp için aleyhte yön", **_q(x, (50, 90, 99))}
        rec["yillik_p99"] = {int(y): float(np.nanpercentile(x[yil[1:1 + len(x)] == y], 99)) for y in np.unique(yil) if np.isfinite(x[yil[1:1 + len(x)] == y]).any()}
        mfe[f"{w}bar"] = rec

    # --- 4: yüksek-vol alt örneği (ATR/close eşikleri BTC'de kalibre)
    gun = ms // GUN_MS
    b = pd.Series(p["close"].to_numpy(), index=(p["open_time"] + SAAT_MS).to_numpy())
    basis_bar = b.reindex(ms + SAAT_MS).to_numpy()
    d_basis_gun = pd.Series(basis_bar, index=gun).groupby(level=0).agg(lambda s: s.iloc[-1] - s.iloc[0] if s.notna().sum() > 1 else np.nan)
    ft = ((f["funding_time"] + SAAT_MS // 2) // SAAT_MS * SAAT_MS).to_numpy()
    f_gun = pd.Series(f["funding_rate"].to_numpy(), index=ft // GUN_MS).groupby(level=0).sum()
    mfe24 = np.full(n, np.nan)
    if n > 25:
        hv = np.lib.stride_tricks.sliding_window_view(h[1:], 24).max(axis=1)
        mfe24[: len(hv)] = hv / o[1 : 1 + len(hv)] - 1.0
    mfe24_gun = pd.Series(mfe24, index=gun).groupby(level=0).max()
    vol = {}
    for ad, esik in esikler.items():
        ust = pd.Series((atr_oran > esik) & ok, index=gun).groupby(level=0).any()
        yv, dv = ust[ust].index, ust[~ust].index
        def _blok(idx):
            return {
                "gun": int(len(idx)),
                "basis_gunluk_degisim_ort_pct": float(d_basis_gun.reindex(idx).mean() * 100) if len(idx) else None,
                "basis_gunluk_degisim_p99_pct": float(d_basis_gun.reindex(idx).quantile(0.99) * 100) if len(idx) else None,
                "funding_gunluk_ort_pct": float(f_gun.reindex(idx).mean() * 100) if len(idx) else None,
                "mfe24_gunluk_max_p90_pct": float(mfe24_gun.reindex(idx).quantile(0.9) * 100) if len(idx) else None,
            }
        vol[ad] = {"esik_atr_oran": esik, "bar_payi_ustu": float(((atr_oran > esik) & ok).sum() / max(ok.sum(), 1)), "yuksek_vol_gunleri": _blok(yv), "diger_gunler": _blok(dv)}
    vol["atr_oran_dagilimi_bu_sembol"] = _q(atr_oran[ok], (50, 90, 95, 99))
    return vol, mfe


# ---------------------------------------------------------------- 6: spot maliyet + dengeleme
def kalem_6(sembol: str, p: pd.DataFrame, maliyet: dict, r_pos_yillik: float | None) -> dict:
    fee = maliyet["fee_taker_bps"]
    slip = maliyet["slippage_bps"] if sembol == maliyet["kalibrasyon"]["sembol"] else None
    tek_yon = fee + (slip or 0.0)
    gd = 2 * tek_yon
    basis = p["close"].to_numpy()
    out = {
        "spot_tek_yon_bps": tek_yon, "spot_gidis_donus_bps": gd,
        "slippage_kalibre": slip is not None,
        "not": "yalnız spot bacak; perp komisyon/slippage repoda yok (B-1, B-2)",
        "acilis_kapanis_amortisman_yillik_pct": {f"H{H}g": float(gd / 10_000 * 365 / H * 100) for H in H_IZGARA_GUN},
        "dengeleme": {},
    }
    for d in DELTA_IZGARA:
        asim = np.abs(basis) > d
        out["dengeleme"][f"delta_{int(d * 100)}pct"] = {
            "notional_fark_esik_asim_payi_bar": float(asim.mean()),
            "asim_bar": int(asim.sum()),
            "duzeltme_maliyeti_bps_asim_basina": float(np.nanmean(np.abs(basis[asim])) * tek_yon) if asim.any() else 0.0,
            "not": "eşit miktar hedge'inde bacak notional farkı = |basis|; düzeltme = fark × spot tek yön maliyeti",
        }
    if r_pos_yillik is not None:
        out["ideal_r_pos_yillik_pct"] = r_pos_yillik
        out["spot_maliyet_sonrasi_yillik_pct"] = {f"H{H}g": float(r_pos_yillik - gd / 10_000 * 365 / H * 100) for H in H_IZGARA_GUN}
    return out


# ---------------------------------------------------------------- 7: PIT
def kalem_7(sembol: str, pit: pd.DataFrame, f: pd.DataFrame) -> dict:
    aylar = pd.to_datetime(f["funding_time"], unit="ms", utc=True).dt.strftime("%Y-%m").unique()
    uye = pit[(pit["sembol"] == sembol)]
    uye_aylar = set(uye["ay"])
    kesisim = [a for a in aylar if a in uye_aylar]
    return {
        "is_ay": int(len(aylar)), "pit_uye_ay": int(len(kesisim)),
        "pit_uye_payi": float(len(kesisim) / len(aylar)) if len(aylar) else None,
        "ilk_uye_ay": min(kesisim) if kesisim else None,
        "not": "PIT tablo 27b7a16ed0ed (ay, sıra ≤ 50); Adım 0 havuzu 2026-09 listesiydi — bu satır o sembolün IS boyunca kaç ay gerçekten evrende olduğunu verir",
    }


# ---------------------------------------------------------------- 8: r_cap ızgarası
def kalem_8(r_pos_yillik: float | None) -> dict:
    if r_pos_yillik is None:
        return {}
    grid = {}
    for L in L_IZGARA:
        m = 1.0 / L
        for b_ad, b in (("b0", 0.0), ("b_m", m)):
            grid[f"L{L}_{b_ad}"] = {"L": L, "m": m, "b": b, "sermaye_carpani": 1 + m + b, "r_cap_yillik_pct": float(r_pos_yillik / (1 + m + b))}
    return {"tanim": "r_cap = r_pos / (1 + m + b); r_pos ideal (Adım 0); Sharpe kaldıraçtan bağımsız, yalnız düzey değişir; GRID — seçim yok; likidasyon hariç (DATA BLOCKED)", "r_pos_yillik_pct": r_pos_yillik, "grid": grid}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adim0", default="runs/faz16/carry_tavan.json")
    ap.add_argument("--cikti", default="runs/faz16/hat1_a_olcum.json")
    a = ap.parse_args()
    kok = Path(".")
    adim0 = json.loads((kok / a.adim0).read_text(encoding="utf-8"))
    semboller = list(adim0["semboller"].keys())
    maliyet = json.loads((kok / "config/maliyet.json").read_text(encoding="utf-8"))
    risk = json.loads((kok / "config/risk.json").read_text(encoding="utf-8"))
    esik_p99 = risk["volatilite_esigi"]
    dag = risk["gerekceler"]["volatilite_esigi"]["dagilim"]
    esikler = {"p90": dag["p90"], "p95": dag["p95"], "p99_volatilite_esigi": esik_p99}
    pit = pd.read_parquet(kok / "data/evren/_evren/27b7a16ed0ed.parquet")

    veri = {
        "funding_depo": "data/funding", "premium_depo": "data/turev/premium", "bar_depo": "data/evren",
        "pit_tablo": {"yol": "data/evren/_evren/27b7a16ed0ed.parquet", "sha256": dosya_hash(kok / "data/evren/_evren/27b7a16ed0ed.parquet")},
        "maliyet": {"yol": "config/maliyet.json", "sha256": dosya_hash(kok / "config/maliyet.json")},
        "risk": {"yol": "config/risk.json", "sha256": dosya_hash(kok / "config/risk.json")},
        "adim0": {"yol": a.adim0, "sha256": dosya_hash(kok / a.adim0)},
        "semboller": {},
    }
    sonuc = {}
    for s in semboller:
        f = _funding(s, kok / "data/funding")
        p = _premium(s, kok / "data/turev/premium")
        barlar = _barlar(s, kok / "data/evren")
        veri["semboller"][s] = {"funding_sha256": dosya_hash(kok / "data/funding" / f"{s}.parquet"), "premium_sha256": dosya_hash(kok / "data/turev/premium" / f"{s}.parquet"), "bar_sha256": dosya_hash(kok / "data/evren" / s / "1h.parquet"), "bar_is": int(len(barlar)), "odeme_is": int(len(f))}
        r_pos = adim0["semboller"][s]["toplam"]["yillik_getiri_pct"]
        k1, k2 = kalem_1_2(f)
        if len(barlar) < ATR_PENCERESI + 30:
            k4 = {"DATA_BLOCKED": f"IS penceresinde spot 1h bar yok ya da yetersiz ({len(barlar)})"}
            k5 = {"DATA_BLOCKED": k4["DATA_BLOCKED"]}
        else:
            k4, k5 = kalem_4_5(barlar, p, f, esikler)
        sonuc[s] = {
            "1_funding_kosu": k1, "2_taban_talep": k2, "3_basis_aleyhte": kalem_3(p),
            "4_yuksek_vol": k4, "5_mfe": k5, "6_spot_maliyet_dengeleme": kalem_6(s, p, maliyet, r_pos),
            "7_pit": kalem_7(s, pit, f), "8_r_cap": kalem_8(r_pos),
        }

    cikti = {
        "olcum": "Hat 1 ikinci tavan — A listesi girdileri (8 kalem)",
        "tur": "ölçüm; ikinci tavan hesaplanmadı; seçim yok; karar yok",
        "uretim_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "is_bitis_utc": datetime.fromtimestamp(IS_BITIS_MS / 1000, UTC).isoformat(),
        "izgaralar": {"basis_pencere_gun": BASIS_PENCERE_GUN, "mfe_pencere_bar": MFE_PENCERE_BAR, "delta": DELTA_IZGARA, "L": L_IZGARA, "H_gun": H_IZGARA_GUN, "vol_esikleri": esikler},
        "veri": veri,
        "data_blocked": {
            "perp_komisyon_slippage": "repoda yok (tasarım B-1, B-2); kalem 6 yalnız spot",
            "likidasyon_sayaci": "mmr tablosu ve mark serisi yok (B-3, B-4); kalem 5 yalnız fiyat girdisi",
            "usdt_benchmark": "seri yok (B-5)",
            "spot_slippage_diger_semboller": "yalnız BTC kalibre (B-6); diğerlerinde tek yön = fee",
        },
        "semboller": sonuc,
    }
    yol = kok / a.cikti
    yol.parent.mkdir(parents=True, exist_ok=True)
    metin = json.dumps(cikti, ensure_ascii=False, indent=1, default=float)
    yol.write_text(metin, encoding="utf-8")
    # deterministik içerik hash'i (uretim_utc hariç)
    icerik = {k: v for k, v in cikti.items() if k != "uretim_utc"}
    print("icerik_sha256:", __import__("hashlib").sha256(json.dumps(icerik, ensure_ascii=False, sort_keys=True, default=float).encode()).hexdigest())

    # özet
    print(f"\n{'sembol':10} {'neg zaman':>9} {'en uzun neg (g)':>15} {'taban%':>7} {'talep%/y':>8} {'basis7g p99%':>12} {'MFE30g p99%':>11} {'PIT ay%':>7} {'r_cap L1':>8} {'r_cap L5':>8}")
    for s, r in sonuc.items():
        k1, k2, k3, k5, k7, k8 = r["1_funding_kosu"], r["2_taban_talep"], r["3_basis_aleyhte"], r["5_mfe"], r["7_pit"], r["8_r_cap"]
        uzun = k1["en_uzun_negatif_kosular"][0]["gun"] if k1["en_uzun_negatif_kosular"] else 0
        b7 = k3["pencereler"]["7g"]["aleyhte_degisim"].get("p99", float("nan")) * 100
        m30 = (k5.get("720bar", {}).get("p99") or float("nan")) * 100
        print(f"{s:10} {k1['negatif_zaman_payi']:>9.2f} {uzun:>15.1f} {k2['taban_payi']*100:>7.1f} {k2['talep_yillik_pct'] or float('nan'):>8.1f} {b7:>12.2f} {m30:>11.1f} {(k7['pit_uye_payi'] or 0)*100:>7.0f} {k8['grid']['L1_b0']['r_cap_yillik_pct'] if k8 else float('nan'):>8.1f} {k8['grid']['L5_b0']['r_cap_yillik_pct'] if k8 else float('nan'):>8.1f}")


if __name__ == "__main__":
    main()
