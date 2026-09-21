"""FXCM MarketData M1 → 1h FX deposu. (K-087/K-088, ROADMAP-RESET R3 Paket 1(a))

Kaynak: `https://candledata.fxcorporate.com/m1/{PAIR}/{yıl}/{hafta}.csv.gz` — README'de
yayımlanmış doğrudan URL, hesap/anahtar yok, "personal use / EULA" (K-088). Haftalık dosya
Pazar→Cuma, damga **UTC** (ölçüldü: ABD yaz saatinde açılış 22:00'den 21:00'e kayıyor), bid ve
ask OHLC, **volume yok**, tick'siz dakika satırı yok.

Bu modül kripto yolundan (`ParquetDepo`, `data/market`, `data/evren`) **bağımsızdır** ve onu
değiştirmez: FX bar şeması farklı (bid+ask, hacimsiz), o yüzden aynı depoya sokulmaz. Sağlayıcı
soyutlaması yok — tek kaynak, tek biçim, kanıtı burada.

Determinizm (K-009): Parquet `ParquetDepo` ile aynı yazım parametreleriyle (zstd/3, sabit
row group, pandas metadata'sız, açık şema) yazılır; satırlar `open_time`a göre sıralı ve tekil;
manifesto `json.dumps(sort_keys=True)`. Aynı komut iki kez → aynı baytlar.

Veri sonu (K-080): `bitis_gun` verilirse o günden sonraki Pazar'la başlayan haftalar
indirilmez, depodaki barlar `open_time < (gün+1) 00:00 UTC` ile kırpılır; uzatmak da geri
sarmak da aynı komut. Manifesto `veri_sonu`nu (son barın açılışı) ve `bitis_gun`u taşır.

**Üretilmeyen:** mid/tek fiyat, spread, `trades`, kalite bayrağı — bunlar R4 kararı (K-007
"aleyhte" orada uygulanır) ve Paket 1(c). Bu katman yalnız kaynağın verdiğini, kaybetmeden ve
uydurmadan, saatlik ızgaraya taşır.
"""

from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scryne_quant.common.hash import dosya_hash
from scryne_quant.common.zaman import timeframe_ms, utc_str
from scryne_quant.data.depo import (
    PARQUET_SURUMU,
    ROW_GROUP_SATIR,
    SIKISTIRMA,
    SIKISTIRMA_SEVIYESI,
)
from scryne_quant.data.sozlesme import FX_BAR_SUTUNLARI

KAYNAK_KOK: Final = "https://candledata.fxcorporate.com"
VARSAYILAN_DEPO: Final = Path("data/fx")
GELEN_DIZINI: Final = "_gelen"
TIMEFRAME: Final = "1h"

#: Kaynağın sabit başlığı — farklı gelirse dosya reddedilir (şema sessizce değişmez).
KAYNAK_BASLIK: Final = (
    "DateTime,BidOpen,BidHigh,BidLow,BidClose,AskOpen,AskHigh,AskLow,AskClose"
)
_DAMGA: Final = re.compile(r"^(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2}):(\d{2})\.(\d{3})$")
_PAIR: Final = re.compile(r"^[A-Z]{6}$")
_GUN: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SAAT_MS: Final = timeframe_ms(TIMEFRAME)
DAKIKA_MS: Final = 60_000

FX_SEMASI: Final = pa.schema(
    [
        ("open_time", pa.int64()),
        ("bid_open", pa.float64()),
        ("bid_high", pa.float64()),
        ("bid_low", pa.float64()),
        ("bid_close", pa.float64()),
        ("ask_open", pa.float64()),
        ("ask_high", pa.float64()),
        ("ask_low", pa.float64()),
        ("ask_close", pa.float64()),
        ("m1_sayisi", pa.int64()),
    ]
)
assert tuple(FX_SEMASI.names) == FX_BAR_SUTUNLARI

Indirici = Callable[[str], bytes | None]
"""URL → gövde; kaynak 404 dönerse `None`. Ağ katmanı test edilebilsin diye enjekte edilir."""


class FxHatasi(ValueError):
    """FX kaynak dosyası ya da depo sözleşmesi ihlali."""


# ------------------------------------------------------------------ hafta numarası (K-088)


def hafta_no(pazar: dt.date) -> tuple[int, int]:
    """FXCM dosya anahtarı `(yıl, hafta)`: yıl Pazar'ın yılı; 1 Ocak'ı içeren hafta 1.

    `%U` Pazar'dan başlayan hafta sayısıdır ve 1 Ocak'tan önceki günleri hafta 0 sayar; yıl
    Pazar'la başlamıyorsa o "hafta 0" FXCM'de hafta 1'dir (2024-01-07 → 2, 2024-03-03 → 10;
    2023-12-31 → 2023/53 — ölçüldü, K-088).
    """
    if pazar.weekday() != 6:
        raise FxHatasi(f"{pazar}: Pazar değil")
    u = int(pazar.strftime("%U"))
    ocak_u = int(dt.date(pazar.year, 1, 1).strftime("%U"))
    return pazar.year, u + (1 if ocak_u == 0 else 0)


def pazarlar(bas: dt.date, bit: dt.date) -> Iterator[dt.date]:
    """`bas`ı içeren haftadan `bit`i içeren haftaya kadar her haftanın Pazar'ı."""
    if bit < bas:
        raise FxHatasi(f"aralık ters: {bas} > {bit}")
    p = bas - dt.timedelta(days=(bas.weekday() + 1) % 7)
    son = bit - dt.timedelta(days=(bit.weekday() + 1) % 7)
    while p <= son:
        yield p
        p += dt.timedelta(days=7)


def dosya_url(pair: str, yil: int, hafta: int) -> str:
    return f"{KAYNAK_KOK}/m1/{pair}/{yil}/{hafta}.csv.gz"


# ------------------------------------------------------------------ okuma / dönüşüm


def _damga_ms(metin: str) -> int:
    e = _DAMGA.match(metin)
    if e is None:
        raise FxHatasi(f"zaman damgası biçimi dışı: {metin!r} (beklenen MM/DD/YYYY HH:MM:SS.mmm)")
    ay, gun, yil, sa, dk, sn, ms = (int(x) for x in e.groups())
    t = dt.datetime(yil, ay, gun, sa, dk, sn, ms * 1000, tzinfo=dt.UTC)
    return int(t.timestamp() * 1000)


def m1_oku(govde: bytes, *, ad: str = "") -> pd.DataFrame:
    """Haftalık `.csv.gz` gövdesi → M1 çerçevesi (`open_time` UTC ms + bid/ask OHLC).

    Başlık kaynağın sabit başlığıyla birebir olmalı; satırlar artan ve tekil olmalı; fiyatlar
    pozitif ve `low ≤ open/close ≤ high`. Sapma → `FxHatasi` (uydurma/onarım yok).
    """
    try:
        metin = gzip.decompress(govde).decode("utf-8")
    except (OSError, UnicodeDecodeError) as hata:
        raise FxHatasi(f"{ad}: gzip/utf-8 çözülemedi: {hata}") from hata
    satirlar = metin.splitlines()
    if not satirlar or satirlar[0].strip() != KAYNAK_BASLIK:
        raise FxHatasi(f"{ad}: başlık beklenen değil: {satirlar[:1]!r}")
    if len(satirlar) == 1:
        raise FxHatasi(f"{ad}: veri satırı yok")
    df = pd.read_csv(
        io.StringIO("\n".join(satirlar[1:])),
        header=None,
        names=["damga", *FX_BAR_SUTUNLARI[1:9]],
        dtype={s: "float64" for s in FX_BAR_SUTUNLARI[1:9]},
    )
    df["open_time"] = np.array([_damga_ms(str(d)) for d in df["damga"]], dtype="int64")
    df = df.drop(columns=["damga"])
    zaman = df["open_time"].to_numpy()
    if (np.diff(zaman) <= 0).any():
        raise FxHatasi(f"{ad}: satırlar artan/tekil değil")
    if (zaman % DAKIKA_MS != 0).any():
        raise FxHatasi(f"{ad}: dakika ızgarasına oturmayan damga var")
    for on in ("bid", "ask"):
        o, h, lo, c = (df[f"{on}_{k}"].to_numpy() for k in ("open", "high", "low", "close"))
        if (o <= 0).any() or (lo <= 0).any():
            raise FxHatasi(f"{ad}: pozitif olmayan {on} fiyatı")
        if (lo > np.minimum(o, c)).any() or (h < np.maximum(o, c)).any():
            raise FxHatasi(f"{ad}: {on} OHLC tutarsız (low ≤ open/close ≤ high değil)")
    return df.loc[:, list(FX_BAR_SUTUNLARI[:9])].reset_index(drop=True)


def saatlik(m1: pd.DataFrame) -> pd.DataFrame:
    """M1 → 1h: bar açılışı saat başı (K-005); bid ve ask ayrı ayrı ilk/maks/min/son; `m1_sayisi`.

    Deterministik: girdi `open_time`a göre sıralı, gruplama sıralı; boş saat üretilmez (tick'siz
    saat = bar yok; takvim/`gap` yorumu R4).
    """
    if m1.empty:
        return pd.DataFrame({ad: pd.Series(dtype=t) for ad, t in _PANDAS_DTYPES.items()})
    saat = (m1["open_time"] // SAAT_MS) * SAAT_MS
    g = m1.groupby(saat, sort=True)
    out = pd.DataFrame(
        {
            "open_time": np.asarray(list(g.groups.keys()), dtype="int64"),
            "bid_open": g["bid_open"].first().to_numpy(),
            "bid_high": g["bid_high"].max().to_numpy(),
            "bid_low": g["bid_low"].min().to_numpy(),
            "bid_close": g["bid_close"].last().to_numpy(),
            "ask_open": g["ask_open"].first().to_numpy(),
            "ask_high": g["ask_high"].max().to_numpy(),
            "ask_low": g["ask_low"].min().to_numpy(),
            "ask_close": g["ask_close"].last().to_numpy(),
            "m1_sayisi": g.size().to_numpy().astype("int64"),
        }
    )
    return out


_PANDAS_DTYPES: Final = {
    ad: ("int64" if t == pa.int64() else "float64")
    for ad, t in zip(FX_SEMASI.names, FX_SEMASI.types, strict=True)
}


# ------------------------------------------------------------------ depo


@dataclass(frozen=True, slots=True)
class FxKaydi:
    pair: str
    yol: Path
    bar_sayisi: int
    ilk_ms: int | None
    son_ms: int | None
    sha256: str | None
    haftalar: dict[str, dict[str, Any]]
    """`"YYYY-W"` → `{sha256, satir, ilk_ms, son_ms}` ya da `{"durum": "yok"}` (404)."""
    bitis_gun: str | None

    def sozluk(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "timeframe": TIMEFRAME,
            "kaynak": "fxcm-candledata-m1",
            "bar_sayisi": self.bar_sayisi,
            "ilk_ms": self.ilk_ms,
            "son_ms": self.son_ms,
            "ilk": utc_str(self.ilk_ms) if self.ilk_ms is not None else None,
            "son": utc_str(self.son_ms) if self.son_ms is not None else None,
            "veri_sonu": utc_str(self.son_ms) if self.son_ms is not None else None,
            "sha256": self.sha256,
            "bitis_gun": self.bitis_gun,
            "haftalar": {k: self.haftalar[k] for k in sorted(self.haftalar)},
        }


class FxDepo:
    """`data/fx/<PAIR>/1h.parquet` + `1h.kaynak.json`; gelen haftalık dosyalar `_gelen/<PAIR>/`."""

    def __init__(self, kok: str | Path = VARSAYILAN_DEPO) -> None:
        self.kok = Path(kok)

    # yollar
    def parquet_yolu(self, pair: str) -> Path:
        return self.kok / pair / f"{TIMEFRAME}.parquet"

    def manifesto_yolu(self, pair: str) -> Path:
        return self.kok / pair / f"{TIMEFRAME}.kaynak.json"

    def gelen_yolu(self, pair: str, yil: int, hafta: int) -> Path:
        return self.kok / GELEN_DIZINI / pair / f"{yil}-{hafta}.csv.gz"

    # okuma
    def oku(self, pair: str) -> pd.DataFrame:
        yol = self.parquet_yolu(pair)
        if not yol.exists():
            raise FxHatasi(f"{pair}: depoda yok ({yol})")
        return pq.read_table(yol, schema=FX_SEMASI).to_pandas()

    def manifesto(self, pair: str) -> dict[str, Any] | None:
        yol = self.manifesto_yolu(pair)
        if not yol.exists():
            return None
        return json.loads(yol.read_text(encoding="utf-8"))

    # yazma
    def _yaz(self, pair: str, df: pd.DataFrame, haftalar: dict[str, Any], bitis_gun: str | None
             ) -> FxKaydi:
        df = df.sort_values("open_time").drop_duplicates("open_time").reset_index(drop=True)
        hedef = self.parquet_yolu(pair)
        hedef.parent.mkdir(parents=True, exist_ok=True)
        if df.empty:
            if hedef.exists():
                hedef.unlink()
            kayit = FxKaydi(pair, hedef, 0, None, None, None, haftalar, bitis_gun)
        else:
            tablo = pa.Table.from_arrays(
                [
                    pa.array(df[ad].to_numpy(), type=t)
                    for ad, t in zip(FX_SEMASI.names, FX_SEMASI.types, strict=True)
                ],
                schema=FX_SEMASI,
            )
            gecici = hedef.with_suffix(".parquet.tmp")
            pq.write_table(
                tablo, gecici, compression=SIKISTIRMA, compression_level=SIKISTIRMA_SEVIYESI,
                row_group_size=ROW_GROUP_SATIR, version=PARQUET_SURUMU, write_statistics=True,
                store_schema=True,
            )
            gecici.replace(hedef)
            kayit = FxKaydi(
                pair, hedef, len(df), int(df["open_time"].iloc[0]), int(df["open_time"].iloc[-1]),
                dosya_hash(hedef), haftalar, bitis_gun,
            )
        self.manifesto_yolu(pair).write_text(
            json.dumps(kayit.sozluk(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        return kayit


# ------------------------------------------------------------------ edinim


def _gun(metin: str) -> dt.date:
    if not _GUN.match(metin):
        raise FxHatasi(f"gün YYYY-MM-DD olmalı: {metin!r}")
    return dt.date.fromisoformat(metin)


def _gelen_al(depo: FxDepo, pair: str, yil: int, hafta: int, indirici: Indirici
              ) -> tuple[Path | None, bool]:
    """Haftalık dosyayı `_gelen`e getirir. Döner: (yol | None=404, yeni_indirildi)."""
    yol = depo.gelen_yolu(pair, yil, hafta)
    yok = yol.parent / f"{yil}-{hafta}.yok"
    if yol.exists() and yol.stat().st_size > 0:
        return yol, False
    if yok.exists():
        return None, False
    govde = indirici(dosya_url(pair, yil, hafta))
    yol.parent.mkdir(parents=True, exist_ok=True)
    if govde is None:
        yok.write_text("404\n", encoding="utf-8")
        return None, True
    gecici = yol.with_suffix(".tmp")
    gecici.write_bytes(govde)
    gecici.replace(yol)
    return yol, True


def fx_al(
    pair: str,
    bas_gun: str,
    bit_gun: str,
    *,
    depo: FxDepo | None = None,
    indirici: Indirici,
    bitis_gun: str | None = None,
) -> FxKaydi:
    """`[bas_gun, bit_gun]` aralığındaki haftaları getirir, M1→1h çevirir, depoyu **baştan** yazar.

    İdempotent: gelen dosyalar bir kez indirilir (varsa dokunulmaz, 404 `.yok` ile hatırlanır);
    depo her çağrıda gelen dosyaların tamamından yeniden kurulur — aynı gelen küme → aynı baytlar.
    `bitis_gun` (K-080): sonraki haftalar istenmez, barlar `< gün+1 00:00 UTC` kırpılır.
    """
    if not _PAIR.match(pair):
        raise FxHatasi(f"pair 6 büyük harf olmalı: {pair!r}")
    depo = depo or FxDepo()
    bas, bit = _gun(bas_gun), _gun(bit_gun)
    sinir_ms: int | None = None
    if bitis_gun is not None:
        sinir = _gun(bitis_gun)
        sinir_ms = int(dt.datetime.combine(sinir + dt.timedelta(days=1), dt.time(), tzinfo=dt.UTC)
                       .timestamp() * 1000)
        bit = min(bit, sinir)
    parcalar: list[pd.DataFrame] = []
    haftalar: dict[str, dict[str, Any]] = {}
    for pazar in pazarlar(bas, bit):
        yil, hafta = hafta_no(pazar)
        anahtar = f"{yil}-{hafta}"
        yol, _ = _gelen_al(depo, pair, yil, hafta, indirici)
        if yol is None:
            haftalar[anahtar] = {"durum": "yok", "pazar": pazar.isoformat()}
            continue
        m1 = m1_oku(yol.read_bytes(), ad=yol.name)
        haftalar[anahtar] = {
            "durum": "var", "pazar": pazar.isoformat(), "sha256": dosya_hash(yol),
            "m1_satir": int(len(m1)),
            "ilk_ms": int(m1["open_time"].iloc[0]), "son_ms": int(m1["open_time"].iloc[-1]),
        }
        parcalar.append(m1)
    m1_hepsi = (
        pd.concat(parcalar, ignore_index=True) if parcalar
        else pd.DataFrame(
            {ad: pd.Series(dtype=t) for ad, t in _PANDAS_DTYPES.items() if ad != "m1_sayisi"}
        )
    )
    if not m1_hepsi.empty:
        m1_hepsi = m1_hepsi.sort_values("open_time").reset_index(drop=True)
        if m1_hepsi["open_time"].duplicated().any():
            raise FxHatasi(f"{pair}: haftalar arasında çakışan dakika var")
        if sinir_ms is not None:
            m1_hepsi = m1_hepsi[m1_hepsi["open_time"] < sinir_ms].reset_index(drop=True)
    return depo._yaz(pair, saatlik(m1_hepsi), haftalar, bitis_gun)


def https_indirici(zaman_asimi_s: float = 60.0) -> Indirici:
    """`requests` ile doğrudan GET; 404 → `None`, diğer hata → `FxHatasi`. Tek istek/dosya."""
    import requests

    def al(url: str) -> bytes | None:
        y = requests.get(url, timeout=zaman_asimi_s, headers={"User-Agent": "ScryneQuant/fx"})
        if y.status_code == 404:
            return None
        if y.status_code != 200:
            raise FxHatasi(f"{url}: HTTP {y.status_code}")
        return y.content

    return al


__all__ = [
    "FX_SEMASI",
    "FxDepo",
    "FxHatasi",
    "FxKaydi",
    "KAYNAK_BASLIK",
    "VARSAYILAN_DEPO",
    "dosya_url",
    "fx_al",
    "hafta_no",
    "https_indirici",
    "m1_oku",
    "pazarlar",
    "saatlik",
]
