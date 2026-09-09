"""Borsa adaptörü sözleşmesi. (K-003, K-015)

Sistemin borsayla konuşan **tek** kapısı burasıdır. Arayüz bilerek dar: tarihsel bar
çekmek, sunucu saatini sormak, sembol kurallarını okumak. Emir gönderme Faz 7'de bu
arayüze eklenir; şimdiden yer açılmıyor çünkü kullanılmayan bir metot, kullanıldığında
test edilmemiş olur.

Neden arayüz var da doğrudan ccxt çağrılmıyor: `strategy/` bu pakete erişemez (K-003) ve
testler ağa çıkmadan çalışmak zorunda. İkisinin de tek yolu, gerçek borsanın yerine
geçebilecek bir sözleşmenin var olması.

**Bar sözleşmesi:** `klines` yalnızca **kapanmış** bar döndürür (K-015/1). Kapanmamış bar
çağrılar arasında değişir; depoya girerse Faz 1'in idempotency kriteri imkânsız hale
gelir. Filtreleme adaptörün işidir, çağıranın değil — çağıranın unutabileceği bir kural,
kural değildir.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

#: Bir kline çağrısında istenecek azami bar. Sabit: Binance'in weight tüketimi çağrı
#: başınadır, `limit`ten bağımsız (Spike 1: 100 de olsa 1000 de olsa weight 2). Daha
#: küçük sayfa istemek saf kayıp.
SAYFA_BOYU = 1000


class BorsaHatasi(Exception):
    """Borsa katmanının dışarı verdiği tek hata tipi.

    Kütüphaneye özgü istisnalar (ccxt) burada sarılır: üst katmanlar `ccxt` import
    etmek zorunda kalmasın, ve borsa değiştiğinde hata yakalayan kod değişmesin.
    """


@dataclass(frozen=True, slots=True)
class SembolKurallari:
    """Bir sembolün emir kuralları. Faz 7'nin ön koşulu, Faz 1'de yalnızca kaydedilir.

    Spike 1'de BTCUSDT için ölçülen: tick 0,01 · step 0,00001 · minNotional 5,00.
    """

    sembol: str
    tick_size: float
    step_size: float
    min_notional: float
    durum: str


class BorsaAdaptoru(ABC):
    """Tarihsel veri için borsa sözleşmesi."""

    @abstractmethod
    def sunucu_zamani_ms(self) -> int:
        """Borsanın kendi saati, UTC epoch ms.

        Yerel saat kullanılmaz: kapanmışlık kararı (K-015/1) borsanın saatine göre
        verilir. Spike 1 yerel saatin sunucudan −153 ms geride olduğunu ölçtü; yanlış
        yönde bir sapma kapanmamış barı kapanmış sayardı.
        """

    @abstractmethod
    def klines(self, sembol: str, timeframe: str, baslangic_ms: int, bitis_ms: int) -> pd.DataFrame:
        """`[baslangic_ms, bitis_ms)` aralığından en fazla `SAYFA_BOYU` **kapanmış** bar.

        Sayfalama çağıranın işidir: dönen son barın `open_time`'ından sonrasını istemek
        için tekrar çağrılır. Boş DataFrame "bu aralıkta veri yok" demektir.

        Dönen sütunlar `HAM_BAR_SUTUNLARI`; kalite bayrağı **yok** — bayrak doğrulama
        katmanının kararıdır (K-006), borsanın beyanı değil.
        """

    @abstractmethod
    def sembol_kurallari(self, sembol: str) -> SembolKurallari:
        """Emir kuralları (tick, step, minNotional). Önbelleklenmesi beklenir."""
