"""Tarihsel bar indirici: sayfalama, kaldığı yerden devam, doğrulama, depoya yazma.

Faz 1'in bitti kriterlerinden ikisi bu dosyada kanıtlanır:

1. **Aynı komut iki kez → dosya bit düzeyinde aynı.** Üç şey birden gerekiyor: adaptör
   kapanmamış barı atıyor (K-015/1), depo kanonik yazıyor (K-011), ve **bayrak tam
   seriden hesaplanıyor** — indirmenin kaç parçaya bölündüğünden bağımsız.
2. **Kaldığı yerden devam.** İstenen aralıktan elde olanlar çıkarılır, yalnızca eksik
   parçalar indirilir.

**Neden bayrak tam seriden hesaplanıyor:** `gap` bayrağı bir barın kendi içeriğine değil,
**öncekiyle** arasındaki mesafeye bakar. Sayfa sayfa doğrulanırsa her sayfanın ilk barı
kendinden önceki bara ulaşamaz; 137 barlık parçalarla inen veri, 1000'lik parçalarla
inenden farklı bayraklanır — ve dosya hash'i indirmenin şekline bağlı hale gelir. Bu
yüzden akış şöyle: ham indir → depodaki ham veriyle birleştir → **tümünü** doğrula → yaz.

**Boşluklara dair:** eksik aralıklar her çalıştırmada yeniden denenir. Binance'in veri
başlangıcından önceki bir aralık istenirse bu çağrı başına bir boş yanıt maliyeti
getirir — ve karşılığında, borsa sonradan bir boşluğu doldurduğunda veri setinin kendi
kendine iyileşmesini sağlar. Ölçülen maliyet (Spike 1: klines çağrısı = 2 weight,
limit 6.000/dk) bu takası tartışmaya değmeyecek kadar ucuz kılıyor.

**Veri sonu sabitlenebilir (`bitis_gun`, K-080).** Arşiv indiricisiyle aynı sözleşme: depo bir
tarihe **çekilebilir**; o günden sonraki barlar indirilmez, depoda varsa **atılır**. Sebep
ölçüldü (2026-09-20): veri seti kimliği dosyanın SHA-256'sı, OOS penceresi veri sonuna
göreli; `data/market/BTCUSDT/1h.parquet` on gün uzatılınca 16 deney kaydının 10'u "veri seti
değişmiş" ile yeniden üretilemez oldu. Geri sarım aynı barları aynı deterministik yazıcıyla
yazar: bugünkü depo 2026-09-09 10:00 UTC'ye kırpıldığında kayıtlardaki `e3adb02c…` hash'i
**bayt düzeyinde** geri geldi (45.576 bar). Uzatmak da geri sarmak da aynı komut; sabitlenen
tarih deney kaydında (`kimlik.veri_son_ms`) durur.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from scryne_quant.common.zaman import bar_acilisi, timeframe_ms, utc_str
from scryne_quant.data.depo import DepoKaydi, ParquetDepo
from scryne_quant.data.dogrulama import KaliteRaporu, dogrula
from scryne_quant.data.semalar import HAM_BAR_SUTUNLARI
from scryne_quant.exchange.temel import BorsaAdaptoru, BorsaHatasi

#: Tek bir eksik aralık için azami sayfa. 1000 bar/sayfa ile 5 milyon bar — 1m'de 9 yıl.
#: Sonsuz döngüye karşı emniyet kemeri: imleç ilerlemezse döngü zaten kırılır, bu sınır
#: yalnızca hiç beklenmeyen bir adaptör davranışına karşı.
AZAMI_SAYFA = 5_000


class IndirmeHatasi(Exception):
    """İndirme sözleşmesinin ihlali."""


@dataclass(frozen=True, slots=True)
class Aralik:
    """`[baslangic_ms, bitis_ms)` — bitiş **dışlayıcı**, her yerde olduğu gibi."""

    baslangic_ms: int
    bitis_ms: int

    def bar_sayisi(self, timeframe: str) -> int:
        return max(0, (self.bitis_ms - self.baslangic_ms) // timeframe_ms(timeframe))

    def __str__(self) -> str:
        return f"{utc_str(self.baslangic_ms)} → {utc_str(self.bitis_ms)}"


@dataclass(frozen=True, slots=True)
class IndirmeSonucu:
    """Bir indirmenin tam kaydı. CLI çıktısı ve rapor dosyası bundan üretilir."""

    sembol: str
    timeframe: str
    aralik: Aralik
    eksik_araliklar: tuple[Aralik, ...]
    inen_bar: int
    cagri_sayisi: int
    sure_s: float
    depo: DepoKaydi
    kalite: KaliteRaporu
    onceki_sha256: str | None

    @property
    def degisti(self) -> bool:
        """Dosya bu çalıştırmada değişti mi? İdempotency'nin gözle görülür yüzü."""
        return self.onceki_sha256 != self.depo.sha256

    def sozluk(self) -> dict[str, Any]:
        return {
            "sembol": self.sembol,
            "timeframe": self.timeframe,
            "istenen_aralik": {
                "baslangic_ms": self.aralik.baslangic_ms,
                "bitis_ms": self.aralik.bitis_ms,
                "baslangic": utc_str(self.aralik.baslangic_ms),
                "bitis": utc_str(self.aralik.bitis_ms),
            },
            "indirilen_aralik_sayisi": len(self.eksik_araliklar),
            "inen_bar": self.inen_bar,
            "cagri_sayisi": self.cagri_sayisi,
            "sure_s": round(self.sure_s, 2),
            "dosya": str(self.depo.yol),
            "sha256": self.depo.sha256,
            "onceki_sha256": self.onceki_sha256,
            "degisti": self.degisti,
            "bayt": self.depo.bayt,
            "toplam_bar": self.depo.bar_sayisi,
            "kalite": self.kalite.sozluk(),
        }


class TarihselIndirici:
    """Borsadan tarihsel bar indirip depoya yazar."""

    def __init__(
        self, adaptor: BorsaAdaptoru, depo: ParquetDepo, *, bitis_gun: str | None = None
    ) -> None:
        self.adaptor = adaptor
        self.depo = depo
        if bitis_gun is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", bitis_gun):
            raise IndirmeHatasi(f"bitis_gun YYYY-MM-DD olmalı: {bitis_gun!r}")
        self.bitis_gun = bitis_gun

    @property
    def bitis_ms(self) -> int | None:
        """`bitis_gun`ün **ertesi** gününün UTC 00:00'ı; bar `open_time < bitis_ms` ise kalır."""
        if self.bitis_gun is None:
            return None
        gun = pd.Timestamp(self.bitis_gun, tz="UTC") + pd.Timedelta(days=1)
        return int(gun.value // 1_000_000)

    # ------------------------------------------------------------- aralık

    def son_kapali_bar_sonu(self, timeframe: str) -> int:
        """İndirmenin varsayılan **dışlayıcı** bitişi: içinde bulunduğumuz barın açılışı.

        Bu değerin ötesindeki tek bar hâlâ açık olandır ve zaten yazılmaz. Bitişi buraya
        sabitlemek, aynı bar içinde iki kez çalıştırılan komutun **aynı aralığı** istemesini
        garanti eder — idempotency'nin gözlemlenebilir olması bunu gerektiriyor.
        """
        return bar_acilisi(self.adaptor.sunucu_zamani_ms(), timeframe)

    def eksik_araliklar(
        self, sembol: str, timeframe: str, aralik: Aralik
    ) -> tuple[Aralik, ...]:
        """İstenen aralığın depoda **olmayan** parçaları.

        "Kaldığı yerden devam" özel bir mod değil, bunun bir sonucu: depoda 2020-2025
        varsa ve 2020-2026 isteniyorsa geriye tek bir eksik aralık kalır.
        """
        adim = timeframe_ms(timeframe)
        if aralik.bitis_ms <= aralik.baslangic_ms:
            return ()
        if not self.depo.var_mi(sembol, timeframe):
            return (aralik,)

        mevcut = self.depo.oku(sembol, timeframe)["open_time"].to_numpy(dtype="int64")
        mevcut = mevcut[(mevcut >= aralik.baslangic_ms) & (mevcut < aralik.bitis_ms)]
        if mevcut.size == 0:
            return (aralik,)

        parcalar: list[Aralik] = []
        if mevcut[0] > aralik.baslangic_ms:
            parcalar.append(Aralik(aralik.baslangic_ms, int(mevcut[0])))

        # İç boşluklar: ardışık iki timestamp arasında bir adımdan fazla mesafe.
        fark = np.diff(mevcut)
        for i in np.flatnonzero(fark > adim):
            parcalar.append(Aralik(int(mevcut[i] + adim), int(mevcut[i + 1])))

        son_uc = int(mevcut[-1]) + adim
        if son_uc < aralik.bitis_ms:
            parcalar.append(Aralik(son_uc, aralik.bitis_ms))

        return tuple(parcalar)

    # ------------------------------------------------------------ indirme

    def _sayfala(
        self,
        sembol: str,
        timeframe: str,
        aralik: Aralik,
        ilerleme: Callable[[int, int], None] | None,
    ) -> tuple[list[pd.DataFrame], int]:
        """Bir aralığı sayfalayarak indirir. Döner: (sayfalar, çağrı sayısı).

        Döngü **boş yanıtta** biter, "kısa sayfa geldi" diye değil: kısa sayfa bir veri
        boşluğunun ardından da gelebilir, ve orada durmak boşluğun ötesindeki veriyi
        sessizce atlamak olurdu.
        """
        adim = timeframe_ms(timeframe)
        sayfalar: list[pd.DataFrame] = []
        cagri = 0
        imlec = aralik.baslangic_ms

        while imlec < aralik.bitis_ms:
            if cagri >= AZAMI_SAYFA:
                raise IndirmeHatasi(
                    f"{sembol} {timeframe}: {AZAMI_SAYFA} sayfa sınırı aşıldı ({aralik})"
                )
            try:
                sayfa = self.adaptor.klines(sembol, timeframe, imlec, aralik.bitis_ms)
            except BorsaHatasi as hata:
                raise IndirmeHatasi(
                    f"{sembol} {timeframe} {utc_str(imlec)} indirilemedi: {hata}"
                ) from hata
            cagri += 1
            if sayfa.empty:
                break

            sayfalar.append(sayfa)
            son = int(sayfa["open_time"].iloc[-1])
            if son + adim <= imlec:  # imleç ilerlemiyor: adaptör sözleşmesi ihlali
                raise IndirmeHatasi(
                    f"{sembol} {timeframe}: imleç ilerlemedi ({utc_str(imlec)}); "
                    "adaptör aralık dışı bar döndürüyor olabilir"
                )
            imlec = son + adim
            if ilerleme is not None:
                ilerleme(sum(len(s) for s in sayfalar), cagri)

        return sayfalar, cagri

    def indir(
        self,
        sembol: str,
        timeframe: str,
        baslangic_ms: int,
        bitis_ms: int | None = None,
        *,
        ilerleme: Callable[[int, int], None] | None = None,
    ) -> IndirmeSonucu:
        """`[baslangic_ms, bitis_ms)` aralığını indirir, doğrular, depoya yazar.

        `bitis_ms` verilmezse içinde bulunduğumuz barın açılışına sabitlenir — yani son
        kapanmış barın sonuna.
        """
        adim = timeframe_ms(timeframe)
        if baslangic_ms % adim != 0:
            baslangic_ms = bar_acilisi(baslangic_ms, timeframe)
        if bitis_ms is None:
            bitis_ms = self.son_kapali_bar_sonu(timeframe)
        else:
            bitis_ms = bar_acilisi(bitis_ms, timeframe)
        # Sabit veri sonu (K-080) istenen aralığı kırpar: sınırın ötesi hiç istenmez.
        if self.bitis_ms is not None:
            bitis_ms = min(bitis_ms, self.bitis_ms)

        aralik = Aralik(baslangic_ms, bitis_ms)
        if aralik.bitis_ms <= aralik.baslangic_ms:
            raise IndirmeHatasi(f"boş aralık istendi: {aralik}")

        vardi = self.depo.var_mi(sembol, timeframe)
        onceki = self.depo.sha256(sembol, timeframe) if vardi else None
        eksikler = self.eksik_araliklar(sembol, timeframe, aralik)

        t0 = time.perf_counter()
        sayfalar: list[pd.DataFrame] = []
        cagri_toplam = 0
        for parca in eksikler:
            yeni, cagri = self._sayfala(sembol, timeframe, parca, ilerleme)
            sayfalar.extend(yeni)
            cagri_toplam += cagri
        sure = time.perf_counter() - t0

        inen = pd.concat(sayfalar, ignore_index=True) if sayfalar else None
        inen_bar = 0 if inen is None else len(inen)

        # Ham veriyi birleştir, sonra **tümünü** doğrula. Sıra önemli: bayrak tam seriden
        # hesaplanmazsa dosya, indirmenin kaç parçaya bölündüğüne bağlı hale gelir.
        birlesik = self._ham_birlestir(sembol, timeframe, inen)
        if self.bitis_ms is not None:
            # Geri sarım: depoda sınırın ötesinde bar varsa düşer. Bayraklar aşağıda tam
            # seriden yeniden hesaplandığı için kırpılmış seri, o güne kadar indirilmiş
            # seriyle aynı dosyayı verir (`test_indirici.py::TestVeriSonu`).
            birlesik = birlesik[birlesik["open_time"].to_numpy(dtype="int64") < self.bitis_ms]
        if birlesik.empty:
            raise IndirmeHatasi(
                f"{sembol} {timeframe}: {aralik} aralığında hiç bar yok ve depo da boş"
            )

        bayrakli, kalite = dogrula(birlesik, timeframe, sembol=sembol.upper())
        kayit = self.depo.yaz(sembol, timeframe, bayrakli)

        return IndirmeSonucu(
            sembol=sembol.upper(),
            timeframe=timeframe,
            aralik=aralik,
            eksik_araliklar=eksikler,
            inen_bar=inen_bar,
            cagri_sayisi=cagri_toplam,
            sure_s=sure,
            depo=kayit,
            kalite=kalite,
            onceki_sha256=onceki,
        )

    def _ham_birlestir(
        self, sembol: str, timeframe: str, inen: pd.DataFrame | None
    ) -> pd.DataFrame:
        """Depodaki veriyi (bayrakları atarak) inen veriyle birleştirir.

        **Bayraklar atılıyor** çünkü birazdan yeniden hesaplanacaklar. Devralmak, bir kez
        yanlış hesaplanmış bir bayrağın veri setinde kalıcılaşması demek olurdu — ve
        bayrağı düzelten bir kod değişikliği mevcut dosyalara hiç ulaşmazdı.

        **Depo-yeni çakışması burada çözülür, doğrulamada değil.** `duplicate` bayrağı
        borsanın aynı timestamp'i iki kez göndermesini kaydeder (K-006); kendi depomuzu
        yeni bir indirmeyle birleştirmek bir borsa anomalisi değil, olağan işleyiştir. İki
        durum ayrılmazsa örtüşen bir aralığı yeniden indirmek yüzlerce barı sahte
        `duplicate` bayrağıyla işaretler. Bu yüzden depodan gelen çakışan satırlar sessizce
        düşürülür (yeni veri kazanır) ve indirilen paketin **kendi içindeki** tekrarlar
        doğrulamaya olduğu gibi ulaşır.
        """
        if inen is None or inen.empty:
            if not self.depo.var_mi(sembol, timeframe):
                return pd.DataFrame(columns=list(HAM_BAR_SUTUNLARI))
            return self.depo.oku(sembol, timeframe).loc[:, list(HAM_BAR_SUTUNLARI)]

        yeni = inen.loc[:, list(HAM_BAR_SUTUNLARI)]
        if not self.depo.var_mi(sembol, timeframe):
            return yeni.reset_index(drop=True)

        mevcut = self.depo.oku(sembol, timeframe).loc[:, list(HAM_BAR_SUTUNLARI)]
        mevcut = mevcut[~mevcut["open_time"].isin(set(yeni["open_time"]))]
        return pd.concat([mevcut, yeni], ignore_index=True)
