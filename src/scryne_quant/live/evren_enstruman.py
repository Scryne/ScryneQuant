"""Canlı evren girişinde enstrüman kimliği + U17 işlem sözleşmesi doğrulaması. (K-085, İz G)

Araştırma yolu enstrümanı `kimlikleri_kur` ile depodaki barlardan türetir; canlı yol barları
REST/akıştan alır ve **`Enstruman` nesnesi görmüyordu** (K-083 "açık kalan", K-084/9). Bu modül
o boşluğu, yeni bir kimlik kaynağı **uydurmadan** kapatır: kimlik, evren tablosunun yanındaki
`kimlik-katalogu.json`dan okunur — yani `sq evren tablo`nun ürettiği, PIT tablosuyla aynı
üretimden çıkan katalog. Tabloda üye olup katalogda olmayan sembol hata; katalog dışı kimlik
üretilmez.

Katalog kimlik taşır, sözleşme taşımaz: `tick_size`/`lot_size` orada `None` (bilinmiyor). U17'ye
göre paper/live'da bunlar **borsadan** doldurulur (`SembolKurallari`, K-046 kalıbı) ve
`Enstruman.islem_icin_dogrula()` fail-closed çalışır: eksik alan ya da `TRADING` dışı sembol →
koşu açılmaz. Doğrulama iki noktada: açılışta (en son ayın üyeleri = işlem görebilecek küme) ve
aylık yenilemede evrene **yeni giren** üyeler için (`EvrenKosucu.enstruman_dogrulayici`).
Geçmiş ayların artık üye olmayan sembolleri doğrulanmaz — onlar yalnız ısınma verisidir ve
borsada kuralları olmayabilir (delist).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from scryne_quant.data.kimlik import Enstruman, KimlikHatasi
from scryne_quant.exchange.kurallar import SembolKurallari

#: Katalog dosyası, evren tablosunun (`<kural>.parquet`) yanında (`cli/main.py sq evren tablo`).
KATALOG_ADI = "kimlik-katalogu.json"

#: Katalog kaydında `Enstruman` alanı olmayan, insan için yazılan anahtarlar.
_TUREV_ANAHTARLAR = frozenset({"gecerli_baslangic", "gecerli_bitis"})

KuralKaynagi = Callable[[str], SembolKurallari]


class EvrenEnstrumanHatasi(ValueError):
    """Canlı evren için enstrüman kimliği kurulamadı ya da işlem sözleşmesi sağlanmadı."""


def katalog_yolu(tablo_yolu: str | Path) -> Path:
    return Path(tablo_yolu).parent / KATALOG_ADI


def katalogu_oku(yol: str | Path) -> dict[str, list[Enstruman]]:
    """`kimlik-katalogu.json` → sembol → kimlik segmentleri (başlangıca göre sıralı).

    Kayıtlar v1 (Paket 1 öncesi) ya da v2 olabilir; eksik v2 alanları `Enstruman`
    varsayılanına düşer (Binance spot kripto — kataloğun tek üretim yolu bu). Bilinmeyen
    anahtar `Enstruman` kurucusunda hata: katalog şeması sessizce genişleyemez.
    """
    p = Path(yol)
    if not p.is_file():
        raise EvrenEnstrumanHatasi(f"kimlik kataloğu yok: {p} (evren tablosuyla birlikte üretilir)")
    try:
        govde = json.loads(p.read_text(encoding="utf-8"))
        kayitlar = govde["enstrumanlar"]
    except (ValueError, KeyError, TypeError) as hata:
        raise EvrenEnstrumanHatasi(f"kimlik kataloğu bozuk: {p}: {hata}") from hata
    out: dict[str, list[Enstruman]] = {}
    for kayit in kayitlar:
        try:
            e = Enstruman(**{k: v for k, v in kayit.items() if k not in _TUREV_ANAHTARLAR})
        except (TypeError, KimlikHatasi) as hata:
            raise EvrenEnstrumanHatasi(
                f"katalog kaydı geçersiz ({kayit.get('kanonik_id')}): {hata}"
            ) from hata
        out.setdefault(e.sembol, []).append(e)
    for segmentler in out.values():
        segmentler.sort(key=lambda e: e.gecerli_baslangic_ms)
    return out


def enstrumanlari_kur(
    katalog: Mapping[str, list[Enstruman]],
    semboller: Any,
    kural_kaynagi: KuralKaynagi,
) -> dict[str, list[Enstruman]]:
    """Üye semboller için işlem-hazır kimlikler: katalog + borsa kuralları + U17 doğrulaması.

    Her sembol için: katalogda olmalı; `SembolKurallari` `TRADING` olmalı; `tick_size`/`lot_size`
    kurallardan yazılır (tüm segmentlere — kural sembolündür); `islem_icin_dogrula()` geçmeli.
    Herhangi biri sağlanmazsa `EvrenEnstrumanHatasi` — **fail closed**, kısmi sonuç yok.
    """
    out: dict[str, list[Enstruman]] = {}
    for sembol in sorted(semboller):
        segmentler = katalog.get(sembol)
        if not segmentler:
            raise EvrenEnstrumanHatasi(
                f"{sembol}: evren tablosunda üye ama kimlik kataloğunda yok (K-083/U13)"
            )
        kural = kural_kaynagi(sembol)
        if not kural.islenebilir:
            raise EvrenEnstrumanHatasi(
                f"{sembol}: borsada işlem görmüyor (durum {kural.durum!r}); paper/live açılamaz"
            )
        try:
            hazir = [
                dataclasses.replace(e, tick_size=kural.tick_size, lot_size=kural.step_size)
                for e in segmentler
            ]
            for e in hazir:
                e.islem_icin_dogrula()
        except KimlikHatasi as hata:
            raise EvrenEnstrumanHatasi(f"{sembol}: {hata}") from hata
        out[sembol] = hazir
    return out


def ozet(kimlikler: Mapping[str, list[Enstruman]]) -> dict[str, Any]:
    """Koşu günlüğü/olay kaydı için kısa özet — kimlik değil, sayım."""
    return {
        "sembol": len(kimlikler),
        "segment": sum(len(s) for s in kimlikler.values()),
        "tipler": sorted({e.instrument_type for s in kimlikler.values() for e in s}),
        "maliyet_modelleri": sorted({e.maliyet_modeli_id for s in kimlikler.values() for e in s}),
    }


__all__ = [
    "KATALOG_ADI",
    "EvrenEnstrumanHatasi",
    "KuralKaynagi",
    "enstrumanlari_kur",
    "katalog_yolu",
    "katalogu_oku",
    "ozet",
]
