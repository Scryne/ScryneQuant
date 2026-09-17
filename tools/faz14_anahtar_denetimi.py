"""Binance API anahtarının yetkilerini denetler — Faz 14 bitti kriteri. (K-062/5, K-066)

    uv run python tools/faz14_anahtar_denetimi.py

Kriter: *"Anahtar ayrımı ve çekim yetkisinin kapalı olduğu ekran görüntüsü/çıktıyla kayıtlı."*

- Tek çağrı: `GET /sapi/v1/account/apiRestrictions` (imzalı, **salt okunur**; emir, transfer,
  bakiye değişikliği yok).
- Anahtar ve sır `.env`den okunur (`BINANCE_API_KEY`, `BINANCE_API_SECRET`) ve **hiçbir çıktıya
  yazılmaz**. Raporda yalnızca anahtarın SHA-256 parmak izinin ilk 12 karakteri durur: hangi
  anahtarın denetlendiği ayırt edilebilsin, anahtarın kendisi çıkarılamasın.
- Geçme koşulları sayısal ve sabit (K-018): çekim kapalı, iç transfer kapalı, evrensel transfer
  kapalı. İşlem yetkisi **ayrıca** raporlanır: bu projede okuma anahtarı ile işlem anahtarı
  ayrı olmalı; işlem yetkili bir anahtar yalnızca Faz 8'de, IP kısıtlı ve elle onayla gelir.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from scryne_quant.common.zaman import simdi_ms, utc_str

KOK = Path(__file__).resolve().parent.parent
UC = "https://api.binance.com/sapi/v1/account/apiRestrictions"


def _env(ad: str) -> str:
    for satir in (KOK / ".env").read_text(encoding="utf-8").splitlines():
        if satir.startswith(f"{ad}="):
            deger = satir.split("=", 1)[1].strip().strip('"').strip("'")
            if deger:
                return deger
    raise SystemExit(f"{ad} .env'de yok")


def main() -> int:
    anahtar, sir = _env("BINANCE_API_KEY"), _env("BINANCE_API_SECRET")
    params = {"timestamp": int(time.time() * 1000), "recvWindow": 10_000}
    sorgu = urlencode(params)
    imza = hmac.new(sir.encode(), sorgu.encode(), hashlib.sha256).hexdigest()
    try:
        y = requests.get(f"{UC}?{sorgu}&signature={imza}",
                         headers={"X-MBX-APIKEY": anahtar}, timeout=20)
    except requests.RequestException as hata:
        # İstisna metni URL'yi taşır; imza sır değildir ama yine de yazdırılmıyor.
        raise SystemExit(f"istek başarısız: {type(hata).__name__}") from None
    if y.status_code != 200:
        raise SystemExit(f"borsa {y.status_code}: {y.text[:200]}")
    k = y.json()

    kapali_olmali = ("enableWithdrawals", "enableInternalTransfer", "permitsUniversalTransfer")
    islem = ("enableSpotAndMarginTrading", "enableMargin", "enableFutures",
             "enableVanillaOptions", "enablePortfolioMarginTrading", "enableFixApiTrade")
    rapor = {
        "zaman": utc_str(simdi_ms()),
        "uc": UC,
        "anahtar_parmak_izi": hashlib.sha256(anahtar.encode()).hexdigest()[:12],
        "yetkiler": k,
        "kontroller": {
            **{f"{a}_kapali": k.get(a) is False for a in kapali_olmali},
            "okuma_acik": k.get("enableReading") is True,
            "islem_yetkisi_yok": not any(k.get(a) for a in islem),
            "ip_kisitli": k.get("ipRestrict") is True,
        },
    }
    kont = rapor["kontroller"]
    rapor["cekim_kapali"] = all(kont[f"{a}_kapali"] for a in kapali_olmali)
    rapor["salt_okunur_anahtar"] = rapor["cekim_kapali"] and kont["islem_yetkisi_yok"]
    yol = KOK / "runs" / "faz14" / f"anahtar-denetimi-{rapor['zaman'][:10]}.json"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(rapor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rapor, ensure_ascii=False, indent=2))
    print(f"rapor: {yol}")
    return 0 if rapor["cekim_kapali"] else 1


if __name__ == "__main__":
    sys.exit(main())
