"""Mod başına koşu kurulumu: adaptör, hat, risk, yürütücü. CLI bunu çağırır. (K-114)

Kurulumun **tek** yerde olmasının sebebi yetki: hangi modun hangi adaptörle, hangi anahtarla
ve hangi kontrolden sonra kurulduğu burada okunur. Özellikle:

- **PAPER**: `PaperBorsa` (ağsız emir), kurallar ve barlar borsanın public ucundan.
- **SHADOW**: salt okunur canlı anahtar → `apiRestrictions` shadow tablosu → `canli_okuyucu`
  (taşımada GET-only) → `GolgeAdaptoru`. İşlem yetkili anahtar verilirse kurulum **başlamaz**.
- **TESTNET**: `BinanceImzaliAdaptoru` (testnet host, testnet anahtarı).
- **LIVE**: `canli_kapi.canli_yetki_ver` (mod LIVE + kapı şimdi geçiyor + onay hash'i tutuyor)
  → `CanliYetki` → işlem anahtarı → `canli_emir_adaptoru`. Sermaye kademe sermayesidir.

Sistem modu bir **tavandır**: istenen koşu modu sistem modunun üstündeyse kurulum reddedilir.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import requests

from scryne_quant.common.maliyet import yukle as maliyet_yukle
from scryne_quant.common.zaman import simdi_ms
from scryne_quant.exchange.hatalar import BorsaHatasi
from scryne_quant.exchange.imzali import BinanceImzaliAdaptoru, kurallari_coz
from scryne_quant.exchange.kurallar import SembolKurallari
from scryne_quant.exchange.paper_adaptoru import PaperBorsa, PaperMaliyet
from scryne_quant.execution.canli_kapi import AgYoklamasi, KapiBaglami, canli_yetki_ver
from scryne_quant.execution.hat import ExecutionHatti, GuvenlikLimitleri
from scryne_quant.execution.mod import CalismaModu, ModDefteri, sira
from scryne_quant.live.akis import Bar
from scryne_quant.oms.defter import EmirDefteri
from scryne_quant.risk import limitler as limitler_mod
from scryne_quant.risk.audit import SqliteDefter
from scryne_quant.risk.motor import RiskMotoru
from scryne_quant.risk.promotion import Asama, PromotionDefteri
from scryne_quant.strategy.kutuphane import coz
from scryne_quant.trader.yurutucu import (
    BarKaynagi,
    ListeBarKaynagi,
    RestBarKaynagi,
    Yurutucu,
    YurutucuAyari,
)

#: Public piyasa verisi (anahtarsız). Kurallar ve barlar buradan.
VERI_HOST: Final = "https://data-api.binance.vision"
CANLI_PUBLIC: Final = "https://api.binance.com"

#: Mod başına kabul edilen risk modları. `gozlem` altyapı ölçümüdür, kanıt üretmez (K-035);
#: LIVE yalnızca `live` (K-010). Shadow'un canlı kanıtı yalnızca `shadow` risk modundan.
RISK_MODLARI: Final[dict[CalismaModu, tuple[str, ...]]] = {
    CalismaModu.PAPER: ("gozlem", "paper"),
    CalismaModu.SHADOW: ("gozlem", "shadow"),
    CalismaModu.TESTNET: ("gozlem",),
    CalismaModu.LIVE: ("live",),
}


class KurulumHatasi(RuntimeError):
    """Koşu bu modda kurulamaz."""


def public_kurallar(sembol: str, *, host: str = VERI_HOST) -> SembolKurallari:
    """`exchangeInfo`dan tam kurallar (taban/kote dahil). Anahtarsız GET."""
    try:
        y = requests.get(f"{host}/api/v3/exchangeInfo", params={"symbol": sembol}, timeout=15)
    except requests.exceptions.RequestException as hata:
        raise BorsaHatasi(f"exchangeInfo okunamadı: {hata}") from hata
    if y.status_code != 200:
        raise BorsaHatasi(f"exchangeInfo {y.status_code}: {y.text[:200]}")
    semboller = y.json().get("symbols") or []
    if not semboller:
        raise BorsaHatasi(f"sembol yok: {sembol}")
    return kurallari_coz(semboller[0])


def public_zaman(host: str = CANLI_PUBLIC) -> int:
    try:
        y = requests.get(f"{host}/api/v3/time", timeout=10)
    except requests.exceptions.RequestException as hata:
        raise BorsaHatasi(f"sunucu zamanı okunamadı: {hata}") from hata
    if y.status_code != 200:
        raise BorsaHatasi(f"/api/v3/time {y.status_code}")
    return int(y.json()["serverTime"])


def ag_yoklamasi(env_dosyasi: str | Path = ".env") -> AgYoklamasi:
    """Live gate'in ağ yoklamaları. Hepsi **okuma**; hiçbiri emir göndermez."""
    from scryne_quant.exchange import canli

    def okuma() -> dict[str, Any]:
        anahtar, sir = canli.okuma_anahtari_oku(env_dosyasi)
        return canli.api_kisitlari(anahtar, sir, zaman_ms=public_zaman())

    def islem() -> dict[str, Any]:
        return canli.islem_anahtari_kisitlari(env_dosyasi, zaman_ms=public_zaman())

    def testnet() -> dict[str, Any]:
        a = BinanceImzaliAdaptoru()
        a.bakiye()
        return {"ok": True, "saat_sapmasi_ms": a.saat_sapmasi_ms()}

    def canli_b() -> dict[str, Any]:
        t0 = simdi_ms()
        sunucu = public_zaman()
        return {"ok": True, "rtt_ms": simdi_ms() - t0, "yerel_eksi_sunucu_ms": t0 - sunucu}

    return AgYoklamasi(
        okuma_anahtari_kisitlari=okuma,
        islem_anahtari_kisitlari=islem,
        testnet_baglantisi=testnet,
        canli_baglantisi=canli_b,
    )


@dataclass
class KosuIstegi:
    mod: CalismaModu
    kosu: str
    strateji: str
    parametreler: dict[str, Any]
    sembol: str = "BTCUSDT"
    timeframe: str = "1h"
    sermaye_usdt: float = 10_000.0
    risk_modu: str = "gozlem"
    kok: Path = Path("runs/execution")
    env_dosyasi: str | Path = ".env"
    tekrar_barlari: list[Bar] | None = None
    """Verilirse PAPER koşusu bu barlar üzerinde **tekrar oynatılır** (saat barlarla ilerler)."""

    kurallar: SembolKurallari | None = None
    """Verilirse public uca gidilmez (test, tekrar)."""


def _mod_tavani(istek: KosuIstegi, mod_defteri: ModDefteri) -> None:
    sistem = mod_defteri.mod()
    if sira(istek.mod) > sira(sistem):
        raise KurulumHatasi(
            f"sistem modu {sistem}; {istek.mod} koşusu açılamaz. Önce "
            f"`sq execution yukselt` ile kapıdan geçilmeli (K-114)."
        )
    if istek.risk_modu not in RISK_MODLARI.get(istek.mod, ()):
        raise KurulumHatasi(
            f"{istek.mod} modunda risk modu {istek.risk_modu!r} olamaz; geçerli: "
            f"{', '.join(RISK_MODLARI.get(istek.mod, ()))}"
        )


def _asamalar(strateji: str, audit: SqliteDefter) -> dict[str, Asama]:
    """Promotion aşaması (paper/shadow/live risk modları için K-010 kapısı)."""
    kayit = PromotionDefteri().oku(strateji, audit=audit)
    return {strateji: kayit.asama}


def kosu_kur(
    istek: KosuIstegi,
    *,
    mod_defteri: ModDefteri | None = None,
    kapi_baglami: KapiBaglami | None = None,
    testnet_adaptoru: Callable[[], Any] | None = None,
) -> tuple[Yurutucu, BarKaynagi]:
    """İstenen modda yürütücüyü kurar. Kurulum kontrollerinden biri geçmezse `KurulumHatasi`."""
    md = mod_defteri or ModDefteri(istek.kok / "mod.json")
    _mod_tavani(istek, md)
    dizin = istek.kok / istek.kosu
    dizin.mkdir(parents=True, exist_ok=True)
    audit = SqliteDefter(dizin / "audit.sqlite")
    limitler = limitler_mod.yukle()
    sermaye = float(istek.sermaye_usdt)

    # ------------------------------------------------------------ bar kaynağı ve saat
    kaynak: BarKaynagi
    if istek.tekrar_barlari is not None:
        if istek.mod is not CalismaModu.PAPER:
            raise KurulumHatasi("tekrar oynatma yalnızca PAPER modunda (gerçek emir yok)")
        tekrar = ListeBarKaynagi(istek.tekrar_barlari, istek.timeframe)
        kaynak = tekrar
        saat: Callable[[], int] = tekrar.sunucu_zamani_ms
    else:
        from scryne_quant.exchange.binance import BinanceAdaptoru

        kaynak = RestBarKaynagi(BinanceAdaptoru())
        saat = simdi_ms

    # ------------------------------------------------------------ adaptör
    paper: PaperBorsa | None = None
    kurallar_yolu = dizin / "kurallar.json"
    if istek.mod is CalismaModu.PAPER:
        kural = istek.kurallar or _kurallar_onbellek(kurallar_yolu, istek.sembol)
        m = maliyet_yukle()
        paper = PaperBorsa(
            kurallar={istek.sembol: kural},
            maliyet=PaperMaliyet(m.fee_taker_bps, m.slippage_bps),
            saat=saat,
            yol=dizin / "paper_borsa.sqlite",
            acilis_bakiyesi={kural.kote_varlik: sermaye},
        )
        adaptor: Any = paper
    elif istek.mod is CalismaModu.SHADOW:
        from scryne_quant.exchange import canli
        from scryne_quant.exchange.golge import GolgeAdaptoru

        anahtar, sir = canli.okuma_anahtari_oku(istek.env_dosyasi)
        canli.yetki_denetle("shadow", canli.api_kisitlari(anahtar, sir, zaman_ms=public_zaman()))
        adaptor = GolgeAdaptoru(canli.canli_okuyucu(anahtar, sir))
    elif istek.mod is CalismaModu.TESTNET:
        adaptor = testnet_adaptoru() if testnet_adaptoru else BinanceImzaliAdaptoru()
    elif istek.mod is CalismaModu.LIVE:
        from scryne_quant.exchange import canli

        b = kapi_baglami or KapiBaglami(
            strateji=istek.strateji,
            audit=SqliteDefter("runs/audit.sqlite"),
            ag=ag_yoklamasi(istek.env_dosyasi),
            mod_defteri=md,
        )
        if b.strateji != istek.strateji:
            raise KurulumHatasi("kapı bağlamının stratejisi istekle aynı olmalı")
        yetki, _ = canli_yetki_ver(b)
        anahtar, sir = canli.islem_anahtari_oku(yetki, istek.env_dosyasi)
        adaptor = canli.canli_emir_adaptoru(yetki, anahtar, sir)
        # Canlı sermaye **kademe** sermayesidir; istek bunu aşamaz.
        sermaye = min(sermaye, yetki.sermaye_usdt)
    else:
        raise KurulumHatasi(f"{istek.mod} bir koşu modu değil")

    hat = ExecutionHatti(
        mod=istek.mod,
        adaptor=adaptor,
        defter=EmirDefteri(dizin / "emirler.sqlite"),
        limitler=GuvenlikLimitleri.risk_limitlerinden(limitler, sermaye),
        sembol=istek.sembol,
        kosu_dizini=dizin,
        audit=audit,
        saat=saat,
    )
    asamalar = (
        _asamalar(istek.strateji, SqliteDefter("runs/audit.sqlite"))
        if istek.risk_modu in ("paper", "shadow", "live")
        else {}
    )
    risk = RiskMotoru(
        limitler, istek.timeframe, mod=istek.risk_modu, defter=audit, asamalar=asamalar
    )
    strateji = coz(istek.strateji)(**istek.parametreler)
    ayar = YurutucuAyari(
        kosu_adi=istek.kosu,
        mod=istek.mod,
        risk_modu=istek.risk_modu,
        strateji=istek.strateji,
        parametreler=strateji.parametreler,
        sembol=istek.sembol,
        timeframe=istek.timeframe,
        sermaye_usdt=sermaye,
        kosu_dizini=dizin,
    )
    y = Yurutucu(
        ayar=ayar, strateji=strateji, risk=risk, hat=hat, kaynak=kaynak, paper=paper, saat=saat
    )
    return y, kaynak


def _kurallar_onbellek(yol: Path, sembol: str) -> SembolKurallari:
    """Paper koşusunun kuralları ilk başlangıçta çekilir ve **sabitlenir** (yeniden üretim)."""
    if yol.is_file():
        return SembolKurallari(**json.loads(yol.read_text(encoding="utf-8")))
    k = public_kurallar(sembol)
    yol.write_text(
        json.dumps({f: getattr(k, f) for f in k.__dataclass_fields__}, indent=1),
        encoding="utf-8",
    )
    return k


__all__ = [
    "RISK_MODLARI",
    "KosuIstegi",
    "KurulumHatasi",
    "ag_yoklamasi",
    "kosu_kur",
    "public_kurallar",
    "public_zaman",
]
