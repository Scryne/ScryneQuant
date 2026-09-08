"""Bar şeması ve kalite bayrakları. (K-005, K-006)

Şema **tek yerde** tanımlıdır ve depoya yazılan her şey buradan geçer. Sebep: dosyanın
SHA-256'sı veri seti kimliğidir (K-009), ve sütun sırası ya da dtype'ı değişen bir yazım
aynı veriye farklı kimlik verir. Şemayı serbest bırakmak, kimliği serbest bırakmaktır.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

import pyarrow as pa


class KaliteDurumu(StrEnum):
    """Bir barın doğrulama durumu. (K-006)

    `ok` dışındaki barlar backtest'te **sessizce kullanılmaz**; oranı sonuç kaydına
    yazılır ve eşiği aşarsa sonuç promotion'a giremez.
    """

    OK = "ok"
    """Doğrulamalardan geçti."""

    GAP = "gap"
    """Öncesinde eksik bar var."""

    DUPLICATE = "duplicate"
    """Aynı timestamp tekrar geldi, tekilleştirildi."""

    SUSPECT = "suspect"
    """Aykırı hareket / sıfır hacim / OHLC tutarsızlığı."""

    BACKFILLED = "backfilled"
    """Sonradan tamamlandı, birincil akıştan gelmedi."""


#: Depoya yazılan barların sütun sırası. Sıra kimliğin parçasıdır — değiştirilmez.
BAR_SUTUNLARI: Final[tuple[str, ...]] = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trades",
    "quality_status",
)

#: Arrow şeması. Açıkça yazılıyor çünkü pandas'ın dtype çıkarımına güvenmek, pandas
#: sürümü değiştiğinde dosya hash'inin sessizce değişmesi demek olurdu.
BAR_SEMASI: Final[pa.Schema] = pa.schema(
    [
        # Bar açılış zamanı, UTC epoch milisaniye (K-005). Kapanış değil, açılış.
        pa.field("open_time", pa.int64(), nullable=False),
        pa.field("open", pa.float64(), nullable=False),
        pa.field("high", pa.float64(), nullable=False),
        pa.field("low", pa.float64(), nullable=False),
        pa.field("close", pa.float64(), nullable=False),
        pa.field("volume", pa.float64(), nullable=False),
        pa.field("quote_volume", pa.float64(), nullable=False),
        pa.field("trades", pa.int64(), nullable=False),
        # Kalite bayrağı bar başına saklanır: backtest hangi barın şüpheli olduğunu
        # çalışma anında bilmek zorunda (K-006), sonradan türetmek zorunda değil.
        pa.field("quality_status", pa.string(), nullable=False),
    ]
)

#: pandas dtype karşılıkları — okuma tarafında tip kaymasını engellemek için.
PANDAS_DTYPES: Final[dict[str, str]] = {
    "open_time": "int64",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "float64",
    "quote_volume": "float64",
    "trades": "int64",
    "quality_status": "string",
}
