"""`sq izle` — dört boyutlu izleme ve alarmlar. (Faz 14)

`kontrol` her çalıştığında bütün kuralları koşturur, etkin alarmları `runs/izleme/durum.json`a
yazar ve **değişimleri** (açılan / kapanan alarm) `runs/izleme/alarmlar.jsonl`e ekler. Hostta
zamanlanmış görevle 15 dakikada bir koşar. Her alarm kodunun `docs/Runbook.md`de satırı var.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.live import izleme
from scryne_quant.live import kill as kill_mod

izle_app = typer.Typer(
    name="izle", help="İzleme: sistem, veri, trading, model + alarmlar. (Faz 14)"
)

VARSAYILAN_KOK = Path("runs/paper")
VARSAYILAN_IZLEME = Path("runs/izleme")


def _anahtar(a: dict) -> str:
    return f"{a['kod']}|{a['kosu']}"


@izle_app.command("kontrol")
def izle_kontrol(
    evren: Annotated[
        list[str] | None, typer.Option("--evren", help="İzlenecek evren koşusu (tekrarlanabilir).")
    ] = None,
    tek: Annotated[
        list[str] | None,
        typer.Option("--tek", help="Tek sembollü koşu: yalnızca süreç kontrolü."),
    ] = None,
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    izleme_kok: Annotated[Path, typer.Option("--izleme")] = VARSAYILAN_IZLEME,
    json_cikti: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Kuralları koşturur; kritik alarm varsa çıkış kodu 2."""
    simdi = simdi_ms()
    sistem = izleme.sistem_gozlemi(kok if kok.exists() else Path("."))
    kosular = [izleme.evren_gozlemi(kok / f"{k}.sqlite", simdi) for k in evren or []]
    for k in tek or []:
        pid = kill_mod.pid_oku(kok / f"{k}.sqlite")
        kosular.append({"kosu": k, "var": False, "pid": pid,
                        "surec_yasiyor": bool(pid and kill_mod.surec_yasiyor_mu(pid))})
    etkin = [a.sozluk() for a in izleme.alarmlar(sistem, kosular, simdi)]

    izleme_kok.mkdir(parents=True, exist_ok=True)
    durum_yolu = izleme_kok / "durum.json"
    onceki = {}
    if durum_yolu.exists():
        onceki = {_anahtar(a): a for a in json.loads(durum_yolu.read_text(encoding="utf-8"))
                  .get("alarmlar", [])}
    simdiki = {_anahtar(a): a for a in etkin}
    degisim = [{"olay": "acildi", **a} for k, a in simdiki.items() if k not in onceki]
    degisim += [{"olay": "kapandi", **a} for k, a in onceki.items() if k not in simdiki]
    zaman = utc_str(simdi)
    if degisim:
        with (izleme_kok / "alarmlar.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            for d in degisim:
                f.write(json.dumps({"zaman": zaman, **d}, ensure_ascii=False) + "\n")
    govde = {"zaman": zaman, "sistem": sistem, "alarmlar": etkin,
             "kosular": [{k: v for k, v in g.items() if k in (
                 "kosu", "surec_yasiyor", "adim", "son_bar_ms", "ozkaynak", "brut", "safe_mode")}
                 for g in kosular]}
    durum_yolu.write_text(json.dumps(govde, ensure_ascii=False, indent=1), encoding="utf-8")

    if json_cikti:
        typer.echo(json.dumps(govde, ensure_ascii=False, indent=1))
    else:
        acilan = sum(d["olay"] == "acildi" for d in degisim)
        typer.echo(f"{zaman}  alarm {len(etkin)} (açılan {acilan}, "
                   f"kapanan {len(degisim) - acilan})")
        for a in etkin:
            typer.echo(f"  [{a['seviye']:<6}] {a['boyut']:<7} {a['kod']:<22} {a['kosu'] or '-'}: "
                       f"{a['mesaj']}")
    if any(a["seviye"] == "kritik" for a in etkin):
        raise typer.Exit(code=2)
