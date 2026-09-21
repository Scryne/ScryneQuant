"""Evren paper motoru: çok enstrümanlı stratejiyi canlı ızgara barlarıyla çalıştırır. (Faz 14)

Tasarım `docs/Faz-14-Coklu-Paper-Tasarim.md`. Üç ilke:

1. **Tek kod yolu (K-001).** Bar işleme `backtest/coklu_motor.CokluAdimci.adim`: backtest'in
   döngüsündeki adımın **kendisi**. Görünüm her adımda o ana kadar bilinen barlardan kurulur;
   kalite bayrakları sembol başına `BarPenceresi` (tek sembollü paper ile aynı doğrulama),
   ızgaraya hizalama `data/izgara.hizala`, üyelik `live/canli_evren.UyelikTakvimi` ∧ bar var.
2. **Büyüyen görünüm.** Stratejiler dengeleme takvimini `ctx.uzunluk`la sayıyor; kayan pencere
   o sayıyı sabitlerdi. Görünüm koşunun başından (ısınma dahil) bütün barları taşır.
3. **Girdi saklanır, durum yeniden üretilir (K-038).** Her bar ve üye listesi *hangi adımdan
   önce bilindiğiyle* depoya yazılır. Toparlanma bütün adımları aynı bilgiyle yeniden oynatır
   ve her adımın özkaynak/maruziyetini kayıtla **bit düzeyinde** karşılaştırır; ayrışmada durur.

Gözlem modunda gerçek emir yok; fill'ler `CokluAdimci`nın simülasyonu. Risk motoru zorunlu
(değişmez kural 3); audit defteri yeniden oynatma bittikten **sonra** bağlanır, yoksa aynı
kararlar her toparlanmada yeniden yazılırdı.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from scryne_quant.backtest.coklu_motor import CokluAdimci, CokluBacktest
from scryne_quant.common.maliyet import Maliyetler, MaliyetModeli
from scryne_quant.common.zaman import timeframe_ms, utc_str
from scryne_quant.data import funding as funding_mod
from scryne_quant.data import makro as makro_mod
from scryne_quant.data.izgara import hizala, uyeligi_barlara_kis
from scryne_quant.live.akis import Bar
from scryne_quant.live.canli_evren import AyUyeligi, UyelikTakvimi
from scryne_quant.live.evren_depo import EvrenKosuDeposu, KayitliAdim
from scryne_quant.live.pencere import BarPenceresi
from scryne_quant.risk.motor import RiskMotoru
from scryne_quant.strategy.kosu import evren_gorunum_kur
from scryne_quant.strategy.temel import PortfoyStratejisi


class EvrenMotorHatasi(RuntimeError):
    """Evren motoru sözleşmesi ihlal edildi."""


class EvrenToparlanmaAyrismasi(EvrenMotorHatasi):
    """Yeniden oynatılan adım kayıtlı sonuçtan farklı çıktı. Koşu durur, tahmin yürütülmez."""


@dataclass
class _Girdiler:
    barlar: dict[str, dict[int, tuple[Bar, int]]] = field(default_factory=dict)
    uyelik: list[tuple[AyUyeligi, int]] = field(default_factory=list)
    # sembol → calc_time → (aralık saat, oran, bilindi adım)
    funding: dict[str, dict[int, tuple[int, float, int]]] = field(default_factory=dict)
    # sembol → open_time → (basis close, bilindi adım)
    premium: dict[str, dict[int, tuple[float, int]]] = field(default_factory=dict)
    # seri → gün → [(değer, bilindi adım), ...] bilindi sırasıyla (revizyon olabilir)
    makro: dict[str, dict[int, list[tuple[float, int]]]] = field(default_factory=dict)


class EvrenPaperMotoru:
    def __init__(
        self,
        *,
        strateji: PortfoyStratejisi,
        maliyet: MaliyetModeli,
        baslangic_sermaye: float,
        risk: RiskMotoru | None,
        depo: EvrenKosuDeposu | None,
        timeframe: str = "1h",
        sifira_yaz_bar: int | None = 48,
        turev: bool = False,
        makro: tuple[str, ...] = (),
        maliyetler: Maliyetler | None = None,
    ) -> None:
        self.timeframe = timeframe
        self.makro = tuple(makro)
        """Makro PIT alanları kurulacak seriler (kısa ad, `data/makro.SERILER`)."""
        self.turev = turev
        """Funding + basis dizileri görünüme eklenir (Aşama F; `research/evren_kosu.veri_kur`
        ile aynı fonksiyonlar: `funding_mod.evren_dizileri`, `evren_premium_dizisi`)."""
        self.backtest = CokluBacktest(
            strateji, maliyet, baslangic_sermaye=baslangic_sermaye, risk=risk,
            sifira_yaz_bar=sifira_yaz_bar, maliyetler=maliyetler,
        )
        self.adimci = CokluAdimci(self.backtest)
        self.depo = depo
        self._g = _Girdiler()
        self._izgara: list[int] = []
        self._adim = timeframe_ms(timeframe)
        self.son_sonuc: KayitliAdim | None = None
        # Sembol başına doğrulanmış diziler: (görünen barların açılış zamanları, diziler).
        self._dogrulanmis: dict[str, tuple[list[int], dict[str, np.ndarray]]] = {}
        self.dogrulama_onbellegi = True

    # ------------------------------------------------------------------ ölçüm

    @property
    def strateji(self) -> PortfoyStratejisi:
        return self.backtest.strateji

    @property
    def adim_sayisi(self) -> int:
        return len(self._izgara)

    @property
    def son_bar_ms(self) -> int | None:
        return self._izgara[-1] if self._izgara else None

    def takvim(self, adim: int | None = None) -> UyelikTakvimi:
        """`adim` işlenmeden önce bilinen üye listeleri."""
        sinir = self.adim_sayisi if adim is None else adim
        tk = UyelikTakvimi()
        for uyelik, bilindi in self._g.uyelik:
            if bilindi <= sinir:
                tk.ekle(uyelik)
        return tk

    def son_bar_zamanlari(self, semboller: Iterable[str]) -> dict[str, int]:
        """Sembol başına bilinen son barın açılışı (akışın tekrar süzme sınırı)."""
        return {s: max(self._g.barlar[s]) for s in semboller if self._g.barlar.get(s)}

    def beklenen_semboller(self, t_ms: int) -> tuple[str, ...]:
        """`t` barında beklenen semboller: o anki üyeler ∪ açık pozisyonlar."""
        uyeler = set(self.takvim().uyeler(t_ms)[0])
        return tuple(sorted(uyeler | set(self.adimci.portfoy.sirali_semboller)))

    # ------------------------------------------------------------------ girdi

    def bar_ekle(self, sembol: str, bar: Bar, *, kaydet: bool = True,
                 bilindi_adim: int | None = None) -> bool:
        if not bar.hizali_mi(self.timeframe):
            raise EvrenMotorHatasi(f"{sembol}: hizasız bar {bar.open_time}")
        adim = self.adim_sayisi if bilindi_adim is None else bilindi_adim
        seri = self._g.barlar.setdefault(sembol, {})
        if bar.open_time in seri:
            return False
        seri[bar.open_time] = (bar, adim)
        if kaydet and self.depo is not None:
            self.depo.bar_yaz(sembol, bar, adim)
        return True

    def funding_ekle(self, sembol: str, calc_time: int, aralik_saat: int, oran: float, *,
                     kaydet: bool = True, bilindi_adim: int | None = None) -> bool:
        adim = self.adim_sayisi if bilindi_adim is None else bilindi_adim
        seri = self._g.funding.setdefault(sembol, {})
        if calc_time in seri:
            return False
        seri[calc_time] = (int(aralik_saat), float(oran), adim)
        if kaydet and self.depo is not None:
            self.depo.funding_yaz(sembol, calc_time, int(aralik_saat), float(oran), adim)
        return True

    def premium_ekle(self, sembol: str, open_time: int, close: float, *, kaydet: bool = True,
                     bilindi_adim: int | None = None) -> bool:
        adim = self.adim_sayisi if bilindi_adim is None else bilindi_adim
        seri = self._g.premium.setdefault(sembol, {})
        if open_time in seri:
            return False
        seri[open_time] = (float(close), adim)
        if kaydet and self.depo is not None:
            self.depo.premium_yaz(sembol, open_time, float(close), adim)
        return True

    def son_funding_zamanlari(self, semboller: Iterable[str]) -> dict[str, int]:
        return {s: max(self._g.funding[s]) for s in semboller if self._g.funding.get(s)}

    def son_premium_zamanlari(self, semboller: Iterable[str]) -> dict[str, int]:
        return {s: max(self._g.premium[s]) for s in semboller if self._g.premium.get(s)}

    def uyelik_ekle(self, uyelik: AyUyeligi, *, kaydet: bool = True,
                    bilindi_adim: int | None = None) -> bool:
        adim = self.adim_sayisi if bilindi_adim is None else bilindi_adim
        for mevcut, _ in self._g.uyelik:
            if mevcut.ay == uyelik.ay:
                if mevcut.semboller != uyelik.semboller:
                    raise EvrenMotorHatasi(f"{uyelik.ay} için farklı üye listesi zaten var")
                return False
        self._g.uyelik.append((uyelik, adim))
        if kaydet and self.depo is not None:
            self.depo.uyelik_yaz(uyelik.ay, uyelik.semboller, uyelik.tablo_hash, adim)
        return True

    # ------------------------------------------------------------------ adım

    def _gorunum_girdisi(self, t_ms: int, *, izgara_listesi: list[int] | None = None) -> Any:
        k = self.adim_sayisi
        izgara = np.asarray(
            izgara_listesi if izgara_listesi is not None else [*self._izgara, t_ms], dtype="int64"
        )
        izgara_kumesi = set(izgara.tolist())
        diziler: dict[str, dict[str, np.ndarray]] = {}
        for sembol in sorted(self._g.barlar):
            barlar = sorted(
                (b for ot, (b, bilindi) in self._g.barlar[sembol].items()
                 if bilindi <= k and ot <= t_ms and ot in izgara_kumesi),
                key=lambda b: b.open_time,
            )
            if not barlar:
                continue
            diziler[sembol] = hizala(pd.DataFrame(self._dogrulanmis_diziler(sembol, barlar)),
                                     izgara)
            if self.turev:
                diziler[sembol].update(self._turev_dizileri(sembol, k, izgara))
        if not diziler:
            raise EvrenMotorHatasi(f"{utc_str(t_ms)}: hiçbir sembolün barı yok")
        if self.makro:
            alanlar = makro_mod.gunlukten_alanlar(
                izgara, {kisa: self._makro_kaynagi(kisa, k) for kisa in self.makro})
            for dz in diziler.values():
                dz.update(alanlar)
        uyelik, _ = uyeligi_barlara_kis(self.takvim(k).dizileri(izgara, diziler), diziler)
        gorunum = evren_gorunum_kur(self.timeframe, diziler, uyelik, self.strateji)
        return self.backtest.girdi_kur(gorunum)

    def _makro_kaynagi(self, kisa: str, k: int) -> Any:
        seri = self._g.makro.get(kisa, {})

        def kaynak(gunler: np.ndarray) -> np.ndarray:
            out = np.full(len(gunler), np.nan)
            for i, g in enumerate(gunler.tolist()):
                bilinen = [d for d, b in seri.get(g, ()) if b <= k]
                if bilinen:
                    out[i] = bilinen[-1]
            return out

        return kaynak

    def makro_ekle(self, seri: str, gun: int, deger: float, *, kaydet: bool = True,
                   bilindi_adim: int | None = None) -> bool:
        """Bir günün PIT değeri. Aynı gün aynı değerle tekrar gelirse eklenmez; farklı
        değerle gelirse revizyon olarak eklenir (görünüm o adımdan sonra yenisini kullanır)."""
        adim = self.adim_sayisi if bilindi_adim is None else bilindi_adim
        kayitlar = self._g.makro.setdefault(seri, {}).setdefault(int(gun), [])
        deger = float(deger)
        if kayitlar and repr(kayitlar[-1][0]) == repr(deger):
            return False
        kayitlar.append((deger, adim))
        if kaydet and self.depo is not None:
            self.depo.makro_yaz(seri, int(gun), deger, adim)
        return True

    def son_makro_gunu(self, seri: str) -> int | None:
        gunler = self._g.makro.get(seri)
        return max(gunler) if gunler else None

    def _turev_dizileri(self, sembol: str, k: int, izgara: np.ndarray) -> dict[str, np.ndarray]:
        """`k` adımından önce bilinen funding ve premium kayıtlarından, araştırmayla aynı yol."""
        f = [(t, a, o) for t, (a, o, b) in self._g.funding.get(sembol, {}).items() if b <= k]
        fdf = (pd.DataFrame(f, columns=["calc_time", "funding_interval_hours",
                                        "last_funding_rate"]).astype(
            {"calc_time": "int64", "funding_interval_hours": "int64",
             "last_funding_rate": "float64"})
               if f else pd.DataFrame())
        cikti = funding_mod.evren_dizileri(izgara, fdf)
        pr = sorted((t, c) for t, (c, b) in self._g.premium.get(sembol, {}).items() if b <= k)
        pdf = (pd.DataFrame(pr, columns=["open_time", "close"]).astype(
            {"open_time": "int64", "close": "float64"}) if pr else pd.DataFrame())
        cikti["basis"] = funding_mod.evren_premium_dizisi(izgara, pdf)
        return cikti

    def _dogrulanmis_diziler(self, sembol: str, barlar: list[Bar]) -> dict[str, np.ndarray]:
        """`BarPenceresi` doğrulaması, önceki adımın sonucu üzerine **artımlı**.

        Neden eşit: `dogrula`nın her bayrağı yalnızca barın kendisine ve sıradaki **bir
        önceki** bara bakar (boşluk, aşırı hareket; tekrar yok çünkü motor aynı açılışı iki
        kez almaz), `BACKFILL` düzeltmesi bar başınadır. Görünen barlar önceki listenin
        **uzantısıysa** eski bayraklar değişmez; yeni barlar bir önceki bar bağlamıyla
        doğrulanır. Liste uzantı değilse (geç bar ortaya girdi) tamamı yeniden doğrulanır.
        Bit düzeyinde eşitlik testle korunur (`test_dogrulama_onbellegi_bit_esit`).
        Olmasaydı her adım bütün geçmişi yeniden doğrulardı: toparlanma O(N²), ölçüldü
        770 barda 0,32 s/adım, sürenin %69'u doğrulama.
        """
        zamanlar = [b.open_time for b in barlar]
        onceki = self._dogrulanmis.get(sembol) if self.dogrulama_onbellegi else None
        if onceki is not None and 0 < len(onceki[0]) <= len(zamanlar) and (
            zamanlar[: len(onceki[0])] == onceki[0]
        ):
            n = len(onceki[0])
            if n == len(zamanlar):
                return onceki[1]
            pencere = BarPenceresi(sembol, self.timeframe, kapasite=len(zamanlar) - n + 1)
            pencere.doldur(barlar[n - 1:])
            ek = pencere.diziler()
            sonuc = {k: np.concatenate([onceki[1][k], ek[k][1:]]) for k in onceki[1]}
            for dizi in sonuc.values():
                dizi.flags.writeable = False
        else:
            pencere = BarPenceresi(sembol, self.timeframe, kapasite=max(2, len(barlar)))
            pencere.doldur(barlar)
            sonuc = pencere.diziler()
        if self.dogrulama_onbellegi:
            self._dogrulanmis[sembol] = (zamanlar, sonuc)
        return sonuc

    def isinma(self, zamanlar: Iterable[int], *, kaydet: bool = True) -> list[KayitliAdim]:
        """Isınma barlarını **toplu** işler: tek görünüm, adımlar sırayla, hepsi `isinma`.

        Neden toplu: bir adımın görünümü yalnızca o ana kadarki barlardan kurulsaydı ilk
        adımda tek bar olurdu ve göstergeler (ATR, 720 barlık hacim ortalaması) hesaplanamazdı.
        Backtest de ısınmayı aynı şekilde işler: tüm seri tek görünüm, `ctx` `t`de kesik
        (K-002), ısınma hedefleri emir üretmez. Isınma yalnızca koşunun başında ve bir kez.
        """
        zamanlar = [int(t) for t in zamanlar]
        if self._izgara:
            raise EvrenMotorHatasi("ısınma yalnızca koşunun başında yapılır")
        if not zamanlar:
            raise EvrenMotorHatasi("boş ısınma")
        if any(b - a != self._adim for a, b in zip(zamanlar, zamanlar[1:], strict=False)) or (
            zamanlar[0] % self._adim
        ):
            raise EvrenMotorHatasi("ısınma ızgarası ardışık ve hizalı olmalı")
        girdi = self._gorunum_girdisi(zamanlar[-1], izgara_listesi=zamanlar)
        sonuclar = []
        for i, t in enumerate(zamanlar):
            ozkaynak, brut = self.adimci.adim(girdi, i, isinma=True, son_bar=False)
            sonuc = KayitliAdim(i, t, True, (), float(ozkaynak), float(brut),
                                len(self.adimci.islemler))
            self._izgara.append(t)
            sonuclar.append(sonuc)
            if kaydet and self.depo is not None:
                self.depo.adim_yaz(sonuc)
        self.son_sonuc = sonuclar[-1]
        return sonuclar

    def adim(self, t_ms: int, *, isinma: bool = False, eksik: Iterable[str] = (),
             kaydet: bool = True) -> KayitliAdim:
        """Bir canlı ızgara barını işler. Önce `isinma` yapılmış olmalı; `t` son işlenen
        bardan tam bir adım sonra olmalı."""
        if not self._izgara:
            raise EvrenMotorHatasi("ilk canlı adımdan önce ısınma gerekir (`isinma`)")
        if t_ms % self._adim != 0:
            raise EvrenMotorHatasi(f"hizasız ızgara barı {t_ms}")
        if self._izgara and t_ms != self._izgara[-1] + self._adim:
            raise EvrenMotorHatasi(
                f"ızgara sırası bozuldu: son {utc_str(self._izgara[-1])}, gelen {utc_str(t_ms)}"
            )
        girdi = self._gorunum_girdisi(t_ms)
        i = len(self._izgara)
        ozkaynak, brut = self.adimci.adim(girdi, i, isinma=isinma, son_bar=False)
        sonuc = KayitliAdim(i, t_ms, isinma, tuple(sorted(eksik)), float(ozkaynak),
                            float(brut), len(self.adimci.islemler))
        self._izgara.append(t_ms)
        self.son_sonuc = sonuc
        if kaydet and self.depo is not None:
            self.depo.adim_yaz(sonuc)
        return sonuc

    # ------------------------------------------------------------------ toparlanma

    @classmethod
    def toparlan(cls, depo: EvrenKosuDeposu, **kurulum: Any) -> EvrenPaperMotoru:
        """Depodaki girdilerle bütün adımları yeniden oynatır ve kayıtla karşılaştırır.

        `kurulum`: `__init__`in `depo` dışındaki argümanları; koşu kimliğiyle uyumu çağıran
        doğrular (`EvrenKosuDeposu.kimlik_yaz`).
        """
        motor = cls(depo=depo, **kurulum)
        risk = motor.backtest.risk
        defter = None
        if risk is not None:
            defter, risk.defter = risk.defter, None  # yeniden oynatma audit'e yazmaz
        barlar: dict[int, list[tuple[str, Bar]]] = {}
        for kb in depo.barlar():
            barlar.setdefault(kb.bilindi_adim, []).append((kb.sembol, kb.bar))
        fundingler: dict[int, list[tuple[str, int, int, float]]] = {}
        for sembol, t, a, o, bilindi in depo.fundingler():
            fundingler.setdefault(bilindi, []).append((sembol, t, a, o))
        premiumlar: dict[int, list[tuple[str, int, float]]] = {}
        for sembol, t, c, bilindi in depo.premiumlar():
            premiumlar.setdefault(bilindi, []).append((sembol, t, c))
        makrolar: dict[int, list[tuple[str, int, float]]] = {}
        for seri, g, d, bilindi in depo.makrolar():
            makrolar.setdefault(bilindi, []).append((seri, g, d))
        uyelikler: dict[int, list[AyUyeligi]] = {}
        for ay, semboller, h, bilindi in depo.uyelikler():
            uyelikler.setdefault(bilindi, []).append(AyUyeligi(ay, semboller, h))

        def yukle(adim: int) -> None:
            for sembol, bar in barlar.get(adim, []):
                motor.bar_ekle(sembol, bar, kaydet=False, bilindi_adim=adim)
            for u in uyelikler.get(adim, []):
                motor.uyelik_ekle(u, kaydet=False, bilindi_adim=adim)
            for sembol, t, a, o in fundingler.get(adim, []):
                motor.funding_ekle(sembol, t, a, o, kaydet=False, bilindi_adim=adim)
            for sembol, t, c in premiumlar.get(adim, []):
                motor.premium_ekle(sembol, t, c, kaydet=False, bilindi_adim=adim)
            for seri, g, d in makrolar.get(adim, []):
                motor.makro_ekle(seri, g, d, kaydet=False, bilindi_adim=adim)

        kayitli = depo.adimlar()
        isinma_sayisi = 0
        while isinma_sayisi < len(kayitli) and kayitli[isinma_sayisi].isinma:
            isinma_sayisi += 1
        yeniden: list[KayitliAdim] = []
        if isinma_sayisi:
            yukle(0)
            yeniden = motor.isinma([a.open_time for a in kayitli[:isinma_sayisi]], kaydet=False)
        for beklenen in kayitli:
            if beklenen.adim < isinma_sayisi:
                yeni = yeniden[beklenen.adim]
            else:
                yukle(beklenen.adim)
                yeni = motor.adim(beklenen.open_time, eksik=beklenen.eksik, kaydet=False)
            if (repr(yeni.ozkaynak), repr(yeni.brut), yeni.islem) != (
                repr(beklenen.ozkaynak), repr(beklenen.brut), beklenen.islem
            ):
                raise EvrenToparlanmaAyrismasi(
                    f"adım {beklenen.adim} ({utc_str(beklenen.open_time)}): yeniden üretilen "
                    f"özkaynak {yeni.ozkaynak!r} / brüt {yeni.brut!r} / işlem {yeni.islem}, "
                    f"kayıtlı {beklenen.ozkaynak!r} / {beklenen.brut!r} / {beklenen.islem}"
                )
        yukle(len(kayitli))
        if risk is not None:
            risk.defter = defter
        return motor


__all__ = ["EvrenMotorHatasi", "EvrenPaperMotoru", "EvrenToparlanmaAyrismasi"]
