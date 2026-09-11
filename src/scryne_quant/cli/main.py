"""`sq` komut satırı arayüzü. (K-012)

Faz 1-5'in **tek** arayüzü burasıdır; grafik arayüz Faz 6'da gelir. Komutlar bilerek dar
ve tekrar çalıştırılabilir: aynı komutu iki kez çalıştırmak bir şeyi bozmamalı, yalnızca
"değişiklik yok" demeli.

Çıktı formatı ikili: insan için tablo, makine için `--json`. İkincisi olmadan bir komutun
sonucu başka bir komuta veya bir teste giremez.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any

import typer

from scryne_quant.backtest.motor import Backtest
from scryne_quant.cli.testnet import testnet_app
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import git_durumu, ortam_kaydi
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.data import funding as funding_mod
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
from scryne_quant.live import baslat as baslat_mod
from scryne_quant.live import durdurma
from scryne_quant.live.depo import KosuDeposu
from scryne_quant.live.kilit import KilitAlinamadi, KosuKilidi
from scryne_quant.research import analiz as analiz_mod
from scryne_quant.research import bolme, tekrar
from scryne_quant.research import degerlendirme as degerlendirme_mod
from scryne_quant.research import deney as deney_mod
from scryne_quant.research import hipotez as hipotez_mod
from scryne_quant.research import karsilastirma as karsilastirma_mod
from scryne_quant.research import tarama as tarama_mod
from scryne_quant.research import walkforward as wf_mod
from scryne_quant.research.izgaralar import izgara as varsayilan_izgara
from scryne_quant.risk import durum as risk_durum_mod
from scryne_quant.risk import kalibrasyon as risk_kalibrasyon
from scryne_quant.risk import limitler as limit_mod
from scryne_quant.risk import promotion as promotion_mod
from scryne_quant.risk.audit import OlayTuru, SqliteDefter
from scryne_quant.risk.motor import RiskMotoru
from scryne_quant.strategy.kutuphane import KIYAS, KUTUPHANE, BilinmeyenStrateji, coz
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
risk_app = typer.Typer(
    name="risk",
    help="Risk motoru: limitler, kalibrasyon, durum, audit, kill switch. (Faz 5)",
)
app.add_typer(risk_app)
promotion_app = typer.Typer(
    name="promotion", help="Promotion zinciri: aşama takibi ve elle onay. (K-010)"
)
app.add_typer(promotion_app)
paper_app = typer.Typer(
    name="paper",
    help="Paper/gözlem koşusu: canlı veri, simüle emir, dashboard. (Faz 6)",
)
app.add_typer(paper_app)
app.add_typer(testnet_app)

#: Koşu dosyalarının varsayılan yeri. Koşu başına **tek** dosya: durum, fill defteri,
#: koşu günlüğü ve risk audit'i aynı SQLite dosyasında (K-034). Koşuyu yedeklemek tek bir
#: dosyayı kopyalamak demek.
VARSAYILAN_PAPER_KOKU = Path("runs/paper")

#: Audit defterinin varsayılan yeri (`.gitignore`'da).
VARSAYILAN_AUDIT = Path("runs/audit.sqlite")

Secim = Annotated[
    str,
    typer.Option(
        "--secim",
        help="Parametre seçimi: tepe (argmax) | plato (plato merkezi). Ayrı çekiliş (K-039).",
    ),
]
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
    risk: Annotated[
        bool, typer.Option("--risk", help="Risk motorunu devreye al (Faz 5, config/risk.json).")
    ] = False,
    audit: Annotated[
        Path | None, typer.Option("--audit", help="Risk kararlarını bu deftere yaz.")
    ] = None,
    depo: Depo = VARSAYILAN_DEPO,
    json_cikti: JsonCikti = False,
) -> None:
    """SMA kesişim stratejisini depodaki veri üzerinde backtest eder. (Faz 3)

    Faz 4'te strateji seçimi parametreleşecek; şimdilik tek referans strateji var ve
    komutu ona sabitlemek, olmayan bir esnekliği varmış gibi göstermekten iyi.

    `--risk` risk motorunu devreye alır (Faz 5). Varsayılanın kapalı olması, Faz 1-4'ün
    ölçümlerinin yeniden üretilebilir kalması için: risk motoru zorunlu olsaydı
    `sq lab dogrula` eski deneylerin hash'ini doğrulayamazdı.
    """
    depo_nesnesi = ParquetDepo(depo)
    df = depo_nesnesi.oku(sembol, timeframe)
    model = maliyet_mod.yukle()

    risk_motoru: RiskMotoru | None = None
    defter = None
    if risk:
        defter = SqliteDefter(audit) if audit else None
        risk_motoru = RiskMotoru(limit_mod.yukle(), timeframe, mod="backtest", defter=defter)

    strateji = SmaKesisim(hizli=hizli, yavas=yavas, maruziyet=maruziyet)
    motor = Backtest(
        strateji, model, baslangic_sermaye=sermaye, seed=seed, risk=risk_motoru
    )
    sonuc = motor.calistir(
        sembol,
        timeframe,
        bar_dizileri(df),
        veri_sha256=depo_nesnesi.sha256(sembol, timeframe),
    )

    if defter is not None:
        defter.kapat()

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
    if sonuc.risk is not None:
        r = sonuc.risk
        typer.echo("")
        typer.echo(f"  risk motoru : {r['mod']} · limit {r['limit_kimligi'][:12]}")
        typer.echo(f"    değerlendirilen: {r['degerlendirilen']:,}  onay: {r['onay']:,}")
        redler = {a: n for a, n in r["red"].items() if n}
        typer.echo(f"    red            : {redler or 'yok'}")
        kisit = {a: n for a, n in r["kisitlayan"].items() if n}
        typer.echo(f"    kısıtlayan     : {kisit or 'yok'}")
        if r["durum"]["safe_mode"]:
            typer.secho(
                f"    SAFE_MODE: {r['durum']['safe_mode_sebep']} "
                f"({utc_str(r['durum']['safe_mode_ms'])})",
                fg=typer.colors.RED,
            )
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


def _funding_okuyor_mu(ad: str) -> bool:
    """Bu strateji `funding` alanını okuyor mu? (K-042)

    Stratejinin **bildirdiği özelliklerden** türetiliyor, bir isim listesinden değil: bir
    liste, yeni bir funding stratejisi eklendiğinde güncellenmesi unutulacak yerdir — ve
    unutulduğunda hata "alan yok" diye değil, sessizce yanlış bir veri kimliği olarak
    görünürdü.
    """
    try:
        sinif = coz(ad)
    except BilinmeyenStrateji:
        return False
    return any("funding" in tanim.kayit.girdiler for tanim in sinif().ozellikler())


def _veri_kimligi(ad: str, bar_hash: str, funding_hash: str | None) -> str:
    """Bir stratejinin **tükettiği** verinin kimliği. (K-009, K-039, K-042)

    Kimlik strateji başına, koşu başına değil. `sq lab kapilar` dokuz stratejiyi aynı
    çerçevede koşturuyor ama `donchian` funding sütununa hiç bakmıyor; onun kimliğini
    funding'le değiştirmek, verisi değişmemiş bir stratejiyi defterde **yeni bir çekiliş**
    yapardı (K-039). Tersi de yanlış: funding okuyan bir stratejiyi yalnızca bar hash'iyle
    kaydetmek, iki farklı girdiyi aynı kimlikle gösterirdi.
    """
    if funding_hash is None or not _funding_okuyor_mu(ad):
        return bar_hash
    return hashlib.sha256(f"{bar_hash}:{funding_hash}".encode()).hexdigest()


def _lab_veri(depo: Path, sembol: str, timeframe: str):
    """Depodan bar dizileri + veri kimlikleri. Her lab komutunun ilk adımı.

    Döner: `(diziler, bar_hash, funding_hash)`. Funding deposu varsa sütun çerçeveye
    **nedensel** olarak ekleniyor (`data/funding.py`, K-042/4); yoksa `funding_hash`
    `None` ve funding okuyan bir strateji `features/motor.py`'de açık bir hata alıyor.

    Sütunu her koşuda eklemek zararsız: okumayan strateji onu hiç görmüyor ve kimliği
    `_veri_kimligi` ile bar hash'inde kalıyor.
    """
    d = ParquetDepo(depo)
    df = d.oku(sembol, timeframe)
    bar_hash = d.sha256(sembol, timeframe)

    funding_hash: str | None = None
    try:
        f = funding_mod.oku(sembol)
    except funding_mod.FundingHatasi:
        pass
    else:
        df = funding_mod.barlara_hizala(df, f)
        funding_hash = _funding_hash(f)

    return bar_dizileri(df), bar_hash, funding_hash


def _funding_hash(f: Any) -> str:
    """Funding serisinin içerik hash'i. Veri kimliğinin funding yarısı (K-009, K-042)."""
    return hashlib.sha256(
        f[["funding_time", "funding_rate"]].to_numpy().tobytes()
    ).hexdigest()


def _kosu_kimligi(adlar: list[str], bar_hash: str, funding_hash: str | None) -> str:
    """Çok stratejili bir koşunun veri kimliği. (K-009)

    Koşudaki **herhangi bir** strateji funding okuyorsa kimlik funding'i de kapsar.
    Aksi hâlde funding deposu değiştiğinde `sq lab dogrula` aynı hash'e farklı sonuç
    üretir — ve determinizm iddiası, doğrulayan komutun kendisi tarafından sessizce
    çürütülmüş olur.
    """
    if funding_hash is not None and any(_funding_okuyor_mu(a) for a in adlar):
        return hashlib.sha256(f"{bar_hash}:{funding_hash}".encode()).hexdigest()
    return bar_hash


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
    secim: Secim = "tepe",
    sermaye: Sermaye = 10_000.0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """Bir stratejinin parametre ızgarasını in-sample penceresinde tarar."""
    sinif = coz(strateji)
    diziler, veri_hash, funding_hash = _lab_veri(depo, sembol, timeframe)
    model = maliyet_mod.yukle()
    secenekler = varsayilan_izgara(strateji)
    _defteri_zorla([strateji], timeframe, veri_hash, secim, funding_hash)
    veri_hash = _veri_kimligi(strateji, veri_hash, funding_hash)

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

    en_iyi = sonuc.sec(secim)
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
    secim: Secim = "tepe",
    sermaye: Sermaye = 10_000.0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """Walk-forward: her katmanda optimize et, sonraki katmanda test et."""
    sinif = coz(strateji)
    diziler, veri_hash, funding_hash = _lab_veri(depo, sembol, timeframe)
    model = maliyet_mod.yukle()
    secenekler = varsayilan_izgara(strateji)
    _defteri_zorla([strateji], timeframe, veri_hash, secim, funding_hash)
    veri_hash = _veri_kimligi(strateji, veri_hash, funding_hash)

    n = len(diziler["open_time"])
    isinma = karsilastirma_mod.ortak_isinma([strateji])
    katmanlar = bolme.walk_forward(n, isinma, egitim, test, kaydirmali=not sabit_capa)
    sonuc = wf_mod.calistir(
        sinif, secenekler, model, sembol, timeframe, diziler, katmanlar, secim=secim,
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
    secim: Secim = "tepe",
    sermaye: Sermaye = 10_000.0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """İşlem sırasını karıştırıp düşüş dağılımını çıkarır."""
    sinif = coz(strateji)
    diziler, veri_hash, funding_hash = _lab_veri(depo, sembol, timeframe)
    model = maliyet_mod.yukle()
    pencere = _tam_pencere(diziler, strateji)
    _defteri_zorla([strateji], timeframe, veri_hash, secim, funding_hash)
    veri_hash = _veri_kimligi(strateji, veri_hash, funding_hash)

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
    secim: Secim = "tepe",
    sermaye: Sermaye = 10_000.0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """Maliyet varsayımlarını bozup stratejinin dayanıklılığını ölçer. (§15.1)"""
    sinif = coz(strateji)
    diziler, veri_hash, funding_hash = _lab_veri(depo, sembol, timeframe)
    model = maliyet_mod.yukle()
    pencere = _tam_pencere(diziler, strateji)
    _defteri_zorla([strateji], timeframe, veri_hash, secim, funding_hash)
    veri_hash = _veri_kimligi(strateji, veri_hash, funding_hash)

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


def _defteri_zorla(
    adlar: list[str],
    timeframe: str,
    veri_sha256: str,
    secim: str = "tepe",
    funding_hash: str | None = None,
) -> None:
    """Koşturulacak her strateji hipotez defterinde kayıtlı mı? (K-039)

    **Araç seviyesinde zorlanması şart, çünkü çekiliş burada yapılıyor.** K-039 ön kaydı
    zorunlu kıldı ama ilk hâlinde yalnızca promotion kapısı kontrol ediyordu — yani
    `sq lab karsilastir` yedi aileyi koşturup sonuçlarını gösterebiliyor, defter bundan
    habersiz kalıyordu. Sonucu **gördükten** sonra kaydetmek ön kayıt değildir; ve o
    kayıt hiç yapılmazsa sayaç olduğundan küçük kalır. İkisi de K-039'un engellemek
    istediği şey.

    Kaçış kapısı **yok** ve bilerek yok: "sadece bakıyorum" diye koşturulan bir strateji
    de bir çekiliştir. Bakmak bedavaysa, yeterince bakan biri kapıyı delmiş olur.
    """
    defter = hipotez_mod.HipotezDefteri()
    eksik = [
        ad
        for ad in adlar
        if defter.sira(
            hipotez_mod.Hipotez.kur(
                ad,
                timeframe,
                _veri_kimligi(ad, veri_sha256, funding_hash),
                varsayilan_izgara(ad),
                "kimlik kontrolü için kurulan geçici hipotez nesnesi",
                secim=secim,
            )
        )
        is None
    ]
    if not eksik:
        return
    komutlar = chr(10).join(
        f'  sq lab hipotez-kaydet {ad} -t {timeframe} -g "<neden deniyorsun>"'
        for ad in eksik
    )
    raise hipotez_mod.HipotezHatasi(
        f"hipotez defterinde kayıtlı olmayan strateji(ler): {', '.join(eksik)} "
        f"({timeframe}, seçim={secim}). Sonucu gördükten sonra kaydetmek ön kayıt "
        f"değildir (K-039). "
        f"Önce kaydedin:{chr(10)}{komutlar}"
    )


@lab_app.command("karsilastir")
def lab_karsilastir(
    sembol: Sembol = "BTCUSDT",
    timeframe: Timeframe = "1h",
    oos_orani: Annotated[float, typer.Option("--oos", help="OOS payı [0.1, 0.5].")] = 0.30,
    olcut: Olcut = "sharpe",
    secim: Secim = "tepe",
    sermaye: Sermaye = 10_000.0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """Beş aileyi aynı veri ve aynı maliyetle IS/OOS olarak yan yana koyar. (Faz 4)"""
    diziler, veri_hash, funding_hash = _lab_veri(depo, sembol, timeframe)
    model = maliyet_mod.yukle()
    adlar = [*KUTUPHANE, *KIYAS]
    _defteri_zorla(adlar, timeframe, veri_hash, secim, funding_hash)
    veri_hash = _kosu_kimligi(adlar, veri_hash, funding_hash)

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
    diziler, veri_hash, funding_hash = _lab_veri(
        depo, kayit["girdi"]["sembol"], kayit["girdi"]["timeframe"]
    )
    veri_hash = _veri_kimligi(kayit["girdi"]["strateji"], veri_hash, funding_hash)
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
    secim: Secim = "tepe",
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
    diziler, veri_hash, funding_hash = _lab_veri(depo, sembol, timeframe)
    model = maliyet_mod.yukle()
    adlar = [*KUTUPHANE, *KIYAS]
    _defteri_zorla(adlar, timeframe, veri_hash, secim, funding_hash)
    veri_hash = _kosu_kimligi(adlar, veri_hash, funding_hash)

    sonuc = degerlendirme_mod.degerlendir(
        model, sembol, timeframe, diziler, stratejiler=adlar, oos_orani=oos_orani,
        olcut=olcut, secim=secim, baslangic_sermaye=sermaye, egitim_bar=egitim,
        test_bar=test,
    )

    yol = deney_mod.Deney(
        tip="degerlendirme", strateji="+".join(adlar), veri_sha256=veri_hash,
        girdi={
            "sembol": sembol, "timeframe": timeframe, "stratejiler": adlar,
            "oos_orani": oos_orani, "olcut": olcut, "secim": secim,
            "egitim_bar": egitim, "test_bar": test,
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


# ----------------------------------------------------------------------- risk


@risk_app.command("kalibre")
def risk_kalibre(
    sembol: Sembol = "BTCUSDT",
    timeframe: Timeframe = "1h",
    azami_maruziyet: Annotated[
        float, typer.Option("--azami-maruziyet", help="İştah: portföyün bu semboldeki tavanı.")
    ] = 0.30,
    islem_basina_risk: Annotated[
        float, typer.Option("--islem-riski", help="İştah: tek işlemin riske attığı kesir.")
    ] = 0.005,
    ardisik_kayip: Annotated[int, typer.Option("--ardisik-kayip")] = 10,
    cooldown_bar: Annotated[int, typer.Option("--cooldown")] = 24,
    drawdown: Annotated[float, typer.Option("--drawdown")] = 0.20,
    ufuk: Annotated[int, typer.Option("--ufuk", help="Risk ufku (bar).")] = (
        risk_kalibrasyon.VARSAYILAN_UFUK_BAR
    ),
    yaz: Annotated[bool, typer.Option("--yaz", help="config/risk.json'a yaz.")] = False,
    depo: Depo = VARSAYILAN_DEPO,
    json_cikti: JsonCikti = False,
) -> None:
    """Risk limitlerini gerçek veriden kalibre eder. (K-033)

    Üç limit **ölçülür** (volatilite eşiği, aleyhte hareket çarpanı, günlük zarar limiti);
    beşi iştah tercihidir ve seçenek olarak verilir. İştah değerlerinin ölçülmüş gibi
    görünmemesi için her biri kayda `kaynak: istah` ve bir gözden geçirme koşuluyla
    yazılıyor.
    """
    d = ParquetDepo(depo)
    df = d.oku(sembol, timeframe)
    veri_hash = d.sha256(sembol, timeframe)
    diziler = bar_dizileri(df)
    bugun = utc_str(simdi_ms())[:10]

    vol = risk_kalibrasyon.volatilite_olc(
        diziler["high"], diziler["low"], diziler["close"]
    )
    ters = risk_kalibrasyon.ters_hareket_olc(
        diziler["open"], diziler["low"], diziler["high"], diziler["close"], ufuk_bar=ufuk
    )
    gunluk = risk_kalibrasyon.gunluk_zarar_olc(
        diziler["open_time"], diziler["close"], azami_maruziyet=azami_maruziyet
    )

    limitler = limit_mod.RiskLimitleri(
        azami_maruziyet=azami_maruziyet,
        islem_basina_risk=islem_basina_risk,
        ters_hareket_atr_carpani=round(ters.carpan, 4),
        gunluk_zarar_limiti=gunluk.limit,
        drawdown_limiti=drawdown,
        ardisik_kayip_limiti=ardisik_kayip,
        cooldown_bar=cooldown_bar,
        volatilite_esigi=round(vol.esik, 6),
        gerekceler={
            "azami_maruziyet": limit_mod.Gerekce(
                kaynak="istah",
                metin=(
                    f"Proje-Fikri §11'in 'BTC exposure <= 30%' örneği. Ölçülmüş bir sayı "
                    f"değil, risk iştahı. Bu veride al-tut kıyası tam seride %77,2 düştü; "
                    f"{azami_maruziyet:.0%} tavan o düşüşün yaklaşık {azami_maruziyet:.0%}'ini "
                    "taşımak demek."
                ),
                gozden_gecirme=(
                    "Faz 8 (kontrollü live) sonunda, backtest/paper/live drift ölçüsüyle "
                    "birlikte. Sermaye artırma kararıyla aynı toplantıda konuşulur."
                ),
                olcum_tarihi=bugun,
            ),
            "islem_basina_risk": limit_mod.Gerekce(
                kaynak="istah",
                metin=(
                    f"Proje-Fikri §42'nin 'risk_per_trade: 0.005' örneği. İştah. Ölçülen "
                    f"aleyhte hareketle ({ters.carpan:.2f}×ATR) birleştiğinde tipik "
                    f"volatilitede maruziyet tavanı "
                    f"{islem_basina_risk / (ters.carpan * vol.dagilim['p50']):.1%} "
                    "çıkıyor — yani pratikte bağlayıcı limit bu, azami maruziyet değil."
                ),
                gozden_gecirme=(
                    "Faz 5 raporundaki maruziyet tablosuna bakılarak. Tavanın azami "
                    "maruziyetin çok altına düşmesi bilinçli bir tercih mi, yoksa iki "
                    "sayının birlikte düşünülmemiş sonucu mu — cevabı rapor veriyor."
                ),
                olcum_tarihi=bugun,
            ),
            "ters_hareket_atr_carpani": limit_mod.Gerekce(
                kaynak="olculdu",
                metin=(
                    f"{ufuk} barlık risk ufkunda aleyhte hareketin p{ters.persentil:g}'ı "
                    f"({ters.ornek_sayisi:,} örnek). Geleneksel '2×ATR' varsayımı bu veride "
                    f"riski hafife alıyor: aynı ufukta medyan {ters.dagilim['p50']:.2f}×ATR. "
                    "Ufuk, Faz 4'te ölçülen medyan tutma süresi (27 saat ≈ 24 bar); v1'de "
                    "borsada duran bir stop emri olmadığı için risk ufku tutma süresidir."
                ),
                dagilim=ters.dagilim,
                olcum_tarihi=bugun,
                veri_sha256=veri_hash,
            ),
            "gunluk_zarar_limiti": limit_mod.Gerekce(
                kaynak="olculdu",
                metin=(
                    f"{gunluk.gun_sayisi:,} günlük getiri dağılımı üzerinden seçildi: "
                    f"{azami_maruziyet:.0%} maruziyet tavanında {gunluk.tetiklenen_gun} günde "
                    f"({gunluk.tetikleme_orani:.2%}) tetikleniyor. Aday tablosu: "
                    + ", ".join(f"{a}→{o:.2%}" for a, o in sorted(gunluk.aday_tablosu.items()))
                    + ". Daha gevşek bir limit normal bir kötü günde stratejinin yerine karar "
                    "verir; daha sıkı olanı neredeyse hiç çalışmaz."
                ),
                dagilim=gunluk.dagilim,
                olcum_tarihi=bugun,
                veri_sha256=veri_hash,
            ),
            "drawdown_limiti": limit_mod.Gerekce(
                kaynak="istah",
                metin=(
                    f"K-019'un `max_drawdown` promotion kapısı "
                    f"{limit_mod.PROMOTION_DRAWDOWN_KAPISI:.0%}; fren kapıdan **önce** "
                    f"devreye girmek zorunda, yoksa canlıda bugün promote etmeyeceğimiz bir "
                    f"düşüşe izin verilmiş olur. {drawdown:.0%} o sınırın altında."
                ),
                gozden_gecirme=(
                    "K-019'un `max_drawdown` eşiği değişirse bu sayı da değişmek zorunda "
                    "(limitler.py'deki tutarlılık kontrolü zorluyor)."
                ),
                olcum_tarihi=bugun,
            ),
            "ardisik_kayip_limiti": limit_mod.Gerekce(
                kaynak="istah",
                metin=(
                    f"Faz 4'ün 6 stratejisinin 564 kayıp serisinde {ardisik_kayip}+ ardışık "
                    "kayıp serilerin %5,9'unda görüldü (p95 = 10); 3+ ise %49,1'inde. "
                    "Yani 10, 'olağan kötü gidiş' değil 'olağandışı' tarafta — daha düşük "
                    "bir limit stratejinin normal davranışını cooldown'a sokardı."
                ),
                gozden_gecirme=(
                    "Paper trading'de (Faz 6) gerçek cooldown tetikleme sıklığı ölçüldüğünde."
                ),
                olcum_tarihi=bugun,
            ),
            "cooldown_bar": limit_mod.Gerekce(
                kaynak="istah",
                metin=(
                    f"{cooldown_bar} bar = 1h timeframe'de bir gün. Faz 4'te ölçülen medyan "
                    "tutma süresi 27 saat; yani cooldown yaklaşık bir pozisyon ömrü kadar. "
                    "Daha kısası 'ara vermek' sayılmaz, daha uzunu stratejiyi pencereden "
                    "çıkarır."
                ),
                gozden_gecirme="Faz 6'da cooldown sonrası ilk işlemlerin sonucu ölçülünce.",
                olcum_tarihi=bugun,
            ),
            "volatilite_esigi": limit_mod.Gerekce(
                kaynak="olculdu",
                metin=(
                    f"ATR({risk_kalibrasyon.ATR_PENCERESI})/fiyat dağılımının "
                    f"p{vol.persentil:g}'ı ({vol.bar_sayisi:,} bar). Medyan "
                    f"{vol.dagilim['p50']:.3%}, yani eşik tipik volatilitenin "
                    f"{vol.esik / vol.dagilim['p50']:.1f} katı. Guard'ın amacı olağandışı "
                    "çalkantıda işlem yapmamak; olağandışının tanımı veriden geliyor."
                ),
                dagilim=vol.dagilim,
                olcum_tarihi=bugun,
                veri_sha256=veri_hash,
            ),
        },
    )

    yol: Path | None = limit_mod.yaz(limitler) if yaz else None
    govde = {
        "limitler": limitler.sozluk(),
        "kimlik": limitler.kimlik(),
        "olcumler": {
            "volatilite": vol.sozluk(),
            "ters_hareket": ters.sozluk(),
            "gunluk_zarar": gunluk.sozluk(),
        },
        "veri": {"sembol": sembol, "timeframe": timeframe, "sha256": veri_hash},
        "yazilan": str(yol) if yol else None,
    }
    if json_cikti:
        _yaz_json(govde)
        return

    typer.echo(f"{sembol} {timeframe} · veri {veri_hash[:12]}")
    typer.echo("")
    typer.echo("  ölçülen:")
    typer.echo(
        f"    volatilite_esigi        : {limitler.volatilite_esigi:.4%}  "
        f"(ATR/fiyat p{vol.persentil:g}, medyan {vol.dagilim['p50']:.3%})"
    )
    typer.echo(
        f"    ters_hareket_atr_carpani: {limitler.ters_hareket_atr_carpani:.2f}×  "
        f"({ufuk} bar ufuk, p{ters.persentil:g}; medyan {ters.dagilim['p50']:.2f}×)"
    )
    typer.echo(
        f"    gunluk_zarar_limiti     : {limitler.gunluk_zarar_limiti:.2%}  "
        f"({gunluk.tetiklenen_gun}/{gunluk.gun_sayisi} gün = {gunluk.tetikleme_orani:.2%})"
    )
    typer.echo("")
    typer.echo("  iştah (ölçüm değil):")
    for ad in ("azami_maruziyet", "islem_basina_risk", "drawdown_limiti"):
        typer.echo(f"    {ad:<24}: {getattr(limitler, ad):.3%}")
    typer.echo(f"    {'ardisik_kayip_limiti':<24}: {limitler.ardisik_kayip_limiti}")
    typer.echo(f"    {'cooldown_bar':<24}: {limitler.cooldown_bar}")
    typer.echo("")
    tipik = limitler.islem_basina_risk / (
        limitler.ters_hareket_atr_carpani * vol.dagilim["p50"]
    )
    typer.echo(
        f"  tipik volatilitede bağlayıcı maruziyet tavanı: {min(tipik, azami_maruziyet):.1%}"
        f"  ({'islem_basina_risk' if tipik < azami_maruziyet else 'azami_maruziyet'})"
    )
    typer.echo(f"  limit kimliği: {limitler.kimlik()[:16]}")
    if yol:
        typer.echo(f"  yazıldı: {yol}")
    else:
        typer.secho("  yazılmadı (--yaz ile yaz)", fg=typer.colors.YELLOW)


@risk_app.command("limitler")
def risk_limitler(json_cikti: JsonCikti = False) -> None:
    """Yürürlükteki risk limitlerini gerekçeleriyle gösterir. (K-033)"""
    limitler = limit_mod.yukle()
    if json_cikti:
        _yaz_json({"limitler": limitler.sozluk(), "kimlik": limitler.kimlik()})
        return
    typer.echo(f"risk limitleri · kimlik {limitler.kimlik()[:16]}")
    for ad in limit_mod.LIMIT_ADLARI:
        deger = getattr(limitler, ad)
        g = limitler.gerekceler[ad]
        isaret = "ölçüldü" if g.kaynak == "olculdu" else "İŞTAH"
        bicim = f"{deger:.4%}" if isinstance(deger, float) and deger < 1 else f"{deger}"
        typer.echo("")
        typer.echo(f"  {ad} = {bicim}   [{isaret}]")
        for satir in _sar(g.metin, 74):
            typer.echo(f"      {satir}")
        if g.gozden_gecirme:
            typer.echo(f"      -> gözden geçirme: {g.gozden_gecirme}")


@risk_app.command("durum")
def risk_durum(
    audit: Annotated[Path, typer.Option("--audit", help="Audit defteri yolu.")] = (
        VARSAYILAN_AUDIT
    ),
    durum_yolu: Annotated[Path, typer.Option("--durum")] = (
        risk_durum_mod.VARSAYILAN_DURUM_YOLU
    ),
    json_cikti: JsonCikti = False,
) -> None:
    """Kalıcı risk durumu + audit özeti. SAFE_MODE açıksa bunu ilk satırda söyler."""
    durum = risk_durum_mod.durum_oku(durum_yolu)
    sayim: dict[str, int] = {}
    zincir: bool | None = None
    if audit.exists():
        with SqliteDefter(audit) as defter:
            sayim = defter.sayim()
            zincir = defter.dogrula()

    govde = {
        "durum": durum.sozluk(),
        "durum_yolu": str(durum_yolu),
        "audit": {"yol": str(audit), "var": audit.exists(), "sayim": sayim, "zincir": zincir},
    }
    if json_cikti:
        _yaz_json(govde)
        return

    if durum.safe_mode:
        typer.secho(
            f"SAFE_MODE AÇIK — sebep: {durum.safe_mode_sebep} "
            f"({utc_str(durum.safe_mode_ms) if durum.safe_mode_ms else '?'})",
            fg=typer.colors.RED,
            bold=True,
        )
        typer.echo("  yeni pozisyon girişi durdu; çıkışlar çalışıyor (K-008)")
        typer.echo("  çıkmak için: sq risk serbest --not '<gerekçe>'")
    else:
        typer.secho("SAFE_MODE kapalı", fg=typer.colors.GREEN)
    typer.echo("")
    typer.echo(f"  bar işlendi   : {durum.bar_sayisi:,} ({durum.gun_sayisi:,} gün)")
    typer.echo(f"  özkaynak      : {durum.son_ozkaynak:,.2f}  (zirve {durum.zirve_ozkaynak:,.2f})")
    typer.echo(f"  drawdown      : {durum.drawdown:.2%}")
    typer.echo(f"  günlük getiri : {durum.gunluk_getiri:+.2%}")
    typer.echo(f"  ardışık kayıp : {durum.ardisik_kayip} (kapanan işlem {durum.kapanan_islem:,})")
    cooldown = (
        "yok"
        if durum.cooldown_bitis_ms is None
        else f"{utc_str(durum.cooldown_bitis_ms)} sonuna kadar"
    )
    typer.echo(f"  cooldown      : {cooldown}")
    typer.echo("")
    if not audit.exists():
        typer.echo(f"  audit defteri yok: {audit}")
        return
    typer.echo(f"  audit ({audit}):")
    for tur, n in sorted(sayim.items()):
        typer.echo(f"    {tur:<12}{n:>8,}")
    if zincir:
        typer.secho("    zincir tutarlı", fg=typer.colors.GREEN)
    else:
        typer.secho("    ZİNCİR BOZUK — audit kurcalanmış", fg=typer.colors.RED, bold=True)


@risk_app.command("audit")
def risk_audit(
    tur: Annotated[str | None, typer.Option("--tur", help="Olay türü süzgeci.")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 20,
    audit: Annotated[Path, typer.Option("--audit")] = VARSAYILAN_AUDIT,
    json_cikti: JsonCikti = False,
) -> None:
    """Audit defterindeki son olayları gösterir."""
    if not audit.exists():
        raise typer.BadParameter(f"audit defteri yok: {audit}")
    olay_turu = OlayTuru(tur) if tur else None
    with SqliteDefter(audit) as defter:
        kayitlar = defter.oku(tur=olay_turu)
        zincir = defter.dogrula()
    son = kayitlar[-limit:]

    if json_cikti:
        _yaz_json({"zincir": zincir, "toplam": len(kayitlar), "olaylar": son})
        return
    zincir_metni = "tutarli" if zincir else "BOZUK"
    typer.echo(f"{len(kayitlar):,} olay · son {len(son)} · zincir {zincir_metni}")
    for k in son:
        g = k["govde"]
        ek = (
            f"red:{g.get('sebep')}"
            if k["tur"] == "red"
            else (
                f"onay {g.get('onayli_maruziyet', 0):.1%}"
                f"{' ←' + ','.join(g.get('kisitlayan', [])) if g.get('kisitlayan') else ''}"
                if k["tur"] == "onay"
                else str(g.get("sebep") or g.get("gerekce") or "")
            )
        )
        typer.echo(f"  {k['zaman_utc']}  {k['tur']:<9}{k['sembol']:<9}{ek}")


@risk_app.command("serbest")
def risk_serbest(
    not_metni: Annotated[
        str, typer.Option("--not", help="SAFE_MODE'dan çıkış gerekçesi (≥10 karakter).")
    ],
    durum_yolu: Annotated[Path, typer.Option("--durum")] = (
        risk_durum_mod.VARSAYILAN_DURUM_YOLU
    ),
    audit: Annotated[Path, typer.Option("--audit")] = VARSAYILAN_AUDIT,
) -> None:
    """SAFE_MODE'u **elle** kapatır. (K-008/4)

    Kill switch'ten çıkışın tek yolu bu komut. Otomatik bir çıkış yolu yok ve olmayacak:
    kendini kapatan bir kill switch, bir uyarıdır.
    """
    durum = risk_durum_mod.durum_oku(durum_yolu)
    if not durum.safe_mode:
        typer.secho("SAFE_MODE açık değil; yapılacak bir şey yok.", fg=typer.colors.YELLOW)
        return

    limitler = limit_mod.yukle()
    with SqliteDefter(audit) as defter:
        motor = RiskMotoru(limitler, "1h", defter=defter, durum=durum)
        motor.serbest_birak(not_metni, simdi_ms())
    risk_durum_mod.durum_yaz(durum, durum_yolu)
    typer.secho("SAFE_MODE kapatıldı; gerekçe audit'e yazıldı.", fg=typer.colors.GREEN)


# ------------------------------------------------------------------ promotion


def _kanit_kur(
    sonuc_yolu: Path | None, kapi_yolu: Path | None, strateji: str
) -> promotion_mod.Kanit:
    """Sonuç kaydı ve kapı değerlendirmesinden promotion kanıtı kurar.

    Eksik dosya **hata değil**: kanıtın o kısmı `None` kalır ve ilgili aşama "ölçülemedi"
    olur. Zorunlu kılmak, henüz ölçülemeyen bir aşamayı (örn. paper) hiç değerlendirilemez
    yapardı; `None` ise zincirin nerede durduğunu söylüyor.
    """
    alanlar: dict[str, Any] = {}

    if sonuc_yolu is not None:
        kayit = json.loads(sonuc_yolu.read_text(encoding="utf-8"))
        kimlik = kayit.get("kimlik", {})
        alanlar |= {
            "config_hash": kimlik.get("config_hash"),
            "sonuc_hash": kimlik.get("sonuc_hash"),
            "veri_sha256": kimlik.get("veri_sha256"),
            "commit": kimlik.get("commit"),
            "dirty": kimlik.get("dirty"),
            "mutlak_engeller": tuple(kayit.get("promotion", {}).get("engeller", [])),
        }
        risk_govdesi = kayit.get("risk")
        if risk_govdesi:
            alanlar |= {
                "risk_limit_kimligi": risk_govdesi.get("limit_kimligi"),
                "risk_max_drawdown": kayit.get("metrikler", {}).get("max_drawdown"),
                "risk_drawdown_limiti": risk_govdesi.get("limitler", {}).get(
                    "drawdown_limiti"
                ),
            }

    if kapi_yolu is not None:
        deney = json.loads(kapi_yolu.read_text(encoding="utf-8"))
        satir = deney.get("cikti", {}).get("stratejiler", {}).get(strateji)
        if satir is None:
            raise typer.BadParameter(
                f"{kapi_yolu} içinde {strateji!r} için kapı değerlendirmesi yok"
            )
        alanlar["kapi_sonucu"] = satir["kapilar"]

    return promotion_mod.Kanit(**alanlar)


@promotion_app.command("durum")
def promotion_durum(
    strateji: Annotated[str | None, typer.Argument(help="Boşsa hepsi.")] = None,
    kok: Annotated[Path, typer.Option("--kok")] = Path("runs/promotion"),
    json_cikti: JsonCikti = False,
) -> None:
    """Strateji(ler)in promotion zincirindeki yerini gösterir. (K-010)"""
    defter = promotion_mod.PromotionDefteri(kok)
    kayitlar = [defter.oku(strateji)] if strateji else defter.hepsi()

    if json_cikti:
        _yaz_json({"zincir": [str(a) for a in promotion_mod.SIRA],
                   "kayitlar": [k.sozluk() for k in kayitlar]})
        return

    typer.echo("zincir: " + " -> ".join(str(a) for a in promotion_mod.SIRA[1:]))
    typer.echo("")
    if not kayitlar:
        typer.secho(
            "  hiçbir stratejinin promotion kaydı yok — yani hiçbiri canlıya yetkili değil",
            fg=typer.colors.YELLOW,
        )
        return
    for k in kayitlar:
        renk = typer.colors.GREEN if k.asama is promotion_mod.Asama.LIVE else None
        typer.secho(f"  {k.strateji:<14}{k.asama}", fg=renk)
        if k.eksik_asamalar():
            typer.echo(f"      eksik: {', '.join(str(a) for a in k.eksik_asamalar())}")


@promotion_app.command("degerlendir")
def promotion_degerlendir(
    strateji: Annotated[str, typer.Argument(help="Strateji adı.")],
    sonuc: Annotated[
        Path | None, typer.Option("--sonuc", help="Backtest sonuç kaydı (runs/*.json).")
    ] = None,
    kapilar: Annotated[
        Path | None, typer.Option("--kapilar", help="`sq lab kapilar` deney kaydı.")
    ] = None,
    kok: Annotated[Path, typer.Option("--kok")] = Path("runs/promotion"),
    json_cikti: JsonCikti = False,
) -> None:
    """Zinciri kanıtın götürdüğü yere kadar ilerletir. (K-010)

    Her çağrı **tek** aşama ilerletir; tamamını denemek için komutu tekrar çalıştırın.
    `elle_onay` aşamasında zincir durur — o adım makine tarafından geçilemez.
    """
    defter = promotion_mod.PromotionDefteri(kok)
    kayit = defter.oku(strateji)
    kanit = _kanit_kur(sonuc, kapilar, strateji)

    adimlar: list[dict[str, Any]] = []
    while True:
        onceki = kayit.asama
        sonuc_asama = kayit.ilerlet(kanit)
        adimlar.append(sonuc_asama.sozluk())
        if kayit.asama is onceki:
            break
    yol = defter.yaz(kayit)

    if json_cikti:
        _yaz_json({"kayit": kayit.sozluk(), "adimlar": adimlar, "yol": str(yol)})
        return

    typer.echo(f"{strateji} · aşama: {kayit.asama}")
    typer.echo("")
    for adim in adimlar:
        isaret = {True: "+", False: "x", None: "?"}[adim["gecti"]]
        typer.echo(f"  {isaret} {adim['asama']:<16}{adim['gerekce']}")
    typer.echo("")
    if kayit.asama is promotion_mod.Asama.LIVE:
        typer.secho("  canlıya yetkili", fg=typer.colors.GREEN)
    else:
        typer.echo(f"  eksik: {', '.join(str(a) for a in kayit.eksik_asamalar())}")
    typer.echo(f"  kayıt: {yol}")


@promotion_app.command("onayla")
def promotion_onayla(
    strateji: Annotated[str, typer.Argument()],
    not_metni: Annotated[str, typer.Option("--not", help="Onay gerekçesi (≥10 karakter).")],
    kok: Annotated[Path, typer.Option("--kok")] = Path("runs/promotion"),
) -> None:
    """K-010'un kaldırılamaz elle onayı. Yalnızca `live_adayi` aşamasında verilebilir."""
    defter = promotion_mod.PromotionDefteri(kok)
    kayit = defter.oku(strateji)
    sonuc = kayit.elle_onayla(not_metni)
    yol = defter.yaz(kayit)
    typer.secho(f"{strateji}: {sonuc.gerekce}", fg=typer.colors.GREEN)
    typer.echo(f"  aşama: {kayit.asama}")
    typer.echo(f"  kayıt: {yol}")


def _sar(metin: str, genislik: int) -> list[str]:
    """Basit kelime sarması. `textwrap` yerine: bağımlılık değil, tek ihtiyaç bu."""
    satirlar: list[str] = []
    mevcut = ""
    for kelime in metin.split():
        if mevcut and len(mevcut) + 1 + len(kelime) > genislik:
            satirlar.append(mevcut)
            mevcut = kelime
        else:
            mevcut = f"{mevcut} {kelime}".strip()
    if mevcut:
        satirlar.append(mevcut)
    return satirlar


# --------------------------------------------------------------------- paper (Faz 6)


def _paper_yolu(kosu_adi: str, kok: Path) -> Path:
    return kok / f"{kosu_adi}.sqlite"


@paper_app.command("baslat")
def paper_baslat(
    kosu_adi: Annotated[str, typer.Argument(help="Koşunun adı; dosya adı da bu olur.")],
    strateji_adi: Annotated[
        str, typer.Option("--strateji", "-s", help="Kütüphanedeki strateji adı.")
    ] = "sma_kesisim",
    mod: Annotated[
        str,
        typer.Option(
            "--mod",
            help="gozlem | paper. `paper` promotion zinciri gerektirir (K-010, K-035).",
        ),
    ] = "gozlem",
    sembol: Annotated[str, typer.Option("--sembol")] = "BTCUSDT",
    timeframe: Annotated[str, typer.Option("--timeframe", "-t")] = "1h",
    sermaye: Annotated[float, typer.Option("--sermaye")] = 10_000.0,
    parametre: Annotated[
        list[str] | None,
        typer.Option("--parametre", "-p", help="ad=deger; birden çok kez verilebilir."),
    ] = None,
    port: Annotated[int, typer.Option("--port", help="Dashboard portu.")] = 8787,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    web: Annotated[
        Path | None, typer.Option("--web", help="SPA build dizini (apps/web/dist).")
    ] = None,
    kok: Annotated[Path, typer.Option("--kok", help="Koşu dosyalarının dizini.")] = (
        VARSAYILAN_PAPER_KOKU
    ),
    depo: Depo = VARSAYILAN_DEPO,
    kapasite: Annotated[int, typer.Option("--pencere", help="Kayan pencere bar sayısı.")] = 1000,
    ag: Annotated[
        bool, typer.Option("--ag/--ag-yok", help="Borsaya bağlan. Kapalıysa yalnızca kurar.")
    ] = True,
) -> None:
    """Paper/gözlem koşusunu başlatır; kayıt varsa toparlanarak devam eder. (Faz 6)

    Aynı `kosu_adi` ile ikinci kez çalıştırmak **yeni bir koşu açmaz**: kayıtlı durumdan
    toparlanır. Toparlanma bir geri yükleme değil, yeniden üretimdir (K-038) — portföy
    fill defterinden, bekleyen karar stratejiden yeniden üretilip kayıtlıyla
    karşılaştırılır, ayrışma varsa koşu başlamaz.

    Konfigürasyon (strateji, parametreler, risk limitleri, sermaye) koşunun kimliğinin
    parçası ve **değişmez** (K-009). Farklı bir konfigürasyon istiyorsanız yeni bir koşu
    adı verin; aynı ada farklı konfigürasyon yazmak hata verir.

    `--mod gozlem` promotion zincirini atlar ama **kanıt üretmez** (K-035): o koşunun
    günleri `paper` aşamasına sayılmaz.
    """
    if mod not in ("gozlem", "paper"):
        raise typer.BadParameter("mod `gozlem` veya `paper` olmalı (K-035)")

    sinif = coz(strateji_adi)
    kwargs = _parametreleri_coz(parametre)
    strateji = sinif(**kwargs)

    model = maliyet_mod.yukle()
    limitler = limit_mod.yukle()
    adaptor = BinanceAdaptoru() if ag else None

    kimlik = baslat_mod.kimlik_kur(
        kosu_adi=kosu_adi,
        mod=mod,
        sembol=sembol,
        timeframe=timeframe,
        strateji=strateji,
        maliyet=model,
        limitler=limitler,
        baslangic_sermaye=sermaye,
    )
    kurulum, uygulama = baslat_mod.kur(
        kimlik=kimlik,
        strateji=strateji,
        maliyet=model,
        limitler=limitler,
        kosu_yolu=_paper_yolu(kosu_adi, kok),
        depo_kok=depo,
        adaptor=adaptor,
        promotion_kok=VARSAYILAN_KOSU_KOKU / "promotion",
        kapasite=kapasite,
        web_kok=web,
    )

    t = kurulum.toparlanma
    typer.echo(f"koşu     : {kosu_adi} ({mod}) {sembol} {timeframe}")
    typer.echo(f"strateji : {strateji_adi} {kwargs or ''}")
    typer.echo(
        "başlangıç: temiz"
        if t.temiz_baslangic
        else f"toparlandı: son bar {utc_str(t.son_bar_ms)}, {t.fill_sayisi} fill"
    )
    typer.echo(f"pencere  : {t.pencere_bar} bar")
    if mod == "gozlem":
        typer.secho(
            "uyarı    : gözlem modu promotion kanıtı üretmez (K-035)",
            fg=typer.colors.YELLOW,
        )
    if kimlik.dirty:
        typer.secho("uyarı    : kirli çalışma ağacı — bu koşu promotion'a giremez (K-009)",
                    fg=typer.colors.YELLOW)

    if not ag:
        kurulum.kapat()
        typer.echo("ağ kapalı: koşu kuruldu ama başlatılmadı (--ag ile başlatın)")
        return

    typer.echo(f"dashboard: http://{host}:{port}")
    sonuc = asyncio.run(baslat_mod.calistir(kurulum, uygulama, host=host, port=port))
    ozet = sonuc.get("ozet") or {}
    typer.echo(
        f"durdu    : {ozet.get('islenen_bar', 0)} bar işlendi, "
        f"{ozet.get('sure_gun', 0.0):.2f} gün"
    )


@paper_app.command("durum")
def paper_durum(
    kosu_adi: Annotated[str, typer.Argument()],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_PAPER_KOKU,
    json_cikti: JsonCikti = False,
) -> None:
    """Çalışmayan bir koşunun kayıtlı durumunu okur. (Faz 6)

    Koşu ayaktayken dashboard'a bakılır; bu komut süreç kapalıyken "nerede kalmıştık"
    sorusunun cevabı. Dosyayı yalnızca **okur**, hiçbir şey değiştirmez.
    """
    yol = _paper_yolu(kosu_adi, kok)
    if not yol.exists():
        raise typer.BadParameter(f"koşu bulunamadı: {yol}")

    with KosuDeposu(yol) as depo:
        kimlik = depo.kosu_oku()
        kontrol = depo.kontrol_noktasi_oku()
        ilk = depo.ilk_olay_ms()
        govde = {
            "kosu": None if kimlik is None else kimlik.sozluk(),
            "kontrol_noktasi": None if kontrol is None else kontrol.sozluk(),
            "fill_sayisi": depo.fill_sayisi(),
            "kesinti_sayisi": depo.kesinti_sayisi(),
            "ilk_olay_ms": ilk,
            "calisma_gun": None if ilk is None else (simdi_ms() - ilk) / 86_400_000,
        }

    if json_cikti:
        _yaz_json(govde)
        return

    k = govde["kosu"] or {}
    typer.echo(
        f"koşu     : {k.get('kosu_adi')} ({k.get('mod')}) "
        f"{k.get('sembol')} {k.get('timeframe')}"
    )
    typer.echo(f"strateji : {(k.get('strateji') or {}).get('ad')}")
    if govde["calisma_gun"] is not None:
        typer.echo(f"çalışma  : {govde['calisma_gun']:.2f} gün")
    typer.echo(f"kesinti  : {govde['kesinti_sayisi']}")
    typer.echo(f"fill     : {govde['fill_sayisi']}")
    kn = govde["kontrol_noktasi"]
    if kn is None:
        typer.echo("durum    : henüz bar işlenmemiş")
        return
    p = kn["portfoy"]
    typer.echo(f"son bar  : {kn['son_bar_utc']}")
    typer.echo(f"portföy  : nakit {p['nakit']:.2f} · miktar {p['miktar']:.8f}")
    if kn["risk"].get("safe_mode"):
        typer.secho(
            f"SAFE_MODE: {kn['risk'].get('safe_mode_sebep')} — çıkış `sq risk serbest` (K-008/4)",
            fg=typer.colors.RED,
        )


@paper_app.command("durdur")
def paper_durdur(
    kosu_adi: Annotated[str, typer.Argument()],
    sebep: Annotated[
        str, typer.Option("--sebep", help="`durdu` satırına yazılacak sebep.")
    ] = "elle durduruldu",
    bekle_s: Annotated[
        float, typer.Option("--bekle", help="Sürecin çıkmasını kaç saniye bekleyelim.")
    ] = 60.0,
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_PAPER_KOKU,
    json_cikti: JsonCikti = False,
) -> None:
    """Çalışan bir koşuyu **düzgün** durdurur. (Faz 6)

    Sert kill ile farkı kayıtta: bu yol `durdu` satırını sebebiyle birlikte yazdırır ve
    koşu kesinti saymaz. Sert kill ise (tek alternatifti) `temiz_kapanmadi` olarak
    geriye dönük kesintiye yazılır — yani kodu düzeltmek için yapılan planlı bir
    yeniden başlatma, *"30 gün kesintisiz"* kriterine karşı bir kesinti olurdu.

    Komut bir bayrak dosyası bırakıp sürecin **kilidi bıraktığını** doğrulayarak bekler;
    kilidin serbest kalması kapanışın gerçekten tamamlandığının tek dış kanıtı.

    **Koşu kapalı kalmaz.** `ScryneQuant-Paper` zamanlanmış görevi onu birkaç dakika
    içinde yeniden başlatır — ve bu istenen davranış: kodu güncellemek için durdurulan bir
    koşunun yeni sürümle kendiliğinden geri gelmesi, elle başlatmayı unutma riskini
    ortadan kaldırıyor. Gerçekten kapalı kalması gerekiyorsa görev de durdurulmalı:
    `Disable-ScheduledTask -TaskName ScryneQuant-Paper`.
    """
    yol = _paper_yolu(kosu_adi, kok)
    if not yol.exists():
        raise typer.BadParameter(f"koşu bulunamadı: {yol}")

    kilit = KosuKilidi(yol)
    try:
        kilit.al().kapat()
    except KilitAlinamadi:
        pass
    else:
        govde = {"kosu": kosu_adi, "durum": "zaten_calismiyordu", "sebep": sebep}
        _yaz_json(govde) if json_cikti else typer.echo(
            "koşu zaten çalışmıyor; durdurulacak bir şey yok"
        )
        return

    durdurma.dur_iste(yol, sebep=sebep)
    typer.echo(f"durdurma istendi: {kosu_adi} — sebep: {sebep}")

    # Yoklama periyodu 15 s; bir tik kaçırmamak için ondan sık bakılıyor.
    son = time.monotonic() + max(bekle_s, 0.0)
    durdu = False
    while time.monotonic() < son:
        time.sleep(1.0)
        try:
            kilit.al().kapat()
        except KilitAlinamadi:
            continue
        durdu = True
        break

    if json_cikti:
        _yaz_json({"kosu": kosu_adi, "durum": "durdu" if durdu else "beklemede", "sebep": sebep})
        return
    if durdu:
        typer.secho("koşu düzgün kapandı; kesinti sayılmadı", fg=typer.colors.GREEN)
        typer.echo(
            "not: zamanlanmış görev koşuyu birkaç dakika içinde yeniden başlatır. "
            "Kapalı kalması gerekiyorsa: Disable-ScheduledTask -TaskName ScryneQuant-Paper"
        )
        return
    typer.secho(
        f"{bekle_s:.0f} s içinde kapanmadı. Bayrak duruyor, süreç bir sonraki yoklamada "
        "görecek — `sq paper olaylar` ile `durdu` satırını doğrula. Bayrağı iptal etmek "
        f"için: {durdurma.bayrak_yolu(yol)} dosyasını sil.",
        fg=typer.colors.YELLOW,
    )


@paper_app.command("olaylar")
def paper_olaylar(
    kosu_adi: Annotated[str, typer.Argument()],
    limit: Annotated[int, typer.Option("--limit", "-n")] = 30,
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_PAPER_KOKU,
    json_cikti: JsonCikti = False,
) -> None:
    """Koşu günlüğü: başlangıç, toparlanma, bayatlık, kopma, hata, kapanış. (Faz 6)

    *"30 gün kesintisiz (kesinti olduysa sebebi kayıtlı ve giderilmiş)"* kriterinin
    okunacağı yer burası.
    """
    yol = _paper_yolu(kosu_adi, kok)
    if not yol.exists():
        raise typer.BadParameter(f"koşu bulunamadı: {yol}")

    with KosuDeposu(yol) as depo:
        olaylar = depo.olaylar(limit=limit)
        kesinti = depo.kesinti_sayisi()

    if json_cikti:
        _yaz_json({"olaylar": olaylar, "kesinti_sayisi": kesinti})
        return

    for o in olaylar:
        ayrinti = json.dumps(o["ayrinti"], ensure_ascii=False)
        typer.echo(f"{o['zaman_utc']}  {o['tur']:<22} {ayrinti}")
    typer.echo(f"\nkesinti sayısı: {kesinti}")


def _parametreleri_coz(ciftler: list[str] | None) -> dict[str, Any]:
    """`ad=deger` çiftlerini sözlüğe çevirir; sayıları sayıya döndürür.

    Tip çıkarımı bilinçli olarak dar: int, float, bool ve string. Daha fazlası (liste,
    sözlük) gerekirse o parametre bir konfigürasyon dosyasına aittir — komut satırında
    JSON ayrıştırmak, yazım hatasının sessizce farklı bir koşu üretmesi demek.
    """
    sonuc: dict[str, Any] = {}
    for cift in ciftler or []:
        if "=" not in cift:
            raise typer.BadParameter(f"parametre `ad=deger` biçiminde olmalı: {cift!r}")
        ad, _, ham = cift.partition("=")
        sonuc[ad.strip()] = _deger_coz(ham.strip())
    return sonuc


def _deger_coz(ham: str) -> Any:
    if ham.lower() in ("true", "false"):
        return ham.lower() == "true"
    for tip in (int, float):
        try:
            return tip(ham)
        except ValueError:
            continue
    return ham


@lab_app.command("hipotez-kaydet")
def lab_hipotez_kaydet(
    strateji_adi: Annotated[str, typer.Argument(help="Kütüphanedeki strateji adı.")],
    gerekce: Annotated[
        str,
        typer.Option("--gerekce", "-g", help="Bu hipotez neden deneniyor? (≥20 karakter)"),
    ],
    sembol: Annotated[str, typer.Option("--sembol")] = "BTCUSDT",
    timeframe: Annotated[str, typer.Option("--timeframe", "-t")] = "1h",
    secim: Secim = "tepe",
    depo: Depo = VARSAYILAN_DEPO,
    json_cikti: JsonCikti = False,
) -> None:
    """Bir hipotezi **sonucu görmeden önce** deftere kaydeder. (K-039)

    K-019'un yedi kapısı strateji başına çalışıyor ve hiçbiri "bu kaçıncı denemeydi"
    sorusunu sormuyor. Yeterince çok deneyen biri, eşiğe hiç dokunmadan, K-018'in
    "sayısal eşik esnetilemez" kuralını deler — hiçbir test kırılmadan. Defter o yolu
    kapatıyor: kaydedilmemiş bir hipotez `out_of_sample` aşamasını geçemez.

    Izgara `research/izgaralar.py`den okunuyor; yani "hangi parametre uzayı denendi"
    sorusunun cevabı kaydın içinde ve sonradan genişletilen bir ızgara **yeni bir
    hipotez** sayılıyor.
    """
    izgara = varsayilan_izgara(strateji_adi)
    # Kimlik, `_defteri_zorla`nın aradığıyla **aynı** kurala göre hesaplanmalı: funding
    # okuyan bir stratejiyi yalnızca bar hash'iyle kaydetmek, kaydı defterde bulunamaz
    # hâle getirir ve ön kayıt yapılmış olmasına rağmen koşu reddedilirdi.
    bar_sha = ParquetDepo(depo).sha256(sembol, timeframe)
    f_sha: str | None = None
    if _funding_okuyor_mu(strateji_adi):
        f_sha = _funding_hash(funding_mod.oku(sembol))
    sha = _veri_kimligi(strateji_adi, bar_sha, f_sha)
    hipotez = hipotez_mod.Hipotez.kur(
        strateji_adi, timeframe, sha, izgara, gerekce, secim=secim
    )

    defter = hipotez_mod.HipotezDefteri()
    onceki = defter.sira(hipotez)
    sira = defter.kaydet(hipotez)

    govde = {
        "sira": sira,
        "toplam": defter.sayi(),
        "yeni": onceki is None,
        "hipotez": hipotez.sozluk(),
    }
    if json_cikti:
        _yaz_json(govde)
        return
    if onceki is not None:
        typer.echo(f"zaten kayıtlı: {sira}. hipotez (aynı soru yeni bir çekiliş değil)")
    else:
        typer.echo(f"kaydedildi: {sira}. hipotez")
    typer.echo(f"kimlik : {hipotez.kimlik[:16]}")
    typer.echo(f"defter : {defter.sayi()} hipotez · {defter.yol}")


@lab_app.command("hipotezler")
def lab_hipotezler(json_cikti: JsonCikti = False) -> None:
    """Hipotez defteri: kaç çekiliş yapıldı, hangi stratejide kaç tane. (K-039)"""
    defter = hipotez_mod.HipotezDefteri()
    kayitlar = defter.tumu()
    if json_cikti:
        _yaz_json({"ozet": defter.ozet(), "hipotezler": kayitlar})
        return
    if not kayitlar:
        typer.echo("defter boş.")
        return
    for sira, k in enumerate(kayitlar, start=1):
        typer.echo(f"{sira:>3}. {k['strateji']:<14} {k['timeframe']:<4} {k['zaman_utc']}")
        for satir in _sar(k["gerekce"], 72):
            typer.echo(f"     {satir}")
    typer.echo("")
    typer.echo(f"toplam {len(kayitlar)} hipotez")
    typer.secho(
        "Bu sayı bir eşik değil, okunması zorunlu bir bağlam: kapıları geçen bir "
        "strateji, kaçıncı deneme olduğu bilinmeden okunamaz (K-039).",
        fg=typer.colors.YELLOW,
    )


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


def _konsolu_utf8_yap() -> None:
    """Çıktıyı UTF-8'e sabitler. Windows konsolu varsayılan olarak cp1252 kullanıyor ve
    `→`, `≥`, `·` gibi karakterlerde **çıktı yazarken çöküyor** (`UnicodeEncodeError`).

    Bu bir kozmetik sorun değil: komutun kendisi başarıyla çalışıp sonucu yazarken
    patlıyor, yani iş yapılmış ama görünmemiş oluyor. Hatanın metnini değiştirmek yerine
    akışı düzeltmek doğru: raporlar ve kararlar Türkçe ve tipografik karakter içeriyor,
    onları ASCII'ye indirmek çıktıyı okunmaz yapardı.
    """
    for akis in (sys.stdout, sys.stderr):
        yeniden = getattr(akis, "reconfigure", None)
        if yeniden is None:  # pragma: no cover - yeniden yapılandırılamayan akış
            continue
        # pragma: no cover - kapalı veya yönlendirilmiş akış
        with suppress(ValueError, OSError):
            yeniden(encoding="utf-8", errors="replace")


def main() -> int:
    """`sq` giriş noktası. Hatalar yığın izi değil, tek satırlık mesaj olarak çıkar."""
    _konsolu_utf8_yap()
    try:
        app()
    except Exception as hata:  # noqa: BLE001 — CLI sınırı: kullanıcıya traceback gösterme
        typer.secho(f"hata: {type(hata).__name__}: {hata}", fg=typer.colors.RED, err=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
