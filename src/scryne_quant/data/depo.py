"""Parquet deposu: sembol/timeframe başına tek dosya, zstd. (K-011, K-009)

Bu modülün tek işi **aynı veriyi her zaman aynı baytlara yazmak.** Faz 1'in idempotency
kriteri (aynı komut iki kez → dosya bit düzeyinde aynı) buraya dayanıyor.

Spike 3'ün ölçtükleri:
- PyArrow'un Parquet çıktısı deterministik; dosya SHA-256'sı veri seti kimliği olabilir.
- zstd seçildi: 525k bar için 14,21 MB / 0,190 s yazma / 0,022 s okuma. brotli %17 daha
  küçük ama 12 kat yavaş yazıyor; snappy %30 daha büyük.
- Tek dosya, bölümlemeye tercih edildi: bölümleme bu ölçekte %18 *daha çok* yer kaplıyor
  ve kazandırdığı 11 ms hissedilmiyor.

Determinizm için burada bilinçli olarak yapılanlar — her biri, atlanırsa hash'i sessizce
değiştirecek bir kaynağı kapatıyor:

1. **pandas metadata'sı yazılmaz.** `Table.from_pandas` dosyaya pandas sürümünü ve index
   bilgisini gömer; pandas güncellenince aynı veri farklı hash verir. Bunun yerine
   sütunlardan açık şemayla Arrow tablosu kuruluyor.
2. **Sıkıştırma seviyesi açıkça veriliyor.** Kütüphane varsayılanı sürümle değişebilir.
3. **`row_group_size` sabit.** Varsayılanı da sürümle değişebilir ve dosya düzenini
   etkiler.
4. **Satırlar `open_time`'a göre sıralı ve tekil.** Gelen sıra dosyaya sızmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scryne_quant.common.hash import dosya_hash
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.semalar import BAR_SEMASI, BAR_SUTUNLARI, PANDAS_DTYPES

#: Determinizm için sabitlenen yazım parametreleri. Değiştirilirse mevcut tüm dosyaların
#: hash'i değişir — yani bu satırlar bir karar, ayar değil.
SIKISTIRMA = "zstd"
SIKISTIRMA_SEVIYESI = 3
ROW_GROUP_SATIR = 122_880
PARQUET_SURUMU = "2.6"


class DepoHatasi(Exception):
    """Depo sözleşmesinin ihlali."""


@dataclass(frozen=True, slots=True)
class DepoKaydi:
    """Bir yazımın sonucu. Sonuç kaydına (K-009) bu bilgiler gider."""

    yol: Path
    bar_sayisi: int
    ilk_ms: int
    son_ms: int
    sha256: str
    bayt: int


class ParquetDepo:
    """Tarihsel bar deposu.

    Düzen: ``<kok>/<sembol>/<timeframe>.parquet`` — sembol/timeframe başına tek dosya.
    """

    def __init__(self, kok: str | Path) -> None:
        self.kok = Path(kok)

    # ---------------------------------------------------------------- yollar

    def yol(self, sembol: str, timeframe: str) -> Path:
        """Bir sembol/timeframe çiftinin dosya yolu."""
        timeframe_ms(timeframe)  # tanınmayan timeframe burada patlasın, yazarken değil
        return self.kok / sembol.upper() / f"{timeframe}.parquet"

    def var_mi(self, sembol: str, timeframe: str) -> bool:
        return self.yol(sembol, timeframe).exists()

    # ------------------------------------------------------------ normalize

    @staticmethod
    def normalize(df: pd.DataFrame) -> pd.DataFrame:
        """Gelen DataFrame'i kanonik biçime sokar.

        Bu fonksiyon idempotency'nin kalbi: aynı barlar hangi sırayla, hangi dtype'la,
        kaç parça hâlinde gelirse gelsin buradan **tek bir** biçimde çıkar.

        Tekilleştirmede **son** kayıt tutulur: aynı timestamp iki kez geldiyse sonraki
        çağrı daha güncel veridir (ör. yeniden indirilen bir aralık).
        """
        eksik = [s for s in BAR_SUTUNLARI if s not in df.columns]
        if eksik:
            raise DepoHatasi(f"eksik sütun(lar): {', '.join(eksik)}")

        out = df.loc[:, list(BAR_SUTUNLARI)].copy()

        for sutun, dtype in PANDAS_DTYPES.items():
            out[sutun] = out[sutun].astype(dtype)

        if out["open_time"].isna().any():
            raise DepoHatasi("open_time boş olamaz")

        out = (
            out.drop_duplicates(subset="open_time", keep="last")
            .sort_values("open_time", kind="stable")
            .reset_index(drop=True)
        )
        return out

    @staticmethod
    def _arrow(df: pd.DataFrame) -> pa.Table:
        """Kanonik DataFrame → Arrow tablosu, pandas metadata'sı olmadan.

        `pa.Table.from_pandas` kullanılmıyor: o, dosyaya pandas sürümünü ve index
        şemasını gömer ve pandas güncellendiğinde aynı verinin hash'i değişir.
        """
        diziler = [
            pa.array(df[alan.name].to_numpy(), type=alan.type)
            if alan.type != pa.string()
            else pa.array(df[alan.name].astype("object").tolist(), type=alan.type)
            for alan in BAR_SEMASI
        ]
        return pa.Table.from_arrays(diziler, schema=BAR_SEMASI)

    # -------------------------------------------------------------- yaz/oku

    def yaz(self, sembol: str, timeframe: str, df: pd.DataFrame) -> DepoKaydi:
        """Barları yazar (mevcut dosyanın üzerine). Kanonikleştirme burada yapılır.

        Kısmi yazım bırakmamak için önce geçici dosyaya yazılıp sonra yerine taşınıyor:
        yazım ortasında kesilen bir süreç, yarım bir parquet dosyası bırakmamalı.
        """
        kanonik = self.normalize(df)
        if kanonik.empty:
            raise DepoHatasi("boş DataFrame yazılamaz")

        hedef = self.yol(sembol, timeframe)
        hedef.parent.mkdir(parents=True, exist_ok=True)
        gecici = hedef.with_suffix(".parquet.tmp")

        pq.write_table(
            self._arrow(kanonik),
            gecici,
            compression=SIKISTIRMA,
            compression_level=SIKISTIRMA_SEVIYESI,
            row_group_size=ROW_GROUP_SATIR,
            version=PARQUET_SURUMU,
            write_statistics=True,
            store_schema=True,
        )
        gecici.replace(hedef)

        return DepoKaydi(
            yol=hedef,
            bar_sayisi=len(kanonik),
            ilk_ms=int(kanonik["open_time"].iloc[0]),
            son_ms=int(kanonik["open_time"].iloc[-1]),
            sha256=dosya_hash(hedef),
            bayt=hedef.stat().st_size,
        )

    def oku(self, sembol: str, timeframe: str) -> pd.DataFrame:
        """Barları okur. Dosya yoksa hata verir — sessizce boş dönmez."""
        yol = self.yol(sembol, timeframe)
        if not yol.exists():
            raise DepoHatasi(f"depoda yok: {sembol} {timeframe} ({yol})")
        df = pq.read_table(yol).to_pandas()
        for sutun, dtype in PANDAS_DTYPES.items():
            df[sutun] = df[sutun].astype(dtype)
        return df

    def birlestir(self, sembol: str, timeframe: str, yeni: pd.DataFrame) -> DepoKaydi:
        """Mevcut veriyle birleştirip yazar. İndiricinin "kaldığı yerden devam"ı bunu kullanır.

        Çakışan timestamp'lerde yeni veri kazanır (`normalize`'ın `keep="last"` kuralı).
        Sonuç, mevcut + yeni birleşiminin kanonik hâlidir — yani aynı aralık kaç kez
        indirilirse indirilsin dosya aynı kalır.
        """
        if self.var_mi(sembol, timeframe):
            mevcut = self.oku(sembol, timeframe)
            birlesik = pd.concat([mevcut, self.normalize(yeni)], ignore_index=True)
        else:
            birlesik = yeni
        return self.yaz(sembol, timeframe, birlesik)

    # ---------------------------------------------------------------- kimlik

    def sha256(self, sembol: str, timeframe: str) -> str:
        """Veri seti kimliği (K-009). Sonuç kaydına bu değer yazılır."""
        yol = self.yol(sembol, timeframe)
        if not yol.exists():
            raise DepoHatasi(f"depoda yok: {sembol} {timeframe} ({yol})")
        return dosya_hash(yol)
