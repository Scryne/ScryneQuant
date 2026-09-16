"""Strateji başına varsayılan tarama ızgaraları. (Faz 4)

Izgaralar **stratejilerin içinde değil burada** duruyor: `strategy/` paketi araştırma
katmanını tanımaz (K-003'ün ruhu), ve bir ızgara stratejinin tanımı değil, ona sorulan
sorunun tanımıdır.

**Izgaralar bilerek küçük.** 1.000 kombinasyon denemek, gürültünün en şanslı örneğini
"en iyi parametre" diye sunmanın en kestirme yolu. Her ızgara 24-48 nokta: parametre
duyarlılığını (plato mu tepe mi) görmeye yetecek kadar geniş, bulunanı ciddiye almayı
zorlaştıracak kadar dar. §16.2'nin overfitting uyarısı tam olarak bunu söylüyor.

**Maruziyet ızgaraya girmiyor.** Pozisyon büyüklüğü risk motorunun kararıdır (Faz 5);
burada sabit tutulmazsa tarama, "daha çok risk al" cevabını her zaman bulur — çünkü
yükselen bir varlıkta maruziyeti artırmak Sharpe'ı değil ama getiriyi her koşulda büyütür.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

#: Tüm ızgaralarda sabit tutulan hedef maruziyet. Bkz. modül docstring'i.
SABIT_MARUZIYET: Final = 0.2

IZGARALAR: Final[dict[str, dict[str, Sequence[Any]]]] = {
    # Kıyas ölçütünün ızgarası tek noktalı: al-tut'ta optimize edilecek bir şey yok,
    # ve olmaması gerekiyor — kıyas sabit bir çizgi olmalı, ayarlanan bir rakip değil.
    "al_tut": {"maruziyet": (SABIT_MARUZIYET,)},
    "sma_kesisim": {
        "hizli": (10, 20, 30, 50),
        "yavas": (50, 100, 150, 200),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "ema_kesisim": {
        "hizli": (10, 20, 30, 50),
        "yavas": (50, 100, 150, 200),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "rsi_donus": {
        "pencere": (7, 14, 21),
        "alt": (20.0, 25.0, 30.0, 35.0),
        "ust": (60.0, 70.0, 80.0),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "donchian": {
        "giris": (20, 40, 55, 80),
        "cikis": (10, 20, 40),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "momentum": {
        "pencere": (12, 24, 48, 96),
        "giris_esigi": (1.0, 2.0, 4.0),
        "cikis_esigi": (-1.0, -2.0, -4.0),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    # --- Faz 4'e dönüş 3: kalabalıklaşma ailesi (K-042) ---------------------
    # Eşikler **persentil**, mutlak değil: funding'in medyanı kalıcı pozitif, mutlak bir
    # eşik neredeyse hep doğru olur ve hiçbir şey ayırt etmez (K-042/3).
    # Pencereler 1h barda: 120 = 5 gün, 240 = 10 gün, 480 = 20 gün.
    "funding_ters": {
        "pencere": (120, 240, 480),
        "giris_p": (0.05, 0.10, 0.20),
        "cikis_p": (0.80, 0.90, 0.95),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    # Kanal parametreleri `donchian`ın ızgarasından **daraltıldı** (55/20 ve 40/20):
    # ölçülen fark tek bir şeye — funding filtresine — atfedilebilmeli. Kanalı da
    # taramak, iki değişkeni aynı anda oynatmak ve hangisinin işe yaradığını
    # bilememek olurdu.
    "funding_filtre": {
        "giris": (40, 55),
        "cikis": (20,),
        "funding_pencere": (120, 240, 480),
        "azami_p": (0.60, 0.70, 0.80, 0.90),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "funding_egilim": {
        "birikim": (24, 72, 168),
        "pencere": (240, 480),
        "giris_p": (0.10, 0.20),
        "cikis_p": (0.80, 0.90),
        "maruziyet": (SABIT_MARUZIYET,),
    },
    "cok_faktor": {
        "trend_pencere": (50, 100, 200),
        "roc_pencere": (12, 24, 48),
        "hacim_pencere": (20,),
        "giris_oyu": (2, 3),
        "cikis_oyu": (1, 2),
        "maruziyet": (SABIT_MARUZIYET,),
    },
}


class IzgaraYok(KeyError):
    """Bu strateji için tanımlı ızgara yok."""


def izgara(strateji_adi: str) -> Mapping[str, Sequence[Any]]:
    """Bir stratejinin varsayılan ızgarası."""
    try:
        return IZGARALAR[strateji_adi]
    except KeyError:
        raise IzgaraYok(
            f"{strateji_adi!r} için ızgara tanımlı değil; tanımlı: {', '.join(sorted(IZGARALAR))}"
        ) from None


def boyut(strateji_adi: str) -> int:
    """Izgaradaki ham kombinasyon sayısı (stratejinin reddedecekleri dahil)."""
    n = 1
    for degerler in izgara(strateji_adi).values():
        n *= len(degerler)
    return n


# --------------------------------------------------------------------- Faz 12: evren

#: Çok enstrümanlı çekilişler: çekiliş adı → (strateji adı, ızgara). (Faz 12, K-051)
#:
#: Tek sembollü `IZGARALAR` strateji adıyla anahtarlanıyor çünkü orada strateji başına tek
#: ızgara vardı. Programlarda aynı aile birden çok çekiliş veriyor (haftalık / aylık
#: yeniden dengeleme); her biri ayrı bir ızgara, dolayısıyla ayrı bir hipotez kimliği.
#:
#: **Hepsi 12 noktalı** (4 pencere × 3 yoğunluk): K-058'in sıkı `pbo` eşiği 12 noktalı
#: donchian ızgarasında ölçüldü; aynı boyutta kalmak "yeni ızgara biçimi" farkını
#: küçültür ama kapatmaz — çok enstrümanlı null ölçülmedi (Faz 12 raporu, açık kalem).
#: `yeniden_dengele_bar` ve `hedef_brut` tek değerli: ekseni değil, çekilişin kimliği.
#: Pencereler 1h barda: 24 = 1 gün, 168 = 1 hafta, 720 = 30 gün, 1440 = 60 gün.
_YOGUNLUK: Final = (5, 10, 20)
_ORTA_VADE: Final = (168, 336, 720, 1440)
_KISA_VADE: Final = (24, 72, 168, 336)
HAFTALIK: Final = 168
AYLIK: Final = 720


def _evren(pencere: Sequence[int], dengeleme: int) -> dict[str, Sequence[Any]]:
    return {
        "pencere": tuple(pencere),
        "azami_enstruman": _YOGUNLUK,
        "yeniden_dengele_bar": (dengeleme,),
        "hedef_brut": (SABIT_MARUZIYET,),
    }


#: Sıra durma kuralının sırasıdır: ilk dört çekiliş ilk iki ailenin (güç, ters dönüş).
EVREN_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    "kesitsel_guc_haftalik": ("kesitsel_guc", _evren(_ORTA_VADE, HAFTALIK)),
    "kesitsel_guc_aylik": ("kesitsel_guc", _evren(_ORTA_VADE, AYLIK)),
    "kesitsel_ters_haftalik": ("kesitsel_ters", _evren(_KISA_VADE, HAFTALIK)),
    "kesitsel_ters_aylik": ("kesitsel_ters", _evren(_KISA_VADE, AYLIK)),
    "kesitsel_dusuk_oynaklik_haftalik": ("kesitsel_dusuk_oynaklik", _evren(_ORTA_VADE, HAFTALIK)),
    "kesitsel_dusuk_oynaklik_aylik": ("kesitsel_dusuk_oynaklik", _evren(_ORTA_VADE, AYLIK)),
}


_TUREV_PENCERELI: Final[dict[str, Sequence[Any]]] = {
    "pencere": (72, 168, 336, 720),
    "dislama_orani": (0.1, 0.2, 0.3),
    "azami_enstruman": (10,),
    "yeniden_dengele_bar": (HAFTALIK,),
    "hedef_brut": (SABIT_MARUZIYET,),
}

#: `turev_evren` programının çekilişleri (Faz 12). Sıra durma kuralının sırası: önce iki
#: funding çekilişi; ikisi de filtresiz kıyası geçmezse basis çekilişleri harcanmaz.
#: Dengeleme haftalık ve sabit: funding hızlı değişen bir bilgi, aylık dengelemede filtre
#: bayat veriyle karar verirdi. `hedef_brut` kesitsel programla aynı (0,2).
TUREV_CEKILISLERI: Final[dict[str, tuple[str, dict[str, Sequence[Any]]]]] = {
    # Son gerçekleşen oran (8 s eşdeğer): anlık kaldıraç baskısı. İkinci eksen yoğunluk;
    # kıyas seçilen yoğunlukla koşulur, fark yalnızca dışlamadan gelir.
    "turev_funding_kesit": ("evren_funding_kesit", {
        "dislama_orani": (0.1, 0.2, 0.3, 0.5),
        "azami_enstruman": _YOGUNLUK,
        "yeniden_dengele_bar": (HAFTALIK,),
        "hedef_brut": (SABIT_MARUZIYET,),
    }),
    # Son W saatte fiilen ödenen toplam: süregelen baskı (K-042/5'in zaman ölçeği farkı).
    # Yoğunluk kıyasın varsayılanında (10) sabit; eksen birikim penceresi.
    "turev_funding_birikim": ("evren_funding_birikim", _TUREV_PENCERELI),
    # Basis çekilişleri hipotez 43-44 görüldükten **sonra** kaydedildi; sonuca bakılarak
    # seçilmesin diye ızgaraları `turev_funding_birikim`in birebir aynası.
    "turev_basis": ("evren_basis", _TUREV_PENCERELI),
    "turev_funding_basis": ("evren_funding_basis", _TUREV_PENCERELI),
}

#: Program → çekilişleri. Koşucu çekilişin programını buradan bulur.
PROGRAM_CEKILISLERI: Final[dict[str, tuple[str, ...]]] = {
    "kesitsel_fiyat": tuple(EVREN_CEKILISLERI),
    "turev_evren": tuple(TUREV_CEKILISLERI),
}


def evren_cekilisi(ad: str) -> tuple[str, Mapping[str, Sequence[Any]]]:
    """Bir evren çekilişinin `(strateji adı, ızgara)` çifti."""
    hepsi = {**EVREN_CEKILISLERI, **TUREV_CEKILISLERI}
    try:
        return hepsi[ad]
    except KeyError:
        raise IzgaraYok(
            f"{ad!r} tanımlı bir evren çekilişi değil; tanımlı: {', '.join(hepsi)}"
        ) from None


def cekilis_programi(ad: str) -> str:
    """Çekilişin ait olduğu araştırma programı."""
    for program, adlar in PROGRAM_CEKILISLERI.items():
        if ad in adlar:
            return program
    raise IzgaraYok(f"{ad!r} hiçbir programın çekilişi değil")
