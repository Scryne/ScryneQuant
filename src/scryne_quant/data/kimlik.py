"""Kanonik enstrüman kimliği ve kimlik kırılması tespiti. (K-052/4, Spike 6 §4a, Faz 9)

**Enstrüman kimliği ticker değildir.** `LUNAUSDT` arşivde 2020-08'den bugüne tek bir seri
gibi duruyor; ama 2022-05-13 00:00 kapanışı 0,00005, ardından 17 gün satır yok, 2022-05-31
06:00 açılışı 1,00. Aynı ticker altında iki farklı varlık: Terra Classic ve yeni LUNA. Seriyi
olduğu gibi okuyan bir motor boşluğun iki yanını birleştirir ve 20.000 katlık bir getiri
görür.

**Mevcut katmanlar bunu yakalamıyor** (arşivden indirilen gerçek seride görüldü): K-006
boşluğu `gap`, sıçramayı `asiri_hareket` → `suspect` işaretliyor — ama **yalnızca tek bir
barı.** Sonraki barlar `ok`; bayrak eksik ya da bozuk barı işaretler, değişen varlığı değil.
Bir getiri penceresi o tek barı atlasa bile boşluğun iki yanındaki fiyatları karşılaştırır.

**Tespit kuralı: uzun boşluk VE imkânsız fiyat oranı, ikisi birden** (K-052/4). Tek başına
ikisi de yetmez: uzun boşluk borsa bakımı ya da askıya alma olabilir (fiyat kaldığı yerden
devam eder); büyük hareket gerçek bir çöküş olabilir (boşluksuz barlarda `suspect` zaten
yakalıyor). Kırılma şüphesi olan noktada seri **iki kimliğe bölünür.**

**Bölmek güvenli yön.** Yanlış pozitif bir kırılma aynı varlığın geçmişini ikiye ayırır: bir
strateji o noktada pozisyonu devralamaz, ısınma yeniden başlar — bilgi kaybı, uydurma yok.
Yanlış negatif ise olmayan bir getiriyi seriye gömer. K-007'nin *"belirsizlikte aleyhte"*
ilkesinin kimlik eksenindeki karşılığı: şüphede böl.

**Eşikler ölçüldü** (2026-09-16, 734 sembol, 20,06 milyon 1h barı, 3.598 boşluk):

| eksik bar | \|ln oran\| < 0,1 | 0,1–1 | 1–2,3 | ≥ 2,3 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1.481 | 1 | 0 | 0 |
| 2–23 | 2.040 | 14 | 6 | 3 |
| 24–167 | 6 | 4 | 1 | 21 |
| 168+ | 8 | 4 | 1 | 2 |

Dağılımda **boş bir bant** var: eksik barı ≥ 12 olan boşluklarda `|ln oran|` 0,99 ile 2,30
arasında hiçbir vaka yok. 2,30 ve üstündeki 28 vakanın tamamı bilinen kimlik değişimi:
`LUNAUSDT` (yeni LUNA), `VENUSDT` (VEN→VET takası, 2.117 bar boşluk), 1:1000
redenominasyonlar (`SUNUSDT`, `COCOSUSDT`, `QUICKUSDT`), 1:100 (`DREPUSDT`, `BNXUSDT`),
1:10 (`BTCSTUSDT`, `STRAXUSDT`, `VIDTUSDT`) ve kaldıraçlı token ters bölünmeleri.

Alt sınırın altında kalan en yakın vakalar gerçek fiyat hareketi: 2021-05-19 çöküşünde
Binance'in **4 barlık** kesintisi sırasında kaldıraçlı token'lar `|ln|` 3,02'ye kadar
oynadı — kimlik değişmedi. Bu yüzden bar eşiği 4'ün üç katına, **12 bara (yarım gün)**
konuldu; oran eşiği ölçülen boş bandın üst ucu olan **ln 10 = 2,3026**. İki eşik de 1h
serileri için ölçüldü; başka bir timeframe'de yeniden ölçülmeden kullanılmaz.

**Kanonik kimlik:** `<venue>:<ticker>@<segmentin ilk barının UTC tarihi>`. Deterministik ve
**geriye doğru kararlı**: seriye yeni bar eklenmesi mevcut kimlikleri değiştirmez, çünkü
bir segmentin ilk barı sonradan değişmez.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

from scryne_quant.common.zaman import timeframe_ms, utc_str

VENUE_BINANCE_SPOT: Final = "binance-spot"

# --- Enstrüman v2 alanları (ROADMAP-RESET R2, K-083 taslağı) -------------------------------
#
# Aşağıdaki kümeler ve varsayılanlar **bugün depoda olan tek gerçeği** kodlar: Binance spot
# kripto, 7/24, tek global maliyet modeli (K-007), finansman yok. Yeni bir sınıf/tip/takvim
# eklemek bu sabitlere dokunmak demek — bilerek; bir varlık sınıfı "kodda geçiyor" diye
# desteklenmiş sayılmaz (Threshold-Policy §3'teki sütunlar `DECISION REQUIRED`). Alanlar
# yalnızca **kimlik** taşır: motor/fill/live bunları okumaz (R4'ün işi), `sozluk()` çıktısı
# hiçbir deney/sonuç hash'ine girmez (`tests/unit/test_enstruman_v2.py` bunu tarıyor).

#: Varlık sınıfları. Yalnız `kripto` — başka sınıf için veri/lisans/takvim kararı yok (R3).
VARLIK_SINIFLARI: Final[frozenset[str]] = frozenset({"kripto"})
VARLIK_KRIPTO: Final = "kripto"

#: Enstrüman tipleri — kapalı küme (U13). Spot ≠ vadeli ≠ CFD ≠ ETF: aynı dayanağın farklı
#: sözleşmeleri farklı enstrümandır; verileri karıştırılmaz. Bugün yalnız `spot` üretiliyor;
#: diğerleri kimlik düzeyinde tanımlı, **çalışır değil** (execution/backtest desteği yok).
ENSTRUMAN_TIPLERI: Final[tuple[str, ...]] = ("spot", "vadeli", "cfd", "etf")
TIP_SPOT: Final = "spot"

#: Takvim kimliği. Yalnız bir etiket: takvim soyutlaması (seans, tatil, eksik-bar tanımı)
#: bu pakette yok, `data/izgara.py` 24/7 ızgara varsayımıyla çalışmaya devam ediyor.
TAKVIM_24X7: Final = "24x7"

#: Maliyet modeli kimliği. `global` = `config/maliyet.json`'daki tek model (K-007, U14 açık).
MALIYET_MODELI_GLOBAL: Final = "global"

#: Kimlik kırılması: asgari eksik bar (1h serileri için). Ölçülen yanlış-pozitif bölgesi
#: ≤ 4 bar (2021-05-19 kesintisi); eşik onun üç katı. Bkz. modül notundaki tablo.
KIRILMA_ASGARI_EKSIK_BAR: Final = 12

#: Kimlik kırılması: asgari `|ln(sonraki açılış / önceki kapanış)|` = ln 10, yani 10 kat.
#: Ölçülen boş bandın (0,99 – 2,30) üst ucu ve en küçük gerçek redenominasyon oranı (1:10).
KIRILMA_ASGARI_LOG_ORAN: Final = 2.302585092994046


class KimlikHatasi(ValueError):
    """Kimlik sözleşmesinin ihlali."""


@dataclass(frozen=True, slots=True)
class KimlikKirilmasi:
    """Bir boşluğun iki yanında farklı varlık şüphesi."""

    sembol: str
    onceki_son_ms: int
    """Boşluktan önceki son barın açılışı."""
    sonraki_ilk_ms: int
    """Boşluktan sonraki ilk barın açılışı — yeni kimliğin başlangıcı."""
    eksik_bar: int
    onceki_kapanis: float
    sonraki_acilis: float

    @property
    def oran(self) -> float:
        """`sonraki_acilis / onceki_kapanis`."""
        return self.sonraki_acilis / self.onceki_kapanis

    @property
    def log_oran(self) -> float:
        """`|ln(oran)|` — yön bağımsız büyüklük. 10 kat artış ve 10 kat düşüş aynı ölçüde."""
        return abs(math.log(self.oran))

    def sozluk(self) -> dict[str, Any]:
        return {
            "sembol": self.sembol,
            "onceki_son": utc_str(self.onceki_son_ms),
            "sonraki_ilk": utc_str(self.sonraki_ilk_ms),
            "onceki_son_ms": self.onceki_son_ms,
            "sonraki_ilk_ms": self.sonraki_ilk_ms,
            "eksik_bar": self.eksik_bar,
            "onceki_kapanis": self.onceki_kapanis,
            "sonraki_acilis": self.sonraki_acilis,
            "oran": self.oran,
            "log_oran": round(self.log_oran, 6),
        }


@dataclass(frozen=True, slots=True)
class Enstruman:
    """Geçerlilik aralığı taşıyan kanonik enstrüman. Aralık `[baslangic, bitis)`.

    **v2 (R2):** kimlik alanlarına sözleşme alanları eklendi — varlık sınıfı, enstrüman tipi,
    takvim, tick/lot/kontrat, maliyet ve finansman modeli kimlikleri. Hepsi varsayılanlı ve
    varsayılanlar bugünkü tek gerçeği (Binance spot kripto) kodlar; `kimlikleri_kur` yalnız
    v1 alanlarını verir. Kanonik kimlik (`kanonik_id`) **değişmedi**: kimlik hâlâ
    `<venue>:<ticker>@<tarih>`; tip/sınıf kimliğe girmiyor, çünkü bugün tek venue tek tip.
    U13'ün `(venue, instrument_type, sembol, geçerlilik)` dörtlüsü ONAY BEKLİYOR — kabul
    edilirse kanonik kimlik biçimi ayrı bir K ile değişir, bu pakette değil.
    """

    kanonik_id: str
    venue: str
    sembol: str
    gecerli_baslangic_ms: int
    gecerli_bitis_ms: int
    """Segmentin son barının **kapanışı** (dışlayıcı): son bar açılışı + timeframe."""
    bar_sayisi: int
    kirilma_ile_basladi: bool

    # --- v2 sözleşme alanları (varsayılan = bugünkü tek gerçek) ---
    asset_class: str = VARLIK_KRIPTO
    """Dayanağın sınıfı (`kripto`; FX/endeks/emtia için karar yok). Tipten ayrı eksen."""
    instrument_type: str = TIP_SPOT
    """`ENSTRUMAN_TIPLERI`den biri. Sınıfla karıştırılmaz: kripto spot ≠ kripto vadeli."""
    takvim_id: str = TAKVIM_24X7
    """Takvim etiketi. Davranışı yok (U15 açık); ızgara hâlâ sürekli 24/7 varsayıyor."""
    tick_size: float | None = None
    """Fiyat adımı. `None` = **bilinmiyor**: arşiv verisi taşımıyor, `exchange/kurallar.py`
    (`SembolKurallari`) borsadan canlı okuyor ve bu katman ona bağlanmadı. Uydurulmaz."""
    lot_size: float | None = None
    """Miktar adımı. `None` = bilinmiyor (bkz. `tick_size`)."""
    contract_size: float | None = None
    """Kontrat büyüklüğü. Spot'ta kavram yok; vadeli/CFD için kaynak yok → `None`."""
    maliyet_modeli_id: str = MALIYET_MODELI_GLOBAL
    """Hangi maliyet modeli. Bugün tek global model (K-007); enstrüman-başı maliyet U14/R2
    sonraki paket — motor bu alanı **okumuyor**."""
    finansman_modeli_id: str | None = None
    """Finansman/rollover modeli. Spot'ta yok; perp funding verisi var, modeli yok (K-079)."""

    def __post_init__(self) -> None:
        if self.asset_class not in VARLIK_SINIFLARI:
            raise KimlikHatasi(
                f"{self.kanonik_id}: bilinmeyen varlık sınıfı {self.asset_class!r}; "
                f"geçerli: {sorted(VARLIK_SINIFLARI)}"
            )
        if self.instrument_type not in ENSTRUMAN_TIPLERI:
            raise KimlikHatasi(
                f"{self.kanonik_id}: bilinmeyen enstrüman tipi {self.instrument_type!r}; "
                f"geçerli: {list(ENSTRUMAN_TIPLERI)}"
            )
        if not self.takvim_id or not self.maliyet_modeli_id:
            raise KimlikHatasi(f"{self.kanonik_id}: takvim_id ve maliyet_modeli_id boş olamaz")
        for ad in ("tick_size", "lot_size", "contract_size"):
            deger = getattr(self, ad)
            if deger is not None and (
                isinstance(deger, bool)
                or not isinstance(deger, (int, float))
                or not math.isfinite(deger)
                or not deger > 0
            ):
                raise KimlikHatasi(
                    f"{self.kanonik_id}: {ad} sonlu pozitif sayı ya da None olmalı"
                )

    def sozluk(self) -> dict[str, Any]:
        """Katalog kaydı. v1 anahtarları **aynı sırada ve aynı değerle** önce; v2 alanları
        sonra. Bu sözlük `_evren/kimlik-katalogu.json`a yazılır ve **hiçbir hash'e girmez**
        (`sonuc_hash`, `config_hash`, `tablo_hash`, deney kimliği) — test_enstruman_v2."""
        return {
            "kanonik_id": self.kanonik_id,
            "venue": self.venue,
            "sembol": self.sembol,
            "gecerli_baslangic_ms": self.gecerli_baslangic_ms,
            "gecerli_bitis_ms": self.gecerli_bitis_ms,
            "gecerli_baslangic": utc_str(self.gecerli_baslangic_ms),
            "gecerli_bitis": utc_str(self.gecerli_bitis_ms),
            "bar_sayisi": self.bar_sayisi,
            "kirilma_ile_basladi": self.kirilma_ile_basladi,
            "asset_class": self.asset_class,
            "instrument_type": self.instrument_type,
            "takvim_id": self.takvim_id,
            "tick_size": self.tick_size,
            "lot_size": self.lot_size,
            "contract_size": self.contract_size,
            "maliyet_modeli_id": self.maliyet_modeli_id,
            "finansman_modeli_id": self.finansman_modeli_id,
        }


def bosluklar(df: pd.DataFrame, timeframe: str, sembol: str = "") -> list[KimlikKirilmasi]:
    """Serideki **tüm** boşluklar, eşik uygulanmadan. Ölçüm (dağılım) buradan yapılır.

    Girdi `open_time`'a göre sıralı ve tekil olmalı (depodan okunan veri öyledir).
    """
    if df.empty:
        return []
    zaman = df["open_time"].to_numpy(dtype="int64")
    if (np.diff(zaman) <= 0).any():
        raise KimlikHatasi(f"{sembol}: open_time sıralı ve tekil değil")
    adim = timeframe_ms(timeframe)
    acilis = df["open"].to_numpy(dtype="float64")
    kapanis = df["close"].to_numpy(dtype="float64")
    out: list[KimlikKirilmasi] = []
    for i in np.flatnonzero(np.diff(zaman) > adim):
        onceki, sonraki = float(kapanis[i]), float(acilis[i + 1])
        if not (onceki > 0 and sonraki > 0):
            # Pozitif olmayan fiyat `suspect` kuralının konusu; oran tanımsız, uydurulmaz.
            continue
        out.append(
            KimlikKirilmasi(
                sembol=sembol,
                onceki_son_ms=int(zaman[i]),
                sonraki_ilk_ms=int(zaman[i + 1]),
                eksik_bar=int((zaman[i + 1] - zaman[i]) // adim) - 1,
                onceki_kapanis=onceki,
                sonraki_acilis=sonraki,
            )
        )
    return out


def kirilmalar(
    df: pd.DataFrame,
    timeframe: str,
    *,
    asgari_eksik_bar: int,
    asgari_log_oran: float,
    sembol: str = "",
) -> list[KimlikKirilmasi]:
    """Kimlik kırılması şüphesi: `eksik_bar >= asgari_eksik_bar` **ve**
    `log_oran >= asgari_log_oran`. Eşikler zorunlu parametre; ölçülen değerler
    `KIRILMA_ASGARI_EKSIK_BAR` ve `KIRILMA_ASGARI_LOG_ORAN` (bkz. modül notu)."""
    if asgari_eksik_bar < 1 or asgari_log_oran <= 0:
        raise KimlikHatasi("eşikler pozitif olmalı: boşluksuz veya oransız kırılma tanımsız")
    return [
        b
        for b in bosluklar(df, timeframe, sembol)
        if b.eksik_bar >= asgari_eksik_bar and b.log_oran >= asgari_log_oran
    ]


def kimlikleri_kur(
    df: pd.DataFrame,
    timeframe: str,
    sembol: str,
    kirilma_listesi: list[KimlikKirilmasi],
    *,
    venue: str = VENUE_BINANCE_SPOT,
) -> list[Enstruman]:
    """Seriyi kırılma noktalarından bölüp kanonik enstrümanları üretir."""
    if df.empty:
        return []
    adim = timeframe_ms(timeframe)
    zaman = df["open_time"].to_numpy(dtype="int64")
    kesimler = sorted({k.sonraki_ilk_ms for k in kirilma_listesi})
    for k in kesimler:
        if k not in set(zaman.tolist()):
            raise KimlikHatasi(f"{sembol}: kırılma noktası seride bir bar değil ({utc_str(k)})")

    sinirlar = [int(zaman[0]), *kesimler]
    out: list[Enstruman] = []
    for j, bas in enumerate(sinirlar):
        son_sinir = sinirlar[j + 1] if j + 1 < len(sinirlar) else None
        maske = (zaman >= bas) if son_sinir is None else ((zaman >= bas) & (zaman < son_sinir))
        parca = zaman[maske]
        tarih = utc_str(int(parca[0]))[:10]
        out.append(
            Enstruman(
                kanonik_id=f"{venue}:{sembol.upper()}@{tarih}",
                venue=venue,
                sembol=sembol.upper(),
                gecerli_baslangic_ms=int(parca[0]),
                gecerli_bitis_ms=int(parca[-1]) + adim,
                bar_sayisi=int(parca.size),
                kirilma_ile_basladi=j > 0,
            )
        )
    return out


__all__ = [
    "ENSTRUMAN_TIPLERI",
    "KIRILMA_ASGARI_EKSIK_BAR",
    "KIRILMA_ASGARI_LOG_ORAN",
    "MALIYET_MODELI_GLOBAL",
    "TAKVIM_24X7",
    "TIP_SPOT",
    "VARLIK_KRIPTO",
    "VARLIK_SINIFLARI",
    "VENUE_BINANCE_SPOT",
    "Enstruman",
    "KimlikHatasi",
    "KimlikKirilmasi",
    "bosluklar",
    "kimlikleri_kur",
    "kirilmalar",
]
