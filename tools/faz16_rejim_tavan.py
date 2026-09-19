"""Faz 16 / Faz 0 — rejim × alpha ailesi **oracle tavanı**, yalnız kayıtlı OOS çıktılarından. (K-077)

Soru: "Jev (ya da herhangi bir seçici) kusursuz olsaydı bile mevcut alpha evreninde kapı
seviyesinde edge var mıydı?" Cevap için her rejimde OOS'ta en iyi aile **sonucu görerek**
seçilir ve rejimler arası geçiş maliyeti sıfır sayılır — ikisi de iyimser; çıkan sayı bir
TAVAN'dır, promotion kanıtı değil. Backtest yok, Jev yok, çekiliş yok: girdi Faz 11'in 38
tek-sembol çekilişi (`runs/deneyler/kapilar_v2/301e3750d764-530ecf2a72f1.json`) ve Faz 12/16'nın
14 evren çekilişi (`runs/faz12/*.json`); rejim etiketi `research/rejim.py`nin bölümlemesi.

Birleşik Sharpe, `rejim.olc` formülünün tersinden (rejim başına ortalama/σ) havuzlanarak
yeniden kurulur; kayıtlı toplam OOS Sharpe'a karşı doğrulanır (evren: ort. sapma 0,07,
azami 0,16). Yaklaşımdan bağımsız üst sınır: gözlenen en yüksek tekil rejim Sharpe'ı.

Kullanım: uv run python tools/faz16_rejim_tavan.py
Çıktı:    runs/faz16/rejim_tavan.json
"""
import json, glob, math
import numpy as np

YIL_BAR = {"1h": 8760, "4h": 2190, "1d": 365}

def momentler(bar, getiri, sharpe, A):
    """rejim.olc formülünün tersi: mean/std (bar başına) ≈ (log1p(getiri)/bar, mean·√A/S)."""
    m = math.log1p(getiri) / bar
    if sharpe is None or abs(sharpe) < 1e-9:
        return m, None
    s = m * math.sqrt(A) / sharpe
    return m, abs(s)

def birlesik_sharpe(parcalar, A):
    """parcalar: [(bar, m, s)] — rejimlerin havuzu; s=None ise (flat) σ=0."""
    n = sum(p[0] for p in parcalar)
    m = sum(p[0] * p[1] for p in parcalar) / n
    v = sum(p[0] * ((p[2] or 0.0) ** 2 + p[1] ** 2) for p in parcalar) / n - m * m
    return m / math.sqrt(v) * math.sqrt(A) if v > 0 else 0.0

def oracle(grup, A):
    """grup: {ad: {rejim: (bar, sharpe, getiri)}} → oracle tabloları."""
    rejimler = sorted({r for v in grup.values() for r in v})
    secim, secim_flat = {}, {}
    for r in rejimler:
        adaylar = [(ad, v[r][1], v[r]) for ad, v in grup.items() if r in v and v[r][1] is not None]
        en = max(adaylar, key=lambda x: x[1])
        secim[r] = en
        secim_flat[r] = en if en[1] > 0 else (None, 0.0, (en[2][0], 0.0, 0.0))
    def birlestir(sec):
        parcalar = []
        for r, (ad, S, (bar, S2, g)) in sec.items():
            m, s = (0.0, None) if ad is None else momentler(bar, g, S, A)
            parcalar.append((bar, m, s))
        return birlesik_sharpe(parcalar, A)
    return {
        "rejimler": rejimler,
        "oracle": {r: {"aile": a, "sharpe": S, "bar": v[0], "getiri": v[2]} for r, (a, S, v) in secim.items()},
        "oracle_birlesik_sharpe": birlestir(secim),
        "oracle_en_kotu_rejim_sharpe": min(S for _, S, _ in secim.values()),
        "oracle_flat": {r: {"aile": a, "sharpe": S} for r, (a, S, v) in secim_flat.items()},
        "oracle_flat_birlesik_sharpe": birlestir(secim_flat),
        "oracle_flat_en_kotu_rejim_sharpe": min(S for _, S, _ in secim_flat.values()),
    }

# --- G1: BTC tek sembol, 38 çekiliş (Faz 11 kaydı)
d = json.load(open("runs/deneyler/kapilar_v2/301e3750d764-530ecf2a72f1.json", encoding="utf-8"))
gruplar = {}
for x in d["cikti"]["cekilisler"]:
    r = (x.get("detay") or {}).get("rejim", {}).get("rejimler") or {}
    if not r: continue
    tf = x["timeframe"]
    ad = f'{x["strateji"]}/{x["secim"]}'
    gruplar.setdefault(f"BTCUSDT {tf}", {})[ad] = {k: (v["bar"], v["sharpe"], v["getiri"]) for k, v in r.items() if v["sharpe"] is not None}

# --- G2: evren 1h, 14 çekiliş (Faz 12/16) + kıyas
ev = {}; kiyas = {}
for p in sorted(glob.glob("runs/faz12/*.json")):
    try: j = json.load(open(p, encoding="utf-8"))
    except Exception: continue
    if not isinstance(j.get("sonuc"), dict) or "detay" not in j["sonuc"]: continue
    r = j["sonuc"]["detay"]["rejim"]["rejimler"]
    ev[j["cekilis"]] = {k: (v["bar"], v["sharpe"], v["getiri"]) for k, v in r.items()}
    kiyas[j["cekilis"]] = (j["kiyas_oos"]["strateji"], j["kiyas_oos"]["metrikler"]["sharpe"], j["sonuc"]["olcumler"]["oos_sharpe"])
gruplar["EVREN 1h (b06857c0)"] = ev

# --- doğrulama: birleştirme yaklaşımı, bilinen toplam OOS Sharpe'a karşı
print("== yaklaşım doğrulaması (evren: rejim momentlerinden toplam Sharpe vs kayıtlı oos_sharpe)")
for ad, (ks, kS, oS) in kiyas.items():
    parcalar = [(b, *momentler(b, g, S, 8760)) for b, S, g in ev[ad].values()]
    print(f"  {ad:22} yeniden={birlesik_sharpe(parcalar, 8760):.3f} kayıt={oS:.3f}")

cikti = {}
for g, grup in gruplar.items():
    A = YIL_BAR[g.split()[1]]
    o = oracle(grup, A)
    cikti[g] = o
    print(f"\n== {g}  ({len(grup)} çekiliş)")
    for r in o["rejimler"]:
        sat = sorted(((ad, v[r][1]) for ad, v in grup.items() if r in v), key=lambda x: -x[1])
        print(f"  {r:9} en iyi 3: " + ", ".join(f"{a} {S:+.2f}" for a, S in sat[:3]) + f"   | pozitif: {sum(1 for _,S in sat if S>0)}/{len(sat)}")
    print(f"  ORACLE          birleşik Sharpe {o['oracle_birlesik_sharpe']:+.3f}   en kötü rejim {o['oracle_en_kotu_rejim_sharpe']:+.3f}")
    print(f"  ORACLE+no-trade birleşik Sharpe {o['oracle_flat_birlesik_sharpe']:+.3f}   en kötü rejim {o['oracle_flat_en_kotu_rejim_sharpe']:+.3f}")
    print(f"  kapı: oos_sharpe ≥ 1,04 → {'GEÇTİ' if o['oracle_flat_birlesik_sharpe']>=1.04 else 'kaldı'};  rejim_kararliligi ≥ 0,685 → {'GEÇTİ' if o['oracle_en_kotu_rejim_sharpe']>=0.685 else 'kaldı'}")
json.dump(cikti, open("runs/faz16/rejim_tavan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
