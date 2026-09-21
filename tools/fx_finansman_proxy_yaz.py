"""FX finansman **proxy** modellerini yazar: merkez bankası faiz farkından. (K-098/2, R5 Paket 1)

    uv run python tools/fx_finansman_proxy_yaz.py [--dizin config/finansman] [--tarih 2026-09-21]

**Neden proxy:** FXCM rollover oranını yalnız platformda (Roll S/Roll B, 1k lot, bir gün önceden)
gösteriyor; **tarihli, herkese açık bir arşiv yok** (fxcm.com/markets/help/rollover-where-is-
rollover-shown, ca/help/.../rollover — 2026-09-21 okundu). Bu yüzden yazılan model `tur="proxy"`:
gerçek broker oranı **gibi kaydedilmez**, `gecici` sayılır, promotion'a giremez (K-098).

**Türetim (`fx_kalibrasyon.finansman_proxy_bps`):** uzun pozisyon taban parayı tutar (faiz alır,
aralığın **altı**), quote parayı borçlanır (faiz öder, aralığın **üstü**) — K-007 aleyhte.
`ham = (quote_üst − taban_alt) / 365 × 100` bps/gün; `uzun_gunluk_bps = max(ham, 0)` (K-095/1,
K-007: lehte carry modellenmez; ham değer kayda girer). Broker marjı bilinmiyor → eklenmedi;
proxy bedeli gerçek brokerınkinden **düşük** olabilir (yön aleyhte değil — bir sebep daha
`gecici`).

**Oran tablosu (politika faizleri, yıllık %, `(alt, üst)`), geçerlilik ve kaynak:** aşağıda.
Aralık = tüm bacakların sabit olduğu en uzun ortak dönem; dışına çıkan koşu için model geçersizdir
(bugün motor aralığı **denetlemiyor** — K-098 açık madde).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scryne_quant.common.finansman import FinansmanKaynagi, FinansmanModeli
from scryne_quant.data.fx_kalibrasyon import finansman_proxy_bps

#: Para birimi → (alt, üst) yıllık %, geçerlilik `(başlangıç, bitiş)` (dahil..hariç), kaynak.
ORANLAR: dict[str, dict[str, object]] = {
    "USD": {
        "aralik_yuzde": (5.25, 5.50),
        "gecerli": ("2023-07-27", "2024-09-18"),
        "kaynak": "Federal Reserve, FOMC statements 2023-07-26 (target range 5-1/4 to 5-1/2) … "
        "2024-09-18 (cut to 4-3/4 to 5); https://www.federalreserve.gov/monetarypolicy/"
        "fomccalendars.htm",
    },
    "EUR": {
        "aralik_yuzde": (4.00, 4.00),
        "gecerli": ("2023-09-20", "2024-06-12"),
        "kaynak": "ECB deposit facility rate 4.00% from 2023-09-20; cut to 3.75% effective "
        "2024-06-12; https://www.ecb.europa.eu/stats/policy_and_exchange_rates/"
        "key_ecb_interest_rates/html/index.en.html",
    },
    "GBP": {
        "aralik_yuzde": (5.25, 5.25),
        "gecerli": ("2023-08-03", "2024-08-01"),
        "kaynak": "Bank of England Bank Rate 5.25% from 2023-08-03; cut to 5.00% on 2024-08-01; "
        "https://www.bankofengland.co.uk/monetary-policy/the-interest-rate-bank-rate",
    },
    "JPY": {
        "aralik_yuzde": (-0.10, -0.10),
        "gecerli": ("2016-02-16", "2024-03-19"),
        "kaynak": "Bank of Japan policy rate −0.10% (negative interest rate policy) until the "
        "2024-03-19 decision (0 to 0.1%); https://www.boj.or.jp/en/mopo/mpmdeci/index.htm",
    },
}

CIFTLER: tuple[str, ...] = ("EURUSD", "GBPUSD", "USDJPY")


def ortak_aralik(taban: str, quote: str) -> str:
    b1, b2 = ORANLAR[taban]["gecerli"]  # type: ignore[misc]
    q1, q2 = ORANLAR[quote]["gecerli"]  # type: ignore[misc]
    return f"{max(b1, q1)}..{min(b2, q2)}"


def model_kur(pair: str, tarih: str) -> FinansmanModeli:
    taban, quote = pair[:3], pair[3:]
    t, q = ORANLAR[taban], ORANLAR[quote]
    ham, deger = finansman_proxy_bps(t["aralik_yuzde"], q["aralik_yuzde"])  # type: ignore[arg-type]
    gerekce = (
        f"PROXY — merkez bankası politika faizi farkı, broker oranı değil. Uzun {pair}: {taban} "
        f"tutulur (alınan faiz aralığın altı {t['aralik_yuzde'][0]}%), {quote} borçlanılır (ödenen "  # type: ignore[index]
        f"faiz aralığın üstü {q['aralik_yuzde'][1]}%); ham = (quote_üst − taban_alt)/365×100 = "  # type: ignore[index]
        f"{ham:.4f} bps/gün; uzun_gunluk_bps = max(ham, 0) = {deger:.4f} (K-095/1, K-007: lehte "
        "carry modellenmez; ham kayıtta). Broker marjı bilinmiyor, eklenmedi. FXCM tarihli "
        "rollover arşivi yok (yalnız platform, bir gün önceden; fxcm.com help 'Where is rollover "
        "shown', "
        "2026-09-21). Kaynaklar: " + t["kaynak"] + " | " + q["kaynak"]  # type: ignore[operator]
    )
    return FinansmanModeli(
        uzun_gunluk_bps=deger,
        kaynak=FinansmanKaynagi(
            saglayici="merkez-bankasi-politika-faizi (proxy)",
            tarih=tarih,
            gerekce=gerekce,
            aralik=ortak_aralik(taban, quote),
            tur="proxy",
            ham_gunluk_bps=ham,
        ),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dizin", default="config/finansman")
    ap.add_argument("--tarih", default="2026-09-21")
    args = ap.parse_args()
    dizin = Path(args.dizin)
    dizin.mkdir(parents=True, exist_ok=True)
    for pair in CIFTLER:
        model = model_kur(pair, args.tarih)
        yol = dizin / f"fxcm-{pair.lower()}.json"
        yol.write_text(
            json.dumps(model.model_dump(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        k = model.kaynak
        assert k is not None
        print(f"{yol}: uzun {model.uzun_gunluk_bps:.4f} bps/gün (ham {k.ham_gunluk_bps:+.4f}), "
              f"aralık {k.aralik}, gecici={model.gecici}")


if __name__ == "__main__":
    main()
