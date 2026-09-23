"""RYPP çekilişi: IS ölçümü, program açılışı, ön kayıt, tek seferlik doğrulama. (K-128, K-130)

    python tools/rypp_kos.py is-olc        # yalnız in-sample: aday + kıyas (OOS'a bakmaz)
    python tools/rypp_kos.py program-ac    # kripto_risk_kapisi programı (bütçe 1)
    python tools/rypp_kos.py kaydet        # hipotez ön kaydı (protokol rypp)
    python tools/rypp_kos.py kos           # OOS + French 202607 + 201705, bir kez

Sıra K-125 §5'tir: araştırma (IS) → dondurma (program + hipotez kaydı, commit) → doğrulama (OOS,
bir kez). `kos` kirli ağaçta, kayıtsız hipotezde, kapanmış programda ya da daha önce koşulmuş bir
çekilişte **çalışmaz** (K-121 dersi: commit'siz koşu). Başarısız OOS üzerinde tuning yapılmaz.

Çıktılar `runs/rypp/<program>/`: `is_olcum.json`, `sonuc_oos.json` (motor kaydı, promotion
`--sonuc`), `ana.json` (`--rypp`), `bagimsiz.json` (`--bagimsiz`), `vintage.json`
(`--bagimsiz-vintage`), `ozet.json`.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import git_durumu
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.data import french
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research import evren_kosu
from scryne_quant.research import hipotez as hipotez_mod
from scryne_quant.research import program as program_mod
from scryne_quant.research import risk_protokolu as rp
from scryne_quant.research import rypp_kosu as rk
from scryne_quant.strategy.kutuphane.evren_esit_agirlik import EvrenEsitAgirlik
from scryne_quant.strategy.kutuphane.evren_risk_kapisi import EvrenRiskKapisi

KOK = Path(__file__).resolve().parent.parent
TABLO = KOK / "data" / "evren" / "_evren" / "27b7a16ed0ed.parquet"
DEPO = KOK / "data" / "evren"
AZAMI_SEMBOL = 600
PROGRAM = "kripto_risk_kapisi"
BUTCE = 1
PORTFOY = "EVREN_ESIT"
CIKTI = KOK / "runs" / "rypp" / PROGRAM
BAGIMSIZ = ("french_12ind_vw_gunluk_202607", "french_12ind_vw_gunluk_201705")

GEREKCE_HIPOTEZ = (
    "K-130 (C fazı, RYPP): evren kıyası (hacimde ilk 10, eşit ağırlık, haftalık, brüt 1,0) + "
    "BTCUSDT 200 günlük SMA rejim kapısı (altındayken nakit), günde bir kontrol. Izgara yok: "
    "literatür standardı tek nokta, sonuca bakılmadan. Soru: düşüşü zamanlamayla azaltıyor mu "
    "(P3 plasebo), getiriyi koruyor mu, bağımsız veride (French iki vintage) tutuyor mu."
)


def _strateji() -> EvrenRiskKapisi:
    return EvrenRiskKapisi()


def _kiyas(s: EvrenRiskKapisi) -> EvrenEsitAgirlik:
    p = s.parametreler
    n = int(p["azami_enstruman"])
    return EvrenEsitAgirlik(yeniden_dengele_bar=int(p["yeniden_dengele_bar"]), azami_enstruman=n,
                            azami_agirlik=float(p["hedef_brut"]) / n,
                            hedef_brut=float(p["hedef_brut"]))


def _veri() -> evren_kosu.EvrenVerisi:
    return evren_kosu.veri_kur(TABLO, depo_kok=DEPO, azami_sembol=AZAMI_SEMBOL)


def _pencereler(veri: evren_kosu.EvrenVerisi):
    ins, oos, _, _ = ed.pencereler(veri, isinma_bar=_strateji().isinma_bar())
    return ins, oos


def _hipotez(veri: evren_kosu.EvrenVerisi) -> hipotez_mod.Hipotez:
    s = _strateji()
    return hipotez_mod.Hipotez.kur(
        s.ad, veri.timeframe, ed.veri_kimligi(veri),
        {a: [v] for a, v in sorted(s.parametreler.items())}, GEREKCE_HIPOTEZ,
        secim="tepe", program=PROGRAM, evren=veri.kural_kimligi, portfoy=PORTFOY,
        protokol="rypp", veri_son_ms=int(veri.zamanlar[-1]),
    )


def _temiz(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _temiz(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_temiz(v) for v in x]
    if isinstance(x, np.ndarray):
        return _temiz(x.tolist())
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def _yaz(yol: Path, govde: Any) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(govde, ensure_ascii=False, indent=1, allow_nan=True),
                   encoding="utf-8")


def _olcum(sonuc: Any) -> dict[str, Any]:
    o = rp.olc(np.asarray(sonuc.ozkaynak, float), rk.KRIPTO_YIL_BAR)
    return _temiz(o.sozluk() | {"islem": sonuc.metrikler.islem_sayisi})


# ------------------------------------------------------------------ komutlar


def is_olc() -> int:
    """Yalnız IS: aday ve kıyas. Karar için değil, uygulamanın doğruluğu ve program kaydının
    `kaynak_olcumu` için (K-051). OOS barına dokunmaz."""
    bas = time.perf_counter()
    veri = _veri()
    ins, oos = _pencereler(veri)
    maliyet = maliyet_mod.yukle()
    st = _strateji()
    s = ed.kosu(st, maliyet, veri, ins)
    k = ed.kosu(_kiyas(st), maliyet, veri, ins)
    govde = {
        "pencere": {"is": [ins.baslangic, ins.bitis], "oos_baslangic": oos.baslangic,
                    "is_ilk_utc": utc_str(int(veri.zamanlar[ins.baslangic])),
                    "is_son_utc": utc_str(int(veri.zamanlar[ins.bitis - 1]))},
        "aday": _olcum(s), "kiyas": _olcum(k), "rejim_gecis": st.gecis,
        "not": "yalnız in-sample; OOS'a bakılmadı",
        "git": git_durumu(KOK), "zaman_utc": utc_str(simdi_ms()),
        "sure_sn": round(time.perf_counter() - bas, 1),
    }
    _yaz(CIKTI / "is_olcum.json", govde)
    print(json.dumps(govde, ensure_ascii=False, indent=1))
    return 0


def program_ac() -> int:
    olcum = json.loads((CIKTI / "is_olcum.json").read_text(encoding="utf-8"))
    kayit = program_mod.ProgramKaydi(
        ad=PROGRAM,
        gerekce=(
            "K-125/K-128: hedef riski yönetilen sistematik yatırım; C fazı tek ön kayıtlı RYPP "
            "adayıyla açılır. Aday kıyasın kendisidir, yalnız piyasanın uzun vadeli trendi "
            "bozulduğunda nakde geçer; promotion yolu RYPP (plasebo + iki vintage bağımsız veri)."
        ),
        kaynak_farki=(
            "Önceki evren çekilişleri seçim/dışlama (kesitsel, türev, makro yalnız giriş engeli) "
            "ya da üye başına trenddi (h63). Bu aday seçimi değiştirmez, çıkışı da yöneten tek "
            "bir piyasa zamanlaması kapısıdır ve alfa değil düşüş azaltımı sorusudur (RYPP)."
        ),
        kaynak_olcumu={"is_aday": olcum["aday"], "is_kiyas": olcum["kiyas"],
                       "is_pencere": olcum["pencere"], "oos_bakilmadi": True,
                       "k124_hisse_is": "sektör trendi al-tut'a +0,1-0,17 Sharpe, riski "
                                        "iyileştirir"},
        azami_cekilis=BUTCE,
        durma_kurali=(
            "Bütçe 1, tek çekiliş. OOS bir kez koşulur (kripto + French 202607 + 201705); "
            "FAIL/INCONCLUSIVE'de aynı OOS'ta tuning yok, program kapanır. PASS promotion değil: "
            "sonra risk incelemesi, paper ve elle onay."
        ),
        esik_tahmini={"rypp_k": BUTCE, "p3_persentil": 1 - 0.05 / BUTCE,
                      "not": "K-128: k = program bütçesi"},
    )
    defter = program_mod.ProgramDefteri()
    if defter.acik(PROGRAM) is not None:
        print(f"{PROGRAM} zaten açık")
        return 0
    defter.ac(kayit)
    print(f"açıldı: {PROGRAM} (bütçe {BUTCE})")
    return 0


def kaydet() -> int:
    veri = _veri()
    hip = _hipotez(veri)
    defter = hipotez_mod.HipotezDefteri()
    onceki = defter.sira(hip)
    sira = defter.kaydet(hip, programlar=None if onceki is not None else
                         program_mod.ProgramDefteri())
    print(("zaten kayıtlı" if onceki is not None else "kaydedildi") + f": {sira}. hipotez")
    print(f"kimlik {hip.kimlik}")
    return 0


def kos() -> int:
    git = git_durumu(KOK)
    if git.get("dirty") or not git.get("commit"):
        print("HATA: çalışma ağacı kirli ya da git okunamadı — önce commit (K-009, K-121)",
              file=sys.stderr)
        return 2
    if (CIKTI / "ana.json").exists():
        print("HATA: bu çekiliş zaten koşuldu; OOS bir kez bakılır (K-125 §5.3)", file=sys.stderr)
        return 2
    programlar = program_mod.ProgramDefteri()
    if programlar.acik(PROGRAM) is None:
        print(f"HATA: {PROGRAM} programı açık değil", file=sys.stderr)
        return 2
    bas = time.perf_counter()

    def ilerle(m: str) -> None:
        print(f"[{time.perf_counter() - bas:7.0f} s] {m}", flush=True)

    # Bağımsız veriler önce: kilit tutmazsa OOS'a hiç bakılmadan durulur.
    cerceveler = {d: french.yukle(manifest=french.manifest_oku(d)) for d in BAGIMSIZ}
    ilerle("bağımsız veriler kilitli ve doğrulandı")
    veri = _veri()
    hip = _hipotez(veri)
    defter = hipotez_mod.HipotezDefteri()
    sira = defter.dogrula(hip)
    ilerle(f"veri hazır · {len(veri.diziler)} sembol · hipotez {sira}")
    _, oos = _pencereler(veri)
    maliyet = maliyet_mod.yukle()
    st = _strateji()
    s = ed.kosu(st, maliyet, veri, oos)
    ilerle("aday OOS koşuldu")
    k = ed.kosu(_kiyas(_strateji()), maliyet, veri, oos)
    ilerle("kıyas OOS koşuldu")
    s2 = ed.kosu(_strateji(), maliyet, veri, oos, maliyet_carpani={"fee": 2.0, "slippage": 2.0})
    ilerle("aday 2x maliyet koşuldu")
    s.yaz(CIKTI / "sonuc_oos.json")
    maliyet_orani = (maliyet.fee_taker_bps + maliyet.slippage_bps) / 1e4
    girdi, meta = rk.kripto_girdi(s, k, s2, maliyet_orani=maliyet_orani, aile_sayisi=BUTCE,
                                  aile_program=PROGRAM)
    ana = rp.degerlendir(girdi)
    _yaz(CIKTI / "ana.json", _temiz(ana.sozluk()))
    ilerle(f"ana RYPP: {ana.durum}")

    esleme = rk.Esleme.kripto_parametrelerinden(st.parametreler)
    bag_sonuc: dict[str, Any] = {}
    for d, dosya in zip(BAGIMSIZ, ("bagimsiz.json", "vintage.json"), strict=True):
        v = cerceveler[d]
        g, m = rk.bagimsiz_girdi(v.cerceve(), esleme, aile_sayisi=BUTCE, aile_program=PROGRAM,
                                 sektorler=french.SEKTORLER)
        sonuc = rp.degerlendir(g)
        govde = _temiz(sonuc.sozluk()) | {"dataset_id": d, "veri_sha256": v.veri_sha256}
        _yaz(CIKTI / dosya, govde)
        bag_sonuc[d] = {"durum": str(sonuc.durum), "meta": m}
        ilerle(f"{d}: {sonuc.durum}")

    ozet = {
        "program": PROGRAM, "hipotez": {"sira": sira, "kimlik": hip.kimlik},
        "oos": {"ilk_utc": utc_str(int(veri.zamanlar[oos.baslangic])),
                "son_utc": utc_str(int(veri.zamanlar[oos.bitis - 1]))},
        "ana": {"durum": str(ana.durum), "meta": meta,
                "aday": _olcum(s), "kiyas": _olcum(k), "aday_2x": _olcum(s2),
                "kosullar": [{"ad": c["ad"], "gecti": c["gecti"]} for c in ana.kosullar]},
        "bagimsiz": bag_sonuc,
        "git": git, "zaman_utc": utc_str(simdi_ms()),
        "sure_sn": round(time.perf_counter() - bas, 1),
        "promotion_komutu": (
            f"sq promotion degerlendir {st.ad} --protokol rypp --sonuc {CIKTI / 'sonuc_oos.json'}"
            f" --rypp {CIKTI / 'ana.json'} --bagimsiz {CIKTI / 'bagimsiz.json'}"
            f" --bagimsiz-vintage {CIKTI / 'vintage.json'} --hipotez {hip.kimlik}"
        ),
    }
    _yaz(CIKTI / "ozet.json", _temiz(ozet))
    print(json.dumps(_temiz(ozet), ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    alt = ap.add_subparsers(dest="komut", required=True)
    for ad in ("is-olc", "program-ac", "kaydet", "kos"):
        alt.add_parser(ad)
    a = ap.parse_args()
    return {"is-olc": is_olc, "program-ac": program_ac, "kaydet": kaydet, "kos": kos}[a.komut]()


if __name__ == "__main__":
    raise SystemExit(main())
