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
from scryne_quant.data.takvim import TAKVIM_FX_5X24, Takvim, takvim

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

#: FXCM MarketData README'nin candle verisi için saydığı 21 çift (2026-09-21 okundu) — kapalı küme;
#: listede olmayan çift istenmez (sağlayıcı listesi uydurulmaz). HEAD ölçümü: 21'inin tamamında
#: 2012 h1 → 2026 h36 mevcut, 2011 404, 2026 h37+ (yayın gecikmesi ≈ 2 hafta) 404.
FXCM_CIFTLER: Final[tuple[str, ...]] = (
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "CADCHF", "EURAUD", "EURCHF", "EURGBP", "EURJPY",
    "EURUSD", "GBPCHF", "GBPJPY", "GBPNZD", "GBPUSD", "NZDCAD", "NZDCHF", "NZDJPY", "NZDUSD",
    "USDCAD", "USDCHF", "USDJPY",
)
#: Sağlayıcının ilk haftası (ölçüldü: 2012 h1 = 2012-01-01 Pazar; 2011 404).
KAYNAK_BASLANGIC: Final = dt.date(2012, 1, 1)

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
    """FXCM dosya anahtarı `(yıl, hafta)`: yıl Pazar'ın yılı; hafta = `%U(Pazar) + kayma`.

    `%U` Pazar'dan başlayan hafta sayısıdır (1 Ocak'tan önceki günler hafta 0). Kayma **1 Ocak'ın
    gününe** bağlı (K-091, 15 yılın 10. dosyasının başlangıç tarihinden ölçüldü): 1 Ocak
    Pazartesi/Salı/Çarşamba ise 1 (o hafta yılın çoğunluğunu taşır → hafta 1), aksi hâlde 0.
    Örnek: 2024 (Pzt) 01-07 → 2, 03-03 → 10; 2016 (Cum) 01-03 → 1; 2015 (Per) 12-27 → 52;
    2023 (Paz) 12-31 → 53; 2026 (Per) 09-13 → 37. K-088'deki ilk formül (`%U(1 Ocak)==0` → +1)
    Per/Cum/Cmt yıllarında bir hafta kaydırıyordu — o yıllardaki "h53 sağlayıcı boşluğu" artefakttı.
    """
    if pazar.weekday() != 6:
        raise FxHatasi(f"{pazar}: Pazar değil")
    u = int(pazar.strftime("%U"))
    kayma = 1 if dt.date(pazar.year, 1, 1).weekday() in (0, 1, 2) else 0
    return pazar.year, u + kayma


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


def hafta_anahtarlari(pazar: dt.date) -> tuple[tuple[int, int], ...]:
    """Kanonik anahtar + sağlayıcının yıl sınırında kullanabildiği alternatif (K-091).

    Ölçüldü: 31 Aralık 2017 haftası `2018/1` (2017/53 404), 31 Aralık 2023 haftası `2023/53`
    (2024/1 404) — sağlayıcı yıl geçişinde tutarsız. Pazar'ın haftası bir sonraki yılın 1 Ocak'ını
    içeriyorsa `(yıl+1, 1)` alternatif olarak denenir; depo anahtarı hep kanonik kalır.
    """
    kanonik = hafta_no(pazar)
    if pazar + dt.timedelta(days=6) >= dt.date(pazar.year + 1, 1, 1):
        return kanonik, (pazar.year + 1, 1)
    return (kanonik,)


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


def _gelen_al(depo: FxDepo, pair: str, pazar: dt.date, indirici: Indirici
              ) -> tuple[Path | None, bool]:
    """Haftalık dosyayı `_gelen`e getirir (kanonik ad); yıl sınırında alternatif anahtar denenir.

    Döner: (yol | None=hiçbir anahtarda yok, yeni_indirildi).
    """
    anahtarlar = hafta_anahtarlari(pazar)
    yil, hafta = anahtarlar[0]
    yol = depo.gelen_yolu(pair, yil, hafta)
    yok = yol.parent / f"{yil}-{hafta}.yok"
    if yol.exists() and yol.stat().st_size > 0:
        return yol, False
    if yok.exists():
        return None, False
    govde = None
    for y, w in anahtarlar:
        govde = indirici(dosya_url(pair, y, w))
        if govde is not None:
            break
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
    if pair not in FXCM_CIFTLER:
        raise FxHatasi(f"{pair}: FXCM MarketData listesinde yok (K-088; 21 çift: FXCM_CIFTLER)")
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
        yol, _ = _gelen_al(depo, pair, pazar, indirici)
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


# ------------------------------------------------------------------ kalite (R3 Paket 1(c))

#: Raporda listelenen eksik saat / kısa saat sayısı üst sınırı (toplam sayı ayrıca verilir).
KALITE_LISTE_SINIRI: Final = 50


def fx_kalite(depo: FxDepo, pair: str, takvim_id: str = TAKVIM_FX_5X24) -> dict[str, Any]:
    """FX deposunun kalite raporu — takvim (`fx-5x24`, K-089) üzerinden; deterministik JSON.

    Tanımlar (K-088/K-089): her `var` haftanın beklenen ızgarası, haftanın kendi ilk ve son barı
    arasında **takvimin açık saydığı** saatlerdir (`Takvim.izgara`): seans penceresi NY 17:00
    dönümlü olduğundan DST kayması ve hafta sonu ızgara dışındadır; ölçülmüş kapalı dönemler
    (`kapali`) beklenmez ve ayrıca sayılır (`kapali_saat`). Takvimin kapsamadığı (`olcum_kapsami`
    dışı) haftalarda kapalı dönem bilinmiyor → hafta `takvim_olcumu_disinda=True` ile işaretlenir,
    eksikler yine gap sayılır (uydurma tatil yok). Takvimin kapalı saydığı anda bar varsa
    `takvim_disi_bar` — takvimin yanlışlandığı yer, sıfır beklenir.

    - **Hafta dosyası**: manifestodaki `haftalar` — `var` / `yok`. `yok` haftalardan ilk ve son
      `var` hafta arasında kalanlar `eksik_dosya` (sağlayıcıda yok ya da indirilmemiş), dışında
      kalanlar `kapsam_disi` (sağlayıcı başlangıcından önce / henüz yayımlanmamış). Dosya
      eksikliği bar eksikliği **sayılmaz**; ayrı raporlanır.
    - **Eksik saat (gap)**: `var` bir haftanın ilk saatiyle son saati arasında takvimin
      beklediği ama depoda olmayan saat başları. Hafta sonu ve `kapali` dönemler beklenmez.
    - **Kısa saat**: `m1_sayisi < 60` — gap değil, bilgi (tick'siz dakika; günlük rollover
      dakikası burada görünür). Saat dağılımı seans kanıtı olarak verilir.
    - **Seans kanıtı** (Paket 1(d) için): haftaların açılış/kapanış saatleri (UTC) ve uzunluk
      dağılımı.
    """
    manifesto = depo.manifesto(pair)
    if manifesto is None:
        raise FxHatasi(f"{pair}: manifesto yok ({depo.manifesto_yolu(pair)})")
    tk: Takvim = takvim(takvim_id)
    haftalar: dict[str, dict[str, Any]] = manifesto.get("haftalar", {})
    sirali = sorted(haftalar.items(), key=lambda kv: kv[1]["pazar"])
    var_idx = [i for i, (_, h) in enumerate(sirali) if h.get("durum") == "var"]
    eksik_dosya, kapsam_disi = [], []
    for i, (anahtar, h) in enumerate(sirali):
        if h.get("durum") == "var":
            continue
        (eksik_dosya if var_idx and var_idx[0] < i < var_idx[-1] else kapsam_disi).append(anahtar)

    df = depo.oku(pair) if depo.parquet_yolu(pair).exists() else None
    zaman = (
        df["open_time"].to_numpy(dtype="int64") if df is not None else np.empty(0, dtype="int64")
    )
    m1 = df["m1_sayisi"].to_numpy(dtype="int64") if df is not None else np.empty(0, dtype="int64")
    mevcut = set(zaman.tolist())

    beklenen_toplam = 0
    kapali_toplam = 0
    eksik: list[int] = []
    acilis_saat: dict[str, int] = {}
    kapanis_saat: dict[str, int] = {}
    uzunluk: dict[str, int] = {}
    hafta_raporu: dict[str, dict[str, Any]] = {}
    for anahtar, h in sirali:
        if h.get("durum") != "var":
            hafta_raporu[anahtar] = {"durum": h.get("durum"), "pazar": h.get("pazar")}
            continue
        ilk = (int(h["ilk_ms"]) // SAAT_MS) * SAAT_MS
        son = (int(h["son_ms"]) // SAAT_MS) * SAAT_MS
        tum = np.arange(ilk, son + SAAT_MS, SAAT_MS, dtype="int64")
        acik = tk.acik_mi(tum)
        kapali = tk.kapali_mi(tum)
        beklenen_dizi = tum[acik]
        beklenen = int(beklenen_dizi.size)
        hafta_eksik = [int(t) for t in beklenen_dizi.tolist() if t not in mevcut]
        beklenen_toplam += beklenen
        kapali_toplam += int(kapali.sum())
        eksik.extend(hafta_eksik)
        a_saat = utc_str(ilk)[11:13]
        k_saat = utc_str(son)[11:13]
        acilis_saat[a_saat] = acilis_saat.get(a_saat, 0) + 1
        kapanis_saat[k_saat] = kapanis_saat.get(k_saat, 0) + 1
        uzunluk[str(beklenen)] = uzunluk.get(str(beklenen), 0) + 1
        hafta_raporu[anahtar] = {
            "durum": "var", "pazar": h["pazar"], "acilis": utc_str(ilk), "kapanis": utc_str(son),
            "beklenen_bar": beklenen, "eksik_bar": len(hafta_eksik),
            "kapali_saat": int(kapali.sum()),
            "m1_satir": h.get("m1_satir"),
            "takvim_olcumu_disinda": not (tk.olcum_icinde(ilk) and tk.olcum_icinde(son)),
        }
    takvim_disi = int((~tk.acik_mi(zaman)).sum()) if zaman.size else 0

    kisa_maske = m1 < 60
    kisa_saatler: dict[str, int] = {}
    for t in zaman[kisa_maske].tolist():
        sa = utc_str(int(t))[11:13]
        kisa_saatler[sa] = kisa_saatler.get(sa, 0) + 1

    return {
        "pair": pair,
        "timeframe": TIMEFRAME,
        "kaynak": "fxcm-candledata-m1",
        "veri_sha256": manifesto.get("sha256"),
        "bitis_gun": manifesto.get("bitis_gun"),
        "takvim": {"kimlik": tk.kimlik, "icerik_hash": tk.icerik_hash, "surum": tk.surum},
        "dosya": {
            "hafta": len(sirali),
            "var": len(var_idx),
            "eksik_dosya": eksik_dosya,
            "kapsam_disi": kapsam_disi,
        },
        "bar": {
            "mevcut": int(len(zaman)),
            "beklenen": beklenen_toplam,
            "eksik": len(eksik),
            "eksik_orani": (len(eksik) / beklenen_toplam) if beklenen_toplam else 0.0,
            "eksik_saatler": [utc_str(t) for t in eksik[:KALITE_LISTE_SINIRI]],
            "kapali_saat": kapali_toplam,
            "takvim_disi_bar": takvim_disi,
            "kisa_saat": int(kisa_maske.sum()),
            "kisa_saat_dagilimi": {k: kisa_saatler[k] for k in sorted(kisa_saatler)},
        },
        "seans": {
            "acilis_saati_utc": {k: acilis_saat[k] for k in sorted(acilis_saat)},
            "kapanis_saati_utc": {k: kapanis_saat[k] for k in sorted(kapanis_saat)},
            "hafta_uzunlugu_saat": {k: uzunluk[k] for k in sorted(uzunluk, key=int)},
            "not": "beklenen ızgara takvimden (NY 17:00 dönümlü 5/7 + ölçülmüş kapalı dönemler); "
            "hafta sonu ve kapalı dönem gap değil; açılış/kapanış UTC saati DST ile kayar (K-089)",
        },
        "haftalar": hafta_raporu,
    }


Varlik = Callable[[str], bool]
"""URL → sağlayıcıda var mı (HEAD 200). İndirmez."""


def kesfet(pair: str, bas_gun: str, bit_gun: str, *, var_mi: Varlik) -> dict[str, Any]:
    """Aralıktaki haftaların sağlayıcıda **var olup olmadığını** HEAD ile ölçer; indirmez.

    Tarihsel derinlik kanıtı ve indirme planı: tam evreni çekmeden hangi haftaların mevcut olduğu
    bilinir. Çıktı deterministik (haftalar sıralı), `_gelen/<PAIR>/kesif.json`a yazılabilir.
    """
    if pair not in FXCM_CIFTLER:
        raise FxHatasi(f"{pair}: FXCM MarketData listesinde yok (K-088)")
    bas, bit = _gun(bas_gun), _gun(bit_gun)
    haftalar: dict[str, dict[str, Any]] = {}
    for pazar in pazarlar(bas, bit):
        yil, hafta = hafta_no(pazar)
        bulunan: str | None = None
        for y, w in hafta_anahtarlari(pazar):
            if var_mi(dosya_url(pair, y, w)):
                bulunan = f"{y}/{w}"
                break
        haftalar[f"{yil}-{hafta}"] = {
            "pazar": pazar.isoformat(), "var": bulunan is not None,
            **({"kaynak_anahtar": bulunan} if bulunan and bulunan != f"{yil}/{hafta}" else {}),
        }
    varlar = [k for k, v in haftalar.items() if v["var"]]
    return {
        "pair": pair, "kaynak": "fxcm-candledata-m1", "bas_gun": bas.isoformat(),
        "bit_gun": bit.isoformat(), "hafta": len(haftalar), "var": len(varlar),
        "yok": len(haftalar) - len(varlar),
        "ilk_var": haftalar[varlar[0]]["pazar"] if varlar else None,
        "son_var": haftalar[varlar[-1]]["pazar"] if varlar else None,
        "haftalar": haftalar,
    }


def https_var_mi(zaman_asimi_s: float = 30.0, deneme: int = 4) -> Varlik:
    """`requests.head` (tek oturum); 200 → var, 404 → yok, diğer → `FxHatasi`.

    Uzun taramada sunucu bağlantıyı düşürebiliyor (ölçüldü: ~770 HEAD'de `RemoteDisconnected`);
    bağlantı hatası üstel beklemeyle `deneme` kez yinelenir, sonra hata — sessizce "yok" denmez.
    """
    import time

    import requests

    oturum = requests.Session()
    oturum.headers["User-Agent"] = "ScryneQuant/fx"

    def bak(url: str) -> bool:
        for i in range(deneme):
            try:
                y = oturum.head(url, timeout=zaman_asimi_s)
            except requests.ConnectionError as hata:
                if i == deneme - 1:
                    raise FxHatasi(f"{url}: bağlantı hatası ({hata})") from hata
                time.sleep(2.0 * (2**i))
                continue
            if y.status_code == 200:
                return True
            if y.status_code == 404:
                return False
            raise FxHatasi(f"{url}: HTTP {y.status_code}")
        raise AssertionError("unreachable")

    return bak


def https_indirici(zaman_asimi_s: float = 60.0) -> Indirici:
    """`requests` ile doğrudan GET; 404 → `None`, diğer hata → `FxHatasi`. Tek istek/dosya."""
    import time

    import requests

    oturum = requests.Session()
    oturum.headers["User-Agent"] = "ScryneQuant/fx"

    def al(url: str) -> bytes | None:
        for i in range(4):
            try:
                y = oturum.get(url, timeout=zaman_asimi_s)
            except requests.ConnectionError as hata:
                if i == 3:
                    raise FxHatasi(f"{url}: bağlantı hatası ({hata})") from hata
                time.sleep(2.0 * (2**i))
                continue
            if y.status_code == 404:
                return None
            if y.status_code != 200:
                raise FxHatasi(f"{url}: HTTP {y.status_code}")
            return y.content
        raise AssertionError("unreachable")

    return al


__all__ = [
    "FXCM_CIFTLER",
    "FX_SEMASI",
    "FxDepo",
    "FxHatasi",
    "FxKaydi",
    "KAYNAK_BASLANGIC",
    "KAYNAK_BASLIK",
    "VARSAYILAN_DEPO",
    "dosya_url",
    "fx_al",
    "fx_kalite",
    "hafta_anahtarlari",
    "hafta_no",
    "https_indirici",
    "https_var_mi",
    "kesfet",
    "m1_oku",
    "pazarlar",
    "saatlik",
]
