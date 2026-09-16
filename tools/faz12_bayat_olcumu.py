"""`bayat_degerleme` ölçümü: barı biten sembolde kalan pozisyonlar. (Faz 12, açık kalem)

`kesitsel_fiyat` raporu §4/1: OOS'ta sayaç 13.101-58.254 pozisyon-bar çıktı. Bu araç
**yeni çekiliş yapmaz**: kapanmış programın dört çekilişinin kayıtlı seçimini
(`runs/faz12/<çekiliş>.json`) ve kıyası aynı OOS penceresinde yeniden koşturur; sonucu
değil **motorun davranışını** ölçer. `sonuc_hash` kayıtla karşılaştırılır — aynı değilse
ölçüm durur (K-038 kalıbı).

Ölçülen:

1. Takılan her pozisyon: sembol, son barı, koşu sonuna kadar kaç bar takılı kaldığı, son
   fiyattan değeri ve özkaynağa oranı.
2. Son bar **delist mi, veri kesiği mi**: sembolün son barı ızgaranın sonundan önce mi, ve
   arşiv kaynak kaydı (`1h.kaynak.json`) son ayı içeriyor mu.
3. İki sınır: (a) motorun bugünkü hâli — son fiyattan değerleme; (b) son bardan sonra değer
   **sıfır** (alt sınır). Ara gerçek (delist duyurusundan sonra satış) ikisinin arasında;
   duyuru tarihi veride olmadığı için tahmin edilmez.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.backtest.metrikler import bar_yili
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import git_durumu
from scryne_quant.common.zaman import timeframe_ms, utc_str
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research import evren_kosu
from scryne_quant.research.izgaralar import evren_cekilisi
from scryne_quant.strategy.evren import LISTELENMEDI
from scryne_quant.strategy.kutuphane import EVREN_AILELER, EvrenEsitAgirlik

KOK = Path(__file__).resolve().parent.parent
TABLO = KOK / "data" / "evren" / "_evren" / "27b7a16ed0ed.parquet"
DEPO = KOK / "data" / "evren"
CIKTI = KOK / "runs" / "faz12" / "bayat-olcumu.json"
CEKILISLER = (
    "kesitsel_guc_haftalik",
    "kesitsel_guc_aylik",
    "kesitsel_ters_haftalik",
    "kesitsel_ters_aylik",
)


def _sharpe(ozkaynak: np.ndarray, yil_bar: float) -> float:
    onceki = np.where(ozkaynak[:-1] > 0.0, ozkaynak[:-1], np.nan)
    r = np.nan_to_num(np.diff(ozkaynak) / onceki, nan=-1.0)
    sd = float(np.std(r, ddof=1))
    return float(np.mean(r) / sd * math.sqrt(yil_bar)) if sd > 0 else float("nan")


def olc(ad: str, strateji, veri, pencere, beklenen_hash: str | None) -> dict:
    maliyet = maliyet_mod.yukle()
    g = ed.gorunum(veri, strateji, pencere)
    sonuc = CokluBacktest(strateji, maliyet).calistir(
        g, veri_sha256=veri.veri_sha256, olcum_baslangici=pencere.olcum_baslangici
    )
    if beklenen_hash is not None and sonuc.sonuc_hash != beklenen_hash:
        raise SystemExit(f"{ad}: sonuc_hash kayıtla uyuşmuyor — ölçüm durdu")

    zam = sonuc.zamanlar
    n_izgara = len(veri)
    son_izgara_ms = int(veri.zamanlar[-1])
    takilanlar = []
    sifir_duzeltme = np.zeros(len(zam), dtype=np.float64)
    for islem in sonuc.islemler:
        if islem.kapanis_ms is not None:
            continue
        kalan = islem.giris_miktar - islem.cikis_miktar
        if kalan <= 0.0:
            continue
        s = islem.sembol
        kalite = np.asarray(veri.diziler[s]["quality_status"], dtype=object)
        var = np.flatnonzero(kalite[:n_izgara] != LISTELENMEDI)
        son_i = int(var[-1])
        son_ms = int(veri.zamanlar[son_i])
        if son_ms >= son_izgara_ms:
            continue  # barı pencere sonuna kadar süren açık pozisyon: takılı değil
        son_fiyat = float(veri.diziler[s]["close"][son_i])
        deger = kalan * son_fiyat
        sonrasi = zam > son_ms
        sifir_duzeltme[sonrasi] += deger
        kaynak = DEPO / s / "1h.kaynak.json"
        # `dosyalar`: arşiv yolu → SHA-256. Son dosya, arşivin o sembol için bildiği son ay.
        aylar = []
        if kaynak.exists():
            dosyalar = json.loads(kaynak.read_text(encoding="utf-8"))["dosyalar"]
            aylar = sorted(Path(y).name for y in dosyalar)
        takilanlar.append({
            "sembol": s,
            "giris_utc": utc_str(islem.acilis_ms),
            "son_bar_utc": utc_str(son_ms),
            "takili_bar": int(sonrasi.sum()),
            "kalan_miktar": kalan,
            "son_fiyat": son_fiyat,
            "giris_notional": islem.giris_notional,
            "son_fiyattan_deger": deger,
            "ozkaynak_payi_son": deger / float(sonuc.ozkaynak[-1]),
            "arsiv_son_kayit": aylar[-1] if aylar else None,
        })

    yil_bar = bar_yili(timeframe_ms(veri.timeframe))
    alt = sonuc.ozkaynak - sifir_duzeltme
    return {
        "ad": ad,
        "sonuc_hash": sonuc.sonuc_hash,
        "hash_kayitla_ayni": None if beklenen_hash is None else True,
        "bayat_degerleme": sonuc.atlanan.get("bayat_degerleme"),
        "takili_pozisyon": len(takilanlar),
        "takilanlar": sorted(takilanlar, key=lambda t: t["son_bar_utc"]),
        "sonda_takili_deger_payi": float(sifir_duzeltme[-1] / sonuc.ozkaynak[-1]),
        "a_son_fiyat": {
            "sharpe": sonuc.metrikler.sharpe,
            "sharpe_yeniden_hesap": _sharpe(sonuc.ozkaynak, yil_bar),
            "toplam_getiri": sonuc.metrikler.toplam_getiri,
        },
        "b_sifir": {
            "sharpe": _sharpe(alt, yil_bar),
            "toplam_getiri": float(alt[-1] / alt[0] - 1.0),
        },
    }


def main() -> int:
    veri = evren_kosu.veri_kur(TABLO, depo_kok=DEPO, azami_sembol=600)
    _, oos, _, _ = ed.pencereler(veri)
    satirlar = []
    for ad in CEKILISLER:
        d = json.loads((KOK / "runs" / "faz12" / f"{ad}.json").read_text(encoding="utf-8"))
        strateji_adi, _ = evren_cekilisi(ad)
        p = d["sonuc"]["detay"]["secim"]["secilen"]
        satir = olc(ad, EVREN_AILELER[strateji_adi](**p), veri, oos,
                    d["sonuc"]["detay"]["oos"]["sonuc_hash"])
        satirlar.append(satir)
        kiyas = d["kiyas_oos"]
        kp = kiyas["parametreler"]
        ks = olc(
            f"kiyas_{kp['yeniden_dengele_bar']}",
            EvrenEsitAgirlik(
                yeniden_dengele_bar=kp["yeniden_dengele_bar"],
                azami_enstruman=kp["azami_enstruman"],
                azami_agirlik=kp["hedef_brut"] / kp["azami_enstruman"],
                hedef_brut=kp["hedef_brut"],
            ),
            veri, oos, kiyas["sonuc_hash"],
        )
        if all(x["ad"] != ks["ad"] for x in satirlar):
            satirlar.append(ks)
        print(
            f"{satir['ad']:24s} bayat={satir['bayat_degerleme']:>6} "
            f"takılı={satir['takili_pozisyon']:>3} "
            f"sonda pay={satir['sonda_takili_deger_payi']:.3%} "
            f"Sharpe a={satir['a_son_fiyat']['sharpe']:+.3f} b={satir['b_sifir']['sharpe']:+.3f}",
            flush=True,
        )
    for s in satirlar:
        if s["ad"].startswith("kiyas"):
            print(
                f"{s['ad']:24s} bayat={s['bayat_degerleme']:>6} "
                f"takılı={s['takili_pozisyon']:>3} "
                f"Sharpe a={s['a_son_fiyat']['sharpe']:+.3f} b={s['b_sifir']['sharpe']:+.3f}"
            )
    CIKTI.write_text(
        json.dumps({"olcumler": satirlar, "pencere": oos.sozluk(), "git": git_durumu(KOK)},
                   ensure_ascii=False, indent=1, default=str),
        encoding="utf-8",
    )
    print(f"yazıldı: {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
