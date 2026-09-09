"""Bar doğrulama ve kalite bayrakları. (K-006, K-005)

Bu modül **tek bir soruyu** cevaplar: bu bar backtest'te kullanılabilir mi?

K-006 cevabı bir bayrağa indiriyor: `ok` dışındaki barlar sessizce kullanılmaz, oranı
sonuç kaydına yazılır, eşiği aşarsa sonuç promotion'a giremez. Buradaki kod o bayrağı
üretir — ve ürettiği her bayrağın bir kuralı, her kuralın bir gerekçesi vardır.

**Spike 2'nin bu modüle bıraktığı borç:** 3 yıllık 1h (26.281 bar) ve 1 yıllık 1m
(525.601 bar) gerçek BTC/USDT verisinde **sıfır** eksik bar, sıfır tekrar, sıfır OHLC
tutarsızlığı, sıfır sıfır-hacimli bar bulundu. Yani aşağıdaki kod yollarının hiçbiri
gerçek veriyle tetiklenmiyor. Test edilmemiş bir güvenlik mekanizmasına güvenmek onu
olmamasından beter yapar — `tests/unit/test_dogrulama.py` bu yüzden yapay bozuk fixture
kullanır ve her kural için ayrı bir vaka içerir.

**Bayrak tekildir.** Bir bar birden çok kurala takılırsa en ağırı yazılır. Öncelik:

    suspect > gap > duplicate > backfilled > ok

Gerekçe: `suspect` barın **içeriğinin** yanlış olabileceğini söyler — en ağırı budur.
`gap` seriyi, `duplicate` yalnızca gelişini ilgilendirir (tekilleştirme zaten çözdü).
`backfilled` bir köken bilgisidir, kusur değil. Öncelik sırası raporlamayı etkiler;
backtest için ayrım basittir: `ok` ya da değil.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np
import pandas as pd

from scryne_quant.common.zaman import timeframe_ms, utc_str
from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI, KaliteDurumu

#: Bir barın önceki kapanışa göre hareketi bunu aşarsa `suspect`.
#:
#: Sayının kaynağı ölçüm: Spike 2, 3 yıllık 1h veride en büyük bar hareketini **533 bps**
#: (%5,33), 1 yıllık 1m veride 429 bps ölçtü. 5.000 bps (%50) bunun ~9 katı — yani bu eşik
#: oynaklığı değil, yalnızca **bozulmayı** yakalar (ondalık kayması, sıfırlanmış fiyat,
#: yanlış sembol). Eşiği piyasa hareketine yaklaştırmak, gerçek bir çöküşü "şüpheli" sayıp
#: backtest'ten atmak olurdu — ki bu, kriz dönemlerini veri setinden silen bir bias üretir.
ASIRI_HAREKET_BPS: Final = 5_000.0

#: Rapora yazılacak azami boşluk kaydı. Boşluk sayısı binlere çıkarsa rapor okunmaz hale
#: gelir; toplam sayı yine de tam verilir, kesilen yalnızca listedir.
RAPOR_BOSLUK_LIMITI: Final = 50


class DogrulamaHatasi(Exception):
    """Doğrulanamayacak kadar bozuk girdi — bayrakla geçiştirilemeyecek sözleşme ihlali."""


@dataclass(frozen=True, slots=True)
class Bosluk:
    """Seride eksik bir aralık: `[baslangic_ms, bitis_ms)` arası bar yok."""

    baslangic_ms: int
    bitis_ms: int
    eksik_bar: int

    def sozluk(self) -> dict[str, Any]:
        return {
            "baslangic_ms": self.baslangic_ms,
            "bitis_ms": self.bitis_ms,
            "baslangic": utc_str(self.baslangic_ms),
            "bitis": utc_str(self.bitis_ms),
            "eksik_bar": self.eksik_bar,
        }


@dataclass(frozen=True, slots=True)
class KaliteRaporu:
    """Bir veri setinin kalite özeti. (K-006)

    Faz 3 bunun `ok_orani` alanını sonuç kaydına yazacak; eşiği aşan sonuç
    `data_quality_warning` bayrağıyla promotion'a giremez (K-010).
    """

    sembol: str
    timeframe: str
    bar_sayisi: int
    ilk_ms: int
    son_ms: int
    beklenen_bar: int
    eksik_bar: int
    bayraklar: dict[str, int]
    suspect_nedenleri: dict[str, int]
    bosluklar: tuple[Bosluk, ...] = field(default=())
    bosluk_sayisi: int = 0

    @property
    def ok_sayisi(self) -> int:
        return self.bayraklar.get(KaliteDurumu.OK, 0)

    @property
    def ok_orani(self) -> float:
        """`ok` barların oranı. Boş veri setinde 0.0 — "kusursuz" değil, "bilinmiyor"."""
        return self.ok_sayisi / self.bar_sayisi if self.bar_sayisi else 0.0

    @property
    def kusursuz(self) -> bool:
        return self.bar_sayisi > 0 and self.ok_sayisi == self.bar_sayisi

    @property
    def kapsama(self) -> float:
        """Beklenen barların ne kadarı elde. Eksik bar oranının tamamlayanı."""
        return self.bar_sayisi / self.beklenen_bar if self.beklenen_bar else 0.0

    def sozluk(self) -> dict[str, Any]:
        """JSON'a yazılabilir özet. Rapor dosyasının ve CLI çıktısının kaynağı."""
        return {
            "sembol": self.sembol,
            "timeframe": self.timeframe,
            "bar_sayisi": self.bar_sayisi,
            "ilk_ms": self.ilk_ms,
            "son_ms": self.son_ms,
            "ilk": utc_str(self.ilk_ms) if self.bar_sayisi else None,
            "son": utc_str(self.son_ms) if self.bar_sayisi else None,
            "beklenen_bar": self.beklenen_bar,
            "eksik_bar": self.eksik_bar,
            "kapsama": round(self.kapsama, 6),
            "ok_orani": round(self.ok_orani, 6),
            "kusursuz": self.kusursuz,
            "bayraklar": dict(self.bayraklar),
            "suspect_nedenleri": dict(self.suspect_nedenleri),
            "bosluk_sayisi": self.bosluk_sayisi,
            "bosluklar": [b.sozluk() for b in self.bosluklar],
        }


def dogrula(
    df: pd.DataFrame,
    timeframe: str,
    *,
    sembol: str = "",
    asiri_hareket_bps: float = ASIRI_HAREKET_BPS,
    backfill: bool = False,
) -> tuple[pd.DataFrame, KaliteRaporu]:
    """Ham barları doğrular, `quality_status` sütununu ekler ve raporu üretir.

    Girdi ham bar sütunlarını içermelidir (`quality_status` varsa yok sayılır — bayrak
    burada **yeniden** hesaplanır; devralmak, bir kez yanlış hesaplanmış bayrağın veri
    setinde kalıcılaşması demek olurdu).

    `backfill=True`: bu parti birincil akıştan değil, sonradan tamamlamadan geliyor —
    kusursuz barlar `ok` yerine `backfilled` işaretlenir (K-006). Faz 1'de bu yol
    kullanılmaz (tek kaynak REST); Faz 6'da birincil akış WebSocket olduğunda anlam
    kazanır. Şimdiden var, çünkü şema o zaman değişmemeli.
    """
    adim = timeframe_ms(timeframe)

    eksik = [s for s in HAM_BAR_SUTUNLARI if s not in df.columns]
    if eksik:
        raise DogrulamaHatasi(f"eksik sütun(lar): {', '.join(eksik)}")

    calisma = df.loc[:, list(HAM_BAR_SUTUNLARI)].copy()

    if calisma.empty:
        bos = calisma.assign(quality_status=pd.Series(dtype="string"))
        return bos, KaliteRaporu(
            sembol=sembol,
            timeframe=timeframe,
            bar_sayisi=0,
            ilk_ms=0,
            son_ms=0,
            beklenen_bar=0,
            eksik_bar=0,
            bayraklar={},
            suspect_nedenleri={},
        )

    calisma["open_time"] = calisma["open_time"].astype("int64")

    # --- sözleşme ihlalleri: bayrakla geçiştirilemez -----------------------
    # Hizasız timestamp tek bir barın kusuru değil, serinin yanlış hizalanmış olması
    # demektir (K-005: bar timestamp'i epoch'a hizalı açılış zamanıdır). Bunu `suspect`
    # sayıp devam etmek, yanlış bir zaman eksenini "biraz şüpheli veri" diye kaydetmek
    # olurdu — sessiz yanlış sonucun tam tarifi.
    hizasiz = calisma["open_time"] % adim != 0
    if hizasiz.any():
        ornek = int(calisma.loc[hizasiz, "open_time"].iloc[0])
        raise DogrulamaHatasi(
            f"{int(hizasiz.sum())} bar {timeframe} ızgarasına hizalı değil "
            f"(ör. {ornek} = {utc_str(ornek)}); K-005 ihlali"
        )

    # --- tekilleştirme ----------------------------------------------------
    # Tekrarlayan timestamp'te son kayıt tutulur (depo ile aynı kural): sonraki çağrı
    # daha güncel veridir. Tutulan bar `duplicate` işaretlenir — tekilleştirmenin
    # gerçekleştiği bilgisi kaybolmasın.
    tekrar_eden_ts = set(calisma.loc[calisma["open_time"].duplicated(keep=False), "open_time"])
    calisma = (
        calisma.drop_duplicates(subset="open_time", keep="last")
        .sort_values("open_time", kind="stable")
        .reset_index(drop=True)
    )

    n = len(calisma)
    acilis = calisma["open"].to_numpy(dtype="float64")
    yuksek = calisma["high"].to_numpy(dtype="float64")
    dusuk = calisma["low"].to_numpy(dtype="float64")
    kapanis = calisma["close"].to_numpy(dtype="float64")
    hacim = calisma["volume"].to_numpy(dtype="float64")
    quote = calisma["quote_volume"].to_numpy(dtype="float64")
    islem = calisma["trades"].to_numpy(dtype="int64")
    zaman = calisma["open_time"].to_numpy(dtype="int64")

    fiyatlar = np.vstack([acilis, yuksek, dusuk, kapanis])

    # --- suspect kuralları ------------------------------------------------
    # Her kuralın adı raporda ayrı sayılır: "12 şüpheli bar" bilgi değil, "12 bar sıfır
    # hacimli" bilgidir. Hangi kuralın tetiklendiğini bilmeden düzeltilecek bir şey yok.
    kurallar: dict[str, np.ndarray] = {
        "sonlu_olmayan": ~np.isfinite(fiyatlar).all(axis=0)
        | ~np.isfinite(hacim)
        | ~np.isfinite(quote),
        "pozitif_olmayan_fiyat": (fiyatlar <= 0).any(axis=0),
        "high_low_ters": yuksek < dusuk,
        "high_govdeyi_kapsamiyor": (yuksek < acilis) | (yuksek < kapanis),
        "low_govdeyi_kapsamiyor": (dusuk > acilis) | (dusuk > kapanis),
        "negatif_hacim": (hacim < 0) | (quote < 0) | (islem < 0),
        "sifir_hacim": hacim == 0,
        # Hacim var ama işlem sayısı sıfır: ikisi aynı olaydan türer, ayrışmaları veri
        # bozulmasının imzasıdır.
        "islemsiz_hacim": (islem == 0) & (hacim > 0),
    }

    onceki_kapanis = np.concatenate([[np.nan], kapanis[:-1]])
    with np.errstate(divide="ignore", invalid="ignore"):
        hareket_bps = np.abs(kapanis - onceki_kapanis) / onceki_kapanis * 10_000
    kurallar["asiri_hareket"] = np.nan_to_num(hareket_bps, nan=0.0) > asiri_hareket_bps

    suspect = np.zeros(n, dtype=bool)
    for maske in kurallar.values():
        suspect |= maske

    # --- gap --------------------------------------------------------------
    # Boşluktan **sonraki** bar işaretlenir: eksik barlar için satır uydurulmaz. Sentetik
    # bar üretmek, olmayan bir fiyatı varmış gibi göstermek olurdu; bu projede en pahalı
    # hata sınıfı tam olarak budur. Boşluk gerçeği raporda ve bayrakta durur, veride değil.
    fark = np.diff(zaman, prepend=zaman[0])
    gap = np.zeros(n, dtype=bool)
    gap[1:] = fark[1:] > adim

    duplicate = np.fromiter((int(t) in tekrar_eden_ts for t in zaman), dtype=bool, count=n)

    # --- bayrak birleştirme (öncelik: suspect > gap > duplicate > backfilled) ---
    temel = KaliteDurumu.BACKFILLED if backfill else KaliteDurumu.OK
    durum = np.full(n, str(temel), dtype=object)
    durum[duplicate] = str(KaliteDurumu.DUPLICATE)
    durum[gap] = str(KaliteDurumu.GAP)
    durum[suspect] = str(KaliteDurumu.SUSPECT)

    calisma["quality_status"] = pd.Series(durum, dtype="string")

    # --- rapor ------------------------------------------------------------
    bosluk_idx = np.flatnonzero(gap)
    bosluklar = tuple(
        Bosluk(
            baslangic_ms=int(zaman[i - 1] + adim),
            bitis_ms=int(zaman[i]),
            eksik_bar=int((zaman[i] - zaman[i - 1]) // adim) - 1,
        )
        for i in bosluk_idx[:RAPOR_BOSLUK_LIMITI]
    )
    beklenen = int((zaman[-1] - zaman[0]) // adim) + 1

    rapor = KaliteRaporu(
        sembol=sembol,
        timeframe=timeframe,
        bar_sayisi=n,
        ilk_ms=int(zaman[0]),
        son_ms=int(zaman[-1]),
        beklenen_bar=beklenen,
        eksik_bar=beklenen - n,
        bayraklar=_sayim(calisma["quality_status"]),
        suspect_nedenleri={ad: int(m.sum()) for ad, m in kurallar.items() if m.any()},
        bosluklar=bosluklar,
        bosluk_sayisi=int(gap.sum()),
    )
    return calisma, rapor


def rapor_cikar(df: pd.DataFrame, timeframe: str, *, sembol: str = "") -> KaliteRaporu:
    """Depodan okunan, **bayrağı zaten hesaplanmış** veri için rapor üretir.

    `dogrula`'dan farkı: bayrağı yeniden hesaplamaz, mevcut bayrakları sayar. `data
    quality` komutu bunu kullanır — depodaki bayrak indirme anındaki doğrulamanın
    sonucudur, rapor anında yeniden türetilmesi gereken bir şey değil.

    Boşluklar yine de timestamp dizisinden hesaplanır: bayrak "bu barın öncesinde boşluk
    var" der ama boşluğun **ne kadar** olduğunu taşımaz.
    """
    if "quality_status" not in df.columns:
        raise DogrulamaHatasi("quality_status yok; önce dogrula() çağrılmalı")

    adim = timeframe_ms(timeframe)
    if df.empty:
        return KaliteRaporu(
            sembol=sembol,
            timeframe=timeframe,
            bar_sayisi=0,
            ilk_ms=0,
            son_ms=0,
            beklenen_bar=0,
            eksik_bar=0,
            bayraklar={},
            suspect_nedenleri={},
        )

    zaman = df["open_time"].to_numpy(dtype="int64")
    fark = np.diff(zaman)
    bosluk_idx = np.flatnonzero(fark > adim)
    bosluklar = tuple(
        Bosluk(
            baslangic_ms=int(zaman[i] + adim),
            bitis_ms=int(zaman[i + 1]),
            eksik_bar=int((zaman[i + 1] - zaman[i]) // adim) - 1,
        )
        for i in bosluk_idx[:RAPOR_BOSLUK_LIMITI]
    )
    beklenen = int((zaman[-1] - zaman[0]) // adim) + 1

    return KaliteRaporu(
        sembol=sembol,
        timeframe=timeframe,
        bar_sayisi=len(df),
        ilk_ms=int(zaman[0]),
        son_ms=int(zaman[-1]),
        beklenen_bar=beklenen,
        eksik_bar=beklenen - len(df),
        bayraklar=_sayim(df["quality_status"]),
        suspect_nedenleri={},
        bosluklar=bosluklar,
        bosluk_sayisi=int(len(bosluk_idx)),
    )


def _sayim(seri: pd.Series) -> dict[str, int]:
    """Bayrak sayıları, sabit sırada. Sıra sabit olmazsa rapor dosyaları gereksiz yere
    farklı çıkar ve `diff` işe yaramaz hale gelir."""
    ham = seri.value_counts().to_dict()
    return {str(d): int(ham.get(str(d), 0)) for d in KaliteDurumu if ham.get(str(d), 0)}
