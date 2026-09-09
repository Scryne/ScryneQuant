"""Event loop: bar bar ilerleyen deterministik backtest motoru. (Faz 3)

Bir barın iç sırası **sabittir** ve bu sıra kararların yarısıdır:

1. **Fill** — bir önceki barda üretilmiş bekleyen sinyal, bu barın **açılışından** dolar
   (K-004). Önce fill olması şart: strateji bu barın kapanışında karar verirken elindeki
   pozisyonun güncel olması gerekir.
2. **Karar** — strateji bu barın **kapanmış** hâliyle çağrılır, `ctx` `t`'de kesiktir
   (K-002). Ürettiği sinyal bekleyene alınır; bu barda dolmaz.
3. **Değerleme** — özkaynak ve maruziyet bu barın kapanışıyla işaretlenir.

Sıra tersine dönseydi (önce karar, sonra fill) sinyal kendi barının açılışında dolardı —
yani karar verilirken bilinmeyen bir fiyatla, gizli look-ahead.

**`ok` olmayan barlarda ne olur (K-006, K-028):** ne karar verilir ne fill yapılır. Bir
`suspect` barın açılışından doldurmak, şüpheli bir fiyattan gerçek bir P&L üretmek olurdu.
Atlanan sinyaller sebebiyle birlikte sayılır ve sonuç kaydına yazılır — K-006'nın
"sessizce kullanılmaz" kuralının "sessizce **atılmaz**" tarafı da bu.

Motorun kendisi rastgelelik içermez; `seed` kayda yazılır çünkü Faz 4'ün Monte Carlo'su
onu kullanacak ve o gün kaydın şekli değişmemeli.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

import numpy as np

from scryne_quant.backtest.fill import AtlamaSebebi, Emir, IslemYonu, emir_hazirla
from scryne_quant.backtest.metrikler import Islem, hesapla
from scryne_quant.backtest.sonuc import VARSAYILAN_KALITE_ESIGI, Sonuc, VeriKimligi, atlama_sayimi
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.portfolio.durum import Portfoy
from scryne_quant.strategy.baglam import PiyasaGorunumu
from scryne_quant.strategy.kosu import gorunum_kur
from scryne_quant.strategy.sinyal import Sinyal
from scryne_quant.strategy.temel import Strateji


class BacktestHatasi(ValueError):
    """Backtest kurulumu geçersiz."""


class Backtest:
    """Tek sembol, tek strateji, spot, uzun-yönlü backtest.

    Kapsam bilinçli olarak dar (Final-Doküman v1): çoklu sembol, açığa satış, kaldıraç ve
    portföy düzeyi tahsis yok. Genişletmek için doğru zaman Faz 4'ün ihtiyacı belli
    olduğunda; şimdiden genel yazmak, hiç kullanılmayacak kod yollarını test edilmemiş
    hâlde bırakırdı.
    """

    def __init__(
        self,
        strateji: Strateji,
        maliyet: MaliyetModeli,
        *,
        baslangic_sermaye: float = 10_000.0,
        seed: int = 0,
        kalite_esigi: float = VARSAYILAN_KALITE_ESIGI,
    ) -> None:
        if baslangic_sermaye <= 0.0:
            raise BacktestHatasi(f"başlangıç sermayesi pozitif olmalı: {baslangic_sermaye}")
        self.strateji = strateji
        self.maliyet = maliyet
        self.baslangic_sermaye = baslangic_sermaye
        self.seed = seed
        self.kalite_esigi = kalite_esigi

    # ------------------------------------------------------------------ koşu

    def calistir(
        self,
        sembol: str,
        timeframe: str,
        bar_dizileri: Mapping[str, np.ndarray],
        *,
        veri_sha256: str = "",
    ) -> Sonuc:
        """Backtest'i koşturur ve tam sonuç kaydını döndürür."""
        adim = timeframe_ms(timeframe)
        gorunum = gorunum_kur(sembol, timeframe, bar_dizileri, self.strateji)
        n = len(gorunum)
        if n < 2:
            raise BacktestHatasi(f"backtest için en az 2 bar gerekir, verilen: {n}")

        acilis = gorunum.barlar["open"]
        kapanis = gorunum.barlar["close"]
        zamanlar = gorunum.barlar["open_time"]
        kalite = gorunum.barlar["quality_status"]

        self.strateji.hazirla()
        portfoy = Portfoy(nakit=self.baslangic_sermaye)

        ozkaynak = np.empty(n, dtype=np.float64)
        maruziyet = np.empty(n, dtype=np.float64)
        islemler: list[Islem] = []
        acik: Islem | None = None
        bekleyen: Sinyal | None = None
        atlanan: list[AtlamaSebebi] = []
        uretilen = 0

        for i in range(n):
            bar_ok = str(kalite[i]) == KaliteDurumu.OK

            # 1) Fill — bekleyen sinyal bu barın açılışından dolar (K-004).
            if bekleyen is not None:
                if not bar_ok:
                    atlanan.append(AtlamaSebebi.FILL_BARI_OK_DEGIL)
                else:
                    sonuc = emir_hazirla(
                        bekleyen, portfoy, float(acilis[i]), int(zamanlar[i]), self.maliyet
                    )
                    if isinstance(sonuc, AtlamaSebebi):
                        atlanan.append(sonuc)
                    else:
                        portfoy, acik = self._uygula(sonuc, portfoy, acik, islemler)
                bekleyen = None

            # 2) Karar — strateji kapanmış barı görür, `ctx` `t`'de kesiktir (K-002).
            if bar_ok:
                ctx = gorunum.baglam(i, portfoy.gorunum(float(kapanis[i])))
                sinyal = self.strateji.on_bar(ctx)
                if sinyal is not None:
                    uretilen += 1
                    if i == n - 1:
                        # Son barın sinyali dolacağı barı bulamaz. Bir sonraki barın
                        # açılışını beklemek yerine kendi kapanışından doldurmak K-004'ün
                        # açıkça yasakladığı şey olurdu.
                        atlanan.append(AtlamaSebebi.SONRAKI_BAR_YOK)
                    else:
                        bekleyen = sinyal

            # 3) Değerleme — bu barın kapanışıyla işaretle.
            fiyat = float(kapanis[i])
            ozkaynak[i] = portfoy.ozkaynak(fiyat)
            maruziyet[i] = portfoy.maruziyet(fiyat)

        sayim = Counter(str(k) for k in kalite)
        ok_olmayan = n - sayim.get(str(KaliteDurumu.OK), 0)

        return Sonuc(
            veri=VeriKimligi(
                sembol=sembol,
                timeframe=timeframe,
                sha256=veri_sha256,
                bar_sayisi=n,
                ilk_ms=int(zamanlar[0]),
                son_ms=int(zamanlar[-1]),
                ok_olmayan_bar=ok_olmayan,
                ok_olmayan_oran=ok_olmayan / n,
                kalite_sayimi=dict(sayim),
            ),
            strateji=self.strateji.sozluk(),
            maliyet=self.maliyet.sozluk(),
            baslangic_sermaye=self.baslangic_sermaye,
            seed=self.seed,
            metrikler=hesapla(ozkaynak, maruziyet, islemler, adim, self.baslangic_sermaye),
            islemler=islemler,
            ozkaynak=ozkaynak,
            maruziyet=maruziyet,
            zamanlar=np.asarray(zamanlar),
            atlanan=atlama_sayimi(atlanan),
            uretilen_sinyal=uretilen,
            acik_pozisyon_sonda=portfoy.acik,
            kalite_esigi=self.kalite_esigi,
        )

    # ------------------------------------------------------------------ defter

    @staticmethod
    def _uygula(
        emir: Emir,
        portfoy: Portfoy,
        acik: Islem | None,
        islemler: list[Islem],
    ) -> tuple[Portfoy, Islem | None]:
        """Emri portföye uygular ve işlem defterini günceller.

        Bir "işlem" düzden düze bir pozisyon turudur: ilk alımda açılır, pozisyon sıfıra
        döndüğünde kapanır. Aradaki her fill aynı turun içindedir.
        """
        if emir.yon is IslemYonu.AL:
            if acik is None:
                acik = Islem(acilis_ms=emir.zaman_ms)
                islemler.append(acik)
            portfoy = portfoy.al(emir.miktar, emir.fiyat, emir.komisyon, emir.zaman_ms)
            acik.giris_notional += emir.notional
            acik.giris_miktar += emir.miktar
        else:
            if acik is None:  # pragma: no cover - pozisyon yokken satış emri üretilmez
                raise BacktestHatasi("açık işlem yokken satış emri")
            portfoy, gerceklesen = portfoy.sat(emir.miktar, emir.fiyat, emir.komisyon)
            acik.cikis_notional += emir.notional
            acik.cikis_miktar += emir.miktar
            acik.net_pnl += gerceklesen

        acik.komisyon += emir.komisyon
        acik.slippage += emir.slippage_maliyeti
        acik.fill_sayisi += 1

        if not portfoy.acik:
            acik.kapanis_ms = emir.zaman_ms
            acik = None
        return portfoy, acik


def calistir(
    strateji: Strateji,
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    *,
    baslangic_sermaye: float = 10_000.0,
    seed: int = 0,
    veri_sha256: str = "",
) -> Sonuc:
    """Tek çağrılık kolaylık sarmalayıcısı."""
    return Backtest(
        strateji, maliyet, baslangic_sermaye=baslangic_sermaye, seed=seed
    ).calistir(sembol, timeframe, bar_dizileri, veri_sha256=veri_sha256)


__all__ = ["Backtest", "BacktestHatasi", "PiyasaGorunumu", "calistir"]
