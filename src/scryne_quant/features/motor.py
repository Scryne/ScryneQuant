"""Özellik motoru: bildirimsel indikatör tanımları → hesaplanmış diziler. (Faz 2)

**Bu modül numpy'dan başka hiçbir şey import etmez.** pandas dahil değil — pandas dosya
okuyabilir (`read_csv`, `read_parquet`), yani strateji katmanının import edebileceği bir
modülde bulunması K-003'ün yasakladığı I/O yüzeyini geri açardı. DataFrame ↔ dizi
dönüşümü `features/barlar.py`'de yaşar ve strateji oraya erişemez.

Tanımlar neden string tabanlı ve callable değil: her backtest sonucuna config hash'i
yazılıyor (K-009). Bir callable'ın kimliği bellek adresidir; `{"indikator": "ema",
"parametreler": {"pencere": 20}}` ise çalıştırmalar arasında aynı hash'i verir. Yani
"hangi özelliklerle çalıştırıldı" sorusu altı ay sonra da cevaplanabilir kalır.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from scryne_quant.features import indikator as ind

#: Bir bar dizisi sözlüğünde bulunması gereken alanlar (`features/barlar.py` üretir).
GEREKLI_ALANLAR: Final[tuple[str, ...]] = ("open", "high", "low", "close", "volume")


class OzellikHatasi(ValueError):
    """Tanım anlamsız: bilinmeyen indikatör, eksik/fazla parametre, isim çakışması."""


@dataclass(frozen=True, slots=True)
class Kayit:
    """Bir indikatörün motora kaydı."""

    girdiler: tuple[str, ...]
    """Bar dizisi sözlüğünden okunacak alanlar, çağrı sırasıyla."""

    parametreler: tuple[str, ...]
    """Zorunlu parametre adları."""

    cikti_ekleri: tuple[str, ...]
    """Üretilen sütun adlarının sonekleri. Tek çıktılıysa tek boş sonek."""

    fonksiyon: Callable[..., Any]


#: İndikatör kayıt defteri. Yeni bir indikatör buraya yazılmadan tanım kabul edilmez —
#: "her yerden çağrılabilen" bir motor, hangi özelliğin nereden geldiğini kaybettirir.
DEFTER: Final[dict[str, Kayit]] = {
    "sma": Kayit(("close",), ("pencere",), ("",), ind.sma),
    "ema": Kayit(("close",), ("pencere",), ("",), ind.ema),
    "rsi": Kayit(("close",), ("pencere",), ("",), ind.rsi),
    "atr": Kayit(("high", "low", "close"), ("pencere",), ("",), ind.atr),
    "true_range": Kayit(("high", "low", "close"), (), ("",), ind.gercek_aralik),
    "hacim_sma": Kayit(("volume",), ("pencere",), ("",), ind.hacim_ortalamasi),
    # Aynı fonksiyon, farklı sütun: **kote** para birimindeki hacim. Faz 10'da eklendi
    # (K-057) çünkü cross-sectional bir sıralamada baz varlık hacmi karşılaştırılamaz —
    # 1 BTC ile 1 DOGE aynı sayı değildir. Evren kuralı da (`data/evren.py`) `quote_volume`
    # topluyor; sıralamanın onunla aynı büyüklüğü kullanması, iki katmanın aynı şeyi
    # ölçmesini sağlıyor. Hesap `hacim_sma` ile birebir aynı fonksiyon olduğu için ayrı bir
    # referans doğrulaması gerekmiyor; `test_ozellik_motoru.py` ikisinin aynı girdide aynı
    # çıktıyı verdiğini kontrol ediyor.
    "kote_hacim_sma": Kayit(("quote_volume",), ("pencere",), ("",), ind.hacim_ortalamasi),
    "en_yuksek": Kayit(("high",), ("pencere",), ("",), ind.en_yuksek),
    "en_dusuk": Kayit(("low",), ("pencere",), ("",), ind.en_dusuk),
    "roc": Kayit(("close",), ("pencere",), ("",), ind.roc),
    # Girdisi bar fiyatı değil **funding** olan iki indikatör (K-042). `funding` alanı
    # bar çerçevesine `data/funding.py::barlara_hizala` tarafından nedensel olarak
    # ekleniyor; yoksa `hesapla` açık bir hata veriyor.
    "funding_persentil": Kayit(("funding",), ("pencere",), ("",), ind.persentil_sirasi),
    "funding_kumulatif": Kayit(("funding",), ("pencere",), ("",), ind.kumulatif),
    "funding_kumulatif_persentil": Kayit(
        ("funding",), ("birikim", "pencere"), ("",), ind.kumulatif_persentil
    ),
    "bollinger": Kayit(
        ("close",),
        ("pencere", "katsayi"),
        ("_alt", "_orta", "_ust"),
        ind.bollinger,
    ),
}


@dataclass(frozen=True, slots=True)
class OzellikTanimi:
    """Bir özelliğin bildirimsel tarifi.

    `ad` ctx'te görünen isimdir. Çok çıktılı indikatörlerde (Bollinger) sütunlar
    `ad + sonek` olur: ``bb`` tanımı ``bb_alt``, ``bb_orta``, ``bb_ust`` üretir.
    """

    ad: str
    indikator: str
    parametreler: Mapping[str, float | int] = ()  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.ad or not self.ad.isidentifier():
            raise OzellikHatasi(f"özellik adı geçerli bir tanımlayıcı olmalı: {self.ad!r}")
        kayit = DEFTER.get(self.indikator)
        if kayit is None:
            raise OzellikHatasi(
                f"bilinmeyen indikatör {self.indikator!r}; kayıtlı: {', '.join(sorted(DEFTER))}"
            )
        verilen = set(dict(self.parametreler))
        gerekli = set(kayit.parametreler)
        if verilen != gerekli:
            eksik = ", ".join(sorted(gerekli - verilen)) or "yok"
            fazla = ", ".join(sorted(verilen - gerekli)) or "yok"
            raise OzellikHatasi(
                f"{self.ad}: parametre uyuşmuyor (eksik: {eksik}; tanınmayan: {fazla})"
            )
        # Frozen dataclass; `parametreler`i kanonik ve hashlenebilir hâle çeviriyoruz ki
        # aynı tanım her zaman aynı config hash'ini versin (K-009).
        object.__setattr__(self, "parametreler", tuple(sorted(dict(self.parametreler).items())))

    @property
    def kayit(self) -> Kayit:
        return DEFTER[self.indikator]

    @property
    def sutunlar(self) -> tuple[str, ...]:
        """Bu tanımın üreteceği sütun adları."""
        return tuple(self.ad + ek for ek in self.kayit.cikti_ekleri)

    def sozluk(self) -> dict[str, Any]:
        """Sonuç kaydına (K-009) yazılabilir, deterministik gösterim."""
        return {
            "ad": self.ad,
            "indikator": self.indikator,
            "parametreler": dict(self.parametreler),
        }


def hesapla(
    bar_dizileri: Mapping[str, np.ndarray],
    tanimlar: Sequence[OzellikTanimi],
) -> dict[str, np.ndarray]:
    """Tanımları bar dizileri üzerinde hesaplar.

    Tüm seri bir kerede, ileri yönde hesaplanır. Bu bir kısayol değil, sözleşmenin
    parçası: `indikator.py`'deki her fonksiyon nedenseldir (`çıktı[t]` yalnızca
    `girdi[0..t]`'ye bağlıdır), bu yüzden tamamını önden hesaplamak, bar bar hesaplamakla
    aynı sayıları verir. Bunun doğruluğu varsayılmıyor — `tests/unit/test_indikator.py`
    her indikatör için geleceği bozup çıktının değişmediğini ölçüyor.
    """
    eksik = [a for a in GEREKLI_ALANLAR if a not in bar_dizileri]
    if eksik:
        raise OzellikHatasi(f"bar dizilerinde eksik alan(lar): {', '.join(eksik)}")

    out: dict[str, np.ndarray] = {}
    for tanim in tanimlar:
        kayit = tanim.kayit
        cakisan = [s for s in tanim.sutunlar if s in out]
        if cakisan:
            raise OzellikHatasi(f"özellik adı iki kez tanımlanmış: {', '.join(cakisan)}")

        yok = [a for a in kayit.girdiler if a not in bar_dizileri]
        if yok:
            raise OzellikHatasi(
                f"{tanim.ad}: `{tanim.indikator}` şu bar alan(lar)ını istiyor ama "
                f"çerçevede yok: {', '.join(yok)}. `funding` için bar çerçevesi "
                f"`data.funding.barlara_hizala` ile hazırlanmalı (K-042)."
            )
        girdiler = [np.asarray(bar_dizileri[alan], dtype=np.float64) for alan in kayit.girdiler]
        sonuc = kayit.fonksiyon(*girdiler, **dict(tanim.parametreler))

        if len(kayit.cikti_ekleri) == 1:
            out[tanim.ad] = sonuc
        else:
            for sutun, dizi in zip(tanim.sutunlar, sonuc, strict=True):
                out[sutun] = dizi

    for ad, dizi in out.items():
        dizi.flags.writeable = False  # ctx'e giden diziler yazılamaz olmalı
        if dizi.dtype != np.float64:  # pragma: no cover - defter float64 üretiyor
            raise OzellikHatasi(f"{ad}: float64 bekleniyordu, {dizi.dtype} geldi")
    return out
