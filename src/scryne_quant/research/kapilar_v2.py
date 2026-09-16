"""K-054'ün dört yeni kapısını tek bir çekiliş için ölçer. (Faz 11)

`research/degerlendirme.py` K-019'un yedi kapısını ölçüyor ve çıktısı Faz 4'ün deney
kayıtlarında donmuş durumda (`sq lab dogrula` onu yeniden üretiyor). Yeni kapılar oraya
eklenmedi, ayrı bir modülde duruyor — çünkü eklemek o kayıtların `cikti_hash`ini
değiştirir ve Faz 4'ün *"herhangi bir deney kaydından yeniden üretilebiliyor"* kriterini
kırardı (Faz 10'un aynı dersi, `Sonuc.evren`de).

## Dört kapı, üç pencere, bir ölçülemez

| Kapı | Nerede ölçülür | Not |
| --- | --- | --- |
| `pbo` | tam ölçüm penceresi | CSCV kendi bölmesini içeride kuruyor |
| `parametre_perturbasyonu` | in-sample | Seçim orada yapılıyor |
| `rejim_kararliligi` | out-of-sample | Kapı OOS performansını ölçer |
| `evren_dayanikliligi` | — | Tek sembolde **ölçülemez** (K-054); çok enstrümanlı koşuda `research/evren_dayaniklilik.py` |

Dördüncüsünün burada `None` dönmesi bir eksiklik değil, K-054'ün kendi cümlesi:
*"tek sembolde geliştirilen bir strateji de artık evrene karşı sınanmak zorunda."*
Ölçülemeyen kapı geçilmiş sayılmaz (K-019), yani tek sembollü her çekiliş bu kapıda
durur — K-045'in tek sembollü aramayı kapatmasının promotion tarafındaki karşılığı.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np

from scryne_quant.backtest.metrikler import bar_yili
from scryne_quant.common.maliyet import MaliyetModeli
from scryne_quant.common.zaman import timeframe_ms
from scryne_quant.research import pbo as pbo_mod
from scryne_quant.research import perturbasyon as pert_mod
from scryne_quant.research import rejim as rejim_mod
from scryne_quant.research.kapilar import Esik, KapiSonucu, degerlendir
from scryne_quant.research.bolme import Pencere
from scryne_quant.research.tarama import ASGARI_ISLEM, kosu, tara
from scryne_quant.strategy.temel import Strateji


class KapiV2Hatasi(ValueError):
    """Yeni kapı ölçümünün girdisi geçersiz."""


def olc(
    strateji_sinifi: type[Strateji],
    secenekler: Mapping[str, Sequence[Any]],
    maliyet: MaliyetModeli,
    sembol: str,
    timeframe: str,
    bar_dizileri: Mapping[str, np.ndarray],
    *,
    ins: Pencere,
    oos: Pencere,
    tam: Pencere,
    secim: str = "tepe",
    olcut: str = "sharpe",
    baslangic_sermaye: float = 10_000.0,
    asgari_islem: int = ASGARI_ISLEM,
    rejim_penceresi: int | None = None,
) -> dict[str, Any]:
    """Bir çekiliş için dört yeni kapının ölçümlerini üretir.

    Döner: `kapilar.degerlendir`in okuyacağı düz alanlar + `detay` bloğu. Detay kayda
    giriyor çünkü tek bir sayı (`pbo = 0,31`) o sayının hangi ızgarada, kaç adayla ve kaç
    kombinasyonda ölçüldüğünü söylemiyor — ve söylemeyen bir sayı yeniden okunamaz.
    """
    yil_bar = bar_yili(timeframe_ms(timeframe))
    # Rejim penceresi zamana bağlı (30 gün), bar sayısına değil — bkz. `rejim.PENCERE_GUN`.
    if rejim_penceresi is None:
        rejim_penceresi = rejim_mod.pencere_bar(timeframe_ms(timeframe))
    olcumler: dict[str, Any] = {}
    detay: dict[str, Any] = {}

    # --- in-sample: seçim + pertürbasyon
    tarama = tara(
        strateji_sinifi,
        secenekler,
        maliyet,
        sembol,
        timeframe,
        bar_dizileri,
        ins,
        olcut=olcut,
        baslangic_sermaye=baslangic_sermaye,
        asgari_islem=asgari_islem,
    )
    secilen = tarama.sec(secim)
    if secilen is None:
        # Geçerli aday yok: seçim yapılmadı, dolayısıyla seçime bağlı hiçbir kapı
        # ölçülemez. Sıfır yazmak "ölçüldü ve kötü" demek olurdu.
        detay["secim"] = {"secilen": None, "sebep": "geçerli aday yok"}
        return {
            "perturbasyon_dusus": None,
            "en_kotu_rejim_sharpe": None,
            "pbo": None,
            "evren_dayaniklilik_orani": None,
            "detay": detay,
        }

    pert = pert_mod.olc(tarama, secilen)
    olcumler["perturbasyon_dusus"] = pert.dusus
    detay["perturbasyon"] = pert.sozluk()
    detay["secim"] = {"yontem": secim, "secilen": secilen.sozluk_parametreler}

    # --- out-of-sample: rejim
    oos_sonuc = kosu(
        strateji_sinifi(**secilen.sozluk_parametreler),
        maliyet,
        sembol,
        timeframe,
        bar_dizileri,
        oos,
        baslangic_sermaye=baslangic_sermaye,
    )
    etiketler = rejim_mod.etiketle(bar_dizileri["close"], pencere=rejim_penceresi)[oos.dilim()]
    # `kosu` ısınma barlarını ölçümden düşürüyor; etiket dizisi de aynı yerden kesilmeli.
    etiket_olcum = etiketler[oos.olcum_baslangici :]
    rej = rejim_mod.olc(oos_sonuc.ozkaynak, etiket_olcum, yil_bar=yil_bar)
    olcumler["en_kotu_rejim_sharpe"] = rej.en_kotu_sharpe
    detay["rejim"] = rej.sozluk() | {"pencere": rejim_penceresi}

    # --- tam pencere: PBO
    try:
        matris, parametreler = pbo_mod.getiri_matrisi(
            strateji_sinifi,
            secenekler,
            maliyet,
            sembol,
            timeframe,
            bar_dizileri,
            tam,
            baslangic_sermaye=baslangic_sermaye,
            asgari_islem=asgari_islem,
        )
        pbo_sonucu = pbo_mod.cscv(matris, yil_bar=yil_bar)
        olcumler["pbo"] = pbo_sonucu.pbo
        detay["pbo"] = pbo_sonucu.sozluk() | {"aday_parametreleri": parametreler}
    except pbo_mod.PboHatasi as hata:
        olcumler["pbo"] = None
        detay["pbo"] = {"olculemedi": str(hata)}

    # --- evren dayanıklılığı: tek sembolde ölçülemez (K-054)
    olcumler["evren_dayaniklilik_orani"] = None
    detay["evren_dayanikliligi"] = {
        "olculemedi": (
            "tek sembollü çekiliş: çıkarılacak ikinci enstrüman yok. K-054 bunu bilerek "
            "ölçülemez bırakıyor — tek sembolde geliştirilen bir strateji de evrene karşı "
            "sınanmak zorunda."
        )
    }

    olcumler["detay"] = detay
    return olcumler




# --------------------------------------------------------------------- eşikler (K-054)

#: Kalibrasyon kuralı: her kapı için iki ızgarada (`donchian` 12 nokta, `rsi_donus` 32
#: nokta) null dağılımı ölçüldü ve **daha sıkı olan** eşik alındı — `<=` kapısında düşük,
#: `>=` kapısında yüksek olanı. Belirsizlikte aleyhte yuvarla (K-007): eşik ızgara şekline
#: bağlı çıktı ve bir aday, kendi ızgarasını seçerek gevşek eşikli tarafa kaçamamalı.
#: Ham örnekler `runs/kalibrasyon-v2/`, rapor `docs/Faz-11-Dogrulama-Raporu.md`.
YANLIS_POZITIF: Final = 0.05

PBO_ESIGI: Final = 0.0087
PERTURBASYON_ESIGI: Final = 0.0565
REJIM_ESIGI: Final = 0.6850
EVREN_DAYANIKLILIK_ESIGI: Final = 0.75

ESIKLER_V2: Final[tuple[Esik, ...]] = (
    Esik(
        ad="pbo",
        alan="pbo",
        sinir=PBO_ESIGI,
        yon="<=",
        gerekce=(
            "Backtest overfitting olasılığı (CSCV, 16 dilim, 12.870 kombinasyon). Literatürün "
            "referansı 0,5 ve iid gürültüde ortalama gerçekten 0,503 çıktı — ama tek ölçüm "
            "±0,20 sapıyor ve **gerçek ızgaralarda null çok daha düşük**: komşu noktalar "
            "neredeyse aynı strateji olduğu için IS-en iyisi edge olmadan da OOS'ta iyi "
            "kalıyor. Kaydırma null'ında medyan 0,237 (donchian); yani 0,5 eşiği edge'siz "
            "ızgaraların %90'ından fazlasını geçirirdi. Ölçülen %5 sınırı donchian 0,0087 "
            "(GA 0,006-0,017, 200 iterasyon), rsi_donus 0,0462 (GA 0,022-0,060, 100 "
            "iterasyon); sıkı olanı alındı. Eşik ızgara şekline bağlı: yeni bir ızgara "
            "biçimi yeniden ölçüm ister."
        ),
    ),
    Esik(
        ad="parametre_perturbasyonu",
        alan="perturbasyon_dusus",
        sinir=PERTURBASYON_ESIGI,
        yon="<=",
        gerekce=(
            "Seçilen noktanın, ızgarada tek eksende bir adım uzaktaki komşularının "
            "medyanından ne kadar yüksek olduğu (ızgaranın skor aralığına oranla). Edge'siz "
            "bir ızgarada argmax tanımı gereği bir zirvedir: null medyanı 0,246 (donchian). "
            "Ölçülen %5 sınırı donchian 0,0752 (GA 0,062-0,097), rsi_donus 0,0565 (GA "
            "0,048-0,078); sıkı olanı alındı. `parametre_kararliligi` başka bir şey ölçüyor "
            "(katmanlar arası seçim değişkenliği, K-054)."
        ),
    ),
    Esik(
        ad="rejim_kararliligi",
        alan="en_kotu_rejim_sharpe",
        sinir=REJIM_ESIGI,
        yon=">=",
        gerekce=(
            "OOS'ta en kötü rejimin Sharpe'ı; rejim, kıyasın 720 barlık geriye dönük "
            "getirisinin işareti (nedensel, parametresiz — rejim motoru Faz 12). Bir rejim "
            "OOS barlarının %10'undan azsa kapı ölçülemez. Edge'siz dünyada ızgaranın en "
            "iyisinin en kötü rejim Sharpe'ı: donchian medyan −0,74, %95 sınırı 0,481 (GA "
            "0,078-0,738, 200 iterasyon); rsi_donus %95 sınırı 0,685 (GA 0,539-1,176, 100 "
            "iterasyon); sıkı (yüksek) olanı alındı. Aralıklar geniş: kuyruk ince. "
            "Daraltmanın yolu iterasyonu artırmak, eşiği yuvarlamak değil."
        ),
    ),
    Esik(
        ad="evren_dayanikliligi",
        alan="evren_dayaniklilik_orani",
        sinir=EVREN_DAYANIKLILIK_ESIGI,
        yon=">=",
        gerekce=(
            "En yüksek katkılı enstrüman evrenden düşürülüp yeniden koşulduğunda Sharpe'ın "
            "ne kadarı kalıyor. Null'dan kalibre **edilemiyor** (null edge'i yok eder, bu kapı "
            "yoğunlaşmayı ölçüyor); yapısal ölçüm: evren kıyası 2023-01…2026-08'de 3-20 "
            "enstrümanla koşuldu, oran 0,832-1,023 bandında kaldı (en yoğun ölçülebilir "
            "kurulum 0,832). 0,75 bandın altında: 'performansın dörtte birinden fazlası tek "
            "bir isme bağlı'. Bant içinden bir **iştah** seçimi ve öyle işaretli; Faz 12'de "
            "gerçek cross-sectional adaylarla yeniden ölçülür. Tek sembolde ve Sharpe ≤ 0 "
            "iken ölçülemez (K-054)."
        ),
    ),
)


def kapilari_degerlendir(
    strateji: str,
    olcumler: Mapping[str, Any],
    *,
    mutlak_engeller: list[str] | None = None,
) -> KapiSonucu:
    """Yalnızca K-054'ün dört yeni kapısını değerlendirir.

    K-019'un yedi kapısıyla birleştirmek `butun_kapilar` ile yapılır; ayrı durmalarının
    sebebi raporlama: 38 çekilişin yeni kapılardaki durumu, eski kapılardaki durumundan
    bağımsız okunabilmeli.
    """
    kapilar: dict[str, dict[str, Any]] = {}
    for esik in ESIKLER_V2:
        deger = olcumler.get(esik.alan)
        kapilar[esik.ad] = {
            "deger": deger,
            "sinir": esik.sinir,
            "yon": esik.yon,
            "gecti": esik.gecti_mi(deger),
        }
    return KapiSonucu(strateji=strateji, kapilar=kapilar, mutlak_engeller=list(mutlak_engeller or []))


def butun_kapilar(
    strateji: str,
    olcumler: Mapping[str, Any],
    *,
    mutlak_engeller: list[str] | None = None,
) -> KapiSonucu:
    """K-019'un yedi + K-054'ün dört kapısı. Promotion'un okuduğu tam liste."""
    eski = degerlendir(strateji, olcumler, mutlak_engeller=mutlak_engeller)
    yeni = kapilari_degerlendir(strateji, olcumler)
    return KapiSonucu(
        strateji=strateji,
        kapilar={**eski.kapilar, **yeni.kapilar},
        mutlak_engeller=eski.mutlak_engeller,
    )


def esik_tablosu() -> list[dict[str, Any]]:
    return [e.sozluk() for e in ESIKLER_V2]


__all__ = [
    "ESIKLER_V2",
    "KapiV2Hatasi",
    "butun_kapilar",
    "esik_tablosu",
    "kapilari_degerlendir",
    "olc",
]
