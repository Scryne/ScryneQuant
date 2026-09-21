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

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

from scryne_quant.common import finansman as finansman_mod
from scryne_quant.common import maliyet as maliyet_mod
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data import funding as funding_mod
from scryne_quant.data import fx as fx_mod
from scryne_quant.data import fx_gorunum as fxg_mod
from scryne_quant.data import kimlik as kimlik_mod
from scryne_quant.data import konumlanma as konumlanma_mod
from scryne_quant.data import makro as makro_mod
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.data.izgara import (
    hizala,
    ortak_izgara,
    uyeligi_barlara_kis,
    uyelik_matrisi,
)
from scryne_quant.data.takvim import TAKVIM_FX_5X24
from scryne_quant.data.takvim import takvim as takvim_al
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
    kimlikler: dict[str, list[kimlik_mod.Enstruman]] = field(default_factory=dict)
    """Sembol → kimlik segmentleri; `enstruman_maliyetleri` bunu çözümler (K-084)."""
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
    kimlikler: dict[str, list[kimlik_mod.Enstruman]] = field(default_factory=dict)
    """Sembol → kanonik kimlik segmentleri (`kimlikleri_kur`). Maliyet çözümlemesi buradan
    (`enstruman_maliyetleri`, K-084/U14); veri kimliğine **girmez** (`veri_kimligi` sabit)."""

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
    funding_depo: str | Path | None = None,
    premium_depo: str | Path | None = None,
    makro_depo: str | Path | None = None,
    konumlanma_depo: str | Path | None = None,
) -> EvrenVerisi:
    """Evren tablosundan ham, stratejiden bağımsız evren verisi kurar.

    `funding_depo` verilirse (arşiv funding'i, `data/turev/funding/`) her sembole `funding`
    ve `funding_odeme` dizileri nedensel olarak eklenir (`data/funding.evren_dizileri`).
    Perp'i olmayan sembolde ikisi de tamamen `NaN`: eşleme uydurulmaz. Dosya hash'leri
    `meta["ek_veri_sha256"]`a yazılır ve veri kimliğine girer.

    `premium_depo` verilirse (`data/turev/premium/`) her sembole `basis` dizisi eklenir
    (`data/funding.evren_premium_dizisi`); hash'leri aynı yere yazılır.

    `konumlanma_depo` verilirse (`data/turev/metrics/`) her sembole konumlanma dizileri
    eklenir (`data/konumlanma.evren_dizileri`): açık pozisyon adedi, taker oranı, büyük hesap
    ve hesap sayısı dengeleri. Verisi olmayan sembolde hepsi `NaN`. Dosya hash'leri
    `meta["ek_veri_sha256"]`a yazılır ve veri kimliğine girer (Faz 16).

    `makro_depo` verilirse (`data/makro/`) her sembole makro persentil alanları eklenir
    (`data/makro.bar_alanlari`). Alanlar semboller arasında **aynı dizi**: ek bellek yok.

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
    ek_sha: dict[str, str] = {}
    if funding_depo is not None:
        fdepo = Path(funding_depo)
        for sembol_, dz in diziler.items():
            yol = fdepo / f"{sembol_}.parquet"
            if yol.is_file():
                ek_sha[f"funding/{sembol_}"] = hashlib.sha256(yol.read_bytes()).hexdigest()
                fdf = pd.read_parquet(yol)
            else:
                fdf = pd.DataFrame()
            dz.update(funding_mod.evren_dizileri(izgara, fdf))
    if premium_depo is not None:
        pdepo = Path(premium_depo)
        for sembol_, dz in diziler.items():
            yol = pdepo / f"{sembol_}.parquet"
            if yol.is_file():
                ek_sha[f"premium/{sembol_}"] = hashlib.sha256(yol.read_bytes()).hexdigest()
                pdf = pd.read_parquet(yol)
            else:
                pdf = pd.DataFrame()
            dz["basis"] = funding_mod.evren_premium_dizisi(izgara, pdf)
    if konumlanma_depo is not None:
        kdepo = Path(konumlanma_depo)
        for sembol_, dz in diziler.items():
            yol = kdepo / f"{sembol_}.parquet"
            if yol.is_file():
                ek_sha[f"konumlanma/{sembol_}"] = hashlib.sha256(yol.read_bytes()).hexdigest()
                kdf = pd.read_parquet(yol)
            else:
                kdf = pd.DataFrame()
            dz.update(konumlanma_mod.evren_dizileri(izgara, kdf))
    if makro_depo is not None:
        alanlar, dosyalar = makro_mod.bar_alanlari(izgara, makro_depo)
        for sid, yol in dosyalar.items():
            ek_sha[f"makro/{sid}"] = hashlib.sha256(yol.read_bytes()).hexdigest()
        for dz in diziler.values():
            dz.update(alanlar)
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
            # Yalnızca ek veri yüklendiyse: kesitsel koşuların meta'sı (ve kimliği) değişmez.
            **(
                {"ek_veri_sha256": dict(sorted(ek_sha.items()))}
                if funding_depo is not None or premium_depo is not None
                or makro_depo is not None or konumlanma_depo is not None
                else {}
            ),
        },
        olcum_baslangici=olcum_baslangici,
        kimlikler=kimlikler,
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
        kimlikler=veri.kimlikler,
    )


# ------------------------------------------------------------------ FX (K-096, R4 Paket 4)


def fx_tablo_mu(meta: Mapping[str, Any]) -> bool:
    """Evren meta'sı FX PIT tablosuna mı ait (`fx_evren.FxEvrenKurali`, `fxcm-candledata-m1`)?"""
    kural = meta.get("kural") or {}
    return isinstance(kural, Mapping) and kural.get("kaynak") == "fxcm-candledata-m1"


def fx_veri_kur(
    tablo_yolu: str | Path,
    *,
    depo_kok: str | Path = fx_mod.VARSAYILAN_DEPO,
    isinma_bar: int = 0,
    baslangic_ay: str | None = None,
    bitis_ay: str | None = None,
    azami_sembol: int | None = None,
) -> EvrenVerisi:
    """FX PIT tablosu (`fx_evren`) + `FxDepo` → `EvrenVerisi`; kripto `veri_kur`un FX ikizi.

    Farklar, hepsi bilerek: kalite bayrağı `fx_gorunum.fx_dogrula` (takvimli, hata sınıfları
    kripto ile aynı şema), ızgara `ortak_izgara(..., takvim=fx-5x24)` (seans dışı damga hata),
    üyelik haftalık (`fx_uyelik_matrisi`), kimlik tablodaki tek segment (`fx_enstruman`;
    kırılma tespiti FX'te yok). Pencere `YYYY-MM`: haftanın Pazar'ı o aylarda olan satırlar.
    Depoda üye görünüp barı olmayan çift hata; barı olup üye olmayan hafta üye değil.
    """
    tablo, meta = tablo_oku(tablo_yolu)
    if not fx_tablo_mu(meta):
        raise EvrenKosuHatasi(f"{tablo_yolu}: FX evren tablosu değil (kaynak fxcm-candledata-m1)")
    tk = takvim_al(str((meta.get("kural") or {}).get("takvim", TAKVIM_FX_5X24)))
    timeframe = fx_mod.TIMEFRAME

    pencere = tablo[tablo["uye"].astype(bool)]
    if baslangic_ay:
        pencere = pencere[pencere["pazar"].astype(str).str[:7] >= baslangic_ay]
    if bitis_ay:
        pencere = pencere[pencere["pazar"].astype(str).str[:7] <= bitis_ay]
    if pencere.empty:
        raise EvrenKosuHatasi(
            f"pencerede ({baslangic_ay or 'başı'}…{bitis_ay or 'sonu'}) hiç üyelik yok"
        )
    semboller = sorted(set(pencere["sembol"].astype(str)))
    if azami_sembol is not None and len(semboller) > azami_sembol:
        raise EvrenKosuHatasi(
            f"pencerede {len(semboller)} çift üye olmuş, tavan {azami_sembol}; kırpmak evreni "
            "daraltmak olur"
        )

    adim = timeframe_ms(timeframe)
    alt_ms, ust_ms = _pencere_sinirlari(baslangic_ay, bitis_ay)
    yukleme_alt = None if alt_ms is None else alt_ms - max(0, isinma_bar) * adim

    depo = fx_mod.FxDepo(depo_kok)
    barlar: dict[str, dict[str, np.ndarray]] = {}
    kimlikler: dict[str, list[kimlik_mod.Enstruman]] = {}
    veri_sha256: dict[str, str] = {}
    kalite: dict[str, dict[str, Any]] = {}
    for pair in semboller:
        manifesto = depo.manifesto(pair)
        if manifesto is None or not depo.parquet_yolu(pair).exists():
            raise EvrenKosuHatasi(f"{pair}: FX deposunda yok ama tabloda üye görünüyor")
        df = depo.oku(pair)
        if df.empty:
            raise EvrenKosuHatasi(f"{pair}: FX deposu boş ama tabloda üye görünüyor")
        veri_sha256[pair] = str(manifesto.get("sha256") or "")
        kimlikler[pair] = [fxg_mod.fx_enstruman(pair, int(df["open_time"].iloc[-1]), len(df))]
        bayrakli, rapor = fxg_mod.fx_dogrula(_kirp(df, yukleme_alt, ust_ms), tk, pair=pair)
        kalite[pair] = {k: rapor[k] for k in ("bar_sayisi", "bayraklar", "suspect_nedenleri",
                                              "bosluk_sayisi", "eksik_bar", "kisa_saat")}
        if not bayrakli.empty:
            barlar[pair] = fxg_mod.fx_barlar(bayrakli)
    if not barlar:
        raise EvrenKosuHatasi("pencerede hiçbir çiftin barı yok")

    izgara = ortak_izgara([b["open_time"] for b in barlar.values()], timeframe, takvim=tk)
    if len(izgara) < 2:
        raise EvrenKosuHatasi("pencerede 2'den az bar var")
    olcum_baslangici = 0 if alt_ms is None else int(np.searchsorted(izgara, alt_ms, "left"))
    olcum_baslangici = min(olcum_baslangici, len(izgara) - 2)

    diziler = {s: fxg_mod.fx_hizala(b, izgara) for s, b in barlar.items()}
    uyelik, bar_yok_uyelik = uyeligi_barlara_kis(
        fxg_mod.fx_uyelik_matrisi(tablo, izgara, tuple(diziler)), diziler
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
            "takvim": {"id": tk.kimlik, "icerik_hash": tk.icerik_hash},
            "pencere": {"baslangic_ay": baslangic_ay, "bitis_ay": bitis_ay},
            "sembol_sayisi": len(semboller),
            "bar_sayisi": int(len(izgara)),
            "isinma_bar": int(olcum_baslangici),
            "uye_bar_toplami": int(sum(int(u.sum()) for u in uyelik.values())),
            "bar_yok_uyelik": dict(sorted(bar_yok_uyelik.items())),
            "kalite": {s: kalite[s] for s in sorted(kalite)},
        },
        olcum_baslangici=olcum_baslangici,
        kimlikler=kimlikler,
        kural_kimligi=str(meta.get("kural_kimlik", "")),
    )


def fx_kur(
    tablo_yolu: str | Path,
    strateji: PortfoyStratejisi,
    *,
    depo_kok: str | Path = fx_mod.VARSAYILAN_DEPO,
    baslangic_ay: str | None = None,
    bitis_ay: str | None = None,
    azami_sembol: int | None = None,
) -> EvrenKurulumu:
    """FX evren tablosundan tek strateji için koşulabilir görünüm (`kur`un FX ikizi)."""
    veri = fx_veri_kur(
        tablo_yolu,
        depo_kok=depo_kok,
        isinma_bar=strateji.isinma_bar(),
        baslangic_ay=baslangic_ay,
        bitis_ay=bitis_ay,
        azami_sembol=azami_sembol,
    )
    gorunum = evren_gorunum_kur(
        veri.timeframe, veri.diziler, veri.uyelik, strateji, kural_kimligi=veri.kural_kimligi
    )
    return EvrenKurulumu(
        gorunum=gorunum,
        veri_sha256=veri.veri_sha256,
        meta=veri.meta,
        olcum_baslangici=veri.olcum_baslangici,
        kimlikler=veri.kimlikler,
    )


def enstruman_maliyetleri(
    katalog: maliyet_mod.MaliyetKatalogu,
    kimlikler: Mapping[str, Sequence[kimlik_mod.Enstruman]],
) -> dict[str, maliyet_mod.SembolMaliyeti] | None:
    """`Enstruman.maliyet_modeli_id` → katalog → model, sembol başına. (K-084/U14)

    Çözümleme **her zaman** yapılır (dosya var mı, `global` Binance spot mu — fail closed);
    ama hepsi `global`e çıkıyorsa `None` döner: motor tek-model yolunda kalır ve kayıt
    biçimi bugünkü Binance spot kaydıyla aynı olur. Bir sembolün segmentleri farklı kimlik
    taşıyamaz. `common/maliyet.py` `Enstruman`ı bilmez; bağ bu katmanda.
    """
    out: dict[str, maliyet_mod.SembolMaliyeti] = {}
    for sembol in sorted(kimlikler):
        segmentler = list(kimlikler[sembol])
        if not segmentler:
            raise maliyet_mod.MaliyetHatasi(f"{sembol}: kimlik segmenti yok")
        kimlik_kumesi = {seg.maliyet_modeli_id for seg in segmentler}
        if len(kimlik_kumesi) != 1:
            raise maliyet_mod.MaliyetHatasi(
                f"{sembol}: segmentler farklı maliyet modeli taşıyor {sorted(kimlik_kumesi)}"
            )
        kimlik = segmentler[0].maliyet_modeli_id
        model = katalog.coz(
            kimlik, binance_spot_kripto=all(seg.binance_spot_kripto for seg in segmentler)
        )
        out[sembol] = maliyet_mod.SembolMaliyeti(kimlik, model)
    if all(em.kimlik == maliyet_mod.GLOBAL_KIMLIK for em in out.values()):
        return None
    return out


def enstruman_finansmanlari(
    katalog: finansman_mod.FinansmanKatalogu,
    kimlikler: Mapping[str, Sequence[kimlik_mod.Enstruman]],
) -> dict[str, finansman_mod.SembolFinansmani] | None:
    """`Enstruman.finansman_modeli_id` → katalog → model, sembol başına. (K-095)

    Kimliği `None` olan sembol (spot) modele girmez; **hepsi** `None` ise `None` döner (motor
    finansmansız yolda, kayıt bugünkü biçimde). Kimliği olan sembolün dosyası yoksa hata — sessiz
    0 yok. Karışık evren (spot + cfd) `None` olmayan alt küme döndürür; motor eksik sembolü
    reddeder (`CokluBacktestHatasi`), yani karışık evren bugün bilerek **koşmaz**.
    """
    out: dict[str, finansman_mod.SembolFinansmani] = {}
    for sembol in sorted(kimlikler):
        segmentler = list(kimlikler[sembol])
        if not segmentler:
            raise finansman_mod.FinansmanHatasi(f"{sembol}: kimlik segmenti yok")
        kimlik_kumesi = {seg.finansman_modeli_id for seg in segmentler}
        if len(kimlik_kumesi) != 1:
            raise finansman_mod.FinansmanHatasi(
                f"{sembol}: segmentler farklı finansman modeli taşıyor {sorted(kimlik_kumesi)}"
            )
        kimlik = segmentler[0].finansman_modeli_id
        if kimlik is None:
            continue
        out[sembol] = finansman_mod.SembolFinansmani(kimlik, katalog.coz(kimlik))
    return out or None


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


__all__ = [
    "EvrenKosuHatasi",
    "EvrenKurulumu",
    "EvrenVerisi",
    "enstruman_maliyetleri",
    "kur",
    "tablo_oku",
    "veri_kur",
]
