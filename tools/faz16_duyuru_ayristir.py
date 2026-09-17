"""Duyuru gövdelerinden **kural tabanlı** olay çıkarımı. (Faz 16, K-067)

    uv run python tools/faz16_duyuru_ayristir.py

Geçmiş dönem için sınıflandırma **kuralla** yapılır, Jev'le değil: modelin eğitim kesimi
öncesine ait bir metni bugün sınıflandırmak `leak_riski` taşır ve kapıdan geçemez (K-049/4,
K-067). Jev'in bu yoldaki işi kuralın **kalitesini ölçmek** (`faz16_duyuru_jev_dogrula.py`) ve
ileriye dönük sınıflandırma.

Çıkarılan alanlar (`data/duyuru/olaylar.parquet`):

| Alan | Ne |
| --- | --- |
| `duyuru_id`, `yayin_ms` | Kaynak duyuru ve **görülme** anı (`available_time`, K-052/15) |
| `olay` | `spot_listeleme`, `spot_kaldirma`, `delist`, `marjin_ekleme`, `marjin_kaldirma`, |
| | `teminat_ekleme`, `teminat_kaldirma`, `vadeli_listeleme`, `vadeli_delist` |
| `yon` | `erisim_artisi` / `erisim_azalisi` — olay türünden türetilir, metinden değil |
| `taban`, `kote`, `parite` | Etkilenen parite (ör. `QNT`, `USDC`, `QNTUSDC`) |
| `etkili_ms` | Metinde yazan yürürlük anı (yoksa boş; uydurulmaz) |

**Kurallar metinden okunur, tahmin edilmez.** Bir gövdede yürürlük saati "At 2026-09-18 03:00
(UTC):" biçiminde pariteden **önce** geliyor; her parite, kendisinden önce gelen en yakın
zamana bağlanır. Zaman bulunamazsa alan boş kalır.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

from scryne_quant.common.zaman import simdi_ms, utc_str

KOK = Path(__file__).resolve().parent.parent
DEPO = KOK / "data" / "duyuru"
CIKTI = DEPO / "olaylar.parquet"
KAYNAK = DEPO / "olaylar.kaynak.json"

#: Olay türü → (başlıkta aranan kalıp, yön). Sıra **önemli**: ilk eşleşen kazanır, bu yüzden
#: daha özel kalıplar üstte.
KURALLAR: tuple[tuple[str, str, str], ...] = (
    ("vadeli_delist", r"futures.*(will delist|to delist)|delisting of usd", "erisim_azalisi"),
    ("vadeli_listeleme", r"futures will (launch|list)", "erisim_artisi"),
    ("marjin_kaldirma", r"margin.*(will delist|to delist|removal|will remove)", "erisim_azalisi"),
    ("marjin_ekleme", r"margin.*(will add|adds|new (isolated|cross)|available)",
     "erisim_artisi"),
    ("teminat_kaldirma", r"removal of.*collateral|remove.*collateral", "erisim_azalisi"),
    ("teminat_ekleme", r"collateral asset|as collateral", "erisim_artisi"),
    ("spot_kaldirma", r"removal of (spot )?trading pairs|remove and cease trading",
     "erisim_azalisi"),
    ("delist", r"will delist|to delist|delisting", "erisim_azalisi"),
    ("spot_listeleme", r"will list|will add|adds .*trading pair|new trading pair|will open "
     r"trading", "erisim_artisi"),
)
#: `QNT/USDC` biçimindeki pariteler. Taban 2-15, kote 2-10 karakter; küçük harf yok.
PARITE = re.compile(r"\b([A-Z0-9]{2,15})/([A-Z0-9]{2,10})\b")
#: `At 2026-09-18 03:00 (UTC)` ya da `on 2026-09-18 at 03:00 (UTC)`.
ZAMAN = re.compile(r"(\d{4}-\d{2}-\d{2})[ ,]*(?:at )?(\d{2}:\d{2})?\s*\(UTC\)")
#: Gövdede geçen ama parite olmayan kısaltmalar (yanlış pozitifleri kes).
HARIC_KOTE = {"UTC", "USD", "APY", "API", "FAQ", "KYC", "P2P", "NFT", "VIP"}


def _olay(baslik: str, metin: str) -> tuple[str, str] | None:
    hedef = f"{baslik}\n{metin[:400]}".lower()
    for ad, kalip, yon in KURALLAR:
        if re.search(kalip, hedef):
            return ad, yon
    return None


def _zamanli_pariteler(metin: str) -> list[tuple[str, str, int | None]]:
    """Metindeki pariteler, kendinden önce gelen en yakın (UTC) zamanla."""
    zamanlar = [(m.start(), m.group(1), m.group(2)) for m in ZAMAN.finditer(metin)]
    cikti: list[tuple[str, str, int | None]] = []
    for m in PARITE.finditer(metin):
        taban, kote = m.group(1), m.group(2)
        if kote in HARIC_KOTE or taban in HARIC_KOTE:
            continue
        onceki = [z for z in zamanlar if z[0] < m.start()]
        etkili = None
        if onceki:
            _, gun, saat = onceki[-1]
            etkili = int(pd.Timestamp(f"{gun} {saat or '00:00'}", tz="UTC").value // 10**6)
        cikti.append((taban, kote, etkili))
    return cikti


def main() -> int:
    duyuru = pd.read_parquet(DEPO / "duyurular.parquet")
    govde = pd.read_parquet(DEPO / "govdeler.parquet")
    birlesik = duyuru.merge(govde[["id", "metin"]], on="id", how="inner")
    satirlar, olaysiz, paritesiz = [], 0, 0
    for r in birlesik.itertuples():
        bulunan = _olay(str(r.baslik), str(r.metin))
        if bulunan is None:
            olaysiz += 1
            continue
        olay, yon = bulunan
        pariteler = _zamanli_pariteler(str(r.metin))
        if not pariteler:
            paritesiz += 1
            continue
        gorulen = set()
        for taban, kote, etkili in pariteler:
            if (taban, kote) in gorulen:
                continue
            gorulen.add((taban, kote))
            satirlar.append({"duyuru_id": int(r.id), "yayin_ms": int(r.yayin_ms),
                             "katalog": str(r.katalog), "olay": olay, "yon": yon,
                             "taban": taban, "kote": kote, "parite": f"{taban}{kote}",
                             "etkili_ms": etkili, "baslik": str(r.baslik)})
    df = pd.DataFrame(satirlar).sort_values(["yayin_ms", "parite"]).reset_index(drop=True)
    df.to_parquet(CIKTI, index=False)
    ozet = {
        "uretildi": utc_str(simdi_ms()),
        "duyuru": len(birlesik),
        "olay_satiri": len(df),
        "olay_bulunamayan_duyuru": olaysiz,
        "parite_bulunamayan_duyuru": paritesiz,
        "olay_dagilimi": df["olay"].value_counts().to_dict(),
        "yon_dagilimi": df["yon"].value_counts().to_dict(),
        "etkili_zamani_olan_oran": float(df["etkili_ms"].notna().mean()) if len(df) else 0.0,
        "usdt_paritesi": int((df["kote"] == "USDT").sum()),
        "benzersiz_taban": int(df["taban"].nunique()),
        "ilk": utc_str(int(df["yayin_ms"].min())) if len(df) else None,
        "son": utc_str(int(df["yayin_ms"].max())) if len(df) else None,
        "kural_hash": hashlib.sha256(json.dumps(KURALLAR, ensure_ascii=False).encode()
                                     ).hexdigest()[:16],
    }
    KAYNAK.write_text(json.dumps(ozet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(json.dumps(ozet, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
