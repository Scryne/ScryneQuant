"""Pozitif kontrol: kapılar gerçek bir üstünlüğü **geçirebiliyor mu**? (istatistiksel güç)

Negatif kontrol (look-ahead, null kalibrasyonu) "sahte üstünlük geçmiyor mu?" sorusunu ölçer.
Bu araç tersini ölçer: bilinen, ayarlanabilir bir üstünlük verilmiş bir sinyal, projenin
**gerçek** motoru, maliyet modeli, IS/OOS bölmesi, walk-forward'u, stres testi ve K-019 +
K-113 kapılarından (`kapilar.degerlendir`) geçiyor mu, hangi olasılıkla?

**Alet, strateji değil.** `Kahin` sinyali bilerek geleceğe bakar (K-002'yi ihlal eder); tek
amacı üstünlüğün büyüklüğünü dışarıdan ayarlamaktır. `KUTUPHANE`ye kaydedilmez, hipotez
defterine yazılmaz, çekiliş sayılmaz (K-039) — `coklu_test.BetikStrateji` ile aynı statü.

Kahin: her `ufuk` barda bir karar; sonraki `ufuk` barın (t+1 açılışından t+1+ufuk açılışına,
K-004 fill'i) getirisinin işaretini `p` olasılıkla doğru bilir. Yukarı derse `maruziyet`
kadar long, aşağı derse FLAT (spot, long-only — kütüphanedeki stratejilerle aynı eylem uzayı).

    uv run python tools/pozitif_kontrol.py --p 0.50 0.55 0.60 --ufuk 24 168 --tohum 20
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from scryne_quant.backtest.metrikler import bar_yili
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.research import analiz, kapilar, kapilar_v2, walkforward
from scryne_quant.research import rejim as rejim_mod
from scryne_quant.research.bolme import is_oos, walk_forward
from scryne_quant.research.degerlendirme import EGITIM_BAR, TEST_BAR, _kararsizlik
from scryne_quant.research.tarama import ASGARI_ISLEM, asgari_islem_pencere, kosu, tara
from scryne_quant.strategy.sinyal import Sinyal, Yon
from scryne_quant.strategy.temel import Strateji

SEMBOL, TF = "BTCUSDT", "1h"
#: Kütüphane stratejilerinin ve kıyasın hedef maruziyeti (al_tut varsayılanı).
MARUZIYET = 0.2
#: Kütüphanedeki en uzun ısınma mertebesi; pencereler gerçek değerlendirmeyle aynı olsun.
ISINMA = 200

_SINYAL: dict[tuple[float, int, int], dict[int, str]] = {}
_DIZILER: dict[str, np.ndarray] = {}
#: Bar deposu. `data/market` (REST, 2021-06→) ya da `data/evren` (arşiv, 2017-08→); K-118.
DEPO = {"yol": "data/market"}


def sinyal_takvimi(acilis: np.ndarray, zaman: np.ndarray, p: float, ufuk: int,
                   tohum: int) -> dict[int, str]:
    """`open_time` → "BUY"/"FLAT"; yalnız yön değişen karar barlarında."""
    rng = np.random.default_rng(tohum)
    out: dict[int, str] = {}
    onceki = "FLAT"
    n = len(acilis)
    for t in range(ISINMA, n - ufuk - 1, ufuk):
        gercek_yukari = acilis[t + 1 + ufuk] > acilis[t + 1]
        dogru = rng.random() < p
        tahmin = gercek_yukari if dogru else not gercek_yukari
        yon = "BUY" if tahmin else "FLAT"
        if yon != onceki:
            out[int(zaman[t])] = yon
            onceki = yon
    return out


class Kahin(Strateji):
    """Ölçüm aleti; bilerek geleceğe bakar. Kütüphaneye **kaydedilmez** (K-039)."""

    ad = "pozitif_kontrol_kahin"

    def __init__(self, p: float = 0.5, ufuk: int = 24, tohum: int = 0) -> None:
        super().__init__(p=p, ufuk=ufuk, tohum=tohum)

    def ozellikler(self) -> Sequence[Any]:
        return ()

    def isinma_bar(self) -> int:
        return 0

    def on_bar(self, ctx: Any) -> Sinyal | None:
        k = (float(self.parametreler["p"]), int(self.parametreler["ufuk"]),
             int(self.parametreler["tohum"]))
        if k not in _SINYAL:
            _SINYAL[k] = sinyal_takvimi(_DIZILER["open"], _DIZILER["open_time"], *k)
        yon = _SINYAL[k].get(int(ctx.zaman))
        if yon is None:
            return None
        return Sinyal(symbol=ctx.sembol, side=Yon(yon),
                      target_exposure=MARUZIYET if yon == "BUY" else 0.0,
                      confidence=1.0, reason="POZITIF_KONTROL", timestamp=ctx.zaman)


def _yukle() -> dict[str, np.ndarray]:
    if not _DIZILER:
        _DIZILER.update(bar_dizileri(ParquetDepo(DEPO["yol"]).oku(SEMBOL, TF)))
    return _DIZILER


def degerlendir(p: float, ufuk: int, tohum: int) -> dict[str, Any]:
    """`research/degerlendirme.degerlendir`in tek-nokta kopyası (aynı pencereler, aynı sıra)."""
    d = _yukle()
    m = maliyet_mod.yukle()
    n = len(d["open_time"])
    ins, oos_p = is_oos(n, ISINMA)
    katmanlar = walk_forward(n, ISINMA, EGITIM_BAR, TEST_BAR, kaydirmali=True)
    grid = {"p": [p], "ufuk": [ufuk], "tohum": [tohum]}

    t = tara(Kahin, grid, m, SEMBOL, TF, d, ins, asgari_islem=ASGARI_ISLEM)
    en_iyi = t.sec("tepe")
    o: dict[str, Any] = {}
    if en_iyi is not None:
        so = kosu(Kahin(p, ufuk, tohum), m, SEMBOL, TF, d, oos_p)
        om = so.metrikler
        ish = en_iyi.metrikler.sharpe
        o |= {
            "oos_sharpe": om.sharpe, "oos_getiri": om.toplam_getiri,
            "oos_islem": om.islem_sayisi, "oos_max_drawdown": om.max_drawdown,
            "is_sharpe": ish, "oos_is_orani": om.sharpe / ish if ish > 0 else float("nan"),
            "oos_yillik_anlamli": om.yillik_anlamli,
            "oos_gun": kapilar.oos_suresi_gun(int(so.ozkaynak.size), timeframe_ms(TF)),
        }
        # K-054 rejim kapısı (kapilar_v2 ile aynı kesim): OOS'ta en kötü rejimin Sharpe'ı.
        et = rejim_mod.etiketle(d["close"], pencere=rejim_mod.pencere_bar(timeframe_ms(TF)))
        et = et[oos_p.dilim()][oos_p.olcum_baslangici:]
        rej = rejim_mod.olc(so.ozkaynak, et, yil_bar=bar_yili(timeframe_ms(TF)))
        o["en_kotu_rejim_sharpe"] = rej.en_kotu_sharpe
    else:
        o["is_islem_yetersiz"] = True
    try:
        wf = walkforward.calistir(Kahin, grid, m, SEMBOL, TF, d, katmanlar,
                                  asgari_islem=asgari_islem_pencere(EGITIM_BAR, timeframe_ms(TF)))
    except walkforward.WalkForwardHatasi as hata:
        # Gerçek hatta bu durum koşuyu düşürür; burada "ölçülemedi" = kapı kalır.
        o["wf_hata"] = str(hata)
    else:
        b = wf.basarili_katmanlar
        poz = sum(1 for k in b if k.test_metrikler.toplam_getiri > 0.0)
        o |= {"wf_pozitif_katman_orani": poz / len(b) if b else float("nan"),
              "wf_kararsizlik": _kararsizlik(wf.parametre_kararliligi()),
              "wf_sharpe": wf.bilesik_metrikler.sharpe}
    st = analiz.stres(Kahin(p, ufuk, tohum), m, SEMBOL, TF, d, oos_p)  # K-119: OOS
    o["stres_bozulma"] = st.bozulma()
    o["stres_sharpe_orani"] = st.sharpe_orani()
    k = kapilar.degerlendir("kahin", o).sozluk()
    kalan = list(k["kalan_kapilar"])
    esik = next(e for e in kapilar_v2.ESIKLER_V2 if e.alan == "en_kotu_rejim_sharpe")
    r = o.get("en_kotu_rejim_sharpe")
    o["rejim_gecti"] = r is not None and r >= esik.sinir
    return {"p": p, "ufuk": ufuk, "tohum": tohum, "olcumler": o, "gecti": k["gecti"],
            "kalan": kalan, "kapilar": k}


def _is(args: tuple[float, int, int, str]) -> dict[str, Any]:
    DEPO["yol"] = args[3]
    return degerlendir(*args[:3])


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=float, nargs="+", default=[0.5, 0.55, 0.6])
    ap.add_argument("--ufuk", type=int, nargs="+", default=[24, 168])
    ap.add_argument("--tohum", type=int, default=10)
    ap.add_argument("--isci", type=int, default=4)
    ap.add_argument("--cikti", default="runs/pozitif_kontrol.json")
    ap.add_argument("--depo", default="data/market")
    a = ap.parse_args(argv)
    isler = [(p, u, s, a.depo) for p in a.p for u in a.ufuk for s in range(a.tohum)]
    with ProcessPoolExecutor(a.isci) as ex:
        sonuc = list(ex.map(_is, isler))
    Path(a.cikti).parent.mkdir(parents=True, exist_ok=True)
    Path(a.cikti).write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, default=str),
                             encoding="utf-8")
    ozet(sonuc)


def ozet(sonuc: list[dict[str, Any]]) -> None:
    """p × ufuk başına: K-019+K-113 geçen, stres hariç geçen, + rejim (K-054) ve kalan kapılar."""
    print(f"{'p':>5} {'ufuk':>5} {'OOS Sh':>7} {'IS Sh':>6} {'K019':>6} {'stres-':>6} "
          f"{'+rejim':>6}  en sık kalan kapılar")
    anahtarlar = sorted({(r["p"], r["ufuk"]) for r in sonuc})
    for p, u in anahtarlar:
        g = [r for r in sonuc if r["p"] == p and r["ufuk"] == u]
        oos = np.nanmedian([r["olcumler"].get("oos_sharpe", np.nan) for r in g])
        ins = np.nanmedian([r["olcumler"].get("is_sharpe", np.nan) for r in g])
        stressiz = [r for r in g if set(r["kalan"]) <= {"stres_dayanikliligi"}]
        rejimli = [r for r in stressiz if r["olcumler"].get("rejim_gecti")]
        say: dict[str, int] = {}
        for r in g:
            for x in r["kalan"]:
                say[x] = say.get(x, 0) + 1
        en = ", ".join(f"{k}:{v}" for k, v in sorted(say.items(), key=lambda kv: -kv[1])[:4])
        n = len(g)
        print(f"{p:5.2f} {u:5d} {oos:7.2f} {ins:6.2f} {sum(r['gecti'] for r in g):3d}/{n:<2d} "
              f"{len(stressiz):3d}/{n:<2d} {len(rejimli):3d}/{n:<2d}  {en}")


if __name__ == "__main__":
    main(sys.argv[1:])
