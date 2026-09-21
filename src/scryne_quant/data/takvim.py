"""Takvim soyutlaması — kod içi, sürümlü, içerik-hash'li katalog. (K-083/U15, ROADMAP-RESET R2)

**Bugün tek uygulama var: `24x7`**, ve bu paket bir *seam*dir, takvim motoru değil. Amaç, ileride
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

from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.zaman import timeframe_ms

#: `24x7` kimliği — `data/kimlik.TAKVIM_24X7` ile aynı dize; oradaki sabit enstrümanın etiketi,
#: buradaki kataloğun anahtarı. İkisi ayrı tanımlı ki `kimlik` → `takvim` bağımlılığı olmasın.
TAKVIM_24X7: Final = "24x7"


class TakvimHatasi(ValueError):
    """Takvim sözleşmesinin ihlali ya da katalogda olmayan takvim."""


@dataclass(frozen=True, slots=True)
class Takvim:
    """Bir takvimin **içeriği**: sürekli mi, sürümü ne. Davranış `izgara`/`beklenen_bar`da.

    Yalnız `surekli=True` destekleniyor (24x7). Seans/tatil alanları burada yok — olmayan
    davranış için alan açmak "kodda geçiyor" yanılgısı üretirdi.
    """

    kimlik: str
    surekli: bool
    surum: int
    aciklama: str

    def __post_init__(self) -> None:
        if not self.kimlik:
            raise TakvimHatasi("takvim kimliği boş olamaz")
        if not self.surekli:
            raise TakvimHatasi(
                f"{self.kimlik}: seanslı takvim bu sürümde tanımlı değil (K-083/U15 — R3/R4)"
            )

    def sozluk(self) -> dict[str, Any]:
        return {
            "kimlik": self.kimlik,
            "surekli": self.surekli,
            "surum": self.surum,
            "aciklama": self.aciklama,
        }

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
        return np.arange(int(baslangic_ms), int(bitis_ms), adim, dtype="int64")

    def beklenen_bar(self, ilk_ms: int, son_ms: int, timeframe: str) -> int:
        """`ilk_ms` ve `son_ms` açılışlı barlar **dahil** beklenen bar sayısı.

        `data/dogrulama.py` ile aynı formül: `(son − ilk) // adım + 1`. Oradaki hesap bu
        pakette buraya **taşınmadı** (R4); bu fonksiyon eşitliği testle sabitler.
        """
        adim = timeframe_ms(timeframe)
        if son_ms < ilk_ms:
            raise TakvimHatasi(f"{self.kimlik}: son bar ilk bardan önce")
        return int((int(son_ms) - int(ilk_ms)) // adim) + 1


#: Katalog — içerik burada, sürüm numarası içerikle birlikte değişir. Yeni takvim = yeni satır +
#: K kaydı; mevcut satırın içeriğini değiştirmek `icerik_hash`i değiştirir ve eski kayıtları
#: ayırt edilir kılar (bilerek).
KATALOG: Final[dict[str, Takvim]] = {
    TAKVIM_24X7: Takvim(
        kimlik=TAKVIM_24X7,
        surekli=True,
        surum=1,
        aciklama="Sürekli 7/24 ızgara; kripto spot (Binance). Seans ve tatil yok.",
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


__all__ = ["KATALOG", "TAKVIM_24X7", "Takvim", "TakvimHatasi", "takvim"]
