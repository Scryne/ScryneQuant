"""Kaynak başına veri sözleşmesi ve katman tamlık kontrolü. (K-052, Spike 6 §4b, Faz 9)

Bir veri kaynağını kullanmadan önce altı soruya **yazılı** cevap gerekir: şema ne, hangi
sıklıkta gelir, zaman damgası neyi ifade eder, eksik olduğunu nasıl anlarız, geriye dönük
değişir mi, kullanım lisansı ne. Cevapsız soru kodda bir varsayım olarak yaşar ve o varsayım
bir gün sessizce yanlış çıkar — bu projede ölçülen örnekleri: REST'in kapanmamış barı
(Spike 1), arşivin µs'e geçişi, `1mo` katmanının 2026-03'ten beri eksik olması (Spike 6).

**Lisans alanı bilinmiyorsa "doğrulanmadı" yazar, tahmin yazmaz.**

**Katman tamlığı.** Arşiv aynı veriyi birden çok katmanda yayımlıyor (`1h`, `1d`, `1mo`).
Türetilmiş bir katmana güvenmek sessiz bir boşluk bırakır: Spike 6'da `1mo` katmanı
2026-03'te 7, 2026-07'de 0 sembol içeriyordu, `1h` ise 448 ve 484. `katman_tamligi` bir
sembolün iki katmanındaki ay listelerini karşılaştırır; eksik ay rapora girer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from scryne_quant.exchange.binance_arsiv import ArsivKaynagi, aylik_dosyalar


@dataclass(frozen=True, slots=True)
class VeriSozlesmesi:
    ad: str
    kaynak: str
    sema: tuple[str, ...]
    cadence: str
    zaman_semantigi: str
    available_time_kaynagi: str
    tamlik: str
    revizyon: str
    lisans: str
    kanit: str

    def sozluk(self) -> dict[str, Any]:
        return {
            "ad": self.ad,
            "kaynak": self.kaynak,
            "sema": list(self.sema),
            "cadence": self.cadence,
            "zaman_semantigi": self.zaman_semantigi,
            "available_time_kaynagi": self.available_time_kaynagi,
            "tamlik": self.tamlik,
            "revizyon": self.revizyon,
            "lisans": self.lisans,
            "kanit": self.kanit,
        }


_BAR_SEMASI: Final = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trades",
    "quality_status",
)
_LISANS_ACIK: Final = "doğrulanmadı — Binance kullanım koşulları okunup kaynaklı kaydedilmedi"

SOZLESMELER: Final[dict[str, VeriSozlesmesi]] = {
    s.ad: s
    for s in (
        VeriSozlesmesi(
            ad="binance-spot-rest-kline",
            kaynak="https://data-api.binance.vision/api/v3/klines",
            sema=_BAR_SEMASI,
            cadence="timeframe ızgarası (1m…1d), epoch'a hizalı",
            zaman_semantigi="open_time = bar açılışı, UTC epoch ms (K-005); endTime kapsayıcı",
            available_time_kaynagi="bar kapanışı (open_time + timeframe); yanıttaki son bar "
            "kapanmamış olabilir ve atılır (K-015/1)",
            tamlik="sayfalama boş yanıtta biter; boşluk `gap` bayrağı (K-006, K-024)",
            revizyon="gözlenmedi; aynı aralığın yeniden indirilmesi yeni veri kazanır",
            lisans=_LISANS_ACIK,
            kanit="Spike 1, Faz 1 veri raporu",
        ),
        VeriSozlesmesi(
            ad="binance-arsiv-spot-kline",
            kaynak="https://data.binance.vision/data/spot/{monthly,daily}/klines/",
            sema=_BAR_SEMASI,
            cadence="aylık dosya ay bitince, günlük dosya ~1 gün gecikmeyle; 1h katmanı",
            zaman_semantigi="open_time bar açılışı; 2024-12 ve öncesi ms, 2025-01 ve sonrası µs "
            "(ölçüldü 2026-09-15); dosya içinde karışık birim reddedilir",
            available_time_kaynagi="bar kapanışı; arşiv yalnızca kapanmış dönemleri yayımlar",
            tamlik="her zip `.CHECKSUM` (SHA-256) ile doğrulanır, checksum'sız dosya reddedilir; "
            "manifesto dosya başına hash taşır; `1h`–`1mo` katman karşılaştırması "
            "(`katman_tamligi`); ızgaraya oturmayan barlar atılıp sayılır (BTCUSDT-1h-2018-02: "
            "43 bar)",
            revizyon="dosya yeniden yayımlanabilir; `--tam-dogrulama` checksum değişimini yakalar",
            lisans=_LISANS_ACIK,
            kanit="Spike 6; Faz 9 raporu (µs geçişi, hizasız bar, REST farkı 4/45.576 bar)",
        ),
        VeriSozlesmesi(
            ad="binance-usdm-funding",
            kaynak="https://fapi.binance.com/fapi/v1/fundingRate",
            sema=("funding_time", "funding_rate", "mark_price"),
            cadence="8 saat (ölçüldü: 7.675 kaydın tamamı)",
            zaman_semantigi="fundingTime ödemenin gerçekleştiği an, UTC epoch ms",
            available_time_kaynagi="fundingTime (ödeme o anda gerçekleşir); hizalama "
            "`fundingTime <= bar_acilisi` (K-042)",
            tamlik="periyot sapması > 60 s anomali; oran tavanı ±%0,3",
            revizyon="gözlenmedi",
            lisans=_LISANS_ACIK,
            kanit="Spike 5",
        ),
        VeriSozlesmesi(
            ad="histdata-fx-m1",
            kaynak="https://www.histdata.com/download-free-forex-data/ (aylık zip, GENERIC ASCII "
            "M1; toplu/otomatik indirme için FTP, tek seferlik ücret)",
            sema=_BAR_SEMASI,
            cadence="M1 bar (dosya aylık); 1h katmanı M1'den türetilir; 5/7 takvim "
            "(Pazar ~22:00 UTC açılış, Cuma ~22:00 UTC kapanış), hafta içi boşluk normal",
            zaman_semantigi="kaynak damgası `YYYYMMDD HHMMSS`, **EST (UTC−5) yaz saati yok**; "
            "UTC'ye sabit +5 saatle çevrilir (K-087); open_time bar açılışı (K-005)",
            available_time_kaynagi="bar kapanışı; aylık dosya ay bitince yayımlanır — canlı "
            "akış yok, yalnız araştırma (R3)",
            tamlik="bar fiyatları **yalnız bid** (spike: `Bar OPEN/HIGH/LOW/CLOSE Bid Quote`); "
            "ask yok → spread ayrı bileşen (R4), o güne kadar maliyet aleyhte varsayımla; "
            "`Volume` kaynakta tanımsız (tick sayısı?) → `trades`e yazılmaz, 0; gap ölçülür",
            revizyon="sağlayıcı beyanı yok; her zip SHA-256'sı manifestoya yazılır, değişen "
            "dosya yakalanır",
            lisans="sağlayıcı lisans metni **yok**; beyan: 'Since it's free data, you'll not get "
            "from us any kind of warranty or certification. Use the data at your own will and "
            "risk.' (kaynak: histdata.com/f-a-q, 2026-09-21 okundu). Yeniden dağıtım/ticari "
            "kullanım/otomasyon için "
            "açık yasak yok; toplu erişim sağlayıcının kendi FTP hizmetiyle. Kullanım: kendi "
            "hesabı, araştırma (K-014). Kaynak akışı adsız → provenans zayıf, canlı için yetmez",
            kanit="K-087 (kaynak taraması 2026-09-21: Dukascopy otomasyon yasağı, Tiingo kalıcı "
            "depolama yasağı → elendi); veri raporu R3 Paket 1'de",
        ),
    )
}


@dataclass(frozen=True, slots=True)
class KatmanTamlikRaporu:
    sembol: str
    referans_katman: str
    turetilmis_katman: str
    referans_ay: int
    turetilmiste_eksik: tuple[str, ...]
    """Referans katmanda olup türetilmiş katmanda olmayan aylar."""
    referansta_eksik: tuple[str, ...]
    """Türetilmiş katmanda olup referansta olmayan aylar."""
    referans_ic_bosluk: tuple[str, ...]
    """Referans katmanın ilk ve son ayı arasında dosyası olmayan aylar."""

    @property
    def tam(self) -> bool:
        return not (self.turetilmiste_eksik or self.referansta_eksik or self.referans_ic_bosluk)

    def sozluk(self) -> dict[str, Any]:
        return {
            "sembol": self.sembol,
            "referans_katman": self.referans_katman,
            "turetilmis_katman": self.turetilmis_katman,
            "referans_ay": self.referans_ay,
            "tam": self.tam,
            "turetilmiste_eksik": list(self.turetilmiste_eksik),
            "referansta_eksik": list(self.referansta_eksik),
            "referans_ic_bosluk": list(self.referans_ic_bosluk),
        }


def _ay_araligi(ilk: str, son: str) -> list[str]:
    aylar = np.arange(np.datetime64(ilk, "M"), np.datetime64(son, "M") + np.timedelta64(1, "M"))
    return [str(a) for a in aylar]


def katman_karsilastir(
    sembol: str,
    referans: set[str],
    turetilmis: set[str],
    *,
    referans_katman: str = "1h",
    turetilmis_katman: str = "1mo",
) -> KatmanTamlikRaporu:
    """İki katmanın ay kümelerini karşılaştırır (ağsız, saf)."""
    ic = (
        tuple(a for a in _ay_araligi(min(referans), max(referans)) if a not in referans)
        if referans
        else ()
    )
    return KatmanTamlikRaporu(
        sembol=sembol.upper(),
        referans_katman=referans_katman,
        turetilmis_katman=turetilmis_katman,
        referans_ay=len(referans),
        turetilmiste_eksik=tuple(sorted(referans - turetilmis)),
        referansta_eksik=tuple(sorted(turetilmis - referans)),
        referans_ic_bosluk=ic,
    )


def katman_tamligi(
    kaynak: ArsivKaynagi,
    sembol: str,
    *,
    referans_katman: str = "1h",
    turetilmis_katman: str = "1mo",
) -> KatmanTamlikRaporu:
    """Arşivde bir sembolün iki aylık katmanını listeleyip karşılaştırır."""
    return katman_karsilastir(
        sembol,
        set(aylik_dosyalar(kaynak, sembol, referans_katman)),
        set(aylik_dosyalar(kaynak, sembol, turetilmis_katman)),
        referans_katman=referans_katman,
        turetilmis_katman=turetilmis_katman,
    )


__all__ = [
    "SOZLESMELER",
    "KatmanTamlikRaporu",
    "VeriSozlesmesi",
    "katman_karsilastir",
    "katman_tamligi",
]
