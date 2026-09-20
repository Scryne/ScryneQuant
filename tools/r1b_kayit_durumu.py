"""R1(b): kayıtlı deneylerin bugünkü depo/kodla durumu — sınıflandırma. (K-080, ROADMAP-RESET R1)

    uv run python tools/r1b_kayit_durumu.py [--kok runs/deneyler] [--cikti <json>] [--tip tarama]

Her `TEKRAR_EDILEBILIR` kayıt için `sq lab dogrula` koşturulur — **ana depoya dokunmadan**:
sembol/timeframe dosyası geçici bir depoya kopyalanır, veri hash'i uyuşmuyorsa ve kaydın
veri sonu biliniyorsa (`kimlik.veri_son_ms` ya da aşağıdaki K-080 öncesi adres tablosu) geri
sarım o kopyada yapılır. Sonuç sınıfları:

- `ayni` — yeniden üretildi.
- `yalniz_sonuc_hash` — ekonomik alanlar birebir, yalnız `sonuc_hash` farklı (K-057/6); kayıt
  bugünkü hash algoritmasıyla yenilenebilir.
- `semantik` — alan düzeyinde fark; kod kayıt tarihinden beri değişmiş; kayıt tarihsel.
- `veri_geri_getirilemedi` — geri sarım bile kayıttaki veri hash'ini vermedi (ya adres yok
  ya depo içeriği değişmiş); tekrar anlamsız.
- `hata` — komut düştü (ayrıntı kayıtta).

Çıktı JSON'u rapora kopyalanır; kayıt dosyaları **değiştirilmez** (append-only kalıbı).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from scryne_quant.research.tekrar import TEKRAR_EDILEBILIR

#: K-080 öncesi kayıtların geri sarma adresi: veri hash'i → son barın açılışı (UTC).
#: Ölçümle bulundu (2026-09-20): bugünkü `data/market/BTCUSDT/1h.parquet` bu sınıra kırpılınca
#: hash bayt düzeyinde geri geldi. Listede olmayan hash için adres yok.
BILINEN_VERI_SONU: dict[str, str] = {
    "e3adb02c2a6a16396fe0c8d7fe5152fe9aef2506974546d1ae48681988382fea": "2026-09-09 09:00",
}


def _kos(argv: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def _son_json(metin: str) -> dict | None:
    """Çıktıdaki (girintili, çok satırlı) son JSON nesnesi."""
    bas = metin.find("{")
    if bas < 0:
        return None
    try:
        return json.loads(metin[bas:])
    except json.JSONDecodeError:
        return None


def kayit_durumu(kayit_yolu: Path, ana_depo: Path, sq: list[str]) -> dict:
    kayit = json.loads(kayit_yolu.read_text(encoding="utf-8"))
    kimlik = kayit.get("kimlik", {})
    girdi = kayit.get("girdi", {})
    sembol, tf = girdi.get("sembol", "BTCUSDT"), girdi.get("timeframe", "1h")
    temel = {
        "kayit": kayit_yolu.as_posix(),
        "tip": kayit.get("tip"),
        "strateji": kayit.get("strateji"),
        "timeframe": tf,
        "zaman": kayit.get("zaman"),
        "commit": (kimlik.get("commit") or "")[:12],
        "dirty": kimlik.get("dirty"),
        "veri_sha256": (kimlik.get("veri_sha256") or "")[:16],
    }
    if kayit.get("tip") not in TEKRAR_EDILEBILIR:
        return {**temel, "durum": "tekrar_edilemez"}

    with tempfile.TemporaryDirectory(prefix="r1b-") as gecici:
        depo = Path(gecici) / "depo"
        (depo / sembol).mkdir(parents=True)
        kaynak = ana_depo / sembol / f"{tf}.parquet"
        if not kaynak.exists():
            return {**temel, "durum": "hata", "ayrinti": f"ana depoda yok: {kaynak}"}
        shutil.copy(kaynak, depo / sembol / f"{tf}.parquet")

        argv = [*sq, "lab", "dogrula", str(kayit_yolu), "--depo", str(depo), "--json", "--geri-sar"]
        adres = kimlik.get("veri_son_ms")
        if adres is None:
            elle = BILINEN_VERI_SONU.get(kimlik.get("veri_sha256", ""))
            if elle:
                argv += ["--veri-sonu", elle]
        t0 = time.perf_counter()
        kod, out, err = _kos(argv)
        sure = round(time.perf_counter() - t0, 1)
        govde = _son_json(out)

    if govde is None:
        metin = (out + err).strip()
        durum = "veri_geri_getirilemedi" if "veri seti değişmiş" in metin else "hata"
        if "veri_son_ms" in metin and "yok" in metin:
            durum = "veri_geri_getirilemedi"
        return {**temel, "durum": durum, "sure_s": sure, "ayrinti": metin[-400:]}

    durum = "ayni" if govde.get("ayni") else (govde.get("fark_sinifi") or "semantik")
    return {
        **temel,
        "durum": durum,
        "sure_s": sure,
        "geri_sarildi": govde.get("geri_sarildi"),
        "fark_sayisi": govde.get("fark_sayisi"),
        "farklar": (govde.get("farklar") or [])[:8],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kok", default="runs/deneyler")
    ap.add_argument("--depo", default="data/market")
    ap.add_argument("--cikti", default="runs/deneyler/tekrar-durumu.json")
    ap.add_argument("--tip", default=None, help="Yalnız bu tip (ör. tarama)")
    a = ap.parse_args()

    sq = [sys.executable, "-m", "scryne_quant.cli.main"]
    kayitlar = sorted(Path(a.kok).glob("*/*.json"))
    sonuclar = []
    for yol in kayitlar:
        try:
            govde = json.loads(yol.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(govde, dict) or "kimlik" not in govde or "tip" not in govde:
            continue
        if a.tip and govde["tip"] != a.tip:
            continue
        print(f"== {yol.as_posix()}", flush=True)
        s = kayit_durumu(yol, Path(a.depo), sq)
        print(f"   {s['durum']}  ({s.get('sure_s', '-')} s)", flush=True)
        sonuclar.append(s)
        Path(a.cikti).write_text(
            json.dumps(
                {"uretildi": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                 "kayitlar": sonuclar},
                ensure_ascii=False, indent=2,
            ) + "\n",
            encoding="utf-8",
        )
    ozet: dict[str, int] = {}
    for s in sonuclar:
        ozet[s["durum"]] = ozet.get(s["durum"], 0) + 1
    print("özet:", json.dumps(ozet, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
