"""Koşu kurulumu: parçaların birleştiği tek yer. (Faz 6)

`live/` paketindeki her modül bir işi yapıyor ve hiçbiri diğerini kurmuyor; bu modül
onları birleştirir. Ayrı durmasının sebebi test edilebilirlik değil, **bağımlılık yönü**:
motorun bir borsa tanımaması (`BarAkisi` protokolü tüketici tarafında), penceresinin
Parquet deposunu bilmemesi, API'nin koşturucuyu bilmemesi — hepsi ancak birleştirme işi
dışarıda durduğunda mümkün.

**Isınma barları `BACKFILL` işaretleniyor.** Depodan ve REST'ten gelen tarihsel barlar bu
koşu tarafından canlı alınmadı; `backfilled` bayrağı (K-006) onları `ok` olmayan yapar ve
paper motoru onların açılışında **fill iddia etmez** (K-028). Yani süreç başlarken geçmişte
işlem yapmış gibi görünmesi yapısal olarak imkânsız. İlk gerçek karar, akıştan gelen ilk
kapanmış barda verilir.
"""

from __future__ import annotations

import asyncio
import signal
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn

from scryne_quant.common import hash as hash_mod
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.common.zaman import simdi_ms, timeframe_ms
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.exchange.akis import BinanceBarAkisi, df_barlara
from scryne_quant.exchange.binance import BinanceAdaptoru
from scryne_quant.live.akis import Bar, Kaynak
from scryne_quant.live.api import Yayinci, bar_yayini, uygulama_kur
from scryne_quant.live.depo import KosuDeposu, KosuKimligi, KosuOlayi
from scryne_quant.live.kilit import KosuKilidi
from scryne_quant.live.kosturucu import Kosturucu
from scryne_quant.live.motor import PaperMotoru
from scryne_quant.live.pencere import VARSAYILAN_KAPASITE
from scryne_quant.live.toparlanma import ToparlanmaSonucu, toparlan
from scryne_quant.risk.audit import SqliteDefter
from scryne_quant.risk.limitler import RiskLimitleri
from scryne_quant.risk.motor import RiskMotoru
from scryne_quant.risk.promotion import PromotionDefteri
from scryne_quant.strategy.temel import Strateji


@dataclass(frozen=True, slots=True)
class Kurulum:
    """Kurulmuş ama henüz çalışmayan koşu."""

    motor: PaperMotoru
    kosturucu: Kosturucu
    yayinci: Yayinci
    toparlanma: ToparlanmaSonucu
    kilit: KosuKilidi
    """Koşunun tek-yazıcı kilidi; süreç boyunca tutuluyor (`live/kilit.py`)."""

    def kapat(self) -> None:
        """Kilidi ve depoyu bırakır. İki kez çağrılabilir."""
        self.kilit.kapat()

    def sozluk(self) -> dict[str, Any]:
        return {
            "kosu": self.motor.kimlik.sozluk(),
            "toparlanma": self.toparlanma.sozluk(),
            "pencere": self.motor.pencere.sozluk(),
        }


def kimlik_kur(
    *,
    kosu_adi: str,
    mod: str,
    sembol: str,
    timeframe: str,
    strateji: Strateji,
    maliyet: MaliyetModeli,
    limitler: RiskLimitleri,
    baslangic_sermaye: float,
) -> KosuKimligi:
    """Koşu kimliğini K-009'un altı alanıyla birlikte kurar.

    `dirty` bayrağı **engellemiyor**, kaydediliyor. Engelleyen yer promotion kapısı
    (K-009: kirli ağaçla üretilen sonuç promotion'a giremez); gözlem koşusunu kirli ağaç
    yüzünden başlatmamak, altyapı testini kaynak kontrolüne bağlamak olurdu.
    """
    git = hash_mod.git_durumu()
    return KosuKimligi(
        kosu_adi=kosu_adi,
        mod=mod,
        sembol=sembol,
        timeframe=timeframe,
        strateji=strateji.sozluk(),
        maliyet=maliyet.sozluk(),
        limitler=limitler.sozluk(),
        limit_kimligi=limitler.kimlik(),
        baslangic_sermaye=baslangic_sermaye,
        commit_sha=str(git.get("commit") or ""),
        dirty=bool(git.get("dirty")),
        kutuphaneler=hash_mod.ortam_kaydi(),
        olusturuldu_ms=simdi_ms(),
    )


def isinma_barlari(
    sembol: str,
    timeframe: str,
    *,
    depo_kok: Path,
    adaptor: BinanceAdaptoru | None,
    kapasite: int = VARSAYILAN_KAPASITE,
) -> list[Bar]:
    """Isınma penceresini depodan doldurur, kalan boşluğu REST'ten tamamlar.

    İkisi de `Kaynak.BACKFILL`: bu koşu onları canlı almadı. Depo yoksa ve REST de
    erişilemiyorsa boş dönülür — pencere büyümeye akıştan başlar ve ilk
    `RISK_ATR_PENCERESI + 1` bar boyunca volatilite ölçülemediği için giriş yapılmaz.
    Bu sessiz bir kayıp değil, kayıtlı bir gecikme.
    """
    adim = timeframe_ms(timeframe)
    barlar: list[Bar] = []

    parquet = ParquetDepo(depo_kok)
    if parquet.var_mi(sembol, timeframe):
        df = parquet.oku(sembol, timeframe).tail(kapasite)
        barlar = df_barlara(df, kaynak=Kaynak.BACKFILL)

    if adaptor is None:
        return barlar

    simdi = adaptor.sunucu_zamani_ms()
    baslangic = (
        barlar[-1].open_time + adim if barlar else simdi - kapasite * adim
    )
    if baslangic < simdi:
        yeni = adaptor.klines(sembol, timeframe, baslangic, simdi)
        barlar.extend(df_barlara(yeni, kaynak=Kaynak.BACKFILL))

    return barlar[-kapasite:]


def kur(
    *,
    kimlik: KosuKimligi,
    strateji: Strateji,
    maliyet: MaliyetModeli,
    limitler: RiskLimitleri,
    kosu_yolu: Path,
    depo_kok: Path,
    adaptor: BinanceAdaptoru | None = None,
    promotion_kok: Path | None = None,
    kapasite: int = VARSAYILAN_KAPASITE,
    azami_veri_yasi_ms: int | None = None,
    web_kok: Path | None = None,
) -> tuple[Kurulum, Any]:
    """Koşuyu ve API uygulamasını kurar; henüz hiçbir şey çalışmıyor.

    **Kilit her şeyden önce alınıyor.** Depo açıldıktan sonra alınsaydı, ikinci süreç
    kilide takılana kadar çoktan bir SQLite bağlantısı açmış ve WAL dosyalarına dokunmuş
    olurdu. Kilit, koşuya dokunan ilk işlem olmalı.
    """
    kilit = KosuKilidi(kosu_yolu).al()
    depo = KosuDeposu(kosu_yolu)
    # Audit defteri **aynı dosyada**: risk kararları ile koşu durumu tek bir dosyada
    # yaşıyor, yani koşunun kopyası kararlarının da kopyası (K-034).
    defter = SqliteDefter(kosu_yolu)

    asamalar = {}
    if promotion_kok is not None and promotion_kok.is_dir():
        asamalar = {k.strateji: k.asama for k in PromotionDefteri(promotion_kok).hepsi()}

    risk = RiskMotoru(limitler, kimlik.timeframe, mod=kimlik.mod, defter=defter, asamalar=asamalar)
    motor_kw: dict[str, Any] = {"kapasite": kapasite}
    if azami_veri_yasi_ms is not None:
        motor_kw["azami_veri_yasi_ms"] = azami_veri_yasi_ms

    motor = PaperMotoru(
        kimlik=kimlik, strateji=strateji, maliyet=maliyet, risk=risk, depo=depo, **motor_kw
    )

    toparlanma = toparlan(
        motor,
        isinma_barlari(
            kimlik.sembol,
            kimlik.timeframe,
            depo_kok=depo_kok,
            adaptor=adaptor,
            kapasite=kapasite,
        ),
    )

    yayinci = Yayinci()
    akis = BinanceBarAkisi(
        kimlik.sembol,
        kimlik.timeframe,
        adaptor=adaptor,
        nabiz_kancasi=motor.nabiz,
        kopma_kancasi=lambda sebep: depo.olay_yaz(
            KosuOlayi.KOPMA, bar_ms=motor.son_bar_ms, ayrinti={"sebep": sebep}
        ),
    )
    kosturucu = Kosturucu(motor, akis, bar_kancasi=bar_yayini(yayinci, motor))
    app = uygulama_kur(motor, defter=defter, web_kok=web_kok, yayinci=yayinci)
    return Kurulum(motor, kosturucu, yayinci, toparlanma, kilit), app


async def calistir(
    kurulum: Kurulum, app: Any, *, host: str = "127.0.0.1", port: int = 8787
) -> dict[str, Any]:
    """Koşturucuyu ve API sunucusunu birlikte çalıştırır; biri biterse diğerini durdurur.

    Tek süreç, iki görev. `SIGINT`/`SIGTERM` koşturucuyu **düzgün** durduruyor: yarım
    kalan bir bar, yazılmamış bir kontrol noktası bırakır ve toparlanma o barı yeniden
    işler — ama düzgün kapanış o yeniden işlemeyi gereksiz kılar ve koşu günlüğüne
    "durdu" satırı bırakır. Kayıtta "neden durdu" boşluğu, Faz 6'nın kesinti kriterinde
    açıklanamayan bir kesinti demek.
    """
    sunucu = uvicorn.Server(
        uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    )

    dongu = asyncio.get_running_loop()
    for isaret in (signal.SIGINT, signal.SIGTERM):
        # Windows'ta asyncio sinyal işleyicisi yok; uvicorn kendi işleyicisini kuruyor
        # ve `finally` bloğu koşturucuyu yine de durduruyor.
        with suppress(NotImplementedError):
            dongu.add_signal_handler(isaret, kurulum.kosturucu.durdur)

    trader = asyncio.create_task(kurulum.kosturucu.calistir(), name="trader")
    web = asyncio.create_task(sunucu.serve(), name="web")
    try:
        bitenler, _ = await asyncio.wait(
            {trader, web}, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        kurulum.kosturucu.durdur()
        sunucu.should_exit = True
        for gorev in (trader, web):
            if not gorev.done():
                gorev.cancel()
        await asyncio.gather(trader, web, return_exceptions=True)
        # Kilit en sonda bırakılıyor: daha erken bırakmak, koşu hâlâ kapanış satırını
        # yazarken ikinci bir sürecin dosyaya girmesine izin verirdi.
        kurulum.kapat()

    for gorev in bitenler:
        if gorev.exception() is not None:
            raise gorev.exception()  # type: ignore[misc]

    ozet = trader.result() if trader.done() and not trader.cancelled() else None
    return {"kosu": kurulum.sozluk(), "ozet": None if ozet is None else ozet.sozluk()}


__all__ = ["Kurulum", "calistir", "isinma_barlari", "kimlik_kur", "kur"]
