"""`sq izle` — dört boyutlu izleme ve alarmlar. (Faz 14)

`kontrol` her çalıştığında bütün kuralları koşturur, etkin alarmları `runs/izleme/durum.json`a
yazar ve **değişimleri** (açılan / kapanan alarm) `runs/izleme/alarmlar.jsonl`e ekler. Hostta
zamanlanmış görevle 15 dakikada bir koşar. Her alarm kodunun `docs/arsiv/Runbook.md`de satırı var.
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
NTFY_KOK = "https://ntfy.sh"


def ntfy_konusu(env_yolu: Path = Path(".env")) -> str | None:
    """`.env`deki `SQ_NTFY_KONU`. Konu adı tahmin edilemez rastgele bir dizgedir; ntfy'da
    konuyu bilen herkes okuyabilir, bu yüzden mesajlara sır, anahtar ya da gerçek hesap bilgisi
    yazılmaz (gözlem koşusunun sanal özkaynağı yazılır)."""
    if not env_yolu.is_file():
        return None
    for satir in env_yolu.read_text(encoding="utf-8").splitlines():
        if satir.startswith("SQ_NTFY_KONU="):
            return satir.split("=", 1)[1].strip() or None
    return None


def bildir(konu: str, baslik: str, govde: str, *, oncelik: str = "default",
           etiket: str = "") -> bool:
    """ntfy.sh'e tek bildirim. Başarısızlık koşuyu/kontrolü etkilemez, `False` döner."""
    import requests

    try:
        y = requests.post(f"{NTFY_KOK}/{konu}", data=govde.encode("utf-8"), timeout=15,
                          headers={"Title": baslik.encode("utf-8"), "Priority": oncelik,
                                   "Tags": etiket})
        return y.status_code == 200
    except requests.RequestException:
        return False
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
    bildirim: Annotated[
        bool, typer.Option("--bildir", help="Açılan/kapanan alarmları ntfy'a gönder.")
    ] = False,
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
    konu = ntfy_konusu() if bildirim else None
    for d in degisim if konu else []:
        acildi = d["olay"] == "acildi"
        bildir(
            konu,
            f"{'ALARM' if acildi else 'kapandı'}: {d['kod']} ({d['kosu'] or 'host'})",
            f"{d['mesaj']}\n{d['boyut']} · {d['seviye']} · {zaman}\n"
            "Müdahale: docs/arsiv/Runbook.md",
            oncelik=("urgent" if d["seviye"] == "kritik" else "high") if acildi else "low",
            etiket="rotating_light" if acildi else "white_check_mark",
        )
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


@izle_app.command("ozet")
def izle_ozet(
    evren: Annotated[list[str] | None, typer.Option("--evren")] = None,
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    izleme_kok: Annotated[Path, typer.Option("--izleme")] = VARSAYILAN_IZLEME,
    bildirim: Annotated[bool, typer.Option("--bildir")] = False,
) -> None:
    """Günlük sağlık özeti. Bildirim olarak gelmediği gün host ya da izleme ayakta değildir:
    alarm sistemi kendi ölümünü haber veremez, sessizliğin kendisi sinyal olmalı."""
    simdi = simdi_ms()
    satirlar = []
    for k in evren or []:
        g = izleme.evren_gozlemi(kok / f"{k}.sqlite", simdi)
        if not g.get("var"):
            satirlar.append(f"{k}: koşu dosyası yok")
            continue
        getiri = (g.get("ozkaynak", 0.0) / 10_000.0 - 1) * 100 if g.get("ozkaynak") else 0.0
        satirlar.append(
            f"{k}: {'çalışıyor' if g['surec_yasiyor'] else 'DURMUŞ'} · adım {g.get('adim')} · "
            f"özkaynak {g.get('ozkaynak', 0):,.0f} ({getiri:+.2f}%) · brüt {g.get('brut', 0):.2f}")
    durum_yolu = izleme_kok / "durum.json"
    etkin = (json.loads(durum_yolu.read_text(encoding="utf-8")).get("alarmlar", [])
             if durum_yolu.exists() else [])
    satirlar.append(f"etkin alarm: {len(etkin)}" + "".join(f"\n- {a['kod']} ({a['kosu']})"
                                                          for a in etkin))
    metin = "\n".join(satirlar)
    typer.echo(metin)
    konu = ntfy_konusu() if bildirim else None
    if konu:
        bildir(konu, "ScryneQuant günlük özet (gözlem, gerçek emir yok)", metin,
               oncelik="low", etiket="bar_chart")
