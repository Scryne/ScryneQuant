"""USDⓈ-M vadeli **salt okunur** iki uç: `commissionRate` ve `leverageBracket`. **Elle çalıştırılır.** (K-066 ek, 2026-09-20)

    uv run python tools/faz16_vadeli_okuma.py [--semboller BTCUSDT ETHUSDT]

K-066 ekinin kapsamı **yalnız** bu iki uçtur; işlem/emir/çekim yetkisi yok, başka uç yok.
Anahtar `BINANCE_API_KEY` / `BINANCE_API_SECRET` (ortam ya da `.env`); hiçbir çıktıya, loga,
kayda **yazılmaz**. Yanıtlar ham JSON olarak `data/turev/kurallar/` altına (gitignore) tarih
damgası ve SHA-256 ile kaydedilir; özet stdout'a. Bu araç hiçbir getiriye bakmaz, hiçbir
hesap yapmaz; fee'yi `config/maliyet.json`'a **yazmaz**.

PIT notu: kayıt anı = PIT sınırı. Bu kayıt 2020–2025 IS'i PIT yapmaz (C-2).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import requests

from scryne_quant.data.funding import ipv4_zorla

KOK = Path(__file__).resolve().parent.parent
DEPO = KOK / "data" / "turev" / "kurallar"
HOST = "https://fapi.binance.com"
UCLAR = {"commissionRate": "/fapi/v1/commissionRate", "leverageBracket": "/fapi/v1/leverageBracket"}
RECV_WINDOW_MS = 5000


def _anahtar() -> tuple[str, str]:
    k, s = os.environ.get("BINANCE_API_KEY"), os.environ.get("BINANCE_API_SECRET")
    if not (k and s):
        for satir in (KOK / ".env").read_text(encoding="utf-8").splitlines():
            if satir.startswith("BINANCE_API_KEY="):
                k = satir.split("=", 1)[1].strip().strip('"')
            elif satir.startswith("BINANCE_API_SECRET="):
                s = satir.split("=", 1)[1].strip().strip('"')
    if not (k and s):
        raise SystemExit("BINANCE_API_KEY / BINANCE_API_SECRET yok")
    return k, s


def _imzali_get(oturum: requests.Session, yol: str, params: dict, anahtar: str, sir: str) -> tuple[int, str]:
    p = {**params, "timestamp": int(time.time() * 1000), "recvWindow": RECV_WINDOW_MS}
    sorgu = urlencode(p)
    imza = hmac.new(sir.encode(), sorgu.encode(), hashlib.sha256).hexdigest()
    r = oturum.get(f"{HOST}{yol}?{sorgu}&signature={imza}", headers={"X-MBX-APIKEY": anahtar}, timeout=20)
    return r.status_code, r.text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semboller", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    a = ap.parse_args()
    anahtar, sir = _anahtar()
    ipv4_zorla()
    oturum = requests.Session()
    DEPO.mkdir(parents=True, exist_ok=True)
    damga = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    kayit = {"kayit_utc": datetime.now(UTC).isoformat(timespec="seconds"), "host": HOST, "uclar": {}, "pit_notu": "kayıt anı PIT sınırıdır; öncesi NON_PIT (C-2)"}
    hata = False
    for ad, yol in UCLAR.items():
        for s in a.semboller:
            kod, metin = _imzali_get(oturum, yol, {"symbol": s}, anahtar, sir)
            sha = hashlib.sha256(metin.encode()).hexdigest()
            dosya = DEPO / f"{ad}_{s}_{damga}.json"
            dosya.write_text(metin, encoding="utf-8")
            kayit["uclar"][f"{ad}/{s}"] = {"endpoint": yol, "http": kod, "sha256": sha, "dosya": dosya.name, "bayt": len(metin)}
            ok = kod == 200
            hata |= not ok
            print(f"{ad:16} {s:8} HTTP {kod}  sha256 {sha[:16]}  {'' if ok else metin[:120]}")
    (DEPO / f"_kayit_{damga}.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("kayıt:", DEPO / f"_kayit_{damga}.json")
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(main())
