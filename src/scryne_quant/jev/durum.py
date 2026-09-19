"""Kanonik durum: Jev'e giden **betimleyici**, deterministik, `t`de kesik anlık görüntü. (K-074/4)

Spec §6'nın `CanonicalMarketState`i. Bu projede şekli üç ölçümle belirlendi (Spike 7):

1. **Hesap kodda, yorum Jev'de.** Jev sayısal eşik kıyasında yanılıyor (zirveye %1,02 uzakken
   "%1'den yakın" dedi). Bu yüzden buraya dizi değil, kodun hesaplayıp yuvarladığı sayılar ve
   kodun verdiği etiketler girer: EMA sıralaması, RSI bandı, volatilite bandı, Bollinger
   konumu, yapı etiketi, funding persentil bandı. Spec'in `key_factors`ı bu etiketlerdir —
   Jev'den istenmez, Jev bunları **okur**.
2. **4h bağlam 1h'den toplanır**, ikinci akış yok. Yalnızca karar anında **kapanmış** kovalar:
   `kova_açılışı + 4h ≤ veri_kesimi` (karar barının kapanışı). Dört `ok` 1h barı olmayan kova
   üretilmez; uydurulmaz (K-024). OHLC + trades Binance 4h ile bit düzeyinde aynı ölçüldü.
3. **Eksik "0" değildir** (spec §56). Isınma penceresindeki NaN `"eksik"`, 24 saatten eski
   funding `"bayat"` etiketi olarak gider; JSON'a NaN yazılamaz (`allow_nan=False`).

## Zaman alanları (spec §16, K-005)

- `karar_ms`: karar barının **açılışı** — `Sinyal.timestamp` ile aynı anlam.
- `veri_kesimi_ms`: karar barının **kapanışı** (`karar_ms + 1h`). Bar verisi bu ana kadar
  kesiktir. Funding ayrıca kendi kesimini taşır (`kaynak_kesimleri.funding_ms`): kullanılan
  son ödemenin zamanı, ve kural `funding_time ≤ karar_ms` (K-042/4 ile aynı; bar açılışında
  gerçekleşmiş ödeme).

İkisi eşit varsayılmaz; ikisi de kayıtta durur.

## Determinizm ve sızıntı

Bu modül duvar saatine bakmaz, rastgelelik içermez, yalnızca `[i-PENCERE_BAR+1 .. i]`
indekslerini okur (ne sonrasını, ne pencere öncesini — ikincisi replay = canlı eşitliği için).
`tests/unit/test_jev_durum.py` şunu ölçer: `i` sonrası **bozulduğunda ve silindiğinde**
`kanonik_json` byte düzeyinde aynı kalır; kasıtlı sızdıran bir kurucu aynı testte
yakalanır. **numpy ve `features.indikator` dışında hesap kütüphanesi import edilmez**;
pandas yok, dosya yok, ağ yok.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any, Final

import numpy as np

from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.zaman import timeframe_ms, utc_str
from scryne_quant.features import indikator as ind

#: Durum şemasının sürümü. Alan eklemek/çıkarmak/yeniden adlandırmak bunu artırır; eski
#: kayıtlar eski sürümle kalır (K-009'un "aynı girdi aynı çıktı" kuralı sürüme bağlı).
DURUM_SURUMU: Final = 1

#: Karar ve bağlam timeframe'leri (K-017 birincil 1h; K-074/4 4h bağlam).
KARAR_TF: Final = "1h"
BAGLAM_TF: Final = "4h"

#: Son ödemeden bu kadar sonra funding **bayat** (`data/funding.py::BAYAT_MS` ile aynı değer;
#: testle eşit tutuluyor). Sabit burada kopyalanıyor çünkü `data/funding.py` `requests`
#: import ediyor ve bu modülün ağ kütüphanesine dolaylı yolu bile olmamalı.
FUNDING_BAYAT_MS: Final = 24 * 3_600_000

#: Funding persentilinin penceresi: 90 gün × 3 ödeme/gün.
FUNDING_PERSENTIL_ODEME: Final = 270

#: Durumun okuduğu geriye dönük bar sayısı (1h). **Canlı ve replay aynı pencereyi görür:**
#: EMA gibi özyinelemeli indikatörler geçmişin tamamına bağlıdır; canlı `BarPenceresi` sınırlı,
#: replay sınırsız olsaydı aynı bar iki yolda farklı hash verirdi (spec §38'in uyardığı drift).
#: Pencere sabitlenince "aynı son 1.200 bar → aynı durum" iki yolda da doğru. 1.200 bar = 50
#: gün 1h, 300 kova 4h (EMA200 için 100 bar pay). Değiştirmek `DURUM_SURUMU`nu artırır.
PENCERE_BAR: Final = 1_200

#: Bir timeframe bloğunun okuduğu pencereler. Değiştirmek `DURUM_SURUMU`nu artırır.
EMA_KISA, EMA_ORTA, EMA_UZUN = 20, 50, 200
RSI_PENCERE = 14
ATR_PENCERE = 14
ATR_PERSENTIL_PENCERE = 200
BB_PENCERE, BB_KATSAYI = 20, 2.0
KANAL_PENCERE = 20
ROC_PENCERE = 24

EKSIK: Final = "eksik"
BAYAT: Final = "bayat"
GUNCEL: Final = "guncel"

_GEREKLI: Final[tuple[str, ...]] = ("open_time", "open", "high", "low", "close", "quality_status")
_OK: Final = "ok"

#: Bir 4h kovasına girebilen 1h kalite bayrakları. `backfilled` dahil: verinin kendisi
#: doğrulamadan geçmiştir, yalnızca geç gelmiştir (K-006). Canlı pencerenin ısınma barları
#: REST'ten `backfilled` gelir; onları dışlamak canlıda ilk 50 gün boyunca 4h bağlamını
#: `eksik` bırakır ve replay (hepsi `ok`) ile canlı aynı barda farklı hash üretirdi.
#: `gap`, `duplicate`, `suspect` veri kusurudur; kova üretilmez (K-024).
_KOVAYA_UYGUN: Final[frozenset[str]] = frozenset({"ok", "backfilled"})


class DurumHatasi(ValueError):
    """Kanonik durum kurulamadı: eksik alan, aralık dışı indeks, hizasız ızgara."""


# ------------------------------------------------------------------ yardımcılar


def _yuvarla(x: float, basamak: int = 2) -> float | str:
    """NaN/inf → `eksik`; aksi hâlde yuvarlanmış float. JSON'a asla NaN gitmez."""
    if x is None or not math.isfinite(x):
        return EKSIK
    # `-0.0` ile `0.0` JSON'da farklı yazılır ve aynı durumu iki hash'e bölerdi.
    return round(float(x), basamak) + 0.0


def _iliski(a: float, b: float) -> str:
    if not (math.isfinite(a) and math.isfinite(b)):
        return EKSIK
    return "ustunde" if a > b else "altinda"


def _hesapla(fn: Any, *diziler: np.ndarray, pencere: int, **kw: Any) -> np.ndarray:
    """İndikatörü hesaplar; seri pencereden kısaysa tamamen NaN döner (ısınma = eksik).

    `GecersizParametre` yakalanıyor çünkü her indikatörün asgari uzunluğu farklı (ATR ve ROC
    `pencere + 1` ister); burada yeniden saymak, `indikator.py`nin kuralını kopyalamak olurdu.
    """
    n = diziler[0].size
    try:
        return fn(*diziler, pencere, **kw)
    except ind.GecersizParametre:
        return np.full(n, np.nan)


def _timeframe_bloku(d: Mapping[str, np.ndarray]) -> dict[str, Any]:
    """Bir timeframe'in son barı için betimleyici blok. Diziler `t`de kesik verilir."""
    c, h, lo = d["close"], d["high"], d["low"]
    i = c.size - 1
    if i < 0:
        return {"veri": EKSIK}
    kap = float(c[i])

    ema20 = _hesapla(ind.ema, c, pencere=EMA_KISA)[i]
    ema50 = _hesapla(ind.ema, c, pencere=EMA_ORTA)[i]
    ema200 = _hesapla(ind.ema, c, pencere=EMA_UZUN)[i]
    rsi = _hesapla(ind.rsi, c, pencere=RSI_PENCERE)[i]
    atr = _hesapla(ind.atr, h, lo, c, pencere=ATR_PENCERE)
    roc = _hesapla(ind.roc, c, pencere=ROC_PENCERE)[i]
    zirve = _hesapla(ind.en_yuksek, h, pencere=KANAL_PENCERE)
    dip = _hesapla(ind.en_dusuk, lo, pencere=KANAL_PENCERE)

    if c.size >= BB_PENCERE:
        alt, orta, ust = ind.bollinger(c, BB_PENCERE, BB_KATSAYI)
        alt_i, orta_i, ust_i = float(alt[i]), float(orta[i]), float(ust[i])
    else:
        alt_i = orta_i = ust_i = math.nan

    # ATR persentili: son 200 barın ATR'si içinde bugünkünün sırası (kod hesaplar).
    atr_i = float(atr[i])
    pencere = atr[max(0, i - ATR_PERSENTIL_PENCERE + 1) : i + 1]
    pencere = pencere[np.isfinite(pencere)]
    if math.isfinite(atr_i) and pencere.size >= ATR_PENCERE:
        atr_p = float(np.mean(pencere < atr_i) * 100.0)
    else:
        atr_p = math.nan

    if math.isfinite(rsi):
        rsi_bandi = "asiri_alim" if rsi >= 70 else "asiri_satim" if rsi <= 30 else "notr"
    else:
        rsi_bandi = EKSIK
    if math.isfinite(atr_p):
        vol_bandi = "yuksek" if atr_p >= 80 else "dusuk" if atr_p <= 20 else "orta"
    else:
        vol_bandi = EKSIK
    if math.isfinite(alt_i):
        bb = (
            "ust_bant_ustu"
            if kap > ust_i
            else "ust_yari"
            if kap > orta_i
            else "alt_yari"
            if kap > alt_i
            else "alt_bant_alti"
        )
    else:
        bb = EKSIK

    # Yapı: son 20 barın zirve/dibi, 20 bar öncekiyle karşılaştırılır. İki tam pencere ister.
    if i - KANAL_PENCERE >= 0 and math.isfinite(zirve[i - KANAL_PENCERE]):
        zy = "yukselen" if zirve[i] > zirve[i - KANAL_PENCERE] else "alcalan"
        dy = "yukselen" if dip[i] > dip[i - KANAL_PENCERE] else "alcalan"
        yapi = f"zirveler_{zy}_dipler_{dy}"
    else:
        yapi = EKSIK

    return {
        "bar_sayisi": int(c.size),
        "kapanis_ema20": _iliski(kap, ema20),
        "ema20_ema50": _iliski(ema20, ema50),
        "ema50_ema200": _iliski(ema50, ema200),
        "rsi14": _yuvarla(rsi, 1),
        "rsi_bandi": rsi_bandi,
        "atr14_yuzde": _yuvarla(atr_i / kap * 100.0 if kap > 0 else math.nan),
        "volatilite_bandi": vol_bandi,
        "bollinger_konum": bb,
        "roc_24bar_yuzde": _yuvarla(roc),
        "zirve20_uzaklik_yuzde": _yuvarla((zirve[i] - kap) / kap * 100.0 if kap > 0 else math.nan),
        "dip20_uzaklik_yuzde": _yuvarla((kap - dip[i]) / kap * 100.0 if kap > 0 else math.nan),
        "yapi": yapi,
    }


# ------------------------------------------------------------------ 4h toplama


def kapanmis_4h(
    diziler_1h: Mapping[str, np.ndarray], i: int, *, veri_kesimi_ms: int
) -> tuple[dict[str, np.ndarray], int]:
    """Son `PENCERE_BAR` 1h bardan, `veri_kesimi_ms`te **kapanmış** tam 4h kovaları toplar.

    Kova `[b, b+4h)`; kapanmış ⇔ `b + 4h ≤ veri_kesimi_ms`. Kovada tam 4 bar yoksa ya da
    biri `_KOVAYA_UYGUN` dışındaysa (gap/duplicate/suspect) kova **üretilmez** (sayısı döner).
    OHLC ve trades Binance'in 4h dosyasıyla bit düzeyinde aynı (Spike 7a); hacim toplama sırası
    yüzünden 1 ulp oynayabilir ve bu yüzden duruma girmez.
    """
    adim1, adim4 = timeframe_ms(KARAR_TF), timeframe_ms(BAGLAM_TF)
    bas = max(0, i - PENCERE_BAR + 1)
    zaman = np.asarray(diziler_1h["open_time"][bas : i + 1], dtype=np.int64)
    kalite = np.asarray(diziler_1h["quality_status"][bas : i + 1], dtype=object)
    kova = (zaman // adim4) * adim4
    kapanmis = kova + adim4 <= veri_kesimi_ms
    zaman, kalite, kova = zaman[kapanmis], kalite[kapanmis], kova[kapanmis]

    acilis = np.asarray(diziler_1h["open"][bas : i + 1], dtype=np.float64)[kapanmis]
    yuksek = np.asarray(diziler_1h["high"][bas : i + 1], dtype=np.float64)[kapanmis]
    dusuk = np.asarray(diziler_1h["low"][bas : i + 1], dtype=np.float64)[kapanmis]
    kapanis = np.asarray(diziler_1h["close"][bas : i + 1], dtype=np.float64)[kapanmis]

    out: dict[str, list[float]] = {"open_time": [], "open": [], "high": [], "low": [], "close": []}
    eksik = 0
    if zaman.size:
        sinirlar = np.flatnonzero(np.diff(kova)) + 1
        baslar = np.concatenate(([0], sinirlar))
        bitisler = np.concatenate((sinirlar, [zaman.size]))
        for b, e in zip(baslar, bitisler, strict=True):
            tam = (e - b) == adim4 // adim1
            hepsi_ok = all(str(k) in _KOVAYA_UYGUN for k in kalite[b:e])
            if not (tam and hepsi_ok):
                eksik += 1
                continue
            out["open_time"].append(int(kova[b]))
            out["open"].append(float(acilis[b]))
            out["high"].append(float(yuksek[b:e].max()))
            out["low"].append(float(dusuk[b:e].min()))
            out["close"].append(float(kapanis[e - 1]))
    diziler = {
        "open_time": np.asarray(out["open_time"], dtype=np.int64),
        **{a: np.asarray(out[a], dtype=np.float64) for a in ("open", "high", "low", "close")},
    }
    return diziler, eksik


# ------------------------------------------------------------------ funding


def _funding_bloku(
    funding_time_ms: np.ndarray | None,
    funding_rate: np.ndarray | None,
    karar_ms: int,
) -> tuple[dict[str, Any], int | None]:
    """`funding_time ≤ karar_ms` olan son ödeme + persentil bandı. Kesim zamanı ayrıca döner."""
    if funding_time_ms is None or funding_rate is None or len(funding_time_ms) == 0:
        return {"veri": EKSIK}, None
    z = np.asarray(funding_time_ms, dtype=np.int64)
    r = np.asarray(funding_rate, dtype=np.float64)
    if z.size != r.size:
        raise DurumHatasi("funding zaman ve oran dizileri aynı uzunlukta olmalı")
    if np.any(np.diff(z) <= 0):
        raise DurumHatasi("funding_time artan ve tekil olmalı")
    gorunen = z <= karar_ms
    if not gorunen.any():
        return {"veri": EKSIK}, None
    son_i = int(np.flatnonzero(gorunen)[-1])
    son_z, son_r = int(z[son_i]), float(r[son_i])
    pencere = r[max(0, son_i - FUNDING_PERSENTIL_ODEME + 1) : son_i + 1]
    persentil = float(np.mean(pencere < son_r) * 100.0)
    bayat = (karar_ms - son_z) > FUNDING_BAYAT_MS
    return {
        "son_oran_yuzde": _yuvarla(son_r * 100.0, 4),
        "son_odeme_ms": son_z,
        "persentil_90gun": _yuvarla(persentil, 1),
        "bandi": "yuksek" if persentil >= 90 else "dusuk" if persentil <= 10 else "notr",
        "durum": BAYAT if bayat else GUNCEL,
    }, son_z


# ------------------------------------------------------------------ kanonik durum


def kanonik_durum(
    diziler_1h: Mapping[str, np.ndarray],
    i: int,
    *,
    sembol: str,
    funding_time_ms: np.ndarray | None = None,
    funding_rate: np.ndarray | None = None,
) -> dict[str, Any]:
    """`i`. (karar) barında kesilmiş kanonik durum. Yalnızca `[i-PENCERE_BAR+1 .. i]` okunur.

    Girdi `features/barlar.bar_dizileri`nin çıktısı (backtest ve canlı için **aynı** diziler)
    ya da aynı alanları taşıyan herhangi bir sözlük. Dönen sözlük JSON'a çevrilebilir
    (`kanonik_json`) ve hash'lenebilir (`durum_hash`); `numpy` tipi içermez.
    """
    eksik = [a for a in _GEREKLI if a not in diziler_1h]
    if eksik:
        raise DurumHatasi(f"bar dizilerinde eksik alan(lar): {', '.join(eksik)}")
    n = len(diziler_1h["open_time"])
    if not 0 <= i < n:
        raise DurumHatasi(f"bar indeksi aralık dışı: {i} (0..{n - 1})")

    adim = timeframe_ms(KARAR_TF)
    karar_ms = int(diziler_1h["open_time"][i])
    if karar_ms % adim:
        raise DurumHatasi(f"karar barı {KARAR_TF} ızgarasına hizalı değil: {karar_ms}")
    veri_kesimi_ms = karar_ms + adim

    bas = max(0, i - PENCERE_BAR + 1)
    kesik_1h = {
        a: np.asarray(diziler_1h[a][bas : i + 1], dtype=np.float64)
        for a in ("open", "high", "low", "close")
    }
    blok_1h = _timeframe_bloku(kesik_1h)
    d4, eksik_4h = kapanmis_4h(diziler_1h, i, veri_kesimi_ms=veri_kesimi_ms)
    blok_4h = _timeframe_bloku(d4)
    blok_4h["eksik_kova"] = int(eksik_4h)
    blok_4h["son_kova_ms"] = int(d4["open_time"][-1]) if d4["open_time"].size else EKSIK

    funding, funding_kesimi = _funding_bloku(funding_time_ms, funding_rate, karar_ms)
    son_kalite = str(diziler_1h["quality_status"][i])

    return {
        "surum": DURUM_SURUMU,
        "sembol": sembol.upper(),
        "karar_timeframe": KARAR_TF,
        "karar_ms": karar_ms,
        "karar_utc": utc_str(karar_ms),
        "veri_kesimi_ms": veri_kesimi_ms,
        "kaynak_kesimleri": {"bar_ms": veri_kesimi_ms, "funding_ms": funding_kesimi},
        "kalite": {"karar_bari": son_kalite, "karar_bari_ok": son_kalite == _OK},
        KARAR_TF: blok_1h,
        f"{BAGLAM_TF}_kapanmis": blok_4h,
        "funding": funding,
    }


def kanonik_json(durum: Mapping[str, Any]) -> bytes:
    """Durumun kanonik byte gösterimi: anahtarlar sıralı, boşluksuz, NaN yasak.

    Byte-identical sızıntı testi bu diziyi karşılaştırır; `durum_hash` bunun SHA-256'sıdır
    (`nesne_hash` aynı kanonu kullanır).
    """
    return json.dumps(
        durum, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def durum_hash(durum: Mapping[str, Any]) -> str:
    """`state_hash` (spec §17): kanonik JSON'un SHA-256'sı."""
    kanonik_json(durum)  # NaN varsa burada patlar; sessizce hash'lenmez
    return nesne_hash(durum)


__all__ = [
    "BAGLAM_TF",
    "BAYAT",
    "DURUM_SURUMU",
    "EKSIK",
    "FUNDING_BAYAT_MS",
    "GUNCEL",
    "KARAR_TF",
    "PENCERE_BAR",
    "DurumHatasi",
    "durum_hash",
    "kanonik_durum",
    "kanonik_json",
    "kapanmis_4h",
]
