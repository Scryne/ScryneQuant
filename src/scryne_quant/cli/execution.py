"""`sq execution` — mod durum makinesi, live gate, koşu, kill, onay. (K-114, R9)

Canlıya giden yol, sırasıyla:

    sq execution durum                         # mod, koşular, son kapı raporu
    sq execution preflight --hedef PAPER       # kontrol listesi (ağsız)
    sq execution yukselt PAPER                 # kapı geçerse bir adım yukarı
    sq execution calistir --mod paper ...      # uçtan uca paper koşusu → rapor.json
    sq execution yukselt SHADOW --ag           # salt okunur anahtar + canlı bağlantı
    sq execution calistir --mod shadow ...     # GOLGE emirler, gerçek hesap okunur
    sq execution yukselt TESTNET --ag
    sq execution calistir --mod testnet ...
    sq execution yukselt LIVE_PENDING_APPROVAL --strateji S --ag
    sq execution onayla --strateji S --hash <rapor hash> --not "..."   # yalnız insan, TTY
    sq execution calistir --mod live --strateji S ...                  # yetki yeniden türetilir

`onayla` **etkileşimlidir**: TTY değilse çalışmaz ve rapor hash'inin ilk 8 karakterini elle
yazmayı ister. Bu modül `mod.canli_onayla`yı çağıran tek yerdir
(`tests/unit/test_canli_izolasyon.py`).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from scryne_quant.common.hash import git_durumu
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.execution.canli_kapi import (
    AgYoklamasi,
    KapiBaglami,
    kapi_raporu,
    kosu_raporlari,
)
from scryne_quant.execution.mod import (
    SIRA,
    CalismaModu,
    ModDefteri,
    ModHatasi,
    canli_onayla,
    sira,
)
from scryne_quant.risk.audit import SqliteDefter

execution_app = typer.Typer(
    name="execution",
    help="Execution modu, live gate, paper/shadow/testnet/live koşuları. (K-114)",
)

KOK = Path("runs/execution")
AUDIT = Path("runs/audit.sqlite")
JsonCikti = Annotated[bool, typer.Option("--json", help="Çıktıyı JSON olarak ver.")]


def _yaz(nesne: Any) -> None:
    typer.echo(json.dumps(nesne, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _defter() -> ModDefteri:
    return ModDefteri(KOK / "mod.json", audit=SqliteDefter(AUDIT))


def _baglam(strateji: str | None, ag: bool) -> KapiBaglami:
    from scryne_quant.trader.kurulum import ag_yoklamasi

    return KapiBaglami(
        strateji=strateji,
        audit=SqliteDefter(AUDIT),
        ag=ag_yoklamasi() if ag else AgYoklamasi(),
        mod_defteri=ModDefteri(KOK / "mod.json"),
    )


def _mod_coz(ad: str) -> CalismaModu:
    try:
        return CalismaModu(ad.upper())
    except ValueError as hata:
        raise typer.BadParameter(f"bilinmeyen mod {ad!r}; geçerli: {', '.join(SIRA)}") from hata


def _rapor_bas(rapor: dict[str, Any]) -> None:
    renk = typer.colors.GREEN if rapor["gecti"] else typer.colors.RED
    typer.secho(
        f"{rapor['hedef']} kapısı: {'GEÇTİ' if rapor['gecti'] else 'KAPALI'}  "
        f"(hash {rapor['hash'][:16]}…)",
        fg=renk,
        bold=True,
    )
    for k in rapor["kontroller"]:
        isaret = "✓" if k["gecti"] is True else ("?" if k["gecti"] is None else "✗")
        typer.echo(f"  {isaret} {k['ad']:<24} {k['ayrinti']}")
        if k["gecti"] is not True and k["engel"]:
            typer.secho(f"      → {k['engel']}", fg=typer.colors.YELLOW)


# ------------------------------------------------------------------ durum


@execution_app.command("durum")
def durum(json_cikti: JsonCikti = False) -> None:
    """Sistem modu, mod geçmişi, koşular ve son raporlar."""
    kayit = ModDefteri(KOK / "mod.json").oku()
    kosular = []
    for p in sorted(KOK.glob("*/durum.json")) if KOK.is_dir() else []:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        kosular.append(
            {
                "kosu": p.parent.name,
                "mod": d.get("mod"),
                "halt": d.get("halt"),
                "safe_mode": d.get("safe_mode"),
                "ozkaynak": (d.get("hesap") or {}).get("ozkaynak"),
                "son_bar": (d.get("veri_tazeligi") or {}).get("son_bar_utc"),
            }
        )
    govde = {
        "mod": str(kayit.mod),
        "bozuk": kayit.bozuk,
        "gecmis": kayit.gecmis[-5:],
        "kosular": kosular,
        "raporlar": [
            {"kosu": p.parent.name, "mod": r.get("mod"), "gecti": r.get("gecti"),
             "bitis": r.get("bitis_utc")}
            for p, r in kosu_raporlari(KapiBaglami())
        ],
    }
    if json_cikti:
        _yaz(govde)
        return
    typer.secho(f"CURRENT MODE: {kayit.mod}", bold=True,
                fg=typer.colors.RED if kayit.mod is CalismaModu.LIVE else typer.colors.CYAN)
    if kayit.bozuk:
        typer.secho(f"  mod kaydı bozuk: {kayit.bozuk} (DISABLED okunuyor)", fg=typer.colors.RED)
    for s in govde["gecmis"]:
        typer.echo(f"  {s.get('zaman_utc')}  {s['nereden']} → {s['nereye']}  "
                   f"{s.get('not') or s.get('sebep') or ''}")
    for k in kosular:
        typer.echo(f"  koşu {k['kosu']:<20} {k['mod']:<8} özkaynak {k['ozkaynak']}  "
                   f"son bar {k['son_bar']}  halt={bool(k['halt'])} safe={k['safe_mode']}")


# ------------------------------------------------------------------ kapı


@execution_app.command("preflight")
def preflight(
    hedef: Annotated[str | None, typer.Option("--hedef", help="Hedef mod (vars. sıradaki)")] = None,
    strateji: Annotated[str | None, typer.Option("--strateji")] = None,
    ag: Annotated[bool, typer.Option("--ag", help="Ağ yoklamaları (salt okuma).")] = False,
    json_cikti: JsonCikti = False,
) -> None:
    """Hedef modun kontrol listesi. Hiçbir şey yazmaz, emir göndermez."""
    mevcut = ModDefteri(KOK / "mod.json").mod()
    h = _mod_coz(hedef) if hedef else SIRA[min(sira(mevcut) + 1, len(SIRA) - 1)]
    rapor = kapi_raporu(h, _baglam(strateji, ag))
    KOK.mkdir(parents=True, exist_ok=True)
    (KOK / f"preflight-{h}.json").write_text(
        json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    if json_cikti:
        _yaz(rapor)
    else:
        _rapor_bas(rapor)
    raise typer.Exit(0 if rapor["gecti"] else 1)


@execution_app.command("hazirlik")
def hazirlik(json_cikti: JsonCikti = False) -> None:
    """Proje gerçek paraya hazır mı? İki hüküm: sistem hazır ve strateji hazır. (K-122)

    Salt okuma: koşu dosyaları, test kaydı, R8 sonucu, promotion kayıtları. Hiçbir şey başlatmaz.
    Çıkış kodu 0 yalnız **ikisi birden** hazırsa.
    """
    from scryne_quant.execution import hazirlik as hz

    r = hz.rapor(".")
    if json_cikti:
        _yaz(r.sozluk())
        raise typer.Exit(0 if r.gercek_paraya_hazir else 1)
    for baslik, kontroller, hazir in (
        ("SİSTEM", r.sistem, r.sistem_hazir), ("STRATEJİ", r.strateji, r.strateji_hazir),
    ):
        typer.secho(f"{baslik}: {'HAZIR' if hazir else 'HAZIR DEĞİL'}", bold=True,
                    fg=typer.colors.GREEN if hazir else typer.colors.RED)
        for k in kontroller:
            isaret = {True: "✓", False: "✗", None: "?"}[k.gecti]
            typer.echo(f"  {isaret} {k.ad:<24} {k.ayrinti}")
            if k.gecti is not True and k.engel:
                typer.echo(f"      → {k.engel}")
    typer.secho(
        "GERÇEK PARA: " + ("koşullar sağlandı (son karar yine senin)" if r.gercek_paraya_hazir
                           else "HAYIR — yukarıdaki eksikler kapanmadan konmaz"),
        bold=True, fg=typer.colors.GREEN if r.gercek_paraya_hazir else typer.colors.YELLOW,
    )
    raise typer.Exit(0 if r.gercek_paraya_hazir else 1)


@execution_app.command("yukselt")
def yukselt(
    hedef: Annotated[str, typer.Argument(help="Bir üst mod (LIVE hariç).")],
    strateji: Annotated[str | None, typer.Option("--strateji")] = None,
    ag: Annotated[bool, typer.Option("--ag")] = False,
    not_metni: Annotated[str, typer.Option("--not")] = "",
) -> None:
    """Bir adım yukarı; kapının tamamı geçmezse yazılmaz. LIVE bu yoldan açılmaz."""
    h = _mod_coz(hedef)
    rapor = kapi_raporu(h, _baglam(strateji, ag))
    _rapor_bas(rapor)
    try:
        satir = _defter().yukselt(h, kapi_raporu=rapor, not_metni=not_metni)
    except ModHatasi as hata:
        typer.secho(str(hata), fg=typer.colors.RED)
        raise typer.Exit(1) from hata
    typer.secho(f"mod: {satir['nereden']} → {satir['nereye']}", fg=typer.colors.GREEN)


@execution_app.command("indir")
def indir(
    hedef: Annotated[str, typer.Argument()],
    sebep: Annotated[str, typer.Option("--sebep")],
) -> None:
    """Alt moda iner. Onay istemez (K-050: riski azaltan)."""
    satir = _defter().indir(_mod_coz(hedef), sebep=sebep)
    if satir is None:
        typer.echo("değişiklik yok")
    else:
        typer.echo(f"mod: {satir['nereden']} → {satir['nereye']}")


@execution_app.command("onayla")
def onayla(
    strateji: Annotated[str, typer.Option("--strateji")],
    rapor_hash: Annotated[str, typer.Option("--hash", help="Okuduğun LIVE raporunun hash'i.")],
    not_metni: Annotated[str, typer.Option("--not", help="Gerekçe (≥20 karakter).")],
    onaylayan: Annotated[str, typer.Option("--onaylayan")] = "Scryne",
) -> None:
    """LIVE_PENDING_APPROVAL → LIVE. **Yalnızca insan**, yalnızca etkileşimli terminalde.

    Kapı onay anında ağ yoklamalarıyla **yeniden** çalışır; rapor hash'i senin okuduğun
    hash ile aynı değilse onay verilmez.
    """
    if not sys.stdin.isatty():
        typer.secho("onay yalnızca etkileşimli terminalde verilir (K-114)", fg=typer.colors.RED)
        raise typer.Exit(2)
    rapor = kapi_raporu(CalismaModu.LIVE, _baglam(strateji, True))
    _rapor_bas(rapor)
    if not rapor["gecti"]:
        raise typer.Exit(1)
    typer.secho(
        f"\nGERÇEK PARA: strateji {strateji}, kademe {rapor['kademe']}, "
        f"sermaye {rapor['sermaye_usdt']} USDT.",
        fg=typer.colors.RED,
        bold=True,
    )
    yazilan = typer.prompt(f"Onaylamak için yaz: CANLI {rapor['hash'][:8]}")
    if yazilan.strip() != f"CANLI {rapor['hash'][:8]}":
        typer.secho("onay metni tutmadı; onay yok", fg=typer.colors.RED)
        raise typer.Exit(1)
    try:
        satir = canli_onayla(
            _defter(),
            kapi_raporu=rapor,
            gorulen_hash=rapor_hash,
            not_metni=not_metni,
            onaylayan=onaylayan,
        )
    except ModHatasi as hata:
        typer.secho(str(hata), fg=typer.colors.RED)
        raise typer.Exit(1) from hata
    typer.secho(f"LIVE açıldı: {satir['zaman_utc']} (onay {satir['satir_hash'][:16]}…)",
                fg=typer.colors.GREEN, bold=True)


# ------------------------------------------------------------------ koşu


def _parametreler(ham: list[str] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in ham or []:
        ad, _, deger = p.partition("=")
        try:
            out[ad] = json.loads(deger)
        except ValueError:
            out[ad] = deger
    return out


def _canli_risk_modu() -> str:
    """LIVE'da varsayılan risk modu kademeden: pilot kademe → `pilot` (K-115), yoksa `live`."""
    from scryne_quant.execution.canli_kapi import KapiBaglami, kademe_tablosu, pilot_mu

    return "pilot" if pilot_mu(kademe_tablosu(KapiBaglami())) else "live"


@execution_app.command("calistir")
def calistir(
    mod: Annotated[str, typer.Option("--mod", help="paper | shadow | testnet | live")],
    kosu: Annotated[str, typer.Option("--kosu")],
    strateji: Annotated[str, typer.Option("--strateji")] = "sma_kesisim",
    parametre: Annotated[list[str] | None, typer.Option("-p", help="ad=değer")] = None,
    sembol: Annotated[str, typer.Option("--sembol")] = "BTCUSDT",
    timeframe: Annotated[str, typer.Option("--timeframe")] = "1h",
    sermaye: Annotated[float, typer.Option("--sermaye")] = 10_000.0,
    risk_modu: Annotated[str, typer.Option("--risk-modu")] = "",
    bekleme: Annotated[float, typer.Option("--bekleme", help="Döngü aralığı (s)")] = 20.0,
    sure_dk: Annotated[float | None, typer.Option("--sure-dk")] = None,
    tekrar: Annotated[int, typer.Option("--tekrar", help="PAPER: yerel depodan son N bar")] = 0,
    isinma: Annotated[int, typer.Option("--isinma")] = 300,
) -> None:
    """Koşuyu başlatır. Sistem modu tavandır; LIVE yetkisi her başlangıçta yeniden türetilir."""
    from scryne_quant.trader.kurulum import KosuIstegi, KurulumHatasi, kosu_kur

    m = _mod_coz(mod)
    rm = risk_modu or {CalismaModu.LIVE: _canli_risk_modu()}.get(m, "gozlem")
    barlar = None
    if tekrar:
        from scryne_quant.data.depo import ParquetDepo
        from scryne_quant.exchange.akis import df_barlara

        df = ParquetDepo("data/market").oku(sembol, timeframe).tail(tekrar + isinma)
        barlar = df_barlara(df)
    istek = KosuIstegi(
        mod=m, kosu=kosu, strateji=strateji, parametreler=_parametreler(parametre),
        sembol=sembol, timeframe=timeframe, sermaye_usdt=sermaye, risk_modu=rm, kok=KOK,
        tekrar_barlari=barlar,
    )
    try:
        y, kaynak = kosu_kur(istek)
    except (KurulumHatasi, PermissionError) as hata:
        typer.secho(f"koşu kurulamadı: {hata}", fg=typer.colors.RED)
        raise typer.Exit(1) from hata
    typer.secho(f"{m} koşusu '{kosu}' ({strateji}, risk {rm}, sermaye {y.ayar.sermaye_usdt})",
                bold=True)
    if barlar is not None:
        rapor = y.tekrar_oynat(kaynak, isinma=isinma)  # type: ignore[arg-type]
    else:
        rapor = y.calistir(
            bekleme_s=bekleme, azami_sure_s=None if sure_dk is None else sure_dk * 60
        )
    _yaz({k: rapor[k] for k in ("mod", "gecti", "kalan", "sayac", "emir_sayimi", "hesap")})
    raise typer.Exit(0 if rapor["gecti"] else 1)


@execution_app.command("durdur")
def durdur(
    kosu: Annotated[str, typer.Option("--kosu")],
    sebep: Annotated[str, typer.Option("--sebep")] = "planlı durdurma",
) -> None:
    """Planlı durdurma bayrağı; koşu bir sonraki döngüde temiz kapanır (kapanış mutabakatı)."""
    from scryne_quant.live import durdurma

    typer.echo(str(durdurma.dur_iste(KOK / kosu / "kosu", sebep=sebep)))


@execution_app.command("kill")
def kill(
    kosu: Annotated[str, typer.Option("--kosu")],
    sebep: Annotated[str, typer.Option("--sebep")],
    json_cikti: JsonCikti = False,
) -> None:
    """Süreç dışı kill: SAFE_MODE işareti → süreci öldür → açık emirleri iptal et → doğrula.

    Modun adaptörüyle: paper (paper borsa), testnet, live (yalnız-iptal canlı adaptör, emir
    açamaz), shadow (canlı hesap salt okunur: açık emir olmadığı doğrulanır). Rapor
    `runs/execution/<koşu>/kill.json`; canlı host'a karşı başarılı rapor live gate kanıtıdır.
    """
    from scryne_quant.live import kill as kill_mod

    dizin = KOK / kosu
    kimlik_yolu = dizin / "kosu.json"
    if not kimlik_yolu.is_file():
        raise typer.BadParameter(f"koşu yok: {dizin}")
    kimlik = json.loads(kimlik_yolu.read_text(encoding="utf-8"))
    m = CalismaModu(kimlik["mod"])
    sembol = kimlik["sembol"]
    canli_host = m in (CalismaModu.LIVE, CalismaModu.SHADOW)
    # Adaptör kurulamasa da (anahtar okunamadı, kurallar dosyası yok) SAFE_MODE işareti ve
    # süreç sonlandırma **yine yapılır** — kill switch'in en önemli iki adımı borsaya bağlı
    # değil. Açık emirler doğrulanamadıysa rapor başarısız yazılır (K-114 denetimi).
    borsa_hatasi = ""
    try:
        borsa = _kill_adaptoru(m, sembol, dizin)
    except Exception as hata:  # noqa: BLE001 — kill her koşulda ilerlemeli
        borsa, borsa_hatasi = None, f"adaptör kurulamadı: {type(hata).__name__}: {hata}"
    rapor = kill_mod.kill(dizin / "kosu", sebep=sebep, borsa=borsa, semboller=(sembol,))
    if borsa_hatasi:
        rapor.hatalar.append(f"{borsa_hatasi} — açık emirler iptal/doğrulanamadı")
    govde = {
        **rapor.sozluk(),
        "mod": str(m),
        "canli_host": canli_host,
        "basarili": rapor.basarili,
        "zaman_utc": utc_str(simdi_ms()),
    }
    yol = dizin / "kill.json"
    yol.write_text(json.dumps(govde, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    # kill.json'ın hash'i koşunun zincirli audit'ine (live gate kanıtı yalnız buna güvenir).
    _audit_olay(dizin, sembol, "kill", {"kill_sha256": _dosya_sha(yol),
                                        "basarili": rapor.basarili, "sebep": sebep})
    if json_cikti:
        _yaz(govde)
    else:
        typer.secho(f"kill {'BAŞARILI' if rapor.basarili else 'BAŞARISIZ'}: {kosu} ({m})",
                    fg=typer.colors.GREEN if rapor.basarili else typer.colors.RED, bold=True)
    raise typer.Exit(0 if rapor.basarili else 1)


def _dosya_sha(yol: Path) -> str:
    import hashlib

    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _audit_olay(dizin: Path, sembol: str, olay: str, govde: dict[str, Any]) -> None:
    from scryne_quant.risk.audit import Olay, OlayTuru

    defter = SqliteDefter(dizin / "audit.sqlite")
    try:
        defter.yaz(Olay(tur=OlayTuru.EXECUTION, zaman_ms=simdi_ms(), sembol=sembol,
                        govde={"olay": olay, **govde}, durum={}))
    finally:
        defter.kapat()


def _kill_adaptoru(m: CalismaModu, sembol: str, dizin: Path) -> Any:
    if m is CalismaModu.PAPER:
        from scryne_quant.exchange.kurallar import SembolKurallari
        from scryne_quant.exchange.paper_adaptoru import PaperBorsa, PaperMaliyet

        kural = SembolKurallari(**json.loads((dizin / "kurallar.json").read_text("utf-8")))
        return PaperBorsa(kurallar={sembol: kural}, maliyet=PaperMaliyet(0.0, 0.0),
                          saat=simdi_ms, yol=dizin / "paper_borsa.sqlite")
    if m is CalismaModu.TESTNET:
        from scryne_quant.exchange.imzali import BinanceImzaliAdaptoru

        return BinanceImzaliAdaptoru()
    if m is CalismaModu.LIVE:
        from scryne_quant.exchange.canli import canli_iptal_adaptoru

        return canli_iptal_adaptoru()
    if m is CalismaModu.SHADOW:
        from scryne_quant.exchange import canli
        from scryne_quant.exchange.golge import GolgeAdaptoru

        anahtar, sir = canli.okuma_anahtari_oku()
        return GolgeAdaptoru(canli.canli_okuyucu(anahtar, sir))
    raise ValueError(f"{m} koşusu için kill adaptörü yok")


@execution_app.command("safe-kaldir")
def safe_kaldir(
    kosu: Annotated[str, typer.Option("--kosu")],
    not_metni: Annotated[str, typer.Option("--not", help="Gerekçe (≥10 karakter).")],
) -> None:
    """SAFE_MODE işaretini **elle** kaldırır (K-008/4). Risk motorunun SAFE_MODE'u ayrıca kalkar."""
    from scryne_quant.live import kill as kill_mod

    kayit = kill_mod.safe_kaldir(KOK / kosu / "kosu", not_metni)
    if (KOK / kosu / "kosu.json").is_file():
        sembol = json.loads((KOK / kosu / "kosu.json").read_text(encoding="utf-8"))["sembol"]
        _audit_olay(KOK / kosu, sembol, "safe_kaldirildi", {"not": not_metni})
    rp = KOK / kosu / "risk.json"
    if rp.is_file():
        d = json.loads(rp.read_text(encoding="utf-8"))
        if d.get("safe_mode"):
            from scryne_quant.risk.durum import RiskDurumu

            durum_ = RiskDurumu.yukle(d)
            durum_.serbest_birak()
            rp.write_text(json.dumps(durum_.sozluk(), ensure_ascii=False, indent=1), "utf-8")
    _yaz(kayit)


@execution_app.command("kosu-kapat")
def kosu_kapat(
    kosu: Annotated[str, typer.Option("--kosu")],
    not_metni: Annotated[str, typer.Option("--not", help="Gerekçe (≥20 karakter).")],
) -> None:
    """Koşuyu **kalıcı olarak** kapatır (halt/SAFE_MODE'lu tatbikat koşuları dahil).

    Kapatılan koşu bir daha başlatılamaz (`kosu_kur` reddeder) ve live gate'in
    `kritik_hata_yok` kontrolünü tutmaz. Halt/SAFE_MODE **kaldırılmaz**: koşu işlem
    yapamaz hâlde arşive geçer. Gerekçe audit'e yazılır (K-008/4, K-038).
    """
    from scryne_quant.execution.canli_kapi import KAPATILDI

    dizin = KOK / kosu
    if not (dizin / "kosu.json").is_file():
        raise typer.BadParameter(f"koşu yok: {dizin}")
    if len(not_metni.strip()) < 20:
        raise typer.BadParameter("koşu kapatma bir gerekçe ister (≥20 karakter)")
    from scryne_quant.live import kill as kill_mod

    pid = kill_mod.pid_oku(dizin / "kosu")
    if pid is not None and kill_mod.surec_yasiyor_mu(pid):
        raise typer.BadParameter("koşu hâlâ çalışıyor; önce `sq execution durdur` ya da `kill`")
    sembol = json.loads((dizin / "kosu.json").read_text(encoding="utf-8"))["sembol"]
    kayit = {"not": not_metni.strip(), "zaman_utc": utc_str(simdi_ms()),
             "safe_mode": (dizin / "kosu.safemode").is_file()}
    (dizin / KAPATILDI).write_text(json.dumps(kayit, ensure_ascii=False, indent=1), "utf-8")
    _audit_olay(dizin, sembol, "kosu_kapatildi", kayit)
    _yaz(kayit)


@execution_app.command("test-kaydet")
def test_kaydet() -> None:
    """Test takımını koşar ve sonucu HEAD commit'iyle kaydeder (live gate `testler` kontrolü)."""
    git = git_durumu()
    sonuc = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "-q", "--strict-markers", "-m",
         "not network", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        check=False,
    )
    son = [s for s in sonuc.stdout.splitlines() if " passed" in s or " failed" in s]
    ozet = son[-1] if son else sonuc.stdout[-300:]
    import re

    gecen = int(m.group(1)) if (m := re.search(r"(\d+) passed", ozet)) else 0
    kalan = int(m.group(1)) if (m := re.search(r"(\d+) (failed|error)", ozet)) else 0
    if sonuc.returncode != 0 and kalan == 0:
        kalan = 1
    kayit = {"commit": git.get("commit"), "dirty": git.get("dirty"), "gecen": gecen,
             "kalan": kalan, "ozet": ozet, "zaman_utc": utc_str(simdi_ms())}
    KOK.mkdir(parents=True, exist_ok=True)
    (KOK / "testler.json").write_text(json.dumps(kayit, indent=1), encoding="utf-8")
    _yaz(kayit)
    raise typer.Exit(0 if kalan == 0 and not git.get("dirty") else 1)


@execution_app.command("pano")
def pano(
    port: Annotated[int, typer.Option("--port")] = 8790,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
) -> None:
    """Tek ekran operasyon panosu (SYSTEM…AUDIT + CURRENT MODE). Salt okuma."""
    import uvicorn

    from scryne_quant.trader.pano import uygulama

    uvicorn.run(uygulama(Path(".")), host=host, port=port, log_level="warning")


__all__ = ["execution_app"]
