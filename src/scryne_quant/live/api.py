"""Dashboard API'si: trader sürecinin **içinde** çalışan salt-okunur FastAPI. (K-012, K-036)

Dört sayfanın (Overview, Strategies, Positions, Logs — K-012) ihtiyaç duyduğu her şey
burada, ve hepsi **okuma**. Yazma ucu yok ve bu bir eksiklik değil, bir sınır:

- Risk limitleri ve strateji parametreleri koşu kimliğinin parçası ve koşu kimliği
  değişmez (K-009; `depo.py`deki `kosu_degismez` tetikleyicisi). Onları API'den
  değiştirebilmek, 30 günlük bir koşunun ortasında konfigürasyonu kaydırmak ve kaydı
  "hangi konfigürasyonla üretildi" sorusuna cevapsız bırakmak olurdu.
- SAFE_MODE'dan çıkış **elle onayla** olur (K-008/4) ve o onay bir gerekçe metni ister.
  Bir dashboard butonu o gerekçeyi bir tıklamaya indirgerdi. Çıkış yolu CLI'da:
  `sq risk serbest`.

**Neden trader sürecinin içinde:** risk durumu, portföy ve pencere o sürecin belleğinde
yaşıyor. Ayrı bir API süreci, o belleğe erişmek için trader'a HTTP atan bir proxy'den
ibaret olurdu — ve ayakta kalması gereken ikinci bir servis, *"30 gün kesintisiz"*
kriterinin paydası (K-034, K-036).

**Her uç `async def`.** FastAPI senkron bir işleyiciyi bir iş parçacığı havuzunda
çalıştırır; oysa koşu deposu SQLite ve SQLite bağlantıları iş parçacığına bağlıdır.
`check_same_thread=False` ile o kontrolü kapatmak mümkündü ama yanlış olurdu: kontrol tam
da bu hatayı yakalamak için var, ve kapatıldığında yerini bir kilit alması gerekirdi.
Doğru cevap daha basit — API de trader döngüsüyle **aynı** olay döngüsünde çalışsın. Tek
yazıcı, tek okuyucu, tek iş parçacığı: K-034'ün "eşzamanlı yazma yok" gerekçesi ancak
böyle doğru kalır.

**Canlı güncelleme SSE ile, WebSocket ile değil.** Trafik tek yönlü (sunucu → tarayıcı) ve
seyrek (1h timeframe'de saatte bir bar). SSE'nin yeniden bağlanması tarayıcıda hazır
geliyor; WebSocket'te onu elle yazmak gerekirdi. İki yönlü bir kanala ihtiyaç duyulmaması
yukarıdaki "yazma ucu yok" kararının doğrudan sonucu.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.live.depo import KESINTI_OLAYLARI, KosuDeposu
from scryne_quant.live.motor import BarSonucu, PaperMotoru
from scryne_quant.risk.audit import Defter

#: SSE abonelerinin kuyruk derinliği. Küçük ve **bilerek**: yavaş bir istemci yüzünden
#: bellekte biriken bir kuyruk, 30 günlük koşuyu bir bellek hatasıyla bitirmenin en sessiz
#: yolu. Kuyruk dolarsa en eski olay düşürülür — dashboard bir güncellemeyi kaçırır,
#: koşu devam eder. Kaydın kendisi diskte, kaybolan şey yalnızca canlı bildirim.
KUYRUK_DERINLIGI: Final = 32

#: `/api/olay` ve `/api/audit`in varsayılan sayfa boyu.
VARSAYILAN_LIMIT: Final = 100


class Yayinci:
    """SSE abonelerine olay dağıtan basit fan-out.

    Abone başına bir kuyruk; dolan kuyruk **eskiyi düşürür**, yayıncıyı bloklamaz. Bir
    dashboard sekmesinin yavaşlığı trader döngüsünü yavaşlatamamalı — bu, arayüzün asla
    ölçümün önüne geçmemesi kuralının koddaki hâli.
    """

    def __init__(self) -> None:
        self._kuyruklar: set[asyncio.Queue[str]] = set()

    def abone(self) -> asyncio.Queue[str]:
        kuyruk: asyncio.Queue[str] = asyncio.Queue(maxsize=KUYRUK_DERINLIGI)
        self._kuyruklar.add(kuyruk)
        return kuyruk

    def birak(self, kuyruk: asyncio.Queue[str]) -> None:
        self._kuyruklar.discard(kuyruk)

    @property
    def abone_sayisi(self) -> int:
        return len(self._kuyruklar)

    def yayinla(self, veri: dict[str, Any]) -> None:
        metin = json.dumps(veri, ensure_ascii=False, default=str)
        for kuyruk in self._kuyruklar:
            if kuyruk.full():
                with suppress(asyncio.QueueEmpty):  # pragma: no cover - yarış durumu
                    kuyruk.get_nowait()
            with suppress(asyncio.QueueFull):  # pragma: no cover - yarış durumu
                kuyruk.put_nowait(metin)


def uygulama_kur(
    motor: PaperMotoru,
    *,
    defter: Defter | None = None,
    web_kok: Path | None = None,
    yayinci: Yayinci | None = None,
) -> FastAPI:
    """Dashboard API'sini kurar. `web_kok` verilirse SPA build'ini de servis eder."""
    app = FastAPI(title="ScryneQuant", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.motor = motor
    app.state.yayinci = yayinci if yayinci is not None else Yayinci()

    depo: KosuDeposu = motor.depo

    # ------------------------------------------------------------- Overview

    @app.get("/api/ozet")
    async def ozet() -> dict[str, Any]:
        """Overview sayfasının tek kaynağı: portföy, risk, veri sağlığı, kesintiler."""
        an = simdi_ms()
        govde = motor.ozet(an)
        govde["saglik"] = _saglik(motor, depo, an)
        return govde

    # ------------------------------------------------------------ Strategies

    @app.get("/api/strateji")
    async def strateji() -> dict[str, Any]:
        """Strateji sayfası: kimlik, promotion aşaması, karar sayaçları."""
        risk = motor.risk
        return {
            "strateji": motor.kimlik.strateji,
            "mod": motor.kimlik.mod,
            "limit_kimligi": motor.kimlik.limit_kimligi,
            "limitler": motor.kimlik.limitler,
            "promotion": {
                ad: str(asama) for ad, asama in sorted(risk.asamalar.items())
            },
            # Gözlem modunun promotion kanıtı üretemediği bilgisi arayüzde de görünür
            # olmalı: ekranda "30 gün kesintisiz" yazan bir kutunun yanında o koşunun
            # kapıya sayılmadığı yazmıyorsa, ekran yanıltır (K-035).
            "kanit_uretir": motor.kimlik.mod == "paper",
            "sayimlar": {
                "degerlendirilen": risk.degerlendirilen,
                "onay": risk.onay_sayisi,
                "red": dict(risk.red_sayimi),
                "kisit": dict(risk.kisit_sayimi),
            },
        }

    # ------------------------------------------------------------- Positions

    @app.get("/api/pozisyon")
    async def pozisyon(limit: int = Query(VARSAYILAN_LIMIT, ge=1, le=1000)) -> dict[str, Any]:
        """Pozisyon sayfası: açık pozisyon, bekleyen niyet, fill defteri."""
        fiyat = motor.fiyat()
        return {
            "fiyat": fiyat,
            "portfoy": motor.ozet()["portfoy"],
            "acik": motor.portfoy.acik,
            "deger": None if fiyat is None else motor.portfoy.deger(fiyat),
            "maruziyet": None if fiyat is None else motor.portfoy.maruziyet(fiyat),
            "acik_islem": motor.ozet()["acik_islem"],
            "bekleyen": motor.ozet()["bekleyen"],
            "filller": depo.filller(limit=limit),
            "fill_sayisi": depo.fill_sayisi(),
        }

    # ------------------------------------------------------------------ Logs

    @app.get("/api/olay")
    async def olay(limit: int = Query(VARSAYILAN_LIMIT, ge=1, le=1000)) -> dict[str, Any]:
        """Koşu günlüğü: başlangıç, toparlanma, bayatlık, kopma, hata, kapanış."""
        return {
            "olaylar": depo.olaylar(limit=limit),
            "kesinti_sayisi": depo.kesinti_sayisi(),
            "kesinti_turleri": sorted(str(t) for t in KESINTI_OLAYLARI),
        }

    @app.get("/api/audit")
    async def audit(limit: int = Query(VARSAYILAN_LIMIT, ge=1, le=1000)) -> dict[str, Any]:
        """Risk audit defteri: onay, red, kill, serbest. Zincir doğrulaması dahil."""
        if defter is None:
            raise HTTPException(status_code=503, detail="audit defteri bağlı değil")
        kayitlar = defter.oku(limit=limit)
        return {
            "kayitlar": list(reversed(kayitlar)),
            # Zincirin bütünlüğü ekranda görünmeli: "kurcalanmadı" bilgisi, ancak
            # gösterildiğinde bir güvence (K-032).
            "zincir_gecerli": defter.dogrula(),
        }

    # --------------------------------------------------------------- canlı

    @app.get("/api/akis")
    async def akis() -> StreamingResponse:
        """Server-Sent Events: her işlenmiş barda bir olay."""
        yayinci: Yayinci = app.state.yayinci
        kuyruk = yayinci.abone()

        async def uret() -> AsyncIterator[bytes]:
            try:
                # İlk mesaj anlık durum: yeni açılan bir sekme bir sonraki barı (1h'te
                # bir saat) beklemeden dolu bir ekran görmeli.
                yield _sse({"tur": "ozet", "govde": await ozet()})
                while True:
                    try:
                        metin = await asyncio.wait_for(kuyruk.get(), timeout=20.0)
                    except TimeoutError:
                        # Yorum satırı: ara sunucuların bağlantıyı boşta kapatmasını
                        # engelliyor. SSE'de veri olmayan satır yok sayılır.
                        yield b": nabiz\n\n"
                        continue
                    yield f"data: {metin}\n\n".encode()
            finally:
                yayinci.birak(kuyruk)

        return StreamingResponse(
            uret(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ----------------------------------------------------------------- SPA

    if web_kok is not None and web_kok.is_dir():
        varliklar = web_kok / "assets"
        if varliklar.is_dir():
            app.mount("/assets", StaticFiles(directory=varliklar), name="assets")

        @app.get("/{yol:path}")
        async def spa(yol: str) -> FileResponse:
            """SPA geri düşüşü: bilinen dosya varsa o, yoksa `index.html`.

            İstemci tarafı yönlendirme için gerekli — `/positions` doğrudan açıldığında
            sunucuda öyle bir dosya yok ama SPA o yolu tanıyor.
            """
            hedef = (web_kok / yol).resolve()
            if yol and hedef.is_file() and web_kok.resolve() in hedef.parents:
                return FileResponse(hedef)
            return FileResponse(web_kok / "index.html")

    return app


def bar_yayini(yayinci: Yayinci, motor: PaperMotoru):
    """`Kosturucu(bar_kancasi=...)` için: her bardan sonra SSE'ye özet yollar."""

    def kanca(sonuc: BarSonucu) -> None:
        an = simdi_ms()
        yayinci.yayinla(
            {
                "tur": "bar",
                "bar": sonuc.sozluk(),
                "govde": {**motor.ozet(an), "saglik": _saglik(motor, motor.depo, an)},
            }
        )

    return kanca


def _saglik(motor: PaperMotoru, depo: KosuDeposu, an: int) -> dict[str, Any]:
    """Overview'ın "System Health" kutusu.

    `kesintisiz_gun` **ilk olaydan** bu yana geçen süre, kesintilerin sayısıyla birlikte
    veriliyor — tek başına bir gün sayısı göstermek, kesintileri görünmez kılardı ve Faz
    6'nın kriteri tam olarak ikisinin birlikte okunmasını istiyor.
    """
    ilk = depo.ilk_olay_ms()
    kesinti = depo.kesinti_sayisi()
    return {
        "baslangic_ms": ilk,
        "baslangic_utc": None if ilk is None else utc_str(ilk),
        "calisma_gun": 0.0 if ilk is None else (an - ilk) / 86_400_000,
        "kesinti_sayisi": kesinti,
        "kesintisiz": kesinti == 0,
        "durdu": motor.durdu,
        "safe_mode": motor.risk.durum.safe_mode,
        "safe_mode_sebep": motor.risk.durum.safe_mode_sebep,
        "bayat": motor.tazelik.bayat_mi(an),
        "veri_yasi_ms": motor.tazelik.yas(an),
    }


def _sse(veri: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(veri, ensure_ascii=False, default=str)}\n\n".encode()


__all__ = ["KUYRUK_DERINLIGI", "VARSAYILAN_LIMIT", "Yayinci", "bar_yayini", "uygulama_kur"]
