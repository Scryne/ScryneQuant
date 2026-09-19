"""`sq jev`: gölge koşusu, replay, dondurma, değerlendirme, durum. (K-074)

Ayrı bir Typer alt uygulaması (`cli/testnet.py`, `cli/kill.py` kalıbı): `cli/main.py`ye tek
satırla bağlanır ve `sq`nin geri kalanı bu modülü yüklemeden açılır. Jev süreci trading
sürecinden ayrıdır; burada `PaperMotoru`, `RiskMotoru`, execution **yok**.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import signal
import sys
from pathlib import Path
from typing import Annotated, Any, Final

import pandas as pd
import typer

from scryne_quant.common.zaman import simdi_ms, timeframe_ms, utc_str

jev_app = typer.Typer(
    name="jev",
    help="Jev karar katmanı — yalnızca gölge/ölçüm; sinyal, risk, emir yok (K-074).",
    no_args_is_help=True,
)

VARSAYILAN_KOK: Final = Path("runs/jev")
VARSAYILAN_DEPO: Final = Path("data/market")
VARSAYILAN_FUNDING: Final = Path("data/funding")
VARSAYILAN_SEMANTIK: Final = Path("data/semantik/jev")


def _yol(kosu: str, kok: Path) -> Path:
    return Path(kosu) if kosu.endswith(".sqlite") else kok / f"{kosu}.sqlite"


def _yaz(nesne: Any) -> None:
    typer.echo(json.dumps(nesne, ensure_ascii=False, indent=2, default=str))


def _ayarlar():
    from scryne_quant.jev import ayarlar as ayar_mod

    try:
        return ayar_mod.yukle()
    except ayar_mod.AyarHatasi as e:
        typer.echo(f"config/jev.json: {e}", err=True)
        raise typer.Exit(2) from e


def _barlar_ve_funding(
    ayarlar: Any, depo: Path, funding_depo: Path
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    from scryne_quant.data.depo import ParquetDepo

    parquet = ParquetDepo(depo)
    if not parquet.var_mi(ayarlar.sembol, "1h"):
        typer.echo(f"{depo}: {ayarlar.sembol} 1h yok — önce `sq data indir`", err=True)
        raise typer.Exit(2)
    barlar = parquet.oku(ayarlar.sembol, "1h")
    f_yol = funding_depo / f"{ayarlar.sembol}.parquet"
    funding = pd.read_parquet(f_yol) if f_yol.exists() else None
    return barlar, funding


# ------------------------------------------------------------------ tekrar


@jev_app.command("tekrar")
def tekrar(
    kosu: Annotated[str, typer.Option("--kosu", help="Koşu adı; runs/jev/<kosu>.sqlite")],
    son_n_bar: Annotated[
        int, typer.Option("--son-n-bar", help="Serinin sonundan kaç bar (karar sayısı).")
    ] = 48,
    bitis_utc: Annotated[
        str | None,
        typer.Option("--bitis-utc", help="Son karar barı (ISO, UTC). Yoksa serinin sonu."),
    ] = None,
    kuru: Annotated[
        bool, typer.Option("--kuru", help="Jev'e sorma; yalnızca durum + hash.")
    ] = False,
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    depo: Annotated[Path, typer.Option("--depo")] = VARSAYILAN_DEPO,
    funding_depo: Annotated[Path, typer.Option("--funding-depo")] = VARSAYILAN_FUNDING,
    sembol: Annotated[
        str | None,
        typer.Option("--sembol", help="config/jev.json'daki sembol yerine (K-076: çoklu sembol replay)."),
    ] = None,
) -> None:
    """Tarihsel replay: durum → Jev → defter. **Backtest değil**; kanıt yalnız `leak_riski=false` satırlarda."""
    from dataclasses import replace

    from scryne_quant.common.hash import dosya_hash
    from scryne_quant.data.depo import ParquetDepo
    from scryne_quant.features.barlar import bar_dizileri
    from scryne_quant.jev import istemci as istemci_mod
    from scryne_quant.jev.defter import JevDefteri
    from scryne_quant.jev.durum import PENCERE_BAR
    from scryne_quant.jev.tekrar import TekrarHatasi, tekrar_kos

    ayarlar = _ayarlar()
    if sembol is not None:
        ayarlar = replace(ayarlar, sembol=sembol.upper())
    barlar, funding = _barlar_ve_funding(ayarlar, depo, funding_depo)
    diziler = bar_dizileri(barlar)
    n = len(barlar)
    son = n - 1
    if bitis_utc is not None:
        hedef = int(pd.Timestamp(bitis_utc, tz="UTC").timestamp() * 1000)
        eslesen = barlar.index[barlar.open_time <= hedef]
        if not len(eslesen):
            typer.echo("bitiş tarihi serinin başından önce", err=True)
            raise typer.Exit(2)
        son = int(eslesen[-1])
    ilk = max(PENCERE_BAR - 1, son - son_n_bar + 1)

    yol = _yol(kosu, kok)
    typer.echo(
        f"replay {ayarlar.sembol} 1h  bar {ilk}..{son}  "
        f"({utc_str(int(barlar.open_time.iloc[ilk]))} → {utc_str(int(barlar.open_time.iloc[son]))})"
        f"  kuru={kuru}  defter={yol}"
    )
    istemci = None if kuru else istemci_mod.typesafe_istemci(ayarlar)

    def ilerleme(k: int, toplam: int) -> None:
        if k % 25 == 0 or k == toplam:
            typer.echo(f"  {k}/{toplam}", err=True)

    try:
        with JevDefteri(yol) as defter:
            oz = tekrar_kos(
                diziler,
                ayarlar=ayarlar,
                defter=defter,
                kosu=kosu,
                ilk=ilk,
                son=son,
                istemci=istemci,
                funding_time_ms=None if funding is None else funding.funding_time.to_numpy(),
                funding_rate=None if funding is None else funding.funding_rate.to_numpy(),
                ilerleme=ilerleme,
            )
            sonuc = oz.sozluk()
            sonuc["zincir_gecerli"] = defter.dogrula()
            sonuc["girdi_sha256"] = {"1h": ParquetDepo(depo).sha256(ayarlar.sembol, "1h")}
            if funding is not None:
                sonuc["girdi_sha256"]["funding"] = dosya_hash(
                    funding_depo / f"{ayarlar.sembol}.parquet"
                )
    except TekrarHatasi as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2) from e
    finally:
        if istemci is not None and hasattr(istemci, "close"):
            istemci.close()
    sonuc["leak_riski"] = (
        "kesime göre" if ayarlar.egitim_kesim_ms is not None
        else "yayın tarihine göre: karar barı yayından sonra açılıyorsa yok (K-075)"
        if ayarlar.yayin_ms is not None
        else True
    )
    sonuc["not"] = "replay kanıtı yalnız leak_riski=false satırlarda (K-074/3, K-075)"
    _yaz(sonuc)


@jev_app.command("dondur")
def dondur_komutu(
    kosu: Annotated[str, typer.Option("--kosu")],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    semantik: Annotated[Path, typer.Option("--semantik")] = VARSAYILAN_SEMANTIK,
    depo: Annotated[Path, typer.Option("--depo")] = VARSAYILAN_DEPO,
) -> None:
    """Defteri Parquet + manifest olarak dondurur (`data/semantik/jev/<turetim_id>/`)."""
    from scryne_quant.data.depo import ParquetDepo
    from scryne_quant.jev.defter import JevDefteri
    from scryne_quant.jev.tekrar import TekrarHatasi, dondur

    ayarlar = _ayarlar()
    girdi = {}
    parquet = ParquetDepo(depo)
    if parquet.var_mi(ayarlar.sembol, "1h"):
        girdi["1h"] = parquet.sha256(ayarlar.sembol, "1h")
    try:
        with JevDefteri(_yol(kosu, kok)) as defter:
            dizin, manifest = dondur(defter, ayarlar=ayarlar, kok=semantik, girdi_sha256=girdi)
    except TekrarHatasi as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2) from e
    typer.echo(f"donduruldu: {dizin}")
    _yaz(
        {
            k: manifest[k]
            for k in (
                "turetim_id",
                "satir",
                "gecerli",
                "leak_riski",
                "kapsam_baslangic_ms",
                "kapsam_bitis_ms",
            )
        }
    )


# ------------------------------------------------------------------ gölge


@jev_app.command("golge")
def golge(
    kosu: Annotated[str, typer.Option("--kosu", help="Koşu adı; runs/jev/<kosu>.sqlite")],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    depo: Annotated[Path, typer.Option("--depo")] = VARSAYILAN_DEPO,
    kuru: Annotated[
        bool,
        typer.Option("--kuru", help="Ağa çıkmadan kurulumu doğrula (ısınma + funding), koşma."),
    ] = False,
) -> None:
    """Gölge koşusu: kapanmış her 1h barda durum → Jev → defter. Emir yok. Ayrı süreç."""
    from scryne_quant.exchange.akis import BinanceBarAkisi
    from scryne_quant.exchange.binance import BinanceAdaptoru
    from scryne_quant.exchange.turev_rest import BinanceTurevRest
    from scryne_quant.jev import istemci as istemci_mod
    from scryne_quant.jev.defter import JevDefteri
    from scryne_quant.jev.golge import (
        FUNDING_GECMIS_MS,
        GolgeKosturucu,
        GolgeMotoru,
        isinma_barlari,
    )
    from scryne_quant.live import durdurma as durdurma_mod
    from scryne_quant.live import kill as kill_mod
    from scryne_quant.live.kilit import KilitAlinamadi, KosuKilidi

    ayarlar = _ayarlar()
    yol = _yol(kosu, kok)
    yol.parent.mkdir(parents=True, exist_ok=True)
    try:
        kilit = KosuKilidi(yol).al()
    except KilitAlinamadi as e:
        typer.echo(f"koşu zaten açık: {e}", err=True)
        raise typer.Exit(2) from e
    durdurma_mod.temizle(yol)
    # Süreç kimliği: izleme/pano "süreç yaşıyor mu" sorusunu buradan cevaplar (K-065 kalıbı).
    kill_mod.pid_yaz(yol)

    adaptor = BinanceAdaptoru()
    turev = BinanceTurevRest()
    istemci = istemci_mod.typesafe_istemci(ayarlar)
    defter = JevDefteri(yol)
    try:
        motor = GolgeMotoru(
            kosu=kosu,
            ayarlar=ayarlar,
            defter=defter,
            istemci=istemci,
            funding_kaynagi=turev.funding,
        )
        # Bağlantı ısıtma: ilk TypeSafe çağrısı DNS yüzünden ~13 s (Spike 7); bunu ilk barın
        # 20 s'lik zaman aşımına bindirmek yerine başlangıçta ödüyoruz. Başarısızlık koşuyu
        # durdurmaz; ilk bar o zaman kendi hatasını fail-closed olarak yazar.
        try:
            istemci.models.list()
        except Exception as e:  # noqa: BLE001 - kayda geçer, koşuyu durdurmaz
            typer.echo(f"uyarı: TypeSafe bağlantı ısıtması başarısız: {type(e).__name__}", err=True)
        barlar = isinma_barlari(ayarlar.sembol, depo_kok=depo, adaptor=adaptor)
        motor.isinma(barlar)
        simdi = simdi_ms()
        motor.funding_yukle(turev.funding(ayarlar.sembol, simdi - FUNDING_GECMIS_MS))
        typer.echo(
            f"gölge {kosu}: pencere {len(motor.pencere)} bar "
            f"(son {utc_str(motor.pencere.son_ms) if motor.pencere.son_ms else '-'}), "
            f"funding {motor.ozet()['funding_odeme']} ödeme, model {ayarlar.model}, defter {yol}"
        )
        if kuru:
            _yaz(motor.ozet())
            return

        akis = BinanceBarAkisi(ayarlar.sembol, "1h", adaptor=adaptor)
        kosturucu = GolgeKosturucu(
            motor,
            akis,
            bar_kancasi=lambda s: typer.echo(
                f"{utc_str(s.bar_ms)}  "
                + (
                    f"{s.karar.durum}"
                    + (
                        f"  yon={s.karar.yon} P={s.karar.yon_olasiliklari} rejim={s.karar.rejim} "
                        f"kurulum={s.karar.kurulum_skor} cekimser={s.karar.cekimser} "
                        f"{s.karar.gecikme_ms} ms"
                        if s.karar is not None and s.karar.gecerli
                        else f"  {s.sebep}"
                    )
                    if s.karar is not None
                    else f"atlandı: {s.sebep}"
                )
            ),
            durdurma_istegi=lambda: durdurma_mod.istek(yol),
        )

        def _sinyal(*_: object) -> None:
            typer.echo("durduruluyor…", err=True)
            kosturucu.durdur()

        for s in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(ValueError, OSError):  # ana iş parçacığı değilse
                signal.signal(s, _sinyal)
        ozet = asyncio.run(kosturucu.calistir())
        _yaz(ozet)
    finally:
        defter.kapat()
        if hasattr(istemci, "close"):
            istemci.close()
        kilit.kapat()


@jev_app.command("durdur")
def durdur(
    kosu: Annotated[str, typer.Option("--kosu")],
    sebep: Annotated[str, typer.Option("--sebep")] = "elle durduruldu",
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
) -> None:
    """Gölge koşusuna düzgün durdurma isteği bırakır (K-043 bayrak kalıbı)."""
    from scryne_quant.live import durdurma as durdurma_mod

    bayrak = durdurma_mod.dur_iste(_yol(kosu, kok), sebep=sebep)
    typer.echo(f"durdurma isteği yazıldı: {bayrak}")


# ------------------------------------------------------------------ durum / değerlendirme


@jev_app.command("durum")
def durum(
    kosu: Annotated[str, typer.Option("--kosu")],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    son: Annotated[int, typer.Option("--son", help="Son kaç karar gösterilsin.")] = 5,
) -> None:
    """Koşunun özeti: sayım, zincir, son kararlar, olaylar."""
    from scryne_quant.jev.defter import JevDefteri

    yol = _yol(kosu, kok)
    if not yol.exists():
        typer.echo(f"defter yok: {yol}", err=True)
        raise typer.Exit(2)
    with JevDefteri(yol) as defter:
        kararlar = defter.kararlar()
        gecikmeler = sorted(
            int(k["karar"]["gecikme_ms"]) for k in kararlar if k["karar"].get("gecikme_ms")
        )

        def p(q: float) -> int | None:
            if not gecikmeler:
                return None
            return gecikmeler[min(len(gecikmeler) - 1, int(q * len(gecikmeler)))]

        _yaz(
            {
                "kosu": defter.kosu_oku(),
                "sayim": defter.sayim(),
                "zincir_gecerli": defter.dogrula(),
                "son_karar_utc": utc_str(defter.son_karar_ms()) if defter.son_karar_ms() else None,
                "gecikme_ms": {"p50": p(0.5), "p95": p(0.95), "p99": p(0.99)},
                "yon_dagilimi": _dagilim(kararlar, "yon"),
                "rejim_dagilimi": _dagilim(kararlar, "rejim"),
                "son_kararlar": [
                    {
                        "karar_utc": k["karar_utc"],
                        "durum": k["durum_kodu"],
                        "yon": k["karar"].get("yon"),
                        "P": k["karar"].get("yon_olasiliklari"),
                        "rejim": k["karar"].get("rejim"),
                        "cekimser": k["karar"].get("cekimser"),
                        "hata": k["karar"].get("hata"),
                    }
                    for k in kararlar[-son:]
                ],
                "son_olaylar": [
                    {"tur": o["tur"], "utc": o["zaman_utc"], "ayrinti": o["ayrinti"]}
                    for o in defter.olaylar()[-son:]
                ],
            }
        )


def _dagilim(kararlar: list[dict[str, Any]], alan: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for k in kararlar:
        v = k["karar"].get(alan)
        if v is not None:
            out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items()))


@jev_app.command("degerlendir")
def degerlendir_komutu(
    kosu: Annotated[str, typer.Option("--kosu")],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    depo: Annotated[Path, typer.Option("--depo")] = VARSAYILAN_DEPO,
    rest: Annotated[
        bool, typer.Option("--rest", help="Karar penceresinin barlarını Binance REST'ten tamamla.")
    ] = False,
    yaz: Annotated[bool, typer.Option("--yaz/--yazma", help="Raporu runs/jev/ altına yaz.")] = True,
) -> None:
    """Kararları ileri sonuçlarla bağlar; önceden tanımlı ölçütlerle rapor üretir."""
    from scryne_quant.common import maliyet as maliyet_mod
    from scryne_quant.data.depo import ParquetDepo
    from scryne_quant.jev.defter import JevDefteri
    from scryne_quant.jev.sonuc import defterden_cerceve, degerlendir, sonuclari_bagla

    ayarlar = _ayarlar()
    yol = _yol(kosu, kok)
    if not yol.exists():
        typer.echo(f"defter yok: {yol}", err=True)
        raise typer.Exit(2)
    with JevDefteri(yol) as defter:
        kararlar = defterden_cerceve(defter.kararlar())
        kimlik = defter.kosu_oku()
    if kararlar.empty:
        typer.echo("defterde karar yok", err=True)
        raise typer.Exit(2)

    parquet = ParquetDepo(depo)
    barlar = (
        parquet.oku(ayarlar.sembol, "1h")
        if parquet.var_mi(ayarlar.sembol, "1h")
        else pd.DataFrame(columns=["open_time", "open", "high", "low", "close"])
    )
    if rest:
        barlar = _rest_ile_tamamla(barlar, ayarlar.sembol, int(kararlar.karar_ms.min()))
    maliyet = maliyet_mod.yukle()
    bagli = sonuclari_bagla(kararlar, barlar, ayarlar=ayarlar, maliyet=maliyet)
    rapor = degerlendir(bagli, ayarlar=ayarlar)
    rapor["kosu"] = kimlik
    rapor["maliyet"] = maliyet.sozluk()
    rapor["uretildi_utc"] = utc_str(simdi_ms())
    if yaz:
        cikti = kok / f"{Path(yol).stem}-degerlendirme-{simdi_ms()}.json"
        cikti.write_text(
            json.dumps(rapor, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
        )
        typer.echo(f"rapor: {cikti}", err=True)
    _yaz(rapor)


def _rest_ile_tamamla(barlar: pd.DataFrame, sembol: str, baslangic_ms: int) -> pd.DataFrame:
    """Depodaki serinin sonrasını (ya da karar penceresini) REST'ten çeker, birleştirir.

    Kalite bayrağı yok: sonuç hesabı ham OHLC okur, karar vermez. Depoya **yazılmaz** — depo
    `sq data indir`in alanı (K-056/1: kaynaklar karıştırılmaz).
    """
    from scryne_quant.exchange.binance import BinanceAdaptoru

    adaptor = BinanceAdaptoru()
    adim = timeframe_ms("1h")
    simdi = adaptor.sunucu_zamani_ms()
    bas = min(baslangic_ms - adim, int(barlar.open_time.max()) + adim if len(barlar) else simdi)
    parcalar = []
    while bas < simdi:
        yeni = adaptor.klines(sembol, "1h", bas, simdi)
        if yeni.empty:
            break
        parcalar.append(yeni)
        bas = int(yeni.open_time.iloc[-1]) + adim
    if not parcalar:
        return barlar
    ek = pd.concat(parcalar, ignore_index=True)
    birlesik = pd.concat(
        [barlar[[c for c in ek.columns if c in barlar.columns]], ek], ignore_index=True
    )
    birlesik = birlesik.drop_duplicates("open_time", keep="last").sort_values("open_time")
    return birlesik.reset_index(drop=True)


__all__ = ["jev_app"]

if __name__ == "__main__":  # pragma: no cover
    sys.exit(jev_app())
