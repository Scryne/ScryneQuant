"""Takvim soyutlaması — kod içi, sürümlü, içerik-hash'li katalog. (K-083/U15, R2; K-089, R3)

**İki takvim var: `24x7` (kripto, R2 seam'i) ve `fx-5x24` (K-089, R3 Paket 1(d) — gerçek FXCM
verisiyle ölçüldü).** R2 paketi bir *seam*dir, takvim motoru değil. Amaç, ileride
seanslı piyasalar (FX 5/7, endeks seansı + tatil) için ızgaranın nereden üretileceğini tek bir
yere bağlamak; **davranış değişikliği yok.** Kanıt: `24x7.izgara(...)` bugünkü `np.arange`
ızgarasıyla eleman-eleman, `beklenen_bar(...)` ise `data/dogrulama.py`nin formülüyle
(`(son − ilk) // adım + 1`) sayı sayıya aynı (`tests/unit/test_takvim.py`).

**Neden kod içi statik katalog, sağlayıcı metadata'sı değil (U15):** takvim bir deney girdisidir
(K-009). Sağlayıcının tatil tablosu zamanla değişir ve kayda hash'lenemez; buradaki katalog içeriği
ise `icerik_hash` ile kimliklidir, kayıt o hash'i taşıyabilir. Üçüncü taraf takvim kütüphanesi
(`exchange_calendars` vb.) ileride aynı arayüzün arkasında, **sürüm pinli** ve içerik-hash'li bir
adaptör olarak gelir — R3 gerçek veri spike'ı olmadan tanımlanmaz.

**R4'e ait olan ve burada yapılmayan:** `gap`/`beklenen_bar` (K-006), kimlik kırılması "eksik bar"
sayımı, `metrikler.bar_yili`, canlı bayatlık — bunlar hâlâ kendi 24/7 varsayımlarıyla çalışır ve
takvime R4'te bağlanır. `Enstruman.takvim_id` bu kataloğa **referanstır**; motor okumaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.zaman import timeframe_ms

#: `24x7` kimliği — `data/kimlik.TAKVIM_24X7` ile aynı dize; oradaki sabit enstrümanın etiketi,
#: buradaki kataloğun anahtarı. İkisi ayrı tanımlı ki `kimlik` → `takvim` bağımlılığı olmasın.
TAKVIM_24X7: Final = "24x7"
TAKVIM_FX_5X24: Final = "fx-5x24"

#: Yıl uzunluğu, milisaniye — 365,25 gün (artık yıl sessizce kaymasın). Eskiden
#: `backtest/metrikler.YIL_MS`; oradaki ad aynı nesneyi yeniden dışa verir (R4 Paket 1).
YIL_MS: Final = 365.25 * 24 * 3_600_000
HAFTA_SAAT: Final = 7 * 24

#: Haftanın günleri (`datetime.weekday`): 0 Pazartesi … 6 Pazar.
_PAZAR: Final = 6
_CUMA: Final = 4


class TakvimHatasi(ValueError):
    """Takvim sözleşmesinin ihlali ya da katalogda olmayan takvim."""


@dataclass(frozen=True, slots=True)
class Seans:
    """Haftalık seans penceresi, **yerel** saatle: `[acilis, kapanis)` — hafta içi kesintisiz.

    FX için `America/New_York` Pazar 17:00 → Cuma 17:00 (K-089): yaz saati yerel saati sabit
    tutar, UTC karşılığı kayar (ölçüldü: kış 22:00 UTC, yaz 21:00 UTC). Kural IANA bölgesine
    bağlıdır (`tzdata`); DST kuralı değişirse ızgara değişir — bilerek, uydurma ofset yok.
    """

    zaman_dilimi: str
    acilis_gun: int
    acilis_saat: int
    kapanis_gun: int
    kapanis_saat: int

    def sozluk(self) -> dict[str, Any]:
        return {
            "zaman_dilimi": self.zaman_dilimi,
            "acilis_gun": self.acilis_gun,
            "acilis_saat": self.acilis_saat,
            "kapanis_gun": self.kapanis_gun,
            "kapanis_saat": self.kapanis_saat,
        }


@dataclass(frozen=True, slots=True)
class Kapali:
    """Ölçülmüş kapalı dönem, UTC epoch ms, `[bas_ms, bit_ms)`; `kaynak` ölçümün adresi."""

    bas_ms: int
    bit_ms: int
    kaynak: str

    def sozluk(self) -> dict[str, Any]:
        return {"bas_ms": self.bas_ms, "bit_ms": self.bit_ms, "kaynak": self.kaynak}


@dataclass(frozen=True, slots=True)
class Takvim:
    """Bir takvimin **içeriği**: sürekli mi, seans kuralı, ölçülmüş kapalı dönemler, sürüm.

    - `surekli=True` (24x7): ızgara `np.arange`, kapalı dönem yok.
    - `surekli=False` → `seans` zorunlu: ızgara seans penceresiyle kesilir, `kapali` çıkarılır.
      `kapali` yalnız **ölçülmüş** dönemleri taşır (K-083/U15: uydurma tatil yok);
      `olcum_kapsami` ölçümün kapsadığı UTC aralığıdır — dışında kapalı dönem **bilinmiyor**,
      yok değil. Davranış `izgara`/`beklenen_bar`da; içerik `icerik_hash`te.
    """

    kimlik: str
    surekli: bool
    surum: int
    aciklama: str
    seans: Seans | None = None
    kapali: tuple[Kapali, ...] = ()
    olcum_kapsami: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        if not self.kimlik:
            raise TakvimHatasi("takvim kimliği boş olamaz")
        if self.surekli and (self.seans is not None or self.kapali):
            raise TakvimHatasi(f"{self.kimlik}: sürekli takvimde seans/kapalı dönem olamaz")
        if not self.surekli and self.seans is None:
            raise TakvimHatasi(f"{self.kimlik}: seanslı takvim `seans` ister (K-083/U15)")
        for k in self.kapali:
            if k.bit_ms <= k.bas_ms or not k.kaynak:
                raise TakvimHatasi(f"{self.kimlik}: kapalı dönem geçersiz {k}")
        if self.kapali and self.olcum_kapsami is None:
            raise TakvimHatasi(f"{self.kimlik}: kapalı dönem ölçüm kapsamı ister")

    def sozluk(self) -> dict[str, Any]:
        # 24x7'nin sözlüğü R2 ile aynı kalır (içerik hash'i değişmez): seans alanları yalnız
        # seanslı takvimde yazılır ("yalnız varsa" kalıbı).
        govde: dict[str, Any] = {
            "kimlik": self.kimlik,
            "surekli": self.surekli,
            "surum": self.surum,
            "aciklama": self.aciklama,
        }
        if self.seans is not None:
            govde["seans"] = self.seans.sozluk()
            govde["kapali"] = [k.sozluk() for k in self.kapali]
            govde["olcum_kapsami"] = list(self.olcum_kapsami) if self.olcum_kapsami else None
        return govde

    # ------------------------------------------------------------- seans yardımcıları

    def acik_mi(self, zamanlar: np.ndarray) -> np.ndarray:
        """UTC ms dizisi için seans içi (ve kapalı dönem dışı) maskesi. Sürekli: hep True."""
        z = np.asarray(zamanlar, dtype="int64")
        if self.surekli or self.seans is None:
            return np.ones(z.size, dtype=bool)
        yerel = pd.to_datetime(z, unit="ms", utc=True).tz_convert(self.seans.zaman_dilimi)
        gun = yerel.weekday.to_numpy()
        dakika = (yerel.hour * 60 + yerel.minute).to_numpy()
        konum = gun * 1440 + dakika
        acilis = self.seans.acilis_gun * 1440 + self.seans.acilis_saat * 60
        kapanis = self.seans.kapanis_gun * 1440 + self.seans.kapanis_saat * 60
        if acilis <= kapanis:
            maske = (konum >= acilis) & (konum < kapanis)
        else:  # hafta sonunu saran pencere (Pazar → Cuma)
            maske = (konum >= acilis) | (konum < kapanis)
        for k in self.kapali:
            maske &= ~((z >= k.bas_ms) & (z < k.bit_ms))
        return maske

    def kapali_mi(self, zamanlar: np.ndarray) -> np.ndarray:
        """Ölçülmüş kapalı dönem içindeki anlar."""
        z = np.asarray(zamanlar, dtype="int64")
        maske = np.zeros(z.size, dtype=bool)
        for k in self.kapali:
            maske |= (z >= k.bas_ms) & (z < k.bit_ms)
        return maske

    def haftalik_saat(self) -> float:
        """Haftada kaç saat açık: sürekli 168; seanslı `[açılış, kapanış)` uzunluğu (fx-5x24: 120).

        Ölçülmüş kapalı dönemler (tatil) buna girmez — yıllıklandırma kural düzeyindedir, tatil
        yılı değil; kapalı dönem sayısı yıldan yıla değişir ve `kapali` yalnız ölçülmüş yılları
        taşır (K-089/2).
        """
        if self.surekli or self.seans is None:
            return float(HAFTA_SAAT)
        acilis = self.seans.acilis_gun * 24 + self.seans.acilis_saat
        kapanis = self.seans.kapanis_gun * 24 + self.seans.kapanis_saat
        return float((kapanis - acilis) % HAFTA_SAAT or HAFTA_SAAT)

    def yillik_bar(self, timeframe_ms: int) -> float:
        """Bir yıla kaç bar sığar (R4 Paket 1). Sürekli: `YIL_MS / timeframe_ms` — R2 öncesi
        `metrikler.bar_yili` ifadesinin **aynısı** (bit-aynı). Seanslı: haftalık açık saat oranıyla
        ölçeklenir (fx-5x24 1h: 8.766 × 120/168 = 6.261,43)."""
        if timeframe_ms <= 0:
            raise TakvimHatasi(f"timeframe_ms pozitif olmalı: {timeframe_ms}")
        if self.surekli:
            return YIL_MS / timeframe_ms
        return YIL_MS / timeframe_ms * (self.haftalik_saat() / HAFTA_SAAT)

    def olcum_icinde(self, ms: int) -> bool:
        """Kapalı dönem bilgisi bu an için ölçülmüş mü (sürekli takvimde hep True)."""
        if self.surekli:
            return True
        if self.olcum_kapsami is None:
            return False
        return self.olcum_kapsami[0] <= ms < self.olcum_kapsami[1]

    @property
    def icerik_hash(self) -> str:
        """Katalog içeriğinin hash'i — kayda yazılacak kimlik (U16: `{id, icerik_hash}`)."""
        return nesne_hash(self.sozluk())

    def izgara(self, baslangic_ms: int, bitis_ms: int, timeframe: str) -> np.ndarray:
        """`[baslangic_ms, bitis_ms)` aralığındaki bar açılışları, `int64`, artan.

        24x7: `np.arange(baslangic_ms, bitis_ms, timeframe_ms)` — bugünkü ızgara semantiğinin
        kendisi (K-005: bar timestamp'i açılış). Başlangıç ızgaraya hizalı olmalı; hizasız bir
        başlangıç sessizce kaymış bir seri üretirdi.
        """
        adim = timeframe_ms(timeframe)
        if baslangic_ms % adim != 0:
            raise TakvimHatasi(
                f"{self.kimlik}: başlangıç {baslangic_ms} {timeframe} ızgarasına hizalı değil "
                "(K-005)"
            )
        if bitis_ms < baslangic_ms:
            raise TakvimHatasi(f"{self.kimlik}: bitiş başlangıçtan önce")
        surekli = np.arange(int(baslangic_ms), int(bitis_ms), adim, dtype="int64")
        if self.surekli:
            return surekli
        return surekli[self.acik_mi(surekli)]

    def beklenen_bar(self, ilk_ms: int, son_ms: int, timeframe: str) -> int:
        """`ilk_ms` ve `son_ms` açılışlı barlar **dahil** beklenen bar sayısı.

        `data/dogrulama.py` ile aynı formül: `(son − ilk) // adım + 1`. Oradaki hesap bu
        pakette buraya **taşınmadı** (R4); bu fonksiyon eşitliği testle sabitler.
        """
        adim = timeframe_ms(timeframe)
        if son_ms < ilk_ms:
            raise TakvimHatasi(f"{self.kimlik}: son bar ilk bardan önce")
        if self.surekli:
            return int((int(son_ms) - int(ilk_ms)) // adim) + 1
        ilk = (int(ilk_ms) // adim) * adim
        return int(self.izgara(ilk, int(son_ms) + 1, timeframe).size)


#: Katalog — içerik burada, sürüm numarası içerikle birlikte değişir. Yeni takvim = yeni satır +
#: K kaydı; mevcut satırın içeriğini değiştirmek `icerik_hash`i değiştirir ve eski kayıtları
#: ayırt edilir kılar (bilerek).
#: fx-5x24 ölçüm kapsamı: EURUSD FXCM m1 dosyaları 2023-11-19 22:00 → 2024-12-13 21:00 UTC
#: (55 hafta; K-089). Bu aralık dışında kapalı dönem **bilinmiyor**.
_FX_OLCUM_KAPSAMI: Final = (1_700_431_200_000, 1_734_123_600_000)

KATALOG: Final[dict[str, Takvim]] = {
    TAKVIM_24X7: Takvim(
        kimlik=TAKVIM_24X7,
        surekli=True,
        surum=1,
        aciklama="Sürekli 7/24 ızgara; kripto spot (Binance). Seans ve tatil yok.",
    ),
    TAKVIM_FX_5X24: Takvim(
        kimlik=TAKVIM_FX_5X24,
        surekli=False,
        surum=1,
        aciklama=(
            "FX 5/7: New York 17:00 dönümlü hafta (Pazar 17:00 → Cuma 17:00 yerel, hafta içi "
            "kesintisiz). FXCM EURUSD m1 ile ölçüldü (K-089): 55 haftanın hepsi 120 saat, DST'de "
            "UTC açılış 22→21; ABD/İngiltere tatillerinde (Şükran Günü, Good Friday, Easter "
            "Monday, May Day, Memorial Day, 4 Temmuz, Labor Day, Veterans Day) kapanış YOK; "
            "yalnız Noel ve Yılbaşı kapanışı ölçüldü ve `kapali`de. Kapsam dışı yıllar için tatil "
            "bilinmiyor."
        ),
        seans=Seans("America/New_York", _PAZAR, 17, _CUMA, 17),
        kapali=(
            # 2023-12-25 01:00 → 2023-12-26 05:00 UTC (NY 24 Aralık 20:00 → 26 Aralık 00:00)
            Kapali(1_703_466_000_000, 1_703_566_800_000, "EURUSD m1 2023 h52: 28 saat eksik"),
            # 2024-01-01 00:00 → 2024-01-02 05:00 UTC (NY 31 Aralık 19:00 → 2 Ocak 00:00)
            Kapali(1_704_067_200_000, 1_704_171_600_000, "EURUSD m1 2023 h53: 29 saat eksik"),
        ),
        olcum_kapsami=_FX_OLCUM_KAPSAMI,
    ),
}


def takvim(kimlik: str) -> Takvim:
    """Katalogdan takvim; olmayan kimlik hata — varsayılana düşmez (K-007 kalıbı)."""
    try:
        return KATALOG[kimlik]
    except KeyError:
        raise TakvimHatasi(
            f"bilinmeyen takvim {kimlik!r}; katalog: {sorted(KATALOG)}"
        ) from None


__all__ = [
    "HAFTA_SAAT",
    "KATALOG",
    "TAKVIM_24X7",
    "TAKVIM_FX_5X24",
    "YIL_MS",
    "Kapali",
    "Seans",
    "Takvim",
    "TakvimHatasi",
    "takvim",
]
