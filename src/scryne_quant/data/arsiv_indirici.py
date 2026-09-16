"""Arşivden çoklu sembol indirici: dosya planı, checksum, kaynak manifestosu, idempotency. (Faz 9)

`TarihselIndirici` REST'ten **aralık** indirir; bu modül arşivden **dosya** indirir. Birim
farklı olduğu için kaldığı yerden devam etmenin ölçüsü de farklı: depoda hangi barların
olduğu değil, **hangi arşiv dosyalarının hangi checksum'la** indirildiği. Bu bilgi
parquet'in yanındaki manifestoda durur (`<timeframe>.kaynak.json`) ve Faz 9'un "her dosyanın
SHA-256'sı kayıtlı" kriterinin kendisidir.

**Depo kökü ayrı (`data/evren`), `data/market` değil — ve bu bir karar.** İki sebep.
(1) Arşiv BTCUSDT 1h'in 2017'den başlayan geçmişini taşıyor, REST dosyası 2021-06'dan; aynı
dosyaya yazmak `data/market/BTCUSDT/1h.parquet`'in hash'ini değiştirirdi — ve o hash,
hipotez defterindeki 38 çekilişin `veri_sha256`sı (K-039). (2) İki kaynak birebir aynı
değil: ortak 45.576 barın 4'ünde hacim/işlem sayısı/kapanış farklı (ölçüldü, 2026-09-15).
Birleştirmek, hangi barın hangi kaynaktan geldiğini dosyada görünmez kılardı. Evren tek
kaynaktan (arşiv) kurulur; geçmiş ölçümlerin yeniden üretilebilirliği yeni bir veri
kaynağına feda edilmez.

**Akış, sembol başına atomik:** plan → eksik dosyaları indir → checksum → ayrıştır →
depodaki ham veriyle birleştir → **tümünü** doğrula → yaz → manifestoyu yaz. Tek bir dosya
doğrulanamazsa o sembol için hiçbir şey yazılmaz. Manifesto **depodan sonra** yazılır:
arada kesilen bir süreç, bir sonraki koşuda o dosyaları yeniden indirir; tersi sırada
kesilse manifesto depoda olmayan veriyi "indirildi" diye gösterirdi.

**Aylık ve günlük katman.** Aylık dosya ay bitince yayımlanır; içinde bulunulan ayın
günleri yalnızca günlük katmanda. Plan: tüm aylık dosyalar + son aylık aydan **sonraki**
günlük dosyalar. O ayın aylık dosyası yayımlandığında indirilir ve manifestodaki günlük
kayıtlar düşer; barların değeri aynı olduğu için depo dosyası değişmez.

**Yeniden yayımlanan dosya.** Manifestoda olan dosya varsayılan olarak yeniden
indirilmez: 25 bin dosyanın checksum'ını her koşuda yeniden sormak ~50 bin istek demek.
`tam_dogrulama=True` her dosyanın güncel checksum'ını sorar; değişen dosya yeniden inip
`degisen_dosyalar` altında raporlanır.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import pandas as pd

from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.depo import DepoKaydi, ParquetDepo
from scryne_quant.data.dogrulama import DogrulamaHatasi, KaliteRaporu, dogrula
from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI
from scryne_quant.exchange.binance_arsiv import (
    ArsivHatasi,
    ArsivKaynagi,
    aylik_dosyalar,
    checksum_dogrula,
    gunluk_dosyalar,
    sha256,
    zip_barlari,
)

#: Evren verisinin depo kökü (`.gitignore`'daki `/data/` altında).
VARSAYILAN_EVREN_DEPO: Final = Path("data/evren")

MANIFESTO_SONEKI: Final = ".kaynak.json"

#: Sembol içi eşzamanlı dosya indirme. Spike 6: 32 iş parçacığıyla 25.349 dosya ≈ 440 s,
#: hata 0.
VARSAYILAN_PARALEL: Final = 32


class ArsivIndirmeHatasi(Exception):
    """Bir sembolün arşiv indirmesi tamamlanamadı; o sembol için hiçbir şey yazılmadı."""


@dataclass(frozen=True, slots=True)
class ArsivIndirmeSonucu:
    sembol: str
    timeframe: str
    aylik_dosya: int
    gunluk_dosya: int
    inen_dosyalar: tuple[str, ...]
    degisen_dosyalar: tuple[str, ...]
    sure_s: float
    onceki_sha256: str | None
    depo: DepoKaydi | None = None
    kalite: KaliteRaporu | None = None
    veri_yok: bool = False
    manifesto: dict[str, str] = field(default_factory=dict)
    atilan_hizasiz_bar: dict[str, int] = field(default_factory=dict)

    @property
    def degisti(self) -> bool:
        return self.depo is not None and self.depo.sha256 != self.onceki_sha256

    def sozluk(self) -> dict[str, Any]:
        return {
            "sembol": self.sembol,
            "timeframe": self.timeframe,
            "veri_yok": self.veri_yok,
            "aylik_dosya": self.aylik_dosya,
            "gunluk_dosya": self.gunluk_dosya,
            "inen_dosya": len(self.inen_dosyalar),
            "degisen_dosyalar": list(self.degisen_dosyalar),
            "atilan_hizasiz_bar": dict(self.atilan_hizasiz_bar),
            "sure_s": round(self.sure_s, 2),
            "onceki_sha256": self.onceki_sha256,
            "sha256": self.depo.sha256 if self.depo else None,
            "degisti": self.degisti,
            "toplam_bar": self.depo.bar_sayisi if self.depo else 0,
            "bayt": self.depo.bayt if self.depo else 0,
            "kalite": self.kalite.sozluk() if self.kalite else None,
        }


@dataclass(frozen=True, slots=True)
class _InenDosya:
    anahtar: str
    sha256: str
    barlar: pd.DataFrame


class ArsivIndirici:
    """Arşivden sembol/timeframe başına indirip `ParquetDepo`ya yazar."""

    def __init__(
        self,
        kaynak: ArsivKaynagi,
        depo: ParquetDepo,
        *,
        paralel: int = VARSAYILAN_PARALEL,
    ) -> None:
        self.kaynak = kaynak
        self.depo = depo
        self.paralel = max(1, paralel)

    # ------------------------------------------------------------ manifesto

    def manifesto_yolu(self, sembol: str, timeframe: str) -> Path:
        parquet = self.depo.yol(sembol, timeframe)
        return parquet.with_name(f"{timeframe}{MANIFESTO_SONEKI}")

    def manifesto_oku(self, sembol: str, timeframe: str) -> dict[str, str]:
        """`{arşiv anahtarı: sha256}`. Depo dosyası yoksa manifesto **yok sayılır**: depoda
        olmayan veriyi "indirildi" diye gösteren bir manifesto, yeniden indirmeyi engellerdi."""
        yol = self.manifesto_yolu(sembol, timeframe)
        if not yol.exists() or not self.depo.var_mi(sembol, timeframe):
            return {}
        govde = json.loads(yol.read_text(encoding="utf-8"))
        return dict(govde["dosyalar"])

    def _hizasiz_oku(self, sembol: str, timeframe: str) -> dict[str, int]:
        yol = self.manifesto_yolu(sembol, timeframe)
        if not yol.exists() or not self.depo.var_mi(sembol, timeframe):
            return {}
        govde = json.loads(yol.read_text(encoding="utf-8"))
        return dict(govde.get("atilan_hizasiz_bar", {}))

    def _manifesto_yaz(
        self,
        sembol: str,
        timeframe: str,
        dosyalar: dict[str, str],
        hizasiz: dict[str, int],
    ) -> None:
        yol = self.manifesto_yolu(sembol, timeframe)
        govde = {
            "sembol": sembol.upper(),
            "timeframe": timeframe,
            "kaynak": "data.binance.vision",
            "dosyalar": dict(sorted(dosyalar.items())),
            # Izgaraya oturmayan ve **atılan** bar sayısı, dosya başına. Atılan veri kayıtsız
            # kalmamalı: depoda yalnızca `gap` bayrağı olarak görünür, sebebi burada.
            "atilan_hizasiz_bar": {a: n for a, n in sorted(hizasiz.items()) if a in dosyalar},
        }
        gecici = yol.with_suffix(".json.tmp")
        gecici.write_text(
            json.dumps(govde, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        gecici.replace(yol)

    # ----------------------------------------------------------------- plan

    def plan(self, sembol: str, timeframe: str) -> tuple[dict[str, str], dict[str, str]]:
        """(aylık `{YYYY-MM: anahtar}`, günlük `{YYYY-MM-DD: anahtar}`).

        Günlük dosyalar yalnızca son aylık aydan **sonrası** için: aylık dosyası olan bir
        ayın günlük kopyasını indirmek aynı barları iki kez indirmektir.
        """
        aylik = aylik_dosyalar(self.kaynak, sembol, timeframe)
        son_ay = max(aylik) if aylik else ""
        gunluk = {
            gun: anahtar
            for gun, anahtar in gunluk_dosyalar(self.kaynak, sembol, timeframe).items()
            if gun[:7] > son_ay
        }
        return aylik, gunluk

    # --------------------------------------------------------------- indirme

    def _dosya_indir(self, anahtar: str) -> _InenDosya:
        zip_bayt = self.kaynak.getir(anahtar)
        if zip_bayt is None:
            raise ArsivHatasi(f"{anahtar}: listede var ama indirilemedi (404)")
        ozet = checksum_dogrula(anahtar, zip_bayt, self.kaynak.getir(f"{anahtar}.CHECKSUM"))
        return _InenDosya(anahtar, ozet, zip_barlari(anahtar, zip_bayt))

    def _guncel_checksum(self, anahtar: str) -> str | None:
        bayt = self.kaynak.getir(f"{anahtar}.CHECKSUM")
        if bayt is None:
            return None
        parca = bayt.decode("ascii", errors="replace").split()
        return parca[0] if parca else None

    def indir(
        self,
        sembol: str,
        timeframe: str = "1h",
        *,
        tam_dogrulama: bool = False,
    ) -> ArsivIndirmeSonucu:
        sembol = sembol.upper()
        t0 = time.perf_counter()
        aylik, gunluk = self.plan(sembol, timeframe)
        planli = {**{a: a for a in aylik.values()}, **{a: a for a in gunluk.values()}}
        vardi = self.depo.var_mi(sembol, timeframe)
        onceki = self.depo.sha256(sembol, timeframe) if vardi else None

        if not planli:
            return ArsivIndirmeSonucu(
                sembol=sembol,
                timeframe=timeframe,
                aylik_dosya=0,
                gunluk_dosya=0,
                inen_dosyalar=(),
                degisen_dosyalar=(),
                sure_s=time.perf_counter() - t0,
                onceki_sha256=onceki,
                veri_yok=True,
            )

        manifesto = self.manifesto_oku(sembol, timeframe)
        gerekli = sorted(a for a in planli if a not in manifesto)
        degisen: list[str] = []
        if tam_dogrulama:
            kayitli = sorted(a for a in planli if a in manifesto)
            with ThreadPoolExecutor(self.paralel) as havuz:
                guncel = dict(zip(kayitli, havuz.map(self._guncel_checksum, kayitli), strict=True))
            degisen = [a for a in kayitli if guncel[a] != manifesto[a]]
            gerekli = sorted({*gerekli, *degisen})

        try:
            with ThreadPoolExecutor(self.paralel) as havuz:
                inenler = list(havuz.map(self._dosya_indir, gerekli))
        except ArsivHatasi as hata:
            raise ArsivIndirmeHatasi(f"{sembol} {timeframe}: {hata}") from hata

        inenler, yeni_hizasiz = _hizasizlari_at(inenler, timeframe)
        hizasiz = {**self._hizasiz_oku(sembol, timeframe), **yeni_hizasiz}

        yeni_manifesto = {**manifesto, **{d.anahtar: d.sha256 for d in inenler}}
        # Aylık dosyası gelmiş ayların günlük kayıtları düşer (barlar aylık dosyada).
        aylik_aylar = set(aylik)
        yeni_manifesto = {
            a: h
            for a, h in yeni_manifesto.items()
            if not (a in manifesto and a not in planli and _gun_ayi(a) in aylik_aylar)
        }

        if not inenler and onceki is not None:
            if yeni_manifesto != manifesto:
                self._manifesto_yaz(sembol, timeframe, yeni_manifesto, hizasiz)
            return ArsivIndirmeSonucu(
                sembol=sembol,
                timeframe=timeframe,
                aylik_dosya=len(aylik),
                gunluk_dosya=len(gunluk),
                inen_dosyalar=(),
                degisen_dosyalar=(),
                sure_s=time.perf_counter() - t0,
                onceki_sha256=onceki,
                depo=_mevcut_kayit(self.depo, sembol, timeframe, onceki),
                manifesto=yeni_manifesto,
            )

        birlesik = self._ham_birlestir(sembol, timeframe, [d.barlar for d in inenler])
        if birlesik.empty:
            raise ArsivIndirmeHatasi(f"{sembol} {timeframe}: arşiv dosyaları boş ve depo da boş")

        try:
            bayrakli, kalite = dogrula(birlesik, timeframe, sembol=sembol)
        except DogrulamaHatasi as hata:
            raise ArsivIndirmeHatasi(f"{sembol} {timeframe}: {hata}") from hata
        kayit = self.depo.yaz(sembol, timeframe, bayrakli)
        self._manifesto_yaz(sembol, timeframe, yeni_manifesto, hizasiz)

        return ArsivIndirmeSonucu(
            sembol=sembol,
            timeframe=timeframe,
            aylik_dosya=len(aylik),
            gunluk_dosya=len(gunluk),
            inen_dosyalar=tuple(d.anahtar for d in inenler),
            degisen_dosyalar=tuple(degisen),
            sure_s=time.perf_counter() - t0,
            onceki_sha256=onceki,
            depo=kayit,
            kalite=kalite,
            manifesto=yeni_manifesto,
            atilan_hizasiz_bar=yeni_hizasiz,
        )

    def _ham_birlestir(
        self, sembol: str, timeframe: str, parcalar: list[pd.DataFrame]
    ) -> pd.DataFrame:
        """Depodaki ham veri + inen dosyalar. Çakışan `open_time`'da **inen** kazanır.

        `TarihselIndirici._ham_birlestir` ile aynı kural ve aynı gerekçe: kendi depomuzla
        yeni indirmenin çakışması borsa anomalisi değil, olağan işleyiş (ör. günlük dosyanın
        yerine aylık dosyanın gelmesi); sahte `duplicate` bayrağı üretmemeli. Bir **dosyanın
        kendi içindeki** tekrarlar ise doğrulamaya olduğu gibi ulaşır.
        """
        dolu = [p for p in parcalar if not p.empty]
        yeni = pd.concat(dolu, ignore_index=True) if dolu else None
        if not self.depo.var_mi(sembol, timeframe):
            return (
                yeni.reset_index(drop=True)
                if yeni is not None
                else pd.DataFrame(columns=list(HAM_BAR_SUTUNLARI))
            )
        mevcut = self.depo.oku(sembol, timeframe).loc[:, list(HAM_BAR_SUTUNLARI)]
        if yeni is None:
            return mevcut
        mevcut = mevcut[~mevcut["open_time"].isin(set(yeni["open_time"]))]
        return pd.concat([mevcut, yeni], ignore_index=True)


def _hizasizlari_at(
    inenler: list[_InenDosya], timeframe: str
) -> tuple[list[_InenDosya], dict[str, int]]:
    """Timeframe ızgarasına oturmayan barları atar; dosya başına sayar.

    **Ölçülen vaka:** `BTCUSDT-1h-2018-02` — Binance'in 2018-02-08 kesintisinden sonra
    2018-02-09 09:28:14.789'dan 2018-02-11 03:28:14.789'a kadar 43 saatlik bar ızgaradan
    28 dk 14,789 sn kaymış açılışla yazılmış; ızgaralı barlarla hiçbiri çakışmıyor.

    **Neden atılıyor, yuvarlanmıyor:** 09:28–10:28 aralığının barı 09:00–10:00 barı değildir;
    yuvarlamak olmayan bir barı varmış gibi göstermektir (K-024). Doğrulama katmanı hizasız
    barı K-005 ihlali olarak **reddeder** ve REST yolunda bu kural değişmiyor; arşivde ise
    tek bir kaymış aralık yüzünden sembolün tüm geçmişini reddetmek, evrenden en eski ve en
    likit isimleri silmek olurdu. Atılan aralık depoda `gap` bayrağıyla görünür, sayısı
    manifestoda ve raporda.
    """
    adim = timeframe_ms(timeframe)
    temiz: list[_InenDosya] = []
    sayim: dict[str, int] = {}
    for d in inenler:
        maske = d.barlar["open_time"] % adim != 0
        if maske.any():
            sayim[d.anahtar] = int(maske.sum())
            temiz.append(
                _InenDosya(d.anahtar, d.sha256, d.barlar.loc[~maske].reset_index(drop=True))
            )
        else:
            temiz.append(d)
    return temiz, sayim


_GUN_ANAHTARI: Final = re.compile(r"/daily/.*-(\d{4}-\d{2})-\d{2}\.zip$")


def _gun_ayi(anahtar: str) -> str:
    """Günlük dosya anahtarının `YYYY-MM`'i; günlük değilse boş."""
    eslesme = _GUN_ANAHTARI.search(anahtar)
    return eslesme.group(1) if eslesme else ""


def _mevcut_kayit(depo: ParquetDepo, sembol: str, timeframe: str, ozet: str) -> DepoKaydi:
    yol = depo.yol(sembol, timeframe)
    df = depo.oku(sembol, timeframe)
    return DepoKaydi(
        yol=yol,
        bar_sayisi=len(df),
        ilk_ms=int(df["open_time"].iloc[0]),
        son_ms=int(df["open_time"].iloc[-1]),
        sha256=ozet,
        bayt=yol.stat().st_size,
    )


def coklu_indir(
    indirici: ArsivIndirici,
    semboller: list[str],
    timeframe: str = "1h",
    *,
    tam_dogrulama: bool = False,
    ilerleme: Callable[[int, int, str], None] | None = None,
) -> tuple[list[ArsivIndirmeSonucu], dict[str, str]]:
    """Sembolleri sırayla indirir. Bir sembolün hatası diğerlerini durdurmaz ama **kaydedilir**:
    dönüşteki hata sözlüğü boş değilse indirme tamamlanmamıştır."""
    sonuclar: list[ArsivIndirmeSonucu] = []
    hatalar: dict[str, str] = {}
    for i, sembol in enumerate(semboller, start=1):
        try:
            sonuclar.append(indirici.indir(sembol, timeframe, tam_dogrulama=tam_dogrulama))
        except (ArsivIndirmeHatasi, ArsivHatasi) as hata:
            hatalar[sembol.upper()] = str(hata)
        if ilerleme is not None:
            ilerleme(i, len(semboller), sembol.upper())
    return sonuclar, hatalar


__all__ = [
    "MANIFESTO_SONEKI",
    "VARSAYILAN_EVREN_DEPO",
    "ArsivIndirici",
    "ArsivIndirmeHatasi",
    "ArsivIndirmeSonucu",
    "coklu_indir",
    "sha256",
]
