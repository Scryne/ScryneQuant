"""Event loop: bar bar ilerleyen deterministik backtest motoru. (Faz 3)

Bir barın iç sırası **sabittir** ve bu sıra kararların yarısıdır:

1. **Fill** — bir önceki barda üretilmiş bekleyen sinyal, bu barın **açılışından** dolar
   (K-004). Önce fill olması şart: strateji bu barın kapanışında karar verirken elindeki
   pozisyonun güncel olması gerekir.
2. **Risk durumu** — risk motoru devredeyse (Faz 5) bu barın özkaynağını işler: gün
   dönümü, zirve, drawdown. Karardan **önce**; sonra olsaydı drawdown ve günlük zarar bir
   bar gecikmeli ölçülür, yani limitler bir bar geç devreye girerdi.
3. **Karar** — strateji bu barın **kapanmış** hâliyle çağrılır, `ctx` `t`'de kesiktir
   (K-002). Ürettiği sinyal risk motorundan geçer; onaylanırsa bekleyene alınır (riskin
   izin verdiği hedefle), reddedilirse `risk_reddetti` olarak sayılır. Hiçbir hâlde bu
   barda dolmaz.
4. **Değerleme** — özkaynak ve maruziyet bu barın kapanışıyla işaretlenir.

Sıra tersine dönseydi (önce karar, sonra fill) sinyal kendi barının açılışında dolardı —
yani karar verilirken bilinmeyen bir fiyatla, gizli look-ahead.

**Risk kararı sinyal barında verilir, fill barında değil.** Fill barında verilseydi risk
motoru `t+1`in açılışını görmüş olurdu — kararı bilinmeyen bir fiyatla vermek, K-002'nin
yasakladığı şeyin risk katmanındaki hâli.

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

from scryne_quant.backtest.defter import uygula as defter_uygula
from scryne_quant.backtest.fill import AtlamaSebebi, Emir, emir_hazirla
from scryne_quant.backtest.metrikler import Islem, hesapla
from scryne_quant.backtest.sonuc import VARSAYILAN_KALITE_ESIGI, Sonuc, VeriKimligi, atlama_sayimi
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.data.semalar import KaliteDurumu
from scryne_quant.features.indikator import atr as atr_hesapla
from scryne_quant.portfolio.durum import Portfoy
from scryne_quant.risk.motor import RISK_ATR_PENCERESI, PiyasaOlcumu, RiskMotoru
from scryne_quant.risk.niyet import OnayliNiyet
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
        risk: RiskMotoru | None = None,
    ) -> None:
        if baslangic_sermaye <= 0.0:
            raise BacktestHatasi(f"başlangıç sermayesi pozitif olmalı: {baslangic_sermaye}")
        self.strateji = strateji
        self.maliyet = maliyet
        self.baslangic_sermaye = baslangic_sermaye
        self.seed = seed
        self.kalite_esigi = kalite_esigi

        self.risk = risk
        """Risk motoru. `None` = devre dışı, ve bu **araştırma** için kasıtlı bir seçenek.

        Neden opsiyonel: Faz 1-4'ün tamamı risk motoru olmadan ölçüldü ve o ölçümler
        karşılaştırma tabanı. Risk motorunu zorunlu kılmak, Faz 4'ün sonuçlarını yeniden
        üretilemez hâle getirir — oysa `sq lab dogrula` tam olarak onu yapıyor.

        Bu, "risk atlanabilir" demek **değil**: backtest bir simülasyondur, execution
        değil. Gerçek emrin geçtiği kapı (`execution/kapi.py`) `OnayliNiyet` dışında
        hiçbir şey kabul etmiyor ve paper/live modunda motor zorunlu. Atlanamayan şey
        borsaya giden yol; ölçülebilir olan şey "risk limitleri bu stratejiye ne yapar".
        """

    # ------------------------------------------------------------------ koşu

    def calistir(
        self,
        sembol: str,
        timeframe: str,
        bar_dizileri: Mapping[str, np.ndarray],
        *,
        veri_sha256: str = "",
        olcum_baslangici: int = 0,
    ) -> Sonuc:
        """Backtest'i koşturur ve tam sonuç kaydını döndürür.

        `olcum_baslangici`: bu indeksten **önceki** barlar yalnızca indikatör ısınması
        içindir — orada üretilen sinyaller işleme dönmez ve equity eğrisi ile metrikler
        o indeksten başlar.

        Faz 4'ün walk-forward'ı için var. Bir katmanı yalnızca kendi barlarıyla
        koşturmak, indikatörleri sıfırdan ısıtmak demek olurdu — oysa canlıda o tarihe
        gelindiğinde geçmiş veri elde olurdu. İndikatörler nedensel olduğu için (K-002)
        önceki barları hesaba katmak look-ahead değil, **gerçekçilik**tir; ölçümü o
        barlardan başlatmak ise katmanın sınırını korur.
        """
        adim = timeframe_ms(timeframe)
        gorunum = gorunum_kur(sembol, timeframe, bar_dizileri, self.strateji)
        n = len(gorunum)
        if n < 2:
            raise BacktestHatasi(f"backtest için en az 2 bar gerekir, verilen: {n}")
        if not 0 <= olcum_baslangici < n - 1:
            raise BacktestHatasi(
                f"ölçüm başlangıcı 0..{n - 2} aralığında olmalı, verilen: {olcum_baslangici}"
            )

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
        # Bekleyen = (sinyal, riskin onayladığı hedef). Risk devre dışıysa hedef sinyalin
        # kendi hedefi; devredeyse onun aşağı çekilmiş hâli.
        bekleyen: tuple[Sinyal, float] | None = None
        atlanan: list[AtlamaSebebi] = []
        uretilen = 0

        # Risk motorunun volatilite ölçüsü. Stratejinin bildirdiği özelliklerden bağımsız
        # hesaplanıyor: strateji ATR bildirmese de guard çalışmak zorunda.
        risk_atr = (
            atr_hesapla(
                gorunum.barlar["high"], gorunum.barlar["low"], kapanis, RISK_ATR_PENCERESI
            )
            if self.risk is not None
            else None
        )

        for i in range(n):
            bar_ok = str(kalite[i]) == KaliteDurumu.OK

            # 1) Fill — bekleyen sinyal bu barın açılışından dolar (K-004).
            if bekleyen is not None:
                if not bar_ok:
                    atlanan.append(AtlamaSebebi.FILL_BARI_OK_DEGIL)
                else:
                    sinyal_b, hedef_b = bekleyen
                    sonuc = emir_hazirla(
                        sinyal_b,
                        portfoy,
                        float(acilis[i]),
                        int(zamanlar[i]),
                        self.maliyet,
                        hedef_maruziyet=hedef_b,
                    )
                    if isinstance(sonuc, AtlamaSebebi):
                        atlanan.append(sonuc)
                    else:
                        portfoy, acik = self._uygula(sonuc, portfoy, acik, islemler)
                bekleyen = None

            fiyat = float(kapanis[i])

            # 2) Risk durumunun bu barla güncellenmesi — **karardan önce.** Sonra olsaydı
            #    drawdown ve günlük zarar bir bar gecikmeli ölçülür, yani limit bir bar
            #    geç devreye girerdi.
            if self.risk is not None:
                self.risk.bar_isle(int(zamanlar[i]), portfoy.ozkaynak(fiyat))

            # 3) Karar — strateji kapanmış barı görür, `ctx` `t`'de kesiktir (K-002).
            if bar_ok:
                ctx = gorunum.baglam(i, portfoy.gorunum(fiyat))
                sinyal = self.strateji.on_bar(ctx)
                if sinyal is not None:
                    uretilen += 1
                    if i < olcum_baslangici:
                        atlanan.append(AtlamaSebebi.ISINMA_PENCERESI)
                    elif i == n - 1:
                        # Son barın sinyali dolacağı barı bulamaz. Bir sonraki barın
                        # açılışını beklemek yerine kendi kapanışından doldurmak K-004'ün
                        # açıkça yasakladığı şey olurdu.
                        atlanan.append(AtlamaSebebi.SONRAKI_BAR_YOK)
                    else:
                        hedef = self._risk_onayi(
                            sinyal, portfoy, fiyat, int(zamanlar[i]), risk_atr, i
                        )
                        if hedef is None:
                            atlanan.append(AtlamaSebebi.RISK_REDDETTI)
                        else:
                            bekleyen = (sinyal, hedef)

            # 4) Değerleme — bu barın kapanışıyla işaretle.
            ozkaynak[i] = portfoy.ozkaynak(fiyat)
            maruziyet[i] = portfoy.maruziyet(fiyat)

        # Ölçüm penceresi: ısınma barları kayda girmez. Girselerdi katmanın Sharpe'ı
        # işlem yapılmayan düz barlarla sulandırılır ve katmanlar arası karşılaştırma
        # ısınma uzunluğuna göre değişirdi.
        ozkaynak = ozkaynak[olcum_baslangici:]
        maruziyet = maruziyet[olcum_baslangici:]
        olcum_zamanlari = np.asarray(zamanlar)[olcum_baslangici:]
        olcum_kalite = np.asarray(kalite)[olcum_baslangici:]
        olcum_n = len(olcum_zamanlari)

        sayim = Counter(str(k) for k in olcum_kalite)
        ok_olmayan = olcum_n - sayim.get(str(KaliteDurumu.OK), 0)

        return Sonuc(
            veri=VeriKimligi(
                sembol=sembol,
                timeframe=timeframe,
                sha256=veri_sha256,
                bar_sayisi=olcum_n,
                ilk_ms=int(olcum_zamanlari[0]),
                son_ms=int(olcum_zamanlari[-1]),
                ok_olmayan_bar=ok_olmayan,
                ok_olmayan_oran=ok_olmayan / olcum_n,
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
            zamanlar=olcum_zamanlari,
            atlanan=atlama_sayimi(atlanan),
            uretilen_sinyal=uretilen,
            acik_pozisyon_sonda=portfoy.acik,
            kalite_esigi=self.kalite_esigi,
            risk=None if self.risk is None else self.risk.ozet(),
        )

    # ------------------------------------------------------------------ risk

    def _risk_onayi(
        self,
        sinyal: Sinyal,
        portfoy: Portfoy,
        fiyat: float,
        zaman_ms: int,
        risk_atr: np.ndarray | None,
        i: int,
    ) -> float | None:
        """Sinyali risk motoruna sunar. Onaylanırsa hedef maruziyet, reddedilirse `None`.

        Risk devre dışıysa sinyalin kendi hedefi dönüyor — yani risksiz koşuda bu fonksiyon
        kimliktir ve Faz 1-4'ün ölçümleri bit düzeyinde korunur.
        """
        if self.risk is None or risk_atr is None:
            return sinyal.target_exposure

        atr_degeri = float(risk_atr[i])
        karar = self.risk.degerlendir(
            sinyal,
            PiyasaOlcumu(
                fiyat=fiyat,
                ozkaynak=portfoy.ozkaynak(fiyat),
                mevcut_maruziyet=portfoy.maruziyet(fiyat),
                bar_ms=zaman_ms,
                # NaN (ısınma penceresi) "ölçülemedi" demek, sıfır değil: sıfır ATR
                # volatilite guard'ını geçer ve boyut tavanını sonsuz yapardı.
                atr=None if np.isnan(atr_degeri) else atr_degeri,
            ),
        )
        return karar.onayli_maruziyet if isinstance(karar, OnayliNiyet) else None

    # ------------------------------------------------------------------ defter

    def _uygula(
        self,
        emir: Emir,
        portfoy: Portfoy,
        acik: Islem | None,
        islemler: list[Islem],
    ) -> tuple[Portfoy, Islem | None]:
        """Emri portföye uygular. Mantık `backtest/defter.py`de — paper döngüsüyle ortak.

        Faz 6'da buradan taşındı (K-001): ortalama maliyet, tur muhasebesi ve cooldown'ı
        tetikleyen "kapanan tur" tanımı backtest ile paper arasında ikiye ayrılamaz.
        """
        portfoy, acik, _ = defter_uygula(emir, portfoy, acik, islemler, risk=self.risk)
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
