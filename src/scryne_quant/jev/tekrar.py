"""Tarihsel replay: durum → Jev → **dondurulmuş** karar dosyası. Backtest bunu çağırmaz. (K-049/5)

Spec §64 Phase 7'nin "historical data → state → Jev → decision" zinciri bu projede iki parçaya
bölünüyor ve ikisi arasında bir dosya var:

    tekrar_kos()   tarihsel barlar → kanonik durum → Jev → JevDefteri (runs/jev/tekrar-*.sqlite)
    dondur()       JevDefteri → Parquet + manifest.json (data/semantik/jev/<turetim_id>/)

Backtest ve değerlendirme yalnızca ikinci parçanın çıktısını okur; Jev'i **hiçbir backtest
döngüsü çağırmaz** (K-049/5). Bunun sebebi K-009: LLM çıktısı sürüme ve örneklemeye bağlı,
"aynı girdi aynı çıktı"yı sağlamaz. Dosya bir kez üretilir, SHA-256'sı türetimin kimliğidir.

**Her replay kaydı `leak_riski` taşır** — kesim tarihi bilinmediği sürece istisnasız
(K-074/3). Replay'in bu projedeki değeri isabet ölçmek değil; boru hattını, şemayı, gecikmeyi ve
canlı = replay durum eşitliğini doğrulamak. Manifest bunu açıkça yazar.

**Kuru mod** (`istemci=None`): Jev'e sorulmaz, yalnızca durumlar kurulup hash'leri
yazılır. Gölge koşusunun ürettiği durum hash'leriyle bit düzeyinde karşılaştırma için
(spec §38: tek state builder) ve API bütçesi harcamadan boru hattını denemek için.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from scryne_quant.common.hash import dosya_hash, git_durumu, nesne_hash
from scryne_quant.common.zaman import simdi_ms, utc_str
from scryne_quant.jev.ayarlar import JevAyarlari
from scryne_quant.jev.defter import JevDefteri, OlayTuru, kosu_kimligi_kur
from scryne_quant.jev.durum import PENCERE_BAR, durum_hash, kanonik_durum
from scryne_quant.jev.istemci import Istemci, sor
from scryne_quant.jev.karar import JevKarari, KararDurumu, karar_kur
from scryne_quant.jev.sorular import soru_sha256

VARSAYILAN_KOK: Final = Path("data/semantik/jev")

#: Parquet'e yazılan sütunlar: `JevKarari.sozluk()` düz alanları. Sözlük alanları JSON metni.
_SOZLUK_ALANLARI: Final[tuple[str, ...]] = ("yon_olasiliklari", "rejim_olasiliklari")


class TekrarHatasi(RuntimeError):
    """Replay kurulumu geçersiz."""


@dataclass(frozen=True, slots=True)
class TekrarOzeti:
    kosu: str
    bar_sayisi: int
    sorulan: int
    atlanan: int
    sayim: dict[str, int]
    ilk_karar_ms: int | None
    son_karar_ms: int | None
    gecikme_ms_p50: float | None
    gecikme_ms_p95: float | None
    kuru: bool

    def sozluk(self) -> dict[str, Any]:
        return {
            "kosu": self.kosu,
            "bar_sayisi": self.bar_sayisi,
            "sorulan": self.sorulan,
            "atlanan": self.atlanan,
            "sayim": self.sayim,
            "ilk_karar_ms": self.ilk_karar_ms,
            "son_karar_ms": self.son_karar_ms,
            "gecikme_ms_p50": self.gecikme_ms_p50,
            "gecikme_ms_p95": self.gecikme_ms_p95,
            "kuru": self.kuru,
        }


def tekrar_kos(
    diziler_1h: Mapping[str, np.ndarray],
    *,
    ayarlar: JevAyarlari,
    defter: JevDefteri,
    kosu: str,
    ilk: int,
    son: int,
    istemci: Istemci | None,
    funding_time_ms: np.ndarray | None = None,
    funding_rate: np.ndarray | None = None,
    saat: Callable[[], int] = simdi_ms,
    ilerleme: Callable[[int, int], None] | None = None,
) -> TekrarOzeti:
    """`[ilk, son]` aralığındaki her `ok` bar için durum kurar, (varsa) Jev'e sorar, deftere yazar.

    Aynı defterde daha önce geçerli karar yazılmış barlar **atlanır**: replay kaldığı yerden
    devam edebilir, aynı bara ikinci kez para harcamaz. `ilk` en az `PENCERE_BAR - 1` olmalı:
    daha erken bir barda durum penceresi tam değildir ve canlıyla eşitlik iddiası düşer.
    """
    n = len(diziler_1h["open_time"])
    if not 0 <= ilk <= son < n:
        raise TekrarHatasi(f"aralık geçersiz: {ilk}..{son} (0..{n - 1})")
    if ilk < PENCERE_BAR - 1:
        raise TekrarHatasi(
            f"ilk bar en az {PENCERE_BAR - 1} olmalı: daha erken barda durum penceresi tam değil"
        )
    sha = soru_sha256(ayarlar.model)
    defter.kosu_yaz(kosu_kimligi_kur(kosu, "tekrar", ayarlar, sha))
    defter.olay_yaz(
        OlayTuru.BASLADI,
        {"ilk": ilk, "son": son, "kuru": istemci is None, "pencere_bar": PENCERE_BAR},
        zaman_ms=saat(),
    )
    var_olan = {int(s["karar_ms"]) for s in defter.kararlar(yalniz_gecerli=True)}
    kalite = diziler_1h["quality_status"]
    sorulan = atlanan = 0
    gecikmeler: list[int] = []
    ilk_ms: int | None = None
    son_ms: int | None = None
    for i in range(ilk, son + 1):
        t = int(diziler_1h["open_time"][i])
        if ilerleme is not None:
            ilerleme(i - ilk + 1, son - ilk + 1)
        if t in var_olan:
            continue
        if str(kalite[i]) != "ok":
            atlanan += 1
            defter.olay_yaz(
                OlayTuru.BAR_ATLANDI, {"karar_ms": t, "kalite": str(kalite[i])}, zaman_ms=saat()
            )
            continue
        durum = kanonik_durum(
            diziler_1h,
            i,
            sembol=ayarlar.sembol,
            funding_time_ms=funding_time_ms,
            funding_rate=funding_rate,
        )
        h = durum_hash(durum)
        if istemci is None:
            # Kuru mod: durum var, karar yok; kayıt EKSIK_VERI değil, sorulmadığı için
            # "geçersiz" bir satır olarak yazılır ve sebep açıkça "kuru" der.
            karar = karar_kur(
                kosu=kosu,
                durum=durum,
                durum_hash=h,
                soru_sha256=sha,
                model_istenen=ayarlar.model,
                uretim_ms=saat(),
                bayat_ms=ayarlar.bayat_ms,
                yon_marji=ayarlar.yon_marji,
                egitim_kesim_ms=ayarlar.egitim_kesim_ms,
                yayin_ms=ayarlar.yayin_ms,
                yanit=None,
                durum_kodu=KararDurumu.EKSIK_VERI,
                hata="kuru mod: Jev'e sorulmadı",
                geriye_donuk=True,
            )
            defter.karar_yaz(karar, durum, None)
        else:
            sonuc = sor(istemci, durum, ayarlar)
            karar = karar_kur(
                kosu=kosu,
                durum=durum,
                durum_hash=h,
                soru_sha256=sha,
                model_istenen=ayarlar.model,
                uretim_ms=saat(),
                bayat_ms=ayarlar.bayat_ms,
                yon_marji=ayarlar.yon_marji,
                egitim_kesim_ms=ayarlar.egitim_kesim_ms,
                yayin_ms=ayarlar.yayin_ms,
                yanit=sonuc.yanit,
                durum_kodu=sonuc.durum,
                hata=sonuc.hata,
                gecikme_ms=sonuc.gecikme_ms,
                geriye_donuk=True,
            )
            defter.karar_yaz(karar, durum, sonuc.yanit)
            gecikmeler.append(sonuc.gecikme_ms)
            sorulan += 1
        ilk_ms = t if ilk_ms is None else ilk_ms
        son_ms = t
    defter.olay_yaz(OlayTuru.DURDU, {"sorulan": sorulan, "atlanan": atlanan}, zaman_ms=saat())
    g = np.asarray(gecikmeler, dtype=np.float64)
    return TekrarOzeti(
        kosu=kosu,
        bar_sayisi=son - ilk + 1,
        sorulan=sorulan,
        atlanan=atlanan,
        sayim=defter.sayim(),
        ilk_karar_ms=ilk_ms,
        son_karar_ms=son_ms,
        gecikme_ms_p50=float(np.percentile(g, 50)) if g.size else None,
        gecikme_ms_p95=float(np.percentile(g, 95)) if g.size else None,
        kuru=istemci is None,
    )


# ------------------------------------------------------------------ dondurma


def kararlar_cercevesi(defter: JevDefteri) -> pd.DataFrame:
    """Defterdeki her karar satırı düz bir çerçeve satırı. Sözlük alanları JSON metni."""
    satirlar = []
    for s in defter.kararlar():
        k = dict(s["karar"])
        for ad in _SOZLUK_ALANLARI:
            k[ad] = None if k.get(ad) is None else json.dumps(k[ad], sort_keys=True)
        k["durum_kodu"] = k.pop("durum")
        satirlar.append(k)
    if not satirlar:
        return pd.DataFrame(columns=list(JevKarari.model_fields))
    df = pd.DataFrame(satirlar)
    return df.sort_values(["karar_ms", "uretim_ms"], kind="stable").reset_index(drop=True)


def dondur(
    defter: JevDefteri,
    *,
    ayarlar: JevAyarlari,
    kok: str | Path = VARSAYILAN_KOK,
    girdi_sha256: Mapping[str, str] | None = None,
    saat: Callable[[], int] = simdi_ms,
) -> tuple[Path, dict[str, Any]]:
    """Defteri Parquet + manifest olarak dondurur. Döner: (dizin, manifest).

    Dizin adı Parquet dosyasının SHA-256'sının ilk 12 karakteri (`turetim_id`): aynı içerik
    aynı kimliği verir, dosya taşınınca kimlik değişmez (K-009, `common/hash.py`).
    """
    kimlik = defter.kosu_oku()
    if kimlik is None:
        raise TekrarHatasi("defterde koşu kimliği yok; dondurulacak bir şey yok")
    df = kararlar_cercevesi(defter)
    gecerli = df[df["durum_kodu"] == "gecerli"] if len(df) else df

    kok = Path(kok)
    gecici = kok / "_gecici"
    gecici.mkdir(parents=True, exist_ok=True)
    parquet_gecici = gecici / f"{kimlik['kosu']}.parquet"
    df.to_parquet(parquet_gecici, index=False, compression="zstd")
    sha = dosya_hash(parquet_gecici)
    turetim_id = sha[:12]
    hedef = kok / turetim_id
    hedef.mkdir(parents=True, exist_ok=True)
    parquet = hedef / "kararlar.parquet"
    if parquet.exists() and dosya_hash(parquet) != sha:
        raise TekrarHatasi(f"{hedef} zaten var ve içeriği farklı; dondurulmuş dosya ezilmez")
    parquet_gecici.replace(parquet)
    with contextlib.suppress(OSError):
        gecici.rmdir()

    leak = bool(gecerli["leak_riski"].any()) if len(gecerli) else True
    manifest: dict[str, Any] = {
        "turetim_id": turetim_id,
        "kararlar_sha256": sha,
        "kosu": kimlik["kosu"],
        "mod": kimlik["mod"],
        "model": ayarlar.model,
        "yayin_ms": ayarlar.yayin_ms,
        "egitim_kesim_ms": ayarlar.egitim_kesim_ms,
        "egitim_kesim_kaynagi": ayarlar.egitim_kesim_kaynagi,
        "soru_sha256": kimlik["soru_sha256"],
        "durum_surumu": ayarlar.durum_surumu,
        "kapsam_baslangic_ms": None if not len(df) else int(df["karar_ms"].min()),
        "kapsam_bitis_ms": None if not len(df) else int(df["karar_ms"].max()),
        "satir": int(len(df)),
        "gecerli": int(len(gecerli)),
        "sayim": defter.sayim(),
        "leak_riski": leak,
        "leak_riski_gerekcesi": (
            "kapsam kesimden önce başlıyor (K-049/4)"
            if leak and ayarlar.egitim_kesim_ms is not None
            else "kapsam kesimden sonra"
            if ayarlar.egitim_kesim_ms is not None
            else "eğitim kesimi bilinmiyor ve kapsam yayın tarihinden önce başlıyor; "
            "geriye dönük türetim kapıya giremez (K-074/3)"
            if leak
            else "eğitim kesimi bilinmiyor; kapsamın tamamı yayın tarihinden sonra, "
            "kesim ≤ yayın olduğundan t sonrası veri eğitimde olamaz (K-075)"
        ),
        "ileriye_donuk": False,
        "girdi_sha256": dict(girdi_sha256 or {}),
        "uretim_ms": saat(),
        "uretim_utc": utc_str(saat()),
        "git": git_durumu(),
        "defter_zinciri_gecerli": defter.dogrula(),
        "not": (
            "Backtest bu dosyayı okuyabilir; Jev'i çağıramaz (K-049/5). Bu türetim isabet "
            "kanıtı değildir; boru hattı, şema ve gecikme doğrulamasıdır."
        ),
    }
    manifest["manifest_sha256"] = nesne_hash({k: v for k, v in manifest.items()})
    (hedef / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return hedef, manifest


__all__ = [
    "VARSAYILAN_KOK",
    "TekrarHatasi",
    "TekrarOzeti",
    "dondur",
    "kararlar_cercevesi",
    "tekrar_kos",
]
