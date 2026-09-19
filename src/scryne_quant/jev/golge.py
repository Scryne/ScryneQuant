"""Gölge motoru: kapanmış 1h bar → kanonik durum → Jev → defter. Emir yok. (K-074/1, K-074/5)

`live/motor.py::PaperMotoru`nun **gözlemci ikizi** — ama ondan ayrı bir süreçte koşar ve ona
dokunmaz. Aynı kaynaklar, aynı doğrulama:

- Barlar `exchange/akis.BinanceBarAkisi`den (paper'ın kullandığı akış; kapanmışlık bayrağı,
  kopma sonrası REST resync), pencere `live/pencere.BarPenceresi` (aynı `dogrula`).
- Isınma barları `data/market` deposundan + REST'ten (`Kaynak.BACKFILL`): paper'ın
  `live/baslat.isinma_barlari`sıyla aynı kural, burada yeniden yazıldı çünkü `live/baslat`
  risk ve execution'ı import ediyor ve bu paket onlara ulaşamaz (`test_jev_izolasyon.py`).
- Funding `exchange/turev_rest.BinanceTurevRest.funding` (arşivle bit düzeyinde aynı ölçüldü).

**Bar başına akış** (`bar_isle`):

1. Bar pencereye girer, pencere yeniden doğrulanır. Son bar `ok` değilse (`backfilled`,
   `gap`…) ya da pencere `PENCERE_BAR`dan kısaysa **durum kurulmaz**, olay yazılır (K-028'in
   karşılığı; replay ile eşitlik için pencere tam olmalı).
2. Funding tazelenir (hata olursa eldeki seri kalır; durum `bayat`/`eksik` etiketler).
3. Kanonik durum kurulur, hash'lenir; **replay'deki kurucunun kendisi** (tek state builder).
4. Jev'e sorulur; her hata `KararDurumu` koduyla kayda gider, karar alanı boş kalır
   (fail-closed). Önceki karar hiçbir yolla taşınmaz.
5. Karar + durum + ham yanıt tek satırda deftere yazılır (zincir hash).
6. Her `tutarlilik_her_n_karar` geçerli kararda aynı durum ikinci kez sorulur ve sapma olay
   olarak yazılır (K-074/6). İkinci cevap karar **değildir**.

Bu sınıfın `Sinyal`, `RiskMotoru`, `execution` ile hiçbir bağı yok ve olamaz: import
grafiği statik testle kapalı. Jev sürecinin ölmesi paper sürecini etkilemez — ayrı
süreç, ayrı kilit (`live/kilit.KosuKilidi`), ayrı dosya.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np

from scryne_quant.common.zaman import simdi_ms, timeframe_ms, utc_str
from scryne_quant.data.depo import ParquetDepo
from scryne_quant.exchange.akis import df_barlara
from scryne_quant.jev.ayarlar import JevAyarlari
from scryne_quant.jev.defter import JevDefteri, OlayTuru, kosu_kimligi_kur
from scryne_quant.jev.durum import KARAR_TF, PENCERE_BAR, durum_hash, kanonik_durum
from scryne_quant.jev.istemci import Istemci, sor
from scryne_quant.jev.karar import JevKarari, karar_kur
from scryne_quant.jev.sorular import soru_sha256
from scryne_quant.live.akis import Bar, BarAkisi, Kaynak
from scryne_quant.live.pencere import BarPenceresi

#: Isınma penceresi: durumun okuduğu pencere + pay (kopma/backfill barları için).
VARSAYILAN_KAPASITE: Final = PENCERE_BAR + 48

#: Funding tarihçesi: 90 günlük persentil için 270 ödeme; 120 gün pay bırakır.
FUNDING_GECMIS_MS: Final = 120 * 24 * 3_600_000

#: `funding(sembol, baslangic_ms) -> [(funding_time_ms, oran), ...]` sözleşmesi
#: (`exchange/turev_rest.BinanceTurevRest.funding`).
FundingKaynagi = Callable[[str, int], list[tuple[int, float]]]


class GolgeHatasi(RuntimeError):
    """Gölge motoru sözleşmesi ihlal edildi."""


@dataclass(frozen=True, slots=True)
class BarSonucu:
    bar_ms: int
    islendi: bool
    """Durum kuruldu ve Jev'e soruldu mu (fail-closed hata da "işlendi" sayılır: kayıt var)."""

    sebep: str | None
    karar: JevKarari | None

    def sozluk(self) -> dict[str, Any]:
        return {
            "bar_ms": self.bar_ms,
            "bar_utc": utc_str(self.bar_ms),
            "islendi": self.islendi,
            "sebep": self.sebep,
            "karar": None if self.karar is None else self.karar.sozluk(),
        }


class GolgeMotoru:
    """Tek sembol, tek timeframe, karar üretmeyen gözlemci."""

    def __init__(
        self,
        *,
        kosu: str,
        ayarlar: JevAyarlari,
        defter: JevDefteri,
        istemci: Istemci,
        funding_kaynagi: FundingKaynagi | None = None,
        kapasite: int = VARSAYILAN_KAPASITE,
        saat: Callable[[], int] = simdi_ms,
    ) -> None:
        if kapasite < PENCERE_BAR:
            raise GolgeHatasi(f"pencere kapasitesi en az {PENCERE_BAR} olmalı: {kapasite}")
        self.kosu = kosu
        self.ayarlar = ayarlar
        self.defter = defter
        self.istemci = istemci
        self.funding_kaynagi = funding_kaynagi
        self.saat = saat
        self.soru_sha256 = soru_sha256(ayarlar.model)
        self.pencere = BarPenceresi(ayarlar.sembol, KARAR_TF, kapasite=kapasite)
        self._funding_z = np.zeros(0, dtype=np.int64)
        self._funding_r = np.zeros(0, dtype=np.float64)
        self._gecerli_sayaci = 0
        self._son_bar_ms: int | None = None
        self.defter.kosu_yaz(kosu_kimligi_kur(kosu, "golge", ayarlar, self.soru_sha256))

    # ------------------------------------------------------------------ ölçüm

    @property
    def son_bar_ms(self) -> int | None:
        return self._son_bar_ms

    def ozet(self) -> dict[str, Any]:
        return {
            "kosu": self.kosu,
            "sembol": self.ayarlar.sembol,
            "model": self.ayarlar.model,
            "soru_sha256": self.soru_sha256,
            "pencere": self.pencere.sozluk(),
            "funding_odeme": int(self._funding_z.size),
            "son_funding_ms": None if not self._funding_z.size else int(self._funding_z[-1]),
            "son_bar_ms": self._son_bar_ms,
            "sayim": self.defter.sayim(),
        }

    # ------------------------------------------------------------------ ısınma

    def isinma(self, barlar: Iterable[Bar]) -> int:
        """Isınma barlarını pencereye alır (hepsi `BACKFILL`: bu koşu onları canlı almadı)."""
        n = 0
        for bar in barlar:
            if bar.kaynak is not Kaynak.BACKFILL:
                raise GolgeHatasi("ısınma barı BACKFILL kaynaklı olmalı (K-006)")
            n += int(self.pencere.ekle(bar))
        self.defter.olay_yaz(
            OlayTuru.BASLADI,
            {"isinma_bar": n, "pencere": self.pencere.sozluk(), "pencere_bar": PENCERE_BAR},
            zaman_ms=self.saat(),
        )
        return n

    def funding_yukle(self, kayitlar: Iterable[tuple[int, float]]) -> int:
        """Funding serisini yükler/birleştirir (artan `funding_time`); ödeme sayısını döner."""
        yeni = sorted({int(z): float(r) for z, r in kayitlar}.items())
        if not yeni:
            return int(self._funding_z.size)
        mevcut = dict(zip(self._funding_z.tolist(), self._funding_r.tolist(), strict=True))
        mevcut.update(yeni)
        sirali = sorted(mevcut.items())
        self._funding_z = np.asarray([z for z, _ in sirali], dtype=np.int64)
        self._funding_r = np.asarray([r for _, r in sirali], dtype=np.float64)
        return int(self._funding_z.size)

    def _funding_tazele(self, t_ms: int) -> None:
        if self.funding_kaynagi is None:
            return
        bas = int(self._funding_z[-1]) + 1 if self._funding_z.size else t_ms - FUNDING_GECMIS_MS
        try:
            self.funding_yukle(self.funding_kaynagi(self.ayarlar.sembol, bas))
        except Exception as e:  # noqa: BLE001 - funding hatası koşuyu durdurmaz; durum etiketler
            self.defter.olay_yaz(
                OlayTuru.BAYAT_VERI,
                {"kaynak": "funding", "hata": f"{type(e).__name__}: {e}", "bar_ms": t_ms},
                zaman_ms=self.saat(),
            )

    # ------------------------------------------------------------------ döngü

    def bar_isle(self, bar: Bar) -> BarSonucu:
        """Kapanmış bir barı işler. Hiçbir durumda fırlatmaz; sebep kayda gider."""
        t = bar.open_time
        yeni = self.pencere.ekle(bar)
        if not yeni and self._son_bar_ms is not None and t <= self._son_bar_ms:
            # Aynı barın revizyonu: karar yeniden verilmez (paper'daki duplicate kuralı).
            self.defter.olay_yaz(
                OlayTuru.BAR_ATLANDI, {"bar_ms": t, "sebep": "revizyon"}, zaman_ms=self.saat()
            )
            return BarSonucu(t, False, "revizyon", None)
        self._son_bar_ms = t

        if len(self.pencere) < PENCERE_BAR:
            sebep = f"pencere eksik: {len(self.pencere)} < {PENCERE_BAR}"
            self.defter.olay_yaz(
                OlayTuru.BAR_ATLANDI, {"bar_ms": t, "sebep": sebep}, zaman_ms=self.saat()
            )
            return BarSonucu(t, False, sebep, None)
        if not self.pencere.son_bar_ok_mu():
            kalite = str(self.pencere.diziler()["quality_status"][-1])
            sebep = f"karar barı ok değil: {kalite}"
            self.defter.olay_yaz(
                OlayTuru.BAR_ATLANDI,
                {"bar_ms": t, "sebep": sebep, "kalite": kalite},
                zaman_ms=self.saat(),
            )
            return BarSonucu(t, False, sebep, None)

        self._funding_tazele(t)
        diziler = self.pencere.diziler()
        durum = kanonik_durum(
            diziler,
            len(self.pencere) - 1,
            sembol=self.ayarlar.sembol,
            funding_time_ms=self._funding_z if self._funding_z.size else None,
            funding_rate=self._funding_r if self._funding_r.size else None,
        )
        karar = self._sor_ve_yaz(durum)
        if karar.gecerli:
            self._gecerli_sayaci += 1
            if self._gecerli_sayaci % self.ayarlar.tutarlilik_her_n_karar == 0:
                self._tutarlilik(durum, karar)
        return BarSonucu(t, True, None if karar.gecerli else karar.hata, karar)

    def _sor_ve_yaz(self, durum: dict[str, Any], *, yaz: bool = True) -> JevKarari:
        h = durum_hash(durum)
        sonuc = sor(self.istemci, durum, self.ayarlar)
        karar = karar_kur(
            kosu=self.kosu,
            durum=durum,
            durum_hash=h,
            soru_sha256=self.soru_sha256,
            model_istenen=self.ayarlar.model,
            uretim_ms=self.saat(),
            bayat_ms=self.ayarlar.bayat_ms,
            yon_marji=self.ayarlar.yon_marji,
            egitim_kesim_ms=self.ayarlar.egitim_kesim_ms,
            yanit=sonuc.yanit,
            durum_kodu=sonuc.durum,
            hata=sonuc.hata,
            gecikme_ms=sonuc.gecikme_ms,
            geriye_donuk=False,
        )
        if yaz:
            self.defter.karar_yaz(karar, durum, sonuc.yanit)
        return karar

    def _tutarlilik(self, durum: dict[str, Any], ilk: JevKarari) -> None:
        ikinci = self._sor_ve_yaz(durum, yaz=False)
        self.defter.tutarlilik_yaz(ilk, ikinci)


# ------------------------------------------------------------------ kurulum yardımcıları


def isinma_barlari(
    sembol: str,
    *,
    depo_kok: Path,
    adaptor: Any | None,
    kapasite: int = VARSAYILAN_KAPASITE,
) -> list[Bar]:
    """Isınma penceresi: depodan (`data/market`) + REST'ten, hepsi `BACKFILL`.

    `live/baslat.isinma_barlari` ile aynı kural (oradan import edilemiyor: bkz. modül
    başlığı). `adaptor` `None` ise yalnızca depo; REST erişilemiyorsa pencere akıştan büyür.
    """
    adim = timeframe_ms(KARAR_TF)
    barlar: list[Bar] = []
    parquet = ParquetDepo(depo_kok)
    if parquet.var_mi(sembol, KARAR_TF):
        barlar = df_barlara(parquet.oku(sembol, KARAR_TF).tail(kapasite), kaynak=Kaynak.BACKFILL)
    if adaptor is None:
        return barlar
    simdi = adaptor.sunucu_zamani_ms()
    baslangic = barlar[-1].open_time + adim if barlar else simdi - kapasite * adim
    while baslangic < simdi:
        yeni = adaptor.klines(sembol, KARAR_TF, baslangic, simdi)
        if yeni.empty:
            break
        barlar.extend(df_barlara(yeni, kaynak=Kaynak.BACKFILL))
        baslangic = barlar[-1].open_time + adim
    return barlar[-kapasite:]


class GolgeKosturucu:
    """Akış → gölge motoru döngüsü. Ayrı süreç; paper koşturucusuna dokunmaz.

    Durdurma isteği (`live/durdurma.py` bayrağı) barla değil **periyodik** yoklanır: 1h
    timeframe'de bir sonraki barı beklemek, "durdur" dedikten sonra bir saat çalışmak demek
    olurdu (`live/kosturucu.py`nin bayatlık yoklamasıyla aynı gerekçe).
    """

    def __init__(
        self,
        motor: GolgeMotoru,
        akis: BarAkisi,
        *,
        bar_kancasi: Callable[[BarSonucu], None] | None = None,
        durdurma_istegi: Callable[[], dict[str, Any] | None] | None = None,
        yoklama_araligi_s: float = 30.0,
    ) -> None:
        self.motor = motor
        self.akis = akis
        self.bar_kancasi = bar_kancasi
        self.durdurma_istegi = durdurma_istegi
        self.yoklama_araligi_s = yoklama_araligi_s
        self.islenen_bar = 0
        self._durduruldu = False
        self.durdurma_sebebi: dict[str, Any] | None = None

    def durdur(self, sebep: dict[str, Any] | None = None) -> None:
        self._durduruldu = True
        self.durdurma_sebebi = sebep
        self.akis.kapat()

    async def _yoklama(self) -> None:
        while not self._durduruldu:
            await asyncio.sleep(self.yoklama_araligi_s)
            istek = self.durdurma_istegi() if self.durdurma_istegi else None
            if istek is not None:
                self.durdur({"sebep": "istek", "istek": istek})
                return

    async def calistir(self) -> dict[str, Any]:
        hata: str | None = None
        yoklama = asyncio.create_task(self._yoklama())
        try:
            async for bar in self.akis.barlar():
                if self._durduruldu:
                    break
                sonuc = self.motor.bar_isle(bar)
                self.islenen_bar += 1
                if self.bar_kancasi is not None:
                    self.bar_kancasi(sonuc)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - kaydedilip yükseltiliyor, yutulmuyor
            hata = f"{type(e).__name__}: {e}"
            self.motor.defter.olay_yaz(
                OlayTuru.HATA, {"hata": hata, "islenen_bar": self.islenen_bar}
            )
            raise
        finally:
            self._durduruldu = True
            yoklama.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await yoklama
            # Akışın aiohttp oturumu kapatılmazsa "Unclosed client session" bırakır
            # (`live/kosturucu.py` ile aynı kapanış).
            temizle = getattr(self.akis, "temizle", None)
            if temizle is not None:
                with contextlib.suppress(Exception):
                    await temizle()
            self.motor.defter.olay_yaz(
                OlayTuru.DURDU,
                {"islenen_bar": self.islenen_bar, "hata": hata, **(self.durdurma_sebebi or {})},
            )
        return {"islenen_bar": self.islenen_bar, "hata": hata, **self.motor.ozet()}


__all__ = [
    "FUNDING_GECMIS_MS",
    "VARSAYILAN_KAPASITE",
    "BarSonucu",
    "GolgeHatasi",
    "GolgeKosturucu",
    "GolgeMotoru",
    "isinma_barlari",
]
