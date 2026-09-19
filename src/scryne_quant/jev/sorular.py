"""Dondurulmuş soru seti: Jev'e sorulan dört yargı ve `SORU_SHA256`. (K-074/6, K-061 kalıbı)

**Soru metni donmuş.** Spec'in `prompt_version`ı bu projede `SORU_SHA256`: metnin, ölçütlerin
ve model pininin kanonik hash'i. Testte sabitleniyor; değiştirmek testi kırar ve bu bilinçli:
soru setini **sonuca bakıp** değiştirmek yeni bir çekiliştir (K-049/2, K-039) ve hipotez
defterine satır ister. Düzeltme gerekiyorsa sürüm artar, eski kayıtlar eski hash'le kalır.

**Dört soru, sıfır sayısal eşik.** Spike 7 ölçtü: Jev "%1'den yakın mı" gibi sayısal
kıyaslarda yanılıyor. Buradaki sorular yalnızca durumdaki **etiketleri** okuyarak
cevaplanabilir; hesap isteyen hiçbir şey sorulmuyor. Spec'in `key_factors`ı Jev'den
istenmiyor — onlar `durum.py`nin ürettiği etiketler.

**Ufuk sabit: 4 bar (4 saat).** `yon` sorusu bu ufka bağlı; `config/jev.json::sonuc`
birincil ufuk aynı sayı. Soruyu ufuktan bağımsız sormak, ölçülen şeyi belirsiz bırakırdı.

Sorular SDK nesnesi değil, düz sözlük: hash SDK sürümüne bağlı olmamalı ve bu modül
`typesafe`i import etmemeli (`test_jev_izolasyon.py`). SDK sözlüğü `system_one`da
doğrudan kabul ediyor (`research/gizli_tekrar.py` aynı yolu kullanıyor).
"""

from __future__ import annotations

from typing import Any, Final

from scryne_quant.common.hash import nesne_hash

#: Soru setinin sürümü. Metin değişirse artar; `SORU_SHA256` zaten değişir, bu okunur etiket.
SORU_SURUMU: Final = 1

#: `yon` sorusunun ufku, karar barı cinsinden. `config/jev.json::sonuc.birincil_ufuk_bar` ile
#: aynı olmalı (testle bağlı).
UFUK_BAR: Final = 4

YONLER: Final[tuple[str, ...]] = ("long", "short", "flat")
REJIMLER: Final[tuple[str, ...]] = (
    "trend_yukari",
    "trend_asagi",
    "aralik",
    "yuksek_volatilite",
    "belirsiz",
)
KURULUM_SEVIYELERI: Final[tuple[str, ...]] = ("dusuk", "orta", "yuksek")

_ORTAK: Final = (
    "State, BTCUSDT icin kapanmis 1h karar barinin (`1h`) ve karar aninda kapanmis 4h barlarin "
    "(`4h_kapanmis`) kodla hesaplanmis teknik ozetidir; fiyat dizisi verilmez. Sayilari "
    "karsilastirma ya da hesap yapma; etiketleri (`ustunde`/`altinda`, bantlar, `yapi`) yorumla. "
    "`eksik` etiketi 'veri yok' demektir, sifir degil; `bayat` guncel olmayan funding demektir."
)

SORULAR: Final[dict[str, dict[str, Any]]] = {
    "yon": {
        "type": "choice",
        "instructions": {
            "gorev": _ORTAK + " Sonraki 4 saatlik ufukta fiyatin beklenen yonu hangisi?",
            "dikkat": (
                "Kararsizsan flat sec; long ya da short yalnizca 1h ve 4h ozeti ayni yonu "
                "destekliyorsa. Eksik ya da bayat girdi varsa flat'e yaklas."
            ),
        },
        "criteria": {
            "long": {"what": "Fiyatin 4 saat icinde yukari gitmesi daha olasi."},
            "short": {"what": "Fiyatin 4 saat icinde asagi gitmesi daha olasi."},
            "flat": {"what": "Belirgin bir yon yok, sinyaller celisiyor ya da girdi yetersiz."},
        },
    },
    "rejim": {
        "type": "choice",
        "instructions": _ORTAK + " Su anki piyasa rejimi hangisi?",
        "criteria": {
            "trend_yukari": {
                "what": "EMA'lar yukari sirali (kapanis > ema20 > ema50 > ema200), yapi yukselen "
                "zirve ve dip."
            },
            "trend_asagi": {"what": "EMA'lar asagi sirali, yapi alcalan zirve ve dip."},
            "aralik": {"what": "Yon yok; fiyat bantlarin icinde, yapi karisik."},
            "yuksek_volatilite": {"what": "Volatilite bandi yuksek ve yon belirsiz."},
            "belirsiz": {"what": "Ozet celiskili, eksik ya da bayat."},
        },
    },
    "kurulum": {
        "type": "score",
        "instructions": _ORTAK + " Yon ne olursa olsun, bu durum ne kadar net bir kurulum?",
        "criteria": [
            {"dusuk": "1h ve 4h celisiyor ya da hicbir etiket belirgin degil."},
            {"orta": "Bir timeframe net, digeri notr."},
            {
                "yuksek": "1h ve 4h ayni yonde, momentum ve yapi uyumlu, volatilite bandi "
                "asiri degil."
            },
        ],
    },
    "cekimser": {
        "type": "noul",
        "instructions": _ORTAK
        + " Bu durumda yon karari VERMEMEK daha dogru mu (celiskili, yetersiz, eksik ya da "
        "bayat girdi)?",
    },
}


#: Soru seti + model pininin hash'i. Model buraya `sorular.py`den değil ayarlardan gelir;
#: hash ayarlardaki modelle **birlikte** hesaplanır ki aynı metin farklı modelle farklı
#: sürüm sayılsın (K-049/2: yeni model = yeni deney).
def soru_sha256(model: str) -> str:
    return nesne_hash(
        {"surum": SORU_SURUMU, "ufuk_bar": UFUK_BAR, "model": model, "sorular": SORULAR}
    )


#: Yanıtta beklenen soru → tip. Şema doğrulaması (`karar.py`) buna bakar.
BEKLENEN: Final[dict[str, str]] = {ad: s["type"] for ad, s in SORULAR.items()}


__all__ = [
    "BEKLENEN",
    "KURULUM_SEVIYELERI",
    "REJIMLER",
    "SORULAR",
    "SORU_SURUMU",
    "UFUK_BAR",
    "YONLER",
    "soru_sha256",
]
