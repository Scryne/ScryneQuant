"""`sq aktif` — çok varlıklı demo bot. (K-134)

    sq aktif geriye   --hesap kripto-trend [--gun 180]   aynı kurallarla backtest
    sq aktif calistir --hesap kripto-trend               bar kapanışlarında demo işlem
    sq aktif karne    --hesap kripto-trend               haftalık karne
    sq aktif durdur   --hesap kripto-trend               temiz durdurma
    sq aktif baglanti --hesap mt5-demo                   MT5 hesabı + sembol adları
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer

aktif_app = typer.Typer(name="aktif", help="Çok varlıklı demo bot (K-134).", no_args_is_help=True)

AYAR = Path("config/aktif.json")
KOK = Path("runs/aktif")

HesapOpt = Annotated[str, typer.Option("--hesap", help="config/aktif.json'daki hesap adı")]


def _ayar(hesap: str) -> tuple[Any, dict[str, Any]]:
    from scryne_quant.aktif.dongu import HesapAyari

    d = json.loads(AYAR.read_text(encoding="utf-8"))
    if hesap not in d["hesaplar"]:
        raise typer.BadParameter(f"hesap yok: {hesap}; mevcut: {', '.join(d['hesaplar'])}")
    ham = d["hesaplar"][hesap]
    risk = {k: v for k, v in d["risk"].items() if not k.startswith("_")}
    return HesapAyari.sozlukten(hesap, ham, risk), ham


def _araci(ayar: Any, ham: dict[str, Any]) -> Any:
    from scryne_quant.aktif.araci import KriptoPaper, MT5Araci, MT5Paper

    if ayar.araci == "kripto_paper":
        return KriptoPaper(KOK / ayar.ad, sermaye=float(ham["sermaye"]),
                           ucret_bps=float(ham["ucret_bps"]), kayma_bps=float(ham["kayma_bps"]),
                           yalniz_long=bool(ham.get("yalniz_long", True)))
    if ayar.araci == "mt5":
        return MT5Araci(sunucu_utc_farki_saat=ham.get("sunucu_utc_farki_saat"))
    if ayar.araci == "mt5_paper":
        return MT5Paper(KOK / ayar.ad, sermaye=float(ham["sermaye"]),
                        ucret_bps=float(ham["ucret_bps"]), kayma_bps=float(ham["kayma_bps"]),
                        sunucu_utc_farki_saat=ham.get("sunucu_utc_farki_saat"))
    raise typer.BadParameter(f"bilinmeyen aracı: {ayar.araci}")


def _mt5_swap(araci: Any, semboller: tuple[str, ...]) -> dict[str, Any]:
    """Backtest için MT5 swap oranları (gecelik, notional kesri) — bugünkü değerler (K-136)."""
    oranlar: dict[str, tuple[float, float]] = {}
    uc_kat = 3
    for s in semboller:
        b = araci._sembol(s)
        if int(b.swap_mode) != 1:
            continue
        f = araci.fiyat(s)
        oranlar[s] = (float(b.swap_long) * float(b.point) / f,
                      float(b.swap_short) * float(b.point) / f)
        uc_kat = int(b.swap_rollover3days)
    return {"swap": oranlar, "sunucu_farki_ms": araci.sunucu_farki_s(semboller[0]) * 1000,
            "uc_kat_gun": uc_kat}


@aktif_app.command("geriye")
def geriye_komut(
    hesap: HesapOpt,
    gun: Annotated[int, typer.Option("--gun", help="geriye kaç gün")] = 180,
    strateji: Annotated[str | None, typer.Option("--strateji", help="ayardakini ez")] = None,
    timeframe: Annotated[str | None, typer.Option("--timeframe", help="ayardakini ez")] = None,
    json_cikti: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Hesabın kuralları + maliyetle backtest; haftalık özet (tamamı ve son %30)."""
    from dataclasses import replace

    from scryne_quant.aktif import geriye as geriye_mod
    from scryne_quant.aktif.araci import binance_gecmis
    from scryne_quant.common.zaman import simdi_ms, timeframe_ms

    ayar, ham = _ayar(hesap)
    if strateji:
        ayar = replace(ayar, strateji=strateji, parametreler={})
    if timeframe:
        ayar = replace(ayar, timeframe=timeframe)
    adim = timeframe_ms(ayar.timeframe)
    barlar: dict[str, pd.DataFrame] = {}
    swap_ek: dict[str, Any] = {}
    if ayar.araci == "kripto_paper":
        veri = KOK / "veri"
        veri.mkdir(parents=True, exist_ok=True)
        bitis = simdi_ms() // adim * adim
        baslangic = bitis - gun * 86_400_000
        for s in ayar.semboller:
            yol = veri / f"{s}_{ayar.timeframe}_{baslangic}_{bitis}.parquet"
            if yol.is_file():
                barlar[s] = pd.read_parquet(yol)
            else:
                df = binance_gecmis(s, ayar.timeframe, baslangic, bitis)
                df.to_parquet(yol)
                barlar[s] = df
        yalniz_long = bool(ham.get("yalniz_long", True))
    else:
        araci = _araci(ayar, ham)
        adet = gun * 86_400_000 // adim
        for s in ayar.semboller:
            barlar[s] = araci.barlar(s, ayar.timeframe, int(adet))
        yalniz_long = araci.yalniz_long
        swap_ek = _mt5_swap(araci, ayar.semboller)
    sonuc = geriye_mod.geriye(barlar, ayar, yalniz_long=yalniz_long,
                              ucret_bps=float(ham.get("ucret_bps", 10)),
                              kayma_bps=float(ham.get("kayma_bps", 5)), **swap_ek)
    kesim = int(len(sonuc) * 0.7)
    son = sonuc.iloc[kesim:].copy()
    son["ozkaynak"] = son["ozkaynak"] / sonuc["ozkaynak"].iloc[kesim - 1]
    rapor = {"hesap": hesap, "strateji": ayar.strateji, "gun": gun,
             "semboller": {s: len(df) for s, df in barlar.items()},
             "tamami": geriye_mod.ozet(sonuc), "son_yuzde30": geriye_mod.ozet(son)}
    if json_cikti:
        typer.echo(json.dumps(rapor, indent=1, ensure_ascii=False))
        return
    typer.echo(f"{hesap} · {ayar.strateji} · {ayar.timeframe} · {gun} gün · "
               f"{len(barlar)} sembol")
    for ad, o in (("tamamı", rapor["tamami"]), ("son %30", rapor["son_yuzde30"])):
        if not o:
            continue
        typer.echo(
            f"  {ad:8s} toplam {o['toplam_getiri']:+.1%} · hafta ort {o['haftalik_ortalama']:+.2%}"
            f" medyan {o['haftalik_medyan']:+.2%} · kârlı hafta {o['pozitif_hafta']:.0%}"
            f" · en kötü hafta {o['en_kotu_hafta']:+.1%} · max düşüş {o['max_dusus']:.1%}"
            f" · işlem/hafta {o['islem_hafta']:.0f} · Sharpe {o['sharpe_haftalik_yillik']:.2f}"
        )


@aktif_app.command("calistir")
def calistir_komut(hesap: HesapOpt) -> None:
    """Demo döngüsü (Ctrl+C ya da `sq aktif durdur` ile biter)."""
    from scryne_quant.aktif import dongu

    ayar, ham = _ayar(hesap)
    (KOK / hesap / "kapali").unlink(missing_ok=True)  # elle başlatma kalıcı kapatmayı kaldırır
    if ayar.araci == "carry_paper":  # K-139: iki bacaklı funding carry, kendi döngüsü
        from scryne_quant.aktif import carry

        typer.echo(f"AKTİF DEMO '{hesap}' · funding carry · spot long + perp short")
        carry.calistir_carry(KOK / hesap, float(ham["sermaye"]), yaz=typer.echo)
        return
    if ayar.araci == "vadeli_paper":  # K-140: kaldıraçlı vadeli trend/kırılım, kendi döngüsü
        from scryne_quant.aktif import vadeli

        v_ayar = vadeli.VadeliAyari(strat=str(ham["strateji"]), kaldirac=float(ham["kaldirac"]),
                                    sert_stop=bool(ham.get("sert_stop", False)),
                                    semboller=tuple(ham["semboller"]))
        typer.echo(f"AKTİF DEMO '{hesap}' · vadeli {v_ayar.strat} · {v_ayar.kaldirac:g}x")
        vadeli.calistir_vadeli(KOK / hesap, float(ham["sermaye"]), v_ayar, yaz=typer.echo)
        return
    araci = _araci(ayar, ham)
    typer.echo(f"AKTİF DEMO '{hesap}' · {ayar.araci} · {ayar.strateji} · {ayar.timeframe} · "
               f"{len(ayar.semboller)} sembol")
    dongu.calistir(araci, ayar, KOK / hesap, yaz=typer.echo)


@aktif_app.command("durdur")
def durdur_komut(hesap: HesapOpt) -> None:
    """Döngü bir sonraki beklemede temiz biter; gözetmen yeniden başlatmaz (`kapali`)."""
    dizin = KOK / hesap
    dizin.mkdir(parents=True, exist_ok=True)
    (dizin / "kapali").touch()
    (dizin / "dur").touch()
    typer.echo(f"{hesap}: durduruluyor; yeniden başlatmak için `sq aktif calistir --hesap {hesap}`")


@aktif_app.command("karne")
def karne_komut(
    hesap: HesapOpt, json_cikti: Annotated[bool, typer.Option("--json")] = False
) -> None:
    """Haftalık karne: getiri, işlem sayısı, ücret, en kötü gün."""
    from scryne_quant.aktif.defter import Defter

    dizin = KOK / hesap
    if not (dizin / "defter.sqlite").is_file():
        raise typer.BadParameter(f"{hesap} için defter yok (henüz çalışmadı)")
    defter = Defter(dizin)
    try:
        satirlar = defter.karne()
    finally:
        defter.kapat()
    if json_cikti:
        typer.echo(json.dumps(satirlar, indent=1))
        return
    for k in satirlar:
        typer.echo(f"{k['hafta']}  {k['bas']:.2f} → {k['son']:.2f}  {k['getiri']:+.2%}  "
                   f"işlem {k['islem']}  ücret {k['ucret']:.2f}  "
                   f"en kötü gün {k['en_kotu_gun']:+.2%}")


@aktif_app.command("baglanti")
def baglanti_komut(hesap: HesapOpt) -> None:
    """MT5 bağlantısı: hesap türü, bakiye, ayardaki sembollerin varlığı ve benzer adlar."""
    ayar, ham = _ayar(hesap)
    if ayar.araci not in ("mt5", "mt5_paper"):
        raise typer.BadParameter("bu komut yalnız MT5 hesabı için")
    araci = _araci(ayar, ham)
    mt5 = araci._mt5
    h = mt5.account_info()
    typer.echo(f"hesap {h.login} · {h.server} · DEMO · {h.currency} · özkaynak {h.equity:.2f} · "
               f"kaldıraç 1:{h.leverage} · {'hedging' if araci.hedging else 'netting'} · "
               f"algoritmik emir {'AÇIK' if h.trade_expert else 'KAPALI (aracı sunucusu)'}")
    for s in ayar.semboller:
        bilgi = mt5.symbol_info(s)
        if bilgi is None:
            typer.echo(f"  ✗ {s} yok")
        else:
            typer.echo(f"  ✓ {s} · sözleşme {bilgi.trade_contract_size} · lot {bilgi.volume_min}"
                       f"/{bilgi.volume_step} · kâr para birimi {bilgi.currency_profit}")
    adaylar = sorted({x.name for x in (mt5.symbols_get() or ())
                      if any(k in x.name.upper() for k in ("500", "NAS", "100", "EURUSD", "US30"))})
    typer.echo("benzer adlar: " + ", ".join(adaylar[:40]))
