"""Bar olmayan gözlemler için point-in-time depo: `available_time` kesmesi. (K-052/5, Faz 9)

Bar bir zaman ızgarasında yaşar ve kapandığı an bilinir. Makro veri, funding, listeleme
duyurusu, haber bir ızgarada yaşamaz: **olayın zamanı** ile **bilindiği zaman** farklıdır.
Mart enflasyonu (event) Nisan ortasında açıklanır (available), sonra revize edilir (ikinci
available). Bir backtest Mart sonunda o sayıyı görürse, henüz açıklanmamış veriyi kullanmıştır.

**Kesme kuralı tek satır: `available_time_ms <= t`.** `event_time`e göre kesmek bu projede
yasak ve bu bir söz değil, bir test: `kesme_sozlesmesini_dogrula` her kesici uygulamayı
event ≤ t < available olan kayıtların bulunduğu bir fixture'la sınar; event_time'a göre kesen
bir uygulama bu testte **kalır** (`tests/unit/test_pit.py`).

**Gün çözünürlüklü available_time gün sonuna yuvarlanır** (UTC 23:59:59.999). ALFRED
vintage'ları gün verir, saat vermez. Günün başına yuvarlamak, o gün açıklanan sayıyı günün
ilk saatinde kullanmaktır; K-007'nin *"belirsizlikte aleyhte"* ilkesi zaman ekseninde budur.

**Revizyon silinmez, üstüne eklenir.** Aynı `event_time` için birden çok kayıt olabilir; t
anında görünen, `available_time <= t` olanların **en son açıklananı**dır. Eski değer depoda
kalır: geçmişteki bir t'de görülen değer, sonradan revize edildi diye değişmemeli.

**Kaynak kısıtı:** `ingested_time` bizim veriyi aldığımız an. Geçmişe dönük indirilen bir
kaynakta available_time'ı kaynağın kendisi vermiyorsa, ingested_time'dan erken bir
available_time **uydurulmaz**; kaynak sözleşmesi bunu `available_time_kaynagi` alanında
söyler (`data/sozlesme.py`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scryne_quant.common.zaman import utc_str

GUN_MS: Final = 86_400_000

#: Depo şeması. Sıra kimliğin parçası (K-009): değiştirilmez.
GOZLEM_SEMASI: Final[pa.Schema] = pa.schema(
    [
        pa.field("seri", pa.string(), nullable=False),
        pa.field("event_time_ms", pa.int64(), nullable=False),
        pa.field("available_time_ms", pa.int64(), nullable=False),
        pa.field("ingested_time_ms", pa.int64(), nullable=False),
        pa.field("effective_from_ms", pa.int64(), nullable=True),
        pa.field("effective_to_ms", pa.int64(), nullable=True),
        pa.field("deger", pa.float64(), nullable=False),
    ]
)
SUTUNLAR: Final[tuple[str, ...]] = tuple(f.name for f in GOZLEM_SEMASI)


class PitHatasi(ValueError):
    """PIT sözleşmesinin ihlali."""


def gun_sonu_ms(gun: dt.date) -> int:
    """Günün UTC son milisaniyesi: gün çözünürlüklü available_time buraya yuvarlanır."""
    bas = dt.datetime(gun.year, gun.month, gun.day, tzinfo=dt.UTC)
    return int(bas.timestamp() * 1000) + GUN_MS - 1


@dataclass(frozen=True, slots=True)
class Gozlem:
    seri: str
    event_time_ms: int
    available_time_ms: int
    ingested_time_ms: int
    deger: float
    effective_from_ms: int | None = None
    effective_to_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.seri:
            raise PitHatasi("seri adı boş olamaz")
        if self.available_time_ms < self.event_time_ms:
            raise PitHatasi(
                f"{self.seri}: available_time ({utc_str(self.available_time_ms)}) event_time'dan "
                f"({utc_str(self.event_time_ms)}) önce olamaz — olay olmadan bilinemez"
            )
        if (
            self.effective_from_ms is not None
            and self.effective_to_ms is not None
            and self.effective_to_ms <= self.effective_from_ms
        ):
            raise PitHatasi(f"{self.seri}: effective_to effective_from'dan sonra olmalı")

    @classmethod
    def gun_cozunurluklu(
        cls,
        seri: str,
        *,
        event_gunu: dt.date,
        available_gunu: dt.date,
        ingested_time_ms: int,
        deger: float,
    ) -> Gozlem:
        """Event ve available yalnızca gün olarak biliniyorsa: **ikisi de gün sonu.**

        Event'in gün sonu olması kesmeyi etkilemez (kesme available'a bakar) ama
        `available >= event` sözleşmesini aynı gün açıklanan veride korur.
        """
        return cls(
            seri=seri,
            event_time_ms=gun_sonu_ms(event_gunu),
            available_time_ms=gun_sonu_ms(available_gunu),
            ingested_time_ms=ingested_time_ms,
            deger=deger,
        )

    def satir(self) -> dict[str, Any]:
        return {s: getattr(self, s) for s in SUTUNLAR}


def tablo(gozlemler: list[Gozlem]) -> pd.DataFrame:
    """Gözlemler → kanonik sıralı DataFrame. Aynı (seri, event, available) iki kez gelirse
    **son** gelen tutulur (yeniden indirme)."""
    if not gozlemler:
        return pd.DataFrame({s: pd.Series(dtype="object") for s in SUTUNLAR})
    df = pd.DataFrame([g.satir() for g in gozlemler], columns=list(SUTUNLAR))
    return _kanonik(df)


def _kanonik(df: pd.DataFrame) -> pd.DataFrame:
    anahtar = ["seri", "event_time_ms", "available_time_ms"]
    return (
        df.drop_duplicates(subset=anahtar, keep="last")
        .sort_values(anahtar, kind="stable")
        .reset_index(drop=True)
        .astype(
            {"event_time_ms": "int64", "available_time_ms": "int64", "ingested_time_ms": "int64"}
        )
    )


def kes(df: pd.DataFrame, t_ms: int, *, effective: bool = False) -> pd.DataFrame:
    """t anında **bilinen** görünüm: her (seri, event_time) için `available_time <= t` olan en
    son revizyon. `effective=True` ise yalnızca t'de yürürlükte olanlar
    (`effective_from <= t < effective_to`, boş uçlar sınırsız)."""
    bilinen = df[df["available_time_ms"] <= t_ms]
    if effective and not bilinen.empty:
        bas = bilinen["effective_from_ms"]
        bit = bilinen["effective_to_ms"]
        bilinen = bilinen[(bas.isna() | (bas <= t_ms)) & (bit.isna() | (t_ms < bit))]
    son = bilinen.sort_values(["seri", "event_time_ms", "available_time_ms"], kind="stable")
    return son.drop_duplicates(subset=["seri", "event_time_ms"], keep="last").reset_index(drop=True)


Kesici = Callable[[pd.DataFrame, int], pd.DataFrame]


def kesme_sozlesmesini_dogrula(kesici: Kesici) -> None:
    """Bir kesici uygulamanın `available_time` sözleşmesine uyduğunu sınar; uymuyorsa hata.

    Fixture üç tuzak taşır: (1) event ≤ t < available — açıklanmamış veri; (2) aynı event'in
    t'den sonra açıklanan revizyonu; (3) t'de tam açıklanan kayıt (sınır dahil olmalı).
    """
    t = 1_700_000_000_000
    saat = 3_600_000
    ornek = tablo(
        [
            Gozlem("cpi", t - 30 * GUN_MS, t - 10 * GUN_MS, t, 3.0),  # bilinen
            Gozlem("cpi", t - 30 * GUN_MS, t + saat, t, 3.4),  # (2) sonra revize
            Gozlem("cpi", t - 2 * GUN_MS, t + 5 * GUN_MS, t, 9.9),  # (1) açıklanmamış
            Gozlem("cpi", t - GUN_MS, t, t, 4.0),  # (3) tam t'de açıklandı
        ]
    )
    sonuc = kesici(ornek, t)
    gorunen = sorted(zip(sonuc["event_time_ms"], sonuc["deger"], strict=True))
    beklenen = [(t - 30 * GUN_MS, 3.0), (t - GUN_MS, 4.0)]
    if gorunen != beklenen:
        raise PitHatasi(
            f"kesici available_time sözleşmesine uymuyor: beklenen {beklenen}, görünen {gorunen}"
        )


class GozlemDeposu:
    """`<kok>/<kaynak>/<seri>.parquet`. Ekleme idempotent; revizyonlar korunur."""

    def __init__(self, kok: str | Path) -> None:
        self.kok = Path(kok)

    def yol(self, kaynak: str, seri: str) -> Path:
        if "/" in seri or "\\" in seri or "/" in kaynak or "\\" in kaynak:
            raise PitHatasi("kaynak/seri adında yol ayırıcı olamaz")
        return self.kok / kaynak / f"{seri}.parquet"

    def oku(self, kaynak: str, seri: str) -> pd.DataFrame:
        yol = self.yol(kaynak, seri)
        if not yol.exists():
            raise PitHatasi(f"depoda yok: {kaynak}/{seri}")
        return _kanonik(pq.read_table(yol).to_pandas())

    def ekle(self, kaynak: str, gozlemler: list[Gozlem]) -> dict[str, int]:
        """Seri başına eklenen **yeni** satır sayısı. Aynı kayıt tekrar gelirse 0."""
        out: dict[str, int] = {}
        for seri in sorted({g.seri for g in gozlemler}):
            yeni = tablo([g for g in gozlemler if g.seri == seri])
            yol = self.yol(kaynak, seri)
            onceki = self.oku(kaynak, seri) if yol.exists() else yeni.iloc[0:0]
            birlesik = _kanonik(pd.concat([onceki, yeni], ignore_index=True))
            out[seri] = len(birlesik) - len(onceki)
            if out[seri] == 0 and birlesik.equals(onceki):
                continue
            yol.parent.mkdir(parents=True, exist_ok=True)
            gecici = yol.with_suffix(".parquet.tmp")
            pq.write_table(
                pa.Table.from_pandas(birlesik, schema=GOZLEM_SEMASI, preserve_index=False),
                gecici,
                compression="zstd",
                compression_level=3,
            )
            gecici.replace(yol)
        return out


__all__ = [
    "GOZLEM_SEMASI",
    "Gozlem",
    "GozlemDeposu",
    "PitHatasi",
    "gun_sonu_ms",
    "kes",
    "kesme_sozlesmesini_dogrula",
    "tablo",
]
