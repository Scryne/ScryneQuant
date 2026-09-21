"""Point-in-time evren tablosu. (K-052/3, K-051/4, Spike 6, Faz 9)

**Evren üyeliği bir zaman serisidir.** Bugünkü listeden kurulan evren, Spike 6'nın ölçtüğü
gibi her ayın likit isimlerinin medyan %18'ini — sonradan başarısız olanları — atar. Bu
modül her ay için, **yalnızca o ayın başında bilinebilecek** veriyle bir üye listesi üretir.

**M ayının üyeliği neye bakar, neye bakmaz:**

- M−1 ayının `quote_volume` toplamı (kendi barlarımızdan; arşivin `1mo` özet katmanından
  **değil** — Spike 6 §4b: o katman 2026-03'ten beri eksik).
- Enstrümanın M−1'in **son gününde hâlâ işlem görüyor olması.** M−1 içinde delist edilmiş
  bir sembol M'nin başında listelenmiş değildir ve bu M'nin başında bilinir.
- **Kanonik kimlik**, ticker değil (K-052/4): kırılma noktasından sonraki kimliğin hacmi
  yalnızca kendi barlarından sayılır. Aksi hâlde yeni LUNA, eski LUNA'nın hacmiyle evrene
  girerdi.
- `suspect` barların hacmi sayılmaz: içeriği bozuk olabilecek bir barın hacmi de bozuk
  olabilir.
- M'ye ve sonrasına ait **hiçbir şey.** Testle kanıtlı: M'den sonraki veri bozulduğunda M ve
  öncesinin üyeliği bit düzeyinde değişmiyor.

**Evren kuralı bir çekiliştir** (K-051/4). `EvrenKurali`nın her alanı — üst N, hacim
eşiği, kote para birimi, dışlanan semboller, ay sonu toleransı — kuralın kimlik hash'ine
girer. Kural değiştirmek aynı veriye yeni bir soru sormaktır ve deftere yazılır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np
import pandas as pd

from scryne_quant.common.hash import nesne_hash
from scryne_quant.data.kimlik import (
    ENSTRUMAN_TIPLERI,
    TIP_SPOT,
    VENUE_BINANCE_SPOT,
    VENUE_TIPLERI,
    Enstruman,
)
from scryne_quant.data.semalar import KaliteDurumu

#: Kaldıraçlı token'lar: fiyatları bir türevin günlük yeniden dengelenmiş getirisi, kendi
#: arz/talepleri değil. Spike 6 aday evrenden bunları (52 sembol) çıkardı.
KALDIRACLI_TOKEN_DESENI: Final = r"(UP|DOWN|BULL|BEAR)USDT$"

#: Taban varlığı stablecoin veya fiat olan pariteler: USDT'ye karşı fiyatı ~sabit, getirisi
#: bir kur farkı. Liste Spike 6'nın dışlama sınıfıyla aynı **amaç**tadır; tam üyeliği bu
#: dosyada sabitlenir ve kural hash'ine girer.
STABIL_FIAT_TABANLAR: Final[tuple[str, ...]] = (
    "AEUR",
    "AUD",
    "BIDR",
    "BRL",
    "BUSD",
    "BVND",
    "DAI",
    "EUR",
    "EURI",
    "FDUSD",
    "GBP",
    "IDRT",
    "NGN",
    "PAX",
    "RUB",
    "SUSD",
    "TRY",
    "TUSD",
    "UAH",
    "USD1",
    "USDC",
    "USDP",
    "USDS",
    "USDSB",
    "UST",
    "ZAR",
)

GUN_MS: Final = 86_400_000


class EvrenHatasi(ValueError):
    """Evren kuralı veya girdisi geçersiz."""


@dataclass(frozen=True, slots=True)
class EvrenKurali:
    """Bir ayın üyelik kuralı. Tüm alanlar kimliğe girer (K-051/4)."""

    ust_n: int
    asgari_quote_hacim: float
    """M−1 ayı toplam `quote_volume` alt sınırı (kote para biriminde)."""
    kote: str = "USDT"
    haric_desenler: tuple[str, ...] = (KALDIRACLI_TOKEN_DESENI,)
    haric_tabanlar: tuple[str, ...] = STABIL_FIAT_TABANLAR
    ay_sonu_tolerans_saat: int = 24
    """Enstrümanın M−1'deki son barı ay sonundan en fazla bu kadar önce olabilir."""
    venue: str = VENUE_BINANCE_SPOT
    """Evrenin venue'su (K-083/U17). Bir evren tek venue, tek tip taşır."""
    instrument_type: str = TIP_SPOT
    """Evrenin enstrüman tipi (K-083/U13/U17). Spot evrenle aynı sembol adı kullanan bir vadeli
    evren farklı kural kimliği alır — `sozluk()`a **yalnız Binance spot dışında** girer ki mevcut
    kuralın kimliği (`27b7a16ed0ed…`, 14 çekilişin `veri_sha256` girdisi) değişmesin."""
    _derlenmis: tuple[re.Pattern[str], ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.ust_n < 1:
            raise EvrenHatasi("ust_n ≥ 1 olmalı")
        if self.asgari_quote_hacim < 0:
            raise EvrenHatasi("asgari_quote_hacim negatif olamaz")
        if self.ay_sonu_tolerans_saat < 1:
            raise EvrenHatasi("ay_sonu_tolerans_saat ≥ 1 olmalı")
        if self.instrument_type not in ENSTRUMAN_TIPLERI:
            raise EvrenHatasi(
                f"bilinmeyen enstrüman tipi {self.instrument_type!r}; "
                f"geçerli: {list(ENSTRUMAN_TIPLERI)}"
            )
        beklenen_tip = VENUE_TIPLERI.get(self.venue)
        if beklenen_tip is not None and beklenen_tip != self.instrument_type:
            raise EvrenHatasi(
                f"venue {self.venue!r} yalnız {beklenen_tip!r} taşır, "
                f"{self.instrument_type!r} verildi"
            )
        object.__setattr__(self, "_derlenmis", tuple(re.compile(d) for d in self.haric_desenler))

    def sozluk(self) -> dict[str, Any]:
        return {
            "ust_n": self.ust_n,
            "asgari_quote_hacim": self.asgari_quote_hacim,
            "kote": self.kote,
            "haric_desenler": list(self.haric_desenler),
            "haric_tabanlar": sorted(self.haric_tabanlar),
            "ay_sonu_tolerans_saat": self.ay_sonu_tolerans_saat,
            # Binance spot dışında venue + tip kimliğe girer; spot için sözlük Faz 9 ile aynı
            # kalır (`risk`/`evren` bloğu kalıbı: "hash'e yalnız varsa girer").
            **(
                {"venue": self.venue, "instrument_type": self.instrument_type}
                if (self.venue, self.instrument_type) != (VENUE_BINANCE_SPOT, TIP_SPOT)
                else {}
            ),
        }

    @property
    def kimlik(self) -> str:
        """Kuralın içerik hash'i: hipotez kimliğinin `evren` alanı (K-051/4)."""
        return nesne_hash(self.sozluk())

    def aday_mi(self, sembol: str) -> bool:
        s = sembol.upper()
        if not s.endswith(self.kote):
            return False
        if any(d.search(s) for d in self._derlenmis):
            return False
        return s.removesuffix(self.kote) not in set(self.haric_tabanlar)


def _ay(ms: np.ndarray) -> np.ndarray:
    """Epoch ms → `YYYY-MM` metni. Metin, çünkü pandas `datetime64[M]`yi Timestamp'e çevirip ay
    aritmetiğini reddediyor; ay karşılaştırması metinde de sıralı ve kesin."""
    return np.datetime_as_string(ms.astype("datetime64[ms]").astype("datetime64[M]"), unit="M")


def aylik_ozet(df: pd.DataFrame, kimlikler: list[Enstruman]) -> pd.DataFrame:
    """Bir sembolün barlarından `(kanonik_id, ay)` başına özet.

    Sütunlar: `kanonik_id`, `sembol`, `ay` (YYYY-MM), `quote_hacim` (suspect hariç),
    `bar_sayisi`, `son_bar_ms`.
    """
    sutunlar = ["kanonik_id", "sembol", "ay", "quote_hacim", "bar_sayisi", "son_bar_ms"]
    if df.empty or not kimlikler:
        return pd.DataFrame(columns=sutunlar)

    zaman = df["open_time"].to_numpy(dtype="int64")
    baslangiclar = np.array([k.gecerli_baslangic_ms for k in kimlikler], dtype="int64")
    if (np.diff(baslangiclar) <= 0).any():
        raise EvrenHatasi("kimlikler başlangıca göre sıralı olmalı")
    idx = np.searchsorted(baslangiclar, zaman, side="right") - 1
    if (idx < 0).any():
        raise EvrenHatasi("ilk kimlikten önce bar var")

    suspect = (df["quality_status"].astype("string") == str(KaliteDurumu.SUSPECT)).to_numpy()
    calisma = pd.DataFrame(
        {
            "kanonik_id": np.array([k.kanonik_id for k in kimlikler], dtype=object)[idx],
            "sembol": kimlikler[0].sembol,
            "ay": _ay(zaman),
            "quote_hacim": np.where(suspect, 0.0, df["quote_volume"].to_numpy(dtype="float64")),
            "open_time": zaman,
        }
    )
    ozet = (
        calisma.groupby(["kanonik_id", "sembol", "ay"], sort=True)
        .agg(
            quote_hacim=("quote_hacim", "sum"),
            bar_sayisi=("open_time", "size"),
            son_bar_ms=("open_time", "max"),
        )
        .reset_index()
    )
    return ozet.loc[:, sutunlar]


def evren_tablosu(
    ozet: pd.DataFrame,
    kural: EvrenKurali,
    *,
    son_uye_ay: str,
) -> pd.DataFrame:
    """Her ay M için üye listesi, M = (ilk özet ayı + 1) … `son_uye_ay` (dahil).

    `son_uye_ay` (YYYY-MM) çağıranın beyanıdır: M−1 ayının **tamamlanmış** olduğu en son M.
    Tamamlanmamış bir ayın hacmiyle sıralama yapmak, ayın geri kalanını bilmeden karar
    vermek değil — ama o ayın **tamamını** bildiğini iddia etmek olurdu.

    Sütunlar: `ay` (YYYY-MM), `sira` (1…N), `kanonik_id`, `sembol`, `onceki_ay_quote_hacim`.
    Eşit hacimde sıra `kanonik_id` ile bozulur — deterministik.
    """
    sutunlar = ["ay", "sira", "kanonik_id", "sembol", "onceki_ay_quote_hacim"]
    if ozet.empty:
        return pd.DataFrame(columns=sutunlar)

    son = np.datetime64(son_uye_ay, "M")
    ilk = np.datetime64(str(ozet["ay"].min()), "M") + np.timedelta64(1, "M")
    adaylar = ozet[ozet["sembol"].map(kural.aday_mi)]
    tolerans_ms = kural.ay_sonu_tolerans_saat * 3_600_000

    parcalar: list[pd.DataFrame] = []
    ay = ilk
    while ay <= son:
        onceki = ay - np.timedelta64(1, "M")
        ay_basi_ms = int(ay.astype("datetime64[ms]").astype("int64"))
        secim = adaylar[
            (adaylar["ay"] == str(onceki))
            & (adaylar["quote_hacim"] >= kural.asgari_quote_hacim)
            # Son bar açılışı + 1 saat = kapanış; kapanış ay başından en fazla tolerans önce.
            & (adaylar["son_bar_ms"] >= ay_basi_ms - tolerans_ms)
        ]
        secim = secim.sort_values(
            ["quote_hacim", "kanonik_id"], ascending=[False, True], kind="stable"
        ).head(kural.ust_n)
        parcalar.append(
            pd.DataFrame(
                {
                    "ay": str(ay),
                    "sira": np.arange(1, len(secim) + 1, dtype="int64"),
                    "kanonik_id": secim["kanonik_id"].to_numpy(dtype=object),
                    "sembol": secim["sembol"].to_numpy(dtype=object),
                    "onceki_ay_quote_hacim": secim["quote_hacim"].to_numpy(dtype="float64"),
                }
            )
        )
        ay = ay + np.timedelta64(1, "M")

    return pd.concat(parcalar, ignore_index=True).loc[:, sutunlar]


def ozetleri_birlestir(ozetler: list[pd.DataFrame]) -> pd.DataFrame:
    """Sembol başına `aylik_ozet` çıktılarını tek tabloda birleştirir (boşları atlayarak)."""
    dolu = [o for o in ozetler if not o.empty]
    if not dolu:
        return pd.DataFrame(
            columns=["kanonik_id", "sembol", "ay", "quote_hacim", "bar_sayisi", "son_bar_ms"]
        )
    return pd.concat(dolu, ignore_index=True)


@dataclass(frozen=True, slots=True)
class TabloSonucu:
    """`tablo_kur` çıktısı: tablo + kayda girecek her şey. Yazma çağıranın işi."""

    tablo: pd.DataFrame
    kural: EvrenKurali
    son_uye_ay: str
    timeframe: str
    kirilma_esikleri: dict[str, Any]
    kirilmalar: list[dict[str, Any]]
    enstrumanlar: list[dict[str, Any]]
    veri_sha256: dict[str, str]


def tablo_kur(
    depo: Any,
    semboller: list[str],
    kural: EvrenKurali,
    *,
    son_uye_ay: str,
    timeframe: str = "1h",
    asgari_eksik_bar: int,
    asgari_log_oran: float,
) -> TabloSonucu:
    """Depodaki barlardan PIT evren tablosunu **hesaplar**, hiçbir şey yazmaz. (Faz 9, Faz 14)

    `sq data evren` (araştırma, `data/evren/_evren/`) ve canlı evren (`live/canli_evren.py`,
    koşunun kendi dizini) aynı fonksiyonu çağırır: iki ayrı hesap, canlı evren ile backtest
    evreninin sessizce ayrıştığı bir sistem üretirdi (K-001). Yazmanın ayrılması da bilinçli:
    canlı yenileme araştırma tablosunun **üstüne yazarsa** o tablonun hash'ini taşıyan her
    hipotezin veri kimliği bozulur.
    """
    from scryne_quant.data import kimlik as kimlik_mod

    ozetler: list[pd.DataFrame] = []
    enstrumanlar: list[dict[str, Any]] = []
    kirilma_kayit: list[dict[str, Any]] = []
    veri: dict[str, str] = {}
    for sembol in semboller:
        df = depo.oku(sembol, timeframe)
        veri[sembol] = depo.sha256(sembol, timeframe)
        kir = kimlik_mod.kirilmalar(
            df, timeframe, asgari_eksik_bar=asgari_eksik_bar,
            asgari_log_oran=asgari_log_oran, sembol=sembol,
        )
        kimlikler = kimlik_mod.kimlikleri_kur(df, timeframe, sembol, kir)
        kirilma_kayit.extend(k.sozluk() for k in kir)
        enstrumanlar.extend(e.sozluk() for e in kimlikler)
        ozetler.append(aylik_ozet(df, kimlikler))
    ozet = ozetleri_birlestir(ozetler)
    return TabloSonucu(
        tablo=evren_tablosu(ozet, kural, son_uye_ay=son_uye_ay),
        kural=kural,
        son_uye_ay=son_uye_ay,
        timeframe=timeframe,
        kirilma_esikleri={"asgari_eksik_bar": asgari_eksik_bar, "asgari_log_oran": asgari_log_oran},
        kirilmalar=kirilma_kayit,
        enstrumanlar=enstrumanlar,
        veri_sha256=dict(sorted(veri.items())),
    )


def tablo_hash(tablo: pd.DataFrame) -> str:
    """Evren tablosunun içerik hash'i — sütun sırası ve satır sırası dahil."""
    return nesne_hash(
        {
            "sutunlar": list(tablo.columns),
            "satirlar": [
                [str(v) if not isinstance(v, float) else repr(v) for v in satir]
                for satir in tablo.itertuples(index=False, name=None)
            ],
        }
    )


__all__ = [
    "KALDIRACLI_TOKEN_DESENI",
    "STABIL_FIAT_TABANLAR",
    "EvrenHatasi",
    "EvrenKurali",
    "aylik_ozet",
    "evren_tablosu",
    "ozetleri_birlestir",
    "tablo_hash",
]
