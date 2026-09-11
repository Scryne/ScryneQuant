"""Kayan bar penceresi: canlı barların strateji görebileceği hâle geldiği yer. (K-001, K-006)

Backtest'te strateji tüm seriyi görür ve `ctx` onu `t`'de keser (K-002). Canlıda böyle bir
seri yok — barlar birer birer gelir. Bu sınıf aradaki farkı kapatıyor: son N kapanmış barı
tutar, her yeni barda **aynı doğrulamadan** (`data/dogrulama.py:dogrula`) geçirir ve
backtest motorunun beklediği dizileri üretir.

**Neden aynı doğrulama, neden ayrı bir canlı kural seti değil:** K-001 "backtest = paper =
live, tek kod yolu" diyor. Canlı bara ayrı bir kalite kuralı yazmak, aynı barın backtest'te
`ok` canlıda `suspect` (veya tersi) sayıldığı bir sistem üretir — ve o ayrışma sonuçlarda
"biraz farklı" olarak görünür, hata olarak değil. Bu projede en pahalı hata sınıfı budur.

**Pencere neden sınırlı:** 30 gün kesintisiz çalışacak bir süreçte sınırsız büyüyen bir
tampon, koşuyu bir bellek hatasıyla bölen şeydir. Sınır indikatör ısınmasından bolca büyük
seçilir; kaydırma FIFO'dur ve düşen bar diske yazılmış olur (`live/depo.py`).

**Yeniden doğrulama maliyeti:** pencere her yeni barda baştan doğrulanıyor — 1h'te saatte
bir, 1.000 bar için milisaniye mertebesinde. Artımlı doğrulama yazmak, `gap` ve
`asiri_hareket` kurallarının komşuluk bağımlılığı yüzünden ikinci bir kural
uygulaması demek olurdu; ikinci uygulama er ya da geç birinciden ayrışır.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable, Iterator
from dataclasses import replace
from typing import Any, Final

import numpy as np
import pandas as pd

from scryne_quant.common.zaman import timeframe_ms, utc_str
from scryne_quant.data.dogrulama import KaliteRaporu, dogrula
from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI, KaliteDurumu
from scryne_quant.live.akis import AkisHatasi, Bar, Kaynak

#: Varsayılan pencere boyu. En uzun indikatör penceresi (Faz 4'te 200 barlık SMA) artı
#: bolca pay: ısınması tamamlanmamış bir indikatör NaN üretir ve risk motoru NaN ATR'yi
#: "ölçülemedi" sayıp reddeder (Faz 5). Yani dar pencere, sistemin kendini sessizce
#: durdurması demek — pahalı olan bellek değil, o sessizlik.
VARSAYILAN_KAPASITE: Final = 1_000


class PencereHatasi(AkisHatasi):
    """Pencere sözleşmesi ihlal edildi (geriye giden zaman, hizasız bar)."""


class BarPenceresi:
    """Son N kapanmış barı tutan, doğrulanmış kayan pencere."""

    __slots__ = ("_sembol", "_timeframe", "_adim", "_kapasite", "_barlar", "_onbellek", "_rapor")

    def __init__(
        self,
        sembol: str,
        timeframe: str,
        *,
        kapasite: int = VARSAYILAN_KAPASITE,
    ) -> None:
        if kapasite < 2:
            raise PencereHatasi(f"pencere kapasitesi en az 2 olmalı: {kapasite}")
        self._sembol = sembol
        self._timeframe = timeframe
        self._adim = timeframe_ms(timeframe)
        self._kapasite = kapasite
        self._barlar: deque[Bar] = deque(maxlen=kapasite)
        self._onbellek: dict[str, np.ndarray] | None = None
        self._rapor: KaliteRaporu | None = None

    # ------------------------------------------------------------------ ölçüm

    def __len__(self) -> int:
        return len(self._barlar)

    def __iter__(self) -> Iterator[Bar]:
        return iter(self._barlar)

    @property
    def sembol(self) -> str:
        return self._sembol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def kapasite(self) -> int:
        return self._kapasite

    @property
    def dolu(self) -> bool:
        return len(self._barlar) == self._kapasite

    @property
    def son(self) -> Bar | None:
        return self._barlar[-1] if self._barlar else None

    @property
    def son_ms(self) -> int | None:
        son = self.son
        return None if son is None else son.open_time

    def beklenen_sonraki_ms(self) -> int | None:
        """Sıradaki barın açılış zamanı. Pencere boşsa `None`."""
        son = self.son_ms
        return None if son is None else son + self._adim

    # ------------------------------------------------------------------ ekleme

    def ekle(self, bar: Bar) -> bool:
        """Bir barı pencereye alır. Yeni bar eklendiyse `True`, revize edildiyse `False`.

        Üç durum ayrı ayrı ele alınıyor ve ikisi sessiz **değil**:

        - **İleri bar** → eklenir. Aradaki boşluk uydurulmaz (K-024); `dogrula` sonraki
          barı `gap` işaretler.
        - **Aynı zamanlı bar** → üzerine yazılır ve `False` döner. Borsa kapanmış bir barı
          revize edebilir; son gelen daha güncel veridir (depo ile aynı kural).
        - **Geriye giden bar** → `PencereHatasi`. Bu bir veri kusuru değil, akışın
          sözleşmesinin ihlali: zamanın geri gittiği bir akıştan üretilen her karar
          şüphelidir ve sayılabilir bir bayrakla geçiştirilemez.
        """
        if not bar.hizali_mi(self._timeframe):
            raise PencereHatasi(
                f"bar {self._timeframe} ızgarasına hizalı değil: "
                f"{bar.open_time} = {utc_str(bar.open_time)} (K-005)"
            )

        son = self.son
        if son is not None:
            if bar.open_time < son.open_time:
                raise PencereHatasi(
                    f"akış geriye gitti: gelen {utc_str(bar.open_time)}, "
                    f"penceredeki son {utc_str(son.open_time)}"
                )
            if bar.open_time == son.open_time:
                self._barlar[-1] = bar
                self._onbellek = None
                self._rapor = None
                return False

        self._barlar.append(bar)
        self._onbellek = None
        self._rapor = None
        return True

    def doldur(self, barlar: Iterable[Bar]) -> int:
        """Birden çok barı sırayla ekler; eklenen **yeni** bar sayısını döndürür."""
        return sum(1 for bar in barlar if self.ekle(bar))

    # -------------------------------------------------------------- doğrulama

    def _hesapla(self) -> tuple[dict[str, np.ndarray], KaliteRaporu]:
        if not self._barlar:
            raise PencereHatasi("boş pencere doğrulanamaz")

        ham = pd.DataFrame([bar.sozluk() for bar in self._barlar], columns=list(HAM_BAR_SUTUNLARI))
        dogrulanmis, rapor = dogrula(ham, self._timeframe, sembol=self._sembol)

        # Bayrağı bar başına düzelt: `dogrula`'nın `backfill` parametresi parti geneli,
        # oysa bir pencerede akıştan gelen ve sonradan tamamlanan barlar **karışık**
        # durur. K-006'nın kuralı bar başına uygulanıyor: sonradan tamamlanmış ve başka
        # hiçbir kusuru olmayan bar `ok` değil `backfilled`.
        durum = dogrulanmis["quality_status"].to_numpy(dtype=object)
        backfill = np.fromiter(
            (bar.kaynak is Kaynak.BACKFILL for bar in self._barlar),
            dtype=bool,
            count=len(self._barlar),
        )
        degistir = backfill & (durum == str(KaliteDurumu.OK))
        durum[degistir] = str(KaliteDurumu.BACKFILLED)

        # Rapor **düzeltilmiş** bayraklarla yeniden sayılıyor. `dogrula` sayımını
        # kendi ürettiği bayraklardan yapıyor ve o bayraklar bar-başına düzeltmeden
        # önceki hâl; olduğu gibi bırakılsaydı dashboard "1000 bar ok" derken motor aynı
        # barları `backfilled` görürdü. İki sayının aynı veriyi farklı anlatması, bu
        # projede "neredeyse doğru"nun tarifi — ve rapor ekranda okunan taraf.
        if degistir.any():
            rapor = replace(rapor, bayraklar=dict(Counter(str(d) for d in durum)))

        diziler: dict[str, np.ndarray] = {
            "open_time": dogrulanmis["open_time"].to_numpy(dtype="int64"),
            "open": dogrulanmis["open"].to_numpy(dtype="float64"),
            "high": dogrulanmis["high"].to_numpy(dtype="float64"),
            "low": dogrulanmis["low"].to_numpy(dtype="float64"),
            "close": dogrulanmis["close"].to_numpy(dtype="float64"),
            "volume": dogrulanmis["volume"].to_numpy(dtype="float64"),
            "quote_volume": dogrulanmis["quote_volume"].to_numpy(dtype="float64"),
            "trades": dogrulanmis["trades"].to_numpy(dtype="int64"),
            "quality_status": durum.astype(object),
        }
        for dizi in diziler.values():
            dizi.flags.writeable = False
        return diziler, rapor

    def _yenile(self) -> None:
        if self._onbellek is None or self._rapor is None:
            self._onbellek, self._rapor = self._hesapla()

    def diziler(self) -> dict[str, np.ndarray]:
        """Backtest motorunun beklediği bar dizileri — `quality_status` dahil.

        Diziler **salt-okunur** (`writeable = False`). Strateji `ctx` üzerinden kopya
        alır (K-002), ama pencereyi tüketen başka bir katmanın kazara yerinde değiştirmesi
        canlıda geçmişi değiştirmek olurdu — backtest'te portföyün değişmezliğiyle
        (`portfolio/durum.py`) korunan şeyin buradaki karşılığı.
        """
        self._yenile()
        assert self._onbellek is not None
        return dict(self._onbellek)

    def rapor(self) -> KaliteRaporu:
        """Penceredeki barların kalite raporu. Dashboard'un "veri sağlığı" kutusu bunu okur."""
        self._yenile()
        assert self._rapor is not None
        return self._rapor

    def son_bar_ok_mu(self) -> bool:
        """Penceredeki son barın kalite bayrağı `ok` mi? (K-028'in canlı karşılığı)"""
        if not self._barlar:
            return False
        return str(self.diziler()["quality_status"][-1]) == str(KaliteDurumu.OK)

    def sozluk(self) -> dict[str, Any]:
        rapor = self.rapor() if self._barlar else None
        return {
            "sembol": self._sembol,
            "timeframe": self._timeframe,
            "kapasite": self._kapasite,
            "bar_sayisi": len(self._barlar),
            "ilk_ms": self._barlar[0].open_time if self._barlar else None,
            "son_ms": self.son_ms,
            "bayraklar": dict(rapor.bayraklar) if rapor else {},
            "bosluk_sayisi": rapor.bosluk_sayisi if rapor else 0,
        }


__all__ = ["VARSAYILAN_KAPASITE", "BarPenceresi", "PencereHatasi"]
