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

import pandas as pd

from scryne_quant.exchange.hatalar import BorsaHatasi
from scryne_quant.exchange.kurallar import SembolKurallari

#: Bir kline çağrısında istenecek azami bar. Sabit: Binance'in weight tüketimi çağrı
#: başınadır, `limit`ten bağımsız (Spike 1: 100 de olsa 1000 de olsa weight 2). Daha
#: küçük sayfa istemek saf kayıp.
SAYFA_BOYU = 1000


#: `BorsaHatasi` Faz 7'de `exchange/hatalar.py`ye taşındı ve burada yeniden dışa
#: veriliyor. Sebep: emir yolundaki kod (`oms/`, `execution/`) bu hatayı yakalamak
#: zorunda, ama bu modül pandas'a bağlı ve o paketlerde pandas yasak
#: (`test_risk_bypass.py`). Mevcut `from ...temel import BorsaHatasi` importları
#: kırılmasın diye isim burada duruyor.


#: `SembolKurallari` de Faz 7'de taşındı (`exchange/kurallar.py`) — aynı gerekçe:
#: emir yolu onu kullanmak zorunda, bu modül pandas taşıyor.


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


__all__ = ["SAYFA_BOYU", "BorsaAdaptoru", "BorsaHatasi", "SembolKurallari"]
