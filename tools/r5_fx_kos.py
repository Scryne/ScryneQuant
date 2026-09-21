"""R5 FX alfa çekilişleri (`fx_fiyat` programı): ön kayıt, koşu, durum. (K-039, K-051, K-102)

    python tools/r5_fx_kos.py kaydet <cekilis> -g "<gerekçe>"
    python tools/r5_fx_kos.py kos <cekilis>
    python tools/r5_fx_kos.py durum

`tools/faz12_evren_kos.py`nin FX karşılığı; aynı kural: `kos` yalnızca defterde **kayıtlı**
bir hipotezi koşturur, kayıt ile koşu aynı `hipotez_kur`dan aynı kimliği görür.

Kripto koşucudan farklar, hepsi ölçülmüş bir kısıttan:

- **Veri:** `evren_kosu.fx_veri_kur` (FXCM deposu, 5x24 takvim, bid/ask, K-096). Pencere
  K-101'in 21 proxy finansman modelinin ortak geçerli aralığıyla sınırlı — aylık pencere
  çözünürlüğünde `2023-11..2024-02` (1.721 bar). Finansman modeli **gevşetilmez**; aralık
  dışına taşan koşuyu motor zaten reddediyor.
- **Isınma verinin içinden:** depo 2023-11-19'dan önceye gitmiyor; `degerlendir(isinma_bar=…)`
  ızgaranın en büyük penceresini (240 + 2) verinin başından ısınma sayar.
- **Kontrol grubu sabit:** `fx_evren_esit_agirlik` (K-099) — 21 çiftin tamamı, haftalık (120 bar)
  dengeleme, `hedef_brut` 0,2 (çekilişlerle aynı maruziyet). Kripto koşucu kıyası seçilen
  yoğunlukla koşuyordu; FX'te yoğunluk kıyasa taşınmaz, çünkü FX kıyasında sıralama yok ve
  tavan alfabetik bir alt küme üretir (K-099). Kıyas hem OOS'ta hem in-sample'da hem tam
  pencerede ölçülür ve kayda girer.
- **Rejim kıyası `EURUSD`:** K-058'in rejim eşiği BTC kapanışında kalibre edildi; FX'te
  kalibre değil ve 30 günlük pencere 516 barlık OOS'a sığmıyor — kapı "ölçülemedi" verir ve
  bu rapora öyle geçer.
- **Walk-forward sığmıyor** (8.766 + 2.190 bar > 1.721): `pencereler` boş katman döndürür,
  kapı "ölçülemedi". Katmanı küçültmek kapının sorusunu değiştirmek olurdu.
- **Koşucu seri:** 21 çift × 1.721 bar bir koşu < 1 s; havuz gereksiz.

Maliyet bileşenleri (komisyon, slippage, spread, finansman) motorun kendi kaydından
(`Metrikler`) okunur; brüt = net + bileşenler. Hiçbir sayı burada modellenmez.
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
from scryne_quant.research import evren_degerlendirme as ed
from scryne_quant.research import evren_kosu
from scryne_quant.research import hipotez as hipotez_mod
from scryne_quant.research import program as program_mod
from scryne_quant.research.izgaralar import (
    FX_CEKILISLERI,
    FX_DONUS_CEKILISLERI,
    FX_HAFTALIK,
    SABIT_MARUZIYET,
    cekilis_programi,
    evren_cekilisi,
)
from scryne_quant.strategy.kutuphane import EVREN_AILELER, FxEvrenEsitAgirlik
from scryne_quant.strategy.kutuphane.kesitsel import ATR_PENCERESI

KOK = Path(__file__).resolve().parent.parent
TABLO = KOK / "data" / "fx" / "_evren" / "6124cf568498.parquet"
DEPO = KOK / "data" / "fx"
CIKTI = KOK / "runs" / "fx"
#: FX programları ve çekilişleri (K-102 `fx_fiyat`, K-104 `fx_ortalama_donus`): aynı pencere, aynı
#: kontrol, aynı ısınma tabanı — sonuçlar programlar arasında aynı IS/OOS barlarında karşılaştırılır
FX_PROGRAMLAR: dict[str, tuple[str, ...]] = {
    "fx_fiyat": tuple(FX_CEKILISLERI),
    "fx_ortalama_donus": tuple(FX_DONUS_CEKILISLERI),
}
TUM_CEKILISLER = tuple(c for adlar in FX_PROGRAMLAR.values() for c in adlar)
#: Isınma tabanı: `fx_fiyat`ın en büyük penceresi (240) + 2. Daha küçük pencereli program da bu
#: tabanı kullanır ki IS/OOS barları ve kontrol sayıları programlar arasında **aynı** olsun.
ISINMA_TABANI = 240 + 2
#: K-101/4: 21 proxy'nin ortak geçerli penceresi 2023-11-19..2024-03-18; aylık çözünürlükte
#: Mart dışarıda kalır (JPY çiftleri 03-19'da biter, `--bitis 2024-03` Mart'ın tamamını ister).
BASLANGIC_AY = "2023-11"
BITIS_AY = "2024-02"
AZAMI_SEMBOL = 30
REJIM_KIYASI = "EURUSD"
#: Kıyasın çift sayısı (K-099: tavan bağlamaz, evrenin tamamı).
KIYAS_CIFT = 21
PORTFOY = ed.KESITSEL_PORTFOY


def _isinma(secenekler: dict[str, Any]) -> int:
    return max(ISINMA_TABANI, max(ATR_PENCERESI, max(int(p) for p in secenekler["pencere"])) + 2)


def _veri(cekilis: str) -> evren_kosu.EvrenVerisi:
    _, secenekler = evren_cekilisi(cekilis)
    return evren_kosu.fx_veri_kur(
        TABLO, depo_kok=DEPO, isinma_bar=_isinma(secenekler),
        baslangic_ay=BASLANGIC_AY, bitis_ay=BITIS_AY, azami_sembol=AZAMI_SEMBOL,
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


def _hipotez(cekilis: str, veri: evren_kosu.EvrenVerisi, gerekce: str) -> hipotez_mod.Hipotez:
    return ed.hipotez_kur(
        cekilis, veri, program=cekilis_programi(cekilis), gerekce=gerekce, portfoy=PORTFOY
    )


def kaydet(cekilis: str, gerekce: str) -> int:
    program = cekilis_programi(cekilis)
    veri = _veri(cekilis)
    hip = _hipotez(cekilis, veri, gerekce)
    defter = hipotez_mod.HipotezDefteri()
    programlar = program_mod.ProgramDefteri()
    onceki = defter.sira(hip)
    sira = defter.kaydet(hip, programlar=None if onceki is not None else programlar)
    butce = programlar.butce(program, defter.tumu())
    print(("zaten kayıtlı" if onceki is not None else "kaydedildi") + f": {sira}. hipotez")
    print(f"kimlik : {hip.kimlik[:16]} · strateji {hip.strateji} · veri {hip.veri_sha256[:12]}")
    print(f"bütçe  : {program} {butce['harcanan']}/{butce['azami_cekilis']} "
          f"(kalan {butce['kalan']})")
    return 0


def _kiyas() -> FxEvrenEsitAgirlik:
    return FxEvrenEsitAgirlik(
        yeniden_dengele_bar=FX_HAFTALIK, azami_enstruman=KIYAS_CIFT, hedef_brut=SABIT_MARUZIYET
    )


def _maliyet_ozeti(sonuc: Any) -> dict[str, Any]:
    """Motor kaydından maliyet bileşenleri ve brüt/net (USD, başlangıç 10.000).

    `islem_sayisi` motorun tanımı (kapanmış tur); kıyas gibi pozisyonu hiç kapatmayan bir
    koşuda 0 çıkar ve yanıltır — `fill_sayisi` (motor hattından geçen her dolum) yanında.
    """
    m = sonuc.metrikler
    spread = m.toplam_spread or 0.0
    finansman = m.toplam_finansman or 0.0
    toplam = m.toplam_komisyon + m.toplam_slippage + spread + finansman
    net = m.bitis_sermaye - m.baslangic_sermaye
    return {
        "islem_sayisi": m.islem_sayisi,
        "fill_sayisi": int(sum(i.fill_sayisi for i in sonuc.islemler)),
        "acik_kalan": int(sum(1 for i in sonuc.islemler if i.kapanis_ms is None)),
        "net_usd": net,
        "brut_usd": net + toplam,
        "net_getiri": m.toplam_getiri,
        "brut_getiri": (net + toplam) / m.baslangic_sermaye,
        "maliyet": {
            "komisyon": m.toplam_komisyon,
            "slippage": m.toplam_slippage,
            "spread": m.toplam_spread,
            "finansman": m.toplam_finansman,
            "toplam": toplam,
        },
        "sharpe": m.sharpe,
        "max_drawdown": m.max_drawdown,
        "turnover": m.turnover,
    }


def kos(cekilis: str) -> int:
    strateji_adi, secenekler = evren_cekilisi(cekilis)
    program = cekilis_programi(cekilis)
    if program not in FX_PROGRAMLAR:
        print(f"HATA: {cekilis} bir FX programının çekilişi değil", file=sys.stderr)
        return 2
    sinif = EVREN_AILELER[strateji_adi]
    basladi = time.perf_counter()
    veri = _veri(cekilis)
    hip = _hipotez(cekilis, veri, "kimlik kontrolü için geçici nesne")
    sira = hipotez_mod.HipotezDefteri().sira(hip)
    if sira is None:
        print(
            f"HATA: {cekilis} hipotez defterinde kayıtlı değil. Sonucu gördükten sonra "
            f"kaydetmek ön kayıt değildir (K-039). Önce: kaydet {cekilis} -g ...",
            file=sys.stderr,
        )
        return 2
    maliyet = maliyet_mod.yukle()
    isinma = _isinma(dict(secenekler))

    def ilerleme(m: str) -> None:
        print(f"[{time.perf_counter() - basladi:6.1f} s] {m}", flush=True)

    ayar = ed.motor_ayarlari(veri)
    if not ayar.coklu_model or ayar.finansmanlar is None or ayar.takvim is None:
        print("HATA: FX motor ayarları çözülemedi (çift başına maliyet/finansman/takvim yok)",
              file=sys.stderr)
        return 2
    ilerleme(
        f"veri hazır · {len(veri.diziler)} çift · {len(veri):,} bar · ısınma {isinma} · "
        f"hipotez {sira} · maliyet modeli {len(ayar.maliyetler)} · "
        f"finansman {len(ayar.finansmanlar)} · takvim {ayar.takvim.kimlik}"
    )
    sonuc = ed.degerlendir(
        sinif, secenekler, maliyet, veri, secim=ed.KESITSEL_SECIM, ilerleme=ilerleme,
        rejim_kiyasi=REJIM_KIYASI, isinma_bar=isinma,
    )
    ins, oos, tam, _ = ed.pencereler(veri, isinma_bar=isinma)

    ilerleme("kıyas (in-sample, OOS, tam)")
    kiyaslar: dict[str, dict[str, Any]] = {}
    for ad, pencere in (("in_sample", ins), ("out_of_sample", oos), ("tam", tam)):
        k = ed.kosu(_kiyas(), maliyet, veri, pencere)
        kiyaslar[ad] = {
            "metrikler": k.metrikler.sozluk(), "sonuc_hash": k.sonuc_hash,
            "ozet": _maliyet_ozeti(k),
            "engeller": list(k.promotion_engelleri),
        }

    detay = sonuc["detay"]
    secilen = detay["secim"].get("secilen")
    oos_ozet = is_ozet = None
    if secilen is not None:
        # Seçilen noktayı IS ve OOS'ta yeniden koştur (fill sayısı için); hash kayıtla eşit
        # olmak zorunda — determinizm kanıtı (K-009), yeni bir ölçüm değil.
        oos_tekrar = ed.kosu(sinif(**secilen), maliyet, veri, oos)
        if oos_tekrar.sonuc_hash != detay["oos"]["sonuc_hash"]:
            print("HATA: OOS tekrar koşusu kayıtla aynı hash'i vermedi (K-009)", file=sys.stderr)
            return 2
        oos_ozet = _maliyet_ozeti(oos_tekrar)
        is_tekrar = ed.kosu(sinif(**secilen), maliyet, veri, ins)
        beklenen = next(
            a["sonuc_hash"] for a in detay["tarama"]["adaylar"]
            if dict(a["parametreler"]) == secilen
        )
        if is_tekrar.sonuc_hash != beklenen:
            print("HATA: IS tekrar koşusu taramadaki hash'i vermedi (K-009)", file=sys.stderr)
            return 2
        is_ozet = _maliyet_ozeti(is_tekrar)
    oos_sharpe = sonuc["olcumler"].get("oos_sharpe")
    kiyas_oos_sharpe = kiyaslar["out_of_sample"]["metrikler"]["sharpe"]
    govde = {
        "cekilis": cekilis,
        "program": program,
        "hipotez": {"sira": sira, "kimlik": hip.kimlik, "veri_kimligi": hip.veri_sha256},
        "evren": {k: v for k, v in veri.meta.items() if k != "kalite"},
        "veri_penceresi": {
            "baslangic_ay": BASLANGIC_AY, "bitis_ay": BITIS_AY,
            "ilk_bar_utc": utc_str(int(veri.zamanlar[0])),
            "son_bar_utc": utc_str(int(veri.zamanlar[-1])),
            "bar": len(veri), "isinma_bar": isinma,
            "finansman_araligi_kaynagi": "K-101/4 (21 proxy ortak aralık 2023-11-19..2024-03-18)",
        },
        "motor": sonuc["motor"] | {
            "maliyet_modelleri": sorted({em.kimlik for em in ayar.maliyetler.values()}),
            "finansman_modelleri": sorted({sf.kimlik for sf in ayar.finansmanlar.values()}),
        },
        "kiyas": {
            "strateji": FxEvrenEsitAgirlik.ad,
            "parametreler": _kiyas().parametreler,
            **kiyaslar,
        },
        "ozet": {
            "secilen": secilen,
            "in_sample": is_ozet,
            "out_of_sample": oos_ozet,
            "kiyas_farki_oos": None if oos_ozet is None else {
                "sharpe": oos_sharpe - kiyas_oos_sharpe,
                "net_getiri": (oos_ozet["net_getiri"]
                               - kiyaslar["out_of_sample"]["ozet"]["net_getiri"]),
            },
        },
        "durma_kurali_olcumu": {
            "oos_sharpe": oos_sharpe,
            "kiyas_oos_sharpe": kiyas_oos_sharpe,
            "kiyasi_gecti": (oos_sharpe is not None and math.isfinite(oos_sharpe)
                             and oos_sharpe > kiyas_oos_sharpe),
        },
        "sonuc": sonuc,
        "git": git_durumu(KOK),
        "sure_sn": round(time.perf_counter() - basladi, 1),
        "zaman_utc": utc_str(simdi_ms()),
    }
    CIKTI.mkdir(parents=True, exist_ok=True)
    yol = CIKTI / f"{cekilis}.json"
    yol.write_text(json.dumps(_temiz(govde), ensure_ascii=False, indent=1), encoding="utf-8")
    ilerleme(f"yazıldı: {yol}")
    print(json.dumps(_temiz({
        "olcumler": sonuc["olcumler"], "ozet": govde["ozet"],
        "durma": govde["durma_kurali_olcumu"],
        "kapilar": {k: v.get("gecti") for k, v in sonuc["kapilar"]["kapilar"].items()}
        if isinstance(sonuc["kapilar"].get("kapilar"), dict) else sonuc["kapilar"],
    }), ensure_ascii=False, indent=1)[:6000])
    return 0


def durum() -> int:
    defter = hipotez_mod.HipotezDefteri()
    programlar = program_mod.ProgramDefteri()
    print(f"defter {defter.sayi()}")
    for program, adlar in FX_PROGRAMLAR.items():
        acik = programlar.acik(program)
        if acik is None:
            print(f"{program}: kapalı")
        else:
            b = programlar.butce(program, defter.tumu())
            print(f"{program}: {b['harcanan']}/{b['azami_cekilis']}")
        for ad in adlar:
            yol = CIKTI / f"{ad}.json"
            if not yol.exists():
                print(f"  {ad:28s} sonuç yok")
                continue
            d = json.loads(yol.read_text(encoding="utf-8"))["durma_kurali_olcumu"]
            print(f"  {ad:28s} oos {d['oos_sharpe']} · kıyas {d['kiyas_oos_sharpe']:.3f} · "
                  f"geçti={d['kiyasi_gecti']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    alt = ap.add_subparsers(dest="komut", required=True)
    k = alt.add_parser("kaydet")
    k.add_argument("cekilis", choices=TUM_CEKILISLER)
    k.add_argument("-g", "--gerekce", required=True)
    r = alt.add_parser("kos")
    r.add_argument("cekilis", choices=TUM_CEKILISLER)
    alt.add_parser("durum")
    a = ap.parse_args()
    if a.komut == "kaydet":
        return kaydet(a.cekilis, a.gerekce)
    if a.komut == "kos":
        return kos(a.cekilis)
    return durum()


if __name__ == "__main__":
    raise SystemExit(main())
