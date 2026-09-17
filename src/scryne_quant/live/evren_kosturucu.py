"""Evren paper koşucusu: motoru canlı birleşik akışa bağlayan döngü. (Faz 14, Aşama E)

Parçalar ayrı ayrı testli; bu modül onları sıraya koyar:

1. **Kilit, pid, bayraklar** — tek sembollü koşuyla aynı modüller (`kilit`, `kill`, `durdurma`).
2. **Başlangıç** — depoda adım varsa `EvrenPaperMotoru.toparlan` (yeniden üretim, K-038); yoksa
   ısınma: evren tablosundan üyelik, REST'ten her üyenin son `isinma_bar + pay` barı, toplu ısınma.
3. **Boşluk tamamlama** — son işlenen bardan şimdiye kadar kapanmış saatler REST'ten `BACKFILL`
   olarak gelir (kapalı kalınan süre; K-006: `backfilled` bayrağı, K-028: fill iddia edilmez).
4. **Döngü** — birleşik akıştan gelen bar hem motora (bilindiği adımla) hem ızgara toplayıcıya
   gider; toplayıcının teslim ettiği her saat bir motor adımıdır. Üye listesi değişirse akış
   yeni sembollerle yeniden kurulur.
5. **SAFE_MODE işareti** (K-065) toparlanmadan sonra risk motorunu kilitler.

Saat, uyku, REST adaptörü ve akış fabrikası dışarıdan verilir: test sahte olanlarla koşar.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from scryne_quant.common.zaman import simdi_ms, timeframe_ms, utc_str
from scryne_quant.exchange.akis import df_barlara
from scryne_quant.live import durdurma as durdurma_mod
from scryne_quant.live import kill as kill_mod
from scryne_quant.live.akis import Bar, Kaynak
from scryne_quant.live.canli_evren import AyUyeligi, ay_metni
from scryne_quant.live.evren_depo import EvrenKosuDeposu
from scryne_quant.live.evren_motor import EvrenPaperMotoru
from scryne_quant.live.evren_yenileme import ay_basi_ms
from scryne_quant.live.izgara_toplayici import VARSAYILAN_BEKLEME_MS, IzgaraToplayici
from scryne_quant.live.kilit import KosuKilidi
from scryne_quant.risk.motor import RiskMotoru

#: Isınmaya stratejinin kendi ısınmasının üstüne eklenen pay (bar).
ISINMA_PAYI = 48

#: Toplayıcı yoklama periyodu (saniye).
YOKLAMA_S = 5.0


class KlineKaynagi(Protocol):
    def klines(self, sembol: str, timeframe: str, baslangic_ms: int, bitis_ms: int
               ) -> pd.DataFrame: ...


AkisFabrikasi = Callable[[Sequence[str], dict[str, int]], Any]
"""`(semboller, son_teslim) -> akış`; akışın `barlar()` async üreteci `(sembol, Bar)` verir."""


@dataclass
class EvrenTablosu:
    """Koşunun kullandığı PIT evren tablosu (dosyadan). Hash meta'dan gelir, uydurulmaz."""

    tablo: pd.DataFrame
    tablo_hash: str
    yol: Path | None = None
    _mtime: float | None = None
    kural_kimlik: str | None = None

    @classmethod
    def oku(cls, parquet: str | Path) -> EvrenTablosu:
        yol = Path(parquet)
        meta = json.loads(yol.with_suffix(".json").read_text(encoding="utf-8"))
        return cls(pd.read_parquet(yol), str(meta["tablo_hash"]), yol, yol.stat().st_mtime,
                   meta.get("kural_kimlik"))

    def yenile(self) -> bool:
        """Dosya değiştiyse yeniden okur (aylık yenileme yeni ayı ekler). Değiştiyse `True`.

        Önceki ayların listesi yeni dosyada **farklıysa** motor bunu reddeder
        (`EvrenPaperMotoru.uyelik_ekle`): geçmiş ayın üyeliği sessizce değişemez.
        """
        if self.yol is None or not self.yol.exists():
            return False
        mtime = self.yol.stat().st_mtime
        if mtime == self._mtime:
            return False
        yeni = EvrenTablosu.oku(self.yol)
        if yeni.kural_kimlik != self.kural_kimlik:
            raise ValueError(f"evren tablosunun kuralı değişmiş: {self.kural_kimlik} → "
                             f"{yeni.kural_kimlik}; aylık yenileme aynı kuralla üretilmeli")
        self.tablo, self.tablo_hash, self._mtime = yeni.tablo, yeni.tablo_hash, yeni._mtime
        return True

    def aylar(self) -> list[str]:
        return sorted(set(self.tablo["ay"].astype(str)))

    def uyelik(self, ay: str) -> AyUyeligi | None:
        satir = self.tablo[self.tablo["ay"].astype(str) == ay]
        if satir.empty:
            return None
        return AyUyeligi(ay, tuple(sorted(satir["sembol"].astype(str))), self.tablo_hash)


def _rest_barlar(kaynak: KlineKaynagi, sembol: str, timeframe: str, baslangic: int, bitis: int
                 ) -> list[Bar]:
    """`[baslangic, bitis)` aralığındaki kapanmış barlar, sayfa sayfa, `BACKFILL`."""
    adim = timeframe_ms(timeframe)
    cikti: list[Bar] = []
    imlec = baslangic
    while imlec < bitis:
        df = kaynak.klines(sembol, timeframe, imlec, bitis)
        barlar = [b for b in df_barlara(df, kaynak=Kaynak.BACKFILL) if b.open_time < bitis]
        if not barlar:
            break
        cikti.extend(barlar)
        imlec = barlar[-1].open_time + adim
    return cikti


@dataclass
class EvrenKosucu:
    kosu_yolu: Path
    kimlik: dict[str, Any]
    kurulum: dict[str, Any]
    """`EvrenPaperMotoru` argümanları (`depo` hariç)."""

    tablo: EvrenTablosu
    rest: KlineKaynagi
    akis_fabrikasi: AkisFabrikasi
    saat: Callable[[], int] = simdi_ms
    bekleme_ms: int = VARSAYILAN_BEKLEME_MS
    gunluk: Callable[[str], None] = print
    turev: Any = None
    """Funding/premium kaynağı (`exchange/turev_rest.BinanceTurevRest` arayüzü); yalnızca
    `kurulum["turev"]` açıksa kullanılır."""

    def __post_init__(self) -> None:
        self.timeframe = str(self.kurulum.get("timeframe", "1h"))
        self._adim = timeframe_ms(self.timeframe)
        self._durdur = False
        self.motor: EvrenPaperMotoru | None = None
        self.depo: EvrenKosuDeposu | None = None
        self._gecikme_bildirildi: set[str] = set()

    # ------------------------------------------------------------------ yardımcılar

    def _son_kapanmis(self) -> int:
        """Kapanmış son barın açılış zamanı."""
        return (self.saat() // self._adim) * self._adim - self._adim

    def _uyelikleri_isle(self, motor: EvrenPaperMotoru, bas: int, bit: int) -> None:
        """`[bas, bit]` aralığına düşen ayların tabloda olan üye listelerini motora ekler.

        Aralığın son ayı tabloda yoksa dosya yeniden okunur (aylık yenileme). Hâlâ yoksa motor
        bilinen en son ayın listesiyle devam eder ve bu `uyelik_gecikmesi` olarak kaydedilir.
        """
        if ay_metni(bit) not in motor.takvim().aylar and ay_metni(bit) not in self.tablo.aylar():
            if self.tablo.yenile():
                motor.depo.olay_yaz("evren_tablosu_yenilendi",
                                    ayrinti={"tablo_hash": self.tablo.tablo_hash})
            elif ay_metni(bit) not in self._gecikme_bildirildi:
                self._gecikme_bildirildi.add(ay_metni(bit))
                motor.depo.olay_yaz("uyelik_gecikmesi", bar_ms=bit,
                                    ayrinti={"ay": ay_metni(bit)})
        for ay in self.tablo.aylar():
            if ay_metni(bas)[:7] <= ay <= ay_metni(bit)[:7]:
                u = self.tablo.uyelik(ay)
                if u is not None and motor.uyelik_ekle(u):
                    motor.depo.olay_yaz("uyelik", ayrinti={"ay": ay, "sembol": len(u.semboller)})
                    if motor.adim_sayisi:  # ısınmada `baslat` bütün sembolleri zaten çeker
                        self._yeni_uyeleri_doldur(motor, u, bit)

    def _yeni_uyeleri_doldur(self, motor: EvrenPaperMotoru, u: AyUyeligi, bit: int) -> None:
        """Evrene yeni giren sembollerin geçmişini REST'ten tamamlar (`bit` dahil).

        Backtest'te üye olmadan önceki barlar veride zaten var; canlıda sembol hiç izlenmediyse
        yoktur. Doldurulmazsa strateji yeni üyeyi kısa geçmişle görür ve canlı backtest'ten
        sessizce ayrışır. Barlar şimdiki adımla kaydedilir: toparlanma aynısını üretir.
        """
        isinma = motor.strateji.isinma_bar() + ISINMA_PAYI
        bas = max(ay_basi_ms(u.ay), 0) - isinma * self._adim
        son_bilinen = motor.son_bar_zamanlari(u.semboller)
        dolan = 0
        for sembol in u.semboller:
            baslangic = max(bas, son_bilinen.get(sembol, bas - self._adim) + self._adim)
            if baslangic > bit:
                continue
            for bar in _rest_barlar(self.rest, sembol, self.timeframe, baslangic,
                                    bit + self._adim):
                dolan += motor.bar_ekle(sembol, bar)
        self._turev_guncelle(motor, u.semboller, bit, funding_bas=bas - 24 * self._adim,
                             premium_bas=bas)
        if dolan:
            motor.depo.olay_yaz("yeni_uye_gecmisi", bar_ms=bit, ayrinti={"ay": u.ay, "bar": dolan})

    def _durum_yaz(self, motor: EvrenPaperMotoru) -> None:
        s = motor.son_sonuc
        govde = {
            "kosu": self.kosu_yolu.stem,
            "adim": motor.adim_sayisi,
            "son_bar_utc": None if s is None else utc_str(s.open_time),
            "ozkaynak": None if s is None else s.ozkaynak,
            "brut_maruziyet": None if s is None else s.brut,
            "islem": len(motor.adimci.islemler),
            "pozisyonlar": list(motor.adimci.portfoy.sirali_semboller),
            "safe_mode": None if motor.backtest.risk is None
            else motor.backtest.risk.durum.safe_mode,
            "yazildi_utc": utc_str(self.saat()),
        }
        yol = self.kosu_yolu.with_suffix(self.kosu_yolu.suffix + ".durum.json")
        yol.write_text(json.dumps(govde, ensure_ascii=False, indent=1), encoding="utf-8")

    # ------------------------------------------------------------------ başlangıç

    def baslat(self) -> EvrenPaperMotoru:
        self.depo = EvrenKosuDeposu(self.kosu_yolu)
        self.depo.kimlik_yaz(self.kimlik)
        if self.depo.adimlar():
            motor = EvrenPaperMotoru.toparlan(self.depo, **self.kurulum)
            self.depo.olay_yaz("toparlandi", bar_ms=motor.son_bar_ms,
                               ayrinti={"adim": motor.adim_sayisi})
        else:
            motor = EvrenPaperMotoru(depo=self.depo, **self.kurulum)
            son = self._son_kapanmis()
            isinma = motor.strateji.isinma_bar() + ISINMA_PAYI
            bas = son - (isinma - 1) * self._adim
            self._uyelikleri_isle(motor, bas, son)
            semboller = sorted({s for ay in motor.takvim().aylar.values() for s in ay.semboller})
            if not semboller:
                raise RuntimeError(f"evren tablosunda {ay_metni(bas)}…{ay_metni(son)} için üye yok")
            for sembol in semboller:
                for bar in _rest_barlar(self.rest, sembol, self.timeframe, bas, son + self._adim):
                    motor.bar_ekle(sembol, bar)
            self._turev_guncelle(motor, semboller, son, funding_bas=bas - 24 * self._adim,
                                 premium_bas=bas)
            motor.isinma(range(bas, son + self._adim, self._adim))
            self.depo.olay_yaz("isinma", bar_ms=son,
                               ayrinti={"bar": isinma, "sembol": len(semboller)})
        risk: RiskMotoru | None = motor.backtest.risk
        isaret = kill_mod.safe_isareti(self.kosu_yolu)
        if isaret is not None and risk is not None:
            risk.kill(str(isaret.get("sebep", "süreç dışı kill")), self.saat(),
                      {"kaynak": "safemode_isareti"})
        self.motor = motor
        self._durum_yaz(motor)
        return motor

    def _turev_guncelle(self, motor: EvrenPaperMotoru, semboller: Sequence[str], t: int,
                        *, funding_bas: int | None = None, premium_bas: int | None = None) -> None:
        """`t` adımından önce: sembollerin yeni funding ödemeleri ve `t`ye kadar kapanmış
        premium barları. Bilinen son kayıttan devam eder; ilk seferde verilen başlangıçtan.

        Ağ çağrıları eşzamanlı (sembol başına iki istek), motora ekleme **sıralı** ve tek
        iş parçacığında: ekleme sırası kayda girer, deterministik kalmalı.
        """
        if not self.kurulum.get("turev") or self.turev is None:
            return
        self._turev_uygula(motor, t, self._turev_cek(motor, semboller, t, funding_bas=funding_bas,
                                                     premium_bas=premium_bas))

    def _turev_cek(self, motor: EvrenPaperMotoru, semboller: Sequence[str], t: int, *,
                   funding_bas: int | None = None, premium_bas: int | None = None) -> Any:
        """Yalnızca ağ; motoru **değiştirmez** (canlı döngüde iş parçacığında koşar, SQLite
        bağlantısı ve girdi sırası döngü iş parçacığında kalır)."""
        from concurrent.futures import ThreadPoolExecutor

        araliklar = self.turev.araliklar()
        son_f = motor.son_funding_zamanlari(semboller)
        son_p = motor.son_premium_zamanlari(semboller)
        simdi = self.saat()
        f_bas = funding_bas if funding_bas is not None else t - 24 * self._adim
        p_bas = premium_bas if premium_bas is not None else t

        def cek(sembol: str) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
            fb = son_f[sembol] + 1 if sembol in son_f else f_bas
            pb = son_p[sembol] + self._adim if sembol in son_p else p_bas
            return (self.turev.funding(sembol, fb),
                    self.turev.premium(sembol, pb, t + self._adim, simdi) if pb <= t else [])

        sirali = sorted(semboller)
        with ThreadPoolExecutor(8) as havuz:
            sonuclar = list(havuz.map(cek, sirali))
        return araliklar, son_p, sirali, sonuclar

    def _turev_uygula(self, motor: EvrenPaperMotoru, t: int, cekilen: Any) -> None:
        araliklar, son_p, sirali, sonuclar = cekilen
        yeni_f = yeni_p = 0
        for sembol, (fundingler, premiumlar) in zip(sirali, sonuclar, strict=True):
            aralik = araliklar.get(sembol, 8)
            for calc_time, oran in sorted(fundingler):
                yeni_f += motor.funding_ekle(sembol, calc_time, aralik, oran)
            for open_time, close in sorted(premiumlar):
                yeni_p += motor.premium_ekle(sembol, open_time, close)
        eksik_p = [s_ for s_ in sirali if motor.son_premium_zamanlari([s_]).get(s_, -1) < t
                   and s_ in son_p]
        if eksik_p:
            motor.depo.olay_yaz("premium_eksik", bar_ms=t, ayrinti={"semboller": eksik_p[:20],
                                                                   "sayi": len(eksik_p)})

    def bosluk_tamamla(self, motor: EvrenPaperMotoru) -> int:
        """Son işlenen bardan son kapanmış bara kadar eksik barları REST'ten ekler ve işler."""
        son = self._son_kapanmis()
        if motor.son_bar_ms is None or motor.son_bar_ms >= son:
            return 0
        self._uyelikleri_isle(motor, motor.son_bar_ms + self._adim, son)
        islenen = 0
        t = motor.son_bar_ms + self._adim
        while t <= son:
            for sembol in motor.beklenen_semboller(t):
                for bar in _rest_barlar(self.rest, sembol, self.timeframe, t, t + self._adim):
                    motor.bar_ekle(sembol, bar)
            self._turev_guncelle(motor, motor.beklenen_semboller(t), t)
            motor.adim(t)
            islenen += 1
            t += self._adim
        if islenen:
            motor.depo.olay_yaz("bosluk_tamamlandi", bar_ms=son, ayrinti={"bar": islenen})
        return islenen

    # ------------------------------------------------------------------ döngü

    def durdur(self) -> None:
        self._durdur = True

    async def calistir(self, *, uyku: Callable[[float], Any] = asyncio.sleep,
                       azami_adim: int | None = None) -> None:
        motor = self.motor or self.baslat()
        self.bosluk_tamamla(motor)
        baslangic_adim = motor.adim_sayisi
        while not self._durdur:
            semboller = motor.beklenen_semboller(motor.son_bar_ms + self._adim)
            son_teslim = motor.son_bar_zamanlari(semboller)
            akis = self.akis_fabrikasi(semboller, son_teslim)
            toplayici = IzgaraToplayici(self.timeframe, beklenen=motor.beklenen_semboller,
                                        bekleme_ms=self.bekleme_ms, son_teslim=motor.son_bar_ms)
            yeniden_kur = asyncio.Event()

            async def tuket(akis: Any = akis, toplayici: IzgaraToplayici = toplayici) -> None:
                async for sembol, bar in akis.barlar():
                    motor.bar_ekle(sembol, bar)
                    gec = toplayici.bar_ekle(sembol, bar)
                    if gec is not None:
                        motor.depo.olay_yaz("gec_bar", bar_ms=bar.open_time,
                                            ayrinti={"sembol": sembol,
                                                     "teslim_edilen": gec.teslim_edilen})

            gorev = asyncio.create_task(tuket())
            try:
                while not self._durdur and not yeniden_kur.is_set():
                    if gorev.done():
                        gorev.result()  # akış hatası yukarı çıksın
                        break
                    for ib in toplayici.hazir(self.saat()):
                        self._uyelikleri_isle(motor, ib.open_time, ib.open_time)
                        if self.kurulum.get("turev") and self.turev is not None:
                            cekilen = await asyncio.to_thread(
                                self._turev_cek, motor,
                                motor.beklenen_semboller(ib.open_time), ib.open_time)
                            self._turev_uygula(motor, ib.open_time, cekilen)
                        sonuc = motor.adim(ib.open_time, eksik=ib.eksik)
                        self._durum_yaz(motor)
                        self.gunluk(f"{utc_str(ib.open_time)} özkaynak {sonuc.ozkaynak:,.2f} "
                                    f"brüt {sonuc.brut:.3f} eksik {len(ib.eksik)}")
                        sonraki = set(motor.beklenen_semboller(ib.open_time + self._adim))
                        if sonraki != set(semboller):
                            motor.depo.olay_yaz("abonelik_degisti", bar_ms=ib.open_time)
                            yeniden_kur.set()
                        islenen = motor.adim_sayisi - baslangic_adim
                        if azami_adim is not None and islenen >= azami_adim:
                            self._durdur = True
                    if durdurma_mod.istek(self.kosu_yolu) is not None:
                        self._durdur = True
                    await uyku(YOKLAMA_S)
            finally:
                akis.kapat()
                gorev.cancel()
                with suppress(BaseException):
                    await gorev
                temizle = getattr(akis, "temizle", None)
                if temizle is not None:
                    with suppress(Exception):
                        await temizle()


async def kos(kosucu: EvrenKosucu, **kw: Any) -> None:
    """Kilit + pid + durdurma bayrağı ile sarılmış çalıştırma."""
    kilit = KosuKilidi(kosucu.kosu_yolu).al()
    try:
        kill_mod.pid_yaz(kosucu.kosu_yolu)
        durdurma_mod.temizle(kosucu.kosu_yolu)
        try:
            await kosucu.calistir(**kw)
            if kosucu.depo is not None:
                istek = durdurma_mod.istek(kosucu.kosu_yolu)
                kosucu.depo.olay_yaz("durdu", bar_ms=kosucu.motor.son_bar_ms if kosucu.motor
                                     else None, ayrinti={"sebep": (istek or {}).get("sebep")})
        except Exception as hata:
            if kosucu.depo is not None:
                kosucu.depo.olay_yaz("hata", ayrinti={"hata": f"{type(hata).__name__}: {hata}"})
            raise
    finally:
        durdurma_mod.temizle(kosucu.kosu_yolu)
        kill_mod.pid_sil(kosucu.kosu_yolu)
        if kosucu.depo is not None:
            kosucu.depo.kapat()
        kilit.kapat()


__all__ = ["AkisFabrikasi", "EvrenKosucu", "EvrenTablosu", "KlineKaynagi", "kos"]

