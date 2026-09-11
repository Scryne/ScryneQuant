"""`sq testnet` — Binance Spot Testnet'e karşı execution ölçümleri. (Faz 7)

Faz 7'nin dördüncü bitti kriteri ağ olmadan ölçülemez:

> *"Testnet'te ≥100 emir, elle müdahale gerektiren hata olmadan tamamlanmış."*

`yuk` komutu o ölçümü yapar. Diğer ikisi onu okunur kılar: `durum` bağlantıyı ve saat
sapmasını gösterir, `mutabakat` defterle borsayı karşılaştırır.

**Sinyaller gerçek risk motorundan geçiyor.** Yük koşusu `OnayliNiyet`i elle kurmuyor;
`RiskMotoru.degerlendir` çağırıyor — yani değişmez kural 3 (*"sinyal risk motorunu
atlayamaz"*) bu ölçümde de geçerli. Mod `gozlem` (K-035): promotion kapılarını geçmiş
strateji olmadığı için `paper` modu her sinyali reddederdi ve ölçüm **boş yere** geçerdi;
gözlem modu promotion dışındaki her limiti uygular ama koşunun ürettiği hiçbir kayıt
promotion kanıtı **olamaz**. Faz 6'da aynı sorunun aynı çözümü.

**Emir büyüklüğü risk motorunun onayladığının altında tutuluyor**, üstünde değil.
`--notional` bir tavan: risk motoru ne onaylarsa onaylasın, testnet emri o kadar küçük
gönderilir. Onayın altına inmek her zaman güvenli; üstüne çıkmak onaylanmamış risktir
(K-007'nin yuvarlama yönüyle aynı mantık).

**Bu koşu canlı borsaya çıkamaz.** `exchange/imzali.py` canlı host sabitini bilerek
tanımlamıyor ve bu komut yalnızca testnet adaptörünü kuruyor. Faz 8'in geçişi bir karar
olarak yazılacak, bir bayrak olarak değil.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, Any

import requests
import typer

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.exchange.emir_adaptoru import Varlik
from scryne_quant.exchange.hatalar import BorsaHatasi
from scryne_quant.exchange.imzali import BinanceImzaliAdaptoru
from scryne_quant.execution.motor import EmirMotoru, IptalSonucu, SaatEngeli
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.oms.emir import EmirDurumu
from scryne_quant.oms.mutabakat import Uyusmazlik, mutabakat
from scryne_quant.oms.pozisyon import (
    CipaYok,
    PozisyonUyusmazligi,
    cipa_at,
    pozisyon_mutabakati,
)
from scryne_quant.risk import limitler as limitler_mod
from scryne_quant.risk.motor import PiyasaOlcumu, RiskMotoru
from scryne_quant.risk.niyet import OnayliNiyet
from scryne_quant.strategy.sinyal import Sinyal, Yon

testnet_app = typer.Typer(
    name="testnet",
    help="Binance Spot Testnet: bağlantı, yük koşusu, mutabakat. (Faz 7)",
)

#: Koşu dosyalarının yeri. `.gitignore`'daki `runs/` altında.
VARSAYILAN_KOK = Path("runs/testnet")

#: Emir başına gönderilecek azami notional (USDT). minNotional 5,00 olduğu için 10 USDT
#: hem sınırın güvenli üstünde hem de testnet defterini kımıldatmayacak kadar küçük.
VARSAYILAN_NOTIONAL = 10.0

#: Emirler arası bekleme. Testnet'in emir hız sınırı ~50/10 s; 0,25 s onun beşte biri.
VARSAYILAN_BEKLEME_S = 0.25

#: Bu kadar emirde bir mutabakat çalışır. Koşunun sonunda bir kez daha çalışır.
VARSAYILAN_MUTABAKAT_HER = 25

JsonCikti = Annotated[bool, typer.Option("--json", help="Çıktıyı JSON olarak ver.")]


def _yaz(nesne: Any) -> None:
    typer.echo(json.dumps(nesne, ensure_ascii=False, indent=2, sort_keys=True))


def _adaptor() -> BinanceImzaliAdaptoru:
    try:
        return BinanceImzaliAdaptoru()
    except BorsaHatasi as hata:
        raise typer.BadParameter(str(hata)) from hata


# --------------------------------------------------------------------- durum


@testnet_app.command("durum")
def testnet_durum(json_cikti: JsonCikti = False) -> None:
    """Bağlantı, saat sapması, sembol kuralları ve bakiye. Hiçbir şey göndermez.

    Saat sapması burada **bilerek** görünür: Faz 7'nin ön koşullarından biri clock-drift
    kontrolünün çalışıyor olması, ve bu sayının bir yerde okunabilir olması o kontrolün
    tek gözlemlenebilir hâli.
    """
    a = _adaptor()
    kural = a.sembol_kurallari("BTCUSDT")
    bakiye = a.bakiye()
    govde = {
        "sunucu_zamani_ms": a.sunucu_zamani_ms(),
        "sunucu_zamani_utc": utc_str(a.sunucu_zamani_ms()),
        "yerel_sapma_ms": a.saat_sapmasi_ms(),
        "son_fiyat": a.son_fiyat("BTCUSDT"),
        "sembol_kurallari": {
            "sembol": kural.sembol,
            "tick_size": kural.tick_size,
            "step_size": kural.step_size,
            "min_notional": kural.min_notional,
            "durum": kural.durum,
        },
        # Testnet hesabı yüzlerce varlıkla geliyor; tamamını basmak çıktıyı okunamaz
        # yapıyor. İşlem çifti ayrıca veriliyor, geri kalanı yalnızca sayılıyor.
        "bakiye": {k: bakiye[k].sozluk() for k in ("BTC", "USDT") if k in bakiye},
        "diger_varlik_sayisi": len([k for k in bakiye if k not in ("BTC", "USDT")]),
        "acik_emir": len(a.acik_emirler("BTCUSDT")),
    }
    if json_cikti:
        _yaz(govde)
        return

    typer.echo(f"sunucu    : {govde['sunucu_zamani_utc']}")
    sapma = govde["yerel_sapma_ms"]
    renk = typer.colors.GREEN if abs(sapma) < 1_000 else typer.colors.YELLOW
    typer.secho(
        f"saat farkı: {sapma} ms (yerel − borsa) — imza sunucu saatinden türüyor",
        fg=renk,
    )
    typer.echo(
        f"kurallar  : tick {kural.tick_size} · step {kural.step_size} · "
        f"minNotional {kural.min_notional} · {kural.durum}"
    )
    typer.echo(f"fiyat     : {govde['son_fiyat']:.2f}")
    typer.echo(
        "bakiye    : "
        + " · ".join(
            f"{v['toplam']:.8g} {k} (kilitli {v['kilitli']:.8g})"
            for k, v in sorted(govde["bakiye"].items())
        )
        + f"  (+{govde['diger_varlik_sayisi']} başka varlık)"
    )
    typer.echo(f"açık emir : {govde['acik_emir']}")


# ----------------------------------------------------------------- mutabakat


@testnet_app.command("mutabakat")
def testnet_mutabakat(
    kosu_adi: Annotated[str, typer.Argument(help="Yük koşusunun adı.")],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    duzelt: Annotated[
        bool,
        typer.Option(
            "--duzelt/--sadece-rapor",
            help="Çözülebilir farkları deftere yaz. Rapor modunda defter değişmez.",
        ),
    ] = False,
    json_cikti: JsonCikti = False,
) -> None:
    """Defterin açık emirlerini borsayla karşılaştırır (§25).

    Varsayılan **rapor modu**: uyuşmazlığı gösterir, koşuyu durdurmaz, defteri değiştirmez.
    `--duzelt` çözülebilir farkları yazar — ve çözülemeyen bir fark varsa yine durur.
    """
    yol = kok / f"{kosu_adi}.sqlite"
    if not yol.exists():
        raise typer.BadParameter(f"koşu bulunamadı: {yol}")

    a = _adaptor()
    with EmirDefteri(yol) as defter:
        if not duzelt:
            # Rapor modunda deftere yazılmamalı; `mutabakat` çözebildiğini yazar, o
            # yüzden yazma yolu kapatılıyor. Bunu bir bayrakla değil, nesneyi sararak
            # yapmak daha dürüst: "yazmadım" iddiası koda bakarak doğrulanabilir olmalı.
            sonuc = mutabakat(_YazmayanDefter(defter), a, "BTCUSDT", durdur=False)
        else:
            sonuc = mutabakat(defter, a, "BTCUSDT", durdur=False)

    if json_cikti:
        _yaz(sonuc.sozluk())
    else:
        typer.secho(
            sonuc.ozet(), fg=typer.colors.RED if sonuc.halt else typer.colors.GREEN
        )
    if sonuc.halt:
        raise typer.Exit(code=1)


class _YazmayanDefter:
    """Okuma geçirgen, yazma sessizce yok sayılır. Yalnızca `--sadece-rapor` için.

    `mutabakat` çözebildiği farkları yazmak üzere tasarlandı; raporlama sırasında bu
    istenmiyor. Alternatif, `mutabakat`a bir `yaz=False` bayrağı eklemekti — ama o bayrak
    emir yolunda da bulunabilir hâle gelirdi ve "mutabakat yaptım ama yazmadım" diye bir
    durumun üretim kodunda karşılığı yok.
    """

    __slots__ = ("_defter",)

    def __init__(self, defter: EmirDefteri) -> None:
        self._defter = defter

    def acik_emirler(self):
        return self._defter.acik_emirler()

    def al(self, istemci_kimligi: str):
        return self._defter.al(istemci_kimligi)

    def tumu(self, *, limit: int | None = None):
        return self._defter.tumu(limit=limit)

    def acilis_oku(self):
        return self._defter.acilis_oku()

    def gecir(self, *_: Any, **__: Any):
        return None

    def komisyon_yaz(self, istemci_kimligi: str, *_: Any, **__: Any):
        # Rapor modunda öğrenilen komisyon **yazılmıyor**, ve bunun bir bedeli var:
        # eksik komisyon eksik kalır, yani rapor "hesaplanamadı" der. Bu doğru olan:
        # `--sadece-rapor` defteri değiştirmeyeceğini söylüyor ve komisyon yazmak onu
        # değiştirmek olurdu. Düzeltmek isteyen `--duzelt` ile çağırır.
        return self._defter.al(istemci_kimligi)


# ------------------------------------------------------------------- pozisyon


@testnet_app.command("pozisyon")
def testnet_pozisyon(
    kosu_adi: Annotated[str, typer.Argument(help="Koşu adı.")],
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    duzelt: Annotated[
        bool,
        typer.Option(
            "--duzelt/--sadece-rapor",
            help="Borsadan öğrenilen komisyonu deftere yaz. Rapor modunda defter değişmez.",
        ),
    ] = False,
    json_cikti: JsonCikti = False,
) -> None:
    """Çıpa + defter akışını borsanın bakiyesiyle karşılaştırır. (Faz 8 kriteri)

    `mutabakat` komutundan **farklı bir soru** soruyor. O, defterdeki emirlerin borsada
    hangi durumda olduğuna bakar; bu, hesabın defterin söylediği yerde olup olmadığına.
    Bütün emirleri doğru bilen bir defter bile dışarıdan gelen bir yatırmayı, elle
    yapılmış bir işlemi ya da başka bir sürecin emrini göremez — ve para o yollardan da
    hareket eder.

    Çıkış kodu 1: açıklanamayan fark var ya da komisyon eksikliği yüzünden hesap
    yapılamadı. İkisi ayrı satırlarda raporlanıyor; biri bir bulgu, diğeri bir
    ölçülemezlik.
    """
    yol = kok / f"{kosu_adi}.sqlite"
    if not yol.exists():
        raise typer.BadParameter(f"koşu bulunamadı: {yol}")

    a = _adaptor()
    with EmirDefteri(yol) as defter:
        hedef = defter if duzelt else _YazmayanDefter(defter)
        try:
            sonuc = pozisyon_mutabakati(hedef, a, "BTCUSDT", durdur=False)
        except CipaYok as hata:
            typer.secho(str(hata), fg=typer.colors.RED)
            raise typer.Exit(code=1) from hata

    if json_cikti:
        _yaz(sonuc.sozluk())
    else:
        for fark in sonuc.farklar:
            typer.echo(
                f"{fark.varlik:<6}: çıpa {fark.acilis:.8f} + defter {fark.akis:+.8f} "
                f"= {fark.beklenen:.8f} · borsa {fark.gercek:.8f} · "
                f"fark {fark.fark:+.10f}"
            )
        typer.secho(
            sonuc.ozet(), fg=typer.colors.RED if sonuc.halt else typer.colors.GREEN
        )
    if sonuc.halt:
        raise typer.Exit(code=1)


# ------------------------------------------------------------------- kesinti


class _YanitiYutanTransport:
    """İsteği **gerçekten gönderir**, sonra yanıtı yutup `ReadTimeout` fırlatır.

    Faz 7'nin ikinci kriteri *"süreç emir gönderiminin ortasında öldürüldüğünde"* diyor.
    O anın borsadan görünüşü tam olarak budur: emir oluştu, ama çağıran sonucu hiç
    öğrenmedi. Süreci gerçekten `kill` etmek daha az sadık bir taklit olurdu — ölen süreç
    yeniden başlayıp *aynı* testi kuramaz, ve ölçmek istediğimiz şey işletim sisteminin
    sinyal davranışı değil, kaybolan yanıtın bıraktığı iz.

    `gonderildi_mi=False` ile ters vaka kurulur: istek hiç yapılmaz ama çağıran yine
    `ReadTimeout` görür — yani "belirsiz" ama borsada emir **yok**.
    """

    __slots__ = ("_gercek", "_gonderildi_mi", "yutulan")

    def __init__(self, gercek: Any, *, gonderildi_mi: bool = True) -> None:
        self._gercek = gercek
        self._gonderildi_mi = gonderildi_mi
        self.yutulan = 0

    def request(self, method: str, url: str, **kw: Any) -> Any:
        if method != "POST" or "/api/v3/order" not in url:
            return self._gercek.request(method, url, **kw)
        self.yutulan += 1
        if self._gonderildi_mi:
            self._gercek.request(method, url, **kw)
        raise requests.exceptions.ReadTimeout("yanıt yutuldu (kesinti testi)")


@testnet_app.command("kesinti")
def testnet_kesinti(
    kosu_adi: Annotated[str, typer.Argument(help="Koşu adı.")],
    notional: Annotated[float, typer.Option("--notional")] = VARSAYILAN_NOTIONAL,
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    risk_yolu: Annotated[Path, typer.Option("--risk")] = limitler_mod.VARSAYILAN_YOL,
) -> None:
    """Gönderim ortasında kesinti + mutabakat. Gerçek testnet'e karşı. (Faz 7 kriteri 2)

    İki vaka ölçülür ve ikisi de çağıran açısından **ayırt edilemez** — tek fark borsada
    ne olduğu:

    | Vaka | Borsada emir | Defter (kesintiden sonra) | Mutabakattan sonra |
    | --- | --- | --- | --- |
    | Yanıt kayboldu, emir oluştu | var | `UNKNOWN` | `FILLED` |
    | Yanıt kayboldu, emir oluşmadı | yok | `UNKNOWN` | `FAILED` |

    Aynı belirsizlikten iki farklı doğru sonuca varılması, mutabakatın tahmin
    yürütmediğinin kanıtı: cevabı borsadan alıyor, varsayımdan değil.
    """
    kok.mkdir(parents=True, exist_ok=True)
    limitler = limitler_mod.yukle(risk_yolu)
    sonuclar: list[dict[str, Any]] = []

    for etiket, gonderildi_mi, beklenen in (
        ("emir_olustu", True, EmirDurumu.FILLED),
        ("emir_olusmadi", False, EmirDurumu.FAILED),
    ):
        yol = kok / f"{kosu_adi}-{etiket}.sqlite"
        if yol.exists():
            raise typer.BadParameter(f"bu koşu zaten var: {yol}. Yeni bir ad seç.")

        saglam = _adaptor()
        fiyat = saglam.son_fiyat("BTCUSDT")
        ozkaynak = notional * 1000.0
        risk = RiskMotoru(limitler, "1h", mod="gozlem")

        kesintili = _kesintili_adaptor(gonderildi_mi=gonderildi_mi)

        bar_ms = saglam.sunucu_zamani_ms()
        risk.bar_isle(bar_ms, ozkaynak)
        karar = risk.degerlendir(
            Sinyal(
                symbol="BTCUSDT",
                side=Yon.BUY,
                target_exposure=notional / ozkaynak,
                confidence=1.0,
                reason=f"FAZ7_KESINTI_{etiket.upper()}",
                timestamp=bar_ms,
            ),
            PiyasaOlcumu(
                fiyat=fiyat,
                ozkaynak=ozkaynak,
                mevcut_maruziyet=0.0,
                bar_ms=bar_ms,
                atr=fiyat * 0.01,
            ),
        )
        if not isinstance(karar, OnayliNiyet):
            raise typer.BadParameter(f"risk motoru reddetti: {karar.sebep}")

        with EmirDefteri(yol) as defter:
            cipa_at(defter, saglam, not_metni=f"kesinti testi {etiket}")
            sonuc = EmirMotoru(defter, kesintili).gonder(karar, notional / fiyat)
            kesinti_durumu = sonuc.emir.durum

        # Süreç öldü: defter kapandı. Yeni bir nesne diskteki durumdan kuruluyor.
        with EmirDefteri(yol) as yeniden:
            mut = mutabakat(yeniden, saglam, "BTCUSDT", durdur=False)
            son = yeniden.al(sonuc.emir.istemci_kimligi)

        sonuclar.append(
            {
                "vaka": etiket,
                "kesinti_sonrasi": str(kesinti_durumu),
                "mutabakat_sonrasi": str(son.durum) if son else None,
                "beklenen": str(beklenen),
                "gecti": kesinti_durumu is EmirDurumu.UNKNOWN
                and son is not None
                and son.durum is beklenen
                and not mut.halt,
                "mutabakat": mut.sozluk(),
            }
        )
        renk = typer.colors.GREEN if sonuclar[-1]["gecti"] else typer.colors.RED
        typer.secho(
            f"{etiket:14s} kesinti→{kesinti_durumu}  mutabakat→"
            f"{son.durum if son else '?'}  (beklenen {beklenen})",
            fg=renk,
        )

    rapor_yolu = kok / f"{kosu_adi}.json"
    rapor_yolu.write_text(
        json.dumps(
            {"sonuclar": sonuclar, "utc": utc_str(simdi_ms())},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    typer.echo(f"rapor: {rapor_yolu}")
    if not all(s["gecti"] for s in sonuclar):
        raise typer.Exit(code=1)


def _kesintili_adaptor(*, gonderildi_mi: bool) -> BinanceImzaliAdaptoru:
    """Yanıtı yutan transport'la sarılmış gerçek adaptör."""
    taban = _adaptor()
    taban._oturum = _YanitiYutanTransport(  # noqa: SLF001 — kesinti testinin tek yolu
        taban._oturum, gonderildi_mi=gonderildi_mi
    )
    return taban


# ----------------------------------------------------------------------- yük


@testnet_app.command("yuk")
def testnet_yuk(
    kosu_adi: Annotated[str, typer.Argument(help="Koşu adı; defter dosyasının adı olur.")],
    emir_sayisi: Annotated[
        int, typer.Option("--emir", help="Gönderilecek emir sayısı (kriter: ≥100).")
    ] = 100,
    notional: Annotated[
        float, typer.Option("--notional", help="Emir başına azami USDT değeri.")
    ] = VARSAYILAN_NOTIONAL,
    bekleme_s: Annotated[
        float, typer.Option("--bekleme", help="Emirler arası bekleme (saniye).")
    ] = VARSAYILAN_BEKLEME_S,
    mutabakat_her: Annotated[
        int, typer.Option("--mutabakat-her", help="Kaç emirde bir mutabakat çalışsın.")
    ] = VARSAYILAN_MUTABAKAT_HER,
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    risk_yolu: Annotated[Path, typer.Option("--risk")] = limitler_mod.VARSAYILAN_YOL,
) -> None:
    """Testnet'e `--emir` adet market emri gönderir ve sonucu raporlar. (Faz 7 kriteri 3)

    Emirler BUY/SELL olarak **dönüşümlü**: net pozisyon sıfıra yakın kalır, yani ölçüm
    testnet bakiyesini tüketmez. Her `--mutabakat-her` emirde bir mutabakat çalışır;
    uyuşmazlık çıkarsa koşu **durur** — kriterin kendisi bunu istiyor.

    Koşu, aynı niyeti bilerek ikinci kez göndererek duplicate korumasını da ölçer: o
    denemede borsaya hiç istek gitmemeli.

    Rapor `<kok>/<kosu_adi>.json` dosyasına yazılır; Faz 7 raporunun sayıları oradan
    alınır, tahmin edilmez.
    """
    if emir_sayisi < 1:
        raise typer.BadParameter("--emir en az 1 olmalı")

    kok.mkdir(parents=True, exist_ok=True)
    defter_yolu = kok / f"{kosu_adi}.sqlite"
    if defter_yolu.exists():
        raise typer.BadParameter(
            f"bu koşu zaten var: {defter_yolu}. Emir defteri append-only; var olan bir "
            f"koşunun üzerine yazmak kaydı bozar. Yeni bir ad seç."
        )

    a = _adaptor()
    kural = a.sembol_kurallari("BTCUSDT")
    if not kural.islenebilir:
        raise typer.BadParameter(f"BTCUSDT işleme kapalı: {kural.durum}")

    fiyat = a.son_fiyat("BTCUSDT")
    bakiye = a.bakiye()
    # Özkaynak **toplam** bakiyeden: kilitli para da hesabın parası. Yalnızca serbeste
    # bakmak, açık bir emir varken özkaynağı olduğundan küçük gösterir ve risk motoruna
    # yanlış bir taban verir.
    ozkaynak = (
        bakiye.get("USDT", Varlik()).toplam + bakiye.get("BTC", Varlik()).toplam * fiyat
    )
    if notional < kural.min_notional:
        raise typer.BadParameter(
            f"--notional {notional} minNotional {kural.min_notional} altında; "
            f"her emir borsadan önce yerel kuralda reddedilirdi"
        )

    limitler = limitler_mod.yukle(risk_yolu)
    risk = RiskMotoru(limitler, "1h", mod="gozlem")

    typer.secho(
        f"yük koşusu: {kosu_adi} · {emir_sayisi} emir · ≤{notional:.2f} USDT/emir\n"
        f"saat farkı: {a.saat_sapmasi_ms()} ms · fiyat {fiyat:.2f} · "
        f"özkaynak {ozkaynak:.2f} USDT\n"
        f"UYARI: gözlem modu — bu koşu promotion kanıtı üretmez (K-035)",
        fg=typer.colors.YELLOW,
    )

    with EmirDefteri(defter_yolu) as defter:
        # Çıpa **ilk emirden önce**: pozisyon mutabakatının bizim tarafımızdaki tek
        # bağımsız kaydı bu. Koşu bittikten sonra atılan bir çıpa, ölçülecek farkı
        # tanımı gereği sıfırlar (`oms/pozisyon.py`).
        cipa_at(defter, a, not_metni=f"testnet yuk kosusu {kosu_adi}")
        rapor = _kosu(
            defter=defter,
            adaptor=a,
            risk=risk,
            emir_sayisi=emir_sayisi,
            notional=notional,
            bekleme_s=bekleme_s,
            mutabakat_her=mutabakat_her,
            ozkaynak=ozkaynak,
            kosu_adi=kosu_adi,
        )

    rapor_yolu = kok / f"{kosu_adi}.json"
    rapor_yolu.write_text(
        json.dumps(rapor, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    _rapor_yaz(rapor, rapor_yolu)
    if not rapor["kriter_saglandi"]:
        raise typer.Exit(code=1)


def _kosu(
    *,
    defter: EmirDefteri,
    adaptor: BinanceImzaliAdaptoru,
    risk: RiskMotoru,
    emir_sayisi: int,
    notional: float,
    bekleme_s: float,
    mutabakat_her: int,
    ozkaynak: float,
    kosu_adi: str,
) -> dict[str, Any]:
    baslangic_ms = simdi_ms()
    reddedilen_sinyal: list[dict[str, Any]] = []
    belirsiz: list[str] = []
    mutabakatlar: list[dict[str, Any]] = []
    hatalar: list[dict[str, Any]] = []
    ilk_niyet: OnayliNiyet | None = None
    duplicate_denendi = False
    duplicate_engellendi = False
    maruziyet = 0.0

    son_alim = 0.0
    for i in range(emir_sayisi):
        # Çıkış bacağı `FLAT`, `SELL` değil: `Sinyal` tam çıkışı FLAT ile ifade etmeyi
        # zorunlu tutuyor (hedef maruziyet 0 olan bir SELL doğrulamada reddediliyor).
        yon = Yon.BUY if i % 2 == 0 else Yon.FLAT
        fiyat = adaptor.son_fiyat("BTCUSDT")
        bar_ms = adaptor.sunucu_zamani_ms()
        risk.bar_isle(bar_ms, ozkaynak)

        hedef = notional / ozkaynak if yon is Yon.BUY else 0.0
        sinyal = Sinyal(
            symbol="BTCUSDT",
            side=yon,
            target_exposure=hedef,
            confidence=1.0,
            reason=f"FAZ7_YUK_{i:03d}",
            timestamp=bar_ms,
        )
        karar = risk.degerlendir(
            sinyal,
            PiyasaOlcumu(
                fiyat=fiyat,
                ozkaynak=ozkaynak,
                mevcut_maruziyet=maruziyet,
                bar_ms=bar_ms,
                atr=fiyat * 0.01,
            ),
        )
        if not isinstance(karar, OnayliNiyet):
            reddedilen_sinyal.append({"sira": i, "sebep": str(karar.sebep)})
            continue

        if yon is Yon.BUY:
            # Risk motorunun onayladığının **altı**: tavan her zaman `--notional`.
            miktar = min(notional, karar.onayli_maruziyet * ozkaynak) / fiyat
        else:
            # Çıkış bacağı, girişin **gerçekten dolan** miktarını satar. `notional/fiyat`
            # demek, alınandan farklı bir miktar satmak ve net pozisyonu her turda biraz
            # kaydırmak olurdu — 100 emirde bu sapma birikir ve ölçümü kirletir.
            miktar = son_alim
            if miktar <= 0.0:
                reddedilen_sinyal.append({"sira": i, "sebep": "satilacak_pozisyon_yok"})
                continue

        try:
            sonuc = EmirMotoru(defter, adaptor).gonder(karar, miktar)
        except SaatEngeli as hata:
            hatalar.append({"sira": i, "tur": "SaatEngeli", "mesaj": str(hata)})
            break
        except BorsaHatasi as hata:
            hatalar.append({"sira": i, "tur": type(hata).__name__, "mesaj": str(hata)})
            continue

        if ilk_niyet is None:
            ilk_niyet = karar
        if sonuc.belirsiz:
            belirsiz.append(sonuc.emir.istemci_kimligi)
        if sonuc.emir.durum is EmirDurumu.FILLED:
            if yon is Yon.BUY:
                son_alim = sonuc.emir.dolan_miktar
                maruziyet = karar.onayli_maruziyet
            else:
                son_alim = 0.0
                maruziyet = 0.0

        typer.echo(
            f"  {i + 1:>4}/{emir_sayisi}  {yon.value:<4} "
            f"{sonuc.emir.miktar:.5f}  {sonuc.emir.durum}"
        )

        if mutabakat_her > 0 and (i + 1) % mutabakat_her == 0:
            mutabakatlar.append(_mutabakat_adimi(defter, adaptor, i + 1, hatalar))
            if hatalar and hatalar[-1].get("tur") == "Uyusmazlik":
                break
        if bekleme_s > 0:
            time.sleep(bekleme_s)

    # Duplicate ölçümü: aynı niyet ikinci kez. Borsaya istek **gitmemeli**.
    if ilk_niyet is not None:
        duplicate_denendi = True
        tekrar = EmirMotoru(defter, adaptor).gonder(ilk_niyet, notional / fiyat)
        duplicate_engellendi = not tekrar.gonderildi

    mutabakatlar.append(_mutabakat_adimi(defter, adaptor, emir_sayisi, hatalar, son=True))
    pozisyon = _pozisyon_adimi(defter, adaptor, hatalar)

    sayim = defter.sayim()
    gonderilen = sum(
        n for d, n in sayim.items() if d not in (str(EmirDurumu.CREATED),)
    )
    uyusmazlik_var = any(
        h.get("tur") in ("Uyusmazlik", "PozisyonUyusmazligi") for h in hatalar
    )
    return {
        "kosu_adi": kosu_adi,
        "baslangic_ms": baslangic_ms,
        "baslangic_utc": utc_str(baslangic_ms),
        "bitis_utc": utc_str(simdi_ms()),
        "hedef_emir": emir_sayisi,
        "defter_sayimi": sayim,
        "gonderilen": gonderilen,
        "belirsiz_kalan": belirsiz,
        "reddedilen_sinyal": reddedilen_sinyal,
        "hatalar": hatalar,
        "mutabakatlar": mutabakatlar,
        "pozisyon_mutabakati": pozisyon,
        "duplicate_denendi": duplicate_denendi,
        "duplicate_engellendi": duplicate_engellendi,
        "saat_sapmasi_ms": adaptor.saat_sapmasi_ms(),
        "risk_red_sayimi": {k: v for k, v in risk.red_sayimi.items() if v},
        "kriter_saglandi": (
            sayim.get(str(EmirDurumu.FILLED), 0) >= emir_sayisi
            and not uyusmazlik_var
            and not belirsiz
            and not hatalar
            and duplicate_engellendi
            # Pozisyon mutabakatı kriterin **parçası**, ekli bir rapor değil: 100 emri
            # hatasız göndermek, hesabın o 100 emrin söylediği yerde olduğunu
            # göstermez. Faz 8'in "açıklanamayan pozisyon farkı: sıfır" kriteri burada
            # ilk kez ölçülüyor.
            and not pozisyon.get("halt", True)
        ),
        "not": (
            "Gözlem modu (K-035): bu koşunun hiçbir kaydı promotion kanıtı değildir. "
            "Ölçülen şey emir yolunun dayanıklılığı, stratejinin başarısı değil."
        ),
    }


def _mutabakat_adimi(
    defter: EmirDefteri,
    adaptor: BinanceImzaliAdaptoru,
    sira: int,
    hatalar: list[dict[str, Any]],
    *,
    son: bool = False,
) -> dict[str, Any]:
    try:
        sonuc = mutabakat(defter, adaptor, "BTCUSDT")
    except Uyusmazlik as hata:
        hatalar.append({"sira": sira, "tur": "Uyusmazlik", "mesaj": str(hata)})
        typer.secho(hata.sonuc.ozet(), fg=typer.colors.RED)
        return {"sira": sira, "son": son, **hata.sonuc.sozluk()}
    return {"sira": sira, "son": son, **sonuc.sozluk()}


def _pozisyon_adimi(
    defter: EmirDefteri,
    adaptor: BinanceImzaliAdaptoru,
    hatalar: list[dict[str, Any]],
) -> dict[str, Any]:
    """Koşu sonunda çıpa + defter akışını borsanın bakiyesiyle karşılaştırır.

    Emir mutabakatı *"defterdeki emirler borsada ne durumda"* sorusunu cevaplıyor; bu
    ondan bağımsız bir soru soruyor: *"hesap, defterin söylediği yerde mi"*. İkisi ayrı
    çünkü bütün emirleri doğru bilen bir defter bile, dışarıdan gelen bir yatırma ya da
    elle yapılmış bir işlemi göremez.
    """
    try:
        return pozisyon_mutabakati(defter, adaptor, "BTCUSDT").sozluk()
    except PozisyonUyusmazligi as hata:
        hatalar.append({"tur": "PozisyonUyusmazligi", "mesaj": str(hata)})
        typer.secho(hata.sonuc.ozet(), fg=typer.colors.RED)
        return hata.sonuc.sozluk()
    except CipaYok as hata:
        hatalar.append({"tur": "CipaYok", "mesaj": str(hata)})
        typer.secho(str(hata), fg=typer.colors.RED)
        return {"halt": True, "cipa_yok": True}


def _rapor_yaz(rapor: dict[str, Any], yol: Path) -> None:
    typer.echo("")
    typer.echo(f"rapor        : {yol}")
    typer.echo(f"defter sayımı: {rapor['defter_sayimi']}")
    typer.echo(
        f"duplicate    : "
        f"{'engellendi ✓' if rapor['duplicate_engellendi'] else 'ENGELLENEMEDİ ✗'}"
    )
    typer.echo(f"belirsiz     : {len(rapor['belirsiz_kalan'])}")
    pozisyon = rapor.get("pozisyon_mutabakati") or {}
    typer.secho(
        "pozisyon     : "
        + (
            "AÇIKLANAMAYAN FARK ✗"
            if pozisyon.get("halt", True)
            else "çıpa + defter = borsa ✓"
        ),
        fg=typer.colors.RED if pozisyon.get("halt", True) else typer.colors.GREEN,
    )
    typer.echo(f"hata         : {len(rapor['hatalar'])}")
    typer.echo(f"saat sapması : {rapor['saat_sapmasi_ms']} ms")
    if rapor["kriter_saglandi"]:
        typer.secho(
            f"KRİTER SAĞLANDI: {rapor['hedef_emir']} emir, elle müdahale gerektiren "
            f"hata yok.",
            fg=typer.colors.GREEN,
        )
    else:
        typer.secho(
            "KRİTER SAĞLANMADI — rapordaki `hatalar` ve `belirsiz_kalan` alanlarına bak. "
            "Eşik gevşetilmez; sebep giderilir ve koşu tekrarlanır.",
            fg=typer.colors.RED,
        )


__all__ = ["testnet_app"]


# ---------------------------------------------------------------------- limit

#: Limit emrinin piyasadan ne kadar uzağa konacağı. %20 aşağısı, dakikalar süren bir
#: ölçümde dolma ihtimalini pratikte sıfırlar — ama emri **gerçek** bir açık emir olarak
#: bırakır. Dolmayan bir emirle çalışmak bir hile değil, iptal yolunun ön koşulu: dolmuş
#: bir emir iptal edilemez.
UZAKLIK_ORANI = 0.80


@testnet_app.command("limit")
def testnet_limit(
    kosu_adi: Annotated[str, typer.Argument(help="Koşu adı; defter dosyasının adı olur.")],
    notional: Annotated[float, typer.Option("--notional")] = VARSAYILAN_NOTIONAL,
    kok: Annotated[Path, typer.Option("--kok")] = VARSAYILAN_KOK,
    risk_yolu: Annotated[Path, typer.Option("--risk")] = limitler_mod.VARSAYILAN_YOL,
) -> None:
    """Limit emri ve iptal yolunu gerçek testnet'e karşı ölçer. (K-047)

    Faz 7 bu yolu açık bırakmıştı: *"`CANCELED` yolu state machine'de tanımlı ama gerçek
    borsaya karşı hiç yürütülmedi."* Tanımlı ama yürütülmemiş bir yol, **çalıştığı
    sanılan** bir yoldur.

    Dört vaka ölçülüyor ve dördü de ancak gerçek borsaya karşı anlamlı:

    | Vaka | Ölçülen |
    | --- | --- |
    | `acik_limit` | Dolmayan emir açık kalıyor ve **para kilitleniyor** |
    | `iptal` | İptal onaylanıyor, kilit çözülüyor, emir açık listeden çıkıyor |
    | `marketable` | Piyasanın üstündeki limit hemen doluyor |
    | `nihai_iptal` | Dolmuş emrin iptali "emir yok" alıyor, defter bozulmuyor |

    Sonunda pozisyon mutabakatı koşuyor: limit yolunun bakiyeyi `serbest`/`kilitli`
    arasında gezdirmesi, `toplam` üzerinden yapılan mutabakatı bozmamalı.
    """
    kok.mkdir(parents=True, exist_ok=True)
    defter_yolu = kok / f"{kosu_adi}.sqlite"
    if defter_yolu.exists():
        raise typer.BadParameter(
            f"bu koşu zaten var: {defter_yolu}. Emir defteri append-only; yeni bir ad seç."
        )

    a = _adaptor()
    kural = a.sembol_kurallari("BTCUSDT")
    if not kural.islenebilir:
        raise typer.BadParameter(f"BTCUSDT işleme kapalı: {kural.durum}")
    if notional < kural.min_notional:
        raise typer.BadParameter(
            f"--notional {notional} minNotional {kural.min_notional} altında"
        )

    fiyat = a.son_fiyat("BTCUSDT")
    bakiye = a.bakiye()
    ozkaynak = (
        bakiye.get("USDT", Varlik()).toplam + bakiye.get("BTC", Varlik()).toplam * fiyat
    )
    risk = RiskMotoru(limitler_mod.yukle(risk_yolu), "1h", mod="gozlem")

    typer.secho(
        f"limit koşusu: {kosu_adi} · fiyat {fiyat:.2f} · ≤{notional:.2f} USDT/emir\n"
        f"UYARI: gözlem modu — bu koşu promotion kanıtı üretmez (K-035)",
        fg=typer.colors.YELLOW,
    )

    with EmirDefteri(defter_yolu) as defter:
        cipa_at(defter, a, not_metni=f"limit/iptal olcumu {kosu_adi}")
        rapor = _limit_kosusu(
            defter=defter,
            adaptor=a,
            risk=risk,
            fiyat=fiyat,
            ozkaynak=ozkaynak,
            notional=notional,
            kosu_adi=kosu_adi,
        )

    rapor_yolu = kok / f"{kosu_adi}.json"
    rapor_yolu.write_text(
        json.dumps(rapor, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    typer.echo(f"\nrapor: {rapor_yolu}")
    if not rapor["kriter_saglandi"]:
        raise typer.Exit(code=1)


def _limit_kosusu(
    *,
    defter: EmirDefteri,
    adaptor: BinanceImzaliAdaptoru,
    risk: RiskMotoru,
    fiyat: float,
    ozkaynak: float,
    notional: float,
    kosu_adi: str,
) -> dict[str, Any]:
    motor = EmirMotoru(defter, adaptor)
    miktar = notional / fiyat
    vakalar: list[dict[str, Any]] = []

    # --- vaka 1: dolmayan limit açık kalıyor, para kilitleniyor -------------
    uzak = fiyat * UZAKLIK_ORANI
    # Uzak limitte notional düşeceği için miktar büyütülüyor: minNotional limit
    # fiyatından hesaplanır, piyasa fiyatından değil.
    acik = _emir_gonder(motor, risk, adaptor, ozkaynak, notional / uzak, uzak, "ACIK")
    onceki_kilit = adaptor.bakiye().get("USDT", Varlik()).kilitli
    vakalar.append(
        {
            "vaka": "acik_limit",
            "durum": str(acik.emir.durum),
            "limit_fiyati": acik.emir.limit_fiyati,
            "kilitli_usdt": onceki_kilit,
            "acik_emir_listesinde": any(
                e.istemci_kimligi == acik.emir.istemci_kimligi
                for e in adaptor.acik_emirler("BTCUSDT")
            ),
            "gecti": acik.emir.durum is EmirDurumu.ACKNOWLEDGED,
        }
    )
    _vaka_yaz(vakalar[-1])

    # --- vaka 2: iptal ------------------------------------------------------
    iptal = motor.iptal(acik.emir.istemci_kimligi)
    sonraki_kilit = adaptor.bakiye().get("USDT", Varlik()).kilitli
    vakalar.append(
        {
            "vaka": "iptal",
            "durum": str(iptal.emir.durum),
            "iptal_edildi": iptal.iptal_edildi,
            "kilitli_usdt": sonraki_kilit,
            "kilit_cozuldu": sonraki_kilit < onceki_kilit,
            "acik_emir_listesinde": any(
                e.istemci_kimligi == acik.emir.istemci_kimligi
                for e in adaptor.acik_emirler("BTCUSDT")
            ),
            "gecti": iptal.iptal_edildi
            and iptal.emir.durum is EmirDurumu.CANCELED
            and sonraki_kilit < onceki_kilit,
        }
    )
    _vaka_yaz(vakalar[-1])

    # --- vaka 3: marketable limit hemen doluyor -----------------------------
    yakin = fiyat * 1.01
    dolan = _emir_gonder(motor, risk, adaptor, ozkaynak, miktar, yakin, "MARKETABLE")
    vakalar.append(
        {
            "vaka": "marketable",
            "durum": str(dolan.emir.durum),
            "limit_fiyati": dolan.emir.limit_fiyati,
            "ortalama_fiyat": dolan.emir.ortalama_fiyat,
            # Borsa limitten **daha iyi** bir fiyattan doldurmalı: alışta limitin altında.
            "limitten_iyi": 0.0 < dolan.emir.ortalama_fiyat <= dolan.emir.limit_fiyati,
            "gecti": dolan.emir.durum is EmirDurumu.FILLED,
        }
    )
    _vaka_yaz(vakalar[-1])

    # --- vaka 4: dolmuş emrin iptali ----------------------------------------
    nihai: IptalSonucu = motor.iptal(dolan.emir.istemci_kimligi)
    vakalar.append(
        {
            "vaka": "nihai_iptal",
            "durum": str(nihai.emir.durum),
            "aga_cikildi": nihai.gonderildi,
            # Emir zaten `FILLED` olarak defterde: iptal ağa **hiç çıkmamalı** ve durum
            # değişmemeli. Çıkmış olsaydı bile borsa "emir yok" derdi ve sonuç aynı
            # olurdu — ama gereksiz bir yazma isteği, çözülecek yeni bir belirsizliktir.
            "gecti": nihai.emir.durum is EmirDurumu.FILLED and not nihai.iptal_edildi,
        }
    )
    _vaka_yaz(vakalar[-1])

    hatalar: list[dict[str, Any]] = []
    pozisyon = _pozisyon_adimi(defter, adaptor, hatalar)

    return {
        "kosu_adi": kosu_adi,
        "utc": utc_str(simdi_ms()),
        "son_fiyat": fiyat,
        "vakalar": vakalar,
        "pozisyon_mutabakati": pozisyon,
        "hatalar": hatalar,
        "defter_sayimi": defter.sayim(),
        "kriter_saglandi": all(v["gecti"] for v in vakalar)
        and not pozisyon.get("halt", True),
        "not": (
            "Gözlem modu (K-035): bu koşunun hiçbir kaydı promotion kanıtı değildir."
        ),
    }


def _emir_gonder(
    motor: EmirMotoru,
    risk: RiskMotoru,
    adaptor: BinanceImzaliAdaptoru,
    ozkaynak: float,
    miktar: float,
    limit_fiyati: float,
    etiket: str,
):
    """Risk motorundan geçirip limit emri gönderir.

    Niyet elle kurulmuyor: değişmez kural 3 (*"sinyal risk motorunu atlayamaz"*) bu
    ölçümde de geçerli — bir ölçüm aracı olması onu muaf tutmaz.
    """
    bar_ms = adaptor.sunucu_zamani_ms()
    fiyat = adaptor.son_fiyat("BTCUSDT")
    risk.bar_isle(bar_ms, ozkaynak)
    karar = risk.degerlendir(
        Sinyal(
            symbol="BTCUSDT",
            side=Yon.BUY,
            target_exposure=(miktar * limit_fiyati) / ozkaynak,
            confidence=1.0,
            reason=f"FAZ8_LIMIT_{etiket}",
            timestamp=bar_ms,
        ),
        PiyasaOlcumu(
            fiyat=fiyat,
            ozkaynak=ozkaynak,
            mevcut_maruziyet=0.0,
            bar_ms=bar_ms,
            atr=fiyat * 0.01,
        ),
    )
    if not isinstance(karar, OnayliNiyet):
        raise typer.BadParameter(f"risk motoru reddetti ({etiket}): {karar.sebep}")
    return motor.gonder(karar, miktar, limit_fiyati=limit_fiyati)


def _vaka_yaz(vaka: dict[str, Any]) -> None:
    renk = typer.colors.GREEN if vaka["gecti"] else typer.colors.RED
    ayrinti = " · ".join(
        f"{k}={v}" for k, v in vaka.items() if k not in ("vaka", "gecti")
    )
    typer.secho(f"  {vaka['vaka']:<14} {ayrinti}", fg=renk)
