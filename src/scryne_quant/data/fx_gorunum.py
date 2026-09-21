"""FXCM 1h deposu → motorun bar dizileri: kalite bayrağı + ızgara + üyelik. (K-096, R4 Paket 4)

`data/fx.py` yalnız kaynağın verdiğini taşır (bid/ask OHLC, `m1_sayisi`; mid/kalite üretmez —
K-088). Motor ise `PiyasaGorunumu` sözleşmesini (`open/high/low/close/volume/quote_volume/trades`
+ `quality_status`) ve K-094'ün `bid_open`/`ask_open` sütunlarını bekler. Bu modül ikisinin
arasındaki **tek** çeviridir ve üç şeyi açıkça yapar:

1. **Kalite bayrağı (`fx_dogrula`)** — kripto `dogrulama.dogrula` ile aynı şema
   (`ok`/`gap`/`suspect`), FX'e özgü kurallarla: iki yanın kendi OHLC tutarlılığı, çapraz kotasyon
   (`ask < bid`), sonlu olmayan/pozitif olmayan fiyat, aşırı hareket (orta kapanış), `m1_sayisi`
   sözleşme dışı (≤ 0 ya da > 60). `gap` = seanslı takvimin (`fx-5x24`) beklediği ama olmayan
   saat; hafta sonu/ölçülmüş kapalı dönem gap değil (K-089). Hizasız damga, tekrar eden damga ve
   **takvim dışı bar** sözleşme ihlalidir: bayrakla geçiştirilmez, hata (takvimin yanlışlandığı
   yer — K-089 ölçümünde 0). Motor yalnız `ok` barda karar verir ve doldurur (K-028, K-006); bu
   modül o kuralı değiştirmez, ona bayrak verir.
2. **Bar dizileri (`fx_barlar`)** — `open/high/low/close` = iki yanın ortası (alan alan
   `(bid + ask) / 2`; orta serinin "high"ı iki high'ın ortasıdır, tanım gereği). `volume`,
   `quote_volume` **NaN** (sağlayıcı vermiyor; sıfır "hacim yok" demek olurdu, NaN "bilinmiyor" —
   kapasite oranı üretilmez, hacim isteyen strateji `hazir()` alamaz). `trades` 0 (int; kripto
   `hizala`nın doldurma değeriyle aynı, bilgi taşımaz). Bid/ask OHLC ve `m1_sayisi` **aynen**
   taşınır: fill K-094 ile `ask_open`/`bid_open`dan olur.
3. **Izgara ve üyelik** — ortak ızgara `ortak_izgara(..., takvim)` ile (seans dışı damga
   reddedilir); barı olmayan saat `listelenmedi` (kripto kalıbı: uydurma bar yok, yokluk
   işaretli). Üyelik haftalık PIT tablosundan (`fx_evren.pit_tablo`: `hafta`, `sembol`, `uye`):
   bar, UTC tarihini içeren Pazar-başlı haftanın satırına bakar; kanıtı olmayan hafta üye değil.

**Kimlik:** tablodaki kanonik kimlik (`fxcm-fx:cfd:<PAIR>@2012-01-01`, `fx_evren`) aynen; FX'te
kırılma tespiti uygulanmadı (tek segment). `maliyet_modeli_id = "fxcm-<pair>"` (K-100/5),
`finansman_modeli_id = "fxcm-<pair>"` — **referans**: `config/maliyet/fxcm-<pair>.json` ve
`config/finansman/fxcm-<pair>.json` yoksa koşu katalogda durur (K-084, K-095; oran uydurulmaz).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any, Final

import numpy as np
import pandas as pd

from scryne_quant.common.zaman import timeframe_ms, utc_str
from scryne_quant.data import fx as fx_mod
from scryne_quant.data.dogrulama import ASIRI_HAREKET_BPS
from scryne_quant.data.izgara import NAN_SUTUNLARI, _paylasimli
from scryne_quant.data.kimlik import VARLIK_FX, VENUE_FXCM_FX, Enstruman, kanonik_kimlik
from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.data.sozlesme import FX_BAR_SUTUNLARI
from scryne_quant.data.takvim import TAKVIM_FX_5X24, Takvim
from scryne_quant.strategy.evren import LISTELENMEDI

TIP_CFD: Final = "cfd"
#: K-098 venue modeli `fxcm-fx` 3 çiftte geçerliydi; 21 çiftte p75 oranı 2,39 ≥ 1,5 ölçüldü → çift
#: başına model (K-100/5). Kimlik referans; dosya `config/maliyet/fxcm-<pair>.json`.
MALIYET_MODELI_FX: Final = "fxcm-fx"
#: Bid/ask OHLC + `m1_sayisi`: motora **aynen** taşınan FX sütunları.
FX_EK_SUTUNLAR: Final[tuple[str, ...]] = tuple(s for s in FX_BAR_SUTUNLARI if s != "open_time")
_YANLAR: Final = ("bid", "ask")
_ALANLAR: Final = ("open", "high", "low", "close")


#: Kapanış artığı sayılacak azami `m1_sayisi`: kapanış anındaki tek tük son tick. Ölçülen iki
#: vakada 1; beşten büyüğü artık değil, takvimin yanlışlandığı yerdir (hata).
KAPANIS_ARTIGI_DK: Final = 5


class FxGorunumHatasi(ValueError):
    """FX bar sözleşmesi ihlali: hizasız/tekrar/takvim dışı damga, eksik sütun, ızgara dışı bar."""


def finansman_modeli_id(pair: str) -> str:
    """Çiftin finansman modeli kimliği (referans; dosya `config/finansman/<id>.json`)."""
    return f"fxcm-{pair.lower()}"


def maliyet_modeli_id(pair: str) -> str:
    """Çiftin maliyet modeli kimliği (K-100/5: çift başına; dosya `config/maliyet/<id>.json`)."""
    return f"fxcm-{pair.lower()}"


# ------------------------------------------------------------------ kalite


def _kapanis_ani(zaman: np.ndarray, tk: Takvim) -> np.ndarray:
    """Damga yerel seans kapanış gününün kapanış saatinde mi (`kapanis_gun` `kapanis_saat`:00)?"""
    if tk.seans is None:
        return np.zeros(zaman.size, dtype=bool)
    yerel = pd.to_datetime(np.asarray(zaman, dtype="int64"), unit="ms", utc=True).tz_convert(
        tk.seans.zaman_dilimi
    )
    return (
        (yerel.weekday.to_numpy() == tk.seans.kapanis_gun)
        & (yerel.hour.to_numpy() == tk.seans.kapanis_saat)
        & (yerel.minute.to_numpy() == 0)
    )


def fx_dogrula(
    df: pd.DataFrame,
    takvim: Takvim,
    *,
    pair: str = "",
    asiri_hareket_bps: float = ASIRI_HAREKET_BPS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """FX barlarına `quality_status` ekler ve raporu döner. Sözleşme ihlali → `FxGorunumHatasi`.

    `asiri_hareket_bps` kripto `dogrulama.ASIRI_HAREKET_BPS` ile aynı (5.000 bps = %50); FX için
    ölçülmüş bir eşik değil, **üst sınır** — bir saatte %50 hareket veri hatasıdır. Daha sıkı bir
    FX eşiği ölçümle gelir (R5 kalibrasyon), burada uydurulmaz.
    """
    adim = timeframe_ms(fx_mod.TIMEFRAME)
    eksik = [s for s in FX_BAR_SUTUNLARI if s not in df.columns]
    if eksik:
        raise FxGorunumHatasi(f"{pair}: eksik sütun(lar): {', '.join(eksik)}")
    if takvim.surekli:
        raise FxGorunumHatasi(f"{pair}: FX kalite bayrağı seanslı takvim ister (K-089)")

    calisma = df.loc[:, list(FX_BAR_SUTUNLARI)].copy().reset_index(drop=True)
    if calisma.empty:
        calisma["quality_status"] = pd.Series(dtype="string")
        return calisma, {"pair": pair, "bar_sayisi": 0, "bayraklar": {}, "suspect_nedenleri": {}}

    zaman = calisma["open_time"].to_numpy(dtype="int64")
    if (zaman % adim != 0).any():
        ornek = int(zaman[zaman % adim != 0][0])
        raise FxGorunumHatasi(f"{pair}: bar 1h ızgarasına hizalı değil ({utc_str(ornek)}); K-005")
    if (np.diff(zaman) <= 0).any():
        raise FxGorunumHatasi(f"{pair}: open_time sıralı ve tekil değil")
    disari = ~takvim.acik_mi(zaman)
    # Kapanış artığı (K-100/2, ölçüldü: NZDUSD 2024-02-02 22:00, USDCHF 2024-01-12 22:00 — Cuma
    # NY 17:00 kapanış anında `m1_sayisi` 1): seans kapanış anında açılan ve ≤ KAPANIS_ARTIGI_DK
    # dakikası olan bar. Seans dışıdır, karar/fill'e girmez, ızgaraya konmaz; **sayılarak** atılır
    # (rapor `kapanis_artigi`), sessizce değil. Kapalı dönemin derinindeki bar hâlâ hata.
    artik = disari & _kapanis_ani(zaman, takvim) & (
        calisma["m1_sayisi"].to_numpy(dtype="int64") <= KAPANIS_ARTIGI_DK
    )
    if (disari & ~artik).any():
        ornek = int(zaman[disari & ~artik][0])
        raise FxGorunumHatasi(
            f"{pair}: {int((disari & ~artik).sum())} bar takvimin kapalı saydığı anda "
            f"({utc_str(ornek)}); takvim ya da veri yanlış — sessizce atılmaz (K-089)"
        )
    kapanis_artiklari = [utc_str(int(t)) for t in zaman[artik].tolist()]
    if artik.any():
        calisma = calisma.loc[~artik].reset_index(drop=True)
        zaman = calisma["open_time"].to_numpy(dtype="int64")

    n = zaman.size
    yan = {
        (y, a): calisma[f"{y}_{a}"].to_numpy(dtype="float64") for y in _YANLAR for a in _ALANLAR
    }
    fiyatlar = np.vstack(list(yan.values()))
    m1 = calisma["m1_sayisi"].to_numpy(dtype="int64")

    kurallar: dict[str, np.ndarray] = {
        "sonlu_olmayan": ~np.isfinite(fiyatlar).all(axis=0),
        "pozitif_olmayan_fiyat": (fiyatlar <= 0).any(axis=0),
        "high_low_ters": (yan["bid", "high"] < yan["bid", "low"])
        | (yan["ask", "high"] < yan["ask", "low"]),
        "high_govdeyi_kapsamiyor": np.any(
            [yan[y, "high"] < yan[y, a] for y in _YANLAR for a in ("open", "close")], axis=0
        ),
        "low_govdeyi_kapsamiyor": np.any(
            [yan[y, "low"] > yan[y, a] for y in _YANLAR for a in ("open", "close")], axis=0
        ),
        # Çapraz kotasyon: ask < bid herhangi bir alanda — K-094 `bid ≤ orta ≤ ask` ister.
        "capraz_kotasyon": np.any([yan["ask", a] < yan["bid", a] for a in _ALANLAR], axis=0),
        # `m1_sayisi` sözleşmesi: 1..60. Kısa saat (< 60) gap değil, bilgi (K-088).
        "m1_sozlesme_disi": (m1 <= 0) | (m1 > 60),
    }
    orta_kapanis = (yan["bid", "close"] + yan["ask", "close"]) / 2.0
    onceki = np.concatenate([[np.nan], orta_kapanis[:-1]])
    with np.errstate(divide="ignore", invalid="ignore"):
        hareket = np.abs(orta_kapanis - onceki) / onceki * 10_000
    kurallar["asiri_hareket"] = np.nan_to_num(hareket, nan=0.0) > asiri_hareket_bps

    suspect = np.zeros(n, dtype=bool)
    for maske in kurallar.values():
        suspect |= maske

    # gap: ardışık iki bar arasında takvimin beklediği ama olmayan saat (hafta sonu beklenmez).
    # Her bar takvimin açık ızgarasında (yukarıda doğrulandı); ızgaradaki konum farkı − 1 = eksik.
    acik_izgara = takvim.izgara(int(zaman[0]), int(zaman[-1]) + adim, fx_mod.TIMEFRAME)
    konum = np.searchsorted(acik_izgara, zaman)
    eksik_arasi = np.diff(konum) - 1
    gap = np.zeros(n, dtype=bool)
    gap[1:] = eksik_arasi > 0

    durum = np.full(n, str(KaliteDurumu.OK), dtype=object)
    durum[gap] = str(KaliteDurumu.GAP)
    durum[suspect] = str(KaliteDurumu.SUSPECT)
    calisma["quality_status"] = pd.Series(durum, dtype="string")

    sayim = calisma["quality_status"].value_counts()
    rapor = {
        "pair": pair,
        "timeframe": fx_mod.TIMEFRAME,
        "takvim": {"kimlik": takvim.kimlik, "icerik_hash": takvim.icerik_hash},
        "bar_sayisi": int(n),
        "ilk_ms": int(zaman[0]),
        "son_ms": int(zaman[-1]),
        "beklenen_bar": int(acik_izgara.size),
        "eksik_bar": int(eksik_arasi.sum()),
        "bosluk_sayisi": int(gap.sum()),
        "bayraklar": {str(k): int(v) for k, v in sorted(sayim.items())},
        "suspect_nedenleri": {ad: int(m.sum()) for ad, m in kurallar.items() if m.any()},
        "kisa_saat": int((m1 < 60).sum()),
        "kapanis_artigi": kapanis_artiklari,
    }
    return calisma, rapor


# ------------------------------------------------------------------ bar dizileri


def fx_barlar(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Bayraklı FX çerçevesi → `PiyasaGorunumu` bar dizileri (ızgarasız, kendi zamanlarıyla)."""
    if "quality_status" not in df.columns:
        raise FxGorunumHatasi("kalite bayrağı yok: önce `fx_dogrula` (K-006)")
    n = len(df)
    diziler: dict[str, np.ndarray] = {"open_time": df["open_time"].to_numpy(dtype="int64")}
    for a in _ALANLAR:
        diziler[a] = (
            df[f"bid_{a}"].to_numpy(dtype="float64") + df[f"ask_{a}"].to_numpy(dtype="float64")
        ) / 2.0
    diziler["volume"] = np.full(n, np.nan, dtype="float64")
    diziler["quote_volume"] = np.full(n, np.nan, dtype="float64")
    diziler["trades"] = np.zeros(n, dtype="int64")
    for s in FX_EK_SUTUNLAR:
        diziler[s] = df[s].to_numpy(dtype="int64" if s == "m1_sayisi" else "float64")
    diziler["quality_status"] = _paylasimli(df["quality_status"])
    return diziler


def fx_hizala(barlar: Mapping[str, np.ndarray], zamanlar: np.ndarray) -> dict[str, np.ndarray]:
    """`fx_barlar` çıktısını ortak ızgaraya oturtur; olmayan saat `listelenmedi` + NaN.

    `izgara.hizala`nın FX hâli: kripto sütunlarına ek olarak bid/ask OHLC (NaN) ve `m1_sayisi` (0)
    da ızgaraya taşınır. Uydurma bar yok — yokluk bayrakla işaretli.
    """
    n = len(zamanlar)
    out: dict[str, np.ndarray] = {"open_time": np.asarray(zamanlar, dtype="int64")}
    kayan = (*NAN_SUTUNLARI, *(s for s in FX_EK_SUTUNLAR if s != "m1_sayisi"))
    for ad in kayan:
        out[ad] = np.full(n, np.nan, dtype="float64")
    out["trades"] = np.zeros(n, dtype="int64")
    out["m1_sayisi"] = np.zeros(n, dtype="int64")
    out["quality_status"] = np.full(n, LISTELENMEDI, dtype=object)

    kendi = np.asarray(barlar["open_time"], dtype="int64")
    if kendi.size == 0:
        return out
    idx = np.searchsorted(zamanlar, kendi)
    if (idx >= n).any() or not np.array_equal(np.asarray(zamanlar)[idx], kendi):
        raise FxGorunumHatasi("çiftin barları ortak ızgarada yok — ızgara yanlış kurulmuş")
    for ad in kayan:
        out[ad][idx] = np.asarray(barlar[ad], dtype="float64")
    out["trades"][idx] = np.asarray(barlar["trades"], dtype="int64")
    out["m1_sayisi"][idx] = np.asarray(barlar["m1_sayisi"], dtype="int64")
    out["quality_status"][idx] = np.asarray(barlar["quality_status"], dtype=object)
    return out


# ------------------------------------------------------------------ üyelik + kimlik


def hafta_anahtari(ms: int) -> str:
    """Barın haftası: UTC tarihini içeren Pazar-başlı haftanın `fx.hafta_no` anahtarı."""
    gun = dt.datetime.fromtimestamp(ms / 1000, tz=dt.UTC).date()
    pazar = gun - dt.timedelta(days=(gun.weekday() + 1) % 7)
    yil, w = fx_mod.hafta_no(pazar)
    return f"{yil}-{w}"


def fx_uyelik_matrisi(
    tablo: pd.DataFrame, zamanlar: np.ndarray, semboller: tuple[str, ...]
) -> dict[str, np.ndarray]:
    """Haftalık PIT tablosu → bar başına üyelik. Tabloda olmayan `(çift, hafta)` üye değil."""
    zamanlar = np.asarray(zamanlar, dtype="int64")
    anahtarlar = np.array([hafta_anahtari(int(t)) for t in zamanlar], dtype=object)
    uyeler: set[tuple[str, str]] = set()
    if not tablo.empty:
        uyeler = {
            (str(s), str(h))
            for s, h, u in zip(tablo["sembol"], tablo["hafta"], tablo["uye"], strict=True)
            if bool(u)
        }
    return {
        s: np.fromiter(((s, h) in uyeler for h in anahtarlar), dtype=bool, count=zamanlar.size)
        for s in semboller
    }


def fx_enstruman(pair: str, son_ms: int, bar_sayisi: int) -> Enstruman:
    """Tablodaki kanonik kimlikle tek segment (`fx_evren.pit_tablo` ile aynı `kanonik_id`)."""
    bas = int(
        dt.datetime.combine(fx_mod.KAYNAK_BASLANGIC, dt.time(), tzinfo=dt.UTC).timestamp() * 1000
    )
    return Enstruman(
        kanonik_id=kanonik_kimlik(
            VENUE_FXCM_FX, TIP_CFD, pair, fx_mod.KAYNAK_BASLANGIC.isoformat()
        ),
        venue=VENUE_FXCM_FX,
        sembol=pair.upper(),
        gecerli_baslangic_ms=bas,
        gecerli_bitis_ms=int(son_ms) + timeframe_ms(fx_mod.TIMEFRAME),
        bar_sayisi=int(bar_sayisi),
        kirilma_ile_basladi=False,
        asset_class=VARLIK_FX,
        instrument_type=TIP_CFD,
        takvim_id=TAKVIM_FX_5X24,
        maliyet_modeli_id=maliyet_modeli_id(pair),
        finansman_modeli_id=finansman_modeli_id(pair),
    )


__all__ = [
    "FX_EK_SUTUNLAR",
    "MALIYET_MODELI_FX",
    "TIP_CFD",
    "FxGorunumHatasi",
    "finansman_modeli_id",
    "maliyet_modeli_id",
    "fx_barlar",
    "fx_dogrula",
    "fx_enstruman",
    "fx_hizala",
    "fx_uyelik_matrisi",
    "hafta_anahtari",
]
