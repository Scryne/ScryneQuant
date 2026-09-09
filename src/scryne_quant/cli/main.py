"""`sq` komut satırı arayüzü. (K-012)

Faz 1-5'in **tek** arayüzü burasıdır; grafik arayüz Faz 6'da gelir. Komutlar bilerek dar
ve tekrar çalıştırılabilir: aynı komutu iki kez çalıştırmak bir şeyi bozmamalı, yalnızca
"değişiklik yok" demeli.

Çıktı formatı ikili: insan için tablo, makine için `--json`. İkincisi olmadan bir komutun
sonucu başka bir komuta veya bir teste giremez.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from scryne_quant.backtest.motor import Backtest
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import git_durumu, ortam_kaydi
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.data.dogrulama import rapor_cikar
from scryne_quant.data.indirici import TarihselIndirici
from scryne_quant.data.kalibrasyon import (
    KALIBRASYON_TIMEFRAME,
    VARSAYILAN_PERSENTIL,
    YONTEM,
    kalibre_et,
)
from scryne_quant.exchange.binance import BinanceAdaptoru
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.research import analiz as analiz_mod
from scryne_quant.research import bolme, tekrar
from scryne_quant.research import degerlendirme as degerlendirme_mod
from scryne_quant.research import deney as deney_mod
from scryne_quant.research import karsilastirma as karsilastirma_mod
from scryne_quant.research import tarama as tarama_mod
from scryne_quant.research import walkforward as wf_mod
from scryne_quant.research.izgaralar import izgara as varsayilan_izgara
from scryne_quant.strategy.kutuphane import KIYAS, KUTUPHANE, coz
from scryne_quant.strategy.kutuphane import aile as _aile
from scryne_quant.strategy.kutuphane.sma_kesisim import SmaKesisim

#: Backtest sonuç kayıtlarının yazıldığı dizin (`.gitignore`'da).
VARSAYILAN_KOSU_KOKU = Path("runs")

#: Varsayılan depo kökü. `.gitignore` `/data/`'yı dışlıyor — market verisi repoya girmez.
VARSAYILAN_DEPO = Path("data/market")

app = typer.Typer(
    name="sq",
    help="ScryneQuant — quant altyapısı komut satırı.",
    no_args_is_help=True,
    add_completion=False,
)
data_app = typer.Typer(name="data", help="Market verisi: indirme, kalite, kalibrasyon.")
app.add_typer(data_app)
lab_app = typer.Typer(
    name="lab",
    help="Strateji laboratuvarı: tarama, walk-forward, Monte Carlo, stres, karşılaştırma.",
)
app.add_typer(lab_app)

Depo = Annotated[Path, typer.Option("--depo", help="Parquet depo kökü.")]
JsonCikti = Annotated[bool, typer.Option("--json", help="Çıktıyı JSON olarak ver.")]


def _yaz_json(nesne: Any) -> None:
    typer.echo(json.dumps(nesne, ensure_ascii=False, indent=2, sort_keys=True))


def _yil_once_ms(yil: float) -> int:
    """`yil` yıl öncesinin epoch ms'i. 365,25 gün/yıl — artık yıl sessizce kaymasın."""
    return simdi_ms() - int(yil * 365.25 * 86_400_000)


def _tarih_ms(deger: str | None, yil: float | None) -> int:
    """`--baslangic` (YYYY-MM-DD) veya `--yil` seçeneğini epoch ms'e çevirir."""
    if deger and yil is not None:
        raise typer.BadParameter("--baslangic ve --yil birlikte verilemez")
    if deger:
        try:
            gun = dt.datetime.strptime(deger, "%Y-%m-%d").replace(tzinfo=dt.UTC)
        except ValueError as hata:
            raise typer.BadParameter(f"tarih YYYY-MM-DD olmalı: {deger!r}") from hata
        return int(gun.timestamp() * 1000)
    if yil is None:
        raise typer.BadParameter("--baslangic ya da --yil verilmeli")
    return _yil_once_ms(yil)


# ---------------------------------------------------------------- data indir


@data_app.command("indir")
def data_indir(
    sembol: Annotated[str, typer.Argument(help="Örn. BTCUSDT")],
    timeframe: Annotated[str, typer.Argument(help="Örn. 1h veya 1m")],
    baslangic: Annotated[str | None, typer.Option("--baslangic", help="YYYY-MM-DD (UTC)")] = None,
    yil: Annotated[float | None, typer.Option("--yil", help="Kaç yıl geriye inilecek")] = None,
    bitis: Annotated[
        str | None, typer.Option("--bitis", help="YYYY-MM-DD (UTC), dışlayıcı")
    ] = None,
    depo_kok: Depo = VARSAYILAN_DEPO,
    json_cikti: JsonCikti = False,
) -> None:
    """Tarihsel barları indirir, doğrular ve depoya yazar.

    Kaldığı yerden devam eder: yalnızca depoda **olmayan** aralıklar indirilir. Aynı
    komutu ikinci kez çalıştırmak dosyayı değiştirmez (Faz 1 idempotency kriteri) —
    çıktıdaki `degisti` alanı bunu doğrudan gösterir.
    """
    baslangic_ms = _tarih_ms(baslangic, yil)
    bitis_ms = _tarih_ms(bitis, None) if bitis else None

    indirici = TarihselIndirici(BinanceAdaptoru(), ParquetDepo(depo_kok))

    def ilerleme(bar: int, cagri: int) -> None:
        if not json_cikti and cagri % 25 == 0:
            typer.echo(f"  … {bar:>9,} bar / {cagri:>4} çağrı", err=True)

    sonuc = indirici.indir(sembol, timeframe, baslangic_ms, bitis_ms, ilerleme=ilerleme)

    if json_cikti:
        _yaz_json(sonuc.sozluk())
        return

    k = sonuc.kalite
    typer.echo(f"{sonuc.sembol} {sonuc.timeframe}  {sonuc.aralik}")
    typer.echo(
        f"  inen bar      : {sonuc.inen_bar:,} "
        f"({sonuc.cagri_sayisi} çağrı, {sonuc.sure_s:.1f} s)"
    )
    typer.echo(
        f"  depoda toplam : {sonuc.depo.bar_sayisi:,} bar, "
        f"{sonuc.depo.bayt / 1024**2:.2f} MB"
    )
    typer.echo(f"  aralık        : {utc_str(k.ilk_ms)} → {utc_str(k.son_ms)}")
    typer.echo(
        f"  kalite        : ok %{k.ok_orani * 100:.4f} · "
        f"eksik {k.eksik_bar} · boşluk {k.bosluk_sayisi}"
    )
    typer.echo(f"  sha256        : {sonuc.depo.sha256}")
    typer.echo(f"  değişti       : {'evet' if sonuc.degisti else 'HAYIR (idempotent)'}")


# -------------------------------------------------------------- data quality


@data_app.command("quality")
def data_quality(
    sembol: Annotated[str, typer.Argument(help="Örn. BTCUSDT")],
    timeframe: Annotated[str, typer.Argument(help="Örn. 1h")],
    depo_kok: Depo = VARSAYILAN_DEPO,
    rapor: Annotated[
        Path | None, typer.Option("--rapor", help="JSON raporun yazılacağı yol")
    ] = None,
    json_cikti: JsonCikti = False,
) -> None:
    """Depodaki bir veri setinin kalite raporunu üretir. (K-006)

    Bayrakları yeniden hesaplamaz — depodaki bayrak indirme anındaki doğrulamanın
    sonucudur. Rapor onu sayar, boşlukları timestamp dizisinden çıkarır.
    """
    depo = ParquetDepo(depo_kok)
    df = depo.oku(sembol, timeframe)
    kalite = rapor_cikar(df, timeframe, sembol=sembol.upper())

    govde = {
        "uretildi": utc_str(simdi_ms()),
        "dosya": str(depo.yol(sembol, timeframe)),
        "veri_sha256": depo.sha256(sembol, timeframe),
        "git": git_durumu(),
        "ortam": ortam_kaydi(),
        "kalite": kalite.sozluk(),
    }
    if rapor is not None:
        rapor.parent.mkdir(parents=True, exist_ok=True)
        rapor.write_text(
            json.dumps(govde, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if json_cikti:
        _yaz_json(govde)
        return

    typer.echo(f"{kalite.sembol} {kalite.timeframe}")
    typer.echo(f"  bar           : {kalite.bar_sayisi:,} / beklenen {kalite.beklenen_bar:,}")
    typer.echo(f"  aralık        : {utc_str(kalite.ilk_ms)} → {utc_str(kalite.son_ms)}")
    typer.echo(f"  kapsama       : %{kalite.kapsama * 100:.4f}  (eksik {kalite.eksik_bar})")
    typer.echo(f"  ok oranı      : %{kalite.ok_orani * 100:.4f}")
    for bayrak, sayi in kalite.bayraklar.items():
        typer.echo(f"    {bayrak:<12}: {sayi:,}")
    if kalite.bosluk_sayisi:
        typer.echo(f"  boşluk        : {kalite.bosluk_sayisi}")
        for b in kalite.bosluklar[:10]:
            typer.echo(f"    {utc_str(b.baslangic_ms)} → {utc_str(b.bitis_ms)} ({b.eksik_bar} bar)")
    if rapor is not None:
        typer.echo(f"  rapor         : {rapor}")


# ------------------------------------------------------------------ data ls


@data_app.command("ls")
def data_ls(
    depo_kok: Depo = VARSAYILAN_DEPO,
    json_cikti: JsonCikti = False,
) -> None:
    """Depodaki veri setlerini listeler."""
    kok = Path(depo_kok)
    satirlar: list[dict[str, Any]] = []
    depo = ParquetDepo(kok)
    for yol in sorted(kok.glob("*/*.parquet")):
        sembol, timeframe = yol.parent.name, yol.stem
        df = depo.oku(sembol, timeframe)
        satirlar.append(
            {
                "sembol": sembol,
                "timeframe": timeframe,
                "bar": len(df),
                "ilk": utc_str(int(df["open_time"].iloc[0])),
                "son": utc_str(int(df["open_time"].iloc[-1])),
                "mb": round(yol.stat().st_size / 1024**2, 2),
                "sha256": depo.sha256(sembol, timeframe),
            }
        )

    if json_cikti:
        _yaz_json(satirlar)
        return
    if not satirlar:
        typer.echo(f"depo boş: {kok}")
        return
    for s in satirlar:
        typer.echo(
            f"{s['sembol']:<10} {s['timeframe']:<4} {s['bar']:>9,} bar  "
            f"{s['ilk']} → {s['son']}  {s['mb']:>7.2f} MB  {s['sha256'][:12]}"
        )


# ------------------------------------------------------ data slippage-kalibre


@data_app.command("slippage-kalibre")
def data_slippage_kalibre(
    sembol: Annotated[str, typer.Argument(help="Örn. BTCUSDT")] = "BTCUSDT",
    timeframe: Annotated[str, typer.Option("--timeframe")] = KALIBRASYON_TIMEFRAME,
    persentil: Annotated[float, typer.Option("--persentil")] = VARSAYILAN_PERSENTIL,
    depo_kok: Depo = VARSAYILAN_DEPO,
    config: Annotated[Path, typer.Option("--config")] = maliyet_mod.VARSAYILAN_YOL,
    gerekce: Annotated[
        str, typer.Option("--gerekce", help="Persentil seçiminin gerekçesi")
    ] = "",
    yaz: Annotated[
        bool, typer.Option("--yaz", help="Sonucu maliyet konfigürasyonuna işle")
    ] = False,
    json_cikti: JsonCikti = False,
) -> None:
    """`slippage_bps`'i 1m veriden kalibre eder. (K-021)

    Varsayılan olarak yalnızca ölçer ve gösterir. `--yaz` verilirse konfigürasyondaki
    geçici değeri kalıcı olarak değiştirir ve `gecici` bayrağını kaldırır — o yüzden
    `--gerekce` zorunludur: gerekçesiz bir kalibrasyon, K-021'in yerine geçtiği K-020'nin
    hatasını tekrarlamaya açık kapı bırakır.
    """
    depo = ParquetDepo(depo_kok)
    df = depo.oku(sembol, timeframe)
    sonuc = kalibre_et(df, sembol=sembol, timeframe=timeframe, persentil=persentil)
    govde: dict[str, Any] = {"olcum": sonuc.sozluk(), "yazildi": False}

    if yaz:
        if not gerekce.strip():
            raise typer.BadParameter("--yaz için --gerekce zorunlu (K-021)")
        mevcut = maliyet_mod.yukle(config)
        kalibrasyon = maliyet_mod.SlippageKalibrasyonu(
            yontem=YONTEM,
            persentil=sonuc.persentil,
            deger_bps=round(sonuc.deger_bps, 4),
            sembol=sonuc.sembol,
            timeframe=sonuc.timeframe,
            aralik_baslangic_ms=sonuc.ilk_ms,
            aralik_bitis_ms=sonuc.son_ms,
            bar_sayisi=sonuc.kullanilan_bar,
            veri_sha256=depo.sha256(sembol, timeframe),
            dagilim_bps={k: round(v, 4) for k, v in sonuc.dagilim_bps.items()},
            tarih=dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"),
            gerekce=gerekce.strip(),
        )
        yeni = maliyet_mod.MaliyetModeli(
            fee_taker_bps=mevcut.fee_taker_bps,
            slippage_bps=round(sonuc.deger_bps, 4),
            kalibrasyon=kalibrasyon,
        )
        maliyet_mod.yaz(yeni, config)
        govde["yazildi"] = True
        govde["config"] = str(config)
        govde["maliyet"] = yeni.sozluk()

    if json_cikti:
        _yaz_json(govde)
        return

    typer.echo(
        f"{sonuc.sembol} {sonuc.timeframe}  "
        f"{utc_str(sonuc.ilk_ms)} → {utc_str(sonuc.son_ms)}"
    )
    typer.echo(
        f"  kullanılan    : {sonuc.kullanilan_bar:,} hareket "
        f"({sonuc.atilan_bar:,} atıldı)"
    )
    typer.echo("  1dk hareket (bps):")
    for ad, deger in sonuc.dagilim_bps.items():
        typer.echo(f"    {ad:<5}: {deger:>10.4f}")
    typer.echo("  1m bar içi salınım (bps):")
    for ad, deger in sonuc.bar_ici_salinim_bps.items():
        typer.echo(f"    {ad:<5}: {deger:>10.4f}")
    typer.echo(f"  seçilen p{sonuc.persentil:g} → slippage_bps = {sonuc.deger_bps:.4f}")
    if govde["yazildi"]:
        typer.echo(f"  yazıldı       : {config} (gecici bayrağı kalktı)")
    else:
        typer.echo("  yazılmadı     : işlemek için --yaz --gerekce '...'")


# ---------------------------------------------------------------- data maliyet


@data_app.command("maliyet")
def data_maliyet(
    config: Annotated[Path, typer.Option("--config")] = maliyet_mod.VARSAYILAN_YOL,
    json_cikti: JsonCikti = False,
) -> None:
    """Yürürlükteki maliyet modelini gösterir. (K-007)"""
    model = maliyet_mod.yukle(config)
    if json_cikti:
        _yaz_json(model.sozluk())
        return
    typer.echo(f"fee_taker_bps   : {model.fee_taker_bps}")
    typer.echo(f"slippage_bps    : {model.slippage_bps}")
    typer.echo(f"gidiş-dönüş     : {model.gidis_donus_bps} bps")
    if model.gecici:
        typer.echo(
            "durum           : GEÇİCİ — bu modelle üretilen sonuç "
            "promotion'a giremez (K-021)"
        )
    else:
        k = model.kalibrasyon
        assert k is not None
        typer.echo(
            f"durum           : kalibre ({k.tarih}, p{k.persentil:g}, "
            f"{k.sembol} {k.timeframe})"
        )
        typer.echo(f"gerekçe         : {k.gerekce}")


# --------------------------------------------------------------------- yardım


# ------------------------------------------------------------------- backtest


@app.command("backtest")
def backtest(
    sembol: Annotated[str, typer.Argument(help="Örn. BTCUSDT")] = "BTCUSDT",
    timeframe: Annotated[str, typer.Option("--timeframe", "-t")] = "1h",
    hizli: Annotated[int, typer.Option("--hizli", help="Hızlı SMA penceresi.")] = 20,
    yavas: Annotated[int, typer.Option("--yavas", help="Yavaş SMA penceresi.")] = 50,
    maruziyet: Annotated[float, typer.Option("--maruziyet", help="Giriş hedefi [0,1].")] = 0.2,
    sermaye: Annotated[float, typer.Option("--sermaye")] = 10_000.0,
    seed: Annotated[int, typer.Option("--seed", help="Kayda yazılır (K-009).")] = 0,
    kayit: Annotated[
        bool, typer.Option("--kayit/--kayit-yok", help="Sonucu runs/ altına yaz.")
    ] = True,
    egri: Annotated[bool, typer.Option("--egri", help="Equity eğrisini de kaydet.")] = False,
    depo: Depo = VARSAYILAN_DEPO,
    json_cikti: JsonCikti = False,
) -> None:
    """SMA kesişim stratejisini depodaki veri üzerinde backtest eder. (Faz 3)

    Faz 4'te strateji seçimi parametreleşecek; şimdilik tek referans strateji var ve
    komutu ona sabitlemek, olmayan bir esnekliği varmış gibi göstermekten iyi.
    """
    depo_nesnesi = ParquetDepo(depo)
    df = depo_nesnesi.oku(sembol, timeframe)
    model = maliyet_mod.yukle()

    strateji = SmaKesisim(hizli=hizli, yavas=yavas, maruziyet=maruziyet)
    motor = Backtest(strateji, model, baslangic_sermaye=sermaye, seed=seed)
    sonuc = motor.calistir(
        sembol,
        timeframe,
        bar_dizileri(df),
        veri_sha256=depo_nesnesi.sha256(sembol, timeframe),
    )

    yol: Path | None = None
    if kayit:
        yol = sonuc.yaz(
            VARSAYILAN_KOSU_KOKU / f"{sonuc.config_hash[:12]}-{sonuc.sonuc_hash[:12]}.json",
            egri=egri,
        )

    if json_cikti:
        govde = sonuc.sozluk(egri=egri)
        govde["kayit_yolu"] = str(yol) if yol else None
        _yaz_json(govde)
        return

    m = sonuc.metrikler
    typer.echo(f"{sembol} {timeframe} · {sonuc.veri.bar_sayisi:,} bar · {strateji!r}")
    typer.echo(f"  {utc_str(sonuc.veri.ilk_ms)} → {utc_str(sonuc.veri.son_ms)}")
    typer.echo("")
    typer.echo(f"  sermaye     : {m.baslangic_sermaye:>14,.2f} → {m.bitis_sermaye:>14,.2f}")
    typer.echo(f"  toplam getiri: {m.toplam_getiri:>13.2%}")
    typer.echo(f"  CAGR        : {m.cagr:>14.2%}{'' if m.yillik_anlamli else '  (pencere kısa)'}")
    typer.echo(f"  max drawdown: {m.max_drawdown:>14.2%}  ({m.max_drawdown_bar:,} bar)")
    typer.echo(f"  Sharpe      : {m.sharpe:>14.3f}    Sortino: {m.sortino:.3f}")
    typer.echo(f"  Calmar      : {m.calmar:>14.3f}    Volatilite: {m.yillik_volatilite:.2%}")
    typer.echo("")
    typer.echo(f"  işlem       : {m.islem_sayisi:>14,}  ({m.kazanan} kazanç / {m.kaybeden} kayıp)")
    typer.echo(f"  win rate    : {m.win_rate:>14.1%}    profit factor: {m.profit_factor:.3f}")
    typer.echo(f"  expectancy  : {m.expectancy:>14,.2f}    ardışık kayıp: {m.ardisik_kayip}")
    typer.echo(f"  ort. tutma  : {m.ortalama_tutma_bar:>14.1f} bar")
    typer.echo("")
    typer.echo(f"  komisyon    : {m.toplam_komisyon:>14,.2f}")
    typer.echo(f"  slippage    : {m.toplam_slippage:>14,.2f}")
    typer.echo(f"  hacim       : {m.islem_hacmi:>14,.2f}  (turnover {m.turnover:.1f}×)")
    typer.echo("")
    typer.echo(f"  ok olmayan bar: {sonuc.veri.ok_olmayan_bar} ({sonuc.veri.ok_olmayan_oran:.4%})")
    typer.echo(f"  üretilen sinyal: {sonuc.uretilen_sinyal}")
    atlanan = {a: n for a, n in sonuc.atlanan.items() if n}
    if atlanan:
        typer.echo(f"  atlanan sinyal : {atlanan}")
    typer.echo("")
    typer.echo(f"  config_hash : {sonuc.config_hash[:16]}")
    typer.echo(f"  sonuc_hash  : {sonuc.sonuc_hash[:16]}")
    if sonuc.promotion_engelleri:
        typer.secho(
            f"  promotion engeli: {', '.join(sonuc.promotion_engelleri)}",
            fg=typer.colors.YELLOW,
        )
    if yol:
        typer.echo(f"  kayıt       : {yol}")


# ------------------------------------------------------------------------ lab


def _lab_veri(depo: Path, sembol: str, timeframe: str):
    """Depodan bar dizileri + veri kimliği. Her lab komutunun ilk adımı."""
    d = ParquetDepo(depo)
    return bar_dizileri(d.oku(sembol, timeframe)), d.sha256(sembol, timeframe)


def _maliyet_govdesi(model: maliyet_mod.MaliyetModeli) -> dict[str, Any]:
    """Maliyet modelinin deney kaydına giden hâli.

    Tekrar bu bloğu okur, `config/maliyet.json`ın **bugünkü** hâlini değil — aksi hâlde
    kalibrasyon güncellendiği gün eski deneyler sessizce farklı sonuç verirdi (K-009).
    """
    return {
        "fee_taker_bps": model.fee_taker_bps,
        "slippage_bps": model.slippage_bps,
        "kalibrasyon": model.kalibrasyon.model_dump() if model.kalibrasyon else None,
    }


def _tam_pencere(diziler: dict[str, Any], strateji_adi: str) -> bolme.Pencere:
    """Isınma sonrası tüm veriyi kapsayan pencere."""
    return bolme.Pencere(
        "tam",
        baslangic=karsilastirma_mod.ortak_isinma([strateji_adi]),
        bitis=len(diziler["open_time"]),
        isinma_baslangic=0,
    )


Sembol = Annotated[str, typer.Argument(help="Örn. BTCUSDT")]
Timeframe = Annotated[str, typer.Option("--timeframe", "-t")]
Sermaye = Annotated[float, typer.Option("--sermaye")]
Olcut = Annotated[str, typer.Option("--olcut", help="sharpe | calmar | getiri | profit_factor")]
KayitKok = Annotated[Path, typer.Option("--deney-kok", help="Deney kayıtlarının kökü.")]
StratejiAdi = Annotated[str, typer.Argument(help="Kütüphanedeki strateji adı.")]


@lab_app.command("stratejiler")
def lab_stratejiler(json_cikti: JsonCikti = False) -> None:
    """Kütüphanedeki stratejileri ve varsayılan ızgaralarını listeler."""
    hepsi = {**KUTUPHANE, **KIYAS}
    govde = {
        ad: {
            "sinif": f"{sinif.__module__}.{sinif.__qualname__}",
            "aile": _aile(ad),
            "varsayilan": dict(sinif().parametreler),
            "izgara": {a: list(d) for a, d in varsayilan_izgara(ad).items()},
            "isinma_bar": sinif().isinma_bar(),
        }
        for ad, sinif in hepsi.items()
    }
    if json_cikti:
        _yaz_json(govde)
        return
    for ad, bilgi in govde.items():
        boyut = 1
        for degerler in bilgi["izgara"].values():
            boyut *= len(degerler)
        typer.echo(
            f"{ad:<14} aile={bilgi['aile']:<15} ızgara={boyut:>4} ısınma={bilgi['isinma_bar']}"
        )


@lab_app.command("tara")
def lab_tara(
    strateji: StratejiAdi,
    sembol: Sembol = "BTCUSDT",
    timeframe: Timeframe = "1h",
    oos_orani: Annotated[float, typer.Option("--oos", help="OOS payı [0.1, 0.5].")] = 0.30,
    olcut: Olcut = "sharpe",
    sermaye: Sermaye = 10_000.0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """Bir stratejinin parametre ızgarasını in-sample penceresinde tarar."""
    sinif = coz(strateji)
    diziler, veri_hash = _lab_veri(depo, sembol, timeframe)
    model = maliyet_mod.yukle()
    secenekler = varsayilan_izgara(strateji)

    ins, _ = karsilastirma_mod.ortak_pencereler(
        len(diziler["open_time"]), [strateji], oos_orani=oos_orani
    )
    sonuc = tarama_mod.tara(
        sinif, secenekler, model, sembol, timeframe, diziler, ins,
        olcut=olcut, baslangic_sermaye=sermaye,
    )

    yol = deney_mod.Deney(
        tip="tarama", strateji=strateji, veri_sha256=veri_hash,
        girdi={
            "sembol": sembol, "timeframe": timeframe,
            "izgara": {a: list(d) for a, d in secenekler.items()},
            "pencere": ins.sozluk(), "olcut": olcut,
            "baslangic_sermaye": sermaye, "maliyet": _maliyet_govdesi(model),
            "asgari_islem": sonuc.asgari_islem,
        },
        cikti=sonuc.sozluk(),
    ).yaz(deney_kok)

    if json_cikti:
        _yaz_json({"deney": str(yol), **sonuc.sozluk()})
        return

    en_iyi = sonuc.en_iyi
    typer.echo(f"{strateji} · {sembol} {timeframe} · IS {ins.uzunluk:,} bar · ölçüt={olcut}")
    typer.echo(
        f"  aday {len(sonuc.adaylar)} "
        f"({len(sonuc.gecerliler)} geçerli, ≥{sonuc.asgari_islem} işlem)"
    )
    typer.echo(f"  plato oranı {sonuc.ust_yuzde_plato():.2f}   duyarlılık {sonuc.duyarlilik():.3f}")
    if en_iyi is None:
        typer.secho(
            "  geçerli aday yok — ızgara veya asgari işlem şartı gözden geçirilmeli",
            fg=typer.colors.YELLOW,
        )
    else:
        m = en_iyi.metrikler
        typer.echo(f"  en iyi: {en_iyi.sozluk_parametreler}")
        typer.echo(
            f"    skor {en_iyi.skor:.3f} · işlem {m.islem_sayisi} · getiri {m.toplam_getiri:.1%}"
            f" · maxDD {m.max_drawdown:.1%} · PF {m.profit_factor:.3f}"
        )
    typer.echo(f"  deney: {yol}")


@lab_app.command("walkforward")
def lab_walkforward(
    strateji: StratejiAdi,
    sembol: Sembol = "BTCUSDT",
    timeframe: Timeframe = "1h",
    egitim: Annotated[int, typer.Option("--egitim", help="Eğitim penceresi (bar).")] = 8766,
    test: Annotated[int, typer.Option("--test", help="Test penceresi (bar).")] = 2190,
    sabit_capa: Annotated[
        bool, typer.Option("--sabit-capa", help="Genişleyen eğitim penceresi.")
    ] = False,
    olcut: Olcut = "sharpe",
    sermaye: Sermaye = 10_000.0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """Walk-forward: her katmanda optimize et, sonraki katmanda test et."""
    sinif = coz(strateji)
    diziler, veri_hash = _lab_veri(depo, sembol, timeframe)
    model = maliyet_mod.yukle()
    secenekler = varsayilan_izgara(strateji)

    n = len(diziler["open_time"])
    isinma = karsilastirma_mod.ortak_isinma([strateji])
    katmanlar = bolme.walk_forward(n, isinma, egitim, test, kaydirmali=not sabit_capa)
    sonuc = wf_mod.calistir(
        sinif, secenekler, model, sembol, timeframe, diziler, katmanlar,
        olcut=olcut, baslangic_sermaye=sermaye,
        # Kıyas ölçütünde optimize edilecek bir şey yok ve kapanmış tur da yok.
        asgari_islem=0 if strateji in KIYAS else tarama_mod.ASGARI_ISLEM,
    )

    yol = deney_mod.Deney(
        tip="walk_forward", strateji=strateji, veri_sha256=veri_hash,
        girdi={
            "sembol": sembol, "timeframe": timeframe,
            "izgara": {a: list(d) for a, d in secenekler.items()},
            "bar_sayisi": n, "isinma": isinma, "egitim_bar": egitim, "test_bar": test,
            "kaydirmali": not sabit_capa, "olcut": olcut,
            "baslangic_sermaye": sermaye, "maliyet": _maliyet_govdesi(model),
        },
        cikti=sonuc.sozluk(),
    ).yaz(deney_kok)

    if json_cikti:
        _yaz_json({"deney": str(yol), **sonuc.sozluk()})
        return

    b = sonuc.bilesik_metrikler
    kip = "sabit çapa" if sabit_capa else "kaydırmalı"
    typer.echo(
        f"{strateji} · {sembol} {timeframe} · {len(katmanlar)} katman "
        f"(eğitim {egitim:,} / test {test:,} bar, {kip})"
    )
    typer.echo(f"  başarılı katman: {len(sonuc.basarili_katmanlar)}/{len(sonuc.katmanlar)}")
    typer.echo("")
    typer.echo("  bileşik OOS:")
    typer.echo(
        f"    sermaye {b.baslangic_sermaye:,.0f} → {b.bitis_sermaye:,.2f} "
        f"({b.toplam_getiri:+.1%})"
    )
    typer.echo(
        f"    Sharpe {b.sharpe:.3f} · maxDD {b.max_drawdown:.1%} · "
        f"işlem {b.islem_sayisi} · PF {b.profit_factor:.3f}"
    )
    typer.echo("")
    typer.echo("  parametre kararlılığı (katmanlar arası):")
    kararlilik = sonuc.parametre_kararliligi()
    for ad, bilgi in kararlilik["parametreler"].items():
        ek = f" · dk={bilgi['degisim_katsayisi']:.2f}" if "degisim_katsayisi" in bilgi else ""
        typer.echo(
            f"    {ad:<16} benzersiz {bilgi['benzersiz']}/{kararlilik['katman']}{ek}"
            f"  {bilgi['degerler']}"
        )
    typer.echo(f"  deney: {yol}")


@lab_app.command("montecarlo")
def lab_montecarlo(
    strateji: StratejiAdi,
    sembol: Sembol = "BTCUSDT",
    timeframe: Timeframe = "1h",
    deneme: Annotated[int, typer.Option("--deneme")] = 1_000,
    seed: Annotated[int, typer.Option("--seed")] = 0,
    sermaye: Sermaye = 10_000.0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """İşlem sırasını karıştırıp düşüş dağılımını çıkarır."""
    sinif = coz(strateji)
    diziler, veri_hash = _lab_veri(depo, sembol, timeframe)
    model = maliyet_mod.yukle()
    pencere = _tam_pencere(diziler, strateji)

    nesne = sinif()
    kosu_sonucu = tarama_mod.kosu(
        nesne, model, sembol, timeframe, diziler, pencere, baslangic_sermaye=sermaye
    )
    sonuc = analiz_mod.monte_carlo(kosu_sonucu.islemler, sermaye, deneme=deneme, seed=seed)

    yol = deney_mod.Deney(
        tip="monte_carlo", strateji=strateji, veri_sha256=veri_hash, seed=seed,
        girdi={
            "sembol": sembol, "timeframe": timeframe,
            "parametreler": dict(nesne.parametreler),
            "pencere": pencere.sozluk(), "deneme": deneme,
            "baslangic_sermaye": sermaye, "maliyet": _maliyet_govdesi(model),
        },
        cikti=sonuc.sozluk(),
    ).yaz(deney_kok)

    if json_cikti:
        _yaz_json({"deney": str(yol), **sonuc.sozluk()})
        return

    typer.echo(f"{strateji} · {sonuc.islem_sayisi} işlem · {deneme:,} deneme · seed={seed}")
    typer.echo(
        f"  gerçekleşen: maxDD {sonuc.gercek_max_drawdown:.1%} · "
        f"getiri {sonuc.gercek_getiri:+.1%}"
    )
    typer.echo(
        "  max drawdown dağılımı: "
        + "  ".join(f"{p}={v:.1%}" for p, v in sonuc.drawdown_dagilimi.items())
    )
    typer.echo(
        "  getiri dağılımı      : "
        + "  ".join(f"{p}={v:+.1%}" for p, v in sonuc.getiri_dagilimi.items())
    )
    typer.echo(f"  gerçekleşenden kötü çıkan deneme oranı: {sonuc.kotu_kuyruk_orani:.1%}")
    typer.echo(f"  deney: {yol}")


@lab_app.command("stres")
def lab_stres(
    strateji: StratejiAdi,
    sembol: Sembol = "BTCUSDT",
    timeframe: Timeframe = "1h",
    sermaye: Sermaye = 10_000.0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """Maliyet varsayımlarını bozup stratejinin dayanıklılığını ölçer. (§15.1)"""
    sinif = coz(strateji)
    diziler, veri_hash = _lab_veri(depo, sembol, timeframe)
    model = maliyet_mod.yukle()
    pencere = _tam_pencere(diziler, strateji)

    nesne = sinif()
    sonuc = analiz_mod.stres(
        nesne, model, sembol, timeframe, diziler, pencere, baslangic_sermaye=sermaye
    )

    yol = deney_mod.Deney(
        tip="stres", strateji=strateji, veri_sha256=veri_hash,
        girdi={
            "sembol": sembol, "timeframe": timeframe,
            "parametreler": dict(nesne.parametreler),
            "pencere": pencere.sozluk(), "baslangic_sermaye": sermaye,
            "maliyet": _maliyet_govdesi(model),
        },
        cikti=sonuc.sozluk(),
    ).yaz(deney_kok)

    if json_cikti:
        _yaz_json({"deney": str(yol), **sonuc.sozluk()})
        return

    typer.echo(f"{strateji} · {sembol} {timeframe} · stres senaryoları")
    typer.echo(
        f"  {'senaryo':<14}{'fee':>7}{'slip':>7}{'getiri':>9}"
        f"{'sharpe':>8}{'maxDD':>8}{'maliyet':>11}"
    )
    for ad, s in sonuc.senaryolar.items():
        typer.echo(
            f"  {ad:<14}{s['fee_taker_bps']:>7.1f}{s['slippage_bps']:>7.2f}"
            f"{s['toplam_getiri']:>9.1%}{s['sharpe']:>8.2f}{s['max_drawdown']:>8.1%}"
            f"{s['toplam_maliyet']:>11,.0f}"
        )
    typer.echo(
        f"  dayanıklı: {'evet' if sonuc.dayanikli else 'HAYIR'} · "
        f"bozulma {sonuc.bozulma():.1%} puan"
    )
    typer.echo(f"  deney: {yol}")


@lab_app.command("karsilastir")
def lab_karsilastir(
    sembol: Sembol = "BTCUSDT",
    timeframe: Timeframe = "1h",
    oos_orani: Annotated[float, typer.Option("--oos", help="OOS payı [0.1, 0.5].")] = 0.30,
    olcut: Olcut = "sharpe",
    sermaye: Sermaye = 10_000.0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """Beş aileyi aynı veri ve aynı maliyetle IS/OOS olarak yan yana koyar. (Faz 4)"""
    diziler, veri_hash = _lab_veri(depo, sembol, timeframe)
    model = maliyet_mod.yukle()
    adlar = [*KUTUPHANE, *KIYAS]

    sonuc = karsilastirma_mod.calistir(
        model, sembol, timeframe, diziler, stratejiler=adlar,
        oos_orani=oos_orani, olcut=olcut, baslangic_sermaye=sermaye, veri_sha256=veri_hash,
    )

    yol = deney_mod.Deney(
        tip="karsilastirma", strateji="+".join(adlar), veri_sha256=veri_hash,
        girdi={
            "sembol": sembol, "timeframe": timeframe, "stratejiler": adlar,
            "oos_orani": oos_orani, "olcut": olcut,
            "baslangic_sermaye": sermaye, "maliyet": _maliyet_govdesi(model),
        },
        cikti=sonuc.sozluk(),
    ).yaz(deney_kok)

    if json_cikti:
        _yaz_json({"deney": str(yol), **sonuc.sozluk()})
        return

    typer.echo(
        f"{sembol} {timeframe} · IS {sonuc.ins_pencere['uzunluk']:,} bar · "
        f"OOS {sonuc.oos_pencere['uzunluk']:,} bar · ölçüt={olcut}"
    )
    typer.echo("")
    typer.echo(
        f"  {'strateji':<13}{'aile':<16}{'plato':>7}{'IS-shp':>8}{'OOS-shp':>9}"
        f"{'OOS/IS':>8}{'OOS-get':>9}{'OOS-DD':>8}{'işlem':>7}"
    )
    for s in sonuc.satirlar:
        if s.ins is None or s.oos is None:
            typer.echo(f"  {s.strateji:<13}{s.aile:<16}  geçerli aday yok")
            continue
        typer.echo(
            f"  {s.strateji:<13}{s.aile:<16}{s.plato_orani:>7.2f}{s.ins.sharpe:>8.2f}"
            f"{s.oos.sharpe:>9.2f}{s.oos_is_sharpe_orani:>8.2f}"
            f"{s.oos.toplam_getiri:>9.1%}{s.oos.max_drawdown:>8.1%}{s.oos.islem_sayisi:>7}"
        )
    typer.echo("")
    typer.echo(f"  deney: {yol}")


@lab_app.command("deneyler")
def lab_deneyler(
    tip: Annotated[str | None, typer.Option("--tip", help="tarama | walk_forward | ...")] = None,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """Kayıtlı deneyleri listeler."""
    yollar = deney_mod.listele(deney_kok, tip)
    if json_cikti:
        _yaz_json([str(y) for y in yollar])
        return
    if not yollar:
        typer.echo("kayıtlı deney yok")
        return
    for y in yollar:
        k = deney_mod.oku(y)
        typer.echo(f"{k['tip']:<15}{k['strateji']:<24}{k['zaman']}  {y.name}")


@lab_app.command("dogrula")
def lab_dogrula(
    kayit_yolu: Annotated[Path, typer.Argument(help="Deney kaydı (.json).")],
    depo: Depo = VARSAYILAN_DEPO,
    json_cikti: JsonCikti = False,
) -> None:
    """Bir deneyi kaydından yeniden koşturur ve çıktı hash'ini doğrular. (Faz 4)

    Faz 4'ün bitti kriteri "rastgele seçilen bir deney yeniden çalıştırılıp hash'i
    doğrulanır" diyor; bu komut o kanıtın kendisi. Çıkış kodu 0 ise aynı, 1 ise değil —
    yani bir betikten de çağrılabilir.
    """
    kayit = deney_mod.oku(kayit_yolu)
    diziler, veri_hash = _lab_veri(depo, kayit["girdi"]["sembol"], kayit["girdi"]["timeframe"])
    yeniden = tekrar.tekrar_uret(kayit, diziler, veri_hash)
    ayni, aciklama = deney_mod.dogrula(kayit, yeniden)

    if json_cikti:
        _yaz_json(
            {"kayit": str(kayit_yolu), "tip": kayit["tip"], "ayni": ayni, "aciklama": aciklama}
        )
        raise typer.Exit(0 if ayni else 1)

    typer.echo(f"{kayit_yolu.name} · {kayit['tip']} · {kayit['strateji']}")
    kimlik = kayit["kimlik"]
    typer.echo(
        f"  kayıt commit: {kimlik['commit']}{' (DIRTY)' if kimlik['dirty'] else ''}"
    )
    typer.echo(f"  veri: {kimlik['veri_sha256'][:16]}…")
    if ayni:
        typer.secho(f"  yeniden üretildi: {aciklama}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  YENİDEN ÜRETİLEMEDİ: {aciklama}", fg=typer.colors.RED)
        raise typer.Exit(1)


@lab_app.command("kapilar")
def lab_kapilar(
    sembol: Sembol = "BTCUSDT",
    timeframe: Timeframe = "1h",
    oos_orani: Annotated[float, typer.Option("--oos", help="OOS payı [0.1, 0.5].")] = 0.30,
    egitim: Annotated[int, typer.Option("--egitim", help="WF eğitim penceresi (bar).")] = (
        degerlendirme_mod.EGITIM_BAR
    ),
    test: Annotated[int, typer.Option("--test", help="WF test penceresi (bar).")] = (
        degerlendirme_mod.TEST_BAR
    ),
    olcut: Olcut = "sharpe",
    sermaye: Sermaye = 10_000.0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """Her stratejiyi K-019 promotion kapılarına karşı değerlendirir. (K-010, K-018)

    IS/OOS + walk-forward + stres zincirini koşturup eşiklere karşı geçer/kalır döndürür.
    **Uygulamaz** — kapının zorlanması Faz 5'in risk motorunda. Burada üretilen şey karar
    değil, kararın dayanağı.

    Pahalıdır (7 strateji, 5,2 yıllık veride birkaç dakika). Promotion kararı ucuz
    olmamalı.
    """
    diziler, veri_hash = _lab_veri(depo, sembol, timeframe)
    model = maliyet_mod.yukle()
    adlar = [*KUTUPHANE, *KIYAS]

    sonuc = degerlendirme_mod.degerlendir(
        model, sembol, timeframe, diziler, stratejiler=adlar, oos_orani=oos_orani,
        olcut=olcut, baslangic_sermaye=sermaye, egitim_bar=egitim, test_bar=test,
    )

    yol = deney_mod.Deney(
        tip="degerlendirme", strateji="+".join(adlar), veri_sha256=veri_hash,
        girdi={
            "sembol": sembol, "timeframe": timeframe, "stratejiler": adlar,
            "oos_orani": oos_orani, "olcut": olcut, "egitim_bar": egitim, "test_bar": test,
            "baslangic_sermaye": sermaye, "maliyet": _maliyet_govdesi(model),
        },
        cikti=sonuc,
    ).yaz(deney_kok)

    if json_cikti:
        _yaz_json({"deney": str(yol), **sonuc})
        return

    p = sonuc["pencereler"]
    typer.echo(
        f"{sembol} {timeframe} · IS {p['in_sample']['uzunluk']:,} / "
        f"OOS {p['out_of_sample']['uzunluk']:,} bar · "
        f"WF {p['walk_forward']['katman']} katman"
    )
    typer.echo("")
    typer.echo("  K-019 eşikleri:")
    for e in sonuc["esikler"]:
        typer.echo(f"    {e['ad']:<24}{e['yon']} {e['sinir']}")
    typer.echo("")

    kapi_adlari = [e["ad"] for e in sonuc["esikler"]]
    basliklar = "".join(f"{a[:9]:>10}" for a in kapi_adlari)
    typer.echo(f"  {'strateji':<13}{basliklar}{'SONUÇ':>9}")
    for ad, satir in sonuc["stratejiler"].items():
        hucreler = ""
        for kapi in kapi_adlari:
            gecti = satir["kapilar"]["kapilar"][kapi]["gecti"]
            hucreler += f"{'✓' if gecti else ('—' if gecti is None else '✗'):>10}"
        durum = "GEÇTİ" if satir["kapilar"]["gecti"] else "kaldı"
        typer.echo(f"  {ad:<13}{hucreler}{durum:>9}")

    typer.echo("")
    for ad, satir in sonuc["stratejiler"].items():
        o = satir["olcumler"]
        typer.echo(
            f"  {ad:<13} OOS-shp {o.get('oos_sharpe', float('nan')):>6.2f} · "
            f"OOS/IS {o.get('oos_is_orani', float('nan')):>6.2f} · "
            f"WF-shp {o.get('wf_sharpe', float('nan')):>6.2f} · "
            f"WF+kat {o.get('wf_pozitif_katman', 0)}/{o.get('wf_katman', 0)} · "
            f"kararsız {o.get('wf_kararsizlik', float('nan')):.2f} · "
            f"stres {o.get('stres_bozulma', float('nan')):.1%}"
        )
    typer.echo("")
    if sonuc["gecen"]:
        typer.secho(f"  kapılardan geçen: {', '.join(sonuc['gecen'])}", fg=typer.colors.GREEN)
    else:
        typer.secho(
            "  kapılardan geçen strateji yok — hiçbiri paper trading'e aday değil",
            fg=typer.colors.YELLOW,
        )
    typer.echo(f"  deney: {yol}")


@app.command("bilgi")
def bilgi(json_cikti: JsonCikti = False) -> None:
    """Ortam ve git durumu — bir sonucun yanına yazılacak kimlik bilgisi. (K-009)"""
    govde = {"git": git_durumu(), "ortam": ortam_kaydi(), "simdi": utc_str(simdi_ms())}
    if json_cikti:
        _yaz_json(govde)
        return
    g = govde["git"]
    typer.echo(f"commit : {g['commit']}{' (DIRTY)' if g['dirty'] else ''}")
    typer.echo(f"python : {govde['ortam']['python']} / {govde['ortam']['platform']}")
    for ad, surum in govde["ortam"]["paketler"].items():
        typer.echo(f"  {ad:<8}: {surum}")


def main() -> int:
    """`sq` giriş noktası. Hatalar yığın izi değil, tek satırlık mesaj olarak çıkar."""
    try:
        app()
    except Exception as hata:  # noqa: BLE001 — CLI sınırı: kullanıcıya traceback gösterme
        typer.secho(f"hata: {type(hata).__name__}: {hata}", fg=typer.colors.RED, err=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
