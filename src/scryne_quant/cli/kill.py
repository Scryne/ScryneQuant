"""`sq kill` — süreç dışı kill switch. (Faz 14, K-065)

Trader sürecinin işbirliği olmadan çalışır: SAFE_MODE işaretini diske yazar, süreci
işletim sistemi düzeyinde sonlandırır, borsadaki açık emirleri iptal edip doğrular
(`live/kill.py`). Paper/gözlem koşusunda borsa emri yok; `--testnet` yalnızca testnet
adaptörünü kurar. Canlı borsa bu komutta **yok** ve bilerek yok: Faz 8'in geçişi bir karar
olarak yazılacak (K-010).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from scryne_quant.common.zaman import utc_str
from scryne_quant.live import kill as kill_mod

kill_app = typer.Typer(
    name="kill",
    help="Süreç dışı kill switch: SAFE_MODE işareti, süreci sonlandırma, emir iptali. (K-065)",
)

VARSAYILAN_KOK = Path("runs/paper")


def _yol(kosu: str, kok: Path) -> Path:
    p = Path(kosu)
    return p if p.suffix == ".sqlite" else kok / f"{kosu}.sqlite"


@kill_app.command("calistir")
def kill_calistir(
    kosu: Annotated[str, typer.Argument(help="Koşu adı ya da .sqlite yolu.")],
    sebep: Annotated[str, typer.Option("--sebep", "-s", help="Neden? (≥5 karakter)")],
    testnet: Annotated[
        bool, typer.Option("--testnet", help="Testnet'teki açık emirleri de iptal et.")
    ] = False,
    sembol: Annotated[
        list[str] | None, typer.Option("--sembol", help="İptal edilecek sembol(ler).")
    ] = None,
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    json_cikti: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Kill: işaret → süreç → emirler. Başarısızsa çıkış kodu 1."""
    borsa = None
    if testnet:
        from scryne_quant.exchange.imzali import BinanceImzaliAdaptoru

        borsa = BinanceImzaliAdaptoru()
    rapor = kill_mod.kill(_yol(kosu, kok), sebep=sebep, borsa=borsa,
                          semboller=tuple(sembol or ("BTCUSDT",)) if borsa else ())
    if json_cikti:
        typer.echo(json.dumps(rapor.sozluk(), ensure_ascii=False, indent=2, default=str))
    else:
        typer.echo(f"SAFE_MODE işareti : {rapor.safe_isaret}")
        typer.echo(f"süreç            : {rapor.surec or 'pid dosyası yok'}")
        typer.echo(f"iptal            : {len(rapor.iptaller)} emir · kalan {rapor.kalan_acik_emir}")
        for h in rapor.hatalar:
            typer.secho(f"HATA             : {h}", fg=typer.colors.RED)
        typer.secho("KILL BAŞARILI" if rapor.basarili else "KILL BAŞARISIZ",
                    fg=typer.colors.GREEN if rapor.basarili else typer.colors.RED)
    raise typer.Exit(0 if rapor.basarili else 1)


@kill_app.command("durum")
def kill_durum(
    kosu: Annotated[str, typer.Argument()],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
) -> None:
    yol = _yol(kosu, kok)
    isaret = kill_mod.safe_isareti(yol)
    pid = kill_mod.pid_oku(yol)
    typer.echo(f"SAFE_MODE işareti: {'YOK' if isaret is None else isaret}")
    typer.echo(f"pid: {pid} ({'yaşıyor' if pid and kill_mod.surec_yasiyor_mu(pid) else 'yok'})")


@kill_app.command("kaldir")
def kill_kaldir(
    kosu: Annotated[str, typer.Argument()],
    not_metni: Annotated[str, typer.Option("--not", help="Gerekçe (≥10 karakter).")],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
) -> None:
    """İşareti **elle** kaldırır (K-008/4). Risk motorundaki SAFE_MODE ayrıca `sq risk serbest`."""
    try:
        kayit = kill_mod.safe_kaldir(_yol(kosu, kok), not_metni)
    except kill_mod.KillHatasi as hata:
        raise typer.BadParameter(str(hata)) from hata
    typer.secho(f"işaret kaldırıldı ({utc_str(kayit['kaldirildi_ms'])}); gerekçe kayda geçti",
                fg=typer.colors.GREEN)


__all__ = ["kill_app"]
