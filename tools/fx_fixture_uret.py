"""Gerçek FXCM deposundan küçük, deterministik FX test fixture'ı üretir. (K-096, R4 Paket 4)

    uv run python tools/fx_fixture_uret.py [--depo data/fx] [--pair EURUSD] [--haftalar 2024-2,…]

Çıktı `tests/fixtures/fx/`: `<PAIR>/1h.parquet` + `1h.kaynak.json` (`FxDepo` ile aynı yazım —
zstd/3, sabit row group, sıralı; iki koşu bayt-aynı), `_evren/<kural12>.parquet` + `.json`
(`fx_evren.pit_tablo` ile aynı sütunlar; yalnız seçilen çift ve haftalar). Manifestodaki hafta
kayıtları gerçek depodan **kopyalanır** (dosya sha'ları), uydurulmaz. Bu betik `scryne_quant`ı
import eder — fixture bağımsız referans değil, gerçek verinin dilimidir; bağımsız doğrulama
testin içindeki `Decimal` hesabıyla yapılır.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scryne_quant.data import fx as fx_mod
from scryne_quant.data import fx_evren

KOK = Path(__file__).resolve().parents[1]
HEDEF = KOK / "tests" / "fixtures" / "fx"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depo", default=str(fx_mod.VARSAYILAN_DEPO))
    ap.add_argument("--pair", default="EURUSD")
    ap.add_argument("--haftalar", default=",".join(f"2024-{h}" for h in range(2, 9)))
    args = ap.parse_args()

    haftalar = tuple(args.haftalar.split(","))
    kaynak = fx_mod.FxDepo(args.depo)
    manifesto = kaynak.manifesto(args.pair)
    if manifesto is None:
        raise SystemExit(f"{args.pair}: kaynak depoda manifesto yok")
    eksik = [h for h in haftalar if manifesto["haftalar"].get(h, {}).get("durum") != "var"]
    if eksik:
        raise SystemExit(f"{args.pair}: kaynak depoda olmayan hafta(lar): {eksik}")
    df = kaynak.oku(args.pair)
    secilen = {h: dict(manifesto["haftalar"][h]) for h in haftalar}
    alt = min(int(h["ilk_ms"]) for h in secilen.values())
    ust = max(int(h["son_ms"]) for h in secilen.values())
    dilim = df[(df["open_time"] >= alt) & (df["open_time"] <= ust)]

    hedef = fx_mod.FxDepo(HEDEF)
    kayit = hedef._yaz(args.pair, dilim, secilen, None)
    kural = fx_evren.FxEvrenKurali(ciftler=(args.pair,))
    tablo = fx_evren.pit_tablo(kural, {args.pair: dict.fromkeys(haftalar, True)})
    dizin = HEDEF / fx_evren.EVREN_DIZINI
    dizin.mkdir(parents=True, exist_ok=True)
    ad = kural.kimlik[:12]
    tablo.to_parquet(dizin / f"{ad}.parquet", index=False)
    meta = {
        "kural": kural.sozluk(),
        "kural_kimlik": kural.kimlik,
        "tablo": (dizin / f"{ad}.parquet").relative_to(KOK).as_posix(),
        "tablo_hash": fx_evren.tablo_hash(tablo),
        "satir": int(len(tablo)),
        "uye_satir": int(tablo["uye"].sum()),
        "kaynak_depo": {"pair": args.pair, "sha256": manifesto.get("sha256"), "haftalar": haftalar},
    }
    (dizin / f"{ad}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(json.dumps({"bar": kayit.bar_sayisi, "sha256": kayit.sha256, "tablo": ad}, indent=1))


if __name__ == "__main__":
    main()
