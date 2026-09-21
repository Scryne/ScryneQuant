"""R6: h54 (`fx_kesitsel_ters`, 240 bar / n=10) doğrulama turu — sabit nokta, yeni pencere. (K-103)

    python tools/r6_h54_tekrar.py [W1 W2 W3]

**Ne yapar:** h54'ün seçilen noktasını (pencere 240, haftalık dengeleme, 0,2 brüt, eşit ağırlık)
K-101 finansman aralıklarından türetilen zaman pencerelerinde **seçim yapmadan** koşturur ve her
pencerede kontrolle (`fx_evren_esit_agirlik`, K-099) karşılaştırır. Parametre araması yok: 12
noktalı ızgara yalnız PBO ve pertürbasyon **teşhisi** için koşulur, seçim için değil.

**Pencereler K-101'den türetilir** (elle seçilmez): bir pencerenin evreni, finansman modeli
pencerenin sonuna kadar geçerli olan çiftlerdir (`config/finansman/fxcm-<pair>.json` `aralik`).
Aralıklar ay ortasında bittiği için W3 haftalık kesim ister (`fx_veri_kur(bitis_pazar=)`).

| Pencere | Evren | Ölçüm | Neden |
|---|---|---|---|
| W1 | 21 çift | 2023-11-19..2024-02-29 | h54'ün kendi penceresi (referans, K-102) |
| W2 | 10 çift (aralık ≥ 2024-06-05) | 2024-03-01..2024-05-31 | JPY/CHF çiftleri 03-19/21'de düşer |
| W3 | 4 çift (aralık ≥ 2024-08-01) | 2024-06-01..2024-07-26 | son hafta Pazar 07-21 (08-01 hariç) |

**Kural 3'ten tek sapma, yazılı:** `azami_enstruman` alt evrende **oranla** ölçeklenir
(`round(10/21 × U)`: W2 5, W3 2). n=10'u 10 çiftlik evrende sabit tutmak "hepsini taşı" = kontrol
demek olurdu; ölçmeye değer bir şey kalmazdı. Sinyal (240 bar ters dönüş), dengeleme, brüt ve
seçim payı (~%48) sabit. Teşhis ızgarasının n ekseni de aynı oranlarla (3/21, 5/21, 10/21).

**Isınma pencere öncesinden:** W2/W3'te depo geriye gidiyor (Şubat/Mayıs barları); ısınma ölçüme
girmez (K-101 denetimi ısınmayı dışarıda tutar). W1'de depo 11-19'da başlar: ısınma verinin içinden.

**Karar ölçütü, koşudan önce yazıldı (K-039):** h54 W1'de kontrolü **IS'te de OOS'ta da** net
getiride geçti (IS −0,071 % vs −0,106 %; OOS +0,248 % vs +0,208 %). "Aynı yön" = yeni pencerede
hem IS hem OOS net benchmark farkı > 0. W2 **ve** W3'te aynı yön → "araştırmaya devam adayı";
herhangi birinde değilse → "elendi". Sharpe ölçüt değil (`yillik_anlamli` taşınır). Kapılar
(`asgari_islem`, `pbo`, pertürbasyon) ölçülür, küçültülmez, zorlanmaz; promotion yok.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r5_fx_kos import DEPO, TABLO, _maliyet_ozeti, _temiz  # noqa: E402

from scryne_quant.backtest.metrikler import bar_yili  # noqa: E402
from scryne_quant.common import finansman as finansman_mod  # noqa: E402
from scryne_quant.common import maliyet as maliyet_mod  # noqa: E402
from scryne_quant.common.hash import git_durumu  # noqa: E402
from scryne_quant.common.zaman import simdi_ms, timeframe_ms, utc_str  # noqa: E402
from scryne_quant.research import evren_dayaniklilik as day_mod  # noqa: E402
from scryne_quant.research import evren_degerlendirme as ed  # noqa: E402
from scryne_quant.research import evren_kosu, kapilar_v2  # noqa: E402
from scryne_quant.research import pbo as pbo_mod  # noqa: E402
from scryne_quant.research import perturbasyon as pert_mod  # noqa: E402
from scryne_quant.research import rejim as rejim_mod  # noqa: E402
from scryne_quant.research.izgaralar import FX_HAFTALIK, SABIT_MARUZIYET  # noqa: E402
from scryne_quant.research.tarama import ASGARI_ISLEM  # noqa: E402
from scryne_quant.strategy.kutuphane import FxEvrenEsitAgirlik  # noqa: E402
from scryne_quant.strategy.kutuphane.kesitsel import KesitselTers  # noqa: E402

KOK = Path(__file__).resolve().parent.parent
CIKTI = KOK / "runs" / "fx"
H54_PENCERE = 240
H54_N = 10
H54_EVREN = 21
ISINMA = H54_PENCERE + 2
#: Yükleyiciye verilen ısınma **duvar saati** cinsinden (hafta sonu boşluğu ızgarada yok):
#: 242 seans barı ≈ 10 takvim günü + hafta sonu; 400 saat fazlasıyla yeter, fazlası ölçüme girmez.
ISINMA_YUKLEME = 400
ORANLAR = (3 / 21, 5 / 21, 10 / 21)
PENCERELER: dict[str, dict[str, Any]] = {
    "W1": {"baslangic_ay": "2023-11", "bitis_ay": "2024-02", "bitis_pazar": None,
           "gecerli_bitis": "2024-03-18"},
    "W2": {"baslangic_ay": "2024-03", "bitis_ay": "2024-05", "bitis_pazar": None,
           "gecerli_bitis": "2024-06-05"},
    "W3": {"baslangic_ay": "2024-06", "bitis_ay": "2024-07", "bitis_pazar": "2024-07-21",
           "gecerli_bitis": "2024-08-01"},
}


def _gecerli_ciftler(bitis: str) -> list[str]:
    """Finansman aralığı `bitis`e (dahil) kadar geçerli çiftler — K-101 dosyalarından."""
    katalog = finansman_mod.FinansmanKatalogu()
    out = []
    for yol in sorted((KOK / "config" / "finansman").glob("fxcm-*.json")):
        pair = yol.stem.split("-", 1)[1].upper()
        model = katalog.coz(yol.stem)
        _, bit = str(model.kaynak.aralik).split("..")
        if bit >= bitis:
            out.append(pair)
    return out


def _n(u: int) -> int:
    return max(1, round(H54_N / H54_EVREN * u))


def _izgara(u: int) -> dict[str, Any]:
    return {
        "pencere": (24, 48, 120, 240),
        "azami_enstruman": tuple(sorted({max(1, round(o * u)) for o in ORANLAR})),
        "yeniden_dengele_bar": (FX_HAFTALIK,),
        "hedef_brut": (SABIT_MARUZIYET,),
    }


def pencere_kos(ad: str) -> dict[str, Any]:
    ayar_p = PENCERELER[ad]
    basladi = time.perf_counter()
    ciftler = _gecerli_ciftler(ayar_p["gecerli_bitis"])
    veri = evren_kosu.fx_veri_kur(
        TABLO, depo_kok=DEPO, isinma_bar=ISINMA_YUKLEME,
        baslangic_ay=ayar_p["baslangic_ay"], bitis_ay=ayar_p["bitis_ay"],
        bitis_pazar=ayar_p["bitis_pazar"], semboller=ciftler, azami_sembol=30,
    )
    u = len(veri.diziler)
    ayar = ed.motor_ayarlari(veri)
    assert ayar.coklu_model and ayar.finansmanlar and ayar.takvim is not None
    assert set(ayar.maliyetler) == set(ayar.finansmanlar) == set(veri.diziler)
    maliyet = maliyet_mod.yukle()
    ins, oos, tam, _ = ed.pencereler(veri, isinma_bar=ISINMA)
    sabit = {"pencere": H54_PENCERE, "azami_enstruman": _n(u),
             "yeniden_dengele_bar": FX_HAFTALIK, "hedef_brut": SABIT_MARUZIYET}
    izg = _izgara(u)
    assert sabit["azami_enstruman"] in izg["azami_enstruman"]
    print(f"[{ad}] {u} çift · {len(veri):,} bar · ısınma {ins.baslangic} · IS {ins.uzunluk} / "
          f"OOS {oos.uzunluk} · n {sabit['azami_enstruman']} · ızgara n {izg['azami_enstruman']}",
          flush=True)

    # --- sabit nokta: IS, OOS, tam (seçim yok)
    is_s = ed.kosu(KesitselTers(**sabit), maliyet, veri, ins)
    oos_s = ed.kosu(KesitselTers(**sabit), maliyet, veri, oos)
    tam_s = ed.kosu(KesitselTers(**sabit), maliyet, veri, tam)

    # --- kontrol: evrenin tamamı, aynı brüt, aynı dengeleme
    def kontrol() -> FxEvrenEsitAgirlik:
        return FxEvrenEsitAgirlik(yeniden_dengele_bar=FX_HAFTALIK, azami_enstruman=u,
                                  hedef_brut=SABIT_MARUZIYET)
    k_is = ed.kosu(kontrol(), maliyet, veri, ins)
    k_oos = ed.kosu(kontrol(), maliyet, veri, oos)
    k_tam = ed.kosu(kontrol(), maliyet, veri, tam)

    # --- teşhis: IS ızgarası → pertürbasyon (sabit noktanın komşuları), tam ızgara → PBO
    tarama_is, _ = ed.tara(KesitselTers, izg, maliyet, veri, ins, asgari_islem=ASGARI_ISLEM)
    aday = next(a for a in tarama_is.adaylar if a.sozluk_parametreler == sabit)
    assert aday.sonuc_hash == is_s.sonuc_hash  # aynı nokta, aynı koşu (K-009)
    try:
        pert = pert_mod.olc(tarama_is, aday)
        pert_dusus: float | None = pert.dusus
        pert_detay: dict[str, Any] = pert.sozluk()
    except pert_mod.PerturbasyonHatasi as hata:  # IS'te geçerli aday yok (islem < 30)
        pert_dusus, pert_detay = None, {"olculemedi": str(hata)}
    tam_tarama, tam_sonuclar = ed.tara(KesitselTers, izg, maliyet, veri, tam,
                                       asgari_islem=ASGARI_ISLEM)
    satirlar = [ed._getiriler(s) for a, s in zip(tam_tarama.adaylar, tam_sonuclar, strict=True)
                if a.gecerli]
    yil_bar = bar_yili(timeframe_ms(veri.timeframe))
    try:
        if len(satirlar) < 2:
            raise pbo_mod.PboHatasi(f"{len(satirlar)} geçerli aday: PBO ölçülemez")
        pbo_s = pbo_mod.cscv(np.vstack(satirlar), yil_bar=yil_bar)
        pbo_deger: float | None = pbo_s.pbo
        pbo_detay: dict[str, Any] = pbo_s.sozluk()
    except pbo_mod.PboHatasi as hata:
        pbo_deger, pbo_detay = None, {"olculemedi": str(hata)}

    # --- evren dayanıklılığı (OOS), stres (tam), rejim (OOS; kalibre değil)
    day = day_mod.olc(
        oos_s, lambda cikar: ed.kosu(KesitselTers(**sabit), maliyet, veri, oos, cikarilanlar=cikar),
        k=1,
    )
    st = ed.stres(lambda: KesitselTers(**sabit), maliyet, veri, tam)
    rejim_kiyasi = next(s for s in ("EURUSD", "GBPUSD") if s in veri.diziler)
    kapanis = np.asarray(veri.diziler[rejim_kiyasi]["close"], dtype=np.float64)
    pb = rejim_mod.pencere_bar(timeframe_ms(veri.timeframe))
    etiket = rejim_mod.etiketle(kapanis[oos.dilim()], pencere=pb)
    rej = rejim_mod.olc(oos_s.ozkaynak, etiket[oos.olcum_baslangici:], yil_bar=yil_bar)

    m_is, m_oos = is_s.metrikler, oos_s.metrikler
    olcumler = {
        "perturbasyon_dusus": pert_dusus,
        "oos_sharpe": m_oos.sharpe,
        "oos_getiri": m_oos.toplam_getiri,
        "oos_islem": m_oos.islem_sayisi,
        "oos_max_drawdown": m_oos.max_drawdown,
        "is_sharpe": m_is.sharpe,
        "oos_is_orani": (m_oos.sharpe / m_is.sharpe) if m_is.sharpe > 0 else float("nan"),
        "plato_orani": tarama_is.ust_yuzde_plato(),
        "en_kotu_rejim_sharpe": rej.en_kotu_sharpe,
        "evren_dayaniklilik_orani": day.oran,
        "stres_bozulma": st.bozulma(),
        "pbo": pbo_deger,
    }
    kapi = kapilar_v2.butun_kapilar(KesitselTers.ad, olcumler,
                                    mutlak_engeller=list(oos_s.promotion_engelleri))

    def ozet(s: Any) -> dict[str, Any]:
        return _maliyet_ozeti(s) | {"yillik_anlamli": s.metrikler.yillik_anlamli,
                                    "sonuc_hash": s.sonuc_hash}

    h_is, h_oos, h_tam = ozet(is_s), ozet(oos_s), ozet(tam_s)
    c_is, c_oos, c_tam = ozet(k_is), ozet(k_oos), ozet(k_tam)
    fark = {p: {"net_getiri_pp": (h["net_getiri"] - c["net_getiri"]) * 100,
                "net_usd": h["net_usd"] - c["net_usd"]}
            for p, h, c in (("in_sample", h_is, c_is), ("out_of_sample", h_oos, c_oos),
                            ("tam", h_tam, c_tam))}
    ayni_yon = fark["in_sample"]["net_usd"] > 0 and fark["out_of_sample"]["net_usd"] > 0
    z = veri.zamanlar
    govde = {
        "pencere": ad,
        "h54": {"sabit": sabit, "sinyal": "kesitsel_ters", "kaynak": "K-102 h54 seçilen nokta"},
        "evren": {"cift": sorted(veri.diziler), "sayi": u, "gecerli_bitis": ayar_p["gecerli_bitis"],
                  "alt_evren": veri.meta.get("alt_evren"), "kural_kimlik": veri.kural_kimligi},
        "zaman": {
            "ilk_bar_utc": utc_str(int(z[0])),
            "olcum_baslangici_utc": utc_str(int(z[ins.baslangic])),
            "is_bitis_utc": utc_str(int(z[ins.bitis - 1])),
            "oos_baslangic_utc": utc_str(int(z[oos.baslangic])),
            "son_bar_utc": utc_str(int(z[-1])), "bar": len(veri), "isinma_bar": ins.baslangic,
            "is_bar": ins.uzunluk, "oos_bar": oos.uzunluk,
            "oos_gun": oos.uzunluk * timeframe_ms(veri.timeframe) / 86_400_000,
        },
        "motor": {"maliyet_modelleri": len(ayar.maliyetler),
                  "finansman_modelleri": len(ayar.finansmanlar),
                  "takvim": ayar.takvim.kimlik, "rejim_kiyasi": rejim_kiyasi},
        "h54_sonuc": {"in_sample": h_is, "out_of_sample": h_oos, "tam": h_tam},
        "kontrol": {"strateji": FxEvrenEsitAgirlik.ad, "azami_enstruman": u,
                    "hedef_brut": SABIT_MARUZIYET,
                    "in_sample": c_is, "out_of_sample": c_oos, "tam": c_tam},
        "benchmark_farki": fark,
        "ayni_yon": ayni_yon,
        "teshis": {
            "izgara": izg, "olcumler": olcumler, "kapilar": kapi.sozluk(),
            "perturbasyon": pert_detay, "pbo": pbo_detay, "evren_dayanikliligi": day.sozluk(),
            "stres": st.sozluk(), "rejim": rej.sozluk() | {"pencere": pb, "kiyas": rejim_kiyasi},
            "is_tarama": tarama_is.sozluk(), "tam_tarama": tam_tarama.sozluk(),
        },
        "git": git_durumu(KOK),
        "sure_sn": round(time.perf_counter() - basladi, 1),
        "zaman_utc": utc_str(simdi_ms()),
    }
    CIKTI.mkdir(parents=True, exist_ok=True)
    yol = CIKTI / f"h54-tekrar-{ad}.json"
    yol.write_text(json.dumps(_temiz(govde), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{ad}] yazıldı {yol} ({govde['sure_sn']} s)", flush=True)
    return govde


def _satir(g: dict[str, Any]) -> str:
    h, c, f = g["h54_sonuc"], g["kontrol"], g["benchmark_farki"]
    out = [f"{g['pencere']}: {g['evren']['sayi']} çift, n={g['h54']['sabit']['azami_enstruman']}, "
           f"{g['zaman']['olcum_baslangici_utc'][:10]}..{g['zaman']['son_bar_utc'][:10]} "
           f"(IS {g['zaman']['is_bar']} / OOS {g['zaman']['oos_bar']} bar, "
           f"OOS {g['zaman']['oos_gun']:.1f} gün)"]
    for p in ("in_sample", "out_of_sample"):
        hh, cc = h[p], c[p]
        out.append(
            f"  {p:14s} h54 net {hh['net_usd']:+7.2f} ({hh['net_getiri']*100:+.3f}%) "
            f"brüt {hh['brut_usd']:+7.2f} maliyet {hh['maliyet']['toplam']:.2f} "
            f"tur/fill {hh['islem_sayisi']}/{hh['fill_sayisi']} | "
            f"kontrol net {cc['net_usd']:+7.2f} ({cc['net_getiri']*100:+.3f}%) | "
            f"fark {f[p]['net_usd']:+.2f} USD "
            f"({f[p]['net_getiri_pp']:+.3f} pp) | yillik_anlamli {hh['yillik_anlamli']}"
        )
    k = g["teshis"]["kapilar"]["kapilar"]
    pk = k["parametre_perturbasyonu"]
    out.append(f"  kapılar: asgari_islem {k['asgari_islem']['deger']} "
               f"({k['asgari_islem']['gecti']}), pbo {k['pbo']['deger']} ({k['pbo']['gecti']}), "
               f"pertürbasyon {pk['deger']} ({pk['gecti']}) · aynı yön: {g['ayni_yon']}")
    return "\n".join(out)


def main(adlar: list[str]) -> int:
    sonuclar = [pencere_kos(ad) for ad in (adlar or list(PENCERELER))]
    yeni = [g for g in sonuclar if g["pencere"] != "W1"]
    karar = "arastirmaya_devam_adayi" if yeni and all(g["ayni_yon"] for g in yeni) else "elendi"
    ozet = {
        "pencereler": {
            g["pencere"]: {"ayni_yon": g["ayni_yon"], "fark": g["benchmark_farki"],
                           "evren": g["evren"]["sayi"], "n": g["h54"]["sabit"]["azami_enstruman"]}
            for g in sonuclar
        },
        "karar": karar,
        "olcut": "W2 ve W3'te hem IS hem OOS net benchmark farkı > 0 (koşudan önce yazıldı)",
        "zaman_utc": utc_str(simdi_ms()),
    }
    (CIKTI / "h54-tekrar-ozet.json").write_text(
        json.dumps(_temiz(ozet), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\n".join(_satir(g) for g in sonuclar))
    print(f"KARAR: {karar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
