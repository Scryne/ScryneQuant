"""`JevKarari`: Jev'in tipli, mühürsüz, **yetkisiz** çıktısı. (K-074/1, K-074/2, spec §20, §33)

`Sinyal`in ikizi ama tersi: `Sinyal` risk motoruna gider, bu nesne **hiçbir yere gitmez** —
deftere yazılır ve orada biter. Ortak olan şey tip disiplini: `extra="forbid"`, yani
`miktar`, `fiyat`, `kaldirac`, `stop` gibi bir alan sızdırmaya çalışan kod derlenmez bile.
Bu nesneden `Sinyal` üreten bir fonksiyon yoktur ve yazılmayacaktır (K-067).

## Karar `choice` değil, olasılık + marj

Spike 7: P(flat) ≈ P(long) ≈ 0,45 iken argmax koşular arasında değişti. `choice` alanı bu
yüzden karar değil; kalıcı olan olasılık vektörü. `yon`, `yon_etiketle` ile **kodda** türetilir:
argmax'ın ikinciyle farkı `marj`dan küçükse `flat`. Marj `config/jev.json`da ve koşudan önce
sabit; değiştirmek yeni bir çekiliştir (K-049/2). Ham olasılıklar her kayıtta durur, etiket
sonradan başka marjla **yeniden hesaplanabilir** ama kayıttaki etiket değişmez.

## Fail-closed (K-074/5, spec §31)

`durum != GECERLI` ise `yon`, `rejim`, `kurulum`, `cekimser` **hepsi `None`** — doğrulayıcı
bunu zorlar. Geçersiz bir kayıt "flat" değildir; "karar yok"tur ve ikisi ayrı sayılır
(çekimserlik oranı ≠ hata oranı). Önceki karar hiçbir yolla taşınmaz: nesne bir önceki
kaydı bilmiyor.

## Zaman (K-074/3)

`ileriye_donuk`: karar, barın kapanışından `bayat_ms` içinde üretildi mi. Evetse model o
anda geleceği bilemez ve `leak_riski=False`. Hayırsa (replay) `leak_riski`, kesim tarihi
biliniyorsa `karar_ms < kesim`, bilinmiyorsa **her zaman `True`**.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Any, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scryne_quant.common.hash import nesne_hash
from scryne_quant.jev.sorular import BEKLENEN, KURULUM_SEVIYELERI, REJIMLER, YONLER


class KararDurumu(StrEnum):
    """Kaydın geçerliliği. `GECERLI` dışındaki her şey "karar yok" demektir."""

    GECERLI = "gecerli"
    TIMEOUT = "timeout"
    API_HATASI = "api_hatasi"
    KIMLIK_HATASI = "kimlik_hatasi"
    ORAN_SINIRI = "oran_siniri"
    SEMA_HATASI = "sema_hatasi"
    MODEL_UYUMSUZ = "model_uyumsuz"
    BAYAT_DURUM = "bayat_durum"
    EKSIK_VERI = "eksik_veri"


class Yon(StrEnum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


#: `Yon` ile `sorular.YONLER` aynı küme; test bunu bağlı tutar.
assert tuple(y.value for y in Yon) == YONLER


class SemaHatasi(ValueError):
    """Model yanıtı beklenen şemaya uymuyor: eksik soru, bilinmeyen kategori, aralık dışı."""


#: Marj kıyasındaki kayan nokta payı: 0,6 − 0,4 = 0,19999… gibi bir fark 0,2 marjını
#: "geçemedi" sayılmamalı. Pay olasılık çözünürlüğünün (0,01) çok altında.
_EPS: Final = 1e-9


def yon_etiketle(olasiliklar: Mapping[str, float], marj: float) -> Yon:
    """Olasılık vektöründen yön: en yüksek, ikinciyle farkı ≥ `marj` ise; değilse `flat`.

    Eşitlik (en yüksek iki olasılık aynı) her zaman `flat`: iki aday arasında seçim yapmak
    Spike 7'nin ölçtüğü argmax kararsızlığını kodda yeniden üretmek olurdu.
    """
    p = {y: float(olasiliklar.get(y, 0.0)) for y in YONLER}
    sirali = sorted(p.values(), reverse=True)
    p1, p2 = sirali[0], sirali[1]
    if p1 - p2 <= _EPS:  # eşitlik
        return Yon.FLAT
    en_yuksek = next(y for y in YONLER if p[y] == p1)
    if en_yuksek == Yon.FLAT or p1 - p2 + _EPS < marj:
        return Yon.FLAT
    return Yon(en_yuksek)


Olasilik = Annotated[float, Field(ge=0.0, le=1.0)]


class JevKarari(BaseModel):
    """Bir barın Jev kaydı. Değişmez; deftere yazılır, başka hiçbir katmana gitmez."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    # ------------------------------------------------------------ kimlik ve zaman
    karar_id: str
    """İçerikten türeyen kimlik: durum hash'i + soru hash'i + model + üretim anı."""

    kosu: str
    """Koşu kimliği (gölge koşusu ya da replay türetimi)."""

    sembol: Annotated[str, Field(min_length=3, max_length=32)]
    karar_ms: int
    """Karar barının **açılışı** (K-005)."""

    veri_kesimi_ms: int
    """Bar verisinin kesimi: karar barının kapanışı."""

    uretim_ms: int
    """Kararın üretildiği duvar saati (UTC epoch ms). Replay'de de gerçek üretim anı."""

    ileriye_donuk: bool
    leak_riski: bool

    # ------------------------------------------------------------ girdi kimliği
    durum_surumu: int
    durum_hash: str
    soru_sha256: str
    model_istenen: str
    model_cozulen: str | None

    # ------------------------------------------------------------ sonuç
    durum: KararDurumu
    hata: str | None = None
    gecikme_ms: int | None = None
    girdi_token: int | None = None
    cikti_token: int | None = None
    yanit_hash: str | None = None
    """Ham cevap sözlüğünün hash'i; cevabın kendisi defterde ayrı sütunda durur."""

    yon: Yon | None = None
    yon_olasiliklari: dict[str, Olasilik] | None = None
    yon_guven: Olasilik | None = None
    yon_marji: float | None = None
    rejim: str | None = None
    rejim_olasiliklari: dict[str, Olasilik] | None = None
    rejim_guven: Olasilik | None = None
    kurulum_skor: Annotated[float, Field(ge=0.0)] | None = None
    kurulum_guven: Olasilik | None = None
    cekimser: Olasilik | None = None

    # ------------------------------------------------------------ doğrulama

    @model_validator(mode="after")
    def _gecerlilik_tutarli(self) -> JevKarari:
        alanlar = (
            self.yon,
            self.yon_olasiliklari,
            self.yon_guven,
            self.rejim,
            self.rejim_olasiliklari,
            self.kurulum_skor,
            self.cekimser,
        )
        if self.durum is KararDurumu.GECERLI:
            if any(a is None for a in alanlar) or self.yon_marji is None:
                raise ValueError("GECERLI kararda yön/rejim/kurulum/çekimser alanları dolu olmalı")
            if self.hata is not None:
                raise ValueError("GECERLI kararda hata metni olamaz")
            if self.model_cozulen != self.model_istenen:
                raise ValueError("GECERLI karar yalnızca istenen modelle üretilebilir (K-074/6)")
            if set(self.yon_olasiliklari) != set(YONLER):  # type: ignore[arg-type]
                raise ValueError(f"yön olasılıkları {YONLER} kümesini taşımalı")
            if set(self.rejim_olasiliklari) != set(REJIMLER):  # type: ignore[arg-type]
                raise ValueError(f"rejim olasılıkları {REJIMLER} kümesini taşımalı")
            if self.rejim not in REJIMLER:
                raise ValueError(f"bilinmeyen rejim: {self.rejim!r}")
            if yon_etiketle(self.yon_olasiliklari, self.yon_marji) is not self.yon:  # type: ignore[arg-type]
                raise ValueError("yön etiketi olasılık vektörü + marj ile tutarsız")
        else:
            if any(a is not None for a in alanlar):
                raise ValueError(
                    f"{self.durum} kaydında karar alanı olamaz: fail-closed, karar yok (K-074/5)"
                )
            if not self.hata:
                raise ValueError("geçersiz kayıt sebebini taşımalı")
        if self.veri_kesimi_ms <= self.karar_ms:
            raise ValueError("veri kesimi karar barının açılışından sonra olmalı")
        if self.karar_ms < 1_000_000_000_000:
            raise ValueError("karar_ms UTC epoch **ms** olmalı (K-005)")
        return self

    @property
    def gecerli(self) -> bool:
        return self.durum is KararDurumu.GECERLI

    def sozluk(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# ------------------------------------------------------------------ kurucu


def karar_id(durum_hash: str, soru_sha256: str, model: str, uretim_ms: int, kosu: str) -> str:
    return nesne_hash(
        {
            "durum_hash": durum_hash,
            "soru_sha256": soru_sha256,
            "model": model,
            "uretim_ms": uretim_ms,
            "kosu": kosu,
        }
    )


def yanit_dogrula(yanit: Mapping[str, Any]) -> dict[str, Any]:
    """Düz yanıt sözlüğünü şemaya karşı doğrular; uymuyorsa `SemaHatasi`.

    Beklenen biçim (`istemci.py` üretir):
    ``{"model": str, "usage": {...}, "answers": {soru: {...}}}``. Cevap alanları SDK'nın
    verdiği isimlerle: choice → `choice`, `confidence`, `probabilities`; score → `score`,
    `confidence`; noul → `noul`.
    """
    cevaplar = yanit.get("answers")
    if not isinstance(cevaplar, Mapping):
        raise SemaHatasi("yanıtta `answers` sözlüğü yok")
    eksik = sorted(set(BEKLENEN) - set(cevaplar))
    if eksik:
        raise SemaHatasi(f"eksik cevap(lar): {', '.join(eksik)}")

    def _olasilik(x: Any, ad: str) -> float:
        try:
            p = float(x)
        except (TypeError, ValueError) as e:
            raise SemaHatasi(f"{ad}: olasılık sayı değil: {x!r}") from e
        if not 0.0 <= p <= 1.0:
            raise SemaHatasi(f"{ad}: olasılık [0,1] dışında: {p}")
        return p

    yon = cevaplar["yon"]
    rejim = cevaplar["rejim"]
    kurulum = cevaplar["kurulum"]
    cekimser = cevaplar["cekimser"]
    for ad, c, kume in (("yon", yon, YONLER), ("rejim", rejim, REJIMLER)):
        p = c.get("probabilities")
        if not isinstance(p, Mapping) or set(p) != set(kume):
            raise SemaHatasi(f"{ad}: olasılık anahtarları {kume} olmalı, gelen {p!r}")
        if c.get("choice") not in kume:
            raise SemaHatasi(f"{ad}: bilinmeyen seçim {c.get('choice')!r}")
    skor = kurulum.get("score")
    try:
        skor_f = float(skor)
    except (TypeError, ValueError) as e:
        raise SemaHatasi(f"kurulum: skor sayı değil: {skor!r}") from e
    if not 0.0 <= skor_f <= len(KURULUM_SEVIYELERI):
        raise SemaHatasi(f"kurulum: skor aralık dışı: {skor_f}")
    return {
        "yon": {
            "choice": str(yon["choice"]),
            "confidence": _olasilik(yon.get("confidence"), "yon.confidence"),
            "probabilities": {k: _olasilik(v, f"yon.{k}") for k, v in yon["probabilities"].items()},
        },
        "rejim": {
            "choice": str(rejim["choice"]),
            "confidence": _olasilik(rejim.get("confidence"), "rejim.confidence"),
            "probabilities": {
                k: _olasilik(v, f"rejim.{k}") for k, v in rejim["probabilities"].items()
            },
        },
        "kurulum": {
            "score": skor_f,
            "confidence": _olasilik(kurulum.get("confidence"), "kurulum.confidence"),
        },
        "cekimser": {"noul": _olasilik(cekimser.get("noul"), "cekimser.noul")},
    }


def _leak_riski(*, ileriye_donuk: bool, karar_ms: int, egitim_kesim_ms: int | None) -> bool:
    if ileriye_donuk:
        return False
    if egitim_kesim_ms is None:
        return True
    return karar_ms < egitim_kesim_ms


def karar_kur(
    *,
    kosu: str,
    durum: Mapping[str, Any],
    durum_hash: str,
    soru_sha256: str,
    model_istenen: str,
    uretim_ms: int,
    bayat_ms: int,
    yon_marji: float,
    egitim_kesim_ms: int | None,
    yanit: Mapping[str, Any] | None,
    durum_kodu: KararDurumu,
    hata: str | None = None,
    gecikme_ms: int | None = None,
    geriye_donuk: bool = False,
) -> JevKarari:
    """Kanonik durum + (varsa) yanıt → `JevKarari`. Şema hatası burada `SEMA_HATASI`na döner.

    `durum_kodu` istemcinin sınıflandırmasıdır (timeout, API…). `GECERLI` verildiğinde yanıt
    şemadan geçmezse kayıt `SEMA_HATASI` olur; çağıran bunu ayrıca ele almak zorunda değil —
    fail-closed varsayılan davranış.

    `geriye_donuk=True` yalnızca replay içindir: üretim anı barın çok sonrasındadır ve bu
    beklenir. Gölgede (`False`) bayat üretim `BAYAT_DURUM` ile geçersizdir.
    """
    karar_ms = int(durum["karar_ms"])
    veri_kesimi_ms = int(durum["veri_kesimi_ms"])
    ileriye_donuk = uretim_ms <= veri_kesimi_ms + bayat_ms
    ortak: dict[str, Any] = {
        "karar_id": karar_id(durum_hash, soru_sha256, model_istenen, uretim_ms, kosu),
        "kosu": kosu,
        "sembol": str(durum["sembol"]),
        "karar_ms": karar_ms,
        "veri_kesimi_ms": veri_kesimi_ms,
        "uretim_ms": uretim_ms,
        "ileriye_donuk": ileriye_donuk,
        "leak_riski": _leak_riski(
            ileriye_donuk=ileriye_donuk, karar_ms=karar_ms, egitim_kesim_ms=egitim_kesim_ms
        ),
        "durum_surumu": int(durum["surum"]),
        "durum_hash": durum_hash,
        "soru_sha256": soru_sha256,
        "model_istenen": model_istenen,
        "model_cozulen": None if yanit is None else yanit.get("model"),
        "gecikme_ms": gecikme_ms,
    }
    if yanit is not None:
        kullanim = yanit.get("usage") or {}
        ortak["girdi_token"] = kullanim.get("input_tokens")
        ortak["cikti_token"] = kullanim.get("output_tokens")
        ortak["yanit_hash"] = nesne_hash(dict(yanit))

    if durum_kodu is not KararDurumu.GECERLI:
        return JevKarari(**ortak, durum=durum_kodu, hata=hata or str(durum_kodu))

    if yanit is None:
        return JevKarari(**ortak, durum=KararDurumu.API_HATASI, hata="yanıt yok")
    if ortak["model_cozulen"] != model_istenen:
        return JevKarari(
            **ortak,
            durum=KararDurumu.MODEL_UYUMSUZ,
            hata=f"istenen {model_istenen}, çözülen {ortak['model_cozulen']}",
        )
    if not ileriye_donuk and not geriye_donuk:
        # Gölge koşusunda bayat üretim = geçersiz. Replay bilerek geriye dönüktür.
        return JevKarari(
            **ortak,
            durum=KararDurumu.BAYAT_DURUM,
            hata=f"üretim {uretim_ms} > kesim {veri_kesimi_ms} + {bayat_ms}",
        )
    try:
        c = yanit_dogrula(yanit)
    except SemaHatasi as e:
        return JevKarari(**ortak, durum=KararDurumu.SEMA_HATASI, hata=str(e))

    return JevKarari(
        **ortak,
        durum=KararDurumu.GECERLI,
        yon=yon_etiketle(c["yon"]["probabilities"], yon_marji),
        yon_olasiliklari=c["yon"]["probabilities"],
        yon_guven=c["yon"]["confidence"],
        yon_marji=yon_marji,
        rejim=c["rejim"]["choice"],
        rejim_olasiliklari=c["rejim"]["probabilities"],
        rejim_guven=c["rejim"]["confidence"],
        kurulum_skor=c["kurulum"]["score"],
        kurulum_guven=c["kurulum"]["confidence"],
        cekimser=c["cekimser"]["noul"],
    )


#: Bu modülde **bilerek olmayan** şeyler; test, `JevKarari`nın bu alanları reddettiğini ölçer.
YASAK_ALANLAR: Final[tuple[str, ...]] = (
    "miktar",
    "quantity",
    "fiyat",
    "price",
    "kaldirac",
    "leverage",
    "stop",
    "target_exposure",
    "order_type",
    "side",
)

__all__ = [
    "YASAK_ALANLAR",
    "JevKarari",
    "KararDurumu",
    "SemaHatasi",
    "Yon",
    "karar_id",
    "karar_kur",
    "yanit_dogrula",
    "yon_etiketle",
]
