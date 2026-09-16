"""Performans metrikleri ve işlem defteri. (§17, Roadmap Faz 3)

**Yıllıklandırma takvim üzerinden yapılır, 252 işlem günü üzerinden değil.** Kripto 7/24
kesintisiz işlem görür; hisse senedi konvansiyonunu buraya taşımak Sharpe'ı ~%18 şişirirdi
(√(365,25·24) / √252·... farkı). Bir bar yılı: `365,25 × 24 × 3.600.000 ms / timeframe_ms`.

**Risksiz faiz sıfır alınır.** Sıfırdan farklı bir oran, hangi para biriminin hangi
vadedeki oranı olduğu kararını gerektirir ve o karar için elimizde veri yok. Sıfır almak
Sharpe'ı **yukarı** çeker, yani aleyhte değil lehte bir varsayım — bu yüzden K-007'nin
"belirsizlikte aleyhte yuvarla" kuralına aykırı görünüyor. Kabul edilmesinin sebebi:
Sharpe burada mutlak bir eşik değil, **stratejiler arası karşılaştırma** aracı (Faz 4) ve
sabit bir kayma sıralamayı değiştirmez. Promotion eşikleri (K-019) sayısallaştırılırken bu
varsayım yeniden gözden geçirilmelidir.

**Drawdown pozitif kesir olarak raporlanır:** `0.23` = %23 düşüş. İşaretli raporlamak,
"max drawdown −0,23'ten büyük olmalı" gibi her okuyanın yönünü karıştırdığı eşiklere yol
açar.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np

#: Yıl uzunluğu, milisaniye. 365,25 gün — artık yıl sessizce kaymasın.
YIL_MS: Final = 365.25 * 24 * 3_600_000

#: Yıllıklandırmanın anlamlı sayılması için gereken asgari pencere: 30 gün.
#:
#: Kısa pencerede yıllıklandırma matematiksel olarak tanımlı ama **anlamsızdır**: 3 saatlik
#: bir koşuda %50 getiri, yıllığa çevrilince 10^500 mertebesinde bir sayı verir. Bu sayı
#: yanlış değil, sorulan sorunun saçma olduğunun göstergesi. `Metrikler.yillik_anlamli`
#: bunu açıkça bildirir; Faz 4'ün walk-forward katmanları kısa olabileceği için bu bayrak
#: orada gerçekten kullanılacak.
ASGARI_YILLIK_PENCERE_MS: Final = 30 * 24 * 3_600_000

#: CAGR tavanı. Kısa pencerede üs alma `OverflowError` fırlatır — ölçüldü, bir testte
#: patladı. Taşmayı hataya çevirmek yerine tavana kırpıyoruz: %100.000.000 yıllık getiri
#: hiçbir gerçek koşuda görülmez, yani bu değeri gören okuyucu `yillik_anlamli`ya bakması
#: gerektiğini anlar. Sonsuz döndürmek olmazdı: JSON'da geçersiz, ve bir metrik tablosunda
#: "sonsuz" iyi diye okunur.
CAGR_TAVANI: Final = 1e6

#: VaR/CVaR güven düzeyleri. Tarihsel (parametrik değil) yöntem: dağılımın normal olduğunu
#: varsaymak, kripto getirilerinde kuyruğu sistematik olarak hafife alır — K-007'nin
#: "belirsizlikte aleyhte yuvarla" kuralına aykırı bir varsayım olurdu.
#:
#: **Bunlar kapı değil, raporlanan metrik** (K-054): eşiği ölçülmemiş bir sayı kapı değildir.
VAR_GUVENLERI: Final[tuple[float, ...]] = (0.95, 0.99)

#: Kapasite ölçüsünün ortalama günlük hacim penceresi (gün). 30 gün, tek bir haber gününün
#: hacim patlamasının oranı şişirmesini engelleyecek kadar uzun; likiditenin ay içinde
#: değiştiği bir evrende bağlayıcı kalacak kadar kısa.
KAPASITE_ADV_GUN: Final = 30


@dataclass(slots=True)
class Islem:
    """Düzden düze bir tur: pozisyon açılır, (kısmen) büyütülür/küçültülür, kapanır.

    "İşlem" birimi olarak tek bir fill değil **pozisyon turu** seçildi: win rate, ortalama
    tutma süresi ve profit factor ancak bir giriş bir çıkışla eşleştiğinde anlamlıdır. Her
    fill'i ayrı işlem saymak, bir pozisyonu iki taksitte kapatan stratejiyi iki kat çok
    işlem yapmış gösterirdi.
    """

    acilis_ms: int
    kapanis_ms: int | None = None
    giris_notional: float = 0.0
    giris_miktar: float = 0.0
    cikis_notional: float = 0.0
    cikis_miktar: float = 0.0
    komisyon: float = 0.0
    slippage: float = 0.0
    net_pnl: float = 0.0
    """Komisyon **ve** slippage düşülmüş gerçekleşen kâr/zarar (quote birimi)."""

    fill_sayisi: int = 0

    sembol: str = ""
    """Turun enstrümanı. Tek sembollü koşuda boş bırakılır ve `sozluk()`e **yazılmaz**.

    Yazılsaydı Faz 1-7'de `runs/` altına kaydedilmiş her sonucun `sonuc_hash`i değişirdi —
    yani çok enstrümanlı motoru eklemek, onu hiç kullanmayan eski deneyleri yeniden
    üretilemez yapardı (K-009). Aynı gerekçeyle `Sonuc.risk` de hash'e yalnızca varsa
    giriyor. Tek sembollü koşuda sembol zaten `veri.sembol`de duruyor, kaybolmuyor.
    """

    @property
    def kapali(self) -> bool:
        return self.kapanis_ms is not None

    @property
    def brut_pnl(self) -> float:
        """Komisyon öncesi kâr/zarar. Slippage fiyata gömülü olduğu için buna dahildir."""
        return self.net_pnl + self.komisyon

    @property
    def kazandi(self) -> bool:
        return self.net_pnl > 0.0

    @property
    def sure_ms(self) -> int:
        return 0 if self.kapanis_ms is None else self.kapanis_ms - self.acilis_ms

    @property
    def getiri(self) -> float:
        """İşleme bağlanan sermayeye göre getiri kesri."""
        return self.net_pnl / self.giris_notional if self.giris_notional > 0.0 else 0.0

    def sozluk(self, *, sembol_yaz: bool = False) -> dict[str, Any]:
        return ({"sembol": self.sembol} if sembol_yaz else {}) | {
            "acilis_ms": self.acilis_ms,
            "kapanis_ms": self.kapanis_ms,
            "giris_notional": self.giris_notional,
            "cikis_notional": self.cikis_notional,
            "miktar": self.giris_miktar,
            "komisyon": self.komisyon,
            "slippage": self.slippage,
            "brut_pnl": self.brut_pnl,
            "net_pnl": self.net_pnl,
            "getiri": self.getiri,
            "sure_ms": self.sure_ms,
            "fill_sayisi": self.fill_sayisi,
        }


@dataclass(frozen=True, slots=True)
class Metrikler:
    """Bir backtest koşusunun performans özeti."""

    # --- getiri
    baslangic_sermaye: float
    bitis_sermaye: float
    toplam_getiri: float
    cagr: float
    yillik_volatilite: float
    yillik_anlamli: bool
    """Pencere yıllıklandırmaya yetecek kadar uzun mu (≥30 gün).

    `False` ise `cagr`, `yillik_volatilite`, `sharpe`, `sortino` ve `calmar` matematiksel
    olarak hesaplanmıştır ama yorumlanamaz. Promotion kapıları (K-019) bu bayrağa bakmak
    zorunda: 3 günlük bir walk-forward katmanının Sharpe'ı bir kanıt değildir.
    """

    # --- risk
    sharpe: float
    sortino: float
    max_drawdown: float
    """Pozitif kesir: 0.23 = %23 düşüş."""
    max_drawdown_bar: int
    """Zirveden zirveye dönüşün en uzun sürdüğü bar sayısı."""
    calmar: float

    # --- işlem
    islem_sayisi: int
    kazanan: int
    kaybeden: int
    win_rate: float
    profit_factor: float
    ortalama_kazanc: float
    ortalama_kayip: float
    expectancy: float
    en_iyi_islem: float
    en_kotu_islem: float
    ardisik_kayip: int
    ortalama_tutma_ms: float
    ortalama_tutma_bar: float

    # --- kuyruk riski (§16, K-054 — raporlanır, kapı değildir)
    var_95: float
    """Bar getirilerinin %95 tarihsel VaR'ı, **pozitif kesir**: 0,03 = barların %5'inde
    en az %3 kaybedildi. Yıllıklandırılmadı; ölçek timeframe'in kendisi."""

    cvar_95: float
    """VaR'ı aşan kuyruğun ortalaması (expected shortfall), pozitif kesir."""

    var_99: float
    cvar_99: float

    # --- kapasite (§16)
    kapasite_adv_azami: float
    """Tek bir fill'in, o enstrümanın 30 günlük ortalama günlük hacmine oranı — azami.

    Kapasitenin en dürüst tek sayısı bu: portföy büyüdükçe hangi emrin piyasayı iteceğini
    ortalama değil, **en kötü** oran söyler. Ölçüm nedensel: ADV, fill barından önceki
    pencereden hesaplanır."""

    kapasite_adv_ortalama: float

    # --- maliyet ve maruziyet
    toplam_komisyon: float
    toplam_slippage: float
    islem_hacmi: float
    turnover: float
    ortalama_maruziyet: float
    azami_maruziyet: float

    def sozluk(self) -> dict[str, Any]:
        return {
            alan: getattr(self, alan)
            for alan in (
                "baslangic_sermaye",
                "bitis_sermaye",
                "toplam_getiri",
                "cagr",
                "yillik_volatilite",
                "yillik_anlamli",
                "sharpe",
                "sortino",
                "max_drawdown",
                "max_drawdown_bar",
                "calmar",
                "islem_sayisi",
                "kazanan",
                "kaybeden",
                "win_rate",
                "profit_factor",
                "ortalama_kazanc",
                "ortalama_kayip",
                "expectancy",
                "en_iyi_islem",
                "en_kotu_islem",
                "ardisik_kayip",
                "ortalama_tutma_ms",
                "ortalama_tutma_bar",
                "var_95",
                "cvar_95",
                "var_99",
                "cvar_99",
                "kapasite_adv_azami",
                "kapasite_adv_ortalama",
                "toplam_komisyon",
                "toplam_slippage",
                "islem_hacmi",
                "turnover",
                "ortalama_maruziyet",
                "azami_maruziyet",
            )
        }


@dataclass(frozen=True, slots=True)
class Drawdown:
    """Düşüş analizi sonucu."""

    azami: float
    en_uzun_bar: int
    seri: np.ndarray = field(repr=False)


def bar_yili(timeframe_ms: int) -> float:
    """Bir yıla kaç bar sığar. Yıllıklandırmanın tek kaynağı."""
    if timeframe_ms <= 0:
        raise ValueError(f"timeframe_ms pozitif olmalı: {timeframe_ms}")
    return YIL_MS / timeframe_ms


def drawdown(ozkaynak: np.ndarray) -> Drawdown:
    """Zirveden düşüş serisi, azami düşüş ve en uzun düşüş süresi.

    Süre "zirveden **yeni** zirveye kadar geçen bar sayısı"dır. Serinin sonunda hâlâ
    toparlanmamış bir düşüş varsa o da sayılır — toparlanmadığı için görmezden gelmek,
    en kötü durumu raporlamamak olurdu.
    """
    if ozkaynak.size == 0:
        return Drawdown(0.0, 0, np.array([], dtype=np.float64))

    zirve = np.maximum.accumulate(ozkaynak)
    # Zirve sıfır veya negatifse oran anlamsız; spot ve uzun-yönlü portföyde özkaynak
    # sıfırın altına inemez, ama sıfıra yaklaşabilir.
    with np.errstate(divide="ignore", invalid="ignore"):
        seri = np.where(zirve > 0.0, 1.0 - ozkaynak / zirve, 0.0)
    seri = np.nan_to_num(seri, nan=0.0, posinf=0.0, neginf=0.0)

    en_uzun = 0
    suren = 0
    for i in range(ozkaynak.size):
        if ozkaynak[i] >= zirve[i]:
            suren = 0
        else:
            suren += 1
            en_uzun = max(en_uzun, suren)

    return Drawdown(azami=float(seri.max()), en_uzun_bar=int(en_uzun), seri=seri)


def var_cvar(getiriler: np.ndarray, guven: float) -> tuple[float, float]:
    """Tarihsel VaR ve CVaR; ikisi de **pozitif kesir** (kayıp) olarak döner.

    Pozitif raporlamak `max_drawdown` ile aynı gerekçe: "VaR −0,03'ten büyük olmalı" gibi
    her okuyanın yönünü karıştırdığı eşikler doğmasın.

    Kayıp yoksa sıfır döner — negatif bir VaR ("en kötü barda bile kazandık") matematiksel
    olarak doğru ama bir risk metriği olarak yanıltıcıdır.
    """
    if getiriler.size == 0:
        return 0.0, 0.0
    esik = float(np.quantile(getiriler, 1.0 - guven))
    kuyruk = getiriler[getiriler <= esik]
    cvar = float(kuyruk.mean()) if kuyruk.size else esik
    return max(0.0, -esik), max(0.0, -cvar)


def gunluk_hacim(
    quote_volume: np.ndarray, timeframe_ms: int, gun: int = KAPASITE_ADV_GUN
) -> np.ndarray:
    """Nedensel ortalama günlük hacim: `i`. barda, **`i` dahil önceki** `gun` günün ortalaması.

    `i`yi dahil etmek bir look-ahead değil: kapasite ölçüsü fill barında hesaplanıyor ve o
    barın hacmi fill anında henüz bilinmiyor olsa da, kapasite bir **karar girdisi değil**,
    bir rapor. Karara girseydi (örneğin "ADV'nin %1'ini aşma" diye bir risk limiti) pencere
    bir bar geriye kaydırılmak zorunda kalırdı; o gün limit yazıldığında burada da yazacak.

    Isınma bölgesinde (ilk pencere dolmadan) eldeki barların ortalaması kullanılır: sıfır
    döndürmek oranı sonsuz yapardı, NaN döndürmek kapasiteyi ölçülemez.
    """
    if quote_volume.size == 0:
        return np.array([], dtype=np.float64)
    bar_gun = max(1, round(86_400_000 / timeframe_ms))
    pencere = max(1, bar_gun * gun)
    v = np.asarray(quote_volume, dtype=np.float64)
    kum = np.concatenate(([0.0], np.cumsum(np.nan_to_num(v, nan=0.0))))
    idx = np.arange(1, v.size + 1)
    bas = np.maximum(0, idx - pencere)
    toplam = kum[idx] - kum[bas]
    gun_sayisi = np.maximum((idx - bas) / bar_gun, 1.0 / bar_gun)
    return toplam / gun_sayisi


def _bolum(pay: float, payda: float, varsayilan: float = 0.0) -> float:
    """Sıfıra bölmeyi `inf` yerine açık bir varsayılana çevirir.

    `inf` bir metrik tablosunda "çok iyi" diye okunur; oysa anlamı "payda yok", yani
    ölçülecek şey yok. Sessiz `inf`, hiç kaybetmemiş bir stratejiyi sonsuz profit factor
    ile en üste taşır.
    """
    return pay / payda if payda != 0.0 else varsayilan


def hesapla(
    ozkaynak: np.ndarray,
    maruziyet: np.ndarray,
    islemler: list[Islem],
    timeframe_ms: int,
    baslangic_sermaye: float,
    *,
    kapasite_oranlari: Sequence[float] = (),
) -> Metrikler:
    """Equity eğrisi + işlem defterinden metrikleri üretir.

    `kapasite_oranlari`: fill başına `notional / ADV` oranları. Motor hesaplar, çünkü hacim
    serisi metrik katmanında yok — ve olmamalı: metrikler equity eğrisi ile işlem
    defterinden türer, bar verisinden değil.
    """
    if ozkaynak.size == 0:
        raise ValueError("boş equity eğrisi")
    if maruziyet.size != ozkaynak.size:
        raise ValueError("maruziyet ve özkaynak serileri aynı uzunlukta olmalı")

    bitis = float(ozkaynak[-1])
    toplam_getiri = _bolum(bitis - baslangic_sermaye, baslangic_sermaye)

    yil_bar = bar_yili(timeframe_ms)
    yil = ozkaynak.size / yil_bar

    if bitis > 0.0 and baslangic_sermaye > 0.0 and yil > 0.0:
        # Log uzayında: doğrudan üs alma kısa pencerede `OverflowError` fırlatıyor.
        us = math.log(bitis / baslangic_sermaye) / yil
        cagr = math.expm1(us) if us < math.log1p(CAGR_TAVANI) else CAGR_TAVANI
    else:
        # Sermaye tükendiyse CAGR tanımsızdır; −1 ("her şey gitti") en dürüst gösterim.
        cagr = -1.0

    getiriler = np.diff(ozkaynak) / np.where(ozkaynak[:-1] != 0.0, ozkaynak[:-1], np.nan)
    getiriler = np.nan_to_num(getiriler, nan=0.0, posinf=0.0, neginf=0.0)

    if getiriler.size > 1:
        sapma = float(getiriler.std(ddof=1))
        ortalama = float(getiriler.mean())
        volatilite = sapma * math.sqrt(yil_bar)
        sharpe = _bolum(ortalama, sapma) * math.sqrt(yil_bar)
        asagi = getiriler[getiriler < 0.0]
        asagi_sapma = math.sqrt(float((asagi**2).mean())) if asagi.size else 0.0
        sortino = _bolum(ortalama, asagi_sapma) * math.sqrt(yil_bar)
    else:
        volatilite = sharpe = sortino = 0.0

    dd = drawdown(ozkaynak)
    calmar = _bolum(cagr, dd.azami)

    kapali = [i for i in islemler if i.kapali]
    kazananlar = [i for i in kapali if i.kazandi]
    kaybedenler = [i for i in kapali if not i.kazandi]
    kar = sum(i.net_pnl for i in kazananlar)
    zarar = -sum(i.net_pnl for i in kaybedenler)

    ardisik = enuzun = 0
    for i in kapali:
        ardisik = ardisik + 1 if not i.kazandi else 0
        enuzun = max(enuzun, ardisik)

    hacim = sum(i.giris_notional + i.cikis_notional for i in islemler)

    return Metrikler(
        baslangic_sermaye=baslangic_sermaye,
        bitis_sermaye=bitis,
        toplam_getiri=toplam_getiri,
        cagr=cagr,
        yillik_volatilite=volatilite,
        yillik_anlamli=ozkaynak.size * timeframe_ms >= ASGARI_YILLIK_PENCERE_MS,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=dd.azami,
        max_drawdown_bar=dd.en_uzun_bar,
        calmar=calmar,
        islem_sayisi=len(kapali),
        kazanan=len(kazananlar),
        kaybeden=len(kaybedenler),
        win_rate=_bolum(len(kazananlar), len(kapali)),
        profit_factor=_bolum(kar, zarar),
        ortalama_kazanc=_bolum(kar, len(kazananlar)),
        ortalama_kayip=_bolum(-zarar, len(kaybedenler)),
        expectancy=_bolum(sum(i.net_pnl for i in kapali), len(kapali)),
        en_iyi_islem=max((i.net_pnl for i in kapali), default=0.0),
        en_kotu_islem=min((i.net_pnl for i in kapali), default=0.0),
        ardisik_kayip=enuzun,
        var_95=var_cvar(getiriler, 0.95)[0],
        cvar_95=var_cvar(getiriler, 0.95)[1],
        var_99=var_cvar(getiriler, 0.99)[0],
        cvar_99=var_cvar(getiriler, 0.99)[1],
        kapasite_adv_azami=max(kapasite_oranlari, default=0.0),
        kapasite_adv_ortalama=(
            sum(kapasite_oranlari) / len(kapasite_oranlari) if kapasite_oranlari else 0.0
        ),
        ortalama_tutma_ms=_bolum(sum(i.sure_ms for i in kapali), len(kapali)),
        ortalama_tutma_bar=_bolum(sum(i.sure_ms for i in kapali), len(kapali) * timeframe_ms),
        toplam_komisyon=sum(i.komisyon for i in islemler),
        toplam_slippage=sum(i.slippage for i in islemler),
        islem_hacmi=hacim,
        turnover=_bolum(hacim, baslangic_sermaye),
        ortalama_maruziyet=float(maruziyet.mean()),
        azami_maruziyet=float(maruziyet.max()),
    )
