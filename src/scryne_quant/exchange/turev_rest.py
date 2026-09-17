"""Binance USDⓈ-M REST: funding ödemeleri, ödeme aralıkları, premium index barları. (Faz 14 F)

Evren funding/basis adayının canlı girdisi. Araştırma aynı veriyi arşivden aldı
(`data/turev/`); spike (2026-09-17) REST'in arşivle **bit düzeyinde aynı** olduğunu ölçtü:

- `fundingRate`: 14 sembol (8 s, 4 s ve aralığı değişmiş semboller), 2026-08-01 sonrası bütün
  kayıtlar — `fundingTime == calc_time` (0 ms fark), oran eşit.
- `premiumIndexKlines` 1h: 5 sembol, 288 bar — `open_time` ve `close` eşit.

**Tek boşluk: ödeme aralığı.** REST ödeme kaydında aralık yok; arşivde var. Ardışık ödeme
farkından çıkarmak arşivle %99,954 tutuyor (son 12 ay, 556.202 kayıt): aralık değişiminin
olduğu kayıtlarda tutmuyor. Bu yüzden aralık, kaydın **alındığı an** `fundingInfo`dan okunur
(o anki güncel aralık; listede olmayan sembol 8 s). Değişim anına denk gelen kayıtta arşivden
sapma olabilir; olursa canlı-backtest sapma raporunda görünür.

Perp'i olmayan sembol (`-1121 Invalid symbol`) boş liste döner: araştırmadaki "funding'i olmayan
üye dışlanmaz, dizisi NaN" kuralının canlı karşılığı.
"""

from __future__ import annotations

import time
from typing import Any, Final

import requests

HOST: Final = "https://fapi.binance.com"
SAYFA: Final = 1_000
PREMIUM_SAYFA: Final = 1_500
TIMEOUT_S: Final = 15.0
DENEME: Final = 3
SAAT_MS: Final = 3_600_000


class TurevRestHatasi(RuntimeError):
    """Türev REST isteği tekrarlara rağmen başarısız."""


class BinanceTurevRest:
    def __init__(self, oturum: Any = None) -> None:
        self._s = oturum if oturum is not None else requests.Session()

    def _get(self, yol: str, params: dict[str, Any]) -> Any | None:
        """JSON gövde; geçersiz sembolde `None`."""
        son: Exception | None = None
        for deneme in range(DENEME):
            try:
                y = self._s.get(f"{HOST}{yol}", params=params, timeout=TIMEOUT_S)
            except requests.exceptions.RequestException as hata:
                son = hata
            else:
                if y.status_code == 200:
                    return y.json()
                if y.status_code == 400 and '"code":-1121' in y.text.replace(" ", ""):
                    return None
                son = TurevRestHatasi(f"{yol} {y.status_code}: {y.text[:200]}")
                if y.status_code not in (418, 429) and y.status_code < 500:
                    break
            if deneme + 1 < DENEME:
                time.sleep(1.0 * 2**deneme)
        raise TurevRestHatasi(f"{yol} {params}: {son}")

    def araliklar(self) -> dict[str, int]:
        """Aralığı ayarlanmış sembollerin güncel ödeme aralığı (saat)."""
        govde = self._get("/fapi/v1/fundingInfo", {}) or []
        return {str(r["symbol"]): int(r["fundingIntervalHours"]) for r in govde}

    def funding(self, sembol: str, baslangic_ms: int) -> list[tuple[int, float]]:
        """`fundingTime >= baslangic_ms` ödemeleri, ileri sayfalama (Spike 5)."""
        cikti: list[tuple[int, float]] = []
        imlec = baslangic_ms
        while True:
            sayfa = self._get("/fapi/v1/fundingRate",
                              {"symbol": sembol, "startTime": imlec, "limit": SAYFA})
            if not sayfa:
                break
            cikti.extend((int(r["fundingTime"]), float(r["fundingRate"])) for r in sayfa)
            if len(sayfa) < SAYFA:
                break
            imlec = int(sayfa[-1]["fundingTime"]) + 1
        return cikti

    def premium(self, sembol: str, baslangic_ms: int, bitis_ms: int,
                simdi_ms: int) -> list[tuple[int, float]]:
        """`[baslangic, bitis)` aralığında **kapanmış** premium index 1h barları (`close`)."""
        cikti: list[tuple[int, float]] = []
        imlec = baslangic_ms
        while imlec < bitis_ms:
            sayfa = self._get("/fapi/v1/premiumIndexKlines",
                              {"symbol": sembol, "interval": "1h", "startTime": imlec,
                               "endTime": bitis_ms - 1, "limit": PREMIUM_SAYFA})
            if not sayfa:
                break
            for r in sayfa:
                t = int(r[0])
                if t + SAAT_MS <= simdi_ms and baslangic_ms <= t < bitis_ms:
                    cikti.append((t, float(r[4])))
            if len(sayfa) < PREMIUM_SAYFA:
                break
            imlec = int(sayfa[-1][0]) + SAAT_MS
        return cikti


__all__ = ["BinanceTurevRest", "TurevRestHatasi"]
