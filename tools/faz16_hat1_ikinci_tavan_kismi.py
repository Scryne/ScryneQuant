"""Hat 1 — ikinci tavanın **kısmi** hesabı: erişilebilen katmanlar + "eksik sınıf" (tasarım §9/§10).

Scryne kararı (2026-09-20): fee (`commissionRate`) ve MMR kademeleri (`leverageBracket`) BLOCKED
kalır (`enableFutures=false`, vadeli hesap açılmıyor). Bu betik bloke girdileri **aşmaz**:
alternatif uç yok, spot→perp taşıma yok, güncel MMR'yi geçmişe uygulama yok, varsayım yok.
Ürettiği her sayı ya bir **üst sınır** ya da bir **ara ölçüm**dür ve `gecici_maliyet_modeli`
mutlak engeli altındadır — resmi kapı sonucu değildir (metodoloji denetimi §1, §3).

Aşamalar (tasarım §9):
 (1) ideal: Adım 0 (`runs/faz16/carry_tavan.json`) — r_pos.
 (2) maliyet-düzeltilmiş ÜST SINIR `r_gross_ust_sinir_fee0`: r_pos − amortisman(H) −
     dengeleme; açılış/kapanış = 2·(fee_spot + slip_spot) + 2·(0 + slip_perp); fee_perp = 0
     (≥ 0 olduğundan üst sınır). δ-dengeleme A-6'da ihmal edilebilir ölçüldü (eklenmez, not).
     Ek: `basabas_fee_perp_bps(H)` — (3)'teki excess Sharpe'ı 1,04'e indiren perp fee.
 (3) fırsat-maliyetli ÜST SINIR: r_cap = r_gross / (1 + m + b) (L×b ızgarası), r_excess =
     r_cap − r_bey (DTB3, `data/makro.pit_gunluk`, K-060); excess Sharpe.
 (4) stres — yalnız erişilebilen sınıflar, her biri (2)'nin temel serisine ayrı uygulanır:
     funding_negatif_k (k∈{1,2}): yıllık − k·|en derin negatif koşu kümülatifi| (A-1)
     basis_aleyhte_w (w∈{1,7,30}): tek seferlik çıkış kaybı = pencere p99 aleyhte Δbasis (A-3),
         H'ye amortize
     yuksek_vol: yalnız yüksek-vol günleri (ATR/close > volatilite_esigi p99, A-4) alt örneği
         — koşullu yıllık getiri (senaryo değil, koşul; ayrı raporlanır, bozulmaya girmez)
     execution: STRES_SENARYOLARI slippage_2x/3x (spot+perp slip), fee_2x/hepsi_2x **KISMİ**
         (yalnız spot fee ×2; perp fee yok — açıkça etiketli)
     borsa_parametresi: taban 0 (talep bileşeni yalnız, A-2)
     erisim_kaybi_D (D∈{1,3,7}): zorunlu çıkışta D-gün azami aleyhte Δbasis (A-3 max), H'ye amortize
     likidasyon_esigi: **CLOSED / hesaplanamaz** (MMR yok) — satır boş, eksik sınıf
     `stres_bozulma` = temel − en kötü ölçülebilen senaryo (yıllık getiri, oran) —
     `research/analiz.StresSonucu.bozulma` tanımı; eksik sınıf nedeniyle **alt sınırdır**.
 Karar (§10): DATA BLOCKED — eksik katman (fee) ve eksik sınıf (likidasyon). CLOSE/ELIGIBLE yok.

Kullanım: uv run python tools/faz16_hat1_ikinci_tavan_kismi.py
Çıktı:    runs/faz16/hat1_ikinci_tavan_kismi.json
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from scryne_quant.common.hash import dosya_hash
from scryne_quant.data.makro import pit_gunluk
from scryne_quant.research.analiz import STRES_SENARYOLARI

KOK = Path(".")
IS_BITIS_MS = 1739728800000
ESIK = 1.04
H_IZGARA = (30, 90, 365)
L_IZGARA = (1, 2, 3, 5)
T_GUN = 91


def _b5():
    spec = importlib.util.spec_from_file_location("b5", KOK / "tools/faz16_hat1_b5_benchmark.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _sharpe(x: pd.Series) -> float | None:
    x = x.dropna()
    return float(x.mean() / x.std(ddof=1) * math.sqrt(365)) if len(x) >= 30 and x.std(ddof=1) > 0 else None


def main() -> None:
    b5 = _b5()
    adim0 = json.loads((KOK / "runs/faz16/carry_tavan.json").read_text(encoding="utf-8"))
    a_olc = json.loads((KOK / "runs/faz16/hat1_a_olcum.json").read_text(encoding="utf-8"))
    b1 = json.loads((KOK / "runs/faz16/hat1_b1_perp_slippage.json").read_text(encoding="utf-8"))
    maliyet = json.loads((KOK / "config/maliyet.json").read_text(encoding="utf-8"))
    fee_spot, slip_spot_btc = maliyet["fee_taker_bps"], maliyet["slippage_bps"]
    perp_slip = {s: b1["perp_is"][s]["deger_bps"] for s in ("BTCUSDT", "ETHUSDT")}

    semboller = list(adim0["semboller"].keys())
    seriler = {s: b5.carry_gunluk(s, KOK / "data/funding", KOK / "data/turev/premium") for s in semboller}
    seriler = {s: r for s, r in seriler.items() if r is not None}
    df = pd.DataFrame(seriler)
    havuz = df.mean(axis=1)

    # benchmark (B-5)
    vintage = pd.read_parquet(KOK / "data/makro/DTB3.parquet")
    gunler = np.arange(int(df.index.min()), int(df.index.max()) + 1, dtype="int64")
    d = pit_gunluk(vintage, gunler) / 100.0
    r_bey = pd.Series(365.0 * d / (360.0 - d * T_GUN) / 365.0, index=gunler)

    def maliyet_bps(sembol: str) -> dict:
        slip_s = slip_spot_btc if sembol == "BTCUSDT" else 0.0  # K-021: yalnız BTC kalibre; diğerleri fee-only (A-6)
        slip_p = perp_slip.get(sembol)  # yalnız BTC/ETH ölçüldü
        return {"fee_spot": fee_spot, "slip_spot": slip_s, "fee_perp": None, "slip_perp": slip_p}

    def asamalar(ad: str, r_pos: pd.Series, sembol_maliyet: dict | None) -> dict:
        out = {"ideal": {"r_pos_yillik_pct": float(r_pos.mean() * 365 * 100), "sharpe": _sharpe(r_pos)}}
        if sembol_maliyet is None or sembol_maliyet["slip_perp"] is None:
            out["maliyet_ust_sinir"] = {"DATA_BLOCKED": "perp slippage yalnız BTC/ETH'de ölçüldü; bu seri için (2)-(4) hesaplanmaz"}
            return out
        m = sembol_maliyet
        acilis_kapanis_bps = 2 * (m["fee_spot"] + m["slip_spot"]) + 2 * (0.0 + m["slip_perp"])
        out["maliyet_ust_sinir"] = {"etiket": "ARA — kapı dışı (gecici_maliyet_modeli); fee_perp = 0 üst sınır", "acilis_kapanis_bps_fee0": acilis_kapanis_bps, "H": {}}
        out["firsat_maliyeti_ust_sinir"] = {"etiket": "ARA — (2) üst sınırı üzerinden; kapı dışı", "H": {}}
        out["basabas_fee_perp_bps"] = {"etiket": "excess Sharpe = 1,04 yapan fee_perp (bps); gerçek fee bilinmiyor", "H": {}}
        out["stres"] = {"etiket": "yalnız erişilebilen sınıflar; likidasyon_esigi CLOSED; execution fee kalemi KISMİ", "H": {}}
        rb = r_bey.reindex(r_pos.index)
        for H in H_IZGARA:
            amort = acilis_kapanis_bps / 10_000 / H  # günlük eşdeğer
            r_gross = r_pos - amort
            out["maliyet_ust_sinir"]["H"][f"H{H}"] = {"r_gross_yillik_pct": float(r_gross.mean() * 365 * 100), "sharpe": _sharpe(r_gross)}
            grid, bb = {}, {}
            for L in L_IZGARA:
                mm = 1.0 / L
                for b_ad, b in (("b0", 0.0), ("b_m", mm)):
                    r_cap = r_gross / (1 + mm + b)
                    ex = (r_cap - rb).dropna()
                    grid[f"L{L}_{b_ad}"] = {"r_excess_yillik_pct": float(ex.mean() * 365 * 100), "excess_sharpe": _sharpe(ex)}
                    # başabaş fee: r_cap(fee) = (r_pos − (amort + 2·fee/1e4/H)) / (1+m+b); Sharpe lineer: bul fee s.t. Sharpe=ESIK
                    sd = ex.std(ddof=1)
                    hedef_mean = ESIK * sd / math.sqrt(365)
                    mevcut_mean = ex.mean()
                    # ex(fee) = ex(0) − 2·fee/1e4/H/(1+m+b) (sabit kaydırma; std değişmez)
                    fee = (mevcut_mean - hedef_mean) * (1 + mm + b) * H * 10_000 / 2
                    bb[f"L{L}_{b_ad}"] = float(fee)
            out["firsat_maliyeti_ust_sinir"]["H"][f"H{H}"] = grid
            out["basabas_fee_perp_bps"]["H"][f"H{H}"] = bb
            # --- stres (yıllık getiri, oran; (2) temel serisi üzerinden)
            temel = float(r_gross.mean() * 365)
            sen = {"temel": temel}
            derin = abs(a_olc["semboller"][ad]["1_funding_kosu"]["en_derin_negatif_kosular"][0]["kumulatif_pct"]) / 100 if a_olc["semboller"][ad]["1_funding_kosu"]["en_derin_negatif_kosular"] else 0.0
            for k in (1, 2):
                sen[f"funding_negatif_k{k}"] = temel - k * derin
            for w in (1, 7, 30):
                p99 = a_olc["semboller"][ad]["3_basis_aleyhte"]["pencereler"][f"{w}g"]["aleyhte_degisim"]["p99"]
                sen[f"basis_aleyhte_{w}g"] = temel - p99 * 365 / H
            for s_ad, c in STRES_SENARYOLARI.items():
                if s_ad == "temel":
                    continue
                bps = 2 * (m["fee_spot"] * c["fee"] + m["slip_spot"] * c["slippage"]) + 2 * (0.0 + m["slip_perp"] * c["slippage"])
                sen[f"execution_{s_ad}" + ("_KISMI" if c["fee"] != 1.0 else "")] = float((r_pos - bps / 10_000 / H).mean() * 365)
            taban_yillik = a_olc["semboller"][ad]["2_taban_talep"]["taban_yillik_pct"] / 100
            sen["borsa_taban0"] = temel - taban_yillik
            for D in (1, 3, 7):
                w = {1: "1g", 3: "7g", 7: "7g"}[D]  # 3 gün penceresi A-3'te yok → 7g maksimumu (muhafazakâr)
                mx = a_olc["semboller"][ad]["3_basis_aleyhte"]["pencereler"][w]["aleyhte_degisim"]["max"]
                sen[f"erisim_kaybi_D{D}" + ("_7g_maks" if D == 3 else "")] = temel - mx * 365 / H
            sen["likidasyon_esigi"] = None  # CLOSED
            olculen = {k: v for k, v in sen.items() if v is not None}
            en_kotu_ad = min(olculen, key=olculen.get)
            yv = a_olc["semboller"][ad]["4_yuksek_vol"].get("p99_volatilite_esigi", {})
            out["stres"]["H"][f"H{H}"] = {
                "senaryolar_yillik_oran": sen,
                "stres_bozulma_alt_sinir": temel - olculen[en_kotu_ad],
                "en_kotu_olculen": en_kotu_ad,
                "eksik_sinif": ["likidasyon_esigi (MMR yok)"],
                "kismi": ["execution_fee_2x_KISMI", "execution_hepsi_2x_KISMI"],
                "yuksek_vol_kosullu": {"gun": yv.get("yuksek_vol_gunleri", {}).get("gun"), "not": "koşullu alt örnek; A-4; senaryo değil"},
            }
        return out

    sonuc = {}
    for s in ("BTCUSDT", "ETHUSDT"):
        sonuc[s] = asamalar(s, seriler[s], maliyet_bps(s))
    # havuz: perp slippage yalnız BTC/ETH → havuz için (2)+ hesaplanamaz; ideal verilir
    sonuc["HAVUZ_28"] = {"ideal": {"r_pos_yillik_pct": float(havuz.mean() * 365 * 100), "sharpe": _sharpe(havuz)}, "maliyet_ust_sinir": {"DATA_BLOCKED": "perp slippage 26 sembolde ölçülmedi (B-6); havuz için (2)-(4) yok"}}

    cikti = {
        "olcum": "Hat 1 — ikinci tavan KISMİ: erişilebilen katmanlar + eksik sınıf (tasarım §9/§10)",
        "karar": "DATA BLOCKED — eksik katman: perp fee; eksik sınıf: likidasyon_esigi (MMR). CLOSE/ELIGIBLE verilmedi.",
        "etiket": "her sayı üst sınır ya da ara ölçüm; gecici_maliyet_modeli mutlak engeli; kapı dışı",
        "uretim_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "girdiler": {p: dosya_hash(KOK / p) for p in ("runs/faz16/carry_tavan.json", "runs/faz16/hat1_a_olcum.json", "runs/faz16/hat1_b1_perp_slippage.json", "config/maliyet.json", "data/makro/DTB3.parquet")},
        "maliyet_kalemleri_bps": {"fee_spot": fee_spot, "slip_spot_BTC": slip_spot_btc, "slip_spot_diger": "kalibre değil → 0 (A-6)", "fee_perp": "BLOCKED (=0 üst sınır)", "slip_perp": perp_slip},
        "izgaralar": {"H_gun": H_IZGARA, "L": L_IZGARA, "b": ["0", "m"]},
        "sonuc": sonuc,
    }
    yol = KOK / "runs/faz16/hat1_ikinci_tavan_kismi.json"
    yol.write_text(json.dumps(cikti, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    icerik = {k: v for k, v in cikti.items() if k != "uretim_utc"}
    print("icerik_sha256:", hashlib.sha256(json.dumps(icerik, ensure_ascii=False, sort_keys=True, default=float).encode()).hexdigest())
    for s in ("BTCUSDT", "ETHUSDT"):
        r = sonuc[s]
        print(f"\n== {s}  ideal {r['ideal']['r_pos_yillik_pct']:.2f} %/y S {r['ideal']['sharpe']:.2f}  | açılış+kapanış fee0 {r['maliyet_ust_sinir']['acilis_kapanis_bps_fee0']:.1f} bps")
        for H in H_IZGARA:
            g = r["maliyet_ust_sinir"]["H"][f"H{H}"]; e = r["firsat_maliyeti_ust_sinir"]["H"][f"H{H}"]; bb = r["basabas_fee_perp_bps"]["H"][f"H{H}"]; st = r["stres"]["H"][f"H{H}"]
            print(f"  H{H:>3}: r_gross_ust {g['r_gross_yillik_pct']:6.2f} S {g['sharpe']:.2f} | excess L1/b0 {e['L1_b0']['r_excess_yillik_pct']:5.2f}/{e['L1_b0']['excess_sharpe']:.2f}  L5/b0 {e['L5_b0']['r_excess_yillik_pct']:5.2f}/{e['L5_b0']['excess_sharpe']:.2f} | başabaş fee L1/b0 {bb['L1_b0']:.0f} bps L1/b_m {bb['L1_b_m']:.0f} | stres_bozulma≥ {st['stres_bozulma_alt_sinir']*100:.2f} pp ({st['en_kotu_olculen']})")
    print(f"\nHAVUZ ideal {sonuc['HAVUZ_28']['ideal']['r_pos_yillik_pct']:.2f} %/y — (2)+ DATA_BLOCKED (perp slippage yalnız BTC/ETH)")


if __name__ == "__main__":
    main()
