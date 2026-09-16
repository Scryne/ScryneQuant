"""Depodan çok enstrümanlı koşu kurulumu: tablo → ızgara → üyelik → görünüm. (Faz 10)

`CokluBacktest` hazır bir `EvrenGorunumu` istiyor ve istemeli — motor dosya okumaz. Bu
modül o görünümü depodan kuruyor ve tek işi bu: hangi sembollerin yükleneceğine karar
vermek, barları ortak ızgaraya oturtmak, üyeliği kanonik kimliğe bağlamak.

**Yalnızca pencere içinde bir kez bile üye olmuş semboller yükleniyor.** 734 sembolün
tamamını belleğe almak ~2 GB tutar ve tamamı hiçbir ayın üyesi değil. Kriter "üye olmuş
olmak" — "bugün üye olmak" değil: bir ay üye olup sonra delist edilen sembol yüklenmezse
hayatta kalma yanlılığı geri gelirdi (K-052/3).

**Kimlik kırılması eşikleri tablodan okunuyor, varsayılandan değil.** Tablo hangi eşikle
üretildiyse üyelik de onunla kurulmalı; ikisinin ayrışması, tabloda var olan bir kanonik
kimliğin ızgarada karşılığı olmaması demek olurdu.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data import kimlik as kimlik_mod
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.data.izgara import (
    hizala,
    ortak_izgara,
    uyelik_matrisi,
    uyeligi_barlara_kis,
)
from scryne_quant.strategy.evren import EvrenGorunumu
from scryne_quant.strategy.kosu import evren_gorunum_kur
from scryne_quant.strategy.temel import PortfoyStratejisi


class EvrenKosuHatasi(ValueError):
    """Evren koşusu kurulamadı."""


@dataclass(frozen=True, slots=True)
class EvrenKurulumu:
    """Kurulmuş görünüm + kayda girecek kimlik bilgileri."""

    gorunum: EvrenGorunumu
    veri_sha256: dict[str, str]
    meta: dict[str, Any]
    olcum_baslangici: int = 0
    """Isınma barlarının bittiği indeks. Pencere başından **önceki** barlar yalnızca
    indikatörleri ısıtmak için yüklendi; ölçüm oradan başlamaz.

    Isınmayı pencereye dahil etmek, ilk günlerin sinyallerini sessizce kaybettirirdi;
    ısınmayı hiç yüklememek ise canlıda elde olacak geçmişi görmezden gelmek olurdu
    (Faz 4'ün walk-forward kararıyla aynı gerekçe)."""

    @property
    def semboller(self) -> tuple[str, ...]:
        return self.gorunum.semboller


def tablo_oku(tablo_yolu: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """PIT evren tablosunu ve yanındaki meta dosyasını okur."""
    yol = Path(tablo_yolu)
    meta_yolu = yol.with_suffix(".json")
    if not yol.exists():
        raise EvrenKosuHatasi(f"evren tablosu yok: {yol}")
    if not meta_yolu.exists():
        raise EvrenKosuHatasi(
            f"evren meta dosyası yok: {meta_yolu}. Tablo tek başına kimliğini taşımıyor — "
            "hangi kuralla ve hangi kırılma eşikleriyle üretildiği orada (K-009)"
        )
    return pd.read_parquet(yol), json.loads(meta_yolu.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class EvrenVerisi:
    """Stratejiden bağımsız ham evren: ortak ızgaradaki bar dizileri + PIT üyelik. (Faz 12)

    `EvrenKurulumu` bir stratejinin özellikleriyle hesaplanmış **tek** bir görünüm taşıyor.
    Araştırma hattı (tarama, walk-forward, PBO) aynı veriyi onlarca farklı parametre ve
    pencereyle koşturuyor; her koşu kendi özelliklerini kendi penceresinde hesaplamalı
    (`research/evren_degerlendirme.py`). Ham veri bu yüzden ayrı bir tip.
    """

    timeframe: str
    zamanlar: np.ndarray
    diziler: dict[str, dict[str, np.ndarray]]
    uyelik: dict[str, np.ndarray]
    veri_sha256: dict[str, str]
    meta: dict[str, Any]
    olcum_baslangici: int
    kural_kimligi: str

    def __len__(self) -> int:
        return len(self.zamanlar)


def veri_kur(
    tablo_yolu: str | Path,
    *,
    depo_kok: str | Path,
    isinma_bar: int = 0,
    baslangic_ay: str | None = None,
    bitis_ay: str | None = None,
    azami_sembol: int | None = None,
) -> EvrenVerisi:
    """Evren tablosundan ham, stratejiden bağımsız evren verisi kurar.

    `isinma_bar`: pencere başından önce yüklenecek bar sayısı. Birden çok strateji veya
    ızgara noktası aynı veriyi kullanacaksa **en büyüğü** verilmeli.

    `azami_sembol`: bellek tavanı. Aşılırsa **hata verir**, sessizce kırpmaz — kırpmak
    evreni daraltmak, yani hayatta kalma yanlılığını elle geri getirmek olurdu.
    """
    tablo, meta = tablo_oku(tablo_yolu)
    timeframe = str(meta["timeframe"])

    pencere = tablo
    if baslangic_ay:
        pencere = pencere[pencere["ay"] >= baslangic_ay]
    if bitis_ay:
        pencere = pencere[pencere["ay"] <= bitis_ay]
    if pencere.empty:
        raise EvrenKosuHatasi(
            f"pencerede ({baslangic_ay or 'başı'}…{bitis_ay or 'sonu'}) hiç üyelik yok"
        )

    semboller = sorted(set(pencere["sembol"].astype(str)))
    if azami_sembol is not None and len(semboller) > azami_sembol:
        raise EvrenKosuHatasi(
            f"pencerede {len(semboller)} sembol üye olmuş, tavan {azami_sembol}. "
            "Pencereyi daraltın ya da tavanı bilinçli olarak yükseltin — sembol listesini "
            "kırpmak evreni daraltmak, yani hayatta kalma yanlılığını geri getirmek olur"
        )

    esikler = meta.get("kimlik_kirilmasi", {})
    asgari_eksik = int(esikler.get("asgari_eksik_bar", kimlik_mod.KIRILMA_ASGARI_EKSIK_BAR))
    asgari_log = float(esikler.get("asgari_log_oran", kimlik_mod.KIRILMA_ASGARI_LOG_ORAN))

    adim = timeframe_ms(timeframe)
    alt_ms, ust_ms = _pencere_sinirlari(baslangic_ay, bitis_ay)
    yukleme_alt = None if alt_ms is None else alt_ms - max(0, isinma_bar) * adim

    depo = ParquetDepo(depo_kok)
    cerceveler: dict[str, pd.DataFrame] = {}
    kimlikler: dict[str, list[kimlik_mod.Enstruman]] = {}
    veri_sha256: dict[str, str] = {}
    for sembol in semboller:
        df = depo.oku(sembol, timeframe)
        if df.empty:
            raise EvrenKosuHatasi(f"{sembol}: depoda veri yok ama tabloda üye görünüyor")
        veri_sha256[sembol] = depo.sha256(sembol, timeframe)
        # Kimlik segmentleri **tüm** seriden çıkarılıyor, pencereden değil: bir kırılma
        # pencerenin dışında olsa da kimliği pencere içinde geçerli kılan şey odur.
        kir = kimlik_mod.kirilmalar(
            df, timeframe, asgari_eksik_bar=asgari_eksik, asgari_log_oran=asgari_log, sembol=sembol
        )
        kimlikler[sembol] = list(kimlik_mod.kimlikleri_kur(df, timeframe, sembol, kir))
        cerceveler[sembol] = _kirp(df, yukleme_alt, ust_ms)

    cerceveler = {s: d for s, d in cerceveler.items() if not d.empty}
    if not cerceveler:
        raise EvrenKosuHatasi("pencerede hiçbir sembolün barı yok")

    izgara = ortak_izgara(
        [d["open_time"].to_numpy(dtype="int64") for d in cerceveler.values()], timeframe
    )
    if len(izgara) < 2:
        raise EvrenKosuHatasi("pencerede 2'den az bar var")
    olcum_baslangici = 0 if alt_ms is None else int(np.searchsorted(izgara, alt_ms, "left"))
    olcum_baslangici = min(olcum_baslangici, len(izgara) - 2)

    diziler = {s: hizala(df, izgara) for s, df in cerceveler.items()}
    # Parquet çerçeveleri artık gereksiz; Arrow havuzu boşalan belleği kendiliğinden işletim
    # sistemine geri vermiyor. Faz 12'de ölçüldü: tam evrende süreç başına ≈1 GB. Havuzlu
    # araştırma hattında her işçi veriyi ayrıca yüklediği için bu fark çarpılıyor.
    del cerceveler
    pa.default_memory_pool().release_unused()
    uyelik, bar_yok_uyelik = uyeligi_barlara_kis(
        {s: u for s, u in uyelik_matrisi(tablo, izgara, kimlikler).items() if s in diziler},
        diziler,
    )
    return EvrenVerisi(
        timeframe=timeframe,
        zamanlar=np.asarray(izgara, dtype="int64"),
        diziler=diziler,
        uyelik=uyelik,
        veri_sha256=veri_sha256,
        meta={
            "tablo": str(tablo_yolu),
            "tablo_hash": meta.get("tablo_hash"),
            "kural": meta.get("kural"),
            "kural_kimlik": meta.get("kural_kimlik"),
            "kimlik_kirilmasi": {"asgari_eksik_bar": asgari_eksik, "asgari_log_oran": asgari_log},
            "pencere": {"baslangic_ay": baslangic_ay, "bitis_ay": bitis_ay},
            "sembol_sayisi": len(semboller),
            "bar_sayisi": int(len(izgara)),
            "isinma_bar": int(olcum_baslangici),
            "uye_bar_toplami": int(sum(int(u.sum()) for u in uyelik.values())),
            # Barı olmadığı için üyelikten düşen saatler (`uyeligi_barlara_kis`).
            "bar_yok_uyelik": dict(sorted(bar_yok_uyelik.items())),
        },
        olcum_baslangici=olcum_baslangici,
        kural_kimligi=str(meta.get("kural_kimlik", "")),
    )


def kur(
    tablo_yolu: str | Path,
    strateji: PortfoyStratejisi,
    *,
    depo_kok: str | Path,
    baslangic_ay: str | None = None,
    bitis_ay: str | None = None,
    azami_sembol: int | None = None,
) -> EvrenKurulumu:
    """Evren tablosundan tek bir strateji için koşulabilir bir görünüm kurar."""
    veri = veri_kur(
        tablo_yolu,
        depo_kok=depo_kok,
        isinma_bar=strateji.isinma_bar(),
        baslangic_ay=baslangic_ay,
        bitis_ay=bitis_ay,
        azami_sembol=azami_sembol,
    )
    gorunum = evren_gorunum_kur(
        veri.timeframe,
        veri.diziler,
        veri.uyelik,
        strateji,
        kural_kimligi=veri.kural_kimligi,
    )
    return EvrenKurulumu(
        gorunum=gorunum,
        veri_sha256=veri.veri_sha256,
        meta=veri.meta,
        olcum_baslangici=veri.olcum_baslangici,
    )


def _pencere_sinirlari(
    baslangic_ay: str | None, bitis_ay: str | None
) -> tuple[int | None, int | None]:
    """Ay adlarını epoch ms sınırlarına çevirir. Bitiş ayı **dahil** (ayın sonuna kadar)."""
    alt = (
        int(np.datetime64(baslangic_ay, "M").astype("datetime64[ms]").astype("int64"))
        if baslangic_ay
        else None
    )
    ust = (
        int(
            (np.datetime64(bitis_ay, "M") + np.timedelta64(1, "M"))
            .astype("datetime64[ms]")
            .astype("int64")
        )
        if bitis_ay
        else None
    )
    return alt, ust


def _kirp(df: pd.DataFrame, alt_ms: int | None, ust_ms: int | None) -> pd.DataFrame:
    zaman = df["open_time"].to_numpy(dtype="int64")
    maske = np.ones(len(df), dtype=bool)
    if alt_ms is not None:
        maske &= zaman >= alt_ms
    if ust_ms is not None:
        maske &= zaman < ust_ms
    return df.loc[maske]


__all__ = ["EvrenKosuHatasi", "EvrenKurulumu", "EvrenVerisi", "kur", "tablo_oku", "veri_kur"]
