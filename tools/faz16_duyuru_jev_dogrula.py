"""Kural tabanlı duyuru ayrıştırmasının **kalite ölçümü** — Jev ile. (Faz 16, K-067/3)

    uv run python tools/faz16_duyuru_jev_dogrula.py --ornek 80

Kural (`faz16_duyuru_ayristir.py`) geçmişi sızıntısız sınıflandırıyor ama kaba: başlık ve
gövdenin ilk satırlarındaki kalıplara bakıyor. Bu araç kuralın **ne kadar isabetli** olduğunu
ölçer: rastgele örneklenen duyurularda Jev'in tipli yargısıyla kuralın etiketini karşılaştırır.

**Bu bir özellik değil, bir ölçümdür.** Jev'in buradaki çıktısı hiçbir stratejiye, hiçbir
backtest'e girmez; yalnızca "kural yeterince iyi mi, nerede yanılıyor" sorusunu yanıtlar
(K-067: Jev sinyal üretmez; geçmiş dönem türetimi kapıya giremez).

Rapor `runs/faz16/duyuru-jev-dogrulama-<zaman>.json`: uyum oranı, kategori bazında kayma,
uyuşmayan örnekler (elle okunacak), model sürümü ve soru hash'i.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

from scryne_quant.common.zaman import simdi_ms, utc_str

KOK = Path(__file__).resolve().parent.parent
DEPO = KOK / "data" / "duyuru"
CIKTI_KOK = KOK / "runs" / "faz16"

#: Çözülmüş sürüm; `jev-latest` zamanla kayar (K-061/3 kalıbı).
MODEL = "jev-1.13.0"
#: Modele giden gövde payı. Duyurunun ilk paragrafları olayı taşır; gerisi standart uyarı.
GOVDE_KARAKTER = 1200

KATEGORILER: dict[str, dict[str, Any]] = {
    "spot_listeleme": {"what": "Spot piyasada yeni parite/token islem acilir ya da yeni islem "
                               "cifti eklenir."},
    "spot_kaldirma": {"what": "Spot piyasada mevcut pariteler islemden kaldirilir."},
    "delist": {"what": "Token/parite borsadan tamamen cikarilir (cekme dahil kapanir)."},
    "marjin_ekleme": {"what": "Marjin (izole/capraz) islemine yeni parite eklenir."},
    "marjin_kaldirma": {"what": "Marjin isleminden parite kaldirilir."},
    "teminat_ekleme": {"what": "Bir varlik teminat (collateral) olarak kabul edilmeye baslar."},
    "teminat_kaldirma": {"what": "Bir varlik teminat olmaktan cikarilir."},
    "vadeli_listeleme": {"what": "Vadeli (futures) piyasada yeni sozlesme acilir."},
    "vadeli_delist": {"what": "Vadeli sozlesme kapatilir ya da kaldirilir."},
    "diger": {"what": "Yukaridakilerin hicbiri: kural degisikligi, kampanya, bakim, bilgi "
                      "notu.", "not_for": "Erisimi artiran ya da azaltan somut bir islem "
                                          "degisikligi varsa o kategori secilir."},
}
_GOREV = ("Binance duyurusunun ne yaptigini sec: hangi islem erisimi degisiyor? Basliga ve "
          "gövdenin ilk paragraflarina bak; duyurunun ASIL eylemine karar ver, yan "
          "cumlelerdeki ornek ya da uyarilara degil.")
_YON = ("Bu duyuru, adi gecen token(lar)in Binance'te islem gorebilirligini ARTIRIYOR mu? "
        "Artis: yeni parite, yeni marjin/vadeli imkani, teminat kabulu. Azalis: kaldirma, "
        "delist, teminatlikta cikarma. Yalnizca bilgi veren duyuruda cevap hayir.")
SORU_SHA256 = hashlib.sha256(
    json.dumps({"gorev": _GOREV, "yon": _YON, "kategoriler": KATEGORILER},
               ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _istemci() -> Any:
    from typesafe_sdk import TypeSafeClient

    return TypeSafeClient()


def _sorular() -> dict[str, Any]:
    from typesafe_sdk import Choice, Noul

    return {
        "olay": Choice(instructions=_GOREV, criteria=KATEGORILER),
        "erisim_artisi": Noul(instructions=_YON),
    }


def _tek(istemci: Any, satir: dict[str, Any]) -> dict[str, Any]:
    yanit = istemci.system_one(
        state={"baslik": satir["baslik"], "govde": satir["govde"]},
        questions=_sorular(), model=MODEL,
    )
    if yanit.model != MODEL:
        raise SystemExit(f"istenen model {MODEL}, çözülen {yanit.model}")
    secim = yanit.choices["olay"]
    noul = yanit.nouls["erisim_artisi"]
    return {
        "duyuru_id": satir["duyuru_id"],
        "baslik": satir["baslik"],
        "kural_olay": satir["kural_olay"],
        "kural_yon": satir["kural_yon"],
        "jev_olay": secim.choice,
        "jev_guven": float(secim.confidence),
        "jev_olasiliklar": {k: float(v) for k, v in secim.probabilities.items()},
        # `NoulAnswer.noul` bir olasılık (float), ikili bir bayrak değil (SDK 0.6.0).
        "jev_erisim_artisi": float(noul.noul),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ornek", type=int, default=80)
    ap.add_argument("--tohum", type=int, default=16)
    ap.add_argument("--isci", type=int, default=6)
    a = ap.parse_args()

    duyuru = pd.read_parquet(DEPO / "duyurular.parquet")
    govde = pd.read_parquet(DEPO / "govdeler.parquet")[["id", "metin"]]
    olay = pd.read_parquet(DEPO / "olaylar.parquet")
    ilk_olay = olay.drop_duplicates("duyuru_id").set_index("duyuru_id")[["olay", "yon"]]
    havuz = duyuru.merge(govde, on="id").sample(
        n=min(a.ornek, len(govde)), random_state=a.tohum)
    satirlar = [{
        "duyuru_id": int(r.id), "baslik": str(r.baslik),
        "govde": str(r.metin)[:GOVDE_KARAKTER],
        "kural_olay": str(ilk_olay["olay"].get(int(r.id), "diger")),
        "kural_yon": str(ilk_olay["yon"].get(int(r.id), "")),
    } for r in havuz.itertuples()]

    istemci = _istemci()
    with istemci, ThreadPoolExecutor(a.isci) as h:
        sonuclar = list(h.map(lambda s: _tek(istemci, s), satirlar))

    df = pd.DataFrame(sonuclar)
    df["olay_uyum"] = df["kural_olay"] == df["jev_olay"]
    df["yon_uyum"] = ((df["kural_yon"] == "erisim_artisi") == (df["jev_erisim_artisi"] >= 0.5))
    govde_rapor = {
        "uretildi": utc_str(simdi_ms()),
        "model": MODEL,
        "soru_sha256": SORU_SHA256,
        "ornek": len(df),
        "olay_uyum_orani": float(df["olay_uyum"].mean()),
        "yon_uyum_orani": float(df["yon_uyum"].mean()),
        "yuksek_guvende_uyum": float(df.loc[df["jev_guven"] >= 0.8, "olay_uyum"].mean())
        if (df["jev_guven"] >= 0.8).any() else None,
        "kural_olay_dagilimi": df["kural_olay"].value_counts().to_dict(),
        "jev_olay_dagilimi": df["jev_olay"].value_counts().to_dict(),
        "uyusmayanlar": df[~df["olay_uyum"]].head(25).to_dict("records"),
        "not": "Bu ölçüm bir özellik değildir; Jev çıktısı hiçbir backtest'e girmez (K-067).",
    }
    CIKTI_KOK.mkdir(parents=True, exist_ok=True)
    yol = CIKTI_KOK / f"duyuru-jev-dogrulama-{simdi_ms()}.json"
    yol.write_text(json.dumps(govde_rapor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in govde_rapor.items() if k != "uyusmayanlar"},
                     ensure_ascii=False, indent=2))
    print(f"rapor: {yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
