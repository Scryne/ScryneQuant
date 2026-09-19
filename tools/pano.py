"""Gözlem panosunu CLI'ya dokunmadan başlatan tek dosyalık başlatıcı. (Faz 14)

`sq paper pano` aynı işi yapıyor ve normal yol odur. Bu betik **dayanıklılık penceresi
açıkken** (K-069) hosta konabilmek için var: pano `cli/main.py`yi hiç içe aktarmadan
kalkıyor, yani hostta çalışan zamanlanmış görevlerin (izleme, yedek, sapma) kullandığı
tek bir dosya bile değişmiyor. Pencere kapandığında bu betik gerekmez; `sq paper pano`
kullanılır ve buradaki tek fark, hangi dosyaların diske dokunduğudur.

Kullanım:
    python tools/pano.py --port 8788 --web apps/web/dist
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
if str(KOK / "src") not in sys.path:
    sys.path.insert(0, str(KOK / "src"))


def main() -> int:
    import uvicorn

    from scryne_quant.live.evren_pano import PanoKaynagi, pano_kur

    ayristirici = argparse.ArgumentParser(description="ScryneQuant gözlem panosu (salt okunur)")
    ayristirici.add_argument("--port", type=int, default=8788)
    ayristirici.add_argument("--host", default="127.0.0.1")
    ayristirici.add_argument("--kok", type=Path, default=KOK / "runs/paper")
    ayristirici.add_argument("--izleme", type=Path, default=KOK / "runs/izleme")
    ayristirici.add_argument("--jev", type=Path, default=KOK / "runs/jev")
    ayristirici.add_argument("--web", type=Path, default=KOK / "apps/web/dist")
    a = ayristirici.parse_args()

    kaynak = PanoKaynagi(a.kok, a.izleme, jev_kok=a.jev)
    web = a.web.resolve() if a.web is not None and a.web.is_dir() else None
    app = pano_kur(kaynak, web_kok=web)
    bulunan = [y.name[: -len(".sqlite")] for y in kaynak.kosu_yollari()]
    print(f"pano    : http://{a.host}:{a.port}  (salt okunur)", flush=True)
    print(f"koşular : {', '.join(bulunan) if bulunan else 'yok'}", flush=True)
    jev = [y.name[: -len(".sqlite")] for y in kaynak.jev_yollari()]
    print(f"jev     : {', '.join(jev) if jev else 'yok'}", flush=True)
    print(f"web     : {web or 'yok (yalnızca /api)'}", flush=True)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
