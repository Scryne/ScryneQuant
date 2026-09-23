"""USDⓈ-M perpetual 1m klines — arşivden, yalnız IS penceresi. **Elle çalıştırılır.** (Hat 1, veri kararı B)

    uv run python tools/faz16_perp_klines_indir.py [--semboller BTCUSDT ETHUSDT] [--timeframe 1m]

Amaç: perp bacağı slippage kalibrasyonu (K-021 yöntemi, `sq data slippage-kalibre --depo`)
için perp 1m barları. `docs/arsiv/Faz-16-Hat1-Veri-Karari-Tasarimi.md` Karar B: **BTCUSDT + ETHUSDT,
yalnız 1m, IS (2020-01 → 2025-02)**; altcoin yok; işlem için değil, maliyet kalibrasyonu için.

- Kaynak: `data.binance.vision` `data/futures/um/monthly/klines/<S>/<tf>/<S>-<tf>-YYYY-MM.zip`
  + `.CHECKSUM` (herkese açık; `exchange/binance_arsiv.HttpArsiv`, IPv4, yeniden deneme).
- Her zip `.CHECKSUM` ile doğrulanır; SHA-256'lar `<S>.kaynak.json`'a yazılır (K-009/K-056).
- **Ayrı depo** `data/turev/klines_1m/<S>/1m.parquet` — `data/market` (REST) ve `data/evren`
  (spot arşivi) ile **karışmaz** (K-056/1). Depo düzeni `ParquetDepo` ile aynı, `quality_status`
  `data/dogrulama.dogrula` ile **yeniden** hesaplanır (K-006/K-024: boşluk doldurulmaz).
- Futures kline CSV'leri spot'tan farklı olarak **başlık satırı** taşıyabilir; ilk alan sayı
  değilse başlık olarak atılır ve sayısı kaynak kaydına yazılır. Sütun düzeni spot ile aynı
  (`_CSV_ALANLARI`); `open_time` ms (µs görülürse `_ms_yap` hata verir, düzeltilmez).
- Bu araç **hiçbir getiriye bakmaz.** Yalnızca veriyi indirir.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.data.dogrulama import dogrula
from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI, HAM_PANDAS_DTYPES
from scryne_quant.exchange.binance_arsiv import (
    _CSV_ALANLARI,
    ArsivHatasi,
    HttpArsiv,
    _ms_yap,
    checksum_dogrula,
    zip_anahtarlari,
)

KOK = Path(__file__).resolve().parent.parent
DEPO = KOK / "data" / "turev" / "klines_1m"
ONEK = "data/futures/um/monthly/klines/"
_AY = re.compile(r"-(\d{4}-\d{2})\.zip$")
IS_ILK_AY, IS_SON_AY = "2020-01", "2025-02"  # IS bitişi 2025-02-16 18:00 UTC; ay dosyası tamamı iner, kesme ölçümde
VARSAYILAN_SEMBOLLER = ("BTCUSDT", "ETHUSDT")


def _csv_oku(anahtar: str, zip_bayt: bytes) -> tuple[pd.DataFrame, int]:
    with zipfile.ZipFile(io.BytesIO(zip_bayt)) as z:
        adlar = z.namelist()
        if len(adlar) != 1:
            raise ArsivHatasi(f"{anahtar}: zip tek dosya içermeli, {len(adlar)} var")
        ham = z.read(adlar[0])
    if not ham.strip():
        return pd.DataFrame({s: pd.Series(dtype=d) for s, d in HAM_PANDAS_DTYPES.items()}), 0
    baslik = 0
    ilk_alan = ham.split(b",", 1)[0].strip()
    if not ilk_alan.isdigit():
        # futures arşivinde başlık satırı: bir kez, yalnız ilk satır
        ilk_satir, _, kalan = ham.partition(b"\n")
        if ilk_satir.split(b",")[0].strip().lower() != b"open_time":
            raise ArsivHatasi(f"{anahtar}: beklenmeyen başlık/biçim: {ilk_satir[:80]!r}")
        ham, baslik = kalan, 1
    df = pd.read_csv(
        io.BytesIO(ham), header=None, names=list(_CSV_ALANLARI), usecols=list(HAM_BAR_SUTUNLARI),
        dtype={"open_time": "int64", "trades": "int64"}, float_precision="round_trip",
    )
    df["open_time"] = _ms_yap(anahtar, df["open_time"])
    for sutun, dtype in HAM_PANDAS_DTYPES.items():
        df[sutun] = df[sutun].astype(dtype)
    return df.loc[:, list(HAM_BAR_SUTUNLARI)], baslik


def sembol_indir(kaynak: HttpArsiv, depo: ParquetDepo, sembol: str, timeframe: str, paralel: int) -> dict:
    onek = f"{ONEK}{sembol}/{timeframe}/"
    _, anahtarlar = kaynak.listele(onek)
    aylar = {ay: a for ay, a in zip_anahtarlari(anahtarlar, _AY).items() if IS_ILK_AY <= ay <= IS_SON_AY}
    if not aylar:
        raise ArsivHatasi(f"{sembol}: arşivde {onek} altında IS ayı yok")

    def _bir(anahtar: str) -> tuple[str, str, pd.DataFrame, int]:
        zip_bayt = kaynak.getir(anahtar)
        if zip_bayt is None:
            raise ArsivHatasi(f"{anahtar}: listede var ama indirilemedi")
        ozet = checksum_dogrula(anahtar, zip_bayt, kaynak.getir(f"{anahtar}.CHECKSUM"))
        df, baslik = _csv_oku(anahtar, zip_bayt)
        return anahtar, ozet, df, baslik

    with ThreadPoolExecutor(max_workers=paralel) as havuz:
        inen = list(havuz.map(_bir, aylar.values()))
    dosyalar = {a: o for a, o, _, _ in inen}
    baslik_sayisi = sum(b for _, _, _, b in inen)
    ham = pd.concat([d for _, _, d, _ in inen], ignore_index=True)
    ham = ham.drop_duplicates("open_time", keep="first").sort_values("open_time").reset_index(drop=True)
    bayrakli, kalite = dogrula(ham, timeframe, sembol=sembol)
    kayit = depo.yaz(sembol, timeframe, bayrakli)
    meta = {
        "sembol": sembol, "timeframe": timeframe, "kaynak": "data.binance.vision", "onek": onek,
        "is_ay_araligi": [IS_ILK_AY, IS_SON_AY], "ay_sayisi": len(aylar), "baslik_satiri_atilan": baslik_sayisi,
        "dosyalar": dict(sorted(dosyalar.items())),
        "satir": int(len(bayrakli)), "ilk": utc_str(int(bayrakli["open_time"].iloc[0])), "son": utc_str(int(bayrakli["open_time"].iloc[-1])),
        "kalite": kalite.sozluk() if hasattr(kalite, "sozluk") else str(kalite),
        "parquet_sha256": depo.sha256(sembol, timeframe),
        "uretildi": utc_str(simdi_ms()),
        "not": "Hat 1 veri kararı B: perp slippage kalibrasyonu için; işlem verisi değil; K-056/1 ayrı depo",
    }
    (depo.yol(sembol, timeframe).parent / f"{timeframe}.kaynak.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return {k: v for k, v in meta.items() if k != "dosyalar"} | {"depo_kaydi": kayit.sozluk() if hasattr(kayit, "sozluk") else str(kayit)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semboller", nargs="+", default=list(VARSAYILAN_SEMBOLLER))
    ap.add_argument("--timeframe", default="1m")
    ap.add_argument("--paralel", type=int, default=8)
    a = ap.parse_args()
    kaynak = HttpArsiv()
    depo = ParquetDepo(DEPO)
    for s in a.semboller:
        try:
            print(json.dumps(sembol_indir(kaynak, depo, s.upper(), a.timeframe, a.paralel), ensure_ascii=False, default=str), flush=True)
        except ArsivHatasi as hata:
            print(f"{s}: HATA {hata}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
