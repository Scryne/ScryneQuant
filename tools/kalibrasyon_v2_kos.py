"""K-054'ün yeni kapılarının null kalibrasyonunu koşturur. **Elle çalıştırılır.**

    uv run python tools/kalibrasyon_v2_kos.py donchian 200

Üç istatistiğin null dağılımını üç ayrı pencerede ölçüp `runs/kalibrasyon-v2/` altına
yazar. Pahalı (strateji başına ~40 dk); eşiklerin gerekçesi bu koşunun çıktısıdır.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import git_durumu, ortam_kaydi
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.research import kalibrasyon_v2 as kal
from scryne_quant.research import rejim as rejim_mod
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.izgaralar import izgara
from scryne_quant.research.karsilastirma import ortak_isinma, ortak_pencereler
from scryne_quant.strategy.kutuphane import coz

KOK = Path(__file__).resolve().parent.parent
CIKTI = KOK / "runs" / "kalibrasyon-v2"


def main() -> int:
    ad = sys.argv[1] if len(sys.argv) > 1 else "donchian"
    deneme = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    sembol, timeframe = "BTCUSDT", "1h"

    depo = ParquetDepo(KOK / "data" / "market")
    diz = bar_dizileri(depo.oku(sembol, timeframe))
    veri_sha = depo.sha256(sembol, timeframe)
    n = len(diz["open_time"])
    maliyet = maliyet_mod.yukle()

    isinma = ortak_isinma([ad])
    ins, oos = ortak_pencereler(n, [ad], oos_orani=0.30)
    tam = Pencere("tam", baslangic=isinma, bitis=n, isinma_baslangic=0)
    yil_bar = 365.25 * 24 * 3_600_000 / 3_600_000

    etiket_tam = rejim_mod.etiketle(diz["close"])
    # `kosu` ısınma barlarını ölçümden düşürüyor; etiket dizisi de aynı yerden kesilmeli.
    # Kesilmezse `rejim.olc` uzunluk uyuşmazlığıyla **durur** — ve durması doğru: sessizce
    # hizalamak, getirileri yanlış rejime yazmak olurdu.
    etiket_oos = etiket_tam[oos.dilim()][oos.olcum_baslangici :]

    sonuc: dict[str, object] = {
        "strateji": ad,
        "sembol": sembol,
        "timeframe": timeframe,
        "veri_sha256": veri_sha,
        "deneme": deneme,
        "bar_sayisi": n,
        "pencereler": {
            "in_sample": ins.sozluk(),
            "out_of_sample": oos.sozluk(),
            "tam": tam.sozluk(),
        },
        "rejim_penceresi": rejim_mod.VARSAYILAN_PENCERE,
        "uretildi": utc_str(simdi_ms()),
        "git": git_durumu(),
        "ortam": ortam_kaydi(),
    }

    CIKTI.mkdir(parents=True, exist_ok=True)
    yol = CIKTI / f"{ad}-{deneme}.json"

    def yaz() -> None:
        """Her ölçümden **sonra** yazar. İlk yazımda dosya yalnızca sonda yazılıyordu ve
        son ölçüm hata verince önceki iki ölçümün ham örneği kayboldu — 45 dakikalık bir
        koşu, bir dilimleme hatası yüzünden. K-044'ün kuralı (ham örnek saklanır ki eşik
        koşu tekrarlanmadan yeniden türetilebilsin) ancak dosya varsa işe yarıyor."""
        metin = json.dumps(sonuc, ensure_ascii=False, indent=2, sort_keys=True)
        yol.write_text(metin + "\n", encoding="utf-8")

    isler = (
        ("pbo", tam, None),
        ("perturbasyon", ins, None),
        ("rejim", oos, etiket_oos),
    )
    for olcum, pencere, etiketler in isler:
        basladi = time.perf_counter()
        takvim = kal.izgara_takvimi(coz(ad), izgara(ad), maliyet, sembol, timeframe, diz, pencere)
        olcum_sonucu = kal.null_olc(
            takvim,
            maliyet,
            sembol,
            timeframe,
            diz,
            olcum=olcum,
            deneme=deneme,
            seed=0,
            yil_bar=yil_bar,
            rejim_etiketleri=etiketler,
        )
        gecen = time.perf_counter() - basladi
        alt, ust = olcum_sonucu.guven_araligi(0.05)
        sonuc[olcum] = {
            **olcum_sonucu.sozluk(),
            "nokta_sayisi": len(takvim),
            "esik_p05": olcum_sonucu.esik(0.05),
            "esik_p01": olcum_sonucu.esik(0.01),
            "esik_p10": olcum_sonucu.esik(0.10),
            "esik_guven_araligi": [alt, ust],
            "sure_sn": round(gecen, 1),
        }
        yaz()
        print(
            f"{ad}/{olcum}: nokta={len(takvim)} gecerli={olcum_sonucu.gecerli_deneme}/{deneme} "
            f"esik(%5)={olcum_sonucu.esik(0.05):.4f} GA=[{alt:.4f},{ust:.4f}] {gecen:.0f}s",
            flush=True,
        )

    CIKTI.mkdir(parents=True, exist_ok=True)
    yol = CIKTI / f"{ad}-{deneme}.json"
    metin = json.dumps(sonuc, ensure_ascii=False, indent=2, sort_keys=True)
    yol.write_text(metin + "\n", encoding="utf-8")
    print(f"yazildi: {yol}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
