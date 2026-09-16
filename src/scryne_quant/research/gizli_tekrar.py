"""Gizli tekrar çekiliş dedektörü. (K-061, K-039)

**Kapatmaya çalıştığı boşluk.** K-039 çekilişleri sayıyor, K-051 bütçeyle sınırlıyor. İkisi
de kimliğe bakıyor ve kimlik aynı mekanizmanın **başka adla** yeniden denenmesini görmez:
tek sembollü funding filtresini evren kesitine taşıyıp yeni bir programda "yeni hipotez"
diye kaydetmek, hiçbir kuralı çiğnemeden aynı soruyu tekrar sormaktır. Bunu yakalamak metni
anlamayı gerektiriyor; kural ya da hash yetmiyor.

**Ne yapar.** Yeni kaydın özetini defterdeki her önceki kayıtla karşılaştırır. Her çift
için Jev'e tek bir Choice sorulur (`ayni_mekanizma` / `parametre_varyasyonu` / `farkli`),
hepsi paralel. Kod `ilgili = P(ayni) + P(param)` toplar ve iki eşikle kademelendirir.

**Ne yapmaz.** Kaydı engellemez, çekiliş sayısını değiştirmez, alım-satım kararına ya da
özelliğe girmez (K-049/1). Uyarır; karar Scryne'ındır. Bu yüzden K-049'un dondurma ve kesim
tarihi kuralları buraya uygulanmaz: piyasa hakkında bir şey söylemiyor, dolayısıyla
look-ahead taşıyamaz (K-061/2).

**Soru metni donmuş.** Eşikler (0,80 / 0,50) bu metinle ölçüldü (2026-09-16 spike'ı). Metni
değiştirmek eşiği geçersiz kılar; `SORU_SHA256` testle korunuyor. Değişiklik yeni bir
spike ve yeni bir K-kaydı ister.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final, Protocol

from scryne_quant.common.hash import nesne_hash
from scryne_quant.common.zaman import simdi_ms, utc_str

#: Çözülmüş sürüm; `jev-latest` zamanla kayıyor ve eski sürümler API'den kalkıyor.
#: Kalkarsa eşikler yeni sürümde yeniden ölçülür (K-061/3).
MODEL: Final = "jev-1.13.0"

#: Spike'ta ölçülen eşikler (K-061/1). Bilinen benzerler 0,81–1,00, gerçek farklılar ≤0,17;
#: sınırda akraba kayıtlar ve mekanizmasız idari gerekçeler 0,40–0,66 bandında.
ESIK_UYARI: Final = 0.80
ESIK_INCELE: Final = 0.50

#: Bir istekteki azami karşılaştırma. Spike'ta ölçülen en büyük istek 48 kayıt (~53k token).
PARCA_BOYU: Final = 48

#: Modele giden alanlar. Kimlik, hash ve zaman mekanizma hakkında bir şey söylemez; yalnızca
#: gürültü ve token.
ALANLAR: Final[tuple[str, ...]] = (
    "strateji",
    "program",
    "timeframe",
    "secim",
    "portfoy",
    "izgara",
    "gerekce",
)

KATEGORILER: Final[tuple[str, ...]] = ("ayni_mekanizma", "parametre_varyasyonu", "farkli")

VARSAYILAN_KAYIT_KOKU: Final = Path("runs/gizli_tekrar")

# Spike metni birebir (ASCII Türkçe dahil). Değiştirme: modül docstring'i.
_GOREV: Final = (
    "`yeni` hipotez kaydini `onceki.{h}` kaydiyla karsilastir. Karar: yeni kayit, onceki "
    "kaydin test ettigi MEKANIZMAYI yeniden mi test ediyor? Mekanizma = hangi bilginin neden "
    "getiri ongordugu iddiasi. Strateji adina, program adina veya metnin benzerligine degil, "
    "test edilen nedensel iddiaya bak."
)
_DIKKAT: Final = (
    "Gerekce metinleri ayni toplu kayittan kopyalanmis olabilir; ayni metin tek basina ayni "
    "mekanizma demek degildir, strateji ve izgara farkina da bak. Ad degistirmek, tek "
    "sembolden evren kesitine tasimak veya filtreyi dislamaya cevirmek mekanizmayi degistirmez."
)
KRITERLER: Final[dict[str, dict[str, Any]]] = {
    "ayni_mekanizma": {
        "what": "Ayni nedensel iddia ve ayni bilgi kaynagi; degisen sey ad, kapsam (tek sembol "
        "-> evren kesiti), portfoy sarmalayicisi ya da uygulama bicimi (giris filtresi -> uyeyi "
        "dislama).",
        "not_for": "Mantik birebir ayni ve fark yalnizca sayisal ayar ise parametre_varyasyonu. "
        "Ayni veriyi kullanan ama farkli bir iddia ise farkli.",
        "examples": [
            "Tek sembollu kirilimda yuksek funding'de girmeme vs evren uyelerinden yuksek "
            "funding'lileri dislama",
            "Momentum stratejisinin baska isimle, ayni gerekceyle yeniden kaydi",
        ],
    },
    "parametre_varyasyonu": {
        "what": "Ayni strateji mantigi ve ayni mekanizma; fark yalnizca pencere, esik, timeframe, "
        "yeniden dengeleme sikligi, izgara araligi veya skorun zaman olcegi gibi ayarlarda.",
        "not_for": "Bilgi kaynagi ya da nedensel iddia degisiyorsa farkli.",
        "examples": [
            "Goreli guc haftalik dengeleme vs ayni goreli guc aylik dengeleme",
            "Ayni kesisim stratejisi 4h vs 1d",
        ],
    },
    "farkli": {
        "what": "Farkli bilgi kaynagi veya farkli nedensel iddia; ayni evren, ayni iskelet veya "
        "ayni izgara sabitlerini kullansa bile.",
        "not_for": "Yalnizca ad, kapsam veya ayar farki olan kayitlar.",
        "examples": [
            "Kisa vadeli ters donus vs orta vadeli goreli guc",
            "VIX stres engeli vs funding kalabalik dislamasi",
            "Parametre secim yontemi (plato) iddiasi vs timeframe maliyet iddiasi",
        ],
    },
}

#: Soru şablonunun hash'i. Eşikler bu metne bağlı; test değişikliği yakalar.
SORU_SHA256: Final = nesne_hash(
    {"gorev": _GOREV, "dikkat": _DIKKAT, "kriterler": KRITERLER, "model": MODEL}
)


class Istemci(Protocol):
    """`typesafe_sdk.TypeSafeClient`in burada kullanılan yüzü (testte sahtesi geçer)."""

    def system_one(
        self, state: Any, questions: Mapping[str, Any], *, model: str | None = ...
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class Bulgu:
    sira: int
    strateji: str
    program: str
    karar: str
    guven: float
    ayni: float
    param: float
    ilgili: float
    seviye: str
    """`uyari` (≥ ESIK_UYARI) · `incele` (≥ ESIK_INCELE) · `temiz`."""


def ozet(kayit: Mapping[str, Any]) -> dict[str, Any]:
    """Kaydın modele giden kısmı; boş alanlar atılır."""
    return {k: kayit[k] for k in ALANLAR if kayit.get(k) not in (None, "", [], {})}


def soru(sira: int) -> dict[str, Any]:
    h = f"h{sira}"
    return {
        "type": "choice",
        "instructions": {"gorev": _GOREV.replace("{h}", h), "dikkat": _DIKKAT},
        "criteria": KRITERLER,
    }


def istek_kur(
    yeni: Mapping[str, Any], onceki: Sequence[tuple[int, Mapping[str, Any]]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """`(state, questions)` — `onceki` `(sira, kayit)` çiftleri."""
    state = {"yeni": ozet(yeni), "onceki": {f"h{s}": ozet(k) for s, k in onceki}}
    return state, {f"h{s}": soru(s) for s, _ in onceki}


def seviye(ilgili: float) -> str:
    if ilgili >= ESIK_UYARI:
        return "uyari"
    if ilgili >= ESIK_INCELE:
        return "incele"
    return "temiz"


def bulgu(sira: int, kayit: Mapping[str, Any], cevap: Any) -> Bulgu:
    p = cevap.probabilities
    ayni, param = float(p.get("ayni_mekanizma", 0.0)), float(p.get("parametre_varyasyonu", 0.0))
    # Kademe kodda: toplam, iki "tekrar" kategorisini tek bir soruya bağlar (K-061/1).
    ilgili = min(1.0, ayni + param)
    return Bulgu(
        sira=sira,
        strateji=kayit.get("strateji", ""),
        program=kayit.get("program") or "",
        karar=cevap.choice,
        guven=float(cevap.confidence),
        ayni=ayni,
        param=param,
        ilgili=ilgili,
        seviye=seviye(ilgili),
    )


def kontrol_et(
    istemci: Istemci,
    yeni: Mapping[str, Any],
    defter: Sequence[Mapping[str, Any]],
    *,
    kayit_koku: Path | None = VARSAYILAN_KAYIT_KOKU,
) -> dict[str, Any]:
    """Yeni kaydı defterdeki her önceki kayıtla karşılaştırır.

    `defter` sıralı kayıtlar (1'den numaralanır). Dönen bulgular `ilgili`ye göre azalan.
    `kayit_koku` verilirse istek, çözülen model ve cevaplar oraya dondurulur: uyarının
    kayıt anında ne söylediği sonradan izlenebilsin.
    """
    ciftler = list(enumerate(defter, start=1))
    bulgular: list[Bulgu] = []
    istekler: list[dict[str, Any]] = []
    for bas in range(0, len(ciftler), PARCA_BOYU):
        parca = ciftler[bas : bas + PARCA_BOYU]
        state, sorular = istek_kur(yeni, parca)
        yanit = istemci.system_one(state, sorular, model=MODEL)
        if yanit.model != MODEL:
            raise RuntimeError(f"istenen model {MODEL}, çözülen {yanit.model}; eşikler geçersiz")
        cevaplar = yanit.choices
        for s, k in parca:
            bulgular.append(bulgu(s, k, cevaplar[f"h{s}"]))
        istekler.append(
            {
                "state_sha256": nesne_hash(state),
                "questions_sha256": nesne_hash(sorular),
                "usage": {
                    "input_tokens": getattr(yanit.usage, "input_tokens", None),
                    "output_tokens": getattr(yanit.usage, "output_tokens", None),
                },
                "cevaplar": {
                    q: {
                        "choice": c.choice,
                        "confidence": c.confidence,
                        "probabilities": c.probabilities,
                    }
                    for q, c in cevaplar.items()
                },
            }
        )
    bulgular.sort(key=lambda b: (-b.ilgili, b.sira))
    zaman = simdi_ms()
    govde: dict[str, Any] = {
        "model": MODEL,
        "soru_sha256": SORU_SHA256,
        "esikler": {"uyari": ESIK_UYARI, "incele": ESIK_INCELE},
        "zaman_ms": zaman,
        "zaman_utc": utc_str(zaman),
        "yeni": ozet(yeni),
        "karsilastirma": len(bulgular),
        "uyari": sum(b.seviye == "uyari" for b in bulgular),
        "incele": sum(b.seviye == "incele" for b in bulgular),
        "bulgular": [asdict(b) for b in bulgular],
    }
    if kayit_koku is not None and bulgular:
        kayit_koku = Path(kayit_koku)
        kayit_koku.mkdir(parents=True, exist_ok=True)
        dosya = kayit_koku / f"{zaman}_{nesne_hash(govde['yeni'])[:12]}.json"
        dosya.write_text(
            json.dumps(
                {**govde, "istekler": istekler}, ensure_ascii=False, indent=2, sort_keys=True
            ),
            encoding="utf-8",
            newline="\n",
        )
        govde["kayit"] = str(dosya)
    return govde


__all__ = [
    "ALANLAR",
    "ESIK_INCELE",
    "ESIK_UYARI",
    "KATEGORILER",
    "KRITERLER",
    "MODEL",
    "PARCA_BOYU",
    "SORU_SHA256",
    "Bulgu",
    "bulgu",
    "istek_kur",
    "kontrol_et",
    "ozet",
    "seviye",
    "soru",
]
