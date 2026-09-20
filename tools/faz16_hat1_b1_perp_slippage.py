"""Hat 1 / B-1 — perp bacağı slippage kalibrasyonu, K-021 yöntemi **aynen**. Ölçüm; config'e yazmaz.

Girdi: `data/turev/klines_1m/<S>/1m.parquet` (veri kararı B, `tools/faz16_perp_klines_indir.py`).
Yöntem: `data/kalibrasyon.kalibre_et` — 1m bar-to-bar |Δclose|/close (bps), yalnız iki ucu
`ok` barlar, boşluk ötesi düşer, persentil `VARSAYILAN_PERSENTIL` (K-021: p75). Aynı fonksiyon,
aynı persentil; spot değeri perp'e **taşınmaz**, perp kendi verisinden ölçülür.

Pencereler (ikisi de raporlanır, seçim yok):
- IS: 2020-01-01 → 2025-02-16 18:00 UTC (birincil; ikinci tavan penceresi)
- Örtüşme: 2023-08-04 → 2025-02-16 18:00 UTC — spot BTC 1m (`data/market`, K-021 kalibrasyonu
  bu depodan) ile aynı tarih aralığı; spot da aynı pencerede yeniden ölçülür ki karşılaştırma
  aynı dönemde olsun. Spot'un yürürlükteki 5,30 değeri 2023-08 → 2026-09 penceresindendir ve
  değişmez.

Tarife (fee) bu betikte **yok**: repoda ve herkese açık kaynakta ölçülemedi (bkz. rapor);
`c_perp_tek_yon` bu yüzden tamamlanmaz.

Kullanım: uv run python tools/faz16_hat1_b1_perp_slippage.py
Çıktı:    runs/faz16/hat1_b1_perp_slippage.json
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from scryne_quant.common.hash import dosya_hash
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.data.kalibrasyon import VARSAYILAN_PERSENTIL, kalibre_et

IS_BITIS_MS = 1739728800000
ORTUSME_BASI_MS = 1691122620000  # spot BTC 1m ilk barı (config/maliyet.json kalibrasyon aralığı)
PERP_DEPO = Path("data/turev/klines_1m")
SPOT_DEPO = Path("data/market")


def _olc(depo: ParquetDepo, sembol: str, bas_ms: int | None, bit_ms: int) -> dict:
    df = depo.oku(sembol, "1m")
    df = df[df["open_time"] < bit_ms]
    if bas_ms is not None:
        df = df[df["open_time"] >= bas_ms]
    s = kalibre_et(df, sembol=sembol, timeframe="1m", persentil=VARSAYILAN_PERSENTIL)
    d = s.sozluk()
    return {k: d[k] for k in d if k not in ("gerekce",)}


def main() -> None:
    perp, spot = ParquetDepo(PERP_DEPO), ParquetDepo(SPOT_DEPO)
    out = {
        "olcum": "Hat 1 / B-1 — perp 1m slippage kalibrasyonu (K-021 yöntemi aynen, p75)",
        "tur": "ölçüm; config/maliyet.json'a yazılmadı; tarife ölçülemedi; seçim yok",
        "uretim_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "yontem": "data/kalibrasyon.kalibre_et: |close[t]-close[t-1]|/close[t-1]·1e4, iki ucu ok barlar, persentil " + str(VARSAYILAN_PERSENTIL),
        "veri": {
            s: {"perp_parquet_sha256": perp.sha256(s, "1m"), "kaynak_json": json.loads((PERP_DEPO / s / "1m.kaynak.json").read_text(encoding="utf-8")) | {"dosyalar": "<62 zip SHA-256, dosyada>"}}
            for s in ("BTCUSDT", "ETHUSDT")
        },
        "maliyet_json_sha256": dosya_hash("config/maliyet.json"),
        "perp_is": {s: _olc(perp, s, None, IS_BITIS_MS) for s in ("BTCUSDT", "ETHUSDT")},
        "perp_ortusme_2023_08_2025_02": {s: _olc(perp, s, ORTUSME_BASI_MS, IS_BITIS_MS) for s in ("BTCUSDT", "ETHUSDT")},
        "spot_btc_ortusme_2023_08_2025_02": _olc(spot, "BTCUSDT", ORTUSME_BASI_MS, IS_BITIS_MS),
        "spot_btc_yururlukteki_config": json.loads(Path("config/maliyet.json").read_text(encoding="utf-8"))["slippage_bps"],
        "tarife": "ÖLÇÜLEMEDİ — herkese açık ücret sayfası JS ile üretiliyor (içerik yok); destek makalesi yalnız 'varsayımsal örnek' veriyor (kullanılmadı); imzalı uç vadeli yetkili anahtar ister (K-066 sınırı içinde denenmedi)",
    }
    for s in ("BTCUSDT", "ETHUSDT"):
        for k in ("veri",):
            out[k][s]["kaynak_json"].pop("dosyalar", None)
    yol = Path("runs/faz16/hat1_b1_perp_slippage.json")
    yol.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    icerik = {k: v for k, v in out.items() if k != "uretim_utc"}
    print("icerik_sha256:", __import__("hashlib").sha256(json.dumps(icerik, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest())
    for ad in ("perp_is", "perp_ortusme_2023_08_2025_02"):
        for s, v in out[ad].items():
            print(f"{ad:32} {s:8} p75={v['deger_bps']:.4f} bps  bar={v['kullanilan_bar']}  p50={v['dagilim_bps']['p50']:.3f} p95={v['dagilim_bps']['p95']:.3f}")
    v = out["spot_btc_ortusme_2023_08_2025_02"]
    print(f"{'spot_btc_ortusme':32} {'BTCUSDT':8} p75={v['deger_bps']:.4f} bps  bar={v['kullanilan_bar']}  p50={v['dagilim_bps']['p50']:.3f} p95={v['dagilim_bps']['p95']:.3f}")
    print("spot config (değişmedi):", out["spot_btc_yururlukteki_config"])


if __name__ == "__main__":
    main()
