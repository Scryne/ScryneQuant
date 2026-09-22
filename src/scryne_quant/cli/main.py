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
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any

import typer

from scryne_quant.backtest.coklu_motor import CokluBacktest
from scryne_quant.backtest.motor import Backtest
from scryne_quant.cli.execution import execution_app
from scryne_quant.cli.izle import izle_app
from scryne_quant.cli.jev import jev_app
from scryne_quant.cli.kill import kill_app
from scryne_quant.cli.testnet import testnet_app
from scryne_quant.common import finansman as finansman_mod
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.hash import git_durumu, ortam_kaydi
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.data import arsiv_indirici as arsiv_mod
from scryne_quant.data import evren as evren_mod
from scryne_quant.data import funding as funding_mod
from scryne_quant.data import fx as fx_mod
from scryne_quant.data import kimlik as kimlik_mod
from scryne_quant.data import sozlesme as sozlesme_mod
from scryne_quant.data import takvim as takvim_mod
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
from scryne_quant.exchange.binance_arsiv import HttpArsiv, spot_sembolleri
from scryne_quant.features.barlar import bar_dizileri
from scryne_quant.live import baslat as baslat_mod
from scryne_quant.live import durdurma
from scryne_quant.live.depo import KosuDeposu
from scryne_quant.live.kilit import KilitAlinamadi, KosuKilidi
from scryne_quant.research import analiz as analiz_mod
from scryne_quant.research import bolme, tekrar
from scryne_quant.research import coklu_test as coklu_mod
from scryne_quant.research import degerlendirme as degerlendirme_mod
from scryne_quant.research import deney as deney_mod
from scryne_quant.research import evren_kosu as evren_kosu_mod
from scryne_quant.research import gizli_tekrar as gizli_tekrar_mod
from scryne_quant.research import hipotez as hipotez_mod
from scryne_quant.research import kapilar as kapilar_mod
from scryne_quant.research import kapilar_v2 as kapilar_v2_mod
from scryne_quant.research import karsilastirma as karsilastirma_mod
from scryne_quant.research import program as program_mod
from scryne_quant.research import tarama as tarama_mod
from scryne_quant.research import walkforward as wf_mod
from scryne_quant.research.izgaralar import izgara as varsayilan_izgara
from scryne_quant.research.izgaralar import strateji_izgarasi
from scryne_quant.risk import durum as risk_durum_mod
from scryne_quant.risk import kalibrasyon as risk_kalibrasyon
from scryne_quant.risk import limitler as limit_mod
from scryne_quant.risk import promotion as promotion_mod
from scryne_quant.risk.audit import OlayTuru, SqliteDefter
from scryne_quant.risk.motor import RiskMotoru
from scryne_quant.strategy.kutuphane import (
    EVREN_KIYAS,
    KIYAS,
    KUTUPHANE,
    BilinmeyenStrateji,
    coz,
)
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
evren_app = typer.Typer(
    name="evren",
    help="Çok enstrümanlı araştırma çekirdeği: evren üzerinde backtest. (Faz 10)",
)
app.add_typer(evren_app)
app.add_typer(testnet_app)
app.add_typer(kill_app)
app.add_typer(izle_app)
app.add_typer(jev_app)
app.add_typer(execution_app)

#: Koşu dosyalarının varsayılan yeri. Koşu başına **tek** dosya: durum, fill defteri,
#: koşu günlüğü ve risk audit'i aynı SQLite dosyasında (K-034). Koşuyu yedeklemek tek bir
#: dosyayı kopyalamak demek.
VARSAYILAN_PAPER_KOKU = Path("runs/paper")

#: Audit defterinin varsayılan yeri (`.gitignore`'da).
VARSAYILAN_AUDIT = Path("runs/audit.sqlite")
#: Promotion komutlarının global audit defteri (K-082 P2): her satır önce buraya yazılır.
AuditYolu = Annotated[Path, typer.Option("--audit", help="Global audit defteri (K-082 P2).")]

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


def _tarih_saat_ms(deger: str) -> int:
    """`'YYYY-MM-DD HH:MM'` (UTC) → epoch ms. `sq lab dogrula --veri-sonu` için (K-080)."""
    try:
        an = dt.datetime.strptime(deger, "%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC)
    except ValueError as hata:
        raise typer.BadParameter(f"tarih 'YYYY-MM-DD HH:MM' olmalı: {deger!r}") from hata
    return int(an.timestamp() * 1000)


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
    bitis_gun: Annotated[
        str | None,
        typer.Option(
            "--bitis-gun",
            help=(
                "Depoyu bu güne sabitle (UTC, dahil): sonrası indirilmez, depoda varsa "
                "atılır (K-080)."
            ),
        ),
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

    indirici = TarihselIndirici(BinanceAdaptoru(), ParquetDepo(depo_kok), bitis_gun=bitis_gun)

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
        f"  inen bar      : {sonuc.inen_bar:,} ({sonuc.cagri_sayisi} çağrı, {sonuc.sure_s:.1f} s)"
    )
    typer.echo(
        f"  depoda toplam : {sonuc.depo.bar_sayisi:,} bar, {sonuc.depo.bayt / 1024**2:.2f} MB"
    )
    typer.echo(f"  aralık        : {utc_str(k.ilk_ms)} → {utc_str(k.son_ms)}")
    typer.echo(
        f"  kalite        : ok %{k.ok_orani * 100:.4f} · "
        f"eksik {k.eksik_bar} · boşluk {k.bosluk_sayisi}"
    )
    typer.echo(f"  sha256        : {sonuc.depo.sha256}")
    typer.echo(f"  değişti       : {'evet' if sonuc.degisti else 'HAYIR (idempotent)'}")


# -------------------------------------------------------------- data quality


@data_app.command("fx-al")
def data_fx_al(
    pairs: Annotated[
        list[str] | None,
        typer.Argument(help="Örn. EURUSD GBPUSD (FXCM MarketData, K-088; boşsa --hepsi)"),
    ] = None,
    hepsi: Annotated[bool, typer.Option("--hepsi", help="FXCM'nin 21 çiftinin tamamı")] = False,
    bas_gun: Annotated[
        str, typer.Option("--bas", help="İlk gün YYYY-MM-DD (o hafta dahil)")
    ] = fx_mod.KAYNAK_BASLANGIC.isoformat(),
    bit_gun: Annotated[
        str | None, typer.Option("--bit", help="Son gün YYYY-MM-DD (o hafta dahil; boşsa bugün)")
    ] = None,
    depo_kok: Annotated[Path, typer.Option("--depo", help="FX depo kökü")] = fx_mod.VARSAYILAN_DEPO,
    bitis_gun: Annotated[
        str | None,
        typer.Option(
            "--bitis-gun",
            help="Depoyu bu güne sabitle (UTC, dahil): sonraki haftalar istenmez, barlar kırpılır "
            "(K-080).",
        ),
    ] = None,
    json_cikti: JsonCikti = False,
) -> None:
    """FXCM MarketData haftalık M1 (bid+ask) → 1h Parquet + SHA manifesto. (R3 Paket 1(a), K-088)

    Doğrudan HTTPS, hesap yok; gelen dosyalar `data/fx/_gelen/<PAIR>/` altında bir kez indirilir
    (404 hatırlanır), depo gelen kümeden **baştan** kurulur — aynı komut iki kez → aynı baytlar.
    Yalnız araştırma verisi (K-087/2); mid/spread üretilmez (R4).
    """
    secim = list(fx_mod.FXCM_CIFTLER) if hepsi else [p.upper() for p in (pairs or [])]
    if not secim:
        raise typer.BadParameter("çift ver (örn. EURUSD) ya da --hepsi")
    bit = bit_gun or dt.datetime.now(dt.UTC).date().isoformat()
    kayitlar = []
    for pair in secim:
        try:
            kayit = fx_mod.fx_al(
                pair, bas_gun, bit, depo=fx_mod.FxDepo(depo_kok),
                indirici=fx_mod.https_indirici(), bitis_gun=bitis_gun,
            )
        except fx_mod.FxHatasi as hata:
            raise typer.BadParameter(str(hata)) from hata
        kayitlar.append(kayit)
        if not json_cikti:
            var = sum(1 for h in kayit.haftalar.values() if h.get("durum") == "var")
            yok = len(kayit.haftalar) - var
            typer.echo(f"{kayit.pair} 1h · {kayit.bar_sayisi:,} bar · hafta {var} var / {yok} yok")
            if kayit.bar_sayisi:
                typer.echo(f"  aralık : {utc_str(kayit.ilk_ms)} → {utc_str(kayit.son_ms)}")
                typer.echo(f"  sha256 : {kayit.sha256}")
            if bitis_gun:
                typer.echo(f"  veri sonu sabit: {bitis_gun} (K-080)")
            typer.echo(f"  dosya  : {kayit.yol}")
    if json_cikti:
        _yaz_json([k.sozluk() for k in kayitlar])


@data_app.command("fx-kesif")
def data_fx_kesif(
    pair: Annotated[str | None, typer.Argument(help="Örn. EURUSD (boşsa --hepsi)")] = None,
    hepsi: Annotated[bool, typer.Option("--hepsi", help="21 çiftin tamamı")] = False,
    bas_gun: Annotated[str, typer.Option("--bas")] = fx_mod.KAYNAK_BASLANGIC.isoformat(),
    bit_gun: Annotated[str | None, typer.Option("--bit", help="Boşsa bugün")] = None,
    depo_kok: Annotated[Path, typer.Option("--depo", help="FX depo kökü")] = fx_mod.VARSAYILAN_DEPO,
    json_cikti: JsonCikti = False,
) -> None:
    """Sağlayıcıda hangi haftaların var olduğunu HEAD ile ölçer; **indirmez**. (K-088)

    Sonuç `data/fx/_gelen/<PAIR>/kesif.json`a yazılır (tarihsel derinlik kanıtı, indirme planı).
    """
    bit = bit_gun or dt.datetime.now(dt.UTC).date().isoformat()
    secim = list(fx_mod.FXCM_CIFTLER) if hepsi else ([pair.upper()] if pair else [])
    if not secim:
        raise typer.BadParameter("çift ver (örn. EURUSD) ya da --hepsi")
    var_mi = fx_mod.https_var_mi()
    sonuclar = []
    for p in secim:
        try:
            sonuc = fx_mod.kesfet(p, bas_gun, bit, var_mi=var_mi)
        except fx_mod.FxHatasi as hata:
            raise typer.BadParameter(str(hata)) from hata
        # Dosya adı aralığı taşır: farklı aralıkların kanıtı birbirini ezmez (fx_evren birleştirir).
        yol = Path(depo_kok) / fx_mod.GELEN_DIZINI / p / (
            f"kesif-{sonuc['bas_gun']}_{sonuc['bit_gun']}.json"
        )
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(
            json.dumps(sonuc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        sonuclar.append(sonuc)
        if not json_cikti:
            typer.echo(
                f"{sonuc['pair']} · {sonuc['var']} var / {sonuc['yok']} yok "
                f"({sonuc['hafta']} hafta) · ilk {sonuc['ilk_var']} → son {sonuc['son_var']}"
                f" · {yol}"
            )
    if json_cikti:
        _yaz_json(sonuclar)


@data_app.command("fx-evren")
def data_fx_evren(
    depo_kok: Annotated[Path, typer.Option("--depo", help="FX depo kökü")] = fx_mod.VARSAYILAN_DEPO,
    json_cikti: JsonCikti = False,
) -> None:
    """FX PIT evren tablosu + hayatta kalma yanlılığı, mevcut kanıttan (kesif + manifesto). (K-090)

    Kanıtı olmayan hücre bilinmiyor sayılır; tam ölçüm için 21 çift × tüm haftalar kanıt gerekir
    (`sq data fx-kesif --hepsi`, HEAD — indirme değil). Çıktı `data/fx/_evren/<kural>.*`.
    """
    from scryne_quant.data import fx_evren as fe_mod

    try:
        meta = fe_mod.evren_kur(fx_mod.FxDepo(depo_kok), fe_mod.FxEvrenKurali())
    except fe_mod.FxEvrenHatasi as hata:
        raise typer.BadParameter(str(hata)) from hata
    if json_cikti:
        _yaz_json(meta)
        return
    k, h = meta["kapsam"], meta["hayatta_kalma"]
    typer.echo(
        f"kural {meta['kural_kimlik'][:12]} · tablo {meta['tablo_hash'][:12]} · "
        f"satır {meta['satir']}"
    )
    typer.echo(
        f"  kapsam : {k['durum']} — {k['kanitli_cift']}/{k['cift']} çift kanıtlı, "
        f"{k['hafta']} hafta ({k['ilk_hafta']} → {k['son_hafta']}), tam kanıtlı çift "
        f"{len(k['tam_kanitli_cift'])}"
    )
    typer.echo(
        f"  hayatta kalma : ölçülen hafta {h['olculen_hafta']} · kısmi kanıt "
        f"{h['kismi_kanit_hafta']} · sağlayıcı boşluğu {len(h['saglayici_boslugu'])} · medyan "
        f"{h['medyan']} · azami {h['azami']} · sıfır olmayan hafta {h['sifir_olmayan_hafta']}"
    )


@data_app.command("fx-kalibre")
def data_fx_kalibre(
    ciftler: Annotated[
        list[str] | None, typer.Argument(help="Çiftler (varsayılan: depoda M1'i olanlar).")
    ] = None,
    baslangic: Annotated[str, typer.Option("--baslangic", help="YYYY-MM-DD (dahil)")] = "",
    bitis: Annotated[str, typer.Option("--bitis", help="YYYY-MM-DD (hariç)")] = "",
    persentil: Annotated[float, typer.Option("--persentil")] = VARSAYILAN_PERSENTIL,
    depo_kok: Annotated[Path, typer.Option("--depo", help="FX depo kökü")] = fx_mod.VARSAYILAN_DEPO,
    rapor: Annotated[Path | None, typer.Option("--rapor", help="Rapor JSON yolu")] = None,
    yaz: Annotated[bool, typer.Option("--yaz", help="Maliyet modelini kataloğa yaz")] = False,
    gerekce: Annotated[str, typer.Option("--gerekce", help="Persentil/karar gerekçesi")] = "",
    json_cikti: JsonCikti = False,
) -> None:
    """FX spread dağılımı + slippage kalibrasyonu (kripto K-021 kalıbı, M1 orta fiyat). (K-098)

    Spread modele **yazılmaz** (K-094 fill'i gerçek bid/ask'ten alır; iki kez sayım yok); rollover
    penceresi ayrı raporlanır. `--yaz`: çiftler arası p75 oranı `VENUE_ORAN_ESIGI` altındaysa tek
    `config/maliyet/fxcm-fx.json` (değer = en büyük p75, K-007), değilse çift başına dosya.
    `fee_taker_bps` Active Trader tarifesinden türetilir (kaynak kayıtta), 0 değil.
    """
    from scryne_quant.data import fx_kalibrasyon as fk_mod

    depo = fx_mod.FxDepo(depo_kok)
    secilen = list(ciftler or [])
    if not secilen:
        gelen = depo.kok / fx_mod.GELEN_DIZINI
        if gelen.is_dir():
            secilen = sorted(
                d.name for d in gelen.iterdir() if d.is_dir() and any(d.glob("*.csv.gz"))
            )
    if not secilen:
        raise typer.BadParameter("M1 dosyası olan çift yok")
    bas_ms = fk_mod.gun_ms(dt.date.fromisoformat(baslangic)) if baslangic else None
    bit_ms = fk_mod.gun_ms(dt.date.fromisoformat(bitis)) if bitis else None
    try:
        olcumler = {
            c: fk_mod.fx_kalibre(
                depo, c, persentil=persentil, baslangic_ms=bas_ms, bitis_ms=bit_ms
            )
            for c in secilen
        }
    except (fk_mod.FxKalibrasyonHatasi, fx_mod.FxHatasi) as hata:
        raise typer.BadParameter(str(hata)) from hata
    karar = fk_mod.venue_karari({c: o["slippage"]["deger_bps"] for c, o in olcumler.items()})

    # Komisyon: £2/100K → bps, pencere orta fiyatlarından; çiftler arası en büyüğü (K-007).
    fee_adaylari: dict[str, float] = {}
    gbpusd: float | None = None
    try:
        gbpusd = _fx_orta_ortalama(depo, "GBPUSD", bas_ms, bit_ms)
        for c in secilen:
            fee_adaylari[c] = fk_mod.fee_bps(gbpusd, _fx_taban_usd(depo, c[:3], bas_ms, bit_ms))
    except fk_mod.FxKalibrasyonHatasi:
        fee_adaylari = {}  # dönüşüm çifti depoda yok → komisyon türetilemez, --yaz reddeder
    fee = max(fee_adaylari.values()) if fee_adaylari else None

    govde: dict[str, Any] = {
        "uretildi": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "pencere": {"baslangic": baslangic or None, "bitis": bitis or None},
        "persentil": persentil,
        "olcumler": olcumler,
        "venue_karari": karar,
        "fee": {
            "kaynak": fk_mod.FEE_KAYNAGI,
            "gbpusd_orta": gbpusd,
            "adaylar_bps": fee_adaylari,
            "fee_taker_bps": fee,
        },
        "yazildi": [],
    }
    if yaz:
        if not gerekce.strip():
            raise typer.BadParameter("--yaz için --gerekce zorunlu (K-021)")
        if fee is None:
            raise typer.BadParameter("--yaz için GBPUSD ölçümü gerekli (komisyon türetimi)")
        govde["yazildi"] = _fx_maliyet_yaz(olcumler, karar, fee_adaylari, persentil, gerekce)
    if rapor is not None:
        fk_mod.yol_yaz(rapor, govde)
        govde["rapor"] = str(rapor)
    if json_cikti:
        _yaz_json(govde)
        return
    for c, o in olcumler.items():
        sp, sl = o["spread"], o["slippage"]["dagilim_bps"]
        typer.echo(
            f"{c}: M1 {o['m1']['satir']:,} · spread p50 {sp['tum']['p50']:.3f} / rollover "
            f"p50 {sp['rollover_penceresi']['p50']:.3f} (×{sp['genisleme_orani_p50']:.1f}) bps · "
            f"slippage p50 {sl['p50']:.3f} p75 {sl['p75']:.3f} p95 {sl['p95']:.3f} bps"
        )
    typer.echo(
        f"karar: {karar['model']} (p75 oranı {karar['oran']:.3f}, eşik {karar['esik']}) · "
        f"fee_taker_bps {fee}"
    )
    for y in govde["yazildi"]:
        typer.echo(f"yazıldı: {y}")


def _fx_orta_ortalama(
    depo: fx_mod.FxDepo, pair: str, bas_ms: int | None, bit_ms: int | None
) -> float:
    from scryne_quant.data import fx_kalibrasyon as fk_mod

    m1, _ = fk_mod.m1_cerceve(depo, pair)
    if bas_ms is not None:
        m1 = m1[m1["open_time"] >= bas_ms]
    if bit_ms is not None:
        m1 = m1[m1["open_time"] < bit_ms]
    return float(m1["close"].mean())


def _fx_taban_usd(
    depo: fx_mod.FxDepo, taban: str, bas_ms: int | None, bit_ms: int | None
) -> float:
    """Taban para biriminin pencere ortalaması USD değeri, depodaki çiftlerden (K-100/5)."""
    orta = lambda pair: _fx_orta_ortalama(depo, pair, bas_ms, bit_ms)  # noqa: E731
    if taban == "USD":
        return 1.0
    if taban in ("EUR", "GBP", "NZD"):
        return orta(f"{taban}USD")
    if taban == "AUD":
        return orta("EURUSD") / orta("EURAUD")
    if taban in ("CAD", "CHF", "JPY"):
        return 1.0 / orta(f"USD{taban}")
    raise fx_mod.FxHatasi(f"{taban}: taban para birimi için USD dönüşümü tanımsız")


def _fx_maliyet_yaz(
    olcumler: dict[str, dict[str, Any]],
    karar: dict[str, Any],
    fee_adaylari: dict[str, float],
    persentil: float,
    gerekce: str,
) -> list[str]:
    """Venue ya da çift başına `MaliyetModeli` dosyaları (K-084 kataloğu, K-021 şeması).

    Komisyon: venue modelinde çiftler arası en büyüğü (K-007); çift başına modelde çiftin kendi
    türetimi (£2/100K taban → tabanın USD değeri; NZD tabanlı 0,42, EUR tabanlı 0,24 — K-100/5).
    """
    from scryne_quant.common.hash import nesne_hash
    from scryne_quant.data import fx_kalibrasyon as fk_mod

    tarih = dt.date.today().isoformat()
    yazilan: list[str] = []

    def _model(kimlik: str, ciftler: list[str], deger: float, dagilim: dict[str, float]) -> None:
        fee = max(fee_adaylari[c] for c in ciftler)
        ilk = min(int(olcumler[c]["slippage"]["ilk_ms"]) for c in ciftler)
        son = max(int(olcumler[c]["slippage"]["son_ms"]) for c in ciftler)
        kal = maliyet_mod.SlippageKalibrasyonu(
            yontem=olcumler[ciftler[0]]["slippage"]["yontem"]
            + " Girdi: M1 orta fiyat ((bid+ask)/2), FXCM candledata (Active Trader spread).",
            persentil=persentil,
            deger_bps=deger,
            sembol=",".join(ciftler),
            timeframe="1m",
            aralik_baslangic_ms=ilk,
            aralik_bitis_ms=son,
            bar_sayisi=sum(int(olcumler[c]["slippage"]["kullanilan_bar"]) for c in ciftler),
            veri_sha256=nesne_hash({c: olcumler[c]["m1"]["dosya_sha256"] for c in ciftler}),
            dagilim_bps=dagilim,
            tarih=tarih,
            gerekce=gerekce + " | fee: " + fk_mod.FEE_KAYNAGI,
        )
        model = maliyet_mod.MaliyetModeli(fee_taker_bps=fee, slippage_bps=deger, kalibrasyon=kal)
        yol = maliyet_mod.MaliyetKatalogu().yol(kimlik)
        maliyet_mod.yaz(model, yol)
        yazilan.append(str(yol))

    if karar["model"] == "fxcm-fx":
        ciftler = sorted(olcumler)
        secilen = max(ciftler, key=lambda c: olcumler[c]["slippage"]["deger_bps"])
        dagilim = dict(olcumler[secilen]["slippage"]["dagilim_bps"])
        dagilim.update(
            {f"{c}_p{int(persentil)}": olcumler[c]["slippage"]["deger_bps"] for c in ciftler}
        )
        _model("fxcm-fx", ciftler, olcumler[secilen]["slippage"]["deger_bps"], dagilim)
    else:
        for c in sorted(olcumler):
            _model(
                f"fxcm-{c.lower()}",
                [c],
                olcumler[c]["slippage"]["deger_bps"],
                dict(olcumler[c]["slippage"]["dagilim_bps"]),
            )
    return yazilan


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

    `sq data quality fx EURUSD` (R3 Paket 1(c), K-088): FX deposu için 5/7 seans farkında rapor —
    hafta sonu boşluğu gap değil, hafta içi eksik saat gap; eksik **dosya** ile eksik **bar**
    ayrı; DST sınırı yanlış gap üretmez (`data/fx.fx_kalite`). `--depo` verilmezse `data/fx`.
    """
    if sembol.lower() == "fx":
        fx_kok = fx_mod.VARSAYILAN_DEPO if depo_kok == VARSAYILAN_DEPO else depo_kok
        try:
            fx_govde = {
                "uretildi": utc_str(simdi_ms()),
                "git": git_durumu(),
                "ortam": ortam_kaydi(),
                "kalite": fx_mod.fx_kalite(fx_mod.FxDepo(fx_kok), timeframe.upper()),
            }
        except fx_mod.FxHatasi as hata:
            raise typer.BadParameter(str(hata)) from hata
        if rapor is not None:
            rapor.parent.mkdir(parents=True, exist_ok=True)
            rapor.write_text(
                json.dumps(fx_govde, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n",
            )
        if json_cikti:
            _yaz_json(fx_govde)
            return
        k = fx_govde["kalite"]
        typer.echo(f"{k['pair']} 1h (fxcm) · veri {str(k['veri_sha256'])[:12]}")
        typer.echo(
            f"  dosya : {k['dosya']['var']}/{k['dosya']['hafta']} hafta var · eksik dosya "
            f"{len(k['dosya']['eksik_dosya'])} · kapsam dışı {len(k['dosya']['kapsam_disi'])}"
        )
        typer.echo(
            f"  bar   : {k['bar']['mevcut']:,} / beklenen {k['bar']['beklenen']:,} · eksik saat "
            f"{k['bar']['eksik']} ({k['bar']['eksik_orani']:.4%}) · kısa saat "
            f"{k['bar']['kisa_saat']}"
        )
        typer.echo(
            f"  seans : açılış {k['seans']['acilis_saati_utc']} · kapanış "
            f"{k['seans']['kapanis_saati_utc']} · uzunluk {k['seans']['hafta_uzunlugu_saat']}"
        )
        return
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


# ------------------------------------------------------- data arsiv-indir


@data_app.command("arsiv-indir")
def data_arsiv_indir(
    semboller: Annotated[
        list[str] | None, typer.Argument(help="Örn. BTCUSDT LUNAUSDT (boşsa --usdt/--hepsi)")
    ] = None,
    usdt: Annotated[
        bool, typer.Option("--usdt", help="Arşivdeki USDT ile biten tüm spot semboller")
    ] = False,
    hepsi: Annotated[bool, typer.Option("--hepsi", help="Arşivdeki tüm spot semboller")] = False,
    timeframe: Annotated[str, typer.Option("--timeframe", help="Örn. 1h")] = "1h",
    depo_kok: Depo = arsiv_mod.VARSAYILAN_EVREN_DEPO,
    paralel: Annotated[
        int, typer.Option("--paralel", help="Sembol içi eşzamanlı dosya")
    ] = arsiv_mod.VARSAYILAN_PARALEL,
    tam_dogrulama: Annotated[
        bool,
        typer.Option("--tam-dogrulama", help="Kayıtlı dosyaların checksum'ını da yeniden sor"),
    ] = False,
    rapor: Annotated[
        Path | None, typer.Option("--rapor", help="JSON raporun yazılacağı yol")
    ] = None,
    bitis_gun: Annotated[
        str | None,
        typer.Option(
            "--bitis-gun",
            help=(
                "Depoyu bu güne sabitle (UTC, dahil): sonrası indirilmez, depoda varsa "
                "atılır (K-080)."
            ),
        ),
    ] = None,
    json_cikti: JsonCikti = False,
) -> None:
    """Binance arşivinden (delist edilenler dahil) bar indirir, doğrular, depoya yazar. (Faz 9)

    Varsayılan depo `data/evren` — `data/market` değil: oradaki dosyaların hash'i hipotez
    defterindeki çekilişlerin veri kimliği. Aynı komutu ikinci kez çalıştırmak hiçbir dosya
    indirmez; yalnızca arşive yeni eklenen dosyalar iner.
    """
    secim = sum(bool(x) for x in (semboller, usdt, hepsi))
    if secim != 1:
        raise typer.BadParameter("sembol listesi, --usdt veya --hepsi seçeneklerinden tam biri")

    kaynak = HttpArsiv(havuz=paralel)
    if semboller:
        liste = sorted({s.upper() for s in semboller})
    else:
        tumu = spot_sembolleri(kaynak)
        liste = [s for s in tumu if s.endswith("USDT")] if usdt else tumu

    indirici = arsiv_mod.ArsivIndirici(
        kaynak, ParquetDepo(depo_kok), paralel=paralel, bitis_gun=bitis_gun
    )
    t0 = time.perf_counter()

    def ilerleme(i: int, toplam: int, sembol: str) -> None:
        if not json_cikti and (i % 25 == 0 or i == toplam):
            gecen = time.perf_counter() - t0
            typer.echo(f"  … {i:>4}/{toplam} {sembol:<14} {gecen:>6.0f} s", err=True)

    sonuclar, hatalar = arsiv_mod.coklu_indir(
        indirici, liste, timeframe, tam_dogrulama=tam_dogrulama, ilerleme=ilerleme
    )

    # Katman tamlığı her indirmede koşar (Faz 9: "tamlık kontrolü otomatik"). Referans indirilen
    # katman; karşılaştırılan arşivin türetilmiş `1mo` katmanı (Spike 6 §4b).
    veri_olan = [s.sembol for s in sonuclar if not s.veri_yok]
    with ThreadPoolExecutor(16) as havuz:
        tamlik = list(
            havuz.map(
                lambda s: sozlesme_mod.katman_tamligi(kaynak, s, referans_katman=timeframe),
                veri_olan,
            )
        )
    eksik_katman = [t.sozluk() for t in tamlik if not t.tam]

    govde = {
        "uretildi": utc_str(simdi_ms()),
        "depo": str(depo_kok),
        "timeframe": timeframe,
        "istenen_sembol": len(liste),
        "sure_s": round(time.perf_counter() - t0, 1),
        "inen_dosya": sum(len(s.inen_dosyalar) for s in sonuclar),
        "degisen_sembol": sum(s.degisti for s in sonuclar),
        "veri_yok": sorted(s.sembol for s in sonuclar if s.veri_yok),
        "hatalar": hatalar,
        "katman_tamligi": {
            "kontrol_edilen": len(tamlik),
            "tam": len(tamlik) - len(eksik_katman),
            "eksik": eksik_katman,
        },
        "git": git_durumu(),
        "sonuclar": [s.sozluk() for s in sonuclar],
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
    else:
        toplam_bar = sum(s.depo.bar_sayisi for s in sonuclar if s.depo)
        toplam_mb = sum(s.depo.bayt for s in sonuclar if s.depo) / 1024**2
        typer.echo(f"arşiv → {depo_kok}  ({timeframe})")
        typer.echo(
            f"  sembol        : {len(liste):,} istendi · {len(sonuclar):,} tamam · "
            f"{len(hatalar)} hata · {len(govde['veri_yok'])} veri yok"
        )
        typer.echo(f"  inen dosya    : {govde['inen_dosya']:,} ({govde['sure_s']:.0f} s)")
        typer.echo(f"  değişen sembol: {govde['degisen_sembol']:,}")
        typer.echo(f"  depoda        : {toplam_bar:,} bar, {toplam_mb:,.1f} MB")
        typer.echo(
            f"  katman tamlığı: {len(tamlik) - len(eksik_katman):,}/{len(tamlik):,} tam "
            f"({timeframe} ↔ 1mo)"
        )
        for sembol, mesaj in sorted(hatalar.items())[:20]:
            typer.echo(f"  HATA {sembol}: {mesaj}")
        if rapor is not None:
            typer.echo(f"  rapor         : {rapor}")
    if hatalar:
        raise typer.Exit(code=1)


def _depo_sembolleri(kok: Path, timeframe: str) -> list[str]:
    """Depoda `<timeframe>.parquet`i olan semboller. `_` ile başlayan dizinler üst veri."""
    return sorted(
        p.parent.name
        for p in kok.glob(f"*/{timeframe}.parquet")
        if not p.parent.name.startswith("_")
    )


# ------------------------------------------------------- data kimlik-olc


@data_app.command("kimlik-olc")
def data_kimlik_olc(
    depo_kok: Depo = arsiv_mod.VARSAYILAN_EVREN_DEPO,
    timeframe: Annotated[str, typer.Option("--timeframe")] = "1h",
    rapor: Annotated[
        Path | None, typer.Option("--rapor", help="JSON raporun yazılacağı yol")
    ] = None,
    json_cikti: JsonCikti = False,
) -> None:
    """Depodaki tüm serilerin boşluklarını ölçer: eksik bar × |ln(fiyat oranı)|. (Faz 9)

    Kimlik kırılması eşiklerinin kaynağı bu dağılım (K-052/4). Eşik uygulanmaz; tüm boşluklar
    sayılır ve en büyük oranlılar listelenir.
    """
    depo = ParquetDepo(depo_kok)
    satirlar: list[dict[str, Any]] = []
    for sembol in _depo_sembolleri(Path(depo_kok), timeframe):
        df = depo.oku(sembol, timeframe)
        satirlar.extend(b.sozluk() for b in kimlik_mod.bosluklar(df, timeframe, sembol))

    uzunluk_sinif = [(1, 1), (2, 23), (24, 167), (168, 719), (720, 10**9)]
    oran_sinif = [0.0, 0.1, 0.5, 1.0, 2.0, 3.0, 5.0, float("inf")]
    tablo: list[dict[str, Any]] = []
    for alt, ust in uzunluk_sinif:
        grup = [s["log_oran"] for s in satirlar if alt <= s["eksik_bar"] <= ust]
        sayim = {
            f"[{oran_sinif[i]}, {oran_sinif[i + 1]})": sum(
                oran_sinif[i] <= x < oran_sinif[i + 1] for x in grup
            )
            for i in range(len(oran_sinif) - 1)
        }
        tablo.append(
            {"eksik_bar": f"{alt}-{ust if ust < 10**9 else '∞'}", "bosluk": len(grup), **sayim}
        )

    govde = {
        "uretildi": utc_str(simdi_ms()),
        "depo": str(depo_kok),
        "timeframe": timeframe,
        "sembol": len(_depo_sembolleri(Path(depo_kok), timeframe)),
        "bosluk": len(satirlar),
        "dagilim": tablo,
        "en_buyuk_oranlar": sorted(satirlar, key=lambda s: -s["log_oran"])[:60],
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
    typer.echo(f"{govde['sembol']} sembol, {govde['bosluk']:,} boşluk ({timeframe})")
    basliklar = list(tablo[0].keys())
    typer.echo("  " + " ".join(f"{b:>12}" for b in basliklar))
    for satir in tablo:
        typer.echo("  " + " ".join(f"{satir[b]!s:>12}" for b in basliklar))
    typer.echo("  en büyük |ln oran|:")
    for s in govde["en_buyuk_oranlar"][:25]:
        typer.echo(
            f"    {s['sembol']:<14} {s['onceki_son']} → {s['sonraki_ilk']}  "
            f"eksik {s['eksik_bar']:>5}  oran {s['oran']:.6g}  |ln| {s['log_oran']:.2f}"
        )


# ------------------------------------------------------------- data evren


@data_app.command("evren")
def data_evren(
    son_ay: Annotated[str, typer.Option("--son-ay", help="Üyeliği üretilecek son ay, YYYY-MM")],
    ust_n: Annotated[int, typer.Option("--ust-n", help="Ay başına azami üye")],
    asgari_hacim: Annotated[
        float, typer.Option("--asgari-hacim", help="M−1 ayı quote hacmi alt sınırı")
    ],
    kirilma_eksik_bar: Annotated[
        int,
        typer.Option("--kirilma-eksik-bar", help="Kimlik kırılması: asgari eksik bar"),
    ] = kimlik_mod.KIRILMA_ASGARI_EKSIK_BAR,
    kirilma_log_oran: Annotated[
        float,
        typer.Option("--kirilma-log-oran", help="Kimlik kırılması: asgari |ln(oran)|"),
    ] = kimlik_mod.KIRILMA_ASGARI_LOG_ORAN,
    depo_kok: Depo = arsiv_mod.VARSAYILAN_EVREN_DEPO,
    timeframe: Annotated[str, typer.Option("--timeframe")] = "1h",
    json_cikti: JsonCikti = False,
) -> None:
    """PIT evren tablosunu üretir ve `<depo>/_evren/` altına yazar. (K-052/3, Faz 9)

    M ayının üyeliği yalnızca M−1'in tamamlanmış verisiyle kurulur. `--son-ay`, M−1'i
    tamamlanmış olan en son M olmalı; komut tamamlanmamış bir M−1'i reddeder.
    """
    try:
        son = dt.datetime.strptime(son_ay, "%Y-%m").replace(tzinfo=dt.UTC)
    except ValueError as hata:
        raise typer.BadParameter(f"--son-ay YYYY-MM olmalı: {son_ay!r}") from hata
    simdi = dt.datetime.now(dt.UTC)
    if (son.year, son.month) > (simdi.year, simdi.month):
        raise typer.BadParameter(
            f"--son-ay {son_ay}: M−1 ayı henüz tamamlanmadı (bugün {simdi:%Y-%m-%d})"
        )

    kural = evren_mod.EvrenKurali(ust_n=ust_n, asgari_quote_hacim=asgari_hacim)
    sonuc = evren_mod.tablo_kur(
        ParquetDepo(depo_kok),
        _depo_sembolleri(Path(depo_kok), timeframe),
        kural,
        son_uye_ay=son_ay,
        timeframe=timeframe,
        asgari_eksik_bar=kirilma_eksik_bar,
        asgari_log_oran=kirilma_log_oran,
    )
    tablo = sonuc.tablo
    enstrumanlar = sonuc.enstrumanlar
    kirilma_kayit = sonuc.kirilmalar
    veri = sonuc.veri_sha256
    tablo_hash = evren_mod.tablo_hash(tablo)

    cikti = Path(depo_kok) / "_evren"
    cikti.mkdir(parents=True, exist_ok=True)
    ad = kural.kimlik[:12]
    tablo_yolu = cikti / f"{ad}.parquet"
    tablo.to_parquet(tablo_yolu, index=False)
    uye_olmus = set(tablo["kanonik_id"])
    bitis = {e["kanonik_id"]: e["gecerli_bitis_ms"] for e in enstrumanlar}
    son_ay_basi_ms = int(son.timestamp() * 1000)
    olu = sorted(k for k in uye_olmus if bitis[k] < son_ay_basi_ms - 30 * 86_400_000)
    meta = {
        "uretildi": utc_str(simdi_ms()),
        "kural": kural.sozluk(),
        "kural_kimlik": kural.kimlik,
        "kimlik_kirilmasi": {
            "asgari_eksik_bar": kirilma_eksik_bar,
            "asgari_log_oran": kirilma_log_oran,
        },
        "son_uye_ay": son_ay,
        "timeframe": timeframe,
        "tablo": str(tablo_yolu),
        "tablo_hash": tablo_hash,
        "ay_sayisi": int(tablo["ay"].nunique()),
        "satir": len(tablo),
        "uye_olmus_kimlik": len(uye_olmus),
        "son_aydan_30_gun_once_bitmis_uye": len(olu),
        "kirilmalar": kirilma_kayit,
        "git": git_durumu(),
        "veri_sha256": dict(sorted(veri.items())),
    }
    (cikti / f"{ad}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (cikti / "kimlik-katalogu.json").write_text(
        json.dumps(
            {"kirilmalar": kirilma_kayit, "enstrumanlar": enstrumanlar},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    if json_cikti:
        _yaz_json({k: v for k, v in meta.items() if k not in ("veri_sha256", "kirilmalar")})
        return
    typer.echo(f"evren {ad}  (N={ust_n}, hacim ≥ {asgari_hacim:,.0f}, son ay {son_ay})")
    typer.echo(f"  sembol / kimlik : {len(veri):,} / {len(enstrumanlar):,}")
    typer.echo(f"  kimlik kırılması: {len(kirilma_kayit)}")
    for k in kirilma_kayit[:20]:
        typer.echo(
            f"    {k['sembol']:<14} {k['onceki_son']} → {k['sonraki_ilk']}  oran {k['oran']:.6g}"
        )
    typer.echo(f"  ay / satır      : {meta['ay_sayisi']} / {len(tablo):,}")
    typer.echo(
        f"  üye olmuş       : {len(uye_olmus):,} kimlik, {len(olu):,} tanesi son aydan önce bitmiş"
    )
    typer.echo(f"  tablo_hash      : {tablo_hash}")
    typer.echo(f"  dosya           : {tablo_yolu}")


# ------------------------------------------------------ data slippage-kalibre


@data_app.command("slippage-kalibre")
def data_slippage_kalibre(
    sembol: Annotated[str, typer.Argument(help="Örn. BTCUSDT")] = "BTCUSDT",
    timeframe: Annotated[str, typer.Option("--timeframe")] = KALIBRASYON_TIMEFRAME,
    persentil: Annotated[float, typer.Option("--persentil")] = VARSAYILAN_PERSENTIL,
    depo_kok: Depo = VARSAYILAN_DEPO,
    config: Annotated[Path, typer.Option("--config")] = maliyet_mod.VARSAYILAN_YOL,
    gerekce: Annotated[str, typer.Option("--gerekce", help="Persentil seçiminin gerekçesi")] = "",
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
        f"{sonuc.sembol} {sonuc.timeframe}  {utc_str(sonuc.ilk_ms)} → {utc_str(sonuc.son_ms)}"
    )
    typer.echo(f"  kullanılan    : {sonuc.kullanilan_bar:,} hareket ({sonuc.atilan_bar:,} atıldı)")
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
            "durum           : GEÇİCİ — bu modelle üretilen sonuç promotion'a giremez (K-021)"
        )
    else:
        k = model.kalibrasyon
        assert k is not None
        typer.echo(
            f"durum           : kalibre ({k.tarih}, p{k.persentil:g}, {k.sembol} {k.timeframe})"
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
    motor = Backtest(strateji, model, baslangic_sermaye=sermaye, seed=seed, risk=risk_motoru)
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


def _veri_sonu(diziler: dict[str, Any]) -> int:
    """Verinin son barının açılışı — deney kaydının geri sarma adresi (K-080)."""
    return int(diziler["open_time"][-1])


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
    return hashlib.sha256(f[["funding_time", "funding_rate"]].to_numpy().tobytes()).hexdigest()


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
    return maliyet_mod.govde(model)


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
        sinif,
        secenekler,
        model,
        sembol,
        timeframe,
        diziler,
        ins,
        olcut=olcut,
        baslangic_sermaye=sermaye,
    )

    yol = deney_mod.Deney(
        tip="tarama",
        strateji=strateji,
        veri_sha256=veri_hash,
        veri_son_ms=_veri_sonu(diziler),
        girdi={
            "sembol": sembol,
            "timeframe": timeframe,
            "izgara": {a: list(d) for a, d in secenekler.items()},
            "pencere": ins.sozluk(),
            "olcut": olcut,
            "baslangic_sermaye": sermaye,
            "maliyet": _maliyet_govdesi(model),
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
        sinif,
        secenekler,
        model,
        sembol,
        timeframe,
        diziler,
        katmanlar,
        secim=secim,
        olcut=olcut,
        baslangic_sermaye=sermaye,
        # Kıyas ölçütünde optimize edilecek bir şey yok ve kapanmış tur da yok.
        asgari_islem=0 if strateji in KIYAS else tarama_mod.ASGARI_ISLEM,
    )

    yol = deney_mod.Deney(
        tip="walk_forward",
        strateji=strateji,
        veri_sha256=veri_hash,
        veri_son_ms=_veri_sonu(diziler),
        girdi={
            "sembol": sembol,
            "timeframe": timeframe,
            "izgara": {a: list(d) for a, d in secenekler.items()},
            "bar_sayisi": n,
            "isinma": isinma,
            "egitim_bar": egitim,
            "test_bar": test,
            "kaydirmali": not sabit_capa,
            "olcut": olcut,
            "baslangic_sermaye": sermaye,
            "maliyet": _maliyet_govdesi(model),
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
        f"    sermaye {b.baslangic_sermaye:,.0f} → {b.bitis_sermaye:,.2f} ({b.toplam_getiri:+.1%})"
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
        tip="monte_carlo",
        strateji=strateji,
        veri_sha256=veri_hash,
        veri_son_ms=_veri_sonu(diziler),
        seed=seed,
        girdi={
            "sembol": sembol,
            "timeframe": timeframe,
            "parametreler": dict(nesne.parametreler),
            "pencere": pencere.sozluk(),
            "deneme": deneme,
            "baslangic_sermaye": sermaye,
            "maliyet": _maliyet_govdesi(model),
        },
        cikti=sonuc.sozluk(),
    ).yaz(deney_kok)

    if json_cikti:
        _yaz_json({"deney": str(yol), **sonuc.sozluk()})
        return

    typer.echo(f"{strateji} · {sonuc.islem_sayisi} işlem · {deneme:,} deneme · seed={seed}")
    typer.echo(
        f"  gerçekleşen: maxDD {sonuc.gercek_max_drawdown:.1%} · getiri {sonuc.gercek_getiri:+.1%}"
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
        tip="stres",
        strateji=strateji,
        veri_sha256=veri_hash,
        veri_son_ms=_veri_sonu(diziler),
        girdi={
            "sembol": sembol,
            "timeframe": timeframe,
            "parametreler": dict(nesne.parametreler),
            "pencere": pencere.sozluk(),
            "baslangic_sermaye": sermaye,
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
        f'  sq lab hipotez-kaydet {ad} -t {timeframe} -p <program> -g "<neden deniyorsun>"'
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
        model,
        sembol,
        timeframe,
        diziler,
        stratejiler=adlar,
        oos_orani=oos_orani,
        olcut=olcut,
        baslangic_sermaye=sermaye,
        veri_sha256=veri_hash,
    )

    yol = deney_mod.Deney(
        tip="karsilastirma",
        strateji="+".join(adlar),
        veri_sha256=veri_hash,
        veri_son_ms=_veri_sonu(diziler),
        girdi={
            "sembol": sembol,
            "timeframe": timeframe,
            "stratejiler": adlar,
            "oos_orani": oos_orani,
            "olcut": olcut,
            "baslangic_sermaye": sermaye,
            "maliyet": _maliyet_govdesi(model),
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


def _tekrar_kos(
    kayit_yolu: Path, depo: Path, geri_sar: bool, veri_sonu: str | None
) -> dict[str, Any]:
    """`dogrula` ve `yenile`nin ortak gövdesi: kaydı yeniden koşturur, sınıflandırır.

    Döner: kayit, diziler, yeniden (çıktı), ayni, aciklama, geri_sarildi, farklar, sinif,
    veri_hash, veri_son_ms (depodaki son bar). Çıkışlar `typer.Exit` ile.
    """
    kayit = deney_mod.oku(kayit_yolu)
    if kayit["tip"] not in tekrar.TEKRAR_EDILEBILIR:
        typer.secho(
            f"{kayit_yolu.name} · {kayit['tip']}: bu deney tipi kaydından yeniden "
            "üretilemiyor (girdisi bar verisi değil).",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)
    if veri_sonu is not None and not geri_sar:
        raise typer.BadParameter("--veri-sonu yalnız --geri-sar ile anlamlı")
    sembol, timeframe = kayit["girdi"]["sembol"], kayit["girdi"]["timeframe"]
    # Strateji adı kaydın **üst düzeyinde**, `girdi` içinde değil (`deney.kaydet` böyle
    # yazıyor). Yanlış yerden okumak her kaydı `KeyError` ile düşürüyordu — ve bu komut
    # Faz 4'ün "herhangi bir deney kaydından yeniden üretilebiliyor" kanıtının kendisi.
    diziler, veri_hash, funding_hash = _lab_veri(depo, sembol, timeframe)
    veri_hash = _veri_kimligi(kayit["strateji"], veri_hash, funding_hash)

    geri_sarildi: dict[str, Any] | None = None
    beklenen_veri = kayit.get("kimlik", {}).get("veri_sha256")
    if geri_sar and beklenen_veri and beklenen_veri != veri_hash:
        son_bar = _tarih_saat_ms(veri_sonu) if veri_sonu else tekrar.veri_son_ms(kayit)
        if son_bar is None:
            typer.secho(
                "  geri sarılamadı: kayıtta `veri_son_ms` yok (K-080 öncesi kayıt); "
                "adresi `--veri-sonu 'YYYY-MM-DD HH:MM'` ile ver.",
                fg=typer.colors.RED,
            )
            raise typer.Exit(1)
        kirpma = tekrar.geri_sar(ParquetDepo(depo), sembol, timeframe, son_bar)
        diziler, veri_hash, funding_hash = _lab_veri(depo, sembol, timeframe)
        veri_hash = _veri_kimligi(kayit["strateji"], veri_hash, funding_hash)
        geri_sarildi = {
            "son_bar_ms": son_bar,
            "son_bar_utc": utc_str(son_bar),
            "bar_sayisi": kirpma.bar_sayisi,
            "sha256": kirpma.sha256,
            "hash_geri_geldi": beklenen_veri == veri_hash,
        }

    yeniden = tekrar.tekrar_uret(kayit, diziler, veri_hash)
    ayni, aciklama = deney_mod.dogrula(kayit, yeniden)
    # Uyuşmazlığın **sınıfı** (R1(b)): yalnız `sonuc_hash` mi (K-057/6, ekonomik sonuç aynı),
    # yoksa alan düzeyinde fark mı (kod o günden beri değişmiş). Karar hash'ten çıkar,
    # sınıf yalnızca açıklar.
    fark_listesi = [] if ayni else deney_mod.farklar(kayit["cikti"], yeniden)
    return {
        "kayit": kayit,
        "diziler": diziler,
        "yeniden": yeniden,
        "ayni": ayni,
        "aciklama": aciklama,
        "geri_sarildi": geri_sarildi,
        "farklar": fark_listesi,
        "sinif": deney_mod.fark_sinifi(fark_listesi),
        "veri_hash": veri_hash,
        "veri_son_ms": _veri_sonu(diziler),
    }


@lab_app.command("dogrula")
def lab_dogrula(
    kayit_yolu: Annotated[Path, typer.Argument(help="Deney kaydı (.json).")],
    depo: Depo = VARSAYILAN_DEPO,
    geri_sar: Annotated[
        bool,
        typer.Option(
            "--geri-sar",
            help=(
                "Veri hash'i uyuşmazsa depoyu kaydın veri sonuna kırpıp yeniden dene "
                "(K-080). Depodaki sonraki barlar ATILIR; `sq data indir` geri getirir."
            ),
        ),
    ] = False,
    veri_sonu: Annotated[
        str | None,
        typer.Option(
            "--veri-sonu",
            help=(
                "Eski kayıtlar için geri sarma adresi: son barın açılışı, "
                "'YYYY-MM-DD HH:MM' UTC. `--geri-sar` ister."
            ),
        ),
    ] = None,
    json_cikti: JsonCikti = False,
) -> None:
    """Bir deneyi kaydından yeniden koşturur ve çıktı hash'ini doğrular. (Faz 4)

    Faz 4'ün bitti kriteri "rastgele seçilen bir deney yeniden çalıştırılıp hash'i
    doğrulanır" diyor; bu komut o kanıtın kendisi. Çıkış kodu 0 ise aynı, 1 ise değil —
    yani bir betikten de çağrılabilir.

    **Geri sarma (K-080):** veri hash'i uyuşmuyorsa ve `--geri-sar` verildiyse depo kaydın
    `veri_son_ms`ine (ya da `--veri-sonu`ya) kırpılır ve hash **yeniden** karşılaştırılır.
    Geri sarım hash'i geri getirmediyse red aynen kalır — kırpma bir tahmin değil, ölçüm.
    """
    t = _tekrar_kos(kayit_yolu, depo, geri_sar, veri_sonu)
    kayit, ayni, aciklama = t["kayit"], t["ayni"], t["aciklama"]
    geri_sarildi, fark_listesi, sinif = t["geri_sarildi"], t["farklar"], t["sinif"]

    if json_cikti:
        _yaz_json(
            {
                "kayit": str(kayit_yolu),
                "tip": kayit["tip"],
                "ayni": ayni,
                "aciklama": aciklama,
                "geri_sarildi": geri_sarildi,
                "fark_sinifi": sinif,
                "fark_sayisi": len(fark_listesi),
                "farklar": fark_listesi[:20],
            }
        )
        raise typer.Exit(0 if ayni else 1)

    typer.echo(f"{kayit_yolu.name} · {kayit['tip']} · {kayit['strateji']}")
    kimlik = kayit["kimlik"]
    typer.echo(f"  kayıt commit: {kimlik['commit']}{' (DIRTY)' if kimlik['dirty'] else ''}")
    typer.echo(f"  veri: {kimlik['veri_sha256'][:16]}…")
    if geri_sarildi is not None:
        typer.secho(
            f"  depo {geri_sarildi['son_bar_utc']} son barına geri sarıldı "
            f"({geri_sarildi['bar_sayisi']} bar, {geri_sarildi['sha256'][:16]}…) — "
            "sonraki barlar atıldı; `sq data indir` geri getirir",
            fg=typer.colors.YELLOW,
        )
    if ayni:
        typer.secho(f"  yeniden üretildi: {aciklama}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  YENİDEN ÜRETİLEMEDİ: {aciklama}", fg=typer.colors.RED)
        if sinif == deney_mod.YALNIZ_SONUC_HASH:
            typer.secho(
                f"  sınıf: yalnız sonuc_hash ({len(fark_listesi)} alan) — ekonomik sonuç "
                "birebir aynı; K-057/6 hash algoritması değişimi, kayıt yenilenebilir",
                fg=typer.colors.YELLOW,
            )
        else:
            ornek = ", ".join(fark_listesi[:4])
            typer.secho(
                f"  sınıf: semantik ({len(fark_listesi)} alan; ör. {ornek}) — kod kayıt "
                "tarihinden beri değişmiş; kayıt tarihsel, bugünkü kodla yeniden üretilemez",
                fg=typer.colors.YELLOW,
            )
        raise typer.Exit(1)


@lab_app.command("yenile")
def lab_yenile(
    kayit_yolu: Annotated[Path, typer.Argument(help="Deney kaydı (.json).")],
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    geri_sar: Annotated[bool, typer.Option("--geri-sar", help="`dogrula` ile aynı.")] = False,
    veri_sonu: Annotated[
        str | None, typer.Option("--veri-sonu", help="`dogrula` ile aynı.")
    ] = None,
    json_cikti: JsonCikti = False,
) -> None:
    """Yalnız `sonuc_hash` alanları eskimiş bir kaydı bugünkü hash algoritmasıyla **yeniler**.

    R1(b), K-057/6: `sonuc_hash` eskiden sıfır atlama sayaçlarını da içeriyordu; enum
    büyüyünce eski kayıtların hash'i ekonomik sonuç değişmeden kaydı. Bu komut kaydı
    **aynı girdiyle** yeniden koşturur ve fark yalnız `sonuc_hash` alanlarındaysa yeni bir kayıt
    yazar (`etiket`: eski kimlik + sebep; `kimlik.veri_son_ms` dolu). Eski kayıt silinmez.

    **Semantik fark varsa yenilemez** ve hata verir: ekonomik sonucu değişmiş bir kaydı
    "yenilemek", farklı bir deneyi eskisinin yerine koymak olurdu. Aynı şekilde zaten aynı
    olan kaydı da yenilemez (gereksiz kopya).
    """
    t = _tekrar_kos(kayit_yolu, depo, geri_sar, veri_sonu)
    kayit = t["kayit"]
    if t["ayni"]:
        typer.secho(f"{kayit_yolu.name}: zaten yeniden üretiliyor, yenileme gereksiz.", fg="green")
        raise typer.Exit(0)
    if t["sinif"] != deney_mod.YALNIZ_SONUC_HASH:
        typer.secho(
            f"{kayit_yolu.name}: yenilenemez — fark semantik ({len(t['farklar'])} alan; "
            f"ör. {', '.join(t['farklar'][:3])}). Kayıt tarihsel kalır.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    eski_kimlik = f"{kayit['kimlik']['girdi_hash'][:12]}-{kayit['kimlik']['cikti_hash'][:12]}"
    yeni = deney_mod.Deney(
        tip=kayit["tip"],
        strateji=kayit["strateji"],
        girdi=kayit["girdi"],
        cikti=t["yeniden"],
        veri_sha256=t["veri_hash"],
        seed=int(kayit["kimlik"].get("seed", 0)),
        etiket=(
            f"yenileme: {eski_kimlik} ({kayit.get('zaman', '')[:10]}); yalnız sonuc_hash "
            f"farklıydı ({len(t['farklar'])} alan) — K-057/6 hash algoritması; R1(b)"
        ),
        veri_son_ms=t["veri_son_ms"],
    )
    yol = yeni.yaz(deney_kok)
    govde = {
        "eski": str(kayit_yolu),
        "eski_kimlik": eski_kimlik,
        "yeni": str(yol),
        "yeni_kimlik": yeni.kimlik,
        "fark_sayisi": len(t["farklar"]),
        "geri_sarildi": t["geri_sarildi"],
    }
    if json_cikti:
        _yaz_json(govde)
        return
    typer.echo(f"{kayit_yolu.name} · {kayit['tip']} · {kayit['strateji']}")
    typer.secho(
        f"  yenilendi → {yol} (yalnız sonuc_hash: {len(t['farklar'])} alan)", fg="green"
    )


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
        model,
        sembol,
        timeframe,
        diziler,
        stratejiler=adlar,
        oos_orani=oos_orani,
        olcut=olcut,
        secim=secim,
        baslangic_sermaye=sermaye,
        egitim_bar=egitim,
        test_bar=test,
    )

    yol = deney_mod.Deney(
        tip="degerlendirme",
        strateji="+".join(adlar),
        veri_sha256=veri_hash,
        veri_son_ms=_veri_sonu(diziler),
        girdi={
            "sembol": sembol,
            "timeframe": timeframe,
            "stratejiler": adlar,
            "oos_orani": oos_orani,
            "olcut": olcut,
            "secim": secim,
            "egitim_bar": egitim,
            "test_bar": test,
            "baslangic_sermaye": sermaye,
            "maliyet": _maliyet_govdesi(model),
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

    vol = risk_kalibrasyon.volatilite_olc(diziler["high"], diziler["low"], diziler["close"])
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
    tipik = limitler.islem_basina_risk / (limitler.ters_hareket_atr_carpani * vol.dagilim["p50"])
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
    durum_yolu: Annotated[Path, typer.Option("--durum")] = (risk_durum_mod.VARSAYILAN_DURUM_YOLU),
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
    durum_yolu: Annotated[Path, typer.Option("--durum")] = (risk_durum_mod.VARSAYILAN_DURUM_YOLU),
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
                "risk_drawdown_limiti": risk_govdesi.get("limitler", {}).get("drawdown_limiti"),
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
        _yaz_json(
            {
                "zincir": [str(a) for a in promotion_mod.SIRA],
                "kayitlar": [k.sozluk() for k in kayitlar],
            }
        )
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
    audit: AuditYolu = VARSAYILAN_AUDIT,
    json_cikti: JsonCikti = False,
) -> None:
    """Zinciri kanıtın götürdüğü yere kadar ilerletir. (K-010)

    Her çağrı **tek** aşama ilerletir; tamamını denemek için komutu tekrar çalıştırın.
    `elle_onay` aşamasında zincir durur — o adım makine tarafından geçilemez.
    """
    defter = promotion_mod.PromotionDefteri(kok)
    with SqliteDefter(audit) as audit_defteri:
        # Kayıt zincirle **ve** audit'le doğrulanmadan ilerletilmez; her yeni satır önce
        # audit'e, sonra dosyaya (K-082 P1/P2).
        kayit = defter.oku(strateji, audit=audit_defteri)
        kanit = _kanit_kur(sonuc, kapilar, strateji)

        adimlar: list[dict[str, Any]] = []
        while True:
            onceki = kayit.asama
            sonuc_asama = kayit.ilerlet(kanit)
            adimlar.append(sonuc_asama.sozluk())
            if kayit.asama is onceki:
                break
        yol = defter.yaz(kayit, audit=audit_defteri)

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
    audit: AuditYolu = VARSAYILAN_AUDIT,
) -> None:
    """K-010'un kaldırılamaz elle onayı. Yalnızca `live_adayi` aşamasında verilebilir."""
    defter = promotion_mod.PromotionDefteri(kok)
    with SqliteDefter(audit) as audit_defteri:
        kayit = defter.oku(strateji, audit=audit_defteri)
        sonuc = kayit.elle_onayla(not_metni)
        yol = defter.yaz(kayit, audit=audit_defteri)
    typer.secho(f"{strateji}: {sonuc.gerekce}", fg=typer.colors.GREEN)
    typer.echo(f"  aşama: {kayit.asama}")
    typer.echo(f"  kayıt: {yol}")


@promotion_app.command("zincirle")
def promotion_zincirle(
    strateji: Annotated[str, typer.Argument()],
    kok: Annotated[Path, typer.Option("--kok")] = Path("runs/promotion"),
    audit: AuditYolu = VARSAYILAN_AUDIT,
) -> None:
    """K-082 öncesi (zincirsiz) promotion kaydını **açıkça** göç ettirir.

    İçerik değişmez; her satıra `onceki_hash`/`satir_hash` eklenir ve satırlar audit'e
    `goc=true` ile yazılır. Zincirsiz kayıt sessizce kabul edilmediği için bu komut
    çalıştırılana kadar o strateji `sq promotion durum/degerlendir` ve `paper` açılışında
    hata verir — bilerek.
    """
    defter = promotion_mod.PromotionDefteri(kok)
    with SqliteDefter(audit) as audit_defteri:
        kayit = defter.zincirle(strateji, audit=audit_defteri)
    typer.secho(
        f"{strateji}: {len(kayit.gecmis)} satır zincirlendi ve audit'e yazıldı (goc=true)",
        fg=typer.colors.GREEN,
    )
    typer.echo(f"  aşama: {kayit.asama}  son hash: {kayit.son_hash[:16]}…")


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
    promotion_kok: Annotated[
        Path, typer.Option("--promotion-kok", help="Promotion kayıtları dizini (K-082).")
    ] = VARSAYILAN_KOSU_KOKU / "promotion",
    audit: AuditYolu = VARSAYILAN_AUDIT,
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
        promotion_kok=promotion_kok,
        audit_yolu=audit,
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
        typer.secho(
            "uyarı    : kirli çalışma ağacı — bu koşu promotion'a giremez (K-009)",
            fg=typer.colors.YELLOW,
        )

    if not ag:
        kurulum.kapat()
        typer.echo("ağ kapalı: koşu kuruldu ama başlatılmadı (--ag ile başlatın)")
        return

    typer.echo(f"dashboard: http://{host}:{port}")
    sonuc = asyncio.run(baslat_mod.calistir(kurulum, uygulama, host=host, port=port))
    ozet = sonuc.get("ozet") or {}
    typer.echo(
        f"durdu    : {ozet.get('islenen_bar', 0)} bar işlendi, {ozet.get('sure_gun', 0.0):.2f} gün"
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
        f"koşu     : {k.get('kosu_adi')} ({k.get('mod')}) {k.get('sembol')} {k.get('timeframe')}"
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
            "not: düzgün kapanan koşuyu zamanlanmış görev yeniden BAŞLATMAZ (yeniden başlatma "
            "yalnızca çökmede; ölçüldü 2026-09-17). Açmak: Start-ScheduledTask <görev adı>"
        )
        return
    typer.secho(
        f"{bekle_s:.0f} s içinde kapanmadı. Bayrak duruyor, süreç bir sonraki yoklamada "
        "görecek — `sq paper olaylar` ile `durdu` satırını doğrula. Bayrağı iptal etmek "
        f"için: {durdurma.bayrak_yolu(yol)} dosyasını sil.",
        fg=typer.colors.YELLOW,
    )


@paper_app.command("evren-baslat")
def paper_evren_baslat(
    kosu_adi: Annotated[str, typer.Argument(help="Koşunun adı; dosya adı da bu olur.")],
    evren_tablo: Annotated[
        Path, typer.Option("--evren-tablo", help="PIT evren tablosu (.parquet, yanında .json).")
    ],
    strateji_adi: Annotated[
        str, typer.Option("--strateji", "-s", help="Evren kıyası ya da evren ailesi adı.")
    ] = "evren_esit_agirlik",
    parametre: Annotated[
        list[str] | None,
        typer.Option("--parametre", "-p", help="ad=deger; birden çok kez verilebilir."),
    ] = None,
    sermaye: Annotated[float, typer.Option("--sermaye")] = 10_000.0,
    sifira_yaz_bar: Annotated[int, typer.Option("--sifira-yaz-bar")] = 48,
    bekleme_s: Annotated[
        int, typer.Option("--bekleme-s", help="Izgara barı bekleme süresi.")
    ] = 120,
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_PAPER_KOKU,
    turev: Annotated[
        bool, typer.Option("--turev", help="Funding + basis girdileri (evren funding aileleri).")
    ] = False,
    makro: Annotated[
        list[str] | None,
        typer.Option("--makro", help="Makro PIT serisi (ör. nfci); FRED_API_KEY .env'de olmalı."),
    ] = None,
) -> None:
    """Çok enstrümanlı **gözlem** koşusu: evren stratejisi canlı birleşik akışla. (Faz 14)

    Mod her zaman `gozlem` (K-035): promotion kanıtı üretmez, gerçek emir yok. Aynı ad ikinci
    kez çalıştırılırsa depodaki girdilerden bütün adımlar yeniden üretilir (K-038) ve kapalı
    kalınan saatler REST'ten tamamlanır. Konfigürasyon koşu kimliğidir; değişirse başlamaz.
    """
    from scryne_quant.data.alfred import AlfredMakroKaynagi, anahtar_oku
    from scryne_quant.exchange.coklu_akis import BinanceCokluBarAkisi
    from scryne_quant.exchange.turev_rest import BinanceTurevRest
    from scryne_quant.live import evren_enstruman as ee_mod
    from scryne_quant.live import evren_kosturucu as ek_mod
    from scryne_quant.strategy.kutuphane import EVREN_AILELER

    kutuphane = {**EVREN_KIYAS, **EVREN_AILELER}
    if strateji_adi not in kutuphane:
        raise typer.BadParameter(
            f"{strateji_adi!r} evren kütüphanesinde yok; kayıtlı: {', '.join(sorted(kutuphane))}"
        )
    kwargs = _parametreleri_coz(parametre)
    strateji = kutuphane[strateji_adi](**kwargs)
    # K-084/U14: canlı evren yolu `Enstruman` görmüyor (K-083 açık kalan, İz G); bugün tek
    # model, katalogdan `global` (Binance spot — adaptör Binance) — dosya yoksa açılmaz.
    maliyet = maliyet_mod.MaliyetKatalogu().coz(maliyet_mod.GLOBAL_KIMLIK, binance_spot_kripto=True)
    limitler = limit_mod.yukle()
    kok.mkdir(parents=True, exist_ok=True)
    kosu_yolu = _paper_yolu(kosu_adi, kok)
    tablo = ek_mod.EvrenTablosu.oku(evren_tablo)
    rest = BinanceAdaptoru()
    # K-085 (İz G): enstrüman kimliği tablonun yanındaki katalogdan, tick/lot borsadan, U17
    # `islem_icin_dogrula` — en son ayın üyeleri (işlem görebilecek küme) için, fail closed.
    # Sonraki aylarda evrene giren üyeler `enstruman_dogrulayici` ile aynı yoldan geçer.
    katalog = ee_mod.katalogu_oku(ee_mod.katalog_yolu(evren_tablo))
    son_uyelik = tablo.uyelik(tablo.aylar()[-1])
    if son_uyelik is None:
        raise typer.BadParameter(f"{evren_tablo}: son ayın üyeliği yok")
    kimlikler = ee_mod.enstrumanlari_kur(katalog, son_uyelik.semboller, rest.sembol_kurallari)
    # K-084/U14: her üyenin `maliyet_modeli_id`si katalogdan çözümlenir; hepsi global → None.
    maliyetler = evren_kosu_mod.enstruman_maliyetleri(maliyet_mod.MaliyetKatalogu(), kimlikler)
    risk = RiskMotoru(limitler, "1h", mod="gozlem", defter=SqliteDefter(kosu_yolu))
    kimlik = {
        "kosu_adi": kosu_adi,
        "mod": "gozlem",
        "timeframe": "1h",
        "strateji": strateji.sozluk(),
        "maliyet": maliyet.sozluk(),
        "limit_kimligi": limitler.kimlik(),
        "baslangic_sermaye": sermaye,
        "sifira_yaz_bar": sifira_yaz_bar,
        # Tablo hash'i değil kural: aylık yenileme tabloyu değiştirir, koşu kimliğini değil.
        # Her ayın listesi hash'iyle depoya ayrıca yazılır; geçmiş ay değişirse motor durur.
        "evren_kural_kimlik": tablo.kural_kimlik,
        # Yalnızca açıksa: türevsiz koşuların kimliği değişmesin.
        **({"turev": True} if turev else {}),
        **({"makro": sorted(makro)} if makro else {}),
        # Yalnız çok modelde (K-084): tek modelli koşunun kimliği Faz 14 ile aynı kalır.
        **(
            {"maliyetler": maliyet_mod.maliyetler_govdesi(maliyetler)}
            if maliyetler is not None
            else {}
        ),
    }
    kosucu: ek_mod.EvrenKosucu

    def akis(semboller, son_teslim):
        return BinanceCokluBarAkisi(
            semboller, "1h", adaptor=rest, son_teslim=son_teslim,
            kopma_kancasi=lambda sebep: kosucu.depo.olay_yaz("kopma", ayrinti={"sebep": sebep}),
            yeniden_baglanma_kancasi=lambda a: kosucu.depo.olay_yaz("yeniden_baglandi", ayrinti=a),
        )

    kosucu = ek_mod.EvrenKosucu(
        kosu_yolu=kosu_yolu,
        kimlik=kimlik,
        kurulum={"strateji": strateji, "maliyet": maliyet, "baslangic_sermaye": sermaye,
                 "risk": risk, "timeframe": "1h", "sifira_yaz_bar": sifira_yaz_bar,
                 "turev": turev, "makro": tuple(sorted(makro or ())),
                 **({"maliyetler": maliyetler} if maliyetler is not None else {})},
        tablo=tablo,
        rest=rest,
        akis_fabrikasi=akis,
        bekleme_ms=bekleme_s * 1000,
        gunluk=lambda satir: typer.echo(satir),
        turev=BinanceTurevRest() if turev else None,
        makro=AlfredMakroKaynagi(anahtar_oku(Path(".env"))) if makro else None,
        enstruman_dogrulayici=lambda u: ee_mod.enstrumanlari_kur(
            katalog, u.semboller, rest.sembol_kurallari
        ),
    )
    typer.echo(f"evren koşusu : {kosu_adi} (gozlem) · {strateji_adi} {kwargs or ''}")
    typer.echo(f"evren tablosu: {evren_tablo} ({tablo.tablo_hash[:12]})")
    typer.echo(f"enstrümanlar : {son_uyelik.ay} {ee_mod.ozet(kimlikler)}")
    try:
        asyncio.run(ek_mod.kos(kosucu))
    except KilitAlinamadi as hata:
        raise typer.BadParameter(str(hata)) from hata
    typer.echo("koşu durdu")


@paper_app.command("evren-tablo-yenile")
def paper_evren_tablo_yenile(
    tablo: Annotated[Path, typer.Argument(help="Koşunun kendi evren tablosu (.parquet).")],
    depo_kok: Depo = arsiv_mod.VARSAYILAN_EVREN_DEPO,
    indir: Annotated[
        bool, typer.Option("--indir", help="M−1 eksikse önce arşivden USDT sembollerini indir.")
    ] = False,
) -> None:
    """Koşunun evren tablosunu içinde bulunulan aya uzatır; idempotent. (Faz 14)

    Aynı kural ve `tablo_kur` ile üretilir, geçmiş ayların listesi değişirse yazmaz. Çıkış
    kodu: 0 güncel/yazıldı, 3 M−1 verisi henüz tamam değil (sonra yeniden dene), 1 hata.
    Zamanlanmış görevle her gün çalıştırılır; koşu dosyayı kendisi yeniden okur.
    """
    from scryne_quant.live import evren_yenileme as ey

    def dene() -> ey.YenilemeSonucu:
        return ey.yenile(tablo, ParquetDepo(depo_kok), _depo_sembolleri(Path(depo_kok), "1h"))

    try:
        sonuc = dene()
        if sonuc.durum == "m1_eksik" and indir:
            typer.echo(f"M−1 eksik ({sonuc.ayrinti}); arşivden indiriliyor")
            subprocess.run(
                [sys.executable, "-m", "scryne_quant.cli.main", "data", "arsiv-indir", "--usdt",
                 "--depo", str(depo_kok)],
                check=False,
            )
            sonuc = dene()
    except ey.EvrenYenilemeHatasi as hata:
        typer.echo(f"HATA: {hata}", err=True)
        raise typer.Exit(code=1) from hata
    typer.echo(f"{utc_str(simdi_ms())}  {sonuc.durum}  son ay {sonuc.son_uye_ay}  "
               f"{(sonuc.tablo_hash or '')[:12]}  {sonuc.ayrinti}")
    if sonuc.durum == "m1_eksik":
        raise typer.Exit(code=3)


def _sqlite_yedekle(kaynak: Path, hedef: Path) -> None:
    """Çalışan koşunun dosyasına dokunmadan tutarlı kopya (SQLite online backup).

    Gövde `live/evren_kurulum.anlik_kopya`da: salt okunur pano da aynı kopyayı alıyor.
    """
    from scryne_quant.live.evren_kurulum import anlik_kopya

    anlik_kopya(kaynak, hedef)


def _evren_kurulum_kimlikten(kimlik: dict[str, Any]) -> dict[str, Any]:
    """Evren koşusunun motor kurulumu, koşu kimliğinden; bugünkü konfigürasyonla bire bir
    tutması doğrulanır (tutmazsa kurulmaz — yanlış konfigürasyonla yeniden üretim kanıt olmaz).

    Gövde `live/evren_kurulum.py`de: salt okunur pano da **aynı** kurulumu kuruyor ve iki
    kopya sessizce ayrışabilirdi. Burada kalan tek şey CLI'ya özgü hata tipi.
    """
    from scryne_quant.live.evren_kurulum import (
        KurulumUyusmazligi,
        evren_kurulum_kimlikten,
    )

    try:
        return evren_kurulum_kimlikten(kimlik)
    except KurulumUyusmazligi as e:
        raise typer.BadParameter(str(e)) from e


@paper_app.command("pano")
def paper_pano(
    port: Annotated[int, typer.Option("--port", help="Dinlenecek port.")] = 8788,
    host: Annotated[str, typer.Option("--host", help="Dinlenecek arayüz.")] = "127.0.0.1",
    web: Annotated[
        Path | None, typer.Option("--web", help="SPA build dizini (apps/web/dist).")
    ] = None,
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_PAPER_KOKU,
    izleme_kok: Annotated[Path, typer.Option("--izleme")] = Path("runs/izleme"),
) -> None:
    """Bütün koşuları gösteren **salt okunur** gözlem panosu. (Faz 14)

    Koşuların kendi süreçlerine dokunmaz: her okuma anlık kopyadan yapılır, hiçbir uç
    durum değiştirmez. Bu yüzden dayanıklılık penceresi açıkken de çalıştırılabilir —
    koşuyu yeniden başlatmak gerekmez.
    """
    import uvicorn

    from scryne_quant.live.evren_pano import PanoKaynagi, pano_kur

    kaynak = PanoKaynagi(kok, izleme_kok)
    app = pano_kur(kaynak, web_kok=web.resolve() if web is not None else None)
    bulunan = [y.name[: -len(".sqlite")] for y in kaynak.kosu_yollari()]
    typer.echo(f"pano    : http://{host}:{port}  (salt okunur)")
    typer.echo(f"koşular : {', '.join(bulunan) if bulunan else 'yok'}")
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)


@paper_app.command("evren-yedek")
def paper_evren_yedek(
    kosu_adi: Annotated[list[str], typer.Argument()],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_PAPER_KOKU,
    yedek_kok: Annotated[Path, typer.Option("--yedek")] = Path("runs/yedek"),
    sakla: Annotated[int, typer.Option("--sakla", help="Koşu başına tutulacak yedek.")] = 7,
) -> None:
    """Evren koşularının günlük yedeği (çalışırken, tutarlı kopya). Eskiler silinir."""
    for ad in kosu_adi:
        kaynak = _paper_yolu(ad, kok)
        if not kaynak.exists():
            typer.echo(f"{ad}: koşu yok, atlandı")
            continue
        hedef = yedek_kok / f"{ad}-{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%SZ}.sqlite"
        _sqlite_yedekle(kaynak, hedef)
        eskiler = sorted(yedek_kok.glob(f"{ad}-*.sqlite"))[:-sakla]
        for e in eskiler:
            e.unlink()
        boyut = hedef.stat().st_size / 1024**2
        typer.echo(f"{ad}: {hedef} ({boyut:.1f} MB), silinen {len(eskiler)}")


@paper_app.command("evren-tatbikat")
def paper_evren_tatbikat(
    kosu_adi: Annotated[str, typer.Argument()],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_PAPER_KOKU,
    yedek_kok: Annotated[Path, typer.Option("--yedek")] = Path("runs/yedek"),
    rapor: Annotated[Path | None, typer.Option("--rapor")] = None,
) -> None:
    """Geri yükleme tatbikatı (Faz 14 bitti kriteri): en son yedek boş bir dizine geri
    getirilir, bütün adımlar girdilerden **yeniden üretilir** (K-038) ve kayıtla bit düzeyinde
    karşılaştırılır; ayrıca yedekteki son adım canlı koşunun aynı adımıyla karşılaştırılır."""
    import tempfile

    from scryne_quant.live.evren_depo import EvrenKosuDeposu
    from scryne_quant.live.evren_motor import EvrenPaperMotoru

    yedekler = sorted(yedek_kok.glob(f"{kosu_adi}-*.sqlite"))
    if not yedekler:
        raise typer.BadParameter(f"{kosu_adi}: yedek yok ({yedek_kok})")
    yedek = yedekler[-1]
    govde: dict[str, Any] = {"kosu": kosu_adi, "yedek": str(yedek), "zaman": utc_str(simdi_ms())}
    with tempfile.TemporaryDirectory() as gecici:
        geri = Path(gecici) / f"{kosu_adi}.sqlite"
        _sqlite_yedekle(yedek, geri)
        depo = EvrenKosuDeposu(geri)
        try:
            kurulum = _evren_kurulum_kimlikten(depo.kimlik_oku() or {})
            t0 = time.perf_counter()
            motor = EvrenPaperMotoru.toparlan(depo, **kurulum)  # ayrışmada hata fırlatır
            govde["yeniden_uretim_s"] = round(time.perf_counter() - t0, 1)
            kayitli = depo.adimlar()
        finally:
            depo.kapat()
    son = kayitli[-1]
    govde.update(adim=len(kayitli), son_bar=utc_str(son.open_time), islem=son.islem,
                 yeniden_uretilen_ozkaynak=motor.son_sonuc.ozkaynak, kayitli_ozkaynak=son.ozkaynak)
    canli = _paper_yolu(kosu_adi, kok)
    with tempfile.TemporaryDirectory() as gecici:
        kopya = Path(gecici) / "canli.sqlite"
        _sqlite_yedekle(canli, kopya)
        d2 = EvrenKosuDeposu(kopya)
        try:
            canli_adim = {a.adim: a for a in d2.adimlar()}.get(son.adim)
        finally:
            d2.kapat()
    govde["canliyla_ayni"] = canli_adim is not None and (
        repr(canli_adim.ozkaynak), repr(canli_adim.brut), canli_adim.islem) == (
        repr(motor.son_sonuc.ozkaynak), repr(motor.son_sonuc.brut), motor.son_sonuc.islem)
    govde["gecti"] = bool(govde["canliyla_ayni"]
                         and repr(motor.son_sonuc.ozkaynak) == repr(son.ozkaynak))
    if rapor is not None:
        rapor.parent.mkdir(parents=True, exist_ok=True)
        rapor.write_text(json.dumps(govde, ensure_ascii=False, indent=2), encoding="utf-8")
    for anahtar, deger in govde.items():
        typer.echo(f"{anahtar:<26}: {deger}")
    if not govde["gecti"]:
        raise typer.Exit(code=1)


@paper_app.command("evren-sapma")
def paper_evren_sapma(
    kosu_adi: Annotated[str, typer.Argument()],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_PAPER_KOKU,
    rapor: Annotated[Path | None, typer.Option("--rapor", help="JSON satırı eklenecek dosya.")]
    = None,
    json_cikti: JsonCikti = False,
) -> None:
    """Canlı-backtest sapması: aynı motor, girdiler baştan biliniyormuş gibi. (Faz 14, §6/2)

    Koşu dosyasına dokunmaz: SQLite yedeği geçici bir dosyaya alınır. Konfigürasyon koşu
    kimliğinden yeniden kurulur ve kimlikle bire bir tutması doğrulanır; tutmazsa ölçmez.
    """
    import tempfile

    from scryne_quant.live.evren_depo import EvrenKosuDeposu
    from scryne_quant.live.evren_sapma import sapma_olc

    kosu_yolu = _paper_yolu(kosu_adi, kok)
    if not kosu_yolu.exists():
        raise typer.BadParameter(f"koşu yok: {kosu_yolu}")
    with tempfile.TemporaryDirectory() as gecici:
        kopya = Path(gecici) / "kopya.sqlite"
        _sqlite_yedekle(kosu_yolu, kopya)
        depo = EvrenKosuDeposu(kopya)
        try:
            kurulum = _evren_kurulum_kimlikten(depo.kimlik_oku() or {})
            t0 = time.perf_counter()
            sonuc = sapma_olc(depo, **kurulum).sozluk()
        finally:
            depo.kapat()
    govde = {"kosu": kosu_adi, "olculdu": utc_str(simdi_ms()),
             "sure_s": round(time.perf_counter() - t0, 1), **sonuc}
    if rapor is not None:
        rapor.parent.mkdir(parents=True, exist_ok=True)
        with rapor.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(govde, ensure_ascii=False, sort_keys=True) + "\n")
    if json_cikti:
        _yaz_json(govde)
        return
    for anahtar, deger in govde.items():
        typer.echo(f"{anahtar:<22}: {deger}")


@paper_app.command("evren-durum")
def paper_evren_durum(
    kosu_adi: Annotated[str, typer.Argument()],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_PAPER_KOKU,
    son_olay: Annotated[int, typer.Option("--olay", help="Gösterilecek son olay sayısı.")] = 10,
) -> None:
    """Evren koşusunun son durumu ve olayları (koşu dosyasına dokunmadan)."""
    from scryne_quant.live.evren_depo import EvrenKosuDeposu

    kosu_yolu = _paper_yolu(kosu_adi, kok)
    durum_yolu = kosu_yolu.with_suffix(kosu_yolu.suffix + ".durum.json")
    if durum_yolu.exists():
        for anahtar, deger in json.loads(durum_yolu.read_text(encoding="utf-8")).items():
            typer.echo(f"{anahtar:<15}: {deger}")
    else:
        typer.echo("durum dosyası yok (koşu hiç başlamamış olabilir)")
    if kosu_yolu.exists():
        depo = EvrenKosuDeposu(kosu_yolu)
        try:
            olaylar = depo.olaylar()
        finally:
            depo.kapat()
        kopma = sum(o["tur"] == "kopma" for o in olaylar)
        gec = sum(o["tur"] == "gec_bar" for o in olaylar)
        typer.echo(f"olay           : {len(olaylar)} (kopma {kopma}, geç bar {gec})")
        for o in olaylar[-son_olay:]:
            typer.echo(f"  {utc_str(o['zaman_ms'])}  {o['tur']:<18} {o['ayrinti']}")


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
    program: Annotated[
        str,
        typer.Option("--program", "-p", help="Ait olduğu açık araştırma programı (K-051/2)."),
    ] = "",
    evren: Annotated[
        str, typer.Option("--evren", help="Evren kuralının kimliği (K-051/4).")
    ] = "",
    portfoy: Annotated[
        str, typer.Option("--portfoy", help="Portföy kurma yöntemi kodu (K-051/4).")
    ] = "",
    rejim: Annotated[
        str, typer.Option("--rejim", help="Rejim tanımının kimliği (K-051/4).")
    ] = "",
    depo: Depo = VARSAYILAN_DEPO,
    json_cikti: JsonCikti = False,
) -> None:
    """Bir hipotezi **sonucu görmeden önce** deftere kaydeder. (K-039, K-051)

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
    depo_nesnesi = ParquetDepo(depo)
    bar_sha = depo_nesnesi.sha256(sembol, timeframe)
    f_sha: str | None = None
    if _funding_okuyor_mu(strateji_adi):
        f_sha = _funding_hash(funding_mod.oku(sembol))
    sha = _veri_kimligi(strateji_adi, bar_sha, f_sha)
    hipotez = hipotez_mod.Hipotez.kur(
        strateji_adi,
        timeframe,
        sha,
        izgara,
        gerekce,
        secim=secim,
        program=program,
        evren=evren,
        portfoy=portfoy,
        rejim=rejim,
        # Geri sarma adresi (K-080): defter satırı hangi veri sonuyla yazıldıysa o.
        veri_son_ms=int(depo_nesnesi.oku(sembol, timeframe)["open_time"].iloc[-1]),
    )

    defter = hipotez_mod.HipotezDefteri()
    programlar = program_mod.ProgramDefteri()
    onceki = defter.sira(hipotez)
    # Program kaydı olmadan araştırma programı koşturulamaz (K-051/2). Zaten kayıtlı bir
    # hipotez yeni bir çekiliş değil, dolayısıyla bütçeden de düşmez.
    sira = defter.kaydet(hipotez, programlar=None if onceki is not None else programlar)

    butce = None
    if program:
        butce = programlar.butce(program, defter.tumu())
    govde = {
        "sira": sira,
        "toplam": defter.sayi(),
        "yeni": onceki is None,
        "hipotez": hipotez.sozluk(),
        "butce": butce,
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
    if butce is not None:
        typer.echo(
            f"bütçe  : {program} · {butce['harcanan']}/{butce['azami_cekilis']} "
            f"(kalan {butce['kalan']})"
        )


def _typesafe_istemci():
    """Tek, komut boyu açık istemci. Testler bunu sahtesiyle değiştirir; ağa çıkmaz.

    Import burada: SDK yalnızca bu komutun bağımlılığı, `sq`nin geri kalanı onsuz açılmalı.
    Anahtar `TYPESAFE_API_KEY` ortam değişkeninden okunur.
    """
    from typesafe_sdk import TypeSafeClient

    return TypeSafeClient()


@lab_app.command("tekrar-kontrol")
def lab_tekrar_kontrol(
    strateji_adi: Annotated[
        str | None, typer.Argument(help="Kaydedilecek stratejinin adı (--sira yoksa zorunlu).")
    ] = None,
    gerekce: Annotated[
        str, typer.Option("--gerekce", "-g", help="Kaydedilecek gerekçe metni.")
    ] = "",
    timeframe: Annotated[str, typer.Option("--timeframe", "-t")] = "1h",
    secim: Secim = "tepe",
    program: Annotated[str, typer.Option("--program", "-p")] = "",
    portfoy: Annotated[str, typer.Option("--portfoy")] = "",
    sira: Annotated[
        int | None,
        typer.Option(
            "--sira", help="Defterde zaten kayıtlı N. hipotezi kendinden öncekilerle karşılaştır."
        ),
    ] = None,
    kayit_koku: Annotated[
        Path, typer.Option("--kayit-koku", help="Dondurulmuş istek/cevap kaydının klasörü.")
    ] = gizli_tekrar_mod.VARSAYILAN_KAYIT_KOKU,
    json_cikti: JsonCikti = False,
) -> None:
    """Yeni hipotez, önceki bir kaydın mekanizmasını başka adla mı deniyor? (K-061, K-039)

    `sq lab hipotez-kaydet`ten **önce** çalıştırılır. Engellemez ve çekiliş sayılmaz:
    uyarı verir, karar Scryne'ındır. Jev'e (TypeSafe) gider; `TYPESAFE_API_KEY` gerekir.
    """
    defter = hipotez_mod.HipotezDefteri().tumu()
    if sira is not None:
        if not 1 <= sira <= len(defter):
            raise typer.BadParameter(f"defterde {len(defter)} kayıt var: --sira {sira}")
        yeni, onceki = defter[sira - 1], defter[: sira - 1]
    else:
        if not strateji_adi or len(gerekce.strip()) < 20:
            raise typer.BadParameter("strateji adı ve ≥20 karakterlik --gerekce gerekli")
        yeni = {
            "strateji": strateji_adi,
            "program": program,
            "timeframe": timeframe,
            "secim": secim,
            "portfoy": portfoy,
            "izgara": {a: list(d) for a, d in strateji_izgarasi(strateji_adi).items()},
            "gerekce": gerekce,
        }
        onceki = defter
    if not onceki:
        raise typer.BadParameter("karşılaştırılacak önceki kayıt yok")

    istemci = _typesafe_istemci()
    try:
        govde = gizli_tekrar_mod.kontrol_et(istemci, yeni, onceki, kayit_koku=kayit_koku)
    finally:
        istemci.close()

    if json_cikti:
        _yaz_json(govde)
        return
    typer.echo(
        f"{govde['karsilastirma']} kayıtla karşılaştırıldı · model {govde['model']} · "
        f"uyarı {govde['uyari']} · incele {govde['incele']}"
    )
    for b in govde["bulgular"]:
        if b["seviye"] == "temiz":
            continue
        etiket = "UYARI " if b["seviye"] == "uyari" else "incele"
        typer.echo(
            f"  {etiket} h{b['sira']:<3} {b['strateji']:<24} ilgili {b['ilgili']:.2f} "
            f"(aynı {b['ayni']:.2f}, param {b['param']:.2f}) → {b['karar']}"
        )
    if not govde["uyari"] and not govde["incele"]:
        typer.echo("  benzer mekanizma bulunmadı")
    if "kayit" in govde:
        typer.echo(f"kayıt : {govde['kayit']}")


def _coklu_test_cekilisleri(depo: Path, deney_kok: Path):
    """Defterdeki hipotezleri **ölçülebilir** olanlarla eşleştirip yeniden üretir. (K-039)

    Eşleşme anahtarı hipotez kimliğinin üç parçası: `(timeframe, secim, veri_sha256)`.
    Parametre ızgarası anahtara girmiyor çünkü ızgara değişikliği zaten **yeni bir
    hipotez** (K-039) ve yeni bir kimlik üretir.

    **Ölçülemeyen çekiliş atlanır ve sebebi döner.** Faz 4'e dönüş 1'de 1d'nin yedi
    çekilişi walk-forward'ı tamamlayamamıştı — araç sayı uydurmak yerine reddetmişti.
    Sayı üretmemiş bir çekiliş yanlış pozitif de **üretemez**, dolayısıyla maksimum
    istatistiğine giremez. Ama defterden silinmez: denendi, sayılır.
    """
    defter = hipotez_mod.HipotezDefteri()
    indeks: dict[tuple[str, str, str], dict[str, Any]] = {}
    for yol in sorted(Path(deney_kok).glob("degerlendirme/*.json")):
        kayit = json.loads(yol.read_text(encoding="utf-8"))
        g = kayit["girdi"]
        indeks[(g["timeframe"], g.get("secim", "tepe"), kayit["kimlik"]["veri_sha256"])] = kayit

    diziler_ob: dict[str, Any] = {}
    cekilisler: list[coklu_mod.Cekilis] = []
    ayar: dict[str, dict[str, Any]] = {}
    atlanan: list[dict[str, str]] = []

    for h in defter.tumu():
        tf, secim, sha = h["timeframe"], h["secim"], h["veri_sha256"]
        kayit = indeks.get((tf, secim, sha))
        blok = None if kayit is None else kayit["cikti"]["stratejiler"].get(h["strateji"])
        if blok is None or blok["olcumler"].get("oos_sharpe") is None:
            atlanan.append(
                {
                    "strateji": h["strateji"],
                    "timeframe": tf,
                    "secim": secim,
                    "sebep": "değerlendirme kaydı yok" if kayit is None else "ölçüm üretilmedi",
                }
            )
            continue

        if tf not in diziler_ob:
            diziler_ob[tf], _, _ = _lab_veri(depo, "BTCUSDT", tf)
        m = kayit["girdi"]["maliyet"]
        model = maliyet_mod.MaliyetModeli(
            fee_taker_bps=m["fee_taker_bps"],
            slippage_bps=m["slippage_bps"],
            kalibrasyon=(
                maliyet_mod.SlippageKalibrasyonu(**m["kalibrasyon"])
                if m.get("kalibrasyon")
                else None
            ),
        )
        pw = kayit["cikti"]["pencereler"]["out_of_sample"]
        pencere = bolme.Pencere(
            ad=pw["ad"],
            baslangic=pw["baslangic"],
            bitis=pw["bitis"],
            isinma_baslangic=pw["isinma_baslangic"],
        )
        secilen = blok["olcumler"]["secilen"]
        strateji = coz(h["strateji"])(**secilen)
        takvim, sonuc = coklu_mod.takvim_cikar(
            strateji,
            model,
            "BTCUSDT",
            tf,
            diziler_ob[tf],
            pencere,
            baslangic_sermaye=kayit["girdi"]["baslangic_sermaye"],
            veri_sha256=sha,
        )
        # Yeniden üretim kayıtla tutmuyorsa bu bir ölçüm değil tahmin olur (K-009).
        kayitli = float(blok["olcumler"]["oos_sharpe"])
        if abs(sonuc.metrikler.sharpe - kayitli) > 1e-9:
            raise typer.BadParameter(
                f"{h['strateji']}/{tf}/{secim} yeniden üretilemedi: kayıt {kayitli:.10f}, "
                f"üretilen {sonuc.metrikler.sharpe:.10f}. Çoklu test bu çekilişi ölçemez."
            )
        c = coklu_mod.Cekilis(
            kimlik=h["kimlik"],
            strateji=h["strateji"],
            timeframe=tf,
            secim=secim,
            secilen=secilen,
            veri_sha256=sha,
            gercek_sharpe=sonuc.metrikler.sharpe,
            isinma_bar=strateji.isinma_bar(),
            oos_bar=pencere.bitis - pencere.baslangic,
            takvim_bar=pencere.bitis - pencere.isinma_baslangic,
            takvim=takvim,
        )
        cekilisler.append(c)
        ayar[c.kimlik] = {
            "maliyet": model,
            "pencere": pencere,
            "sermaye": kayit["girdi"]["baslangic_sermaye"],
        }

    return cekilisler, ayar, diziler_ob, atlanan, defter.sayi()


@lab_app.command("coklu-test")
def lab_coklu_test(
    deneme: Annotated[int, typer.Option("--deneme", "-n", help="Null iterasyon sayısı.")] = 1_000,
    seed: Annotated[int, typer.Option("--seed")] = 0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """K-039'un açık düzeltmesi: kaç çekiliş yapıldıysa eşik ne olmalı? (K-039, K-019)

    K-039 sayımı getirdi ama düzeltmeyi **açık bıraktı**: *"stratejiler bağımsız değil,
    düzeltme çarpanı bilinmiyor, uydurulan bir çarpan olmayan bir kesinlik iddia eder."*
    Bu komut çarpanı uydurmuyor — defterdeki çekilişleri, edge'i olmayan bir dünyada
    yeniden koşturup **ölçüyor**.

    Yöntem `research/coklu_test.py`de: her çekilişin OOS sinyal takvimi dairesel
    kaydırılıp gerçek backtest motorundan geçiriliyor; kaydırma iterasyon başına
    **paylaşılıyor** ki stratejiler arası korelasyon bozulmasın. Maksimum, K-019'un ucuz
    kapılarını geçen çekilişler arasından alınıyor.

    Pahalıdır (31 çekiliş × 1.000 iterasyon ≈ 15 dakika). Ucuz olmamalı: çıktısı bir
    promotion eşiği.
    """
    cekilisler, ayar, diziler_ob, atlanan, defter_sayisi = _coklu_test_cekilisleri(depo, deney_kok)
    if not cekilisler:
        raise typer.BadParameter("ölçülebilir çekiliş yok")

    asgari = next(e for e in kapilar_mod.ESIKLER if e.ad == "asgari_islem")
    azami_dd = next(e for e in kapilar_mod.ESIKLER if e.ad == "max_drawdown")

    def kosturucu(c, takvim):
        a = ayar[c.kimlik]
        r = tarama_mod.kosu(
            coklu_mod.BetikStrateji(takvim, isinma=c.isinma_bar),
            a["maliyet"],
            "BTCUSDT",
            c.timeframe,
            diziler_ob[c.timeframe],
            a["pencere"],
            baslangic_sermaye=a["sermaye"],
            veri_sha256=c.veri_sha256,
        )
        islem = len([i for i in r.islemler if i.kapali])
        uygun = bool(asgari.gecti_mi(islem)) and bool(azami_dd.gecti_mi(r.metrikler.max_drawdown))
        return r.metrikler.sharpe, uygun

    null = coklu_mod.null_dagilimi(cekilisler, kosturucu, deneme=deneme, seed=seed)

    sharpe_kapisi = next(e for e in kapilar_mod.ESIKLER if e.ad == "oos_sharpe")
    oranlar = (0.20, 0.10, 0.05, 0.01)
    govde = {
        "defter_sayisi": defter_sayisi,
        "olculebilir": len(cekilisler),
        "atlanan": atlanan,
        "uygunluk_kapilari": [asgari.ad, azami_dd.ad],
        "mevcut_esik": sharpe_kapisi.sinir,
        "null": null.sozluk(),
        "duzeltilmis_esikler": {f"{o:.2f}": null.duzeltilmis_esik(o) for o in oranlar},
        "esik_guven_araliklari": {f"{o:.2f}": list(null.esik_guven_araligi(o)) for o in oranlar},
        "mevcut_esigin_yanlis_pozitifi": float((null.azami >= sharpe_kapisi.sinir).mean()),
        "cekilisler": [c.sozluk() for c in cekilisler],
    }

    yol = deney_mod.Deney(
        tip="coklu_test",
        strateji="+".join(sorted({c.strateji for c in cekilisler})),
        veri_sha256=hashlib.sha256(
            "|".join(sorted(c.veri_sha256 for c in cekilisler)).encode()
        ).hexdigest(),
        girdi={"deneme": deneme, "seed": seed, "defter_sayisi": defter_sayisi},
        cikti=govde,
        seed=seed,
    ).yaz(deney_kok)

    if json_cikti:
        _yaz_json({"deney": str(yol), **govde})
        return

    typer.echo(
        f"defter {defter_sayisi} hipotez · ölçülebilir {len(cekilisler)} · atlanan {len(atlanan)}"
    )
    for a in atlanan:
        typer.echo(f"    atlandı: {a['strateji']:<15} {a['timeframe']:<3} {a['sebep']}")
    typer.echo("")
    typer.echo(
        f"  null (edge yok, {len(cekilisler)} çekiliş, {deneme} iterasyon) — "
        "en iyi çekilişin OOS Sharpe'ı:"
    )
    for ad, deger in null.azami_dagilimi.items():
        typer.echo(f"    {ad}  {deger:>7.3f}")
    typer.echo("")
    typer.echo(f"  gerçek en iyi : {null.gercek_en_iyi:.4f} ({null.gercek_en_iyi_strateji})")
    typer.secho(
        f"  p-değeri      : {null.p_degeri:.3f}  — edge olmasa bile bu kadar iyi bir "
        "sonucun çıkma olasılığı",
        fg=typer.colors.YELLOW if null.p_degeri > 0.05 else typer.colors.GREEN,
    )
    typer.echo("")
    typer.echo(
        f"  mevcut eşik {sharpe_kapisi.sinir} → yanlış-pozitif "
        f"{govde['mevcut_esigin_yanlis_pozitifi']:.1%}"
    )
    typer.echo("  düzeltilmiş eşik adayları (%90 bootstrap güven aralığıyla):")
    for o in oranlar:
        alt, ust = null.esik_guven_araligi(o)
        typer.echo(
            f"    yanlış-pozitif {o:>5.0%}  →  oos_sharpe ≥ {null.duzeltilmis_esik(o):.3f}"
            f"   [{alt:.3f} – {ust:.3f}]"
        )
    typer.echo("")
    typer.echo(f"  deney: {yol}")


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


@evren_app.command("backtest")
def evren_backtest(
    tablo: Annotated[Path, typer.Argument(help="PIT evren tablosu (.parquet).")],
    strateji: Annotated[
        str, typer.Option("--strateji", help="Çok enstrümanlı strateji/kıyas adı.")
    ] = "evren_esit_agirlik",
    baslangic_ay: Annotated[
        str, typer.Option("--baslangic", help="Pencere başlangıcı, YYYY-MM.")
    ] = "",
    bitis_ay: Annotated[str, typer.Option("--bitis", help="Pencere bitişi, YYYY-MM.")] = "",
    azami_enstruman: Annotated[
        int, typer.Option("--azami-enstruman", help="Aynı anda taşınacak azami pozisyon.")
    ] = 10,
    azami_agirlik: Annotated[
        float, typer.Option("--azami-agirlik", help="Tek enstrüman ağırlık tavanı.")
    ] = 0.30,
    yeniden_dengele: Annotated[
        int, typer.Option("--yeniden-dengele", help="Yeniden dengeleme periyodu (bar).")
    ] = 720,
    oynaklik_ayarli: Annotated[
        bool, typer.Option("--oynaklik-ayarli", help="Eşit ağırlık yerine oynaklık ayarlı boyut.")
    ] = False,
    azami_sembol: Annotated[
        int, typer.Option("--azami-sembol", help="Bellek tavanı: yüklenecek azami sembol.")
    ] = 120,
    sermaye: Annotated[float, typer.Option("--sermaye")] = 10_000.0,
    depo_kok: Depo = arsiv_mod.VARSAYILAN_EVREN_DEPO,
    fx_depo: Annotated[
        Path, typer.Option("--fx-depo", help="FX tablosu için FXCM depo kökü (K-096).")
    ] = fx_mod.VARSAYILAN_DEPO,
    yaz: Annotated[bool, typer.Option("--yaz/--yazma", help="Sonucu runs/ altına yaz.")] = True,
    json_cikti: JsonCikti = False,
) -> None:
    """Evren üzerinde çok enstrümanlı backtest koşturur. (Faz 10)

    **Bu komut alfa aramaz.** Varsayılan strateji bir kıyastır (K-030): "o ay listelenmiş
    likit isimlerin hepsini taşısaydım ne olurdu". Bir araştırma programı açmadan
    (K-051) buradan bir hipotez üretilmez; ölçülen şey çekirdeğin kendisi.

    **FX tablosu (K-096):** tablo meta'sı `fxcm-candledata-m1` kaynağını taşıyorsa görünüm
    `--fx-depo`dan `fx_gorunum` ile kurulur (bid/ask fill, kalite bayrağı), takvim tablonun
    takvimi (`fx-5x24`) olarak motora geçer; maliyet (`fxcm-fx`) ve finansman (`fxcm-<çift>`)
    modelleri katalogdan **zorunlu** çözülür — dosya yoksa koşu başlamaz (K-084, K-095).
    Varsayılan kıyas kote hacim ister; FX'te hacim yok, o yüzden sinyal üretmez — FX için
    kıyas tanımı ayrı karar (K-030).
    """
    if strateji not in EVREN_KIYAS:
        raise typer.BadParameter(
            f"{strateji!r} çok enstrümanlı kütüphanede yok; kayıtlı: "
            f"{', '.join(sorted(EVREN_KIYAS))}"
        )
    sinif = EVREN_KIYAS[strateji]
    nesne = sinif(
        yeniden_dengele_bar=yeniden_dengele,
        azami_enstruman=azami_enstruman,
        azami_agirlik=azami_agirlik,
        esit_agirlik=not oynaklik_ayarli,
    )

    basladi = time.perf_counter()
    _, tablo_meta = evren_kosu_mod.tablo_oku(tablo)
    takvim: takvim_mod.Takvim | None = None
    if evren_kosu_mod.fx_tablo_mu(tablo_meta):
        kurulum = evren_kosu_mod.fx_kur(
            tablo,
            nesne,
            depo_kok=fx_depo,
            baslangic_ay=baslangic_ay or None,
            bitis_ay=bitis_ay or None,
            azami_sembol=azami_sembol,
        )
        takvim = takvim_mod.takvim(str(kurulum.meta["takvim"]["id"]))
    else:
        kurulum = evren_kosu_mod.kur(
            tablo,
            nesne,
            depo_kok=depo_kok,
            baslangic_ay=baslangic_ay or None,
            bitis_ay=bitis_ay or None,
            azami_sembol=azami_sembol,
        )
    kurulum_sn = time.perf_counter() - basladi

    # K-084/U14: her enstrümanın `maliyet_modeli_id`si katalogdan çözümlenir (dosya yoksa /
    # global spot dışıysa hata). Bugünkü Binance spot evreninde hepsi `global` → `None`,
    # motor tek-model yolunda ve kayıt biçimi Faz 10-16 ile aynı.
    maliyetler = evren_kosu_mod.enstruman_maliyetleri(
        maliyet_mod.MaliyetKatalogu(), kurulum.kimlikler
    )
    # K-095: `finansman_modeli_id` taşıyan (cfd) üye varsa modeli katalogdan çözülür (dosya
    # yoksa hata); spot evreninde hepsi `None` → motor finansmansız yolda. FX tablosunda takvim
    # yukarıda çözüldü (K-096); finansman seanslı takvimle motora girer.
    finansmanlar = evren_kosu_mod.enstruman_finansmanlari(
        finansman_mod.FinansmanKatalogu(), kurulum.kimlikler
    )
    basladi = time.perf_counter()
    sonuc = CokluBacktest(
        nesne,
        maliyet_mod.yukle(),
        baslangic_sermaye=sermaye,
        maliyetler=maliyetler,
        finansmanlar=finansmanlar,
        takvim=takvim,
    ).calistir(
        kurulum.gorunum,
        veri_sha256=kurulum.veri_sha256,
        olcum_baslangici=kurulum.olcum_baslangici,
    )
    kosu_sn = time.perf_counter() - basladi

    yol: Path | None = None
    if yaz:
        yol = sonuc.yaz(
            VARSAYILAN_KOSU_KOKU
            / "evren"
            / f"{sonuc.config_hash[:12]}-{sonuc.sonuc_hash[:12]}.json"
        )

    m = sonuc.metrikler
    ozet = {
        "evren": kurulum.meta,
        "strateji": strateji,
        "kurulum_sn": round(kurulum_sn, 2),
        "kosu_sn": round(kosu_sn, 2),
        "config_hash": sonuc.config_hash,
        "sonuc_hash": sonuc.sonuc_hash,
        "metrikler": m.sozluk(),
        "akis": sonuc.sozluk()["akis"],
        "kayit": str(yol) if yol else None,
    }
    if json_cikti:
        _yaz_json(ozet)
        return

    typer.echo(f"evren backtest · {strateji} · {kurulum.meta['sembol_sayisi']} sembol")
    typer.echo(
        f"  pencere      : {baslangic_ay or 'başı'} … {bitis_ay or 'sonu'} "
        f"({kurulum.meta['bar_sayisi']:,} bar, {kurulum.meta['uye_bar_toplami']:,} üye bar)"
    )
    typer.echo(f"  süre         : kurulum {kurulum_sn:.1f} s · koşu {kosu_sn:.1f} s")
    typer.echo(
        f"  sermaye      : {m.baslangic_sermaye:,.0f} → {m.bitis_sermaye:,.0f} "
        f"({m.toplam_getiri:+.2%})"
    )
    typer.echo(f"  Sharpe/MaxDD : {m.sharpe:+.3f} / {m.max_drawdown:.2%}")
    typer.echo(f"  işlem        : {m.islem_sayisi:,} (turnover {m.turnover:.1f}×)")
    typer.echo(f"  VaR/CVaR %95 : {m.var_95:.3%} / {m.cvar_95:.3%}")
    typer.echo(
        f"  kapasite ADV : azami {m.kapasite_adv_azami:.4%} · "
        f"ortalama {m.kapasite_adv_ortalama:.4%}"
    )
    typer.echo(f"  maliyet      : {m.toplam_komisyon + m.toplam_slippage:,.0f}")
    typer.echo(f"  sonuc_hash   : {sonuc.sonuc_hash[:16]}")
    if yol:
        typer.echo(f"  kayıt        : {yol}")


# --------------------------------------------------------------- araştırma programları


@lab_app.command("program-kaydet")
def lab_program_kaydet(
    ad: Annotated[str, typer.Argument(help="Program adı (kod: a-z, 0-9, _).")],
    gerekce: Annotated[
        str, typer.Option("--gerekce", "-g", help="Program neden açılıyor? (≥60 karakter)")
    ],
    kaynak_farki: Annotated[
        str,
        typer.Option(
            "--kaynak-farki",
            "-k",
            help="Bilgi kaynağı neden belirgin biçimde farklı? (≥60 karakter, K-045)",
        ),
    ],
    kaynak_olcumu: Annotated[
        str,
        typer.Option("--kaynak-olcumu", help="Farkın sayısal dayanağı (JSON nesnesi)."),
    ],
    azami_cekilis: Annotated[
        int, typer.Option("--azami-cekilis", "-n", help="Arama bütçesi: azami hipotez sayısı.")
    ],
    durma_kurali: Annotated[
        str,
        typer.Option("--durma-kurali", "-d", help="Ne olursa durulacak? (K-042, ≥20 karakter)"),
    ],
    esik_tahmini: Annotated[
        str,
        typer.Option("--esik-tahmini", help="Bütçe dahil eşiğin mertebe tahmini (JSON nesnesi)."),
    ],
    json_cikti: JsonCikti = False,
) -> None:
    """Bir araştırma programını **ön kayıtla** açar. (K-051/2)

    Program kaydı olmadan hipotez kaydedilemez: K-044 her yeni çekilişin `oos_sharpe`
    kapısını yükselttiğini ölçtü, yani bir arama programı bulduğu şeyi geçiremeyeceği bir
    duvarı kendisi örebilir. Kayıt o duvarın fiyatını baştan görünür kılıyor.

    `--esik-tahmini` **kapı değildir**; kapı program bitiminde `sq lab coklu-test` ile
    ölçülür (K-044). Amacı programın kendi maliyetini baştan yazması.
    """
    try:
        olcum = json.loads(kaynak_olcumu)
        tahmin = json.loads(esik_tahmini)
    except json.JSONDecodeError as hata:
        raise typer.BadParameter(f"JSON çözülemedi: {hata}") from hata
    if not isinstance(olcum, dict) or not isinstance(tahmin, dict):
        raise typer.BadParameter("--kaynak-olcumu ve --esik-tahmini birer JSON nesnesi olmalı")

    kayit = program_mod.ProgramKaydi(
        ad=ad,
        gerekce=gerekce,
        kaynak_farki=kaynak_farki,
        kaynak_olcumu=olcum,
        azami_cekilis=azami_cekilis,
        durma_kurali=durma_kurali,
        esik_tahmini=tahmin,
    )
    defter = program_mod.ProgramDefteri()
    defter.ac(kayit)
    hipotezler = hipotez_mod.HipotezDefteri().tumu()
    butce = defter.butce(ad, hipotezler)

    if json_cikti:
        _yaz_json({"program": kayit.sozluk(), "butce": butce})
        return
    typer.echo(f"program açıldı: {ad}")
    typer.echo(f"  kimlik  : {kayit.kimlik[:16]}")
    typer.echo(f"  bütçe   : {butce['harcanan']}/{butce['azami_cekilis']}")
    typer.echo(f"  durma   : {kayit.durma_kurali}")
    typer.echo(f"  defter  : {defter.yol}")


@lab_app.command("program-kapat")
def lab_program_kapat(
    ad: Annotated[str, typer.Argument(help="Kapatılacak program adı.")],
    sonuc: Annotated[str, typer.Option("--sonuc", "-s", help="Ne bulundu? (≥20 karakter)")],
    json_cikti: JsonCikti = False,
) -> None:
    """Bir araştırma programını kapatır. Kapanış ayrı bir satır — defter append-only."""
    defter = program_mod.ProgramDefteri()
    hipotezler = hipotez_mod.HipotezDefteri().tumu()
    harcanan = defter.harcanan(ad, hipotezler)
    kapanis = defter.kapat(ad, sonuc, harcanan)
    if json_cikti:
        _yaz_json(kapanis.sozluk())
        return
    typer.echo(f"program kapandı: {ad} · {harcanan} çekiliş harcandı")


@lab_app.command("butce")
def lab_butce(
    ad: Annotated[str, typer.Argument(help="Program adı. Boş bırakılırsa hepsi.")] = "",
    json_cikti: JsonCikti = False,
) -> None:
    """Açık programların arama bütçesi durumu. (K-051/2)"""
    defter = program_mod.ProgramDefteri()
    hipotezler = hipotez_mod.HipotezDefteri().tumu()
    adlar = [ad] if ad else [k["ad"] for k in defter.acik_programlar()]
    satirlar = [defter.butce(a, hipotezler) for a in adlar]

    if json_cikti:
        _yaz_json({"programlar": satirlar, "defter_toplami": len(hipotezler)})
        return
    if not satirlar:
        typer.echo("açık araştırma programı yok")
        return
    typer.echo(f"defter: {len(hipotezler)} hipotez")
    for b in satirlar:
        durum = "DOLU" if b["kalan"] <= 0 else f"kalan {b['kalan']}"
        typer.echo(f"  {b['ad']:<24} {b['harcanan']:>3}/{b['azami_cekilis']:<3} {durum}")
        typer.echo(f"      durma: {b['durma_kurali']}")


@lab_app.command("kapilar-v2")
def lab_kapilar_v2(
    sembol: Sembol = "BTCUSDT",
    oos_orani: Annotated[float, typer.Option("--oos", help="OOS payı [0.1, 0.5].")] = 0.30,
    sermaye: Sermaye = 10_000.0,
    depo: Depo = VARSAYILAN_DEPO,
    deney_kok: KayitKok = deney_mod.VARSAYILAN_KOK,
    json_cikti: JsonCikti = False,
) -> None:
    """Defterdeki **her** çekilişi K-054'ün dört yeni kapısından geçirir. (Faz 11)

    Faz 11'in bitti kriteri: *"Defterdeki mevcut 38 çekiliş yeni kapılardan da geçirilmiş
    ve sonuç raporlanmış — geçen olsa da olmasa da."* Bu komut o raporun kendisi.

    Pahalıdır (çekiliş başına ~20 s): her çekiliş için in-sample taraması, OOS koşusu ve
    tam pencerede PBO matrisi yeniden üretiliyor.
    """
    defter = hipotez_mod.HipotezDefteri()
    kayitlar = defter.tumu()
    model = maliyet_mod.yukle()
    diziler_ob: dict[str, Any] = {}
    satirlar: list[dict[str, Any]] = []

    for h in kayitlar:
        ad, tf = h["strateji"], h["timeframe"]
        if tf not in diziler_ob:
            diziler_ob[tf], _, _ = _lab_veri(depo, sembol, tf)
        diziler = diziler_ob[tf]
        n = len(diziler["open_time"])
        isinma = karsilastirma_mod.ortak_isinma([ad])
        ins, oos = karsilastirma_mod.ortak_pencereler(n, [ad], oos_orani=oos_orani)
        tam = bolme.Pencere("tam", baslangic=isinma, bitis=n, isinma_baslangic=0)
        asgari = 0 if ad in KIYAS else tarama_mod.ASGARI_ISLEM

        try:
            olcumler = kapilar_v2_mod.olc(
                coz(ad),
                varsayilan_izgara(ad),
                model,
                sembol,
                tf,
                diziler,
                ins=ins,
                oos=oos,
                tam=tam,
                secim=h["secim"],
                baslangic_sermaye=sermaye,
                asgari_islem=asgari,
            )
            hata = ""
        except (ValueError, KeyError) as e:  # ölçülemeyen çekiliş atlanmaz, sebebiyle yazılır
            olcumler = {
                "pbo": None,
                "perturbasyon_dusus": None,
                "en_kotu_rejim_sharpe": None,
                "evren_dayaniklilik_orani": None,
            }
            hata = f"{type(e).__name__}: {e}"

        duz = {a: d for a, d in olcumler.items() if a != "detay"}
        kapi = kapilar_v2_mod.kapilari_degerlendir(f"{ad}/{tf}/{h['secim']}", duz)
        satirlar.append(
            {
                "kimlik": h["kimlik"],
                "strateji": ad,
                "timeframe": tf,
                "secim": h["secim"],
                "program": h.get("program", ""),
                "olcumler": duz,
                "kapilar": kapi.sozluk(),
                "hata": hata,
                "detay": olcumler.get("detay", {}),
            }
        )
        # Ara kayıt: her çekilişten sonra. Tam koşu bir saat sürüyor ve kayıt adımında
        # bir hata o saati silerdi — bu fazda iki kez oldu.
        ara = Path(deney_kok) / "kapilar_v2" / "_ara.json"
        ara.parent.mkdir(parents=True, exist_ok=True)
        ara.write_text(json.dumps(satirlar, ensure_ascii=False, default=str), encoding="utf-8")

    gecen = [s for s in satirlar if s["kapilar"]["gecti"]]
    govde = {
        "defter_sayisi": len(kayitlar),
        "esikler": kapilar_v2_mod.esik_tablosu(),
        "cekilisler": satirlar,
        "gecen": [s["kimlik"] for s in gecen],
    }
    yol = deney_mod.Deney(
        tip="kapilar_v2",
        strateji="+".join(sorted({s["strateji"] for s in satirlar})),
        veri_sha256=hashlib.sha256(
            "|".join(sorted({h["veri_sha256"] for h in kayitlar})).encode()
        ).hexdigest(),
        girdi={"oos_orani": oos_orani, "sermaye": sermaye, "defter_sayisi": len(kayitlar)},
        cikti=govde,
    ).yaz(deney_kok)

    if json_cikti:
        _yaz_json({"deney": str(yol), **govde})
        return

    typer.echo(f"defter {len(kayitlar)} çekiliş · yeni kapılar (K-054)")
    typer.echo(
        f"  {'çekiliş':<28} {'pbo':>7} {'perturbasyon':>13} {'rejim':>8} {'evren':>7}  kalan"
    )
    for s in satirlar:
        o = s["olcumler"]
        etiket = f"{s['strateji']}/{s['timeframe']}/{s['secim']}"
        typer.echo(
            f"  {etiket:<28} {_sayi(o['pbo']):>7} {_sayi(o['perturbasyon_dusus']):>13} "
            f"{_sayi(o['en_kotu_rejim_sharpe']):>8} "
            f"{_sayi(o['evren_dayaniklilik_orani']):>7}  "
            f"{len(s['kapilar']['kalan_kapilar'])}"
        )
    typer.echo("")
    typer.echo(f"  geçen: {len(gecen)}/{len(satirlar)}")
    typer.echo(f"  kayıt: {yol}")


def _sayi(deger: float | None) -> str:
    """Ölçülemeyen değer tabloda uzun tire ile görünür; `0,000` ile karıştırılmasın."""
    return "—" if deger is None else f"{deger:.3f}"


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
